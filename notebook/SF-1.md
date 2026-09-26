<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF-1 — `[emulated]` in the format

Follow-on of the [plan](../IMPLEMENTATION-PLAN.md) named in L02f3. Terms: **`[emulated]`** is
the evidence class for a result observed on a device model; the **checker** is
`skills/board-expert/scripts/spec_check.py`; a **tag clause** is the tail of a fact bullet
that the checker examines. See the [glossary](../GLOSSARY.md) and the
[evidence](../evidence/SF-1.md).

## 2026-09-25T20:33-07:00 — opening
Goal: add `[emulated]` wherever the tags are defined and checked, with L02f3's three usage
rules (cite the model version and the run IDs; state an observation, never the model's
mechanism; never the sole authority), and add a checker rule and tests. Start: branch
`driver-porting/sf1` from `origin/main` at `d4fa761`, own worktree, clean. Baseline: 36
board-expert tests OK; the shipped specs check clean under both parsers (9 pre-existing
`unverified` warnings).

## 2026-09-25T20:40-07:00 — the checker already had the shapes; only "never alone" is new
The citation rule is the `[doc]`/`[DT]`/`[rtl]`/`[inference]` parenthetical rule with one more
name, and the TODO rule is the `[source-observed]`/`[press]`/`[inference]` list with one more
name. The one genuinely new rule is "never the sole authority": a tail clause whose tag set is
exactly `{emulated}` is an error. It is a set test on the tags the checker already extracts
from the tail, so an `[emulated]` cited inside an `[inference]`'s parenthetical passes (the
inference carries the tag) and one beside a `[databook]` passes. A side effect accepted as
harmless: `variants: tag: emulated` is now a legal provenance class, since `TAG_CLASSES` is
derived from the same list.

## 2026-09-25T20:45-07:00 — what the checker cannot see
The phrasing rule (observation, not mechanism) and whether the parenthetical really names a
model version and run IDs are judgment; the checker tests only that a parenthetical exists,
the same as for `[doc]`. Those two rules go to `spec-verifier`'s text, which is where the
L02f3 verifier actually enforced them (against an observations extract, never the model's
source). The rule that the fact stays distinct from a hardware requirement is carried by the
mandatory `TODO (verify on hardware)`.

## 2026-09-25T21:05-07:00 — the review: the reference use did not match the rule I wrote
The reviewer read revision 6 in the run store and found its inline citations are bare
pointers (`[emulated]` §12.5 EM2), not parentheticals: the format as first written would
have rejected the very use it was adopted from, and no test could show it because the
board-spec checker never reads a clean-room spec. Fixed by letting the parenthetical name
either the model, version and runs or a numbered observation that carries them; revision 6's
bare form is a limitation for the next spec revision. The other findings were wording that
overstated the checker (it tests that a parenthetical exists, not what it names) and a
paragraph written before the review it described. The reviewer proved the three new tests
fail on weakened copies of the checker, which the implementer had not done.
