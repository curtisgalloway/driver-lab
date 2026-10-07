<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Evaluations

> **Frozen archive.** Everything under `evals/` is kept as history of the work before
> driver-lab's license split (2026-10-06) and is no longer updated. The clean-room skills these
> campaigns used now live in [cleanroom-skills](https://github.com/curtisgalloway/cleanroom-skills),
> with their [design](https://github.com/curtisgalloway/cleanroom-skills/blob/main/DESIGN.md), and
> new evaluation rounds run from there. Names and paths below are as they were then
> (`os-investigator` is now `cleanroom-investigator`). CI still runs the campaigns' checks, and
> `campaign-review` still reads `evals/e1000`. See the
> [license-split design](../docs/LICENSE-SPLIT.md), requirement LS-R20.

- [`enc28j60/`](enc28j60/README.md): the ENC28J60 pilot (corpus, answer key, scoring policy,
  checkers and reconstruction inputs).
- `e1000/`: the L02 differential campaign in QEMU: the [harness](e1000/harness/README.md), the
  blind requirement list, the claim map and the status index.
- `deployment.yaml`: the reference deployment manifest for continuous review (CR5).
- [`EVAL-CONSENSUS-2026-09-18.md`](EVAL-CONSENSUS-2026-09-18.md): the evaluation consensus two
  reviewers reached on 2026-09-18, the source of [EVAL-PLAN.md](../EVAL-PLAN.md).

Terms: a *campaign* is one device's spec, candidate, checks and evidence under one declared
scope; see the [glossary](../GLOSSARY.md).
