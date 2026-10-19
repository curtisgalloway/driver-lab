// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Strict YAML 1.2 loader built on `saphyr-parser` (port of `specload.py` + `BF-IMX-11`).
//!
//! Enforces fail-closed rules:
//! - File size, nesting depth, and node count limits:
//!   - Default (`.spec.yaml`, `.facts.yaml`, `.verify.yaml`, `corpus.yaml`, `board-specs.yaml`):
//!     10 MiB, 64 nesting levels, 100,000 YAML nodes.
//!   - Index files (`*.index.yaml`, `BF-IMX-11`):
//!     32 MiB, 64 nesting levels, 500,000 YAML nodes.
//! - Rejects byte-order marks (UTF-8, UTF-16 LE/BE), non-UTF-8 bytes, lone CR, control/format
//!   characters (`Cc`, `Cf`, `Cs`, `Co`, `Cn`, `Zl`, `Zp`, `Zs` except U+0020, and default-ignorable
//!   code points), and refused characters in file names.
//! - Rejects YAML directives (`%YAML`, `%TAG`, etc.), anchors (`&`), aliases (`*`), explicit tags
//!   (`!`, `!!str`), merge keys (`<<`), non-string mapping keys, duplicate mapping keys, empty plain
//!   scalars, and multi-document streams.
//! - Resolves plain scalars using strict YAML 1.2 Core Schema rules (`true`, `false`, `null`,
//!   signed 64-bit decimal integers, and `0x` hex integers without underscores; YAML 1.1 boolean
//!   and sexagesimal traps such as `yes`, `no`, `on`, `off`, `08`, `12:34` remain strings).
//! - Rejects strings containing tabs or refused characters and strings not in Unicode NFC form
//!   (`unicode_normalization::is_nfc`).
//! - Records 1-based `(line, col)` spans on every value and mapping key node.

use crate::diagnostic::{
    bad_file_name, char_label, is_yaml_refused_char, visible_name, Finding, Level,
};
use saphyr_parser::{Event, Parser, ScalarStyle, Span};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Number, Value};
use std::fmt;
use std::fs::File;
use std::io::Read;
use std::path::Path;
use unicode_normalization::is_nfc;

/// Default byte cap for spec, facts, verify, root, and corpus YAML files (10 MiB).
pub const MAX_BYTES: usize = 10 * 1024 * 1024;
/// Default nesting depth cap (64 levels).
pub const MAX_DEPTH: usize = 64;
/// Default YAML node cap for spec, facts, verify, root, and corpus files (100,000 nodes).
pub const MAX_NODES: usize = 100_000;

/// Byte cap for generated `*.index.yaml` files (`BF-IMX-11`: 32 MiB).
pub const INDEX_MAX_BYTES: usize = 32 * 1024 * 1024;
/// Nesting depth cap for `*.index.yaml` files (64 levels).
pub const INDEX_MAX_DEPTH: usize = 64;
/// YAML node cap for generated `*.index.yaml` files (`BF-IMX-11`: 500,000 nodes).
pub const INDEX_MAX_NODES: usize = 500_000;

/// Size, depth, and node limits enforced during strict YAML loading.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct YamlLimits {
    /// Maximum input size in bytes.
    pub max_bytes: usize,
    /// Maximum container nesting depth.
    pub max_depth: usize,
    /// Maximum total YAML nodes (mappings, sequences, keys, and scalar values).
    pub max_nodes: usize,
}

impl Default for YamlLimits {
    fn default() -> Self {
        Self::default_spec()
    }
}

impl YamlLimits {
    /// Standard limits (10 MiB, 64 depth, 100,000 nodes).
    #[must_use]
    pub const fn default_spec() -> Self {
        Self {
            max_bytes: MAX_BYTES,
            max_depth: MAX_DEPTH,
            max_nodes: MAX_NODES,
        }
    }

    /// Limits for `*.index.yaml` files (`BF-IMX-11`: 32 MiB, 64 depth, 500,000 nodes).
    #[must_use]
    pub const fn index() -> Self {
        Self {
            max_bytes: INDEX_MAX_BYTES,
            max_depth: INDEX_MAX_DEPTH,
            max_nodes: INDEX_MAX_NODES,
        }
    }

    /// Selects limits based on `path` (`*.index.yaml` uses [`YamlLimits::index`], all other
    /// files use [`YamlLimits::default_spec`]).
    #[must_use]
    pub fn for_path(path: &Path) -> Self {
        let is_index = path
            .file_name()
            .and_then(|n| n.to_str())
            .is_some_and(|n| n.ends_with(".index.yaml"));
        if is_index {
            Self::index()
        } else {
            Self::default_spec()
        }
    }
}

/// 1-based line and column coordinates in a YAML source file.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Mark {
    /// 1-based line number.
    pub line: usize,
    /// 1-based column number.
    pub column: usize,
}

impl Default for Mark {
    fn default() -> Self {
        Self { line: 1, column: 1 }
    }
}

impl Mark {
    /// Creates a new 1-based [`Mark`].
    #[must_use]
    pub const fn new(line: usize, column: usize) -> Self {
        Self { line, column }
    }

