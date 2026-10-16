#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for `spec.py todo` (issue 112): the TODOs of the roots as a readback worklist.

Every root here is invented and built in a temporary directory. The command is a read-only view:
these tests also check that it leaves the exit status to the check, never to a missing method.

Run in the pinned environment:
  .venv-spec/bin/python -m unittest discover -s skills/spec-format/tests -v
"""

import contextlib
import io
import json
import pathlib
import shutil
import sys
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "spec.py"
sys.path.insert(0, str(SCRIPT.parent))
import spec as spec_cli  # noqa: E402
from test_check import HDR, TempRoots, chip, fact, marker  # noqa: E402

DOC = ('    - {name: trm, class: databook, title: Widget TRM, '
       'url: "https://example.invalid/trm.pdf", pages: 80}\n')


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec_cli.main(["todo", *[str(a) for a in argv]])
    return code, out.getvalue(), err.getvalue()


def todo(*argv):
    """(exit code, JSON result) of `spec.py todo --json ...`."""
    code, out, _ = run("--json", *argv)
    return code, json.loads(out)


def gap(fid, check, method=None, extra=""):
    line = f"    todo: {{check: {check}, text: Read {fid} back"
    line += f", method: {method}}}\n" if method else "}\n"
    return (f"  - id: {fid}\n    section: quick-facts\n    title: T {fid}\n"
            f"    claim: C {fid}.\n" + line + extra)


def by_fact(result):
    return {t["fact"].split("#")[-1]: t for t in result["todos"]}


SOC = (HDR + "format: 2\nkind: soc\nid: wsoc\nname: W\ntriggers: [wsoc]\n"
       "instances:\n  - {id: uart0, name: uart0, ip: wuart, reg: null, irq: null, clocks: [],\n"
       "     todo: {check: hardware, text: Find where uart0 sits., method: Probe the bus.}}\n"
       "  - {id: uart1, name: uart1, ip: wuart, reg: \"0x2000\", irq: {kind: SPI, number: 2},\n"
       "     clocks: [], support: [{class: databook, doc: trm, at: [{section: \"2\"}]}]}\n"
       "resources:\n  documents:\n" + DOC + "facts:\n"
       + gap("g-hw", "hardware", "Toggle the pin.",
             extra="    critical: true\n    scope: {boards: [alpha], modes: [fast]}\n")
       + gap("g-nomethod", "hardware")
       + gap("g-doc", "document")
       + fact("s-todo", extra="    todo: {check: source, text: Confirm the reset value.}\n")
       + fact("s-plain")
       + "assumptions:\n  - id: clk-on\n    text: The clock runs.\n"
       "    todo: {check: hardware, text: Measure the clock.}\n")
IP = (HDR + "format: 2\nkind: ip\nid: wuart\nname: U\ntriggers: [wuart]\n"
      "resources:\n  documents:\n" + DOC + "facts:\n" + fact("u", extra="").replace(
          "section: quick-facts", "section: programming-model"))


class WorklistTests(TempRoots):
    def setUp(self):
        super().setUp()
        self.r = self.root("r", {"board-specs.yaml": marker("r"), "s.spec.yaml": SOC,
                                 "u.spec.yaml": IP})

    def test_lists_gaps_and_supported_facts_with_a_todo(self):
        code, result = todo(self.r)
        self.assertEqual(code, 0, result["findings"])
        facts = by_fact(result)
        self.assertEqual(set(facts), {"g-hw", "g-nomethod", "g-doc", "s-todo", "uart0",
                                      "clk-on"})
        self.assertEqual(facts["g-hw"]["kind"], "gap")
        self.assertEqual(facts["s-todo"]["kind"], "supported-with-todo")
        self.assertEqual(facts["g-hw"]["fact"], "wsoc@r#g-hw")

    def test_item_fields(self):
        item = by_fact(todo(self.r)[1])["g-hw"]
        self.assertEqual(
            {k: item[k] for k in ("check", "text", "method", "critical", "scope", "instance")},
            {"check": "hardware", "text": "Read g-hw back", "method": "Toggle the pin.",
             "critical": True, "scope": {"boards": ["alpha"], "modes": ["fast"]},
             "instance": None})
        self.assertTrue(item["file"].endswith("s.spec.yaml"))
        self.assertEqual(item["spec"], "wsoc")
        self.assertNotIn("missing_method", item)
        plain = by_fact(todo(self.r)[1])["s-todo"]
        self.assertEqual((plain["method"], plain["critical"], plain["scope"]),
                         (None, False, None))

    def test_other_record_kinds_are_named(self):
        facts = by_fact(todo(self.r)[1])
        self.assertEqual(facts["uart0"]["kind"], "instance")
        self.assertEqual(facts["uart0"]["instance"], "uart0")
        self.assertEqual(facts["clk-on"]["kind"], "assumption")
        self.assertEqual(facts["clk-on"]["fact"], "wsoc@r#clk-on")

    def test_check_filter(self):
        for check, want in (("hardware", {"g-hw", "g-nomethod", "uart0", "clk-on"}),
                            ("document", {"g-doc"}), ("source", {"s-todo"})):
            code, result = todo(self.r, "--check", check)
            self.assertEqual(code, 0)
            self.assertEqual(set(by_fact(result)), want, check)
            self.assertEqual(result["counts"]["total"], len(want))
            self.assertEqual({t["check"] for t in result["todos"]}, {check})

    def test_hardware_todo_without_a_method_is_flagged_and_exit_stays_zero(self):
        code, result = todo(self.r, "--check", "hardware")
        self.assertEqual(code, 0)
        flagged = {t["fact"].split("#")[-1] for t in result["todos"] if t.get("missing_method")}
        self.assertEqual(flagged, {"g-nomethod", "clk-on"})
        self.assertEqual(result["counts"]["missing_method"], 2)
        for t in result["todos"]:
            if "missing_method" in t:
                self.assertIs(t["missing_method"], True)
        _, text, _ = run(self.r, "--check", "hardware")
        marked = [ln for ln in text.splitlines() if "(no method)" in ln]
        self.assertEqual(len(marked), 2, text)
        self.assertTrue(any("g-nomethod" in ln for ln in marked))
        self.assertNotIn("(no method)", [ln for ln in text.splitlines() if "g-hw" in ln][0])
        _, doc_text, _ = run(self.r, "--check", "document")
        self.assertNotIn("(no method)", doc_text)

    def test_json_shape(self):
        code, result = todo(self.r)
        self.assertEqual(code, 0)
        self.assertEqual(set(result), {"ok", "roots", "errors", "warnings", "todos", "counts",
                                       "findings"})
        self.assertIs(result["ok"], True)
        self.assertEqual(set(result["todos"][0]), {"fact", "file", "root", "spec", "kind",
                                                   "check", "text", "method", "critical",
                                                   "scope", "instance"})
        counts = result["counts"]
        self.assertEqual(counts["total"], 6)
        self.assertEqual(counts["by_check"], {"hardware": 4, "document": 1, "source": 1})
        self.assertEqual(counts["by_kind"]["gap"], 3)
        self.assertEqual(counts["by_kind"]["supported-with-todo"], 1)
        self.assertEqual((counts["by_kind"]["instance"], counts["by_kind"]["assumption"]),
                         (1, 1))
        self.assertEqual(counts["critical"], 1)
        self.assertEqual(sum(counts["by_kind"].values()), counts["total"])

    def test_no_todos_is_exit_zero(self):
        r = self.root("clean", {"board-specs.yaml": marker("c"),
                                "w.spec.yaml": chip(facts=fact("a"))})
        code, result = todo(r)
        self.assertEqual(code, 0)
        self.assertEqual(result["todos"], [])
        self.assertEqual(result["counts"]["total"], 0)
        code, text, _ = run(r)
        self.assertEqual((code, text.splitlines()[-1][:10]), (0, "0 TODO(s):"))

    def test_human_output_groups_by_file_then_instance(self):
        code, text, _ = run(self.r)
        self.assertEqual(code, 0)
        lines = text.splitlines()
        heads = [ln for ln in lines if not ln.startswith(" ") and "TODO(s)" in ln
                 and "(wsoc)" in ln]
        self.assertEqual(heads, ["r:s.spec.yaml (wsoc): 6 TODO(s)"])
        at = lines.index("  instance uart0:")
        self.assertIn("wsoc@r#uart0", lines[at + 1])
        self.assertTrue(lines[at + 1].startswith("    hardware"))
        self.assertTrue(all("g-hw" not in ln for ln in lines[at:at + 4]))
        self.assertIn("critical", [ln for ln in lines if "wsoc@r#g-hw" in ln][0])
        self.assertIn("scope: boards=alpha; modes=fast",
                      [ln for ln in lines if "wsoc@r#g-hw" in ln][0])
        self.assertIn("      method: Toggle the pin.", lines)

    def test_context_roots_are_not_listed(self):
        docs = self.root("docs", {"board-specs.yaml": marker("d"),
                                  "x.spec.yaml": chip("xchip", facts=gap("far", "hardware"))})
        code, result = todo(self.r, "--context-root", docs)
        self.assertEqual(code, 0, result["findings"])
        self.assertNotIn("far", by_fact(result))

    def test_payload_rows_with_a_todo_are_listed_under_their_fact(self):
        src = HERE / "fixtures" / "peripheral"
        r = self.tmp / "periph"
        r.mkdir()
        shutil.copy(src / "board-specs.yaml", r)
        text = (src / "widget.spec.yaml").read_text(encoding="utf-8")
        old = '{id: type, name: frame_type, offset: "0x0", size: 1, meaning: type byte}'
        self.assertIn(old, text)
        (r / "widget.spec.yaml").write_text(text.replace(
            old, old[:-1] + ", todo: {check: hardware, text: Capture a frame., "
            "method: Dump four bytes.}}"), encoding="utf-8")
        code, result = todo(r)
        self.assertEqual(code, 0, result["findings"])
        rows = [t for t in result["todos"] if t["kind"] == "layout-field"]
        self.assertEqual(len(rows), 1, result["todos"])
        self.assertTrue(rows[0]["fact"].endswith(".type"), rows[0]["fact"])
        self.assertEqual(rows[0]["method"], "Dump four bytes.")
        self.assertEqual(result["counts"]["by_kind"]["layout-field"], 1)

    def test_atlas_and_explorer_carry_the_row_todos_that_the_worklist_lists(self):
        import atlas
        import explorer

        src = HERE / "fixtures" / "peripheral"
        r = self.tmp / "views"
        r.mkdir()
        shutil.copy(src / "board-specs.yaml", r)
        text = (src / "widget.spec.yaml").read_text(encoding="utf-8")
        edits = {
            "          meaning: block enable\n":
                "          meaning: block enable\n"
                "          todo: {check: hardware, text: Read it back., method: Toggle it.}\n",
            "{id: s2, action: write the divisor to BAUD}":
                "{id: s2, action: write the divisor to BAUD, "
                "todo: {check: source, text: Confirm the step.}}",
            "            requirement: comment-explained\n":
                "            requirement: comment-explained\n"
                "            todo: {check: document, text: Read the order.}\n",
        }
        for old, new in edits.items():
            self.assertEqual(text.count(old), 1, old)
            text = text.replace(old, new)
        (r / "widget.spec.yaml").write_text(text, encoding="utf-8")
        code, result = todo(r)
        self.assertEqual(code, 0, result["findings"])
        row_kinds = {"field", "layout-field", "step", "order"}
        expected = sorted((t["fact"], t["kind"], t["check"], t["text"], t["method"] or "")
                          for t in result["todos"] if t["kind"] in row_kinds)
        self.assertEqual(len(expected), 3, result["todos"])

        args = types.SimpleNamespace(roots=[r], context_root=[], require_license=False,
                                           public_skill=[])
        checker = spec_cli._run_check(args)
        flat = lambda facts: sorted(
            (t["fact"], t["kind"], t["check"], t["text"], t["method"])
            for f in facts for t in f["row_todos"])
        spec_id = next(f.spec_id for f in checker.files)
        atlas_facts = atlas.data(checker, spec_id)["facts"]
        self.assertEqual(flat(atlas_facts), expected)
        explorer_facts = [f for s in explorer.data(checker, {}, []) for f in s["facts"]]
        shown = sorted(
            [(t["fact"], t["kind"], t["check"], t["text"], t["method"])
             for f in explorer_facts for t in f["row_todos"]]
            + [(f["ref"], "", f["todo"]["check"], f["todo"]["text"], "")
               for f in explorer_facts if f["todo"] and "." in f["ref"].split("#")[-1]])
        self.assertEqual([(x[0], x[2], x[3]) for x in shown],
                         [(x[0], x[2], x[3]) for x in expected])

    def test_every_payload_row_kind_is_listed_once_under_its_parent(self):
        src = HERE / "fixtures" / "peripheral"
        r = self.tmp / "rows"
        r.mkdir()
        shutil.copy(src / "board-specs.yaml", r)
        text = (src / "widget.spec.yaml").read_text(encoding="utf-8")
        todo_of = ", todo: {check: hardware, text: Read it back.}"
        edits = {
            "          meaning: block enable\n":
                "          meaning: block enable\n"
                "          todo: {check: hardware, text: Read it back., method: Toggle it.}\n",
            "meaning: 8N1 format}": "meaning: 8N1 format" + todo_of + "}",
            "            action: write 0 to CTRL\n":
                "            action: write 0 to CTRL\n"
                "            todo: {check: source, text: Read it back.}\n",
            "{id: s2, action: write the divisor to BAUD}":
                "{id: s2, action: write the divisor to BAUD" + todo_of + "}",
            "            requirement: comment-explained\n":
                "            requirement: comment-explained\n"
                "            todo: {check: document, text: Read it back.}\n",
        }
        for old, new in edits.items():
            self.assertEqual(text.count(old), 1, old)
            text = text.replace(old, new)
        (r / "widget.spec.yaml").write_text(text, encoding="utf-8")
        code, result = todo(r)
        self.assertEqual(code, 0, result["findings"])
        got = sorted((t["fact"].split("#")[-1], t["kind"]) for t in result["todos"])
        self.assertEqual(got, [
            ("baud-latch-test", "gap"),
            ("reg-ctrl.en", "field"),
            ("reg-lcr.format", "field"),
            ("seq-init.order[0]", "order"),
            ("seq-init.s1", "step"),
            ("seq-init.s2", "step"),
        ])
        by_ref = {t["fact"].split("#")[-1]: t for t in result["todos"]}
        self.assertEqual(by_ref["reg-ctrl.en"]["method"], "Toggle it.")
        self.assertEqual(by_ref["seq-init.s1"]["check"], "source")

    def test_variant_rows_are_listed_as_variants(self):
        board = (HDR + "format: 2\nkind: board\nid: wboard\nname: W\ntriggers: [wboard]\n"
                 "parts: [wsoc]\ncache: c1\n"
                 "variants:\n  - id: v1\n    name: V1\n    triggers: [wv1]\n"
                 "    shares: [all]\n    differs: x\n"
                 "    todo: {check: hardware, text: Compare the variants.}\n"
                 "resources:\n  documents:\n" + DOC + "facts:\n" + fact("b"))
        r = self.root("withboard", {"board-specs.yaml": marker("r"), "s.spec.yaml": SOC,
                                    "u.spec.yaml": IP, "b.spec.yaml": board})
        code, result = todo(r)
        self.assertEqual(code, 0, result["findings"])
        v1 = by_fact(result)["v1"]
        self.assertEqual((v1["kind"], v1["instance"], v1["fact"]),
                         ("variant", None, "wboard@r#v1"))
        self.assertEqual(result["counts"]["by_kind"]["variant"], 1)

    def test_missing_dependency_exits_three_with_failure_json(self):
        from unittest import mock

        out = io.StringIO()
        with mock.patch.object(spec_cli, "check_dependencies", return_value=["pyyaml missing"]):
            with contextlib.redirect_stdout(out):
                code = spec_cli.main(["todo", "--json", str(self.r)])
        self.assertEqual(code, 3)
        failure = json.loads(out.getvalue())
        self.assertEqual((failure["ok"], failure["error"], failure["todos"]),
                         (False, "precondition", []))

    def test_invalid_root_exits_one_and_still_prints(self):
        bad = self.root("bad", {"board-specs.yaml": marker("b"),
                                "w.spec.yaml": chip(facts=gap("g", "hardware")),
                                "z.spec.yaml": chip(facts=fact("z") + fact("z"))})
        code, result = todo(bad)
        self.assertEqual(code, 1)
        self.assertIs(result["ok"], False)
        self.assertGreater(result["errors"], 0)
        self.assertTrue(any(f["level"] == "error" for f in result["findings"]))
        code, text, _ = run(bad)
        self.assertEqual(code, 1)
        self.assertIn("error", text)

    def test_malformed_todo_is_a_schema_error_not_a_listing(self):
        bad = self.root("bad2", {"board-specs.yaml": marker("b"),
                                 "w.spec.yaml": chip(facts=gap("g", "bogus"))})
        code, result = todo(bad)
        self.assertEqual(code, 1)
        self.assertEqual(result["todos"], [])

    def test_usage_errors_exit_two(self):
        code, _, _ = run(self.tmp / "nope")
        self.assertEqual(code, 2)
        code, out, _ = run("--json", self.tmp / "nope")
        self.assertEqual(code, 2)
        failure = json.loads(out)
        self.assertEqual((failure["ok"], failure["error"], failure["todos"]),
                         (False, "usage", []))
        with contextlib.redirect_stderr(io.StringIO()):
            code = spec_cli.main(["todo", "--check", "bogus", str(self.r)])
        self.assertEqual(code, 2)

    def test_skill_usage_documents_todo(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(spec_cli.main(["--skill"]), 0)
        text = out.getvalue()
        self.assertIn("spec.py todo <root>...", text)
        self.assertIn("--check hardware|document|source", text)
        self.assertIn("(no method)", text)


if __name__ == "__main__":
    unittest.main()
