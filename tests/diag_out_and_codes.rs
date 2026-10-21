// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Integration and conformance tests for Milestone PA-2:
//! - Shared `Finding.code` classification (`classify_check_finding_code`,
//!   `classify_resolve_finding_code`) and JSON serialization on `check`, `resolve`, and `status`.
//! - Global `--diag-out <FILE>` CLI option on `check`, `resolve`, and `status` (`ENV-1`/`ENV-2`
//!   compliant).

use hwspecs::diagnostic::{classify_check_finding_code, classify_resolve_finding_code};
use serde_json::Value;
use std::fs;
use std::path::PathBuf;
use std::process::Command;
use tempfile::TempDir;

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn fixtures_dir() -> PathBuf {
    repo_root().join("skills/spec-format/tests/fixtures")
}

fn run_cli(args: &[&str]) -> (i32, String, String) {
    let mut full = vec!["hwspecs"];
    full.extend_from_slice(args);
    let mut stdout = Vec::new();
    let mut stderr = Vec::new();
    let code = hwspecs::run_from_args(full, &mut stdout, &mut stderr);
    (
        code,
        String::from_utf8(stdout).unwrap(),
        String::from_utf8(stderr).unwrap(),
    )
}

#[test]
fn test_classify_check_finding_code_all_patterns() {
    let cases = [
        (
            "at least one root directory is required",
            "CHK-PRECONDITION",
        ),
        (
            "checking a standalone *.facts.yaml file requires --root <dir>",
            "CHK-PRECONDITION",
        ),
        ("schema: 'format' is a required property", "CHK-SCHEMA"),
        ("duplicate mapping key 'id'", "CHK-SCHEMA"),
        (
            "context root: schema: 'kind' is a required property",
            "CHK-SCHEMA",
        ),
        ("basis fact 'clk-gate' is stale", "CHK-BASIS-STALE"),
        (
            "fact 'irq-line' is unverified under --require-verified pr",
            "CHK-BASIS-STALE",
        ),
        (
            "overlay target record 'uart0' not found in base spec",
            "CHK-OVERLAY-TARGET",
        ),
        (
            "todo 'check-fifo' resolves: unknown fact id",
            "CHK-TODO-TRACKING",
        ),
        (
            "bus protocol 'axilite' endpoint responder mismatch",
            "CHK-BUS-PROTOCOL",
        ),
        (
            "repository license 'GPL-2.0-only' is not in root accepts list",
            "CHK-LICENSE",
        ),
        (
            "unsubstituted template placeholder '{{SPEC_ID}}'",
            "CHK-STUB",
        ),
        ("unanchored hex literal 0x4000_1000 in prose", "CHK-PROSE"),
        ("corpus.yaml entry missing .index.yaml file", "CHK-CORPUS"),
        (
            "citation anchor repo 'linux' is not declared in resources.repos",
            "CHK-CITATION",
        ),
        (
            "register 'CTRL' field [31:0] width exceeds register width",
            "CHK-PERIPHERAL",
        ),
        ("unexpected top-level condition in spec", "CHK-GENERAL"),
    ];

    for (msg, expected_code) in cases {
        let actual = classify_check_finding_code(msg);
        assert!(
            !actual.is_empty(),
            "classify_check_finding_code returned empty code for: {msg}"
        );
        assert_eq!(
            actual, expected_code,
            "unexpected check code for message: {msg}"
        );
        // Verify determinism across repeated calls
        assert_eq!(classify_check_finding_code(msg), actual);
    }
}

