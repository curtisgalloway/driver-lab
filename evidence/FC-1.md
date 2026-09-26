<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# FC-1: a small-frame content check

## Terms

- **Claim**, **qualified**, **precondition**, **planted defect**, **isolated run** — as in
  the [L02d3 evidence](L02d3.md#terms). **Candidate** — `e1000_l02` as CF-1 left it (spec
  revision 6); **reference** — Linux v6.12's `e1000`.
- **Pattern payload** — the payload busybox `ping -p` sends: its 4-byte timestamp, then one
  byte repeated. Without `-p` the timestamp is followed by zeros.
- **Copybreak path** — the reference's receive path for frames of at most 256 bytes, which
  copies the frame into a small buffer; d21c is planted in it (QF-1).
- **Checksum-error count** — `InCsumErrors` on the `Icmp:` line of `/proc/net/snmp`: ICMP
  messages the kernel dropped for a bad checksum. The kernel verifies every ICMP message,
  echo replies included, after a raw socket (busybox ping's) has received it.
- **Acceptance set** — L02f3's run set: all ten suite scenarios, isolated, reference ×2 and
  candidate ×2, 40 runs.

See the [glossary](../GLOSSARY.md), the [design](../QEMU-DIFFERENTIAL.md) (§7, A6), the
[plan](../IMPLEMENTATION-PLAN.md) (FC-1), the [QF-1 evidence](QF-1.md) (F3, the finding
this unit answers) and the [notebook chapter](../notebook/FC-1.md).

## Status

**In progress, 2026-09-26.** Declaration below; results follow.

## The gap (QF-1, F3)

`frame-sizes` checked that 60- and 61-byte frames *arrive* (Q25), not what they carry. A
ping's payload past its 4-byte timestamp is zeros, so QF-1's d21c, which shifts every
received small frame's tail by one byte, passed the scenario 3 of 3: shifted zeros are zeros,
and the peer's capture showed every reply equal to its request. Q09 (4 MiB over HTTP)
covers large frames only, and only as a stalled transfer.

## The check

`frame-sizes` now sends its 60- and 61-byte pings, both directions, with a one-byte pattern
(`ping -p`; `0xa5` for 60-byte frames, `0x5a` for 61), and judges the content three ways.
Every existing check name is unchanged; the 42-, 1513- and 1514-byte pings are unchanged.

| Check (`frame-sizes`) | Reads | Shows |
| --- | --- | --- |
| "the DUT's kernel counted no ICMP checksum errors while the pings ran" | `/proc/net/snmp` on the DUT before the pings and after each of the nine | Frames the driver delivered arrived intact, echo replies included. This is the only witness for a reply the driver delivered corrupted: ping's raw socket receives the reply before the kernel verifies it, so ping counts it as received (arrival) while the kernel counts the error (integrity). The detail names the pings during which the count rose |
| "the DUT echoed the peer's 60- and 61-byte echo requests byte for byte" | the peer's capture; each request matched to the reply with its ICMP id and sequence number | The request reached the DUT's stack intact and the reply left the DUT intact (a corrupted request that the kernel dropped shows as "no reply") |
| "the DUT's 60- and 61-byte echo requests reached the peer with the pattern payload intact" | the peer's capture | What the driver transmitted is what the stack gave it, past the timestamp |
| "the peer's 60- and 61-byte echo requests and replies reached the DUT's device with the expected payload" | the DUT's capture (the frames that entered its device) | The stimulus: the peer's requests carried the pattern and its replies repeated the DUT's requests. A precondition, not a claim |

Why captures alone cannot do it: both captures sit on the wire side of the driver, so a
frame the driver delivers corrupted to the stack is visible only through what the stack does
with it, an echo reply or a checksum error. Why one byte: busybox `ping -p` takes one byte,
so a shift that stays inside the pattern is still invisible; a shift into the byte beyond
the frame, a flipped byte, a stale tail or a wrong length is not (limitation below).

**Claim.** A new claim rather than a change to Q25's frozen text, for three reasons: Q25 is
arrival ("frames of 60 and 61 bytes are received"), qualified by d21b, and stays as it is;
content is a different behavior, which is what F3 says; and the claim list's precedent for
a new check is a new claim added before the candidate's first run of it (Q25 and Q26 in
L02d3). Declared here before any run:

| ID | Claim | Checks (scenario) |
| --- | --- | --- |
| Q27 | Frames of 60 and 61 bytes are received and transmitted with their content intact | the checksum-error count; the DUT echoed the peer's requests byte for byte; the DUT's requests reached the peer with the pattern intact (frame-sizes) |

