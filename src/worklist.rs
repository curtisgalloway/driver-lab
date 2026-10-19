// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Verification worklist (`todo`) and freshness status (`status`) commands (`worklist.py`, `RT-4`, `BF-ARM-21`).

use crate::diagnostic::{visible_name, EXIT_DOMAIN_FAILURE, EXIT_OK, EXIT_USAGE_ERROR};
use crate::records::{
    has_support, load_schemas, Checker, PathElem, RootInfo, SpecFile, SpecRecord,
    SpecStatusEntry, StatusReport, STATUSES, SUMMARY,
};
use crate::{Cli, StatusArgs, TodoArgs};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::io::Write;
use std::ops::Not;
use std::path::{Path, PathBuf};

/// Closed set of TODO `check` categories (`worklist.py:CHECKS`).
pub const CHECKS: &[&str] = &["hardware", "document", "source"];

/// Closed set of TODO item kinds (`worklist.py:KINDS`).
pub const KINDS: &[&str] = &[
    "gap",
    "supported-with-todo",
    "instance",
    "variant",
    "assumption",
    "field",
    "layout-field",
    "step",
    "order",
];

/// A single TODO worklist item (`worklist.py:_item`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Item {
    /// Full fact/subrecord reference (`<spec>@<root>#<id>`).
    pub fact: String,
    /// Spec file path string.
    pub file: String,
    /// Root label.
    pub root: String,
    /// Spec identifier.
    pub spec: String,
    /// Item kind (`gap`, `supported-with-todo`, `instance`, `variant`, `assumption`, `field`, `layout-field`, `step`, `order`).
    pub kind: String,
    /// Check kind (`hardware`, `document`, `source`).
    pub check: String,
    /// TODO text.
    pub text: String,
    /// Optional verification method.
    pub method: Option<String>,
    /// Whether the item is bring-up critical.
    pub critical: bool,
    /// Optional scope object.
    pub scope: Option<Value>,
    /// Optional instance name when `kind == "instance"`.
    pub instance: Option<String>,
    /// `true` when `check == "hardware"` and `method` is absent (omitted from JSON when `false`).
    #[serde(skip_serializing_if = "Not::not", default)]
    pub missing_method: bool,
}

fn row_kind(path: &[PathElem]) -> String {
    let len = path.len();
    if len >= 3
        && matches!(&path[len - 2], PathElem::Key(k) if k == "fields")
        && matches!(&path[len - 3], PathElem::Key(k) if k == "layout")
    {
        return "layout-field".to_string();
    }
    if len >= 2 {
        if let PathElem::Key(k) = &path[len - 2] {
            match k.as_str() {
                "fields" => return "field".to_string(),
                "steps" => return "step".to_string(),
                "order" => return "order".to_string(),
                _ => {}
            }
        }
    }
    String::new()
}

#[allow(clippy::too_many_arguments)]
fn build_item(
    checker: &Checker,
    f: &SpecFile,
    ref_str: String,
    kind: String,
    todo: &Value,
    critical: bool,
    scope: Option<Value>,
    instance: Option<String>,
) -> Item {
    let check = todo
        .get("check")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let method = todo
        .get("method")
        .and_then(Value::as_str)
        .map(ToString::to_string);
    let missing_method = check == "hardware" && method.is_none();
    let root_label = checker.roots[f.root_idx].label();
    Item {
        fact: ref_str,
        file: f.path.to_string_lossy().to_string(),
        root: root_label,
        spec: f.spec_id(),
        kind,
        check,
        text: todo
            .get("text")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        method,
        critical,
        scope,
        instance,
        missing_method,
    }
}

/// Collects child-row TODO items for a top-level record (`worklist.py:row_items`).
#[must_use]
pub fn row_items(checker: &Checker, f: &SpecFile, rec: &SpecRecord) -> Vec<Item> {
    let mut items = Vec::new();
    let critical = rec
        .data
        .get("critical")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    for (row, path) in crate::peripheral::children(&rec.data, &rec.path) {
        if let Some(todo) = row.get("todo") {
            let row_id = row
                .get("id")
                .and_then(Value::as_str)
                .map(ToString::to_string)
                .unwrap_or_else(|| {
                    if path.len() >= 2 {
                        let k = match &path[path.len() - 2] {
                            PathElem::Key(s) => s.as_str(),
                            PathElem::Index(_) => "",
                        };
                        let idx = match &path[path.len() - 1] {
                            PathElem::Index(i) => i.to_string(),
                            PathElem::Key(s) => s.clone(),
                        };
                        format!("{k}[{idx}]")
                    } else {
                        String::new()
                    }
                });
            items.push(build_item(
                checker,
                f,
                format!("{}.{row_id}", rec.full),
                row_kind(&path),
                todo,
                critical,
                None,
                None,
            ));
        }
    }
    items
}

