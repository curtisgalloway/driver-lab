// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Interactive spec explorer and topology atlas generator (`explorer.py` and `atlas.py`, `RT-8`).

use crate::records::{Checker, PathElem, SpecFile, SpecRecord, StatusRow};
use crate::render_html;
use crate::render_md;
use crate::specmd;
use comrak::nodes::{AstNode, NodeValue};
use comrak::{parse_document, Arena, Options};
use regex::Regex;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::sync::OnceLock;
use unicode_normalization::UnicodeNormalization;

/// Format version of `anchors.json` (`explorer.py:ANCHORS_FORMAT`).
pub const ANCHORS_FORMAT: i64 = 1;

fn anchor_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[A-Za-z0-9._-]+$").unwrap())
}

fn blob_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/blob/([0-9a-f]{40})/(.+)$",
        )
        .unwrap()
    })
}

fn wiki_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/wiki/([A-Za-z0-9_.-]+)$",
        )
        .unwrap()
    })
}

fn number_prefix_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[0-9]+(?:\.[0-9]+)*[.)]?\s+").unwrap())
}

/// Recursively sorts all JSON object keys lexicographically so serialization is deterministic
/// even when `serde_json`'s `preserve_order` feature is active.
#[must_use]
pub fn sort_json_keys(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut sorted: BTreeMap<String, Value> = BTreeMap::new();
            for (k, v) in map {
                sorted.insert(k.clone(), sort_json_keys(v));
            }
            let mut out = Map::with_capacity(sorted.len());
            for (k, v) in sorted {
                out.insert(k, v);
            }
            Value::Object(out)
        }
        Value::Array(arr) => Value::Array(arr.iter().map(sort_json_keys).collect()),
        other => other.clone(),
    }
}

fn strip_html_tags(s: &str) -> String {
    static TAG_RE: OnceLock<Regex> = OnceLock::new();
    let re = TAG_RE.get_or_init(|| Regex::new(r"<[^>]*>").unwrap());
    decode_html_entities(&re.replace_all(s, ""))
}

/// Strips CommonMark syntax and HTML tags from `text` down to whitespace-collapsed plain text
/// for search (`explorer.py:plain`).
#[must_use]
pub fn plain(text: &str) -> String {
    let arena = Arena::new();
    let root = parse_document(&arena, text, &Options::default());
    let mut parts = Vec::new();
    fn walk<'a>(node: &'a AstNode<'a>, parts: &mut Vec<String>) {
        let ast = node.data.borrow();
        match &ast.value {
            NodeValue::Text(t) => parts.push(t.clone()),
            NodeValue::Code(c) => parts.push(c.literal.clone()),
            NodeValue::CodeBlock(c) => {
                parts.push(" ".to_string());
                parts.push(c.literal.clone());
                parts.push(" ".to_string());
            }
            NodeValue::SoftBreak | NodeValue::LineBreak => parts.push(" ".to_string()),
            NodeValue::HtmlInline(h) => parts.push(strip_html_tags(h)),
            NodeValue::HtmlBlock(h) => {
                parts.push(" ".to_string());
                parts.push(strip_html_tags(&h.literal));
                parts.push(" ".to_string());
            }
            NodeValue::Paragraph | NodeValue::Heading(_) | NodeValue::Item(_) => {
                for child in node.children() {
                    walk(child, parts);
                }
                parts.push(" ".to_string());
            }
            _ => {
                for child in node.children() {
                    walk(child, parts);
                }
            }
        }
    }
    walk(root, &mut parts);
    parts
        .join("")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

/// Normalizes a heading string for matching: Unicode NFC, collapsed whitespace, case-folded,
/// and leading section numbers (`"2.1 "` / `"2) "`) stripped (`explorer.py:heading_key`).
#[must_use]
pub fn heading_key(text: &str) -> String {
    let collapsed = text.split_whitespace().collect::<Vec<_>>().join(" ");
    let norm: String = collapsed.nfc().collect::<String>().to_lowercase();
    let stripped = number_prefix_re().replace(&norm, "").into_owned();
    if stripped.is_empty() {
        norm
    } else {
        stripped
    }
}

/// Validates and normalizes an HTML anchor fragment (`explorer.py:Headings._clean`).
#[must_use]
pub fn clean_anchor(raw: &str) -> Option<String> {
    let without_hash = raw.strip_prefix('#').unwrap_or(raw);
    let without_prefix = without_hash
        .strip_prefix("user-content-")
        .unwrap_or(without_hash);
    if !without_prefix.is_empty() && anchor_re().is_match(without_prefix) {
        Some(without_prefix.to_string())
    } else {
        None
    }
}

fn decode_html_entities(s: &str) -> String {
    s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&#x27;", "'")
}

fn parse_tag_attrs(tag_body: &str) -> HashMap<String, String> {
    static ATTR_RE: OnceLock<Regex> = OnceLock::new();
    let re = ATTR_RE.get_or_init(|| {
        Regex::new(r#"([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))"#)
            .unwrap()
    });
    let mut attrs = HashMap::new();
    for caps in re.captures_iter(tag_body) {
        let key = caps.get(1).unwrap().as_str().to_ascii_lowercase();
        let val = caps
            .get(2)
            .or_else(|| caps.get(3))
            .or_else(|| caps.get(4))
            .map(|m| decode_html_entities(m.as_str()))
            .unwrap_or_default();
        attrs.insert(key, val);
    }
    attrs
}

/// Extracts `{heading_key: anchor_fragment}` from GitHub-rendered HTML (`explorer.py:parse_headings`).
///
/// Supports both GitHub heading shapes:
/// 1. `<div class="markdown-heading"><h2 class="heading-element">...</h2><a id="user-content-..." href="#..."></a></div>`
/// 2. `<h2><a id="user-content-..." class="anchor" href="#..."></a>...</h2>`
///
/// First occurrence of a normalized heading key wins. External `<a href="https://...">` links
/// inside headings are ignored.
#[must_use]
pub fn parse_headings(html_text: &str) -> BTreeMap<String, String> {
    let mut found: BTreeMap<String, String> = BTreeMap::new();
    let mut current_tag: Option<String> = None;
    let mut current_text = String::new();
    let mut current_anchor: Option<String> = None;
    let mut pending_text: Option<String> = None;

    let mut record = |text: &str, anchor: Option<String>| {
        if let Some(a) = anchor {
            let key = heading_key(text);
            if !key.is_empty() {
                found.entry(key).or_insert(a);
            }
        }
    };

    let bytes = html_text.as_bytes();
    let mut i = 0usize;
    while i < bytes.len() {
        if bytes[i] == b'<' {
            if let Some(rel_end) = html_text[i..].find('>') {
                let tag_raw = &html_text[i + 1..i + rel_end];
                i += rel_end + 1;
                let trimmed = tag_raw.trim();
                if trimmed.starts_with('!') || trimmed.starts_with('?') {
                    continue;
                }
                if let Some(close_rest) = trimmed.strip_prefix('/') {
                    let close_name = close_rest
                        .split_whitespace()
                        .next()
                        .unwrap_or("")
                        .to_ascii_lowercase();
                    if current_tag.as_deref() == Some(close_name.as_str()) {
                        if current_anchor.is_some() {
                            let anch = current_anchor.take();
                            record(&current_text, anch);
                            pending_text = None;
                        } else {
                            pending_text = Some(current_text.clone());
                        }
                        current_tag = None;
                    } else if matches!(close_name.as_str(), "div" | "section" | "article" | "main")
                    {
                        pending_text = None;
                    }
                } else {
                    let open_name = trimmed
                        .split(|c: char| c.is_whitespace() || c == '/')
                        .next()
                        .unwrap_or("")
                        .to_ascii_lowercase();
                    let attrs = parse_tag_attrs(trimmed);
                    if matches!(open_name.as_str(), "h1" | "h2" | "h3" | "h4" | "h5" | "h6") {
                        current_tag = Some(open_name);
                        current_text.clear();
                        current_anchor = attrs.get("id").and_then(|id| clean_anchor(id));
                        pending_text = None;
                    } else if open_name == "a"
                        && (current_tag.is_some() || pending_text.is_some())
                        && current_anchor.is_none()
                    {
                        if let Some(href) = attrs.get("href") {
                            if !href.starts_with('#') {
                                continue;
                            }
                        }
                        let raw_target = attrs
                            .get("href")
                            .or_else(|| attrs.get("id"))
                            .map(String::as_str)
                            .unwrap_or("");
                        let cleaned = clean_anchor(raw_target);
                        if let Some(pt) = pending_text.take() {
                            record(&pt, cleaned);
                        } else {
                            current_anchor = cleaned;
                        }
                    } else if current_tag.is_none()
                        && matches!(
                            open_name.as_str(),
                            "p" | "ul" | "ol" | "table" | "pre" | "blockquote" | "hr"
                        )
                    {
                        pending_text = None;
                    }
                }
                continue;
            }
        }
        let next_lt = html_text[i..]
            .find('<')
            .map(|off| i + off)
            .unwrap_or(bytes.len());
        if current_tag.is_some() {
            current_text.push_str(&decode_html_entities(&html_text[i..next_lt]));
        }
        i = next_lt;
    }

    found
}

fn percent_encode_path(path: &str) -> String {
    let mut out = String::with_capacity(path.len());
    for b in path.bytes() {
        if b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.' | b'~' | b'/') {
            out.push(b as char);
        } else {
            out.push_str(&format!("%{:02X}", b));
        }
    }
    out
}

