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


def _rule(ruler, name):
    return next(r.fn for r in ruler.__rules__ if r.name == name)


def _markdown():
    if not _MD:
        require()
        from markdown_it import MarkdownIt  # noqa: PLC0415
        from markdown_it.helpers import parseLinkLabel  # noqa: PLC0415

        md = MarkdownIt("commonmark")
        backtick = _rule(md.inline.ruler, "backticks")
        link = _rule(md.inline.ruler, "link")
        reference = _rule(md.block.ruler, "reference")

        def recording_backtick(state, silent):
            start, before = state.pos, len(state.tokens)
            ok = backtick(state, silent)
            if ok and not silent:
                for tok in state.tokens[before:]:
                    if tok.type == "code_inline":
                        tok.meta = {**(tok.meta or {}), "span": (start, state.pos)}
            return ok

        def recording_link(state, silent):
            start, before = state.pos, len(state.tokens)
            label_end = parseLinkLabel(state, start, True)
            ok = link(state, silent)
            if ok and not silent:
                # Pending text is flushed into a token first, so look past it.
                tok = next((t for t in state.tokens[before:] if t.type == "link_open"), None)
                if tok is not None:
                    tok.meta = {**(tok.meta or {}), "span": (start, state.pos),
                                "label_end": label_end}
            return ok

        def recording_reference(state, start_line, end_line, silent):
            ok = reference(state, start_line, end_line, silent)
            if ok and not silent:
                state.env.setdefault("mdtokens_references", []).append((start_line, state.line))
            return ok

        md.inline.ruler.at("backticks", recording_backtick)
        md.inline.ruler.at("link", recording_link)
        md.block.ruler.at("reference", recording_reference)
        # Keep entities and escapes as their own tokens (text_special), so the profile can see
        # them; joining text tokens is cosmetic.
        md.core.ruler.disable("text_join")
        _MD.append(md)
    return _MD[0]


def _replacements(src: str, children) -> list[tuple[int, int, str]]:
    """(start, end, text) rewrites of src: code spans (see module doc) and, for each inline
    link, its brackets and its destination and title, which are never rendered as text."""
    out = []
    for tok in children or ():
        meta = tok.meta or {}
        if tok.type == "code_inline" and "span" in meta:
            start, end = meta["span"]
            raw = src[start:end]
            ticks = len(tok.markup)
            inner = raw[ticks:len(raw) - ticks]
            if TOKEN_SPAN_RE.fullmatch(tok.content.strip()):
                out.append((start, end, inner.strip(" ")))
            else:
                # The span's edges stay visible as "_", so letters inside it never join the
                # text around it into a tag or an anchor.
                out.append((start, end, "_" + _PROSE_CHAR_RE.sub("_", inner) + "_"))
        elif tok.type == "link_open" and "span" in meta and meta.get("label_end", -1) >= 0:
            start, end = meta["span"]
            label_end = meta["label_end"]
            out.append((start, start + 1, "_"))
            out.append((label_end, end, re.sub(r"[^\n]", "_", src[label_end:end])))
    return sorted(out)


def _mask_inline(src: str, children) -> str:
    """src (an inline token's content) with its code spans and link metadata rewritten."""
    out, pos = [], 0
    for start, end, text in _replacements(src, children):
        out.append(src[pos:start])
        out.append(text)
        pos = end
    out.append(src[pos:])
    return "".join(out)


ESCAPED_SYNTAX = set("[]()`&\\")
_LINK_TAIL_BAD_RE = re.compile(r"[\[\]]|&(?:#\d+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);")


def _inline_profile(tok, doc: "Doc") -> None:
    """Profile violations among an inline token's children, at their file lines."""
    line = tok.map[0]
    src = tok.content

    def add(kind, message, offset=None):
        at = line if offset is None else tok.map[0] + src.count("\n", 0, offset)
        doc.violations.append((at, kind, message))

    for child in tok.children or ():
        meta = child.meta or {}
        if child.type in ("softbreak", "hardbreak"):
            line += 1
        elif child.type == "html_inline":
            add("html_inline", "raw HTML is outside the spec Markdown profile")
        elif child.type == "image":
            add("image", "an image is outside the spec Markdown profile")
        elif child.type == "text_special" and child.info == "entity":
            add("entity", f"the character reference {child.markup!r} is outside the spec "
                "Markdown profile; write the character itself")
        elif child.type == "text_special" and child.info == "escape" \
                and child.content in ESCAPED_SYNTAX:
            add("escape", f"the backslash escape {child.markup!r} is outside the spec Markdown "
                "profile; put literal syntax characters in a code span")
        elif child.type == "link_open" and "span" in meta:
            start, end = meta["span"]
            label_end = meta.get("label_end", -1)
            if label_end >= 0 and _LINK_TAIL_BAD_RE.search(src[label_end + 1:end]):
                add("link_meta", "a link destination or title holds a bracket or a character "
                    "reference: provenance is read only from link text (spec Markdown "
                    "profile)", start)
        elif child.type == "code_inline" and "span" in meta:
            start, end = meta["span"]
            before = src[start - 1] if start > 0 else " "
            after = src[end] if end < len(src) else " "
            if WORD_CHAR_RE.match(before) or WORD_CHAR_RE.match(after):
                add("code_span_in_word", "a code span starts or ends inside a word; bound it "
                    "by whitespace or punctuation (spec Markdown profile)", start)


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
    env: dict = {}
    for tok in md.parse(text, env):
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
            doc.violations.append((tok.map[0], "blockquote", "a block quote is outside the "
                                   "spec Markdown profile"))
        elif tok.type == "html_block":
            doc.violations.append((tok.map[0], "html_block", "raw HTML is outside the spec "
                                   "Markdown profile (the SPDX header goes in the frontmatter "
                                   "as YAML comments)"))
        elif tok.type in ("paragraph_open", "heading_open") and tok.map:
            if not stack:
                doc.units.append((tok.map[0], tok.map[1]))
            if tok.type == "heading_open":
                if tok.markup in ("=", "-"):
                    doc.violations.append((tok.map[0], "setext", "a setext heading (underlined) is "
                                           "outside the spec Markdown profile; write ## Title"))
                if tok.level == 0:  # a section boundary only at the top of the document
                    doc.headings.append([tok.map[0], int(tok.tag[1:]), ""])
                else:
                    doc.violations.append((tok.map[0], "nested_heading", "a heading inside a "
                                           "list item is outside the spec Markdown profile"))
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
    for start, end in env.get("mdtokens_references", []):
        doc.violations.append((start, "reference", "a link reference definition is outside the "
                               "spec Markdown profile; write the link inline"))
        for n in range(start, min(end, len(lines))):
            doc.masked[n] = ""  # never rendered: nothing in it is provenance
    doc.headings = [tuple(h) for h in doc.headings]
    doc.units.sort()
    return doc


def section_of(doc: "Doc", line: int, level: int = 2) -> str | None:
    """The section 0-based ``line`` is in: the text of the last top-level heading of
    ``level`` above it, unless a heading of a higher level (fewer #) came after that one and
    ended it."""
    section = None
    for n, lvl, text in doc.headings:
        if n >= line:
            break
        if lvl == level:
            section = text
        elif lvl < level:
            section = None
    return section


def profile_violations(doc: "Doc", fact_sections=FACT_SECTIONS) -> list[tuple[int, str]]:
    """(0-based line, message) for every construct outside the spec Markdown profile, a nested
    list item in a fact section included; sorted by line."""
    out = [(n, msg) for n, _kind, msg in doc.violations]
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