    /// Returns the 1-based column number (alias for `self.column`).
    #[must_use]
    pub const fn col(&self) -> usize {
        self.column
    }
}

/// Segment of a path into a loaded YAML document.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub enum PathSegment {
    /// Mapping key name.
    Key(String),
    /// Sequence element index.
    Index(usize),
}

impl From<&str> for PathSegment {
    fn from(s: &str) -> Self {
        Self::Key(s.to_string())
    }
}

impl From<String> for PathSegment {
    fn from(s: String) -> Self {
        Self::Key(s)
    }
}

impl From<usize> for PathSegment {
    fn from(i: usize) -> Self {
        Self::Index(i)
    }
}

/// One error encountered while loading a YAML file.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LoadError {
    /// File path.
    pub path: String,
    /// 1-based line number.
    pub line: usize,
    /// 1-based column number.
    pub column: usize,
    /// Stable diagnostic code.
    pub code: String,
    /// Diagnostic message.
    pub message: String,
}

impl LoadError {
    /// Constructs a new [`LoadError`].
    #[must_use]
    pub fn new(
        path: impl Into<String>,
        line: usize,
        column: usize,
        code: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self {
            path: path.into(),
            line,
            column,
            code: code.into(),
            message: message.into(),
        }
    }

    /// Returns the 1-based column number (alias for `self.column`).
    #[must_use]
    pub const fn col(&self) -> usize {
        self.column
    }

    /// Converts this [`LoadError`] into a structured [`Finding`].
    #[must_use]
    pub fn to_finding(&self) -> Finding {
        Finding::new(
            Level::Error,
            &self.code,
            &self.path,
            self.line,
            self.column,
            &self.message,
        )
    }
}

impl fmt::Display for LoadError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{}:{}:{}: {}",
            visible_name(&self.path),
            self.line,
            self.column,
            self.message
        )
    }
}

impl std::error::Error for LoadError {}

/// Compact tree of 1-based source positions mirroring a parsed YAML [`Value`].
/// Avoids per-node path-vector cloning and `HashMap` hashing during parsing.
#[derive(Debug, Clone)]
pub enum MarkNode {
    /// Scalar node mark.
    Scalar(Mark),
    /// Sequence node mark and element marks.
    Sequence { mark: Mark, items: Vec<MarkNode> },
    /// Mapping node mark and `(key_name, key_mark, value_mark_node)` entries.
    Mapping {
        mark: Mark,
        entries: Vec<(String, Mark, MarkNode)>,
    },
}

impl MarkNode {
    /// Returns the 1-based [`Mark`] of this node itself.
    #[must_use]
    pub const fn node_mark(&self) -> Mark {
        match self {
            Self::Scalar(m) | Self::Sequence { mark: m, .. } | Self::Mapping { mark: m, .. } => *m,
        }
    }
}

/// Result of loading a YAML file with [`load_file`] or [`load_text`].
#[derive(Debug, Clone)]
pub struct Loaded {
    /// Parsed JSON-compatible value tree (`None` when `errors` is non-empty).
    pub data: Option<Value>,
    /// Errors encountered while loading (at most one fatal load error per file).
    pub errors: Vec<LoadError>,
    /// Root of the 1-based source mark tree.
    pub root_mark: Option<MarkNode>,
}

impl Loaded {
    fn from_error(err: LoadError) -> Self {
        Self {
            data: None,
            errors: vec![err],
            root_mark: None,
        }
    }

    /// Returns `true` if the YAML file loaded with zero errors.
    #[must_use]
    pub fn ok(&self) -> bool {
        self.errors.is_empty()
    }

    /// Converts any load errors into structured [`Finding`]s.
    #[must_use]
    pub fn findings(&self) -> Vec<Finding> {
        self.errors.iter().map(LoadError::to_finding).collect()
    }

    /// Looks up the 1-based [`Mark`] for `path` (or mapping key `key` under `path`),
    /// walking down the mark tree and returning the nearest recorded ancestor if a child
    /// segment does not exist (`specload.py:Loaded.mark`).
    #[must_use]
    pub fn mark(&self, path: &[PathSegment], key: Option<&str>) -> Mark {
        let Some(mut cur) = self.root_mark.as_ref() else {
            return Mark::default();
        };
        let mut nearest = cur.node_mark();

        for (idx, seg) in path.iter().enumerate() {
            let is_last = idx + 1 == path.len();
            match (cur, seg) {
                (MarkNode::Mapping { entries, .. }, PathSegment::Key(k)) => {
                    if let Some((_, km, child)) = entries.iter().find(|(ek, _, _)| ek == k) {
                        if is_last && key == Some(k.as_str()) {
                            return *km;
                        }
                        cur = child;
                        nearest = cur.node_mark();
                    } else {
                        return nearest;
                    }
                }
                (MarkNode::Sequence { items, .. }, PathSegment::Index(i)) => {
                    if let Some(child) = items.get(*i) {
                        cur = child;
                        nearest = cur.node_mark();
                    } else {
                        return nearest;
                    }
                }
                _ => return nearest,
            }
        }

        if let Some(target_key) = key {
            if let MarkNode::Mapping { entries, .. } = cur {
                if let Some((_, km, _)) = entries.iter().find(|(ek, _, _)| ek == target_key) {
                    return *km;
                }
            }
        }

        nearest
    }

