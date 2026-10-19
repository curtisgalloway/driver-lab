# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""The corpus ledger (#153): `corpus.yaml` beside a root's `board-specs.yaml`.

The ledger lists every document and hardware block discovery found, each with a disposition:
`spec:<id>` (or `spec:<id>#<fact>` for a block a spec covers as one record), `planned:<note>`
or `excluded:<reason>`. Leaving a block out is then a recorded decision, not an oversight.

The schema makes a disposition required. `spec.py check` adds, for each root with a ledger:
a `spec:` disposition resolves to a spec (and fact; overlays included) in this root's layer
or an earlier one, and a document's spec lists that document; every document a spec of the
root lists in `resources.documents` is in the ledger, with the same `sha256` when both give
one; no name twice in a group; no `access: private` entry under a `public` layer; no
unsubstituted template placeholder. These are errors, but all except the `sha256` mismatch
leave the root trusted: the ledger records scope, not facts, so a reference into the root does
not fail over it. A `sha256` mismatch says a spec may cite other bytes, so it does.
`spec.py corpus` also fails a checked root that has no ledger, and prints its coverage.
"""

from __future__ import annotations

import re

GROUPS = ("documents", "blocks")
STATES = ("spec", "planned", "excluded", "unresolved")
SPEC = re.compile(r"spec:([a-z0-9][a-z0-9-]*)(?:#([a-z0-9][a-z0-9-]*))?")


def state(disposition: str) -> str:
    """spec, planned or excluded: the part before the first colon."""
    return disposition.partition(":")[0]


def check(checker):
    for root in checker.roots:
        if root.corpus is not None:
            _check_root(checker, root)


def _check_root(checker, root):
    import specmd

    loaded = root.corpus
    where = (root.corpus_path, root, loaded)
    data = loaded.data

    def add(at, path, message):
        checker.add(at, path, message, trust=False)

    ledger = {}
    for group in GROUPS:
        seen = ledger.setdefault(group, {})
        for i, entry in enumerate(data[group]):
            name = entry["name"]
            if name in seen:
                add(where, (group, i, "name"),
                    f"{group} entry {name!r} is listed twice in the corpus ledger")
                continue
            seen[name] = entry
            why = _disposition(checker, root, group, entry)
            if why and state(entry["disposition"]) == "spec":
                root.corpus_unresolved.add((group, name))
            if why:
                add(where, (group, i, "disposition"),
                    f"disposition {entry['disposition']!r}: {why}")
            if root.layer == "public" and entry.get("access") == "private":
                add(where, (group, i, "access"),
                    f"{group} entry {name!r}: access: private under a public root")
    _check_placeholders(add, where, data, (), specmd)
    for f in root.files:
        for name, (entry, path) in sorted(f.documents.items()):
            listed = ledger["documents"].get(name)
            if listed is None:
                add(f, path + ("name",), f"documents entry {name!r} is not in the root's corpus "
                                         f"ledger ({root.corpus_path.name}): add it with a "
                                         f"disposition")
                continue
            if "access" in entry and entry["access"] != listed["access"]:
                add(f, path + ("access",), f"documents entry {name!r}: access "
                                           f"{entry['access']} differs from the corpus "
                                           f"ledger's {listed['access']}")
            if "sha256" in entry and "sha256" in listed and entry["sha256"] != listed["sha256"]:
                # the one ledger finding about facts: the spec may cite other bytes than the
                # ledger recorded, so this error makes the root untrusted (user decision)
                checker.add(f, path + ("sha256",), f"documents entry {name!r}: sha256 differs "
                                                   f"from the corpus ledger's; one of them "
                                                   f"names other bytes")


def _disposition(checker, root, group, entry) -> str | None:
    """Why a `spec:` disposition does not hold, or None. The spec is read in this root or an
    earlier layer (a ledger may not point at a layer that merges after it), overlays
    included; a document's spec must list that document."""
    m = SPEC.fullmatch(entry["disposition"])
    if m is None:
        return None  # planned or excluded; the schema checked the form
    spec_id, fact_id = m.groups()
    files = [f for f in checker.files if f.spec_id == spec_id]
    if not files:
        return f"no spec {spec_id!r} among the roots read"
    files = [f for f in files if f.root.rank <= root.rank]
    if not files:
        return (f"spec {spec_id!r} is only in a layer that merges after this root's "
                f"({root.layer})")
    if fact_id is not None and not any(fact_id in f.records for f in files):
        return f"spec {spec_id!r} has no fact {fact_id!r}"
    if group == "documents" and not any(entry["name"] in f.documents for f in files):
        return f"spec {spec_id!r} does not list document {entry['name']!r} in resources.documents"
    return None


def _check_placeholders(add, where, node, path, specmd):
    if isinstance(node, dict):
        for k, v in node.items():
            _check_placeholders(add, where, v, path + (k,), specmd)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _check_placeholders(add, where, v, path + (i,), specmd)
    elif isinstance(node, str) and "<" in node:
        found = specmd.placeholders(node)
        if found:
            add(where, path, f"unsubstituted template placeholder {found[0][2]!r}")


def coverage(root) -> dict | None:
    """Per group, the rows and their counts by state; None when the root has no valid ledger."""
    if root.corpus is None:
        return None
    out = {}
    for group in GROUPS:
        rows = [{"name": e["name"], "title": e.get("title", ""),
                 "subsystem": e.get("subsystem", ""),
                 # a spec: disposition the check could not resolve is not specified
                 "state": ("unresolved" if (group, e["name"]) in root.corpus_unresolved
                           else state(e["disposition"])),
                 "disposition": e["disposition"]}
                for e in root.corpus.data[group]]
        counts = {s: sum(1 for r in rows if r["state"] == s) for s in STATES}
        out[group] = {"rows": rows, "counts": counts}
    return out


def summary(cov: dict) -> str:
    """One line: `documents 3 spec, 1 planned, 2 excluded; blocks ...`."""
    return "; ".join(f"{group} " + ", ".join(f"{cov[group]['counts'][s]} {s}" for s in STATES
                                          if s != "unresolved" or cov[group]["counts"][s])
                     for group in GROUPS)
