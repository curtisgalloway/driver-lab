// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Conformance tests for the claim-to-citation binding checks in `hwspecs resolve`
//! (`tests/conformance/claim-binding/cases.json`, synthetic widget fixture).

use regex::Regex;
use serde_json::Value;
use std::fs;
use std::path::Path;
use std::process::Command;
use tempfile::TempDir;

const FIXTURE_DIR: &str = "tests/conformance/claim-binding";

fn git(repo: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
        .args(args)
        .current_dir(repo)
        .env("GIT_AUTHOR_NAME", "Test")
        .env("GIT_AUTHOR_EMAIL", "test@users.noreply.github.com")
        .env("GIT_COMMITTER_NAME", "Test")
        .env("GIT_COMMITTER_EMAIL", "test@users.noreply.github.com")
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "git {args:?} failed: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stdout).trim().to_string()
}

/// Builds the scratch repository and spec; returns (tempdir, spec path, repo binding, cases).
fn setup() -> (TempDir, String, String, Value) {
    let cases: Value =
        serde_json::from_str(&fs::read_to_string(format!("{FIXTURE_DIR}/cases.json")).unwrap())
            .unwrap();
    let fixture = &cases["fixture"];
    let tmp = TempDir::new().unwrap();
    let repo = tmp.path().join("repo");
    fs::create_dir_all(&repo).unwrap();
    git(&repo, &["init", "-q"]);
    for f in fixture["files"].as_array().unwrap() {
        let name = f.as_str().unwrap();
        fs::copy(format!("{FIXTURE_DIR}/{name}"), repo.join(name)).unwrap();
        git(&repo, &["add", name]);
    }
    git(&repo, &["commit", "-q", "-m", "fixture"]);
    let commit = git(&repo, &["rev-parse", "HEAD"]);
    let template = fs::read_to_string(format!(
        "{FIXTURE_DIR}/{}",
        fixture["spec"].as_str().unwrap()
    ))
    .unwrap();
    let spec = template.replace(fixture["commit_placeholder"].as_str().unwrap(), &commit);
    let spec_path = tmp.path().join("widget.spec.yaml");
    fs::write(&spec_path, spec).unwrap();
    let binding = format!("{}={}", fixture["repo"].as_str().unwrap(), repo.display());
    let spec_str = spec_path.to_str().unwrap().to_string();
    (tmp, spec_str, binding, cases)
}

fn resolve(spec: &str, binding: &str, strict: bool) -> (i32, Value) {
    let mut args = vec!["--json", "resolve", spec, "--repo", binding];
    if strict {
        args.push("--strict-claims");
    }
    let out = Command::new(env!("CARGO_BIN_EXE_hwspecs"))
        .args(&args)
        .output()
        .unwrap();
    let parsed: Value = serde_json::from_slice(&out.stdout).unwrap_or_else(|e| {
        panic!(
            "resolve output is not JSON ({e}): {}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        )
    });
    (out.status.code().unwrap_or(-1), parsed)
}

fn check_mode(cases: &Value, result: &Value, key: &str) {
    let findings = result["findings"].as_array().unwrap();
    let ids: Vec<&str> = cases["cases"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| c["id"].as_str().unwrap())
        .collect();
    for f in findings {
        let msg = f["message"].as_str().unwrap();
        assert!(
            ids.iter().any(|id| msg.starts_with(&format!("{id}: "))),
            "{key}: finding not attributed to any case: {f}"
        );
    }
    for case in cases["cases"].as_array().unwrap() {
        let id = case["id"].as_str().unwrap();
        let prefix = format!("{id}: ");
        let got: Vec<&Value> = findings
            .iter()
            .filter(|f| f["message"].as_str().unwrap().starts_with(&prefix))
            .collect();
        let want = case[key].as_array().unwrap();
        assert_eq!(
            got.len(),
            want.len(),
            "{key}: case {id}: expected {want:?}, got {got:?}"
        );
        for (g, w) in got.iter().zip(want) {
            assert_eq!(g["code"], w["code"], "{key}: case {id}: {g}");
            assert_eq!(g["level"], w["level"], "{key}: case {id}: {g}");
            let pat = Regex::new(w["message_pattern"].as_str().unwrap()).unwrap();
            let msg = g["message"].as_str().unwrap();
            assert!(
                pat.is_match(&msg[prefix.len()..]),
                "{key}: case {id}: message {msg:?} does not match {pat}"
            );
            assert_eq!(
                hwspecs::diagnostic::classify_resolve_finding_code(msg),
                w["code"].as_str().unwrap(),
                "message-based classification must agree with the emitted code"
            );
        }
    }
}

#[test]
fn claim_binding_conformance_cases() {
    let (_tmp, spec, binding, cases) = setup();

    let (rc, result) = resolve(&spec, &binding, false);
    check_mode(&cases, &result, "findings");
    assert_eq!(rc, 1, "range and ngpios findings are errors: {result}");
    assert_eq!(result["ok"], false);

    let (rc_strict, strict) = resolve(&spec, &binding, true);
    check_mode(&cases, &strict, "strict_findings");
    assert_eq!(rc_strict, 1);
}

#[test]
fn unbound_hex_alone_fails_only_under_strict_claims() {
    let (tmp, spec, binding, _cases) = setup();
    // Keep only the unrelated-hex fact.
    let text = fs::read_to_string(&spec).unwrap();
    let (head, facts) = text.split_once("facts:\n").unwrap();
    let only: String = facts
        .split("  - id: ")
        .filter(|chunk| chunk.starts_with("unrelated-hex\n"))
        .map(|chunk| format!("  - id: {chunk}"))
        .collect();
    let single = tmp.path().join("single.spec.yaml");
    fs::write(&single, format!("{head}facts:\n{only}")).unwrap();
    let single = single.to_str().unwrap();

    let (rc, result) = resolve(single, &binding, false);
    assert_eq!(rc, 0, "a warning alone must not fail resolve: {result}");
    assert_eq!(result["ok"], true);
    assert_eq!(result["findings"][0]["code"], "RES-CLAIM-HEX-UNBOUND");
    assert_eq!(result["findings"][0]["level"], "warning");

    let (rc, result) = resolve(single, &binding, true);
    assert_eq!(
        rc, 1,
        "--strict-claims makes the binding finding an error: {result}"
    );
    assert_eq!(result["findings"][0]["level"], "error");
}
