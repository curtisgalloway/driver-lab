<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Spec format 2 — implementation plan

Design: [SPEC-FORMAT-V2.md](SPEC-FORMAT-V2.md), approved by the user on 2026-10-08 with decisions
D1–D22; revision: merge commit `c5d9778` on `main` (pull request #65; the approval commit inside
it is `6844645`, "docs: spec format 2 design approved").
Notebook: [index](../notebook/index.md), design chapter [SF2-design](../notebook/SF2-design.md);
process log: [PROCESS-NOTES.md](../PROCESS-NOTES.md). Review learnings this plan absorbs:
[SPEC-REGEN-learnings](../notebook/SPEC-REGEN-learnings.md).
Project checks: the full list in [AGENTS.md](../AGENTS.md#checks), plus the checks each
milestone adds ([Checks added by this plan](#checks-added-by-this-plan)).

## Terms

- **Spec, fact record, fact reference, root-qualified reference, support entry, basis hash,
  canonical form, rendered view, viewer, badge** — the design's [Terms](SPEC-FORMAT-V2.md#terms)
  and the [glossary](../GLOSSARY.md).
- **Format 1 / v1** — today's Markdown specs and their checkers (`spec_check.py`,
  `anchor_check.py`, `mdtokens.py`). **Format 2 / v2** — the design's YAML specs.
- **Milestone** — a deliverable with acceptance criteria, tests, review and a checkpoint; one
  per session. **Code unit / docs unit / content unit** — a milestone whose main output is
  tools and tests / skill and contract text / spec and record content; the review method
  differs by kind (below).
- **Spec repositories** — `hardware-specs-docs`, `hardware-specs-permissive`,
  `hardware-specs-gpl`.
- **Stop rule** — the limit on review rounds set before a milestone starts; reaching it hands
  the remaining blockers to the user instead of starting another round.

## Conventions

- **Milestone IDs** `SF2-1`–`SF2-12` and the gate `SF2-G`. The design's outline had seven units;
  this plan splits them for session size ([outline mapping](#outline-mapping)).
- **Branches.** One topic branch per milestone, cut from a freshly fetched `origin/main`:
  `sf2/sf2-<n>` (`sf2/sf2-g` for the gate), the name the orchestrator uses from SF2-1 on (the
  plan first said `format-v2/sf2-<n>`). A milestone that changes a spec repository gets a branch
  of the same name there. Worktrees under `.claude/worktrees/<name>`.
- **Checkpoint commit:** `driver-porting: SF2-<n> — <title>`, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01GCyuTJU8apag5WEVZdyEny`. Author email: the
  noreply form the repository's history uses. Stage files by name.
- **Pull requests and merges:** one pull request per milestone per repository. The user
  authorized (2026-10-07) pushing, opening pull requests and merging in driver-lab and the three
  spec repositories without asking each time and without the business-hours wait; so the
  orchestrator pushes the milestone branch, opens the pull request, waits for green CI and merges
  with a merge commit (the spec repositories pin driver-lab commits). Never push `main`.
  Deleting the merged branch, local and remote, is part of merging (`git cherry` first).
  Anything outside those four repositories needs its own go. Enabling GitHub Pages on the three
  spec repositories in SF2-11 is approved (decision 5).
- **Records:** evidence in `evidence/SF2-<n>.md`, one notebook chapter `notebook/SF2-<n>.md`
  with a row in the [notebook index](../notebook/index.md), process-log entries in
  `PROCESS-NOTES.md`. Agent runs (verifiers, Codex) record their transcripts' paths and logs in
  the run ledger under the private run store (`python3 utilities/run-store.py`); evidence cites
  run IDs only.
- **Design gate:** satisfied (approved 2026-10-08). A milestone that needs a design change stops,
  amends the design, and asks the user before continuing.
- **User overrides:** none.
- **Implementers:** one fresh subagent per milestone. Model by unit (user decision 2026-10-08):
  Opus 5.5 for SF2-1 to SF2-7 and SF2-G (loader, checker, records, CommonMark checks, viewer,
  resolver, payload schemas, the gate); Sonnet 5.5 for SF2-8 to SF2-12 (skill text, templates,
  migration, cutover, retirement). The orchestrator holds pushes, merges, Codex runs and user questions.
- **Review method** (naming it here authorizes it; executing sessions do not re-decide):
  - **Code units** (SF2-1–SF2-7, SF2-12): **both** an executing Claude reviewer (a fresh
    subagent that runs the checks, writes break cases including degenerate inputs: empty,
    whitespace-only, separators only, aliases of the thing under test; and mutation checks:
    revert each guard and confirm a test fails) **and** a Codex diff review,
    `python3 utilities/codex-review.py ro <checkout> <brief> <log>`, brief and log under the
    system temp directory. RG-T1 showed each finds bypasses the other misses. Every spec field a
    tool passes to a subprocess is reviewed as untrusted input.
  - **Docs units** (SF2-8, SF2-9): a reviewer subagent that traces every changed rule to the
    design and to the code it describes, plus a Codex `ro` diff review; and a grep of every
    skill for the format 1 rule each change replaces (RG-T1 T7).
  - **Content units** (SF2-10): `spec-verifier` (fresh subagents, a second reader for each
    `critical` fact) on the facts the record does not carry, plus a networked Codex coverage
    review **without** the verifier records, `python3 utilities/codex-review.py net <review dir>
    <brief> <log>`, in a scratch directory outside any checkout.
  - **Cutover and gate** (SF2-11, SF2-G): as named in those milestones.
  - The artifact of every review (reviewer report, Codex log summary, verifier record) is linked
    from the evidence file; review and fixes precede the checkpoint commit.
- **Stop rules** (set now, per the RG1 and RG-T1 lesson; the user may change them):
  - Code units: at most **three** review rounds (a round is both reviewers on the current diff).
    If a round finds a blocker of the same kind, in the same layer, as the previous round
    (a second parser, a second way to spell provenance), stop at once: the orchestrator brings
    it to the user as "patch or redesign", as in RG-T1 round 5.
  - Docs units: at most **two** rounds.
  - Content units: at most **two** verification rounds; the second re-verifies only facts the
    first round's fixes changed. Merge threshold: zero `FAIL`, zero unsettled `ADJUDICATE`
    (the user adjudicates).
  - Reaching a limit: the orchestrator lists the open blockers with options (fix in a follow-up
    milestone, narrow the scope, accept and record as a limitation) and asks; no further round
    starts without the user's decision.
- **Review order:** review and fixes precede the checkpoint commit, which is the last step.
- **Orchestrated mode:** allowed (`orchestrate-milestones`): one fresh subagent per milestone,
  the orchestrator landing each as one pull request per repository.
- **The format 1 tools stay as they are** until SF2-12 (D11): no new features, bug fixes only on
  the user's say-so. The spec repositories keep their current driver-lab pin until SF2-11.

## Status

| ID | Outcome | Dependencies | Status |
|----|---------|--------------|--------|
| SF2-1 | Strict loader, pinned dependencies, core schemas | — | in_progress (review) |
| SF2-2 | Checker: composition, references, license gate | SF2-1 | pending |
| SF2-3 | Verification records and per-fact freshness | SF2-2 | pending |
| SF2-4 | CommonMark checks and the Markdown view | SF2-3 | pending |
| SF2-5 | The viewer and publishing | SF2-4 | pending |
| SF2-6 | Resolve, show and drift | SF2-2 | pending |
| SF2-7 | Peripheral specs, reviews and facts files in format 2 | SF2-4, SF2-6 | pending |
| SF2-8 | The contract and the board-spec skills | SF2-3, SF2-5, SF2-6 | pending |
| SF2-9 | Peripheral, review and investigator skills | SF2-7, SF2-8 | pending |
| SF2-10 | bcm2711 converted and verified on draft branches | SF2-5, SF2-6, SF2-8 | pending |
| SF2-11 | The three spec repositories cut over, published | SF2-10 (Pages approved) | pending |
| SF2-12 | Format 1 retired | SF2-9, SF2-11 | pending |
| SF2-G | Whole-outcome gate | all | pending |

Order: the board-spec path end to end first (SF2-1 → SF2-6, SF2-8, SF2-10, SF2-11), because
it carries the only published content; peripheral and review support (SF2-7, SF2-9) may run in
parallel with SF2-8 and SF2-10 once its dependencies merge. SF2-12 waits for both paths.

### Outline mapping

| Design outline unit | Plan milestones |
|---|---|
| 1 Loader and schema | SF2-1 (core schemas); typed `data` payloads in SF2-7 |
| 2 Checker | SF2-2 (composition, references, gate), SF2-3 (records, D19), SF2-4 (D20–D22) |
| 3 Resolve and drift | SF2-6; `inventory` in SF2-7 |
| 4 Render, viewer and status | SF2-3 (`status`), SF2-4 (Markdown view), SF2-5 (viewer, publishing) |
| 5 Skills | SF2-8 (contract, board-spec skills, `spec-verifier`), SF2-9 (peripheral, review, investigator) |
| 6 Migration of bcm2711 | SF2-10 (convert and verify), SF2-11 (cut over the repositories) |
| 7 Retire format 1 | SF2-12 |

## Design coverage

The design labels three requirements (R1–R3) and 22 decisions; the rest of its contract is in
its sections, mapped here by section.

| Requirement or decision | Milestones | Verification |
|---|---|---|
| R1 One format for every spec kind | SF2-1 (board kinds, overlay, facts), SF2-7 (peripheral, review payloads) | schema fixtures: one valid file per kind |
| R2 Markdown is a rendered view, never parsed for meaning | SF2-4, SF2-5, SF2-11 | renderer and viewer tests; nothing reads the views; published site |
| R3 Facts are records with stable ids; citations are fields | SF2-1, SF2-2 | schema plus checker tests; no prose parsing in the checker (review) |
| D1 Root-qualified references | SF2-2; examples in SF2-8; used in SF2-10 | reference-resolution tests for all three forms; duplicate root names |
| D2 Per-fact basis hashes | SF2-3; used in SF2-10 | canonical-form and staleness tests |
| D3 Inference stands alone; read classes jointly | SF2-1 (schema), SF2-10 (splits) | schema fixtures; seven split facts |
| D4 CommonMark in claims and prose, no raw HTML, separation in the viewer | SF2-4, SF2-5 | text-check fixtures; viewer badge tests |
| D5 Built and published by CI, not committed | SF2-5 (workflow template), SF2-11 (per repository) | artifact on a pull request; Pages site live |
| D6 Strict scalar resolution; hex strings | SF2-1 | loader fixtures |
| D7 `skills/spec-format/` reference skill | SF2-1 (created), SF2-8 (contract, pointer) | skill present; `board-expert/SPEC-FORMAT.md` is a pointer |
| D8 `jsonschema` after `dep-quality` | SF2-1 | `dep-quality` report in the evidence; pin |
| D9 PyYAML; in-place scalar rewrite | SF2-1 (loader), SF2-6 (`drift --rewrite`) | rewrite tests keep comments and the SPDX header |
| D10 Carry verdicts after a fidelity check | SF2-10 | fidelity report; carried and re-verified counts |
| D11 Read-only v1; docs → permissive → gpl in one unit; remove v1 | conventions, SF2-11, SF2-12 | three merges in one session; v1 code gone |
| D12 One license per repos entry; confirmed files list | SF2-1 (schema), SF2-2 (closed list), SF2-6 (SPDX lines at the pin) | resolve tests with a mismatching file |
| D13 Transitive license gate | SF2-2 | gate matrix including references across roots |
| D14 `critical` requires a second reader | SF2-1 (field), SF2-3 (check), SF2-8 (procedure) | record tests |
| D15 `source-observed` with an extension fragment | SF2-1 (fragment mechanism), SF2-2 (rule) | a test fragment; extension adoption is backlog |
| D16 One verdict per register or sequence; sub-keys | SF2-3 (keys), SF2-7 (payloads) | record-key tests |
| D17 `<name>.spec.yaml` for every kind | SF2-1, SF2-2 (discovery) | discovery tests |
| D18 `conflicts` field | SF2-1 (schema), SF2-4/SF2-5 (contested rendering) | schema and render fixtures |
| D19 Upstream-stale: warn on `main`, error on pull requests | SF2-3 (checker modes), SF2-11 (workflows) | tests of both modes; CI on a scratch pull request |
| D20 Raw HTML found by a CommonMark parse | SF2-4 | text-check fixtures |
| D21 Images as links; link schemes | SF2-4 (checker), SF2-5 (viewer) | fixtures with `javascript:` and image links |
| D22 Containment in the checker and the publish step | SF2-4, SF2-5 | fixtures with headings and unclosed fences |
| § The fact record (fields, gap facts) | SF2-1, SF2-2 | schema and checker fixtures |
| § Conflict entries, Assumptions, Instances and variants, Prose, notices | SF2-1, SF2-2, SF2-4 | fixtures |
| § Provenance classes, locators, anchors, inference | SF2-1 (shapes), SF2-2 (names, pages), SF2-6 (anchors at the pin) | per-class fixtures |
| § References (grammar, cycles, layer order) | SF2-2 | tests |
| § Resources (documents, retrieval, commits, https only, roles) | SF2-1, SF2-2, SF2-6 | tests incl. a non-https URL never reaching a subprocess |
| § Roots, layers, overlays, license gate | SF2-2 | the license-gate matrix rewritten |
| § Verification records (file, keys, summary, readers, carried, sources) | SF2-3 | tests |
| § Peripheral specs and reviews (pins, registers, sequences, layouts, findings, facts file) | SF2-7, SF2-9 | fixtures from the widget example |
| § Validation (layers table) | SF2-1–SF2-4, SF2-6 | each row has a test |
| § YAML loader | SF2-1 | one failing fixture per pitfall |
| § Dependencies | SF2-1 | `dep-quality` reports; hash-pinned requirements |
| § Rendering and the viewer | SF2-4, SF2-5 | render and viewer tests; artifact; Pages |
| § Migration (what converts, converting, carrying, what stays) | SF2-10, SF2-11, SF2-12 | evidence counts; archive checks still pass |
| § Effects on skills and spec repositories | SF2-8, SF2-9, SF2-11, SF2-12 | reviewer trace; grep for v1 rules |
| § How the learnings map to this design | per milestone ([Learnings](#learnings-absorbed)) | evidence notes the rows |

**Gaps and items outside the four authorized repositories** (also in the backlog):

- **The `source-observed` extension** (D15) lives in a separate repository (the one the README's
  pointer line names). SF2-1 and SF2-2 build the fragment mechanism and test it with a fixture
  fragment; adopting it there is not planned here.
- **`bringup-kit`** reads the docs and permissive repositories through `board-expert`, and its
  tests write root markers without `format:`. After SF2-11 those repositories are format 2 and
  after SF2-12 `board-expert` reads only format 2. SF2-12 checks `bringup-kit` against the new
  reader; a change there needs the user's go (not covered by the 2026-10-07 authorization).
- **The coverage-review record** and **viewer search** are design non-goals.
- **`campaign-review`** needs no change (design, Effects); nothing planned.

## Checks added by this plan

Each milestone adds its checks to `.github/workflows/checks.yml` and to the AGENTS.md list in
the same commit. Proposed (final names and pins decided in SF2-1; `<pins>` is the hash-pinned
requirements file SF2-1 writes):

```bash
python3 -m venv .venv-sf2 && .venv-sf2/bin/pip install --require-hashes -r skills/spec-format/requirements.txt   # SF2-1
.venv-sf2/bin/python -m unittest discover -s skills/spec-format/tests                                          # SF2-1 onward
.venv-sf2/bin/python skills/spec-format/scripts/spec.py check skills/board-expert/specs --stubs-from skills    # SF2-12, replacing spec_check.py
```

## Learnings absorbed

Rows of the [learnings rollup](../notebook/SPEC-REGEN-learnings.md), in table order, and where
this plan takes them. Rows marked *pre-RG2* are verifier and scaffold procedure, not format; the
rollup already assigns them to a pass before RG2 (see the decision under [Needs a user
decision](#needs-a-user-decision)).

| Rollup row | Milestone |
|---|---|
| verifier: summary table against its figure and chapter | pre-RG2 |
| verifier: coverage pass | pre-RG2; the content-unit review method uses a Codex coverage review |
| verifier: a TODO's method must be able to observe the thing | SF2-1 (`todo.method`), SF2-8 |
| verifier: grade citation precision | SF2-3 (`citation_precision`), SF2-8 |
| verifier: facts plus a trailing TODO | SF2-1 (`todo` is a field), SF2-8 |
| scaffold, investigator: Arm static PDFs; canonical and retrieval URL | SF2-1 (`retrieval`), SF2-8, SF2-9 |
| scaffold: SoC checklist (console, entry contract, memory, interrupts) | pre-RG2 |
| scaffold: `[DT]` takes the tree's license; docs-root template without repos | SF2-2 (DT gated), SF2-8 (templates) |
| investigator: license per cited file | SF2-6 (D12), SF2-9 |
| docs and permissive README/AGENTS citation rules | SF2-11 |
| `SPEC-FORMAT.md`, `spec_check`: `[src]` class, overlay records, CI anchor checks | superseded; SF2-2, SF2-3, SF2-6 |
| review practice: executing reviewer and diff reader | Conventions (review method) |
| review practice: degenerate break cases | Conventions; every code unit |
| review practice: grep every skill for the old rule | SF2-8, SF2-9, SF2-12 |
| review practice: spec fields given to a subprocess are untrusted | SF2-6 |
| review practice: a relaxing flag needs a test that it cannot relax the gated input | SF2-2 (context roots), SF2-3 (`main` mode) |
| verifier: missing locator; derivation inside a `[doc]` bullet | SF2-1 (D3 schema, locators), SF2-8 |
| verifier: who spawns the second verifier; record field | SF2-3 (`readers`, `critical`), SF2-8 |
| `SPEC-FORMAT.md`: `adjudicate` key; document hash in `sources` | SF2-3 |
| verifier: a `[src]` fact about where hardware is needs a document class | SF2-8 |
| tool design: parse once | SF2-1 (one loader), SF2-4 (one CommonMark module) |
| review practice: stop patching, redesign; set the stop rule | Conventions (stop rules) |
| verifier: contrary-evidence step | SF2-3 (field), SF2-8 (procedure) |
| a coverage review is a separate job | content-unit review method; record format out of scope |
| verifier: contrary evidence as a standing step | SF2-8 |
| plan: a unit's stop rule before verification | Conventions (stop rules) |
| spec format: store facts structured | this plan |
| briefs: survey the corpus before claiming compliance | SF2-10 (corpus survey before conversion), every brief |
| briefs: distinct scratch directories for parallel verifiers | SF2-10 |

---

## SF2-1 — Strict loader, pinned dependencies, core schemas

**Outcome:** `skills/spec-format/` exists as a reference skill (D7) with `load_strict` and the
JSON Schemas for the root marker, the verification record, and specs of kinds `board`, `soc`,
`chip`, `ip`, `overlay` and `facts`. Before: no format 2 code. After: `spec.py validate <file>`
(proposed name) loads a file, rejects every YAML pitfall in the design's table with a line and
column, and validates it against the schema for its kind.
**Design coverage:** R1 (board kinds), R3, D3 (schema part), D6, D7, D8, D9 (loader), D12
(schema), D14 (field), D15 (fragment mechanism), D17, D18 (schema); § The fact record, Conflict
entries, Assumptions, Instances and variants, Prose, Provenance classes, Locators, Anchors
(shapes), Inference, Resources (shapes), YAML loader, Dependencies.
**Dependencies:** none.
**In scope:** loader; three schemas; the `support` classes with per-class fields; the
`source-observed` fragment hook; `dep-quality` and pins; the `spec.py` command skeleton
(subcommand dispatch, `--json`, exit codes 0/1/2/3).
**Out of scope:** cross-file checks (SF2-2); typed `data` payloads for peripheral specs and
reviews (SF2-7); records' semantic checks (SF2-3).

### Implementation steps
1. Run `dep-quality` on `jsonschema`, `jschon`, PyYAML and markdown-it-py; record the scores in
   the evidence; pin the chosen versions with hashes in `skills/spec-format/requirements.txt`
   (proposed). If `dep-quality` argues against `jsonschema`, stop and ask (D8 was "subject to the
   score").
2. `skills/spec-format/SKILL.md` (proposed): reference skill, not user-invocable; one paragraph
   pointing at the design until SF2-8 writes the contract.
3. `skills/spec-format/scripts/specload.py` (proposed): `load_strict(path)` per the design's
   loader table (resolver for `true`/`false`/`null`/decimal integers only; anchors, aliases,
   merge keys, explicit tags, several documents, duplicate keys, non-string keys, control and
   invisible characters, non-NFC strings, BOM and non-UTF-8 all errors with line and column).
4. `skills/spec-format/schema/spec.schema.json`, `root.schema.json`, `verify.schema.json`
   (proposed): closed records (`unevaluatedProperties: false`), kind conditionals, per-class
   support entries, locators, anchors, inference premises, fact and reference patterns, `todo`,
   `scope`, `critical`, `relates`, `conflicts`, `assumptions`, `instances`, `variants`,
   `resources` (documents, repos with `role`, `files`, `https` URLs; series; tools), `notices`.
5. `spec.py` skeleton with `validate`; the `source-observed` fragment named in a root marker is
   loaded and composed into the schema (D15), with a test fragment under `tests/fixtures`.
6. Fixtures: one valid file per kind; one invalid file per schema rule and per loader pitfall;
   the design's worked example slices (copied into fixtures) must validate.
7. CI step and AGENTS.md line.

### Acceptance criteria
- [ ] Every row of the design's loader table has a fixture that fails with the expected message
  and line.
- [ ] The design's worked-example YAML (docs, permissive and GPL slices, the record) validates.
- [ ] Each support class rejects a missing required field and an unknown field; `inference` with
  a sibling support entry, `emulated` alone, `press` without `todo` all fail.
- [ ] A `repos` entry with a non-`https` URL fails validation.
- [ ] Exit codes: 0 valid, 1 invalid, 2 usage, 3 a pinned dependency missing (no fallback parser).

### Testing and review
- Tests: `skills/spec-format/tests/test_load.py`, `test_schema.py` (proposed).
- Verify with: the SF2-1 lines under [Checks added by this plan](#checks-added-by-this-plan);
  the full AGENTS.md list still passes.
- Review focus: equivalent spellings the loader or schema still admits (a second way to write
  the same thing is the format 1 failure); closed records really closed under every `if/then`.
- Review method: code unit (conventions).

### Session sizing
Needs the design's sections from "The spec file" to "Inference" and "Validation", plus
`campaign-review/scripts/index_check.py`'s `UniqueLoader`. Uncertainty: `unevaluatedProperties`
with nested conditionals. Split point: the record and root schemas can move to SF2-3 if the spec
schema takes the session.

### Evidence and findings
Status: in_progress; implemented, awaiting review. Evidence: `evidence/SF2-1.md` (written after
review). Notebook: [SF2-1](../notebook/SF2-1.md).

---

## SF2-2 — Checker: composition, references and the license gate

**Outcome:** `spec.py check <root>... [--context-root ...] [--require-license]` checks what a
schema cannot: discovery, composition, overlays, names, references, layer order, the license
gate direct and transitive, privacy and placeholders. The license-gate fixture matrix runs in
format 2 with the same expected results.
**Design coverage:** R3, D1, D12 (closed `files` list), D13, D15 (rule), D17; § References,
Roots/layers/overlays/license gate, Validation rows "check".
**Dependencies:** SF2-1.
**In scope:** root discovery (marker `name` required in format 2, duplicate names an error,
no symbolic links); `*.spec.yaml` discovery; `parts`, `overlays`, `variant_of`,
`instances[].ip`; fact-id uniqueness per spec id per root; `repo`, `doc`, `assumption` names;
document class and page bounds; the three reference forms (`#id`, `spec#id`,
`spec@root#id`), required qualification across roots, cycles, layer order; the gate over `src`,
`DT` and `rtl` anchors and through references, using `board-expert/scripts/spdx.py`;
`--context-root` downgrading only a context root's own findings; public-layer privacy;
template placeholders; stubs (`--stubs-from`).
**Out of scope:** records (SF2-3); text checks (SF2-4); anything needing a checkout (SF2-6).

### Implementation steps
1. `skills/spec-format/scripts/speccheck.py` (proposed), called by `spec.py check`.
2. Rewrite `skills/peripheral-spec/tests/fixtures/license-gate/` board fixtures and roots as
   format 2 under `skills/spec-format/tests/fixtures/license-gate/` (proposed; the v1 fixtures
   stay until SF2-12), with `expected.json` carried over row for row.
3. Rewrite the board-expert `bad_root`, `good_root`, `vendor_root` fixtures in format 2, each bad
   fixture keeping its one defect.
4. Reference fixtures: a GPL-root inference referencing a docs fact (passes), the reverse
   (fails the transitive gate), an unqualified cross-root reference (fails), a same-id fact in
   two roots (passes), a cycle (fails), a reference into a later layer (fails), a renamed root
   (every dangling reference reported).

### Acceptance criteria
- [ ] The license-gate matrix gives the expected exit code for every pair, in format 2.
- [ ] Each reference fixture above gives its expected result with a message naming the fact.
- [ ] A context root that is, contains or sits inside a checked root is a usage error (exit 2);
  a test proves a context root cannot downgrade a checked root's own finding.
- [ ] No code path reads a claim, title or prose string for meaning (reviewer confirms).

### Testing and review
- Tests: `test_check.py` (proposed), the matrix test.
- Review focus: the gate as one function over one structure; degenerate inputs (empty `accepts`,
  empty anchors list, `name: ""`, a reference that is `#`); relaxing flags.
- Review method: code unit.

### Session sizing
Needs the design's References and Roots sections, `spdx.py`, the v1 matrix README. The largest
code unit. Split point: the transitive gate and cross-root reference fixtures (step 4) become
SF2-2b if steps 1–3 take the session.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-2.md`. Notebook: `notebook/SF2-2.md`.

---

## SF2-3 — Verification records and per-fact freshness

**Outcome:** records in `resources/<name>.verify.yaml` are checked: keys are fact ids (or
`id.sub` keys), `summary` has five keys and matches, `critical` facts have a second reader,
carried verdicts are well formed; every verdict is current, stale, upstream-stale or missing by
its basis hash. `spec.py status [--stale]` lists them. The checker's `--require-verified` has a
pull-request mode (stale and upstream-stale are errors) and a `main` mode (upstream-stale
warns) per D19.
**Design coverage:** D2, D14, D16 (keys), D19; § Verification records, Freshness.
**Dependencies:** SF2-2.
**In scope:** canonical form `fact-v1`; basis hash over fact, cited resources' identity
fields, assumptions and referenced facts' hashes (Merkle); record checks; `status`; the two CI
modes (proposed flag: `--require-verified=pr|main`).
**Out of scope:** writing records (the verifier does, SF2-8 procedure); rendering status
(SF2-4).

### Implementation steps
1. `skills/spec-format/scripts/records.py` (proposed): canonical JSON, basis hash, record checks.
2. Fixtures: the board-expert `verify_root` cases in format 2 (current, stale, current FAIL,
   malformed, none), plus: a layout-only edit (no staleness), a bookkeeping-field edit (none), a
   referenced fact edited in another root (upstream-stale), a `critical` fact with one reader.
3. `spec.py status` with `--json`.

### Acceptance criteria
- [ ] Reflowing a folded scalar, reordering keys, moving a fact's section and editing comments
  leave every basis hash unchanged; editing a claim, a locator, a cited commit or a referenced
  fact changes exactly the expected hashes.
- [ ] Upstream-stale is an error under the pull-request mode and a warning under `main` mode; a
  test proves `main` mode does not relax a fact staled by its own file.
- [ ] A key naming no fact, a summary that does not match, and a missing second reader on a
  `critical` fact are errors.

### Testing and review
- Tests: `test_records.py` (proposed).
- Review focus: canonicalization determinism (NFC, integers only, key order); what the hash omits
  by design; that `main` mode is the only relaxation.
- Review method: code unit.

### Session sizing
Needs the design's Verification records section and SF2-2's composition API. Small surface,
exacting tests. Split point: `status` can move to SF2-4 if needed.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-3.md`. Notebook: `notebook/SF2-3.md`.

---

## SF2-4 — CommonMark checks and the Markdown view

**Outcome:** one module (proposed `textcheck.py`) parses claim, title, prose and note fields with
the pinned CommonMark library and reports only raw HTML, disallowed link schemes, headings and
unclosed fences (D20–D22); `spec.py check` fails on them. `spec.py render --format md` builds
the Markdown view (single and merged, with status), escapes generated text, and repeats the
containment check before rendering.
**Design coverage:** R2, D4, D20, D21 (checker side), D22, D18 (contested rendering); §
Rendering and the viewer (Markdown view), Validation (no raw HTML, v1-tag lint).
**Dependencies:** SF2-3 (status in the view).
**In scope:** the text module and its fixtures; the v1-tag lint (warning); the Markdown
renderer with the generated provenance block and banner.
**Out of scope:** the HTML viewer and the publish workflow (SF2-5); peripheral generated
sections (SF2-7).

### Implementation steps
1. `textcheck.py`: CommonMark tokens → findings (HTML block or inline, link and autolink scheme,
   heading, unclosed fence); no other output.
2. Adversarial fixtures: HTML in every CommonMark form; HTML-like text in code spans and fences
   (passes); `<0 0 0>`, `<&gic>` (pass); autolinks (pass) and `javascript:` links (fail); setext
   and ATX headings; a fence "closed" by an over-indented line.
3. `render_md.py` (proposed): banner, identity block, resources tables, context section, one
   block per fact with escaped heading, author claim, generated provenance block and full
   reference; overlay sub-headings; `--with-status`.
4. Render the design's worked example and compare with its "Markdown view" slice.

### Acceptance criteria
- [ ] Every fixture gives the expected finding or none; the module exposes no other result.
- [ ] Generated text containing Markdown syntax (a title with `*`, a path with `_`) renders
  literally.
- [ ] A claim imitating a provenance block renders as author text (documented limit; test pins
  the behavior so it is not mistaken for a guarantee).

### Testing and review
- Tests: `test_textcheck.py`, `test_render_md.py` (proposed).
- Review focus: that the parse decides nothing about provenance; escaping of every generated
  string.
- Review method: code unit.

### Session sizing
Needs the design's Rendering section and the CommonMark library's token API. Split point:
the renderer (steps 3–4) moves to SF2-5 if the text module and its fixtures take the session.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-4.md`. Notebook: `notebook/SF2-4.md`.

---

## SF2-5 — The viewer and publishing

**Outcome:** `spec.py render --format html` builds the static viewer: each fact an `article`
with a `claim` container (author Markdown rendered with HTML disabled, images as links, link
schemes limited) and a `provenance` container of badges drawn from fields. A reusable publish
workflow (template in driver-lab, proposed `skills/spec-format/ci/`) builds both views, uploads
them as an artifact on pull requests, and deploys to Pages on `main` and weekly.
**Design coverage:** R2, D4 (viewer side), D5, D21, D22 (publish-step repeat); § The viewer,
Publishing.
**Dependencies:** SF2-4.
**In scope:** viewer HTML and CSS; the badge table (class, verdict, TODO, critical, origin,
assumes, contested, requirement/assessment, gap); the workflow template; a dry run of the
template against a scratch fixture repository layout (no real deploy).
**Out of scope:** enabling Pages in the spec repositories (SF2-11); search and navigation.

### Implementation steps
1. `render_html.py` (proposed); badge markup and stylesheet; per-field rendering so an unbalanced
   construct ends at its container.
2. Tests: author text cannot produce an element with a badge class or an `id`; `javascript:` and
   `data:` links dropped; images become links; every badge appears from its field.
3. Workflow template: build both views; containment repeat; artifact upload on pull requests;
   Pages deploy on `main` and on schedule; refuses to deploy a site missing a spec's page.

### Acceptance criteria
- [ ] The adversarial claims from SF2-4 render inside their `claim` container with no badge
  class and no raw HTML.
- [ ] The workflow template passes `actionlint` (or the check the repository uses; to be
  discovered) and a local dry run of its build steps.

### Testing and review
- Tests: `test_render_html.py` (proposed).
- Review focus: the guarantee argument in the design (fixed element set, no attributes from
  author text); workflow permissions (read-only except the Pages deploy job).
- Review method: code unit.

### Session sizing
Needs the design's viewer section and SF2-4's renderer. Split point: the workflow template
(step 3) moves to SF2-11 if the viewer takes the session.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-5.md`. Notebook: `notebook/SF2-5.md`.

---

## SF2-6 — Resolve, show and drift

**Outcome:** `spec.py resolve` fetches each cited repos entry at its commit (shallow, blob-less,
`https` only, `--` before positional arguments, size limit) and checks every `src`, `DT` and
`rtl` anchor (path, line range, symbol near the range), each cited file's SPDX line against its
entry's license (D12), and document hashes with `--docs-dir`. `spec.py show` prints each fact
beside its cited lines; `spec.py drift <rev> [--rewrite]` moves a pin, rewriting moved lines in
place and marking changed anchors `stale`.
**Design coverage:** D9 (rewrite), D12; § Anchors (resolution, `search`, `stale`), Resources
(commits, `files`), Validation "resolve" column.
**Dependencies:** SF2-2.
**In scope:** porting `fetch_src_pins.py` behavior; anchor resolution; per-file licenses; hex
values in claims against cited lines (warning); `show`; `drift`.
**Out of scope:** `inventory` (SF2-7).

### Implementation steps
1. `resolve.py` (proposed), reusing `fetch_src_pins.py`'s fetch rules and its self-test idea
   (a good and a bad anchor against a real pinned repository).
2. `drift`: locate scalars by PyYAML node marks and replace spans; keep comments and the SPDX
   header; add `stale: {was: <commit>}`.
3. Fixtures: a fixture repository (local git) for line, symbol, `search` and SPDX checks; a
   `url` beginning with `-` or using `file:`/`ext::` never reaches `git`.

### Acceptance criteria
- [ ] Each anchor fixture resolves or fails as expected; a file whose SPDX line differs from its
  entry fails.
- [ ] `drift --rewrite` leaves comments and the SPDX header byte-identical and the file still
  validates.
- [ ] A definite fetch failure (missing commit, missing repository) fails; only a size or time
  limit skips, and a self-test proves resolution ran.

### Testing and review
- Tests: `test_resolve.py`, `test_drift.py` (proposed); network-free by default, one real-fetch
  self-test gated as in the spec repositories' `RESOLVE_SRC`.
- Review focus: subprocess arguments from spec fields (RG-T1 R1); skip paths (RG-T1 R3).
- Review method: code unit.

### Session sizing
Needs `fetch_src_pins.py`, the anchor-resolution parts of `anchor_check.py` and the design's
anchor section. Split point: `drift` (step 2) becomes SF2-6b.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-6.md`. Notebook: `notebook/SF2-6.md`.

---

## SF2-7 — Peripheral specs, reviews and facts files in format 2

**Outcome:** the schema covers kinds `peripheral` and `review` with typed payloads (`register`
and `fields`, `sequence` with steps and order, `layout`, `finding`, `pair`, `coverage`), the
`requirement` and `assessment` rules, roles `source`/`target`/`impl`/`ref`, and `areas`;
`spec.py inventory` compares register records with headers at the pin; the renderers generate
the provenance notice, canonical-references table, register tables, verify-on-hardware list and
open-questions list; `hardware-investigator`'s `license_gate.py` and its worked example read
`kind: facts` files.
**Design coverage:** R1 (peripheral, review), D16; § Peripheral specs and reviews, The
investigator's facts file.
**Dependencies:** SF2-4, SF2-6.
**In scope:** payload schemas; checker rules (`hw-required` needs a document class;
`comment-explained` needs a `comment` anchor; `bug` needs `settled_by` or `self_evident`);
verdict sub-keys; `inventory`; generated sections in both views; the widget fixtures in format 2;
the investigator's examples and tests.
**Out of scope:** skill text (SF2-9).

### Implementation steps
1. Extend `spec.schema.json` with the payloads and kinds.
2. Checker rules above; sub-key checks in records.
3. `inventory` ported from `inventory_check.py` to read records, not prose.
4. Generated sections in `render_md.py` and `render_html.py`.
5. Convert the peripheral license-gate fixtures (15 specs) and the investigator's examples to
   format 2; carry `expected.json`.

### Acceptance criteria
- [ ] The widget register, sequence and finding examples from the design validate and render.
- [ ] `inventory` reports an omitted register and a value mismatch on fixtures, exactly.
- [ ] The peripheral license-gate matrix and the investigator's worked-example tests pass in
  format 2.

### Testing and review
- Review focus: one citation form per class (no reintroduced aliases); generated lists equal to
  the facts they come from.
- Review method: code unit.

### Session sizing
Several payloads but one pattern. Split point: reviews (`finding`, `pair`, `coverage`) and their
fixtures become SF2-7b.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-7.md`. Notebook: `notebook/SF2-7.md`.

---

## SF2-8 — The contract and the board-spec skills

**Outcome:** `skills/spec-format/SKILL.md` carries the format 2 contract (shapes by reference to
the schemas; classes, references, roots, records, rendering); `board-expert/SPEC-FORMAT.md` is a
pointer; `board-expert` reads format 2 (merged Markdown view with status for the composition,
the YAML for exact fields) and, until SF2-12, still reads format 1 roots; `board-spec-scaffold`
ships YAML templates per kind and writes fact records; `spec-verifier` keys verdicts by fact id,
writes YAML records with basis hashes, `readers`, `contrary_evidence`, `citation_precision`,
`carried_from`, and runs delta verification from `spec.py status --stale`.
**Design coverage:** D7 (contract), D14 (procedure); § Effects (SPEC-FORMAT, board-expert,
scaffold, spec-verifier).
**Dependencies:** SF2-3, SF2-5, SF2-6 (the commands the text names must exist).
**In scope:** the four skills above and their tests where they have them; `GLOSSARY.md`;
learnings rows marked SF2-8.
**Out of scope:** peripheral-spec, reference-driver-review, hardware-investigator (SF2-9);
pre-RG2 procedure rows (user decision: they stay in the pre-RG2 pass).

### Implementation steps
1. Contract document in `skills/spec-format/SKILL.md`; pointer in `SPEC-FORMAT.md`.
2. `board-expert/SKILL.md`: resolve, materialize, report sections in format 2 terms; full fact
   references in answers; record status via `spec.py status`.
3. Scaffold templates (`board`, `soc`, `chip`, `ip`, `overlay`, root marker) as YAML; the docs-root
   variant without `repos`.
4. `spec-verifier/SKILL.md`: the record format 2, delta verification, second readers, the
   contrary-evidence step, citation precision, TODO-method check, the `[src]`-about-hardware rule.
5. Grep every skill for each replaced format 1 rule; fix or list it for SF2-9/SF2-12.

### Acceptance criteria
- [ ] Every command and field the text names exists in `spec.py` or the schema (reviewer runs
  them).
- [ ] The scaffold templates validate after placeholder substitution (test).
- [ ] No skill outside SF2-9's scope still states a format 1 rule as current (grep in evidence).

### Testing and review
- Review method: docs unit.

### Session sizing
Text-heavy, four skills. Split point: `spec-verifier` (step 4) becomes SF2-8b.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-8.md`. Notebook: `notebook/SF2-8.md`.

---

## SF2-9 — Peripheral, review and investigator skills

**Outcome:** `peripheral-spec` (and its subagent and verifier templates), `reference-driver-review`
(and its templates) and `hardware-investigator` describe and produce format 2: records with
payloads, roles instead of pin lines, `requirement` and `assessment`, `spec.py
check/resolve/show/drift/inventory`; the anchor-grammar section is replaced.
**Design coverage:** § Effects (peripheral-spec, reference-driver-review, hardware-investigator).
**Dependencies:** SF2-7, SF2-8.
**In scope:** the three skills and their templates; the investigator's worked example text.
**Out of scope:** removing v1 scripts (SF2-12).

### Implementation steps
1. Rewrite the skills' grammar and procedure sections; keep the placement rule and license
   guidance.
2. Templates rewritten around records.
3. Grep for `Source pin:`, `[src:`, `[impl:`, `[ref:`, `[doc:` rules stated as current.

### Acceptance criteria
- [ ] Each skill's commands run against SF2-7's fixtures as written.
- [ ] No format 1 rule stated as current in the three skills (grep in evidence).

### Testing and review
- Review method: docs unit.

### Session sizing
Three skills, two with templates. Split point: `reference-driver-review` becomes SF2-9b.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-9.md`. Notebook: `notebook/SF2-9.md`.

---

## SF2-10 — bcm2711 converted and verified on draft branches

**Outcome:** the three bcm2711 specs and their records exist in format 2 on branches
`format-v2/sf2-10` of the three spec repositories (not merged): converted by `spec.py migrate`,
citations structured, the three mixed bullets split into seven facts (D3), a fidelity report
deciding which of the 65 verdicts carry (D10, at most 61), and the remaining facts verified to
zero `FAIL`. `spec.py check` with `--require-verified=pr`, `resolve` and `render` pass on all
three against each other's branches.
**Design coverage:** D1 (references in content), D3, D10, D14 (second readers on critical
facts); § Migration (what converts, converting, carrying).
**Dependencies:** SF2-5, SF2-6, SF2-8.
**In scope:** `skills/spec-format/scripts/migrate.py` (proposed; reads format 1 with the
existing `mdtokens.py`, its last use); a corpus survey before conversion (lead-ins, mixed
bullets, uncited premises, angle brackets, headings in bullet text); the citation pass; the
fidelity check; delta verification; `resolve` on every `DT` anchor (a failure is a finding about
the v1 spec, recorded as one).
**Out of scope:** switching the repositories' CI or merging (SF2-11); new facts suggested by
the coverage review (backlog for RG, unless the user decides otherwise).

### Implementation steps
1. Corpus survey; record counts in the evidence before converting.
2. `migrate.py`; mechanical conversion of the three specs.
3. Citation pass (fresh agent, v1 and draft v2, no sources).
4. Splits; fidelity check (fresh agent, opens no source); carried verdicts with `carried_from`.
5. Delta verification (`spec-verifier`, distinct scratch directories per verifier, second reader
   for `critical` facts); Codex coverage review.
6. Fix accepted findings; re-verify changed facts only (stop rule).

### Acceptance criteria
- [ ] Fidelity report covers all 65 v1 bullets; carried count and the list of re-verified facts
  recorded.
- [ ] Every fact current in its record, zero `FAIL`, zero unsettled `ADJUDICATE`, second readers
  on all `critical` facts.
- [ ] `check`, `resolve` and both renders pass for the three draft branches together.

### Testing and review
- Review method: content unit (conventions), plus a code-unit review of `migrate.py` by the
  executing reviewer only (it runs once and is deleted in SF2-12).

### Session sizing
Conversion plus verification of three specs. Split point: after step 4 (conversion and fidelity
done, records carried), with delta verification as SF2-10b.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-10.md`. Notebook: `notebook/SF2-10.md`.

---

## SF2-11 — The three spec repositories cut over and published

**Outcome:** in one session (D11), in the order docs, permissive, gpl, each spec repository
merges a pull request that bumps its driver-lab pin to a commit with format 2, replaces
`specs/*.spec.md` and `*.verify.md` with the SF2-10 files, switches `scripts/checks.sh` to
`spec.py` steps (`check` with `--require-verified=pr` on pull requests and `=main` on `main`,
`resolve`, `render`, `self-test` on the format 2 fixtures), adds the publish workflow, and
updates README and AGENTS.md citation rules. Each repository's Pages site shows its specs.
**Design coverage:** D5, D11, D19 (workflows); § Effects (spec repositories), Migration
(transition).
**Dependencies:** SF2-10. Enabling GitHub Pages on the three public repositories is approved
(decision 5).
**In scope:** the three repositories' changes; a scratch pull request per repository proving
the gate fit/misfit and the D19 modes in published CI (as LS5 and LS-G did).
**Out of scope:** driver-lab's v1 removal (SF2-12).

### Implementation steps
1. Before starting: confirm SF2-10's branches still pass against current `main` of each.
2. docs: pull request, green CI, merge; enable Pages (with the user's go); confirm the site.
3. permissive, then gpl: the same, each reading the previous repository's merged `main` as
   context.
4. Scratch pull requests proving the gate and D19 behavior; close them unmerged.

### Acceptance criteria
- [ ] All three merged in order in one session; each `main` CI green after the last merge.
- [ ] Each Pages site serves the single and merged views; a pull request shows the artifact.
- [ ] Scratch pull requests: misfit fails, fit passes, upstream-stale fails the pull request and
  only warns on `main`.

### Testing and review
- Review method: executing reviewer on each repository's diff and the scratch results, plus Codex
  `ro` per repository. Stop rule: two rounds; a failing repository rolls back its own merge only
  if the next one cannot proceed (the orchestrator asks first).

### Session sizing
Three similar changes plus CI waits. Split point: none by design (D11); if a merge cannot land,
stop with the earlier repositories merged and their `main` warning, and ask.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-11.md`. Notebook: `notebook/SF2-11.md`.

---

## SF2-12 — Format 1 retired

**Outcome:** driver-lab carries no format 1 code: `spec_check.py`, `anchor_check.py`'s
Markdown mode, `inventory_check.py`, `mdtokens.py`, `fetch_src_pins.py` and `migrate.py` are
removed or replaced by `spec.py`; the v1 fixtures go; `board-expert` reads format 2 only; CI and
the AGENTS.md list run the format 2 checks; markdown-it-py stays as the pinned CommonMark library
(D20). The frozen archive's checks still pass.
**Design coverage:** D11; § Migration (what stays), Effects (driver-lab CI).
**Dependencies:** SF2-9, SF2-11.
**In scope:** removals; `board-expert/specs` marker to `format: 2`; tests; CI; a check of
`bringup-kit`'s tests against the new reader (report only; a change there needs the user's go).
**Out of scope:** the frozen archive (unchanged).

### Acceptance criteria
- [ ] No tracked file outside the archive and the history records imports or names a removed
  module as current (grep in evidence).
- [ ] The full AGENTS.md list passes, archive checks included.
- [ ] `bringup-kit`'s result recorded.

### Testing and review
- Review method: code unit.

### Session sizing
Mostly deletions and CI edits. Split point: none expected.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-12.md`. Notebook: `notebook/SF2-12.md`.

---

## SF2-G — Whole-outcome gate

Checks the assembled system against the whole design from fresh clones of driver-lab and the
three spec repositories: every row of [Design coverage](#design-coverage) with its evidence
link; the worked example's claims reproduced on the published bcm2711 (references, a
cross-root inference, a carried verdict, an upstream-stale case made on a scratch branch); the
license-gate matrices for board and peripheral fixtures; the viewer's guarantee on the
adversarial fixtures; the Pages sites; the full AGENTS.md list; no format 1 rule stated as
current in any skill. Review: `review-swarm` over the combined state, focused on
cross-milestone interactions (pins between repositories, the two `--require-verified` modes,
the shared CommonMark module), plus a Codex `ro` review of the combined diff. Stop rule: two
rounds.

### Evidence and findings
Status: pending. Evidence: `evidence/SF2-G.md`. Notebook: `notebook/SF2-G.md`.

## Stop point and what follows

This plan ends at SF2-G. The spec-regeneration series ([plan](SPEC-REGEN-PLAN.md)) is paused
until then and resumes with RG2 (`rpi4`) written in format 2, after the pre-RG2 learnings pass.
No RG unit starts while a format 2 milestone is open.

## Decisions (user, 2026-10-08)

1. **Implementer model:** mixed by unit (Opus 5.5 for SF2-1 to SF2-7 and SF2-G, Sonnet 5.5 for
   SF2-8 to SF2-12; see Conventions).
2. **Pre-RG2 procedure learnings** stay in the separate pass before RG2; SF2-8 does not absorb
   them.
3. **Coverage findings in SF2-10** that would add new facts go to the RG backlog; the migration
   stays a conversion.
4. **Stop rules** as set in the conventions are confirmed.
5. **GitHub Pages** (later the same day): approved for the three spec repositories; SF2-11 may
   enable it.
6. **Models unchanged** (later the same day): Opus 5.5 for SF2-1 to SF2-7, SF2-G and every
   reviewer and verifier; Sonnet 5.5 for SF2-8 to SF2-12.

Orchestrator decisions during SF2-1's review (2026-10-08), within the design's scope:

- **Locator precision for `standard`:** a `databook` locator always carries a section, page,
  pages, table, figure or clause; a `standard` locator does only when its document entry has
  `pages` (a paged document), which SF2-2's checker enforces. The design's Locators paragraph is
  amended to match; its worked example cites an unpaged standard (`booting.rst`) by heading.
- **No empty optional lists:** an optional list is absent or non-empty (`readers: []` and an
  absent `readers` were two spellings). Required lists that may hold nothing (`instances` of a
  soc, `clocks`, `facts`, `sources`, `accepts`) keep `[]`. The design's worked example drops its
  `aliases: []` and `readers: []` lines.

Orchestrator decisions during SF2-1's round-2 review (2026-10-08):

- **`symbol`** cites C++ and assembler names as spelled (`~Foo`, `operator<<`, `Foo<T>`,
  `$label`, `struct gic_chip_data`): single-line, no leading `-`. SF2-6 passes symbols, nodes,
  refs and paths to a command only as separate arguments after `--`, never through a shell.
- **`accepts`** is required in a format 2 root marker; `[]` means documents only.
- **`resources`** is absent or non-empty (`{}` was a second spelling).
- **`fetch_via` and retrieval `via`** are prose, never executed.
- **Exit code 100** is `spec.py`'s internal error, apart from 1 (a file is invalid): the tool-specific
  band of the house exit-code contract. (First set to 4, reversed the same day: 4 is reserved
  there for "target unreachable".)
- **Requirements markers:** only `python_version` and `python_full_version` comparisons, as
  padded three-part versions; anything else is exit 3.

## Needs a user decision (later)

- **`bringup-kit`** follow-up if SF2-12 finds its tests need a change (outside the 2026-10-07
  authorization).

## Discovered work / backlog

- **`source-observed` extension adoption** (D15): the extension's own repository supplies its
  schema fragment and moves to format 2; not in this plan.
- **Coverage-review record format**: design non-goal; RG1 showed the need.
- **Viewer search and navigation**: design non-goal; builds on SF2-5.

## Next session

- Current milestone and status: none started; plan approved by the user on 2026-10-08.
- Resume action: begin SF2-1 (implementer: Opus 5.5).
- Read first: the design, this plan's conventions and SF2-1, the
  [SF2-design](../notebook/SF2-design.md) chapter.
