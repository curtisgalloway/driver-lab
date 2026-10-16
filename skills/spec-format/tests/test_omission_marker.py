# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""The omission marker (issue 106): a `todo` with `check: document` on a supported record.

A fact or payload row that summarizes its locator says what it left out with a document TODO.
These tests pin what the contract and board-expert rely on: a claimed, supported fact may carry
one, both views render it beside the record (a payload row's too) and in the open questions,
and `spec.py todo --check document` lists it. The widget fixture is invented.

Run in the pinned environment:
  .venv-spec/bin/python -m unittest discover -s skills/spec-format/tests -v
"""

from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import render_html  # noqa: E402
import render_md  # noqa: E402
from test_spec_format_7a import Fixture, run  # noqa: E402

SKILLS = HERE.parents[1]
FACT_TEXT = "Divisor rounding rule (TRM table 7-3, p. 41) not extracted."
ROW_TEXT = "Per-bit enable encodings (TRM table 4-2, p. 22) not extracted."


class OmissionMarker(Fixture):
    def setUp(self):
        super().setUp()
        facts = {f["id"]: f for f in self.data["facts"]}
        self.claimed = facts["seq-init"]
        self.assertIn("claim", self.claimed)
        self.assertIn("support", self.claimed)
        self.claimed["todo"] = {"check": "document", "text": FACT_TEXT}
        self.row = facts["reg-ctrl"]["data"]["fields"][0]
        self.assertIn("support", self.row)
        self.row["todo"] = {"check": "document", "text": ROW_TEXT}
        self.write()

    def test_supported_records_with_a_document_todo_check_clean(self):
        self.assertEqual(run("validate", self.file)[0], 0)
        code, result = self.check()
        self.assertEqual(code, 0, result)

    def test_markdown_renders_both_markers_beside_their_records(self):
        view = render_md.render(self.checker())
        for text in (FACT_TEXT, ROW_TEXT):
            line = "- TODO (verify on document): " + render_md.escape(text)
            self.assertEqual(view.count(line), 1, text)
        row_entry = view.index("Payload entry " + render_md.code("reg-ctrl.en"))
        row_todo = view.index(render_md.escape(ROW_TEXT), row_entry)
        self.assertLess(row_todo, view.index("####", row_entry))
        claim = view.index("Clear CTRL, write BAUD")
        fact_todo = view.index(render_md.escape(FACT_TEXT), claim)
        self.assertLess(fact_todo, view.index("####", claim))

    def test_html_renders_both_markers_as_todo_badges(self):
        view = render_html.render(self.checker())
        self.assertEqual(view.count(render_html.badge("todo", "verify on document")), 2)
        for text in (FACT_TEXT, ROW_TEXT):
            self.assertIn("<p>" + render_html.literal(text) + "</p>", view)
        self.assertNotIn("<th>todo</th>", view)
        self.assertNotIn("&quot;check&quot;", view)

    def test_open_questions_and_worklist_list_both(self):
        code, result = run("todo", self.root, "--check", "document")
        self.assertEqual(code, 0, result)
        kinds = {t["fact"].split("#")[-1]: t["kind"] for t in result["todos"]}
        self.assertEqual(kinds, {"seq-init": "supported-with-todo", "reg-ctrl.en": "field"})
        view = render_md.render(self.checker())
        section = view[view.index(render_md.escape("Open questions (generated)")):]
        for text in (FACT_TEXT, ROW_TEXT):
            self.assertIn(render_md.escape(text), section)


class Guidance(unittest.TestCase):
    def test_contract_defines_the_marker(self):
        text = " ".join((SKILLS / "spec-format" / "SKILL.md").read_text().split())
        self.assertIn("Mark omissions with a document TODO.", text)
        self.assertIn("It is not a completeness claim", text)

    def test_board_expert_says_when_to_open_the_locator(self):
        text = " ".join((SKILLS / "board-expert" / "SKILL.md").read_text().split())
        self.assertIn("Answer from the spec when the value asked for is in a fact's claim", text)
        self.assertIn("A missing omission marker is not proof of completeness", text)


if __name__ == "__main__":
    unittest.main()
