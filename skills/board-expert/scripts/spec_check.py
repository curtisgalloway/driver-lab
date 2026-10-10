#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Check board specs against FORMAT-1.md.

A root is a directory holding ``board-specs.yaml``; every ``*.spec.md``
below it is a spec (or an overlay, when its frontmatter has ``overlays:``).
Give one or more roots; references (``parts``, ``instances[].ip``,
``overlays``) resolve across all of them together, the way the reader sees
them.

What fails (exit 1):

  * frontmatter that does not parse, or is missing a key its kind requires
  * an unknown ``kind`` or root ``layer``; a duplicate ``id``
  * a ``parts`` entry, an ``instances[].ip``, an ``overlays`` target, or a
    ``variant_of`` that resolves to nothing across the given roots
  * an ``instances[]`` row whose ``reg`` is not an integer or null, or whose
    ``irq`` is not null or a mapping with ``kind`` (SPI | PPI | extended)
    and an integer ``number``; an ``extended`` irq without ``parent``, or a
    SPI/PPI irq with one
  * a ``variants[]`` entry without a ``name``, or with a ``tag`` that is not
    a provenance class
  * an ``id``, ``aliases[]``, ``parts[]``, ``variant_of``, or ``overlays``
    value that is not a normalized id (``^[a-z0-9][a-z0-9-]*$``); a
    ``triggers`` or ``not_triggers`` that is not a list of strings
  * a ``resources.series`` entry with ``cite: true``; a ``fetch:`` value
    other than ok | blocked | truncated | partial, or a ``fetch_via:`` that
    is not a string; a ``status:`` other than unmerged | merged |
    superseded, on an entry or on one of its ``files``
  * under a ``public`` root: any ``access: internal`` entry, or a ``via:``
    naming a skill not passed with ``--public-skill``
  * a root marker ``license:`` that is not an SPDX expression, or an
    ``accepts:`` that is not a list of single SPDX identifiers; with
    ``--require-license``, a marker without either field
  * a ``resources.repos`` entry whose ``license:`` is not an SPDX expression;
    in a root whose marker declares ``accepts:``, a repos entry with no
    ``license:`` at all; with ``--require-license``, a repos entry whose
    ``license:`` the root's ``accepts:`` does not accept (the board-spec license
    gate: ``A OR B`` passes when either side is accepted, ``A AND B`` only when
    both are, as in ``anchor_check.py --root``)
  * an ``ip`` spec with no ``docs`` entry marked ``cite: true``
  * a fact bullet that does not END with its tag clause (one or more
    ``[tag]``, each optionally followed by a parenthetical citation, then at
    most one closing ``TODO (verify on hardware)`` sentence).  Only the tail
    clause is examined: a tag name mentioned in the prose is not a tag and is
    ignored by every rule below.  Code comes from one CommonMark parse
    (peripheral-spec's ``mdtokens.py``, shared with ``anchor_check.py``):
    nothing in a code block is a tag, a code span holding exactly one tag (or
    anchor, or the TODO marker) is that token, and any longer code span is
    prose.  In the tail every tag token counts, nested ones included, and
    every ``[src]`` needs anchors in its own parenthetical.  A tag or anchor
    kind not in its canonical case, outside code, is an error, and so is a
    code fence that never closes.  A bullet whose text, after an optional
    bold lead-in, starts with ``TODO (verify on hardware)`` is a gap and
    needs no tag
  * a tail clause with ``[source-observed]``, ``[press]``, ``[inference]``
    or ``[emulated]`` but no ``TODO (verify on hardware)``; a ``[doc]``,
    ``[DT]``, ``[rtl]``, ``[inference]`` or ``[emulated]`` in the tail not
    followed by a parenthetical naming its source (for ``[DT]``: the file,
    and its origin when it is a decompiled blob rather than a source
    ``.dts``; the origin may be the ``name`` of a ``resources.repos`` entry
    -- for ``[inference]``: its premises and the derivation, since an
    inference is supported by an argument rather than by a citation -- for
    ``[emulated]``: the device model, its version and the run IDs, the way
    ``[hardware]`` names the board); a tail clause whose only tag is
    ``[emulated]``, since a model observation is never the sole authority
    for a fact: another class stands beside it, or the observation is a
    premise of an ``[inference]``
  * a ``[src]`` in the tail not followed by a parenthetical holding at least
    one ``[src:<repo>: path:L1-L2 (symbol)]`` anchor (peripheral-spec's
    anchor grammar, parsed by its ``anchor_check.py``); anywhere in the body,
    a ``[src:]`` anchor that is malformed, names no repo, names a repo the
    spec's own ``resources.repos`` does not list, or names one whose ``ref``
    is not a full commit id, that has no ``license:``, or whose license the
    root's ``accepts:`` does not accept (always, not only under
    ``--require-license``; a root with no ``accepts:``, or ``accepts: []``,
    accepts no ``[src]``); a ``[src:]`` anchor broken across lines or by
    spaces, or with no ``]`` before the end of its list item or paragraph
  * an unsubstituted template placeholder (``<...>`` starting with a letter,
    outside backtick code spans, not a URL or a message id) in a spec's
    frontmatter or body, or in a stub
  * (a finding in a ``--context-root`` is reported as a warning instead: such a
    root is read so that overlays and parts resolve, and fails in its own checks)
  * a stub (``--stub PATH``, or every stub found by ``--stubs-from DIR``: a
    ``*/SKILL.md`` whose frontmatter says "stub over") whose ``spec: <id>``
    does not resolve
  * a verification record (``<root>/resources/<name>.verify.md``, where
    ``<name>`` is the spec file's name without ``.spec.md``, overlays included;
    written by the ``spec-verifier`` skill) whose frontmatter is malformed,
    whose ``spec_file`` is not that spec's path relative to the root, or which
    is current and whose ``summary.fail`` is not zero (a stale record reports
    stale, whatever its counts); two spec files in one root that would share a
    record; with ``--require-verified``, also a spec with no record or a record
    whose ``spec_sha256`` no longer matches
  * a ``--context-root`` that is, contains, or sits inside a checked root, or
    that holds or is reached through a symbolic link (usage error, exit 2); in
    a checked root, any symbolic link (file or directory), or the root being or
    being reached through one