/// Maps a document URL to `(fetch_target_url, accept_header)` if and only if it is a
/// commit-pinned GitHub blob URL (`40` lowercase hex SHA) or a GitHub wiki page URL
/// without dot-segment traversal (`explorer.py:fetch_url`).
#[must_use]
pub fn fetch_url(url: &str) -> Option<(String, String)> {
    if let Some(caps) = blob_re().captures(url) {
        let owner = caps.get(1)?.as_str();
        let repo = caps.get(2)?.as_str();
        let commit = caps.get(3)?.as_str();
        let path = caps.get(4)?.as_str();
        if path.split('/').any(|seg| matches!(seg, "" | "." | "..")) {
            return None;
        }
        let encoded = percent_encode_path(path);
        return Some((
            format!("https://api.github.com/repos/{owner}/{repo}/contents/{encoded}?ref={commit}"),
            "application/vnd.github.html+json".to_string(),
        ));
    }
    if let Some(caps) = wiki_re().captures(url) {
        let page = caps.get(3)?.as_str();
        if matches!(page, "." | "..") {
            return None;
        }
        return Some((url.to_string(), "text/html".to_string()));
    }
    None
}

/// Builds request headers for `target` and `accept`, sending `Authorization: Bearer <token>`
/// ONLY when `target` has hostname `api.github.com` (`explorer.py:_request_headers`).
#[must_use]
pub fn request_headers(
    target: &str,
    accept: &str,
    env: &HashMap<String, String>,
) -> BTreeMap<String, String> {
    let mut headers = BTreeMap::new();
    headers.insert("Accept".to_string(), accept.to_string());
    headers.insert(
        "User-Agent".to_string(),
        "hwspecs-spec-explorer".to_string(),
    );
    let token = env
        .get("GITHUB_TOKEN")
        .or_else(|| env.get("GH_TOKEN"))
        .filter(|s| !s.is_empty());
    if let Some(tok) = token {
        if target.starts_with("https://api.github.com/") || target == "https://api.github.com" {
            headers.insert("Authorization".to_string(), format!("Bearer {tok}"));
        }
    }
    headers
}

/// Fetches a document's rendered HTML without following redirects (`explorer.py:_fetch`).
pub fn fetch_html(url: &str) -> Result<String, String> {
    let Some((target, accept)) = fetch_url(url) else {
        return Err("URL is not a commit-pinned GitHub blob or GitHub wiki page".to_string());
    };
    let env_map: HashMap<String, String> = std::env::vars().collect();
    let headers = request_headers(&target, &accept, &env_map);
    let agent = ureq::AgentBuilder::new()
        .redirects(0)
        .timeout(std::time::Duration::from_secs(15))
        .build();
    let mut req = agent.get(&target);
    for (k, v) in &headers {
        req = req.set(k, v);
    }
    match req.call() {
        Ok(resp) => {
            let status = resp.status();
            if status != 200 {
                return Err(format!("HTTP {status}"));
            }
            let mut body = Vec::new();
            use std::io::Read;
            resp.into_reader()
                .take((5 * 1024 * 1024 + 1) as u64)
                .read_to_end(&mut body)
                .map_err(|e| e.to_string())?;
            if body.len() > 5 * 1024 * 1024 {
                return Err("document exceeds 5 MiB".to_string());
            }
            Ok(String::from_utf8_lossy(&body).into_owned())
        }
        Err(ureq::Error::Status(code, _)) => Err(format!("HTTP {code}")),
        Err(e) => Err(e.to_string()),
    }
}

/// Collects `{base_doc_url: {cited_headings}}` across all non-context files in `checker`
/// (`explorer.py:wanted`).
#[must_use]
pub fn wanted(checker: &Checker) -> BTreeMap<String, BTreeSet<String>> {
    let mut urls: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for file in &checker.files {
        let root = &checker.roots[file.root_idx];
        if root.context {
            continue;
        }
        for (_, rec) in &file.records {
            for (entry, _) in crate::records::supports(&rec.data, &rec.path) {
                let Some(doc_name) = entry.get("doc").and_then(Value::as_str) else {
                    continue;
                };
                let Some((doc, _)) = file.documents.get(doc_name) else {
                    continue;
                };
                let raw_url = doc.get("url").and_then(Value::as_str).unwrap_or("");
                if !specmd::allowed_link(raw_url) {
                    continue;
                }
                let base_url = raw_url.split('#').next().unwrap_or("");
                if let Some(at_arr) = entry.get("at").and_then(Value::as_array) {
                    for at in at_arr {
                        if let Some(heading) = at.get("heading").and_then(Value::as_str) {
                            if at.get("page").is_none() && at.get("pages").is_none() {
                                urls.entry(base_url.to_string())
                                    .or_default()
                                    .insert(heading.to_string());
                            }
                        }
                    }
                }
            }
        }
    }
    urls
}

/// Resolves cited document headings using a caller-supplied `fetcher` (`explorer.py:resolve_anchors`).
pub fn resolve_anchors_with<F>(checker: &Checker, mut fetcher: F) -> Value
where
    F: FnMut(&str) -> Result<String, String>,
{
    let mut anchors = Map::new();
    let mut unresolved = Vec::new();
    for (url, headings) in wanted(checker) {
        let found = match fetcher(&url) {
            Ok(html) => parse_headings(&html),
            Err(reason) => {
                for heading in headings {
                    unresolved.push(json!({
                        "heading": heading,
                        "reason": reason,
                        "url": url,
                    }));
                }
                continue;
            }
        };
        let mut matched = Map::new();
        for heading in headings {
            let key = heading_key(&heading);
            if let Some(anchor) = found.get(&key) {
                if anchor_re().is_match(anchor) {
                    matched.insert(heading, Value::String(anchor.clone()));
                    continue;
                }
            }
            unresolved.push(json!({
                "heading": heading,
                "reason": "heading not found in document",
                "url": url,
            }));
        }
        if !matched.is_empty() {
            anchors.insert(url, Value::Object(matched));
        }
    }
    sort_json_keys(&json!({
        "anchors": Value::Object(anchors),
        "format": ANCHORS_FORMAT,
        "unresolved": Value::Array(unresolved),
    }))
}

/// Resolves cited document headings over the network (`explorer.py:resolve_anchors`).
#[must_use]
pub fn resolve_anchors(checker: &Checker) -> Value {
    resolve_anchors_with(checker, fetch_html)
}

/// Returns an empty format-1 `anchors.json` value (`explorer.py:empty_anchors`).
#[must_use]
pub fn empty_anchors_value() -> Value {
    sort_json_keys(&json!({
        "anchors": {},
        "format": ANCHORS_FORMAT,
        "unresolved": [],
    }))
}

/// Returns the canonical JSON string for an empty format-1 `anchors.json`.
#[must_use]
pub fn empty_anchors() -> String {
    dump_anchors(&empty_anchors_value())
}

/// Serializes `anchors` in canonical format-1 pretty JSON with sorted keys and a trailing newline
/// (`explorer.py:dump_anchors`).
#[must_use]
pub fn dump_anchors(anchors: &Value) -> String {
    let sorted = sort_json_keys(anchors);
    let mut s = serde_json::to_string_pretty(&sorted).unwrap_or_else(|_| "{}".to_string());
    s.push('\n');
    s
}

