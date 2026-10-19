// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! SPDX 2.3 license expression parser, compatibility checker, `LicenseRef-*` public-root
//! guard (`BF-IMX-ISS-5`), SPDX source header scanner, copyright attribution scanner/comparator
//! and `ATTRIBUTION.md` generator/checker, and `license-gate` implementation.

use crate::diagnostic::{
    visible_name, ExitCode, Finding, EXIT_DOMAIN_FAILURE, EXIT_OK, EXIT_USAGE_ERROR,
};
use crate::yaml_strict::{self, PathSegment};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeSet, HashMap};
use std::fmt;
use std::path::Path;
use std::sync::OnceLock;

/// Maximum parentheses nesting depth in an SPDX expression (`spdx.py:MAX_DEPTH`).
pub const MAX_DEPTH: usize = 32;

/// Canonical SPDX license identifiers recognized by the parser (`spdx.py:KNOWN` + standard IDs).
pub const KNOWN_LICENSES: &[&str] = &[
    "0BSD",
    "AGPL-3.0-only",
    "AGPL-3.0-or-later",
    "Apache-1.1",
    "Apache-2.0",
    "Artistic-2.0",
    "BSD-1-Clause",
    "BSD-2-Clause",
    "BSD-2-Clause-Patent",
    "BSD-2-Clause-Views",
    "BSD-3-Clause",
    "BSD-3-Clause-Clear",
    "BSD-4-Clause",
    "BSL-1.0",
    "bzip2-1.0.6",
    "CC-BY-3.0",
    "CC-BY-4.0",
    "CC-BY-SA-3.0",
    "CC-BY-SA-4.0",
    "CC0-1.0",
    "CDDL-1.0",
    "CDDL-1.1",
    "EPL-1.0",
    "EPL-2.0",
    "GFDL-1.1-no-invariants-or-later",
    "GFDL-1.2-no-invariants-only",
    "GPL-1.0-only",
    "GPL-1.0-or-later",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "ISC",
    "LGPL-2.0-only",
    "LGPL-2.0-or-later",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "Linux-OpenIB",
    "MirOS",
    "MIT",
    "MIT-0",
    "MPL-1.1",
    "MPL-2.0",
    "NCSA",
    "OpenSSL",
    "PostgreSQL",
    "Python-2.0",
    "Unlicense",
    "UPL-1.0",
    "X11",
    "Zlib",
];

/// Deprecated GNU SPDX identifiers and their canonical SPDX replacements (`spdx.py:DEPRECATED`).
pub const DEPRECATED_LICENSES: &[(&str, &str)] = &[
    ("GPL-1.0", "GPL-1.0-only"),
    ("GPL-2.0", "GPL-2.0-only"),
    ("GPL-3.0", "GPL-3.0-only"),
    ("LGPL-2.0", "LGPL-2.0-only"),
    ("LGPL-2.1", "LGPL-2.1-only"),
    ("LGPL-3.0", "LGPL-3.0-only"),
    ("AGPL-3.0", "AGPL-3.0-only"),
];

/// Canonical SPDX license exception identifiers (`spdx.py:EXCEPTIONS`).
pub const KNOWN_EXCEPTIONS: &[&str] = &[
    "Autoconf-exception-2.0",
    "Autoconf-exception-3.0",
    "Bison-exception-2.2",
    "Classpath-exception-2.0",
    "GCC-exception-2.0",
    "GCC-exception-3.1",
    "Linux-syscall-note",
    "LLVM-exception",
    "Qt-GPL-exception-1.0",
    "u-boot-exception-2.0",
    "Universal-FOSS-exception-1.0",
];

/// Error returned when parsing or validating an SPDX license expression.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SpdxError(pub String);

impl SpdxError {
    /// Returns the error message string.
    #[must_use]
    pub fn message(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for SpdxError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for SpdxError {}

/// Parsed SPDX 2.3 expression AST.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SpdxExpr {
    /// Single license identifier in canonical case (e.g. `"MIT"`, `"GPL-2.0-or-later"`, `"Apache-2.0+"`).
    License(String),
    /// License with exception (`<license> WITH <exception>`, both in canonical case).
    With(String, String),
    /// Conjunctive requirement (`<left> AND <right>`).
    And(Box<SpdxExpr>, Box<SpdxExpr>),
    /// Disjunctive choice (`<left> OR <right>`).
    Or(Box<SpdxExpr>, Box<SpdxExpr>),
}

impl SpdxExpr {
    /// Returns `true` if any license identifier in this expression is a `LicenseRef-*`
    /// or `DocumentRef-*:LicenseRef-*` custom reference (`BF-IMX-ISS-5`).
    #[must_use]
    pub fn has_license_ref(&self) -> bool {
        self.first_license_ref().is_some()
    }

    /// Returns the first `LicenseRef-*` or `DocumentRef-*:LicenseRef-*` identifier in
    /// this expression, if any (`BF-IMX-ISS-5`).
    #[must_use]
    pub fn first_license_ref(&self) -> Option<&str> {
        match self {
            Self::License(id) | Self::With(id, _) => {
                if is_licenseref_id(id) {
                    Some(id.as_str())
                } else {
                    None
                }
            }
            Self::And(l, r) | Self::Or(l, r) => {
                l.first_license_ref().or_else(|| r.first_license_ref())
            }
        }
    }

    /// Computes a canonical, commutative/associative key for comparing two SPDX expressions
    /// for structural equivalence (port of `resolve.py:license_key`).
    #[must_use]
    pub fn canonical_key(&self) -> String {
        match self {
            Self::License(id) => format!("license:{}", id.to_ascii_lowercase()),
            Self::With(id, exc) => {
                format!(
                    "with:{}:{}",
                    id.to_ascii_lowercase(),
                    exc.to_ascii_lowercase()
                )
            }
            Self::And(_, _) => {
                let mut parts = Vec::new();
                collect_op_keys(self, true, &mut parts);
                parts.sort();
                parts.dedup();
                format!("and:({})", parts.join(","))
            }
            Self::Or(_, _) => {
                let mut parts = Vec::new();
                collect_op_keys(self, false, &mut parts);
                parts.sort();
                parts.dedup();
                format!("or:({})", parts.join(","))
            }
        }
    }
}

fn collect_op_keys(expr: &SpdxExpr, is_and: bool, out: &mut Vec<String>) {
    match (expr, is_and) {
        (SpdxExpr::And(l, r), true) | (SpdxExpr::Or(l, r), false) => {
            collect_op_keys(l, is_and, out);
            collect_op_keys(r, is_and, out);
        }
        _ => out.push(expr.canonical_key()),
    }
}

fn collect_op_nodes<'a>(expr: &'a SpdxExpr, is_and: bool, out: &mut Vec<&'a SpdxExpr>) {
    match (expr, is_and) {
        (SpdxExpr::And(l, r), true) | (SpdxExpr::Or(l, r), false) => {
            collect_op_nodes(l, is_and, out);
            collect_op_nodes(r, is_and, out);
        }
        _ => out.push(expr),
    }
}

impl fmt::Display for SpdxExpr {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::License(id) => f.write_str(id),
            Self::With(id, exc) => write!(f, "{id} WITH {exc}"),
            Self::And(_, _) => {
                let mut nodes = Vec::new();
                collect_op_nodes(self, true, &mut nodes);
                for (i, node) in nodes.iter().enumerate() {
                    if i > 0 {
                        f.write_str(" AND ")?;
                    }
                    if matches!(node, Self::Or(_, _)) {
                        write!(f, "({node})")?;
                    } else {
                        write!(f, "{node}")?;
                    }
                }
                Ok(())
            }
            Self::Or(_, _) => {
                let mut nodes = Vec::new();
                collect_op_nodes(self, false, &mut nodes);
                for (i, node) in nodes.iter().enumerate() {
                    if i > 0 {
                        f.write_str(" OR ")?;
                    }
                    if matches!(node, Self::And(_, _)) {
                        write!(f, "({node})")?;
                    } else {
                        write!(f, "{node}")?;
                    }
                }
                Ok(())
            }
        }
    }
}

/// Returns `true` if `id` is a `LicenseRef-*` or `DocumentRef-*:LicenseRef-*` token (case-insensitive).
#[must_use]
pub fn is_licenseref_id(id: &str) -> bool {
    let lower = id.to_ascii_lowercase();
    lower.starts_with("licenseref-") || lower.starts_with("documentref-")
}

fn is_idstring(s: &str) -> bool {
    !s.is_empty()
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '-')
}

