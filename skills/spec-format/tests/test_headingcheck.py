# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Issue #96: opt-in heading checks at citation locations, without live network."""

import contextlib
import io
from pathlib import Path
import sys
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import explorer
import spec
from test_check import check, chip, marker
from test_explorer import BLOB, DOCS, heading_fact, RENDERED
from test_render_html import Fixture


class HeadingCheckTests(Fixture):
    """Run the real checker and explorer parser with controlled fetched HTML."""

    def setUp(self):
        super().setUp()
        self.path.write_text(
            chip(
                docs=DOCS,
                facts=heading_fact("a", "kernel_old")
                + heading_fact("b", "Missing heading"),
            )
        )

    def heading_warnings(self, result):
        return [f for f in result["findings"] if "heading " in f["message"]]

    def test_default_check_never_fetches(self):
        with mock.patch.object(explorer, "_get") as fetch:
            code, result = check(self.root)
        self.assertEqual(code, 0, result)
        self.assertEqual(self.heading_warnings(result), [])
        fetch.assert_not_called()

    def test_missing_heading_warns_at_locator_and_fetches_once(self):
        with mock.patch.object(explorer, "_get", return_value=RENDERED) as fetch:
            code, result = check(self.root, "--resolve-headings")
        self.assertEqual(code, 0, result)
        fetch.assert_called_once_with(*explorer.fetch_url(BLOB))
        warnings = self.heading_warnings(result)
        self.assertEqual(len(warnings), 1, result)
        finding = warnings[0]
        self.assertEqual(finding["level"], "warning")
        self.assertIn("Missing heading", finding["message"])
        self.assertIn("no such heading", finding["message"])
        self.assertEqual(finding["path"], str(self.path))
        line = self.path.read_text().splitlines()[finding["line"] - 1]
        self.assertIn("Missing heading", line)
        self.assertGreater(finding["column"], 1)

    def test_exact_heading_text_required(self):
        self.path.write_text(chip(docs=DOCS, facts=heading_fact("a", "otg_mode")))
        with mock.patch.object(
            explorer,
            "_get",
            return_value='<h2 id="otg">otg_mode (Raspberry Pi 4 only)</h2>',
        ):
            code, result = check(self.root, "--resolve-headings")
        self.assertEqual(code, 0, result)
        self.assertEqual(len(self.heading_warnings(result)), 1)

    def test_each_citation_warns_but_document_is_fetched_once(self):
        self.path.write_text(
            chip(
                docs=DOCS,
                facts=heading_fact("a", "Missing") + heading_fact("b", "Missing"),
            )
        )
        with mock.patch.object(explorer, "_get", return_value=RENDERED) as fetch:
            code, result = check(self.root, "--resolve-headings")
        self.assertEqual(code, 0, result)
        fetch.assert_called_once()
        self.assertEqual(len(self.heading_warnings(result)), 2)

    def test_network_failure_warns_without_claiming_heading_absent(self):
        with mock.patch.object(explorer, "_get", side_effect=OSError("offline")):
            code, result = check(self.root, "--resolve-headings")
        self.assertEqual(code, 0, result)
        warnings = self.heading_warnings(result)
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all("fetch failed: OSError" in f["message"] for f in warnings))

    def test_wiki_is_supported_but_unpinned_blob_and_other_hosts_skip(self):
        for url, supported in (
            ("https://github.com/o/r/wiki/Guide", True),
            ("https://github.com/o/r/blob/main/Guide.md", False),
            ("https://example.invalid/Guide", False),
        ):
            self.path.write_text(
                chip(
                    docs=DOCS.replace(BLOB, url), facts=heading_fact("a", "kernel_old")
                )
            )
            with self.subTest(url=url), mock.patch.object(
                explorer, "_get", return_value=RENDERED
            ) as fetch:
                code, result = check(self.root, "--resolve-headings")
            self.assertEqual(code, 0, result)
            if supported:
                fetch.assert_called_once()
                self.assertEqual(self.heading_warnings(result), [])
            else:
                fetch.assert_not_called()
                self.assertIn(
                    "unsupported document URL",
                    self.heading_warnings(result)[0]["message"],
                )

    def test_invalid_input_prevents_network(self):
        self.path.write_text(
            self.path.read_text().replace("doc: guide", "doc: undeclared")
        )
        with mock.patch.object(explorer, "_get") as fetch:
            code, result = check(self.root, "--resolve-headings")
        self.assertEqual(code, 1, result)
        fetch.assert_not_called()

    def test_context_roots_are_not_fetched(self):
        dependency = self.root.parent / "dependency"
        dependency.mkdir()
        (dependency / "board-specs.yaml").write_text(marker("dependency"))
        (dependency / "other.spec.yaml").write_text(
            chip(
                sid="other",
                docs=DOCS.replace(BLOB, "https://github.com/o/r/wiki/Dependency"),
                facts=heading_fact("a", "Missing"),
            )
        )
        with mock.patch.object(explorer, "_get", return_value=RENDERED) as fetch:
            code, result = check(
                self.root, "--context-root", dependency, "--resolve-headings"
            )
        self.assertEqual(code, 0, result)
        fetch.assert_called_once_with(*explorer.fetch_url(BLOB))
        self.assertTrue(
            all(f["path"] == str(self.path) for f in self.heading_warnings(result))
        )

    def test_terminal_output_and_unanchored_bullet(self):
        self.path.write_text(
            chip(docs=DOCS, facts=heading_fact("a", "System registers"))
        )
        out = io.StringIO()
        with mock.patch.object(
            explorer, "_get", return_value="<ul><li>System registers</li></ul>"
        ), contextlib.redirect_stdout(out):
            code = spec.main(["check", str(self.root), "--resolve-headings"])
        self.assertEqual(code, 0)
        self.assertIn(
            "warning: a: heading 'System registers': no such heading", out.getvalue()
        )

    def test_nested_premise_heading_is_checked(self):
        data = yaml.safe_load(self.path.read_text())
        data["facts"] = [
            dict(
                id="a",
                section="quick-facts",
                title="A",
                claim="A follows.",
                todo={"check": "hardware", "text": "Check A."},
                support=[
                    {
                        "class": "inference",
                        "derivation": "It follows.",
                        "premises": [
                            {
                                "states": "Premise A.",
                                "support": [
                                    {
                                        "class": "doc",
                                        "doc": "guide",
                                        "at": [{"heading": "Missing"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            )
        ]
        self.write(data)
        with mock.patch.object(explorer, "_get", return_value=RENDERED):
            code, result = check(self.root, "--resolve-headings")
        self.assertEqual(code, 0, result)
        self.assertEqual(len(self.heading_warnings(result)), 1)
