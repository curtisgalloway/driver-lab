#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""spec.py: the spec format 2 command line (design: docs/SPEC-FORMAT-V2.md).

Subcommands built so far: `validate` (SF2-1), `check` (SF2-2, in speccheck.py; verification
records and freshness from SF2-3, in records.py), `status` (SF2-3), Markdown `render`
(SF2-4, in render_md.py), HTML `render` (SF2-5, in render_html.py), `resolve`, `show`
and `drift` (SF2-6, in resolve.py and drift.py), typed peripheral `inventory` (SF2-7a,
in inventory.py) and mechanical `migrate` (SF2-10a, in migrate.py).

Exit status (the house contract): 0 every file valid, or every root checked with no error
(warnings allowed); 1 a file failed to load or validate, or a check found an error; 2 usage
(bad arguments, a path that does not exist, a file name that says no schema, roots that are the
same or nested, a context root holding a symbolic link); 3 a pinned dependency is missing or at
another version than skills/spec-format/requirements.txt pins, or that file holds a marker
spec.py cannot evaluate (there is no fallback parser), or a root has no board-specs.yaml;
100 an internal error in spec.py itself, not a verdict on any file (the tool-specific band
100-124 of the house exit-code contract; 4 is reserved there for "target unreachable").
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_PRECONDITION, EXIT_INTERNAL = 0, 1, 2, 3, 100

