// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Integration and conformance tests for `hwspecs::records` (`RT-3a`).
//!
//! Verifies byte-for-byte identical `fact-v1` canonical JSON serialization, SHA-256 basis hashes,
//! upstream dependency maps, cycle-safe Tarjan SCC digests, `.verify.yaml` validation, and
//! freshness verdicts across `tests/conformance/fact-v1-vectors.json`, `skills/board-expert/specs`,
//! `skills/spec-verifier/examples/widget`, and `skills/spec-format/tests/fixtures/`, plus all
//! behavioral cases ported from `skills/spec-format/tests/test_records.py`.

use hwspecs::records::{
    bookkeeping_fields, canonical, check_roots, compute_graph, sha256_str, status_roots, STATUSES,
    SUMMARY,
};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, HashMap, HashSet};
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
const COMMIT: &str = "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d";
const TRM: &str = "    - {name: trm, class: databook, title: Widget TRM, url: \"https://example.invalid/trm.pdf\", pages: 80, verified: 2026-10-01, fetch: ok}\n";

fn linux_repo() -> String {
    format!(
        "    - name: linux\n      url: https://example.invalid/linux\n      commit: \"{COMMIT}\"\n      license: GPL-2.0-only\n      role: source\n      files:\n        - {{path: drivers/w.c, license_from: spdx-line}}\n        - {{path: drivers/x.c, license_from: spdx-line}}\n      verified: 2026-10-01\n      fetch: ok\n"
    )
}