/// Matches `^(?:DocumentRef-[A-Za-z0-9.-]+:)?LicenseRef-[A-Za-z0-9.-]+$` (case-insensitive
/// for `licenseref-`/`documentref-` prefix, canonicalizing prefix case while keeping ID body).
fn normalize_license_ref(word: &str) -> Option<String> {
    let lower = word.to_ascii_lowercase();
    if let Some(after_doc) = lower.strip_prefix("documentref-") {
        let colon_pos = after_doc.find(':')?;
        let doc_id = &word["DocumentRef-".len().."DocumentRef-".len() + colon_pos];
        if !is_idstring(doc_id) {
            return None;
        }
        let rest = &word["DocumentRef-".len() + colon_pos + 1..];
        let rest_lower = rest.to_ascii_lowercase();
        if rest_lower.starts_with("licenseref-") {
            let ref_id = &rest["LicenseRef-".len()..];
            if is_idstring(ref_id) {
                return Some(format!("DocumentRef-{doc_id}:LicenseRef-{ref_id}"));
            }
        }
        return None;
    }
    if lower.starts_with("licenseref-") {
        let ref_id = &word["LicenseRef-".len()..];
        if is_idstring(ref_id) {
            return Some(format!("LicenseRef-{ref_id}"));
        }
    }
    None
}

fn lookup_known_license(lower: &str) -> Option<&'static str> {
    KNOWN_LICENSES
        .iter()
        .copied()
        .find(|&k| k.eq_ignore_ascii_case(lower))
}

fn lookup_deprecated_license(lower: &str) -> Option<&'static str> {
    DEPRECATED_LICENSES.iter().find_map(|&(dep, repl)| {
        if dep.eq_ignore_ascii_case(lower) {
            Some(repl)
        } else {
            None
        }
    })
}

fn lookup_known_exception(lower: &str) -> Option<&'static str> {
    KNOWN_EXCEPTIONS
        .iter()
        .copied()
        .find(|&e| e.eq_ignore_ascii_case(lower))
}

/// Normalizes a single SPDX license identifier token (with optional trailing `+`),
/// matching `spdx.py:normalize_id`.
pub fn normalize_id(word: &str) -> Result<String, SpdxError> {
    if let Some(canon_ref) = normalize_license_ref(word) {
        return Ok(canon_ref);
    }
    let plus = word.ends_with('+');
    let base = if plus { &word[..word.len() - 1] } else { word };
    if base.is_empty() {
        return Err(SpdxError(format!(
            "'{}' is not a license identifier",
            visible_name(word)
        )));
    }
    let key = base.to_ascii_lowercase();
    let canonical = if let Some(dep) = lookup_deprecated_license(&key) {
        dep
    } else if let Some(known) = lookup_known_license(&key) {
        known
    } else if matches!(key.as_str(), "and" | "or" | "with") {
        return Err(SpdxError(format!(
            "'{}': write the operator in uppercase ({})",
            visible_name(word),
            base.to_ascii_uppercase()
        )));
    } else {
        return Err(SpdxError(format!(
            "unknown SPDX license identifier '{}' (the known identifiers are listed in \
             board-expert/scripts/spdx.py; write LicenseRef-<name> for a license SPDX does \
             not list)",
            visible_name(base)
        )));
    };
    if !plus {
        return Ok(canonical.to_string());
    }
    if let Some(stem) = canonical.strip_suffix("-only") {
        return Ok(format!("{stem}-or-later"));
    }
    if canonical.ends_with("-or-later") {
        return Ok(canonical.to_string());
    }
    Ok(format!("{canonical}+"))
}

fn tokenize(text: &str) -> Result<Vec<String>, SpdxError> {
    let mut out = Vec::new();
    let bytes = text.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        let ch = bytes[i];
        if ch.is_ascii_whitespace() {
            i += 1;
            continue;
        }
        if ch == b'(' || ch == b')' {
            out.push((ch as char).to_string());
            i += 1;
            continue;
        }
        let start = i;
        while i < bytes.len()
            && !bytes[i].is_ascii_whitespace()
            && bytes[i] != b'('
            && bytes[i] != b')'
        {
            i += 1;
        }
        out.push(text[start..i].to_string());
    }
    if out.is_empty() {
        return Err(SpdxError("empty license expression".to_string()));
    }
    Ok(out)
}

fn is_operator(token: &str) -> bool {
    matches!(token, "AND" | "OR" | "WITH")
}

fn unexpected_token_msg(tok: &str) -> String {
    if matches!(tok.to_ascii_lowercase().as_str(), "and" | "or" | "with") {
        format!(
            "'{}': write the operator in uppercase ({})",
            visible_name(tok),
            tok.to_ascii_uppercase()
        )
    } else {
        format!(
            "unexpected '{}' after a complete expression (join terms with AND or OR)",
            visible_name(tok)
        )
    }
}

struct SpdxParser {
    tokens: Vec<String>,
    pos: usize,
    depth: usize,
}

impl SpdxParser {
    fn new(tokens: Vec<String>) -> Self {
        Self {
            tokens,
            pos: 0,
            depth: 0,
        }
    }

    fn peek(&self) -> Option<&str> {
        self.tokens.get(self.pos).map(String::as_str)
    }

    fn take(&mut self) -> Option<String> {
        if self.pos >= self.tokens.len() {
            None
        } else {
            let tok = self.tokens[self.pos].clone();
            self.pos += 1;
            Some(tok)
        }
    }

    fn parse_disjunction(&mut self) -> Result<SpdxExpr, SpdxError> {
        let mut left = self.parse_conjunction()?;
        while self.peek() == Some("OR") {
            self.take();
            let right = self.parse_conjunction()?;
            left = SpdxExpr::Or(Box::new(left), Box::new(right));
        }
        Ok(left)
    }

    fn parse_conjunction(&mut self) -> Result<SpdxExpr, SpdxError> {
        let mut left = self.parse_operand()?;
        while self.peek() == Some("AND") {
            self.take();
            let right = self.parse_operand()?;
            left = SpdxExpr::And(Box::new(left), Box::new(right));
        }
        Ok(left)
    }

    fn parse_operand(&mut self) -> Result<SpdxExpr, SpdxError> {
        let Some(tok) = self.take() else {
            return Err(SpdxError(
                "expression ends where a license identifier was expected".to_string(),
            ));
        };
        if tok == "(" {
            self.depth += 1;
            if self.depth > MAX_DEPTH {
                return Err(SpdxError(format!(
                    "parentheses nested more than {MAX_DEPTH} deep"
                )));
            }
            let inner = self.parse_disjunction()?;
            let Some(closing) = self.take() else {
                return Err(SpdxError(
                    "unbalanced parenthesis: '(' without ')'".to_string(),
                ));
            };
            if closing != ")" {
                return Err(SpdxError(unexpected_token_msg(&closing)));
            }
            self.depth -= 1;
            if self.peek() == Some("WITH") {
                return Err(SpdxError(
                    "WITH must follow a single license identifier, not a parenthesis".to_string(),
                ));
            }
            return Ok(inner);
        }
        if tok == ")" || is_operator(&tok) {
            return Err(SpdxError(format!(
                "'{}' where a license identifier was expected",
                visible_name(&tok)
            )));
        }
        let lic = normalize_id(&tok)?;
        if self.peek() == Some("WITH") {
            self.take();
            let Some(exc) = self.take() else {
                return Err(SpdxError(
                    "WITH must be followed by an exception identifier".to_string(),
                ));
            };
            if exc == "(" || exc == ")" || is_operator(&exc) {
                return Err(SpdxError(
                    "WITH must be followed by an exception identifier".to_string(),
                ));
            }
            let Some(canon_exc) = lookup_known_exception(&exc) else {
                return Err(SpdxError(format!(
                    "unknown SPDX exception identifier '{}'",
                    visible_name(&exc)
                )));
            };
            return Ok(SpdxExpr::With(lic, canon_exc.to_string()));
        }
        Ok(SpdxExpr::License(lic))
    }
}

/// Parses an SPDX 2.3 license expression into a canonical [`SpdxExpr`] AST (`spdx.py:parse`).
pub fn parse(text: &str) -> Result<SpdxExpr, SpdxError> {
    let tokens = tokenize(text)?;
    let mut parser = SpdxParser::new(tokens);
    let tree = parser.parse_disjunction()?;
    if let Some(tok) = parser.peek() {
        if tok == ")" {
            return Err(SpdxError(
                "unbalanced parenthesis: ')' without '('".to_string(),
            ));
        }
        return Err(SpdxError(unexpected_token_msg(tok)));
    }
    Ok(tree)
}

