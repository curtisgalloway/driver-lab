<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF2-7a — Peripheral specs and facts files in format 2

**Terms:** a payload is a fact's structured register, sequence or byte layout; a pin names
an immutable source commit; a sub-key names a supported field or step's separate verdict.
See the [glossary](../GLOSSARY.md). Plan: [SF2-7](../docs/SPEC-FORMAT-V2-PLAN.md#sf2-7--peripheral-specs-reviews-and-facts-files-in-format-2).
Run: `sf2-7a-20261009-01`. Reviews and HTML generation belong to separate units.

## 2026-10-09T19:23:01-07:00 — Implementation and first checks

- The license matrix already had 15 format 2 copies using the IP kind. They now use the
  peripheral kind, with the same expected exit codes; format 1 tools remain available.
- Nested support needs the same citation traversal as top-level support, including the
  license gate, references, resolution and basis hashes. Separately supported register
  fields and sequence steps get sub-keys; their bases also depend on the parent fact.
- C integer suffix removal must match numbers, not identifiers: a broad suffix regex
  truncated `CTRL`. The named-constant parser test now covers that case.
- The first mutation pass found a test that never moved HEAD and tests that indexed
  missing sub-keys before asserting their existence. The tests now move HEAD, retain the
  older pin, and assert presence before reading a record. Header membership uses the
  resolver's existing closed-file rule before source access.
- Both safety-check command defaults require a Git index. This export has none; the
  same scan functions were run with an explicit list of regular exported files.

## 2026-10-09T19:32:15-07:00 — Mutation qualification finished

- The remaining surviving mutation exposed an invalid control: the SoC fixture includes
  extension-class support and needs its root marker during validation. The test now
  validates each unchanged control first, with that marker, before adding a forbidden
  payload or requirement. Every mutation qualifies through assertion failures.
- The patch collector flags four empty directories reserved read-only by the harness;
  no authored file is refused. The orchestrator needs that collector detail in its ledger.


## 2026-10-09T20:41:25-07:00 — Review round 1 fixes

- Inventory comments now retain the complete expression. Object macros expand as tokens,
  preserving C precedence; duplicate and conditional definitions require agreement and
  complete branch coverage. Function macros, unsupported expressions and declarations,
  recursive or excessive expansions, and unresolved enum values remain named unknowns with
  reasons. Unknowns fail inventory even when a spec covers them. Header-defined macros
  suppress the built-in meanings; include guards are recognized by their opening pair.
- D16 now separates a supported child's data, citations and references from the parent's
  basis. The child keeps the register name and offset, or the sequence's step order.
  Field-anchor and step-action edits affect only their sub-keys; parent-only support and
  unsupported-child edits affect only the parent. Identity and step-order edits still
  affect the relevant children. Field requirements can override the inherited requirement.
- Ordinary peripheral overlay facts with hardware TODOs now reach the generated hardware
  list, in merged and separate views. Reset null is refused; absent width and access mean
  unknown. The design's register offset example uses canonical hexadecimal spelling.
- Fidelity restoration: both investigator answers again say "BAUD, the baud divisor" and
  "a write to it latches BAUD"; the firmware CTRL claim again says "bit 0 enables the block".
  Both initialization claims and their original citation ranges are restored verbatim.
  Invented reset, width and access values, the 8N1 field, the order row, and the per-step
  decomposition are removed; the original prose carries the initialization evidence.
- Fidelity restoration: the BSD target fixture again says "The driver binds by compatible
  string." Its original `[tgt: drivers/widget/widget.cc:12]` citation is retained in a note;
  no symbol was recorded, so format 2 uses a file-scoped `compatible` search rather than an
  invented symbol. Its citation now gates the target license without `--require-license`.
- Fidelity restoration: the documents-only fixture again says "The FIFO is 64 entries
  deep." Both it and the reset claim cite the original Widget TRM sections 5.1 and 4.2,
  replacing the conversion's programming-guide citation.
- Regression replay against the exported base gives 19 assertion failures and no unittest
  errors; all six inventory blocker regressions fail by assertion before the fixes.
- The nine reviewer guard gaps are addressed: eight have assertion-failing mutations; the
  redundant Markdown parent predicate is removed because sub-records have no section.
  The citation pass instead guards by top-level record path and has an exact diagnostic
  count test. The first mutation rerun also exposed a renamed bits guard and a layout
  mutation that crashed before its assertion; both now qualify by assertion in isolation.

## 2026-10-09T21:01:31-07:00 — Review round 2, supported-subset stop rule

- Round 1 and its confirmation both accepted wrong register values on valid C. The
  orchestrator's stop-rule decision in `fix-r2-brief.md` for run `sf2-7a-20261009-01`
  ends alternative evaluation: inventory now refuses duplicate definitions, conditional
  definitions and dependencies, and enum/macro collisions with explicit unknown reasons.
- A directive inside an enum refuses the entire body. Branch collection keeps alternative
  members, including comma-free branches, while initializer identifiers remain expressions.
  Directive text cannot close an enum or invent a member. Unknown members still count for
  omissions. The four round-2 inputs have regressions and refusal mutations.
- Include-guard recognition now checks the balanced whole-file wrapper and rejects outer
  alternatives. Empty guard macros remain in the definition table, so an empty `BIT` guard
  cannot restore an assumed built-in meaning. Object macros still expand textually.
- D16 child bases now include inherited requirements. Tests check stale verdicts for both
  fields and steps, new inheritance, and explicit overrides that remain independent.
- Mutation qualification exposed a new test that indexed a removed child before asserting
  its existence. The assertion now comes first so the refusal fails by assertion, not error.

## 2026-10-09T21:24:45-07:00 — Review round 3, refuse unrecognized tokens and arithmetic

- The round-2 confirmation found another shortened multiline-comment definition, token
  pasting interpreted as a comment, arithmetic that ignored C wraparound, and an enum
  member lost after a nested struct brace. The orchestrator's `fix-r3-brief.md` for run
  `sf2-7a-20261009-01` requires refusing anything not fully understood.
- Line splices now precede comment removal, and each block comment becomes one space
  before directive splitting. An explicit C token whitelist checks complete integer
  literals (including octal and legal suffixes), supported names, operators and calls.
  Unknown syntax keeps a refusal reason rather than shortening the definition.
- Division and remainder use exact integers. Every intermediate stays inside the
  unsigned 32-bit range; invalid shifts, zero divisors and possible signed overflow
  are refused. Unary complement's negative exact result is also unknown. No wrapping
  arithmetic is simulated.
- Enum scanning balances the enum's own braces while masking directive and quoted text.
  Nested braces or `sizeof` refuse every member; the member collector tracks nested
  parentheses, braces and brackets so later members remain named and count for omissions.
- Reviewing expansion exposed two additional hazards: adjacent replacement tokens could
  form a new operator, and an enum initializer's unsigned suffix could change arithmetic
  on its name. Expansions now preserve token boundaries; enum references use their
  evaluated integer value. Enum values outside the signed 32-bit range are refused.
- A seeded compiler comparison checks random whitelist expressions, macro and enum
  references, and all four confirmation inputs. It accepts only an equal integer or
  an unknown, bounds compilation and execution time, and skips explicitly when no C
  compiler is available. Refusal mutations cover the new independent guards.
- Mutation qualification found that disabling the entire token whitelist let a Python
  binary literal reach the parser's internal literal lookup and fail with an error.
  The mutation now removes only the preprocessor-operator refusals, producing an
  assertion failure for the token-pasting regression without unrelated parser errors.
