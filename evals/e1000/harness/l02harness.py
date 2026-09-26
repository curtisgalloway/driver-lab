#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""QEMU harness for the L02 e1000 differential test.

Boots two guests on the test host from one kernel and one initramfs:

- the DUT, a q35 guest with an emulated e1000 (82540EM) whose driver module is loaded by
  a scenario, with every e1000 register access traced;
- the peer, a q35 guest with a virtio-net device, the known-good end of the link.

The guests share a point-to-point datagram socket network. Each runs guest-init.sh, which
serves shell commands over a second serial port, so scenarios run on the host and can drive
either guest and the QEMU monitor between steps. Everything a run produces lands in its run
directory: consoles, command logs, the raw and filtered register traces, a packet capture
per side, artifact identities, and verdicts.json.

Exit status: 0 every scenario passed; 1 a scenario failed (FAIL: a guest misbehaved,
which a driver can cause); 2 a usage, setup or harness error (ERROR: bad inputs, a
guest that never booted, or an exception in the harness itself).
Stdlib only; Python 3.10 or newer.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import datetime
import gzip
import hashlib
import io
import json
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
DUT_MAC = "52:54:00:12:34:56"
PEER_MAC = "52:54:00:12:34:57"
DUT_IP = "192.0.2.1"
PEER_IP = "192.0.2.2"
TRACE_EVENTS = (
    "memory_region_ops_read",
    "memory_region_ops_write",
    "pci_cfg_read",
    "pci_cfg_write",
    "e1000*",
)
E1000_REGIONS = ("'e1000-mmio'", "'e1000-io'")
# The trace logs absolute addresses; BAR0 is 128 KiB and naturally aligned, so an
# address modulo its size is the register offset. EECD (0x10) and EERD (0x14) are the
# two ways the 82540EM's EEPROM can be read.
E1000_BAR0_SIZE = 0x20000
EEPROM_REGS = (0x10, 0x14)
# The e1000's QEMU device id, for the monitor's set_link.
DUT_NIC_ID = "nic0"

# Register offsets and bits from the 8254x manual (SDM Table 13-2 and the register
# sections the spec cites). Only names the harness decodes or checks are listed.
REGS = {
    0x00000: "CTRL",
    0x00008: "STATUS",
    0x00010: "EECD",
    0x00014: "EERD",
    0x00018: "CTRL_EXT",
    0x00020: "MDIC",
    0x00028: "FCAL",
    0x0002C: "FCAH",
    0x00030: "FCT",
    0x00038: "VET",
    0x000C0: "ICR",
    0x000C4: "ITR",
    0x000C8: "ICS",
    0x000D0: "IMS",
    0x000D8: "IMC",
    0x00100: "RCTL",
    0x00170: "FCTTV",
    0x00400: "TCTL",
    0x00410: "TIPG",
    0x00458: "AIFS",
    0x00E00: "LEDCTL",
    0x01000: "PBA",
    0x02160: "FCRTL",
    0x02168: "FCRTH",
    0x02800: "RDBAL",
    0x02804: "RDBAH",
    0x02808: "RDLEN",
    0x02810: "RDH",
    0x02818: "RDT",
    0x02820: "RDTR",
    0x02828: "RXDCTL",
    0x0282C: "RADV",
    0x02C00: "RSRPD",
    0x03800: "TDBAL",
    0x03804: "TDBAH",
    0x03808: "TDLEN",
    0x03810: "TDH",
    0x03818: "TDT",
    0x03820: "TIDV",
    0x03828: "TXDCTL",
    0x0382C: "TADV",
    0x05000: "RXCSUM",
    0x05800: "WUC",
    0x05820: "MANC",
}
REG = {name: off for off, name in REGS.items()}
CTRL_RST = 1 << 26  # SDM 13.4.1
EN = 1 << 1  # RCTL.EN (SDM 13.4.22) and TCTL.EN (SDM 13.4.33)
ICR_LSC = 1 << 2  # SDM Table 13-63


class HarnessError(Exception):
    """A setup problem: the run cannot start or cannot be judged."""


class GuestError(Exception):
    """A guest stopped answering: timeout, closed channel, or QEMU exit."""


# (check name, passed, detail)
Check = tuple[str, bool, str]


# --- initramfs ------------------------------------------------------------------------


def cpio_newc(entries: list[tuple[str, int, bytes, int, int]]) -> bytes:
    """Returns a newc cpio archive of (name, mode, data, rdevmajor, rdevminor) entries.

    Every mtime, uid and gid is zero, so equal inputs give byte-identical archives.
    """
    out = io.BytesIO()

    def pad4(n: int) -> None:
        out.write(b"\0" * (-n % 4))

    for ino, (name, mode, data, rmaj, rmin) in enumerate(
        entries + [("TRAILER!!!", 0, b"", 0, 0)], start=1
    ):
        raw = name.encode() + b"\0"
        fields = (ino, mode, 0, 0, 1, 0, len(data), 0, 0, rmaj, rmin, len(raw), 0)
        header = b"070701" + b"".join(b"%08X" % f for f in fields)
        out.write(header + raw)
        pad4(len(header) + len(raw))
        out.write(data)
        pad4(len(data))
    return out.getvalue()


def build_initramfs(busybox: Path, modules: list[Path]) -> bytes:
    """Returns the gzip-compressed initramfs shared by both guests."""
    entries = []
    for d in ("bin", "dev", "lib", "lib/modules", "proc", "sys", "tmp"):
        entries.append((d, 0o040755, b"", 0, 0))
    entries.append(("dev/console", 0o020600, b"", 5, 1))
    entries.append(("init", 0o100755, (HERE / "guest-init.sh").read_bytes(), 0, 0))
    entries.append(("bin/busybox", 0o100755, busybox.read_bytes(), 0, 0))
    for m in modules:
        entries.append((f"lib/modules/{m.name}", 0o100644, m.read_bytes(), 0, 0))
    return gzip.compress(cpio_newc(entries), mtime=0)


# --- captures -------------------------------------------------------------------------


@dataclasses.dataclass
class Frame:
    ts: float
    data: bytes


def read_pcap(path: Path) -> list[Frame]:
    """Reads a classic little- or big-endian microsecond pcap file."""
    raw = path.read_bytes()
    if len(raw) < 24:
        return []
    magic = raw[:4]
    if magic == b"\xd4\xc3\xb2\xa1":
        end = "<"
    elif magic == b"\xa1\xb2\xc3\xd4":
        end = ">"
    else:
        raise HarnessError(f"{path}: not a pcap file")
    frames, off = [], 24
    while off + 16 <= len(raw):
        sec, usec, incl, _ = struct.unpack(end + "IIII", raw[off : off + 16])
        off += 16
        frames.append(Frame(sec + usec / 1e6, raw[off : off + incl]))
        off += incl
    return frames


def icmp_echoes(frames: list[Frame]) -> list[tuple[str, str, int, int]]:
    """Returns (src, dst, icmp type, frame length) for each IPv4 ICMP echo frame."""
    found = []
    for f in frames:
        d = f.data
        if len(d) < 14 + 20 + 8 or d[12:14] != b"\x08\x00" or d[23] != 1:
            continue
        # The DUT's frames come from the driver under test, so a header may lie.
        ihl = (d[14] & 0x0F) * 4
        if ihl < 20 or len(d) < 14 + ihl + 8:
            continue
        icmp_type = d[14 + ihl]
        if icmp_type in (0, 8):
            src = ".".join(str(b) for b in d[26:30])
            dst = ".".join(str(b) for b in d[30:34])
            found.append((src, dst, icmp_type, len(d)))
    return found


def empty_trace_counts() -> dict[str, int]:
    return {
        "mmio_read": 0,
        "mmio_write": 0,
        "eeprom": 0,
        "io": 0,
        "pci_cfg": 0,
        "model_event": 0,
    }


def filter_trace(raw_log: Path, out: Path) -> dict[str, int]:
    """Copies e1000 register accesses and e1000 model events to out; returns counts."""
    counts = empty_trace_counts()
    # QEMU 10.2.1 with -msg timestamp=on writes "<ISO time> <event> <args>"; other
    # builds of the log backend write "<pid>@<sec>.<usec>:<event> <args>" or no prefix.
    event = re.compile(r"^(?:\S+Z |\d+@\d+\.\d+:)?(\w+)(?: (\S+))?")
    addr = re.compile(r" addr 0x([0-9a-f]+) ")
    with raw_log.open(errors="replace") as src, out.open("w") as dst:
        for line in src:
            m = event.match(line)
            if not m:
                continue
            name = m.group(1)
            if name.startswith("memory_region_ops_"):
                if E1000_REGIONS[0] in line:
                    counts["mmio_read" if name.endswith("read") else "mmio_write"] += 1
                    a = addr.search(line)
                    if a and int(a.group(1), 16) % E1000_BAR0_SIZE in EEPROM_REGS:
                        counts["eeprom"] += 1
                elif E1000_REGIONS[1] in line:
                    counts["io"] += 1
                else:
                    continue
            elif name.startswith("pci_cfg_"):
                if m.group(2) != "e1000":
                    continue
                counts["pci_cfg"] += 1
            elif name.startswith("e1000"):
                counts["model_event"] += 1
            else:
                continue
            dst.write(line)
    return counts


# --- trace decoding -------------------------------------------------------------------


