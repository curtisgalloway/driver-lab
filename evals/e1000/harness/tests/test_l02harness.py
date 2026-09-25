# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the parts of l02harness.py that run without QEMU."""

import gzip
import json
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import l02harness as h  # pylint: disable=wrong-import-position


def parse_newc(archive: bytes) -> list[tuple[str, int, bytes, int, int]]:
    """An independent newc reader: (name, mode, data, rdevmajor, rdevminor)."""
    out, off = [], 0
    while True:
        assert archive[off : off + 6] == b"070701", off
        f = [int(archive[off + 6 + 8 * i : off + 14 + 8 * i], 16) for i in range(13)]
        namesize, filesize = f[11], f[6]
        name_start = off + 110
        name = archive[name_start : name_start + namesize - 1].decode()
        data_start = name_start + namesize + (-(110 + namesize) % 4)
        data = archive[data_start : data_start + filesize]
        off = data_start + filesize + (-filesize % 4)
        if name == "TRAILER!!!":
            return out
        out.append((name, f[1], data, f[9], f[10]))


def pcap(frames: list[bytes]) -> bytes:
    head = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    body = b"".join(
        struct.pack("<IIII", 1, i, len(fr), len(fr)) + fr for i, fr in enumerate(frames)
    )
    return head + body


def echo_frame(src: str, dst: str, icmp_type: int, payload: int = 56) -> bytes:
    eth = b"\x52\x54\x00\x12\x34\x57" + b"\x52\x54\x00\x12\x34\x56" + b"\x08\x00"
    ip = bytes([0x45, 0, 0, 0, 0, 0, 0, 0, 64, 1, 0, 0])
    ip += bytes(int(x) for x in src.split(".")) + bytes(int(x) for x in dst.split("."))
    return eth + ip + bytes([icmp_type, 0, 0, 0, 0, 1, 0, 1]) + b"\0" * payload


class CpioTest(unittest.TestCase):

    def test_round_trip_and_alignment(self):
        entries = [
            ("bin", 0o040755, b"", 0, 0),
            ("dev/console", 0o020600, b"", 5, 1),
            ("init", 0o100755, b"#!/bin/sh\n", 0, 0),
            ("odd", 0o100644, b"abcde", 0, 0),
        ]
        archive = h.cpio_newc(entries)
        self.assertEqual(len(archive) % 4, 0)
        self.assertEqual(parse_newc(archive), entries)

    def test_reproducible(self):
        entries = [("init", 0o100755, b"x", 0, 0)]
        self.assertEqual(h.cpio_newc(entries), h.cpio_newc(entries))

    def test_initramfs_carries_init_busybox_and_modules(self):
        with tempfile.TemporaryDirectory() as d:
            bb, ko = Path(d, "busybox"), Path(d, "e1000.ko")
            bb.write_bytes(b"BB")
            ko.write_bytes(b"KO")
            archive = gzip.decompress(h.build_initramfs(bb, [ko]))
        names = {n: (m, data) for n, m, data, _, _ in parse_newc(archive)}
        self.assertEqual(names["bin/busybox"], (0o100755, b"BB"))
        self.assertEqual(names["lib/modules/e1000.ko"], (0o100644, b"KO"))
        self.assertTrue(names["init"][1].startswith(b"#!/bin/busybox sh"))
        self.assertIn("dev/console", names)


class PcapTest(unittest.TestCase):

    def test_echo_frames_found_with_lengths(self):
        frames = [
            echo_frame("192.0.2.1", "192.0.2.2", 8),
            echo_frame("192.0.2.2", "192.0.2.1", 0),
            b"\xff" * 60,
            # IPv4 ICMP whose IHL claims 60 bytes of header in a 42-byte frame.
            echo_frame("192.0.2.1", "192.0.2.2", 8, payload=0)[:14]
            + b"\x4f"
            + echo_frame("192.0.2.1", "192.0.2.2", 8, payload=0)[15:],
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "x.pcap")
            p.write_bytes(pcap(frames))
            echoes = h.icmp_echoes(h.read_pcap(p))
        self.assertEqual(
            echoes,
            [("192.0.2.1", "192.0.2.2", 8, 98), ("192.0.2.2", "192.0.2.1", 0, 98)],
        )

    def test_empty_file_has_no_frames(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "x.pcap")
            p.write_bytes(b"")
            self.assertEqual(h.read_pcap(p), [])

    def test_not_a_pcap_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "x.pcap")
            p.write_bytes(b"\0" * 40)
            with self.assertRaises(h.HarnessError):
                h.read_pcap(p)


