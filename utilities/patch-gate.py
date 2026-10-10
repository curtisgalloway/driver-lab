# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Check an applied Codex patch in one run and print a short report.

Usage:
  python3 utilities/patch-gate.py PATCH WORKTREE [--refused FILE] [--reuse-venv]
      [--suite NAME=COMMAND]... [--no-default-suites]

The orchestrator runs this itself after `git apply` (AGENTS.md, "Delegation in orchestrated
runs"). It replaces a subagent runner that cost about 71k tokens per patch to run the same
commands, which the orchestrator then reran anyway.

PATCH     The patch codex-implement.py wrote; its added lines are scanned for risky patterns.
WORKTREE  The milestone worktree the patch was applied in; every command runs there.
--refused The `.refused.txt` beside the patch; any refused path fails the gate.
--reuse-venv  Keep WORKTREE/.venv-sf2 instead of rebuilding it with --require-hashes.
--suite   An extra check, NAME=COMMAND (split like a shell, run without one).

Pattern hits are reported verbatim for the orchestrator to judge; they do not fail the gate.

Exit status: 0 every check passed and nothing was refused; 1 a check failed, a file was refused,
or a new untracked file holds a home directory path; 2 usage error.
"""

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys

RISKY = re.compile(
    r"subprocess|os\.system|eval\(|exec\(|shell=True|socket|urllib|requests\.|http://|"
    r"https://|/home/|/Users/|~/|\.ssh|\.claude|\.codex|\.config|AGENTS\.md|CLAUDE\.md",
    re.IGNORECASE)
HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9_]")
ERROR_LINE = re.compile(r"^(FAIL|ERROR):|Error\b|error:")
MAX_ERROR_LINES = 3
MAX_UNTRACKED_BYTES = 1 << 20


def default_suites():
  python = sys.executable
  return [
      ("spec-format", [os.path.join(".venv-sf2", "bin", "python"), "-m", "unittest",
                       "discover", "-s", "skills/spec-format/tests"]),
      ("utilities", [python, "-m", "unittest", "discover", "-s", "utilities/tests"]),
      ("privacy", [python, "utilities/check-no-private-paths.py"]),
      ("open-side", [python, "utilities/check-open-side.py"]),
  ]


def risky_hits(patch_text):
  """(patch line number, line) for each added line that matches a risky pattern."""
  hits = []
  for number, line in enumerate(patch_text.splitlines(), 1):
    if line.startswith("+") and not line.startswith("+++") and RISKY.search(line):
      hits.append((number, line))
  return hits


def refused_count(text):
  """Count refused paths; codex-implement writes 'refused: 0' when there are none."""
  lines = [line for line in text.splitlines() if line.strip()]
  if len(lines) == 1:
    match = re.fullmatch(r"refused:\s*(\d+)", lines[0].strip())
    if match:
      return int(match.group(1))
  return len(lines)


def summary(output):
  """unittest's 'Ran N tests' and verdict lines, else the last non-empty line."""
  lines = [line.rstrip() for line in output.splitlines() if line.strip()]
  ran = [i for i, line in enumerate(lines) if re.match(r"Ran \d+ tests?\b", line)]
  if ran:
    return "; ".join(lines[ran[-1]:ran[-1] + 2])
  return lines[-1] if lines else "(no output)"


def run(command, cwd):
  try:
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
  except OSError as exc:
    return 127, str(exc)
  return proc.returncode, proc.stdout + proc.stderr


def build_venv(worktree):
  venv = os.path.join(worktree, ".venv-sf2")
  shutil.rmtree(venv, ignore_errors=True)
  code, output = run([sys.executable, "-m", "venv", ".venv-sf2"], worktree)
  if code == 0:
    code, output = run([os.path.join(".venv-sf2", "bin", "pip"), "install", "-q",
                        "--require-hashes", "-r", "skills/spec-format/requirements.txt"],
                       worktree)
  return code, output


def untracked_home_paths(worktree):
  """(number of new untracked files, names of those holding a home directory path)."""
  code, output = run(["git", "ls-files", "--others", "--exclude-standard", "-z"], worktree)
  if code != 0:
    raise RuntimeError(f"git ls-files failed: {summary(output)}")
  names = [name for name in output.split("\0") if name]
  flagged = []
  for name in names:
    path = os.path.join(worktree, name)
    try:
      if os.path.islink(path) or os.path.getsize(path) > MAX_UNTRACKED_BYTES:
        continue
      with open(path, "rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    except OSError:
      continue
    if HOME_PATH.search(text):
      flagged.append(name)
  return len(names), flagged


def suite_arg(value):
  name, sep, command = value.partition("=")
  if not sep or not name or not command.strip():
    raise argparse.ArgumentTypeError("expected NAME=COMMAND")
  return name, shlex.split(command)


def main(argv):
  parser = argparse.ArgumentParser(prog="patch-gate.py", allow_abbrev=False)
  parser.add_argument("patch")
  parser.add_argument("worktree")
  parser.add_argument("--refused")
  parser.add_argument("--reuse-venv", action="store_true")
  parser.add_argument("--suite", action="append", default=[], type=suite_arg)
  parser.add_argument("--no-default-suites", action="store_true")
  args = parser.parse_args(argv)
  if not os.path.isdir(args.worktree):
    parser.error(f"not a directory: {args.worktree}")
  try:
    with open(args.patch, encoding="utf-8", errors="replace") as f:
      patch_text = f.read()
    refused_text = ""
    if args.refused:
      with open(args.refused, encoding="utf-8", errors="replace") as f:
        refused_text = f.read()
  except OSError as exc:
    parser.error(str(exc))

  failed = False
  refused = refused_count(refused_text)
  failed |= refused > 0
  print(f"refused: {refused}")
  hits = risky_hits(patch_text)
  print(f"pattern hits: {len(hits)}")
  for number, line in hits:
    print(f"  patch:{number}: {line}")

  suites = [] if args.no_default_suites else default_suites()
  suites += args.suite
  if not args.reuse_venv and any(name == "spec-format" for name, _ in suites):
    code, output = build_venv(args.worktree)
    if code:
      failed = True
      print(f"FAIL venv (exit {code}): {summary(output)}")
  for name, command in suites:
    code, output = run(command, args.worktree)
    print(f"{'ok  ' if code == 0 else 'FAIL'} {name} (exit {code}): {summary(output)}")
    if code:
      failed = True
      errors = [line for line in output.splitlines() if ERROR_LINE.search(line)]
      for line in errors[:MAX_ERROR_LINES]:
        print(f"  {line}")

  try:
    count, flagged = untracked_home_paths(args.worktree)
  except RuntimeError as exc:
    failed = True
    print(f"FAIL untracked: {exc}")
  else:
    failed |= bool(flagged)
    print(f"untracked: {count} new file(s), home paths in: {', '.join(flagged) or 'none'}")
  print(f"gate: {'FAIL' if failed else 'pass'}")
  return 1 if failed else 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
