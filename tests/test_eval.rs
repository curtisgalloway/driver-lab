// SPDX-License-Identifier: Apache-2.0
//! Integration tests for `hwspecs eval` (RT-9), porting `skills/spec-eval/tests/test_spec_eval.py`
//! plus ENV-5 candidate sandbox containment tests and CLI subcommand tests.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use hwspecs::eval::{
    build_bwrap_args_with_options, check_bank, compile_and_run_tests, export_preambles, load_bank,
    normalize, validate,
};
use serde_json::{json, Value};
use tempfile::TempDir;

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn fixtures_dir() -> PathBuf {
    repo_root().join("skills/spec-eval/tests/fixtures")
}

fn run_eval_cli(args: &[&str]) -> (i32, String, String) {
    let mut argv = vec!["hwspecs", "eval"];
    argv.extend_from_slice(args);
    let mut stdout = Vec::new();
    let mut stderr = Vec::new();
    let code = hwspecs::run_from_args(argv, &mut stdout, &mut stderr);
    (
        code,
        String::from_utf8_lossy(&stdout).into_owned(),
        String::from_utf8_lossy(&stderr).into_owned(),
    )
}

// ===========================================================================
// 1. PreludeTests (ported from test_spec_eval.py::PreludeTests)
// ===========================================================================

#[test]
fn test_prelude_compiles_and_passes_self_tests() {
    let hw_prelude = repo_root().join("skills/spec-eval/rust/hw_eval_prelude.rs");
    let tmp = TempDir::new().unwrap();
    let exe = tmp.path().join("prelude_tests");
    let build = std::process::Command::new("rustc")
        .args(["--edition", "2021", "--test", "-o"])
        .arg(&exe)
        .arg(&hw_prelude)
        .output()
        .unwrap();
    assert!(
        build.status.success(),
        "{}",
        String::from_utf8_lossy(&build.stderr)
    );

    let out = std::process::Command::new(exe)
        .arg("--test-threads=1")
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("6 passed; 0 failed"));
}

// ===========================================================================
// 2. SchemaTests (ported from test_spec_eval.py::SchemaTests)
// ===========================================================================

#[test]
fn test_synthetic_bank_passes_schema() {
    let bank = load_bank(&fixtures_dir().join("synthetic_bank.json")).unwrap();
    assert_eq!(bank.len(), 5);
}

#[test]
fn test_legacy_bank_normalizes_and_passes() {
    let bank = load_bank(&fixtures_dir().join("legacy_item.json")).unwrap();
    assert_eq!(bank.len(), 1);
    let item = &bank[0];
    assert_eq!(item["stratum"].as_str().unwrap(), "in-spec-scalar");
}

#[test]
fn test_legacy_bank_normalizes_fields_exact() {
    let bank = load_bank(&fixtures_dir().join("legacy_item.json")).unwrap();
    let item = normalize(&bank[0]);
    assert_eq!(item["tier"].as_u64().unwrap(), 2);
    assert!(item["fn_signature"].as_str().unwrap().contains("fold8"));
    assert!(item["reference_rust"].as_str().unwrap().contains("fold8"));
    let doc_pages = item["doc_pages_primary"].as_array().unwrap();
    assert_eq!(doc_pages.len(), 1);
    assert_eq!(doc_pages[0].as_u64().unwrap(), 3);
    assert!(!item["use_hw_prelude"].as_bool().unwrap());
}

#[test]
fn test_normalize_does_not_overwrite_present_v2_fields() {
    let raw = json!({
        "tier": "tier1",
        "stratum": "out-of-spec",
        "signature": "old",
        "fn_signature": "new",
    });
    let norm = normalize(&raw);
    assert_eq!(
        norm.get("stratum").and_then(Value::as_str),
        Some("out-of-spec")
    );
    assert_eq!(
        norm.get("fn_signature").and_then(Value::as_str),
        Some("new")
    );
}

