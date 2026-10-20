// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Restricted CommonMark checker and template-placeholder detector
//! (port of `skills/spec-format/scripts/specmd.py` and `textcheck.py`,
//! plus `BF-IMX-12`, `BF-ARM-19`, and `BF-GW-24`).

use crate::diagnostic::Level;
use crate::yaml_strict::{self, PathSegment};
use comrak::nodes::{AstNode, NodeValue};
use comrak::{parse_document, Arena, Options};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, HashSet};
use std::ops::Range;
use std::path::Path;
use std::sync::LazyLock;

/// Maximum block/inline nesting depth in Spec Markdown fields.
pub const MAX_DEPTH: usize = 16;

/// Hard parser nesting ceiling (matches `specmd.py`'s `maxNesting: 64`).
pub const PARSER_MAX_NESTING: usize = 64;

/// Maximum consecutive backticks permitted in any decoded string or mapping key.
pub const MAX_BACKTICKS: usize = 32;

/// Object replacement character used to break inline text across code spans and autolinks
/// without altering line numbers.
pub const BREAK: &str = "\u{fffc}";

static PLACEHOLDER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"<[A-Za-z][A-Za-z0-9 _-]*>").expect("valid PLACEHOLDER_RE"));

static TYPED_PLACEHOLDER_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)^<(?:board|soc|chip|ip|peripheral|doc|repo|domain|stub)[- ][A-Za-z0-9 _-]*>$")
        .expect("valid TYPED_PLACEHOLDER_RE")
});

static ALLOWED_LINK_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)^(?:https?|mailto):").expect("valid ALLOWED_LINK_RE"));

static V1_TAG_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?i)\[(?:databook|standard|rtl|DT|src|source-observed|doc|hardware|press|inference|emulated)(?:\]|:)",
    )
    .expect("valid V1_TAG_RE")
});

static FOOTNOTE_INLINE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[\^[^\]\n]+\]").expect("valid FOOTNOTE_INLINE_RE"));

static FOOTNOTE_REFDEF_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[\^[^\]\n]+\]:").expect("valid FOOTNOTE_REFDEF_RE"));

static REF_DEF_LINE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?: {0,3}>[ ]?| {0,3}(?:[-+*]|[0-9]{1,9}[.)])[ ]+)* {0,3}\[[^\]\n]+\]:")
        .expect("valid REF_DEF_LINE_RE")
});

static EXCESS_BACKTICKS_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"`{33,}").expect("valid EXCESS_BACKTICKS_RE"));

/// Embedded YAML templates from `skills/board-spec-scaffold/templates/`.
const YAML_TEMPLATES: &[(&str, &str)] = &[
    (
        "board-specs.yaml",
        include_str!("../skills/board-spec-scaffold/templates/board-specs.yaml"),
    ),
    (
        "board.spec.yaml",
        include_str!("../skills/board-spec-scaffold/templates/board.spec.yaml"),
    ),
    (
        "chip.spec.yaml",
        include_str!("../skills/board-spec-scaffold/templates/chip.spec.yaml"),
    ),
    (
        "corpus.yaml",
        include_str!("../skills/board-spec-scaffold/templates/corpus.yaml"),
    ),
    (
        "domains.yaml",
        include_str!("../skills/board-spec-scaffold/templates/domains.yaml"),
    ),
    (
        "ip.spec.yaml",
        include_str!("../skills/board-spec-scaffold/templates/ip.spec.yaml"),
    ),
    (
        "overlay.spec.yaml",
        include_str!("../skills/board-spec-scaffold/templates/overlay.spec.yaml"),
    ),
    (
        "soc.spec.yaml",
        include_str!("../skills/board-spec-scaffold/templates/soc.spec.yaml"),
    ),
    (
        "docs-root/board-specs.yaml",
        include_str!("../skills/board-spec-scaffold/templates/docs-root/board-specs.yaml"),
    ),
    (
        "docs-root/overlay.spec.yaml",
        include_str!("../skills/board-spec-scaffold/templates/docs-root/overlay.spec.yaml"),
    ),
];

