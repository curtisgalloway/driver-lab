#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""A small SPDX license-expression parser and the license gate's acceptance rule.

Enough of SPDX for the spec roots' license fields (design LS-R1, LS-R2, LS-R4):
license identifiers, ``LicenseRef-``/``DocumentRef-`` references, the ``+``
suffix, the operators ``AND``, ``OR`` and ``WITH`` (uppercase, as the SPDX
specification recommends and the Linux kernel writes them), and parentheses.
``AND`` binds tighter than ``OR``; ``WITH`` binds tightest.

Identifiers are matched case-insensitively against a short list of known ones
(``KNOWN``) and written back in their canonical case. The deprecated GNU forms
are normalized: ``GPL-2.0`` is ``GPL-2.0-only`` and ``GPL-2.0+`` is
``GPL-2.0-or-later``, as SPDX defines them. An identifier outside the list is an
error, not a guess; use ``LicenseRef-<name>`` for a license SPDX does not list,
or add the identifier to ``KNOWN``.

The acceptance rule (``accepted``): an accepts list is a set of single
identifiers. A license is accepted when its normalized identifier is in the set,
so ``GPL-2.0-or-later`` is accepted only where the list names it, never because
the list names ``GPL-2.0-only`` (or the reverse). ``X WITH E`` is accepted when
``X`` is, since an exception only adds permissions. ``A OR B`` is accepted when
either side is; ``A AND B`` only when both are.

Stdlib only; imported by ``spec_check.py`` and, by relative path, by
``peripheral-spec/scripts/anchor_check.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical identifiers the gate recognizes. Kept short on purpose: the identifiers that
# appear in the source trees a spec cites (the Linux kernel's LICENSES/ directory, firmware
# and BSD trees) and the licenses the spec repositories carry.
KNOWN = (
    "0BSD",
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "Apache-1.1",
    "Apache-2.0",
    "Artistic-2.0",
    "BSD-1-Clause",
    "BSD-2-Clause",
    "BSD-2-Clause-Patent",
    "BSD-3-Clause",
    "BSD-3-Clause-Clear",
    "BSD-4-Clause",
    "BSL-1.0",
    "CC-BY-3.0",
    "CC-BY-4.0",
    "CC-BY-SA-3.0",
    "CC-BY-SA-4.0",
    "CC0-1.0",
    "CDDL-1.0",
    "EPL-1.0",
    "EPL-2.0",
    "GFDL-1.1-no-invariants-or-later",
    "GFDL-1.2-no-invariants-only",
    "GPL-1.0-only",
    "GPL-1.0-or-later",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "ISC",
    "LGPL-2.0-only",
    "LGPL-2.0-or-later",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "Linux-OpenIB",
    "MIT",
    "MIT-0",
    "MPL-1.1",
    "MPL-2.0",
    "Unlicense",
    "X11",
    "Zlib",
)
# Deprecated SPDX identifiers and what SPDX says they mean.
DEPRECATED = {
    "GPL-1.0": "GPL-1.0-only",
    "GPL-2.0": "GPL-2.0-only",
    "GPL-3.0": "GPL-3.0-only",
    "LGPL-2.0": "LGPL-2.0-only",
    "LGPL-2.1": "LGPL-2.1-only",
    "LGPL-3.0": "LGPL-3.0-only",
    "AGPL-3.0": "AGPL-3.0-only",
}
EXCEPTIONS = (
    "Autoconf-exception-3.0",
    "Bison-exception-2.2",
    "Classpath-exception-2.0",
    "GCC-exception-2.0",
    "GCC-exception-3.1",
    "Linux-syscall-note",
    "LLVM-exception",
    "u-boot-exception-2.0",
)
OPERATORS = ("AND", "OR", "WITH")
MAX_DEPTH = 32  # nested parentheses; deeper input is an error, not a RecursionError

_KNOWN = {k.lower(): k for k in KNOWN}
_DEPRECATED = {k.lower(): v for k, v in DEPRECATED.items()}
_EXCEPTIONS = {k.lower(): k for k in EXCEPTIONS}
_REF_RE = re.compile(r"^(?:DocumentRef-[A-Za-z0-9.-]+:)?LicenseRef-[A-Za-z0-9.-]+$")
_TOKEN_RE = re.compile(r"\s*(\(|\)|[^\s()]+)")


class SpdxError(ValueError):
    """The text is not an SPDX expression this parser accepts."""


@dataclass(frozen=True)
class License:
    """One license term: a normalized identifier, optionally with an exception."""

    id: str  # canonical, e.g. "GPL-2.0-or-later", "LicenseRef-foo", "Apache-2.0+"
    exception: str | None = None

    def __str__(self) -> str:
        return f"{self.id} WITH {self.exception}" if self.exception else self.id