/// Parses a single SPDX license identifier for an `accepts` list, rejecting compound
/// `AND`/`OR`/`WITH` expressions (`spdx.py:parse_identifier`).
pub fn parse_identifier(text: &str) -> Result<String, SpdxError> {
    let tree = parse(text)?;
    match tree {
        SpdxExpr::License(id) => Ok(id),
        SpdxExpr::With(_, _) | SpdxExpr::And(_, _) | SpdxExpr::Or(_, _) => Err(SpdxError(format!(
            "'{}' is an expression; an accepts list holds single license identifiers",
            visible_name(text)
        ))),
    }
}

/// Evaluates whether every license required by `expr` is in `allowed` (`spdx.py:accepted`).
///
/// Matches by canonical identifier (case-insensitively on normalized IDs).
/// `X WITH E` is accepted when `X` is in `allowed`, since an exception only adds permissions.
#[must_use]
pub fn accepted(expr: &SpdxExpr, allowed: &BTreeSet<String>) -> bool {
    let contains_ci =
        |id: &str| allowed.contains(id) || allowed.iter().any(|a| a.eq_ignore_ascii_case(id));
    match expr {
        SpdxExpr::License(id) | SpdxExpr::With(id, _) => contains_ci(id),
        SpdxExpr::And(l, r) => accepted(l, allowed) && accepted(r, allowed),
        SpdxExpr::Or(l, r) => accepted(l, allowed) || accepted(r, allowed),
    }
}

/// Parses `expression` and checks whether it is satisfied by `accepts`, returning
/// `(accepted, canonical_expression_string)` (`spdx.py:check`).
pub fn check_with_canonical<S: AsRef<str>>(
    expression: &str,
    accepts: &[S],
) -> Result<(bool, String), SpdxError> {
    let mut allowed = BTreeSet::new();
    for item in accepts {
        allowed.insert(parse_identifier(item.as_ref())?);
    }
    let tree = parse(expression)?;
    let shown = tree.to_string();
    Ok((accepted(&tree, &allowed), shown))
}

/// Parses `expression` and every entry of `accepts`, then returns whether `expression` is
/// satisfied by `accepts`.
pub fn check<S: AsRef<str>>(expression: &str, accepts: &[S]) -> Result<bool, SpdxError> {
    Ok(check_with_canonical(expression, accepts)?.0)
}

/// Validates that an SPDX expression contains no `LicenseRef-*` or `DocumentRef-*` identifiers
/// when evaluated in a `public` root (`BF-IMX-ISS-5`).
pub fn reject_public_licenseref(expr: &SpdxExpr) -> Result<(), SpdxError> {
    if let Some(bad) = expr.first_license_ref() {
        return Err(SpdxError(format!(
            "custom SPDX identifier '{}' is not permitted in a public root; use a standard SPDX license identifier",
            visible_name(bad)
        )));
    }
    Ok(())
}

/// Parses and checks `expression` against `accepts` for a root with the given `layer`
/// (`"public"` or `"private"`). In a `"public"` root, any `LicenseRef-*` or `DocumentRef-*`
/// identifier in `accepts` or `expression` is rejected (`BF-IMX-ISS-5`).
pub fn check_for_layer<S: AsRef<str>>(
    expression: &str,
    accepts: &[S],
    layer: &str,
) -> Result<bool, SpdxError> {
    let is_public = layer == "public";
    let mut allowed = BTreeSet::new();
    for item in accepts {
        let id = parse_identifier(item.as_ref())?;
        if is_public && is_licenseref_id(&id) {
            return Err(SpdxError(format!(
                "custom SPDX identifier '{}' is not permitted in a public root accepts list",
                visible_name(item.as_ref())
            )));
        }
        allowed.insert(id);
    }
    let expr = parse(expression)?;
    if is_public {
        reject_public_licenseref(&expr)?;
    }
    Ok(accepted(&expr, &allowed))
}

/// Computes a canonical structural key for an SPDX expression (`resolve.py:license_key`).
#[must_use]
pub fn license_key(expr: &SpdxExpr) -> String {
    expr.canonical_key()
}

/// Result of scanning the top of a source file for an `SPDX-License-Identifier:` header.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SpdxHeader {
    /// 1-based line number where `SPDX-License-Identifier:` was found.
    pub line: usize,
    /// Raw expression text extracted after `SPDX-License-Identifier:`.
    pub raw_expression: String,
    /// Parsed [`SpdxExpr`].
    pub expr: SpdxExpr,
}

/// Scans the first 5 lines of `text` for an `SPDX-License-Identifier:` tag
/// (port of `resolve.py:360-386`).
pub fn scan_spdx_header(text: &str) -> Result<Option<SpdxHeader>, (usize, SpdxError)> {
    let text = text.strip_prefix('\u{FEFF}').unwrap_or(text);
    for (idx, raw_line) in text.lines().take(5).enumerate() {
        let line_no = idx + 1;
        if let Some((_, after)) = raw_line.split_once("SPDX-License-Identifier:") {
            let mut expr_str = after.trim();
            if let Some(stripped) = expr_str.strip_suffix("*/") {
                expr_str = stripped.trim();
            } else if let Some(stripped) = expr_str.strip_suffix("-->") {
                expr_str = stripped.trim();
            }
            expr_str = expr_str.trim_end_matches(['\'', '"', ' ', '\t']);
            let parsed = parse(expr_str).map_err(|e| (line_no, e))?;
            return Ok(Some(SpdxHeader {
                line: line_no,
                raw_expression: expr_str.to_string(),
                expr: parsed,
            }));
        }
    }
    Ok(None)
}

// ---------------------------------------------------------------------------
// Attribution scanner, comparator, and ATTRIBUTION.md generator/checker
// (exact port of `skills/spec-format/scripts/attribution.py`)
// ---------------------------------------------------------------------------

/// Maximum distance after a scanned notice where a hand-added ambiguous evidence line may appear.
pub const EXTRA_REACH: usize = 3;

const SPDX_COPYRIGHT_PREFIX: &str = "SPDX-FileCopyrightText:";

const ABBREVIATIONS: &[&str] = &[
    "Inc.", "Ltd.", "Co.", "Corp.", "L.L.C.", "S.A.", "B.V.", "N.V.", "Pty.", "Jr.", "Sr.",
];

/// Status of copyright attribution for a pinned source file.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum AttributionStatus {
    /// No copyright notice found in the scanned source lines.
    NoneFound,
    /// Copyright lines found, but holder names could not be extracted unambiguously.
    Ambiguous,
    /// Copyright holder names and evidence lines extracted cleanly.
    Recorded,
}

impl AttributionStatus {
    /// String representation (`"none-found"`, `"ambiguous"`, `"recorded"`).
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::NoneFound => "none-found",
            Self::Ambiguous => "ambiguous",
            Self::Recorded => "recorded",
        }
    }
}

impl fmt::Display for AttributionStatus {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// One evidence line from a source file's copyright notices.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttributionEvidence {
    /// 1-based line number in the source file.
    pub line: usize,
    /// Normalized notice text on that line.
    pub text: String,
}

/// Copyright attribution record for a source file.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttributionRecord {
    /// Attribution status (`none-found`, `ambiguous`, `recorded`).
    pub status: AttributionStatus,
    /// Deduplicated copyright holder names (in order of appearance).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub names: Vec<String>,
    /// Evidence lines from the source file.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub evidence: Vec<AttributionEvidence>,
    /// Total line count of the scanned file (`0` when deserialized from a spec record).
    #[serde(default, skip_serializing)]
    pub lines: usize,
}

impl AttributionRecord {
    /// Converts this scan result into a schema-shaped `attribution` JSON object
    /// (`attribution.py:record`: omits empty `names`/`evidence` and omits `lines`).
    #[must_use]
    pub fn to_schema_value(&self) -> Value {
        let mut map = serde_json::Map::new();
        map.insert(
            "status".to_string(),
            Value::String(self.status.as_str().to_string()),
        );
        if !self.names.is_empty() {
            map.insert(
                "names".to_string(),
                Value::Array(
                    self.names
                        .iter()
                        .map(|n| Value::String(n.clone()))
                        .collect(),
                ),
            );
        }
        if !self.evidence.is_empty() {
            map.insert(
                "evidence".to_string(),
                Value::Array(
                    self.evidence
                        .iter()
                        .map(|e| {
                            serde_json::json!({
                                "line": e.line,
                                "text": e.text,
                            })
                        })
                        .collect(),
                ),
            );
        }
        Value::Object(map)
    }
}

