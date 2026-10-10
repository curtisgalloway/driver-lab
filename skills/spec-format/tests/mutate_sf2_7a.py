# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Mutate SF2-7a guards in separate temporary trees; require assertion failures.

Run with the hash-pinned interpreter. Logs and results.json stay in TMPDIR; the exported
tree is never changed. A mutation causing unittest errors or an internal CLI error fails
qualification. Three independent subprocesses bound the total run time.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

CODE = [
    ("hardware-document", "peripheral", 'if value == "hw-required" and not any(', 'if False and not any('),
    ("comment-anchor", "peripheral", 'if value == "comment-explained" and not any(', 'if False and not any('),
    ("inherited-requirement", "peripheral", 'value = row.get("requirement", inherited)', 'value = row.get("requirement")'),
    ("area-duplicate", "peripheral", 'if row["area"] in areas:', 'if False:'),
    ("reset-width", "peripheral", 'if int(register["reset"], 16).bit_length() > register["width"]:', 'if False:'),
    ("bits-bound", "peripheral", 'if low > high or ("width" in register and high >= register["width"]):', 'if False:'),
    ("layout-bound", "peripheral", 'if int(row["offset"], 16) + row["size"] > payload["layout"]["size"]:', 'if False:'),
    ("child-id-duplicate", "peripheral", 'if key in seen:', 'if False:'),
    ("order-step-existence", "peripheral", 'if before not in steps or after not in steps:', 'if False:'),
    ("order-self", "peripheral", 'if before == after:', 'if False:'),
    ("order-duplicate", "peripheral", 'if (before, after) in constraints:', 'if False:'),
    ("order-cycle", "peripheral", 'checker.add(file, path + ("data", "sequence", "order"), "ordering constraints form a cycle")', 'pass'),
    ("target-role", "peripheral", 'if entry and entry[0].get("role") != "target":', 'if False:'),
    ("subkey-support", "peripheral", 'if "support" in row and path[-2] in ("fields", "steps"):', 'if False:'),
    ("subkey-duplicate", "speccheck", 'self.add(f, path + ("id",), f"sub-key {rid!r} is used twice")', 'pass'),
    ("nested-citations", "speccheck", 'yield from supports(value, base + (key,), False)', 'yield from supports(value, base + (key,), False) if key != "data" else ()'),
    ("subkey-parent-basis", "peripheral", 'data["parent_identity"] = {k: payload["register"][k] for k in ("name", "offset")}', 'pass'),
    ("subkey-step-order", "peripheral", 'data["parent_identity"] = {"steps": [row["id"] for row in payload["sequence"]["steps"]]}', 'pass'),
    ("subkey-effective-requirement", "peripheral", 'data["requirement"] = rec.parent.data["requirement"]', 'pass'),
    ("parent-excludes-supported-children", "peripheral", 'owner[path[-1]] = {"id": owner[path[-1]]["id"]}', 'pass'),
    ("subkey-critical", "speccheck", 'if parent.data.get("critical"):', 'if False:'),
    ("subkey-records", "records", 'if dot and (key not in f.records or key in f.duplicated):', 'if dot:'),
    ("bad-subkey-diagnostic", "records", 'if dot and (key not in f.records or key in f.duplicated):\n            checker.add', 'if dot and (key not in f.records or key in f.duplicated):\n            continue\n            checker.add'),
    ("facts-target-gate", "speccheck", 'checker.check_file(file)\n    checker.check_references()', 'pass\n    checker.check_references()'),
    ("inventory-value", "inventory", 'if expected is not None and actual != expected:', 'if False:'),
    ("inventory-omission", "inventory", 'for name in values if name not in covered]', 'for name in values if False]'),
    ("inventory-conflict", "inventory", 'if name in covered and covered[name][0] != actual:', 'if False:'),
    ("inventory-absent", "inventory", 'absent = sorted(set(covered) - values.keys())', 'absent = []'),
    ("inventory-strict", "inventory", '(args.strict and result["omissions"])', '(False and result["omissions"])'),
    ("inventory-closed-files", "inventory", 'resolve.check_anchor(entry, {"path": header})', 'pass'),
    ("inventory-immutable", "inventory", 'entry["commit"], args.timeout,', 'resolve.git(local[entry["name"]], ["rev-parse", "HEAD"], 30, 1024).decode().strip(), args.timeout,'),
    ("inventory-prose-coverage", "inventory", 'for name in values if name not in covered]', 'for name in values if name not in covered and name not in str(data)]'),
    ("inventory-license", "inventory", 'resolve.check_license(repo, entry, {"path": header})', 'pass'),
    ("inventory-shift-bound", "inventory", 'and not 0 <= right <= 31:', 'and right < 0:'),
    ("inventory-genmask-order", "inventory", '0 <= values[1] <= values[0] <= 31:', '0 <= values[1] <= 31 and 0 <= values[0] <= 31:'),
    ("inventory-multiline-comment", "inventory", 'lambda m: " "\n                        if', 'lambda m: re.sub(r"[^\\n]", " ", m[0])\n                        if'),
    ("inventory-token-whitelist", "inventory", 'elif token not in {', 'elif token not in {"#", "##"} and token not in {'),
    ("inventory-literal-whitelist", "inventory", 'LITERAL.fullmatch(token)', 'LITERAL.match(token)'),
    ("inventory-upper-intermediate-bound", "inventory", 'if not 0 <= value <= 0xffffffff:', 'if value < 0:'),
    ("inventory-lower-intermediate-bound", "inventory", 'if not 0 <= value <= 0xffffffff:', 'if value > 0xffffffff:'),
    ("inventory-signed-overflow", "inventory", 'and not unsigned and value > 0x7fffffff:', 'and False:'),
    ("inventory-zero-divisor", "inventory", 'raise ValueError("division by zero")', 'return 0, unsigned'),
    ("inventory-complement", "inventory", 'value = ~value', 'value = value'),
    ("inventory-enum-sizeof", "inventory", 'r"[{}]|\\bsizeof\\b", body', 'r"[{}]", body'),
    ("inventory-enum-brace-refusal", "inventory", 'r"[{}]|\\bsizeof\\b", body', 'r"\\bsizeof\\b", body'),
    ("inventory-enum-matching-brace", "inventory", 'if depth == 0:\n                    yield', 'if masked[index] == "}":\n                    yield'),
    ("inventory-macro-token-boundaries", "inventory", 'value = " " + value + " "', 'value = value'),
    ("inventory-enum-integer-type", "inventory", 'value = f"({enum_value})"', 'value = f"({value})"'),
    ("inventory-enum-value-bound", "inventory", 'if declaration_kind == "enum" and value > 0x7fffffff:', 'if False:'),
    ("inventory-enum-dependency-bound", "inventory", 'if enum_value is None or enum_value > 0x7fffffff:', 'if enum_value is None:'),
    ("inventory-unique-definition", "inventory", 'if len(rows) != 1:', 'if False:'),
    ("inventory-conditional-macro", "inventory", '"conditional definition" if stack else None', 'None'),
    ("inventory-conditional-enum", "inventory", '"conditional definition" if conditional else None', 'None'),
    ("inventory-supported-dependency", "inventory", 'body, kind = supported(name)', 'body, _, kind = definitions[name][0]'),
    ("inventory-enum-directive", "inventory", 'if re.search(r"^[ \\t]*#", body, re.M):', 'if False:'),
    ("inventory-enum-branches", "inventory", 'return list(dict.fromkeys(names))', 'return list(dict.fromkeys(names))[:1]'),
    ("inventory-enum-macro-collision", "inventory", 'if "enum" in types and types & {"define", "guard"}:', 'if False:'),
    ("inventory-empty-builtin-guard", "inventory", 'name, body = match.groups()', 'name, body = match.groups()\n                if guard and i == guard[1]:\n                    continue'),
    ("inventory-whole-file-guard", "inventory", 'if i == closing and re.fullmatch', 'if re.fullmatch'),
    ("inventory-guard-alternative", "inventory", 'elif op in ("elif", "else") and depth == 1:', 'elif False:'),
    ("facts-file-symlink", "speccheck", 'or not path.is_file() or through_link(path):', 'or not path.is_file():'),
    ("duplicated-subkey-verdict", "records", 'key not in f.records or key in f.duplicated', 'key not in f.records'),
    ("layout-fields-no-subkey", "peripheral", 'if path[-2] == "steps" or "register" in data.get("data", {}):', 'if True:'),
    ("top-level-citations-once", "speccheck", 'if len(rec.path) == 2:', 'if True:'),
    ("generated-registers", "peripheral", 'registers.append(dict(payload["register"], fact=fid, fields=payload.get("fields", [])))', 'pass'),
    ("generated-verify", "peripheral", 'if row.get("requirement", fact.get("requirement")) == "as-implemented":', 'if False:'),
    ("generated-questions", "peripheral", 'questions.append({"fact": fid, **fact["todo"]})', 'pass'),
    ("generated-nested-todo", "peripheral", 'questions.append({"fact": fid + "." + key, **row["todo"]})', 'pass'),
    ("generated-references", "peripheral", 'for entry in resources.get(group, [])]', 'for entry in []]'),
    ("generated-provenance", "peripheral", 'classes = sorted({entry["class"] for fact in file.data["facts"]', 'classes = sorted({entry["class"] for fact in []'),
    ("markdown-registers", "render_md", '_table(out, "Register map (generated)", rows)', 'pass'),
    ("markdown-verify", "render_md", 'for row in summary["verify"]:', 'for row in []:'),
    ("markdown-questions", "render_md", '_table(out, "Open questions (generated)", summary["questions"])', 'pass'),
    ("markdown-provenance", "render_md", 'out.extend(["Support classes: " + ", ".join(code(c) for c in summary["classes"]) + ".", ""])', 'pass'),
    ("markdown-register-claim", "render_md", 'if "register" in data.get("data", {}):', 'if False:'),
]


