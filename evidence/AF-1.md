<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# AF-1: a second independent reading of spec revision 4's changes

## Terms

- **Spec** — the clean-room implementation spec for the Intel 82540EM (e1000) core network
  path ([L02b](L02b.md)); **revision 4** is the revision [L02c](L02c.md) landed, from which
  the candidate driver was written; revisions 5 ([L02s](L02s.md)) and 6 ([L02f3](L02f3.md))
  came later.
- **Reading** — one fresh verifier subagent's pass over a set of the spec's claims, giving
  each a verdict (`PASS`, `FAIL`, `UNVERIFIABLE`, `GAP`), as in `spec-verifier`; a
  **verification record** is the file that holds the verdicts.
- **First reading** — L02c's change check of revision 4 (2026-09-24, a Claude Opus 5.5
  subagent with the manual PDF, on the revision-4 draft): 51 verdicts, 50 PASS, 1 FAIL, the
  FAIL fixed by a one-line change confirmed by `diff` only.
- **Second reading** — this unit's (2026-09-25, a Claude Fable 5.1 subagent with the manual's
  text rendering only, on the landed revision 4), made without sight of the first.
- **A1** — the design's acceptance criterion: the spec covers the core path, with two
  verification readings and no unresolved FAIL ([design](../QEMU-DIFFERENTIAL.md)).
- **Adjudication** — the operator's decision on a claim the two readings judged differently,
  made against the cited authority's text.

See the [glossary](../GLOSSARY.md), the [plan](../IMPLEMENTATION-PLAN.md) (follow-ons named
in L02f3) and the [notebook chapter](../notebook/AF-1.md).

## Status

**Complete, 2026-09-25.** Revision 4's changes now have two independent readings. The second
read every changed claim (69 verdicts: 68 PASS, 1 FAIL, 0 UNVERIFIABLE, 0 GAP) and agrees
with the first on every claim but one; it also independently confirms the one-line citation
fix that L02c had checked only by `diff`. The one disagreement is adjudicated below as a
format lapse in the spec's own tag convention, not an accuracy error, and goes to the next
spec revision; the spec was not edited in this unit. A1's "one reading" shortfall for
revision 4 is closed; what remains under A1 is stated below. Private run `af1-20260925-01`
holds the brief, the record, the diff, the scans and the ledger.

## Method

The option chosen was the second reading, not the recall re-measurement the plan also
allowed: A1 asks for two readings of the text, and only a second reading of the same changes
supplies that; recall on a later revision answers a different limitation (recall measured on
revision 3 only, still open) and would have left the one-reading shortfall standing.

| Step | Result |
| --- | --- |
| Inputs | Revision 3 (`b93d7ef0…d11f`, 1,530 lines; the orchestrator copied it from the original run store into this host's L02c run directory at 22:31 Pacific, since the local copy held only revision 4) and revision 4 (`0490a888…3472`, 1,601 lines); the unified diff, 22 hunks (the first reading's record speaks of 25, from a diff of the draft made elsewhere); the manual's text rendering (`66d93b63…`); for the `[kernel]` claims, the pinned v6.12 tree's `include/` and `Documentation/` only, as L02c's readers had |
| Brief | Written from the diff before the operator opened the first reading's record: 23 changed passages keyed by section and item (never by line or hunk), the forbidden inputs (driver source, QEMU, other runs, the evidence files, the first record), and the record's format. No PDF of the manual is in this store, so the brief says PDF page numbers come from the text's form feeds and that a micro-sign check is UNVERIFIABLE |
| Second reading | One fresh `spec-verifier` reviewer subagent, clean-room (no driver or QEMU source; the operator read none either). 69 verdicts in 8.7 minutes: 68 PASS, 1 FAIL; clean-room check of the changed hunks PASS |
| Leak scans | Revision 4 and the new record, with the L02c whitelist (362 lines, 347 entries) against the 7 reference driver files at the pinned commit. Revision 4: clean. The record: one identifier, `pci_dev`, inside its quotation of the `pci_read_config_dword` prototype from the target tree's `include/linux/pci.h` (the same class as `PAGE_SIZE`, which L02c added to the target-API list); dispositioned as target-API nomenclature on a run-local copy of the whitelist, the L02c whitelist unchanged; rescan clean |
| Comparison | The operator matched the first reading's 51 keys to the second's 69 by section and item and adjudicated the one disagreement against the spec's own rule (below) |

