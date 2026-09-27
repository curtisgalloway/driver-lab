#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Check campaign claim maps and status indexes without running a harness.

Exit status: 0 clean, 1 findings, 2 usage error, 3 missing precondition.
Callers that want findings to be nonfatal may use || true. --json emits one
object with ok, counts and findings. No private run store is opened.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import datetime
import math
import json
import operator
from pathlib import Path
import re
import sys

# Exact types deliberately exclude YAML booleans from integer fields.
# pylint: disable=unidiomatic-typecheck

try:
    import yaml
except ImportError:
    yaml = None

HASH = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
SECTION = re.compile(r"[0-9]+(?:\.[0-9]+)*\Z")
STATES = {"current", "stale", "contested", "superseded"}
REASONS = {"unobservable", "blocked", "out of scope", "not worth it"}
RULES = {
    "isolated-defect-specific-A6-2026-09-25",
    "isolated-acceptance-set-2-repetitions",
    "emulated-observation-not-hardware",
    "C6-item-classification-2026-09-26",
    "A1-as-written",
    "A1-amended-2026-09-26",
}
EVIDENCE_CLASSES = {
    "databook",
    "standard",
    "source-observed",
    "inference",
    "kernel",
    "emulated",
}
SKILL = """---
name: campaign-index-check
description: Validate a campaign's claim map, status index and evidence links.
---
# Campaign index checker, format version 1
Run `index_check.py CAMPAIGN --root REPOSITORY [--json]` with PyYAML installed.
CAMPAIGN holds claims.yaml and status.yaml. --root defaults to the working
 directory; all evidence and harness links are relative to that root.
The checker reads only these public files and the harness's Python syntax tree.
It never launches guests or reads private sources. Findings exit 1, missing inputs
exit 3, usage errors exit 2, clean exits 0. JSON always has ok, counts, findings.
A clean result validates structure and links, not the truth of a recorded verdict.
"""


class Invalid(ValueError):
    """An index or name expression cannot be validated."""


def require(condition, message):
    """Stop this validation with an actionable finding."""
    if not condition:
        raise Invalid(message)


def mapping(value, required, optional=()):
    """Check a closed mapping shape."""
    require(isinstance(value, dict), "expected a mapping")
    require(
        set(required) <= value.keys(), f"missing fields: {set(required) - value.keys()}"
    )
    require(value.keys() <= set(required) | set(optional), "unknown fields")


def string(value):
    """Require a nonempty string."""
    require(
        isinstance(value, str) and bool(value.strip()), "expected a nonempty string"
    )


def strings(value, nonempty=False, pattern=None):
    """Check a unique list of strings, optionally constrained by a regex."""
    require(isinstance(value, list), "expected a list")
    require(not nonempty or bool(value), "expected a nonempty list")
    for part in value:
        string(part)
        require(pattern is None or pattern.fullmatch(part), f"invalid value: {part}")
    require(len(set(value)) == len(value), "duplicate list member")


def sha(value, nullable=True):
    """Require a full SHA-256, never an abbreviated identity."""
    require(
        (nullable and value is None)
        or (isinstance(value, str) and HASH.fullmatch(value)),
        "expected full SHA-256",
    )


def date(value):
    """Require an ISO date stored as a string."""
    string(value)
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise Invalid("expected ISO date") from exc


def local_file(root, value):
    """Resolve a repository-relative file, rejecting escapes including symlinks."""
    string(value)
    part = value.split("#", 1)[0]
    require(
        part and not Path(part).is_absolute(), "expected repository-relative file link"
    )
    if root is None:
        require(".." not in Path(part).parts, "link escapes repository")
        return Path(part)
    path = (root / part).resolve()
    require(path.is_relative_to(root), "link escapes repository")
    require(path.is_file(), f"link does not resolve to a file: {value}")
    return path


def links(root, values):
    """Check evidence links; fragments are locators, not validated anchors."""
    strings(values, nonempty=True)
    for value in values:
        local_file(root, value)