def reg_name(off: int) -> str:
    """Returns the manual's name for a register offset, or the offset in hex."""
    if off in REGS:
        return REGS[off]
    if 0x04000 <= off < 0x04200:
        return f"STAT+0x{off - 0x4000:03x}"
    if 0x05200 <= off < 0x05400:
        return f"MTA[{(off - 0x5200) // 4}]"
    if 0x05400 <= off < 0x05480:
        return f"RA{'L' if off % 8 == 0 else 'H'}[{(off - 0x5400) // 8}]"
    if 0x05600 <= off < 0x05800:
        return f"VFTA[{(off - 0x5600) // 4}]"
    return f"0x{off:05x}"


@dataclasses.dataclass
class Access:
    """One line of the filtered register trace, decoded.

    kind is "mmio" (memory BAR), "io" (a register reached through the I/O window's
    IODATA, with reg the offset last written to IOADDR), "io-addr" (IOADDR itself),
    "cfg" (PCI configuration space) or "event" (a QEMU e1000 model event, in text).
    """

    t: float | None
    kind: str
    rw: str
    reg: int | None
    value: int | None
    text: str = ""

    @property
    def name(self) -> str:
        if self.kind in ("mmio", "io"):
            return "?" if self.reg is None else reg_name(self.reg)
        if self.kind == "io-addr":
            return "IOADDR"
        if self.kind == "cfg":
            return f"cfg@0x{self.reg:02x}"
        return self.text.split(" ", 1)[0]

    @property
    def is_register(self) -> bool:
        return self.kind in ("mmio", "io", "io-addr")


_ISO_TIME = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z ")
_PID_TIME = re.compile(r"^\d+@(\d+\.\d+):")
_MR_LINE = re.compile(
    r"memory_region_ops_(read|write) .* addr 0x([0-9a-f]+) value 0x([0-9a-f]+)"
    r" size \d+ name '(e1000-mmio|e1000-io)'"
)
_CFG_LINE = re.compile(
    r"pci_cfg_(read|write) e1000 \S+ @0x([0-9a-f]+) (?:<-|->) 0x([0-9a-f]+)"
)
_EVENT_LINE = re.compile(r"(e1000\w*(?: .*)?)$")


def line_time(line: str) -> float | None:
    """Returns a trace line's host real time in seconds, when it carries one."""
    m = _ISO_TIME.match(line)
    if m:
        t = datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S.%f")
        return t.replace(tzinfo=datetime.timezone.utc).timestamp()
    m = _PID_TIME.match(line)
    return float(m.group(1)) if m else None


def decode_trace(lines) -> list[Access]:
    """Decodes filtered trace lines (see filter_trace) into Accesses, in file order."""
    out: list[Access] = []
    io_sel: int | None = None
    for line in lines:
        line = line.rstrip("\n")
        t = line_time(line)
        m = _MR_LINE.search(line)
        if m:
            rw = m.group(1)[0]
            addr, value = int(m.group(2), 16), int(m.group(3), 16)
            if m.group(4) == "e1000-mmio":
                out.append(Access(t, "mmio", rw, addr % E1000_BAR0_SIZE, value))
            elif addr & 0x7 == 0:
                if rw == "w":
                    io_sel = value
                out.append(Access(t, "io-addr", rw, None, value))
            else:
                out.append(Access(t, "io", rw, io_sel, value))
            continue
        m = _CFG_LINE.search(line)
        if m:
            reg, value = int(m.group(2), 16), int(m.group(3), 16)
            out.append(Access(t, "cfg", m.group(1)[0], reg, value))
            continue
        body = line.split(" ", 1)[1] if _ISO_TIME.match(line) else line
        body = body.split(":", 1)[1] if _PID_TIME.match(body) else body
        m = _EVENT_LINE.match(body)
        if m:
            out.append(Access(t, "event", "", None, None, m.group(1)))
    return out


@dataclasses.dataclass
class Window:
    start: float
    end: float
    label: str


class Timeline:
    """Non-overlapping, time-sorted windows; finds the one holding a time."""

    def __init__(self, windows: list[Window]):
        self.windows = sorted(windows, key=lambda w: w.start)
        self.starts = [w.start for w in self.windows]

    def find(self, t: float | None) -> Window | None:
        if t is None:
            return None
        i = bisect.bisect_right(self.starts, t) - 1
        if i >= 0 and t <= self.windows[i].end:
            return self.windows[i]
        return None


def command_windows(cmdlog: Path, who: str) -> list[Window]:
    """Returns one window per guest command in a *-cmds.jsonl file."""
    if not cmdlog.exists():
        return []
    out = []
    for line in cmdlog.read_text().splitlines():
        d = json.loads(line)
        out.append(Window(d["start"], d["end"], f"{who}#{d['seq']} {d['cmd']}"))
    return out


def label_accesses(
    accesses: list[Access],
    scenarios: list[Window],
    phases: list[list[Window]],
) -> list[tuple[str, str]]:
    """Returns (scenario, phase) for each access.

    The scenario is the window holding the access ("outside" if none). The phase is the
    first of the phases timelines (in priority order: DUT commands, peer commands, host
    actions) with a window holding it, or "idle": for example the driver's own timers
    between commands.
    """
    scen = Timeline(scenarios)
    lines = [Timeline(p) for p in phases]
    out = []
    for a in accesses:
        s = scen.find(a.t)
        phase = next((w.label for tl in lines if (w := tl.find(a.t))), "idle")
        out.append((s.label if s else "outside", phase))
    return out


def write_labeled_trace(
    accesses: list[Access], labels: list[tuple[str, str]], jsonl: Path, summary: Path
) -> None:
    """Writes one JSON line per access, gzipped, and per scenario the phases' counts."""
    per: dict[str, dict[str, dict]] = {}
    with gzip.open(jsonl, "wt") as f:
        for a, (scenario, phase) in zip(accesses, labels):
            row = {
                "t": a.t,
                "scenario": scenario,
                "phase": phase,
                "kind": a.kind,
                "rw": a.rw,
                "reg": None if a.reg is None else f"0x{a.reg:05x}",
                "name": a.name,
                "value": None if a.value is None else f"0x{a.value:x}",
            }
            if a.kind == "event":
                row["text"] = a.text
            f.write(json.dumps(row) + "\n")
            ph = per.setdefault(scenario, {}).setdefault(
                phase, {"phase": phase, "first": a.t, "ops": {}}
            )
            key = f"{a.rw} {a.name}".strip()
            ph["ops"][key] = ph["ops"].get(key, 0) + 1
    summary.write_text(
        json.dumps(
            {s: list(ph.values()) for s, ph in per.items()}, indent=1, sort_keys=False
        )
    )


def tail_wraps(accesses: list[Access], reg: int) -> int:
    """Counts how often the values written to a tail register go down: ring wraps.

    Only within one life of the ring: a global reset or a write to the ring's length
    register starts a new one, and writes of 0 are skipped, since drivers write the tail
    back to 0 when they clear or set up a ring. A genuine wrap through 0 is still counted
    at the next nonzero write.
    """
    length = REG["RDLEN"] if reg == REG["RDT"] else REG["TDLEN"]
    wraps, last = 0, None
    for a in accesses:
        if not a.is_register or a.rw != "w" or a.reg is None:
            continue
        if a.reg == length or (a.reg == REG["CTRL"] and a.value & CTRL_RST):
            last = None
        elif a.reg == reg and a.value:
            if last is not None and a.value < last:
                wraps += 1
            last = a.value
    return wraps


