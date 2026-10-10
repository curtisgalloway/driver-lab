# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Compare typed register offsets and field masks with C constants at an immutable pin.

Evaluate only a supported subset: one definition per name across all cited headers,
no macro/enum collision, and no conditional definition or dependency except inside a
recognized whole-file include guard. Any directive in an enum body makes every member
unknown; members from every branch are retained. Object macros expand textually and
every token must pass the bounded integer parser (never eval or a shell). Built-in
BIT/GENMASK meanings apply only when no header defines the name, including empty guard
macros. Unsupported names carry reasons and still count for omissions. Only structured
payloads count as coverage. Conditions and duplicate alternatives are never guessed.
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
    return COMMENTS.sub(lambda m: re.sub(r"[^\n]", " ", m[0])
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


def include_guard(lines):
    """Opening/define/closing line indices only for a balanced whole-file guard."""
    nonempty = [i for i, line in enumerate(lines) if line.strip()]
    if len(nonempty) < 3:
        return None
    opening, defining, closing = nonempty[0], nonempty[1], nonempty[-1]
    first = re.fullmatch(r"\s*#\s*ifndef\s+([A-Za-z_]\w*)\s*", lines[opening])
    second = DEFINE.match(lines[defining])
    if not (first and second and first[1] == second[1] and not second[2].strip()):
        return None
    depth = 0
    for i in nonempty:
        directive = re.match(r"\s*#\s*(\w+)\b", lines[i])
        if not directive:
            continue
        op = directive[1]
        if op in ("if", "ifdef", "ifndef"):
            depth += 1
        elif op in ("elif", "else") and depth == 1:
            return None
        elif op == "endif":
            depth -= 1
            if depth == 0:
                if i == closing and re.fullmatch(r"\s*#\s*endif\s*", lines[i]):
                    return opening, defining, closing
                return None
    return None


def directed_enum_names(body):
    """Collect member names through all branches without evaluating their expressions.

    Each branch resumes the member/expression state at its conditional's opening.
    This retains comma-free alternative members without treating an initializer's
    branch-dependent identifiers as members. States merge at endif, never values.
    """
    tokens = re.compile(r"^[ \t]*#\s*(\w+)\b[^\n]*|[A-Za-z_]\w*|"
                        r"0[xX][0-9a-fA-F]+|\d+|\"(?:\\.|[^\"\\])*\"|"
                        r"'(?:\\.|[^'\\])*'|[^\s]", re.M)
    states, stack, names = {(True, 0)}, [], []
    for token in tokens.finditer(body):
        if token[1]:
            op = token[1]
            if op in ("if", "ifdef", "ifndef"):
                stack.append((set(states), set(), False))
            elif op in ("elif", "else") and stack:
                entry, exits, exhaustive = stack.pop()
                stack.append((entry, exits | states, exhaustive or op == "else"))
                states = set(entry)
            elif op == "endif" and stack:
                entry, exits, exhaustive = stack.pop()
                states |= exits | (set() if exhaustive else entry)
            continue
        value, updated = token[0], set()
        for beginning, depth in states:
            if beginning and re.fullmatch(r"[A-Za-z_]\w*", value):
                names.append(value)
                beginning = False
            elif value == "(":
                depth += 1
            elif value == ")":
                depth = max(0, depth - 1)
            elif value == "," and depth == 0:
                beginning = True
            updated.add((beginning, depth))
        states = updated
    return list(dict.fromkeys(names))


def declarations(text):
    """Collect definitions and refusal reasons without executing the preprocessor."""
    text = strip_comments(re.sub(r"\\\n", "", text))
    lines = text.splitlines()
    guard = include_guard(lines)
    definitions, stack, contexts, predecessors = {}, [], [], {}

    def add(name, expression, kind, reason=None):
        definitions.setdefault(name, []).append((expression, reason, kind))

    for i, line in enumerate(lines):
        contexts.append(bool(stack))
        directive = re.match(r"\s*#\s*(\w+)\b(.*)", line)
        if directive:
            op, tail = directive.groups()
            if guard and i in (guard[0], guard[2]):
                continue
            if op in ("if", "ifdef", "ifndef"):
                stack.append(i)
            elif op == "endif" and stack:
                stack.pop()
            elif op == "define" and (match := DEFINE.match(line)):
                name, body = match.groups()
                add(name, None if body.startswith("(") else body.strip(),
                    "guard" if guard and i == guard[1] else "define",
                    "conditional definition" if stack else None)
            elif op == "undef" and (match := re.match(r"\s*(\w+)", tail)):
                add(match[1], None, "define", "unsupported undef directive")
            continue
        if match := BITFIELD.match(line):
            add(match[1], None, "bitfield", "unsupported bitfield declaration")

    enum_text = re.sub(r"^[ \t]*#[^\n]*", lambda m: " " * len(m[0]), text, flags=re.M)
    enum_text = COMMENTS.sub(lambda m: re.sub(r"[^\n]", " ", m[0]), enum_text)
    for enum in re.finditer(r"\benum\b[^;{]*\{([^}]*)\}", enum_text, re.S):
        body = text[enum.start(1):enum.end(1)]
        conditional = contexts[text[:enum.start()].count("\n")]
        if re.search(r"^[ \t]*#", body, re.M):
            for name in directed_enum_names(body):
                add(name, None, "enum", "preprocessor directive in enum body")
            continue
        previous, preceding = None, []
        for member in re.split(r",(?![^()]*\))", body):
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
            add(name, expression, "enum", "conditional definition" if conditional else None)
            previous = name
            preceding.append(name)
    return definitions, predecessors


def extract(text, reasons=None):
    return extract_headers([("", text)], reasons)[:2]


def extract_headers(headers, reasons=None):
    """Evaluate unique, unconditional definitions and supported dependencies only."""
    definitions, kinds, origins, predecessors = {}, {}, {}, {}
    for header, text in headers:
        found, dependencies = declarations(text)
        for name, earlier in dependencies.items():
            predecessors.setdefault(name, []).extend(earlier)
        for name, rows in found.items():
            definitions.setdefault(name, []).extend(rows)
            kinds[name] = "define" if rows[-1][2] == "guard" else rows[-1][2]
            origins[name] = header

    def supported(name):
        rows = definitions[name]
        types = {kind for _, _, kind in rows}
        if "enum" in types and types & {"define", "guard"}:
            raise ValueError("name is both an enum member and a macro")
        if len(rows) != 1:
            raise ValueError("ambiguous name: multiple definitions")
        expression, reason, kind = rows[0]
        if reason:
            raise ValueError(reason)
        return expression, kind

    budget = [0]

    def expand(expression, seen=()):
        budget[0] += 1
        if budget[0] > 4096:
            raise ValueError("macro expansion work bound")
        if expression is None or not expression or len(expression) > 4096 or len(seen) > 32:
            raise ValueError("unsupported declaration or expansion bound")
        parts, end = [], 0
        for token in TOKEN.finditer(expression):
            name, value = token[0], token[0]
            if name in definitions:
                if name in seen:
                    raise ValueError("recursive macro")
                body, kind = supported(name)
                for earlier in predecessors.get(name, []):
                    earlier_body, _ = supported(earlier)
                    candidate = integer(expand(earlier_body, seen + (name,)), {}, disabled=definitions)
                    if candidate is None:
                        raise ValueError("implicit enum has an unknown preceding member")
                value = expand(body, seen + (name,))
                if kind == "enum":
                    value = f"({value})"
            parts.extend((expression[end:token.start()], value))
            if sum(map(len, parts)) > 4096:
                raise ValueError("macro expansion bound")
            end = token.end()
        return "".join(parts) + expression[end:]

    values, unknown = {}, {}
    for name, rows in definitions.items():
        if len(rows) == 1 and rows[0][2] == "guard":
            continue
        budget[0] = 0
        try:
            body, _ = supported(name)
            if any(values.get(earlier) is None for earlier in predecessors.get(name, [])):
                raise ValueError("implicit enum has an unknown preceding member")
            value = integer(expand(body, (name,)), {}, disabled=definitions)
            if value is None:
                raise ValueError("unsupported expression or declaration")
            values[name] = value
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
