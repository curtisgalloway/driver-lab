<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SR-7: spec revision 7, after a second reading of revisions 5 and 6

## Terms

- **Spec** — the clean-room implementation spec for the Intel 82540EM (e1000) core network
  path ([L02b](L02b.md)); **revision 4** is the one the candidate was written from
  ([L02c](L02c.md)), **revision 5** set PSCON bit 11 ([L02s](L02s.md)), **revision 6** folded
  in L02's `[emulated]` results and spec gaps ([L02f3](L02f3.md)); **revision 7** is this
  unit's, built on revision 6.
- **Reading**, **first reading**, **second reading**, **A1**, **adjudication** — as in
  [AF-1](AF-1.md#terms). Here the first readings are the landed records of L02s (revision 5,
  15 verdicts, 2026-09-25, Claude Opus 5.5) and L02f3's round 4 (revision 6, 45 verdicts,
  2026-09-25, Claude Fable 5.1); the second reading is this unit's, of every claim changed
  between revisions 4 and 6 (2026-09-26, Claude Fable 5.1, without sight of either first
  record).
- **Extract** — the operator's file of what the differential runs recorded (register traces,
  packet captures, kernel logs, verdicts), against which an `[emulated]` claim is verified;
  never the model's source ([SF-1](SF-1.md)).
- **CF-1** — the unit that rebuilt the candidate from revision 6 ([CF-1](CF-1.md)), in
  flight when this unit was approved and merged while it ran; the reason this revision
  changes no driver requirement.

See the [glossary](../GLOSSARY.md), the [plan](../IMPLEMENTATION-PLAN.md) (follow-ons named
in L02f3) and the [notebook chapter](../notebook/SR-7.md).

## Status

**Complete, 2026-09-26.** Revisions 5 and 6's changes now have two independent readings: the
second read every changed claim (83 verdicts: 77 PASS, 3 FAIL, 3 UNVERIFIABLE) and agrees
with the first readings on 54 of their 60 keys (2 were read once by the first readings
only; 4 keys, on three passages, disagree); the three disagreements are adjudicated below
for the second reading, all on form, citation scope or definiteness, and applied in
revision 7. Revision 7 is revision 6 plus fifteen hunks: AF-1's six items, SF-1's pointer
form, QF-1's F2 as §12.5 EM8, the three adjudicated corrections and the readers' wording
notes; **no requirement on a driver changes**, which the revision-7 readers confirmed hunk by
hunk. Six sequential fresh readings of revision 7's changes ended at 59 PASS, 0 FAIL, 1
UNVERIFIABLE (the first five found 1, 3, 1, 1 and 1 FAIL, all fixed; round 2's header FAIL
and rounds 3 to 5's EM8 FAILs were sentences a fix pass had written, and round 2's other
two were in text an earlier round had passed). Revision 7 is 1,685 lines, SHA-256
`ae18af9995e996d386dd1b8149e9bacc0bbe0ab25a121a8c17033ccf585f0f14`, landed in private run
`e1000-sr7-20260926-01` with its ledger PASS line. The user's two backlog requests are
recorded in the plan.

## Method

