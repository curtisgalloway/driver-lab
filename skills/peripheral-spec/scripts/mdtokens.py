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
  ``.``, ``-`` and whitespace replaced by ``_``, so nothing in it reads as a tag, an
  anchor, a parenthesis or a placeholder. Line breaks stay where they were, so a line
  number in ``masked`` is a line number in the file.
* ``code_lines``: 0-based lines inside code blocks (fence lines included);
  ``unclosed_fences``: 0-based opening lines of fences that never close, which CommonMark
  runs to the end of their container, hiding everything after them.
* ``items``: every list item, ``Item(start, end, parent)`` with 0-based ``[start, end)``
  lines and the index of the enclosing item (None at top level; a blockquote does not
  break nesting). ``item_at(n)`` is the innermost item holding line ``n``.
* ``units``: the ranges a construct may not cross: each top-level list item, and each
  paragraph or heading outside any list.
* ``headings``: ``(line, level, text)`` per heading.
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


@dataclass
class Doc:
    lines: list[str]
    masked: list[str]
    code_lines: set = field(default_factory=set)
    unclosed_fences: list = field(default_factory=list)
    items: list = field(default_factory=list)
    units: list = field(default_factory=list)  # (start, end), 0-based, end exclusive
    headings: list = field(default_factory=list)  # (line, level, text)

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
            out.append(_PROSE_CHAR_RE.sub("_", inner))
        pos = end
    out.append(src[pos:])
    return "".join(out)


def _place(raw: str, content: str, masked: str) -> str:
    """raw with its trailing content replaced by masked: the prefix (indentation, a list
    marker, a blockquote marker) stays, so the line keeps its shape."""
    if content and raw.rstrip().endswith(content):
        cut = len(raw.rstrip()) - len(content)
        return raw[:cut] + masked
    at = raw.find(content) if content else -1
    if at >= 0:
        return raw[:at] + masked + raw[at + len(content):]
    return masked


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
            if tok.type == "fence":
                last = lines[tok.map[1] - 1].strip() if tok.map[1] - 1 > tok.map[0] else ""
                closes = (len(last) >= len(tok.markup) and set(last) == {tok.markup[0]})
                if not closes:
                    doc.unclosed_fences.append(tok.map[0])
        elif tok.type == "list_item_open":
            doc.items.append(Item(tok.map[0], tok.map[1], stack[-1] if stack else None))
            stack.append(len(doc.items) - 1)
            if len(stack) == 1:
                doc.units.append((tok.map[0], tok.map[1]))
        elif tok.type == "list_item_close":
            stack.pop()
        elif tok.type in ("paragraph_open", "heading_open") and not stack and tok.map:
            doc.units.append((tok.map[0], tok.map[1]))
            if tok.type == "heading_open":
                doc.headings.append([tok.map[0], int(tok.tag[1:]), ""])
        elif tok.type == "heading_open" and tok.map:
            doc.headings.append([tok.map[0], int(tok.tag[1:]), ""])
        elif tok.type == "inline" and tok.map:
            if doc.headings and doc.headings[-1][0] == tok.map[0] and not doc.headings[-1][2]:
                doc.headings[-1][2] = tok.content.strip()
            masked = _mask_inline(tok.content, tok.children).split("\n")
            content = tok.content.split("\n")
            for k, (c_line, m_line) in enumerate(zip(content, masked)):
                n = tok.map[0] + k
                if n < len(lines):
                    doc.masked[n] = _place(lines[n], c_line, m_line)
    doc.headings = [tuple(h) for h in doc.headings]
    doc.units.sort()
    return doc
