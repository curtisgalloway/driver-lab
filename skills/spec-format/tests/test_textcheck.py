# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""CommonMark safety fixtures, field selection, and checker integration (SF2-4)."""

import dataclasses
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import specmd
import textcheck
from test_check import check, chip, marker


class Safety(unittest.TestCase):
    def test_fixtures(self):
        cases = json.loads((HERE / "fixtures/textcheck/cases.json").read_text())
        for case in cases:
            with self.subTest(case=case["name"]):
                found = specmd.findings(case["text"])
                self.assertEqual([[f.line, f.kind] for f in found], case["findings"])
                for finding in found:
                    self.assertEqual(set(dataclasses.asdict(finding)),
                                     {"line", "kind", "message", "level"})
                    self.assertEqual(finding.level, "error")

    def test_lint_aliases_and_no_provenance_result(self):
        for text in ("[databook]", "[DATAbOok]", "[src:r: f.c:1 (x)]",
                     "&#91;src:r]", "[da*ta*book]"):
            with self.subTest(text=text):
                self.assertEqual([f.kind for f in specmd.findings(text, lint=True)], ["v1-tag"])
                self.assertEqual(specmd.findings(text), [])
        for text in ("", " ", "[ ]", "[]", "[databookish]", "`[databook]`",
                     "```\n[src:x]\n```", "    [databook]"):
            self.assertEqual(specmd.findings(text, lint=True), [])

    def test_line_after_inline_break(self):
        self.assertEqual([(f.line, f.kind) for f in specmd.findings("first\n<b>x</b>")],
                         [(2, "html"), (2, "html")])
        cases = [
            ("`code\nspan` <b>x</b>", [(2, "html"), (2, "html")]),
            ("&#10; <b>x</b>", [(1, "html"), (1, "html")]),
            ("first\n[x](javascript:x)", [(2, "link")]),
            ("first\n![text\n<b>](https://example.invalid/x)", [(3, "html")]),
            ("[text\n<b>](https://example.invalid/x)", [(2, "html")]),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual([(f.line, f.kind) for f in specmd.findings(text)], expected)

    def test_every_author_field_and_notice_exemption(self):
        data = {"orientation": "# bad", "facts": [{"title": "# bad", "claim": "# bad",
                "note": "# bad", "support": [{"note": "# bad", "title": "# bad"}]}],
                "resources": {"documents": [{"title": "# bad", "note": "# bad"}],
                              "repos": [{"files": [{"note": "# bad"}]}]},
                "instances": [{"note": "# bad", "irq": {"note": "# bad"}}],
                "notices": [{"text": "<script>", "title": "# exempt"}],
                "todo": {"text": "# generated"}, "milestones": "# bad", "notes": "# bad"}
        selected = list(textcheck.fields(data))
        self.assertEqual(len(selected), 13)
        self.assertTrue(all(value == "# bad" for _, value, _ in selected))
        self.assertFalse(any(path[0] in ("notices", "todo") for path, _, _ in selected))


class Integration(unittest.TestCase):
    def test_check_reports_fact_field_and_decoded_line(self):
        for field in ("claim", "title", "note", "orientation", "resource-title", "resource-note",
                      "support-note"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                data = yaml.safe_load(chip())
                if field == "orientation":
                    data[field] = "# bad"
                elif field.startswith("resource-"):
                    data["resources"]["documents"][0][field.split("-")[1]] = "# bad"
                elif field == "support-note":
                    data["facts"][0]["support"][0]["note"] = "# bad"
                else:
                    data["facts"][0][field] = "# bad"
                (root / "board-specs.yaml").write_text(marker())
                (root / "widgetchip.spec.yaml").write_text(yaml.safe_dump(data))
                code, result = check(root)
                self.assertEqual(code, 1)
                found = [f for f in result["findings"] if "heading inside a field" in f["message"]]
                self.assertEqual(len(found), 1)
                self.assertGreater(found[0]["line"], 0)
                self.assertIn("field line 1", found[0]["message"])
                if field in ("claim", "title", "note", "support-note"):
                    self.assertIn("fact 'reset'", found[0]["message"])

    def test_lint_is_warning_and_not_a_citation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "board-specs.yaml").write_text(marker())
            (root / "widgetchip.spec.yaml").write_text(chip().replace("C reset.", '"[src:fake]"'))
            code, result = check(root)
            self.assertEqual(code, 0)
            tags = [f for f in result["findings"] if "format 1 tag" in f["message"]]
            self.assertEqual(len(tags), 1)
            self.assertEqual(tags[0]["level"], "warning")


if __name__ == "__main__":
    unittest.main()