#[test]
fn test_schema_rejects_bad_id() {
    let mut bank = load_bank(&fixtures_dir().join("synthetic_bank.json")).unwrap();
    let dup = bank[0].clone();
    bank.push(dup);
    let errs = check_bank(&bank);
    assert!(
        errs.iter().any(|e| e.contains("duplicate")),
        "expected duplicate error, got {:?}",
        errs
    );
}

#[test]
fn test_schema_rejects_negative_without_abstain_probe() {
    let raw: Value = serde_json::from_str(
        &fs::read_to_string(fixtures_dir().join("synthetic_bank.json")).unwrap(),
    )
    .unwrap();
    let mut neg = raw["items"]
        .as_array()
        .unwrap()
        .iter()
        .find(|i| i.get("stratum").and_then(Value::as_str) == Some("out-of-spec"))
        .unwrap()
        .clone();
    neg.as_object_mut().unwrap().remove("abstain_probe");
    let bank = json!({ "items": [neg] });
    let errs =
        hwspecs::eval::bank_findings(&bank, &hwspecs::eval::load_schema(None).unwrap())
            .unwrap();
    assert!(
        errs.iter().any(|e| e.contains("abstain_probe")),
        "expected abstain_probe error, got {errs:?}"
    );
}

#[test]
fn test_schema_rejects_unknown_extra_property() {
    let raw: Value = serde_json::from_str(
        &fs::read_to_string(fixtures_dir().join("synthetic_bank.json")).unwrap(),
    )
    .unwrap();
    let mut item = raw["items"][0].clone();
    item["surprise_field"] = json!(123);
    let bank = json!({ "items": [item] });
    let errs =
        hwspecs::eval::bank_findings(&bank, &hwspecs::eval::load_schema(None).unwrap())
            .unwrap();
    assert!(
        errs.iter().any(|e| e.contains("surprise_field")),
        "expected surprise_field error, got {errs:?}"
    );
}

#[test]
fn test_validator_rejects_unknown_schema_keyword() {
    let bad_schema = json!({ "type": "object", "patternProperties": {} });
    let errs = validate(&json!({}), &bad_schema).unwrap_err();
    assert!(
        errs.0.contains("patternProperties"),
        "expected patternProperties error, got {:?}",
        errs
    );
}

#[test]
fn test_bank_findings_flags_weak_test_module() {
    let tmp = TempDir::new().unwrap();
    let mut bank = load_bank(&fixtures_dir().join("synthetic_bank.json")).unwrap();
    bank[0]["trap_rust"] = bank[0]["reference_rust"].clone();
    let bank_path = tmp.path().join("bank.json");
    std::fs::write(
        &bank_path,
        serde_json::to_string(&json!({"items": bank})).unwrap(),
    )
    .unwrap();

    let (code, out, err) = run_eval_cli(&[
        "grade-code",
        "--bank",
        bank_path.to_str().unwrap(),
        "--self-test",
    ]);
    assert_eq!(code, 1, "out: {out}, err: {err}");
    assert!(out.contains("the harness is too weak"));
    assert!(out.contains("FAIL zx-uart-divisor"));
}

#[test]
fn test_bank_findings_clean_on_synthetic_bank() {
    let raw: Value = serde_json::from_str(
        &fs::read_to_string(fixtures_dir().join("synthetic_bank.json")).unwrap(),
    )
    .unwrap();
    let items: Vec<Value> = raw["items"]
        .as_array()
        .unwrap()
        .iter()
        .map(normalize)
        .collect();
    let bank = json!({ "items": items });
    assert_eq!(
        hwspecs::eval::bank_findings(&bank, &hwspecs::eval::load_schema(None).unwrap())
            .unwrap(),
        vec![] as Vec<String>
    );
}

// ===========================================================================
// 3. SelfTestTests (ported from test_spec_eval.py::SelfTestTests)
// ===========================================================================

#[test]
fn test_self_test_passes_on_synthetic_and_legacy_banks() {
    for name in ["synthetic_bank.json", "legacy_item.json"] {
        let bank_path = fixtures_dir().join(name);
        let (code, _out, err) = run_eval_cli(&["validate-bank", bank_path.to_str().unwrap()]);
        assert_eq!(code, 0, "{name} failed validate-bank: {err}");
    }
}

