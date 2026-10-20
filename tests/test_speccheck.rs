// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Integration and conformance tests for `driver_lab::speccheck` (`RT-3b` + `RT-4`).
//!
//! Covers:
//! - License gate matrix (`fixtures/license-gate/expected.json`), board overlays, cross-root
//!   references, fail-closed chains, untrusted context roots, and fixed-point trust propagation
//! - Root marker validation, symlink rejection, duplicate root names, and misnamed file discovery
//! - Board fixtures (`good_root`, all 38 `bad_root` files, `bad_load_root`, `vendor_root`,
//!   `stubs`, and `worked-example`)
//! - `textcheck` (`fixtures/textcheck/cases.json`, field selection, notice exemption, retired v1
//!   provenance tag lint, and 33+ backtick fence bounds across keys/values/source_path)
//! - `headingcheck` (`check_headings_with_fetcher`, `fetch_url`, `parse_rendered_headings`)
//! - Bug-fix regressions: `BF-IMX-14`, `BF-IMX-18`, `BF-GW-27`, and `BF-IMX-ISS-4`

use driver_lab::records::{load_schemas, Checker};
use driver_lab::speccheck::{
    check_headings_with_fetcher, classify_context_finding, fetch_url, load_and_run_checker,
    parse_rendered_headings, textcheck_data_where, TaintClass,
};
use serde_json::{json, Value};
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

struct TempDir {
    _inner: tempfile::TempDir,
    path: PathBuf,
}

impl TempDir {
    fn new() -> std::io::Result<Self> {
        let inner = tempfile::TempDir::new()?;
        let path = inner.path().canonicalize()?;
        Ok(Self {
            _inner: inner,
            path,
        })
    }

    fn path(&self) -> &Path {
        &self.path
    }
}

const HDR: &str =
    "# SPDX-FileCopyrightText: 2026 contributors\n# SPDX-License-Identifier: Apache-2.0\n";
const SHA_A: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn fixtures_dir() -> PathBuf {
    repo_root().join("skills/spec-format/tests/fixtures")
}

fn run_cli(args: &[&str]) -> (i32, String, String) {
    let mut full = vec!["driver-lab"];
    full.extend_from_slice(args);
    let mut stdout = Vec::new();
    let mut stderr = Vec::new();
    let code = driver_lab::run_from_args(full, &mut stdout, &mut stderr);
    (
        code,
        String::from_utf8(stdout).unwrap(),
        String::from_utf8(stderr).unwrap(),
    )
}

fn check_json(args: &[&str]) -> (i32, Value) {
    let mut full = vec!["check", "--json"];
    full.extend_from_slice(args);
    let (code, out, err) = run_cli(&full);
    let val: Value = serde_json::from_str(&out)
        .unwrap_or_else(|e| panic!("failed to parse check JSON: {e}\nout={out}\nerr={err}"));
    (code, val)
}

fn errors(result: &Value, text: Option<&str>) -> Vec<Value> {
    result["findings"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|f| {
            f["level"] == "error"
                && text.is_none_or(|needle| f["message"].as_str().unwrap_or("").contains(needle))
        })
        .cloned()
        .collect()
}

fn warnings(result: &Value, text: Option<&str>) -> Vec<Value> {
    result["findings"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|f| {
            f["level"] == "warning"
                && text.is_none_or(|needle| f["message"].as_str().unwrap_or("").contains(needle))
        })
        .cloned()
        .collect()
}

fn write_file(path: &Path, content: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, format!("{HDR}{content}")).unwrap();
}

// ---------------------------------------------------------------------------
// 1. License gate matrix
// ---------------------------------------------------------------------------

