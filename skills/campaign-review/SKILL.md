---
name: campaign-review
description: >-
  Maintain and check a driver campaign's claim map and status index against recorded
  public evidence. Use when recording qualifications, candidate results, emulated
  observations, verification history or findings; automated sweeps are later work.
---

<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Campaign review

**Terms:** a claim map connects behavior claims to named checks and planted defects;
a status index records verdicts, their basis and finding dispositions. See the
[format](INDEX-FORMAT.md) and [glossary](../../GLOSSARY.md).

Read INDEX-FORMAT.md before editing a campaign's claims.yaml or status.yaml.
Recover facts from the cited evidence and explicitly supplied run IDs. Keep raw
artifacts private; publish only safe identities and concise verdicts with links.
Preserve qualification limits and unknown basis fields. Append new verdicts with
supersedes links; never relabel an old PASS as qualification of an untested claim.

Run scripts/index_check.py with the campaign directory and --root pointing to its
repository. It needs PyYAML and supports --json; it reads no private store and runs
no guests. Also run that repository's privacy check. Independent review should
trace the entries to the evidence, not treat schema validation as proof.

CR1 and CR2 provide data and this check only. Do not infer a sufficient-for-scope verdict,
start a candidate round, edit a spec or perform an outward action from a queued
item alone. Follow the campaign's authorization and review instructions.
