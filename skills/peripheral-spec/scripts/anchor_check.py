#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0
"""Check the source anchors in a peripheral spec.

A peripheral spec cites where each fact came from with inline tags:

    [src: drivers/net/ethernet/cadence/macb_main.c:2311-2340 (macb_init_hw)]
    [tgt: src/devices/block/drivers/sdhci/sdhci.cc:88 (Sdhci::Init)]
    [doc: Zynq-7000 TRM UG585 §16.3.2]

``src`` anchors resolve against the source repository, ``tgt`` anchors against
the target-OS repository, both at a pinned commit; ``doc`` tags are citations
to documents.  Several anchors may share one tag, separated by ``;``.  A line
consisting only of tags anchors the table or list that follows it (a "block
anchor").

A spec may list the documents it cites in YAML front matter::

    ---
    docs:
      - name: trm                      # used in anchors
        title: Widget TRM v1.0
        url: https://example.com/widget-trm.pdf
        sha256: <64 hex digits of the file>
        pages: 120                     # optional: page anchors must fall within it
        file: widget-trm-v1.0.pdf      # optional: the file's name under --docs-dir
    ---

and cite them by name: ``[doc:trm p.12]``, ``[doc:trm pp.12-14]``,
``[doc:trm §4.3]``, several locators per document (``[doc:trm §4.3 p.88]``) and
several documents per tag (``[doc:trm p.12; ds §3.1]``).  A named anchor has no
space after ``doc:``; one naming no listed document, citing a page outside the
document's ``pages``, or not of that shape is an error, as is a registry entry
missing a field or with a malformed ``sha256``.  ``--docs-dir DIR`` hashes
each listed document's file (``DIR/<file>``, default ``DIR/<name>.pdf``) and
fails on a mismatch; a missing file is skipped with a warning.  Nothing is
fetched: the ``url`` is recorded, never opened.  An unnamed tag
(``[doc: Widget TRM §4.3]``, with the space) is checked as before; under
``--require-license`` in a root whose ``accepts:`` is empty (a datasheet-only
root, where documents are a spec's only provenance) it is an error.

The spec states its pins on lines of the form::

    Source pin: <name-or-url>@<commit> [<SPDX license expression>]
    Target pin: <name-or-url>@<commit> [<SPDX license expression>]

A spec may state several pins per side, each with a distinct name, and cite one
by name: ``[src:linux: drivers/net/foo.c:120]`` resolves against the ``linux``
Source pin.  An anchor without a pin name resolves against the side's only pin,
and is an error when the side has several.  Give one repository per pin with
``--repo NAME=PATH[@REV]`` (repeatable); a bare ``--repo PATH[@REV]`` serves a
spec with at most one Source pin, as before.

A pin's license must be an SPDX expression (``board-expert/scripts/spdx.py``
reads it); one that does not parse is an error, and so is one that cannot be
checked because board-expert is not installed beside this skill.  A line that
starts like a pin (``Source pin:``) but does not have the pin's shape is a
warning, and an error under ``--root``.  ``--root DIR`` applies the
license gate: DIR's ``board-specs.yaml`` lists in ``accepts:`` the licenses its
specs may cite, and every ``[src:]``/``[tgt:]`` anchor (and the aliases) whose
pin's license is not accepted fails, as does an anchor whose pin states no
license or that has no pin at all, and a pin no anchor cites whose license is
not accepted.  ``A OR B`` passes when either side is accepted, ``A AND B`` only
when both are.  ``[doc:]`` tags are not gated.  A root without ``accepts:``
fails the gate rather than skipping it.  ``--require-license`` (with ``--root``)
also makes a missing ``license:`` in DIR's marker an error, as
``spec_check.py --require-license`` does, and requires named doc anchors in a
root that accepts no source.

A board spec (``board-expert/SPEC-FORMAT.md``) states its pins in front matter instead:
each ``resources.repos`` entry with a ``name`` and a ``ref`` is a Source pin of that name,
at that ref, with the entry's ``license:``, and its ``[src]`` facts cite
``[src:<name>: path:L]``. A ``Source pin:`` line naming the same tree must agree with the
entry.

The ``reference-driver-review`` skill uses the same machinery under different
names: ``[impl:]`` is an alias of ``[src:]`` (with ``Impl pin:`` and
``--impl-repo``) and ``[ref:]`` an alias of ``[tgt:]`` (with ``Ref pin:`` and
``--ref-repo``), so a review's implementation-side anchors get drift tracking.

Modes (all stdlib; needs ``git`` on PATH):

  default   resolve every anchor at the pin: path exists, line range in bounds,
            symbol (if given) present in or near the range; flag fact-bearing
            lines that carry no tag at all, claims whose hex literals do not
            appear in the lines they cite, ``[hw-required]`` labels with no
            ``[doc:]`` backing, unnamed ``[doc:]`` tags with no section number,
            and named ``[doc:]`` anchors against the spec's ``docs:`` registry.
  --show    render a review sheet: each spec claim followed by the cited source
            lines, so a human can check the spec against the code by reading.
  --drift R compare each anchor's cited lines at the pin with revision R and
            report which anchors need re-review before the pin moves.
  --rewrite with --drift: update the spec in place — anchors whose cited text
            merely moved get their new line numbers and the Source pin becomes
            R (with several Source pins, the one ``--drift-pin`` names);
            anchors whose text changed keep their numbers and gain a
            ``[stale: was <pin>]`` marker that fails every later check until a
            person re-verifies the claim and removes it.

Exit status: 0 clean, 1 findings, 2 usage or git error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# The body keeps its leading whitespace: "[doc:trm p.12]" (none) is a named doc anchor,
# "[doc: Widget TRM §4]" an unnamed citation. Other kinds strip it.
TAG_RE = re.compile(r"\[(src|tgt|impl|ref|doc|stale):([^\]]*)\]")
KIND_ALIAS = {"impl": "src", "ref": "tgt"}
PIN_ALIAS = {"impl": "source", "ref": "target"}
ANCHOR_RE = re.compile(
    r"^(?P<path>[^\s:()]+):(?P<l1>\d+)(?:-(?P<l2>\d+))?(?:\s*\((?P<sym>[^)]+)\))?$"
)
# The optional license is SPDX-shaped: identifiers joined by OR, AND or WITH, with
# parentheses. Other trailing text ("@abc (v6.1 tag)") leaves the line unmatched, as before.
# Operators match in any case so that "GPL-2.0 or MIT" is read as a pin and its license
# rejected with spdx.py's message; ":" admits DocumentRef-x:LicenseRef-y.
SPDX_TOKEN = r"\(*[A-Za-z0-9][A-Za-z0-9.+:-]*\)*"
PIN_RE = re.compile(r"^(Source|Target|Impl|Ref) pin:\s*(?P<name>\S+?)@(?P<rev>[0-9A-Za-z._/-]+)"
                    rf"(?:\s+(?P<license>{SPDX_TOKEN}(?:\s+(?i:OR|AND|WITH)\s+{SPDX_TOKEN})*))?\s*$")
# A line that starts like a pin. One PIN_RE rejects is reported, never silently dropped:
# a warning, and under --root an error, since the gate cannot see a pin it did not read.
PIN_START_RE = re.compile(r"^(Source|Target|Impl|Ref) pin:")
# A pin name usable in an anchor ("[src:linux: path:L]") and in --repo NAME=PATH.
PIN_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"
NAMED_ANCHOR_RE = re.compile(rf"^(?P<pin>{PIN_NAME}):\s+(?P<rest>\S.*)$")
NAMED_REPO_RE = re.compile(rf"^(?P<pin>{PIN_NAME})=(?P<value>.+)$")
SIDE = {"src": "source", "tgt": "target"}
HEX_RE = re.compile(r"0x[0-9A-Fa-f]+")
FACT_HINT_RE = re.compile(
    r"0x[0-9A-Fa-f]+|\bbits?\s*\[?\d|\bIRQ\s*#?\d|\boffset\b|\bdelay\b|\btimeout\b|\bretr(y|ies)\b",
    re.IGNORECASE,
)
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}")
LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
HW_REQUIRED_RE = re.compile(r"\[?\bhw[-_ ]required\b\]?", re.IGNORECASE)
# A section NUMBER, not a quoted title: "§4.3", "section 6", "ch. 12", "Table 3-1", "p. 88",
# "Appendix B". A bare "§" followed by a title is how citations go unverifiable.
DOC_SECTION_RE = re.compile(r"§\s*[A-Z]?\d|\bsec(tion|t)?\.?\s*[A-Z]?\d|\bch(apter)?\.?\s*\d|"
                            r"\btable\s*[A-Z]?\d|\bfig(ure)?\.?\s*\d|\bp(age|p)?\.\s*\d|"
                            r"\bappendix\s*[A-Z0-9]", re.IGNORECASE)
# Named doc anchors: "<name> <locator>..." with p.N, pp.N-M or §x.y locators.
DOC_ITEM_RE = re.compile(rf"^(?P<name>{PIN_NAME})\s+(?P<locs>\S.*)$")
DOC_LOCATOR_RE = re.compile(r"^(?:p\.(?P<page>\d+)|pp\.(?P<p1>\d+)-(?P<p2>\d+)|"
                            r"§(?P<sec>[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*))$")
DOC_FORMS = "[doc:<name> p.N], [doc:<name> pp.N-M] or [doc:<name> §x.y]"
SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
DOC_KEYS = ("name", "title", "url", "sha256", "pages", "file")
# Top-level front-matter keys that mark a board spec (board-expert/SPEC-FORMAT.md).
BOARD_KEYS = ("kind:", "overlays:", "resources:")


def is_board_spec(meta: dict | None) -> bool:
    return isinstance(meta, dict) and any(k[:-1] in meta for k in BOARD_KEYS)


def hex_set(text: str) -> set[str]:
    """Hex literals in text, normalized: lowercase, underscores dropped, leading zeros stripped."""
    out = set()
    for m in re.finditer(r"0[xX][0-9A-Fa-f_]+", text):
        v = m.group(0)[2:].replace("_", "").lower().lstrip("0") or "0"
        out.add(v)
    return out
SYMBOL_BEFORE = 200  # a symbol naming the enclosing definition may precede the range by this much


@dataclass
class Anchor:
    kind: str  # src | tgt
    path: str
    l1: int
    l2: int
    symbol: str | None
    spec_line: int
    claim: str
    raw: str  # the anchor as written, including any "pin: " prefix
    pin: str | None = None  # the named pin, when the anchor names one
    group: int = 0  # the list item (its first line) the anchor sits in, else its own line


@dataclass
class DocAnchor:
    name: str
    spec_line: int
    raw: str  # the item as written: "trm p.12"
    pages: list = field(default_factory=list)  # [first, last] per page locator
    sections: list = field(default_factory=list)


@dataclass
class Finding:
    level: str  # error | warn
    spec_line: int
    message: str
    anchor: str | None = None


@dataclass
class Report:
    spec: str
    pins: dict = field(default_factory=dict)  # side -> its first pin (kept for old readers)
    pin_list: dict = field(default_factory=dict)  # side -> every pin, in spec order
    anchors: int = 0
    doc_tags: int = 0
    docs: list = field(default_factory=list)  # the front matter's docs: registry, validated
    doc_anchors: list = field(default_factory=list)  # DocAnchor per named [doc:] item
    unnamed_docs: list = field(default_factory=list)  # (spec_line, text) of unnamed [doc:] tags
    findings: list = field(default_factory=list)
    license_gate: dict = field(default_factory=dict)  # {"root", "accepts"} under --root
    unread_pins: list = field(default_factory=list)  # (spec_line, text) of pin-like lines not read
    moves: list = field(default_factory=list)  # (spec_line, old_raw, new_raw)
    stale: list = field(default_factory=list)  # (spec_line, raw) changed or gone

    def add(self, level: str, spec_line: int, message: str, anchor: str | None = None):
        self.findings.append(Finding(level, spec_line, message, anchor))

    @property
    def errors(self):
        return [f for f in self.findings if f.level == "error"]


class Repo:
    """Read-only view of a git repository at one revision."""

    def __init__(self, path: str, rev: str):
        self.path = Path(path)
        self.rev = rev
        self._files: dict[str, list[str] | None] = {}
        if not (self.path / ".git").exists() and not (self.path / "HEAD").exists():
            raise SystemExit(f"error: {path} is not a git repository")
        full = self._git("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
        if full is None:
            raise SystemExit(f"error: revision {rev!r} not found in {path}")
        self.full_rev = full.strip()

    def _git(self, *args: str) -> str | None:
        proc = subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True,
            text=True,
            errors="replace",
        )
        if proc.returncode != 0:
            return None
        return proc.stdout

    def lines(self, rel: str) -> list[str] | None:
        if rel not in self._files:
            text = self._git("show", f"{self.full_rev}:{rel}")
            if text is None:
                self._files[rel] = None
            else:
                # split("\n") leaves one phantom "" after the final newline,
                # which would let an anchor cite one line past EOF.
                split = text.split("\n")
                if split and split[-1] == "":
                    split.pop()
                self._files[rel] = split
        return self._files[rel]

    def blob(self, rel: str) -> str | None:
        out = self._git("rev-parse", "--verify", "--quiet", f"{self.full_rev}:{rel}")
        return None if out is None else out.strip()


# --------------------------------------------------------------------------- parse


def parse_tag_body(kind: str, body: str, spec_line: int, claim: str, report: Report) -> list[Anchor]:
    anchors = []
    for item in (s.strip() for s in body.split(";")):
        if not item:
            continue
        pin = None
        named = NAMED_ANCHOR_RE.match(item)
        if named and ANCHOR_RE.match(named["rest"]):
            pin = named["pin"]
            m = ANCHOR_RE.match(named["rest"])
        else:
            m = ANCHOR_RE.match(item)
        if not m:
            report.add("error", spec_line, f"malformed {kind} anchor: {item!r} "
                       "(expected [pin: ]path:L1[-L2] [(symbol)])", item)
            continue
        l1 = int(m["l1"])
        l2 = int(m["l2"]) if m["l2"] else l1
        if l2 < l1:
            report.add("error", spec_line, f"inverted line range in anchor {item!r}", item)
            l1, l2 = l2, l1
        anchors.append(Anchor(kind, m["path"], l1, l2, m["sym"], spec_line, claim, item, pin))
    return anchors


def paragraph_before(lines: list[str], idx: int, tail: str) -> str:
    """Join the paragraph ending at lines[idx] (0-based) with `tail`, newest last."""
    parts = []
    j = idx - 1
    while j >= 0:
        prev = lines[j].strip()
        if not prev or prev.startswith("#") or prev.startswith("|") or LIST_RE.match(lines[j]):
            break
        parts.append(TAG_RE.sub("", prev).strip())
        j -= 1
    parts.reverse()
    joined = " ".join(parts + [tail]).strip(" .,;")
    return joined[-300:]


def split_front_matter(text: str) -> tuple[str | None, int]:
    """(front matter text, lines it occupies including both ``---``), or (None, 0)."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None, 0
    for n in range(1, len(lines)):
        if lines[n].rstrip() == "---":
            return "\n".join(lines[1:n]), n + 1
    return None, 0  # no closing line: not front matter, as before


