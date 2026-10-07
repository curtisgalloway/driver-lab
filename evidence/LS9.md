<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS9: `anchored-peripheral-spec` renamed `peripheral-spec`

**Terms:** a *peripheral spec* is a spec of one device's programming model whose facts cite
source lines or documents (formerly "anchored spec"). The *frozen archive* is the history kept
after the license split; the *spec repositories* are `hardware-specs-gpl`, `-docs` and
`-permissive` (all in the [glossary](../GLOSSARY.md)). A *pin* is the commit a CI workflow checks
out of another repository.

Design: [LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md) (LS-R16, LS-R7 renamed). Plan:
[LS9](../docs/LICENSE-SPLIT-PLAN.md#ls9--rename-anchored-peripheral-spec-to-peripheral-spec).
Notebook: [LS9](../notebook/LS9.md). Starting revisions: driver-lab `9003213` (origin/main, LS1–LS8
merged), `cleanroom-skills` `b0e36f7`; the spec repositories at their `main`.

**Status: complete at the checkpoint;** pushes, pull requests and remote CI are the
orchestrator's. Each repository has one commit on `license-split/ls9`; the three spec
repositories pin the driver-lab commit (a commit cannot name itself; its hash is in the pull
request and in the spec repositories' workflows).

## What changed

- **driver-lab:** `skills/anchored-peripheral-spec` moved to `skills/peripheral-spec` with
  `git mv`, and its `name:` field. Every path reference updated: `checks.yml` (step name and
  path), the `AGENTS.md` check list, `board-expert`'s test (`GATE_ROOTS`), `spdx.py`, the tests'
  README, the scaffold template, `README.md`, `DESIGN.md`, and the skills that name it
  (`reference-driver-review`, `spec-verifier`, `board-expert`). Prose "anchored spec" became
  "peripheral spec", including the `spec-verifier` section heading and the three places that cite
  it. Left alone on purpose: "anchored" meaning attached to a board (`anchored or generic`,
  "anchored IP"), and "every fact anchored", which describe how a fact is cited.
- **cleanroom-skills:** `AGENTS.md`, `README.md`, `DESIGN.md`, `cleanroom-spec` and
  `cleanroom-verifier` skills. `TRANSITION.md` is the move record and keeps the old name.
- **Spec repositories:** `AGENTS.md`, `README.md` and `scripts/checks.sh` (the three paths it
  builds); the driver-lab pin in `.github/workflows/checks.yml` moved to the LS9 commit.
- **Not changed:** `evidence/`, `notebook/`, `evals/`, `history/`, the archive files named in
  `check-open-side.py`, `docs/LICENSE-SPLIT*.md`, `TRANSITION.md`: they record what the name was.

## Acceptance

| Criterion | Evidence and result |
| --- | --- |
| No `anchored-peripheral-spec` outside the frozen archive and history | Met. `grep -rIn anchored-peripheral-spec` over `cleanroom-skills`, `hardware-specs-gpl`, `-docs` and `-permissive` prints nothing. In driver-lab the remaining hits are in `evidence/`, `notebook/`, `docs/LICENSE-SPLIT.md`, `docs/LICENSE-SPLIT-PLAN.md` (naming the rename) and `TRANSITION.md` |
| Spec repositories' and `cleanroom-skills` CI green | Local part met (below). Remote CI on the new pin is the orchestrator's check after pushing |
| Full check list passes | Met, below |

**driver-lab checks** (in the worktree, after the review fixes): privacy `OK: 287 tracked files`;
open side `OK: 286 tracked files`; utilities 13 OK; board-expert 69 OK (1 skipped);
`peripheral-spec` 96 OK; `spec_check.py` `OK: 0 specs checked`; ENC28J60 105 OK; author manifest
`OK: 3 rows`; e1000 harness 70 OK; campaign-review 121 OK; `index_check.py` `OK: 28 claims, …`.

**Spec repositories** (`scripts/checks.sh specs|anchors|self-test` against the worktree as the
driver-lab path; `-permissive` also takes the docs repository's `specs`): all nine runs exit 0,
each `self-test: passed`. **cleanroom-skills:** privacy `OK: 49 tracked files`; investigator 7
OK; implementer 61 OK; portability scan `0 finding(s)`. The scan ran from a local `public-skills`
checkout, not the CI pin.

## Review

One independent reviewer subagent with fresh context read the diffs of all five repositories and
the check log. No must-fix.

| # | Sev. | Finding | Resolution |
| --- | --- | --- | --- |
| S1 | should-fix | `spec-verifier` heading `## Anchored specs and reviews` and four references to it kept the old term | Renamed together: heading, `README.md`, `peripheral-spec` and `reference-driver-review` references, and "For an anchored spec" |
| S2 | should-fix | `cleanroom-skills/DESIGN.md` link turned from a pinned permalink into a `main` link, though nearby text cites line numbers of a fixed version | Pinned to the LS9 commit in the `cleanroom-skills` commit |
| S3 | should-fix | `cleanroom-skills/TRANSITION.md` edited, a move record | Reverted |
| N1 | nit | `DESIGN.md` "reuse the anchored route" and "SOURCE-ANCHORED" in the subagent prompt | Reworded |
| N2 | nit | `board-expert/SKILL.md` line now 108 characters | My change reverted; the sentence is about board mode, not this rename |

The fixes were checked by rerunning the tests of the files touched, the privacy check and the
open-side check; no second review.

## Limitations

- Links from the spec repositories' READMEs to `driver-lab/tree/main/skills/peripheral-spec`
  resolve only after the driver-lab pull request merges.
- The spec repositories' pin is a commit on a branch until that pull request merges with a merge
  commit; a squash merge would orphan the pin.

## Pull requests needed

driver-lab `license-split/ls9` (merge first, with a merge commit); `cleanroom-skills`,
`hardware-specs-gpl`, `hardware-specs-docs`, `hardware-specs-permissive`, each `license-split/ls9`.
