#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Report freshness, S1–S5 and a guarded queue without changing the index.

Exit status: 0 sufficient/no ready work, 1 findings/work, 2 usage, 3 missing inputs.
Use || true if findings should not stop a shell. --json emits one object.
"""

from collections import Counter
import json
from pathlib import Path
import sys

import index_check as check
import source_registry
import stopping
import deployment
from cli import Parser

# Named formats avoid nested quote conventions and work before Python 3.12.
# pylint: disable=consider-using-f-string

SKILL = """---
name: campaign-sweep
description: Report campaign freshness, stopping conditions and guarded work.
---
# Campaign sweep version 2
Run sweep.py CAMPAIGN [--registry SOURCES] [--deployment MANIFEST]
[--target-spec SPEC] [--json]. The default registry is
CAMPAIGN/sources.yaml. First run index_check.py to check file links/check names,
and refresh applicable registry files with pinned_file_adapter.py locally.
Only index/registry metadata, deployment configuration and class definitions
are opened. No registered source is parsed, hashed or executed. Existing
stale/contested states survive; superseded history
is excluded. Eligible counts are a freshness filter; stopping evaluates S1-S5
separately. Its queue/batch are proposals only, at most three units, with tier 2
requiring a user decision on that item. Models come from manifest roles: the
reader role reads (reference: Codex gpt-6-astra) and the reviewer role reviews
(reference: Claude Fable 5.1). Unknown classes are R; W never starts work.
Narrow mappings require exact old/new hashes and reviewer confirmation.
Missing mappings widen. Missing identities are reported, never invented.
JSON version 2 changes ok and the exit status to stopping sufficiency/no ready
work. The fresh key preserves CR3's verdict: no stale/contested entries, stale
controls or unavailable identities. Metadata input formats remain version 1.
Exits: 0 sufficient/no ready work, 1 findings/work, 2 usage, 3 missing input/blocked registry.
Use || true for nonfatal findings. JSON is one object; the index is never written.
"""

RUN_KINDS = {"qualification", "result", "candidate_round", "observation"}
CANDIDATE_KINDS = {"result", "candidate_round"}
FIELDS = {
    "harness": "harness_sha256",
    "guest_init": "guest_init_sha256",
    "reference": "reference_module_sha256",
    "candidate": "candidate_module_sha256",
    "guest_kernel": "guest.kernel_sha256",
    "guest_image": "guest.initramfs_sha256",
    "guest_busybox": "guest.busybox_sha256",
    "emulator": "emulator.sha256",
}


def overlap(left, right):
    """Section parents cover descendants, but 5.1 never covers 5.10."""
    return any(
        a == b or a.startswith(b + ".") or b.startswith(a + ".")
        for a in left
        for b in right
    )


def value_at(basis, path):
    """Resolve one explicitly supported nested identity field."""
    value = basis
    for part in path.split("."):
        if value is None:
            return None
        value = value[part]
    return value


def change_for(source, old_hash):
    """Only a reviewed, exact end-to-end map can narrow an identity change."""
    return next(
        (
            c
            for c in source.get("changes", [])
            if c["from_sha256"] == old_hash
            and c["to_sha256"] == source["sha256"]
            and c["reviewed"]
        ),
        None,
    )


def changed(source, basis, entry):
    """Compare recorded identities only; an absent basis cannot trigger change."""
    kind = source["kind"]
    if source.get("bindings") and entry["basis"] not in source["bindings"]:
        return False, None
    if kind in {"document", "kernel"}:
        pin = next(
            (
                p
                for p in basis["source_pins"]
                if p["id"] == source.get("pin", source["id"])
            ),
            None,
        )
        if pin is None:
            return False, None
        old = pin.get("sha256")
        drift = source["sha256"] is not None and (
            (old is not None and old != source["sha256"])
            or (
                old is None
                and source["expected_sha256"] is not None
                and source["sha256"] != source["expected_sha256"]
            )
        )
        return (
            pin["version"] != source["version"]
            or drift
            or (
                "commit" in pin
                and "commit" in source
                and pin["commit"] != source["commit"]
            )
        ), old
    if kind == "toolchain":
        old = basis["toolchain"]
        return old is not None and old != source["version"], None
    if kind not in FIELDS:
        return False, None
    old = (
        entry["validated_harness_sha256"]
        if kind == "harness" and entry["kind"] == "qualification"
        else value_at(basis, FIELDS[kind])
    )
    different = (
        old is not None and source["sha256"] is not None and old != source["sha256"]
    )
    if kind == "emulator" and basis["emulator"] is not None:
        different |= basis["emulator"]["version"] != source["version"]
    return different, old


def spec_rule(entry, basis, source, context):
    """C2 row 1: accumulate all revision headers since the recorded basis."""
    latest = source["revision"]
    old = basis["spec_revision"]
    if old == latest and basis["spec_sha256"] == source["sha256"]:
        return None
    headers = context["status"]["revisions"]
    known = old < latest and all(str(r) in headers for r in range(old + 1, latest + 1))
    known = known and headers[str(latest)]["spec_sha256"] == source["sha256"]
    sections = (
        [
            s
            for r in range(old + 1, latest + 1)
            for s in headers[str(r)]["changed_sections"]
        ]
        if known
        else None
    )
    requirement = (
        any(headers[str(r)]["requirement_change"] for r in range(old + 1, latest + 1))
        if known
        else True
    )
    mapping = change_for(source, basis["spec_sha256"])
    if not known and mapping:
        sections = mapping["sections"]
        requirement = source.get("requirement_change", True)
    kind = entry["kind"]
    if kind == "verification":
        if basis["dependencies"] is None or sections is None:
            return "spec changed; unknown dependencies/header: whole revision"
        if overlap(entry["sections"] + basis["dependencies"], sections):
            return "spec changed in reading sections or declared dependencies"
    if kind == "qualification" and (
        sections is None
        or overlap(context["claims"][entry["claim"]]["cites"], sections)
    ):
        return "spec changed in claim's expected-outcome sections"
    if kind in CANDIDATE_KINDS and requirement:
        return "spec changed a driver requirement"
    return None


def document_rule(entry, basis, source, context):
    """C2 row 2: missing citation/change detail widens to the whole document."""
    if entry["kind"] != "verification":
        return None
    differs, old = changed(source, basis, entry)
    if not differs:
        return None
    mapping = change_for(source, old)
    sections = context["registry"]["citations"].get(entry["id"], {}).get(source["id"])
    if not mapping or mapping["sections"] is None or sections is None:
        return "document changed; unmapped citation/change: whole document"
    if overlap(sections, mapping["sections"]):
        return "document changed in cited sections"
    return None


def kernel_rule(entry, basis, source, context):
    """C2 row 3: a source release affects source/kernel readings only."""
    del context
    if (
        entry["kind"] == "verification"
        and {"source-observed", "kernel"} & set(entry["evidence_classes"])
        and changed(source, basis, entry)[0]
    ):
        return "reference source/kernel pin changed"
    return None


def harness_rule(entry, basis, source, context):
    """C2 row 4: check -> scenario -> harness from reviewed diff metadata."""
    differs, old = changed(source, basis, entry)
    if entry["kind"] != "qualification" or not differs:
        return None
    mapping = change_for(source, old)
    claims = list(context["claims"].values())
    checks = {c for claim in claims for c in claim["checks"]}
    scenarios = {s for claim in claims for s in claim["scenarios"]}
    claim = context["claims"][entry["claim"]]
    if mapping and mapping["checks"] is not None and set(mapping["checks"]) <= checks:
        if set(mapping["checks"]) & set(claim["checks"]):
            return "harness diff changed a named check"
        return None
    if (
        mapping
        and mapping["scenarios"] is not None
        and set(mapping["scenarios"]) <= scenarios
    ):
        if set(mapping["scenarios"]) & set(claim["scenarios"]):
            return "harness diff widened to enclosing scenario"
        return None
    context["unmapped"].add(source["id"])
    return "harness diff unmapped/unreviewed: all qualifications"


def emulator_rule(entry, basis, source, context):
    """C2 row 5: runs and readings citing emulated evidence on that identity."""
    del context
    affected = entry["kind"] in RUN_KINDS or (
        entry["kind"] == "verification" and "emulated" in entry["evidence_classes"]
    )
    if affected and changed(source, basis, entry)[0]:
        return "emulator/guest identity changed"
    return None


def candidate_rule(entry, basis, source, context):
    """C2 row 6: candidate identity cannot requalify or disqualify checks."""
    del context
    if entry["kind"] in CANDIDATE_KINDS and changed(source, basis, entry)[0]:
        return "candidate build changed"
    return None


def toolchain_rule(entry, basis, source, context):
    """A recorded compiler change invalidates run verdicts using that build."""
    del context
    if entry["kind"] in RUN_KINDS and changed(source, basis, entry)[0]:
        return "recorded toolchain changed"
    return None


def unchanged_rule(entry, basis, source, context):
    """C2 rows 8 and 9: new fixtures/models do not invalidate earlier scope."""
    del entry, basis, source, context
    return None


RULES = {
    "spec": spec_rule,
    "document": document_rule,
    "kernel": kernel_rule,
    "harness": harness_rule,
    "guest_init": harness_rule,
    "emulator": emulator_rule,
    "guest_kernel": emulator_rule,
    "guest_image": emulator_rule,
    "guest_busybox": emulator_rule,
    "candidate": candidate_rule,
    "toolchain": toolchain_rule,
    "model": unchanged_rule,
    "fixture": unchanged_rule,
    "reference": unchanged_rule,
}


def spec_since(entry, basis, source, context):
    """Name the earliest recorded revision that invalidated this entry."""
    for number in range(basis["spec_revision"] + 1, source["revision"] + 1):
        header = context["status"]["revisions"].get(str(number))
        if header is None:
            break
        intermediate = dict(
            source, revision=number, sha256=header["spec_sha256"], changes=[]
        )
        if spec_rule(entry, basis, intermediate, context):
            return f"spec-r{number}"
    mapping = change_for(source, basis["spec_sha256"])
    return mapping["since"] if mapping else "spec-r{revision}".format(**source)


def sweep(claims, status, registry, reader=None, roles=None):
    """Compare metadata; supplied roles keep evaluation free of file reads."""
    roles = deployment.load() if roles is None else roles
    check.validate(claims, status, None)
    source_registry.validate(registry, claims, status)
    context = dict(
        claims={c["id"]: c for c in claims["claims"]},
        status=status,
        registry=registry,
        unmapped=set(),
    )
    entries = {e["id"]: e for e in status["entries"]}
    reasons = {e["id"]: [] for e in entries.values()}
    states = {e["id"]: e["status"]["state"] for e in entries.values()}
    controls = {}
    unavailable = sorted(s["id"] for s in registry["sources"] if s["status"] != "ok")
    for entry in entries.values():
        eid = entry["id"]
        if states[eid] == "superseded":
            continue
        if states[eid] != "current":
            reasons[eid].append(
                dict(
                    reason=entry["status"]["reason"],
                    since=entry["status"]["stale_since"],
                    source="index",
                )
            )
        basis = status["bases"][entry["basis"]]
        for source in registry["sources"]:
            if source["status"] != "ok":
                continue
            reason = RULES[source["kind"]](entry, basis, source, context)
            if reason:
                mapping = change_for(source, changed(source, basis, entry)[1])
                since = mapping["since"] if mapping else source["checked"]
                if source["kind"] == "spec":
                    since = spec_since(entry, basis, source, context)
                reasons[eid].append(
                    dict(reason=reason, since=since, source=source["id"])
                )
                if states[eid] == "current":
                    states[eid] = "stale"
            if (
                source["kind"] == "reference"
                and entry["kind"] == "qualification"
                and changed(source, basis, entry)[0]
            ):
                for defect in context["claims"][entry["claim"]]["defects"]:
                    for run in defect["control_runs"]:
                        controls[run] = dict(
                            id=run,
                            state="stale",
                            since=source["checked"],
                            reason="reference module changed",
                        )
    for observation in entries.values():
        if observation["kind"] != "observation" or states[observation["id"]] != "stale":
            continue
        for entry in entries.values():
            if (
                entry["kind"] != "verification"
                or states[entry["id"]] == "superseded"
                or "emulated" not in entry["evidence_classes"]
            ):
                continue
            basis = status["bases"][entry["basis"]]
            if basis["dependencies"] is None or overlap(
                entry["sections"] + basis["dependencies"], observation["sections"]
            ):
                if states[entry["id"]] == "current":
                    states[entry["id"]] = "stale"
                reasons[entry["id"]].append(
                    dict(
                        reason="cited emulated observation is stale",
                        since=reasons[observation["id"]][0]["since"],
                        source=observation["id"],
                    )
                )
    conflicts = []
    for conflict in registry["contradictions"]:
        eid = conflict["observation"]
        if states[eid] == "superseded":
            continue
        states[eid] = "contested"
        reason = dict(
            reason="hardware contradicts emulated observation",
            since=conflict["since"],
            source=conflict["conflict"],
        )
        reasons[eid].append(reason)
        conflicts.append(conflict)
    for observation in entries.values():
        eid = observation["id"]
        if observation["kind"] != "observation" or states[eid] != "contested":
            continue
        since = next((r["since"] for r in reasons[eid] if r["since"]), f"index:{eid}")
        for entry in entries.values():
            if states[entry["id"]] == "superseded":
                continue
            uses = False
            if entry["kind"] == "qualification":
                premise = registry["premises"].get(entry["claim"])
                uses = (
                    eid in premise
                    if premise is not None
                    else overlap(
                        context["claims"][entry["claim"]]["cites"],
                        observation["sections"],
                    )
                )
            if (
                entry["kind"] == "verification"
                and "emulated" in entry["evidence_classes"]
            ):
                basis = status["bases"][entry["basis"]]
                uses = basis["dependencies"] is None or overlap(
                    entry["sections"] + basis["dependencies"], observation["sections"]
                )
            if uses:
                if states[entry["id"]] == "current":
                    states[entry["id"]] = "stale"
                reasons[entry["id"]].append(
                    dict(
                        reason="premise observation contested",
                        since=since,
                        source=eid,
                    )
                )
    rows = [
        dict(
            id=eid,
            kind=entries[eid]["kind"],
            state=states[eid],
            previous_state=entries[eid]["status"]["state"],
            reasons=reasons[eid],
            stale_since=(reasons[eid][0]["since"] if states[eid] == "stale" else None),
        )
        for eid in sorted(entries)
        if states[eid] in {"stale", "contested"}
    ]
    accepted = sorted(
        eid
        for eid in entries
        if states[eid] == "current" and entries[eid]["kind"] != "item"
    )
    result = dict(
        version=2,
        campaign=status["campaign"],
        fresh=not rows and not controls and not unavailable,
        entries=rows,
        stale_controls=[controls[k] for k in sorted(controls)],
        conflicts=conflicts,
        unavailable=unavailable,
        unmapped_harness=sorted(context["unmapped"]),
        eligible=accepted,
        eligible_counts=dict(Counter(entries[e]["kind"] for e in accepted)),
        counts=dict(Counter(states.values())),
    )
    result["stopping"] = stopping.evaluate(
        claims, status, result, reader=reader, roles=roles
    )
    result["ok"] = result["stopping"]["sufficient"] and not result["stopping"]["batch"]
    return result


def main(argv=None):
    """Read campaign and deployment metadata and report, without side effects."""
    parser = Parser(description=__doc__)
    parser.add_argument("campaign", nargs="?", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--deployment", type=Path)
    parser.add_argument("--target-spec", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--skill", action="store_true")
    args = parser.parse_args(argv)
    if args.skill:
        print(SKILL)
        return 0
    if args.campaign is None:
        parser.error("campaign is required")
    result, code = {"ok": False, "findings": []}, 0
    if check.yaml is None:
        result["findings"], code = ["PyYAML is required; use uv run --with pyyaml"], 3
    else:
        try:
            result = sweep(
                check.read_yaml(args.campaign / "claims.yaml"),
                check.read_yaml(args.campaign / "status.yaml"),
                check.read_yaml(args.registry or args.campaign / "sources.yaml"),
                roles=deployment.load(args.deployment, args.target_spec),
            )
            code = 3 if result["unavailable"] else 0 if result["ok"] else 1
        except OSError:
            result["findings"], code = ["Cannot read a required metadata file"], 3
        except (ValueError, check.yaml.YAMLError) as exc:
            detail = (
                str(exc)
                if isinstance(exc, check.Invalid)
                else "invalid input encoding or syntax"
            )
            result["findings"], code = [detail], 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif "entries" in result:
        for entry in result["entries"]:
            reasons = "; ".join(
                "{reason} (since {since})".format(**r) for r in entry["reasons"]
            )
            print("{state} {id}: {reasons}".format(**dict(entry, reasons=reasons)))
        for control in result["stale_controls"]:
            print("stale control {id}: {reason}".format(**control))
        print("Counts: " + json.dumps(result["counts"], sort_keys=True))
        print(
            "Eligible records (not acceptance): "
            + json.dumps(result["eligible_counts"], sort_keys=True)
        )
        print("Unavailable sources: " + ", ".join(result["unavailable"]))
        print("Unmapped harness changes: " + ", ".join(result["unmapped_harness"]))
        report = result["stopping"]
        print("Sufficient for scope: " + str(report["sufficient"]))
        for condition, value in report["conditions"].items():
            print(
                condition
                + ": "
                + ("met" if value["met"] else "; ".join(value["blockers"]))
            )
        for key in (
            "blockers",
            "round_cap",
            "policy_changes",
            "open_items",
            "shortfalls",
            "queue",
        ):
            print(key + ": " + json.dumps(report[key], sort_keys=True))
        print("First batch: " + ", ".join(report["batch"]))
        print("Waiting for next batch: " + ", ".join(report["waiting"]))
    else:
        print("\n".join(result["findings"]))
    return code


if __name__ == "__main__":
    sys.exit(main())