#[test]
fn test_classify_resolve_finding_code_all_patterns() {
    let cases = [
        ("network fetch is disabled by --offline", "RES-PRECONDITION"),
        ("no spec files found in target", "RES-PRECONDITION"),
        ("duplicate mapping key 'facts'", "RES-YAML"),
        (
            "f1: line range is outside the file's 10 lines",
            "RES-ANCHOR-MISMATCH",
        ),
        (
            "f1: symbol 'init_hw' is not near the cited range",
            "RES-ANCHOR-MISMATCH",
        ),
        (
            "claim hex values absent from cited lines: 0xff",
            "RES-ANCHOR-MISMATCH",
        ),
        (
            "register offset absent from cited PDF pages: 0x100",
            "RES-ANCHOR-MISMATCH",
        ),
        (
            "f1: stale anchor; re-verify before resolving",
            "RES-ANCHOR-MISMATCH",
        ),
        ("document sha256 mismatch for manual.pdf", "RES-DOC-INDEX"),
        ("missing .index.yaml for cited section 4.2", "RES-DOC-INDEX"),
        (
            "f1: pin must be a full lowercase commit id",
            "RES-GIT-SOURCE",
        ),
        (
            "f1: repository URL must be an https:// URL",
            "RES-GIT-SOURCE",
        ),
        ("unused --repo mapping 'extra'", "RES-GIT-SOURCE"),
        ("unexpected resolution condition", "RES-GENERAL"),
    ];

    for (msg, expected_code) in cases {
        let actual = classify_resolve_finding_code(msg);
        assert!(
            !actual.is_empty(),
            "classify_resolve_finding_code returned empty code for: {msg}"
        );
        assert_eq!(
            actual, expected_code,
            "unexpected resolve code for message: {msg}"
        );
        // Verify determinism across repeated calls
        assert_eq!(classify_resolve_finding_code(msg), actual);
    }
}

#[test]
fn test_check_json_and_diag_out_on_failing_fixtures() {
    let bad_root = fixtures_dir().join("check/bad_root");
    let bad_root_str = bad_root.to_str().unwrap();

    // 1. `hwspecs check --json` on failing fixture emits non-empty `code` on every finding
    let (rc_json, out_json, err_json) = run_cli(&["check", "--json", bad_root_str]);
    assert_eq!(rc_json, 1, "expected exit 1 on bad_root, err={err_json}");
    let parsed_json: Value =
        serde_json::from_str(&out_json).expect("check --json output must be valid JSON");
    assert_eq!(parsed_json["ok"], false);
    let findings = parsed_json["findings"]
        .as_array()
        .expect("findings must be an array");
    assert!(
        !findings.is_empty(),
        "expected findings on bad_root fixture"
    );
    for f in findings {
        let code = f
            .get("code")
            .and_then(Value::as_str)
            .unwrap_or_else(|| panic!("finding missing string 'code': {f}"));
        assert!(!code.is_empty(), "finding 'code' must be non-empty: {f}");
        assert!(
            code.starts_with("CHK-"),
            "check finding code must start with CHK-: {code}"
        );
    }

    // 2. `hwspecs check --diag-out <path>` without `--json` keeps stdout/stderr in normal text
    //    mode while writing identical JSON (with `code` on every finding) to `<path>`
    let tmp = TempDir::new().unwrap();
    let diag_path = tmp.path().join("nested").join("check-diag.json");
    let diag_str = diag_path.to_str().unwrap();

    let (rc_text, out_text, err_text) = run_cli(&["check", "--diag-out", diag_str, bad_root_str]);
    assert_eq!(rc_text, 1);
    assert!(err_text.is_empty(), "unexpected stderr: {err_text}");
    assert!(
        out_text.contains("root(s), ") && out_text.contains("error(s)"),
        "expected human-readable summary on stdout, got: {out_text}"
    );
    // Human-readable Display format must remain `path:line:col: level: message`
    assert!(
        !out_text.contains("CHK-"),
        "human-readable text output must not embed rule codes: {out_text}"
    );

    let diag_raw = fs::read_to_string(&diag_path).expect("diag-out file must be written");
    let diag_val: Value =
        serde_json::from_str(&diag_raw).expect("diag-out file must contain valid JSON");
    assert_eq!(
        diag_val, parsed_json,
        "--diag-out JSON must match --json output"
    );

    // 3. Precondition / usage error on `check --diag-out` also populates `code`
    let usage_diag = tmp.path().join("check-usage-diag.json");
    let (rc_usage, _out_u, err_u) = run_cli(&["check", "--diag-out", usage_diag.to_str().unwrap()]);
    assert_eq!(rc_usage, 2);
    assert!(err_u.contains("at least one root directory is required"));
    let usage_val: Value = serde_json::from_str(&fs::read_to_string(&usage_diag).unwrap()).unwrap();
    assert_eq!(
        usage_val["findings"][0]["code"].as_str(),
        Some("CHK-PRECONDITION")
    );
}