struct AttributionRegexes {
    leader: Regex,
    trailer: Regex,
    candidate_copyright_followed: Regex,
    candidate_c_followed: Regex,
    midline_copyright: Regex,
    midline_c_symbol: Regex,
    word: Regex,
    symbol: Regex,
    by: Regex,
    reserved: Regex,
    email: Regex,
    years_only: Regex,
}

fn attr_regexes() -> &'static AttributionRegexes {
    static RE: OnceLock<AttributionRegexes> = OnceLock::new();
    RE.get_or_init(|| AttributionRegexes {
        leader: Regex::new(r"^(?:/\*+!?|\*+|//+[!/]?|#+|;+|--|<!--|%+|@+|!+)\s*").unwrap(),
        trailer: Regex::new(r"\s*(?:\*/|-->)\s*$").unwrap(),
        candidate_copyright_followed: Regex::new(r"^(?i:copyright)\s*(?:\([Cc]\)|©|\d{4})")
            .unwrap(),
        candidate_c_followed: Regex::new(r"^\([Cc]\)\s*(?:\d{4}|(?i:copyright)\b)").unwrap(),
        midline_copyright: Regex::new(r"(?i)\bcopyright\b\s*(?:\(c\)|©|\d{4})").unwrap(),
        midline_c_symbol: Regex::new(r"(?i)(?:\(c\)|©)\s*(?:copyright\b|\d{4})").unwrap(),
        word: Regex::new(r"(?i)^copyright\b\s*").unwrap(),
        symbol: Regex::new(r"^(?:\([Cc]\)|©)\s*").unwrap(),
        by: Regex::new(r"(?i)^by\s+").unwrap(),
        reserved: Regex::new(r"([.,]?)\s*All [Rr]ights [Rr]eserved\.?\s*$").unwrap(),
        email: Regex::new(r"\s*<[^<>@]*@[^<>]*>\s*$").unwrap(),
        years_only: Regex::new(r"^[\d\s,\-–]*(?:present)?[\d\s,\-–]*$").unwrap(),
    })
}

/// Strips one comment leader, trailer, and extra whitespace from a source line
/// (`attribution.py:notice_text`). Only strips UTF-8 BOM when `first == true` (line 1).
#[must_use]
pub fn notice_text_line(line: &str, first: bool) -> String {
    let re = attr_regexes();
    let line = if first {
        line.strip_prefix('\u{FEFF}').unwrap_or(line)
    } else {
        line
    };
    let no_cr = line.replace('\r', "");
    let mut text = no_cr.trim_start();
    if let Some(m) = re.leader.find(text) {
        text = &text[m.end()..];
    }
    let without_trailer = re.trailer.replace(text, "");
    let collapsed: Vec<&str> = without_trailer.split_whitespace().collect();
    collapsed.join(" ")
}

/// Strips one comment leader and trailer from `line` (treating it as line 1 for BOM stripping).
#[must_use]
pub fn notice_text(line: &str) -> String {
    notice_text_line(line, true)
}

fn is_word_char(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

fn is_candidate(text: &str) -> bool {
    let re = attr_regexes();
    if text.starts_with(SPDX_COPYRIGHT_PREFIX) || text.starts_with('©') {
        return true;
    }
    if let Some(rest) = text.strip_prefix("Copyright") {
        if rest.chars().next().is_none_or(|c| !is_word_char(c)) {
            return true;
        }
    }
    re.candidate_copyright_followed.is_match(text) || re.candidate_c_followed.is_match(text)
}

fn is_midline(text: &str) -> bool {
    let re = attr_regexes();
    if re.midline_copyright.is_match(text) {
        return true;
    }
    for m in re.midline_c_symbol.find_iter(text) {
        let before = &text[..m.start()];
        if before.chars().next_back().is_none_or(|c| !is_word_char(c)) {
            return true;
        }
    }
    false
}

/// Matches a leading `YEAR_LIST` (`\d{4}(?:\s*[-–]\s*(?:\d{4}|\d{2}(?!\d)|present)|\s*,\s*(?:\d{4}|present))*`),
/// returning the byte length of the matched year list in `s`, if any.
fn match_year_list_prefix(s: &str) -> Option<usize> {
    let bytes = s.as_bytes();
    if bytes.len() < 4 || !bytes[..4].iter().all(u8::is_ascii_digit) {
        return None;
    }
    let mut end = 4usize;
    loop {
        let rest = &s[end..];
        let ws_len = rest.len() - rest.trim_start().len();
        let after_ws = &rest[ws_len..];
        if let Some(after_dash) = after_ws
            .strip_prefix('-')
            .or_else(|| after_ws.strip_prefix('–'))
        {
            let dash_len = after_ws.len() - after_dash.len();
            let ws2_len = after_dash.len() - after_dash.trim_start().len();
            let target = &after_dash[ws2_len..];
            if let Some(after_pres) = target.strip_prefix("present") {
                let _ = after_pres;
                end += ws_len + dash_len + ws2_len + "present".len();
                continue;
            }
            let digit_count = target.bytes().take_while(u8::is_ascii_digit).count();
            if digit_count == 4 || digit_count == 2 {
                end += ws_len + dash_len + ws2_len + digit_count;
                continue;
            }
            break;
        } else if let Some(after_comma) = after_ws.strip_prefix(',') {
            let ws2_len = after_comma.len() - after_comma.trim_start().len();
            let target = &after_comma[ws2_len..];
            if target.starts_with("present") {
                end += ws_len + 1 + ws2_len + "present".len();
                continue;
            }
            let digit_count = target.bytes().take_while(u8::is_ascii_digit).count();
            if digit_count == 4
                && target[4..]
                    .chars()
                    .next()
                    .is_none_or(|c| !c.is_ascii_digit())
            {
                end += ws_len + 1 + ws2_len + 4;
                continue;
            }
            break;
        } else {
            break;
        }
    }
    Some(end)
}

/// Matches `YEARS = YEAR_LIST + r"\s*,?\s*"` at the start of `text`, returning the end index.
fn match_years_prefix(text: &str) -> Option<usize> {
    let yl_end = match_year_list_prefix(text)?;
    let mut rest = &text[yl_end..];
    let ws1 = rest.len() - rest.trim_start().len();
    rest = &rest[ws1..];
    let comma = if let Some(after_comma) = rest.strip_prefix(',') {
        rest = after_comma;
        1
    } else {
        0
    };
    let ws2 = rest.len() - rest.trim_start().len();
    Some(yl_end + ws1 + comma + ws2)
}

/// Matches `TRAILING_YEARS = r"\s*,?\s*" + YEAR_LIST + r"\.?$"` at the end of `holder`,
/// returning the byte index where the trailing years start.
fn find_trailing_years(holder: &str) -> Option<usize> {
    for (idx, _) in holder.char_indices() {
        let tail = &holder[idx..];
        let ws1 = tail.len() - tail.trim_start().len();
        let after_ws1 = &tail[ws1..];
        let (comma, after_comma) = if let Some(ac) = after_ws1.strip_prefix(',') {
            (1, ac)
        } else {
            (0, after_ws1)
        };
        let ws2 = after_comma.len() - after_comma.trim_start().len();
        let cand = &after_comma[ws2..];
        if let Some(yl_len) = match_year_list_prefix(cand) {
            let rem = &cand[yl_len..];
            if rem.is_empty() || rem == "." {
                return Some(idx);
            }
        }
        let _ = comma;
    }
    None
}

fn extract_holder(mut text: &str) -> Option<String> {
    let re = attr_regexes();
    let spdx = text.starts_with(SPDX_COPYRIGHT_PREFIX);
    if spdx {
        text = text[SPDX_COPYRIGHT_PREFIX.len()..].trim_start();
    }
    let mut marked = false;
    let mut word_first = false;
    if let Some(m) = re.word.find(text) {
        word_first = true;
        text = &text[m.end()..];
    }
    if let Some(m) = re.symbol.find(text) {
        marked = true;
        text = &text[m.end()..];
        if !word_first {
            if let Some(wm) = re.word.find(text) {
                text = &text[wm.end()..];
            }
        }
    }
    let has_years = if let Some(y_end) = match_years_prefix(text) {
        marked = true;
        text = &text[y_end..];
        true
    } else {
        false
    };
    if !spdx && !marked {
        return None;
    }

    let trimmed = text.trim();
    let mut holder = if has_years {
        re.by.replace(trimmed, "").into_owned()
    } else {
        trimmed.to_string()
    };

    if let Some(caps) = re.reserved.captures(&holder) {
        let start = caps.get(0).unwrap().start();
        let dot_grp = caps.get(1).map_or("", |m| m.as_str());
        let mut prefix = holder[..start].to_string();
        let words: Vec<&str> = prefix.split_whitespace().collect();
        if dot_grp == "."
            && words
                .last()
                .is_some_and(|w| ABBREVIATIONS.contains(&format!("{w}.").as_str()))
        {
            prefix.push('.');
        }
        holder = prefix;
    }

    holder = holder.trim().to_string();
    if holder.ends_with(">.") {
        holder.pop();
    }
    holder = re.email.replace(&holder, "").into_owned();
    if let Some(t_start) = find_trailing_years(&holder) {
        holder.truncate(t_start);
    }
    holder = holder.trim_end().to_string();
    if holder.ends_with(',') {
        holder.pop();
    }
    holder = holder.trim().to_string();
    let words: Vec<&str> = holder.split_whitespace().collect();
    if holder.ends_with('.') && !words.last().is_some_and(|w| ABBREVIATIONS.contains(w)) {
        holder.pop();
    }
    holder = holder.trim().to_string();
    if holder.contains('<') || holder.contains('>') || holder.eq_ignore_ascii_case("by") {
        return None;
    }
    if holder.chars().any(char::is_alphabetic) {
        Some(holder)
    } else {
        None
    }
}

/// Scans all lines of `text` and returns its copyright [`AttributionRecord`]
/// (`attribution.py:scan`).
#[must_use]
pub fn scan_attribution(text: &str) -> AttributionRecord {
    let lines: Vec<&str> = text.split('\n').collect();
    // Note: if `text` ends with '\n', `split('\n')` has a trailing empty element, whereas
    // `lines()` in Python/Rust drops the trailing newline empty element.
    let line_slice: Vec<&str> = text.lines().collect();
    let _ = lines;
    scan_attribution_lines(&line_slice)
}

/// Scans an explicit slice of lines and returns its copyright [`AttributionRecord`]
/// (`attribution.py:scan`).
#[must_use]
pub fn scan_attribution_lines<S: AsRef<str>>(lines: &[S]) -> AttributionRecord {
    let mut evidence = Vec::new();
    let mut names: Vec<String> = Vec::new();
    let mut ambiguous = false;

    for (idx, raw_line) in lines.iter().enumerate() {
        let number = idx + 1;
        let text = notice_text_line(raw_line.as_ref(), number == 1);
        let holder = if is_candidate(&text) {
            extract_holder(&text)
        } else if is_midline(&text) {
            None
        } else {
            continue;
        };
        evidence.push(AttributionEvidence { line: number, text });
        match holder {
            None => ambiguous = true,
            Some(h) => {
                if !names.contains(&h) {
                    names.push(h);
                }
            }
        }
    }

    let status = if evidence.is_empty() {
        AttributionStatus::NoneFound
    } else if ambiguous {
        AttributionStatus::Ambiguous
    } else {
        AttributionStatus::Recorded
    };
    AttributionRecord {
        status,
        names,
        evidence,
        lines: lines.len(),
    }
}

/// Extracts an [`AttributionRecord`] from a `resources.repos[].files[]` JSON value
/// (or directly from an `attribution` JSON object).
#[must_use]
pub fn record_from_value(entry: &Value) -> Option<AttributionRecord> {
    let raw = entry
        .get("attribution")
        .and_then(Value::as_object)
        .or_else(|| entry.as_object())?;
    let status = match raw.get("status")?.as_str()? {
        "none-found" => AttributionStatus::NoneFound,
        "ambiguous" => AttributionStatus::Ambiguous,
        "recorded" => AttributionStatus::Recorded,
        _ => return None,
    };
    let names = raw
        .get("names")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(Value::as_str)
                .map(visible_name)
                .collect()
        })
        .unwrap_or_default();
    let evidence = raw
        .get("evidence")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(|item| {
                    let obj = item.as_object()?;
                    let line = obj.get("line")?.as_u64()? as usize;
                    let text = visible_name(obj.get("text")?.as_str()?);
                    Some(AttributionEvidence { line, text })
                })
                .collect()
        })
        .unwrap_or_default();
    Some(AttributionRecord {
        status,
        names,
        evidence,
        lines: 0,
    })
}

