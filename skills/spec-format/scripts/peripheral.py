# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Typed peripheral payload traversal, semantic checks and generated lists.

Only structured fields decide requirements, citations and generated summaries.
Layout offsets and sizes count bytes; register bits are [low, high], inclusive.
"""

import copy
import re

# The four spec-level registries, and what one entry is called in a message.
REGISTRIES = ("resetTypes", "fieldAccessPolicyDefinitions", "enumerationDefinitions",
              "registerFiles")
ENTRY_LABEL = {"resetTypes": "reset type", "fieldAccessPolicyDefinitions": "access policy",
               "enumerationDefinitions": "enumeration", "registerFiles": "register file"}

# Today's short register access values and their IP-XACT form (D24). The checker warns on a
# short value and builds its message from this table; `drift --rewrite` reuses it.
LEGACY_ACCESS = {
    "ro": {"access": "read-only"},
    "wo": {"access": "write-only"},
    "rw": {"access": "read-write"},
    "w1c": {"access": "read-write", "modifiedWriteValue": "oneToClear"},
    "w1s": {"access": "read-write", "modifiedWriteValue": "oneToSet"},
    "rc": {"access": "read-only", "readAction": "clear"},
}


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


def referenced_registries(rec):
    """([(group, name, entry, path)], why): the registry entries a record's basis covers.

    Taken from basis_data, so a parent leaves out the entries only its separately supported
    fields name, and such a field's sub-record holds only its own. A policy brings the reset
    types it is unaffected by. why is set (and the list empty) when a name is not in the file
    or is declared twice there. Sorted by group and name."""
    f = rec.file
    data = basis_data(rec)
    if getattr(rec, "parent", None) is not None:
        fields, register = [data], {}
    else:
        payload = data.get("data", {})
        fields, register = payload.get("fields", []), payload.get("register", {})
        # Layout facts are not split into sub-records: their fields belong to this record.
        fields = fields + payload.get("layout", {}).get("fields", [])
    wanted, queue = set(), []

    def want(group, name):
        if (group, name) not in wanted:
            wanted.add((group, name))
            queue.append((group, name))

    if "registerFile" in register:
        want("registerFiles", register["registerFile"])
    for field in fields:
        for reset in field.get("resets", []):
            if "resetTypeRef" in reset:
                want("resetTypes", reset["resetTypeRef"])
        for name in field.get("unaffectedBy", []):
            want("resetTypes", name)
        if "enumerationDefinitionRef" in field:
            want("enumerationDefinitions", field["enumerationDefinitionRef"])
        if "fieldAccessPolicyDefinitionRef" in field:
            want("fieldAccessPolicyDefinitions", field["fieldAccessPolicyDefinitionRef"])
    out = []
    while queue:
        group, name = queue.pop()
        if (group, name) in f.ambiguous:
            return [], f"{rec.full}: {ENTRY_LABEL[group]} {name!r} is listed twice in its file"
        if name not in f.registries.get(group, {}):
            return [], f"{rec.full}: {ENTRY_LABEL[group]} {name!r} is not in its file's {group}"
        entry, path = f.registries[group][name]
        out.append((group, name, entry, path))
        if group == "fieldAccessPolicyDefinitions":
            for reset in entry.get("unaffectedBy", []):
                want("resetTypes", reset)
    return sorted(out, key=lambda item: item[:2]), None


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
            if "bits" in row and at[-3] == "data":
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
    check_registers(checker, file)
    check_layouts(checker, file)
    check_sequences(checker, file)


# --- precise payloads: registries, field properties, arrays (docs/SPEC-FORMAT.md) ----------

def _count(dim):
    n = 1
    for d in dim:
        n *= d
    return n


def _width(row):
    """A field's width from its bits, or None when the bits are out of order."""
    low, high = row["bits"]
    return high - low + 1 if low <= high else None


def _fits(value, width):
    return width is None or int(value, 16).bit_length() <= width


def _overlap(a, b):
    """Whether two usages (absent is read-write) can apply to one access."""
    a, b = a.get("usage", "read-write"), b.get("usage", "read-write")
    return {a, b} != {"read", "write"}