@dataclass(frozen=True)
class Op:
    """``AND`` or ``OR`` over two or more operands."""

    op: str
    args: tuple

    def __str__(self) -> str:
        return f" {self.op} ".join(
            f"({a})" if isinstance(a, Op) and a.op != self.op else str(a) for a in self.args
        )


def normalize_id(word: str) -> str:
    """Canonical form of one identifier (with an optional trailing ``+``), or SpdxError."""
    if _REF_RE.match(word):
        return word
    plus = word.endswith("+")
    base = word[:-1] if plus else word
    if not base:
        raise SpdxError(f"'{word}' is not a license identifier")
    key = base.lower()
    if key in _DEPRECATED:
        canonical = _DEPRECATED[key]
    elif key in _KNOWN:
        canonical = _KNOWN[key]
    elif key in ("and", "or", "with"):
        raise SpdxError(f"'{word}': write the operator in uppercase ({base.upper()})")
    else:
        raise SpdxError(
            f"unknown SPDX license identifier '{base}' (the known identifiers are listed in "
            "board-expert/scripts/spdx.py; write LicenseRef-<name> for a license SPDX does "
            "not list)"
        )
    if not plus:
        return canonical
    # "+" means "this version or any later one". For the GNU family that is the -or-later id.
    if canonical.endswith("-only"):
        return canonical[: -len("-only")] + "-or-later"
    if canonical.endswith("-or-later"):
        return canonical
    return canonical + "+"


def tokenize(text: str) -> list[str]:
    tokens = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:  # only trailing whitespace can fail to match, and it was stripped
            raise SpdxError(f"cannot read {text[pos:]!r}")
        tokens.append(m.group(1))
        pos = m.end()
    return tokens


def parse(text) -> License | Op:
    """Parse an SPDX license expression. Raises SpdxError with a reason."""
    if not isinstance(text, str):
        raise SpdxError(f"expected an SPDX expression as a string, got {type(text).__name__}")
    tokens = tokenize(text)
    if not tokens:
        raise SpdxError("empty license expression")
    pos = 0
    depth = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        tok = peek()
        pos += 1
        return tok

    def operand():
        tok = take()
        if tok is None:
            raise SpdxError("expression ends where a license identifier was expected")
        if tok == "(":
            nonlocal depth
            depth += 1
            if depth > MAX_DEPTH:
                raise SpdxError(f"parentheses nested more than {MAX_DEPTH} deep")
            inner = disjunction()
            closing = take()
            if closing is None:
                raise SpdxError("unbalanced parenthesis: '(' without ')'")
            if closing != ")":
                raise SpdxError(unexpected(closing))
            depth -= 1
            if peek() == "WITH":
                raise SpdxError("WITH must follow a single license identifier, not a parenthesis")
            return inner
        if tok == ")" or tok in OPERATORS:
            raise SpdxError(f"'{tok}' where a license identifier was expected")
        lic = normalize_id(tok)
        if peek() == "WITH":
            take()
            exc = take()
            if exc is None or exc in ("(", ")") or exc in OPERATORS:
                raise SpdxError("WITH must be followed by an exception identifier")
            if exc.lower() not in _EXCEPTIONS:
                raise SpdxError(f"unknown SPDX exception identifier '{exc}'")
            return License(lic, _EXCEPTIONS[exc.lower()])
        return License(lic)

    def chain(op, sub):
        args = [sub()]
        while peek() == op:
            take()
            args.append(sub())
        return args[0] if len(args) == 1 else Op(op, tuple(args))

    def conjunction():
        return chain("AND", operand)

    def disjunction():
        return chain("OR", conjunction)

    tree = disjunction()
    if pos != len(tokens):
        tok = tokens[pos]
        if tok == ")":
            raise SpdxError("unbalanced parenthesis: ')' without '('")
        raise SpdxError(unexpected(tok))
    return tree


def unexpected(tok: str) -> str:
    """The message for a token where an operator or the end of a group was expected."""
    if tok.lower() in ("and", "or", "with"):
        return f"'{tok}': write the operator in uppercase ({tok.upper()})"
    return f"unexpected '{tok}' after a complete expression (join terms with AND or OR)"


def parse_identifier(text) -> str:
    """One accepts-list entry: a single identifier, no operators. Returns its canonical form."""
    tree = parse(text)
    if not isinstance(tree, License) or tree.exception:
        raise SpdxError(
            f"'{text}' is an expression; an accepts list holds single license identifiers"
        )
    return tree.id


def accepted(tree: License | Op, accepts) -> bool:
    """Whether every license the expression requires is in ``accepts`` (canonical ids)."""
    accepts = set(accepts)
    if isinstance(tree, License):
        return tree.id in accepts
    results = (accepted(a, accepts) for a in tree.args)
    return any(results) if tree.op == "OR" else all(results)


def check(expression: str, accepts) -> tuple[bool, str]:
    """(accepted?, normalized expression). Raises SpdxError when it does not parse."""
    tree = parse(expression)
    return accepted(tree, accepts), str(tree)
