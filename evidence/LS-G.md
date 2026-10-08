<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS-G: whole-outcome acceptance

**Terms:** a *spec repository* is one of `hardware-specs-gpl`, `-docs` and `-permissive`; its
*root marker* (`specs/board-specs.yaml`) states the repository's license and the source licenses
it *accepts*; a *pin* is either a spec's `Source pin:` line (the source tree and commit it cites,
with that tree's SPDX license) or the driver-lab commit a CI workflow checks out; the *license
gate* fails a spec whose pin carries a license the root does not accept; the *hook* is
`cleanroom-skills`' `cleanroom_hook.py`, which denies an implementation session reads of the
dirty-side skills by name; the *frozen archive* is the pre-split history kept in driver-lab (all
in the [glossary](../GLOSSARY.md)). A *scratch spec* is a synthetic spec made only for this
check and never merged.

Design: [LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md#acceptance-for-the-whole-outcome) (acceptance
items 1–5). Plan: [LS-G](../docs/LICENSE-SPLIT-PLAN.md#ls-g--whole-outcome-acceptance). Notebook:
[LS-G](../notebook/LS-G.md). Run ID: `lsg-20261007-01` (private run store).

**Status: complete.** All five items are met. Item 2 is met locally and in published CI: nine
scratch pull requests, one per cell, each got the expected verdict and were closed unmerged
(below).

## Revisions tested

Fresh `git clone` of each repository's `main` from GitHub, 2026-10-07:

| Repository | Commit |
| --- | --- |
| driver-lab | `739f0e8` |
| `hardware-specs-gpl` | `734da56` |
| `hardware-specs-docs` | `bba1890` |
| `hardware-specs-permissive` | `c6f5e69` |
| `cleanroom-skills` | `a3554da` |
| `fuchsia-skills` | `ad982e9` |
| `bringup-kit` | `d1307dd` |
| `public-skills` | `5889be1` |

The spec repositories' CI pins driver-lab `c221716` (on `main`); `cleanroom-skills`' CI pins
`public-skills` `d63e3f1` (on `main`). Both pinned trees were checked out from the fresh clones
and used for the local runs. Between `c221716` and `739f0e8` neither checker
(`spec_check.py`, `anchor_check.py`) nor the license-gate fixtures changed.

## Acceptance

| Item (design) | Result | Evidence |
| --- | --- | --- |
| 1. LS-R1 to LS-R20 each met, with evidence linked from the plan | Met, apart from one clause open in `cleanroom-skills` (LS-R19's public-skills pin bump; CI unaffected) | [Item 1](#item-1-every-requirement-met-with-evidence-linked-from-the-plan); the plan's coverage table gained an Evidence column |
| 2. Scratch setup: GPL-2.0-only pin fails docs and permissive, passes GPL; datasheet-only passes all three; `GPL-2.0 OR MIT` pin passes permissive and GPL | Met, all nine cells, locally and in published CI | [Item 2](#item-2-the-scratch-setup) |
| 3. `cleanroom-skills` beside driver-lab: moved tests pass; an implementer session reading `board-expert` is blocked | Met | [Item 3](#item-3-cleanroom-skills-beside-driver-lab) |
| 4. driver-lab's full check list, the anchor-tool tests, the open-side check and the frozen archive's checks pass | Met | [Item 4](#item-4-driver-labs-checks) |
| 5. No stale skill names in `fuchsia-skills`, `bringup-kit`, `public-skills` | Met, with `bringup-kit`'s declared historical records as the accepted exception | [Item 5](#item-5-no-stale-skill-names-in-the-consumers) |

## Item 1: every requirement met, with evidence linked from the plan

An independent subagent traced each requirement to its evidence file and checked the claim
against the fresh clones; its table is in the run store. All twenty are met but one clause of
LS-R19 (below). The plan's
[design-coverage table](../docs/LICENSE-SPLIT-PLAN.md#design-coverage) now links the evidence for
each, and every relative link in the plan, the design, the `LS*` evidence and notebook files,
`README.md`, `AGENTS.md` and `GLOSSARY.md` resolves (a link and heading-anchor check). The 75
`github.com/curtisgalloway/<repo>/(tree|blob)/<ref>/<path>` links in the eight repositories
resolve against the clones, apart from nine into `fuchsia-ci`, which was not cloned (outside the
split).

Four requirements are met in a form the design's text does not spell out, each recorded in its
milestone's evidence and noted in the coverage table: LS-R5's named-anchor rule applies where a
root's `accepts:` is empty (the docs repository's case); LS-R9's script part runs
`inventory_check.py` once per named pin; LS-R20's allowlist is wider than the design's list, each addition justified
in LS8.

One clause is open, outside driver-lab: LS-R19's "driver-lab's CI pin of public-skills moves to a
commit with the updated links". LS12 called it moot because LS7 removed driver-lab's checkout,
but LS6 had carried that step into `cleanroom-skills`, whose workflow still pins `public-skills`
`d63e3f1`, a commit from before LS12's link change (its comment also still says "Same commit as
driver-lab's workflow pins"). The scanner it runs is unchanged, so CI is unaffected; the fix is a
pin bump in `cleanroom-skills` (review findings F2 and F6 below).

The 2026-10-07 decisions changed what LS-R11 and LS-R12 rest on after LS5 recorded them. Current
state: the GPL marker reads `accepts: [GPL-2.0-only, GPL-2.0-or-later, Apache-2.0, MIT,
BSD-2-Clause, BSD-3-Clause, ISC, 0BSD]`, the permissive marker the same without the two GPL
identifiers, the docs marker `accepts: []`. The latest CI on each repository's `main` succeeded
(`hardware-specs-gpl` at `734da56`, `-docs` at `bba1890`, `-permissive` at `c6f5e69`; also
`cleanroom-skills`, driver-lab, `fuchsia-skills` and `public-skills` at the commits above). The
GPL repository's self-test log on `main`:

```
self-test: fit gpl-only-spec.md passed (exit 0)
self-test: misfit gpl3-only-spec.md failed as required (exit 1) with:
self-test: fit ISC-spec.md passed (exit 0)
self-test: fit 0BSD-spec.md passed (exit 0)
self-test: fit widgetchip.spec.md widgetchip-bsd-overlay.spec.md passed (exit 0)
self-test: misfit widgetchip-gpl3-overlay.spec.md failed as required (exit 1) with:
self-test: passed
```

Stale status text corrected here: the plan's status table and LS10–LS12 status lines (all merged:
driver-lab #54, #55, #57, #58; `cleanroom-skills` #4, #6; `fuchsia-skills` #7; `public-skills`
#100; `bringup-kit` #17), its "Next session", two closed limitations (LS4's, LS8's
`docs/STORY.md`), its "Checks added" block (the `hardware-investigator` tests), the design's
status line ("Nothing below is built yet"), `peripheral-spec`'s "These repositories do not exist
yet", and a home-relative directory in LS12's evidence. The earlier evidence files' "complete at
the checkpoint" lines are left as written: they record the state at their checkpoint, and the
plan holds status.

## Item 2: the scratch setup

Three scratch specs, each committed alone under `specs/scratch/` on a branch of its own in each
spec repository with that repository's SPDX identifier, then each repository's three CI steps (`scripts/checks.sh specs|anchors|self-test`)
run against driver-lab at the pin, the permissive repository with the docs repository's `specs/`
as its second root, as its workflow does:

- `lsg-gpl-pin-spec.md`: `Source pin: linux@1111111 GPL-2.0-only`, two `[src:linux: …]` anchors.
- `lsg-datasheet-spec.md`: no pin; a `docs:` registry and two named `[doc:widget-trm …]` anchors.
- `lsg-dt-dual-spec.md`: `Source pin: dts@2222222 GPL-2.0 OR MIT`, two `[src:dts: …]` anchors.

| Spec | `hardware-specs-gpl` | `hardware-specs-docs` | `hardware-specs-permissive` | Expected (design) |
| --- | --- | --- | --- | --- |
| GPL-2.0-only pin | pass | **fail** | **fail** | fails docs and permissive, passes GPL |
| datasheet only | pass | pass | pass | passes all three |
| `GPL-2.0 OR MIT` pin | pass | **fail** | pass | passes permissive and GPL |

Every cell matches. Each failure is the `anchors` step (exit 1); `specs` and `self-test` pass on
all nine branches. The gate's message, from the permissive repository:

```
license gate: root specs accepts: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD
ERROR L16: license gate: [src:linux: drivers/net/widget/widget.c:42 (WIDGET_CTRL)] cites source pin 'linux' (GPL-2.0-only), which root specs does not accept (accepts: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, 0BSD)
result: FAIL (2 errors, 1 warnings)
anchors: 1 peripheral spec(s) checked, 1 failed
```

and from the docs repository for the dual-licensed pin (`accepts: none`, so neither branch of the
`OR` is accepted):

```
ERROR L16: license gate: [src:dts: arch/arm64/boot/dts/widget/widget.dtsi:40] cites source pin 'dts' (GPL-2.0 OR MIT), which root specs does not accept (accepts: none)
```

The passing cells print `result: PASS` and `anchors: 1 peripheral spec(s) checked, 0 failed`.

### Published CI

Each branch is one commit on the repository's `main` named above, adding one file. Each was opened
as a draft pull request (the workflows run on `pull_request`), its verdict recorded here, then
closed without merging and the branch deleted. Every failure is in the `Peripheral specs`
(anchors) step.

| Repository | Branch | Commit | Expected CI | Published CI |
| --- | --- | --- | --- | --- |
| `hardware-specs-gpl` | `ls-g/scratch-gpl-pin` | `398148a` | pass | pass, [run](https://github.com/curtisgalloway/hardware-specs-gpl/actions/runs/37707982429) (PR #3, closed unmerged) |
| `hardware-specs-gpl` | `ls-g/scratch-datasheet` | `82f149b` | pass | pass, [run](https://github.com/curtisgalloway/hardware-specs-gpl/actions/runs/37707987788) (PR #4, closed unmerged) |
| `hardware-specs-gpl` | `ls-g/scratch-dt-dual` | `8f08aa4` | pass | pass, [run](https://github.com/curtisgalloway/hardware-specs-gpl/actions/runs/37707992124) (PR #5, closed unmerged) |
| `hardware-specs-docs` | `ls-g/scratch-gpl-pin` | `08fc715` | fail (anchors step) | fail (anchors step), [run](https://github.com/curtisgalloway/hardware-specs-docs/actions/runs/37707997518) (PR #3, closed unmerged) |
| `hardware-specs-docs` | `ls-g/scratch-datasheet` | `1e39dd9` | pass | pass, [run](https://github.com/curtisgalloway/hardware-specs-docs/actions/runs/37708001606) (PR #4, closed unmerged) |
| `hardware-specs-docs` | `ls-g/scratch-dt-dual` | `c94d00a` | fail (anchors step) | fail (anchors step), [run](https://github.com/curtisgalloway/hardware-specs-docs/actions/runs/37708007068) (PR #5, closed unmerged) |
| `hardware-specs-permissive` | `ls-g/scratch-gpl-pin` | `3bd8ede` | fail (anchors step) | fail (anchors step), [run](https://github.com/curtisgalloway/hardware-specs-permissive/actions/runs/37708012020) (PR #3, closed unmerged) |
| `hardware-specs-permissive` | `ls-g/scratch-datasheet` | `e72e6ba` | pass | pass, [run](https://github.com/curtisgalloway/hardware-specs-permissive/actions/runs/37708015878) (PR #4, closed unmerged) |
| `hardware-specs-permissive` | `ls-g/scratch-dt-dual` | `e030515` | pass | pass, [run](https://github.com/curtisgalloway/hardware-specs-permissive/actions/runs/37708019802) (PR #5, closed unmerged) |

## Item 3: `cleanroom-skills` beside driver-lab

CI steps of `cleanroom-skills` from the fresh clone: portability scan at the pinned
`public-skills` `d63e3f1` `0 finding(s)`; privacy `OK: 51 tracked files, no absolute home
paths`; `cleanroom-investigator` tests `Ran 7 tests` / `OK`; `cleanroom-implementer` tests
`Ran 118 tests` / `OK`.

The session fixture: a workspace beside the two clones with an empty `.claude/` (the project
marker the hook looks for), a symlink `notes -> ../../driver-lab/skills/board-expert`, and five
`PreToolUse` events fed one by one to `cleanroom_hook.py` with `CLEANROOM_ROLE` unset (the
implementer):

```
printf '%s' "$event" | env -u CLEANROOM_ROLE python3 cleanroom-skills/skills/cleanroom-implementer/scripts/cleanroom_hook.py
```

| Event | Exit | Decision |
| --- | --- | --- |
| `Read` of `driver-lab/skills/board-expert/SKILL.md` | 2 | deny |
| `Skill` `driver-porting:board-expert` | 2 | deny |
| `Bash` `cat ../../driver-lab/skills/board-expert/scripts/spec_check.py` | 2 | deny |
| `Bash` `cat notes/SKILL.md` (the symlink, name never written) | 2 | deny |
| `Read` of `driver-lab/skills/peripheral-spec/SKILL.md` (control) | 0 | allow |

The denial, identical for the four (tool name aside), on stdout as `decision` and on stderr:

```
cleanroom: BLOCKED Read - target matches 'name:board-expert'. Encumbered source (Linux/U-Boot/TF-A/vendor firmware), the dirty-side skills (board-expert, hardware-investigator, cleanroom-investigator) and the GPL spec repository (hardware-specs-gpl) are off-limits in implementation sessions. If the spec is insufficient, append the question to docs/spec-gaps/<device>.md as '- [open] <date> <section> <question>', mark the code site TODO(spec-gap), and continue with other work. This attempt was logged.
```

The four attempts were logged in the workspace's `docs/provenance/hook-blocks.jsonl`. The
recorded-session side: `session_audit.py` on `cleanroom-skills`' `firewall_session.jsonl`
exits 1 with `Read matched 'name:board-expert'`, `Skill matched 'name:hardware-investigator'`,
`Bash matched 'name:hardware-specs-gpl'` and `verdict: FINDINGS - contaminated session(s)`.

## Item 4: driver-lab's checks

The twelve commands of the [AGENTS.md list](../AGENTS.md#checks) (compared line by line with the
file) from the fresh clone at `739f0e8`, every one exit 0: privacy `OK: 307 tracked files`;
open side `OK: 306 tracked files, no clean-room mention outside the allowlist`; utilities
`Ran 13 tests` / `OK`; board-expert `Ran 69 tests` / `OK (skipped=1)`; the anchor tools
(`peripheral-spec`) `Ran 96 tests` / `OK`; hardware-investigator `Ran 18 tests` / `OK`;
`spec_check.py` `OK: 0 specs checked`; and the frozen archive's checks: ENC28J60 `Ran 105 tests`
/ `OK`, author manifest `matches the frozen corpus`, e1000 harness `Ran 70 tests` / `OK`,
campaign-review `Ran 121 tests` / `OK`, `index_check.py evals/e1000` `OK: 28 claims, …`.

## Item 5: no stale skill names in the consumers

The names searched are every skill directory driver-lab has had that no longer exists under that
name (from `git log --all --name-only -- 'skills/*'`): `os-investigator`,
`anchored-peripheral-spec`, `board-expert-scaffold`, `indiedroid-nova-expert`, `pixel10-expert`,
`rpi4-expert`, `rpi-expert`. LS12's grep covered the first, second and last.

- `fuchsia-skills`, `public-skills`: `rg -n -i '<names>' <repo> -g '!.git'` prints nothing
  (`rc=1`).
- `bringup-kit`, excluding the historical records its `AGENTS.md` declares (`laps/`,
  `evals/rpi5-qa-examples/`, `evals/rpi5-prompt-analysis/`, `evals/skill-routing-eval/`,
  `evals/agent-bringup-toolkit-plan.md`, `evals/lap5-m7-postmortem.md`), and with
  `hardware-specs-gpl` added to the names: nothing (`rc=1`). Inside the declared records: 292
  files (`laps/` 222, `evals/` 70), the exception the user accepted on 2026-10-07.
- No consumer names a clean-room skill with a driver-lab path or as `driver-porting:<name>`.
- `bringup-kit`'s tests from the fresh clone: `341 passed`.

## Review

`review-swarm` over the combined state: driver-lab's working tree against `739f0e8` (the diff)
in a directory holding it beside the seven other fresh clones and the three scratch specs, so that
each arm could read every repository; the arms were told that a cross-repository interaction
(pins, paths, names) in an unchanged repository is in scope. Seven arms, budget 40 tool calls and
15 minutes each: `All 7 arms delivered`. Mechanical check: 8 findings, 0 dropped, 2 merged as
identical (6 left), 1 outside the diff. Referee: 5 kept, 1 dropped (the evidence file's review
placeholder, which this section fills), no severity changed. Run directory: in run
`lsg-20261007-01`, `review/review-swarm/`.

| # | Sev. | Arms | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | medium | correctness, compat, docs | `peripheral-spec`'s new paragraph points at the fixture roots for an offline placement check, but the GPL and permissive fixture roots also accept `X11` and `Zlib`, which the published markers do not | Fixed: the paragraph says so. The fixtures are not changed (LS2's matrix and tests use them) |
| F2 | low | correctness | `cleanroom-skills`' workflow comment says its `public-skills` pin is the "Same commit as driver-lab's workflow pins"; driver-lab has no such pin since LS7 | Other repository; proposed fix below |
| F6 | low | history | LS-G and the plan called LS-R19's pin clause moot; the pin moved to `cleanroom-skills` (LS6) and still predates LS12's link change | Fixed in the records (item 1, the plan's coverage row, notebook); the bump itself is proposed below |
| F5 | low | docs | The notebook said the scratch specs' `Source pin:` line was a form no fixture uses; only the named anchors are new | Fixed |
| F7 | low | conventions | The scratch specs carried Apache-2.0 headers in the GPL and docs repositories, whose rules require their own identifier | Fixed: the nine commits amended before any push, rerun with the same verdicts; the table above has the new commits |

After the fixes: the nine scratch branches' three steps rerun (same verdicts), privacy, open-side
and `peripheral-spec` tests rerun (final run in the checkpoint report). No second swarm.

### Findings in other repositories (proposed, not made)

- `cleanroom-skills` `.github/workflows/checks.yml`: bump the `public-skills` ref from `d63e3f1`
  to a `main` commit at or after `10ab32b` (LS12's link change), and replace the comment "Same
  commit as driver-lab's workflow pins" with the reason for the pin. Closes LS-R19's last clause.
- `bringup-kit` `README.md` "Spec roots": the permissive repository's sources are listed as "BSD,
  MIT, ISC or Apache"; add 0BSD (decision of 2026-10-07). Found by the item-1 audit.

## Limitations

- Item 3 ran on side-by-side checkouts, not on a harness plugin install; the plugin-cache layout is
  covered by `cleanroom-skills`' own tests, not by this fixture.
- The spec repositories' `anchors` step checks form, pins and licenses, not that a `[src:]` line
  exists (no source checkout; each run warns `anchors not resolved`). The scratch specs' sources
  are synthetic.
- The spec repositories pin driver-lab `c221716`; a later checker change reaches them only by a
  pin bump in each.
