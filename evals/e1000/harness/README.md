<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# e1000 QEMU harness

Runs a Linux e1000 driver against QEMU's emulated Intel 82540EM and records what happened, so
the reference driver and a candidate written from the spec can be compared
([design](../../../QEMU-DIFFERENTIAL.md), plan units L02d1 and L02d2).

## Terms

- **DUT** (device under test) — the guest whose emulated e1000 is driven by the module being
  tested.
- **Peer** — a second guest with a virtio-net card, the known-good end of the link.
- **Register trace** — QEMU's log of every guest read and write to the e1000's registers.
- **Scenario** — a named sequence of guest commands and checks. Its verdict is PASS, FAIL
  (a guest misbehaved, which a driver can cause) or ERROR (the harness or the host did).
- **Run directory** — one fresh directory per harness run holding everything it produced;
  `--out` must not exist yet.
- **Phase** — the guest command or host action (a link toggle, a wait) a register access
  happened during, found by time; "idle" when none was running (the driver's own timers).
- **Deferred check** — a check a scenario registers but the harness evaluates after QEMU
  exits, from the register trace or the packet captures.
- **Planted defect** — a deliberate bug in a disposable copy of the reference driver; the
  suite must fail on it.

See the [glossary](../../../GLOSSARY.md).

## What it does

`l02harness.py run` builds one initramfs (static busybox, [`guest-init.sh`](guest-init.sh), and
the given modules), boots the DUT and the peer as two `q35` guests joined by a
point-to-point datagram socket, and runs the scenarios in order. Each guest serves shell
commands over its second serial port, so a scenario runs on the host and can drive either
guest, and the DUT's QEMU monitor, between steps. The DUT loads no driver until a scenario
tells it to.

A run directory holds:

| File | Contents |
| --- | --- |
| `verdicts.json` | Overall verdict, per-scenario verdicts with each check, trace counts |
| `identities.json` | SHA-256 of the kernel, initramfs, busybox, modules, harness files and QEMU binary; QEMU version |
| `dut-regtrace.log` | e1000 MMIO, I/O-port and PCI-configuration accesses, and the model's `e1000*` events |
| `dut-regtrace.jsonl.gz` | The same, decoded: register name and value (I/O-window accesses resolved to the register IOADDR selected), with the scenario and phase each happened in |
| `trace-phases.json` | Per scenario, per phase: counts of each register read and write, the input for comparing two drivers phase by phase |
| `host-actions.jsonl` | The host's own steps (link toggles, waits) with their times |
| `dut-trace-raw.log.gz` | The unfiltered QEMU trace |
| `dut.pcap`, `peer.pcap` | Every frame on each side's link, from QEMU's `filter-dump` |
| `*-console.log`, `*-cmds.jsonl` | Each guest's kernel console; every scenario command with its output and host timestamps |
| `dut-dmesg-NN-<scenario>.txt` | The DUT's kernel log from scenario NN, taken after the driver is unloaded; `00-boot` is the boot log |
| `peer-dmesg.txt` | The peer's kernel log at the end of the run |
| `initramfs.cpio.gz`, `*-argv.json`, `*-qemu.log` | The guests' initramfs, each QEMU command line, and QEMU's own output |

After the scenarios, two pseudo-scenarios check the stored files:

- `trace` (when a suite scenario ran) checks the whole register trace against rules the
  manual states: at least 1 µs between a global reset (`CTRL.RST`) and the next register
  access; ring lengths nonzero multiples of 128 bytes; ring bases 16-byte aligned; tail
  writes inside the ring; head writes only while that direction is disabled; ITR's reserved
  bits clear. A reset returns lengths and enables to their power-on values. Its
  observations record which window carried each reset, the gaps, any ring base above
  4 GiB, and the ITR values written: facts L02f compares between drivers.
- `capture` (when `smoke` ran) checks that the trace holds e1000 reads, writes and EEPROM
  interface accesses (EECD or EERD) and, when `smoke` passed, that each packet capture holds
  its pings in both directions. The EEPROM check shows that the driver used the EEPROM, not
  that the MAC came from it.

Packet checks match frames by content, never by time: `filter-dump` timestamps are not on
the host clock the trace and command logs share.

Exit status: 0 every scenario passed; 1 a scenario FAILed; 2 bad arguments or inputs, a guest
that never booted (the DUT has no driver loaded then, so it cannot be the driver's fault), or
an exception in the harness (ERROR; the run stops there). A guest that stops answering, whose
command channel breaks, or whose QEMU exits FAILs its scenario and is not used again; the
harness kills any QEMU that does not power off. `verdicts.json` is written in every case
except a setup error found before the run directory exists, a failure to read the inputs or
write the run's own files (a full disk, for example), which also exits 2, or an interrupt
after the scenarios have finished.

## Scenarios

Every suite scenario loads the driver itself and unloads it at the end. After each one the harness
stops any background traffic, unloads the driver if a failed scenario left it loaded, and
checks the DUT's kernel log since the previous scenario: a warning, call trace, oops,
transmit hang, netdev watchdog timeout, interrupt storm, or DMA-API or allocation failure
FAILs the scenario. Ordinary driver messages (link up and down, probe banners) do not.

`--scenario all` runs the first ten, in this order: the design's §5 list plus
`link-loss-tx`, the probe for L02e's item L4, not in §5's order.

Every bring-up also checks that at most 4 unicast frames reached the DUT while it came up.
Nothing the DUT does then draws a unicast reply, so more means frames left over from an
earlier scenario, sent while the DUT could not receive. They can use up a stalled driver's
buffers and fail a scenario for an earlier one's fault; this check names that cause.

| Name | Checks |
| --- | --- |
| `smoke` | Module loads and binds; the interface's MAC matches the one QEMU was given; carrier within 15 s; three pings each way with no loss; `rmmod` succeeds |
| `frame-sizes` | Pings each way at 60, 61, 1513 and 1514-byte frames, and a 42-byte one the DUT must pad; afterwards, the peer's capture holds the DUT's requests and replies at each size and no DUT frame shorter than 60 bytes |
| `ring-wrap` | 1,500 back-to-back pings each way with no loss, 4 MiB over HTTP each way with matching MD5; afterwards, the trace shows both tails wrapping at least 3 times |
| `rx-overrun` | With the DUT's interrupts masked by the harness (`devmem` writes IMC, then restores IMS), the peer floods it; the receive head must reach the tail (the ring ran dry), and the trace must show the device accepting frames with no RDT write while masked; after the mask is restored, pings each way must succeed |
| `link-flap` | The link drops through QEMU's monitor: carrier falls within 10 s and pings fail; it returns: carrier within 15 s and pings succeed. Observes whether ICR reads after the drop showed the link-change cause |
| `link-loss-tx` | The link drops for 8 s while the DUT floods the peer (the trace must show it transmitting in the second before); carrier must fall; afterwards pings succeed. Observes TDH and TDT during the outage. QEMU's model keeps completing transmit descriptors with the link down, so transmits queued through an outage (L02e item L4) cannot be reproduced here |
| `stop-start` | 20 interface down/up cycles back to back, then carrier and pings |
| `down-during-traffic` | Floods both ways (the trace must show both tails moving in the second before), interface down, and only then the floods stopped; interface up, carrier, a fixed 3 s settling interval, then one set of pings each way (no retry). The trace must show the last RCTL write at least 1 s before those pings, so QEMU's receive hold (below) and the burst of frames it held had ended; the check's detail counts that burst |
| `reload` | Three load, ping, unload cycles |
| `itr` | ITR read through the memory BAR; afterwards, the read must equal the last value the trace shows written, or 0 after a reset. That checks the model and the decoder agree, not the driver; the values the driver wrote after its last reset are recorded for L02f |
| `selftest-hang` | Harness self-test. PASS when a guest command that never returns gets the DUT reported dead after its timeout; later scenarios in the run then FAIL |
| `selftest-panic` | Harness self-test. PASS when a guest kernel panic (SysRq crash) gets the DUT reported dead; later scenarios then FAIL |

Two link scenarios clear both guests' ARP entries after the link returns, recording them
first: pings sent during the outage leave the entry unresolved, and the next ping can be lost
waiting for it, which is the stack's doing, not the driver's. Floods are `ping -i 0.001`;
this busybox's `nc` has no UDP mode.

QEMU's model holds all reception for one second after every RCTL write, and releases the
frames that arrived meanwhile in one burst; the manual describes no such hold. Drivers rewrite
RCTL when the stack joins multicast groups at carrier-up, so a ping sent right after carrier
returns can fall inside it. `down-during-traffic` waits it out (plan unit L02f2b,
[evidence](../../../evidence/L02f2b.md)).

What QEMU's model does not show: when the receive ring is full it stops accepting frames
rather than dropping and counting them, so there is no missed-packet count or overrun cause
to check in emulation.

## Running it

On the test host (x86-64 Linux, KVM recommended, QEMU 10.2.1, a static busybox, Python 3.10+), with a
v6.12 kernel built with `CONFIG_E1000=m`, virtio-net, devtmpfs and initrd support:

```bash
python3 l02harness.py run --kernel obj/arch/x86/boot/bzImage \
  --module obj/drivers/net/ethernet/intel/e1000/e1000.ko --driver e1000 --out runs/r001
```

`--driver` names both the module to load and the PCI driver it must bind as; the candidate
is `--module .../e1000_l02.ko --driver e1000_l02`. `--scenario` repeats to choose and order
scenarios. `--accel` defaults to `auto`: KVM when `/dev/kvm` is usable, otherwise TCG with a
warning, since the scenarios' timeouts assume KVM speed. The choice is recorded in
`identities.json`. `--dut-mem` (default 3G) sets the DUT's memory; q35 maps memory above
2 GiB beyond the 4 GiB boundary, so the default makes memory above 4 GiB available to a
driver whose DMA mask allows it. The reference never placed a ring there.

A full suite run (`--scenario all`) takes a little over 2 minutes with KVM.

**Isolated runs for qualified evidence.** In one boot, a driver that stalls a flood leaves
frames queued at the peer that reach later scenarios. The checks were qualified (plan unit
L02d3, [evidence](../../../evidence/L02d3.md)) with each scenario in its own run, on fresh
guests; cite a result as qualified evidence only from such a run:

```bash
for s in smoke frame-sizes ring-wrap rx-overrun link-flap link-loss-tx stop-start \
    down-during-traffic reload itr; do
  python3 l02harness.py run --kernel ... --module ... --driver ... --scenario "$s" --out "runs/r001-$s"
done
```

The unit tests cover the parts that need no QEMU:
`python3 -m unittest discover -s tests -v`.