def _check_table(checker, file, rows, path, what):
    """Names unique within a table; values unique among entries whose usages overlap."""
    names = {}
    for k, row in enumerate(rows):
        if row["name"] in names:
            checker.add(file, path + (k, "name"),
                        f"{what}: value name {row['name']!r} is listed twice")
        names.setdefault(row["name"], k)
        for earlier in rows[:k]:
            if int(earlier["value"], 16) == int(row["value"], 16) and _overlap(earlier, row):
                checker.add(file, path + (k, "value"),
                            f"{what}: value {row['value']} is listed twice for "
                            f"{earlier['name']!r} and {row['name']!r}")
                break


def _check_constraint(checker, file, constraint, path, what):
    if "minimum" in constraint and int(constraint["minimum"], 16) > int(constraint["maximum"], 16):
        checker.add(file, path + ("minimum",),
                    f"{what}: minimum {constraint['minimum']} is above maximum "
                    f"{constraint['maximum']}")


def check_registries(checker, file, cited):
    """The four registries' entries: their support as a fact's is checked, and each entry's
    own rules (the checks that hold wherever it is used)."""
    for group in REGISTRIES:
        for i, entry in enumerate(file.data.get(group, [])):
            path = (group, i)
            what = f"{ENTRY_LABEL[group]} {entry['name']!r}"
            import speccheck

            for sup, at in speccheck.supports(entry, path):
                if sup["class"] in ("inference", "emulated"):
                    checker.reject(file, at + ("class",),
                                   f"{what}: {sup['class']} support names facts, which a "
                                   f"registry entry cannot; cite the source", citation=True)
            checker.check_support(file, what, entry, path, cited)
            if group == "fieldAccessPolicyDefinitions":
                for k, name in enumerate(entry.get("unaffectedBy", [])):
                    if name not in file.registries["resetTypes"]:
                        checker.add(file, path + ("unaffectedBy", k),
                                    f"{what}: unaffectedBy {name!r} names no resetTypes entry")
                if "writeValueConstraint" in entry:
                    _check_constraint(checker, file, entry["writeValueConstraint"],
                                      path + ("writeValueConstraint",), what)
            elif group == "enumerationDefinitions":
                _check_table(checker, file, entry["enumeratedValues"],
                             path + ("enumeratedValues",), what)
            elif group == "registerFiles" and "array" in entry:
                if int(entry["array"]["stride"], 16) < int(entry["range"], 16):
                    checker.add(file, path + ("array", "stride"),
                                f"{what}: array stride {entry['array']['stride']} is below the "
                                f"range {entry['range']}, so the elements overlap")


def _field_index(file):
    """{(fact id, field id): (field, register)} over the register facts of this file."""
    out = {}
    for fact in file.data.get("facts", []):
        payload = fact.get("data", {})
        if "register" in payload:
            for field in payload.get("fields", []):
                out.setdefault((fact["id"], field["id"]), (field, payload["register"]))
    return out


def _lookup(file, group, name):
    found = file.registries.get(group, {}).get(name)
    return found[0] if found else None


def _field_ref(index, ref):
    fact, _, field = ref[1:].partition(".")
    return index.get((fact, field))


def _check_register(checker, file, register, rpath):
    access = register.get("access")
    if access in LEGACY_ACCESS:
        form = ", ".join(f"{k}: {v}" for k, v in LEGACY_ACCESS[access].items())
        checker.add(file, rpath + ("access",),
                    f"register access {access!r} is a legacy value: write {form} (IP-XACT)",
                    level="warning")
    width = register.get("width")
    array = register.get("array")
    count = _count(array["dim"]) if array else 1
    stride = int(array["stride"], 16) if array else 0
    size = (width + 7) // 8 if width else None
    if array and size is not None and stride < size:
        checker.add(file, rpath + ("array", "stride"),
                    f"register array stride {array['stride']} is below the register's "
                    f"{size} bytes, so the elements overlap")
    name = register.get("registerFile")
    if name is None:
        return
    group = _lookup(file, "registerFiles", name)
    if group is None:
        checker.add(file, rpath + ("registerFile",),
                    f"registerFile {name!r} names no registerFiles entry")
    elif size is not None:
        end = int(register["offset"], 16) + (count - 1) * stride + size
        if end > int(group["range"], 16):
            checker.add(file, rpath + ("offset",),
                        f"register ends at byte {hex(end)} of register file {name!r}, whose "
                        f"range is {group['range']}")