#[test]
fn test_license_gate_matrix() {
    let lg_dir = fixtures_dir().join("license-gate");
    let expected: Value =
        serde_json::from_str(&fs::read_to_string(lg_dir.join("expected.json")).unwrap()).unwrap();
    let obj = expected.as_object().unwrap();
    let without_req = obj
        .get("without_require_license")
        .and_then(Value::as_object);

    for (spec_name, row_val) in obj {
        if spec_name == "comment" || spec_name == "without_require_license" {
            continue;
        }
        let row = row_val.as_object().unwrap();
        let spec_src = lg_dir.join("specs").join(spec_name);

        for (root_kind, want_code_val) in row {
            let want_req_code = want_code_val.as_i64().unwrap() as i32;
            let want_no_req_code = without_req
                .and_then(|m| m.get(spec_name))
                .and_then(|r| r.get(root_kind))
                .and_then(Value::as_i64)
                .map(|c| c as i32)
                .unwrap_or(want_req_code);

            let tmp = TempDir::new().unwrap();
            let root = tmp.path().join("root");
            fs::create_dir_all(&root).unwrap();
            fs::copy(
                lg_dir
                    .join("roots")
                    .join(root_kind)
                    .join("board-specs.yaml"),
                root.join("board-specs.yaml"),
            )
            .unwrap();
            fs::copy(&spec_src, root.join(spec_name)).unwrap();

            let (rc_req, res_req) = check_json(&[root.to_str().unwrap(), "--require-license"]);
            assert_eq!(
                rc_req, want_req_code,
                "license-gate {spec_name} x {root_kind} (--require-license): got {rc_req}, want {want_req_code}: {res_req}"
            );

            let (rc_def, res_def) = check_json(&[root.to_str().unwrap()]);
            assert_eq!(
                rc_def, want_no_req_code,
                "license-gate {spec_name} x {root_kind} (default): got {rc_def}, want {want_no_req_code}: {res_def}"
            );
        }
    }
}

// ---------------------------------------------------------------------------
// 2. Board overlays & cross-root references
// ---------------------------------------------------------------------------

#[test]
fn test_board_overlay_fixtures() {
    let lg_dir = fixtures_dir().join("license-gate");
    let board_dir = lg_dir.join("board");

    // Base root (`public` layer, permissive license) holding `widgetchip.spec.yaml`
    let tmp = TempDir::new().unwrap();
    let base_root = tmp.path().join("base");
    fs::create_dir_all(&base_root).unwrap();
    fs::copy(
        lg_dir.join("roots/permissive/board-specs.yaml"),
        base_root.join("board-specs.yaml"),
    )
    .unwrap();
    fs::copy(
        board_dir.join("widgetchip.spec.yaml"),
        base_root.join("widgetchip.spec.yaml"),
    )
    .unwrap();

    // Product overlay root (accepts BSD-3-Clause, MIT) with BSD overlay -> passes
    let overlay_root = tmp.path().join("overlay");
    write_file(
        &overlay_root.join("board-specs.yaml"),
        "format: 2\nlayer: product\nname: overlay-root\nlicense: Apache-2.0\naccepts: [BSD-3-Clause, MIT]\n",
    );
    fs::copy(
        board_dir.join("widgetchip-bsd-overlay.spec.yaml"),
        overlay_root.join("widgetchip-bsd-overlay.spec.yaml"),
    )
    .unwrap();

    let (rc, res) = check_json(&[
        overlay_root.to_str().unwrap(),
        "--context-root",
        base_root.to_str().unwrap(),
    ]);
    assert_eq!(rc, 0, "valid BSD board overlay failed: {res}");
    assert!(errors(&res, None).is_empty());

    // GPL-3.0-only overlay under permissive root -> fails license gate
    fs::remove_file(overlay_root.join("widgetchip-bsd-overlay.spec.yaml")).unwrap();
    fs::copy(
        board_dir.join("widgetchip-gpl3-overlay.spec.yaml"),
        overlay_root.join("widgetchip-gpl3-overlay.spec.yaml"),
    )
    .unwrap();
    let (rc, res) = check_json(&[
        overlay_root.to_str().unwrap(),
        "--context-root",
        base_root.to_str().unwrap(),
        "--require-license",
    ]);
    assert_ne!(
        rc, 0,
        "expected GPL-3.0 overlay under permissive root to fail: {res}"
    );
    assert!(!errors(&res, None).is_empty());
}