/// Formats child-row TODO items for rendered Markdown/HTML pages (`worklist.py:page_rows`).
#[must_use]
pub fn page_rows(
    checker: &Checker,
    f: &SpecFile,
    rec: &SpecRecord,
) -> Vec<BTreeMap<String, String>> {
    row_items(checker, f, rec)
        .into_iter()
        .map(|i| {
            let mut map = BTreeMap::new();
            map.insert("fact".to_string(), i.fact);
            map.insert("kind".to_string(), i.kind);
            map.insert("check".to_string(), i.check);
            map.insert("text".to_string(), i.text);
            map.insert("method".to_string(), i.method.unwrap_or_default());
            map
        })
        .collect()
}

/// Collects all TODO items across checked roots in `checker` (`worklist.py:collect`).
#[must_use]
pub fn collect(checker: &Checker) -> Vec<Item> {
    let mut items = Vec::new();
    for f in &checker.files {
        if checker.roots[f.root_idx].context {
            continue;
        }
        let root_label = checker.roots[f.root_idx].label();
        let spec_id = f.spec_id();
        for (_, rec) in &f.records {
            if rec.parent_id.is_some() {
                continue;
            }
            let data = &rec.data;
            let critical = data
                .get("critical")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            if let Some(PathElem::Key(top)) = rec.path.first() {
                let kind = if top == "facts" {
                    if has_support(data) {
                        "supported-with-todo".to_string()
                    } else {
                        "gap".to_string()
                    }
                } else if top == "instances" {
                    "instance".to_string()
                } else if top == "variants" {
                    "variant".to_string()
                } else {
                    String::new()
                };

                if let Some(todo) = data.get("todo") {
                    items.push(build_item(
                        checker,
                        f,
                        rec.full.clone(),
                        kind,
                        todo,
                        critical,
                        data.get("scope").cloned(),
                        if top == "instances" {
                            data.get("name")
                                .and_then(Value::as_str)
                                .map(ToString::to_string)
                        } else {
                            None
                        },
                    ));
                }
            }
            items.extend(row_items(checker, f, rec));
        }
        if let Some(assumptions) = f.data.get("assumptions").and_then(Value::as_array) {
            for entry in assumptions {
                if let Some(todo) = entry.get("todo") {
                    let id = entry.get("id").and_then(Value::as_str).unwrap_or("");
                    items.push(build_item(
                        checker,
                        f,
                        format!("{spec_id}@{root_label}#{id}"),
                        "assumption".to_string(),
                        todo,
                        false,
                        None,
                        None,
                    ));
                }
            }
        }
    }
    items
}

/// Computes summary counts over `items` (`worklist.py:counts`).
#[must_use]
pub fn counts(items: &[Item]) -> Value {
    let mut by_check = BTreeMap::new();
    let mut by_kind = BTreeMap::new();
    for &c in CHECKS {
        by_check.insert(c.to_string(), 0usize);
    }
    for &k in KINDS {
        by_kind.insert(k.to_string(), 0usize);
    }

    let mut critical = 0usize;
    let mut missing_method = 0usize;

    for i in items {
        if let Some(c) = by_check.get_mut(&i.check) {
            *c += 1;
        }
        if let Some(k) = by_kind.get_mut(&i.kind) {
            *k += 1;
        }
        if i.critical {
            critical += 1;
        }
        if i.missing_method {
            missing_method += 1;
        }
    }

    json!({
        "total": items.len(),
        "by_check": by_check,
        "by_kind": by_kind,
        "critical": critical,
        "missing_method": missing_method,
    })
}

fn scope_str(scope: &Value) -> String {
    let mut parts = Vec::new();
    if let Some(obj) = scope.as_object() {
        for (k, v) in obj {
            if let Some(arr) = v.as_array() {
                let vals: Vec<_> = arr.iter().filter_map(Value::as_str).collect();
                parts.push(format!("{k}={}", vals.join(", ")));
            }
        }
    }
    parts.join("; ")
}