/// Validates and loads `anchors.json` against the cited headings of `checker`, refusing
/// malformed JSON, non-canonical formatting, unexpected URLs or headings, invalid fragments,
/// or duplicate entries (`explorer.py:load_anchors`).
pub fn load_anchors(
    text: &str,
    checker: &Checker,
) -> Result<BTreeMap<String, BTreeMap<String, String>>, String> {
    let raw: Value =
        serde_json::from_str(text).map_err(|e| format!("anchors.json is not valid JSON: {e}"))?;
    let Some(obj) = raw.as_object() else {
        return Err("anchors.json does not have the format-1 anchor schema".to_string());
    };
    if obj.len() != 3
        || obj.get("format").and_then(Value::as_i64) != Some(ANCHORS_FORMAT)
        || !obj.get("anchors").is_some_and(Value::is_object)
        || !obj.get("unresolved").is_some_and(Value::is_array)
    {
        return Err("anchors.json does not have the format-1 anchor schema".to_string());
    }
    if dump_anchors(&raw) != text {
        return Err("anchors.json is not in canonical form".to_string());
    }
    let allowed = wanted(checker);
    let mut out: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    let mut seen: HashSet<(String, String)> = HashSet::new();

    for (url, table_val) in obj["anchors"].as_object().unwrap() {
        let Some(allowed_headings) = allowed.get(url) else {
            return Err(format!(
                "anchors.json names an unexpected document URL: {url:?}"
            ));
        };
        let Some(table) = table_val.as_object() else {
            return Err(format!(
                "anchors.json names an unexpected document URL: {url:?}"
            ));
        };
        if table.is_empty() {
            return Err(format!(
                "anchors.json names an unexpected document URL: {url:?}"
            ));
        }
        let mut url_map = BTreeMap::new();
        for (heading, anchor_val) in table {
            if !allowed_headings.contains(heading) {
                return Err(format!(
                    "anchors.json names an unexpected heading under {url:?}"
                ));
            }
            let Some(anchor) = anchor_val.as_str() else {
                return Err(format!(
                    "anchors.json has an invalid anchor fragment for {url:?}"
                ));
            };
            if !anchor_re().is_match(anchor) {
                return Err(format!(
                    "anchors.json has an invalid anchor fragment for {url:?}"
                ));
            }
            url_map.insert(heading.clone(), anchor.to_string());
            seen.insert((url.clone(), heading.clone()));
        }
        out.insert(url.clone(), url_map);
    }

    for item in obj["unresolved"].as_array().unwrap() {
        let Some(item_obj) = item.as_object() else {
            return Err("anchors.json has an invalid unresolved entry".to_string());
        };
        if item_obj.len() != 3 {
            return Err("anchors.json has an invalid unresolved entry".to_string());
        }
        let (Some(url), Some(heading), Some(reason)) = (
            item_obj
                .get("url")
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty()),
            item_obj
                .get("heading")
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty()),
            item_obj
                .get("reason")
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty()),
        ) else {
            return Err("anchors.json has an invalid unresolved entry".to_string());
        };
        let _ = reason;
        let Some(allowed_headings) = allowed.get(url) else {
            return Err("anchors.json unresolved entry is not a cited heading".to_string());
        };
        if !allowed_headings.contains(heading) {
            return Err("anchors.json unresolved entry is not a cited heading".to_string());
        }
        if !seen.insert((url.to_string(), heading.to_string())) {
            return Err("anchors.json lists a heading twice".to_string());
        }
    }

    Ok(out)
}

/// Formats human-readable report lines for unresolved headings (`explorer.py:unresolved_report`).
#[must_use]
pub fn unresolved_report(anchors: &Value) -> Vec<String> {
    let mut res = Vec::new();
    if let Some(unresolved) = anchors.get("unresolved").and_then(Value::as_array) {
        for u in unresolved {
            if let (Some(url), Some(heading), Some(reason)) = (
                u.get("url").and_then(Value::as_str),
                u.get("heading").and_then(Value::as_str),
                u.get("reason").and_then(Value::as_str),
            ) {
                res.push(format!("unresolved heading: {url} :: {heading} ({reason})"));
            }
        }
    }
    res
}

fn format_locator(at: &Map<String, Value>) -> String {
    let mut parts = Vec::new();
    for (key, value) in at {
        if key == "pages" {
            if let Some(arr) = value.as_array() {
                let joined = arr
                    .iter()
                    .filter_map(Value::as_str)
                    .collect::<Vec<_>>()
                    .join("\u{2013}");
                parts.push(format!("pp. {joined}"));
            }
        } else if let Some(v_str) = value.as_str() {
            let prefix = match key.as_str() {
                "page" => "p. ".to_string(),
                "section" => "\u{00a7}".to_string(),
                "heading" => "heading: ".to_string(),
                other => format!("{other} "),
            };
            parts.push(format!("{prefix}{v_str}"));
        }
    }
    parts.join(", ")
}

fn build_cite(
    checker: &Checker,
    file_idx: usize,
    entry: &Value,
    anchors: &BTreeMap<String, BTreeMap<String, String>>,
) -> Result<Value, String> {
    let file = &checker.files[file_idx];
    let cls = entry
        .get("class")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let mut doc_title = String::new();
    let mut doc_url = String::new();
    let mut locators = Vec::new();

    if let Some(doc_name) = entry.get("doc").and_then(Value::as_str) {
        if let Some((doc, _)) = file.documents.get(doc_name) {
            let title = doc.get("title").and_then(Value::as_str).unwrap_or("");
            doc_title = if let Some(rev) = doc.get("revision").and_then(Value::as_str) {
                format!("{title} ({rev})")
            } else {
                title.to_string()
            };
            let raw_url = doc.get("url").and_then(Value::as_str).unwrap_or("");
            if specmd::allowed_link(raw_url) {
                doc_url = raw_url.to_string();
            }
            let base_url = doc_url.split('#').next().unwrap_or("");
            let resolved = anchors.get(base_url);
            if let Some(at_arr) = entry.get("at").and_then(Value::as_array) {
                for at_val in at_arr {
                    let Some(at_obj) = at_val.as_object() else {
                        continue;
                    };
                    let text = format_locator(at_obj);
                    let mut url = String::new();
                    if !base_url.is_empty()
                        && at_obj.contains_key("heading")
                        && !at_obj.contains_key("page")
                        && !at_obj.contains_key("pages")
                    {
                        if let Some(h) = at_obj.get("heading").and_then(Value::as_str) {
                            if let Some(frag) = resolved.and_then(|m| m.get(h)) {
                                if anchor_re().is_match(frag) {
                                    url = format!("{base_url}#{frag}");
                                }
                            }
                        }
                    } else if !base_url.is_empty()
                        && (at_obj.contains_key("page") || at_obj.contains_key("pages"))
                        && base_url.to_ascii_lowercase().ends_with(".pdf")
                    {
                        let first = at_obj
                            .get("page")
                            .and_then(Value::as_str)
                            .or_else(|| {
                                at_obj
                                    .get("pages")
                                    .and_then(Value::as_array)
                                    .and_then(|a| a.first())
                                    .and_then(Value::as_str)
                            })
                            .unwrap_or("");
                        if !first.is_empty() && first.chars().all(|c| c.is_ascii_digit()) {
                            url = format!("{base_url}#page={first}");
                        }
                    }
                    locators.push(json!({
                        "text": text,
                        "url": url,
                    }));
                }
            }
        }
    }

    let mut code_anchors = Vec::new();
    if let Some(anch_arr) = entry.get("anchors").and_then(Value::as_array) {
        for anchor in anch_arr {
            let repo_name = anchor.get("repo").and_then(Value::as_str).unwrap_or("");
            let Some((repo, _)) = file.repos.get(repo_name) else {
                continue;
            };
            let r_name = repo
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or(repo_name);
            let r_commit = repo.get("commit").and_then(Value::as_str).unwrap_or("");
            let r_lic = repo.get("license").and_then(Value::as_str).unwrap_or("");
            let a_path = anchor.get("path").and_then(Value::as_str).unwrap_or("");
            let mut label = format!("{r_name}@{r_commit} ({r_lic}) {a_path}");
            if let Some(lines) = anchor.get("lines").and_then(Value::as_array) {
                if lines.len() == 2 {
                    label.push_str(&format!(
                        " lines {}\u{2013}{}",
                        render_md::_value(&lines[0]),
                        render_md::_value(&lines[1])
                    ));
                }
            }
            let raw_repo_url = repo.get("url").and_then(Value::as_str).unwrap_or("");
            let trimmed_url = raw_repo_url.strip_suffix(".git").unwrap_or(raw_repo_url);
            let mut url = String::new();
            if trimmed_url.starts_with("https://github.com/") && specmd::allowed_link(trimmed_url) {
                url = format!(
                    "{trimmed_url}/blob/{r_commit}/{}",
                    percent_encode_path(a_path)
                );
                if let Some(lines) = anchor.get("lines").and_then(Value::as_array) {
                    if lines.len() == 2 {
                        url.push_str(&format!(
                            "#L{}-L{}",
                            render_md::_value(&lines[0]),
                            render_md::_value(&lines[1])
                        ));
                    }
                }
            }
            let mut detail = Vec::new();
            for key in ["symbol", "node", "search", "comment", "stale"] {
                if let Some(val) = anchor.get(key) {
                    detail.push(format!("{key}: {}", render_md::_value(val)));
                }
            }
            code_anchors.push(json!({
                "detail": detail,
                "label": label,
                "url": url,
            }));
        }
    }

    let mut premises = Vec::new();
    if cls == "inference" {
        if let Some(prem_arr) = entry.get("premises").and_then(Value::as_array) {
            for premise in prem_arr {
                if let Some(fact_ref) = premise.get("fact").and_then(Value::as_str) {
                    let (rec_opt, why_opt) = checker.resolve(file_idx, fact_ref);
                    if let Some(why) = why_opt {
                        return Err(why);
                    }
                    let rec = rec_opt.ok_or_else(|| format!("unresolved premise {fact_ref}"))?;
                    premises.push(json!({
                        "kind": "fact",
                        "ref": rec.full,
                        "uses": premise.get("uses").and_then(Value::as_str).unwrap_or(""),
                    }));
                } else if let Some(states) = premise.get("states").and_then(Value::as_str) {
                    let mut sub_cites = Vec::new();
                    if let Some(sup_arr) = premise.get("support").and_then(Value::as_array) {
                        for s in sup_arr {
                            sub_cites.push(build_cite(checker, file_idx, s, anchors)?);
                        }
                    }
                    premises.push(json!({
                        "cites": sub_cites,
                        "html": render_html::author(states),
                        "kind": "states",
                        "text": plain(states),
                    }));
                } else if let Some(assump_id) = premise.get("assumption").and_then(Value::as_str) {
                    if let Some((a, _)) = file.assumptions.get(assump_id) {
                        premises.push(json!({
                            "id": a.get("id").and_then(Value::as_str).unwrap_or(assump_id),
                            "kind": "assumption",
                            "text": a.get("text").and_then(Value::as_str).unwrap_or(""),
                        }));
                    }
                }
            }
        }
    }

    let skip = [
        "class",
        "doc",
        "at",
        "anchors",
        "note",
        "premises",
        "derivation",
    ];
    let mut extra = Vec::new();
    if let Some(obj) = entry.as_object() {
        for (k, v) in obj {
            if !skip.contains(&k.as_str()) {
                extra.push(format!("{k}: {}", render_md::_value(v)));
            }
        }
    }

    let note_html = entry
        .get("note")
        .and_then(Value::as_str)
        .map(render_html::author)
        .unwrap_or_default();

    Ok(json!({
        "anchors": code_anchors,
        "class": cls,
        "derivation": entry.get("derivation").and_then(Value::as_str).unwrap_or(""),
        "doc": doc_title,
        "doc_url": doc_url,
        "extra": extra,
        "locators": locators,
        "note_html": note_html,
        "premises": premises,
    }))
}

