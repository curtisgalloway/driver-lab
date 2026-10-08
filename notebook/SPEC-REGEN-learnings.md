<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Spec regeneration: review learnings

Rollup of the review findings recorded in [RG-regen](RG-regen.md), grouped by the skill or
format rule they implicate. Each row is a proposed change; it is made in its own driver-lab pull
request, not inside a unit.

| Skill or rule | Proposed change | Evidence (unit, finding) | Found by | Status |
|---|---|---|---|---|
| `spec-verifier` | Check a summary table against the figure and chapter it summarizes; a claim built on one table row can hide exceptions elsewhere | RG1 C1, C2 | Codex | proposed |
| `spec-verifier` | Coverage pass: list the facts in each cited table or section that the spec omits, not only whether stated claims hold | RG1 C11, C12 | Codex | proposed |
| `spec-verifier` | Verify that a TODO's proposed method can observe the thing (privilege level, security state) | RG1 C4 | Codex | proposed |
| `spec-verifier` | Grade citation precision (page range, table named, derived wording) explicitly instead of PASS-with-note | RG1 V2 | verifier | proposed |
| `spec-verifier` | Rule for bullets with facts plus a trailing TODO (verifier invented "PASS on the facts") | RG1 verifier report | verifier | proposed |
| `board-spec-scaffold`, `hardware-investigator` | Arm documents: try `documentation-service.arm.com/static/<id>` PDFs when `developer.arm.com` returns 403; record the canonical resource and the retrieval URL | RG1 C6, C17, C19 | Codex | proposed |
| `board-spec-scaffold` | SoC checklist: console routing per model and enable flags; Linux entry contract (placement, alignment, caches); memory discovery and reservations; full interrupt-ID table | RG1 C7, C8, C9, C11 | Codex | proposed |
| `board-spec-scaffold` | `[DT]` facts take the device tree's license; say so where it invites copying DT values, and give a docs-root template variant without `repos` | RG1 implementer friction 5, 6 | implementer | proposed |
| `hardware-investigator` | Confirm the license per cited file at the pin, not per repository | RG1 V3, C5 | both | proposed |
| docs, permissive `AGENTS.md`/README | Their citation rules describe peripheral specs only; add the board-spec form (`resources.docs`, hash in `note`) | RG1 implementer friction 3, 4 | implementer | proposed |
| `SPEC-FORMAT.md`, `spec_check` | `[src]` class with pin and license gate; check overlay records; CI anchor-checks board specs | RG1 implementer friction 1, 2; V4 | implementer, verifier | in RG-T1 |
| orchestrator briefs | Give parallel verifiers distinct scratch directories; give the right `anchor_check.py` path | RG1 overlay verifier | verifier | applied from RG2 |

## Reviewer comparison

Per unit: findings accepted from each reviewer, and how many each caught that the other missed.

| Unit | `spec-verifier` accepted | Codex accepted | Verifier only | Codex only | Both |
|---|---|---|---|---|---|
| RG1 | 4 | 20 | 2 (V1, V4) | 18 | 2 (V3/C5, V2/C13 partly) |
