// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use hwspecs::docresolve::{
    hex_values, hex_values_u64, locator_pattern, section_covered_by_index,
};
use serde_json::json;
use std::collections::BTreeSet;
use std::fs;
use std::process::Command;
use tempfile::TempDir;

fn run_test_cli(args: Vec<&str>) -> std::process::Output {
    let bin = env!("CARGO_BIN_EXE_hwspecs");
    let mut cmd = Command::new(bin);
    cmd.args(args);
    cmd.output().expect("failed to execute process")
}

#[test]
fn test_hex_values_extraction() {
    let text1 = "The address is 0x1234_5678 and also 4438_0000h.";
    let res1 = hex_values(text1);
    assert_eq!(res1, vec!["0x1234_5678", "4438_0000h"]);
}

#[test]
fn test_locator_pattern() {
    let pat1 = locator_pattern("table", "Table 1.2");
    assert!(pat1.is_match("Table 1.2 is shown"));

    // Issue #166: captions and prose references followed by a period
    let pat_table = hwspecs::docresolve::locator_pattern("table", "9-12");
    assert!(pat_table.is_match("Table 9-12. Standard Interface Descriptor"));
    assert!(pat_table.is_match("Table 9-12: Standard Interface Descriptor"));
    assert!(pat_table.is_match("Table 9-12 Standard Interface Descriptor"));

    let pat_table_end = hwspecs::docresolve::locator_pattern("table", "11-15");
    assert!(pat_table_end.is_match("outlined in Table 11-15."));
    assert!(pat_table_end.is_match("(see Table 11-15.)"));

    let pat_fig = hwspecs::docresolve::locator_pattern("figure", "9-4");
    assert!(pat_fig.is_match("Figure 9-4. Information Returned by a GetStatus() Request"));

    let pat_endash = hwspecs::docresolve::locator_pattern("table", "2-3");
    assert!(pat_endash.is_match("Table 2–3. USBLEGSUP Register Bit Definitions"));
    let pat_endash_rev = hwspecs::docresolve::locator_pattern("table", "2–3");
    assert!(pat_endash_rev.is_match("Table 2-3. USBLEGSUP Register Bit Definitions"));

    let pat_sec = hwspecs::docresolve::locator_pattern("section", "9.4.5");
    assert!(pat_sec.is_match("see section 9.4.5."));
    assert!(pat_sec.is_match("9.4.5. GetStatus"));
    assert!(!pat_sec.is_match("Section 1.9.4.5"));
    assert!(!pat_sec.is_match("Section 19.4.5"));

    // Prefix section or table numbers must not match longer numbers
    let pat_sec_prefix = hwspecs::docresolve::locator_pattern("section", "9.4");
    assert!(!pat_sec_prefix.is_match("Section 9.4.5 Standard Requests"));
    assert!(pat_sec_prefix.is_match("Section 9.4. Standard Requests"));
    assert!(pat_sec_prefix.is_match("see Section 9.4."));

    let pat_table_prefix = hwspecs::docresolve::locator_pattern("table", "9-1");
    assert!(!pat_table_prefix.is_match("Table 9-12. Standard Interface Descriptor"));
    assert!(!pat_table_prefix.is_match("Table 9-1-2. Subtable"));
    assert!(pat_table_prefix.is_match("Table 9-1. Standard Device Requests"));
    assert!(pat_table_prefix.is_match("Table 9-1-A. Variant"));
}

#[test]
fn test_bf_usb_1_locator_prefix_normalization_and_trailing_punctuation() {
    let pat_prefixed = locator_pattern("table", "Table 9-2");
    let pat_bare = locator_pattern("table", "9-2");
    let pat_trailing = locator_pattern("table", "Table 16.");
    assert!(pat_prefixed.is_match("Table 9-2. Format of Setup Data"));
    assert!(pat_bare.is_match("Table 9-2. Format of Setup Data"));
    assert!(!pat_prefixed.is_match("Table 9-2-1. Sub-table"));
    assert!(pat_trailing.is_match("Table 16: Endpoint Descriptor"));
    assert!(!pat_trailing.is_match("Table 16.1: Extended Endpoint"));

    let fig_pat = locator_pattern("figure", "Figure 1-1");
    assert!(fig_pat.is_match("Figure 1-1. LPM State Transition Diagram"));
    assert!(!fig_pat.is_match("Figure 1-10. Other Diagram"));
}

