<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 112 — TODO worklist

**Terms.** A TODO is the `todo` field of a spec record: what is still unknown (`text`), what
kind of check settles it (`check`: `hardware`, `document` or `source`) and, optionally, how
(`method`). A readback worklist is the list of hardware TODOs a physical readback phase would
work through. See the [glossary](../GLOSSARY.md).

`spec.py todo <root>...` runs the same check as `status` and lists every TODO of the checked
roots, without reading a verdict. It is a read-only view: no verdict rule changes, and a TODO
stays open until a verifier settles it. `--check` keeps one `todo.check`; human output is grouped
by spec file and then by instance; `--json` prints `{"todos": [...], "counts": {...}}` plus the
check's own `ok`, `roots`, `errors`, `warnings` and `findings`. A `hardware` TODO without a
`method` is marked `(no method)` (`"missing_method": true` in JSON), and does not change the exit
status.

The schema allows a `todo` in eight places, and all eight are listed: facts (`gap` when the fact
has no support, else `supported-with-todo`), instance and variant rows, assumptions, and the
register fields, layout fields, steps and order rows of a typed payload. A payload row is listed
under its parent's reference plus `.<row id>` (`.order[<index>]` for an order row, which has no
id); `instance` is the instance row's name, null elsewhere.

| Acceptance | Evidence |
| --- | --- |
| Lists gap facts and supported facts with a TODO | `test_lists_gaps_and_supported_facts_with_a_todo` |
| `--check` filters | `test_check_filter` over all three checks |
| Hardware TODO without a method is flagged, exit unchanged | `test_hardware_todo_without_a_method_is_flagged_and_exit_stays_zero` (JSON and human) |
| Other record kinds named | instance and assumption test; variant test; payload rows test for field, layout field, step and order, each once |
| `--json` shape and counts | `test_json_shape`, `test_item_fields` |
| Exit codes 0, 1, 2, 3 | no-TODO and listed-TODO roots exit 0; invalid root and malformed todo exit 1 with the list still printed; usage error exits 2 with failure JSON; missing dependency exits 3 with failure JSON |
| Context roots not listed | `test_context_roots_are_not_listed` |
| `--skill` usage and SKILL.md updated | `test_skill_usage_documents_todo`; spec-format, hardware-investigator and board-expert docs |

Checks, all passing from the worktree: privacy scan, open-side scan, `spec.py check` of the
board-expert root with `--stubs-from skills --require-license` (0 errors, 0 warnings), the
spec-format suite (690 tests, one opt-in network test skipped; 17 are new), the
hardware-investigator suite (24 tests) and the board-expert suite (7 tests).

Smoke test: `spec.py todo skills/board-expert/specs --check hardware` lists nothing (0 TODOs: 0
hardware, 0 document, 0 source; 0 hardware without a method). The shipped root holds only its
marker and no spec files, so the tests carry the coverage.

Independent review: an independent reviewer subagent (Sonnet) read the diff and the saved test
output and found no blockers. Two should-fix findings were resolved. First, the tests did not
cover variant, field, step or order TODOs: two mutations of the worklist code, deleting the
guard against listing a supported payload row twice and mislabeling variants as instances, had
survived. New tests cover every row kind, and both mutations now fail. Second, the documentation
omitted the `.order[<index>]` reference form. Four nits were also resolved: an exit-3 test, the
availability wording, a misleading parameter name, and a forward link between records.

Limitations: the list reports what the files say. It does not judge whether a `hardware` method is
sufficient, and it does not read verdicts, so a TODO a verifier already settled still appears
until the spec drops it. Scope is the record's own; a payload row does not inherit its parent's
scope (it does inherit `critical`, as its verdict key does).
