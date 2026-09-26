<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# L01 hardware unit — the candidate and the reference on the Pi 4 fixture

The second unit of L01, started once the fixture was wired ("go", 2026-09-26). Terms: the
**candidate** is `enc28j60_l01` as the first unit's repair round 1 left it; the **reference**
is the v6.12 `enc28j60` driver; the **DUT** is the ENC28J60's interface under whichever driver
is bound; the **peer** is a virtual interface on the fixture's built-in Ethernet in its own
namespace. See the [glossary](../GLOSSARY.md) and the [evidence](../evidence/L01-hw.md).

## 2026-09-26T14:01-07:00 — opening: the fixture answers to its name, and the name is the right port
Goal: exercise both drivers on the hardware under one configuration, with declared checks,
evidence that each condition occurred, and planted defects that show the checks can fail.
Start: branch `driver-porting/l01b` from `origin/main` at `3ea64ef`, own worktree, clean.
The fixture's name resolves to its built-in Ethernet, on the same subnet as this workstation;
`spi0.0` is `microchip,enc28j60` at 12 MHz with the interrupt on GPIO 25, and nothing is bound
to it. `tcpdump` and `iperf3` were missing and went in with apt; everything else was there.

## 2026-09-26T14:07-07:00 — both drivers build against 6.18 unchanged
The reference (v6.12) and the candidate compile out of tree against the Pi's installed 6.18
headers with `W=1` and zero warnings, without touching a line. The adaptation the plan
allowed for is empty; nothing to record on either side. The first setup load of the
reference showed NetworkManager bringing the new interface up for its carrier probe (no
connection activated), 15 interrupts on the GPIO line, and `link up - Half duplex`.

## 2026-09-26T14:20-07:00 — the development runs: what the reference does that the plan did not expect
Two development runs of the harness on the reference and one on the candidate, none of them
evidence. Four discoveries, all on the reference:
- R-03 is real: every received frame is delivered 4 bytes long, the FCS included (a 60-byte
  ping arrives as 64). The candidate delivers the wire length.
- Pings from the peer to the DUT average 158 ms (max 1 s) while the other direction is 1 ms.
  The candidate: 1.2 ms both ways. A received frame waits for something else to run the
  reference's handler; the 100 ms poll the candidate added (B-12) is what bounds it there.
- After every `down`/`up`, 0 of 3 pings answered in 20 of 20 cycles, carrier back in 2 s each
  time (the candidate: 3 of 3, carrier in 0.1 s, since it never parks the chip in power-save).
- `rmmod` under a ping flood hung in `free_irq`, waiting for a threaded handler that never
  returned; the stack is in the run store. The task sat in D state, the shutdown waited on
  it, and the fixture came back six minutes after `reboot`. The candidate's `rmmod` under
  the same flood took 0.1 s.
And one on the fixture: TCP receive overflows the 6.5 KiB ring as a matter of course (the
sender is on a gigabit port; TCP retransmits), so a check that demands zero receive drops
fails both drivers for a reason that is neither driver's. The pass rules were set before the
primary runs to judge receive errors beyond overflow, and to leave `rx_dropped` alone in idle
windows, where the switch's spanning-tree hellos raise it every 2 s.

## 2026-09-26T14:36-07:00 — declared and launched
Harness frozen at `cb42e46b…`, the checks, expectations and six planted defects committed
(`933904f`), eleven runs queued: two per driver interleaved, six defects, one diagnostic run
of the reference with its debug messages on for the three checks it failed or hung.

## 2026-09-26T14:58-07:00 — round p1: the candidate 10 of 10 then 9 of 10, the reference 8 of 10 twice, and the two failures are the same two
The candidate passed every check in its first run and all but C7 in its second, where the
LAN's own multicast overflowed the ring twice in the idle window (55 frames in 3 s) with the
pings and the transfer intact: a rule that was too strict, and asymmetric, since the
reference's overflow counter was never judged. The reference failed C6 and C7 in both runs,
the same way each time (0 of 3 pings after every reopen, carrier back in 2 s; after the flood,
10 of 10 pings but the check's other terms unmet), and its `rmmod` did not hang either time:
the hang stands as seen once, with its stack. Its peer-to-DUT pings: the first ten answered
2053, 1854, 1651 … 223 ms apart, one queue draining 200 ms at a time, then 1.2 ms; the
candidate's, 1.2 ms from the first. Defect d1 (a wrapped pointer treated as corrupt) failed
C3, C4b, C5 and C9 and left its driver bound, so the fixture went round a reboot.

## 2026-09-26T15:07-07:00 — blocked by the SSH agent; round r2 declared meanwhile
At 15:05 the forwarded SSH agent began refusing to sign for the fixture's key; the desktop
1Password agent locked or wants approval, and the key is in the human-only vault, so there is
no agent-side way round it (homelab-ssh). The runner had read the failed ssh as "a driver is
bound" and issued reboots, and the first launch had run one job because ssh ate the job
list's stdin; both fixed. Round r2 is declared and committed (`89a3f91`): the one C7 rule
made symmetric and tolerant of the LAN's bursts, one run per driver, d2–d6, and the
diagnostic reference run. The ledger got "15:10" from expectation twice while the clock read
15:07; corrected before the commit, and logged in the process notes.

## 2026-09-26T15:50-07:00 — round r2 ran to d4, then the agent refused again; written up as blocked
The candidate passed 10 of 10 under the r2 rule; the reference failed C6 and C7 a third time.
d2 (an even ERXRDPT) failed nothing in a full run on this B7 part: one observation, not a
verdict on the erratum. d3 failed C4b and only C4b. d4 failed C2 and C3 as declared and four
more checks on polling-only throughput; its rows are on the fixture. At 15:46 the SSH agent
refused to sign again, with d5, d6 and the diagnostic run still queued; the orchestrator's rule
for that case is to stop, so the results are written up with the pending cells marked, the
reviewer is launched on the local artifacts, and the unit reports blocked. In analysis one
harness field turned out to be a cumulative count rather than a delta (no verdict uses it),
and one shared condition surfaced: the whole-run capture keeps the DUT promiscuous, so both
drivers accepted the LAN's background traffic, which is where the idle-window overflows came
from.

## 2026-09-26T16:07-07:00 — the review: thirteen findings, three corrections before the checkpoint
The reviewer read the harness against every stored artifact. The three that changed the
text: d1's "three" reset messages were the summary's truncation of 433; the C6 reading had
blamed the PKTIF erratum and credited the candidate's poll for a 1.2 ms answer, both
contradicted by the candidate itself taking packet interrupts on the same part, so the cause
is now open pending the diagnostic run; and the r2 rule was "symmetric" only in name. Two
findings add evidence: d1's C7 PASS is spurious (the overflow term sums four counters), and
the reference books hundreds of transmit errors with zero transmit packets after the flood
while its transfer completes, the pattern R-02 predicts. The p1 harness, overwritten by the
r2 patch, was reconstructed by reversing it and hash-verified. Two ledger stamps were again
written from expectation and corrected against the clock in the writing command.
