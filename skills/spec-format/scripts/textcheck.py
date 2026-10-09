# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Select author fields and attach specmd's safety findings to the checked YAML values.

All titles and notes, and prose fields, are checked. Generated structured strings (scope,
locators, TODOs, derivations) are escaped by the renderer; they are not embedded Markdown.
Source notices are exempt from CommonMark checks. All decoded strings, including notices,
structured values and mapping keys, share the Markdown view's backtick-run bound.
"""

from __future__ import annotations

import re

import specmd


MAX_BACKTICKS = 32


def strings(data, path=()):
    """(path, string, is key) for every decoded string, without a field allow-list."""
    if isinstance(data, str):
        yield path, data, False
    elif isinstance(data, dict):
        for key, value in data.items():
            at = path + (key,)
            if isinstance(key, str):
                yield at, key, True
            yield from strings(value, at)
    elif isinstance(data, list):
        for i, value in enumerate(data):
            yield from strings(value, path + (i,))


def check_backticks(checker, where, data):
    """Bound delimiters before rendering, including generated strings and source notices."""
    from speccheck import _where

    for path, value, key in strings(data):
        if re.search(r"`{33,}", value):
            checker.add(where, path, f"{_where(path)}{' key' if key else ''}: "
                        "a run of more than 32 backticks", key=key)


def fields(data, path=()):
    """(path, decoded string, lint tags) for each CommonMark author field."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "notices" and not path:
                continue
            at = path + (key,)
            if key in ("claim", "title", "note", "orientation", "milestones", "notes", "states"):
                if isinstance(value, str):
                    yield at, value, key in ("claim", "orientation", "milestones", "notes")
            else:
                yield from fields(value, at)
    elif isinstance(data, list):
        for i, value in enumerate(data):
            yield from fields(value, path + (i,))


def check_file(checker, file):
    check_backticks(checker, file, {"source_path": file.path.relative_to(file.root.given).as_posix()})
    check_data(checker, file, file.data, file.records)


def check_data(checker, where, data, records=None):
    from speccheck import _where

    check_backticks(checker, where, data)
    for path, value, lint in fields(data):
        owner = next((r for r in (records or {}).values() if path[:2] == r.path), None)
        label = f"fact {owner.id!r}, " if owner else ""
        for finding in specmd.findings(value, lint=lint):
            checker.add(where, path,
                        f"{label}{_where(path)} (field line {finding.line}): {finding.message}",
                        level=finding.level)