def _check_enumeration(checker, file, field, width, fpath, what):
    """Enumerated values: the field's own table, or the shared one it names.

    Returns (own table or None, shared name or None)."""
    table = field.get("enumeratedValues")
    if table is not None:
        for k, row in enumerate(table):
            if not _fits(row["value"], width):
                checker.add(file, fpath + ("enumeratedValues", k, "value"),
                            f"enumerated value {row['value']} ({row['name']}) does not fit the "
                            f"{width}-bit field")
        _check_table(checker, file, table, fpath + ("enumeratedValues",), what)
    name = field.get("enumerationDefinitionRef")
    if name is not None:
        definition = _lookup(file, "enumerationDefinitions", name)
        if definition is None:
            checker.add(file, fpath + ("enumerationDefinitionRef",),
                        f"enumerationDefinitionRef {name!r} names no enumerationDefinitions "
                        f"entry")
        else:
            for row in definition["enumeratedValues"]:
                if not _fits(row["value"], width):
                    checker.add(file, fpath + ("enumerationDefinitionRef",),
                                f"enumeration {name!r} value {row['value']} ({row['name']}) "
                                f"does not fit the {width}-bit field")
    return table, name


def _check_field(checker, file, fact, register, field, fpath, index):
    width = _width(field)
    policy = None
    ref = field.get("fieldAccessPolicyDefinitionRef")
    if ref is not None:
        policy = _lookup(file, "fieldAccessPolicyDefinitions", ref)
        if policy is None:
            checker.add(file, fpath + ("fieldAccessPolicyDefinitionRef",),
                        f"fieldAccessPolicyDefinitionRef {ref!r} names no "
                        f"fieldAccessPolicyDefinitions entry")
    table, name = _check_enumeration(checker, file, field, width, fpath,
                                     f"field {field['id']!r}")
    # The write constraint, the field's own or its policy's.
    if "writeValueConstraint" in field:
        constraint, cpath = field["writeValueConstraint"], fpath + ("writeValueConstraint",)
        _check_constraint(checker, file, constraint, cpath, f"field {field['id']!r}")
    elif policy is not None and "writeValueConstraint" in policy:
        constraint, cpath = (policy["writeValueConstraint"],
                             fpath + ("fieldAccessPolicyDefinitionRef",))
    else:
        constraint, cpath = None, None
    if constraint is not None:
        for key in ("minimum", "maximum"):
            if key in constraint and not _fits(constraint[key], width):
                checker.add(file, cpath if policy and "writeValueConstraint" not in field
                            else cpath + (key,),
                            f"{key} {constraint[key]} does not fit the {width}-bit field")
        if constraint.get("useEnumeratedValues") and table is None and name is None:
            checker.add(file, cpath, f"field {field['id']!r}: useEnumeratedValues needs "
                                     f"enumeratedValues or an enumerationDefinitionRef")
    # Resets and the reset types that leave the field alone.
    resets = file.registries["resetTypes"]
    unaffected = field.get("unaffectedBy", policy.get("unaffectedBy", []) if policy else [])
    seen = set()
    for k, reset in enumerate(field.get("resets", [])):
        rpath = fpath + ("resets", k)
        kind = reset.get("resetTypeRef")
        if kind is not None and kind not in resets:
            checker.add(file, rpath + ("resetTypeRef",),
                        f"resetTypeRef {kind!r} names no resetTypes entry")
        if kind in seen:
            checker.add(file, rpath, f"field {field['id']!r}: "
                        + (f"reset type {kind!r}" if kind else "the default reset type")
                        + " has two resets entries")
        seen.add(kind)
        if kind in unaffected:
            checker.add(file, rpath + ("resetTypeRef",),
                        f"reset type {kind!r} is in both resets and unaffectedBy of field "
                        f"{field['id']!r}")
        for key in ("value", "mask"):
            if key in reset and not _fits(reset[key], width):
                checker.add(file, rpath + (key,),
                            f"reset {key} {reset[key]} does not fit the {width}-bit field")
    for k, kind in enumerate(field.get("unaffectedBy", [])):
        if kind not in resets:
            checker.add(file, fpath + ("unaffectedBy", k),
                        f"unaffectedBy {kind!r} names no resetTypes entry")
    # A field repeated inside the register.
    array = field.get("array")
    if array and width is not None:
        stride = array.get("bitStride", width)
        if stride < width:
            checker.add(file, fpath + ("array", "bitStride"),
                        f"bitStride {stride} is below the {width}-bit field, so the elements "
                        f"overlap")
        last = field["bits"][1] + (_count(array["dim"]) - 1) * stride
        if "width" in register and last >= register["width"]:
            checker.add(file, fpath + ("array",),
                        f"the last element ends at bit {last}, outside the "
                        f"{register['width']}-bit register")
    # Other fields.
    own = f"#{fact['id']}.{field['id']}"
    alias = field.get("aliasOf")
    if alias is not None:
        if alias == own:
            checker.add(file, fpath + ("aliasOf",), f"field {field['id']!r} is an alias of itself")
        elif _field_ref(index, alias) is None:
            checker.add(file, fpath + ("aliasOf",), f"aliasOf {alias!r} names no field of "
                                                    f"this file")
    lock = field.get("lockedBy")
    if lock is not None:
        target = _field_ref(index, lock["field"])
        if target is None:
            checker.add(file, fpath + ("lockedBy", "field"),
                        f"lockedBy field {lock['field']!r} names no field of this file")
        elif not _fits(lock["lockedValue"], _width(target[0])):
            checker.add(file, fpath + ("lockedBy", "lockedValue"),
                        f"lockedValue {lock['lockedValue']} does not fit the "
                        f"{_width(target[0])}-bit field {lock['field']!r}")


