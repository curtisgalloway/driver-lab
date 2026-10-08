<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# License split — implementation plan

Design: [LICENSE-SPLIT.md](LICENSE-SPLIT.md), revision 2026-10-05, approved by the user on
2026-10-05 (commit `452a4ca`, "License split: settle the design").
Notebook: [index](../notebook/index.md), design chapter [LS-design](../notebook/LS-design.md);
process log: [PROCESS-NOTES.md](../PROCESS-NOTES.md).
Project checks: the full list in [AGENTS.md](../AGENTS.md#checks), plus the checks each
milestone adds (collected under [Checks added by this plan](#checks-added-by-this-plan)).

## Terms

- **Spec, peripheral spec, anchor, pin, root, root marker, overlay** — see the design's
  [Terms](LICENSE-SPLIT.md#terms).
- **Accepts list, license gate, placement rule, spec repositories, `cleanroom-skills`, frozen
  archive, SPDX** — defined in the [glossary](../GLOSSARY.md).
- **Milestone** — a deliverable with acceptance criteria, tests, review and a checkpoint; one
  per session. **Consumer** — another repository that names these skills (`fuchsia-skills`,
  `bringup-kit`, `public-skills`).

## Conventions

- **Milestone IDs** `LS1`–`LS12` and the gate `LS-G`. One topic branch per milestone, cut from a
  freshly fetched `origin/main`: `license-split/ls<n>`. Checkpoint commit message:
  `driver-porting: LS<n> — <title>`. A milestone that changes another repository gets a branch
  of the same name there and its own pull request; the evidence file lists every PR.
- **Pushes, pull requests, merges and repo creation** follow [AGENTS.md](../AGENTS.md): only on
  the user's explicit "push"; never push `main`; merge only when told. Creating a public GitHub
  repository (LS5, LS6) is outward-facing and needs its own explicit go. For public
  repositories the user-level business-hours push schedule applies; check visibility with
  `gh repo view` before invoking it.
- **Records:** evidence in `evidence/LS<n>.md`, one notebook chapter `notebook/LS<n>.md` with a
  row in the [notebook index](../notebook/index.md), process-log entries in `PROCESS-NOTES.md`.
  No milestone launches an agent run, so none uses the run store.
- **Design gate:** satisfied (approved 2026-10-05). A milestone that needs a design change stops,
  updates the design and asks again before continuing.
- **User overrides:** none.
- **Review method** (naming it here authorizes it): one independent reviewer subagent with fresh
  context that reads the diff **and** the milestone's check output, per the project's
  2026-09-25 default. `review-swarm` for LS2 and LS11, which change access controls (the
  license gate and the clean-room firewall). Docs-only milestones (LS4, LS8): a reviewer
  subagent tracing each changed claim to the code or design it describes. The artifact is the
  reviewer's returned findings, quoted or linked in the evidence file.
- **Review order:** review and fixes precede the checkpoint commit, which is the last step.
- **Orchestrated mode:** allowed; one fresh subagent per milestone (the `orchestrate-milestones`
  skill), the orchestrator holding pushes, merges and user questions.

## Status

| ID | Outcome | Dependencies | Status |
|----|---------|--------------|--------|
| LS1 | Anchor tools under test; several named pins | — | complete ([evidence](../evidence/LS1.md)) |
| LS2 | Root license fields and the license gate | LS1 | complete ([evidence](../evidence/LS2.md)) |
| LS3 | Checkable doc anchors | LS1 | complete ([evidence](../evidence/LS3.md)) |
| LS4 | Placement guidance, provenance template, "why this exists", format docs | LS2, LS3 | complete ([evidence](../evidence/LS4.md)) |
| LS5 | The three spec repositories, with CI that proves the gate | LS1–LS4 merged; user's go to create repos | complete ([evidence](../evidence/LS5.md)) |
| LS6 | `cleanroom-skills` created with history, its CI green | LS5; user's go to create the repo | complete ([evidence](../evidence/LS6.md)) |
| LS7 | driver-lab's skills neutral; clean-room rules moved; moved skills removed | LS6 | complete ([evidence](../evidence/LS7.md)) |
| LS8 | driver-lab's documents split; frozen archive marked; open-side mention check | LS7 | complete ([evidence](../evidence/LS8.md)) |
| LS9 | `anchored-peripheral-spec` renamed `peripheral-spec`; spec repos repinned | LS8 | complete ([evidence](../evidence/LS9.md)) |
| LS10 | `hardware-investigator` skill | LS9 | complete; merged (driver-lab #54) ([evidence](../evidence/LS10.md)) |
| LS11 | Firewall by name in `cleanroom-implementer`'s hook | LS10 | complete; merged, with the re-review (driver-lab #55, #58) ([evidence](../evidence/LS11.md)) |
| LS12 | Consumers updated: names, repos, spec roots, marketplaces | LS11 | complete; merged (driver-lab #57) ([evidence](../evidence/LS12.md)) |
| LS-G | Whole-outcome acceptance | LS1–LS12 | complete; published CI matched item 2's matrix ([evidence](../evidence/LS-G.md)) |

Ordering: tooling and spec repos first (the user's decision), so LS1–LS4 land under the current
skill names and LS9 renames them. The split (LS6–LS11) follows. LS12 touches each consumer once,
after every name is final. LS3 may run in parallel with LS2.

## Design coverage

| Requirement | Milestones | Verification | Evidence |
|---|---|---|---|
| LS-R1 Root license | LS2 (code), LS4 (docs) | `spec_check.py` tests for both fields, warning and `--require-license` | [LS2](../evidence/LS2.md#acceptance), [LS4](../evidence/LS4.md#acceptance) |
| LS-R2 Resource license | LS2 | `check_resources` tests | [LS2](../evidence/LS2.md#acceptance), gated in [LS5](../evidence/LS5.md#acceptance) |
| LS-R3 Several named pins | LS1 | `anchor_check.py` tests: named and legacy pins, overwrite bug | [LS1](../evidence/LS1.md#acceptance) |
| LS-R4 License gate | LS2, proven in LS5 | gate tests incl. `OR`/`AND`; each repo's CI self-test | [LS2](../evidence/LS2.md#acceptance), [LS5](../evidence/LS5.md#acceptance), [LS-G item 2](../evidence/LS-G.md#item-2-the-scratch-setup) |
| LS-R5 Checkable doc anchors | LS3 | tests for registry, page range, hash mismatch | [LS3](../evidence/LS3.md#acceptance) (named anchors required where `accepts:` is empty, the docs repository's case) |
| LS-R6 Anchor-tool tests and CI | LS1 | new test suite runs in `checks.yml` | [LS1](../evidence/LS1.md#acceptance) |
| LS-R7 Placement guidance | LS4, renamed in LS9 | reviewer traces the table to the design | [LS4](../evidence/LS4.md#acceptance), [LS9](../evidence/LS9.md#acceptance) |
| LS-R8 Provenance template | LS4, moves in LS6 | template present; `cleanroom-spec` refers to it | [LS4](../evidence/LS4.md#acceptance), [LS6](../evidence/LS6.md#acceptance) |
| LS-R9 Per-repo pins in verification | LS1 (`inventory_check.py`), LS4 (`spec-verifier` text) | tests; reviewer | [LS1](../evidence/LS1.md#acceptance) (one named pin per `inventory_check.py` run), [LS4](../evidence/LS4.md#acceptance) |
| LS-R10 Why this exists | LS4 | README section present before LS6's public repo | [LS4](../evidence/LS4.md#acceptance) |
| LS-R11 Three repos | LS5 | repos exist, CI green on `main` | [LS5](../evidence/LS5.md#acceptance); accepts lists as of 2026-10-07 in [LS-G item 1](../evidence/LS-G.md#item-1-every-requirement-met-with-evidence-linked-from-the-plan) |
| LS-R12 Gate proven per repo | LS5 | CI self-test fails the misfit fixture, passes the fit one | [LS5](../evidence/LS5.md#acceptance), [LS-G item 2](../evidence/LS-G.md#item-2-the-scratch-setup) |
| LS-R13 Consumers point at the right repos | LS12 | bringup-kit roots; public-skills README | [LS12](../evidence/LS12.md#acceptance) |
| LS-R14 `cleanroom-skills` | LS6, LS7 | repo public, history present, its CI green | [LS6](../evidence/LS6.md#acceptance), [LS7](../evidence/LS7.md#acceptance), [LS8](../evidence/LS8.md#acceptance), [LS-G item 3](../evidence/LS-G.md#item-3-cleanroom-skills-beside-driver-lab) |
| LS-R15 Neutral board-expert | LS7 | grep of the open skills; `spec_check.py` still accepts `[source-observed]` | [LS7](../evidence/LS7.md#acceptance) |
| LS-R16 Renames | LS9 | no `anchored-peripheral-spec` outside the archive | [LS9](../evidence/LS9.md#acceptance) |
| LS-R17 `hardware-investigator` | LS10 | skill review; a worked question on a fixture root | [LS10](../evidence/LS10.md#acceptance) |
| LS-R18 Firewall by name | LS11 | hook tests for each blocked skill and GPL checkout | [LS11](../evidence/LS11.md#acceptance), [LS-G item 3](../evidence/LS-G.md#item-3-cleanroom-skills-beside-driver-lab) |
| LS-R19 Consumers renamed | LS12 | grep of each consumer finds no stale name | [LS12](../evidence/LS12.md#acceptance), [LS-G item 5](../evidence/LS-G.md#item-5-no-stale-skill-names-in-the-consumers) (the public-skills CI pin moved from driver-lab to `cleanroom-skills` in LS6/LS7 and still sits at `d63e3f1`, before LS12's links; the bump is open in `cleanroom-skills`, CI unaffected) |
| LS-R20 Open side only | LS8 | mention check in CI with the archive allowlist | [LS8](../evidence/LS8.md#acceptance) (the allowlist's additions beyond the design are justified there), [LS-G item 4](../evidence/LS-G.md#item-4-driver-labs-checks) |

## Checks added by this plan

Each milestone adds its checks to `.github/workflows/checks.yml` and to the AGENTS.md list in
the same commit. Proposed, final names decided in the milestone:

```bash
python3 -m unittest discover -s skills/peripheral-spec/tests              # LS1; renamed in LS9
python3 utilities/check-open-side.py                                     # LS8
python3 -m unittest discover -s utilities/tests                            # LS8
python3 -m unittest discover -s skills/hardware-investigator/tests         # LS10
```

---

## LS1 — Anchor tools under test; several named pins

**Outcome:** 47 tests for `anchor_check.py` and `inventory_check.py`, run in CI; several named,
licensed pins per spec (`Source pin: <name>@<rev> [<SPDX>]`, `[src:<name>: path:L]`,
`--repo NAME=PATH`, `--drift-pin`); the single-pin form unchanged.
**Design coverage:** LS-R3, LS-R6, LS-R9 (script part: `inventory_check.py` takes one named pin
per run, since it compares one header tree). **Dependencies:** none.
**Status:** complete. Evidence: [LS1](../evidence/LS1.md). Notebook: [LS1](../notebook/LS1.md).
**Open limitations:** licenses are parsed, not validated (LS2); a single non-SPDX token after a
pin's revision is captured as its license, for LS2's validation to reject.

## LS2 — Root license fields and the license gate

**Outcome:** root markers carry `license:` and `accepts:`, validated by `spec_check.py` (absent:
a warning; `--require-license`: an error); `resources.repos[].license` must parse as SPDX and is
required where `accepts:` is declared; `skills/board-expert/scripts/spdx.py` parses SPDX
expressions; `anchor_check.py --root DIR` fails every anchor (both sides) and uncited pin whose
license DIR does not accept, and fails when DIR declares no `accepts:`. Repository-shaped
fixtures with an expected-result matrix in
`skills/anchored-peripheral-spec/tests/fixtures/license-gate/`, for LS5's CI self-test.
**Design coverage:** LS-R1 (code; docs in LS4), LS-R2, LS-R4 (proven per repository in LS5).
**Dependencies:** LS1.
**Status:** complete. Evidence: [LS2](../evidence/LS2.md). Notebook: [LS2](../notebook/LS2.md).
Review: `review-swarm`, five findings fixed.
**Open limitations:** board specs' resource licenses are validated, not gated; the shipped
`skills/board-expert/specs` root has no license fields yet (two CI warnings; its accepts list is
a policy choice); the known-identifier list is short. (The first two closed in LS5 by the user's
decisions of 2026-10-06.)

## LS3 — Checkable doc anchors

**Outcome:** a `docs:` registry in spec front matter (`name`, `title`, `url`, `sha256`, optional
`pages` and `file`), checked for missing and malformed fields; named `[doc:<name> p.N]`,
`pp.N-M` and `§x.y` anchors (no space after `doc:`), failing on an unknown name or a page
outside `pages`; `--docs-dir DIR` hashes each document's file and fails on a mismatch (a
missing file warns); `anchor_check.py --require-license` (with `--root`) requires the marker's
`license:` and, in a root whose `accepts:` is empty, named doc anchors. Unnamed `[doc: …]`
anchors check as before. No network access.
**Design coverage:** LS-R5. **Dependencies:** LS1.
**Status:** complete. Evidence: [LS3](../evidence/LS3.md). Notebook: [LS3](../notebook/LS3.md).
Review: one independent reviewer subagent; one should-fix (a leading `---` rule taken for
front matter) and two nits fixed.
**Open limitations:** hashes compare file bytes only; `pages` is the author's statement; LS2's
`docs-only-spec.md` fixture fails the docs root under `--require-license` (LS5's self-test
needs a named-anchor fixture or no flag); the registry, the space rule, `--docs-dir` and
`--require-license` are documented only in `anchor_check.py`'s docstring until LS4.

## LS4 — Guidance, provenance template, "why this exists", format docs

**Outcome:** `anchored-peripheral-spec` states the placement rule and the design's repo table
(replacing the "is it yours?" test) and documents named, licensed pins, the `docs:` registry,
`--root`, `--require-license`, `--docs-dir` and `--drift-pin`; `SPEC-FORMAT.md` explains the
marker's license fields and how peripheral specs sit in a licensed root; the scaffold's marker
template carries `license:`/`accepts:`; `cleanroom-spec` fills a private `PROVENANCE.md`;
`spec-verifier`'s anchored procedure runs every pin and the gate; the README opens with "Why this
exists and what it is not for".
**Design coverage:** LS-R7, LS-R8, LS-R9 (`spec-verifier` text), LS-R10, LS-R1 docs.
**Dependencies:** LS2, LS3.
**Status:** complete. Evidence: [LS4](../evidence/LS4.md). Notebook: [LS4](../notebook/LS4.md).
Review: one reviewer subagent tracing each changed claim to code or design.
**Open limitations:** the repositories the docs name do not exist until LS5 (closed in LS5;
`peripheral-spec`'s text saying so was corrected in LS-G); peripheral specs
must be named `<device>-spec.md` because `spec_check.py` loads `*.spec.md` as board specs (LS5's
layout); `cleanroom-spec`'s other landing text is reconciled with policy 1 when it moves (LS6,
LS7).

## LS5 — The three spec repositories

**Design coverage:** LS-R11, LS-R12; proves LS-R4.
**Dependencies:** LS1–LS4 merged to `origin/main` (CI pins a driver-lab commit on `main`); the
user's explicit go to create the three public repositories and push to them.
**In scope:** `hardware-specs-gpl`, `hardware-specs-docs`, `hardware-specs-permissive` under
`curtisgalloway`: LICENSE (GPL-2.0-only; CC-BY-4.0; Apache-2.0 + NOTICE), root marker under
`specs/` with `license:` and `accepts:`, README (placement rule, "which repo" table, the
"every claim is anchored and checked in CI" statement on the first screen), CI, and a CI
self-test.
**Out of scope:** any real spec (the regeneration workstream); bringup-kit's roots (LS12).

### Implementation steps
1. Create each local checkout beside driver-lab with the files above and SPDX
   headers (CI files Apache-2.0 in the docs repo). Commit locally.
2. CI: check out driver-lab at a pinned `main` commit (the pattern `checks.yml` uses for
   public-skills); run `spec_check.py specs --require-license` and `anchor_check.py --root
   specs` on each spec. The permissive repo also checks out `hardware-specs-docs` as a second
   root so cross-repo overlays resolve.
3. Self-test step: copy LS2's fit and misfit fixtures for this repo's license into a temp root
   and assert the misfit fails and the fit passes (the fixtures are not published as specs).
4. On the user's go: create the repos (public), push, confirm CI green; record the runs.

### Acceptance criteria
- [ ] All three repos exist, public (quote `gh repo view --json visibility`), CI green on `main`.
- [ ] Each self-test shows the misfit failing with the gate's message and the fit passing
      (quote the CI log lines).
- [ ] No private infrastructure in any file or commit message (privacy check run on each).

### Testing and review
- Reviewer subagent reads the three repos and their CI logs. Focus: the README table matches
  the design; the pinned driver-lab commit is on `main`; licenses and SPDX headers correct.

### Session sizing
Three small repos of the same shape; the uncertainty is CI wiring. Split point: GPL and docs
repos first, permissive (with the second-root checkout) as a second checkpoint.

### Evidence and findings
Status: **complete.** The board-spec license gate in `spec_check.py --require-license` and the
shipped root's license fields (the user's decisions of 2026-10-06); `hardware-specs-gpl`,
`hardware-specs-docs` and `hardware-specs-permissive` public, CI pinned to driver-lab `5d7eac2`
and green, each self-test failing its misfit with the gate's message.
Open limitation: CI checks form, pins and licenses, not `[src:]` resolution (no source checkout).
Evidence: [LS5](../evidence/LS5.md). Notebook: [LS5](../notebook/LS5.md).

## LS6 — `cleanroom-skills` created with history

**Outcome:** `curtisgalloway/cleanroom-skills`, public, holding `cleanroom-spec`,
`cleanroom-implementer` and `cleanroom-investigator` (renamed from `os-investigator`) with their
history (21 commits kept by `git filter-repo` from driver-lab `5d7eac2`, plus the rename and the
repository's own files), a commit map, plugin manifests, README, CI green.
**Design coverage:** LS-R14 (repository, history, CI), LS-R8 (the provenance template moved with
`cleanroom-spec`). **Dependencies:** LS5; the user's go (2026-10-06).
**Status:** complete. Evidence: [LS6](../evidence/LS6.md). Notebook: [LS6](../notebook/LS6.md).
**Open limitations:** until LS7 removes driver-lab's copies, both plugins carry the three skills;
the `cleanroom-skills` README says to use plugin-qualified names meanwhile, and LS7 deletes that
paragraph.

## LS7 — driver-lab's skills neutral; clean-room rules moved

**Outcome:** driver-lab's open skills carry no clean-room text: `board-expert` has a method and
report of its own and no longer loads `os-investigator`; `SPEC-FORMAT.md` says `[source-observed]`
is defined by an extension (the checker still accepts it) and states how a fact read only from
code appears on the open side; `board-spec-scaffold`, `spec-verifier`, `anchored-peripheral-spec`
and `reference-driver-review` no longer name the clean-room skills; the three clean-room skill
directories, their CI steps and the public-skills checkout are gone. In `cleanroom-skills`
(`670cecd`), `cleanroom-investigator` wraps `board-expert` (plus `BOARD-SPECS.md`) and a new
`cleanroom-verifier` skill wraps `spec-verifier`; every removed passage is in the evidence's move
list.
**Design coverage:** LS-R15, LS-R14 (spec-verifier part). **Dependencies:** LS6.
**Status:** complete. Evidence: [LS7](../evidence/LS7.md). Notebook: [LS7](../notebook/LS7.md).
Review: one reviewer subagent; six should-fix items and five nits, all resolved.
**Open limitations:** the acceptance grep's one recorded exception is
`skills/campaign-review/tests/fixtures/deployment-cr5.yaml` (a copy of the frozen CR5
deployment); root documents still describe the clean-room skills until LS8.

## LS8 — Documents split; frozen archive; open-side check

**Outcome:** driver-lab's `DESIGN.md` keeps the open method and its clean-room passages (28, by
line range) are in a new `cleanroom-skills/DESIGN.md`, moved verbatim apart from names and
links; `README.md`'s clean-room section, `AGENTS.md`'s Isolation rule and five glossary rows
moved to their `cleanroom-skills` counterparts, and the README names the method in one pointer
line; frozen-archive headers on the archive documents, `evals/` (a new `evals/README.md` plus
the two campaigns' READMEs), `evidence/` (a new README) and the notebook index;
`utilities/check-open-side.py` with 13 tests, in CI and the AGENTS.md list.
**Design coverage:** LS-R20, LS-R14 (design text). **Dependencies:** LS7.
**Status:** complete. Evidence: [LS8](../evidence/LS8.md). Notebook: [LS8](../notebook/LS8.md).
Review: one docs reviewer subagent; seven should-fix items and 13 nits, all resolved but one
nit (pinning links to `cleanroom-skills`, after its merge).
**Open limitations:** the allowlist adds, beyond the design's list, three history records
(`PROCESS-NOTES.md`, `TRANSITION.md`, `docs/STORY.md`; the last moved to `cleanroom-skills` on
2026-10-07 and left the allowlist), the whole of `IMPLEMENTATION-PLAN.md`
and the checker itself, each justified in the evidence; links into `cleanroom-skills` at `main`
resolve only once its LS8 pull request merges, and pinning them to that merge is left for later.

## LS9 — Rename `anchored-peripheral-spec` to `peripheral-spec`

**Design coverage:** LS-R16, LS-R7 (renamed).
**Dependencies:** LS8.
**In scope:** directory and skill rename; "anchored spec" → "peripheral spec" in prose outside
the archive; CI path; the three spec repos' CI repinned to a driver-lab commit with the new
path (a PR in each); `cleanroom-skills` references.
**Out of scope:** consumer repos (LS12).

### Acceptance criteria
- [x] No `anchored-peripheral-spec` outside the frozen archive and history (quote the grep).
- [x] The three spec repos' CI green on the new pin; `cleanroom-skills` CI green (run locally and passing; the orchestrator confirmed on 2026-10-07 that all five LS9 pull requests' CI succeeded and that they merged: driver-lab #53, `cleanroom-skills` #3, and #1 in each of `hardware-specs-gpl`, `-docs` and `-permissive`).
- [x] The full check list passes.

### Testing and review
- Reviewer subagent. Focus: references outside driver-lab that this milestone owns.

### Session sizing
Mechanical rename across four repos. Low uncertainty.

### Evidence and findings
Status: complete; the orchestrator confirmed the five pull requests' CI green and merged them on 2026-10-07. Evidence: [LS9](../evidence/LS9.md). Notebook: [LS9](../notebook/LS9.md).

## LS10 — `hardware-investigator`

**Design coverage:** LS-R17.
**Dependencies:** LS9.
**In scope:** a new open-side skill answering board and peripheral questions from sources a
target root accepts, through `board-expert`, producing anchored facts with named, licensed pins
for `peripheral-spec`; refusing (with the reason) a source the target root does not accept.
**Out of scope:** a wall; generating whole specs (that is `peripheral-spec`).

### Implementation steps
1. Write `skills/hardware-investigator/SKILL.md` (with SPDX header after front matter): inputs
   (question, target root), method (consult `board-expert`, locate source, pin it with its
   license, check acceptability against the root's accepts list, cite), output (anchored facts
   ready for `peripheral-spec`).
2. A worked example on the `board-expert` fixtures (`widgetboard`, `widgetsoc`) and a fixture
   source tree with a license, documented in the skill.
3. If a helper script is needed (for example, printing a root's accepts list), it follows the
   exit-code contract and has tests.
4. README skill table and glossary.

### Acceptance criteria
- [x] A reviewer following the skill on the fixture produces anchored facts that pass
      `anchor_check.py --root` for an accepting root, and is told to stop for a refusing one.
- [x] The skill names no clean-room concept; `check-open-side.py` passes.
- [x] Portability: `portability_scan.py` on any new script passes.

### Testing and review
- Reviewer subagent runs the worked example as written. Focus: the skill's instructions are
  enough on their own; license checks happen before citing, not after.

### Session sizing
One new skill; uncertainty is in how much method to write. Split point: SKILL.md and the
worked example before any helper script.

### Evidence and findings
Status: complete and merged (driver-lab #54). Evidence: [LS10](../evidence/LS10.md). Notebook: [LS10](../notebook/LS10.md).

## LS11 — Firewall by name

**Design coverage:** LS-R18.
**Dependencies:** LS10 (every blocked name exists).
**In scope (in `cleanroom-skills`):** `cleanroom_hook.py`'s default policy blocks reads of the
`board-expert`, `hardware-investigator` and `cleanroom-investigator` skill directories (however
installed: plugin cache, linked checkout) and of any `hardware-specs-gpl` checkout; the
investigator and verifier roles stay allowed as today; tests; the prose ban stays.
**Out of scope:** blocking the docs or permissive spec repos (allowed by design).

### Acceptance criteria
- [x] Hook tests: each blocked target denied for the implementer role, allowed for the
      investigator role, across path, command and search forms the hook already handles.
- [x] A session-audit fixture that reads `board-expert` is flagged (design acceptance item 3).
- [x] `cleanroom-skills` CI green, including the portability scan (the CI steps, with the portability
      scan at the CI pin, passed locally; remote CI passed on `cleanroom-skills` #4 and driver-lab #55,
      both merged 2026-10-07).

### Testing and review
- Review method: **`review-swarm`** (an access control). Focus: bypasses by alternate install
  paths, symlinks, case, and commands that read without naming the path.

### Session sizing
One script and its tests, an existing pattern. Low to medium uncertainty (install paths).

### Evidence and findings
Status: complete and merged: `cleanroom-skills` #4 (`199059a`, `35ff17e`) and driver-lab #55; the second review-swarm over `35ff17e` (2026-10-07) led to `cleanroom-skills` `5310aac` and `89418fd`, merged as `cleanroom-skills` #6 and driver-lab #58. Evidence: [LS11](../evidence/LS11.md). Notebook: [LS11](../notebook/LS11.md).

## LS12 — Consumers updated

**Design coverage:** LS-R19, LS-R13.
**Dependencies:** LS11; the user's "push" for each repo (public-skills is public: business-hours
schedule applies; check every repo's visibility first).
**In scope:** `fuchsia-skills` (README, AGENTS.md, onboarding doc, `fuchsia-source` skill,
including its stale `rpi-expert` reference); `bringup-kit` (templates/AGENTS.md, README,
hardware-inventory template, Bringup.md; spec roots naming the docs and permissive repos only);
`public-skills` (README, marketplace description, `agent-agnostic-skills` links to
`cleanroom-implementer/scripts` → `cleanroom-skills`); driver-lab's CI pin of public-skills
bumped to the commit with the new links (moot since LS7 removed that pin and its only use);
driver-lab's marketplace entry.
**Out of scope:** bringup-kit's archived laps (`laps/`), which keep their historical names.

### Acceptance criteria
- [x] A grep of each consumer (excluding archives it declares) finds none of
      `os-investigator`, `anchored-peripheral-spec`, `rpi-expert`, and no clean-room skill
      named with a driver-lab path (quote the commands and output).
- [x] bringup-kit's spec roots name no `hardware-specs-gpl`; its tests pass.
- [x] Each consumer's own checks pass locally (remote CI is the orchestrator's); the driver-lab pin is moot since LS7.

### Testing and review
- Reviewer subagent with the three diffs. Focus: handoffs by name still resolve.

### Session sizing
Three repos, many small edits. Split point: one checkpoint per repo.

### Evidence and findings
Status: complete and merged: `fuchsia-skills` #7 (`c09eac4`), `bringup-kit` #17 (`c20d7a3`), `public-skills` #100 (`10ab32b`) and driver-lab #57. Evidence: [LS12](../evidence/LS12.md). Notebook: [LS12](../notebook/LS12.md).

## LS-G — Whole-outcome acceptance

Checks the design's [acceptance](LICENSE-SPLIT.md#acceptance-for-the-whole-outcome) items 1–5
together, from fresh clones of all eight repositories (driver-lab, the three spec repos,
`cleanroom-skills`, and the three consumers): every LS-R row in the coverage table with its evidence
link; the scratch setup of item 2 run end to end against the published CI; `cleanroom-skills`
installed beside driver-lab (item 3); driver-lab's full list and the archive checks (item 4);
the consumer greps (item 5). Review: `review-swarm` over the combined state, focused on
cross-milestone interactions (pins, paths, names).

### Evidence and findings
Status: complete. Items 1, 3, 4 and 5 met from fresh clones; item 2 met by running each spec
repository's CI steps locally and by nine scratch pull requests whose published CI matched every
cell. Evidence:
[LS-G](../evidence/LS-G.md). Notebook: [LS-G](../notebook/LS-G.md).

## Discovered work / backlog

- **Spec regeneration** (non-goal here): regenerate the deleted specs into the three repos,
  starting with the bcm2711 docs spec and its permissive overlay (facts 2, 3, 6 of the design's
  audit), which also proves cross-repo overlays for real.
- **`cleanroom-skills` public-skills pin** (LS-G, review findings F2/F6): bump `d63e3f1` to a
  `main` commit at or after `10ab32b` and fix the comment that says driver-lab pins the same
  commit; closes LS-R19's last clause.
- **`bringup-kit` README** (LS-G item 1): add 0BSD to the permissive repository's source list.
- **Stale branch** `origin/specs/source-observed-audit-fixes` (closed PR #41, two unique commits
  by `git cherry`): the user decides whether to delete it.

## Next session

- Current milestone: LS-G complete. LS1–LS12 and the LS11 re-review are merged (driver-lab #57
  and #58), and all five acceptance items are met, item 2 also in published CI
  ([LS-G's evidence](../evidence/LS-G.md)).
- Resume action: the two small fixes in other repositories under the backlog close the split; the next workstream is spec regeneration
  (backlog below).
- Read first: [LS-G's evidence](../evidence/LS-G.md) (its limitations and the findings left for
  other repositories).