/// Checks whether `name` occurs in `text` bounded by non-word characters or string ends
/// (`attribution.py:_occurs`).
#[must_use]
pub fn occurs_word_bounded(name: &str, text: &str) -> bool {
    if name.is_empty() {
        return false;
    }
    for (start, _) in text.match_indices(name) {
        let end = start + name.len();
        let before_ok = text[..start]
            .chars()
            .next_back()
            .is_none_or(|c| !is_word_char(c));
        let after_ok = text[end..].chars().next().is_none_or(|c| !is_word_char(c));
        if before_ok && after_ok {
            return true;
        }
    }
    false
}

fn format_py_str_list(items: &[String]) -> String {
    let quoted: Vec<String> = items.iter().map(|s| format!("'{s}'")).collect();
    format!("[{}]", quoted.join(", "))
}

/// Compares a recorded [`AttributionRecord`] against a scanned [`AttributionRecord`] and the
/// source lines (`attribution.py:compare`), returning all disagreement messages (empty if valid).
#[must_use]
pub fn compare_attribution_all<S: AsRef<str>>(
    recorded: &AttributionRecord,
    scanned: &AttributionRecord,
    lines: &[S],
) -> Vec<String> {
    if recorded.status != scanned.status {
        return vec![format!(
            "attribution status '{}' but the source scan finds '{}'",
            recorded.status, scanned.status
        )];
    }
    match recorded.status {
        AttributionStatus::NoneFound => Vec::new(),
        AttributionStatus::Recorded => {
            let have = &recorded.evidence;
            let want = &scanned.evidence;
            let mut messages = Vec::new();
            let max_len = have.len().max(want.len());
            for i in 0..max_len {
                if i >= want.len() {
                    messages.push(format!(
                        "evidence line {}: recorded '{}', the source scan finds no such notice",
                        have[i].line, have[i].text
                    ));
                } else if i >= have.len() || have[i].line > want[i].line {
                    messages.push(format!("missing evidence line {}", want[i].line));
                } else if have[i].line < want[i].line {
                    messages.push(format!(
                        "evidence line {}: the source scan finds the next notice at line {}",
                        have[i].line, want[i].line
                    ));
                } else if have[i].text != want[i].text {
                    messages.push(format!(
                        "evidence line {}: recorded '{}', source has '{}'",
                        have[i].line, have[i].text, want[i].text
                    ));
                } else {
                    continue;
                }
                break;
            }
            if recorded.names != scanned.names {
                messages.push(format!(
                    "names differ: recorded {}, scan finds {}",
                    format_py_str_list(&recorded.names),
                    format_py_str_list(&scanned.names)
                ));
            }
            messages
        }
        AttributionStatus::Ambiguous => {
            let re = attr_regexes();
            let have = &recorded.evidence;
            let want = &scanned.evidence;
            let mut messages = Vec::new();
            let mut previous = 0usize;
            for item in have {
                if item.line <= previous {
                    messages.push(format!(
                        "evidence line {}: lines must increase, without repeats",
                        item.line
                    ));
                }
                previous = previous.max(item.line);
            }
            for item in want {
                if !have.contains(item) {
                    messages.push(format!("missing evidence line {}", item.line));
                }
            }
            for item in have {
                if want.contains(item) {
                    continue;
                }
                let number = item.line;
                if number == 0 || number > lines.len() {
                    messages.push(format!(
                        "evidence line {} does not exist (the file has {} lines)",
                        number,
                        lines.len()
                    ));
                    continue;
                }
                let actual = notice_text_line(lines[number - 1].as_ref(), number == 1);
                if item.text != actual {
                    messages.push(format!(
                        "evidence line {}: recorded '{}', source has '{}'",
                        number, item.text, actual
                    ));
                } else if !want
                    .iter()
                    .any(|c| c.line < number && number <= c.line + EXTRA_REACH)
                {
                    messages.push(format!(
                        "evidence line {}: not within {} lines after a notice the source scan finds",
                        number, EXTRA_REACH
                    ));
                }
            }
            for name in &scanned.names {
                if !recorded
                    .names
                    .iter()
                    .any(|rec_name| occurs_word_bounded(name, rec_name))
                {
                    messages.push(format!(
                        "names omit '{}', which the source scan recognizes",
                        name
                    ));
                }
            }
            let mut sorted_have = have.clone();
            sorted_have.sort_by_key(|i| i.line);
            let joined: String = sorted_have
                .iter()
                .map(|i| i.text.as_str())
                .collect::<Vec<_>>()
                .join(" ");
            for name in &recorded.names {
                if name.eq_ignore_ascii_case("copyright") || re.years_only.is_match(name) {
                    messages.push(format!("name '{}' is not a holder", name));
                } else if !occurs_word_bounded(name, &joined) {
                    messages.push(format!("name '{}' occurs in no evidence text", name));
                }
            }
            messages
        }
    }
}

