# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Compare typed register offsets and field masks with C constants at an immutable pin.

Expressions use a bounded integer parser, never eval or a shell. Unsupported expressions
remain unknown and are counted explicitly. Only structured payloads count as coverage.
"""

from __future__ import annotations

import ast
import operator
from pathlib import Path
import re
import tempfile

import resolve

DEFINE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)\s+(.+)")
ENUM = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*([^,}]+)")
BITFIELD = re.compile(r"^\s*(?:unsigned\s+)?(?:int|long|char|short|u(?:int)?\d+(?:_t)?)\s+(\w+)\s*:\s*\d+\s*;")
SKIP = re.compile(r"^(_+|.*_H_?$|.*_H__$|.*_INCLUDED$)")
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.BitOr: operator.or_, ast.BitAnd: operator.and_, ast.BitXor: operator.xor,
       ast.LShift: operator.lshift, ast.RShift: operator.rshift}


def integer(expression, names):
    """Integer or None for a bounded subset of C constant expressions."""
    expression = re.split(r"/\*|//", expression, maxsplit=1)[0].strip()
    expression = re.sub(r"\b(0[xX][0-9a-fA-F]+|[0-9]+)[uUlL]+\b", r"\1", expression)
    if len(expression) > 4096:
        return None

    def read(node, depth=0):
        if depth > 32:
            raise ValueError("expression nesting")
        if isinstance(node, ast.Constant) and type(node.value) is int:
            value = node.value
        elif isinstance(node, ast.Name) and names.get(node.id) is not None:
            value = names[node.id]
        elif isinstance(node, ast.BinOp) and type(node.op) in OPS:
            left, right = read(node.left, depth + 1), read(node.right, depth + 1)
            if isinstance(node.op, (ast.LShift, ast.RShift)) and not 0 <= right <= 4096:
                raise ValueError("shift bound")
            value = OPS[type(node.op)](left, right)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            values = [read(arg, depth + 1) for arg in node.args]
            if node.func.id in ("BIT", "BIT_ULL") and len(values) == 1 and 0 <= values[0] <= 4096:
                value = 1 << values[0]
            elif node.func.id in ("GENMASK", "GENMASK_ULL") and len(values) == 2 and 0 <= values[1] <= values[0] <= 4096:
                high, low = values
                value = ((1 << (high - low + 1)) - 1) << low
            else:
                raise ValueError("unsupported call")
        else:
            raise ValueError("unsupported expression")
        if value < 0 or value.bit_length() > 4096:
            raise ValueError("integer bound")
        return value

    try:
        return read(ast.parse(expression, mode="eval").body)
    except (SyntaxError, ValueError, RecursionError):
        return None


def extract(text):
    definitions, kinds = {}, {}
    for line in text.splitlines():
        match = DEFINE.match(line) or ENUM.match(line)
        if match and not SKIP.match(match[1]):
            definitions[match[1]] = match[2]
            kinds[match[1]] = "define" if DEFINE.match(line) else "enum"
        elif (match := BITFIELD.match(line)):
            definitions[match[1]] = ""
            kinds[match[1]] = "bitfield"
    values = dict.fromkeys(definitions)
    for _ in range(min(len(values), 64) + 1):
        changed = False
        for name, expression in definitions.items():
            if values[name] is None:
                value = integer(expression, values)
                if value is not None:
                    values[name], changed = value, True
        if not changed:
            break
    return values, kinds


def compare(data, values, origins, kinds):
    """Exact reports: name, expected header value, actual structured value, fact key."""
    covered, mismatches, conflicts = {}, [], []
    for fact in data["facts"]:
        payload = fact.get("data", {})
        if "register" not in payload:
            continue
        register = payload["register"]
        entries = [(register["name"], int(register["offset"], 16), fact["id"])]
        for field in payload.get("fields", []):
            low, high = field["bits"]
            if not 0 <= low <= high < register["width"] or high > 4096:
                import spec

                raise spec.Usage("inventory field bits must be ordered, inside width and at most 4096")
            entries.append((field["name"], ((1 << (high - low + 1)) - 1) << low,
                            fact["id"] + "." + field["id"]))
        for name, actual, key in entries:
            if name in covered and covered[name][0] != actual:
                conflicts.append({"name": name, "facts": [covered[name][1], key],
                                  "values": [hex(covered[name][0]), hex(actual)]})
            covered[name] = (actual, key)
            expected = values.get(name)
            if expected is not None and actual != expected:
                mismatches.append({"name": name, "expected": hex(expected), "actual": hex(actual),
                                   "fact": key, "path": origins[name]})
    omissions = [{"name": name, "kind": kinds[name], "path": origins[name]}
                 for name in values if name not in covered]
    absent = sorted(set(covered) - values.keys())
    return {"omissions": omissions, "mismatches": mismatches, "conflicts": conflicts,
            "absent": absent, "unknown": sorted(n for n, v in values.items() if v is None),
            "names": len(values), "covered": len(set(covered) & values.keys())}


def run(args):
    import spec

    files, findings, local = resolve.prepare(args)
    if findings:
        return 1, {"ok": False, "findings": resolve.validation_findings(findings),
                   "_text": [str(f) for f in findings]}
    if len(files) != 1 or not args.headers:
        raise spec.Usage("inventory takes one file and at least one --headers path")
    _, loaded = files[0]
    entries = loaded.data.get("resources", {}).get("repos", [])
    selected = [e for e in entries if args.pin is None or e["name"] == args.pin]
    if len(selected) != 1:
        raise spec.Usage("--pin must select exactly one repos entry for inventory")
    entry = selected[0]
    try:
        resolve.check_commit(entry.get("commit"))
        resolve.check_url(entry["url"])
    except resolve.ResolutionError as exc:
        raise spec.Usage(f"inventory needs an immutable source pin: {exc}") from exc
    values, origins, kinds = {}, {}, {}
    with tempfile.TemporaryDirectory(prefix="spec-inventory-") as scratch:
        try:
            for header in args.headers:
                resolve.check_anchor(entry, {"path": header})
            repo = (resolve.Repository(local[entry["name"]], entry["commit"], args.timeout,
                                       args.limit_mb << 20) if entry["name"] in local else
                    resolve.fetch(entry, Path(scratch) / "source", args.timeout, args.limit_mb << 20))
            for header in args.headers:
                resolve.check_license(repo, entry, {"path": header})
                found, types = extract("\n".join(repo.lines(header)))
                for name, value in found.items():
                    if name in values and values[name] != value:
                        raise resolve.ContentError(f"header constants disagree for {name}")
                    values[name], kinds[name], origins[name] = value, types[name], header
        except resolve.ResolutionError as exc:
            return 1, {"ok": False, "findings": [{"message": str(exc)}],
                       "_text": [resolve.display_line(str(exc))]}
    result = compare(loaded.data, values, origins, kinds)
    bad = bool(result["mismatches"] or result["conflicts"] or result["absent"] or
               (args.strict and result["omissions"]))
    result.update(ok=not bad, pin=entry["name"], commit=entry["commit"], findings=[])
    lines = [f"inventory: {result['names']} names; {result['covered']} covered; "
             f"{len(result['unknown'])} unknown values"]
    for row in result["mismatches"]:
        lines.append(f"MISMATCH {row['name']}: header {row['expected']}, spec {row['actual']} "
                     f"at {row['fact']} ({row['path']})")
    for row in result["omissions"]:
        lines.append(f"omitted {row['name']} ({row['kind']}, {row['path']})")
    for row in result["conflicts"]:
        lines.append(f"CONFLICT {row['name']}: {row['values']} at {row['facts']}")
    for name in result["absent"]:
        lines.append(f"absent from headers: {name}")
    for name in result["unknown"]:
        lines.append(f"unknown value: {name}")
    lines.append("result: " + ("FAIL" if bad else "PASS"))
    result["_text"] = [resolve.display_line(line) for line in lines]
    return int(bad), result


def register(subparsers):
    parser = subparsers.add_parser("inventory", help=__doc__.splitlines()[0], allow_abbrev=False)
    resolve.add_arguments(parser)
    parser.add_argument("--pin", help="repos entry containing the headers")
    parser.add_argument("--headers", nargs="+", required=True, help="repo-relative files in the pin's closed list")
    parser.add_argument("--strict", action="store_true", help="omissions also fail")
    parser.set_defaults(handler=run)