**Shared code.** `icmp_echoes()`, which the `capture` pseudo-scenario and the sent-sizes
check use, is now a projection of the new decoder. Offline, before any run, the old and new
functions gave identical output on all 484 captures stored from every earlier run (1,270,293
frames). On QF-1's stored `frame-sizes` captures the new echo check passes for the reference,
the candidate and d21c (F3 reproduced offline) and fails for d21 and d21b (no replies); the
two pattern checks fail on every stored capture, as they must for a stimulus that carried
no pattern. 57 harness tests pass (44 before, 13 for the changed surface).

## Frozen before execution (2026-09-26, 08:42 Pacific)

Private run `fc1-20260926-01`. The candidate does not change in this unit.

| Artifact | Identity |
| --- | --- |
| Harness | `l02harness.py` `9c33f54d…` (this unit's change), `guest-init.sh` `eccecebe…` (unchanged); the previous harness was `7024864e…` (QF-1, CF-1) |
| Reference module | `e1000.ko` `43242751…` |
| Candidate module | `e1000_l02.ko` `ce7e3e2c…` (CF-1 round 1) |
| Kernel, QEMU, busybox | `0d96151b…`; 10.2.1+ds-1ubuntu3.2, `0cd4112a…`, KVM, DUT memory 3 GiB; `df12634c…` (busybox 1.37.0, whose `ping` has `-p`) |
| Defects (modules) | d21c `5ff074ae…` (QF-1's module, unchanged); d24 `9d48bc1d…` (new, built out of tree against the same kernel, 0 warnings) |
| Run script and job list | `run1.sh` `42733562…`, `jobs-f1.txt` `79e0028b…` (52 lines) |

- **d21c** (QF-1): the copybreak copy's second part starts one byte too far, so received
  frames longer than 46 bytes arrive with their tail shifted by one byte; the byte pulled in
  is the one beyond the frame in the receive buffer (0 in QF-1's runs).
- **d24** (new, transmit): after the software padding, bit 0 of frame byte 50 is flipped in
  every frame of 51 to 100 bytes. Byte 50 is payload byte 8 of a 60- or 61-byte echo, inside
  the pattern; for ARP and the padded 42-byte echo it is padding; 1513- and 1514-byte frames
  are untouched.

**Run declaration (round `f1`, 52 isolated runs, eight in parallel).**

- The acceptance set on the changed harness: all ten suite scenarios, reference ×2 and
  candidate ×2 (40 runs). Criterion: reference 20 of 20 PASS, candidate 20 of 20 PASS on
  every check. The harness file changed and a shared decoder was reimplemented (shown
  byte-identical offline), so every earlier qualification's scenario is rerun for both.
- `frame-sizes` ×3 more for each driver (5 each in all): every check PASS, the four new ones
  included; the checksum-error count unchanged; the content details report two requests of
  each size per direction.
- d21c, `frame-sizes` ×3 (Q27, receive), expected in 3 of 3: bring-up and the 42-, 1513- and
  1514-byte pings PASS; "DUT pings peer with 60-byte frames" and "… 61-byte frames" **PASS**
  (the reply's shifted tail ends in the byte beyond the frame, its checksum fails, and the
  kernel drops it after ping's raw socket already has it: arrival, not integrity); "peer
  pings DUT with 60/61-byte frames" FAIL (the request's checksum fails; no reply); the
  checksum-error check **FAIL** with +2 during each of the four 60/61-byte pings (8 in all),
  the claim's own failure and, on the DUT's own pings, the only failing check; "the DUT
  echoed … byte for byte" FAIL with "no reply" for the peer's four requests (the claim's
  failure as the kernel's checksum saw it); the pattern check and the stimulus check PASS;
  sent-sizes FAIL on the missing 60/61-byte replies (a consequence); runts, rmmod, the
  kernel log and the trace rules PASS. Contingency: a frame whose byte beyond the frame
  equals its pattern byte would pass unchanged; any such frame is reported.
- d24, `frame-sizes` ×3 (Q27, transmit), expected in 3 of 3: bring-up and the 42-byte ping
  PASS (byte 50 is padding there); "DUT pings peer with 60/61-byte frames" FAIL (the peer
  drops the corrupted request); 1513/1514 PASS; "peer pings DUT with 60/61-byte frames" FAIL
  (the DUT's reply is corrupted on transmit); the checksum-error check PASS (nothing corrupted
  reaches the DUT); the pattern check **FAIL**, each of the DUT's four requests "differs at
  frame byte 50"; the echo check **FAIL**, each reply "differs at frame byte 50" (both the
  claim's own failure); the stimulus check FAIL with "no reply" for the DUT's four requests
  (a consequence: the peer never replied); sent-sizes, runts, rmmod, the kernel log and the
  trace rules PASS.
- Every failure is kept, attributed and reported; no run is repeated to replace a result.
  A reference or candidate failure blocks the corresponding conclusion.

The declaration is in the run's ledger and here, committed before the first run.
