---
name: reference-driver-review
description: >-
  Review a driver against a reference implementation of the same hardware. Produce format 2
  findings with structured evidence on both sides at immutable commits, correspondence and
  coverage records, and assessments distinct from verification verdicts. Defaults to the
  current driver; finds the reference through board-expert or a structured user decision.
  Output is a review, never driver code. Uses the spec-format commands and spec-verifier.
---

<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Driver review against a reference implementation

Produce one `kind: review` YAML report per driver. Compare an implementation with an applicable
reference, citing exact source lines on both sides. The output records differences and their
consequences, plus what was compared and what remains open. To produce a programming spec,
use `peripheral-spec`.

## Terms

- **Implementation / reference**: the driver being reviewed / the other driver used as evidence.
- **Role**: a repos entry's `role: impl` or `ref`; both use `class: src` anchors.
- **Finding / assessment**: a difference record / its judgment (`bug`, `suspect`, `benign`,
  `ref-issue`), separate from the verifier's verdict about whether the finding is supported.
- **Correspondence / coverage**: paired routines or files / which areas were compared and why.
- **Pin / root / basis hash**: exact source commit / spec directory and license policy /
  fingerprint of a fact and its declared dependencies used for verification freshness.

See the [glossary](../../GLOSSARY.md), [spec-format](../spec-format/SKILL.md) and the `review`
branch and payload definitions in the [schema](../spec-format/schema/spec.schema.json).

## Intake and finding the reference

Default to the driver in the current directory; find its enclosing repository and current
commit. If there are multiple drivers, ask which. Identify the peripheral, silicon IP/vendor,
SoC/board and revision from compatible strings, register names, bindings, version checks and
quirk tables. Do not choose a reference until hardware applicability is clear.

Ask a matching board expert for repository URL, revision, paths, licenses and applicability,
without source reading yet. If none knows, ask the user for a resolvable reference in a
structured decision batch following `board-expert/QUESTIONS.md`. A source-release description
is sufficient if you can locate it; ask when variant or instance ambiguity remains. Check out
the reference outside the implementation tree, in a cache or scratch directory, and record how
it was chosen and why it applies. Never copy reference files into the implementation tree.

