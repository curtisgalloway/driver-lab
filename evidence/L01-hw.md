<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# L01 second unit: test real behavior on hardware

## Terms

- **Candidate** — the ENC28J60 driver written from the spec in the first unit, unchanged since
  its repair round 1 (`enc28j60_l01`).
- **Reference driver** — the upstream Linux v6.12 `enc28j60` driver, comparison evidence, not
  truth; the first unit's reference review recorded eight defects in it (R-01 to R-08).
- **DUT** — the device under test: the ENC28J60's network interface, driven by whichever
  driver is bound.
- **Peer** — the other end of every test conversation: a virtual interface on the fixture's
  built-in Ethernet, in its own network namespace, so DUT traffic crosses the switch.
- **Check** — one declared pass/fail question (C1–C9 below); a check *covers* a condition
  only when the run also records evidence that the condition occurred.
- **RSTP / BPDU** — the switch protocol that prevents Ethernet loops / its control frame,
  which advertises whether a port is forwarding ordinary traffic.
- **ARP** — the exchange that discovers an Ethernet neighbor before IPv4 traffic can flow.
- **Planted defect** — a deliberate edit to a disposable copy of the candidate, used to show
  that a check can fail (a *negative control*).

See the [glossary](../GLOSSARY.md), the [plan](../IMPLEMENTATION-PLAN.md) (L01, second
unit) and the [first unit](L01.md).

## Status

**Scoped L01 acceptance complete; L01c independent review pending.** The unchanged
candidate passed all ten r3 checks. All five original negative controls were caught across
p1/r2; r3 qualified the repaired checks with four controls, including removal with no
flood. Every declared job and capture is retained and the final fixture copy is verified.
The reference's immediate-reopen C6 failure is attributed to switch forwarding delay,
not an interrupt stall. No original-candidate failure or spec gap required a repair;
repair round 2 remains unused. Historical verdicts and superseded interpretations remain
visible below. The orchestrator reviews the code and artifacts before landing.

Private run ID: `enc28j60-l01-hw-20260926-01`, in the driver-porting run store: ledger, the
harness, module builds, every run's `result.json`, command log, kernel log and packet
captures, the planted-defect diffs and the reviewer's report.

## Fixture and identities

- **The Pi 4 fixture**: a Raspberry Pi 4 Model B Rev 1.5 running Raspberry Pi OS (Debian 13),
  kernel `6.18.50+rpt-rpi-v8` (Debian `1:6.18.50-1+rpt1`, 2026-09-11), booted from SD. The
  kernel image, the `enc28j60` device-tree overlay and the firmware are identified by hash
  in the ledger.
- **Board**: an ENC28J60 module on SPI0 chip select 0 at 12 MHz (the stock overlay's
  `spi-max-frequency`), interrupt on GPIO 25, falling edge. Silicon revision B7 (`EREVID`
  0x06), read at every probe by both drivers. Raw-SPI checks before this unit (register
  write and read back, the interrupt line asserting) were the orchestrator's setup, not
  evidence here.
- **Link partner**: the switch that also carries the fixture's built-in Ethernet; the
  ENC28J60 links at 10 Mb/s half duplex (both drivers default to half duplex; neither was
  reconfigured). The two ports are on the same VLAN: the peer reaches the DUT through the
  switch in every run.
- **In-tree driver blocked**: the distribution's `enc28j60` module is blacklisted and its
  `modprobe` install rule fails on purpose, so nothing binds `spi0.0` at boot; each run binds
  exactly one driver by `insmod` of a build from this unit and checks the driver symlink.
