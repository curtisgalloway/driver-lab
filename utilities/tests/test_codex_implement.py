# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for utilities/codex-implement.py: one fixed form, every refusal, and the tamper check."""

import contextlib
import importlib.util
import io
import os
import shutil
import stat
import tempfile
import unittest
from unittest import mock

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                      "codex-implement.py")


def load():
  spec = importlib.util.spec_from_file_location("codex_implement", SCRIPT)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


class CodexImplementTest(unittest.TestCase):

  def setUp(self):
    self.tmp = os.path.realpath(tempfile.mkdtemp())
    self.addCleanup(shutil.rmtree, self.tmp)
    self.mod = load()
    self.repo = os.path.join(self.tmp, "repo")
    self.home = os.path.join(self.tmp, "home")
    self.store = os.path.join(self.tmp, "store")
    self.run_dir = os.path.join(self.store, "unit-20261009-01")
    os.makedirs(self.run_dir)
    self.brief = os.path.join(self.run_dir, "brief.md")
    self.write(self.brief, "brief\n")
    self.write(os.path.join(self.home, ".config", "driver-lab", "config.toml"),
               f'run_store = "{self.store}"\n')
    self.worktree = self.make_worktree("unit")
    self.mod.REPO = self.repo
    patcher = mock.patch.object(self.mod, "home", return_value=self.home)
    patcher.start()
    self.addCleanup(patcher.stop)

  def write(self, path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
      f.write(text)

  def make_worktree(self, name):
    worktree = os.path.join(self.repo, ".claude", "worktrees", name)
    meta = os.path.join(self.repo, ".git", "worktrees", name)
    self.write(os.path.join(worktree, ".git"), f"gitdir: {meta}\n")
    self.write(os.path.join(meta, "gitdir"), f"{worktree}/.git\n")
    return worktree

  def build(self, *args):
    return self.mod.build(*args, "20261009T000000Z", "/private/tmpdir")

  def assert_refused(self, *args):
    with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
      self.build(*args)
    self.assertEqual(cm.exception.code, 2, args)

  def test_fixed_form(self):
    cmd, worktree, log, last = self.build(self.worktree, self.run_dir, self.brief)
    self.assertEqual(worktree, self.worktree)
    self.assertEqual(log, os.path.join(self.run_dir, "codex-20261009T000000Z.log"))
    self.assertEqual(last, os.path.join(self.run_dir, "last-message-20261009T000000Z.md"))
    self.assertEqual(cmd[:4], ["codex", "exec", "--sandbox", "workspace-write"])
    self.assertEqual(cmd[cmd.index("--cd") + 1], self.worktree)
    adds = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--add-dir"]
    self.assertEqual(adds, ["/private/tmpdir"])
    self.assertIn("sandbox_workspace_write.exclude_slash_tmp=true", cmd)
    self.assertFalse(any(self.store in a for a in cmd[:-3]))
    self.assertIn("model_reasoning_effort=high", cmd)
    self.assertTrue(cmd[-1].startswith(f"Read {self.brief} and carry it out"))
    self.assertIn("do not run git commit", cmd[-1])
    self.assertFalse(any(".git" in a for a in cmd))

  def test_worktree_must_be_a_linked_worktree_under_the_repo(self):
    self.assert_refused(self.store, self.run_dir, self.brief)
    self.assert_refused(self.repo, self.run_dir, self.brief)
    plain = os.path.join(self.repo, ".claude", "worktrees", "plain")
    os.makedirs(plain)
    self.assert_refused(plain, self.run_dir, self.brief)

  def test_worktree_git_file_must_point_at_its_metadata_and_back(self):
    other = self.make_worktree("other")
    self.write(os.path.join(other, ".git"), f"gitdir: {self.tmp}\n")
    self.assert_refused(other, self.run_dir, self.brief)
    third = self.make_worktree("third")
    self.write(os.path.join(self.repo, ".git", "worktrees", "third", "gitdir"), "/elsewhere\n")
    self.assert_refused(third, self.run_dir, self.brief)
    fourth = self.make_worktree("fourth")
    os.remove(os.path.join(fourth, ".git"))
    os.symlink(os.path.join(self.worktree, ".git"), os.path.join(fourth, ".git"))
    self.assert_refused(fourth, self.run_dir, self.brief)

  def test_run_store_comes_from_the_config_file_not_the_environment(self):
    with mock.patch.dict(os.environ, {"DRIVER_LAB_RUNS": self.tmp, "XDG_CONFIG_HOME": self.tmp,
                                      "HOME": self.tmp}):
      self.build(self.worktree, self.run_dir, self.brief)
      elsewhere = os.path.join(self.tmp, "elsewhere")
      os.mkdir(elsewhere)
      self.write(os.path.join(elsewhere, "brief.md"), "brief\n")
      self.assert_refused(self.worktree, elsewhere, os.path.join(elsewhere, "brief.md"))

  def test_run_dir_must_be_directly_inside_the_store(self):
    self.assert_refused(self.worktree, self.store, os.path.join(self.store, "x"))
    nested = os.path.join(self.run_dir, "nested")
    self.write(os.path.join(nested, "brief.md"), "brief\n")
    self.assert_refused(self.worktree, nested, os.path.join(nested, "brief.md"))
    self.assert_refused(self.worktree, os.path.join(self.store, "missing"), self.brief)

  def test_brief_must_be_a_file_in_the_run_dir(self):
    outside = os.path.join(self.store, "brief.md")
    self.write(outside, "brief\n")
    self.assert_refused(self.worktree, self.run_dir, outside)
    self.assert_refused(self.worktree, self.run_dir, os.path.join(self.run_dir, "missing.md"))

  def test_existing_output_paths_are_refused(self):
    os.symlink(self.home, os.path.join(self.run_dir, "last-message-20261009T000000Z.md"))
    self.assert_refused(self.worktree, self.run_dir, self.brief)

  def test_unsafe_spellings_are_refused(self):
    for bad in (self.worktree + "/.", self.worktree + "/../x", "relative/path",
                self.worktree + " -s", "-C" + self.worktree, self.worktree.replace("/", "//", 1)):
      self.assert_refused(bad, self.run_dir, self.brief)

  def test_symlinked_paths_are_refused(self):
    link = os.path.join(self.store, "link")
    os.symlink(self.run_dir, link)
    self.assert_refused(self.worktree, link, os.path.join(link, "brief.md"))

  def test_wrong_argument_count(self):
    for args in ([self.worktree, self.run_dir],
                 [self.worktree, self.run_dir, self.brief, "--sandbox=danger-full-access"]):
      with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
        self.mod.main(args)
      self.assertEqual(cm.exception.code, 2)

  def fake_codex(self, body):
    bindir = os.path.join(self.tmp, "bin")
    path = os.path.join(bindir, "codex")
    self.write(path, "#!/bin/sh\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return mock.patch.dict(os.environ, {"PATH": bindir + os.pathsep + os.environ["PATH"]})

  def run_main(self):
    for name in os.listdir(self.run_dir):
      if name.startswith(("codex-", "last-message-")):
        os.remove(os.path.join(self.run_dir, name))
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
      code = self.mod.main([self.worktree, self.run_dir, self.brief])
    return code, err.getvalue()

  def test_a_clean_run_exits_zero(self):
    with self.fake_codex("echo working\n"):
      code, err = self.run_main()
    self.assertEqual((code, err), (0, ""))

  def test_a_changed_git_file_is_restored_and_reported(self):
    dot_git = os.path.join(self.worktree, ".git")
    original = open(dot_git, "rb").read()
    with self.fake_codex(f"echo 'gitdir: /evil' > '{dot_git}'\n"):
      code, err = self.run_main()
    self.assertEqual(code, 4)
    self.assertIn("TAMPER", err)
    self.assertEqual(open(dot_git, "rb").read(), original)

  def test_new_agent_configuration_is_reported(self):
    for made in (".claude/settings.json", "CLAUDE.md", "sub/CLAUDE.local.md",
                 "sub/AGENTS.override.md"):
      with self.subTest(made=made):
        target = os.path.join(self.worktree, made)
        with self.fake_codex(f"mkdir -p '{os.path.dirname(target)}' && touch '{target}'\n"):
          code, err = self.run_main()
        self.assertEqual(code, 4)
        self.assertIn("TAMPER", err)
        shutil.rmtree(os.path.join(self.worktree, made.split("/")[0]), ignore_errors=True)
        if os.path.exists(target):
          os.remove(target)

  def test_changed_or_removed_agent_files_and_hidden_ones_are_reported(self):
    self.write(os.path.join(self.worktree, "AGENTS.md"), "rules\n")
    self.write(os.path.join(self.worktree, "docs", ".claude", "x"), "x\n")
    agents = os.path.join(self.worktree, "AGENTS.md")
    for body in (f"echo more >> '{agents}'\n", f"rm '{agents}'\n",
                 f"echo y > '{self.worktree}/docs/.claude/x'\n",
                 f"mkdir -p '{self.worktree}/.venv/lib' && touch '{self.worktree}/.venv/lib/CLAUDE.md'\n",
                 f"touch '{self.worktree}/GEMINI.md'\n"):
      with self.subTest(body=body):
        self.write(agents, "rules\n")
        self.write(os.path.join(self.worktree, "docs", ".claude", "x"), "x\n")
        with self.fake_codex(body):
          code, err = self.run_main()
        self.assertEqual(code, 4)
        self.assertIn("TAMPER", err)
        for leftover in (".venv", "GEMINI.md"):
          path = os.path.join(self.worktree, leftover)
          if os.path.isdir(path):
            shutil.rmtree(path)
          elif os.path.lexists(path):
            os.remove(path)

  def test_a_new_symlink_out_of_the_worktree_is_reported(self):
    link = os.path.join(self.worktree, "evidence.md")
    with self.fake_codex(f"ln -s '{self.home}/.bashrc' '{link}'\n"):
      code, err = self.run_main()
    self.assertEqual(code, 4)
    self.assertIn("links outside the worktree", err)
    os.remove(link)
    with self.fake_codex(f"ln -s README '{link}'\n"):
      code, err = self.run_main()
    self.assertEqual((code, err), (0, ""))

  def test_codex_gets_a_private_tmpdir_that_is_removed_afterwards(self):
    seen = os.path.join(self.tmp, "seen")
    with self.fake_codex(f"echo \"$TMPDIR\" > '{seen}'\n"):
      code, _ = self.run_main()
    self.assertEqual(code, 0)
    tmpdir = open(seen, encoding="utf-8").read().strip()
    self.assertIn("codex-implement-", tmpdir)
    self.assertFalse(os.path.exists(tmpdir))

  def test_agent_configuration_present_before_is_not_reported(self):
    self.write(os.path.join(self.worktree, "CLAUDE.md"), "already here\n")
    with self.fake_codex("true\n"):
      code, err = self.run_main()
    self.assertEqual((code, err), (0, ""))


if __name__ == "__main__":
  unittest.main()
