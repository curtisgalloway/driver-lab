# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""C6 stopping rule and C3/C4 queue, evaluated only from validated metadata."""

from collections import defaultdict

# Nested quotes in f-strings preserve compatibility with Python before 3.12.
# pylint: disable=inconsistent-quotes

READER = {"name": "Claude Fable", "version": "5.1"}
BATCH_CAP = 3
ROUND_CAP = 3
CAP_DATE = "2026-09-26"
POLICY = "A1-amended-2026-09-26"


def effective_class(entry):
    """Unknown classifications are requirements until a person resolves them."""
    return entry["class"] if entry["class"] in {"R", "E", "W"} else "R"


def covers(sections, required):
    """A reading of a parent covers a child; the reverse does not hold."""
    return all(any(r == s or r.startswith(s + ".") for s in sections) for r in required)


def reading_groups(status):
    """Deduplicate slices without conflating sequential and independent readers."""
    groups = defaultdict(list)
    for entry in status["entries"]:
        if entry["kind"] == "verification" and entry["purpose"] == "accuracy":
            groups[entry["reading_id"]].append(entry)
    return groups


def round_report(status, groups):
    """Unknown start dates do not exempt a revision from the new round cap."""
    rows = []
    for revision, header in status["revisions"].items():
        readings = [
            group[0]
            for group in groups.values()
            if status["bases"][group[0]["basis"]]["spec_revision"] == int(revision)
        ]
        count = max(
            [len(readings)]
            + [int(e["round"]) for e in readings if e["round"].isdigit()]
        )
        historical = bool(header.get("started") and header["started"] <= CAP_DATE)
        if count > ROUND_CAP or (count == ROUND_CAP and not historical):
            rows.append(
                dict(
                    revision=int(revision),
                    rounds=count,
                    state="historical"
                    if historical
                    else "awaiting decision"
                    if count > ROUND_CAP
                    else "limit reached",
                    reason="pre-cap history"
                    if historical
                    else "round cap reached; send remaining findings to the user",
                )
            )
    return rows


def select_batch(queue):
    """Bound the batch and independently enforce the tier-2 decision guard."""
    ready = [
        u["id"]
        for u in queue
        if u["state"] == "ready"
        and (
            u["tier"] == 1
            or (u["tier"] == 2 and u.get("decision", {}).get("who") == "user")
        )
    ]
    return ready[:BATCH_CAP], ready[BATCH_CAP:]


