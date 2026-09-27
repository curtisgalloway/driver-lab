# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Contract failures must fail on metadata, not on the driver's test outcome."""

import copy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from test_sweep import ROOT, SCRIPTS, check
import contract_check as contract
import deployment

FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(FIXTURES))
import contract_stub as stub  # pylint: disable=wrong-import-position

sys.path.insert(0, str(ROOT / "evals/e1000/harness"))
import l02harness as harness  # pylint: disable=wrong-import-position


class ContractTests(unittest.TestCase):
    """Check both the native QEMU data and neutral stub through the same CLI."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def cli(self, *args, expected=0):
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "contract_check.py"),
                "--deployment",
                str(deployment.REFERENCE),
                "--json",
                *map(str, args),
            ],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        self.assertEqual(proc.stderr, "")
        report = json.loads(proc.stdout)
        self.assertEqual(report["ok"], expected == 0)
        return report

    def source_file(self, data):
        path = self.root / "source.json"
        path.write_text(json.dumps(data))
        return path

    def harness_failure(self, mode):
        """Run actual harness control flow with guest/process entry points mocked."""
        kernel, busybox, module = [
            self.root / name for name in ("kernel", "busybox", "e1000.ko")
        ]
        for path in (kernel, busybox, module):
            path.write_bytes(b"test input")
        args = SimpleNamespace(
            out=self.root / mode,
            kernel=kernel,
            busybox=busybox,
            module=[module],
            driver="e1000",
            scenario=["itr"],
            boot_timeout=1,
        )
        peer, dut = mock.Mock(), mock.Mock()
        peer.dead = False
        peer.run.return_value = (0, "")
        if mode == "boot":
            peer.start.side_effect = harness.HarnessError("startup failed")
        elif mode == "insmod":
            dut.run.side_effect = [
                (0, ""),
                harness.GuestError("guest died during insmod"),
            ]
        else:
            dut.run.side_effect = harness.GuestError("guest died before boot log")
        identity = contract.read_json(FIXTURES / "qemu-run/identities.json")
        with mock.patch.object(harness, "resolve_host"), mock.patch.object(
            harness, "build_initramfs", return_value=b"test image"
        ), mock.patch.object(
            harness, "identities", return_value=identity
        ), mock.patch.object(
            harness, "qemu_argv", return_value=[]
        ), mock.patch.object(
            harness, "Guest", side_effect=[peer, dut]
        ), mock.patch.object(
            harness, "Qmp"
        ), mock.patch.object(
            harness, "post_process", return_value=[]
        ), contextlib.redirect_stdout(
            io.StringIO()
        ):
            code = harness.run(args)
        self.assertEqual(code, 1 if mode == "insmod" else 2)
        if mode == "insmod":
            self.assertEqual(dut.run.call_args.args, ("insmod /lib/modules/e1000.ko",))
        return args.out

    def test_actual_harness_failures_are_valid_contracts(self):
        for mode, group, outcome in (
            ("boot", "boot", "ERROR"),
            ("insmod", "itr", "FAIL"),
            ("before-scenario", "between scenarios", "ERROR"),
        ):
            with self.subTest(mode=mode):
                directory = self.harness_failure(mode)
                recorded = contract.read_json(directory / "verdicts.json")
                self.assertEqual(recorded["results"][0]["scenario"], group)
                self.assertEqual(recorded["results"][0]["checks"], [])
                report = self.cli("--run-dir", directory)
                self.assertEqual(report["checks"]["fixture"]["overall"], outcome)

    def test_undeclared_scenario_rejected_for_both_identity_shapes(self):
        for native in (True, False):
            with self.subTest(native=native):
                directory = stub.write_run(self.root / str(native))
                if native:
                    (directory / "identities.json").write_bytes(
                        (FIXTURES / "qemu-run/identities.json").read_bytes()
                    )
                path = directory / "verdicts.json"
                document = contract.read_json(path)
                document["results"].append(
                    {
                        "scenario": "smoke",
                        "verdict": "PASS",
                        "checks": [{"check": "extra", "ok": True}],
                    }
                )
                path.write_text(json.dumps(document))
                self.cli("--run-dir", directory, expected=1)

    def test_error_groups_cannot_hide_missing_scenario_or_execution(self):
        directory = stub.write_run(self.root / "error-groups")
        path = directory / "verdicts.json"
        for group in ("boot", "between scenarios", "trace", "capture"):
            for outcome in ("PASS", "ERROR"):
                with self.subTest(group=group, outcome=outcome):
                    checks = (
                        [] if outcome == "ERROR" else [{"check": "extra", "ok": True}]
                    )
                    path.write_text(
                        json.dumps(
                            {
                                "overall": outcome,
                                "results": [
                                    {
                                        "scenario": group,
                                        "verdict": outcome,
                                        "checks": checks,
                                    }
                                ],
                            }
                        )
                    )
                    valid = (
                        group in {"boot", "between scenarios"} and outcome == "ERROR"
                    )
                    self.cli("--run-dir", directory, expected=0 if valid else 1)
        document = contract.read_json(FIXTURES / "qemu-run/verdicts.json")
        document["overall"] = "ERROR"
        document["results"].append(
            {"scenario": "boot", "verdict": "ERROR", "checks": []}
        )
        path.write_text(json.dumps(document))
        self.cli("--run-dir", directory, expected=1)

    def test_manifest_constructor_errors_return_json(self):
        path = self.root / "invalid.yaml"
        for content in ("version: 2026-99-99\nplugins: []\n", "version: [\n"):
            path.write_text(content)
            self.cli("--deployment", path, expected=1)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "sweep.py"),
                    str(ROOT / "evals/e1000"),
                    "--deployment",
                    str(path),
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stderr, "")
            self.assertFalse(json.loads(proc.stdout)["ok"])

    def test_capture_is_limited_to_documented_context(self):
        for native in (True, False):
            for scenario in ("itr", "smoke"):
                with self.subTest(native=native, scenario=scenario):
                    directory = stub.write_run(
                        self.root / f"capture-{native}-{scenario}"
                    )
                    identity = (
                        contract.read_json(FIXTURES / "qemu-run/identities.json")
                        if native
                        else stub.identity()
                    )
                    conditions = identity if native else identity["conditions"]
                    conditions["scenarios"] = [scenario]
                    (directory / "identities.json").write_text(json.dumps(identity))
                    path = directory / "verdicts.json"
                    document = contract.read_json(path)
                    document["results"][0]["scenario"] = scenario
                    document["results"].append(
                        {
                            "scenario": "capture",
                            "verdict": "PASS",
                            "checks": [{"check": "captured", "ok": True}],
                        }
                    )
                    path.write_text(json.dumps(document))
                    self.cli(
                        "--run-dir",
                        directory,
                        expected=1 if native and scenario == "itr" else 0,
                    )

    def test_json_usage_errors(self):
        for args in (("--run-dir",), ("--unknown",), ("--deployment",)):
            with self.subTest(args=args):
                report = self.cli(*args, expected=2)
                self.assertEqual(report["version"], 1)
                self.assertEqual(report["checks"], {})
                self.assertTrue(report["findings"])
        for args in (("--deployment",), ("--unknown",), ()):
            with self.subTest(sweep_args=args):
                proc = subprocess.run(
                    [sys.executable, str(SCRIPTS / "sweep.py"), "--json", *args],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stderr, "")
                self.assertFalse(json.loads(proc.stdout)["ok"])

    def test_reference_adapter_and_native_qemu(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "pinned_file_adapter.py"),
                str(ROOT / "evals/e1000/sources.yaml"),
                "harness",
                "--root",
                str(ROOT),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = self.cli(
            "--source-json",
            self.source_file(json.loads(proc.stdout)),
            "--run-dir",
            FIXTURES / "qemu-run",
        )
        self.assertEqual(report["checks"]["fixture"]["verdicts"], {"PASS": 19})

    def test_successful_stub_processes(self):
        proc = subprocess.run(
            [sys.executable, str(FIXTURES / "contract_stub.py")],
            capture_output=True,
            text=True,
            check=True,
        )
        path = self.source_file(json.loads(proc.stdout))
        proc = subprocess.run(
            [
                sys.executable,
                str(FIXTURES / "contract_stub.py"),
                "--run-dir",
                str(self.root / "run"),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        directory = json.loads(proc.stdout)["run_dir"]
        self.cli("--source-json", path, "--run-dir", directory)

    def test_each_missing_source_provenance_field(self):
        for field in stub.SOURCE_FIELDS:
            with self.subTest(field=field):
                path = self.source_file(stub.omit(stub.source(), field))
                report = self.cli("--source-json", path, expected=1)
                self.assertTrue(report["findings"])

    def test_each_missing_backend_provenance_field(self):
        for number, field in enumerate(stub.FIXTURE_FIELDS):
            with self.subTest(field=field):
                directory = stub.write_run(self.root / str(number), field)
                self.cli("--run-dir", directory, expected=1)

    def test_each_missing_native_qemu_provenance_field(self):
        identity = contract.read_json(FIXTURES / "qemu-run/identities.json")
        paths = [
            (key,)
            for key in (
                "qemu_version",
                "sha256",
                "driver",
                "accel",
                "scenarios",
                "dut_mem",
                "host_kernel",
                "python",
            )
        ]
        paths += [
            ("sha256", key)
            for key in (
                "qemu",
                "harness:l02harness.py",
                "harness:guest-init.sh",
                "kernel",
                "initramfs",
                "busybox",
            )
        ]
        for parts in paths:
            with self.subTest(field=parts):
                value = copy.deepcopy(identity)
                parent = value if len(parts) == 1 else value[parts[0]]
                del parent[parts[-1]]
                with self.assertRaises(check.Invalid):
                    contract.fixture_identity(value)

    def test_malformed_source_data_and_null_hash(self):
        for field, value in [
            ("sha256", None),
            ("sha256", "abc"),
            ("status", []),
            ("checked", "yesterday"),
            ("version", ""),
            ("provenance", None),
        ]:
            data = stub.source()
            data[field] = value
            with self.subTest(field=field):
                self.cli("--source-json", self.source_file(data), expected=1)
        for state in ("blocked", "unknown"):
            data = stub.source()
            data.update(status=state, sha256=None)
            report = self.cli("--source-json", self.source_file(data))
            self.assertEqual(report["checks"]["source"]["status"], state)

    def test_fail_error_are_valid_contracts_but_not_passes(self):
        directory = stub.write_run(self.root / "run")
        path = directory / "verdicts.json"
        for outcome in ("FAIL", "ERROR"):
            path.write_text(
                json.dumps(
                    {
                        "overall": outcome,
                        "results": [
                            {
                                "scenario": "itr",
                                "verdict": outcome,
                                "checks": [{"check": "insmod", "verdict": outcome}],
                            }
                        ],
                    }
                )
            )
            report = self.cli("--run-dir", directory)
            self.assertEqual(report["checks"]["fixture"]["overall"], outcome)
            self.assertEqual(report["checks"]["fixture"]["verdicts"], {outcome: 1})

    def test_invalid_hash_conditions_and_multiple_requested_scenarios(self):
        for field, value in (
            ("harness_sha256", None),
            ("kernel_sha256", "short"),
            ("image_sha256", True),
            ("conditions", {}),
            ("conditions", {"scenarios": ["itr", "smoke"]}),
        ):
            with self.subTest(field=field, value=value):
                identity = stub.identity()
                identity[field] = value
                with self.assertRaises(check.Invalid):
                    contract.fixture_identity(identity)
        native = contract.read_json(FIXTURES / "qemu-run/identities.json")
        native["scenarios"] = ["itr", "smoke"]
        with self.assertRaisesRegex(check.Invalid, "one scenario"):
            contract.fixture_identity(native)

    def test_malformed_or_contradictory_verdicts(self):
        directory = stub.write_run(self.root / "run")
        path = directory / "verdicts.json"
        baseline = contract.read_json(path)
        mutations = [
            lambda d: d.update(overall="SKIP"),
            lambda d: d.update(results=[]),
            lambda d: d["results"].append(copy.deepcopy(d["results"][0])),
            lambda d: d["results"][0].update(checks=[]),
            lambda d: d["results"][0]["checks"][0].update(verdict="FAIL"),
            lambda d: d["results"][0]["checks"][0].update(ok="yes"),
            lambda d: d["results"][0]["checks"].append(
                copy.deepcopy(d["results"][0]["checks"][0])
            ),
            lambda d: d["results"][0]["checks"][0].pop("check"),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(case=number):
                document = copy.deepcopy(baseline)
                mutate(document)
                path.write_text(json.dumps(document))
                self.cli("--run-dir", directory, expected=1)

    def test_missing_files_bad_json_duplicate_keys_and_skill(self):
        self.cli("--source-json", self.root / "absent", expected=3)
        self.cli("--run-dir", self.root, expected=3)
        path = self.root / "source.json"
        for text in ("{", '{"id": 1, "id": 2}'):
            path.write_text(text)
            self.cli("--source-json", path, expected=1)
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "contract_check.py"), "--skill"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertTrue(proc.stdout.startswith("---\nname:"))

    def test_contract_reads_only_and_never_executes_manifest_commands(self):
        manifest = check.read_yaml(deployment.REFERENCE)
        marker = self.root / "should-not-exist"
        for entry in manifest["plugins"]:
            if entry["kind"] in {"source", "fixture"}:
                entry["command"] = ["touch", str(marker)]
        path = self.root / "manifest.yaml"
        path.write_text(check.yaml.safe_dump(manifest))
        fixture = FIXTURES / "qemu-run"
        before = {p.name: p.read_bytes() for p in fixture.iterdir()}
        self.cli("--deployment", path, "--run-dir", fixture)
        self.assertEqual(before, {p.name: p.read_bytes() for p in fixture.iterdir()})
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