## The two readings compared

| | First reading (L02c) | Second reading (AF-1) |
| --- | --- | --- |
| Verdicts | 51: 50 PASS, 1 FAIL | 69: 68 PASS, 1 FAIL (65 claim lines over the 22 hunks, the header, 3 cross-checks) |
| Text read | Revision 4 draft (`e3b80f84…`), before the follow-up | Landed revision 4 (`0490a888…`) |
| Model, inputs | Claude Opus 5.5; manual PDF and text; kernel `include/`, `Documentation/` | Claude Fable 5.1; manual text only; the same kernel directories |

- **Agreements: 49 of the first reading's 51 keys** carry the same verdict (PASS) in the
  second, usually at finer grain (the second splits a passage's quotation, page number and
  `[inference]` into separate lines). Both readings independently attached the same caveat
  to R7's verification test: a CTRL bit reading 1 after the reset cannot separate an EEPROM
  re-read from the hardware restoring the value without one; both outcomes keep the 5 ms
  wait, so the test is safe as written.
- **The first reading's FAIL** (the DMA alignment citation one line short, `399–400`) reads
  PASS in the second on the landed `399–401`. Not a disagreement: the text changed between
  the two readings, and the second is the independent re-read of that correction which L02c
  recorded as missing.
- **Disagreement, 1:** §10.3 probe step 3, the `[inference]` that the PCI core sets
  `IORESOURCE_MEM_64` from BAR0's type field. First: PASS ("the inference is labeled and the
  advice to read the config dword follows"). Second: FAIL, the inference states no confidence,
  which the spec's §1 requires. Adjudicated below.
- **Keyed by one reading only** (no verdict conflict): the first keyed "R7: 5 ms wait kept"
  and "EEPROM-default CTRL bits: coverage by G1 through §5.10", which the second folded into
  neighboring lines; the second added Table 13-3's footnote 2 as its own line, and three
  cross-checks (a keyword sweep of the whole file, the citations around each hunk, and §5.1's
  unchanged statistics sentence).
- **Missed by both on the hunks:** nothing found. Outside the hunks, the second reading noted
  three things the first had not: §5.1's unchanged "statistics become valid within 1 µs
  (§14.8)" leans on the §14.8 claim that §4.7 and G-10 now decline to follow; §14.3's last
  bullet ("For the 82541xx and 82547GI/EI, clear all statistical counters") is the one place
  the manual scopes counter-clearing to named parts and §4.7 does not mention it; and the
  text rendering keeps the micro sign in §14.8 while dropping it in Table 13-3 and the timer
  registers, so G-16's "drops the micro sign" is true of the cited places, not the whole
  rendering. The first reading's PDF checks of the micro-sign values were not new claims of
  revision 4 and the second could not repeat them.

## Adjudication

**§10.3 probe step 3, the `IORESOURCE_MEM_64` `[inference]`.** The authority here is the
spec's own tag convention, not the manual. Revision 4's §1 tag table says of `[inference]`:
"Not read anywhere; concluded. Premises, derivation, confidence and verification method are
given." The passage gives its premise ("the header defines the flag without comment") and a
mitigation ("read the config dword when the answer matters") and states no confidence and no
verification. Read against that sentence, the second reading is right and the claim is a
**FAIL on form**; both readings agree that every citation in the passage resolves to what the
spec says (`include/linux/pci.h:1241`, `include/uapi/linux/pci_regs.h:96, :105–108`,
`include/linux/ioport.h:55`), so it is not an accuracy error. The first reading's PASS
applied the weaker test "labeled and mitigated". The lapse is not particular to this
passage: of revision 4's 50 `[inference]` uses, 13 state a confidence; the full form is used
for the argued inferences (R7, the EEPROM-default bits, X9, §7.4, §9.1) and omitted from the
one-clause design choices, and both full readings of revision 3 passed those. Revisions 5 and
6 did not change §10.3 or §1's sentence (the revision 4→6 diff touches neither), so the
correction goes to the next revision as item 1 below, with the wider convention question as
item 2.