/// Embedded Markdown templates from `skills/board-spec-scaffold/templates/` and
/// `skills/peripheral-spec/templates/`.
const MD_TEMPLATES: &[(&str, &str)] = &[
    (
        "domain-stub-SKILL.md",
        include_str!("../skills/board-spec-scaffold/templates/domain-stub-SKILL.md"),
    ),
    (
        "stub-SKILL.md",
        include_str!("../skills/board-spec-scaffold/templates/stub-SKILL.md"),
    ),
    (
        "vendor-board-tools-SKILL.md",
        include_str!("../skills/board-spec-scaffold/templates/vendor-board-tools-SKILL.md"),
    ),
    (
        "spec-subagent-prompt.md",
        include_str!("../skills/peripheral-spec/templates/spec-subagent-prompt.md"),
    ),
    (
        "verifier-prompt.md",
        include_str!("../skills/peripheral-spec/templates/verifier-prompt.md"),
    ),
];

fn collect_yaml_scalar_placeholders(val: &Value, out: &mut HashSet<String>) {
    match val {
        Value::String(s) => {
            for m in PLACEHOLDER_RE.find_iter(s) {
                out.insert(m.as_str().to_string());
            }
        }
        Value::Array(items) => {
            for item in items {
                collect_yaml_scalar_placeholders(item, out);
            }
        }
        Value::Object(map) => {
            for (k, v) in map {
                for m in PLACEHOLDER_RE.find_iter(k) {
                    out.insert(m.as_str().to_string());
                }
                collect_yaml_scalar_placeholders(v, out);
            }
        }
        _ => {}
    }
}

/// Vocabulary of known scaffold/prompt template placeholders (`BF-IMX-12`).
///
/// Built from scalar string values of `.yaml` templates parsed through `yaml_strict`
/// (ignoring `#` comment lines such as `<id>`, `<fact>`, `<note>`, `<reason>` in `corpus.yaml`)
/// plus `.md` templates (excluding generic comment/prose metavariables `<id>`, `<fact>`,
/// `<note>`, `<reason>`).
pub static TEMPLATE_PLACEHOLDERS: LazyLock<HashSet<String>> = LazyLock::new(|| {
    let mut set = HashSet::new();
    for (name, content) in YAML_TEMPLATES {
        let loaded = yaml_strict::load_text(content, Path::new(name));
        if let Some(data) = &loaded.data {
            collect_yaml_scalar_placeholders(data, &mut set);
        }
    }
    for (_name, content) in MD_TEMPLATES {
        for line in content.lines() {
            if line.trim_start().starts_with('#') && !line.contains("SPDX-") {
                continue;
            }
            for m in PLACEHOLDER_RE.find_iter(line) {
                set.insert(m.as_str().to_string());
            }
        }
    }
    // BF-IMX-12: generic metavariables from corpus.yaml comments / inline code examples
    // must not be blacklisted in prose.
    for excluded in ["<id>", "<fact>", "<note>", "<reason>"] {
        set.remove(excluded);
    }
    set
});

/// Returns `true` if `token` (matching `<[A-Za-z][A-Za-z0-9 _-]*>`) is a known scaffold/prompt
/// template placeholder or starts with a typed template prefix (`<board-...>`, `<soc-...>`, etc.).
#[must_use]
pub fn is_template_placeholder(token: &str) -> bool {
    TEMPLATE_PLACEHOLDERS.contains(token) || TYPED_PLACEHOLDER_RE.is_match(token)
}

/// One safety or containment finding at a 1-based line within a decoded Markdown field.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TextFinding {
    /// 1-based line number within the decoded field.
    pub line: usize,
    /// Finding category (`"footnote"`, `"nesting"`, `"html"`, `"link"`, `"reference"`,
    /// `"heading"`, `"fence"`, `"v1-tag"`).
    pub kind: String,
    /// Diagnostic message.
    pub message: String,
    /// Severity level (`Level::Error` or `Level::Warning`).
    pub level: Level,
}

impl TextFinding {
    /// Constructs a new [`TextFinding`].
    #[must_use]
    pub fn new(
        line: usize,
        kind: impl Into<String>,
        message: impl Into<String>,
        level: Level,
    ) -> Self {
        Self {
            line,
            kind: kind.into(),
            message: message.into(),
            level,
        }
    }