    /// Convenience helper to look up a [`Mark`] using string keys at top level or nested mappings.
    #[must_use]
    pub fn mark_keys(&self, keys: &[&str], key: Option<&str>) -> Mark {
        let segs: Vec<PathSegment> = keys
            .iter()
            .map(|&k| PathSegment::Key(k.to_string()))
            .collect();
        self.mark(&segs, key)
    }
}

const BOMS: &[&[u8]] = &[b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff"];

/// Loads a YAML file from disk using path-appropriate limits (`YamlLimits::for_path`).
#[must_use]
pub fn load_file(path: impl AsRef<Path>) -> Loaded {
    let path = path.as_ref();
    load_file_with_limits(path, YamlLimits::for_path(path))
}

/// Loads a YAML file from disk with explicit [`YamlLimits`].
#[must_use]
pub fn load_file_with_limits(path: impl AsRef<Path>, limits: YamlLimits) -> Loaded {
    let path = path.as_ref();
    let path_str = path.to_string_lossy().into_owned();

    if bad_file_name(path) {
        let name = path
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| path_str.clone());
        return Loaded::from_error(LoadError::new(
            path_str,
            1,
            1,
            "YAML-BAD-FILENAME",
            format!(
                "a refused character in the file name: {}",
                visible_name(&name)
            ),
        ));
    }

    let file = match File::open(path) {
        Ok(f) => f,
        Err(e) => {
            return Loaded::from_error(LoadError::new(
                path_str,
                1,
                1,
                "YAML-IO",
                format!("cannot read file: {}", visible_name(&e.to_string())),
            ));
        }
    };

    let mut raw = Vec::new();
    let read_cap = (limits.max_bytes as u64).saturating_add(1);
    if let Err(e) = file.take(read_cap).read_to_end(&mut raw) {
        return Loaded::from_error(LoadError::new(
            path_str,
            1,
            1,
            "YAML-IO",
            format!("cannot read file: {}", visible_name(&e.to_string())),
        ));
    }

    if raw.len() > limits.max_bytes {
        return Loaded::from_error(LoadError::new(
            path_str,
            1,
            1,
            "YAML-SIZE-LIMIT",
            format!("file exceeds the {}-byte limit", limits.max_bytes),
        ));
    }

    for bom in BOMS {
        if raw.starts_with(bom) {
            return Loaded::from_error(LoadError::new(
                path_str,
                1,
                1,
                "YAML-BOM",
                "a byte-order mark; save the file as UTF-8 without one",
            ));
        }
    }

    let text = match std::str::from_utf8(&raw) {
        Ok(s) => s,
        Err(exc) => {
            let before = std::str::from_utf8(&raw[..exc.valid_up_to()]).unwrap_or("");
            let line = before.bytes().filter(|&b| b == b'\n').count() + 1;
            let last_line = before.rsplit('\n').next().unwrap_or(before);
            let col = last_line.chars().count() + 1;
            return Loaded::from_error(LoadError::new(
                path_str,
                line,
                col,
                "YAML-UTF8",
                format!("bytes that are not UTF-8 ({exc})"),
            ));
        }
    };

    load_text_with_limits(text, path, limits)
}

/// Loads YAML from an in-memory string `source` using path-appropriate limits (`YamlLimits::for_path`).
#[must_use]
pub fn load_text(source: &str, path: impl AsRef<Path>) -> Loaded {
    let path = path.as_ref();
    load_text_with_limits(source, path, YamlLimits::for_path(path))
}

/// Scans raw YAML source text for lone CR and refused Unicode characters before parsing.
fn check_text(path_str: &str, source: &str) -> Result<(), LoadError> {
    let mut line = 1usize;
    let mut col = 1usize;
    let mut chars = source.chars().peekable();

    while let Some(ch) = chars.next() {
        if ch == '\n' {
            line += 1;
            col = 1;
            continue;
        }
        if ch == ' ' || ch == '\t' {
            col += 1;
            continue;
        }
        if ch == '\r' {
            if chars.peek() == Some(&'\n') {
                col += 1;
                continue;
            }
            return Err(LoadError::new(
                path_str,
                line,
                col,
                "YAML-LONE-CR",
                "a refused character in the file: a lone CR (use LF or CRLF line endings)",
            ));
        }
        if is_yaml_refused_char(ch) {
            return Err(LoadError::new(
                path_str,
                line,
                col,
                "YAML-REFUSED-CHAR",
                format!("a refused character in the file: {}", char_label(ch)),
            ));
        }
        col += 1;
    }
    Ok(())
}