def parse_doc_body(body: str, spec_line: int, report: Report) -> None:
    """Record the named doc anchors in a [doc:<name> ...] tag body."""
    for item in (s.strip() for s in body.split(";")):
        if not item:
            continue
        m = DOC_ITEM_RE.match(item)
        locs = re.split(r"[\s,]+", m["locs"].strip(" ,")) if m else []
        parsed = [DOC_LOCATOR_RE.match(loc) for loc in locs]
        if not m or not all(parsed):
            report.add("error", spec_line, f"malformed named doc anchor [doc:{item}] (expected "
                                           f"{DOC_FORMS}; for an unnamed citation put a space "
                                           "after 'doc:')", item)
            continue
        anchor = DocAnchor(m["name"], spec_line, item)
        for loc in parsed:
            if loc["sec"]:
                anchor.sections.append(loc["sec"])
                continue
            first, last = (int(loc["page"]),) * 2 if loc["page"] else (int(loc["p1"]),
                                                                        int(loc["p2"]))
            if first < 1:
                report.add("error", spec_line, f"[doc:{item}] cites page {first}; pages count "
                                               "from 1", item)
            elif last < first:
                report.add("error", spec_line, f"[doc:{item}] has an inverted page range "
                                               f"{first}-{last}", item)
            else:
                anchor.pages.append([first, last])
        report.doc_anchors.append(anchor)


