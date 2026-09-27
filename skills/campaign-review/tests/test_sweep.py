#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""C2 mutation tests on copies of the real campaign, with exact expected sets."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/campaign-review/scripts"
sys.path.insert(0, str(SCRIPTS))
import index_check as check  # pylint: disable=wrong-import-position
import pinned_file_adapter as adapter  # pylint: disable=wrong-import-position
import source_registry  # pylint: disable=wrong-import-position
import sweep  # pylint: disable=wrong-import-position


def inputs():
    """Copy e1000 and align active qualification context to isolate each mutation."""
    claims = check.read_yaml(ROOT / "evals/e1000/claims.yaml")
    status = check.read_yaml(ROOT / "evals/e1000/status.yaml")
    registry = check.read_yaml(ROOT / "evals/e1000/sources.yaml")
    for entry in status["entries"]:
        if entry["kind"] == "qualification":
            basis = copy.deepcopy(status["bases"][entry["basis"]])
            basis.update(
                spec_revision=8, spec_sha256=status["revisions"]["8"]["spec_sha256"]
            )
            entry["basis"] = "matrix-" + entry["id"]
            status["bases"][entry["basis"]] = basis
    return claims, status, registry


def source(registry, sid):
    """Select a source by its public local ID."""
    return next(s for s in registry["sources"] if s["id"] == sid)


def mutate(registry, sid, sections=None, checks=None, scenarios=None):
    """Record a reviewed end-to-end mapping to one different identity."""
    row = source(registry, sid)
    old = row["sha256"]
    row["sha256"] = "a" * 64
    row["changes"] = [
        dict(
            from_sha256=old,
            to_sha256=row["sha256"],
            since="matrix-change",
            reviewed=True,
            sections=sections,
            checks=checks,
            scenarios=scenarios,
            evidence=["synthetic reviewed diff"],
        )
    ]
    return row


def newly_affected(result):
    """Return changed active entries, excluding preserved historical staleness."""
    return sorted(
        e["id"] for e in result["entries"] if e["previous_state"] == "current"
    )


def matrix():
    """Produce all nine C2 rows with independently declared expected entry sets."""
    results = [f"result-Q{i:02}" for i in range(1, 29)] + ["candidate-CF2-a2"]
    qualifications = [f"qualification-Q{i:02}" for i in range(1, 29)]
    observations = [f"EM{i}" for i in range(1, 9)]
    rows = []
    for name in [
        "spec",
        "document",
        "kernel",
        "harness",
        "emulator",
        "candidate",
        "hardware",
        "fixture",
        "model",
    ]:
        claims, status, registry = inputs()
        expected, contested = [], []
        if name == "spec":
            row = mutate(registry, "spec", sections=["5.3"])
            row.update(revision=9, version="revision 9", requirement_change=True)
            expected = results + ["qualification-Q01", "verify-r8-round2"]
        elif name == "document":
            mutate(registry, "8254x-sdm")
            expected = ["verify-r8-round2"]
        elif name == "kernel":
            source(registry, "linux-e1000_main-c")["version"] = "new release"
            expected = ["verify-r8-round2"]
        elif name == "harness":
            mutate(registry, "harness", checks=["MAC matches QEMU's"])
            expected = ["qualification-Q01"]
        elif name == "emulator":
            mutate(registry, "qemu-e1000")
            expected = results + qualifications + observations
        elif name == "candidate":
            mutate(registry, "candidate")
            expected = results
        elif name == "hardware":
            registry["contradictions"] = [
                dict(
                    observation="EM1",
                    since="matrix-change",
                    conflict="spec/section12.md#conflict-EM1",
                )
            ]
            registry["premises"] = {
                c["id"]: ["EM1" if c["id"] == "Q01" else "EM2"]
                for c in claims["claims"]
            }
            expected, contested = ["qualification-Q01"], ["EM1"]
        else:
            row = copy.deepcopy(source(registry, "candidate"))
            row.update(
                id=name, kind=name, version="new identity", sha256="a" * 64, file=None
            )
            registry["sources"].append(row)
        result = sweep.sweep(claims, status, registry)
        actual_stale = sorted(
            e["id"]
            for e in result["entries"]
            if e["previous_state"] == "current" and e["state"] == "stale"
        )
        actual_contested = sorted(
            e["id"]
            for e in result["entries"]
            if e["previous_state"] == "current" and e["state"] == "contested"
        )
        affected = set(expected + contested)
        units = [u for u in result["stopping"]["queue"] if affected & set(u["entries"])]
        expected_kinds = {
            "spec": ["acceptance-set-rerun", "re-verification", "requalification"],
            "document": ["re-verification"],
            "kernel": ["re-verification"],
            "harness": ["requalification"],
            "emulator": ["acceptance-set-rerun", "requalification"],
            "candidate": ["acceptance-set-rerun"],
            "hardware": ["re-verification", "requalification"],
            "fixture": [],
            "model": [],
        }[name]
        kinds = sorted({u["kind"] for u in units})
        covered = set(e for u in units for e in u["entries"])
        queue_ok = kinds == expected_kinds and affected <= covered
        rows.append(
            dict(
                row=name,
                expected_stale=sorted(expected),
                stale=actual_stale,
                expected_contested=contested,
                contested=actual_contested,
                expected_unit_kinds=expected_kinds,
                unit_kinds=kinds,
                units=units,
                queue_ok=queue_ok,
                ok=(
                    actual_stale == sorted(expected)
                    and actual_contested == contested
                    and queue_ok
                ),
            )
        )
    return rows


