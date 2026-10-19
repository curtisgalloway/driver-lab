// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Corpus ledger checker and coverage reporter (`skills/spec-format/scripts/corpus.py`,
//! `RUST-TOOLING-DESIGN.md` §4.3 `BF-IMX-12`, §4.5 `BF-GW-24`, `RT-4`).
//!
//! Validates `<root>/corpus.yaml` dispositions (`spec:<id>[#<fact>]`, `planned:<note>`,
//! `excluded:<reason>`), cross-checks `resources.documents` entries across all spec files in the
//! root against the ledger, enforces template placeholder rules (`BF-IMX-12`, `BF-GW-24`), and
//! implements `driver-lab corpus`.

use crate::diagnostic::{visible_name, EXIT_DOMAIN_FAILURE, EXIT_OK, EXIT_USAGE_ERROR};
use crate::records::{Checker, PathElem, CORPUS};
use crate::specmd;
use crate::yaml_strict::Loaded;
use crate::{Cli, CorpusArgs};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::io::Write;
use std::path::Path;
use std::sync::LazyLock;

/// Ledger groups (`documents`, `blocks`).
pub const GROUPS: &[&str] = &["documents", "blocks"];

/// Disposition states (`spec`, `planned`, `excluded`, `unresolved`).
pub const STATES: &[&str] = &["spec", "planned", "excluded", "unresolved"];

static SPEC_DISPOSITION_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^spec:([a-z0-9][a-z0-9-]*)(?:#([a-z0-9][a-z0-9-]*))?$")
        .expect("valid SPEC_DISPOSITION_RE")
});

/// Returns the disposition prefix before the first `:` (`"spec"`, `"planned"`, or `"excluded"`).
#[must_use]
pub fn state(disposition: &str) -> &str {
    disposition
        .split_once(':')
        .map_or(disposition, |(prefix, _)| prefix)
}

/// Checks `corpus.yaml` ledgers across all loaded roots in `checker` (`corpus.py:check`).
pub fn check(checker: &mut Checker) {
    let num_roots = checker.roots.len();
    for root_idx in 0..num_roots {
        if checker.roots[root_idx].corpus.is_some() {
            check_root(checker, root_idx);
        }
    }
}

fn check_root(checker: &mut Checker, root_idx: usize) {
    let Some(corpus_path) = checker.roots[root_idx].corpus_path.clone() else {
        return;
    };
    let Some(loaded) = checker.roots[root_idx].corpus.clone() else {
        return;
    };
    let Some(data) = loaded.data.clone() else {
        return;
    };
    let is_public = checker.roots[root_idx].layer.as_deref() == Some("public");

    let mut ledger: HashMap<String, HashMap<String, Value>> = HashMap::new();
    let mut findings: Vec<(Vec<PathElem>, String)> = Vec::new();

    for &group in GROUPS {
        let seen = ledger.entry(group.to_string()).or_default();
        if let Some(entries) = data.get(group).and_then(Value::as_array) {
            for (i, entry) in entries.iter().enumerate() {
                let Some(name) = entry.get("name").and_then(Value::as_str) else {
                    continue;
                };
                if seen.contains_key(name) {
                    findings.push((
                        vec![
                            PathElem::from(group),
                            PathElem::Index(i),
                            PathElem::from("name"),
                        ],
                        format!("{group} entry '{name}' is listed twice in the corpus ledger"),
                    ));
                    continue;
                }
                seen.insert(name.to_string(), entry.clone());

                let disp = entry
                    .get("disposition")
                    .and_then(Value::as_str)
                    .unwrap_or("");
                if let Some(why) = disposition_problem(checker, root_idx, group, entry) {
                    findings.push((
                        vec![
                            PathElem::from(group),
                            PathElem::Index(i),
                            PathElem::from("disposition"),
                        ],
                        format!("disposition '{disp}': {why}"),
                    ));
                }
                if is_public && entry.get("access").and_then(Value::as_str) == Some("private") {
                    findings.push((
                        vec![
                            PathElem::from(group),
                            PathElem::Index(i),
                            PathElem::from("access"),
                        ],
                        format!("{group} entry '{name}': access: private under a public root"),
                    ));
                }
            }
        }
    }

    check_placeholders(&data, &mut Vec::new(), &mut findings);

    for (path, msg) in findings {
        checker.add_where(
            &corpus_path,
            Some(root_idx),
            Some(&loaded),
            &path,
            msg,
            "error",
            false,
            true,
            false,
        );
    }

    let corpus_file_name = corpus_path
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_else(|| CORPUS.to_string());
    let file_indices = checker.roots[root_idx].files.clone();
    let doc_ledger = ledger.get("documents").cloned().unwrap_or_default();

    let mut file_findings: Vec<(usize, Vec<PathElem>, String, bool)> = Vec::new();
    for f_idx in file_indices {
        let mut doc_entries: Vec<(String, Value, Vec<PathElem>)> = checker.files[f_idx]
            .documents
            .iter()
            .map(|(k, (v, p))| (k.clone(), v.clone(), p.clone()))
            .collect();
        doc_entries.sort_by(|a, b| a.0.cmp(&b.0));

        for (name, entry, path) in doc_entries {
            let Some(listed) = doc_ledger.get(&name) else {
                let mut p = path;
                p.push(PathElem::from("name"));
                file_findings.push((
                    f_idx,
                    p,
                    format!(
                        "documents entry '{name}' is not in the root's corpus ledger ({corpus_file_name}): add it with a disposition"
                    ),
                    false,
                ));
                continue;
            };
            if let (Some(e_acc), Some(l_acc)) = (
                entry.get("access").and_then(Value::as_str),
                listed.get("access").and_then(Value::as_str),
            ) {
                if e_acc != l_acc {
                    let mut p = path.clone();
                    p.push(PathElem::from("access"));
                    file_findings.push((
                        f_idx,
                        p,
                        format!(
                            "documents entry '{name}': access {e_acc} differs from the corpus ledger's {l_acc}"
                        ),
                        false,
                    ));
                }
            }
            if let (Some(e_sha), Some(l_sha)) = (
                entry.get("sha256").and_then(Value::as_str),
                listed.get("sha256").and_then(Value::as_str),
            ) {
                if e_sha != l_sha {
                    // The one ledger finding about facts: the spec may cite other bytes than the
                    // ledger recorded, so this error makes the root untrusted (`trust = true`).
                    let mut p = path;
                    p.push(PathElem::from("sha256"));
                    file_findings.push((
                        f_idx,
                        p,
                        format!(
                            "documents entry '{name}': sha256 differs from the corpus ledger's; one of them names other bytes"
                        ),
                        true,
                    ));
                }
            }
        }
    }

    for (f_idx, path, msg, trust) in file_findings {
        checker.add_file(f_idx, &path, msg, "error", false, true, trust);
    }
}

