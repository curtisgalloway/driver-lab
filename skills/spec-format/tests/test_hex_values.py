# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""resolve.hex_values reads C suffixes and digit separators (issue #82)."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import resolve


class HexValues(unittest.TestCase):

    def test_c_suffixes(self):
        for text in ("0x1000", "0x1000U", "0x1000u", "0x1000L", "0x1000UL", "0x1000ul",
                     "0x1000ULL", "0x1000LLU", "0x1000LU", "(0x1000UL)"):
            with self.subTest(text=text):
                self.assertEqual(resolve.hex_values(text), {0x1000})

    def test_digit_separators(self):
        self.assertEqual(resolve.hex_values("0xF000_0000"), {0xF0000000})
        self.assertEqual(resolve.hex_values("0xF000'0000"), {0xF0000000})

    def test_zero_padding_is_the_same_value(self):
        self.assertEqual(resolve.hex_values("0x0 0x00000000 0x0UL"), {0})

    def test_not_a_hex_literal(self):
        self.assertEqual(resolve.hex_values("0xZZ x0x10 0x10G deadbeef"), set())
        self.assertEqual(resolve.hex_values("0x_10 0x10_"), set())

    def test_claim_against_suffixed_source(self):
        claim = resolve.hex_values("the window is 0x0 to 0x1000")
        source = resolve.hex_values("#define BASE 0x0UL\n#define SIZE 0x1000UL")
        self.assertEqual(claim - source, set())


if __name__ == "__main__":
    unittest.main()
