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

_PARSER = None


def _parser():
    global _PARSER  # pylint: disable=global-statement
    if _PARSER is None:
        from markdown_it import MarkdownIt

        _PARSER = MarkdownIt("commonmark")
    return _PARSER


def outside_code(text: str) -> str:
    """The text a reader sees outside code: text and raw-HTML tokens, one per line.

    Left out: fenced and indented code blocks, code spans, and autolinks (`<https://...>`,
    `<a@b.example>`), which are links rather than text. Raw HTML is kept, since a template
    placeholder such as `<board name>` parses as an HTML tag.
    """
    out = []
    for token in _parser().parse(text):
        if token.type == "html_block":
            out.append(token.content)
        elif token.type == "inline":
            in_autolink = False
            for child in token.children or []:
                if child.type == "link_open" and child.markup == "autolink":
                    in_autolink = True
                elif child.type == "link_close" and in_autolink:
                    in_autolink = False
                elif not in_autolink and child.type in ("text", "html_inline"):
                    out.append(child.content)
    return "\n".join(out)
