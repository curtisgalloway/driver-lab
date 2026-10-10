# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Dependency-free visible names for loaders and text diagnostics, even before imports work."""

import unicodedata

NAME_CATEGORIES = frozenset(("Cc", "Cf", "Zl", "Zp", "Co", "Cs", "Cn"))


def visible_name(value) -> str:
    """Make terminal controls and invisible filename characters printable."""
    return "".join((f"\\u{ord(c):04x}" if ord(c) <= 0xffff else f"\\U{ord(c):08x}")
                   if unicodedata.category(c) in NAME_CATEGORIES else c for c in str(value))
