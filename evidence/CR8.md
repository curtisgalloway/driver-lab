<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR8: live items through a revision (spec revision 9)

## Terms

- **Spec** — the clean-room implementation spec for the Intel 82540EM (e1000) core network
  path ([L02b](L02b.md)); **revision 8** is SR-8's ([SR-8](SR-8.md)); **revision 9** is this
  unit's, built on revision 8. HALF 1 covers the hardware; HALF 2 (§10) the Linux integration.
- **R/E/W item** — a finding that changes what a driver must do / the evidence for a claim /
  only wording or form (the design's C6). **Round** — one fresh reader's verification reading
  of the current working copy; rounds are sequential, and the design caps them at three per
  revision, with fixes after round two allowed only to delete or narrow text (C6).
- **Clean-room wall** — the rule that the spec carries observations of the encumbered source
  driver, never its code or its reasoning.
- **NAPI** — the Linux network stack's polled receive interface (`napi_schedule_prep()`,
  `napi_enable()`, `napi_disable()`), cited from the kernel's `include/` and `Documentation/`.
- **Sweep**, **S1–S5**, **tier 1 / tier 2** — as in the
  [design](../DESIGN.md#continuous-review-keeping-specs-right-as-evidence-changes).

See the [glossary](../GLOSSARY.md), the
[plan](../IMPLEMENTATION-PLAN.md#cr8--one-live-item-through-a-revision-conditional) and the
[notebook chapter](../notebook/CR8.md).

## Status

**Complete, 2026-09-27, with two requirement items left for the user.** Revision 9 applies
every spec item queued for it: CR6b's twelve R findings, its 41 E and 28 W adjudicated lines,
the CR6a correction to §4.7's TNCRS argument (the user's option b), SR-8's items 1–3 (item 2
widened) and CF-2's A-RR-1. **It changes requirements on a driver**, and its header says so,
item by item. Three sequential fresh readings by Codex `gpt-6-astra` (the manifest's reader
role), the cap: round 1 **344 PASS, 17 FAIL, 3 UNVERIFIABLE, 1 GAP** with the clean-room check
FAIL; round 2 **301 PASS, 2 FAIL, 3 UNVERIFIABLE**, clean-room PASS; round 3 **338 PASS, 2
FAIL, 3 UNVERIFIABLE**, clean-room PASS. Every FAIL after round 2 was fixed by deletion, as the
cap requires, and the landed text differs from round 3's by three deletions that no reader
has read; one round-3 FAIL is only partly fixed by its deletion and is queued as a W item. Revision 9 is 1,800 lines, SHA-256
`0fd7bc0a6bd4ad181af26a7e5f20d50c1fbaa312a3248470aca31623f03f261a`, landed in private run
`cr8-20260927-01` with its ledger line. C5's live-item criterion is met (below). The remainder
list goes to the user.

## The user's decisions this unit ran under

Recorded 2026-09-26/27 and relayed by the orchestrator; the relay's exact text is saved in the run as
`review/orchestrator-relay-decisions.md` (SHA-256 `27768d41…4230`), which the quotations below are from:

1. **Scope:** "one revision (revision 9) applies all 12 CR6b R findings (`CR6b-R-*`), the E and
   W aggregate items bound for CR8, and the CR6a TNCRS fix."
2. **TNCRS, option (b):** "keep §4.7's link-down TNCRS reading as a stated design choice and
   replace the false justifying clause with its real reason (no change to what a driver must
   do)", folding in CR6b's related findings, with SR-8-2 riding "as a wording fix if it fits".
3. **Reader role** stays Codex `gpt-6-astra`.
4. **The four `[source-observed]` clauses that state the Linux driver's reasons:** "the
   clean-room check in this revision judges each, and any that cross the wall are rewritten to
   state only observable facts."