fn build_fact(
    checker: &Checker,
    rec: &SpecRecord,
    status_map: &HashMap<(usize, String), &StatusRow>,
    anchors: &BTreeMap<String, BTreeMap<String, String>>,
) -> Result<Value, String> {
    let file_idx = rec.file_idx;
    let file = &checker.files[file_idx];
    let root = &checker.roots[file.root_idx];
    let d = &rec.data;
    let row = status_map.get(&(file_idx, rec.id.clone())).copied();
    let verdict_entry = file.verdicts.get(&rec.id).map(|(v, _)| v);

    let mut cites = Vec::new();
    if let Some(sup_arr) = d.get("support").and_then(Value::as_array) {
        for s in sup_arr {
            cites.push(build_cite(checker, file_idx, s, anchors)?);
        }
    }

    let mut notes_html = Vec::new();
    let mut notes_text = Vec::new();
    if let Some(n) = d.get("note").and_then(Value::as_str) {
        notes_html.push(json!({"label": "Fact note", "html": render_html::author(n)}));
        notes_text.push(plain(n));
    }
    if let Some(v) = verdict_entry {
        if let Some(n) = v.get("note").and_then(Value::as_str) {
            notes_html.push(json!({"label": "Verdict note", "html": render_html::author(n)}));
            notes_text.push(plain(n));
        }
    }

    let mut conflicts = Vec::new();
    if let Some(conf_arr) = d.get("conflicts").and_then(Value::as_array) {
        for c in conf_arr {
            let with_str = c.get("with").and_then(Value::as_str).unwrap_or("");
            let mut c_cites = Vec::new();
            if let Some(csup) = c.get("support").and_then(Value::as_array) {
                for s in csup {
                    c_cites.push(build_cite(checker, file_idx, s, anchors)?);
                }
            }
            let mut settled = Vec::new();
            if let Some(ssup) = c.get("settled_by").and_then(Value::as_array) {
                for s in ssup {
                    settled.push(build_cite(checker, file_idx, s, anchors)?);
                }
            }
            conflicts.push(json!({
                "cites": c_cites,
                "resolution": c.get("resolution").and_then(Value::as_str).unwrap_or(""),
                "settled_by": settled,
                "with_html": render_html::author(with_str),
                "with_text": plain(with_str),
            }));
        }
    }

    let mut assumes = Vec::new();
    if let Some(assump_arr) = d.get("assumes").and_then(Value::as_array) {
        for name_val in assump_arr {
            if let Some(name) = name_val.as_str() {
                if let Some((a, _)) = file.assumptions.get(name) {
                    assumes.push(json!({
                        "id": a.get("id").and_then(Value::as_str).unwrap_or(name),
                        "if_wrong": a.get("if_wrong").and_then(Value::as_str).unwrap_or(""),
                        "text": a.get("text").and_then(Value::as_str).unwrap_or(""),
                    }));
                }
            }
        }
    }

    let mut children = Vec::new();
    for (_, sub) in &file.records {
        if sub.parent_id.as_deref() == Some(rec.id.as_str()) {
            let sub_row = status_map.get(&(file_idx, sub.id.clone())).copied();
            let mut sub_cites = Vec::new();
            if let Some(ssup) = sub.data.get("support").and_then(Value::as_array) {
                for s in ssup {
                    sub_cites.push(build_cite(checker, file_idx, s, anchors)?);
                }
            }
            children.push(json!({
                "cites": sub_cites,
                "id": sub.id,
                "ref": sub.full,
                "status": sub_row.map(|r| r.status.as_str()).unwrap_or("unverified"),
                "verdict": sub_row.and_then(|r| r.verdict.as_deref()).unwrap_or(""),
            }));
        }
    }

    let mut readers = Vec::new();
    if let Some(v) = verdict_entry {
        if let Some(r_arr) = v.get("readers").and_then(Value::as_array) {
            for r in r_arr {
                readers.push(json!({
                    "date": r.get("date").and_then(Value::as_str).unwrap_or(""),
                    "reading": r.get("reading").and_then(Value::as_str).unwrap_or(""),
                    "verdict": r.get("verdict").and_then(Value::as_str).unwrap_or(""),
                    "verifier": r.get("verifier").and_then(Value::as_str).unwrap_or(""),
                }));
            }
        }
    }

    let claim = d.get("claim").and_then(Value::as_str);
    let claim_html = claim.map(render_html::author).unwrap_or_default();
    let claim_text = if let Some(c) = claim {
        plain(c)
    } else {
        serde_json::to_string(&sort_json_keys(d)).unwrap_or_default()
    };
    let full_text = if notes_text.is_empty() {
        claim_text
    } else {
        format!("{claim_text} {}", notes_text.join(" "))
            .trim()
            .to_string()
    };

    let default_section = match rec.path.first() {
        Some(PathElem::Key(k)) => k.as_str(),
        _ => "facts",
    };
    let section = d
        .get("section")
        .and_then(Value::as_str)
        .unwrap_or(default_section);
    let title = d
        .get("title")
        .or_else(|| d.get("name"))
        .and_then(Value::as_str)
        .unwrap_or(&rec.id);
    let todo = if let Some(t) = d.get("todo").and_then(Value::as_object) {
        json!({
            "check": t.get("check").and_then(Value::as_str).unwrap_or(""),
            "method": t.get("method").and_then(Value::as_str).unwrap_or(""),
            "text": t.get("text").and_then(Value::as_str).unwrap_or(""),
        })
    } else {
        Value::Null
    };

    let origin = verdict_entry
        .and_then(|v| v.get("origin"))
        .and_then(|o| o.get("root"))
        .and_then(Value::as_str)
        .map(ToString::to_string)
        .unwrap_or_else(|| root.label());

    Ok(json!({
        "assumes": assumes,
        "carried": verdict_entry.and_then(|v| v.get("carried_from")).is_some(),
        "children": children,
        "cites": cites,
        "claim_html": claim_html,
        "conflicts": conflicts,
        "contested": !conflicts.is_empty(),
        "critical": d.get("critical").and_then(Value::as_bool).unwrap_or(false),
        "date": verdict_entry.and_then(|v| v.get("date")).and_then(Value::as_str).unwrap_or(""),
        "gap": rec.path.first() == Some(&PathElem::from("facts")) && !crate::records::has_support(d),
        "id": rec.id,
        "notes_html": notes_html,
        "origin": origin,
        "readers": readers,
        "ref": rec.full,
        "second_reader_missing": row.is_some_and(|r| r.second_reader == "missing"),
        "section": section,
        "source": root.label(),
        "status": row.map(|r| r.status.as_str()).unwrap_or("unverified"),
        "text": full_text,
        "title": title,
        "todo": todo,
        "verdict": row.and_then(|r| r.verdict.as_deref()).unwrap_or(""),
        "verifier": verdict_entry.and_then(|v| v.get("verifier")).and_then(Value::as_str).unwrap_or(""),
    }))
}

