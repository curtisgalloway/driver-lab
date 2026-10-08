#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""spec.py: the spec format 2 command line (design: docs/SPEC-FORMAT-V2.md).

Subcommands built so far (SF2-1): `validate`. Later milestones add `check`, `status`,
`render`, `resolve`, `show`, `drift`, `inventory` and `migrate`.

Exit status (the house contract): 0 every file valid; 1 a file failed to load or validate;
2 usage (bad arguments, a path that does not exist, a file name that says no schema);
3 a pinned dependency is missing or at another version than skills/spec-format/requirements.txt
pins (there is no fallback parser).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_PRECONDITION = 0, 1, 2, 3

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
SCHEMA_DIR = SKILL_DIR / "schema"
REQUIREMENTS = SKILL_DIR / "requirements.txt"
SCHEMA_BASE = "https://github.com/curtisgalloway/driver-lab/spec-format/2/"
EXTENSION_URN = "urn:driver-lab:spec-format:2:extension:source-observed"
MARKER = "board-specs.yaml"

# Distribution name -> import name. The three libraries format 2 is built on (D8, D9, D20);
# every spec.py subcommand runs under the same pinned set.
DIRECT = {"pyyaml": "yaml", "jsonschema": "jsonschema", "markdown-it-py": "markdown_it"}

SKILL = """\
---
name: spec-format-cli
description: Drive spec.py, the spec format 2 tool (validate a spec, facts file, verification record or root marker against its schema).
---

# spec.py

    python3 skills/spec-format/scripts/spec.py validate <file>... [--root <dir>] [--json]

Run it in an environment holding skills/spec-format/requirements.txt (hash-pinned):
`uv run --with-requirements skills/spec-format/requirements.txt python3 ...`, or a venv made
with `pip install --require-hashes -r skills/spec-format/requirements.txt`.

The file name chooses the schema: `*.spec.yaml` and `*.facts.yaml` (spec.schema.json; a facts
file holds `kind: facts` and a spec file any other kind), `*.verify.yaml` (verify.schema.json),
`board-specs.yaml` (root.schema.json). `--root <dir>` reads `<dir>/board-specs.yaml` and loads
the `source-observed` schema fragment it names (D15); without it, a `source-observed` support
entry is refused.

Output: one `path:line:column: message` per finding, then a summary line. `--json` prints one
object: `{"ok": bool, "files": [{"path", "schema", "valid"}], "findings": [{"path", "line",
"column", "message"}]}`.

Exit status: 0 all valid; 1 a file invalid; 2 usage; 3 a pinned dependency missing or at
another version.
"""


class Usage(Exception):
    """A usage error: exit 2."""


class Precondition(Exception):
    """A missing precondition: exit 3."""


