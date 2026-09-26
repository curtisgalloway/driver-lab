<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CS-1 — checksum-preserving corruption of received small frames

Follow-on of the [plan](../IMPLEMENTATION-PLAN.md), from FC-1's open limitation. Terms: a
**claim** is a check whose PASS is cited as evidence about the candidate; it is
**qualified** when a planted defect made it fail for the claim's reason while the reference
passed; a **checksum-preserving corruption** swaps two 16-bit words or makes a
compensating two-byte change, so every ones'-complement checksum over the frame stays
valid. See the [glossary](../GLOSSARY.md) and the [evidence](../evidence/CS-1.md).

## 2026-09-26T09:10-07:00 — opening: make a checksum-preserving corruption of a received reply visible
Goal: a stimulus whose received payload the DUT verifies end to end. Start: branch
`driver-porting/cs1` from `origin/main` at `57273d6`, own worktree, clean; harness
`884e771c…` as FC-1 left it; the candidate `ce7e3e2c…` from CF-1. The KVM slot is held
by another session for hours, so this pass does everything but the runs. FC-1's gap: a
reply the DUT receives with two words swapped passes the kernel's ICMP checksum and
ping's raw socket, and both captures sit on the wire side of the driver.

## 2026-09-26T09:20-07:00 — TCP over busybox, with the peer's MTU as the size clamp
Options weighed: a static UDP sender and receiver in the guest image (a new program to
pin and build), or busybox's own TCP tools. TCP's checksum is the same ones'-complement
sum, so a word swap reaches the application, and `ring-wrap` already compares an HTTP
transfer by MD5 with `httpd`, `wget` and `md5sum`. The missing piece was making the
frames small: lowering the peer's MTU to 200 bounds its own sends by the MTU and the
DUT's by the MSS the peer advertises from it, so the DUT's configuration is untouched (no
`ndo_change_mtu`, which the two drivers may implement differently). Frames are 214 bytes,
inside the reference's copybreak path, whose copy sees the descriptor length with the
FCS (218 of 256). The reference advertises TSO on this part, so the DUT's stream may be
segmented by the model; the wire frames and the peer's MD5 are the same either way, and
the transmit defect handles both skb shapes with `skb_copy_bits`/`skb_store_bits`.

## 2026-09-26T09:29-07:00 — the premise on real captures; d25 and d26 built; declaration written
On FC-1's four stored `ring-wrap` runs every TCP frame verifies, every data frame of at
least 204 bytes still verifies after the swap at bytes 200/202 (the swap changed every
one), and a flipped byte fails every one. On the stored `frame-sizes` captures the same
swap inside the 60/61-byte echoes' one-byte pattern changes no byte at all. d25 (receive,
in the copybreak copy) and d26 (transmit, after the padding) built with no warnings. The
`ring-wrap` transfer function was reparameterized with its strings held byte for byte by
a test, so the acceptance set is rerun for both drivers as FC-1 did. Round `c1` declared:
52 isolated runs, each defect expected to fail exactly its own stream check, 3 of 3.
Stopped before any run: ready for the KVM slot.

## 2026-09-26T10:12-07:00 — round c1 in 1 min 45 s; not as declared: the DUT sent 310-byte frames
52 runs, 36 PASS, 16 FAIL. Every `frame-sizes` run failed the stimulus check, and only
its DUT-to-peer half: the peer's frames were 214 bytes as designed, the DUT's 310. Nothing
was analyzed until the KVM window closed.

## 2026-09-26T10:17-07:00 — the kernel floors the advertised MSS at 256
The peer's SYN carried MSS 256 in all 16 runs: `ipv4_default_advmss` takes the larger of
the MTU less 40 and `route.min_adv_mss`, whose default is 256, so the peer's MTU bounded
the DUT's segments only down to that floor. A premise error in the check's design, not a
driver finding: both drivers delivered both 1 MiB streams intact in every run, and the
stimulus check did exactly what it is for. d26's 1 of 3 is the same error seen from the
defect: 310-byte skbs and `gso_size` 244 fall outside its conditions, and only run 1 had
partial 210-byte segments inside them. Fix on the peer only: lower the floor to 160 in the
same command as the MTU, restore both. Round c2 declared: `frame-sizes` ×5 each driver and
×3 each defect on the new harness; the other nine scenarios' c1 results stand, since the
diff touches only the two peer commands and their check names, a decision taken after
seeing the results and said so in the evidence.

## 2026-09-26T10:33-07:00 — round c2 as declared; both defects caught 3 of 3; d25 shows the FC-1 gap closed
The user launched c2 (my launch command was refused by the agent harness's safety check),
10:29:41 to 10:30:15. The peer now advertises MSS 160 and the DUT's stream goes in 214-byte
frames; the stimulus check passes in all 16 runs. Reference and candidate 5 of 5 with both
MD5s equal; d25 and d26 each fail exactly their own stream check 3 of 3, wget completing
every time: the swapped words passed every checksum and reached the application, which is
the corruption no check could see before. One retransmission burst (26 segments) in one
d25 run and the candidate's different partial-segment pattern are observations. Rebased
onto SR-8's merge, keeping both units' plan and index text.

## 2026-09-26T12:44-07:00 — review: seven findings, all on the records; the unit closes
A first reviewer was stopped with the session at the quota pause; a fresh one from the same
brief recomputed every verdict, identity and capture fact, reproduced the DUT's corrupted
MD5s from the captures under both defects, and found nothing that changed a result: four
record corrections (stale check names and pre-rebase hashes in the evidence, one wrong
segment count, the plan and index behind the checkpoint), three notes (the expected-hash
file compares only the candidate module; the process-log entry uncommitted; a failed
`ip link` would leave the peer's MSS floor lowered). Applied or recorded; no harness
change after the runs, so no further round. Times in this unit were written from
expectation three times before a `date` caught them; the process log has the lesson.
