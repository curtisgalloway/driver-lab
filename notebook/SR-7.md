<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SR-7 — spec revision 7

Follow-on of the [plan](../IMPLEMENTATION-PLAN.md), approved by the user on 2026-09-26. Terms:
a **reading** is one fresh verifier's pass over a set of spec claims with a verdict per claim;
**A1** is the design's criterion of two verification readings with no unresolved FAIL; the
**extract** is the operator's file of what the differential runs recorded, which an
`[emulated]` claim is checked against. See the [glossary](../GLOSSARY.md) and the
[evidence](../evidence/SR-7.md).

## 2026-09-26T07:37-07:00 — opening: read revisions 5 and 6 as landed before touching them
Goal: the second independent reading AF-1 recommended for revisions 5 and 6, then revision 7
with the six AF-1 items, SF-1's pointer form and QF-1's F2, changing no driver requirement
because CF-1 is in flight on revision 6. Start: branch `driver-porting/sr7` from `origin/main`
at `77e754d`, own worktree, clean. The reader's brief is written from the r4→r6 diff (16 hunks)
alone and the reader launched before I open either landed verification record, as AF-1 did;
it gets L02f3's observations extract because L02f3's readers had it, so the readings are
comparable. There are no `[kernel]` claims among the changes, so the reader gets no Linux tree.

## 2026-09-26T07:50-07:00 — the new §12.5 entry comes from the captures, not from the finding
QF-1's F2 explains the runts by the model's source, which the spec must not carry. What the
runs recorded is enough: in every `frame-sizes` capture the peer's ARP and its echo replies to
the DUT's 42-byte pings are 42-byte frames at the DUT, both drivers receive them, a defect
that shortened each small frame by one byte killed ARP, and one that dropped frames over 46
bytes of descriptor length passed the 42-byte ping. Two things I had wrong on the first pass
and the captures corrected: the peer is a virtio-net guest (so nothing pads its frames), and
in the d21 runs the peer still sent its own echo requests at 60 bytes and more; only the
DUT's pings never left, for want of ARP. Counting frames by sender and ethertype with a small
pcap reader was cheaper than reasoning about what "every ping failed" implies.

## 2026-09-26T07:54-07:00 — the checker cannot read this spec, so its rule was applied by hand
`spec_check.py` reads `*.spec.md` under a root with YAML frontmatter; the clean-room spec has
neither. Importing its `UNNAMED_RES['emulated']` regex over both files shows the point: revision
6's three tag-clause uses match (a bare `§12.5 EM2` after the tag), the draft's do not, and
what still matches in the draft are prose mentions of the tag name, which the format says are
not tags. That is the "if it applies" of the brief answered: it applies to the shape, not to
the file.

## 2026-09-26T07:49-07:00 — the second reading agrees on 55 of 60 keys; the three disagreements are all the manual's §11.1.3 list and one word
83 lines against the first readings' 15 and 45 over the same 16 hunks. Two of the three
disagreements are the same fact seen from two places: §11.1.3 names PHY register 16's bits
3, 4, 6:5, 9:8 and 11, so it neither requires register 20's place before G7 (the caveat
revision 5 dropped when it justified bit 11's order) nor covers bit 1 in §9.2's timing
clause. The third is EM7's "behave identically", which says more than "no check tells them
apart" when the trace comparison did see different register writes. Both first readers passed
these while looking at the bit-11 question, which was the change; the second reader, reading
the sentence rather than the change, saw the neighbor. All three are wording; none changes
what a driver does. Both readers of G-12 independently offered §8.4.2's last paragraph as a
third citation on 1000 Mb/s half duplex; two independent nominations is reason enough to add it.

## 2026-09-26T07:52-07:00 — correction: the ledger's step times had been written from memory
The clock read 07:50 when I had just written "07:58" and "07:59" into the ledger, and the
earlier entries ("07:44–07:52", "07:53", "07:54") were late by four to nine minutes against
the files' own mtimes. This is AF-1's F5 exactly, repeated by the same model a day later. The
ledger is rewritten from the mtimes and says so; the rule that should have applied: run
`date` or `stat` in the same command as the step, never afterwards from recollection. This
chapter's own 07:50 and 07:54 headings above are from the same memory: by the mtimes, the
EM8 work and the checker scratch run both fell between 07:40 and 07:46. The headings stay,
since the chapter is append-only; read them as "before 07:46".

## 2026-09-26T08:00-07:00 — the new tag rule found its own first victim
Round 1 on revision 7: 52 PASS, 1 FAIL, and the FAIL is a consequence of item (1). Narrowing
§1's `[inference]` row to "an argument needs confidence and verification; a one-clause design
choice may omit them" made E5's untouched first policy ("log it, random address or refuse")
inconsistent: it is a policy, so it is on the required side, and it had neither. The reader
was right; the premises, a confidence and a "none needed, the choice is the implementer's"
were added with the choices unchanged. Two notes from the same round were sharper than the
text: EM8 said the reference driver has a "small-frame receive path", a structural fact about
encumbered code that the captures do not need (reworded to "a planted defect that ..."), and
"drops the micro sign" is what a viewer shows, not what the bytes hold (a private-use code
point, U+F06D, sits there; a grep for "µ" cannot find those places). Round 2 launched on the
fixed text so the landed record's hash matches the landed file.

