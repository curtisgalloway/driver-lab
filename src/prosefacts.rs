// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Hardware-fact-in-prose detector (port of `skills/spec-format/scripts/prosefacts.py`
//! and `utilities/check-no-hardware-facts.py`).
//!
//! Scans prose for hex literals of two or more digits (`0x7e20`, `0xFE201000`) and
//! uppercase underscore-separated register-style names (`UART_CTRL`, `GICD_CTLR`,
//! `GICD_ITARGETSRn`) outside `${SHELL_VAR}` expansions on lines without `hw-fact-ok:`.

use crate::diagnostic::{
    DiagnosticEnvelope, Finding, Level, EXIT_DOMAIN_FAILURE, EXIT_OK, EXIT_USAGE_ERROR,
};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

/// Line opt-out marker (`hw-fact-ok:`).
pub const OPT_OUT: &str = "hw-fact-ok:";

/// Directories skipped during recursive directory traversal.
pub const SKIP_DIRS: &[&str] = &[
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "target",
];

static HEX_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?-u)\b0[xX][0-9A-Fa-f]{2,}(?:_[0-9A-Fa-f]+)*\b").expect("valid HEX_RE")
});

static REG_CORE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+[nx]?").expect("valid REG_CORE_RE"));

static SHELL_VAR_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}").expect("valid SHELL_VAR_RE"));

static FRONTMATTER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?s)\A---\n(.*?)\n---\n").expect("valid FRONTMATTER_RE"));

/// Classification of a prose hardware fact finding.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProseFactKind {
    /// Hex literal token (`0x...`).
    HexLiteral,
    /// Register-style ALL_CAPS token (`GICD_CTLR`, `UART0_CR`, etc.).
    RegisterName,
}

impl ProseFactKind {
    /// Stable diagnostic code (`PROSE-HEX-LITERAL` or `PROSE-REGISTER-NAME`).
    #[must_use]
    pub const fn code(self) -> &'static str {
        match self {
            Self::HexLiteral => "PROSE-HEX-LITERAL",
            Self::RegisterName => "PROSE-REGISTER-NAME",
        }
    }
}

/// One hardware-fact-in-prose match produced by [`scan_text`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProseFactMatch {
    /// 1-based line number.
    pub line: usize,
    /// 1-based character column number.
    pub column: usize,
    /// Match classification (`hex_literal` or `register_name`).
    pub kind: ProseFactKind,
    /// Raw matched token string.
    pub token: String,
    /// Short description (`hex literal '0x...'` or `register-style name '...'`).
    pub what: String,
    /// Full diagnostic message (matching `prosefacts.py::message`).
    pub message: String,
}

impl ProseFactMatch {
    /// Converts this match into a [`Finding`] for `file`.
    #[must_use]
    pub fn to_finding(&self, file: impl Into<String>) -> Finding {
        Finding::new(
            Level::Error,
            self.kind.code(),
            file,
            self.line,
            self.column,
            &self.message,
        )
    }
}

/// Formats the full diagnostic message for a `what` description (`hex literal '...'`
/// or `register-style name '...'`), matching `prosefacts.py::message`.
#[must_use]
pub fn message(what: &str) -> String {
    format!(
        "{what} in prose no checker reads: put the fact in a spec and point at it, or mark an intentional example with `{OPT_OUT} <reason>` on the line"
    )
}

/// Alias for [`message`].
#[must_use]
pub fn format_message(what: &str) -> String {
    message(what)
}

/// Converts a byte index within `line` to a 1-based character column.
fn byte_idx_to_char_col(line: &str, byte_idx: usize) -> usize {
    line[..byte_idx].chars().count() + 1
}

fn blank_shell_vars(line: &str) -> String {
    let mut out = line.as_bytes().to_vec();
    for m in SHELL_VAR_RE.find_iter(line) {
        for b in &mut out[m.start()..m.end()] {
            *b = b' ';
        }
    }
    String::from_utf8(out).unwrap_or_else(|_| line.to_string())
}

fn has_valid_register_boundaries(blanked: &str, start: usize, end: usize) -> bool {
    let bytes = blanked.as_bytes();
    if start > 0 {
        let prev = bytes[start - 1];
        if prev.is_ascii_alphanumeric() || prev == b'_' || prev == b'$' || prev == b'-' {
            return false;
        }
    }
    if end < bytes.len() {
        let next = bytes[end];
        if next.is_ascii_alphanumeric() || next == b'_' || next == b'-' {
            return false;
        }
    }
    true
}

