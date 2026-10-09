# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""The one CommonMark parse of spec format 2 (design: Validation, D4, D20-D22).

Every format 2 tool that needs to know what a text field looks like as CommonMark asks this
module, which parses with the pinned markdown-it-py ("commonmark" preset). It never derives
meaning: no provenance, class, citation, id or value is read from a parse. SF2-2 uses it only to
find text outside code (for the template-placeholder check); SF2-4 adds the raw-HTML, link-scheme
and containment checks here, so there stays one parse in one module.
"""

from __future__ import annotations

import re

_PARSER = None

# What breaks a run of text: code, an autolink. It matches no placeholder character, so a
# placeholder never spans it, and it is not a line break, so line counts stay the source's.
BREAK = "￼"

# A template placeholder (design, Validation; SF2-2 review): `<`, a letter, then letters,
# digits, spaces, hyphens or underscores, then `>`. The scaffold templates' placeholders all
# have this shape (`<Board display name>`, `<soc-id>`, `<SPDX identifier>`); a header name, a
# path, an address or a URL (`<linux/of.h>`, `<a@b>`, `<https://...>`) does not.
PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z0-9 _-]*>")


def _parser():
    global _PARSER  # pylint: disable=global-statement
    if _PARSER is None:
        from markdown_it import MarkdownIt

        _PARSER = MarkdownIt("commonmark")
    return _PARSER


def _inline_text(children) -> str:
    """The text a reader sees in one inline run, continuous across emphasis and links; image
    alternative text included; code spans and autolinks replaced by BREAK; soft and hard line
    breaks kept as newlines."""
    out, in_autolink = [], False
    for child in children or []:
        if child.type == "link_open" and child.markup == "autolink":
            in_autolink = True
            out.append(BREAK)
        elif child.type == "link_close" and in_autolink:
            in_autolink = False
        elif in_autolink:
            continue
        elif child.type in ("text", "html_inline"):
            out.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            out.append("\n")
        elif child.type == "code_inline":
            out.append(BREAK)
        elif child.type == "image":
            out.append(BREAK + _inline_text(child.children) + BREAK)
    return "".join(out)


def text_blocks(text: str) -> list[tuple[int, str]]:
    """(first source line, 0-based; the text outside code) for each block that holds text:
    paragraphs, headings, table cells and raw HTML blocks. Fenced and indented code is left
    out."""
    blocks = []
    for token in _parser().parse(text):
        line = token.map[0] if token.map else 0
        if token.type == "html_block":
            blocks.append((line, token.content))
        elif token.type == "inline":
            blocks.append((line, _inline_text(token.children)))
    return blocks


def outside_code(text: str) -> str:
    """The text outside code, one block per line group."""
    return "\n".join(t for _, t in text_blocks(text))


def placeholders(text: str) -> list[tuple[int, int, str]]:
    """Template placeholders outside code: (1-based line, 1-based column, placeholder).

    The line is the source line (blocks keep their line breaks); the column is where the
    placeholder's text appears on that line outside a code span, or 1 when formatting inside
    it (`<board *name*>`) means it is not spelled there literally."""
    source = text.split("\n")
    found = []
    for first, block in text_blocks(text):
        for m in PLACEHOLDER.finditer(block):
            line = first + block.count("\n", 0, m.start())
            found.append((line + 1, _column(source[line] if line < len(source) else "",
                                            m.group(0)), m.group(0)))
    return found


def _column(line: str, needle: str) -> int:
    at = line.find(needle)
    while at >= 0:
        if line.count("`", 0, at) % 2 == 0:  # not inside a code span on this line
            return at + 1
        at = line.find(needle, at + 1)
    return 1