## 2026-09-26T08:10-07:00 — round 2: the fix pass made one of its own defects, and the caveat exposed an old one
39 PASS, 3 FAIL. One is mine: adding premises to E5 in round 1 made E5 a changed passage,
and the header that claims "every changed passage named" did not name it (L02f3's fix
passes made the same shape of error, three times). One is the manual's shape: "§8.4.2's last
paragraph" was the last on p. 159, and the section runs on to p. 160. The third is the
interesting one: R7's caveat said a 0 reading "shows no reload", but the test never confirms
the EEPROM value was applied at power-up in the first place; Table 13-3's footnote 2 makes
that load conditional on the signature bits, so on a device without the signature the bit is
0 before and after and a 0 settles nothing. The gap was in revision 6's test text all along;
the new caveat made it load-bearing, and only then was it visible. The precondition (read
the bit, expect 1) is the reader's; round 3 launched on it.

## 2026-09-26T08:20-07:00 — round 3: two readers pulling one sentence in opposite directions
50 PASS, 1 FAIL, on EM8's second-defect sentence. Round 1 asked me to stop saying the
reference driver has a "small-frame receive path" (a structural fact the captures do not
need); round 3 read the result, "dropped received frames whose descriptor length exceeded 46
bytes", as a defect on every frame over 46 bytes, which the passing 1513- and 1514-byte pings
contradict, and proposed putting the path back. Both are right about their own concern, and
the way through is the one the house phrasing rule already gives: state the scope by what
the runs showed ("reaching short frames only: the 1513- and 1514-byte pings passed"), never by
where the defect sits in the code. The other change was dropping "a symbol-font glyph": the
text holds U+F06D, and the text cannot say why. Round 4 launched, with SPEC-FORMAT.md added
as an input so the header's "the citation shape the spec format now requires" is checkable.

## 2026-09-26T08:28-07:00 — round 4: the same sentence's other half
53 PASS, 1 FAIL, and it is the first-defect sentence this time: round 1's rewording to "a
planted defect that delivered every received frame one byte short" had widened the defect
beyond the extract, which scopes it to short frames, exactly as round 3 found for the second
defect. The lesson is one I should have taken from round 3 and applied to both halves: when
a structural phrase is removed, replace it with the scope it carried ("short received
frames"), not with nothing. Round 5 launched on that one change.

## 2026-09-26T08:38-07:00 — round 5: my own gloss on the captures was the last overclaim
59 PASS, 1 FAIL: the parenthetical I added in round 4, "ARP included; the peer's ARP went
unanswered", is my reading of the captures (the DUT's 15 ARP frames are its own requests, so
the peer's requests got no reply), and the extract does not say so; it lists frame counts by
sender and says the DUT's pings never left it. The reader's wording claims exactly the
extract, and it is taken. Two notes taken with it: R7's older "1 means the reset reloaded the
EEPROM value" now said more than the new caveat allows, and "displays as nothing" is the
viewer's doing, not the file's. Round 6 launched. Six rounds for one revision is the cost of
a fix pass that keeps adding words; each round's FAIL has been a sentence the previous fix
wrote.

## 2026-09-26T08:46-07:00 — round 6 clean; revision 7 landed
59 PASS, 0 FAIL, 1 UNVERIFIABLE (the PDF check, which no reader in this store can settle).
Landed as revision 7, 1,685 lines, with the PASS line in the run's provenance ledger and
both verification records scanned clean. Six rounds against L02f3's four: the difference is
that EM8 is a new observation written from captures, and every rewording of its two defect
sentences traded one overclaim for another until the sentence said only what the extract
says. Next time an `[emulated]` entry is drafted, write it from the extract's sentences, not
from the finding that prompted it.

## 2026-09-26T08:57-07:00 — corrections from the records review
Three things above are wrong and stay as written because the chapter is append-only. The
07:49 heading's "55 of 60 keys": the comparison's own rows say 54 same, 2 read once, 4
disagreeing keys on 3 passages; I had counted the passage that is a key in both first
records once. The 08:10 entry says round 3 launched; it launched at 08:11 by the ledger. And
the same entry's "one is mine" undercounts: by the ledger, round 2's header FAIL and rounds
3 to 5's EM8 FAILs were fix-pass sentences, while round 2's other two were in text round 1
had passed. The 07:49 entry also repeats the adjudication argument the evidence carries (the
one-job rule, F9); read the evidence for it.
