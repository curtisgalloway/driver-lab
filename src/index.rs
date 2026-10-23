// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Document outline and section indexer (`src/index.rs`, `RT-5`).
//!
//! Port of `skills/spec-format/scripts/index.py` plus normative fixes:
//! - `BF-USB-3`: Empty-password PDF Standard Security Handler Revisions 2–6 (RC4, AES-128, AES-256)
//!   via `src/pdf.rs`.
//! - `BF-USB-4`, `BF-IMX-10`, `BF-ARM-20`: Section `number` extraction for `Chapter N`,
//!   `Section N`, `Appendix X`, `Part N`, Arm alphanumeric sections (`A1`, `A1.2`, `B2.41`), and
//!   top-level single-letter appendices (`A`, `B`, ...) while preserving `UNIT` exclusion for
//!   quantities (`12 MHz clock`, `5 V supply`, `64 bit mode`).
//! - `BF-IMX-8`: HTML heading extraction (`<h1>`–`<h6>`) via `scraper` (`html5ever`).
//! - `BF-GW-22`: Trac/MoinMoin wiki heading fallback (`= Heading =` / `= Heading`) when a plain-text
//!   or Markdown document has zero ATX headings.
//! - `BF-IMX-9`: Shared boundary-page disambiguation and normalized `section:` matching in
//!   [`links`].
//! - `ENV-3`: Atomic file writes staged in scratch space so no dotfile is ever left in `work/`.

use crate::diagnostic::{visible_name, ExitCode, Finding};
use crate::pdf::{clean_outline_title, is_pdf_bytes, read_pdf_metadata, DEFAULT_MAX_OUTLINE_DEPTH};
use crate::sandbox::{AtomicFileWriter, ScratchResolver};
use crate::yaml_strict::{self, Loaded, PathSegment};
use comrak::nodes::{AstNode, NodeValue};
use comrak::{Arena, Options};
use regex::Regex;
use scraper::{ElementRef, Html, Selector};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

/// Subdirectory under a spec root holding `<doc>.index.yaml` files.
pub const DIR: &str = "index";

/// File suffix for generated document section indexes.
pub const SUFFIX: &str = ".index.yaml";

/// Maximum heading/outline nesting depth (`1..=6`).
pub const MAX_DEPTH: usize = DEFAULT_MAX_OUTLINE_DEPTH;

/// Maximum input size for Markdown, HTML, or wiki text documents (10 MiB).
pub const MAX_MD_BYTES: usize = 10 * 1024 * 1024;

/// Error returned when a document cannot be indexed (`exit 1`, code `IDX-NOT-INDEXABLE`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NotIndexable(pub String);

impl fmt::Display for NotIndexable {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for NotIndexable {}

/// One indexed section entry in `<doc>.index.yaml`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IndexSection {
    /// Extracted section number (e.g., `"1"`, `"6.1"`, `"A"`, `"B2.41"`, `"Part 1"`), if any.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub number: Option<String>,
    /// Cleaned single-line NFC title.
    pub title: String,
    /// 1-based depth level (`1..=6`).
    pub level: usize,
    /// 1-based inclusive `[start_page, end_page]` span for PDF documents.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pages: Option<[usize; 2]>,
    /// 1-based inclusive `[start_line, end_line]` span for Markdown/HTML/wiki documents.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub lines: Option<[usize; 2]>,
}

impl IndexSection {
    /// Converts this section to a JSON/YAML [`Value`] object.
    #[must_use]
    pub fn to_value(&self) -> Value {
        let mut map = Map::new();
        map.insert("level".to_string(), json!(self.level));
        if let Some(lines) = self.lines {
            map.insert("lines".to_string(), json!([lines[0], lines[1]]));
        }
        if let Some(ref num) = self.number {
            map.insert("number".to_string(), json!(num));
        }
        if let Some(pages) = self.pages {
            map.insert("pages".to_string(), json!([pages[0], pages[1]]));
        }
        map.insert("title".to_string(), json!(self.title));
        Value::Object(map)
    }

    /// Parses an [`IndexSection`] from a JSON/YAML [`Value`] object.
    pub fn from_value(v: &Value) -> Option<Self> {
        let obj = v.as_object()?;
        let title = obj.get("title")?.as_str()?.to_string();
        let level = obj.get("level")?.as_u64()? as usize;
        let number = obj
            .get("number")
            .and_then(Value::as_str)
            .map(ToString::to_string);
        let pages = obj.get("pages").and_then(Value::as_array).and_then(|arr| {
            if arr.len() == 2 {
                Some([arr[0].as_u64()? as usize, arr[1].as_u64()? as usize])
            } else {
                None
            }
        });
        let lines = obj.get("lines").and_then(Value::as_array).and_then(|arr| {
            if arr.len() == 2 {
                Some([arr[0].as_u64()? as usize, arr[1].as_u64()? as usize])
            } else {
                None
            }
        });
        Some(Self {
            number,
            title,
            level,
            pages,
            lines,
        })
    }
}

/// Complete `<doc>.index.yaml` data model.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DocumentIndex {
    /// Format version (`2`).
    pub format: usize,
    /// Document identifier matching `resources.documents[].name`.
    pub document: String,
    /// Lowercase 64-character hex SHA-256 of the indexed document bytes.
    pub sha256: String,
    /// Document source kind (`"pdf"` or `"markdown"`).
    pub source: String,
    /// Total PDF page count when `source == "pdf"`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pages: Option<usize>,
    /// Total line count when `source == "markdown"`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub lines: Option<usize>,
    /// Ordered section entries.
    pub sections: Vec<IndexSection>,
}

impl DocumentIndex {
    /// Converts this [`DocumentIndex`] to a [`Value`] matching `index.schema.json`.
    #[must_use]
    pub fn to_value(&self) -> Value {
        let mut map = Map::new();
        map.insert("format".to_string(), json!(self.format));
        map.insert("document".to_string(), json!(self.document));
        map.insert("sha256".to_string(), json!(self.sha256));
        map.insert("source".to_string(), json!(self.source));
        if let Some(pages) = self.pages {
            map.insert("pages".to_string(), json!(pages));
        }
        if let Some(lines) = self.lines {
            map.insert("lines".to_string(), json!(lines));
        }
        map.insert(
            "sections".to_string(),
            Value::Array(self.sections.iter().map(IndexSection::to_value).collect()),
        );
        Value::Object(map)
    }

    /// Parses a [`DocumentIndex`] from a loaded JSON/YAML [`Value`].
    pub fn from_value(v: &Value) -> Option<Self> {
        let obj = v.as_object()?;
        let format = obj.get("format")?.as_u64()? as usize;
        let document = obj.get("document")?.as_str()?.to_string();
        let sha256 = obj.get("sha256")?.as_str()?.to_string();
        let source = obj.get("source")?.as_str()?.to_string();
        let pages = obj.get("pages").and_then(Value::as_u64).map(|n| n as usize);
        let lines = obj.get("lines").and_then(Value::as_u64).map(|n| n as usize);
        let sections_arr = obj.get("sections")?.as_array()?;
        let mut sections = Vec::with_capacity(sections_arr.len());
        for item in sections_arr {
            sections.push(IndexSection::from_value(item)?);
        }
        Some(Self {
            format,
            document,
            sha256,
            source,
            pages,
            lines,
            sections,
        })
    }
}

/// Normalizes a raw heading or bookmark title into a single-line NFC string free of characters
/// refused by the strict YAML loader (`index.py:title`).
#[must_use]
pub fn title(text: &str) -> String {
    clean_outline_title(text)
}

fn part_prefix_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)^Part\s+([0-9A-Z]+)(?:[.:]|\b)\s+\S").expect("valid regex"))
}

fn named_prefix_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"(?i)^(?:Chapter|Section|Appendix)\s+([0-9A-Z]+(?:\.[0-9]+)*)(?:[.:]|\b)\s+\S")
            .expect("valid regex")
    })
}

fn direct_number_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"^((?:[0-9]+|[A-Z][0-9]*)(?:\.[0-9]+)+|[A-Z][0-9]+|[0-9]+)\.?\s+\S")
            .expect("valid regex")
    })
}

fn single_letter_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^([A-Z])(\.)?\s+\S").expect("valid regex"))
}

/// Measurement units exclusion regex (`index.py:UNIT`).
///
/// Case-sensitive: `"5 V supply"` and `"12 MHz clock"` are quantities, whereas
/// `"1 A Note on Errata"`, `"4 V Series Boards"`, `"2 Pins"`, and `"5 V-Bus"` are sections.
fn unit_prefix_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"^(?:(?:[kMG]Hz|Hz|[mu\u{00b5}]V|[mu\u{00b5}]A|[kKMG]i?B|bits?|bytes?|[kKMG]bps|[mun\u{00b5}p]s|%|x)(?:\s|$|[,.;:)])|[VABs](?:\s+[a-z]|\s*$|[,.;:)]))",
        )
        .expect("valid regex")
    })
}

/// Extracts a standalone section number from `name` (`BF-USB-4`, `BF-IMX-10`, `BF-ARM-20`).
#[must_use]
pub fn extract_section_number(name: &str) -> Option<String> {
    if let Some(caps) = part_prefix_re().captures(name) {
        return Some(format!("Part {}", &caps[1]));
    }
    if let Some(caps) = named_prefix_re().captures(name) {
        return Some(caps[1].to_string());
    }
    if let Some(caps) = direct_number_re().captures(name) {
        let num = &caps[1];
        let is_bare_integer = num.bytes().all(|b| b.is_ascii_digit());
        if is_bare_integer {
            let m = caps.get(1).expect("group 1");
            let rest = name[m.end()..].trim_start();
            if unit_prefix_re().is_match(rest) {
                return None;
            }
        }
        return Some(num.to_string());
    }
    None
}