def parse_spec(text: str, report: Report, strict: bool, skip: int = 0,
               board: bool = False) -> list[Anchor]:
    """Parse the spec body; the first ``skip`` lines (its front matter) are not read.

    An anchor inside a list item, on its first line or on an indented continuation line,
    takes the whole item as its claim, so a wrapped bullet whose anchors sit on a later line
    keeps the values it states. ``board`` (a board spec, whose facts carry board-spec tags
    that ``spec_check.py`` checks) turns off the untagged-fact heuristic.
    """
    anchors: list[Anchor] = []
    lines = text.split("\n")
    item_start = 0  # first line of the list item being read, 0 outside one
    items: dict[int, list[str]] = {}  # item first line -> its lines, tags removed
    # A tags-only line "arms" a block anchor; it covers the next contiguous block
    # (table or list), which may be separated from it by blank lines.
    block_state = None  # None | "armed" | "covering"
    block_anchors: list[Anchor] = []  # anchors of the armed/covering block anchor
    in_code = False
    for i, line in enumerate(lines, 1):
        if i <= skip:
            continue
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        pin = PIN_RE.match(stripped)
        if pin:
            key = pin.group(1).lower()
            side = PIN_ALIAS.get(key, key)
            entry = {"name": pin["name"], "rev": pin["rev"], "license": pin["license"],
                     "line": i}
            same = report.pin_list.setdefault(side, [])
            if any(p["name"] == pin["name"] for p in same):
                report.add("error", i, f"duplicate {side} pin name {pin['name']!r}: each pin "
                                       "on a side needs a distinct name")
            else:
                same.append(entry)
                report.pins.setdefault(side, entry)
            continue
        if PIN_START_RE.match(stripped):
            report.unread_pins.append((i, stripped))
        if LIST_RE.match(line) and not line.startswith((" ", "\t")):
            item_start = i
            items[i] = []
        elif item_start and not (stripped and line.startswith((" ", "\t"))
                                 and not LIST_RE.match(line)):
            item_start = 0
        if item_start:
            items[item_start].append(TAG_RE.sub("", stripped).strip(" -*"))
        tags = TAG_RE.findall(line)
        claim = TAG_RE.sub("", line).strip(" |-*")
        if tags and len(claim) < 40 and not stripped.startswith(("|", "-", "*")) \
                and not LIST_RE.match(line):
            # The tag closes a multi-line paragraph: the claim is the paragraph.
            claim = paragraph_before(lines, i - 1, claim)
        new_anchors: list[Anchor] = []
        for kind, body in tags:
            kind = KIND_ALIAS.get(kind, kind)
            if kind == "stale":
                report.add("error", i, f"anchor marked stale ({body.strip()}): re-verify the "
                                       "claim against the pin and remove the marker")
                continue
            if kind != "doc" and not any(item.strip() for item in body.split(";")):
                report.add("error", i, f"empty [{kind}:] anchor: give a path and lines")
                continue
            if kind == "doc":
                report.doc_tags += 1
                if not body.strip():
                    report.add("error", i, "empty [doc:] tag")
                elif not body[0].isspace():
                    parse_doc_body(body, i, report)
                else:
                    report.unnamed_docs.append((i, body.strip()))
                    if not DOC_SECTION_RE.search(body):
                        report.add("warn", i, f"[doc:] cites no section/chapter/table number: "
                                              f"{body.strip()[:60]!r}")
                continue
            new_anchors.extend(parse_tag_body(kind, body, i, claim, report))
        for a in new_anchors:
            a.group = item_start or i
        anchors.extend(new_anchors)
        if HW_REQUIRED_RE.search(line) and not any(k == "doc" for k, _ in tags):
            report.add("warn", i, "[hw-required] with no [doc:] on the line — if no document "
                                  "backs it, label it [as-implemented]")
        if not stripped:
            if block_state == "covering":
                block_state = None
                block_anchors = []
            continue
        # A tags-only continuation line of a list item belongs to the item, not to a block.
        tags_only = bool(tags) and not claim and not (item_start and item_start != i)
        if tags_only:
            block_state = "armed"
            block_anchors = new_anchors
            continue
        if block_state == "armed":
            block_state = "covering"
        if block_state == "covering":
            # The block anchor's claim is the block it covers.
            for a in block_anchors:
                a.claim = (a.claim + " / " if a.claim else "") + stripped
            continue
        if tags:
            continue
        # No tag on this line and no block anchor in force: is it a fact?
        is_row = stripped.startswith("|") and not TABLE_SEP_RE.match(stripped)
        is_item = bool(LIST_RE.match(line))
        if not (is_row or is_item):
            continue
        header_row = is_row and i < len(lines) and TABLE_SEP_RE.match(lines[i].strip() or "x")
        if header_row:
            continue
        if board:
            continue
        if strict or FACT_HINT_RE.search(stripped):
            report.add("warn" if not strict else "error", i,
                       "fact-bearing line carries no [src:]/[tgt:]/[doc:] tag: "
                       + stripped[:80])
    for a in anchors:
        text = " ".join(t for t in items.get(a.group, []) if t)
        if text:
            a.claim = text[-300:]
    report.anchors = len(anchors)
    return anchors