#[test]
fn test_self_test_catches_broken_reference_solution() {
    let tmp = TempDir::new().unwrap();
    let mut bank = load_bank(&fixtures_dir().join("synthetic_bank.json")).unwrap();
    bank[0]["trap_rust"] = json!("pub fn nope( {");
    let bank_path = tmp.path().join("bank.json");
    std::fs::write(
        &bank_path,
        serde_json::to_string(&json!({"items": bank})).unwrap(),
    )
    .unwrap();

    let (code, out, _err) = run_eval_cli(&[
        "grade-code",
        "--bank",
        bank_path.to_str().unwrap(),
        "--self-test",
    ]);
    assert_eq!(code, 1);
    assert!(out.contains("trap does not compile"));
}

#[test]
fn test_self_test_catches_non_panicking_negative_ref() {
    let tmp = TempDir::new().unwrap();
    let mut bank = load_bank(&fixtures_dir().join("synthetic_bank.json")).unwrap();
    let oos_idx = bank
        .iter()
        .position(|i| i["stratum"] == "out-of-spec")
        .unwrap();
    bank[oos_idx]["abstain_probe"] = json!("enable_crc_offload(&mut NoSuchBus)");
    let bank_path = tmp.path().join("bank.json");
    std::fs::write(
        &bank_path,
        serde_json::to_string(&json!({"items": bank})).unwrap(),
    )
    .unwrap();

    let (code, out, err) = run_eval_cli(&[
        "grade-code",
        "--bank",
        bank_path.to_str().unwrap(),
        "--self-test",
    ]);
    assert_eq!(code, 1, "out: {out}, err: {err}");
    assert!(out.contains("do not compile"));
}

// ===========================================================================
// 4. ExportTests (ported from test_spec_eval.py::ExportTests)
// ===========================================================================

#[test]
fn test_export_preambles_writes_all_arms_with_abstain_rule_and_prelude_summary() {
    let tmp = TempDir::new().unwrap();
    let bank_path = fixtures_dir().join("synthetic_bank.json");
    let out_file = tmp.path().join("code_preambles.json");
    let mut stderr = Vec::new();
    assert_eq!(
        export_preambles(&bank_path, &out_file, None, None, &mut stderr),
        0
    );
    let text = std::fs::read_to_string(&out_file).unwrap();
    let table: std::collections::BTreeMap<String, Value> = serde_json::from_str(&text).unwrap();
    assert_eq!(table.len(), 5);
    for entry in table.values() {
        let mut keys: Vec<_> = entry.as_object().unwrap().keys().cloned().collect();
        keys.sort();
        assert_eq!(
            keys,
            vec!["preamble", "signature", "tier", "use_hw_prelude"]
        );
    }
}

// ===========================================================================
// 5. GradingTests (ported from test_spec_eval.py::GradingTests)
// ===========================================================================

