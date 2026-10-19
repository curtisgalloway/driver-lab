#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Validate the language-neutral conformance corpus in tests/conformance/.

Checks all four conformance artifacts against the Python implementation:
- tests/conformance/prosefacts.json against prosefacts.py
- tests/conformance/fact-v1-vectors.json against records.py and speccheck.py
- tests/conformance/finding-codes.json catalog completeness and regex validity
- tests/conformance/cases.json fixture checks and BF-* regression entries
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
CONFORMANCE_DIR = REPO_ROOT / "tests" / "conformance"
SCRIPTS_DIR = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import prosefacts  # noqa: E402
import records  # noqa: E402
import spec  # noqa: E402
import speccheck  # noqa: E402

REQUIRED_MODULES = {
    "specload.py",
    "speccheck.py",
    "peripheral.py",
    "topology.py",
    "records.py",
    "specmd.py",
    "prosefacts.py",
    "resolve.py",
    "docresolve.py",
    "index.py",
    "corpus.py",
    "worklist.py",
    "inventory.py",
    "drift.py",
    "stubgen.py",
}

EXPECTED_BF_CODES = (
    [f"BF-USB-{i}" for i in range(1, 5)]
    + [f"BF-IMX-ISS-{i}" for i in range(1, 8)]
    + [f"BF-IMX-{i}" for i in range(8, 19)]
    + [f"BF-ARM-{i}" for i in range(19, 22)]
    + [f"BF-GW-{i}" for i in range(22, 28)]
)


