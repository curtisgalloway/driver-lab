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
| `skills/board-expert/SPEC-FORMAT.md` | Terms: `[emulated]` in the class list, with its citation form (model, version, run IDs), the phrasing rule, the never-alone rule and the TODO; Tag rules: `[emulated]` needs the TODO and a parenthetical and is never the only tag; Clean-room rules: allowed under the same conditions, mechanism stays on the encumbered side; "What the checker enforces": the three rules, and the existing `[rtl]` and `[inference]` rules, which the list had omitted |
| `DESIGN.md` | "Make the kind of evidence visible": the class named with its origin and adoption date; the evidence-model table: a row for `[emulated]` (trusted for, assumes, failure modes, from the QEMU design's proposed row plus the L02f3 rules); the test-feedback loop: a model result becomes an `[emulated]` fact that narrows or confirms a claim without closing it |
| `QEMU-DIFFERENTIAL.md` | "(proposed)" removed from the term and the section; the section now records the adoption and points at the evidence model and the format |
| `GLOSSARY.md`, `EVAL-PLAN.md` | The class is adopted, not proposed; the provenance-tag term lists it |
| `skills/board-expert/scripts/spec_check.py` | `TAG_NAMES` gains `emulated`; `NAMED_TAGS` gains it (parenthetical required); a new `TODO_TAGS` tuple replaces the inline list and gains it; a new never-alone rule; docstring updated |
| `skills/board-expert/tests/test_spec_check.py` and fixtures | Six tag-rule unit tests; the good fixture gains two correct uses (beside `[databook]`; as an `[inference]` premise); the bad fixture gains one bullet per failure (alone, no TODO, no parenthetical), each producing exactly one finding, asserted in the every-failure-class test |
| `skills/spec-verifier/SKILL.md` | Board specs: an `[emulated]` claim is compared against what its cited runs recorded, never the model's source; clean-room driver specs: the same, with the three ways it fails |
| `skills/board-spec-scaffold/SKILL.md` | The tag-clause step names the TODO-carrying classes and the never-alone rule |
| `PROCESS-NOTES.md`, `IMPLEMENTATION-PLAN.md`, `notebook/` | The 18:50 process entry closed; a follow-on list with SF-1 complete and the order of the rest; "Next session" points at AF-1; chapter and index row |

Not changed: `os-investigator` and `cleanroom-spec`, whose tag lists are the investigation
classes (facts read from sources); `[emulated]` comes from test runs, which the design's
feedback loop, not the investigator, produces. The e1000 spec (revision 6) already carries
the class in its own §1 table and needs no edit.

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
| `python3 -m unittest discover -s skills/board-expert/tests` | 42 tests OK (36 before; every case runs under PyYAML and the subset parser) |
| `spec_check.py skills/board-expert/specs --stubs-from skills` | OK, 11 specs, 9 warnings, unchanged from before the change, under both `parser: pyyaml` and `parser: subset` |
| `spec_check.py --no-pyyaml` on the bad fixture | exactly one `[emulated]` finding per planted bullet (alone; no TODO; no parenthetical) |
| `utilities/check-no-private-paths.py` | OK, 212 tracked files |
| `git diff --check`; privacy grep of the diff | clean; no hits |

## Review

One fresh-context independent reviewer read the diff against `origin/main` and the checker's
test output (report in the run store under `review/`). Findings and resolutions are below;
the reviewer did not ask for broader review.

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |

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