| Step | Result |
| --- | --- |
| Inputs | Revisions 4 (`0490a888…`, 1,601 lines), 5 (`c587f41d…`, 1,604) and 6 (`f78ea07a…`, 1,661), copied from their runs and hashed; the r4→r5 (5 hunks), r5→r6 (13) and r4→r6 (16) diffs; the manual's text rendering (`66d93b63…`; no PDF in this store); L02f3's observations extract for EM1–EM7; the L02c whitelist (362 lines, 347 entries) and map; for the one `[kernel]` passage revision 7 touches, the pinned v6.12 tree's `include/` and `Documentation/` only |
| Second reading of revisions 5 and 6 | Brief written from the diffs before the operator opened either first record: 18 changed passages keyed by section and item. One fresh `spec-verifier` reader, clean-room (no driver or QEMU source; the operator read none either), given the extract as L02f3's readers had it. 83 verdicts in 7.7 minutes: 77 PASS, 3 FAIL, 3 UNVERIFIABLE, 0 GAP; clean-room check of the changed hunks PASS |
| Comparison | The operator matched the first readings' 60 keys (15 + 45) to the second's 83 lines by section and item (`review/comparison.md` in the run) and adjudicated each disagreement against the manual's text and the extract |
| Revision 7 | Edited on a working copy of revision 6 from the manual text, the spec, the public evidence files and QF-1's run artifacts (captures classified by sender, ethertype and length; verdicts; the guests' device models from the run's argv files). No driver source, no QEMU source |
| Reverification of revision 7 | Fresh `spec-verifier` readers on the r6→r7 changes and their dependencies (15 hunks), each given revision 6, the working copy, the diff, the manual text, the extract extended with M8, both scan reports and the two kernel directories; none given the second reading's record, the comparison or an earlier round's record. Round 1: 54 verdicts, 52 PASS, 1 FAIL, 1 UNVERIFIABLE; the FAIL and six notes applied. Round 2: 42 verdicts, 39 PASS, 3 FAIL (the header omitted the passage round 1's fix had changed; R7's caveat rested on a precondition the test lacked; a "last paragraph" that was not); all applied. Round 3: 53 verdicts, 50 PASS, 1 FAIL, 2 UNVERIFIABLE (EM8's second-defect sentence, scoped by the runs' results rather than by the defect's place in the driver; the format file added as an input for the header's citation-shape claim). Round 4: 55 verdicts, 53 PASS, 1 FAIL, 1 UNVERIFIABLE (EM8's first-defect sentence, the same overreach round 1's rewording had introduced in the other half of the sentence; scoped to short frames). Round 5: 60 verdicts, 59 PASS, 1 FAIL (the operator's gloss on the d21 captures, "ARP included, the peer's ARP went unanswered", which the extract does not record; replaced by the extract's facts). Round 6: 60 verdicts, **59 PASS, 0 FAIL, 1 UNVERIFIABLE** (G-16's "checked on the PDF", unchanged from revision 6; no PDF in this store); clean-room check of the changed hunks PASS in every round; the landed record carries the landed hash |
| Leak scans | Revision 6, every draft of revision 7 (seven scans) and the verification records, with the L02c whitelist against the 7 reference driver files at the pinned commit; every scan clean |

## The readings of revisions 5 and 6 compared

| | First readings (L02s, L02f3) | Second reading (SR-7) |
| --- | --- | --- |
| Verdicts | 15 (15 PASS) and 45 (44 PASS, 1 UNVERIFIABLE) | 83: 77 PASS, 3 FAIL, 3 UNVERIFIABLE |
| Text read | The landed revisions 5 and 6 (each first record is the final, clean round after fixes) | The landed revision 6, with revisions 4 and 5 and the three diffs |
| Model, inputs | Opus 5.5 (L02s), Fable 5.1 (L02f3); manual text; L02f3's extract | Fable 5.1; the same manual text and extract |

- **Agreements: 54 of the 60 first keys** carry the same verdict in the second reading,
  usually at finer grain (the second gives a quotation, a page number, each premise set, the
  confidence and the verification their own lines). Two of those carry an extra UNVERIFIABLE
  line beside the PASS: R6's "1 µs", which the second declares unsettleable without the PDF
  where the first passed it from context (both had the text only; the value rests on L02c's
  PDF check, G-16), and §12.6's "Filed by" column, which the first left as a note.
- **Read by the first readings only: 2 keys**, both claims about that unit's leak-scan
  reports; the second reader was not given those reports (this unit rescanned revision 6:
  clean).
- **Disagreements: 4 keys, on three passages** (the PHY-extras bullet is a key in both first
  records). 54 + 2 + 4 = 60. All three passages adjudicated for the second reading, below;
  none touches what a driver must do.
- **Noted by a first and by the second reader:** a third manual statement against 1000 Mb/s
  half duplex in §8.4.2 (L02f3's round-4 record calls it the section's last sentence; the
  second reader's reply, recorded in the ledger and not in its record, its last paragraph);
  revision 7 cites it.
- **Missed by both on the hunks:** nothing found beyond the three disagreements. Outside the
  hunks the second reader noted, and revision 7 applies as wording: §4.8's PSCON row gave
  bit 11's reset value with no pointer at G4's "set to 1" (in its record, the cross-file
  line); §12.3's HALF 1 bullet listed the tag classes behind "every fact" without §8's
  `[kernel]` (in its reply, recorded in the ledger).

## Adjudication

1. **§5.4 PHY-extras bullet, the register-20 clause** (first: PASS, judged for bit 11;
   second: FAIL). Revision 4 read "Before G7 (order not known to be required) it sets PSCON
   bit 11 … and … writes PHY register 20"; revision 5 replaced the parenthetical with a
   bit-11 justification from §11.1.3, so the sentence also asserted register 20's place
   before G7 with no caveat. §11.1.3 (printed p. 188) names "PHY Specific Control Register
   bits 3, 4, 6:5, 9:8 and 11" and no register-20 bit, so that order rests on the source
   alone and the spec's own `[source-observed]` rule (§1) requires the caveat. **FAIL on
   form**; the guidance ("leave register 20 at its reset value") is unchanged. Applied.
2. **§9.2 PSCON row, the timing clause** (first: PASS; second: FAIL). "The bits apply only at
   the next PHY reset, AN restart, power-down exit or link loss" was attributed to §11.1.3 for
   bits 6:5, 1 and 11; the same list does not include bit 1. **FAIL on citation scope**,
   harmless (bit 1 is kept at reset). Applied: "bits 6:5 and 11 …, §11.1.3; bit 1 is kept at
   its reset value".
3. **§12.5 EM7, "behave identically in it"** (first: PASS against the same extract; second:
   FAIL). The extract records that the trace comparison saw the two drivers write different
   flow-control register values and that no check distinguishes them; "behave identically"
   states more than that (the `spec-verifier` rule: an `[emulated]` claim fails when it
   claims more than the runs show). **FAIL on definiteness**; wording only. Applied with the
   second reader's text.

Why the first readers passed passage 1 (both) and passage 2 (L02s, the only first reading
of §9.2, which revision 6 did not change): each was reading the change (bit 11), and the
defect sits in the neighboring clause of the same sentence, which the change had altered by
removing a parenthetical. A second independent reading of the sentence, rather
than of the change, is what found it.

## Revision 7

Built on revision 6 in the run store; the working copy, the r6→r7 diff (15 hunks), the
extract with M8, the scan reports, both briefs, both verification records, the comparison
and the ledger stay there. **No requirement on a driver changes**: every passage below is a
tag-form, wording, citation or observation change, and the revision-7 reader was asked to
confirm that hunk by hunk (below). CF-1 can proceed on revision 6 or revision 7 (open item).

| Passage | Change | Source |
| --- | --- | --- |
| Header | Revision 7, eleven items, the no-requirement-change statement | — |
| §1 tag table, `[inference]` row | Says when confidence and a verification method are required (an inference that carries an argument) and when a one-clause design choice may omit them (naming its premise; "order not known to be required" is its verification clause). The narrowing option of AF-1's item 2: the inferences that state no confidence on the tag's line (38 of revision 4's 50, by AF-1's count) conform where they are one-clause design choices, without editing each; the revision-7 reader sampled both kinds against the row | AF-1 item 2 |
| §4.1 FWE row, §5.2 R6, §5.3 E1 | `[emulated]` §12.5 EMn → `[emulated]` (§12.5 EMn), the format's parenthetical form; no change of meaning | SF-1 Limitations |
| §4.7 general rules, initialization bullet | Notes §14.3's "For the 82541xx and 82547GI/EI, clear all statistical counters" (printed p. 376), the one place the manual scopes counter-clearing to named parts, and that it does not settle the §13.7/§14.8 disagreement for this part | AF-1 item 4 |
| §4.8 PSCON row | Bit 11: "(reset 0; set to 1 by §5.4 G4)" | Second reading's note |
| §5.1 statistics paragraph | §14.8's initialization-within-1-µs and "indeterminate values" and §13.7's not-initialized stated side by side; the spec relies on neither, clearing by reading (§5.5); no wait needed in practice, now a tagged one-clause `[inference]` (the reset sequence runs first). §5.1, §4.7 and G-10 now say one thing | AF-1 item 3; the revision-7 reader's note on the tag |
| §5.2 R7 verification test | Caveat: a reading of 1 cannot separate an EEPROM re-read from a restore from an internal copy, so it supports keeping the wait rather than proving a reload; a 0 shows no reload for that bit and the wait is then a harmless 5 ms; neither outcome drops the wait on its own, and a 0 is the result that lets the default be revisited on hardware. The test gains the precondition the caveat needs: read CTRL bit 20 and expect 1 before the write, since Table 13-3 footnote 2 makes the power-up load of the EEPROM value conditional on the signature bits, and without it a 0 settles nothing (a gap in revision 6's test text that the caveat made load-bearing) | AF-1 item 5 (both readings of revision 4); the revision-7 reader's round-1 note and round-2 FAIL |
| §5.3 E5, first `[inference]` | The "log it, then random address or refuse" policy now states its premises, confidence and verification (none needed: the choice is the implementer's, either keeps the log line); the choices are unchanged | Revision-7 reader, round 1 FAIL: the new §1 row made the untagged policy inconsistent |
| §5.4 PHY-extras bullet | Register 20's place before G7: "order not known to be required, since §11.1.3 names no register-20 bit" | Adjudication 1 |
| §9.2 PSCON row | Timing clause scoped to bits 6:5 and 11 with §11.1.3; bit 1 kept at reset | Adjudication 2 |
| §10.3 probe step 3 | The `IORESOURCE_MEM_64` `[inference]` states its premise with citations, confidence high, and a verification on the test device (compare the resource flag against the config dword's type field) | AF-1 item 1 |
| §12.1 G-12 | Also quotes §8.4.2 (p. 159): no half-duplex support "when operating at 1000 Mb/s in internal PHY mode"; L02f3's record had called it the section's last sentence and the second reader's reply its last paragraph, and the revision-7 reader found the section runs on to p. 160 | L02f3 round 4 and the second reader's reply (ledger); the revision-7 reader's round-2 FAIL on the citation |
| §12.1 G-16 | The rendering drops the micro sign in the cited places (pp. 228, 308, 318) and keeps it in §14.8 (p. 388) and §6.3's PCI clock notes (pp. 135, 137), so a bare "s" is suspect and a surviving "µs" is not; "drops" is what a reader sees, since those places hold a private-use code point (U+F06D) that displays as nothing, and the three pages are the set of places, not one per value | AF-1 item 6; the revision-7 reader's note, confirmed in the rendering's bytes |
| §12.3 HALF 1 bullet | Names §8's `[kernel]` citations among the classes behind HALF 1's facts | The second reader's reply (ledger) |
| §12.5 heading, intro, EM7, EM8 | Heading EM1–EM8; the intro names the planted-defect runs EM8 rests on; EM7 reworded (adjudication 3); **EM8**: frames shorter than 60 bytes reach the host at their wire length instead of being dropped as runts, stated from the captures and verdicts (the peer's 42-byte ARP and echo replies received by both unmodified drivers in every `frame-sizes` run; a planted defect delivering short received frames one byte short failing every ping; a planted defect keyed to a descriptor length over 46 bytes and reaching short frames only passing the 42-byte ping), beside §6.4's row 60 (whose words "runt" and "dropped" are the spec's; the manual's are undersize, RUC §13.7.34, and "short packets" stored only with RCTL.SBP = 1, §13.4.22); consequence: none required, since §6.4 takes the length from the descriptor, and a receive path assuming 60 bytes would misbehave here and not on hardware. The defects are described by what they did to short frames and by the pings that passed and failed, not by where they sit in the reference driver | QF-1 F2, phrased from what the runs recorded; the revision-7 readers' rounds 1, 3 and 4 on the two defect sentences |

**What EM8 rests on.** QF-1's finding explains the runts by the model's source, which the
spec must not carry. The captures alone say enough: the DUT is QEMU's `e1000`; the peer is a
guest on a virtio-net device, so nothing pads its frames; in every `frame-sizes` capture the
peer's ARP and its echo replies to the DUT's 42-byte pings are 42-byte frames at the DUT
(the DUT's own frames all leave at 60 bytes or more); both drivers receive them (the
42-byte ping passes in all eight control runs across QF-1 and L02f3); a copy of the
reference driver delivering short received frames one byte short failed every ping in 3 of
3 runs (the DUT's pings never left it; the peer's six echo requests went unanswered, while
its 21 42-byte ARP requests and replies appear in every capture), and a copy whose defect
was keyed to a descriptor length over 46 bytes and reached short frames only passed the
42-byte ping in 3 of 3, failed the 60- and 61-byte ones and passed the 1513- and 1514-byte
ones. The extract (M8 in the run) carries the counts.

**The checker.** `spec_check.py` reads board specs (`*.spec.md` with YAML frontmatter) and
not this spec, so "passing its rule" was checked by hand: its `[emulated]`-unnamed regex,
imported from the checker, matches revision 6's three tag-clause uses and none of revision
7's; what it still matches in revision 7 are prose mentions of the tag name, which the
format says are not tags. The never-alone rule holds as in revision 6 (each use is a premise
of an `[inference]` or beside a `[databook]` citation), judged by the readers.

## A1 after this unit

| A1 clause | Revision 4 | Revisions 5 and 6 | Revision 7 |
| --- | --- | --- | --- |
| Two verification readings | Met (AF-1), one first-reading claim read once | **Met**: two independent readings of every changed claim, different contexts (and, for revision 5, different models), neither seeing the other; two first-reading keys (leak-scan claims) read once | Not met as independent readings: six sequential fresh readings until clean, the final text read once after fixes (the same shape as L02s and L02f3); a second independent reading is the same procedure as this unit, when wanted |
| No unresolved FAIL | Closed here: the §10.3 form FAIL applied in revision 7 | The three second-reading FAILs applied in revision 7; none open | None open: round 6 is 59 PASS, 0 FAIL |

What remains under A1: revision 7's changes read once; recall measured on revision 3 only.

## Items held back

None. Every item applied is a tag-form, wording, citation or observation change; nothing
changes what a driver must do, so nothing is listed for the user under the CF-1 rule.

## Items for the next spec revision (none applied here)

| # | Passage | Item | Source |
| --- | --- | --- | --- |
| 1 | §12.1 G-16 | The private-use code point that stands for the micro sign also occurs at printed pp. 295 (ITR's 128 µs example, §4.3), 309 (RADV, §4.4), 319 (TIDV) and 321 (TADV, §4.5), values the spec uses; G-16 lists only the three pages AF-1 named, and "the set of places" could be read as exhaustive | The round-6 reader's reply, outside scope (recorded in the ledger, not in its record) |
| 2 | §1 tag table, `[inference]` row | "Verification: none needed, because …" satisfies the row in R6 and now E5; the row could say so | The round-4 reader's reply, outside scope (ledger) |
| 3 | §5.2 R7 precondition | A prior iteration of the test in the same power cycle would also make CTRL bit 20 read 0; the parenthetical gives only the signature reason (the stated handling, "inconclusive", is right either way) | The round-5 reader's reply, outside scope (ledger) |

## Open items for the user

- **The next candidate round's spec.** CF-1 merged on revision 6 while this unit ran
  ([CF-1](CF-1.md)); revision 7 changes no requirement, so its result stands on revision 7.
  The next candidate round (CF-1's TNCRS attribution rule, once the revision after this one
  states it, and the file header's revision number) should be given revision 7 as its spec;
  the choice is the user's, since that round is the user's Codex launch.
- **The possible upstream report** (QF-1's F1) is recorded in the plan's backlog as the user
  asked; nothing has been filed.

## Checks

| Check | Result |
| --- | --- |
| `utilities/check-no-private-paths.py` | OK |
| `git diff --check`; privacy grep of the diff (addresses, host names, machine names, home paths) | clean; no hits |
| `spec_check.py` | Not applicable to this spec (no YAML frontmatter, not a `*.spec.md` under a root); its `[emulated]` rules applied by hand, above |
| Leak scans (L02c whitelist, 7 reference files at the pinned commit) | revision 6 clean; every draft of revision 7 clean (seven scans); both verification records clean |
| Changed surface | documentation and the private spec only: no test surface changed; the full suite runs in CI |

## Measures

- Operator time: about 07:37 to the final checkpoint on 2026-09-26 (Pacific), one session.
  Model cost not measured.
- Readers, harness-reported (figures in the ledger): the second reading of revisions 5 and
  6, 7.7 minutes; the six revision-7 rounds, 7.8, 9.4, 8.6, 7.1, 8.6 and 7.5 minutes.
- Human review effort: none during the unit.

## Review

The unit's verification artifacts are the readings themselves (the second reading's record
and the six revision-7 records in the run store). The public records were then read by one
fresh, read-only reviewer (same model family as the implementer) against the ledger, the
briefs, the comparison, the diffs, the extract, the scans, the verification records, the
first readings' records and the QF-1 and L02f3 captures and verdicts; its report is in the
run store under `review/`. It confirmed every hash, line count, hunk count, verdict total
and scan result quoted here, the comparison's coverage of all 60 keys and its mapped
verdicts, §11.1.3 as both records quote it, the adjudications as fair to both records, the
revision-7 table's coverage of all 15 hunks and their sources, that no hunk changes a driver
obligation (judged on each hunk's imperative content), that EM8 claims no more than the
extract and the extract matches a recount of all 14 captures and the verdicts exactly, the
A1 table against L02f3 and AF-1, and the absence of private infrastructure in the diff; it
judged broader review unnecessary. Nine findings, two medium, all applied:

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| F1 | medium | "55 of 60 keys agree": the comparison's own rows give 54 same, 2 read once, 4 disagreeing keys on 3 passages; the totals had counted the passage that is a key in both first records once | 54 + 2 + 4 = 60 everywhere; the comparison's totals and the ledger corrected with a note; the notebook carries a correction entry |
| F2 | medium | "Every FAIL after the first was a fix-pass sentence": round 2's G-12 and R7 FAILs were in text round 1 had passed | Restated: round 2's header FAIL and rounds 3 to 5's EM8 FAILs were fix-pass sentences; the other two were not |
| F3 | low | Stale counts: "ten items" (eleven landed), "both drafts" (seven scans), "five notes" (six) | Corrected |
| F4 | low | "What EM8 rests on" and the table row kept the glosses the round-5 reader removed from the spec ("ARP included"; "21 unanswered ARP frames", when 15 of the 21 are replies) | Both now use the landed EM8's facts |
| F5 | low | Notes attributed to records that do not hold them (the §8.4.2 and §12.3 notes are in the second reader's reply, not its record; L02f3 said "last sentence"; the next-revision items cite readers whose ledger entries lacked them) | Attributed to the replies, recorded in the ledger; the round-4 to round-6 replies' notes added to the ledger |
| F6 | low | "Both first readers passed passages 1 and 2": only L02s read §9.2 | Restated |
| F7 | low | The rounds' harness-reported durations were not in the ledger | Harness figures (minutes, tokens, tool calls) added to the ledger; Measures quotes them |
| F8 | low | The index's "Updated" time postdated its commit; the ledger's "grep … below" had nothing below; the notebook's "08:10" for round 3's launch against the ledger's 08:11 | Index time set at the final edit; the grep's results written into the ledger; the notebook's correction entry |
| F9 | info | The plan's backlog entry restated QF-1's F1; the plan's SR-7 entry, the index bullets and one notebook entry repeated conclusions | Backlog entry cut to a pointer; plan entry and index bullets cut to status, links and one-line lessons; the notebook entry noted in its correction entry (append-only) |

## Limitations

- Every reader and the implementer share a model family; no human read the changes.
- No PDF in this store: G-16's "checked on the PDF" and R6's "1 µs" rest on L02c's PDF
  check; the second reading declared the former UNVERIFIABLE and the latter's value
  UNVERIFIABLE where the first readings passed it from context.
- Revision 7's changes were read six times sequentially and the final text once, not twice
  independently; the same A1 shape as revisions 5 and 6 had before this unit.
- The comparison of the readings is the operator's matching by section and item, recorded
  row by row in the run store (`review/comparison.md`), not a mechanical join.
- EM8's defect descriptions went through four rounds of wording: what the runs recorded is
  in the extract (M8) and the captures; the entry claims only that, and the private ledger
  holds the reason QF-1's first declaration was wrong, which the spec does not carry.
- Four of the six FAILs after round 1 (round 2's header, rounds 3 to 5's EM8 sentences) were
  sentences a fix pass had written, as L02f3 also found; a fix pass that adds words needs its
  own reading. The other two (round 2's R7 caveat and G-12 citation) were in text an earlier
  round had passed.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
