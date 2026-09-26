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
- **Planted defect** — a deliberate edit to a disposable copy of the candidate, used to show
  that a check can fail (a *negative control*).

See the [glossary](../GLOSSARY.md), the [plan](../IMPLEMENTATION-PLAN.md) (L01, second
unit) and the [first unit](L01.md).

## Status

**In progress.** This file is written in two parts: the declaration below was committed
before the primary runs; the results follow it.

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

The DUT interface is moved into a network namespace (`10.99.0.2/24`); the peer is a macvlan
on the built-in Ethernet in a second namespace (`10.99.0.1/24`), so every DUT frame goes to
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

## Results

*(filled in after the runs)*
