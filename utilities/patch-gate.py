# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Check an applied Codex patch in one run and print a short report.

Usage:
  python3 <main checkout>/utilities/patch-gate.py PATCH WORKTREE --refused FILE [--reuse-venv]
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

Trust. The patch may have changed anything in WORKTREE, including the checks themselves. So:
  - this script must not live inside WORKTREE (run it from the main checkout);
  - the privacy and open-side checks run from this script's own directory, over WORKTREE's
    tracked files plus the new untracked ones the patch added (git apply leaves them
    untracked, and `git ls-files` alone would never see them);
  - a patch that touches a gate input (the check scripts, this script, the pinned
    requirements, CI workflows) fails the gate, so the orchestrator reads that change first.
The test suites necessarily run the patched code; whether its tests still mean anything is a
review question, not one this gate can answer.

Exit status: 0 every check passed and nothing was refused; 1 a check failed, a file was refused,
or a new untracked file holds a home directory path; 2 usage error.
"""

import argparse
import importlib.util
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
HERE = os.path.dirname(os.path.realpath(__file__))
GATE_INPUTS = re.compile(
    r"^(utilities/(check-[^/]*|patch-gate)\.py|skills/spec-format/requirements\.txt|"
    r"\.github/.*)$")
PATCH_PATH = re.compile(r"^(?:\+\+\+|---) (?:[ab]/)?(\S+)")
MAX_ERROR_LINES = 3
MAX_UNTRACKED_BYTES = 1 << 20


def default_suites():
  python = sys.executable
  return [
      ("spec-format", [os.path.join(".venv-sf2", "bin", "python"), "-m", "unittest",
                       "discover", "-s", "skills/spec-format/tests"]),
      ("utilities", [python, "-m", "unittest", "discover", "-s", "utilities/tests"]),
  ]


def risky_hits(patch_text):
  """(patch line number, line) for each added line that matches a risky pattern."""
  hits = []
  for number, line in enumerate(patch_text.splitlines(), 1):
    if line.startswith("+") and not line.startswith("+++") and RISKY.search(line):
      hits.append((number, line))
  return hits


def touched_gate_inputs(patch_text):
  """Gate-input paths the patch adds, deletes or changes."""
  paths = {m.group(1) for line in patch_text.splitlines() if (m := PATCH_PATH.match(line))}
  return sorted(p for p in paths if p != "/dev/null" and GATE_INPUTS.match(p))


def load_check(name):
  spec = importlib.util.spec_from_file_location(name.replace("-", "_"),
                                                os.path.join(HERE, name + ".py"))
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def trusted_checks(worktree, untracked):
  """Run this checkout's privacy and open-side scans over WORKTREE's tracked and new files."""
  privacy, open_side = load_check("check-no-private-paths"), load_check("check-open-side")
  tracked = open_side.tracked_files(worktree)
  paths = sorted(set(tracked) | set(untracked))
  home = privacy.scan([os.path.join(worktree, p) for p in paths
                       if not p.endswith(privacy.SKIP_SUFFIXES)])
  terms = open_side.scan(worktree, paths)
  return len(paths), [f"{os.path.relpath(p, worktree)}:{n}: {hit}" for p, n, hit in home], \
      [f"{p}:{n}: [{name}]" for p, n, name, _ in terms]


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


def untracked_files(worktree):
  code, output = run(["git", "ls-files", "--others", "--exclude-standard", "-z"], worktree)
  if code != 0:
    raise RuntimeError(f"git ls-files failed: {summary(output)}")
  return [name for name in output.split("\0") if name]


def untracked_home_paths(worktree, names):
  """(names holding a home directory path, names this scan could not read)."""
  flagged, unscanned = [], []
  for name in names:
    path = os.path.join(worktree, name)
    try:
      if os.path.islink(path) or os.path.getsize(path) > MAX_UNTRACKED_BYTES:
        unscanned.append(name)
        continue
      with open(path, "rb") as f:
        text = f.read().decode("utf-8", errors="replace")
    except OSError:
      unscanned.append(name)
      continue
    if HOME_PATH.search(text):
      flagged.append(name)
  return flagged, unscanned


def suite_arg(value):
  name, sep, command = value.partition("=")
  if not sep or not name or not command.strip():
    raise argparse.ArgumentTypeError("expected NAME=COMMAND")
  return name, shlex.split(command)


def main(argv):
  parser = argparse.ArgumentParser(prog="patch-gate.py", allow_abbrev=False)
  parser.add_argument("patch")
  parser.add_argument("worktree")
  parser.add_argument("--refused", required=True)
  parser.add_argument("--reuse-venv", action="store_true")
  parser.add_argument("--suite", action="append", default=[], type=suite_arg)
  parser.add_argument("--no-default-suites", action="store_true")
  args = parser.parse_args(argv)
  if not os.path.isdir(args.worktree):
    parser.error(f"not a directory: {args.worktree}")
  worktree = os.path.realpath(args.worktree)
  if os.path.commonpath([worktree, HERE]) == worktree:
    parser.error("run the gate from the main checkout, not from inside WORKTREE")
  try:
    with open(args.patch, encoding="utf-8", errors="replace") as f:
      patch_text = f.read()
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
  inputs = touched_gate_inputs(patch_text)
  failed |= bool(inputs)
  print(f"gate inputs touched: {', '.join(inputs) or 'none'}")

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
    names = untracked_files(args.worktree)
  except RuntimeError as exc:
    failed = True
    print(f"FAIL untracked: {exc}")
  else:
    flagged, unscanned = untracked_home_paths(args.worktree, names)
    failed |= bool(flagged or unscanned)
    print(f"untracked: {len(names)} new file(s), home paths in: {', '.join(flagged) or 'none'}"
          + (f"; NOT scanned: {', '.join(unscanned)}" if unscanned else ""))
    try:
      count, home, terms = trusted_checks(worktree, names)
    except Exception as exc:  # pylint: disable=broad-except
      failed = True
      print(f"FAIL trusted checks: {type(exc).__name__}: {exc}")
    else:
      failed |= bool(home or terms)
      print(f"{'ok  ' if not home else 'FAIL'} privacy (trusted copy): {count} files, "
            f"{len(home)} home path(s)")
      print(f"{'ok  ' if not terms else 'FAIL'} open-side (trusted copy): {count} files, "
            f"{len(terms)} mention(s)")
      for line in (home + terms)[:MAX_ERROR_LINES]:
        print(f"  {line}")
  print(f"gate: {'FAIL' if failed else 'pass'}")
  return 1 if failed else 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
