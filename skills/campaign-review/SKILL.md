---
name: campaign-review
description: >-
  Maintain and check a driver campaign's claim map and status index against recorded
  public evidence. Use when recording qualifications, candidate results, emulated
  observations, verification history or findings, or detecting stale verdicts after
  a recorded input changes.
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

At the start of each orchestrator session and whenever a known input changes
(such as a package upgrade or manual edition), refresh applicable sources locally
with scripts/pinned_file_adapter.py REGISTRY ID --write --json, then run
scripts/sweep.py CAMPAIGN --json. Both need PyYAML; their --skill output documents
the CLI. The adapter resolves repository/run-store-relative files and hashes opaque
bytes; the sweep opens only the three metadata files. An adapter observation does
not adopt a new edition or replace an expected pin. Preserve the deployment's
authorization requirements for changing an adopted source.

Inspect unavailable identities and each stale/contested entry, retaining the
report as a review artifact. Use reviewed, hash-bound change maps to narrow a
change; an unreviewed or incomplete harness mapping widens to all qualifications.
The registry's snapshot provenance is not a live host check. Sources absent from
the registry cannot trigger detection. Run the sweep locally; public CI runs the
tests and index check, not private-source refreshes or the real sweep.

CR3 reports freshness only. Do not infer a sufficient-for-scope verdict,
start a candidate round, edit a spec or perform an outward action from a queued
item alone. Follow the campaign's authorization and review instructions.
