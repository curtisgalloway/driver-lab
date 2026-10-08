#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for scripts/specload.py: one failing input per row of the design's loader table.

Run in the pinned environment (pip checks the hashes; `uv run --with-requirements` does not):
  python3 -m venv .venv-sf2
  .venv-sf2/bin/pip install --require-hashes -r skills/spec-format/requirements.txt
  .venv-sf2/bin/python -m unittest discover -s skills/spec-format/tests -v

Inputs are bytes written here with escapes, never raw control or invisible characters, so the
test file itself stays plain text. Each case names the line and column the error must report.
"""

import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import specload  # noqa: E402

# (label, bytes, line, column, substring of the problem). One row per pitfall in the design's
# "The YAML loader" table, several where a row names several spellings.
FAILING = [
    # Anchors and aliases, merge keys.
    ("anchor", b"a: &x 1\nb: 2\n", 1, 4, "an anchor (&x)"),
    ("anchor on a mapping", b"a: &x {b: 1}\n", 1, 4, "an anchor"),
    ("alias", b"a: 1\nb: *x\n", 2, 4, "alias"),
    ("anchor and alias", b"a: &x 1\nb: *x\n", 1, 4, "an anchor"),
    ("merge key", b"a: 1\n<<: {b: 2}\n", 2, 1, "a merge key"),
    ("quoted merge key", b'"<<": {b: 2}\n', 1, 1, "a merge key"),
    # Explicit tags.
    ("python tag", b"a: !!python/object:os.system x\n", 1, 4, "an explicit tag"),
    ("custom tag", b"a: !custom x\n", 1, 4, "an explicit tag"),
    ("str tag", b"a: !!str 1\n", 1, 4, "an explicit tag"),
    ("non-specific tag", b"a: ! 1\n", 1, 4, "an explicit tag"),
    ("tag on a sequence", b"a: !!seq [1]\n", 1, 4, "an explicit tag"),
    ("directive", b"%YAML 1.1\n---\na: 1\n", 1, 1, "directive"),
    ("tag directive", b"%TAG !e! tag:example.com,2000:\n---\na: 1\n", 1, 1, "directive"),
    # Several documents.
    ("two documents", b"a: 1\n---\nb: 2\n", 2, 1, "more than one YAML document"),
    ("two documents, both marked", b"---\na: 1\n...\n---\nb: 2\n", 4, 1, "more than one"),
    ("empty file", b"", 1, 1, "an empty file"),
    ("comments only", b"# nothing\n", 1, 1, "an empty file"),
    # Duplicate keys.
    ("duplicate key", b"a: 1\nb: 2\na: 3\n", 3, 1, "a duplicate key: a"),
    ("duplicate key, quoted and plain", b'a: 1\n"a": 2\n', 2, 1, "a duplicate key: a"),
    ("duplicate nested key", b"a:\n  b: 1\n  b: 2\n", 3, 3, "a duplicate key: b"),
    # Non-string keys.
    ("integer key", b"1: x\n", 1, 1, "a non-string key (1)"),
    ("boolean key", b"true: y\n", 1, 1, "a non-string key (true)"),
    ("null key", b"null: y\n", 1, 1, "a non-string key (null)"),
    ("empty key", b": y\n", 1, 1, ""),
    ("sequence key", b"? [a, b]\n: y\n", 1, 3, "a mapping or list used as a key"),
    ("mapping key", b"? {a: 1}\n: y\n", 1, 3, "a mapping or list used as a key"),
    # Implicit typing: what is not one of the four plain forms is a string, so an empty plain
    # value (a second spelling of null or "") is refused.
    ("empty value", b"a:\nb: 1\n", 1, 3, "an empty value"),
    ("empty list item", b"a:\n  -\n  - x\n", 2, 4, "an empty value"),
    ("empty flow value", b"a: {b: }\n", 1, 7, "an empty value"),
    # Invisible and control characters, NFC.
    ("zero-width space", b"a: x\xe2\x80\x8by\n", 1, 5, "U+200B"),
    ("zero-width space, escaped", b'a: "x\\u200by"\n', 1, 4, "U+200B"),
    ("bidirectional override", b"a: ab\xe2\x80\xaecd\n", 1, 6, "U+202E"),
    ("bidirectional isolate", b"a: ab\xe2\x81\xa6cd\n", 1, 6, "U+2066"),
    ("word joiner", b"a: ab\xe2\x81\xa0cd\n", 1, 6, "U+2060"),
    ("BOM inside a value", b"a: ab\xef\xbb\xbfcd\n", 1, 6, "U+FEFF"),
    ("soft hyphen", b"a: ab\xc2\xadcd\n", 1, 6, "U+00AD"),
    ("no-break space", b"a: ab\xc2\xa0cd\n", 1, 6, "U+00A0"),
    ("line separator, escaped", b'a: "ab\\Lcd"\n', 1, 4, "U+2028"),
    ("paragraph separator, escaped", b'a: "ab\\Pcd"\n', 1, 4, "U+2029"),
    ("line separator in a quoted value", b'a: "ab\xe2\x80\xa8cd"\n', 1, 7, "U+2028"),
    ("private use", b"a: ab\xee\x80\x80cd\n", 1, 6, "U+E000"),
    ("tab in a value", b"a: 'ab\tcd'\n", 1, 7, "U+0009"),
    ("tab in a block scalar", b"a: |\n  ab\tcd\n", 2, 5, "U+0009"),
    ("escaped NUL", b'a: "x\\0y"\n', 1, 4, "U+0000"),
    ("escaped C0", b'a: "x\\x01y"\n', 1, 4, "U+0001"),
    ("escaped CR", b'a: "x\\ry"\n', 1, 4, "U+000D"),
    ("escaped DEL", b'a: "x\\x7fy"\n', 1, 4, "U+007F"),
    ("escaped C1", b'a: "x\\x85y"\n', 1, 4, "U+0085"),
    ("raw control in the file", b"a: x\x01y\n", 1, 5, "U+0001"),
    ("raw control in a comment", b"a: 1 # x\x02\n", 1, 9, "U+0002"),
    ("invisible key", b"a\xe2\x80\x8b: 1\n", 1, 2, "U+200B"),
    ("not NFC", b'a: "e\xcc\x81"\n', 1, 4, "not in Unicode NFC"),
    ("not NFC key", b"e\xcc\x81: 1\n", 1, 1, "not in Unicode NFC"),
    # Line breaks PyYAML would normalize before any value is seen: refused in the source.
    ("lone CR in a quoted value", b'a: "x\ry"\n', 1, 6, "a lone CR"),
    ("lone CR in a block scalar", b"a: |\n  x\ry\n", 2, 4, "a lone CR"),
    ("CR line endings", b"a: x\rb: y\r", 1, 5, "a lone CR"),
    ("NEL in a quoted value", b'a: "x\xc2\x85  y"\n', 1, 6, "U+0085"),
    ("NEL in a block scalar", b"a: |\n  x\xc2\x85y\n", 2, 4, "U+0085"),
    ("NEL as a line ending", b"a: x\xc2\x85b: y\n", 1, 5, "U+0085"),
    # Default-ignorable code points that are not format characters, and the blank Braille cell.
    ("combining grapheme joiner", b"a: OSC_FREQ\xcd\x8f\n", 1, 12, "U+034F"),
    ("variation selector", b"a: x\xef\xb8\x8fy\n", 1, 5, "U+FE0F"),
    ("Hangul filler", b"a: x\xe3\x85\xa4y\n", 1, 5, "U+3164"),
    ("Hangul choseong filler", b"a: x\xe1\x85\x9fy\n", 1, 5, "U+115F"),
    ("Mongolian selector", b"a: x\xe1\xa0\x8by\n", 1, 5, "U+180B"),
    ("blank Braille pattern", b"a: x\xe2\xa0\x80y\n", 1, 5, "U+2800"),
    ("tag character", b"a: x\xf3\xa0\x80\x81y\n", 1, 5, "U+E0001"),
    ("escaped grapheme joiner", b'a: "x\\u034fy"\n', 1, 4, "U+034F"),
    # Invisible characters in comments, too.
    ("zero-width space in a comment", b"a: 1 # x\xe2\x80\x8by\n", 1, 9, "U+200B"),
    ("bidi override in a comment", b"# \xe2\x80\xaeabc\na: 1\n", 1, 3, "U+202E"),
    # Positions count characters and LF or CRLF lines.
    ("CRLF, second line", b"a: x\r\nb: y\xe2\x80\x8bz\r\n", 2, 5, "U+200B"),
    ("after a two-byte character", b"a: \xc3\xa9\xe2\x80\x8b\n", 1, 5, "U+200B"),
    # Malformed scalars.
    ("escape beyond Unicode", b'a: "\\U00110000"\n', 1, 7, "a malformed scalar"),
    ("a huge integer", b"a: " + b"9" * 4400 + b"\n", 1, 4, "64-bit"),
    ("a 20-digit integer", b"a: 12345678901234567890\n", 1, 4, "64-bit"),
    ("just past 64 bits", b"a: 9223372036854775808\n", 1, 4, "64-bit"),
    ("just below -64 bits", b"a: -9223372036854775809\n", 1, 4, "64-bit"),
    # Any directive, reserved ones included.
    ("reserved directive", b"%FOO bar\n---\na: 1\n", 1, 1, "a %FOO directive"),
    # Byte-order mark, non-UTF-8.
    ("UTF-8 BOM", b"\xef\xbb\xbfa: 1\n", 1, 1, "a byte-order mark"),
    ("UTF-16 BOM", b"\xff\xfea\x00:\x00 \x001\x00\n\x00", 1, 1, "a byte-order mark"),
    ("Latin-1 byte", b"a: 1\nb: caf\xe9\n", 2, 7, "not UTF-8"),
    ("bad byte after a two-byte character", b'a: "\xc3\xa9\xff"\n', 1, 6, "not UTF-8"),
    ("truncated sequence", b"a: \xe2\x80\n", 1, 4, "not UTF-8"),
    ("overlong encoding", b"a: \xc0\xaf\n", 1, 4, "not UTF-8"),
    ("surrogate escape", b'a: "\\ud800"\n', 1, 4, "U+D800"),
    # Syntax: still a line and column.
    ("bad indentation", b"a:\n  b: 1\n c: 2\n", 3, 2, ""),
    ("unclosed flow", b"a: [1, 2\n", 2, 1, ""),
    ("deep nesting", b"a: " + b"[" * 5000 + b"]" * 5000 + b"\n", 1, 1, "nesting too deep"),
]


def write(tmp: pathlib.Path, label: str, data: bytes) -> pathlib.Path:
    path = tmp / (label.replace(" ", "-").replace(",", "") + ".yaml")
    path.write_bytes(data)
    return path


class FailingInputs(unittest.TestCase):
    def test_each_pitfall_fails_with_line_and_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            for label, data, line, column, problem in FAILING:
                with self.subTest(label):
                    path = write(pathlib.Path(tmp), label, data)
                    with self.assertRaises(specload.LoadError) as ctx:
                        specload.load_strict(path)
                    err = ctx.exception
                    self.assertIn(problem, err.problem)
                    self.assertEqual((err.line, err.column), (line, column), str(err))
                    self.assertTrue(str(err).startswith(f"{path}:{line}:{column}: "))


class Resolution(unittest.TestCase):
    """D6: only true, false, null and decimal integers are not strings."""

    def load(self, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "x.yaml"
            path.write_text(text, encoding="utf-8")
            return specload.load_strict(path)

    def test_plain_scalars(self):
        data = self.load(
            "a: [no, yes, on, off, y, n, True, FALSE, Null, NULL, ~]\n"
            "b: [012, 0o12, 0x7E20_1000, 1_000, +1, -0, 1e3, .inf, .nan, 1.10, 1:20]\n"
            "c: [2026-10-08, 2026-10-08T12:00:00Z]\n"
            "d: [true, false, null, 0, 7, -7, 9223372036854775807, -9223372036854775808]\n"
            "e: ['true', \"null\", '7']\n"
            "f: |\n  7\n"
        )
        self.assertEqual(data["a"], ["no", "yes", "on", "off", "y", "n", "True", "FALSE",
                                     "Null", "NULL", "~"])
        self.assertEqual(data["b"], ["012", "0o12", "0x7E20_1000", "1_000", "+1", "-0", "1e3",
                                     ".inf", ".nan", "1.10", "1:20"])
        self.assertEqual(data["c"], ["2026-10-08", "2026-10-08T12:00:00Z"])
        self.assertEqual(data["d"], [True, False, None, 0, 7, -7, 2**63 - 1, -(2**63)])
        self.assertEqual(data["e"], ["true", "null", "7"])
        self.assertEqual(data["f"], "7\n")
        for value in data["d"]:
            self.assertIn(type(value), (bool, type(None), int))

    def test_block_scalars_stay_strings(self):
        data = self.load("a: |-\n  true\nb: >-\n  7\nc: |-\n  null\n")
        self.assertEqual(data, {"a": "true", "b": "7", "c": "null"})

    def test_tab_and_crlf_are_allowed_outside_values(self):
        data = self.load("a: 1 # a\ttab in a comment\r\nb: 2\r\n")
        self.assertEqual(data, {"a": 1, "b": 2})

    def test_keys_that_look_typed_are_strings_when_plain_words(self):
        data = self.load("no: 1\non: 2\nyes: 3\n'1': 4\n")
        self.assertEqual(list(data), ["no", "on", "yes", "1"])

    def test_allowed_text(self):
        data = self.load(
            "a: \"en dash \u2013, \u00e9, \u4e2d\"\n"
            "b: |\n  line one\n  line two\n"
            "c: >-\n  folded\n  text\n"
        )
        self.assertEqual(data["a"], "en dash \u2013, \u00e9, \u4e2d")
        self.assertEqual(data["b"], "line one\nline two\n")
        self.assertEqual(data["c"], "folded text")

    def test_explicit_document_markers_are_layout(self):
        self.assertEqual(self.load("---\na: 1\n...\n"), {"a": 1})

    def test_crlf_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "x.yaml"
            path.write_bytes(b"a: x\r\nb: |\r\n  y\r\n")
            self.assertEqual(specload.load_strict(path), {"a": "x", "b": "y\n"})


class Marks(unittest.TestCase):
    def test_values_and_keys_have_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "x.yaml"
            path.write_text("a:\n  - b: 1\n    c: [x, y]\n", encoding="utf-8")
            loaded = specload.load_strict_marked(path)
        self.assertEqual(loaded.mark(("a", 0, "c", 1)), specload.Mark(3, 12))
        self.assertEqual(loaded.mark(("a", 0, "c"), key=True), specload.Mark(3, 5))
        self.assertEqual(loaded.mark(("a", 0, "missing")), specload.Mark(2, 5))


if __name__ == "__main__":
    unittest.main()
