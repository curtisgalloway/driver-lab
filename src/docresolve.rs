// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::sandbox::{run_bounded, PipeLimits};
use regex::{Regex, RegexBuilder};
use serde_json::{Map, Value};
use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Command;
use std::sync::OnceLock;

pub struct PdfPages {
    path: PathBuf,
    limit_bytes: usize,
    cache: HashMap<usize, Result<Vec<String>, String>>,
    size: usize,
}

impl PdfPages {
    pub fn new(path: PathBuf, _timeout_secs: u64, limit_bytes: usize) -> Self {
        Self {
            path,
            limit_bytes,
            cache: HashMap::new(),
            size: 0,
        }
    }

    pub fn page(&mut self, number: usize) -> Result<Vec<String>, String> {
        if !self.cache.contains_key(&number) {
            let res = self.extract(number);
            self.cache.insert(number, res);
        }
        self.cache.get(&number).unwrap().clone()
    }

    fn extract(&mut self, number: usize) -> Result<Vec<String>, String> {
        let mut cmd = Command::new("pdftotext");
        cmd.args([
            "-f",
            &number.to_string(),
            "-l",
            &number.to_string(),
            "-layout",
            "-enc",
            "UTF-8",
            self.path.to_str().unwrap(),
            "-",
        ]);
        let limits = PipeLimits {
            stdout_limit: self.limit_bytes.saturating_sub(self.size),
            stderr_limit: 1024,
        };
        let res = run_bounded(&mut cmd, limits).map_err(|e| e.to_string())?;
        if res.status != 0 {
            let stderr = String::from_utf8_lossy(&res.stderr);
            return Err(format!(
                "ResolutionError: PDF extraction failed: {}",
                stderr.trim()
            ));
        }
        self.size += res.stdout.len();
        let text = String::from_utf8_lossy(&res.stdout);
        Ok(text.lines().map(|s| s.to_string()).collect())
    }
}

pub fn locator_pattern(kind: &str, value: &str) -> Regex {
    let trimmed = value.trim().trim_end_matches(['.', ':']).trim();
    let base = if trimmed.is_empty() {
        value.trim()
    } else {
        trimmed
    };
    let kind_lower = kind.to_lowercase();
    let mut raw_tokens: Vec<&str> = base.split_whitespace().collect();
    if (kind_lower == "table" || kind_lower == "figure")
        && !raw_tokens
            .first()
            .is_some_and(|first| first.eq_ignore_ascii_case(&kind_lower))
    {
        raw_tokens.insert(0, &kind_lower);
    }

    let num_tokens = raw_tokens.len();
    let num_idx = usize::from(kind_lower == "table" || kind_lower == "figure");
    let token_regexes: Vec<String> = raw_tokens
        .into_iter()
        .enumerate()
        .map(|(idx, token)| {
            let cleaned = if idx == num_idx {
                token.trim_end_matches(['.', ':'])
            } else {
                token
            };
            let joined = cleaned
                .split(['-', '–'])
                .map(regex::escape)
                .collect::<Vec<_>>()
                .join("[-–]");
            if idx == num_idx && idx + 1 < num_tokens {
                format!("{joined}[.:]?")
            } else {
                joined
            }
        })
        .collect();
    let token_str = token_regexes.join(r"\s+");
    let pat = format!(
        r"(?i)(?:^|[^\w.])(?:{})(?:$|[^\w.\-–]|\.(?:\W|$)|[-–](?:\D|$))",
        token_str
    );
    RegexBuilder::new(&pat)
        .case_insensitive(true)
        .build()
        .unwrap()
}

pub enum DocReader {
    Pdf(PdfPages),
    NonPdf { lines: Option<Vec<String>> },
    Unpinned,
    ResolutionError(String),
}

pub struct CitationItem {
    pub doc: String,
    pub locator: Value,
    pub fact: String,
    pub status: String,
    /// PDF evidence as `(pdf_page, line_on_page, text)`.
    pub source: Vec<(usize, usize, String)>,
    /// Format the citation was resolved against: `"pdf"`, `"markdown"`, or empty when it was not
    /// resolved.
    pub format: &'static str,
    /// Markdown evidence as `(line_in_document, text)`, one entry per line of each matched section.
    pub lines: Vec<(usize, String)>,
    /// Text of each Markdown heading a `section` or `heading` locator matched.
    pub headings: Vec<String>,
}

impl CitationItem {
    fn new(doc: String, locator: Value, fact: String) -> Self {
        Self {
            doc,
            locator,
            fact,
            status: "failed".to_string(),
            source: Vec::new(),
            format: "",
            lines: Vec::new(),
            headings: Vec::new(),
        }
    }
}