HERE = Path(__file__).resolve().parent
# `python3 -I` leaves the script's directory off sys.path.
sys.path.insert(0, str(HERE))
from textnames import visible_name  # pylint: disable=wrong-import-position
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
description: Drive spec.py, the spec format 2 tool (validate a file against its schema; check spec roots for composition, references, the license gate and verification records; report each verdict's freshness; resolve anchors, show evidence and compare or rewrite pins with drift).
---

# spec.py

    python3 skills/spec-format/scripts/spec.py validate <file>... [--root <dir>] [--json]
    python3 skills/spec-format/scripts/spec.py check <root>... [--context-root <dir>]...
        [--require-license] [--public-skill <name>]... [--stub <SKILL.md>]...
        [--stubs-from <skills dir>]... [--require-verified pr|main] [--json]
    python3 skills/spec-format/scripts/spec.py check <file.facts.yaml>... --root <dir>
        [--require-license] [--public-skill <name>]... [--json]
    python3 skills/spec-format/scripts/spec.py status <root>... [--context-root <dir>]...
        [--require-license] [--public-skill <name>]... [--stale] [--json]
    python3 skills/spec-format/scripts/spec.py render <root>... [--context-root <dir>]...
        [--spec <id>] [--merged] [--with-status] [--source-commit <ROOT=40-hex>]...
        [--tool-commit <40-hex>] --format md|html [--json]
    python3 skills/spec-format/scripts/spec.py resolve <file>... [--repo NAME=CHECKOUT]...
        [--docs-dir DIR] [--root DIR] [--timeout SECONDS] [--limit-mb N] [--json]
    python3 skills/spec-format/scripts/spec.py show <file>... [resolver options]
    python3 skills/spec-format/scripts/spec.py drift <commit> <file> [--pin NAME]
        [--rewrite] [resolver options]
    python3 skills/spec-format/scripts/spec.py inventory <file> --headers <path>...
        [--pin NAME] [--strict] [resolver options]
    python3 skills/spec-format/scripts/spec.py migrate <v1.spec.md> [--output <new.spec.yaml>]
        [--report <new.md>] [--marker <v1 board-specs.yaml>] [--verdicts <v1.verify.md>]
        [--license-from REPO:PATH=spdx-line|notice|license-file]... [--json]

`migrate` creates one fact per format 1 bullet, with an id from its bold lead-in, and a report
mapping every old verdict key. Explicit src anchors and unambiguous DT file/line parentheticals
become support. Document and inference prose stays in the report and is marked citation-pass
in the fact's TODO. Mixed bullets are marked split-mixed and kept whole. Inference-nested anchors
are report candidates only. Document registry classes are provisional doc until the citation
pass. Each v1 repository file needs an explicit --license-from declaration; the tool does not
read sources. Document hashes, commits, page counts and retrieval URLs are extracted when
explicit in resource metadata. A sibling marker, when present, is copied with format: 2 to the
output directory. A sibling resources verification record, when present (or supplied with
--verdicts), supplies the exact old keys; otherwise keys are derived from section/ordinal/title.
Outputs must be new files; no overwrites. No verdicts carry, and critical
fact selection, citation judgments, splits and fidelity checking belong to later readers.

Run it in a venv made with
`python3 -m venv .venv-sf2 && .venv-sf2/bin/pip install --require-hashes -r skills/spec-format/requirements.txt`
(pip checks the hashes; `uv run --with-requirements` was seen installing a file with wrong ones).

The file name chooses the schema: `*.spec.yaml` and `*.facts.yaml` (spec.schema.json; a facts
file holds `kind: facts` and a spec file any other kind), `*.verify.yaml` (verify.schema.json),
`board-specs.yaml` (root.schema.json). `--root <dir>` reads `<dir>/board-specs.yaml` and loads
the `source-observed` schema fragment it names (D15); without it, a `source-observed` support
entry is refused.

Output: one `path:line:column: message` per finding, then a summary line. `--json` prints one
object, always: `{"ok": bool, "files": [{"path", "schema", "valid"}], "findings": [{"path",
"line", "column", "message"}]}`, plus `"error": "usage" | "precondition" | "internal"` when the
run did not validate (then `files` is empty and each finding has path "" and line and column 0).
A file that cannot be read is a finding on that file.

`check` reads each root's `board-specs.yaml`, validates every `*.spec.yaml` below it, then
checks what a schema cannot: names (`doc`, `repo`, `assumption`) resolving in the citing file,
document classes and page bounds, ids unique per spec id per root, composition (`parts`,
`variant_of`, `instances[].ip`, overlays), fact references (`#id`, `spec#id`,
`spec@root#id`) with layer order and no premise cycles, and the license gate, direct and
through references. `--context-root` reads a further root so references and overlays resolve;
findings in its own files are warnings. `--require-license` also gates repos entries no anchor
cites. `--public-skill` names a skill a public root's tools may name in `via:`. Output: one
`path:line:column: error|warning: message` per finding, then a summary; `--json` prints
`{"ok", "roots": [{"path", "name", "layer", "context"}], "specs", "stubs", "verification",
"findings": [{"path", "line", "column", "level", "message"}]}`, with `"error"` as for `validate`
when no check ran; `verification` counts the checked roots' facts by freshness.

Verification records: `<root>/resources/<name>.verify.yaml` belongs to `<name>.spec.yaml` (any
directory of the root); its `spec` and `spec_file` name that file, every verdict key names one of
its facts (instances, variants), `summary` counts the verdicts, a GAP verdict belongs to a gap
fact, readers agree with the verdict, a current verdict's `upstream` lists the facts in other
roots it rests on with their bases. Each verdict is `current` (its `basis` is the fact's basis
hash now), `stale`, `upstream-stale` (only facts in other roots changed), `unverified` (no
verdict) or `unknown` (the basis cannot be established: never current). A current FAIL is an
error; the others, and a `critical` fact whose current verdict has no `readers`, are warnings,
and errors under `--require-verified pr` (pull requests: every one) or `--require-verified main`
(every one but upstream-stale, which stays a warning; D19). Freshness findings are for checked
roots only.

`status` runs the same check and prints, per spec file of the checked roots, its record and
summary and each fact's freshness; `--stale` lists only what a re-verification has to cover
(every fact not current, and current critical facts without a second reader). `--json` prints
`{"ok", "roots", "errors", "warnings", "specs": [{"path", "root", "spec", "record", "state",
"facts": [{"key", "ref", "kind", "status", "verdict", "carried", "basis", "recorded",
"upstream", "changed", "reason", "second_reader"}]}], "findings"}` (the check's findings, as
for `check`): `basis` is the fact's basis hash now and
`upstream` the map a verdict reached now records (null when the basis is unknown). Exit 0 when
the check found no error, 1 when it did (the report is printed either way).

`resolve` checks source anchors and licenses at immutable pins, and document hashes when
`--docs-dir` supplies bytes as DIR/NAME. `--repo` binds a named entry to the top level of a
local checkout; unbound entries are fetched over HTTPS. Only size/time limits skip anchors;
the summary counts skips explicitly, and a fully skipped run exits 0. `show` also displays
facts beside cited source lines, escaping terminal control characters. Search anchors check
scope existence only; their prose is never executed.

`drift` compares one cited entry with a full lowercase commit id (40 or 64 hex digits).
`--pin` is required when several entries are cited. `--rewrite` moves the pin, updates unique
moved ranges and marks changed anchors stale while preserving comments and layout. Changed
search scopes and operational read failures refuse rewriting and retain the original file.

`inventory` reads the selected repos entry's closed files at its immutable commit and compares
register offsets and field masks with C constants. Reports are exact structured values;
unsupported or ambiguous expressions are reported as unknown with reasons and fail.
Mismatches, conflicting spec values and names
absent from headers fail; omitted header names also fail under `--strict`. Several repos entries
require `--pin`. No author prose counts as coverage. Only a bounded subset of integer constant
expressions is supported (literals, textual object macros, arithmetic, shifts, BIT and GENMASK
when the headers do not define them). Function-like macros are unknown; enum members are
reported, with implicit values known only when all preceding members are known.

`check <file.facts.yaml> --root <target>` checks investigator output with the same citation and
license rules, without placing it in a spec root or requiring verification records. It reads
the target marker only. Context, stub and verification options are not available in this mode.

Exit status: 0 all valid (validate) or no error (check/resolve/show/drift; warnings allowed); 1 a file invalid or a
check error; 2 usage; 3 a pinned dependency missing or at another version, or a root without
board-specs.yaml; 100 an internal error in spec.py (the files were not judged).

`check` also rejects raw HTML, disallowed links (including images), link reference definitions,
footnotes, nesting deeper than 16, headings and unclosed fences in CommonMark author fields,
including verification-record notes.
Format 1 tag spellings in claims and prose are warnings.
`render` runs that check and repeats containment before emitting a view. Generated text is
literal. In the Markdown view author Markdown is verbatim in labeled top-level fences with no info string.
Generated syntax and values that GFM might autolink use code spans. Without
explicit `--source-commit` and `--tool-commit` values the banner states that commits are
unavailable and includes each checked YAML's SHA256. Both arguments require 40 lowercase hex
characters; no Git subprocess runs. Repeat `--source-commit ROOT=SHA` once per rendered root
directory; a bare SHA is accepted only when one root is rendered. Each omitted root is
unavailable. `--tool-commit` identifies the rendering tool separately.
`--merged` includes context files for the selected ids, ordered by layer; without it each
checked file gets its own view. Errors print diagnostics instead of a partial view; `--json`
returns `{"ok", "markdown", "findings"}` for md or `{"ok", "html", "findings"}` for html
(the view is null on error). HTML renders author CommonMark separately in each field with raw
HTML disabled, images as links and checked hrefs only. Only structured fields produce badges.
The reusable publishing workflow and local build/verify helper live under `spec-format/ci/`.
"""


class Usage(Exception):
    """A usage error: exit 2."""


class Precondition(Exception):
    """A missing precondition: exit 3."""


_MARKER = re.compile(
    r"python_(full_)?version\s*(<=|>=|==|!=|<|>)\s*'([0-9]+(?:\.[0-9]+){0,2})'")


def _marker_applies(marker: str) -> bool:
    """Evaluate a requirements marker. Only `python_version` and `python_full_version`
    compared with a version are understood, as three-part versions padded with zeros
    (python_version is the running major.minor.0). Anything else raises ValueError: spec.py
    never guesses whether a pin applies."""
    m = _MARKER.fullmatch(marker.strip())
    if not m:
        raise ValueError(f"requirements marker not understood: {marker.strip()!r}")
    want = tuple(int(x) for x in m.group(3).split("."))
    want = want + (0,) * (3 - len(want))
    have = tuple(sys.version_info[:3]) if m.group(1) else tuple(sys.version_info[:2]) + (0,)
    return {"<": have < want, "<=": have <= want, ">": have > want, ">=": have >= want,
            "==": have == want, "!=": have != want}[m.group(2)]


def pinned_versions() -> dict[str, str]:
    """The `name==version` pins of requirements.txt that apply to this Python, by normalized
    distribution name."""
    pins = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)\s*(?:;([^\\]*))?", line)
        if m and (m.group(3) is None or _marker_applies(m.group(3))):
            pins[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = m.group(2)
    return pins


def check_dependencies() -> list[str]:
    """Problems with the pinned dependencies; empty when every pin that applies is installed
    at its version and the three direct ones import."""
    import importlib
    import importlib.metadata

    try:
        pins = pinned_versions()
    except OSError as exc:
        return [f"cannot read {REQUIREMENTS}: {exc}"]
    except ValueError as exc:
        return [f"{REQUIREMENTS.name}: {exc}"]
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
    for dist, want in sorted(pins.items()):
        if dist in DIRECT:
            continue
        try:
            have = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{dist} is not installed (pinned {want})")
            continue
        if have != want:
            problems.append(f"{dist} is {have}, pinned {want}")
    return problems


def _strict_json(path: Path):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError(f"duplicate key {k!r}")
            out[k] = v
        return out

    def constant(name):
        raise ValueError(f"{name} is not JSON")

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=constant)


class Finding:
    def __init__(self, path, line, column, message):
        self.path, self.line, self.column, self.message = str(path), line, column, message

    def key(self):
        return (self.path, self.line, self.column, self.message)

    def as_dict(self):
        return {"path": self.path, "line": self.line, "column": self.column,
                "message": self.message}

    def __str__(self):
        return visible_name(f"{self.path}:{self.line}:{self.column}: {self.message}")


# --- schemas -------------------------------------------------------------------------------

_DEFAULT_EXTENSION = {
    "$id": EXTENSION_URN,
    "$comment": "message: a source-observed entry needs the extension's schema fragment; "
    "pass --root with a root marker whose extensions names it (D15)",
    "not": {},
}

_FRAGMENT_KEYS = {"$comment", "title", "description", "type", "properties", "required"}
# Field names that carry a citation in the core format. An extension may not declare them at any
# depth: the license gate reads citations only from core fields, so an extension entry naming a
# repository or a path would cite gated content no gate sees (orchestrator decision, SF2-2 review).
_CITATION_FIELDS = {"repo", "path", "doc", "anchors", "lines", "symbol", "node", "url"}
# The keywords a fragment may use below its top (user decision 2026-10-08, SF2-2 review round 2):
# plain properties and value constraints only. Anything that admits fields by pattern, by
# condition or by combination (patternProperties, dependentSchemas, if/then/else, anyOf, ...),
# or a schema-valued additionalProperties or unevaluatedProperties, could admit a field whose
# name no check sees; with plain properties only, the citation-name ban holds by construction.
_FRAGMENT_PLAIN = {
    "$comment", "title", "description", "type", "properties", "required", "enum", "const",
    "pattern", "format", "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "multipleOf", "minItems", "maxItems", "uniqueItems", "items",
    "minProperties", "maxProperties", "additionalProperties", "unevaluatedProperties",
}
_FRAGMENT_PROPERTY = re.compile(r"[a-z][a-z0-9_]*")  # used with fullmatch
# Draft 2020-12's keywords. A fragment may use no other: a keyword the validator does not know
# (draft-07's `dependencies`, a typo) would be a silently ignored constraint.
_KEYWORDS_2020_12 = {
    "$schema", "$id", "$ref", "$anchor", "$dynamicRef", "$dynamicAnchor", "$vocabulary",
    "$comment", "$defs", "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
    "dependentSchemas", "prefixItems", "items", "contains", "properties", "patternProperties",
    "additionalProperties", "propertyNames", "unevaluatedItems", "unevaluatedProperties",
    "type", "enum", "const", "multipleOf", "maximum", "exclusiveMaximum", "minimum",
    "exclusiveMinimum", "maxLength", "minLength", "pattern", "maxItems", "minItems",
    "uniqueItems", "maxContains", "minContains", "maxProperties", "minProperties", "required",
    "dependentRequired", "format", "contentEncoding", "contentMediaType", "contentSchema",
    "title", "description", "default", "deprecated", "readOnly", "writeOnly", "examples",
}


def _pattern_problem(pattern: str) -> str | None:
    """Why a fragment's regex would not mean the same in Python and ECMA-262, or None.

    Refused: an unescaped `$` outside a character class (Python's `$` also matches before a
    final newline), `\\Z` (an end anchor in Python, a literal Z in ECMA-262) and `(?#...)`
    comments (Python only, and they hide what the scan reads). A `]` first in a class is
    literal, as in `[]$]`.
    """
    if "(?#" in pattern:
        return "uses a (?#...) comment, which ECMA-262 does not have"
    escaped = in_class = False
    class_start = -1
    for at, ch in enumerate(pattern):
        if escaped:
            escaped = False
            if ch == "Z":
                return "uses \\Z, an end anchor only in Python; end it with (?![\\s\\S])"
        elif ch == "\\":
            escaped = True
        elif in_class:
            first = at == class_start + 1 or (at == class_start + 2
                                              and pattern[class_start + 1] == "^")
            if ch == "]" and not first:
                in_class = False
        elif ch == "[":
            in_class, class_start = True, at
        elif ch == "$":
            return ("uses $, which in Python also matches before a final newline; end it "
                    "with (?![\\s\\S])")
    return None


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


_SCHEMA_ONE = {"items", "contains", "not", "if", "then", "else", "propertyNames",
               "additionalProperties", "unevaluatedProperties", "unevaluatedItems",
               "additionalItems", "contentSchema"}
_SCHEMA_MAP = {"properties", "patternProperties", "dependentSchemas", "$defs", "definitions"}
_SCHEMA_LIST = {"allOf", "anyOf", "oneOf", "prefixItems"}


def core_fields(schemas: dict[str, dict]) -> set[str]:
    """Every field a core support class declares, and `class`."""
    names = {"class"}
    for branch in schemas["spec"]["$defs"]["support"]["allOf"]:
        names.update(branch.get("then", {}).get("properties", {}))
    return names


def check_fragment(fragment, where: Path, reserved: set[str]) -> list[str]:
    """Problems with an extension's schema fragment; it may only add fields (D15).

    The fragment is composed into the support entry with the core schema's
    unevaluatedProperties still in force, so at its top it may declare only type, properties
    and required: no keyword that would mark every property evaluated (additionalProperties,
    patternProperties, unevaluatedProperties) or combine schemas. Anywhere in it, no keyword
    that reaches outside it ($ref, $dynamicRef, $id, $anchor, $defs, ...). It may not declare a
    field a core class declares (anchors, url, doc, ...), since tools read those by name.
    """
    import jsonschema

    if not isinstance(fragment, dict):
        return [f"{where}: a schema fragment is a JSON object"]
    problems = []
    try:
        jsonschema.Draft202012Validator.check_schema(fragment)
    except jsonschema.SchemaError as exc:
        problems.append(f"{where}: not a valid JSON Schema: {exc.message}")
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
        if name in reserved:
            problems.append(f"{where}: field name {name!r} is a core field; choose another")
        elif not _FRAGMENT_PROPERTY.fullmatch(name):
            problems.append(f"{where}: field name {name!r} not allowed (lowercase letters, "
                            f"digits and _)")
    required = fragment.get("required", [])
    if (not isinstance(required, list) or not all(isinstance(r, str) for r in required)
            or any(r not in props for r in required)):
        problems.append(f"{where}: required lists only fields the fragment declares")

    def walk(schema, trail):
        """Visit every subschema; keywords in schema position only, never data."""
        if isinstance(schema, bool):
            return
        if not isinstance(schema, dict):
            return  # check_schema reports it
        for key, value in schema.items():
            at = "/".join(trail + (key,))
            if key.startswith("$") and key != "$comment":
                problems.append(f"{where}: {key} at {at} not allowed")
            elif key not in _KEYWORDS_2020_12:
                problems.append(f"{where}: {key} at {at} is not a draft 2020-12 keyword")
            elif key not in _FRAGMENT_PLAIN:
                problems.append(f"{where}: {key} at {at} not allowed: a fragment uses plain "
                                f"properties and value constraints only")
            elif key in ("additionalProperties", "unevaluatedProperties") and not isinstance(
                    value, bool):
                problems.append(f"{where}: {key} at {at} not allowed with a schema value; "
                                f"write true or false")
            elif key == "items" and not isinstance(value, dict):
                problems.append(f"{where}: items at {at} must be one schema")
            if key == "pattern" and isinstance(value, str) and _pattern_problem(value):
                problems.append(f"{where}: pattern at {at} {_pattern_problem(value)}")
            if key == "patternProperties" and isinstance(value, dict):
                for name in value:
                    if _pattern_problem(name):
                        problems.append(f"{where}: pattern {name!r} at {at} "
                                        f"{_pattern_problem(name)}")
            if key == "properties" and isinstance(value, dict):
                for name in value:
                    if name in _CITATION_FIELDS:
                        problems.append(f"{where}: field name {name!r} at {at} carries a "
                                        f"citation in the core format; an extension may not "
                                        f"declare it (the license gate would not see it)")
            if key in _SCHEMA_ONE:
                walk(value, trail + (key,))
            elif key in _SCHEMA_MAP and isinstance(value, dict):
                for name, sub in value.items():
                    walk(sub, trail + (key, name))
            elif key in _SCHEMA_LIST and isinstance(value, list):
                for i, sub in enumerate(value):
                    walk(sub, trail + (key, str(i)))

    walk(fragment, ())
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


def _branch_names(schema, instance, resolve, is_valid, depth=0) -> set:
    """Property names the schema declares for this instance: its own properties and those of
    the in-place branches that apply (every allOf branch and $ref; the anyOf and oneOf branches
    the instance satisfies; then or else as its if decides). A kind's or a class's branch
    counts only when the instance is of that kind."""
    names: set = set()
    if not isinstance(schema, dict) or depth > 32:
        return names
    props = schema.get("properties")
    if isinstance(props, dict):
        names.update(props)
    for sub in schema.get("allOf", []):
        names |= _branch_names(sub, instance, resolve, is_valid, depth + 1)
    for key in ("anyOf", "oneOf"):
        for sub in schema.get(key, []):
            if is_valid(sub, instance):
                names |= _branch_names(sub, instance, resolve, is_valid, depth + 1)
    if "$ref" in schema:
        names |= _branch_names(resolve(schema["$ref"]), instance, resolve, is_valid, depth + 1)
    if "if" in schema:
        branch = "then" if is_valid(schema["if"], instance) else "else"
        names |= _branch_names(schema.get(branch), instance, resolve, is_valid, depth + 1)
    return names


def schema_findings(validator, data, loaded, path: Path, resolve) -> list[Finding]:
    """Findings for every schema error, each placed at its line and column.

    An unknown-key report from unevaluatedProperties has a cascade: when a value inside a
    kind's or class's branch fails, the branch's annotations are dropped and every key it
    declared reads as unevaluated. Such a key is left out only when the branch that applies to
    this object declares it and another error lies at or below the object; any other key is
    reported. additionalProperties has no cascade and is always reported.
    """
    from jsonschema.exceptions import best_match

    unknown = ("unevaluatedProperties", "additionalProperties")
    errors = list(validator.iter_errors(data))
    # Errors that can explain a cascade at path P: any other error at or below P, and an
    # unknown-key error strictly below P (its own branch failed, and so did P's).
    others = [(tuple(e.absolute_path), e.validator in unknown) for e in errors]
    out = []
    for error in errors:
        at = tuple(error.absolute_path)
        if "propertyNames" in error.absolute_schema_path and isinstance(error.instance, str):
            key = error.instance
            m = loaded.mark(at + (key,), key=True)
            out.append(Finding(path, m.line, m.column,
                               f"{_where(at)}: key {key!r}: {_custom_message(error) or _short(error)}"))
            continue
        if error.validator in unknown and isinstance(error.instance, dict):
            shadowed = any(p[:len(at)] == at and (len(p) > len(at) or not is_unknown)
                           for p, is_unknown in others if (p, is_unknown) != (at, True))
            own = (_branch_names(error.schema, error.instance, resolve,
                                 lambda sub, inst: validator.evolve(schema=sub).is_valid(inst))
                   if error.validator == "unevaluatedProperties" and shadowed else set())
            for key in error.instance:
                if repr(key) not in error.message:
                    continue
                if key in own:
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

def _bad_json_string(node) -> str | None:
    """The first refused character in any key or string of parsed JSON (escapes decoded)."""
    import specload

    if isinstance(node, str):
        bad = specload.bad_character(node)
        return f"a string holding {bad}" if bad else None
    items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(
        node, list) else ()
    for k, v in items:
        found = _bad_json_string(k) if isinstance(k, str) else None
        found = found or _bad_json_string(v)
        if found:
            return found
    return None


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
    import specload

    try:
        fragment = _strict_json(target)
        specload.check_text(target, target.read_text(encoding="utf-8"))
    except specload.LoadError as exc:
        findings.append(Finding(marker, 1, 1, f"extensions: {rel}:{exc.line}:{exc.column}: "
                                              f"{exc.problem}"))
        return None
    except (OSError, ValueError) as exc:
        findings.append(Finding(marker, 1, 1, f"extensions: {rel}: {exc}"))
        return None
    bad = _bad_json_string(fragment)
    if bad:
        findings.append(Finding(marker, 1, 1, f"extensions: {rel}: {bad}"))
        return None
    problems = check_fragment(fragment, Path(rel), core_fields(load_schemas()))
    for p in problems:
        findings.append(Finding(marker, 1, 1, f"extensions: {p}"))
    return None if problems else fragment


def validate_file(path: Path, schemas, extension, findings: list[Finding], *, raw=None):
    """Load and schema-check one file: (valid, schema kind, Loaded or None)."""
    import jsonschema

    import specload

    kind = schema_kind(path)
    before = len(findings)
    try:
        loaded = specload.load_strict_marked(path) if raw is None else specload.load_strict_marked(path, raw)
    except specload.LoadError as exc:
        findings.append(Finding(path, exc.line, exc.column, exc.problem))
        return False, kind, None
    except OSError as exc:
        findings.append(Finding(path, 1, 1, f"cannot read the file: {exc.strerror or exc}"))
        return False, kind, None
    if kind == "root":
        extension = None  # a marker is validated with its own fragment, below
    registry = registry_for(schemas, extension)
    validator = jsonschema.Draft202012Validator(schemas[kind], registry=registry)
    def resolve(ref: str):
        if ref == EXTENSION_URN:
            return extension if extension and kind != "root" else _DEFAULT_EXTENSION
        doc, _, pointer = ref.partition("#")
        node = schemas[kind]
        if doc:
            node = next((v for v in schemas.values() if v["$id"].endswith("/" + doc)), {})
        for part in pointer.strip("/").split("/") if pointer.strip("/") else []:
            node = node.get(part, {}) if isinstance(node, dict) else {}
        return node

    findings.extend(schema_findings(validator, loaded.data, loaded, path, resolve))
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
    return len(findings) == before, kind, loaded


def read_root(root: Path, schemas, findings: list[Finding]) -> dict | None:
    marker = root / MARKER
    if not marker.is_file():
        raise Usage(f"--root {root}: no {MARKER} there")
    ok, _, _ = validate_file(marker, schemas, None, findings)
    if not ok:
        return None
    import specload

    return load_extension(marker, specload.load_strict(marker), [])


def cmd_check(args) -> tuple[int, dict]:
    checker = _run_check(args, stubs=args.stub, stubs_from=args.stubs_from,
                         require_verified=args.require_verified)
    ordered = _ordered(checker.findings)
    errors = sum(1 for f in ordered if f.level == "error")
    warnings = len(ordered) - errors
    summary = (f"{len(checker.roots)} root(s), {len(checker.files)} spec file(s), "
               f"{checker.stubs} stub(s): {errors} error(s), {warnings} warning(s)")
    return (EXIT_INVALID if errors else EXIT_OK), {
        "ok": not errors,
        "roots": [{"path": str(r.given), "name": r.name, "layer": r.layer, "context": r.context}
                  for r in checker.roots],
        "specs": len(checker.files),
        "stubs": checker.stubs,
        "verification": _counts(checker),
        "findings": [f.as_dict() for f in ordered],
        "_text": [str(f) for f in ordered] + [summary],
    }


def _ordered(findings) -> list:
    uniq = {(f.path, f.line, f.column, f.level, f.message): f for f in findings}
    return sorted(uniq.values(), key=lambda f: (f.path, f.line, f.column, f.message))


def _counts(checker) -> dict:
    import records

    counts = dict.fromkeys(records.STATUSES, 0)
    for entry in checker.status:
        if not entry["file"].root.context:
            for row in entry["rows"]:
                counts[row["status"]] += 1
    return counts


def _run_check(args, **extra):
    import types

    import speccheck

    api = types.SimpleNamespace(validate_file=validate_file, load_extension=load_extension)
    try:
        if getattr(args, "root", None) is not None:
            return speccheck.check_facts(api, load_schemas(), args.roots, args.root,
                                         require_license=args.require_license,
                                         public_skills=args.public_skill,
                                         context_roots=args.context_root, **extra)
        return speccheck.check(
            api, load_schemas(), args.roots, context_roots=args.context_root,
            require_license=args.require_license, public_skills=args.public_skill, **extra)
    except speccheck.UsageError as exc:
        raise Usage(str(exc)) from None
    except speccheck.PreconditionError as exc:
        raise Precondition(str(exc)) from None


def cmd_status(args) -> tuple[int, dict]:
    import records

    checker = _run_check(args)
    ordered = _ordered(checker.findings)
    errors = sum(1 for f in ordered if f.level == "error")
    warnings = len(ordered) - errors
    specs, text = [], []
    for entry in checker.status:
        f = entry["file"]
        if f.root.context:
            continue
        rows = entry["rows"]
        if args.stale:
            rows = [r for r in rows if r["status"] != "current" or r["second_reader"] == "missing"]
            if not rows:
                continue
        rel = records._rel(f.root, f.path)
        specs.append({"path": str(f.path), "root": f.root.label, "spec": f.spec_id,
                      "record": entry["record"], "state": entry["state"], "facts": rows})
        summary = "no record"
        if entry["state"] == "ok":
            s = f.record_loaded.data["summary"]
            summary = entry["record"] + ": " + ", ".join(f"{k} {s[k]}" for k in records.SUMMARY)
        elif entry["state"] != "none":
            summary = f"{entry['record']}: {entry['state']}"
        text.append(f"{f.root.label}:{rel} ({f.spec_id}): {summary}")
        for r in rows:
            notes = [r["verdict"]] if r["verdict"] else []
            if r["carried"]:
                notes.append("carried")
            if r["second_reader"] == "missing":
                notes.append("needs a second reader")
            if r["changed"]:
                notes.append("upstream changed: " + ", ".join(r["changed"]))
            if r["reason"]:
                notes.append(r["reason"])
            text.append(f"  {r['status']:<15} {r['key']}" + (f"  ({'; '.join(notes)})"
                                                               if notes else ""))
    tally = dict.fromkeys(records.STATUSES, 0)
    for spec in specs:
        for r in spec["facts"]:
            tally[r["status"]] += 1
    text += [str(f) for f in ordered if f.level == "error"]  # what the exit status rests on
    text.append(", ".join(f"{n} {k}" for k, n in tally.items())
                + f"; the check found {errors} error(s), {warnings} warning(s)")
    return (EXIT_INVALID if errors else EXIT_OK), {
        "ok": not errors,
        "roots": [{"path": str(r.given), "name": r.name, "layer": r.layer, "context": r.context}
                  for r in checker.roots],
        "errors": errors,
        "warnings": warnings,
        "specs": specs,
        "findings": [f.as_dict() for f in ordered],
        "_text": text,
    }


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
        ok, kind, _ = validate_file(p, schemas, extension, findings)
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


def commit_arg(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise argparse.ArgumentTypeError("commit must be 40 lowercase hex characters")
    return value


def source_commit_arg(value):
    commit_arg(value.rsplit("=", 1)[-1])
    return value


def build_parser() -> argparse.ArgumentParser:
    sys.path.insert(0, str(HERE))
    import drift
    import resolve
    import inventory
    import migrate

    parser = _Parser(
        prog="spec.py", description=__doc__.splitlines()[0], allow_abbrev=False,
        epilog="exit status: 0 valid; 1 invalid; 2 usage; 3 a pinned dependency missing; 100 internal",
    )
    parser.add_argument("--skill", action="store_true", help="print the usage skill and exit")
    sub = parser.add_subparsers(dest="command")
    v = sub.add_parser("validate", help="load and schema-check files", allow_abbrev=False)
    v.add_argument("files", nargs="+", type=Path)
    v.add_argument("--root", type=Path, help="a root whose marker names extension fragments")
    v.add_argument("--json", action="store_true", help="one JSON object on stdout")
    c = sub.add_parser("check", help="check spec roots: names, composition, references, the "
                                     "license gate", allow_abbrev=False)
    c.add_argument("roots", nargs="+", type=Path, help="spec root directories")
    c.add_argument("--root", type=Path, help="target root for checking standalone facts files")
    c.add_argument("--context-root", action="append", default=[], type=Path,
                   help="a further root read so references and overlays resolve; findings in "
                        "its own files are warnings")
    c.add_argument("--require-license", action="store_true",
                   help="also gate repos entries no anchor or notice names")
    c.add_argument("--public-skill", action="append", default=[],
                   help="a skill a public root's tools may name in via:")
    c.add_argument("--stub", action="append", default=[], type=Path, help="a stub SKILL.md")
    c.add_argument("--stubs-from", action="append", default=[], type=Path,
                   help="a skills directory; every */SKILL.md calling itself a stub is checked")
    c.add_argument("--require-verified", choices=("pr", "main"), default=None,
                   help="stale, unverified and unknown verdicts are errors; upstream-stale too "
                        "under pr, a warning under main (D19)")
    c.add_argument("--json", action="store_true", help="one JSON object on stdout")
    st = sub.add_parser("status", help="each verdict's freshness, per spec file",
                        allow_abbrev=False)
    st.add_argument("roots", nargs="+", type=Path, help="spec root directories")
    st.add_argument("--context-root", action="append", default=[], type=Path,
                    help="a further root read so references and overlays resolve")
    st.add_argument("--require-license", action="store_true",
                    help="as for check (it decides which roots are trusted)")
    st.add_argument("--public-skill", action="append", default=[],
                    help="as for check")
    st.add_argument("--stale", action="store_true",
                    help="only facts a re-verification has to cover")
    st.add_argument("--json", action="store_true", help="one JSON object on stdout")
    rd = sub.add_parser("render", help="generate a Markdown view or HTML viewer", allow_abbrev=False)
    rd.add_argument("roots", nargs="+", type=Path, help="spec root directories")
    rd.add_argument("--context-root", action="append", default=[], type=Path)
    rd.add_argument("--require-license", action="store_true")
    rd.add_argument("--public-skill", action="append", default=[])
    rd.add_argument("--spec", help="render only this spec id")
    rd.add_argument("--merged", action="store_true", help="include context bases and overlays")
    rd.add_argument("--with-status", action="store_true", help="include verdict and freshness")
    rd.add_argument("--source-commit", type=source_commit_arg, action="append",
                    help="ROOT=SHA, once per rendered root; bare SHA only with one root")
    rd.add_argument("--tool-commit", type=commit_arg, help="driver-lab commit (40 lowercase hex)")
    rd.add_argument("--format", required=True, choices=("md", "html"))
    rd.add_argument("--json", action="store_true", help="one JSON object on stdout")
    resolve.register(sub)
    drift.register(sub)
    inventory.register(sub)
    migrate.register(sub)
    return parser


def _failure(kind: str, messages: list[str], command: str | None = None,
             render_format: str = "md") -> str:
    """The --json object for a run that judged nothing (usage, precondition, internal)."""
    if command == "render":
        return json.dumps({"ok": False, "error": kind,
                           "html" if render_format == "html" else "markdown": None,
                           "findings": [{"message": m} for m in messages]}, sort_keys=True)
    if command == "status":
        return json.dumps({"ok": False, "error": kind, "roots": [], "errors": len(messages),
                           "warnings": 0, "specs": [],
                           "findings": [{"path": "", "line": 0, "column": 0, "level": "error",
                                         "message": m} for m in messages]}, sort_keys=True)
    if command == "check":
        return json.dumps({"ok": False, "error": kind, "roots": [], "specs": 0, "stubs": 0,
                           "verification": {},
                           "findings": [{"path": "", "line": 0, "column": 0, "level": "error",
                                         "message": m} for m in messages]}, sort_keys=True)
    return json.dumps({"ok": False, "error": kind, "files": [],
                       "findings": [{"path": "", "line": 0, "column": 0, "message": m}
                                    for m in messages]}, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    want_json = any(a == "--json" or a.startswith("--json=") for a in argv)
    command = next((a for a in argv if not a.startswith("-")), None)
    render_format = "html" if ("--format=html" in argv or any(
        a == "--format" and argv[i + 1:i + 2] == ["html"] for i, a in enumerate(argv))) else "md"
    parser = build_parser()

    def fail(kind: str, code: int, messages: list[str], hint: str = "") -> int:
        if want_json:
            print(_failure(kind, messages, command, render_format))
        else:
            label = {"usage": "usage error", "precondition": "missing precondition"}.get(
                kind, "internal error")
            for m in messages:
                if command in ("validate", "resolve", "show", "drift", "inventory"):
                    import resolve

                    m = resolve.display_line(m)
                print(visible_name(f"{label}: {m}"), file=sys.stderr)
            if hint:
                print(hint, file=sys.stderr)
        return code

    try:
        args = parser.parse_args(argv)
    except Usage as exc:
        return fail("usage", EXIT_USAGE, [str(exc)])
    if args.skill:
        print(SKILL, end="")
        return EXIT_OK
    if args.command is None:
        return fail("usage", EXIT_USAGE,
                    ["name a subcommand: validate, check, status, render, resolve, show, drift, migrate"])

    try:
        problems = check_dependencies()
    except Exception as exc:  # pylint: disable=broad-except
        import traceback

        traceback.print_exc(file=sys.stderr)
        return fail("internal", EXIT_INTERNAL, [f"{type(exc).__name__}: {exc}"])
    if problems:
        return fail("precondition", EXIT_PRECONDITION, problems,
                    "install: pip install --require-hashes -r skills/spec-format/requirements.txt")
    sys.path.insert(0, str(HERE))
    try:
        import render_md
        import render_html

        handler = getattr(args, "handler", None) or {
            "check": cmd_check, "status": cmd_status, "validate": cmd_validate,
            "render": lambda a: (render_html if a.format == "html" else render_md).command(
                sys.modules[__name__], a)}[args.command]
        code, result = handler(args)
    except Usage as exc:
        return fail("usage", EXIT_USAGE, [str(exc)])
    except Precondition as exc:
        return fail("precondition", EXIT_PRECONDITION, [str(exc)])
    except Exception as exc:  # pylint: disable=broad-except
        # A bug, not a verdict on the files: say so, in JSON when JSON was asked for.
        import traceback

        traceback.print_exc(file=sys.stderr)
        return fail("internal", EXIT_INTERNAL, [f"{type(exc).__name__}: {exc}"])
    text = result.pop("_text")
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif args.command in ("check", "status", "render") or hasattr(args, "handler"):
        for line in text:
            # resolve, show and drift escape their own lines (resolve.display_line).
            if (args.command == "render" and code == EXIT_OK) or hasattr(args, "handler"):
                print(line)
            else:
                print(visible_name(line))
    else:
        for line in text:
            print(line)
        bad = sum(1 for f in result["files"] if not f["valid"])
        print(f"{len(result['files'])} file(s), {bad} invalid, {len(text)} finding(s)")
    return code


if __name__ == "__main__":
    sys.modules["spec"] = sys.modules[__name__]
    sys.exit(main())
