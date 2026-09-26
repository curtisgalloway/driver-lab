<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CF-2 — the candidate on spec revision 8

The next candidate round after [SR-8](SR-8.md), approved by the user on 2026-09-26 ("Run the
next round when able"). Terms: the **candidate** is `e1000_l02` as CF-1 left it; a **round** is
one audited clean-room implementer pass; the **rule** is revision 8's TNCRS attribution rule;
the **acceptance set** is L02f3's 40 isolated runs. See the [glossary](../GLOSSARY.md) and the
[evidence](../evidence/CF-2.md).

## 2026-09-26T12:32-07:00 — opening, after a pause: round 1 is done, so the unit starts by checking it
Goal: bring the candidate to revision 8 (the rule and the header's revision number) and rerun
the acceptance set on the FC-1 harness. Start: branch `driver-porting/cf2` from `origin/main` at
`ad247be`, own worktree, clean. The user launched round 1 (Codex, `gpt-6-astra`, in the audited
sandbox) at 10:32; the orchestrator built it (0 warnings). The session was stopped once for the
quota reset before anything was written, so the check starts from the ledger, not from memory.

## 2026-09-26T12:35-07:00 — the 21 hunks reduce to one rule, and the diff is that rule in four places
Re-running `sandbox_audit.py` on the round-1 and pilot logs gives byte-identical PASS reports;
the implementer read the spec, the diff and the candidate, and not the manual. Of the 21 hunks
only four change what this driver does, and all four are the same rule seen from §4.7, §5.5,
§5.9 and §10.3. The change keeps one sample under the statistics lock, seeds it at the clearing
sweep, and routes every TNCRS read through one helper that credits by the sample and then
re-samples; the link check now takes the lock and drains through the same helper, using its
STATUS read as L1's. The header says revision 8 and nothing else in it moved.

The question asked of this unit: the link check runs on every watchdog tick as well as on every
LSC, so the counter is drained twice per tick. The spec names the readings that must happen,
not the only ones that may, and its rule is per reading, so an extra reading splits an interval
into two credited by the same sample; where a link change fell between them, the extra reading
is the one L6 asks for. Permitted; the cost is one TNCRS and one STATUS read per tick.

Expected in the traces against CF-1: more TNCRS reads (one per link check), one more STATUS
read per clearing sweep, and TNCRS before STATUS in each poll instead of after. Nothing the
model can show about the crediting itself: its link never changes duplex.

## 2026-09-26T12:40-07:00 — 40 of 40 on the FC-1 harness, 79 seconds
Declared at 12:37 (commit `a283279`), launched 12:38:07, last done 12:39:26: reference 20 of 20,
candidate 20 of 20, 944 checks (CF-1's 928 plus FC-1's sixteen), 0 failed, every identity as
frozen. The driver's kernel-log lines are identical to CF-1's; the EECD probe line still reads
`0x198`. Nothing the rule changed is visible in a verdict, as expected.

## 2026-09-26T12:43-07:00 — attributing the traces: classify each TNCRS read by the register before it
Every TNCRS read in a CF-2 trace has a predecessor that names it: DC means the clearing sweep,
COLC the periodic poll, anything else a link check. With that, the three predicted differences
fall out exactly in 19 of 20 runs: the TNCRS surplus is the link-check count (watchdog ticks,
plus one for the forced LSC at open, plus the scenario's link changes), the STATUS surplus is
the sweep count, and TNCRS precedes STATUS in every sweep and poll. The twentieth run,
`frame-sizes-1`, has one more watchdog tick than its CF-1 twin: FC-1's counter reads made the
scenario 10.4 s instead of 10.3, right on the 2 s boundary, so the sixth poll lands by chance
(CF-2's own second repetition has five). One link check per open has its STATUS read a few
accesses late, with MTA writes between: the stack's `set_rx_mode` on another CPU, the same
interleaving class CF-1 saw with ICR and RDT. The 52 IMS/IMC phase-level leftovers are mostly
`frame-sizes` phases renamed by FC-1's `-p` flag; whole-run totals sit within the control pairs.

What the model cannot show: the crediting. STATUS reads `0x80080781` at every link check
(1000 Mb/s full duplex, link up) and TNCRS reads 0 at every reading, so every sample is full
duplex and nothing is ever discarded. The traces place the readings; the reviews and HF-1's
hardware check carry the rule.

## 2026-09-26T13:02-07:00 — correction (artifact review R2, R3, R5): the STATUS value, the late reads, the identity
The 12:43 entry glossed `0x80080781` as "link up"; it is the link-down value (bit 1 clear), read
at the forced LSC of each open and at every link-down check, while `0x80080783` is the link-up
one; both have FD = 1, which is all the argument needed. The late STATUS read after an open's
first link check happens once per affected open, 26 times in 12 runs, 3 to 16 accesses later;
my script looked two accesses ahead and I read its "missing" entries by hand. And the link-check
identity only adds up once a "poll" is seen to include stop's final reading, one per close.
None touches a verdict or an attribution.
