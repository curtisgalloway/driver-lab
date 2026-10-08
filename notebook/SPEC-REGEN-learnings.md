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
| review practice | For a gate or checker, run both an executing reviewer (break cases, mutations) and a diff reader; in RG-T1 each found a bypass the other missed | RG-T1 T1, T2, T9 | both | proposed |
| review practice | Break cases must include degenerate inputs (empty anchors, aliases of the tag under test) | RG-T1 T1, T2 | Codex, Claude | proposed |
| review practice | When a format rule changes, grep every skill for the old rule | RG-T1 T7 | Codex | proposed |
| review practice | Every spec field handed to a subprocess is untrusted input: `--` before positional args, scheme allow-list, no shell; reviewers probe it | RG-T1 R1 | both | proposed |
| review practice | A flag or path that relaxes a gate (context roots, skip-on-error) needs a test proving it cannot relax the gated input itself | RG-T1 R2, R3 | both, Claude | proposed |
| `spec-verifier` | Rule for a correct value whose locator is missing from the bullet (split three ADJUDICATE items); and whether a derivation inside a `[doc]` bullet needs `[inference]` | RG1 A1–A3, V5 | verifiers | proposed |
| `spec-verifier` | Say who spawns the second verifier when verification is delegated, and add a record field showing whether it ran | RG1 re-verification reports | verifiers | proposed |
| `SPEC-FORMAT.md` | `summary` keys omit `adjudicate`; `sources` has no place for a document hash | RG1 re-verification reports | verifiers | proposed |
| `spec-verifier` | A `[src]` bullet stating where hardware is (an address map) needs a document class too; say so in the class rule | RG1 V8 | verifier | proposed |
| tool design | Parse a format once and derive every check from that parse; two scanners of one file disagree, and each disagreement is a bypass | RG-T1 rounds 3–5 | Codex | in RG-T1 round 6 |
| review practice | When a fix round opens new holes in the same layer, stop patching and redesign; set the stop rule before the next round | RG-T1 rounds 3–5 | orchestrator | applied |
| orchestrator briefs | Give parallel verifiers distinct scratch directories; give the right `anchor_check.py` path | RG1 overlay verifier | verifier | applied from RG2 |

## Reviewer comparison

Per unit: findings accepted from each reviewer, and how many each caught that the other missed.

| Unit | `spec-verifier` accepted | Codex accepted | Verifier only | Codex only | Both |
|---|---|---|---|---|---|
| RG-T1 (tooling; Claude column is the code reviewer) | 6 | 8 | 4 (T2, T9, T10, T11) | 6 (T1, T4–T8) | 2 (T3, T12) |
| RG-T1 round 2 (Claude column is the code reviewer) | 9 | 8 | 4 (R3, R10, R11, R12) | 3 (R5, R7, R9) | 5 (R1, R2, R4, R6, R8) |
| RG1 | 4 | 20 | 2 (V1, V4) | 18 | 2 (V3/C5, V2/C13 partly) |