/// Scans `text` line-by-line for unreferenced hex literals and register-style tokens,
/// sorted by `(line, column, what)` to match `prosefacts.py::findings`.
#[must_use]
pub fn scan_text(text: &str) -> Vec<ProseFactMatch> {
    let mut out = Vec::new();
    for (idx, line) in text.split('\n').enumerate() {
        let lineno = idx + 1;
        if line.contains(OPT_OUT) {
            continue;
        }
        for m in HEX_RE.find_iter(line) {
            let token = m.as_str().to_string();
            let what = format!("hex literal '{token}'");
            let msg = message(&what);
            out.push(ProseFactMatch {
                line: lineno,
                column: byte_idx_to_char_col(line, m.start()),
                kind: ProseFactKind::HexLiteral,
                token,
                what,
                message: msg,
            });
        }
        let blanked = blank_shell_vars(line);
        for m in REG_CORE_RE.find_iter(&blanked) {
            if !has_valid_register_boundaries(&blanked, m.start(), m.end()) {
                continue;
            }
            let token = m.as_str().to_string();
            let what = format!("register-style name '{token}'");
            let msg = message(&what);
            out.push(ProseFactMatch {
                line: lineno,
                column: byte_idx_to_char_col(line, m.start()),
                kind: ProseFactKind::RegisterName,
                token,
                what,
                message: msg,
            });
        }
    }
    out.sort_by(|a, b| (a.line, a.column, &a.what).cmp(&(b.line, b.column, &b.what)));
    out
}

/// Returns `(1-based line, 1-based column, what)` tuples matching `prosefacts.py::findings`.
#[must_use]
pub fn findings(text: &str) -> Vec<(usize, usize, String)> {
    scan_text(text)
        .into_iter()
        .map(|m| (m.line, m.column, m.what))
        .collect()
}

/// Returns `true` if `path` (with `text` contents) is an agent definition (`agents/*.md`)
/// or a board/domain stub skill (`SKILL.md` with `stub over` in YAML frontmatter).
#[must_use]
pub fn in_default_scope(path: &Path, text: &str) -> bool {
    if path.extension().and_then(|e| e.to_str()) == Some("md")
        && path
            .parent()
            .and_then(|p| p.file_name())
            .and_then(|n| n.to_str())
            == Some("agents")
    {
        return true;
    }
    if path.file_name().and_then(|n| n.to_str()) == Some("SKILL.md") {
        if let Some(caps) = FRONTMATTER_RE.captures(text) {
            return caps[1].contains("stub over");
        }
    }
    false
}

/// Scans a single file on disk and returns structured [`Finding`]s.
#[must_use]
pub fn scan_file(path: &Path, display_path: &str) -> Vec<Finding> {
    match fs::read_to_string(path) {
        Ok(text) => scan_text(&text)
            .into_iter()
            .map(|m| m.to_finding(display_path))
            .collect(),
        Err(exc) => vec![Finding::new(
            Level::Error,
            "PROSE-IO",
            display_path,
            1,
            1,
            format!("cannot read UTF-8 text ({exc})"),
        )],
    }
}

fn is_skipped_dir(path: &Path) -> bool {
    path.components().any(|comp| {
        comp.as_os_str()
            .to_str()
            .is_some_and(|name| SKIP_DIRS.contains(&name))
    })
}

fn walk_md_files(dir: &Path, root_dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(dir) else {
        return;
    };
    let mut children: Vec<PathBuf> = entries.filter_map(|e| e.ok().map(|e| e.path())).collect();
    children.sort();
    for child in children {
        let rel = child.strip_prefix(root_dir).unwrap_or(&child);
        if is_skipped_dir(rel) {
            continue;
        }
        if child.is_dir() {
            walk_md_files(&child, root_dir, out);
        } else if child.is_file() {
            out.push(child);
        }
    }
}

/// Formats `path` relative to `repo_root` when `path` is inside `repo_root`, or as-is otherwise.
#[must_use]
pub fn display_rel_path(path: &Path, repo_root: &Path) -> String {
    if let Ok(rel) = path.strip_prefix(repo_root) {
        if !rel.as_os_str().is_empty() {
            return rel.to_string_lossy().into_owned();
        }
    }
    path.to_string_lossy().into_owned()
}

