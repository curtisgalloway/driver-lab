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

DEFINE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)(.*)$")
TOKEN = re.compile(r"\b[A-Za-z_]\w*\b")
COMMENTS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*', re.S)
BITFIELD = re.compile(r"^\s*(?:unsigned\s+)?(?:int|long|char|short|u(?:int)?\d+(?:_t)?)\s+(\w+)\s*:\s*\d+\s*;")
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.BitOr: operator.or_, ast.BitAnd: operator.and_, ast.BitXor: operator.xor,
       ast.LShift: operator.lshift, ast.RShift: operator.rshift}


def strip_comments(text):
    """Replace comments with whitespace, retaining tokens on either side."""
    return COMMENTS.sub(lambda m: " "
                        if m[0].startswith(("/*", "//")) else m[0], text)


def integer(expression, names, disabled=()):
    """Integer or None for a bounded subset of C constant expressions."""
    expression = " ".join(strip_comments(expression).split())
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
            if node.func.id in disabled or node.func.id in names:
                raise ValueError("locally defined call")
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


def declarations(text):
    """Collect every declaration, including unsupported forms, without overwriting names.

    Conditions are not executed. Their branches must cover all possibilities before a
    conditional name can be known. A conventional empty include-guard pair is ignored.
    """
    text = strip_comments(re.sub(r"\\\n", "", text))
    lines = text.splitlines()
    nonempty = [line.strip() for line in lines if line.strip()]
    guard = None
    if len(nonempty) >= 3:
        first = re.fullmatch(r"#\s*ifndef\s+(\w+)", nonempty[0])
        second = DEFINE.match(nonempty[1])
        if first and second and first[1] == second[1] and not second[2].strip():
            guard = first[1]
    definitions, kinds, stack, groups, predecessors = {}, {}, [], {}, {}
    enum_lines = []

    def add(name, expression, kind):
        definitions.setdefault(name, []).append((expression, tuple(stack)))
        kinds[name] = kind

    for line in lines:
        directive = re.match(r"\s*#\s*(\w+)\b(.*)", line)
        if directive:
            op, tail = directive.groups()
            if op in ("if", "ifdef", "ifndef"):
                if op == "ifndef" and tail.strip() == guard and not stack:
                    continue
                group = len(groups)
                groups[group] = [1, False]
                stack.append((group, 0))
            elif op in ("else", "elif") and stack:
                group, branch = stack.pop()
                groups[group][0] += 1
                groups[group][1] |= op == "else"
                stack.append((group, branch + 1))
            elif op == "endif" and stack:
                stack.pop()
            elif op == "define" and (match := DEFINE.match(line)):
                name, body = match.groups()
                if name != guard:
                    add(name, None if body.startswith("(") else body.strip(), "define")
            elif op == "undef" and (match := re.match(r"\s*(\w+)", tail)):
                add(match[1], None, "define")
            continue
        enum_lines.append((line, tuple(stack)))
        if match := BITFIELD.match(line):
            add(match[1], None, "bitfield")

    enum_text = "\n".join(line for line, _ in enum_lines)
    for enum in re.finditer(r"\benum\b[^;{]*\{([^}]*)\}", enum_text, re.S):
        previous = None
        preceding = []
        start = enum_text[:enum.start(1)].count("\n")
        position = 0
        for member in re.split(r",(?![^()]*\))", enum[1]):
            first = position + len(member) - len(member.lstrip())
            context = enum_lines[min(start + enum[1][:first].count("\n"), len(enum_lines) - 1)][1]
            position += len(member) + 1
            match = re.match(r"\s*([A-Za-z_]\w*)\b(.*)", member, re.S)
            if not match:
                continue
            name, tail = match.groups()
            if tail.strip().startswith("="):
                expression = tail.strip()[1:].strip()
            elif not tail.strip():
                expression = "0" if previous is None else f"({previous}) + 1"
                predecessors.setdefault(name, []).extend(preceding)
            else:
                expression = None
            definitions.setdefault(name, []).append((expression, context))
            kinds[name] = "enum"
            previous = name
            preceding.append(name)
    return definitions, kinds, groups, predecessors


def extract(text, reasons=None):
    return extract_headers([("", text)], reasons)[:2]


