<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR6b: a comparison reading of spec revision 8 by a new reading model

## Terms

- **Spec** — the clean-room implementation spec for the Intel 82540EM (e1000) core network
  path ([L02b](L02b.md)); **revision 8** is the current one ([SR-8](SR-8.md)). HALF 1 covers
  the hardware; HALF 2 (§10) the Linux integration.
- **Comparison reading** (the design's C4) — one fresh reader using a new reading model reads
  the current revision whole, under the same brief format and without sight of any earlier
  record; its record is joined to the earlier ones key by key, and its FAILs are
  disagreements until adjudicated against the cited authority.
- **Reader role** — the deployment manifest's (`evals/deployment.yaml`) declaration of which
  model reads; **scope.reader** — the reader the status index has adopted.
- **R/E/W item**, **S1–S5**, **tier-1/tier-2** — as in [CR6a](CR6a.md#terms) and the
  [design](../DESIGN.md#continuous-review-keeping-specs-right-as-evidence-changes).
- **NAPI** — the Linux network stack's polled receive interface; `napi_schedule_prep()`,
  `napi_enable()` and `napi_disable()` are its calls, cited from the kernel's `include/` and
  `Documentation/`.

See the [glossary](../GLOSSARY.md), the [plan](../IMPLEMENTATION-PLAN.md#cr6--the-first-tier-1-batch)
and the [notebook chapter](../notebook/CR6.md).

## Status

**Complete, 2026-09-26; the second unit of CR6's batch.** Changing the manifest's reader role
to Codex `gpt-6-astra` (a different model family; an orchestrator decision under the CR plan the user approved, recorded in PR #27's body, not a model the user named)
queued exactly one comparison reading. The reading ran in Codex's read-only sandbox with no
network, 41 minutes and 416,524 tokens (Codex-reported), over the whole of revision 8: **800
verdicts, 681 PASS, 98 FAIL, 19 UNVERIFIABLE, 2 GAP**. Four fresh Claude Opus 5.5 reviewers
adjudicated all 119 non-PASS lines: 84 upheld or partly upheld, 16 rejected, 19 input
limitations (no PDF, or inputs the brief excluded). Of the 84, **14 lines (12 findings) are R**, most of
them in HALF 2's kernel protocol order, which earlier readers had checked only for its
citations. They go to the user as one revision decision (below). The index has adopted the
new reader. Private run `cr6-20260926-01` holds the brief, workspace, record, command log,
join, adjudications, scan and ledger.

## Method

| Step | Result |
| --- | --- |
| Queue | `evals/deployment.yaml`'s reader role changed from Claude Fable 5.1 to Codex `gpt-6-astra`; the sweep then listed one `comparison-reading` unit, ready, with that model, and nothing else changed ([notebook](../notebook/CR6.md)) |
| Brief and workspace | Written before any CR6a result: the whole of revision 8 keyed by section and item, one line per checkable fact; inputs copied into a workspace holding no earlier record (revision 8, the operator's `[emulated]` observations extract, the verifier and format texts), plus the manual's text rendering (no PDF) and the pinned v6.12 tree's `include/` and `Documentation/`; `[source-observed]` facts checked for their markers only; the record returned as the final message |
| Reading | Launched by the orchestrator: `codex exec`, model `gpt-6-astra`, reasoning effort high, `--sandbox read-only`, output captured with `-o`; exit 0. The command log shows reads of the workspace, the manual text and the two permitted kernel directories, and one read outside them: at start the reader probed five instruction-file paths (three inside the run store, none of which exist) and printed the one that exists, the user's source-tree conventions file, which holds no records |
| Join | `review/comparison-cr6b.md`: the latest landed record of each revision (3 through 8). The new record is at finer grain than any earlier one, so the 681 PASS lines are joined at section level (680 same; 1, §12.4's hash-binding line, read once) and the 119 non-PASS lines key by key by the adjudicators |
| Adjudication | Four fresh Claude Opus 5.5 reviewers, one per section group (header to §4, §5, §6–§10, §11–§12), each given its lines, the whole new record, the spec, the cited authorities and every earlier record; 1,521 s and 769,784 tokens summed over the four, which ran in parallel (about 8 minutes elapsed). Per line: upheld, partly upheld or rejected against the authority; what earlier readers said; class; accuracy or form; driver change |
| Leak scan | L02c whitelist, 7 reference driver files at the pinned commit: the new record clean (0 shared runs, 0 identifiers) |

No verdict was changed before adjudication. The operator moved seven lines the adjudicators
had classed W but marked as accuracy findings to E (a claim's truth is not wording); none of
the seven changes what a driver must do.

## What the adjudication found

| Outcome | Lines |
| --- | --- |
| Upheld or partly upheld | 84: **R 14** (12 findings), **E 41**, **W 28**, 1 already recorded in the spec's own §12.6 (MDIC's error bit) |
| Rejected | 16: the new reader asked for more than the spec's rules require (a `[source-observed]` marker the tag's definition already carries; a one-clause design choice §1 lets omit confidence) or misread a passage |
| Input limitations | 19: no PDF (micro-sign rendering), and the historical revisions, the provenance ledger and the attestation's scan reports excluded by the brief. Earlier readers shared some of these limits; others (the header's history, the provenance and ledger claims) were settled by readers who had those inputs, or never read at this grain |

The earlier readers passed every upheld claim or never read it at this grain. Revision 3's
whole-text readers checked HALF 2's kernel citations for existence, not the order of the
protocol they describe; that is where most R findings are.

### R findings (for the user)

| Index ID | Passage | Finding | Adjudicator's weight | Proposed fix |
| --- | --- | --- | --- | --- |
| `CR6b-R-napi-schedule` | §10.3 interrupt handling, §7.5 | Interrupts are masked before `napi_schedule_prep()`; the kernel pattern the spec cites masks only when that call succeeds | with ndo_open, the most consequential: together they can leave every interrupt masked | prep, then mask, then schedule |
| `CR6b-R-ndo-open` | §10.3 `ndo_open` | `napi_enable()` comes after the unmask and the forced link-change interrupt; with the mask-first handler the device can be left masked with no poll | as above | enable NAPI before any interrupt source |
| `CR6b-R-ndo-stop` | §10.3 `ndo_stop` | a poll can unmask after the stop path masks | upheld | mask again after `napi_disable()`, before `free_irq()` |
| `CR6b-R-stats-cancel` | §10.3 statistics | nothing cancels the periodic statistics timer or work | upheld (a gap) | cancel it synchronously in `ndo_stop` |
| `CR6b-R-probe-regions` | §10.3 probe | the BAR is requested twice (explicitly, then by the managed iomap) | upheld | one ownership model |
| `CR6b-R-remove-order` | §10.3 remove | regions released before the device is disabled, against the PCI document the spec cites | upheld; low practical harm | unmap, disable, release |
| `CR6b-R-probe-dma` | §10.3 probe | the DMA-mask fallback cites the kernel document's lines labeled as wrong code | upheld; no behavior change, the fallback never runs | drop the fallback |
| `CR6b-R-mtu` | §10.3 | the permitted inputs do not show the MTU stays within 1500 without the change-MTU callback | R because the class is in doubt; partly unsettled | cite support for the default, or set the maximum MTU explicitly |
| `CR6b-R-L6-lock` | §5.9 L6 | STATUS.FD is sampled before the statistics lock is taken; a poll in between can be overwritten by the older sample | R or E in doubt; the error is bounded by the link task's latency, the residual §4.7 already states | sample FD inside the lock with the drain |
| `CR6b-R-PIF` | §6.1 | the manual says software must examine a packet whose inexact-filter bit is set; the spec says it may | upheld | filter such packets against the joined list, or an argued pass-through policy |
| `CR6b-R-RLEC` | §4.7 | RUC and ROC count only frames with a good CRC and RLEC does not, so "RLEC alone, or RUC + ROC" can report different numbers | upheld | RLEC alone (the adjudicator's recommendation), or RUC + ROC labeled as the good-CRC subset |
| `CR6b-R-ring-len` | §6.3 | the ring length field caps the ring at 65,528 descriptors; the manual itself says "64K" | R because the class is in doubt; minor | state the bound |

None was observed in the acceptance runs: open, stop, down/up and unload were exercised
there, but none of these races or orderings was triggered, no counter a CRC error would split
was compared, and no ring came near its size limit; the adjudications do not show that they
cannot be triggered. Whether CF-2's candidate has the same defects is a question for the next
candidate round, not this unit.

### E and W findings (for the next revision)

Carried in the index as `CR6b-evidence-items` (E, 41 lines) and `CR6b-wording-items` (W, 28),
both for CR8's revision. The E aggregate records no claim status changed: every E line was checked
against the adjudicators' "driver change" column (all no), and some sit in sections that
claims cite (§5.2 for Q18, §6.3 for Q07, Q08 and Q21, §8.4 for Q09, §11's test definitions),
whose harness checks and qualifications they do not touch; the aggregate therefore records
`changes_status: false` without listing claims. Keys, as the record gives them:

- **E:** §1/tag-compliance/1; §4.0/Reserved-bits/1, Table-grouping/1; §4.1/STATUS-BUS64/1,
  CTRL_EXT-handling/1; §4.3/ITR-inference/2; §4.5/TADV-inference/3, TCTL-SWXOFF/1,
  COLD-inference/3; §4.7/COLC/1, TNCRS/10, TNCRS/11, TNCRS/13, TNCRS/14, RLEC/4,
  octet-note/2; §4.8/LPA/1; §5.2/R6/3, R6/4, R6/5, R7/8, reset-effects/3,
  EEPROM-defaults/4; §5.3/E3/2; §5.6/SECRC/2; §6.3/one-empty-slot/3;
  §7.4/7813-verification/1; §8.1/DMA-addresses/1; §8.2/high-half/3; §8.4/coherency/1;
  §9.1/MDIO-timeout/1; §11/M4/1, M5/1; §12.1/G-6/2, G-19/1; §12.2/interrupt-confidence/1,
  kernel-confidence/1; §12.5/EM1/2, EM4/2; §12.6/R6/1, TNCRS-attribution/1.
- **W:** §4.5/TCTL-CT/2; §5.2/EEPROM-defaults/5, post-reset-extras/1; §5.3/E5/3,
  EEPROM-timeout/1; §5.6/X2/2, X4/2, X5/2, X9/3, X9/4; §5.7/T1/2, T5/2, T6/2;
  §5.10/source-power-down/1; §6.2/source-descriptors/1; §6.4/software-padding/2;
  §7.4/source-timers/1; §9.1/serialization/1; §9.4/source-flow-control/1;
  §10.3/probe-7/2, RX-delivery/2; §12.1/G-4/2, G-7/2, G-10/2, G-13/1, G-17/2;
  §12.3/HALF-1-attestation/2, source-transfer/1.

Two E findings bear on revision 8's own rule. §4.7's TNCRS row says the rule misattributes no
count the previous practice attributed correctly, with high confidence; after a change from half
to full duplex, counts between link-up and the drain at that change are discarded where the old
practice would have reported them, so that sentence and its confidence go (TNCRS/11, /13).
The rule and its net benefit stand. The user chose option (b) for CR6a's item (keep the
link-down reading as a stated design choice) before these adjudications finished; three
adjudicators tie this finding and `CR6b-R-L6-lock` to the same rule, and one asks a person to
confirm the revision-8 requirement is still wanted on the corrected argument. The user's
revision decision below therefore asks for that confirmation too. §5.2 R6's 10 µs margin is counted from the processor's
write and holds only if the posted write reaches the device well within 9 µs, which the spec
does not state (R6/3–/5); the adjudicator classed it E because the correction is wording, and
left one question open: whether a PCI configuration read, which the manual neither allows nor
forbids during reset, should flush the write instead.

Four of the E and W lines touch the spec's clean-room attestation: reasons attributed to the
source driver ("reasoning that", "giving as its reason") in `[source-observed]` passages. The
adjudicator left whether they cross the clean-room wall to the clean-room verifier or a person;
revision 7 removed a clause of the same kind (SR-7's PHY-extras finding).

## After this unit

The index records the reading (`verify-r8-cr6b`, independent, covering revisions 3 to 8 because
it read the whole current text) and its adjudication, the twelve R items, the two aggregate
items, and adopts `gpt-6-astra` as `scope.reader`. The comparison-reading unit is no longer
queued. The sweep after this unit (exit 1):

| Condition | After CR6a | After CR6b |
| --- | --- | --- |
| S2 | 13 stale qualifications | unchanged |
| S3 | AF-1's item; CR6a's reading and adjudication carry an accuracy FAIL | AF-1's item; twelve open R items; both readings and both adjudications carry accuracy FAILs |
| S4 | revisions 3–6 at 0/2; revision 8 met | **revisions 3–6 at 1/2**; revision 8 met (three lineages) |
| S5 | unmet (CR6a produced an R item) | unmet (CR6b produced R items) |

The whole-text reading also discharged the 63 stale accuracy slices from earlier revisions from
the queue (they stay stale in the index, as history), so the historical re-verification unit
is gone: 15 tier-1 units remain (a second reading for
revisions 3–6, AF-1's reconciliation, 13 requalifications), and 12 tier-2
`requirement-change` units wait for the user's decision beside the two outward reports. The
round-cap report no longer counts adjudications as rounds (fixed in this unit, with a test);
revision 8 stays pre-cap history.

## Checks

| Check | Result |
| --- | --- |
| `index_check.py evals/e1000` | OK: 48 items, 99 verification entries |
| `sweep.py evals/e1000` | not sufficient, as above; exit 1 |
| `campaign-review` tests | 106 OK, with the round-cap regression test |
| `utilities/check-no-private-paths.py`; privacy grep of the diff (addresses, host and machine names, home paths, MAC addresses) | OK; no hits |
| Leak scan | above |

## Review

After the index and records were drafted, one fresh, read-only Claude Opus 5.5 reviewer read
this file, the index entries, commit `0c68775` (the reader-role change and its tests), the
round-cap fix and every run artifact; its report is in the run store under `review/`. It
confirmed the reading's time, tokens and record hash, the 800 verdict counts, all 119
adjudication lines against the consolidated tallies (no mismatch, including the fourteen R
lines and the seven W→E moves), the E and W key lists, the sweep against the table above, the
round-cap fix (its test fails on the old code), the command-log audit, and the absence of
private infrastructure. Three medium findings, ten low and five informational, all applied or
recorded:

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| RB-1 | medium | The user chose option (b) before CR6b's adjudications, which tie two findings to the same rule; the file said the decision was unaffected | Said; the user's revision decision asks for confirmation |
| RB-2 | medium | The R table dropped the adjudicators' qualifiers | Weight column added; the MTU fix gives both options |
| RB-3 | medium | No record shows the user naming `gpt-6-astra` | Recorded as the orchestrator's decision under the approved plan; returned to the user for confirmation |
| RB-4 | low | "Renewed" 63 stale slices | "Discharged from the queue; still stale" |
| RB-5 | low | "Shared" input limitations overstated | Reworded |
| RB-6 | low | "Never exercised" overstated | "None observed" |
| RB-7 | low | The instruction-file read was attributed to the CLI, and Limitations contradicted it | The reader's probe described; Limitations corrected |
| RB-8 | low | "Ten R findings on the kernel documentation" | Eight of ten |
| RB-9 | low | Adjudication time 1,522 s and "25 minutes" | 1,521 s summed; about 8 minutes elapsed |
| RB-10 | low | The E aggregate's empty claim list was unargued | Argued above |
| RB-11 | low | SR-8-2 not updated after the decision | Where the widening lives is said in CR6a's decision section; SR-8-2 stays as recorded until CR8 applies it |
| RB-12 | low | The plan called CR6 complete with a section-level PASS join, before the checkpoint | Plan status names the deviation |
| RB-13 | low | Checks placeholder; no Review section | Both filled |
| RB-14 | info | Whole-text coverage of revisions 3–8 is new | One sentence in INDEX-FORMAT |
| RB-15 | info | The adjudication basis lists §3, which had no lines | Kept; adjudications count for neither S4 nor discharge |
| RB-16 | info | The private consolidation file mixes the operator's reclassification and ride-along E lines | Labeled in the run store |
| RB-17 | info | The next second reading (revisions 3–6) would use the same model as CR6b | For the user when that unit is batched |
| RB-18 | info | INDEX-FORMAT's scope.reader sentence is history | Updated |

## Limitations

- One comparison reading by one new model family; agreement between models raises
  repeatability, not truth, and the adjudicators are one model family (Claude).
- Each group was adjudicated by one reviewer; ten R findings rest on one adjudicator (the §6–§10
  group), eight of them on its reading of the kernel documentation. The user's decision should treat the R list as findings to fix
  in a revision that is itself read, not as settled text.
- C4 asks for a key-by-key join; the PASS join is at section level: it shows no earlier record contradicts a new PASS, not
  that an earlier reader checked the same sentence.
- The reader's isolation from earlier records was by instruction and workspace contents, not
  by a sandbox boundary; the command log shows one read outside the permitted inputs (the
  source-tree conventions file, above) and no earlier record.
- No PDF: every micro-sign rendering stays UNVERIFIABLE, and no recorded PDF check exists for
  three of G-16's further pages (309, 319, 321).
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
