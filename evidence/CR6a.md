<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR6a: a second independent reading of spec revision 8's changes

## Terms

- **Spec** — the clean-room implementation spec for the Intel 82540EM (e1000) core network
  path ([L02b](L02b.md)); **revision 8** ([SR-8](SR-8.md)) added the TNCRS attribution rule,
  a driver-requirement change.
- **TNCRS** — the controller's "transmit with no CRS" statistics register, cleared when read
  and valid in full duplex only; revision 8 says which duplex each reading's count is credited
  by (§4.7's row, §5.9 step L6).
- **Reading** — one fresh `spec-verifier` reader's pass with a verdict per claim; a **lineage**
  counts one reader's sequential passes once. **Join** — matching two readings' records key by
  key (section and item). **Adjudication** — deciding a disagreement against the cited
  authority, here by a fresh reviewer.
- **Tier-1 unit**, **batch**, **R/E/W item**, **S1–S5** — the continuous-review terms in the
  [design](../DESIGN.md#continuous-review-keeping-specs-right-as-evidence-changes): queued agent
  work; at most three units; an item that changes what a driver must do, the evidence, or the
  wording; the stopping rule's conditions.

See the [glossary](../GLOSSARY.md), the [plan](../IMPLEMENTATION-PLAN.md#cr6--the-first-tier-1-batch)
and the [notebook chapter](../notebook/CR6.md).

## Status

**Complete, 2026-09-26; the first tier-1 unit run from the queue.** A fresh Claude Fable 5.1
reader (the deployment manifest's reader role), with no sight of SR-8's records, read revision
8's ten changed hunks and their declared dependencies: **62 verdicts, 60 PASS, 1 FAIL, 1
UNVERIFIABLE**, clean-room check PASS, 8.8 minutes and 228,623 tokens (harness-reported). Joined
to SR-8's round-2 record, the two agree on 67 of its 69 keys; one key was read once and one
disagrees. A fresh Claude Opus 5.5 reviewer adjudicated the disagreement for the new reading:
a sentence of §4.7's derivation is false under the rule it justifies, and **one R item goes to
the user as a revision decision** (below). No verdict was changed before adjudication and the
spec was not edited. Revision 8 now has two independent reading lineages; the campaign is still
not sufficient (below). Private run `cr6-20260926-01` holds the brief, inputs, record, join,
adjudication, scan and ledger.

## Method

| Step | Result |
| --- | --- |
| Queue | The sweep's first unit, `e1000:second-reading:current`, restricted by the plan's CR6a scope to revision 8. Its S4 requirement for revision 8 is the header's nine changed sections, so the brief covered all ten hunks, with §4.7's row, §5.5, §5.9 L6 and §10.3 as its focus |
| Brief | Written from the diff before the operator opened SR-8's records: ten passages keyed by section and item, the per-hunk requirement question, declared dependencies (§4.1, §4.3–§4.5, §5.3, §5.4, §5.7, §5.10, §11), and a forbidden list covering every earlier run and this repository |
| Inputs | Revision 7 (`ae18af99…`) and 8 (`e0f17ffa…`), the r7→r8 diff (10 hunks), the manual's text rendering (`66d93b63…`, no PDF), the pinned v6.12 tree's `include/` and `Documentation/`, both SR-8 leak-scan reports, a copy of [CF-1](CF-1.md)'s evidence, and the verifier and format texts, copied into the run and hashed |
| Reading | 62 verdicts as above; FAIL `§4.7/TNCRS/14`; UNVERIFIABLE `§12.1/G-16/8` (whether the manual's private-use code point renders as the micro sign on the PDF). The reader counted the code point independently: twelve occurrences on ten pages, as G-16 says |
| Join | `review/comparison.md`, SR-8 round 2's 69 keys: **67 same, 1 disagreement, 1 read once** (SR-8's check that CF-1's update was scoped to the revision-4-to-6 diff). The per-hunk requirement answers are identical: §4.7's row, §5.5 and §5.9 L6 change what a driver must do, §10.3 only as their HALF 2 restatement, the other six hunks not |
| Adjudication | A fresh Claude Opus 5.5 reviewer (recorded in the index under the basis role `reader`, which the checker requires of every verification basis, as CR2 recorded L02c's third reader) given both records, the join, the spec, the manual passages and the design's classes (2.7 minutes, 120,534 tokens); it spot-checked 22 join rows and found two record-keeping slips (the brief's file name; one note's relation to SR-8's item 2), both applied |
| Leak scan | L02c whitelist, 7 reference driver files at the pinned commit: revision 8 clean; the record 0 shared runs, 0 all-caps identifiers and one identifier shared with a reference driver file, the irq-saving spinlock call, quoted from `Documentation/kernel-hacking/locking.rst` to confirm §10.3's lock placement. It is a public kernel API name, the class SR-8's record scan flagged and judged the same way; the record stays private |

## The disagreement and its adjudication

§4.7's TNCRS row requires, among other things, that no reading be skipped because the link is
down, and its derivation justifies that with one clause: that a reading gated on link-up would
move a down interval's counts into the next link's interval, whose duplex may differ. SR-8's
round 2 passed the derivation whole; CR6a failed that clause.

**Adjudicated for CR6a, as an accuracy FAIL.** Under the rule itself, each reading is credited
by the duplex sampled at the *previous* reading. A driver that skipped readings while the link
was down would still read at the next link-up, and would credit the down interval's counts by
the previous link's duplex: they join the previous link's interval, not the next one's. The
clause describes the practice revision 8 replaced. It is also the only support the row gives
for the link-down half of the requirement, and no argument from premises (1)–(4) recovers it:
by premise (3) a new duplex arrives only with a link-up, so readings at the poll and at link-up
already split the counts by duplex, and the link-down reading only changes which duplex value
credits the down interval, a value the manual does not define without a link (Table 13-5
gives FD an initial value of X). The rest of the rule follows. A driver that obeys revision 8
is not wrong, and no observable count should differ, since nothing is transmitted without a
link.

## Items

| ID (index) | Class | Item | Disposition |
| --- | --- | --- | --- |
| `CR6a-link-down-reading` | R (R or E in doubt, so R by C6's rule) | §4.7's gated-reading clause is false under the rule; the requirement to read at a link-down change is unsupported by the stated premises. Affects §4.7's rule and derivation, §5.9 L6's "up or down", and the revision-8 header | **The user's revision decision** (the trigger for CR8); options below |
| `SR-8-2` (existing, W) | W | The first interval's duplex, sampled before link-up, is an undefined value. CR6a's reader raised the same point, prompted by the brief (it asked what STATUS.FD holds at the clearing read, so this agreement is not independent), and in a note on "What remains", unprompted, widened it to every interval that starts with the link down | Decided with the R item (the R item's index disposition names it): option (a) resolves it; under (b) or (c) it stays W, widened, for the next revision. SR-8-2's own entry is unchanged until that decision |

The decision for the user, with the reviewer's three options and the implementer's
recommendation first:

1. **(b) Keep the link-down reading as a stated design choice** and replace the false clause
   with its reason (uniform with L6's "on every change", harmless). No change to what a driver
   must do, so the next candidate round's work is unchanged; the widened SR-8-2 remains a W
   sentence. Recommended: the smallest change, nothing observable differs.
2. **(a) Treat an interval with no link as not full duplex**: record the link state with FD at
   each reading and discard the counts of any interval that began with the link down. The
   down reading then becomes necessary and SR-8-2 is resolved, but a driver must do more.
3. **(c) Drop the link-down reading requirement**, reading only at the poll and at link-up. A
   driver does less; the false clause goes with the requirement; the widened SR-8-2 remains a W
   sentence.

## The user's decision

On 2026-09-26 the user chose **option (b)**, asked by the orchestrator as a structured
question: keep the link-down reading as a stated design choice and replace the false clause
with its real reason. Nothing changes in what a driver must do, so the item is no longer R:
the index records the decision on a replacement entry, `CR6a-link-down-reading-decided`, class
E (the requirement's support, not the requirement), with no claim in scope affected. The
reading's accuracy FAIL stays open, and blocks S3, until a revision replaces the clause: that
revision is CR8, and this decision is its trigger. `SR-8-2` stays W, widened to every interval
that starts with the link down, for the same revision; the widening is recorded in the
replacement item's disposition, and SR-8-2's own entry stays as recorded until CR8 applies it. The spec was not edited.

## After this unit

`SR-8-independent-reading` is superseded by `SR-8-independent-reading-CR6a` (applied: the
second lineage exists). Its impact is recorded as no claim affected, because the item was about
reading coverage, which S4 counts, not about a claim's status; that is what clears its S3
blocker. The sweep after this unit (exit 1):

| Condition | Before CR6a | After CR6a |
| --- | --- | --- |
| S2 | 13 stale qualifications | unchanged |
| S3 | two review items with impact unrecorded | `AF-1-reading-coverage` impact unrecorded; the R item open; CR6a's reading and its adjudication carry an accuracy FAIL |
| S4 | revisions 3–6 at 0/2, revision 8 at 1/2 | revisions 3–6 at 0/2; **revision 8 met (2/2)** |
| S5 | met (latest independent reading SR-7's) | unmet: the latest independent reading, CR6a's, produced an R item |

The queue now holds a tier-2 `requirement-change` unit for the R item, awaiting the user's
decision, beside the two outward-report decisions. Revision 8's reading count is four (two
SR-8 rounds, this reading and its adjudication), reported as pre-cap history because the
revision started on 2026-09-26.

## Checks

| Check | Result |
| --- | --- |
| `index_check.py evals/e1000` | OK: 33 items, 97 verification entries |
| `sweep.py evals/e1000` | not sufficient, as above; exit 1 |
| `utilities/check-no-private-paths.py`; privacy grep of the diff (addresses, host and machine names, home paths, MAC addresses) | OK; no hits |
| `campaign-review` tests | 105 OK. The tests that pin the e1000 report now read a frozen copy of the index as CR5 left it (`tests/fixtures/e1000-status-cr5.yaml`), since every new index entry changes that report; the provenance consistency test still reads the live index, and CI's `index_check.py` checks the live index |
| Leak scans | above |
| Review | one fresh Claude Opus 5.5 reviewer of the records, index entries and test change against the run artifacts; see Review |

## Review

The unit's verification artifacts are the reading, the join and the adjudication (above). The
records were then read by one fresh, read-only Claude Opus 5.5 reviewer against the run's
ledger, the two records, the join, the adjudication, the scan and the sweep output; its report
is in the run store under `review/`. It confirmed every hash, verdict count, time and token
figure here, the index entries against the format, the sweep before and after, the frozen test
baseline (byte-identical to the index as CR5 left it) and the absence of private
infrastructure. Two medium findings, seven low and three informational, all applied or
recorded:

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| R-1 | medium | The adjudication's basis copied the reader's dependencies, not the passages it was pointed at | Dependencies set to §1, §5.10, §10.3, §12.1 |
| R-2 | medium | The provenance consistency test had moved to the frozen index, so nothing compared the live index with the public provenance table | That test reads the live index again |
| R-3 | low | The index did not record SR-8-2's fold into the R decision | The R item's disposition names SR-8-2 |
| R-4 | low | The brief asked SR-8-2's question, so that agreement was prompted | Said in the Items table |
| R-5 | low | "Not a reference-driver identifier" contradicted the scan | Reworded |
| R-6 | low | Checks pointed at a missing section | Results recorded |
| R-7 | low | Option (c) stated no consequence | Stated |
| R-8 | low | A 25-word spec clause quoted in public evidence | Paraphrased |
| R-9 | low | The replacement item's recorded impact was unexplained | Explained |
| R-10 | info | The Opus adjudicator is recorded under the role `reader` | Said in Method |
| R-11 | info | The round-cap report counts the adjudication as a reading | Recorded in the notebook for the stopping code, before a post-cap revision needs it |
| R-12 | info | Reading and adjudication both carry the FAIL, two S3 blockers for one finding | Conservative; kept |

## Limitations

- Both readers are Claude Fable 5.1 and share a model family with the spec's author; the
  independence is of context, not of model. CR6b's comparison reading by another model family
  is the check on that.
- The adjudicator is one reviewer; its classification of the item as R rests on C6's "R when in
  doubt", and the user may classify it otherwise.
- No PDF: G-16's micro-sign rendering remains UNVERIFIABLE in both readings.
- The queue's second-reading unit also asks for revisions 3–6, which CR6a's scope excludes;
  those gaps remain.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
