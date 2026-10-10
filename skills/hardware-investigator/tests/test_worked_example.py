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

    def test_answers_preserve_claims_except_explicit_comment_attribution(self):
        for source in ("linux", "fw"):
            data = yaml.safe_load((EX / "expected" / ("answer-" + source + ".facts.yaml")).read_text())
            expected = [
                "CTRL is at offset 0x00, and bit 0 enables the block.",
                "BAUD, the baud divisor, is at offset 0x04.",
                "LCR is at offset 0x08; the source comment says a write to it latches BAUD.",
                ("The driver initializes the block by clearing CTRL, writing BAUD, writing LCR, then setting the enable bit."
                 if source == "linux" else
                 "The firmware disables the block before reprogramming it, writes BAUD, writes LCR, then enables the block."),
            ]
            self.assertEqual([f.get("claim") for f in data["facts"]], expected)
            for fact in data["facts"][:3]:
                self.assertEqual(set(fact["data"]), {"register"})
                self.assertEqual(set(fact["data"]["register"]), {"name", "offset"})
            self.assertEqual(set(data["facts"][3]["data"]), {"sequence"})
            self.assertEqual(data["facts"][3]["requirement"],
                             "as-implemented" if source == "linux" else "comment-explained")
            self.assertEqual([f["support"][0]["anchors"][0]["lines"] for f in data["facts"]],
                             [[4, 5], [6, 6], [7, 7], [12, 15]] if source == "linux" else
                             [[4, 4], [5, 5], [6, 6], [10, 13]])

    def test_lcr_claims_attribute_the_comment_anchors(self):
        for source in ("linux", "fw"):
            with self.subTest(source=source):
                data = yaml.safe_load((EX / "expected" / f"answer-{source}.facts.yaml").read_text())
                lcr = next(f for f in data["facts"] if f["id"] == "reg-lcr")
                self.assertTrue(lcr["support"][0]["anchors"][0]["comment"])
                self.assertIn("the source comment says", lcr["claim"])

    def test_facts_spdx_headers_match_the_destination_root(self):
        for source, root in (("linux", "gpl"), ("fw", "permissive")):
            with self.subTest(source=source):
                marker = yaml.safe_load((EX / "roots" / root / "board-specs.yaml").read_text())
                header = (EX / "expected" / f"answer-{source}.facts.yaml").read_text().splitlines()[:2]
                self.assertEqual(header, ["# SPDX-FileCopyrightText: 2026 contributors",
                                          "# SPDX-License-Identifier: " + marker["license"]])

    def test_expected_answers_assemble_into_peripheral_specs(self):
        for source, tree, root_name in (("linux", "widget-linux", "gpl"),
                                        ("fw", "widget-fw", "permissive")):
            with self.subTest(source=source):
                facts = self.facts(f"answer-{source}.facts.yaml", tree)
                original = yaml.safe_load(facts.read_text())
                assembled = yaml.safe_load(facts.read_text())
                assembled.update(kind="peripheral", id=f"widget-{source}",
                                 name=f"Widget {source} UART")
                for fact in assembled["facts"]:
                    fact["section"] = "registers" if "register" in fact.get("data", {}) else "sequences"
                root = self.tmp / f"assembled-{source}"
                root.mkdir()
                shutil.copy(EX / "roots" / root_name / "board-specs.yaml", root)
                path = root / "widget.spec.yaml"
                header = "\n".join(facts.read_text().splitlines()[:2]) + "\n"
                path.write_text(header + yaml.safe_dump(assembled, sort_keys=False))
                for args in (("validate", path, "--root", root),
                             ("check", root, "--require-license"),
                             ("resolve", path, "--root", root, "--repo", f"{source}={self.tmp / tree}")):
                    rc, out = py(SPEC, *args)
                    self.assertEqual(rc, 0, out)
                    if args[0] == "resolve":
                        self.assertIn("4 anchor(s) resolved, 0 skipped", out)
                restored = yaml.safe_load(path.read_text())
                for fact in restored["facts"]:
                    fact["section"] = "facts"
                restored["kind"] = "facts"
                del restored["id"], restored["name"]
                self.assertEqual(restored, original)


if __name__ == "__main__":
    unittest.main()
