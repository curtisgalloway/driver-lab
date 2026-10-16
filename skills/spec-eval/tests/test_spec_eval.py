# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the spec-eval skill: prelude, schema, self-test, export and grading."""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
FIXTURES = HERE / "fixtures"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
import speceval  # pylint: disable=wrong-import-position

NEEDS_RUSTC = unittest.skipUnless(shutil.which("rustc"), "rustc not installed")
BANK = FIXTURES / "synthetic_bank.json"
LEGACY = FIXTURES / "legacy_item.json"


def run(script, *args, stdin=None, env=None):
    return subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True, input=stdin, check=False,
                          env=env)


def bank_items():
    return json.loads(BANK.read_text())["items"]


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write_bank(self, items, name="bank.json"):
        path = self.tmp / name
        path.write_text(json.dumps({"items": items}))
        return path


@NEEDS_RUSTC
class PreludeTests(TempDirCase):
    def test_prelude_tests_pass(self):
        exe = self.tmp / "prelude_tests"
        build = subprocess.run(
            ["rustc", "--edition", "2021", "--test", "-o", str(exe),
             str(SKILL / "rust" / "hw_eval_prelude.rs")],
            capture_output=True, text=True, check=False)
        self.assertEqual(build.returncode, 0, build.stderr)
        out = subprocess.run([str(exe), "--test-threads=1"], capture_output=True, text=True,
                             check=False).stdout
        self.assertIn("6 passed; 0 failed", out)
        for name in ("w1c_rmw", "ordered_sequence", "capability_gating", "bitfield_codec",
                     "hardware_math", "mockbus_semantics"):
            self.assertIn(f"test prelude_tests::{name} ... ok", out)

    def test_marker_splits_prelude(self):
        text = speceval.read_prelude()
        self.assertIn("pub trait RegBus", text)
        self.assertNotIn("prelude_tests", text)


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = speceval.load_schema()

    def test_fixtures_validate(self):
        for path in (BANK, LEGACY):
            data = json.loads(path.read_text())
            self.assertEqual(speceval.validate(data, self.schema), [], path.name)
            self.assertEqual(speceval.check_bank(speceval.load_bank(path)), [], path.name)

    def errors_for(self, mutate):
        items = copy.deepcopy(bank_items())
        mutate(items[0])
        return speceval.validate(items, self.schema) + speceval.check_bank(items)

    def test_missing_required_field(self):
        errors = self.errors_for(lambda i: i.pop("task_prompt"))
        self.assertTrue(any("task_prompt" in e for e in errors), errors)

    def test_missing_alias_pair(self):
        errors = self.errors_for(lambda i: i.pop("test_harness"))
        self.assertTrue(errors)

    def test_bad_stratum(self):
        errors = self.errors_for(lambda i: i.update(stratum="easy"))
        self.assertTrue(any("stratum" in e for e in errors), errors)

    def test_unknown_field(self):
        errors = self.errors_for(lambda i: i.update(surprise=1))
        self.assertTrue(any("surprise" in e for e in errors), errors)

    def test_both_aliases(self):
        errors = self.errors_for(lambda i: i.update(signature="pub fn x()"))
        self.assertTrue(any("fn_signature" in e and "signature" in e for e in errors), errors)

    def test_duplicate_id(self):
        items = bank_items()
        items.append(copy.deepcopy(items[0]))
        self.assertTrue(any("duplicate" in e for e in speceval.check_bank(items)))

    def test_signature_with_body_refused(self):
        errors = self.errors_for(lambda i: i.update(fn_signature="pub fn f() { }"))
        self.assertTrue(any("header only" in e for e in errors), errors)

    def test_out_of_spec_needs_probe(self):
        items = copy.deepcopy(bank_items())
        oos = next(i for i in items if i["stratum"] == "out-of-spec")
        del oos["abstain_probe"]
        self.assertTrue(any("abstain_probe" in e for e in speceval.check_bank(items)))

    def test_nested_unknown_keyword_raises_even_if_unvisited(self):
        schema = {"type": "object", "properties": {"a": {"patternProperties": {}}}}
        with self.assertRaises(ValueError):
            speceval.validate({}, schema)

    def test_bool_is_not_integer(self):
        self.assertTrue(speceval.validate(True, {"type": "integer"}))
        self.assertEqual(speceval.validate(3, {"type": "integer"}), [])

    def test_unknown_keyword_raises(self):
        with self.assertRaises(ValueError):
            speceval.validate({}, {"type": "object", "patternProperties": {}})

    def test_normalize_legacy(self):
        item = speceval.normalize(speceval.load_bank(LEGACY)[0])
        self.assertEqual(item["tier"], 2)
        self.assertIn("fold8", item["fn_signature"])
        self.assertIn("fold8", item["reference_rust"])
        self.assertEqual(item["doc_pages_primary"], [3])
        self.assertFalse(item["use_hw_prelude"])


