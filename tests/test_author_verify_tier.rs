// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use driver_lab::author::{check_auto5_warnings, check_auto6_canonical_register_source};
use serde_json::json;
use std::fs;
use std::path::PathBuf;

#[test]
fn test_auto5_103() {
    let fact = json!({
        "meaning": "names a table",
    });
    let w = check_auto5_warnings(&fact);
    assert!(w.contains(&"#103".to_string()));
}

#[test]
fn test_auto5_105() {
    let fact = json!({
        "action": "wait for status",
    });
    let w = check_auto5_warnings(&fact);
    assert!(w.contains(&"#105".to_string()));
}

#[test]
fn test_auto5_150() {
    let fact = json!({
        "section": "target",
    });
    let w = check_auto5_warnings(&fact);
    assert!(w.contains(&"#150".to_string()));
}

#[test]
fn test_auto6() {
    let fact = json!({
        "repo": "",
    });
    let w = check_auto6_canonical_register_source(&fact);
    assert!(w.contains(&"empty repo".to_string()));
}

#[test]
fn test_tier_calibration() {
    let mut path = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    path.push("evidence");
    path.push("CR6b.md");
    let cr6b = fs::read_to_string(path).unwrap();
    assert!(cr6b.contains("84: **R 14** (12 findings), **E 41**, **W 28**"));
    assert!(cr6b.contains("16: the new reader asked for more than the spec's rules require"));
    assert!(cr6b.contains("19: no PDF (micro-sign rendering)"));
}
