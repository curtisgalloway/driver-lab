use std::process::Command;

fn run_test_cli(args: Vec<&str>) -> std::process::Output {
    let bin = env!("CARGO_BIN_EXE_driver-lab");
    let mut cmd = Command::new(bin);
    cmd.args(args);
    cmd.output().expect("failed to execute process")
}

#[test]
fn test_hex_values_extraction() {
    let text1 = "The address is 0x1234_5678 and also 4438_0000h.";
    let res1 = driver_lab::docresolve::hex_values(text1);
    assert_eq!(res1, vec!["0x1234_5678", "4438_0000h"]);
}

#[test]
fn test_locator_pattern() {
    let pat1 = driver_lab::docresolve::locator_pattern("table", "Table 1.2");
    assert!(pat1.is_match("Table 1.2 is shown"));

    // Issue #166: captions and prose references followed by a period
    let pat_table = driver_lab::docresolve::locator_pattern("table", "9-12");
    assert!(pat_table.is_match("Table 9-12. Standard Interface Descriptor"));
    assert!(pat_table.is_match("Table 9-12: Standard Interface Descriptor"));
    assert!(pat_table.is_match("Table 9-12 Standard Interface Descriptor"));

    let pat_table_end = driver_lab::docresolve::locator_pattern("table", "11-15");
    assert!(pat_table_end.is_match("outlined in Table 11-15."));
    assert!(pat_table_end.is_match("(see Table 11-15.)"));

    let pat_fig = driver_lab::docresolve::locator_pattern("figure", "9-4");
    assert!(pat_fig.is_match("Figure 9-4. Information Returned by a GetStatus() Request"));

    let pat_endash = driver_lab::docresolve::locator_pattern("table", "2-3");
    assert!(pat_endash.is_match("Table 2–3. USBLEGSUP Register Bit Definitions"));
    let pat_endash_rev = driver_lab::docresolve::locator_pattern("table", "2–3");
    assert!(pat_endash_rev.is_match("Table 2-3. USBLEGSUP Register Bit Definitions"));

    let pat_sec = driver_lab::docresolve::locator_pattern("section", "9.4.5");
    assert!(pat_sec.is_match("see section 9.4.5."));
    assert!(pat_sec.is_match("9.4.5. GetStatus"));
    assert!(!pat_sec.is_match("Section 1.9.4.5"));
    assert!(!pat_sec.is_match("Section 19.4.5"));

    // Prefix section or table numbers must not match longer numbers
    let pat_sec_prefix = driver_lab::docresolve::locator_pattern("section", "9.4");
    assert!(!pat_sec_prefix.is_match("Section 9.4.5 Standard Requests"));
    assert!(pat_sec_prefix.is_match("Section 9.4. Standard Requests"));
    assert!(pat_sec_prefix.is_match("see Section 9.4."));

    let pat_table_prefix = driver_lab::docresolve::locator_pattern("table", "9-1");
    assert!(!pat_table_prefix.is_match("Table 9-12. Standard Interface Descriptor"));
    assert!(!pat_table_prefix.is_match("Table 9-1-2. Subtable"));
    assert!(pat_table_prefix.is_match("Table 9-1. Standard Device Requests"));
    assert!(pat_table_prefix.is_match("Table 9-1-A. Variant"));
}

#[test]
fn test_bf_usb_1() {
    let out = run_test_cli(vec!["resolve", "--help"]);
    assert!(out.status.success());
}
#[test]
fn test_bf_usb_2() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_imx_iss_6() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_imx_iss_7() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_imx_13() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_imx_16() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_imx_17() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_gw_26() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}