#[test]
fn test_bf_usb_2_unicode_en_dash_and_ascii_hyphen_matching() {
    let pat = locator_pattern("table", "Table 2-3");
    assert!(pat.is_match("Table 2–3. USBLEGSUP Register"));
    assert!(pat.is_match("Table 2-3. USBLEGSUP Register"));
    assert!(!pat.is_match("Table 2–3–1. Subfield"));
}

#[test]
fn test_bf_imx_iss_6_line_wrapped_captions_and_index_section_span() {
    let pat = locator_pattern("table", "Table 282. Break character length");
    assert!(pat.is_match("Table 282\nBreak character length"));
    assert!(pat.is_match("Table 282. Break character length"));
    assert!(pat.is_match("Table 282:\n  Break character length"));

    let sha = "a".repeat(64);
    let idx = json!({
        "format": 2,
        "document": "imx95-rm",
        "sha256": sha,
        "sections": [
            {
                "number": "12.3.4",
                "title": "LPUART Baud Rate Generation",
                "start_page": 2578,
                "end_page": 2586
            }
        ]
    });
    assert!(
        section_covered_by_index(&idx, Some(&sha), "12.3.4", 2582, 2583).unwrap(),
        "mid-section pages 2582..2583 must be covered by verified index span 2578..2586"
    );
    assert!(section_covered_by_index(
        &idx,
        Some(&sha),
        "Section 12.3.4 LPUART Baud Rate Generation",
        2582,
        2583
    )
    .unwrap());
    assert!(
        !section_covered_by_index(&idx, Some(&sha), "12.3.4", 2590, 2591).unwrap(),
        "pages outside [2578, 2586] must not be covered"
    );
}

#[test]
fn test_bf_imx_iss_7_and_bf_imx_16_vendor_h_suffix_hex_normalization() {
    let text = "Base 4438_0000h reset 0404_0007h offsets 14h, 1Ch, and 580h in each beach.";
    let vals = hex_values_u64(text);
    let expected: BTreeSet<u64> = [0x4438_0000, 0x0404_0007, 0x14, 0x1c, 0x580]
        .into_iter()
        .collect();
    assert_eq!(
        vals, expected,
        "English words 'each'/'beach' must not parse as hex"
    );
}

#[test]
fn test_bf_imx_13_section_locator_with_trailing_period() {
    let pat = locator_pattern("section", "1.2");
    assert!(pat.is_match("1.2. Purpose"));
    assert!(pat.is_match("Section 1.2: Overview"));
    assert!(!pat.is_match("1.2.1 Detailed Scope"));
}

#[test]
fn test_bf_imx_17_stale_index_rejected_on_sha256_mismatch() {
    let idx_sha = "a".repeat(64);
    let doc_sha = "b".repeat(64);
    let idx = json!({
        "format": 2,
        "document": "imx95-rm",
        "sha256": idx_sha,
        "sections": [
            {
                "number": "12.3",
                "title": "Registers",
                "start_page": 10,
                "end_page": 20
            }
        ]
    });
    let err = section_covered_by_index(&idx, Some(&doc_sha), "12.3", 12, 12).unwrap_err();
    assert!(
        err.contains("stale index"),
        "expected stale index error on sha256 mismatch, got: {err}"
    );
}

