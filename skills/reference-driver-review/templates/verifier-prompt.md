<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
Fill-in prompt: substitute every angle-bracket placeholder before delegation.
-->

# Format 2 review verification prompt

**Terms:** assessments judge differences; verdicts judge support; bases track semantic evidence
freshness. See [the glossary](../../../GLOSSARY.md).

Independently verify <review> in <root>; you did not author it and do not edit it.
Load `reference-driver-review`, `peripheral-spec`, `spec-format` and `spec-verifier`.
Read <impl-checkout> and <ref-checkout> at their respective repos entries' immutable commits.
License evidence must fit the root. Inspect file SPDX lines and confirm notices/license files
that resolve cannot prove. Inspect reference choice and hardware revision applicability first.

Use the pinned interpreter `<python>` and sibling `<spec.py>`:

```bash
<python> <spec.py> check <root> --require-license
<python> <spec.py> resolve <review> --root <root> --repo impl=<impl-checkout> --repo ref=<ref-checkout>
<python> <spec.py> show <review> --root <root> --repo impl=<impl-checkout> --repo ref=<ref-checkout>
<python> <spec.py> inventory <register-spec> --root <register-root> --repo linux=<ref-checkout> --pin linux --headers <header> --strict
<python> <spec.py> status <root> --json
```

Repeat bindings for all entries and resolve every overlay against its own resources.
`--docs-dir DIR` supplies named document bytes (`DIR/NAME`). Inspect skips, not only exit 0.
Inventory needs a companion with register payloads, not the review itself; the tested reference
companion is SF2-7's peripheral fixture. Real comparisons need both sides' companions. Unknown
header expressions, mismatches and unexplained omissions are findings, never an inventory pass.

Read the paired files in full once, then check each finding's claim, both-side anchors,
category, assessment, consequence and resolution. Verify correspondence pairs name actual
counterparts; repeat negative/global searches (implementation for missing, reference for extra).
Recompute counts. Reject padded ranges, wrong symbols, guard/helper anchors instead of performing
statements, wrong-revision comparisons and claimed divergences that do not exist. Blindly
re-derive about 10% of anchors before reading claims, seeded by review hash; record the sample.

A bug's settled_by documents must apply and actually settle it; a self-evident reason must
stand without the reference. Benign requires justification; suspects need hardware probes on
the generated list; ref-issue must explain why the reference should not be followed. A
requirement label does not earn an assessment. Check precise document locators and note unavailable
bytes. Search for contrary evidence. Review coverage for constants, sequences/timing,
interrupts/DMA, error/recovery, power and errata: every exclusion needs a reason and every
zero-finding comparison says what was read. Account for unmapped routines. Flag excessive quoting.

Return a full report and proposed `<root>/resources/<driver>-review.verify.yaml` via
spec-verifier, keyed by fact ids with bases/upstream from status JSON, contrary_evidence,
citation_precision and all five summary counts. A PASS verdict can validate a suspect finding:
it means the reported uncertainty and evidence are accurate, not that hardware behavior passed.
Retain GAP/UNVERIFIABLE/ADJUDICATE as needed. The orchestrator coordinates a second independent
reader for critical facts, installs the record and runs the verification gate. List blockers by
fact id, path/lines and reason, with FAIL corrections. Do not edit the review. Existing format 1
work uses the unchanged verifier prompt in [FORMAT-1.md](../FORMAT-1.md).