/// Formats human-readable worklist lines grouped by file in discovery order (`worklist.py:lines`).
pub fn lines<F>(items: &[Item], heading: F) -> Vec<String>
where
    F: Fn(&Item) -> String,
{
    let mut out = Vec::new();
    let mut file_order: Vec<String> = Vec::new();
    let mut by_file: HashMap<String, Vec<&Item>> = HashMap::new();
    for item in items {
        if !by_file.contains_key(&item.file) {
            file_order.push(item.file.clone());
        }
        by_file.entry(item.file.clone()).or_default().push(item);
    }

    for file_key in file_order {
        let Some(group) = by_file.get(&file_key) else {
            continue;
        };
        if group.is_empty() {
            continue;
        }
        out.push(format!("{}: {} TODO(s)", heading(group[0]), group.len()));
        let mut inst_order: Vec<String> = Vec::new();
        let mut instances: HashMap<String, Vec<&Item>> = HashMap::new();
        for item in group {
            if let Some(inst) = &item.instance {
                if !instances.contains_key(inst) {
                    inst_order.push(inst.clone());
                }
                instances.entry(inst.clone()).or_default().push(item);
            } else {
                out.extend(show(item, "  "));
            }
        }
        for name in inst_order {
            if let Some(rows) = instances.get(&name) {
                out.push(format!("  instance {name}:"));
                for item in rows {
                    out.extend(show(item, "    "));
                }
            }
        }
    }
    out
}

fn show(item: &Item, indent: &str) -> Vec<String> {
    let mut notes = Vec::new();
    if item.critical {
        notes.push("critical".to_string());
    }
    if let Some(scope) = &item.scope {
        notes.push(format!("scope: {}", scope_str(scope)));
    }
    if item.missing_method {
        notes.push("(no method)".to_string());
    }

    let mut head = format!(
        "{}{:<8} {:<19} {}",
        indent, item.check, item.kind, item.fact
    );
    if !notes.is_empty() {
        head.push_str("  ");
        head.push_str(&notes.join("; "));
    }

    let text = item.text.split_whitespace().collect::<Vec<_>>().join(" ");
    let mut out = vec![head, format!("{indent}    {text}")];
    if let Some(m) = &item.method {
        let m_str = m.split_whitespace().collect::<Vec<_>>().join(" ");
        out.push(format!("{indent}    method: {m_str}"));
    }
    out
}

fn resolve_roots_from_targets(
    targets: &[PathBuf],
    explicit_root: Option<&PathBuf>,
) -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if let Some(r) = explicit_root {
        roots.push(r.clone());
    }
    for t in targets {
        if !roots.contains(t) {
            roots.push(t.clone());
        }
    }
    roots
}

fn rel_to_root_given(root_given: &Path, path: &Path) -> String {
    path.strip_prefix(root_given)
        .map(|p| p.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path.to_string_lossy().into_owned())
}

