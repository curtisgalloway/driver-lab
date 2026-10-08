<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS-G: whole-outcome acceptance

Gate of the [license-split plan](../docs/LICENSE-SPLIT-PLAN.md#ls-g--whole-outcome-acceptance).

### 2026-10-07 — opening

Goal: the design's acceptance items 1–5, from fresh clones of all eight repositories at their
`main` (the plan says six; the consumers are three, so driver-lab, three spec repositories,
`cleanroom-skills` and three consumers make eight). Run ID `lsg-20261007-01`.

### 2026-10-07 — decision: scratch specs are new files, not the gate fixtures

The spec repositories' self-tests already run driver-lab's license-gate fixtures. Copying those
into the scratch branches would test the same bytes twice. The three scratch specs are new, cite
with the named anchor form (`[src:linux: …]`) that no self-test fixture uses (the `Source pin:`
line itself is the same as `gpl-only-spec.md`'s), and sit in a subdirectory (`specs/scratch/`), so they also check that the
`anchors` step's `find` reaches nested specs.

### 2026-10-07 — decision: the published-CI half is the orchestrator's

This session does not push. Nine local branches (`ls-g/scratch-<case>` in each spec repository)
carry one commit each; the orchestrator opens them as draft pull requests, records the verdicts,
closes them and deletes the branches. The local run of each repository's `scripts/checks.sh`
against driver-lab at the repositories' pinned commit gives the expected verdict for each.

### 2026-10-07 — the pin lags `main`, harmlessly

The three spec repositories pin driver-lab `c221716` (LS9). Twelve commits have landed since;
`git diff c221716 origin/main` over the two checkers, the license-gate fixtures and the shipped
root changes only `peripheral-spec/SKILL.md` prose. So the pinned and current checkers judge the
scratch specs the same way. A future checker change needs a pin bump in all three repositories.

### 2026-10-07 — "installed beside" means side-by-side checkouts here

The plugin install commands (`/plugin marketplace add …`) need an interactive harness. Item 3
was run on the fresh clones side by side, which is the layout the hook resolves (a symlink and a
`../` path into the sibling driver-lab clone), plus a `Skill` event naming the plugin-qualified
skill. Whether the plugin cache layout is also caught is covered by `cleanroom-skills`' own
tests (plugin cache is one of the install layouts in `TestFirewallByName`).

### 2026-10-07 — stale names: the deleted board experts too

LS12's grep looked for `os-investigator`, `anchored-peripheral-spec` and `rpi-expert`. The full
list of skill directories that ever existed in driver-lab adds `board-expert-scaffold`,
`indiedroid-nova-expert`, `pixel10-expert` and `rpi4-expert`. The wider grep still finds nothing
in `fuchsia-skills` or `public-skills`, and nothing in `bringup-kit` outside its declared
historical records.

### 2026-10-07 — the public-skills pin moved, it was not removed

The review-swarm's history arm found that LS7 deleted driver-lab's public-skills checkout because
LS6 had carried the same step into `cleanroom-skills`, which still pins `d63e3f1`, a commit from
before LS12's link change. So LS-R19's "pin moves to a commit with the updated links" was not moot:
it applies in `cleanroom-skills`. CI is unaffected (the portability scanner is the same at both
commits). The bump is a `cleanroom-skills` change, outside this unit; reported, not made.

### 2026-10-07 — dead end: a scratch spec's license header

The first scratch commits carried an Apache-2.0 SPDX header in all three repositories; the GPL
and docs repositories require their own identifier on every file. Amended before any push (the
SHAs in the evidence are the amended ones); the local verdicts did not change.

### 2026-10-07 — published CI matched all nine cells

The nine scratch pull requests (#3–#5 in each spec repository) ran the published workflows: the
GPL repository passed all three, docs failed the GPL-only and dual-licensed device-tree pins,
permissive failed only the GPL-only pin. Each failure was in the anchors step, as locally. All
nine were closed unmerged and their branches deleted.
