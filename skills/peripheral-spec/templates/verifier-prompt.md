<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
Fill-in prompt: substitute every angle-bracket placeholder before delegation.
-->

# Peripheral verification prompt

**Terms:** verdicts judge evidence records; sub-keys identify independently supported fields or
steps; a basis hash tracks semantic dependencies. See [the glossary](../../../docs/GLOSSARY.md).

Independently verify <spec> in <root>. You did not author it. Load `peripheral-spec`,
`spec-format` and `spec-verifier`; use their verification procedure. Read source bytes at each
`resources.repos[].commit`, not checkout HEAD. The `linux` binding is <source-checkout>;
additional source/target bindings: <additional bindings>. Resolve license lines, and read
notices/license files for every `license_from` confirmation the resolver cannot prove.

Run `hwspecs --version` first, then run:

```bash
hwspecs check <root> --require-license
hwspecs resolve <spec> --root <root> --repo linux=<source-checkout>
hwspecs inventory <spec> --root <root> --repo linux=<source-checkout> --pin linux --headers <header> --strict
hwspecs show <spec> --root <root> --repo linux=<source-checkout>
hwspecs status <root> --json --no-fail-on-pending
```

Repeat bindings for all cited entries; add document bytes via `--docs-dir DIR` (`DIR/NAME`).
Inspect resolution/skipped counts, not just exit status. Strict omissions, mismatches or unknown
header expressions are findings unless explicitly resolved or recorded as a limitation; a
limited inventory is never called a pass. A gate error is fixed by placement or evidence,
never by relabeling licenses.

Read the main source files in full once, then judge every fact and supported child. Check
register offset/width/access/reset and fields against definitions and accessors, steps against
performing statements/call sites, ordering against documents or attributed comments, layouts
against structs. Recompute counts and repeat every scoped absence/global search. Reject padded
ranges, wrong symbols and plausible lines that do not support the claim. Re-derive roughly 10%
of anchors blind before reading the claims, seeded by the spec hash, and record the sample.

A field whose cited source gives a value table or bit assignments, with neither values nor a
`todo` saying they were left out, is a FAIL; so is a property (access, reset, value) that
disagrees with the source. A layout field whose `bits`, `byteOrder` or `bitNumbering` disagrees
with the cited document is a FAIL. A wait, poll or handshake step with neither a bound nor a
`todo` is a FAIL; so is a step whose `op`, `target`, `value`, `until` or `timeout` disagrees
with the cited source, and a quantity whose unit or levels (tolerance included) disagree with
the document. A fact whose only support is a pinned, machine-readable source its readers may use under
their root's license (D31, D32) is a duplicate and a FAIL; the `correction` strips it to what
the source lacks. Driver-code readings and cost-saving summaries are not duplicates.

Check all required subject areas and omissions: databook register organization including
untouched registers, identity/revision, prerequisites, init/error/power/teardown, layouts,
interrupts/DMA, sub-protocols, target integration, gotchas and questions. Test `requirement`:
hw-required needs an applicable document, comment-explained needs attributed comment support,
as-implemented is code observation. Every code-only hardware assumption has an observable TODO;
generated hardware and open-question lists must represent the records. Spot-check locators
against obtainable documents; name every unavailable source. Search for contrary evidence,
including limitations and revision mismatches. Read the notes that govern each cited value,
wherever they appear: table footnotes, exception rows, and clauses for another actor or type.
A dropped condition or a contradicted exclusivity is FAIL. A true claim that omits a sibling
rule is PASS with `contrary_evidence: found`; its `note` names the omission and proposes text.
A zero-finding result must say how coverage was earned.

Return a full report plus proposed `<root>/resources/<device>.verify.yaml` following
spec-verifier. Key verdicts by fact id and `fact-id.sub-id` for fields/steps with independent
support; otherwise the parent covers them. Take basis/upstream from status JSON. State
contrary_evidence, citation_precision, all five summary counts and required verdict fields.
Do not manufacture a PASS from a mechanically valid anchor; retain GAP, UNVERIFIABLE and
ADJUDICATE as appropriate. The orchestrator coordinates a fresh second reader for critical facts
and installs the record, then runs the verification gate. Do not edit the spec. Report blockers
by fact/sub-key, cited path/lines and reason, with corrections for FAILs.
