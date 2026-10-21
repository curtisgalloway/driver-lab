// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use std::fs;
use std::process::Command;
use tempfile::TempDir;

fn run_license_gate(args: &[&str]) -> (i32, String, String) {
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_hwspecs"));
    cmd.arg("license-gate");
    for a in args {
        cmd.arg(a);
    }
    let output = cmd.output().unwrap();
    (
        output.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
    )
}

#[test]
fn test_root_alone_prints_accepts_list() {
    let root = "skills/hardware-investigator/examples/roots/permissive";
    let (rc, out, _) = run_license_gate(&["--root", root]);
    assert_eq!(rc, 0);
    assert!(out.contains("accepts: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause"));
    assert!(out.contains("example-permissive"));
}

#[test]
fn test_accepted_license() {
    let root = "skills/hardware-investigator/examples/roots/permissive";
    let (rc, out, _) = run_license_gate(&["--root", root, "MIT"]);
    assert_eq!(rc, 0);
    assert!(out.contains("accepted: MIT"));
}

#[test]
fn test_refused_license_names_reason() {
    let root = "skills/hardware-investigator/examples/roots/permissive";
    let (rc, out, _) = run_license_gate(&["--root", root, "GPL-2.0-only"]);
    assert_eq!(rc, 1);
    assert!(out.contains("refused: GPL-2.0-only"));
    assert!(out.contains("root example-permissive"));
    assert!(out.contains("accepts: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause"));
}

#[test]
fn test_or_passes_when_one_side_accepted() {
    let root = "skills/hardware-investigator/examples/roots/permissive";
    let (rc, out, _) = run_license_gate(&["--root", root, "GPL-2.0-only OR MIT"]);
    assert_eq!(rc, 0, "{}", out);
}

#[test]
fn test_and_needs_both_sides() {
    let root = "skills/hardware-investigator/examples/roots/permissive";
    let (rc, out, _) = run_license_gate(&["--root", root, "GPL-2.0-only AND MIT"]);
    assert_eq!(rc, 1, "{}", out);
}

#[test]
fn test_gpl_family_is_not_interchangeable() {
    let root1 = "skills/hardware-investigator/examples/roots/gpl";
    let (rc1, out1, _) = run_license_gate(&["--root", root1, "GPL-2.0-or-later"]);
    assert_eq!(rc1, 0, "{}", out1);

    let root2 = "skills/hardware-investigator/examples/roots/permissive";
    let (rc2, out2, _) = run_license_gate(&["--root", root2, "GPL-2.0+"]);
    assert_eq!(rc2, 1, "{}", out2);
}

#[test]
fn test_one_refusal_makes_exit_one_but_all_are_reported() {
    let root = "skills/hardware-investigator/examples/roots/permissive";
    let (rc, out, _) = run_license_gate(&["--root", root, "MIT", "GPL-3.0-only"]);
    assert_eq!(rc, 1);
    assert!(out.contains("accepted: MIT"));
    assert!(out.contains("refused: GPL-3.0-only"));
}

#[test]
fn test_not_an_spdx_expression_is_refused() {
    let root = "skills/hardware-investigator/examples/roots/permissive";
    let (rc, out, _) = run_license_gate(&["--root", root, "Totally Free License"]);
    assert_eq!(rc, 1);
    assert!(out.contains("refused: Totally Free License"));
    assert!(out.contains("not an SPDX expression"));
}

#[test]
fn test_root_without_accepts_refuses_everything() {
    let tmp = TempDir::new().unwrap();
    fs::write(
        tmp.path().join("board-specs.yaml"),
        "layer: public\nname: bare\n",
    )
    .unwrap();
    let root = tmp.path().to_str().unwrap();

    let (rc1, out1, _) = run_license_gate(&["--root", root, "MIT"]);
    assert_eq!(rc1, 1);
    assert!(out1.contains("invalid spec format root marker"));

    let (rc2, _, _) = run_license_gate(&["--root", root]);
    assert_eq!(rc2, 1);
}

#[test]
fn test_empty_accepts_refuses_everything() {
    let tmp = TempDir::new().unwrap();
    fs::write(
        tmp.path().join("board-specs.yaml"),
        "format: 2\nlayer: public\nname: docs\nlicense: CC-BY-4.0\naccepts: []\n",
    )
    .unwrap();
    let root = tmp.path().to_str().unwrap();

    let (rc, out, _) = run_license_gate(&["--root", root, "MIT"]);
    assert_eq!(rc, 1);
    assert!(out.contains("accepts: none"));
}

#[test]
fn test_invalid_accepts_entry_exits_one() {
    let tmp = TempDir::new().unwrap();
    fs::write(
        tmp.path().join("board-specs.yaml"),
        "format: 2\nlayer: public\nname: bad\nlicense: MIT\naccepts: [Foo Bar, MIT]\n",
    )
    .unwrap();
    let root = tmp.path().to_str().unwrap();

    let (rc, out, _) = run_license_gate(&["--root", root, "MIT"]);
    assert_eq!(rc, 1, "{}", out);
    assert!(out.contains("error:"));
}

#[test]
fn test_invalid_markers_never_accept_a_license() {
    let valid = "format: 2\nlayer: public\nname: test\nlicense: MIT\naccepts: [MIT]\n";
    let cases = vec![
        ("format missing", valid.replace("format: 2\n", "")),
        ("format one", valid.replace("format: 2", "format: 1")),
        ("duplicate key", format!("{}accepts: []\n", valid)),
        (
            "noncanonical identifier",
            valid.replace("[MIT]", "[GPL-2.0]"),
        ),
        ("duplicate identifier", valid.replace("[MIT]", "[MIT, MIT]")),
        ("bad license", valid.replace("license: MIT", "license: Foo")),
        (
            "accepts expression",
            valid.replace("[MIT]", "[MIT OR BSD-3-Clause]"),
        ),
        ("not a mapping", "[]\n".to_string()),
        ("malformed YAML", "format: [\n".to_string()),
    ];

    let tmp = TempDir::new().unwrap();
    let marker_path = tmp.path().join("board-specs.yaml");
    let root = tmp.path().to_str().unwrap();

    for (label, text) in cases {
        fs::write(&marker_path, text).unwrap();
        let (rc, out, _) = run_license_gate(&["--root", root, "MIT"]);
        assert_eq!(rc, 1, "Case {} failed: {}", label, out);
        assert!(
            out.contains("invalid spec format root marker"),
            "Case {} failed: {}",
            label,
            out
        );
        assert!(
            !out.contains("accepted: MIT"),
            "Case {} failed: {}",
            label,
            out
        );
    }
}

// test_missing_pinned_dependencies_is_precondition_error is Python specific (missing pyyaml etc)
// so we skip it for the Rust port.

#[test]
fn test_not_a_root_is_a_usage_error() {
    let tmp = TempDir::new().unwrap();
    let root = tmp.path().to_str().unwrap();
    let (rc, _, err) = run_license_gate(&["--root", root, "MIT"]);
    assert_eq!(rc, 2);
    assert!(err.contains("not a spec root"));
}

#[test]
fn test_missing_root_argument_is_a_usage_error() {
    let (rc, _, _) = run_license_gate(&["MIT"]);
    assert_eq!(rc, 2);
}
