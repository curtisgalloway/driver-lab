<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CF-1: the candidate on spec revision 6

## Terms

- **Candidate** — `e1000_l02`, the driver written from spec revision 4 (L02e), repaired once
  (L02f2) and, in this unit, updated to revision 6. **Reference** — Linux v6.12's `e1000`.
- **Round** — one bounded implementer pass in the audited clean-room sandbox
  (`cleanroom-implementer`, "Tier 1 on Linux"), as in L02f2: a brief carrying only spec text,
  manual text and permitted observations; an strace log audited by `sandbox_audit.py`.
- **Acceptance set** — L02f3's run set: all ten suite scenarios, isolated (one scenario per
  fresh boot), reference ×2 and candidate ×2, 40 runs. **Isolated run**, **claim**,
  **qualified** — as in the [L02d3 evidence](L02d3.md#terms).
- **L01 review trio** — the three independent reviews L01 and L02e gave a candidate: a
  reference review (candidate against the reference driver, each difference decided from the
  manual), a requirements review (candidate against the blind list, without the reference) and
  `review-swarm` on the diff ([L01](L01.md), [L02e](L02e.md)).

See the [glossary](../GLOSSARY.md), the [design](../QEMU-DIFFERENTIAL.md), the
[plan](../IMPLEMENTATION-PLAN.md) (CF-1), the [L02f3 evidence](L02f3.md) (the definition
of this follow-on) and the [notebook chapter](../notebook/CF-1.md).

## Status

**In progress, 2026-09-26.** Round 1 is done and checked; the acceptance run is declared
below and runs next.

## Frozen before execution (2026-09-26, 07:59 Pacific)

Private run `e1000-cf1-20260925-01`.

| Artifact | Identity |
| --- | --- |
| Spec | Revision 6, `f78ea07a…45b2` (L02f3's landed copy); the revision-4-to-6 diff given to the implementer `96743b65…` (16 hunks, 228 lines) |
| Candidate before | `e1000_l02.c` `dfb0aa0c…` (L02f2 round 1; module `366782e4…`, the one L02f3 and QF-1 ran) |
| Candidate after (round 1) | `e1000_l02.c` `a8afc8c4…`, module `e1000_l02.ko` `ce7e3e2c…`, built with gcc-14 against the pinned v6.12 tree, 0 warnings at default and W=1, module defaults |
| Harness | `l02harness.py` `7024864e…`, `guest-init.sh` `eccecebe…` (QF-1's final harness, the checkout at `77e754d`) |
| Reference module | `e1000.ko` `43242751…` (as every unit since L02d2) |
| Kernel, QEMU, busybox | `bzImage` `0d96151b…`; 10.2.1+ds-1ubuntu3.2, `qemu-system-x86_64` `0cd4112a…`, KVM, DUT memory 3 GiB; `df12634c…` |
| Run script and job list | `run1.sh` `3c90950a…`, `jobs-a1.txt` `a847819e…` (L02f3's list, 40 lines) |

**Run declaration (round `a1`).** All ten suite scenarios, isolated, for the reference and
for the round-1 candidate, two repetitions each: 40 runs, eight in parallel, reference and
candidate interleaved, on the QF-1 harness. Pass criteria: reference 20 of 20 PASS (A4);
candidate 20 of 20 PASS on every check, the `trace` and `capture` pseudo-scenarios and the
kernel-log check included. Every failure is kept, attributed and reported; no run is repeated
to replace a result; a reference failure the manual does not explain blocks judging the
affected candidate behavior. Past probe, the candidate's register traces are compared with
L02f3's candidate traces scenario by scenario: the EECD write value (FWE now written 01b) and
one STATUS read before each TNCRS read are the expected differences; any other difference is
attributed to the candidate, the spec, the model or the harness before the unit closes. The
declaration is in the run's ledger and here, committed before the first run.