/// Promotes top-level single-letter appendix headings (`A Title`, `B Title`, `A. Title`) when
/// supported by document structure (`BF-USB-4`, `BF-IMX-10`):
/// - Any heading `^([A-Z])\.?\s+\S` whose descendant section has a number starting with
///   `<letter>.` or `<letter><digit>` (e.g., `"A Release Notes"` followed by `"A.1 Overview"`).
/// - Any level-1 heading with an explicit dot (`"A. AArch32..."`) after a numbered chapter, or a
///   level-1 single-letter heading after numbered chapters (excluding bare `"A"` and `"I"` without
///   a dot unless followed by another single-letter appendix sibling like `"B ..."`).
fn promote_single_letter_appendices(sections: &mut [IndexSection]) {
    let len = sections.len();
    let mut seen_numbered_level1 = false;

    for i in 0..len {
        if sections[i].level == 1 && sections[i].number.is_some() {
            seen_numbered_level1 = true;
            continue;
        }
        if sections[i].number.is_some() {
            continue;
        }
        let Some(caps) = single_letter_re().captures(&sections[i].title) else {
            continue;
        };
        let letter = caps[1].to_string();
        let has_dot = caps.get(2).is_some();
        let base_level = sections[i].level;

        // Check if any descendant under this section is numbered `<letter>.<n>` or `<letter><n>`.
        let dot_prefix = format!("{letter}.");
        let mut has_matching_child = false;
        for later in &sections[i + 1..] {
            if later.level <= base_level {
                break;
            }
            if let Some(ref child_num) = later.number {
                if child_num.starts_with(&dot_prefix)
                    || (child_num.starts_with(&letter)
                        && child_num[letter.len()..]
                            .bytes()
                            .next()
                            .is_some_and(|b| b.is_ascii_digit()))
                {
                    has_matching_child = true;
                    break;
                }
            }
        }

        if has_matching_child {
            sections[i].number = Some(letter);
            if base_level == 1 {
                seen_numbered_level1 = true;
            }
            continue;
        }

        if base_level == 1 && seen_numbered_level1 {
            // If letter is 'A' or 'I' without a dot, check if a subsequent level-1 sibling is 'B'
            // or 'J' (e.g., `A Liquid Corrosion...`, `B Debug Accessory Mode` in `usb-type-c`).
            let next_expected = match letter.as_str() {
                "A" => Some("B"),
                "I" => Some("J"),
                _ => None,
            };
            let allowed = if let Some(next_let) = next_expected {
                has_dot
                    || sections[i + 1..].iter().filter(|s| s.level == 1).any(|s| {
                        single_letter_re()
                            .captures(&s.title)
                            .is_some_and(|c| &c[1] == next_let)
                    })
            } else {
                true
            };
            if allowed {
                sections[i].number = Some(letter);
            }
        }
    }
}

/// Builds a single [`IndexSection`] with `pages` or `lines` span (`index.py:section`).
#[must_use]
pub fn section(name: &str, level: usize, rng: [usize; 2], key: &str) -> IndexSection {
    let number = extract_section_number(name);
    let (pages, lines) = if key == "pages" {
        (Some(rng), None)
    } else {
        (None, Some(rng))
    };
    IndexSection {
        number,
        title: name.to_string(),
        level,
        pages,
        lines,
    }
}

/// Indexes a PDF document from raw bytes (`index.py:from_pdf` + `BF-USB-3` + `BF-USB-4` +
/// `BF-IMX-10` + `BF-ARM-20`).
pub fn from_pdf(data: &[u8]) -> Result<(usize, Vec<IndexSection>), NotIndexable> {
    let meta = read_pdf_metadata(data, MAX_DEPTH)
        .map_err(|e| NotIndexable(format!("cannot read the PDF outline: {e}")))?;
    let count = meta.pages;
    let flat = meta.outline;
    if flat.is_empty() {
        return Err(NotIndexable(
            "the PDF has no outline (bookmarks) to index; an index is never guessed from page text"
                .to_string(),
        ));
    }

    let mut firsts: Vec<usize> = flat.iter().map(|e| e.page).collect();
    let mut lasts: Vec<usize> = Vec::with_capacity(flat.len());

    for (i, entry) in flat.iter().enumerate() {
        let mut last = count;
        for later in &flat[i + 1..] {
            if later.level <= entry.level && later.page >= entry.page {
                last = later.page; // next section may start part-way down this page
                break;
            }
        }
        lasts.push(entry.page.max(last));
    }

    // A parent covers its children in any page order (`index.py:115-119`).
    for i in (0..flat.len()).rev() {
        for j in (i + 1)..flat.len() {
            if flat[j].level <= flat[i].level {
                break;
            }
            firsts[i] = firsts[i].min(firsts[j]);
            lasts[i] = lasts[i].max(lasts[j]);
        }
    }

    let mut sections: Vec<IndexSection> = flat
        .iter()
        .enumerate()
        .map(|(i, e)| section(&e.title, e.level, [firsts[i], lasts[i]], "pages"))
        .collect();
    promote_single_letter_appendices(&mut sections);
    Ok((count, sections))
}

/// Returns `true` if `data` looks like an HTML document (`<!DOCTYPE html` or `<html` within the
/// first 4 KiB; `BF-IMX-8`).
#[must_use]
pub fn is_html_bytes(data: &[u8]) -> bool {
    let prefix = &data[..data.len().min(4096)];
    let s = String::from_utf8_lossy(prefix).to_ascii_lowercase();
    s.contains("<!doctype html") || s.contains("<html")
}

/// Normalizes `\r\n` and `\r` line breaks to `\n` and counts lines (`index.py:135`).
///
/// Only `\r\n`, `\r`, and `\n` are treated as line breaks (so `\x0c` form-feed does not start a
/// new line), and a single trailing line break at EOF ends the last line rather than starting an
/// empty line.
fn normalize_lines_and_count(text: &str) -> (String, usize) {
    let normalized = text.replace("\r\n", "\n").replace('\r', "\n");
    let trimmed = normalized.strip_suffix('\n').unwrap_or(&normalized);
    let count = trimmed.split('\n').count().max(1);
    (normalized, count)
}

/// Collects plain text inside a `scraper::ElementRef`, skipping Sphinx `.headerlink` anchors and
/// stripping trailing pilcrow (`¶`) permalink markers (`BF-IMX-8`).
fn html_heading_text(el: ElementRef<'_>) -> String {
    fn walk_el(el: ElementRef<'_>, out: &mut String) {
        if let Some(cls) = el.value().attr("class") {
            if cls.split_whitespace().any(|c| c == "headerlink") {
                return;
            }
        }
        for child in el.children() {
            if let Some(child_el) = ElementRef::wrap(child) {
                walk_el(child_el, out);
            } else if let scraper::Node::Text(t) = child.value() {
                out.push_str(&t.text);
            }
        }
    }

    let mut raw = String::new();
    walk_el(el, &mut raw);
    let cleaned = title(&raw);
    cleaned.trim_end_matches('\u{00B6}').trim().to_string()
}

/// Masks HTML comments (`<!-- ... -->`) and `<script>`/`<style>` blocks with spaces while
/// preserving `\n` line breaks so tag line numbers match DOM headings accurately.
fn mask_html_comments_and_scripts(normalized_html: &str) -> String {
    static MASK_RE: OnceLock<Regex> = OnceLock::new();
    let re = MASK_RE.get_or_init(|| {
        Regex::new(r"(?is)<!--.*?-->|<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>")
            .expect("valid regex")
    });
    let mut out = normalized_html.as_bytes().to_vec();
    for m in re.find_iter(normalized_html) {
        for b in &mut out[m.start()..m.end()] {
            if *b != b'\n' {
                *b = b' ';
            }
        }
    }
    String::from_utf8(out).unwrap_or_else(|_| normalized_html.to_string())
}

