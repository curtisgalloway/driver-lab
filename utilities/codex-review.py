#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
# Preserve this command's hyphenated filename.
# pylint: disable=invalid-name
"""Run a Codex review in one of two fixed forms, so a permission rule can allow only this script.

Usage:
  codex-review.py ro  CHECKOUT BRIEF LOG [--dry-run]
  codex-review.py net REVIEW_DIR BRIEF LOG [--dry-run]

ro   Read-only review of a git checkout: `codex exec --sandbox read-only --cd CHECKOUT`.
     BRIEF and LOG must lie under the system temp directory.
net  Networked review in a throwaway directory: `codex exec --sandbox workspace-write` with
     network access, `--skip-git-repo-check --cd REVIEW_DIR`. REVIEW_DIR must lie under the
     system temp directory and outside any git work tree; BRIEF must lie inside REVIEW_DIR.

The prompt is fixed ("read BRIEF and carry it out"); the caller passes no Codex flags and no
prompt text. Every path must be absolute, already resolved (no symlink component, no `.` or
`..`), and spelled with [A-Za-z0-9._/-] only. Output goes to LOG (overwritten). With
--dry-run the command is printed and not run.

Exit codes: 0 Codex ran and exited 0; 1 Codex exited non-zero; 2 usage or validation error;
3 the codex binary is missing.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

SAFE = re.compile(r"/[A-Za-z0-9._/-]+")
PROMPT = "Read {brief} and carry out that review completely. Print the ranked findings as your final answer."


def fail(msg):
  print(f"codex-review: {msg}", file=sys.stderr)
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


def under(path, root):
  return path == root or path.startswith(root + "/")


def in_git_tree(path):
  probe = path
  while True:
    if os.path.exists(os.path.join(probe, ".git")):
      return True
    parent = os.path.dirname(probe)
    if parent == probe:
      return False
    probe = parent


def build(mode, target, brief, log):
  tmp = os.path.realpath(tempfile.gettempdir())
  target = clean_path(target, "target directory")
  brief = clean_path(brief, "BRIEF")
  log = clean_path(log, "LOG")
  if not os.path.isdir(target):
    fail(f"not a directory: {target}")
  if not os.path.isfile(brief):
    fail(f"BRIEF is not a file: {brief}")
  if not under(log, tmp) or not os.path.isdir(os.path.dirname(log)):
    fail(f"LOG must be in an existing directory under {tmp}: {log}")
  if os.path.lexists(log) and not os.path.isfile(log):
    fail(f"LOG exists and is not a regular file: {log}")
  if mode == "ro":
    if not in_git_tree(target):
      fail(f"ro needs a git checkout: {target}")
    if not under(brief, tmp):
      fail(f"BRIEF must be under {tmp}: {brief}")
    flags = ["--sandbox", "read-only"]
  else:
    if not under(target, tmp) or target == tmp:
      fail(f"net REVIEW_DIR must be a directory under {tmp}: {target}")
    if in_git_tree(target):
      fail(f"net REVIEW_DIR may not be inside a git work tree: {target}")
    if not under(brief, target):
      fail(f"net BRIEF must be inside REVIEW_DIR: {brief}")
    flags = [
        "--sandbox", "workspace-write",
        "-c", "sandbox_workspace_write.network_access=true",
        "--skip-git-repo-check",
    ]
  return ["codex", "exec", *flags, "--cd", target, PROMPT.format(brief=brief)], log


def main(argv):
  dry = "--dry-run" in argv
  args = [a for a in argv if a != "--dry-run"]
  if len(args) != 4 or args[0] not in ("ro", "net"):
    fail("usage: codex-review.py ro|net TARGET BRIEF LOG [--dry-run]")
  cmd, log = build(*args)
  if dry:
    print(cmd)
    return 0
  if shutil.which("codex") is None:
    print("codex-review: codex is not installed", file=sys.stderr)
    return 3
  with open(log, "w", encoding="utf-8") as out:
    proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                          check=False)
  return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
