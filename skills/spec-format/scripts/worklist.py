# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""`spec.py todo`: the TODOs of the checked roots as a worklist (issue 112).

A read-only view over what the check already loaded. It reads each spec file's own data, never
a verdict, so it changes no verdict rule: a TODO stays open until a verifier settles it.

Kinds: for a fact, `gap` (no support, so a todo is required) or `supported-with-todo`; for
the other places the schema allows a `todo`, the name of the place: `instance` and `variant`
(rows, which have no gap notion), `assumption`, and the rows of a typed payload that are not
records of their own unless supported: `field` (register), `layout-field`, `step` and `order`.
"""

from __future__ import annotations

import speccheck

CHECKS = ("hardware", "document", "source")
KINDS = ("gap", "supported-with-todo", "instance", "variant", "assumption", "field",
         "layout-field", "step", "order")
_ROW_KINDS = {"fields": "field", "steps": "step", "order": "order"}


def _row_kind(path: tuple) -> str:
    """The kind of a payload row: a `fields` list holds register fields, or layout fields
    under `layout`."""
    if path[-2] == "fields" and path[-3] == "layout":
        return "layout-field"
    return _ROW_KINDS[path[-2]]


def _item(f, ref: str, kind: str, todo: dict, *, critical=False, scope=None, instance=None):
    item = {
        "fact": ref,
        "file": str(f.path),
        "root": f.root.label,
        "spec": f.spec_id,
        "kind": kind,
        "check": todo["check"],
        "text": todo["text"],
        "method": todo.get("method"),
        "critical": critical,
        "scope": scope,
        "instance": instance,
    }
    if todo["check"] == "hardware" and not todo.get("method"):
        item["missing_method"] = True
    return item


def collect(checker) -> list[dict]:
    """Every TODO of the checked (non-context) roots, in file order, then document order."""
    import peripheral

    items = []
    for f in checker.files:
        if f.root.context:
            continue
        for rec in f.records.values():
            if rec.parent is not None:
                continue  # a supported payload row: reached through its parent's children
            data, critical = rec.data, rec.data.get("critical") is True
            top = rec.path[0]
            if top == "facts":
                kind = "supported-with-todo" if speccheck.has_support(data) else "gap"
            else:
                kind = {"instances": "instance", "variants": "variant"}[top]
            if "todo" in data:
                items.append(_item(f, rec.full, kind, data["todo"], critical=critical,
                                   scope=data.get("scope"),
                                   instance=data["name"] if top == "instances" else None))
            for row, path in peripheral.children(data):
                if "todo" not in row:
                    continue
                row_id = row["id"] if "id" in row else f"{path[-2]}[{path[-1]}]"
                items.append(_item(f, f"{rec.full}.{row_id}", _row_kind(path),
                                   row["todo"], critical=critical))
        for entry in f.data.get("assumptions", []):
            if "todo" in entry:
                items.append(_item(f, f"{f.spec_id}@{f.root.label}#{entry['id']}",
                                   "assumption", entry["todo"]))
    return items


def counts(items: list[dict]) -> dict:
    return {
        "total": len(items),
        "by_check": {c: sum(1 for i in items if i["check"] == c) for c in CHECKS},
        "by_kind": {k: sum(1 for i in items if i["kind"] == k) for k in KINDS},
        "critical": sum(1 for i in items if i["critical"]),
        "missing_method": sum(1 for i in items if i.get("missing_method")),
    }


def _scope(scope: dict) -> str:
    return "; ".join(f"{k}={', '.join(v)}" for k, v in scope.items())


def lines(items: list[dict], heading) -> list[str]:
    """Human output: grouped by spec file, then by instance where present.

    heading(item) gives the heading line of an item's spec file (built by the caller, so the
    displayed path stays the one `status` shows)."""
    out, by_file = [], {}
    for item in items:
        by_file.setdefault(item["file"], []).append(item)
    for group in by_file.values():
        out.append(f"{heading(group[0])}: {len(group)} TODO(s)")
        instances = {}
        for item in group:
            if item["instance"] is None:
                out += _show(item, "  ")
            else:
                instances.setdefault(item["instance"], []).append(item)
        for name, rows in instances.items():
            out.append(f"  instance {name}:")
            for item in rows:
                out += _show(item, "    ")
    return out


def _show(item: dict, indent: str) -> list[str]:
    notes = []
    if item["critical"]:
        notes.append("critical")
    if item["scope"]:
        notes.append("scope: " + _scope(item["scope"]))
    if item.get("missing_method"):
        notes.append("(no method)")
    head = f"{indent}{item['check']:<8} {item['kind']:<19} {item['fact']}"
    if notes:
        head += "  " + "; ".join(notes)
    out = [head, f"{indent}    {' '.join(item['text'].split())}"]
    if item["method"]:
        out.append(f"{indent}    method: {' '.join(item['method'].split())}")
    return out