    /// Stable diagnostic code (`MD-RETIRED-PROVENANCE` for `v1-tag` warnings, `MD-CONTAINMENT`
    /// for safety/containment errors).
    #[must_use]
    pub fn diagnostic_code(&self) -> &'static str {
        if self.kind == "v1-tag" {
            "MD-RETIRED-PROVENANCE"
        } else {
            "MD-CONTAINMENT"
        }
    }
}

/// D21: only `http:`, `https:`, `mailto:`, and in-page `#` anchors are allowed link destinations.
#[must_use]
pub fn allowed_link(url: &str) -> bool {
    url.starts_with('#') || ALLOWED_LINK_RE.is_match(url)
}

fn collect_covered_lines<'a>(
    node: &'a AstNode<'a>,
    covered: &mut Vec<Range<usize>>,
    in_code_ranges: &mut Vec<Range<usize>>,
) {
    let ast = node.data.borrow();
    let sourcepos = ast.sourcepos;
    if sourcepos.start.line > 0 && sourcepos.end.line >= sourcepos.start.line {
        match &ast.value {
            NodeValue::Paragraph
            | NodeValue::Heading(_)
            | NodeValue::CodeBlock(_)
            | NodeValue::HtmlBlock(_)
            | NodeValue::ThematicBreak => {
                covered.push(sourcepos.start.line..sourcepos.end.line + 1);
            }
            NodeValue::Code(_) => {
                in_code_ranges.push(sourcepos.start.line..sourcepos.end.line + 1);
            }
            _ => {}
        }
    }
    for child in node.children() {
        collect_covered_lines(child, covered, in_code_ranges);
    }
}

fn check_nesting<'a>(node: &'a AstNode<'a>, depth: usize, out: &mut Vec<TextFinding>) {
    if depth > MAX_DEPTH {
        let line = node.data.borrow().sourcepos.start.line;
        out.push(TextFinding::new(
            line,
            "nesting",
            format!("nesting deeper than {MAX_DEPTH}"),
            Level::Error,
        ));
        return; // Only report once per nested tree
    }
    for child in node.children() {
        let child_depth = if matches!(child.data.borrow().value, NodeValue::Document) {
            depth
        } else {
            depth + 1
        };
        check_nesting(child, child_depth, out);
    }
}

