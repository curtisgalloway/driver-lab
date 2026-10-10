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
    subprocess.run(["git", "init", "-q", self.tree], check=True)
    self.patch = self.write("p.patch", "+++ b/x.py\n+print('hi')\n")

  def write(self, name, text):
    path = os.path.join(self.tmp, name)
    with open(path, "w", encoding="utf-8") as f:
      f.write(text)
    return path

  def gate(self, *extra):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
      code = self.mod.main([self.patch, self.tree, "--no-default-suites", *extra])
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
    self.assertIn("pattern hits: 0", out)
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
    refused = self.write("r.txt", ".claude/settings.json\n")
    code, out = self.gate("--refused", refused)
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
    self.assertIn("untracked: 1 new file(s), home paths in: new.txt", out)

  def test_bad_suite_argument_is_usage_error(self):
    with self.assertRaises(SystemExit) as raised, \
         contextlib.redirect_stderr(io.StringIO()):
      self.mod.main([self.patch, self.tree, "--suite", "nocommand"])
    self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
  unittest.main()