def literal(node, env):
    """Evaluate only the finite literal expressions used to construct check names.

    Unknown runtime values are None. No imports, calls, attribute reads or harness
    code execute. Unsupported name construction therefore fails closed.
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.Attribute):
        return None
    if isinstance(node, (ast.List, ast.Tuple)):
        return [literal(x, env) for x in node.elts]
    if isinstance(node, ast.BinOp):
        op = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.FloorDiv: operator.floordiv,
        }.get(type(node.op))
        if op:
            return op(literal(node.left, env), literal(node.right, env))
    if isinstance(node, ast.IfExp):
        return literal(node.body if literal(node.test, env) else node.orelse, env)
    if isinstance(node, ast.Subscript):
        return literal(node.value, env)[literal(node.slice, env)]
    if isinstance(node, ast.Slice):
        return slice(
            *(
                literal(x, env) if x else None
                for x in (node.lower, node.upper, node.step)
            )
        )
    if isinstance(node, ast.JoinedStr):
        parts = []
        for part in node.values:
            if isinstance(part, ast.Constant):
                parts.append(part.value)
            else:
                require(part.conversion == -1, "formatted conversion unsupported")
                require(part.format_spec is None, "format specification unsupported")
                value = literal(part.value, env)
                require(value is not None, "unresolved name expression")
                parts.append(format(value))
        return "".join(parts)
    if isinstance(node, ast.ListComp) and len(node.generators) == 1:
        gen = node.generators[0]
        require(not gen.ifs, "filtered name comprehension unsupported")
        result = []
        for value in literal(gen.iter, env):
            child = dict(env)
            bind(gen.target, value, child)
            result.append(literal(node.elt, child))
        return result
    raise Invalid("unsupported literal expression")


def maybe_literal(node, env):
    """Non-name runtime expressions need not be understood."""
    try:
        return literal(node, env)
    except (Invalid, TypeError, ValueError, KeyError, IndexError):
        return None


def bind(target, value, env):
    """Bind a literal assignment or loop target."""
    if isinstance(target, ast.Name):
        env[target.id] = value
    elif isinstance(target, (ast.Tuple, ast.List)):
        if isinstance(value, (tuple, list)) and len(value) == len(target.elts):
            for sub, part in zip(target.elts, value):
                bind(sub, part, env)


def harness_check_names(path):
    """Statically collect exact emitted names along scenario/helper call paths.

    Finite loops and literal helper arguments are expanded, including frame sizes,
    reload suffixes and HTTP sizes. Runtime branches are both visited; runtime
    effects are never executed. This is a name check, not a reachability proof.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    globals_ = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                bind(target, maybe_literal(node.value, globals_), globals_)
    names = set()

    def calls(node, env, stack):
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            if isinstance(call.func, ast.Attribute):
                if call.func.attr in {"check", "defer"} and call.args:
                    if any(
                        k.arg == "check" and maybe_literal(k.value, env) is False
                        for k in call.keywords
                    ):
                        continue
                    name = maybe_literal(call.args[0], env)
                    if isinstance(name, str):
                        names.add(name)
            elif isinstance(call.func, ast.Name) and call.func.id in funcs:
                name = call.func.id
                if name in stack:
                    continue
                fn = funcs[name]
                child = dict(globals_)
                for arg, default in zip(
                    fn.args.args[-len(fn.args.defaults) :], fn.args.defaults
                ):
                    child[arg.arg] = maybe_literal(default, env)
                for arg, value in zip(fn.args.args, call.args):
                    child[arg.arg] = maybe_literal(value, env)
                for kw in call.keywords:
                    child[kw.arg] = maybe_literal(kw.value, env)
                walk(fn.body, child, stack | {name})

    def walk(nodes, env, stack):
        for node in nodes:
            if isinstance(node, ast.FunctionDef):
                continue
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                if node.value:
                    calls(node.value, env, stack)
                    value = maybe_literal(node.value, env)
                    for target in (
                        node.targets if isinstance(node, ast.Assign) else [node.target]
                    ):
                        bind(target, value, env)
            elif isinstance(node, ast.For):
                values = maybe_literal(node.iter, env)
                if isinstance(values, (tuple, list)):
                    for value in values:
                        child = dict(env)
                        bind(node.target, value, child)
                        walk(node.body, child, stack)
            elif isinstance(node, ast.If):
                calls(node.test, env, stack)
                walk(node.body, dict(env), stack)
                walk(node.orelse, dict(env), stack)
            elif isinstance(node, ast.Try):
                for body in [node.body, node.orelse, node.finalbody]:
                    walk(body, dict(env), stack)
            else:
                calls(node, env, stack)

    for name, fn in funcs.items():
        if name.startswith("scenario_") or name == "settle":
            walk(fn.body, dict(globals_), {name})
    fn = funcs.get("trace_rules")
    if fn:
        for node in ast.walk(fn):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == "checks" and isinstance(node.value, ast.List):
                    for row in node.value.elts:
                        if isinstance(row, ast.Tuple) and row.elts:
                            name = maybe_literal(row.elts[0], globals_)
                            if isinstance(name, str):
                                names.add(name)
    return names


