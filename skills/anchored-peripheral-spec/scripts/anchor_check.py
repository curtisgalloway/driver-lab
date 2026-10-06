#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Curtis Galloway
# SPDX-License-Identifier: Apache-2.0
"""Check the source anchors in a source-anchored peripheral spec.

A source-anchored spec cites where each fact came from with inline tags:

    [src: drivers/net/ethernet/cadence/macb_main.c:2311-2340 (macb_init_hw)]
    [tgt: src/devices/block/drivers/sdhci/sdhci.cc:88 (Sdhci::Init)]
    [doc: Zynq-7000 TRM UG585 §16.3.2]

``src`` anchors resolve against the source repository, ``tgt`` anchors against
the target-OS repository, both at a pinned commit; ``doc`` tags are citations
to documents and are not resolved.  Several anchors may share one tag,
separated by ``;``.  A line consisting only of tags anchors the table or list
that follows it (a "block anchor").

The spec states its pins on lines of the form::

    Source pin: <name-or-url>@<commit> [<SPDX license expression>]
    Target pin: <name-or-url>@<commit> [<SPDX license expression>]

A spec may state several pins per side, each with a distinct name, and cite one
by name: ``[src:linux: drivers/net/foo.c:120]`` resolves against the ``linux``
Source pin.  An anchor without a pin name resolves against the side's only pin,
and is an error when the side has several.  Give one repository per pin with
``--repo NAME=PATH[@REV]`` (repeatable); a bare ``--repo PATH[@REV]`` serves a
spec with at most one Source pin, as before.  The license is recorded and
reported here; ``--root`` (a later change) checks it against the spec root.

The ``reference-driver-review`` skill uses the same machinery under different
names: ``[impl:]`` is an alias of ``[src:]`` (with ``Impl pin:`` and
``--impl-repo``) and ``[ref:]`` an alias of ``[tgt:]`` (with ``Ref pin:`` and
``--ref-repo``), so a review's implementation-side anchors get drift tracking.

Modes (all stdlib; needs ``git`` on PATH):

  default   resolve every anchor at the pin: path exists, line range in bounds,
            symbol (if given) present in or near the range; flag fact-bearing
            lines that carry no tag at all, claims whose hex literals do not
            appear in the lines they cite, ``[hw-required]`` labels with no
            ``[doc:]`` backing, and ``[doc:]`` tags with no section number.
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
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

TAG_RE = re.compile(r"\[(src|tgt|impl|ref|doc|stale):\s*([^\]]*)\]")
KIND_ALIAS = {"impl": "src", "ref": "tgt"}
PIN_ALIAS = {"impl": "source", "ref": "target"}
ANCHOR_RE = re.compile(
    r"^(?P<path>[^\s:()]+):(?P<l1>\d+)(?:-(?P<l2>\d+))?(?:\s*\((?P<sym>[^)]+)\))?$"
)
# The optional license is SPDX-shaped: identifiers joined by OR, AND or WITH, with
# parentheses. Other trailing text ("@abc (v6.1 tag)") leaves the line unmatched, as before.
SPDX_TOKEN = r"\(*[A-Za-z0-9][A-Za-z0-9.+-]*\)*"
PIN_RE = re.compile(r"^(Source|Target|Impl|Ref) pin:\s*(?P<name>\S+?)@(?P<rev>[0-9A-Za-z._/-]+)"
                    rf"(?:\s+(?P<license>{SPDX_TOKEN}(?:\s+(?:OR|AND|WITH)\s+{SPDX_TOKEN})*))?\s*$")
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
    findings: list = field(default_factory=list)
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


def parse_spec(text: str, report: Report, strict: bool) -> list[Anchor]:
    anchors: list[Anchor] = []
    lines = text.split("\n")
    # A tags-only line "arms" a block anchor; it covers the next contiguous block
    # (table or list), which may be separated from it by blank lines.
    block_state = None  # None | "armed" | "covering"
    block_anchors: list[Anchor] = []  # anchors of the armed/covering block anchor
    in_code = False
    for i, line in enumerate(lines, 1):
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
            if kind == "doc":
                report.doc_tags += 1
                if not body.strip():
                    report.add("error", i, "empty [doc:] tag")
                elif not DOC_SECTION_RE.search(body):
                    report.add("warn", i, f"[doc:] cites no section/chapter/table number: "
                                          f"{body.strip()[:60]!r}")
                continue
            new_anchors.extend(parse_tag_body(kind, body, i, claim, report))
        anchors.extend(new_anchors)
        if HW_REQUIRED_RE.search(line) and not any(k == "doc" for k, _ in tags):
            report.add("warn", i, "[hw-required] with no [doc:] on the line — if no document "
                                  "backs it, label it [as-implemented]")
        if not stripped:
            if block_state == "covering":
                block_state = None
                block_anchors = []
            continue
        tags_only = bool(tags) and not claim
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
        if strict or FACT_HINT_RE.search(stripped):
            report.add("warn" if not strict else "error", i,
                       "fact-bearing line carries no [src:]/[tgt:]/[doc:] tag: "
                       + stripped[:80])
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
    """Per spec line: at least one hex literal in the claim must appear in the union of
    all lines cited by that spec line's anchors (a line may carry several anchors)."""
    by_line: dict[int, list[int]] = {}
    for idx, a in enumerate(anchors):
        if idx in cited_by_anchor:
            by_line.setdefault(a.spec_line, []).append(idx)
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
            report.add("warn", spec_line,
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


def rewrite_spec(spec_path: str, text: str, report: Report, new_rev: str,
                 pin: dict | None) -> int:
    """Apply moves, stale markers and the new revision of the drifted Source pin to the
    spec file. Returns edits made."""
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
            lines[idx] = f"{m.group(1)} pin: {m['name']}@{new_rev}{license_}"
            edits += 1
    Path(spec_path).write_text("\n".join(lines), encoding="utf-8")
    return edits


def render_report(report: Report, out):
    print(f"spec: {report.spec}", file=out)
    for side, pins in sorted(report.pin_list.items()):
        for pin in pins:
            license_ = f" ({pin['license']})" if pin["license"] else ""
            print(f"{side} pin: {pin['name']}@{pin['rev']}{license_}", file=out)
    print(f"anchors: {report.anchors}  doc tags: {report.doc_tags}", file=out)
    errors = report.errors
    warns = [f for f in report.findings if f.level == "warn"]
    for f in sorted(report.findings, key=lambda f: (f.level != "error", f.spec_line)):
        tag = "ERROR" if f.level == "error" else "warn "
        print(f"{tag} L{f.spec_line}: {f.message}", file=out)
    print(f"result: {'FAIL' if errors else 'PASS'} "
          f"({len(errors)} errors, {len(warns)} warnings)", file=out)


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


def anchor_keys(anchors: list[Anchor], report: Report) -> dict[int, tuple]:
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

    report = Report(spec=args.spec)
    anchors = parse_spec(text, report, args.strict)

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

    keys = anchor_keys(anchors, report)
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
        n = rewrite_spec(args.spec, text, report, args.drift, drift_pin)
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