/// Compares a recorded [`AttributionRecord`] with the scanned [`AttributionRecord`] when only
/// the two records are given, returning the first disagreement message or `None`.
#[must_use]
pub fn compare_attribution(
    recorded: &AttributionRecord,
    actual: &AttributionRecord,
) -> Option<String> {
    let empty_lines: &[&str] = &[];
    compare_attribution_all(recorded, actual, empty_lines)
        .into_iter()
        .next()
}

/// One-line human-readable summary over the files a fact cites (`attribution.py:summary`).
#[must_use]
pub fn attribution_summary(records: &[Option<AttributionRecord>], always: bool) -> Option<String> {
    if (records.is_empty() || !always) && !records.iter().any(Option::is_some) {
        return None;
    }
    let mut names: Vec<String> = Vec::new();
    for rec in records.iter().flatten() {
        if matches!(
            rec.status,
            AttributionStatus::Recorded | AttributionStatus::Ambiguous
        ) {
            for n in &rec.names {
                if !names.contains(n) {
                    names.push(n.clone());
                }
            }
        }
    }
    let unrecorded = records.iter().filter(|r| r.is_none()).count();
    let no_notice = records
        .iter()
        .flatten()
        .filter(|r| r.status == AttributionStatus::NoneFound)
        .count();
    let ambiguous = records
        .iter()
        .flatten()
        .filter(|r| r.status == AttributionStatus::Ambiguous)
        .count();

    let mut parts = Vec::new();
    if unrecorded > 0 {
        parts.push(format!("{unrecorded} unrecorded"));
    }
    if no_notice > 0 {
        parts.push(format!("{no_notice} no notice found"));
    }
    if ambiguous > 0 {
        parts.push(format!("{ambiguous} ambiguous"));
    }

    let mut pieces = Vec::new();
    if !names.is_empty() {
        pieces.push(names.join("; "));
    }
    if !parts.is_empty() {
        pieces.push(format!("attribution incomplete ({})", parts.join(", ")));
    }
    Some(pieces.join("; "))
}

/// Short table cell text for rendered views (`attribution.py:cell`).
#[must_use]
pub fn attribution_cell(recorded: Option<&AttributionRecord>) -> String {
    let Some(rec) = recorded else {
        return String::new();
    };
    let names = rec.names.join("; ");
    match rec.status {
        AttributionStatus::NoneFound => "no notice found".to_string(),
        AttributionStatus::Ambiguous | AttributionStatus::Recorded => {
            if names.is_empty() {
                rec.status.as_str().to_string()
            } else {
                format!("{}: {names}", rec.status.as_str())
            }
        }
    }
}