@NEEDS_RUSTC
class SelfTestTests(TempDirCase):
    def test_fixtures_pass(self):
        for path in (BANK, LEGACY):
            proc = run("grade_code.py", "--bank", path, "--self-test")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_weak_trap_is_a_finding(self):
        items = bank_items()
        items[0]["trap_rust"] = items[0]["reference_rust"]
        proc = run("grade_code.py", "--bank", self.write_bank(items), "--self-test")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("the harness is too weak", proc.stdout)
        self.assertIn(f"FAIL {items[0]['id']}", proc.stdout)

    def test_trap_that_does_not_compile(self):
        items = bank_items()
        items[0]["trap_rust"] = "pub fn nope( {"
        proc = run("grade_code.py", "--bank", self.write_bank(items), "--self-test")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("trap does not compile", proc.stdout)

    def test_signature_without_spec_gap(self):
        items = bank_items()
        items[1]["fn_signature"] = "pub fn pack_desc(len: u16, chan: u8, flags: u16) -> u32"
        proc = run("grade_code.py", "--bank", self.write_bank(items), "--self-test")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("published signature", proc.stdout)

    def finding(self, mutate, index=0, expect=""):
        items = bank_items()
        mutate(items[index])
        env = dict(os.environ, SPEC_EVAL_RUN_TIMEOUT="3")
        proc = run("grade_code.py", "--bank", self.write_bank(items), "--self-test", env=env)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(f"FAIL {items[index]['id']}", proc.stdout)
        self.assertIn(expect, proc.stdout)

    def oos_index(self):
        return next(n for n, i in enumerate(bank_items()) if i["stratum"] == "out-of-spec")

    def test_broken_probe(self):
        self.finding(lambda i: i.update(abstain_probe="enable_crc_offload(&mut NoSuchBus)"),
                     self.oos_index(), "do not compile")

    def test_probe_that_never_fires(self):
        self.finding(lambda i: i.update(abstain_probe="Ok::<(), SpecGap>(())"),
                     self.oos_index(), "does not detect an abstaining answer")

    def test_probe_that_fires_on_reference(self):
        self.finding(lambda i: i.update(abstain_probe="Err::<(), SpecGap>(SpecGap(\"x\"))"),
                     self.oos_index(), "fires on the reference")

    def test_signature_name_mismatch(self):
        self.finding(lambda i: i.update(
            fn_signature="pub fn pack_descriptor(len: u16) -> Result<u32, SpecGap>"),
            1, "published signature")

    def test_hanging_trap(self):
        self.finding(lambda i: i.update(trap_rust=i["trap_rust"].replace(
            "Ok(", "loop {} //", 1)), 0, "trap times out")

    def test_unknown_top_level_key(self):
        path = self.tmp / "doc.json"
        path.write_text(json.dumps({"items": bank_items(), "extra_top_level": 1}))
        proc = run("grade_code.py", "--bank", path, "--self-test")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("extra_top_level", proc.stdout)

    def test_schema_errors_skip_compiles(self):
        items = bank_items()
        items[0]["stratum"] = "easy"
        proc = run("grade_code.py", "--bank", self.write_bank(items), "--self-test")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stratum", proc.stdout)
        self.assertNotIn("PASS", proc.stdout)

    def test_missing_bank_is_usage_error(self):
        proc = run("grade_code.py", "--bank", self.tmp / "none.json", "--self-test")
        self.assertEqual(proc.returncode, 2)


