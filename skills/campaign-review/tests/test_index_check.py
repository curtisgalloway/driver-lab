# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Schema and evidence-link checks, including mutations that must fail closed."""

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "index_check.py"
ROOT = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location("index_check", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class IndexTests(unittest.TestCase):
    """Each mutation runs against a fresh, valid pair of documents."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(HERE / "fixtures", self.root, dirs_exist_ok=True)
        self.claims = checker.read_yaml(self.root / "claims.yaml")
        self.status = checker.read_yaml(self.root / "status.yaml")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            capture_output=True,
            text=True,
            check=False,
        )

    def save(self):
        for name, data in [("claims.yaml", self.claims), ("status.yaml", self.status)]:
            (self.root / name).write_text(yaml.safe_dump(data))

    def reject(self, message):
        self.save()
        proc = self.run_cli(self.root, "--root", self.root, "--json")
        self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
        result = json.loads(proc.stdout)
        self.assertFalse(result["ok"])
        self.assertIn(message, result["findings"][0])
        self.assertNotIn("Traceback", proc.stderr)

    def test_good_fixture(self):
        proc = self.run_cli(self.root, "--root", self.root, "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual(
            json.loads(proc.stdout)["counts"],
            {"claims": 1, "qualification": 1, "verification": 1},
        )

    def test_bad_fixtures(self):
        cases = [
            (
                "missing basis field",
                ("bases", "frozen", "spec_sha256"),
                None,
                "missing fields",
                True,
            ),
            (
                "truncated hash",
                ("bases", "frozen", "spec_sha256"),
                "abcdef12",
                "full SHA-256",
                False,
            ),
            (
                "unknown kind",
                ("entries", 0, "kind"),
                "unknown",
                "invalid entry kind",
                False,
            ),
            (
                "bad status",
                ("entries", 0, "status", "state"),
                "green",
                "invalid status",
                False,
            ),
            (
                "stale without cause",
                ("entries", 0, "status", "state"),
                "stale",
                "nonempty string",
                False,
            ),
            (
                "unknown basis",
                ("entries", 0, "basis"),
                "missing",
                "unknown basis",
                False,
            ),
            ("unknown claim", ("entries", 0, "claim"), "Q99", "unknown claim", False),
            ("empty rule", ("entries", 0, "rule"), "", "nonempty string", False),
            ("unknown field", ("entries", 0, "surprise"), 1, "unknown fields", False),
            ("empty runs", ("entries", 0, "run_ids"), [], "nonempty list", False),
            (
                "broken link",
                ("entries", 0, "evidence"),
                ["missing.md"],
                "does not resolve",
                False,
            ),
            (
                "directory link",
                ("entries", 0, "evidence"),
                ["."],
                "does not resolve",
                False,
            ),
            (
                "external link",
                ("entries", 0, "evidence"),
                ["https://example.invalid/report"],
                "does not resolve",
                False,
            ),
            (
                "escaped link",
                ("entries", 0, "evidence"),
                ["../outside.md"],
                "escapes repository",
                False,
            ),
            (
                "missing supersedes",
                ("entries", 0, "supersedes"),
                ["missing"],
                "target missing",
                False,
            ),
            (
                "self supersedes",
                ("entries", 0, "supersedes"),
                ["q-Q01"],
                "self supersession",
                False,
            ),
            (
                "invalid verdict",
                ("entries", 0, "verdict"),
                "PASS",
                "invalid qualification verdict",
                False,
            ),
            (
                "negative cost",
                ("entries", 0, "cost"),
                {"seconds": -1},
                "invalid cost",
                False,
            ),
            (
                "nonfinite cost",
                ("entries", 0, "cost"),
                {"usd": float("nan")},
                "invalid cost",
                False,
            ),
            (
                "bad date",
                ("entries", 0, "decision"),
                {"who": "user", "date": "tomorrow", "link": "evidence.md"},
                "ISO date",
                False,
            ),
        ]
        original = copy.deepcopy(self.status)
        for title, path, value, expected, remove in cases:
            with self.subTest(title=title):
                self.status = copy.deepcopy(original)
                node = self.status
                for key in path[:-1]:
                    node = node[key]
                if remove:
                    del node[path[-1]]
                else:
                    node[path[-1]] = value
                self.reject(expected)

    def test_bad_claim_fixtures(self):
        original = copy.deepcopy(self.claims)
        for field, value, expected in [
            ("cites", [], "nonempty list"),
            ("cites", ["SDM 6"], "invalid value"),
            ("checks", ["packet arrive"], "unknown harness check"),
            ("mandatory", "yes", "mandatory flag"),
            ("evidence", ["absent.md"], "does not resolve"),
            ("defects", [], "lacks detected defect"),
        ]:
            with self.subTest(field=field, value=value):
                self.claims = copy.deepcopy(original)
                self.claims["claims"][0][field] = value
                self.reject(expected)

    def test_duplicate_ids_and_missing_qualification(self):
        self.status["entries"].append(copy.deepcopy(self.status["entries"][0]))
        self.reject("duplicate entry ID")
        self.status["entries"] = []
        self.reject("expected one nonsuperseded qualification")

    def test_duplicate_claim(self):
        self.claims["claims"].append(copy.deepcopy(self.claims["claims"][0]))
        self.reject("duplicate claim ID")

    def test_duplicate_yaml_key(self):
        with (self.root / "claims.yaml").open("a") as out:
            out.write("version: 1\n")
        proc = self.run_cli(self.root, "--root", self.root, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("duplicate YAML key", proc.stdout)

    def test_bad_yaml(self):
        (self.root / "claims.yaml").write_text("claims: [")
        proc = self.run_cli(self.root, "--root", self.root, "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(json.loads(proc.stdout)["ok"])

    def test_supersedes_current_then_history(self):
        old = copy.deepcopy(self.status["entries"][0])
        old["id"] = "old"
        self.status["entries"].append(old)
        self.status["entries"][0]["supersedes"] = ["old"]
        self.reject("target must be superseded")
        old["status"]["state"] = "superseded"
        self.assertEqual(
            checker.validate(self.claims, self.status, self.root)["qualification"], 2
        )

    def test_supersedes_cycle(self):
        for name, target in [("old", "older"), ("older", "old")]:
            e = copy.deepcopy(self.status["entries"][0])
            e.update(id=name, supersedes=[target])
            e["status"]["state"] = "superseded"
            self.status["entries"].append(e)
        self.reject("supersedes cycle")

    def test_shortfall_requires_approval_and_reopening(self):
        e = self.status["entries"][0]
        e.update(
            verdict="shortfall",
            shortfall={"reason": "unobservable", "reopen": "New tool."},
        )
        self.reject("requires user decision")
        e["decision"] = {"who": "user", "date": "2026-09-25", "link": "evidence.md"}
        checker.validate(self.claims, self.status, self.root)
        e["shortfall"]["reason"] = "difficult"
        self.reject("invalid shortfall reason")
        e["shortfall"] = {"reason": "unobservable", "reopen": ""}
        self.reject("nonempty string")

    def test_items(self):
        item = copy.deepcopy(self.status["entries"][0])
        for key in ["claim", "validated_harness_sha256"]:
            del item[key]
        item.update(
            id="item",
            kind="item",
            verdict="Clarify wording.",
            rule="C6-item-classification-2026-09-26",
            target="records",
            source=3,
            disposition={"state": "queued", "destination": "Next records pass."},
        )
        item["class"] = "W"
        self.status["entries"].append(item)
        checker.validate(self.claims, self.status, self.root)
        original = copy.deepcopy(item)
        for field, value, expected in [
            ("class", "", "nonempty string"),
            ("source", True, "invalid item source"),
            ("target", "driver", "invalid item target"),
            ("disposition", {"state": "applied"}, "needs revision"),
            ("disposition", {"state": "queued"}, "nonempty string"),
            ("disposition", {"state": "rejected"}, "nonempty string"),
            (
                "disposition",
                {"state": "shortfall", "reason": "blocked"},
                "nonempty string",
            ),
            ("aliases", ["q-Q01"], "duplicate entry ID or alias"),
        ]:
            with self.subTest(field=field):
                self.status["entries"][-1] = copy.deepcopy(original)
                self.status["entries"][-1][field] = value
                self.reject(expected)

    def test_result_cannot_claim_shortfall_as_qualified(self):
        e = self.status["entries"][0]
        e.update(verdict="unqualified")
        result = copy.deepcopy(e)
        del result["validated_harness_sha256"]
        result.update(
            id="result",
            kind="result",
            verdict="PASS",
            round="a2",
            qualification=e["id"],
            qualified_evidence=True,
        )
        self.status["entries"].append(result)
        self.reject("unqualified result labeled qualified")
        result["qualified_evidence"] = False
        checker.validate(self.claims, self.status, self.root)

    def add_item(self, disposition):
        item = copy.deepcopy(self.status["entries"][0])
        for key in ["claim", "validated_harness_sha256"]:
            del item[key]
        item.update(
            id="item",
            kind="item",
            verdict="Clarify wording.",
            rule="C6-item-classification-2026-09-26",
            target="records",
            source=3,
            disposition=disposition,
        )
        item["class"] = "W"
        self.status["entries"].append(item)
        return item

    def test_disposition_fields_match_state(self):
        item = self.add_item({"state": "queued", "destination": "Next brief."})
        states = [
            {"state": "queued", "destination": "Next brief."},
            {"state": "applied", "revision": 1},
            {"state": "shortfall", "reason": "blocked", "reopen": "New tool."},
            {"state": "rejected", "reason": "Already addressed."},
        ]
        extras = {
            "revision": False,
            "reason": ["bad"],
            "reopen": ["bad"],
            "destination": {"nonsense": True},
        }
        for disposition in states:
            item["disposition"] = disposition
            checker.validate(self.claims, self.status, self.root)
            for field, value in extras.items():
                if field in disposition or (
                    disposition["state"] == "shortfall" and field == "destination"
                ):
                    continue
                with self.subTest(state=disposition["state"], field=field):
                    item["disposition"] = {**disposition, field: value}
                    self.reject("unknown fields")
        item["disposition"] = {
            "state": "queued",
            "destination": "Next brief.",
            "revision": False,
            "reopen": ["bad"],
        }
        self.reject("unknown fields")

    def test_optional_shortfall_destination(self):
        disposition = {
            "state": "shortfall",
            "reason": "out of scope",
            "reopen": "Hardware fixture available.",
        }
        self.add_item(disposition)
        checker.validate(self.claims, self.status, self.root)
        disposition["destination"] = "HF-1"
        checker.validate(self.claims, self.status, self.root)
        for value in [{"nonsense": True}, ["bad"], False, None, ""]:
            with self.subTest(value=value):
                disposition["destination"] = value
                self.reject("nonempty string")

    def test_static_and_formatted_renames(self):
        self.claims["claims"][0]["checks"] = ["interface up (load 2)"]
        checker.validate(self.claims, self.status, self.root)
        p = self.root / "harness.py"
        p.write_text(p.read_text().replace("interface up", "interface ready"))
        self.reject("unknown harness check")

    def test_formatted_name_is_exact(self):
        self.claims["claims"][0]["checks"] = ["interface up (load 999)"]
        self.reject("unknown harness check")

    def test_real_http_conversion_and_format_renames(self):
        harness = (ROOT / "evals/e1000/harness/l02harness.py").read_text()
        original = "{what} over HTTP{via} {label} arrives intact"
        self.assertIn(original, harness)
        self.claims["claims"][0]["checks"] = [
            "4 MiB over HTTP peer to DUT arrives intact"
        ]
        path = self.root / "harness.py"
        path.write_text(harness)
        checker.validate(self.claims, self.status, self.root)
        for suffix in ["!r", "!s", "!a", ":>20", ":"]:
            with self.subTest(suffix=suffix):
                changed = original.replace("{label}", "{label" + suffix + "}")
                path.write_text(harness.replace(original, changed))
                self.reject("unknown harness check")

    def test_documentation_is_not_a_check(self):
        with (self.root / "harness.py").open("a") as out:
            out.write('\n"phantom check"\n')
        self.claims["claims"][0]["checks"] = ["phantom check"]
        self.reject("unknown harness check")

    def test_harness_is_not_executed(self):
        with (self.root / "harness.py").open("a") as out:
            out.write('\nraise RuntimeError("must never execute")\n')
        checker.validate(self.claims, self.status, self.root)

    def test_symlink_escape(self):
        (self.root / "outside").symlink_to(SCRIPT)
        self.status["entries"][0]["evidence"] = ["outside"]
        self.reject("escapes repository")

    def test_missing_precondition_usage_and_skill(self):
        (self.root / "status.yaml").unlink()
        proc = self.run_cli(self.root, "--root", self.root, "--json")
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(json.loads(proc.stdout)["ok"])
        self.assertEqual(self.run_cli().returncode, 2)
        proc = self.run_cli("--skill")
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.startswith("---\n"))

    def test_unknown_applied_class_is_a_requirement_in_history(self):
        claims = checker.read_yaml(ROOT / "evals/e1000/claims.yaml")
        status = checker.read_yaml(ROOT / "evals/e1000/status.yaml")
        item = next(e for e in status["entries"] if e["id"] == "CF-1-TNCRS")
        item["class"] = "unknown"
        checker.validate(claims, status, ROOT)
        status["revisions"]["8"]["requirement_change"] = False
        with self.assertRaisesRegex(checker.Invalid, "matching R item chain"):
            checker.validate(claims, status, ROOT)

    def test_real_campaign(self):
        claims = checker.read_yaml(ROOT / "evals/e1000/claims.yaml")
        status = checker.read_yaml(ROOT / "evals/e1000/status.yaml")
        counts = checker.validate(claims, status, ROOT)
        self.assertEqual(
            counts,
            {
                "claims": 28,
                "qualification": 28,
                "result": 28,
                "observation": 8,
                "item": 31,
                "verification": 95,
                "candidate_round": 3,
            },
        )
        self.assertEqual(
            {c["id"] for c in claims["claims"]}, {f"Q{i:02}" for i in range(1, 29)}
        )
        entries = {e["id"]: e for e in status["entries"]}
        self.assertEqual(entries["qualification-Q18"]["verdict"], "shortfall")
        self.assertFalse(entries["result-Q18"]["qualified_evidence"])
        self.assertEqual(entries["SR-8-4"]["target"], "records")
        self.assertEqual(entries["A-RR-1"]["class"], "W")
        self.assertEqual(entries["SR-8-2"]["aliases"], ["A-RR-5"])
        self.assertIn(
            "Next implementer brief", entries["A-RR-7"]["disposition"]["destination"]
        )
        rlec = entries["CF-2-RLEC-comment"]
        self.assertEqual((rlec["class"], rlec["target"]), ("W", "candidate"))
        self.assertEqual(rlec["disposition"], entries["A-RR-7"]["disposition"])
        basis = status["bases"][entries["CF-2-AR-10"]["basis"]]
        self.assertEqual(
            basis["candidate_module_sha256"],
            "df37c7ad143d7a04bf6655ce4e6f8770788677049e6973e6e1a4d294c88eee65",
        )
        self.assertEqual(
            basis["harness_sha256"],
            "884e771c655d627a4b4af11d0526e1445579dad674146b5db8c8121b99e8c03d",
        )
        self.assertEqual(
            basis["emulator"]["sha256"],
            "0cd4112a8f0cb891eb7c10e8df38c9dfeec8c7389bb22db6aa425f0d6fe733dc",
        )
        self.assertIn(
            "evidence/L02f2b.md#requalification",
            entries["qualification-Q15"]["evidence"],
        )
        q15 = next(c for c in claims["claims"] if c["id"] == "Q15")
        self.assertIn(
            "evidence/L02f2b.md#requalification", q15["defects"][0]["evidence"]
        )
        self.assertEqual(
            {e["id"] for e in status["entries"] if e["kind"] == "observation"},
            {f"EM{i}" for i in range(1, 9)},
        )
        self.assertEqual(status["revision_range"], [3, 8])
        self.assertEqual(set(status["revisions"]), {str(r) for r in range(3, 9)})
        readings = [e for e in entries.values() if e["kind"] == "verification"]
        self.assertEqual(len({e["reading_id"] for e in readings}), 22)
        self.assertEqual(
            {e["reading_id"] for e in readings if e["status"]["state"] == "current"},
            {"verify-r8-round2"},
        )
        self.assertEqual(entries["verify-r8-round2"]["independence"], "sequential")
        self.assertEqual(
            entries["CF-1-TNCRS"]["disposition"], {"state": "applied", "revision": 8}
        )
        self.assertIn("CF-1-TNCRS", status["revisions"]["8"]["items"])
        self.assertEqual(
            entries["candidate-CF2-a1"]["supersedes"], ["candidate-CF1-a1"]
        )
        self.assertEqual(
            entries["candidate-CF2-a2"]["supersedes"], ["candidate-CF2-a1"]
        )
        self.assertEqual(
            set(entries["candidate-CF2-a2"]["results"]),
            {f"result-Q{i:02}" for i in range(1, 29)},
        )

    def test_history_mutations(self):
        original = copy.deepcopy(self.status)
        cases = [
            (("revisions",), {}, "missing or unexpected revision"),
            (("revision_range",), [True, 8], "invalid revision range"),
            (("revision_range",), [7, 8], "missing or unexpected revision"),
            (("revisions", "8", "spec_sha256"), "b" * 64, "spec_sha256 does not match"),
            (("entries", 1, "text"), "unknown", "spec_sha256 does not match"),
            (("entries", 1, "covers_revisions"), [7, 8], "covered revision"),
            (("entries", 1, "evidence_classes"), ["unknown"], "evidence class"),
            (("entries", 1, "evidence_classes"), [], "nonempty list"),
            (("entries", 1, "sections"), ["2"], "outside reading basis"),
            (("entries", 1, "independence"), "gate", "gate cannot count as accuracy"),
            (("bases", "reading", "model"), None, "requires reader model"),
            (("revisions", "8", "requirement_change"), True, "matching R item chain"),
            (("revisions", "8", "items"), ["missing"], "applied to this spec revision"),
        ]
        for path, value, expected in cases:
            with self.subTest(path=path, value=value):
                self.status = copy.deepcopy(original)
                node = self.status
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = value
                self.reject(expected)
        self.status = copy.deepcopy(original)
        self.status["entries"].pop()
        self.reject("missing verification")

    def test_draft_hash_and_state(self):
        reading = self.status["entries"][1]
        self.status["revisions"]["8"]["drafts"] = {"round1": "b" * 64}
        reading["text"] = "round1"
        self.reject("spec_sha256 does not match")
        self.status["bases"]["reading"]["spec_sha256"] = "b" * 64
        self.reject("draft reading must remain superseded")
        reading["status"]["state"] = "superseded"
        checker.validate(self.claims, self.status, self.root)

    def test_verification_rejects_undefined_optional_fields(self):
        reading = self.status["entries"][1]
        for key, value in [
            ("aliases", ["unexpected-alias"]),
            ("shortfall", {"reason": "blocked", "reopen": "New evidence."}),
        ]:
            with self.subTest(field=key):
                reading[key] = value
                self.reject("unknown fields")
                del reading[key]

    def test_real_applied_spec_item_requires_destination(self):
        claims = checker.read_yaml(ROOT / "evals/e1000/claims.yaml")
        original = checker.read_yaml(ROOT / "evals/e1000/status.yaml")
        for new_item in (False, True):
            with self.subTest(new_item=new_item):
                status = copy.deepcopy(original)
                if new_item:
                    item = copy.deepcopy(
                        next(e for e in status["entries"] if e["id"] == "CF-1-TNCRS")
                    )
                    item.update(id="new-applied-R")
                    del item["aliases"]
                    status["entries"].append(item)
                else:
                    item = next(e for e in status["entries"] if e["id"] == "SR-8-1")
                item["disposition"] = {"state": "applied", "revision": 999}
                with self.assertRaisesRegex(checker.Invalid, "destination is missing"):
                    checker.validate(claims, status, ROOT)
                item["disposition"]["revision"] = 8
                with self.assertRaisesRegex(
                    checker.Invalid, "missing from destination header"
                ):
                    checker.validate(claims, status, ROOT)

    def test_real_public_provenance(self):
        status = checker.read_yaml(ROOT / "evals/e1000/status.yaml")
        entries = {e["id"]: e for e in status["entries"]}
        link = "evidence/CR2-provenance.md"
        rows = {}
        for line in (ROOT / link).read_text().splitlines():
            if line.startswith("| `verify-"):
                rows[line.split("|")[1].strip().strip("`")] = line
        cited = {
            e["id"]
            for e in entries.values()
            if e["kind"] == "verification" and link in e["evidence"]
        }
        self.assertEqual(len(rows), 43)
        self.assertEqual(set(rows), cited)
        for entry_id, row in rows.items():
            entry = entries[entry_id]
            basis = status["bases"][entry["basis"]]
            self.assertIn(basis["spec_sha256"], row)
            self.assertIn(basis["model"]["name"], row)
            self.assertIn(basis["model"]["version"], row)
            self.assertIn(", ".join(entry["sections"]), row)
            self.assertIn(", ".join(entry["evidence_classes"]), row)
            self.assertIn(entry["run_ids"][0], row)
            self.assertIsNone(basis["dependencies"])
            self.assertIn("dependencies: null", row)
        self.assertEqual(
            entries["verify-r3-adjudication"]["evidence_classes"], ["databook"]
        )
        self.assertEqual(
            status["bases"]["cf1-a1"]["model"], status["bases"]["cf2-a2"]["model"]
        )

    def test_reading_slice_coverage(self):
        self.status["bases"]["reading"]["sections_read"] = ["1", "2"]
        self.reject("missing reading section slice")
        reading = copy.deepcopy(self.status["entries"][1])
        reading.update(id="slice2", sections=["2"])
        self.status["entries"].append(reading)
        checker.validate(self.claims, self.status, self.root)
        reading["sections"] = ["1"]
        self.reject("overlapping reading slices")
        reading["sections"] = ["2"]
        reading["verdict"] = "FAIL"
        self.reject("inconsistent reading slices")

    def test_requirement_and_candidate_chain(self):
        item = self.add_item({"state": "applied", "revision": 8})
        item.update(target="spec")
        item["class"] = "R"
        revision = self.status["revisions"]["8"]
        revision.update(requirement_change=True, items=["item"])
        candidate = copy.deepcopy(self.status["entries"][0])
        del candidate["claim"]
        del candidate["validated_harness_sha256"]
        candidate.update(
            id="candidate",
            kind="candidate_round",
            round="a1",
            applied_items=["item"],
            verification=["verification"],
            results=[],
            scope="Synthetic acceptance round.",
        )
        self.status["entries"].append(candidate)
        checker.validate(self.claims, self.status, self.root)
        original = copy.deepcopy(candidate)
        for field, value, expected in [
            ("applied_items", ["missing"], "matching applied R item"),
            ("verification", ["q-Q01"], "landed verification link"),
            ("results", ["q-Q01"], "result basis or round mismatch"),
        ]:
            with self.subTest(field=field):
                candidate[field] = value
                self.reject(expected)
                candidate[field] = original[field]
        item["disposition"]["revision"] = 7
        self.reject("applied to this spec revision")

    def test_old_unscoped_reading_cannot_remain_current(self):
        self.status["revision_range"] = [8, 9]
        self.status["revisions"]["9"] = copy.deepcopy(self.status["revisions"]["8"])
        reading = copy.deepcopy(self.status["entries"][1])
        reading.update(id="new", reading_id="new", basis="new", covers_revisions=[9])
        self.status["bases"]["new"] = copy.deepcopy(self.status["bases"]["reading"])
        self.status["bases"]["new"]["spec_revision"] = 9
        self.status["entries"].append(reading)
        self.reject("must widen, not stay current")


if __name__ == "__main__":
    unittest.main()
