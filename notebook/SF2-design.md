<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF2-design — spec format 2: design decisions and the plan

Design and planning work for spec format 2 ([design](../docs/SPEC-FORMAT-V2.md),
[plan](../docs/SPEC-FORMAT-V2-PLAN.md)). The milestones get their own chapters (`SF2-1.md`, ...).

### 2026-10-08T12:09-07:00 — opening (written after the design session)

This chapter was opened when the plan was written, after the design session; the entries below
carry the time of writing, and the design session's times are the commits'. Goal of that session:
a design for replacing the Markdown spec formats with YAML validated by a JSON Schema (direction
decided after RG-T1's round 8, see [RG-regen](RG-regen.md)). Worktree `format-v2`, branch
`docs/spec-format-v2` from `origin/main` at `3429441`.

### 2026-10-08T12:09-07:00 — decision: first draft, 18 open choices

Draft committed as `f39503b` (11:10): data model, closed provenance classes, references,
records with per-fact basis hashes, peripheral and review payloads, schema/checker split, YAML
loader rules, rendering, migration of the three bcm2711 specs (65 facts), worked example, and
18 open decisions with a recommendation each. Every YAML and JSON block parsed under a
duplicate-key-rejecting loader, and the schema excerpt passed `check_schema`.

### 2026-10-08T12:09-07:00 — surprise: the open-side check flagged a phrase

`check-open-side.py` failed on "the research subagent" in the skills-effects table; the phrase is
on its list. Reworded to "the subagent that researches facts". Worth grepping drafts for the
listed terms before running the check.

### 2026-10-08T12:09-07:00 — direction: the user's decisions on D1–D18, and D19

Settled the same day (`4106a97`, 11:42). Differences from the recommendations: D1 root-qualified
references instead of a fact prefix in the root marker; D4 CommonMark allowed in claims and prose
with no raw HTML, the distinction from cited facts guaranteed by the viewer's badges, not by the
Markdown view; D5 rendered views built and published by CI, not committed. Added D19 from the
draft's risks table: an upstream edit stales dependent facts as a warning on the dependent
repository's `main` and an error on its pull requests. The rest as recommended.

### 2026-10-08T12:09-07:00 — direction: D20–D22

The revision left three calls open; the user settled them (`2e83ab1`, 11:45): D20 raw HTML is
whatever CommonMark parses as HTML (replacing a lexical `<`-rule that would have rejected angle
brackets in code); D21 images as links, link schemes limited, as drafted; D22 containment
(no headings, no unclosed fences) in the checker too. Consequence recorded in the design: the
checker imports a pinned CommonMark library, used only for those checks, never for meaning.
Approved as `6844645`, merged in pull request #65 (`c5d9778`, 12:02).

### 2026-10-08T12:09-07:00 — decision: plan shape

Derived the plan from the design's seven-unit outline, split for session size into SF2-1–SF2-12
and the gate SF2-G: the board-spec path first (it carries the only published content), the
bcm2711 conversion verified on draft branches (SF2-10) before the one-session cutover D11 asks
for (SF2-11). Review per unit kind: code units get an executing Claude reviewer and a Codex `ro`
diff review; content units `spec-verifier` and a networked Codex coverage review without the
records. Stop rules set up front (three rounds for code, two for docs and content). Six items
left for the user (plan, "Needs a user decision").

### 2026-10-08T12:09-07:00 — checkpoint (closing)

Plan written; chapter closed. Next: the user reviews the plan and its open items; SF2-1 starts in
its own chapter.
