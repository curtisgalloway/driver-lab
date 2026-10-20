// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::records::{Checker, SpecFile, SpecRecord, StatusRow};
use crate::specmd;
use serde_json::Value;
use std::collections::{BTreeMap, HashMap};
use std::path::PathBuf;

pub fn escape(value: &str) -> String {
    let mut text = value.replace(['\n', '\r'], " ");
    text = text.trim_start().to_string();
    let lower = text.to_lowercase();
    if text.contains('@')
        || text.contains(':')
        || text.contains('|')
        || text.contains('*')
        || text.contains('_')
        || text.contains('`')
        || text.contains('<')
        || text.contains('[')
        || lower.contains("www.")
    {
        return code(&text);
    }
    let mut escaped = String::new();
    for c in text.chars() {
        if c.is_ascii_punctuation() {
            escaped.push('\\');
        }
        escaped.push(c);
    }
    escaped
}

pub fn code(value: &str) -> String {
    let text = value.replace(['\n', '\r'], " ");
    let mut max_backticks = 0;
    let mut current = 0;
    for c in text.chars() {
        if c == '`' {
            current += 1;
            if current > max_backticks {
                max_backticks = current;
            }
        } else {
            current = 0;
        }
    }
    let fence = "`".repeat(max_backticks + 1);
    let pad = if text.starts_with('`')
        || text.ends_with('`')
        || (text.starts_with(' ') && text.ends_with(' ') && !text.trim().is_empty())
    {
        " "
    } else {
        ""
    };
    if text.is_empty() {
        return String::new();
    }
    format!("{}{}{}{}{}", fence, pad, text, pad, fence)
}

pub fn _value(value: &Value) -> String {
    match value {
        Value::Object(_) | Value::Array(_) => serde_json::to_string(value).unwrap_or_default(),
        Value::String(s) => s.clone(),
        Value::Null => String::new(),
        _ => value.to_string(),
    }
}

pub struct View {
    pub lines: Vec<String>,
    pub expected: BTreeMap<(usize, String, String), usize>,
    pub line: usize,
}

impl Default for View {
    fn default() -> Self {
        Self::new()
    }
}

impl View {
    pub fn new() -> Self {
        Self {
            lines: Vec::new(),
            expected: BTreeMap::new(),
            line: 0,
        }
    }

    pub fn append(&mut self, value: String) {
        let count = value.chars().filter(|&c| c == '\n').count() + 1;
        self.lines.push(value);
        self.line += count;
    }

    pub fn extend(&mut self, values: Vec<String>) {
        for v in values {
            self.append(v);
        }
    }

    pub fn heading(&mut self, level: usize, value: &str) {
        *self
            .expected
            .entry((self.line, "heading_open".to_string(), String::new()))
            .or_insert(0) += 1;
        self.extend(vec![
            format!("{} {}", "#".repeat(level), value),
            String::new(),
        ]);
    }

    pub fn author(&mut self, value: &str, label: &str) {
        self.extend(vec![format!("{} (author text):", label), String::new()]);
        let mut max_backticks = 2;
        let mut current = 0;
        for c in value.chars() {
            if c == '`' {
                current += 1;
                if current > max_backticks {
                    max_backticks = current;
                }
            } else {
                current = 0;
            }
        }
        let fence = "`".repeat(max_backticks + 1);
        let mut content = value.to_string();
        if !content.is_empty() && !content.ends_with('\n') {
            content.push('\n');
        }
        *self
            .expected
            .entry((self.line, "fence".to_string(), content.clone()))
            .or_insert(0) += 1;
        self.extend(vec![
            format!("{}\n{}{}", fence, content, fence),
            String::new(),
        ]);
    }
}

pub fn _author(out: &mut View, value: &str, label: &str) {
    out.author(value, label);
}

