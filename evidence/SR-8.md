<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SR-8: spec revision 8, the TNCRS attribution rule

## Terms

- **Spec** — the clean-room implementation spec for the Intel 82540EM (e1000) core network
  path ([L02b](L02b.md)); **revision 6** is the one the current candidate was written from
  ([CF-1](CF-1.md)), **revision 7** changed no requirement ([SR-7](SR-7.md)); **revision 8**
  is this unit's, built on revision 7.
- **TNCRS** — the controller's "transmit with no CRS" statistics register: successful
  transmissions during which the PHY did not assert carrier sense within one slot time. The
  manual calls it valid in full duplex only, and the spec reports it as a carrier error only
  then (§4.7, since revision 6).
- **Drain**, **reading** (of a counter) — one read of a clear-on-read statistics register,
  which empties it; the count read covers the interval since the previous reading.
- **Reading**, **round** (of a verifier) — one fresh `spec-verifier` reader's pass over the
  changed claims with a verdict per claim, as in [SR-7](SR-7.md#terms); rounds are sequential
  until a round reports no FAIL.
- **Candidate** — `e1000_l02`, the driver last rebuilt from revision 6 in CF-1; its result
  stands on revision 7 and does not cover this revision's rule.

See the [glossary](../GLOSSARY.md), the [plan](../IMPLEMENTATION-PLAN.md) (follow-ons named
in L02f3) and the [notebook chapter](../notebook/SR-8.md).

## Status

**Complete, 2026-09-26.** Revision 8 is revision 7 plus ten hunks: the TNCRS attribution rule
the user chose, written into §4.7, §5.5 and §5.9 with its argument, and SR-7's three wording
items. **It changes a requirement on a driver**, and the header says so and says that the
current candidate (CF-1's, written from revision 6) does not yet follow it. Two sequential
fresh readings of the changes: round 1 found 50 PASS, 3 FAIL, 1 GAP (two page numbers one page
off, a reviewer count, and the rule's starting point with no step in §5.5), all applied; round
2 found **68 PASS, 0 FAIL, 1 UNVERIFIABLE** (whether the rendering's code point is the micro
sign on the four further pages G-16 now lists; no PDF in this store). Revision 8 is 1,686
lines, SHA-256 `e0f17ffa443d50e6ca97c918cd23adedd71cbe1b92857d4aae4e4d693e6326d7`, landed in
private run `e1000-sr8-20260926-01` with its ledger PASS line. The next candidate round, which
would implement the rule, is not approved and is listed for the user below.

## The rule, as revision 8 writes it

The user chose CF-1's reviewer-A rule on 2026-09-26 ("drain at link change"). Revision 8
states it in §4.7's TNCRS row, as an `[inference]` that carries a policy (§1's row requires
premises, confidence and a verification method of such an inference), and as a new step L6
in §5.9:

- The counter is read, and so cleared, at the periodic statistics poll and at every
  link-status change, up or down.
- Each reading's count is credited to the duplex in force since the previous reading, never
  to the duplex read at the time of the reading: the driver keeps the STATUS.FD value sampled
  at the previous reading, credits by it (reports the count if that value was full duplex,
  discards it otherwise), then samples FD again for the interval that starts. The record
  starts at §5.5's clearing read, which samples FD for the first interval.
- Both readings are taken under one lock (the statistics lock §10.3's accumulator takes), and
  a reading is never skipped because the link is down.

Premises, cited to the manual except where the spec's own configuration is the premise: the register clears when read (§13.7 introduction); it is
valid only in full duplex (§13.7.12); in this spec's configuration the duplex is resolved by
auto-negotiation and never forced (G1, G7), STATUS.FD reports the duplex "as set by either
Hardware Auto-Negotiation function, or by software" (Table 13-5) and ICR.LSC is "set each
time the link status changes" (§13.4.17), so a new duplex arrives only with a link change;
and the counter "only increments if transmits are enabled" (§13.7.12), which this spec does
not tie to the link, so a reading skipped while the link is down loses no count but moves it
into the next interval. The residual the row states: counts that accrue between the
hardware's change and the driver's reading at that change go to the previous duplex, an
error bounded by the link task's latency instead of the poll period. Confidence medium for
the premise that rests on the spec's own configuration; the verification is on hardware over
a 10/100 link whose partner switches duplex, informative only where half duplex is involved
(G-12). §12.6 records the gap (filed by CF-1's implementer and by two of its reviewers, the
reference review and the `review-swarm`) as resolved by this rule.

**A driver-requirement change.** The header says so, and says that the candidate written
from revision 6 does not yet follow it (it credits each poll's count to the duplex read at
the poll and drains nothing at a link change, [CF-1](CF-1.md) A-F5 / C-F1). The next candidate
round would implement it; that round is not approved and is listed for the user in the plan.

## Method

| Step | Result |
| --- | --- |
| Inputs | Revision 7 (`ae18af99…`, 1,685 lines), copied from its run and hashed; the manual's text rendering (`66d93b63…`; no PDF in this store); the L02c whitelist (362 lines, 347 entries) and map; for the two `[kernel]` bullets revision 8 touches, the pinned v6.12 tree's `include/` and `Documentation/` only; [CF-1](CF-1.md)'s public evidence for the rule and the candidate's current behavior; [SR-7](SR-7.md)'s three items. No driver source, no QEMU source; CF-1's private reviewer reports were left unopened (reviewer A's names reference functions as locations) |
| Revision 8 | Edited on a working copy of revision 7 from the manual text (§13.7's introduction, §13.7.12, Table 13-5, §13.4.17's LSC row, read in the shell by printed page), the spec and the public evidence. The rule's premises were each located in the manual before the row was written; the G-16 page list was made by counting every occurrence of the code point in the rendering and mapping each to its printed page by form feeds (twelve on ten pages) |
| Reverification | Fresh `spec-verifier` readers on the r7→r8 changes and their dependencies, each given revision 7, the working copy, the diff, the manual text, both scan reports, the two kernel directories, CF-1's evidence (three sections, for the header's candidate statement and §12.6's filers), the skill text and the format's `[inference]` class; neither given the other's record. Round 1 (9 hunks): 54 verdicts, 50 PASS, 3 FAIL, 1 GAP; the FAILs, the GAP and the reader's three notes applied. Round 2 (10 hunks): 69 verdicts, **68 PASS, 0 FAIL, 1 UNVERIFIABLE**; clean-room check of the changed hunks PASS in both rounds; the landed record carries the landed hash. Each round answered, hunk by hunk, whether what a driver must do changed: round 1 (no §5.5 hunk yet) named §4.7's row, §5.9 L6 and §10.3's placement; round 2 named §4.7's row, §5.5's sample and §5.9 L6, with §10.3 only as their HALF 2 placement, and the other six hunks not |
| Leak scans | Revision 7 (baseline), both drafts (the second is the landed file) and the two verification records, with the L02c whitelist against the 7 reference driver files at the pinned commit: the spec scans clean; the records report six kernel API names (spinlock, delayed-work and carrier helpers) that the readers quoted while confirming §10.3's unchanged `[kernel]` `file:line` citations hold their symbols; judged not reference-driver identifiers (the reference driver uses the same public API, which is what the scanner matches), and the records stay private in any case |

## Revision 8

Built on revision 7 in the run store; the working copy, the r7→r8 diff (10 hunks; round 1's 9-hunk diff was overwritten and reproduces from revision 7 and the kept round-1 copy), both
briefs, the verification records, the scans and the ledger stay there.

| Passage | Change | Source |
| --- | --- | --- |
| Header | Revision 8, four items; the requirement-change statement; the candidate's current TNCRS behavior | — |
| §1 tag table, `[inference]` row | The verification method may be "none needed" with the reason why (R6: the step's own poll checks it; E5: the choice is the implementer's and either keeps the claim) | SR-7 item 2 |
| §4.7 TNCRS row | The rule above, with its four premises, derivation, residual, confidence and hardware verification; the row's first sentence now speaks of intervals | The user's choice; CF-1 A-F5 / C-F1 |
| §5.5 | Sample STATUS.FD at the clearing read and keep it as the duplex the first TNCRS interval is credited by (tagged `[inference]`, the rule's starting point); round 1's GAP | The rule; the round-1 reader |
| §5.2 R7 | The precondition's parenthetical gives both reasons CTRL bit 20 can read 0 before the write (the signature bits, Table 13-3 footnote 2; an earlier iteration of the test in the same power cycle) and says to repeat only after a power cycle | SR-7 item 3 |
| §5.9 | New step L6 (drain TNCRS under the statistics lock on every change, credit by the duplex recorded at the previous reading, record L1's FD for the next interval); the order paragraph now covers L1–L6 | The rule |
| §10.3 Link reporting | The link task drains TNCRS under the statistics spinlock (L6); the periodic accumulator credits TNCRS by the rule and shares the lock with L6; kernel citations unchanged | The rule |
| §12.1 G-16 | The four further pages where the rendering holds the private-use code point at values the spec uses (printed pp. 295 ITR, 309 RADV, 319 TIDV, 321 TADV), the three it does not cite (pp. 5, 172, 204), the count (twelve occurrences on ten pages) and the PDF arithmetic | SR-7 item 1; the count made in this unit |
| §12.2 Statistics row | Names the attribution rule as a spec choice, hardware-verifiable only | The rule |
| §12.6 | New row: the gap, its filers (CF-1's implementer, reference review and `review-swarm`) and its resolution | CF-1 |

## A1 after this unit

| A1 clause | Revision 7 | Revision 8 |
| --- | --- | --- |
| Two verification readings | Six sequential readings until clean, the final text read once ([SR-7](SR-7.md)) | Not met as independent readings: two sequential fresh readings until clean, the final text read once (the same shape); a second independent reading is the procedure of AF-1 and SR-7, when wanted |
| No unresolved FAIL | None open | None open: round 2 is 68 PASS, 0 FAIL |

What remains under A1: revisions 7 and 8's changes read once each in their final form; recall
measured on revision 3 only.

## Items for the next spec revision (none applied here)

All four are the round-2 reader's notes: items 2 and 3 from its reply (recorded in the
ledger), item 1 from a note in its record (§5.2/R7/precondition/2) and item 4 from its
record's frontmatter; none was a finding, and none was applied because a fix pass that adds words needs its own reading
([SR-7](SR-7.md), Limitations).

| # | Passage | Item |
| --- | --- | --- |
| 1 | §5.2 R7 precondition | The parenthetical lists two causes of a 0; any other earlier software write of CTRL bit 20 in the same power cycle is a third of the same kind, and the handling already covers it |
| 2 | §5.5, §4.7 | The FD sample at the clearing read is taken before the link is up, and Table 13-5 gives FD an initial value of X, so the first, link-down interval is credited by an unspecified value; harmless while nothing transmits without link, and worth a sentence |
| 3 | §5.5, §5.9 L6 | Both `[inference]` tags give their premises by reference to §4.7's row; a strict reading of §1's row could ask for a one-clause premise inline |
| 4 | records | The pinned Linux tree on the test host is a plain directory named by the commit, not a checkout; the records say so |

## Open items for the user

| Item | Recommendation |
| --- | --- |
| **The next candidate round** (implement the attribution rule; the file header's revision number, CF-1's C-F4; revision 8 as its spec) | Approve it as one unit on the CF-1 pattern (one audited clean-room round, the acceptance set, the L01 review trio). It is the user's Codex launch. Until it runs, the candidate on the shelf does not follow §4.7's rule, which no scenario can observe on the emulated device (its link never changes duplex, [CF-1](CF-1.md)) |
| Hardware verification of the rule (HF-1) | The row's method needs a 10/100 link whose partner switches duplex; add it to HF-1's list with CF-1's FWE and half-duplex TNCRS items |

## Checks

| Check | Result |
| --- | --- |
| `utilities/check-no-private-paths.py` | OK |
| `git diff --check`; privacy grep of the diff (addresses, host names, machine names, home paths, MAC addresses) | clean; one hit, `frame-sizes` in a context line, not private |
| `spec_check.py` | Not applicable to this spec (no YAML frontmatter, not a `*.spec.md` under a root); the readers judged the `[inference]` shapes against §1's row and the format's class |
| Leak scans (L02c whitelist, 7 reference files at the pinned commit) | revision 7 clean; both drafts clean; the verification records: six kernel API names, judged above |
| Changed surface | documentation and the private spec only: no test surface changed; the full suite runs in CI |

## Measures

- Operator time: about 09:12 to the final checkpoint on 2026-09-26 (Pacific), one session,
  interrupted from about 09:38 to 10:10 by an API spend limit (resumed from disk). Model cost
  not measured.
- Readers, harness-reported (figures in the ledger): round 1, 7.7 minutes; round 2, 8.1 minutes.
- Human review effort: none during the unit, beyond choosing the rule.

## Review

The unit's verification artifacts are the readings themselves (the two records in the run
store, and the round-1 record and reviewed draft kept beside them). After the pre-review
checkpoint, one fresh, read-only reviewer (same model family as the implementer) read the
public records against the ledger, the brief, the diff, the scans, the three verification
records, the provenance ledger and the landed passages; its report is in the run store under
`review/`. It confirmed every hash, line count, hunk count, verdict count and scan result
quoted here, the three FAILs and the GAP as described and fixed, the header's statements
against CF-1, the rule's bullets against §4.7 and L6, the three SR-7 items, the four
next-revision items, the A1 table, the plan's "awaiting the user", the absence of private
infrastructure, and every ledger time against file times; it judged broader review
unnecessary. Ten findings, two medium, all applied:

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| F1 | medium | The Revision 8 table had nine rows for a ten-hunk diff: the §5.5 hunk had none | Row added |
| F2 | medium | "The rule" repeated the wording round 1 had failed in the spec ("both of its reviewers") | The landed wording |
| F3 | low | "9 hunks" for the diff in the store (10; round 1's 9-hunk diff was overwritten) | Corrected, with where round 1's diff reproduces from |
| F4 | low | The per-hunk answers were attributed to both rounds; round 1 had no §5.5 hunk | Attributed per round |
| F5 | low | Two next-revision items attributed to the reply are in the record; two glosses were the implementer's | Attributed to the record; glosses dropped; the ledger's entry corrected with a note |
| F6 | low | Checks said "no hits" where the ledger records one non-private hit | Said |
| F7 | low | The index's "Updated" time postdated the commit carrying it (SR-7's F8 again) | Set at the final edit before the post-review checkpoint |
| F8 | low | The Review section described the records review in the past tense before it ran | This section, written after it |
| F9 | info | Two notebook entries restate the rule's argument and round 1's findings (SR-7 F9's class) | A correction entry in the append-only chapter |
| F10 | info | "Premises, each cited to the manual" (premise 3 is the spec's configuration and an assumption); the rule statement omitted §5.5's sample | Wording |

## Limitations

- Every reader and the implementer share a model family; no human read the changes.
- The rule cannot be exercised on the emulated device (its link never changes duplex, per
  [CF-1](CF-1.md)); its correctness rests on the argument in §4.7's row, which two readers
  passed, and on a hardware test not yet run.
- Premise (3) of the rule (a new duplex arrives only with a link that came up) rests on this
  spec's configuration and on an assumption the row states; the confidence is medium for it.
- No PDF in this store: whether the code point on the four further pages renders as the micro
  sign is UNVERIFIABLE here, as G-16's "checked on the PDF" was in SR-7.
- Revision 8's changes were read twice sequentially and the final text once, not twice
  independently; the same A1 shape as revision 7.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
