<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SR-8 — spec revision 8

Follow-on of the [plan](../IMPLEMENTATION-PLAN.md), approved by the user on 2026-09-26, who
also chose the rule it writes. Terms: a **reading** is one fresh verifier's pass over a set of
spec claims with a verdict per claim; a **drain** is a read of a clear-on-read statistics
register, which empties it; **TNCRS** is the transmit-without-carrier-sense counter the manual
calls valid in full duplex only. See the [glossary](../GLOSSARY.md) and the
[evidence](../evidence/SR-8.md).

## 2026-09-26T09:12-07:00 — opening: a requirement change, so the header has to say so
Goal: revision 8 on revision 7 with the TNCRS attribution rule CF-1's reviewers asked for (the
user chose reviewer A's "drain at link change" on 2026-09-26) and SR-7's three wording items.
Start: branch `driver-porting/sr8` from `origin/main` at `57273d6`, own worktree, clean. Unlike
SR-7 this revision changes what a driver must do, and the candidate on the shelf (CF-1's) does
not do it yet; the header says both, since a reader of the spec alone must not take the
candidate's result as covering the rule. Clean room as before: manual text, the spec, the
public evidence; CF-1's private reviewer-A report was left unopened because it names reference
functions as locations, and the evidence file already carries the rule.

## 2026-09-26T09:17-07:00 — the rule is an argument, so the manual has to supply four premises
The manual says nothing about which duplex a count belongs to, so the rule is an `[inference]`
that carries a policy, and §1's row (revision 7's) makes it state premises, confidence and a
verification. The four the argument needs were all in the manual, each on one page: clear on
read (§13.7's introduction), full duplex only (§13.7.12), FD "as set by either Hardware
Auto-Negotiation function, or by software" with LSC "set each time the link status changes"
(Table 13-5, §13.4.17), and "only increments if transmits are enabled" (§13.7.12). The last
one is what makes "never gate on link-up" more than a preference: with TCTL.EN left set across
link loss (§5.7 T7, cleared only by §5.10 D3), a skipped reading does not stop the counter, it
moves the counts into the next link's interval. The one premise the manual cannot supply is
that the duplex changes only with a link change; that holds because this spec never forces it
(G1 clears FRCDPLX, G7 enables auto-negotiation), so the confidence is medium and says why.
The residual the rule leaves is the link task's latency, and the row says that too.

## 2026-09-26T09:17-07:00 — G-16's page list: count the code point, do not trust the list
SR-7's round-6 reader had named four more pages where the rendering holds U+F06D at values the
spec uses. Counting every occurrence in the text and mapping each to its printed page by form
feeds gives twelve on ten pages: the three cited (228 twice, 308, 318), the four named (295,
309, 319, 321) and three the spec does not cite (5 twice, 172, 204). G-16 now lists all ten
with the count, so the next reader can check the list by counting rather than by searching for
a sign that is not there.

## 2026-09-26T09:28-07:00 — round 1: two page numbers off by one, and the rule's starting point had no step
50 PASS, 3 FAIL, 1 GAP. The two page FAILs are the same mistake twice: I took the page of the
section heading for the page of the sentence, and in both places (§13.7's introduction, Table
13-5) the footer sits between them, so the sentence is one page on. The third was a count: CF-1
had three reviewers, and "both reviewers" named two; §12.6's own row already had it right. The
GAP is the useful one: the rule says its record "starts at §5.5's clearing read", and nothing in
§5.5 told the driver to sample the duplex there, so the first interval had no duplex to be
credited by until the first link change. One sentence in §5.5 closes it. The reader's three
out-of-scope notes were all taken (the header now names the order paragraph and §5.5; premise
(4) names D7's reset beside D3; premise (3) states the assumption it leans on, in the form G4's
premise (3) already uses). Round 2 launched on the fixed text.

## 2026-09-26T09:37-07:00 — round 2 clean; revision 8 landed; the record scan's findings are the reader's own citations
68 PASS, 0 FAIL, 1 UNVERIFIABLE (whether U+F06D renders as the micro sign on the four further
pages, which only the PDF can settle). Two rounds against SR-7's six: the rule was written once
from the manual's sentences rather than reworded round by round, and the FAILs were bookkeeping.
The verification records' leak scan then reported findings for the first time in this series:
six kernel API names (spinlock, delayed-work and carrier helpers) that the reader named while
confirming §10.3's unchanged `[kernel]` `file:line` citations hold their symbols. The spec cites
those lines without naming the symbols, so L02c's target-API list never had them; the reference
driver uses the same public API, which is what the scanner sees. Judged not a leak (the records
stay private either way), and the reason is in the ledger beside the scan. The reader's four
notes (a third cause of a 0 in R7's precondition; the first, link-down interval credited by an
unspecified FD; premises by reference in §5.5's and L6's tags; the tree is a directory named by
the commit) go to the next revision: a fix pass that adds words needs its own reading.

## 2026-09-26T10:10-07:00 — interruption: a spend limit, resumed from disk
The session stopped on an API spend-limit error at about 09:38, after revision 8 had landed
and its PASS line was written, with the public records drafted and nothing committed. Resumed
at 10:10 on usage credits from the ledger and the worktree, not from memory; the ledger carries
the same note.

## 2026-09-26T10:17-07:00 — corrections from the records review
The records review (ten findings, all applied; the evidence's Review table has them) marks
two things in this chapter that stay as written because it is append-only. The 09:17 entry
restates the rule's premises, confidence and residual, and the 09:28 entry restates round 1's
findings; both belong to the evidence (the one-job rule, F9), so read them there. And the
09:37 entry's account of the reader's four notes attributes all four to its reply, where two
(R7's third cause; the plain-directory tree) are in its record. The lesson SR-7 wrote for the
index's "Updated" time was repeated here (F7): set it at the last edit, not at the first.