#[test]
fn test_resolve_json_and_diag_out_on_failing_fixtures() {
    let tmp = TempDir::new().unwrap();
    let repo_dir = tmp.path().join("repo");
    fs::create_dir_all(&repo_dir).unwrap();

    let git_env = [
        ("GIT_AUTHOR_NAME", "Test"),
        ("GIT_AUTHOR_EMAIL", "test@users.noreply.github.com"),
        ("GIT_COMMITTER_NAME", "Test"),
        ("GIT_COMMITTER_EMAIL", "test@users.noreply.github.com"),
    ];
    assert!(Command::new("git")
        .args(["init", "-q"])
        .current_dir(&repo_dir)
        .envs(git_env)
        .status()
        .unwrap()
        .success());
    fs::write(
        repo_dir.join("driver.c"),
        "// SPDX-License-Identifier: BSD-3-Clause\nint init_hw(void) { return 0x10; }\n",
    )
    .unwrap();
    assert!(Command::new("git")
        .args(["add", "driver.c"])
        .current_dir(&repo_dir)
        .envs(git_env)
        .status()
        .unwrap()
        .success());
    assert!(Command::new("git")
        .args(["commit", "-q", "-m", "init"])
        .current_dir(&repo_dir)
        .envs(git_env)
        .status()
        .unwrap()
        .success());
    let commit = String::from_utf8(
        Command::new("git")
            .args(["rev-parse", "HEAD"])
            .current_dir(&repo_dir)
            .output()
            .unwrap()
            .stdout,
    )
    .unwrap()
    .trim()
    .to_string();

    // Spec with multiple failing/warning resolve conditions:
    // - f-bad-range: line range outside file (error -> RES-ANCHOR-MISMATCH)
    // - f-bad-hex: claim hex 0x99 absent from cited lines (warning -> RES-ANCHOR-MISMATCH)
    let spec_path = tmp.path().join("bad_resolve.spec.yaml");
    fs::write(
        &spec_path,
        format!(
            r#"format: 2
kind: chip
id: bad-resolve
name: Bad Resolve Fixture
resources:
  repos:
    - name: drv
      url: https://example.invalid/drv
      commit: "{commit}"
      license: BSD-3-Clause
      files:
        - path: driver.c
          license_from: spdx-line
facts:
  - id: f-bad-range
    section: identity
    title: Bad range
    claim: Out of range anchor.
    support:
      - class: src
        anchors:
          - repo: drv
            path: driver.c
            lines: [10, 20]
  - id: f-bad-hex
    section: identity
    title: Missing hex
    claim: Returns 0x99.
    support:
      - class: src
        anchors:
          - repo: drv
            path: driver.c
            lines: [2, 2]
            symbol: init_hw
"#
        ),
    )
    .unwrap();

    let repo_arg = format!("drv={}", repo_dir.display());
    let spec_str = spec_path.to_str().unwrap();

    // 1. `hwspecs resolve --json` on failing fixture emits non-empty `code` on every finding
    let (rc_json, out_json, err_json) =
        run_cli(&["resolve", "--json", spec_str, "--repo", &repo_arg]);
    assert_eq!(rc_json, 1, "expected exit 1, err={err_json}");
    let parsed_json: Value =
        serde_json::from_str(&out_json).expect("resolve --json output must be valid JSON");
    assert_eq!(parsed_json["ok"], false);
    let findings = parsed_json["findings"]
        .as_array()
        .expect("findings must be an array");
    assert_eq!(findings.len(), 2, "expected 2 findings: {findings:?}");
    for f in findings {
        let code = f
            .get("code")
            .and_then(Value::as_str)
            .unwrap_or_else(|| panic!("resolve finding missing 'code': {f}"));
        assert!(!code.is_empty(), "resolve finding code must not be empty");
        assert_eq!(code, "RES-ANCHOR-MISMATCH");
    }

    // 2. `hwspecs resolve --diag-out <path>` without `--json` keeps stdout/stderr in normal text
    //    mode while writing valid JSON (with `code` on findings) to `<path>`
    let diag_path = tmp.path().join("resolve-diag.json");
    let diag_str = diag_path.to_str().unwrap();
    let (rc_text, out_text, err_text) = run_cli(&[
        "resolve",
        "--diag-out",
        diag_str,
        spec_str,
        "--repo",
        &repo_arg,
    ]);
    assert_eq!(rc_text, 1);
    assert!(err_text.is_empty(), "unexpected stderr: {err_text}");
    assert!(
        out_text.contains("f-bad-range: line range is outside the file's")
            && out_text.contains("1 anchor(s) resolved, 0 skipped"),
        "expected human-readable resolve output on stdout, got: {out_text}"
    );
    assert!(
        !out_text.contains("RES-"),
        "human-readable resolve output must not embed rule codes: {out_text}"
    );

    let diag_val: Value = serde_json::from_str(&fs::read_to_string(&diag_path).unwrap()).unwrap();
    assert_eq!(diag_val, parsed_json);

    // 3. Precondition error on `resolve --diag-out` populates `code`
    let pre_diag = tmp.path().join("resolve-pre-diag.json");
    let missing_target = tmp.path().join("nonexistent-dir");
    let (rc_pre, _out_pre, err_pre) = run_cli(&[
        "resolve",
        "--diag-out",
        pre_diag.to_str().unwrap(),
        missing_target.to_str().unwrap(),
    ]);
    assert_eq!(rc_pre, 2);
    assert!(err_pre.contains("usage error:"));
    let pre_val: Value = serde_json::from_str(&fs::read_to_string(&pre_diag).unwrap()).unwrap();
    assert_eq!(pre_val["ok"], false);
    let pre_code = pre_val["findings"][0]["code"]
        .as_str()
        .expect("precondition finding must have 'code'");
    assert!(!pre_code.is_empty());
}

#[test]
fn test_status_diag_out_and_finding_codes() {
    let bad_root = fixtures_dir().join("check/bad_root");
    let bad_root_str = bad_root.to_str().unwrap();
    let tmp = TempDir::new().unwrap();
    let diag_path = tmp.path().join("status-diag.json");
    let diag_str = diag_path.to_str().unwrap();

    let (rc_text, out_text, err_text) = run_cli(&["status", "--diag-out", diag_str, bad_root_str]);
    assert_eq!(rc_text, 1);
    assert!(err_text.is_empty());
    assert!(
        !out_text.trim().starts_with('{'),
        "status without --json must emit human-readable text on stdout: {out_text}"
    );

    let diag_val: Value = serde_json::from_str(&fs::read_to_string(&diag_path).unwrap()).unwrap();
    assert_eq!(diag_val["ok"], false);
    let findings = diag_val["findings"]
        .as_array()
        .expect("status findings must be an array");
    assert!(!findings.is_empty());
    for f in findings {
        let code = f
            .get("code")
            .and_then(Value::as_str)
            .expect("status finding must have string 'code'");
        assert!(!code.is_empty());
        assert!(code.starts_with("CHK-"));
    }
}
