<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF2-G: whole-outcome gate

**Terms:**

- *format 2*: the YAML spec format that `spec.py` reads and checks.
- *fresh clone*: a new clone of a repository from GitHub, not a local working copy.
- *pin*: the driver-lab commit a spec repository's workflows check out to run `spec.py`.
- *upstream-stale*: a verdict that went stale only because a fact in another repository changed.
  A pull-request check reports it as an error; a check of `main` reports it as a warning.
- *viewer guarantee*: no author text can produce a badge or an element outside its own container
  in the HTML viewer.
- *scratch branch*: a local branch in a scratch clone, never pushed.

See the [glossary](../GLOSSARY.md) for the rest.

Design: [SPEC-FORMAT-V2.md](../docs/SPEC-FORMAT-V2.md). Plan:
[SF2-G](../docs/SPEC-FORMAT-V2-PLAN.md#sf2-g--whole-outcome-gate).
Notebook: [SF2-G](../notebook/SF2-G.md). Run: `sf2-g-20261010-01` in the private run store
(ledger, command outputs, the gate's scratch scripts).

**Status: complete.** The gate ran on fresh clones of
driver-lab and the three spec repositories. Five of the seven items passed as they stood. The
full checks list failed in a deep checkout path (G1, G2). The coverage walk found two validation
checks without a test that can fail (G3, G4). G1 to G4 are fixed here with tests. Review round 1
(`review-swarm` and a Codex `ro` review) found one blocker, a critical fact with no second
reader that publishes when it is upstream-stale; it is fixed, with the other round 1 fixes
below. Round 2, the last the stop rule allows, found no blocker; its should-fix and four stale
passages of documentation are fixed.

## What the gate ran on

Fresh clones of driver-lab at `59df6e1` (origin/main) and of `hardware-specs-docs` at `a587a13`,
`hardware-specs-permissive` at `d7cb00d` and `hardware-specs-gpl` at `6b19f27`, each its `main`
after SF2-11. All six workflow pins in the three repositories name driver-lab `b86af093`, an
ancestor of `59df6e1`, 27 commits behind it.

## Acceptance

| Gate item | Result | Evidence |
| --- | --- | --- |
| 1. Every Design coverage row with its evidence | met after fixes | Table below: every row has an evidence file that shows its verification. The design's validation table has 22 rows. A read-only mapping found a failing test for 21; the 22nd (an instance whose `ip` names no spec) had none (G3, fixed). The Resources row's "non-https URL" case was not in the test (G4, fixed). |
| 2. Worked example on the published bcm2711 | met | See [Worked example](#worked-example-on-the-published-bcm2711) |
| 3. License-gate matrices, board and peripheral fixtures | met | 204 runs of `spec.py check` through the CLI, 0 mismatches. They cover the 15-row peripheral matrix under each of the three fixture markers and each of the three **published** markers, with and without `--require-license`, plus the four board fixtures against all six markers |
| 4. Viewer guarantee on the adversarial fixtures | met | All 61 adversarial text cases, plus 7 forging cases written for the gate, were injected into a claim, a TODO and a verification note of the worked-example fixture: 204 runs through the CLI. Each run either failed `check` and `render` together, with no partial view (102), or rendered (102). Every rendered run kept the badge multiset of a benign render, had balanced HTML, no `img` or `script`, no attribute but `href` inside author containers, and no link outside `https:`, `http:`, `mailto:` and `#`. The published gpl merged viewer passes the same structural checks (0 violations) |
| 5. Pages sites | met | Fetched every file of the three sites (docs 8, permissive 6, gpl 14). Each is byte-identical to a local `publish.py build` from the clones' `main` with the pinned tool |
| 6. Full `AGENTS.md` checks list on the fresh clone | met after fixes | At `59df6e1`, in a scratch path under the system temp directory: 11 of 13. `spec-format` had 9 failures (G1) and `utilities` 1 (G2), both caused by where the checkout lies. After round 1, the whole list ran again on a fresh clone of `sf2/sf2-g` in the same kind of path (round 1 code; only these records changed afterwards): 13 of 13 (utilities 68 tests, `spec-format` 628 with 1 skipped, the archive checks included) |
| 7. No format 1 rule stated as current in any skill | met | A grep over `skills/` (tests excluded) for format 1 file names, tags, retired tools and `format 1` found 10 lines. All 10 are D10 carry procedure, negative rules ("never … leave format 1 records in a format 2 root"), the carried-verdict schema comment, or the checker's code that rejects format 1 input |

## Design coverage, row by row

"Shows it" means the evidence file records the verification the plan names for that row.

| Row | Evidence | Gate result |
| --- | --- | --- |
| R1 one format for every kind | [SF2-1](SF2-1.md) (board kinds, overlay, facts), [SF2-7a](SF2-7a.md) (peripheral), [SF2-7b](SF2-7b.md) (review) | shows it |
| R2 Markdown is a view, never parsed | [SF2-4](SF2-4.md), [SF2-5](SF2-5.md), [SF2-11](SF2-11.md) | shows it; item 5 confirms the published site |
| R3 facts are records; citations are fields | [SF2-1](SF2-1.md), [SF2-2](SF2-2.md) ("no prose parsing") | shows it |
| D1 root-qualified references | [SF2-2](SF2-2.md), [SF2-10](SF2-10.md) | shows it; SF2-8's evidence does not name the examples, but `spec-format/SKILL.md`, the scaffold's overlay templates and `board-expert/SKILL.md` carry all three forms; item 2 resolves one on the published specs |
| D2 per-fact basis hashes | [SF2-3](SF2-3.md) | shows it; item 2 (layout-only edit stales nothing; a premise edit stales exactly one fact) |
| D3 inference stands alone | [SF2-1](SF2-1.md), [SF2-10](SF2-10.md) (seven split facts) | shows it |
| D4 CommonMark, no raw HTML, viewer separation | [SF2-4](SF2-4.md), [SF2-5](SF2-5.md) | shows it; item 4 |
| D5 built and published by CI | [SF2-5](SF2-5.md), [SF2-11](SF2-11.md) (artifact on a pull request; Pages live) | shows it; item 5 |
| D6 strict scalars, hex strings | [SF2-1](SF2-1.md) | shows it |
| D7 `spec-format` reference skill | [SF2-1](SF2-1.md), [SF2-8](SF2-8.md) | shows it; `board-expert/SPEC-FORMAT.md` is a pointer at `59df6e1` |
| D8 `jsonschema` after `dep-quality` | [SF2-1](SF2-1.md) | shows it |
| D9 PyYAML; in-place rewrite | [SF2-1](SF2-1.md), [SF2-6](SF2-6.md) | shows it |
| D10 carry after a fidelity check | [SF2-10](SF2-10.md) (50 of 65 carried) | shows it; item 2 reads `gic-node` and `reserved-stub-page` as current and carried |
| D11 read-only v1; one-session cutover; v1 removed | [SF2-11](SF2-11.md), [SF2-12](SF2-12.md) | shows it |
| D12 one license per repos entry | [SF2-1](SF2-1.md), [SF2-2](SF2-2.md), [SF2-6](SF2-6.md) | shows it; `test_resolve.py` has the mismatching-SPDX-line test |
| D13 transitive license gate | [SF2-2](SF2-2.md) | shows it; items 2 (reverse reference) and 3 |
| D14 `critical` needs a second reader | [SF2-1](SF2-1.md), [SF2-3](SF2-3.md), [SF2-8](SF2-8.md), [SF2-10](SF2-10.md) | shows it |
| D15 `source-observed` fragment | [SF2-1](SF2-1.md), [SF2-2](SF2-2.md) | shows the fragment mechanism; adoption is backlog |
| D16 one verdict per register or sequence | [SF2-3](SF2-3.md), [SF2-7a](SF2-7a.md) | shows it |
| D17 `<name>.spec.yaml` | [SF2-1](SF2-1.md), [SF2-2](SF2-2.md) | shows it |
| D18 `conflicts` | [SF2-1](SF2-1.md), [SF2-4](SF2-4.md), [SF2-5](SF2-5.md) (Contested badge) | shows it |
| D19 upstream-stale modes | [SF2-3](SF2-3.md), [SF2-11](SF2-11.md) (scratch pull request) | shows it; item 2 reproduces both modes locally |
| D20 raw HTML by a CommonMark parse | [SF2-4](SF2-4.md) | shows it |
| D21 images as links; link schemes | [SF2-4](SF2-4.md), [SF2-5](SF2-5.md) | shows it; item 4 |
| D22 containment | [SF2-4](SF2-4.md), [SF2-5](SF2-5.md) | shows it; item 4 |
| § The fact record | [SF2-1](SF2-1.md), [SF2-2](SF2-2.md) | shows it |
| § Conflicts, Assumptions, Instances, Prose, notices | [SF2-1](SF2-1.md), [SF2-2](SF2-2.md), [SF2-4](SF2-4.md) | shows it, except a dangling `instances[].ip` (G3, fixed) |
| § Provenance classes, locators, anchors, inference | [SF2-1](SF2-1.md), [SF2-2](SF2-2.md), [SF2-6](SF2-6.md) | shows it |
| § References | [SF2-2](SF2-2.md) | shows it |
| § Resources | [SF2-1](SF2-1.md), [SF2-2](SF2-2.md), [SF2-6](SF2-6.md) | shows it after G4: the bad-URL test now includes a plain `http://` URL; `show`, `drift` and `inventory` reach Git only through the same `resolve.fetch` guard |
| § Roots, layers, overlays, license gate | [SF2-2](SF2-2.md) | shows it; item 3 |
| § Verification records | [SF2-3](SF2-3.md) | shows it |
| § Peripheral specs and reviews | [SF2-7a](SF2-7a.md), [SF2-7b](SF2-7b.md), [SF2-9](SF2-9.md) | shows it |
| § Validation (each row has a test) | no single evidence file; built here | met after G3: 22 of 22 rows have a test that fails when the check is removed. Two are weaker: the render row is shown by tests that re-check a bypassed checker, and inventory by its header tests |
| § YAML loader | [SF2-1](SF2-1.md) | shows it |
| § Dependencies | [SF2-1](SF2-1.md) | shows it |
| § Rendering and the viewer | [SF2-4](SF2-4.md), [SF2-5](SF2-5.md) | shows it; items 4 and 5 |
| § Migration | [SF2-10](SF2-10.md), [SF2-11](SF2-11.md), [SF2-12](SF2-12.md) | shows it; archive checks pass in item 6 |
| § Effects on skills and spec repositories | [SF2-8](SF2-8.md), [SF2-9](SF2-9.md), [SF2-11](SF2-11.md), [SF2-12](SF2-12.md) | shows it; item 7 |
| § Learnings | each evidence file's notes | not re-traced row by row; the plan maps every rollup row to a milestone |

## Worked example on the published bcm2711

Run against the published `main` of each repository, with the current tool:

- **References and a cross-root inference.** The gpl fact `tree-describes-low-peripheral-mode`
  rests on `#address-translation-in-the-tree` and on
  `bcm2711@hardware-specs-docs#addressing-model`, and its record holds that fact's basis in
  `upstream`. `spec.py status` over the three roots: 60 current, 0 stale, 0 upstream-stale.
- **Carried verdicts.** `gic-node` and `reserved-stub-page` are current and marked carried, with
  `carried_from` naming the gpl repository's format 1 record. The published files differ from the
  design's slice in two ways that SF2-10 decided: `gic-node` is not `critical`, and the split
  facts were verified in SF2-10, with second readers.
- **Upstream-stale.** A scratch branch of the docs clone added one word to `addressing-model`'s
  claim. The gpl check in pull-request mode failed with exactly one error:
  `upstream-stale: bcm2711@hardware-specs-docs#addressing-model changed since the verdict of
  2026-10-09`. In `main` mode it passed, with the same line as a warning. Nothing else in gpl or
  permissive went stale, and docs' own check called `addressing-model` stale.
- **Layout does not count.** A second scratch branch reordered that fact's keys and added a
  comment: docs and gpl both check clean in pull-request mode.
- **The reverse reference fails the gate.** A third scratch branch gave docs an inference
  resting on `bcm2711@hardware-specs-gpl#gic-node`: `GPL-2.0-only is not accepted by root
  hardware-specs-docs (accepts: none: documents only) (license gate, D13)`.

The three spec repositories' own `scripts/checks.sh all` (`RESOLVE_SRC=1`) passed in both
modes, against the pin and against driver-lab `59df6e1`: 12 runs, all exit 0 (gpl resolved 141
anchors).

## Findings and resolutions

- **G1, a deep checkout failed nine `spec-format` tests.** An untrusted-root message quoted the
  root's first error cut at 200 characters, path included. In a deep checkout the path used up
  the 200 characters, so the reason the tests look for was cut off. This was the SF2-2 backlog nit
  ("the full path takes most of them") showing up as test failures. Resolution: the checker
  keeps each error's location and message apart and cuts only the message.
  `test_reason_survives_a_deep_checkout` copies the fixtures below a path longer than 200
  characters. It fails with the fix reverted and passes with it.
- **G2, a `codex-review` refusal test assumes the checkout is outside the system temp
  directory.** The case "ro brief outside temp" passes `README.md` of the checkout as the brief,
  so in a checkout under the temp directory the script accepts it (correctly) and the test fails.
  Resolution (round 1): the case takes the first existing file outside the temp directory
  (the checkout's `README.md`, the standard library, the interpreter, `/etc/hosts`), and skips
  only if there is none.
- **G3, an instance whose `ip` names no spec had no test.** The checker's branch existed, but
  only the wrong-kind branch was tested. Resolution: the fixture `instance-dangling.spec.yaml` in
  `fixtures/check/bad_root` and its expected error. Removing the branch fails the test.
- **G4, the "non-https URL" of the Resources row was not among the bad URLs tested.** The test
  had `file:`, `ext::`, uppercase `HTTPS` and malformed URLs, but no plain `http://`. Resolution:
  the case is added. It is refused before Git, in the same `resolve.fetch` guard `show`, `drift`
  and `inventory` use.
- **G5, the spec repositories pin a driver-lab commit from before SF2-7a.** `b86af093` predates
  peripheral and review support, SF2-9 and SF2-12. The repositories pass with both the pin and
  the current tool. The current tool's viewer adds verifier and second-reader lines that the
  published sites lack. Outside driver-lab. Proposed: bump the pin in all three repositories
  (both workflows each), docs, then permissive, then gpl, as one pull request per repository.
- **G6, fixture markers accept two licenses the published markers do not.** The permissive and
  gpl markers of the license-gate fixtures and of the worked-example fixtures add `X11` and
  `Zlib`; no fixture spec cites either, so the matrix gives the same 204 results under both
  marker sets. LS-G F1 had documented this, and the caveat was lost in SF2-9; round 1 restored
  it in the license-gate fixtures' README. Proposed: align both fixture sets with the published
  markers in a follow-up, or record that they are a superset on purpose.

## Limitations

- The `main`-mode upstream-stale result was reproduced with the CLI on a local branch, not by a
  workflow; SF2-11's scratch pull request is the published-CI proof.
- The viewer runs inject into three author fields of one fixture. The existing unit tests cover
  the other fields; the gate did not repeat them field by field.
- The learnings rollup was not re-traced row by row.
- The fresh-clone checks ran under the system temp directory, which is how G1 and G2 surfaced;
  CI's shorter path hides both.

## Reviews

| Round | Reviewer | Outcome |
| --- | --- | --- |
| 1 | Codex `ro`, combined diff | one blocker (B1), one should-fix (S1) |
| 1 | `review-swarm`, two parts (code; tests and records), seven arms each, referee | 13 findings after the referee (part A 9, part B 4); the referee dropped 3 |
| 2 | Codex `ro`, round 1 fixes | no blocker; one should-fix (S1), one note |
| 2 | `review-swarm`, round 1 fixes, seven arms, referee | no blocker; 4 documentation findings (F2–F5); the referee dropped 1 (F1) |

Review artifacts: `review/codex1/`, `review/swarm/`, `review/codex2/` and `review/swarm2/` in
run `sf2-g-20261010-01`.

Round 1 findings and decisions:

| Finding | Decision | Reason |
| --- | --- | --- |
| Codex B1: an upstream-stale `critical` fact without a second reader passes `main` mode and publishes | fixed: the reader rule applies to current and upstream-stale verdicts; a check-and-publish test in both modes | `main` relaxes staleness only; it must not carry a missing reader through |
| Codex S1: item 6 overstated the fresh-clone result | fixed: G2 fixed, the whole list rerun on a fresh clone of the branch, item 6 restated | the acceptance claim must name the run that supports it |
| A-F8: a current ADJUDICATE is a warning in every mode | user decision (2026-10-10): an error under `--require-verified pr`, a warning under `main`; implemented with tests of both modes; `spec-verifier` and the design say so | the same shape as upstream staleness: nothing unsettled lands through a pull request, and `main` never turns red on its own |
| A-F1: `patch-gate.py` did not treat the Codex wrappers as gate inputs | fixed: `codex-implement.py` and `codex-review.py` are gate inputs (docstring, `AGENTS.md`), with a test | a patch could widen Codex's own sandbox unflagged |
| B-F1: no test reaches publish's clean-context guard | fixed: a test with a context root holding its own error | the guard was the only stop and nothing tested it |
| A-F6, A-F5: `board-expert` and `board-spec-scaffold` said HTML rendering arrives in SF2-5 | fixed: both say it is on main | the text contradicted the code |
| A-F3: `publish.py` let the renderers' `UsageError` and `PreconditionError` escape as tracebacks | fixed: caught and reported in one line, with a test | the documented failure is a message and exit 1 |
| B-F2: a `mutate_sf2_5.py` target no longer existed | fixed: retargeted to `has_support`. The rerun then showed the second-reader badge mutation surviving, because another section prints the same words; the test now asserts the badge itself. Rerun: 65 of 65 killed by assertion | the script stopped at that entry, so later mutations never ran |
| B-F3, B-F4: G6 understated; the LS-G caveat was lost | fixed: G6 names the worked-example markers; the fixture README carries the caveat again | records match the fixtures |
| A-F4: pin lag can stop downstream publishing when an upstream repository lands a new form first | orchestrator: deferred to the G5 follow-up the user approved today (all three pins bumped back to back right after SF2-G merges, no spec content in between) | the bump order removes the window |
| A-F2: duplicate pages when a base and its overlay share a root | orchestrator: backlog | latent; no repository has that layout |
| A-F10: `escape()` instead of a fence in "Verify on hardware" | orchestrator: backlog | the text stays inert; fidelity only |
| A-F11: `node_range` rescans per node | orchestrator: backlog | performance; under a second today |
| Referee drops (A-F7, A-F9, B-F5) | orchestrator: stay dropped | the referee's reasons stand |

Round 2 findings and decisions:

| Finding | Decision | Reason |
| --- | --- | --- |
| Codex2 S1: the G2 test's brief could be refused by `codex-review.py`'s path-syntax check before the temp boundary, so it passed with the boundary removed | fixed: the brief must be safely spelled, and a new test asserts the boundary's own diagnostic; removing the boundary fails it, in a home checkout and in a temp-directory clone | a refusal test must fail when the guard it names is removed |
| Codex2 note 2, swarm2 F2: `spec-verifier` said `main` differs from `pr` only in upstream-stale | fixed: ADJUDICATE joins the `pr` error list and the `main` warnings | the text must match `records.py` |
| swarm2 F3, F4, F5: `spec-format/SKILL.md`, `spec.py check --help` and the `second_pass` docstring described the old reader and mode rules | fixed, with `speccheck.py`'s module docstring, which said the same | the same |
| swarm2 referee drop F1 | orchestrator: stays dropped | such a fact already failed `main` on the reader rule before round 1 |

None of the three published roots holds an ADJUDICATE verdict (all seven records count
`adjudicate: 0`), so the new rule fails no published pull request; their checks with the
round 1 tool pass in both modes.
