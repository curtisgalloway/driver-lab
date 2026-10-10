# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""The one CommonMark parse of spec format 2 (design: Validation, D4, D20-D22).

Every format 2 tool that needs to know what a text field looks like as CommonMark asks this
module, which parses with the pinned markdown-it-py ("commonmark" preset). It never derives
meaning: no provenance, class, citation, id or value is read from a parse. SF2-2 uses it only to
find text outside code (for the template-placeholder check). Safety and containment findings
also live here, so there stays one parse in one module.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

_PARSER = None
MAX_DEPTH = 16

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
        from markdown_it.parser_block import ParserBlock
        from markdown_it.parser_inline import ParserInline
        from markdown_it.rules_block import StateBlock, fence
        from markdown_it.rules_inline import StateInline, autolink, html_inline, image, link

        class CheckedDepth:
            # Observe every level change, including skipToken's temporary increments.
            # Record reaching the ceiling even if lookahead later backtracks or caches
            # a text fallback. A shared env also preserves exhaustion in image labels,
            # whose recursive inline parse starts a fresh state at level zero.
            @property
            def level(self):
                return self._level

            @level.setter
            def level(self, value):
                self._level = value
                if value >= self.md.options["maxNesting"]:
                    self.env.setdefault("nesting_limit", getattr(self, "line", 0) + 1)

        class CheckedInlineState(CheckedDepth, StateInline):
            pass

        class CheckedBlockState(CheckedDepth, StateBlock):
            pass

        class CheckedInlineParser(ParserInline):
            def parse(self, src, md, env, tokens):
                # Same lifecycle as the pinned parser; only the state type changes.
                state = CheckedInlineState(src, md, env, tokens)
                self.tokenize(state)
                for rule in self.ruler2.getRules(""):
                    rule(state)
                return state.tokens

        class CheckedBlockParser(ParserBlock):
            def parse(self, src, md, env, tokens):
                if not src:
                    return None
                state = CheckedBlockState(src, md, env, tokens)
                self.tokenize(state, state.line, state.lineMax)
                return state.tokens

        # Stop parsing before Python's recursion ceiling, but well past the field limit.
        # Reaching this ceiling is recorded even when the parser drops deep tokens.
        _PARSER = MarkdownIt("commonmark", {"maxNesting": 64})
        _PARSER.inline = CheckedInlineParser()
        _PARSER.block = CheckedBlockParser()
        # New components start with every rule enabled; reapply CommonMark's rule filter.
        _PARSER.configure("commonmark", options_update={"maxNesting": 64})
        # Recognize even unsafe destinations, rather than silently treating their Markdown
        # as ordinary text. Nothing renders HTML with this parser; findings reject the URL.
        _PARSER.validateLink = lambda url: True

        def checked_fence(state, start, end, silent):
            indent = state.sCount[start]
            accepted = fence(state, start, end, silent)
            if accepted and not silent:
                token = state.tokens[-1]
                # The rule's content excludes a closing marker, if it consumed one. Comparing
                # its own source slice observes that decision, including nested containers and
                # over-indentation, without a second lexical fence scanner.
                token.meta["closed"] = token.content != state.getLines(
                    start + 1, state.line, indent, True)
            return accepted

        _PARSER.block.ruler.at("fence", checked_fence,
                               {"alt": ["paragraph", "reference", "blockquote", "list"]})

        def positioned(rule):
            def wrapped(state, silent):
                start, before = state.pos, len(state.tokens)
                accepted = rule(state, silent)
                if accepted and not silent:
                    for token in state.tokens[before:]:
                        if token.type in ("html_inline", "link_open", "image"):
                            token.meta.setdefault("field_line", state.src.count("\n", 0, start))
                return accepted
            return wrapped

        for name, rule in (("html_inline", html_inline), ("autolink", autolink),
                           ("link", link), ("image", image)):
            _PARSER.inline.ruler.at(name, positioned(rule))
    return _PARSER


@dataclass(frozen=True)
class TextFinding:
    """A safety/layout finding at a 1-based line within one decoded field, never evidence."""

    line: int
    kind: str
    message: str
    level: str = "error"


