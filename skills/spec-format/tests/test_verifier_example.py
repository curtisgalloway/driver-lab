# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Run the exact worked record from spec-verifier through the format 2 gate."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
VERIFIER = HERE.parents[1] / "spec-verifier"
sys.path.insert(0, str(HERE.parent / "scripts"))
import spec as spec_cli
from specload import load_strict


def run(*args):
    output, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
        code = spec_cli.main([str(arg) for arg in args] + ["--json"])
    return code, json.loads(output.getvalue())


class VerifierExample(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name) / "fixture-root"
        shutil.copytree(VERIFIER / "examples" / "format-2", self.root)
        text = (VERIFIER / "SKILL.md").read_text(encoding="utf-8")
        example = text.split("## Complete worked record\n", 1)[1]
        record = example.split("```yaml\n", 1)[1].split("```", 1)[0]
        self.record = self.root / "resources" / "widget.verify.yaml"
        self.record.write_text(record, encoding="utf-8")

    def test_worked_record_passes_pr_gate_verbatim(self):
        code, result = run("check", self.root, "--require-verified", "pr")
        self.assertEqual(code, 0, result)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["findings"], [], result)
        data = load_strict(self.record)
        spec = self.root / "widget.spec.yaml"
        self.assertEqual(data["spec_sha256"], hashlib.sha256(spec.read_bytes()).hexdigest())
        manual = self.root / "resources" / "widget-trm.txt"
        self.assertEqual(data["sources"][0]["sha256"],
                         hashlib.sha256(manual.read_bytes()).hexdigest())
        code, status = run("status", self.root)
        self.assertEqual(code, 0, status)
        facts = {row["key"]: row for row in status["specs"][0]["facts"]}
        self.assertEqual(set(facts), {"reset-cycles", "reset-budget", "power-on-state"})
        self.assertEqual({row["status"] for row in facts.values()}, {"current"})
        self.assertEqual(facts["reset-cycles"]["second_reader"], "present")
        self.assertEqual(facts["power-on-state"]["verdict"], "GAP")

    def test_missing_second_reader_enters_delta_and_fails_gate(self):
        data = load_strict(self.record)
        del data["verdicts"]["reset-cycles"]["readers"]
        self.record.write_text(json.dumps(data), encoding="utf-8")
        code, status = run("status", self.root, "--stale")
        self.assertEqual(code, 0, status)
        self.assertEqual([row["key"] for row in status["specs"][0]["facts"]],
                         ["reset-cycles"])
        code, checked = run("check", self.root, "--require-verified", "pr")
        self.assertEqual(code, 1, checked)
        self.assertTrue(any("second reader" in finding["message"]
                            for finding in checked["findings"]), checked)

    def test_changed_fact_stales_its_dependent_but_not_the_gap(self):
        spec = self.root / "widget.spec.yaml"
        spec.write_text(spec.read_text(encoding="utf-8").replace(
            "Reset completes in 10", "Reset completes in 11"), encoding="utf-8")
        code, status = run("status", self.root, "--stale")
        self.assertEqual(code, 0, status)
        self.assertEqual({row["key"]: row["status"]
                          for row in status["specs"][0]["facts"]},
                         {"reset-cycles": "stale", "reset-budget": "stale"})
        code, checked = run("check", self.root, "--require-verified", "pr")
        self.assertEqual(code, 1, checked)
        self.assertTrue(any("verdict stale" in finding["message"]
                            for finding in checked["findings"]), checked)
