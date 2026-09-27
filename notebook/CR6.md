<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR6: the first tier-1 batch

**Terms:** a reading is one fresh verifier's pass with a verdict per claim; a lineage counts
one reader's sequential passes once; a comparison reading is a re-reading by a new reading
model, joined key by key to the last record. See the [glossary](../GLOSSARY.md).

## 2026-09-26T21:09:39-07:00 — recovered state and the CR6a brief

- The sweep's S4 requirement for revision 8 is the header's changed sections (§1, §4.7, §5.2,
  §5.5, §5.9, §10.3, §12.1, §12.2, §12.6), not only the four requirement-changing passages
  the plan names. A reading of the four alone would leave revision 8 at 1/2 lineages, so the
  brief covers all ten hunks, with the four as its focus and the rest as the same revision's
  text or dependencies.
- The queue's second-reading unit also lists revisions 3–6 at 0/2 (CR4's conservative
  widening). CR6a's scope is revision 8 only, so those gaps stay after it; CR6b, a reading of
  the whole current text, is the unit that can reach them.
- SR-8's brief referred to its own worktree for three inputs; that worktree is gone, so the
  public inputs were copied into the run and hashed rather than pointed at the repository,
  which the reader is forbidden to open (its evidence and index hold SR-8's results).

Private run `cr6-20260926-01` holds the brief, inputs and ledger.

## 2026-09-26T21:24:38-07:00 — CR6a reading, join and adjudication

- The reader's one FAIL was on a sentence SR-8's reader had passed inside a whole-derivation
  line. Splitting an `[inference]` into one line per part (the brief asks for it) is what
  exposed it: SR-8's derivation line bundled the main argument with the gated-reading clause.
- The adjudicator found the clause false under the rule's own crediting and the link-down half
  of "never skip a reading" unsupported, so the item is R (C6's "R when in doubt") and goes to
  the user. Nothing observable changes: without a link nothing is transmitted.
- The index checker requires a verification basis's model role to be `reader`, so the
  adjudication entry records its Opus reviewer under that role, as CR2 recorded L02c's third
  reader.
- The round-cap report counts the adjudication entry as a fourth accuracy reading of revision
  8 (historical, so no block). An adjudication is not a round; worth a rule in the stopping code
  before a post-cap revision needs one.
- After the entries, S4 holds for revision 8 (2/2) and S5 no longer does: the newest
  independent reading produced an R item.

## 2026-09-26T21:37:16-07:00 — CR6b prepared: reader role changed, comparison reading queued

- Changing the manifest's reader queued exactly one comparison reading, as C4 asks, and moved
  it into the current batch at priority 1 (second reading, comparison, re-verification of
  AF-1's item).
- The same change broke five tests: they asserted the reference manifest's reader or combined
  the live manifest with the frozen index. Like the index, the manifest is data the tests should
  not pin; they now read CR5's manifest as a fixture, and the default-loading tests compare with
  whatever the reference file declares.
- Codex's read-only sandbox cannot write a record, so the brief makes the record its final
  message, which `-o` saves. The workspace holds only the brief and its inputs; nothing
  earlier is in it, and the brief forbids the rest of the store. That is an instruction, not a
  wall, the same as for the Claude readers.
- The launch is the orchestrator's; the unit resumes at the join.

## 2026-09-26T22:32:55-07:00 — CR6b reading, join and adjudication

- The Codex record is at a much finer grain than any earlier record (800 lines against 555 for
  revision 3's whole-text reading), so a key-by-key join of the PASS lines was not possible:
  they were joined by section, and only the 119 non-PASS lines key by key, by the adjudicators.
- Most R findings are in HALF 2's kernel protocol order (NAPI masking, open/stop ordering,
  resource ownership). Revision 3's readers checked those bullets' `file:line` citations,
  which all hold; nobody had read the order the citations describe. A comparison reading by
  another model family found what re-reading changed hunks never looked at.
- One adjudicator per section group kept 119 lines to about six minutes each. Several
  adjudicators classed accuracy findings W where the fix is only words; the operator moved
  those seven to E, since C6's W is wording or form, not a false claim.
- Recording the whole-text reading as covering revisions 3–8 renewed 63 stale accuracy slices,
  and the historical re-verification unit left the queue. S4 for revisions 3–6 is now 1/2.
- The round-cap fix: `round_report` now skips adjudication entries; the new test failed first.
- The user's CR6a decision (option b) is recorded as a replacement item of class E with the
  decision on it; S5 still names CR6a's reading until a later independent reading replaces it,
  which CR6b now has (with its own R items).

## 2026-09-26T22:42:58-07:00 — CR6b records review; a correction

- Correction to the previous entry: the whole-text reading did not renew the 63 stale accuracy
  slices; it discharged them from the queue, and they stay stale in the index as history.
- The records reviewer found that the user's option (b) for CR6a's item was given before CR6b's
  adjudications tied two more findings to the same rule; the decision stands as recorded, and
  the revision decision now asks the user to confirm it.
- It also found no record of the user naming `gpt-6-astra`; the orchestrator chose it under the
  approved plan, and the report asks for confirmation.