What warns (reported, exit stays 0):

  * a root marker without ``license:`` or without ``accepts:`` (markers
    written before these fields still load), unless ``--require-license``
    makes it an error
  * two overlays for the same id in the same layer
  * a part whose ``cache`` differs from its board's
  * a spec with no verification record ("unverified"), or one whose record
    was written for an older version of the file ("verification stale"),
    unless ``--require-verified`` makes these errors. A stale record with
    FAIL verdicts reports stale only: its verdicts were for another version
  * a record under ``resources/`` that belongs to no spec file in its root
    (for example one left under the overlaid id's name)

Markdown is read with markdown-it-py, pinned to 4.2.0 through peripheral-spec's
``mdtokens.py``: run as ``uv run --with markdown-it-py==4.2.0 python3 spec_check.py``.
Without that exact version the checker exits 3 (missing dependency); it has no second
Markdown scanner to fall back to.  Otherwise stdlib.  PyYAML is used when importable;
otherwise a parser for the
YAML subset the format uses (block mappings and lists, flow lists, one-level
flow mappings, folded and literal scalars, comments) reads the frontmatter.
The subset parser rejects ``: `` inside an unquoted scalar, as PyYAML does,
so the two never disagree on that trap.  ``--no-pyyaml`` forces the subset
parser, which is what the tests exercise so the fallback never rots; the
output names the parser that ran (``parser: pyyaml`` or ``parser: subset``).

Exit codes follow the dev-tools/cli-conventions contract:

  0  clean (warnings allowed)
  1  findings
  2  usage error
  3  missing precondition (a root has no board-specs.yaml; peripheral-spec's
     scripts or markdown-it-py 4.2.0 missing)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import spdx  # same directory

# peripheral-spec's scripts sit beside this skill: anchor_check.py parses [src:] anchors and
# mdtokens.py is the one Markdown parse both checkers read a spec's structure from.
_PERIPHERAL = Path(__file__).resolve().parent.parent.parent / "peripheral-spec" / "scripts"
if str(_PERIPHERAL) not in sys.path:
    sys.path.append(str(_PERIPHERAL))
try:
    import anchor_check  # noqa: E402
    import mdtokens  # noqa: E402
except ImportError:
    anchor_check = mdtokens = None

KINDS = ("board", "soc", "chip", "ip")
LAYERS = ("public", "ip-vendor", "soc-vendor", "product", "local")
REQUIRED = {
    "board": ("kind", "id", "name", "triggers", "parts", "cache"),
    "soc": ("kind", "id", "name", "triggers", "instances"),
    "chip": ("kind", "id", "name", "triggers"),
    "ip": ("kind", "id", "name", "triggers", "resources"),
}
IRQ_KINDS = ("SPI", "PPI", "extended")
FETCH_VALUES = ("ok", "blocked", "truncated", "partial")
STATUS_VALUES = ("unmerged", "merged", "superseded")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# An unsubstituted template placeholder: <...> starting with a letter, but not an
# autolink (<https://...>) or a message id (<id@host>).
PLACEHOLDER_RE = re.compile(r"<(?!https?://|mailto:)[A-Za-z][^>@\n]*>")
FACT_SECTIONS = mdtokens.FACT_SECTIONS if mdtokens else frozenset()
TAG_NAMES = "databook|standard|rtl|DT|src|source-observed|doc|hardware|press|inference|emulated"
# The classes a variants: row may name. Not [src]: its authority is the anchors in its
# parenthetical, and a variants row has no place for them.
TAG_CLASSES = tuple(t for t in TAG_NAMES.split("|") if t != "src")
TAG_RE = re.compile(rf"\[({TAG_NAMES})\]")
# A tag name in any case: one that is not exactly a canonical name is an error.
ANY_CASE_TAG_RE = re.compile(rf"\[((?i:{TAG_NAMES}))\]")
TODO_RE = re.compile(r"TODO \(verify on hardware\)")
# A parenthetical with up to two levels of nesting inside it, so an [inference]'s premises may
# hold a [src] ([src:x: f.c:1 (sym)]) clause. The text is the masked bullet (mdtokens), where
# code spans no longer contribute brackets or parentheses.
_PAREN0 = r"\([^()]*\)"
_PAREN1 = rf"\((?:[^()]|{_PAREN0})*\)"
_PAREN2 = rf"\((?:[^()]|{_PAREN1})*\)"
# One tag with an optional parenthetical citation.
_TAG_CLAUSE = rf"\[(?:{TAG_NAMES})\](?:\s*{_PAREN2})?"
# The tail a fact bullet must end with: tag clauses, then at most one TODO sentence.
TAIL_RE = re.compile(
    rf"(?:{_TAG_CLAUSE})(?:\s*[,;]?\s*{_TAG_CLAUSE})*\.?"
    rf"(?:\s*TODO \(verify on hardware\)[^\[\]]*)?\s*$"
)
# A gap bullet, read from the item's own parsed text (no list marker, no indentation).
GAP_RE = re.compile(r"^(?:\*\*[^*]+\*\*\s*)?TODO \(verify on hardware\)")
# Tags that must be followed by a parenthetical naming their source.
NAMED_TAGS = ("doc", "DT", "inference", "rtl", "emulated", "src")
# Tags whose fact must carry the closing TODO (verify on hardware) sentence.
TODO_TAGS = ("source-observed", "press", "inference", "emulated")


# Anchor kinds anchor_check.py reads that a board spec may not use: [impl:] is an alias of
# [src:] and [tgt:]/[ref:] cite a target-OS tree, none of which a board spec pins.
OTHER_ANCHOR_KINDS = ("impl", "tgt", "ref")
# A [src] pin: a full commit id (SHA-1, or SHA-256 for a repository in that object format).
COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)


# ----------------------------------------------------------------------------
# YAML subset parser (fallback when PyYAML is absent)
# ----------------------------------------------------------------------------


class YamlError(ValueError):
    pass


def _scalar(text: str, key: str | None = None):
    text = text.strip()
    if text == "" or text == "null" or text == "~":
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    if text == "[]":
        return []
    if text.startswith("["):
        if not text.endswith("]"):
            raise YamlError(f"unterminated flow sequence: {text!r}")
        inner = text[1:-1].strip()
        return [_scalar(p) for p in _split_flow(inner)] if inner else []
    if text.startswith("{"):
        if not text.endswith("}"):
            raise YamlError(f"unterminated flow mapping: {text!r}")
        inner = text[1:-1].strip()
        result = {}
        for part in _split_flow(inner) if inner else []:
            fkey, sep, value = part.partition(":")
            if not sep:
                raise YamlError(f"flow mapping entry without a colon: {part!r}")
            result[fkey.strip()] = _scalar(value, fkey.strip())
        return result
    if (text[0] == text[-1]) and text[0] in "\"'" and len(text) >= 2:
        return text[1:-1]
    if ": " in text or text.endswith(":"):
        where = f"the value of {key!r}" if key else "an unquoted value"
        raise YamlError(f"{where} contains ': ' (mapping values are not allowed here); quote it")
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"0x[0-9a-fA-F]+", text):
        return int(text, 16)
    return text