- **Builds**: both drivers built out of tree on the fixture against its installed 6.18
  headers (user decision, 2026-09-26), `W=1`, zero warnings each, **no source change for
  either**. Reference source = the v6.12 files pinned in the first unit; candidate source
  SHA-256 `70c5fbbd…` (the first unit's repair-1 build). Modules: reference `b2302dcd…`,
  candidate `85062ec8…`; vermagic `6.18.50+rpt-rpi-v8 SMP preempt mod_unload modversions
  aarch64`.
- **Harness** (frozen 2026-09-26 14:34 PDT, before any primary run): `l01hw.py`
  `cb42e46b…`, `rawframe.py` `d267ae51…`, `blob.py` `93509dad…`; planted-defect generator
  `make_mutants.py` `c1c976c8…`.
- **Reset between runs**: `rmmod`; the next `insmod`'s probe performs the chip's soft reset
  and reads the revision (the candidate first clears power-save, per errata issue 19; the
  reference does not, R-04). When a reference run's `rmmod` hangs (see results), the fixture
  is rebooted before the next run.

## Test design

The DUT interface is moved into a network namespace (on a dedicated test subnet); the peer is a macvlan
on the built-in Ethernet in a second namespace (on that test subnet), so every DUT frame goes to
the switch and back. Control traffic stays on the built-in interface, whose configuration is
untouched. Captures run on both ends for the whole run and at full size during the traffic
check. Exact frame sizes use raw sockets at both ends (an experimental ethertype, a sequence
number, the declared length and a per-frame byte pattern, so the receiver verifies size and
content). Checksummed transfers use a seeded generator so both ends and the harness know
the expected MD5 without sharing a file.

## Declared checks

Declared 2026-09-26 14:36 PDT, after four harness-development runs (two on the reference,
one on the candidate, one that ended in a reference `rmmod` hang) and before any primary
run. Each primary run executes C1–C9 in order; **two primary runs per driver, interleaved**
(reference, candidate, reference, candidate). Planted defects run once each afterward.

| Check | What it does | Passes when | Evidence that the condition occurred |
| --- | --- | --- | --- |
| C1 probe | `insmod`, then the netdev appears under `spi0.0` | driver symlink names the module under test; exactly one `enc28j60*` module loaded; netdev registered | kernel log probe lines; module list |
| C2 open and link | `ip link set up`, wait for carrier | carrier within 10 s; ≥ 1 interrupt on the GPIO 25 edge line during it; ethtool reports 10 Mb/s half duplex | carrier time; interrupt-count delta; ethtool text |
| C3 bidirectional traffic | 20 pings each way; iperf3 TCP 10 s each way; 1 MiB checksummed transfer each way | 20 of 20 replies each way; > 1 Mb/s each way; both MD5s match; interrupts fired; no receive error beyond ring overflow, no CRC/length/frame error, no TX error | ping RTTs; iperf3 rates and retransmits; captures on both ends (frame counts, max length); counters |
| C4a sizes, DUT transmits | raw frames of 18, 46, 59, 60, 61, 64, 65, 100, 256, 512, 1000, 1499, 1500, 1513, 1514 bytes | every frame arrives at the peer once at max(60, L) with the pattern intact | per-frame table with sent and delivered lengths |
| C4b sizes, DUT receives | the same lengths from the peer | every frame delivered once at max(60, L) + 4 for the reference (it passes the FCS up, R-03) or + 0 for the candidate, pattern intact | per-frame table |
| C5 receive-buffer wrap | 4 MiB checksummed transfer each way | both MD5s match; no receive error beyond overflow, no CRC/length/frame error, no TX error, no driver log line; received bytes ≥ 2 × ring size; under 240 s | rx_bytes ÷ ring size = the least number of write-pointer traversals (ring 6.5 KiB reference, 6 KiB candidate); planted defect d1 shows the wrap path is exercised |
| C6 repeated stop/start | 20 × (down, up, wait for carrier, 3 pings) | every cycle: carrier drops, returns within 10 s, 3 of 3 pings answered | per-cycle carrier times, ping counts, DUT rx/tx packet counts during the pings |
| C7 overflow and recovery | iperf3 UDP at 30 Mb/s for 5 s onto the 10 Mb/s link, then 10 pings and a 1 MiB transfer | the DUT's overflow counters rose during the flood (rx_over_errors on the candidate; rx_dropped on the reference, which shares that counter with unhandled-protocol frames); rx_errors and rx_over_errors do not move in a 3 s idle window after; 10 of 10 pings; MD5 matches | flood loss reported by iperf3; counter deltas in three windows |
| C8 removal under traffic | `rmmod` while the peer floods the DUT with pings | rmmod exits 0 within 10 s; the driver is gone; no kernel warning | rmmod time; the hung process's kernel stack when it hangs |
| C9 kernel log | the whole run's log | no BUG/WARNING/Oops/call trace; no `tx timeout` (reference) or `I/O or engine failure` (candidate) | the log |

Ring overflows during TCP are allowed in C3 and C5 and recorded: on this fixture the sender
sits on a gigabit port and the 6.5 KiB ring overflows as a matter of course; TCP retransmits.
The candidate books an overflow as `rx_errors` + `rx_over_errors`, the reference as
`rx_dropped`; the checks judge `rx_errors − rx_over_errors`. `rx_dropped` is not judged in
idle windows: the switch's spanning-tree hellos (every 2 s) and other unhandled multicast
raise it in both drivers. Both rules were set after the development runs and before the
primary runs; the development results are kept in the ledger.

**Expected results, reference** (from the development runs, which the primary runs test for
repeatability): C1, C2, C3, C4a, C4b, C5 pass (C4b with + 4 bytes; C3 with a peer-to-DUT ping
RTT far above the DUT-to-peer one, 158 ms average against 1 ms in development, recorded);
**C6 expected to fail** (0 of 3 pings after every reopen in development, carrier back in
2 s); C7 uncertain (in development the post-flood transfer arrived 1,224 bytes long); **C8
expected to hang** (`rmmod` waited in `free_irq` for a threaded handler that never returned);
C9 pass.

**Expected results, candidate**: C1–C9 pass (the development run passed all but the two
criteria revised above).

**Planted defects** (disposable copies of the candidate, one edit each, diffs in the run
store), each run once through the full sequence; a defect counts as *caught* only when the
named check fails for the stated reason:

| Defect | Edit | Must fail |
| --- | --- | --- |
| d1 wrap pointer rejected | a wrapped next-packet pointer is treated as corruption (reset) | C5, on receive errors beyond overflow and driver reset messages; C3 and C9 as consequences |
| d2 ERXRDPT even | the read pointer is written as the next pointer itself (erratum 14 violated) | an experiment: whichever check fails, if any, is the finding; not counted as a control |
| d3 FCS kept | the 4 FCS bytes are delivered as payload | C4b (every delivered length + 4); C3 and C5 expected to pass |
| d4 no INTIE | the interrupt enable is never set; the driver only polls | C2 (interrupt delta 0 while carrier still arrives); C3 on its interrupt delta |
| d5 ETXND short | every transmitted frame one byte short | C4a; C3 (truncated replies) |
| d6 RXERIF not cleared | the overflow flag is never acknowledged | C7 (counters keep moving in the idle window) |

### Round r2, declared after round p1 (2026-09-26 15:07 PDT)

Round p1 ran the four primary runs and defect d1 (results below). Its C7 settle rule
(`rx_over_errors` must not move at all in the 3 s idle window) failed the candidate's second
run for a reason that is not the driver's: the LAN's own multicast arrives at wire speed and
overflowed the 6 KiB ring twice in that window while 55 multicast frames came in, with the
pings 10 of 10 and the transfer intact. The reference's overflow counter (`rx_dropped`) was
never judged, so the rule was also asymmetric. **r2 rule, both drivers, C7 only:** in the idle
window, `rx_errors` beyond `rx_over_errors` is 0 and `rx_over_errors` is at most 5. Defect d6
is the control for it: a never-acknowledged RXERIF books one overflow per service pass, tens
per 3 s. Every other rule is unchanged; p1's verdicts stand as recorded. r2 adds one run per
driver under the new rule (harness `19840f97…`), the five remaining defects (d2–d6, one run
each), and a diagnostic run of the reference with its own debug messages on (C6, C7, C8
only; not a primary run; it exists to attribute the reference's C6 and C7 failures).

## Results (p1/r2 history)

### Verdicts

Round p1 (harness `cb42e46b…`, 2026-09-26 14:36–14:58 PDT) and round r2 (harness
`19840f97…`, 15:26–15:46 PDT). Reference and candidate ran interleaved; the fixture was not
rebooted between any two of these runs (the reboot after d1 was a runner misreading, see
the ledger, and never happened).

| Check | ref p1-1 | cand p1-1 | ref p1-2 | cand p1-2 | ref r2-1 | cand r2-1 | d1 | d2 | d3 | d4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 probe | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| C2 open, link, interrupt | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **FAIL** |
| C3 traffic | PASS | PASS | PASS | PASS | PASS | PASS | **FAIL** | PASS | PASS | **FAIL** |
| C4a sizes, transmit | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **FAIL** |
| C4b sizes, receive | PASS | PASS | PASS | PASS | PASS | PASS | **FAIL** | PASS | **FAIL** | PASS |
| C5 wrap | PASS | PASS | PASS | PASS | PASS | PASS | **FAIL** | PASS | PASS | **FAIL** |
| C6 stop/start | **FAIL** | PASS | **FAIL** | PASS | **FAIL** | PASS | PASS | PASS | PASS | **FAIL** |
| C7 overflow, recovery | **FAIL** | PASS | **FAIL** | FAIL¹ | **FAIL** | PASS | PASS² | PASS | PASS | **FAIL** |
| C8 rmmod under traffic | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| C9 kernel log | PASS | PASS | PASS | PASS | PASS | PASS | **FAIL** | PASS | PASS | PASS |

¹ cand p1-2's C7: pings 10 of 10 and the transfer intact; the flood raised `rx_over_errors`
by 18; the idle window then showed 2 more overflows while 55 multicast frames arrived from
the LAN at wire speed. That is the p1 rule's zero tolerance, revised for r2 (at most 5); the
verdict stands as recorded under the rule it ran under. The r2 candidate run passed C7 with
the same evidence shape.

² d1's C7 PASS is spurious (review R1): the check's "overflow occurred" term sums four
receive counters, and here the one that moved was `rx_errors` 1 from the planted defect's
own wrap fault, with `rx_over_errors` 0, only 63 frames received in the flood window, no
iperf3 server report, and the post-flood 1 MiB taking 68 s. The term is not specific; a
declared next round should judge `rx_over_errors` for the candidate. The candidate's own
C7 passes are not affected (their `rx_over_errors` were 18–30).

At the L01b checkpoint, the r2 verdicts (ref r2-1, cand r2-1, d2, d3, d4) were read
from the runner's log. L01c retrieved and verified their JSON, logs, and captures and
confirmed every verdict. **Every
number below is from the two p1 runs per driver and d1, whose artifacts are in the store;
"three runs" claims are verdict-level only** (review R4).

### The candidate

The same verdicts in three p1/r2 runs; the numbers are p1's two. Carrier 0.1 s after `up` (it never parks the chip in
power-save, so the PHY link survives a `down`); 5 interrupts during the open. Pings 1.0–1.25
ms average in both directions from the first request. TCP 4.08–4.09 Mb/s peer to DUT and
2.94 Mb/s DUT to peer over the 10 Mb/s half-duplex link, 1 MiB and 4 MiB intact each way by
MD5 (4 MiB received in 4.5 s, sent in 9.0 s). Every frame size from 18 to 1514 bytes
transmitted and received once with its content intact: frames under 60 bytes padded to 60 by
the chip with zero padding, delivered lengths equal to the wire length (the FCS stripped).
The 4 MiB receive drove at least 733–740 traversals of the 6 KiB ring (rx_bytes ÷ ring),
with 14–17 ring overflows booked as `rx_over_errors` and no other receive error, and the
planted wrap defect d1 shows the wrap path is what that check exercises. 20 of 20 stop/start
cycles with carrier back in ≤ 0.13 s and 3 of 3 pings each. The UDP flood (11.8–11.9 Mb/s
offered, 32–48 % lost across the switch and the ring) raised `rx_over_errors` by 18–30, the
counters settled, and 10 of 10 pings and a 1 MiB transfer followed. `rmmod` under a ping
flood returned in 0.09–0.10 s. No driver message in the kernel log in any run. 1,427–1,485
collisions counted per traffic check: the half-duplex link's ordinary collisions, read from
the transmit status vector (the reference does not count them).

### The reference

C1–C5, C8 and C9 pass in all three runs (p1 numbers: the FCS delivered in every received
frame, 60-byte wire frames arriving as 64 and 1514 as 1518, R-03 now a hardware fact; the
4 MiB receive at 679–686 ring traversals). Two failures in all three runs, described from
p1's two:

- **C6.** Carrier returns 1.9–2.1 s after each `up` (the reference parks the chip in
  power-save on `down`, and the PHY re-links on the next open), and then **0 of 3 pings are
  answered in every one of p1's 40 cycles** (and r2's verdict says the same of its 20), with
