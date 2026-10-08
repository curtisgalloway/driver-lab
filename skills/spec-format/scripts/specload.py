# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""The one YAML loader for spec format 2: `load_strict(path)`.

YAML has many spellings for one value; this loader admits one. It reads a file with PyYAML's
pure-Python parser (which gives a line and column for every node) and builds plain Python data
itself, so no PyYAML constructor or implicit resolver ever runs. The design's loader table
(docs/SPEC-FORMAT-V2.md, "The YAML loader") is the contract:

- plain scalars resolve only to `true`, `false`, `null` and decimal integers; every other
  scalar, quoted or not, is a string (D6). An empty plain value (`key:`) is an error, since it
  would be a second spelling of `null` or of `""`; `-0` is a string, not a second zero;
- anchors, aliases, merge keys (`<<`) and explicit tags (`!!str`, `!x`) are errors, and so are
  `%YAML`/`%TAG` directives;
- exactly one document;
- mapping keys are strings, unique within their mapping;
- strings hold no control characters except newline, no format (invisible) characters, no line
  or paragraph separators, no private-use or unassigned code points, no space other than
  U+0020, and are NFC;
- the file is UTF-8 without a byte-order mark.

Every error is a `LoadError` naming the file, a 1-based line and column, and the problem.
"""

from __future__ import annotations

import dataclasses
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from yaml.composer import Composer
from yaml.events import AliasEvent, DocumentStartEvent
from yaml.nodes import MappingNode, ScalarNode, SequenceNode
from yaml.parser import Parser
from yaml.reader import Reader, ReaderError
from yaml.resolver import BaseResolver
from yaml.scanner import Scanner

# The only plain scalars that are not strings (D6). `-0` is left a string on purpose.
_INT = re.compile(r"0|-?[1-9][0-9]*")
_PLAIN = {"true": True, "false": False, "null": None}
_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")


@dataclasses.dataclass(frozen=True)
class Mark:
    """A 1-based position in a file."""

    line: int
    column: int


class LoadError(Exception):
    """A file that `load_strict` refuses, with where and why."""

    def __init__(self, path: Path | str, line: int, column: int, problem: str):
        self.path = str(path)
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


def bad_character(text: str) -> str | None:
    """Describe the first character `load_strict` refuses in a string, or None."""
    for ch in text:
        if ch == "\n" or ch == " ":
            continue
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp", "Zs"):
            name = unicodedata.name(ch, "unnamed")
            return f"U+{ord(ch):04X} ({name}, category {cat})"
    return None


class _Loader(Reader, Scanner, Parser, Composer, BaseResolver):
    """PyYAML's reader, scanner, parser and composer; refuses anchors, aliases and tags.

    BaseResolver has no implicit resolvers, so the composer tags every plain scalar `str`;
    the tags are never used: `_build` decides types from the node's style and text.
    """

    def __init__(self, stream: str):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BaseResolver.__init__(self)

    def compose_document(self):
        event = self.peek_event()
        if isinstance(event, DocumentStartEvent) and (event.version or event.tags):
            raise _Refused(event.start_mark, "a %YAML or %TAG directive (write none)")
        return super().compose_document()

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
    if _INT.fullmatch(text):
        return int(text)
    return text


class _Builder:
    def __init__(self, source: str):
        self.source = source
        self.values: dict[tuple, Mark] = {}
        self.keys: dict[tuple, Mark] = {}

    def check_string(self, node: ScalarNode, text: str) -> None:
        bad = bad_character(text)
        if bad is not None:
            raise _Refused(self._locate(node, bad), f"a string holding {bad}")
        if unicodedata.normalize("NFC", text) != text:
            raise _Refused(node.start_mark, "a string that is not in Unicode NFC form")

    def _locate(self, node: ScalarNode, bad: str) -> yaml.Mark:
        """The mark of the refused character where it appears literally in the source."""
        ch = chr(int(bad[2:].split(" ", 1)[0], 16))
        at = self.source.find(ch, node.start_mark.index, node.end_mark.index)
        if at < 0:  # written as an escape: point at the scalar
            return node.start_mark
        line = self.source.count("\n", 0, at)
        column = at - (self.source.rfind("\n", 0, at) + 1)
        return yaml.Mark("", at, line, column, None, None)

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
        line = raw.count(b"\n", 0, exc.start) + 1
        column = exc.start - (raw.rfind(b"\n", 0, exc.start) + 1) + 1
        raise LoadError(path, line, column, f"bytes that are not UTF-8 ({exc.reason})") from None


def load_strict_marked(path: Path | str) -> Loaded:
    """Load one YAML file under the format 2 rules, keeping every value's position."""
    path = Path(path)
    source = _decode(path, path.read_bytes())
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
    except ReaderError as exc:  # PyYAML's own non-printable check, anywhere in the file
        at = exc.position
        line = source.count("\n", 0, at) + 1
        column = at - (source.rfind("\n", 0, at) + 1) + 1
        raise LoadError(
            path, line, column, f"a control character U+{exc.character:04X} in the file"
        ) from None
    except yaml.YAMLError as exc:
        raise LoadError(path, 1, 1, str(exc)) from None
    except RecursionError:
        raise LoadError(path, 1, 1, "nesting too deep") from None
    finally:
        if loader is not None:
            loader.dispose()
    return Loaded(data, builder.values, builder.keys)


def load_strict(path: Path | str) -> Any:
    """Load one YAML file under the format 2 rules; raise `LoadError` on any pitfall."""
    return load_strict_marked(path).data