/// Indexes an HTML document by extracting `<h1>`–`<h6>` headings via `scraper` (`BF-IMX-8`).
pub fn from_html(data: &[u8]) -> Result<(usize, Vec<IndexSection>), NotIndexable> {
    if data.len() > MAX_MD_BYTES {
        return Err(NotIndexable(
            "HTML document exceeds 10 MiB limit".to_string(),
        ));
    }
    let text = std::str::from_utf8(data)
        .map_err(|_| NotIndexable("neither a PDF nor UTF-8 HTML".to_string()))?;
    let (normalized, count) = normalize_lines_and_count(text);
    let masked = mask_html_comments_and_scripts(&normalized);

    static H_OPEN_RE: OnceLock<Regex> = OnceLock::new();
    let h_open_re = H_OPEN_RE
        .get_or_init(|| Regex::new(r"(?i)<h([1-6])(?:[\s/>]|$)").expect("valid heading regex"));

    // Precompute 1-based line numbers for each `<h[1-6]` opening tag in the masked source.
    let mut line_starts = vec![0usize];
    for (idx, b) in masked.bytes().enumerate() {
        if b == b'\n' {
            line_starts.push(idx + 1);
        }
    }
    let byte_to_line = |offset: usize| -> usize {
        match line_starts.binary_search(&offset) {
            Ok(i) => i + 1,
            Err(i) => i,
        }
    };
    let tag_positions: Vec<(usize, usize)> = h_open_re
        .captures_iter(&masked)
        .map(|cap| {
            let m = cap.get(0).expect("full match");
            let lvl = (cap[1].as_bytes()[0] - b'0') as usize;
            (lvl, byte_to_line(m.start()))
        })
        .collect();

    let doc = Html::parse_document(&normalized);
    let selector = Selector::parse("h1, h2, h3, h4, h5, h6").expect("valid selector");
    let mut heads: Vec<(String, usize, usize)> = Vec::new();
    let mut tag_cursor = 0usize;

    for el in doc.select(&selector) {
        let tag_name = el.value().name();
        let Some(level) = tag_name
            .strip_prefix('h')
            .or_else(|| tag_name.strip_prefix('H'))
            .and_then(|s| s.parse::<usize>().ok())
            .filter(|&l| (1..=MAX_DEPTH).contains(&l))
        else {
            continue;
        };

        // Match this element to the next corresponding `<h{level}` tag position in source order.
        let mut line_no = heads.last().map_or(1, |h| h.2);
        while tag_cursor < tag_positions.len() {
            let (cand_lvl, cand_line) = tag_positions[tag_cursor];
            tag_cursor += 1;
            if cand_lvl == level {
                line_no = cand_line.min(count);
                break;
            }
        }

        let clean = html_heading_text(el);
        if !clean.is_empty() {
            heads.push((clean, level, line_no));
        }
    }

    if heads.is_empty() {
        return Err(NotIndexable(
            "the HTML file has no headings to index".to_string(),
        ));
    }

    let sections = build_line_sections(&heads, count);
    Ok((count, sections))
}

/// Extracts plain text from a `comrak` heading AST node (`index.py:plain`).
fn markdown_heading_plain_text<'a>(heading_node: &'a AstNode<'a>) -> String {
    let mut parts = String::new();
    for node in heading_node.descendants().skip(1) {
        match &node.data.borrow().value {
            NodeValue::Text(t) => parts.push_str(t),
            NodeValue::Code(c) => parts.push_str(&c.literal),
            NodeValue::SoftBreak | NodeValue::LineBreak => parts.push(' '),
            _ => {}
        }
    }
    parts
}

/// Extracts Trac/MoinMoin wiki headings (`= H1 =`, `== H2 ==`, or `= H1`, `== H2`; `BF-GW-22`).
fn extract_trac_wiki_headings(
    normalized_text: &str,
    max_line: usize,
) -> Vec<(String, usize, usize)> {
    static WIKI_HEADING_RE: OnceLock<Regex> = OnceLock::new();
    let re = WIKI_HEADING_RE.get_or_init(|| {
        Regex::new(r"^(={1,6})\s+(.+?)\s*=*\s*(?:#[A-Za-z0-9_.-]+)?$").expect("valid wiki regex")
    });

    let mut heads = Vec::new();
    let mut in_code_block = false;

    for (idx, raw_line) in normalized_text.split('\n').enumerate() {
        let line_no = (idx + 1).min(max_line);
        let trimmed = raw_line.trim();
        if trimmed.starts_with("{{{") {
            if !trimmed.ends_with("}}}") || trimmed == "{{{" {
                in_code_block = true;
            }
            continue;
        }
        if in_code_block {
            if trimmed.contains("}}}") {
                in_code_block = false;
            }
            continue;
        }
        if trimmed.starts_with("||") {
            continue;
        }
        if let Some(caps) = re.captures(trimmed) {
            let level = caps[1].len();
            if (1..=MAX_DEPTH).contains(&level) {
                let raw_title = caps[2].trim_end_matches('=').trim();
                let clean = title(raw_title);
                if !clean.is_empty() {
                    heads.push((clean, level, line_no));
                }
            }
        }
    }

    heads
}

fn build_line_sections(heads: &[(String, usize, usize)], count: usize) -> Vec<IndexSection> {
    let mut sections = Vec::with_capacity(heads.len());
    for (i, (name, level, first)) in heads.iter().enumerate() {
        let mut last = count;
        for (_, later_level, later_first) in &heads[i + 1..] {
            if *later_level <= *level {
                last = later_first.saturating_sub(1);
                break;
            }
        }
        sections.push(section(name, *level, [*first, (*first).max(last)], "lines"));
    }
    promote_single_letter_appendices(&mut sections);
    sections
}

/// Indexes a Markdown or Trac/MoinMoin wiki document from raw bytes (`index.py:from_markdown` +
/// `BF-GW-22`).
pub fn from_markdown(data: &[u8]) -> Result<(usize, Vec<IndexSection>), NotIndexable> {
    if data.len() > MAX_MD_BYTES {
        return Err(NotIndexable(
            "Markdown file exceeds 10 MiB limit".to_string(),
        ));
    }
    let text = std::str::from_utf8(data)
        .map_err(|_| NotIndexable("neither a PDF nor UTF-8 Markdown".to_string()))?;
    let (normalized, count) = normalize_lines_and_count(text);

    let arena = Arena::new();
    let options = Options::default();
    let root = comrak::parse_document(&arena, &normalized, &options);

    let mut heads: Vec<(String, usize, usize)> = Vec::new();
    for node in root.descendants() {
        let ast = node.data.borrow();
        if let NodeValue::Heading(ref h) = ast.value {
            if !h.setext && (1..=MAX_DEPTH as u8).contains(&h.level) {
                let h_level = h.level as usize;
                let start_line = ast.sourcepos.start.line.max(1).min(count);
                drop(ast);
                let clean = title(&markdown_heading_plain_text(node));
                if !clean.is_empty() {
                    heads.push((clean, h_level, start_line));
                }
            }
        }
    }

    if heads.is_empty() {
        heads = extract_trac_wiki_headings(&normalized, count);
    }

    if heads.is_empty() {
        return Err(NotIndexable(
            "the Markdown file has no headings to index".to_string(),
        ));
    }

    let sections = build_line_sections(&heads, count);
    Ok((count, sections))
}

/// Builds a [`DocumentIndex`] by detecting whether `data` is PDF, HTML, or Markdown/Trac wiki.
pub fn build(name: &str, data: &[u8]) -> Result<DocumentIndex, NotIndexable> {
    let digest = hex::encode(Sha256::digest(data));
    if is_pdf_bytes(data) {
        let (pages, sections) = from_pdf(data)?;
        Ok(DocumentIndex {
            format: 2,
            document: name.to_string(),
            sha256: digest,
            source: "pdf".to_string(),
            pages: Some(pages),
            lines: None,
            sections,
        })
    } else if is_html_bytes(data) {
        let (lines, sections) = from_html(data)?;
        Ok(DocumentIndex {
            format: 2,
            document: name.to_string(),
            sha256: digest,
            source: "markdown".to_string(),
            pages: None,
            lines: Some(lines),
            sections,
        })
    } else {
        let (lines, sections) = from_markdown(data)?;
        Ok(DocumentIndex {
            format: 2,
            document: name.to_string(),
            sha256: digest,
            source: "markdown".to_string(),
            pages: None,
            lines: Some(lines),
            sections,
        })
    }
}

/// Returns `true` if a YAML scalar string can be emitted unquoted in flow style without changing
/// its YAML 1.2 / 1.1 type or failing strict YAML parsing.
fn is_safe_unquoted_yaml_scalar(s: &str) -> bool {
    if s.is_empty() || s.len() > 200 {
        return false;
    }
    if s.starts_with(' ') || s.ends_with(' ') {
        return false;
    }
    let lower = s.to_ascii_lowercase();
    if matches!(
        lower.as_str(),
        "true"
            | "false"
            | "null"
            | "yes"
            | "no"
            | "on"
            | "off"
            | "y"
            | "n"
            | "~"
            | ".nan"
            | ".inf"
            | "-.inf"
    ) {
        return false;
    }
    let first = s.as_bytes()[0];
    if first.is_ascii_digit()
        || matches!(
            first,
            b'-' | b'+'
                | b'.'
                | b'#'
                | b'&'
                | b'*'
                | b'!'
                | b'|'
                | b'>'
                | b'\''
                | b'"'
                | b'%'
                | b'@'
                | b'`'
                | b'?'
                | b':'
                | b'['
                | b']'
                | b'{'
                | b'}'
                | b','
        )
    {
        return false;
    }
    if s.contains(": ")
        || s.contains(" #")
        || s.ends_with(':')
        || s.chars().any(|c| {
            matches!(
                c,
                ',' | '['
                    | ']'
                    | '{'
                    | '}'
                    | '#'
                    | '&'
                    | '*'
                    | '!'
                    | '|'
                    | '>'
                    | '\''
                    | '"'
                    | '%'
                    | '@'
                    | '`'
            )
        })
    {
        return false;
    }
    // Also reject strings that match sexagesimal (`12:34`) or numeric patterns.
    if s.bytes().all(|b| b.is_ascii_digit() || b == b':') {
        return false;
    }
    true
}

/// Formats a YAML string scalar deterministically on a single line (`index.py:dump`).
#[must_use]
pub fn format_yaml_scalar_str(s: &str, force_quote: bool) -> String {
    if !force_quote && is_safe_unquoted_yaml_scalar(s) {
        return s.to_string();
    }
    if !s.contains('\'') {
        format!("'{s}'")
    } else if !s.contains('"') && !s.contains('\\') {
        format!("\"{s}\"")
    } else {
        format!("'{}'", s.replace('\'', "''"))
    }
}

