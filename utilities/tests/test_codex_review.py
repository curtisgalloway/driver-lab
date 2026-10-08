# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for utilities/codex-review.py: it builds only the two fixed forms and refuses the rest."""

import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "codex-review.py")
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
        ("ro", REPO, os.path.join(REPO, "README.md"), self.log), # ro brief outside temp
        ("exec", self.tmp, self.brief, self.log),                # unknown mode
    ]
    for case in cases:
      with self.subTest(case=case):
        self.assertEqual(run(*case).returncode, 2)

  def test_extra_arguments_refused(self):
    r = subprocess.run([sys.executable, SCRIPT, "net", self.tmp, self.brief, self.log,
                        "-c", "mcp_servers.x.command=sh"], capture_output=True, check=False)
    self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
  unittest.main()