#[test]
fn test_cross_root_reference_fixtures() {
    let ref_dir = fixtures_dir().join("references");

    // 1. gpl-cites-docs: gpl root citing docs context root -> passes
    let gcd = ref_dir.join("gpl-cites-docs");
    let (rc, res) = check_json(&[
        gcd.join("gpl").to_str().unwrap(),
        "--context-root",
        gcd.join("docs").to_str().unwrap(),
    ]);
    assert_eq!(rc, 0, "gpl-cites-docs failed: {res}");
    assert!(errors(&res, None).is_empty());

    // 2. docs-cites-gpl: docs root (accepts: []) citing gpl context root -> fails license gate
    let dcg = ref_dir.join("docs-cites-gpl");
    let (rc, res) = check_json(&[
        dcg.join("docs").to_str().unwrap(),
        "--context-root",
        dcg.join("gpl").to_str().unwrap(),
    ]);
    assert_ne!(rc, 0, "docs-cites-gpl must fail: {res}");

    // 3. later-layer: public root citing product context root -> fails layer ordering
    let ll = ref_dir.join("later-layer");
    let (rc, res) = check_json(&[
        ll.join("docs").to_str().unwrap(),
        "--context-root",
        ll.join("vendor").to_str().unwrap(),
    ]);
    assert_ne!(rc, 0, "later-layer must fail: {res}");

    // 4. renamed-root, unqualified -> gpl cites docs with invalid/ambiguous reference
    for case in ["renamed-root", "unqualified"] {
        let dir = ref_dir.join(case);
        let (rc, res) = check_json(&[
            dir.join("gpl").to_str().unwrap(),
            "--context-root",
            dir.join("docs").to_str().unwrap(),
        ]);
        assert_ne!(rc, 0, "expected references/{case} to fail: {res}");
    }

    // 5. same-id -> fact IDs are unique per spec id per root -> passes
    let same_id = ref_dir.join("same-id");
    let (rc, res) = check_json(&[
        same_id.join("gpl").to_str().unwrap(),
        "--context-root",
        same_id.join("docs").to_str().unwrap(),
    ]);
    assert_eq!(rc, 0, "expected references/same-id to pass: {res}");
    assert!(errors(&res, None).is_empty());
}

#[test]
fn test_fail_closed_and_untrusted_roots() {
    let ref_dir = fixtures_dir().join("references");

    // Fail-closed chain: docs (accepts: []) -> perm -> gpl
    let fc_dir = ref_dir.join("fail-closed");
    let (rc, res) = check_json(&[
        fc_dir.join("docs").to_str().unwrap(),
        "--context-root",
        fc_dir.join("perm").to_str().unwrap(),
        "--context-root",
        fc_dir.join("gpl").to_str().unwrap(),
    ]);
    assert_ne!(rc, 0, "fail-closed chain must fail: {res}");
    assert!(
        !errors(&res, None).is_empty(),
        "expected error in fail-closed chain"
    );

    // Untrusted context root (`gpl-bad-marker`) referenced by `perm`
    let (rc, res) = check_json(&[
        fc_dir.join("perm").to_str().unwrap(),
        "--context-root",
        fc_dir.join("gpl-bad-marker").to_str().unwrap(),
    ]);
    assert_ne!(rc, 0, "untrusted context root must fail downstream: {res}");
    assert!(
        !errors(&res, None).is_empty(),
        "expected error when referencing untrusted context root"
    );
}

// ---------------------------------------------------------------------------
// 3. Board check fixtures (`good_root`, `bad_root`, `bad_load_root`, `vendor_root`, `stubs`, `worked-example`)
// ---------------------------------------------------------------------------