class TraceTest(unittest.TestCase):

    LINES = [
        "2026-09-24T23:20:21.497100Z memory_region_ops_write cpu 0 mr 0x1 addr 0x70"
        " value 0x8f size 1 name 'rtc-index'\n",
        "2026-09-24T23:20:22.000001Z memory_region_ops_write cpu 0 mr 0x2 addr"
        " 0xfeb80000 value 0x4000000 size 4 name 'e1000-mmio'\n",
        "2026-09-24T23:20:22.000002Z memory_region_ops_read cpu 0 mr 0x2 addr"
        " 0xfeb80008 value 0x80080783 size 4 name 'e1000-mmio'\n",
        "2026-09-24T23:20:22.000003Z memory_region_ops_read cpu 0 mr 0x3 addr 0xc000"
        " value 0x0 size 4 name 'e1000-io'\n",
        "2026-09-24T23:20:22.000004Z pci_cfg_write e1000 00:01.0 @0x4 <- 0x107\n",
        "2026-09-24T23:20:22.000005Z pci_cfg_write virtio-net-pci 00:01.0 @0x4 <- 0x7\n",
        "2026-09-24T23:20:22.000006Z e1000x_link_negotiation_done Auto negotiation"
        " is completed\n",
        "memory_region_ops_write cpu 0 mr 0x2 addr 0xfeb80000 value 0x0 size 4"
        " name 'e1000-mmio'\n",
        "12345@1695600000.123456:memory_region_ops_read cpu 0 mr 0x2 addr 0xfeb80010"
        " value 0x0 size 4 name 'e1000-mmio'\n",
        "2026-09-24T23:20:22.000007Z memory_region_ops_write cpu 0 mr 0x2 addr"
        " 0xfeb80014 value 0x1 size 4 name 'e1000-mmio'\n",
    ]

    def test_counts_and_keeps_only_e1000_lines(self):
        with tempfile.TemporaryDirectory() as d:
            raw, out = Path(d, "raw.log"), Path(d, "out.log")
            raw.write_text("".join(self.LINES))
            counts = h.filter_trace(raw, out)
            kept = out.read_text().splitlines(keepends=True)
        self.assertEqual(
            counts,
            {
                "mmio_read": 2,
                "mmio_write": 3,
                "eeprom": 2,
                "io": 1,
                "pci_cfg": 1,
                "model_event": 1,
            },
        )
        self.assertEqual(kept, [self.LINES[i] for i in (1, 2, 3, 4, 6, 7, 8, 9)])


class GuestChannelTest(unittest.TestCase):

    def _guest(self, d: str):
        g = h.Guest("dut", ["true"], Path(d))
        g.sock, other = socket.socketpair()
        return g, other

    def test_broken_channel_is_a_guest_death_and_is_logged(self):
        with tempfile.TemporaryDirectory() as d:
            g, other = self._guest(d)
            other.close()
            with self.assertRaises(h.GuestError):
                g.run("true", timeout=2)
            self.assertIn("command channel failed", g.dead)
            g.sock.close()
            g.cmdlog.close()
            logged = Path(d, "dut-cmds.jsonl").read_text()
        self.assertIn('"cmd": "true"', logged)

    def test_self_test_on_an_already_dead_guest_fails(self):
        with tempfile.TemporaryDirectory() as d:
            g, other = self._guest(d)
            g.dead = "dut: no answer before the timeout"
            checks = h.expect_dead(g, "sleep 600", 5, "no answer before the timeout")
            other.close()
            g.sock.close()
            g.cmdlog.close()
        self.assertEqual(len(checks), 1)
        self.assertFalse(checks[0][1])