/// Checks if the document begins with a `%DIRECTIVE` line before any content token.
fn check_leading_directive(path_str: &str, source: &str) -> Result<(), LoadError> {
    for (idx, raw_line) in source.split('\n').enumerate() {
        let line_no = idx + 1;
        let trimmed = raw_line.trim_start_matches([' ', '\t']);
        if trimmed.is_empty() || trimmed.starts_with('\r') || trimmed.starts_with('#') {
            continue;
        }
        if let Some(rest) = raw_line.strip_prefix('%') {
            let name: String = rest
                .chars()
                .take_while(|c| !c.is_whitespace() && *c != '#')
                .collect();
            return Err(LoadError::new(
                path_str,
                line_no,
                1,
                "YAML-DIRECTIVE",
                format!("a %{name} directive (write none)"),
            ));
        }
        break;
    }
    Ok(())
}

fn span_mark(span: Span) -> Mark {
    Mark {
        line: span.start.line().max(1),
        column: span.start.col() + 1,
    }
}

/// Locates an `&anchor` or `!tag` token in `source` between character indices `from_char` and
/// `to_char` (only called on the cold error path when `anchor_id > 0` or `tag.is_some()`).
fn find_anchor_or_tag_error(
    path_str: &str,
    source: &str,
    from_char: usize,
    to_char: usize,
    has_anchor: bool,
    tag_fallback: Option<String>,
    fallback_mark: Mark,
) -> LoadError {
    let chars: Vec<char> = source.chars().collect();
    let end = to_char.min(chars.len());
    let start = from_char.min(end);

    let mut line = 1usize;
    let mut col = 1usize;
    for &c in &chars[..start] {
        if c == '\n' {
            line += 1;
            col = 1;
        } else {
            col += 1;
        }
    }

    let mut i = start;
    let mut in_comment = false;
    while i < end {
        let c = chars[i];
        if in_comment {
            if c == '\n' {
                in_comment = false;
                line += 1;
                col = 1;
            } else {
                col += 1;
            }
            i += 1;
            continue;
        }
        if c == '#' {
            in_comment = true;
            col += 1;
            i += 1;
            continue;
        }
        if c == '&' && has_anchor {
            let err_line = line;
            let err_col = col;
            i += 1;
            let mut name = String::new();
            while i < chars.len() {
                let nc = chars[i];
                if nc.is_whitespace() || matches!(nc, '[' | ']' | '{' | '}' | ',') {
                    break;
                }
                name.push(nc);
                i += 1;
            }
            return LoadError::new(
                path_str,
                err_line,
                err_col,
                "YAML-ANCHOR",
                format!(
                    "an anchor (&{}); anchors are not allowed",
                    visible_name(&name)
                ),
            );
        }
        if c == '!' && tag_fallback.is_some() {
            let err_line = line;
            let err_col = col;
            let mut raw_tag = String::new();
            while i < chars.len() {
                let nc = chars[i];
                if nc.is_whitespace() || matches!(nc, '[' | ']' | '{' | '}' | ',') {
                    break;
                }
                raw_tag.push(nc);
                i += 1;
            }
            return LoadError::new(
                path_str,
                err_line,
                err_col,
                "YAML-TAG",
                format!(
                    "an explicit tag ({}); tags are not allowed",
                    visible_name(&raw_tag)
                ),
            );
        }
        if c == '\n' {
            line += 1;
            col = 1;
        } else {
            col += 1;
        }
        i += 1;
    }

    if has_anchor {
        LoadError::new(
            path_str,
            fallback_mark.line,
            fallback_mark.column,
            "YAML-ANCHOR",
            "an anchor (&); anchors are not allowed",
        )
    } else {
        let t = tag_fallback.unwrap_or_else(|| "!".to_string());
        LoadError::new(
            path_str,
            fallback_mark.line,
            fallback_mark.column,
            "YAML-TAG",
            format!(
                "an explicit tag ({}); tags are not allowed",
                visible_name(&t)
            ),
        )
    }
}

fn extract_token_at_char(source: &str, char_idx: usize) -> String {
    source
        .chars()
        .skip(char_idx)
        .take_while(|c| !c.is_whitespace() && !matches!(c, '[' | ']' | '{' | '}' | ','))
        .collect()
}

enum EscapeErrorKind {
    Surrogate { quote_col: usize, cp: u32 },
    BeyondUnicode { hex_col: usize },
}

/// Inspects line `line_no` (1-based) for a UTF-16 surrogate escape (`\uD800`..`\uDFFF` or
/// `\UD800`..`\UDFFF`) or an out-of-range `\UXXXXXXXX` code point (`> 0x10FFFF`).
fn classify_escape_error_on_line(
    source: &str,
    line_no: usize,
    err_col: usize,
) -> Option<EscapeErrorKind> {
    let line_str = source.split('\n').nth(line_no.saturating_sub(1))?;
    let chars: Vec<char> = line_str.chars().collect();
    let mut quote_col = err_col;
    for (idx, &c) in chars.iter().enumerate() {
        if c == '"' && idx + 1 >= err_col && quote_col == err_col {
            quote_col = idx + 1;
        }
        if idx + 1 < err_col {
            continue;
        }
        if c == '\\' && idx + 5 < chars.len() && (chars[idx + 1] == 'u' || chars[idx + 1] == 'U') {
            let hex_len = if chars[idx + 1] == 'u' { 4 } else { 8 };
            if idx + 2 + hex_len <= chars.len() {
                let hex_str: String = chars[idx + 2..idx + 2 + hex_len].iter().collect();
                if let Ok(cp) = u32::from_str_radix(&hex_str, 16) {
                    if (0xD800..=0xDFFF).contains(&cp) {
                        return Some(EscapeErrorKind::Surrogate { quote_col, cp });
                    }
                    if cp > 0x10FFFF {
                        return Some(EscapeErrorKind::BeyondUnicode { hex_col: idx + 3 });
                    }
                }
            }
        }
    }
    None
}