/// Executes `driver-lab todo` (`spec.py:cmd_todo`).
pub fn run_todo_cmd(
    cli: &Cli,
    args: &TodoArgs,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let roots = resolve_roots_from_targets(&args.targets, args.root.as_ref());
    if roots.is_empty() {
        let msg = "at least one root directory is required";
        if cli.json {
            let payload = json!({
                "ok": false,
                "error": "usage",
                "roots": [],
                "errors": 0,
                "warnings": 0,
                "counts": counts(&[]),
                "todos": [],
                "findings": [{"path": "", "line": 0, "column": 0, "level": "error", "message": msg}]
            });
            let _ = writeln!(stdout, "{}", serde_json::to_string(&payload).unwrap());
        } else {
            let _ = writeln!(stderr, "error: {msg}");
        }
        return EXIT_USAGE_ERROR;
    }

    let public_skills: HashSet<String> = args.public_skills.iter().cloned().collect();
    let schemas = load_schemas();
    let mut checker = Checker::new(args.require_license, public_skills, None);
    if let Err((code, msg)) = crate::speccheck::load_and_run_checker(
        &mut checker,
        &roots,
        &args.context_roots,
        &[],
        &[],
        false,
        cli.offline,
        schemas,
    ) {
        let err_kind = if code == EXIT_USAGE_ERROR {
            "usage"
        } else {
            "precondition"
        };
        if cli.json {
            let payload = json!({
                "ok": false,
                "error": err_kind,
                "roots": [],
                "errors": 0,
                "warnings": 0,
                "counts": counts(&[]),
                "todos": [],
                "findings": [{"path": "", "line": 0, "column": 0, "level": "error", "message": msg}]
            });
            let _ = writeln!(stdout, "{}", serde_json::to_string(&payload).unwrap());
        } else {
            let _ = writeln!(stderr, "error: {msg}");
        }
        return code;
    }

    let ordered = checker.ordered_findings();
    let errors = ordered.iter().filter(|f| f.level == "error").count();
    let warnings = ordered.len() - errors;

    let mut items = collect(&checker);
    if let Some(ref check_filter) = args.check {
        items.retain(|i| &i.check == check_filter);
    }
    if let Some(ref spec_filter) = args.spec {
        items.retain(|i| &i.spec == spec_filter);
    }
    let summary = counts(&items);

    let mut root_given_by_label: HashMap<String, PathBuf> = HashMap::new();
    for r in &checker.roots {
        root_given_by_label.insert(r.label(), r.given.clone());
    }

    let mut text = lines(&items, |i| {
        let rel = root_given_by_label
            .get(&i.root)
            .map(|rg| rel_to_root_given(rg, Path::new(&i.file)))
            .unwrap_or_else(|| i.file.clone());
        format!("{}:{rel} ({})", i.root, i.spec)
    });
    for f in &ordered {
        if f.level == "error" {
            text.push(f.to_string());
        }
    }

    let by_check = summary.get("by_check").unwrap();
    let parts: Vec<String> = CHECKS
        .iter()
        .map(|&c| {
            let n = by_check.get(c).and_then(Value::as_u64).unwrap_or(0);
            format!("{n} {c}")
        })
        .collect();
    let mut tail = format!("{} TODO(s): {}", items.len(), parts.join(", "));
    let crit = summary
        .get("critical")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    if crit > 0 {
        tail.push_str(&format!(" ({crit} critical)"));
    }
    let mm = summary
        .get("missing_method")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    if mm > 0 {
        tail.push_str(&format!(" ({mm} hardware without method)"));
    }
    tail.push_str(&format!(
        "; the check found {errors} error(s), {warnings} warning(s)"
    ));
    text.push(tail);

    let root_infos: Vec<RootInfo> = checker
        .roots
        .iter()
        .map(|r| RootInfo {
            path: r.given.to_string_lossy().into_owned(),
            name: r.name.clone(),
            layer: r.layer.clone(),
            context: r.context,
        })
        .collect();

    let exit_code = if errors > 0 {
        EXIT_DOMAIN_FAILURE
    } else {
        EXIT_OK
    };
    if cli.json {
        let payload = json!({
            "ok": errors == 0,
            "roots": root_infos,
            "errors": errors,
            "warnings": warnings,
            "counts": summary,
            "todos": items,
            "findings": ordered,
        });
        let _ = writeln!(stdout, "{}", serde_json::to_string(&payload).unwrap());
    } else {
        for line in text {
            let _ = writeln!(stdout, "{}", visible_name(&line));
        }
    }
    exit_code
}

