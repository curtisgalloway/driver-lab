// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Static spec format viewer and atlas generator.
use crate::records::{Checker, SpecFile, SpecRecord, StatusRow};
use serde_json::Value;
use std::collections::HashMap;

use comrak::nodes::{AstNode, NodeValue};
use comrak::{parse_document, Arena, Options};

pub fn escape_html(text: &str, quote: bool) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '&' => out.push_str("&amp;"),
            '"' if quote => out.push_str("&quot;"),
            '\'' if quote => out.push_str("&#x27;"),
            _ => out.push(c),
        }
    }
    out
}

pub fn allowed_link(url: &str) -> bool {
    url.starts_with("http://") || url.starts_with("https://") || url.starts_with('#')
}

pub fn link(url: &str, label: &str) -> String {
    if !allowed_link(url) {
        return escape_html(label, false);
    }
    format!(
        "<a href=\"{}\">{}</a>",
        escape_html(url, true),
        escape_html(label, false)
    )
}

/// No author string reaches an HTML sink unescaped.
pub fn author(text: &str) -> String {
    let arena = Arena::new();
    let root = parse_document(&arena, text, &Options::default());
    let mut out = String::new();
    let mut links_stack = Vec::new();

    fn emit<'a>(node: &'a AstNode<'a>, out: &mut String, links: &mut Vec<bool>) {
        let ast = node.data.borrow();
        match &ast.value {
            NodeValue::Document
            | NodeValue::BlockQuote
            | NodeValue::List(_)
            | NodeValue::Item(_)
            | NodeValue::Paragraph => {
                let tag = match &ast.value {
                    NodeValue::BlockQuote => "blockquote",
                    NodeValue::List(l) => {
                        if l.list_type == comrak::nodes::ListType::Ordered {
                            "ol"
                        } else {
                            "ul"
                        }
                    }
                    NodeValue::Item(_) => "li",
                    NodeValue::Paragraph => "p",
                    _ => "",
                };
                if !tag.is_empty() {
                    out.push_str(&format!("<{}>", tag));
                }
                for child in node.children() {
                    emit(child, out, links);
                }
                if !tag.is_empty() {
                    out.push_str(&format!("</{}>", tag));
                }
            }
            NodeValue::Text(t) => {
                out.push_str(&escape_html(t, false));
            }
            NodeValue::HtmlInline(h) => {
                // HTML disabled/escaped defensively
                out.push_str(&escape_html(h, false));
            }
            NodeValue::HtmlBlock(h) => {
                out.push_str(&escape_html(&h.literal, false));
            }
            NodeValue::Code(c) => {
                out.push_str("<code>");
                out.push_str(&escape_html(&c.literal, false));
                out.push_str("</code>");
            }
            NodeValue::CodeBlock(c) => {
                out.push_str("<pre><code>");
                out.push_str(&escape_html(&c.literal, false));
                out.push_str("</code></pre>");
            }
            NodeValue::Emph => {
                out.push_str("<em>");
                for child in node.children() {
                    emit(child, out, links);
                }
                out.push_str("</em>");
            }
            NodeValue::Strong => {
                out.push_str("<strong>");
                for child in node.children() {
                    emit(child, out, links);
                }
                out.push_str("</strong>");
            }
            NodeValue::Image(img) => {
                let allowed = links.is_empty() || !links.iter().any(|&x| x);
                let mut label = String::new();
                for child in node.children() {
                    emit(child, &mut label, links);
                }
                if allowed && allowed_link(&img.url) {
                    out.push_str(&format!(
                        "<a href=\"{}\">{}</a>",
                        escape_html(&img.url, true),
                        label
                    ));
                } else {
                    out.push_str(&label);
                }
            }
            NodeValue::Link(l) => {
                let allowed =
                    (links.is_empty() || !links.iter().any(|&x| x)) && allowed_link(&l.url);
                if allowed {
                    out.push_str(&format!("<a href=\"{}\">", escape_html(&l.url, true)));
                } else {
                    out.push_str("<span>");
                }
                links.push(allowed);
                for child in node.children() {
                    emit(child, out, links);
                }
                if links.pop().unwrap_or(false) {
                    out.push_str("</a>");
                } else {
                    out.push_str("</span>");
                }
            }
            NodeValue::SoftBreak => out.push('\n'),
            NodeValue::LineBreak => out.push_str("<br>"),
            NodeValue::ThematicBreak => out.push_str("<hr>"),
            _ => {
                for child in node.children() {
                    emit(child, out, links);
                }
            }
        }
    }

    emit(root, &mut out, &mut links_stack);
    out
}