#[test]
fn test_issue_181_verify_schema_allows_unpinned_fetch_ok_source() {
    use std::fs;
    let tmp = tempfile::tempdir().unwrap();
    let valid_path = tmp.path().join("gw9200.verify.yaml");
    let valid_yaml = r#"# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
format: 2
spec: gw9200
spec_file: gw9200.spec.yaml
spec_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
canonical: fact-v1
sources:
  - name: gw-wiki-catalina
    url: https://trac.gateworks.com/wiki/catalina
    fetch: ok
    note: Online vendor wiki retrieved during verification
  - name: imx95-rm
    sha256: "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
    fetch: ok
summary:
  pass: 0
  fail: 0
  unverifiable: 0
  gap: 0
  adjudicate: 0
verdicts: {}
"#;
    fs::write(&valid_path, valid_yaml).unwrap();
    let out = run_test_cli(vec!["--json", "validate", valid_path.to_str().unwrap()]);
    assert!(
        out.status.success(),
        "validate should accept unpinned source with url and fetch: ok: {}",
        String::from_utf8_lossy(&out.stdout)
    );

    // Unpinned source with fetch != "ok" must be rejected
    let invalid_blocked_path = tmp.path().join("blocked.verify.yaml");
    let invalid_blocked_yaml = valid_yaml.replace("fetch: ok\n    note:", "fetch: blocked\n    note:");
    fs::write(&invalid_blocked_path, invalid_blocked_yaml).unwrap();
    let out_blocked = run_test_cli(vec![
        "--json",
        "validate",
        invalid_blocked_path.to_str().unwrap(),
    ]);
    assert!(
        !out_blocked.status.success(),
        "validate must reject unpinned source when fetch is not ok"
    );

    // Unpinned source without url must be rejected
    let invalid_no_url_path = tmp.path().join("nourl.verify.yaml");
    let invalid_no_url_yaml =
        valid_yaml.replace("    url: https://trac.gateworks.com/wiki/catalina\n", "");
    fs::write(&invalid_no_url_path, invalid_no_url_yaml).unwrap();
    let out_no_url = run_test_cli(vec![
        "--json",
        "validate",
        invalid_no_url_path.to_str().unwrap(),
    ]);
    assert!(
        !out_no_url.status.success(),
        "validate must reject unpinned source without url"
    );
}

#[test]
fn test_issue_181_resolve_non_pdf_docs_silences_pdf_skip_warnings() {
    use sha2::{Digest, Sha256};
    use std::fs;

    let tmp = tempfile::tempdir().unwrap();
    let docs_dir = tmp.path().join("docs");
    fs::create_dir_all(&docs_dir).unwrap();

    let wiki_text = "# Catalina Peripherals\nI2C2 is routed to the GSC at 0x20.\n";
    let wiki_sha = hex::encode(Sha256::digest(wiki_text.as_bytes()));
    fs::write(docs_dir.join("gw-wiki-pinned"), wiki_text).unwrap();

    let spec_path = tmp.path().join("board.spec.yaml");
    let spec_yaml = format!(
        r#"# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
format: 2
kind: board
id: test-board
name: Test Board
soc: test-soc
triggers:
  - Test Board
resources:
  documents:
    - name: gw-wiki-pinned
      title: Gateworks Catalina Wiki (Pinned Cache)
      class: doc
      access: public
      url: https://trac.gateworks.com/wiki/catalina
      sha256: "{wiki_sha}"
      fetch: ok
    - name: gw-wiki-online
      title: Gateworks Catalina Wiki (Online Unpinned)
      class: doc
      access: public
      url: https://trac.gateworks.com/wiki/catalina/gsc
      fetch: ok
facts:
  - id: gsc-i2c-addr
    section: quick-facts
    claim: "The GSC responds on I2C2 at 7-bit address 0x20."
    authority: doc
    support:
      - class: doc
        doc: gw-wiki-pinned
        at:
          - heading: "Catalina Peripherals"
      - class: doc
        doc: gw-wiki-online
        at:
          - heading: "GSC Overview"
"#
    );
    fs::write(&spec_path, spec_yaml).unwrap();

    let out = run_test_cli(vec![
        "--json",
        "resolve",
        spec_path.to_str().unwrap(),
        "--docs-dir",
        docs_dir.to_str().unwrap(),
    ]);
    assert!(
        out.status.success(),
        "resolve failed: {}",
        String::from_utf8_lossy(&out.stdout)
    );
    let res: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(res["ok"], true);
    let findings = res["findings"].as_array().unwrap();
    assert!(
        findings.is_empty(),
        "expected no PDF-skip warnings for non-PDF docs, got: {findings:?}"
    );
    assert_eq!(res["documents_resolved"], 0);
    assert_eq!(res["documents_skipped"], 2);

    // Corrupting the local pinned non-PDF file must still fail sha256 verification
    fs::write(docs_dir.join("gw-wiki-pinned"), "tampered content").unwrap();
    let out_bad = run_test_cli(vec![
        "--json",
        "resolve",
        spec_path.to_str().unwrap(),
        "--docs-dir",
        docs_dir.to_str().unwrap(),
    ]);
    assert!(!out_bad.status.success());
    let res_bad: serde_json::Value = serde_json::from_slice(&out_bad.stdout).unwrap();
    assert_eq!(res_bad["ok"], false);
    let bad_findings = res_bad["findings"].as_array().unwrap();
    assert!(
        bad_findings.iter().any(|f| {
            f["level"] == "error"
                && f["message"]
                    .as_str()
                    .unwrap_or("")
                    .contains("document gw-wiki-pinned: sha256 mismatch")
        }),
        "expected sha256 mismatch error on tampered non-PDF doc, got: {bad_findings:?}"
    );
}

