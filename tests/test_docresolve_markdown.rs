// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Markdown document resolution in `hwspecs resolve` (`section:` and `heading:` locators), the
//! `--fail-on-skipped-documents` flag, and the `fixture_resolve` conformance cases in
//! `tests/conformance/cases.json`.

use hwspecs::docresolve::{
    find_markdown_section, markdown_heading_key, markdown_headings, match_markdown_heading,
    HeadingMatch,
};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::Path;
use std::process::{Command, Output};

fn run_cli(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_hwspecs"))
        .args(args)
        .output()
        .expect("failed to execute hwspecs")
}

fn lines(text: &str) -> Vec<String> {
    text.lines().map(String::from).collect()
}

#[test]
fn headings_atx_setext_and_fences() {
    let doc = lines(
        "# Title {#top}\n\
         text\n\
         \n\
         ## 9. Foo ##\n\
         ```\n\
         # not a heading\n\
         ```\n\
         Setext Two\n\
         ----------\n\
         #hashtag is not a heading\n\
         ~~~~\n\
         ## also not\n\
         ~~~~\n\
         ### 9.1 Bar\n",
    );
    let got: Vec<(usize, usize, String)> = markdown_headings(&doc)
        .into_iter()
        .map(|h| (h.line, h.level, h.text))
        .collect();
    assert_eq!(
        got,
        vec![
            (0, 1, "Title {#top}".to_string()),
            (3, 2, "9. Foo".to_string()),
            (7, 2, "Setext Two".to_string()),
            (13, 3, "9.1 Bar".to_string()),
        ]
    );
}

#[test]
fn headings_skip_front_matter_comments_and_lists() {
    let doc = lines(
        "---\n\
         title: x\n\
         ---\n\
         <!--\n\
         # commented out\n\
         -->\n\
         <!-- # one-line comment -->\n\
         # Real\n\
         \n\
         1. first item\n\
         ---\n\
         ## Closed ###\n\
         ## Hash#tag\n",
    );
    let got: Vec<(usize, usize, String)> = markdown_headings(&doc)
        .into_iter()
        .map(|h| (h.line, h.level, h.text))
        .collect();
    assert_eq!(
        got,
        vec![
            (7, 1, "Real".to_string()),
            (11, 2, "Closed".to_string()),
            (12, 2, "Hash#tag".to_string()),
        ]
    );
}

#[test]
fn heading_key_normalization() {
    assert_eq!(
        markdown_heading_key("Control  Register {#ctrl}"),
        "control register"
    );
    assert_eq!(markdown_heading_key("`CTRL` field:"), "ctrl field");
    assert_eq!(markdown_heading_key("Section 9.2 Foo"), "9.2 foo");
}

#[test]
fn heading_matching_rules() {
    use HeadingMatch::*;
    assert_eq!(match_markdown_heading("Foo", "foo"), Exact);
    assert_eq!(match_markdown_heading("Foo", "9. Foo"), NumericPrefix);
    assert_eq!(match_markdown_heading("9. Foo", "Foo"), NumericPrefix);
    assert_eq!(
        match_markdown_heading("9) Foo", "9. Foo {#foo}"),
        NumericPrefix
    );
    // A bare leading integer followed by words is a title, not a section number.
    assert_eq!(match_markdown_heading("KiB SRAM", "64 KiB SRAM"), None);
    assert_eq!(match_markdown_heading("64", "64 KiB SRAM"), None);
    assert_eq!(match_markdown_heading("64 kib sram", "64 KiB SRAM"), Exact);
    assert_eq!(match_markdown_heading("9.2", "9.2 Bar"), NumericPrefix);
    assert_eq!(match_markdown_heading("9", "9.2 Bar"), None);
    assert_eq!(match_markdown_heading("4. Foo", "9. Foo"), None);
    assert_eq!(match_markdown_heading("Foo", "Foo bar"), None);
    assert_eq!(match_markdown_heading("", "Foo"), None);
}