/// Options for [`citations_with_options`].
#[derive(Debug, Clone, Copy, Default)]
pub struct DocResolveOptions {
    /// Report every skipped document citation as an error (`--fail-on-skipped-documents`).
    pub fail_on_skipped: bool,
}

pub const DOC_CLASSES: &[&str] = &[
    "databook",
    "datasheet",
    "errata",
    "appnote",
    "standard",
    "doc",
];

pub fn supports<'a>(
    data: &'a Value,
    base: Vec<String>,
    payload: bool,
    out: &mut Vec<(&'a Map<String, Value>, Vec<String>)>,
) {
    match data {
        Value::Object(map) => {
            for (key, value) in map {
                if key == "support" || key == "settled_by" {
                    if let Value::Array(arr) = value {
                        for (i, entry) in arr.iter().enumerate() {
                            if let Value::Object(entry_map) = entry {
                                let mut at = base.clone();
                                at.push(key.clone());
                                at.push(i.to_string());
                                out.push((entry_map, at));
                            }
                        }
                    }
                }
                let mut at = base.clone();
                at.push(key.clone());
                supports(value, at, false, out);
            }
            if payload {
                if let Some(data_map) = map.get("data").and_then(|v| v.as_object()) {
                    if let Some(_pair_map) = data_map.get("pair").and_then(|v| v.as_object()) {
                        // skip for docresolve
                    }
                }
            }
        }
        Value::Array(arr) => {
            for (i, value) in arr.iter().enumerate() {
                let mut at = base.clone();
                at.push(i.to_string());
                supports(value, at, false, out);
            }
        }
        _ => {}
    }
}

/// One Markdown heading: its 0-based line index, level (1-6) and raw text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MarkdownHeading {
    pub line: usize,
    pub level: usize,
    pub text: String,
}

fn fence_marker(line: &str) -> Option<(char, usize)> {
    let indent = line.len() - line.trim_start_matches(' ').len();
    if indent > 3 {
        return None;
    }
    let rest = &line[indent..];
    let ch = rest.chars().next()?;
    if ch != '`' && ch != '~' {
        return None;
    }
    let run = rest.chars().take_while(|c| *c == ch).count();
    if run < 3 {
        return None;
    }
    if ch == '`' && rest[run..].contains('`') {
        return None;
    }
    Some((ch, run))
}

fn atx_heading(line: &str) -> Option<(usize, String)> {
    let indent = line.len() - line.trim_start_matches(' ').len();
    if indent > 3 {
        return None;
    }
    let rest = &line[indent..];
    let level = rest.chars().take_while(|c| *c == '#').count();
    if level == 0 || level > 6 {
        return None;
    }
    let after = &rest[level..];
    if !(after.is_empty() || after.starts_with(' ') || after.starts_with('\t')) {
        return None;
    }
    let mut text = after.trim();
    // Optional closing sequence: a run of `#` preceded by whitespace (or the whole text).
    let without_hashes = text.trim_end_matches('#');
    if without_hashes.len() != text.len()
        && (without_hashes.is_empty() || without_hashes.ends_with([' ', '\t']))
    {
        text = without_hashes.trim_end();
    }
    Some((level, text.to_string()))
}

fn setext_level(line: &str) -> Option<usize> {
    let indent = line.len() - line.trim_start_matches(' ').len();
    if indent > 3 {
        return None;
    }
    let body = line.trim();
    if body.is_empty() {
        return None;
    }
    if body.chars().all(|c| c == '=') {
        Some(1)
    } else if body.chars().all(|c| c == '-') {
        Some(2)
    } else {
        None
    }
}

fn could_be_setext_text(line: &str) -> bool {
    let t = line.trim();
    if t.is_empty() || line.len() - line.trim_start_matches(' ').len() > 3 {
        return false;
    }
    !(t.starts_with("- ")
        || t.starts_with("* ")
        || t.starts_with("+ ")
        || t.starts_with('>')
        || t.starts_with('|')
        || t.starts_with('<')
        || ordered_list_marker(t))
}

fn ordered_list_marker(t: &str) -> bool {
    let digits = t.chars().take_while(char::is_ascii_digit).count();
    (1..=9).contains(&digits)
        && t[digits..].starts_with(['.', ')'])
        && t[digits + 1..]
            .chars()
            .next()
            .is_none_or(char::is_whitespace)
}

