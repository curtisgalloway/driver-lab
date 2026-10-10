# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for utilities/codex-review.py: it builds only the two fixed forms and refuses the rest."""

import os
import re
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "codex-review.py")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


SAFE = re.compile(r"/[A-Za-z0-9._/-]+")  # codex-review.py's path syntax, which runs first


def safe(path):
  """Whether codex-review.py's path-syntax checks would accept path, so that a refusal of it
  comes from the check under test and not from its spelling (SF2-G review round 2, S1)."""
  return (SAFE.fullmatch(path) is not None and "//" not in path
          and not {".", ".."} & set(path.split("/")) and os.path.realpath(path) == path)


def outside_temp_file():
  """An existing, safely spelled file outside the system temp directory, wherever the checkout
  lives: a checkout under the temp directory made README.md an inside-temp brief (SF2-G G2)."""
  tmp = os.path.realpath(tempfile.gettempdir())
  for path in (os.path.join(REPO, "README.md"), os.__file__, sys.executable, "/etc/hosts",
               "/etc/passwd"):
    real = os.path.realpath(path)
    if os.path.isfile(real) and os.path.commonpath([real, tmp]) != tmp and safe(real):
      return real
  raise unittest.SkipTest("no safely spelled file outside the temp directory to use as a brief")


def run(*args):
  return subprocess.run([sys.executable, SCRIPT, *args, "--dry-run"], capture_output=True,
                        text=True, check=False)


class CodexReviewTest(unittest.TestCase):

  def setUp(self):
    self.tmp = os.path.realpath(tempfile.mkdtemp())
    self.brief = os.path.join(self.tmp, "BRIEF.md")
    with open(self.brief, "w", encoding="utf-8") as f:
      f.write("brief\n")
    self.log = os.path.join(self.tmp, "out.log")

  def test_net_form(self):
    r = run("net", self.tmp, self.brief, self.log)
    self.assertEqual(r.returncode, 0, r.stderr)
    self.assertIn("'workspace-write'", r.stdout)
    self.assertIn("'sandbox_workspace_write.network_access=true'", r.stdout)
    self.assertIn(f"'--cd', '{self.tmp}'", r.stdout)
    self.assertIn("'sandbox_workspace_write.exclude_slash_tmp=true'", r.stdout)
    self.assertIn("'sandbox_workspace_write.exclude_tmpdir_env_var=true'", r.stdout)

  def test_log_symlink_refused(self):
    target = os.path.join(self.tmp, "target")
    open(target, "w", encoding="utf-8").close()
    os.symlink(target, self.log)
    r = subprocess.run([sys.executable, SCRIPT, "net", self.tmp, self.brief, self.log],
                       capture_output=True, text=True, check=False,
                       env={**os.environ, "PATH": self.tmp})
    self.assertEqual(r.returncode, 2, r.stderr)

  def test_ro_form(self):
    r = run("ro", REPO, self.brief, self.log)
    self.assertEqual(r.returncode, 0, r.stderr)
    self.assertIn("'read-only'", r.stdout)
    self.assertNotIn("network_access", r.stdout)

  def test_refusals(self):
    link = os.path.join(self.tmp, "link")
    os.symlink(self.tmp, link)
    cases = [
        ("net", REPO, self.brief, self.log),                     # net inside a git tree
        ("net", "/", self.brief, self.log),                      # net outside the temp dir
        ("net", self.tmp + "/../" + os.path.basename(self.tmp), self.brief, self.log),
        ("net", link, self.brief, self.log),                     # symlink
        ("net", self.tmp, self.brief, "/" + "x.log"),            # log outside temp
        ("net", self.tmp, "--upload-pack=x", self.log),          # option-shaped path
        ("net", self.tmp, self.brief + " -c a=b", self.log),     # space in path
        ("ro", self.tmp, self.brief, self.log),                  # ro needs a checkout
        ("ro", REPO, outside_temp_file(), self.log),             # ro brief outside temp
        ("exec", self.tmp, self.brief, self.log),                # unknown mode
    ]
    for case in cases:
      with self.subTest(case=case):
        self.assertEqual(run(*case).returncode, 2)

  def test_ro_brief_outside_temp_is_refused_by_the_temp_boundary(self):
    # The refusal must come from the temp-boundary check itself, not an earlier syntax check.
    if not safe(REPO):
      self.skipTest("the checkout path is not safely spelled for codex-review.py")
    brief = outside_temp_file()
    r = run("ro", REPO, brief, self.log)
    self.assertEqual(r.returncode, 2)
    self.assertIn("BRIEF must be under " + os.path.realpath(tempfile.gettempdir()), r.stderr)

  def test_extra_arguments_refused(self):
    r = subprocess.run([sys.executable, SCRIPT, "net", self.tmp, self.brief, self.log,
                        "-c", "mcp_servers.x.command=sh"], capture_output=True, check=False)
    self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
  unittest.main()
