<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS8 — Documents split; frozen archive; open-side check

Milestone of the [license-split plan](../docs/LICENSE-SPLIT-PLAN.md#ls8--documents-split-frozen-archive-open-side-check).

### 2026-10-06T18:21-07:00 — opening (written late)

This entry was written after the move was drafted, not at the start: the chapter was opened
late (process log, same time). Goal: LS-R20 and the design-text part of LS-R14, as a paired
change. Starting revisions: driver-lab `6a58cb4` (origin/main, LS1–LS7 merged) on
`license-split/ls8` in its own worktree, `cleanroom-skills` `c8754dd` on `license-split/ls8`;
both clean apart from driver-lab's untracked `.claude/`. Approach: move `DESIGN.md`'s
clean-room passages verbatim into a new `cleanroom-skills/DESIGN.md` with line ranges, reword
the kept sections only where they named the method, then the README, AGENTS.md and glossary;
archive headers; the check script first, so its output drives the rest.

First survey (the new check, before any document edit): 83 matching lines outside the
design's archive list, in `DESIGN.md` (47), `README.md` (25), `GLOSSARY.md` (8) and
`AGENTS.md` (3); plus `PROCESS-NOTES.md`, `TRANSITION.md` and `docs/STORY.md`, which the
design's list does not name.

### 2026-10-06T18:21-07:00 — decision: the term list

`clean[-_ ]?room` (covers every `cleanroom-*` name and `cleanroom_sandbox.sh`), `os-investigator`,
"the wall", "licensing wall", "research subagent", "dirty side"/"clean side", and the moved
scripts `leak_scan`, `sandbox_audit`, `session_audit`. Prose "leak scan" is not a term: the
continuous-review design (C3, C5) names the leak scan as a tier-0 check of the frozen e1000
campaign, and rewording an approved design's process steps was out of scope.

### 2026-10-06T18:21-07:00 — decision: allowlist beyond the design's list

Item by item, recorded in the evidence: the three history records (`PROCESS-NOTES.md`, an
append-only log; `TRANSITION.md`, the 2026-09-25 move; `docs/STORY.md`, a timeline), the whole
of `IMPLEMENTATION-PLAN.md` (its sections after CR are the bookkeeping of L01, L02 and CR:
deferred table, decisions D7–D9, blockers, next session), and the checker with its tests.
README: one matching line, counted, so a second fails.

### 2026-10-06T18:21-07:00 — decision: no redirect stubs in `DESIGN.md`

Every link into a `DESIGN.md` anchor (Markdown and the e1000 status index) targets a kept
section: scope, evidence model, "when there is no existing driver", continuous review, C5, C6,
the layer's acceptance. None targets a moved heading, so no stub is needed. The lifecycle keeps
steps 1, 4 and 6, renumbered 1–3 (nothing links them by number).

### 2026-10-06T18:21-07:00 — surprise: archive links broken since LS7

`RECONSTRUCTION.md` linked four files of the skills LS7 deleted (`cleanroom_hook.py`, the
policy, `session_audit.py`, `leak_scan.py`). Repointed to their new home in `cleanroom-skills`
at `main`. The README also still said the three spec repositories "do not exist yet" (they have
since LS5); fixed in the sentence the pointer line sits next to.

### 2026-10-06T18:31-07:00 — review: seven should-fix, 13 nits

One docs reviewer subagent (`ls8-review.md`, session scratch). The useful catches: the
continuous-review design still required a leak scan and a session audit on the open side (now
"source-overlap scan", conditional), a clean-room clause at the head of "Investigation" that
both lists missed (moved, row 10a), the README's spec-location sentence contradicting the GPL
rule, and pending L02 work stranded in a now-frozen plan (its header says where it goes). The
term list gained the method's own vocabulary, and the README exemption now requires the line to
name `cleanroom-skills`. One nit declined: pinning links to `cleanroom-skills` waits for its
merge commit.

### 2026-10-06T18:31-07:00 — checkpoint (closing)

Both check lists, the open-side check and the link check rerun after the fixes; checkpoint
commits in both repositories on `license-split/ls8`. Next: LS9.