The PCI configuration-read question (does such a read flush the posted reset write? the manual
is silent) rides as an E item: R6 now states it as open. The CF-n candidate round is not part
of CR8. Where CR6b's table left a fix open, the **orchestrator decided** within the user's
scope, on the implementer's recommendation: RLEC alone; the driver drops PIF multicast packets
not in the joined list; one unmanaged ownership model in probe; `max_mtu` set to 1500;
`ndo_stop` uses a mask lock and a stopping flag. The orchestrator also accepted that CF-2-AR-10
(an `[emulated]` note that the model reads STATUS.FD = 1 with no link) stays queued: it needs
an extract item of its own. SR-8-1, SR-8-3 and A-RR-1 rode because the design says W items
wait for "the next revision made for another reason", which this is.

## Method

| Step | Result |
| --- | --- |
| Inputs | Revision 8 (`e0f17ffa…`, 1,686 lines), copied from SR-8's run; the manual's text rendering (`66d93b63…`, no PDF); the pinned v6.12 tree's `include/` and `Documentation/` only; CR6's adjudications and CR6b's record (its non-PASS lines and notes); the public evidence of CR6a, CR6b, SR-8 and CF-2; the L02c whitelist (347 entries). No driver source, no QEMU source |
| Revision 9 | Edited on a working copy of revision 8 from the manual (read by printed page) and the kernel documentation, every changed line re-derived from its authority |
| Authoring pre-check | Before round 1, one fresh Claude Opus 5.5 reviewer read draft 1's hunks against the manual and the kernel documentation (557 s, 199,314 tokens): 18 findings, one error (a delayed link work canceled with the plain-work call) and two races the draft left (the link task re-enabling the carrier after `ndo_stop`; a shared-line interrupt reading ICR inside R6's 1 µs); all applied. Not a verification round; no reader saw it |
| Rounds | Each round: a new workspace holding only the brief and its inputs (revision 8, the working copy, the diff, both leak-scan reports, the M1–M8 observations extract, the verifier and format texts), no earlier record; `codex exec` in its read-only sandbox, launched by the orchestrator, which checked the brief's and inputs' hashes first. The brief asked, per hunk, whether what a driver must do changed, and asked the clean-room check to judge the four reason clauses and G-4 |
| Adjudication | The implementer, against the cited authority, before any fix; every decision in the run's ledger |
| Leak scans | L02c whitelist against the 7 reference driver files at the pinned commit: revision 8 clean; every draft and the landed text 0 shared runs and 0 all-caps identifiers; lowercase identifiers four in drafts 1 and 2 (a delayed-work cancel, a multicast-address test, the maximum-MTU field, the irq-saving spinlock call) and five from draft 3 on (adding the running-state test), each a Linux interface HALF 2 now names and cites from `include/`, the class SR-8 and CR6a judged; the three records: the same names (four in round 1's, five in rounds 2 and 3's) |

## Revision 9

The working copy, the r8→r9 diff (48 hunks), the drafts, the three records, the scans and the
ledger stay in the run store. Requirement changes, as the header numbers them:

| # | Passage | Change | Item |
| --- | --- | --- | --- |
| 1 | §5.9 L6 and its order paragraph; §10.3 link task | L6 takes its own STATUS.FD sample inside the statistics lock, with the TNCRS drain | `CR6b-R-L6-lock` |
| 2 | §4.7 RLEC, RUC, ROC rows | Report RLEC alone; RUC and ROC count only valid-CRC frames | `CR6b-R-RLEC` |
| 3 | §6.1, §6.5, §10.3 receive path, §11 M5 | Packets that passed only the multicast hash (PIF) are examined as Table 3-2 requires; outside promiscuous and all-multicast modes a multicast packet not in the joined list is dropped | `CR6b-R-PIF` |
| 4 | §6.3 | A ring holds at most 65,528 descriptors (LEN is bits 19:7) | `CR6b-R-ring-len` |
| 5 | §7.5, §10.3 handler, §12.2 | Check that the poll can be scheduled, then mask, then schedule (napi.rst) | `CR6b-R-napi-schedule` |
| 6 | §10.3 `ndo_open`, §5.10 D6 | `request_irq()` and `napi_enable()` between §5.7 and §5.8; statistics accumulator started after §5.8 | `CR6b-R-ndo-open` |
| 7 | §10.3 `ndo_stop`, poll, `ndo_tx_timeout` | D4's mask under a mask lock with a stopping flag the poll checks (set from probe, cleared just before I2); link work and statistics accumulator stopped synchronously before the reset; carrier off again after them; the timeout work takes RTNL, acts only while running, and is canceled in remove() | `CR6b-R-ndo-stop`, `CR6b-R-stats-cancel` |
| 8 | §10.3 probe, `ndo_change_mtu`, §11 M7 | One unmanaged ownership model; a 64-bit DMA mask with no fallback; `max_mtu` = 1500 | `CR6b-R-probe-regions`, `CR6b-R-probe-dma`, `CR6b-R-mtu` |
| 9 | §10.3 remove() | Unmap, disable, then release (pci.rst) | `CR6b-R-remove-order` |

