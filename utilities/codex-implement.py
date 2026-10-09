# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Run Codex as a milestone implementer in one fixed form, so a permission rule can allow only this script.

Usage:
  codex-implement.py WORKTREE RUN_DIR BRIEF [--dry-run]

WORKTREE  A linked git worktree of this repository, directly under its .claude/worktrees/, whose
          .git file and metadata point at each other.
RUN_DIR   An existing directory directly inside the run store named by `run_store` in
          ~/.config/driver-lab/config.toml (the home directory comes from the password database;
          DRIVER_LAB_RUNS, XDG_CONFIG_HOME and HOME are ignored, so the caller cannot move it).
BRIEF     A file directly inside RUN_DIR; Codex is told to read it and carry it out.

The command is `codex exec --sandbox workspace-write --cd WORKTREE` with network access and high
reasoning effort. Codex may write only the worktree, /tmp, RUN_DIR and the pip cache (when it is
a real directory). It gets no write access to any git directory, so it cannot plant hooks or
configuration that would later run outside its sandbox; it leaves its changes uncommitted, and
the orchestrator reviews and commits them. The caller passes no Codex flags and no prompt text.

After Codex exits, the script checks the worktree for files that would act outside the sandbox
the next time an agent or git works there: a changed or replaced `.git` file (restored), and any
`.claude/` directory or CLAUDE.md, CLAUDE.local.md or AGENTS.override.md file that was not there
before. Any of these is reported and the exit code is 4.

Every path must be absolute, already resolved (no symlink component, no `.` or `..`), and spelled
with [A-Za-z0-9._/-] only. Codex's output goes to RUN_DIR/codex-<UTC time>.log and its final
message to RUN_DIR/last-message-<UTC time>.md; neither may exist beforehand, and both paths are
printed first. With --dry-run the command is printed and not run.