fn walk_findings<'a>(
    node: &'a AstNode<'a>,
    text: &str,
    out: &mut Vec<TextFinding>,
    in_inline: &mut usize,
    inline_decoded: &mut String,
    inline_visible: &mut String,
    lint: bool,
    inline_first_line: &mut usize,
    open_html_tags: &mut Vec<String>,
) {
    let ast = node.data.borrow();
    let line = ast.sourcepos.start.line;
    let mut flush = false;

    match &ast.value {
        NodeValue::CodeBlock(cb) => {
            if !cb.fenced {
                // Indented block, do nothing specific for findings other than it covers lines
            } else {
                // Fenced block: check if closed properly
                let literal_newlines = cb.literal.chars().filter(|&c| c == '\n').count();
                let end_line_text = text
                    .lines()
                    .nth(ast.sourcepos.end.line.saturating_sub(1))
                    .unwrap_or("");
                let fence_str =
                    std::iter::repeat_n(cb.fence_char as char, cb.fence_length).collect::<String>();
                if ast.sourcepos.end.line <= ast.sourcepos.start.line + literal_newlines
                    || !end_line_text.contains(&fence_str)
                {
                    out.push(TextFinding::new(
                        line,
                        "fence",
                        "unclosed code fence",
                        Level::Error,
                    ));
                }
            }
        }
        NodeValue::HtmlBlock(_) => {
            out.push(TextFinding::new(line, "html", "raw HTML", Level::Error));
        }
        NodeValue::Heading(_) => {
            out.push(TextFinding::new(
                line,
                "heading",
                "heading inside a field",
                Level::Error,
            ));
            if *in_inline == 0 {
                *inline_first_line = line;
                inline_decoded.clear();
                inline_visible.clear();
                open_html_tags.clear();
            }
            *in_inline += 1;
        }
        NodeValue::Paragraph => {
            if *in_inline == 0 {
                *inline_first_line = line;
                inline_decoded.clear();
                inline_visible.clear();
                open_html_tags.clear();
            }
            *in_inline += 1;
        }
        NodeValue::Link(link) => {
            let url = if link.url.starts_with("mailto:") {
                link.url.clone()
            } else if link.url.contains('@') && !link.url.contains("://") {
                format!("mailto:{}", link.url)
            } else {
                link.url.clone()
            };
            if !allowed_link(&url) {
                out.push(TextFinding::new(
                    line,
                    "link",
                    format!("disallowed link destination '{}'", url),
                    Level::Error,
                ));
            }
            if text
                .lines()
                .nth(line.saturating_sub(1))
                .unwrap_or("")
                .contains(&link.url)
            {
                // Approximate autolink check
                inline_decoded.push_str(BREAK);
                inline_visible.push_str(BREAK);
            }
        }
        NodeValue::Image(img) => {
            if !allowed_link(&img.url) {
                out.push(TextFinding::new(
                    line,
                    "link",
                    format!("disallowed link destination '{}'", img.url),
                    Level::Error,
                ));
            }
            inline_decoded.push_str(BREAK);
            inline_visible.push_str(BREAK);
        }
        NodeValue::HtmlInline(html) => {
            let raw = html;
            // approximate check for is_register_subscript
            inline_decoded.push_str(raw);
            inline_visible.push_str(raw);
            out.push(TextFinding::new(line, "html", "raw HTML", Level::Error));
        }
        NodeValue::Text(s) => {
            if *in_inline > 0 {
                inline_decoded.push_str(s);
                inline_visible.push_str(s);
            }
        }
        NodeValue::Code(_) => {
            if *in_inline > 0 {
                inline_decoded.push_str(BREAK);
                inline_visible.push_str(BREAK);
            }
        }
        NodeValue::SoftBreak | NodeValue::LineBreak if *in_inline > 0 => {
            inline_decoded.push('\n');
            inline_visible.push('\n');
        }
        _ => {}
    }

    for child in node.children() {
        if let NodeValue::Image(_) = child.data.borrow().value {
            walk_findings(
                child,
                text,
                out,
                in_inline,
                inline_decoded,
                inline_visible,
                lint,
                inline_first_line,
                open_html_tags,
            );
        } else if let NodeValue::Link(_) = child.data.borrow().value {
            walk_findings(
                child,
                text,
                out,
                in_inline,
                inline_decoded,
                inline_visible,
                lint,
                inline_first_line,
                open_html_tags,
            );
        } else {
            walk_findings(
                child,
                text,
                out,
                in_inline,
                inline_decoded,
                inline_visible,
                lint,
                inline_first_line,
                open_html_tags,
            );
        }
    }

    match &ast.value {
        NodeValue::Heading(_) | NodeValue::Paragraph => {
            *in_inline = in_inline.saturating_sub(1);
            if *in_inline == 0 {
                flush = true;
            }
        }
        _ => {}
    }

    if flush {
        if !inline_decoded.is_empty() {
            for m in FOOTNOTE_INLINE_RE.find_iter(inline_decoded) {
                let mline = *inline_first_line
                    + inline_decoded.as_bytes()[..m.start()]
                        .iter()
                        .filter(|&&b| b == b'\n')
                        .count();
                out.push(TextFinding::new(
                    mline,
                    "footnote",
                    "footnote reference or definition inside a field",
                    Level::Error,
                ));
            }
        }
        if lint && !inline_visible.is_empty() {
            for m in V1_TAG_RE.find_iter(inline_visible) {
                let mline = *inline_first_line
                    + inline_visible.as_bytes()[..m.start()]
                        .iter()
                        .filter(|&&b| b == b'\n')
                        .count();
                out.push(TextFinding::new(
                    mline,
                    "v1-tag",
                    format!("retired provenance tag '{}' in author text", m.as_str()),
                    Level::Warning,
                ));
            }
        }
        inline_decoded.clear();
        inline_visible.clear();
    }
}

