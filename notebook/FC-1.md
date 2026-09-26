<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# FC-1 — a small-frame content check

Follow-on of the [plan](../IMPLEMENTATION-PLAN.md), from QF-1's finding F3. Terms: a
**claim** is a check whose PASS is cited as evidence about the candidate; it is
**qualified** when a planted defect made it fail for the claim's reason while the reference
passed; the **pattern payload** is what busybox `ping -p` sends (a 4-byte timestamp, then
one byte repeated). See the [glossary](../GLOSSARY.md) and the
[evidence](../evidence/FC-1.md).

## 2026-09-26T08:22-07:00 — opening: make small-frame content visible to the suite
Goal: give `frame-sizes` a content check, so that a driver that corrupts a 60- or 61-byte
frame past its headers fails something. Start: branch `driver-porting/fc1` from
`origin/main` at `9f8e43e`, own worktree, clean; harness `7024864e…` as QF-1 left it; the
candidate `ce7e3e2c…` from CF-1. QF-1's d21c (tail shifted by one byte from byte 46) passed
the scenario 3 of 3 because the payload past the timestamp is zeros.

## 2026-09-26T08:30-07:00 — the captures cannot see one of the four paths; the kernel's counter can
A pattern payload makes corruption matter, but where is it seen? The DUT's transmitted
frames are in the peer's capture (compare with the pattern); the peer's requests the DUT
received are seen through the DUT's echo replies (compare reply with request); the peer's
replies the DUT received are seen by nobody: busybox ping takes them from a raw socket,
which the kernel serves before it verifies the ICMP checksum, and `unpack4` checks the id
and type only. So a corrupted reply counts as received. The witness is `InCsumErrors` on
the DUT's `Icmp:` line of `/proc/net/snmp`: the kernel verifies every ICMP message after
the raw socket has its copy and counts the bad ones. Read before the pings and after each
one, the count attributes a rise to the ping that caused it. busybox 1.37's `ping` has `-p`
(one byte), and its source confirms the layout (timestamp, then the pattern) and that it
opens a raw socket only. Raw sockets and user namespaces are unavailable to this session,
so the layout is confirmed by the run, not locally.

## 2026-09-26T08:38-07:00 — two defects, one per direction; the shared decoder shown identical offline
d21c qualifies the receive side; for the transmit side a new defect, d24, flips bit 0 of
frame byte 50 in every frame of 51 to 100 bytes after the software padding: payload byte 8
of a 60/61-byte echo, padding for ARP and the padded 42-byte echo, nothing for 1513/1514.
The decoder behind `icmp_echoes()` was rewritten to carry id, sequence and payload; old and
new give identical output on all 484 stored captures (1,270,293 frames), which is the
argument that the `capture` pseudo-scenario and the sent-sizes check did not change. On
QF-1's stored captures the new echo check passes for d21c (F3 reproduced offline, before
any run) and the pattern checks fail everywhere, since that stimulus carried no pattern.

## 2026-09-26T08:41-07:00 — declaration committed, 52 runs launched
Round f1: the acceptance set (ten scenarios, reference ×2 and candidate ×2) on the changed
harness, `frame-sizes` ×3 more per driver, d21c ×3 and d24 ×3. Each check's expected verdict
for both defects is in the evidence and the ledger, committed at `612ec59` (08:41:24)
before the first run. The one contingency named: d21c's shift pulls in the byte beyond the
frame, which was 0 in QF-1's buffers; a frame whose beyond-byte equals its pattern byte
would pass unchanged.

## 2026-09-26T08:44-07:00 — 52 runs in 109 s; both defects fail as declared, and ping counts the corrupted replies as received
Reference 20 of 20 and candidate 20 of 20 on the acceptance set, `frame-sizes` 5 of 5 each,
1,118 checks and no failure; the captures show the pattern where the check expects it, so
the `-p` layout read from busybox's source holds. d21c fails the checksum-error check in
every run with +2 on each of the four 60/61-byte pings, and on the DUT's own pings that is
the only failing check: ping reported `0% packet loss` while the kernel counted every reply
bad. That is the F3 gap closed at the exact spot QF-1 predicted. d24 fails the two capture
comparisons at frame byte 50 with the flipped values named.

## 2026-09-26T08:50-07:00 — the declaration applied two rules to one program
d24's one departure from the declaration: "peer pings DUT with 60/61-byte frames" passed. I
had reasoned that the peer's kernel would drop the DUT's corrupted replies, forgetting that
the peer's ping is the same busybox on the same raw socket as the DUT's, which gets the
reply before the checksum is checked. So the peer counted the corrupted replies as received,
exactly as the DUT does under d21c. The content checks saw the corruption either way, which
is the point of having them; the lesson is that none of the four arrival checks at 60/61
bytes can ever see a corrupted reply, on either side. The frozen section's "08:42" against a
commit at 08:41:24 is a records nit, corrected.

## 2026-09-26T09:04-07:00 — the review's one real finding, fixed and rerun; the record's clocks straightened
The reviewer recomputed everything, parsed the captures itself and found one gap in the new
check: a counter read that failed mid-run reset the comparison, so a rise across the gap
would have been lost (never exercised: all 160 reads succeeded). A failed read now fails
the check and comparisons are against the last successful read; `frame-sizes` rerun on the
final harness for both drivers and both defects, 8 of 8 as declared. The other findings
were the record's own clocks: the notebook's 08:50 entry and the index were committed at
08:47:46, so this entry carries its real time; "24 frames per run" was 8; d24 also touches
the DUT's IPv6 housekeeping frames, which nothing reads.
