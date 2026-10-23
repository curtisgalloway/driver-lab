// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Subcommands that exist in the CLI surface but have no implementation must say so on stderr
//! and exit non-zero, never report success after doing no work.

use hwspecs::diagnostic::{EXIT_NOT_IMPLEMENTED, EXIT_OK};
use std::fs;

/// Runs `hwspecs` with `args` and returns `(exit code, stdout, stderr)`.
fn run(args: &[&str]) -> (i32, String, String) {
    let mut argv = vec!["hwspecs"];
    argv.extend_from_slice(args);
    let mut out = Vec::new();
    let mut err = Vec::new();
    let rc = hwspecs::run_from_args(argv, &mut out, &mut err);
    (
        rc,
        String::from_utf8(out).expect("stdout is UTF-8"),
        String::from_utf8(err).expect("stderr is UTF-8"),
    )
}

/// Asserts the not-implemented contract: non-zero exit, the exact stderr line, empty stdout.
fn assert_not_implemented(args: &[&str], command: &str) {
    let (rc, stdout, stderr) = run(args);
    assert_ne!(rc, EXIT_OK, "{args:?} exited 0; stderr: {stderr}");
    assert_eq!(rc, EXIT_NOT_IMPLEMENTED, "{args:?}; stderr: {stderr}");
    assert_eq!(
        stderr,
        format!("{command}: not implemented\n"),
        "{args:?} stderr"
    );
    assert_eq!(stdout, "", "{args:?} wrote to stdout");
}

#[test]
fn not_implemented_exit_code_is_nonzero() {
    assert_ne!(EXIT_NOT_IMPLEMENTED, EXIT_OK);
}

#[test]
fn verify_prepare_reports_not_implemented() {
    assert_not_implemented(&["verify", "prepare", "--phase", "blind"], "verify prepare");
    // The documented invocation shape must reach the same message, not a usage error.
    assert_not_implemented(
        &[
            "verify",
            "prepare",
            "widget-root",
            "--spec",
            "widget",
            "--phase",
            "claims",
            "--shard",
            "1/2",
            "--repo",
            "widget=widget-checkout",
            "--out",
            "packet.json",
        ],
        "verify prepare",
    );
}

#[test]
fn verify_submit_blind_reports_not_implemented() {
    assert_not_implemented(&["verify", "submit-blind"], "verify submit-blind");
    assert_not_implemented(
        &[
            "verify",
            "submit-blind",
            "--packet",
            "packet.json",
            "--input",
            "blind.yaml",
        ],
        "verify submit-blind",
    );
}

#[test]
fn verify_assemble_reports_not_implemented() {
    assert_not_implemented(&["verify", "assemble"], "verify assemble");
    assert_not_implemented(
        &[
            "verify",
            "assemble",
            "widget-root",
            "--packet",
            "packet.json",
            "--primary",
            "r1.yaml",
        ],
        "verify assemble",
    );
}

#[test]
fn assemble_reports_not_implemented_and_writes_nothing() {
    let dir = tempfile::TempDir::new().expect("temp dir");
    let target = dir.path().join("widget.spec.yaml");
    let original = "schema: hardware-spec/2\nfacts: {}\n";
    fs::write(&target, original).expect("write target");
    let slice = dir.path().join("widget.facts.yaml");
    fs::write(
        &slice,
        "facts:\n  widget-ctrl-reset:\n    claim: synthetic\n",
    )
    .expect("write slice");

    assert_not_implemented(
        &[
            "assemble",
            target.to_str().unwrap(),
            "--from",
            slice.to_str().unwrap(),
        ],
        "assemble",
    );
    assert_eq!(fs::read_to_string(&target).unwrap(), original);
}

#[test]
fn assemble_does_not_panic_on_bad_input() {
    // No arguments at all must also reach the report, not a usage error.
    assert_not_implemented(&["assemble"], "assemble");

    let dir = tempfile::TempDir::new().expect("temp dir");
    let target = dir.path().join("widget.spec.yaml");
    let missing = dir.path().join("missing.facts.yaml");
    // Valid YAML that is not JSON: the previous code parsed it with serde_json and panicked.
    let yaml = dir.path().join("yaml.facts.yaml");
    fs::write(&yaml, "facts:\n  widget-a: {claim: x}\n").unwrap();
    let garbage = dir.path().join("garbage.facts.yaml");
    fs::write(&garbage, [0xff_u8, 0xfe, b'{', b':']).unwrap();

    for slice in [&missing, &yaml, &garbage] {
        assert_not_implemented(
            &[
                "assemble",
                target.to_str().unwrap(),
                "--from",
                slice.to_str().unwrap(),
            ],
            "assemble",
        );
    }
}

#[test]
fn campaign_sweep_reports_not_implemented() {
    assert_not_implemented(&["campaign", "sweep"], "campaign sweep");
    assert_not_implemented(
        &["campaign", "sweep", "widget-campaign", "--json"],
        "campaign sweep",
    );
    assert_not_implemented(
        &[
            "campaign",
            "sweep",
            "widget-campaign",
            "--registry",
            "sources.yaml",
            "--deployment",
            "deployment.yaml",
        ],
        "campaign sweep",
    );
}

#[test]
fn campaign_contract_check_reports_not_implemented() {
    assert_not_implemented(&["campaign", "contract-check"], "campaign contract-check");
    assert_not_implemented(
        &[
            "campaign",
            "contract-check",
            "--source-json",
            "source.json",
            "--run-dir",
            "run",
            "--json",
        ],
        "campaign contract-check",
    );
}

#[test]
fn campaign_stopping_reports_not_implemented() {
    assert_not_implemented(&["campaign", "stopping"], "campaign stopping");
    assert_not_implemented(
        &["campaign", "stopping", "widget-campaign", "--json"],
        "campaign stopping",
    );
}

#[test]
fn campaign_pinned_file_adapter_reports_not_implemented() {
    assert_not_implemented(
        &[
            "campaign",
            "pinned-file-adapter",
            "sources.yaml",
            "widget",
            "--write",
            "--json",
        ],
        "campaign pinned-file-adapter",
    );
}