def check_basis(basis):
    """Validate recorded identities; null never means an invented identity."""
    mapping(
        basis,
        (
            "spec_revision",
            "spec_sha256",
            "sections_read",
            "dependencies",
            "source_pins",
            "harness_sha256",
            "guest_init_sha256",
            "emulator",
            "guest",
            "reference_module_sha256",
            "candidate_module_sha256",
            "toolchain",
            "model",
            "missing",
        ),
    )
    require(
        type(basis["spec_revision"]) is int and basis["spec_revision"] > 0,
        "invalid spec revision",
    )
    for key in (
        "spec_sha256",
        "harness_sha256",
        "guest_init_sha256",
        "reference_module_sha256",
        "candidate_module_sha256",
    ):
        sha(basis[key], nullable=key != "spec_sha256")
    strings(basis["sections_read"], pattern=SECTION)
    if basis["dependencies"] is not None:
        strings(basis["dependencies"], pattern=SECTION)
    strings(basis["missing"])
    require(isinstance(basis["source_pins"], list), "source_pins must be a list")
    pin_ids = []
    for pin in basis["source_pins"]:
        mapping(pin, ("id", "version"), ("sha256", "commit"))
        string(pin["id"])
        string(pin["version"])
        pin_ids.append(pin["id"])
        require("sha256" in pin or "commit" in pin, "source pin lacks identity")
        if "sha256" in pin:
            sha(pin["sha256"], nullable=False)
        if "commit" in pin:
            require(
                isinstance(pin["commit"], str)
                and re.fullmatch("[0-9a-f]{40}", pin["commit"]),
                "invalid commit",
            )
    require(len(pin_ids) == len(set(pin_ids)), "duplicate source pin")
    if basis["emulator"] is not None:
        mapping(basis["emulator"], ("id", "version", "sha256", "accel"))
        for key in ("id", "version", "accel"):
            string(basis["emulator"][key])
        sha(basis["emulator"]["sha256"], nullable=False)
    if basis["guest"] is not None:
        mapping(basis["guest"], ("kernel_sha256", "busybox_sha256", "initramfs_sha256"))
        for value in basis["guest"].values():
            sha(value)
    if basis["toolchain"] is not None:
        string(basis["toolchain"])
    if basis["model"] is not None:
        mapping(basis["model"], ("role", "name", "version"))
        require(
            isinstance(basis["model"]["role"], str)
            and basis["model"]["role"] in {"reader", "implementer", "reviewer"},
            "invalid model role",
        )
        string(basis["model"]["name"])
        string(basis["model"]["version"])