fn disposition_problem(
    checker: &Checker,
    root_idx: usize,
    group: &str,
    entry: &Value,
) -> Option<String> {
    let disp = entry.get("disposition").and_then(Value::as_str)?;
    let caps = SPEC_DISPOSITION_RE.captures(disp)?;
    let spec_id = caps.get(1)?.as_str();
    let fact_id_opt = caps.get(2).map(|m| m.as_str());

    let matching_files: Vec<usize> = checker
        .files
        .iter()
        .enumerate()
        .filter_map(|(idx, f)| {
            if f.spec_id() == spec_id {
                Some(idx)
            } else {
                None
            }
        })
        .collect();
    if matching_files.is_empty() {
        return Some(format!("no spec '{spec_id}' among the roots read"));
    }

    let root_rank = checker.roots[root_idx].rank;
    let root_layer = checker.roots[root_idx]
        .layer
        .as_deref()
        .unwrap_or("public");
    let layer_files: Vec<usize> = matching_files
        .into_iter()
        .filter(|&f_idx| checker.roots[checker.files[f_idx].root_idx].rank <= root_rank)
        .collect();
    if layer_files.is_empty() {
        return Some(format!(
            "spec '{spec_id}' is only in a layer that merges after this root's ({root_layer})"
        ));
    }

    if let Some(fact_id) = fact_id_opt {
        let has_fact = layer_files
            .iter()
            .any(|&f_idx| checker.files[f_idx].record_map.contains_key(fact_id));
        if !has_fact {
            return Some(format!("spec '{spec_id}' has no fact '{fact_id}'"));
        }
    }

    if group == "documents" {
        let doc_name = entry.get("name").and_then(Value::as_str).unwrap_or("");
        let lists_doc = layer_files
            .iter()
            .any(|&f_idx| checker.files[f_idx].documents.contains_key(doc_name));
        if !lists_doc {
            return Some(format!(
                "spec '{spec_id}' does not list document '{doc_name}' in resources.documents"
            ));
        }
    }

    None
}

