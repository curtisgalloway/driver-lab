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