def trace_rules(accesses: list[Access]) -> tuple[list[Check], dict]:
    """Checks the whole register trace against rules the manual states.

    Returns the checks and observations for L02f (reset path, gaps, ring geometry,
    addresses above 4 GB, ITR values).
    """
    regs = [a for a in accesses if a.is_register]
    resets = {"mmio": 0, "io": 0}
    gaps: list[int] = []
    bad: dict[str, list[str]] = {
        k: [] for k in ("gap", "len", "base", "tail", "head", "itr")
    }
    ring_len = {"RDLEN": 0, "TDLEN": 0}
    enabled = {"RCTL": False, "TCTL": False}
    high_bases: set[str] = set()
    itr_values: list[int] = []

    def at(a: Access) -> str:
        return f"{a.name}={a.value:#x} at {a.t}"

    for i, a in enumerate(regs):
        if a.rw != "w" or a.kind == "io-addr" or a.reg is None:
            continue
        name, v = reg_name(a.reg), a.value
        if name == "CTRL" and v & CTRL_RST:
            resets[a.kind] += 1
            nxt = regs[i + 1] if i + 1 < len(regs) else None
            if nxt and a.t is not None and nxt.t is not None:
                # The trace has microsecond resolution; rounding undoes the float
                # error of subtracting two epoch times (about 0.24 us at this size).
                gap = round((nxt.t - a.t) * 1e6)
                gaps.append(gap)
                if gap < 1:
                    bad["gap"].append(f"{gap} us before {nxt.name} at {nxt.t}")
            # A global reset returns the receive and transmit registers to power-on
            # values (SDM 14.7): lengths 0, EN clear.
            ring_len = {"RDLEN": 0, "TDLEN": 0}
            enabled = {"RCTL": False, "TCTL": False}
        elif name in ring_len:
            ring_len[name] = v
            if v == 0 or v & 0x7F or v > 0xFFF80:
                bad["len"].append(at(a))
        elif name in ("RDBAL", "TDBAL"):
            if v & 0xF:
                bad["base"].append(at(a))
        elif name in ("RDBAH", "TDBAH"):
            if v:
                high_bases.add(f"{name}={v:#x}")
        elif name in ("RDT", "TDT"):
            n = ring_len["RDLEN" if name == "RDT" else "TDLEN"] // 16
            if v and (n == 0 or v >= n):
                bad["tail"].append(f"{at(a)} with a {n}-descriptor ring")
        elif name in ("RDH", "TDH"):
            if enabled["RCTL" if name == "RDH" else "TCTL"]:
                bad["head"].append(f"{at(a)} while enabled")
        elif name in enabled:
            enabled[name] = bool(v & EN)
        elif name == "ITR":
            itr_values.append(v)
            if v >> 16:
                bad["itr"].append(at(a))

    def detail(key: str, ok_text: str) -> str:
        found = bad[key]
        if not found:
            return ok_text
        more = f" (and {len(found) - 5} more)" if len(found) > 5 else ""
        return "; ".join(found[:5]) + more

    checks: list[Check] = [
        (
            "each CTRL.RST write is followed by at least 1 us before the next register"
            " access (SDM 13.4.1)",
            not bad["gap"],
            detail(
                "gap",
                f"{len(gaps)} resets ({resets['mmio']} through the memory BAR,"
                f" {resets['io']} through the I/O window, where port-I/O spacing alone"
                f" exceeds 1 us), smallest gap {min(gaps, default=0)} us",
            ),
        ),
        (
            "RDLEN and TDLEN are written as nonzero multiples of 128"
            " (SDM 13.4.27, 13.4.38)",
            not bad["len"],
            detail("len", "ok"),
        ),
        (
            "RDBAL and TDBAL are written 16-byte aligned (SDM 13.4.25, 13.4.36)",
            not bad["base"],
            detail("base", "ok"),
        ),
        (
            "every RDT and TDT write stays inside the ring (SDM 3.2.6, 3.4)",
            not bad["tail"],
            detail("tail", "ok"),
        ),
        (
            "RDH and TDH are written only while the receiver or transmitter is disabled"
            " (SDM 13.4.28, 13.4.39)",
            not bad["head"],
            detail("head", "ok"),
        ),
        (
            "ITR is written with its reserved bits 31:16 clear (SDM 13.4.18)",
            not bad["itr"],
            detail("itr", "ok"),
        ),
    ]
    observations = {
        "resets_by_window": resets,
        "reset_gaps_us": gaps,
        "ring_base_high_halves": sorted(high_bases),
        "itr_values_written": sorted(set(itr_values)),
    }
    return checks, observations


# --- guests ---------------------------------------------------------------------------


class Guest:
    """One QEMU process and the command channel to its guest-init.sh."""

    def __init__(self, name: str, argv: list[str], rundir: Path):
        self.name = name
        self.argv = argv
        self.rundir = rundir
        self.proc: subprocess.Popen | None = None
        self.sock: socket.socket | None = None
        self.buf = b""
        self.seq = 0
        self.dead: str | None = None
        self.cmdlog = (rundir / f"{name}-cmds.jsonl").open("a")

    def start(self) -> None:
        (self.rundir / f"{self.name}-argv.json").write_text(
            json.dumps(self.argv, indent=1)
        )
        self.proc = subprocess.Popen(
            self.argv,
            stdin=subprocess.DEVNULL,
            stdout=(self.rundir / f"{self.name}-qemu.log").open("w"),
            stderr=subprocess.STDOUT,
        )

    def connect(self, deadline: float) -> None:
        """Connects to the command socket once QEMU has created it."""
        path = str(self.rundir / f"{self.name}-cmd.sock")
        while True:
            self.check_alive()
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(path)
                self.sock = s
                break
            except OSError as e:
                s.close()
                if time.monotonic() > deadline:
                    raise GuestError(
                        f"{self.name}: command socket never appeared"
                    ) from e
                time.sleep(0.1)

    def wait_ready(self, deadline: float) -> None:
        """Waits for a READY line; the guest repeats it until its first command."""
        while not self._readline(deadline).startswith("L02 READY"):
            pass

    def check_alive(self) -> None:
        """Raises GuestError when the guest is known dead or its QEMU has exited."""
        if self.dead:
            raise GuestError(self.dead)
        if self.proc and self.proc.poll() is not None:
            self.dead = f"{self.name}: QEMU exited with status {self.proc.returncode}"
            raise GuestError(self.dead)

    def _readline(self, deadline: float) -> str:
        while b"\n" not in self.buf:
            self.check_alive()
            left = deadline - time.monotonic()
            if left <= 0:
                self.dead = f"{self.name}: no answer before the timeout"
                raise GuestError(self.dead)
            self.sock.settimeout(min(left, 0.5))
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError as e:
                # A reset or broken channel means the guest or its QEMU died, which a
                # driver can cause: a guest failure, not a harness error.
                self.check_alive()
                self.dead = f"{self.name}: command channel failed ({e})"
                raise GuestError(self.dead) from e
            if not chunk:
                self.check_alive()
                self.dead = f"{self.name}: command channel closed"
                raise GuestError(self.dead)
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode(errors="replace").rstrip("\r")

    def run(self, cmd: str, timeout: float = 30) -> tuple[int, str]:
        """Runs a shell command in the guest; returns (exit status, output)."""
        if "\n" in cmd:
            raise HarnessError("guest commands are single lines")
        self.check_alive()
        self.seq += 1
        seq = self.seq
        started = time.time()
        deadline = time.monotonic() + timeout
        end = re.compile(rf"^(.*)L02 END {seq} (\d+)$")
        out: list[str] = []
        try:
            try:
                self.sock.sendall(f"{seq} {cmd}\n".encode())
            except OSError as e:
                self.dead = f"{self.name}: command channel failed ({e})"
                raise GuestError(self.dead) from e
            while self._readline(deadline) != f"L02 BEGIN {seq}":
                pass
            while True:
                line = self._readline(deadline)
                m = end.match(line)
                if m:
                    if m.group(1):
                        out.append(m.group(1))
                    rc = int(m.group(2))
                    break
                out.append(line)
        except GuestError as e:
            self._log(seq, cmd, started, None, "\n".join(out), str(e))
            raise
        text = "\n".join(out)
        self._log(seq, cmd, started, rc, text, None)
        return rc, text

    def _log(self, seq, cmd, started, rc, out, error) -> None:
        self.cmdlog.write(
            json.dumps(
                {
                    "seq": seq,
                    "cmd": cmd,
                    "start": started,
                    "end": time.time(),
                    "rc": rc,
                    "out": out,
                    "error": error,
                }
            )
            + "\n"
        )
        self.cmdlog.flush()

    def stop(self, grace: float = 10) -> None:
        """Powers the guest off, or kills QEMU when it does not stop within grace seconds."""
        if self.proc is None:
            return
        if self.proc.poll() is None and self.sock and not self.dead:
            try:
                self.sock.sendall(b"0 poweroff -f\n")
            except OSError:
                pass
        try:
            self.proc.wait(grace)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        if self.sock:
            self.sock.close()
        self.cmdlog.close()


