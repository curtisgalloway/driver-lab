---
name: spec-verifier
description: >-
  Verify hardware specs against their cited evidence in fresh reader contexts and write
  separate verification records. Use to verify, re-verify or audit a spec, after a spec or
  source changes, or when its checker reports stale or missing verdicts. Format 2 uses
  fact-keyed YAML records and delta verification.
  Orchestrator only: readers compare evidence; the orchestrator coordinates and checks.
---

<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Spec verifier

## Terms

- **Fact / fact id** — one structured claim in a YAML spec / its stable identifier.
- **Support / document class** — its declared evidence / `databook`, `standard` or `doc`.
- **Basis / upstream map** — the fingerprint of a fact and its declared dependencies / the
  bases of facts in other roots it rests on, used to distinguish upstream changes.
- **Freshness / verdict** — whether the recorded basis still matches / what the reader found:
  `PASS`, `FAIL`, `UNVERIFIABLE`, `GAP` or `ADJUDICATE`. A current verdict need not be PASS.
- **Orchestrator / verifier / second reader** — the coordinating agent / a fresh agent reading
  sources / another independent reader of a critical fact. A harness is the agent's application.
- **Delta verification** — renewing only the verdicts that need it.
- **Contrary evidence / citation precision** — evidence that might limit or contradict a
  claim / whether its citation identifies the evidence for the whole claim.

See the [glossary](../../GLOSSARY.md), sibling [format contract](../spec-format/SKILL.md)
and [record schema](../spec-format/schema/verify.schema.json).

## Require format 2

The root marker must declare `format: 2`; specs and records are YAML. A missing, invalid or
unsupported format marker is a finding. Convert the root before verifying its specs.

### Board specs

Board, SoC, chip, IP and overlay files use the same format 2 procedure. Each file gets its
own record, overlays included. The record's `spec` is the file's `id`, or its `overlays` id.

### Peripheral specs and reviews

Format 2 peripheral specs and reviews use this same procedure. Verdicts cover facts,
not individual anchors. Register fields and sequence steps with their own support get
`fact-id.sub-id` keys (D16); otherwise the parent verdict covers them. Their bases include
the effective requirement and parent identifying data. Finding assessments are separate from
verifier verdicts. Correspondence pair anchors count as support. Read the authoring procedures
in [peripheral-spec](../peripheral-spec/SKILL.md) and
[reference-driver-review](../reference-driver-review/SKILL.md).

## Coordinate a format 2 reading

The orchestrator selects work, spawns fresh readers, assembles their YAML and runs the gate.
It never reads sources or edits the spec in this role. Readers may write proposed records
in separate scratch directories; the orchestrator alone installs them in the root. Give
readers the spec, declared dependencies, this skill and access to sources at the pins.
Do not give them the author's reasoning, this conversation or earlier verdicts. For delta
work give selected fact ids and changed upstream references, without previous conclusions.

Commands use repository-relative paths; when installed, locate the sibling
`spec-format/scripts/spec.py`. Use Python with spec-format's hash-pinned requirements
installed. Run `spec.py --skill` to confirm availability. `check` and `status` exist from
SF2-3; `resolve` and `show` require SF2-6. Report a missing prerequisite rather than
guessing at an unchecked result.

1. **Check structure and licenses.** Supply the selected root and every dependency root
   needed by composition or fact references as context:

   ```bash
   python3 skills/spec-format/scripts/spec.py check <root> --context-root <dependency-root> --require-license
   python3 skills/spec-format/scripts/spec.py status <root> --context-root <dependency-root> --require-license --json
   python3 skills/spec-format/scripts/spec.py status <root> --context-root <dependency-root> --require-license --stale --json
   ```

   Repeat `--context-root` for more dependencies; omit it when none are needed. A context
   root's own findings print as warnings, but a reference into an untrusted context still
   fails. A current FAIL is an expected error until an author fixes it. Correct schema,
   reference, citation and license errors before evidence reading; report them to the
   author, never edit the spec here. Repair a bad record that makes a root untrusted first.

