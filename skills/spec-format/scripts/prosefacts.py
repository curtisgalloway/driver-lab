# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Hardware facts in prose that no checker reads (#156): stubs, agent files, wrapping skills.

A stub or agent prompt that states a base address, an address range, an instance number or a
register name is a fact outside every spec: `spec.py check` never reads it and `spec-verifier`
never verifies it, yet the agent treats its own prompt as authoritative. Facts belong in specs;
prose points at them. This module finds the likely ones:

- a hex literal of two or more digits (`0x7e20`, `0xFE201000`, also in code spans), which
  covers address ranges;
- a register-style name: upper-case words joined by underscores, with an optional `n` or `x`
  index suffix (`UART_CTRL`, `GICD_CTLR`, `GICD_ITARGETSRn`). A shell variable (`$NAME`,
  `${NAME}`) is not one.

It never catches hex without `0x` (`fe20_0000`), decimal addresses (`base 4096`), instance
numbers in words (`uart2 is the console`), or register names without an underscore or in lower
case: those still need review. A line carrying `hw-fact-ok:` with a reason is an intentional
example and passes; the marker shows up in review, which is the point. Standard library only:
the repository checks run it with a bare python3.
"""

from __future__ import annotations

import re

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