/// Lists the ATX (`# Title`) and setext (`Title` over `===`/`---`) headings of a Markdown
/// document, ignoring a leading YAML front matter block, HTML comments, and fenced code blocks.
pub fn markdown_headings(lines: &[String]) -> Vec<MarkdownHeading> {
    let mut out = Vec::new();
    let mut fence: Option<(char, usize)> = None;
    let mut in_comment = false;
    let mut prev_blank_or_heading = true;
    let mut i = 0;
    if lines
        .first()
        .is_some_and(|l| l.trim_start_matches('\u{feff}').trim_end() == "---")
    {
        if let Some(close) = lines[1..]
            .iter()
            .position(|l| matches!(l.trim_end(), "---" | "..."))
        {
            i = close + 2;
        }
    }
    while i < lines.len() {
        let line = lines[i].trim_start_matches('\u{feff}');
        if fence.is_none() && (in_comment || line.trim_start().starts_with("<!--")) {
            let after_open = if in_comment {
                line
            } else {
                &line[line.find("<!--").unwrap_or(0) + 4..]
            };
            in_comment = !after_open.contains("-->");
            i += 1;
            prev_blank_or_heading = true;
            continue;
        }
        if let Some((ch, run)) = fence {
            if let Some((c2, r2)) = fence_marker(line) {
                if c2 == ch && r2 >= run && line.trim().chars().all(|c| c == ch) {
                    fence = None;
                }
            }
            i += 1;
            prev_blank_or_heading = true;
            continue;
        }
        if let Some(marker) = fence_marker(line) {
            fence = Some(marker);
            i += 1;
            prev_blank_or_heading = true;
            continue;
        }
        if let Some((level, text)) = atx_heading(line) {
            out.push(MarkdownHeading {
                line: i,
                level,
                text,
            });
            i += 1;
            prev_blank_or_heading = true;
            continue;
        }
        if prev_blank_or_heading && could_be_setext_text(line) {
            if let Some(level) = lines.get(i + 1).and_then(|l| setext_level(l)) {
                out.push(MarkdownHeading {
                    line: i,
                    level,
                    text: line.trim().to_string(),
                });
                i += 2;
                prev_blank_or_heading = true;
                continue;
            }
        }
        prev_blank_or_heading = line.trim().is_empty();
        i += 1;
    }
    out
}

/// Normalizes heading or locator text for comparison: drops a trailing `{#anchor}`, backticks,
/// a leading `Section`/`§`, and trailing `.`/`:`; collapses whitespace; folds case.
pub fn markdown_heading_key(text: &str) -> String {
    static ANCHOR_RE: OnceLock<Regex> = OnceLock::new();
    let anchor_re =
        ANCHOR_RE.get_or_init(|| Regex::new(r"\s*\{#[^}]*\}\s*$").expect("valid regex"));
    static PREFIX_RE: OnceLock<Regex> = OnceLock::new();
    let prefix_re =
        PREFIX_RE.get_or_init(|| Regex::new(r"(?i)^(?:section\s+|§\s*)(\d)").expect("valid regex"));
    let stripped = anchor_re.replace(text, "");
    let collapsed = stripped
        .replace('`', "")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase();
    let unprefixed = prefix_re.replace(&collapsed, "$1");
    unprefixed.trim_end_matches(['.', ':']).trim().to_string()
}

/// Splits a normalized key into an optional numeric prefix (`9`, `9.2.1`) and an optional title.
///
/// A number is a section number when it is dotted (`9.2 Foo`), punctuated (`9. Foo`, `9) Foo`),
/// or the whole key (`9`). A bare leading integer followed by words (`64 KiB SRAM`) is part of
/// the title.
fn split_numeric_prefix(key: &str) -> (Option<String>, Option<String>) {
    static NUM_RE: OnceLock<Regex> = OnceLock::new();
    let num_re = NUM_RE
        .get_or_init(|| Regex::new(r"^(\d+(?:\.\d+)*)([.:)])?(?:\s+(.*))?$").expect("valid regex"));
    let whole_title = || (None, Some(key.to_string()).filter(|t| !t.is_empty()));
    let Some(caps) = num_re.captures(key) else {
        return whole_title();
    };
    let num = &caps[1];
    let punctuated = caps.get(2).is_some();
    let title = caps
        .get(3)
        .map(|m| m.as_str().trim().to_string())
        .filter(|t| !t.is_empty());
    if title.is_some() && !punctuated && !num.contains('.') {
        return whole_title();
    }
    (Some(num.to_string()), title)
}