class SweepTests(unittest.TestCase):
    """Exact invalidation, widening, exclusion and read-boundary checks."""

    def setUp(self):
        self.claims, self.status, self.registry = inputs()

    def run_sweep(self):
        return sweep.sweep(self.claims, self.status, self.registry)

    def test_matrix(self):
        for row in matrix():
            with self.subTest(row=row["row"]):
                self.assertEqual(row["stale"], row["expected_stale"])
                self.assertEqual(row["contested"], row["expected_contested"])
                self.assertTrue(row["queue_ok"], row)

    def test_baseline_and_no_source_access_or_mutation(self):
        before = copy.deepcopy((self.claims, self.status, self.registry))
        with mock.patch.object(
            Path, "open", side_effect=AssertionError("source read")
        ), mock.patch.object(
            Path, "read_bytes", side_effect=AssertionError("source read")
        ), mock.patch.object(
            check, "harness_check_names", side_effect=AssertionError("source parsed")
        ):
            result = self.run_sweep()
        self.assertEqual(newly_affected(result), [])
        self.assertEqual(before, (self.claims, self.status, self.registry))
        self.assertTrue(
            all(e["id"] not in result["eligible"] for e in result["entries"])
        )
        self.assertEqual(len(result["entries"]), 83)

    def test_real_index(self):
        self.status = check.read_yaml(ROOT / "evals/e1000/status.yaml")
        result = self.run_sweep()
        self.assertEqual(
            newly_affected(result),
            [
                "qualification-" + c
                for c in [
                    "Q01",
                    "Q02",
                    "Q03",
                    "Q11",
                    "Q12",
                    "Q13",
                    "Q14",
                    "Q15",
                    "Q16",
                    "Q17",
                    "Q18",
                    "Q24",
                    "Q26",
                ]
            ],
        )
        self.assertEqual(result["counts"], dict(current=84, stale=96, superseded=13))
        self.assertEqual(result["unmapped_harness"], [])
        by_id = {e["id"]: e for e in result["entries"]}
        self.assertEqual(by_id["qualification-Q01"]["stale_since"], "spec-r6")
        self.assertEqual(by_id["qualification-Q02"]["stale_since"], "spec-r7")

    def test_spec_wording_and_declared_dependencies(self):
        row = mutate(self.registry, "spec", sections=["5.3"])
        row.update(revision=9, requirement_change=False)
        basis = self.status["bases"]["verify-r8-round2"]
        basis["dependencies"] = []
        self.assertEqual(newly_affected(self.run_sweep()), ["qualification-Q01"])
        basis["dependencies"] = ["5"]
        self.assertEqual(
            newly_affected(self.run_sweep()), ["qualification-Q01", "verify-r8-round2"]
        )
        self.assertFalse(sweep.overlap(["5.1"], ["5.10"]))
        self.assertTrue(sweep.overlap(["5"], ["5.10"]))

    def test_spec_unknown_header_widens(self):
        row = source(self.registry, "spec")
        row.update(revision=9, sha256="a" * 64)
        expected = [f"qualification-Q{i:02}" for i in range(1, 29)]
        expected += [f"result-Q{i:02}" for i in range(1, 29)]
        expected += ["candidate-CF2-a2", "verify-r8-round2"]
        self.assertEqual(newly_affected(self.run_sweep()), sorted(expected))

    def test_document_mapping_and_missing_citations(self):
        mutate(self.registry, "8254x-sdm", sections=["13.4"])
        self.registry["citations"] = {"verify-r8-round2": {"8254x-sdm": ["14"]}}
        self.assertEqual(newly_affected(self.run_sweep()), [])
        self.registry["citations"]["verify-r8-round2"]["8254x-sdm"] = ["13"]
        self.assertEqual(newly_affected(self.run_sweep()), ["verify-r8-round2"])
        self.registry["citations"] = {}
        self.assertEqual(newly_affected(self.run_sweep()), ["verify-r8-round2"])

    def test_kernel_leaves_manual_verdicts_current(self):
        mutate(self.registry, "linux-e1000_main-c")
        entry = next(e for e in self.status["entries"] if e["id"] == "verify-r8-round2")
        entry["evidence_classes"] = ["databook"]
        self.assertEqual(newly_affected(self.run_sweep()), [])

    def test_reference_control_runs(self):
        mutate(self.registry, "reference")
        result = self.run_sweep()
        expected = {
            run
            for c in self.claims["claims"]
            for d in c["defects"]
            for run in d["control_runs"]
        }
        self.assertEqual({c["id"] for c in result["stale_controls"]}, expected)
        self.assertEqual(newly_affected(result), [])

    def test_harness_widening_and_bad_names(self):
        row = mutate(
            self.registry, "harness", checks=["not a check"], scenarios=["itr"]
        )
        result = self.run_sweep()
        expected = sorted(
            "qualification-" + c["id"]
            for c in self.claims["claims"]
            if "itr" in c["scenarios"]
        )
        self.assertEqual(newly_affected(result), expected)
        self.assertEqual(result["unmapped_harness"], [])
        for mapping in [
            dict(checks=None, scenarios=None),
            dict(checks=["MAC matches QEMU's"], scenarios=None, reviewed=False),
            dict(checks=["unknown check"], scenarios=["unknown scenario"]),
        ]:
            row["changes"][0].update(mapping)
            result = self.run_sweep()
            self.assertEqual(
                newly_affected(result), [f"qualification-Q{i:02}" for i in range(1, 29)]
            )
            self.assertEqual(result["unmapped_harness"], ["harness"])

    def test_mapping_must_cover_exact_old_hash(self):
        row = mutate(self.registry, "harness", checks=["MAC matches QEMU's"])
        row["changes"][0]["from_sha256"] = "b" * 64
        self.assertEqual(len(newly_affected(self.run_sweep())), 28)
        row["changes"][0]["to_sha256"] = "b" * 64
        with self.assertRaisesRegex(check.Invalid, "current hash"):
            self.run_sweep()

    def test_guest_kernel_and_image(self):
        mutate(self.registry, "guest-kernel")
        self.assertEqual(len(newly_affected(self.run_sweep())), 65)
        self.claims, self.status, self.registry = inputs()
        mutate(self.registry, "guest-image-candidate")
        self.assertEqual(len(newly_affected(self.run_sweep())), 29)

    def test_emulated_reading_follows_observation_dependency(self):
        entry = next(e for e in self.status["entries"] if e["id"] == "verify-r8-round2")
        entry["evidence_classes"] = ["emulated"]
        mutate(self.registry, "qemu-e1000")
        self.assertIn("verify-r8-round2", newly_affected(self.run_sweep()))
        entry["evidence_classes"] = ["databook"]
        self.assertNotIn("verify-r8-round2", newly_affected(self.run_sweep()))

    def test_unrecorded_compiler_does_not_trigger(self):
        self.registry["sources"] = [
            s for s in self.registry["sources"] if s["kind"] != "toolchain"
        ]
        self.assertEqual(newly_affected(self.run_sweep()), [])
        row = copy.deepcopy(source(self.registry, "candidate"))
        row.update(
            id="compiler",
            kind="toolchain",
            version="new compiler",
            sha256=None,
            file=None,
        )
        self.registry["sources"].append(row)
        for basis in self.status["bases"].values():
            basis["toolchain"] = None
        self.assertEqual(newly_affected(self.run_sweep()), [])

    def test_recorded_toolchain(self):
        source(self.registry, "toolchain")["version"] = "exact compiler build"
        result = self.run_sweep()
        self.assertEqual(len(newly_affected(result)), 57)

    def test_hardware_widening_preserves_candidate(self):
        self.registry["contradictions"] = [
            dict(
                observation="EM1",
                since="new-run",
                conflict="spec/section12.md#conflict-EM1",
            )
        ]
        result = self.run_sweep()
        expected = sorted(
            "qualification-" + c["id"]
            for c in self.claims["claims"]
            if sweep.overlap(
                c["cites"],
                next(e["sections"] for e in self.status["entries"] if e["id"] == "EM1"),
            )
        )
        self.assertEqual(newly_affected(result), sorted(["EM1"] + expected))
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertTrue(
            all(f"result-Q{i:02}" in result["eligible"] for i in range(1, 29))
        )

    def test_invalid_registry_and_missing_identity(self):
        source(self.registry, "harness")["status"] = "blocked"
        result = self.run_sweep()
        self.assertEqual(result["unavailable"], ["harness"])
        self.assertFalse(result["ok"])
        for path in ["/private/file", "../escape", "sub/../../escape", "C:\\file"]:
            with self.subTest(path=path):
                source(self.registry, "harness")["file"]["path"] = path
                with self.assertRaises(check.Invalid):
                    self.run_sweep()

    def test_index_contested_observation_invalidates_dependents(self):
        entries = {entry["id"]: entry for entry in self.status["entries"]}
        entries["EM1"]["status"].update(
            state="contested", reason="Hardware contradicts this observation."
        )
        self.registry["premises"] = {"Q01": ["EM1"]}
        entries["verify-r8-round2"]["evidence_classes"] = ["emulated"]
        self.assertEqual(self.registry["contradictions"], [])
        result = self.run_sweep()
        affected = {entry["id"]: entry for entry in result["entries"]}
        self.assertEqual(affected["EM1"]["state"], "contested")
        for entry_id in ("qualification-Q01", "verify-r8-round2"):
            self.assertEqual(affected[entry_id]["state"], "stale")
            self.assertNotIn(entry_id, result["eligible"])
            self.assertEqual(affected[entry_id]["stale_since"], "index:EM1")
        self.assertEqual(result["conflicts"], [])
        self.assertIn("candidate-CF2-a2", result["eligible"])

    def registry_clis(self, registry):
        """Run both JSON interfaces against the same temporary registry."""
        with tempfile.TemporaryDirectory() as temp:
            campaign = Path(temp)
            for name, value in (
                ("claims", self.claims),
                ("status", self.status),
                ("sources", registry),
            ):
                (campaign / f"{name}.yaml").write_text(check.yaml.safe_dump(value))
            for script, args in (
                ("sweep.py", [str(campaign)]),
                (
                    "pinned_file_adapter.py",
                    [str(campaign / "sources.yaml"), "candidate"],
                ),
            ):
                yield script, subprocess.run(
                    [sys.executable, str(SCRIPTS / script), *args, "--json"],
                    capture_output=True,
                    text=True,
                    check=False,
                )

    def test_null_ok_hash_rejected_per_kind(self):
        for kind in sorted(source_registry.KINDS):
            registry = copy.deepcopy(self.registry)
            row = source(registry, "candidate")
            row.update(kind=kind, sha256=None, version="new candidate")
            if kind == "spec":
                row["revision"] = 9
            with self.subTest(kind=kind):
                if kind in {"toolchain", "model", "fixture"}:
                    source_registry.validate(registry)
                else:
                    with self.assertRaisesRegex(check.Invalid, "full SHA-256"):
                        source_registry.validate(registry)
                    row["status"] = "unknown"
                    source_registry.validate(registry)

    def test_null_candidate_hash_json_error(self):
        source(self.registry, "candidate").update(sha256=None, version="new candidate")
        for script, proc in self.registry_clis(self.registry):
            with self.subTest(script=script):
                self.assertEqual(proc.returncode, 1)
                payload = json.loads(proc.stdout)
                self.assertFalse(payload["ok"])
                self.assertIn("full SHA-256", payload["findings"][0])
                self.assertEqual(proc.stderr, "")

    def test_malformed_registry_types_json_error(self):
        for field, value in (("kind", []), ("status", {}), ("file.root", [])):
            registry = copy.deepcopy(self.registry)
            row = source(registry, "candidate")
            if field == "file.root":
                row["file"]["root"] = value
            else:
                row[field] = value
            for script, proc in self.registry_clis(registry):
                with self.subTest(field=field, script=script):
                    self.assertEqual(proc.returncode, 1)
                    payload = json.loads(proc.stdout)
                    self.assertFalse(payload["ok"])
                    self.assertIn("nonempty string", payload["findings"][0])
                    self.assertEqual(proc.stderr, "")

    def test_cli_json_skill_and_errors(self):
        def run(*args):
            return subprocess.run(
                [sys.executable, str(SCRIPTS / "sweep.py"), *map(str, args)],
                capture_output=True,
                text=True,
                check=False,
            )

        proc = run(ROOT / "evals/e1000", "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["counts"]["stale"], 96)
        self.assertEqual(run().returncode, 2)
        self.assertTrue(run("--skill").stdout.startswith("---\n"))
        with tempfile.TemporaryDirectory() as temp:
            proc = run(temp, "--json")
            self.assertEqual(proc.returncode, 3)
            self.assertFalse(json.loads(proc.stdout)["ok"])


class AdapterTests(unittest.TestCase):
    """Opaque byte comparison, path boundaries, and explicit registry updates."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "opaque"
        self.file.write_bytes(b"opaque bytes\x00\xff")
        self.registry = inputs()[2]
        self.source = source(self.registry, "candidate")
        self.source["file"] = dict(root="repository", path="opaque")
        self.path = self.root / "sources.yaml"
        self.path.write_text(check.yaml.safe_dump(self.registry))

    def cli(self, *args):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "pinned_file_adapter.py"),
                str(self.path),
                "candidate",
                "--root",
                str(self.root),
                "--json",
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_hash_pin_match_and_provenance(self):
        result = adapter.inspect(self.source, self.root)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["matches_pin"])
        self.assertNotIn("opaque bytes", json.dumps(result))
        self.source["expected_sha256"] = result["sha256"]
        self.assertTrue(adapter.inspect(self.source, self.root)["matches_pin"])
        self.assertEqual(result["provenance"]["adapter"], "pinned-file")

    def test_absent_blocked_and_symlink_escape(self):
        self.source["file"] = None
        self.assertEqual(adapter.inspect(self.source, self.root)["status"], "unknown")
        self.source["file"] = dict(root="repository", path="absent")
        self.assertEqual(adapter.inspect(self.source, self.root)["status"], "blocked")
        (self.root / "escape").symlink_to(ROOT / "README.md")
        self.source["file"]["path"] = "escape"
        self.assertEqual(adapter.inspect(self.source, self.root)["status"], "blocked")

    def test_write_dry_run_and_idempotence(self):
        original = self.path.read_bytes()
        proc = self.cli("--write", "--dry-run")
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(json.loads(proc.stdout)["would_update"])
        self.assertEqual(self.path.read_bytes(), original)
        proc = self.cli("--write")
        self.assertTrue(json.loads(proc.stdout)["updated"])
        updated = self.path.read_bytes()
        self.assertNotEqual(updated, original)
        self.cli("--write")
        self.assertEqual(self.path.read_bytes(), updated)
        row = source(check.read_yaml(self.path), "candidate")
        self.assertEqual(row["expected_sha256"], self.source["expected_sha256"])
        self.assertNotEqual(row["sha256"], row["expected_sha256"])

    def test_run_store_and_missing_dependency(self):
        self.source["file"] = dict(root="run_store", path="opaque")
        self.assertEqual(adapter.inspect(self.source, ROOT, self.root)["status"], "ok")
        self.source["file"]["path"] = "absent"
        self.assertEqual(
            adapter.inspect(self.source, ROOT, self.root)["status"], "blocked"
        )
        with mock.patch.object(check, "yaml", None), mock.patch(
            "builtins.print"
        ) as output:
            self.assertEqual(adapter.main([str(self.path), "candidate", "--json"]), 3)
            self.assertFalse(json.loads(output.call_args.args[0])["ok"])

    def test_duplicate_keys_and_unknown_id(self):
        with self.path.open("a") as out:
            out.write("version: 1\n")
        self.assertEqual(self.cli().returncode, 1)
        self.source["file"]["path"] = "../outside"
        with self.assertRaises(check.Invalid):
            source_registry.validate(self.registry)


if __name__ == "__main__":
    if sys.argv[1:] == ["--matrix"]:
        matrix_rows = matrix()
        print(json.dumps(matrix_rows, indent=2))
        sys.exit(0 if all(r["ok"] for r in matrix_rows) else 1)
    unittest.main()