# --------------------------------------------------------------------------- checks


def find_symbol(file_lines: list[str], symbol: str, lo: int, hi: int) -> int | None:
    """First 1-based line in [lo, hi] containing symbol as a whole word, else None."""
    pat = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(symbol) + r"(?![A-Za-z0-9_])")
    lo = max(lo, 1)
    hi = min(hi, len(file_lines))
    for n in range(lo, hi + 1):
        if pat.search(file_lines[n - 1]):
            return n
    return None


def resolve(anchor: Anchor, repo: Repo, report: Report) -> list[str] | None:
    file_lines = repo.lines(anchor.path)
    where = f"pin {anchor.pin}: " if anchor.pin else ""
    if file_lines is None:
        report.add("error", anchor.spec_line,
                   f"{where}{anchor.path} does not exist at {repo.rev}", anchor.raw)
        return None
    if anchor.l2 > len(file_lines):
        report.add("error", anchor.spec_line,
                   f"{where}{anchor.path} has {len(file_lines)} lines; anchor cites "
                   f"{anchor.l1}-{anchor.l2}", anchor.raw)
        return None
    cited = file_lines[anchor.l1 - 1: anchor.l2]
    if anchor.symbol:
        # The symbol names the cited definition or the definition enclosing the
        # cited lines, so it may legitimately precede the range.
        if find_symbol(file_lines, anchor.symbol, anchor.l1 - SYMBOL_BEFORE, anchor.l2) is None:
            anywhere = find_symbol(file_lines, anchor.symbol, 1, len(file_lines))
            if anywhere is None:
                report.add("error", anchor.spec_line,
                           f"symbol {anchor.symbol!r} is not in {anchor.path}", anchor.raw)
            else:
                report.add("warn", anchor.spec_line,
                           f"symbol {anchor.symbol!r} first appears at line {anywhere}, not "
                           f"within {SYMBOL_BEFORE} lines before the cited range "
                           f"{anchor.l1}-{anchor.l2}", anchor.raw)
    if all(not l.strip() for l in cited):
        report.add("warn", anchor.spec_line,
                   f"cited range {anchor.path}:{anchor.l1}-{anchor.l2} is blank", anchor.raw)
    return cited


def check_hex_consistency(anchors: list[Anchor], cited_by_anchor: dict[int, list[str]], report: Report):
    """Per claim: at least one hex literal in the claim must appear in the union of all lines
    cited by that claim's anchors. A claim is a list item (every anchor in it, on any of its
    lines) or, outside a list, one spec line."""
    by_line: dict[int, list[int]] = {}
    for idx, a in enumerate(anchors):
        if idx in cited_by_anchor:
            by_line.setdefault(a.group or a.spec_line, []).append(idx)
    for spec_line, idxs in by_line.items():
        claim_hex = hex_set(anchors[idxs[0]].claim)
        if not claim_hex:
            continue
        cited_hex = set()
        for idx in idxs:
            cited_hex |= hex_set("\n".join(cited_by_anchor[idx]))
        if not (claim_hex & cited_hex):
            shown = ", ".join("0x" + h for h in sorted(claim_hex)[:4])
            where = "; ".join(anchors[idx].raw for idx in idxs)
            report.add("warn", anchors[idxs[0]].spec_line,
                       f"none of the claim's hex literals ({shown}) appear in the lines cited by "
                       f"this line ({where}) — wrong value, or cite the offset definition too?")


def check_drift(anchor: Anchor, pinned: Repo, new: Repo, report: Report):
    old_blob, new_blob = pinned.blob(anchor.path), new.blob(anchor.path)
    if new_blob is None:
        report.stale.append((anchor.spec_line, anchor.raw))
        report.add("error", anchor.spec_line,
                   f"{anchor.path} is gone at {new.rev}", anchor.raw)
        return
    if old_blob == new_blob:
        return
    old_lines, new_lines = pinned.lines(anchor.path), new.lines(anchor.path)
    if old_lines is None or new_lines is None:
        return
    old_cited = old_lines[anchor.l1 - 1: anchor.l2]
    new_cited = new_lines[anchor.l1 - 1: anchor.l2]
    if old_cited == new_cited:
        return  # file changed elsewhere; this range is byte-identical
    # Same text may simply have moved: look for it elsewhere in the new file.
    moved_to = None
    if old_cited and any(l.strip() for l in old_cited):
        n = len(old_cited)
        for start in range(0, max(len(new_lines) - n + 1, 0)):
            if new_lines[start: start + n] == old_cited:
                moved_to = start + 1
                break
    if moved_to is not None:
        new_l2 = moved_to + (anchor.l2 - anchor.l1)
        span = f"{moved_to}-{new_l2}" if new_l2 != moved_to else f"{moved_to}"
        new_raw = (f"{anchor.pin}: " if anchor.pin else "") + f"{anchor.path}:{span}" \
            + (f" ({anchor.symbol})" if anchor.symbol else "")
        report.moves.append((anchor.spec_line, anchor.raw, new_raw))
        report.add("warn", anchor.spec_line,
                   f"cited text moved: {anchor.path}:{anchor.l1}-{anchor.l2} is now "
                   f"{span} at {new.rev} (content unchanged; update the line numbers)",
                   anchor.raw)
        return
    hint = ""
    if anchor.symbol:
        at = find_symbol(new_lines, anchor.symbol, 1, len(new_lines))
        hint = f"; symbol {anchor.symbol!r} now at line {at}" if at else \
               f"; symbol {anchor.symbol!r} no longer in file"
    report.stale.append((anchor.spec_line, anchor.raw))
    report.add("error", anchor.spec_line,
               f"cited text changed: {anchor.path}:{anchor.l1}-{anchor.l2} differs at "
               f"{new.rev}{hint} — re-verify this claim", anchor.raw)


# --------------------------------------------------------------------------- output


