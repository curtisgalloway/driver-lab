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

## 2026-09-26T08:02-07:00 — 40 of 40 on the QF-1 harness, 80 seconds
Declared at 07:59 (commit `122b04a`), first run 08:00:15, last done 08:01:35: reference 20 of 20,
candidate 20 of 20, 928 checks, 0 failed, every identity as frozen. The candidate's probe line
now reads `EECD=0x00000198` where L02f3's read `0x00000188`: the one visible sign of the FWE
change, and the only change in the driver's kernel-log lines.

## 2026-09-26T08:04-07:00 — attributing the trace differences: count the polls, not the TNCRS reads
Comparing each candidate run with its L02f3 twin register by register, the EECD write value and
the STATUS read counts are the only differences that are not run-to-run noise (ring addresses,
traffic-dependent index values, open/close cadence, all seen between two L02f3 runs of the same
module). The STATUS surplus first looked one short of the TNCRS reads in every run. It is not:
the driver also reads TNCRS in the init-time sweep that clears the whole statistics block (G-10),
which adds no STATUS read, so the surplus equals TNCRS reads minus sweeps, exactly, in all 20
runs. Two polls (one each in `itr-1` and `ring-wrap-1`) have an ICR read or an RDT write stamped
between STATUS and TNCRS: another CPU's interrupt handler or NAPI poll running during the
statistics poll, whose lock is local. Nothing else differs.

## 2026-09-26T08:09-07:00 — the trio finds no bug; the one real weakness is the gap the implementer filed
Nine reviewers and a referee, all fresh, in parallel with the runs. The reference review has no
`[bug]`: where the two drivers differ on the changed code, the reference is the one departing
from the manual (FWE written back as read; TNCRS reported at every duplex) or from the
kernel's own definition (`tx_errors` without `tx_carrier_errors`). The requirements review
has every critical row implemented. The swarm's referee kept two low findings and dropped the
two that restated the change's intent. The one substantive item, found independently by the
reference reviewer and the swarm's correctness arm, is the question the implementer had
already filed: which duplex a TNCRS reading belongs to when the link changed between reads.
The spec does not say, so it goes to the next spec revision with the reviewers' proposed
rule, not to a repair round. The model's link is always full duplex, so no scenario could see it.

Dead end avoided: fixing the stale "revision 4" header comment myself. It is the implementer's
file, and the source identity the acceptance set ran would change; it waits for the next round.

## 2026-09-26T08:20-07:00 — correction (artifact review R1, R2): the gap and poll ranges were misread
The candidate's smallest reset gap per run is 5 to 8 µs, not 5 to 17: I took 17 from the gap
lists, where it appears, not from the per-run minima. The statistics-poll surplus ranges 2 to
23 per run, not 3 to 23 (`ring-wrap` polls twice). Neither touches a verdict. The reviewer also
re-derived the STATUS surplus a second way (TNCRS reads minus the clearing sweep's GORCL
reads) and got the same numbers in all 20 runs.
