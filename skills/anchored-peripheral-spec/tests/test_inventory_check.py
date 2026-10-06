#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""
Tests for scripts/inventory_check.py, against synthetic git repositories built per run.

Run:  python3 -m unittest discover -s skills/anchored-peripheral-spec/tests -v
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

from test_anchor_check import make_repo

HERE = pathlib.Path(__file__).resolve().parent
CHECKER = HERE.parent / "scripts" / "inventory_check.py"

REGS_H = textwrap.dedent("""\
    #ifndef WIDGET_REGS_H
    #define WIDGET_REGS_H
    #define WIDGET_CTRL_OFFSET 0x10
    #define WIDGET_STAT_OFFSET 0x14
    #define WIDGET_IRQ_MASK 0x0f
    #endif
    """)

BOARD_DTSI = textwrap.dedent("""\
    / {
        widget0: widget@fe200000 {
            compatible = "acme,widget";
            reg = <0x0 0xfe200000 0x0 0x100>;
            clock-names = "core";
            interrupts = <GIC_SPI 42 IRQ_TYPE_LEVEL_HIGH>;
        };
    };
    """)


class InventoryCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="inventory-check-test-")
        cls.linux, cls.linux_rev = make_repo(
            cls.tmp, "linux", {"regs.h": REGS_H, "board.dtsi": BOARD_DTSI})
        cls.other, cls.other_rev = make_repo(cls.tmp, "other", {"regs.h": "/* empty */\n"})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def spec(self, body):
        f = tempfile.NamedTemporaryFile("w", suffix=".md", dir=self.tmp, delete=False)
        f.write(textwrap.dedent(body))
        f.close()
        return f.name

    def run_check(self, *args):
        proc = subprocess.run([sys.executable, str(CHECKER), *map(str, args)],
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout + proc.stderr


class TestCharacterization(InventoryCase):
    """Behavior with one pin, as before named pins."""

    def test_complete_spec_passes(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            WIDGET_CTRL is at 0x10. WIDGET_STAT is at 0x14. WIDGET_IRQ_MASK masks.
            """)
        rc, out = self.run_check(s, "--repo", self.linux, "--headers", "regs.h", "--strict")
        self.assertEqual(rc, 0, out)
        self.assertIn("omitted: 0", out)

    def test_wrong_offset_is_a_mismatch(self):
        s = self.spec(f"Source pin: linux@{self.linux_rev}\n\nWIDGET_CTRL is at 0x18.\n")
        rc, out = self.run_check(s, "--repo", self.linux, "--headers", "regs.h")
        self.assertEqual(rc, 1, out)
        self.assertIn("MISMATCH WIDGET_CTRL_OFFSET: header 0x10, spec 0x18", out)

    def test_two_values_for_one_name_conflict(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            WIDGET_IRQ_MASK is 0x0f.
            WIDGET_IRQ_MASK is 0x1f.
            """)
        rc, out = self.run_check(s, "--repo", self.linux, "--headers", "regs.h")
        self.assertEqual(rc, 1, out)
        self.assertIn("CONFLICT WIDGET_IRQ_MASK", out)

    def test_omissions_fail_only_when_strict(self):
        s = self.spec(f"Source pin: linux@{self.linux_rev}\n\nWIDGET_CTRL is at 0x10.\n")
        rc, out = self.run_check(s, "--repo", self.linux, "--headers", "regs.h")
        self.assertEqual(rc, 0, out)
        self.assertIn("omitted  WIDGET_STAT_OFFSET", out)
        rc, out = self.run_check(s, "--repo", self.linux, "--headers", "regs.h", "--strict")
        self.assertEqual(rc, 1, out)

    def test_dt_node_inventory(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}

            The acme,widget block at 0xfe200000 takes the core clock on SPI 42.
            """)
        rc, out = self.run_check(s, "--repo", self.linux, "--dt", "board.dtsi",
                                 "--dt-node", "widget0", "--strict")
        self.assertEqual(rc, 0, out)
        s2 = self.spec(f"Source pin: linux@{self.linux_rev}\n\nThe acme,widget block.\n")
        rc, out = self.run_check(s2, "--repo", self.linux, "--dt", "board.dtsi",
                                 "--dt-node", "widget0", "--strict")
        self.assertEqual(rc, 1, out)
        self.assertIn("omitted  DT clock-names: core", out)

    def test_usage_errors(self):
        s = self.spec("WIDGET_CTRL is at 0x10.\n")
        rc, out = self.run_check(s, "--repo", self.linux, "--headers", "regs.h")
        self.assertEqual(rc, 2, out)  # no @rev and no pin
        s = self.spec(f"Source pin: linux@{self.linux_rev}\n")
        rc, out = self.run_check(s, "--repo", self.linux)
        self.assertEqual(rc, 2, out)  # neither --headers nor --dt
        rc, out = self.run_check(s, "--repo", self.linux, "--headers", "absent.h")
        self.assertEqual(rc, 2, out)


class TestNamedPins(InventoryCase):
    """Several named Source pins (LS-R3, LS-R9)."""

    def two_pin_spec(self):
        return self.spec(f"""\
            Source pin: other@{self.other_rev} MIT
            Source pin: linux@{self.linux_rev} GPL-2.0-only

            WIDGET_CTRL is at 0x10. WIDGET_STAT is at 0x14. WIDGET_IRQ_MASK masks.
            """)

    def test_named_repo_uses_that_pins_revision(self):
        rc, out = self.run_check(self.two_pin_spec(), "--repo", f"linux={self.linux}",
                                 "--headers", "regs.h", "--strict")
        self.assertEqual(rc, 0, out)
        self.assertIn(f"at {self.linux_rev}", out)

    def test_bare_repo_with_several_pins_is_usage_error(self):
        rc, out = self.run_check(self.two_pin_spec(), "--repo", self.linux, "--headers", "regs.h")
        self.assertEqual(rc, 2, out)
        self.assertIn("name one", out)

    def test_unknown_pin_name_is_usage_error(self):
        rc, out = self.run_check(self.two_pin_spec(), "--repo", f"uboot={self.linux}",
                                 "--headers", "regs.h")
        self.assertEqual(rc, 2, out)
        self.assertIn("names pin 'uboot'", out)

    def test_repeated_pin_name_fails(self):
        s = self.spec(f"""\
            Source pin: linux@{self.linux_rev}
            Source pin: linux@{self.other_rev}
            """)
        rc, out = self.run_check(s, "--repo", f"linux={self.linux}", "--headers", "regs.h")
        self.assertEqual(rc, 1, out)
        self.assertIn("repeats a Source pin name", out)


if __name__ == "__main__":
    unittest.main()