/// How a locator matched a heading.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HeadingMatch {
    None,
    /// The normalized texts are equal.
    Exact,
    /// Equal once a numeric prefix present on only one side, or the title, is set aside: `Foo`
    /// matches `9. Foo`, and `9.2` matches `9.2 Bar`. Two different numbers never match.
    NumericPrefix,
}

pub fn match_markdown_heading(locator: &str, heading: &str) -> HeadingMatch {
    let lk = markdown_heading_key(locator);
    let hk = markdown_heading_key(heading);
    if lk.is_empty() {
        return HeadingMatch::None;
    }
    if lk == hk {
        return HeadingMatch::Exact;
    }
    let (ln, lt) = split_numeric_prefix(&lk);
    let (hn, ht) = split_numeric_prefix(&hk);
    let numbers_agree = match (&ln, &hn) {
        (Some(a), Some(b)) => a == b,
        _ => true,
    };
    let matched = match (&lt, &ht) {
        (Some(a), Some(b)) => a == b && numbers_agree,
        (None, _) => ln.is_some() && ln == hn,
        (Some(_), None) => false,
    };
    if matched {
        HeadingMatch::NumericPrefix
    } else {
        HeadingMatch::None
    }
}

/// Finds the section a `section` or `heading` locator names: the first heading that matches
/// exactly, else the first that matches ignoring a numeric prefix. Returns the heading, the
/// 0-based, end-exclusive line range up to the next heading of the same or a higher level, and
/// how many headings matched equally well (more than one means the locator is ambiguous).
pub fn find_markdown_section<'a>(
    headings: &'a [MarkdownHeading],
    total_lines: usize,
    locator: &str,
) -> Option<(&'a MarkdownHeading, usize, usize, usize)> {
    let pick = |want: HeadingMatch| -> Vec<usize> {
        headings
            .iter()
            .enumerate()
            .filter(|(_, h)| match_markdown_heading(locator, &h.text) == want)
            .map(|(i, _)| i)
            .collect()
    };
    let mut found = pick(HeadingMatch::Exact);
    if found.is_empty() {
        found = pick(HeadingMatch::NumericPrefix);
    }
    let idx = *found.first()?;
    let heading = &headings[idx];
    let end = headings[idx + 1..]
        .iter()
        .find(|h| h.level <= heading.level)
        .map_or(total_lines, |h| h.line);
    Some((heading, heading.line, end, found.len()))
}

fn locator_text(v: &Value) -> Option<String> {
    match v {
        Value::String(s) => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        _ => None,
    }
}

fn path_is_markdown(s: &str) -> bool {
    let path_part = s.split(['?', '#']).next().unwrap_or(s).to_ascii_lowercase();
    path_part.ends_with(".md") || path_part.ends_with(".markdown")
}

pub struct DocCitationsResult {
    pub items: Vec<CitationItem>,
    pub own_lines: Vec<String>,
    pub pdf_own_lines: Vec<String>,
    /// Lines of the Markdown sections the record's own `support` resolved.
    pub markdown_own_lines: Vec<String>,
    pub has_unextracted_own_doc: bool,
}

pub fn citations<F>(
    record: &Value,
    base: Vec<String>,
    documents: &mut HashMap<String, (Value, DocReader)>,
    add: F,
) -> (Vec<CitationItem>, Vec<String>)
where
    F: FnMut(Vec<String>, String, &str),
{
    let res = citations_with_status(record, base, documents, add);
    (res.items, res.own_lines)
}

pub fn citations_with_status<F>(
    record: &Value,
    base: Vec<String>,
    documents: &mut HashMap<String, (Value, DocReader)>,
    add: F,
) -> DocCitationsResult
where
    F: FnMut(Vec<String>, String, &str),
{
    citations_with_options(record, base, documents, DocResolveOptions::default(), add)
}

