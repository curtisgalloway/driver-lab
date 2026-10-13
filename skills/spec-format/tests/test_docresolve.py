# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Document evidence regression tests for issue #107."""

import contextlib
import hashlib
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import docresolve
import resolve
import spec
import yaml
from test_resolve import cli, HEADER


def pdf_bytes(pages):
    """Small real PDF with one text stream per page, without test dependencies."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids = []
    for text in pages:
        number = len(objects) + 1
        kids.append(f"{number} 0 R")
        stream = f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET".encode()
        objects.extend(
            [
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {number + 1} 0 R >>"
                ).encode(),
                f"<< /Length {len(stream)} >>\nstream\n".encode()
                + stream
                + b"\nendstream",
            ]
        )
    objects[1] = (
        f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    )
    output = b"%PDF-1.4\n"
    offsets = [0]
    for n, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(output)
    output += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return (
        output
        + (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{start}\n%%EOF\n"
        ).encode()
    )


class DocumentTests(unittest.TestCase):
    """Exercise document-only commands with mocked and real PDF text."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.path = self.directory / "chip.spec.yaml"
        raw = pdf_bytes(
            ["1.2 Table 2-3 Figure 4-5 VALUE 0x10", "middle 0x20", "3.4 Table 8-9 0x30"]
        )
        (self.directory / "manual").write_bytes(raw)
        self.data = dict(
            format=2,
            kind="chip",
            id="chip",
            name="Chip",
            triggers=["chip"],
            resources={
                "documents": [
                    dict(
                        name="manual",
                        title="Manual",
                        url="https://example.invalid/manual",
                        **{"class": "standard"},
                        pages=3,
                        page_numbering="pdf",
                        sha256=hashlib.sha256(raw).hexdigest(),
                    )
                ]
            },
            facts=[
                dict(
                    id="value",
                    section="quick-facts",
                    title="Value",
                    claim="VALUE is 0x10.",
                    support=[
                        dict(
                            **{"class": "standard"},
                            doc="manual",
                            at=[
                                dict(page="1", section="1.2", table="2-3", figure="4-5")
                            ],
                        )
                    ],
                )
            ],
        )

    @property
    def locator(self):
        return self.data["facts"][0]["support"][0]["at"][0]

    def run_cli(self, command="resolve"):
        self.path.write_text(HEADER + yaml.safe_dump(self.data, sort_keys=False))
        return cli(command, self.path, "--docs-dir", self.directory)

    def mocked_pages(self):
        return mock.patch.object(
            docresolve.PdfPages,
            "page",
            side_effect=lambda n: {
                1: ["1.2 Table 2-3 Figure 4-5 VALUE 0x10"],
                2: ["middle 0x20"],
                3: ["3.4 Table 8-9 0x30"],
            }[n],
        )

    def test_document_only_show_and_terminal_output(self):
        with self.mocked_pages():
            code, result = self.run_cli("show")
            self.assertEqual(code, 0, result)
            self.assertEqual(result["documents_resolved"], 1)
            self.assertEqual(result["findings"], [])
            citation = result["facts"][0]["citations"][0]
            self.assertEqual(
                citation["source"][0], [1, 1, "1.2 Table 2-3 Figure 4-5 VALUE 0x10"]
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(
                    spec.main(
                        ["show", str(self.path), "--docs-dir", str(self.directory)]
                    ),
                    0,
                )
            self.assertIn("manual", out.getvalue())
            self.assertIn("PDF page 1", out.getvalue())
            self.assertIn("VALUE 0x10", out.getvalue())

    def test_adjacent_and_absent_locators_warn(self):
        self.locator.update(page="2", section="1.2", table="8-9", figure="999")
        with self.mocked_pages():
            code, result = self.run_cli()
        self.assertEqual(code, 0, result)
        messages = "\n".join(f["message"] for f in result["findings"])
        self.assertIn("adjacent PDF page(s): 1", messages)
        self.assertIn("adjacent PDF page(s): 3", messages)
        self.assertIn("figure '999' absent", messages)
        self.assertIn("claim hex values absent", messages)

    def test_inclusive_range_and_missing_register_offset(self):
        self.locator.clear()
        self.locator.update(pages=["1", "3"], table="8-9")
        fact = self.data["facts"][0]
        self.data["kind"] = "peripheral"
        fact["section"] = "registers"
        fact["claim"] = "VALUE is 0x20."
        fact["data"] = {"register": {"name": "VALUE", "offset": "0xff"}}
        with self.mocked_pages():
            code, result = self.run_cli("show")
        self.assertEqual(code, 0, result)
        self.assertEqual(
            {line[0] for line in result["document_citations"][0]["source"]}, {1, 2, 3}
        )
        self.assertEqual(len(result["findings"]), 1, result)
        self.assertIn("register offset absent", result["findings"][0]["message"])

    def test_printed_numbering_and_missing_pages_skip(self):
        for change in ("printed", "no-pages"):
            with self.subTest(change=change), self.mocked_pages() as extractor:
                if change == "printed":
                    self.data["resources"]["documents"][0]["page_numbering"] = "printed"
                else:
                    self.data["resources"]["documents"][0]["page_numbering"] = "pdf"
                    self.locator.pop("page")
                code, result = self.run_cli()
                self.assertEqual(code, 0, result)
                self.assertEqual(result["documents_skipped"], 1)
                extractor.assert_not_called()

    def test_hash_mismatch_prevents_extraction(self):
        (self.directory / "manual").write_bytes(b"%PDF-changed")
        with self.mocked_pages() as extractor:
            code, result = self.run_cli()
        self.assertEqual(code, 1, result)
        extractor.assert_not_called()

    def test_missing_extractor_and_empty_text_are_skipped(self):
        with mock.patch.object(docresolve.shutil, "which", return_value=None):
            code, result = self.run_cli()
        self.assertEqual((code, result["documents_skipped"]), (0, 1), result)
        self.assertIn("pdftotext unavailable", str(result))
        with mock.patch.object(docresolve.PdfPages, "page", return_value=[]):
            code, result = self.run_cli()
        self.assertEqual((code, result["documents_skipped"]), (0, 1), result)

    @unittest.skipUnless(shutil.which("pdftotext"), "optional pdftotext unavailable")
    def test_real_pdf_extraction_and_cache(self):
        code, result = self.run_cli("show")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["findings"], [])
        reader = docresolve.PdfPages(self.directory / "manual", 30, 4096)
        self.assertIn("0x10", "\n".join(reader.page(1)))
        with mock.patch.object(docresolve.subprocess, "run") as proc:
            reader.page(1)
            proc.assert_not_called()
        with self.assertRaises(resolve.ResolutionError):
            reader.page(4)
        with self.assertRaises(resolve.LimitExceeded):
            docresolve.PdfPages(self.directory / "manual", 30, 1).page(1)

    def test_locator_tokens_do_not_match_prefixes(self):
        for kind, token, text in (
            ("section", "1.2", "1.20"),
            ("table", "2-3", "Table 2-30"),
            ("figure", "4-5", "Figure 4-5-1"),
        ):
            self.assertIsNone(docresolve.locator_pattern(kind, token).search(text))
        self.assertIsNotNone(
            docresolve.locator_pattern("table", "2-3").search("Table\n2-3")
        )

    def test_optional_page_count_and_document_classes(self):
        self.data["resources"]["documents"][0].pop("pages")
        for kind in ("standard", "databook", "doc"):
            self.data["resources"]["documents"][0]["class"] = kind
            self.data["facts"][0]["support"][0]["class"] = kind
            with self.subTest(kind=kind), self.mocked_pages():
                code, result = self.run_cli()
                self.assertEqual((code, result["documents_resolved"]), (0, 1), result)

    def test_huge_page_number_returns_verdict(self):
        self.data["resources"]["documents"][0].pop("pages")
        for page in ("1" * 5000, "4294967297"):
            self.locator["page"] = page
            with self.subTest(page=page[:20]), self.mocked_pages() as extractor:
                code, result = self.run_cli()
            self.assertEqual(code, 1, result)
            self.assertIn("extractor integer range", str(result))
            extractor.assert_not_called()

    def test_extraction_failure_and_timeout(self):
        with mock.patch.object(
            docresolve.PdfPages,
            "page",
            side_effect=resolve.ResolutionError("corrupt PDF"),
        ):
            code, result = self.run_cli()
        self.assertEqual(code, 1, result)
        self.assertEqual(result["document_citations"][0]["status"], "failed")
        with mock.patch.object(
            docresolve.PdfPages, "page", side_effect=resolve.LimitExceeded("time limit")
        ):
            code, result = self.run_cli()
        self.assertEqual((code, result["documents_skipped"]), (0, 1), result)

    def test_without_docs_dir_and_unpinned_document(self):
        self.run_cli()
        code, result = cli("show", self.path)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["document_citations"], [])
        self.data["resources"]["documents"][0].pop("sha256")
        with self.mocked_pages() as extractor:
            code, result = self.run_cli()
        self.assertEqual((code, result["documents_skipped"]), (0, 1), result)
        extractor.assert_not_called()

    def test_premise_text_does_not_clear_owner_hex_warning(self):
        record = self.data["facts"][0]
        record["claim"] = "VALUE is 0x20."
        record["support"].append(
            {
                "class": "inference",
                "premises": [
                    {
                        "claim": "Other is 0x20.",
                        "support": [
                            {
                                "class": "standard",
                                "doc": "manual",
                                "at": [{"page": "2"}],
                            }
                        ],
                    }
                ],
            }
        )
        doc = self.data["resources"]["documents"][0]
        reader = docresolve.PdfPages(self.directory / "manual", 30, 4096)
        with self.mocked_pages():
            items, lines = docresolve.citations(
                record, ("facts", 0), {"manual": (doc, reader)}, mock.Mock()
            )
        self.assertEqual(len(items), 2)
        self.assertEqual(resolve.hex_values("\n".join(lines)), {0x10})