/// Repeats every author-field safety/containment check on a spec and its verification record,
/// independently of a prior `check` pass (`render_html.py:refuse_unsafe_fields`).
pub fn refuse_unsafe_fields(file: &SpecFile) -> Result<(), String> {
    let mut values = crate::specmd::author_fields(&file.data);
    if let Some(ref rec_loaded) = file.record_loaded {
        if let Some(ref rec_data) = rec_loaded.data {
            values.extend(crate::specmd::author_fields(rec_data));
        }
    }
    for field in values {
        let bad: Vec<_> = crate::specmd::findings(&field.value, false)
            .into_iter()
            .filter(|f| f.level == crate::diagnostic::Level::Error)
            .collect();
        if let Some(first) = bad.first() {
            let elems: Vec<crate::records::PathElem> = field
                .path
                .iter()
                .map(|seg| match seg {
                    crate::yaml_strict::PathSegment::Key(k) => {
                        crate::records::PathElem::Key(k.clone())
                    }
                    crate::yaml_strict::PathSegment::Index(i) => {
                        crate::records::PathElem::Index(*i)
                    }
                })
                .collect();
            return Err(format!(
                "{}: {}: {}",
                file.spec_id(),
                crate::records::format_where(&elems),
                first.message
            ));
        }
    }
    Ok(())
}

pub fn render_atlas_checker(checker: &Checker, spec_id: &str) -> Result<String, String> {
    crate::explorer::atlas::page(checker, spec_id, false, &[], "unavailable")
}

