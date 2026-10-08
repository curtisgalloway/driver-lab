#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for spec.py's command line: exit codes 0/1/2/3, --json and --skill.

Run in the pinned environment:
  uv run --with-requirements skills/spec-format/requirements.txt \
    python3 -m unittest discover -s skills/spec-format/tests -v
"""

import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "spec.py"
VALID = HERE / "fixtures" / "valid"
sys.path.insert(0, str(SCRIPT.parent))
import spec as spec_cli  # noqa: E402

GOOD = VALID / "widget-pmic.spec.yaml"


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec_cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class ExitCodes(unittest.TestCase):
    def test_valid_is_0(self):
        code, out, _ = run(["validate", str(GOOD)])
        self.assertEqual(code, 0)
        self.assertIn("1 file(s), 0 invalid, 0 finding(s)", out)

    def test_invalid_is_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = pathlib.Path(tmp) / "x.spec.yaml"
            bad.write_text("format: 2\nkind: chip\nfacts: []\n", encoding="utf-8")
            code, out, _ = run(["validate", str(bad), str(GOOD)])
            self.assertEqual(code, 1)
            self.assertIn(f"{bad}:1:1: (top): 'id' is a required property", out)
            self.assertIn("2 file(s), 1 invalid", out)
            bad.write_text("a: &x 1\n", encoding="utf-8")
            code, out, _ = run(["validate", str(bad)])
            self.assertEqual(code, 1)
            self.assertIn(f"{bad}:1:4: an anchor", out)

    def test_usage_is_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            other = tmp / "spec.yml"
            other.write_text("format: 2\n", encoding="utf-8")
            cases = [
                [],
                ["frobnicate"],
                ["validate"],
                ["validate", str(tmp / "missing.spec.yaml")],
                ["validate", str(other)],
                ["validate", str(tmp)],
                ["validate", "--root", str(tmp / "nope"), str(GOOD)],
                ["validate", "--root", str(tmp), str(GOOD)],
                ["validate", "--bogus", str(GOOD)],
                ["validate", "--js", str(GOOD)],
                ["validate", "--ro", str(VALID), str(GOOD)],
            ]
            for argv in cases:
                with self.subTest(argv):
                    code, out, err = run(argv)
                    self.assertEqual(code, 2, err)
                    self.assertEqual(out, "")
                    self.assertIn("usage error", err)
                    code, out, err = run(argv + ["--json"])
                    self.assertEqual(code, 2, err)
                    self.assertEqual(json.loads(out)["error"], "usage")

    def test_missing_dependency_is_3(self):
        with tempfile.TemporaryDirectory() as tmp:
            req = pathlib.Path(tmp) / "requirements.txt"
            text = spec_cli.REQUIREMENTS.read_text(encoding="utf-8")
            req.write_text(text.replace("jsonschema==4.26.0", "jsonschema==0.0.1"),
                           encoding="utf-8")
            with mock.patch.object(spec_cli, "REQUIREMENTS", req):
                code, out, err = run(["validate", str(GOOD)])
                self.assertEqual(code, 3)
                self.assertIn("jsonschema is 4.26.0, pinned 0.0.1", err)
                code, out, err = run(["validate", "--json", str(GOOD)])
                self.assertEqual(code, 3)
                self.assertEqual(json.loads(out)["error"], "precondition")
        with mock.patch.dict(spec_cli.DIRECT, {"not-a-real-dist": "nope"}):
            with mock.patch.object(spec_cli, "pinned_versions",
                                   return_value=dict(spec_cli.pinned_versions(),
                                                     **{"not-a-real-dist": "1.0"})):
                code, _, err = run(["validate", str(GOOD)])
                self.assertEqual(code, 3)
                self.assertIn("not-a-real-dist is not installed", err)

    def test_no_site_packages_is_3(self):
        """With site-packages off (-S), nothing is importable: exit 3, no fallback."""
        proc = subprocess.run([sys.executable, "-S", str(SCRIPT), "validate", str(GOOD)],
                              capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("is not installed", proc.stderr)

    def test_dependency_check_reads_every_direct_pin(self):
        pins = spec_cli.pinned_versions()
        self.assertEqual({d: pins[d] for d in spec_cli.DIRECT},
                         {"pyyaml": "6.0.3", "jsonschema": "4.26.0", "markdown-it-py": "4.2.0"})
        self.assertEqual(spec_cli.check_dependencies(), [])


class Output(unittest.TestCase):
    def test_json(self):
        code, out, err = run(["validate", "--json", str(GOOD)])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        result = json.loads(out)
        self.assertEqual(result, {"ok": True, "findings": [],
                                  "files": [{"path": str(GOOD), "schema": "spec",
                                             "valid": True}]})

    def test_json_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = pathlib.Path(tmp) / "board-specs.yaml"
            bad.write_text("format: 2\nlayer: public\nname: X\n", encoding="utf-8")
            code, out, _ = run(["validate", "--json", str(bad)])
        self.assertEqual(code, 1)
        result = json.loads(out)
        self.assertFalse(result["ok"])
        self.assertEqual(result["files"][0]["schema"], "root")
        self.assertEqual(result["findings"][0]["line"], 3)
        self.assertEqual(result["findings"][0]["column"], 7)
        self.assertIn("name: 'X' does not match", result["findings"][0]["message"])

    def test_skill(self):
        code, out, _ = run(["--skill"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("---\nname: "))
        self.assertIn("Exit status", out)

    def test_runs_as_a_script(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "validate", str(GOOD)],
                              capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