def _split_flow(inner: str) -> list[str]:
    parts, buf, quote = [], [], None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf or not parts:
        parts.append("".join(buf))
    return [p for p in parts if p.strip()]


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def parse_yaml_subset(text: str):
    lines = []
    for raw in text.splitlines():
        stripped = _strip_comment(raw)
        if stripped.strip() == "":
            lines.append(None)
        else:
            lines.append(stripped)
    pos = 0

    def skip_blank():
        nonlocal pos
        while pos < len(lines) and lines[pos] is None:
            pos += 1

    def block_scalar(indent: int, style: str) -> str:
        nonlocal pos
        collected = []
        while pos < len(lines):
            line = lines[pos]
            if line is None:
                collected.append("")
                pos += 1
                continue
            if _indent(line) <= indent:
                break
            collected.append(line.strip())
            pos += 1
        while collected and collected[-1] == "":
            collected.pop()
        joiner = "\n" if style.startswith("|") else " "
        return joiner.join(collected)

    def parse_value(after_colon: str, indent: int, key: str | None = None):
        nonlocal pos
        value = after_colon.strip()
        if value in (">", ">-", "|", "|-"):
            pos += 1
            return block_scalar(indent, value)
        if value != "":
            pos += 1
            return _scalar(value, key)
        pos += 1
        skip_blank()
        if pos >= len(lines):
            return None
        nxt = lines[pos]
        if _indent(nxt) <= indent and not nxt.lstrip().startswith("- "):
            return None
        return parse_node(max(_indent(nxt), indent))

    def parse_mapping(indent: int) -> dict:
        nonlocal pos
        result: dict = {}
        while True:
            skip_blank()
            if pos >= len(lines):
                break
            line = lines[pos]
            if _indent(line) < indent:
                break
            if _indent(line) > indent:
                raise YamlError(f"unexpected indentation at line {pos + 1}: {line!r}")
            body = line.strip()
            if body.startswith("- "):
                break
            m = re.match(r"([A-Za-z0-9_.\-]+):(.*)", body)
            if not m:
                raise YamlError(f"expected 'key: value' at line {pos + 1}: {line!r}")
            key, rest = m.group(1), m.group(2)
            result[key] = parse_value(rest, indent, key)
        return result

    def parse_list(indent: int) -> list:
        nonlocal pos
        result: list = []
        while True:
            skip_blank()
            if pos >= len(lines):
                break
            line = lines[pos]
            if _indent(line) != indent or not line.strip().startswith("- "):
                break
            item = line.strip()[2:]
            item_indent = indent + 2
            m = re.match(r"([A-Za-z0-9_.\-]+):(.*)", item)
            if m and not item.startswith(("'", '"', "[")):
                # mapping starting on the dash line: rewrite in place and parse
                lines[pos] = " " * item_indent + item
                result.append(parse_mapping(item_indent))
            else:
                pos += 1
                result.append(_scalar(item))
        return result

    def parse_node(indent: int):
        skip_blank()
        if pos >= len(lines):
            return None
        if lines[pos].strip().startswith("- "):
            return parse_list(_indent(lines[pos]))
        return parse_mapping(indent)

    result = parse_node(0)
    skip_blank()
    if pos < len(lines):
        raise YamlError(f"trailing content at line {pos + 1}: {lines[pos]!r}")
    return result