def evaluate(claims_doc, status, freshness, reader=None):
    """Return stopping conditions, explicit limits and a queue; execute nothing."""
    reader = dict(READER if reader is None else reader)
    entries = {e["id"]: e for e in status["entries"]}
    claims = {c["id"]: c for c in claims_doc["claims"]}
    scope = status.get("scope")
    scoped = set(scope["claims"]) if scope else set(claims)
    states = {e["id"]: e["status"]["state"] for e in entries.values()}
    states.update({e["id"]: e["state"] for e in freshness["entries"]})
    conditions = {f"S{i}": dict(met=True, blockers=[]) for i in range(1, 6)}

    def block(condition, detail):
        conditions[condition]["met"] = False
        conditions[condition]["blockers"].append(detail)

    if not scope:
        block("S1", "scope declaration missing")
    policies = scope["rules"] if scope else {}
    policy_changes = []
    policy_blockers = []
    eligible = set(freshness["eligible"])
    for entry in entries.values():
        expected = policies.get(entry["kind"])
        if expected and expected != entry["rule"]:
            policy_changes.append(
                dict(
                    id=entry["id"],
                    recorded=entry["rule"],
                    expected=expected,
                    compared=False,
                )
            )
            eligible.discard(entry["id"])
            if states[entry["id"]] == "current" and (
                "claim" not in entry or entry["claim"] in scoped
            ):
                policy_blockers.append(entry["id"])

    shortfalls = []
    for cid in sorted(scoped):
        claim = claims[cid]
        qualifications = [
            e
            for e in entries.values()
            if e["kind"] == "qualification"
            and e["claim"] == cid
            and states[e["id"]] != "superseded"
        ]
        qualification = qualifications[0]
        qid = qualification["id"]
        if qualification["verdict"] == "shortfall":
            shortfalls.append(
                dict(
                    id=qid,
                    **qualification["shortfall"],
                    decision=qualification.get("decision"),
                    current=qid in eligible,
                )
            )
        if not claim["mandatory"]:
            continue
        if qid not in eligible:
            block(
                "S2",
                f"{cid}: qualification/shortfall is not current under the scope rule",
            )
            continue
        if qualification["verdict"] == "shortfall":
            if qualification.get("decision", {}).get("who") != "user":
                block("S2", f"{cid}: mandatory shortfall requires user approval")
            continue
        results = [
            e
            for e in entries.values()
            if e["kind"] == "result" and e["claim"] == cid and e["id"] in eligible
        ]
        accepted = scope and "emulated" in scope["accepted_classes"][cid]
        if (
            qualification["verdict"] != "qualified"
            or not any(
                e["verdict"] == "PASS"
                and e["qualified_evidence"]
                and e["qualification"] == qid
                for e in results
            )
            or not accepted
        ):
            block("S2", f"{cid}: no qualified PASS in an accepted evidence class")

    queue = []

    def unit(kind, ids, reason, tier=1, decision=None, suffix=None):
        value = dict(
            id=f"{status['campaign']}:{kind}:{suffix or 'current'}",
            kind=kind,
            tier=tier,
            entries=sorted(set(ids)),
            reason=reason,
            state="ready"
            if tier == 1 or (decision and decision.get("who") == "user")
            else "awaiting decision",
        )
        if tier == 1:
            value["model"] = reader
        if decision:
            value["decision"] = decision
        queue.append(value)
        return value

    items = []
    for entry in entries.values():
        if entry["kind"] != "item" or states[entry["id"]] == "superseded":
            continue
        disp = entry["disposition"]
        if disp["state"] not in {"queued", "shortfall"}:
            continue
        cls, target = effective_class(entry), entry["target"]
        row = dict(
            id=entry["id"],
            recorded_class=entry["class"],
            effective_class=cls,
            target=target,
            disposition=disp,
            action="recorded",
        )
        items.append(row)
        if disp["state"] == "shortfall":
            shortfalls.append(dict(id=entry["id"], **disp))
            continue
        impact = entry.get("impact")
        in_scope = impact is None or bool(scoped & set(impact["claims"]))
        status_change = impact is None or impact["changes_status"]
        if (
            cls == "E"
            and target not in {"spec", "records"}
            and (impact is not None or target == "review")
            and in_scope
            and status_change
        ):
            reason = (
                "impact unrecorded"
                if impact is None
                else "evidence changes a claim status in scope"
            )
            block("S3", f"{entry['id']}: {reason}")
            if target == "review" and "action" not in entry:
                unit(
                    "re-verification",
                    [entry["id"]],
                    "review claim-status impact",
                    suffix=entry["id"],
                )
        if target == "records":
            row["action"] = "records maintenance; not a spec item"
        elif cls == "W":
            row["action"] = "carry to next revision/brief; never starts a revision"
        elif "action" in entry:
            if in_scope and (
                target == "spec"
                and (cls == "R" or status_change)
                or target == "review"
                and cls == "R"
            ):
                block("S3", f"{entry['id']}: open {cls} item affecting scope")
            unit(
                entry["action"],
                [entry["id"]],
                disp["destination"],
                tier=2,
                decision=entry.get("decision"),
                suffix=entry["id"],
            )
            row["action"] = "tier-2 decision"
        elif in_scope and (
            target == "spec"
            and (cls == "R" or status_change)
            or target == "review"
            and cls == "R"
        ):
            block("S3", f"{entry['id']}: open {cls} item affecting scope")
            row["action"] = (
                "requirement decision" if cls == "R" else "evidence revision"
            )
            unit(
                "requirement-change" if cls == "R" else "evidence-revision",
                [entry["id"]],
                row["action"],
                tier=2 if cls == "R" else 1,
                decision=entry.get("decision"),
                suffix=entry["id"],
            )
        elif entry.get("execution") == "carry":
            row["action"] = "carry to next brief; no standalone round"
        elif target in {"candidate", "hardware", "upstream"} or "action" in entry:
            action = entry.get(
                "action",
                {
                    "candidate": "implementation",
                    "hardware": "hardware-run",
                    "upstream": "outward-report",
                }.get(target),
            )
            unit(
                action,
                [entry["id"]],
                disp["destination"],
                tier=2,
                decision=entry.get("decision"),
                suffix=entry["id"],
            )
            row["action"] = "tier-2 decision"
        else:
            row["action"] = (
                "re-verification of claim-status impact"
                if target == "review" and in_scope and status_change
                else "carry; no change to a claim status in scope"
            )
        if cls == "E" and target == "review" and impact is None:
            row["action"] = "impact unrecorded; " + row["action"]

    groups = reading_groups(status)
    for entry in entries.values():
        if states[entry["id"]] == "superseded":
            continue
        if (
            entry["kind"] == "result"
            and entry["claim"] in scoped
            and entry["verdict"] != "PASS"
        ):
            block("S3", f"{entry['id']}: open result {entry['verdict']}")
        if entry["kind"] == "observation" and states[entry["id"]] == "contested":
            block("S3", f"{entry['id']}: contested fact")
    for rid, group in groups.items():
        if any(e["id"] in eligible for e in group):
            assessment = group[0].get("assessment")
            if assessment is None or assessment["accuracy_failures"]:
                block("S3", f"{rid}: accuracy failures present or not classified")

    coverage = []
    for revision, header in status["revisions"].items():
        if header["requirement_change"] is False:
            continue
        required = header["changed_sections"] or sorted(
            {s for cid in scoped for s in claims[cid]["cites"]}
        )
        candidates = []
        independent = []
        for rid, group in groups.items():
            first = group[0]
            sections = [s for e in group if e["id"] in eligible for s in e["sections"]]
            if (
                int(revision) in first["covers_revisions"]
                and first["text"] == "landed"
                and first["independence"] in {"independent", "sequential"}
                and covers(sections, required)
            ):
                candidates.append(rid)
                if first["independence"] == "independent":
                    independent.append(rid)
        count = len(independent) + int(bool(set(candidates) - set(independent)))
        row = dict(
            revision=int(revision),
            readings=candidates,
            independent_count=count,
            required_sections=required,
        )
        coverage.append(row)
        if count < 2:
            block(
                "S4",
                f"revision {revision}: {count}/2 current independent reading lineages",
            )

    independent_groups = [
        g for g in groups.values() if g[0]["independence"] == "independent"
    ]
    latest = None
    if not independent_groups or any(
        "sequence" not in g[0] for g in independent_groups
    ):
        block("S5", "latest independent re-reading is not recorded in sequence")
    else:
        latest = max(independent_groups, key=lambda g: g[0]["sequence"])[0]
        assessment = latest.get("assessment")
        if assessment is None or assessment["r_items"]:
            block("S5", f"{latest['reading_id']}: R findings present or unclassified")

    rounds = round_report(status, groups)
    if not conditions["S4"]["met"] or not conditions["S5"]["met"]:
        reading = unit(
            "second-reading", [], "unmet S4/S5; read current text independently"
        )
        reading["coverage"] = coverage
    if scope and scope["reader"] != reader:
        unit(
            "comparison-reading",
            [],
            "reader role changed; compare and adjudicate before changing verdicts",
        )

    stale_by_kind = defaultdict(list)
    historical_stale = []
    for row in freshness["entries"]:
        entry = entries[row["id"]]
        if entry.get("claim") and entry["claim"] not in scoped:
            continue
        if entry["kind"] == "verification":
            if entry["purpose"] != "accuracy":
                historical_stale.append(entry["id"])
                continue
            basis = status["bases"][entry["basis"]]
            required = (
                basis["sections_read"]
                if basis["dependencies"] is None
                else entry["sections"] + basis["dependencies"]
            )
            renewed = any(
                set(entry["covers_revisions"]) <= set(group[0]["covers_revisions"])
                and group[0]["text"] == "landed"
                and group[0]["independence"] in {"independent", "sequential"}
                and covers(
                    [s for e in group if e["id"] in eligible for s in e["sections"]],
                    required,
                )
                for group in groups.values()
            )
            if renewed:
                historical_stale.append(entry["id"])
                continue
        kind = {
            "verification": "re-verification",
            "qualification": "requalification",
            "result": "acceptance-set-rerun",
            "candidate_round": "acceptance-set-rerun",
            "observation": "acceptance-set-rerun",
        }.get(entry["kind"])
        if entry["kind"] == "observation" and row["state"] == "contested":
            kind = "re-verification"
        if kind:
            stale_by_kind[kind].append(entry["id"])
    for kind, ids in sorted(stale_by_kind.items()):
        if kind == "requalification":
            for eid in sorted(ids):
                unit(
                    kind,
                    [eid],
                    "reconcile expected outcome and qualify on current identities",
                    suffix=entries[eid]["claim"],
                )
        else:
            unit(kind, ids, "refresh affected evidence on current identities")
    if freshness["stale_controls"]:
        unit(
            "requalification",
            [c["id"] for c in freshness["stale_controls"]],
            "reference control changed",
            suffix="controls",
        )

    priority = {
        "second-reading": 0,
        "comparison-reading": 1,
        "re-verification": 2,
        "requalification": 3,
        "acceptance-set-rerun": 4,
    }
    queue.sort(key=lambda u: (u["tier"], priority.get(u["kind"], 5), u["id"]))
    cap_blocked = any(r["state"] == "awaiting decision" for r in rounds)
    cap_reached = any(r["state"] == "limit reached" for r in rounds)
    if cap_blocked or cap_reached or not scope:
        for value in queue:
            if not scope or value["kind"] in {
                "second-reading",
                "comparison-reading",
                "re-verification",
                "evidence-revision",
            }:
                value["state"] = "awaiting decision"
    batch, waiting = select_batch(queue)
    sufficient = (
        all(c["met"] for c in conditions.values())
        and not cap_blocked
        and not freshness["unavailable"]
        and not freshness["stale_controls"]
        and not any(stale_by_kind.values())
        and not policy_blockers
    )
    blockers = [
        f"{name}: {reason}"
        for name, value in conditions.items()
        for reason in value["blockers"]
    ]
    blockers.extend(
        f"{e}: stale/contested evidence in scope"
        for ids in stale_by_kind.values()
        for e in ids
    )
    blockers.extend(
        f"{e}: unavailable source identity" for e in freshness["unavailable"]
    )
    blockers.extend(
        f"{e['id']}: stale reference control" for e in freshness["stale_controls"]
    )
    blockers.extend(f"{e}: different rule; not compared" for e in policy_blockers)
    blockers.extend(
        f"revision {r['revision']}: round cap exceeded"
        for r in rounds
        if r["state"] == "awaiting decision"
    )
    return dict(
        sufficient=sufficient,
        conditions=conditions,
        coverage=coverage,
        blockers=blockers,
        policy_blockers=policy_blockers,
        latest_independent=latest["reading_id"] if latest else None,
        round_cap=rounds,
        policy_changes=policy_changes,
        evaluation_policy=POLICY,
        open_items=items,
        shortfalls=shortfalls,
        queue=queue,
        batch=batch,
        waiting=waiting,
        historical_stale=sorted(historical_stale),
        reopening_entries=sorted(e for ids in stale_by_kind.values() for e in ids),
    )