fn trm_hashed() -> Value {
    json!({
        "name": "trm",
        "class": "databook",
        "title": "Widget TRM",
        "url": "https://example.invalid/trm.pdf",
        "pages": 80
    })
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

fn check_json(args: &[&str]) -> (i32, Value) {
    let mut full = vec!["check", "--json"];
    full.extend_from_slice(args);
    let (code, out, err) = run_cli(&full);
    let val: Value = serde_json::from_str(&out)
        .unwrap_or_else(|e| panic!("failed to parse check JSON: {e}\nout={out}\nerr={err}"));
    (code, val)
}

fn status_json(args: &[&str]) -> (i32, Value) {
    let mut full = vec!["status", "--json"];
    full.extend_from_slice(args);
    let (code, out, err) = run_cli(&full);
    let val: Value = serde_json::from_str(&out)
        .unwrap_or_else(|e| panic!("failed to parse status JSON: {e}\nout={out}\nerr={err}"));
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

fn rows(result: &Value) -> BTreeMap<String, Value> {
    let mut map = BTreeMap::new();
    if let Some(specs) = result["specs"].as_array() {
        for s in specs {
            if let Some(facts) = s["facts"].as_array() {
                for r in facts {
                    map.insert(r["ref"].as_str().unwrap().to_string(), r.clone());
                }
            }
        }
    }
    map
}

fn bases(args: &[&str]) -> BTreeMap<String, Option<String>> {
    let (_code, result) = status_json(args);
    assert!(
        result.get("error").is_none(),
        "unexpected status error: {result}"
    );
    rows(&result)
        .into_iter()
        .map(|(k, v)| (k, v["basis"].as_str().map(ToString::to_string)))
        .collect()
}

fn marker(name: &str, accepts: &str, lic: &str, layer: &str) -> String {
    format!("{HDR}format: 2\nlayer: {layer}\nname: {name}\nlicense: {lic}\naccepts: {accepts}\n")
}

fn marker_default(name: &str) -> String {
    marker(name, "[]", "CC-BY-4.0", "public")
}

fn fact(
    fid: &str,
    claim: Option<&str>,
    extra: &str,
    support: Option<&str>,
    section: &str,
) -> String {
    let sup =
        support.unwrap_or("    support: [{class: databook, doc: trm, at: [{section: \"1\"}]}]\n");
    let c = claim
        .map(ToString::to_string)
        .unwrap_or_else(|| format!("C {fid}."));
    format!(
        "  - id: {fid}\n    section: {section}\n    title: T {fid}\n    claim: {c}\n{sup}{extra}"
    )
}

fn fact_simple(fid: &str) -> String {
    fact(fid, None, "", None, "quick-facts")
}

fn ref_fact(fid: &str, refs: &[&str], extra: &str) -> String {
    let mut premises = String::new();
    for r in refs {
        premises.push_str(&format!("          - fact: \"{r}\"\n"));
    }
    format!(
        "  - id: {fid}\n    section: quick-facts\n    title: T {fid}\n    claim: C {fid}.\n    support:\n      - class: inference\n        premises:\n{premises}        derivation: it follows\n    todo: {{check: hardware, text: check it.}}\n{extra}"
    )
}

fn chip(sid: &str, facts: &str, repos: &str, head: &str, docs: &str) -> String {
    let mut text = format!(
        "{HDR}format: 2\nkind: chip\nid: {sid}\nname: Widget\ntriggers: [{sid}]\n{head}resources:\n  documents:\n{docs}"
    );
    if !repos.is_empty() {
        text.push_str("  repos:\n");
        text.push_str(repos);
    }
    text.push_str("facts:\n");
    if facts.is_empty() {
        text.push_str("  []\n");
    } else {
        text.push_str(facts);
    }
    text
}

#[allow(dead_code)]
fn overlay(target: &str, facts: &str, repos: &str) -> String {
    let mut text = format!("{HDR}format: 2\nkind: overlay\noverlays: {target}\n");
    if !repos.is_empty() {
        text.push_str("resources:\n  repos:\n");
        text.push_str(repos);
    }
    text.push_str("facts:\n");
    if facts.is_empty() {
        text.push_str("  []\n");
    } else {
        text.push_str(facts);
    }
    text
}

fn make_verdict(basis: &str, value: &str, extra: Option<Map<String, Value>>) -> Value {
    let mut v = Map::new();
    v.insert("basis".to_string(), json!(basis));
    v.insert("verdict".to_string(), json!(value));
    v.insert("date".to_string(), json!("2026-10-08"));
    v.insert("verifier".to_string(), json!("a model"));
    v.insert("contrary_evidence".to_string(), json!("none-found"));
    v.insert("citation_precision".to_string(), json!("exact"));
    if value == "FAIL" {
        v.insert("correction".to_string(), json!("the fix"));
    }
    if value == "ADJUDICATE" {
        v.insert(
            "readings".to_string(),
            json!([
                {"verifier": "a", "verdict": "PASS", "reasoning": "r"},
                {"verifier": "b", "verdict": "FAIL", "reasoning": "s"}
            ]),
        );
    }
    if let Some(ext) = extra {
        for (k, val) in ext {
            if val.is_null() {
                v.remove(&k);
            } else {
                v.insert(k, val);
            }
        }
    }
    Value::Object(v)
}

fn make_record(
    sid: &str,
    spec_file: &str,
    verdicts: &Map<String, Value>,
    summary: Option<Value>,
) -> String {
    let sum = summary.unwrap_or_else(|| {
        let mut counts = Map::new();
        for &(k, _) in SUMMARY {
            counts.insert(k.to_string(), json!(0));
        }
        for v in verdicts.values() {
            if let Some(vstr) = v.get("verdict").and_then(Value::as_str) {
                let lower = vstr.to_ascii_lowercase();
                if let Some(c) = counts.get_mut(&lower) {
                    *c = json!(c.as_i64().unwrap_or(0) + 1);
                }
            }
        }
        Value::Object(counts)
    });
    let data = json!({
        "format": 2,
        "spec": sid,
        "spec_file": spec_file,
        "spec_sha256": "0".repeat(64),
        "canonical": "fact-v1",
        "sources": [],
        "summary": sum,
        "verdicts": verdicts
    });
    format!("{HDR}{}\n", serde_json::to_string_pretty(&data).unwrap())
}

fn write_files(root: &Path, files: &[(&str, &str)]) {
    for (rel, text) in files {
        let p = root.join(rel);
        if let Some(parent) = p.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(p, text).unwrap();
    }
}

fn verify_all(root: &Path, sid: &str, spec_file: &str, status_args: &[&str]) {
    let (_code, result) = status_json(status_args);
    let target_path = root.join(spec_file).to_string_lossy().into_owned();
    let specs = result["specs"].as_array().unwrap();
    let found: Vec<&Value> = specs
        .iter()
        .filter(|s| s["path"].as_str() == Some(target_path.as_str()))
        .collect();
    assert_eq!(found.len(), 1, "spec not found in status: {result}");
    let mut verdicts = Map::new();
    for r in found[0]["facts"].as_array().unwrap() {
        let basis = r["basis"].as_str().unwrap();
        let mut extra = Map::new();
        let up = &r["upstream"];
        if up.as_object().is_some_and(|m| !m.is_empty()) {
            extra.insert("upstream".to_string(), up.clone());
        }
        if r["second_reader"].as_str() != Some("not-needed") {
            extra.insert(
                "readers".to_string(),
                json!([{"verifier": "a second model", "verdict": "PASS"}]),
            );
        }
        let v = make_verdict(basis, "PASS", Some(extra));
        verdicts.insert(r["key"].as_str().unwrap().to_string(), v);
    }
    let stem = Path::new(spec_file)
        .file_name()
        .unwrap()
        .to_str()
        .unwrap()
        .strip_suffix(".spec.yaml")
        .unwrap();
    let rec_text = make_record(sid, spec_file, &verdicts, None);
    write_files(
        root,
        &[(&format!("resources/{stem}.verify.yaml"), &rec_text)],
    );
}

// ---------------------------------------------------------------------------
// 1. Golden Conformance Vectors (`tests/conformance/fact-v1-vectors.json`)
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct FactV1Corpus {
    basis_version: String,
    canonical_json_vectors: Vec<CanonicalJsonVector>,
    suites: Vec<FactV1Suite>,
}

#[derive(Deserialize)]
struct CanonicalJsonVector {
    id: String,
    input: Value,
    canonical_json: String,
    sha256: String,
}

#[derive(Deserialize)]
struct FactV1Suite {
    id: String,
    roots: Vec<String>,
    context_roots: Vec<String>,
    spec_count: usize,
    vector_count: usize,
    vectors: Vec<FactV1Vector>,
}

#[derive(Deserialize)]
struct FactV1Vector {
    root: String,
    spec: String,
    key: String,
    #[serde(rename = "ref")]
    full_ref: String,
    kind: String,
    status: String,
    verdict: Option<String>,
    basis: Option<String>,
    recorded: Option<String>,
    upstream: Option<BTreeMap<String, String>>,
    changed: Vec<String>,
    reason: Option<String>,
    second_reader: String,
}

#[test]
fn test_conformance_fact_v1_vectors_byte_for_byte() {
    let raw = fs::read_to_string("tests/conformance/fact-v1-vectors.json")
        .expect("tests/conformance/fact-v1-vectors.json must exist");
    let corpus: FactV1Corpus = serde_json::from_str(&raw).unwrap();
    assert_eq!(corpus.basis_version, "fact-v1");

    for vec in &corpus.canonical_json_vectors {
        let got_json = canonical(&vec.input).unwrap();
        assert_eq!(
            got_json, vec.canonical_json,
            "canonical JSON mismatch on {}",
            vec.id
        );
        let got_sha = sha256_str(&got_json);
        assert_eq!(got_sha, vec.sha256, "SHA-256 mismatch on {}", vec.id);
    }

    for suite in &corpus.suites {
        let roots: Vec<PathBuf> = suite.roots.iter().map(PathBuf::from).collect();
        let context_roots: Vec<PathBuf> = suite.context_roots.iter().map(PathBuf::from).collect();
        let report = status_roots(&roots, &context_roots, false, &HashSet::new(), false);
        assert_eq!(
            report.specs.len(),
            suite.spec_count,
            "spec_count mismatch in suite {}",
            suite.id
        );
        let actual_rows: Vec<_> = report
            .specs
            .iter()
            .flat_map(|s| {
                s.facts
                    .iter()
                    .map(move |f| (s.root.clone(), s.spec.clone(), f))
            })
            .collect();
        assert_eq!(
            actual_rows.len(),
            suite.vector_count,
            "vector_count mismatch in suite {}",
            suite.id
        );
        for ((root_name, spec_id, actual), expected) in actual_rows.iter().zip(&suite.vectors) {
            assert_eq!(root_name, &expected.root, "suite {}", suite.id);
            assert_eq!(spec_id, &expected.spec, "suite {}", suite.id);
            assert_eq!(actual.key, expected.key, "suite {}", suite.id);
            assert_eq!(actual.r#ref, expected.full_ref, "suite {}", suite.id);
            assert_eq!(actual.kind, expected.kind, "suite {}", suite.id);
            assert_eq!(
                actual.status, expected.status,
                "suite {} ref {}",
                suite.id, actual.r#ref
            );
            assert_eq!(
                actual.verdict, expected.verdict,
                "suite {} ref {}",
                suite.id, actual.r#ref
            );
            assert_eq!(
                actual.basis, expected.basis,
                "suite {} ref {}",
                suite.id, actual.r#ref
            );
            assert_eq!(
                actual.recorded, expected.recorded,
                "suite {} ref {}",
                suite.id, actual.r#ref
            );
            assert_eq!(
                actual.upstream, expected.upstream,
                "suite {} ref {}",
                suite.id, actual.r#ref
            );
            assert_eq!(
                actual.changed, expected.changed,
                "suite {} ref {}",
                suite.id, actual.r#ref
            );
            assert_eq!(
                actual.reason, expected.reason,
                "suite {} ref {}",
                suite.id, actual.r#ref
            );
            assert_eq!(
                actual.second_reader, expected.second_reader,
                "suite {} ref {}",
                suite.id, actual.r#ref
            );
        }
    }
}

// ---------------------------------------------------------------------------
// 2. Canonical Form & Basis Formula (`Canonical`, `BasisFormula`, `Compute`)
// ---------------------------------------------------------------------------

#[test]
fn test_canonical_sorted_keys_nfc_and_types() {
    let val = json!({"b": [1, true, null], "a": "é"});
    let s = canonical(&val).unwrap();
    assert_eq!(s, "{\"a\":\"é\",\"b\":[1,true,null]}");

    // NFC normalization
    let nfd = "cafe\u{0301}";
    let nfc = "caf\u{00e9}";
    assert_ne!(nfd, nfc);
    let mut m_nfd = Map::new();
    m_nfd.insert(nfd.to_string(), Value::String(nfd.to_string()));
    let mut m_nfc = Map::new();
    m_nfc.insert(nfc.to_string(), Value::String(nfc.to_string()));
    assert_eq!(
        canonical(&Value::Object(m_nfd)).unwrap(),
        canonical(&Value::Object(m_nfc)).unwrap()
    );

    // Integers, booleans, strings stay distinct
    assert_ne!(
        canonical(&json!([1])).unwrap(),
        canonical(&json!([true])).unwrap()
    );
    assert_ne!(
        canonical(&json!(["1"])).unwrap(),
        canonical(&json!([1])).unwrap()
    );

    // Floats refused
    assert!(canonical(&json!(1.5)).is_err());
}

#[test]
fn test_basis_formula_cited_fact_and_fact_resting_on_it() {
    let model = |fact_val: &Value,
                 documents: &Value,
                 repos: &Value,
                 assumptions: &Value,
                 lines: &[String]|
     -> String {
        let c = |v: &Value| canonical(v).unwrap();
        let mut sorted = lines.to_vec();
        sorted.sort();
        let text = format!(
            "fact-v1\n{}\n{}\n{}\n{}",
            c(fact_val),
            c(&json!({"documents": documents, "repos": repos})),
            c(assumptions),
            sorted.join("\n")
        );
        sha256_str(&text)
    };

    let tmp = TempDir::new().unwrap();
    let r = tmp.path().join("r");
    let assumption = "  - {id: same-silicon, text: the parts are the same die}\n";
    let facts = format!(
        "{}{}{}",
        fact("a", None, "    assumes: [same-silicon]\n", None, "quick-facts"),
        fact(
            "b",
            None,
            "",
            Some(
                "    support:\n      - class: src\n        anchors: [{repo: linux, path: drivers/w.c, lines: [3, 4], symbol: w_probe}]\n"
            ),
            "quick-facts"
        ),
        ref_fact("c", &["#a", "#b"], "")
    );
    write_files(
        &r,
        &[
            (
                "board-specs.yaml",
                &marker("r", "[GPL-2.0-only]", "GPL-2.0-only", "public"),
            ),
            (
                "w.spec.yaml",
                &chip(
                    "widgetchip",
                    &facts,
                    &linux_repo(),
                    &format!("assumptions:\n{assumption}"),
                    TRM,
                ),
            ),
        ],
    );
    let b = bases(&[r.to_str().unwrap()]);
    let a = model(
        &json!({
            "id": "a",
            "title": "T a",
            "claim": "C a.",
            "assumes": ["same-silicon"],
            "support": [{"class": "databook", "doc": "trm", "at": [{"section": "1"}]}]
        }),
        &json!({"trm": trm_hashed()}),
        &json!({}),
        &json!({"same-silicon": {"id": "same-silicon", "text": "the parts are the same die"}}),
        &[],
    );
    let b_expected = model(
        &json!({
            "id": "b",
            "title": "T b",
            "claim": "C b.",
            "support": [{"class": "src", "anchors": [{"repo": "linux", "path": "drivers/w.c", "lines": [3, 4], "symbol": "w_probe"}]}]
        }),
        &json!({}),
        &json!({
            "linux": {
                "name": "linux",
                "url": "https://example.invalid/linux",
                "commit": COMMIT,
                "license": "GPL-2.0-only",
                "role": "source",
                "files": [{"path": "drivers/w.c", "license_from": "spdx-line"}]
            }
        }),
        &json!({}),
        &[],
    );
    let c = model(
        &json!({
            "id": "c",
            "title": "T c",
            "claim": "C c.",
            "support": [{"class": "inference", "premises": [{"fact": "#a"}, {"fact": "#b"}], "derivation": "it follows"}],
            "todo": {"check": "hardware", "text": "check it."}
        }),
        &json!({}),
        &json!({}),
        &json!({}),
        &[
            format!("widgetchip@r#a {a}"),
            format!("widgetchip@r#b {b_expected}"),
        ],
    );
    assert_eq!(b["widgetchip@r#a"].as_deref(), Some(a.as_str()));
    assert_eq!(b["widgetchip@r#b"].as_deref(), Some(b_expected.as_str()));
    assert_eq!(b["widgetchip@r#c"].as_deref(), Some(c.as_str()));
}

#[test]
fn test_compute_dag_and_cycles_directly() {
    // 1. Resting on an unknown fact is unknown
    let x = "s@r#x".to_string();
    let y = "s@r#y".to_string();
    let z = "s@r#z".to_string();
    let mut out = HashMap::new();
    compute_graph(
        std::slice::from_ref(&x),
        |n| match n.as_str() {
            "s@r#x" => vec![("#y".to_string(), Some(y.clone()), None)],
            "s@r#y" => vec![("#z".to_string(), Some(z.clone()), None)],
            _ => vec![],
        },
        |n| match n.as_str() {
            "s@r#x" => (Some("x".to_string()), None),
            "s@r#y" => (Some("y".to_string()), None),
            _ => (None, Some("z cites an unlisted document".to_string())),
        },
        &HashMap::new(),
        &mut out,
    );
    assert_eq!(
        out[&z],
        (None, Some("z cites an unlisted document".to_string()))
    );
    assert_eq!(
        out[&y],
        (None, Some("z cites an unlisted document".to_string()))
    );
    assert_eq!(
        out[&x],
        (None, Some("z cites an unlisted document".to_string()))
    );

    // 2. Self-cycle of one
    let mut out_self = HashMap::new();
    compute_graph(
        std::slice::from_ref(&x),
        |_| vec![("#x".to_string(), Some(x.clone()), None)],
        |_| (Some("x".to_string()), None),
        &HashMap::new(),
        &mut out_self,
    );
    let digest = sha256_str(&format!("fact-v1-cycle\ns@r#x {}\n", sha256_str("x")));
    let expected_self = sha256_str(&format!("fact-v1\nx\ns@r#x {digest}"));
    assert_eq!(out_self[&x], (Some(expected_self), None));

    // 3. Resting on known facts hashes their bases
    let mut out_known = HashMap::new();
    compute_graph(
        std::slice::from_ref(&x),
        |n| {
            if n == "s@r#x" {
                vec![("#y".to_string(), Some(y.clone()), None)]
            } else {
                vec![]
            }
        },
        |n| {
            if n == "s@r#x" {
                (Some("x".to_string()), None)
            } else {
                (Some("y".to_string()), None)
            }
        },
        &HashMap::new(),
        &mut out_known,
    );
    let y_basis = sha256_str("fact-v1\ny\n");
    let x_basis = sha256_str(&format!("fact-v1\nx\ns@r#y {y_basis}"));
    assert_eq!(out_known[&y], (Some(y_basis), None));
    assert_eq!(out_known[&x], (Some(x_basis), None));
}

// ---------------------------------------------------------------------------
// 3. Invariance & Cycles (`Invariance`, `Cycles`, `CrossRootCycle`)
// ---------------------------------------------------------------------------

#[test]
fn test_invariance_layout_bookkeeping_and_targeted_edits() {
    let tmp = TempDir::new().unwrap();
    let docs = tmp.path().join("docs");
    write_files(
        &docs,
        &[
            ("board-specs.yaml", &marker_default("up")),
            (
                "u.spec.yaml",
                &chip(
                    "upchip",
                    &format!("{}{}", fact_simple("mode"), fact_simple("other")),
                    "",
                    "",
                    TRM,
                ),
            ),
        ],
    );

    let build_spec = |claim_a: &str,
                      section: &str,
                      trm_str: &str,
                      linux_str: &str,
                      assumption: &str,
                      reverse_order: bool|
     -> String {
        let mut items = vec![
            fact("a", Some(claim_a), "", None, section),
            fact(
                "b",
                None,
                "",
                Some("    support:\n      - class: src\n        anchors: [{repo: linux, path: drivers/w.c, lines: [3, 4], symbol: w_probe}]\n"),
                "quick-facts",
            ),
            ref_fact("c", &["#a"], ""),
            fact(
                "d",
                None,
                "    relates: [{fact: \"#c\", relation: qualifies}]\n",
                None,
                "quick-facts",
            ),
            fact("e", None, "    assumes: [same-silicon]\n", None, "quick-facts"),
            ref_fact("f", &["upchip@up#mode"], ""),
            fact(
                "g",
                None,
                "",
                Some("    support:\n      - class: src\n        anchors: [{repo: linux, path: drivers/x.c, lines: [1, 2], symbol: x_init}]\n"),
                "quick-facts",
            ),
            fact_simple("h"),
            "  - id: i\n    section: quick-facts\n    title: T i\n    claim: C i.\n    support:\n      - class: inference\n        premises:\n          - assumption: same-silicon\n        derivation: it follows\n    todo: {check: hardware, text: check it.}\n".to_string(),
        ];
        if reverse_order {
            items.reverse();
        }
        chip(
            "widgetchip",
            &items.join(""),
            linux_str,
            &format!("assumptions:\n  - {{id: same-silicon, text: {assumption}}}\n"),
            trm_str,
        )
    };

    let base_spec = build_spec(
        "C a.",
        "quick-facts",
        TRM,
        &linux_repo(),
        "the parts are the same die",
        false,
    );
    let g0 = tmp.path().join("g0");
    write_files(
        &g0,
        &[
            (
                "board-specs.yaml",
                &marker("g", "[GPL-2.0-only]", "GPL-2.0-only", "public"),
            ),
            ("w.spec.yaml", &base_spec),
        ],
    );
    let base_hashes = bases(&[
        g0.to_str().unwrap(),
        "--context-root",
        docs.to_str().unwrap(),
    ]);

    let mut counter = 1;
    let mut diff_against_base = |spec_text: &str, docs_dir: &Path| -> Vec<String> {
        let g = tmp.path().join(format!("g{counter}"));
        counter += 1;
        write_files(
            &g,
            &[
                (
                    "board-specs.yaml",
                    &marker("g", "[GPL-2.0-only]", "GPL-2.0-only", "public"),
                ),
                ("w.spec.yaml", spec_text),
            ],
        );
        let after = bases(&[
            g.to_str().unwrap(),
            "--context-root",
            docs_dir.to_str().unwrap(),
        ]);
        let mut changed: Vec<String> = base_hashes
            .keys()
            .filter(|k| base_hashes[*k] != after[*k])
            .map(|k| k.split('#').nth(1).unwrap().to_string())
            .collect();
        changed.sort();
        changed
    };

    // Layout changes nothing
    assert!(diff_against_base(
        &build_spec(
            "C a.",
            "quick-facts",
            TRM,
            &linux_repo(),
            "the parts are the same die",
            true
        ),
        &docs
    )
    .is_empty());
    assert!(diff_against_base(
        &build_spec(
            "C a.",
            "gotchas",
            TRM,
            &linux_repo(),
            "the parts are the same die",
            false
        ),
        &docs
    )
    .is_empty());

    // Bookkeeping changes nothing
    let trm_bk = TRM.replace(
        "verified: 2026-10-01, fetch: ok",
        "verified: 2026-10-07, fetch: blocked, note: n",
    );
    assert!(diff_against_base(
        &build_spec(
            "C a.",
            "quick-facts",
            &trm_bk,
            &linux_repo(),
            "the parts are the same die",
            false
        ),
        &docs
    )
    .is_empty());

    // Targeted edits change only dependent facts
    assert_eq!(
        diff_against_base(
            &build_spec(
                "C a, edited.",
                "quick-facts",
                TRM,
                &linux_repo(),
                "the parts are the same die",
                false
            ),
            &docs
        ),
        vec!["a", "c", "d"]
    );
    assert_eq!(
        diff_against_base(
            &build_spec(
                "C a.",
                "quick-facts",
                TRM,
                &linux_repo().replace(COMMIT, &"f".repeat(40)),
                "the parts are the same die",
                false
            ),
            &docs
        ),
        vec!["b", "g"]
    );
    assert_eq!(
        diff_against_base(
            &build_spec(
                "C a.",
                "quick-facts",
                TRM,
                &linux_repo(),
                "the parts share a die",
                false
            ),
            &docs
        ),
        vec!["e", "i"]
    );

    // Cross-root edit changes only fact f
    let docs2 = tmp.path().join("docs2");
    write_files(
        &docs2,
        &[
            ("board-specs.yaml", &marker_default("up")),
            (
                "u.spec.yaml",
                &chip(
                    "upchip",
                    &format!(
                        "{}{}",
                        fact("mode", Some("C mode, edited."), "", None, "quick-facts"),
                        fact_simple("other")
                    ),
                    "",
                    "",
                    TRM,
                ),
            ),
        ],
    );
    assert_eq!(diff_against_base(&base_spec, &docs2), vec!["f"]);
}

#[test]
fn test_cycles_and_cross_root_cycle() {
    let tmp = TempDir::new().unwrap();
    let r = tmp.path().join("r");
    let facts = format!(
        "{}{}",
        fact(
            "a",
            None,
            "    relates: [{fact: \"#b\", relation: same-as}]\n",
            None,
            "quick-facts"
        ),
        fact(
            "b",
            None,
            "    relates: [{fact: \"#a\", relation: same-as}]\n",
            None,
            "quick-facts"
        )
    );
    write_files(
        &r,
        &[
            ("board-specs.yaml", &marker_default("r")),
            ("w.spec.yaml", &chip("widgetchip", &facts, "", "", TRM)),
        ],
    );
    let got = bases(&[r.to_str().unwrap()]);
    let c = |v: &Value| canonical(v).unwrap();
    let res = c(&json!({"documents": {"trm": trm_hashed()}, "repos": {}}));
    let mut local = HashMap::new();
    for (me, other) in [("a", "b"), ("b", "a")] {
        let f_json = c(&json!({
            "id": me,
            "title": format!("T {me}"),
            "claim": format!("C {me}."),
            "support": [{"class": "databook", "doc": "trm", "at": [{"section": "1"}]}],
            "relates": [{"fact": format!("#{other}"), "relation": "same-as"}]
        }));
        local.insert(me, format!("{f_json}\n{res}\n{{}}"));
    }
    let digest = sha256_str(&format!(
        "fact-v1-cycle\nwidgetchip@r#a {}\nwidgetchip@r#b {}\n",
        sha256_str(&local["a"]),
        sha256_str(&local["b"])
    ));
    for (me, other) in [("a", "b"), ("b", "a")] {
        let expected = sha256_str(&format!(
            "fact-v1\n{}\nwidgetchip@r#{other} {digest}",
            local[me]
        ));
        assert_eq!(
            got[&format!("widgetchip@r#{me}")].as_deref(),
            Some(expected.as_str())
        );
    }
}

// ---------------------------------------------------------------------------
// 4. Record Validation & Schema Checks (`RecordChecks`)
// ---------------------------------------------------------------------------

#[test]
fn test_record_checks_validation_and_rules() {
    let tmp = TempDir::new().unwrap();

    // 1. Clean record
    let r1 = tmp.path().join("r1");
    write_files(
        &r1,
        &[
            ("board-specs.yaml", &marker_default("r")),
            (
                "w.spec.yaml",
                &chip(
                    "widgetchip",
                    &format!("{}{}", fact_simple("a"), fact_simple("b")),
                    "",
                    "",
                    TRM,
                ),
            ),
        ],
    );
    let b1 = bases(&[r1.to_str().unwrap()]);
    let mut verdicts = Map::new();
    verdicts.insert(
        "a".to_string(),
        make_verdict(b1["widgetchip@r#a"].as_deref().unwrap(), "PASS", None),
    );
    verdicts.insert(
        "b".to_string(),
        make_verdict(b1["widgetchip@r#b"].as_deref().unwrap(), "PASS", None),
    );
    write_files(
        &r1,
        &[(
            "resources/w.verify.yaml",
            &make_record("widgetchip", "w.spec.yaml", &verdicts, None),
        )],
    );
    let (code, res) = check_json(&[r1.to_str().unwrap()]);
    assert_eq!(code, 0);
    assert_eq!(res["findings"].as_array().unwrap().len(), 0);

    // 2. Verdict missing contrary_evidence or citation_precision surfaces custom schema $comment
    let mut bad_verdicts = verdicts.clone();
    let mut v_no_ce = bad_verdicts["a"].as_object().unwrap().clone();
    v_no_ce.remove("contrary_evidence");
    bad_verdicts.insert("a".to_string(), Value::Object(v_no_ce));
    write_files(
        &r1,
        &[(
            "resources/w.verify.yaml",
            &make_record("widgetchip", "w.spec.yaml", &bad_verdicts, None),
        )],
    );
    let (code, res) = check_json(&[r1.to_str().unwrap()]);
    assert_eq!(code, 1);
    assert!(
        !errors(
            &res,
            Some("a verdict states contrary_evidence and citation_precision")
        )
        .is_empty(),
        "expected custom schema $comment in findings: {res}"
    );

    // 3. Summary mismatch
    write_files(
        &r1,
        &[(
            "resources/w.verify.yaml",
            &make_record(
                "widgetchip",
                "w.spec.yaml",
                &verdicts,
                Some(json!({"pass": 1, "fail": 1, "unverifiable": 0, "gap": 0, "adjudicate": 0})),
            ),
        )],
    );
    let (code, res) = check_json(&[r1.to_str().unwrap()]);
    assert_eq!(code, 1);
    assert!(!errors(&res, Some("summary fail: 1, but 0 verdict(s) are FAIL")).is_empty());
    assert!(!errors(&res, Some("summary pass: 1, but 2 verdict(s) are PASS")).is_empty());

    // 4. Orphan record
    let r_orphan = tmp.path().join("r_orphan");
    write_files(
        &r_orphan,
        &[
            ("board-specs.yaml", &marker_default("r")),
            ("w.spec.yaml", &chip("widgetchip", "", "", "", TRM)),
            (
                "resources/gone.verify.yaml",
                &make_record("gone", "gone.spec.yaml", &Map::new(), None),
            ),
        ],
    );
    let (code, res) = check_json(&[r_orphan.to_str().unwrap()]);
    assert_eq!(code, 1);
    assert!(!errors(&res, Some("no spec file named gone.spec.yaml in root r")).is_empty());
}

// ---------------------------------------------------------------------------
// 5. Fixtures: `VerifyRoot`, `StatusCommand`, `WorkedExample`, `Upstream`
// ---------------------------------------------------------------------------

#[test]
fn test_verify_root_fixture_and_status_command() {
    let vroot = "skills/spec-format/tests/fixtures/records/verify_root";

    for mode in [None, Some("pr"), Some("main")] {
        let mut args = vec![vroot];
        if let Some(m) = mode {
            args.push("--require-verified");
            args.push(m);
        }
        let (code, result) = check_json(&args);
        assert_eq!(code, 1);
        assert_eq!(
            result["verification"],
            json!({
                "current": 2,
                "stale": 2,
                "upstream-stale": 0,
                "unverified": 2,
                "unknown": 0
            })
        );
    }

    // Status text & exit codes
    let (code, out, _) = run_cli(&["status", vroot]);
    assert_eq!(code, 1);
    assert!(out.contains(
        "verify:vok.spec.yaml (vok): resources/vok.verify.yaml: pass 1, fail 0, unverifiable 0, gap 0, adjudicate 0"
    ));
    assert!(out.contains("  current         reset  (PASS)"));
    assert!(out.contains("verify:vnone.spec.yaml (vnone): no record"));
    assert!(out.contains("verify:vbad.spec.yaml (vbad): resources/vbad.verify.yaml: invalid"));
    assert!(out.lines().last().unwrap().contains(
        "2 current, 2 stale, 0 upstream-stale, 2 unverified, 0 unknown; the check found 4 error(s), 4 warning(s)"
    ));

    // Status --stale filters out current facts
    let (_, stale_out, _) = run_cli(&["status", "--stale", vroot]);
    assert!(!stale_out.contains("verify:vok.spec.yaml (vok)"));
    assert!(stale_out.contains("verify:vstale.spec.yaml (vstale)"));

    // Usage exit code 2
    for bad_args in [
        &["status"][..],
        &["status", "--json"][..],
        &["check", vroot, "--require-verified"][..],
        &["check", vroot, "--require-verified", "yes"][..],
        &["check", vroot, "--require-verified=PR"][..],
        &["status", vroot, "--require-verified", "pr"][..],
    ] {
        let (code, _, _) = run_cli(bad_args);
        assert_eq!(code, 2, "expected exit code 2 for {bad_args:?}");
    }
    let (code, json_out, _) = run_cli(&["status", "--json"]);
    assert_eq!(code, 2);
    let parsed: Value = serde_json::from_str(&json_out).unwrap();
    assert_eq!(parsed["ok"], json!(false));
    assert_eq!(parsed["error"], json!("usage"));
}

#[test]
fn test_upstream_freshness_and_second_readers() {
    let tmp = TempDir::new().unwrap();
    let docs = tmp.path().join("docs");
    write_files(
        &docs,
        &[
            ("board-specs.yaml", &marker_default("up")),
            (
                "u.spec.yaml",
                &chip(
                    "upchip",
                    &format!("{}{}", fact_simple("mode"), fact_simple("other")),
                    "",
                    "",
                    TRM,
                ),
            ),
        ],
    );
    let gpl = tmp.path().join("gpl");
    write_files(
        &gpl,
        &[
            ("board-specs.yaml", &marker_default("g")),
            (
                "x.spec.yaml",
                &chip(
                    "xchip",
                    &format!(
                        "{}{}{}",
                        ref_fact("direct", &["upchip@up#mode"], ""),
                        ref_fact("through", &["#direct"], ""),
                        fact_simple("local")
                    ),
                    "",
                    "",
                    TRM,
                ),
            ),
        ],
    );
    verify_all(
        &gpl,
        "xchip",
        "x.spec.yaml",
        &[
            gpl.to_str().unwrap(),
            "--context-root",
            docs.to_str().unwrap(),
        ],
    );

    for mode in ["pr", "main"] {
        let (code, res) = check_json(&[
            gpl.to_str().unwrap(),
            "--context-root",
            docs.to_str().unwrap(),
            "--require-verified",
            mode,
        ]);
        assert_eq!(code, 0, "mode {mode} failed: {res}");
        assert_eq!(res["verification"]["current"], json!(3));
    }

    // Upstream edit makes direct & through upstream-stale (error on pr, warning on main)
    let docs_edited = tmp.path().join("docs_edited");
    write_files(
        &docs_edited,
        &[
            ("board-specs.yaml", &marker_default("up")),
            (
                "u.spec.yaml",
                &chip(
                    "upchip",
                    &format!(
                        "{}{}",
                        fact("mode", Some("C mode, edited."), "", None, "quick-facts"),
                        fact_simple("other")
                    ),
                    "",
                    "",
                    TRM,
                ),
            ),
        ],
    );
    let (code_pr, res_pr) = check_json(&[
        gpl.to_str().unwrap(),
        "--context-root",
        docs_edited.to_str().unwrap(),
        "--require-verified",
        "pr",
    ]);
    assert_eq!(code_pr, 1);
    assert_eq!(res_pr["verification"]["upstream-stale"], json!(2));

    let (code_main, res_main) = check_json(&[
        gpl.to_str().unwrap(),
        "--context-root",
        docs_edited.to_str().unwrap(),
        "--require-verified",
        "main",
    ]);
    assert_eq!(code_main, 0);
    assert_eq!(res_main["verification"]["upstream-stale"], json!(2));
    assert_eq!(warnings(&res_main, Some("upstream-stale")).len(), 2);

    // Bookkeeping fields match records::bookkeeping_fields
    assert!(bookkeeping_fields("documents").contains(&"verified"));
    assert!(bookkeeping_fields("repos").contains(&"fetch_via"));
    assert!(bookkeeping_fields("files").contains(&"attribution"));
    assert!(bookkeeping_fields("assumptions").contains(&"todo"));
    assert_eq!(STATUSES.len(), 5);
}

#[test]
fn test_worked_example_status_and_upstream_edit() {
    let tmp = TempDir::new().unwrap();
    let docs = tmp.path().join("docs");
    let gpl = tmp.path().join("gpl");

    fn copy_dir_all(src: &Path, dst: &Path) {
        fs::create_dir_all(dst).unwrap();
        for entry in fs::read_dir(src).unwrap() {
            let entry = entry.unwrap();
            let ty = entry.file_type().unwrap();
            let target = dst.join(entry.file_name());
            if ty.is_dir() {
                copy_dir_all(&entry.path(), &target);
            } else {
                fs::copy(entry.path(), &target).unwrap();
            }
        }
    }

    // Copy worked-example/docs and worked-example/gpl
    copy_dir_all(
        Path::new("skills/spec-format/tests/fixtures/worked-example/docs"),
        &docs,
    );
    copy_dir_all(
        Path::new("skills/spec-format/tests/fixtures/worked-example/gpl"),
        &gpl,
    );

    verify_all(
        &gpl,
        "bcm2711",
        "bcm2711.spec.yaml",
        &[
            gpl.to_str().unwrap(),
            "--context-root",
            docs.to_str().unwrap(),
        ],
    );
    let (code, res) = check_json(&[
        gpl.to_str().unwrap(),
        "--context-root",
        docs.to_str().unwrap(),
        "--require-verified",
        "pr",
    ]);
    assert_eq!(code, 0, "expected clean check: {res}");

    // Edit addressing-model in docs
    let spec_path = docs.join("bcm2711.spec.yaml");
    let text = fs::read_to_string(&spec_path).unwrap();
    let anchor = text.find("  - id: addressing-model").unwrap();
    let claim_pos = text[anchor..].find("    claim:").unwrap() + anchor;
    let edited = format!(
        "{}    note: an edit\n{}",
        &text[..claim_pos],
        &text[claim_pos..]
    );
    fs::write(&spec_path, edited).unwrap();

    let (code_main, res_main) = check_json(&[
        gpl.to_str().unwrap(),
        "--context-root",
        docs.to_str().unwrap(),
        "--require-verified",
        "main",
    ]);
    assert_eq!(code_main, 0);
    assert_eq!(
        warnings(
            &res_main,
            Some("fact 'tree-describes-low-peripheral-mode': upstream-stale")
        )
        .len(),
        1
    );

    let (code_pr, res_pr) = check_json(&[
        gpl.to_str().unwrap(),
        "--context-root",
        docs.to_str().unwrap(),
        "--require-verified",
        "pr",
    ]);
    assert_eq!(code_pr, 1);
    assert_eq!(
        errors(
            &res_pr,
            Some("fact 'tree-describes-low-peripheral-mode': upstream-stale")
        )
        .len(),
        1
    );

    // Direct library call check_roots matches
    let rep = check_roots(
        std::slice::from_ref(&gpl),
        std::slice::from_ref(&docs),
        false,
        &HashSet::new(),
        Some("pr".to_string()),
    );
    assert_eq!(rep.exit_code, 1);
}