def check_registers(checker, file):
    """Register-level and field-level checks of the precise-payload properties."""
    index = _field_index(file)
    for i, fact in enumerate(file.data.get("facts", [])):
        payload = fact.get("data", {})
        register = payload.get("register")
        if not register:
            continue
        path = ("facts", i, "data")
        _check_register(checker, file, register, path + ("register",))
        for j, field in enumerate(payload.get("fields", [])):
            _check_field(checker, file, fact, register, field, path + ("fields", j), index)


def generated(file):
    """Exact structured projection for both reading views (no prose parsing)."""
    registers, verify, questions = [], [], []
    findings, pairs, coverage, field_list, layouts = [], [], [], [], []
    for fact in file.data["facts"]:
        fid = fact["id"]
        payload = fact.get("data", {})
        if "finding" in payload:
            findings.append(dict(payload["finding"], fact=fid))
            if payload["finding"]["assessment"] == "suspect":
                verify.append({"fact": fid, "text": payload["finding"]["consequence"]})
        if "pair" in payload:
            pairs.append(dict(payload["pair"], fact=fid))
        if "coverage" in payload:
            coverage.append(dict(payload["coverage"], fact=fid))
        if "layout" in payload:
            layouts.append(dict(payload["layout"], fact=fid))
        if "register" in payload:
            registers.append(dict(payload["register"], fact=fid, fields=payload.get("fields", [])))
            field_list.extend(dict(field, fact=fid) for field in payload.get("fields", []))
        sequence_steps = payload.get("sequence", {}).get("steps", [])
        suspect = payload.get("finding", {}).get("assessment") == "suspect"
        if fact.get("requirement") == "as-implemented" and not sequence_steps and not suspect:
            verify.append({"fact": fid, "text": fact.get("claim", payload.get("register", {}).get("name", fid))})
        elif fact.get("todo", {}).get("check") == "hardware" and not sequence_steps and not suspect:
            verify.append({"fact": fid, "text": fact.get("claim", fid)})
        for row, at in children(fact):
            if row.get("requirement", fact.get("requirement")) == "as-implemented":
                key = row.get("id", row.get("before", "") + "->" + row.get("after", ""))
                text = (step_text(row) if at[-2] == "steps"
                        else row.get("action", row.get("meaning", key)))
                verify.append({"fact": fid + "." + key, "text": text})
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
    definitions = {name: file.data[name] for name in REGISTRIES if name in file.data}
    return {"registers": registers, "verify": verify, "questions": questions,
            "references": references, "classes": classes,
            "findings": findings, "pairs": pairs, "coverage": coverage,
            "fields": field_list, "layouts": layouts, "definitions": definitions}


def register_rows(summary):
    """Both views use the same ordered register columns and field values."""
    rows = []
    for register in summary["registers"]:
        row = {key: register.get(key, "")
               for key in ("fact", "offset", "name", "width", "access", "reset")}
        row["fields"] = [{k: field[k] for k in ("id", "name", "bits", "meaning")}
                         for field in register["fields"]]
        row.update({key: register[key] for key in
                    ("registerFile", "array", "modifiedWriteValue", "readAction")
                    if key in register})
        rows.append(row)
    return rows