def pinned_versions() -> dict[str, str]:
    """The `name==version` pins of requirements.txt, by normalized distribution name."""
    pins = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)", line)
        if m:
            pins[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = m.group(2)
    return pins


def check_dependencies() -> list[str]:
    """Problems with the pinned direct dependencies; empty when all are present at the pin."""
    import importlib
    import importlib.metadata

    try:
        pins = pinned_versions()
    except OSError as exc:
        return [f"cannot read {REQUIREMENTS}: {exc}"]
    problems = []
    for dist, module in DIRECT.items():
        want = pins.get(dist)
        if want is None:
            problems.append(f"{REQUIREMENTS.name} pins no version of {dist}")
            continue
        try:
            have = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{dist} is not installed (pinned {want})")
            continue
        if have != want:
            problems.append(f"{dist} is {have}, pinned {want}")
            continue
        try:
            importlib.import_module(module)
        except ImportError as exc:
            problems.append(f"{dist} {have} does not import: {exc}")
    return problems


def _strict_json(path: Path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError(f"duplicate key {k!r}")
            out[k] = v
        return out

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


class Finding:
    def __init__(self, path, line, column, message):
        self.path, self.line, self.column, self.message = str(path), line, column, message

    def key(self):
        return (self.path, self.line, self.column, self.message)

    def as_dict(self):
        return {"path": self.path, "line": self.line, "column": self.column,
                "message": self.message}

    def __str__(self):
        return f"{self.path}:{self.line}:{self.column}: {self.message}"


# --- schemas -------------------------------------------------------------------------------

_DEFAULT_EXTENSION = {
    "$id": EXTENSION_URN,
    "$comment": "message: a source-observed entry needs the extension's schema fragment; "
    "pass --root with a root marker whose extensions names it (D15)",
    "not": {},
}

_FRAGMENT_KEYS = {"$comment", "title", "description", "type", "properties", "required"}
_FRAGMENT_PROPERTY = re.compile(r"^[a-z][a-z0-9_]*$")


def schema_kind(path: Path) -> str:
    name = path.name
    if name == MARKER:
        return "root"
    if name.endswith(".verify.yaml"):
        return "verify"
    if name.endswith(".spec.yaml") or name.endswith(".facts.yaml"):
        return "spec"
    raise Usage(
        f"{path}: cannot tell which schema applies; name the file *.spec.yaml, *.facts.yaml, "
        f"*.verify.yaml or {MARKER}"
    )


def load_schemas() -> dict[str, dict]:
    schemas = {}
    for kind in ("spec", "root", "verify"):
        path = SCHEMA_DIR / f"{kind}.schema.json"
        try:
            schemas[kind] = _strict_json(path)
        except (OSError, ValueError) as exc:
            raise Precondition(f"schema {path}: {exc}") from None
    return schemas


def check_fragment(fragment, where: Path) -> list[str]:
    """Problems with an extension's schema fragment; it may only add fields (D15).

    The fragment is composed into the support entry with the core schema's
    unevaluatedProperties still in force, so it must not carry keywords that would mark every
    property evaluated (additionalProperties, patternProperties, unevaluatedProperties) or
    that reach outside it ($ref, $id, $defs, ...).
    """
    import jsonschema

    if not isinstance(fragment, dict):
        return [f"{where}: a schema fragment is a JSON object"]
    problems = []
    extra = sorted(set(fragment) - _FRAGMENT_KEYS)
    if extra:
        problems.append(f"{where}: keywords not allowed in a fragment: {', '.join(extra)}")
    if fragment.get("type") != "object":
        problems.append(f'{where}: a fragment declares "type": "object"')
    props = fragment.get("properties")
    if not isinstance(props, dict) or not props:
        problems.append(f"{where}: a fragment declares its fields in a non-empty properties")
        props = {}
    for name in props:
        if name == "class" or not _FRAGMENT_PROPERTY.match(name):
            problems.append(f"{where}: field name {name!r} not allowed (lowercase, not class)")
    required = fragment.get("required", [])
    if not isinstance(required, list) or any(r not in props for r in required):
        problems.append(f"{where}: required lists only fields the fragment declares")

    def walk(node, trail):
        if isinstance(node, dict):
            for k, v in node.items():
                if k.startswith("$") and k != "$comment" and trail[-1:] != ("properties",):
                    problems.append(f"{where}: {k} at {'/'.join(trail) or 'top'} not allowed")
                walk(v, trail + (k,))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, trail + (str(i),))

    walk(fragment, ())
    try:
        jsonschema.Draft202012Validator.check_schema(fragment)
    except jsonschema.SchemaError as exc:
        problems.append(f"{where}: not a valid JSON Schema: {exc.message}")
    return problems


def registry_for(schemas: dict[str, dict], extension: dict | None):
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    ext = dict(extension, **{"$id": EXTENSION_URN}) if extension else _DEFAULT_EXTENSION
    resources = [(s["$id"], Resource.from_contents(s, default_specification=DRAFT202012))
                 for s in schemas.values()]
    resources.append((EXTENSION_URN, Resource(contents=ext, specification=DRAFT202012)))
    return Registry().with_resources(resources)


# --- error reporting ------------------------------------------------------------------------

def _where(path) -> str:
    out = ""
    for p in path:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out or "(top)"


def _custom_message(error) -> str | None:
    """A "message: ..." $comment on the failing schema or on a failing branch under it."""
    stack = [error]
    while stack:
        e = stack.pop(0)
        comment = e.schema.get("$comment") if isinstance(e.schema, dict) else None
        if isinstance(comment, str) and comment.startswith("message: "):
            return comment[len("message: "):]
        stack.extend(e.context or [])
    return None


def _short(error) -> str:
    message = error.message
    shown = repr(error.instance)
    if len(shown) > 60 and message.startswith(shown):
        message = "the value" + message[len(shown):]
    if len(message) > 300:
        message = message[:297] + "..."
    return message


def _declared_names(node, out: set) -> set:
    """Every property name any schema declares, anywhere."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            out.update(props)
        for v in node.values():
            _declared_names(v, out)
    elif isinstance(node, list):
        for v in node:
            _declared_names(v, out)
    return out


def schema_findings(validator, data, loaded, path: Path, declared: set) -> list[Finding]:
    """Findings for every schema error, each placed at its line and column.

    An unknown-key report (unevaluatedProperties) has a cascade: when a value inside a kind or
    class branch fails, the branch fails and every key it declared reads as unevaluated. So a
    key that some schema declares is reported as unknown only when nothing else failed at or
    below the object holding it; a key no schema declares is always reported.
    """
    from jsonschema.exceptions import best_match

    errors = list(validator.iter_errors(data))
    other_paths = [tuple(e.absolute_path) for e in errors
                   if e.validator not in ("unevaluatedProperties", "additionalProperties")]
    out = []
    for error in errors:
        at = tuple(error.absolute_path)
        if error.validator in ("unevaluatedProperties", "additionalProperties") and isinstance(
            error.instance, dict
        ):
            shadowed = any(p[:len(at)] == at for p in other_paths)
            for key in error.instance:
                if repr(key) not in error.message:
                    continue
                if shadowed and key in declared:
                    continue
                m = loaded.mark(at + (key,), key=True)
                out.append(Finding(path, m.line, m.column,
                                   f"{_where(at + (key,))}: unknown key {key!r} here"))
            continue
        mark = loaded.mark(at)
        message = _custom_message(error)
        if message is None and error.validator == "type" and not isinstance(
            error.instance, (str, dict, list)
        ):
            read_as = {bool: "a boolean", int: "an integer", type(None): "null"}.get(
                type(error.instance), type(error.instance).__name__)
            message = (f"{error.instance!r} was read as {read_as}, expected "
                       f"{error.validator_value}; quote it to keep it a string (D6)"
                       if error.validator_value == "string" else None)
        if message is None:
            message = _short(error)
            if error.validator in ("anyOf", "oneOf") and error.context:
                deeper = [e for e in error.context if e.validator != "type"] or error.context
                message += f" (closest: {_short(best_match(deeper))})"
        out.append(Finding(path, mark.line, mark.column, f"{_where(at)}: {message}"))
    return out


# --- validate -------------------------------------------------------------------------------

def load_extension(marker: Path, data, findings: list[Finding]) -> dict | None:
    """The source-observed fragment a valid marker names, or None; problems become findings."""
    if not isinstance(data, dict) or not data.get("extensions"):
        return None
    rel = data["extensions"][0]["schema"]
    root = marker.parent.resolve()
    target = (marker.parent / rel).resolve()
    if root not in target.parents:
        findings.append(Finding(marker, 1, 1, f"extensions: {rel} lies outside the root"))
        return None
    try:
        fragment = _strict_json(target)
    except (OSError, ValueError) as exc:
        findings.append(Finding(marker, 1, 1, f"extensions: {rel}: {exc}"))
        return None
    problems = check_fragment(fragment, Path(rel))
    for p in problems:
        findings.append(Finding(marker, 1, 1, f"extensions: {p}"))
    return None if problems else fragment


def validate_file(path: Path, schemas, extension, findings: list[Finding]) -> tuple[bool, str]:
    import jsonschema

    import specload

    kind = schema_kind(path)
    before = len(findings)
    try:
        loaded = specload.load_strict_marked(path)
    except specload.LoadError as exc:
        findings.append(Finding(path, exc.line, exc.column, exc.problem))
        return False, kind
    if kind == "root":
        extension = None  # a marker is validated with its own fragment, below
    registry = registry_for(schemas, extension)
    validator = jsonschema.Draft202012Validator(schemas[kind], registry=registry)
    declared = _declared_names(list(schemas.values()) + [extension or {}], set())
    findings.extend(schema_findings(validator, loaded.data, loaded, path, declared))
    data = loaded.data
    if kind == "spec" and isinstance(data, dict) and isinstance(data.get("kind"), str):
        is_facts_name = path.name.endswith(".facts.yaml")
        if is_facts_name != (data["kind"] == "facts"):
            m = loaded.mark(("kind",))
            want = "a *.facts.yaml file holds kind: facts" if is_facts_name else (
                "kind: facts belongs in a *.facts.yaml file")
            findings.append(Finding(path, m.line, m.column, f"kind: {want}"))
    if kind == "root" and len(findings) == before:
        load_extension(path, data, findings)
    return len(findings) == before, kind


def read_root(root: Path, schemas, findings: list[Finding]) -> dict | None:
    marker = root / MARKER
    if not marker.is_file():
        raise Usage(f"--root {root}: no {MARKER} there")
    ok, _ = validate_file(marker, schemas, None, findings)
    if not ok:
        return None
    import specload

    return load_extension(marker, specload.load_strict(marker), [])


def cmd_validate(args) -> tuple[int, dict]:
    for p in args.files:
        if not p.is_file():
            raise Usage(f"{p}: no such file")
        schema_kind(p)
    if args.root is not None and not args.root.is_dir():
        raise Usage(f"--root {args.root}: not a directory")
    schemas = load_schemas()
    findings: list[Finding] = []
    extension = read_root(args.root, schemas, findings) if args.root else None
    files = []
    for p in args.files:
        ok, kind = validate_file(p, schemas, extension, findings)
        files.append({"path": str(p), "schema": kind, "valid": ok})
    uniq = {f.key(): f for f in findings}
    ordered = sorted(uniq.values(), key=lambda f: (f.path, f.line, f.column, f.message))
    ok = not ordered
    return (EXIT_OK if ok else EXIT_INVALID), {
        "ok": ok,
        "files": files,
        "findings": [f.as_dict() for f in ordered],
        "_text": [str(f) for f in ordered],
    }


class _Parser(argparse.ArgumentParser):
    """argparse that raises Usage instead of exiting, so --json can shape the error."""

    def error(self, message):
        raise Usage(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="spec.py", description=__doc__.splitlines()[0], allow_abbrev=False,
        epilog="exit status: 0 valid; 1 invalid; 2 usage; 3 a pinned dependency missing",
    )
    parser.add_argument("--skill", action="store_true", help="print the usage skill and exit")
    sub = parser.add_subparsers(dest="command")
    v = sub.add_parser("validate", help="load and schema-check files", allow_abbrev=False)
    v.add_argument("files", nargs="+", type=Path)
    v.add_argument("--root", type=Path, help="a root whose marker names extension fragments")
    v.add_argument("--json", action="store_true", help="one JSON object on stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    want_json = "--json" in argv
    parser = build_parser()

    def fail_usage(message: str) -> int:
        if want_json:
            print(json.dumps({"ok": False, "error": "usage", "findings": [message]},
                             sort_keys=True))
        else:
            print(f"usage error: {message}", file=sys.stderr)
        return EXIT_USAGE

    try:
        args = parser.parse_args(argv)
    except Usage as exc:
        return fail_usage(str(exc))
    if args.skill:
        print(SKILL, end="")
        return EXIT_OK
    if args.command is None:
        return fail_usage("name a subcommand: validate")

    problems = check_dependencies()
    if problems:
        if want_json:
            print(json.dumps({"ok": False, "error": "precondition", "findings": problems},
                             sort_keys=True))
        else:
            for p in problems:
                print(f"missing precondition: {p}", file=sys.stderr)
            print("install: pip install --require-hashes -r skills/spec-format/requirements.txt",
                  file=sys.stderr)
        return EXIT_PRECONDITION
    sys.path.insert(0, str(HERE))
    try:
        code, result = cmd_validate(args)
    except Usage as exc:
        return fail_usage(str(exc))
    except Precondition as exc:
        if want_json:
            print(json.dumps({"ok": False, "error": "precondition", "findings": [str(exc)]},
                             sort_keys=True))
        else:
            print(f"missing precondition: {exc}", file=sys.stderr)
        return EXIT_PRECONDITION
    text = result.pop("_text")
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        for line in text:
            print(line)
        bad = sum(1 for f in result["files"] if not f["valid"])
        print(f"{len(result['files'])} file(s), {bad} invalid, {len(text)} finding(s)")
    return code


if __name__ == "__main__":
    sys.exit(main())
