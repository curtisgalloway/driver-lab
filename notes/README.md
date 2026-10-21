<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Notes

Working records: how the project got here and the evidence behind what the
[README](../README.md) claims. Current documentation is in [`docs/`](../docs/); terms are in the
[glossary](../docs/GLOSSARY.md).

| Folder | What it holds |
| --- | --- |
| [`plans/`](plans/) | Implementation plans with milestone status: [atlas connections](plans/ATLAS-CONNECTIONS-PLAN.md), [spec format](plans/SPEC-FORMAT-PLAN.md), [spec regeneration](plans/SPEC-REGEN-PLAN.md), [license split](plans/LICENSE-SPLIT-PLAN.md) |
| [`evidence/`](evidence/README.md) | One file per experiment: conclusions, acceptance table, limitations, findings |
| [`notebook/`](notebook/index.md) | The lab notebook: one chapter per experiment, with discoveries and dead ends |
| [`research/`](research/) | Surveys of existing hardware-description standards ([1](research/STANDARDS-SURVEY.md), [2](research/STANDARDS-SURVEY-2.md)) |
| [`history/`](history/) | [The move out of public-skills](history/TRANSITION.md), the [process log](history/PROCESS-NOTES.md), and the [public-skills commit map](history/public-skills-commit-map.txt) |
| [`archive/`](archive/) | Frozen evaluation documents from before the license split: the [implementation](archive/IMPLEMENTATION-PLAN.md), [deferred](archive/DEFERRED-PLAN.md) and [evaluation](archive/EVAL-PLAN.md) plans, the [reconstruction protocol](archive/RECONSTRUCTION.md), the [QEMU differential design](archive/QEMU-DIFFERENTIAL.md), and the validation [proposal](archive/VALIDATION-PROPOSAL.md) and [review](archive/VALIDATION-REVIEW.md) |

`archive/`, and the files in `evidence/` and `notebook/` from before the split, are the frozen
archive described in [docs/LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md): kept as history and not
updated. `utilities/check-open-side.py` allowlists `archive/`, `evidence/`, `notebook/` and
`history/`. These files lived at the repository root, or in
top-level `evidence/`, `notebook/` and `history/` folders, until 2026-10-21; links pinned to
earlier commits still use those paths.

The repository was split out of [public-skills](https://github.com/curtisgalloway/public-skills)
on 2026-09-25 and renamed from driver-lab to hardware-specs on 2026-10-21.