#[test]
fn section_extent_stops_at_same_or_higher_level() {
    let doc = lines(
        "# A\n\
         a\n\
         ## 1. B\n\
         b\n\
         ### 1.1 C\n\
         c\n\
         ## 2. D\n\
         d\n",
    );
    let headings = markdown_headings(&doc);
    let (h, start, end, n) = find_markdown_section(&headings, doc.len(), "B").unwrap();
    assert_eq!((h.text.as_str(), start, end, n), ("1. B", 2, 6, 1));
    let (_, start, end, _) = find_markdown_section(&headings, doc.len(), "1.1").unwrap();
    assert_eq!((start, end), (4, 6));
    let (_, start, end, _) = find_markdown_section(&headings, doc.len(), "2. D").unwrap();
    assert_eq!((start, end), (6, 8));
    // An exact match wins over an earlier numeric-prefix match.
    let doc2 = lines("## 3. Reset\nx\n## Reset\ny\n");
    let h2 = markdown_headings(&doc2);
    let (h, _, _, n) = find_markdown_section(&h2, doc2.len(), "Reset").unwrap();
    assert_eq!((h.text.as_str(), n), ("Reset", 1));
    // Two equally good matches are counted, so the caller can warn.
    let doc3 = lines("# A\n## Registers\n# B\n## Registers\n");
    let h3 = markdown_headings(&doc3);
    let (_, start, _, n) = find_markdown_section(&h3, doc3.len(), "Registers").unwrap();
    assert_eq!((start, n), (1, 2));
    assert!(find_markdown_section(&headings, doc.len(), "Missing").is_none());
}

/// Writes a one-document spec and its pinned document into `dir`; returns (spec, docs dir).
fn write_spec(dir: &Path, doc_name: &str, doc_text: &str, facts: &str) -> (String, String) {
    let docs = dir.join("docs");
    fs::create_dir_all(&docs).unwrap();
    fs::write(docs.join(doc_name), doc_text).unwrap();
    let sha = hex::encode(Sha256::digest(doc_text.as_bytes()));
    let spec = dir.join("widget.spec.yaml");
    fs::write(
        &spec,
        format!(
            "# SPDX-FileCopyrightText: 2026 contributors\n\
             # SPDX-License-Identifier: Apache-2.0\n\
             format: 2\n\
             kind: chip\n\
             id: widget\n\
             name: Synthetic Widget\n\
             triggers: [synthetic widget]\n\
             resources:\n\
             \x20 documents:\n\
             \x20   - name: {doc_name}\n\
             \x20     class: doc\n\
             \x20     title: Synthetic Widget notes\n\
             \x20     url: https://example.invalid/{doc_name}\n\
             \x20     sha256: {sha}\n\
             \x20     access: public\n\
             facts:\n{facts}"
        ),
    )
    .unwrap();
    (
        spec.to_string_lossy().into_owned(),
        docs.to_string_lossy().into_owned(),
    )
}

fn json_out(out: &Output) -> Value {
    serde_json::from_slice(&out.stdout)
        .unwrap_or_else(|e| panic!("bad JSON ({e}): {}", String::from_utf8_lossy(&out.stdout)))
}

#[test]
fn markdown_register_offset_checked_against_section() {
    let tmp = tempfile::tempdir().unwrap();
    let facts = "  - id: ctrl
    section: registers
    claim: The synthetic Widget control register is described in the guide.
    data:
      register:
        offset: \"0x10\"
    support:
      - class: doc
        doc: guide.md
        at: [{heading: Status}]
";
    let (spec, docs) = write_spec(
        tmp.path(),
        "guide.md",
        "# Control\nAt offset 0x10.\n# Status\nAt offset 0x14.\n",
        facts,
    );
    let out = run_cli(&["--json", "resolve", &spec, "--docs-dir", &docs]);
    let res = json_out(&out);
    assert_eq!(res["documents_resolved"], 1, "{res}");
    let msgs: Vec<&str> = res["findings"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|f| f["message"].as_str())
        .collect();
    assert!(
        msgs.contains(&"register offset absent from cited Markdown sections: 0x10"),
        "{msgs:?}"
    );
    let cit = &res["document_citations"][0];
    assert_eq!(cit["format"], "markdown");
    assert_eq!(cit["headings"][0], "Status");
    assert_eq!(cit["source"][0][0], 3);
    assert_eq!(cit["source"][0][1], "# Status");
}

