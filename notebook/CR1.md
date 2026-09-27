<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR1: claim map and index implementation

**Terms:** the claim map links behaviors to checks; the status index records their
verdicts and basis. See the [glossary](../GLOSSARY.md). Conclusions and decisions
are in [the evidence](../evidence/CR1.md); item status is in
[the index](../evals/e1000/status.yaml).

## 2026-09-26T17:48:29-07:00

Recovered the later identities from the named records; the earlier two run stores
were absent, so their run citations stay grounded in the public evidence. The
original harness hash was recoverable from repository history.

Exact name construction needed more than a text search: frame sizes, HTTP sizes,
reload suffixes and shared ping labels are constructed in helpers. The checker
expands those finite syntax-tree expressions without executing the harness.

Network resolution prevented the first PyYAML fetch. A temporary copy of the
existing cache allowed the required uv commands to run offline. Multi-file Pyink
waited without completing; single-file invocations completed. Formatting exposed
a quote-sensitive mutation in the rename test; replacing the literal text rather
than its quote delimiters preserves the test after formatting.

Implementation checks passed. Independent review and the checkpoint are left to
the orchestrator, as the brief requires.

## 2026-09-26T18:05:49-07:00

Applied the orchestrator's five decisions from the independent Codex review.
The real HTTP check exposed the formatted-string conversion gap; tests now exercise
that expression and both malformed-disposition reproductions. The original a1
identity record confirmed the basis for CF-2's link observation. Review findings
and their dispositions are recorded in the evidence; no second review was run.