/// Resolves a record's document citations against the pinned files in `documents`.
///
/// PDF citations resolve by page; Markdown citations resolve by `section` or `heading` locator
/// against the document's headings. A document counts as Markdown when its name or URL ends in
/// `.md`/`.markdown` or its text has a heading; a locator matching no heading is an error for a
/// document declared as Markdown and a skip (with a warning) for one recognized by its text. Skips are reported through `add` as warnings (errors with
/// [`DocResolveOptions::fail_on_skipped`]); a skip that is expected for the document's format
/// (a non-PDF, non-Markdown file, a locator with no section or heading) is reported only with
/// that option.
pub fn citations_with_options<F>(
    record: &Value,
    base: Vec<String>,
    documents: &mut HashMap<String, (Value, DocReader)>,
    opts: DocResolveOptions,
    mut add: F,
) -> DocCitationsResult
where
    F: FnMut(Vec<String>, String, &str),
{
    let skip_level = if opts.fail_on_skipped {
        "error"
    } else {
        "warning"
    };
    let mut items = Vec::new();
    let mut own_lines = Vec::new();
    let mut pdf_own_lines = Vec::new();
    let mut markdown_own_lines: Vec<String> = Vec::new();
    let mut has_unextracted_own_doc = false;
    let mut supports_list = Vec::new();
    supports(record, base.clone(), false, &mut supports_list);

    let fact_id = record
        .get("id")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let mut expected_support = base.clone();
    expected_support.push("support".to_string());

    for (support, at) in supports_list {
        let cls = match support.get("class").and_then(|v| v.as_str()) {
            Some(c) => c,
            None => continue,
        };
        if !DOC_CLASSES.contains(&cls) {
            continue;
        }
        let is_own_support = !at.is_empty() && at[..at.len() - 1] == expected_support;
        let name = match support.get("doc").and_then(|v| v.as_str()) {
            Some(n) => n.to_string(),
            None => {
                if is_own_support {
                    has_unextracted_own_doc = true;
                }
                continue;
            }
        };

        let at_locators = match support.get("at").and_then(|v| v.as_array()) {
            Some(arr) => arr.clone(),
            None => Vec::new(),
        };
        if at_locators.is_empty() && is_own_support {
            has_unextracted_own_doc = true;
        }

        for (index, locator) in at_locators.iter().enumerate() {
            let mut where_at = at.clone();
            where_at.push("at".to_string());
            where_at.push(index.to_string());

            let mut item = CitationItem::new(name.clone(), locator.clone(), fact_id.clone());

            let doc_entry = documents.get_mut(&name);
            let (doc_info, reader_state) = match doc_entry {
                Some(entry) => entry,
                None => {
                    if is_own_support {
                        has_unextracted_own_doc = true;
                    }
                    item.status = "skipped".to_string();
                    add(
                        where_at.clone(),
                        format!(
                            "{}: {}: PDF evidence skipped: document is not declared",
                            fact_id, name
                        ),
                        skip_level,
                    );
                    items.push(item);
                    continue;
                }
            };

            let has_pdf_url = ["url", "retrieval"].iter().any(|k| {
                doc_info.get(*k).and_then(|v| v.as_str()).is_some_and(|u| {
                    let path_part = u.split(['?', '#']).next().unwrap_or(u);
                    path_part.to_ascii_lowercase().ends_with(".pdf")
                })
            });
            let is_pdf_doc = doc_info.get("page_numbering").and_then(|v| v.as_str()) == Some("pdf")
                || doc_info.get("pages").is_some()
                || has_pdf_url;
            let has_page_locator = locator.get("page").is_some() || locator.get("pages").is_some();
            let declared_markdown = path_is_markdown(&name)
                || ["url", "retrieval"].iter().any(|k| {
                    doc_info
                        .get(*k)
                        .and_then(|v| v.as_str())
                        .is_some_and(path_is_markdown)
                });

            let mut extracted_own = false;
            let result: Result<(), String> = (|| {
                let reader = match reader_state {
                    DocReader::Pdf(r) => r,
                    DocReader::ResolutionError(e) => {
                        if e.starts_with("ResolutionError:") {
                            return Err(e.clone());
                        }
                        return Err(format!("ResolutionError: {}", e));
                    }
                    DocReader::Unpinned => {
                        if is_pdf_doc || has_page_locator {
                            return Err("LimitExceeded: document has no sha256 pin".to_string());
                        }
                        return Err("Skipped: document has no sha256 pin".to_string());
                    }
                    DocReader::NonPdf { lines } => {
                        if is_pdf_doc || has_page_locator {
                            return Err("LimitExceeded: document is not a PDF".to_string());
                        }
                        let Some(doc_lines) = lines else {
                            return Err("Skipped: document is not UTF-8 text within the size cap"
                                .to_string());
                        };
                        let headings = markdown_headings(doc_lines);
                        let is_markdown = declared_markdown || !headings.is_empty();
                        let wanted: Vec<(&str, String)> = ["heading", "section"]
                            .iter()
                            .filter_map(|k| locator.get(*k).and_then(locator_text).map(|v| (*k, v)))
                            .collect();
                        if !is_markdown || wanted.is_empty() {
                            if is_own_support {
                                own_lines.extend(doc_lines.iter().cloned());
                                extracted_own = true;
                            }
                            return Err(if is_markdown {
                                "Skipped: locator names no section or heading".to_string()
                            } else {
                                "Skipped: document is neither a PDF nor Markdown".to_string()
                            });
                        }
                        let mut spans: Vec<(usize, usize, String)> = Vec::new();
                        for (kind, value) in &wanted {
                            let Some((heading, start, end, candidates)) =
                                find_markdown_section(&headings, doc_lines.len(), value)
                            else {
                                // Only a document declared as Markdown (by name or URL) fails;
                                // one recognized by its headings alone may be another format.
                                let prefix = if declared_markdown {
                                    "ResolutionError"
                                } else {
                                    "SkippedWarn"
                                };
                                return Err(format!(
                                    "{prefix}: {kind} {value:?} matches no Markdown heading"
                                ));
                            };
                            if candidates > 1 {
                                let mut warn_where = where_at.clone();
                                warn_where.push(kind.to_string());
                                add(
                                    warn_where,
                                    format!(
                                        "{}: {}: {} {:?} is ambiguous: it matches {} Markdown headings; using the first, at line {}",
                                        fact_id,
                                        name,
                                        kind,
                                        value,
                                        candidates,
                                        start + 1
                                    ),
                                    "warning",
                                );
                            }
                            // Keep only spans not already covered by another (a heading
                            // inside a cited section adds nothing).
                            if spans.iter().any(|&(s, e, _)| s <= start && end <= e) {
                                continue;
                            }
                            spans.retain(|&(s, e, _)| !(start <= s && e <= end));
                            spans.push((start, end, heading.text.clone()));
                        }
                        spans.sort_unstable();
                        item.headings = spans.iter().map(|(_, _, h)| h.clone()).collect();
                        let mut section_lines: Vec<String> = Vec::new();
                        for &(start, end, _) in &spans {
                            for (n, line) in doc_lines[start..end].iter().enumerate() {
                                item.lines.push((start + n + 1, line.clone()));
                                section_lines.push(line.clone());
                            }
                        }
                        let text = section_lines.join("\n");
                        for kind in ["table", "figure"] {
                            if let Some(value) = locator.get(kind).and_then(locator_text) {
                                if locator_pattern(kind, &value).is_match(&text) {
                                    continue;
                                }
                                let mut warn_where = where_at.clone();
                                warn_where.push(kind.to_string());
                                add(
                                    warn_where,
                                    format!(
                                        "{}: {}: {} {:?} absent from cited Markdown section",
                                        fact_id, name, kind, value
                                    ),
                                    "warning",
                                );
                            }
                        }
                        item.format = "markdown";
                        item.status = "resolved".to_string();
                        if is_own_support {
                            markdown_own_lines.extend(section_lines.iter().cloned());
                            own_lines.extend(section_lines);
                            extracted_own = true;
                        }
                        return Ok(());
                    }
                };

                let page_numbering = doc_info.get("page_numbering").and_then(|v| v.as_str());
                if page_numbering != Some("pdf") {
                    return Err("LimitExceeded: page_numbering is not pdf".to_string());
                }

                let bounds = if let Some(pages) = locator.get("pages").and_then(|v| v.as_array()) {
                    vec![
                        pages.first().unwrap_or(&Value::Null).clone(),
                        pages.get(1).unwrap_or(&Value::Null).clone(),
                    ]
                } else {
                    let page = locator.get("page").unwrap_or(&Value::Null).clone();
                    vec![page.clone(), page]
                };

                let mut normalized = Vec::new();
                for b in &bounds {
                    let s = match b.as_str() {
                        Some(s) if s.is_ascii() && s.chars().all(|c| c.is_ascii_digit()) => s,
                        _ => {
                            return Err(
                                "LimitExceeded: locator needs numeric PDF page(s)".to_string()
                            )
                        }
                    };
                    let stripped = s.trim_start_matches('0');
                    let norm = if stripped.is_empty() { "0" } else { stripped };
                    if norm.len() > 10 || (norm.len() == 10 && norm > "2147483647") {
                        return Err(
                            "ResolutionError: PDF page exceeds extractor integer range".to_string()
                        );
                    }
                    normalized.push(norm.to_string());
                }

                let first: usize = normalized[0].parse().unwrap();
                let last: usize = normalized[1].parse().unwrap();
                let count = doc_info
                    .get("pages")
                    .and_then(|v| v.as_u64())
                    .map(|n| n as usize);

                if first < 1 || last < first || count.is_some_and(|c| last > c) {
                    return Err(
                        "ResolutionError: PDF page range outside declared pages".to_string()
                    );
                }

                let mut lines = Vec::new();
                for page in first..=last {
                    let page_lines = reader.page(page).map_err(|e| {
                        if e.starts_with("ResolutionError:") {
                            e
                        } else {
                            format!("ResolutionError: {}", e)
                        }
                    })?;
                    for (n, line) in page_lines.iter().enumerate() {
                        item.source.push((page, n + 1, line.clone()));
                    }
                    lines.extend(page_lines);
                }

                if !lines.iter().any(|l| !l.trim().is_empty()) {
                    return Err(
                        "LimitExceeded: cited PDF pages have no extractable text".to_string()
                    );
                }

                let text = lines.join("\n");
                for kind in ["section", "table", "figure"] {
                    if let Some(locator_kind) = locator.get(kind).and_then(|v| v.as_str()) {
                        let pattern = locator_pattern(kind, locator_kind);
                        if pattern.is_match(&text) {
                            continue;
                        }

                        let mut nearby = Vec::new();
                        for &page in &[first.saturating_sub(1), last + 1] {
                            if page < 1 || count.is_some_and(|c| page > c) {
                                continue;
                            }
                            if let Ok(page_lines) = reader.page(page) {
                                let page_text = page_lines.join("\n");
                                if pattern.is_match(&page_text) {
                                    nearby.push(page.to_string());
                                }
                            }
                        }

                        let suffix = if !nearby.is_empty() {
                            format!("; found on adjacent PDF page(s): {}", nearby.join(", "))
                        } else {
                            "".to_string()
                        };

                        let mut warn_where = where_at.clone();
                        warn_where.push(kind.to_string());
                        add(
                            warn_where,
                            format!(
                                "{}: {}: {} {:?} absent from cited PDF pages{}",
                                fact_id, name, kind, locator_kind, suffix
                            ),
                            "warning",
                        );
                    }
                }

                item.format = "pdf";
                item.status = "resolved".to_string();

                if is_own_support {
                    pdf_own_lines.extend(lines.iter().cloned());
                    own_lines.extend(lines);
                    extracted_own = true;
                }

                Ok(())
            })();

            if is_own_support && !extracted_own {
                has_unextracted_own_doc = true;
            }

            match result {
                Ok(_) => {}
                Err(e) => {
                    if let Some(reason) = e.strip_prefix("SkippedWarn:") {
                        item.status = "skipped".to_string();
                        add(
                            where_at.clone(),
                            format!(
                                "{}: {}: document evidence skipped: {}",
                                fact_id,
                                name,
                                reason.trim()
                            ),
                            skip_level,
                        );
                    } else if let Some(reason) = e.strip_prefix("Skipped:") {
                        // Expected for the document's format: silent unless skips must fail.
                        item.status = "skipped".to_string();
                        if opts.fail_on_skipped {
                            add(
                                where_at.clone(),
                                format!(
                                    "{}: {}: document evidence skipped: {}",
                                    fact_id,
                                    name,
                                    reason.trim()
                                ),
                                "error",
                            );
                        }
                    } else if e.starts_with("LimitExceeded:") {
                        item.status = "skipped".to_string();
                        add(
                            where_at.clone(),
                            format!(
                                "{}: {}: PDF evidence skipped: {}",
                                fact_id,
                                name,
                                e.trim_start_matches("LimitExceeded: ").trim()
                            ),
                            skip_level,
                        );
                    } else if e.starts_with("ResolutionError:") {
                        add(
                            where_at.clone(),
                            format!(
                                "{}: {}: {}",
                                fact_id,
                                name,
                                e.trim_start_matches("ResolutionError: ").trim()
                            ),
                            "error",
                        );
                    } else {
                        item.status = "skipped".to_string();
                        add(
                            where_at.clone(),
                            format!("{}: {}: PDF evidence skipped: {}", fact_id, name, e),
                            skip_level,
                        );
                    }
                }
            }

            items.push(item);
        }
    }

    // The register-offset check the PDF path gets in `resolve`, for Markdown sections.
    if !markdown_own_lines.is_empty() {
        if let Some(offset_str) = record
            .get("data")
            .and_then(|d| d.get("register"))
            .and_then(|r| r.get("offset"))
            .and_then(Value::as_str)
        {
            let offset_hex = crate::resolve::hex_values(offset_str);
            let section_hex = crate::resolve::hex_values(&markdown_own_lines.join("\n"));
            if !offset_hex.is_subset(&section_hex) {
                let mut off_at = base.clone();
                off_at.extend(["data", "register", "offset"].map(String::from));
                add(
                    off_at,
                    format!("register offset absent from cited Markdown sections: {offset_str}"),
                    "warning",
                );
            }
        }
    }

    DocCitationsResult {
        items,
        own_lines,
        pdf_own_lines,
        markdown_own_lines,
        has_unextracted_own_doc,
    }
}