/// Builds the JSON data model for the interactive spec explorer (`explorer.py:data`).
pub fn data(
    checker: &Checker,
    anchors: &BTreeMap<String, BTreeMap<String, String>>,
    entries: &[Value],
    tool_commit: &str,
) -> Result<Value, String> {
    data_with_check(checker, anchors, entries, tool_commit, true)
}

/// Builds the JSON data model for the interactive spec explorer, optionally checking
/// `render_html::refuse_unsafe_fields` (`explorer.py:data`).
pub fn data_with_check(
    checker: &Checker,
    anchors: &BTreeMap<String, BTreeMap<String, String>>,
    entries: &[Value],
    tool_commit: &str,
    check_unsafe: bool,
) -> Result<Value, String> {
    for root in &checker.roots {
        if root.context && !root.untrusted.is_empty() {
            return Err("cannot render explorer: context root does not check clean".to_string());
        }
    }
    if check_unsafe {
        for file in &checker.files {
            render_html::refuse_unsafe_fields(file)?;
        }
    }

    let mut status_map: HashMap<(usize, String), &StatusRow> = HashMap::new();
    for (f_idx, entry) in &checker.status {
        for row in &entry.facts {
            status_map.insert((*f_idx, row.key.clone()), row);
        }
    }

    let mut ids = Vec::new();
    for f in &checker.files {
        if !checker.roots[f.root_idx].context {
            let sid = f.spec_id();
            if !ids.contains(&sid) {
                ids.push(sid);
            }
        }
    }

    let mut specs = Vec::new();
    for sid in ids {
        let mut group: Vec<&SpecFile> = checker
            .files
            .iter()
            .filter(|f| f.spec_id() == sid)
            .collect();
        group.sort_by_key(|f| {
            let r = &checker.roots[f.root_idx];
            (f.is_overlay(), r.rank, r.order, f.path.clone())
        });
        let base = group
            .iter()
            .find(|f| !f.is_overlay())
            .copied()
            .unwrap_or(group[0]);

        let mut documents = Vec::new();
        let mut seen_docs: HashSet<(String, String)> = HashSet::new();
        for f in &group {
            if let Some(docs) = f
                .data
                .get("resources")
                .and_then(|r| r.get("documents"))
                .and_then(Value::as_array)
            {
                for doc in docs {
                    let title = doc
                        .get("title")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string();
                    let raw_url = doc.get("url").and_then(Value::as_str).unwrap_or("");
                    let key = (title.clone(), raw_url.to_string());
                    if seen_docs.insert(key) {
                        documents.push(json!({
                            "class": doc.get("class").and_then(Value::as_str).unwrap_or(""),
                            "pages": doc.get("pages").cloned().unwrap_or(Value::Null),
                            "title": title,
                            "url": if specmd::allowed_link(raw_url) { raw_url } else { "" },
                        }));
                    }
                }
            }
        }

        let mut orientation_html = String::new();
        for f in &group {
            if let Some(ori) = f.data.get("orientation").and_then(Value::as_str) {
                orientation_html.push_str(&render_html::author(ori));
            }
        }

        let mut facts = Vec::new();
        for f in &group {
            for (_, rec) in &f.records {
                if rec.parent_id.is_none() {
                    facts.push(build_fact(checker, rec, &status_map, anchors)?);
                }
            }
        }

        let mut spec_pages = Vec::new();
        for p in entries {
            if p.get("spec").and_then(Value::as_str) == Some(sid.as_str()) {
                spec_pages.push(json!({
                    "html": p.get("html").and_then(Value::as_str).unwrap_or(""),
                    "label": p.get("source").and_then(Value::as_str).unwrap_or(""),
                    "markdown": p.get("markdown").and_then(Value::as_str).unwrap_or(""),
                }));
            }
        }

        specs.push(json!({
            "documents": documents,
            "facts": facts,
            "id": sid,
            "kind": base.kind(),
            "name": base.data.get("name").and_then(Value::as_str).unwrap_or(&sid),
            "orientation_html": orientation_html,
            "pages": spec_pages,
            "triggers": base.data.get("triggers").cloned().unwrap_or_else(|| json!([])),
        }));
    }

    Ok(sort_json_keys(&json!({
        "specs": specs,
        "tool_commit": if tool_commit.is_empty() { "unavailable" } else { tool_commit },
    })))
}

/// Renders the self-contained `index.html` spec explorer page (`explorer.py:page`).
pub fn try_page(
    checker: &Checker,
    anchors: &BTreeMap<String, BTreeMap<String, String>>,
    entries: &[Value],
    tool_commit: &str,
) -> Result<String, String> {
    try_page_with_check(checker, anchors, entries, tool_commit, true)
}

/// Renders the self-contained `index.html` spec explorer page, optionally checking
/// `render_html::refuse_unsafe_fields` (`explorer.py:page`).
pub fn try_page_with_check(
    checker: &Checker,
    anchors: &BTreeMap<String, BTreeMap<String, String>>,
    entries: &[Value],
    tool_commit: &str,
    check_unsafe: bool,
) -> Result<String, String> {
    let payload_val = data_with_check(checker, anchors, entries, tool_commit, check_unsafe)?;
    let payload_str = serde_json::to_string(&payload_val)
        .unwrap_or_else(|_| "{}".to_string())
        .replace('&', "\\u0026")
        .replace('<', "\\u003c")
        .replace('>', "\\u003e");

    let html = include_str!("../skills/spec-format/scripts/explorer.html");
    let css = include_str!("../skills/spec-format/scripts/explorer.css");
    let js = include_str!("../skills/spec-format/scripts/explorer.js");

    Ok(format!(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">\n\
         <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n\
         <title>Spec explorer</title><style>{css}</style></head><body>\n\
         {html}<script type=\"application/json\" id=\"spec-data\">{payload_str}</script>\n\
         <script>{js}</script>\n\
         </body></html>\n"
    ))
}

/// Convenience wrapper for [`try_page`] accepting either a parsed `BTreeMap` or an `anchors.json`
/// `Value` (`explorer.py:page`). Panics or returns an error string if unsafe fields are encountered.
pub fn page(
    checker: &Checker,
    loaded_anchors: &Value,
    entries: &[Value],
    tool_commit: &str,
) -> Result<String, String> {
    let mut map: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    let anchors_obj = loaded_anchors
        .get("anchors")
        .and_then(Value::as_object)
        .or_else(|| loaded_anchors.as_object());
    if let Some(obj) = anchors_obj {
        for (url, tbl) in obj {
            if let Some(tbl_obj) = tbl.as_object() {
                let mut inner = BTreeMap::new();
                for (h, a) in tbl_obj {
                    if let Some(a_str) = a.as_str() {
                        inner.insert(h.clone(), a_str.to_string());
                    }
                }
                map.insert(url.clone(), inner);
            }
        }
    }
    try_page(checker, &map, entries, tool_commit)
}

/// Board and SoC topology atlas (`atlas.py`, `RT-8`).
pub mod atlas {
    use super::{plain, sort_json_keys};
    use crate::records::{Checker, PathElem, SpecFile, StatusRow};
    use crate::render_html;
    use serde_json::{json, Map, Value};
    use std::collections::{HashMap, HashSet};

