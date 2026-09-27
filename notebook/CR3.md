<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR3 notebook

**Terms:** the registry holds input identities; the sweep compares them with
verdict bases. A pin is an expected file hash. See the [glossary](../GLOSSARY.md).

## 2026-09-26T19:28:29-07:00 — Implementation and local verification

The existing qualification bases record older spec revisions even though their
validated harness hash is current. Comparing both independently exposed a spec
context gap; details and exact entries belong in [CR3 evidence](../evidence/CR3.md).

Five local artifacts were available for opaque hashing; the remaining registry
identities needed explicit snapshot provenance. Kept the adapter separate from
the sweep and reused the ENC28J60 pin comparator. Reviewer-supplied diff metadata
provides narrow mappings without making the sweep a source parser.

The first offline cache lacked PyYAML. The existing populated cache worked.
Multi-file Pyink workers stalled; individual file invocations completed. The
matrix and checks now pass. Independent review and checkpoint are left to the
orchestrator; no commit or external action was made.

## 2026-09-26T19:44:51-07:00 — Review fixes

The orchestrator accepted all three findings from the read-only Codex review
(gpt-6-astra). Added failing reproductions, then fixed index-only contested
observations, null available hashes and malformed enum types. All 56 campaign
tests and 105 ENC28J60 tests pass. The evidence records the dispositions and
13 qualification reconciliations for CR4; none were requalified here.