#[test]
fn test_check_good_vendor_and_worked_example_roots() {
    let chk_dir = fixtures_dir().join("check");

    let (rc, res) = check_json(&[
        chk_dir.join("good_root").to_str().unwrap(),
        "--public-skill",
        "widget-board-tools",
    ]);
    assert_eq!(rc, 0, "good_root failed: {res}");
    assert!(errors(&res, None).is_empty());

    // vendor_root has `dangling.spec.yaml` (overlays: nosuchboard -> error) and two overlays of widgetboard (-> warning)
    let (rc, res) = check_json(&[
        chk_dir.join("vendor_root").to_str().unwrap(),
        "--context-root",
        chk_dir.join("good_root").to_str().unwrap(),
    ]);
    assert_ne!(rc, 0, "vendor_root with dangling overlay must fail: {res}");
    assert!(!errors(&res, Some("nosuchboard")).is_empty());
    assert!(!warnings(&res, Some("2 overlays of 'widgetboard'")).is_empty());

    let we_dir = fixtures_dir().join("worked-example");
    let (rc, res) = check_json(&[
        we_dir.join("docs").to_str().unwrap(),
        we_dir.join("gpl").to_str().unwrap(),
    ]);
    assert_eq!(rc, 0, "worked-example failed: {res}");
    assert!(errors(&res, None).is_empty());

    let (rc, res) = check_json(&[chk_dir.join("bad_load_root").to_str().unwrap()]);
    assert_ne!(rc, 0, "bad_load_root must fail: {res}");
    assert!(!errors(&res, None).is_empty());
}

#[test]
fn test_check_bad_root_all_files_report_errors() {
    let bad_root = fixtures_dir().join("check/bad_root");
    let (rc, res) = check_json(&[bad_root.to_str().unwrap()]);
    assert_ne!(rc, 0, "bad_root must fail");

    let findings = res["findings"].as_array().unwrap();
    let mut files_with_errors = HashSet::new();
    for f in findings {
        if f["level"] == "error" {
            if let Some(file) = f
                .get("path")
                .or_else(|| f.get("file"))
                .and_then(Value::as_str)
            {
                let p = Path::new(file);
                if let Some(name) = p.file_name().and_then(|s| s.to_str()) {
                    files_with_errors.insert(name.to_string());
                }
            }
        }
    }

    for entry in fs::read_dir(&bad_root).unwrap() {
        let entry = entry.unwrap();
        let name = entry.file_name().into_string().unwrap();
        if name.starts_with("bad_") && name.ends_with(".yaml") {
            assert!(
                files_with_errors.contains(&name),
                "expected bad_root/{name} to produce at least one error finding; got files: {files_with_errors:?}"
            );
        }
    }
}

#[test]
fn test_check_stubs_overlap_fixture() {
    let chk_dir = fixtures_dir().join("check");
    let good_root = chk_dir.join("good_root");
    let stubs = chk_dir.join("stubs");

    let (rc, res) = check_json(&[
        good_root.to_str().unwrap(),
        "--public-skill",
        "widget-board-tools",
        "--stubs-from",
        stubs.to_str().unwrap(),
    ]);
    assert_ne!(rc, 0, "expected errors from fixtures/check/stubs: {res}");
    assert!(
        !warnings(&res, Some("both enter through spec")).is_empty(),
        "expected stub overlap warning: {:?}",
        warnings(&res, None)
    );
}

// ---------------------------------------------------------------------------
// 4. Root validation, symlinks, duplicate root names, misnamed file discovery
// ---------------------------------------------------------------------------