2. **Select the delta from status.** JSON `specs[].facts[]` supplies `key`, `ref`, `kind`,
   `status`, `verdict`, `carried`, `basis`, `recorded`, `upstream`, `changed`, `reason` and
   `second_reader`. Use `key` as the verdict key and full `ref` to identify a fact across
   roots. `record` names an existing record (null if absent); `state` reports whether it
   loaded. Status exits 1 on a check error but still prints its report; inspect `findings`.

   | Status | Work |
   | --- | --- |
   | `current` | Preserve the verdict, basis, date and readers; no new primary reading. |
   | `stale` | A fresh verifier reads the fact and its dependencies at current identities. |
   | `unverified` | A fresh verifier reads it for the first recorded verdict. |
   | `unknown` | Read `reason` and fix the unresolved dependency or rejected citation first. A reader can investigate, but a null basis cannot produce a current verdict. Re-run status after correction. |
   | `upstream-stale` | If the previous verdict was PASS, read changes to the upstream facts named in `changed` and check whether the dependent claim still follows; unchanged local sources need no repeat reading. If the previous verdict was anything other than PASS, require a full fresh reading of the claim and all its evidence and dependencies. Renew only after the required reading. |

   `--stale` includes every non-current fact **and current critical facts missing a second
   reader**. For the latter, launch only the missing reader. Also inspect the unfiltered
   report for current FAIL and ADJUDICATE: they need correction or user adjudication even
   when absent from the stale list. Preserve other current verdicts unchanged.

3. **Primary reading.** The verifier performs the standing evidence checks below on each
   selected supported fact. For an upstream-only change with a previous PASS, apply them to
   the changed evidence and its effect on the dependent claim; every other previous verdict
   requires the full reading. A gap follows GAP below. Check instances and
   variants by their own ids and support too. Read referenced facts and named assumptions;
   note any condition on which the conclusion depends.

4. **Second reader (D14).** The **orchestrator**, never the verifier, spawns a different
   fresh reader for each `critical: true` fact lacking a reading at the current basis.
   One reader may cover several critical facts in a file. Give the same evidence brief,
   without the first verdict or reasoning. Another session of the same model is allowed;
   it must be another reader. Identify each by agent/model/harness and a distinct session
   label. The verifier's own reading never counts, even under another spelling: the checker
   compares identities after Unicode NFC normalization, whitespace collapse and case folding.
   Do not evade the comparison with aliases.

   Store the second result in the fact's `readers`, each `{verifier, verdict, date, note}`
   (`date` and `note` are optional in the schema; include them for an audit trail). Omit
   `readers` until someone runs; `readers: []` is invalid. Never reuse a stale second reading
   for a renewed basis. For an upstream-only critical fact, the second reader independently
   checks the upstream changes too, using a full reading if the previous verdict was not
   PASS. Disagreement follows ADJUDICATE below.

5. **Assemble and gate.** Install one record per file, preserve verdicts outside the delta,
   count all five summary buckets, and re-run status before copying new bases. If inputs
   changed during reading, do not stamp a verdict with a newer basis: re-read the affected
   delta. Report corrections for the author to apply, then re-run on affected facts within
   the campaign's recorded stop rules.

## Standing evidence checks for the verifier

- **Materialize cited bytes.** Use full `resources.repos` commits, `resources.documents`
  identities and each document's canonical `url` and `retrieval` entries. Retrieval methods
  are descriptive text, never commands to execute. Record sources and fetch failures. Match
  `sha256` when document bytes are available; a blocked fetch does not authorize an unpinned
  replacement.
- **Resolve and read.** Machine-check anchors at the pin, SPDX-line license evidence and
  available document hashes; then read each fact beside its cited source lines:

  ```bash
  python3 skills/spec-format/scripts/spec.py resolve <spec.spec.yaml> --root <root> --repo <name>=<checkout> --docs-dir <document-dir>
  python3 skills/spec-format/scripts/spec.py show <spec.spec.yaml> --root <root> --repo <name>=<checkout> --docs-dir <document-dir>
  ```

  Repeat `--repo` for named repos; unbound repos are fetched over HTTPS. `--docs-dir` supplies
  files as `<document-dir>/<document-name>`; omit it when unavailable and state which hashes
  were not checked. `show` displays source evidence; read document text separately. Inspect
  warnings and skipped counts: a fully skipped resolution can exit 0 and establishes no
  anchor. Repeat every `search` anchor's search; resolution checks scope existence only.
  Resolution alone never earns PASS. Only `license_from: spdx-line` evidence is
  machine-checked. For `notice` or `license-file`, open the cited notice or license file at
  the pin, confirm it applies to the cited source file, and compare it with the declared
  license. Record the comparison; a mismatch is FAIL, and inaccessible evidence is
  UNVERIFIABLE rather than an assumed match.