def _dates_to_strings(node):
    """PyYAML turns ``verified: 2026-09-18`` into a date; the subset parser keeps the string."""
    import datetime

    if isinstance(node, dict):
        return {k: _dates_to_strings(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_dates_to_strings(v) for v in node]
    if isinstance(node, datetime.date):
        return node.isoformat()
    return node


def pyyaml_available() -> bool:
    try:
        import yaml  # type: ignore  # noqa: F401
    except ImportError:
        return False
    return True


def parser_name(use_pyyaml: bool) -> str:
    """Which parser load_yaml will actually run: 'pyyaml' or 'subset'."""
    return "pyyaml" if use_pyyaml and pyyaml_available() else "subset"


def load_yaml(text: str, use_pyyaml: bool):
    if use_pyyaml and pyyaml_available():
        import yaml  # type: ignore

        return _dates_to_strings(yaml.safe_load(text))
    return parse_yaml_subset(text)


# ----------------------------------------------------------------------------
# Model
# ----------------------------------------------------------------------------


@dataclass
class Finding:
    level: str  # "error" | "warning"
    path: str
    message: str


@dataclass
class Spec:
    path: Path
    root: Path
    layer: str
    meta: dict
    body: str
    # The root marker's accepts list (canonical SPDX ids), or None when the root declares none.
    accepts: tuple | None = None
    # --require-license: resources.repos licenses must be in accepts (the board-spec gate).
    gate: bool = False
    # Lines before the body (the frontmatter and its fences), so findings cite file lines.
    body_offset: int = 0
    _doc: object = None

    @property
    def doc(self):
        """The body's one Markdown parse (mdtokens.Doc), made on first use."""
        if self._doc is None:
            self._doc = mdtokens.parse(self.body)
        return self._doc

    @property
    def is_overlay(self) -> bool:
        return "overlays" in self.meta

    @property
    def id(self):
        return self.meta.get("overlays") if self.is_overlay else self.meta.get("id")


def read_root(root: Path, use_pyyaml: bool) -> tuple[dict | None, str | None]:
    marker = root / "board-specs.yaml"
    if not marker.exists():
        return None, f"{root}: no board-specs.yaml (not a spec root)"
    try:
        data = load_yaml(marker.read_text(), use_pyyaml) or {}
    except Exception as exc:  # noqa: BLE001
        return None, f"{marker}: cannot parse: {exc}"
    return data, None


def check_root_license(
    marker: dict, where: str, require: bool, findings: list[Finding]
) -> tuple | None:
    """Validate a root marker's ``license:`` and ``accepts:`` (design LS-R1).

    Returns the accepts list as canonical SPDX identifiers, or None when the marker
    declares none. A declared list that is malformed still counts as declared (the
    valid entries only, possibly none), so a broken list never loosens a check.
    """
    missing = "error" if require else "warning"
    if "license" not in marker:
        findings.append(
            Finding(
                missing,
                where,
                "root marker: no license: field (the SPDX expression for this root's own "
                "license); --require-license makes this an error",
            )
        )
    else:
        try:
            spdx.parse(marker["license"])
        except spdx.SpdxError as exc:
            findings.append(Finding("error", where, f"root marker: license: {exc}"))
    if "accepts" not in marker:
        findings.append(
            Finding(
                missing,
                where,
                "root marker: no accepts: field (the SPDX identifiers anchored sources may "
                "carry; [] for none); --require-license makes this an error",
            )
        )
        return None
    raw = marker["accepts"]
    if not isinstance(raw, list):
        findings.append(
            Finding("error", where, "root marker: accepts: must be a list of SPDX identifiers ([] for none)")
        )
        return ()
    accepts = []
    for item in raw:
        try:
            accepts.append(spdx.parse_identifier(item))
        except spdx.SpdxError as exc:
            findings.append(Finding("error", where, f"root marker: accepts entry {item!r}: {exc}"))
    return tuple(accepts)


class LinkInContextRoot(Exception):
    """A context root holds a symbolic link, or is reached through one: refuse to run."""


def walk_root(root: Path, context: bool, findings: list[Finding]) -> list[Path]:
    """Every file under root, found without following links. A link (file or directory) is
    an error in a checked root and stops the run (LinkInContextRoot) in a context root."""
    files = []
    for top, dirs, names in os.walk(root, followlinks=False):
        for name in sorted(dirs) + sorted(names):
            path = Path(top) / name
            if path.is_symlink():
                if context:
                    raise LinkInContextRoot(f"{path} is a symbolic link")
                findings.append(
                    Finding("error", str(path), "symbolic link in a spec root: a root holds its "
                            "files itself, never through links")
                )
            elif name in names:
                files.append(path)
        dirs[:] = sorted(d for d in dirs if not (Path(top) / d).is_symlink())
    return files


def through_link(root: Path) -> bool:
    """Whether root is, or is reached through, a symbolic link.

    Each component is inspected as given, before any normalization: in
    ``/bin/../../tmp/r`` the link ``/bin`` is seen even though ``..`` cancels it lexically.
    A relative root starts from the working directory, which the OS reports resolved.
    """
    cur = Path(root.anchor) if root.is_absolute() else Path.cwd()
    for part in root.parts[1:] if root.is_absolute() else root.parts:
        cur = cur / part
        if cur.is_symlink():
            return True
    return False


def load_specs(
    roots: list[Path],
    use_pyyaml: bool,
    findings: list[Finding],
    require_license: bool = False,
    context_roots: tuple = (),
    origin: dict | None = None,
) -> tuple[list[Spec], list[str]]:
    """Load every root's specs. origin, when given, maps every file path found to whether it
    was found under a context root, so each finding keeps the root it was read through."""
    specs: list[Spec] = []
    preconditions: list[str] = []
    origin = {} if origin is None else origin
    for root in roots:
        context = root in context_roots
        if through_link(root):
            if context:
                raise LinkInContextRoot(f"{root} is, or is reached through, a symbolic link")
            findings.append(
                Finding("error", str(root), "spec root is, or is reached through, a symbolic "
                        "link: give its real path")
            )
            continue
        marker, err = read_root(root, use_pyyaml)
        if err:
            preconditions.append(err)
            continue
        layer = marker.get("layer")
        if layer not in LAYERS:
            findings.append(
                Finding("error", str(root / "board-specs.yaml"), f"unknown layer {layer!r}")
            )
            layer = str(layer)
        accepts = check_root_license(
            marker, str(root / "board-specs.yaml"), require_license, findings
        )
        files = walk_root(root, context, findings)
        origin.update({str(f): context for f in files})
        origin[str(root)] = context
        for path in sorted(f for f in files if f.name.endswith(".spec.md")):
            text = path.read_text()
            m = FRONTMATTER_RE.match(text)
            if not m:
                findings.append(Finding("error", str(path), "no YAML frontmatter"))
                continue
            try:
                meta = load_yaml(m.group(1), use_pyyaml)
            except Exception as exc:  # noqa: BLE001
                findings.append(Finding("error", str(path), f"frontmatter does not parse: {exc}"))
                continue
            if not isinstance(meta, dict):
                findings.append(Finding("error", str(path), "frontmatter is not a mapping"))
                continue
            offset = text[: m.start(2)].count("\n")
            specs.append(
                Spec(path, root, layer, meta, m.group(2), accepts, require_license, offset)
            )
    return specs, preconditions


# ----------------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------------


def check_frontmatter(spec: Spec, findings: list[Finding]) -> None:
    p = str(spec.path)
    check_resources(spec, findings)
    if spec.is_overlay:
        if not isinstance(spec.meta.get("overlays"), str):
            findings.append(Finding("error", p, "overlays: must name one spec id"))
        for key in ("kind", "id", "parts"):
            if key in spec.meta:
                findings.append(Finding("error", p, f"an overlay may not carry {key!r}"))
        check_variants(spec, findings)
        return
    kind = spec.meta.get("kind")
    if kind not in KINDS:
        findings.append(Finding("error", p, f"unknown kind {kind!r}"))
        return
    for key in REQUIRED[kind]:
        if key not in spec.meta:
            findings.append(Finding("error", p, f"kind {kind}: missing required key {key!r}"))
    if kind == "ip":
        docs = (spec.meta.get("resources") or {}).get("docs") or []
        if not any(isinstance(d, dict) and d.get("cite") is True for d in docs):
            findings.append(Finding("error", p, "ip spec has no docs entry with cite: true"))
    for row in spec.meta.get("instances") or []:
        check_instance_shape(p, row, findings)
    check_variants(spec, findings)
    if "variant_of" in spec.meta and kind != "board":
        findings.append(Finding("error", p, "variant_of is only valid on a board spec"))
    check_ids_and_triggers(spec, findings)


def check_variants(spec: Spec, findings: list[Finding]) -> None:
    """variants: rows name a variant and, optionally, a provenance class (never src)."""
    p = str(spec.path)
    for variant in spec.meta.get("variants") or []:
        if not isinstance(variant, dict) or not variant.get("name"):
            findings.append(Finding("error", p, "variants: entry without a name"))
            continue
        tag = variant.get("tag")
        if tag is not None and tag not in TAG_CLASSES:
            findings.append(
                Finding(
                    "error",
                    p,
                    f"variants: entry {variant['name']!r}: tag must be a provenance class, not {tag!r}",
                )
            )
        source = variant.get("source")
        if source is not None and not isinstance(source, str):
            findings.append(
                Finding("error", p, f"variants: entry {variant['name']!r}: source must be a string")
            )


def check_ids_and_triggers(spec: Spec, findings: list[Finding]) -> None:
    """Ids are normalized (lowercase, hyphens); triggers and not_triggers are lists of strings."""
    p = str(spec.path)
    candidates: list[tuple[str, object]] = []
    for key in ("id", "variant_of", "overlays"):
        if spec.meta.get(key) is not None:
            candidates.append((key, spec.meta[key]))
    for key in ("aliases", "parts"):
        values = spec.meta.get(key)
        if values is None:
            continue
        if not isinstance(values, list):
            findings.append(Finding("error", p, f"{key} must be a list"))
            continue
        candidates += [(f"{key} entry", v) for v in values]
    for key, value in candidates:
        if not isinstance(value, str) or not ID_RE.match(value):
            findings.append(
                Finding(
                    "error",
                    p,
                    f"{key} {value!r} is not a normalized id (lowercase, digits, hyphens; "
                    "spaces and underscores become hyphens)",
                )
            )
    for key in ("triggers", "not_triggers"):
        values = spec.meta.get(key)
        if values is None:
            continue
        if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
            findings.append(Finding("error", p, f"{key} must be a list of non-empty strings"))


def check_placeholders(text: str, where: str, findings: list[Finding]) -> None:
    """An unsubstituted <...> template placeholder, outside code, is an error."""
    stripped = "\n".join(mdtokens.parse(text).masked)
    seen: list[str] = []
    for m in PLACEHOLDER_RE.finditer(stripped):
        if m.group(0) not in seen:
            seen.append(m.group(0))
    for token in seen[:3]:
        findings.append(
            Finding("error", where, f"unsubstituted template placeholder {token!r}")
        )


def check_instance_shape(p: str, row, findings: list[Finding]) -> None:
    if not isinstance(row, dict):
        findings.append(Finding("error", p, "instances: row is not a mapping"))
        return
    name = row.get("name")
    reg = row.get("reg")
    if reg is not None and (not isinstance(reg, int) or isinstance(reg, bool)):
        findings.append(
            Finding("error", p, f"instance {name!r}: reg must be an integer or null, not {reg!r}")
        )
    irq = row.get("irq")
    if irq is None:
        return
    if not isinstance(irq, dict):
        findings.append(
            Finding("error", p, f"instance {name!r}: irq must be null or a mapping, not {irq!r}")
        )
        return
    if irq.get("kind") not in IRQ_KINDS:
        findings.append(
            Finding("error", p, f"instance {name!r}: irq.kind must be one of {IRQ_KINDS}")
        )
    number = irq.get("number")
    if not isinstance(number, int) or isinstance(number, bool):
        findings.append(Finding("error", p, f"instance {name!r}: irq.number must be an integer"))
    intid = irq.get("intid")
    if intid is not None and (not isinstance(intid, int) or isinstance(intid, bool)):
        findings.append(Finding("error", p, f"instance {name!r}: irq.intid must be an integer"))
    parent = irq.get("parent")
    if irq.get("kind") == "extended":
        if not isinstance(parent, str) or not parent:
            findings.append(
                Finding("error", p, f"instance {name!r}: irq.kind extended requires irq.parent")
            )
        if intid is not None:
            findings.append(
                Finding("error", p, f"instance {name!r}: irq.intid is not valid for kind extended")
            )
    elif parent is not None:
        findings.append(
            Finding("error", p, f"instance {name!r}: irq.parent is only valid for kind extended")
        )


def check_resources(spec: Spec, findings: list[Finding]) -> None:
    p = str(spec.path)
    for group, entry in iter_resources(spec.meta):
        label = entry.get("name") or entry.get("title") or entry.get("url") or "?"
        if group == "series" and entry.get("cite") is True:
            findings.append(
                Finding("error", p, f"series entry {label!r}: a series is a map, never cite: true")
            )
        fetch = entry.get("fetch")
        if fetch is not None and fetch not in FETCH_VALUES:
            findings.append(
                Finding("error", p, f"{group} entry {label!r}: fetch must be one of {FETCH_VALUES}")
            )
        fetch_via = entry.get("fetch_via")
        if fetch_via is not None and (not isinstance(fetch_via, str) or not fetch_via):
            findings.append(
                Finding("error", p, f"{group} entry {label!r}: fetch_via must be a non-empty string")
            )
        verified = entry.get("verified")
        if verified is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(verified)):
            findings.append(
                Finding("error", p, f"{group} entry {label!r}: verified must be an ISO date (YYYY-MM-DD)")
            )
        status = entry.get("status")
        if status is not None and status not in STATUS_VALUES:
            findings.append(
                Finding("error", p, f"{group} entry {label!r}: status must be one of {STATUS_VALUES}")
            )
        if group == "repos":
            check_repo_license(spec, label, entry, findings)
            url = entry.get("url")
            if url is not None and (not isinstance(url, str) or not url.startswith("https://")):
                findings.append(
                    Finding(
                        "error",
                        p,
                        f"repos entry {label!r}: url {url!r} must be an https:// URL (tools "
                        "fetch it, and accept no other transport)",
                    )
                )
        for item in entry.get("files") or []:
            if isinstance(item, str):
                continue
            if not isinstance(item, dict) or not item.get("path"):
                findings.append(
                    Finding("error", p, f"{group} entry {label!r}: files entry must be a path or a mapping with path")
                )
                continue
            fstatus = item.get("status")
            if fstatus is not None and fstatus not in STATUS_VALUES:
                findings.append(
                    Finding(
                        "error",
                        p,
                        f"{group} entry {label!r}: file {item['path']!r}: status must be one of {STATUS_VALUES}",
                    )
                )