pub fn literal(value: &str) -> String {
    crate::render_html::escape_html(value, true)
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

    let commits = crate::render_md::source_commits(checker, &groups, source_commit)?;

    for group in &mut groups {
        group.sort_by_key(|f| {
            let root = &checker.roots[f.root_idx];
            (f.is_overlay(), root.rank, root.order, f.path.clone())
        });
        for file in group.iter() {
            let root = &checker.roots[file.root_idx];
            if root.context && !root.untrusted.is_empty() {
                return Err(
                    "cannot render merged input: context root does not check clean".to_string(),
                );
            }
            refuse_unsafe_fields(file)?;
        }
    }

    let mut out = Vec::new();
    let css = include_str!("../skills/spec-format/scripts/viewer.css");

    out.push("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">".to_string());
    out.push(
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">".to_string(),
    );
    out.push(format!(
        "<title>Spec viewer</title><style>{}</style></head><body><main>",
        css
    ));

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

        let base = group[0];
        let base_id = base.spec_id();
        let base_kind = base.kind();

        out.push("<section>".to_string());
        out.push("<p>Generated by spec.py render. Do not edit.</p>".to_string());
        out.push(format!(
            "<p>Canonical form {}; hwspecs {}.</p>",
            literal(crate::records::CANONICAL),
            literal(tool_commit.unwrap_or("unavailable"))
        ));

        for file in group.iter() {
            let root = &checker.roots[file.root_idx];
            let relative = file
                .path
                .strip_prefix(&root.given)
                .unwrap_or(&file.path)
                .to_string_lossy()
                .into_owned();
            let digest = "unavailable"; // Skipped hash reading
            out.push(format!(
                "<p>Source {}; commit {}; SHA256 {}.</p>",
                literal(&format!("{}:{}", root.label(), relative)),
                literal(
                    commits
                        .get(&root.given.canonicalize().unwrap_or(root.given.clone()))
                        .map(|s| s.as_str())
                        .unwrap_or("unavailable")
                ),
                digest
            ));
        }

        if merged {
            let ctx_warnings: Vec<String> = checker
                .ordered_findings()
                .into_iter()
                .filter(|f| f.level == "warning" && f.message.starts_with("context root:"))
                .map(|f| {
                    format!(
                        "<li><code>{}</code>: {}</li>",
                        literal(&f.path),
                        literal(&f.message)
                    )
                })
                .collect();
            if !ctx_warnings.is_empty() {
                out.push(format!(
                    "<div class=\"context-warnings\"><p>Context root warnings:</p><ul>{}</ul></div>",
                    ctx_warnings.join("")
                ));
            }
        }

        let name = base
            .data
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or(&base_id);
        out.push(format!("<h1>{}</h1>", literal(name)));

        let mut triggers = Vec::new();
        if let Some(arr) = base.data.get("triggers").and_then(|v| v.as_array()) {
            for v in arr {
                if let Some(s) = v.as_str() {
                    triggers.push(literal(s));
                }
            }
        }
        out.push(format!(
            "<p>{} &middot; {} &middot; triggers: {}</p>",
            literal(&base_id),
            literal(base_kind),
            triggers.join(", ")
        ));

        for key in &[
            "aliases",
            "not_triggers",
            "parts",
            "variant_of",
            "cache",
            "overlays",
        ] {
            if let Some(val) = base.data.get(*key) {
                out.push(format!(
                    "<p>{}: {}</p>",
                    literal(key),
                    literal(&crate::render_md::_value(val))
                ));
            }
        }

        // Skip resources and generated (same as render_md)

        let mut context_keys = false;
        for file in group.iter() {
            for key in &["orientation", "milestones", "notes"] {
                if file.data.get(*key).is_some() {
                    context_keys = true;
                }
            }
        }
        if context_keys {
            out.push("<section class=\"context\"><h2>Context (not facts)</h2>".to_string());
            for file in group.iter() {
                for key in &["orientation", "milestones", "notes"] {
                    if let Some(val) = file.data.get(*key).and_then(|v| v.as_str()) {
                        let cap = {
                            let mut c = key.to_string();
                            if let Some(r) = c.get_mut(0..1) {
                                r.make_ascii_uppercase();
                            }
                            c
                        };
                        out.push(format!(
                            "<div class=\"author\"><p>{} (author text)</p>{}</div>",
                            literal(&cap),
                            crate::render_html::author(val)
                        ));
                    }
                }
            }
            out.push("</section>".to_string());
        }

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
                    if rec
                        .data
                        .get("section")
                        .and_then(|v| v.as_str())
                        .unwrap_or("facts")
                        == *section
                    {
                        has_section = true;
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
            out.push(format!("<section><h2>{}</h2>", literal(&cap)));

            for file in group.iter() {
                let mut rows = Vec::new();
                for (_, rec) in &file.records {
                    if rec
                        .data
                        .get("section")
                        .and_then(|v| v.as_str())
                        .unwrap_or("facts")
                        == *section
                    {
                        rows.push(rec);
                    }
                }
                if !rows.is_empty() && file.is_overlay() {
                    let root = &checker.roots[file.root_idx];
                    out.push(format!(
                        "<h3>Overlay: {} ({})</h3>",
                        literal(root.layer.as_deref().unwrap_or("")),
                        literal(&root.label())
                    ));
                }
                for rec in rows {
                    _fact(&mut out, checker, rec, file, &status_map, with_status);
                }
            }
            out.push("</section>".to_string());
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
                    out.push(format!(
                        "<section><h2>{}: {}</h2>",
                        literal(&cap),
                        literal(&root.label())
                    ));
                    for rec in rows {
                        _fact(&mut out, checker, rec, file, &status_map, with_status);
                    }
                    out.push("</section>".to_string());
                }
            }
        }

        for file in group.iter() {
            if let Some(arr) = file.data.get("notices").and_then(|v| v.as_array()) {
                for notice in arr {
                    let repo = notice.get("repo").and_then(|v| v.as_str()).unwrap_or("");
                    let path = notice.get("path").and_then(|v| v.as_str()).unwrap_or("");
                    let text = notice.get("text").and_then(|v| v.as_str()).unwrap_or("");
                    out.push(format!(
                        "<section><h2>Source notice: {}</h2><pre>{}</pre></section>",
                        literal(&format!("{}:{}", repo, path)),
                        literal(text)
                    ));
                }
            }
        }
        out.push("</section>".to_string());
    }

    out.push("</main></body></html>".to_string());
    let mut view = out.join("\n");
    view.push('\n');
    Ok(view)
}

