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
| LS2 | Root license fields and the license gate | LS1 | pending |
| LS3 | Checkable doc anchors | LS1 | pending |
| LS4 | Placement guidance, provenance template, "why this exists", format docs | LS2, LS3 | pending |
| LS5 | The three spec repositories, with CI that proves the gate | LS1–LS4 merged; user's go to create repos | pending |
| LS6 | `cleanroom-skills` created with history, its CI green | LS5; user's go to create the repo | pending |
| LS7 | driver-lab's skills neutral; clean-room rules moved; moved skills removed | LS6 | pending |
| LS8 | driver-lab's documents split; frozen archive marked; open-side mention check | LS7 | pending |
| LS9 | `anchored-peripheral-spec` renamed `peripheral-spec`; spec repos repinned | LS8 | pending |
| LS10 | `hardware-investigator` skill | LS9 | pending |
| LS11 | Firewall by name in `cleanroom-implementer`'s hook | LS10 | pending |
| LS12 | Consumers updated: names, repos, spec roots, marketplaces | LS11 | pending |
| LS-G | Whole-outcome acceptance | LS1–LS12 | pending |

Ordering: tooling and spec repos first (the user's decision), so LS1–LS4 land under the current
skill names and LS9 renames them. The split (LS6–LS11) follows. LS12 touches each consumer once,
after every name is final. LS3 may run in parallel with LS2.

## Design coverage

| Requirement | Milestones | Verification |
|---|---|---|
| LS-R1 Root license | LS2 (code), LS4 (docs) | `spec_check.py` tests for both fields, warning and `--require-license` |
| LS-R2 Resource license | LS2 | `check_resources` tests |
| LS-R3 Several named pins | LS1 | `anchor_check.py` tests: named and legacy pins, overwrite bug |
| LS-R4 License gate | LS2, proven in LS5 | gate tests incl. `OR`/`AND`; each repo's CI self-test |
| LS-R5 Checkable doc anchors | LS3 | tests for registry, page range, hash mismatch |
| LS-R6 Anchor-tool tests and CI | LS1 | new test suite runs in `checks.yml` |
| LS-R7 Placement guidance | LS4, renamed in LS9 | reviewer traces the table to the design |
| LS-R8 Provenance template | LS4, moves in LS6 | template present; `cleanroom-spec` refers to it |
| LS-R9 Per-repo pins in verification | LS1 (`inventory_check.py`), LS4 (`spec-verifier` text) | tests; reviewer |
| LS-R10 Why this exists | LS4 | README section present before LS6's public repo |
| LS-R11 Three repos | LS5 | repos exist, CI green on `main` |
| LS-R12 Gate proven per repo | LS5 | CI self-test fails the misfit fixture, passes the fit one |
| LS-R13 Consumers point at the right repos | LS12 | bringup-kit roots; public-skills README |
| LS-R14 `cleanroom-skills` | LS6, LS7 | repo public, history present, its CI green |
| LS-R15 Neutral board-expert | LS7 | grep of the open skills; `spec_check.py` still accepts `[source-observed]` |
| LS-R16 Renames | LS9 | no `anchored-peripheral-spec` outside the archive |
| LS-R17 `hardware-investigator` | LS10 | skill review; a worked question on a fixture root |
| LS-R18 Firewall by name | LS11 | hook tests for each blocked skill and GPL checkout |
| LS-R19 Consumers renamed | LS12 | grep of each consumer finds no stale name |
| LS-R20 Open side only | LS8 | mention check in CI with the archive allowlist |

## Checks added by this plan

Each milestone adds its checks to `.github/workflows/checks.yml` and to the AGENTS.md list in
the same commit. Proposed, final names decided in the milestone:

```bash
python3 -m unittest discover -s skills/anchored-peripheral-spec/tests   # LS1; path changes in LS9
python3 utilities/check-open-side.py                                     # LS8
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

**Design coverage:** LS-R1, LS-R2, LS-R4.
**Dependencies:** LS1.
**In scope:** root marker `license:` and `accepts:`; `--require-license`; resource license
validation; an SPDX expression parser; `anchor_check.py --root`.
**Out of scope:** documentation of the fields in `SPEC-FORMAT.md` beyond a stub entry (LS4);
doc-anchor registry (LS3).

### Implementation steps
1. An SPDX expression parser (identifiers, `OR`, `AND`, `WITH`, parentheses, `-or-later` and
   `+`), with a small known-identifier list. Proposed location
   `skills/board-expert/scripts/spdx.py`, imported by `spec_check.py` and, by relative path, by
   `anchor_check.py`; the milestone may choose another shared location and records why.
   Acceptance rule: `A OR B` passes if either passes; `A AND B` only if both; `GPL-2.0-or-later`
   passes where `GPL-2.0-only` is accepted only if the accepts list says so explicitly (the
   design's GPL repo lists both).
2. `spec_check.py`: read `license:` and `accepts:` from the marker; validate both; warn when
   absent; `--require-license` makes absence exit 1. `check_resources`: validate
   `repos[].license` as SPDX; required in a root with `accepts:`.
3. `anchor_check.py --root <dir>`: read the root marker; fail each anchor whose pin's license is
   not accepted, or has no license when the root declares `accepts:`. Report anchor, pin,
   license and the accepts list.
4. Fixtures: three roots shaped like the three repos (GPL, docs, permissive) and specs that fit
   and misfit each, reused by LS5's CI self-test.
5. Short `SPEC-FORMAT.md` entry for the two fields (full guidance in LS4).

### Acceptance criteria
- [ ] The design's acceptance item 2 holds on fixtures: a GPL-2.0-only pin fails in the docs
      and permissive roots and passes in the GPL root; a `GPL-2.0 OR MIT` pin passes in the
      permissive and GPL roots; a spec with no pins passes everywhere.
- [ ] A marker with no license fields loads with a warning; with `--require-license` it exits 1.
- [ ] An invalid SPDX string in a marker or a resource exits 1 with the field named.
- [ ] bringup-kit's test-written markers (`layer: public` only) still pass without the flag.
- [ ] The full check list passes.

### Testing and review
- Tests: parser table tests; spec_check marker and resource tests; gate tests per fixture root.
- Review method: **`review-swarm`** (the gate decides what may be published).
- Review focus: a misfit that passes (false accept) is the severe failure; `OR`/`AND` handling;
  messages a spec author can act on.

### Session sizing
Two scripts and one new module; fixtures shared with LS5. Split point: spec_check side (steps
1, 2) and anchor_check gate (steps 3, 4) as two checkpoints.

### Evidence and findings
Status: pending. Evidence: [LS2](../evidence/LS2.md). Notebook: [LS2](../notebook/LS2.md).

## LS3 — Checkable doc anchors

**Design coverage:** LS-R5.
**Dependencies:** LS1 (may run in parallel with LS2).
**In scope:** a `docs:` registry in spec front matter, named `[doc:<name> p.N]` anchors, page
range check, `--docs-dir` hash check; `--require-license` requiring named doc anchors.
**Out of scope:** fetching documents; checking quoted text against a PDF.

### Implementation steps
1. Grammar: `docs:` list (`name`, `title`, `url`, `sha256`, optional `pages`); `[doc:<name>
   p.N]`, `pp.N-M`, `§x.y` forms; several per tag separated by `;` as today.
2. Checks: unknown name, page out of range, malformed sha256 (exit 1); with `--docs-dir`, hash
   the file named by the entry (proposed: `<docs-dir>/<name>.pdf` or an explicit `file:`) and
   fail on mismatch, skip with a note when missing.
3. Unnamed `[doc: …]` stays a warning-only form; under `--require-license` it is an error.
4. Tests with a small generated file whose hash is pinned.

### Acceptance criteria
- [ ] Each failure above exits 1 with the anchor and document named; a correct spec passes.
- [ ] A hash mismatch fails only with `--docs-dir`; without it the check is structural.
- [ ] Existing specs with unnamed doc anchors still pass without `--require-license`.
- [ ] The full check list passes.

### Testing and review
- Reviewer subagent. Focus: backward compatibility; no network access in the checker.

### Session sizing
One script, one feature. Low uncertainty.

### Evidence and findings
Status: pending. Evidence: [LS3](../evidence/LS3.md). Notebook: [LS3](../notebook/LS3.md).

## LS4 — Guidance, provenance template, "why this exists", format docs

**Design coverage:** LS-R7, LS-R8, LS-R9 (`spec-verifier` text), LS-R10, LS-R1 docs.
**Dependencies:** LS2, LS3.
**In scope:** `anchored-peripheral-spec/SKILL.md` placement rule and "which repo" table;
`SPEC-FORMAT.md` license fields and doc registry; `board-spec-scaffold` templates gain
`license:`/`accepts:`; `cleanroom-spec` `PROVENANCE.md` template; `spec-verifier`'s anchored-spec
procedure for named pins and the gate; README "Why this exists and what it is not for".
**Out of scope:** the clean-room split's text moves (LS7, LS8).

### Implementation steps
1. Placement rule and table (repo, license, accepts list, what goes there) in the
   anchored-spec skill; replace the "is it yours?" test.
2. `SPEC-FORMAT.md`: root license fields, `--require-license`, `docs:` registry, named pins.
3. Scaffold templates: marker fields with placeholders; spec templates show named pins.
4. Proposed `skills/cleanroom-spec/templates/PROVENANCE.md` and the step in `cleanroom-spec`
   that fills it, stating it stays private.
5. `spec-verifier`: anchored-spec procedure runs `anchor_check.py --root` with every pin.
6. README: the "Why this exists" section near the top, using the design's community-reaction
   points; glossary rows for any new term.

### Acceptance criteria
- [ ] Every command and field the docs show exists in LS1–LS3's code (reviewer checks each).
- [ ] The "which repo" table matches the design's repo table exactly.
- [ ] The provenance template has every field LS-R8 lists.
- [ ] The privacy check and full check list pass.

### Testing and review
- Docs-only reviewer subagent tracing each claim to code or design.

### Session sizing
Six files of prose, no code. Low uncertainty.

### Evidence and findings
Status: pending. Evidence: [LS4](../evidence/LS4.md). Notebook: [LS4](../notebook/LS4.md).

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
Status: pending. Evidence: [LS5](../evidence/LS5.md). Notebook: [LS5](../notebook/LS5.md).

## LS6 — `cleanroom-skills` created with history

**Design coverage:** LS-R14 (repository, history, CI), LS-R8 (template moves with
`cleanroom-spec`).
**Dependencies:** LS5; the user's explicit go to create the public repository. LS4's README
section and the new repo's own README framing must be in place before it is public.
**In scope:** a new repo holding `cleanroom-spec`, `cleanroom-implementer`, and `os-investigator`
renamed `cleanroom-investigator` (with `leak_scan.py` and tests), with history; plugin manifest;
CI running the moved tests and the portability scan; README; a commit map as in TRANSITION.md.
**Out of scope:** removing the skills from driver-lab and moving clean-room rules out of
`board-expert` and `spec-verifier` (LS7). For one milestone both repos carry the skills.

### Implementation steps
1. In a scratch clone, `git filter-repo` keeping the three skill paths (and their history
   through the public-skills import), renaming `skills/os-investigator` →
   `skills/cleanroom-investigator`; fix the skill's own name and internal references.
2. Plugin manifest (`.claude-plugin/plugin.json`, marketplace entry), LICENSE (Apache-2.0),
   README (what it is, what it is not for, that output is never published, that it depends on
   driver-lab, a pointer to the frozen evals at a pinned driver-lab commit), AGENTS.md.
3. CI: the three test suites and `portability_scan.py` on `cleanroom-implementer/scripts`,
   pinned as driver-lab does today.
4. Commit map file from the filter-repo run.
5. On the user's go: create the public repo, push, confirm CI green.

### Acceptance criteria
- [ ] The repo is public, CI green; `git log --follow` on a moved file shows pre-split history.
- [ ] `cleanroom-investigator`'s `SKILL.md` name field and every internal reference use the new
      name; no `os-investigator` outside history and the commit map.
- [ ] Installed beside driver-lab, the moved tests pass locally.
- [ ] Privacy check run on the new repo's files and commit messages (history inherited from
      a public repo; the check covers new commits).

### Testing and review
- Reviewer subagent. Focus: history preserved; nothing outside the three skills leaked in by
  the filter; the README's framing.

### Session sizing
Mechanical with one risky step (filter-repo paths). Split point: local repo complete and
verified (steps 1–4) before the public push.

### Evidence and findings
Status: pending. Evidence: [LS6](../evidence/LS6.md). Notebook: [LS6](../notebook/LS6.md).

## LS7 — driver-lab's skills neutral; clean-room rules moved

**Design coverage:** LS-R15, LS-R14 (spec-verifier part).
**Dependencies:** LS6.
**In scope:** a paired change in both repos. In driver-lab: `board-expert` stops loading
`os-investigator`; `SPEC-FORMAT.md`'s clean-room rules and the `[source-observed]` description
leave (the tag stays accepted, described as defined by an extension); `board-spec-scaffold`'s
subagent and templates drop clean-room text; `spec-verifier`'s clean-room section and the
clean-room text in its shared parts leave; delete `skills/cleanroom-spec`,
`skills/cleanroom-implementer`, `skills/os-investigator`; CI drops their steps; plugin
description updated. In `cleanroom-skills`: `cleanroom-investigator` wraps `board-expert` and
carries the moved rules; the clean-room verification lands as a `cleanroom-verifier` skill or a
section of `cleanroom-spec` (decide and record).
**Out of scope:** `DESIGN.md` and other documents (LS8); renames on the open side (LS9).

### Implementation steps
1. Move the text, not rewrite it: each removed passage lands in `cleanroom-skills` in the same
   change; list each move (source lines → destination) in the evidence.
2. Update `board-expert/tests` that expected clean-room text (`test_spec_check.py` lines the
   design's current-state section points to).
3. Remove the three skill directories and their CI steps; keep `portability_scan.py` only in
   `cleanroom-skills`.
4. Fix references in the remaining open skills (`reference-driver-review`, `campaign-review`
   fixtures) by pointing at `cleanroom-skills` or removing them.

### Acceptance criteria
- [ ] `rg -i 'os-investigator|clean-?room|the wall|research subagent' skills/` in driver-lab
      matches nothing except `[source-observed]` in `spec_check.py` and its test (quote output).
- [ ] Every removed passage has a destination in `cleanroom-skills` (the move list).
- [ ] driver-lab's remaining check list and `cleanroom-skills`' CI both pass.

### Testing and review
- Reviewer subagent with both diffs. Focus: no rule lost in the move; `board-expert` still
  works as a plain fact finder (its tests); `cleanroom-investigator` actually wraps it.

### Session sizing
Many files but mostly moves. Split point: board-expert and scaffold (with their counterparts)
as one checkpoint, spec-verifier and the deletions as a second.

### Evidence and findings
Status: pending. Evidence: [LS7](../evidence/LS7.md). Notebook: [LS7](../notebook/LS7.md).

## LS8 — Documents split; frozen archive; open-side check

**Design coverage:** LS-R20, LS-R14 (design text).
**Dependencies:** LS7.
**In scope:** `DESIGN.md`'s clean-room sections move to `cleanroom-skills` (proposed
`DESIGN.md` there); driver-lab's `README.md`, `AGENTS.md`, `GLOSSARY.md` lose clean-room text
except one README pointer line; archive headers on the frozen files the design lists; a new
`utilities/check-open-side.py` with that allowlist, in CI and AGENTS.md; marketplace and plugin
descriptions corrected (they still name deleted board experts).
**Out of scope:** consumer repos (LS12).

### Implementation steps
1. Move DESIGN.md's clean-room sections (the "two walls", "Check what crosses the licensing
   wall", reconstruction parts); keep the evidence model and continuous review in driver-lab.
   Fix links from both sides; the frozen archive keeps its links working.
2. Archive header on each frozen document: frozen as of the split, new rounds run from
   `cleanroom-skills`.
3. `check-open-side.py`: fail on clean-room terms outside the allowlist; tests for the script.
4. AGENTS.md: rules that are clean-room-only (isolation, sandbox) move or point to
   `cleanroom-skills`; the check list updated.

### Acceptance criteria
- [ ] `check-open-side.py` passes on driver-lab and fails on a planted mention (test).
- [ ] No broken relative links (a link check over changed files; record the command).
- [ ] The frozen archive's CI checks (`campaign-review` index check, ENC28J60 tests) still pass.

### Testing and review
- Docs reviewer subagent. Focus: nothing the open side relies on moved away; the archive stays
  readable.

### Session sizing
DESIGN.md is 1216 lines; moving sections plus link fixes is the bulk. Split point: archive
headers and the check script as one checkpoint, the DESIGN.md move as another.

### Evidence and findings
Status: pending. Evidence: [LS8](../evidence/LS8.md). Notebook: [LS8](../notebook/LS8.md).

## LS9 — Rename `anchored-peripheral-spec` to `peripheral-spec`

**Design coverage:** LS-R16, LS-R7 (renamed).
**Dependencies:** LS8.
**In scope:** directory and skill rename; "anchored spec" → "peripheral spec" in prose outside
the archive; CI path; the three spec repos' CI repinned to a driver-lab commit with the new
path (a PR in each); `cleanroom-skills` references.
**Out of scope:** consumer repos (LS12).

### Acceptance criteria
- [ ] No `anchored-peripheral-spec` outside the frozen archive and history (quote the grep).
- [ ] The three spec repos' CI green on the new pin; `cleanroom-skills` CI green.
- [ ] The full check list passes.

### Testing and review
- Reviewer subagent. Focus: references outside driver-lab that this milestone owns.

### Session sizing
Mechanical rename across four repos. Low uncertainty.

### Evidence and findings
Status: pending. Evidence: [LS9](../evidence/LS9.md). Notebook: [LS9](../notebook/LS9.md).

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
- [ ] A reviewer following the skill on the fixture produces anchored facts that pass
      `anchor_check.py --root` for an accepting root, and is told to stop for a refusing one.
- [ ] The skill names no clean-room concept; `check-open-side.py` passes.
- [ ] Portability: `portability_scan.py` on any new script passes.

### Testing and review
- Reviewer subagent runs the worked example as written. Focus: the skill's instructions are
  enough on their own; license checks happen before citing, not after.

### Session sizing
One new skill; uncertainty is in how much method to write. Split point: SKILL.md and the
worked example before any helper script.

### Evidence and findings
Status: pending. Evidence: [LS10](../evidence/LS10.md). Notebook: [LS10](../notebook/LS10.md).

## LS11 — Firewall by name

**Design coverage:** LS-R18.
**Dependencies:** LS10 (every blocked name exists).
**In scope (in `cleanroom-skills`):** `cleanroom_hook.py`'s default policy blocks reads of the
`board-expert`, `hardware-investigator` and `cleanroom-investigator` skill directories (however
installed: plugin cache, linked checkout) and of any `hardware-specs-gpl` checkout; the
investigator and verifier roles stay allowed as today; tests; the prose ban stays.
**Out of scope:** blocking the docs or permissive spec repos (allowed by design).

### Acceptance criteria
- [ ] Hook tests: each blocked target denied for the implementer role, allowed for the
      investigator role, across path, command and search forms the hook already handles.
- [ ] A session-audit fixture that reads `board-expert` is flagged (design acceptance item 3).
- [ ] `cleanroom-skills` CI green, including the portability scan.

### Testing and review
- Review method: **`review-swarm`** (an access control). Focus: bypasses by alternate install
  paths, symlinks, case, and commands that read without naming the path.

### Session sizing
One script and its tests, an existing pattern. Low to medium uncertainty (install paths).

### Evidence and findings
Status: pending. Evidence: [LS11](../evidence/LS11.md). Notebook: [LS11](../notebook/LS11.md).

## LS12 — Consumers updated

**Design coverage:** LS-R19, LS-R13.
**Dependencies:** LS11; the user's "push" for each repo (public-skills is public: business-hours
schedule applies; check every repo's visibility first).
**In scope:** `fuchsia-skills` (README, AGENTS.md, onboarding doc, `fuchsia-source` skill,
including its stale `rpi-expert` reference); `bringup-kit` (templates/AGENTS.md, README,
hardware-inventory template, Bringup.md; spec roots naming the docs and permissive repos only);
`public-skills` (README, marketplace description, `agent-agnostic-skills` links to
`cleanroom-implementer/scripts` → `cleanroom-skills`); driver-lab's CI pin of public-skills
bumped to the commit with the new links; driver-lab's marketplace entry.
**Out of scope:** bringup-kit's archived laps (`laps/`), which keep their historical names.

### Acceptance criteria
- [ ] A grep of each consumer (excluding archives it declares) finds none of
      `os-investigator`, `anchored-peripheral-spec`, `rpi-expert`, and no clean-room skill
      named with a driver-lab path (quote the commands and output).
- [ ] bringup-kit's spec roots name no `hardware-specs-gpl`; its tests pass.
- [ ] Each consumer's own checks pass; driver-lab CI green on the new pin.

### Testing and review
- Reviewer subagent with the three diffs. Focus: handoffs by name still resolve.

### Session sizing
Three repos, many small edits. Split point: one checkpoint per repo.

### Evidence and findings
Status: pending. Evidence: [LS12](../evidence/LS12.md). Notebook: [LS12](../notebook/LS12.md).

## LS-G — Whole-outcome acceptance

Checks the design's [acceptance](LICENSE-SPLIT.md#acceptance-for-the-whole-outcome) items 1–5
together, from fresh clones of all six repositories (driver-lab, the three spec repos,
`cleanroom-skills`, and the consumers): every LS-R row in the coverage table with its evidence
link; the scratch setup of item 2 run end to end against the published CI; `cleanroom-skills`
installed beside driver-lab (item 3); driver-lab's full list and the archive checks (item 4);
the consumer greps (item 5). Review: `review-swarm` over the combined state, focused on
cross-milestone interactions (pins, paths, names). Evidence: [LS-G](../evidence/LS-G.md).

## Discovered work / backlog

- **Spec regeneration** (non-goal here): regenerate the deleted specs into the three repos,
  starting with the bcm2711 docs spec and its permissive overlay (facts 2, 3, 6 of the design's
  audit), which also proves cross-repo overlays for real.
- **Stale branch** `origin/specs/source-observed-audit-fixes` (closed PR #41, two unique commits
  by `git cherry`): the user decides whether to delete it.

## Next session

- Current milestone: LS1 complete; LS2 is next (LS3 may run beside it).
- Completed: LS1 on branch `license-split/ls1` (checkpoint commit `driver-porting: LS1 —
  anchor tools under test; several named pins`), not pushed.
- Remaining decisions: none blocking LS2. LS5 and LS6 each need the user's go to create public
  repositories.
- Resume action: after the LS1 pull request merges, begin **LS2** on `license-split/ls2` from a
  fetched `origin/main`.
- Read first: the design, this plan's conventions and LS2, the notebook index, LS1's evidence,
  `skills/board-expert/scripts/spec_check.py` (root and resource handling) and
  `skills/anchored-peripheral-spec/scripts/anchor_check.py`.
