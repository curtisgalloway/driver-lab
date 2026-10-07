<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS6 — `cleanroom-skills` created with history

Milestone of the [license-split plan](../docs/LICENSE-SPLIT-PLAN.md#ls6--cleanroom-skills-created-with-history).

### 2026-10-06T17:40-07:00 — opening

Goal: LS-R14's repository part and LS-R8's move: a local `cleanroom-skills` repository holding
`cleanroom-spec`, `cleanroom-implementer` and `os-investigator` renamed `cleanroom-investigator`,
with history, plugin manifests, README, CI and a commit map; the orchestrator creates the public
GitHub repository and pushes on the user's go. Starting revision `5d7eac2` (origin/main, LS5
merged). driver-lab itself is not edited in this milestone apart from these records. This entry
is written after the work below; the entries that follow record it in order.

### 2026-10-06T17:40-07:00 — direction: the user's decisions relayed with the brief

Repository name `cleanroom-skills`, public from day one; `os-investigator` renamed
`cleanroom-investigator`; evaluations stay frozen in driver-lab and the new repository links to
them at a pinned driver-lab commit; `RECONSTRUCTION.md` and `QEMU-DIFFERENTIAL.md` stay in
driver-lab.

### 2026-10-06T17:40-07:00 — attempt: the filter

A `--single-branch` clone of driver-lab from GitHub (a full clone would have turned every remote
branch into a local one under filter-repo), then `uvx git-filter-repo` (a40bce548d2c) with
`--path` for the three skill directories and `--path-rename skills/os-investigator/:skills/cleanroom-investigator/`.
Before filtering, `git log --name-only` over the whole history showed the three directories
never lived anywhere else in driver-lab, and no rename ever moved a file into them, so the three
paths capture all of their history. Result: 273 commits parsed, 21 kept, HEAD at the LS4 commit
(the last to touch the skills), `origin` removed by filter-repo.

### 2026-10-06T17:40-07:00 — surprise: `--follow` shows no rename, and the history starts in public-skills

Because filter-repo renamed the directory in every commit, `git log --follow` on
`skills/cleanroom-investigator/SKILL.md` shows the file added under its new name in the first
commit; the pre-split history is all there (seven commits from 2026-09-01 on), but no rename
appears in it. The root commit is public-skills' 2026-09-01 packaging commit, the same root as
driver-lab's own history, not driver-lab's stand-up commit: driver-lab's history was itself cut
out of public-skills. A public-skills hash therefore translates through driver-lab's map, then
the new one (the reviewer caught the first wording of this).

### 2026-10-06T17:40-07:00 — decision: commit map keeps only kept commits

filter-repo maps the 252 pruned commits to all zeros. `history/driver-lab-commit-map.txt` keeps
the 21 rows with a copy, as driver-lab's `public-skills-commit-map.txt` does (it has no zero
rows), with a header saying the rest have none.

### 2026-10-06T17:40-07:00 — attempt: rename and cross-repository references

`sed` replaced `os-investigator` in ten files of the three skills; the title became
"Clean-room Investigator". References to skills that stay in driver-lab (`board-expert`,
`anchored-peripheral-spec`, `spec-verifier`, `board-expert/QUESTIONS.md`) and to the
license-split design now say they are driver-lab's, installed alongside. No relative links
existed to break. Both moved test suites pass (7 and 61 tests). `cleanroom-spec` has no tests,
so CI runs two suites, not three.

### 2026-10-06T17:40-07:00 — decision: names, glossary, the overlap note

Plugin and marketplace are both named `cleanroom-skills` (install
`cleanroom-skills@cleanroom-skills`). A `GLOSSARY.md` was added (the user's one-glossary-per-repo
rule), copying the relevant driver-lab rows and marking them. Until LS7 removes driver-lab's
copies, both plugins carry `cleanroom-spec` and `cleanroom-implementer`; the README says to use
plugin-qualified names or disable driver-lab's copies. **LS7 should delete that README
paragraph.**

### 2026-10-06T17:40-07:00 — attempt: local CI, review, commits

CI steps run locally against public-skills `d63e3f1` extracted with `git archive`
(`ls6-local-ci.log`, session scratch): portability 0 findings, privacy `OK: 46 tracked files`,
tests OK. One reviewer subagent with fresh context (`ls6-review.md`): no blockers; every one of
the 21 map rows checked; file contents byte-identical to driver-lab's; two should-fix wording
items (where the history starts; how to choose between the duplicate skills) and nits, fixed
except the column-width reflow and extra glossary terms. CI rerun clean, appended to the same
log. Commits `225d95d` (rename) and `adeb0ff` (repository files) on `main`, noreply author.

### 2026-10-06T17:42-07:00 — checkpoint (closing): published

Orchestrator, on the user's go: created `curtisgalloway/cleanroom-skills` public and pushed
`main` (23 commits). First CI run 37553309706 green: portability 0 findings, privacy OK, 7 and
61 tests OK. LS6 complete.
