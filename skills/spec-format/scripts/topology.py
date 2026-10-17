# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Typed resource contracts and closed-world, owner-directed topology contexts.

This module checks authored facts, never inferred wiring, cell encodings or live state.
Context admission is separate from the atlas's existing spec-relation graph selection.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

PAYLOADS = ("topologyNode", "connection", "topologyConfiguration", "selection")
OWNER_KINDS = ("board", "soc", "chip")


def references(data, base):
    """Distinct field kinds keep endpoints on one node from being duplicate refs."""
    fields = data.get("data", {})
    for field in ("instance", "rate", "voltage"):
        if field in fields.get("topologyNode", {}):
            yield (
                "topology-" + field,
                fields["topologyNode"][field],
                base + ("data", "topologyNode", field),
            )
    for side in ("provider", "consumer"):
        if side in fields.get("connection", {}):
            yield (
                "topology-" + side,
                fields["connection"][side]["node"],
                base + ("data", "connection", side, "node"),
            )
    for field in ("configuration", "selects"):
        if field in fields.get("selection", {}):
            yield (
                "topology-" + field,
                fields["selection"][field],
                base + ("data", "selection", field),
            )


def bases(checker):
    """Only unique real specs confer a kind on overlays; ambiguity grants no kind."""
    by_id = defaultdict(list)
    for file in checker.files:
        if not file.is_overlay:
            by_id[file.spec_id].append(file)
    return {sid: files[0] for sid, files in by_id.items() if len(files) == 1}


def payload(rec, name):
    return rec.data.get("data", {}).get(name)


def target(checker, rec, name, field, expected):
    """Type-check at the factRef path, preserving normal resolution/gate failures."""
    value = payload(rec, name)
    if field not in value:
        return None
    other, _ = checker.resolve(rec.file, value[field])
    if other is None:
        return None  # the ordinary reference pass reports the unresolved reference
    valid = (
        other.path[0] == "instances"
        if expected == "instance"
        else payload(other, expected) is not None
    )
    if not valid:
        checker.reject(
            rec.file,
            rec.path + ("data", name, field),
            f"topology {field} must reference a {expected} record",
        )
        return None
    return other


def endpoint(checker, rec, side):
    value = payload(rec, "connection")[side]
    other, _ = checker.resolve(rec.file, value["node"])
    if other is None:
        return None
    at = rec.path + ("data", "connection", side)
    node = payload(other, "topologyNode")
    if node is None:
        checker.reject(
            rec.file,
            at + ("node",),
            "connection endpoint must reference a topologyNode fact",
        )
        return None
    ports = [p for p in node["ports"] if p["name"] == value["port"]]
    if len(ports) != 1:
        checker.add(rec.file, at + ("port",), "connection port is missing or ambiguous")
        return None
    port = ports[0]
    if port["role"] != side or port["kind"] != payload(rec, "connection")["kind"]:
        checker.add(
            rec.file,
            at + ("port",),
            "connection port role/kind does not match endpoint",
        )
    if side == "provider" and "cells" in port:
        arity = port["cells"]
        if len(value.get("cells", [])) != arity:
            checker.add(
                rec.file,
                at + ("cells",),
                f"provider requires exactly {arity} specifier cells",
            )
    return other


@dataclass
class Context:
    """Deterministic admitted records, plus explicit cross-board rendering boundaries.

    Owners are spec IDs, including overlays of those IDs. No reverse reference from a
    non-admitted owner can enlarge this set. Callers must still apply rendering
    safety gates.
    """

    focus: object
    owners: frozenset
    records: tuple
    boundaries: tuple  # (connection record, endpoint side, excluded node record)

    def of_kind(self, name):
        return tuple(rec for rec in self.records if payload(rec, name) is not None)


def context(checker, focus):
    """Design H: composition seeds, then non-board endpoints of admitted owners.

    The input is a unique real board/soc/chip SpecFile. This helper does not fetch
    specs, evaluate scope prose, or use global incoming edges to discover more owners.
    """
    real = bases(checker)
    owners = set()

    def admit(sid):
        file = real.get(sid)
        if file is None or (file.kind == "board" and file is not focus):
            return False
        if sid in owners:
            return False
        owners.add(sid)
        return True

    pending = [focus.spec_id]
    while pending:
        sid = pending.pop()
        if not admit(sid):
            continue
        pending.extend(real[sid].data.get("parts", []))
    # Include the design's instance and describes seeds, without treating them as
    # topology owners of a forbidden kind. Overlay instance rows belong to their target.
    composed = set(owners)
    for file in checker.files:
        if file.spec_id in composed:
            for row in file.data.get("instances", []):
                for key in ("ip", "peripheral"):
                    if key in row:
                        admit(row[key])
        if file.kind == "peripheral" and composed.intersection(
            file.data.get("describes", [])
        ):
            admit(file.spec_id)

    candidates = sorted(
        (
            r
            for f in checker.files
            for r in f.records.values()
            if any(payload(r, n) is not None for n in PAYLOADS)
            and real.get(f.spec_id) is not None
            and real[f.spec_id].kind in OWNER_KINDS
        ),
        key=lambda r: r.full,
    )
    changed = True
    while changed:
        changed = False
        for rec in candidates:
            conn = payload(rec, "connection")
            if rec.file.spec_id not in owners or conn is None:
                continue
            for side in ("provider", "consumer"):
                node, _ = checker.resolve(rec.file, conn[side]["node"])
                if node is not None and payload(node, "topologyNode") is not None:
                    owner = real.get(node.file.spec_id)
                    if owner is not None and owner.kind in ("soc", "chip"):
                        changed = admit(owner.spec_id) or changed

    records, boundaries = [], []
    for rec in candidates:
        if rec.file.spec_id not in owners:
            continue
        if (
            payload(rec, "topologyConfiguration") is not None
            or payload(rec, "selection") is not None
        ):
            if focus.kind != "board" or rec.file.spec_id != focus.spec_id:
                continue
        conn = payload(rec, "connection")
        excluded = False
        if conn is not None:
            for side in ("provider", "consumer"):
                node, _ = checker.resolve(rec.file, conn[side]["node"])
                if node is not None and node.file.spec_id not in owners:
                    boundaries.append((rec, side, node))
                    excluded = True
        if not excluded:
            records.append(rec)
    return Context(focus, frozenset(owners), tuple(records), tuple(boundaries))


