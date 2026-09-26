<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# AF-1 — a second reading of revision 4's changes

Follow-on of the [plan](../IMPLEMENTATION-PLAN.md) named in L02f3. Terms: a **reading** is
one fresh verifier's pass over a set of spec claims with a verdict per claim; the **first
reading** is L02c's change check of revision 4; **A1** is the design's criterion of two
verification readings with no unresolved FAIL. See the [glossary](../GLOSSARY.md) and the
[evidence](../evidence/AF-1.md). **HALF 2** is the spec's second part, the Linux
integration written from kernel headers and documentation, as against HALF 1, the hardware.

## 2026-09-25T22:33-07:00 — opening: the second reading, not the recall re-measurement
Goal: close L02c's recorded A1 shortfall for revision 4's changes. The plan offers a second
reading or a recall re-measurement; only a second reading of the same text supplies what A1
asks for (two readings), and recall on a later revision answers a different limitation, so the
second reading it is. Start: branch `driver-porting/af1` from `origin/main` at `5a21ac0`, own
worktree, clean. Revision 3 was not in this host's copy of the L02c run; the orchestrator
copied it from the original store at 22:31 (hash matches the L02b/L02c ledgers). The r3→r4
diff regenerated here has 22 hunks; the first reading's record speaks of 25, because it read
the draft (before the one-line citation follow-up) and a diff made elsewhere.

## 2026-09-25T22:40-07:00 — brief from the diff alone, reader launched before I read the first record
The brief lists 23 changed passages keyed by section and item, so the second reader's keys
can be matched to the first reading's without either seeing the other. No PDF of the manual is
in this store, so the brief tells the reader that PDF page numbers come from the text's form
feeds and that a micro-sign check is UNVERIFIABLE. HALF 2 claims get the pinned tree's
`include/` and `Documentation/` only, as L02c's readers had. I opened the first reading's
record only after the launch: it was a Claude Opus 5.5 subagent with the PDF; this reading is
Fable 5.1 without it, so the two readings differ in model as well as in context.

## 2026-09-25T22:47-07:00 — the readings agree on every claim but one, and the one is about form
69 lines against the first reading's 51 over the same 22 hunks; 49 of the first's keys carry
the same PASS, the first's one FAIL (a citation range a line short) reads PASS on the landed
text, so the `diff`-only check L02c admitted to is now an independent re-read. The one
disagreement: the §10.3 inference that the PCI core sets `IORESOURCE_MEM_64` from the BAR
type field has no stated confidence. The spec's own §1 says an `[inference]` gives "premises,
derivation, confidence and verification method", so the second reader is right on the rule;
but a grep shows 13 of revision 4's 50 inferences state a confidence, and both full readings
of revision 3 passed the rest. A form lapse, not an accuracy error, for the next revision.
Both readers, independently, hung the same caveat on R7's verification test (a 1 cannot tell
a re-read from a restore); that is the kind of agreement two readings are for.

## 2026-09-25T22:48-07:00 — the record's leak scan flagged a kernel type in a quoted prototype
`pci_dev`, inside the record's quotation of `pci_read_config_dword`'s signature from the
target tree's `include/linux/pci.h`. The same shape as L02c's `PAGE_SIZE` (a HALF 2 public
API name that also appears in the driver). Dispositioned on a run-local copy of the whitelist
rather than by editing the L02c one, and rescanned clean. Lesson for briefs: tell a reader
that quotes a HALF 2 prototype to name the function, not its parameter types.

## 2026-09-25T22:56-07:00 — correction: the times in this chapter and the ledger were from memory
The records reviewer compared the ledger's step times with the artifacts' own timestamps and
found them written after the fact: the brief and the reader's launch were at 22:34, not 22:40
(the record was written at 22:43 after 8.7 minutes, which the stated times could not hold),
the revision-4 scan at 22:35, the record's scan and its disposition at 22:44–22:45. The
entries above keep their headings; the ledger is corrected from the file times. The same
review found that my count of agreeing keys had double-counted two folded ones (48, not 49,
with one first-reading claim, G1's coverage of the EEPROM-default bits through §5.10, read
once), and that no key-to-key table existed anywhere: the matching now lives in the run store
as a 51-row table. A comparison that is the unit's whole result needs to be an artifact, not
a number in a sentence.