pub fn hex_values(text: &str) -> Vec<String> {
    let mut values = Vec::new();
    let re1 = Regex::new(r"0[xX][0-9a-fA-F_']+").unwrap();
    for cap in re1.captures_iter(text) {
        values.push(cap[0].to_string());
    }
    let re2 = Regex::new(r"\b(?:[0-9][0-9A-Fa-f_]*|[0-9A-F][0-9A-F_]+)[hH]\b").unwrap();
    for cap in re2.captures_iter(text) {
        values.push(cap[0].to_string());
    }
    values
}

/// Extracts and normalizes hex values in document text (`0x...` and vendor `h`-suffix notation)
/// to integer `u64` values (`BF-IMX-ISS-7`, `BF-IMX-16`).
pub fn hex_values_u64(text: &str) -> std::collections::BTreeSet<u64> {
    let mut set = std::collections::BTreeSet::new();
    let re1 = Regex::new(r"(?i)\b0x([0-9a-f](?:[0-9a-f_']*[0-9a-f])?)(?:u(?:ll|l)?|(?:ll|l)u?)?\b")
        .unwrap();
    for cap in re1.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            let s = m.as_str().replace(['_', '\''], "");
            if let Ok(v) = u64::from_str_radix(&s, 16) {
                set.insert(v);
            }
        }
    }
    let re2 = Regex::new(r"\b([0-9][0-9A-Fa-f_]*|[0-9A-F][0-9A-F_]+)[hH]\b").unwrap();
    for cap in re2.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            let s = m.as_str().replace('_', "");
            if let Ok(v) = u64::from_str_radix(&s, 16) {
                set.insert(v);
            }
        }
    }
    set
}