def _enumerated(values):
    """`0x0 off; 0x1 x1`; a value whose usage is not read-write names it."""
    return "; ".join(
        f"{v['value']} {v['name']}" + (f" ({v['usage']})" if v.get("usage", "read-write")
                                         != "read-write" else "")
        for v in values)


def _constraint(constraint):
    if constraint.get("writeAsRead"):
        return "writeAsRead"
    if constraint.get("useEnumeratedValues"):
        return "useEnumeratedValues"
    return f"{constraint['minimum']}..{constraint['maximum']}"


FIELD_COLUMNS = ("field", "name", "bits", "access", "modifiedWriteValue", "readAction",
                 "policy", "resets", "unaffectedBy", "values", "writeValueConstraint",
                 "reserved", "volatile", "initializedBy", "lockedBy", "aliasOf", "array")


def field_rows(summary):
    """One row per register field with only what the field itself states.

    Policies are not resolved and register-level values are not inherited: the definition
    of a policy is shown with the other registries. Every row carries every column that any
    row uses, in FIELD_COLUMNS order, with "" where the field lacks it.
    """
    rows = []
    for field in summary["fields"]:
        row = {"field": field["fact"] + "." + field["id"], "name": field["name"],
               "bits": field["bits"]}
        for key in ("access", "modifiedWriteValue", "readAction"):
            if key in field:
                row[key] = field[key]
        if "fieldAccessPolicyDefinitionRef" in field:
            row["policy"] = field["fieldAccessPolicyDefinitionRef"]
        if "resets" in field:
            row["resets"] = "; ".join(
                r["value"] + (f" ({r['resetTypeRef']})" if "resetTypeRef" in r else "")
                + (f" mask {r['mask']}" if "mask" in r else "") for r in field["resets"])
        if "unaffectedBy" in field:
            row["unaffectedBy"] = ", ".join(field["unaffectedBy"])
        if "enumeratedValues" in field:
            row["values"] = _enumerated(field["enumeratedValues"])
        elif "enumerationDefinitionRef" in field:
            row["values"] = "see " + field["enumerationDefinitionRef"]
        if "writeValueConstraint" in field:
            row["writeValueConstraint"] = _constraint(field["writeValueConstraint"])
        for key in ("reserved", "volatile"):
            if key in field:
                row[key] = "true" if field[key] else "false"
        if "initializedBy" in field:
            row["initializedBy"] = field["initializedBy"]
        if "lockedBy" in field:
            row["lockedBy"] = f"{field['lockedBy']['field']} = {field['lockedBy']['lockedValue']}"
        if "aliasOf" in field:
            row["aliasOf"] = field["aliasOf"]
        if "array" in field:
            array = field["array"]
            row["array"] = "dim " + "x".join(map(str, array["dim"])) + (
                f", bitStride {array['bitStride']}" if "bitStride" in array else "")
        rows.append(row)
    used = [key for key in FIELD_COLUMNS if any(key in row for row in rows)]
    return [{key: row.get(key, "") for key in used} for row in rows]


LAYOUT_COLUMNS = ("field", "layout", "offset", "size", "bits", "byteOrder", "bitNumbering",
                  "values")


def layout_field_rows(summary):
    """One row per layout field, with its layout's byte order and bit numbering.

    Only the columns some row uses, in LAYOUT_COLUMNS order, "" where a row lacks one."""
    rows = []
    for layout in summary["layouts"]:
        for field in layout["fields"]:
            row = {"field": layout["fact"] + "." + field["id"], "layout": layout["name"],
                   "offset": field["offset"], "size": field["size"]}
            if "bits" in field:
                row["bits"] = field["bits"]
            for key in ("byteOrder", "bitNumbering"):
                if key in layout:
                    row[key] = layout[key]
            if "enumeratedValues" in field:
                row["values"] = _enumerated(field["enumeratedValues"])
            elif "enumerationDefinitionRef" in field:
                row["values"] = "see " + field["enumerationDefinitionRef"]
            rows.append(row)
    used = [key for key in LAYOUT_COLUMNS if any(key in row for row in rows)]
    return [{key: row.get(key, "") for key in used} for row in rows]


