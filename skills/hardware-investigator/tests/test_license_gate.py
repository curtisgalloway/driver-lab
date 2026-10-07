#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for scripts/license_gate.py.

Run:  python3 -m unittest discover -s skills/hardware-investigator/tests -v

Exit-code contract (as the other scripts): 0 every license accepted, 1 a license refused
(or the root cannot accept anything), 2 usage error.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "license_gate.py"
ROOTS = HERE.parent / "examples" / "roots"


def run(*args):
    proc = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


class LicenseGate(unittest.TestCase):
    def test_root_alone_prints_accepts_list(self):
        rc, out, _ = run("--root", ROOTS / "permissive")
        self.assertEqual(rc, 0)
        self.assertIn("accepts: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause", out)
        self.assertIn("example-permissive", out)

    def test_accepted_license(self):
        rc, out, _ = run("--root", ROOTS / "permissive", "MIT")
        self.assertEqual(rc, 0)
        self.assertIn("accepted: MIT", out)

    def test_refused_license_names_reason(self):
        rc, out, _ = run("--root", ROOTS / "permissive", "GPL-2.0-only")
        self.assertEqual(rc, 1)
        self.assertIn("refused: GPL-2.0-only", out)
        self.assertIn("root example-permissive", out)
        self.assertIn("accepts: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause", out)

    def test_or_passes_when_one_side_accepted(self):
        rc, out, _ = run("--root", ROOTS / "permissive", "GPL-2.0-only OR MIT")
        self.assertEqual(rc, 0, out)

    def test_and_needs_both_sides(self):
        rc, out, _ = run("--root", ROOTS / "permissive", "GPL-2.0-only AND MIT")
        self.assertEqual(rc, 1, out)

    def test_gpl_family_is_not_interchangeable(self):
        rc, out, _ = run("--root", ROOTS / "gpl", "GPL-2.0-or-later")
        self.assertEqual(rc, 0, out)
        rc, out, _ = run("--root", ROOTS / "permissive", "GPL-2.0+")
        self.assertEqual(rc, 1, out)

    def test_one_refusal_makes_exit_one_but_all_are_reported(self):
        rc, out, _ = run("--root", ROOTS / "permissive", "MIT", "GPL-3.0-only")
        self.assertEqual(rc, 1)
        self.assertIn("accepted: MIT", out)
        self.assertIn("refused: GPL-3.0-only", out)

    def test_not_an_spdx_expression_is_refused(self):
        rc, out, _ = run("--root", ROOTS / "permissive", "Totally Free License")
        self.assertEqual(rc, 1)
        self.assertIn("refused: Totally Free License", out)
        self.assertIn("not an SPDX expression", out)

    def test_root_without_accepts_refuses_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "board-specs.yaml").write_text("layer: public\nname: bare\n")
            rc, out, _ = run("--root", tmp, "MIT")
            self.assertEqual(rc, 1)
            self.assertIn("declares no accepts:", out)
            rc, out, _ = run("--root", tmp)
            self.assertEqual(rc, 1)

    def test_empty_accepts_refuses_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "board-specs.yaml").write_text(
                "layer: public\nname: docs\nlicense: CC-BY-4.0\naccepts: []\n")
            rc, out, _ = run("--root", tmp, "MIT")
            self.assertEqual(rc, 1)
            self.assertIn("accepts: none", out)

    def test_invalid_accepts_entry_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "board-specs.yaml").write_text(
                "layer: public\nname: bad\nlicense: MIT\naccepts: [Foo Bar, MIT]\n")
            rc, out, _ = run("--root", tmp, "MIT")
            self.assertEqual(rc, 1, out)
            self.assertIn("error:", out)

    def test_not_a_root_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _, err = run("--root", tmp, "MIT")
            self.assertEqual(rc, 2)
            self.assertIn("not a spec root", err)

    def test_missing_root_argument_is_a_usage_error(self):
        rc, _, _ = run("MIT")
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
