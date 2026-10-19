# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for utilities/check-no-hardware-facts.py and the rules it shares (prosefacts.py).

The checker runs as CI runs it, on explicit paths in a temporary directory and on its default
scope (agent files and stubs), so the exit code and the reported location are what is asserted.
"""

from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check-no-hardware-facts.py"
_spec = importlib.util.spec_from_file_location("check_no_hardware_facts", SCRIPT)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)
STUB = "---\nname: x-expert\ndescription: Board expert for X. A stub over the x board spec.\n---\n"


def run(*paths):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = check.main([str(p) for p in paths])
    return code, out.getvalue()


class Rules(unittest.TestCase):
    def setUp(self):
        self.rules = check.rules()

    def whats(self, text):
        return [what for _, _, what in self.rules.findings(text)]

    def test_hex_literals(self):
        self.assertEqual(self.whats("UART at 0xfe201000 and 0X7E20_1000."),
                         ["hex literal '0xfe201000'", "hex literal '0X7E20_1000'"])
        self.assertEqual(self.whats("range 0x1000-0x1fff"),
                         ["hex literal '0x1000'", "hex literal '0x1fff'"])
        self.assertEqual(self.whats("value 0x0 and v0x10 and 0x1"), [])  # one digit; inside a word

    def test_register_names(self):
        self.assertEqual(self.whats("set GICD_CTLR then UART0_CR"),
                         ["register-style name 'GICD_CTLR'", "register-style name 'UART0_CR'"])
        self.assertEqual(self.whats("set GICD_ITARGETSRn and GICR_IPRIORITYRn"),
                         ["register-style name 'GICD_ITARGETSRn'",
                          "register-style name 'GICR_IPRIORITYRn'"])
        self.assertEqual(self.whats("UART, SPDX-License-Identifier, my_var, $GITHUB_TOKEN, "
                                    "${CLAUDE_PLUGIN_ROOT}/x"), [])

    def test_opt_out_and_position(self):
        self.assertEqual(self.whats("an example 0xdead hw-fact-ok: format example"), [])
        self.assertEqual(self.rules.findings("ok\n  at 0xbeef")[0][:2], (2, 6))


class Command(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_flags_a_stub_with_an_address(self):
        path = self.tmp / "x-expert" / "SKILL.md"
        path.parent.mkdir()
        path.write_text(STUB + "\nThe console UART is at 0xfe201000.\n`spec: x`\n")
        code, out = run(path)
        self.assertEqual(code, 1)
        self.assertIn(f"{path}:6:", out)
        self.assertIn("hex literal '0xfe201000'", out)

    def test_clean_files_pass(self):
        path = self.tmp / "agents" / "x.md"
        path.parent.mkdir()
        path.write_text("Load board-expert and pass `spec: x`.\n")
        self.assertEqual(run(path)[0], 0)

    def test_default_scope_is_agents_and_stubs(self):
        self.assertTrue(check.in_scope("a/agents/x.md", ""))
        self.assertTrue(check.in_scope("skills/x-expert/SKILL.md", STUB))
        self.assertFalse(check.in_scope("skills/spec-format/SKILL.md",
                                        "---\nname: spec-format\ndescription: format\n---\n"))
        self.assertFalse(check.in_scope("docs/notes.md", "0xdead"))

    def test_this_repository_is_clean(self):
        code, out = run()
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
