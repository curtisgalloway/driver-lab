#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for document section indexes (#155): `spec.py index`, its checks and its views.

Each test copies fixtures/check/good_root to a temporary root and builds the document bytes it
needs: a PDF with an outline made with pypdf, or a Markdown file. No PDF is committed.

Run in the pinned environment:
  .venv-spec/bin/python -m unittest discover -s skills/spec-format/tests -v
"""

import contextlib
import hashlib
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "spec.py"
GOOD = HERE / "fixtures" / "check" / "good_root"
sys.path.insert(0, str(SCRIPT.parent))
import spec as spec_cli  # noqa: E402
import index as index_mod  # noqa: E402

SKILL = ["--public-skill", "widget-board-tools"]
TRM = '{name: widget-trm, class: databook, title: Widget SoC TRM, url: "https://example.invalid/widget-trm.pdf", pages: 120}'


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec_cli.main([str(a) for a in argv] + ["--json"])
    return code, json.loads(out.getvalue())


OUTLINE = (("1 Overview", 0, ()),
           ("6 UART", 89, (("6.1 Registers", 91, ()), ("6.2 FIFO", 95, ()))),
           ("Appendix A Errata", 110, ()))


def pdf(pages=120, outline=OUTLINE):
    """A PDF with blank pages and the given outline: (title, 0-based page, children)."""
    import pypdf

    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)

    def add(items, parent=None):
        for name, page, children in items:
            item = writer.add_outline_item(name, page, parent=parent)
            add(children, item)

    add(outline)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class IndexTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = pathlib.Path(self._tmp.name)
        self.root = tmp / "good_root"
        shutil.copytree(GOOD, self.root)
        self.docs = tmp / "docs"
        self.docs.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def install(self, data, *, name="widget-trm", pages=None, numbering="pdf"):
        """Write the document bytes and record their hash (and pages) in widgetsoc's entry."""
        (self.docs / name).write_bytes(data)
        soc = self.root / "widgetsoc.spec.yaml"
        text = soc.read_text(encoding="utf-8")
        extra = f", sha256: {hashlib.sha256(data).hexdigest()}"
        if pages:
            extra = f", pages: {pages}, page_numbering: {numbering}" + extra
        new = TRM.replace(", pages: 120}", extra + "}")
        self.assertIn(TRM, text)
        soc.write_text(text.replace(TRM, new), encoding="utf-8")

    def index(self, name="widget-trm"):
        return run("index", name, "--root", self.root, "--docs-dir", self.docs)

    def errors(self, result):
        return [f["message"] for f in result["findings"] if f["level"] == "error"]

    def warnings(self, result):
        return [f["message"] for f in result["findings"] if f["level"] == "warning"
                and "unverified" not in f["message"]]

    # --- building ----------------------------------------------------------------------------

    def test_pdf_outline_becomes_sections(self):
        self.install(pdf(), pages=120)
        code, result = self.index()
        self.assertEqual(code, 0, result)
        import specload

        data = specload.load_strict(pathlib.Path(result["path"]))
        self.assertEqual((data["source"], data["pages"]), ("pdf", 120))
        self.assertEqual(data["sections"], [
            # each range keeps the page the next section starts on: it may end part-way down
            {"number": "1", "title": "1 Overview", "level": 1, "pages": [1, 90]},
            {"number": "6", "title": "6 UART", "level": 1, "pages": [90, 111]},
            {"number": "6.1", "title": "6.1 Registers", "level": 2, "pages": [92, 96]},
            {"number": "6.2", "title": "6.2 FIFO", "level": 2, "pages": [96, 111]},
            {"title": "Appendix A Errata", "level": 1, "pages": [111, 120]}])

    def test_out_of_order_outline_keeps_parents_around_children(self):
        outline = (("1 Intro", 0, ()), ("2 Body", 9, (("2.1 Late", 49, ()), ("2.2 Early", 19, ()))),
                   ("3 End", 29, ()))
        self.install(pdf(outline=outline), pages=120)
        _, result = self.index()
        import specload

        got = {s["title"]: s["pages"] for s in
               specload.load_strict(pathlib.Path(result["path"]))["sections"]}
        self.assertEqual(got["2.1 Late"], [50, 120])  # no later sibling starts after page 50
        self.assertEqual(got["2.2 Early"], [20, 30])
        self.assertEqual(got["2 Body"], [10, 120])  # covers both children
        for name, (first, last) in got.items():
            self.assertLessEqual(first, last, name)

    def test_hostile_titles_load_again(self):
        titles = ["soft\u00adhyphen", "zero\u200bwidth", "\ufeffbom", "bidi \u202eevil",
                  "private \ue000use", "nonchar \ufffe", "decomposed e\u0301", "- dash",
                  "# hash", "{brace}", "key: value", "'quote\"", "tab\there", "line\nbreak",
                  "yes", "1", "x" * 2000]
        outline = tuple((t, i, ()) for i, t in enumerate(titles))
        self.install(pdf(outline=outline), pages=120)
        code, result = self.index()
        self.assertEqual(code, 0, result)
        code, checked = run("check", self.root, *SKILL)
        self.assertEqual((code, self.errors(checked)), (0, []))
        import specload

        got = [s["title"] for s in specload.load_strict(pathlib.Path(result["path"]))["sections"]]
        self.assertIn("decomposed \u00e9", got)  # NFC
        self.assertIn("soft hyphen", got)
        self.assertIn("yes", got)

    def test_output_is_deterministic_and_carries_the_marker_header(self):
        self.install(pdf(), pages=120)
        _, first = self.index()
        a = pathlib.Path(first["path"]).read_text(encoding="utf-8")
        _, second = self.index()
        self.assertEqual(a, pathlib.Path(second["path"]).read_text(encoding="utf-8"))
        self.assertTrue(a.startswith("# SPDX-FileCopyrightText: 2026 contributors\n"
                                     "# SPDX-License-Identifier: Apache-2.0\n"))
        self.assertEqual(pathlib.Path(first["path"]),
                         self.root / "index" / "widget-trm.index.yaml")

    def test_markdown_headings_become_line_ranges(self):
        text = "# Guide\n\nintro\n\n## 1 Setup\n\nx\n\n## 2 Use\n\ny\n### 2.1 Detail\nz\n"
        self.install(text.encode())
        code, result = self.index()
        self.assertEqual(code, 0, result)
        import specload

        data = specload.load_strict(pathlib.Path(result["path"]))
        self.assertEqual(data["source"], "markdown")
        self.assertEqual(data["lines"], 13)
        self.assertEqual([(s["title"], s["lines"]) for s in data["sections"]],
                         [("Guide", [1, 13]), ("1 Setup", [5, 8]), ("2 Use", [9, 13]),
                          ("2.1 Detail", [12, 13])])

    def test_index_holds_no_page_text(self):
        import pypdf

        writer = pypdf.PdfWriter()
        from pypdf.generic import (DecodedStreamObject, DictionaryObject, NameObject)

        writer = pypdf.PdfWriter()
        page = writer.add_blank_page(width=200, height=200)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject(
            {NameObject("/F1"): writer._add_object(font)})})
        body = DecodedStreamObject()
        body.set_data(b"BT /F1 12 Tf 20 100 Td (SECRETBODYTEXT) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(body)
        writer.add_outline_item("1 Only", 0)
        buf = io.BytesIO()
        writer.write(buf)
        self.assertIn("SECRETBODYTEXT", pypdf.PdfReader(io.BytesIO(buf.getvalue()))
                      .pages[0].extract_text())  # the page really carries text
        self.install(buf.getvalue(), pages=1)
        _, result = self.index()
        text = pathlib.Path(result["path"]).read_text(encoding="utf-8")
        self.assertNotIn("SECRETBODYTEXT", text)
        self.assertEqual(text.count("\n"), 10, text)  # header lines and one section, nothing else

    # --- writing -----------------------------------------------------------------------------

    def test_refuses_to_write_through_a_link(self):
        self.install(pdf(), pages=120)
        outside = self.docs / "outside.txt"
        outside.write_text("keep me")
        (self.root / "index").mkdir()
        (self.root / "index" / "widget-trm.index.yaml").symlink_to(outside)
        code, _ = self.index()
        self.assertEqual(code, 2)
        self.assertEqual(outside.read_text(), "keep me")
        (self.root / "index" / "widget-trm.index.yaml").unlink()
        (self.root / "index").rmdir()
        (self.root / "index").symlink_to(self.docs, target_is_directory=True)
        code, _ = self.index()
        self.assertEqual(code, 2)
        self.assertFalse((self.docs / "widget-trm.index.yaml").exists())

    def test_refuses_when_index_is_a_file(self):
        self.install(pdf(), pages=120)
        (self.root / "index").write_text("not a directory")
        code, _ = self.index()
        self.assertEqual(code, 2)

    # --- refusals ----------------------------------------------------------------------------

    def test_refuses_bytes_with_another_hash(self):
        self.install(pdf(), pages=120)
        (self.docs / "widget-trm").write_bytes(pdf(pages=121))
        code, result = self.index()
        self.assertEqual(code, 1)
        self.assertFalse((self.root / "index").exists())

    def test_refuses_a_document_without_sha256(self):
        (self.docs / "widget-trm").write_bytes(pdf())
        code, result = self.index()
        self.assertEqual(code, 2)
        self.assertIn("has no sha256", json.dumps(result))

    def test_refuses_an_unlisted_document(self):
        code, result = self.index("nosuch-doc")
        self.assertEqual(code, 2)

    def test_refuses_a_pdf_without_outline(self):
        self.install(pdf(outline=()), pages=120)
        code, result = self.index()
        self.assertEqual(code, 1)
        self.assertFalse((self.root / "index").exists())

    # --- the check ---------------------------------------------------------------------------

    def test_current_index_checks_clean(self):
        self.install(pdf(), pages=120)
        self.index()
        code, result = run("check", self.root, *SKILL)
        self.assertEqual((code, self.errors(result), self.warnings(result)), (0, [], []))

    def test_hash_mismatch_warns(self):
        self.install(pdf(), pages=120)
        self.index()
        path = self.root / "index" / "widget-trm.index.yaml"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("sha256: ", "sha256: 0", 1).replace(
            text.split("sha256: ")[1][:64], "0" * 63, 1), encoding="utf-8")
        code, result = run("check", self.root, *SKILL)
        self.assertEqual(code, 0, result)
        self.assertEqual(len(self.warnings(result)), 1, result)
        self.assertIn("is not the registry's", self.warnings(result)[0])

    def test_unlisted_document_warns(self):
        self.install(pdf(), pages=120)
        self.index()
        path = self.root / "index" / "widget-trm.index.yaml"
        path.write_text(path.read_text().replace("document: widget-trm", "document: other-doc"))
        path.rename(self.root / "index" / "other-doc.index.yaml")
        code, result = run("check", self.root, *SKILL)
        self.assertEqual(code, 0, result)
        self.assertIn("lists document 'other-doc'", " ".join(self.warnings(result)))

    def untrusted(self):
        import types

        import speccheck

        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)
        return speccheck.check(api, spec_cli.load_schemas(), [self.root],
                               public_skills=["widget-board-tools"]).roots[0].untrusted

    def test_page_count_mismatch_warns(self):
        self.install(pdf(), pages=120)
        self.index()
        path = self.root / "index" / "widget-trm.index.yaml"
        path.write_text(path.read_text().replace("pages: 120\n", "pages: 121\n"))
        code, result = run("check", self.root, *SKILL)
        self.assertEqual(code, 0, result)
        self.assertIn("index counts 121 pages", " ".join(self.warnings(result)))

    def test_registry_without_sha256_warns(self):
        self.install(pdf(), pages=120)
        self.index()
        soc = self.root / "widgetsoc.spec.yaml"
        import re

        soc.write_text(re.sub(r", sha256: [0-9a-f]{64}", "", soc.read_text()))
        code, result = run("check", self.root, *SKILL)
        self.assertEqual(code, 0, result)
        self.assertIn("records no sha256", " ".join(self.warnings(result)))

    def test_near_miss_index_name_is_an_error(self):
        self.install(pdf(), pages=120)
        self.index()
        (self.root / "index" / "widget-trm.index.yaml").rename(
            self.root / "index" / "widget-trm.index.yml")
        code, result = run("check", self.root, *SKILL)
        self.assertEqual(code, 1)
        self.assertIn("not read as a document index", " ".join(self.errors(result)))
        self.assertEqual(self.untrusted(), [])

    def test_unicode_digit_page_locator_does_not_crash_views(self):
        self.install(pdf(), pages=120)
        self.index()
        soc = self.root / "widgetsoc.spec.yaml"
        soc.write_text(soc.read_text().replace('section: "6.1", pages: ["92", "93"]',
                                               'page: "\u00b2"'))
        code, result = run("render", self.root, *SKILL, "--format", "md")
        self.assertEqual(code, 0, result)

    def test_misplaced_index_is_an_error_that_keeps_trust(self):
        self.install(pdf(), pages=120)
        self.index()
        shutil.move(self.root / "index" / "widget-trm.index.yaml",
                    self.root / "widget-trm.index.yaml")
        code, result = run("check", self.root, *SKILL)
        self.assertEqual(code, 1)
        self.assertIn("lives in the root's own index/", " ".join(self.errors(result)))
        self.assertEqual(self.untrusted(), [])

    def test_malformed_index_is_an_error(self):
        self.install(pdf(), pages=120)
        self.index()
        path = self.root / "index" / "widget-trm.index.yaml"
        path.write_text(path.read_text().replace("source: pdf", "source: word"))
        code, result = run("check", self.root, *SKILL)
        self.assertEqual(code, 1)
        self.assertEqual(self.untrusted(), [])

    def test_validate_picks_the_index_schema(self):
        self.install(pdf(), pages=120)
        _, built = self.index()
        code, result = run("validate", built["path"])
        self.assertEqual((code, result["files"][0]["schema"]), (0, "index"))

    # --- links and views ---------------------------------------------------------------------

    def test_links_by_section_heading_and_pdf_page(self):
        self.install(pdf(), pages=120)
        self.index()
        import types

        import speccheck

        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)
        checker = speccheck.check(api, spec_cli.load_schemas(), [self.root],
                                  public_skills=["widget-board-tools"])
        [entry] = index_mod.links(checker.roots[0])
        facts = {s["title"]: s["facts"] for s in entry["sections"]}
        # uart-base cites section 6.1, pages 92-93 (PDF numbering): 6.1 and its parent 6
        self.assertEqual(facts, {"1 Overview": [], "6 UART": ["widgetsoc@good#uart-base"],
                                 "6.1 Registers": ["widgetsoc@good#uart-base"],
                                 "6.2 FIFO": [], "Appendix A Errata": []})

    def test_printed_page_numbers_link_by_section_only(self):
        self.install(pdf(), pages=120, numbering="printed")
        soc = self.root / "widgetsoc.spec.yaml"
        soc.write_text(soc.read_text().replace('section: "6.1", ', ""))
        self.index()
        import types

        import speccheck

        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)
        checker = speccheck.check(api, spec_cli.load_schemas(), [self.root],
                                  public_skills=["widget-board-tools"])
        [entry] = index_mod.links(checker.roots[0])
        self.assertEqual([s["facts"] for s in entry["sections"]], [[]] * 5)

    def test_section_number_matches_whole_components(self):
        self.install(pdf(), pages=120, numbering="printed")
        soc = self.root / "widgetsoc.spec.yaml"
        soc.write_text(soc.read_text().replace('section: "6.1"', 'section: "6.10"'))
        self.index()
        import types

        import speccheck

        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)
        checker = speccheck.check(api, spec_cli.load_schemas(), [self.root],
                                  public_skills=["widget-board-tools"])
        [entry] = index_mod.links(checker.roots[0])
        facts = {s["title"]: s["facts"] for s in entry["sections"]}
        self.assertEqual(facts["6 UART"], ["widgetsoc@good#uart-base"])  # 6.10 is under 6
        self.assertEqual(facts["6.1 Registers"], [])  # but not under 6.1

    def test_markdown_view_lists_indexed_sections(self):
        self.install(pdf(), pages=120)
        self.index()
        code, result = run("render", self.root, *SKILL, "--format", "md")
        self.assertEqual(code, 0, result)
        self.assertIn("## Document index (generated): widget\\-trm", result["markdown"])
        self.assertIn("6\\.1 Registers", result["markdown"])

    def test_html_viewer_and_atlas_list_indexed_sections(self):
        self.install(pdf(), pages=120)
        self.index()
        code, result = run("render", self.root, *SKILL, "--format", "html")
        self.assertEqual(code, 0, result)
        self.assertIn("Document index (generated): widget-trm", result["html"])
        self.assertIn("<td>6.1 Registers</td>", result["html"])
        import types

        import atlas
        import speccheck

        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)
        checker = speccheck.check(api, spec_cli.load_schemas(), [self.root],
                                  public_skills=["widget-board-tools"])
        [entry] = atlas.data(checker, "widgetboard")["indexes"]
        self.assertEqual((entry["root"], entry["document"], len(entry["sections"])),
                         ("good", "widget-trm", 5))


if __name__ == "__main__":
    unittest.main()