class ConformanceCorpusTests(unittest.TestCase):
    """Validate tests/conformance/*.json against spec.py, records.py, and prosefacts.py."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.api = types.SimpleNamespace(
            validate_file=spec.validate_file,
            load_extension=spec.load_extension,
        )
        cls.schemas = spec.load_schemas()

    def test_prosefacts_conformance(self) -> None:
        path = CONFORMANCE_DIR / "prosefacts.json"
        self.assertTrue(path.is_file(), f"missing {path}")
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], 1)
        self.assertEqual(doc["opt_out_token"], prosefacts.OPT_OUT)

        cases = doc["cases"]
        self.assertGreaterEqual(len(cases), 20)
        categories = {c["category"] for c in cases}
        for required_cat in (
            "hex_literal",
            "register_name",
            "bitfield",
            "bit_width",
            "timing_bound",
            "code_fence",
            "inline_code",
            "url",
            "sha256_digest",
            "model_name",
            "shell_variable",
            "opt_out",
        ):
            self.assertIn(required_cat, categories)

        positives = [c for c in cases if c["positive"]]
        negatives = [c for c in cases if not c["positive"]]
        self.assertGreater(len(positives), 0)
        self.assertGreater(len(negatives), 0)

        for case in cases:
            with self.subTest(case=case["id"]):
                actual = prosefacts.findings(case["text"])
                expected_tuples = [tuple(t) for t in case["tuples"]]
                self.assertEqual(actual, expected_tuples)
                self.assertEqual(bool(actual), case["positive"])
                self.assertEqual(case["expected"], case["findings"])
                self.assertEqual(len(actual), len(case["findings"]))
                for (line, col, what), item in zip(actual, case["findings"]):
                    self.assertEqual(line, item["line"])
                    self.assertEqual(col, item["column"])
                    self.assertEqual(what, item["what"])
                    self.assertEqual(prosefacts.message(what), item["message"])

    def test_fact_v1_vectors_conformance(self) -> None:
        path = CONFORMANCE_DIR / "fact-v1-vectors.json"
        self.assertTrue(path.is_file(), f"missing {path}")
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], 1)
        self.assertEqual(doc["basis_version"], "fact-v1")

        for cvec in doc["canonical_json_vectors"]:
            with self.subTest(canonical=cvec["id"]):
                canon = records.canonical(cvec["input"])
                self.assertEqual(canon, cvec["canonical_json"])
                self.assertEqual(records.sha256(canon), cvec["sha256"])

        recomputed_flat = []
        for suite in doc["suites"]:
            with self.subTest(suite=suite["id"]):
                roots = [REPO_ROOT / p for p in suite["roots"]]
                context_roots = [REPO_ROOT / p for p in suite["context_roots"]]
                checker = speccheck.check(
                    self.api,
                    self.schemas,
                    roots,
                    context_roots=context_roots,
                )
                actual_vectors = []
                for entry in checker.status:
                    f = entry["file"]
                    if f.root.context:
                        continue
                    rel_path = f.path.relative_to(REPO_ROOT).as_posix()
                    for r in entry["rows"]:
                        vec = {
                            "suite": suite["id"],
                            "spec_file": rel_path,
                            "root": f.root.label,
                            "spec": f.spec_id,
                            "fact_id": r["key"],
                            "key": r["key"],
                            "ref": r["ref"],
                            "kind": r["kind"],
                            "status": r["status"],
                            "verdict": r["verdict"],
                            "basis": r["basis"],
                            "recorded": r["recorded"],
                            "upstream": r["upstream"],
                            "changed": r["changed"],
                            "reason": r["reason"],
                            "second_reader": r["second_reader"],
                        }
                        actual_vectors.append(vec)
                        recomputed_flat.append(vec)
                self.assertEqual(actual_vectors, suite["vectors"])

        self.assertEqual(recomputed_flat, doc["vectors"])

    def test_finding_codes_catalog(self) -> None:
        path = CONFORMANCE_DIR / "finding-codes.json"
        self.assertTrue(path.is_file(), f"missing {path}")
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], 1)

        codes = doc["codes"]
        code_ids = [c["code"] for c in codes]
        self.assertEqual(len(code_ids), len(set(code_ids)), "duplicate code IDs in catalog")

        covered_modules = {c["module"] for c in codes}
        for mod in REQUIRED_MODULES:
            self.assertIn(mod, covered_modules, f"module {mod} missing from finding-codes.json")

        for bf_code in EXPECTED_BF_CODES:
            self.assertIn(bf_code, code_ids, f"missing regression code {bf_code}")

        auto5_codes = [c["code"] for c in codes if c["category"] == "auto5_warning"]
        self.assertGreaterEqual(len(auto5_codes), 4)

        for entry in codes:
            with self.subTest(code=entry["code"]):
                self.assertIn(entry["level"], ("error", "warning", "info", "clean"))
                compiled = re.compile(entry["pattern"])
                self.assertIsNotNone(compiled)

    def test_cases_conformance(self) -> None:
        codes_doc = json.loads((CONFORMANCE_DIR / "finding-codes.json").read_text(encoding="utf-8"))
        known_codes = {c["code"]: c for c in codes_doc["codes"]}

        cases_path = CONFORMANCE_DIR / "cases.json"
        self.assertTrue(cases_path.is_file(), f"missing {cases_path}")
        doc = json.loads(cases_path.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], 1)

        for fcase in doc["fixture_cases"]:
            with self.subTest(fixture_case=fcase["id"]):
                roots = [REPO_ROOT / p for p in fcase["roots"]]
                context_roots = [REPO_ROOT / p for p in fcase["context_roots"]]
                checker = speccheck.check(
                    self.api,
                    self.schemas,
                    roots,
                    context_roots=context_roots,
                    **fcase.get("options", {}),
                )
                ordered = spec._ordered(checker.findings)
                errors = sum(1 for f in ordered if f.level == "error")
                self.assertEqual(errors == 0, fcase["ok"])
                self.assertEqual(0 if errors == 0 else 1, fcase["exit_code"])
                self.assertEqual(len(ordered), len(fcase["findings"]))

                for actual, expected in zip(ordered, fcase["findings"]):
                    rel_path = Path(actual.path).relative_to(REPO_ROOT).as_posix()
                    self.assertIn(expected["code"], known_codes)
                    self.assertEqual(actual.level, expected["level"])
                    self.assertEqual(rel_path, expected["path"])
                    self.assertEqual(actual.line, expected["line"])
                    self.assertEqual(actual.column, expected["column"])
                    self.assertEqual(actual.message, expected["message"])
                    self.assertRegex(actual.message, expected["message_pattern"])

        bf_cases = doc["bf_regression_cases"]
        self.assertEqual([c["code"] for c in bf_cases], EXPECTED_BF_CODES)
        for bcase in bf_cases:
            with self.subTest(bf_case=bcase["id"]):
                self.assertIn(bcase["code"], known_codes)
                self.assertIsInstance(bcase["ok"], bool)
                self.assertIn(bcase["level"], ("error", "warning", "info", "clean"))
                self.assertTrue(bcase["path"])
                self.assertGreaterEqual(bcase["line"], 1)
                self.assertIsNotNone(re.compile(bcase["pattern"]))


if __name__ == "__main__":
    unittest.main()
