<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF2-8b — Spec verifier in format 2

**Terms:** a verifier reads cited evidence in a fresh context; the orchestrator coordinates
readers; delta verification selects facts whose verdicts need renewal. See the
[glossary](../GLOSSARY.md).

This is step 4 and the verifier part of step 5 of
[SF2-8](../docs/SPEC-FORMAT-V2-PLAN.md#sf2-8--the-contract-and-the-board-spec-skills).
Run: `sf2-8b-20261009-01`. Starting revision: `a4ce86bc97a2a332b59f73881cb3d6f9dfa6254c`,
an exported tree. The orchestrator owns review, evidence and the checkpoint commit.

### 2026-10-09T16:11-07:00 — opening

Read the format 2 design, the SF2-3 evidence, schemas, freshness implementation and existing
verifier. Confirmed `status --json` supplies `basis` and `upstream`; SF2-6's separate tree
supplies `resolve` and `show`. The rewrite will select by root format and retain format 1
in a linked reference until SF2-12.

### 2026-10-09T16:11-07:00 — dead end: environment setup

The system Python's venv creation failed because ensurepip is unavailable. `uv venv --seed`
created a Python 3.12 environment; pip installed the hash-pinned requirements successfully.
The environment is in scratch because this export forbids dot-directories, overriding the
brief's request for an in-tree venv. No system packages were changed.

### 2026-10-09T16:11-07:00 — decisions within the design

- Route old board and peripheral handoff headings to the format 1 reference after checking
  the root format. Preserve the old procedure rather than silently applying YAML rules to it.
- Use `status` output for every basis and upstream map. An unknown basis blocks writing a
  current verdict; request correction of its structural cause first.
- A current critical fact without a reader still needs that reader. Current FAIL and
  unsettled ADJUDICATE also need resolution even when absent from the stale list.
- Document that D16 sub-keys are reserved but rejected in this export until SF2-7, and that
  the CLI gate allows unsettled ADJUDICATE as a warning; the user must adjudicate before merge.
- Keep the runnable worked example synthetic and use it to test the exact record shown
  in the skill, including a critical fact, an inference and a gap.

### 2026-10-09T16:17-07:00 — verification and handoff findings

The worked-record test first assumed the loader returned a wrapper; `load_strict` returns
the data mapping. Corrected the test's two accesses. All three example tests now pass,
including loss of a second reader and propagation of an edited premise to its inference.
The complete spec-format suite passes 254 tests. The other content suites and standalone
checks pass except two export-dependent suites: utilities has two failures from a
read-only git marker in scratch; campaign-review has ten errors from its stand-in scan's
`git ls-files`, which needs a real checkout. No unrelated tests or utility behavior changed.

Confirmed SF2-6 `resolve` and `show` with the synthetic document's hash and local bytes;
both report no findings. Source-anchor presentation is not exercised by this document-only
example. Help output confirms the documented source-checkout flags. The skill validator,
portability scan, explicit-path privacy check and open-side scan of changed files pass.

Searched all skills for old record naming, bullet/anchor keys, whole-file freshness,
front-matter summaries, pin lines, old checkers and second-verifier rules. Within the verifier
those rules remain only in the explicitly format 1 reference. Board-expert and scaffold
handoffs belong to SF2-8a; peripheral/review/investigator handoffs and templates to SF2-9;
old checkers and fixtures to SF2-12. Frozen campaign stand-in history remains history.
The final run report supplies commands, counts and detailed handoff hits for the ledger.

### 2026-10-09T16:17-07:00 — checkpoint: implementation ready for orchestrator review

Done: format 2 procedure, retained format 1 reference, synthetic root/manual, exact worked
record test, new glossary terms and this chapter/index entry. No plan status or evidence file
changed. No commit is possible in this export. Independent docs reviews, the git-based
checks and rerunning the export-dependent suites remain with the orchestrator; this entry
does not declare SF2-8 complete. The run report is the ledger handoff.