def extract_headers(headers, reasons=None):
    """Expand object macros as tokens, with bounded alternatives for duplicate definitions."""
    definitions, kinds, origins, groups, predecessors = {}, {}, {}, {}, {}
    for header, text in headers:
        found, types, conditions, dependencies = declarations(text)
        offset = len(groups)
        groups.update({g + offset: branches for g, branches in conditions.items()})
        for name, earlier in dependencies.items():
            predecessors.setdefault(name, []).extend(earlier)
        for name, rows in found.items():
            definitions.setdefault(name, []).extend(
                (expr, tuple((g + offset, b) for g, b in context)) for expr, context in rows)
            kinds[name], origins[name] = types[name], header

    def complete(contexts):
        if any(len(context) > 32 for context in contexts):
            return False
        if () in contexts:
            return True
        if not contexts:
            return False
        group = contexts[0][0][0]
        count, exhaustive = groups[group]
        return exhaustive and all(complete([c[1:] for c in contexts if c[0] == (group, b)])
                                  for b in range(count))

    budget = [0]

    def expand(expression, seen=()):
        budget[0] += 1
        if budget[0] > 4096:
            raise ValueError("macro expansion work bound")
        if expression is None or not expression or len(expression) > 4096 or len(seen) > 32:
            raise ValueError("unsupported declaration or expansion bound")
        parts, end = [""], 0
        for token in TOKEN.finditer(expression):
            name = token[0]
            alternatives = {name}
            if name in definitions:
                if name in seen:
                    raise ValueError("recursive macro")
                rows = definitions[name]
                for earlier in predecessors.get(name, []):
                    if not complete([context for _, context in definitions[earlier]]):
                        raise ValueError("implicit enum has a conditional preceding member")
                    candidates = {integer(expr, {}, disabled=definitions)
                                  for body, _ in definitions[earlier]
                                  for expr in expand(body, seen + (name,))}
                    if None in candidates or len(candidates) != 1:
                        raise ValueError("implicit enum has an unknown preceding member")
                if not complete([context for _, context in rows]):
                    raise ValueError("conditional definition may be absent")
                alternatives = set()
                for expr, _ in rows:
                    for value in expand(expr, seen + (name,)):
                        alternatives.add(f"({value})" if kinds[name] == "enum" else value)
            parts = [p + expression[end:token.start()] + value for p in parts for value in alternatives]
            if len(parts) > 64 or any(len(p) > 4096 for p in parts):
                raise ValueError("macro expansion bound")
            end = token.end()
        return {p + expression[end:] for p in parts}

    values, unknown = {}, {}
    for name, rows in definitions.items():
        budget[0] = 0
        try:
            if any(values.get(earlier) is None for earlier in predecessors.get(name, [])):
                raise ValueError("implicit enum has an unknown preceding member")
            if not complete([context for _, context in rows]):
                raise ValueError("conditional definition may be absent")
            results = {integer(expr, {}, disabled=definitions)
                       for body, _ in rows for expr in expand(body, (name,))}
            if None in results:
                raise ValueError("unsupported expression or declaration")
            if len(results) != 1:
                raise ValueError("ambiguous definitions disagree")
            values[name] = results.pop()
        except ValueError as exc:
            values[name], unknown[name] = None, str(exc)
    if reasons is not None:
        reasons.update(unknown)
    return values, kinds, origins


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
            if not 0 <= low <= high or ("width" in register and high >= register["width"]) or high > 4096:
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
    headers, reasons = [], {}
    with tempfile.TemporaryDirectory(prefix="spec-inventory-") as scratch:
        try:
            for header in args.headers:
                resolve.check_anchor(entry, {"path": header})
            repo = (resolve.Repository(local[entry["name"]], entry["commit"], args.timeout,
                                       args.limit_mb << 20) if entry["name"] in local else
                    resolve.fetch(entry, Path(scratch) / "source", args.timeout, args.limit_mb << 20))
            for header in args.headers:
                resolve.check_license(repo, entry, {"path": header})
                headers.append((header, "\n".join(repo.lines(header))))
        except resolve.ResolutionError as exc:
            return 1, {"ok": False, "findings": [{"message": str(exc)}],
                       "_text": [resolve.display_line(str(exc))]}
    values, kinds, origins = extract_headers(headers, reasons)
    result = compare(loaded.data, values, origins, kinds)
    result["unknown_reasons"] = reasons
    bad = bool(result["mismatches"] or result["conflicts"] or result["absent"] or
               result["unknown"] or (args.strict and result["omissions"]))
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
        lines.append(f"unknown value: {name}: {reasons[name]}")
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