the DUT counting one received frame per cycle
  against three requests plus ARP, while transmitting 4–5 frames of its own. The same
  mechanism shows in C3: the first ten peer-to-DUT pings of run p1-1 came back with RTTs of
  2053, 1854, 1651, … 223 ms — ten requests answered at one instant, two seconds after the
  open — and then 1.2 ms; run p1-2's first five: 1004, 804, 601, 398, 194 ms. Averages 571
  ms and 151 ms against 1.1–1.5 ms the other way. **Historical reading, withdrawn by L01c below:** the reference services its
  receive ring only from its interrupt thread, and after an open that thread is not being
  run by received frames; it runs when something else happens (a transmit completion, a
  link change), which TCP supplies continuously and an idle link does not. **The cause is
  open** (review R3 corrected an earlier draft that blamed the errata's PKTIF issue: the
  candidate enables the same packet interrupt on the same part and is woken by received
  frames at once, its 0.7–1.4 ms RTTs being interrupt latency, not its 100 ms poll, so
  "the pin is not driven for packets" is contradicted by the candidate's own data). At that checkpoint the diagnostic had not run. The initial attribution excluded the
  fixture; the retrieved captures contradict that exclusion. See L01c's C6 attribution
  below, which supersedes this interpretation.
- **C7.** Recovery passed every time (10 of 10 pings, 1 MiB intact) but **the reference's
  counters never moved during the flood** (41–55 % of the datagrams lost, `rx_dropped`,
  `rx_errors`, `rx_over_errors` all 0), so the check's "the condition occurred" term is
  unmet. Attribution: the reference's accounting. It books an overrun only when the ring's
  free space is zero at the moment its handler runs. The earlier explanation also invoked
  delayed interrupt service; L01c withdraws that inference. UDP loss does not locate the
  drop inside the chip. Overflow is demonstrated for the candidate by its dedicated
  counter; it remains unproven for the reference despite the offered rate and losses.
- **`rmmod` hang, once in four attempts** (development run 3, not a primary run): `rmmod`
  under the ping flood blocked in `free_irq` → `__synchronize_irq`, waiting for the threaded
  handler to return; the task stayed in D state and the fixture needed a reboot, which the
  hung task delayed by several minutes. In the three primary runs the same `rmmod` returned
  in 0.09 s. The stack is in the run store. The handler's loop keeps going while any
  interrupt cause is pending; what kept one pending after close is not established.

- **Transmit accounting after the flood (review R6, unreported before it).** In both p1
  reference runs the flood window booked `tx_errors` 16 and 15 against 11 and 10
  `tx_packets`, and the post-flood 1 MiB window booked **433 and 431 transmit errors with 0
  transmit packets** while the transfer completed in 1.13 s, so every ACK the DUT sent was
  counted as an error and not as a packet. Absent in the development run without a flood
  before it; the candidate's figures are 0–2 errors and 432–446 packets. Consistent with
  R-02 (the reference never clears `ESTAT.TXABRT`, so once an abort has happened every
  later completion reads as one); the causal chain is source review, the counter pattern
  is hardware. No rule judged it; it belongs in a declared next round.

Neither failure demonstrates a candidate spec gap. C6 reflects fixture forwarding state;
C7 lacks specific reference overflow evidence. The first unit's source-review requirements
remain separate evidence and are not proved by these two reference failures.

### Planted defects (negative controls)

| Defect | Declared to fail | Result | Caught as declared? |
| --- | --- | --- | --- |
| d1 wrap pointer rejected | C5 (C3, C9 as consequences) | C3 (TCP 0 Mb/s peer to DUT, rx_errors 83 with 83 driver log lines, the 1 MiB receive corrupt), C4b (two frames lost to a reset), C5 (the 4 MiB receive stalled to the harness's 240 s limit), C9 (433 "I/O or engine failure -5; resetting" lines over the run; an earlier draft said three, the summary's truncation, review R2); 166 carrier changes over the run | **Yes.** A defect that only fires on a wrapped next-packet pointer failed the wrap check and the traffic check, which is also the evidence that wraps occur in a 1 MiB transfer. C5 failed by stall rather than by its counter rule; the counter and message evidence is in C3 and C9. |
| d2 ERXRDPT even (erratum 14) | an experiment | no check failed | Experiment result: on this B7 part, one full run with an even read pointer (about 700 ring traversals, 20 stop/start cycles, a flood) showed nothing. One run; it does not say the erratum is harmless, only that these checks did not see it. Not counted as a control. |
| d3 FCS kept | C4b only | C4b only; L01c verified all 15 delivered lengths equal max(60, L) + 4 | **Yes**, specific to the declared length defect. |
| d4 no INTIE | C2 (C3 on its interrupt term) | C2, C3, C4a, C5 (timeout), C6, C7; retrieved artifacts confirm zero interrupts in C2 and C3 and missing 65/256/1000/1499-byte C4a frames | **Yes** for C2 and C3; the other failures are consequences of the planted polling-only defect. |
| d5 ETXND short | C4a, C3 | C4a rejects 14/15 cases: padding hides the 18-byte case, other short frames have damaged content, frames above 60 bytes arrive one byte short; C3/C7 time out, C5 cannot connect, C6 answers no pings | **Yes**, C4a proves the named truncation; C3 is a consequential timeout. |
| d6 RXERIF not cleared | C7 (the r2 rule's control) | C7 only: 29,928 overflows during flood and 48,253 during the idle window; recovery pings and transfer intact | **Yes**, the idle-counter bound fails decisively. |

### Requirement-to-evidence table

Areas follow the first unit's requirement ledger facets (124 critical and important rows,
all `implemented` by source review B). Hardware evidence here is for the candidate unless
stated; "source-reviewed" means the first unit's reviews A and B and nothing on hardware.

| Area | Status | Evidence |
| --- | --- | --- |
| Register map, bank switching, MAC/MII dummy byte (REG) | tested indirectly | every check drives the map; the revision read at every probe (C1), the MAC address programmed and answering (C3), PHY reads deciding carrier (C2, C6) |
| Reset and initialization: wake before SRC, CLKRDY, MAC/PHY configuration (INIT) | tested | C1 (probe after every preceding driver's state, including the reference leaving the chip in power-save), C2 (carrier), C4a (hardware padding to 60 with zeros and CRC generation, since the peer's NIC accepted every frame) |
| Transmit: control byte, ETXST/ETXND, TSV, one packet in flight (TX) | tested | C4a 15 sizes, C3/C5 TCP, 1,400+ ordinary collisions counted per run; d5 detects truncation |
| Late-collision retransmit bound (TX-010, S-02, L5) | untested | no late collision occurred (switch link, no hub); the 17-attempt bound and the 2 s deadline are source-reviewed only |
| Receive: next-packet pointer, slot check, FCS strip, odd ERXRDPT, PKTDEC (RX) | tested | C4b 15 sizes at exact lengths, C5 ≥ 733 ring traversals intact; d1 shows the wrap path fails when broken; d3 shows the length rule is checked; d2's even ERXRDPT unobservable in one run |
| Receive overflow (RXERIF) | tested | C7: `rx_over_errors` 18–30 per flood, counters settle, recovery; d6 detects an unacknowledged overflow flag |
| Corrupt next-pointer recovery (§11.5, B-08) | exercised, not injected | d1 exercised the reset path 433 times without a kernel warning; receive traffic did not recover while the planted fault recurred; no real pointer corruption was injected |
| Interrupts: INTIE mask/unmask, sources, EPKTCNT over PKTIF (IRQ) | tested | C2 5 interrupts at open, ~8,000 per traffic check; d4 shows the interrupt term fails without INTIE; the reference's C6 is switch-forwarding evidence, not evidence against PKTIF |
| PHY and link: LSTAT, PHIR acknowledge, PHIE (PHY) | tested | C2, C6 (carrier return and replies; administrative carrier-down is not driver evidence) |
| Open/stop, queue discipline, removal (NET) | tested | C6, C8 (0.1 s under flood), C9 |
| TX timeout (watchdog) | untested | never triggered; the path is source-reviewed only |
| Receive filters: unicast, broadcast, multicast, promiscuous (FILT) | tested incidentally | ARP (broadcast) and IPv6 ND/MLD (multicast) worked in every run; the DUT was promiscuous throughout (the capture sets it), so the "normal" filter was in force only in C1–C2; no dedicated check |
| Device-tree binding, optional `spi-max-frequency`, SPI mode (F-01, F-02) | tested | C1 binds on the stock overlay (12 MHz, mode 0) |
| SPI timing: CS delays, effective clock, B1/B4 8 MHz rule (S-01, L1–L4) | unobservable here | B7 silicon at 12 MHz; no analyzer on the bus; the delays are source-reviewed |
| Full duplex, duplex change while up | untested | half duplex only (the switch's fixed 10 Mb/s half duplex); `ethtool -s` not exercised |
| Wake-on-LAN, power-down, DMA checksum, BIST, electrical | out of scope | first unit's scope decision |

### Same configuration

Same harness, same commands, same namespace layout, same LAN, interleaved runs minutes
apart, no module parameters for either driver. One shared condition to know: the DUT
interface is promiscuous from C2 on (the whole-run capture), so both drivers set the chip's
receive filter to accept everything and both received the LAN's background traffic;
`rx_otherhost` counts show it. The reference logs each filter change ("promiscuous mode");
the candidate is silent.

### Harness defects found in analysis and review

- C1's `irq_delta_during_load` is the interrupt line's cumulative count since boot, not a
  delta: before `insmod` the line has no handler name and the harness's pattern does not
  match it. No verdict uses the field; every within-run interrupt delta (C2, C3, C5, C6, C7)
  is a true delta.
- C7's "overflow occurred" term is a sum of four counters and not specific (R1, above).
- C6's "carrier drops on down" term cannot fail: the kernel clears LOWER_UP on an
  administrative down whatever the driver does (0.02–0.04 s in all 100 p1 cycles). The
  carrier-return and ping terms are the real ones (R9).
- C5's "under 240 s" clause never yields a verdict: the transfer's own timeout is also
  240 s, so a stall raises out of the check before its counters and log are recorded, as
  d1 showed (R10).
- C8 records nothing showing the ping flood was running at `rmmod` time, and the harness's
  attempt to stop that flood afterward fails (it cannot signal a process `sudo` started);
  the flood ends on its own count or 60 s deadline (R11).
- The p1 harness (`cb42e46b…`) was overwritten in the store by the r2 patch; reconstructed
  by reversing that patch, hash-verified, and kept as `harness/p1/l01hw.py` (R5).

None changes an original candidate verdict; R1 changes d1's C7 cell (above).
L01c applies the repairs in the separately declared r3 harness below.

### Decisions made in the user's place

- The peer is a macvlan on the built-in Ethernet inside a second namespace rather than the
  root namespace itself, so exact-size raw frames and IPv4 could be used from both ends; the
  built-in interface's own configuration is untouched. (Ledger, 14:10.)
- `ip netns exec` was used once by hand to read the hung `rmmod`'s kernel stack, a read-only
  diagnostic; the harness does the same when an unload hangs. (Ledger, 14:22.)
- NetworkManager's carrier probe of the new interface (it brings it up, activates nothing)
  was recorded and left alone. (Ledger.)
- The fixture was rebooted once (14:23) to clear the hung `rmmod`. (Ledger.)
- A new evidence file for this unit, rather than a section in `L01.md`: the first unit's
  file is a complete record of a different kind of work, and the plan's one-job rule keeps
  each file citable on its own.

### Review findings and resolutions

One independent reviewer (a fresh Claude Fable 5.1 subagent) read the harness, the planted
defects, every `result.json`, command log and kernel log in the store, the ledger and this
file, and checked the private files for infrastructure details; the report is
`review/artifact-review.md` in the run store. Thirteen findings, none requiring the review
swarm (no shared machinery or access control changed):

| Finding | Severity | Resolution |
| --- | --- | --- |
| R1 C7's overflow term not specific; d1's C7 PASS spurious | high | d1's historical cell footnoted; r3 judges the selected counter plus a receive-traffic floor; reference counter ambiguity remains explicit |
| R2 "three" reset messages for d1 was a truncation; TCP 0 Mb/s, receive timed out, 166 carrier changes | medium | corrected in the defect table |
| R3 the C6 reading blamed the PKTIF erratum and "1.2 ms from the poll", contradicted by the candidate's own packet interrupts | medium | L01c capture analysis attributes C6 to switch forwarding state after PHY power-down; prior interrupt-stall reading withdrawn |
| R4 "three runs" ranges rest on p1's two; r2 and d2–d4 are verdict lines | medium | p1 numbers remain scoped; L01c retrieved, hash-verified, and inspected r2 artifacts, confirming the logged verdicts |
| R5 the p1 harness not in the store | medium | reconstructed by reversing the r2 patch, hash `cb42e46b…` verified, stored |
| R6 reference transmit errors after the flood unreported | medium | added, tied to R-02 as consistent, for a declared next round |
| R7 the r2 rule called "symmetric" | medium | reworded: loosened for the candidate's accounting; the reference's overrun counter stays unjudged |
| R8 same configuration confirmed; criteria revisions supported | low | no change |
| R9 C6's carrier-drop term vacuous | low | r3 withdraws that coverage and judges carrier return plus replies |
| R10 C5's time clause never reached | low | r3 converts timeout into failure data and retains counters/logs under a shared deadline |
| R11 C8's flood not evidenced; its stop fails | low | r3 requires packet timestamps overlapping removal and explicitly terminates its ping |
| R12 three ledger contradictions (d1's driver "left bound"; a reboot that never happened; "every probe logs the revision") | low | ledger corrected |
| R13 identities consistent; public files clean; the private harness and runner embed a user name, a host and a key path | low | they stay private; noted in the ledger |

The reviewer's verdict: p1's conclusions are supported by the artifacts as described; the
r2 statements and two of the three caught controls rest on verdict lines until the
artifacts are retrieved; R2, R3 and R7 needed correction before the checkpoint (done).

### Limits

- L01b's missing r2 artifacts and two unrun controls were resolved in L01c. The reference
  overflow evidence still depends on its nonspecific drop counter.
- Every check ran on one board, one switch, one silicon revision, at 12 MHz; nothing here
  speaks to B1/B4 parts, full duplex, hubs, or other SPI clocks.
- The reference's overflow condition is inferred, not counted (above).
- The operator wrote the harness and read the reference; a harness bias toward the
  candidate's accounting is possible and is what the independent review is for.

## L01c continuation

### Round r3 declaration

Declared 2026-09-26T16:58:43-07:00, before any r3 run. The original candidate and reference modules are
unchanged. One full reference run and one full candidate run, in that order; then one
run per control below. No silent retries; preserve every attempt and stop for transport
failure, a hung unload, or an attributable original-candidate failure.

- **C6 (R9):** judge carrier returning within 10 s and all three replies in each of
  20 cycles. Keep administrative carrier-down time as information only: the kernel
  clears LOWER_UP independently of the driver's shutdown. Physical shutdown remains
  source-reviewed, not established by that observation.
- **C5 (R10):** a shared 240 s budget covers both 4 MiB transfers. A transfer timeout
  becomes recorded failure data; collect counters and driver messages afterward. Skip
  the second direction only if the shared budget is exhausted, and record why. Stop
  only this run's transfer children. All original integrity/error/wrap terms remain.
- **C8 (R11):** retain the removal rule, require the ping process alive at removal,
  at least ten captured echo requests in the preceding second, at least one during
  the removal command, and positive DUT receive growth before removal. Retain the
  timestamped capture and ping output; explicitly stop the privileged ping afterward.
  Remove the 5,000-packet cap so a fast sender cannot finish before removal starts.
- **C7 (R1):** require positive `rx_over_errors` for the candidate or `rx_dropped`
  for the reference, plus at least 100 received frames during the flood. The reference
  counter still cannot distinguish overflow from other drops; a pass alone cannot
  establish reference overflow. Keep the r2 allowance of at most five idle overflows
  and no other receive error. Actually wait 3 s: r2's field said 3 s but its code slept
  2 s. The post-flood transmit counters remain diagnostic, not a new pass rule.
- C1–C4 and C9 otherwise retain their declared checks and expectations.

| Run | Checks beyond automatic C1/C2/C9 | Expected result and reason |
| --- | --- | --- |
| r3-ref-1 | full sequence | C6 fails as before; C7 likely fails its overflow evidence; other checks pass, C8 hang remains possible |
| r3-cand-1 | full sequence | all ten checks pass |
| m3-d1 | C5, C7 | C5 fails wrap corruption/stall with retained counters/log; C7 must reject an unrelated receive-error-only overflow claim |
| m3-d5 | C6 | C6 fails replies with shortened transmit frames; this qualifies its surviving traffic term |
| m3-d6 | C7 | C7 fails its idle-counter bound with RXERIF unacknowledged |
| h3-no-flood | C8 | original candidate with a harness copy replacing only the ping command with `true`; C8 must fail traffic evidence even if unload succeeds |
| diag-r3-ref-debug10 | C6 | reference C6 still expected to fail; verbosity 10 enables interrupt messages, unlike r2's out-of-range value |

Five private harness regression tests exercise timeout retention, C6's surviving
terms, C7's unrelated-error rejection, and C8's packet overlap. The harness and its
control remain private; the following hashes freeze the executable inputs.

- `harness/r3/l01hw.py`: `cf16e0dd75779d593efaf7cae99e6d6ae6c69282ac4fafb2e62d1128727e7a0d`
- `harness/r3/rawframe.py`: `d267ae51cc255f1bb5c124004e4dd652b8da8cea11cfa43c869edd6751c7cfea`
- `harness/r3/blob.py`: `93509dad10ed61b218af9dd3942a4030a87e478e79834d04f45a6e942396b673`
- `harness/r3/test_l01hw.py`: `52d449cec53e6a249d224c7d5787bbbfd8729f8c3da523deb99cb8c177b16b56`
- `harness/r3/no-flood/l01hw.py`: `e963e437951eb4e12cf7b87ddbc46be4e490049a8a44e0ad6051c0815c5f7d54`

### L01c decisions

- Keep the harness and tests in the private run store, anchored by hashes in git, because they embed fixture configuration.
- Use the surviving C6 terms and explicitly withdraw carrier-drop coverage, because administrative down cannot prove driver shutdown.
- Use one shared C5 deadline and record an unattempted second direction on exhaustion, because the declared limit applies to the whole check.
- Require C8 packet overlap and remove its packet-count cap, because a launched process does not prove traffic during removal.
- Fix R1 along with R9–R11 and require 100 received frames, because the review demonstrated a false positive from one unrelated error and only 63 received frames.
- Correct the C7 wait to 3 s while retaining r2 verdicts, because the existing code did not implement the declared duration.
- Run each r3 job once and restrict controls to the affected checks, because the earlier full runs already cover their other effects.
- Keep post-flood transmit counters diagnostic, because changing that acceptance rule is unnecessary to qualify these repairs.
- Leave unrelated cleanroom-tooling test failures outside this unit, because no corresponding source changed; record the validation limit.
- Add one separately declared `debug=10` C6 diagnostic, because the driver interprets debug as a bit count and `0x2fe` silently selects default logging.
- Save local commits in a separate writable checkout and provide a bundle, because the supplied worktree's shared Git metadata is read-only.
- Preserve and recopy the changing d5 capture after stopping its orphaned writer, because a size/hash mismatch cannot be accepted as a verified transfer.
- Attribute C6 to fixture forwarding state, because paired captures show the DUT-side port withholding traffic while the peer-side port forwards.
- Mark scoped L01 acceptance complete while leaving review pending, because the acceptance criteria are met and review is the orchestrator's next gate.

Declaration amended 2026-09-26T17:02:01-07:00, still before any r3 run: add the verbosity-10 diagnostic after the six listed jobs.

### Completed r2 and C6 attribution

All remaining declared jobs ran once after the explicitly void interrupted d5 attempt.
The completed r2 fixture copy comprises 134 files, including every capture; its size and
SHA-256 comparisons had no mismatches. An initial copy differed in d5's C3 peer capture:
a C3 exception had bypassed capture cleanup, leaving its writer alive. Both transfer
attempts and manifests are retained; the writer was stopped before the verified recopy.
This is a harness artifact-lifetime failure, separate from the planted transmit defect.

The original diagnostic reproduced 0/20 good C6 cycles, carrier returning in 1.97–2.07 s,
and C7's missing overflow evidence; C8 and C9 passed. Its `debug=0x2fe` did **not** enable
interrupt messages: the reference passes it to `netif_msg_init`, which interprets the
value as a count of low bits and substitutes defaults for values at least 32. The
separately declared verbosity-10 run tests the intended diagnostic without rewriting r2.

**C6 attribution: fixture forwarding delay after the reference powers down the link.**
During the diagnostic's C6 window, the peer capture contains 60 outgoing ARP requests;
none reaches the DUT capture. The DUT receives 20 spanning-tree control frames, all
advertising a designated port with neither Learning nor Forwarding set. The peer-side
port advertises Forwarding in all 50 of its control frames. Thus receiving and interrupt
service are not globally stalled, and the two switch ports are in different forwarding
states. After the final C6 cycle the DUT-side port begins advertising Learning/Forwarding
and ARP reaches the DUT, which replies. The reference's close routine powers down the
PHY; the candidate keeps the physical link up. This explains why identical administrative
commands expose the switch delay only with the reference. The earlier PKTIF/interrupt
interpretation is withdrawn, including its assertion that the fixture was excluded.

The captured flags describe the sending port's state; see the
[Cisco RSTP explanation](https://www.cisco.com/c/en/us/support/docs/lan-switching/spanning-tree-protocol/24062-146.html).
The attribution is an inference from the captures plus the reference's close behavior,
not a controlled switch-configuration experiment. No switch setting was changed. It
explains this failure immediately after reopening; it does not certify other reference behavior.

### L01c validation limits

The five new private harness regression tests pass. Repository checks pass for
os-investigator (7), board-expert (42), ENC28J60 (105), and e1000 (70); the author manifest
matches, the spec check passes with nine existing unverified-spec warnings, and the
portability scan reports zero findings. The cleanroom suite has 59 passes and two failures
in unchanged code: a temporary project resolves to an ancestor harness directory, moving
the event log outside the test's expected directory; and a sandbox smoke test where this
session cannot create a nested namespace. These remain visible validation limits for the
orchestrator; no unrelated tooling was changed.

### R3 primary results

The declaration was committed as `7f3c72b` before deployment or execution. The unchanged
candidate passed all ten checks. C5 transferred 4 MiB each way in 14.1 s with at least
732.1 receive-ring traversals and no unexplained receive error. C6 passed 20/20 cycles
with carrier returning within 0.10 s. C7 recorded 21 overflows during 3,480 received flood
frames, two in the real 3 s idle window, and intact recovery with no transmit error.
C8 removed the module in 0.10 s with 1,451 captured requests in the preceding second,
36 during removal, and 2,924 DUT receive packets before removal.

The reference passed nine checks; only C6 failed. Its C8 removal took 0.11 s with
1,494 requests in the preceding second and 37 during removal. Its C7 PASS arose from
one `rx_dropped` among 3,619 received flood frames. **This is not verified overflow:**
the reference shares that counter with unrelated drops. Its post-flood transfer again
completed while booking 441 transmit errors and zero transmit packets, consistent with
the previously reviewed abort-status accounting defect. The unchanged C7 rule records
that accounting but does not judge it. Neither observation is a candidate failure.

### R3 control results and failure attribution

| Run | Failed checks | Attribution and qualification |
| --- | --- | --- |
| m3-d1 | C5, C7, C9 | Planted wrap defect. C5 returns a normal FAIL at 240.4 s, preserving 959 unexplained receive errors and 959 driver messages; its second transfer is explicitly skipped after the shared deadline. C7 rejects zero overflow counts despite one unrelated receive error, 49 received flood frames, 10/10 recovery pings and an intact transfer. C9 retains all 1,207 reset messages. |
| m3-d5 | C6 | Planted transmit truncation. Carrier returns within 0.17 s, but no cycle passes its three-reply term; the surviving C6 check can fail. |
| m3-d6 | C7 | Planted missing overflow acknowledgement. The real 3 s idle window records 71,968 overflows, exceeding five; 23,272 occurred during 3,351 received flood frames. |
| h3-no-flood | C8 | Planted harness failure, not candidate behavior. Removal exits zero in 0.10 s; ping is not alive and both request counts are zero. Five background receive packets alone do not qualify traffic. |

No job was silently repeated. No original-candidate failure or spec gap was found, so
no repair brief was written and repair round 2 remains unused. Historical reference C7
failures are missing counter evidence from the reference's accounting; reference C6 is
attributed to the fixture's forwarding state. The development removal hang remains
reference behavior with its saved stack and no established internal cause. Historical
C3/C7 exceptions on d5 are triggered by its planted transmit defect; the lost capture
cleanup is separately attributed to the harness. The first artifact-copy mismatch and
unrelated local validation failures are also retained, not driver verdicts.

The representative controls now qualify receive wrap, frame lengths, interrupt activity,
transmit truncation, stop/start replies, overflow acknowledgement, and removal-traffic
evidence. The reference's nonspecific overflow counter and the unobservable or excluded
requirements in the requirement table remain limitations. Administrative carrier-down
alone is no longer claimed as shutdown evidence. The frozen harness still lacks an
exception-safe C3 capture lifetime; its affected d5 capture extends beyond C3 and must
be interpreted with the command timestamps, not as a C3-only time window.

### Final diagnostic, acceptance, and handoff

`diag-r3-ref-debug10` failed C6 only and unloaded normally. Its 535-line log includes
22 receive-interrupt entries, 22 link-interrupt entries, and 122 transmit-completion
entries. Receive entries report one queued packet at a time; the handler is demonstrably
active. This is consistent with the capture-based fixture attribution and contradicts
an assertion that no interrupt servicing occurs during C6.

The final transfer verified **186 remote files, 1,093,934,823 bytes**, by size and
SHA-256, with zero mismatches. The run store retains all failed, development, void, and
primary runs; both transfer attempts; the frozen p1/r2/r3 harnesses; the negative control;
regression tests; module identities; and the regenerated summary. The Pi 4 fixture has
no driver bound after the last run.

| L01 acceptance criterion | Disposition |
| --- | --- |
| Agreed candidate behavior checks pass | Met: r3 candidate 10/10; original module unchanged |
| Relevant critical source-review findings resolved | Met by the first unit's retained repair/reviews; no new candidate defect found |
| Representative negative controls fail as expected | Met: original five controls caught across p1/r2; four r3 controls qualify the repaired checks |
| Hardware/boot identities and unavailable coverage recorded | Met: identities retained per run; requirement table and limitations retained |
| Final driver/spec revisions and evidence retained | Met: unchanged pinned candidate/reference, original spec lineage, frozen harness hashes, complete verified artifacts |

This accepts only the documented candidate behavior on this fixture. It does not turn
reference drop counts into overflow proof, establish physical carrier shutdown from an
administrative flag, or close the explicitly untested requirements. Independent review
of L01c remains the orchestrator's next gate; no review was launched by this implementer.

The supplied worktree's Git metadata was read-only. Local checkpoint commits therefore
live on the same topic-branch name in a separate writable checkout, with a portable bundle
in the private run store. The original worktree retains the matching record edits but its
branch cannot be advanced by this session. Importing those commits is a handoff action,
not a missing fixture run. Nothing was pushed and no pull request was opened.
