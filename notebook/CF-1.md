<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CF-1 — the candidate on spec revision 6

Follow-on of the [plan](../IMPLEMENTATION-PLAN.md) named in L02f3. Terms: the **candidate**
is `e1000_l02`, written from revision 4 and repaired once; a **round** is one audited
clean-room implementer pass; the **acceptance set** is L02f3's 40 isolated runs. See the
[glossary](../GLOSSARY.md) and the [evidence](../evidence/CF-1.md).

## 2026-09-26T07:55-07:00 — opening: round 1 is already done, so the unit starts with checking it
Goal: bring the candidate to spec revision 6 and rerun the acceptance set on the QF-1 harness.
Start: branch `driver-porting/cf1` from `origin/main` at `77e754d`, own worktree, clean. The
user launched round 1 (Codex, `gpt-6-astra`, in the audited sandbox) at 07:49 after the agent's
own launch was refused twice by the safety check; the orchestrator built it (0 warnings). My
first job is to check the audit and the diff scope independently, not to trust the ledger.

## 2026-09-26T07:57-07:00 — the 16 spec hunks reduce to two changes, and the diff is exactly those
Re-running `sandbox_audit.py` on the round-1 and pilot logs gives byte-identical PASS reports.
Of the 16 hunks in the revision-4-to-6 diff, only two change what this driver does: FWE = 01b
on the EECD write (the candidate has one such write) and TNCRS counted only in full duplex.
R6's 10 µs margin, E1's fail-on-request/proceed-on-grant policy, E5's choice, RLEC not summed
with RUC and ROC, and G4's bit 11 before the AN restart were all already in the L02f2 code;
the implementer said so for each and changed nothing else. Expected trace differences from
L02f3: the EECD write goes from `0x188` to `0x198`, and a STATUS read precedes every TNCRS read.
