# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""One Markdown parse for the spec checkers.

``anchor_check.py`` (this directory) and board-expert's ``spec_check.py`` read a spec's
structure from this module and from nothing else: which lines are code blocks, where the
inline code spans are, and which lines belong to which list item. It wraps markdown-it-py
(CommonMark), pinned to ``PINNED``; a checker that cannot import that exact version exits 3
("missing dependency") rather than falling back to a scanner of its own.

``parse(text)`` returns a ``Doc``:

* ``lines``: the text split on ``\\n``; ``masked``: the same lines, one for one, with
  every fenced or indented code block blanked and every inline code span rewritten:
  a span whose whole content is one bracketed token (``[DT]``, ``[src:fw: a.c:1]``,
  ``[Src]``) or the ``TODO (verify on hardware)`` marker is that token, its backticks
  dropped; any other span is prose, its characters other than letters, digits, ``_``,
  ``.``, ``-`` and whitespace replaced by ``_`` and its backticks kept as ``_``, so
  nothing in it, or joined across its edges, reads as a tag, an anchor, a parenthesis or a
  placeholder. Line breaks stay where they were, so a line
  number in ``masked`` is a line number in the file.
* ``code_lines``: 0-based lines inside code blocks (fence lines included);
  ``unclosed_fences``: 0-based opening lines of fences that never close, which CommonMark
  runs to the end of their container, hiding everything after them.
* ``items``: every list item, ``Item(start, end, parent)`` with 0-based ``[start, end)``
  lines and the index of the enclosing item (None at top level; a blockquote does not
  break nesting). ``item_at(n)`` is the innermost item holding line ``n``.
* ``units``: the ranges a construct may not cross: each top-level list item, and each
  paragraph or heading outside any list.
* ``headings``: ``(line, level, text)`` per top-level heading (one inside a list item or a
  block quote is not a section boundary); ``section_of(doc, line)`` names the section.
* ``Item.own``: the item's own masked inline content, nested items excluded.

``profile_violations(doc, fact_sections)`` lists every construct outside the spec Markdown
profile (board-expert SPEC-FORMAT, "The spec Markdown profile"); ``anchor_problems(doc)``
lists every malformed source-anchor start. Both checkers report both, so neither can pass
what the other fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PINNED = "4.2.0"
PACKAGE = f"markdown-it-py=={PINNED}"

# A code span holding exactly one of these is that token, not prose.
TOKEN_SPAN_RE = re.compile(
    r"\[[A-Za-z][A-Za-z-]*(?::[^\[\]\n]*)?\]|TODO \(verify on hardware\)"
)
_PROSE_CHAR_RE = re.compile(r"[^\w\s.\-]")
WORD_CHAR_RE = re.compile(r"\w")
# The board-spec sections whose bullets are facts (board-expert SPEC-FORMAT, Tag rules).
FACT_SECTIONS = frozenset({
    "Quick-facts", "Gotchas", "Standards and databook", "Programming model",
    "Known variants and quirks",
})


class MissingDependency(Exception):
    """markdown-it-py at the pinned version is not importable."""


def require() -> None:
    """Raise MissingDependency unless markdown-it-py PINNED is importable."""
    try:
        import markdown_it  # noqa: PLC0415
    except ImportError as exc:
        raise MissingDependency(
            f"missing dependency: {PACKAGE} is not installed (run the checker with "
            f"'uv run --with {PACKAGE} python3 ...')"
        ) from exc
    if markdown_it.__version__ != PINNED:
        raise MissingDependency(
            f"missing dependency: the checkers are pinned to {PACKAGE}, found "
            f"markdown-it-py {markdown_it.__version__} (run with 'uv run --with {PACKAGE}')"
        )


@dataclass
class Item:
    start: int
    end: int
    parent: int | None
    own: list = field(default_factory=list)  # masked inline content of its own paragraphs


@dataclass
class Doc:
    lines: list[str]
    masked: list[str]
    code_lines: set = field(default_factory=set)
    unclosed_fences: list = field(default_factory=list)
    items: list = field(default_factory=list)
    units: list = field(default_factory=list)  # (start, end), 0-based, end exclusive
    headings: list = field(default_factory=list)  # (line, level, text), top level only
    violations: list = field(default_factory=list)  # (line, kind, message): outside the profile

    def item_at(self, n: int) -> int | None:
        """Index of the innermost list item holding 0-based line n, or None."""
        best = None
        for idx, item in enumerate(self.items):
            if item.start <= n < item.end:
                best = idx  # items are in document order, so later ones are inner
        return best

    def top_items(self) -> list[int]:
        return [i for i, item in enumerate(self.items) if item.parent is None]


_MD = []