class RunValidationTest(unittest.TestCase):

    def _args(self, d: Path, **over):
        k, bb, ko = Path(d, "bzImage"), Path(d, "busybox"), Path(d, "e1000.ko")
        for p in (k, bb, ko):
            p.write_bytes(b"x")
        argv = ["run", "--kernel", str(k), "--busybox", str(bb), "--module", str(ko)]
        argv += ["--driver", over.get("driver", "e1000"), "--out", str(Path(d, "run"))]
        argv += ["--qemu", over.get("qemu", "qemu-system-x86_64")]
        for s in over.get("scenarios", []):
            argv += ["--scenario", s]
        return argv

    def test_driver_without_module_is_a_setup_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(h.main(self._args(Path(d), driver="e1000_l02")), 2)
            self.assertFalse(Path(d, "run").exists())

    def test_unknown_scenario_is_a_setup_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(h.main(self._args(Path(d), scenarios=["nope"])), 2)

    def test_existing_run_directory_is_refused_even_empty(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "run").mkdir()
            self.assertEqual(h.main(self._args(Path(d))), 2)
            self.assertEqual(list(Path(d, "run").iterdir()), [])

    def test_missing_qemu_is_a_setup_error_before_the_run_directory(self):
        with tempfile.TemporaryDirectory() as d:
            argv = self._args(Path(d), qemu=str(Path(d, "no-such-qemu")))
            self.assertEqual(h.main(argv), 2)
            self.assertFalse(Path(d, "run").exists())


def mmio(t: float, rw: str, reg: str, value: int) -> "h.Access":
    return h.Access(t, "mmio", rw, h.REG[reg], value)


class DecodeTest(unittest.TestCase):

    LINES = [
        "2026-09-25T00:02:43.166173Z memory_region_ops_write cpu 1 mr 0x1 addr"
        " 0xfebc00d8 value 0xffffffff size 4 name 'e1000-mmio'\n",
        "2026-09-25T00:02:43.176487Z memory_region_ops_write cpu 1 mr 0x2 addr 0xc000"
        " value 0x0 size 4 name 'e1000-io'\n",
        "2026-09-25T00:02:43.176517Z memory_region_ops_write cpu 1 mr 0x2 addr 0xc004"
        " value 0x4140240 size 4 name 'e1000-io'\n",
        "2026-09-25T00:02:41.469287Z pci_cfg_write e1000 00:01.0 @0x10 <- 0xffffffff\n",
        "2026-09-25T00:02:41.469300Z pci_cfg_read e1000 00:01.0 @0x0 -> 0x100e8086\n",
        "2026-09-25T00:02:41.457467Z e1000x_mac_indicate Indicating MAC to guest:"
        " 52:54:00:12:34:56\n",
        "12345@1695600000.123456:memory_region_ops_read cpu 0 mr 0x2 addr 0xfeb85400"
        " value 0x12005452 size 4 name 'e1000-mmio'\n",
    ]

    def test_decodes_each_kind(self):
        a = h.decode_trace(self.LINES)
        self.assertEqual(
            [(x.kind, x.rw, x.name, x.value) for x in a],
            [
                ("mmio", "w", "IMC", 0xFFFFFFFF),
                ("io-addr", "w", "IOADDR", 0),
                ("io", "w", "CTRL", 0x4140240),
                ("cfg", "w", "cfg@0x10", 0xFFFFFFFF),
                ("cfg", "r", "cfg@0x00", 0x100E8086),
                ("event", "", "e1000x_mac_indicate", None),
                ("mmio", "r", "RAL[0]", 0x12005452),
            ],
        )
        self.assertAlmostEqual(a[0].t, 1790294563.166173, places=5)
        self.assertAlmostEqual(a[-1].t, 1695600000.123456, places=5)

    def test_io_data_before_any_address_has_no_register(self):
        line = (
            "2026-09-25T00:02:43.1Z memory_region_ops_read cpu 1 mr 0x2 addr 0xc004"
            " value 0x0 size 4 name 'e1000-io'\n"
        )
        (a,) = h.decode_trace([line])
        self.assertEqual((a.kind, a.reg, a.name), ("io", None, "?"))


