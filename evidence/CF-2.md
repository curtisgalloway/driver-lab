<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CF-2: the candidate on spec revision 8

## Terms

- **Candidate** — `e1000_l02`, the driver written from spec revision 4 (L02e), repaired once
  (L02f2), updated to revision 6 ([CF-1](CF-1.md)) and, in this unit, to revision 8.
  **Reference** — Linux v6.12's `e1000`.
- **The rule** — revision 8's TNCRS attribution rule ([SR-8](SR-8.md)): the clear-on-read
  TNCRS counter is read at the periodic statistics poll and at every link-status change, each
  reading's count is credited to the duplex sampled at the previous reading (reported if that
  was full duplex, discarded otherwise), and the record starts at the clearing read (§4.7,
  §5.5, §5.9 L6).
- **Reading** (of the counter) — one read of TNCRS, which clears it; the count covers the
  interval since the previous reading. **Sample** — the STATUS.FD value kept from a reading
  for crediting the next one.
- **Round**, **acceptance set**, **L01 review trio**, **isolated run**, **claim**,
  **qualified** — as in [CF-1](CF-1.md#terms).

See the [glossary](../GLOSSARY.md), the [design](../QEMU-DIFFERENTIAL.md), the
[plan](../IMPLEMENTATION-PLAN.md) (CF-2), the [SR-8 evidence](SR-8.md) (the rule), the
[CF-1 evidence](CF-1.md) (the pattern and the comparison baseline) and the
[notebook chapter](../notebook/CF-2.md).

## Status

**In progress, 2026-09-26.** Round 1 is done and checked; the acceptance set is declared below
and not yet run.

## Frozen before execution (2026-09-26, 12:37 Pacific)

Private run `e1000-cf2-20260926-01`.

| Artifact | Identity |
| --- | --- |
| Spec | Revision 8, `e0f17ffa…6326d7` (SR-8's landed copy); the revision-6-to-8 diff given to the implementer `038d97e5…` (21 hunks, 270 lines) |
| Candidate before | `e1000_l02.c` `a8afc8c4…` (CF-1 round 1; module `ce7e3e2c…`, the one CF-1 and FC-1 ran) |
| Candidate after (round 1) | `e1000_l02.c` `2ac15713…`, module `e1000_l02.ko` `df37c7ad…`, built with gcc-14 against the pinned v6.12 tree, 0 warnings at default and W=1, module defaults |
| Harness | `l02harness.py` `884e771c…`, `guest-init.sh` `eccecebe…` (FC-1's final harness; the checkout at `ad247be`, origin/main) |
| Reference module | `e1000.ko` `43242751…` (as every unit since L02d2) |
| Kernel, QEMU, busybox | `bzImage` `0d96151b…`; 10.2.1+ds-1ubuntu3.2, `qemu-system-x86_64` `0cd4112a…`, KVM, DUT memory 3 GiB; `df12634c…` |
| Run script and job list | `run1.sh` `281dae8d…`, `jobs-a1.txt` `a847819e…` (CF-1's and L02f3's list, 40 lines) |

**Run declaration (round `a1`).** All ten suite scenarios, isolated, for the reference and
for the round-1 candidate, two repetitions each: 40 runs, eight in parallel, reference and
candidate interleaved, on the FC-1 harness. Pass criteria: reference 20 of 20 PASS (A4);
candidate 20 of 20 PASS on every check, the `trace` and `capture` pseudo-scenarios and the
kernel-log check included. Every failure is kept, attributed and reported; no run is repeated
to replace a result; a reference failure the manual does not explain blocks judging the
affected candidate behavior. Past probe, the candidate's register traces are compared with
CF-1's candidate traces scenario by scenario, CF-1's two repetitions serving as the control
for run-to-run variation. Three differences are expected from the change: TNCRS is read more
often, by the number of link checks per run (each link check now drains the counter); STATUS
is read once more per clearing sweep (the §5.5 sample); and within each statistics poll the
TNCRS read now precedes the STATUS read. Any other difference is attributed to the candidate,
the spec, the model or the harness before the unit closes. The kernel-log lines are expected
to be identical to CF-1's. The rule itself cannot be observed on the model, whose link is
1000 Mb/s full duplex and never changes duplex: every sample is full duplex and every reading
is credited, so the traces can show where the readings happen, not whether the crediting is
right. The declaration is in the run's ledger and here, committed before the first run.