@NEEDS_RUSTC
class ExportTests(TempDirCase):
    def export(self):
        out = self.tmp / "code_preambles.json"
        proc = run("rust_check.py", "--export-preambles", BANK, "-o", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return out

    def test_export_is_a_whitelist(self):
        out = self.export()
        text = out.read_text()
        table = json.loads(text)
        self.assertEqual(sorted(table), sorted(i["id"] for i in bank_items()))
        for entry in table.values():
            self.assertEqual(sorted(entry),
                             ["preamble", "signature", "tier", "use_hw_prelude"])
        secrets = []
        for item in bank_items():
            secrets += [item["reference_rust"].strip(), item["trap_rust"].strip(),
                        item["test_harness"].strip(), item["task_prompt"]]
            secrets += item["spec_facts"]
            secrets += [item["abstain_probe"]] if "abstain_probe" in item else []
        for secret in secrets:
            self.assertNotIn(json.dumps(secret)[1:-1], text, secret[:40])
        self.assertIn("pub trait RegBus", table["zx-desc-pack"]["preamble"])
        self.assertNotIn("pub trait RegBus", table["zx-uart-divisor"]["preamble"])
        self.assertNotIn("prelude_tests", text)

    def export_status(self, items):
        proc = run("rust_check.py", "--export-preambles", self.write_bank(items), "-o",
                   self.tmp / "o.json")
        self.assertNotIn("Traceback", proc.stderr)
        return proc

    def test_export_refuses_invalid_banks(self):
        items = bank_items()
        items[0]["fn_signature"] = items[0]["reference_rust"]
        self.assertEqual(self.export_status(items).returncode, 1)
        items = bank_items()
        items[0]["tier"] = "x"
        self.assertEqual(self.export_status(items).returncode, 1)
        items = bank_items()
        del items[0]["id"]
        self.assertEqual(self.export_status(items).returncode, 1)
        self.assertFalse((self.tmp / "o.json").exists())

    def test_export_unreadable_input(self):
        proc = run("rust_check.py", "--export-preambles", self.tmp / "nope.json", "-o",
                   self.tmp / "o.json")
        self.assertEqual(proc.returncode, 2)
        bad = self.tmp / "bad.json"
        bad.write_text("{not json")
        proc = run("rust_check.py", "--export-preambles", bad, "-o", self.tmp / "o.json")
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)

    def test_preambles_file_not_an_object(self):
        arr = self.tmp / "arr.json"
        arr.write_text("[]")
        proc = run("rust_check.py", "zx-desc-pack", "--preambles", arr, "--code", "")
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)

    def test_rust_check(self):
        out = self.export()
        item = next(i for i in bank_items() if i["id"] == "zx-desc-pack")
        good = run("rust_check.py", "zx-desc-pack", "--preambles", out,
                   "--code", item["reference_rust"])
        self.assertEqual(good.returncode, 0, good.stdout)
        self.assertEqual(good.stdout.strip(), "COMPILE_OK")
        bad = run("rust_check.py", "zx-desc-pack", "--preambles", out, stdin="fn broken( {")
        self.assertEqual(bad.returncode, 1)
        self.assertTrue(bad.stdout.startswith("COMPILE_ERROR"), bad.stdout)
        unknown = run("rust_check.py", "no-such-item", "--preambles", out, "--code", "")
        self.assertEqual(unknown.returncode, 2)
        missing = run("rust_check.py", "zx-desc-pack", "--preambles", self.tmp / "x.json",
                      "--code", "")
        self.assertEqual(missing.returncode, 2)


EXPECTED = {
    ("zx-uart-divisor", "m1", "A"): "correct",
    ("zx-uart-divisor", "m1", "B"): "test-fail",
    ("zx-desc-pack", "m1", "A"): "correct",
    ("zx-desc-pack", "m1", "B"): "compile-error",
    ("zx-status-clear", "m1", "A"): "correct",
    ("zx-status-clear", "m1", "B"): "test-fail",
    ("zx-start-transfer", "m2", "A"): "correct",
    ("zx-start-transfer", "m2", "D"): "test-fail",
    ("zx-crc-offload", "m2", "A"): "abstain-ok",
    ("zx-crc-offload", "m2", "B"): "correct",
    ("zx-crc-offload", "m2", "C"): "abstain-wrong",
    ("zx-crc-offload", "m2", "D"): "test-fail",
    ("zx-crc-offload", "m3", "A"): "abstain-ok",
    ("zx-uart-divisor", "m3", "B"): "abstain-wrong",
    ("zx-no-such-item", "m3", "A"): "unknown-item",
}