#[test]
fn test_bf_gw_26_unused_repo_mapping_warns_without_aborting_and_env1_partial_clone_refused() {
    let tmp = TempDir::new().unwrap();
    let repo_dir = tmp.path().join("tools");
    let extra_dir = tmp.path().join("extra");
    fs::create_dir_all(&repo_dir).unwrap();
    fs::create_dir_all(&extra_dir).unwrap();

    let git_env = [
        ("GIT_AUTHOR_NAME", "Test"),
        ("GIT_AUTHOR_EMAIL", "test@users.noreply.github.com"),
        ("GIT_COMMITTER_NAME", "Test"),
        ("GIT_COMMITTER_EMAIL", "test@users.noreply.github.com"),
    ];
    for d in [&repo_dir, &extra_dir] {
        assert!(Command::new("git")
            .args(["init", "-q"])
            .current_dir(d)
            .envs(git_env)
            .status()
            .unwrap()
            .success());
        fs::write(
            d.join("driver.c"),
            "// SPDX-License-Identifier: BSD-3-Clause\nint stub_magic(void) { return 0x42; }\n",
        )
        .unwrap();
        assert!(Command::new("git")
            .args(["add", "driver.c"])
            .current_dir(d)
            .envs(git_env)
            .status()
            .unwrap()
            .success());
        assert!(Command::new("git")
            .args(["commit", "-q", "-m", "init"])
            .current_dir(d)
            .envs(git_env)
            .status()
            .unwrap()
            .success());
    }
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

    let spec_path = tmp.path().join("widget.spec.yaml");
    fs::write(
        &spec_path,
        format!(
            r#"format: 2
kind: chip
id: widget
name: Widget
resources:
  repos:
    - name: tools
      url: https://example.invalid/tools
      commit: "{commit}"
      license: BSD-3-Clause
      files:
        - path: driver.c
          license_from: spdx-line
facts:
  - id: stub-magic
    section: identity
    title: Stub magic
    claim: Returns 0x42.
    support:
      - class: src
        anchors:
          - repo: tools
            path: driver.c
            lines: [2, 2]
            symbol: stub_magic
"#
        ),
    )
    .unwrap();

    // 1. --list-repos outputs name<TAB>commit
    let mut out_list = Vec::new();
    let mut err_list = Vec::new();
    let rc_list = hwspecs::run_from_args(
        [
            "hwspecs",
            "resolve",
            "--list-repos",
            spec_path.to_str().unwrap(),
        ],
        &mut out_list,
        &mut err_list,
    );
    assert_eq!(rc_list, 0);
    assert_eq!(
        String::from_utf8_lossy(&out_list).trim(),
        format!("tools\t{commit}")
    );

    // 2. Unused --repo mapping emits a warning and exits 0 (BF-GW-26)
    let tools_arg = format!("tools={}", repo_dir.display());
    let unused_arg = format!("unused={}", extra_dir.display());
    let mut out = Vec::new();
    let mut err = Vec::new();
    let rc = hwspecs::run_from_args(
        [
            "hwspecs",
            "resolve",
            spec_path.to_str().unwrap(),
            "--repo",
            &tools_arg,
            "--repo",
            &unused_arg,
        ],
        &mut out,
        &mut err,
    );
    let out_str = String::from_utf8_lossy(&out);
    assert_eq!(rc, 0, "out={out_str} err={}", String::from_utf8_lossy(&err));
    assert!(
        out_str.contains("warning: unused --repo mapping 'unused'"),
        "expected unused --repo warning in output: {out_str}"
    );
    assert!(out_str.contains("1 anchor(s) resolved, 0 skipped"));

    // 3. Partial clone bound via --repo exits 3 (ENV-1)
    assert!(Command::new("git")
        .args(["config", "extensions.partialClone", "origin"])
        .current_dir(&repo_dir)
        .status()
        .unwrap()
        .success());
    let mut out_pc = Vec::new();
    let mut err_pc = Vec::new();
    let rc_pc = hwspecs::run_from_args(
        [
            "hwspecs",
            "resolve",
            spec_path.to_str().unwrap(),
            "--repo",
            &tools_arg,
        ],
        &mut out_pc,
        &mut err_pc,
    );
    let err_pc_str = String::from_utf8_lossy(&err_pc);
    assert_eq!(rc_pc, 3, "expected exit 3 on partial clone: {err_pc_str}");
    assert!(
        err_pc_str.contains("partial clone: bind a full checkout"),
        "expected partial clone message, got: {err_pc_str}"
    );
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
    let invalid_blocked_yaml =
        valid_yaml.replace("fetch: ok\n    note:", "fetch: blocked\n    note:");
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
    assert!(findings_with_docs
        .iter()
        .any(|f| f["message"].as_str().unwrap_or("").contains("0x51")));
    assert!(findings_with_docs
        .iter()
        .any(|f| f["message"].as_str().unwrap_or("").contains("0x99")));
}