def render_show(anchors: list[Anchor], repos: dict, keys: dict, out):
    for idx, a in enumerate(anchors):
        repo = repos.get(keys.get(idx))
        print(f"--- spec L{a.spec_line}: {a.claim[:240]}", file=out)
        print(f"    [{a.kind}: {a.raw}]", file=out)
        if repo is None:
            print("    (repository for this anchor not given)", file=out)
            continue
        file_lines = repo.lines(a.path)
        if file_lines is None or a.l2 > len(file_lines):
            print("    (unresolvable — see findings)", file=out)
            continue
        for n in range(a.l1, a.l2 + 1):
            print(f"    {n:6d} | {file_lines[n - 1]}", file=out)
        print(file=out)


def rewrite_repos_ref(lines: list[str], name_line: int, new_full: str) -> bool:
    """Set the ``ref:`` of the resources.repos entry whose ``name:`` is on name_line (1-based).

    The entry runs from its ``- `` line to the next line indented no deeper than that dash.
    """
    def indent(line: str) -> int:
        return len(line) - len(line.lstrip())

    first = name_line - 1
    while first > 0 and not lines[first].lstrip().startswith("- "):
        first -= 1
    dash = indent(lines[first])
    for j in range(first, len(lines)):
        line = lines[j]
        if j > first and line.strip() and indent(line) <= dash:
            break
        m = re.match(r"^(\s*(?:-\s+)?ref:\s*)(['\"]?)[^'\"#\s]+\2(.*)$", line)
        if m:
            lines[j] = f"{m.group(1)}{new_full}{m.group(3)}"
            return True
    return False


def rewrite_spec(spec_path: str, text: str, report: Report, new_rev: str,
                 pin: dict | None, new_full: str | None = None) -> int:
    """Apply moves, stale markers and the new revision of the drifted Source pin to the
    spec file. Returns edits made. A pin read from a board spec's resources.repos entry gets
    its ``ref:`` set to ``new_full``, the full commit id, since a board spec pins commits."""
    lines = text.split("\n")
    edits = 0
    for spec_line, old_raw, new_raw in report.moves:
        idx = spec_line - 1
        if old_raw in lines[idx]:
            lines[idx] = lines[idx].replace(old_raw, new_raw, 1)
            edits += 1
    old_rev = pin["rev"] if pin else "?"
    for spec_line, raw in report.stale:
        idx = spec_line - 1
        tag_re = re.compile(r"(\[(?:src|impl):[^\]]*" + re.escape(raw) + r"[^\]]*\])")
        new_line, n = tag_re.subn(r"\1 [stale: was " + old_rev + "]", lines[idx], count=1)
        if n:
            lines[idx] = new_line
            edits += 1
    if pin is not None:
        idx = pin["line"] - 1
        m = PIN_RE.match(lines[idx].strip())
        if m and m["name"] == pin["name"]:
            license_ = f" {m['license']}" if m["license"] else ""
            body_rev = new_full if "repos_line" in pin and new_full else new_rev
            lines[idx] = f"{m.group(1)} pin: {m['name']}@{body_rev}{license_}"
            edits += 1
        if "repos_line" in pin:
            if rewrite_repos_ref(lines, pin["repos_line"], new_full or new_rev):
                edits += 1
            else:
                report.add("error", pin["repos_line"], f"--rewrite could not find the ref: of "
                                                       f"resources.repos entry {pin['name']!r}; "
                                                       "set it by hand")
    Path(spec_path).write_text("\n".join(lines), encoding="utf-8")
    return edits


def render_report(report: Report, out):
    print(f"spec: {report.spec}", file=out)
    for side, pins in sorted(report.pin_list.items()):
        for pin in pins:
            license_ = f" ({pin['license']})" if pin["license"] else ""
            print(f"{side} pin: {pin['name']}@{pin['rev']}{license_}", file=out)
    print(f"anchors: {report.anchors}  doc tags: {report.doc_tags}", file=out)
    for doc in report.docs:
        pages = f", {doc['pages']} pages" if doc["pages"] else ""
        print(f"doc {doc['name']}: {doc['title']}{pages}", file=out)
    if report.license_gate:
        accepts = ", ".join(report.license_gate["accepts"]) or "none"
        print(f"license gate: root {report.license_gate['root']} accepts: {accepts}", file=out)
    errors = report.errors
    warns = [f for f in report.findings if f.level == "warn"]
    for f in sorted(report.findings, key=lambda f: (f.level != "error", f.spec_line)):
        tag = "ERROR" if f.level == "error" else "warn "
        print(f"{tag} L{f.spec_line}: {f.message}", file=out)
    print(f"result: {'FAIL' if errors else 'PASS'} "
          f"({len(errors)} errors, {len(warns)} warnings)", file=out)


# --------------------------------------------------------------------------- licenses


def board_expert_scripts() -> Path:
    """board-expert's scripts directory, beside this skill (symlinks resolved)."""
    return Path(__file__).resolve().parent.parent.parent / "board-expert" / "scripts"


def load_license_tools():
    """Import board-expert's spdx and spec_check modules, or return None."""
    path = str(board_expert_scripts())
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        import spdx  # noqa: PLC0415
        import spec_check  # noqa: PLC0415
    except ImportError:
        return None
    return spdx, spec_check


def check_pin_licenses(report: Report, spdx) -> None:
    """Every license a pin states must parse as an SPDX expression."""
    for side, pins in report.pin_list.items():
        for pin in pins:
            if pin["license"] is None:
                continue
            try:
                spdx.parse(pin["license"])
            except spdx.SpdxError as exc:
                report.add("error", pin["line"], f"{side} pin {pin['name']!r}: license "
                                                 f"{pin['license']!r} is not an SPDX expression: {exc}")


def read_root_accepts(root: str, spec_check, report: Report, require: bool = False):
    """The root's accepts list (canonical ids), or None when the gate cannot run (reported).

    ``require`` (--require-license) makes a missing ``license:`` an error too.

    Raises SystemExit (usage error) when the root has no marker or the marker does not parse.
    """
    marker_path = Path(root) / "board-specs.yaml"
    if not marker_path.is_file():
        raise SystemExit(f"error: --root {root}: no board-specs.yaml (not a spec root)")
    try:
        marker = spec_check.load_yaml(marker_path.read_text(), spec_check.pyyaml_available())
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"error: --root {root}: cannot parse board-specs.yaml: {exc}")
    if not isinstance(marker, dict):
        raise SystemExit(f"error: --root {root}: board-specs.yaml is not a mapping")
    found: list = []
    accepts = spec_check.check_root_license(marker, str(marker_path), require, found)
    for f in found:
        if f.level == "error":  # a malformed license: or accepts: in the marker
            report.add("error", 0, f"--root {root}: {f.message}")
    if accepts is None:
        report.add("error", 0, f"license gate: root {root} declares no accepts: list, so the "
                               "gate cannot run (add accepts: to its board-specs.yaml; [] "
                               "accepts no source)")
    return accepts