def slot(checker, rec):
    end = payload(rec, "connection")["consumer"]
    node, _ = checker.resolve(rec.file, end["node"])
    return (node.full, end["port"]) if node is not None else None


def check(checker):
    real = bases(checker)
    configs, selections = {}, []
    for file in checker.files:
        owner = real.get(file.spec_id)
        for rec in file.records.values():
            data = rec.data.get("data", {})
            if not any(name in data for name in PAYLOADS):
                continue
            if owner is None or owner.kind not in OWNER_KINDS:
                checker.add(
                    file,
                    rec.path + ("data",),
                    "topology payload requires a real board, soc or chip target",
                )
                continue
            node = payload(rec, "topologyNode")
            if node is not None:
                seen = set()
                for i, port in enumerate(node["ports"]):
                    if port["name"] in seen:
                        checker.add(
                            file,
                            rec.path + ("data", "topologyNode", "ports", i, "name"),
                            "topology node port name is duplicated",
                        )
                    seen.add(port["name"])
                if (
                    "incompleteKinds" in node
                    and rec.data.get("todo", {}).get("check") != "document"
                ):
                    checker.add(
                        file,
                        rec.path + ("data", "topologyNode", "incompleteKinds"),
                        "incompleteKinds requires a document TODO explaining the gap",
                    )
                for field, expected in (
                    ("instance", "instance"),
                    ("rate", "quantity"),
                    ("voltage", "quantity"),
                ):
                    target(checker, rec, "topologyNode", field, expected)
            if "connection" in data:
                endpoint(checker, rec, "provider")
                endpoint(checker, rec, "consumer")
            config = payload(rec, "topologyConfiguration")
            if config is not None:
                board = real.get(config["board"])
                if board is None or board.kind != "board":
                    checker.add(
                        file,
                        rec.path + ("data", "topologyConfiguration", "board"),
                        "topology configuration board must resolve to a real board",
                    )
                elif file.spec_id != board.spec_id:
                    checker.add(
                        file,
                        rec.path + ("data", "topologyConfiguration", "board"),
                        "topology configuration must belong to its configured board",
                    )
                else:
                    configs[rec] = board
            if "selection" in data:
                config_rec = target(
                    checker, rec, "selection", "configuration", "topologyConfiguration"
                )
                conn = target(checker, rec, "selection", "selects", "connection")
                if (
                    conn is not None
                    and payload(conn, "connection")["mode"] != "selectable"
                ):
                    checker.reject(
                        file,
                        rec.path + ("data", "selection", "selects"),
                        "selection must reference a selectable connection, never fixed",
                    )
                selections.append((rec, config_rec, conn))

    contexts = {f: context(checker, f) for f in real.values() if f.kind in OWNER_KINDS}
    for ctx in contexts.values():
        for rec, side, _ in ctx.boundaries:
            checker.reject(
                rec.file,
                rec.path + ("data", "connection", side, "node"),
                f"endpoint is outside topology context {ctx.focus.spec_id!r}; "
                "board-specific topology must belong to that board",
            )
        slots = defaultdict(list)
        for rec in ctx.of_kind("connection"):
            key = slot(checker, rec)
            if key is not None:
                slots[key].append(rec)
        for key, records in slots.items():
            fixed = [r for r in records if payload(r, "connection")["mode"] == "fixed"]
            if len(fixed) > 1 or (fixed and len(records) > 1):
                for rec in records:
                    checker.add(
                        rec.file,
                        rec.path + ("data", "connection", "consumer"),
                        f"consumer slot {key!r} has multiple fixed connections "
                        "or mixes fixed/selectable connections in context "
                        f"{ctx.focus.spec_id!r}",
                    )

    chosen = defaultdict(list)
    for rec, config, conn in selections:
        board = configs.get(config)
        if board is None or rec.file.spec_id != board.spec_id:
            checker.reject(
                rec.file,
                rec.path + ("data", "selection", "configuration"),
                "selection must belong to the configured board",
            )
            continue
        if conn is None:
            continue
        if conn not in contexts[board].of_kind("connection"):
            checker.reject(
                rec.file,
                rec.path + ("data", "selection", "selects"),
                "selected connection is not admitted to the configured board topology",
            )
            continue
        key = (config.full, slot(checker, conn))
        chosen[key].append((rec, conn))
    for choices in chosen.values():
        # Reject every competing claim, including duplicates, regardless of order.
        if len({conn.full for _, conn in choices}) > 1:
            for rec, _ in choices:
                checker.reject(
                    rec.file,
                    rec.path + ("data", "selection", "selects"),
                    "configuration selects different candidates in one consumer slot",
                )