#[test]
fn test_root_validation_symlinks_and_discovery() {
    let tmp = TempDir::new().unwrap();
    let root = tmp.path().join("root");
    fs::create_dir_all(&root).unwrap();

    // Missing board-specs.yaml
    let (rc, res) = check_json(&[root.to_str().unwrap()]);
    assert_ne!(rc, 0);
    assert!(!errors(&res, Some("board-specs.yaml")).is_empty());

    // Valid marker + misnamed spec file (`misnamed.spec.yml`)
    write_file(
        &root.join("board-specs.yaml"),
        "format: 2\nname: test-root\nlayer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0]\n",
    );
    write_file(&root.join("misnamed.spec.yml"), "foo: bar\n");
    let (rc, res) = check_json(&[root.to_str().unwrap()]);
    assert_ne!(rc, 0);
    assert!(
        !errors(&res, Some(".spec.yaml")).is_empty(),
        "expected error for misnamed.spec.yml: {res}"
    );
    fs::remove_file(root.join("misnamed.spec.yml")).unwrap();

    // Symlink inside root should be flagged
    let target = tmp.path().join("outside.spec.yaml");
    write_file(&target, "format: 2\nkind: ip\nid: out\nname: Out\n");
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(&target, root.join("link.spec.yaml")).unwrap();
        let (rc, res) = check_json(&[root.to_str().unwrap()]);
        assert_ne!(rc, 0);
        assert!(
            !errors(&res, Some("symbolic link")).is_empty()
                || !errors(&res, Some("symlink")).is_empty(),
            "expected symlink error: {:?}",
            errors(&res, None)
        );
        fs::remove_file(root.join("link.spec.yaml")).unwrap();
    }

    // Duplicate root name between primary and context root
    let ctx = tmp.path().join("ctx");
    write_file(
        &ctx.join("board-specs.yaml"),
        "format: 2\nname: test-root\nlayer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0]\n",
    );
    let (rc, res) = check_json(&[
        root.to_str().unwrap(),
        "--context-root",
        ctx.to_str().unwrap(),
    ]);
    assert_ne!(rc, 0);
    assert!(
        !errors(&res, Some("test-root")).is_empty(),
        "expected duplicate root name error: {:?}",
        errors(&res, None)
    );
}

// ---------------------------------------------------------------------------
// 5. Textcheck (`fixtures/textcheck/cases.json` + mutate_spec_format_4 backtick fence bounds)
// ---------------------------------------------------------------------------

#[test]
fn test_textcheck_cases_fixture_and_backtick_bounds() {
    let cases_path = fixtures_dir().join("textcheck/cases.json");
    let cases_arr: Value = serde_json::from_str(&fs::read_to_string(cases_path).unwrap()).unwrap();

    for case in cases_arr.as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        let text = case["text"].as_str().unwrap();
        let want_findings = case["findings"].as_array().unwrap();

        let raw_got = driver_lab::specmd::findings(text, false);
        let mut got: Vec<(usize, &str)> = Vec::new();
        for f in &raw_got {
            let pair = (f.line, f.kind.as_str());
            if !got.contains(&pair) {
                got.push(pair);
            }
        }
        assert_eq!(
            got.len(),
            want_findings.len(),
            "textcheck case {name} finding count mismatch for text {text:?}: got={got:?}, want={want_findings:?}"
        );
        for ((line, kind), want) in got.iter().zip(want_findings.iter()) {
            let want_arr = want.as_array().unwrap();
            let want_line = want_arr[0].as_u64().unwrap() as usize;
            let want_kind = want_arr[1].as_str().unwrap();
            assert_eq!(*line, want_line, "textcheck case {name} line mismatch");
            assert_eq!(*kind, want_kind, "textcheck case {name} kind mismatch");
        }
    }

    // 33+ backtick fence limit across keys and string values (mutate_spec_format_4 guard)
    let run_textcheck = |path: &Path, doc: &Value| -> Vec<driver_lab::records::SpecFinding> {
        let mut checker = Checker::new(false, HashSet::new(), None);
        textcheck_data_where(&mut checker, path, None, None, doc, None, true);
        checker.findings
    };

    let ticks_32 = "`".repeat(32);
    let ticks_33 = "`".repeat(33);

    let ok_doc = json!({ "claim": format!("safe {ticks_32} span") });
    assert!(
        run_textcheck(Path::new("ok.spec.yaml"), &ok_doc).is_empty(),
        "32 backticks should pass"
    );

    let bad_val_doc = json!({ "claim": format!("unsafe {ticks_33} span") });
    let val_findings = run_textcheck(Path::new("ok.spec.yaml"), &bad_val_doc);
    assert!(
        val_findings.iter().any(|f| f.message.contains("backtick")),
        "33 backticks in string value must fail: {val_findings:?}"
    );

    let mut bad_key_map = serde_json::Map::new();
    bad_key_map.insert(format!("key_{ticks_33}"), Value::String("normal".into()));
    let key_findings = run_textcheck(Path::new("ok.spec.yaml"), &Value::Object(bad_key_map));
    assert!(
        key_findings.iter().any(|f| f.message.contains("backtick")),
        "33 backticks in mapping key must fail: {key_findings:?}"
    );
}

