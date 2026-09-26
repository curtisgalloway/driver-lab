<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CS-1: checksum-preserving corruption of received small frames

## Terms

- **Claim**, **qualified**, **precondition**, **planted defect**, **isolated run** — as in
  the [L02d3 evidence](L02d3.md#terms). **Candidate** — `e1000_l02` as CF-1 left it (spec
  revision 6, module `ce7e3e2c…`); **reference** — Linux v6.12's `e1000`.
- **Checksum-preserving corruption** — a change to a frame's bytes that leaves every
  ones'-complement checksum over them unchanged: two 16-bit words at even offsets
  swapped, or a compensating two-byte change. IP, ICMP, TCP and UDP all use that sum, so
  the stack accepts such a frame.
- **Small-frame streams** — 1 MiB over HTTP each way, added to `frame-sizes` by this unit,
  in frames of at most 214 bytes: the peer's MTU is lowered to 200 while they run.
- **Copybreak path** — the reference's receive path for frames of at most 256 bytes
  (descriptor length, which counts the 4-byte FCS the model reports), which copies the
  frame into a small buffer; d21c (QF-1) and d25 (here) are planted in it.
- **Acceptance set** — L02f3's run set: all ten suite scenarios, isolated, reference ×2 and
  candidate ×2, 40 runs.

See the [glossary](../GLOSSARY.md), the [design](../QEMU-DIFFERENTIAL.md) (§7, A6), the
[plan](../IMPLEMENTATION-PLAN.md) (CS-1), the [FC-1 evidence](FC-1.md) (the open
limitation this unit answers) and the [notebook chapter](../notebook/CS-1.md).

## Status

**In progress, 2026-09-26.** The harness change, its tests, the two planted defects and
the run declaration below are done and committed; no run of this unit has been made,
because the test host's KVM slot is held by another session. The runs, the results, the
qualification and the review follow when the slot is free.

## The gap (FC-1, open limitation)

FC-1's checks see a corruption of a 60- or 61-byte frame through the ICMP checksum (the
kernel's checksum-error count, a dropped request) or through the echo (the DUT's reply
compared with the peer's request). A corruption that keeps the checksum in a **reply the
DUT receives** is seen by neither: the kernel accepts the reply, busybox `ping` reads it
from a raw socket and compares nothing past the id and type, and both captures sit on
the wire side of the driver. ping's payload is one repeated byte, so even a swap of two
words inside it changes nothing; busybox has no tool that sends a chosen payload over
ICMP or UDP (its `nc` has no UDP mode). Q09 (4 MiB over HTTP, `ring-wrap`) compares the
delivered bytes by MD5, but in 1514-byte frames, and was qualified only by a
checksum-breaking defect that stalled the transfer (L02d3).

## The check

After its pings, `frame-sizes` lowers the peer's MTU to 200, serves 1 MiB of random
bytes over HTTP from the peer to the DUT and then from the DUT to the peer (port 8081,
so a capture check can tell the streams from `ring-wrap`'s transfer on 8080), compares
`wget`'s MD5 of the bytes the receiving stack delivered with the sender's MD5 of the
file, and restores the peer's MTU. Every existing check name is unchanged; the pings
and their content checks are unchanged.

| Check (`frame-sizes`) | Reads | Shows |
| --- | --- | --- |
| "1 MiB over HTTP in small frames peer to DUT arrives intact" | the MD5 the DUT's `wget` computed against the peer's | What the driver delivered to the DUT's stack is what the peer sent, byte for byte, over about 7,100 frames of at most 214 bytes: the claim's receive half. A corruption that keeps TCP's checksum reaches `wget` and changes the MD5; one that breaks it stalls the transfer (Q09's failure shape) |
| "1 MiB over HTTP in small frames DUT to peer arrives intact" | the MD5 the peer's `wget` computed against the DUT's | What reached the peer is what the DUT's stack gave the driver: the claim's transmit half |
| "peer's MTU set to 200 for the small-frame streams", "peer's MTU restored to 1500 after the small-frame streams", "HTTP server with a 1 MiB file (peer to DUT)", "… (DUT to peer)" | the peer's and the DUT's command results | Preconditions: the stimulus was set up and taken down |
| "the small-frame streams' data frames were at most 214 bytes and carried 1 MiB each way" | both captures: the peer's data frames from the DUT's capture (what entered its device), the DUT's from the peer's | The stimulus: each stream ran in small frames and carried the whole 1 MiB. A precondition, not a claim; a stalled stream fails it too |

**Why the peer's MTU.** TCP's checksum is the same 16-bit ones'-complement sum as
ICMP's, so a word swap survives it and reaches the application; MD5 over the delivered
bytes is then the witness, in either direction. The frames have to be small for the
receive path under test to be the small-frame one (the reference's copybreak path takes
frames up to 256 bytes with the FCS), and lowering the **peer's** MTU bounds both
directions: the peer's own sends by its MTU, the DUT's by the MSS the peer advertises
from it. So nothing changes on the DUT, and no MTU change reaches the driver under test,
whose `ndo_change_mtu` the two drivers may implement differently (the reference takes a
running interface down and up on one). The payload is `/dev/urandom`, as `ring-wrap`'s, so every frame's
bytes are distinct and any swap that moves bytes changes the MD5.

