// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Semantic specification checker (`skills/spec-format/scripts/speccheck.py`,
//! `textcheck.py`, `review.py`, `headingcheck.py`, `index.py:check`,
//! `RUST-TOOLING-DESIGN.md` §4.2 `BF-IMX-ISS-4`, §4.3 `BF-IMX-12`, `BF-IMX-14`, `BF-IMX-18`,
//! §4.5 `BF-GW-24`, `BF-GW-25`, `BF-GW-27`, `RT-3b`, `RT-4`).

use crate::diagnostic::{
    visible_name, Finding, EXIT_DOMAIN_FAILURE, EXIT_OK, EXIT_SANDBOX_ERROR, EXIT_USAGE_ERROR,
};
use crate::model::{CORPUS, MARKER};
use crate::records::{
    anchors, format_where, registry_entry_label, supports, CheckReport, Checker, PathElem,
    RootInfo, Schemas, SpecFile, SpecFinding, SpecRecord, SpecRoot, REGISTRIES, SPEC_SUFFIX,
    STATUSES,
};
use crate::spdx::{self, SpdxError};
use crate::yaml_strict::Loaded;
use crate::{CheckArgs, Cli};
use regex::Regex;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::sync::LazyLock;

const LAYERS: &[&str] = &["public", "ip-vendor", "soc-vendor", "product", "local"];

const TEXT_KEYS: &[&str] = &[
    "claim",
    "title",
    "note",
    "orientation",
    "milestones",
    "notes",
    "states",
];

const LINT_KEYS: &[&str] = &["claim", "orientation", "milestones", "notes"];

static BACKTICKS_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"`{33,}").expect("valid BACKTICKS_RE"));

static DIGITS_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[0-9]+$").expect("valid DIGITS_RE"));

static FRONTMATTER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?s)^---\n(.*?)\n---(\n|$)").expect("valid FRONTMATTER_RE"));

static STUB_SPEC_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"`spec:\s*([a-z0-9][a-z0-9\-]*)`").expect("valid STUB_SPEC_RE"));

static STUB_INSTANCE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"`instance:\s*([a-z0-9][a-z0-9\-]*)#([a-z0-9][a-z0-9\-]*)`")
        .expect("valid STUB_INSTANCE_RE")
});

static STUB_NAME_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?m)^name:\s*["']?([^\s"']+)["']?\s*$"#).expect("valid STUB_NAME_RE")
});

static STUB_SPLIT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"`split:\s*([^`]+)`").expect("valid STUB_SPLIT_RE"));

static WORD_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"[a-z0-9][a-z0-9-]*").expect("valid WORD_RE"));

static HTML_HEADING_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?is)<h[1-6][^>]*>(.*?)</h[1-6]>").expect("valid HTML_HEADING_RE")
});

static HTML_TAG_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?is)<[^>]+>").expect("valid HTML_TAG_RE"));

static MD_HEADING_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?m)^\s{0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?\s*$").expect("valid MD_HEADING_RE")
});

/// Explicit context-root taint classification (`BF-GW-27`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TaintClass {
    /// YAML/JSON Schema load errors, root/layer/spec/fact ID collisions, license-gate violations,
    /// and refused-character/containment errors that taint a context root and block `render --merged`.
    TaintingError,
    /// Unresolved references from a context root to a third root not loaded for this invocation,
    /// or upstream `.verify.yaml` `spec_file` path mismatches that downgrade to warnings without
    /// tainting the context root (`BF-GW-27`).
    DowngradedContextWarning,
}

/// Classifies a finding message on a context root into [`TaintClass`] (`BF-GW-27`).
#[must_use]
pub fn classify_context_finding(message: &str) -> TaintClass {
    let raw = message.strip_prefix("context root: ").unwrap_or(message);
    if raw.ends_with("resolves to no spec")
        || (raw.starts_with("spec_file '") && raw.contains(": this record belongs to '"))
    {
        TaintClass::DowngradedContextWarning
    } else {
        TaintClass::TaintingError
    }
}

pub(crate) fn allowed_sections(kind: &str) -> &'static [&'static str] {
    match kind {
        "chip" | "soc" | "board" => &["quick-facts", "gotchas", "topology"],
        "ip" => &[
            "standards",
            "programming-model",
            "data-formats",
            "variants-quirks",
            "gotchas",
        ],
        "protocol" => &[
            "standards",
            "programming-model",
            "data-formats",
            "sub-protocols",
            "variants-quirks",
            "gotchas",
            "open-questions",
        ],
        "peripheral" => &[
            "identity",
            "registers",
            "sequences",
            "data-formats",
            "interrupts",
            "dma",
            "sub-protocols",
            "target",
            "gotchas",
            "open-questions",
        ],
        "review" => &[
            "identity",
            "correspondence",
            "coverage",
            "findings",
            "agreements",
            "open-questions",
        ],
        "facts" => &["facts"],
        _ => &[],
    }
}

fn through_link(path: &Path) -> bool {
    let mut cur = if path.is_absolute() {
        PathBuf::from("/")
    } else {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    };
    for comp in path.components() {
        match comp {
            Component::RootDir => cur = PathBuf::from("/"),
            Component::CurDir => {
                cur.push(".");
                if cur.is_symlink() {
                    return true;
                }
            }
            Component::ParentDir => {
                cur.push("..");
                if cur.is_symlink() {
                    return true;
                }
            }
            Component::Normal(part) => {
                cur.push(part);
                if cur.is_symlink() {
                    return true;
                }
            }
            Component::Prefix(_) => {}
        }
    }
    false
}

fn rel_to_root(root: &SpecRoot, path: &Path) -> String {
    path.strip_prefix(&root.given)
        .map(|p| p.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path.to_string_lossy().into_owned())
}

fn rel_spec_file(root: &SpecRoot, file: &SpecFile) -> String {
    match file.path.strip_prefix(&root.given) {
        Ok(rel) => format!(
            "{}:{}",
            root.label(),
            rel.to_string_lossy().replace('\\', "/")
        ),
        Err(_) => file.path.to_string_lossy().into_owned(),
    }
}

fn record_kind_word(rec: &SpecRecord) -> &'static str {
    match rec.path.first() {
        Some(PathElem::Key(k)) if k == "instances" => "instance",
        Some(PathElem::Key(k)) if k == "variants" => "variant",
        _ => "fact",
    }
}

fn what_record(rec: &SpecRecord) -> String {
    format!("{} '{}'", record_kind_word(rec), rec.id)
}

fn number_key(digits: &str) -> (usize, &str) {
    let trimmed = digits.trim_start_matches('0');
    let norm = if trimmed.is_empty() { "0" } else { trimmed };
    (norm.len(), norm)
}

fn short_repr(value: &str) -> String {
    let chars: Vec<char> = value.chars().collect();
    if chars.len() <= 24 {
        format!("'{value}'")
    } else {
        let head: String = chars[..12].iter().collect();
        let tail: String = chars[chars.len() - 6..].iter().collect();
        format!("'{head}...{tail}'")
    }
}

// ---------------------------------------------------------------------------
// Text checking (`textcheck.py`)
// ---------------------------------------------------------------------------

/// Scans `node` for any string or key containing a run of more than 32 backticks (`textcheck.py:check_backticks`).
pub fn textcheck_backticks_where(
    checker: &mut Checker,
    file_path: &Path,
    root_idx: Option<usize>,
    loaded: Option<&Loaded>,
    node: &Value,
    trust: bool,
) {
    fn walk(
        checker: &mut Checker,
        file_path: &Path,
        root_idx: Option<usize>,
        loaded: Option<&Loaded>,
        node: &Value,
        path: &[PathElem],
        is_key: bool,
        trust: bool,
    ) {
        match node {
            Value::String(s) => {
                if BACKTICKS_RE.is_match(s) {
                    let suffix = if is_key { " key" } else { "" };
                    checker.add_where(
                        file_path,
                        root_idx,
                        loaded,
                        path,
                        format!(
                            "{}{suffix}: a run of more than 32 backticks",
                            format_where(path)
                        ),
                        "error",
                        is_key,
                        true,
                        trust,
                    );
                }
            }
            Value::Object(map) => {
                for (k, v) in map {
                    let mut p = path.to_vec();
                    p.push(PathElem::Key(k.clone()));
                    walk(
                        checker,
                        file_path,
                        root_idx,
                        loaded,
                        &Value::String(k.clone()),
                        &p,
                        true,
                        trust,
                    );
                    walk(checker, file_path, root_idx, loaded, v, &p, false, trust);
                }
            }
            Value::Array(arr) => {
                for (i, item) in arr.iter().enumerate() {
                    let mut p = path.to_vec();
                    p.push(PathElem::Index(i));
                    walk(checker, file_path, root_idx, loaded, item, &p, false, trust);
                }
            }
            _ => {}
        }
    }
    walk(
        checker,
        file_path,
        root_idx,
        loaded,
        node,
        &[],
        false,
        trust,
    );
}

fn text_fields(node: &Value, path: &[PathElem]) -> Vec<(Vec<PathElem>, String, String)> {
    let mut out = Vec::new();
    match node {
        Value::Object(map) => {
            for (k, v) in map {
                if path.is_empty() && k == "notices" {
                    continue;
                }
                let mut child = path.to_vec();
                child.push(PathElem::Key(k.clone()));
                if TEXT_KEYS.contains(&k.as_str()) {
                    if let Some(s) = v.as_str() {
                        out.push((child, k.clone(), s.to_string()));
                        continue;
                    }
                }
                out.extend(text_fields(v, &child));
            }
        }
        Value::Array(arr) => {
            for (i, item) in arr.iter().enumerate() {
                let mut child = path.to_vec();
                child.push(PathElem::Index(i));
                out.extend(text_fields(item, &child));
            }
        }
        _ => {}
    }
    out
}

/// Checks Spec Markdown prose fields in `data` (`textcheck.py:check_data`).
pub fn textcheck_data_where(
    checker: &mut Checker,
    file_path: &Path,
    root_idx: Option<usize>,
    loaded: Option<&Loaded>,
    data: &Value,
    records: Option<&[(String, SpecRecord)]>,
    trust: bool,
) {
    textcheck_backticks_where(checker, file_path, root_idx, loaded, data, trust);
    for (path, key, value) in text_fields(data, &[]) {
        let owner_id = records.and_then(|recs| {
            if path.len() < 2 {
                return None;
            }
            recs.iter().find_map(|(_, r)| {
                if r.path.len() == 2 && r.path[..] == path[..2] {
                    Some(r.id.clone())
                } else {
                    None
                }
            })
        });
        let label = match owner_id {
            Some(id) => format!("fact '{id}', "),
            None => String::new(),
        };
        let lint = LINT_KEYS.contains(&key.as_str());
        for finding in crate::specmd::findings(&value, lint) {
            checker.add_where(
                file_path,
                root_idx,
                loaded,
                &path,
                format!(
                    "{label}{} (field line {}): {}",
                    format_where(&path),
                    finding.line,
                    finding.message
                ),
                finding.level.as_str(),
                false,
                true,
                trust,
            );
        }
    }
}

fn textcheck_file(checker: &mut Checker, file_idx: usize) {
    let file_path = checker.files[file_idx].path.clone();
    let root_idx = checker.files[file_idx].root_idx;
    let rel = rel_to_root(&checker.roots[root_idx], &file_path);
    textcheck_backticks_where(
        checker,
        &file_path,
        Some(root_idx),
        None,
        &json!({ "source_path": rel }),
        true,
    );
    let loaded = checker.files[file_idx].loaded.clone();
    let data = checker.files[file_idx].data.clone();
    let records = checker.files[file_idx].records.clone();
    textcheck_data_where(
        checker,
        &file_path,
        Some(root_idx),
        Some(&loaded),
        &data,
        Some(&records),
        true,
    );
}

// ---------------------------------------------------------------------------
// Root loading (`speccheck.py:load_roots`, `read_marker`, `load_corpus`, `load_index`)
// ---------------------------------------------------------------------------

static CACHED_SCHEMA_MAP: LazyLock<BTreeMap<String, Value>> =
    LazyLock::new(crate::schema::load_schemas);

fn fast_validate_file(
    path: &Path,
    schema_map: &BTreeMap<String, Value>,
    extension: Option<&Value>,
    findings: &mut Vec<Finding>,
) -> Result<(bool, crate::model::SchemaKind, Option<Loaded>), String> {
    if extension.is_none() {
        if let Ok(kind) = crate::model::schema_kind(path) {
            let mut tmp_findings = Vec::new();
            if let Ok((true, _, Some(loaded))) = crate::records::validate_file(
                path,
                crate::records::load_schemas(),
                None,
                &mut tmp_findings,
            ) {
                let is_facts = path
                    .file_name()
                    .map(|n| n.to_string_lossy().ends_with(".facts.yaml"))
                    .unwrap_or(false);
                let facts_ok = !is_facts
                    || loaded
                        .data
                        .as_ref()
                        .and_then(|d| d.get("kind"))
                        .and_then(Value::as_str)
                        == Some("overlay");
                if facts_ok && tmp_findings.is_empty() {
                    return Ok((true, kind, Some(loaded)));
                }
            }
        }
    }
    crate::schema::validate_file(path, schema_map, extension, findings)
}

fn add_schema_findings_to_checker(
    checker: &mut Checker,
    raw: Vec<Finding>,
    root_idx: Option<usize>,
    trust: bool,
) {
    for f in raw {
        checker.add_where(
            Path::new(&f.path),
            root_idx,
            None,
            &[],
            f.message,
            "error",
            false,
            true,
            trust,
        );
        // Fix line and column on the just-pushed SpecFinding:
        if let Some(last) = checker.findings.last_mut() {
            last.line = f.line;
            last.column = f.col;
        }
        if let Some(r_idx) = root_idx {
            if trust {
                if let Some(last_untrusted) = checker.roots[r_idx].untrusted.last_mut() {
                    last_untrusted.0 = format!("{}:{}:{}", f.path, f.line, f.col);
                }
            }
        }
    }
}

fn load_untrusting(
    checker: &mut Checker,
    root_idx: usize,
    path: &Path,
    schema_map: &BTreeMap<String, Value>,
) -> Option<Loaded> {
    let mut raw = Vec::new();
    let (ok, _, loaded_opt) = match fast_validate_file(path, schema_map, None, &mut raw) {
        Ok(res) => res,
        Err(msg) => {
            checker.add_where(
                path,
                Some(root_idx),
                None,
                &[],
                msg,
                "error",
                false,
                true,
                false,
            );
            return None;
        }
    };
    add_schema_findings_to_checker(checker, raw, Some(root_idx), false);
    if ok {
        loaded_opt
    } else {
        None
    }
}