def _markdown():
    if not _MD:
        require()
        from markdown_it import MarkdownIt  # noqa: PLC0415
        from markdown_it.rules_inline.backticks import backtick  # noqa: PLC0415

        def recording_backtick(state, silent):
            start, before = state.pos, len(state.tokens)
            ok = backtick(state, silent)
            if ok and not silent:
                for tok in state.tokens[before:]:
                    if tok.type == "code_inline":
                        tok.meta = {**(tok.meta or {}), "span": (start, state.pos)}
            return ok

        md = MarkdownIt("commonmark")
        md.inline.ruler.at("backticks", recording_backtick)
        _MD.append(md)
    return _MD[0]


def _mask_inline(src: str, children) -> str:
    """src (an inline token's content) with its code spans rewritten (see module doc)."""
    out, pos = [], 0
    for tok in children or ():
        span = (tok.meta or {}).get("span") if tok.type == "code_inline" else None
        if span is None:
            continue
        start, end = span
        raw = src[start:end]
        ticks = len(tok.markup)
        inner = raw[ticks:len(raw) - ticks]
        out.append(src[pos:start])
        if TOKEN_SPAN_RE.fullmatch(tok.content.strip()):
            out.append(inner.strip(" "))
        else:
            # The span's edges stay visible as "_", so letters inside it never join the text
            # around it into a tag or an anchor.
            out.append("_" + _PROSE_CHAR_RE.sub("_", inner) + "_")
        pos = end
    out.append(src[pos:])
    return "".join(out)


def _inline_profile(tok, doc: "Doc") -> None:
    """Profile violations among an inline token's children, at their file lines."""
    line = tok.map[0]
    src = tok.content
    for child in tok.children or ():
        if child.type in ("softbreak", "hardbreak"):
            line += 1
        elif child.type == "html_inline":
            doc.violations.append((line, "html_inline", "raw HTML is outside the spec Markdown profile"))
        elif child.type == "image":
            doc.violations.append((line, "image", "an image is outside the spec Markdown profile"))
        elif child.type == "code_inline":
            span = (child.meta or {}).get("span")
            if span is None:
                continue
            start, end = span
            before = src[start - 1] if start > 0 else " "
            after = src[end] if end < len(src) else " "
            if WORD_CHAR_RE.match(before) or WORD_CHAR_RE.match(after):
                doc.violations.append(
                    (line + src.count("\n", 0, start), "code_span_in_word", "a code span starts or ends inside a "
                     "word; bound it by whitespace or punctuation (spec Markdown profile)")
                )


def _place(raw: str, content: str, masked: str) -> str:
    """raw with its trailing content replaced by masked: the prefix (indentation, a list
    marker) stays, so the line keeps its shape."""
    if content and raw.rstrip().endswith(content):
        cut = len(raw.rstrip()) - len(content)
        return raw[:cut] + masked
    at = raw.find(content) if content else -1
    if at >= 0:
        return raw[:at] + masked + raw[at + len(content):]
    return masked


def _fence_closed(tok) -> bool:
    """Whether the parser consumed a closing fence for this fence token.

    markdown-it's fence rule sets ``map`` to ``[start, next + 1]`` when it consumed a closing
    line and ``[start, next]`` when it ran out of its container, and ``content`` to the lines
    strictly between: so the closer exists exactly when one line of the map is neither the
    opener nor content.
    """
    content = tok.content
    # Each content line ends with a line feed, except a last line at the end of the text.
    n = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    return tok.map[1] - tok.map[0] - 1 - n == 1


def parse(text: str) -> Doc:
    """Parse text once; see the module docstring for what the Doc holds."""
    md = _markdown()
    lines = text.split("\n")
    doc = Doc(lines=lines, masked=list(lines))
    stack: list[int] = []  # open list items, innermost last
    for tok in md.parse(text):
        if tok.type in ("fence", "code_block") and tok.map:
            for n in range(tok.map[0], tok.map[1]):
                doc.code_lines.add(n)
                doc.masked[n] = ""
            if tok.type == "fence" and not _fence_closed(tok):
                doc.unclosed_fences.append(tok.map[0])
        elif tok.type == "list_item_open":
            doc.items.append(Item(tok.map[0], tok.map[1], stack[-1] if stack else None))
            stack.append(len(doc.items) - 1)
            if len(stack) == 1:
                doc.units.append((tok.map[0], tok.map[1]))
        elif tok.type == "list_item_close":
            stack.pop()
        elif tok.type == "blockquote_open":
            doc.violations.append((tok.map[0], "blockquote", "a block quote is outside the spec Markdown "
                                   "profile"))
        elif tok.type == "html_block":
            doc.violations.append((tok.map[0], "html_block", "raw HTML is outside the spec Markdown "
                                   "profile"))
        elif tok.type in ("paragraph_open", "heading_open") and tok.map:
            if not stack:
                doc.units.append((tok.map[0], tok.map[1]))
            if tok.type == "heading_open":
                if tok.markup in ("=", "-"):
                    doc.violations.append((tok.map[0], "setext", "a setext heading (underlined) is "
                                           "outside the spec Markdown profile; write ## Title"))
                if tok.level == 0:  # a section boundary only at the top of the document
                    doc.headings.append([tok.map[0], int(tok.tag[1:]), ""])
        elif tok.type == "inline" and tok.map:
            if doc.headings and doc.headings[-1][0] == tok.map[0] and not doc.headings[-1][2]:
                doc.headings[-1][2] = tok.content.strip()
            _inline_profile(tok, doc)
            joined = _mask_inline(tok.content, tok.children)
            if stack:
                doc.items[stack[-1]].own.append(joined)
            masked = joined.split("\n")
            content = tok.content.split("\n")
            for k, (c_line, m_line) in enumerate(zip(content, masked)):
                n = tok.map[0] + k
                if n < len(lines):
                    doc.masked[n] = _place(lines[n], c_line, m_line)
    doc.headings = [tuple(h) for h in doc.headings]
    doc.units.sort()
    return doc