- **Compare the whole claim.** Check values, units, address spaces, ordering, scope and
  conditions. `comment: true` attributes a comment, not established behavior. Emulated
  support is judged against the cited model/version/run observations, not model source or
  mechanism. Hardware support is judged against the measurement and stated board, method,
  date and conditions. Extension support follows the root's rules; it never replaces core
  citations.
- **Search for contrary evidence every time.** Read adjacent qualifications, alternative
  paths/configurations, errata and sources that could show the claim too broad. Describe the
  search scope and result in `note`; set `contrary_evidence` to `none-found`, `found` or
  `not-checked`. `none-found` means the stated search found none, not that none exists.
  `found` names conflicting evidence and its effect on the verdict. `not-checked` states
  the obstacle; never imply the step ran. This is a standing step for delta readings too.
- **Grade citation precision separately.** Set `citation_precision: exact` when the anchors
  or locators identify the evidence for the whole claim closely enough to repeat the reading;
  use `imprecise` for overly broad or incomplete citations and explain how to narrow them.
  A missing locator, wrong passage or nonexistent anchor is FAIL, not merely imprecise.
  `databook` needs section/page/pages/table/figure/clause; `standard` does too when its
  document has `pages`; unpaged standards and `doc` may use headings. Shape and bounds are
  mechanical; the reader checks that the locator is right. An otherwise supported claim
  may PASS with an imprecise citation, with the precision finding reported separately.
- **Read versus derived (D3).** Read-class support may jointly support a claim, but a derived
  conclusion needs its own `inference` fact with `premises` and `derivation`. A derivation
  hidden in a `doc` claim is FAIL with a proposed split. Inference stands alone in `support`.
  Check premises, derivation and degree of certainty. If a verdict needs an undeclared fact
  or assumption, request a declared dependency (`relates`, a premise reference or `assumes`)
  before accepting it. A record note cannot make the basis track an undeclared dependency.
- **Source code about hardware needs documentation.** A `src` fact can
  state what code defines or does. A claim about where hardware is or what it requires needs
  document-class support too; its absence is FAIL on class. A claim that a product runs a
  particular build cannot be proved by code alone: propose a separate inference with explicit
  premises, assumptions, scoped certainty and a TODO, rather than relabeling it as definite.
- **Check every TODO method.** A TODO alongside support does not erase the supported part
  or turn it into GAP. Read `todo.check`, `todo.text` and optional `todo.method`: can the
  method observe the remaining question under the stated conditions? Reading an EL3-only
  register from EL1 cannot settle its value; a few patch words cannot identify a whole
  shipped build. An impossible method or a trailing TODO used to cover unsupported assertions
  is FAIL with a proposed correction. A legitimate outstanding hardware check may coexist
  with PASS on a conditional inference; PASS does not mean the TODO was performed.

## Verdicts and disagreements

| Verdict | Use |
| --- | --- |
| PASS | Evidence supports the claim as stated and classified, with scope and named assumptions. Explain the comparison in `note`. |
| FAIL | A discrepancy, wrong class, missing/wrong locator or invalid TODO method. Include `correction` proposing a fix; never edit the spec. |
| UNVERIFIABLE | Evidence could not be read (blocked, partial or truncated fetch, inaccessible measurement). State what was not established. A citation shown nonexistent at the pin is FAIL. |
| GAP | Only a fact with **no `support`** and a TODO. Check whether the TODO can settle it; explain deficiencies in `note` for the author. Record `citation_precision: imprecise` because there is no citation and `contrary_evidence: not-checked` because there is no supported value to compare, explaining both limits in `note`. Never GAP a supported fact, instance or variant. The checker requires a gap's verdict to be GAP. |
| ADJUDICATE | Independent readings disagree. Store both in `readings`, each `{verifier, verdict, reasoning}`, and actual second readings in `readers`. Count only in `summary.adjudicate`, never PASS/FAIL merely because of disagreement. |