#[test]
fn plain_text_document_skips_quietly_unless_flagged() {
    let tmp = tempfile::tempdir().unwrap();
    let facts = "  - id: note
    section: quick-facts
    claim: The synthetic Widget has a note.
    support:
      - class: doc
        doc: notes.txt
        at: [{heading: Notes}]
";
    let (spec, docs) = write_spec(tmp.path(), "notes.txt", "plain text, no headings\n", facts);

    let out = run_cli(&["resolve", &spec, "--docs-dir", &docs]);
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(out.status.success(), "{text}");
    assert!(!text.contains("skipped:"), "{text}");
    assert!(text.contains("0 anchor(s) resolved, 0 skipped"), "{text}");
    assert!(
        text.contains("0 document citation(s) resolved, 1 skipped"),
        "{text}"
    );

    let out = run_cli(&[
        "--json",
        "resolve",
        &spec,
        "--docs-dir",
        &docs,
        "--fail-on-skipped-documents",
    ]);
    assert_eq!(out.status.code(), Some(1));
    let res = json_out(&out);
    assert_eq!(res["ok"], false);
    let f = &res["findings"][0];
    assert_eq!(f["level"], "error");
    assert_eq!(
        f["message"],
        "note: notes.txt: document evidence skipped: document is neither a PDF nor Markdown"
    );
}

