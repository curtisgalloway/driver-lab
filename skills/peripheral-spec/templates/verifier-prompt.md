<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
Fill-in prompt: substitute every angle-bracket placeholder before delegation.
-->

# Format 2 peripheral verification prompt

**Terms:** verdicts judge evidence records; sub-keys identify independently supported fields or
steps; a basis hash tracks semantic dependencies. See [the glossary](../../../GLOSSARY.md).

Independently verify <spec> in <root>. You did not author it. Load `peripheral-spec`,
`spec-format` and `spec-verifier`; use their format 2 procedure. Read source bytes at each
`resources.repos[].commit`, not checkout HEAD. The `linux` binding is <source-checkout>;
additional source/target bindings: <additional bindings>. Resolve license lines, and read
notices/license files for every `license_from` confirmation the resolver cannot prove.

Run with the hash-pinned interpreter `<python>` and sibling `<spec.py>`:

```bash
<python> <spec.py> check <root> --require-license
<python> <spec.py> resolve <spec> --root <root> --repo linux=<source-checkout>
<python> <spec.py> inventory <spec> --root <root> --repo linux=<source-checkout> --pin linux --headers <header> --strict
<python> <spec.py> show <spec> --root <root> --repo linux=<source-checkout>
<python> <spec.py> status <root> --json
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

Check all required subject areas and omissions: databook register organization including
untouched registers, identity/revision, prerequisites, init/error/power/teardown, layouts,
interrupts/DMA, sub-protocols, target integration, gotchas and questions. Test `requirement`:
hw-required needs an applicable document, comment-explained needs attributed comment support,
as-implemented is code observation. Every code-only hardware assumption has an observable TODO;
generated hardware and open-question lists must represent the records. Spot-check locators
against obtainable documents; name every unavailable source. Search for contrary evidence,
including limitations and revision mismatches. A zero-finding result must say how coverage was earned.

Return a full report plus proposed `<root>/resources/<device>.verify.yaml` following
spec-verifier. Key verdicts by fact id and `fact-id.sub-id` for fields/steps with independent
support; otherwise the parent covers them. Take basis/upstream from status JSON. State
contrary_evidence, citation_precision, all five summary counts and required verdict fields.
Do not manufacture a PASS from a mechanically valid anchor; retain GAP, UNVERIFIABLE and
ADJUDICATE as appropriate. The orchestrator coordinates a fresh second reader for critical facts
and installs the record, then runs the verification gate. Do not edit the spec. Report blockers
by fact/sub-key, cited path/lines and reason, with corrections for FAILs. Format 1 work uses
only the unchanged verifier template in [FORMAT-1.md](../FORMAT-1.md).