def check_shortfall(value):
    """Every shortfall carries an allowed reason and reopening condition."""
    require(
        isinstance(value.get("reason"), str) and value["reason"] in REASONS,
        "invalid shortfall reason",
    )
    string(value.get("reopen"))


def check_entry(entry, bases, root):
    """Validate common fields and the selected entry kind."""
    common = (
        "id",
        "kind",
        "basis",
        "verdict",
        "rule",
        "status",
        "supersedes",
        "run_ids",
        "evidence",
    )
    fields = {
        "qualification": ("claim", "validated_harness_sha256"),
        "result": ("claim", "round", "qualification", "qualified_evidence"),
        "observation": ("sections", "evidence_class"),
        "item": ("class", "source", "target", "disposition"),
        "verification": (
            "text",
            "sections",
            "evidence_classes",
            "verifier",
            "round",
            "independence",
            "purpose",
            "covers_revisions",
            "scope",
            "reading_id",
        ),
        "candidate_round": (
            "round",
            "applied_items",
            "verification",
            "results",
            "scope",
        ),
    }
    kind = entry.get("kind")
    require(isinstance(kind, str) and kind in fields, "invalid entry kind")
    optional = ("decision", "cost")
    if kind != "verification":
        optional += ("shortfall", "aliases")
    mapping(entry, common + fields[kind], optional)
    string(entry["id"])
    require(ID.fullmatch(entry["id"]), "invalid entry ID")
    string(entry["basis"])
    require(entry["basis"] in bases, "unknown basis")
    string(entry["verdict"])
    require(isinstance(entry["rule"], str) and entry["rule"] in RULES, "unknown rule")
    status = entry["status"]
    mapping(status, ("state", "reason", "stale_since"))
    require(
        isinstance(status["state"], str) and status["state"] in STATES, "invalid status"
    )
    string(status["reason"])
    if status["state"] == "stale":
        string(status["stale_since"])
    else:
        require(status["stale_since"] is None, "stale_since requires stale status")
    strings(entry["supersedes"], pattern=ID)
    strings(entry["run_ids"], nonempty=True)
    links(root, entry["evidence"])
    if "aliases" in entry:
        strings(entry["aliases"], nonempty=True, pattern=ID)
    if "shortfall" in entry:
        mapping(entry["shortfall"], ("reason", "reopen"))
        check_shortfall(entry["shortfall"])
    if "decision" in entry:
        decision = entry["decision"]
        mapping(decision, ("who", "date", "link"))
        string(decision["who"])
        date(decision["date"])
        local_file(root, decision["link"])
    if "cost" in entry:
        mapping(entry["cost"], (), ("seconds", "tokens", "usd"))
        require(bool(entry["cost"]), "empty cost")
        for value in entry["cost"].values():
            require(
                type(value) in (int, float) and math.isfinite(value) and value >= 0,
                "invalid cost",
            )
    if kind in {"qualification", "result"}:
        string(entry["claim"])
    if kind == "qualification":
        require(
            entry["verdict"]
            in {"qualified", "shortfall", "unqualified", "insensitive"},
            "invalid qualification verdict",
        )
        sha(entry["validated_harness_sha256"], nullable=False)
        require(
            ("shortfall" in entry) == (entry["verdict"] == "shortfall"),
            "shortfall verdict and details must agree",
        )
    elif kind == "result":
        require(entry["verdict"] in {"PASS", "FAIL", "ERROR"}, "invalid result verdict")
        require(type(entry["qualified_evidence"]) is bool, "invalid qualified_evidence")
        string(entry["round"])
        string(entry["qualification"])
        sha(bases[entry["basis"]]["candidate_module_sha256"], nullable=False)
        sha(bases[entry["basis"]]["harness_sha256"], nullable=False)
    elif kind == "observation":
        strings(entry["sections"], nonempty=True, pattern=SECTION)
        require(entry["evidence_class"] == "emulated", "invalid observation class")
    elif kind == "verification":
        for key in ("text", "verifier", "round", "scope", "reading_id"):
            string(entry[key])
        require(ID.fullmatch(entry["reading_id"]), "invalid reading ID")
        strings(entry["sections"], nonempty=True, pattern=SECTION)
        strings(entry["evidence_classes"], nonempty=True)
        require(
            set(entry["evidence_classes"]) <= EVIDENCE_CLASSES,
            "invalid verification evidence class",
        )
        require(
            entry["rule"] in {"A1-as-written", "A1-amended-2026-09-26"},
            "invalid verification rule",
        )
        require(
            isinstance(entry["independence"], str)
            and entry["independence"]
            in {"independent", "sequential", "adjudication", "gate"},
            "invalid reading independence",
        )
        require(
            isinstance(entry["purpose"], str)
            and entry["purpose"] in {"accuracy", "transfer", "acceptance"},
            "invalid reading purpose",
        )
        require(
            (entry["independence"] == "gate") == (entry["purpose"] != "accuracy"),
            "gate cannot count as accuracy",
        )
        covered = entry["covers_revisions"]
        require(
            isinstance(covered, list)
            and bool(covered)
            and all(type(r) is int and r > 0 for r in covered),
            "invalid covered revisions",
        )
        require(len(covered) == len(set(covered)), "duplicate covered revision")
        basis = bases[entry["basis"]]
        require(
            set(entry["sections"]) <= set(basis["sections_read"]),
            "verification sections outside reading basis",
        )
        require(
            basis["model"] is not None and basis["model"]["role"] == "reader",
            "verification requires reader model",
        )
    elif kind == "candidate_round":
        string(entry["round"])
        string(entry["scope"])
        for key in ("applied_items", "verification", "results"):
            strings(entry[key], nonempty=key != "results", pattern=ID)
        sha(bases[entry["basis"]]["candidate_module_sha256"], nullable=False)
        sha(bases[entry["basis"]]["harness_sha256"], nullable=False)
    else:
        require(
            isinstance(entry["class"], str) and entry["class"] in {"R", "E", "W"},
            "invalid item class",
        )
        require(
            type(entry["source"]) is int and entry["source"] in {1, 2, 3},
            "invalid item source",
        )
        require(
            isinstance(entry["target"], str)
            and entry["target"]
            in {"spec", "candidate", "records", "upstream", "hardware", "review"},
            "invalid item target",
        )
        disp = entry["disposition"]
        mapping(disp, ("state",), ("revision", "reason", "reopen", "destination"))
        require(
            isinstance(disp["state"], str)
            and disp["state"] in {"queued", "applied", "shortfall", "rejected"},
            "invalid disposition",
        )
        fields = {
            "queued": ("destination",),
            "applied": ("revision",),
            "shortfall": ("reason", "reopen", "destination"),
            "rejected": ("reason",),
        }
        mapping(disp, ("state",), fields[disp["state"]])
        if "destination" in disp:
            string(disp["destination"])
        if disp["state"] == "shortfall":
            check_shortfall(disp)
        if disp["state"] == "applied":
            require(
                type(disp.get("revision")) is int and disp["revision"] > 0,
                "applied item needs revision",
            )
        if disp["state"] == "queued":
            string(disp.get("destination"))
        if disp["state"] == "rejected":
            string(disp.get("reason"))