class LabelTest(unittest.TestCase):

    def test_scenario_and_phase_priority(self):
        acc = [mmio(t, "w", "TDT", 1) for t in (1.0, 2.5, 3.5, 4.5, 9.0)]
        scen = [h.Window(0.5, 5.0, "01 smoke")]
        dut = [h.Window(2.0, 3.0, "dut#1 ping")]
        peer = [h.Window(2.0, 4.0, "peer#1 ping")]
        host = [h.Window(4.2, 4.8, "host: hold 1 s")]
        got = h.label_accesses(acc, scen, [dut, peer, host])
        self.assertEqual(
            got,
            [
                ("01 smoke", "idle"),
                ("01 smoke", "dut#1 ping"),
                ("01 smoke", "peer#1 ping"),
                ("01 smoke", "host: hold 1 s"),
                ("outside", "idle"),
            ],
        )

    def test_labeled_trace_files(self):
        acc = [mmio(1.0, "w", "TDT", 1), mmio(1.1, "w", "TDT", 2)]
        with tempfile.TemporaryDirectory() as d:
            j, s = Path(d, "t.jsonl.gz"), Path(d, "p.json")
            h.write_labeled_trace(acc, [("01 smoke", "idle")] * 2, j, s)
            rows = [json.loads(x) for x in gzip.decompress(j.read_bytes()).splitlines()]
            summary = json.loads(s.read_text())
        self.assertEqual(rows[1]["name"], "TDT")
        self.assertEqual(rows[1]["value"], "0x2")
        self.assertEqual(summary["01 smoke"][0]["ops"], {"w TDT": 2})


class TraceRulesTest(unittest.TestCase):

    GOOD = [
        mmio(1.0, "w", "CTRL", h.CTRL_RST),
        mmio(1.005, "r", "STATUS", 0),
        mmio(1.1, "w", "RDLEN", 4096),
        mmio(1.1, "w", "RDBAL", 0x1000),
        mmio(1.1, "w", "RDH", 0),
        mmio(1.1, "w", "RDT", 255),
        mmio(1.2, "w", "RCTL", h.EN),
        mmio(1.3, "w", "RDT", 3),
        mmio(1.3, "w", "ITR", 195),
    ]

    def failed(self, accesses):
        checks, _ = h.trace_rules(accesses)
        return [name.split(" (", maxsplit=1)[0] for name, ok, _ in checks if not ok]

    def test_a_well_behaved_trace_passes(self):
        self.assertEqual(self.failed(self.GOOD), [])

    def test_each_rule_catches_its_violation(self):
        cases = {
            "each CTRL.RST write is followed by at least 1 us before the next register"
            " access": [
                mmio(1.0, "w", "CTRL", h.CTRL_RST),
                mmio(1.0, "r", "STATUS", 0),
            ],
            "RDLEN and TDLEN are written as nonzero multiples of 128": [
                mmio(1.0, "w", "RDLEN", 255 * 16)
            ],
            "RDBAL and TDBAL are written 16-byte aligned": [
                mmio(1.0, "w", "TDBAL", 0x1008)
            ],
            "every RDT and TDT write stays inside the ring": [
                mmio(1.0, "w", "TDLEN", 4096),
                mmio(1.1, "w", "TDT", 256),
            ],
            "RDH and TDH are written only while the receiver or transmitter"
            " is disabled": [
                mmio(1.0, "w", "RCTL", h.EN),
                mmio(1.1, "w", "RDH", 0),
            ],
            "ITR is written with its reserved bits 31:16 clear": [
                mmio(1.0, "w", "ITR", 0x10000)
            ],
        }
        for rule, trace in cases.items():
            with self.subTest(rule=rule):
                self.assertEqual(self.failed(trace), [rule])

    def test_reset_returns_lengths_and_enables_to_power_on_values(self):
        trace = [
            mmio(1.0, "w", "RCTL", h.EN),
            mmio(1.0, "w", "RDLEN", 4096),
            h.Access(2.0, "io", "w", h.REG["CTRL"], h.CTRL_RST),
            mmio(2.1, "w", "RDH", 0),
            mmio(2.1, "w", "RDT", 0),
            mmio(2.1, "w", "RDT", 5),
        ]
        self.assertEqual(
            self.failed(trace), ["every RDT and TDT write stays inside the ring"]
        )
        _, obs = h.trace_rules(trace)
        self.assertEqual(obs["resets_by_window"], {"mmio": 0, "io": 1})

    def test_tail_wraps(self):
        acc = [mmio(t, "w", "RDT", v) for t, v in enumerate((250, 254, 2, 100, 255, 1))]
        self.assertEqual(h.tail_wraps(acc, h.REG["RDT"]), 2)

    def test_tail_resets_and_new_rings_are_not_wraps(self):
        acc = [
            mmio(1, "w", "RDLEN", 4096),
            mmio(2, "w", "RDT", 254),
            mmio(3, "w", "RDT", 0),
            mmio(4, "w", "CTRL", h.CTRL_RST),
            mmio(5, "w", "RDT", 254),
            mmio(6, "w", "RDLEN", 4096),
            mmio(7, "w", "RDT", 100),
            mmio(8, "w", "RDT", 0),
            mmio(9, "w", "RDT", 3),
        ]
        # Only 100 -> (0) -> 3 is a wrap: the 0 is skipped, the reset and the length
        # write each start a new ring.
        self.assertEqual(h.tail_wraps(acc, h.REG["RDT"]), 1)

    def test_one_microsecond_at_epoch_scale_is_not_short(self):
        t = 1790294563.166173
        trace = [mmio(t, "w", "CTRL", h.CTRL_RST), mmio(t + 1e-6, "r", "STATUS", 0)]
        self.assertEqual(self.failed(trace), [])