def section_of(doc: "Doc", line: int, level: int = 2) -> str | None:
    """The text of the last top-level heading of ``level`` above 0-based ``line``."""
    section = None
    for n, lvl, text in doc.headings:
        if lvl == level and n < line:
            section = text
    return section


# Profile rules detected but not yet enforced: every existing spec opens with an SPDX header
# in an HTML comment, and a source notice is quoted as a block quote. Held for a user decision
# (2026-10-08); see the RG-T1 round-7 report.
HELD = frozenset({"html_block", "blockquote"})


def profile_violations(doc: "Doc", fact_sections=FACT_SECTIONS) -> list[tuple[int, str]]:
    """(0-based line, message) for every construct outside the spec Markdown profile, a nested
    list item in a fact section included; sorted by line. Kinds in HELD are left out."""
    out = [(n, msg) for n, kind, msg in doc.violations if kind not in HELD]
    for item in doc.items:
        if item.parent is None:
            continue
        top = item
        while top.parent is not None:
            top = doc.items[top.parent]
        if section_of(doc, top.start) in fact_sections:
            out.append((item.start, "a nested list item in a fact section is outside the spec "
                        "Markdown profile; each fact is its own top-level bullet"))
    for n in doc.unclosed_fences:
        out.append((n, "code fence never closes: everything after it to the end of its list "
                    "item or of the file is code"))
    return sorted(out)


# The start of a source anchor in any case and with any whitespace inside "[src:": only the
# exact lowercase "[src:" (or "[impl:", "[tgt:", "[ref:") is an anchor the checkers read.
ANCHOR_START_RE = re.compile(
    r"\[\s*((?i:s\s*r\s*c|i\s*m\s*p\s*l|t\s*g\s*t|r\s*e\s*f))\s*:"
)
OTHER_KIND_RE = re.compile(r"\[((?i:doc|stale)):")
BROKEN_ANCHOR = ("a [src:] anchor is broken across lines or by spaces; keep each anchor whole "
                 "on one line (anchor_check.py reads one line at a time)")


def anchor_problems(doc: "Doc") -> list[tuple[int, str]]:
    """(0-based line, message) for each anchor start no checker would read: whitespace inside
    "[src:" (blank lines included), a kind not in lowercase, no closing "]" before the end of
    its list item or paragraph, or a "]" only after a line break. Both checkers report these."""
    body = "\n".join(doc.masked)
    starts = [0]
    for line in doc.masked:
        starts.append(starts[-1] + len(line) + 1)
    out = []
    for m in ANCHOR_START_RE.finditer(body):
        line = body.count("\n", 0, m.start())
        kind = re.sub(r"\s", "", m.group(1))
        if re.search(r"\s", m.group(0)):
            out.append((line, BROKEN_ANCHOR))
            continue
        if kind != kind.lower():
            out.append((line, f"anchor kind {m.group(0)!r} is not lowercase: write "
                        f"[{kind.lower()}: ...] (anchor kinds are case-sensitive)"))
        unit_end = next((end for start, end in doc.units if start <= line < end), line + 1)
        limit = starts[min(unit_end, len(doc.masked))] - 1
        close = body.find("]", m.end(), max(limit, m.end()))
        if close < 0:
            out.append((line, "a [src:] anchor has no closing ']' before the end of its list "
                        "item or paragraph"))
        elif "\n" in body[m.end():close]:
            out.append((line, BROKEN_ANCHOR))
    # [doc: and [stale: are not source anchors, but their kinds are case-sensitive too.
    for m in OTHER_KIND_RE.finditer(body):
        if m.group(1) != m.group(1).lower():
            out.append((body.count("\n", 0, m.start()), f"anchor kind {m.group(0)!r} is not "
                        f"lowercase: write [{m.group(1).lower()}: ...] (anchor kinds are "
                        "case-sensitive)"))
    return sorted(out)