@NEEDS_RUSTC
class GradingTests(TempDirCase):
    def grade(self, bank, records, abstain="A", extra=()):
        raw = self.tmp / "raw.jsonl"
        raw.write_text("".join(json.dumps(r) + "\n" for r in records))
        args = ["--bank", bank, "--raw", raw, "--out", self.tmp / "graded.jsonl",
                "--report", self.tmp / "report.md", *extra]
        if abstain is not None:
            args += ["--abstain-arms", abstain]
        proc = run("grade_code.py", *args)
        rows = []
        if proc.returncode == 0:
            rows = [json.loads(line) for line in
                    (self.tmp / "graded.jsonl").read_text().splitlines()]
        return proc, rows

    def test_sweep(self):
        graded = self.tmp / "graded.jsonl"
        report = self.tmp / "report.md"
        proc = run("grade_code.py", "--bank", BANK, "--raw", FIXTURES / "sweep", "--out",
                   graded, "--report", report, "--abstain-arms", "A")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("unknown item id", proc.stderr)
        rows = [json.loads(line) for line in graded.read_text().splitlines()]
        got = {(r["item_id"], r["model"], r["arm"]): r["outcome"] for r in rows}
        self.assertEqual(got, EXPECTED)
        self.assertEqual(len(rows), len(EXPECTED))
        by_key = {(r["item_id"], r["model"], r["arm"]): r for r in rows}
        raw = [json.loads(line) for f in sorted((FIXTURES / "sweep").glob("*.jsonl"))
               for line in f.read_text().splitlines()]
        probe_only = next(r for r in raw if r["item_id"] == "zx-crc-offload"
                          and r["model"] == "m2" and r["arm"] == "A")
        self.assertNotIn("abstained", probe_only)
        self.assertTrue(by_key[("zx-crc-offload", "m2", "A")]["abstained"])
        self.assertIn("diagnostics", by_key[("zx-desc-pack", "m1", "B")])
        self.assertEqual(by_key[("zx-uart-divisor", "m1", "B")]["failed_tests"],
                         ["tests::rounds_to_nearest"])
        text = report.read_text()
        for heading in ("Answerable from the spec: every stratum except out-of-spec",
                        "Out-of-spec items", "All items", "Per model and arm"):
            self.assertIn(heading, text)
        self.assertIn("Abstain arms (an out-of-spec item's right answer is abstention): A",
                      text)
        self.assertIn("| pass rate | 100% | 0% | n/a | 0% |", text)
        self.assertNotIn("ZeroDivision", text)

    def test_missing_raw_is_usage_error(self):
        proc = run("grade_code.py", "--bank", BANK, "--raw", self.tmp / "none", "--out",
                   self.tmp / "g", "--report", self.tmp / "r", "--abstain-arms", "none")
        self.assertEqual(proc.returncode, 2)

    def test_abstain_arms_required_with_out_of_spec_items(self):
        proc, _ = self.grade(BANK, [], abstain=None)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--abstain-arms", proc.stderr)
        # A bank without out-of-spec items does not need it.
        proc, _ = self.grade(LEGACY, [], abstain=None)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_abstain_arms_none_and_absent_arm_warning(self):
        item = next(i for i in bank_items() if i["id"] == "zx-crc-offload")
        rec = {"item_id": "zx-crc-offload", "model": "m", "arm": "A",
               "rust_code": 'pub fn enable_crc_offload<B: RegBus>(bus: &mut B) -> '
                            'Result<(), SpecGap> { Err(SpecGap("x")) }'}
        proc, rows = self.grade(BANK, [rec], abstain="none")
        self.assertEqual(rows[0]["outcome"], "abstain-wrong", item["id"])
        proc, _ = self.grade(BANK, [rec], abstain="A,spec_only")
        self.assertIn("'spec_only' appears in no record", proc.stderr)

    def two_test_bank(self):
        item = {
            "id": "two", "stratum": "in-spec-scalar", "tier": 2, "task_prompt": "p",
            "fn_signature": "pub fn f(x: u32) -> Result<u32, SpecGap>",
            "reference_rust": "pub fn f(x: u32) -> Result<u32, SpecGap> { Ok(x + 1) }",
            "trap_rust": "pub fn f(x: u32) -> Result<u32, SpecGap> { Ok(x) }",
            "use_hw_prelude": True,
            "test_harness": "#[cfg(test)] mod tests { use super::*; "
                            "#[test] fn a() { assert_eq!(f(1), Ok(2)); } "
                            "#[test] fn b() { assert_eq!(f(2), Ok(3)); } }",
        }
        return self.write_bank([item])

    def outcome_of(self, bank, code, item_id="two", **kw):
        rec = {"item_id": item_id, "model": "m", "arm": "A", "rust_code": code, **kw}
        proc, rows = self.grade(bank, [rec], abstain="none")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return rows[0]

    def test_mid_run_death_is_not_correct(self):
        bank = self.two_test_bank()
        ok = "pub fn f(x: u32) -> Result<u32, SpecGap> { Ok(x + 1) }"
        self.assertEqual(self.outcome_of(bank, ok)["outcome"], "correct")
        for dying in ("std::process::abort()", "std::process::exit(0)"):
            code = ("pub fn f(x: u32) -> Result<u32, SpecGap> { if x == 2 { " + dying +
                    " } Ok(x + 1) }")
            graded = self.outcome_of(bank, code)
            if "exit" in dying:
                self.assertEqual(graded["outcome"], "compile-error", dying)
            else:
                self.assertEqual(graded["outcome"], "test-fail", dying)
                self.assertFalse(graded["test_ok"])

    def test_fake_summary_then_abort_is_not_correct(self):
        bank = self.two_test_bank()
        code = ("use std::io::Write;\n"
                "pub fn f(x: u32) -> Result<u32, SpecGap> { if x == 2 { "
                "let mut o = std::io::stdout(); "
                "o.write_all(b\"\\ntest tests::b ... ok\\n\\ntest result: ok. 2 passed\\n\").unwrap(); "
                "o.flush().unwrap(); std::process::abort() } Ok(x + 1) }")
        graded = self.outcome_of(bank, code)
        self.assertEqual(graded["outcome"], "test-fail")
        self.assertFalse(graded["test_ok"])

    def test_spaced_refused_constructs(self):
        bank = self.two_test_bank()
        for code in ("macro_rules ! assert_eq { ($($t:tt)*) => {} }\n"
                     "pub fn f(x: u32) -> Result<u32, SpecGap> { Ok(0) }",
                     "# ! [allow(unused)]\npub fn f(x: u32) -> Result<u32, SpecGap> { Ok(x+1) }",
                     "pub fn f(x: u32) -> Result<u32, SpecGap> { "
                     "if x == 2 { std::process :: exit(0) } Ok(x + 1) }"):
            graded = self.outcome_of(bank, code)
            self.assertEqual(graded["outcome"], "compile-error", code)
            self.assertTrue(graded["diagnostics"].startswith("refused:"), code)

    def test_empty_abstain_arms_counts_as_missing(self):
        proc, _ = self.grade(BANK, [], abstain="")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--abstain-arms", proc.stderr)

    def test_bad_run_timeout_is_usage_error(self):
        for value in ("abc", "0", "-3"):
            env = dict(os.environ, SPEC_EVAL_RUN_TIMEOUT=value)
            proc = run("grade_code.py", "--bank", BANK, "--self-test", env=env)
            self.assertEqual(proc.returncode, 2, value)
            self.assertIn("SPEC_EVAL_RUN_TIMEOUT", proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_exit_in_a_helper_module_path_is_refused(self):
        bank = self.two_test_bank()
        code = ("use std::process; pub fn f(x: u32) -> Result<u32, SpecGap> { "
                "if x == 2 { process::exit(0) } Ok(x + 1) }")
        graded = self.outcome_of(bank, code)
        self.assertEqual(graded["outcome"], "compile-error")
        self.assertTrue(graded["diagnostics"].startswith("refused:"))

    def test_marker_text_is_not_an_abstention(self):
        bank = self.write_bank(bank_items())
        code = ('pub fn enable_crc_offload<B: RegBus>(bus: &mut B) -> Result<(), SpecGap> { '
                'bus.write32(0x28, 1); panic!("__EVAL_SPEC_GAP__"); }')
        rec = {"item_id": "zx-crc-offload", "model": "m", "arm": "A", "rust_code": code}
        proc, rows = self.grade(bank, [rec], abstain="A")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(rows[0]["abstained"])
        self.assertEqual(rows[0]["outcome"], "test-fail")

    def test_hostile_answers_refused(self):
        bank = self.two_test_bank()
        for code in ("macro_rules! assert_eq { ($($t:tt)*) => {} }\n"
                     "pub fn f(x: u32) -> Result<u32, SpecGap> { Ok(0) }",
                     "#![allow(unused)]\npub fn f(x: u32) -> Result<u32, SpecGap> { Ok(x+1) }",
                     "mod __eval_probe {}"):
            graded = self.outcome_of(bank, code)
            self.assertEqual(graded["outcome"], "compile-error", code)
            self.assertTrue(graded["diagnostics"].startswith("refused:"))

    def test_self_reported_abstention_with_empty_code(self):
        bank = self.write_bank(bank_items())
        for code in ("", "  \n"):
            rec = {"item_id": "zx-crc-offload", "model": "m", "arm": "A",
                   "rust_code": code, "abstained": True}
            proc, rows = self.grade(bank, [rec], abstain="A")
            self.assertEqual(rows[0]["outcome"], "abstain-ok")


if __name__ == "__main__":
    unittest.main()