class DeferredTest(unittest.TestCase):

    def post(self, accesses, d="."):
        return h.Post(accesses, {1: h.Window(10.0, 20.0, "01 itr")}, Path(d))

    def test_itr_readback_follows_writes_and_resets(self):
        base = [mmio(1.0, "w", "ITR", 195), mmio(11.0, "r", "ITR", 195)]
        self.assertTrue(h.itr_readback(self.post(base), 1)[0])
        reset = [
            mmio(1.0, "w", "ITR", 195),
            mmio(2.0, "w", "CTRL", h.CTRL_RST),
            mmio(11.0, "r", "ITR", 195),
        ]
        self.assertFalse(h.itr_readback(self.post(reset), 1)[0])
        self.assertFalse(h.itr_readback(self.post(base[:1]), 1)[0])

    def test_busy_before(self):
        acc = [mmio(9.5 + i / 100, "w", "TDT", i) for i in range(12)]
        self.assertTrue(h.busy_before(10.0, ("TDT",))(self.post(acc), 1)[0])
        self.assertFalse(h.busy_before(10.0, ("TDT", "RDT"))(self.post(acc), 1)[0])

    def test_dut_sent_sizes(self):
        frames = [
            echo_frame("192.0.2.1", "192.0.2.2", t, n - 42)
            for n in (60, 61, 1513, 1514)
            for t in (0, 8)
        ]
        with tempfile.TemporaryDirectory() as d:
            Path(d, "peer.pcap").write_bytes(pcap(frames))
            self.assertTrue(h.dut_sent_sizes(self.post([], d), 1)[0])
            Path(d, "peer.pcap").write_bytes(pcap(frames[:-1]))
            ok, detail = h.dut_sent_sizes(self.post([], d), 1)
        self.assertFalse(ok)
        self.assertIn("(8, 1514)", detail)


class DeferredMoreTest(unittest.TestCase):

    def ev(self, t: float) -> "h.Access":
        return h.Access(t, "event", "", None, None, "e1000x_rx_flt_ucast_match x")

    def post(self, accesses):
        return h.Post(accesses, {1: h.Window(0.0, 100.0, "01 x")}, Path("."))

    def test_no_leftovers_bound(self):
        acc = [self.ev(1.0 + i / 100) for i in range(5)]
        self.assertFalse(h.no_leftovers(0.5, 2.0)(self.post(acc), 1)[0])
        self.assertTrue(h.no_leftovers(0.5, 2.0)(self.post(acc[:4]), 1)[0])
        self.assertTrue(h.no_leftovers(5.0, 6.0)(self.post(acc), 1)[0])

    def test_stalled_needs_frames_and_no_tail_write(self):
        mask = mmio(1.2, "w", "IMC", 0xFFFFFFFF)
        acc = [mask, self.ev(1.5), self.ev(1.6)]
        self.assertTrue(h.stalled(1.0, 1.3, 2.0)(self.post(acc), 1)[0])
        tail = acc + [mmio(1.7, "w", "RDT", 5)]
        self.assertFalse(h.stalled(1.0, 1.3, 2.0)(self.post(tail), 1)[0])
        self.assertFalse(h.stalled(1.0, 1.3, 2.0)(self.post([mask]), 1)[0])

    def test_stalled_starts_at_the_mask_write(self):
        acc = [
            mmio(1.1, "w", "RDT", 5),
            mmio(1.2, "w", "IMC", 0xFFFFFFFF),
            self.ev(1.5),
        ]
        self.assertTrue(h.stalled(1.0, 1.3, 2.0)(self.post(acc), 1)[0])
        ok, detail = h.stalled(1.0, 1.3, 2.0)(self.post(acc[:1] + acc[2:]), 1)
        self.assertFalse(ok)
        self.assertIn("no IMC write", detail)

    def test_lsc_counts_only_after_the_toggle(self):
        acc = [mmio(1.0, "r", "ICR", h.ICR_LSC), mmio(5.0, "r", "ICR", 0x84)]
        self.assertEqual(h.icr_lsc(3.0)(self.post(acc), 1)[1].split()[0], "1")

    def test_itr_writes_after_the_last_reset(self):
        acc = [
            mmio(1.0, "w", "ITR", 976),
            mmio(2.0, "w", "CTRL", h.CTRL_RST),
            mmio(3.0, "w", "ITR", 195),
            mmio(4.0, "r", "ITR", 195),
        ]
        ok, detail = h.itr_writes(3.5, 4.5)(self.post(acc), 1)
        self.assertTrue(ok)
        self.assertIn("[195]", detail)

    def test_itr_writes_stop_at_the_harness_read_back(self):
        acc = [
            mmio(0.5, "r", "ITR", 0),
            mmio(1.0, "w", "ITR", 195),
            mmio(2.0, "w", "ITR", 976),
            mmio(3.0, "r", "ITR", 976),
            mmio(4.0, "w", "CTRL", h.CTRL_RST),
        ]
        ok, detail = h.itr_writes(2.5, 3.5)(self.post(acc), 1)
        self.assertTrue(ok)
        self.assertIn("2 writes, values [195, 976]", detail)
        ok, detail = h.itr_writes(5.0, 6.0)(self.post(acc), 1)
        self.assertFalse(ok)
        self.assertIn("no harness ITR read", detail)


