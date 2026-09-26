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