def apply_license_gate(anchors: list[Anchor], keys: dict, report: Report, root: str,
                       accepts: tuple, spdx) -> None:
    """Fail each anchor whose pin's license the root does not accept (design LS-R4)."""
    listed = ", ".join(accepts) or "none"
    verdicts = {}  # (side, pin name) -> None when accepted, else why not
    for side, pins in report.pin_list.items():
        for pin in pins:
            lic = pin["license"]
            if lic is None:
                why = ", which states no license"
            else:
                try:
                    ok, _ = spdx.check(lic, accepts)
                    why = None if ok else f" ({lic}), which root {root} does not accept"
                except spdx.SpdxError:
                    why = f" ({lic}), which is not an SPDX expression"
            verdicts[(side, pin["name"])] = why
    cited = set()
    for idx, a in enumerate(anchors):
        if idx not in keys:
            continue  # an unknown or missing pin name, already an error
        side = SIDE[a.kind]
        name = keys[idx][1]
        shown = f"[{a.kind}:{'' if a.pin else ' '}{a.raw}]"
        if name is None:
            report.add("error", a.spec_line,
                       f"license gate: {shown} has no {side} pin, so its source license is "
                       f"unknown; state the pin with its SPDX license (root {root} accepts: "
                       f"{listed})", a.raw)
            continue
        cited.add((side, name))
        why = verdicts[(side, name)]
        if why is not None:
            report.add("error", a.spec_line,
                       f"license gate: {shown} cites {side} pin {name!r}{why} "
                       f"(accepts: {listed})", a.raw)
    for side, pins in report.pin_list.items():
        for pin in pins:
            why = verdicts[(side, pin["name"])]
            if why is not None and (side, pin["name"]) not in cited:
                report.add("error", pin["line"],
                           f"license gate: {side} pin {pin['name']!r}{why} (accepts: "
                           f"{listed}); no anchor cites it: remove the pin, or place the spec "
                           "in a root that accepts it")


# --------------------------------------------------------------------------- documents


def entry_line(front: str, name, fallback: int) -> int:
    """The spec line of a registry entry's ``name:`` (front matter starts at line 2)."""
    if isinstance(name, str):
        pat = re.compile(r"^\s*(?:-\s*)?name:\s*['\"]?" + re.escape(name) + r"['\"]?\s*$")
        for n, line in enumerate(front.split("\n")):
            if pat.match(line):
                return n + 2
    return fallback


def read_front_matter(front: str | None, skip: int, report: Report, spec_check):
    """Decide whether a leading ``---`` block is front matter; return (meta, lines to skip).

    It is front matter when it holds a ``docs:`` line, or else parses as a YAML mapping and
    carries no anchor tag. Otherwise it is body text (between horizontal rules, as before
    LS3) and is scanned like the rest. A block with a ``docs:`` line that cannot be read is
    an error.
    """
    if front is None:
        return None, 0
    meant = any(line.startswith(("docs:",) + BOARD_KEYS) for line in front.split("\n"))
    if not meant and TAG_RE.search(front):
        return None, 0
    if spec_check is None:
        if meant:
            report.add("error", 1, "spec front matter cannot be read: board-expert's "
                                   f"spec_check.py was not found at {board_expert_scripts()} "
                                   "(install board-expert beside this skill)")
            return None, skip
        return None, 0
    try:
        meta = spec_check.load_yaml(front, spec_check.pyyaml_available())
    except Exception as exc:  # noqa: BLE001
        if meant:
            report.add("error", 1, f"front matter does not parse: {exc}")
            return None, skip
        return None, 0
    if not isinstance(meta, dict):
        return None, 0
    return meta, skip


