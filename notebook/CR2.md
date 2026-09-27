<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR2: verification-history backfill

**Terms:** a reading is one verifier's pass; its basis identifies the text and
inputs. See the [glossary](../GLOSSARY.md). Conclusions and decisions are in
[the evidence](../evidence/CR2.md); verdict status is in
[the index](../evals/e1000/status.yaml).

## 2026-09-26T18:28:20-07:00

Recovered reading identities from verification frontmatter without opening spec
bodies. Several records describe drafts under the same revision number; the
landed hash alone would have assigned failed verdicts to different text. SR-7's
combined reading similarly required keeping the actual revision-6 hash while
identifying both revisions' changes in its scope.

Section splitting initially made the YAML diff obscure CR1's unchanged records.
Preserving the original text and using separate anchors for the new metadata made
the change additive. Multi-file formatting waited after formatting its inputs;
single-file invocations exited cleanly. The checker tests now exercise draft
identity mismatches, missing history and section slices, and broken chain links.

No spec was edited or re-verified. Independent review and checkpoint remain with
the orchestrator.

## 2026-09-26T18:59:32-07:00

Applied the orchestrator's five decisions from the independent read-only review.
The dependency cross-check lists were reconstructions rather than recorded
complete declarations; replaced them with unknown dependencies and documented the
remaining recoverable metadata in the public provenance extract. Added reverse
applied-item checks and optional-field regressions. Review dispositions are in
the evidence; no second independent review was run.