**§4.7's TNCRS row** requires nothing new beyond item 1 and a clarification that extra
readings are allowed (A-RR-1). Its argument is corrected: the false clause about gated readings
is gone, and the reading at a link-down change is stated as a design choice with its reasons
(L6 then drains on every change without testing the link; the transmitter defers when the link
is not up, §13.7.11, so nothing is expected to be counted, with EM5's contrary model behavior
named); "What remains" says the rule shortens the misattribution window rather than improving
every count (the sentence and confidence that said otherwise are gone, CR6b's TNCRS/11 and
/13), and that every interval starting with the link down is credited by an FD value the
manual does not define (SR-8-2, widened); the verification says what it cannot resolve. §5.5
states its premise inline (SR-8-3); §12.6's row records the correction.

**Evidence and wording** (the 41 E and 28 W lines, SR-8-1): citations, quotations, tags,
confidences and verification clauses across §1, §4.0–§4.8, §5.2–§5.10, §6.2–§6.4, §7.4, §8.1,
§8.2, §8.4, §9.1, §9.4, §11 M4, §12.1, §12.2, §12.3, §12.5 and §12.6, including R6's margin (an
assumed posted-write latency, confidence medium, what no check shows, the open question on
configuration reads) and R7's test (read CTRL bit 20 after the 5 ms wait; the earlier-write
cause of an early 0 widened from an earlier iteration of the test to any earlier write). Three passages correct HALF 2 or a conditional recommendation to agree with rules
already in the spec, with no new requirement: CTRL_EXT handling, probe step 7 (E5's choices)
and the receive length with SECRC = 1.

**The clean-room judgment** (the user's decision 4): round 1 judged all four reason clauses
(§5.2's I/O-window reset, §5.5's clearing placement, §5.6 X2's untouched entry 15, §6.4's
software pad) to carry the source driver's reasoning; each lost its reason and keeps only the
observation. G-4's reason clause was removed in draft 1 on CR6b's disposition, and round 1
judged the rest of G-4 clean. Rounds 2 and 3 passed all five.

## The rounds

| Round | Text | Verdicts | Clean-room | Minutes, tokens (Codex-reported) | What was done |
| --- | --- | --- | --- | --- | --- |
| 1 | draft 2 (`5b779706…`) | 344 PASS, 17 FAIL, 3 UNVERIFIABLE, 1 GAP | FAIL (the four clauses) | 8.4, 207,372 | 16 FAILs and the GAP upheld and fixed, one partly (X9: §14.4 states the RDTR sentence twice, once for every part); the clauses rewritten |
| 2 | draft 3 (`9c53a94f…`) | 301 PASS, 2 FAIL, 3 UNVERIFIABLE | PASS | 14.4, 221,510 | Both FAILs upheld; both are missing mechanisms, so under the cap only the overstating text was deleted (remainder below) |
| 3 | draft 4 (`1f598447…`) | 338 PASS, 2 FAIL, 3 UNVERIFIABLE | PASS | 13.9, 225,632 | Both FAILs wording. The E3 quotation's capitalization: fixed by deleting the quotation marks. §12.3's attestation naming only §8's kernel citations: deleting "alone" removed the false "only", but the bullet still omits §4.7's citation, so it is partly fixed and queued as `CR8-W-attestation-kernel`. The header's "every changed passage named" was deleted too, since the §12.3 change is not in its list |

The UNVERIFIABLE lines are input limits: in rounds 2 and 3, the header's attribution to the
CR6b reading, its statement about CF-2's candidate (records the brief excluded) and the manual's
micro sign at R6 (no PDF); round 1 read the two header claims as one line and marked R6's stated
posted-write assumption UNVERIFIABLE instead. Rounds 2 and 3's per-hunk requirement answers
matched the header's items; round 1's did not match draft 2's header, which was its
Header/revision/2 FAIL (three HALF 2 corrections unnamed), fixed in draft 3. Round 3 found no
remaining race in the interrupt, open, stop and remove sequences as written; it read a text in
which round 2's two mechanisms were still unspecified (only their overstating sentences had
been deleted) and did not flag them again, so its note does not settle them.

## Remainder for the user

Round 2's two findings name protocol the spec now needs but the cap would not let this revision
add. Both are indexed as R items queued for the user's decision, so the sweep lists them as
tier-2 requirement-change units.

| Index ID | Class | Finding | Recommendation | Options |
| --- | --- | --- | --- | --- |
| `CR8-R-poll-tail-reopen` | R | A poll that stalls after `napi_complete_done()` across a close and the next open can unmask during the new open's poll (napi.rst keeps interrupts masked while a poll is scheduled) | Fix in the next revision with (a) | (a) The poll calls `napi_complete_done()` and makes its unmask decision under the mask lock, so `ndo_stop`'s flag orders against both; (b) a per-open generation number the poll records before completing and checks before unmasking; (c) state it as a benign race (an extra interrupt during a poll finds the prepare step failing and does nothing) and keep the spec as it is |
| `CR8-R-timeout-quiescence` | R | The transmit-timeout recovery does not exclude a concurrent `ndo_start_xmit` or a completion-driven queue wake while it resets (RTNL does not serialize transmit) | Fix in the next revision with (a) | (a) Recover through the stack's own close and open under RTNL, which quiesce transmit; (b) a driver recovery state: `netif_tx_disable()` (takes the TX lock), completion wakes suppressed until reinitialized, restart after success; (c) narrow recovery to a reset that keeps the rings and never frees buffers under a running transmit |

Other open items after this unit:

- **Two independent readings (C5, S4).** Revision 9 changes requirements, so its text needs
  two independent readings before e1000 is sufficient; the three rounds are one sequential
  lineage, and none read the landed bytes. The sweep queues the second reading (tier 1). It is
  held ("awaiting decision") while R items are open.
- **The next candidate round** (CF-n on revision 9) is tier 2, the user's launch.
- **CF-2-AR-10** stays queued for a later revision (a replacement entry, `CF-2-AR-10-r9`, gives
  it that destination, since revision 9 was the one its old destination named).
- **`CR8-W-attestation-kernel`** (W): §12.3's HALF 1 attestation still names only §8's kernel
  citations, though §4.7's octet note now cites the kernel too; for the next revision.

## After this unit

The index records revision 9's header (requirement change, 32 changed sections, the 19
applied items), the three rounds as draft readings with their cost, each applied item as a new
entry `<id>-r9` (disposition `applied`, revision 9) that supersedes the queued one, and the two
remainder items, the partly fixed attestation (W) and CF-2-AR-10's replacement. The revision-8 readings are stale since revision 9. `sources.yaml` pins the
spec at revision 9; the pinned-file adapter matches. The sweep after landing (exit 1):