def read_docs_registry(front: str | None, meta: dict | None, report: Report) -> dict:
    """Validate the front matter's ``docs:`` registry; return {name: entry}.

    An entry keeps its name when other fields are wrong, so anchors citing it are judged on
    their own; a malformed ``sha256`` is dropped (no hash check), a malformed ``pages``
    ignored (no page check), each with its error.
    """
    if meta is None or "docs" not in meta:
        return {}
    docs_line = next((n + 2 for n, line in enumerate(front.split("\n"))
                      if line.startswith("docs:")), 1)
    entries = meta["docs"]
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        report.add("error", docs_line, "docs: must be a list of documents (name, title, url, "
                                       "sha256, optional pages and file)")
        return {}
    registry: dict = {}
    for idx, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            report.add("error", docs_line, f"docs: entry {idx} is not a mapping")
            continue
        name = entry.get("name")
        line = entry_line(front, name, docs_line)
        label = f"docs: entry {idx} ({name!r})" if isinstance(name, str) else f"docs: entry {idx}"

        def bad(msg, label=label, line=line):
            report.add("error", line, f"{label}: {msg}")

        if not isinstance(name, str) or not re.fullmatch(PIN_NAME, name):
            bad("name: must be a short identifier (letters, digits, '.', '_', '-'), as in "
                "[doc:<name> p.N]")
            continue
        if name in registry:
            bad(f"duplicate document name {name!r}: each document needs a distinct name")
            continue
        for key in ("title", "url"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                bad(f"{key}: is required (a non-empty string)")
        for key in entry:
            if key not in DOC_KEYS:
                report.add("warn", line, f"{label}: unknown key {key!r} (known: "
                                         f"{', '.join(DOC_KEYS)})")
        doc = {"name": name, "title": entry.get("title"), "url": entry.get("url"),
               "sha256": None, "pages": None, "file": None, "line": line}
        sha = entry.get("sha256")
        if "sha256" not in entry:
            bad("sha256: is required (the document file's SHA-256, 64 hex digits)")
        elif not isinstance(sha, str) or not SHA256_RE.match(sha):
            bad(f"sha256: {sha!r} is not 64 hex digits (quote it if it is all digits)")
        else:
            doc["sha256"] = sha.lower()
        if "pages" in entry:
            pages = entry["pages"]
            if isinstance(pages, bool) or not isinstance(pages, int) or pages < 1:
                bad(f"pages: {pages!r} is not a positive page count")
            else:
                doc["pages"] = pages
        if "file" in entry:
            rel = entry["file"]
            parts = Path(rel).parts if isinstance(rel, str) else ()
            if not isinstance(rel, str) or not rel.strip() or Path(rel).is_absolute() \
                    or ".." in parts:
                bad(f"file: {rel!r} must be a relative path inside --docs-dir")
            else:
                doc["file"] = rel
        registry[name] = doc
    report.docs = list(registry.values())
    return registry


def read_repos_pins(front: str | None, meta: dict | None, report: Report) -> None:
    """A board spec's ``resources.repos`` entries are its Source pins.

    A board spec (``board-expert/SPEC-FORMAT.md``) states each source tree once, as a
    ``resources.repos`` entry with ``name``, ``ref`` and ``license``; its ``[src]`` facts cite
    ``[src:<name>: path:L]``. Each entry with a usable name and a ``ref`` becomes a Source pin
    here, so the anchors resolve and the license gate reads the same license
    ``spec_check.py`` does. A ``Source pin:`` line of the same name may also be present; it
    must state the same revision and license.
    """
    resources = (meta or {}).get("resources")
    repos = resources.get("repos") if isinstance(resources, dict) else None
    if not isinstance(repos, list):
        return
    same = report.pin_list.setdefault("source", [])
    for entry in repos:
        if not isinstance(entry, dict):
            continue
        name, ref, lic = entry.get("name"), entry.get("ref"), entry.get("license")
        if not isinstance(name, str) or not re.fullmatch(PIN_NAME, name) or ref is None:
            continue
        ref = str(ref)
        lic = str(lic).strip() if lic is not None else None
        line = entry_line(front, name, 1)
        stated = next((p for p in same if p["name"] == name), None)
        if stated is not None:
            stated["repos_line"] = line
            if stated["rev"] != ref or (stated["license"] or None) != lic:
                report.add("error", stated["line"],
                           f"Source pin {name!r} ({stated['rev']} {stated['license'] or 'no license'}) "
                           f"disagrees with resources.repos entry {name!r} ({ref} "
                           f"{lic or 'no license'}); state the pin once, in resources.repos")
            continue
        entry_pin = {"name": name, "rev": ref, "license": lic, "line": line,
                     "url": entry.get("url"), "repos_line": line}
        same.append(entry_pin)
        report.pins.setdefault("source", entry_pin)
    if not same:
        del report.pin_list["source"]


def check_doc_anchors(report: Report, registry: dict) -> None:
    """Every named doc anchor must name a listed document, at a page within it."""
    listed = ", ".join(registry) or "none"
    for a in report.doc_anchors:
        doc = registry.get(a.name)
        if doc is None:
            report.add("error", a.spec_line, f"[doc:{a.raw}] names document {a.name!r}, but "
                                             f"the spec's docs: registry lists: {listed} (for "
                                             "an unnamed citation put a space after 'doc:')",
                       a.raw)
            continue
        if doc["pages"] is None:
            continue
        for first, last in a.pages:
            if last > doc["pages"]:
                shown = f"page {first}" if first == last else f"pages {first}-{last}"
                report.add("error", a.spec_line,
                           f"[doc:{a.raw}] cites {shown}, but document {a.name!r} "
                           f"({doc['title']}) has {doc['pages']} pages", a.raw)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_doc_hashes(report: Report, registry: dict, docs_dir: str) -> None:
    """Hash each listed document's local file under docs_dir against its sha256."""
    for doc in registry.values():
        if doc["sha256"] is None:
            continue  # malformed or missing: already an error
        rel = doc["file"] or f"{doc['name']}.pdf"
        path = Path(docs_dir) / rel
        if not path.is_file():
            report.add("warn", doc["line"], f"document {doc['name']!r}: {path} not found; "
                                            "hash not checked")
            continue
        actual = sha256_file(path)
        if actual != doc["sha256"]:
            report.add("error", doc["line"],
                       f"document {doc['name']!r} ({doc['title']}): {path} has sha256 {actual}, "
                       f"but the registry records {doc['sha256']}")


def require_named_docs(report: Report, root: str) -> None:
    """In a root that accepts no source, every [doc:] tag must name a listed document."""
    for line, body in report.unnamed_docs:
        report.add("error", line,
                   f"unnamed [doc: {body[:60]}]: root {root} accepts no source, so documents "
                   "are its specs' only provenance and --require-license requires named ones: "
                   "list the document under docs: in the front matter and cite "
                   "[doc:<name> p.N]")


# --------------------------------------------------------------------------- main


def bind_repos(values: list[str], kind: str, pins: list[dict], flag: str) -> dict:
    """Bind --repo/--target-repo values to the spec's pins on one side.

    Returns {(kind, pin name or None): Repo}. Raises SystemExit (usage error) when a
    value names no pin of the spec, a bare value is ambiguous, or a rev is missing.
    """
    side = SIDE[kind]
    repos: dict = {}
    for value in values:
        named = NAMED_REPO_RE.match(value)
        if named and not Path(value.partition("@")[0]).exists():
            name, value = named["pin"], named["value"]
            matches = [p for p in pins if p["name"] == name]
            if not matches:
                have = ", ".join(p["name"] for p in pins) or "none"
                raise SystemExit(f"error: --{flag} names pin {name!r}, but the spec's "
                                 f"{side} pins are: {have}")
            pin = matches[0]
        else:
            if len(pins) > 1:
                have = ", ".join(p["name"] for p in pins)
                raise SystemExit(f"error: the spec has {len(pins)} {side} pins ({have}); "
                                 f"name one: --{flag} NAME=PATH[@REV]")
            pin = pins[0] if pins else None
            name = pin["name"] if pin else None
        key = (kind, name)
        if key in repos:
            raise SystemExit(f"error: --{flag} given twice for "
                             + (f"pin {name!r}" if name else f"the {side} side"))
        path, _, rev = value.partition("@")
        if not rev:
            if pin is None:
                raise SystemExit(f"error: --{flag} has no @rev and the spec states no "
                                 f"'{side.capitalize()} pin:' line")
            rev = pin["rev"]
        repos[key] = Repo(path, rev)
    return repos


def anchor_keys(anchors: list[Anchor], report: Report, board: bool = False) -> dict[int, tuple]:
    """Map each anchor index to its (kind, pin name or None) key; report anchors that
    name an unknown pin, or name none on a side with several pins."""
    keys = {}
    for idx, a in enumerate(anchors):
        side = SIDE[a.kind]
        pins = report.pin_list.get(side, [])
        if a.pin is not None:
            if not any(p["name"] == a.pin for p in pins):
                have = ", ".join(p["name"] for p in pins) or "none"
                report.add("error", a.spec_line, f"anchor names pin {a.pin!r}, but the spec's "
                                                 f"{side} pins are: {have}", a.raw)
                continue
            keys[idx] = (a.kind, a.pin)
        elif board and pins and all("repos_line" in p for p in pins):
            report.add("error", a.spec_line, f"anchor names no pin: in a board spec write "
                                             f"[{a.kind}:<repo>: {a.raw}] with the name of a "
                                             "resources.repos entry", a.raw)
        elif len(pins) > 1:
            report.add("error", a.spec_line, f"anchor names no pin, but the spec has {len(pins)} "
                                             f"{side} pins: write [{a.kind}:<pin>: {a.raw}]",
                       a.raw)
        else:
            keys[idx] = (a.kind, pins[0]["name"] if pins else None)
    return keys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("spec", help="path to the spec markdown file")
    ap.add_argument("--repo", "--impl-repo", metavar="[NAME=]PATH[@REV]", action="append",
                    default=[],
                    help="source repository for [src:]/[impl:] anchors; repeat with NAME= for "
                         "each named Source/Impl pin (REV defaults to that pin)")
    ap.add_argument("--target-repo", "--ref-repo", metavar="[NAME=]PATH[@REV]", action="append",
                    default=[],
                    help="target-OS repository for [tgt:]/[ref:] anchors; NAME= as for --repo "
                         "(REV defaults to the Target/Ref pin)")
    ap.add_argument("--show", action="store_true",
                    help="print each claim with its cited source lines (review sheet)")
    ap.add_argument("--drift", metavar="REV",
                    help="compare [src:] anchors at the pin against REV in the source repo")
    ap.add_argument("--drift-pin", metavar="NAME",
                    help="with --drift: the Source pin to compare, when the spec has several")
    ap.add_argument("--rewrite", action="store_true",
                    help="with --drift: rewrite moved anchors and that Source pin in the spec")
    ap.add_argument("--root", metavar="DIR",
                    help="license gate: fail anchors whose pin's license DIR's board-specs.yaml "
                         "does not list in accepts:")
    ap.add_argument("--require-license", action="store_true",
                    help="with --root: DIR's marker must state license: as well as accepts:, "
                         "and in a root that accepts no source every [doc:] tag must name a "
                         "document from the spec's docs: registry")
    ap.add_argument("--docs-dir", metavar="DIR",
                    help="hash each document in the spec's docs: registry from DIR/<file> "
                         "(default DIR/<name>.pdf) and fail on a mismatch; nothing is fetched")
    ap.add_argument("--strict", action="store_true",
                    help="every table row and list item must carry a tag, not just hex/bit facts")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--output", "-o", help="write the report here instead of stdout")
    args = ap.parse_args(argv)

    try:
        text = Path(args.spec).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.require_license and not args.root:
        print("error: --require-license needs --root DIR", file=sys.stderr)
        return 2
    if args.docs_dir and not Path(args.docs_dir).is_dir():
        print(f"error: --docs-dir {args.docs_dir} is not a directory", file=sys.stderr)
        return 2

    report = Report(spec=args.spec)
    tools = load_license_tools()
    front, skip = split_front_matter(text)
    meta, skip = read_front_matter(front, skip, report, tools[1] if tools else None)
    board = is_board_spec(meta)
    anchors = parse_spec(text, report, args.strict, skip, board)
    read_repos_pins(front, meta, report)
    registry = read_docs_registry(front, meta, report)
    check_doc_anchors(report, registry)
    if args.docs_dir:
        check_doc_hashes(report, registry, args.docs_dir)
    if tools is None:
        if args.root:
            print(f"error: --root needs board-expert's scripts beside this skill "
                  f"({board_expert_scripts()}), which were not found", file=sys.stderr)
            return 2
        if any(p["license"] for pins in report.pin_list.values() for p in pins):
            report.add("error", 0, "pin licenses cannot be validated: board-expert's spdx.py "
                                   f"was not found at {board_expert_scripts()} (install "
                                   "board-expert beside this skill)")
    else:
        check_pin_licenses(report, tools[0])
    for line, pin_text in report.unread_pins:
        report.add("error" if args.root else "warn", line,
                   f"line starts like a pin but is not read as one: {pin_text[:80]!r} (expected "
                   "'<Side> pin: <name>@<rev> [<SPDX expression>]')")
    accepts = None
    if args.root:
        try:
            accepts = read_root_accepts(args.root, tools[1], report, args.require_license)
        except SystemExit as e:
            print(e, file=sys.stderr)
            return 2
        report.license_gate = {"root": args.root, "accepts": list(accepts or ())}
        if args.require_license and accepts is not None and not accepts:
            require_named_docs(report, args.root)

    if args.rewrite and not args.drift:
        print("error: --rewrite needs --drift REV", file=sys.stderr)
        return 2
    if args.drift_pin and not args.drift:
        print("error: --drift-pin needs --drift REV", file=sys.stderr)
        return 2
    try:
        repos: dict = {}
        repos.update(bind_repos(args.repo, "src", report.pin_list.get("source", []), "repo"))
        repos.update(bind_repos(args.target_repo, "tgt", report.pin_list.get("target", []),
                                "target-repo"))
        drift_key = drift_repo = drift_pin = None
        if args.drift:
            src_keys = [k for k in repos if k[0] == "src"]
            if args.drift_pin:
                drift_key = ("src", args.drift_pin)
                if drift_key not in repos:
                    raise SystemExit(f"error: --drift-pin {args.drift_pin!r} has no --repo "
                                     f"{args.drift_pin}=PATH")
            elif len(src_keys) == 1:
                drift_key = src_keys[0]
            elif not src_keys:
                raise SystemExit("error: --drift needs --repo")
            else:
                raise SystemExit("error: several source repositories given; choose one with "
                                 "--drift-pin NAME")
            drift_repo = Repo(repos[drift_key].path, args.drift)
            drift_pin = next((p for p in report.pin_list.get("source", [])
                              if p["name"] == drift_key[1]), None)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    for (kind, name), repo in sorted(repos.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        pin = next((p for p in report.pin_list.get(SIDE[kind], []) if p["name"] == name), None)
        if pin and not repo.full_rev.startswith(pin["rev"]) and pin["rev"] != repo.rev:
            report.add("warn", 0, f"{SIDE[kind]} pin {name} in spec is {pin['rev']} but "
                                  f"checking at {repo.rev} ({repo.full_rev[:12]})")

    keys = anchor_keys(anchors, report, board)
    if accepts is not None:
        apply_license_gate(anchors, keys, report, args.root, accepts, tools[0])
    unresolved: dict[str, int] = {}
    for idx, a in enumerate(anchors):
        if idx in keys and keys[idx] not in repos:
            unresolved[a.kind] = unresolved.get(a.kind, 0) + 1
    for kind, n in sorted(unresolved.items()):
        report.add("warn", 0, f"{n} [{kind}:] anchors not resolved (no repository given)")

    cited_by_anchor: dict[int, list[str]] = {}
    for idx, a in enumerate(anchors):
        repo = repos.get(keys.get(idx))
        if repo is None:
            continue
        cited = resolve(a, repo, report)
        if cited is not None:
            cited_by_anchor[idx] = cited
            if drift_repo is not None and keys[idx] == drift_key:
                check_drift(a, repo, drift_repo, report)
    check_hex_consistency(anchors, cited_by_anchor, report)

    if args.rewrite:
        n = rewrite_spec(args.spec, text, report, args.drift, drift_pin, drift_repo.full_rev)
        report.add("warn", 0, f"made {n} edits in {args.spec}: pin is now {args.drift}; "
                              f"{len(report.stale)} anchors marked [stale:] for re-verification")

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        if args.show:
            render_show(anchors, repos, keys, out)
        if args.json:
            payload = asdict(report)
            payload["result"] = "FAIL" if report.errors else "PASS"
            json.dump(payload, out, indent=2)
            print(file=out)
        else:
            render_report(report, out)
    finally:
        if out is not sys.stdout:
            out.close()
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
