# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Stopping-rule, queue, policy and authorization regressions over real metadata."""

import copy
import unittest

from test_sweep import BASELINE, BASELINE_DEPLOYMENT, check, deployment, inputs, source, sweep
import stopping

ROLES = deployment.load(BASELINE_DEPLOYMENT)


def entry(status, eid):
    """Select one fixture record."""
    return next(e for e in status["entries"] if e["id"] == eid)


def complete_readings(status):
    """Synthetic full readings: explicit coverage, independence and adjudication."""
    template = entry(status, "verify-r8-round2")
    sections = sorted({s for b in status["bases"].values() for s in b["sections_read"]})
    for number in (1, 2):
        reading = copy.deepcopy(template)
        rid = f"synthetic-full-{number}"
        basis = copy.deepcopy(status["bases"][template["basis"]])
        basis["sections_read"] = sections
        basis["dependencies"] = []
        status["bases"][rid] = basis
        reading.update(
            id=rid,
            reading_id=rid,
            basis=rid,
            sections=sections,
            covers_revisions=list(range(3, 9)),
            supersedes=[],
            independence="independent",
            sequence=22 + number,
            round=f"full-{number}",
        )
        status["entries"].append(reading)


class StoppingTests(unittest.TestCase):
    """Negative cases must block acceptance or batching, not merely print a warning."""

    def setUp(self):
        self.claims, self.status, self.registry = inputs()
        # Synthetic no-impact declarations isolate each test's own trigger.
        # The real-report test reloads the unchanged public status index.
        for eid in ("AF-1-reading-coverage", "SR-8-independent-reading"):
            self.item(eid)["impact"] = dict(claims=[], changes_status=False)

    def report(self):
        return sweep.sweep(self.claims, self.status, self.registry, roles=ROLES)[
            "stopping"
        ]

    def item(self, eid="SR-8-1"):
        return entry(self.status, eid)

    def test_real_blockers_and_first_batch(self):
        self.status = check.read_yaml(BASELINE)
        report = self.report()
        self.assertFalse(report["sufficient"])
        self.assertEqual(
            [s for s, v in report["conditions"].items() if not v["met"]],
            ["S2", "S3", "S4"],
        )
        self.assertEqual(len(report["conditions"]["S2"]["blockers"]), 13)
        self.assertEqual(
            report["batch"],
            [
                "e1000:second-reading:current",
                "e1000:re-verification:AF-1-reading-coverage",
                "e1000:re-verification:SR-8-independent-reading",
            ],
        )
        self.assertEqual(len(report["waiting"]), 14)
        self.assertEqual(
            report["conditions"]["S3"]["blockers"],
            [
                "AF-1-reading-coverage: impact unrecorded",
                "SR-8-independent-reading: impact unrecorded",
            ],
        )
        self.assertEqual(len(report["open_items"]), 14)
        self.assertTrue(all(r["state"] == "historical" for r in report["round_cap"]))

    def test_sufficient_then_new_reader_even_when_sufficient(self):
        complete_readings(self.status)
        original = self.report()
        self.assertTrue(original["sufficient"], original["conditions"])
        self.assertEqual(original["batch"], [])
        for campaign in ("e1000", "second-campaign"):
            self.claims["campaign"] = self.status["campaign"] = self.registry[
                "campaign"
            ] = campaign
            result = sweep.sweep(
                self.claims,
                self.status,
                self.registry,
                reader=dict(name="new reader", version="2"),
                roles=ROLES,
            )["stopping"]
            self.assertTrue(result["sufficient"])
            units = [u for u in result["queue"] if u["kind"] == "comparison-reading"]
            self.assertEqual(len(units), 1)
            self.assertEqual(units[0]["id"], campaign + ":comparison-reading:current")
            self.assertEqual(units[0]["model"]["version"], "2")

    def test_sequential_reads_are_one_lineage(self):
        complete_readings(self.status)
        for rid in ("synthetic-full-1", "synthetic-full-2"):
            entry(self.status, rid)["independence"] = "sequential"
        self.assertFalse(self.report()["conditions"]["S4"]["met"])

    def test_gate_adjudication_draft_and_partial_reads_cannot_fill_s4(self):
        for mutation in ("adjudication", "gate", "partial", "draft"):
            with self.subTest(mutation=mutation):
                self.setUp()
                complete_readings(self.status)
                for rid in ("synthetic-full-1", "synthetic-full-2"):
                    value = entry(self.status, rid)
                    if mutation == "gate":
                        value.update(independence="gate", purpose="acceptance")
                    elif mutation == "partial":
                        value["sections"] = ["5.5"]
                        self.status["bases"][rid]["sections_read"] = ["5.5"]
                    elif mutation == "draft":
                        value["text"] = "verify-r8-round1"
                        self.status["bases"][rid]["spec_sha256"] = self.status[
                            "revisions"
                        ]["8"]["drafts"]["verify-r8-round1"]
                        value["status"].update(state="superseded", stale_since=None)
                    else:
                        value["independence"] = mutation
                self.assertFalse(self.report()["conditions"]["S4"]["met"])

    def test_no_scope_no_batch(self):
        del self.status["scope"]
        report = self.report()
        self.assertFalse(report["conditions"]["S1"]["met"])
        self.assertEqual(report["batch"], [])

    def test_unaccepted_evidence_blocks_s2(self):
        self.status["scope"]["accepted_classes"]["Q01"] = ["databook"]
        self.assertIn("Q01", self.report()["conditions"]["S2"]["blockers"][0])

    def test_shortfall_needs_user_and_reopening_reason(self):
        for change in ("operator", "missing-reopen", "bad-reason"):
            with self.subTest(change=change):
                self.setUp()
                value = self.item("qualification-Q18")
                if change == "operator":
                    value["decision"]["who"] = "operator"
                elif change == "missing-reopen":
                    value["shortfall"]["reopen"] = ""
                else:
                    value["shortfall"]["reason"] = "too hard"
                with self.assertRaises(check.Invalid):
                    self.report()

    def test_w_and_records_do_not_start_revisions(self):
        report = self.report()
        wording_items = {"SR-8-1", "SR-8-2", "SR-8-3", "A-RR-1"}
        self.assertTrue(report["conditions"]["S3"]["met"])
        self.assertTrue(
            all(not wording_items.intersection(u["entries"]) for u in report["queue"])
        )
        self.item("SR-8-4")["class"] = "R"
        report = self.report()
        self.assertTrue(report["conditions"]["S3"]["met"])
        self.assertFalse(any("SR-8-4" in u["entries"] for u in report["queue"]))

    def test_unknown_class_is_r_and_requires_decision(self):
        self.item()["class"] = "uncertain"
        report = self.report()
        self.assertFalse(report["conditions"]["S3"]["met"])
        row = next(i for i in report["open_items"] if i["id"] == "SR-8-1")
        self.assertEqual(row["effective_class"], "R")
        unit = next(u for u in report["queue"] if u["kind"] == "requirement-change")
        self.assertEqual(unit["tier"], 2)
        self.assertEqual(unit["state"], "awaiting decision")
        self.assertNotIn(unit["id"], report["batch"])

    def test_review_e_without_impact_is_unresolved(self):
        for eid in ("AF-1-reading-coverage", "SR-8-independent-reading"):
            with self.subTest(item=eid):
                self.setUp()
                del self.item(eid)["impact"]
                report = self.report()
                self.assertFalse(report["conditions"]["S3"]["met"])
                self.assertIn(
                    f"{eid}: impact unrecorded", report["conditions"]["S3"]["blockers"]
                )
                row = next(i for i in report["open_items"] if i["id"] == eid)
                self.assertIn("impact unrecorded", row["action"])
                self.assertNotIn("no change", row["action"])
                self.assertTrue(any(eid in u["entries"] for u in report["queue"]))

    def test_version_two_preserves_freshness_independently_of_ok(self):
        complete_readings(self.status)
        result = sweep.sweep(self.claims, self.status, self.registry, roles=ROLES)
        self.assertEqual(result["version"], 2)
        self.assertTrue(result["ok"])
        self.assertTrue(result["entries"])
        self.assertFalse(result["fresh"])
        self.assertEqual(
            result["fresh"],
            not result["entries"]
            and not result["stale_controls"]
            and not result["unavailable"],
        )
        self.assertIn("version 2", sweep.SKILL)
        self.assertIn("fresh", sweep.SKILL)
        for value in self.status["entries"]:
            if value["status"]["state"] == "stale":
                value["status"].update(state="superseded", stale_since=None)
        result = sweep.sweep(self.claims, self.status, self.registry, roles=ROLES)
        self.assertFalse(result["entries"])
        self.assertTrue(result["fresh"])
        source(self.registry, "candidate")["status"] = "unknown"
        result = sweep.sweep(self.claims, self.status, self.registry, roles=ROLES)
        self.assertFalse(result["fresh"])
        self.assertFalse(result["ok"])

    def test_e_only_reopens_when_claim_status_changes_in_scope(self):
        value = self.item()
        value["class"] = "E"
        for claims, changed, expected in [
            ([], True, False),
            (["Q01"], False, False),
            (["Q01"], True, True),
        ]:
            value["impact"] = dict(claims=claims, changes_status=changed)
            report = self.report()
            self.assertEqual(
                any(u["kind"] == "evidence-revision" for u in report["queue"]), expected
            )
            self.assertEqual(report["conditions"]["S3"]["met"], not expected)
        del value["impact"]
        self.assertFalse(self.report()["conditions"]["S3"]["met"])

    def test_all_tier_two_actions_require_their_own_user_decision(self):
        complete_readings(self.status)
        value = self.item("A-RR-4")
        for action in (
            "requirement-change",
            "implementation",
            "hardware-run",
            "recall",
            "adopt-source",
            "accept-shortfall",
            "outward-report",
        ):
            for who in (None, "operator", "user"):
                with self.subTest(action=action, who=who):
                    value["action"] = action
                    value.pop("decision", None)
                    if who:
                        value["decision"] = dict(
                            who=who, date="2026-09-27", link="evidence/CR4.md"
                        )
                    report = self.report()
                    unit = next(u for u in report["queue"] if "A-RR-4" in u["entries"])
                    self.assertEqual(unit["tier"], 2)
                    self.assertEqual(unit["id"] in report["batch"], who == "user")
                    self.assertNotIn(
                        "e1000:outward-report:QF-1-F1-upstream", report["batch"]
                    )

    def test_fourth_unit_waits_and_forged_ready_tier_two_is_excluded(self):
        queue = [dict(id=str(i), tier=1, state="ready") for i in range(4)]
        queue.insert(0, dict(id="unauthorized", tier=2, state="ready"))
        self.assertEqual(stopping.select_batch(queue), (["0", "1", "2"], ["3"]))

    def test_rule_changes_flagged_and_excluded_not_compared(self):
        complete_readings(self.status)
        self.item("qualification-Q01")["rule"] = "different-A6"
        for rid in ("synthetic-full-1", "synthetic-full-2"):
            self.item(rid)["rule"] = "different-A1"
        report = self.report()
        self.assertFalse(report["sufficient"])
        self.assertFalse(report["conditions"]["S2"]["met"])
        self.assertFalse(report["conditions"]["S4"]["met"])
        self.assertEqual(len(report["policy_changes"]), 3)
        self.assertTrue(all(not r["compared"] for r in report["policy_changes"]))

    def test_latest_reading_r_item_blocks_s5_even_after_disposition(self):
        complete_readings(self.status)
        self.item("synthetic-full-2")["assessment"]["r_items"] = ["CF-1-TNCRS"]
        self.assertFalse(self.report()["conditions"]["S5"]["met"])
        self.item("synthetic-full-2")["assessment"]["r_items"] = []
        self.assertTrue(self.report()["conditions"]["S5"]["met"])

    def test_unclassified_and_accuracy_failures_block_s3(self):
        complete_readings(self.status)
        self.item("synthetic-full-2")["assessment"]["accuracy_failures"] = 1
        self.assertFalse(self.report()["conditions"]["S3"]["met"])
        del self.item("synthetic-full-2")["assessment"]
        self.assertFalse(self.report()["conditions"]["S3"]["met"])

    def test_post_cap_and_unknown_date_overrun_blocks_reading_batch(self):
        for started in ("2026-09-27", None):
            self.status["revisions"]["7"].pop("started", None)
            if started:
                self.status["revisions"]["7"]["started"] = started
            report = self.report()
            row = next(r for r in report["round_cap"] if r["revision"] == 7)
            self.assertEqual(row["state"], "awaiting decision")
            self.assertNotIn("e1000:second-reading:current", report["batch"])
            self.assertFalse(report["sufficient"])

    def test_unavailable_identity_cannot_be_sufficient(self):
        complete_readings(self.status)
        source(self.registry, "candidate")["status"] = "unknown"
        self.assertFalse(self.report()["sufficient"])

    def test_third_round_sends_remaining_readings_to_user(self):
        complete_readings(self.status)
        self.status["entries"] = [
            e for e in self.status["entries"] if e["id"] != "synthetic-full-2"
        ]
        self.status["revisions"]["8"]["started"] = "2026-09-27"
        report = self.report()
        self.assertEqual(report["round_cap"][-1]["state"], "limit reached")
        self.assertNotIn("e1000:second-reading:current", report["batch"])

    def test_mandatory_item_shortfall_needs_its_own_user_decision(self):
        value = self.item()
        value["class"] = "E"
        value["disposition"] = dict(
            state="shortfall", reason="unobservable", reopen="new instrument"
        )
        with self.assertRaisesRegex(check.Invalid, "explicit claim impact"):
            self.report()
        value["impact"] = dict(claims=["Q01"], changes_status=True)
        with self.assertRaisesRegex(check.Invalid, "user decision"):
            self.report()
        value["decision"] = dict(who="user", date="2026-09-27", link="evidence/CR4.md")
        self.report()

    def test_sequences_and_impact_types_fail_closed(self):
        self.item("verify-r8-round2")["sequence"] = 1
        with self.assertRaisesRegex(check.Invalid, "duplicate reading sequence"):
            self.report()
        self.setUp()
        for value in (
            dict(claims=["Q99"], changes_status=True),
            dict(claims=["Q01"], changes_status="yes"),
        ):
            self.item()["impact"] = value
            with self.assertRaises(check.Invalid):
                self.report()

    def test_review_evidence_impact_reopens_and_unknown_review_is_r(self):
        value = self.item("AF-1-reading-coverage")
        value["impact"] = dict(claims=["Q01"], changes_status=True)
        report = self.report()
        self.assertFalse(report["conditions"]["S3"]["met"])
        self.assertTrue(any(value["id"] in u["entries"] for u in report["queue"]))
        value["class"] = "unknown"
        report = self.report()
        self.assertFalse(report["conditions"]["S3"]["met"])
        unit = next(u for u in report["queue"] if value["id"] in u["entries"])
        self.assertEqual(unit["tier"], 2)

    def test_tier_two_action_cannot_hide_spec_evidence_impact(self):
        value = self.item()
        value["class"] = "E"
        value["impact"] = dict(claims=["Q01"], changes_status=True)
        value["action"] = "adopt-source"
        report = self.report()
        self.assertFalse(report["conditions"]["S3"]["met"])
        unit = next(u for u in report["queue"] if value["id"] in u["entries"])
        self.assertEqual(unit["tier"], 2)
        self.assertNotIn(unit["id"], report["batch"])


if __name__ == "__main__":
    unittest.main()