pub fn findings(text: &str, lint: bool) -> Vec<TextFinding> {
    let mut out = Vec::new();

    // 1. Raw source line scan for `[^` footnote syntax.
    for (idx, source) in text.split('\n').enumerate() {
        if source.contains("[^") {
            out.push(TextFinding::new(
                idx + 1,
                "footnote",
                "footnote reference or definition inside a field",
                Level::Error,
            ));
        }
    }

    let arena = Arena::new();
    let root = parse_document(&arena, text, &Options::default());

    let mut covered_ranges = Vec::new();
    let mut in_code_ranges = Vec::new();
    collect_covered_lines(root, &mut covered_ranges, &mut in_code_ranges);

    // Check excessive blocks/brackets

    // (This is just an approximation for check_excessive_bracket_nesting, which we might skip if we check_nesting via AST)
    check_nesting(root, 0, &mut out);

    // Reference definitions
    for (idx, raw_line) in text.split('\n').enumerate() {
        let line_no = idx + 1;
        if REF_DEF_LINE_RE.is_match(raw_line) {
            let is_covered = covered_ranges
                .iter()
                .any(|r| r.start <= line_no && line_no < r.end);
            if !is_covered {
                out.push(TextFinding::new(
                    line_no,
                    "reference",
                    "link reference definition inside a field",
                    Level::Error,
                ));
                if FOOTNOTE_REFDEF_RE.is_match(raw_line) {
                    out.push(TextFinding::new(
                        line_no,
                        "footnote",
                        "footnote reference or definition inside a field",
                        Level::Error,
                    ));
                }
            }
        }
    }

    let mut inline_decoded = String::new();
    let mut inline_visible = String::new();
    let mut in_inline = 0usize;
    let mut inline_first_line = 1usize;
    let mut open_html_tags = Vec::new();

    walk_findings(
        root,
        text,
        &mut out,
        &mut in_inline,
        &mut inline_decoded,
        &mut inline_visible,
        lint,
        &mut inline_first_line,
        &mut open_html_tags,
    );

    out
}

fn walk_text_blocks<'a>(node: &'a AstNode<'a>, skip_html: bool, blocks: &mut Vec<(usize, String)>) {
    let ast = node.data.borrow();
    match &ast.value {
        NodeValue::Paragraph | NodeValue::Heading(_) => {
            let mut buf = String::new();
            walk_inline_text(node, &mut buf, skip_html);
            blocks.push((ast.sourcepos.start.line, buf));
            return; // Children handled by walk_inline_text
        }
        NodeValue::HtmlBlock(hb) if !skip_html => {
            blocks.push((ast.sourcepos.start.line, hb.literal.clone()));
        }
        _ => {}
    }
    for child in node.children() {
        walk_text_blocks(child, skip_html, blocks);
    }
}

fn walk_inline_text<'a>(node: &'a AstNode<'a>, buf: &mut String, skip_html: bool) {
    let ast = node.data.borrow();
    match &ast.value {
        NodeValue::Text(s) => buf.push_str(s),
        NodeValue::Code(_) => buf.push_str(BREAK),
        NodeValue::SoftBreak | NodeValue::LineBreak => buf.push('\n'),
        NodeValue::HtmlInline(s) => {
            if skip_html {
                buf.push_str(BREAK);
            } else {
                buf.push_str(s);
            }
        }
        NodeValue::Link(_) => {
            // Check if autolink by checking the first character of the source
            // Note: comrak parses autolinks as Link with a single Text child.
            // If the text starts with '<', it's likely an autolink in source.
            // For simplicity, we can always push a BREAK.
        }
        NodeValue::Image(_) => {
            buf.push_str(BREAK);
        }
        _ => {}
    }
    for child in node.children() {
        if matches!(ast.value, NodeValue::Link(_)) {
            // if we are inside a link, we need to push a BREAK if it's an autolink, but we can just process children for normal links
        }
        walk_inline_text(child, buf, skip_html);
    }
}

pub fn text_blocks(text: &str, skip_html: bool) -> Vec<(usize, String)> {
    let mut blocks = Vec::new();
    let arena = Arena::new();
    let root = parse_document(&arena, text, &Options::default());
    walk_text_blocks(root, skip_html, &mut blocks);
    blocks
}

pub fn outside_code(text: &str) -> String {
    text_blocks(text, false)
        .into_iter()
        .map(|(_, t)| t)
        .collect::<Vec<_>>()
        .join("\n")
}

