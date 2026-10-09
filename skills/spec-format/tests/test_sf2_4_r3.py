# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Round-3 regressions; each method fails by assertion on pristine e2ed33f.

The 32-backtick cases are passing controls within methods that also reject 33, 80 and
255. Renderer assertions are exercised directly without turning CLI errors into kills.
"""

import shutil
from types import SimpleNamespace
import unittest

import yaml

from test_check import check, chip
from test_render_md import HERE, PARSER, run
import test_render_md as render_tests
import render_md
import specmd
import textcheck


BOUND_MESSAGE = "a run of more than 32 backticks"


class ReviewRound3(unittest.TestCase):
    setUp = render_tests.Views.setUp
    write = render_tests.Views.write

    def assert_bound(self, result, field):
        messages = [f["message"] for f in result["findings"] if BOUND_MESSAGE in f["message"]]
        self.assertEqual(len(messages), 1, result["findings"])
        self.assertIn(field, messages[0])

    def field_boundary(self, field):
        for length in (32, 33, 80, 255):
            with self.subTest(field=field, length=length):
                data = yaml.safe_load(chip())
                ticks = "`" * length
                data["facts"][0][field] = "before " + ticks + " **FORGED** www.example.com"
                self.write(data)
                code, result = check(self.root)
                self.assertEqual(code, 0 if length == 32 else 1)
                if length == 32:
                    code, out, err = run(self.root, "--format", "md")
                    self.assertEqual((code, err), (0, ""))
                    tokens = PARSER.parse(out)
                    delimiters = [t.markup for t in tokens if t.type == "fence"] + [
                        c.markup for t in tokens for c in t.children or [] if c.type == "code_inline"]
                    self.assertTrue(delimiters)
                    self.assertLessEqual(max(map(len, delimiters)), 33)
                    self.assertIn(data["facts"][0][field], out)
                else:
                    self.assert_bound(result, "facts[0]." + field)

    def test_claim_boundaries(self):
        self.field_boundary("claim")

    def test_note_boundaries(self):
        self.field_boundary("note")

    def test_title_boundaries(self):
        self.field_boundary("title")

    def test_every_author_path_and_notice_is_bounded(self):
        value = "before " + "`" * 33 + " after"
        data = {"orientation": value, "milestones": value, "notes": value,
                "facts": [{"claim": value, "title": value, "note": value,
                           "support": [{"note": value, "premises": [{"states": value}]}],
                           "conflicts": [{"note": value, "support": [{"note": value}]}]}],
                "resources": {"documents": [{"title": value, "note": value}],
                              "repos": [{"note": value, "files": [{"note": value}]}]},
                "instances": [{"note": value}], "variants": [{"note": value}],
                "notices": [{"text": value}]}
        messages = []
        checker = SimpleNamespace(add=lambda where, path, message, **kw: messages.append((path, message)))
        textcheck.check_data(checker, None, data)
        bounded = {path for path, message in messages if BOUND_MESSAGE in message}
        expected = {path for path, _, _ in textcheck.fields(data)} | {("notices", 0, "text")}
        self.assertEqual(bounded, expected)

    def test_generated_spec_values_are_bounded(self):
        paths = (("name",), ("triggers", 0), ("resources", "documents", 0, "revision"),
                 ("facts", 0, "support", 0, "at", 0, "section"),
                 ("facts", 0, "todo", "text"))
        for path in paths:
            with self.subTest(path=path):
                data = yaml.safe_load(chip())
                data["facts"][0]["todo"] = {"check": "hardware", "text": "Verify it"}
                target = data
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = "value " + "`" * 33 + " after"
                self.write(data)
                code, result = check(self.root)
                self.assertEqual(code, 1)
                self.assert_bound(result, str(path[-1]))

    def test_generated_mapping_keys_and_nested_values_are_bounded(self):
        value = "`" * 33
        messages = []
        checker = SimpleNamespace(add=lambda where, path, message, **kw: messages.append((path, message, kw)))
        data = {"support": [{"custom": {value: "ordinary", "nested": [value]}}]}
        textcheck.check_data(checker, None, data)
        bounded = [(path, kw.get("key")) for path, message, kw in messages if BOUND_MESSAGE in message]
        self.assertEqual(bounded, [(("support", 0, "custom", value), True),
                                   (("support", 0, "custom", "nested", 0), False)])

    def test_root_file_strings_are_bounded(self):
        path = self.root / "board-specs.yaml"
        data = yaml.safe_load(path.read_text())
        for length in (32, 33):
            with self.subTest(length=length):
                data["roots"] = ["child-" + "`" * length]
                path.write_text(yaml.safe_dump(data))
                code, result = check(self.root)
                self.assertEqual(code, 0 if length == 32 else 1)
                if length == 33:
                    self.assert_bound(result, "roots[0]")

    def test_source_path_is_bounded(self):
        for length in (32, 33):
            with self.subTest(length=length):
                directory = self.root / ("child-" + "`" * length)
                directory.mkdir()
                moved = directory / self.path.name
                self.path.rename(moved)
                try:
                    code, result = check(self.root)
                    self.assertEqual(code, 0 if length == 32 else 1)
                    if length == 33:
                        self.assert_bound(result, "source_path")
                finally:
                    moved.rename(self.path)
                    directory.rmdir()

    def test_record_note_boundaries(self):
        self.path.unlink()
        fixture = HERE / "fixtures/records/verify_root"
        shutil.copyfile(fixture / "vok.spec.yaml", self.root / "vok.spec.yaml")
        directory = self.root / "resources"
        directory.mkdir()
        record = yaml.safe_load((fixture / "resources/vok.verify.yaml").read_text())
        record["spec_sha256"] = "0" * 64
        for length in (32, 33, 80, 255):
            with self.subTest(length=length):
                record["verdicts"]["reset"]["note"] = "note " + "`" * length + " after"
                (directory / "vok.verify.yaml").write_text(yaml.safe_dump(record))
                code, result = check(self.root)
                self.assertEqual(code, 0 if length == 32 else 1)
                if length != 32:
                    self.assert_bound(result, "verdicts.reset.note")

    def test_renderer_asserts_span_limit(self):
        self.assertEqual(max(len(t.markup) for t in PARSER.parseInline(render_md.code("`" * 32))[0].children), 33)
        for length in (33, 80, 255):
            with self.subTest(length=length), self.assertRaisesRegex(AssertionError, "33 backticks"):
                render_md.code("`" * length)

    def test_renderer_asserts_fence_limit(self):
        out = render_md.View()
        out.author("`" * 32)
        self.assertEqual([len(t.markup) for t in PARSER.parse("\n".join(out)) if t.type == "fence"], [33])
        for length in (33, 80, 255):
            with self.subTest(length=length), self.assertRaisesRegex(AssertionError, "33 backticks"):
                render_md.View().author("`" * length)

    def test_plain_footnote_substring_in_claim_note_and_title(self):
        for value in ("[^*x*]\n\n[^*x*]: two words", "[^`x`]", "[^*x*]", "before [^",
                      "`[^x]`", "```\n[^x]: text\n```", "    [^x]: text", "\\[^x]"):
            for field in ("claim", "note", "title"):
                with self.subTest(value=value, field=field):
                    data = yaml.safe_load(chip())
                    data["facts"][0][field] = " ".join(value.split()) if field == "title" else value
                    self.write(data)
                    code, result = check(self.root)
                    self.assertEqual(code, 1)
                    self.assertTrue(any("footnote" in f["message"] and "facts[0]." + field in f["message"]
                                        for f in result["findings"]))

    def test_footnote_string_position_and_token_guards_remain(self):
        self.assertTrue(any(f.kind == "footnote" and f.line == 3
                            for f in specmd.findings("first\nsecond\n[^`x`]")))
        self.assertEqual(sum(f.kind == "footnote" for f in specmd.findings("[^x]")), 2)
        self.assertEqual(sum(f.kind == "footnote" for f in specmd.findings("[^x]: definition")), 2)
        self.assertTrue(any(f.kind == "footnote" for f in specmd.findings("&#91;^x]")))


if __name__ == "__main__":
    unittest.main()