class Qmp:
    """A minimal QMP client for the DUT's monitor socket."""

    def __init__(self, path: Path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect(str(path))
        self.file = self.sock.makefile("rwb")
        self._recv()
        self.execute("qmp_capabilities")

    def _recv(self) -> dict:
        while True:
            msg = json.loads(self.file.readline())
            if "event" not in msg:
                return msg

    def execute(self, command: str, **arguments) -> dict:
        req = {"execute": command}
        if arguments:
            req["arguments"] = arguments
        self.file.write(json.dumps(req).encode() + b"\n")
        self.file.flush()
        reply = self._recv()
        if "error" in reply:
            raise HarnessError(f"QMP {command}: {reply['error']}")
        return reply.get("return", {})

    def close(self) -> None:
        self.file.close()
        self.sock.close()


def qemu_argv(role: str, args, rundir: Path, initrd: Path) -> list[str]:
    r = rundir
    net = {"dut": (DUT_MAC, "e1000"), "peer": (PEER_MAC, "virtio-net-pci")}[role]
    other = "peer" if role == "dut" else "dut"
    argv = [
        args.qemu,
        "-M",
        "q35",
        "-accel",
        args.accel,
        "-m",
        args.dut_mem if role == "dut" else "512M",
        "-smp",
        "2",
        "-nodefaults",
        "-no-reboot",
        "-display",
        "none",
        "-msg",
        "timestamp=on",
        "-kernel",
        str(args.kernel),
        "-initrd",
        str(initrd),
        "-append",
        f"console=ttyS0 panic=-1 l02.role={role}",
        "-chardev",
        f"file,id=con,path={r}/{role}-console.log",
        "-serial",
        "chardev:con",
        "-chardev",
        f"socket,id=cmd,path={r}/{role}-cmd.sock,server=on,wait=off",
        "-serial",
        "chardev:cmd",
        "-netdev",
        (
            f"dgram,id=n0,local.type=unix,local.path={r}/{role}-net.sock,"
            f"remote.type=unix,remote.path={r}/{other}-net.sock"
        ),
        "-device",
        f"{net[1]},id={DUT_NIC_ID},netdev=n0,mac={net[0]},romfile=",
        "-object",
        f"filter-dump,id=d0,netdev=n0,file={r}/{role}.pcap",
    ]
    if args.accel == "kvm":
        argv += ["-cpu", "host"]
    if role == "dut":
        (r / "trace-events").write_text("\n".join(TRACE_EVENTS) + "\n")
        argv += [
            "-qmp",
            f"unix:{r}/dut-qmp.sock,server=on,wait=off",
            "-trace",
            f"events={r}/trace-events",
            "-D",
            f"{r}/dut-trace-raw.log",
        ]
    return argv


# --- scenarios ------------------------------------------------------------------------


@dataclasses.dataclass
class Post:
    """What deferred checks see after QEMU exits: the decoded trace and captures."""

    accesses: list[Access]
    windows: dict[int, Window]
    rundir: Path

    def during(self, step: int) -> list[Access]:
        """Returns the accesses made while scenario number step was running."""
        w = self.windows.get(step)
        if w is None:
            return []
        return [a for a in self.accesses if a.t is not None and w.start <= a.t <= w.end]

    def frames(self, side: str) -> list[Frame]:
        return read_pcap(self.rundir / f"{side}.pcap")


# A deferred check gets the Post and its scenario's number; returns (passed, detail).
Deferred = Callable[[Post, int], tuple[bool, str]]


@dataclasses.dataclass
class Ctx:
    dut: Guest
    peer: Guest
    qmp: Qmp
    driver: str
    rundir: Path
    step: int = 0  # 1-based position of the running scenario, for file names
    checks: list[Check] = dataclasses.field(default_factory=list)
    observations: dict = dataclasses.field(default_factory=dict)
    deferred: list[tuple[int, str, Deferred, bool]] = dataclasses.field(
        default_factory=list
    )
    actions: list[dict] = dataclasses.field(default_factory=list)

    def check(self, name: str, ok, detail="") -> bool:
        self.checks.append((name, bool(ok), str(detail).strip()))
        return bool(ok)

    def observe(self, key: str, value) -> None:
        """Records a fact for L02f that is not itself a pass/fail condition."""
        self.observations[key] = value

    def defer(self, name: str, fn: Deferred, check: bool = True) -> None:
        """Registers a check, or with check=False an observation, for after the run.

        Deferred checks read the register trace and packet captures, which are
        complete only once QEMU has exited.
        """
        self.deferred.append((self.step, name, fn, check))

    def host(self, action: str, fn: Callable[[], object]):
        """Runs a host-side step and records its time window for the trace labels."""
        start = time.time()
        try:
            return fn()
        finally:
            self.actions.append(
                {
                    "step": self.step,
                    "action": action,
                    "start": start,
                    "end": time.time(),
                }
            )

    def hold(self, seconds: float) -> None:
        self.host(f"hold {seconds} s", lambda: time.sleep(seconds))

    def set_link(self, up: bool) -> None:
        """Toggles the DUT's link through QEMU's monitor.

        A monitor that fails because the DUT's QEMU has exited (after a guest panic,
        which a driver can cause) is a guest failure, like a broken command channel;
        a monitor that fails while QEMU runs is the harness's.
        """

        def toggle() -> None:
            try:
                self.qmp.execute("set_link", name=DUT_NIC_ID, up=up)
            except (OSError, ValueError) as e:
                if self.dut.proc:
                    try:
                        self.dut.proc.wait(2)
                    except subprocess.TimeoutExpired:
                        pass
                self.dut.check_alive()
                raise HarnessError(f"QMP set_link failed: {e}") from e

        self.host(f"set_link {'up' if up else 'down'}", toggle)


def wait_for(guest: Guest, cmd: str, want: str, timeout: float) -> tuple[bool, str]:
    """Polls cmd once a second until its output equals want; returns (ok, last output)."""
    deadline = time.monotonic() + timeout
    while True:
        rc, out = guest.run(cmd)
        if rc == 0 and out.strip() == want:
            return True, out.strip()
        if time.monotonic() > deadline:
            return False, out.strip()
        time.sleep(1)


def ping(
    c: Ctx, guest: Guest, dst: str, name: str, count: int = 3, size: int | None = None
) -> bool:
    """Pings dst from guest; the check passes on zero loss."""
    s = "" if size is None else f" -s {size}"
    rc, out = guest.run(f"ping -c {count} -W 2{s} {dst}", timeout=20 + 2 * count)
    return c.check(name, rc == 0 and " 0% packet loss" in out, out)


def carrier(c: Ctx, want: str, timeout: float, name: str) -> bool:
    ok, out = wait_for(c.dut, "cat /sys/class/net/eth0/carrier", want, timeout)
    return c.check(name, ok, out)


def unicast_frames(accesses: list[Access], t0: float, t1: float) -> int:
    """Counts frames the model accepted for the DUT's own MAC between two host times."""
    return sum(
        1
        for a in accesses
        if a.kind == "event"
        and a.name == "e1000x_rx_flt_ucast_match"
        and a.t is not None
        and t0 <= a.t <= t1
    )


def no_leftovers(t0: float, t1: float, bound: int = 4) -> Deferred:
    """Few unicast frames reached the DUT while it was coming up.

    Nothing the DUT does during bring-up draws a unicast reply, so frames then are left
    over from an earlier scenario: sent while the DUT could not receive and held until
    it could. They can use up a stalled driver's buffers and fail this scenario for
    the earlier one's fault; this check names that cause.
    """

    def check(p: Post, _: int) -> tuple[bool, str]:
        n = unicast_frames(p.accesses, t0, t1)
        return (
            n <= bound,
            f"{n} unicast frames arrived during bring-up (at most {bound})",
        )

    return check


def bring_up(c: Ctx, tag: str = "") -> bool:
    """Loads the driver and brings eth0 up with its address; True when all went well."""
    t = f" ({tag})" if tag else ""
    t0 = time.time()
    rc, out = c.dut.run(f"insmod /lib/modules/{c.driver}.ko")
    if not c.check("insmod" + t, rc == 0, out):
        return False
    rc, out = c.dut.run(f"ls /sys/bus/pci/drivers/{c.driver}/ | grep ':'")
    ok = c.check("bound to a PCI device" + t, rc == 0 and out.strip() != "", out)
    rc, out = c.dut.run("cat /sys/class/net/eth0/address")
    ok &= c.check("MAC matches QEMU's" + t, out.strip() == DUT_MAC, out)
    rc, out = c.dut.run(f"ip link set eth0 up && ip addr add {DUT_IP}/24 dev eth0")
    ok &= c.check("interface up" + t, rc == 0, out)
    ok &= carrier(c, "1", 15, "carrier within 15 s" + t)
    c.defer(
        "no frames left over from an earlier scenario arrived during bring-up" + t,
        no_leftovers(t0, time.time()),
    )
    return ok


def tear_down(c: Ctx, tag: str = "") -> bool:
    rc, out = c.dut.run(f"ip link set eth0 down && rmmod {c.driver}")
    return c.check("rmmod" + (f" ({tag})" if tag else ""), rc == 0, out)


def both_ways(c: Ctx, when: str) -> bool:
    ok = ping(c, c.dut, PEER_IP, f"DUT pings peer {when}")
    return ping(c, c.peer, DUT_IP, f"peer pings DUT {when}") and ok


def forget_neighbors(c: Ctx) -> None:
    """Records, then clears, both guests' neighbor (ARP) entries.

    Pings sent while the link was down leave the entry unresolved with packets queued
    on it; the first ping afterwards then waits for a fresh resolution and can be lost.
    That is the stack's behavior, caused by the scenario, not the driver's.
    """
    for g, who in ((c.dut, "DUT"), (c.peer, "peer")):
        _, out = g.run("ip neigh show dev eth0; ip neigh flush dev eth0")
        c.observe(f"{who} neighbor entries before the flush", out)


def bar0(c: Ctx) -> int | None:
    """Returns the e1000's memory BAR address, from sysfs."""
    rc, out = c.dut.run("head -1 /sys/class/net/eth0/device/resource")
    try:
        base = int(out.split()[0], 16) if rc == 0 else 0
    except (IndexError, ValueError):
        base = 0
    c.check("memory BAR found in sysfs", base != 0, out)
    return base or None


def devmem(c: Ctx, base: int, reg: str, value: int | None = None) -> int | None:
    """Reads a register through /dev/mem, or writes it when value is given.

    These accesses are the harness's, not the driver's: the trace labels put them in the
    devmem command's phase.
    """
    addr = base + REG[reg]
    if value is None:
        rc, out = c.dut.run(f"devmem {addr:#x} 32")
        try:
            return int(out.strip(), 16) if rc == 0 else None
        except ValueError:
            return None
    rc, out = c.dut.run(f"devmem {addr:#x} 32 {value:#x}")
    c.check(f"harness writes {reg} = {value:#x}", rc == 0, out)
    return value


# A request every millisecond whether or not replies come, 1042-byte frames. busybox nc
# has no UDP mode, and ping -i 0 hangs the guest.
FLOOD = "ping -i 0.001 -q -s 1000 -W 1"


def start_flood(c: Ctx, guest: Guest, dst: str, who: str) -> bool:
    """Starts a ping flood in the background and checks it runs; settle() stops it."""
    guest.run(f"{FLOOD} -c 1000000 {dst} >/dev/null 2>&1 &")
    rc, out = guest.run("sleep 0.5; pidof ping")
    return c.check(f"{who} flood running", rc == 0, out)


KERNEL_LOG_PROBLEM = re.compile(
    r"WARNING:|Call Trace:|BUG:|Oops|Kernel panic|general protection fault"
    r"|Unable to handle|Tx Unit Hang|NETDEV WATCHDOG|transmit queue \d+ timed out"
    r"|nobody cared|page allocation failure|DMA-API|swiotlb buffer is full"
    r"|UBSAN|KASAN|refcount_t:|list_(?:add|del) corruption|blocked for more than"
)


def kernel_log_problems(log: str) -> list[str]:
    """Returns the kernel log lines that show a driver or kernel fault.

    Warnings, call traces, oopses, transmit hangs and watchdog timeouts, interrupt
    storms, DMA-API and allocation failures. Ordinary driver messages (link up and
    down, probe banners) do not count.
    """
    return [line for line in log.splitlines() if KERNEL_LOG_PROBLEM.search(line)]


def settle(c: Ctx, name: str) -> None:
    """Ends a scenario: stops background traffic, unloads the driver if a failed
    scenario left it loaded, and checks the DUT's kernel log since the last scenario.

    The log is taken after the unload, so warnings from rmmod count.
    """
    for g in (c.dut, c.peer):
        if not g.dead:
            g.run("killall -q ping httpd wget; rm -rf /tmp/www; true")
    if c.dut.dead:
        return
    rc, _ = c.dut.run(f"grep -q '^{c.driver} ' /proc/modules")
    if rc == 0:
        rc, out = c.dut.run(f"ip link set eth0 down; rmmod {c.driver}")
        c.check(
            "cleanup: driver unloaded after the scenario stopped early", rc == 0, out
        )
    _, log = c.dut.run("dmesg -c")
    (c.rundir / f"dut-dmesg-{c.step:02d}-{name}.txt").write_text(log + "\n")
    problems = kernel_log_problems(log)
    c.check(
        "kernel log has no warnings, call traces or transmit hangs",
        not problems,
        "\n".join(problems[:20]) or f"{len(log.splitlines())} lines, none flagged",
    )


def scenario_smoke(c: Ctx) -> None:
    """Probe, MAC, link, ping both ways, unload.

    The capture checks confirm afterwards that the driver used the EEPROM interface;
    they cannot show that the MAC came from it.
    """
    if not bring_up(c):
        return
    ping(c, c.dut, PEER_IP, "DUT pings peer")
    ping(c, c.peer, DUT_IP, "peer pings DUT")
    tear_down(c)


# (ICMP payload, Ethernet frame length without FCS). A 0-byte payload makes a 42-byte
# frame, which must leave the DUT padded to 60 (spec 6.4, SDM 3.3.3).
FRAME_SIZES = ((0, 60), (18, 60), (19, 61), (1471, 1513), (1472, 1514))


def dut_sent_sizes(p: Post, _: int) -> tuple[bool, str]:
    """The peer's capture holds DUT echo requests and replies at each design size."""
    seen = {(t, n) for s, _, t, n in icmp_echoes(p.frames("peer")) if s == DUT_IP}
    want = {(t, n) for n in (60, 61, 1513, 1514) for t in (0, 8)}
    missing = sorted(want - seen)
    return (
        not missing,
        f"missing (type, length) {missing}" if missing else "all present",
    )


def dut_runts(p: Post, _: int) -> tuple[bool, str]:
    mac = bytes.fromhex(DUT_MAC.replace(":", ""))
    short = [
        len(f.data)
        for f in p.frames("peer")
        if f.data[6:12] == mac and len(f.data) < 60
    ]
    return not short, f"{len(short)} short frames, lengths {sorted(set(short))}"


def scenario_frame_sizes(c: Ctx) -> None:
    """Transmit and receive at 60, 61, 1513 and 1514 bytes, and a 42-byte frame the
    DUT must pad."""
    if not bring_up(c):
        return
    for payload, _ in FRAME_SIZES:
        ping(
            c,
            c.dut,
            PEER_IP,
            f"DUT pings peer with {42 + payload}-byte frames",
            2,
            payload,
        )
    for payload, frame in FRAME_SIZES[1:]:
        ping(c, c.peer, DUT_IP, f"peer pings DUT with {frame}-byte frames", 2, payload)
    c.defer(
        "the DUT sent echo requests and replies of 60, 61, 1513 and 1514 bytes",
        dut_sent_sizes,
    )
    c.defer("no frame the DUT sent was shorter than 60 bytes", dut_runts)
    tear_down(c)


def wraps_at_least(reg: str, n: int) -> Deferred:
    def check(p: Post, step: int) -> tuple[bool, str]:
        w = tail_wraps(p.during(step), REG[reg])
        return w >= n, f"{reg} wrapped {w} times"

    return check


def http_blob(c: Ctx, server: Guest, client: Guest, ip: str, label: str) -> None:
    """Serves 4 MiB of random data from server and checks client receives it intact."""
    rc, out = server.run(
        "mkdir -p /tmp/www && dd if=/dev/urandom of=/tmp/www/blob bs=1k count=4096"
        " 2>/dev/null && md5sum /tmp/www/blob | cut -d' ' -f1"
        " && httpd -p 8080 -h /tmp/www"
    )
    sent = out.strip().splitlines()[0] if rc == 0 and out.strip() else ""
    if not c.check(f"HTTP server with a 4 MiB file ({label})", sent, out):
        return
    rc, got = client.run(
        f"wget -q -T 20 -O - http://{ip}:8080/blob | md5sum | cut -d' ' -f1",
        timeout=120,
    )
    c.check(
        f"4 MiB over HTTP {label} arrives intact",
        got.strip() == sent,
        f"sent {sent}, got {got}",
    )
    server.run("killall -q httpd; rm -rf /tmp/www; true")


def scenario_ring_wrap(c: Ctx) -> None:
    """Enough traffic to wrap both rings several times, with data checked end to end."""
    if not bring_up(c):
        return
    n = 1500
    for guest, dst, who in ((c.dut, PEER_IP, "DUT"), (c.peer, DUT_IP, "peer")):
        # -w bounds the run: without replies, ping -A falls back to one
        # request a second, which would outlast the command timeout.
        rc, out = guest.run(f"ping -A -q -c {n} -w 60 -W 2 {dst}", timeout=120)
        c.check(
            f"{who} sends {n} pings back to back, none lost",
            rc == 0 and " 0% packet loss" in out,
            out,
        )
    http_blob(c, c.peer, c.dut, PEER_IP, "peer to DUT")
    http_blob(c, c.dut, c.peer, DUT_IP, "DUT to peer")
    c.defer(
        "the transmit ring wrapped at least 3 times (TDT went down)",
        wraps_at_least("TDT", 3),
    )
    c.defer(
        "the receive ring wrapped at least 3 times (RDT went down)",
        wraps_at_least("RDT", 3),
    )
    tear_down(c)


def overrun_events(p: Post, step: int) -> tuple[bool, str]:
    n = sum(
        1
        for a in p.during(step)
        if a.kind == "event" and a.name == "e1000_receiver_overrun"
    )
    return n > 0, f"{n} e1000_receiver_overrun events"


def stalled(t_before: float, t_after: float, t1: float) -> Deferred:
    """While the harness had the DUT's interrupts masked, the model accepted frames for
    the DUT and nothing wrote the receive tail: the ring filled without being
    replenished. Backs up the dry-ring read, which a device reset would also satisfy
    (both pointers 0).

    The masked interval starts at the harness's IMC write, the last all-ones IMC write
    between the host times taken just before and just after it, not at the host time
    before it: tail writes the driver made before the mask took effect are legitimate.
    It ends at t1, taken before the harness restores IMS."""

    def check(p: Post, _: int) -> tuple[bool, str]:
        masks = [
            a.t
            for a in p.accesses
            if a.t is not None
            and t_before <= a.t <= t_after
            and a.is_register
            and a.rw == "w"
            and a.reg == REG["IMC"]
            and a.value == 0xFFFFFFFF
        ]
        if not masks:
            return False, "no IMC write masking every cause found in the trace"
        t0 = masks[-1]
        frames = unicast_frames(p.accesses, t0, t1)
        tails = sum(
            1
            for a in p.accesses
            if a.t is not None
            and t0 <= a.t <= t1
            and a.is_register
            and a.rw == "w"
            and a.reg == REG["RDT"]
        )
        return (
            frames > 0 and tails == 0,
            f"{frames} frames accepted, {tails} RDT writes",
        )

    return check


def scenario_rx_overrun(c: Ctx) -> None:
    """A receive flood with the DUT's interrupts masked by the harness, so the ring runs
    dry; then the mask is restored and reception must resume (spec 6.3).

    The ring running dry is read from the device: the receive head has reached the tail
    (SDM 3.2.6). QEMU's model does not drop frames then; it stops taking them, so the
    peer's sends back up and its ping may stop early with "No buffer space available".
    """
    if not bring_up(c) or not both_ways(c, "before the flood"):
        return
    base = bar0(c)
    if base is None:
        return
    ims = devmem(c, base, "IMS")
    if not c.check("driver's interrupt mask read", ims is not None, f"IMS = {ims}"):
        return
    t_mask = time.time()
    devmem(c, base, "IMC", 0xFFFFFFFF)
    t_masked = time.time()
    _, out = c.peer.run(f"{FLOOD} -c 1000 {DUT_IP}; true", timeout=30)
    c.observe("peer flood output", out)
    c.hold(1)
    head, tail = devmem(c, base, "RDH"), devmem(c, base, "RDT")
    c.check(
        "the receive ring ran dry while interrupts were masked (RDH reached RDT)",
        head is not None and head == tail,
        f"RDH {head}, RDT {tail}",
    )
    t_unmask = time.time()
    devmem(c, base, "IMS", ims)
    c.defer(
        "while masked, the device accepted frames and the driver wrote no RDT",
        stalled(t_mask, t_masked, t_unmask),
    )
    c.dut.run("sleep 2")
    both_ways(c, "after the overrun")
    _, out = c.dut.run(
        "cd /sys/class/net/eth0/statistics && grep . rx_packets rx_dropped"
        " rx_missed_errors rx_over_errors rx_fifo_errors"
    )
    c.observe("driver statistics after the flood", out)
    c.defer("QEMU reported a receiver overrun", overrun_events, check=False)
    tear_down(c)


def icr_lsc(t0: float) -> Deferred:
    """ICR reads with the link-change cause set, from host time t0 (the link toggle)
    to the end of the scenario, so bring-up's own link change is not counted."""

    def check(p: Post, step: int) -> tuple[bool, str]:
        n = sum(
            1
            for a in p.during(step)
            if a.t >= t0
            and a.is_register
            and a.rw == "r"
            and a.reg == REG["ICR"]
            and a.value & ICR_LSC
        )
        return n > 0, f"{n} ICR reads with LSC set after the link dropped"

    return check


def scenario_link_flap(c: Ctx) -> None:
    """Link down and up through QEMU's monitor; carrier follows and traffic resumes."""
    if not bring_up(c) or not both_ways(c, "before the link drops"):
        return
    t_down = time.time()
    c.set_link(False)
    carrier(c, "0", 10, "carrier drops within 10 s of link loss")
    rc, out = c.dut.run(f"ping -c 2 -W 1 {PEER_IP}", timeout=15)
    c.check("no traffic while the link is down", rc != 0, out)
    c.set_link(True)
    carrier(c, "1", 15, "carrier returns within 15 s")
    forget_neighbors(c)
    both_ways(c, "after the link returns")
    c.defer(
        "ICR reads showed the link-change cause (LSC)", icr_lsc(t_down), check=False
    )
    tear_down(c)


def busy_before(t: float, regs: tuple[str, ...], n: int = 10) -> Deferred:
    """Traffic was flowing in the second before host time t: each tail register was
    written at least n times."""

    def check(p: Post, _: int) -> tuple[bool, str]:
        near = [a for a in p.accesses if a.t is not None and t - 1 <= a.t <= t]
        got = {r: sum(1 for a in near if a.rw == "w" and a.reg == REG[r]) for r in regs}
        return all(v >= n for v in got.values()), f"writes in the second before: {got}"

    return check


def scenario_link_loss_tx(c: Ctx) -> None:
    """The link drops for 8 s while the DUT is transmitting; carrier must fall, and
    traffic must resume without a hang afterwards.

    Meant as the probe for L02e item L4 (transmits queued at link loss). QEMU's model
    keeps completing transmit descriptors with the link down, so nothing stays queued
    through the outage; TDH and TDT read during it record that. L4 cannot be reproduced
    in emulation.
    """
    if not bring_up(c) or not both_ways(c, "before the link drops"):
        return
    base = bar0(c)
    if not start_flood(c, c.dut, PEER_IP, "DUT"):
        return
    c.dut.run("sleep 1")
    c.defer(
        "the DUT was transmitting when the link dropped",
        busy_before(time.time(), ("TDT",)),
    )
    t_down = time.time()
    c.set_link(False)
    carrier(c, "0", 10, "carrier drops within 10 s of link loss")
    c.hold(max(0.0, 8 - (time.time() - t_down)))
    if base:
        head, tail = devmem(c, base, "TDH"), devmem(c, base, "TDT")
        c.observe("TDH, TDT after 8 s without link", [head, tail])
    c.set_link(True)
    c.dut.run("killall -q ping; true")
    carrier(c, "1", 15, "carrier returns within 15 s")
    forget_neighbors(c)
    both_ways(c, "after the link returns")
    tear_down(c)


def scenario_stop_start(c: Ctx) -> None:
    """20 interface down/up cycles back to back, then traffic."""
    if not bring_up(c):
        return
    rc, out = c.dut.run(
        "for i in $(seq 20); do"
        " ip link set eth0 down && ip link set eth0 up || exit 1; done",
        timeout=180,
    )
    c.check("20 down/up cycles", rc == 0, out)
    carrier(c, "1", 15, "carrier within 15 s after the cycles")
    both_ways(c, "after the cycles")
    tear_down(c)


# QEMU's e1000 model holds all reception for one second after every RCTL write
# (hw/net/e1000.c, flush_queue_timer; the manual describes no such behavior). Frames that
# arrive meanwhile wait outside the model (in the socket backend) and are delivered in one
# burst when the hold ends.
RX_HOLD = 1.0

# Seconds the harness waits after it reads carrier 1, before the recovery pings of
# down-during-traffic. Both drivers rewrite RCTL at carrier-up, which starts a hold; frames
# the peer's flood sent after the DUT went down are released in a burst when it ends. A
# ping sent inside the hold can lose its reply behind that burst (L02f2, V6 and H1). In
# the 18 L02f2 traces the last carrier-up RCTL write came 0.50 s (candidate) to 1.00 s
# (reference) before the harness read carrier 1, so the hold ended at most 0.05 s after
# that read. 3 s covers that with a margin of about 2 s, enough for a carrier-up RCTL write
# up to ~1.9 s after the read. Fixed and bounded; the pings are never retried. The deferred
# check settled_before() confirms from each run's trace that the hold was over.
RECOVERY_SETTLE = 3.0


def settled_before(t_ping: float, t_end: float) -> Deferred:
    """The pings starting at host time t_ping began after the model's receive hold ended.

    Passes when the last RCTL write before t_ping came at least RX_HOLD earlier. The
    detail records the burst: unicast frames the model accepted between that write and
    t_ping (frames left over from the flood), and those accepted while the pings ran,
    up to t_end.
    """

    def check(p: Post, _: int) -> tuple[bool, str]:
        rctl = [
            a.t
            for a in p.accesses
            if a.t is not None
            and a.is_register
            and a.rw == "w"
            and a.reg == REG["RCTL"]
            and a.t <= t_ping
        ]
        if not rctl:
            return False, "no RCTL write before the pings"
        last = max(rctl)
        burst = [
            a.t
            for a in p.accesses
            if a.kind == "event"
            and a.name == "e1000x_rx_flt_ucast_match"
            and a.t is not None
            and last <= a.t < t_ping
        ]
        during = unicast_frames(p.accesses, t_ping, t_end)
        where = f", the last {t_ping - max(burst):.3f} s before them" if burst else ""
        return t_ping - last >= RX_HOLD, (
            f"last RCTL write {t_ping - last:.3f} s before the pings (hold {RX_HOLD} s);"
            f" {len(burst)} unicast frames accepted after it and before the pings{where};"
            f" {during} while the DUT's pings ran"
        )

    return check


def scenario_down_during_traffic(c: Ctx) -> None:
    """The interface goes down while traffic flows both ways, then comes back.

    Both floods run until the interface is down and are stopped only then, so the peer
    keeps sending into the outage. After carrier returns, the harness waits
    RECOVERY_SETTLE seconds for the model's receive hold and the burst of leftover
    frames to pass, then pings once each way; see RECOVERY_SETTLE.
    """
    if not bring_up(c) or not both_ways(c, "before the traffic"):
        return
    if not start_flood(c, c.peer, DUT_IP, "peer") or not start_flood(
        c, c.dut, PEER_IP, "DUT"
    ):
        return
    c.dut.run("sleep 1")
    c.defer(
        "traffic flowed both ways when the interface went down",
        busy_before(time.time(), ("TDT", "RDT")),
    )
    rc, out = c.dut.run("ip link set eth0 down")
    c.check("interface goes down during traffic", rc == 0, out)
    c.dut.run("killall -q ping; true")
    c.peer.run("killall -q ping; true")
    rc, out = c.dut.run("ip link set eth0 up")
    c.check("interface comes back up", rc == 0, out)
    carrier(c, "1", 15, "carrier within 15 s")
    c.hold(RECOVERY_SETTLE)
    t_ping = time.time()
    ping(c, c.dut, PEER_IP, "DUT pings peer afterwards")
    c.defer(
        "the pings afterwards began after the receive hold and the leftover burst",
        settled_before(t_ping, time.time()),
    )
    ping(c, c.peer, DUT_IP, "peer pings DUT afterwards")
    tear_down(c)


def scenario_reload(c: Ctx) -> None:
    """Three load, traffic, unload cycles."""
    for i in (1, 2, 3):
        tag = f"load {i}"
        if not bring_up(c, tag):
            return
        ping(c, c.dut, PEER_IP, f"DUT pings peer ({tag})", 2)
        ping(c, c.peer, DUT_IP, f"peer pings DUT ({tag})", 2)
        if not tear_down(c, tag):
            return


def itr_readback(p: Post, step: int) -> tuple[bool, str]:
    """The last ITR read in the scenario returns the value last written to ITR.

    Walks the whole trace: a global reset returns ITR to 0 (SDM 13.4.18, 14.7). This
    compares the model's stored value with the model's own log of writes, so it checks
    the model and the trace decoder, not the driver: a driver that never writes ITR, or
    writes a wrong value, still passes. The driver's writes are recorded separately.
    """
    w = p.windows[step]
    reads = [
        i
        for i, a in enumerate(p.accesses)
        if a.t is not None
        and w.start <= a.t <= w.end
        and a.is_register
        and a.rw == "r"
        and a.reg == REG["ITR"]
    ]
    if not reads:
        return False, "no ITR read in the trace"
    last = 0
    for a in p.accesses[: reads[-1]]:
        if not a.is_register or a.rw != "w" or a.reg is None:
            continue
        if a.reg == REG["ITR"]:
            last = a.value
        elif a.reg == REG["CTRL"] and a.value & CTRL_RST:
            last = 0
    got = p.accesses[reads[-1]].value
    return got == last, f"read {got:#x}, last written {last:#x}"


def itr_writes(t_before: float, t_after: float) -> Deferred:
    """The ITR values written in the scenario after its last global reset before the
    harness's ITR read-back, the last ITR read between the host times taken just before
    and just after it. Bounding at that read keeps teardown's reset from discarding the
    values the driver used while it ran, and an earlier ITR read by the driver itself
    from cutting the collection short."""

    def check(p: Post, step: int) -> tuple[bool, str]:
        reads = [
            a.t
            for a in p.during(step)
            if a.t is not None
            and t_before <= a.t <= t_after
            and a.is_register
            and a.rw == "r"
            and a.reg == REG["ITR"]
        ]
        if not reads:
            return False, "no harness ITR read found in the trace"
        vals: list[int] = []
        for a in p.during(step):
            if a.t is not None and a.t >= reads[-1]:
                break
            if not a.is_register or a.rw != "w" or a.reg is None:
                continue
            if a.reg == REG["CTRL"] and a.value & CTRL_RST:
                vals = []
            elif a.reg == REG["ITR"]:
                vals.append(a.value)
        return bool(vals), f"{len(vals)} writes, values {sorted(set(vals))}"

    return check


def scenario_itr(c: Ctx) -> None:
    """The interrupt-throttling register is read back (the spec's C-2 decision: through
    the memory BAR, compared with the last write in the register trace), and the values
    the driver wrote after its last reset are recorded for L02f."""
    if not bring_up(c) or not both_ways(c, "to raise interrupts"):
        return
    base = bar0(c)
    if base is None:
        return
    t_read = time.time()
    v = devmem(c, base, "ITR")
    t_read_done = time.time()
    if c.check("ITR read through the memory BAR", v is not None, f"{v}"):
        rate = round(1e9 / (v * 256)) if v else None
        c.observe("ITR", {"value": v, "interrupts_per_s": rate})
    c.defer(
        "model and decoder agree: ITR reads back the value the trace shows last written,"
        " or 0 after a reset (SDM 13.4.18)",
        itr_readback,
    )
    c.defer(
        "ITR values the driver wrote after its last reset",
        itr_writes(t_read, t_read_done),
        check=False,
    )
    tear_down(c)


def expect_dead(guest: Guest, cmd: str, timeout: float, *signs: str) -> list[Check]:
    """Runs cmd; passes only if the harness then reports the guest dead with a sign."""
    name = f"guest reported dead ({' or '.join(signs)})"
    if guest.dead:
        return [(name, False, f"already dead before the test: {guest.dead}")]
    try:
        rc, out = guest.run(cmd, timeout=timeout)
    except GuestError as e:
        return [(name, any(s in str(e) for s in signs), str(e))]
    return [(name, False, f"command returned {rc}: {out}")]


def scenario_selftest_hang(c: Ctx) -> None:
    """Harness self-test: a command that never returns marks the DUT dead.

    Passes when detection works. The DUT is unusable afterwards, so every later
    scenario in the run fails.
    """
    c.checks += expect_dead(c.dut, "sleep 600", 5, "no answer before the timeout")


def scenario_selftest_panic(c: Ctx) -> None:
    """Harness self-test: a guest kernel panic marks the DUT dead.

    Passes when detection works; later scenarios in the run fail.
    """
    rc, out = c.dut.run("cat /proc/sys/kernel/sysrq")
    if not c.check("magic SysRq available", rc == 0, out):
        return
    c.checks += expect_dead(
        c.dut,
        "echo c > /proc/sysrq-trigger",
        20,
        "channel closed",
        "channel failed",
        "QEMU exited",
    )


SCENARIOS: dict[str, Callable[[Ctx], None]] = {
    "smoke": scenario_smoke,
    "frame-sizes": scenario_frame_sizes,
    "ring-wrap": scenario_ring_wrap,
    "rx-overrun": scenario_rx_overrun,
    "link-flap": scenario_link_flap,
    "link-loss-tx": scenario_link_loss_tx,
    "stop-start": scenario_stop_start,
    "down-during-traffic": scenario_down_during_traffic,
    "reload": scenario_reload,
    "itr": scenario_itr,
    "selftest-hang": scenario_selftest_hang,
    "selftest-panic": scenario_selftest_panic,
}
# `--scenario all` runs these, in this order: the design's section 5 list plus
# link-loss-tx (the probe for L02e item L4), not in section 5's order.
SUITE = [s for s in SCENARIOS if not s.startswith("selftest-")]


def capture_checks(rundir: Path, counts: dict[str, int], pinged: bool) -> list[Check]:
    """Checks that the stored captures hold what the run claims to have exercised."""
    checks: list[Check] = [
        ("register trace has e1000 MMIO writes", counts["mmio_write"] > 0, str(counts)),
        ("register trace has e1000 MMIO reads", counts["mmio_read"] > 0, str(counts)),
        (
            "register trace has EEPROM interface accesses (EECD/EERD)",
            counts["eeprom"] > 0,
            str(counts),
        ),
    ]
    if pinged:
        for side in ("dut", "peer"):
            echoes = icmp_echoes(read_pcap(rundir / f"{side}.pcap"))
            want = {
                (DUT_IP, PEER_IP, 8),
                (PEER_IP, DUT_IP, 0),
                (PEER_IP, DUT_IP, 8),
                (DUT_IP, PEER_IP, 0),
            }
            seen = {(s, d, t) for s, d, t, _ in echoes}
            checks.append(
                (
                    f"{side}.pcap has both pings' requests and replies",
                    want <= seen,
                    f"{len(echoes)} echo frames",
                )
            )
    return checks


# --- run ------------------------------------------------------------------------------


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identities(args, initrd: Path) -> dict:
    files = {"kernel": args.kernel, "initramfs": initrd, "busybox": args.busybox}
    files.update({f"module:{m.name}": m for m in args.module})
    files.update(
        {
            f"harness:{p.name}": p
            for p in (HERE / "l02harness.py", HERE / "guest-init.sh")
        }
    )
    files["qemu"] = args.qemu_path
    return {
        "sha256": {k: sha256(Path(v)) for k, v in files.items()},
        "paths": {k: str(v) for k, v in files.items()},
        "qemu_version": args.qemu_version,
        "host_kernel": platform.release(),
        "python": platform.python_version(),
        "driver": args.driver,
        "accel": args.accel,
        "scenarios": args.scenario,
        "dut_mem": args.dut_mem,
    }


def resolve_host(args) -> None:
    """Finds the QEMU binary and its version, and picks the accelerator."""
    found = shutil.which(args.qemu)
    if not found:
        raise HarnessError(f"QEMU binary not found: {args.qemu}")
    args.qemu_path = Path(found)
    try:
        out = subprocess.run(
            [found, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        ).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HarnessError(f"cannot run {found} --version: {e}") from e
    if not out.strip():
        raise HarnessError(f"{found} --version printed nothing")
    args.qemu_version = out.splitlines()[0]
    if args.accel == "auto":
        kvm = os.access("/dev/kvm", os.R_OK | os.W_OK)
        args.accel = "kvm" if kvm else "tcg"
        if not kvm:
            print(
                "note: /dev/kvm is not usable; running under TCG, where the"
                " scenarios' timeouts may be too short",
                file=sys.stderr,
            )


def result(
    scenario: str,
    verdict: str,
    error,
    start: float,
    checks,
    step: int | None = None,
    observations: dict | None = None,
) -> dict:
    return {
        "scenario": scenario,
        "step": step,
        "verdict": verdict,
        "error": error,
        "start": start,
        "end": time.time(),
        "checks": [{"check": n, "ok": ok, "detail": d} for n, ok, d in checks],
        "observations": observations or {},
    }


def run_scenarios(ctx: Ctx, names: list[str], results: list[dict]) -> None:
    """Runs each scenario, then settle(); stops after an ERROR."""
    _, log = ctx.dut.run("dmesg -c")
    (ctx.rundir / "dut-dmesg-00-boot.txt").write_text(log + "\n")
    for step, name in enumerate(names, start=1):
        ctx.step, ctx.checks, ctx.observations = step, [], {}
        t0 = time.time()
        error, verdict = None, None
        try:
            SCENARIOS[name](ctx)
            settle(ctx, name)
        except GuestError as e:
            error, verdict = str(e), "FAIL"
        except (Exception, KeyboardInterrupt) as e:  # pylint: disable=broad-exception-caught
            error, verdict = f"{type(e).__name__}: {e}", "ERROR"
        if verdict is None:
            passed = bool(ctx.checks) and all(ok for _, ok, _ in ctx.checks)
            verdict = "PASS" if passed else "FAIL"
        results.append(
            result(name, verdict, error, t0, ctx.checks, step, ctx.observations)
        )
        print(f"{verdict} {name}" + (f" ({error})" if error else ""), flush=True)
        if verdict == "ERROR":
            break
    if not ctx.peer.dead:
        try:
            _, log = ctx.peer.run("dmesg")
            (ctx.rundir / "peer-dmesg.txt").write_text(log + "\n")
        except GuestError:
            pass


def post_process(ctx: Ctx | None, rundir: Path, results: list[dict]) -> list[Access]:
    """Decodes and labels the register trace, then applies the deferred checks."""
    regtrace = rundir / "dut-regtrace.log"
    if not regtrace.exists():
        return []
    with regtrace.open(errors="replace") as f:
        accesses = decode_trace(f)
    steps = {r["step"]: r for r in results if r.get("step")}
    windows = {
        s: Window(r["start"], r["end"], f"{s:02d} {r['scenario']}")
        for s, r in steps.items()
    }
    actions = ctx.actions if ctx else []
    with (rundir / "host-actions.jsonl").open("w") as f:
        for a in actions:
            f.write(json.dumps(a) + "\n")
    phases = [
        command_windows(rundir / "dut-cmds.jsonl", "dut"),
        command_windows(rundir / "peer-cmds.jsonl", "peer"),
        [Window(a["start"], a["end"], f"host: {a['action']}") for a in actions],
    ]
    labels = label_accesses(accesses, list(windows.values()), phases)
    write_labeled_trace(
        accesses, labels, rundir / "dut-regtrace.jsonl.gz", rundir / "trace-phases.json"
    )
    post = Post(accesses, windows, rundir)
    for step, name, fn, is_check in ctx.deferred if ctx else []:
        r = steps[step]
        before = r["verdict"]
        try:
            ok, detail = fn(post, step)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # A harness exception is an ERROR, but the scenario's own error (a dead
            # guest, say) is kept in front of it.
            r["verdict"] = "ERROR"
            err = f"deferred check {name!r}: {type(e).__name__}: {e}"
            r["error"] = f"{r['error']}; {err}" if r["error"] else err
        else:
            if is_check:
                r["checks"].append(
                    {"check": name, "ok": ok, "detail": detail, "deferred": True}
                )
                if not ok and r["verdict"] == "PASS":
                    r["verdict"] = "FAIL"
            else:
                r["observations"][name] = detail
        if r["verdict"] != before:
            print(f"{r['verdict']} {r['scenario']} (after trace checks)", flush=True)
    return accesses


def run(args) -> int:
    rundir = args.out.resolve()
    if rundir.exists():
        raise HarnessError(f"{rundir} exists; each run gets a fresh directory")
    for p in [args.kernel, args.busybox, *args.module]:
        if not p.is_file():
            raise HarnessError(f"missing input: {p}")
    if f"{args.driver}.ko" not in {m.name for m in args.module}:
        raise HarnessError(f"no module named {args.driver}.ko among --module")
    unknown = [s for s in args.scenario if s not in SCENARIOS]
    if unknown:
        raise HarnessError(f"unknown scenario(s): {', '.join(unknown)}")
    resolve_host(args)
    rundir.parent.mkdir(parents=True, exist_ok=True)
    try:
        rundir.mkdir(mode=0o700)
    except FileExistsError as e:
        raise HarnessError(f"{rundir} appeared meanwhile; not sharing it") from e

    initrd = rundir / "initramfs.cpio.gz"
    initrd.write_bytes(build_initramfs(args.busybox, args.module))
    (rundir / "identities.json").write_text(
        json.dumps(identities(args, initrd), indent=1)
    )

    peer = Guest("peer", qemu_argv("peer", args, rundir, initrd), rundir)
    dut = Guest("dut", qemu_argv("dut", args, rundir, initrd), rundir)
    results, qmp, ctx = [], None, None
    started = time.time()
    # FAIL means a guest misbehaved, which a driver can cause. ERROR means the harness or
    # the host did: the DUT loads no driver before the first scenario, so a boot failure
    # is an ERROR, as is any exception other than GuestError, or an interrupt.
    try:
        peer.start()
        dut.start()
        deadline = time.monotonic() + args.boot_timeout
        peer.connect(deadline)
        dut.connect(deadline)
        peer.wait_ready(deadline)
        dut.wait_ready(deadline)
        qmp = Qmp(rundir / "dut-qmp.sock")
        ctx = Ctx(dut, peer, qmp, args.driver, rundir)
    except (Exception, KeyboardInterrupt) as e:  # pylint: disable=broad-exception-caught
        results.append(result("boot", "ERROR", f"{type(e).__name__}: {e}", started, []))
        print(f"ERROR boot ({e})", flush=True)
    else:
        try:
            run_scenarios(ctx, args.scenario, results)
        except (Exception, KeyboardInterrupt) as e:  # pylint: disable=broad-exception-caught
            # The boot log or the peer's log could not be taken: the guest died first.
            results.append(
                result(
                    "between scenarios",
                    "ERROR",
                    f"{type(e).__name__}: {e}",
                    started,
                    [],
                )
            )
            print(f"ERROR between scenarios ({e})", flush=True)
    finally:
        if qmp:
            qmp.close()
        dut.stop()
        peer.stop()

    raw = rundir / "dut-trace-raw.log"
    counts = (
        filter_trace(raw, rundir / "dut-regtrace.log")
        if raw.exists()
        else empty_trace_counts()
    )
    if raw.exists():
        with raw.open("rb") as src, gzip.open(str(raw) + ".gz", "wb") as dst:
            dst.writelines(src)
        raw.unlink()
    t0 = time.time()
    try:
        accesses = post_process(ctx, rundir, results)
    except Exception as e:  # pylint: disable=broad-exception-caught
        accesses = []
        err = f"{type(e).__name__}: {e}"
        results.append(result("trace", "ERROR", err, t0, []))
        print(f"ERROR trace ({err})", flush=True)
    drove = any(r["scenario"] in SUITE for r in results)
    if drove and accesses:
        checks, observations = trace_rules(accesses)
        verdict = "PASS" if all(ok for _, ok, _ in checks) else "FAIL"
        results.append(result("trace", verdict, None, t0, checks, None, observations))
        print(f"{verdict} trace", flush=True)
    pinged = any(r["scenario"] == "smoke" and r["verdict"] == "PASS" for r in results)
    if any(r["scenario"] == "smoke" for r in results):
        t0 = time.time()
        try:
            checks = capture_checks(rundir, counts, pinged)
            verdict = "PASS" if all(ok for _, ok, _ in checks) else "FAIL"
            results.append(result("capture", verdict, None, t0, checks))
        except Exception as e:  # pylint: disable=broad-exception-caught
            err = f"{type(e).__name__}: {e}"
            results.append(result("capture", "ERROR", err, t0, []))
        print(f"{results[-1]['verdict']} capture", flush=True)
    for p in rundir.glob("*.sock"):
        p.unlink()
    verdicts = {r["verdict"] for r in results}
    if "ERROR" in verdicts or not results:
        overall = "ERROR"
    else:
        overall = "PASS" if verdicts == {"PASS"} else "FAIL"
    (rundir / "verdicts.json").write_text(
        json.dumps(
            {"overall": overall, "trace_counts": counts, "results": results}, indent=1
        )
    )
    print(f"{overall} overall; run directory {rundir}")
    return {"PASS": 0, "FAIL": 1}.get(overall, 2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="boot both guests and run scenarios")
    r.add_argument("--kernel", type=Path, required=True, help="guest bzImage")
    r.add_argument(
        "--module",
        type=Path,
        action="append",
        required=True,
        help="driver module to place in /lib/modules (repeatable)",
    )
    r.add_argument(
        "--driver",
        required=True,
        help="module and PCI driver name the DUT loads, e.g. e1000",
    )
    r.add_argument("--out", type=Path, required=True, help="fresh run directory")
    r.add_argument(
        "--scenario",
        action="append",
        help=(
            "scenario to run, in order (default smoke); 'all' is the suite"
            f" {SUITE}; the others are {[x for x in SCENARIOS if x not in SUITE]}"
        ),
    )
    r.add_argument(
        "--busybox",
        type=Path,
        default=Path("/usr/bin/busybox"),
        help="a statically linked busybox",
    )
    r.add_argument("--qemu", default="qemu-system-x86_64")
    r.add_argument(
        "--accel",
        choices=("auto", "kvm", "tcg"),
        default="auto",
        help="auto: KVM when /dev/kvm is usable, otherwise TCG",
    )
    r.add_argument("--boot-timeout", type=float, default=60)
    r.add_argument(
        "--dut-mem",
        default="3G",
        help="DUT memory. q35 maps RAM beyond 2 GiB above the 4 GiB boundary, so the"
        " default makes memory above 4 GiB available to a driver whose DMA mask allows it",
    )
    args = ap.parse_args(argv)
    args.scenario = [
        x for s in (args.scenario or ["smoke"]) for x in (SUITE if s == "all" else [s])
    ]
    try:
        return run(args)
    except (HarnessError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
