# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Markdown reading views, escaping and containment (SF2-4).

The design's worked-example slices intentionally omit sources and one premise. The test
adds explicitly synthetic omissions in temporary copies; no fact or source in the archive
is changed. Zero basis hashes in the sample record correctly render stale, not current.
"""

import contextlib
import copy
import io
import json
import re
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from markdown_it import MarkdownIt
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import render_md
import spec
import speccheck
import specload
from test_check import chip, marker, fact, inference, repo, src_fact

PARSER = MarkdownIt("commonmark").enable("table")


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec.main(["render", *map(str, args)])
    return code, out.getvalue(), err.getvalue()


def checked(*roots, context=()):
    args = SimpleNamespace(roots=list(roots), context_root=list(context),
                           require_license=False, public_skill=[])
    return spec._run_check(args)


class Escaping(unittest.TestCase):
    def test_resources_table_values_and_labels_are_literal(self):
        value = '*bold* _path_ | [x](url) &amp; <tag> `ticks`'
        out = render_md.View()
        render_md._table(out, value, [{"name": value, value: value,
                                      "note": "Resource _author_ note.",
                                      "files": [{"path": value, "license_from": value}]}])
        tokens = PARSER.parse("\n".join(out))
        inline = [t for t in tokens if t.type == "inline"]
        self.assertTrue(inline)
        generated = [t for t in inline if not t.content.startswith(("Note for", "Author text"))]
        self.assertTrue(all(c.type in ("text", "code_inline") for t in generated for c in t.children))
        self.assertEqual(sum(c.content == value for t in generated for c in t.children), 6)
        self.assertIn("Resource _author_ note.", "\n".join(out))

    def test_all_generated_punctuation_is_literal(self):
        value = '*emphasis* _under_ [link](javascript:x) ![image](x) <b> &amp; | \\ `code` # head'
        html = PARSER.render("#### " + render_md.escape(value))
        self.assertNotIn("<em>", html)
        self.assertNotIn("<a ", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("<b>", html)
        inline = PARSER.parse("#### " + render_md.escape(value))[1]
        self.assertEqual([t.type for t in inline.children], ["code_inline"])
        self.assertEqual(inline.children[0].content, value)
        self.assertEqual(render_md.escape("next\n# heading"), "next \\# heading")

    def test_code_span_degenerate_and_backtick_aliases(self):
        for value in ("", " ", "   ", "`", "``", "`x`", "`x", "x`", " x ", " x", "x ",
                      "a`b``c", "[x](*y*)", "a|b", "line\nnext"):
            with self.subTest(value=value):
                text = render_md.code(value)
                tokens = PARSER.parse(text)
                if value:
                    self.assertEqual(len(tokens), 3)
                    children = tokens[1].children
                    self.assertEqual(len(children), 1)
                    self.assertEqual(children[0].type, "code_inline")
                    self.assertEqual(children[0].content, value.replace("\n", " "))
                else:
                    self.assertEqual(tokens, [])

    def test_citation_fields_are_all_literal(self):
        value = '*md* _path_ | [x](url) <script> &amp; `tick`'
        f = SimpleNamespace(documents={"d": ({"title": value, "revision": value}, ())},
                            repos={"r": ({"name": value, "commit": value, "license": value}, ())})
        entries = [
            {"class": "databook", "doc": "d", "at": [{"section": value, "heading": value}]},
            {"class": "src", "anchors": [{"repo": "r", "path": value, "symbol": value,
                "search": value, "node": value, "lines": [1, 2], "comment": True,
                "stale": {"was": value}}]},
            {"class": "hardware", "board": value, "method": value, "date": value},
            {"class": "press", "title": value, "url": value},
            {"class": "source-observed", "custom": {"nested": value}},
        ]
        for entry in entries:
            with self.subTest(entry=entry):
                text = render_md._citation(f, entry)
                children = PARSER.parse(text)[1].children
                self.assertTrue(all(t.type in ("text", "code_inline") for t in children))
                self.assertIn(value, "".join(t.content for t in children))


class Views(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "board-specs.yaml").write_text(marker("root_name"))
        self.path = self.root / "widget_chip.spec.yaml"
        self.path.write_text(chip())

    def write(self, data):
        self.path.write_text(yaml.safe_dump(data, sort_keys=False))

    def test_single_banner_identity_resources_context_and_order(self):
        data = yaml.safe_load(chip(facts=fact("a") + fact("b")))
        data["name"] = "Widget *name*"
        data["orientation"] = "Author *context*."
        data["facts"][0]["title"] = "A *literal* title"
        data["facts"][0]["note"] = "Author _note_."
        data["facts"][1]["section"] = "gotchas"
        self.write(data)
        code, out, err = run(self.root, "--format", "md", "--with-status")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Do not edit", out)
        self.assertIn("root_name:widget_chip.spec.yaml", out)
        self.assertIn("commit unavailable", out)
        self.assertIn("Canonical form `fact-v1`", out)
        self.assertIn("SHA256", out)
        self.assertIn("## Resources", out)
        self.assertIn("Orientation (author text):\n\n```\nAuthor *context*.\n```", out)
        self.assertIn("#### `A *literal* title`", out)
        self.assertIn("Fact note (author text):\n\n```\nAuthor _note_.\n```", out)
        self.assertIn("`widgetchip@root_name#a` · unverified", out)
        self.assertLess(out.index("#### `A"), out.index("## Gotchas"))
        code, bare, _ = run(self.root, "--format", "md")
        self.assertEqual(code, 0)
        self.assertNotIn(" · unverified", bare)

    def test_claim_imitation_is_author_text_and_never_provenance(self):
        data = yaml.safe_load(chip())
        imitation = '**Provenance** (generated):\n\n- src: invented@commit fake.c\n- `fake@fake#fake`'
        data["facts"][0]["claim"] = imitation
        self.write(data)
        code, out, _ = run(self.root, "--format", "md")
        self.assertEqual(code, 0)
        self.assertIn(imitation + "\n```\n\nProvenance (generated):", out)
        self.assertEqual(out.count("**Provenance** (generated):"), 1)
        self.assertIn("- databook: Widget TRM", out)

    def test_render_checks_again_if_checker_was_bypassed(self):
        checker = checked(self.root)
        file = checker.files[0]
        for value in ("# injected", "```\nswallows", "<script>x</script>", "[x](javascript:x)"):
            with self.subTest(value=value):
                file.data["facts"][0]["claim"] = value
                with self.assertRaisesRegex(ValueError, "facts"):
                    render_md.render(checker)
        with tempfile.TemporaryDirectory() as temp:
            context = Path(temp)
            (context / "board-specs.yaml").write_text(marker("context"))
            (context / "widgetchip.spec.yaml").write_text(chip())
            checker = checked(self.root, context=(context,))
            file = next(f for f in checker.files if f.root.context)
            file.data["facts"][0]["claim"] = "# injected"
            with self.assertRaisesRegex(ValueError, "facts"):
                render_md.render(checker, merged=True)

    def test_bad_inputs_and_cli_failure_contracts(self):
        for field, value in (("claim", "```\nx\n    ```"), ("note", "h\n---"),
                             ("title", "# h"), ("claim", "<script>"),
                             ("claim", "[x](javascript:x)")):
            data = yaml.safe_load(chip())
            data["facts"][0][field] = value
            self.write(data)
            code, out, err = run(self.root, "--format", "md", "--json")
            self.assertEqual((code, err), (1, ""))
            result = json.loads(out)
            self.assertIsNone(result["markdown"])
            self.assertNotIn("Generated by", out)
        self.path.write_text(chip())
        for args in (("--spec", ""), ("--spec", " "), ("--spec", "#"),
                     ("--spec", "widget-chip-alias"), ("--format", "html")):
            code, out, err = run(self.root, "--format", "md", "--json", *args)
            self.assertEqual((code, err), (2, ""))
            self.assertEqual(json.loads(out)["error"], "usage")
        empty = self.root / "empty"
        empty.mkdir()
        code, out, err = run(empty, "--format", "md", "--json")
        self.assertEqual((code, err), (3, ""))
        self.assertEqual(json.loads(out)["error"], "precondition")
        with patch.object(render_md, "render", side_effect=RuntimeError("intentional")):
            code, out, err = run(self.root, "--format", "md", "--json")
        self.assertEqual(code, 100)
        self.assertEqual(json.loads(out)["error"], "internal")
        self.assertIn("RuntimeError", err)

    def test_gap_conflict_scope_assumption_todo_and_notices(self):
        data = yaml.safe_load(chip())
        entry = data["facts"][0]
        value = '*literal* _path_ | [link](url) `tick`'
        entry.pop("support")
        entry["todo"] = {"check": "hardware", "text": value, "method": value}
        entry["scope"] = {"boards": [value], "modes": [value]}
        entry["assumes"] = ["assumed"]
        data["assumptions"] = [{"id": "assumed", "text": value}]
        entry["conflicts"] = [{"reading": value, "support": [
            {"class": "databook", "doc": "trm", "at": [{"section": "1"}]}]}]
        self.write(data)
        code, out, err = run(self.root, "--format", "md")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("- Gap", out)
        self.assertIn("conflict (contested)", out)
        self.assertIn("- scope: boards: " + render_md.escape(value), out)
        self.assertIn("- TODO (verify on hardware): " + render_md.escape(value), out)
        self.assertIn("- method: " + render_md.escape(value), out)
        self.assertIn("- assumes `assumed`: " + render_md.escape(value), out)
        self.path.write_text(chip(repos=repo(), facts=src_fact("a")))
        (self.root / "board-specs.yaml").write_text(marker("root_name", accepts="[GPL-2.0-only]"))
        data = yaml.safe_load(self.path.read_text())
        notice = 'copyright\n```\n# notice heading\n<script>\n`````'
        data["notices"] = [{"repo": "linux", "path": "drivers/w.c", "text": notice}]
        self.write(data)
        code, out, err = run(self.root, "--format", "md")
        self.assertEqual((code, err), (0, ""))
        self.assertIn(notice, out)
        tokens = PARSER.parse(out)
        self.assertFalse(any(t.type == "html_block" for t in tokens))
        self.assertTrue(any(t.type == "fence" and notice in t.content for t in tokens))

    def test_inference_generated_premises_derivation_and_relations(self):
        data = yaml.safe_load(chip(facts=fact("a") + inference("b", "#a")))
        entry = data["facts"][1]
        value = '*literal* _path_ [link](https://example.invalid/x)'
        support = entry["support"][0]
        support["premises"][0]["uses"] = value
        support["premises"].append({"states": value, "support": copy.deepcopy(data["facts"][0]["support"])})
        support["premises"].append({"assumption": "assumed"})
        support["derivation"] = value
        support["confidence"] = "low"
        data["assumptions"] = [{"id": "assumed", "text": value}]
        entry["relates"] = [{"fact": "#a", "relation": "qualifies"}]
        self.write(data)
        code, out, err = run(self.root, "--format", "md")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("- inference, from:", out)
        self.assertIn("  - `widgetchip@root_name#a`", out)
        self.assertIn("(T a): " + render_md.escape(value), out)
        self.assertIn("- derivation: " + render_md.escape(value), out)
        self.assertIn("- confidence: low", out)
        self.assertIn("- qualifies: `widgetchip@root_name#a`", out)
        self.assertIn("  - assumption `assumed`: " + render_md.escape(value), out)

    def test_identity_and_fact_generated_text_render_literally(self):
        data = yaml.safe_load(chip())
        value = '*bold* _under_ [x](https://example.invalid) | `ticks`'
        data["name"] = value
        data["triggers"] = [value]
        data["facts"][0]["title"] = value
        data["resources"]["documents"][0]["title"] = value
        data["resources"]["documents"][0]["revision"] = value
        data["facts"][0]["support"][0]["at"][0]["section"] = value
        data["facts"][0]["conflicts"] = [{"reading": value,
            "support": [{"class": "databook", "doc": "trm", "at": [{"section": "1"}]}],
            "resolution": value, "assumption": value,
            "decided": {"by": value, "date": "2026-10-08"}}]
        self.write(data)
        code, out, err = run(self.root, "--format", "md")
        self.assertEqual((code, err), (0, ""))
        tokens = PARSER.parse(out)
        self.assertTrue(all(c.type in ("text", "code_inline", "strong_open", "strong_close", "softbreak")
                            for t in tokens for c in t.children or []))
        heads = [t.children[0].content for i, t in enumerate(tokens)
                 if t.type == "inline" and tokens[i-1].type == "heading_open"]
        self.assertEqual(heads.count(value), 2)
        visible = "\n".join("".join(c.content for c in t.children or [])
                            for t in tokens if t.type == "inline")
        self.assertIn("triggers: " + value, visible)
        for key in ("conflict", "resolution", "assumption"):
            self.assertIn(key + ": " + value, visible)

    def test_merged_refuses_invalid_context_instead_of_omitting_it(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        context = Path(temp.name)
        (context / "board-specs.yaml").write_text(marker("context"))
        (context / "broken.spec.yaml").write_text("format: 2\nkind: overlay\noverlays: widgetchip\nfacts: wrong\n")
        code, out, err = run(self.root, "--context-root", context, "--merged", "--format", "md", "--json")
        self.assertEqual((code, err), (1, ""))
        self.assertIsNone(json.loads(out)["markdown"])

    def test_selection_aliases_and_no_specs(self):
        data = yaml.safe_load(chip())
        data["aliases"] = ["widget-alias"]
        self.write(data)
        code, out, err = run(self.root, "--spec", "widget-alias", "--format", "md", "--json")
        self.assertEqual((code, err), (2, ""))
        self.assertEqual(json.loads(out)["error"], "usage")
        self.path.unlink()
        code, out, err = run(self.root, "--format", "md", "--json")
        self.assertEqual((code, err), (2, ""))
        self.assertEqual(json.loads(out)["error"], "usage")

    def test_check_error_prevents_renderer_call(self):
        checker = checked(self.root)
        checker.add(checker.files[0], (), "intentional check failure")
        args = SimpleNamespace(merged=False, spec=None, with_status=False)
        with patch.object(spec, "_run_check", return_value=checker), patch.object(
                render_md, "render", return_value="unsafe view") as renderer:
            code, result = render_md.command(spec, args)
        self.assertEqual(code, 1)
        self.assertIsNone(result["markdown"])
        renderer.assert_not_called()


class WorkedExample(unittest.TestCase):
    def test_merged_design_slice_and_current_carried_status(self):
        with tempfile.TemporaryDirectory() as temp:
            copied = Path(temp) / "worked"
            shutil.copytree(HERE / "fixtures/worked-example", copied)
            docs, perm, gpl = (copied / name for name in ("docs", "permissive", "gpl"))
            path = perm / "bcm2711.spec.yaml"
            data = yaml.safe_load(path.read_text())
            base = yaml.safe_load((docs / "bcm2711.spec.yaml").read_text())
            data["resources"]["documents"].extend(d for d in base["resources"]["documents"]
                                                   if d["name"] in ("rpi-docs-legacy-boot", "bcm2711-peripherals"))
            for name, cls in (("tfa-rpi4", "doc"), ("gic400-trm", "databook")):
                data["resources"]["documents"].append({"name": name, "class": cls,
                    "title": "Synthetic omitted " + name, "url": "https://example.invalid/" + name})
            data["facts"].append({"id": "patch-words", "section": "quick-facts",
                "title": "Synthetic omitted premise", "claim": "Placeholder for the omitted premise.",
                "support": [{"class": "hardware", "board": "synthetic", "method": "fixture", "date": "2026-10-08"}]})
            path.write_text(yaml.safe_dump(data, sort_keys=False))
            code, out, err = run(docs, perm, gpl, "--spec", "bcm2711", "--merged", "--with-status", "--format", "md")
            self.assertEqual((code, err), (0, ""))
            visible = "\n".join("".join(c.content for c in t.children or [])
                                for t in PARSER.parse(out) if t.type == "inline")
            design = (HERE.parents[2] / "docs/SPEC-FORMAT-V2.md").read_text()
            slice_text = design.split("### Markdown view (merged, with status; slice)")[1].split("~~~markdown")[1].split("~~~")[0]
            slice_visible = "\n".join("".join(c.content for c in t.children or [])
                                      for t in PARSER.parse(slice_text) if t.type == "inline")
            for heading in ("# Broadcom BCM2711", "## Context (not facts)", "## Quick-facts",
                            "#### Addressing model", "#### High peripheral mode is likely the full map",
                            "### Overlay: public (hardware-specs-gpl)", "#### The tree describes Low Peripheral mode",
                            "#### GIC node"):
                self.assertIn(heading.lstrip("# "), slice_visible)
                self.assertIn(heading.lstrip("# "), visible)
            for title in ("Addressing model", "High peripheral mode is likely the full map",
                          "The tree describes Low Peripheral mode", "GIC node"):
                block = "#### " + title + slice_text.split("#### " + title, 1)[1]
                block = re.split(r"\n#{2,4} ", block, 1)[0].strip()
                self.assertIn(block, out)
            self.assertTrue(slice_text.lstrip().startswith("Generated by"))
            self.assertIn("8d3ae59288f1e7d58d76558a6ee96d533bc5019f", slice_text)
            html = PARSER.render(out)
            self.assertIn("BCM2711 ARM Peripherals (release 4", html)
            self.assertIn("§1.2.1–1.2.4, pp. 4–6", html)
            self.assertIn("arch/arm/boot/dts/broadcom/bcm2711.dtsi lines 56–66", html)
            self.assertIn("PASS 2026-10-08 · stale (carried from format 1", visible)
            self.assertLess(out.index("#### Addressing model"), out.index("#### GIC node"))
            self.assertEqual(out.count("#### Addressing model"), 1)
            self.assertIn("hardware-specs-docs:bcm2711.spec.yaml", out)
            checker = checked(docs, perm, gpl)
            record_path = gpl / "resources/bcm2711.verify.yaml"
            record = specload.load_strict(record_path)
            status = next(e for e in checker.status if e["file"].root.given == gpl)
            for row in status["rows"]:
                if row["key"] in record["verdicts"]:
                    record["verdicts"][row["key"]]["basis"] = row["basis"]
            record_path.write_text(yaml.safe_dump(record))
            code, out, err = run(gpl, "--context-root", docs, "--context-root", perm,
                                 "--spec", "bcm2711", "--merged", "--with-status", "--format", "md")
            self.assertEqual((code, err), (0, ""))
            visible = "\n".join("".join(c.content for c in t.children or [])
                                for t in PARSER.parse(out) if t.type == "inline")
            self.assertIn("PASS 2026-10-08 · current (carried from format 1; second reader missing)", visible)
            self.assertEqual(out.count("#### Addressing model"), 1)
            code, out, err = run(gpl, "--context-root", docs, "--context-root", perm, "--format", "md")
            self.assertEqual((code, err), (0, ""))
            self.assertNotIn("#### Addressing model", out)
            self.assertIn("#### GIC node", out)


if __name__ == "__main__":
    unittest.main()