def check_layouts(checker, file):
    """Bit-packed layout fields: bits inside the container, byte order, values, overlap."""
    for i, fact in enumerate(file.data.get("facts", [])):
        layout = fact.get("data", {}).get("layout")
        if not layout:
            continue
        base = ("facts", i, "data", "layout", "fields")
        placed = []
        for j, field in enumerate(layout["fields"]):
            fpath = base + (j,)
            size = field["size"]
            if "bits" in field:
                low, high = field["bits"]
                if low > high or high >= size * 8:
                    checker.add(file, fpath + ("bits",),
                                f"bits [{low}, {high}] must be ordered and inside the field's "
                                f"{size} byte{'s' if size != 1 else ''} ({size * 8} bits)")
                if "byteOrder" not in layout and size > 1:
                    checker.add(file, fpath + ("bits",),
                                f"layout {layout['name']!r} has no byteOrder, but field "
                                f"{field['id']!r} has bits in a {size}-byte container; say "
                                f"bigEndian or littleEndian")
                width = _width(field)
            else:
                width = size * 8
            _check_enumeration(checker, file, field, width, fpath,
                               f"layout field {field['id']!r}")
            if "bits" in field and low <= high:
                for other in placed:
                    olow, ohigh = other["bits"]
                    if ((int(other["offset"], 16), other["size"])
                            == (int(field["offset"], 16), size)
                            and low <= ohigh and olow <= high):
                        checker.add(file, fpath + ("bits",),
                                    f"field {field['id']!r} bits [{low}, {high}] overlap field "
                                    f"{other['id']!r} in the same container; fine for a union, "
                                    f"otherwise a mistake", level="warning")
                        break
                placed.append(field)


# --- precise payloads: quantities and an operation per step (docs/SPEC-FORMAT.md) -----------

LEVELS = ("min", "nom", "typ", "max")
LEVEL_PAIRS = (("min", "nom"), ("nom", "max"), ("min", "max"), ("min", "typ"), ("typ", "max"))
CANONICAL_HEX = re.compile(r"^0x(0|[1-9a-f][0-9a-f]*)$")


def quantity_text(quantity):
    """`min 60 s, nom 60 s, max 90 s`: the levels present, in the order min, nom, typ, max."""
    return ", ".join(f"{level} {quantity[level]} {quantity['unit']}"
                     for level in LEVELS if level in quantity)


def _timeout_text(step):
    out = f"; timeout {quantity_text(step['timeout'])}" if "timeout" in step else ""
    if "onTimeout" in step:
        out += ("; on timeout, fail" if step["onTimeout"] == "fail"
                else f"; on timeout, go to step {step['onTimeout']}")
    return out


def step_text(step):
    """The English of a step: an action step's own text, else written from its operation."""
    if "op" not in step:
        return step["action"]
    op, target = step["op"], step.get("target", "")
    on_field = "." in target
    if op == "write":
        return f"Write {step['value']} to {target}."
    if op in ("setBits", "clearBits"):
        verb = "Set" if op == "setBits" else "Clear"
        return f"{verb} {target}." if on_field else f"{verb} bits {step['mask']} of {target}."
    if op == "read":
        return f"Read {target}."
    if op == "poll":
        until = step["until"]
        if "equals" in until:
            cond = f"it equals {until['equals']}"
        elif "bitsSet" in until:
            cond = f"bits {until['bitsSet']} are set"
        else:
            cond = f"bits {until['bitsClear']} are clear"
        every = f", every {quantity_text(step['interval'])}" if "interval" in step else ""
        return f"Poll {target} until {cond}{every}{_timeout_text(step)}."
    if op == "delay":
        return f"Wait {quantity_text(step['duration'])}."
    return f"Wait for interrupt {target}{_timeout_text(step)}."


def _check_quantity(checker, file, quantity, path):
    """Levels in order: min <= nom <= max, and typ inside [min, max]."""
    for low, high in LEVEL_PAIRS:
        if low in quantity and high in quantity and quantity[low] > quantity[high]:
            checker.add(file, path, f"{low} {quantity[low]} is above {high} {quantity[high]}")


