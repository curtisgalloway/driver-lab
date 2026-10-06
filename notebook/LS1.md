<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS1 — anchor tools under test; several named pins

Milestone of the [license-split plan](../docs/LICENSE-SPLIT-PLAN.md#ls1--anchor-tools-under-test-several-named-pins).

### 2026-10-06T07:38-07:00 — opening

Goal: tests and CI for `anchor_check.py` and `inventory_check.py`, then several named source
pins per spec (LS-R3, LS-R6, LS-R9's script part). Starting revision `a82785c` (origin/main);
worktree `.claude/worktrees/ls1`, branch `license-split/ls1`, no pre-existing changes. Cut
before PR #43 (the plan) merged; rebase onto `origin/main` after it lands. Approach:
characterization tests first against the unchanged scripts, then the grammar change.

### 2026-10-06T07:38-07:00 — attempt: characterization tests

`tests/test_anchor_check.py`: 19 tests over synthetic git repos built per run (resolution,
symbols, malformed and inverted anchors, doc tags, stale markers, untagged facts, block
anchors, hex consistency, usage errors, aliases, drift and rewrite). All pass on the unchanged
script.

### 2026-10-06T07:38-07:00 — surprise: no committed spec carries a pin

`rg '^\s*(Source|Target|Impl|Ref) pin:'` over the repository's Markdown finds only the
grammar examples in two SKILL.md files. The frozen evals' specs live in the run store, not
here, so the plan's "every existing spec in the frozen archive gives the same result" has an
empty list in this repository; the characterization tests carry the compatibility check.

### 2026-10-06T07:43-07:00 — decision: grammar and two deviations from the plan's steps

Named pins reuse the existing pin name (`Source pin: linux@abc` already has one) plus an
optional license expression after the revision; an anchor names a pin as `[src:linux: path:L]`
(a space after the pin's colon separates it from `path:L`). `report.pins` keeps the first pin
per side for existing readers; `pin_list` holds all. Deviations, both recorded for review:
`--drift-pin NAME` instead of the plan's `--rewrite-pin` (the pin choice governs the drift
comparison, not only the rewrite); `inventory_check.py` takes one named pin per run instead of
"checking every pin", because it inventories one header tree against the spec.

### 2026-10-06T07:43-07:00 — attempt: named pins, tests, CI

`anchor_check.py`: duplicate names, unnamed anchors on a multi-pin side and unknown pin names
are findings (exit 1); `--repo NAME=PATH` mistakes are usage errors (exit 2); resolution
errors name the pin. `inventory_check.py` imports the grammar from `anchor_check.py`. 42 tests
pass; the six inventory characterization tests also pass against the original script (run
with it swapped back in). Full AGENTS.md check list green; CI step and check-list line added.

### 2026-10-06T07:48-07:00 — attempt: review findings fixed

Independent reviewer: no blockers; five should-fix and three nits (see the
[evidence](../evidence/LS1.md#review)). The main one: four new tests asserted only exit 2, which
the old scripts also returned ("is not a git repository"), so they could not fail. Each now
asserts its message, and the whole suite was run against the original scripts: 26
characterization tests pass, all 21 new-grammar tests fail. License capture narrowed to
SPDX-shaped text, so "@rev (v6.1 tag)" stays a non-pin as before.

### 2026-10-06T07:48-07:00 — checkpoint (closing)

LS1 complete: 47 tests, full check list green, evidence written, plan updated. Next: LS2 after
the LS1 pull request merges.