/// Checks whether `val` matches `^(?:0|-?[1-9][0-9]*)$`.
fn is_decimal_integer_token(val: &str) -> bool {
    if val == "0" {
        return true;
    }
    let digits = val.strip_prefix('-').unwrap_or(val);
    let mut chars = digits.chars();
    match chars.next() {
        Some('1'..='9') => chars.all(|c| c.is_ascii_digit()),
        _ => false,
    }
}

/// Checks whether `val` matches strict YAML 1.2 Core Schema hex integer `^0x[0-9a-fA-F]+$`
/// (no underscores, so `0x7E20_1000` remains a string while `0x10` resolves to `16`).
fn is_core_hex_integer_token(val: &str) -> Option<&str> {
    let hex_digits = val.strip_prefix("0x").or_else(|| val.strip_prefix("0X"))?;
    if !hex_digits.is_empty() && hex_digits.chars().all(|c| c.is_ascii_hexdigit()) {
        Some(hex_digits)
    } else {
        None
    }
}

/// Locates `ch` literally inside `span` in `source` (matching `specload.py:_locate`),
/// falling back to `fallback_mark` if `ch` was produced by an escape sequence.
fn locate_char_in_span(source: &str, span: Span, ch: char, fallback_mark: Mark) -> Mark {
    let start_idx = span.start.index();
    let end_idx = span.end.index().max(start_idx + 1);
    let mut line = 1usize;
    let mut col = 1usize;
    for (idx, c) in source.chars().enumerate() {
        if idx >= start_idx && idx < end_idx && c == ch {
            return Mark::new(line, col);
        }
        if idx >= end_idx {
            break;
        }
        if c == '\n' {
            line += 1;
            col = 1;
        } else {
            col += 1;
        }
    }
    fallback_mark
}

/// Computes the 1-based column for an empty plain scalar so `a:\n` reports column 3 (after `:`)
/// and `  -\n` reports column 4 (after `-`), matching `specload.py`.
fn empty_scalar_mark(source: &str, span: Span, mark: Mark, is_expecting_key: bool) -> Mark {
    if is_expecting_key {
        return mark;
    }
    let line_str = source
        .split('\n')
        .nth(mark.line.saturating_sub(1))
        .unwrap_or("");
    let ch_at = line_str.chars().nth(mark.column.saturating_sub(1));
    if matches!(ch_at, Some(':' | '-')) {
        Mark::new(mark.line, mark.column + 1)
    } else if matches!(ch_at, Some('}' | ']' | ',')) && mark.column > 1 {
        let prev = line_str.chars().nth(mark.column.saturating_sub(2));
        if prev == Some(' ') {
            Mark::new(mark.line, mark.column - 1)
        } else {
            mark
        }
    } else {
        let _ = span;
        mark
    }
}

/// Resolves a scalar according to strict YAML 1.2 rules.
fn resolve_scalar(
    path_str: &str,
    source: &str,
    val: &str,
    style: ScalarStyle,
    span: Span,
    mark: Mark,
    is_expecting_key: bool,
) -> Result<Value, LoadError> {
    if style == ScalarStyle::Plain {
        if val.is_empty() {
            let em = empty_scalar_mark(source, span, mark, is_expecting_key);
            return Err(LoadError::new(
                path_str,
                em.line,
                em.column,
                "YAML-EMPTY-VALUE",
                "an empty value; write null or \"\"",
            ));
        }
        match val {
            "true" => return Ok(Value::Bool(true)),
            "false" => return Ok(Value::Bool(false)),
            "null" => return Ok(Value::Null),
            _ => {}
        }
        if is_decimal_integer_token(val) {
            return match val.parse::<i64>() {
                Ok(n) => Ok(Value::Number(Number::from(n))),
                Err(_) => Err(LoadError::new(
                    path_str,
                    mark.line,
                    mark.column,
                    "YAML-INT-RANGE",
                    "an integer outside the signed 64-bit range; quote it if it is a string",
                )),
            };
        }
        if let Some(hex_digits) = is_core_hex_integer_token(val) {
            return match i64::from_str_radix(hex_digits, 16) {
                Ok(n) => Ok(Value::Number(Number::from(n))),
                Err(_) => Err(LoadError::new(
                    path_str,
                    mark.line,
                    mark.column,
                    "YAML-INT-RANGE",
                    "an integer outside the signed 64-bit range; quote it if it is a string",
                )),
            };
        }
    }

    // Note: `check_text` already verified that `source` contains no refused character other than
    // `\t`. Only `ScalarStyle::DoubleQuoted` can introduce new characters via `\` escapes; for all
    // other styles, the only refused character that can appear in `val` is `\t`.
    if style == ScalarStyle::DoubleQuoted {
        for ch in val.chars() {
            if ch != '\n' && ch != ' ' && is_yaml_refused_char(ch) {
                let loc = locate_char_in_span(source, span, ch, mark);
                return Err(LoadError::new(
                    path_str,
                    loc.line,
                    loc.column,
                    "YAML-REFUSED-STRING-CHAR",
                    format!("a string holding {}", char_label(ch)),
                ));
            }
        }
    } else if val.contains('\t') {
        let loc = locate_char_in_span(source, span, '\t', mark);
        return Err(LoadError::new(
            path_str,
            loc.line,
            loc.column,
            "YAML-REFUSED-STRING-CHAR",
            format!("a string holding {}", char_label('\t')),
        ));
    }

    // Pure-ASCII strings are trivially in Unicode NFC form.
    if !val.is_ascii() && !is_nfc(val) {
        return Err(LoadError::new(
            path_str,
            mark.line,
            mark.column,
            "YAML-NON-NFC",
            "a string that is not in Unicode NFC form",
        ));
    }

    Ok(Value::String(val.to_string()))
}

