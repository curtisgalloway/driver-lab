# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Round-1 regressions: each test fails by assertion on the original SF2-4 export."""

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from test_check import check, chip, fact, inference, marker
from test_render_md import HERE, PARSER, checked, run
import render_md
import specload
import specmd


class ReviewRound1(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "board-specs.yaml").write_text(marker("root_name"))
        self.path = self.root / "widget_chip.spec.yaml"
        self.path.write_text(chip())

    def write(self, data):
        self.path.write_text(yaml.safe_dump(data, sort_keys=False))

    def test_reference_definitions_in_every_author_field(self):
        for destination in ("javascript:alert(document.domain)", "relative/file", "data:image/svg+xml,x"):
            for location in ("claim", "title", "note", "orientation", "support", "resource"):
                with self.subTest(destination=destination, location=location):
                    data = yaml.safe_load(chip(facts=fact("a") + fact("b")))
                    data["facts"][0]["claim"] = "See [the manual] and ![badge][the manual]."
                    definition = "[the manual]: " + destination
                    if location == "orientation":
                        data[location] = definition
                    elif location == "support":
                        data["facts"][1]["support"][0]["note"] = definition
                    elif location == "resource":
                        data["resources"]["documents"][0]["note"] = definition
                    else:
                        data["facts"][1][location] = definition
                    self.write(data)
                    code, result = check(self.root)
                    self.assertEqual(code, 1)
                    self.assertTrue(any("link reference definition" in f["message"] for f in result["findings"]))
                    code, out, err = run(self.root, "--format", "md", "--json")
                    self.assertEqual((code, err), (1, ""))
                    self.assertIsNone(json.loads(out)["markdown"])
        for text in ("[x]: https://example.invalid", "> [x]: #a", "- [x]: #a",
                     "[x]: #a\n[x]: #b"):
            self.assertTrue(any(f.kind == "reference" for f in specmd.findings(text)))
        for text in ("`[x]: #a`", "```\n[x]: #a\n```", "    [x]: #a"):
            self.assertEqual(specmd.findings(text), [])

    def test_assembled_view_rejects_unplaced_constructs_without_output(self):
        for text in ("[injected](https://example.invalid)", "![injected](#a)",
                     "<script>x</script>", "\n\n## injected", "\n\n[x]: #a"):
            with self.subTest(text=text), patch.object(render_md, "_citation", return_value=text):
                code, out, err = run(self.root, "--format", "md", "--json")
                self.assertEqual((code, err), (1, ""))
                self.assertIsNone(json.loads(out)["markdown"])
                self.assertIn("assembled Markdown containment", out)

    def test_notes_follow_complete_provenance_and_never_absorb_items(self):
        for case in ("note-list-absorbs-premise", "toplevel-note-list-absorbs", "states-leading-spaces"):
            with self.subTest(case=case):
                data = yaml.safe_load(chip(facts=fact("p") + inference("q", "#p")))
                entry = data["facts"][1]
                support = entry["support"][0]
                entry["critical"] = True
                entry["todo"] = {"check": "hardware", "text": "generated TODO"}
                nested = copy.deepcopy(data["facts"][0]["support"])
                nested[0]["note"] = "- author item"
                support["premises"].insert(0, {"states": "     *starred* text", "support": nested})
                if case == "toplevel-note-list-absorbs":
                    entry["support"] = copy.deepcopy(data["facts"][0]["support"])
                    entry["support"][0]["note"] = "- author item"
                    entry["support"].append(copy.deepcopy(data["facts"][0]["support"][0]))
                    entry["support"][1]["at"] = [{"section": "2"}]
                self.write(data)
                code, out, err = run(self.root, "--format", "md")
                self.assertEqual((code, err), (0, ""))
                self.assertIn("- author item", out)
                status_code, status_out, status_err = run(self.root, "--format", "md", "--with-status")
                self.assertEqual((status_code, status_err), (0, ""))
                self.assertIn("- author item", status_out)
                self.assertLess(out.index("widgetchip@root_name#q"), out.index("- author item"))
                self.assertIn("bring-up critical", out)
                tokens = PARSER.parse(out)
                stack, generated, author = [], [], []
                for token in tokens:
                    if token.nesting == -1:
                        stack.pop()
                    elif token.nesting == 1:
                        stack.append(token.type)
                    elif token.type == "inline":
                        visible = "".join(c.content for c in token.children)
                        if "author item" in visible:
                            author.append(tuple(stack))
                        elif any(s in visible for s in ("databook:", "widgetchip@root_name#", "derivation:",
                                                       "generated TODO", "starred", "inference, from:")):
                            generated.append((visible, tuple(stack)))
                self.assertEqual(author, [("bullet_list_open", "list_item_open", "paragraph_open")])
                for visible, parents in generated:
                    self.assertEqual(parents[-2:], ("list_item_open", "paragraph_open"), visible)
                    self.assertNotIn("blockquote_open", parents)
                    if any(s in visible for s in ("derivation:", "generated TODO", "#q")):
                        self.assertEqual(parents, ("bullet_list_open", "list_item_open", "paragraph_open"), visible)
                self.assertTrue(any("generated TODO" in t for t, _ in generated))
                if case != "toplevel-note-list-absorbs":
                    self.assertTrue(any("starred" in t and p.count("list_item_open") == 2 for t, p in generated))
                    self.assertTrue(any("#p" in t and p.count("list_item_open") == 2 for t, p in generated))
                    self.assertFalse(any(t.type == "code_block" for t in tokens))

    def test_commits_are_explicit_and_no_subprocess_runs(self):
        source, tool = "1" * 40, "a" * 40
        with patch.object(subprocess, "run", return_value=type("Result", (), {
                "returncode": 0, "stdout": "b" * 40})()) as spawned:
            code, out, err = run(self.root, "--format", "md")
        self.assertEqual((code, err), (0, ""))
        spawned.assert_not_called()
        self.assertIn("commit unavailable", out)
        self.assertIn("driver-lab unavailable", out)
        code, out, err = run(self.root, "--format", "md", "--source-commit", source, "--tool-commit", tool)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("commit " + source, out)
        self.assertIn("driver-lab " + tool, out)
        for flag in ("--source-commit", "--tool-commit"):
            for value in ("", " ", "#", "A" * 40, "a" * 39, "a" * 41, "a" * 40 + "\n", "g" * 40):
                with self.subTest(flag=flag, value=value):
                    code, out, err = run(self.root, "--format", "md", "--json", flag, value)
                    self.assertEqual((code, err), (2, ""))
                    self.assertEqual(json.loads(out)["error"], "usage")

    def test_banner_hash_uses_checked_bytes_without_second_read(self):
        original = self.path.read_bytes()
        checker = checked(self.root)
        self.path.write_text(chip().replace("C reset.", "Changed after checking."))
        with patch.object(Path, "read_bytes", return_value=b"second read") as reader:
            out = render_md.render(checker)
        reader.assert_not_called()
        self.assertIn(hashlib.sha256(original).hexdigest(), out)
        self.assertIn("C reset.", out)
        self.assertNotIn("Changed after checking", out)

    def test_forbidden_filename_categories_spec_record_and_root(self):
        names = ("widget\x1b]52;c;Zg==\x07", "bad\u200b", "bad\u2028", "bad\u2029",
                 "bad\ue000", "bad\u0378")
        for name in names:
            with self.subTest(name=name):
                target = self.root / (name + ".spec.yaml")
                self.path.rename(target)
                try:
                    code, result = check(self.root)
                    self.assertEqual(code, 1)
                    self.assertTrue(any("forbidden Unicode" in f["message"] for f in result["findings"]))
                finally:
                    target.rename(self.path)
        resources = self.root / "resources"
        resources.mkdir()
        target = resources / (names[0] + ".verify.yaml")
        target.write_text("not a valid record")
        code, result = check(self.root)
        self.assertEqual(code, 1)
        self.assertTrue(any("forbidden Unicode" in f["message"] for f in result["findings"]))
        target.unlink()
        badroot = self.root / names[0]
        badroot.mkdir()
        (badroot / "board-specs.yaml").write_text(marker())
        code, result = check(badroot)
        self.assertEqual(code, 1)
        self.assertTrue(any("forbidden Unicode" in f["message"] for f in result["findings"]))
        for value in (*names, "bad\ud800"):
            self.assertNotEqual(render_md.code(value), "`" + value + "`")
            self.assertFalse(any(c in render_md.code(value) for c in ("\x1b", "\x07", "\u200b", "\ud800")))
        with patch.object(Path, "read_bytes", return_value=self.path.read_bytes()), self.assertRaises(specload.LoadError):
            specload.load_strict_marked(self.root / "bad\ud800.spec.yaml")

    def test_verification_notes_checked_at_the_record_location(self):
        shutil.copytree(HERE / "fixtures/records/verify_root", self.root / "verify")
        root = self.root / "verify"
        path = root / "resources/vok.verify.yaml"
        original = specload.load_strict(path)
        for note, expected in (("<script>x</script>", "raw HTML"), ("# heading", "heading inside"),
                               ("[x](javascript:x)", "disallowed link"), ("```", "unclosed code"),
                               ("[x]: #a", "link reference definition")):
            with self.subTest(note=note):
                data = copy.deepcopy(original)
                key = next(iter(data["verdicts"]))
                data["verdicts"][key]["note"] = note
                path.write_text(yaml.safe_dump(data, sort_keys=False))
                code, result = check(root)
                self.assertEqual(code, 1)
                findings = [f for f in result["findings"] if expected in f["message"] and f["path"] == str(path)]
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0]["line"], specload.load_strict_marked(path).mark(("verdicts", key, "note")).line)

    def test_raw_html_one_construct_and_no_placeholder_overlap(self):
        data = yaml.safe_load(chip())
        data["facts"][0]["claim"] = "a <b>x</b>"
        self.write(data)
        code, result = check(self.root)
        self.assertEqual(code, 1)
        findings = [f for f in result["findings"] if f["level"] == "error"]
        self.assertEqual(len(findings), 1)
        self.assertIn("raw HTML", findings[0]["message"])
        data["facts"][0]["claim"] = "a <bus> and \\<board name>"
        self.write(data)
        code, result = check(self.root)
        self.assertEqual(code, 1)
        findings = [f for f in result["findings"] if f["level"] == "error"]
        self.assertEqual(len(findings), 2)
        self.assertEqual(sum("raw HTML" in f["message"] for f in findings), 1)
        self.assertEqual(sum("placeholder" in f["message"] for f in findings), 1)

    def test_generated_leading_whitespace_cannot_create_code_blocks(self):
        for value in ("     *literal*", "\t[x](url)", "\n    - item", "   "):
            with self.subTest(value=value):
                escaped = render_md.escape(value)
                self.assertEqual(escaped, escaped.lstrip())
                self.assertFalse(any(t.type == "code_block" for t in PARSER.parse(escaped)))

    def test_instance_and_variant_notes_follow_generated_references(self):
        shutil.copytree(HERE / "fixtures/check/good_root", self.root / "board")
        root = self.root / "board"
        for sid, key in (("widgetsoc", "instances"), ("widgetboard", "variants")):
            with self.subTest(kind=key):
                path = root / (sid + ".spec.yaml")
                data = specload.load_strict(path)
                doc = data["resources"]["documents"][0]
                for row in data[key]:
                    row["support"] = [{"class": doc["class"], "doc": doc["name"],
                                       "at": [{"section": "1"}],
                                       "note": "- author note for " + row["id"]}]
                path.write_text(yaml.safe_dump(data, sort_keys=False))
                code, out, err = run(root, "--public-skill", "widget-board-tools", "--spec", sid, "--format", "md")
                self.assertEqual((code, err), (0, ""))
                self.assertIn("## " + key.capitalize(), out)
                for row in data[key]:
                    self.assertIn("author note for " + row["id"], out)
                    self.assertLess(out.index(sid + "@good#" + row["id"]),
                                    out.index("author note for " + row["id"]))


if __name__ == "__main__":
    unittest.main()