def check_repo_license(spec: Spec, label: str, entry: dict, findings: list[Finding]) -> None:
    """A repos entry's license is an SPDX expression; required when the root has accepts: (LS-R2).

    Under --require-license it must also be accepted by the root's accepts: list (the
    board-spec license gate, decided by the user on 2026-10-06), by the same rule as
    anchor_check.py's gate. A root with no accepts: is already an error there.
    """
    p = str(spec.path)
    if "license" in entry:
        try:
            tree = spdx.parse(entry["license"])
        except spdx.SpdxError as exc:
            findings.append(Finding("error", p, f"repos entry {label!r}: license: {exc}"))
            return
        if spec.gate and spec.accepts is not None and not spdx.accepted(tree, spec.accepts):
            listed = ", ".join(spec.accepts) or "none"
            findings.append(
                Finding(
                    "error",
                    p,
                    f"license gate: repos entry {label!r} ({entry['license']}), which root "
                    f"{spec.root} does not accept (accepts: {listed}); cite it from a root that "
                    "accepts it, or drop it",
                )
            )
    elif spec.accepts is not None:
        findings.append(
            Finding(
                "error",
                p,
                f"repos entry {label!r}: no license: (required in a root whose marker declares accepts:)",
            )
        )


def iter_resources(meta: dict):
    resources = meta.get("resources") or {}
    if not isinstance(resources, dict):
        return
    for group, entries in resources.items():
        for entry in entries or []:
            if isinstance(entry, dict):
                yield group, entry


def check_public(spec: Spec, public_skills: set[str], findings: list[Finding]) -> None:
    if spec.layer != "public":
        return
    p = str(spec.path)
    for group, entry in iter_resources(spec.meta):
        label = entry.get("name") or entry.get("title") or entry.get("url") or "?"
        if entry.get("access") == "internal":
            findings.append(
                Finding("error", p, f"{group} entry {label!r}: access: internal under a public root")
            )
        via = entry.get("via")
        if isinstance(via, str):
            skill = via.split(":", 1)[1] if via.startswith("skill:") else via
            if skill not in public_skills:
                findings.append(
                    Finding(
                        "error",
                        p,
                        f"{group} entry {label!r}: via {via!r} is not a public skill "
                        "(pass --public-skill NAME if it is)",
                    )
                )


def check_references(specs: list[Spec], findings: list[Finding]) -> None:
    by_id: dict[str, list[Spec]] = {}
    for spec in specs:
        if not spec.is_overlay and isinstance(spec.id, str):
            by_id.setdefault(spec.id, []).append(spec)
    for sid, owners in by_id.items():
        if len(owners) > 1:
            for owner in owners:
                findings.append(
                    Finding("error", str(owner.path), f"duplicate id {sid!r} ({len(owners)} specs)")
                )
    # One overlay per id per root: overlays of one id in different roots of one layer merge in
    # the order the roots are given (FORMAT-1, Roots and layers); two in one root have no
    # order between them.
    overlays_seen: dict[tuple[str, str, str], list[Spec]] = {}
    for spec in specs:
        p = str(spec.path)
        if spec.is_overlay:
            target = spec.meta.get("overlays")
            if target not in by_id:
                findings.append(Finding("error", p, f"overlays {target!r} resolves to nothing"))
            overlays_seen.setdefault((str(target), spec.layer, str(spec.root)), []).append(spec)
            continue
        base = spec.meta.get("variant_of")
        if base is not None:
            if base not in by_id:
                findings.append(Finding("error", p, f"variant_of {base!r} resolves to nothing"))
            elif by_id[base][0].meta.get("kind") != "board":
                findings.append(Finding("error", p, f"variant_of {base!r} is not a board spec"))
        for part in spec.meta.get("parts") or []:
            if part not in by_id:
                findings.append(Finding("error", p, f"parts entry {part!r} resolves to nothing"))
                continue
            part_cache = by_id[part][0].meta.get("cache")
            if part_cache and spec.meta.get("cache") and part_cache != spec.meta.get("cache"):
                findings.append(
                    Finding(
                        "warning",
                        p,
                        f"part {part!r} names cache {part_cache!r}, this board {spec.meta.get('cache')!r}",
                    )
                )
        for row in spec.meta.get("instances") or []:
            if not isinstance(row, dict):
                continue
            ip = row.get("ip")
            if ip not in by_id:
                findings.append(
                    Finding("error", p, f"instance {row.get('name')!r}: ip {ip!r} resolves to nothing")
                )
            elif by_id[ip][0].meta.get("kind") != "ip":
                findings.append(
                    Finding("error", p, f"instance {row.get('name')!r}: {ip!r} is not an ip spec")
                )
    for (target, layer, root), owners in overlays_seen.items():
        if len(owners) > 1:
            for owner in owners:
                findings.append(
                    Finding(
                        "warning",
                        str(owner.path),
                        f"{len(owners)} overlays for {target!r} in layer {layer!r} in one root "
                        f"({root}); merge order undefined",
                    )
                )


