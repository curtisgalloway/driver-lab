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
reasoning effort. The sandbox may write only two places: the worktree, and a fresh private
temporary directory the script creates (Codex's TMPDIR; /tmp itself is excluded). Nothing
outside the sandbox reads that temporary directory. RUN_DIR, the run store, the pip cache and
every git directory stay read-only to Codex, so it cannot leave hooks, configuration, cached
packages or symlinks that something outside its sandbox later follows. The Codex CLI itself,
which runs outside the sandbox, writes the final message into RUN_DIR, where the sandbox cannot
plant a symlink. Codex leaves its changes uncommitted (the prompt says so), puts what belongs in
the run ledger into its final message, and the orchestrator reviews and commits.

After Codex exits, the script compares the worktree with a snapshot taken before the run and
reports, with exit code 4:
  - a changed, replaced or removed `.git` file (restored from the snapshot);
  - any added, changed or removed agent configuration or instructions: AGENTS.md,
    AGENTS.override.md, CLAUDE.md, CLAUDE.local.md, GEMINI.md, and anything under a .claude,
    .codex, .agents or .gemini directory, anywhere in the worktree;
  - any new symlink whose target resolves outside the worktree.
Everything else Codex wrote is code to review before it runs anywhere: do not run the worktree's
own virtual environments or scripts outside a sandbox before reading the diff; reviewers build
fresh environments in an export.

Every path must be absolute, already resolved (no symlink component, no `.` or `..`), and spelled
with [A-Za-z0-9._/-] only. The script writes RUN_DIR/codex-<UTC time>.log and Codex writes
RUN_DIR/last-message-<UTC time>.md; neither may exist beforehand, and both paths are printed
first. With --dry-run the command is printed and not run.

Exit codes: 0 Codex ran and exited 0; 1 Codex exited non-zero; 2 usage or validation error;
3 the codex binary is missing; 4 the worktree was tampered with (see above).
"""

import datetime
import hashlib
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

SAFE = re.compile(r"/[A-Za-z0-9._/-]+")
PROMPT = ("Read {brief} and carry it out completely. Leave your changes uncommitted in the "
          "working tree; do not run git commit. You cannot write the run directory: put what "
          "belongs in its ledger into your final message, which is your report to the "
          "orchestrator.")
REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
AGENT_FILES = ("AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md", "GEMINI.md")
AGENT_DIRS = (".claude", ".codex", ".agents", ".gemini")


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


def fingerprint(path):
  if os.path.islink(path):
    return "link:" + os.readlink(path)
  if os.path.isfile(path):
    return "file:" + hashlib.sha256(read_bytes(path)).hexdigest()
  return "dir" if os.path.isdir(path) else "other"


def snapshot(worktree):
  """Agent configuration and outward symlinks in the worktree, keyed by path."""
  agent, links = {}, set()
  for top, dirs, files in os.walk(worktree):
    if top == worktree:
      dirs[:] = [d for d in dirs if d != ".git"]
    in_agent_dir = any(part in AGENT_DIRS for part in os.path.relpath(top, worktree).split(os.sep))
    for name in dirs + files:
      path = os.path.join(top, name)
      if in_agent_dir or name in AGENT_DIRS or name in AGENT_FILES:
        agent[path] = fingerprint(path)
      if os.path.islink(path):
        target = os.path.realpath(path)
        if target != worktree and not target.startswith(worktree + os.sep):
          links.add(path)
  return agent, links


def build(worktree, run_dir, brief, stamp, tmpdir):
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
  cmd = [
      "codex", "exec", "--sandbox", "workspace-write", "--add-dir", tmpdir,
      "-c", "sandbox_workspace_write.network_access=true",
      "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
      "-c", "model_reasoning_effort=high",
      "--cd", worktree, "--output-last-message", last,
      PROMPT.format(brief=brief),
  ]
  return cmd, worktree, log, last


def restore(dot_git, data):
  if os.path.isdir(dot_git) and not os.path.islink(dot_git):
    shutil.rmtree(dot_git)
  elif os.path.lexists(dot_git):
    os.remove(dot_git)
  fd = os.open(dot_git, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
  with os.fdopen(fd, "wb") as f:
    f.write(data)


def main(argv):
  dry = "--dry-run" in argv
  args = [a for a in argv if a != "--dry-run"]
  if len(args) != 3:
    fail("usage: codex-implement.py WORKTREE RUN_DIR BRIEF [--dry-run]")
  stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  if dry:
    cmd, _, _, _ = build(*args, stamp, "<private tmpdir>")
    print(cmd)
    return 0
  if shutil.which("codex") is None:
    print("codex-implement: codex is not installed", file=sys.stderr)
    return 3
  tmpdir = os.path.realpath(tempfile.mkdtemp(prefix="codex-implement-"))
  try:
    cmd, worktree, log, last = build(*args, stamp, tmpdir)
    dot_git = os.path.join(worktree, ".git")
    dot_git_bytes = read_bytes(dot_git)
    agent_before, links_before = snapshot(worktree)
    print(f"log: {log}\nlast message: {last}", flush=True)
    try:
      fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
      fail(f"cannot create LOG: {exc}")
    env = dict(os.environ, TMPDIR=tmpdir)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
      proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                            check=False, env=env)
  finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
  tampered = []
  if os.path.islink(dot_git) or not os.path.isfile(dot_git) or read_bytes(dot_git) != dot_git_bytes:
    restore(dot_git, dot_git_bytes)
    tampered.append(f"{dot_git} was changed (restored)")
  agent_after, links_after = snapshot(worktree)
  for path in sorted(set(agent_before) | set(agent_after)):
    if agent_before.get(path) != agent_after.get(path):
      what = ("appeared" if path not in agent_before else
              "was removed" if path not in agent_after else "changed")
      tampered.append(f"{path} {what}")
  tampered += [f"{path} links outside the worktree" for path in sorted(links_after - links_before)]
  if tampered:
    for line in tampered:
      print(f"codex-implement: TAMPER: {line}", file=sys.stderr)
    return 4
  return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
