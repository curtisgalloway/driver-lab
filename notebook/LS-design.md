<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS-design — license split: settling the design and deriving the plan

Design and planning work for the license split ([design](../docs/LICENSE-SPLIT.md)). One
chapter per unit; the milestones get their own chapters (`LS1.md`, ...).

### 2026-10-05T16:21-07:00 — opening

Goal: turn the draft note `docs/LICENSE-SPLIT.md` into an approved design with labeled
requirements, then derive an implementation plan with the project-plan skill. Starting
revision `a82785c` (origin/main, PR #42 merged); worktree `.claude/worktrees/ls-plan`, branch
`docs/license-split-plan`; no pre-existing changes. Check before planning: none of the note's
tooling changes, repos or renames exist (no root `license:`/`accepts:`, no license gate in
`anchor_check.py`, no `PROVENANCE.md` template, no `hardware-investigator`, no `hwspecs-*` or
clean-room repo).

### 2026-10-05T16:21-07:00 — direction: decisions before the plan

The user interrupted the first planning pass: ask the open decisions first, then plan. The
first quiz's "name for the clean-room repo" read as possibly the repo holding clean-room
*specs*; clarified that it holds the skills only (clean-room specs are never published).

### 2026-10-05T16:21-07:00 — decision: the user's answers

- Clean-room skills repo: **`cleanroom-skills`**, public from day one.
- ENC28J60 and e1000 evals: **frozen in driver-lab** as an archive; new rounds run from
  `cleanroom-skills`.
- `hardware-specs-docs` license: **CC-BY-4.0**.
- Spec repos: **`hardware-specs-gpl`, `hardware-specs-docs`, `hardware-specs-permissive`**;
  all three created together (the bcm2711 BSD overlay is the permissive repo's first material).
- `os-investigator` is renamed **`cleanroom-investigator`**.
- Order: **license tooling and spec repos first**, then the clean-room split.

### 2026-10-06T05:03-07:00 — decision: consequences settled while revising the design

Measured state from a code survey: `anchor_check.py` keeps one pin per side (a second
`Source pin:` overwrites the first) and has no tests or CI; doc anchors are unchecked; root
markers carry no license; the implementer's hook blocks no skill by name. Settled in the design:
the clean-room docs describing the frozen evals stay with them (about 44 archive links);
the GPL firewall lives in the implementer's hook, not in a neutral `board-expert`; no alias
stubs for renamed skills; a marker without license fields warns, `--require-license` errors.

### 2026-10-06T05:03-07:00 — checkpoint (closing)

The user approved the design on 2026-10-05 (committed as `452a4ca`). The plan,
[LICENSE-SPLIT-PLAN.md](../docs/LICENSE-SPLIT-PLAN.md), maps LS-R1 to LS-R20 onto LS1–LS12
and the gate LS-G; tooling first, then the split, then consumers once. Next: LS1 (anchor-tool
tests and named pins) after this branch merges.