/// Executes `driver-lab status` (`spec.py:cmd_status`, `BF-ARM-21` `--no-fail-on-pending`).
pub fn run_status_cmd(
    cli: &Cli,
    args: &StatusArgs,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let roots = resolve_roots_from_targets(&args.targets, args.root.as_ref());
    if roots.is_empty() {
        let msg = "at least one root directory is required";
        if cli.json {
            let payload = json!({
                "ok": false,
                "error": "usage",
                "roots": [],
                "errors": 0,
                "warnings": 0,
                "specs": [],
                "findings": [{"path": "", "line": 0, "column": 0, "level": "error", "message": msg}]
            });
            let _ = writeln!(stdout, "{}", serde_json::to_string(&payload).unwrap());
        } else {
            let _ = writeln!(stderr, "error: {msg}");
        }
        return EXIT_USAGE_ERROR;
    }

    let public_skills: HashSet<String> = args.public_skills.iter().cloned().collect();
    let schemas = load_schemas();
    let mut checker = Checker::new(args.require_license, public_skills, None);
    if let Err((code, msg)) = crate::speccheck::load_and_run_checker(
        &mut checker,
        &roots,
        &args.context_roots,
        &[],
        &[],
        false,
        cli.offline,
        schemas,
    ) {
        let err_kind = if code == EXIT_USAGE_ERROR {
            "usage"
        } else {
            "precondition"
        };
        if cli.json {
            let payload = json!({
                "ok": false,
                "error": err_kind,
                "roots": [],
                "errors": 0,
                "warnings": 0,
                "specs": [],
                "findings": [{"path": "", "line": 0, "column": 0, "level": "error", "message": msg}]
            });
            let _ = writeln!(stdout, "{}", serde_json::to_string(&payload).unwrap());
        } else {
            let _ = writeln!(stderr, "error: {msg}");
        }
        return code;
    }

    let ordered = checker.ordered_findings();
    let errors = ordered.iter().filter(|f| f.level == "error").count();
    let warnings = ordered.len() - errors;

    let mut specs = Vec::new();
    let mut text = Vec::new();

    for (f_idx, entry) in &checker.status {
        let f = &checker.files[*f_idx];
        let root = &checker.roots[f.root_idx];
        if root.context {
            continue;
        }
        if let Some(ref spec_filter) = args.spec {
            if &entry.spec != spec_filter {
                continue;
            }
        }
        let mut rows = entry.facts.clone();
        if args.stale {
            rows.retain(|r| r.status != "current" || r.second_reader == "missing");
            if rows.is_empty() {
                continue;
            }
        }
        let rel = rel_to_root_given(&root.given, &f.path);
        let summary = if entry.state == "ok" {
            let s = f
                .record_loaded
                .as_ref()
                .and_then(|ld| ld.data.as_ref())
                .and_then(|d| d.get("summary"));
            let parts: Vec<String> = SUMMARY
                .iter()
                .map(|&(k, _)| {
                    let n = s
                        .and_then(|sobj| sobj.get(k))
                        .and_then(Value::as_i64)
                        .unwrap_or(0);
                    format!("{k} {n}")
                })
                .collect();
            format!(
                "{}: {}",
                entry.record.as_deref().unwrap_or(""),
                parts.join(", ")
            )
        } else if entry.state != "none" {
            format!("{}: {}", entry.record.as_deref().unwrap_or(""), entry.state)
        } else {
            "no record".to_string()
        };

        text.push(format!("{}:{rel} ({}): {summary}", root.label(), f.spec_id()));
        for r in &rows {
            let mut notes = Vec::new();
            if let Some(v) = &r.verdict {
                notes.push(v.clone());
            }
            if r.second_reader == "missing" {
                notes.push("needs a second reader".to_string());
            }
            if !r.changed.is_empty() {
                notes.push(format!("upstream changed: {}", r.changed.join(", ")));
            }
            if let Some(reason) = &r.reason {
                notes.push(reason.clone());
            }
            let suffix = if notes.is_empty() {
                String::new()
            } else {
                format!("  ({})", notes.join("; "))
            };
            text.push(format!("  {:<15} {}{suffix}", r.status, r.key));
        }

        specs.push(SpecStatusEntry {
            path: entry.path.clone(),
            root: entry.root.clone(),
            spec: entry.spec.clone(),
            record: entry.record.clone(),
            state: entry.state.clone(),
            facts: rows,
        });
    }

    let mut tally: HashMap<&str, usize> = STATUSES.iter().map(|&s| (s, 0)).collect();
    for spec in &specs {
        for r in &spec.facts {
            if let Some(c) = tally.get_mut(r.status.as_str()) {
                *c += 1;
            }
        }
    }

    for f in &ordered {
        if f.level == "error" {
            text.push(f.to_string());
        }
    }
    let tally_parts: Vec<String> = STATUSES
        .iter()
        .map(|&k| format!("{} {k}", tally[k]))
        .collect();
    text.push(format!(
        "{}; the check found {errors} error(s), {warnings} warning(s)",
        tally_parts.join(", ")
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

    // BF-ARM-21: `--no-fail-on-pending` guarantees exit 0 when the only findings are pending
    // verification (`unverified` or `needs a second reader`), while still failing on structural
    // or integrity errors (`errors > 0`).
    let exit_code = if errors > 0 {
        EXIT_DOMAIN_FAILURE
    } else {
        EXIT_OK
    };
    let report = StatusReport {
        exit_code,
        ok: errors == 0,
        error: None,
        roots: root_infos,
        errors,
        warnings,
        specs,
        findings: ordered,
        text_lines: text,
    };

    if cli.json {
        let mut val = serde_json::to_value(&report).unwrap_or(Value::Null);
        if args.no_fail_on_pending {
            if let Some(obj) = val.as_object_mut() {
                obj.insert("no_fail_on_pending".to_string(), Value::Bool(true));
            }
        }
        let _ = writeln!(stdout, "{}", serde_json::to_string(&val).unwrap());
    } else {
        for line in &report.text_lines {
            let _ = writeln!(stdout, "{}", visible_name(line));
        }
    }
    report.exit_code
}