def schema_mutations():
    result = []
    for name, keys in (("register", ("name", "offset")),
                       ("field", ("id", "name", "bits", "meaning")),
                       ("step", ("id", "action")), ("order", ("before", "after")),
                       ("layout", ("name", "size", "fields")),
                       ("area", ("area", "level", "note")),
                       ("layoutField", ("id", "name", "offset", "size", "meaning"))):
        for key in keys:
            result.append((name + "-requires-" + key, ("$defs", name, "required"), "remove", key))
    for name in ("register", "field", "step", "order", "layout", "layoutField", "area"):
        result.append((name + "-closed", ("$defs", name, "additionalProperties"), "set", True))
    for name in ("requirement",):
        result.append((name + "-enum", ("$defs", name), "set", {}))
    result.extend([
        ("payload-exclusive", ("$defs", "payload", "oneOf"), "rename", "anyOf"),
        ("field-support-rules", ("$defs", "field", "allOf"), "set", []),
        ("step-support-rules", ("$defs", "step", "allOf"), "set", []),
        ("order-support-rules", ("$defs", "order", "allOf"), "set", []),
        ("layout-field-support-rules", ("$defs", "layoutField", "allOf"), "set", []),
        ("fields-require-register", ("$defs", "payload", "dependentRequired"), "set", {}),
        ("area-level", ("$defs", "area", "properties", "level"), "set", {"type": "string"}),
        ("peripheral-resources", ("allOf", -1, "then", "required"), "remove", "resources"),
        ("peripheral-id", ("allOf", -1, "then", "required"), "remove", "id"),
        ("peripheral-name", ("allOf", -1, "then", "required"), "remove", "name"),
        ("peripheral-sections", ("allOf", -1, "then", "properties", "facts", "items", "properties", "section"), "set", {"type": "string"}),
        ("registers-payload", ("$defs", "fact", "allOf", 2), "set", {}),
        ("sequences-payload", ("$defs", "fact", "allOf", 3), "set", {}),
        ("layouts-payload", ("$defs", "fact", "allOf", 4), "set", {}),
        ("open-question-gap", ("$defs", "fact", "allOf", 5), "set", {}),
        ("register-reset-nonnull", ("$defs", "register", "properties", "reset", "type"), "set", ["string", "null"]),
        ("register-access", ("$defs", "register", "properties", "access"), "set", {}),
    ])
    for index, kind in enumerate(("board", "soc", "chip", "ip")):
        result.append((kind + "-no-payload", ("allOf", index, "then", "properties", "facts", "items", "not"), "set", {"not": {}}))
    for trail, label in ((("$defs", "register", "properties", "width", "minimum"), "register-width"),
                          (("$defs", "layout", "properties", "size", "minimum"), "layout-size"),
                          (("$defs", "layoutField", "properties", "size", "minimum"), "layout-field-size")):
        result.append((label, trail, "set", 0))
    for trail, label in ((("$defs", "payload", "properties", "fields", "minItems"), "register-fields-nonempty"),
                          (("$defs", "sequence", "properties", "steps", "minItems"), "steps-nonempty"),
                          (("$defs", "sequence", "properties", "order", "minItems"), "order-nonempty"),
                          (("$defs", "layout", "properties", "fields", "minItems"), "layout-fields-nonempty"),
                          (("allOf", -1, "then", "properties", "areas", "minItems"), "areas-nonempty")):
        result.append((label, trail, "set", 0))
    return result


