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
  - which paths changed comes from WORKTREE itself (`git diff HEAD` and the untracked files),
    never from parsing PATCH, so renames, quoted names, binary and mode-only changes count
    (PATCH's own paths, read with git's parser, are used only to find ignored ones, below);
  - a change to a gate input (the check scripts, this script, the Codex wrappers
    codex-implement.py and codex-review.py, the pinned requirements, CI workflows) fails the gate, so the orchestrator reads that change first, and so does a
    binary change, which no scan here can read;
  - every scan runs before any patched code. The suites run last, each in its own process
    group that is killed when it returns, and the gate fails if WORKTREE's changes differ
    afterwards, so patched code cannot hide or alter what was scanned;
  - `.gitignore`, `.gitattributes` and `.gitmodules` are gate inputs too: they decide what git
    reports as changed and how it diffs it. A changed path holding a control character fails;
  - the after-suite digest also covers HEAD and its branch, the raw index, the git hooks,
    config and info/ files, and any merge, cherry-pick, revert or rebase state, so that a
    suite's staging, committing, hooks or pending merges change the digest. The gate's own
    diffs read a copy of the index, so only a suite can change it; one that runs `git status`
    or `git add` in WORKTREE refreshes the index and fails the gate too;
  - a changed or new path that is a symlink, a directory, not valid UTF-8, or has a suffix the
    scans skip fails: the scans would pass over it, while git may still commit it as text;
  - a path the patch adds or changes that the worktree's ignore rules hide (so the untracked
    scan never sees it) fails; its paths come from `git apply --numstat`, git's own parser.