| Condition | Before CR8 | After CR8 |
| --- | --- | --- |
| S2 | 13 stale qualifications | every qualification but Q23's stale (revision 9 changed sections all but one claim cites); Q23 has no qualified PASS in an accepted class |
| S3 | AF-1's item; twelve open R items; four readings with accuracy FAILs | AF-1's item; the two remainder R items (the W item does not block) |
| S4 | revisions 3–6 at 1/2 | revisions 3–6, 8 and 9 at 0/2 (the whole-text CR6b reading is stale) |
| S5 | CR6b produced R items | unchanged: CR6b is still the latest independent reading |
| Round cap | revision 8 pre-cap history | revision 9: three rounds, "limit reached", remainder to the user |

The queue: 27 requalifications and an acceptance-set rerun (tier 1, ready); the second reading
and two re-verifications (tier 1, held); the two remainder items and two outward reports
(tier 2, awaiting decision).

**C5's second criterion is met:** live W and E items (SR-8-1, SR-8-2, SR-8-3, A-RR-1, the CR6b
aggregates) were carried through a revision with the index updated at each step and the queued
entries superseded. **C6's "no W item alone started a revision" holds:** R items and the user's
decision started it.

## Checks

| Check | Result |
| --- | --- |
| `index_check.py evals/e1000` | OK: 28 claims, 71 items, 102 verification entries |
| `sweep.py evals/e1000` | not sufficient, as above; exit 1 |
| `pinned_file_adapter.py` on the spec | matches the pin |
| `campaign-review` tests | 115 OK. The baseline tests now also read the source registry as it stood before this unit (`tests/fixtures/e1000-sources-cr7.yaml`), since the live registry pins revision 9, which the frozen index does not have; the live sweep's stale count is 144 |
| `utilities/check-no-private-paths.py`; privacy grep of the diff | see Review |
| `spec_check.py` | Not applicable (this spec has no frontmatter) |
| Leak scans | above |