def allowed_link(url: str) -> bool:
    """D21: only http, https, mailto and in-page anchors (no relative or network paths)."""
    return url.startswith("#") or bool(re.match(r"^(?:https?|mailto):", url, re.IGNORECASE))


def viewer_tokens(text: str):
    """Parse one viewer field with raw HTML disabled, using the shared checked grammar.

    A copy keeps rendering options from changing the checker's HTML detection. Consumers
    render a fixed token vocabulary, never token attributes or fence info strings.
    """
    import copy

    parser = copy.copy(_parser())
    parser.options = copy.deepcopy(parser.options)
    parser.options["html"] = False
    env = {}
    tokens = parser.parse(text, env)
    if "nesting_limit" in env:
        raise ValueError("viewer parser nesting limit reached")
    return tokens


def findings(text: str, *, lint=False) -> list[TextFinding]:
    """Only safety/layout findings; the parse never supplies facts or provenance.

    Inline rules record their source line, including after multiline code spans and inside
    images. Diagnostics explicitly name a decoded-field line (YAML folding can make that
    differ from a physical line). Images follow the same URL rule as links.
    """
    out = []

    def add(line, kind, message, level="error"):
        out.append(TextFinding(line, kind, message, level))

    for line, source in enumerate(text.split("\n"), 1):
        if "[^" in source:
            add(line, "footnote", "footnote reference or definition inside a field")

    def inline(children, first, depth=0):
        tags = []
        level = depth
        for child in children or []:
            line = first + child.meta.get("field_line", 0)
            if child.nesting == 1:
                level += 1
            if level > MAX_DEPTH:
                add(line, "nesting", f"nesting deeper than {MAX_DEPTH}")
                return
            if child.nesting == -1:
                level -= 1
            if child.type == "text" and re.search(r"\[\^[^\]\n]+\]", child.content):
                add(line, "footnote", "footnote reference or definition inside a field")
            if child.type == "html_inline":
                tag = re.fullmatch(r"<(\/?)([A-Za-z][\w-]*)\s*[^>]*>", child.content)
                if tag and tag[1] and tag[2].lower() in tags:
                    tags.remove(tag[2].lower())
                else:
                    add(line, "html", "raw HTML")
                    if tag and not tag[1] and not child.content.endswith("/>"):
                        tags.append(tag[2].lower())
            elif child.type in ("link_open", "image"):
                url = child.attrGet("href" if child.type == "link_open" else "src") or ""
                if not allowed_link(url):
                    add(line, "link", f"disallowed link destination {url!r}")
            if child.children:
                inline(child.children, line, level + 1)

    env = {}
    tokens = _parser().parse(text, env)
    if "nesting_limit" in env:
        add(env["nesting_limit"], "nesting",
            f"nesting deeper than {MAX_DEPTH} (parser nesting limit reached)")
    for ref in list(env.get("references", {}).values()) + env.get("duplicate_refs", []):
        add(ref["map"][0] + 1, "reference", "link reference definition inside a field")
        if re.search(r"\[\^[^\]\n]+\]:", text.splitlines()[ref["map"][0]]):
            add(ref["map"][0] + 1, "footnote", "footnote reference or definition inside a field")
    for token in tokens:
        line = token.map[0] + 1 if token.map else 1
        if token.level > MAX_DEPTH:
            add(line, "nesting", f"nesting deeper than {MAX_DEPTH}")
        if token.type == "html_block":
            add(line, "html", "raw HTML")
        elif token.type == "heading_open":
            add(line, "heading", "heading inside a field")
        elif token.type == "fence" and not token.meta["closed"]:
            add(line, "fence", "unclosed code fence")
        elif token.type == "inline":
            inline(token.children, line)
            if lint:
                visible = _inline_text(token.children)
                for match in V1_TAG.finditer(visible):
                    add(line + visible.count("\n", 0, match.start()), "v1-tag",
                        f"format 1 tag {match.group(0)!r} in author text", "warning")
    return out


V1_TAG = re.compile(
    r"\[(?:databook|standard|rtl|DT|src|source-observed|doc|hardware|press|inference|emulated)"
    r"(?:\]|:)", re.IGNORECASE)


