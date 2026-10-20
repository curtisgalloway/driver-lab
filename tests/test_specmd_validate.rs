use driver_lab::prosefacts::{scan_text, ProseFactKind};
use driver_lab::specmd::findings;
use serde::Deserialize;
use std::fs;

#[derive(Deserialize)]
struct Case {
    name: String,
    text: String,
    findings: Vec<(usize, String)>,
}

#[test]
fn test_cases_json() {
    let content =
        fs::read_to_string("skills/spec-format/tests/fixtures/textcheck/cases.json").unwrap();
    let cases: Vec<Case> = serde_json::from_str(&content).unwrap();
    for case in cases {
        let mut actual_findings = findings(&case.text, true);
        actual_findings.dedup_by(|a, b| a.line == b.line && a.kind == b.kind);
        let actual: Vec<(usize, String)> = actual_findings
            .into_iter()
            .map(|f| (f.line, f.kind))
            .collect();
        assert_eq!(actual, case.findings, "Failed case: {}", case.name);
    }
}

#[derive(Deserialize)]
struct ProsefactsCorpus {
    cases: Vec<ProsefactsCase>,
}

#[derive(Deserialize)]
struct ProsefactsCase {
    id: String,
    text: String,
    findings: Vec<ProsefactsFinding>,
}

#[derive(Deserialize)]
struct ProsefactsFinding {
    line: usize,
    kind: String,
}

#[test]
fn test_prosefacts_corpus() {
    let content = fs::read_to_string("tests/conformance/prosefacts.json").unwrap();
    let corpus: ProsefactsCorpus = serde_json::from_str(&content).unwrap();
    for case in corpus.cases {
        let actual_findings = scan_text(&case.text);

        let expected: Vec<(usize, String)> = case
            .findings
            .into_iter()
            .map(|f| (f.line, f.kind))
            .collect();
        let actual: Vec<(usize, String)> = actual_findings
            .into_iter()
            .map(|f| {
                let kind = match f.kind {
                    ProseFactKind::HexLiteral => "hex_literal".to_string(),
                    ProseFactKind::RegisterName => "register_name".to_string(),
                };
                (f.line, kind)
            })
            .collect();
        assert_eq!(actual, expected, "Failed prosefacts case: {}", case.id);
    }
}