/// Checks whether a cited `section` locator on `[first_page, last_page]` is covered by a verified
/// `<root>/index/<doc>.index.yaml` entry (`BF-IMX-ISS-6` part 1, `BF-IMX-17`).
pub fn section_covered_by_index(
    index_data: &Value,
    expected_doc_sha256: Option<&str>,
    section_locator: &str,
    first_page: usize,
    last_page: usize,
) -> Result<bool, String> {
    let idx_sha = index_data
        .get("sha256")
        .and_then(Value::as_str)
        .unwrap_or("");
    if let Some(expected) = expected_doc_sha256 {
        if !expected.is_empty() && idx_sha != expected {
            return Err(format!(
                "stale index: index sha256 ({idx_sha}) does not match document sha256 ({expected})"
            ));
        }
    }
    let Some(sections) = index_data.get("sections").and_then(Value::as_array) else {
        return Ok(false);
    };
    let (cited_title, cited_num) = crate::index::normalize_cited_section(section_locator);

    for entry in sections {
        let Some(obj) = entry.as_object() else {
            continue;
        };
        let (start_p, end_p) = if let Some(arr) = obj.get("pages").and_then(Value::as_array) {
            if arr.len() == 2 {
                (
                    arr[0].as_u64().map(|n| n as usize),
                    arr[1].as_u64().map(|n| n as usize),
                )
            } else {
                (None, None)
            }
        } else {
            let sp = obj
                .get("start_page")
                .or_else(|| obj.get("page"))
                .and_then(Value::as_u64)
                .map(|n| n as usize);
            let ep = obj
                .get("end_page")
                .and_then(Value::as_u64)
                .map(|n| n as usize)
                .or(sp);
            (sp, ep)
        };
        let (Some(sp), Some(ep)) = (start_p, end_p) else {
            continue;
        };
        if !(sp <= first_page && last_page <= ep) {
            continue;
        }
        let num_match = cited_num.as_ref().is_some_and(|cn| {
            obj.get("number")
                .and_then(Value::as_str)
                .and_then(|s| {
                    crate::index::normalize_cited_section(s)
                        .1
                        .or_else(|| Some(s.trim().to_string()))
                })
                .as_ref()
                .is_some_and(|sn| sn.eq_ignore_ascii_case(cn))
        });
        let title_match = !cited_title.is_empty()
            && obj
                .get("title")
                .and_then(Value::as_str)
                .map(|s| crate::index::normalize_cited_section(s).0)
                .as_deref()
                .is_some_and(|st| st.eq_ignore_ascii_case(&cited_title));
        if num_match || title_match {
            return Ok(true);
        }
    }
    Ok(false)
}
