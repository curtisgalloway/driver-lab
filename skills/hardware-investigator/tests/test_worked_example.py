#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Runs WORKED-EXAMPLE.md's three runs, so the fixtures and the expected facts cannot rot.

Run:  python3 -m unittest discover -s skills/hardware-investigator/tests -v

Builds the two fixture source trees as git repositories in a temporary directory, fills the
expected facts files with the real commits, and checks the format 2 gate and resolver
exit codes the example promises.
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
GATE = SKILL / "scripts" / "license_gate.py"
SPEC = SKILL.parent / "spec-format" / "scripts" / "spec.py"
EX = SKILL / "examples"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True).stdout.strip()


def py(script, *args):
    proc = subprocess.run([sys.executable, str(script), *map(str, args)],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


class WorkedExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="hw-investigator-test-"))
        cls.rev = {}
        for name in ("widget-linux", "widget-fw"):
            dest = cls.tmp / name
            shutil.copytree(EX / "sources" / name, dest)
            git(dest, "init", "-q")
            git(dest, "add", ".")
            git(dest, "commit", "-q", "-m", "fixture")
            cls.rev[name] = git(dest, "rev-parse", "HEAD")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def facts(self, answer, name):
        text = (EX / "expected" / answer).read_text().replace("1" * 40, self.rev[name])
        path = self.tmp / answer
        path.write_text(text)
        return path

    def anchor(self, answer, pin, tree, root):
        file = self.facts(answer, tree)
        rc, out = py(GATE, "--facts", file, "--root", EX / "roots" / root)
        if rc:
            return rc, out
        return py(SPEC, "resolve", file, "--repo", f"{pin}={self.tmp / tree}",
                  "--root", EX / "roots" / root)

    def test_run_a_accepting_root_passes(self):
        rc, out = py(GATE, "--root", EX / "roots" / "gpl", "GPL-2.0-only")
        self.assertEqual(rc, 0, out)
        rc, out = self.anchor("answer-linux.facts.yaml", "linux", "widget-linux", "gpl")
        self.assertEqual(rc, 0, out)
        self.assertIn("anchor(s) resolved, 0 skipped", out)

    def test_run_b_refusing_root_stops_at_the_gate(self):
        rc, out = py(GATE, "--root", EX / "roots" / "permissive", "GPL-2.0-only")
        self.assertEqual(rc, 1, out)
        self.assertIn("refused: GPL-2.0-only", out)

    def test_run_b_backstop_fails_if_the_gpl_facts_are_cited_anyway(self):
        rc, out = self.anchor("answer-linux.facts.yaml", "linux", "widget-linux", "permissive")
        self.assertEqual(rc, 1, out)
        self.assertIn("GPL-2.0-only is not accepted", out)

    def test_run_c_other_source_passes_the_refusing_root(self):
        rc, out = py(GATE, "--root", EX / "roots" / "permissive", "MIT")
        self.assertEqual(rc, 0, out)
        rc, out = self.anchor("answer-fw.facts.yaml", "fw", "widget-fw", "permissive")
        self.assertEqual(rc, 0, out)
        self.assertIn("anchor(s) resolved, 0 skipped", out)

    def test_source_licenses_match_the_example_text(self):
        linux = (EX / "sources/widget-linux/drivers/tty/serial/widget.c").read_text()
        fw = (EX / "sources/widget-fw/uart/widget_uart_init.c").read_text()
        self.assertEqual(linux.splitlines()[0], "// SPDX-License-Identifier: GPL-2.0-only")
        self.assertEqual(fw.splitlines()[0], "/* SPDX-License-Identifier: MIT */")

    def test_converted_answers_preserve_exact_format_one_claims(self):
        for source in ("linux", "fw"):
            data = yaml.safe_load((EX / "expected" / ("answer-" + source + ".facts.yaml")).read_text())
            expected = [
                "CTRL is at offset 0x00, and bit 0 enables the block.",
                "BAUD, the baud divisor, is at offset 0x04.",
                "LCR is at offset 0x08, and a write to it latches BAUD.",
                ("The driver initializes the block by clearing CTRL, writing BAUD, writing LCR, then setting the enable bit."
                 if source == "linux" else
                 "The firmware disables the block before reprogramming it, writes BAUD, writes LCR, then enables the block."),
            ]
            self.assertEqual([f.get("claim") for f in data["facts"]], expected)
            for fact in data["facts"][:3]:
                self.assertEqual(set(fact["data"]), {"register"})
                self.assertEqual(set(fact["data"]["register"]), {"name", "offset"})
            self.assertNotIn("data", data["facts"][3])
            self.assertEqual(data["facts"][3]["requirement"],
                             "as-implemented" if source == "linux" else "comment-explained")
            self.assertEqual([f["support"][0]["anchors"][0]["lines"] for f in data["facts"]],
                             [[4, 5], [6, 6], [7, 7], [12, 15]] if source == "linux" else
                             [[4, 4], [5, 5], [6, 6], [10, 13]])


if __name__ == "__main__":
    unittest.main()
