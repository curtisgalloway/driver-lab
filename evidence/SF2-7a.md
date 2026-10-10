<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF2-7a: peripheral specs and facts files in format 2

**Terms:**

- *payload*: a fact's structured register, sequence or byte layout.
- *sub-key*: the separate verdict key of a supported register field or sequence step (D16).
- *inventory*: `spec.py inventory`, which compares register records with the C headers at the pin.
- *stop rule*: the rule that a repeated blocker kind in confirmation stops the fix loop for a
  decision.
- *mutation*: a deliberate break in the code under test, used to show a test can fail.

See the [glossary](../GLOSSARY.md) for the rest.

Design: [SPEC-FORMAT-V2.md](../docs/SPEC-FORMAT-V2.md) (R1, D16; Peripheral specs and reviews;
The investigator's facts file). Plan:
[SF2-7](../docs/SPEC-FORMAT-V2-PLAN.md#sf2-7--peripheral-specs-reviews-and-facts-files-in-format-2).
Notebook: [SF2-7a](../notebook/SF2-7a.md). Run: `sf2-7a-20261009-01` in the private run store
(ledger, briefs, four Codex reviews, the executing Opus review).

**Status: complete for SF2-7a's scope.** The scope was split by the orchestrator under the user's
overnight instruction: SF2-7a is SF2-7 minus the review kinds and their fixtures (SF2-7b, the
plan's own split point) and minus the HTML generated sections, a follow-up now that SF2-5 is
merged. SF2-7 stays in progress.

## What was done

- **Implementation (Codex).** Payload schemas for the `peripheral` kind, the checker rules,
  verdict sub-keys, `inventory` reading records instead of prose, the generated sections in the
  Markdown view, the 15 license-matrix specs and the investigator's examples in format 2. The
  patch gate failed once: three investigator tests need the pinned format 2 tool set, not CI's
  Markdown-only venv. The CI step and the AGENTS.md checks line moved to the format 2 venv.
- **Round 1** (a Codex review and an Opus executing review). Four inventory blockers (a comment
  truncating an expression, duplicate or conditional definitions overwriting, wrong macro
  semantics, silently skipped constructs), plus fidelity losses in the investigator examples,
  D16 sub-key freshness coupled to the parent, and nine guards no mutation touched. The
  orchestrator's D16 decision: a sub-key's basis covers its own data and support plus the
  parent's identifying data; the parent's basis excludes children that carry their own support
  ("precise where the author cited precisely"). Fixes restored the lost fidelity and added
  assertion-failing mutations.
- **Round 2, stop rule hit.** The confirmation found four more inventory blockers of the same
  kind (wrong values accepted on valid C). Decision: inventory evaluates a supported subset only
  (one unconditional definition, no conditionals in an enum or definition, no enum and macro
  name collision, no local redefinition of a built-in macro name); everything else is an unknown
  with a reason.
- **Round 3, stop rule hit again.** The confirmation found three more (a multiline comment
  truncating a define, `##` read as a comment, lost 32-bit overflow) and a `sizeof` in an enum.
  Decision: refuse what is not fully understood. Comments and line splices are removed first, a
  token whitelist gates every expression, arithmetic is exact and any intermediate outside
  0 to 2^32-1 is unknown, and braces or `sizeof` in an enum make it unknown. A differential test
  compares the evaluator with a C compiler when one is present: 388 inputs, none with a wrong
  value (an equal integer or an unknown is the only accepted answer). Decision for the next
  round: if the final confirmation still found blockers, merge and open issues, with no fourth
  round.
- **Final confirmation.** One blocker: an unclosed enum (an unbalanced brace inside `#if 0`)
  dropped its members. The orchestrator fixed it directly to fail closed (`enum@line<N>` is
  unknown); the regression fails before the fix and passes after. No further review round.

## Acceptance criteria

The plan's SF2-7 criteria, restricted to SF2-7a. The `finding`, `pair` and `coverage` payloads
and the review kind are SF2-7b.

| Criterion | Evidence | Met |
| --- | --- | --- |
| The widget register, sequence and finding examples validate and render | Register and sequence examples validate and render in the Markdown view. The finding example is a review payload: SF2-7b. The HTML view is the follow-up | partly (register and sequence, Markdown) |
| `inventory` reports an omitted register and a value mismatch on fixtures, exactly | Fixture tests assert both. Wrong-value acceptance, the repeated blocker kind, is closed by refusal: 388 compiler-differential inputs with no wrong value | yes |
| The peripheral license-gate matrix and the investigator's worked-example tests pass in format 2 | The 15 matrix specs use the peripheral kind with unchanged expected exit codes; the investigator tests pass under the pinned format 2 tool set | yes |
| Review focus: generated lists equal the facts they come from | Hardware TODOs on payload-less overlay facts now reach the generated lists in merged and separate views (round 1 finding) | yes, Markdown view |

## Design coverage

- **R1:** the peripheral kind validates, with typed payloads.
- **D16:** register fields and sequence steps with their own support get sub-keys. A field
  edit changes only its sub-key; identity and step-order edits change the relevant children;
  inherited requirements are part of the child basis (confirmed by the round 2 review).

## Reviews

| Reviewer | Outcome |
| --- | --- |
| Codex, round 1 (`codex1`) | 4 inventory blockers; should-fix: the built-in `BIT()` overrides a source definition, generated lists omit payload-less overlay facts |
| Opus, executing review (`claude1`) | no code blocker; fidelity losses in the investigator examples, dropped `_H` and leading-underscore names, duplicate define overwriting, truncation, implicit enum values, D16 coupling, parent-only override of `hw-required`, nine surviving guard mutants, `reset: null` rendering, the design's offset example |
| Codex, confirmation 2 (`codex2`) | 4 blockers of round 1's kind (stop rule); D16 and the investigator fidelity confirmed |
| Codex, confirmation 3 (`codex3`) | 3 blockers and a should-fix (stop rule); D16 inherited requirement confirmed |
| Codex, final confirmation (`codex4`) | 1 blocker, the unclosed enum; fixed by the orchestrator, no further round |

## Consequential findings

- **Inventory accepted wrong values on valid C**, in three consecutive rounds. A bounded fix per
  case did not converge, so the rule changed from "evaluate correctly" to "refuse unless fully
  understood". Resolution: the stop-rule decisions above, plus the differential test as the
  check that no accepted value is wrong.
- **Unclosed enum.** A brace inside `#if 0` can leave an enum unclosed and silently drop members.
  Resolution: fail closed with a named unknown.
- **Investigator example fidelity.** The first conversion invented reset, width and access values
  and a per-step decomposition, and dropped the BSD target and documents-only facts' original
  citations. Resolution: original wording and citations restored; the invented values removed.
- **Surviving guards.** The reviewer found nine guards no mutation touched. Resolution: eight got
  assertion-failing mutations; the ninth was a redundant predicate and was removed.
- **Mutation qualification found test bugs** (tests indexing a record before asserting it
  exists, a control that did not validate). Resolution: assertions moved first.

## Verification

At the final state after the merge of `origin/main`: 619 spec-format tests; 133 of 133 mutations
killed by assertions at round 3 (no crashes); the compiler differential above. The full
AGENTS.md checks list at close-out is recorded below.

Close-out, in the SF2-7a worktree reusing `.venv-sf2`: every command in the list exited 0
(`check-no-private-paths.py` OK on 613 tracked files; `check-open-side.py` OK on 612; utilities,
board-expert, peripheral-spec, hardware-investigator (19 tests, in the format 2 venv),
spec-format (619 tests), enc28j60, e1000 and campaign-review suites OK; `spec_check.py` OK;
author manifest matches; campaign index OK, 28 claims). The compiler differential checked 389
values: 319 equal, 70 unknown, none wrong.

## Limitations and follow-ups

- **Inventory reports more names as unknown, by design.** Anything it cannot fully evaluate
  (conditionals, duplicate definitions, function-like macros, nested braces or `sizeof` in an
  enum) is a named unknown, and unknowns fail inventory even when a spec covers them. A header
  that uses such constructs needs them resolved or the spec marked.
- **HTML generated sections** (provenance notice, register tables, hardware and open-question
  lists) are not in the HTML view yet: a follow-up now that SF2-5 is merged.
- **Reviews** (`finding`, `pair`, `coverage`, the review kind and fixtures): SF2-7b.
- **Compiler differential** skips explicitly when no C compiler is installed.
- **Not run here:** CI on the GitHub runner (the pull request runs it).
