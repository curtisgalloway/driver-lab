# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Review judgments and side roles are structured fields, never inferred from prose.

D16 adds no review sub-keys: finding, pair and coverage payloads belong to their fact.
Their nested citations participate in the normal citation, license and freshness checks.
"""

import speccheck


def check_file(checker, file):
    for i, fact in enumerate(file.data["facts"]):
        payload = fact.get("data", {})
        at = ("facts", i, "data")
        finding = payload.get("finding")
        if finding:
            if finding["assessment"] == "bug" and not (
                    finding.get("settled_by") or finding.get("self_evident")):
                checker.add(file, at + ("finding", "assessment"),
                            "bug needs settled_by with document support or self_evident with reason")
            sides = {side: [] for side in ("impl", "ref")}
            for anchor, path in speccheck.anchors(fact, ("facts", i)):
                entry = file.repos.get(anchor["repo"])
                role = entry[0].get("role") if entry else None
                if role in sides:
                    sides[role].append(anchor)
            if not all(sides.values()):
                checker.add(file, at + ("finding",), "finding needs both impl and ref side anchors")
            if finding["category"] == "missing" and not any(
                    "search" in anchor for anchor in sides["impl"]):
                checker.add(file, at + ("finding", "category"),
                            "missing finding needs an impl search anchor")
        for side, anchors in payload.get("pair", {}).items():
            for j, anchor in enumerate(anchors):
                entry = file.repos.get(anchor["repo"])
                if entry and entry[0].get("role") != side:
                    checker.add(file, at + ("pair", side, j, "repo"),
                                "pair " + side + " needs a repos entry with role: " + side)