fn find_placeholder_column(line: &str, needle: &str) -> usize {
    let mut search_from = 0usize;
    while let Some(rel) = line[search_from..].find(needle) {
        let byte_idx = search_from + rel;
        let backticks_before = line.as_bytes()[..byte_idx]
            .iter()
            .filter(|&&b| b == b'`')
            .count();
        if backticks_before % 2 == 0 {
            return line[..byte_idx].chars().count() + 1;
        }
        search_from = byte_idx + 1;
    }
    1
}

pub fn placeholders(text: &str, skip_html: bool) -> Vec<(usize, usize, String)> {
    let source_lines: Vec<&str> = text.split('\n').collect();
    let mut found = Vec::new();
    for (first, block) in text_blocks(text, skip_html) {
        for m in PLACEHOLDER_RE.find_iter(&block) {
            let tok = m.as_str();
            if !is_template_placeholder(tok) {
                continue;
            }
            let line_idx = first.saturating_sub(1)
                + block.as_bytes()[..m.start()]
                    .iter()
                    .filter(|&&b| b == b'\n')
                    .count();
            let col = source_lines
                .get(line_idx)
                .map_or(1, |src| find_placeholder_column(src, tok));
            found.push((line_idx + 1, col, tok.to_string()));
        }
    }
    found
}

pub fn placeholder(text: &str, skip_html: bool) -> Option<String> {
    placeholders(text, skip_html)
        .into_iter()
        .next()
        .map(|(_, _, tok)| tok)
}

pub type ConstructMap = BTreeMap<(usize, String, String), usize>;

fn walk_constructs<'a>(node: &'a AstNode<'a>, result: &mut ConstructMap) {
    let ast = node.data.borrow();
    let zero_line = ast.sourcepos.start.line.saturating_sub(1);
    match &ast.value {
        NodeValue::Heading(_) => {
            *result
                .entry((zero_line, "heading_open".to_string(), String::new()))
                .or_insert(0) += 1;
        }
        NodeValue::CodeBlock(cb) => {
            if cb.fenced {
                *result
                    .entry((zero_line, "fence".to_string(), cb.literal.clone()))
                    .or_insert(0) += 1;
            }
        }
        NodeValue::HtmlBlock(_) => {
            *result
                .entry((zero_line, "html_block".to_string(), String::new()))
                .or_insert(0) += 1;
        }
        NodeValue::Link(link) => {
            let href = if link.url.starts_with("mailto:") {
                link.url.clone()
            } else if link.url.contains('@') && !link.url.contains("://") {
                format!("mailto:{}", link.url)
            } else {
                link.url.clone()
            };
            *result
                .entry((zero_line, "link_open".to_string(), href))
                .or_insert(0) += 1;
        }
        NodeValue::Image(img) => {
            *result
                .entry((zero_line, "image".to_string(), img.url.clone()))
                .or_insert(0) += 1;
        }
        NodeValue::HtmlInline(_) => {
            *result
                .entry((zero_line, "html_inline".to_string(), String::new()))
                .or_insert(0) += 1;
        }
        _ => {}
    }
    for child in node.children() {
        walk_constructs(child, result);
    }
}

pub fn constructs(text: &str) -> ConstructMap {
    let mut result = ConstructMap::new();
    let arena = Arena::new();
    let mut opts = Options::default();
    opts.extension.table = true;
    let root = parse_document(&arena, text, &opts);
    walk_constructs(root, &mut result);

    let mut covered_ranges = Vec::new();
    let mut in_code_ranges = Vec::new();
    collect_covered_lines(root, &mut covered_ranges, &mut in_code_ranges);

    for (idx, raw_line) in text.split('\n').enumerate() {
        if REF_DEF_LINE_RE.is_match(raw_line) {
            let line_no = idx + 1;
            let is_covered = covered_ranges
                .iter()
                .any(|r| r.start <= line_no && line_no < r.end);
            if !is_covered {
                *result
                    .entry((idx, "reference".to_string(), String::new()))
                    .or_insert(0) += 1;
            }
        }
    }
    result
}

