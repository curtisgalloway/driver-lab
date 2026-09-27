# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Synthetic syntax-only harness; never executed by the checker."""


def bring_up(c, tag=""):
    suffix = f" ({tag})" if tag else ""
    c.check("interface up" + suffix, True)


def scenario_smoke(c):
    bring_up(c)
    c.check("packet arrived", True)


def scenario_reload(c):
    for i in (1, 2, 3):
        bring_up(c, f"load {i}")