pub fn _fact(
    out: &mut Vec<String>,
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
    out.push(format!(
        "<article class=\"fact\" id=\"{}\"><header><h4>{}</h4></header><div class=\"claim\">",
        literal(&rec.full),
        literal(title)
    ));

    if let Some(claim) = data.get("claim").and_then(|v| v.as_str()) {
        out.push(crate::render_html::author(claim));
    } else {
        out.push("<dl>".to_string());
        if let Some(reg) = data.get("data").and_then(|v| v.get("register")) {
            let offset = reg.get("offset").and_then(|v| v.as_str()).unwrap_or("");
            let name = reg.get("name").and_then(|v| v.as_str()).unwrap_or("");
            out.push(format!(
                "<dt>Register {}</dt><dd>at {}</dd>",
                literal(name),
                literal(offset)
            ));
        }
        if let Value::Object(obj) = data {
            for (key, value) in obj {
                if !["id", "support", "note", "todo", "title", "name", "data"]
                    .contains(&key.as_str())
                {
                    out.push(format!(
                        "<dt>{}</dt><dd>{}</dd>",
                        literal(key),
                        literal(&crate::render_md::_value(value))
                    ));
                }
            }
        }
        out.push("</dl>".to_string());
    }
    if let Some(layout) = data.get("data").and_then(|v| v.get("layout")) {
        let name = layout.get("name").and_then(|v| v.as_str()).unwrap_or("");
        let size = layout.get("size").and_then(|v| v.as_i64()).unwrap_or(0);
        out.push(format!(
            "<p>Layout <code>{}</code> ({} B).</p>",
            literal(name),
            size
        ));
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
                meta.push(format!("{}: {}", label, literal(val)));
            }
        }
        if meta.is_empty() {
            out.push(format!("<p>Connector <code>{}</code>.</p>", literal(cname)));
        } else {
            out.push(format!(
                "<p>Connector <code>{}</code> ({}).</p>",
                literal(cname),
                meta.join(", ")
            ));
        }
        if let Some(pins) = conn.get("pins").and_then(|v| v.as_array()) {
            if !pins.is_empty() {
                out.push("<table class=\"connector\"><thead><tr><th>Pin</th><th>Signal</th><th>Direction</th><th>Level</th><th>Note</th></tr></thead><tbody>".to_string());
                for p in pins {
                    let pin_str = p
                        .get("pin")
                        .map(crate::render_md::_value)
                        .unwrap_or_default();
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
                    out.push(format!(
                        "<tr><td><code>{}</code></td><td><code>{}</code></td><td>{}</td><td>{}</td><td>{}</td></tr>",
                        literal(&pin_str),
                        literal(&sig),
                        literal(dir),
                        literal(&level),
                        literal(note)
                    ));
                }
                out.push("</tbody></table>".to_string());
            }
        }
    }
    if let Some(mm) = data.get("data").and_then(|v| v.get("memory_map")) {
        if let Some(mname) = mm.get("name").and_then(|v| v.as_str()) {
            out.push(format!(
                "<p>Memory map <code>{}</code>.</p>",
                literal(mname)
            ));
        }
        if let Some(entries) = mm.get("regions").and_then(|v| v.as_array()) {
            if !entries.is_empty() {
                out.push("<table class=\"memory-map\"><thead><tr><th>Name</th><th>Variable</th><th>Base</th><th>Size</th><th>Purpose</th></tr></thead><tbody>".to_string());
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
                    out.push(format!(
                        "<tr><td><code>{}</code></td><td><code>{}</code></td><td><code>{}</code></td><td><code>{}</code></td><td>{}</td></tr>",
                        literal(rname),
                        literal(var),
                        literal(base),
                        literal(size),
                        literal(&purpose)
                    ));
                }
                out.push("</tbody></table>".to_string());
            }
        }
    }
    if let Some(qty) = data.get("data").and_then(|v| v.get("quantity")) {
        out.push(format!(
            "<p>Quantity: {}.</p>",
            literal(&crate::render_md::_value(qty))
        ));
    }
    out.push("</div><div class=\"provenance\">".to_string());

    if let Some(todo) = data.get("todo") {
        let check = todo.get("check").and_then(|v| v.as_str()).unwrap_or("");
        let text = todo.get("text").and_then(|v| v.as_str()).unwrap_or("");
        out.push(format!(
            "<span class=\"badge todo\">verify on {}</span><p>{}</p>",
            literal(check),
            literal(text)
        ));
        if let Some(method) = todo.get("method").and_then(|v| v.as_str()) {
            out.push(format!("<p>Method: {}</p>", literal(method)));
        }
    }

    let mut text = format!("<code>{}</code>", literal(&rec.full));
    if data.get("critical").is_some() {
        text.push_str(" &middot; bring-up critical");
    }

    if with_status {
        if let Some(rows) =
            status_map.get(&(file.root_idx, file.path.to_string_lossy().into_owned()))
        {
            if let Some(row) = rows.get(&rec.id) {
                if let Some(verdict) = &row.verdict {
                    text.push_str(&format!(" &middot; {} ...", literal(verdict)));
                }
                text.push_str(&format!(" &middot; {}", literal(&row.status)));
            }
        }
    }
    out.push(format!("<p>{}</p>", text));

    if let Some(req) = data.get("requirement").and_then(|v| v.as_str()) {
        out.push(format!(
            "<span class=\"badge requirement\">{}</span>",
            literal(req)
        ));
    }

    out.push("</div>".to_string());

    if let Some(note) = data.get("note").and_then(|v| v.as_str()) {
        out.push(format!(
            "<div class=\"author\"><p>Fact note (author text)</p>{}</div>",
            crate::render_html::author(note)
        ));
    }
    out.push("</article>".to_string());
}