enum ContainerFrame {
    Sequence {
        mark: Mark,
        items: Vec<Value>,
        mark_items: Vec<MarkNode>,
        depth: usize,
    },
    Mapping {
        mark: Mark,
        map: Map<String, Value>,
        mark_entries: Vec<(String, Mark, MarkNode)>,
        pending_key: Option<(String, Mark)>,
        depth: usize,
    },
}

impl ContainerFrame {
    fn depth(&self) -> usize {
        match self {
            Self::Sequence { depth, .. } | Self::Mapping { depth, .. } => *depth,
        }
    }

    fn is_expecting_key(&self) -> bool {
        matches!(
            self,
            Self::Mapping {
                pending_key: None,
                ..
            }
        )
    }
}

/// Loads YAML from `source` enforcing `limits` and recording 1-based source spans.
#[must_use]
pub fn load_text_with_limits(source: &str, path: impl AsRef<Path>, limits: YamlLimits) -> Loaded {
    let path = path.as_ref();
    let path_str = path.to_string_lossy().into_owned();

    if bad_file_name(path) {
        let name = path
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| path_str.clone());
        return Loaded::from_error(LoadError::new(
            path_str,
            1,
            1,
            "YAML-BAD-FILENAME",
            format!(
                "a refused character in the file name: {}",
                visible_name(&name)
            ),
        ));
    }

    if source.len() > limits.max_bytes {
        return Loaded::from_error(LoadError::new(
            path_str,
            1,
            1,
            "YAML-SIZE-LIMIT",
            format!("file exceeds the {}-byte limit", limits.max_bytes),
        ));
    }

    if source.starts_with('\u{FEFF}') {
        return Loaded::from_error(LoadError::new(
            path_str,
            1,
            1,
            "YAML-BOM",
            "a byte-order mark; save the file as UTF-8 without one",
        ));
    }

    if let Err(err) = check_text(&path_str, source) {
        return Loaded::from_error(err);
    }

    if let Err(err) = check_leading_directive(&path_str, source) {
        return Loaded::from_error(err);
    }

    let mut parser = Parser::new_from_str(source);
    let mut doc_count = 0usize;
    let mut node_count = 0usize;
    let mut last_char_idx = 0usize;
    let mut stack: Vec<ContainerFrame> = Vec::new();
    let mut root_value: Option<Value> = None;
    let mut root_mark: Option<MarkNode> = None;

    let mut check_limits = |depth: usize, mark: Mark| -> Result<(), LoadError> {
        if depth > limits.max_depth {
            return Err(LoadError::new(
                &path_str,
                1,
                1,
                "YAML-DEPTH-LIMIT",
                format!(
                    "nesting too deep (exceeds the {}-level limit)",
                    limits.max_depth
                ),
            ));
        }
        node_count += 1;
        if node_count > limits.max_nodes {
            return Err(LoadError::new(
                &path_str,
                mark.line,
                mark.column,
                "YAML-NODE-LIMIT",
                format!("document exceeds the {}-node limit", limits.max_nodes),
            ));
        }
        Ok(())
    };

    while let Some(ev_res) = parser.next_event() {
        let (event, span) = match ev_res {
            Ok(pair) => pair,
            Err(scan_err) => {
                let m = scan_err.marker();
                let line = m.line().max(1);
                let col = m.col() + 1;
                let info = scan_err.info();
                if info.contains("unknown anchor") {
                    let raw = extract_token_at_char(source, m.index());
                    let name = raw.strip_prefix('*').unwrap_or(&raw);
                    return Loaded::from_error(LoadError::new(
                        path_str,
                        line,
                        col,
                        "YAML-ALIAS",
                        format!("an alias (*{}); write the value out", visible_name(name)),
                    ));
                }
                if info.contains("handle wasn't declared") || info.contains("while parsing a tag") {
                    let raw = extract_token_at_char(source, m.index());
                    return Loaded::from_error(LoadError::new(
                        path_str,
                        line,
                        col,
                        "YAML-TAG",
                        format!(
                            "an explicit tag ({}); tags are not allowed",
                            visible_name(&raw)
                        ),
                    ));
                }
                if info.contains("directive") {
                    let raw = extract_token_at_char(source, m.index());
                    let name = raw.strip_prefix('%').unwrap_or(&raw);
                    return Loaded::from_error(LoadError::new(
                        path_str,
                        line,
                        col,
                        "YAML-DIRECTIVE",
                        format!("a %{} directive (write none)", visible_name(name)),
                    ));
                }
                if info.contains("escape") {
                    let mut mal_col = col;
                    match classify_escape_error_on_line(source, line, col) {
                        Some(EscapeErrorKind::Surrogate { quote_col, cp }) => {
                            return Loaded::from_error(LoadError::new(
                                path_str,
                                line,
                                quote_col,
                                "YAML-REFUSED-STRING-CHAR",
                                format!("a string holding U+{cp:04X} (surrogate, category Cs)"),
                            ));
                        }
                        Some(EscapeErrorKind::BeyondUnicode { hex_col }) => {
                            mal_col = hex_col;
                        }
                        None => {}
                    }
                    return Loaded::from_error(LoadError::new(
                        path_str,
                        line,
                        mal_col,
                        "YAML-MALFORMED-SCALAR",
                        format!("a malformed scalar ({})", visible_name(info)),
                    ));
                }
                if info.contains("depth") || info.contains("recursion") {
                    return Loaded::from_error(LoadError::new(
                        path_str,
                        1,
                        1,
                        "YAML-DEPTH-LIMIT",
                        format!(
                            "nesting too deep (exceeds the {}-level limit)",
                            limits.max_depth
                        ),
                    ));
                }
                return Loaded::from_error(LoadError::new(
                    path_str,
                    line,
                    col,
                    "YAML-SYNTAX",
                    format!("YAML syntax error: {}", visible_name(info)),
                ));
            }
        };

        let mark = span_mark(span);

        match event {
            Event::StreamStart | Event::StreamEnd | Event::Nothing | Event::DocumentEnd => {
                last_char_idx = span.end.index();
            }
            Event::DocumentStart(_) => {
                doc_count += 1;
                if doc_count > 1 {
                    return Loaded::from_error(LoadError::new(
                        path_str,
                        mark.line,
                        mark.column,
                        "YAML-MULTI-DOC",
                        "more than one YAML document; a file holds exactly one",
                    ));
                }
                last_char_idx = span.end.index();
            }
            Event::Alias(_) => {
                let raw = extract_token_at_char(source, span.start.index());
                let name = raw.strip_prefix('*').unwrap_or(&raw);
                return Loaded::from_error(LoadError::new(
                    path_str,
                    mark.line,
                    mark.column,
                    "YAML-ALIAS",
                    format!("an alias (*{}); write the value out", visible_name(name)),
                ));
            }
            Event::SequenceStart(anchor_id, tag) => {
                if anchor_id > 0 || tag.is_some() {
                    let err = find_anchor_or_tag_error(
                        &path_str,
                        source,
                        last_char_idx,
                        span.start.index(),
                        anchor_id > 0,
                        tag.map(|t| t.to_string()),
                        mark,
                    );
                    return Loaded::from_error(err);
                }
                if stack.last().is_some_and(ContainerFrame::is_expecting_key) {
                    return Loaded::from_error(LoadError::new(
                        path_str,
                        mark.line,
                        mark.column,
                        "YAML-COMPLEX-KEY",
                        "a mapping or list used as a key",
                    ));
                }
                let depth = stack.last().map_or(1, |f| f.depth() + 1);
                if let Err(err) = check_limits(depth, mark) {
                    return Loaded::from_error(err);
                }
                stack.push(ContainerFrame::Sequence {
                    mark,
                    items: Vec::new(),
                    mark_items: Vec::new(),
                    depth,
                });
                last_char_idx = span.end.index();
            }
            Event::MappingStart(anchor_id, tag) => {
                if anchor_id > 0 || tag.is_some() {
                    let err = find_anchor_or_tag_error(
                        &path_str,
                        source,
                        last_char_idx,
                        span.start.index(),
                        anchor_id > 0,
                        tag.map(|t| t.to_string()),
                        mark,
                    );
                    return Loaded::from_error(err);
                }
                if stack.last().is_some_and(ContainerFrame::is_expecting_key) {
                    return Loaded::from_error(LoadError::new(
                        path_str,
                        mark.line,
                        mark.column,
                        "YAML-COMPLEX-KEY",
                        "a mapping or list used as a key",
                    ));
                }
                let depth = stack.last().map_or(1, |f| f.depth() + 1);
                if let Err(err) = check_limits(depth, mark) {
                    return Loaded::from_error(err);
                }
                stack.push(ContainerFrame::Mapping {
                    mark,
                    map: Map::new(),
                    mark_entries: Vec::new(),
                    pending_key: None,
                    depth,
                });
                last_char_idx = span.end.index();
            }
            Event::SequenceEnd | Event::MappingEnd => {
                let (finished_val, finished_mark) = match stack.pop() {
                    Some(ContainerFrame::Sequence {
                        mark: m,
                        items,
                        mark_items,
                        ..
                    }) => (
                        Value::Array(items),
                        MarkNode::Sequence {
                            mark: m,
                            items: mark_items,
                        },
                    ),
                    Some(ContainerFrame::Mapping {
                        mark: m,
                        map,
                        mark_entries,
                        ..
                    }) => (
                        Value::Object(map),
                        MarkNode::Mapping {
                            mark: m,
                            entries: mark_entries,
                        },
                    ),
                    None => {
                        return Loaded::from_error(LoadError::new(
                            path_str,
                            mark.line,
                            mark.column,
                            "YAML-SYNTAX",
                            "unexpected container end",
                        ));
                    }
                };
                match stack.last_mut() {
                    Some(ContainerFrame::Sequence {
                        items, mark_items, ..
                    }) => {
                        items.push(finished_val);
                        mark_items.push(finished_mark);
                    }
                    Some(ContainerFrame::Mapping {
                        map,
                        mark_entries,
                        pending_key,
                        ..
                    }) => {
                        if let Some((k, km)) = pending_key.take() {
                            mark_entries.push((k.clone(), km, finished_mark));
                            map.insert(k, finished_val);
                        }
                    }
                    None => {
                        root_value = Some(finished_val);
                        root_mark = Some(finished_mark);
                    }
                }
                last_char_idx = span.end.index();
            }
            Event::Scalar(val, style, anchor_id, tag) => {
                if anchor_id > 0 || tag.is_some() {
                    let err = find_anchor_or_tag_error(
                        &path_str,
                        source,
                        last_char_idx,
                        span.start.index(),
                        anchor_id > 0,
                        tag.map(|t| t.to_string()),
                        mark,
                    );
                    return Loaded::from_error(err);
                }

                let depth = stack.last().map_or(1, |f| f.depth() + 1);
                if let Err(err) = check_limits(depth, mark) {
                    return Loaded::from_error(err);
                }

                if stack.last().is_some_and(ContainerFrame::is_expecting_key) {
                    let resolved =
                        match resolve_scalar(&path_str, source, &val, style, span, mark, true) {
                            Ok(v) => v,
                            Err(err) => return Loaded::from_error(err),
                        };
                    let key_str = match resolved {
                        Value::String(s) => s,
                        _ => {
                            return Loaded::from_error(LoadError::new(
                                path_str,
                                mark.line,
                                mark.column,
                                "YAML-NON-STRING-KEY",
                                format!(
                                    "a non-string key ({}); quote it if it is a name",
                                    visible_name(&val)
                                ),
                            ));
                        }
                    };
                    if key_str == "<<" {
                        return Loaded::from_error(LoadError::new(
                            path_str,
                            mark.line,
                            mark.column,
                            "YAML-MERGE-KEY",
                            "a merge key (<<); write the keys out",
                        ));
                    }
                    if let Some(ContainerFrame::Mapping {
                        map, pending_key, ..
                    }) = stack.last_mut()
                    {
                        if map.contains_key(&key_str) {
                            return Loaded::from_error(LoadError::new(
                                path_str,
                                mark.line,
                                mark.column,
                                "YAML-DUPLICATE-KEY",
                                format!("a duplicate key: {}", visible_name(&key_str)),
                            ));
                        }
                        *pending_key = Some((key_str, mark));
                    }
                } else {
                    let resolved =
                        match resolve_scalar(&path_str, source, &val, style, span, mark, false) {
                            Ok(v) => v,
                            Err(err) => return Loaded::from_error(err),
                        };
                    let scalar_mark = MarkNode::Scalar(mark);
                    match stack.last_mut() {
                        Some(ContainerFrame::Sequence {
                            items, mark_items, ..
                        }) => {
                            items.push(resolved);
                            mark_items.push(scalar_mark);
                        }
                        Some(ContainerFrame::Mapping {
                            map,
                            mark_entries,
                            pending_key,
                            ..
                        }) => {
                            if let Some((k, km)) = pending_key.take() {
                                mark_entries.push((k.clone(), km, scalar_mark));
                                map.insert(k, resolved);
                            }
                        }
                        None => {
                            root_value = Some(resolved);
                            root_mark = Some(scalar_mark);
                        }
                    }
                }
                last_char_idx = span.end.index();
            }
        }
    }

    if doc_count == 0 {
        return Loaded::from_error(LoadError::new(
            path_str,
            1,
            1,
            "YAML-EMPTY",
            "an empty file: no YAML document",
        ));
    }

    Loaded {
        data: root_value,
        errors: Vec::new(),
        root_mark,
    }
}
