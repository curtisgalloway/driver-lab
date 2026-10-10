# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Synthetic format 1 conversion, deferred judgments and CLI file safety."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import migrate
import spec
import specload


IDENTITY = """kind: soc
id: test-soc
name: Test SoC
triggers: [test soc]
instances: []
aliases: []
"""
REPO = """resources:
  repos:
    - name: tree
      url: https://example.org/tree
      ref: '1111111111111111111111111111111111111111'
      license: MIT
      files: [soc.dtsi, code.c]
"""
LICENSES = {"tree:soc.dtsi": "spdx-line", "tree:code.c": "notice"}


def v1(body, metadata=IDENTITY):
    return "---\n" + metadata + "---\n\n# Test\n\n" + body


def cli(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec.main(args)
    return code, out.getvalue(), err.getvalue()


class MechanicalConversion(unittest.TestCase):
    def convert(self, body, metadata=IDENTITY):
        return migrate.convert(v1(body, metadata), license_from=LICENSES)

    def test_leadin_claim_section_and_key(self):
        data, report = self.convert("## Quick-facts\n\n- **Address map.** First line.\n  Second `line`. `[doc]` (Manual, header)\n")
        fact = data["facts"][0]
        self.assertEqual({k: fact[k] for k in ("id", "title", "section", "claim")},
                         {"id": "address-map", "title": "Address map", "section": "quick-facts",
                          "claim": "First line.\nSecond `line`."})
        self.assertEqual(report["rows"][0]["key"], 'Quick-facts/1 "Address map"')
        self.assertEqual(report["rows"][0]["provenance"], "`[doc]` (Manual, header)")
        self.assertNotIn("aliases", data)
        self.assertEqual(data["instances"], [])

    def test_reordering_unique_titles_does_not_change_ids(self):
        a = '- **One.** Text. `[doc]` (Book, one)\n'
        b = '- **Two.** Text. `[doc]` (Book, two)\n'
        first, _ = self.convert("## Quick-facts\n\n" + a + b)
        second, _ = self.convert("## Quick-facts\n\n" + b + a)
        self.assertEqual({f["title"]: f["id"] for f in first["facts"]},
                         {f["title"]: f["id"] for f in second["facts"]})

    def test_duplicate_titles_across_sections_are_disambiguated(self):
        data, _ = self.convert("## Quick-facts\n\n- **Same.** A. `[doc]` (X)\n\n## Gotchas\n\n- **Same.** B. `[doc]` (Y)\n")
        self.assertEqual([f["id"] for f in data["facts"]], ["same-quick-facts", "same-gotchas"])

    def test_duplicate_titles_in_section_refuse_guessing(self):
        with self.assertRaisesRegex(migrate.MigrationError, "duplicate lead-ins"):
            self.convert("## Quick-facts\n\n- **Same.** A. `[doc]` (X)\n- **Same.** B. `[doc]` (Y)\n")

    def test_source_anchor_ranges_and_symbols(self):
        data, report = self.convert("## Quick-facts\n\n- **Writes.** Writes R. `[src]` ([src:tree: code.c:2-4 (write_r)]; [src:tree: code.c:7 (R)])\n", IDENTITY + REPO)
        self.assertEqual(data["facts"][0]["support"], [{"class": "src", "anchors": [
            {"repo": "tree", "path": "code.c", "lines": [2, 4], "symbol": "write_r"},
            {"repo": "tree", "path": "code.c", "lines": [7, 7], "symbol": "R"}]}])
        self.assertNotIn("todo", data["facts"][0])
        self.assertEqual(report["summary"]["structured_citations"], 2)
        self.assertEqual(data["resources"]["repos"][0]["commit"], "1" * 40)

    def test_dt_multiple_ranges_and_single_line(self):
        data, _ = self.convert("## Quick-facts\n\n- **DT cells.** Value. `[DT]` (soc.dtsi lines 2-3 and 5–6, tree), `[DT]` (soc.dtsi line 9, tree)\n", IDENTITY + REPO)
        self.assertEqual([a["lines"] for s in data["facts"][0]["support"] for a in s["anchors"]],
                         [[2, 3], [5, 6], [9, 9]])

    def test_ambiguous_dt_basename_is_deferred(self):
        metadata = (IDENTITY + REPO).replace("soc.dtsi, code.c", "a/soc.dtsi, b/soc.dtsi, code.c")
        data, report = migrate.convert(v1("## Quick-facts\n\n- **DT.** Value. `[DT]` (soc.dtsi lines 1-2, tree)\n", metadata),
            license_from={**LICENSES, "tree:a/soc.dtsi": "spdx-line", "tree:b/soc.dtsi": "spdx-line"})
        self.assertNotIn("support", data["facts"][0])
        self.assertTrue(report["rows"][0]["citation_pass"])

    def test_missing_source_symbol_is_deferred(self):
        data, report = self.convert("## Quick-facts\n\n- **Source.** Value. `[src]` ([src:tree: code.c:1-2])\n", IDENTITY + REPO)
        self.assertNotIn("support", data["facts"][0])
        self.assertIn("[src:tree: code.c:1-2]", migrate.report_text(report))

    def test_unpinned_or_unlisted_source_is_deferred(self):
        for metadata, path in ((IDENTITY + REPO.replace("'" + "1" * 40 + "'", "main"), "code.c"),
                               (IDENTITY + REPO, "other.c")):
            with self.subTest(metadata=metadata, path=path):
                data, _ = self.convert(f"## Quick-facts\n\n- **Source.** Value. `[src]` ([src:tree: {path}:1-2 (R)])\n", metadata)
                self.assertNotIn("support", data["facts"][0])

    def test_inference_candidates_are_never_read_support(self):
        data, report = self.convert("## Quick-facts\n\n- **Conclusion.** Result. `[inference]` (premises: value [src:tree: code.c:1-2 (R)]; a tree `[DT]` (soc.dtsi lines 4-5, tree); derivation: result follows) `TODO (verify on hardware)`: observe it.\n", IDENTITY + REPO)
        self.assertNotIn("support", data["facts"][0])
        self.assertEqual(report["summary"]["deferred_anchor_candidates"], 2)
        self.assertEqual(report["rows"][0]["original_todo"], "observe it.")
        self.assertEqual(data["facts"][0]["todo"]["check"], "hardware")

    def test_mixed_bullet_is_flagged_and_not_split(self):
        data, report = self.convert("## Quick-facts\n\n- **Mixed.** Read and derived. `[src]` ([src:tree: code.c:1-2 (R)]), `[inference]` (premises: R; derivation: follows)\n", IDENTITY + REPO)
        self.assertEqual(len(data["facts"]), 1)
        self.assertEqual(data["facts"][0]["claim"], "Read and derived.")
        self.assertIn("split-mixed", data["facts"][0]["todo"]["text"])
        self.assertEqual(report["summary"]["mixed_bullets"], 1)
        self.assertEqual(data["facts"][0]["support"][0]["class"], "src")

    def test_document_prose_and_multiline_todo_are_retained(self):
        data, report = self.convert("## Quick-facts\n\n- **Doc.** Text. `[databook]` (Manual, §1, p. 3; Table 2)\n  `TODO (verify on\n  hardware)`: first\n  second\n")
        self.assertIn("citation-pass", data["facts"][0]["todo"]["text"])
        self.assertEqual(report["rows"][0]["original_todo"], "first\nsecond")
        self.assertIn("Manual, §1, p. 3; Table 2", migrate.report_text(report))

    def test_literal_tags_and_todo_inside_ordinary_code_stay_claim_text(self):
        data, _ = self.convert("## Quick-facts\n\n- **Literals.** Use `fake [DT]` and `fake TODO (verify on hardware): x`. `[doc]` (Manual)\n")
        self.assertEqual(data["facts"][0]["claim"], "Use `fake [DT]` and `fake TODO (verify on hardware): x`.")

    def test_tags_inside_fenced_code_stay_in_claim(self):
        data, _ = self.convert('## Quick-facts\n\n- **Literal.** Claim.\n\n  ```\n  [doc]\n  ```\n\n  `[doc]` (Manual, header)\n')
        self.assertEqual(data['facts'][0]['claim'], 'Claim.\n\n```\n[doc]\n```')

    def test_forbidden_link_destination_is_rejected_by_legacy_profile(self):
        with self.assertRaisesRegex(migrate.MigrationError, "link destination"):
            self.convert("## Quick-facts\n\n- **Link.** [Read](https://example.org/[DT]). `[doc]` (Manual)\n")

    def test_resource_hash_commit_retrieval_and_original_guidance(self):
        metadata = IDENTITY + """resources:
  docs:
    - title: Test manual
      url: https://example.org/blob/2222222222222222222222222222222222222222/manual
      cite: true
      verified: 2026-10-09
      note: '12-page PDF, SHA-256 HASH; printed page numbers'
      fetch_via: 'official PDF at https://example.org/manual.pdf (revision A)'
""".replace("HASH", "a" * 64)
        data, report = self.convert("## Quick-facts\n\n- **Doc.** Value. `[doc]` (Test manual)\n", metadata)
        doc = data["resources"]["documents"][0]
        self.assertEqual(doc["name"], "test-manual")
        self.assertEqual(doc["sha256"], "a" * 64)
        self.assertEqual(doc["commit"], "2" * 40)
        self.assertEqual(doc["pages"], 12)
        self.assertEqual(doc["verified"], "2026-10-09")
        self.assertEqual(doc["retrieval"], [{"url": "https://example.org/manual.pdf"}])
        self.assertNotIn("fetch_via", doc)
        self.assertNotIn("cite", doc)
        self.assertNotIn("SHA-256", doc["note"])
        self.assertIn("revision A", migrate.report_text(report))

    def test_literal_source_notice_survives(self):
        body = "## Quick-facts\n\n- **Value.** Value. `[src]` ([src:tree: code.c:1 (R)])\n\n## Source notices\n\nNotice from code.c:\n\n```text\nCopyright <author@example.org>\nAll rights reserved.\n```\n"
        data, _ = self.convert(body, IDENTITY + REPO)
        self.assertEqual(data["notices"], [{"repo": "tree", "path": "code.c",
                                         "text": "Copyright <author@example.org>\nAll rights reserved."}])

    def test_overlay_kind_orientation_and_empty_resources(self):
        data, _ = self.convert("Overlay introduction.\n\n## Quick-facts\n\n- **Value.** Text. `[doc]` (Manual)\n", "overlays: test-soc\nresources: {docs: [], tools: []}\n")
        self.assertEqual(data["kind"], "overlay")
        self.assertEqual(data["orientation"], "Overlay introduction.")
        self.assertNotIn("resources", data)

    def test_gap_with_original_hardware_todo_is_preserved(self):
        data, report = self.convert("## Quick-facts\n\n- **Unknown.** Unknown value. `TODO (verify on hardware)`: read it.\n")
        self.assertNotIn("support", data["facts"][0])
        self.assertTrue(data["facts"][0]["todo"]["text"].startswith("read it."))
        self.assertFalse(report["rows"][0]["citation_pass"])

    def test_invalid_markdown_and_frontmatter_fail_closed(self):
        for raw in ("", " ", "---\n---", "---\nformat: 2\n---\n",
                    v1("## Quick-facts\n\n- Text without a lead-in.\n"),
                    v1("## Quick-facts\n\n- **Value.** Text. `[doc]` (unclosed\n"),
                    v1("## Quick-facts\n\n- **Value.** Text.\n  ## Inside\n"),
                    v1("## Quick-facts\n\n- **Value.** Text.\n  - Nested.\n")):
            with self.subTest(raw=raw), self.assertRaises((migrate.MigrationError, specload.LoadError)):
                migrate.convert(raw)

    def test_missing_license_declaration_does_not_guess(self):
        with self.assertRaisesRegex(migrate.MigrationError, "supply --license-from"):
            migrate.convert(v1("## Quick-facts\n\n- **Value.** Value. `[DT]` (soc.dtsi line 1, tree)\n", IDENTITY + REPO))

    def test_yaml_roundtrip_retains_strings_without_aliases(self):
        data, _ = self.convert("## Quick-facts\n\n- **A.** 2026-10-09: `0x10`. `[doc]` (Manual)\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.spec.yaml"
            path.write_text(migrate.yaml_text(data), encoding="utf-8")
            self.assertEqual(specload.load_strict(path), data)

    def test_verdict_keys_preserve_record_punctuation(self):
        _, report = self.convert('## Gotchas\n\n- **Caution.** Value. `[doc]` (Manual)\n')
        migrate.map_verdict_keys('---\nspec: test-soc\n---\n\n- Gotchas/1 "Caution.": PASS — read.\n', report)
        self.assertEqual(report['rows'][0]['key'], 'Gotchas/1 "Caution."')
        self.assertIn('Gotchas/1 "Caution."', migrate.report_text(report))

    def test_verdict_key_mismatch_missing_and_duplicate_are_rejected(self):
        for entries in ('- Gotchas/1 "Other": PASS\n', '',
                        '- Gotchas/1 "Caution": PASS\n- Gotchas/1 "Caution": FAIL\n'):
            _, report = self.convert('## Gotchas\n\n- **Caution.** Value. `[doc]` (Manual)\n')
            with self.subTest(entries=entries), self.assertRaises(migrate.MigrationError):
                migrate.map_verdict_keys('---\nspec: test-soc\n---\n\n' + entries, report)


class MigrationCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "old.spec.md"
        self.source.write_text(v1("## Quick-facts\n\n- **Value.** Value. `[doc]` (Manual)\n"), encoding="utf-8")
        self.output = self.root / "out" / "new.spec.yaml"
        self.report = self.root / "report.md"
        self.args = ["migrate", str(self.source), "--output", str(self.output),
                     "--report", str(self.report), "--json"]

    def test_cli_outputs_validate_and_marker_is_copied(self):
        marker = self.root / "board-specs.yaml"
        original = "name: test\nlayer: public\nlicense: MIT\naccepts: [MIT]\n"
        marker.write_text(original, encoding="utf-8")
        code, out, err = cli(self.args)
        self.assertEqual(code, 0, err + out)
        self.assertEqual(json.loads(out)["summary"]["facts"], 1)
        code, out, err = cli(["validate", str(self.output), str(self.output.parent / "board-specs.yaml"), "--json"])
        self.assertEqual(code, 0, err + out)
        self.assertEqual(marker.read_text(), original)
        self.assertIn('Quick-facts/1 "Value"', self.report.read_text())

    def test_cli_autodiscovers_record_without_carrying_verdicts(self):
        resources = self.root / "resources"
        resources.mkdir()
        (resources / "old.verify.md").write_text('---\nspec: test-soc\n---\n\n- Quick-facts/1 "Value.": PASS\n', encoding='utf-8')
        code, out, _ = cli(self.args)
        self.assertEqual(code, 0, out)
        self.assertIn('Quick-facts/1 "Value."', self.report.read_text())
        self.assertFalse(list(self.output.parent.rglob('*.verify.yaml')))

    def test_no_output_written_on_schema_error(self):
        self.source.write_text(v1("## Quick-facts\n\n- **Value.** Text. `[doc]` (X)\n", "kind: soc\nid: test\n"), encoding="utf-8")
        code, out, _ = cli(self.args)
        self.assertEqual(code, 1, out)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.report.exists())

    def test_existing_output_or_report_never_overwritten(self):
        for path in (self.output, self.report):
            with self.subTest(path=path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("sentinel", encoding="utf-8")
                code, out, _ = cli(self.args)
                self.assertEqual(code, 2, out)
                self.assertEqual(path.read_text(), "sentinel")
                other = self.report if path == self.output else self.output
                self.assertFalse(other.exists())
                path.unlink()

    def test_symlink_output_directory_is_refused(self):
        actual = self.root / "actual"
        actual.mkdir()
        self.output.parent.symlink_to(actual, target_is_directory=True)
        code, out, _ = cli(self.args)
        self.assertEqual(code, 2, out)
        self.assertFalse((actual / self.output.name).exists())
        self.assertFalse(self.report.exists())

    def test_defaults_and_usage_failures(self):
        code, out, _ = cli(["migrate", str(self.source), "--json"])
        self.assertEqual(code, 0, out)
        self.assertTrue(self.source.with_suffix(".yaml").is_file())
        for args in (["migrate", "--json"],
                     ["migrate", str(self.root / "absent.spec.md"), "--json"],
                     self.args + ["--license-from", "invalid=notice"],
                     self.args + ["--output", str(self.root / "bad.md")]):
            with self.subTest(args=args):
                code, out, _ = cli(args)
                self.assertEqual(code, 2, out)
                self.assertEqual(json.loads(out)["error"], "usage")

    def test_report_fences_cannot_be_closed_by_provenance(self):
        data, report = migrate.convert(v1("## Quick-facts\n\n- **Quoted.** Text. `[doc]` (Manual, ```literal```)\n"))
        text = migrate.report_text(report)
        self.assertIn("````\n`[doc]` (Manual, ```literal```)\n````", text)


if __name__ == "__main__":
    unittest.main()