Exit codes: 0 Codex ran and exited 0; 1 Codex exited non-zero; 2 usage or validation error;
3 the codex binary is missing; 4 the worktree was tampered with (see above).
"""

import datetime
import os
import pwd
import re
import shutil
import subprocess
import sys
import tomllib

SAFE = re.compile(r"/[A-Za-z0-9._/-]+")
PROMPT = ("Read {brief} and carry it out completely. Leave your changes uncommitted in the "
          "working tree; do not run git commit. Your final message is your report to the "
          "orchestrator.")
REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
AGENT_FILES = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.override.md")


def fail(msg):
  print(f"codex-implement: {msg}", file=sys.stderr)
  sys.exit(2)


def clean_path(arg, what):
  """Return arg if it is absolute, resolved and safely spelled; exit 2 otherwise."""
  if not SAFE.fullmatch(arg) or "//" in arg:
    fail(f"{what} must be an absolute path of [A-Za-z0-9._/-]: {arg!r}")
  parts = arg.split("/")
  if "." in parts or ".." in parts:
    fail(f"{what} may not contain . or .. components: {arg}")
  if os.path.realpath(arg) != arg.rstrip("/"):
    fail(f"{what} passes through a symlink or is not resolved: {arg}")
  return arg.rstrip("/")


def home():
  return pwd.getpwuid(os.getuid()).pw_dir


def run_store():
  cfg = os.path.join(home(), ".config", "driver-lab", "config.toml")
  try:
    with open(cfg, "rb") as stream:
      value = tomllib.load(stream).get("run_store")
  except (OSError, tomllib.TOMLDecodeError) as exc:
    fail(f"cannot read run_store from {cfg}: {exc}")
  if not isinstance(value, str) or not value:
    fail(f"run_store is not set in {cfg}")
  store = os.path.realpath(os.path.expanduser(value))
  if not os.path.isdir(store):
    fail(f"run store is not a directory: {store}")
  return store


def read_bytes(path):
  with open(path, "rb") as f:
    return f.read()


def check_worktree(worktree):
  worktrees = os.path.join(REPO, ".claude", "worktrees")
  if os.path.dirname(worktree) != worktrees:
    fail(f"WORKTREE must be directly under {worktrees}: {worktree}")
  dot_git = os.path.join(worktree, ".git")
  if os.path.islink(dot_git) or not os.path.isfile(dot_git):
    fail(f"WORKTREE is not a linked git worktree: {worktree}")
  meta = os.path.join(REPO, ".git", "worktrees", os.path.basename(worktree))
  if read_bytes(dot_git) != f"gitdir: {meta}\n".encode():
    fail(f"WORKTREE's .git file does not point at {meta}")
  back = os.path.join(meta, "gitdir")
  if not os.path.isfile(back) or read_bytes(back) != f"{dot_git}\n".encode():
    fail(f"{back} does not point back at the worktree")
  return dot_git


def agent_files(worktree):
  """Paths in the worktree that an agent harness would load as configuration or instructions."""
  found = set()
  for top, dirs, files in os.walk(worktree):
    dirs[:] = [d for d in dirs if d not in (".git", ".venv", ".venv-sf2", "node_modules")]
    if ".claude" in dirs or ".claude" in files:
      found.add(os.path.join(top, ".claude"))
    found.update(os.path.join(top, f) for f in files if f in AGENT_FILES)
  return found


def build(worktree, run_dir, brief, stamp):
  worktree = clean_path(worktree, "WORKTREE")
  run_dir = clean_path(run_dir, "RUN_DIR")
  brief = clean_path(brief, "BRIEF")
  check_worktree(worktree)
  store = run_store()
  if os.path.dirname(run_dir) != store or not os.path.isdir(run_dir):
    fail(f"RUN_DIR must be an existing directory directly inside {store}: {run_dir}")
  if os.path.dirname(brief) != run_dir or not os.path.isfile(brief):
    fail(f"BRIEF must be a file directly inside RUN_DIR: {brief}")
  log = os.path.join(run_dir, f"codex-{stamp}.log")
  last = os.path.join(run_dir, f"last-message-{stamp}.md")
  for path in (log, last):
    if os.path.lexists(path):
      fail(f"output path already exists: {path}")
  writable = [run_dir]
  pip_cache = os.path.join(home(), ".cache", "pip")
  if os.path.isdir(pip_cache) and os.path.realpath(pip_cache) == pip_cache:
    writable.append(pip_cache)
  add_dirs = [arg for path in writable for arg in ("--add-dir", path)]
  cmd = [
      "codex", "exec", "--sandbox", "workspace-write", *add_dirs,
      "-c", "sandbox_workspace_write.network_access=true",
      "-c", "model_reasoning_effort=high",
      "--cd", worktree, "--output-last-message", last,
      PROMPT.format(brief=brief),
  ]
  return cmd, worktree, log


def main(argv):
  dry = "--dry-run" in argv
  args = [a for a in argv if a != "--dry-run"]
  if len(args) != 3:
    fail("usage: codex-implement.py WORKTREE RUN_DIR BRIEF [--dry-run]")
  stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  cmd, worktree, log = build(*args, stamp)
  if dry:
    print(cmd)
    return 0
  if shutil.which("codex") is None:
    print("codex-implement: codex is not installed", file=sys.stderr)
    return 3
  dot_git = os.path.join(worktree, ".git")
  dot_git_bytes = read_bytes(dot_git)
  before = agent_files(worktree)
  print(f"log: {log}\nlast message: {cmd[cmd.index('--output-last-message') + 1]}", flush=True)
  try:
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
  except OSError as exc:
    fail(f"cannot create LOG: {exc}")
  with os.fdopen(fd, "w", encoding="utf-8") as out:
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                          check=False)
  tampered = []
  if os.path.islink(dot_git) or not os.path.isfile(dot_git) or read_bytes(dot_git) != dot_git_bytes:
    if os.path.isdir(dot_git) and not os.path.islink(dot_git):
      shutil.rmtree(dot_git)
    elif os.path.lexists(dot_git):
      os.remove(dot_git)
    with open(dot_git, "wb") as f:
      f.write(dot_git_bytes)
    tampered.append(f"{dot_git} was changed (restored)")
  tampered += [f"{path} appeared" for path in sorted(agent_files(worktree) - before)]
  if tampered:
    for line in tampered:
      print(f"codex-implement: TAMPER: {line}", file=sys.stderr)
    return 4
  return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
