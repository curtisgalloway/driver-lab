<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF2-7b: reviews and the HTML generated sections

**Terms:**

- *payload*: a fact's structured finding, correspondence pair or coverage record.
- *pair*: a correspondence fact's implementation and reference source anchors.
- *mutation*: a deliberate break in the code under test, used to show a test can fail.
- *stop rule*: the rule that a repeated blocker kind in confirmation stops the fix loop for a
  decision.

See the [glossary](../GLOSSARY.md) for the rest.

Design: [SPEC-FORMAT-V2.md](../docs/SPEC-FORMAT-V2.md) (R1, D16; Peripheral specs and reviews).
Plan: [SF2-7](../docs/SPEC-FORMAT-V2-PLAN.md#sf2-7--peripheral-specs-reviews-and-facts-files-in-format-2).
Notebook: [SF2-7b](../notebook/SF2-7b.md). Earlier part: [SF2-7a](SF2-7a.md). Run:
`sf2-7b-20261009-01` in the private run store (ledger, briefs, two Codex reviews, the
executing Opus review).

**Status: complete.** With SF2-7a this completes SF2-7.

## What was done

- **Implementation (Codex), from the SF2-7a merge:** the `finding`, `pair` and `coverage`
  payloads and the review kind; review judgments in `data.finding.assessment`, distinct from a
  verifier's verdict; checker rules (a missing finding needs implementation search evidence;
  pairs check each repository's implementation or reference role; settlement documents and pair
  anchors use the ordinary citation, license and freshness traversal); and the provenance
  notice, tables and lists in the HTML view, from the same field projections as the Markdown
  view. Generated elements are fixed and values escaped, so author text cannot add an attribute
  or a badge. 640 tests, 102 new mutations.
- **Round 1** had two reviewers, neither finding a blocker or an escape (see Reviews).
- **Orchestrator decision**, under the user's overnight instruction: a correspondence fact's
  pair anchors count as its support. No forced todo or Gap badge for a fact whose evidence is
  its pair.
- **Fix** (645 tests; 133 SF2-7a and 131 SF2-7b mutations, all killed by assertions): child
  (sub-key) verification metadata in HTML, the target kind's payload restrictions on review
  overlays, a "Settled by" label, the pair decision, and pinned guards for the untested items.
- **Confirmation of the fix** confirmed all five items and found one regression: the pair
  exemption leaked into instance and variant rows (`data: {pair: {}}` or null passed). The
  orchestrator fixed it directly, scoped to correspondence facts; the test fails before the fix
  and passes after (646 tests).

## Acceptance criteria

The plan's SF2-7 criteria, now complete.

| Criterion | Evidence | Met |
| --- | --- | --- |
| The widget register, sequence and finding examples validate and render | Register and sequence in both views: [SF2-7a](SF2-7a.md) (Markdown) and this unit (HTML). Finding example: validates and renders in both views, with the design's wording and citations (its implementation side is illustrative) | yes |
| `inventory` reports an omitted register and a value mismatch on fixtures, exactly | [SF2-7a](SF2-7a.md) | yes |
| The peripheral license-gate matrix and the investigator's worked-example tests pass in format 2 | [SF2-7a](SF2-7a.md) | yes |
| Review focus: generated lists equal the facts they come from | Independent computation from the YAML against both views, overlays included: 3,088 of 3,088 documents equal | yes, both views |

## Reviews

| Reviewer | Outcome |
| --- | --- |
| Codex, round 1 (`codex1`) | no blocker; 96 HTML probes clean; should-fix: HTML hid child metadata, review overlays bypassed payload restrictions |
| Opus, executing review (`claude1`) | no blocker; 12,000 fuzz cases gave 12,518 HTML and 12,518 Markdown documents with 0 violations; generated lists equal their facts in 3,088 of 3,088 cases; should-fix: 10 untested guards, the pair decision, the unlabeled settlement |
| Codex, confirmation (`codex2`) | all five items confirmed; one regression (pair exemption leaking into instance and variant rows), fixed directly |

## Consequential findings

- **Pair-only correspondence facts were gaps.** A fact backed only by its pair needed a todo and
  showed a Gap badge although pair anchors already counted for citation, license and freshness.
  Resolution: orchestrator decision that pair anchors are support; schema, verdict checks and
  both views agree.
- **The pair exemption was too wide.** The first fix let instance and variant rows pass with an
  empty or null pair. Resolution: scoped to correspondence facts, with a regression test.
- **Ten guards no test pinned** (missing-search side, per-fact HTML tables, the side label,
  the agreements section, the overlay section enum, settlement schema, review `id`, `notes` and
  `cache`). Resolution: assertion tests and mutations for each.
- **Settlement was unlabeled**, so a reader could not tell the settling document from the
  fact's own citations. Resolution: a fixed "Settled by" label in both views.
- **Mutation qualification found test bugs again** (records indexed before asserting they exist,
  scratch copies missing the legacy parser). Resolution: assertions moved first, runners fixed.

## Verification

At the final state: 646 spec-format tests. The mutation runs at the fix commit killed 133 of
133 SF2-7a and 131 of 131 SF2-7b mutations by assertion. The full AGENTS.md checks list at
close-out is recorded below.

Close-out, in the SF2-7b worktree reusing `.venv-sf2`: every command in the list exited 0
(`check-no-private-paths.py` OK on 621 tracked files; `check-open-side.py` OK on 620; utilities
(67 tests), board-expert (136, 1 skipped), peripheral-spec (134), hardware-investigator (19, in
the format 2 venv), spec-format (including the compiler differential: 389 values, 319 equal, 70
unknown, none wrong), enc28j60, e1000 (70) and campaign-review (123) suites OK; `spec_check.py`
OK; author manifest matches; campaign index OK, 28 claims).

## Limitations and follow-ups

- **Nits not fixed** (reported by the executing review): a `missing` finding's implementation
  side may mix line anchors with its search; booleans render as `True`/`False`; settlement and
  pair cells render as raw JSON; the per-fact Finding table shows `settled_by` in HTML but not
  Markdown; the Area table's `note` column differs between views; `$defs/assessment` is unused
  and a fact-level `assessment` loop in the HTML renderer is dead code.
- **Fuzzing covers the generated sections and per-fact payload tables**, not skill text
  (SF2-9).
- **Not run here:** CI on the GitHub runner (the pull request runs it).