fn check_placeholders(
    node: &Value,
    path: &mut Vec<PathElem>,
    out: &mut Vec<(Vec<PathElem>, String)>,
) {
    match node {
        Value::Object(map) => {
            for (k, v) in map {
                path.push(PathElem::from(k.as_str()));
                check_placeholders(v, path, out);
                path.pop();
            }
        }
        Value::Array(items) => {
            for (i, v) in items.iter().enumerate() {
                path.push(PathElem::Index(i));
                check_placeholders(v, path, out);
                path.pop();
            }
        }
        Value::String(s) if s.contains('<') => {
            let found = specmd::placeholders(s, false);
            if let Some((_, _, tok)) = found.first() {
                out.push((
                    path.clone(),
                    format!("unsubstituted template placeholder '{tok}'"),
                ));
            }
        }
        _ => {}
    }
}

/// One row in a corpus coverage group (`documents` or `blocks`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CorpusRow {
    pub name: String,
    pub title: String,
    pub subsystem: String,
    pub state: String,
    pub disposition: String,
}

/// Group coverage summary (`rows` and `counts` by state).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CorpusGroupCoverage {
    pub rows: Vec<CorpusRow>,
    pub counts: BTreeMap<String, usize>,
}

/// Per-root entry in `driver-lab corpus` output.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CorpusRootEntry {
    pub path: String,
    pub name: Option<String>,
    pub ledger: String,
    pub coverage: Option<BTreeMap<String, CorpusGroupCoverage>>,
}

/// Computes coverage for `root_idx` (`corpus.py:coverage`), or `None` when the root has no valid
/// ledger.
#[must_use]
pub fn coverage(
    checker: &Checker,
    root_idx: usize,
) -> Option<BTreeMap<String, CorpusGroupCoverage>> {
    let loaded: &Loaded = checker.roots[root_idx].corpus.as_ref()?;
    let data = loaded.data.as_ref()?;

    // Recompute unresolved `(group, name)` pairs identically to `_check_root`.
    let mut unresolved: HashSet<(String, String)> = HashSet::new();
    for &group in GROUPS {
        let mut seen: HashSet<String> = HashSet::new();
        if let Some(entries) = data.get(group).and_then(Value::as_array) {
            for entry in entries {
                let Some(name) = entry.get("name").and_then(Value::as_str) else {
                    continue;
                };
                if !seen.insert(name.to_string()) {
                    continue;
                }
                let disp = entry
                    .get("disposition")
                    .and_then(Value::as_str)
                    .unwrap_or("");
                if state(disp) == "spec"
                    && disposition_problem(checker, root_idx, group, entry).is_some()
                {
                    unresolved.insert((group.to_string(), name.to_string()));
                }
            }
        }
    }

    let mut out = BTreeMap::new();
    for &group in GROUPS {
        let mut rows = Vec::new();
        if let Some(entries) = data.get(group).and_then(Value::as_array) {
            for e in entries {
                let name = e
                    .get("name")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let title = e
                    .get("title")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let subsystem = e
                    .get("subsystem")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let disposition = e
                    .get("disposition")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let row_state = if unresolved.contains(&(group.to_string(), name.clone())) {
                    "unresolved".to_string()
                } else {
                    state(&disposition).to_string()
                };
                rows.push(CorpusRow {
                    name,
                    title,
                    subsystem,
                    state: row_state,
                    disposition,
                });
            }
        }
        let mut counts = BTreeMap::new();
        for &s in STATES {
            let count = rows.iter().filter(|r| r.state == s).count();
            counts.insert(s.to_string(), count);
        }
        out.insert(group.to_string(), CorpusGroupCoverage { rows, counts });
    }
    Some(out)
}

/// Formats a one-line summary for a coverage map (`corpus.py:summary`).
#[must_use]
pub fn summary(cov: &BTreeMap<String, CorpusGroupCoverage>) -> String {
    GROUPS
        .iter()
        .map(|&group| {
            let gcov = &cov[group];
            let parts: Vec<String> = STATES
                .iter()
                .filter_map(|&s| {
                    let count = gcov.counts.get(s).copied().unwrap_or(0);
                    if s != "unresolved" || count > 0 {
                        Some(format!("{count} {s}"))
                    } else {
                        None
                    }
                })
                .collect();
            format!("{group} {}", parts.join(", "))
        })
        .collect::<Vec<_>>()
        .join("; ")
}

