#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Refuse hardware facts in agent and stub prose (#156).

An agent definition or a board-expert stub is read as authoritative by the agent it starts, but
no checker reads it: a base address, an address range or a register name written there is a
fact outside every spec, and nothing catches it when it is wrong. A comparison of hand-written
domain agents for one SoC found three such facts wrong, each contradicted by the agents' own
reference material. Facts belong in specs, where `spec.py check` and `spec-verifier` reach them;
agent and stub prose points at the specs.

Scope, by default: every tracked `agents/*.md`, and every tracked `SKILL.md` whose front matter
calls it a stub (`stub over`). `hwspecs check --stubs-from` runs the same rules on the stubs a
spec repository installs; this check covers the agent files it never reads: a hex literal of two
or more digits (`0x7e20`, `0xFE201000`, also in code spans), or an upper-case underscore name
with an optional `n` or `x` index suffix (`UART_CTRL`, `GICD_CTLR`, `GICD_ITARGETSRn`, excluding
shell variables like `$NAME` or `${NAME}`). A line carrying `hw-fact-ok: <reason>` passes.

Exit 0 clean / 1 findings / 2 error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
HEX = re.compile(r"(?<![0-9A-Za-z_])0[xX][0-9A-Fa-f]{2,}(?:_[0-9A-Fa-f]+)*(?![0-9A-Za-z_])")
REGISTER = re.compile(r"(?<![0-9A-Za-z_$-])[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+[nx]?"
                      r"(?![0-9A-Za-z_-])")
SHELL_VAR = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}")
OPT_OUT = "hw-fact-ok:"


def findings(text: str) -> list[tuple[int, int, str]]:
    """(1-based line, 1-based column, what) for each likely hardware fact in the text."""
    out = []
    for n, line in enumerate(text.split("\n"), 1):
        if OPT_OUT in line:
            continue
        for m in HEX.finditer(line):
            out.append((n, m.start() + 1, f"hex literal {m.group(0)!r}"))
        blanked = SHELL_VAR.sub(lambda m: " " * len(m.group(0)), line)
        for m in REGISTER.finditer(blanked):
            out.append((n, m.start() + 1, f"register-style name {m.group(0)!r}"))
    return sorted(out)


def message(what: str) -> str:
    return (f"{what} in prose no checker reads: put the fact in a spec and point at it, or mark "
            f"an intentional example with `{OPT_OUT} <reason>` on the line")


def rules():
    return types.SimpleNamespace(
        HEX=HEX, REGISTER=REGISTER, SHELL_VAR=SHELL_VAR, OPT_OUT=OPT_OUT,
        findings=findings, message=message,
    )


def in_scope(path: str, text: str) -> bool:
    p = Path(path)
    if p.suffix == ".md" and p.parent.name == "agents":
        return True
    if p.name == "SKILL.md":
        m = FRONTMATTER.match(text)
        return bool(m and "stub over" in m.group(1))
    return False


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True,
                         check=True, cwd=ROOT).stdout
    return [str(ROOT / p) for p in out.split("\0") if p]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*",
                        help="files to check, in scope or not (default: tracked agent files "
                             "and stubs)")
    args = parser.parse_args(argv)
    try:
        prosefacts = rules()
        paths = args.paths or tracked_files()
    except (subprocess.CalledProcessError, OSError, ImportError) as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2
    checked, findings = 0, []
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not args.paths and not in_scope(path, text):
            continue
        checked += 1
        for line, column, what in prosefacts.findings(text):
            findings.append(f"{path}:{line}:{column}: {prosefacts.message(what)}")
    for f in findings:
        print(f)
    if findings:
        print(f"\n{len(findings)} likely hardware fact(s) in agent or stub prose.",
              file=sys.stderr)
        return 1
    print(f"OK: {checked} agent and stub file(s), no hardware facts in prose")
    return 0


if __name__ == "__main__":
    sys.exit(main())
