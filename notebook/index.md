<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Notebook index

Updated: 2026-09-25T13:45-07:00

A row is stale when its chapter has an entry newer than "indexed through". The notebook
starts with L02e; earlier units' paths are in their [evidence files](../evidence/). The
process log for this project is [PROCESS-NOTES.md](../PROCESS-NOTES.md). Terms: a chapter is
one unit's append-only notes; see the [glossary](../GLOSSARY.md) (lab notebook, process log).

## Chapters

### [L02d2 — QEMU harness, scenarios and planted defects](L02d2.md)
Entries: 2026-09-24T17:31-07:00 through 2026-09-25T13:45-07:00
Outcome: complete; the reference passes twice on the final harness, m2–m5 detected, m1 an
equivalent mutation; a Codex review of the fixes found three more (R1, R2, R5), all fixed.
- The test host was this checkout's own machine; no SSH was needed.
- Frames left over from a stalled flood contaminate later scenarios, differently each round;
  only ring-wrap detects m5 in every round.
- busybox `nc` has no UDP mode; floods are `ping -i 0.001`; `ping -i 0` hangs the guest.
- QEMU's e1000 pushes back instead of overrunning, and drains TX with the link down (L4
  not reproducible); packet-capture timestamps are about 8 h off the host clock.
- m1 (receive tail one early) is an equivalent mutation; m5 replaces it.
- Correction: the ITR read-back checks the model, not the driver (C4).

### [L02d1 — QEMU harness, boot and capture](L02d1.md)
Entries: 2026-09-24T16:17-07:00 through 2026-09-24T17:03-07:00
Outcome: complete; smoke passes on the reference; failure paths exit as documented.
- Dead end: busybox `read -t` on the guest command channel drops partial lines; use a
  blocking read and repeat READY from a background loop.
- QEMU 10.2.1 `-msg timestamp=on` prefixes trace lines with an ISO time, not `pid@time:`.
- The reference reads its EEPROM by bit-banging EECD (about 6,700 accesses), not EERD.
- Smoke does not yet check the kernel log (L02d2).

### [L02e — Implement, build, and review the candidate](L02e.md)
Entries: 2026-09-24T12:22-07:00 through 2026-09-24T13:09-07:00
Outcome: complete; driver builds clean, reviewed, repaired once, never run.
- GCC 15 cannot build Linux v6.12; the test host builds with gcc-14.
- Dead end: forcing a 32-bit DMA mask (the spec permits 64-bit with fallback).
- Spec error found: PSCON bit 11 (carrier sense on transmit) should be set.
- The session auditor flags a clean Claude Code session; its 8 findings were traced by hand.
- Entries before 12:22 are reconstructed from the run ledger.

## Threads
- **A check that cannot fail:** [L02d2](L02d2.md) — floods that never ran (r001), the ITR
  read-back, the L4 and M2 probes; caught by run artifacts and the coverage reviewer, not by
  code review.
- **Spec errors found downstream:** [L02e](L02e.md) — the reference review found a spec §5.4
  error (PSCON bit 11) that L02c's two readings passed; the implementer filed it during repair.
