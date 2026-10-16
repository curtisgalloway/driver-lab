---
name: spec-eval
description: >-
  Use when you have a bank of code-writing items for a spec and want to measure, by compiling
  and running unit tests, whether readers of the spec write correct driver-helper code: to
  author or self-test an item bank, export the preambles contestants compile against, or grade
  a sweep of answers. No model judges anything.
---

<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Spec eval

## Terms

- **Item / item bank** — one code-writing task with its reference, trap and tests / a JSON file
  of items.
- **Reference** — an answer that is correct by the source document. It must pass the harness.
- **Trap** — a plausible wrong answer (the common misreading). It must fail the harness; if it
  passes, the harness is too weak.
- **Harness** — the Rust unit tests that grade an answer, run against a mock register bus.
- **Abstention / `SpecGap`** — answering "the spec does not say" by returning
  `Err(SpecGap("..."))` instead of inventing code. The right answer to an out-of-spec item.
- **Arm** — one information source a round compares (for example, the spec versus the
  source document). Unrelated to the Arm processor company.
- **Stratum** — the kind of item: `in-spec-scalar`, `in-spec-structured`, `out-of-spec`,
  `adversarial` or `synthesis`.
- **Archetype** — the code pattern an item exercises: `w1c-rmw`, `ordered-sequence`,
  `capability-gating`, `bitfield-codec` or `hardware-math`.
- **Tier** — item difficulty, 2 or 3 (legacy spelling `"tier2"` and `"tier3"`).

The glossary at `GLOSSARY.md` in the repository root covers the rest.

## What it measures

Whether a reader of a spec can write correct driver-helper code from it. Each answer is
compiled with `rustc` and run against the item's unit tests; the outcome is mechanical. There
is no model-judged grading.

## Where banks live

A bank quotes the sources its items were written from, so it lives in the spec repository it
tests, at `eval/bank/code_bank.json`, under that repository's license. This repository holds
only the tool and a synthetic bank for its tests (`tests/fixtures/synthetic_bank.json`,
an invented device).

## Item format

`schema/code_bank.schema.json` is the format (JSON Schema, draft 2020-12). A bank is an array
of items, or an object `{"items": [...]}`. Each item needs `id`, `stratum`, `tier`,
`task_prompt` and one name of each pair below; legacy names are still accepted, and an item
that carries both names of a pair is refused.

| Canonical | Legacy |
| --- | --- |
| `fn_signature` | `signature` |
| `reference_rust` | `ref_rs` |
| `trap_rust` | `trap_rs` |
| `test_harness` | `tests_rs` |
| `preamble` | `preamble_rs` |
| `chapter_or_block` | `domain` |
| `doc_pages_primary` | `pdf_pages` |
| `doc_pages_secondary` | `pdf_pages_secondary` |

Other optional fields: `archetype`, `spec_id`, `spec_facts`, `citation`, `notes`,
`use_hw_prelude` and `abstain_probe`. `fn_signature` is the header only (no `{`); it is what
`--export-preambles` hands to a contestant. The bank is validated as a whole document, so an
unknown top-level key is refused too.

- `use_hw_prelude: true` puts the prelude (below) ahead of the item's own `preamble`. Without
  it the preamble must stand alone, including its own `SpecGap` if the signature uses one.
- `abstain_probe` is a Rust expression of type `Result<_, SpecGap>` that calls the function
  being tested with arguments for which an abstaining answer returns `Err(SpecGap(_))`. The
  grader appends `#[cfg(test)] mod __eval_probe { use super::*; ... }` with one test,
  `assert!(matches!({ <expr> }, Err(SpecGap(_))))`. The probe test passing means the answer
  abstains; an answer that panics, fabricates or prints anything cannot make it pass. The
  probe test is not counted as one of the item's tests, and the expression sees every name the
  prelude and the answer define (`use super::*`).
- **Out-of-spec contract.** An out-of-spec item's `reference_rust` and `test_harness` encode
  the source document's answer (the spec repository lacks it, the source document has it), so
  an arm reading the document can score `correct`. Abstention is detected by `abstain_probe`,
  which every out-of-spec item must have (`check_bank` refuses the bank otherwise). The
  reference must not abstain; self-test fails the item if the probe fires on it.

Every signature must return `Result<_, SpecGap>` so that any item can be answered by
abstaining; `--self-test` checks this by compiling the harness and probe against a stub body.
An abstention is detected only through the item's probe or a record's own `abstained` flag;
an item without a probe (in-spec items) that is answered with `Err(SpecGap(..))` is simply a
failing answer (`test-fail`) unless the record says it abstained.

## The prelude

`rust/hw_eval_prelude.rs` is the text before its marker line; the test module after it is not
prepended. It defines:

- `SpecGap(&'static str)` and `BusOp` (the recorded operations, including `DelayUs`).
- `trait RegBus` with `read8/16/32/64`, `write8/16/32/64` and `delay_us`.
- `MockBus`: stored registers, scripted read queues and an operation log. A read pops the
  offset's queue first, else returns the stored value. Builders `with_reg8/16/32/64`; setters
  and getters `set_reg*` and `get_reg*`; `queue_reads*`; `writes*_to(off)`; `last_write32`;
  `delays_us`; `total_delay_us`; and the public `ops` log for asserting exact order.

Semantics worth knowing when you write a harness: a narrower write replaces the whole stored
value (`write8` at an offset holding a 32-bit value leaves only that byte); writes do not
drain or change a pending read queue; write-1-to-clear is not modeled (a read after a W1C
write returns what was written), so assert on the writes, not on the register afterward.