## A1 after this unit

| A1 clause | Revision 4's changes | Revisions 5 and 6's changes |
| --- | --- | --- |
| Two verification readings | **Met.** Two independent readings, different models and contexts, neither seeing the other; the first's one FAIL independently confirmed fixed | Not met as independent readings: sequential fresh readings until clean (L02s: two; L02f3: four), the final text read once after fixes |
| No unresolved FAIL | One FAIL open, on form (the §10.3 confidence), carried to the next spec revision because this unit does not edit the spec; no accuracy FAIL | None open in the landed records |

The recorded shortfall "revision 4's changes were read once" is closed. What remains under A1:
the low form FAIL above until the next revision applies it; revisions 5 and 6's final text
read once; recall measured on revision 3 only. The next revision (CF-1 builds on revision 6)
can apply item 1 and, if the same A1 standard is wanted for revisions 5 and 6, a second
independent reading of their changes is the same procedure as this unit.

## Items for the next spec revision (none applied here)

| # | Passage (unchanged in revisions 5 and 6 unless said) | Item | Source |
| --- | --- | --- | --- |
| 1 | §10.3 probe step 3, `IORESOURCE_MEM_64` `[inference]` | State a confidence (high) and a verification (on the test device, compare the resource flag against the config-dword read) | Second reading's FAIL, adjudicated |
| 2 | §1 tag table, `[inference]` row | 37 of revision 4's 50 inferences give no confidence; either add one to each inference that carries an argument, or narrow the sentence to say when the full form is required | Adjudication |
| 3 | §5.1, "Statistics become valid within 1 µs" | Reword so that §5.1 and §4.7/G-10 read as one position (§14.8 says accessible within 1 µs; the spec clears by reading rather than relying on it) | Second reading, outside scope |
| 4 | §4.7 statistics rules | Mention §14.3's last bullet, which scopes counter-clearing to the 82541xx and 82547GI/EI, beside the §13.7/§14.8 disagreement (revision 6 changed §4.7's TNCRS, RLEC, RUC and ROC rows, not this bullet) | Second reading, outside scope |
| 5 | §5.2 R7 verification test | Say that a reading of 1 cannot separate a re-read from a restore without one, and that either keeps the wait | Both readings' caveat |
| 6 | §12.1 G-16 | "Drops the micro sign" is true of the cited places, not the whole rendering (§14.8 keeps it) | Second reading, outside scope |

Items 3–6 are wording; none changes a requirement. Revision 6's bare `[emulated]` pointers
([SF-1](SF-1.md), Limitations) remain the other item queued for that revision.

## Checks

| Check | Result |
| --- | --- |
| `utilities/check-no-private-paths.py` | OK |
| `git diff --check`; privacy grep of the diff (addresses, host names, machine names, home paths) | clean; no hits |
| Leak scans (above) | revision 4 clean; the record clean after the one target-API disposition |
| Changed surface | documentation only: no test surface changed; the full suite runs in CI |

## Review

The unit's review artifact is the second reading itself (the record in the run store). The
records here were also read by one fresh, read-only reviewer (same model family as the
implementer) against the two verification records, the diff and the ledger; its report is in
the run store under `review/`, and its findings and resolutions follow.

(Review pending at this commit; findings and resolutions are added after it.)

## Limitations

- Both readings share a model family with the spec's author, and the second shares its model
  with this unit's implementer; no human read the changes.
- The second reading had no PDF: the micro-sign values revision 4 marks "PDF-verified" were
  not new claims and were not re-checked; printed-to-PDF page mapping was checked by form-feed
  count instead.
- The readings differ in grain (51 and 69 lines over the same 22 hunks); the comparison is the
  operator's matching by section and item, recorded in the notebook, not a mechanical join.
- The second reading verified the `[kernel]` citations against `include/` and
  `Documentation/` of the pinned tree on this host, not the L02c run's staged copies; the tree
  is the same commit.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