def execute(case, store):
    label = case[0]
    dest = store / label
    for relative in ("skills/spec-format", "skills/board-expert/scripts", "skills/peripheral-spec/scripts", "skills/hardware-investigator/examples"):
        shutil.copytree(REPO / relative, dest / relative, ignore=shutil.ignore_patterns("__pycache__"))
    if isinstance(case[1], str):
        _, module, before, after = case
        path = dest / "skills/spec-format/scripts" / (module + ".py")
        text = path.read_text()
        if text.count(before) != 1:
            return {"mutation": label, "killed": False, "reason": "guard is not unique"}
        path.write_text(text.replace(before, after))
    else:
        _, trail, action, value = case
        path = dest / "skills/spec-format/schema/spec.schema.json"
        schema = json.loads(path.read_text())
        parent = schema
        for part in trail[:-1]:
            parent = parent[part]
        if action == "remove":
            parent[trail[-1]].remove(value)
        elif action == "rename":
            parent[value] = parent.pop(trail[-1])
        else:
            parent[trail[-1]] = value
        path.write_text(json.dumps(schema))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s",
                           "skills/spec-format/tests", "-p", "test_sf2_7a.py", "-q"],
                          cwd=dest, env=env, capture_output=True, text=True)
    output = proc.stdout + proc.stderr
    (store / (label + ".log")).write_text(output)
    match = re.search(r"FAILED \(failures=(\d+)(?:, errors=(\d+))?\)", output)
    killed = bool(proc.returncode and match and not match[2] and "AssertionError" in output
                  and "'error': 'internal'" not in output and '"error": "internal"' not in output)
    return {"mutation": label, "killed": killed, "exit": proc.returncode,
            "failures": int(match[1]) if match else 0}


def main():
    store = Path(tempfile.mkdtemp(prefix="sf2-7a-mutations-"))
    cases = CODE + schema_mutations()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda case: execute(case, store), cases))
    (store / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    for result in results:
        print(result["mutation"] + ": " + ("assertion kill" if result["killed"] else "UNQUALIFIED"))
    print(f"{sum(r['killed'] for r in results)}/{len(results)} qualified; logs: {store}")
    return int(not all(r["killed"] for r in results))


if __name__ == "__main__":
    sys.exit(main())
