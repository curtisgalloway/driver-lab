#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the corpus ledger (#153): `corpus.yaml` in `spec.py check` and `spec.py corpus`.

Each test copies fixtures/check/good_root to a temporary root, installs
fixtures/corpus/good_root.corpus.yaml as its ledger, and changes one thing.

Run in the pinned environment:
  .venv-spec/bin/python -m unittest discover -s skills/spec-format/tests -v
"""

import contextlib
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "spec.py"
FIX = HERE / "fixtures"
GOOD = FIX / "check" / "good_root"
LEDGER = FIX / "corpus" / "good_root.corpus.yaml"
sys.path.insert(0, str(SCRIPT.parent))
import spec as spec_cli  # noqa: E402

SKILL = ["--public-skill", "widget-board-tools"]


def run(command, *argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = spec_cli.main([command, "--json", *[str(a) for a in argv]])
    return code, json.loads(out.getvalue())


def errors(result):
    return [f["message"] for f in result["findings"] if f["level"] == "error"]


class CorpusTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name) / "good_root"
        shutil.copytree(GOOD, self.root)
        self.ledger = self.root / "corpus.yaml"
        shutil.copy(LEDGER, self.ledger)

    def tearDown(self):
        self._tmp.cleanup()

    def edit(self, path, old, new):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def check(self):
        return run("check", self.root, *SKILL)

    def assert_one_error(self, needle):
        code, result = self.check()
        found = errors(result)
        self.assertEqual(code, 1, found)
        self.assertEqual(len(found), 1, found)
        self.assertIn(needle, found[0])
        return result

    # --- positive ----------------------------------------------------------------------------

    def test_good_ledger_checks_clean(self):
        code, result = self.check()
        self.assertEqual((code, errors(result)), (0, []))

    def test_corpus_reports_coverage(self):
        code, result = run("corpus", self.root, *SKILL)
        self.assertEqual((code, errors(result)), (0, []))
        cov = result["roots"][0]["coverage"]
        self.assertEqual(cov["documents"]["counts"], {"spec": 3, "planned": 1, "excluded": 0,
                                                              "unresolved": 0})
        self.assertEqual(cov["blocks"]["counts"], {"spec": 1, "planned": 1, "excluded": 1,
                                                           "unresolved": 0})

    def test_root_without_ledger_passes_check(self):
        self.ledger.unlink()
        code, result = self.check()
        self.assertEqual((code, errors(result)), (0, []))

    # --- negative ----------------------------------------------------------------------------

    def test_corpus_fails_without_ledger(self):
        self.ledger.unlink()
        code, result = run("corpus", self.root, *SKILL)
        self.assertEqual(code, 1)
        self.assertIn("has no corpus ledger", " ".join(errors(result)))

    def test_corpus_names_the_ledger_state(self):
        _, result = run("corpus", self.root, *SKILL)
        self.assertEqual(result["roots"][0]["ledger"], "ok")
        self.edit(self.ledger, "format: 2\n", "format: 2\nextra: key\n")
        _, result = run("corpus", self.root, *SKILL)
        self.assertEqual((result["roots"][0]["ledger"], result["roots"][0]["coverage"]),
                         ("invalid", None))
        self.ledger.unlink()
        _, result = run("corpus", self.root, *SKILL)
        self.assertEqual(result["roots"][0]["ledger"], "missing")

    def test_missing_disposition(self):
        self.edit(self.ledger, ', disposition: "excluded: no public documentation"', "")
        self.assert_one_error("'disposition' is a required property")

    def test_malformed_disposition(self):
        self.edit(self.ledger, '"excluded: no public documentation"', '"dropped"')
        self.assert_one_error("a disposition is spec:<id>")

    def test_empty_reason(self):
        self.edit(self.ledger, '"excluded: no public documentation"', '"excluded: "')
        self.assert_one_error("a disposition is spec:<id>")

    def test_spec_disposition_resolves(self):
        self.edit(self.ledger, '"spec:widgetsoc"', '"spec:nosuchsoc"')
        self.assert_one_error("no spec 'nosuchsoc'")

    def test_fact_disposition_resolves(self):
        self.edit(self.ledger, '"spec:widgetsoc#uart0"', '"spec:widgetsoc#uart9"')
        self.assert_one_error("has no fact 'uart9'")

    def test_cited_document_missing_from_ledger(self):
        self.edit(self.ledger, '  - {name: uart-trm, title: Widget UART TRM, access: public, '
                               'subsystem: uart, disposition: "spec:widgetuart"}\n', "")
        result = self.assert_one_error("documents entry 'uart-trm' is not in the root's corpus")
        [found] = [f for f in result["findings"] if f["level"] == "error"]
        self.assertTrue(found["path"].endswith("widgetuart.spec.yaml"), found)

    def test_document_spec_must_list_the_document(self):
        self.edit(self.ledger, 'disposition: "spec:widgetuart"', 'disposition: "spec:widgetboard"')
        self.assert_one_error("spec 'widgetboard' does not list document 'uart-trm'")

    def test_fact_disposition_reaches_an_overlay(self):
        overlay = self.root / "uart-overlay.spec.yaml"
        overlay.write_text(
            "# SPDX-FileCopyrightText: 2026 contributors\n"
            "# SPDX-License-Identifier: Apache-2.0\n"
            "format: 2\nkind: overlay\noverlays: widgetuart\nfacts:\n"
            "  - id: uart-erratum\n    section: gotchas\n    title: Erratum\n"
            "    claim: The FIFO level reads one low.\n"
            "    todo: {check: document, text: find the errata sheet.}\n", encoding="utf-8")
        self.edit(self.ledger, '"planned: second lap"', '"spec:widgetuart#uart-erratum"')
        code, result = self.check()
        self.assertEqual((code, errors(result)), (0, []))

    def test_disposition_may_not_name_a_later_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            later = pathlib.Path(tmp) / "later"
            later.mkdir()
            (later / "board-specs.yaml").write_text(
                "# SPDX-FileCopyrightText: 2026 contributors\n"
                "# SPDX-License-Identifier: Apache-2.0\n"
                "format: 2\nlayer: product\nname: later\nlicense: Apache-2.0\naccepts: []\n",
                encoding="utf-8")
            (later / "secret.spec.yaml").write_text(
                "# SPDX-FileCopyrightText: 2026 contributors\n"
                "# SPDX-License-Identifier: Apache-2.0\n"
                "format: 2\nkind: ip\nid: secret-block\nname: Secret\ntriggers: [secret]\n"
                "resources:\n  documents:\n    - {name: d, class: doc, title: D, "
                "url: \"https://example.invalid/d\"}\n"
                "facts:\n  - id: exists\n    section: gotchas\n    title: Exists\n"
                "    claim: The block exists.\n"
                "    todo: {check: document, text: find a document.}\n", encoding="utf-8")
            self.edit(self.ledger, '"planned: second lap"', '"spec:secret-block"')
            code, result = run("check", self.root, "--context-root", later, *SKILL)
            found = errors(result)
            self.assertEqual(code, 1, found)
            self.assertEqual(len(found), 1, found)
            self.assertIn("only in a layer that merges after this root's (public)", found[0])

    def test_misnamed_ledger_is_an_error(self):
        for name in ("corpus.yml", "Corpus.yaml", "corpus.yaml.bak"):
            with self.subTest(name=name):
                self.ledger.rename(self.root / name)
                self.assert_one_error("not read as a corpus ledger")
                (self.root / name).rename(self.ledger)

    def test_ledger_errors_leave_the_root_trusted(self):
        import types

        import speccheck

        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)

        def untrusted():
            checker = speccheck.check(api, spec_cli.load_schemas(), [self.root],
                                      public_skills=["widget-board-tools"])
            self.assertTrue([f for f in checker.findings if f.level == "error"])
            return checker.roots[0].untrusted

        self.edit(self.ledger, '"spec:widgetsoc"', '"spec:nosuchsoc"')
        self.edit(self.ledger, "  - {name: crypto,", "  - {name: gpu,")
        self.edit(self.ledger, '  - {name: uart-trm,', '  - {name: other-trm,')
        self.assertEqual(untrusted(), [])  # dispositions, a name twice, a missing document
        self.edit(self.ledger, "format: 2\n", "format: 2\nextra: key\n")
        self.assertEqual(untrusted(), [])  # a ledger the schema refuses

    def test_sha256_mismatch_makes_the_root_untrusted(self):
        import types

        import speccheck

        self.edit(self.ledger, "title: Widget SoC TRM, access",
                  f"title: Widget SoC TRM, sha256: {'a' * 64}, access")
        self.edit(self.root / "widgetsoc.spec.yaml", "pages: 120}",
                  f"pages: 120, sha256: {'b' * 64}}}")
        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)
        checker = speccheck.check(api, spec_cli.load_schemas(), [self.root],
                                  public_skills=["widget-board-tools"])
        [(_, message)] = checker.roots[0].untrusted
        self.assertIn("sha256 differs from the corpus ledger's", message)

    def test_unresolved_spec_disposition_is_not_counted_as_specified(self):
        import types

        import corpus
        import speccheck

        self.edit(self.ledger, '"spec:widgetsoc#uart0"', '"spec:widgetsoc#uart9"')
        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)
        checker = speccheck.check(api, spec_cli.load_schemas(), [self.root],
                                  public_skills=["widget-board-tools"])
        cov = corpus.coverage(checker.roots[0])
        self.assertEqual(cov["blocks"]["counts"],
                         {"spec": 0, "planned": 1, "excluded": 1, "unresolved": 1})
        self.assertIn("1 unresolved", corpus.summary(cov))

    def test_access_disagrees(self):
        self.edit(self.root / "ip" / "widgetuart.spec.yaml", "access: public}",
                  "access: registration}")
        self.assert_one_error("access registration differs from the corpus ledger's public")

    def test_sha256_disagrees(self):
        a, b = "a" * 64, "b" * 64
        self.edit(self.ledger, "title: Widget SoC TRM, access",
                  f"title: Widget SoC TRM, sha256: {a}, access")
        self.edit(self.root / "widgetsoc.spec.yaml", "pages: 120}", f"pages: 120, sha256: {b}}}")
        self.assert_one_error("sha256 differs from the corpus ledger's")

    def test_access_and_sha256_both_disagree(self):
        import types

        import speccheck

        a, b = "a" * 64, "b" * 64
        self.edit(self.root / "widgetsoc.spec.yaml", "pages: 120}", f"pages: 120, sha256: {b}}}")
        self.edit(self.ledger, "title: Widget SoC TRM, access",
                  f"title: Widget SoC TRM, sha256: {a}, access")
        self.edit(self.root / "ip" / "widgetuart.spec.yaml", "access: public}",
                  "access: registration}")
        code, result = self.check()
        found = errors(result)
        self.assertEqual(code, 1, found)
        self.assertEqual(len(found), 2, found)
        self.assertTrue(any("access registration differs" in m for m in found), found)
        self.assertTrue(any("sha256 differs" in m for m in found), found)
        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)
        checker = speccheck.check(api, spec_cli.load_schemas(), [self.root],
                                  public_skills=["widget-board-tools"])
        self.assertTrue(checker.roots[0].untrusted)

    def test_sha256_agrees(self):
        a = "a" * 64
        self.edit(self.ledger, "title: Widget SoC TRM, access",
                  f"title: Widget SoC TRM, sha256: {a}, access")
        self.edit(self.root / "widgetsoc.spec.yaml", "pages: 120}", f"pages: 120, sha256: {a}}}")
        code, result = self.check()
        self.assertEqual((code, errors(result)), (0, []))

    def test_name_twice(self):
        self.edit(self.ledger, "  - {name: crypto,", "  - {name: gpu,")
        self.assert_one_error("'gpu' is listed twice")

    def test_private_under_public_root(self):
        self.edit(self.ledger, "access: registration", "access: private")
        self.assert_one_error("access: private under a public root")

    def test_internal_names_its_rename(self):
        self.edit(self.ledger, "access: registration", "access: internal")
        self.assert_one_error("internal was renamed private")

    def test_placeholder(self):
        self.edit(self.ledger, '"planned: second lap"', '"planned: <milestone>"')
        self.assert_one_error("unsubstituted template placeholder")

    def test_nested_ledger(self):
        shutil.copy(self.ledger, self.root / "ip" / "corpus.yaml")
        self.assert_one_error("a corpus ledger lives beside the root's board-specs.yaml")

    # --- rendering ---------------------------------------------------------------------------

    def test_markdown_view_shows_coverage(self):
        code, result = run("render", self.root, *SKILL, "--format", "md")
        self.assertEqual(code, 0, result)
        view = result["markdown"]
        self.assertIn("## Corpus coverage (generated): good", view)
        self.assertIn("`excluded: no public documentation`", view)
        self.assertIn("1 spec\\, 1 planned\\, 1 excluded", view)

    def test_html_viewer_shows_coverage(self):
        code, result = run("render", self.root, *SKILL, "--format", "html")
        self.assertEqual(code, 0, result)
        self.assertIn("Corpus coverage (generated): good", result["html"])
        self.assertIn("<td>excluded: no public documentation</td>", result["html"])

    def test_markdown_view_without_ledger_has_no_coverage(self):
        self.ledger.unlink()
        code, result = run("render", self.root, *SKILL, "--format", "md")
        self.assertEqual(code, 0, result)
        self.assertNotIn("Corpus coverage", result["markdown"])

    def test_atlas_carries_coverage(self):
        import atlas
        import types

        import speccheck

        api = types.SimpleNamespace(validate_file=spec_cli.validate_file,
                                    load_extension=spec_cli.load_extension)
        checker = speccheck.check(api, spec_cli.load_schemas(), [self.root],
                                  public_skills=["widget-board-tools"])
        payload = atlas.data(checker, "widgetboard")
        [entry] = payload["corpus"]
        self.assertEqual(entry["root"], "good")
        self.assertEqual(entry["blocks"]["counts"], {"spec": 1, "planned": 1, "excluded": 1,
                                                           "unresolved": 0})
        self.assertEqual([r["name"] for r in entry["documents"]["rows"]],
                         ["widget-trm", "uart-trm", "widget-product-page", "widget-errata"])

    def test_validate_picks_the_corpus_schema(self):
        code, result = run("validate", self.ledger)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["files"][0]["schema"], "corpus")


if __name__ == "__main__":
    unittest.main()