def _check_step_value(checker, file, step, spath, key, value, target, field, register, entries):
    """One value or equals: canonical hex that fits, or an enumerated value's name."""
    where = spath + ((key,) if key == "value" else ("until", "equals"))
    if value.startswith("0x"):
        if not CANONICAL_HEX.match(value):
            checker.add(file, where, f"value {value!r} is not canonical hex (D6)")
        elif field is not None:
            if not _fits(value, _width(field)):
                checker.add(file, where, f"value {value} does not fit the {_width(field)}-bit "
                                         f"field {target!r}")
        elif "width" in register and not _fits(value, register["width"]):
            checker.add(file, where, f"value {value} does not fit the {register['width']}-bit "
                                     f"register {target!r}")
        return
    entry = next((e for e in entries if e["name"] == value), None)
    if entry is None:
        checker.add(file, where, f"value {value!r} is not an enumerated value of {target!r}")
        return
    usage = entry.get("usage", "read-write")
    if step["op"] == "write" and usage == "read":
        checker.add(file, where, f"{value!r} is a read meaning of {target!r}; a write needs a "
                                 f"write or read-write value")
    if step["op"] == "poll" and usage == "write":
        checker.add(file, where, f"{value!r} is a write meaning of {target!r}; a poll "
                                 f"compares a read value")


def _check_step_mask(checker, file, where, mask, target, field, register):
    if field is not None:
        width, label = _width(field), "field"
    else:
        width, label = register.get("width"), "register"
    if not _fits(mask, width):
        checker.add(file, where, f"mask {mask} does not fit the {width}-bit {label} {target!r}")


def check_sequences(checker, file):
    """Quantities, and the steps with an op: targets, values, masks and onTimeout."""
    facts = {f["id"]: f for f in file.data.get("facts", [])}
    index = _field_index(file)
    for i, fact in enumerate(file.data.get("facts", [])):
        payload = fact.get("data", {})
        if "quantity" in payload:
            _check_quantity(checker, file, payload["quantity"],
                            ("facts", i, "data", "quantity"))
        steps = payload.get("sequence", {}).get("steps", [])
        ids = {step["id"] for step in steps}
        for j, step in enumerate(steps):
            spath = ("facts", i, "data", "sequence", "steps", j)
            for key in ("timeout", "interval", "duration"):
                if key in step:
                    _check_quantity(checker, file, step[key], spath + (key,))
            if "op" not in step:
                continue
            _check_step(checker, file, step, spath, facts, index, ids)


def _check_step(checker, file, step, spath, facts, index, ids):
    op, target = step["op"], step.get("target")
    field = register = None
    if target is not None:
        fid, _, name = target[1:].partition(".")
        owner = facts.get(fid)
        if op == "waitInterrupt":
            if name or owner is None or owner.get("section") != "interrupts":
                checker.add(file, spath + ("target",),
                            f"waitInterrupt target {target!r} names no interrupts fact of "
                            f"this file")
                return
        elif owner is None or "register" not in owner.get("data", {}):
            checker.add(file, spath + ("target",),
                        f"target {target!r} names no register fact of this file")
            return
        else:
            register = owner["data"]["register"]
            if name:
                found = index.get((fid, name))
                if found is None:
                    checker.add(file, spath + ("target",),
                                f"target {target!r} names no field of register fact {fid!r}")
                    return
                field = found[0]
    if field is not None:
        entries = list(field.get("enumeratedValues", []))
        ref = field.get("enumerationDefinitionRef")
        if ref is not None:
            definition = _lookup(file, "enumerationDefinitions", ref)
            entries += definition["enumeratedValues"] if definition else []
    else:
        entries = []
    if "value" in step:
        _check_step_value(checker, file, step, spath, "value", step["value"], target, field,
                          register, entries)
    until = step.get("until", {})
    if "equals" in until:
        _check_step_value(checker, file, step, spath, "equals", until["equals"], target, field,
                          register, entries)
    if op != "waitInterrupt":
        for where, mask in ((spath + ("mask",), step.get("mask")),
                            (spath + ("until", "bitsSet"), until.get("bitsSet")),
                            (spath + ("until", "bitsClear"), until.get("bitsClear"))):
            if mask is not None:
                _check_step_mask(checker, file, where, mask, target, field, register)
        if op in ("setBits", "clearBits"):
            if field is None and "mask" not in step:
                checker.add(file, spath, f"{op} on register {target!r} needs a mask, or name "
                                         f"a field")
            elif field is not None and "mask" in step:
                checker.add(file, spath + ("mask",),
                            f"mask is for a register target; {target!r} is a field")
    action = step.get("onTimeout")
    if action is not None and action != "fail" and action not in ids:
        checker.add(file, spath + ("onTimeout",),
                    f"onTimeout {action!r} names no step of this sequence")
