<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# QF-1: the four unqualified claims (Q18, Q24, Q25, Q26)

## Terms

- **Claim**, **qualified**, **unqualified**, **unobservable**, **insensitive**, **planted
  defect**, **isolated run** — as in the [L02d3 evidence](L02d3.md#terms). **Candidate** —
  `e1000_l02` as built in L02f2's round 1 (the module L02f3 accepted); **reference** —
  Linux v6.12's `e1000`.
- **Trace stamp** — the host time QEMU writes on each traced register access, in whole
  microseconds. QEMU stamps a write before the device model executes it and a read after;
  the difference between two stamps therefore bounds the guest's interval between the
  accesses from above.
- **Reset gap** — the difference between the stamp of a `CTRL.RST` write and the stamp of
  the next register access, the quantity the harness's reset rule judges (Q18).

See the [glossary](../GLOSSARY.md), the [design](../QEMU-DIFFERENTIAL.md) (§7, A6), the
[plan](../IMPLEMENTATION-PLAN.md) (QF-1) and the [notebook chapter](../notebook/QF-1.md).

## Status

In progress (2026-09-26).

## Frozen before execution (2026-09-26, 00:26 Pacific)

Private run `qf1-20260926-01`. The candidate does not change in this unit.

| Artifact | Identity |
| --- | --- |
| Harness | `l02harness.py` `7024864e…` (this unit's change, below), `guest-init.sh` `eccecebe…` (unchanged); the previous harness was `705694b9…` |
| Reference module | `e1000.ko` `43242751…` |
| Candidate module | `e1000_l02.ko` `366782e4…` (L02f2 round 1) |
| Kernel, QEMU, busybox | `0d96151b…`; 10.2.1+ds-1ubuntu3.2, `0cd4112a…`, KVM, DUT memory 3 GiB; `df12634c…` |
| Defects (modules) | d17 `007a1903…`, d18 `8fe39520…`, d19 `feaf2687…`, d20 `c368b636…`, d21 `6d7ff491…`, d22 `f19fba29…`; built out of tree against the same kernel with no warnings |
| Run script and job list | `run1.sh` `2ac79a3d…`, `jobs-q1.txt` `7285a263…` (63 lines) |

**The harness change.** The trace stamps each access to the microsecond, so two stamps
1 µs apart can be any interval under 2 µs; in the 40 L02f3 traces, consecutive memory-BAR
writes are stamped 0 µs apart hundreds of times per run and a write followed by a read is
stamped 1 µs apart most often. The old reset rule failed only on a difference under 1 µs,
so it passed intervals it could not show to be 1 µs. The rule now fails on a difference
under 2 µs (`RESET_GAP_STAMPS_US`), the smallest difference that shows an interval of at
least 1 µs; the check's name is unchanged and its detail says so. Tests: 0 and 1 µs fail,
2 and 3 pass; the I/O-window path is judged the same way. Nothing else in the harness
changed.

**Run declaration (round `q1`, 63 isolated runs, eight in parallel).**

- The acceptance set on the changed harness: all ten suite scenarios, reference ×2 and
  candidate ×2 (40 runs, as L02f3's). Criterion: reference 20 of 20 PASS, candidate 20 of
  20 PASS on every check. The change touches the trace pseudo-scenario, which runs in
  every scenario, so every earlier qualification's scenario is rerun for both drivers.
- d17 (module init fails), `smoke` ×3: expected "insmod" FAIL in 3 of 3; the scenario
  stops; the capture pseudo-scenario also fails for lack of any access (a consequence).
- d18 (probe rejects the 82540EM), `smoke` ×3: expected "insmod" PASS, "bound to a PCI
  device" FAIL in 3 of 3; the MAC, interface-up and carrier checks fail as consequences;
  the cleanup unload passes; the kernel log's "probe … failed" line is not flagged.
- d19 (`ndo_open` returns `-EBUSY`), `smoke` ×3: expected insmod, bind and MAC PASS,
  "interface up" FAIL in 3 of 3, carrier FAIL as a consequence, no pings; cleanup unload
  passes; kernel log clean.
- d20 (probe takes a module reference it never drops), `smoke` ×3: expected every check
  through the pings PASS, "rmmod" FAIL in 3 of 3 (module in use), the cleanup unload FAIL
  as a consequence; kernel log clean.
- d21 (the small-frame receive path delivers each frame one byte short), `frame-sizes`
  ×3: expected bring-up and the 42-byte ping PASS (its reply arrives padded to 60 bytes
  and survives one byte short), the four 60- and 61-byte ping checks FAIL in 3 of 3 (the
  frame arrives one byte shorter than its IP total length and IP drops it), 1513 and 1514
  PASS (above the copybreak size), the sent-sizes capture check FAIL on the missing 60-
  and 61-byte replies (a consequence), runts PASS, rmmod PASS, kernel log clean.
- d22 (global reset through the memory BAR with no wait after it), `smoke` ×8: expected
  every smoke check PASS; the reset rule FAIL in at least 1 of 8 runs, most likely most,
  with gaps of 0 or 1 µs; the gaps recorded per run, and the old rule's verdict
  recomputed from them. If no run shows a gap under 2 µs, Q18 stays unqualified.
- Every failure is kept, attributed and reported; no run is repeated to replace a result.
  A reference or candidate failure blocks the corresponding conclusion.

The declaration is in the run's ledger and here; this section is committed before the
first run.
