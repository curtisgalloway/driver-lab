<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS7 — driver-lab's skills neutral; clean-room rules moved

Milestone of the [license-split plan](../docs/LICENSE-SPLIT-PLAN.md#ls7--driver-labs-skills-neutral-clean-room-rules-moved).

### 2026-10-06T17:48-07:00 — opening

Goal: LS-R15 and the `spec-verifier` part of LS-R14, as a paired change. In driver-lab,
`board-expert`, `board-spec-scaffold`, `SPEC-FORMAT.md`, `QUESTIONS.md`, `VENDOR-GUIDE.md` and
`spec-verifier` lose their clean-room text, the three clean-room skill directories and their CI
steps go, and the other open skills stop naming them. In `cleanroom-skills`, every removed
passage lands, mostly in `cleanroom-investigator` (which wraps `board-expert`) and in the
clean-room verification. Starting revisions: driver-lab `b9b60f7` (origin/main, LS1–LS6
merged), `cleanroom-skills` `adeb0ff`; both on `license-split/ls7`, both clean apart from
driver-lab's untracked `.claude/`. Approach: move text, not rewrite it, and keep a move list for
the evidence; give `board-expert` a plain method of its own so it still works without the
investigator.

First survey: `rg -i 'os-investigator|clean-?room|the wall|research subagent' skills/` matches
in 38 files; outside the three skills being deleted, 14 files. `campaign-review`'s stand-in
generator copies `skills/os-investigator/SKILL.md` into a reader's workspace (breaks on
deletion), and its `deployment.py` reads SPEC-FORMAT's provenance-class lines by regex, so the
`[source-observed]` entry must keep its line shape.

### 2026-10-06T17:59-07:00 — decision: `board-expert` gets a plain method of its own

`board-expert` delegated its whole *how* (method, tags, report format) to `os-investigator`, so
removing the investigator would have left it with no method. Its sections 3 and 4 now carry a
neutral method and report, copied from the investigator's parts that say nothing about the wall
(pin the commit, ground truth, device trees first, cross-check, cite documents, the inference
rules, untrusted fetched content, the report headings), with facts from code cited by file and
line. `cleanroom-investigator` wraps it with a table of which `board-expert` section it uses as
written and which it replaces.

### 2026-10-06T17:59-07:00 — decision: the clean-room verification becomes `cleanroom-verifier`

A new skill rather than a section of `cleanroom-spec`: it wraps `spec-verifier` the way
`cleanroom-investigator` wraps `board-expert`; its record rules (no source, leak scan) apply to
any spec verified from encumbered source, not only to `cleanroom-spec`'s output; and
`cleanroom-spec` stays about producing and landing a spec. `spec-verifier` gained one neutral
sentence saying a skill defining its own kind may wrap it.

### 2026-10-06T17:59-07:00 — decision: board-spec rules in `BOARD-SPECS.md`, and no repository name in SPEC-FORMAT

The moved SPEC-FORMAT and scaffold text went to a file beside `cleanroom-investigator`'s
SKILL.md, keeping the skill body about investigating. SPEC-FORMAT says `[source-observed]` is
"defined by an extension", the design's wording (LS-R15), without naming `cleanroom-skills`:
naming it would match the acceptance grep and LS-R20's coming one-README-line rule. Where the
open format used the class in examples (series, variants, anchored IP, the ip template), the
example now names the tree or uses `[inference]` with the code as a premise.

### 2026-10-06T17:59-07:00 — surprise: `campaign-review`'s stand-in counted the investigator's file

`test_standin` asserted seven frozen inputs; dropping the investigator's instruction file from
the stand-in reader's workspace made six. The assertion now expects six. The CR5 deployment
fixture still names `skill:cleanroom-implementer`; kept, as a copy of the frozen CR5 manifest
whose skill keeps its name in `cleanroom-skills`.

### 2026-10-06T17:59-07:00 — attempt: checks

driver-lab's full list (nine commands after the change) exits 0 throughout; `cleanroom-skills`'
CI steps exit 0, the portability scan run from public-skills at the CI pin `d63e3f1` extracted
with `git archive`. The deleted directories are `diff -r` identical to `cleanroom-skills`'
filtered tip `225d95d^`. Acceptance grep: only the CR5 fixture.

### 2026-10-06T18:05-07:00 — attempt: review and fixes

One reviewer subagent with fresh context (`ls7-review.md`, session scratch): no blockers, every
move-list row found at its destination, no unlisted rule. Main should-fix: with
`[source-observed]` defined elsewhere, the open format had no class for a fact read only from
code, and the ip template's replacement contradicted itself. Fixed with one sentence under
SPEC-FORMAT's *Provenance tag* (cite by commit, file and line; in a spec only as a cited premise
of an `[inference]`), pointed at from the other places. Also: the anchored skill's "not for"
limit restated, "There is no wall here" removed, the README's two broken test commands deleted,
wording nits in `cleanroom-skills`. Both check lists and the acceptance grep rerun clean.

### 2026-10-06T18:05-07:00 — checkpoint (closing)

`cleanroom-skills` committed as `670cecd`; driver-lab's checkpoint commit follows with these
records. LS8's allowlist must take the CR5 deployment fixture; LS12's public-skills pin bump is
moot. Process-log entry added: the brief's wording and the acceptance grep disagreed.