def check_history(status_doc, by_id, root):
    """Bind readings to exact texts and requirement changes to applied findings."""
    span = status_doc["revision_range"]
    require(
        isinstance(span, list)
        and len(span) == 2
        and all(type(r) is int and r > 0 for r in span)
        and span[0] <= span[1],
        "invalid revision range",
    )
    revisions = status_doc["revisions"]
    require(isinstance(revisions, dict), "revisions must be a mapping")
    require(
        set(revisions) == {str(r) for r in range(span[0], span[1] + 1)},
        "missing or unexpected revision in declared range",
    )
    bases = status_doc["bases"]
    reading_groups = {}
    for entry in by_id.values():
        if entry["kind"] == "verification":
            reading_groups.setdefault(entry["reading_id"], []).append(entry)
    for group in reading_groups.values():
        first = group[0]
        sections = []
        for entry in group:
            for key in (
                "basis",
                "text",
                "verdict",
                "round",
                "verifier",
                "independence",
                "purpose",
                "covers_revisions",
                "rule",
                "evidence_classes",
                "run_ids",
                "evidence",
                "scope",
            ):
                require(entry[key] == first[key], "inconsistent reading slices")
            sections.extend(entry["sections"])
        require(len(sections) == len(set(sections)), "overlapping reading slices")
        require(
            set(sections) == set(bases[first["basis"]]["sections_read"]),
            "missing reading section slice",
        )
    for number, revision in revisions.items():
        mapping(
            revision,
            (
                "spec_sha256",
                "drafts",
                "requirement_change",
                "changed_sections",
                "items",
                "evidence",
                "run_ids",
            ),
        )
        sha(revision["spec_sha256"], nullable=False)
        require(isinstance(revision["drafts"], dict), "drafts must be a mapping")
        for key, value in revision["drafts"].items():
            require(ID.fullmatch(key) and key != "landed", "invalid draft ID")
            sha(value, nullable=False)
            require(value != revision["spec_sha256"], "draft duplicates landed hash")
        changed = revision["requirement_change"]
        require(
            type(changed) is bool or (changed is None and int(number) == span[0]),
            "invalid requirement-change header",
        )
        strings(
            revision["changed_sections"], nonempty=changed is not None, pattern=SECTION
        )
        strings(revision["items"], pattern=ID)
        links(root, revision["evidence"])
        strings(revision["run_ids"], nonempty=True)
        applied_r = []
        for item_id in revision["items"]:
            item = by_id.get(item_id)
            require(
                item is not None
                and item["kind"] == "item"
                and item["target"] == "spec"
                and item["disposition"]
                == {"state": "applied", "revision": int(number)},
                "revision item must be applied to this spec revision",
            )
            if item["class"] == "R":
                applied_r.append(item_id)
        require(
            bool(applied_r) == (changed is True),
            "requirement-change header needs matching R item chain",
        )
        readings = [
            e
            for e in by_id.values()
            if e["kind"] == "verification"
            and int(number) in e["covers_revisions"]
            and e["purpose"] == "accuracy"
        ]
        require(bool(readings), f"revision {number}: missing verification")
    for entry in by_id.values():
        kind = entry["kind"]
        if (
            kind == "item"
            and entry["target"] == "spec"
            and entry["disposition"]["state"] == "applied"
        ):
            destination = revisions.get(str(entry["disposition"]["revision"]))
            require(destination is not None, "applied spec item destination is missing")
            require(
                entry["id"] in destination["items"],
                "applied spec item missing from destination header",
            )
        if kind not in {"verification", "candidate_round"}:
            continue
        basis = bases[entry["basis"]]
        number = basis["spec_revision"]
        revision = revisions.get(str(number))
        require(revision is not None, "unknown history revision")
        if kind == "verification":
            text = entry["text"]
            expected = (
                revision["spec_sha256"]
                if text == "landed"
                else revision["drafts"].get(text)
            )
            require(
                expected is not None and basis["spec_sha256"] == expected,
                "verification spec_sha256 does not match revision text",
            )
            require(
                number in entry["covers_revisions"]
                and all(
                    str(r) in revisions and r <= number
                    for r in entry["covers_revisions"]
                ),
                "covered revision does not match reading basis",
            )
            if text != "landed":
                require(
                    entry["status"]["state"] == "superseded",
                    "draft reading must remain superseded",
                )
            if entry["status"]["state"] == "current":
                require(
                    number == span[1] or basis["dependencies"] is not None,
                    "older reading without dependencies must widen, not stay current",
                )
        else:
            require(
                basis["spec_sha256"] == revision["spec_sha256"],
                "candidate round spec hash does not match landed revision",
            )
            for item_id in entry["applied_items"]:
                require(
                    item_id in revision["items"] and by_id[item_id]["class"] == "R",
                    "candidate round lacks matching applied R item",
                )
            for reading_id in entry["verification"]:
                reading = by_id.get(reading_id)
                require(
                    reading is not None
                    and reading["kind"] == "verification"
                    and reading["purpose"] == "accuracy"
                    and reading["text"] == "landed"
                    and bases[reading["basis"]]["spec_revision"] == number,
                    "candidate round lacks landed verification link",
                )
            for result_id in entry["results"]:
                result = by_id.get(result_id)
                require(
                    result is not None
                    and result["kind"] == "result"
                    and result["basis"] == entry["basis"]
                    and result["round"] == entry["round"],
                    "candidate round result basis or round mismatch",
                )


