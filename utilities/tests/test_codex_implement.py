# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for utilities/codex-implement.py: it builds only the one fixed form and refuses the rest."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

UTILITIES = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SCRIPT = os.path.join(UTILITIES, "codex-implement.py")
REPO = os.path.dirname(UTILITIES)


class CodexImplementTest(unittest.TestCase):

  def setUp(self):
    self.store = os.path.realpath(tempfile.mkdtemp())
    self.run_dir = os.path.join(self.store, "unit-20261009-01")
    os.mkdir(self.run_dir)
    self.brief = os.path.join(self.run_dir, "brief.md")
    with open(self.brief, "w", encoding="utf-8") as f:
      f.write("brief\n")
    worktrees = os.path.join(REPO, ".claude", "worktrees")
    os.makedirs(worktrees, exist_ok=True)
    self.worktree = tempfile.mkdtemp(prefix="codex-implement-test-", dir=worktrees)
    with open(os.path.join(self.worktree, ".git"), "w", encoding="utf-8") as f:
      f.write("gitdir: elsewhere\n")

  def tearDown(self):
    shutil.rmtree(self.store)
    shutil.rmtree(self.worktree)

  def run_script(self, *args):
    env = dict(os.environ, DRIVER_LAB_RUNS=self.store)
    return subprocess.run([sys.executable, SCRIPT, *args, "--dry-run"], capture_output=True,
                          text=True, check=False, env=env)

  def test_fixed_form(self):
    r = self.run_script(self.worktree, self.run_dir, self.brief)
    self.assertEqual(r.returncode, 0, r.stderr)
    self.assertIn("'workspace-write'", r.stdout)
    self.assertIn(f"'--cd', '{self.worktree}'", r.stdout)
    self.assertIn(f"'--add-dir', '{os.path.join(REPO, '.git')}'", r.stdout)
    self.assertIn(f"'--add-dir', '{self.run_dir}'", r.stdout)
    self.assertIn("'model_reasoning_effort=high'", r.stdout)
    self.assertIn(f"Read {self.brief} and carry it out", r.stdout)
    self.assertNotIn("danger", r.stdout)

  def assert_refused(self, *args):
    r = self.run_script(*args)
    self.assertEqual(r.returncode, 2, (args, r.stdout, r.stderr))
    self.assertEqual(r.stdout, "")

  def test_worktree_must_be_a_linked_worktree_under_the_repo(self):
    self.assert_refused(self.store, self.run_dir, self.brief)
    self.assert_refused(REPO, self.run_dir, self.brief)
    os.remove(os.path.join(self.worktree, ".git"))
    self.assert_refused(self.worktree, self.run_dir, self.brief)

  def test_run_dir_must_be_directly_inside_the_store(self):
    self.assert_refused(self.worktree, self.store, os.path.join(self.store, "x"))
    nested = os.path.join(self.run_dir, "nested")
    os.mkdir(nested)
    brief = os.path.join(nested, "brief.md")
    with open(brief, "w", encoding="utf-8") as f:
      f.write("brief\n")
    self.assert_refused(self.worktree, nested, brief)
    self.assert_refused(self.worktree, os.path.join(self.store, "missing"), self.brief)

  def test_brief_must_be_a_file_in_the_run_dir(self):
    outside = os.path.join(self.store, "brief.md")
    with open(outside, "w", encoding="utf-8") as f:
      f.write("brief\n")
    self.assert_refused(self.worktree, self.run_dir, outside)
    self.assert_refused(self.worktree, self.run_dir, os.path.join(self.run_dir, "missing.md"))

  def test_unsafe_spellings_are_refused(self):
    for bad in (self.worktree + "/.", self.worktree + "/../x", "relative/path",
                self.worktree + " -s", "-C" + self.worktree, self.worktree.replace("/", "//", 1)):
      self.assert_refused(bad, self.run_dir, self.brief)

  def test_symlinked_paths_are_refused(self):
    link = os.path.join(self.store, "link")
    os.symlink(self.run_dir, link)
    self.assert_refused(self.worktree, link, os.path.join(link, "brief.md"))

  def test_wrong_argument_count(self):
    self.assert_refused(self.worktree, self.run_dir)
    self.assert_refused(self.worktree, self.run_dir, self.brief, "--sandbox=danger-full-access")


if __name__ == "__main__":
  unittest.main()