fn read_marker_full(
    checker: &mut Checker,
    root_idx: usize,
    schema_map: &BTreeMap<String, Value>,
) {
    let marker_path = checker.roots[root_idx].given.join(MARKER);
    let mut raw = Vec::new();
    let (ok, _, loaded_opt) =
        match fast_validate_file(&marker_path, schema_map, None, &mut raw) {
            Ok(res) => res,
            Err(msg) => {
                checker.add_where(
                    &marker_path,
                    Some(root_idx),
                    None,
                    &[],
                    msg,
                    "error",
                    false,
                    true,
                    true,
                );
                checker.unreadable_markers.push(marker_path);
                return;
            }
        };
    add_schema_findings_to_checker(checker, raw, Some(root_idx), true);
    let Some(loaded) = loaded_opt else {
        checker.unreadable_markers.push(marker_path);
        return;
    };
    if !ok {
        checker.unreadable_markers.push(marker_path);
        return;
    }
    let Some(data) = loaded.data.clone() else {
        checker.unreadable_markers.push(marker_path);
        return;
    };

    let mut ext_findings = Vec::new();
    let extension = crate::schema::load_extension(&marker_path, &data, &mut ext_findings);
    let has_ext_errors = !ext_findings.is_empty();
    add_schema_findings_to_checker(checker, ext_findings, Some(root_idx), true);
    if has_ext_errors {
        checker.unreadable_markers.push(marker_path);
        return;
    }

    let name = data
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let layer = data
        .get("layer")
        .and_then(Value::as_str)
        .unwrap_or("public")
        .to_string();
    let rank = LAYERS.iter().position(|&l| l == layer).unwrap_or(0);
    checker.roots[root_idx].name = Some(name);
    checker.roots[root_idx].layer = Some(layer);
    checker.roots[root_idx].rank = rank;
    checker.roots[root_idx].extension = extension;
    checker.roots[root_idx].marker = Some(loaded.clone());

    textcheck_backticks_where(
        checker,
        &marker_path,
        Some(root_idx),
        Some(&loaded),
        &data,
        true,
    );

    if let Some(lic) = data.get("license").and_then(Value::as_str) {
        if let Err(SpdxError(msg)) = spdx::parse(lic) {
            checker.add_where(
                &marker_path,
                Some(root_idx),
                Some(&loaded),
                &[PathElem::from("license")],
                format!("license: {msg}"),
                "error",
                false,
                true,
                true,
            );
        }
    }

    let mut accepts = BTreeSet::new();
    let mut seen: HashMap<String, String> = HashMap::new();
    if let Some(arr) = data.get("accepts").and_then(Value::as_array) {
        for (i, item) in arr.iter().enumerate() {
            let Some(s) = item.as_str() else {
                continue;
            };
            match spdx::parse_identifier(s) {
                Ok(canon) => {
                    if canon != s {
                        checker.add_where(
                            &marker_path,
                            Some(root_idx),
                            Some(&loaded),
                            &[PathElem::from("accepts"), PathElem::Index(i)],
                            format!("accepts entry '{s}': write it as '{canon}', its one spelling"),
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                    if let Some(prev) = seen.get(&canon) {
                        checker.add_where(
                            &marker_path,
                            Some(root_idx),
                            Some(&loaded),
                            &[PathElem::from("accepts"), PathElem::Index(i)],
                            format!("accepts lists {canon} twice (as '{prev}' and '{s}')"),
                            "error",
                            false,
                            true,
                            true,
                        );
                    } else {
                        seen.insert(canon.clone(), s.to_string());
                    }
                    accepts.insert(canon);
                }
                Err(SpdxError(msg)) => {
                    checker.add_where(
                        &marker_path,
                        Some(root_idx),
                        Some(&loaded),
                        &[PathElem::from("accepts"), PathElem::Index(i)],
                        format!("accepts entry '{s}': {msg}"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }
    }
    checker.roots[root_idx].accepts = Some(accepts);
}

fn walk_root_full(checker: &mut Checker, root_idx: usize) -> Result<Vec<PathBuf>, (i32, String)> {
    let root_given = checker.roots[root_idx].given.clone();
    let is_ctx = checker.roots[root_idx].context;
    let root_label = checker.roots[root_idx].label();
    let mut found = Vec::new();
    let mut stack = vec![root_given.clone()];

    while let Some(top) = stack.pop() {
        let entries = match std::fs::read_dir(&top) {
            Ok(rd) => rd,
            Err(err) => {
                checker.add_where(
                    &top,
                    Some(root_idx),
                    None,
                    &[],
                    format!(
                        "cannot list this directory ({err}); the root's specs are not all known, so the check cannot pass"
                    ),
                    "error",
                    false,
                    false,
                    true,
                );
                continue;
            }
        };
        let mut dirs = Vec::new();
        let mut names = Vec::new();
        for entry in entries.flatten() {
            let path = entry.path();
            let name = entry.file_name().to_string_lossy().into_owned();
            let ft = match std::fs::symlink_metadata(&path) {
                Ok(m) => m.file_type(),
                Err(_) => continue,
            };
            if ft.is_symlink() {
                if is_ctx {
                    return Err((
                        EXIT_USAGE_ERROR,
                        format!(
                            "--context-root {}: {} is a symbolic link; a root holds its files itself",
                            root_given.display(),
                            path.display()
                        ),
                    ));
                }
                checker.add_where(
                    &path,
                    Some(root_idx),
                    None,
                    &[],
                    "symbolic link in a spec root: a root holds its files itself, never through links",
                    "error",
                    false,
                    true,
                    true,
                );
                continue;
            }
            if ft.is_dir() {
                dirs.push((name, path));
            } else {
                names.push((name, path));
            }
        }
        dirs.sort_by(|a, b| a.0.cmp(&b.0));
        names.sort_by(|a, b| a.0.cmp(&b.0));

        for (name, path) in names {
            let lower = name.to_ascii_lowercase();
            if name == MARKER && top != root_given {
                checker.add_where(
                    &path,
                    Some(root_idx),
                    None,
                    &[],
                    format!("a nested {MARKER} inside root {root_label}: one root, one marker"),
                    "error",
                    false,
                    true,
                    true,
                );
            } else if name == CORPUS {
                if top == root_given {
                    checker.roots[root_idx].corpus_path = Some(path);
                } else {
                    checker.add_where(
                        &path,
                        Some(root_idx),
                        None,
                        &[],
                        format!("a corpus ledger lives beside the root's {MARKER}: move it there"),
                        "error",
                        false,
                        true,
                        false,
                    );
                }
            } else if lower.starts_with("corpus.") || lower == "corpus" {
                checker.add_where(
                    &path,
                    Some(root_idx),
                    None,
                    &[],
                    format!(
                        "not read as a corpus ledger: name it {CORPUS} beside the root's {MARKER}, or move it out of the root"
                    ),
                    "error",
                    false,
                    true,
                    false,
                );
            } else if name.ends_with(".spec.yaml") {
                found.push(path);
            } else if name.ends_with(".index.yaml") {
                if top == root_given.join("index") {
                    checker.roots[root_idx].index_paths.push(path);
                } else {
                    checker.add_where(
                        &path,
                        Some(root_idx),
                        None,
                        &[],
                        "a document index lives in the root's own index/ directory: move it there",
                        "error",
                        false,
                        true,
                        false,
                    );
                }
            } else if lower.contains(".index.") {
                checker.add_where(
                    &path,
                    Some(root_idx),
                    None,
                    &[],
                    "not read as a document index: name it <document>.index.yaml in index/",
                    "error",
                    false,
                    true,
                    false,
                );
            } else if name.ends_with(".verify.yaml") {
                if top == root_given.join("resources") {
                    checker.roots[root_idx].record_paths.push(path);
                } else {
                    checker.add_where(
                        &path,
                        Some(root_idx),
                        None,
                        &[],
                        "a verification record lives in the root's own resources/ directory: move it there",
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            } else if lower.ends_with(".spec.md") {
                checker.add_where(
                    &path,
                    Some(root_idx),
                    None,
                    &[],
                    "a Markdown spec (.spec.md) is not read: specs are <name>.spec.yaml files",
                    "error",
                    false,
                    true,
                    true,
                );
            } else if lower.contains(".spec.") || lower.contains(".facts.") {
                let want = if lower.contains(".facts.") {
                    "a facts file does not belong in a spec root"
                } else {
                    "name it *.spec.yaml (lowercase, .yaml), or move it out of the root"
                };
                checker.add_where(
                    &path,
                    Some(root_idx),
                    None,
                    &[],
                    format!("not read as a spec: {want}"),
                    "error",
                    false,
                    true,
                    true,
                );
            } else if lower.contains(".verify.")
                || (top == root_given.join("resources") && lower.contains("verify"))
            {
                checker.add_where(
                    &path,
                    Some(root_idx),
                    None,
                    &[],
                    "not read as a verification record: name it <name>.verify.yaml (lowercase, .yaml) in resources/, or move it out of the root",
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }

        for (_, dpath) in dirs.into_iter().rev() {
            stack.push(dpath);
        }
    }
    Ok(found)
}

fn load_spec_full(
    checker: &mut Checker,
    root_idx: usize,
    path: &Path,
    schema_map: &BTreeMap<String, Value>,
) {
    let ext = checker.roots[root_idx].extension.clone();
    let mut raw = Vec::new();
    let (ok, _, loaded_opt) =
        match fast_validate_file(path, schema_map, ext.as_ref(), &mut raw) {
            Ok(res) => res,
            Err(msg) => {
                checker.add_where(
                    path,
                    Some(root_idx),
                    None,
                    &[],
                    msg,
                    "error",
                    false,
                    true,
                    true,
                );
                return;
            }
        };
    add_schema_findings_to_checker(checker, raw, Some(root_idx), true);
    if !ok {
        return;
    }
    let Some(loaded) = loaded_opt else {
        return;
    };
    let Some(data) = loaded.data.clone() else {
        return;
    };
    let file_idx = checker.files.len();
    checker.files.push(SpecFile {
        path: path.to_path_buf(),
        root_idx,
        loaded,
        data,
        records: Vec::new(),
        record_map: HashMap::new(),
        duplicated: HashSet::new(),
        assumptions: HashMap::new(),
        documents: HashMap::new(),
        repos: HashMap::new(),
        ambiguous: HashSet::new(),
        registries: HashMap::new(),
        record_state: "none".to_string(),
        record_path: None,
        record_loaded: None,
        verdicts: HashMap::new(),
    });
    checker.roots[root_idx].files.push(file_idx);
}

fn load_roots_full(
    checker: &mut Checker,
    checked: &[PathBuf],
    context: &[PathBuf],
    schema_map: &BTreeMap<String, Value>,
) -> Result<HashMap<usize, Vec<(PathBuf, Loaded)>>, (i32, String)> {
    let mut given: Vec<(PathBuf, bool)> = Vec::new();
    for p in checked {
        given.push((p.clone(), false));
    }
    for p in context {
        given.push((p.clone(), true));
    }
    for (p, _) in &given {
        if !p.is_dir() {
            return Err((EXIT_USAGE_ERROR, format!("{}: not a directory", p.display())));
        }
    }
    let mut reals: Vec<(PathBuf, PathBuf, bool)> = Vec::with_capacity(given.len());
    for (p, ctx) in given {
        let real = p.canonicalize().unwrap_or_else(|_| p.clone());
        reals.push((real, p, ctx));
    }
    for i in 0..reals.len() {
        for j in (i + 1)..reals.len() {
            let (a, pa, ca) = &reals[i];
            let (b, pb, cb) = &reals[j];
            if a == b {
                return Err((
                    EXIT_USAGE_ERROR,
                    format!(
                        "{} and {} are the same root; give each root once",
                        pa.display(),
                        pb.display()
                    ),
                ));
            }
            if a.starts_with(b) || b.starts_with(a) {
                let (inner, outer) = if a.starts_with(b) { (pa, pb) } else { (pb, pa) };
                let kind = if ca != cb {
                    "a context root and a checked root"
                } else {
                    "two roots"
                };
                return Err((
                    EXIT_USAGE_ERROR,
                    format!(
                        "{} sits inside {}: {kind} must be separate directories",
                        inner.display(),
                        outer.display()
                    ),
                ));
            }
        }
    }

    let mut loaded_indexes: HashMap<usize, Vec<(PathBuf, Loaded)>> = HashMap::new();

    for (order, (real, p, ctx)) in reals.into_iter().enumerate() {
        let root = SpecRoot {
            given: p.clone(),
            real,
            context: ctx,
            order,
            name: None,
            layer: None,
            rank: 0,
            accepts: None,
            extension: None,
            marker: None,
            files: Vec::new(),
            spec_paths: Vec::new(),
            record_paths: Vec::new(),
            corpus_path: None,
            corpus: None,
            index_paths: Vec::new(),
            untrusted: Vec::new(),
        };
        if through_link(&p) {
            if ctx {
                return Err((
                    EXIT_USAGE_ERROR,
                    format!(
                        "--context-root {} is, or is reached through, a symbolic link; give its real path",
                        p.display()
                    ),
                ));
            }
            let r_idx = checker.roots.len();
            checker.roots.push(root);
            checker.add_where(
                &p,
                Some(r_idx),
                None,
                &[],
                "spec root is, or is reached through, a symbolic link: give its real path",
                "error",
                false,
                true,
                true,
            );
            continue;
        }
        if !p.join(MARKER).is_file() {
            return Err((
                EXIT_SANDBOX_ERROR,
                format!("{}: no {MARKER} (not a spec root)", p.display()),
            ));
        }
        let r_idx = checker.roots.len();
        checker.roots.push(root);
        read_marker_full(checker, r_idx, schema_map);
        let files = walk_root_full(checker, r_idx)?;
        if checker.roots[r_idx].accepts.is_none() {
            checker.roots[r_idx].record_paths.clear();
            checker.roots[r_idx].corpus_path = None;
            checker.roots[r_idx].index_paths.clear();
            continue;
        }
        if let Some(cp) = checker.roots[r_idx].corpus_path.clone() {
            checker.roots[r_idx].corpus = load_untrusting(checker, r_idx, &cp, schema_map);
        }
        let index_paths = checker.roots[r_idx].index_paths.clone();
        let mut idx_list = Vec::new();
        for ip in index_paths {
            if let Some(ld) = load_untrusting(checker, r_idx, &ip, schema_map) {
                idx_list.push((ip, ld));
            }
        }
        loaded_indexes.insert(r_idx, idx_list);

        checker.roots[r_idx].spec_paths = files.clone();
        for path in files {
            load_spec_full(checker, r_idx, &path, schema_map);
        }
    }
    Ok(loaded_indexes)
}

// ---------------------------------------------------------------------------
// Per-file checking (`speccheck.py:check_file`, `review.py`, `BF-IMX-14`)
// ---------------------------------------------------------------------------

fn gate_expr(checker: &Checker, root_idx: usize, expression: &str) -> Option<String> {
    let tree = match spdx::parse(expression) {
        Ok(t) => t,
        Err(SpdxError(msg)) => {
            return Some(format!(
                "its license '{expression}' is not an SPDX expression ({msg})"
            ));
        }
    };
    let accepts = checker.roots[root_idx].accepts.clone().unwrap_or_default();
    if spdx::accepted(&tree, &accepts) {
        return None;
    }
    let shown = if accepts.is_empty() {
        "none: documents only".to_string()
    } else {
        accepts.into_iter().collect::<Vec<_>>().join(", ")
    };
    Some(format!(
        "{tree} is not accepted by root {} (accepts: {shown})",
        checker.roots[root_idx].label()
    ))
}

fn gate_name(
    checker: &mut Checker,
    file_idx: usize,
    path: &[PathElem],
    name: &str,
    what: &str,
    citation: bool,
) -> bool {
    let root_idx = checker.files[file_idx].root_idx;
    let Some((repo_val, _)) = checker.files[file_idx].repos.get(name).cloned() else {
        checker.reject(
            file_idx,
            path,
            format!(
                "{what} names repos entry '{name}', which is not in this file's resources.repos"
            ),
            citation,
        );
        return false;
    };
    let lic = repo_val
        .get("license")
        .and_then(Value::as_str)
        .unwrap_or("");
    if let Some(reason) = gate_expr(checker, root_idx, lic) {
        checker.reject(
            file_idx,
            path,
            format!("{what} names repos entry '{name}': {reason}"),
            citation,
        );
    }
    true
}

fn check_citation_full(
    checker: &mut Checker,
    file_idx: usize,
    what: &str,
    entry: &Value,
    path: &[PathElem],
) {
    let Some(name) = entry.get("doc").and_then(Value::as_str) else {
        return;
    };
    let cls = entry.get("class").and_then(Value::as_str).unwrap_or("");
    let mut doc_path = path.to_vec();
    doc_path.push(PathElem::from("doc"));

    let Some((doc, _)) = checker.files[file_idx].documents.get(name).cloned() else {
        checker.reject(
            file_idx,
            &doc_path,
            format!("{what}: document '{name}' is not in this file's resources.documents"),
            true,
        );
        return;
    };
    if doc.get("cite").and_then(Value::as_bool) == Some(false) {
        checker.reject(
            file_idx,
            &doc_path,
            format!(
                "{what}: document '{name}' is marked cite: false (a map only); it cannot be cited"
            ),
            true,
        );
    }
    let doc_cls = doc.get("class").and_then(Value::as_str).unwrap_or("");
    let is_databook_like = matches!(doc_cls, "databook" | "datasheet" | "errata" | "appnote");
    // BF-IMX-14: `datasheet`, `errata`, and `appnote` in `resources.documents[].class` are
    // databook-class documents citable via `class: databook` (or their own class name).
    let class_mismatch = match cls {
        "databook" => !is_databook_like,
        "datasheet" | "errata" | "appnote" => doc_cls != cls,
        "standard" | "doc" => doc_cls != cls,
        _ => false,
    };
    if class_mismatch {
        checker.reject(
            file_idx,
            &doc_path,
            format!("{what}: a {cls} citation names document '{name}' of class {doc_cls}"),
            true,
        );
    }

    let count = doc.get("pages").and_then(Value::as_i64);
    if let Some(at_arr) = entry.get("at").and_then(Value::as_array) {
        for (i, loc) in at_arr.iter().enumerate() {
            let mut lpath = path.to_vec();
            lpath.push(PathElem::from("at"));
            lpath.push(PathElem::Index(i));
            let has_precise = ["section", "page", "pages", "table", "figure", "clause"]
                .iter()
                .any(|k| loc.get(*k).is_some());
            if cls == "standard" && count.is_some() && !has_precise {
                checker.reject(
                    file_idx,
                    &lpath,
                    format!(
                        "{what}: document '{name}' is paged, so a standard locator needs a section, page, pages, table, figure or clause, not a heading alone"
                    ),
                    true,
                );
            }
            let mut numbers: Vec<(String, Vec<PathElem>)> = Vec::new();
            if let Some(pg) = loc.get("page").and_then(Value::as_str) {
                let mut p = lpath.clone();
                p.push(PathElem::from("page"));
                numbers.push((pg.to_string(), p));
            }
            if let Some(pgs) = loc.get("pages").and_then(Value::as_array) {
                for (k, pval) in pgs.iter().enumerate() {
                    if let Some(pg) = pval.as_str() {
                        let mut p = lpath.clone();
                        p.push(PathElem::from("pages"));
                        p.push(PathElem::Index(k));
                        numbers.push((pg.to_string(), p));
                    }
                }
            }
            for (value, vpath) in numbers {
                if !DIGITS_RE.is_match(&value) {
                    continue;
                }
                if value.len() > 1 && value.starts_with('0') {
                    let stripped = value.trim_start_matches('0');
                    let norm = if stripped.is_empty() { "0" } else { stripped };
                    checker.reject(
                        file_idx,
                        &vpath,
                        format!(
                            "{what}: page {}: write {} (no leading zeros)",
                            short_repr(&value),
                            short_repr(norm)
                        ),
                        true,
                    );
                }
                if let Some(c) = count {
                    let c_str = c.to_string();
                    if !(number_key(&value) >= number_key("1")
                        && number_key(&value) <= number_key(&c_str))
                    {
                        checker.reject(
                            file_idx,
                            &vpath,
                            format!(
                                "{what}: page {} is outside the {c} pages of document '{name}'",
                                short_repr(&value)
                            ),
                            true,
                        );
                    }
                }
            }
            if let Some(pgs) = loc.get("pages").and_then(Value::as_array) {
                if pgs.len() == 2 {
                    if let (Some(p0), Some(p1)) = (pgs[0].as_str(), pgs[1].as_str()) {
                        if DIGITS_RE.is_match(p0)
                            && DIGITS_RE.is_match(p1)
                            && number_key(p0) > number_key(p1)
                        {
                            let mut p = lpath;
                            p.push(PathElem::from("pages"));
                            checker.reject(
                                file_idx,
                                &p,
                                format!(
                                    "{what}: pages [{}, {}] run backwards; write [first, last]",
                                    short_repr(p0),
                                    short_repr(p1)
                                ),
                                true,
                            );
                        }
                    }
                }
            }
        }
    }
}

fn check_support_full(
    checker: &mut Checker,
    file_idx: usize,
    what: &str,
    data: &Value,
    base: &[PathElem],
    cited: &mut HashSet<String>,
) {
    for (entry, path) in supports(data, base) {
        if entry.get("doc").is_some() {
            check_citation_full(checker, file_idx, what, &entry, &path);
        }
    }
    for (anchor, path) in anchors(data, base) {
        if anchor.get("stale").is_some() {
            let mut p = path.clone();
            p.push(PathElem::from("stale"));
            checker.add_file(
                file_idx,
                &p,
                format!("{what}: stale anchor; re-verify and remove stale"),
                "error",
                false,
                true,
                true,
            );
        }
        let Some(name) = anchor.get("repo").and_then(Value::as_str) else {
            continue;
        };
        cited.insert(name.to_string());
        if let Some(lines) = anchor.get("lines").and_then(Value::as_array) {
            if lines.len() == 2 {
                if let (Some(l0), Some(l1)) = (lines[0].as_i64(), lines[1].as_i64()) {
                    if l0 > l1 {
                        let mut p = path.clone();
                        p.push(PathElem::from("lines"));
                        checker.reject(
                            file_idx,
                            &p,
                            format!("{what}: lines [{l0}, {l1}] run backwards; write [first, last]"),
                            true,
                        );
                    }
                }
            }
        }
        let mut repo_path = path.clone();
        repo_path.push(PathElem::from("repo"));
        if !gate_name(
            checker,
            file_idx,
            &repo_path,
            name,
            &format!("{what}: an anchor"),
            true,
        ) {
            continue;
        }
        let (entry, _) = checker.files[file_idx].repos[name].clone();
        if entry.get("commit").is_none() {
            checker.reject(
                file_idx,
                &repo_path,
                format!(
                    "{what}: anchor names repos entry '{name}', which pins a ref, not a commit; a cited entry carries the full commit"
                ),
                true,
            );
        }
        let listed: HashSet<String> = entry
            .get("files")
            .and_then(Value::as_array)
            .map(|arr| {
                arr.iter()
                    .filter_map(|item| {
                        item.get("path")
                            .and_then(Value::as_str)
                            .map(ToString::to_string)
                    })
                    .collect()
            })
            .unwrap_or_default();
        if let Some(apath) = anchor.get("path").and_then(Value::as_str) {
            if !listed.contains(apath) {
                let mut p = path.clone();
                p.push(PathElem::from("path"));
                checker.reject(
                    file_idx,
                    &p,
                    format!(
                        "{what}: '{apath}' is not in the files of repos entry '{name}' (the closed list of cited paths, D12)"
                    ),
                    true,
                );
            }
        }
    }

    let mut names: Vec<(String, Vec<PathElem>)> = Vec::new();
    if let Some(assumes) = data.get("assumes").and_then(Value::as_array) {
        for (i, a) in assumes.iter().enumerate() {
            if let Some(s) = a.as_str() {
                let mut p = base.to_vec();
                p.push(PathElem::from("assumes"));
                p.push(PathElem::Index(i));
                names.push((s.to_string(), p));
            }
        }
    }
    for (entry, at) in supports(data, base) {
        if let Some(premises) = entry.get("premises").and_then(Value::as_array) {
            for (j, premise) in premises.iter().enumerate() {
                if let Some(s) = premise.get("assumption").and_then(Value::as_str) {
                    let mut p = at.clone();
                    p.push(PathElem::from("premises"));
                    p.push(PathElem::Index(j));
                    p.push(PathElem::from("assumption"));
                    names.push((s.to_string(), p));
                }
            }
        }
    }
    for (name, path) in names {
        if !checker.files[file_idx].assumptions.contains_key(&name) {
            checker.reject(
                file_idx,
                &path,
                format!("{what}: assumption '{name}' is not in this file's assumptions"),
                true,
            );
        }
    }
}

fn check_review_file(checker: &mut Checker, file_idx: usize) {
    let Some(facts) = checker.files[file_idx]
        .data
        .get("facts")
        .and_then(Value::as_array)
        .cloned()
    else {
        return;
    };
    for (i, fact) in facts.iter().enumerate() {
        let Some(payload) = fact.get("data").and_then(Value::as_object) else {
            continue;
        };
        let fid = fact.get("id").and_then(Value::as_str).unwrap_or("");
        let what = format!("fact '{fid}'");
        let path = vec![PathElem::from("facts"), PathElem::Index(i)];

        if let Some(finding) = payload.get("finding").and_then(Value::as_object) {
            let fpath = vec![
                PathElem::from("facts"),
                PathElem::Index(i),
                PathElem::from("data"),
                PathElem::from("finding"),
            ];
            if finding.get("assessment").and_then(Value::as_str) == Some("bug")
                && !finding.contains_key("settled_by")
                && !finding.contains_key("self_evident")
            {
                checker.add_file(
                    file_idx,
                    &fpath,
                    format!(
                        "{what}: bug needs settled_by with document support or self_evident with reason"
                    ),
                    "error",
                    false,
                    true,
                    true,
                );
            }
            let mut has_impl = false;
            let mut has_ref = false;
            let mut has_impl_search = false;
            for (anchor, _) in anchors(fact, &path) {
                let rname = anchor.get("repo").and_then(Value::as_str).unwrap_or("");
                let role = checker.files[file_idx]
                    .repos
                    .get(rname)
                    .and_then(|(e, _)| e.get("role"))
                    .and_then(Value::as_str);
                if role == Some("impl") {
                    has_impl = true;
                    if anchor.get("search").is_some() {
                        has_impl_search = true;
                    }
                } else if role == Some("ref") {
                    has_ref = true;
                }
            }
            if !has_impl || !has_ref {
                checker.add_file(
                    file_idx,
                    &fpath,
                    format!("{what}: finding needs both impl and ref side anchors"),
                    "error",
                    false,
                    true,
                    true,
                );
            } else if finding.get("category").and_then(Value::as_str) == Some("missing")
                && !has_impl_search
            {
                let mut cpath = fpath;
                cpath.push(PathElem::from("category"));
                checker.add_file(
                    file_idx,
                    &cpath,
                    format!("{what}: missing finding needs an impl search anchor"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }

        if let Some(pair) = payload.get("pair").and_then(Value::as_object) {
            for side in ["impl", "ref"] {
                if let Some(arr) = pair.get(side).and_then(Value::as_array) {
                    for (j, anchor) in arr.iter().enumerate() {
                        let rname = anchor.get("repo").and_then(Value::as_str).unwrap_or("");
                        let role = checker.files[file_idx]
                            .repos
                            .get(rname)
                            .and_then(|(e, _)| e.get("role"))
                            .and_then(Value::as_str);
                        if role != Some(side) {
                            checker.add_file(
                                file_idx,
                                &[
                                    PathElem::from("facts"),
                                    PathElem::Index(i),
                                    PathElem::from("data"),
                                    PathElem::from("pair"),
                                    PathElem::from(side),
                                    PathElem::Index(j),
                                    PathElem::from("repo"),
                                ],
                                format!("{what}: pair {side} needs a repos entry with role: {side}"),
                                "error",
                                false,
                                true,
                                true,
                            );
                        }
                    }
                }
            }
        }
    }
}

fn check_placeholders_file(checker: &mut Checker, file_idx: usize) {
    let data = checker.files[file_idx].data.clone();
    let author_paths: HashSet<Vec<PathElem>> = text_fields(&data, &[])
        .into_iter()
        .map(|(p, _, _)| p)
        .collect();

    fn walk(
        checker: &mut Checker,
        file_idx: usize,
        node: &Value,
        path: &[PathElem],
        author_paths: &HashSet<Vec<PathElem>>,
    ) {
        match node {
            Value::String(s) => {
                if s.contains('<') {
                    let in_author = author_paths.contains(path);
                    if let Some((_, _, found)) =
                        crate::specmd::placeholders(s, in_author).into_iter().next()
                    {
                        checker.add_file(
                            file_idx,
                            path,
                            format!(
                                "{}: unsubstituted template placeholder '{found}'",
                                format_where(path)
                            ),
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }
            }
            Value::Object(map) => {
                for (k, v) in map {
                    if k == "symbol" {
                        continue;
                    }
                    if path.len() == 2 && path[0] == PathElem::from("notices") && k == "text" {
                        continue;
                    }
                    if k == "text"
                        && path
                            .iter()
                            .any(|elem| elem == &PathElem::from("attribution"))
                    {
                        continue;
                    }
                    let mut p = path.to_vec();
                    p.push(PathElem::Key(k.clone()));
                    walk(checker, file_idx, v, &p, author_paths);
                }
            }
            Value::Array(arr) => {
                for (i, item) in arr.iter().enumerate() {
                    let mut p = path.to_vec();
                    p.push(PathElem::Index(i));
                    walk(checker, file_idx, item, &p, author_paths);
                }
            }
            _ => {}
        }
    }

    walk(checker, file_idx, &data, &[], &author_paths);
}

fn check_file_full(checker: &mut Checker, file_idx: usize) {
    textcheck_file(checker, file_idx);

    let mut cited: HashSet<String> = HashSet::new();
    let top_records: Vec<SpecRecord> = checker.files[file_idx]
        .records
        .iter()
        .filter(|(_, r)| r.path.len() == 2)
        .map(|(_, r)| r.clone())
        .collect();
    for rec in top_records {
        let what = what_record(&rec);
        check_support_full(checker, file_idx, &what, &rec.data, &rec.path, &mut cited);
        if let Some(irq) = rec.data.get("irq").and_then(Value::as_object) {
            if let (Some(intid), Some(kind), Some(num)) = (
                irq.get("intid").and_then(Value::as_i64),
                irq.get("kind").and_then(Value::as_str),
                irq.get("number").and_then(Value::as_i64),
            ) {
                let offset = match kind {
                    "SPI" => Some(32),
                    "PPI" => Some(16),
                    _ => None,
                };
                if let Some(off) = offset {
                    let want = num + off;
                    if intid != want {
                        let mut p = rec.path.clone();
                        p.push(PathElem::from("irq"));
                        p.push(PathElem::from("intid"));
                        checker.add_file(
                            file_idx,
                            &p,
                            format!(
                                "{what}: intid {intid} does not agree with {kind} {num} (INTID {want})"
                            ),
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }
            }
        }
    }

    let data = checker.files[file_idx].data.clone();
    for &group in REGISTRIES {
        if let Some(arr) = data.get(group).and_then(Value::as_array) {
            for (i, entry) in arr.iter().enumerate() {
                let path = vec![PathElem::from(group), PathElem::Index(i)];
                let ename = entry.get("name").and_then(Value::as_str).unwrap_or("");
                let what = format!("{} '{ename}'", registry_entry_label(group));
                for (sup, mut at) in supports(entry, &path) {
                    if let Some(cls) = sup.get("class").and_then(Value::as_str) {
                        if cls == "inference" || cls == "emulated" {
                            at.push(PathElem::from("class"));
                            checker.reject(
                                file_idx,
                                &at,
                                format!(
                                    "{what}: {cls} support names facts, which a registry entry cannot; cite the source"
                                ),
                                true,
                            );
                        }
                    }
                }
                check_support_full(checker, file_idx, &what, entry, &path, &mut cited);
            }
        }
    }

    crate::peripheral::check_registries(checker, file_idx, &mut cited);
    crate::peripheral::check_file(checker, file_idx);
    check_review_file(checker, file_idx);

    if let Some(notices) = data.get("notices").and_then(Value::as_array) {
        for (i, notice) in notices.iter().enumerate() {
            if let Some(rname) = notice.get("repo").and_then(Value::as_str) {
                cited.insert(rname.to_string());
                gate_name(
                    checker,
                    file_idx,
                    &[
                        PathElem::from("notices"),
                        PathElem::Index(i),
                        PathElem::from("repo"),
                    ],
                    rname,
                    "a notice",
                    false,
                );
            }
        }
    }

    let repo_entries: Vec<(String, Value, Vec<PathElem>)> = checker.files[file_idx]
        .repos
        .iter()
        .map(|(k, (v, p))| (k.clone(), v.clone(), p.clone()))
        .collect();
    let root_idx = checker.files[file_idx].root_idx;
    let req_lic = checker.require_license;
    for (name, entry, mut path) in repo_entries {
        let lic = entry.get("license").and_then(Value::as_str).unwrap_or("");
        path.push(PathElem::from("license"));
        if let Err(SpdxError(msg)) = spdx::parse(lic) {
            checker.add_file(
                file_idx,
                &path,
                format!("repos entry '{name}': license: {msg}"),
                "error",
                false,
                true,
                true,
            );
            continue;
        }
        if req_lic && !cited.contains(&name) {
            if let Some(reason) = gate_expr(checker, root_idx, lic) {
                checker.add_file(
                    file_idx,
                    &path,
                    format!(
                        "repos entry '{name}': {reason} (--require-license gates every repos entry, cited or not)"
                    ),
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }
    }

    if let Some(series_arr) = data
        .get("resources")
        .and_then(|r| r.get("series"))
        .and_then(Value::as_array)
    {
        for (i, s) in series_arr.iter().enumerate() {
            if let Some(target) = s.get("target").and_then(Value::as_str) {
                if !checker.files[file_idx].repos.contains_key(target) {
                    checker.add_file(
                        file_idx,
                        &[
                            PathElem::from("resources"),
                            PathElem::from("series"),
                            PathElem::Index(i),
                            PathElem::from("target"),
                        ],
                        format!("series target '{target}' names no repos entry of this file"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }
    }

    // BF-IMX-14: PDF documents of class `datasheet`, `errata`, or `appnote` require `pages`.
    if let Some(docs_arr) = data
        .get("resources")
        .and_then(|r| r.get("documents"))
        .and_then(Value::as_array)
    {
        for (i, doc) in docs_arr.iter().enumerate() {
            let doc_cls = doc.get("class").and_then(Value::as_str).unwrap_or("");
            if matches!(doc_cls, "datasheet" | "errata" | "appnote") {
                let url = doc.get("url").and_then(Value::as_str).unwrap_or("");
                let url_path = url.split(['?', '#']).next().unwrap_or(url);
                let is_pdf = url_path.to_ascii_lowercase().ends_with(".pdf");
                let cite_false = doc.get("cite").and_then(Value::as_bool) == Some(false);
                if is_pdf && !cite_false && doc.get("pages").is_none() {
                    let name = doc.get("name").and_then(Value::as_str).unwrap_or("");
                    checker.add_file(
                        file_idx,
                        &[
                            PathElem::from("resources"),
                            PathElem::from("documents"),
                            PathElem::Index(i),
                        ],
                        format!(
                            "documents entry '{name}': class {doc_cls} PDF document requires pages"
                        ),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }
    }

    if checker.roots[root_idx].layer.as_deref() == Some("public") {
        if let Some(resources) = data.get("resources").and_then(Value::as_object) {
            for (group, entries_val) in resources {
                if let Some(entries) = entries_val.as_array() {
                    for (i, entry) in entries.iter().enumerate() {
                        let label = entry
                            .get("name")
                            .or_else(|| entry.get("title"))
                            .and_then(Value::as_str)
                            .unwrap_or("");
                        let access = entry.get("access").and_then(Value::as_str);
                        if access == Some("private") {
                            checker.add_file(
                                file_idx,
                                &[
                                    PathElem::from("resources"),
                                    PathElem::from(group.as_str()),
                                    PathElem::Index(i),
                                    PathElem::from("access"),
                                ],
                                format!(
                                    "{group} entry '{label}': access: private under a public root"
                                ),
                                "error",
                                false,
                                true,
                                true,
                            );
                        } else if access == Some("members-only")
                            && entry.get("cite").and_then(Value::as_bool) != Some(false)
                        {
                            checker.add_file(
                                file_idx,
                                &[
                                    PathElem::from("resources"),
                                    PathElem::from(group.as_str()),
                                    PathElem::Index(i),
                                    PathElem::from("access"),
                                ],
                                format!(
                                    "{group} entry '{label}': a members-only document under a public root is a map only: mark it cite: false, or move the spec to a root whose readers have access"
                                ),
                                "error",
                                false,
                                true,
                                true,
                            );
                        }
                        if group == "tools" {
                            if let Some(via) = entry.get("via").and_then(Value::as_str) {
                                let skill = via.strip_prefix("skill:").unwrap_or(via);
                                if !checker.public_skills.contains(skill) {
                                    checker.add_file(
                                        file_idx,
                                        &[
                                            PathElem::from("resources"),
                                            PathElem::from("tools"),
                                            PathElem::Index(i),
                                            PathElem::from("via"),
                                        ],
                                        format!(
                                            "tools entry '{label}': via '{via}' is not a public skill (pass --public-skill NAME if it is)"
                                        ),
                                        "error",
                                        false,
                                        true,
                                        true,
                                    );
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    check_placeholders_file(checker, file_idx);
}

// ---------------------------------------------------------------------------
// Composition checking (`speccheck.py:check_composition`, `BF-GW-25`, `BF-GW-27`)
// ---------------------------------------------------------------------------

/// Runs composition checks across all loaded files (`speccheck.py:check_composition`).
pub fn check_composition_full(checker: &mut Checker) {
    checker.check_composition();

    let mut base: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    for (f_idx, f) in checker.files.iter().enumerate() {
        if !f.is_overlay() {
            base.entry(f.spec_id()).or_default().push(f_idx);
        }
    }

    let mut names: BTreeMap<String, Vec<(usize, usize)>> = BTreeMap::new();
    for (f_idx, f) in checker.files.iter().enumerate() {
        if let Some(aliases) = f.data.get("aliases").and_then(Value::as_array) {
            for (i, alias) in aliases.iter().enumerate() {
                if let Some(a) = alias.as_str() {
                    names.entry(a.to_string()).or_default().push((f_idx, i));
                }
            }
        }
    }

    for (alias, uses) in &names {
        if let Some(base_owners) = base.get(alias) {
            for &(f_idx, i) in uses {
                checker.add_file(
                    f_idx,
                    &[PathElem::from("aliases"), PathElem::Index(i)],
                    format!("alias '{alias}' is the id of another spec"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
            for &g_idx in base_owners {
                let others: Vec<String> = uses
                    .iter()
                    .map(|&(f_idx, _)| {
                        rel_spec_file(
                            &checker.roots[checker.files[f_idx].root_idx],
                            &checker.files[f_idx],
                        )
                    })
                    .collect();
                checker.add_file(
                    g_idx,
                    &[PathElem::from("id")],
                    format!(
                        "spec id '{alias}' is also an alias in {}",
                        others.join(", ")
                    ),
                    "error",
                    false,
                    true,
                    true,
                );
            }
        } else if uses.len() > 1 {
            for &(f_idx, i) in uses {
                checker.add_file(
                    f_idx,
                    &[PathElem::from("aliases"), PathElem::Index(i)],
                    format!("alias '{alias}' is also an alias of another spec"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }
    }

    let mut parts_graph: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for f_idx in 0..checker.files.len() {
        if checker.files[f_idx].is_overlay() {
            check_overlay(checker, f_idx, &base);
            continue;
        }
        let is_ctx = checker.roots[checker.files[f_idx].root_idx].context;
        let mut parts_reports = Vec::new();
        if let Some(parts) = checker.files[f_idx]
            .data
            .get("parts")
            .and_then(Value::as_array)
        {
            for (i, part) in parts.iter().enumerate() {
                if let Some(p) = part.as_str() {
                    parts_graph
                        .entry(checker.files[f_idx].spec_id())
                        .or_default()
                        .push(p.to_string());
                    if !base.contains_key(p) {
                        parts_reports.push((
                            i,
                            format!("parts entry '{p}' resolves to no spec"),
                            "error",
                            !is_ctx,
                        ));
                        continue;
                    }
                    let other_cache = checker.files[base[p][0]]
                        .data
                        .get("cache")
                        .and_then(Value::as_str)
                        .map(ToString::to_string);
                    let f_cache = checker.files[f_idx]
                        .data
                        .get("cache")
                        .and_then(Value::as_str)
                        .map(ToString::to_string);
                    if let (Some(oc), Some(fc)) = (other_cache, f_cache) {
                        if oc != fc {
                            parts_reports.push((
                                i,
                                format!("part '{p}' names cache '{oc}', this spec '{fc}'"),
                                "warning",
                                true,
                            ));
                        }
                    }
                }
            }
        }
        for (i, msg, lvl, trust) in parts_reports {
            checker.add_file(
                f_idx,
                &[PathElem::from("parts"), PathElem::Index(i)],
                msg,
                lvl,
                false,
                true,
                trust,
            );
        }

        let mut var_report = None;
        if let Some(target) = checker.files[f_idx]
            .data
            .get("variant_of")
            .and_then(Value::as_str)
            .map(ToString::to_string)
        {
            let spec_id = checker.files[f_idx].spec_id();
            if target == spec_id {
                var_report = Some(("variant_of names the spec itself".to_string(), true));
            } else if !base.contains_key(&target) {
                var_report = Some((
                    format!("variant_of '{target}' resolves to no spec"),
                    !is_ctx,
                ));
            } else {
                let kind = checker.files[base[&target][0]].kind().to_string();
                if kind != "board" {
                    var_report = Some((
                        format!("variant_of '{target}' is not a board spec (kind {kind})"),
                        true,
                    ));
                }
            }
        }
        if let Some((msg, trust)) = var_report {
            checker.add_file(
                f_idx,
                &[PathElem::from("variant_of")],
                msg,
                "error",
                false,
                true,
                trust,
            );
        }

        check_instances(checker, f_idx, &base);
        check_describes(checker, f_idx, &base);
    }

    check_parts_cycles(checker, &parts_graph, &base);
    check_unattached_peripherals(checker);

    let mut overlays: BTreeMap<(String, usize), Vec<usize>> = BTreeMap::new();
    for (f_idx, f) in checker.files.iter().enumerate() {
        if f.is_overlay() {
            overlays
                .entry((f.spec_id(), f.root_idx))
                .or_default()
                .push(f_idx);
        }
    }
    for ((target, r_idx), owners) in &overlays {
        if owners.len() > 1 {
            let root_label = checker.roots[*r_idx].label();
            for &f_idx in owners {
                checker.add_file(
                    f_idx,
                    &[PathElem::from("overlays")],
                    format!(
                        "{} overlays of '{target}' in root {root_label}; their merge order is undefined",
                        owners.len()
                    ),
                    "warning",
                    false,
                    true,
                    true,
                );
            }
        }
    }
}

/// Checks `instances` entries (`speccheck.py:check_instances`, `BF-GW-27`).
pub fn check_instances(checker: &mut Checker, f_idx: usize, base: &BTreeMap<String, Vec<usize>>) {
    let is_ctx = checker.roots[checker.files[f_idx].root_idx].context;
    let mut reports = Vec::new();
    if let Some(instances) = checker.files[f_idx]
        .data
        .get("instances")
        .and_then(Value::as_array)
    {
        for (i, row) in instances.iter().enumerate() {
            let name = row
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            for (key, kind) in [("ip", "ip"), ("peripheral", "peripheral")] {
                if let Some(target) = row.get(key).and_then(Value::as_str) {
                    if !base.contains_key(target) {
                        reports.push((
                            i,
                            key.to_string(),
                            format!("instance '{name}': {key} '{target}' resolves to no spec"),
                            !is_ctx,
                        ));
                    } else {
                        let target_idx = base[target][0];
                        let target_kind = checker.files[target_idx].kind().to_string();
                        if target_kind != kind {
                            let art = if kind == "ip" { "an" } else { "a" };
                            reports.push((
                                i,
                                key.to_string(),
                                format!(
                                    "instance '{name}': '{target}' is not {art} {kind} spec (kind {target_kind})"
                                ),
                                true,
                            ));
                        }
                    }
                }
            }
        }
    }
    for (i, key, msg, trust) in reports {
        checker.add_file(
            f_idx,
            &[
                PathElem::from("instances"),
                PathElem::Index(i),
                PathElem::from(key.as_str()),
            ],
            msg,
            "error",
            false,
            true,
            trust,
        );
    }
}

/// Checks `describes` entries on peripheral specs (`speccheck.py:check_describes`).
pub fn check_describes(checker: &mut Checker, f_idx: usize, base: &BTreeMap<String, Vec<usize>>) {
    let is_ctx = checker.roots[checker.files[f_idx].root_idx].context;
    let f_root_idx = checker.files[f_idx].root_idx;
    let f_rank = checker.roots[f_root_idx].rank;
    let f_layer = checker.roots[f_root_idx]
        .layer
        .clone()
        .unwrap_or_else(|| "public".to_string());
    let mut reports = Vec::new();
    if let Some(describes) = checker.files[f_idx]
        .data
        .get("describes")
        .and_then(Value::as_array)
    {
        for (i, item) in describes.iter().enumerate() {
            let Some(target) = item.as_str() else {
                continue;
            };
            if !base.contains_key(target) {
                reports.push((
                    i,
                    format!("describes entry '{target}' resolves to no spec"),
                    !is_ctx,
                ));
                continue;
            }
            let tf_idx = base[target][0];
            let tf_kind = checker.files[tf_idx].kind().to_string();
            let tf_root_idx = checker.files[tf_idx].root_idx;
            let tf_rank = checker.roots[tf_root_idx].rank;
            let tf_layer = checker.roots[tf_root_idx]
                .layer
                .clone()
                .unwrap_or_else(|| "public".to_string());
            if !matches!(tf_kind.as_str(), "soc" | "chip" | "board") {
                reports.push((
                    i,
                    format!(
                        "describes entry '{target}' is not a soc, chip or board spec (kind {tf_kind})"
                    ),
                    true,
                ));
            } else if tf_rank > f_rank {
                reports.push((
                    i,
                    format!(
                        "describes entry '{target}' is in layer {tf_layer}, after this root's layer {f_layer}; name it from that layer's instances[].peripheral instead"
                    ),
                    true,
                ));
            }
        }
    }
    for (i, msg, trust) in reports {
        checker.add_file(
            f_idx,
            &[PathElem::from("describes"), PathElem::Index(i)],
            msg,
            "error",
            false,
            true,
            trust,
        );
    }
}

/// Checks `kind: overlay` files (`speccheck.py:check_overlay`).
pub fn check_overlay(checker: &mut Checker, f_idx: usize, base: &BTreeMap<String, Vec<usize>>) {
    let is_ctx = checker.roots[checker.files[f_idx].root_idx].context;
    let target = checker.files[f_idx].spec_id();
    if !base.contains_key(&target) {
        checker.add_file(
            f_idx,
            &[PathElem::from("overlays")],
            format!("overlays '{target}' resolves to no spec"),
            "error",
            false,
            true,
            !is_ctx,
        );
        return;
    }
    let tf_idx = base[&target][0];
    let tf_root_idx = checker.files[tf_idx].root_idx;
    let f_root_idx = checker.files[f_idx].root_idx;
    let tf_rank = checker.roots[tf_root_idx].rank;
    let f_rank = checker.roots[f_root_idx].rank;
    let tf_layer = checker.roots[tf_root_idx]
        .layer
        .clone()
        .unwrap_or_else(|| "public".to_string());
    let f_layer = checker.roots[f_root_idx]
        .layer
        .clone()
        .unwrap_or_else(|| "public".to_string());
    if tf_rank > f_rank {
        checker.add_file(
            f_idx,
            &[PathElem::from("overlays")],
            format!(
                "overlays '{target}', which is in layer {tf_layer}, after this root's layer {f_layer}; an overlay merges after its target"
            ),
            "error",
            false,
            true,
            true,
        );
    }

    let tf_kind = checker.files[tf_idx].kind().to_string();
    let allowed = allowed_sections(&tf_kind);
    let mut fact_reports = Vec::new();
    if let Some(facts) = checker.files[f_idx]
        .data
        .get("facts")
        .and_then(Value::as_array)
    {
        for (i, fact) in facts.iter().enumerate() {
            if let Some(sec) = fact.get("section").and_then(Value::as_str) {
                if !allowed.contains(&sec) {
                    fact_reports.push((
                        vec![
                            PathElem::from("facts"),
                            PathElem::Index(i),
                            PathElem::from("section"),
                        ],
                        format!(
                            "section '{sec}' is not a section of the target, kind {tf_kind} ({})",
                            allowed.join(", ")
                        ),
                    ));
                }
            }
            if tf_kind == "review" {
                if let Some(payload) = fact.get("data").and_then(Value::as_object) {
                    if ["register", "sequence", "layout"]
                        .iter()
                        .any(|k| payload.contains_key(*k))
                    {
                        fact_reports.push((
                            vec![
                                PathElem::from("facts"),
                                PathElem::Index(i),
                                PathElem::from("data"),
                            ],
                            "review overlay refuses register, sequence and layout payloads"
                                .to_string(),
                        ));
                    }
                }
            } else if matches!(tf_kind.as_str(), "ip" | "protocol") {
                if let Some(payload) = fact.get("data").and_then(Value::as_object) {
                    if ["register", "sequence"]
                        .iter()
                        .any(|k| payload.contains_key(*k))
                    {
                        fact_reports.push((
                            vec![
                                PathElem::from("facts"),
                                PathElem::Index(i),
                                PathElem::from("data"),
                            ],
                            format!("{tf_kind} overlay refuses register and sequence payloads"),
                        ));
                    }
                }
            }
        }
    }
    for (p, msg) in fact_reports {
        checker.add_file(f_idx, &p, msg, "error", false, true, true);
    }

    if checker.files[f_idx].data.get("instances").is_some()
        && !matches!(tf_kind.as_str(), "soc" | "chip")
    {
        checker.add_file(
            f_idx,
            &[PathElem::from("instances")],
            format!(
                "instances: the target '{target}' is of kind {tf_kind}, which has no instances"
            ),
            "error",
            false,
            true,
            true,
        );
    }
    check_instances(checker, f_idx, base);
}

/// Checks for cycles in `parts:` (`speccheck.py:check_parts_cycles`).
pub fn check_parts_cycles(
    checker: &mut Checker,
    graph: &BTreeMap<String, Vec<String>>,
    base: &BTreeMap<String, Vec<usize>>,
) {
    let mut reported: HashSet<Vec<String>> = HashSet::new();
    let mut reports = Vec::new();

    for start in graph.keys() {
        let mut stack = vec![(start.clone(), vec![start.clone()])];
        while let Some((node, trail)) = stack.pop() {
            let Some(neighbors) = graph.get(&node) else {
                continue;
            };
            for nxt in neighbors {
                if let Some(pos) = trail.iter().position(|x| x == nxt) {
                    let cycle = trail[pos..].to_vec();
                    let min_idx = cycle
                        .iter()
                        .enumerate()
                        .min_by_key(|(_, v)| *v)
                        .map(|(i, _)| i)
                        .unwrap_or(0);
                    let mut key = cycle[min_idx..].to_vec();
                    key.extend_from_slice(&cycle[..min_idx]);
                    if !reported.insert(key) {
                        continue;
                    }
                    let mut shown_parts = cycle.clone();
                    shown_parts.push(cycle[0].clone());
                    let shown = shown_parts.join(" -> ");
                    for i in 0..cycle.len() {
                        let cur = &cycle[i];
                        let next_node = &cycle[(i + 1) % cycle.len()];
                        if let Some(owners) = base.get(cur) {
                            for &f_idx in owners {
                                let idx_opt = checker.files[f_idx]
                                    .data
                                    .get("parts")
                                    .and_then(Value::as_array)
                                    .and_then(|arr| {
                                        arr.iter().position(|v| v.as_str() == Some(next_node))
                                    });
                                if let Some(idx) = idx_opt {
                                    reports.push((
                                        f_idx,
                                        vec![PathElem::from("parts"), PathElem::Index(idx)],
                                        format!("parts form a cycle: {shown}"),
                                    ));
                                }
                            }
                        }
                    }
                } else if trail.len() <= graph.len() {
                    let mut next_trail = trail.clone();
                    next_trail.push(nxt.clone());
                    stack.push((nxt.clone(), next_trail));
                }
            }
        }
    }

    for (f_idx, path, msg) in reports {
        checker.add_file(f_idx, &path, msg, "error", false, true, true);
    }
}

/// Warns when a peripheral spec is not linked to any `soc`, `chip`, or `board` spec
/// (`speccheck.py:check_unattached_peripherals`, `BF-GW-25`).
pub fn check_unattached_peripherals(checker: &mut Checker) {
    let has_parent = checker
        .files
        .iter()
        .any(|f| !f.is_overlay() && matches!(f.kind(), "soc" | "chip" | "board"));
    if !has_parent {
        return;
    }

    let mut named: HashSet<String> = HashSet::new();
    for f in &checker.files {
        if let Some(instances) = f.data.get("instances").and_then(Value::as_array) {
            for row in instances {
                if let Some(p) = row.get("peripheral").and_then(Value::as_str) {
                    named.insert(p.to_string());
                }
            }
        }
        // BF-GW-25: Include spec IDs referenced in `parts:` of `board`, `soc`, and `chip` specs.
        if !f.is_overlay() && matches!(f.kind(), "board" | "soc" | "chip") {
            if let Some(parts) = f.data.get("parts").and_then(Value::as_array) {
                for part in parts {
                    if let Some(p) = part.as_str() {
                        named.insert(p.to_string());
                    }
                }
            }
        }
    }

    let mut to_warn = Vec::new();
    for (f_idx, f) in checker.files.iter().enumerate() {
        if f.kind() == "peripheral"
            && !f.is_overlay()
            && f.data.get("describes").is_none()
            && !named.contains(&f.spec_id())
        {
            to_warn.push((
                f_idx,
                format!(
                    "peripheral spec '{}' is linked to no soc, chip or board spec: name one in describes, or name this spec in that spec's instances[].peripheral",
                    f.spec_id()
                ),
            ));
        }
    }
    for (f_idx, msg) in to_warn {
        checker.add_file(
            f_idx,
            &[PathElem::from("id")],
            msg,
            "warning",
            false,
            true,
            true,
        );
    }
}

// ---------------------------------------------------------------------------
// Document index checking (`index.py:check`, `speccheck.py:check_indexes`)
// ---------------------------------------------------------------------------

fn check_indexes_full(
    checker: &mut Checker,
    loaded_indexes: &HashMap<usize, Vec<(PathBuf, Loaded)>>,
) {
    let num_roots = checker.roots.len();
    for root_idx in 0..num_roots {
        let Some(entries) = loaded_indexes.get(&root_idx) else {
            continue;
        };
        let mut docs: HashMap<String, Value> = HashMap::new();
        let file_indices = checker.roots[root_idx].files.clone();
        for f_idx in file_indices {
            for (name, (doc, _)) in &checker.files[f_idx].documents {
                docs.entry(name.clone()).or_insert_with(|| doc.clone());
            }
        }
        let root_label = checker.roots[root_idx].label();

        for (path, loaded) in entries {
            let Some(data) = loaded.data.clone() else {
                continue;
            };
            textcheck_backticks_where(checker, path, Some(root_idx), Some(loaded), &data, false);
            let fname = path
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();
            let stem = fname.strip_suffix(".index.yaml").unwrap_or(&fname);
            let doc_name = data.get("document").and_then(Value::as_str).unwrap_or("");
            if doc_name != stem {
                checker.add_where(
                    path,
                    Some(root_idx),
                    Some(loaded),
                    &[PathElem::from("document")],
                    format!(
                        "document '{doc_name}' does not match index file name '{fname}' (expected '{stem}')"
                    ),
                    "error",
                    false,
                    true,
                    false,
                );
            }
            let Some(doc) = docs.get(doc_name) else {
                checker.add_where(
                    path,
                    Some(root_idx),
                    Some(loaded),
                    &[PathElem::from("document")],
                    format!(
                        "document '{doc_name}' is not in any spec file's resources.documents in root {root_label}"
                    ),
                    "error",
                    false,
                    true,
                    false,
                );
                continue;
            };
            if let Some(doc_sha) = doc.get("sha256").and_then(Value::as_str) {
                let idx_sha = data.get("sha256").and_then(Value::as_str).unwrap_or("");
                if idx_sha != doc_sha {
                    checker.add_where(
                        path,
                        Some(root_idx),
                        Some(loaded),
                        &[PathElem::from("sha256")],
                        format!(
                            "index sha256 does not match resources.documents entry '{doc_name}' (index is stale; re-run `spec.py index`)"
                        ),
                        "error",
                        false,
                        true,
                        false,
                    );
                }
            } else {
                checker.add_where(
                    path,
                    Some(root_idx),
                    Some(loaded),
                    &[PathElem::from("sha256")],
                    format!(
                        "resources.documents entry '{doc_name}' has no sha256; pin the document's sha256 so the index can be checked for staleness"
                    ),
                    "warning",
                    false,
                    true,
                    false,
                );
            }
            if let (Some(doc_pages), Some(idx_pages)) = (
                doc.get("pages").and_then(Value::as_i64),
                data.get("pages").and_then(Value::as_i64),
            ) {
                if idx_pages != doc_pages {
                    checker.add_where(
                        path,
                        Some(root_idx),
                        Some(loaded),
                        &[PathElem::from("pages")],
                        format!(
                            "index pages ({idx_pages}) does not match resources.documents entry '{doc_name}' ({doc_pages})"
                        ),
                        "error",
                        false,
                        true,
                        false,
                    );
                }
            }
            let pages_opt = data.get("pages").and_then(Value::as_i64);
            if let Some(outline) = data.get("outline").and_then(Value::as_array) {
                for (i, entry) in outline.iter().enumerate() {
                    if let (Some(start), Some(end)) = (
                        entry.get("start_page").and_then(Value::as_i64),
                        entry.get("end_page").and_then(Value::as_i64),
                    ) {
                        if start > end {
                            checker.add_where(
                                path,
                                Some(root_idx),
                                Some(loaded),
                                &[
                                    PathElem::from("outline"),
                                    PathElem::Index(i),
                                    PathElem::from("end_page"),
                                ],
                                format!("end_page {end} is before start_page {start}"),
                                "error",
                                false,
                                true,
                                false,
                            );
                        }
                        if let Some(pages) = pages_opt {
                            if end > pages {
                                checker.add_where(
                                    path,
                                    Some(root_idx),
                                    Some(loaded),
                                    &[
                                        PathElem::from("outline"),
                                        PathElem::Index(i),
                                        PathElem::from("end_page"),
                                    ],
                                    format!("end_page {end} exceeds the document's {pages} pages"),
                                    "error",
                                    false,
                                    true,
                                    false,
                                );
                            }
                        }
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Stubs & agent name checking (`speccheck.py:check_stubs`, `check_overlap`, `BF-IMX-ISS-4`)
// ---------------------------------------------------------------------------

/// Checks expert stubs and `--stubs-from` directories (`speccheck.py:check_stubs`).
pub fn check_stubs(
    checker: &mut Checker,
    mut stubs: Vec<PathBuf>,
    stubs_from: &[PathBuf],
) -> Result<(), String> {
    for d in stubs_from {
        if !d.is_dir() {
            return Err(format!("--stubs-from {}: not a directory", d.display()));
        }
        if let Ok(entries) = std::fs::read_dir(d) {
            let mut paths: Vec<_> = entries
                .filter_map(Result::ok)
                .map(|e| e.path().join("SKILL.md"))
                .filter(|p| p.exists())
                .collect();
            paths.sort();
            for path in paths {
                if let Ok(text) = std::fs::read_to_string(&path) {
                    if let Some(caps) = FRONTMATTER_RE.captures(&text) {
                        if caps.get(1).map_or("", |m| m.as_str()).contains("stub over") {
                            stubs.push(path);
                        }
                    }
                }
            }
        }
    }

    let ids: HashSet<String> = checker
        .files
        .iter()
        .filter(|f| !f.is_overlay())
        .map(SpecFile::spec_id)
        .collect();
    let mut unique_stubs = BTreeMap::new();
    for path in stubs {
        let resolved = if path.exists() {
            path.canonicalize().unwrap_or_else(|_| path.clone())
        } else {
            path.clone()
        };
        unique_stubs.entry(resolved).or_insert(path);
    }
    let stubs_list: Vec<PathBuf> = unique_stubs.into_values().collect();
    checker.stubs = stubs_list.len();

    let mut names: BTreeMap<String, PathBuf> = BTreeMap::new();
    let mut claims: BTreeMap<String, Vec<(String, PathBuf, Vec<HashSet<String>>)>> =
        BTreeMap::new();

    for path in &stubs_list {
        if !path.is_file() {
            checker.findings.push(SpecFinding {
                path: path.display().to_string(),
                line: 1,
                column: 1,
                level: "error".to_string(),
                message: "stub file not found".to_string(),
            });
            continue;
        }
        let text = std::fs::read_to_string(path).unwrap_or_default();
        let path_str = path.display().to_string();

        let at = |index: usize, message: String, checker: &mut Checker| {
            let prefix = &text[..index.min(text.len())];
            let line = prefix.chars().filter(|&c| c == '\n').count() + 1;
            let last_newline = prefix.rfind('\n').map_or(0, |i| i + 1);
            let column = prefix[last_newline..].chars().count() + 1;
            checker.findings.push(SpecFinding {
                path: path_str.clone(),
                line,
                column,
                level: "error".to_string(),
                message,
            });
        };

        if let Some((line, column, found)) =
            crate::specmd::placeholders(&text, false).into_iter().next()
        {
            checker.findings.push(SpecFinding {
                path: path_str.clone(),
                line,
                column,
                level: "error".to_string(),
                message: format!("unsubstituted template placeholder '{found}'"),
            });
        }

        let specs: Vec<_> = STUB_SPEC_RE.captures_iter(&text).collect();
        if specs.is_empty() {
            at(0, "stub names no `spec: <id>`".to_string(), checker);
        }
        for m in &specs {
            let spec_id = m.get(1).map_or("", |c| c.as_str());
            if !ids.contains(spec_id) {
                at(
                    m.get(0).unwrap().start(),
                    format!("stub spec id '{spec_id}' resolves to no spec"),
                    checker,
                );
            }
        }
        for m in STUB_INSTANCE_RE.captures_iter(&text) {
            let spec_id = m.get(1).map_or("", |c| c.as_str());
            let inst_id = m.get(2).map_or("", |c| c.as_str());
            let mut found_row = false;
            for f in &checker.files {
                if f.spec_id() == spec_id {
                    if let Some(&r_idx) = f.record_map.get(inst_id) {
                        let rec = &f.records[r_idx].1;
                        if rec.path.first() == Some(&PathElem::from("instances")) {
                            found_row = true;
                            break;
                        }
                    }
                }
            }
            if !found_row {
                at(
                    m.get(0).unwrap().start(),
                    format!("stub instance {spec_id}#{inst_id} resolves to no instance row"),
                    checker,
                );
            }
        }
        for prose in crate::prosefacts::scan_text(&text) {
            checker.findings.push(SpecFinding {
                path: path_str.clone(),
                line: prose.line,
                column: prose.column,
                level: "error".to_string(),
                message: crate::prosefacts::format_message(&prose.what),
            });
        }

        let name = if let Some(front) = FRONTMATTER_RE.captures(&text) {
            if let Some(n) = STUB_NAME_RE.captures(front.get(1).map_or("", |m| m.as_str())) {
                n.get(1).map_or("", |m| m.as_str()).to_string()
            } else {
                path.parent()
                    .and_then(|p| p.file_name())
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string()
            }
        } else {
            path.parent()
                .and_then(|p| p.file_name())
                .unwrap_or_default()
                .to_string_lossy()
                .to_string()
        };

        if let Some(existing) = names.get(&name) {
            at(
                0,
                format!(
                    "stub name '{name}' is also the name of {}: installed agents and skills need distinct names",
                    existing.display()
                ),
                checker,
            );
        } else {
            names.insert(name.clone(), path.clone());
        }

        let mut splits = Vec::new();
        for m in STUB_SPLIT_RE.captures_iter(&text) {
            let mut split_set = HashSet::new();
            for word in WORD_RE.find_iter(m.get(1).map_or("", |c| c.as_str())) {
                split_set.insert(word.as_str().to_string());
            }
            splits.push(split_set);
        }
        let mut spec_ids = Vec::new();
        let mut seen_sids = HashSet::new();
        for m in &specs {
            let sid = m.get(1).map_or("", |c| c.as_str()).to_string();
            if seen_sids.insert(sid.clone()) {
                spec_ids.push(sid);
            }
        }
        for spec_id in spec_ids {
            claims
                .entry(spec_id)
                .or_default()
                .push((name.clone(), path.clone(), splits.clone()));
        }
    }

    check_overlap(checker, &claims);
    check_agent_names(checker, stubs_from);
    Ok(())
}

/// Checks agent name uniqueness in sibling `agents/` directories (`speccheck.py:check_agent_names`).
pub fn check_agent_names(checker: &mut Checker, stubs_from: &[PathBuf]) {
    let mut seen: BTreeMap<String, PathBuf> = BTreeMap::new();
    let mut dirs = Vec::new();
    let mut seen_dirs = HashSet::new();
    for d in stubs_from {
        let agent_dir = d
            .parent()
            .unwrap_or_else(|| Path::new(""))
            .join("agents");
        if agent_dir.is_dir() {
            let canon = agent_dir
                .canonicalize()
                .unwrap_or_else(|_| agent_dir.clone());
            if seen_dirs.insert(canon) {
                dirs.push(agent_dir);
            }
        }
    }
    for folder in dirs {
        if let Ok(entries) = std::fs::read_dir(folder) {
            let mut paths: Vec<_> = entries
                .filter_map(Result::ok)
                .map(|e| e.path())
                .filter(|p| p.extension().is_some_and(|e| e == "md"))
                .collect();
            paths.sort();
            for path in paths {
                if let Ok(text) = std::fs::read_to_string(&path) {
                    if let Some(front) = FRONTMATTER_RE.captures(&text) {
                        if let Some(found) =
                            STUB_NAME_RE.captures(front.get(1).map_or("", |m| m.as_str()))
                        {
                            let name = found.get(1).map_or("", |m| m.as_str()).to_string();
                            if let Some(existing_path) = seen.get(&name) {
                                checker.findings.push(SpecFinding {
                                    path: path.display().to_string(),
                                    line: 1,
                                    column: 1,
                                    level: "error".to_string(),
                                    message: format!(
                                        "agent name '{name}' is also the name of {}: installed agents need distinct names",
                                        existing_path.display()
                                    ),
                                });
                            } else {
                                seen.insert(name, path.clone());
                            }
                        }
                    }
                }
            }
        }
    }
}

/// Warns when two stubs enter through the same spec without a stated split
/// (`speccheck.py:check_overlap`, `BF-IMX-ISS-4`).
pub fn check_overlap(
    checker: &mut Checker,
    claims: &BTreeMap<String, Vec<(String, PathBuf, Vec<HashSet<String>>)>>,
) {
    for (spec_id, owners) in claims {
        let primary_hub = format!("{spec_id}-expert");
        for (i, (a, apath, asplit)) in owners.iter().enumerate() {
            for (b, bpath, bsplit) in owners.iter().skip(i + 1) {
                if a == b
                    || asplit.iter().any(|s| s.contains(b))
                    || bsplit.iter().any(|s| s.contains(a))
                {
                    continue;
                }
                // BF-IMX-ISS-4: Accept 3+ domain stubs sharing an entry spec when both name the
                // primary board/SoC expert (`<spec_id>-expert` or a shared `*-expert` hub) in
                // their `split:` clauses without requiring manual O(N^2) cross-listing.
                let a_names_primary = asplit.iter().any(|s| s.contains(&primary_hub));
                let b_names_primary = bsplit.iter().any(|s| s.contains(&primary_hub));
                let shares_expert_hub = (a_names_primary && b_names_primary)
                    || (owners.len() >= 3
                        && asplit.iter().any(|sa| {
                            bsplit.iter().any(|sb| {
                                sa.intersection(sb)
                                    .any(|tok| tok.ends_with("-expert") && tok != a && tok != b)
                            })
                        }));
                if shares_expert_hub {
                    continue;
                }
                checker.findings.push(SpecFinding {
                    path: bpath.display().to_string(),
                    line: 1,
                    column: 1,
                    level: "warning".to_string(),
                    message: format!(
                        "stubs '{a}' ({}) and '{b}' both enter through spec '{spec_id}' with no stated split: add a `split: ...` line to one naming the other and saying which questions go where",
                        apath.display()
                    ),
                });
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Heading resolution (`headingcheck.py`, `explorer.py`, `check --resolve-headings`)
// ---------------------------------------------------------------------------

static GITHUB_BLOB_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^https://github\.com/([\w.-]+)/([\w.-]+)/blob/([0-9a-f]{40})/([\w./-]+)$")
        .expect("valid GITHUB_BLOB_RE")
});

static GITHUB_WIKI_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^https://github\.com/([\w.-]+)/([\w.-]+)/wiki/([\w.-]+)$")
        .expect("valid GITHUB_WIKI_RE")
});

static ANCHOR_ID_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"^[^\x00-\x20\x7f"<>\\`#]{1,200}$"#).expect("valid ANCHOR_ID_RE")
});

static HEADING_WITH_ID_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?is)<h([1-6])([^>]*)>(.*?)</h[1-6]>(?:\s*(<a\b[^>]*>))?"#)
        .expect("valid HEADING_WITH_ID_RE")
});

static ATTR_ID_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?i)\bid\s*=\s*["']([^"']*)["']"#).expect("valid ATTR_ID_RE")
});

static ATTR_CLASS_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?i)\bclass\s*=\s*["']([^"']*)["']"#).expect("valid ATTR_CLASS_RE")
});

static ATTR_HREF_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?i)\bhref\s*=\s*["']([^"']*)["']"#).expect("valid ATTR_HREF_RE")
});

fn has_dot_segments(parts: &[&str]) -> bool {
    parts
        .iter()
        .any(|p| p.split('/').any(|seg| seg == "." || seg == ".."))
}

fn percent_encode_path(path: &str) -> String {
    let mut out = String::new();
    for b in path.as_bytes() {
        if b.is_ascii_alphanumeric() || matches!(*b, b'-' | b'_' | b'.' | b'~' | b'/') {
            out.push(*b as char);
        } else {
            out.push_str(&format!("%{b:02X}"));
        }
    }
    out
}

/// Returns the rendered-HTML request `(url, accept_header)` for a document URL, or `None` when
/// the URL is not a full-commit GitHub blob or wiki page (`explorer.py:fetch_url`).
#[must_use]
pub fn fetch_url(url: &str) -> Option<(String, &'static str)> {
    if let Some(caps) = GITHUB_BLOB_RE.captures(url) {
        let owner = caps.get(1)?.as_str();
        let repo = caps.get(2)?.as_str();
        let commit = caps.get(3)?.as_str();
        let path = caps.get(4)?.as_str();
        if has_dot_segments(&[owner, repo, path]) {
            return None;
        }
        let api = format!(
            "https://api.github.com/repos/{owner}/{repo}/contents/{}?ref={commit}",
            percent_encode_path(path)
        );
        return Some((api, "application/vnd.github.html"));
    }
    if let Some(caps) = GITHUB_WIKI_RE.captures(url) {
        let owner = caps.get(1)?.as_str();
        let repo = caps.get(2)?.as_str();
        let page = caps.get(3)?.as_str();
        if !has_dot_segments(&[owner, repo, page]) {
            return Some((url.to_string(), "text/html"));
        }
    }
    None
}

/// Normalizes heading text into a case-folded lookup key (`explorer.py:heading_key`).
#[must_use]
pub fn heading_key(text: &str) -> String {
    text.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .trim()
        .to_lowercase()
}

fn decode_basic_html_entities(s: &str) -> String {
    s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&#x27;", "'")
}

/// Extracts anchored heading keys (`heading_key(text) -> anchor_id`) from GitHub-rendered HTML
/// (`explorer.py:Headings`).
#[must_use]
pub fn parse_rendered_headings(html: &str) -> HashMap<String, String> {
    let mut found = HashMap::new();
    for caps in HEADING_WITH_ID_RE.captures_iter(html) {
        let h_attrs = caps.get(2).map(|m| m.as_str()).unwrap_or("");
        let h_inner = caps.get(3).map(|m| m.as_str()).unwrap_or("");
        let next_a = caps.get(4).map(|m| m.as_str()).unwrap_or("");

        let stripped = HTML_TAG_RE.replace_all(h_inner, "");
        let text = decode_basic_html_entities(&stripped);
        let key = heading_key(&text);

        let mut anchor_opt: Option<String> = ATTR_ID_RE
            .captures(h_attrs)
            .and_then(|c| c.get(1))
            .map(|m| m.as_str().to_string())
            .filter(|s| !s.is_empty());

        if anchor_opt.is_none() && !next_a.is_empty() {
            let has_anchor_class = ATTR_CLASS_RE
                .captures(next_a)
                .and_then(|c| c.get(1))
                .is_some_and(|m| m.as_str().split_whitespace().any(|w| w == "anchor"));
            if has_anchor_class {
                if let Some(href) = ATTR_HREF_RE.captures(next_a).and_then(|c| c.get(1)) {
                    if let Some(rest) = href.as_str().strip_prefix('#') {
                        if !rest.is_empty() {
                            anchor_opt = Some(rest.to_string());
                        }
                    }
                }
            }
        }

        if let Some(raw_anchor) = anchor_opt {
            let clean = raw_anchor
                .strip_prefix("user-content-")
                .unwrap_or(&raw_anchor)
                .to_string();
            found.entry(key).or_insert(clean);
        }
    }
    let _ = &HTML_HEADING_RE;
    let _ = &MD_HEADING_RE;
    found
}

fn py_quote_str(s: &str) -> String {
    if s.contains('\'') && !s.contains('"') {
        format!("\"{}\"", s.replace('\\', "\\\\").replace('"', "\\\""))
    } else {
        format!("'{}'", s.replace('\\', "\\\\").replace('\'', "\\'"))
    }
}

/// Checks `heading:` locators on cited documents using a custom fetcher (`headingcheck.py:check`).
pub fn check_headings_with_fetcher<F>(
    checker: &mut Checker,
    offline: bool,
    mut fetcher: F,
) -> Result<(), (i32, String)>
where
    F: FnMut(&str, &str) -> Result<String, String>,
{
    if checker.findings.iter().any(|f| f.level == "error") {
        return Ok(());
    }

    // Collect wanted `(url -> BTreeSet<heading>)` over non-context files (`explorer.py:wanted`).
    let mut wanted: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for file in &checker.files {
        if checker.roots[file.root_idx].context {
            continue;
        }
        for (_, rec) in &file.records {
            for (entry, _) in supports(&rec.data, &[]) {
                let Some(doc_name) = entry.get("doc").and_then(Value::as_str) else {
                    continue;
                };
                let Some((doc, _)) = file.documents.get(doc_name) else {
                    continue;
                };
                let Some(url) = doc.get("url").and_then(Value::as_str) else {
                    continue;
                };
                if fetch_url(url).is_none() {
                    continue;
                }
                if let Some(at_arr) = entry.get("at").and_then(Value::as_array) {
                    for loc in at_arr {
                        if let Some(h) = loc.get("heading").and_then(Value::as_str) {
                            wanted
                                .entry(url.to_string())
                                .or_default()
                                .insert(h.to_string());
                        }
                    }
                }
            }
        }
    }

    const MAX_FETCHES: usize = 500;
    let mut unresolved: HashMap<(String, String), String> = HashMap::new();
    for (count, (url, headings)) in wanted.into_iter().enumerate() {
        if count >= MAX_FETCHES {
            for h in headings {
                unresolved.insert((url.clone(), h), "fetch limit reached".to_string());
            }
            continue;
        }
        if offline {
            return Err((
                EXIT_SANDBOX_ERROR,
                format!("--resolve-headings cannot fetch '{url}' while --offline is active"),
            ));
        }
        let (req_url, accept) = fetch_url(&url).unwrap();
        let (found, reason) = match fetcher(&req_url, accept) {
            Ok(body) => (
                parse_rendered_headings(&body),
                "no such heading on the rendered page".to_string(),
            ),
            Err(err_name) => (HashMap::new(), format!("fetch failed: {err_name}")),
        };
        for h in headings {
            let anchor_ok = found
                .get(&heading_key(&h))
                .is_some_and(|a| !a.is_empty() && ANCHOR_ID_RE.is_match(a));
            if !anchor_ok {
                unresolved.insert((url.clone(), h), reason.clone());
            }
        }
    }

    let num_files = checker.files.len();
    for file_idx in 0..num_files {
        let r_idx = checker.files[file_idx].root_idx;
        if checker.roots[r_idx].context {
            continue;
        }
        let records: Vec<SpecRecord> = checker.files[file_idx]
            .records
            .iter()
            .map(|(_, r)| r.clone())
            .collect();
        for rec in records {
            for (support, at) in supports(&rec.data, &rec.path) {
                let Some(doc_name) = support.get("doc").and_then(Value::as_str) else {
                    continue;
                };
                let Some((doc, _)) = checker.files[file_idx].documents.get(doc_name).cloned()
                else {
                    continue;
                };
                let url = doc
                    .get("url")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string();
                let Some(at_arr) = support.get("at").and_then(Value::as_array) else {
                    continue;
                };
                for (index, locator) in at_arr.iter().enumerate() {
                    let Some(heading) = locator.get("heading").and_then(Value::as_str) else {
                        continue;
                    };
                    let mut reason = unresolved.get(&(url.clone(), heading.to_string())).cloned();
                    if fetch_url(&url).is_none() {
                        reason = Some(
                            "unsupported document URL (needs a full-commit GitHub blob or wiki page)"
                                .to_string(),
                        );
                    }
                    if let Some(why) = reason {
                        let mut hpath = at.clone();
                        hpath.push(PathElem::from("at"));
                        hpath.push(PathElem::Index(index));
                        hpath.push(PathElem::from("heading"));
                        checker.add_file(
                            file_idx,
                            &hpath,
                            format!("{}: heading {}: {why}", rec.id, py_quote_str(heading)),
                            "warning",
                            false,
                            true,
                            false,
                        );
                    }
                }
            }
        }
    }
    Ok(())
}

/// Checks `heading:` locators on cited documents against live GitHub URLs (`headingcheck.py:check`).
pub fn check_headings(checker: &mut Checker, offline: bool) -> Result<(), (i32, String)> {
    check_headings_with_fetcher(checker, offline, |req_url, accept| {
        let mut req = ureq::get(req_url)
            .set("Accept", accept)
            .set("User-Agent", "spec-explorer");
        if req_url.starts_with("https://api.github.com/") {
            if let Ok(token) =
                std::env::var("GITHUB_TOKEN").or_else(|_| std::env::var("GH_TOKEN"))
            {
                if !token.is_empty() {
                    req = req.set("Authorization", &format!("Bearer {token}"));
                }
            }
        }
        match req.call() {
            Ok(resp) => resp.into_string().map_err(|_| "OSError".to_string()),
            Err(_) => Err("OSError".to_string()),
        }
    })
}

// ---------------------------------------------------------------------------
// Full checker pipeline (`load_and_run_checker`) & standalone `.facts.yaml` (`check_facts`)
// ---------------------------------------------------------------------------

fn check_structure_full(
    checker: &mut Checker,
    schemas: &Schemas,
    schema_map: &BTreeMap<String, Value>,
) {
    let mut by_path: HashMap<PathBuf, usize> = HashMap::new();
    for (idx, f) in checker.files.iter().enumerate() {
        by_path.insert(f.path.clone(), idx);
    }

    for root_idx in 0..checker.roots.len() {
        let spec_paths = checker.roots[root_idx].spec_paths.clone();
        let mut stems: BTreeMap<String, Vec<PathBuf>> = BTreeMap::new();
        for p in &spec_paths {
            let fname = p
                .file_name()
                .map(|s| s.to_string_lossy().into_owned())
                .unwrap_or_default();
            let stem = fname.strip_suffix(SPEC_SUFFIX).unwrap_or(&fname).to_string();
            stems.entry(stem).or_default().push(p.clone());
        }

        // First run `records::Checker::check_structure`, OR run our own record validation using
        // `crate::schema::validate_file` so `.verify.yaml` gets full schema cascade filtering +
        // `textcheck::check_data_where` + `BF-GW-27` context-root taint rules!
        let _ = schemas;
        for (stem, paths) in &stems {
            if paths.len() > 1 {
                for p in paths {
                    let others: Vec<String> = paths
                        .iter()
                        .filter(|q| *q != p)
                        .map(|q| rel_to_root(&checker.roots[root_idx], q))
                        .collect();
                    let msg = format!(
                        "this file and {} would share the verification record resources/{stem}.verify.yaml; give spec files distinct names",
                        others.join(", ")
                    );
                    if let Some(&f_idx) = by_path.get(p) {
                        checker.add_file(f_idx, &[], msg, "error", false, true, true);
                        checker.files[f_idx].record_state = "shared".to_string();
                    } else {
                        checker.add_where(
                            p,
                            Some(root_idx),
                            None,
                            &[],
                            msg,
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }
            }
        }

        let record_paths = checker.roots[root_idx].record_paths.clone();
        for rpath in record_paths {
            check_one_verify_record(checker, schema_map, root_idx, &rpath, &stems, &by_path);
        }
    }
}

fn check_one_verify_record(
    checker: &mut Checker,
    schema_map: &BTreeMap<String, Value>,
    root_idx: usize,
    rpath: &Path,
    stems: &BTreeMap<String, Vec<PathBuf>>,
    by_path: &HashMap<PathBuf, usize>,
) {
    let mut raw = Vec::new();
    let (ok, _, loaded_opt) = match fast_validate_file(rpath, schema_map, None, &mut raw)
    {
        Ok(res) => res,
        Err(msg) => {
            checker.add_where(
                rpath,
                Some(root_idx),
                None,
                &[],
                msg,
                "error",
                false,
                true,
                true,
            );
            return;
        }
    };
    add_schema_findings_to_checker(checker, raw, Some(root_idx), true);
    if ok {
        if let Some(ref ld) = loaded_opt {
            if let Some(ref d) = ld.data {
                textcheck_data_where(checker, rpath, Some(root_idx), Some(ld), d, None, true);
            }
        }
    }

    let fname = rpath
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default();
    let stem = fname.strip_suffix(".verify.yaml").unwrap_or(&fname);
    let owners = stems.get(stem).cloned().unwrap_or_default();

    if owners.is_empty() {
        let path_at = if ok {
            vec![PathElem::from("spec_file")]
        } else {
            Vec::new()
        };
        let root_label = checker.roots[root_idx].label();
        checker.add_where(
            rpath,
            Some(root_idx),
            loaded_opt.as_ref(),
            &path_at,
            format!(
                "no spec file named {stem}{SPEC_SUFFIX} in root {root_label}: a record belongs to the spec file of its name"
            ),
            "error",
            false,
            true,
            true,
        );
        return;
    }
    if owners.len() > 1 {
        return;
    }
    let Some(&f_idx) = by_path.get(&owners[0]) else {
        return;
    };
    checker.files[f_idx].record_path = Some(rpath.to_path_buf());
    if !ok {
        checker.files[f_idx].record_state = "invalid".to_string();
        return;
    }
    let Some(loaded) = loaded_opt else {
        checker.files[f_idx].record_state = "invalid".to_string();
        return;
    };
    let Some(data) = loaded.data.clone() else {
        checker.files[f_idx].record_state = "invalid".to_string();
        return;
    };

    let is_ctx = checker.roots[root_idx].context;
    let rel = rel_to_root(&checker.roots[root_idx], &checker.files[f_idx].path);
    let spec_file_val = data.get("spec_file").and_then(Value::as_str).unwrap_or("");
    if spec_file_val != rel {
        // BF-GW-27: Upstream `.verify.yaml` `spec_file` path mismatches in a context root are
        // downgraded context warnings and do not taint the context root.
        checker.add_where(
            rpath,
            Some(root_idx),
            Some(&loaded),
            &[PathElem::from("spec_file")],
            format!(
                "spec_file '{spec_file_val}': this record belongs to '{rel}', the spec file of its name"
            ),
            "error",
            false,
            true,
            !is_ctx,
        );
    }
    let spec_val = data.get("spec").and_then(Value::as_str).unwrap_or("");
    let f_spec_id = checker.files[f_idx].spec_id();
    let is_ov = checker.files[f_idx].is_overlay();
    if spec_val != f_spec_id {
        let kind_phrase = if is_ov { "an overlay of" } else { "spec" };
        checker.add_where(
            rpath,
            Some(root_idx),
            Some(&loaded),
            &[PathElem::from("spec")],
            format!("spec '{spec_val}': the spec file '{rel}' is {kind_phrase} '{f_spec_id}'"),
            "error",
            false,
            true,
            true,
        );
    }

    if let Some(sources_arr) = data.get("sources").and_then(Value::as_array) {
        let spec_docs = checker.files[f_idx]
            .data
            .get("resources")
            .and_then(|r| r.get("documents"))
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        for (s_idx, src_entry) in sources_arr.iter().enumerate() {
            let Some(src_obj) = src_entry.as_object() else {
                continue;
            };
            if !src_obj.contains_key("commit") && !src_obj.contains_key("sha256") {
                let src_name = src_obj.get("name").and_then(Value::as_str).unwrap_or("");
                let matches_unpinned_doc = spec_docs.iter().any(|d| {
                    d.get("name").and_then(Value::as_str) == Some(src_name)
                        && !d.as_object().is_some_and(|m| m.contains_key("sha256"))
                        && d.get("fetch").and_then(Value::as_str) == Some("ok")
                });
                if !matches_unpinned_doc {
                    checker.add_where(
                        rpath,
                        Some(root_idx),
                        Some(&loaded),
                        &[PathElem::from("sources"), PathElem::from(s_idx)],
                        format!(
                            "source '{src_name}' without commit or sha256 must name an unpinned fetch: ok document in '{rel}'"
                        ),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }
    }

    checker.files[f_idx].record_state = "ok".to_string();
    let mut counts: HashMap<String, i64> = crate::records::SUMMARY
        .iter()
        .map(|&(_, v)| (v.to_string(), 0))
        .collect();

    if let Some(verdicts_map) = data.get("verdicts").and_then(Value::as_object) {
        for (key, v) in verdicts_map {
            let v_str = v.get("verdict").and_then(Value::as_str).unwrap_or("");
            if let Some(c) = counts.get_mut(v_str) {
                *c += 1;
            }
            let kpath = vec![PathElem::from("verdicts"), PathElem::Key(key.clone())];
            let (fid, sub_opt) = match key.split_once('.') {
                Some((a, b)) => (a, Some(b)),
                None => (key.as_str(), None),
            };
            if checker.files[f_idx].duplicated.contains(fid) {
                checker.add_where(
                    rpath,
                    Some(root_idx),
                    Some(&loaded),
                    &kpath,
                    format!(
                        "verdict key '{key}': fact id '{fid}' is declared twice in {rel}, so the key is ambiguous"
                    ),
                    "error",
                    true,
                    true,
                    true,
                );
                continue;
            }
            if !checker.files[f_idx].record_map.contains_key(fid) {
                checker.add_where(
                    rpath,
                    Some(root_idx),
                    Some(&loaded),
                    &kpath,
                    format!("verdict key '{key}' names no fact, instance or variant of {rel}"),
                    "error",
                    true,
                    true,
                    true,
                );
                continue;
            }
            if let Some(sub) = sub_opt {
                if !checker.files[f_idx].record_map.contains_key(key)
                    || checker.files[f_idx].duplicated.contains(key)
                {
                    checker.add_where(
                        rpath,
                        Some(root_idx),
                        Some(&loaded),
                        &kpath,
                        format!(
                            "verdict key '{key}': '{fid}' has no field or step '{sub}' with its own support (a sub-key names a register field or sequence step, D16)"
                        ),
                        "error",
                        true,
                        true,
                        true,
                    );
                    continue;
                }
            }

            let rec = checker.files[f_idx].get_record(key).unwrap().clone();
            let mut vpath = kpath.clone();
            vpath.push(PathElem::from("verdict"));
            if rec.path.first() == Some(&PathElem::from("facts")) {
                let gap = !crate::records::has_support(&rec.data);
                if gap && v_str != "GAP" {
                    checker.add_where(
                        rpath,
                        Some(root_idx),
                        Some(&loaded),
                        &vpath,
                        format!(
                            "verdict {v_str} for '{fid}', a gap fact (no support): its verdict is GAP"
                        ),
                        "error",
                        false,
                        true,
                        true,
                    );
                } else if !gap && v_str == "GAP" {
                    checker.add_where(
                        rpath,
                        Some(root_idx),
                        Some(&loaded),
                        &vpath,
                        format!(
                            "verdict GAP for '{fid}', which has support: GAP is a gap fact's verdict"
                        ),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            } else if v_str == "GAP" {
                checker.add_where(
                    rpath,
                    Some(root_idx),
                    Some(&loaded),
                    &vpath,
                    format!(
                        "verdict GAP for {}: GAP is a gap fact's verdict, and an instance or variant row is never a gap",
                        what_record(&rec)
                    ),
                    "error",
                    false,
                    true,
                    true,
                );
            }

            if v_str != "ADJUDICATE" {
                if let Some(readers) = v.get("readers").and_then(Value::as_array) {
                    for (i, reader) in readers.iter().enumerate() {
                        let r_verdict = reader
                            .get("verdict")
                            .and_then(Value::as_str)
                            .unwrap_or("");
                        if r_verdict != v_str {
                            let mut rpath_at = kpath.clone();
                            rpath_at.push(PathElem::from("readers"));
                            rpath_at.push(PathElem::Index(i));
                            rpath_at.push(PathElem::from("verdict"));
                            checker.add_where(
                                rpath,
                                Some(root_idx),
                                Some(&loaded),
                                &rpath_at,
                                format!(
                                    "verdict key '{key}': a reader's verdict {r_verdict} disagrees with {v_str}; record the disagreement as ADJUDICATE with readings"
                                ),
                                "error",
                                false,
                                true,
                                true,
                            );
                        }
                    }
                }
            }
            checker.files[f_idx]
                .verdicts
                .insert(key.clone(), (v.clone(), kpath));
        }
    }

    if let Some(sum_obj) = data.get("summary").and_then(Value::as_object) {
        for &(name, value) in crate::records::SUMMARY {
            let got = sum_obj.get(name).and_then(Value::as_i64).unwrap_or(0);
            let want = counts.get(value).copied().unwrap_or(0);
            if got != want {
                checker.add_where(
                    rpath,
                    Some(root_idx),
                    Some(&loaded),
                    &[PathElem::from("summary"), PathElem::from(name)],
                    format!("summary {name}: {got}, but {want} verdict(s) are {value}"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }
    }
    checker.files[f_idx].record_loaded = Some(loaded);
}

/// Loads all roots, runs all semantic, peripheral, topology, corpus, index, verification-record,
/// stub, and optional heading checks (`speccheck.py:check`).
pub fn load_and_run_checker(
    checker: &mut Checker,
    roots: &[PathBuf],
    context_roots: &[PathBuf],
    stubs: &[PathBuf],
    stubs_from: &[PathBuf],
    resolve_headings: bool,
    offline: bool,
    schemas: &Schemas,
) -> Result<(), (i32, String)> {
    let schema_map = &*CACHED_SCHEMA_MAP;
    let loaded_indexes = load_roots_full(checker, roots, context_roots, schema_map)?;

    checker.check_roots_unique();
    for f_idx in 0..checker.files.len() {
        checker.index_file(f_idx);
    }
    for f_idx in 0..checker.files.len() {
        check_file_full(checker, f_idx);
    }
    check_structure_full(checker, schemas, schema_map);
    check_composition_full(checker);
    checker.check_references();
    crate::topology::check(checker);
    crate::corpus::check(checker);
    check_indexes_full(checker, &loaded_indexes);
    checker.first_pass();
    checker.check_trust();
    checker.second_pass();
    check_stubs(checker, stubs.to_vec(), stubs_from).map_err(|msg| (EXIT_SANDBOX_ERROR, msg))?;
    if resolve_headings {
        check_headings(checker, offline)?;
    }
    Ok(())
}

/// Standalone `.facts.yaml` check mode (`speccheck.py:check_facts`, `BF-IMX-18`).
pub fn check_facts(
    paths: &[PathBuf],
    target: &Path,
    require_license: bool,
    public_skills: &HashSet<String>,
    context_roots: &[PathBuf],
    stubs: &[PathBuf],
    stubs_from: &[PathBuf],
    require_verified: Option<String>,
    resolve_headings: bool,
    offline: bool,
) -> Result<Checker, (i32, String)> {
    if !context_roots.is_empty()
        || !stubs.is_empty()
        || !stubs_from.is_empty()
        || require_verified.is_some()
    {
        return Err((
            EXIT_USAGE_ERROR,
            "standalone facts checks do not take context, stub or verification options".to_string(),
        ));
    }
    if paths.is_empty() {
        return Err((
            EXIT_USAGE_ERROR,
            "--root takes at least one *.facts.yaml file".to_string(),
        ));
    }
    if !target.is_dir() || through_link(target) {
        return Err((
            EXIT_USAGE_ERROR,
            "--root must name a directory reached without symbolic links".to_string(),
        ));
    }
    if !target.join(MARKER).is_file() {
        return Err((
            EXIT_SANDBOX_ERROR,
            format!("--root {}: no {MARKER} (not a spec root)", target.display()),
        ));
    }

    let schema_map = &*CACHED_SCHEMA_MAP;
    let mut checker = Checker::new(require_license, public_skills.clone(), None);
    let real = target.canonicalize().unwrap_or_else(|_| target.to_path_buf());
    checker.roots.push(SpecRoot {
        given: target.to_path_buf(),
        real,
        context: false,
        order: 0,
        name: None,
        layer: None,
        rank: 0,
        accepts: None,
        extension: None,
        marker: None,
        files: Vec::new(),
        spec_paths: Vec::new(),
        record_paths: Vec::new(),
        corpus_path: None,
        corpus: None,
        index_paths: Vec::new(),
        untrusted: Vec::new(),
    });
    read_marker_full(&mut checker, 0, &schema_map);
    if checker.roots[0].accepts.is_none() {
        return Ok(checker);
    }

    let mut seen: HashSet<PathBuf> = HashSet::new();
    for path in paths {
        let resolved = path.canonicalize().unwrap_or_else(|_| path.clone());
        if !seen.insert(resolved) {
            return Err((
                EXIT_USAGE_ERROR,
                format!("{} is given more than once", path.display()),
            ));
        }
        let name = path
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        if !name.ends_with(".facts.yaml") {
            return Err((
                EXIT_USAGE_ERROR,
                format!(
                    "{}: with --root, check takes *.facts.yaml files",
                    path.display()
                ),
            ));
        }
        if !path.exists() {
            return Err((EXIT_USAGE_ERROR, format!("{}: file not found", path.display())));
        }
        if !path.is_file() || through_link(path) {
            return Err((
                EXIT_USAGE_ERROR,
                format!(
                    "{}: must be a regular file reached without symbolic links",
                    path.display()
                ),
            ));
        }
        load_spec_full(&mut checker, 0, path, &schema_map);
    }

    for f_idx in 0..checker.files.len() {
        checker.index_file(f_idx);
    }
    for f_idx in 0..checker.files.len() {
        check_file_full(&mut checker, f_idx);
    }
    checker.check_references();
    if resolve_headings {
        check_headings(&mut checker, offline)?;
    }
    Ok(checker)
}

/// Runs `check` over `roots` and `context_roots` (`spec.py:cmd_check`).
#[must_use]
pub fn check_roots(
    roots: &[PathBuf],
    context_roots: &[PathBuf],
    require_license: bool,
    public_skills: &HashSet<String>,
    require_verified: Option<String>,
    stubs: &[PathBuf],
    stubs_from: &[PathBuf],
    resolve_headings: bool,
    offline: bool,
) -> CheckReport {
    if roots.is_empty() {
        return CheckReport {
            exit_code: EXIT_USAGE_ERROR,
            ok: false,
            error: Some("usage".to_string()),
            roots: Vec::new(),
            specs: 0,
            stubs: 0,
            verification: STATUSES.iter().map(|&s| (s.to_string(), 0)).collect(),
            findings: vec![SpecFinding {
                path: String::new(),
                line: 0,
                column: 0,
                level: "error".to_string(),
                message: "at least one root directory is required".to_string(),
            }],
            text_lines: Vec::new(),
        };
    }

    let schemas = crate::records::load_schemas();
    let mut checker = Checker::new(require_license, public_skills.clone(), require_verified);
    if let Err((code, msg)) = load_and_run_checker(
        &mut checker,
        roots,
        context_roots,
        stubs,
        stubs_from,
        resolve_headings,
        offline,
        schemas,
    ) {
        let err_kind = if code == EXIT_USAGE_ERROR {
            "usage"
        } else {
            "precondition"
        };
        return CheckReport {
            exit_code: code,
            ok: false,
            error: Some(err_kind.to_string()),
            roots: Vec::new(),
            specs: 0,
            stubs: 0,
            verification: STATUSES.iter().map(|&s| (s.to_string(), 0)).collect(),
            findings: vec![SpecFinding {
                path: String::new(),
                line: 0,
                column: 0,
                level: "error".to_string(),
                message: msg,
            }],
            text_lines: Vec::new(),
        };
    }

    build_check_report(&checker)
}

fn build_check_report(checker: &Checker) -> CheckReport {
    let ordered = checker.ordered_findings();
    let errors = ordered.iter().filter(|f| f.level == "error").count();
    let warnings = ordered.len() - errors;

    let mut verification: BTreeMap<String, usize> =
        STATUSES.iter().map(|&s| (s.to_string(), 0)).collect();
    for (f_idx, entry) in &checker.status {
        let r_idx = checker.files[*f_idx].root_idx;
        if !checker.roots[r_idx].context {
            for row in &entry.facts {
                if let Some(c) = verification.get_mut(&row.status) {
                    *c += 1;
                }
            }
        }
    }

    let mut text_lines: Vec<String> = ordered.iter().map(ToString::to_string).collect();
    text_lines.push(format!(
        "{} root(s), {} spec file(s), {} stub(s): {errors} error(s), {warnings} warning(s)",
        checker.roots.len(),
        checker.files.len(),
        checker.stubs
    ));

    let root_infos = checker
        .roots
        .iter()
        .map(|r| RootInfo {
            path: r.given.to_string_lossy().into_owned(),
            name: r.name.clone(),
            layer: r.layer.clone(),
            context: r.context,
        })
        .collect();

    CheckReport {
        exit_code: if errors > 0 {
            EXIT_DOMAIN_FAILURE
        } else {
            EXIT_OK
        },
        ok: errors == 0,
        error: None,
        roots: root_infos,
        specs: checker.files.len(),
        stubs: checker.stubs,
        verification,
        findings: ordered,
        text_lines,
    }
}

/// Determines whether `check` was invoked in standalone `.facts.yaml` mode (`BF-IMX-18`).
///
/// Under `BF-IMX-18`:
/// - Passing a directory target alongside `--root <dir>` (e.g. `driver-lab check <dir> --root <dir>`)
///   runs normal root-directory checking rather than failing with a standalone-facts usage error.
/// - Standalone `.facts.yaml` mode is triggered when any target path ends with `.facts.yaml`
///   (or is a file with `kind: facts` / a file target paired with `--root`).
fn is_standalone_facts_invocation(targets: &[PathBuf], root_opt: Option<&PathBuf>) -> bool {
    if targets.iter().any(|p| {
        p.file_name()
            .and_then(|n| n.to_str())
            .is_some_and(|n| n.ends_with(".facts.yaml"))
    }) {
        return true;
    }
    if root_opt.is_some() {
        if targets.is_empty() {
            return false;
        }
        // If any target is a file (or does not exist as a directory and looks like a file),
        // and not all targets are directories, treat as standalone facts mode.
        if targets.iter().all(|p| p.is_dir()) {
            return false;
        }
        return true;
    }
    false
}

/// Executes `driver-lab check` (`spec.py:cmd_check`, `BF-IMX-18`).
pub fn run_check_cmd(
    cli: &Cli,
    args: &CheckArgs,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let public_skills: HashSet<String> = args.public_skills.iter().cloned().collect();
    let require_verified = if let Some(ref rv) = args.require_verified {
        Some(rv.clone())
    } else if !args.verify.is_empty() {
        Some("pr".to_string())
    } else {
        None
    };

    let report = if is_standalone_facts_invocation(&args.targets, args.root.as_ref()) {
        let Some(ref root_dir) = args.root else {
            let msg = "checking a standalone *.facts.yaml file requires --root <dir>";
            let rep = CheckReport {
                exit_code: EXIT_USAGE_ERROR,
                ok: false,
                error: Some("usage".to_string()),
                roots: Vec::new(),
                specs: 0,
                stubs: 0,
                verification: STATUSES.iter().map(|&s| (s.to_string(), 0)).collect(),
                findings: vec![SpecFinding {
                    path: String::new(),
                    line: 0,
                    column: 0,
                    level: "error".to_string(),
                    message: msg.to_string(),
                }],
                text_lines: Vec::new(),
            };
            return emit_check_report(&rep, cli.json, stdout, stderr);
        };
        match check_facts(
            &args.targets,
            root_dir,
            args.require_license,
            &public_skills,
            &args.context_roots,
            &args.stubs,
            &args.stubs_from,
            require_verified,
            args.resolve_headings,
            cli.offline,
        ) {
            Ok(checker) => build_check_report(&checker),
            Err((code, msg)) => {
                let err_kind = if code == EXIT_USAGE_ERROR {
                    "usage"
                } else {
                    "precondition"
                };
                CheckReport {
                    exit_code: code,
                    ok: false,
                    error: Some(err_kind.to_string()),
                    roots: Vec::new(),
                    specs: 0,
                    stubs: 0,
                    verification: STATUSES.iter().map(|&s| (s.to_string(), 0)).collect(),
                    findings: vec![SpecFinding {
                        path: String::new(),
                        line: 0,
                        column: 0,
                        level: "error".to_string(),
                        message: msg,
                    }],
                    text_lines: Vec::new(),
                }
            }
        }
    } else {
        let mut roots: Vec<PathBuf> = args.targets.clone();
        if let Some(ref r) = args.root {
            let r_canon = r.canonicalize().unwrap_or_else(|_| r.clone());
            let already = roots
                .iter()
                .any(|t| t.canonicalize().unwrap_or_else(|_| t.clone()) == r_canon);
            if !already {
                roots.push(r.clone());
            }
        }
        check_roots(
            &roots,
            &args.context_roots,
            args.require_license,
            &public_skills,
            require_verified,
            &args.stubs,
            &args.stubs_from,
            args.resolve_headings,
            cli.offline,
        )
    };

    emit_check_report(&report, cli.json, stdout, stderr)
}

fn emit_check_report(
    report: &CheckReport,
    json_mode: bool,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    if json_mode {
        let _ = writeln!(
            stdout,
            "{}",
            serde_json::to_string(report).unwrap_or_default()
        );
    } else if report.error.is_some() {
        if let Some(first) = report.findings.first() {
            let _ = writeln!(stderr, "{}", visible_name(&format!("error: {}", first.message)));
        }
    } else {
        for line in &report.text_lines {
            let _ = writeln!(stdout, "{}", visible_name(line));
        }
    }
    report.exit_code
}
