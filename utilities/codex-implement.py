# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Run Codex as a milestone implementer in one fixed form, so a permission rule can allow only this script.

Usage:
  codex-implement.py WORKTREE RUN_DIR BRIEF [--dry-run]

WORKTREE  A linked git worktree of this repository under its .claude/worktrees/.
RUN_DIR   An existing directory directly inside the configured run store
          (`utilities/run-store.py`).
BRIEF     A file inside RUN_DIR; Codex is told to read it and carry it out.

The command is `codex exec --sandbox workspace-write --cd WORKTREE` with network access and high
reasoning effort. Writes are limited to the worktree, /tmp, this repository's .git directory
(so a linked worktree can commit), RUN_DIR and the pip cache. The caller passes no Codex flags
and no prompt text. Every path must be absolute, already resolved (no symlink component, no `.`
or `..`), and spelled with [A-Za-z0-9._/-] only. Codex's output goes to
RUN_DIR/codex-<UTC time>.log and its final message to RUN_DIR/last-message-<UTC time>.md; both
paths are printed first. With --dry-run the command is printed and not run.

Exit codes: 0 Codex ran and exited 0; 1 Codex exited non-zero; 2 usage or validation error;
3 the codex binary is missing.
"""

import datetime
import importlib.util
import os
import re
import shutil
import subprocess
import sys

SAFE = re.compile(r"/[A-Za-z0-9._/-]+")
PROMPT = ("Read {brief} and carry it out completely. Your final message is your report to the "
          "orchestrator.")
UTILITIES = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(UTILITIES)


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


def run_store():
  spec = importlib.util.spec_from_file_location("run_store", os.path.join(UTILITIES, "run-store.py"))
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  path, source = module.run_store()
  if path is None:
    fail(f"run store not configured (see {source})")
  store = os.path.realpath(path)
  if not os.path.isdir(store):
    fail(f"run store is not a directory: {store}")
  return store


def build(worktree, run_dir, brief, stamp):
  worktree = clean_path(worktree, "WORKTREE")
  run_dir = clean_path(run_dir, "RUN_DIR")
  brief = clean_path(brief, "BRIEF")
  worktrees = os.path.join(REPO, ".claude", "worktrees")
  if os.path.dirname(worktree) != worktrees:
    fail(f"WORKTREE must be directly under {worktrees}: {worktree}")
  if not os.path.isfile(os.path.join(worktree, ".git")):
    fail(f"WORKTREE is not a linked git worktree: {worktree}")
  store = run_store()
  if os.path.dirname(run_dir) != store or not os.path.isdir(run_dir):
    fail(f"RUN_DIR must be an existing directory directly inside {store}: {run_dir}")
  if os.path.dirname(brief) != run_dir or not os.path.isfile(brief):
    fail(f"BRIEF must be a file directly inside RUN_DIR: {brief}")
  log = os.path.join(run_dir, f"codex-{stamp}.log")
  last = os.path.join(run_dir, f"last-message-{stamp}.md")
  writable = [os.path.join(REPO, ".git"), run_dir]
  pip_cache = os.path.realpath(os.path.expanduser("~/.cache/pip"))
  if os.path.isdir(pip_cache):
    writable.append(pip_cache)
  add_dirs = [arg for path in writable for arg in ("--add-dir", path)]
  cmd = [
      "codex", "exec", "--sandbox", "workspace-write", *add_dirs,
      "-c", "sandbox_workspace_write.network_access=true",
      "-c", "model_reasoning_effort=high",
      "--cd", worktree, "--output-last-message", last,
      PROMPT.format(brief=brief),
  ]
  return cmd, log, last


def main(argv):
  dry = "--dry-run" in argv
  args = [a for a in argv if a != "--dry-run"]
  if len(args) != 3:
    fail("usage: codex-implement.py WORKTREE RUN_DIR BRIEF [--dry-run]")
  stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  cmd, log, last = build(*args, stamp)
  if dry:
    print(cmd)
    return 0
  if shutil.which("codex") is None:
    print("codex-implement: codex is not installed", file=sys.stderr)
    return 3
  print(f"log: {log}\nlast message: {last}", flush=True)
  try:
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
  except OSError as exc:
    fail(f"cannot create LOG: {exc}")
  with os.fdopen(fd, "w", encoding="utf-8") as out:
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                          check=False)
  return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