def iter_fact_bullets(doc):
    """Yield (1-based body line, text) for every top-level list item in a fact section.

    Sections, list items and code come from the one Markdown parse (mdtokens). The text is the
    item's own masked inline content (its paragraphs, lazy continuation lines included), so
    neither the list marker nor its indentation matters, and a nested item never lends its
    tags to its parent (nested items in a fact section are a profile error of their own).
    """
    for idx in doc.top_items():
        item = doc.items[idx]
        if mdtokens.section_of(doc, item.start) in FACT_SECTIONS:
            yield item.start + 1, "\n".join(item.own)


def paren_after(text: str, pos: int) -> tuple[int, int] | None:
    """The balanced parenthetical starting at text[pos] after optional whitespace, as a
    (start, end) slice, or None when there is none or it never closes."""
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text) or text[pos] != "(":
        return None
    depth = 0
    for i in range(pos, len(text)):
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return pos, i + 1
    return None


def own_text(inner: str) -> str:
    """inner with every nested tag's parenthetical blanked: what a clause cites itself."""
    out = list(inner)
    for m in TAG_RE.finditer(inner):
        span = paren_after(inner, m.end())
        if span:
            out[span[0]:span[1]] = " " * (span[1] - span[0])
    return "".join(out)


NAMED_WHAT = {
    "doc": "its source",
    "DT": "the file (and its origin, for a blob)",
    "inference": "its premises and derivation",
    "rtl": "the design, its revision, and the module",
    "emulated": "the device model, its version and the run IDs",
    "src": "the [src:<repo>: path:L] anchors it was read from",
}


def check_tags(spec: Spec, findings: list[Finding]) -> None:
    p = str(spec.path)
    for line_no, raw in iter_fact_bullets(spec.doc):
        where = f"{p}:{line_no + spec.body_offset}"
        if GAP_RE.match(raw.lstrip()):
            continue  # a gap-only bullet: "- **Topic.** TODO (verify on hardware) ..."
        bullet = " ".join(line.strip() for line in raw.splitlines())
        tail_match = TAIL_RE.search(bullet)
        if not tail_match:
            if TAG_RE.search(bullet):
                findings.append(
                    Finding(
                        "error",
                        where,
                        "fact bullet does not end with its tag clause (tags, each with an optional "
                        "parenthetical, then at most one TODO sentence); a tag name in the prose "
                        "does not count",
                    )
                )
            else:
                findings.append(Finding("error", where, "fact bullet has no provenance tag"))
            continue
        # Only the tail clause is examined from here on: prose may mention tag names freely.
        # In it every tag token counts, nested ones included; a code span holding only a tag
        # is that tag (mdtokens), and any longer code span is prose with no tag in it.
        tail = tail_match.group(0)
        tags = list(TAG_RE.finditer(tail))
        names = [m.group(1) for m in tags]
        has_todo = bool(TODO_RE.search(tail))
        messages: list[str] = []
        for needs_todo in TODO_TAGS:
            if needs_todo in names and not has_todo:
                messages.append(f"[{needs_todo}] fact without 'TODO (verify on hardware)'")
        for m in tags:
            tag = m.group(1)
            if tag not in NAMED_TAGS:
                continue
            span = paren_after(tail, m.end())
            if span is None:
                messages.append(
                    f"[{tag}] must be followed by a parenthetical naming {NAMED_WHAT[tag]}"
                )
            elif tag == "src" and count_src_anchors(own_text(tail[span[0] + 1:span[1] - 1])) == 0:
                # Every [src] clause, nested ones included, carries anchors of its own; a nested
                # clause's anchors do not count for the clause around it, nor the reverse.
                messages.append(
                    "[src] parenthetical cites no anchor: write [src:<repo>: path:L1-L2 (symbol)] "
                    "naming a resources.repos entry pinned to a commit"
                )
        # A model observation is never the sole authority for a fact: it stands beside
        # another class, or it is a premise of an [inference] (which then carries the tag).
        if names and set(names) == {"emulated"}:
            messages.append(
                "[emulated] is never the sole authority for a fact: cite another class beside "
                "it, or make the observation a premise of an [inference]"
            )
        for message in dict.fromkeys(messages):
            findings.append(Finding("error", where, message))


def count_src_anchors(text: str) -> int:
    """How many well-formed [src:] anchors anchor_check.py parses out of text."""
    n = 0
    for m in re.finditer(r"\[src:([^\]]*)\]", text):
        n += len(anchor_check.parse_tag_body("src", m.group(1), 0, "", anchor_check.Report(spec="")))
    return n


def load_anchor_check():
    """peripheral-spec's anchor_check module (imported beside this skill), or None."""
    return anchor_check


def check_markdown(spec: Spec, findings: list[Finding]) -> None:
    """Every construct outside the spec Markdown profile (mdtokens.profile_violations: an
    image, raw HTML other than the leading SPDX comment, a block quote outside ## Source
    notices, a setext heading, a code span inside a word, a nested list item in a
    fact section, a code fence that never closes), and a tag name not in its canonical case
    ([Src], [SRC], [dt]) anywhere outside code: tag names are case-sensitive."""
    p = str(spec.path)
    for n, message in mdtokens.profile_violations(spec.doc, FACT_SECTIONS):
        findings.append(Finding("error", f"{p}:{n + 1 + spec.body_offset}", message))
    for n, line in enumerate(spec.doc.masked, 1):
        for m in ANY_CASE_TAG_RE.finditer(line):
            if m.group(1) not in TAG_NAMES.split("|"):
                canonical = next(t for t in TAG_NAMES.split("|") if t.lower() == m.group(1).lower())
                findings.append(
                    Finding(
                        "error",
                        f"{p}:{n + spec.body_offset}",
                        f"tag {m.group(0)!r} is not in its canonical case: write [{canonical}] "
                        "(tag names are case-sensitive)",
                    )
                )


