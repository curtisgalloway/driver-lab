<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Notebook index

Updated: 2026-09-26T08:57-07:00

A row is stale when its chapter has an entry newer than "indexed through". The notebook
starts with L02e; earlier units' paths are in their [evidence files](../evidence/). The
process log for this project is [PROCESS-NOTES.md](../PROCESS-NOTES.md). Terms: a chapter is
one unit's append-only notes; see the [glossary](../GLOSSARY.md) (lab notebook, process log).

## Chapters

### [SR-7 — spec revision 7](SR-7.md)
Entries: 2026-09-26T07:37-07:00 through 2026-09-26T08:57-07:00
Outcome: complete; see the [evidence](../evidence/SR-7.md).
- A second reading of a sentence finds what a reading of the change in it does not.
- Write an `[emulated]` entry from the extract's sentences, not from the finding.
- Six verification rounds; four FAILs were sentences a fix pass had written.
- Corrections: ledger times from memory (AF-1's F5 repeated); the key count (55, not 54).

### [CF-1 — the candidate on spec revision 6](CF-1.md)
Entries: 2026-09-26T07:55-07:00 through 2026-09-26T08:20-07:00
Outcome: complete; the candidate implements revision 6 (two behaviors changed), 40 of 40 on the
QF-1 harness, no bug from the L01 review trio; see the [evidence](../evidence/CF-1.md).
- Of 16 spec hunks only two change this driver: FWE = 01b on its one EECD write, TNCRS in full
  duplex only.
- Attributing the trace differences meant counting statistics polls, not TNCRS reads: the
  init-time clearing sweep reads TNCRS too.
- Where the drivers differ on the changed code, the reference is the one off the manual.
- The one weakness (which duplex a TNCRS reading belongs to after a link change) is a spec gap.
- Correction (artifact review R1): per-run smallest reset gaps are 5 to 8 µs, not 5 to 17.

### [QF-1 — the four unqualified claims](QF-1.md)
Entries: 2026-09-26T00:10-07:00 through 2026-09-26T00:52-07:00
Outcome: complete; Q24, Q25 and Q26 qualified, Q18 stays unqualified (`unobservable`); see
the [evidence](../evidence/QF-1.md).
- The trace resolves sub-microsecond intervals as equal stamps; the 1 µs rule was lenient,
  not blind, and now needs stamps 2 µs apart.
- Even with no wait at all, a reset write is never followed within 4 µs here; why is unknown.
- The model does not pad short frames: a small-frame defect that trims also kills ARP.
- The kernel-log check caught a warning in the reference's own probe error path.
- Ping payloads are zeros past a 4-byte timestamp, so small-frame corruption is invisible.
- Correction (review R1): write-then-read stamps are typically 6 µs apart, not 1.

### [AF-1 — a second reading of revision 4's changes](AF-1.md)
Entries: 2026-09-25T22:33-07:00 through 2026-09-25T22:56-07:00
Outcome: complete; see the [evidence](../evidence/AF-1.md).
- The one disagreement between the readings was the spec's own tag rule, not the manual.
- Both readers independently hung the same caveat on R7's verification test.
- The record's leak scan flagged a kernel type quoted from a target-tree prototype.
- Correction (review F5): the ledger's step times had been written from memory.

### [SF-1 — `[emulated]` in the format](SF-1.md)
Entries: 2026-09-25T20:33-07:00 through 2026-09-25T21:05-07:00
Outcome: complete; the class is in the format, the evidence model and the checker; see the
[evidence](../evidence/SF-1.md).
- The checker already had the citation and TODO shapes; "never alone" is the one new rule,
  a set test on the tail's tags.
- The phrasing rule and the run-ID content are judgment, so they went to `spec-verifier`'s
  text, where L02f3 actually enforced them.

### [L02f3 — spec feedback, reverification and L02 acceptance](L02f3.md)
Entries: 2026-09-25T18:35-07:00 through 2026-09-25T19:30-07:00
Outcome: complete; L02 closes with both decisions met and explicit shortfalls; see the
[evidence](../evidence/L02f3.md).
- The 40 acceptance runs finished in 81 s, before the spec edits were done.
- An `[emulated]` entry states what the runs recorded, never the model's mechanism.
- With the whitelist on the test host, the scans are clean; L02s's set comparison had no
  baseline.
- The fix pass made three defects of its own (a rename that hit the milestone keys, a
  double replacement, a change list not rewritten from the diff); four verifier rounds.

### [L02f2b — harness fix H1 and Q15 requalification](L02f2b.md)
Entries: 2026-09-25T18:05-07:00 through 2026-09-25T18:35-07:00
Outcome: complete; see the [evidence](../evidence/L02f2b.md).
- Traffic already ran through shutdown; only the settling interval was missing.
- The old harness still failed the candidate at the same load (control).
- The reference's leftover burst comes before its carrier-up RCTL write.
- Correction (review R1): the first stated reason for 3 s was wrong for the candidate.

### [L02s — spec revision 5](L02s.md)
Entries: 2026-09-25T17:49-07:00 through 2026-09-25T18:12-07:00
Outcome: complete; revision 5 sets PSCON bit 11, 15 PASS after one round of fixes.
- The manual never says "set bit 11": the spec argues it as an `[inference]` from §8.4.2 and
  Table 13-31, confidence medium, with the contrary sentence recorded.
- The first verifier caught a wrong ordering claim: "Retain" in the bit table says what a
  reset keeps, not when a write applies; §11.1.3 makes bit 11 wait for an AN restart.
- The manual contradicts itself on TNCRS in half duplex (§8.4.2 against §13.7.12).
- Out-of-scope notes from both verifiers go to L02f3.

### [L02f2 — bounded repair and retest](L02f2.md)
Entries: 2026-09-25T16:45-07:00 through 2026-09-25T17:45-07:00
Outcome: complete after one round; the candidate binds and passes 9 of 10 scenarios past probe.
- The implementer runs under bubblewrap with a fresh Codex home; strace audits every read.
- The sandbox is codified in `cleanroom-implementer` (`cleanroom_sandbox.sh`, `sandbox_audit.py`).
- Round 1: E1 waits 10 ms, then proceeds to EERD with a warning; audit PASS after a pipe
  false positive in the audit was fixed.
- `down-during-traffic` fails at random (3 of 6): the reply reaches ICMP in every measured
  run; QEMU holds reception 1 s after any RCTL write, and with the candidate's faster carrier
  the hold ends as the ping starts, releasing ~30 leftover flood frames just ahead of the
  reply. Model plus harness (H1), not the candidate.
- The operator's machine crashed twice; entries for 16:48 and 16:51 are reconstructed, and
  the first code review was lost with the scratch space and rerun.
- Reviews: `review-swarm` 13 findings (fixed or left to the user); a fresh artifact reviewer
  14, all fixed, among them two wrong notebook statements (corrected at 17:45).
- First past-probe comparison: V7–V16, all `benign`; flow control off goes to L02f3.

### [L02f1 — differential run and attribution](L02f1.md)
Entries: 2026-09-25T15:06-07:00 through 2026-09-25T15:56-07:00
Outcome: complete; reference 10/10 PASS, candidate fails every scenario at probe (one cause).
- QEMU hard-wires EECD.EE_GNT = 1; the candidate enforces spec E1 (manual §13.4.4) and aborts.
- Labeled `benign`, model limitation; secondary spec gap: no bound or fallback in E1.
- The model also reads EECD.FWE = 00b, which the manual forbids; both drivers write it back.
- The run store was not on the test host; now a per-user setting (`docs/run-store-config`).
- Nothing after probe has run: L02f2 must repair before any real comparison.

### [L02d3 — check qualification](L02d3.md)
Entries: 2026-09-25T14:23-07:00 through 2026-09-25T14:43-07:00
Outcome: complete; 26 claims, 22 qualified by planted defects in isolated runs, 4 unqualified.
- The reference pads short frames in software (`eth_skb_pad`), so a padding defect must drop
  that as well as TCTL.PSP.
- Dead end: d09 (ring indices not reset on clean) is equivalent: open re-zeroes them.
- d16's checksum-gated corruption never ran; the model apparently never reports TCP-good.
- Removing the reset wait leaves 13 µs gaps: the 1 µs rule cannot be failed this way.
- The reviewer, reading captures, caught a reason written from memory (ARP at 42 bytes).

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
  [L02d3](L02d3.md) — qualified 22 of 26 claims with planted defects; the 1 µs reset rule
  stays unqualified. [L02f2](L02f2.md) — the reverse: a check that fails a correct driver at
  random (H1, `down-during-traffic`); [L02f2b](L02f2b.md) fixed it and requalified Q15.
- **Model departures from the manual:** [L02d2](L02d2.md) — no overrun drops, TX drains with
  the link down; [L02f1](L02f1.md) — EE_GNT always 1 and FWE = 00b in EECD;
  [L02f2](L02f2.md) — a one-second receive hold after every RCTL write.
- **Spec errors found downstream:** [L02e](L02e.md) — the reference review found a spec §5.4
  error (PSCON bit 11) that L02c's two readings passed; the implementer filed it during repair.
  [L02s](L02s.md) — corrected in revision 5; its own first draft had an ordering error that
  the verifier caught. [L02f3](L02f3.md) — revision 6 folds in every gap L02 filed; the
  verifiers' findings were mostly the operator's own fix-pass errors.
- **Model departures from the manual** (continued): [L02f3](L02f3.md) — all seven recorded in
  the spec as `[emulated]` EM1–EM7, with the rule that an entry cites runs, not mechanism.
  [SF-1](SF-1.md) — the class and that rule adopted into the format, the evidence model and
  the checker.
- **Spec errors found downstream** (continued): [AF-1](AF-1.md) — a second independent reading
  of revision 4's changes found no accuracy error the first had missed; the one disagreement
  was the spec's tag convention applied unevenly.
- **A check that cannot fail** (continued): [QF-1](QF-1.md) — Q24–Q26 shown able to fail by
  planted defects; the reset rule restated as what the trace can observe and still not shown
  able to fail on this host and model; a small-frame content corruption that no check sees.
- **Model departures from the manual** (continued): [QF-1](QF-1.md) — the model delivers
  runts at their wire length (42-byte ARP reaches the driver), for the next `[emulated]` table.
  [SR-7](SR-7.md) — recorded as EM8, from the captures alone.
- **Spec errors found downstream** (continued): [SR-7](SR-7.md) — a second reading of
  revisions 5 and 6 found three form and citation defects beside the changes, none an
  accuracy error; revision 7 applies them and AF-1's items.
- **Spec errors found downstream** (continued): [CF-1](CF-1.md) — updating the candidate to
  revision 6 surfaced one gap the revision does not close (TNCRS attribution across a duplex
  change), filed by the implementer and found again by two reviewers.