/// Formats one [`IndexSection`] as a single-line flow mapping (`{level: 1, ...}`).
#[must_use]
pub fn format_section_flow(s: &IndexSection) -> String {
    let mut parts = Vec::with_capacity(4);
    parts.push(format!("level: {}", s.level));
    if let Some(lines) = s.lines {
        parts.push(format!("lines: [{}, {}]", lines[0], lines[1]));
    }
    if let Some(ref num) = s.number {
        parts.push(format!("number: {}", format_yaml_scalar_str(num, true)));
    }
    if let Some(pages) = s.pages {
        parts.push(format!("pages: [{}, {}]", pages[0], pages[1]));
    }
    parts.push(format!(
        "title: {}",
        format_yaml_scalar_str(&s.title, false)
    ));
    format!("{{{}}}", parts.join(", "))
}

/// Formats a [`DocumentIndex`] into deterministic YAML with the root marker's SPDX header lines
/// (`index.py:dump`).
#[must_use]
pub fn dump(index: &DocumentIndex, header: &[String]) -> String {
    let mut lines: Vec<String> = header.to_vec();
    lines
        .push("# Generated by hwspecs index: headings and locators only. Do not edit.".to_string());
    lines.push(format!("format: {}", index.format));
    lines.push(format!(
        "document: {}",
        format_yaml_scalar_str(&index.document, false)
    ));
    lines.push(format!(
        "sha256: {}",
        format_yaml_scalar_str(&index.sha256, false)
    ));
    lines.push(format!(
        "source: {}",
        format_yaml_scalar_str(&index.source, false)
    ));
    if let Some(p) = index.pages {
        lines.push(format!("pages: {p}"));
    }
    if let Some(l) = index.lines {
        lines.push(format!("lines: {l}"));
    }
    if index.sections.is_empty() {
        lines.push("sections: []".to_string());
    } else {
        lines.push("sections:".to_string());
        for s in &index.sections {
            lines.push(format!("  - {}", format_section_flow(s)));
        }
    }
    let mut out = lines.join("\n");
    out.push('\n');
    out
}

/// Returns `true` if `target` (or any component between `base` and `target`, or `base` itself)
/// is a symbolic link.
#[must_use]
pub fn is_or_through_symlink(base: &Path, target: &Path) -> bool {
    if fs::symlink_metadata(base)
        .map(|m| m.file_type().is_symlink())
        .unwrap_or(false)
    {
        return true;
    }
    if fs::symlink_metadata(target)
        .map(|m| m.file_type().is_symlink())
        .unwrap_or(false)
    {
        return true;
    }
    if let Ok(rel) = target.strip_prefix(base) {
        let mut cur = base.to_path_buf();
        for comp in rel.components() {
            cur.push(comp);
            if fs::symlink_metadata(&cur)
                .map(|m| m.file_type().is_symlink())
                .unwrap_or(false)
            {
                return true;
            }
        }
    }
    false
}

/// Writes `content` atomically to `dest`, staging the temporary file in `scratch` first (`ENV-3`,
/// never leaving a dotfile in `dest.parent()`) and falling back to a same-directory RAII tempfile
/// only on cross-filesystem (`EXDEV`) renames.
pub fn write_index_atomic(
    dest: &Path,
    content: &str,
    scratch: &ScratchResolver,
) -> Result<(), String> {
    if let Ok(staging_dir) = scratch.ensure_dir() {
        if let Ok(mut writer) = AtomicFileWriter::new_in(staging_dir, dest) {
            if writer.write_all(content.as_bytes()).is_ok() && writer.commit().is_ok() {
                return Ok(());
            }
        }
    }
    let mut writer = AtomicFileWriter::new(dest).map_err(|e| e.to_string())?;
    writer
        .write_all(content.as_bytes())
        .map_err(|e| e.to_string())?;
    writer.commit().map(|_| ()).map_err(|e| e.to_string())
}

/// Summary of a declared `resources.documents` entry in a spec root.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeclaredDocument {
    /// Document `name` identifier.
    pub name: String,
    /// Optional `sha256` recorded in `resources.documents`.
    pub sha256: Option<String>,
    /// Optional `pages` count recorded in `resources.documents`.
    pub pages: Option<usize>,
    /// Optional `page_numbering` (`"pdf"` or `"printed"`).
    pub page_numbering: Option<String>,
}

/// Outcome of running `hwspecs index <document> --root <root> --docs-dir <docs_dir>`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IndexCommandOutcome {
    /// Exit code (`0` pass, `1` domain failure, `2` usage error, `3` sandbox error).
    pub exit_code: ExitCode,
    /// `true` when the index file was written.
    pub ok: bool,
    /// Output `.index.yaml` path (if written).
    pub path: Option<PathBuf>,
    /// Number of indexed sections (if written).
    pub sections: Option<usize>,
    /// Diagnostic findings (if any).
    pub findings: Vec<Finding>,
    /// Human-readable output lines.
    pub text: Vec<String>,
}

impl IndexCommandOutcome {
    /// Serializes this outcome to the JSON object format expected by `hwspecs index --json`.
    #[must_use]
    pub fn to_json_value(&self) -> Value {
        let mut map = Map::new();
        map.insert("ok".to_string(), json!(self.ok));
        map.insert(
            "path".to_string(),
            self.path
                .as_ref()
                .map(|p| json!(visible_name(&p.display().to_string())))
                .unwrap_or(Value::Null),
        );
        if let Some(secs) = self.sections {
            map.insert("sections".to_string(), json!(secs));
        }
        if !self.findings.is_empty() {
            map.insert("findings".to_string(), json!(self.findings));
        }
        map.insert(
            "_text".to_string(),
            json!(self
                .text
                .iter()
                .map(|s| visible_name(s))
                .collect::<Vec<_>>()),
        );
        Value::Object(map)
    }
}

/// Scans `.spec.yaml` files in `root_dir` to collect `resources.documents` entries and the root's
/// `# SPDX-` marker header lines.
pub fn scan_root_documents(
    root_dir: &Path,
) -> Result<(String, Vec<String>, Vec<DeclaredDocument>), Finding> {
    let marker_path = root_dir.join("board-specs.yaml");
    let marker_text = fs::read_to_string(&marker_path).map_err(|e| {
        Finding::error(
            "USAGE",
            marker_path.display().to_string(),
            1,
            1,
            format!("cannot read root marker {}: {e}", marker_path.display()),
        )
    })?;
    let header: Vec<String> = marker_text
        .lines()
        .filter(|l| l.starts_with("# SPDX-"))
        .map(ToString::to_string)
        .collect();
    let marker_loaded = yaml_strict::load_file(&marker_path);
    if let Some(err) = marker_loaded.errors.first() {
        return Err(err.to_finding());
    }
    let root_label = marker_loaded
        .data
        .as_ref()
        .and_then(|v| v.get("name"))
        .and_then(Value::as_str)
        .unwrap_or("root")
        .to_string();

    let mut docs = Vec::new();
    let mut stack = vec![root_dir.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        let mut sorted: Vec<PathBuf> = entries.filter_map(|e| e.ok().map(|e| e.path())).collect();
        sorted.sort();
        for path in sorted {
            let Ok(meta) = fs::symlink_metadata(&path) else {
                continue;
            };
            if meta.file_type().is_symlink() {
                continue;
            }
            if meta.is_dir() {
                if path.file_name().and_then(|n| n.to_str()) != Some(DIR) {
                    stack.push(path);
                }
                continue;
            }
            let Some(fname) = path.file_name().and_then(|n| n.to_str()) else {
                continue;
            };
            if !fname.ends_with(".spec.yaml") {
                continue;
            }
            let loaded = yaml_strict::load_file(&path);
            let Some(data) = loaded.data else {
                continue;
            };
            if let Some(doc_arr) = data
                .get("resources")
                .and_then(|r| r.get("documents"))
                .and_then(Value::as_array)
            {
                for d in doc_arr {
                    let Some(name) = d.get("name").and_then(Value::as_str) else {
                        continue;
                    };
                    let sha256 = d
                        .get("sha256")
                        .and_then(Value::as_str)
                        .map(ToString::to_string);
                    let pages = d.get("pages").and_then(Value::as_u64).map(|n| n as usize);
                    let page_numbering = d
                        .get("page_numbering")
                        .and_then(Value::as_str)
                        .map(ToString::to_string);
                    docs.push(DeclaredDocument {
                        name: name.to_string(),
                        sha256,
                        pages,
                        page_numbering,
                    });
                }
            }
        }
    }

    Ok((root_label, header, docs))
}

/// Executes the `index` command against `root_dir` and `docs_dir` (`index.py:command`).
pub fn run_index_command(
    document: &str,
    root_dir: &Path,
    docs_dir: &Path,
    scratch: &ScratchResolver,
) -> IndexCommandOutcome {
    run_index_command_with_out(document, root_dir, docs_dir, None, scratch)
}

