<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF2-8a — The format 2 contract, board-expert and scaffold

Terms: a fact record stores a claim and structured evidence; a root is a directory of specs;
a rendered view is generated from those records. See the [glossary](../GLOSSARY.md).
Goal: steps 1–3 and the relevant step 5 of
[SF2-8](../docs/SPEC-FORMAT-V2-PLAN.md#sf2-8--the-contract-and-the-board-spec-skills).
Review and the milestone evidence remain with the orchestrator; run `sf2-8a-20261009-01`.

## 2026-10-09T16:11-07:00 — opening
Starting revision: export of `a4ce86bc97a2a332b59f73881cb3d6f9dfa6254c`, with no git metadata.
No earlier implementation changes identified. Write the contract against the schemas and the
SF2-4/SF2-6 command definitions, replace scaffold templates with YAML, keep an explicitly
labeled format 1 reading path, and run the required suites. SF2-8b owns spec-verifier.

## 2026-10-09T16:18-07:00 — decision: document-first templates
The four base templates cite documents only; the source overlay demonstrates DT/src pins and
a cross-root inference. A documents-only overlay and marker cover the empty accepts policy.
Schemas stay the single source for shapes. Tests will fill every placeholder and check composition.

## 2026-10-09T16:18-07:00 — surprise: review-branch rendering
SF2-4 fences author text rather than embedding live Markdown. The contract describes that
implemented behavior and labels HTML as SF2-5. SF2-6 resolver commands take files, not roots.

## 2026-10-09T16:18-07:00 — dead end: system venv
The system Python could not create a seeded environment because ensurepip is unavailable.
Switched to uv venv with seed packages under temporary storage; pip checked requirement hashes.
The direct request forbids dot-directories, so the brief’s in-tree venv example is not used.

## 2026-10-09T16:26-07:00 — discovery: a contract consumer outside the board reader
The full checks exposed campaign-review's class registry parsing the old contract's prose.
It now reads the authoritative support-class enum; its explicit format 1 target-spec extension
path is retained. Added regression checks for enum-only recognition and the empty-list failure.
This is the narrow dependency repair required by moving the contract, not a campaign migration.

## 2026-10-09T16:26-07:00 — checkpoint: implementation awaiting independent review
The contract, reader and scaffold are implemented; all eight substituted YAML templates validate.
Composition and documents-only placement have positive and negative checks in the existing suite.
The full checks were attempted. Stand-in campaign tests require git metadata this export cannot
provide; utility git-tree detection also disagrees with this sandbox's scratch/export layout.
The ledger report records exact commands, counts and limits. The two git-based privacy checks
are left to the orchestrator as the brief directs. No verifier files or format 1 tools changed.
The plan remains in progress. Independent review and the checkpoint commit belong to the
orchestrator; SF2-8b implements the verifier. HTML rendering remains SF2-5; other skill migrations
remain SF2-9, and legacy readers/tools retire in SF2-12.

## 2026-10-09T17:49-07:00 — review round 1 fixes
Recovered the unchanged format 1 contract from the pre-SF2-8a revision into FORMAT-1.md;
its legacy consumers now have their sections back. Replaced all template SPDX defaults with
placeholders and added license checks against the declared root policy. Clarified marker paths,
overlay references, SoC instances/INTIDs, pinned DT text and confidential-document exclusions;
the scaffold points to the verifier's format 2 procedure. The Git-based checks cannot enumerate
this export; their scan functions checked the exported files instead. Commands, results and
the remaining Git-index check belong in the orchestrator's private ledger. SF2-8b files were
not edited.

## 2026-10-09T19:00-07:00 — closed
Round 1 reviews and the confirmation round (every finding fixed, no new blocker or should-fix)
are done; 8b was merged into this branch and the milestone lands as one pull request. Outcome
and findings: [evidence/SF2-8.md](../evidence/SF2-8.md). Kept for later: the reviewer's
format 1 deletion blocker is the pattern to check first when a contract file becomes a pointer.
