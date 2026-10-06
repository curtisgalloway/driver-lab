#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""
Table tests for scripts/spdx.py: parsing, normalization and the license gate's acceptance rule.

Run:  python3 -m unittest discover -s skills/board-expert/tests -v
"""

import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import spdx  # noqa: E402

GPL_ROOT = ("GPL-2.0-only", "GPL-2.0-or-later", "Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause")
PERMISSIVE_ROOT = ("Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause")
DOCS_ROOT = ()


class Parse(unittest.TestCase):
    def test_normalized_forms(self):
        for text, expected in (
            ("MIT", "MIT"),
            ("mit", "MIT"),
            ("GPL-2.0", "GPL-2.0-only"),
            ("GPL-2.0+", "GPL-2.0-or-later"),
            ("GPL-2.0-only+", "GPL-2.0-or-later"),
            ("GPL-2.0-or-later", "GPL-2.0-or-later"),
            ("LGPL-2.1+", "LGPL-2.1-or-later"),
            ("Apache-2.0+", "Apache-2.0+"),
            ("GPL-2.0 OR MIT", "GPL-2.0-only OR MIT"),
            ("(GPL-2.0+ OR MIT)", "GPL-2.0-or-later OR MIT"),
            ("GPL-2.0 WITH Linux-syscall-note", "GPL-2.0-only WITH Linux-syscall-note"),
            ("MIT AND BSD-3-Clause OR ISC", "(MIT AND BSD-3-Clause) OR ISC"),
            ("MIT AND (BSD-3-Clause OR ISC)", "MIT AND (BSD-3-Clause OR ISC)"),
            ("LicenseRef-vendor-blob", "LicenseRef-vendor-blob"),
            ("DocumentRef-x:LicenseRef-y", "DocumentRef-x:LicenseRef-y"),
            ("  BSD-3-Clause  ", "BSD-3-Clause"),
            ("(" * 32 + "MIT" + ")" * 32, "MIT"),
        ):
            with self.subTest(text=text):
                self.assertEqual(str(spdx.parse(text)), expected)

    def test_errors_name_the_problem(self):
        for text, fragment in (
            ("", "empty license expression"),
            ("mainline", "unknown SPDX license identifier 'mainline'"),
            ("GPL-2", "unknown SPDX license identifier 'GPL-2'"),
            ("GPL-2.0 or MIT", "write the operator in uppercase (OR)"),
            ("MIT OR", "expression ends where a license identifier was expected"),
            ("OR MIT", "'OR' where a license identifier was expected"),
            ("(MIT OR ISC", "unbalanced parenthesis: '(' without ')'"),
            ("MIT OR ISC)", "unbalanced parenthesis: ')' without '('"),
            ("MIT ISC", "unexpected 'ISC' after a complete expression"),
            ("GPL-2.0 WITH", "WITH must be followed by an exception identifier"),
            ("GPL-2.0 WITH no-such-exception", "unknown SPDX exception identifier"),
            ("(MIT) WITH Linux-syscall-note", "WITH must follow a single license identifier"),
            ("+", "is not a license identifier"),
            ("(MIT and ISC)", "'and': write the operator in uppercase (AND)"),
            ("(MIT ISC)", "unexpected 'ISC' after a complete expression"),
            ("(" * 200 + "MIT" + ")" * 200, "parentheses nested more than 32 deep"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(spdx.SpdxError) as ctx:
                    spdx.parse(text)
                self.assertIn(fragment, str(ctx.exception))

    def test_non_strings_are_errors(self):
        for value in (None, 3, ["MIT"]):
            with self.subTest(value=value), self.assertRaises(spdx.SpdxError) as ctx:
                spdx.parse(value)
            self.assertIn("expected an SPDX expression as a string", str(ctx.exception))

    def test_accepts_entries_are_single_identifiers(self):
        self.assertEqual(spdx.parse_identifier("GPL-2.0"), "GPL-2.0-only")
        self.assertEqual(spdx.parse_identifier("0BSD"), "0BSD")
        for text in ("MIT OR ISC", "GPL-2.0 WITH Linux-syscall-note"):
            with self.subTest(text=text), self.assertRaises(spdx.SpdxError) as ctx:
                spdx.parse_identifier(text)
            self.assertIn("an accepts list holds single license identifiers", str(ctx.exception))


class Accepted(unittest.TestCase):
    """The design's acceptance item 2, and the OR/AND/WITH/-or-later rules."""

    def check(self, expression, accepts):
        return spdx.check(expression, accepts)[0]

    def test_table(self):
        for expression, gpl, permissive, docs in (
            ("GPL-2.0-only", True, False, False),
            ("GPL-2.0", True, False, False),
            ("GPL-2.0+", True, False, False),
            ("GPL-2.0 OR MIT", True, True, False),
            ("(GPL-2.0+ OR MIT)", True, True, False),
            ("GPL-2.0-only AND MIT", True, False, False),
            ("MIT AND BSD-3-Clause", True, True, False),
            ("GPL-2.0 WITH Linux-syscall-note", True, False, False),
            ("BSD-3-Clause", True, True, False),
            ("GPL-3.0-only", False, False, False),
            ("GPL-3.0-only OR MIT", True, True, False),
            ("LicenseRef-vendor-blob", False, False, False),
            ("Apache-2.0+", False, False, False),
        ):
            with self.subTest(expression=expression):
                self.assertEqual(self.check(expression, GPL_ROOT), gpl)
                self.assertEqual(self.check(expression, PERMISSIVE_ROOT), permissive)
                self.assertEqual(self.check(expression, DOCS_ROOT), docs)

    def test_or_later_needs_its_own_entry(self):
        self.assertFalse(self.check("GPL-2.0-or-later", ("GPL-2.0-only",)))
        self.assertFalse(self.check("GPL-2.0+", ("GPL-2.0-only",)))
        self.assertFalse(self.check("GPL-2.0-only", ("GPL-2.0-or-later",)))
        self.assertTrue(self.check("GPL-2.0+", ("GPL-2.0-or-later",)))

    def test_matching_is_by_canonical_id(self):
        accepts = (spdx.parse_identifier("gpl-2.0"),)
        self.assertTrue(self.check("GPL-2.0-only", accepts))
        self.assertTrue(self.check("gpl-2.0", accepts))


if __name__ == "__main__":
    unittest.main()