## Measures

- Implementer time: 07:22 to landing at 08:36 on 2026-09-27 (Pacific), plus the records.
- Readers (Codex-reported): 8.4, 14.4 and 13.9 minutes; 207,372, 221,510 and 225,632 tokens.
- Authoring pre-check: 9.3 minutes, 199,314 tokens.
- Human review effort: the user's four scope decisions; the orchestrator's five fix options.

## Review

After the pre-review checkpoint, one fresh, read-only Claude Opus 5.5 reviewer read this file,
the index and registry changes, the test change and every run artifact (records, workspaces,
drafts, logs, scans, ledger); its report is in the run store under `review/`. It confirmed
every hash, line and hunk count, verdict count, time and token figure, the header table
against the landed header, the 32 changed sections (recomputed from the diff), all twelve R
fixes located in the landed text, the superseded and stale entries, that each round's workspace
held no earlier record and that every change after round 2 is a deletion, the frozen test
fixture byte for byte, the sweep table against live runs before and after, and the absence of
private infrastructure. Two medium findings, seven low and three informational, all applied:

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| RR-1 | medium | The user's decisions were quoted with no run artifact holding the words | The relay text saved in the run and cited; quotations checked against it |
| RR-2 | medium | Round 3's §12.3 FAIL was recorded as fixed; the deletion removed only "alone" | Recorded as partly fixed; `CR8-W-attestation-kernel` queued |
| RR-3 | low | "The same three UNVERIFIABLE in every round" is wrong for round 1 | Stated per round |
| RR-4 | low | Round 1's per-hunk answers did not match draft 2's header | Said, with the FAIL it was |
| RR-5 | low | Four kernel identifiers in drafts 1–2, not five | Stated per draft |
| RR-6 | low | Round 3's "no remaining race" note needs its context | Caveat added |
| RR-7 | low | The notebook used a word the house style avoids | Reworded |
| RR-8 | low | The plan still said CR7 was landing | "CR7 complete (PR #35)" |
| RR-9 | low | CF-2-AR-10's destination was the revision that passed it | Replacement entry `CF-2-AR-10-r9` |
| RR-10 | info | The ledger said "; it" became ". Because"; it was a pure deletion | Ledger corrected |
| RR-11 | info | "A third cause" is a widening of the second | Reworded here |
| RR-12 | info | The notebook said revision 9 staled 27 qualifications; 13 were already stale | Correction entry |

## Limitations

- Every reading is one model's (`gpt-6-astra`), three sequential rounds; the implementer and the
  pre-check reviewer share a model family; no human read the changes.
- The landed text has not been read: it differs from round 3's text by three deletions made
  under the cap.
- The readers' isolation was by instruction and workspace contents: in each round Codex read
  the source-tree conventions file above its working directory before the brief (it loads such
  files by default). That file holds no records; no reader read an earlier record, driver
  source or QEMU source.
- The new HALF 2 protocol (interrupt, open, stop, remove, recovery) is argued from the kernel
  documentation; no candidate implements it yet and no run has exercised it.
- No PDF: the micro-sign rendering stays UNVERIFIABLE.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