class SetLinkTest(unittest.TestCase):

    class DeadQmp:

        def execute(self, *_, **__):
            raise BrokenPipeError("broken pipe")

    def ctx(self, d: str, exited: bool):
        g = h.Guest("dut", ["true"], Path(d))
        g.proc = subprocess.Popen(["true"] if exited else ["sleep", "30"])
        if exited:
            g.proc.wait()
        return h.Ctx(g, g, self.DeadQmp(), "e1000", Path(d)), g

    def test_monitor_failure_after_qemu_exit_is_a_guest_failure(self):
        with tempfile.TemporaryDirectory() as d:
            c, g = self.ctx(d, exited=True)
            with self.assertRaises(h.GuestError):
                c.set_link(False)
            g.cmdlog.close()
        self.assertEqual(c.actions[0]["action"], "set_link down")

    def test_monitor_failure_with_qemu_running_is_a_harness_error(self):
        with tempfile.TemporaryDirectory() as d:
            c, g = self.ctx(d, exited=False)
            with self.assertRaises(h.HarnessError):
                c.set_link(True)
            g.proc.kill()
            g.proc.wait()
            g.cmdlog.close()


class KernelLogTest(unittest.TestCase):

    def test_flags_faults_not_link_messages(self):
        log = "\n".join(
            [
                "[ 6.5] e1000: eth0 NIC Link is Up 1000 Mbps Full Duplex",
                "[ 6.6] e1000 0000:00:01.0 eth0: Detected Tx Unit Hang",
                "[ 7.0] e1000 0000:00:01.0 eth0: NETDEV WATCHDOG: CPU: 0: transmit queue"
                " 0 timed out 5947 ms",
                "[ 8.0] WARNING: CPU: 1 PID: 9 at net/core/dev.c:1 x",
                "[ 9.0] e1000: eth0 NIC Link is Down",
            ]
        )
        self.assertEqual(len(h.kernel_log_problems(log)), 3)


class SuiteArgsTest(unittest.TestCase):

    def test_all_expands_to_the_suite_without_self_tests(self):
        self.assertNotIn("selftest-hang", h.SUITE)
        self.assertEqual(h.SUITE[0], "smoke")
        self.assertEqual(len(h.SUITE), 10)

    def test_main_expands_all_in_place(self):
        seen = {}
        with mock.patch.object(
            h, "run", lambda args: seen.setdefault("s", args.scenario)
        ):
            argv = ["run", "--kernel", "k", "--module", "e1000.ko", "--driver", "e1000"]
            h.main(
                argv
                + ["--out", "o", "--scenario", "selftest-hang", "--scenario", "all"]
            )
        self.assertEqual(seen["s"], ["selftest-hang"] + h.SUITE)


if __name__ == "__main__":
    unittest.main()