    fn sections_for_kind(kind: &str) -> &'static [&'static str] {
        match kind {
            "board" => &[
                "identity",
                "boot",
                "interrupts",
                "timers",
                "clocks-power",
                "console",
                "io",
                "storage",
                "display",
                "coprocessors",
                "security",
                "errata",
            ],
            "soc" => &[
                "identity",
                "address-map",
                "boot",
                "interrupts",
                "timers",
                "clocks-power",
                "io",
                "buses",
                "dma",
                "memory",
                "security",
                "coprocessors",
                "errata",
            ],
            "chip" | "ip" => &[
                "quick-facts",
                "identity",
                "integration",
                "programming",
                "errata",
                "gotchas",
            ],
            "peripheral" => &[
                "identity",
                "standards",
                "resources",
                "registers",
                "layouts",
                "sequences",
                "behaviors",
                "verification",
                "gotchas",
            ],
            _ => &["facts"],
        }
    }

    fn base_file<'a>(spec_id: &str, files: &[(usize, &'a SpecFile)]) -> Option<&'a SpecFile> {
        files
            .iter()
            .find(|(_, f)| f.spec_id() == spec_id && !f.is_overlay())
            .map(|(_, f)| *f)
    }

    fn address(value: Option<&Value>) -> Option<i64> {
        let v = value?;
        if v.is_boolean() {
            return None;
        }
        if let Some(i) = v.as_i64() {
            return Some(i);
        }
        if let Some(s) = v.as_str() {
            let trimmed = s.trim();
            if let Some(hex) = trimmed
                .strip_prefix("0x")
                .or_else(|| trimmed.strip_prefix("0X"))
            {
                return i64::from_str_radix(hex, 16).ok();
            }
        }
        None
    }

    fn size_str(n: i64) -> String {
        for (unit, shift) in [("GiB", 30), ("MiB", 20), ("KiB", 10)] {
            if n >= (1i64 << shift) {
                let v = (n as f64) / ((1i64 << shift) as f64);
                if v.fract() == 0.0 {
                    return format!("{v:.0} {unit}");
                }
                return format!("{v:.1} {unit}");
            }
        }
        format!("{n} bytes")
    }

    /// Selects the placed specs `(spec_id, parent_id, join_how)` and eligible `(file_idx, &SpecFile)`
    /// for an atlas centered on `spec_id` (`atlas.py:select`).
    pub fn select<'a>(
        checker: &'a Checker,
        spec_id: &str,
        merged: bool,
    ) -> Result<
        (
            Vec<(String, Option<String>, String)>,
            Vec<(usize, &'a SpecFile)>,
        ),
        String,
    > {
        let files: Vec<(usize, &SpecFile)> = checker
            .files
            .iter()
            .enumerate()
            .filter(|(_, f)| {
                let root = &checker.roots[f.root_idx];
                merged || !root.context
            })
            .collect();

        let present: HashSet<String> = files.iter().map(|(_, f)| f.spec_id()).collect();
        if !present.contains(spec_id) {
            return Err(format!("no spec '{spec_id}' in the rendered roots"));
        }

        let mut placed: Vec<(String, Option<String>, String)> =
            vec![(spec_id.to_string(), None, String::new())];
        let mut placed_set: HashSet<String> = HashSet::from([spec_id.to_string()]);

        let add = |child: &str,
                   parent: &str,
                   how: &str,
                   placed: &mut Vec<(String, Option<String>, String)>,
                   placed_set: &mut HashSet<String>|
         -> bool {
            if present.contains(child) && !placed_set.contains(child) {
                placed.push((child.to_string(), Some(parent.to_string()), how.to_string()));
                placed_set.insert(child.to_string());
                true
            } else {
                false
            }
        };

        let mut queue = vec![spec_id.to_string()];
        while !queue.is_empty() {
            let sid = queue.remove(0);
            if let Some(b) = base_file(&sid, &files) {
                if let Some(parts) = b.data.get("parts").and_then(Value::as_array) {
                    for part in parts {
                        if let Some(p) = part.as_str() {
                            if add(p, &sid, "parts", &mut placed, &mut placed_set) {
                                queue.push(p.to_string());
                            }
                        }
                    }
                }
            }
        }

        let core: Vec<String> = placed.iter().map(|(s, _, _)| s.clone()).collect();

        let add_ips = |ids: &[String],
                       placed: &mut Vec<(String, Option<String>, String)>,
                       placed_set: &mut HashSet<String>| {
            for sid in ids {
                for (_, f) in &files {
                    if f.spec_id() == *sid {
                        if let Some(instances) = f.data.get("instances").and_then(Value::as_array) {
                            for row in instances {
                                if let Some(ip) = row.get("ip").and_then(Value::as_str) {
                                    add(ip, sid, "ip", placed, placed_set);
                                }
                                if let Some(peri) = row.get("peripheral").and_then(Value::as_str) {
                                    add(peri, sid, "programming", placed, placed_set);
                                }
                            }
                        }
                    }
                }
            }
        };

        add_ips(&core, &mut placed, &mut placed_set);

        for (_, f) in &files {
            if f.kind() == "peripheral" && !f.is_overlay() {
                if let Some(describes) = f.data.get("describes").and_then(Value::as_array) {
                    for target in describes {
                        if let Some(t) = target.as_str() {
                            if core.iter().any(|c| c == t) {
                                add(&f.spec_id(), t, "programming", &mut placed, &mut placed_set);
                                break;
                            }
                        }
                    }
                }
            }
        }

        let mut counts: HashMap<String, HashMap<String, usize>> = HashMap::new();
        for &(file_idx, f) in &files {
            for (_, rec) in &f.records {
                if rec.path.first() != Some(&PathElem::from("facts")) || rec.parent_id.is_some() {
                    continue;
                }
                for (_, ref_str, _) in crate::records::references(&rec.data, &rec.path) {
                    let (target_opt, why_opt) = checker.resolve(file_idx, &ref_str);
                    if why_opt.is_none() {
                        if let Some(target) = target_opt {
                            let a = f.spec_id();
                            let b = checker.files[target.file_idx].spec_id();
                            for (inside, outside) in [(&a, &b), (&b, &a)] {
                                if core.contains(inside)
                                    && !placed_set.contains(outside)
                                    && present.contains(outside)
                                {
                                    *counts
                                        .entry(outside.clone())
                                        .or_default()
                                        .entry(inside.clone())
                                        .or_default() += 1;
                                }
                            }
                        }
                    }
                }
            }
        }

        let mut linked = Vec::new();
        let mut outside_keys: Vec<String> = counts.keys().cloned().collect();
        outside_keys.sort();
        for outside in outside_keys {
            let inside_counts = &counts[&outside];
            let mut inside_keys: Vec<String> = inside_counts.keys().cloned().collect();
            inside_keys.sort();
            let parent = inside_keys
                .into_iter()
                .max_by_key(|k| inside_counts[k])
                .unwrap();
            let b = base_file(&outside, &files);
            let how = if b.is_some_and(|f| f.kind() == "peripheral") {
                "programming"
            } else {
                "related"
            };
            add(&outside, &parent, how, &mut placed, &mut placed_set);
            linked.push(outside);
        }
        add_ips(&linked, &mut placed, &mut placed_set);

        Ok((placed, files))
    }

    /// Builds the JSON payload for an atlas centered on `spec_id` (`atlas.py:data`).
    pub fn data(
        checker: &Checker,
        spec_id: &str,
        merged: bool,
        source_commits: &[String],
        tool_commit: &str,
    ) -> Result<Value, String> {
        let (placed_vec, files) = select(checker, spec_id, merged)?;
        let placed_ids: HashSet<String> = placed_vec.iter().map(|(s, _, _)| s.clone()).collect();
        let chosen: Vec<(usize, &SpecFile)> = files
            .iter()
            .copied()
            .filter(|(_, f)| placed_ids.contains(&f.spec_id()))
            .collect();

        let chosen_refs: Vec<&SpecFile> = chosen.iter().map(|(_, f)| *f).collect();
        let commits =
            crate::render_md::source_commits_list(checker, &[chosen_refs], source_commits)?;

        for &(_, f) in &chosen {
            let root = &checker.roots[f.root_idx];
            if root.context && !root.untrusted.is_empty() {
                return Err(
                    "cannot render merged input: context root does not check clean".to_string(),
                );
            }
            render_html::refuse_unsafe_fields(f)?;
        }

        let mut status_map: HashMap<(usize, String), &StatusRow> = HashMap::new();
        for (f_idx, entry) in &checker.status {
            for row in &entry.facts {
                status_map.insert((*f_idx, row.key.clone()), row);
            }
        }

        let mut placed_keys: HashSet<String> = HashSet::new();
        for &(_, f) in &chosen {
            for (_, rec) in &f.records {
                if rec.parent_id.is_none() {
                    placed_keys.insert(rec.full.clone());
                }
            }
        }

        let mut roots_order: Vec<String> = Vec::new();
        let mut roots_map: HashMap<String, Value> = HashMap::new();
        let mut specs: Vec<Value> = Vec::new();
        let mut facts: Vec<Value> = Vec::new();
        let mut instances: Vec<Value> = Vec::new();

        for (sid, parent, how) in &placed_vec {
            let mut group: Vec<(usize, &SpecFile)> = chosen
                .iter()
                .copied()
                .filter(|(_, f)| f.spec_id() == *sid)
                .collect();
            group.sort_by_key(|(_, f)| {
                let r = &checker.roots[f.root_idx];
                (f.is_overlay(), r.rank, r.order, f.path.clone())
            });

            let base = base_file(sid, &group);
            let kind = base.map(|f| f.kind()).unwrap_or("overlay");
            let name = base
                .and_then(|f| f.data.get("name").and_then(Value::as_str))
                .unwrap_or(sid);

            let mut orientation = String::new();
            for &(_, f) in &group {
                if let Some(ori) = f.data.get("orientation").and_then(Value::as_str) {
                    orientation.push_str(&render_html::author(ori));
                }
            }

            let mut section_counts: HashMap<String, usize> = HashMap::new();
            let mut extra_sections: Vec<String> = Vec::new();
            for &(_, f) in &group {
                for (_, rec) in &f.records {
                    if rec.path.first() == Some(&PathElem::from("facts")) && rec.parent_id.is_none()
                    {
                        let s = rec
                            .data
                            .get("section")
                            .and_then(Value::as_str)
                            .unwrap_or("facts")
                            .to_string();
                        *section_counts.entry(s.clone()).or_default() += 1;
                        if !sections_for_kind(kind).contains(&s.as_str())
                            && !extra_sections.contains(&s)
                        {
                            extra_sections.push(s);
                        }
                    }
                }
            }

            let mut sections = Vec::new();
            for &s in sections_for_kind(kind) {
                if let Some(&cnt) = section_counts.get(s) {
                    if cnt > 0 {
                        sections.push(json!({"count": cnt, "id": s}));
                    }
                }
            }
            for s in extra_sections {
                if let Some(&cnt) = section_counts.get(&s) {
                    if cnt > 0 {
                        sections.push(json!({"count": cnt, "id": s}));
                    }
                }
            }

            let mut root_labels = Vec::new();
            for &(_, f) in &group {
                let lbl = checker.roots[f.root_idx].label();
                if !root_labels.contains(&lbl) {
                    root_labels.push(lbl);
                }
            }

            specs.push(json!({
                "id": sid,
                "join": how,
                "kind": kind,
                "name": name,
                "orientation_html": orientation,
                "parent": parent,
                "roots": root_labels,
                "sections": sections,
            }));

            for (file_idx, f) in group {
                let root = &checker.roots[f.root_idx];
                let root_lbl = root.label();
                if !roots_map.contains_key(&root_lbl) {
                    let abs = root
                        .given
                        .canonicalize()
                        .unwrap_or_else(|_| root.given.clone());
                    let lic = root
                        .marker
                        .as_ref()
                        .and_then(|m| m.data.as_ref())
                        .and_then(|d| d.get("license"))
                        .and_then(Value::as_str)
                        .unwrap_or("");
                    roots_order.push(root_lbl.clone());
                    roots_map.insert(
                        root_lbl.clone(),
                        json!({
                            "commit": commits.get(&abs).cloned().unwrap_or_default(),
                            "context": root.context,
                            "layer": root.layer.clone().unwrap_or_default(),
                            "license": lic,
                            "name": root_lbl,
                        }),
                    );
                }

                for (_, rec) in &f.records {
                    if rec.parent_id.is_some() {
                        continue;
                    }
                    let d = &rec.data;
                    let row = status_map.get(&(file_idx, rec.id.clone())).copied();
                    let verdict = f.verdicts.get(&rec.id).map(|(v, _)| v);

                    let mut common = Map::new();
                    common.insert("key".to_string(), json!(rec.full));
                    common.insert("spec".to_string(), json!(sid));
                    common.insert("id".to_string(), json!(rec.id));
                    common.insert("root".to_string(), json!(root.label()));
                    common.insert(
                        "verdict".to_string(),
                        json!(row.and_then(|r| r.verdict.as_deref()).unwrap_or("")),
                    );
                    common.insert(
                        "freshness".to_string(),
                        json!(row.map(|r| r.status.as_str()).unwrap_or("unverified")),
                    );
                    common.insert(
                        "verifier".to_string(),
                        json!(verdict
                            .and_then(|v| v.get("verifier"))
                            .and_then(Value::as_str)
                            .unwrap_or("")),
                    );
                    common.insert(
                        "date".to_string(),
                        json!(verdict
                            .and_then(|v| v.get("date"))
                            .and_then(Value::as_str)
                            .unwrap_or("")),
                    );

                    if rec.path.first() == Some(&PathElem::from("facts")) {
                        let claim = d.get("claim").and_then(Value::as_str);
                        let claim_html = claim.map(render_html::author).unwrap_or_default();
                        let text = if let Some(c) = claim {
                            plain(c)
                        } else {
                            serde_json::to_string(&sort_json_keys(d)).unwrap_or_default()
                        };

                        let mut classes: Vec<String> = Vec::new();
                        let mut sources = Vec::new();
                        if let Some(sup_arr) = d.get("support").and_then(Value::as_array) {
                            for s in sup_arr {
                                let cls = s
                                    .get("class")
                                    .and_then(Value::as_str)
                                    .unwrap_or("")
                                    .to_string();
                                if !cls.is_empty() && !classes.contains(&cls) {
                                    classes.push(cls.clone());
                                }
                                let src = s
                                    .get("doc")
                                    .and_then(Value::as_str)
                                    .or_else(|| {
                                        s.get("anchors")
                                            .and_then(Value::as_array)
                                            .and_then(|a| a.first())
                                            .and_then(|a0| a0.get("repo"))
                                            .and_then(Value::as_str)
                                    })
                                    .or_else(|| s.get("title").and_then(Value::as_str))
                                    .unwrap_or("");
                                sources.push(json!({
                                    "class": cls,
                                    "source": src,
                                }));
                            }
                        }

                        let mut relates = Vec::new();
                        let mut premises = Vec::new();
                        let mut outside = 0usize;

                        let resolve_target_key =
                            |t: &crate::records::RecordKey| -> (String, String, bool) {
                                let tf = &checker.files[t.file_idx];
                                let trec = tf.get_record(&t.id).unwrap();
                                let target_key = if let Some(ref pid) = trec.parent_id {
                                    tf.get_record(pid).unwrap().full.clone()
                                } else {
                                    t.full.clone()
                                };
                                let in_page = placed_keys.contains(&target_key);
                                (target_key, tf.spec_id(), in_page)
                            };

                        if let Some(rel_arr) = d.get("relates").and_then(Value::as_array) {
                            for rel in rel_arr {
                                if let Some(f_str) = rel.get("fact").and_then(Value::as_str) {
                                    let (t_opt, why_opt) = checker.resolve(file_idx, f_str);
                                    if why_opt.is_none() {
                                        if let Some(t) = t_opt {
                                            let (target_key, target_spec, in_page) =
                                                resolve_target_key(&t);
                                            relates.push(json!({
                                                "in_page": in_page,
                                                "relation": rel.get("relation").and_then(Value::as_str).unwrap_or(""),
                                                "target": target_key,
                                                "target_spec": target_spec,
                                            }));
                                            if !in_page {
                                                outside += 1;
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        for (entry, _) in crate::records::supports(d, &rec.path) {
                            if entry.get("class").and_then(Value::as_str) == Some("inference") {
                                if let Some(prem_arr) =
                                    entry.get("premises").and_then(Value::as_array)
                                {
                                    for premise in prem_arr {
                                        if let Some(f_str) =
                                            premise.get("fact").and_then(Value::as_str)
                                        {
                                            let (t_opt, why_opt) = checker.resolve(file_idx, f_str);
                                            if why_opt.is_none() {
                                                if let Some(t) = t_opt {
                                                    let (target_key, target_spec, in_page) =
                                                        resolve_target_key(&t);
                                                    let uses = premise
                                                        .get("uses")
                                                        .and_then(Value::as_str)
                                                        .unwrap_or("");
                                                    premises.push(json!({
                                                        "in_page": in_page,
                                                        "target": target_key,
                                                        "target_spec": target_spec,
                                                        "uses": uses,
                                                    }));
                                                    relates.push(json!({
                                                        "in_page": in_page,
                                                        "relation": "premise",
                                                        "target": target_key,
                                                        "target_spec": target_spec,
                                                        "uses": uses,
                                                    }));
                                                    if !in_page {
                                                        outside += 1;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        let todo = if let Some(t) = d.get("todo").and_then(Value::as_object) {
                            json!({
                                "check": t.get("check").and_then(Value::as_str).unwrap_or(""),
                                "text": t.get("text").and_then(Value::as_str).unwrap_or(""),
                            })
                        } else {
                            Value::Null
                        };

                        let mut row_todos = Vec::new();
                        for (child, _) in crate::records::peripheral_children(d, &rec.path) {
                            if let Some(ct) = child.get("todo").and_then(Value::as_object) {
                                let cid = child
                                    .get("id")
                                    .or_else(|| child.get("name"))
                                    .and_then(Value::as_str)
                                    .map(ToString::to_string)
                                    .unwrap_or_else(|| {
                                        format!(
                                            "{}->{}",
                                            child
                                                .get("before")
                                                .and_then(Value::as_str)
                                                .unwrap_or(""),
                                            child
                                                .get("after")
                                                .and_then(Value::as_str)
                                                .unwrap_or("")
                                        )
                                    });
                                row_todos.push(json!({
                                    "check": ct.get("check").and_then(Value::as_str).unwrap_or(""),
                                    "id": cid,
                                    "text": ct.get("text").and_then(Value::as_str).unwrap_or(""),
                                }));
                            }
                        }

                        let mut fact_obj = common;
                        fact_obj.insert(
                            "section".to_string(),
                            json!(d.get("section").and_then(Value::as_str).unwrap_or("facts")),
                        );
                        fact_obj.insert(
                            "title".to_string(),
                            json!(d.get("title").and_then(Value::as_str).unwrap_or(&rec.id)),
                        );
                        fact_obj.insert("claim_html".to_string(), json!(claim_html));
                        fact_obj.insert("text".to_string(), json!(text));
                        fact_obj.insert(
                            "critical".to_string(),
                            json!(d.get("critical").and_then(Value::as_bool).unwrap_or(false)),
                        );
                        fact_obj.insert("gap".to_string(), json!(!crate::records::has_support(d)));
                        fact_obj.insert("todo".to_string(), todo);
                        fact_obj.insert("row_todos".to_string(), Value::Array(row_todos));
                        fact_obj.insert("classes".to_string(), json!(classes));
                        fact_obj.insert("sources".to_string(), Value::Array(sources));
                        fact_obj.insert("relates".to_string(), Value::Array(relates));
                        fact_obj.insert("premises".to_string(), Value::Array(premises));
                        fact_obj.insert("outside_links".to_string(), json!(outside));
                        facts.push(Value::Object(fact_obj));
                    } else if rec.path.first() == Some(&PathElem::from("instances")) {
                        let base_addr = address(d.get("reg"));
                        let irq = if let Some(i) = d.get("irq").and_then(Value::as_object) {
                            json!({
                                "intid": i.get("intid").cloned().unwrap_or(Value::Null),
                                "kind": i.get("kind").and_then(Value::as_str).unwrap_or(""),
                                "number": i.get("number").cloned().unwrap_or(Value::Null),
                            })
                        } else {
                            Value::Null
                        };
                        let todo = if let Some(t) = d.get("todo").and_then(Value::as_object) {
                            json!({
                                "check": t.get("check").and_then(Value::as_str).unwrap_or(""),
                                "text": t.get("text").and_then(Value::as_str).unwrap_or(""),
                            })
                        } else {
                            Value::Null
                        };
                        let mut inst_obj = common;
                        inst_obj.insert(
                            "name".to_string(),
                            json!(d.get("name").and_then(Value::as_str).unwrap_or(&rec.id)),
                        );
                        inst_obj.insert(
                            "ip".to_string(),
                            json!(d.get("ip").and_then(Value::as_str).unwrap_or("")),
                        );
                        inst_obj.insert(
                            "peripheral".to_string(),
                            json!(d.get("peripheral").and_then(Value::as_str).unwrap_or("")),
                        );
                        inst_obj.insert(
                            "reg".to_string(),
                            d.get("reg").cloned().unwrap_or(Value::Null),
                        );
                        inst_obj.insert(
                            "base".to_string(),
                            base_addr.map(|b| json!(b)).unwrap_or(Value::Null),
                        );
                        inst_obj.insert("irq".to_string(), irq);
                        inst_obj.insert(
                            "clocks".to_string(),
                            d.get("clocks").cloned().unwrap_or_else(|| json!([])),
                        );
                        inst_obj.insert(
                            "iommu".to_string(),
                            d.get("iommu").cloned().unwrap_or(Value::Null),
                        );
                        inst_obj.insert(
                            "power_domain".to_string(),
                            json!(d.get("power_domain").and_then(Value::as_str).unwrap_or("")),
                        );
                        inst_obj.insert("todo".to_string(), todo);
                        instances.push(Value::Object(inst_obj));
                    }
                }
            }
        }

        let mut mapped: Vec<Value> = instances
            .iter()
            .filter(|i| i.get("base").is_some_and(Value::is_i64))
            .cloned()
            .collect();
        mapped.sort_by_key(|i| {
            (
                i.get("base").and_then(Value::as_i64).unwrap_or(0),
                i.get("key")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
            )
        });

        let mut memory_map = Vec::new();
        for idx in 0..mapped.len() {
            let inst = &mapped[idx];
            let base = inst.get("base").and_then(Value::as_i64).unwrap_or(0);
            let next_base = mapped
                .get(idx + 1)
                .and_then(|n| n.get("base"))
                .and_then(Value::as_i64);
            let gap = next_base.filter(|&nb| nb > base).map(|nb| nb - base);
            let needle = format!("0x{base:x}");
            let inst_key = inst.get("key").and_then(Value::as_str).unwrap_or("");
            let mut cites = Vec::new();
            for f in &facts {
                let rel_match = f
                    .get("relates")
                    .and_then(Value::as_array)
                    .is_some_and(|rels| {
                        rels.iter()
                            .any(|r| r.get("target").and_then(Value::as_str) == Some(inst_key))
                    });
                let text_match = base >= 0x1000
                    && f.get("text")
                        .and_then(Value::as_str)
                        .is_some_and(|t| t.to_ascii_lowercase().contains(&needle));
                if rel_match || text_match {
                    if let Some(fk) = f.get("key").and_then(Value::as_str) {
                        cites.push(Value::String(fk.to_string()));
                    }
                }
            }
            let mut mm_obj = inst.as_object().cloned().unwrap_or_default();
            mm_obj.insert(
                "next_base".to_string(),
                json!(next_base.map(|nb| format!("0x{nb:x}")).unwrap_or_default()),
            );
            mm_obj.insert(
                "span_bytes".to_string(),
                gap.map(|g| json!(g)).unwrap_or(Value::Null),
            );
            mm_obj.insert(
                "span".to_string(),
                json!(gap.map(size_str).unwrap_or_default()),
            );
            mm_obj.insert("cites".to_string(), Value::Array(cites));
            memory_map.push(Value::Object(mm_obj));
        }

        let mut other_ids = Vec::new();
        for &(_, f) in &files {
            let root = &checker.roots[f.root_idx];
            if !root.context {
                let sid = f.spec_id();
                if !placed_ids.contains(&sid) && !other_ids.contains(&sid) {
                    other_ids.push(sid);
                }
            }
        }
        let mut unplaced = Vec::new();
        for sid in other_ids {
            let b = base_file(&sid, &files);
            unplaced.push(json!({
                "id": sid,
                "kind": b.map(|f| f.kind()).unwrap_or("overlay"),
                "name": b.and_then(|f| f.data.get("name").and_then(Value::as_str)).unwrap_or(&sid),
            }));
        }

        let roots_arr: Vec<Value> = roots_order
            .into_iter()
            .filter_map(|lbl| roots_map.remove(&lbl))
            .collect();

        Ok(sort_json_keys(&json!({
            "center": spec_id,
            "facts": facts,
            "instances": instances,
            "memory_map": memory_map,
            "merged": merged,
            "roots": roots_arr,
            "specs": specs,
            "tool_commit": if tool_commit.is_empty() { "unavailable" } else { tool_commit },
            "unplaced": unplaced,
        })))
    }

    /// Renders the self-contained interactive topology atlas HTML page (`atlas.py:page`).
    pub fn page(
        checker: &Checker,
        spec_id: &str,
        merged: bool,
        source_commits: &[String],
        tool_commit: &str,
    ) -> Result<String, String> {
        let payload = data(checker, spec_id, merged, source_commits, tool_commit)?;
        let title_name = payload
            .get("specs")
            .and_then(Value::as_array)
            .and_then(|arr| {
                arr.iter()
                    .find(|s| s.get("id").and_then(Value::as_str) == Some(spec_id))
            })
            .and_then(|s| s.get("name"))
            .and_then(Value::as_str)
            .unwrap_or(spec_id);
        let title = render_html::escape_html(&format!("{title_name} atlas"), true);

        let payload_str = serde_json::to_string(&payload)
            .unwrap_or_else(|_| "{}".to_string())
            .replace('&', "\\u0026")
            .replace('<', "\\u003c")
            .replace('>', "\\u003e");

        let css = include_str!("../skills/spec-format/scripts/atlas.css");
        let html = include_str!("../skills/spec-format/scripts/atlas.html");
        let js = include_str!("../skills/spec-format/scripts/atlas.js");

        Ok(format!(
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">\n\
             <meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n\
             <title>{title}</title>\n\
             <style>{css}</style></head><body>\n\
             {html}<script type=\"application/json\" id=\"spec-data\">{payload_str}</script>\n\
             <script>{js}</script>\n\
             </body></html>\n"
        ))
    }
}