/// Executes the `index` command with an optional explicit `--out <path>` override.
pub fn run_index_command_with_out(
    document: &str,
    root_dir: &Path,
    docs_dir: &Path,
    out_override: Option<&Path>,
    scratch: &ScratchResolver,
) -> IndexCommandOutcome {
    let usage = |msg: String| IndexCommandOutcome {
        exit_code: ExitCode::UsageError,
        ok: false,
        path: None,
        sections: None,
        findings: vec![Finding::error("USAGE", "", 0, 0, msg.clone())],
        text: vec![format!("usage error: {msg}")],
    };

    let (root_label, header, all_docs) = match scan_root_documents(root_dir) {
        Ok(res) => res,
        Err(finding) => {
            return IndexCommandOutcome {
                exit_code: ExitCode::DomainFailure,
                ok: false,
                path: None,
                sections: None,
                findings: vec![finding.clone()],
                text: vec![finding.to_string()],
            };
        }
    };

    let entries: Vec<&DeclaredDocument> = all_docs.iter().filter(|d| d.name == document).collect();
    if entries.is_empty() {
        return usage(format!(
            "no spec in root {root_label} lists a document named '{document}'"
        ));
    }

    let hashes: BTreeSet<&str> = entries.iter().filter_map(|e| e.sha256.as_deref()).collect();
    if hashes.is_empty() {
        return usage(format!(
            "document '{document}' has no sha256 in resources.documents: an index is pinned to known bytes, so record the hash first"
        ));
    }
    if hashes.len() > 1 {
        return usage(format!(
            "the root's specs give document '{document}' {} different sha256 values",
            hashes.len()
        ));
    }

    let doc_path = docs_dir.join(document);
    let is_regular = fs::symlink_metadata(&doc_path)
        .map(|m| m.file_type().is_file() && !m.file_type().is_symlink())
        .unwrap_or(false);
    if !is_regular || is_or_through_symlink(docs_dir, &doc_path) {
        return usage(format!("--docs-dir has no regular file named '{document}'"));
    }

    let data = match fs::read(&doc_path) {
        Ok(b) => b,
        Err(e) => {
            return usage(format!("cannot read {}: {e}", doc_path.display()));
        }
    };

    let want = *hashes.iter().next().expect("non-empty hashes");
    let have = hex::encode(Sha256::digest(&data));
    if have != want {
        let msg = format!(
            "{}: sha256 {have} is not the registry's {want}; not indexed",
            doc_path.display()
        );
        return IndexCommandOutcome {
            exit_code: ExitCode::DomainFailure,
            ok: false,
            path: None,
            sections: None,
            findings: vec![Finding::error(
                "DOC-HASH-MISMATCH",
                doc_path.display().to_string(),
                1,
                1,
                format!("sha256 {have} is not the registry's {want}; not indexed"),
            )],
            text: vec![msg],
        };
    }

    let built = match build(document, &data) {
        Ok(idx) => idx,
        Err(exc) => {
            let msg = format!("{}: {exc}", doc_path.display());
            return IndexCommandOutcome {
                exit_code: ExitCode::DomainFailure,
                ok: false,
                path: None,
                sections: None,
                findings: vec![Finding::error(
                    "IDX-NOT-INDEXABLE",
                    doc_path.display().to_string(),
                    1,
                    1,
                    exc.to_string(),
                )],
                text: vec![msg],
            };
        }
    };

    let out = match out_override {
        Some(p) => p.to_path_buf(),
        None => root_dir.join(DIR).join(format!("{document}{SUFFIX}")),
    };
    let folder = out
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| root_dir.join(DIR));
    let check_base = if out_override.is_some() {
        folder.as_path()
    } else {
        root_dir
    };
    let folder_bad = is_or_through_symlink(check_base, &folder)
        || (folder.exists()
            && !fs::symlink_metadata(&folder)
                .map(|m| m.is_dir() && !m.file_type().is_symlink())
                .unwrap_or(false));
    let out_bad = fs::symlink_metadata(&out)
        .map(|m| m.file_type().is_symlink() || !m.is_file())
        .unwrap_or(false);
    if folder_bad || out_bad {
        return usage(format!(
            "{}: is, or is reached through, a symbolic link, or is not a regular file in a directory; not written",
            out.display()
        ));
    }

    if let Err(e) = fs::create_dir_all(&folder) {
        return usage(format!("cannot create {}: {e}", folder.display()));
    }

    let yaml_text = dump(&built, &header);
    if let Err(e) = write_index_atomic(&out, &yaml_text, scratch) {
        return usage(format!("{}: {e}", out.display()));
    }

    let shown = built.sections.len();
    let line = format!(
        "{}: {shown} section(s) from {}",
        out.display(),
        built.source
    );
    IndexCommandOutcome {
        exit_code: ExitCode::Pass,
        ok: true,
        path: Some(out),
        sections: Some(shown),
        findings: Vec::new(),
        text: vec![line],
    }
}

/// Validates a loaded `.index.yaml` [`Loaded`] document against `index.schema.json` structural
/// rules and returns any schema findings.
#[must_use]
pub fn validate_index_loaded(path: &Path, loaded: &Loaded) -> Vec<Finding> {
    let mut findings: Vec<Finding> = loaded
        .errors
        .iter()
        .map(yaml_strict::LoadError::to_finding)
        .collect();
    if !findings.is_empty() {
        return findings;
    }
    let Some(ref data) = loaded.data else {
        return findings;
    };
    let path_str = path.display().to_string();
    let mark_at = |segs: &[PathSegment]| -> (usize, usize) {
        let m = loaded.mark(segs, None);
        (m.line, m.column)
    };

    let Some(obj) = data.as_object() else {
        findings.push(Finding::error(
            "SCHEMA-PATTERN-OR-TYPE",
            &path_str,
            1,
            1,
            "index root must be a YAML mapping",
        ));
        return findings;
    };

    for req in ["format", "document", "sha256", "source", "sections"] {
        if !obj.contains_key(req) {
            findings.push(Finding::error(
                "SCHEMA-REQUIRED-PROPERTY",
                &path_str,
                1,
                1,
                format!("'{req}' is a required property"),
            ));
        }
    }

    for k in obj.keys() {
        if !matches!(
            k.as_str(),
            "format" | "document" | "sha256" | "source" | "pages" | "lines" | "sections"
        ) {
            let km = loaded.mark(&[PathSegment::from(k.as_str())], Some(k.as_str()));
            let (l, c) = (km.line, km.column);
            findings.push(Finding::error(
                "SCHEMA-UNKNOWN-KEY",
                &path_str,
                l,
                c,
                format!("unknown key '{k}' here"),
            ));
        }
    }

    if let Some(fmt_val) = obj.get("format") {
        if fmt_val.as_i64() != Some(2) {
            let (l, c) = mark_at(&[PathSegment::from("format")]);
            findings.push(Finding::error(
                "SCHEMA-ENUM-OR-CONST",
                &path_str,
                l,
                c,
                "format must be 2",
            ));
        }
    }

    static DOC_ID_RE: OnceLock<Regex> = OnceLock::new();
    let doc_id_re =
        DOC_ID_RE.get_or_init(|| Regex::new(r"^[a-z0-9][a-z0-9._-]*$").expect("valid regex"));
    if let Some(doc_val) = obj.get("document") {
        let (l, c) = mark_at(&[PathSegment::from("document")]);
        match doc_val.as_str() {
            Some(s) if !s.is_empty() && s.len() <= 128 && doc_id_re.is_match(s) => {}
            _ => findings.push(Finding::error(
                "SCHEMA-PATTERN-OR-TYPE",
                &path_str,
                l,
                c,
                "document does not match '^[a-z0-9][a-z0-9._-]*$'",
            )),
        }
    }

    static SHA_RE: OnceLock<Regex> = OnceLock::new();
    let sha_re = SHA_RE.get_or_init(|| Regex::new(r"^[0-9a-f]{64}$").expect("valid regex"));
    if let Some(sha_val) = obj.get("sha256") {
        let (l, c) = mark_at(&[PathSegment::from("sha256")]);
        match sha_val.as_str() {
            Some(s) if sha_re.is_match(s) => {}
            _ => findings.push(Finding::error(
                "SCHEMA-PATTERN-OR-TYPE",
                &path_str,
                l,
                c,
                "sha256 does not match '^[0-9a-f]{64}$'",
            )),
        }
    }

    let source_str = obj.get("source").and_then(Value::as_str);
    match source_str {
        Some("pdf") => {
            if !obj.contains_key("pages") {
                findings.push(Finding::error(
                    "SCHEMA-REQUIRED-PROPERTY",
                    &path_str,
                    1,
                    1,
                    "'pages' is a required property for source: pdf",
                ));
            }
            if obj.contains_key("lines") {
                let (l, c) = mark_at(&[PathSegment::from("lines")]);
                findings.push(Finding::error(
                    "SCHEMA-PATTERN-OR-TYPE",
                    &path_str,
                    l,
                    c,
                    "lines is not allowed when source is pdf",
                ));
            }
        }
        Some("markdown") => {
            if !obj.contains_key("lines") {
                findings.push(Finding::error(
                    "SCHEMA-REQUIRED-PROPERTY",
                    &path_str,
                    1,
                    1,
                    "'lines' is a required property for source: markdown",
                ));
            }
            if obj.contains_key("pages") {
                let (l, c) = mark_at(&[PathSegment::from("pages")]);
                findings.push(Finding::error(
                    "SCHEMA-PATTERN-OR-TYPE",
                    &path_str,
                    l,
                    c,
                    "pages is not allowed when source is markdown",
                ));
            }
        }
        Some(other) => {
            let (l, c) = mark_at(&[PathSegment::from("source")]);
            findings.push(Finding::error(
                "SCHEMA-ENUM-OR-CONST",
                &path_str,
                l,
                c,
                format!("'{other}' is not one of ['pdf', 'markdown']"),
            ));
        }
        None => {}
    }

    for bound_key in ["pages", "lines"] {
        if let Some(v) = obj.get(bound_key) {
            let (l, c) = mark_at(&[PathSegment::from(bound_key)]);
            if v.as_i64().is_none_or(|n| n < 1) {
                findings.push(Finding::error(
                    "SCHEMA-PATTERN-OR-TYPE",
                    &path_str,
                    l,
                    c,
                    format!("{bound_key} must be an integer >= 1"),
                ));
            }
        }
    }

    let doc_pages = obj.get("pages").and_then(Value::as_i64);
    let doc_lines = obj.get("lines").and_then(Value::as_i64);

    if let Some(sec_val) = obj.get("sections") {
        let (sl, sc) = mark_at(&[PathSegment::from("sections")]);
        match sec_val.as_array() {
            Some(arr) if !arr.is_empty() && arr.len() <= 20_000 => {
                for (idx, item) in arr.iter().enumerate() {
                    let segs = vec![PathSegment::from("sections"), PathSegment::from(idx)];
                    let (il, ic) = mark_at(&segs);
                    let Some(sec_obj) = item.as_object() else {
                        findings.push(Finding::error(
                            "SCHEMA-PATTERN-OR-TYPE",
                            &path_str,
                            il,
                            ic,
                            "section entry must be a mapping",
                        ));
                        continue;
                    };
                    for req in ["title", "level"] {
                        if !sec_obj.contains_key(req) {
                            findings.push(Finding::error(
                                "SCHEMA-REQUIRED-PROPERTY",
                                &path_str,
                                il,
                                ic,
                                format!("'{req}' is a required property"),
                            ));
                        }
                    }
                    if let Some(lvl) = sec_obj.get("level") {
                        if !lvl.as_i64().is_some_and(|n| (1..=6).contains(&n)) {
                            findings.push(Finding::error(
                                "SCHEMA-PATTERN-OR-TYPE",
                                &path_str,
                                il,
                                ic,
                                "level must be an integer in 1..6",
                            ));
                        }
                    }
                    if let Some(t) = sec_obj.get("title") {
                        if !t
                            .as_str()
                            .is_some_and(|s| !s.is_empty() && s.len() <= 4096 && !s.contains('\n'))
                        {
                            findings.push(Finding::error(
                                "SCHEMA-PATTERN-OR-TYPE",
                                &path_str,
                                il,
                                ic,
                                "title must be a non-empty single-line string",
                            ));
                        }
                    }
                    if let Some(n) = sec_obj.get("number") {
                        if !n
                            .as_str()
                            .is_some_and(|s| !s.is_empty() && s.len() <= 64 && !s.contains('\n'))
                        {
                            findings.push(Finding::error(
                                "SCHEMA-PATTERN-OR-TYPE",
                                &path_str,
                                il,
                                ic,
                                "number must be a non-empty string",
                            ));
                        }
                    }
                    if source_str == Some("pdf") {
                        if !sec_obj.contains_key("pages") || sec_obj.contains_key("lines") {
                            findings.push(Finding::error(
                                "SCHEMA-REQUIRED-PROPERTY",
                                &path_str,
                                il,
                                ic,
                                "PDF section requires 'pages' and forbids 'lines'",
                            ));
                        }
                    } else if source_str == Some("markdown")
                        && (!sec_obj.contains_key("lines") || sec_obj.contains_key("pages"))
                    {
                        findings.push(Finding::error(
                            "SCHEMA-REQUIRED-PROPERTY",
                            &path_str,
                            il,
                            ic,
                            "Markdown section requires 'lines' and forbids 'pages'",
                        ));
                    }
                    for (span_key, max_bound) in [("pages", doc_pages), ("lines", doc_lines)] {
                        if let Some(span_val) = sec_obj.get(span_key) {
                            let valid_pair = span_val.as_array().and_then(|a| {
                                if a.len() == 2 {
                                    Some((a[0].as_i64()?, a[1].as_i64()?))
                                } else {
                                    None
                                }
                            });
                            match valid_pair {
                                Some((first, last)) if first >= 1 && last >= 1 => {
                                    if first > last {
                                        findings.push(Finding::error(
                                            "IDX-MISMATCH",
                                            &path_str,
                                            il,
                                            ic,
                                            format!("{span_key} [{first}, {last}] runs backwards"),
                                        ));
                                    }
                                    if let Some(bound) = max_bound {
                                        if last > bound {
                                            findings.push(Finding::error(
                                                "IDX-MISMATCH",
                                                &path_str,
                                                il,
                                                ic,
                                                format!(
                                                    "{span_key} {last} exceeds document {span_key} {bound}"
                                                ),
                                            ));
                                        }
                                    }
                                }
                                _ => findings.push(Finding::error(
                                    "SCHEMA-PATTERN-OR-TYPE",
                                    &path_str,
                                    il,
                                    ic,
                                    format!(
                                        "{span_key} must be a 2-element array of positive integers"
                                    ),
                                )),
                            }
                        }
                    }
                }
            }
            _ => findings.push(Finding::error(
                "SCHEMA-PATTERN-OR-TYPE",
                &path_str,
                sl,
                sc,
                "sections must be a non-empty array",
            )),
        }
    }

    findings
}