// ---------------------------------------------------------------------------
// 6. Headingcheck (`fetch_url`, `parse_rendered_headings`, `check_headings_with_fetcher`)
// ---------------------------------------------------------------------------

#[test]
fn test_headingcheck_urls_parsing_and_verification() {
    // 1. fetch_url classification
    let pinned_blob = format!(
        "https://github.com/torvalds/linux/blob/{SHA_A}/Documentation/devicetree/bindings/foo.md"
    );
    let expected_api = format!(
        "https://api.github.com/repos/torvalds/linux/contents/Documentation/devicetree/bindings/foo.md?ref={SHA_A}"
    );
    assert_eq!(
        fetch_url(&pinned_blob),
        Some((expected_api, "application/vnd.github.html"))
    );
    let unpinned_blob = "https://github.com/torvalds/linux/blob/main/README.md";
    assert_eq!(fetch_url(unpinned_blob), None);

    let wiki_url = "https://github.com/owner/repo/wiki/Board-Guide";
    assert_eq!(
        fetch_url(wiki_url),
        Some((wiki_url.to_string(), "text/html"))
    );

    // 2. parse_rendered_headings
    let html = r##"
        <html><body>
        <h1 id="overview">Overview</h1>
        <div class="markdown-heading"><h2 class="heading-element">Clock Tree &amp; PLLs</h2><a id="user-content-clock-tree" class="anchor" href="#clock-tree"></a></div>
        </body></html>
    "##;
    let headings = parse_rendered_headings(html);
    assert_eq!(
        headings.get("overview").map(String::as_str),
        Some("overview")
    );
    assert_eq!(
        headings.get("clock tree & plls").map(String::as_str),
        Some("clock-tree")
    );

    // 3. check_headings_with_fetcher against a synthetic Format 2 root
    let tmp = TempDir::new().unwrap();
    let root = tmp.path().join("root");
    write_file(
        &root.join("board-specs.yaml"),
        "format: 2\nname: hroot\nlayer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0]\n",
    );
    write_file(
        &root.join("chip.spec.yaml"),
        r#"format: 2
kind: chip
id: test-chip
name: Test Chip
triggers: [test-chip]
resources:
  documents:
    - name: wiki
      class: doc
      title: Chip Wiki
      url: "https://github.com/owner/repo/wiki/Board-Guide"
facts:
  - id: f1
    section: quick-facts
    title: Main Chip
    claim: The SoC is mounted on the main board.
    support:
      - class: doc
        doc: wiki
        at:
          - heading: Missing Section
"#,
    );

    let mut checker = Checker::new(false, HashSet::new(), None);
    load_and_run_checker(
        &mut checker,
        std::slice::from_ref(&root),
        &[],
        &[],
        &[],
        false,
        false,
        load_schemas(),
    )
    .expect("load_and_run_checker should succeed");
    assert!(
        checker.findings.iter().all(|f| f.level != "error"),
        "unexpected pre-heading errors: {:?}",
        checker.findings
    );

    check_headings_with_fetcher(&mut checker, false, |_url, _accept| {
        Ok("<h1 id=\"present\">Present Section</h1>".to_string())
    })
    .expect("check_headings_with_fetcher should succeed");
    assert!(
        checker
            .findings
            .iter()
            .any(|f| f.message.contains("Missing Section")),
        "expected missing heading finding, got: {:?}",
        checker.findings
    );
}

// ---------------------------------------------------------------------------
// 7. Bug-fix regressions: BF-IMX-14, BF-IMX-18, BF-GW-27, BF-IMX-ISS-4
// ---------------------------------------------------------------------------

