# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Unit and integration tests for utilities/hwspecs-audit."""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


TESTS_DIR = Path(__file__).resolve().parent
UTILITIES_DIR = TESTS_DIR.parent
REPO_ROOT = UTILITIES_DIR.parent
WRAPPER_PATH = UTILITIES_DIR / "hwspecs-audit"


def load_wrapper_module():
    """Import `utilities/hwspecs-audit` as a Python module for unit testing."""
    loader = importlib.machinery.SourceFileLoader("hwspecs_audit", str(WRAPPER_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    spec.loader.exec_module(module)
    return module


def find_bringup_kit() -> Path | None:
    """Locate a sibling `bringup-kit` checkout if present on this machine."""
    env_dir = os.environ.get("BRINGUP_KIT_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()
    for parent in REPO_ROOT.parents:
        candidate = parent / "bringup-kit"
        if (candidate / "bringupkit" / "audit.py").is_file() and (
            candidate / "tools" / "streamline_due.py"
        ).is_file():
            return candidate
    return None


hwspecs_audit = load_wrapper_module()


class HwspecsAuditTest(unittest.TestCase):
    """Comprehensive tests for `utilities/hwspecs-audit`."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="hwspecs-audit-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.run_store = self.tmp / "store"
        self.run_store.mkdir(parents=True, exist_ok=True)
        self.work_dir = self.tmp / "workspace"
        self.specs_dir = self.work_dir / "specs"
        self.specs_dir.mkdir(parents=True, exist_ok=True)
        (self.specs_dir / "board-specs.yaml").write_text(
            "name: gw9200-specs\nlayer: board\n", encoding="utf-8"
        )
        self.spec_a = self.specs_dir / "gw9200-i2c.spec.yaml"
        self.spec_b = self.specs_dir / "gw9200-uart.spec.yaml"
        self.spec_a.write_text("kind: peripheral\nname: i2c_v1\n", encoding="utf-8")
        self.spec_b.write_text("kind: peripheral\nname: uart_v1\n", encoding="utf-8")

        self.fake_hwspecs = self.tmp / "fake_hwspecs.py"
        self._write_fake_hwspecs()

    def _write_fake_hwspecs(self) -> None:
        """Create a controllable fake `hwspecs` script supporting text, `--json`, and `--diag-out`."""
        script = '''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if "--version" in args or "-V" in args:
    print("hwspecs 0.4.0 (abc1234def56)")
    sys.exit(0)

diag_out = None
json_mode = False
filtered = []
i = 0
while i < len(args):
    if args[i] == "--diag-out" and i + 1 < len(args):
        diag_out = args[i + 1]
        i += 2
    elif args[i].startswith("--diag-out="):
        diag_out = args[i].split("=", 1)[1]
        i += 1
    elif args[i] == "--json":
        json_mode = True
        i += 1
    else:
        filtered.append(args[i])
        i += 1

# Record exact received argv so tests can prove argv was not mutated by default.
argv_log = os.environ.get("FAKE_HWSPECS_ARGV_LOG")
if argv_log:
    with open(argv_log, "w", encoding="utf-8") as fh:
        json.dump(sys.argv[1:], fh)

mode = os.environ.get("FAKE_HWSPECS_MODE", "pass")
subcmd = filtered[0] if filtered else "check"

if mode == "fail_text":
    # Emit standard text findings and stderr text without codes.
    print("specs/gw9200-i2c.spec.yaml:14:3: error: fact 'i2c_bus' cites invalid reg.bus 0x4000 in 'specs/gw9200-i2c.spec.yaml'")
    print("specs/gw9200-uart.spec.yaml:22:5: error: unknown citation repo 'vendor-bsp' at line 88")
    print("specs/gw9200-uart.spec.yaml:30:1: warning: todo item missing tracking reference")
    if subcmd == "resolve":
        print("12 anchor(s) resolved, 2 skipped")
    if diag_out:
        payload = {
            "ok": False,
            "errors": 2,
            "warnings": 1,
            "resolved": 12 if subcmd == "resolve" else None,
            "skipped": 2 if subcmd == "resolve" else None,
            "findings": [
                {
                    "path": "specs/gw9200-i2c.spec.yaml",
                    "line": 14,
                    "column": 3,
                    "level": "error",
                    "code": "CHK-BUS-PROTOCOL",
                    "message": "fact 'i2c_bus' cites invalid reg.bus 0x4000",
                },
                {
                    "path": "specs/gw9200-uart.spec.yaml",
                    "line": 22,
                    "column": 5,
                    "level": "error",
                    "code": "CHK-CITATION",
                    "message": "unknown citation repo 'vendor-bsp' at line 88",
                },
                {
                    "path": "specs/gw9200-uart.spec.yaml",
                    "line": 30,
                    "column": 1,
                    "level": "warning",
                    "code": "CHK-TODO-TRACKING",
                    "message": "todo item missing tracking reference",
                },
            ],
        }
        with open(diag_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    sys.exit(1)

if mode == "fail_uart_only":
    if json_mode:
        payload = {
            "ok": False,
            "findings": [
                {
                    "path": "specs/gw9200-uart.spec.yaml",
                    "line": 25,
                    "column": 2,
                    "level": "error",
                    "code": "CHK-CITATION",
                    "message": "unknown citation repo 'other-bsp' at line 99",
                }
            ],
        }
        print(json.dumps(payload))
    else:
        print("specs/gw9200-uart.spec.yaml:25:2: error: unknown citation repo 'other-bsp' at line 99")
    sys.exit(1)

if mode == "fail_outside_path":
    leaked = "/home" + "/alice/private_dir/secret.yaml"
    print(f"{leaked}:9:1: error: leaked path {leaked} with 0xdeadbeef")
    sys.exit(1)

if mode == "panic_100":
    sys.stderr.write("thread 'main' panicked at src/speccheck.rs:101:5: internal invariant failed\\n")
    sys.exit(100)

if mode == "internal_envelope":
    payload = {
        "ok": False,
        "error": "internal",
        "errors": 1,
        "warnings": 0,
        "findings": [
            {
                "path": "",
                "line": 0,
                "column": 0,
                "level": "error",
                "code": "INTERNAL-ERR",
                "message": "unexpected internal failure",
            }
        ],
    }
    print(json.dumps(payload))
    sys.exit(1)

if subcmd == "resolve":
    print("  claim: reset value is 0x0")
    print("18 anchor(s) resolved, 0 skipped")
else:
    print("OK: 2 specs checked")
if diag_out:
    with open(diag_out, "w", encoding="utf-8") as fh:
        json.dump({"ok": True, "errors": 0, "warnings": 0, "findings": []}, fh)
sys.exit(0)
'''
        self.fake_hwspecs.write_text(script, encoding="utf-8")
        self.fake_hwspecs.chmod(0o755)

    def _run_wrapper(
        self, *args: str, env_Middle: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "HWSPECS_RUNS": str(self.run_store),
        }
        if env_Middle:
            env.update(env_Middle)
        return subprocess.run(
            [sys.executable, str(WRAPPER_PATH), *args],
            cwd=self.work_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_slug_normalization_and_path_scrubbing(self) -> None:
        alice_home = "/home" + "/alice"
        bob_home = "/home" + "/bob"
        msg1 = (
            "fact 'gic_dist' cites unknown repo \"linux-bsp\" at line 42 (0x1000) "
            f"in {alice_home}/work/specs/rdo.spec.yaml"
        )
        msg2 = (
            "fact 'uart0' cites unknown repo \"vendor-tree\" at line 991 (0xff00_1234) "
            f"in {bob_home}/checkout/specs/uart.spec.yaml"
        )
        slug1 = hwspecs_audit.normalize_message_slug(msg1)
        slug2 = hwspecs_audit.normalize_message_slug(msg2)
        self.assertEqual(slug1, slug2)
        self.assertEqual(slug1, "msg-fact-cites-unknown-repo-at-line-in")
        self.assertNotIn("alice", slug1)
        self.assertNotIn("0x", slug1)
        self.assertNotIn("42", slug1)

        rel = hwspecs_audit.scrub_path(
            str(self.spec_a), [self.specs_dir], self.work_dir
        )
        self.assertEqual(rel, "gw9200-i2c.spec.yaml")

        ext = hwspecs_audit.scrub_path(
            f"{alice_home}/secret/outside.yaml", [self.specs_dir], self.work_dir
        )
        self.assertTrue(ext.startswith("<external>:"), ext)
        self.assertEqual(len(ext), len("<external>:") + 12)
        self.assertNotIn("alice", ext)

    def test_atomic_publish_idempotent_and_no_overwrite_conflict(self) -> None:
        target = self.run_store / "camp-1" / "audit" / "hwspecs" / "ev1-check.json"
        rec = {"schema": "hwspecs-diag-1", "event_id": "ev1", "ok": True}
        self.assertTrue(hwspecs_audit.atomic_publish(target, rec))
        # Publishing identical content is idempotent and returns False.
        self.assertFalse(hwspecs_audit.atomic_publish(target, rec))
        # Publishing conflicting content to the same target raises ValueError and preserves original.
        with self.assertRaises(ValueError):
            hwspecs_audit.atomic_publish(
                target, {"schema": "hwspecs-diag-1", "event_id": "ev1", "ok": False}
            )
        saved = json.loads(target.read_text(encoding="utf-8"))
        self.assertTrue(saved["ok"])

    def test_wrapper_preserves_argv_and_tees_output_in_text_mode(self) -> None:
        argv_log = self.tmp / "argv.json"
        res = self._run_wrapper(
            "--run",
            "camp-text",
            "--step",
            "resolve-step",
            "--",
            str(self.fake_hwspecs),
            "resolve",
            "specs",
            env_Middle={
                "FAKE_HWSPECS_MODE": "fail_text",
                "FAKE_HWSPECS_ARGV_LOG": str(argv_log),
            },
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("12 anchor(s) resolved, 2 skipped", res.stdout)
        self.assertIn("specs/gw9200-i2c.spec.yaml:14:3: error:", res.stdout)

        # Verify argv was not mutated (no --json or --diag-out injected by default).
        recorded_argv = json.loads(argv_log.read_text(encoding="utf-8"))
        self.assertEqual(recorded_argv, ["resolve", "specs"])

        diag_files = list(
            (self.run_store / "camp-text" / "audit" / "hwspecs").glob("*-resolve.json")
        )
        self.assertEqual(len(diag_files), 1)
        diag = json.loads(diag_files[0].read_text(encoding="utf-8"))
        self.assertEqual(diag["schema"], "hwspecs-diag-1")
        self.assertEqual(diag["tool_commit"], "abc1234def56")
        self.assertEqual(diag["root"], "gw9200-specs")
        self.assertEqual(diag["errors"], 2)
        self.assertEqual(diag["warnings"], 1)
        self.assertEqual(diag["anchors_resolved"], 12)
        self.assertEqual(diag["anchors_skipped"], 2)
        self.assertIn("gw9200-i2c.spec.yaml", diag["spec_hashes_before"])
        self.assertIn("gw9200-uart.spec.yaml", diag["spec_hashes_before"])

        # Ensure raw prose and paths are never stored in the receipt.
        raw_receipt_text = diag_files[0].read_text(encoding="utf-8")
        self.assertNotIn("vendor-bsp", raw_receipt_text)
        self.assertNotIn("0x4000", raw_receipt_text)
        for f in diag["findings"]:
            self.assertNotIn("message", f)
            self.assertTrue(f["code_or_slug"].startswith("msg-"))

    def test_wrapper_use_diag_out_extracts_finding_codes(self) -> None:
        res = self._run_wrapper(
            "--use-diag-out",
            "--",
            str(self.fake_hwspecs),
            "check",
            "specs",
            env_Middle={
                "HWSPECS_AUDIT_RUN": "camp-diag",
                "HWSPECS_AUDIT_STEP": "gate-check",
                "FAKE_HWSPECS_MODE": "fail_text",
            },
        )
        self.assertEqual(res.returncode, 1)
        # Human-readable stdout is still teed to caller.
        self.assertIn("specs/gw9200-i2c.spec.yaml:14:3: error:", res.stdout)

        diag_files = list(
            (self.run_store / "camp-diag" / "audit" / "hwspecs").glob("*-check.json")
        )
        self.assertEqual(len(diag_files), 1)
        diag = json.loads(diag_files[0].read_text(encoding="utf-8"))
        codes = {f["code_or_slug"] for f in diag["findings"]}
        self.assertEqual(codes, {"CHK-BUS-PROTOCOL", "CHK-CITATION", "CHK-TODO-TRACKING"})

    def test_external_path_scrubbing_and_tool_bug_candidate_detection(self) -> None:
        # 1. Outside path is hashed to <external>:<sha256[:12]>.
        self._run_wrapper(
            "--run",
            "camp-sec",
            "--",
            str(self.fake_hwspecs),
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "fail_outside_path"},
        )
        # 2. Exit 100 / panic sets tool_bug_candidate = True.
        self._run_wrapper(
            "--run",
            "camp-sec",
            "--",
            str(self.fake_hwspecs),
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "panic_100"},
        )
        # 3. Internal-error JSON envelope sets tool_bug_candidate = True.
        self._run_wrapper(
            "--run",
            "camp-sec",
            "--",
            str(self.fake_hwspecs),
            "--json",
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "internal_envelope"},
        )

        diag_files = sorted(
            (self.run_store / "camp-sec" / "audit" / "hwspecs").glob("*.json")
        )
        self.assertEqual(len(diag_files), 3)
        d0 = json.loads(diag_files[0].read_text(encoding="utf-8"))
        self.assertFalse(d0["tool_bug_candidate"])
        self.assertTrue(d0["findings"][0]["path"].startswith("<external>:"))
        self.assertNotIn("alice", diag_files[0].read_text(encoding="utf-8"))

        d1 = json.loads(diag_files[1].read_text(encoding="utf-8"))
        self.assertTrue(d1["tool_bug_candidate"])
        self.assertEqual(d1["exit_code"], 100)

        d2 = json.loads(diag_files[2].read_text(encoding="utf-8"))
        self.assertTrue(d2["tool_bug_candidate"])
        self.assertEqual(d2["envelope_error"], "internal")

    def test_gate_edit_cycles_noop_reruns_tool_issue_split_and_report(self) -> None:
        run_name = "camp-cycles"
        # Run 1: both spec_a (CHK-BUS-PROTOCOL) and spec_b (CHK-CITATION) fail.
        self._run_wrapper(
            "--run",
            run_name,
            "--use-diag-out",
            "--",
            str(self.fake_hwspecs),
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "fail_text"},
        )
        # Run 2: no-op rerun without editing any spec file -> increments noop_reruns, not edit_cycles.
        self._run_wrapper(
            "--run",
            run_name,
            "--use-diag-out",
            "--",
            str(self.fake_hwspecs),
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "fail_text"},
        )
        # Edit spec_b (v2) while fixing spec_a; Run 3 fails only on spec_b.
        self.spec_b.write_text("kind: peripheral\nname: uart_v2\n", encoding="utf-8")
        self._run_wrapper(
            "--run",
            run_name,
            "--",
            str(self.fake_hwspecs),
            "--json",
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "fail_uart_only"},
        )
        # Edit spec_b again (v3); Run 4 passes cleanly -> emits gate-clean.json!
        self.spec_b.write_text("kind: peripheral\nname: uart_v3\n", encoding="utf-8")
        self._run_wrapper(
            "--run",
            run_name,
            "--",
            str(self.fake_hwspecs),
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "pass"},
        )
        # Run 5: another clean run -> must NOT emit a duplicate gate-clean.json.
        self._run_wrapper(
            "--run",
            run_name,
            "--",
            str(self.fake_hwspecs),
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "pass"},
        )

        gates = list(
            (self.run_store / run_name / "audit" / "gates").glob("*/gate-clean.json")
        )
        self.assertEqual(len(gates), 1)
        gate_doc = json.loads(gates[0].read_text(encoding="utf-8"))
        self.assertTrue(gate_doc["run_id"].startswith(f"{run_name}.gate."))
        self.assertEqual(gate_doc["campaign_run"], run_name)
        self.assertEqual(gate_doc["noop_reruns"], 1)

        # Log #197 for CHK-BUS-PROTOCOL so spec_a's failure is attributed to a tool defect.
        r_issue = self._run_wrapper(
            "record-issue",
            "--run",
            run_name,
            "--issue",
            "#197",
            "--subcmd",
            "check",
            "--code",
            "CHK-BUS-PROTOCOL",
            "--summary",
            "i2c reg.bus validation rejected controller bus",
        )
        self.assertEqual(r_issue.returncode, 0, r_issue.stderr)

        # Record a verifier round for gw9200-i2c (testing all 11 fail categories validation).
        sha_a = hashlib.sha256(self.spec_a.read_bytes()).hexdigest()
        r_ver = self._run_wrapper(
            "record-verified",
            "--run",
            run_name,
            "--spec",
            "gw9200-i2c",
            "--round",
            "1",
            "--spec-sha256",
            sha_a,
            "--stale-checked",
            "31",
            "--critical-second-read",
            "11",
            "--verdict",
            "PASS=30",
            "--verdict",
            "FAIL=1",
            "--fail-category",
            "derivation=1",
        )
        self.assertEqual(r_ver.returncode, 0, r_ver.stderr)

        # Reject invalid fail category.
        r_bad_cat = self._run_wrapper(
            "record-verified",
            "--run",
            run_name,
            "--spec",
            "gw9200-i2c",
            "--round",
            "2",
            "--spec-sha256",
            sha_a,
            "--stale-checked",
            "5",
            "--critical-second-read",
            "2",
            "--fail-category",
            "not-a-valid-category=1",
        )
        self.assertEqual(r_bad_cat.returncode, 2)

        # Record two subagents: one that will be superseded by exact bringup-audit-1 usage,
        # and one that stays as a Tier 1 harness-notice.
        self._run_wrapper(
            "record-subagent",
            "--run",
            run_name,
            "--run-id",
            "sub-exact-1",
            "--role",
            "spec-verifier",
            "--shard",
            "gw9200-i2c",
            "--model",
            "claude-opus-4-6",
            "--reported-tokens",
            "999999",
            "--reported-duration-ms",
            "5000",
        )
        self._run_wrapper(
            "record-subagent",
            "--run",
            run_name,
            "--run-id",
            "sub-tier1-only",
            "--role",
            "peripheral-spec",
            "--shard",
            "gw9200-uart",
            "--model",
            "gpt-5",
            "--reported-tokens",
            "4000",
            "--reported-duration-ms",
            "3000",
        )

        # Publish an exact `bringup-audit-1` usage receipt for `sub-exact-1`.
        audit_dir = self.run_store / run_name / "audit"
        usage_rec = {
            "schema": "bringup-audit-1",
            "kind": "usage",
            "id": "sub-exact-1-usage",
            "run_id": "sub-exact-1",
            "lap": run_name,
            "milestone": "spec-gate",
            "step": "verify",
            "attempt": "1",
            "recorded_at": hwspecs_audit.utc_now_iso(),
            "measurement_key": "msg-001",
            "provider": "anthropic",
            "model": "claude-opus-4-6",
            "semantics": "exclusive-message-buckets",
            "tokens": {
                "input": 1000,
                "cache_read": 2000,
                "cache_write": 0,
                "output": 500,
            },
        }
        hwspecs_audit.publish_bringup_receipt(audit_dir, usage_rec)

        # Run report --json and verify all metrics.
        r_rep = self._run_wrapper("report", "--run", run_name, "--json")
        self.assertEqual(r_rep.returncode, 0, r_rep.stderr)
        report = json.loads(r_rep.stdout)

        gm = report["gate_metrics"]
        # gw9200-i2c failed on 1 distinct hash (attributed to tool issue #197).
        # gw9200-uart failed on 2 distinct hashes (v1 and v2, spec-defect) before passing on v3.
        self.assertEqual(gm["specs"]["gw9200-i2c.spec.yaml"]["gate_edit_cycles"], 1)
        self.assertEqual(gm["specs"]["gw9200-i2c.spec.yaml"]["tool_defect_cycles"], 1)
        self.assertEqual(gm["specs"]["gw9200-i2c.spec.yaml"]["spec_defect_cycles"], 0)
        self.assertEqual(gm["specs"]["gw9200-i2c.spec.yaml"]["noop_reruns"], 1)

        self.assertEqual(gm["specs"]["gw9200-uart.spec.yaml"]["gate_edit_cycles"], 2)
        self.assertEqual(gm["specs"]["gw9200-uart.spec.yaml"]["spec_defect_cycles"], 2)
        self.assertEqual(gm["specs"]["gw9200-uart.spec.yaml"]["tool_defect_cycles"], 0)
        self.assertEqual(gm["specs"]["gw9200-uart.spec.yaml"]["noop_reruns"], 1)

        self.assertEqual(gm["total_gate_edit_cycles"], 3)
        self.assertEqual(gm["tool_defect_cycles"], 1)
        self.assertEqual(gm["spec_defect_cycles"], 2)
        # Run 2 (failing) and Run 5 (clean re-check) both ran without spec hash changes.
        self.assertEqual(gm["total_noop_reruns"], 2)

        # Verify exact usage (1000 + 2000 + 500 = 3500) superseded 999999 on sub-exact-1,
        # and combined with 4000 from sub-tier1-only = 7500 (never summing 999999!).
        sub = report["subagents"]
        self.assertEqual(sub["effective_total_tokens"], 7500)
        self.assertEqual(sub["unsuperseded_reported_tokens"], 4000)

        # Verify Markdown report rendering.
        r_md = self._run_wrapper("report", run_name)
        self.assertEqual(r_md.returncode, 0, r_md.stderr)
        self.assertIn("# Process Audit Report", r_md.stdout)
        self.assertIn("`#197`", r_md.stdout)

    def test_uncaptured_usage_is_reported_as_unknown_never_zero(self) -> None:
        run_name = "camp-no-usage"
        self._run_wrapper(
            "--run",
            run_name,
            "--",
            str(self.fake_hwspecs),
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "pass"},
        )
        r_rep = self._run_wrapper("report", "--run", run_name, "--json")
        self.assertEqual(r_rep.returncode, 0, r_rep.stderr)
        report = json.loads(r_rep.stdout)
        self.assertEqual(report["subagents"]["effective_total_tokens"], "unknown")
        self.assertEqual(report["subagents"]["exact_tokens_by_bucket"], "unknown")
        self.assertEqual(report["coverage"]["token_usage_coverage"], "unknown")
        self.assertEqual(report["coverage"]["uncaptured_hwspecs_calls"], "unknown")

    def test_compatibility_with_bringupkit_audit_and_streamline_due(self) -> None:
        kit_dir = find_bringup_kit()
        if kit_dir is None:
            self.skipTest("sibling bringup-kit checkout not present")

        sys.path.insert(0, str(kit_dir))
        try:
            from bringupkit import audit as bk_audit
            from tools import streamline_due as bk_streamline
        finally:
            sys.path.pop(0)

        run_name = "camp-compat"
        # 1. Failing check followed by passing check -> emits gate-clean.json
        self._run_wrapper(
            "--run",
            run_name,
            "--lap",
            "lap1",
            "--milestone",
            "m1",
            "--step",
            "s1",
            "--attempt",
            "a1",
            "--",
            str(self.fake_hwspecs),
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "fail_text"},
        )
        self._run_wrapper(
            "--run",
            run_name,
            "--lap",
            "lap1",
            "--milestone",
            "m1",
            "--step",
            "s1",
            "--attempt",
            "a1",
            "--",
            str(self.fake_hwspecs),
            "check",
            "specs",
            env_Middle={"FAKE_HWSPECS_MODE": "pass"},
        )
        # 2. Record a tool issue -> emits tool-issue.json
        self._run_wrapper(
            "record-issue",
            "--run",
            run_name,
            "--issue",
            "#198",
            "--subcmd",
            "check",
            "--code",
            "CHK-OVERLAY-TARGET",
            "--summary",
            "cross-repo overlay_target resolution in corpus.yaml",
        )
        # 3. Record two verifier rounds -> emits review/*-r1/verified.json and review/*-r2/verified.json
        sha_a = hashlib.sha256(self.spec_a.read_bytes()).hexdigest()
        self._run_wrapper(
            "record-verified",
            "--run",
            run_name,
            "--spec",
            "gw9200-i2c",
            "--round",
            "1",
            "--spec-sha256",
            sha_a,
            "--stale-checked",
            "10",
            "--critical-second-read",
            "4",
            "--verdict",
            "PASS=10",
        )
        self._run_wrapper(
            "record-verified",
            "--run",
            run_name,
            "--spec",
            "gw9200-i2c",
            "--round",
            "2",
            "--spec-sha256",
            sha_a,
            "--stale-checked",
            "10",
            "--critical-second-read",
            "4",
            "--verdict",
            "PASS=10",
        )

        # Verify `bringupkit/audit.py` `project()` succeeds on `<run_store>/<run_name>/audit`
        # without colliding with `audit/hwspecs/`, `audit/gates/`, or `audit/issues/`.
        source_file = self.work_dir / "note.md"
        source_file.write_text("evidence\n", encoding="utf-8")
        source_sha = hashlib.sha256(source_file.read_bytes()).hexdigest()
        mapping_path = self.work_dir / "mapping.json"
        mapping_path.write_text(
            json.dumps(
                {
                    "schema": "bringup-audit-1",
                    "lap": "lap1",
                    "milestone": "m1",
                    "title": "Test Milestone",
                    "status": "complete",
                    "sources": [
                        {
                            "id": "src1",
                            "path": "note.md",
                            "sha256": source_sha,
                            "locator": "line 1",
                        }
                    ],
                    "steps": [
                        {
                            "id": "s1",
                            "title": "Gate check",
                            "depends_on": [],
                            "sources": ["src1"],
                        }
                    ],
                    "attempts": [
                        {
                            "id": "a1",
                            "step": "s1",
                            "role": "hwspecs-cli",
                            "purpose": "Run check",
                            "result": "Passed",
                            "next_reason": None,
                            "predecessor": None,
                            "observed_at": hwspecs_audit.utc_now_iso(),
                            "duration_seconds": 1.0,
                            "precision": "measured",
                            "acceptance": "accepted",
                            "sources": ["src1"],
                            "origin": "historical-import",
                        }
                    ],
                    "limitations": [],
                }
            ),
            encoding="utf-8",
        )
        projected = bk_audit.project(
            mapping_path, self.work_dir, self.run_store / run_name / "audit"
        )
        self.assertEqual(projected["summary"]["recorded_runs"], 2)

        # Verify `streamline_due.py`'s `finished_since` sees all 4 trigger events as distinct
        # runs (1 gate-clean.json + 1 tool-issue.json + 2 verified.json rounds = 4 events).
        found = bk_streamline.finished_since(
            [str(self.run_store)],
            {"verified.json", "gate-clean.json", "tool-issue.json"},
            since=0.0,
        )
        self.assertEqual(len(found), 4, f"Expected 4 distinct trigger events, got {found}")


if __name__ == "__main__":
    unittest.main()