/// Checks `<root>/index/` and all `*.index.yaml` files inside `root_dir` (`index.py:check` +
/// `speccheck.py` index walk rules).
pub fn check_root_indexes(
    root_dir: &Path,
    root_label: &str,
    declared_docs: &[DeclaredDocument],
) -> (Vec<(PathBuf, Loaded)>, Vec<Finding>) {
    let mut valid_indexes: Vec<(PathBuf, Loaded)> = Vec::new();
    let mut findings: Vec<Finding> = Vec::new();

    // Check for misplaced `*.index.yaml` files outside `<root>/index/`.
    let mut stack = vec![root_dir.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        let mut sorted: Vec<PathBuf> = entries.filter_map(|e| e.ok().map(|e| e.path())).collect();
        sorted.sort();
        for path in sorted {
            let Ok(meta) = fs::symlink_metadata(&path) else {
                continue;
            };
            if meta.file_type().is_symlink() {
                continue;
            }
            if meta.is_dir() {
                if path != root_dir.join(DIR) {
                    stack.push(path);
                }
                continue;
            }
            if path
                .file_name()
                .and_then(|n| n.to_str())
                .is_some_and(|n| n.ends_with(SUFFIX))
                && path.parent() != Some(&root_dir.join(DIR))
            {
                findings.push(Finding::error(
                    "CHK-NOT-READ-AS-SPEC",
                    path.display().to_string(),
                    1,
                    1,
                    "a document index lives in the root's own index/ directory, not here",
                ));
            }
        }
    }

    let idx_dir = root_dir.join(DIR);
    let Ok(idx_meta) = fs::symlink_metadata(&idx_dir) else {
        return (valid_indexes, findings);
    };
    if idx_meta.file_type().is_symlink() || !idx_meta.is_dir() {
        findings.push(Finding::error(
            "IDX-MISMATCH",
            idx_dir.display().to_string(),
            1,
            1,
            "index/ is not a plain directory",
        ));
        return (valid_indexes, findings);
    }

    let Ok(entries) = fs::read_dir(&idx_dir) else {
        return (valid_indexes, findings);
    };
    let mut paths: Vec<PathBuf> = entries.filter_map(|e| e.ok().map(|e| e.path())).collect();
    paths.sort();

    for path in paths {
        let Ok(meta) = fs::symlink_metadata(&path) else {
            continue;
        };
        let fname = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or_default();
        if meta.file_type().is_symlink() {
            findings.push(Finding::error(
                "IDX-MISMATCH",
                path.display().to_string(),
                1,
                1,
                "symbolic link under index/ is not read",
            ));
            continue;
        }
        if !meta.is_file() || !fname.ends_with(SUFFIX) {
            findings.push(Finding::error(
                "CHK-NOT-READ-AS-SPEC",
                path.display().to_string(),
                1,
                1,
                format!(
                    "{fname} is not read as a document index: indexes under index/ end in {SUFFIX}"
                ),
            ));
            continue;
        }

        let loaded = yaml_strict::load_file(&path);
        let schema_findings = validate_index_loaded(&path, &loaded);
        if !schema_findings.is_empty() {
            findings.extend(schema_findings);
            continue;
        }
        valid_indexes.push((path, loaded));
    }

    // Semantic checks on valid loaded indexes (`index.py:283-321`).
    let mut seen: BTreeMap<String, PathBuf> = BTreeMap::new();
    for (path, loaded) in &valid_indexes {
        let Some(ref data) = loaded.data else {
            continue;
        };
        let Some(name) = data.get("document").and_then(Value::as_str) else {
            continue;
        };
        let dm = loaded.mark(&[PathSegment::from("document")], None);
        let (doc_line, doc_col) = (dm.line, dm.column);
        if let Some(first_path) = seen.get(name) {
            let first_name = first_path
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or_default();
            findings.push(Finding::warning(
                "IDX-MISMATCH",
                path.display().to_string(),
                doc_line,
                doc_col,
                format!(
                    "a second index for document '{name}' (the first is {first_name}): keep one, named {name}{SUFFIX}"
                ),
            ));
        } else {
            seen.insert(name.to_string(), path.clone());
        }
    }

    for (path, loaded) in &valid_indexes {
        let Some(ref data) = loaded.data else {
            continue;
        };
        let Some(name) = data.get("document").and_then(Value::as_str) else {
            continue;
        };
        let mark_for = |key: &str| -> (usize, usize) {
            let m = loaded.mark(&[PathSegment::from(key)], None);
            (m.line, m.column)
        };

        let fname = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or_default();
        let expected_fname = format!("{name}{SUFFIX}");
        if fname != expected_fname {
            let (l, c) = mark_for("document");
            findings.push(Finding::warning(
                "IDX-MISMATCH",
                path.display().to_string(),
                l,
                c,
                format!("index for '{name}' is named {fname}: name it {expected_fname}"),
            ));
        }

        let entries: Vec<&DeclaredDocument> =
            declared_docs.iter().filter(|d| d.name == name).collect();
        if entries.is_empty() {
            let (l, c) = mark_for("document");
            findings.push(Finding::warning(
                "IDX-MISMATCH",
                path.display().to_string(),
                l,
                c,
                format!("no spec of root {root_label} lists document '{name}'"),
            ));
            continue;
        }

        let hashes: BTreeSet<&str> = entries.iter().filter_map(|e| e.sha256.as_deref()).collect();
        if hashes.is_empty() {
            let (l, c) = mark_for("sha256");
            findings.push(Finding::warning(
                "IDX-MISMATCH",
                path.display().to_string(),
                l,
                c,
                format!(
                    "the registry records no sha256 for document '{name}', so nothing pins the bytes this index describes"
                ),
            ));
        } else if let Some(idx_sha) = data.get("sha256").and_then(Value::as_str) {
            if !hashes.contains(idx_sha) {
                let (l, c) = mark_for("sha256");
                findings.push(Finding::warning(
                    "IDX-MISMATCH",
                    path.display().to_string(),
                    l,
                    c,
                    format!(
                        "index sha256 is not the registry's for document '{name}': the index describes other bytes; regenerate it with spec.py index"
                    ),
                ));
            }
        }

        let counts: BTreeSet<usize> = entries.iter().filter_map(|e| e.pages).collect();
        if let Some(idx_pages) = data
            .get("pages")
            .and_then(Value::as_u64)
            .map(|n| n as usize)
        {
            if !counts.is_empty() && !counts.contains(&idx_pages) {
                let (l, c) = mark_for("pages");
                let counts_str = counts
                    .iter()
                    .map(ToString::to_string)
                    .collect::<Vec<_>>()
                    .join(", ");
                findings.push(Finding::warning(
                    "IDX-MISMATCH",
                    path.display().to_string(),
                    l,
                    c,
                    format!("index counts {idx_pages} pages; the registry gives {counts_str}"),
                ));
            }
        }
    }

    (valid_indexes, findings)
}

