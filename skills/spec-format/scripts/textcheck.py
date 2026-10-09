# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Select author fields and attach specmd's safety findings to the checked YAML values.

All titles and notes, and prose fields, are checked. Generated structured strings (scope,
locators, TODOs, derivations) are escaped by the renderer; they are not embedded Markdown.
Source notices are verbatim fenced text and are exempt.
"""

from __future__ import annotations

import specmd


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
    check_data(checker, file, file.data, file.records)


def check_data(checker, where, data, records=None):
    from speccheck import _where

    for path, value, lint in fields(data):
        owner = next((r for r in (records or {}).values() if path[:2] == r.path), None)
        label = f"fact {owner.id!r}, " if owner else ""
        for finding in specmd.findings(value, lint=lint):
            checker.add(where, path,
                        f"{label}{_where(path)} (field line {finding.line}): {finding.message}",
                        level=finding.level)
