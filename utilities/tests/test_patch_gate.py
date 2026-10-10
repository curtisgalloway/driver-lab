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
    self.patch = self.write("p.patch", "+++ b/x.py\n+print('hi')\n")
    self.refused = self.write("none.txt", "refused: 0\n")

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
    self.patch = self.write("p.patch", "+++ b/x.py\n+import subprocess\n")
    code, out = self.gate()
    self.assertEqual(code, 0, out)
    self.assertIn("patch:2: +import subprocess", out)

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