/// Generates a deterministic `ATTRIBUTION.md` document from loaded spec JSON values.
#[must_use]
pub fn generate_attribution_md(specs: &[Value]) -> String {
    let mut out = String::from(
        "<!--\nSPDX-FileCopyrightText: 2026 contributors\nSPDX-License-Identifier: Apache-2.0\n-->\n\n# Source Attribution\n\n",
    );
    let mut any_repo = false;

    for spec in specs {
        let spec_id = spec.get("id").and_then(Value::as_str).unwrap_or("unknown");
        let Some(repos) = spec
            .get("resources")
            .and_then(|r| r.get("repos"))
            .and_then(Value::as_array)
        else {
            continue;
        };
        for repo in repos {
            let Some(files) = repo.get("files").and_then(Value::as_array) else {
                continue;
            };
            any_repo = true;
            let repo_name = repo.get("name").and_then(Value::as_str).unwrap_or("repo");
            let url = repo.get("url").and_then(Value::as_str).unwrap_or("");
            let commit = repo
                .get("commit")
                .or_else(|| repo.get("ref"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let license = repo.get("license").and_then(Value::as_str).unwrap_or("");

            out.push_str(&format!(
                "## `{spec_id}` / `{repo_name}` (`{license}`)\n\n- URL: `{url}`\n- Pin: `{commit}`\n\n| File | License source | Attribution |\n| :--- | :--- | :--- |\n"
            ));
            for file in files {
                let path = file.get("path").and_then(Value::as_str).unwrap_or("");
                let license_from = file
                    .get("license_from")
                    .and_then(Value::as_str)
                    .unwrap_or("");
                let rec = record_from_value(file);
                let cell = attribution_cell(rec.as_ref()).replace('|', "\\|");
                out.push_str(&format!(
                    "| `{}` | `{}` | {} |\n",
                    visible_name(path),
                    visible_name(license_from),
                    cell
                ));
            }
            out.push('\n');
        }
    }

    if !any_repo {
        out.push_str("No pinned source repositories with file attributions.\n");
    }
    out
}

/// Checks whether an existing `ATTRIBUTION.md` matches the deterministically generated
/// output for `specs`.
pub fn check_attribution_md(existing_md: &str, specs: &[Value]) -> Result<(), String> {
    let expected = generate_attribution_md(specs);
    if existing_md.trim() == expected.trim() {
        Ok(())
    } else {
        Err("ATTRIBUTION.md is out of date with spec repository attributions".to_string())
    }
}

// ---------------------------------------------------------------------------
// Root marker loading & `license-gate` implementation
// (port of `skills/hardware-investigator/scripts/license_gate.py` + `BF-IMX-ISS-5`)
// ---------------------------------------------------------------------------

/// Primary root marker filename (`board-specs.yaml`).
pub const ROOT_MARKER_FILE: &str = "board-specs.yaml";
/// Alternate root marker filename (`.spec-root.yaml`).
pub const ALT_ROOT_MARKER_FILE: &str = ".spec-root.yaml";

/// Validated root marker configuration for license gating.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SpecRootMarker {
    /// Path to the loaded marker file (`board-specs.yaml` or `.spec-root.yaml`).
    pub marker_path: String,
    /// Root name.
    pub name: String,
    /// Root layer (`"public"` or `"private"`).
    pub layer: String,
    /// Root's own SPDX license expression.
    pub license: String,
    /// Ordered list of accepted single SPDX license identifiers (as written in the marker).
    pub accepts: Vec<String>,
    /// Normalized canonical set of accepted identifiers.
    pub allowed_set: BTreeSet<String>,
}

/// Locates and validates `<root>/board-specs.yaml` (or `<root>/.spec-root.yaml`).
/// Enforces `speccheck.py:read_marker` rules + `BF-IMX-ISS-5`:
/// - `format: 2`, `layer: public | private`, `name`, `license`, `accepts`
/// - Every `accepts` entry must be a single canonical SPDX identifier without duplicates.
/// - In a `public` root, `LicenseRef-*` and `DocumentRef-*` are rejected (`BF-IMX-ISS-5`).
pub fn load_root_marker(root_dir: &Path) -> Result<SpecRootMarker, Vec<Finding>> {
    let primary = root_dir.join(ROOT_MARKER_FILE);
    let alt = root_dir.join(ALT_ROOT_MARKER_FILE);
    let marker = if primary.is_file() {
        primary
    } else if alt.is_file() {
        alt
    } else {
        let root_disp = visible_name(&root_dir.to_string_lossy());
        return Err(vec![Finding::error(
            "MARKER-MISSING",
            &root_disp,
            1,
            1,
            format!("--root {root_disp}: no {ROOT_MARKER_FILE} (not a spec root)"),
        )]);
    };

    let marker_disp = visible_name(&marker.to_string_lossy());
    let loaded = yaml_strict::load_file(&marker);
    if !loaded.ok() {
        return Err(loaded.findings());
    }

    let Some(Value::Object(data)) = loaded.data.as_ref() else {
        return Err(vec![Finding::error(
            "MARKER-SCHEMA",
            &marker_disp,
            1,
            1,
            "root marker must be a YAML mapping",
        )]);
    };

    let mut findings = Vec::new();

    for key in data.keys() {
        if !matches!(
            key.as_str(),
            "format" | "layer" | "name" | "license" | "accepts" | "extension" | "description"
        ) {
            let m = loaded.mark(&[PathSegment::Key(key.clone())], Some(key));
            findings.push(Finding::error(
                "MARKER-SCHEMA",
                &marker_disp,
                m.line,
                m.column,
                format!("unexpected property '{key}' in root marker"),
            ));
        }
    }

    if data.get("format").and_then(Value::as_i64) != Some(2) {
        let m = loaded.mark(&[PathSegment::Key("format".to_string())], None);
        findings.push(Finding::error(
            "MARKER-FORMAT",
            &marker_disp,
            m.line,
            m.column,
            "format must be 2",
        ));
    }

    let layer = match data.get("layer").and_then(Value::as_str) {
        Some(l @ ("public" | "private")) => l.to_string(),
        _ => {
            let m = loaded.mark(&[PathSegment::Key("layer".to_string())], None);
            findings.push(Finding::error(
                "MARKER-LAYER",
                &marker_disp,
                m.line,
                m.column,
                "layer must be 'public' or 'private'",
            ));
            "public".to_string()
        }
    };

    let name = match data.get("name").and_then(Value::as_str) {
        Some(n) if !n.trim().is_empty() && !n.contains('`') => n.to_string(),
        Some(_) => {
            let m = loaded.mark(&[PathSegment::Key("name".to_string())], None);
            findings.push(Finding::error(
                "MARKER-NAME",
                &marker_disp,
                m.line,
                m.column,
                "invalid root name",
            ));
            "(unnamed)".to_string()
        }
        None => {
            findings.push(Finding::error(
                "MARKER-NAME",
                &marker_disp,
                1,
                1,
                "missing required property 'name'",
            ));
            "(unnamed)".to_string()
        }
    };

    let root_license = match data.get("license").and_then(Value::as_str) {
        Some(l) if !l.trim().is_empty() => {
            let m = loaded.mark(&[PathSegment::Key("license".to_string())], None);
            match parse(l) {
                Ok(expr) => {
                    if layer == "public" {
                        if let Err(err) = reject_public_licenseref(&expr) {
                            findings.push(Finding::error(
                                "MARKER-LICENSE-PUBLIC-REF",
                                &marker_disp,
                                m.line,
                                m.column,
                                format!("license: {err}"),
                            ));
                        }
                    }
                }
                Err(err) => {
                    findings.push(Finding::error(
                        "MARKER-LICENSE",
                        &marker_disp,
                        m.line,
                        m.column,
                        format!("license: {err}"),
                    ));
                }
            }
            l.to_string()
        }
        _ => {
            let m = loaded.mark(&[PathSegment::Key("license".to_string())], None);
            findings.push(Finding::error(
                "MARKER-LICENSE",
                &marker_disp,
                m.line,
                m.column,
                "missing required property 'license'",
            ));
            "(none declared)".to_string()
        }
    };

    let mut accepts = Vec::new();
    let mut allowed_set = BTreeSet::new();
    match data.get("accepts") {
        Some(Value::Array(accepts_arr)) => {
            let mut seen: HashMap<String, String> = HashMap::new();
            for (i, item) in accepts_arr.iter().enumerate() {
                let m = loaded.mark(
                    &[
                        PathSegment::Key("accepts".to_string()),
                        PathSegment::Index(i),
                    ],
                    None,
                );
                let Some(s) = item.as_str() else {
                    findings.push(Finding::error(
                        "MARKER-ACCEPTS",
                        &marker_disp,
                        m.line,
                        m.column,
                        "accepts entries must be non-empty strings",
                    ));
                    continue;
                };
                match parse_identifier(s) {
                    Ok(canonical) => {
                        if canonical != s {
                            findings.push(Finding::error(
                                "MARKER-ACCEPTS-NONCANONICAL",
                                &marker_disp,
                                m.line,
                                m.column,
                                format!(
                                    "accepts entry '{s}': write it as '{canonical}', its one spelling"
                                ),
                            ));
                        }
                        if layer == "public" && is_licenseref_id(&canonical) {
                            findings.push(Finding::error(
                                "MARKER-ACCEPTS-PUBLIC-REF",
                                &marker_disp,
                                m.line,
                                m.column,
                                format!(
                                    "accepts entry '{s}': custom SPDX identifier is not permitted in a public root"
                                ),
                            ));
                        }
                        if let Some(prev) = seen.get(&canonical) {
                            findings.push(Finding::error(
                                "MARKER-ACCEPTS-DUPLICATE",
                                &marker_disp,
                                m.line,
                                m.column,
                                format!("accepts lists {canonical} twice (as '{prev}' and '{s}')"),
                            ));
                        } else {
                            seen.insert(canonical.clone(), s.to_string());
                        }
                        accepts.push(s.to_string());
                        allowed_set.insert(canonical);
                    }
                    Err(err) => {
                        findings.push(Finding::error(
                            "MARKER-ACCEPTS",
                            &marker_disp,
                            m.line,
                            m.column,
                            format!("accepts entry '{s}': {err}"),
                        ));
                    }
                }
            }
        }
        _ => {
            let m = loaded.mark(&[PathSegment::Key("accepts".to_string())], None);
            findings.push(Finding::error(
                "MARKER-ACCEPTS",
                &marker_disp,
                m.line,
                m.column,
                "missing or non-list 'accepts' in root marker",
            ));
        }
    }

    if !findings.is_empty() {
        return Err(findings);
    }

    Ok(SpecRootMarker {
        marker_path: marker.to_string_lossy().into_owned(),
        name,
        layer,
        license: root_license,
        accepts,
        allowed_set,
    })
}

/// Result of checking one license expression in `license-gate`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LicenseGateDecision {
    /// Repository name (`None` when checking direct CLI license expressions).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub repo: Option<String>,
    /// The SPDX license expression checked (canonical form when valid).
    pub license: String,
    /// `true` if accepted by the target root.
    pub accepted: bool,
    /// Human-readable line (`accepted: ...` or `refused: ...`).
    pub message: String,
}

/// Complete result of a `license-gate` run.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LicenseGateReport {
    /// `true` if the marker is valid and all checked expressions were accepted.
    pub ok: bool,
    /// Numeric exit code (`0`, `1`, `2`, or `3`).
    pub exit_code: i32,
    /// Target root path as passed on CLI.
    pub root: String,
    /// Target root name (when known).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub root_name: Option<String>,
    /// Target root layer (`"public"` or `"private"`).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub layer: Option<String>,
    /// Target root's own license.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub root_license: Option<String>,
    /// Target root's `accepts` list.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub accepts: Vec<String>,
    /// Lines formatted for standard output (`root: ...`, `license: ...`, `accepts: ...`, decisions).
    pub stdout_lines: Vec<String>,
    /// Per-license decisions.
    pub decisions: Vec<LicenseGateDecision>,
    /// Marker or facts-file findings.
    pub findings: Vec<Finding>,
    /// Usage/precondition error messages for stderr.
    pub errors: Vec<String>,
}

impl LicenseGateReport {
    /// Returns the structured [`ExitCode`].
    #[must_use]
    pub fn status(&self) -> ExitCode {
        ExitCode::from_i32(self.exit_code).unwrap_or(ExitCode::DomainFailure)
    }
}

fn evaluate_one_license(
    marker: &SpecRootMarker,
    license: &str,
    repo_label: Option<&str>,
) -> LicenseGateDecision {
    let listed = if marker.accepts.is_empty() {
        "none".to_string()
    } else {
        marker.accepts.join(", ")
    };

    let expr = match parse(license) {
        Ok(e) => e,
        Err(err) => {
            return LicenseGateDecision {
                repo: repo_label.map(ToString::to_string),
                license: license.to_string(),
                accepted: false,
                message: format!(
                    "refused: {} (not an SPDX expression: {err}; root {} accepts: {listed})",
                    visible_name(license),
                    visible_name(&marker.name)
                ),
            };
        }
    };

    if marker.layer == "public" {
        if let Err(err) = reject_public_licenseref(&expr) {
            return LicenseGateDecision {
                repo: repo_label.map(ToString::to_string),
                license: license.to_string(),
                accepted: false,
                message: format!(
                    "refused: {} (not permitted in public root {}: {err}; accepts: {listed})",
                    visible_name(license),
                    visible_name(&marker.name)
                ),
            };
        }
    }

    let shown = expr.to_string();
    if accepted(&expr, &marker.allowed_set) {
        LicenseGateDecision {
            repo: repo_label.map(ToString::to_string),
            license: shown.clone(),
            accepted: true,
            message: format!("accepted: {shown}"),
        }
    } else {
        LicenseGateDecision {
            repo: repo_label.map(ToString::to_string),
            license: shown.clone(),
            accepted: false,
            message: format!(
                "refused: {shown} (not accepted by root {}; accepts: {listed})",
                visible_name(&marker.name)
            ),
        }
    }
}