#[test]
fn test_bf_imx_14_datasheet_errata_appnote_citability_and_pdf_pages() {
    for class_name in ["datasheet", "errata", "appnote"] {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path().join("root");
        write_file(
            &root.join("board-specs.yaml"),
            "format: 2\nname: r\nlayer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0]\n",
        );

        // 1. PDF with valid `pages` and in-range `page` passes with 0 errors
        write_file(
            &root.join("p.spec.yaml"),
            &format!(
                r#"format: 2
kind: ip
id: test-p
name: Test IP
triggers: [test-p]
resources:
  documents:
    - name: doc1
      class: {class_name}
      title: Test Doc
      url: "https://example.invalid/doc.pdf"
      sha256: "1111111111111111111111111111111111111111111111111111111111111111"
      pages: 50
facts:
  - id: f1
    section: standards
    title: Clock Rate
    claim: Clock rate is 24 MHz.
    support:
      - class: databook
        doc: doc1
        at:
          - page: "25"
"#
            ),
        );
        let (rc, res) = check_json(&[root.to_str().unwrap()]);
        assert_eq!(
            rc, 0,
            "BF-IMX-14: {class_name} PDF with valid pages/page must pass: {res}"
        );
        assert!(errors(&res, None).is_empty());

        // 2. Out-of-range `page: "51"` when `pages: 50` must fail
        write_file(
            &root.join("p.spec.yaml"),
            &format!(
                r#"format: 2
kind: ip
id: test-p
name: Test IP
triggers: [test-p]
resources:
  documents:
    - name: doc1
      class: {class_name}
      title: Test Doc
      url: "https://example.invalid/doc.pdf"
      sha256: "1111111111111111111111111111111111111111111111111111111111111111"
      pages: 50
facts:
  - id: f1
    section: standards
    title: Clock Rate
    claim: Clock rate is 24 MHz.
    support:
      - class: databook
        doc: doc1
        at:
          - page: "51"
"#
            ),
        );
        let (rc, res) = check_json(&[root.to_str().unwrap()]);
        assert_ne!(
            rc, 0,
            "BF-IMX-14: {class_name} PDF with out-of-range page must fail: {res}"
        );
        assert!(
            !errors(&res, Some("50")).is_empty() || !errors(&res, Some("pages")).is_empty(),
            "BF-IMX-14: expected page bounds error for {class_name}: {:?}",
            errors(&res, None)
        );

        // 3. PDF missing `pages` must fail
        write_file(
            &root.join("p.spec.yaml"),
            &format!(
                r#"format: 2
kind: ip
id: test-p
name: Test IP
triggers: [test-p]
resources:
  documents:
    - name: doc1
      class: {class_name}
      title: Test Doc
      url: "https://example.invalid/doc.pdf"
      sha256: "1111111111111111111111111111111111111111111111111111111111111111"
facts:
  - id: f1
    section: standards
    title: Clock Rate
    claim: Clock rate is 24 MHz.
    support:
      - class: databook
        doc: doc1
        at:
          - heading: Overview
"#
            ),
        );
        let (rc, res) = check_json(&[root.to_str().unwrap()]);
        assert_ne!(
            rc, 0,
            "BF-IMX-14: {class_name} PDF without pages must fail: {res}"
        );
        assert!(
            !errors(&res, Some("pages")).is_empty(),
            "BF-IMX-14: expected missing pages error for {class_name}: {:?}",
            errors(&res, None)
        );
    }
}

#[test]
fn test_bf_imx_18_standalone_facts_yaml_with_root_flag() {
    let tmp = TempDir::new().unwrap();
    let root = tmp.path().join("root");
    write_file(
        &root.join("board-specs.yaml"),
        "format: 2\nname: test-root\nlayer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0]\n",
    );
    let facts_path = tmp.path().join("notes.facts.yaml");
    write_file(
        &facts_path,
        r#"format: 2
kind: facts
id: test-notes
name: Test Notes
resources:
  documents:
    - name: trm
      class: databook
      title: Widget TRM
      url: "https://example.invalid/trm.pdf"
      sha256: "1111111111111111111111111111111111111111111111111111111111111111"
      pages: 80
facts:
  - id: clock-rate
    section: facts
    title: Clock Rate
    claim: The reference clock runs at 24 MHz.
    support:
      - class: databook
        doc: trm
        at:
          - page: "10"
"#,
    );

    // Passing BOTH `--root <dir>` and a `.facts.yaml` positional path must trigger standalone
    // `.facts.yaml` mode cleanly (`BF-IMX-18`).
    let (rc, res) = check_json(&[
        "--root",
        root.to_str().unwrap(),
        facts_path.to_str().unwrap(),
    ]);
    assert_eq!(
        rc, 0,
        "BF-IMX-18: standalone .facts.yaml with --root must succeed: {res}"
    );
    assert!(errors(&res, None).is_empty());
}