/// Citation input for [`links`] / [`compute_index_links`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FactDocumentCitation {
    /// Full canonical fact reference (e.g., `"widgetsoc@good#uart-base"`).
    pub fact_full_id: String,
    ///Cited document name (`resources.documents[].name`).
    pub document: String,
    /// `true` when the declaring spec sets `page_numbering: "pdf"` on this document.
    pub pdf_numbered: bool,
    /// Optional `section` locator string.
    pub section: Option<String>,
    /// Optional `heading` locator string.
    pub heading: Option<String>,
    /// Optional `page` locator string.
    pub page: Option<String>,
    /// Optional `pages` `[first, last]` locator strings.
    pub pages: Option<[String; 2]>,
}

/// Linked section row returned by [`compute_index_links`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LinkedIndexSection {
    /// Section number, if any.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub number: Option<String>,
    /// Cleaned title.
    pub title: String,
    /// 1-based depth level.
    pub level: usize,
    /// 1-based page range `[first, last]`, if PDF.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pages: Option<[usize; 2]>,
    /// 1-based line range `[first, last]`, if Markdown/HTML/wiki.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub lines: Option<[usize; 2]>,
    /// Sorted list of full fact IDs (`<spec>@<root>#<fact>`) linked to this section.
    pub facts: Vec<String>,
}

/// Linked document index returned by [`compute_index_links`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LinkedDocumentIndex {
    /// Document name.
    pub document: String,
    /// Source kind (`"pdf"` or `"markdown"`).
    pub source: String,
    /// Document SHA-256.
    pub sha256: String,
    /// Sections with linked fact IDs.
    pub sections: Vec<LinkedIndexSection>,
}

/// Normalizes a cited `section:` locator string (`BF-IMX-9`), returning `(normalized_title,
/// extracted_number)`.
#[must_use]
pub fn normalize_cited_section(raw_sec: &str) -> (String, Option<String>) {
    let cleaned = title(raw_sec);
    if cleaned.is_empty() {
        return (cleaned, None);
    }
    // Check `Part <N>`
    static PART_CITE_RE: OnceLock<Regex> = OnceLock::new();
    let part_re = PART_CITE_RE
        .get_or_init(|| Regex::new(r"(?i)^Part\s+([0-9A-Z]+)(?:[.:]|\b)").expect("valid regex"));
    if let Some(caps) = part_re.captures(&cleaned) {
        return (cleaned.clone(), Some(format!("Part {}", &caps[1])));
    }

    // Check `Chapter <N>`, `Section <N>`, `Appendix <X>`
    static PREFIXED_CITE_RE: OnceLock<Regex> = OnceLock::new();
    let pref_re = PREFIXED_CITE_RE.get_or_init(|| {
        Regex::new(r"(?i)^(?:Chapter|Section|Appendix)\s+([0-9A-Z]+(?:\.[0-9]+)*)(?:[.:]|\b)")
            .expect("valid regex")
    });
    if let Some(caps) = pref_re.captures(&cleaned) {
        return (cleaned.clone(), Some(caps[1].to_string()));
    }

    // Check bare section number or prefix (`4.2`, `4.2 System interrupts`, `A1.2`, `A`, `6.10`)
    static BARE_CITE_RE: OnceLock<Regex> = OnceLock::new();
    let bare_re = BARE_CITE_RE.get_or_init(|| {
        Regex::new(
            r"^((?:[0-9]+|[A-Z][0-9]*)(?:\.[0-9]+)+|[A-Z][0-9]+|[0-9]+|[A-Z])(?:[.:]?(?:\s+\S.*|$))",
        )
        .expect("valid regex")
    });
    if let Some(caps) = bare_re.captures(&cleaned) {
        let token = &caps[1];
        let is_bare_int = token.bytes().all(|b| b.is_ascii_digit());
        if is_bare_int {
            let m = caps.get(1).expect("group 1");
            let rest = cleaned[m.end()..]
                .trim_start_matches(['.', ':'])
                .trim_start();
            if !rest.is_empty() && unit_prefix_re().is_match(rest) {
                return (cleaned, None);
            }
        }
        return (cleaned.clone(), Some(token.to_string()));
    }

    (cleaned, None)
}

fn parse_ascii_page_num(s: &str) -> Option<usize> {
    if !s.is_empty() && s.len() < 9 && s.bytes().all(|b| b.is_ascii_digit()) {
        s.parse::<usize>().ok()
    } else {
        None
    }
}

/// Computes ancestor section indices (in `0..idx`) for section `idx` in `sections`.
fn section_ancestors(sections: &[IndexSection], idx: usize) -> Vec<usize> {
    let mut ancestors = Vec::new();
    let mut target_level = sections[idx].level;
    if target_level <= 1 {
        return ancestors;
    }
    for i in (0..idx).rev() {
        if sections[i].level < target_level {
            ancestors.push(i);
            target_level = sections[i].level;
            if target_level <= 1 {
                break;
            }
        }
    }
    ancestors
}