fn marker_exists(root_dir: &Path) -> bool {
    root_dir.join(ROOT_MARKER_FILE).is_file() || root_dir.join(ALT_ROOT_MARKER_FILE).is_file()
}

/// Checks zero or more SPDX license expressions against `<root>/board-specs.yaml` (or `.spec-root.yaml`),
/// matching `license_gate.py`.
#[must_use]
pub fn gate_licenses(root_dir: &Path, licenses: &[String]) -> LicenseGateReport {
    let root_disp = visible_name(&root_dir.to_string_lossy());
    if !marker_exists(root_dir) {
        let msg = format!("error: --root {root_disp}: no {ROOT_MARKER_FILE} (not a spec root)");
        return LicenseGateReport {
            ok: false,
            exit_code: EXIT_USAGE_ERROR,
            root: root_disp,
            root_name: None,
            layer: None,
            root_license: None,
            accepts: Vec::new(),
            stdout_lines: Vec::new(),
            decisions: Vec::new(),
            findings: Vec::new(),
            errors: vec![msg],
        };
    }

    let marker = match load_root_marker(root_dir) {
        Ok(m) => m,
        Err(found) => {
            let mut stdout_lines = vec![
                format!("root: {root_disp} ((unnamed))"),
                "license: (none declared)".to_string(),
            ];
            for f in &found {
                stdout_lines.push(f.to_string());
            }
            stdout_lines.push(
                "refused: invalid spec format root marker; no source may be cited through it"
                    .to_string(),
            );
            return LicenseGateReport {
                ok: false,
                exit_code: EXIT_DOMAIN_FAILURE,
                root: root_disp,
                root_name: None,
                layer: None,
                root_license: None,
                accepts: Vec::new(),
                stdout_lines,
                decisions: Vec::new(),
                findings: found,
                errors: Vec::new(),
            };
        }
    };

    let listed = if marker.accepts.is_empty() {
        "none".to_string()
    } else {
        marker.accepts.join(", ")
    };
    let mut stdout_lines = vec![
        format!("root: {root_disp} ({})", visible_name(&marker.name)),
        format!("license: {}", visible_name(&marker.license)),
        format!("accepts: {listed}"),
    ];

    let mut decisions = Vec::with_capacity(licenses.len());
    let mut all_ok = true;
    for lic in licenses {
        let dec = evaluate_one_license(&marker, lic, None);
        if !dec.accepted {
            all_ok = false;
        }
        stdout_lines.push(dec.message.clone());
        decisions.push(dec);
    }

    let findings = decisions
        .iter()
        .filter(|d| !d.accepted)
        .map(|d| {
            Finding::error(
                "LICENSE-GATE-REFUSED",
                &marker.marker_path,
                1,
                1,
                d.message.clone(),
            )
        })
        .collect();

    LicenseGateReport {
        ok: all_ok,
        exit_code: if all_ok { EXIT_OK } else { EXIT_DOMAIN_FAILURE },
        root: root_disp,
        root_name: Some(marker.name),
        layer: Some(marker.layer),
        root_license: Some(marker.license),
        accepts: marker.accepts,
        stdout_lines,
        decisions,
        findings,
        errors: Vec::new(),
    }
}

/// Checks all `resources.repos[].license` entries in a `.facts.yaml` file against
/// `<root>/board-specs.yaml` (or `.spec-root.yaml`).
#[must_use]
pub fn gate_facts_file(root_dir: &Path, facts_path: &Path) -> LicenseGateReport {
    let root_disp = visible_name(&root_dir.to_string_lossy());
    if !marker_exists(root_dir) {
        let msg = format!("error: --root {root_disp}: no {ROOT_MARKER_FILE} (not a spec root)");
        return LicenseGateReport {
            ok: false,
            exit_code: EXIT_USAGE_ERROR,
            root: root_disp,
            root_name: None,
            layer: None,
            root_license: None,
            accepts: Vec::new(),
            stdout_lines: Vec::new(),
            decisions: Vec::new(),
            findings: Vec::new(),
            errors: vec![msg],
        };
    }

    let marker = match load_root_marker(root_dir) {
        Ok(m) => m,
        Err(found) => {
            let mut stdout_lines = Vec::new();
            for f in &found {
                stdout_lines.push(f.to_string());
            }
            stdout_lines.push(
                "refused: invalid spec format root marker; no source may be cited through it"
                    .to_string(),
            );
            return LicenseGateReport {
                ok: false,
                exit_code: EXIT_DOMAIN_FAILURE,
                root: root_disp,
                root_name: None,
                layer: None,
                root_license: None,
                accepts: Vec::new(),
                stdout_lines,
                decisions: Vec::new(),
                findings: found,
                errors: Vec::new(),
            };
        }
    };

    let path_disp = visible_name(&facts_path.to_string_lossy());
    let loaded = yaml_strict::load_file(facts_path);
    if !loaded.ok() {
        let found = loaded.findings();
        let stdout_lines = found.iter().map(ToString::to_string).collect();
        return LicenseGateReport {
            ok: false,
            exit_code: EXIT_DOMAIN_FAILURE,
            root: root_disp,
            root_name: Some(marker.name),
            layer: Some(marker.layer),
            root_license: Some(marker.license),
            accepts: marker.accepts,
            stdout_lines,
            decisions: Vec::new(),
            findings: found,
            errors: Vec::new(),
        };
    }

    let Some(Value::Object(ref data)) = loaded.data else {
        let f = Finding::error(
            "FACTS-SCHEMA",
            &path_disp,
            1,
            1,
            "facts file must be a YAML mapping",
        );
        return LicenseGateReport {
            ok: false,
            exit_code: EXIT_DOMAIN_FAILURE,
            root: root_disp,
            root_name: Some(marker.name),
            layer: Some(marker.layer),
            root_license: Some(marker.license),
            accepts: marker.accepts,
            stdout_lines: vec![f.to_string()],
            decisions: Vec::new(),
            findings: vec![f],
            errors: Vec::new(),
        };
    };

    let repos_opt = data
        .get("resources")
        .and_then(Value::as_object)
        .and_then(|r| r.get("repos"))
        .and_then(Value::as_array);

    let mut decisions = Vec::new();
    let mut findings = Vec::new();
    let mut stdout_lines = Vec::new();
    let mut all_ok = true;

    if let Some(repos) = repos_opt {
        for (idx, repo) in repos.iter().enumerate() {
            let m = loaded.mark(
                &[
                    PathSegment::Key("resources".to_string()),
                    PathSegment::Key("repos".to_string()),
                    PathSegment::Index(idx),
                ],
                None,
            );
            let Some(repo_obj) = repo.as_object() else {
                let f = Finding::error(
                    "FACTS-REPO",
                    &path_disp,
                    m.line,
                    m.column,
                    format!("resources.repos[{idx}] must be a mapping"),
                );
                stdout_lines.push(f.to_string());
                findings.push(f);
                all_ok = false;
                continue;
            };
            let name = repo_obj
                .get("name")
                .and_then(Value::as_str)
                .filter(|s| !s.trim().is_empty());
            let license = repo_obj
                .get("license")
                .and_then(Value::as_str)
                .filter(|s| !s.trim().is_empty());
            let (Some(name_str), Some(lic_str)) = (name, license) else {
                let f = Finding::error(
                    "FACTS-REPO-LICENSE",
                    &path_disp,
                    m.line,
                    m.column,
                    "repository entry is missing a string name or license",
                );
                stdout_lines.push(f.to_string());
                findings.push(f);
                all_ok = false;
                continue;
            };
            let dec = evaluate_one_license(&marker, lic_str, Some(name_str));
            if !dec.accepted {
                all_ok = false;
                let f = Finding::error(
                    "FACTS-LICENSE-REFUSED",
                    &path_disp,
                    m.line,
                    m.column,
                    dec.message.clone(),
                );
                findings.push(f);
            }
            stdout_lines.push(dec.message.clone());
            decisions.push(dec);
        }
    }

    LicenseGateReport {
        ok: all_ok,
        exit_code: if all_ok { EXIT_OK } else { EXIT_DOMAIN_FAILURE },
        root: root_disp,
        root_name: Some(marker.name),
        layer: Some(marker.layer),
        root_license: Some(marker.license),
        accepts: marker.accepts,
        stdout_lines,
        decisions,
        findings,
        errors: Vec::new(),
    }
}