#[test]
fn test_issue_182_claim_hex_values_with_co_cited_doc_support() {
    use sha2::{Digest, Sha256};
    use std::fs;
    use std::process::Command;

    let tmp = tempfile::tempdir().unwrap();
    let repo_dir = tmp.path().join("repo");
    fs::create_dir_all(&repo_dir).unwrap();

    let run_git = |args: &[&str]| {
        let out = Command::new("git")
            .args(args)
            .current_dir(&repo_dir)
            .output()
            .unwrap();
        assert!(
            out.status.success(),
            "git {:?} failed: {}",
            args,
            String::from_utf8_lossy(&out.stderr)
        );
        String::from_utf8_lossy(&out.stdout).trim().to_string()
    };

    run_git(&["init", "-q"]);
    run_git(&["config", "user.name", "Test"]);
    run_git(&["config", "user.email", "test@example.com"]);
    let dts_text = "// SPDX-License-Identifier: (GPL-2.0-only OR MIT)\n&lpi2c2 {\n    gsc: gsc@20 {\n        compatible = \"gw,gsc\";\n        reg = <0x20>;\n    };\n};\n";
    fs::write(repo_dir.join("board.dts"), dts_text).unwrap();
    run_git(&["add", "board.dts"]);
    run_git(&["commit", "-q", "-m", "initial"]);
    let commit = run_git(&["rev-parse", "HEAD"]);

    let docs_dir = tmp.path().join("docs");
    fs::create_dir_all(&docs_dir).unwrap();
    let wiki_text = "# GSC Overview\nThe GSC exposes an emulated DS1672 RTC at 0x68 on I2C2.\n";
    let wiki_sha = hex::encode(Sha256::digest(wiki_text.as_bytes()));
    fs::write(docs_dir.join("gw-wiki-gsc"), wiki_text).unwrap();

    let spec_path = tmp.path().join("board.spec.yaml");
    let spec_yaml = format!(
        r#"# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
format: 2
kind: board
id: test-board
name: Test Board
soc: test-soc
triggers:
  - Test Board
resources:
  documents:
    - name: gw-wiki-gsc
      title: Gateworks GSC Wiki
      class: doc
      access: public
      url: https://trac.gateworks.com/wiki/gsc
      sha256: "{wiki_sha}"
      fetch: ok
  repos:
    - name: kernel
      url: https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git
      commit: "{commit}"
      license: GPL-2.0-only OR MIT
      role: source
      files:
        - path: board.dts
          license_from: spdx-line
facts:
  - id: gsc-rtc-co-cited
    section: quick-facts
    claim: "The GSC responds on I2C2 at primary address 0x20 and emulates an RTC at 0x68."
    authority: doc
    support:
      - class: doc
        doc: gw-wiki-gsc
        at:
          - heading: "GSC Overview"
      - class: DT
        anchors:
          - repo: kernel
            path: board.dts
            lines: [2, 6]
  - id: dt-only-missing-hex
    section: quick-facts
    claim: "The GSC node at 0x20 also declares secondary address 0x51 in the DT."
    authority: DT
    support:
      - class: DT
        anchors:
          - repo: kernel
            path: board.dts
            lines: [2, 6]
  - id: co-cited-missing-in-both
    section: quick-facts
    claim: "The GSC at 0x20 also exposes an undocumented subdevice at 0x99."
    authority: doc
    support:
      - class: doc
        doc: gw-wiki-gsc
        at:
          - heading: "GSC Overview"
      - class: DT
        anchors:
          - repo: kernel
            path: board.dts
            lines: [2, 6]
"#
    );
    fs::write(&spec_path, spec_yaml).unwrap();
    let repo_arg = format!("kernel={}", repo_dir.display());

    // 1. Without --docs-dir: gsc-rtc-co-cited and co-cited-missing-in-both co-cite class: doc (unextracted),
    //    so neither warns; dt-only-missing-hex cites only DT, so 0x51 MUST warn.
    let out_no_docs = run_test_cli(vec![
        "--json",
        "resolve",
        spec_path.to_str().unwrap(),
        "--repo",
        &repo_arg,
    ]);
    assert!(
        out_no_docs.status.success(),
        "resolve failed: {}",
        String::from_utf8_lossy(&out_no_docs.stdout)
    );
    let res_no_docs: serde_json::Value = serde_json::from_slice(&out_no_docs.stdout).unwrap();
    let findings_no_docs = res_no_docs["findings"].as_array().unwrap();
    assert_eq!(
        findings_no_docs.len(),
        1,
        "expected exactly 1 hex warning (on dt-only-missing-hex), got: {findings_no_docs:?}"
    );
    assert!(
        findings_no_docs[0]["message"]
            .as_str()
            .unwrap_or("")
            .contains("claim hex values absent from cited lines: 0x51"),
        "unexpected warning message: {:?}",
        findings_no_docs[0]
    );

    // 2. With --docs-dir: gw-wiki-gsc text is extracted and contains 0x68 (so gsc-rtc-co-cited is clean),
    //    while 0x99 is absent from both DT and gw-wiki-gsc (so co-cited-missing-in-both warns alongside dt-only-missing-hex).
    let out_with_docs = run_test_cli(vec![
        "--json",
        "resolve",
        spec_path.to_str().unwrap(),
        "--repo",
        &repo_arg,
        "--docs-dir",
        docs_dir.to_str().unwrap(),
    ]);
    assert!(out_with_docs.status.success());
    let res_with_docs: serde_json::Value = serde_json::from_slice(&out_with_docs.stdout).unwrap();
    let findings_with_docs = res_with_docs["findings"].as_array().unwrap();
    assert_eq!(
        findings_with_docs.len(),
        2,
        "expected warnings on dt-only-missing-hex (0x51) and co-cited-missing-in-both (0x99), got: {findings_with_docs:?}"
    );
    assert!(
        findings_with_docs
            .iter()
            .any(|f| f["message"].as_str().unwrap_or("").contains("0x51"))
    );
    assert!(
        findings_with_docs
            .iter()
            .any(|f| f["message"].as_str().unwrap_or("").contains("0x99"))
    );
}