def validate(claims_doc, status_doc, root):
    """Validate documents; root=None checks metadata without opening source files."""
    mapping(claims_doc, ("version", "campaign", "harness", "claims"))
    mapping(
        status_doc,
        ("version", "campaign", "revision_range", "revisions", "bases", "entries"),
    )
    require(
        type(claims_doc["version"]) is int
        and claims_doc["version"] == 1
        and type(status_doc["version"]) is int
        and status_doc["version"] == 1,
        "unsupported format version",
    )
    string(claims_doc["campaign"])
    require(claims_doc["campaign"] == status_doc["campaign"], "campaign mismatch")
    names = (
        harness_check_names(local_file(root, claims_doc["harness"]))
        if root is not None
        else None
    )
    require(names is None or bool(names), "no harness check names found")
    claims = claims_doc["claims"]
    require(isinstance(claims, list) and bool(claims), "claims must be a nonempty list")
    by_claim = {}
    for claim in claims:
        mapping(
            claim,
            (
                "id",
                "title",
                "mandatory",
                "cites",
                "checks",
                "scenarios",
                "scope",
                "defects",
                "evidence",
            ),
        )
        string(claim["id"])
        require(ID.fullmatch(claim["id"]), "invalid claim ID")
        require(claim["id"] not in by_claim, "duplicate claim ID")
        by_claim[claim["id"]] = claim
        string(claim["title"])
        string(claim["scope"])
        require(type(claim["mandatory"]) is bool, "invalid mandatory flag")
        strings(claim["cites"], nonempty=True, pattern=SECTION)
        strings(claim["checks"], nonempty=True)
        claim_id = claim["id"]
        for name in claim["checks"]:
            require(
                names is None or name in names,
                f"{claim_id}: unknown harness check: {name}",
            )
        strings(claim["scenarios"], nonempty=True, pattern=ID)
        links(root, claim["evidence"])
        require(isinstance(claim["defects"], list), "defects must be a list")
        for defect in claim["defects"]:
            mapping(defect, ("id", "run_ids", "control_runs", "outcome", "evidence"))
            string(defect["id"])
            strings(defect["run_ids"], nonempty=True)
            strings(defect["control_runs"], nonempty=True)
            require(
                isinstance(defect["outcome"], str)
                and defect["outcome"]
                in {
                    "detected",
                    "unobservable",
                    "insensitive",
                    "equivalent",
                    "not specific",
                },
                "invalid defect outcome",
            )
            links(root, defect["evidence"])
    bases = status_doc["bases"]
    require(isinstance(bases, dict) and bool(bases), "bases must be a nonempty mapping")
    for key, value in bases.items():
        string(key)
        require(ID.fullmatch(key), "invalid basis ID")
        check_basis(value)
    entries = status_doc["entries"]
    require(isinstance(entries, list), "entries must be a list")
    by_id, all_ids = {}, set()
    for entry in entries:
        require(isinstance(entry, dict), "entry must be a mapping")
        check_entry(entry, bases, root)
        for key in [entry["id"]] + entry.get("aliases", []):
            require(key not in all_ids, f"duplicate entry ID or alias: {key}")
            all_ids.add(key)
        by_id[entry["id"]] = entry
    qualifications = Counter()
    results = Counter()
    for entry in entries:
        for target in entry["supersedes"]:
            require(target in by_id, "supersedes target missing")
            old = by_id[target]
            require(target != entry["id"], "self supersession")
            require(
                old["status"]["state"] == "superseded",
                "supersedes target must be superseded, never current",
            )
            require(
                old["kind"] == entry["kind"] and old.get("claim") == entry.get("claim"),
                "supersedes target has different kind or claim",
            )
        if entry["kind"] in {"qualification", "result"}:
            require(entry["claim"] in by_claim, "unknown claim reference")
        if entry["kind"] == "qualification":
            claim = by_claim[entry["claim"]]
            if entry["status"]["state"] != "superseded":
                qualifications[entry["claim"]] += 1
            if entry["verdict"] == "qualified":
                require(
                    any(d["outcome"] == "detected" for d in claim["defects"]),
                    "qualified claim lacks detected defect",
                )
            if entry["verdict"] == "shortfall" and claim["mandatory"]:
                require(
                    entry.get("decision", {}).get("who") == "user",
                    "mandatory shortfall requires user decision",
                )
        if entry["kind"] == "result":
            ref = by_id.get(entry["qualification"])
            require(
                ref is not None
                and ref["kind"] == "qualification"
                and ref["claim"] == entry["claim"],
                "invalid result qualification link",
            )
            if entry["qualified_evidence"]:
                require(
                    ref["verdict"] == "qualified",
                    "unqualified result labeled qualified",
                )
            if entry["status"]["state"] == "current":
                results[entry["claim"]] += 1
    for claim in by_claim:
        require(
            qualifications[claim] == 1,
            f"{claim}: expected one nonsuperseded qualification",
        )
        require(results[claim] <= 1, f"{claim}: duplicate current result")
    for entry in entries:
        seen, pending = set(), list(entry["supersedes"])
        while pending:
            target = pending.pop()
            require(target != entry["id"], "supersedes cycle")
            if target not in seen:
                seen.add(target)
                pending.extend(by_id[target]["supersedes"])
    check_history(status_doc, by_id, root)
    return dict(claims=len(claims), **Counter(e["kind"] for e in entries))


