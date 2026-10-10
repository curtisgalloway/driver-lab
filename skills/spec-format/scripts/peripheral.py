# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Typed peripheral payload traversal, semantic checks and generated lists.

Only structured fields decide requirements, citations and generated summaries.
Layout offsets and sizes count bytes; register bits are [low, high], inclusive.
"""

import copy


def children(data, base=()):
    payload = data.get("data", {})
    for i, field in enumerate(payload.get("fields", [])):
        yield field, base + ("data", "fields", i)
    for i, field in enumerate(payload.get("layout", {}).get("fields", [])):
        yield field, base + ("data", "layout", "fields", i)
    for group in ("steps", "order"):
        for i, row in enumerate(payload.get("sequence", {}).get(group, [])):
            yield row, base + ("data", "sequence", group, i)


def subrecords(data, base=()):
    """D16: supported register fields and sequence steps have verdict sub-keys."""
    for row, path in children(data, base):
        if "support" in row and path[-2] in ("fields", "steps"):
            # Layout fields do not have D16 sub-keys: only registers and sequences do.
            if path[-2] == "steps" or "register" in data.get("data", {}):
                yield row, path


def basis_data(rec):
    """D16 projection: independent children, effective requirement and parent identity."""
    data = copy.deepcopy(rec.data)
    if getattr(rec, "parent", None) is not None:
        if "requirement" not in data and "requirement" in rec.parent.data:
            data["requirement"] = rec.parent.data["requirement"]
        payload = rec.parent.data["data"]
        if "register" in payload:
            data["parent_identity"] = {k: payload["register"][k] for k in ("name", "offset")}
        elif "sequence" in payload:
            data["parent_identity"] = {"steps": [row["id"] for row in payload["sequence"]["steps"]]}
    else:
        for _, path in subrecords(rec.data):
            owner = data
            for part in path[:-1]:
                owner = owner[part]
            owner[path[-1]] = {"id": owner[path[-1]]["id"]}
    return data


def owns_citation(rec, path):
    """The parent's freshness does not include a separately supported child's citation."""
    return not any(path[:len(at)] == at for _, at in subrecords(rec.data, rec.path))


def requirement(checker, file, row, path, inherited=None, inherited_support=()):
    value = row.get("requirement", inherited)
    support = row.get("support", inherited_support)
    if value == "hw-required" and not any(
            entry["class"] in ("databook", "standard", "doc") for entry in support):
        checker.add(file, path + ("requirement",), "hw-required needs document-class support")
    if value == "comment-explained" and not any(
            entry["class"] in ("src", "DT", "rtl") and anchor.get("comment")
            for entry in support for anchor in entry.get("anchors", [])):
        checker.add(file, path + ("requirement",), "comment-explained needs a comment anchor")


def check_file(checker, file):
    areas = set()
    for i, row in enumerate(file.data.get("areas", [])):
        if row["area"] in areas:
            checker.add(file, ("areas", i, "area"), "area is listed twice")
        areas.add(row["area"])
    for i, fact in enumerate(file.data["facts"]):
        path = ("facts", i)
        requirement(checker, file, fact, path)
        payload = fact.get("data", {})
        register = payload.get("register")
        if register and "reset" in register and "width" in register:
            if int(register["reset"], 16).bit_length() > register["width"]:
                checker.add(file, path + ("data", "register", "reset"), "reset exceeds register width")
        seen = set()
        for row, at in children(fact, path):
            requirement(checker, file, row, at, fact.get("requirement"), fact.get("support", []))
            if "id" in row:
                key = (at[-2], row["id"])
                if key in seen:
                    checker.add(file, at + ("id",), "field or step id is listed twice")
                seen.add(key)
            if "bits" in row:
                low, high = row["bits"]
                if low > high or ("width" in register and high >= register["width"]):
                    checker.add(file, at + ("bits",), "bits must be ordered and inside register width")
            if "offset" in row and "layout" in payload:
                if int(row["offset"], 16) + row["size"] > payload["layout"]["size"]:
                    checker.add(file, at + ("offset",), "field exceeds layout size")
        sequence = payload.get("sequence", {})
        steps = {row["id"] for row in sequence.get("steps", [])}
        edges, constraints = {}, set()
        for j, order in enumerate(sequence.get("order", [])):
            at = path + ("data", "sequence", "order", j)
            before, after = order["before"], order["after"]
            if before not in steps or after not in steps:
                checker.add(file, at, "order names an unknown step")
            if before == after:
                checker.add(file, at, "order cannot name the same step twice")
            if (before, after) in constraints:
                checker.add(file, at, "ordering constraint is listed twice")
            constraints.add((before, after))
            edges.setdefault(before, set()).add(after)
        pending = set(steps)
        while pending:
            ready = {s for s in pending if not (edges.get(s, set()) & pending)}
            if not ready:
                checker.add(file, path + ("data", "sequence", "order"), "ordering constraints form a cycle")
                break
            pending -= ready
        if fact["section"] == "target":
            import speccheck

            for anchor, at in speccheck.anchors(fact, path):
                entry = file.repos.get(anchor["repo"])
                if entry and entry[0].get("role") != "target":
                    checker.add(file, at + ("repo",), "target facts need a repos entry with role: target")


def generated(file):
    """Exact structured projection for generated Markdown sections (no prose parsing)."""
    registers, verify, questions = [], [], []
    for fact in file.data["facts"]:
        fid = fact["id"]
        payload = fact.get("data", {})
        if "register" in payload:
            registers.append(dict(payload["register"], fact=fid, fields=payload.get("fields", [])))
        sequence_steps = payload.get("sequence", {}).get("steps", [])
        if fact.get("requirement") == "as-implemented" and not sequence_steps:
            verify.append({"fact": fid, "text": fact.get("claim", payload.get("register", {}).get("name", fid))})
        elif fact.get("todo", {}).get("check") == "hardware" and not sequence_steps:
            verify.append({"fact": fid, "text": fact.get("claim", fid)})
        for row, at in children(fact):
            if row.get("requirement", fact.get("requirement")) == "as-implemented":
                key = row.get("id", row.get("before", "") + "->" + row.get("after", ""))
                verify.append({"fact": fid + "." + key,
                               "text": row.get("action", row.get("meaning", key))})
        if "todo" in fact:
            questions.append({"fact": fid, **fact["todo"]})
        for row, at in children(fact):
            if "todo" in row:
                key = row.get("id", row.get("before", "") + "->" + row.get("after", ""))
                questions.append({"fact": fid + "." + key, **row["todo"]})
    resources = file.data.get("resources", {})
    references = [{"type": group, **entry} for group in ("documents", "repos")
                  for entry in resources.get(group, [])]
    import speccheck

    classes = sorted({entry["class"] for fact in file.data["facts"]
                      for entry, _ in speccheck.supports(fact, ())})
    return {"registers": registers, "verify": verify, "questions": questions,
            "references": references, "classes": classes}