Limits. A process that leaves its group (a second setsid) can still outlive the gate; the
orchestrator should recheck the worktree just before committing. The hooks and config are
shared by every worktree of the checkout, so another session changing them during a run (a
`git worktree add`, a `push -u`) fails that run. State outside the repository (global git
config, the home directory) is not covered.
This gate is a check on the patch, not a sandbox: Codex's own containment is codex-implement.
The test suites necessarily run the patched code; whether its tests still mean anything is a
review question, not one this gate can answer. Every interpreter the gate starts runs with
`-I`, so a module the patch adds at WORKTREE's top level (a `venv.py` or `unittest.py`) cannot
stand in for the standard library's and fake the venv build or a suite's runner (#78). Extra
--suite commands that start Python should pass `-I` too.

Exit status: 0 every check passed and nothing was refused; 1 a check failed, a file was refused,
or a new untracked file holds a home directory path; 2 usage error.
"""

import argparse
import hashlib
import importlib.util
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

RISKY = re.compile(
    r"subprocess|os\.system|eval\(|exec\(|shell=True|socket|urllib|requests\.|http://|"
    r"https://|/home/|/Users/|~/|\.ssh|\.claude|\.codex|\.config|AGENTS\.md|CLAUDE\.md",
    re.IGNORECASE)
HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9_]")
ERROR_LINE = re.compile(r"^(FAIL|ERROR):|Error\b|error:")
HERE = os.path.dirname(os.path.realpath(__file__))
# Paths whose change can weaken the gate itself: the checks, the Codex wrappers (Codex's own
# containment; SF2-G review A-F1), the pinned requirements, CI, and the files that decide what
# git reports as changed or how it diffs it.
GATE_INPUTS = re.compile(
    r"utilities/(check-[^/]*|patch-gate|codex-implement|codex-review)\.py|"
    r"skills/spec-format/requirements\.txt|"
    r"\.github/.*|(.*/)?\.git(ignore|attributes|modules)", re.DOTALL)
# A changed path holding a control character is refused outright rather than matched.
ODD_PATH = re.compile(r"[\x00-\x1f\x7f]")
MAX_ERROR_LINES = 3
MAX_UNTRACKED_BYTES = 1 << 20


def default_suites():
  python = sys.executable
  return [
      ("spec-format", [os.path.join(".venv-sf2", "bin", "python"), "-I", "-m", "unittest",
                       "discover", "-s", "skills/spec-format/tests"]),
      ("utilities", [python, "-I", "-m", "unittest", "discover", "-s", "utilities/tests"]),
  ]


def risky_hits(patch_text):
  """(patch line number, line) for each added line that matches a risky pattern."""
  hits = []
  for number, line in enumerate(patch_text.splitlines(), 1):
    if line.startswith("+") and not line.startswith("+++") and RISKY.search(line):
      hits.append((number, line))
  return hits


GIT = ["git", "-c", "core.fsmonitor=false", "--no-pager"]


def git(worktree, *args, private_index=False):
  """Run git in WORKTREE without external diff drivers or text conversion.

  With PRIVATE_INDEX the command reads a copy of WORKTREE's index, so a `git diff` that
  refreshes stat data writes the copy, never the real index the digest hashes (#79).
  """
  if not private_index:
    return run_git([*GIT, "-C", worktree, *args], args, None)
  index = run_git([*GIT, "-C", worktree, "rev-parse", "--git-path", "index"], ("rev-parse",),
                  None).decode("utf-8", "surrogateescape").rstrip("\n")
  with tempfile.TemporaryDirectory(prefix="patch-gate-") as tmp:
    copy = os.path.join(tmp, "index")
    if os.path.exists(os.path.join(worktree, index)):
      shutil.copyfile(os.path.join(worktree, index), copy)
    return run_git([*GIT, "-C", worktree, *args], args, {**os.environ, "GIT_INDEX_FILE": copy})


def run_git(command, args, env):
  proc = subprocess.run(command, capture_output=True, check=False, env=env)
  if proc.returncode != 0:
    raise RuntimeError(f"git {args[0]} failed: "
                       f"{summary(proc.stderr.decode('utf-8', 'replace'))}")
  return proc.stdout


def worktree_changes(worktree):
  """(changed tracked paths, binary paths, untracked paths) as WORKTREE holds them."""
  changed = [p for p in git(worktree, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z",
                           "HEAD", private_index=True)
             .decode("utf-8", "surrogateescape").split("\0") if p]
  binary = []
  for row in git(worktree, "diff", "--no-ext-diff", "--no-renames", "--no-textconv", "--numstat", "-z",
                 "HEAD", private_index=True)\
      .decode("utf-8", "surrogateescape").split("\0"):
    added, _, rest = row.partition("\t")
    if added == "-":
      binary.append(rest.partition("\t")[2])
  untracked = [p for p in git(worktree, "ls-files", "--others", "--exclude-standard", "-z")
               .decode("utf-8", "surrogateescape").split("\0") if p]
  return changed, binary, untracked


# Git state outside the working files that a suite could change to alter what gets committed:
# the index, hashed raw because `git commit` reuses its cache of directory trees, which
# `ls-files` does not show (a forged entry commits files nothing lists); the hooks; the
# repository and per-worktree config; info/ (exclude, attributes); and the merge,
# cherry-pick, revert and rebase state a plain `git commit` would pick up (a written
# MERGE_HEAD turns the next commit into a merge with an unscanned parent).
GIT_STATE_PATHS = ("index", "config", "config.worktree", "hooks", "info", "MERGE_HEAD",
                   "MERGE_MSG", "MERGE_MODE", "AUTO_MERGE", "CHERRY_PICK_HEAD", "REVERT_HEAD",
                   "SQUASH_MSG", "sequencer", "rebase-merge", "rebase-apply")


def git_state_files(worktree):
  """(label, path) for each file under WORKTREE's GIT_STATE_PATHS, in a stable order."""
  files = []
  for name in GIT_STATE_PATHS:
    top = git(worktree, "rev-parse", "--git-path", name).decode("utf-8", "surrogateescape")
    top = os.path.join(worktree, top.rstrip("\n"))
    if not os.path.isdir(top) or os.path.islink(top):
      files.append((name, top))
      continue
    for root, dirs, names in os.walk(top):
      dirs.sort()
      for leaf in sorted(names):
        path = os.path.join(root, leaf)
        files.append((name + "/" + os.path.relpath(path, top), path))
  return files


def hash_file(digest, name, path):
  digest.update(name.encode("utf-8", "surrogateescape") + b"\0")
  try:
    if os.path.islink(path):
      digest.update(b"link:" + os.readlink(path).encode("utf-8", "surrogateescape"))
    elif not os.path.lexists(path):
      digest.update(b"absent")
    else:
      with open(path, "rb") as f:
        digest.update(f.read())
  except OSError as exc:
    digest.update(f"unreadable:{exc.errno}".encode())
  digest.update(b"\0")


def worktree_digest(worktree):
  """A digest of what WORKTREE would commit: HEAD and its branch, the tracked changes and
  untracked files, bytes included, and the git state in GIT_STATE_PATHS (#79)."""
  digest = hashlib.sha256(git(worktree, "rev-parse", "--verify", "HEAD"))
  digest.update(b"branch:" + git(worktree, "rev-parse", "--symbolic-full-name", "HEAD"))
  digest.update(git(worktree, "diff", "--no-ext-diff", "--no-renames", "--no-textconv", "--binary",
                    "HEAD", private_index=True))
  for name, path in git_state_files(worktree):
    hash_file(digest, "git:" + name, path)
  for name in sorted(worktree_changes(worktree)[2]):
    hash_file(digest, name, os.path.join(worktree, name))
  return digest.hexdigest()


def unscannable(worktree, paths):
  """PATHS the text scans would skip: symlinks, directories, files that are not UTF-8, and
  files with a suffix the scans pass over as binary (`.pdf`, `.zip` and the like).

  The privacy and open-side scans read files as UTF-8 and pass over any that fail to decode,
  while git calls a file text unless it holds a NUL byte, so one stray byte would carry a file
  past both scans as text (#79). A path no longer present (a deletion) is not reported.
  """
  skipped = tuple(load_check("check-no-private-paths").SKIP_SUFFIXES
                  + load_check("check-open-side").SKIP_SUFFIXES)
  found = []
  for name in sorted(set(paths)):
    path = os.path.join(worktree, name)
    if not os.path.lexists(path):
      continue
    if os.path.islink(path) or not os.path.isfile(path) or name.endswith(skipped):
      found.append(name)
      continue
    try:
      with open(path, "rb") as f:
        f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
      found.append(name)
  return found


def ignored_patch_paths(worktree, patch):
  """Paths PATCH adds or changes that WORKTREE's ignore rules hide from the untracked scan.

  Paths come from git's own patch parser (`git apply --numstat`); `git check-ignore` reports
  only untracked paths, so a tracked file matching an ignore pattern is not counted (#80).
  """
  rows = git(worktree, "apply", "--numstat", "-z", patch).decode("utf-8", "surrogateescape")
  # Each row is "added<TAB>deleted<TAB>path"; for a rename git apply prints the new path only.
  paths = [row.split("\t", 2)[2] for row in rows.split("\0") if row.count("\t") >= 2]
  paths = [p for p in paths if p]
  if not paths:
    return []
  proc = subprocess.run([*GIT, "-C", worktree, "check-ignore", "-z", "--stdin"],
                        input="\0".join(paths).encode("utf-8", "surrogateescape"),
                        capture_output=True, check=False)
  if proc.returncode not in (0, 1):
    raise RuntimeError(f"git check-ignore failed: "
                       f"{summary(proc.stderr.decode('utf-8', 'replace'))}")
  return sorted(p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p)


def touched_gate_inputs(paths):
  """The gate inputs among PATHS."""
  return sorted(p for p in set(paths) if GATE_INPUTS.fullmatch(p) or ODD_PATH.search(p))


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
  """Run COMMAND in its own process group; kill whatever of the group outlives it.

  Output goes to a temporary file, not a pipe, so a background child that inherits it cannot
  hold the gate open until it finishes.
  """
  with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as out:
    try:
      proc = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out,
                              stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as exc:
      return 127, str(exc)
    try:
      proc.wait()
    finally:
      try:
        os.killpg(proc.pid, signal.SIGKILL)
      except (ProcessLookupError, PermissionError):
        pass
      proc.wait()
    out.seek(0)
    return proc.returncode, out.read()


def build_venv(worktree):
  venv = os.path.join(worktree, ".venv-sf2")
  shutil.rmtree(venv, ignore_errors=True)
  code, output = run([sys.executable, "-I", "-m", "venv", ".venv-sf2"], worktree)
  if code == 0:
    code, output = run([os.path.join(".venv-sf2", "bin", "pip"), "install", "-q",
                        "--require-hashes", "-r", "skills/spec-format/requirements.txt"],
                       worktree)
  return code, output


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
  print(f"pattern hits (advisory): {len(hits)}")
  for number, line in hits:
    print(f"  patch:{number}: {line}")

  # Every scan runs before any patched code does.
  try:
    changed, binary, names = worktree_changes(worktree)
    odd = unscannable(worktree, changed + names)
    ignored = ignored_patch_paths(worktree, os.path.abspath(args.patch))
    before = worktree_digest(worktree)
  except RuntimeError as exc:
    print(f"FAIL worktree state: {exc}")
    print("gate: FAIL")
    return 1
  inputs = touched_gate_inputs(changed + names)
  failed |= bool(inputs or binary)
  print(f"changed: {len(changed)} tracked, {len(names)} new; gate inputs touched: "
        f"{', '.join(inputs) or 'none'}; binary: {', '.join(binary) or 'none'}")
  failed |= bool(odd or ignored)
  print(f"unscannable (link, directory, not UTF-8 or skipped suffix): {', '.join(odd) or 'none'}; "
        f"ignored by the worktree: {', '.join(ignored) or 'none'}")
  flagged, unscanned = untracked_home_paths(worktree, names)
  failed |= bool(flagged or unscanned)
  print(f"new files with home paths: {', '.join(flagged) or 'none'}"
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

  # Patched code runs from here on.
  suites = [] if args.no_default_suites else default_suites()
  suites += args.suite
  if not args.reuse_venv and any(name == "spec-format" for name, _ in suites):
    code, output = build_venv(worktree)
    if code:
      failed = True
      print(f"FAIL venv (exit {code}): {summary(output)}")
  for name, command in suites:
    code, output = run(command, worktree)
    print(f"{'ok  ' if code == 0 else 'FAIL'} {name} (exit {code}): {summary(output)}")
    if code:
      failed = True
      errors = [line for line in output.splitlines() if ERROR_LINE.search(line)]
      for line in errors[:MAX_ERROR_LINES]:
        print(f"  {line}")
  try:
    after = worktree_digest(worktree)
  except RuntimeError as exc:
    after = f"unreadable: {exc}"
  if after != before:
    failed = True
    print("FAIL worktree changed while the suites ran; the scans above no longer describe it")
  print(f"gate: {'FAIL' if failed else 'pass'}")
  return 1 if failed else 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
