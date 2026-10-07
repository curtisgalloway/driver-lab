<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS4: placement guidance, provenance template and format docs

**Terms:** the *placement rule* says which of the three public *spec repositories*
(`hardware-specs-gpl`, `hardware-specs-docs`, `hardware-specs-permissive`) a spec belongs in; a
*root marker*'s `accepts:` lists the licenses its specs' *pins* (named source trees at a commit)
may carry, and the *license gate* (`anchor_check.py --root`) enforces it. A *provenance
attestation* is the private record of how a clean-room spec was made. See the
[glossary](../GLOSSARY.md) and the [design's terms](../docs/LICENSE-SPLIT.md#terms).

Design: [LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md), revision 2026-10-05 (LS-R1 docs, LS-R7,
LS-R8, LS-R9's `spec-verifier` text, LS-R10). Plan:
[LS4](../docs/LICENSE-SPLIT-PLAN.md#ls4--guidance-provenance-template-why-this-exists-format-docs).
Notebook: [LS4](../notebook/LS4.md). Starting revision `b3a0440` (LS3's checkpoint, stacked on
LS2 `7092822`; neither merged); no pre-existing changes.

**Result: complete.** The format the LS1–LS3 tools check is now documented where authors and
verifiers read it, the "is it yours?" test is replaced by the placement rule and the design's
repo table, a private provenance template exists for clean-room specs, and the README opens with
why the project exists and what it is not for. Docs only: no script or test changed.

## What changed

- `skills/anchored-peripheral-spec/SKILL.md`: description and intro framed by license, not
  ownership; new section "Where the spec goes: which repository's license fits?" with the
  placement rule, the design's repo table verbatim (and that the repositories do not exist until
  LS5; check against the fixture roots meanwhile), and how to choose (two pins on one tree when
  its files carry different licenses); the anchor grammar gains named `[src:<pin>: …]` and
  `[tgt:<pin>: …]`, pin licenses, and a *Documents* bullet for the `docs:` registry and named
  `[doc:<name> p.N]` anchors; the check step shows `--repo NAME=PATH`, `--root`,
  `--require-license` and `--docs-dir` with the gate's rules; `--drift-pin`; `inventory_check.py`
  one tree per run; a quality-bar line.
- Its templates: the spec-writer prompt asks for licensed, named pins and the registry, and runs
  the gate; the verifier prompt runs the gate and `--docs-dir` and treats a `license gate:` error
  as a FAIL.
- `skills/board-expert/SPEC-FORMAT.md`: Terms entries; the root marker's license fields
  explained (SPDX, `accepts: []`, case, `GPL-2.0`/`GPL-2.0+` normalization, warnings and
  `--require-license` in both tools); new subsection "Peripheral specs in a licensed root"
  (named pins, the `docs:` registry and how it differs from `resources.docs`, the checks a spec
  repository runs, and the `<device>-spec.md` naming).
- `skills/board-spec-scaffold`: the marker template gains `license:`/`accepts:` placeholders; the
  root step mentions them.
- `skills/cleanroom-spec/templates/PROVENANCE.md` (new) and a SKILL.md step "The provenance
  attestation (private; fill it at every landing)", plus a quality-bar line.
- `skills/spec-verifier/SKILL.md`, anchored-spec procedure only: a checkout per named pin, the
  gate and `--docs-dir` when the spec lives in a licensed root, `inventory_check.py` per pin.
- `README.md`: "Why this exists and what it is not for" after the scope paragraph; the skill
  table row and the anchored-spec section framed by license. `GLOSSARY.md`: three rows.

## Acceptance

| Criterion | Evidence and result |
| --- | --- |
| Every command and field the docs show exists in LS1–LS3's code | Each was run against scratch specs (two pins on one tree, a document with a known hash) and the three fixture roots: `ls4-verify.sh`, log `ls4-doc-commands.log` (session scratch). Two drafted claims were wrong and were corrected before review (below). Reviewer: see *Review*. |
| The "which repo" table matches the design's repo table exactly | Copied cell for cell from the design's *The repos*; reviewer: see *Review*. |
| The provenance template has every field LS-R8 lists | `PROVENANCE.md` sections: *Who ran it*, *Sources behind the wall*, *Which agent saw what*, *Pins*, *Verifier reports*, and the spec's sha256 under *Spec*; private-record statement in its header and first paragraph. Reviewer: see *Review*. |
| The privacy check and full check list pass | All 12 commands exit 0 (`ls4-checks.log`, session scratch): anchored-peripheral-spec `Ran 94 … OK`, board-expert `Ran 57 … OK (skipped=1)`. |

**Claims corrected by the verification runs:** a pin given no `--repo` leaves its anchors
unresolved with only a warning (exit 0), not an error; `--drift` with several `--repo`
checkouts requires `--drift-pin` (exit 2). Both texts now say so.

## Decisions the plan left open

- **Named pins in templates:** the scaffold's spec templates are board specs, which have no pins;
  named pins went into `anchored-peripheral-spec`'s prompt templates instead, and the scaffold got
  the marker fields only.
- **The repo table verbatim:** its "facts 2, 3, 6 below" points into the design; a sentence after
  the table explains it rather than editing the cell.
- **Peripheral spec file names:** `spec_check.py` loads every `*.spec.md` as a board spec
  (`widget.spec.md` fails with `unknown kind None`), so `SPEC-FORMAT.md` says to name peripheral
  specs `<device>-spec.md`. Input for LS5's layout.

## Review

One independent reviewer subagent with fresh context traced every changed claim to the code or
the design, reproducing behavioral claims on its own scratch specs and roots. Its findings are
saved as `ls4-review.md` in the session scratch. No blockers; all four criteria met (the repo
table byte-identical to the design's; every LS-R8 field present). It did not run the
portability scan (no script changed); the implementer's check log includes it. Every finding was
fixed:

| # | Sev. | Finding | Resolution |
| --- | --- | --- | --- |
| S1 | should-fix | The spec-writer template's `inventory_check.py` self-check used a bare `--repo`, which exits 2 on the multi-pin specs the same template asks for | `--repo <pin>=<source checkout>`, once per pin whose tree holds the headers |
| S2 | should-fix | The new `cleanroom-spec` step kept only `docs/provenance/` private, not the spec in `docs/` | Says the spec and `docs/provenance/` stay out of a public tree |
| S3 | should-fix | README line 7 still said "source you own" | Now "source you may cite (GPL-2.0, BSD, MIT, Apache, or your own code)" |
| N1 | nit | The template said the spec hash must equal the ledger's, which records a 12-hex prefix | The template records the full hash; its prefix matches the ledger |
| N2 | nit | "Any GPL-2.0 source → GPL repo" also caught `GPL-2.0 OR MIT` files, which belong in permissive | "A license that requires GPL-2.0, with no permissive alternative" |
| N3 | nit | "License gate" and "named pin" undefined in `spec-verifier`'s Terms; "SPDX" unglossed in the anchored skill | Terms entry added; SPDX glossed on first use with a pointer to the glossary |
| N4 | nit | The marker template said license fields were optional elsewhere; the gate always needs `accepts:` | Comment says `spec_check.py` only warns, and the gate needs `accepts:` |
| N5 | nit | "Implementers may and should read the source" sat beside the new text on readers the source's license does not permit | Qualified with a pointer to *Where the spec goes* |

The fixes are text only and were checked against the reviewer's reproductions; no second review
was run.

## Limitations

- `cleanroom-spec` still lands specs in a project's `docs/` and says nothing else about where
  that project is published; the new step says the spec and its attestation stay private. The
  rest of the skill is reconciled with policy 1 when it moves (LS6, LS7).
- The repo table and placement text name repositories that do not exist until LS5; the skill says
  so and points at the fixture roots meanwhile.
- Marketplace and plugin descriptions are unchanged (LS8, LS12).
