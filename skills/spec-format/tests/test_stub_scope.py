#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for #156's stub checks in `spec.py check --stubs-from`: hardware facts in stub prose,
`instance:` lines, duplicate stub names, and two stubs sharing an entry spec without a split.

Each test writes stubs into a temporary skills directory and checks them against
fixtures/check/good_root.

Run in the pinned environment:
  .venv-spec/bin/python -m unittest discover -s skills/spec-format/tests -v
"""

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "spec.py"
GOOD = HERE / "fixtures" / "check" / "good_root"
sys.path.insert(0, str(SCRIPT.parent))
import spec as spec_cli  # noqa: E402


def stub(name, body, spec="widgetsoc"):
    return (f"---\nname: {name}\ndescription: Domain expert for {name}. A stub over the {spec} "
            f"spec: board-expert does the work.\n---\n\n`spec: {spec}`\n{body}\n")


class StubScope(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.skills = pathlib.Path(self._tmp.name) / "skills"
        self.skills.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def put(self, folder, text, where=None):
        path = (where or self.skills) / folder / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        return path

    def check(self, *dirs):
        out = io.StringIO()
        argv = ["check", "--json", str(GOOD), "--public-skill", "widget-board-tools"]
        for d in dirs or (self.skills,):
            argv += ["--stubs-from", str(d)]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = spec_cli.main(argv)
        result = json.loads(out.getvalue())
        stubs = [f for f in result["findings"] if "SKILL.md" in f["path"]]
        return code, [(f["level"], f["message"]) for f in stubs]

    def test_clean_stub(self):
        self.put("usb-expert", stub("usb-expert", "`instance: widgetsoc#uart0`"))
        self.assertEqual(self.check(), (0, []))

    def test_hex_and_register_names_are_errors(self):
        path = self.put("usb-expert", stub("usb-expert", "The UART is at 0x7e201000; set UART_CR."))
        code, found = self.check()
        self.assertEqual(code, 1)
        self.assertEqual([lvl for lvl, _ in found], ["error", "error"])
        self.assertIn("hex literal '0x7e201000'", found[0][1])
        self.assertIn("register-style name 'UART_CR'", found[1][1])
        path.write_text(stub("usb-expert", "Format example 0x7e201000 hw-fact-ok: format only"))
        self.assertEqual(self.check(), (0, []))

    def test_instance_line_resolves(self):
        self.put("usb-expert", stub("usb-expert", "`instance: widgetsoc#uart9`"))
        code, found = self.check()
        self.assertEqual(code, 1)
        self.assertIn("instance widgetsoc#uart9 resolves to no instance row", found[0][1])
        self.put("fact-expert", stub("fact-expert", "`instance: widgetsoc#uart-base`\n"
                                     "`split: usb-expert owns the UART`"))
        code, found = self.check()
        self.assertIn("instance widgetsoc#uart-base resolves to no instance row",
                      " ".join(m for _, m in found))  # a fact, not an instance row

    def test_duplicate_names_across_installed_roots(self):
        other = pathlib.Path(self._tmp.name) / "other"
        self.put("usb-expert", stub("usb-expert", "`split: usb-expert in other owns host mode`"))
        self.put("usb-expert", stub("usb-expert", "`split: usb-expert owns device mode`"),
                 where=other)
        code, found = self.check(self.skills, other)
        self.assertEqual(code, 1)
        self.assertEqual([lvl for lvl, _ in found], ["error"])
        self.assertIn("stub name 'usb-expert' is also the name of", found[0][1])

    def test_one_file_given_twice_is_not_a_duplicate(self):
        path = self.put("usb-expert", stub("usb-expert", ""))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = spec_cli.main(["check", "--json", str(GOOD), "--public-skill",
                                  "widget-board-tools", "--stubs-from", str(self.skills),
                                  "--stubs-from", str(self.skills), "--stub", str(path)])
        self.assertEqual(code, 0, out.getvalue())

    def test_quoted_names_are_compared(self):
        other = pathlib.Path(self._tmp.name) / "other"
        self.put("a", stub('"usb-expert"', "`split: a whole other usb-expert`"))
        self.put("b", stub("usb-expert", ""), where=other)
        code, found = self.check(self.skills, other)
        self.assertIn("stub name 'usb-expert' is also the name of", " ".join(m for _, m in found))

    def test_split_names_the_whole_stub(self):
        self.put("rpi-usb", stub("rpi-usb", ""))
        self.put("rpi-usb-host", stub("rpi-usb-host", ""))
        self.put("rpi-storage", stub("rpi-storage", "`split: rpi-usb-host owns USB storage`"))
        code, found = self.check()
        warned = [m for _, m in found if "no stated split" in m]
        # rpi-usb and rpi-usb-host share widgetsoc with no split; rpi-storage vs rpi-usb too,
        # since naming rpi-usb-host does not name rpi-usb
        self.assertEqual(len(warned), 2, warned)
        self.assertTrue(any("'rpi-storage'" in m and "'rpi-usb'" in m for m in warned), warned)

    def test_shared_entry_spec_needs_a_split(self):
        self.put("usb-expert", stub("usb-expert", ""))
        self.put("storage-expert", stub("storage-expert", ""))
        code, found = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], "warning")
        self.assertIn("both enter through spec 'widgetsoc' with no stated split", found[0][1])
        self.put("split-note", "not a stub\n")  # ignored: no front matter
        (self.skills / "storage-expert" / "SKILL.md").write_text(
            stub("storage-expert", "`split: usb-expert answers USB mass storage`"))
        self.assertEqual(self.check(), (0, []))


if __name__ == "__main__":
    unittest.main()