## Archetypes and strata

Archetypes: `w1c-rmw` (write-1-to-clear bits: write only the bit, never read-modify-write),
`ordered-sequence` (writes, delays and polls in a required order), `capability-gating` (read a
capability, act only when present), `bitfield-codec` (pack and unpack a register or descriptor
word), `hardware-math` (dividers, timeouts, rounding).

Strata: `in-spec-scalar` (one stated value or formula), `in-spec-structured` (a layout or
table), `out-of-spec` (the spec does not say; the right answer is abstention in the arms that
may abstain), `adversarial` (the requirement embeds a false premise), `synthesis` (several
facts combined).

## Arms

A round compares information sources and labels its arms. Pass `--abstain-arms` with the
labels in which an out-of-spec item's right answer is abstention; in the other arms an
abstention counts as wrong. The round's contestant prompts, sandbox and isolation rules live
with the round, not in this repository.

## Adversarial items: the false-premise rule

Embed the caller's wrong assumption naturally in the requirement, without warning the
contestant. For example, a comment saying the capability ID is 0x0031 while the harness's mock
holds the real 0x0030. Record the truth in `spec_facts` so the verifiers can check it. A
contestant who copies the premise fails the harness; one who reads the spec passes.

## Authoring protocol

1. **Draft** the item: prompt, signature, reference, trap and harness, with page citations.
2. **Self-test**: `grade_code.py --self-test` must pass. It proves the reference passes
   the harness, the trap fails it (a trap that hangs is also a finding), the harness and probe
   compile against the published signature with a stub body, the probe fires on that stub, and
   the probe does not fire on the reference.
3. **Blind verification**: three independent reviewers (models or people) each check every item
   against the source documents, without seeing the reference or the other reviews. Fix or drop
   items they dispute.

## Commands

All scripts use only the Python standard library and need `rustc` (edition 2021) on the path.
Run them with `python3 -I`.

```bash
python3 -I skills/spec-eval/scripts/grade_code.py --bank eval/bank/code_bank.json --self-test
python3 -I skills/spec-eval/scripts/rust_check.py --export-preambles eval/bank/code_bank.json -o code_preambles.json
python3 -I skills/spec-eval/scripts/rust_check.py ITEM_ID --file answer.rs --preambles code_preambles.json
python3 -I skills/spec-eval/scripts/grade_code.py --bank eval/bank/code_bank.json --raw raw/ --out graded.jsonl --report report.md --abstain-arms ARM1,ARM2
```

- The export holds only `preamble`, `signature`, `tier` and `use_hw_prelude` for each item, so
  it can go to a contestant. `rust_check.py` reads it from `--preambles`, else from
  `SPEC_EVAL_PREAMBLES`, else `code_preambles.json` in the current directory, and takes the
  code from `--code`, `--file` or standard input.
- A sweep's `--raw` is a `.jsonl` file or a directory of them. Each record has `item_id` (or
  `id`), `model`, `arm`, `rust_code` and optionally `abstained`. Records with an unknown item
  id are reported on standard error and graded `unknown-item`, outside the tables.
- Outcomes: `compile-error`; `abstain-ok` (out-of-spec item, abstain arm, abstained);
  `abstain-wrong` (abstained anywhere else); `correct` (the run finished and all of the item's
  tests passed); `test-fail`. Passed means `correct` or `abstain-ok`. A run that aborts, exits
  or times out part-way is never `correct`: it must announce `running N tests`, print the
  `test result:` line, report all N, and exit with the test runner's own status (0, or 101
  when a test failed), so a binary killed by a signal fails whatever it printed.
- `--abstain-arms` is required when the bank has an out-of-spec item: name the arms (comma
  separated) in which abstaining is right, or give `none`. Naming an arm that appears in no
  record prints a warning, and the report states the set used.
- A record whose `abstained` is true counts as an abstention whatever the code does (with
  empty or blank `rust_code` it is graded without compiling). The self-report overrides the
  code's behavior, so use it only when the contestant's instructions give a way to abstain
  without code.
- Answers containing `macro_rules!`, `#![`, `process::exit` or `__eval_probe` (matched with
  any whitespace Rust allows between the tokens) are refused: `compile-error` with
  diagnostics starting `refused:`. The list blocks the obvious ways to subvert a harness; it
  is not a sandbox.
- **Grading runs answers unsandboxed**, with the grader's privileges, file system and network,
  and the harness assumes answers are not written to subvert it. Run grading in a disposable
  environment.
- `rust_check.py` compiles a library crate, while grading builds the test program; an error
  that appears only in the full build can pass `COMPILE_OK` and fail at grading.
- `SPEC_EVAL_RUN_TIMEOUT` (seconds, default 20) bounds each test run; a value that is not a
  positive integer exits 2.
- `--jobs N` sets the thread count (default: the CPU count). `--schema` and `--prelude`
  override the bundled files.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success (`COMPILE_OK`, export written, grading finished, self-test clean). |
| 1 | Self-test findings or schema errors; `rust_check.py`: `COMPILE_ERROR`. |
| 2 | Usage or environment error: bad arguments, unreadable file, unknown item id, no `rustc`. |

## Not here

Document slicing helpers (turning a PDF into pages for a contestant) and the contestant
prompts, sandbox layout and rules about what a contestant may read. Those belong to the
evaluation round, outside this repository.