def check_src_anchors(spec: Spec, findings: list[Finding]) -> None:
    """Every [src:<repo>: path:L] anchor in the body names a pinned, accepted repos entry.

    The pin is the spec's own resources.repos entry of that name: its ref must be a full
    commit id and its license one the root's accepts: list accepts. Unlike the repos gate
    under --require-license, this applies always, and a root with no accepts: (or an empty
    one, a documents-only root) accepts no [src] at all. Resolving the anchors against the
    tree is anchor_check.py's job; this checks only what the spec itself can show. Anchors
    are read from the masked body (mdtokens): code blocks and prose code spans hold none.
    """
    p = str(spec.path)
    for n, message in mdtokens.anchor_problems(spec.doc):
        findings.append(Finding("error", f"{p}:{n + 1 + spec.body_offset}", message))
    ac = anchor_check
    repos = {}
    for group, entry in iter_resources(spec.meta):
        if group == "repos" and isinstance(entry.get("name"), str):
            repos.setdefault(entry["name"], entry)
    listed = ", ".join(spec.accepts) if spec.accepts else "none"
    judged: dict[str, str | None] = {}  # repo name -> why it cannot pin a [src] anchor

    def pin_problem(name: str) -> str | None:
        entry = repos.get(name)
        if entry is None:
            have = ", ".join(repos) or "none"
            return f"names repo {name!r}, but the spec's resources.repos entries are: {have}"
        ref = entry.get("ref")
        if not isinstance(ref, str) or not COMMIT_RE.match(ref):
            return (
                f"cites repos entry {name!r}, whose ref {ref!r} is not a full commit id "
                "(40 lowercase hex digits): a [src] fact is read at a pinned commit"
            )
        if "license" not in entry:
            return f"cites repos entry {name!r}, which states no license:"
        try:
            tree = spdx.parse(entry["license"])
        except spdx.SpdxError:
            return None  # reported by check_repo_license
        if spec.accepts is None:
            return (
                f"license gate: [src] cites repos entry {name!r} ({entry['license']}), but root "
                f"{spec.root} declares no accepts: list"
            )
        if not spdx.accepted(tree, spec.accepts):
            return (
                f"license gate: [src] cites repos entry {name!r} ({entry['license']}), which root "
                f"{spec.root} does not accept (accepts: {listed}); move the fact to a root that "
                "accepts it"
            )
        return None

    for n, line in enumerate(spec.doc.masked, 1):
        where = f"{p}:{n + spec.body_offset}"
        report = ac.Report(spec=p)
        anchors = []
        for kind, body in ac.TAG_RE.findall(line):
            if kind in OTHER_ANCHOR_KINDS:
                findings.append(
                    Finding(
                        "error",
                        where,
                        f"[{kind}:{body}] is not a board-spec anchor: a board spec cites source "
                        "only as [src:<repo>: path:L] ([impl:], [tgt:] and [ref:] belong to "
                        "peripheral specs and reviews)",
                    )
                )
            elif kind == "src":
                if not any(item.strip() for item in body.split(";")):
                    findings.append(
                        Finding("error", where, f"empty [src:{body}] anchor: name a repo, a path and lines")
                    )
                    continue
                anchors += ac.parse_tag_body(kind, body, n, "", report)
        for f in report.findings:
            if f.level == "error":
                findings.append(Finding("error", where, f.message))
        for a in anchors:
            if a.pin is None:
                findings.append(
                    Finding(
                        "error",
                        where,
                        f"[src: {a.raw}] names no repo: write [src:<repo>: {a.raw}] with the "
                        "name of a resources.repos entry",
                    )
                )
                continue
            if a.pin not in judged:
                judged[a.pin] = pin_problem(a.pin)
                # One finding per repo, at its first anchor, not one per anchor.
                problem = judged[a.pin]
                if problem is not None:
                    if not problem.startswith("license gate:"):
                        problem = f"[src:{a.raw}] {problem}"
                    findings.append(Finding("error", where, problem))


RECORD_KEYS = ("spec", "spec_file", "spec_sha256", "verified", "verifier", "sources", "summary")
SUMMARY_KEYS = ("pass", "fail", "unverifiable", "gap")
# Optional because a record written before adjudication existed is still valid, and most
# records have nothing to adjudicate. Validated when present; never a failure on its own.
OPTIONAL_SUMMARY_KEYS = ("adjudicate",)


def record_path(spec: Spec) -> Path:
    """<root>/resources/<spec file name, .spec.md replaced by .verify.md>.

    Named for the file, not the id, so a base spec and its overlay, or two overlays of one id,
    in one root each have their own record. For the usual <id>.spec.md it is <id>.verify.md.
    """
    return spec.root / "resources" / (spec.path.name[: -len(".spec.md")] + ".verify.md")


def check_orphan_records(
    roots: list[Path], specs: list[Spec], findings: list[Finding]
) -> None:
    """Warn on a record no spec file in its root owns (such as one under an overlaid id's
    name, or left after its spec was deleted). Every given root, spec files or not."""
    owned = {record_path(s) for s in specs}
    for root in roots:
        for rec in sorted((root / "resources").glob("*.verify.md")):
            if rec not in owned:
                findings.append(
                    Finding(
                        "warning",
                        str(rec),
                        "verification record belongs to no spec file in this root: a record is "
                        "named for its spec file (<file name>.verify.md); rename or remove it",
                    )
                )


def check_record_collisions(specs: list[Spec], findings: list[Finding]) -> None:
    """Two spec files in one root whose names would share one verification record."""
    owners: dict[Path, list[Spec]] = {}
    for spec in specs:
        owners.setdefault(record_path(spec), []).append(spec)
    for rec, same in owners.items():
        if len(same) > 1:
            names = ", ".join(str(s.path.relative_to(s.root)) for s in same)
            for spec in same:
                findings.append(
                    Finding(
                        "error",
                        str(spec.path),
                        f"{len(same)} spec files in one root ({names}) would share the "
                        f"verification record {rec.relative_to(spec.root)}; rename one",
                    )
                )


def check_verification(
    spec: Spec, use_pyyaml: bool, require: bool, findings: list[Finding]
) -> str:
    """Check the spec's verification record; return its status for the summary.

    Statuses: "verified", "unverified", "stale", "failing", "malformed".
    Only the record's frontmatter is read; the body is the verifier's and the
    reader's business, not this script's.
    """
    p = str(spec.path)
    level = "error" if require else "warning"
    rec = record_path(spec)
    if not rec.exists():
        findings.append(Finding(level, p, f"unverified: no record at {rec.relative_to(spec.root)}"))
        return "unverified"
    rp = str(rec)
    m = FRONTMATTER_RE.match(rec.read_text())
    if not m:
        findings.append(Finding("error", rp, "verification record has no YAML frontmatter"))
        return "malformed"
    try:
        meta = load_yaml(m.group(1), use_pyyaml)
    except Exception as exc:  # noqa: BLE001
        findings.append(Finding("error", rp, f"verification record does not parse: {exc}"))
        return "malformed"
    if not isinstance(meta, dict):
        findings.append(Finding("error", rp, "verification record frontmatter is not a mapping"))
        return "malformed"
    malformed = False
    for key in RECORD_KEYS:
        if key not in meta:
            findings.append(Finding("error", rp, f"verification record: missing key {key!r}"))
            malformed = True
    if meta.get("spec") is not None and meta.get("spec") != spec.id:
        findings.append(
            Finding("error", rp, f"verification record: spec {meta.get('spec')!r} is not {spec.id!r}")
        )
        malformed = True
    rel = spec.path.relative_to(spec.root).as_posix()
    if "spec_file" in meta and meta.get("spec_file") != rel:
        findings.append(
            Finding(
                "error",
                rp,
                f"verification record: spec_file {meta.get('spec_file')!r} is not {rel!r}, the "
                "file this record belongs to",
            )
        )
        malformed = True
    verified = meta.get("verified")
    if verified is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(verified)):
        findings.append(Finding("error", rp, "verification record: verified must be an ISO date"))
        malformed = True
    if "sources" in meta and not isinstance(meta.get("sources"), list):
        findings.append(Finding("error", rp, "verification record: sources must be a list"))
        malformed = True
    for entry in meta.get("sources") or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            findings.append(Finding("error", rp, "verification record: sources entry without a name"))
            malformed = True
            continue
        fetch = entry.get("fetch")
        if fetch is not None and fetch not in FETCH_VALUES:
            findings.append(
                Finding("error", rp, f"verification record: source {entry['name']!r}: fetch must be one of {FETCH_VALUES}")
            )
            malformed = True
    summary = meta.get("summary")
    if "summary" in meta:
        if not isinstance(summary, dict):
            findings.append(Finding("error", rp, "verification record: summary must be a mapping"))
            malformed = True
        else:
            for key in SUMMARY_KEYS:
                value = summary.get(key)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    findings.append(
                        Finding("error", rp, f"verification record: summary.{key} must be a non-negative integer")
                    )
                    malformed = True
            for key in OPTIONAL_SUMMARY_KEYS:
                if key not in summary:
                    continue
                value = summary[key]
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    findings.append(
                        Finding("error", rp, f"verification record: summary.{key} must be a non-negative integer")
                    )
                    malformed = True
    if malformed:
        return "malformed"
    digest = hashlib.sha256(spec.path.read_bytes()).hexdigest()
    stale = str(meta.get("spec_sha256")).lower() != digest
    if stale:
        # Its verdicts, FAILs included, are about another version of the file: the fix may
        # already be in. Report it stale and let the next verification judge.
        old = summary.get("fail", 0)
        note = f" (its {old} FAIL verdict(s) were for that version)" if old else ""
        findings.append(
            Finding(level, p, f"verification stale: {rec.relative_to(spec.root)} was written for another version of this file{note}")
        )
        return "stale"
    if summary.get("fail", 0) > 0:
        findings.append(
            Finding("error", p, f"verification record reports {summary['fail']} FAIL verdict(s); see {rec.relative_to(spec.root)}")
        )
        return "failing"
    return "verified"