#[test]
fn test_end_to_end_grading_and_report_sweep() {
    let tmp = TempDir::new().unwrap();
    let bank_path = fixtures_dir().join("synthetic_bank.json");
    let responses_path = fixtures_dir().join("sweep");
    let out_jsonl = tmp.path().join("graded.jsonl");
    let out_report = tmp.path().join("report.md");

    let (code, _out, err) = run_eval_cli(&[
        "grade-code",
        "--bank",
        bank_path.to_str().unwrap(),
        "--raw",
        responses_path.to_str().unwrap(),
        "--out",
        out_jsonl.to_str().unwrap(),
        "--report",
        out_report.to_str().unwrap(),
        "--abstain-arms",
        "A",
    ]);
    assert_eq!(code, 0, "grade-code failed: {err}");

    let graded_raw = fs::read_to_string(&out_jsonl).unwrap();
    let mut rows: BTreeMap<(String, String, String), Value> = BTreeMap::new();
    for line in graded_raw.lines() {
        if line.trim().is_empty() {
            continue;
        }
        let r: Value = serde_json::from_str(line).unwrap();
        let key = (
            r["item_id"].as_str().unwrap().to_string(),
            r["model"].as_str().unwrap().to_string(),
            r["arm"].as_str().unwrap().to_string(),
        );
        rows.insert(key, r);
    }

    let expected: &[((&str, &str, &str), &str)] = &[
        (("zx-uart-divisor", "m1", "A"), "correct"),
        (("zx-uart-divisor", "m1", "B"), "test-fail"),
        (("zx-desc-pack", "m1", "A"), "correct"),
        (("zx-desc-pack", "m1", "B"), "compile-error"),
        (("zx-status-clear", "m1", "A"), "correct"),
        (("zx-status-clear", "m1", "B"), "test-fail"),
        (("zx-start-transfer", "m2", "A"), "correct"),
        (("zx-start-transfer", "m2", "D"), "test-fail"),
        (("zx-crc-offload", "m2", "A"), "abstain-ok"),
        (("zx-crc-offload", "m2", "B"), "correct"),
        (("zx-crc-offload", "m2", "C"), "abstain-wrong"),
        (("zx-crc-offload", "m2", "D"), "test-fail"),
        (("zx-crc-offload", "m3", "A"), "abstain-ok"),
        (("zx-uart-divisor", "m3", "B"), "abstain-wrong"),
        (("zx-no-such-item", "m3", "A"), "unknown-item"),
    ];

    assert_eq!(rows.len(), expected.len());
    for &(k, want_outcome) in expected {
        let key = (k.0.to_string(), k.1.to_string(), k.2.to_string());
        let got = rows
            .get(&key)
            .unwrap_or_else(|| panic!("missing row for {k:?}"))["outcome"]
            .as_str()
            .unwrap();
        assert_eq!(
            got, want_outcome,
            "for {k:?}: got {got}, want {want_outcome}"
        );
    }
}

// ===========================================================================
// 6. ENV-5 Candidate Sandbox Containment Tests
// ===========================================================================

#[test]
fn test_env5_bwrap_command_line_construction_and_home_masking() {
    let scratch = Path::new("/tmp/hwspecs-eval-scratch-123");
    let bin = Path::new("/tmp/hwspecs-eval-scratch-123/cand_test");

    // 1. Standard Linux home under /home/user
    let args_std =
        build_bwrap_args_with_options(bin, scratch, true, Some(Path::new("/home/alice")));
    assert!(args_std.contains(&std::ffi::OsString::from("--unshare-all")));
    assert!(args_std.contains(&std::ffi::OsString::from("--die-with-parent")));
    assert!(args_std.contains(&std::ffi::OsString::from("--clearenv")));
    assert!(args_std.contains(&std::ffi::OsString::from("--ro-bind")));
    // Verify /home is never mounted
    assert!(!args_std
        .iter()
        .any(|a| a.to_string_lossy().contains("/home")));

    // 2. When $HOME is under /usr (e.g., /usr/local/someorg/home/alice), bwrap must mask
    // the parent directory under /usr with --tmpfs so --ro-bind /usr /usr does not leak $HOME.
    let current_home = std::env::var_os("HOME").map(PathBuf::from);
    if let Some(ref home) = current_home {
        if home.starts_with("/usr") && home.exists() {
            let args_host = build_bwrap_args_with_options(bin, scratch, true, Some(home));
            let parent = home.parent().unwrap().to_string_lossy().into_owned();
            let mut found_mask = false;
            for win in args_host.windows(2) {
                if win[0].to_string_lossy() == "--tmpfs" && win[1].to_string_lossy() == parent {
                    found_mask = true;
                    break;
                }
            }
            assert!(
                found_mask,
                "expected --tmpfs <home-parent> in bwrap args to prevent $HOME leak under /usr"
            );
        }
    }
}