pub fn source_commits_list(
    checker: &Checker,
    groups: &[Vec<&SpecFile>],
    values: &[String],
) -> Result<HashMap<PathBuf, String>, String> {
    let mut given: HashMap<PathBuf, (usize, String)> = HashMap::new();
    for group in groups {
        for f in group {
            let root = &checker.roots[f.root_idx];
            let abs = root
                .given
                .canonicalize()
                .unwrap_or_else(|_| root.given.clone());
            given
                .entry(abs)
                .or_insert_with(|| (root.order, root.given.to_string_lossy().into_owned()));
        }
    }
    let mut shown_vec: Vec<(usize, String)> = given.values().cloned().collect();
    shown_vec.sort();
    let shown = shown_vec
        .into_iter()
        .map(|(_, label)| label)
        .collect::<Vec<_>>()
        .join(", ");
    let mut commits: HashMap<PathBuf, String> = HashMap::new();
    for value in values {
        let (root, sha) = if let Some((name, s)) = value.rsplit_once('=') {
            let r = std::path::Path::new(name)
                .canonicalize()
                .unwrap_or_else(|_| PathBuf::from(name));
            if name.is_empty() || !given.contains_key(&r) {
                return Err(format!(
                    "--source-commit ROOT must name a rendered root directory (rendered: {shown})"
                ));
            }
            (r, s)
        } else {
            if given.len() != 1 {
                return Err("bare --source-commit requires exactly one rendered root".to_string());
            }
            (given.keys().next().unwrap().clone(), value.as_str())
        };
        if sha.len() != 40 || !sha.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')) {
            return Err("commit must be 40 lowercase hex characters".to_string());
        }
        if commits.contains_key(&root) {
            return Err("--source-commit given twice for a root".to_string());
        }
        commits.insert(root, sha.to_string());
    }
    Ok(commits)
}

pub fn source_commits(
    checker: &Checker,
    groups: &[Vec<&SpecFile>],
    source_commit: Option<&str>,
) -> Result<HashMap<PathBuf, String>, String> {
    let values: Vec<String> = match source_commit {
        Some(s) if !s.is_empty() => s.split('\n').map(ToString::to_string).collect(),
        _ => Vec::new(),
    };
    source_commits_list(checker, groups, &values)
}