**The user adjudicates.** Present both readings and disputed evidence. Do not vote or pick
one yourself. Leave `adjudication` absent while unsettled. On the user's decision, retain
`readings`, add `adjudication: {decision, by, date, rule}`, set PASS or FAIL, and include
`correction` only for FAIL. A finding of excessive definiteness is FAIL on definiteness.
Retain dissenting history in `readings`; the checker requires `readers` entries to agree
with a settled verdict, so obtain an updated second reading rather than rewrite its earlier
conclusion as agreement.

A current ADJUDICATE is an **error under `--require-verified pr`** and a warning under `main`
(user decision, 2026-10-10), so a pull request cannot land one; the user settles it first.
Current UNVERIFIABLE and GAP may pass the mechanical gate too: report those limits.

## Write the YAML record

Write `<root>/resources/<name>.verify.yaml`, with `<name>` the spec file's basename without
`.spec.yaml`, even for a nested spec or overlay. Never put it in a nested `resources/`,
share it between files, or leave format 1 records in a format 2 root.

- `format: 2`; `spec`: spec id (overlay target id); `spec_file`: root-relative path;
  `canonical: fact-v1`; `spec_sha256`: SHA-256 of the exact spec bytes at assembly, for
  information only. Compute that file digest normally; it does not decide freshness.
- `sources`: everything consulted, with `name`, `commit` for a repository, `url` and `sha256`
  for document bytes, `fetch` and useful `note`. Each source needs `commit` or `sha256` in
  this schema. For inaccessible evidence use its declared identity and state bytes were not
  confirmed; never invent a hash. Evidence with neither identity cannot be encoded as a
  source: report the schema limitation and request an identified resource. For a run extract
  without such identity, name it in the verdict note and report the missing source identity.
- `verdicts`: keyed by **bare fact id**, including instance and variant ids. Copy a new
  verdict's `basis` from that fact's **`spec.py status --json`** row, and its `upstream` map
  when nonempty; omit `{}` because an empty map is invalid. Null `basis` or `upstream` means
  unknown: repair the cause and rerun status. **Never compute a basis by hand**, use
  `recorded` as today's basis, or update hashes without a reading.
- Each verdict has `verdict`, ISO `date`, `verifier` (agent, model, harness, reader identity),
  `note`, `contrary_evidence`, `citation_precision` and any required `readers`, `correction`,
  `readings` or `adjudication`. No top-level `verified` or `verifier` exists in format 2.
  Cite evidence in notes; do not paste source code into records.
- `summary` has exactly `pass`, `fail`, `unverifiable`, `gap`, `adjudicate`, all present,
  even when zero. Count every stored verdict, preserved verdicts outside the delta included.

### Carrying a format 1 verdict (D10)

Carry only when claim text is byte-identical and a fresh conversion-fidelity check confirms
the same citations and locators, nothing added. Split claims, added search premises and
fidelity failures need fresh readings. Copy what the old record said, identify its
`carried_from: {repo, commit, path, key, format: 1}`, and use the converted fact's basis from
status. Retain original dates, reader identities and reasoning; do not imply a new reading.
**Omit `contrary_evidence` and `citation_precision`** for format 1 carries, as the schema
requires. Never invent readers that the old record did not document; a carried critical
fact still needs its independent second reader. A later fresh primary reading replaces the
carry: remove `carried_from` and supply both new fields. Status reports `carried: true`.

## Gate and report

```bash
python3 skills/spec-format/scripts/spec.py check <root> --context-root <dependency-root> --require-license --require-verified pr
python3 skills/spec-format/scripts/spec.py check <root> --context-root <dependency-root> --require-license --require-verified main
```

