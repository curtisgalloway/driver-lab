# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""The one YAML loader for spec format 2: `load_strict(path)`.

YAML has many spellings for one value; this loader admits one. It reads a file with PyYAML's
pure-Python parser (which gives a line and column for every node) and builds plain Python data
itself, so no PyYAML constructor or implicit resolver ever runs. The design's loader table
(docs/SPEC-FORMAT-V2.md, "The YAML loader") is the contract:

- plain scalars resolve only to `true`, `false`, `null` and decimal integers within the
  signed 64-bit range; every other scalar, quoted or not, is a string (D6). An empty plain
  value (`key:`) is an error, since it would be a second spelling of `null` or of `""`; `-0`
  is a string, not a second zero;
- anchors, aliases, merge keys (`<<`), explicit tags (`!!str`, `!x`) and directives (`%YAML`,
  `%TAG`, any `%`) are errors;
- exactly one document;
- mapping keys are strings, unique within their mapping;
- the file is UTF-8 without a byte-order mark. Anywhere in it, comments included, it holds no
  refused character (below) except a tab and a CR that ends a CRLF line ending: a lone CR or a
  NEL would be turned into a line break by PyYAML before any value is seen;
- every string, after escapes are decoded, holds no refused character but newline, and is NFC.

Refused characters: controls (category Cc), format characters (Cf: zero-width, bidirectional
controls, soft hyphen, BOM), surrogates, private-use and unassigned code points, line and
paragraph separators, every space but U+0020, and the other default-ignorable code points that
render as nothing (combining grapheme joiner, variation selectors, Hangul fillers) plus the
blank Braille pattern.