/// Runs `prose-facts` over `paths` (or default `agents/*.md` and stub `skills/*/SKILL.md` under
/// `repo_root` when `paths` is empty) and returns all findings.
#[must_use]
pub fn run_prose_facts(repo_root: &Path, paths: &[PathBuf]) -> Vec<Finding> {
    let mut out = Vec::new();
    if paths.is_empty() {
        let mut candidates = Vec::new();
        for dir_name in ["agents", "skills"] {
            let base = repo_root.join(dir_name);
            if base.is_dir() {
                walk_md_files(&base, &base, &mut candidates);
            }
        }
        candidates.sort();
        for file in candidates {
            let Ok(text) = fs::read_to_string(&file) else {
                continue;
            };
            if !in_default_scope(&file, &text) {
                continue;
            }
            let rel = display_rel_path(&file, repo_root);
            out.extend(scan_text(&text).into_iter().map(|m| m.to_finding(&rel)));
        }
        return out;
    }

    for p in paths {
        if !p.exists() {
            let rel = display_rel_path(p, repo_root);
            out.push(Finding::new(
                Level::Error,
                "PROSE-MISSING-PATH",
                rel,
                1,
                1,
                "path does not exist",
            ));
        } else if p.is_dir() {
            let mut sub = Vec::new();
            walk_md_files(p, p, &mut sub);
            for f in sub {
                if matches!(f.extension().and_then(|e| e.to_str()), Some("md" | "txt")) {
                    let rel = display_rel_path(&f, repo_root);
                    out.extend(scan_file(&f, &rel));
                }
            }
        } else {
            let rel = display_rel_path(p, repo_root);
            out.extend(scan_file(p, &rel));
        }
    }
    out
}

/// Executes the `driver-lab prose-facts [<paths...>]` CLI subcommand.
pub fn run_prose_facts_cmd(
    paths: &[PathBuf],
    json_mode: bool,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let repo_root = Path::new(".");
    for p in paths {
        if !p.exists() {
            let msg = format!("cannot read {}: No such file or directory", p.display());
            if json_mode {
                let env = DiagnosticEnvelope::usage_error("PROSE-IO", &msg);
                let _ = writeln!(stdout, "{}", env.to_json_string());
            } else {
                let _ = writeln!(stderr, "cannot start: {msg}");
            }
            return EXIT_USAGE_ERROR;
        }
    }

    let mut checked = 0usize;
    let mut findings_list: Vec<Finding> = Vec::new();

    if paths.is_empty() {
        let mut candidates = Vec::new();
        for dir_name in ["agents", "skills"] {
            let base = repo_root.join(dir_name);
            if base.is_dir() {
                walk_md_files(&base, &base, &mut candidates);
            }
        }
        candidates.sort();
        for file in candidates {
            let Ok(text) = fs::read_to_string(&file) else {
                continue;
            };
            if !in_default_scope(&file, &text) {
                continue;
            }
            checked += 1;
            let disp = display_rel_path(&file, repo_root);
            findings_list.extend(scan_text(&text).into_iter().map(|m| m.to_finding(&disp)));
        }
    } else {
        for p in paths {
            if p.is_dir() {
                let mut sub = Vec::new();
                walk_md_files(p, p, &mut sub);
                for f in sub {
                    if matches!(f.extension().and_then(|e| e.to_str()), Some("md" | "txt")) {
                        checked += 1;
                        let disp = p
                            .parent()
                            .map(|_| f.to_string_lossy().into_owned())
                            .unwrap_or_else(|| f.to_string_lossy().into_owned());
                        findings_list.extend(scan_file(&f, &disp));
                    }
                }
            } else {
                checked += 1;
                let disp = p.to_string_lossy().into_owned();
                findings_list.extend(scan_file(p, &disp));
            }
        }
    }

    let ok = findings_list.is_empty();
    let code = if ok { EXIT_OK } else { EXIT_DOMAIN_FAILURE };

    if json_mode {
        let env =
            DiagnosticEnvelope::from_findings(findings_list).with_field("checked", json!(checked));
        let _ = writeln!(stdout, "{}", env.to_json_string());
    } else if ok {
        let _ = writeln!(
            stdout,
            "OK: {checked} agent and stub file(s), no hardware facts in prose"
        );
    } else {
        for f in &findings_list {
            let _ = writeln!(stdout, "{}", f.format_without_level());
        }
        let _ = writeln!(
            stderr,
            "\n{} likely hardware fact(s) in agent or stub prose.",
            findings_list.len()
        );
    }

    code
}