#[test]
fn test_env5_macos_sandbox_exec_profile_denies_network_and_home() {
    let scratch = std::path::Path::new("/private/tmp/eval-scratch");
    let home = std::path::Path::new("/Users/tester");
    let profile = hwspecs::eval::build_macos_sandbox_profile(scratch, Some(home));
    assert!(profile.contains("(deny network*)"));
    assert!(profile.contains("(deny file-read* (subpath \"/Users/tester\"))"));
    assert!(profile.contains("(deny file-write* (subpath \"/Users/tester\"))"));
    assert!(profile.contains("(allow file-write*\n"));
    assert!(profile.contains("  (subpath \"/private/tmp/eval-scratch\"))"));
}

#[test]
#[ignore = "requires bubblewrap user namespaces; run explicitly in CI via cargo test -- --ignored"]
fn test_env5_live_sandbox_blocks_home_and_network_in_candidate_tests() {
    let host_home = std::env::var("HOME").unwrap_or_else(|_| "/nonexistent".to_string());
    let candidate_test = format!(
        r#"
#[cfg(test)]
mod _env5_containment_test {{
    use std::net::TcpStream;
    use std::path::Path;
    use std::time::Duration;

    #[test]
    fn verify_isolated_env_home_and_net() {{
        // 1. $HOME env var must not be set inside the sandbox
        assert!(
            std::env::var_os("HOME").is_none(),
            "HOME env var leaked into sandbox"
        );

        // 2. Host home directory path must not be readable inside the sandbox
        let host_home_path = Path::new({host_home:?});
        assert!(
            !host_home_path.exists() && std::fs::read_dir(host_home_path).is_err(),
            "Host home directory is accessible inside sandbox!"
        );

        // 3. Outbound network connections must fail immediately in isolated net namespace
        let net_res = TcpStream::connect_timeout(
            &"8.8.8.8:53".parse().unwrap(),
            Duration::from_millis(200),
        );
        assert!(
            net_res.is_err(),
            "Network connection succeeded inside sandbox!"
        );
    }}
}}
"#
    );

    let res = compile_and_run_tests(&candidate_test, None, None, false).unwrap();
    assert!(
        res.compiled,
        "containment test failed to compile: {:?}",
        res.diagnostics
    );
    let test_ok = res.results.values().all(|v| v == "ok") && res.complete && res.compiled;
    assert!(
        test_ok,
        "ENV-5 containment assertions failed inside sandbox: {:?}\nstdout: {}\nstderr: {}",
        res.results, res.stdout, res.diagnostics
    );
}

// ===========================================================================
// 7. Subcommands Tests
// ===========================================================================

#[test]
fn test_cli_grade_facts() {
    let tmp = tempfile::TempDir::new().unwrap();
    let bank_path = tmp.path().join("bank.json");
    let cand_path = tmp.path().join("cand.json");
    let out_path = tmp.path().join("out.json");

    let bank_json = serde_json::json!({
        "bank": "test",
        "version": 1,
        "items": [
            {
                "id": "q1",
                "tier": 2,
                "stratum": "in-spec-scalar",
                "fn_signature": "fn test()",
                "task_prompt": "task",
                "reference_rust": "fn test() {}",
                "trap_rust": "fn eval() {}",
                "test_harness": "#[cfg(test)]\nmod tests {\n#[test]\nfn a(){}\n}",
                "doc_pages_primary": [1],
                "use_hw_prelude": false,
            }
        ]
    });
    std::fs::write(&bank_path, serde_json::to_string(&bank_json).unwrap()).unwrap();

    let cand_json = serde_json::json!({
        "item_id": "q1",
        "rust_code": "fn test() {}"
    });
    std::fs::write(
        &cand_path,
        serde_json::to_string(&cand_json).unwrap() + "\n",
    )
    .unwrap();

    let (code, _stdout, stderr) = run_eval_cli(&[
        "grade-facts",
        "--bank",
        bank_path.to_str().unwrap(),
        "--raw",
        cand_path.to_str().unwrap(),
        "--out",
        out_path.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stderr: {}", stderr);

    let out_text = std::fs::read_to_string(&out_path).unwrap();
    let out_json: serde_json::Value =
        serde_json::from_str(out_text.lines().next().unwrap()).unwrap();
    assert_eq!(
        out_json.get("outcome").unwrap().as_str().unwrap(),
        "test-fail"
    );
}