Use `pr` for a proposed change: stale, upstream-stale, unverified, unknown and a current
critical fact without a second reader are errors. `main` differs only in allowing
upstream-stale as a warning (D19); local stale still fails. Current FAIL always fails.
Repeat status to check the delta and report the gate, five summary counts, precision and
contrary-evidence limits, TODOs, each FAIL's correction and unsettled ADJUDICATE. Commit or
stage records only when the project calls for it; do not push without authorization.

## Complete worked record

The [example root](examples/format-2/board-specs.yaml) describes a **synthetic** Widget,
not real hardware. Its [spec](examples/format-2/widget.spec.yaml) cites a local
[synthetic manual](examples/format-2/resources/widget-trm.txt). Copy this record verbatim to
`<example-root>/resources/widget.verify.yaml` in scratch and run
`check <example-root> --require-license --require-verified pr`. The reset count is marked
critical only to demonstrate the `readers` field, not because real bring-up depends on it.
The reset-budget inference combines two separately documented phases; no single section
states their total. The test in
`skills/spec-format/tests/test_verifier_example.py` copies this exact fenced record into a
fixture root and requires zero errors. Bases came from `status --json`; changing example
facts or resource identities requires a new reading and new bases.

```yaml
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
format: 2
spec: widget
spec_file: widget.spec.yaml
spec_sha256: f746cb36f4afdff59cd9ac22c347e2227c4feff3df83ab14a8801f3e3985a9dd
canonical: fact-v1
sources:
  - name: widget-trm.txt
    url: https://example.invalid/widget-trm.txt
    sha256: 8e73c19aecb71c5e4010de85849911c900a6d041958b16a9146d680338bc815f
    fetch: ok
    note: Synthetic local manual, not a fetched vendor document.
summary: {pass: 3, fail: 0, unverifiable: 0, gap: 1, adjudicate: 0}
verdicts:
  reset-cycles:
    basis: da96ce840be65a7a2619d7b2387576d048500e7bfaad946a01cadf50984e5548
    verdict: PASS
    date: 2026-10-09
    verifier: Synthetic primary reader, example model/harness, session A
    note: >-
      Section 1 on page 1 states 10 cycles. Read all three sections for qualifications
      and conflicting counts; none found. This establishes only the synthetic claim.
    contrary_evidence: none-found
    citation_precision: exact
    readers:
      - verifier: Synthetic second reader, example model/harness, session B
        verdict: PASS
        date: 2026-10-09
        note: Illustrative independent comparison with section 1's fixed count.
  settle-cycles:
    basis: 60302e04a786da6c85cf3935d1c637e1066af8a48385f6a92700b1e9e33edd0a
    verdict: PASS
    date: 2026-10-09
    verifier: Synthetic primary reader, example model/harness, session A
    note: >-
      Section 2 on page 1 states 4 more cycles immediately after reset, using the same
      clock without overlap. Read all three sections for qualifications or a different
      phase order; none found. This establishes only the synthetic claim.
    contrary_evidence: none-found
    citation_precision: exact
  reset-budget:
    basis: fb6d4fab15ca733423268329c3b10c7ae8c07a0e27e84163fdf0560598de1112
    verdict: PASS
    date: 2026-10-09
    verifier: Synthetic primary reader, example model/harness, session A
    note: >-
      The reset-cycles and settle-cycles premises give sequential phases of 10 and 4
      cycles on the same clock, with no overlap or intervening delay: 10 + 4 = 14.
      No section states that total. Read all three sections for contrary timing or
      ordering qualifications; none found. The TODO could measure the duration on a
      future physical implementation; it has not been performed and does not weaken
      the supported inference about this synthetic model.
    contrary_evidence: none-found
    citation_precision: exact
  power-on-state:
    basis: 91ab9398fa6ec9db9a0bb4fc7adc3e4791e35152810d3f9c96f10853e16f8e9e
    verdict: GAP
    date: 2026-10-09
    verifier: Synthetic primary reader, example model/harness, session A
    note: >-
      No support entry; the TODO can be settled by a future explicit definition.
      No authority is cited for a power-on value, so citation precision is imprecise
      and contrary evidence for such a value was not checked.
    contrary_evidence: not-checked
    citation_precision: imprecise
```

The reader identities and readings above are illustrative, not evidence that real reader
sessions ran. The fixture test establishes schema, freshness and gate behavior only.