Every error is a `LoadError` naming the file, a 1-based line and column (counted in
characters), and the problem.
"""

from __future__ import annotations

import dataclasses
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from yaml.composer import Composer
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, ScalarNode, SequenceNode
from yaml.parser import Parser
from yaml.reader import Reader
from yaml.resolver import BaseResolver
from yaml.scanner import Scanner
from yaml.tokens import DirectiveToken

# The only plain scalars that are not strings (D6). `-0` is left a string on purpose.
_INT = re.compile(r"0|-?[1-9][0-9]{0,18}")
_INT_MIN, _INT_MAX = -(2**63), 2**63 - 1
_PLAIN = {"true": True, "false": False, "null": None}
_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")
_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp", "Zs")
# Default_Ignorable_Code_Point (Unicode DerivedCoreProperties) outside the categories above,
# and U+2800, which renders blank.
_INVISIBLE = (
    (0x034F, 0x034F), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F),
    (0x2065, 0x2065), (0x2800, 0x2800), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
)


@dataclasses.dataclass(frozen=True)
class Mark:
    """A 1-based position in a file."""

    line: int
    column: int


NAME_CATEGORIES = frozenset(("Cc", "Cf", "Zl", "Zp", "Co", "Cs", "Cn"))


def visible_name(value) -> str:
    """Make terminal controls and invisible filename characters printable."""
    return "".join((f"\\u{ord(c):04x}" if ord(c) <= 0xffff else f"\\U{ord(c):08x}")
                   if unicodedata.category(c) in NAME_CATEGORIES else c for c in str(value))


class LoadError(Exception):
    """A file that `load_strict` refuses, with where and why."""

    def __init__(self, path: Path | str, line: int, column: int, problem: str):
        self.path = visible_name(path)
        self.line = line
        self.column = column
        self.problem = problem
        super().__init__(f"{self.path}:{line}:{column}: {problem}")


@dataclasses.dataclass
class Loaded:
    """Data from `load_strict` with the position of every value and mapping key.

    Positions are keyed by the path of the value: a tuple of mapping keys and list indexes
    from the document root (`()` is the root). `keys` holds the position of the key itself
    for a value inside a mapping.
    """

    data: Any
    values: dict[tuple, Mark]
    keys: dict[tuple, Mark]
    source_bytes: bytes = b""

    def mark(self, path: tuple, *, key: bool = False) -> Mark:
        """The position of `path`, or of its nearest ancestor that has one."""
        path = tuple(path)
        if key and path in self.keys:
            return self.keys[path]
        while path not in self.values and path:
            path = path[:-1]
        return self.values.get(path, Mark(1, 1))


def _mark(m: yaml.Mark) -> Mark:
    return Mark(m.line + 1, m.column + 1)


def _refused(ch: str) -> bool:
    if unicodedata.category(ch) in _CATEGORIES:
        return True
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _INVISIBLE)


def _describe(ch: str) -> str:
    name = unicodedata.name(ch, "unnamed")
    return f"U+{ord(ch):04X} ({name}, category {unicodedata.category(ch)})"


def bad_character(text: str) -> str | None:
    """Describe the first character `load_strict` refuses in a string value, or None."""
    for ch in text:
        if ch != "\n" and ch != " " and _refused(ch):
            return _describe(ch)
    return None


def _position(source: str, at: int) -> Mark:
    line = source.count("\n", 0, at) + 1
    return Mark(line, at - (source.rfind("\n", 0, at) + 1) + 1)


def check_text(path: Path, source: str) -> None:
    """Refuse a character anywhere in a text file (a YAML file before PyYAML normalizes line
    breaks, or a schema fragment): every refused character but a tab, and a CR not in CRLF."""
    for at, ch in enumerate(source):
        if ch == "\n" or ch == " " or ch == "\t":
            continue
        if ch == "\r" and source.startswith("\n", at + 1):
            continue
        if _refused(ch):
            m = _position(source, at)
            what = "a lone CR (use LF or CRLF line endings)" if ch == "\r" else _describe(ch)
            raise LoadError(path, m.line, m.column, f"a refused character in the file: {what}")


class _Loader(Reader, Scanner, Parser, Composer, BaseResolver):
    """PyYAML's reader, scanner, parser and composer; refuses anchors, aliases, tags and
    directives.

    BaseResolver has no implicit resolvers, so the composer tags every plain scalar `str`;
    the tags are never used: `_Builder` decides types from the node's style and text.
    """

    def __init__(self, stream: str):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BaseResolver.__init__(self)

    def process_directives(self):
        if self.check_token(DirectiveToken):
            token = self.peek_token()
            raise _Refused(token.start_mark, f"a %{token.name} directive (write none)")
        return super().process_directives()

    def compose_node(self, parent, index):
        event = self.peek_event()
        if isinstance(event, AliasEvent):
            raise _Refused(event.start_mark, f"an alias (*{event.anchor}); write the value out")
        if getattr(event, "anchor", None) is not None:
            raise _Refused(event.start_mark, f"an anchor (&{event.anchor}); anchors are not allowed")
        if getattr(event, "tag", None) is not None:
            raise _Refused(event.start_mark, f"an explicit tag ({event.tag}); tags are not allowed")
        return super().compose_node(parent, index)


class _Refused(Exception):
    def __init__(self, mark: yaml.Mark, problem: str):
        super().__init__(problem)
        self.mark = mark
        self.problem = problem


def _scalar(node: ScalarNode) -> Any:
    if node.style is not None:  # quoted or block: always a string
        return node.value
    text = node.value
    if text == "":
        raise _Refused(node.start_mark, 'an empty value; write null or ""')
    if text in _PLAIN:
        return _PLAIN[text]
    if re.fullmatch(r"-?[1-9][0-9]{19,}", text):
        raise _Refused(node.start_mark, "an integer outside the signed 64-bit range; quote it "
                                        "if it is a string")
    if _INT.fullmatch(text):
        value = int(text)
        if not _INT_MIN <= value <= _INT_MAX:
            raise _Refused(node.start_mark, "an integer outside the signed 64-bit range; quote "
                                            "it if it is a string")
        return value
    return text


class _Builder:
    def __init__(self, source: str):
        self.source = source
        self.values: dict[tuple, Mark] = {}
        self.keys: dict[tuple, Mark] = {}

    def check_string(self, node: ScalarNode, text: str) -> None:
        for ch in text:
            if ch != "\n" and ch != " " and _refused(ch):
                raise _Refused(self._locate(node, ch), f"a string holding {_describe(ch)}")
        if unicodedata.normalize("NFC", text) != text:
            raise _Refused(node.start_mark, "a string that is not in Unicode NFC form")

    def _locate(self, node: ScalarNode, ch: str) -> yaml.Mark:
        """Where `ch` appears literally in the scalar's source; its start if escaped."""
        at = self.source.find(ch, node.start_mark.index, node.end_mark.index)
        if at < 0:
            return node.start_mark
        m = _position(self.source, at)
        return yaml.Mark("", at, m.line - 1, m.column - 1, None, None)

    def build(self, node, path: tuple) -> Any:
        self.values[path] = _mark(node.start_mark)
        if isinstance(node, ScalarNode):
            value = _scalar(node)
            if isinstance(value, str):
                self.check_string(node, value)
            return value
        if isinstance(node, SequenceNode):
            return [self.build(item, path + (i,)) for i, item in enumerate(node.value)]
        if isinstance(node, MappingNode):
            out: dict[str, Any] = {}
            for key_node, value_node in node.value:
                if not isinstance(key_node, ScalarNode):
                    raise _Refused(key_node.start_mark, "a mapping or list used as a key")
                key = _scalar(key_node)
                if not isinstance(key, str):
                    raise _Refused(
                        key_node.start_mark,
                        f"a non-string key ({key_node.value}); quote it if it is a name",
                    )
                if key == "<<":
                    raise _Refused(key_node.start_mark, "a merge key (<<); write the keys out")
                self.check_string(key_node, key)
                if key in out:
                    raise _Refused(key_node.start_mark, f"a duplicate key: {key}")
                self.keys[path + (key,)] = _mark(key_node.start_mark)
                out[key] = self.build(value_node, path + (key,))
            return out
        raise _Refused(node.start_mark, "an unknown node")  # pragma: no cover


