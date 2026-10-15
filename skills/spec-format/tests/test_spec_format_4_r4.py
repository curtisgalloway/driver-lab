# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Round-4 regressions for parser nesting-limit exhaustion, including lookahead."""

import json
import unittest

import yaml

from test_check import check, chip
from test_render_md import run
import test_render_md as render_tests
import specmd


class ReviewRound4(unittest.TestCase):
    setUp = render_tests.Views.setUp
    write = render_tests.Views.write

    def exhausted_field(self, opener, depth, field):
        value = opener * depth + "x" + "](javascript:alert(1))" * depth
        data = yaml.safe_load(chip())
        data["facts"][0][field] = value
        self.write(data)
        with self.subTest(surface="parser"):
            self.assertTrue(any(f.kind == "nesting" for f in specmd.findings(value)))
        with self.subTest(surface="check"):
            code, result = check(self.root)
            self.assertEqual(code, 1, result)
            self.assertTrue(any("nesting" in f["message"] and "facts[0]." + field in f["message"]
                                for f in result["findings"]), result)
        with self.subTest(surface="render"):
            code, out, err = run(self.root, "--format", "md", "--json")
            self.assertEqual((code, err), (1, ""), out)
            result = json.loads(out)
            self.assertIsNone(result["markdown"])
            self.assertTrue(any("nesting" in f["message"] for f in result["findings"]), result)

    def test_image_65_claim(self):
        self.exhausted_field("![", 65, "claim")

    def test_image_130_claim(self):
        self.exhausted_field("![", 130, "claim")

    def test_image_65_note(self):
        self.exhausted_field("![", 65, "note")

    def test_image_130_note(self):
        self.exhausted_field("![", 130, "note")

    def test_link_65_claim(self):
        self.exhausted_field("[", 65, "claim")

    def test_link_130_claim(self):
        self.exhausted_field("[", 130, "claim")

    def test_link_65_note(self):
        self.exhausted_field("[", 65, "note")

    def test_link_130_note(self):
        self.exhausted_field("[", 130, "note")

    def test_block_limit_recorded(self):
        for depth in (65, 130):
            with self.subTest(depth=depth):
                env = {}
                specmd._parser().parse("> " * depth + "deep", env)
                self.assertTrue(env.get("nesting_limit"))
                self.assertTrue(any(f.kind == "nesting" for f in
                                    specmd.findings("> " * depth + "deep")))

    def test_limit_state_does_not_leak_and_literal_brackets_are_allowed(self):
        specmd.findings("![" * 130 + "x" + "](https://example.invalid)" * 130)
        for value in ("ordinary", "[x](https://example.invalid)",
                      "![x](https://example.invalid)", "[x] " * 130,
                      r"\[" * 130 + "x" + r"\]" * 130,
                      "`" + "![" * 130 + "`", "```\n" + "![" * 130 + "\n```"):
            with self.subTest(value=value):
                self.assertEqual(specmd.findings(value), [])


if __name__ == "__main__":
    unittest.main()