#[test]
fn test_bf_gw_27_explicit_context_root_taint_classification() {
    // Integrity errors taint the context root
    assert_eq!(
        classify_context_finding("root marker failed schema validation"),
        TaintClass::TaintingError
    );
    assert_eq!(
        classify_context_finding("repository 'linux' license 'GPL-2.0-only' is not accepted"),
        TaintClass::TaintingError
    );
    assert_eq!(
        classify_context_finding("duplicate metadata.id 'widget' across files"),
        TaintClass::TaintingError
    );

    // Non-tainting upstream unresolved third-root references and spec_file path mismatches
    // are downgraded to context warnings (BF-GW-27)
    assert_eq!(
        classify_context_finding(
            "context root: instance 'uart0': ip 'widgetuart' resolves to no spec"
        ),
        TaintClass::DowngradedContextWarning
    );
    assert_eq!(
        classify_context_finding(
            "context root: spec_file 'soc/old.spec.yaml': this record belongs to 'soc/new.spec.yaml'"
        ),
        TaintClass::DowngradedContextWarning
    );
}

#[test]
fn test_bf_imx_iss_4_three_way_domain_stub_split() {
    let chk_dir = fixtures_dir().join("check");
    let good_root = chk_dir.join("good_root");

    let tmp = TempDir::new().unwrap();
    let stubs_dir = tmp.path().join("skills");

    // 3 domain stubs all entering through `widgetsoc` and naming `widgetsoc-expert` in their `split:`
    for (name, title) in [
        ("widget-boot", "Widget Boot Expert"),
        ("widget-clocks", "Widget Clocks Expert"),
        ("widget-usb", "Widget USB Expert"),
    ] {
        let p = stubs_dir.join(name).join("SKILL.md");
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(
            &p,
            format!(
                r#"---
name: {name}
description: Domain expert stub over widgetsoc for {title}
---
<!-- stubgen: widgetboard -->

# {title}

- `spec: widgetsoc`
- `split: widgetsoc-expert owns top-level SoC integration`
"#
            ),
        )
        .unwrap();
    }

    // With all 3 stubs naming the shared `widgetsoc-expert` hub (`BF-IMX-ISS-4`), check --stubs-from
    // emits 0 stub overlap warnings!
    let (rc, res) = check_json(&[
        good_root.to_str().unwrap(),
        "--public-skill",
        "widget-board-tools",
        "--stubs-from",
        stubs_dir.to_str().unwrap(),
    ]);
    assert_eq!(
        rc, 0,
        "BF-IMX-ISS-4: 3 domain stubs naming shared expert hub must pass: {res}"
    );
    assert!(
        warnings(&res, Some("both enter through spec")).is_empty(),
        "BF-IMX-ISS-4: expected 0 overlap warnings when naming shared expert hub: {:?}",
        warnings(&res, None)
    );

    // Now remove the `split:` line from `widget-usb` -> must emit overlap warnings
    fs::write(
        stubs_dir.join("widget-usb").join("SKILL.md"),
        r#"---
name: widget-usb
description: Domain expert stub over widgetsoc for Widget USB Expert
---
<!-- stubgen: widgetboard -->

# Widget USB Expert

- `spec: widgetsoc`
"#,
    )
    .unwrap();
    let (_rc, res) = check_json(&[
        good_root.to_str().unwrap(),
        "--public-skill",
        "widget-board-tools",
        "--stubs-from",
        stubs_dir.to_str().unwrap(),
    ]);
    assert!(
        !warnings(&res, Some("both enter through spec")).is_empty(),
        "BF-IMX-ISS-4: missing split on third stub must emit overlap warning: {:?}",
        warnings(&res, None)
    );
}