def _inline_text(children, *, skip_html=False) -> str:
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
        elif child.type == "html_inline" and skip_html:
            out.append(BREAK)
        elif child.type in ("text", "text_special", "html_inline"):
            out.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            out.append("\n")
        elif child.type == "code_inline":
            out.append(BREAK)
        elif child.type == "image":
            out.append(BREAK + _inline_text(child.children, skip_html=skip_html) + BREAK)
    return "".join(out)


def text_blocks(text: str, *, skip_html=False) -> list[tuple[int, str]]:
    """(first source line, 0-based; the text outside code) for each block that holds text:
    paragraphs, headings, table cells and raw HTML blocks. Fenced and indented code is left
    out."""
    blocks = []
    for token in _parser().parse(text):
        line = token.map[0] if token.map else 0
        if token.type == "html_block" and not skip_html:
            blocks.append((line, token.content))
        elif token.type == "inline":
            blocks.append((line, _inline_text(token.children, skip_html=skip_html)))
    return blocks


def outside_code(text: str) -> str:
    """The text outside code, one block per line group."""
    return "\n".join(t for _, t in text_blocks(text))


def placeholders(text: str, *, skip_html=False) -> list[tuple[int, int, str]]:
    """Template placeholders outside code: (1-based line, 1-based column, placeholder).

    The line is the source line (blocks keep their line breaks); the column is where the
    placeholder's text appears on that line outside a code span, or 1 when formatting inside
    it (`<board *name*>`) means it is not spelled there literally."""
    source = text.split("\n")
    found = []
    for first, block in text_blocks(text, skip_html=skip_html):
        for m in PLACEHOLDER.finditer(block):
            line = first + block.count("\n", 0, m.start())
            found.append((line + 1, _column(source[line] if line < len(source) else "",
                                            m.group(0)), m.group(0)))
    return found


def constructs(text: str) -> Counter:
    """Layout-only signatures: source line, token kind and link destination, never evidence."""
    result = Counter()

    def inline(children, first):
        for child in children or []:
            line = first + child.meta.get("field_line", 0)
            if child.type in ("link_open", "image", "html_inline"):
                value = child.attrGet("href" if child.type == "link_open" else "src") or ""
                result[(line, child.type, value)] += 1
            if child.children:
                inline(child.children, line)

    env = {}
    for token in _parser().parse(text, env):
        line = token.map[0] if token.map else 0
        if token.type in ("heading_open", "html_block"):
            result[(line, token.type, "")] += 1
        elif token.type == "fence":
            result[(line, "fence", token.content)] += 1
        elif token.type == "inline":
            inline(token.children, line)
    for ref in list(env.get("references", {}).values()) + env.get("duplicate_refs", []):
        result[(ref["map"][0], "reference", "")] += 1
    return result


def check_view(text: str, expected: Counter):
    """Only generated constructs outside exact, top-level, closed author fences.

    No GFM plugins are pinned; the CommonMark preset is the shared parser. Fenced content
    stays inert under both parsers. Expected positions and contents come from the builder,
    never from parsing author Markdown.
    """
    blocks = {"heading_open", "heading_close", "paragraph_open", "paragraph_close",
              "bullet_list_open", "bullet_list_close", "ordered_list_open",
              "ordered_list_close", "list_item_open", "list_item_close", "inline", "fence",
              "table_open", "table_close", "thead_open", "thead_close", "tbody_open",
              "tbody_close", "tr_open", "tr_close", "th_open", "th_close", "td_open", "td_close"}
    for token in _parser().parse(text):
        if token.type not in blocks or (token.type == "fence" and (
                token.level != 0 or token.info or not token.meta["closed"])):
            raise ValueError("assembled Markdown containment failed")
        if token.type == "inline" and any(c.type not in ("text", "code_inline", "softbreak")
                                           for c in token.children or []):
            raise ValueError("assembled Markdown containment failed")
    actual = constructs(text)
    if actual != expected:
        raise ValueError("assembled Markdown containment failed")


def _column(line: str, needle: str) -> int:
    at = line.find(needle)
    while at >= 0:
        if line.count("`", 0, at) % 2 == 0:  # not inside a code span on this line
            return at + 1
        at = line.find(needle, at + 1)
    return 1