**License posture:** a review is a critique with citations, not an instruction to paste code.
Quote only a few lines when the exact expression matters. Fixes state hardware facts and use
code permitted by the implementation's license. For publication in a spec repository, apply
[peripheral-spec's placement rule](../peripheral-spec/SKILL.md#where-the-spec-goes-which-repositorys-license-fits)
and the destination marker's gate to both roles and all transitive evidence. A GPL reference
cannot enter a docs or permissive root through a role change. Confirm every cited file's
license at the pin and retain notices; do not relabel sources to pass the gate.

## The reference is evidence

A reference can be wrong, stale or for another revision. A difference alone does not establish
a bug. Compare applicability on both sides before making any finding depend on the match.
Public datasheets and standards settle a difference when they can; state their exact locators
and applicability. Public roots never cite confidential or NDA documents. A proxy document's
limits are part of the finding. Where no document settles it, record the uncertainty and a
probe rather than declaring the implementation wrong.

## Records instead of anchor aliases

Use `<driver>-review.spec.yaml` with SPDX comments matching its destination, `format: 2`,
`kind: review`, `id`, `name`, `resources` and `facts`. Each source entry has a distinct name,
HTTPS URL, full lowercase `commit`, license, closed `files` list with `license_from`, and
`role: impl` or `ref`. Different file licenses need separate entries, even from the same tree.
Both sides use `support: [{class: src, anchors: [...]}]`; the anchor's `repo` selects the entry.
There are no implementation/reference citation classes or line-based pin declarations.

Read [peripheral-spec's support rules](../peripheral-spec/SKILL.md#documents-first-structured-support-always):
repo-relative paths, inclusive lines, nearby symbols and tight performing statements; negative
claims use a scoped `search` anchor. Resolver search checks only scope existence; a verifier
must repeat the search. Every search scope must be listed as a path in the repo entry's
`files`, including a directory scope with its trailing slash (`dir/`).
Attribute code comments with `comment: true`. Documents live in
`resources.documents`; support names their class, name and precise `at` locators. Use canonical
citation URLs and separate retrieval URLs, hashes and page counts. Never fabricate citations.

Every finding in `section: findings` has a claim and `data.finding`:

| Field | Meaning |
| --- | --- |
| `category` | `differs` (both do it differently), `missing` (reference only), `extra` (implementation only) |
| `assessment` | `bug`, `suspect`, `benign`, `ref-issue` |
| `consequence` | What fails or why the difference is harmless |
| `settled_by` | Document-class support that settles the judgment, when available |
| `self_evident`, `reason` | Alternative bug justification: `self_evident: true` and the explicit reason |
| `resolution` | `status: open`, `fixed` with full `commit`, or `wontfix` with `reason` |

A `bug` needs `settled_by` or a self-evident defect (wrong ack bit, offset used as a mask),
with a reason that stands without the reference. A `suspect` goes on the generated hardware
list with what to probe in a hardware TODO. A `benign` needs a stated justification;
"probably fine" remains suspect. A `ref-issue` records why following the reference would be
wrong (for example, it serves another revision). The verifier's PASS/FAIL evaluates whether
the assessment and evidence are earned; it is not the finding's assessment.

Cite both sides for every finding. For `missing`, the implementation side **must** include a
`search` anchor over the absence's scope, while the reference cites the performing lines.
For `extra`, the checker requires some ref-side anchor, without requiring it to be a search
anchor; the verifier must still establish the claimed absence on the reference side.
`requirement` describes behavior as in peripheral-spec; it never substitutes for `assessment`.

## Required review content

- **Notice and identity**: the generated notice names pins; put reference choice, applicability,
  evidence policy and revision-match risk in `notes` and supported `identity` facts.
- **Correspondence**: `section: correspondence`, `data.pair: {impl: [anchors], ref: [anchors]}`.
  Pair anchors count as support and freshness dependencies; pair-only facts need no artificial
  TODO. Account for every entry point; unmapped entries become findings or explicit scope limits.
- **Coverage**: `section: coverage`, `data.coverage: {area, compared, read, reason}`.
  State what was read even for zero-finding areas. Cover constants, sequencing/timing,
  interrupts, DMA/layouts, error/recovery, power, errata and sub-protocols, or give reasons
  for exclusions. Use source search evidence for a coverage claim, not an unrelated manual.
- **Findings**: list bugs first, suspects second, then other assessments. Keep stable ids.
- **Agreements**: supported `agreements` facts for meaningful independent agreement.
- **Questions**: `open-questions` gap facts with TODOs for what neither tree nor document settles.
  Use `areas` for per-area confidence. Hardware/open-question lists and reading views are
  generated, not edited. Empty lists need an explanation of how coverage earned them.

## How to run it

The orchestrator resolves intake and starts a review drafter using
[the review prompt](templates/review-subagent-prompt.md). First obtain the correspondence map;
then investigators compare paired slices of both trees: constants, sequences, interrupts/DMA,
error paths and quirks. Give each the map. Run constants twice independently; resolve every
one-sided result against both headers before drafting. Preserve returned record ids, citations
and resource names, resolving collisions explicitly. No drafter invents anchors. A small driver
can be read in one context.

### Check, verify, land

Use the hash-pinned spec-format environment. `<python>` is its interpreter, `<spec.py>` the
sibling script, `<root>` the review root, `<review>` the file. `<impl-checkout>` binds `impl`
and `<ref-checkout>` binds `ref`; use the actual names, repeating bindings for all cited entries.
Commands are tested against SF2-7's review fixture and overlay. The fixture's implementation is
illustrative: the command test creates stand-in bytes to resolve it, not a hardware validation.

```bash
<python> <spec.py> check <root> --require-license
<python> <spec.py> resolve <review> --root <root> --repo impl=<impl-checkout> --repo ref=<ref-checkout>
<python> <spec.py> show <review> --root <root> --repo impl=<impl-checkout> --repo ref=<ref-checkout>
```

Add `--docs-dir DIR` when document bytes are available as `DIR/NAME`. Inspect skipped counts
before claiming all anchors resolved. Check every overlay file independently too: citations
resolve against its own resources. Mechanical validity never proves a finding.

Inventory reads register payloads, which a review cannot carry; finding prose and pair anchors
are not register coverage. For a header comparison, maintain companion peripheral/facts files
with the compared register/field records, and run inventory on each side's companion. In the
fixture recipe, `<register-spec>` is SF2-7's peripheral fixture, `<register-root>` its root and
`<header>` its synthetic C header; `linux` binds the reference checkout. A real implementation
companion uses its own pin and header instead.

```bash
<python> <spec.py> inventory <register-spec> --root <register-root> --repo linux=<ref-checkout> --pin linux --headers <header> --strict
```

Unexplained omissions and mismatches need resolution. Unknown expressions fail with reasons;
record limitations instead of claiming an exact inventory passed. The companion check does not
replace a correspondence and coverage review of the implementation.

A fresh verifier uses [the verifier prompt](templates/verifier-prompt.md) and
[spec-verifier](../spec-verifier/SKILL.md). It reads paired files in full, checks every finding
on both sides, repeats absences, recomputes counts, tests applicability/correspondence and
justification, and independently re-derives about 10% of anchors before reading the claims.
Critical facts need a second independent reader coordinated by the orchestrator.
It writes `<root>/resources/<driver>-review.verify.yaml`, keyed by fact id and basis hash.
An author does not insert an empty record. After fixes and re-verification, publish with the
appropriate verification gate and link the generated reading view.

### Lifecycle

When fixes land, set addressed findings' `resolution: {status: fixed, commit: <full hash>}`,
then inspect and rewrite the implementation pin:

```bash
<python> <spec.py> drift <new-commit> <review> --pin impl --root <root> --repo impl=<impl-checkout> --repo ref=<ref-checkout>
<python> <spec.py> drift <new-commit> <review> --pin impl --rewrite --root <root> --repo impl=<impl-checkout> --repo ref=<ref-checkout>
```

Drift marks changed anchors stale and moves unique relocated ranges. Re-read before clearing
`stale`; changed search scopes or operational errors refuse rewriting. Update per-fact verdicts
through spec-verifier; whole-file hashes do not establish freshness. A reference revision
change merits a new applicability and comparison pass, not automatic renewal of old findings.

## Format 1 (retained until SF2-12)

Existing Markdown reviews use [FORMAT-1.md](FORMAT-1.md) and its unchanged appended review and
verifier prompts. It also points to peripheral-spec's format 1 grammar. Roots without `format`,
or with `format: 1`, select that procedure; invalid markers are findings. Never mix formats or
write new format 1 reviews. The legacy checkers stay unchanged until SF2-12.