/// Links citations in a root to each document's canonical index sections (`index.py:links` +
/// `BF-IMX-9`).
///
/// `candidate_indexes` is a list of `(index_file_filename, DocumentIndex)` pairs from
/// `<root>/index/`.
#[must_use]
pub fn compute_index_links(
    candidate_indexes: &[(String, DocumentIndex)],
    citations: &[FactDocumentCitation],
) -> Vec<LinkedDocumentIndex> {
    // Choose the canonical index per document (`<name>.index.yaml` wins over misnamed copies;
    // otherwise first by filename).
    let mut sorted_candidates: Vec<&(String, DocumentIndex)> = candidate_indexes.iter().collect();
    sorted_candidates.sort_by(|a, b| a.1.document.cmp(&b.1.document).then_with(|| a.0.cmp(&b.0)));

    let mut chosen: BTreeMap<String, &(String, DocumentIndex)> = BTreeMap::new();
    for item in sorted_candidates {
        let name = &item.1.document;
        let expected = format!("{name}{SUFFIX}");
        match chosen.get(name) {
            None => {
                chosen.insert(name.clone(), item);
            }
            Some(prev) if item.0 == expected && prev.0 != expected => {
                chosen.insert(name.clone(), item);
            }
            _ => {}
        }
    }

    let mut out = Vec::with_capacity(chosen.len());
    for (doc_name, (_, idx_data)) in chosen {
        let doc_cites: Vec<&FactDocumentCitation> = citations
            .iter()
            .filter(|c| c.document == doc_name)
            .collect();
        let sections = &idx_data.sections;
        let mut hits: Vec<BTreeSet<String>> = vec![BTreeSet::new(); sections.len()];

        for cite in doc_cites {
            let mut matched_by_sec_or_heading = Vec::new();

            // 1. Try matching by normalized `section:` or `heading:` first (`BF-IMX-9`).
            if let Some(ref raw_sec) = cite.section {
                let (norm_title, cited_num) = normalize_cited_section(raw_sec);
                for (i, s) in sections.iter().enumerate() {
                    let mut is_match = false;
                    if let (Some(ref s_num), Some(ref c_num)) = (&s.number, &cited_num) {
                        if c_num == s_num || c_num.starts_with(&format!("{s_num}.")) {
                            is_match = true;
                        }
                    }
                    if !is_match
                        && !norm_title.is_empty()
                        && s.title.eq_ignore_ascii_case(&norm_title)
                    {
                        is_match = true;
                    }
                    if is_match {
                        matched_by_sec_or_heading.push(i);
                    }
                }
            }

            if let Some(ref raw_heading) = cite.heading {
                let norm_h = title(raw_heading);
                for (i, s) in sections.iter().enumerate() {
                    if s.title == norm_h && !matched_by_sec_or_heading.contains(&i) {
                        matched_by_sec_or_heading.push(i);
                    }
                }
            }

            if !matched_by_sec_or_heading.is_empty() {
                for idx in matched_by_sec_or_heading {
                    hits[idx].insert(cite.fact_full_id.clone());
                    for anc in section_ancestors(sections, idx) {
                        hits[anc].insert(cite.fact_full_id.clone());
                    }
                }
                continue;
            }

            // 2. Fall back to PDF page matching when `page_numbering == "pdf"` (`BF-IMX-9`).
            if !cite.pdf_numbered {
                continue;
            }
            let page_nums: Vec<usize> = if let Some(ref p) = cite.page {
                parse_ascii_page_num(p).into_iter().collect()
            } else if let Some(ref ps) = cite.pages {
                ps.iter().filter_map(|p| parse_ascii_page_num(p)).collect()
            } else {
                Vec::new()
            };

            for p in page_nums {
                let containing: Vec<usize> = sections
                    .iter()
                    .enumerate()
                    .filter_map(|(i, s)| {
                        let [start, end] = s.pages?;
                        if start <= p && p <= end {
                            Some(i)
                        } else {
                            None
                        }
                    })
                    .collect();
                if containing.is_empty() {
                    continue;
                }

                // Check if `p` is a shared boundary page where one or more sections start (`start == p`)
                // while an earlier non-ancestor section ends (`end == p && start < p`).
                let starting_on_p: Vec<usize> = containing
                    .iter()
                    .copied()
                    .filter(|&i| sections[i].pages.is_some_and(|[start, _]| start == p))
                    .collect();

                if !starting_on_p.is_empty() {
                    // Pick the deepest section(s) starting on page `p`, plus their ancestors that
                    // contain `p` (`BF-IMX-9`).
                    let max_lvl = starting_on_p
                        .iter()
                        .map(|&i| sections[i].level)
                        .max()
                        .unwrap_or(1);
                    for &idx in &starting_on_p {
                        if sections[idx].level == max_lvl {
                            hits[idx].insert(cite.fact_full_id.clone());
                            for anc in section_ancestors(sections, idx) {
                                if sections[anc].pages.is_some_and(|[s, e]| s <= p && p <= e) {
                                    hits[anc].insert(cite.fact_full_id.clone());
                                }
                            }
                        }
                    }
                } else {
                    for idx in containing {
                        hits[idx].insert(cite.fact_full_id.clone());
                    }
                }
            }
        }

        let rows = sections
            .iter()
            .enumerate()
            .map(|(i, s)| LinkedIndexSection {
                number: s.number.clone(),
                title: s.title.clone(),
                level: s.level,
                pages: s.pages,
                lines: s.lines,
                facts: hits[i].iter().cloned().collect(),
            })
            .collect();

        out.push(LinkedDocumentIndex {
            document: doc_name,
            source: idx_data.source.clone(),
            sha256: idx_data.sha256.clone(),
            sections: rows,
        });
    }

    out
}

/// Scans `root_dir` specs and `root_dir/index/*.index.yaml` files and computes [`links`] directly
/// (`index.py:links`).
pub fn links_for_root_dir(root_dir: &Path) -> Vec<LinkedDocumentIndex> {
    let Ok((root_label, _, _)) = scan_root_documents(root_dir) else {
        return Vec::new();
    };
    let idx_dir = root_dir.join(DIR);
    let Ok(idx_entries) = fs::read_dir(&idx_dir) else {
        return Vec::new();
    };
    let mut candidate_indexes = Vec::new();
    let mut idx_paths: Vec<PathBuf> = idx_entries
        .filter_map(|e| e.ok().map(|e| e.path()))
        .collect();
    idx_paths.sort();
    for path in idx_paths {
        let Ok(meta) = fs::symlink_metadata(&path) else {
            continue;
        };
        if meta.file_type().is_symlink() || !meta.is_file() {
            continue;
        }
        let Some(fname) = path.file_name().and_then(|n| n.to_str()) else {
            continue;
        };
        if !fname.ends_with(SUFFIX) {
            continue;
        }
        let loaded = yaml_strict::load_file(&path);
        if !validate_index_loaded(&path, &loaded).is_empty() {
            continue;
        }
        if let Some(idx_doc) = loaded.data.as_ref().and_then(DocumentIndex::from_value) {
            candidate_indexes.push((fname.to_string(), idx_doc));
        }
    }

    let mut citations = Vec::new();
    let mut stack = vec![root_dir.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        let mut sorted: Vec<PathBuf> = entries.filter_map(|e| e.ok().map(|e| e.path())).collect();
        sorted.sort();
        for path in sorted {
            let Ok(meta) = fs::symlink_metadata(&path) else {
                continue;
            };
            if meta.file_type().is_symlink() {
                continue;
            }
            if meta.is_dir() {
                if path != idx_dir {
                    stack.push(path);
                }
                continue;
            }
            if !path
                .file_name()
                .and_then(|n| n.to_str())
                .is_some_and(|n| n.ends_with(".spec.yaml"))
            {
                continue;
            }
            let loaded = yaml_strict::load_file(&path);
            let Some(data) = loaded.data else {
                continue;
            };
            let spec_id_opt = if data.get("kind").and_then(Value::as_str) == Some("overlay") {
                data.get("overlays").and_then(Value::as_str)
            } else {
                data.get("id").and_then(Value::as_str)
            };
            let Some(spec_id) = spec_id_opt else {
                continue;
            };
            let mut doc_pdf_map: BTreeMap<String, bool> = BTreeMap::new();
            if let Some(docs) = data
                .get("resources")
                .and_then(|r| r.get("documents"))
                .and_then(Value::as_array)
            {
                for d in docs {
                    if let Some(dname) = d.get("name").and_then(Value::as_str) {
                        let is_pdf = d.get("page_numbering").and_then(Value::as_str) == Some("pdf");
                        doc_pdf_map.insert(dname.to_string(), is_pdf);
                    }
                }
            }
            collect_spec_citations(&data, spec_id, &root_label, &doc_pdf_map, &mut citations);
        }
    }

    compute_index_links(&candidate_indexes, &citations)
}

fn collect_support_entries_recursive<'a>(val: &'a Value, out: &mut Vec<&'a Value>) {
    match val {
        Value::Object(map) => {
            for (k, v) in map {
                if (k == "support" || k == "settled_by") && v.is_array() {
                    if let Some(arr) = v.as_array() {
                        out.extend(arr.iter());
                    }
                }
                collect_support_entries_recursive(v, out);
            }
        }
        Value::Array(arr) => {
            for item in arr {
                collect_support_entries_recursive(item, out);
            }
        }
        _ => {}
    }
}

fn collect_record_support_citations(
    rec: &Value,
    full_id: &str,
    doc_pdf_map: &BTreeMap<String, bool>,
    out: &mut Vec<FactDocumentCitation>,
) {
    let mut entries = Vec::new();
    collect_support_entries_recursive(rec, &mut entries);
    for entry in entries {
        let Some(doc_name) = entry.get("doc").and_then(Value::as_str) else {
            continue;
        };
        let Some(&pdf_numbered) = doc_pdf_map.get(doc_name) else {
            continue;
        };
        let Some(at_arr) = entry.get("at").and_then(Value::as_array) else {
            continue;
        };
        for loc in at_arr {
            let section = loc
                .get("section")
                .and_then(Value::as_str)
                .map(ToString::to_string);
            let heading = loc
                .get("heading")
                .and_then(Value::as_str)
                .map(ToString::to_string);
            let page = loc
                .get("page")
                .and_then(Value::as_str)
                .map(ToString::to_string);
            let pages = loc.get("pages").and_then(Value::as_array).and_then(|a| {
                if a.len() == 2 {
                    Some([a[0].as_str()?.to_string(), a[1].as_str()?.to_string()])
                } else {
                    None
                }
            });
            out.push(FactDocumentCitation {
                fact_full_id: full_id.to_string(),
                document: doc_name.to_string(),
                pdf_numbered,
                section,
                heading,
                page,
                pages,
            });
        }
    }
}

fn collect_spec_citations(
    spec_data: &Value,
    spec_id: &str,
    root_label: &str,
    doc_pdf_map: &BTreeMap<String, bool>,
    out: &mut Vec<FactDocumentCitation>,
) {
    for list_key in ["facts", "instances", "variants"] {
        if let Some(arr) = spec_data.get(list_key).and_then(Value::as_array) {
            for rec in arr {
                if let Some(id) = rec.get("id").and_then(Value::as_str) {
                    let full = format!("{spec_id}@{root_label}#{id}");
                    collect_record_support_citations(rec, &full, doc_pdf_map, out);
                }
            }
        }
    }
    if let Some(secs) = spec_data.get("sections").and_then(Value::as_object) {
        for sec_val in secs.values() {
            if let Some(facts) = sec_val.get("facts").and_then(Value::as_array) {
                for rec in facts {
                    if let Some(id) = rec.get("id").and_then(Value::as_str) {
                        let full = format!("{spec_id}@{root_label}#{id}");
                        collect_record_support_citations(rec, &full, doc_pdf_map, out);
                    }
                }
            }
        }
    }
}
