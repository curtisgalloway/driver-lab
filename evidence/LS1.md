<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS1: anchor tools under test; several named pins

**Terms:** a *pin* names a source tree and its commit in a spec (`Source pin: linux@abc123`);
an *anchor* cites lines at that pin (`[src: path:L]`). *Characterization tests* record what a
tool did before a change, so the change can be shown not to alter it. See the
[glossary](../GLOSSARY.md) and the [design's terms](../docs/LICENSE-SPLIT.md#terms).

Design: [LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md), revision 2026-10-05 (LS-R3, LS-R6, the
script part of LS-R9). Plan: [LS1](../docs/LICENSE-SPLIT-PLAN.md#ls1--anchor-tools-under-test-several-named-pins).
Notebook: [LS1](../notebook/LS1.md). Starting revision `a82785c`; rebased onto `df815b2` (PR #43
merged); no pre-existing changes.

**Result: complete.** `anchor_check.py` and `inventory_check.py` had no tests and no CI step;
they now have 47 tests run in CI. A spec may state several named Source (or Target) pins, each
with an optional SPDX license expression, and cite them as `[src:<pin>: path:L]`. The
single-pin form and a bare `--repo PATH[@REV]` behave as before.

## What changed

- `anchor_check.py`: pin lines take an optional SPDX-shaped license after the revision; several
  pins per side, kept in spec order in `pin_list` (`pins` keeps the first per side for existing
  readers; before, a second pin silently replaced the first). Anchors may name a pin.
  `--repo`/`--target-repo` (and the `--impl-repo`/`--ref-repo` aliases) repeat as
  `NAME=PATH[@REV]`. New `--drift-pin NAME` chooses the pin `--drift` compares and `--rewrite`
  updates; the rewrite keeps the pin's license.
- `inventory_check.py`: the same grammar, imported from `anchor_check.py`; one named pin per
  run.
- Tests: `skills/anchored-peripheral-spec/tests/` (`test_anchor_check.py`, 37 tests;
  `test_inventory_check.py`, 10). CI step "anchored-peripheral-spec tests" and the AGENTS.md
  check list.
- `anchored-peripheral-spec/SKILL.md`: the pin grammar paragraph (full guidance is LS4).

## Acceptance

| Criterion | Evidence and result |
| --- | --- |
| Characterization tests pass against the unchanged grammar (recorded) | Run with `origin/main`'s two scripts swapped back in: the 26 characterization and compatibility tests pass; all 21 new-grammar tests fail (17 failures, 4 errors), so none of them can pass without the change. Log: `ls1-old-scripts.log` (session scratch), summary `Ran 47 tests … FAILED (failures=17, errors=4)` with 26 `ok`. The inventory characterization class was also run alone against the original script: `Ran 6 tests … OK`. |
| Two named pins each checked against their own tree; a wrong line names the pin | `test_each_anchor_resolves_against_its_own_pin`; `test_wrong_line_names_the_pin` asserts `pin fw: stub.c has 3 lines`; the same for named Ref pins (`test_named_target_pins`). |
| Duplicate pin name, or an unnamed anchor with several pins, exit 1 | `test_duplicate_pin_name_fails`, `test_unnamed_anchor_with_several_pins_fails` (anchor_check); `test_repeated_pin_name_fails` (inventory_check, exit 1 after review finding S2). |
| Frozen-archive specs give the same result as before | **The list is empty:** no committed spec carries a pin (`rg '^\s*(Source\|Target\|Impl\|Ref) pin:'` over the repository's Markdown finds only the two SKILL.md grammar examples); the evals' specs live in the private run store. The characterization tests carry the compatibility check instead. |
| CI runs the new suite; full check list passes | Step added to `checks.yml`. Full AGENTS.md list run locally after the review fixes: all 12 commands exit 0 (`ls1-checks-2.log`, session scratch), anchored-peripheral-spec `Ran 47 tests … OK`. |

## Deviations from the plan's steps

- **`--drift-pin` instead of `--rewrite-pin`:** the pin choice decides which anchors `--drift`
  compares, not only which line `--rewrite` edits. The reviewer judged it justified.
- **`inventory_check.py` takes one named pin per run** instead of "checking every pin": it
  compares one header tree against the spec. LS-R9's script part is met in that form; the plan's
  LS1 text is amended to say so.

## Review

Independent reviewer subagent (fresh context, read-only), reading the diff, the plan and design
sections, and the first check log, and probing with throwaway repositories. No blockers. Its
findings and their resolutions:

| # | Finding | Resolution |
| --- | --- | --- |
| S1 | Four new tests also passed against the old scripts: they asserted only exit 2, which the old scripts returned for an unrelated reason ("is not a git repository") | Each now asserts its message (`names pin 'uboot'`, `given twice for pin 'fw'`, `repeats a Source pin name`); the old-script run above shows every new-grammar test failing |
| S2 | `inventory_check.py` exited 2 for a duplicate pin name; a spec fault is a finding (1) | Exits 1 with `result: FAIL`; docstring updated; test asserts 1 |
| S3 | The license capture took any trailing text (`@rev (v6.1 tag)` became a pin with license "(v6.1 tag)"), which LS2's gate would read as a license | The capture accepts only SPDX-shaped tokens joined by `OR`/`AND`/`WITH`; other trailing text leaves the line unmatched, as before. Tests for both. A single non-SPDX token (`@rev mainline`) is still captured; LS2's SPDX validation rejects it (input for LS2) |
| S4 | No evidence file; criterion 1 recorded only in notebook prose | This file, with the old-script run |
| S5 | The overwrite test was not shown failing first | Shown failing against the old script (`test_licenses_recorded_and_first_pin_kept`: error) |
| N1 | `--repo a=b@REV` with a checkout named `a=b` was misread as a pin name | The existence check uses the path before `@`; `test_repo_path_containing_equals_sign` |
| N2 | `[stale: was <rev>]` does not name the pin on a multi-pin spec | Not changed: the anchor beside it names the pin |
| N3 | No tests for named target pins or `--drift-pin` errors | `test_named_target_pins`, `test_drift_pin_errors` |

The fixes were confined to the findings and covered by tests; no second review was run.

## Limitations

- A license is parsed and reported but not validated; LS2 adds SPDX validation and the gate.
- No spec in this repository uses the new grammar yet; the spec repositories (LS5) will be the
  first.