#[test]
fn markdown_extension_without_headings_is_an_error() {
    let tmp = tempfile::tempdir().unwrap();
    let facts = "  - id: note
    section: quick-facts
    claim: The synthetic Widget has a note.
    support:
      - class: doc
        doc: notes.md
        at: [{section: \"2\"}]
";
    let (spec, docs) = write_spec(tmp.path(), "notes.md", "no headings here\n", facts);
    let out = run_cli(&["--json", "resolve", &spec, "--docs-dir", &docs]);
    assert_eq!(out.status.code(), Some(1));
    let res = json_out(&out);
    assert_eq!(res["documents_failed"], 1);
    assert_eq!(
        res["findings"][0]["message"],
        "note: notes.md: section \"2\" matches no Markdown heading"
    );
}

#[test]
fn summary_line_printed_with_docs_dir_even_without_citations() {
    let tmp = tempfile::tempdir().unwrap();
    let facts = "  - id: plain
    section: quick-facts
    claim: The synthetic Widget exists.
    todo:
      check: document
      text: Find a source.
      method: Read one.
";
    let (spec, docs) = write_spec(tmp.path(), "guide.md", "# Guide\n", facts);
    let out = run_cli(&["resolve", &spec, "--docs-dir", &docs]);
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(
        text.contains("0 document citation(s) resolved, 0 skipped"),
        "{text}"
    );
    let out = run_cli(&["resolve", &spec]);
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(!text.contains("document citation(s)"), "{text}");
}

#[test]
fn fail_on_skipped_documents_requires_docs_dir() {
    let out = run_cli(&[
        "resolve",
        "skills/spec-format/tests/fixtures/docresolve-markdown/good",
        "--fail-on-skipped-documents",
    ]);
    assert_eq!(out.status.code(), Some(2));
}

#[test]
fn conformance_fixture_resolve_cases() {
    let raw = fs::read_to_string("tests/conformance/cases.json").unwrap();
    let cases: Value = serde_json::from_str(&raw).unwrap();
    let mut ran = 0;
    for case in cases["cases"].as_array().unwrap() {
        if case["kind"] != "fixture_resolve" {
            continue;
        }
        ran += 1;
        let id = case["id"].as_str().unwrap();
        let mut args: Vec<String> = vec!["--json".into(), "resolve".into()];
        for t in case["targets"].as_array().unwrap() {
            args.push(t.as_str().unwrap().to_string());
        }
        args.push("--docs-dir".into());
        args.push(case["docs_dir"].as_str().unwrap().to_string());
        if case["options"]["fail_on_skipped_documents"] == true {
            args.push("--fail-on-skipped-documents".into());
        }
        let argv: Vec<&str> = args.iter().map(String::as_str).collect();
        let out = run_cli(&argv);
        let res = json_out(&out);
        assert_eq!(
            out.status.code(),
            case["exit_code"].as_i64().map(|c| c as i32),
            "{id}: exit code; {res}"
        );
        for key in [
            "ok",
            "documents_resolved",
            "documents_skipped",
            "documents_failed",
        ] {
            assert_eq!(res[key], case[key], "{id}: {key}");
        }
        let findings = res["findings"].as_array().unwrap();
        let count = |lvl: &str| findings.iter().filter(|f| f["level"] == lvl).count() as u64;
        assert_eq!(
            Some(count("error")),
            case["error_count"].as_u64(),
            "{id}: errors"
        );
        assert_eq!(
            Some(count("warning")),
            case["warning_count"].as_u64(),
            "{id}: warnings"
        );
        let want = case["findings"].as_array().unwrap();
        assert_eq!(findings.len(), want.len(), "{id}: findings {findings:?}");
        for (got, exp) in findings.iter().zip(want) {
            for key in ["code", "level", "path", "line", "column", "message"] {
                assert_eq!(got[key], exp[key], "{id}: finding {key}");
            }
        }
    }
    assert!(ran >= 3, "expected fixture_resolve cases, ran {ran}");
}

#[test]
fn markdown_register_offset_found_in_section_is_quiet() {
    let tmp = tempfile::tempdir().unwrap();
    let facts = "  - id: ctrl
    section: registers
    claim: The synthetic Widget control register is described in the guide.
    data:
      register:
        offset: \"0x10\"
    support:
      - class: doc
        doc: guide.md
        at: [{heading: Control}]
";
    let (spec, docs) = write_spec(
        tmp.path(),
        "guide.md",
        "# Control\nAt offset 0x10.\n# Status\nAt offset 0x14.\n",
        facts,
    );
    let res = json_out(&run_cli(&["--json", "resolve", &spec, "--docs-dir", &docs]));
    assert_eq!(res["documents_resolved"], 1, "{res}");
    assert_eq!(res["findings"].as_array().unwrap().len(), 0, "{res}");
}

#[test]
fn ambiguous_heading_warns() {
    let tmp = tempfile::tempdir().unwrap();
    let facts = "  - id: regs
    section: registers
    claim: The synthetic Widget block registers are listed.
    support:
      - class: doc
        doc: guide.md
        at: [{heading: Registers}]
";
    let (spec, docs) = write_spec(
        tmp.path(),
        "guide.md",
        "# Block A\n## Registers\na\n# Block B\n## Registers\nb\n",
        facts,
    );
    let res = json_out(&run_cli(&["--json", "resolve", &spec, "--docs-dir", &docs]));
    assert_eq!(res["ok"], true, "{res}");
    assert_eq!(res["documents_resolved"], 1);
    let f = &res["findings"][0];
    assert_eq!(f["level"], "warning");
    assert_eq!(
        f["message"],
        "regs: guide.md: heading \"Registers\" is ambiguous: it matches 2 Markdown headings; using the first, at line 2"
    );
}

#[test]
fn sniffed_document_unmatched_locator_is_a_skip_warning() {
    let tmp = tempfile::tempdir().unwrap();
    let facts = "  - id: cfg
    section: quick-facts
    claim: The synthetic Widget has configuration notes.
    support:
      - class: doc
        doc: notes.txt
        at: [{section: \"4.2\"}]
";
    let (spec, docs) = write_spec(
        tmp.path(),
        "notes.txt",
        "# Configuration notes\nkey = value\n",
        facts,
    );
    let res = json_out(&run_cli(&["--json", "resolve", &spec, "--docs-dir", &docs]));
    assert_eq!(res["ok"], true, "{res}");
    assert_eq!(res["documents_skipped"], 1);
    let f = &res["findings"][0];
    assert_eq!(f["level"], "warning");
    assert_eq!(
        f["message"],
        "cfg: notes.txt: document evidence skipped: section \"4.2\" matches no Markdown heading"
    );
    let out = run_cli(&[
        "--json",
        "resolve",
        &spec,
        "--docs-dir",
        &docs,
        "--fail-on-skipped-documents",
    ]);
    assert_eq!(out.status.code(), Some(1));
    assert_eq!(json_out(&out)["findings"][0]["level"], "error");
}