**Why not a UDP sender in the guest image.** A static sender and receiver with a chosen,
position-dependent payload would do the same for UDP, at the cost of a new program in
the initramfs with its own source, build and pin. busybox `httpd`, `wget`, `md5sum`,
`dd` and `ip link set … mtu` are already in the pinned image (1.37.0, `df12634c…`) and
already used by `ring-wrap` (all but the MTU change); the whole addition is one scenario
step and one capture check, and the guest image is unchanged.

**The reference transmits with TSO.** The reference advertises TCP segmentation offload
on the 82540EM, so the DUT's stream may leave its stack as large skbs that the model
segments at the 148-byte MSS; the wire frames and the MD5 at the peer are the same
either way, and the transmit defect below is written for both skb shapes. The candidate's
features are not known to this unit and do not matter to the check.

**Claim.** A new claim rather than a change to Q27's or Q09's frozen text: Q27 names 60-
and 61-byte ICMP frames and its qualifying defects are checksum-visible; Q09 is
`ring-wrap`'s 4 MiB in 1514-byte frames, qualified as a stalled transfer; this is a
different check on different frames, and the claim list's precedent for a new check is a
new claim added before the candidate's first run of it (Q25–Q27). Declared here before
any run:

| ID | Claim | Checks (scenario) |
| --- | --- | --- |
| Q28 | A 1 MiB TCP stream in frames of at most 214 bytes is received and transmitted with its content intact, as the MD5 of the delivered bytes shows | "1 MiB over HTTP in small frames peer to DUT arrives intact" (receive); "… DUT to peer arrives intact" (transmit) (frame-sizes) |