pub fn render(
    checker: &Checker,
    spec_id: Option<&str>,
    merged: bool,
    with_status: bool,
    source_commit: Option<&str>,
    tool_commit: Option<&str>,
) -> Result<String, String> {
    if merged {
        for root in &checker.roots {
            if root.context && !root.untrusted.is_empty() {
                return Err(
                    "cannot render merged input: context root does not check clean".to_string(),
                );
            }
        }
    }

    let selected: Vec<&SpecFile> = checker
        .files
        .iter()
        .filter(|f| {
            let root = &checker.roots[f.root_idx];
            !root.context && spec_id.is_none_or(|sid| f.spec_id() == sid)
        })
        .collect();

    if selected.is_empty() {
        return Err(if spec_id.is_some() {
            "no checked spec matches --spec".to_string()
        } else {
            "no specs to render".to_string()
        });
    }

    let mut ids = Vec::new();
    for f in &selected {
        let sid = f.spec_id();
        if !ids.contains(&sid) {
            ids.push(sid);
        }
    }

    let mut groups: Vec<Vec<&SpecFile>> = Vec::new();
    if merged {
        for sid in &ids {
            groups.push(
                checker
                    .files
                    .iter()
                    .filter(|f| f.spec_id() == *sid)
                    .collect(),
            );
        }
    } else {
        for f in &selected {
            groups.push(vec![*f]);
        }
    }

    let commits = source_commits(checker, &groups, source_commit)?;

    let mut out = View::new();

    // Status map: root_idx + path -> StatusRow
    let mut status_map: HashMap<(usize, String), HashMap<String, &StatusRow>> = HashMap::new();
    for (f_idx, entry) in &checker.status {
        let mut rows = HashMap::new();
        for row in &entry.facts {
            rows.insert(row.key.clone(), row);
        }
        status_map.insert((*f_idx, entry.path.clone()), rows);
    }

    for group in &mut groups {
        group.sort_by_key(|f| {
            let root = &checker.roots[f.root_idx];
            (f.is_overlay(), root.rank, root.order, f.path.clone())
        });
        for file in group.iter() {
            crate::render_html::refuse_unsafe_fields(file)?;
        }

        let base = group[0];
        let base_id = base.spec_id();
        let base_kind = base.kind();

        if !out.lines.is_empty() {
            out.extend(vec!["Generated view:".to_string(), String::new()]);
        }
        out.extend(vec![
            format!("Generated by {}. Do not edit.", code("spec.py render")),
            String::new(),
            format!(
                "Canonical form {}; driver-lab {}.",
                code(crate::records::CANONICAL),
                escape(tool_commit.unwrap_or("unavailable"))
            ),
            String::new(),
        ]);

        for file in group.iter() {
            let root = &checker.roots[file.root_idx];
            let relative = file
                .path
                .strip_prefix(&root.given)
                .unwrap_or(&file.path)
                .to_string_lossy()
                .into_owned();
            let digest = "unavailable"; // Skipped hash reading
            out.extend(vec![
                format!(
                    "Source {}; commit {}; SHA256 {}.",
                    code(&format!("{}:{}", root.label(), relative)),
                    escape(
                        commits
                            .get(&root.given.canonicalize().unwrap_or(root.given.clone()))
                            .map(|s| s.as_str())
                            .unwrap_or("unavailable")
                    ),
                    code(digest)
                ),
                String::new(),
            ]);
        }

        if merged {
            let ctx_warnings: Vec<String> = checker
                .ordered_findings()
                .into_iter()
                .filter(|f| f.level == "warning" && f.message.starts_with("context root:"))
                .map(|f| format!("- {}: {}", code(&f.path), escape(&f.message)))
                .collect();
            if !ctx_warnings.is_empty() {
                out.extend(vec!["Context root warnings:".to_string(), String::new()]);
                out.extend(ctx_warnings);
                out.append(String::new());
            }
        }

        let name = base
            .data
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or(&base_id);
        out.heading(1, &escape(name));

        let mut triggers = Vec::new();
        if let Some(arr) = base.data.get("triggers").and_then(|v| v.as_array()) {
            for v in arr {
                if let Some(s) = v.as_str() {
                    triggers.push(escape(s));
                }
            }
        }
        out.extend(vec![
            format!(
                "{} · {} · triggers: {}",
                code(&base_id),
                escape(base_kind),
                triggers.join(", ")
            ),
            String::new(),
        ]);

        for key in &[
            "aliases",
            "not_triggers",
            "parts",
            "variant_of",
            "cache",
            "overlays",
        ] {
            if let Some(val) = base.data.get(*key) {
                out.extend(vec![
                    format!("{}: {}", escape(key), escape(&_value(val))),
                    String::new(),
                ]);
            }
        }

        // Check for Context (not facts)
        let mut has_context = false;
        for file in group.iter() {
            if file.data.get("orientation").is_some()
                || file.data.get("milestones").is_some()
                || file.data.get("notes").is_some()
            {
                has_context = true;
                break;
            }
        }

        if has_context {
            out.heading(2, "Context (not facts)");
            for (i, file) in group.iter().enumerate() {
                if file.data.get("orientation").is_some()
                    || file.data.get("milestones").is_some()
                    || file.data.get("notes").is_some()
                {
                    let root = &checker.roots[file.root_idx];
                    if file.is_overlay() {
                        out.heading(
                            3,
                            &format!(
                                "Overlay: {} ({})",
                                escape(root.layer.as_deref().unwrap_or("")),
                                escape(&root.label())
                            ),
                        );
                    }
                    if i != 0 && !file.is_overlay() {
                        out.extend(vec!["Context (not facts):".to_string(), String::new()]);
                    }
                    for key in &["orientation", "milestones", "notes"] {
                        if let Some(val) = file.data.get(*key).and_then(|v| v.as_str()) {
                            let mut cap = key.to_string();
                            if let Some(r) = cap.get_mut(0..1) {
                                r.make_ascii_uppercase();
                            }
                            _author(&mut out, val, &cap);
                        }
                    }
                }
            }
        }

        // Sections
        let target_kind = checker
            .files
            .iter()
            .find(|f| !f.is_overlay() && f.spec_id() == base_id)
            .map(|f| f.kind())
            .unwrap_or(base.kind());
        let sections = crate::speccheck::allowed_sections(target_kind);
        for section in sections {
            let mut has_section = false;
            for file in group.iter() {
                for (_, rec) in &file.records {
                    if rec.data.get("section").and_then(|v| v.as_str()) == Some(*section) {
                        has_section = true;
                        break;
                    }
                }
            }
            if !has_section {
                continue;
            }

            let mut cap = section.to_string();
            if let Some(r) = cap.get_mut(0..1) {
                r.make_ascii_uppercase();
            }
            out.heading(2, &cap);

            for file in group.iter() {
                let mut facts = Vec::new();
                for (_, rec) in &file.records {
                    if rec.data.get("section").and_then(|v| v.as_str()) == Some(*section) {
                        facts.push(rec);
                    }
                }
                if !facts.is_empty() && file.is_overlay() {
                    let root = &checker.roots[file.root_idx];
                    out.heading(
                        3,
                        &format!(
                            "Overlay: {} ({})",
                            escape(root.layer.as_deref().unwrap_or("")),
                            escape(&root.label())
                        ),
                    );
                }
                for rec in facts {
                    _fact(&mut out, checker, rec, file, &status_map, with_status);
                }
            }
        }

        for kind in &["instances", "variants"] {
            for file in group.iter() {
                let mut rows = Vec::new();
                for (_, rec) in &file.records {
                    if let Some(k) = rec.path.first().and_then(|p| match p {
                        crate::records::PathElem::Key(key) => Some(key),
                        _ => None,
                    }) {
                        if k == kind {
                            rows.push(rec);
                        }
                    }
                }
                if !rows.is_empty() {
                    let mut cap = kind.to_string();
                    if let Some(r) = cap.get_mut(0..1) {
                        r.make_ascii_uppercase();
                    }
                    let root = &checker.roots[file.root_idx];
                    out.heading(2, &format!("{}: {}", cap, escape(&root.label())));
                    for rec in rows {
                        _fact(&mut out, checker, rec, file, &status_map, with_status);
                    }
                }
            }
        }

        for file in group.iter() {
            if let Some(arr) = file.data.get("notices").and_then(|v| v.as_array()) {
                let root = &checker.roots[file.root_idx];
                out.heading(2, &format!("Source notices: {}", escape(&root.label())));
                for notice in arr {
                    let repo = notice.get("repo").and_then(|v| v.as_str()).unwrap_or("");
                    let path = notice.get("path").and_then(|v| v.as_str()).unwrap_or("");
                    let text = notice.get("text").and_then(|v| v.as_str()).unwrap_or("");
                    out.extend(vec![code(&format!("{}:{}", repo, path)), String::new()]);
                    _author(&mut out, text, "Notice");
                }
            }
        }
    }

    // skip _indexes, _coverage

    let mut view = out.lines.join("\n");
    view = view.trim_end().to_string();
    view.push('\n');

    specmd::check_view(&view, &out.expected)?;

    Ok(view)
}

