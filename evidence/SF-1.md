<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF-1: the `[emulated]` evidence class in the format, the evidence model and the checker

## Terms

- **`[emulated]`** — the evidence class for a result observed on a device model (QEMU or
  another emulator) rather than on silicon; proposed in the [QEMU differential
  design](../QEMU-DIFFERENTIAL.md), used in spec revision 6 ([L02f3](L02f3.md)), adopted here.
- **Evidence model** — the design's table of what each provenance class is trusted for, what
  that trust assumes and how it fails ([DESIGN.md](../DESIGN.md#evidence-model-what-we-trust-and-why)).
- **Format** — `skills/board-expert/SPEC-FORMAT.md`, the contract for board specs and the
  statement of the tag rules; **checker** — `skills/board-expert/scripts/spec_check.py`, which
  enforces the mechanical part of those rules; **tag clause** — the tail of a fact bullet, the
  only part the checker examines for tags.
- **Consumers** — the skills that read or write tagged facts: `board-spec-scaffold` (author),
  `spec-verifier` (verifier), `board-expert` (reader).

See the [glossary](../GLOSSARY.md), the [plan](../IMPLEMENTATION-PLAN.md) (follow-ons named
in L02f3) and the [notebook chapter](../notebook/SF-1.md).

## Status

**Complete, 2026-09-25.** `[emulated]` is a defined provenance class: in the format's tag
table and tag rules, in the design's evidence model, in the checker with three rules and
tests, and in the consumer skills' text. The three usage rules L02f3 learned are stated
where the tags are defined: the tag cites the model version and the run IDs the way
`[hardware]` cites the board; an entry states what was observed from outside the model,
never its mechanism; and a model result is never the sole authority for a fact. The shipped
board specs and stubs check clean under both parsers, as before.

## What changed

| File | Change |
| --- | --- |
| `skills/board-expert/SPEC-FORMAT.md` | Terms: `[emulated]` in the class list, with its citation form (model, version and run IDs, or a pointer to a numbered observation in the same spec that carries them, revision 6's shape), the phrasing rule, the never-alone rule and the TODO; Tag rules: `[emulated]` needs the TODO and a parenthetical and is never the only tag; Clean-room rules: allowed under the same conditions, mechanism stays on the encumbered side; "What the checker enforces": the three rules, and the existing `[rtl]` and `[inference]` rules, which the list had omitted |
| `DESIGN.md` | "Make the kind of evidence visible": the class named with its origin and adoption date; the evidence-model table: a row for `[emulated]` (trusted for, assumes, failure modes, from the QEMU design's proposed row plus the never-alone rule); a third rule under the table (citation and phrasing: a model observation is a citation, not a mechanism); the test-feedback loop: a model result becomes an `[emulated]` fact that narrows or confirms a claim without closing it |
| `QEMU-DIFFERENTIAL.md` | "(proposed)" removed from the term and the section; the section now records the adoption and points at the evidence model and the format |
| `GLOSSARY.md`, `EVAL-PLAN.md` | The class is adopted, not proposed; the provenance-tag term lists it |
| `skills/board-expert/scripts/spec_check.py` | `TAG_NAMES` gains `emulated`; `NAMED_TAGS` gains it (parenthetical required); a new `TODO_TAGS` tuple replaces the inline list and gains it; a new never-alone rule; docstring updated |
| `skills/board-expert/tests/test_spec_check.py` and fixtures | Six tag-rule unit tests; the good fixture gains two correct uses (beside `[databook]`; as an `[inference]` premise); the bad fixture gains one bullet per failure (alone, no TODO, no parenthetical), each producing one finding in the checker's output; the every-failure-class test asserts each message appears, and the alone case's unit test asserts it is the only finding |
| `skills/spec-verifier/SKILL.md` | Board specs: an `[emulated]` claim is compared against what its cited runs recorded, never the model's source; clean-room driver specs: the same, with the three ways it fails |
| `skills/board-spec-scaffold/SKILL.md` | The tag-clause step names the TODO-carrying classes and the never-alone rule |
| `PROCESS-NOTES.md`, `IMPLEMENTATION-PLAN.md`, `notebook/` | The 18:50 process entry closed; a follow-on list with SF-1 complete and the order of the rest; "Next session" points at AF-1; chapter and index row |

Not changed: `os-investigator` and `cleanroom-spec`, whose tag lists are the investigation
classes (facts read from sources); `[emulated]` comes from test runs, which the design's
feedback loop, not the investigator, produces. The e1000 spec (revision 6) already carries
the class in its own §1 table; its inline citations point at §12.5 without parentheses
(`[emulated]` §12.5 EM2), a shape that predates the rule (see Limitations).

## The checker rules

Three rules, in the checker's existing style (the tail clause only; a tag name in the prose
is not a tag):

1. `[emulated]` without a following parenthetical: error, "must be followed by a
   parenthetical naming the device model, its version and the run IDs". The same mechanism
   as `[doc]`, `[DT]`, `[rtl]` and `[inference]`.
2. `[emulated]` in a tail without `TODO (verify on hardware)`: error, as for
   `[source-observed]`, `[press]` and `[inference]`.
3. A tail whose tag set is exactly `{emulated}`: error, "never the sole authority for a
   fact: cite another class beside it, or make the observation a premise of an
   `[inference]`". A set test on the tags the checker already extracts, so an `[emulated]`
   inside an `[inference]`'s parenthetical passes (the inference carries the tag) and one
   beside a `[databook]` passes.

What the checker does not judge, and the verifier does: whether the parenthetical really
names a model version and run IDs, and whether the entry states an observation rather than
the model's mechanism. The checker tests presence, as it does for `[doc]`'s page name.

## Checks

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s skills/board-expert/tests` | 42 tests OK (36 before); the fixture cases run under PyYAML and the subset parser, the six new tag-rule cases exercise `check_tags` and `UNNAMED_RES` directly |
| `spec_check.py skills/board-expert/specs --stubs-from skills` | OK, 11 specs, 9 warnings, unchanged from before the change, under both `parser: pyyaml` and `parser: subset` |
| `spec_check.py --no-pyyaml` on the bad fixture | exactly one `[emulated]` finding per planted bullet (alone; no TODO; no parenthetical) |
| `utilities/check-no-private-paths.py` | OK, 214 tracked files (212 before the two new records) |
| `git diff --check`; privacy grep of the diff | clean; no hits |

## Review

One fresh-context independent reviewer (same model family as the implementer) read the diff
of the pre-review commit against `origin/main`, the L02f3 records that state the rules, and
this file, and ran the board-expert tests, the spec check under both parsers and the privacy
check (report in the run store, `sf1-20260925-01/review/`). It also proved the new tests can
fail: on scratch copies of the checker with the never-alone block removed, with `emulated`
dropped from `TODO_TAGS`, and with it dropped from `NAMED_TAGS`, the corresponding unit test
and the every-failure-class test failed each time. Fourteen findings, one medium:

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| F1 | medium | The format required a parenthetical naming the model, version and runs, but revision 6, the use the class was adopted from, cites its observations as a bare pointer (`[emulated]` §12.5 EM2) to a table that carries them; L02f3 names that pointer as the first shape that held up | The format now accepts either form inside the parenthetical: the model, version and runs, or a numbered observation in the same spec that carries them (`[emulated]` (§12.5 EM2)). The checker still requires the parenthetical. Revision 6's bare pointer predates the rule; recorded under Limitations for the next spec revision |
| F2 | low | The review paragraph was written before the review ran | Rewritten from the report |
| F3 | low | "Each producing exactly one finding, asserted in the every-failure-class test": that test asserts each message appears, not a count | Reworded; the alone case's unit test is the one that asserts a single finding |
| F4 | low | "Every case runs under PyYAML and the subset parser" is the fixture cases only; the six new tag-rule cases call `check_tags` directly | Reworded |
| F5 | low | The privacy check counts 214 tracked files at the commit, not 212 | Corrected here and in the ledger |
| F6 | low | The process note and the plan said the checker "enforces the citation"; it enforces that a parenthetical is present | Both reworded |
| F7 | low | The verifier's board-spec paragraph sent the verifier to what the runs recorded; the clean-room paragraph, and L02f3's practice, use an operator-prepared extract, which is what keeps model source out | Board-spec paragraph now says "an extract ... prepared by the operator" |
| F8 | info | The evidence-model row carried usage rules in its failure-modes cell, unlike the other rows | Cell cut at the never-alone rule; a third rule under the table carries the citation and phrasing rules |
| F9 | info | The glossary said "QEMU device model"; the format says QEMU or another emulator | Glossary reworded |
| F10 | info | "What the checker enforces" said "a parenthetical naming its source" for five tags; the checker tests presence | Says so now |
| F11 | info | `variants: tag: emulated` is now legal; the format's variant text names `doc`, `press`, `source-observed` | Recorded under Limitations; no change |
| F12 | info | An over-long line in the scaffold skill | Rewrapped |
| F13 | info | The plan's "the user authorized running all of them ... in the order below" is not stated in any file the reviewer had | From the orchestrator's brief for this unit; left for the orchestrator to confirm in the PR |
| F14 | info | Pre-existing: the checker reports body-relative line numbers (the bad fixture's bullets at file lines 38 to 40 are reported as `:15` to `:17`) | Outside this unit; recorded under Limitations |

The reviewer confirmed the three rules against the format text and L02f3's rules (the
`[inference]`-premise and beside-another-class shapes pass, two `[emulated]` with nothing
else still fail, prose mentions are ignored, the added name cannot collide in the regexes),
the shipped specs and prior tests unchanged, the records consistent and non-repeating, and
no private infrastructure in the diff. It judged broader review unnecessary: three rules in
one checker function, fixtures, tests and text; no shared execution machinery.

## Limitations

- The checker enforces presence, not content: a parenthetical that names no run ID passes
  it, as a `[doc]` parenthetical naming the wrong page does. Content is the verifier's job.
- `variants: tag: emulated` is now a legal value because `TAG_CLASSES` is derived from the
  same list; nothing uses it and nothing forbids it.
- The never-alone rule counts tags anywhere in the tail clause, including inside an
  `[inference]`'s parenthetical; that is what lets the premise shape pass, and it also means
  `[inference]` is not itself checked for having a non-`[emulated]` premise. The verifier
  reads the argument.
- No board spec in the repository uses the class yet; the only real use is the clean-room
  e1000 spec in the private run store, which the checker does not read. The fixtures are the
  only executed examples.
- Revision 6's inline citations (`[emulated]` §12.5 EM2, no parentheses) predate the rule and
  would fail the checker if it read clean-room specs; the next spec revision (CF-1 rebuilds
  from revision 6, or any later feedback revision) converts them to `[emulated]` (§12.5 EM2).
- The checker reports body-relative line numbers (the frontmatter's lines are not counted),
  a pre-existing defect the review noticed; not changed here.
