<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 78

**Terms.** The patch gate checks an applied Codex patch. See the [glossary](../GLOSSARY.md).

## 2026-10-14 — Shadowed standard-library modules

The review finding's text never arrived, so an adversarial reread looked for any way a patch
could make the gate pass without its checks running. `python -m venv` from inside the worktree
imported a planted `venv.py`; the same held for `-m unittest`. The static scans run before
either, so they were not skipped, but the pinned venv and the suite results were. Added `-I`
to every interpreter the gate starts. The tests put the planted module's marker outside the
worktree so it cannot become part of the tree under test. Did not add the triage's second
idea, failing on any new top-level module named after a standard-library one: with `-I` the
gate's own interpreters no longer look there, and `--suite` callers are told to pass `-I`
in the gate's docstring and in AGENTS.md. Closed with the [acceptance evidence](../evidence/ISSUE-78.md).