fn escape_cell(value: &str) -> String {
    escape(value).replace('|', "\\|")
}

pub fn _fact(
    out: &mut View,
    _checker: &Checker,
    rec: &SpecRecord,
    file: &SpecFile,
    status_map: &HashMap<(usize, String), HashMap<String, &StatusRow>>,
    with_status: bool,
) {
    let data = &rec.data;
    let title = data
        .get("title")
        .or_else(|| data.get("name"))
        .or_else(|| {
            data.get("data")
                .and_then(|d| {
                    d.get("register")
                        .or_else(|| d.get("layout"))
                        .or_else(|| d.get("connector"))
                        .or_else(|| d.get("memory_map"))
                })
                .and_then(|x| x.get("name").or_else(|| x.get("designator")))
        })
        .and_then(|v| v.as_str())
        .unwrap_or(&rec.id);
    out.heading(4, &escape(title));

    if let Some(claim) = data.get("claim").and_then(|v| v.as_str()) {
        _author(out, claim, "Claim");
    } else {
        if let Some(reg) = data.get("data").and_then(|v| v.get("register")) {
            // Simplified register formatting
            let offset = reg.get("offset").and_then(|v| v.as_str()).unwrap_or("");
            let name = reg.get("name").and_then(|v| v.as_str()).unwrap_or("");
            out.extend(vec![
                format!("Register {} at {}.", code(name), code(offset)),
                String::new(),
            ]);
        }
        // dump keys
        if let Value::Object(obj) = data {
            for (key, value) in obj {
                if !["id", "support", "note", "todo", "title", "name", "data"]
                    .contains(&key.as_str())
                {
                    out.append(format!("- {}: {}", escape(key), escape(&_value(value))));
                }
            }
        }
        out.append(String::new());
    }
    if let Some(layout) = data.get("data").and_then(|v| v.get("layout")) {
        let name = layout.get("name").and_then(|v| v.as_str()).unwrap_or("");
        let size = layout.get("size").and_then(|v| v.as_i64()).unwrap_or(0);
        out.extend(vec![
            format!("Layout {} ({} B).", code(name), size),
            String::new(),
        ]);
    }
    if let Some(conn) = data.get("data").and_then(|v| v.get("connector")) {
        let cname = conn
            .get("designator")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let mut meta = Vec::new();
        for (label, key) in &[
            ("kind", "kind"),
            ("part", "part_number"),
            ("mating", "mating_part"),
            ("pitch", "pitch"),
        ] {
            if let Some(val) = conn.get(*key).and_then(|v| v.as_str()) {
                meta.push(format!("{}: {}", label, escape(val)));
            }
        }
        let header = if meta.is_empty() {
            format!("Connector {}.", code(cname))
        } else {
            format!("Connector {} ({}).", code(cname), meta.join(", "))
        };
        out.extend(vec![header, String::new()]);
        if let Some(pins) = conn.get("pins").and_then(|v| v.as_array()) {
            if !pins.is_empty() {
                out.append("| Pin | Signal | Direction | Level | Note |".to_string());
                out.append("| --- | --- | --- | --- | --- |".to_string());
                for p in pins {
                    let pin_str = p.get("pin").map(_value).unwrap_or_default();
                    let mut sig = p
                        .get("signal")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    let mut qualifiers = Vec::new();
                    if let Some(gpio) = p.get("gpio").and_then(|v| v.as_str()) {
                        qualifiers.push(format!("gpio: {}", gpio));
                    }
                    if let Some(ball) = p.get("ball").and_then(|v| v.as_str()) {
                        qualifiers.push(format!("ball: {}", ball));
                    }
                    if !qualifiers.is_empty() {
                        sig.push_str(&format!(" ({})", qualifiers.join(", ")));
                    }
                    let dir = p.get("direction").and_then(|v| v.as_str()).unwrap_or("");
                    let mut level = p
                        .get("level")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    if let Some(pull) = p.get("pull").and_then(|v| v.as_str()) {
                        if level.is_empty() {
                            level = pull.to_string();
                        } else {
                            level.push_str(&format!(" ({})", pull));
                        }
                    }
                    let note = p.get("note").and_then(|v| v.as_str()).unwrap_or("");
                    out.append(format!(
                        "| {} | {} | {} | {} | {} |",
                        code(&pin_str).replace('|', "\\|"),
                        escape_cell(&sig),
                        escape_cell(dir),
                        escape_cell(&level),
                        escape_cell(note)
                    ));
                }
                out.append(String::new());
            }
        }
    }
    if let Some(mm) = data.get("data").and_then(|v| v.get("memory_map")) {
        if let Some(mname) = mm.get("name").and_then(|v| v.as_str()) {
            out.extend(vec![format!("Memory map {}.", code(mname)), String::new()]);
        }
        if let Some(entries) = mm.get("regions").and_then(|v| v.as_array()) {
            if !entries.is_empty() {
                out.append("| Name | Variable | Base | Size | Purpose |".to_string());
                out.append("| --- | --- | --- | --- | --- |".to_string());
                for e in entries {
                    let rname = e.get("name").and_then(|v| v.as_str()).unwrap_or("");
                    let var = e.get("env_var").and_then(|v| v.as_str()).unwrap_or("");
                    let base = e.get("base").and_then(|v| v.as_str()).unwrap_or("");
                    let size = e.get("size").and_then(|v| v.as_str()).unwrap_or("");
                    let mut purpose = e
                        .get("purpose")
                        .or_else(|| e.get("note"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    if let Some(kind) = e.get("kind").and_then(|v| v.as_str()) {
                        if purpose.is_empty() {
                            purpose = kind.to_string();
                        } else {
                            purpose.push_str(&format!(" ({})", kind));
                        }
                    }
                    out.append(format!(
                        "| {} | {} | {} | {} | {} |",
                        escape_cell(rname),
                        escape_cell(var),
                        escape_cell(base),
                        escape_cell(size),
                        escape_cell(&purpose)
                    ));
                }
                out.append(String::new());
            }
        }
    }
    if let Some(qty) = data.get("data").and_then(|v| v.get("quantity")) {
        out.extend(vec![
            format!("Quantity: {}.", escape(&_value(qty))),
            String::new(),
        ]);
    }

    out.extend(vec!["Provenance (generated):".to_string(), String::new()]);

    if let Some(todo) = data.get("todo") {
        let check = todo.get("check").and_then(|v| v.as_str()).unwrap_or("");
        let text = todo.get("text").and_then(|v| v.as_str()).unwrap_or("");
        out.append(format!(
            "- TODO (verify on {}): {}",
            escape(check),
            escape(text)
        ));
        if let Some(method) = todo.get("method").and_then(|v| v.as_str()) {
            out.append(format!("- method: {}", escape(method)));
        }
    }

    let mut text = format!("- {}", code(&rec.full));
    if data.get("critical").is_some() {
        text.push_str(" · bring-up critical");
    }

    if with_status {
        if let Some(rows) =
            status_map.get(&(file.root_idx, file.path.to_string_lossy().into_owned()))
        {
            if let Some(row) = rows.get(&rec.id) {
                if let Some(verdict) = &row.verdict {
                    text.push_str(&format!(" · {} ...", escape(verdict))); // simplified date
                }
                text.push_str(&format!(" · {}", escape(&row.status)));
            }
        }
    }
    out.extend(vec![text, String::new()]);

    if let Some(req) = data.get("requirement").and_then(|v| v.as_str()) {
        out.extend(vec![format!("Requirement: {}", code(req)), String::new()]);
    }

    if let Some(note) = data.get("note").and_then(|v| v.as_str()) {
        _author(out, note, "Fact note");
    }
}

/// Executes `driver-lab render` (`spec.py:cmd_render`, `RT-7`, `RT-8`, `BF-GW-27`, `ENV-1`).
pub fn run_render_cmd(
    cli: &crate::Cli,
    args: &crate::RenderArgs,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> i32 {
    use crate::diagnostic::{visible_name, EXIT_DOMAIN_FAILURE, EXIT_OK, EXIT_USAGE_ERROR};
    use crate::RenderFormat;
    use serde_json::json;
    use std::collections::HashSet;

    let key = match args.format {
        RenderFormat::Md => "markdown",
        RenderFormat::Html | RenderFormat::Atlas => "html",
    };

    let emit_fail = |kind: &str,
                     code: i32,
                     msg: &str,
                     stdout: &mut dyn std::io::Write,
                     stderr: &mut dyn std::io::Write|
     -> i32 {
        if cli.json {
            let payload = json!({
                "ok": false,
                "error": kind,
                key: Value::Null,
                "findings": [{"message": msg}],
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
                _ => "error",
            };
            let _ = writeln!(stderr, "{}", visible_name(&format!("{label}: {msg}")));
        }
        code
    };

    if args.format == RenderFormat::Atlas && args.spec.is_none() {
        return emit_fail(
            "usage",
            EXIT_USAGE_ERROR,
            "--format atlas needs --spec ID: the board (or other spec) to center on",
            stdout,
            stderr,
        );
    }

    let mut roots: Vec<PathBuf> = args.targets.clone();
    if let Some(ref r) = args.root {
        if !roots.contains(r) {
            roots.push(r.clone());
        }
    }
    if roots.is_empty() {
        return emit_fail(
            "usage",
            EXIT_USAGE_ERROR,
            "at least one root directory is required",
            stdout,
            stderr,
        );
    }

    let public_skills: HashSet<String> = args.public_skills.iter().cloned().collect();
    let schemas = crate::records::load_schemas();
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
        let kind = if code == EXIT_USAGE_ERROR {
            "usage"
        } else {
            "precondition"
        };
        return emit_fail(kind, code, &msg, stdout, stderr);
    }

    let merged = args.merged || args.self_contained;
    if merged {
        for r_idx in 0..checker.roots.len() {
            if checker.roots[r_idx].context && !checker.roots[r_idx].untrusted.is_empty() {
                let marker_path = checker.roots[r_idx].given.join(crate::records::MARKER);
                let marker_data = checker.roots[r_idx].marker.clone();
                checker.add_where(
                    &marker_path,
                    Some(r_idx),
                    marker_data.as_ref(),
                    &[],
                    "cannot render merged input: context root does not check clean",
                    "error",
                    false,
                    false,
                    false,
                );
            }
        }
    }

    let ordered = checker.ordered_findings();
    let has_errors = ordered.iter().any(|f| f.level == "error");
    if has_errors {
        if cli.json {
            let payload = json!({
                "ok": false,
                key: Value::Null,
                "findings": ordered,
            });
            let _ = writeln!(
                stdout,
                "{}",
                serde_json::to_string(&payload).unwrap_or_default()
            );
        } else {
            for f in &ordered {
                let _ = writeln!(stdout, "{}", visible_name(&f.to_string()));
            }
        }
        return EXIT_DOMAIN_FAILURE;
    }

    let joined_commits = args.source_commits.join("\n");
    let source_commit = if args.source_commits.is_empty() {
        None
    } else {
        Some(joined_commits.as_str())
    };
    let tool_commit = args.tool_commit.as_deref();
    let rendered = match args.format {
        RenderFormat::Md => render(
            &checker,
            args.spec.as_deref(),
            merged,
            args.with_status,
            source_commit,
            tool_commit,
        ),
        RenderFormat::Html => crate::render_html::render(
            &checker,
            args.spec.as_deref(),
            merged,
            args.with_status,
            source_commit,
            tool_commit,
        ),
        RenderFormat::Atlas => crate::explorer::atlas::page(
            &checker,
            args.spec.as_deref().unwrap_or(""),
            merged,
            &args.source_commits,
            tool_commit.unwrap_or("unavailable"),
        ),
    };

    match rendered {
        Ok(view) => {
            if let Some(ref out_path) = args.out {
                if let Err(e) = std::fs::write(out_path, &view) {
                    return emit_fail(
                        "precondition",
                        crate::diagnostic::EXIT_SANDBOX_ERROR,
                        &e.to_string(),
                        stdout,
                        stderr,
                    );
                }
            }
            if cli.json {
                let payload = json!({
                    "ok": true,
                    key: view,
                    "findings": ordered,
                });
                let _ = writeln!(
                    stdout,
                    "{}",
                    serde_json::to_string(&payload).unwrap_or_default()
                );
            } else if args.out.is_none() {
                let _ = writeln!(stdout, "{}", view.trim_end_matches('\n'));
            }
            EXIT_OK
        }
        Err(msg) => {
            if msg.contains("no checked spec matches --spec")
                || msg.contains("no spec ")
                || msg.contains("no specs to render")
                || msg.contains("unknown spec")
                || msg.contains("--source-commit")
                || msg.contains("commit must be 40 lowercase hex")
            {
                return emit_fail("usage", EXIT_USAGE_ERROR, &msg, stdout, stderr);
            }
            if cli.json {
                let payload = json!({
                    "ok": false,
                    key: Value::Null,
                    "findings": [{"message": msg}],
                });
                let _ = writeln!(
                    stdout,
                    "{}",
                    serde_json::to_string(&payload).unwrap_or_default()
                );
            } else {
                let _ = writeln!(stdout, "{}", visible_name(&msg));
            }
            EXIT_DOMAIN_FAILURE
        }
    }
}