/// Executes `driver-lab corpus` (`spec.py:cmd_corpus`).
pub fn run_corpus_cmd(
    cli: &Cli,
    args: &CorpusArgs,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let mut root_paths = args.targets.clone();
    if let Some(ref r) = args.root {
        if !root_paths.contains(r) {
            root_paths.push(r.clone());
        }
    }
    // Accept either root directories or `<root>/corpus.yaml` paths (`CorpusArgs.targets`).
    let normalized_roots: Vec<std::path::PathBuf> = root_paths
        .into_iter()
        .map(|p| {
            if p.file_name().and_then(|n| n.to_str()) == Some(CORPUS) && p.is_file() {
                p.parent()
                    .unwrap_or_else(|| Path::new("."))
                    .to_path_buf()
            } else {
                p
            }
        })
        .collect();

    if normalized_roots.is_empty() {
        return emit_corpus_error(
            "usage",
            EXIT_USAGE_ERROR,
            "corpus requires at least one spec root directory",
            cli.json,
            stdout,
            stderr,
        );
    }

    let public_skills: HashSet<String> = args.public_skills.iter().cloned().collect();
    let schemas = crate::records::load_schemas();
    let mut checker = Checker::new(args.require_license, public_skills, None);
    if let Err((code, msg)) = crate::speccheck::load_and_run_checker(
        &mut checker,
        &normalized_roots,
        &args.context_roots,
        &[],
        &[],
        false,
        cli.offline,
        schemas,
    ) {
        let kind = if code == EXIT_USAGE_ERROR {
            "usage"
        } else {
            "precondition"
        };
        return emit_corpus_error(kind, code, &msg, cli.json, stdout, stderr);
    }

    let mut roots = Vec::new();
    let num_roots = checker.roots.len();
    for r_idx in 0..num_roots {
        if checker.roots[r_idx].context {
            continue;
        }
        if checker.roots[r_idx].corpus_path.is_none() {
            let missing_path = checker.roots[r_idx].given.join(CORPUS);
            let label = checker.roots[r_idx].label();
            checker.add_where(
                &missing_path,
                Some(r_idx),
                None,
                &[],
                format!(
                    "root {label} has no corpus ledger: every document and block it considered needs a recorded disposition (#153)"
                ),
                "error",
                false,
                true,
                false,
            );
        }
        let ledger = if checker.roots[r_idx].corpus_path.is_none() {
            "missing".to_string()
        } else if checker.roots[r_idx].corpus.is_some() {
            "ok".to_string()
        } else {
            "invalid".to_string()
        };
        let cov = coverage(&checker, r_idx);
        roots.push(CorpusRootEntry {
            path: checker.roots[r_idx].given.to_string_lossy().into_owned(),
            name: checker.roots[r_idx].name.clone(),
            ledger,
            coverage: cov,
        });
    }

    let ordered = checker.ordered_findings();
    let errors = ordered.iter().filter(|f| f.level == "error").count();
    let warnings = ordered.len() - errors;

    let mut text = Vec::new();
    for r in &roots {
        let label = r.name.as_deref().unwrap_or(&r.path);
        if let Some(ref cov) = r.coverage {
            text.push(format!("{label}: {}", summary(cov)));
            for &group in GROUPS {
                if let Some(gcov) = cov.get(group) {
                    let singular = &group[..group.len() - 1];
                    for row in &gcov.rows {
                        if row.state != "spec" {
                            text.push(format!("  {singular} {}: {}", row.name, row.disposition));
                        }
                    }
                }
            }
        } else {
            text.push(format!("{label}: {} ledger", r.ledger));
        }
    }
    for f in &ordered {
        text.push(f.to_string());
    }
    text.push(format!(
        "{} root(s): {errors} error(s), {warnings} warning(s)",
        roots.len()
    ));

    let code = if errors > 0 {
        EXIT_DOMAIN_FAILURE
    } else {
        EXIT_OK
    };
    if cli.json {
        let payload = json!({
            "ok": errors == 0,
            "roots": roots,
            "errors": errors,
            "warnings": warnings,
            "findings": ordered,
        });
        let _ = writeln!(
            stdout,
            "{}",
            serde_json::to_string(&payload).unwrap_or_default()
        );
    } else {
        for line in text {
            let _ = writeln!(stdout, "{}", visible_name(&line));
        }
    }
    code
}

fn emit_corpus_error(
    kind: &str,
    code: i32,
    msg: &str,
    json_mode: bool,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    if json_mode {
        let payload = json!({
            "ok": false,
            "error": kind,
            "roots": [],
            "errors": 1,
            "warnings": 0,
            "findings": [{
                "path": "",
                "line": 0,
                "column": 0,
                "level": "error",
                "message": msg,
            }],
        });
        let _ = writeln!(
            stdout,
            "{}",
            serde_json::to_string(&payload).unwrap_or_default()
        );
    } else {
        let label = match kind {
            "usage" => "usage error",
            "precondition" => "missing precondition",
            _ => "internal error",
        };
        let _ = writeln!(stderr, "{}", visible_name(&format!("{label}: {msg}")));
    }
    code
}
