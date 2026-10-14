# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for utilities/patch-gate.py."""

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                      "patch-gate.py")


def load():
  spec = importlib.util.spec_from_file_location("patch_gate", SCRIPT)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class PatchGateTest(unittest.TestCase):

  def setUp(self):
    self.mod = load()
    self.tmp = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
    self.tree = os.path.join(self.tmp, "tree")
    os.mkdir(self.tree)
    self.git("init", "-q")
    self.put("utilities/check-open-side.py", "x = 1\n")
    self.put("README.md", "readme\n")
    self.git("add", ".")
    self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "i")
    self.patch = self.write("p.patch", self.new_file_patch("x.py", "print('hi')"))
    self.refused = self.write("none.txt", "refused: 0\n")

  @staticmethod
  def new_file_patch(name, line):
    return (f"diff --git a/{name} b/{name}\nnew file mode 100644\n--- /dev/null\n"
            f"+++ b/{name}\n@@ -0,0 +1 @@\n+{line}\n")

  def git(self, *args):
    subprocess.run(["git", "-C", self.tree, *args], check=True, capture_output=True)

  def put(self, name, data):
    path = os.path.join(self.tree, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w") as f:
      f.write(data)

  def write(self, name, text):
    path = os.path.join(self.tmp, name)
    with open(path, "w", encoding="utf-8") as f:
      f.write(text)
    return path

  def gate(self, *extra):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
      code = self.mod.main([self.patch, self.tree, "--refused", self.refused,
                            "--no-default-suites", *extra])
    return code, out.getvalue()

  def test_risky_hits_only_added_lines(self):
    text = "+++ b/https://x\n-import subprocess\n context eval(\n+x = eval(y)\n+safe\n"
    self.assertEqual(self.mod.risky_hits(text), [(4, "+x = eval(y)")])

  def test_refused_count(self):
    self.assertEqual(self.mod.refused_count("refused: 0\n"), 0)
    self.assertEqual(self.mod.refused_count(""), 0)
    self.assertEqual(self.mod.refused_count(".claude/settings.json\nx/.git\n"), 2)

  def test_summary_prefers_unittest_lines(self):
    out = "....\n----\nRan 12 tests in 0.1s\n\nOK (skipped=1)\n"
    self.assertEqual(self.mod.summary(out), "Ran 12 tests in 0.1s; OK (skipped=1)")
    self.assertEqual(self.mod.summary("x\nOK: 5 files\n"), "OK: 5 files")

  def test_clean_patch_passes(self):
    code, out = self.gate("--suite", f"ok={sys.executable} -c pass")
    self.assertEqual(code, 0, out)
    self.assertIn("pattern hits (advisory): 0", out)
    self.assertIn("ok   ok (exit 0)", out)
    self.assertTrue(out.endswith("gate: pass\n"), out)

  def test_failing_suite_fails_and_shows_error_lines(self):
    script = self.write("bad.py", "import sys\nprint('FAIL: test_x')\nsys.exit(1)\n")
    code, out = self.gate("--suite", f"bad={sys.executable} {script}")
    self.assertEqual(code, 1)
    self.assertIn("FAIL bad (exit 1)", out)
    self.assertIn("  FAIL: test_x", out)
    self.assertTrue(out.endswith("gate: FAIL\n"), out)

  def test_refused_path_fails(self):
    self.refused = self.write("r.txt", ".claude/settings.json\n")
    code, out = self.gate()
    self.assertEqual(code, 1)
    self.assertIn("refused: 1", out)

  def test_pattern_hits_reported_but_do_not_fail(self):
    self.patch = self.write("p.patch", self.new_file_patch("x.py", "import subprocess"))
    code, out = self.gate()
    self.assertEqual(code, 0, out)
    self.assertIn("patch:6: +import subprocess", out)

  def test_untracked_home_path_fails(self):
    home = "/" + "home" + "/someone/x"
    with open(os.path.join(self.tree, "new.txt"), "w", encoding="utf-8") as f:
      f.write(home)
    code, out = self.gate()
    self.assertEqual(code, 1)
    self.assertIn("new files with home paths: new.txt", out)
    self.assertIn("FAIL privacy (trusted copy): 3 files, 1 home path(s)", out)

  def test_untracked_file_reaches_trusted_privacy_check(self):
    # The trusted check scans new untracked files that `git ls-files` alone would miss.
    count, home, terms = self.mod.trusted_checks(self.tree, [])
    self.assertEqual((count, home, terms), (2, [], []))
    with open(os.path.join(self.tree, "n.md"), "w", encoding="utf-8") as f:
      f.write("see /" + "Users/someone/notes\n")
    count, home, _ = self.mod.trusted_checks(self.tree, ["n.md"])
    self.assertEqual(count, 3)
    self.assertEqual(len(home), 1)

  def test_unreadable_untracked_file_fails(self):
    os.symlink("/nonexistent", os.path.join(self.tree, "link"))
    code, out = self.gate()
    self.assertEqual(code, 1)
    self.assertIn("NOT scanned: link", out)

  def test_changed_gate_input_fails_whatever_the_patch_says(self):
    # The patch text names nothing; the worktree is what counts.
    self.put("utilities/check-open-side.py", "x = 2\n")
    code, out = self.gate()
    self.assertEqual(code, 1)
    self.assertIn("gate inputs touched: utilities/check-open-side.py", out)

  def test_new_and_renamed_gate_inputs_fail(self):
    os.makedirs(os.path.join(self.tree, "skills/spec-format"))
    self.git("mv", "README.md", "skills/spec-format/requirements.txt")
    self.put(".github/workflows/checks.yml", "on: push\n")
    code, out = self.gate()
    self.assertEqual(code, 1)
    self.assertIn(".github/workflows/checks.yml, skills/spec-format/requirements.txt", out)

  def test_binary_change_fails(self):
    self.put("README.md", b"\x00\x01binary")
    code, out = self.gate()
    self.assertEqual(code, 1)
    self.assertIn("binary: README.md", out)

  def test_suite_that_changes_worktree_fails(self):
    script = self.write("edit.py", "open('README.md', 'a').write('later\\n')\n")
    code, out = self.gate("--suite", f"edit={sys.executable} {script}")
    self.assertEqual(code, 1)
    self.assertIn("FAIL worktree changed while the suites ran", out)

  def git_suite(self, name, *commands):
    """A --suite that runs each git COMMAND (an argument list) in the worktree."""
    script = self.write(name + ".py", "import subprocess\n" + "".join(
        f"subprocess.run({['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *c]!r}"
        ", check=True)\n" for c in commands))
    return f"{name}={sys.executable} {script}"

  def test_suite_that_stages_then_restores_fails(self):
    # Issue 79: a staged change with the file restored on disk left `git diff HEAD` unchanged,
    # and the orchestrator's next commit would have carried the staged content.
    self.put("README.md", "readme\nstaged\n")
    self.git("add", "README.md")
    self.git("restore", "--staged", "README.md")
    self.put("README.md", "readme\n")
    script = self.write("stage.py",
                        "import subprocess\nopen('README.md', 'a').write('leak\\n')\n"
                        "subprocess.run(['git', 'add', 'README.md'], check=True)\n"
                        "open('README.md', 'w').write('readme\\n')\n")
    code, out = self.gate("--suite", f"stage={sys.executable} {script}")
    self.assertEqual(code, 1, out)
    self.assertIn("FAIL worktree changed while the suites ran", out)

  def test_suite_that_changes_git_state_fails(self):
    hook = os.path.join(self.tree, ".git", "hooks", "pre-commit")
    cases = {
        "commit": self.git_suite("commit", ["commit", "-q", "--allow-empty", "-m", "x"]),
        "flag": self.git_suite("flag", ["update-index", "--assume-unchanged", "README.md"]),
        "hook": f"hook={sys.executable} " + self.write("hook.py", f"open({hook!r}, 'w').close()\n"),
        "config": self.git_suite("config", ["config", "user.email", "x@example.invalid"]),
        "hooks-path": self.git_suite("hooks-path", ["config", "core.hooksPath", "elsewhere"]),
        "exclude": f"exclude={sys.executable} " + self.write(
            "exclude.py", f"open({os.path.join(self.tree, '.git', 'info', 'exclude')!r}, 'a')"
            ".write('*.md\\n')\n"),
        "merge-head": f"merge={sys.executable} " + self.write(
            "merge.py", "import subprocess\nhead = subprocess.run(['git', 'rev-parse', 'HEAD'], "
            "capture_output=True, text=True).stdout\n"
            f"open({os.path.join(self.tree, '.git', 'MERGE_HEAD')!r}, 'w').write(head)\n"),
        "branch": self.git_suite("branch", ["branch", "other"], ["symbolic-ref", "HEAD", "refs/heads/other"]),
    }
    for name, suite in cases.items():
      with self.subTest(case=name):
        code, out = self.gate("--suite", suite)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL worktree changed while the suites ran", out)

  def test_non_utf8_or_symlinked_tracked_file_fails(self):
    # Issue 79: git calls a file text unless it holds a NUL; the scans skipped non-UTF-8 files.
    home = "/" + "home/someone/x\n"
    self.put("README.md", home.encode() + b"\xff\n")
    code, out = self.gate()
    self.assertEqual(code, 1, out)
    self.assertIn("binary: none", out)
    self.assertIn("unscannable (link, directory, not UTF-8 or skipped suffix): README.md;", out)
    os.remove(os.path.join(self.tree, "README.md"))
    target = self.write("target.txt", home)  # an existing target: the scan would follow it
    os.symlink(target, os.path.join(self.tree, "README.md"))
    code, out = self.gate()
    self.assertEqual(code, 1, out)
    self.assertIn("unscannable (link, directory, not UTF-8 or skipped suffix): README.md;", out)

  def test_text_file_with_a_skipped_suffix_fails(self):
    self.put("notes.pdf", "/" + "home/someone/x\n")
    code, out = self.gate()
    self.assertEqual(code, 1, out)
    self.assertIn("unscannable (link, directory, not UTF-8 or skipped suffix): notes.pdf;", out)

  def test_suite_that_forges_the_index_tree_cache_fails(self):
    # Issue 79 review: `git commit` reuses the index's cached tree for a directory the next
    # `git add` does not touch, so a forged cache entry commits files `ls-files` never lists.
    forge = self.write("forge.py", """import hashlib, os, shutil, subprocess
def g(*a, env=None, inp=None):
  return subprocess.run(["git", *a], check=True, capture_output=True, env=env,
                        input=inp).stdout.decode().strip()
gitdir = g("rev-parse", "--absolute-git-dir")
idx = os.path.join(gitdir, "index")
g("write-tree")
old = bytes.fromhex(g("rev-parse", "HEAD:utilities"))
tmp = os.path.join(gitdir, "tmp-idx")
shutil.copy(idx, tmp)
env = dict(os.environ, GIT_INDEX_FILE=tmp)
blob = g("hash-object", "-w", "--stdin", inp=b"leak\\n")
g("update-index", "--add", "--cacheinfo", "100644," + blob + ",utilities/leak.md", env=env)
new = bytes.fromhex(g("rev-parse", g("write-tree", env=env) + ":utilities"))
os.remove(tmp)
data = open(idx, "rb").read()[:-20]
i = data.index(b"utilities\\0", data.index(b"TREE", 12))
j = data.index(b"\\n", i) + 1
assert data[j:j + 20] == old
data = data[:j] + new + data[j + 20:]
open(idx, "wb").write(data + hashlib.sha1(data).digest())
""")
    code, out = self.gate("--suite", f"forge={sys.executable} {forge}")
    self.assertEqual(code, 1, out)
    self.assertIn("FAIL worktree changed while the suites ran", out)
    listed = subprocess.run(["git", "-C", self.tree, "ls-files"], capture_output=True,
                            text=True, check=True).stdout
    self.assertNotIn("leak.md", listed)  # the forgery is invisible to ls-files

  def test_deleted_file_is_not_unscannable(self):
    os.remove(os.path.join(self.tree, "README.md"))
    code, out = self.gate()
    self.assertEqual(code, 0, out)
    self.assertIn("unscannable (link, directory, not UTF-8 or skipped suffix): none;", out)

  def test_patch_path_hidden_by_ignore_rules_fails(self):
    # Issue 80: a file under a path the base tree already ignores never reached the scans.
    self.put(".gitignore", "*.swp\n")
    self.put("kept.swp", "tracked\n")
    self.git("add", "-f", ".gitignore", "kept.swp")
    self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "ig")
    self.put("notes.swp", "/" + "home/someone/x\n")
    self.put("tab\tname.swp", "x\n")  # a tab in the path must survive numstat parsing
    self.patch = self.write("p.patch", self.new_file_patch("notes.swp", "x")
                            + 'diff --git "a/tab\\tname.swp" "b/tab\\tname.swp"\nnew file mode 100644\n'
                            '--- /dev/null\n+++ "b/tab\\tname.swp"\n@@ -0,0 +1 @@\n+x\n'
                            + "diff --git a/kept.swp b/kept.swp\n--- a/kept.swp\n+++ b/kept.swp\n"
                            "@@ -1 +1 @@\n-tracked\n+changed\n")
    self.put("kept.swp", "changed\n")
    code, out = self.gate()
    self.assertEqual(code, 1, out)
    self.assertIn("changed: 1 tracked, 0 new", out)
    self.assertIn("ignored by the worktree: notes.swp, tab\tname.swp\n", out)

  def test_suite_that_only_touches_a_tracked_file_passes(self):
    # Review round 2: a stat-only change made the gate's own `git diff` rewrite the index.
    self.put("README.md", "readme\nchanged\n")
    # An unchanged tracked file whose timestamp moves is what makes `git diff` refresh.
    script = self.write("touch.py", "import os, time\nt = time.time() + 5\n"
                        "os.utime('utilities/check-open-side.py', (t, t))\n")
    code, out = self.gate("--suite", f"touch={sys.executable} {script}")
    self.assertEqual(code, 0, out)

  def test_patch_git_cannot_parse_fails(self):
    self.patch = self.write("p.patch", "+++ b/x.py\n+print('hi')\n")
    code, out = self.gate()
    self.assertEqual(code, 1, out)
    self.assertIn("FAIL worktree state: git apply failed", out)

  def test_git_metadata_files_and_odd_paths_are_gate_inputs(self):
    for path in (".gitignore", "docs/.gitignore", ".gitattributes", ".gitmodules",
                 "utilities/patch-gate.py\n", "a\nb.md"):
      with self.subTest(path=path):
        self.assertEqual(self.mod.touched_gate_inputs([path]), [path])

  def test_codex_wrappers_are_gate_inputs(self):
    # SF2-G review A-F1: a patch could widen Codex's own sandbox in codex-implement.py.
    for path in ("utilities/codex-implement.py", "utilities/codex-review.py"):
      with self.subTest(path=path):
        self.assertEqual(self.mod.touched_gate_inputs([path]), [path])
    self.put("utilities/codex-implement.py", "x = 2\n")
    code, out = self.gate()
    self.assertEqual(code, 1)
    self.assertIn("gate inputs touched: utilities/codex-implement.py", out)

  def test_new_gitignore_hiding_a_file_fails(self):
    self.put(".gitignore", "hidden.txt\n")
    self.put("hidden.txt", "/" + "home/someone/x\n")
    code, out = self.gate()
    self.assertEqual(code, 1)
    self.assertIn("gate inputs touched: .gitignore", out)

  def test_background_child_is_killed_with_its_suite(self):
    marker = os.path.join(self.tmp, "late")
    child = self.write("child.py", f"import time\ntime.sleep(1)\nopen({marker!r}, 'w').write('x')\n")
    script = self.write("bg.py", f"import subprocess, sys\nsubprocess.Popen([sys.executable, {child!r}])\n")
    code, out = self.gate("--suite", f"bg={sys.executable} {script}")
    self.assertEqual(code, 0, out)
    import time  # pylint: disable=import-outside-toplevel
    time.sleep(1.5)
    self.assertFalse(os.path.exists(marker))

  def plant(self, module):
    """A top-level MODULE.py in the worktree that leaves a marker outside it if imported."""
    marker = os.path.join(self.tmp, module + ".ran")
    self.put(module + ".py", f"open({marker!r}, 'w').close()\n")
    return marker

  def test_planted_venv_module_cannot_replace_the_venv_build(self):
    # Issue 78: `python -m venv` run from WORKTREE imported a patch's own venv.py, so a stub
    # could skip the --require-hashes install and the gate still passed.
    marker = self.plant("venv")
    real_run, commands = self.mod.run, []
    def record(command, cwd):
      commands.append(command)
      return real_run(command, cwd) if "venv" in command else (0, "")
    self.mod.run = record
    code, output = self.mod.build_venv(self.tree)
    self.assertEqual(code, 0, output)
    self.assertFalse(os.path.exists(marker), "the planted venv.py ran")
    self.assertTrue(os.path.exists(os.path.join(self.tree, ".venv-sf2", "pyvenv.cfg")))
    self.assertEqual(commands[0][1:4], ["-I", "-m", "venv"])

  def test_planted_unittest_module_cannot_replace_a_default_suite(self):
    marker = self.plant("unittest")
    self.put("utilities/tests/test_ok.py",
             "import unittest\nclass T(unittest.TestCase):\n  def test_ok(self):\n    pass\n")
    suites = dict(self.mod.default_suites())
    for name, command in suites.items():
      with self.subTest(suite=name):
        self.assertEqual(command[1:3], ["-I", "-m"])
    code, output = self.mod.run(suites["utilities"], self.tree)
    self.assertEqual(code, 0, output)
    self.assertIn("Ran 1 test", output)
    self.assertFalse(os.path.exists(marker), "the planted unittest.py ran")

  def test_other_paths_are_not_gate_inputs(self):
    self.assertEqual(self.mod.touched_gate_inputs(["utilities/run-store.py", "a.md"]), [])

  def test_refuses_to_run_from_inside_worktree(self):
    repo = os.path.dirname(self.mod.HERE)
    with self.assertRaises(SystemExit) as raised, \
         contextlib.redirect_stderr(io.StringIO()):
      self.mod.main([self.patch, repo, "--refused", self.refused, "--no-default-suites"])
    self.assertEqual(raised.exception.code, 2)

  def test_refused_list_is_required(self):
    with self.assertRaises(SystemExit) as raised, \
         contextlib.redirect_stderr(io.StringIO()):
      self.mod.main([self.patch, self.tree, "--no-default-suites"])
    self.assertEqual(raised.exception.code, 2)

  def test_bad_suite_argument_is_usage_error(self):
    with self.assertRaises(SystemExit) as raised, \
         contextlib.redirect_stderr(io.StringIO()):
      self.mod.main([self.patch, self.tree, "--refused", self.refused, "--suite", "nocommand"])
    self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
  unittest.main()