STUB_RE = re.compile(r"`spec:\s*([a-z0-9][a-z0-9\-]*)`")


def find_stubs(skills_dir: Path) -> list[Path]:
    """Every */SKILL.md under skills_dir whose frontmatter calls itself a stub."""
    stubs = []
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        m = FRONTMATTER_RE.match(path.read_text())
        if m and "stub over" in m.group(1):
            stubs.append(path)
    return stubs


def check_stub(path: Path, ids: set[str], findings: list[Finding]) -> None:
    if not path.exists():
        findings.append(Finding("error", str(path), "stub file not found"))
        return
    check_placeholders(path.read_text(), str(path), findings)
    found = STUB_RE.findall(path.read_text())
    if not found:
        findings.append(Finding("error", str(path), "stub names no `spec: <id>`"))
        return
    for sid in found:
        if sid not in ids:
            findings.append(Finding("error", str(path), f"stub spec id {sid!r} resolves to nothing"))


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("roots", nargs="+", type=Path, help="spec root directories")
    parser.add_argument(
        "--context-root",
        action="append",
        default=[],
        type=Path,
        help="a further root read for resolution only (overlay targets, parts): its specs are "
        "checked, but its findings are reported as warnings, since they fail in its own "
        "repository's checks",
    )
    parser.add_argument(
        "--stub", action="append", default=[], type=Path, help="a stub SKILL.md to check"
    )
    parser.add_argument(
        "--stubs-from",
        action="append",
        default=[],
        type=Path,
        help="a plugin skills directory; every */SKILL.md whose frontmatter says 'stub over' is checked",
    )
    parser.add_argument(
        "--public-skill",
        action="append",
        default=[],
        help="a skill name that may appear in via: under a public root",
    )
    parser.add_argument(
        "--require-verified",
        action="store_true",
        help="a spec with no verification record, or a stale one, is an error instead of a warning",
    )
    parser.add_argument(
        "--require-license",
        action="store_true",
        help="a root marker without license: or accepts: is an error instead of a warning, "
        "and a resources.repos license the root's accepts: does not accept is an error",
    )
    parser.add_argument("--no-pyyaml", action="store_true", help="force the subset parser")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if mdtokens is None or anchor_check is None:
        print(f"missing precondition: peripheral-spec's anchor_check.py and mdtokens.py were not "
              f"found at {_PERIPHERAL} (install peripheral-spec beside board-expert)",
              file=sys.stderr)
        return 3
    try:
        mdtokens.require()
    except mdtokens.MissingDependency as exc:
        print(exc, file=sys.stderr)
        return 3

    checked = [r.resolve() for r in args.roots]
    for ctx in args.context_root:
        c = ctx.resolve()
        for r in checked:
            if c == r or c in r.parents or r in c.parents:
                print(
                    f"usage error: --context-root {ctx} is, contains, or sits inside the checked "
                    f"root {r}; a context root must be a separate root",
                    file=sys.stderr,
                )
                return 2

    findings: list[Finding] = []
    use_pyyaml = not args.no_pyyaml
    parser_used = parser_name(use_pyyaml)
    origin: dict[str, bool] = {}
    try:
        specs, preconditions = load_specs(
            list(args.roots) + list(args.context_root), use_pyyaml, findings,
            args.require_license, tuple(args.context_root), origin,
        )
    except LinkInContextRoot as exc:
        print(f"usage error: --context-root: {exc}; a context root may hold no links",
              file=sys.stderr)
        return 2
    if preconditions:
        for msg in preconditions:
            print(f"missing precondition: {msg}", file=sys.stderr)
        return 3

    public_skills = set(args.public_skill)
    verification: dict[str, int] = {}
    for spec in specs:
        check_frontmatter(spec, findings)
        check_public(spec, public_skills, findings)
        check_tags(spec, findings)
        check_markdown(spec, findings)
        check_src_anchors(spec, findings)
        check_placeholders(spec.path.read_text(), str(spec.path), findings)
        if isinstance(spec.id, str):
            # Overlays too: each is verified under its own root (spec-verifier, Board specs).
            status = check_verification(spec, use_pyyaml, args.require_verified, findings)
            verification[status] = verification.get(status, 0) + 1
    check_references(specs, findings)
    check_record_collisions(specs, findings)
    check_orphan_records(list(args.roots) + list(args.context_root), specs, findings)
    ids = {s.id for s in specs if not s.is_overlay and isinstance(s.id, str)}
    stubs = list(args.stub)
    for skills_dir in args.stubs_from:
        if not skills_dir.is_dir():
            print(f"missing precondition: {skills_dir} is not a directory", file=sys.stderr)
            return 3
        stubs += find_stubs(skills_dir)
    for stub in stubs:
        check_stub(stub, ids, findings)

    # A finding keeps the root it was read through: every path a check reports is one the
    # walk found (roots hold no links), looked up exactly, never matched by prefix.
    for f in findings:
        if origin.get(re.sub(r":\d+$", "", f.path)):
            f.level = "warning"
            f.message = f"context root: {f.message}"
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    if args.json:
        json.dump(
            {
                "specs": len(specs),
                "stubs": len(stubs),
                "parser": parser_used,
                "verification": verification,
                "findings": [asdict(f) for f in findings],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        for f in findings:
            print(f"{f.level}: {f.path}: {f.message}", file=sys.stderr)
        if errors:
            print(
                f"FAIL: {len(errors)} error(s), {len(warnings)} warning(s) (parser: {parser_used})",
                file=sys.stderr,
            )
        else:
            print(
                f"OK: {len(specs)} specs checked, {len(warnings)} warning(s) (parser: {parser_used})"
            )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