def read_yaml(path):
    """Read safe YAML, rejecting duplicate mapping keys rather than losing data."""

    class UniqueLoader(yaml.SafeLoader):
        """The safe loader with duplicate-key rejection."""

    def construct(loader, node, deep=False):
        out = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            require(isinstance(key, str), "mapping keys must be strings")
            require(key not in out, f"duplicate YAML key: {key}")
            out[key] = loader.construct_object(value_node, deep=deep)
        return out

    UniqueLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct
    )
    return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)


def main(argv=None):
    """Run the read-only public index check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path, nargs="?")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--skill", action="store_true")
    args = parser.parse_args(argv)
    if args.skill:
        print(SKILL)
        return 0
    if args.campaign is None:
        parser.error("campaign is required")
    counts, findings, code = {}, [], 0
    if yaml is None:
        findings, code = ["PyYAML is required; use uv run --with pyyaml"], 3
    else:
        try:
            claims = read_yaml(args.campaign / "claims.yaml")
            status = read_yaml(args.campaign / "status.yaml")
            counts = validate(claims, status, args.root.resolve())
        except OSError:
            findings, code = ["Cannot read a required input file"], 3
        except (Invalid, yaml.YAMLError, SyntaxError, UnicodeError) as exc:
            findings, code = [str(exc)], 1
    if args.json:
        print(json.dumps(dict(ok=code == 0, counts=counts, findings=findings)))
    elif findings:
        print("\n".join(findings))
    else:
        print("OK: " + ", ".join(f"{n} {kind}" for kind, n in counts.items()))
    return code


if __name__ == "__main__":
    sys.exit(main())