def _decode(path: Path, raw: bytes) -> str:
    if raw.startswith(_BOMS):
        raise LoadError(path, 1, 1, "a byte-order mark; save the file as UTF-8 without one")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        good = raw[:exc.start].decode("utf-8")  # valid up to the first bad byte
        m = _position(good, len(good))
        raise LoadError(path, m.line, m.column, f"bytes that are not UTF-8 ({exc.reason})") from None


def load_strict_marked(path: Path | str) -> Loaded:
    """Load one YAML file under the format 2 rules, keeping every value's position.

    Raises `LoadError` for every refused input, and `OSError` when the file cannot be read.
    """
    path = Path(path)
    if any(unicodedata.category(c) in NAME_CATEGORIES for c in str(path)):
        raise LoadError(path, 1, 1, "file name contains a forbidden Unicode character")
    raw = path.read_bytes()
    source = _decode(path, raw)
    check_text(path, source)
    loader = None
    try:
        loader = _Loader(source)
        node = loader.get_single_node()
        if node is None:
            raise LoadError(path, 1, 1, "an empty file: no YAML document")
        builder = _Builder(source)
        data = builder.build(node, ())
    except _Refused as exc:
        m = _mark(exc.mark)
        raise LoadError(path, m.line, m.column, exc.problem) from None
    except yaml.MarkedYAMLError as exc:
        m = exc.problem_mark or exc.context_mark
        line, column = (m.line + 1, m.column + 1) if m else (1, 1)
        problem = exc.problem or exc.context or "YAML syntax error"
        if "expected a single document" in str(exc):
            problem = "more than one YAML document; a file holds exactly one"
        raise LoadError(path, line, column, problem) from None
    except (ValueError, OverflowError) as exc:  # e.g. an escape naming no code point
        m = _mark(loader.get_mark()) if loader is not None else Mark(1, 1)
        raise LoadError(path, m.line, m.column, f"a malformed scalar ({exc})") from None
    except yaml.YAMLError as exc:
        raise LoadError(path, 1, 1, str(exc)) from None
    except RecursionError:
        raise LoadError(path, 1, 1, "nesting too deep") from None
    finally:
        if loader is not None:
            loader.dispose()
    return Loaded(data, builder.values, builder.keys, raw)


def load_strict(path: Path | str) -> Any:
    """Load one YAML file under the format 2 rules; raise `LoadError` on any pitfall."""
    return load_strict_marked(path).data