pub fn check_view(text: &str, expected: &ConstructMap) -> Result<(), String> {
    let arena = Arena::new();
    let mut opts = Options::default();
    opts.extension.table = true;
    let root = parse_document(&arena, text, &opts);

    fn check_node<'a>(node: &'a AstNode<'a>, text: &str, depth: usize) -> Result<(), String> {
        let ast = node.data.borrow();
        match &ast.value {
            NodeValue::Document => {}
            NodeValue::Heading(_) => {
                if depth > 0 {
                    return Err("assembled Markdown containment failed".to_string());
                }
            }
            NodeValue::Paragraph
            | NodeValue::List(_)
            | NodeValue::Item(_)
            | NodeValue::Table(_)
            | NodeValue::TableRow(_)
            | NodeValue::TableCell
            | NodeValue::Text(_)
            | NodeValue::Code(_)
            | NodeValue::SoftBreak => {}
            NodeValue::CodeBlock(cb) => {
                if !cb.fenced || depth > 0 || !cb.info.is_empty() {
                    return Err("assembled Markdown containment failed".to_string());
                }
                let literal_newlines = cb.literal.chars().filter(|&c| c == '\n').count();
                let end_line_text = text
                    .lines()
                    .nth(ast.sourcepos.end.line.saturating_sub(1))
                    .unwrap_or("");
                let fence_str =
                    std::iter::repeat_n(cb.fence_char as char, cb.fence_length).collect::<String>();
                if ast.sourcepos.end.line <= ast.sourcepos.start.line + literal_newlines
                    || !end_line_text.contains(&fence_str)
                {
                    return Err("assembled Markdown containment failed".to_string());
                }
            }
            _ => {
                return Err("assembled Markdown containment failed".to_string());
            }
        }
        let child_depth = if matches!(ast.value, NodeValue::Document) {
            depth
        } else {
            depth + 1
        };
        for child in node.children() {
            check_node(child, text, child_depth)?;
        }
        Ok(())
    }

    check_node(root, text, 0)?;

    let actual = constructs(text);
    if &actual != expected {
        return Err("assembled Markdown containment failed".to_string());
    }
    Ok(())
}

pub fn has_excess_backticks(s: &str) -> bool {
    EXCESS_BACKTICKS_RE.is_match(s)
}

pub fn all_strings(data: &Value) -> Vec<(Vec<PathSegment>, String, bool)> {
    let mut out = Vec::new();
    walk_strings(data, &mut Vec::new(), &mut out);
    out
}

fn walk_strings(
    data: &Value,
    path: &mut Vec<PathSegment>,
    out: &mut Vec<(Vec<PathSegment>, String, bool)>,
) {
    match data {
        Value::String(s) => {
            out.push((path.clone(), s.clone(), false));
        }
        Value::Object(map) => {
            for (k, v) in map {
                path.push(PathSegment::Key(k.clone()));
                out.push((path.clone(), k.clone(), true));
                walk_strings(v, path, out);
                path.pop();
            }
        }
        Value::Array(items) => {
            for (i, v) in items.iter().enumerate() {
                path.push(PathSegment::Index(i));
                walk_strings(v, path, out);
                path.pop();
            }
        }
        _ => {}
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuthorField {
    pub path: Vec<PathSegment>,
    pub value: String,
    pub lint: bool,
}

pub fn author_fields(data: &Value) -> Vec<AuthorField> {
    let mut out = Vec::new();
    walk_author_fields(data, &mut Vec::new(), &mut out);
    out
}

fn walk_author_fields(data: &Value, path: &mut Vec<PathSegment>, out: &mut Vec<AuthorField>) {
    match data {
        Value::Object(map) => {
            for (key, value) in map {
                if key == "notices" && path.is_empty() {
                    continue;
                }
                path.push(PathSegment::Key(key.clone()));
                if matches!(
                    key.as_str(),
                    "claim"
                        | "title"
                        | "note"
                        | "purpose"
                        | "orientation"
                        | "milestones"
                        | "notes"
                        | "states"
                ) {
                    if let Value::String(s) = value {
                        let lint = matches!(
                            key.as_str(),
                            "claim" | "orientation" | "milestones" | "notes"
                        );
                        out.push(AuthorField {
                            path: path.clone(),
                            value: s.clone(),
                            lint,
                        });
                    }
                } else {
                    walk_author_fields(value, path, out);
                }
                path.pop();
            }
        }
        Value::Array(items) => {
            for (i, value) in items.iter().enumerate() {
                path.push(PathSegment::Index(i));
                walk_author_fields(value, path, out);
                path.pop();
            }
        }
        _ => {}
    }
}