**Shared code.** `http_blob()`, `ring-wrap`'s transfer, gained size, port and wording
parameters whose defaults reproduce its commands and check names byte for byte (a test
holds the literal strings). A TCP segment decoder (`tcp_segments()`) is new and used by
the stimulus check only; the ICMP decoder is untouched. Offline, before any run, on
FC-1's four stored `ring-wrap` runs: every IPv4 TCP frame in every capture verifies its
TCP checksum (6,167 to 7,485 per capture); after swapping the 16-bit words at frame bytes
200 and 202 of every data frame of at least 204 bytes (5,797 to 5,844 per capture) every
one still verifies, the swap having changed every one; a flipped byte 200 fails every
one. On FC-1's stored `frame-sizes` captures, swapping two words inside the 60/61-byte
echoes' pattern changes no byte at all (the pattern is one repeated byte), which is the
FC-1 blind spot made concrete. The new decoder finds `ring-wrap`'s data frames on port
8080 (about 2,900 each way, at most 1514 bytes, 4,194,497 payload bytes each way, the
4 MiB plus the HTTP headers) and no stream on 8081 there. 70 harness tests pass (58
before; 12 for the changed surface: the decoder, the checksum-preservation premise for
TCP and ICMP, the stimulus check's pass and each failure, `ring-wrap`'s unchanged
strings, the scenario's order and the MTU restore when the DUT dies mid-stream).

## Frozen before execution (2026-09-26)

Private run `cs1-20260926-01`. The candidate does not change in this unit.

| Artifact | Identity |
| --- | --- |
| Harness | `l02harness.py` `da4c9407…` (this unit's change; round `c1`), `guest-init.sh` `eccecebe…` (unchanged); the previous harness was `884e771c…` (FC-1 final) |
| Reference module | `e1000.ko` `43242751…` |
| Candidate module | `e1000_l02.ko` `ce7e3e2c…` (CF-1 round 1) |
| Kernel, QEMU, busybox | `0d96151b…`; 10.2.1+ds-1ubuntu3.2, `0cd4112a…`, KVM, DUT memory 3 GiB; `df12634c…` (busybox 1.37.0) |
| Defects (modules) | d25 `9dbee0dd…`, d26 `72510962…`, built out of tree against the same kernel with `gcc-14`, 0 warnings each |
| Run script and job list | `run1.sh` `6618f966…`, `jobs-c1.txt` `84b47350…` (52 lines) |

- **d25** (receive): after the copybreak copy, when the descriptor length is at least 208
  (a wire frame of at least 204 bytes, the FCS counted), the 16-bit words at frame bytes
  200 and 202 are swapped. In `frame-sizes` that range holds the peer's stream data
  frames (214 bytes; bytes 200–203 are payload bytes 134–137 of the segment) and possibly
  the peer's HTTP response header frames, and no ICMP (60, 61, 98, 1513, 1514 and the
  42-byte frames), ARP (42) or IPv6 housekeeping frame (70 to 90).
- **d26** (transmit): after the software padding, the words at skb offsets 200 and 202
  are swapped in every skb of 204 to 256 bytes and in every GSO skb segmented for an MSS
  of at most 200, through `skb_copy_bits` and `skb_store_bits` so a payload in page
  fragments is reached; in a GSO skb the swap lands in the first segment's payload. The
  streams' skbs are affected whichever shape the stack gives them; the 60/61-byte echoes,
  the 1042-byte flood frames, the 1513/1514-byte pings and `ring-wrap`'s 1448-byte MSS
  are not.

**Run declaration (round `c1`, 52 isolated runs, eight in parallel).**

- The acceptance set on the changed harness: all ten suite scenarios, reference ×2 and
  candidate ×2 (40 runs). Criterion: reference 20 of 20 PASS, candidate 20 of 20 PASS on
  every check. The harness file changed and a shared function (`ring-wrap`'s transfer)
  was reparameterized (its strings shown identical by test), so every earlier
  qualification's scenario is rerun for both drivers.
- `frame-sizes` ×3 more for each driver (5 each in all): every check PASS, the seven new
  ones included (30 checks in the scenario, 36 with the trace rules); both stream checks
  with equal MD5s; the stimulus check reporting about 7,100 data frames of at most 214
  bytes each way carrying at least 1,048,576 bytes.
- d25, `frame-sizes` ×3 (Q28, receive), expected in 3 of 3: exactly one failed check,
  "1 MiB over HTTP in small frames peer to DUT arrives intact", with `sent` and `got`
  different MD5s and `wget` completing (the swap keeps TCP's checksum, so nothing is
  dropped or retransmitted and the transfer does not stall); every other check PASS,
  among them the DUT-to-peer stream, the stimulus check (the wire frames are the peer's,
  unchanged), every ping and ICMP content check, the checksum-error count, bring-up,
  runts, rmmod, the kernel log and the trace rules. Contingency: a swapped HTTP response
  header frame could make `wget` fail instead; the check still fails, with a `got` that
  is not the MD5 of a full body, and it is reported.
- d26, `frame-sizes` ×3 (Q28, transmit), expected in 3 of 3: exactly one failed check,
  "1 MiB over HTTP in small frames DUT to peer arrives intact", `sent` and `got`
  different, `wget` completing (the model computes the TCP checksum after the swap when
  the driver offloads it, and the swap keeps it when it does not); every other check
  PASS, the peer-to-DUT stream and the stimulus check included (the frames' lengths are
  unchanged). Contingency: the DUT's HTTP response header skb, if 204 to 256 bytes or a
  GSO skb, is swapped too and the peer's `wget` could fail on it; the check still fails
  and it is reported.
- Every failure is kept, attributed and reported; no run is repeated to replace a result.
  A reference or candidate failure blocks the corresponding conclusion. Every run's
  `identities.json` must record the hashes above.

The declaration is in the run's ledger and here, committed before any run; the launch
time and the first scenario's start are recorded when the runs are made.

## Results

Pending: no run yet (the KVM slot).

## Qualification

Pending.

## Acceptance (against the brief)

| Criterion | Result |
| --- | --- |
| A stimulus whose received payload the DUT verifies end to end, so a checksum-preserving corruption is detected | The check is implemented and tested offline; the runs are pending |
| Smallest addition that works, justified | No guest-image change: busybox's `httpd`, `wget`, `md5sum`, `dd` and `ip link set … mtu`, one scenario step and one capture check (above) |
| Check names stable; new checks and a claim, with the convention said | Every existing name unchanged (`ring-wrap`'s strings held by a test); Q28 a new claim, with the reasons above |
| Harness tests for the changed surface | 12 new tests, 70 pass |
| Planted defects for receive and transmit, built; counts and expected outcomes declared before any run | d25 and d26 built (0 warnings); the declaration above, committed |
| Reference and candidate on the declared repetitions; whatever else the change touches rerun | Pending (the acceptance set ×2 each and `frame-sizes` ×5 each are declared) |

## Findings

None yet.

## Review

Pending (one independent reviewer reading the diff and the run artifacts, after the runs).

## Measures

- Operator time so far: about 09:10 to the first checkpoint on 2026-09-26 (Pacific), one
  session; see the notebook. Model cost not measured.
- Host time so far: the two defect builds, about 20 s each; the offline premise checks
  about 1 minute.

## Open limitations (so far)

- One corruption shape per direction (two adjacent words swapped at one offset); a
  compensating two-byte change or a swap elsewhere in the frame is not planted.
  Qualification is defect-specific, as in L02d3.
- The streams' frames are at most 214 bytes; the copybreak boundary itself (252 bytes on
  the wire, 256 with the FCS) and frames between are not exercised, and a driver whose
  small-frame path starts elsewhere is exercised at 214 bytes only.
- The corruption must survive to the application to be seen: a checksum-preserving
  corruption of a TCP header field (a port, a sequence number) is seen as a lost or
  stalled transfer, not attributed.
- The transmit half rests on the wire frames and the peer's MD5; whether the reference's
  driver or the model segmented the DUT's stream is not observed.
- `ring-wrap`'s Q09 stays qualified only as a stalled transfer; the same defect shape at
  frames over 1,000 bytes would qualify it for content too, a possible follow-on.
- Subagent transcripts are recorded by path in the run's ledger; those paths are temporary.
