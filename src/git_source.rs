// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Git object plumbing, repository checkout binding, `fetch --cache`, and `pinned-file-adapter`
//! (`RT-6`, `ENV-1`, `ENV-6`, `BF-GW-26`).
//!
//! Enforces:
//! - Hardened `git` invocations over [`crate::sandbox::run_bounded`] (`Stdio::piped()`), zero
//!   tempfiles (`ENV-1`).
//! - Immediate refusal (`exit 3`, code `"RESOLVE-PARTIAL-CLONE"`) when a bound `--repo` checkout
//!   has `extensions.partialClone` or `remote.*.promisor` configured (`ENV-1`).
//! - Lazy scratch directory allocation via [`crate::sandbox::ScratchResolver`] only when an
//!   unbound repository must be fetched; zero scratch allocations when all cited repositories are
//!   bound via `--repo <name>=<path>` (`ENV-1`).
//! - Non-fatal warning (`Level::Warning`, code `"RESOLVE-UNUSED-REPO"`) when a `--repo <name>=<path>`
//!   mapping is not declared in the target spec's `resources.repos` (`BF-GW-26`).
//! - Inlined `check_blob` SHA-256 verification and `pinned-file-adapter` source registry inspection
//!   and atomic update.
//! - Auditable local cache population via `hwspecs fetch --cache <dir>` (`ENV-6`).

use crate::diagnostic::{
    bad_file_name, is_yaml_refused_char, visible_name, ExitCode, Finding, EXIT_DOMAIN_FAILURE,
    EXIT_OK, EXIT_SANDBOX_ERROR, EXIT_USAGE_ERROR,
};
use crate::sandbox::{
    run_bounded, AtomicFileWriter, PipeLimits, SandboxError, ScratchResolver, DEFAULT_STDERR_LIMIT,
    DEFAULT_STDOUT_LIMIT,
};
use crate::yaml_strict;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fmt;
use std::fs;
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;

/// Default per-command timeout in seconds (`resolve.py:TIMEOUT`).
pub const DEFAULT_TIMEOUT_SECS: u64 = 60;
/// Default per-blob / per-document text byte limit in MiB (`resolve.py:LIMIT_MB`).
pub const DEFAULT_LIMIT_MB: usize = 50;
/// Maximum cumulative bytes read across all `git cat-file blob` calls (`resolve.py:TOTAL_BLOB_LIMIT`).
pub const TOTAL_BLOB_LIMIT: usize = 64 * 1024 * 1024;

/// Hardened git configuration flags prepended to every `git` invocation (`resolve.py:SAFE`).
pub const SAFE_GIT_ARGS: &[&str] = &[
    "-c",
    "protocol.allow=never",
    "-c",
    "protocol.https.allow=always",
    "-c",
    "http.followRedirects=false",
    "-c",
    "core.hooksPath=/dev/null",
];

/// CLI usage error (`exit 2`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UsageError(pub String);

impl fmt::Display for UsageError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for UsageError {}

/// Environment, sandbox, or precondition error (`exit 3`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PreconditionError {
    /// Stable diagnostic code.
    pub code: String,
    /// Human-readable diagnostic message.
    pub message: String,
}

impl PreconditionError {
    /// Creates a new [`PreconditionError`].
    #[must_use]
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
        }
    }
}

impl fmt::Display for PreconditionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for PreconditionError {}

impl From<SandboxError> for PreconditionError {
    fn from(err: SandboxError) -> Self {
        Self::new(err.code(), err.to_string())
    }
}

/// Anchor- or repository-level operational failure during git/document inspection.
/// When `skip` is `true`, the failure is due to a size or time limit and counts as a skipped
/// anchor rather than a hard domain error (`resolve.py:OperationalError`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OperationalError {
    /// Diagnostic message.
    pub message: String,
    /// Whether this operational failure should be counted as a skip (size/time limit).
    pub skip: bool,
}

impl OperationalError {
    /// Creates a non-skipped operational failure (`exit 1` finding).
    #[must_use]
    pub fn fail(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            skip: false,
        }
    }

    /// Creates a skipped operational failure (size/time limit exceeded).
    #[must_use]
    pub fn skipped(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            skip: true,
        }
    }
}

impl fmt::Display for OperationalError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for OperationalError {}

/// Combined error returned when opening a repository or resolving a checkout.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GitError {
    /// Precondition / sandbox failure (`exit 3`).
    Precondition(PreconditionError),
    /// Operational failure (`exit 1` or skipped).
    Operational(OperationalError),
}

impl From<PreconditionError> for GitError {
    fn from(e: PreconditionError) -> Self {
        Self::Precondition(e)
    }
}

impl From<SandboxError> for GitError {
    fn from(e: SandboxError) -> Self {
        Self::Precondition(PreconditionError::from(e))
    }
}

impl From<OperationalError> for GitError {
    fn from(e: OperationalError) -> Self {
        Self::Operational(e)
    }
}

impl fmt::Display for GitError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Precondition(p) => write!(f, "{p}"),
            Self::Operational(o) => write!(f, "{o}"),
        }
    }
}

impl std::error::Error for GitError {}

/// Regex matching a full 40-char (SHA-1) or 64-char (SHA-256) lowercase hex commit ID.
#[must_use]
pub fn commit_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$").expect("valid regex"))
}

/// Returns `true` if `s` is a valid 40- or 64-character lowercase hex commit hash.
#[must_use]
pub fn is_valid_commit_oid(s: &str) -> bool {
    commit_re().is_match(s)
}

/// Formats a line of source text for terminal-safe display (`resolve.py:display_line`).
/// Expands `\t` to 4 spaces and escapes control, format, line-separator, surrogate, and
/// private-use characters.
#[must_use]
pub fn display_line(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for ch in text.chars() {
        if ch == '\t' {
            out.push_str("    ");
        } else if ch != ' ' && is_yaml_refused_char(ch) {
            let code = ch as u32;
            if code < 0x100 {
                out.push_str(&format!("\\x{code:02x}"));
            } else if code < 0x10000 {
                out.push_str(&format!("\\u{code:04x}"));
            } else {
                out.push_str(&format!("\\U{code:08x}"));
            }
        } else {
            out.push(ch);
        }
    }
    out
}

/// Validates that `path` is a regular file (not a symlink or special file) and has a clean
/// file name (`resolve.py:file_path`).
pub fn check_file_path(path: &Path, flag: &str) -> Result<(), UsageError> {
    if bad_file_name(path) {
        return Err(UsageError(format!(
            "{flag} {}: invalid file name characters",
            path.display()
        )));
    }
    let Ok(meta) = fs::symlink_metadata(path) else {
        return Err(UsageError(format!(
            "{flag} {}: not a regular file",
            path.display()
        )));
    };
    if meta.file_type().is_symlink() || !meta.file_type().is_file() {
        return Err(UsageError(format!(
            "{flag} {}: not a regular file",
            path.display()
        )));
    }
    Ok(())
}

/// Validates that `path` is a directory (not a symlink) (`resolve.py:dir_path`).
pub fn check_dir_path(path: &Path, flag: &str) -> Result<(), UsageError> {
    let Ok(meta) = fs::symlink_metadata(path) else {
        return Err(UsageError(format!(
            "{flag} {}: not a directory",
            path.display()
        )));
    };
    if meta.file_type().is_symlink() || !meta.file_type().is_dir() {
        return Err(UsageError(format!(
            "{flag} {}: not a directory",
            path.display()
        )));
    }
    Ok(())
}

/// Returns `true` if `path` or any component between `base` and `path` (or `base` itself)
/// is a symbolic link (`resolve.py:is_or_through_symlink`).
#[must_use]
pub fn is_or_through_symlink(base: &Path, path: &Path) -> bool {
    let is_link = |p: &Path| {
        fs::symlink_metadata(p)
            .map(|m| m.file_type().is_symlink())
            .unwrap_or(false)
    };
    if is_link(base) || is_link(path) {
        return true;
    }
    if let Ok(rel) = path.strip_prefix(base) {
        let mut cur = base.to_path_buf();
        for part in rel.components() {
            cur.push(part);
            if is_link(&cur) {
                return true;
            }
        }
    }
    false
}

/// Parses `--repo <name>=<path>` CLI arguments (`resolve.py:repo_map`).
///
/// Validates syntax (`NAME=CHECKOUT`), non-empty name/path without whitespace in `name`,
/// no duplicate repository names, and that each checkout path is an existing non-symlink
/// directory.
pub fn parse_repo_specs(items: &[String]) -> Result<BTreeMap<String, PathBuf>, UsageError> {
    let mut out = BTreeMap::new();
    for item in items {
        let Some((raw_name, raw_path)) = item.split_once('=') else {
            return Err(UsageError(format!(
                "--repo {item:?}: expected NAME=CHECKOUT"
            )));
        };
        let name = raw_name.trim();
        let path_trimmed = raw_path.trim();
        if name.is_empty() || path_trimmed.is_empty() || name.chars().any(char::is_whitespace) {
            return Err(UsageError(format!(
                "--repo {item:?}: expected NAME=CHECKOUT"
            )));
        }
        if out.contains_key(name) {
            return Err(UsageError(format!("--repo {name}: given more than once")));
        }
        let path = PathBuf::from(raw_path);
        check_dir_path(&path, &format!("--repo {name}"))?;
        out.insert(name.to_string(), path);
    }
    Ok(out)
}

/// Executes a hardened `git` command in `cwd` using [`run_bounded`] (`Stdio::piped()`),
/// scrubbing `GIT_*` environment variables and prepending [`SAFE_GIT_ARGS`] (`ENV-1`).
pub fn run_git(args: &[&str], cwd: &Path, stdout_limit: usize) -> Result<Vec<u8>, GitError> {
    run_git_with_lazy(args, cwd, stdout_limit, false)
}

/// Executes a hardened `git` command in `cwd`, allowing promisor lazy-fetch only when
/// `allow_lazy_fetch` is `true` (disposable scratch repositories fetched over HTTPS when
/// `--offline` is false).
pub fn run_git_with_lazy(
    args: &[&str],
    cwd: &Path,
    stdout_limit: usize,
    allow_lazy_fetch: bool,
) -> Result<Vec<u8>, GitError> {
    let mut cmd = Command::new("git");
    cmd.args(SAFE_GIT_ARGS);
    cmd.arg("-C").arg(cwd);
    cmd.args(args);

    for (k, _) in env::vars_os() {
        if k.to_string_lossy().starts_with("GIT_") {
            cmd.env_remove(&k);
        }
    }
    cmd.env("GIT_CONFIG_NOSYSTEM", "1");
    cmd.env("GIT_CONFIG_GLOBAL", "/dev/null");
    cmd.env("GIT_TERMINAL_PROMPT", "0");
    cmd.env("GIT_ALLOW_PROTOCOL", "https");
    cmd.env("GIT_NO_REPLACE_OBJECTS", "1");
    if !allow_lazy_fetch {
        cmd.env("GIT_NO_LAZY_FETCH", "1");
    }

    let limits = PipeLimits {
        stdout_limit,
        stderr_limit: DEFAULT_STDERR_LIMIT,
    };
    let output = match run_bounded(&mut cmd, limits) {
        Ok(out) => out,
        Err(SandboxError::OutputOverflow { limit, .. }) if stdout_limit < DEFAULT_STDOUT_LIMIT => {
            let subcmd = args.first().copied().unwrap_or("git");
            return Err(GitError::Operational(OperationalError::skipped(format!(
                "git {subcmd} output exceeded {limit} bytes"
            ))));
        }
        Err(SandboxError::SubprocessSpawn { program, message }) => {
            return Err(GitError::Precondition(PreconditionError::new(
                "SANDBOX-SUBPROCESS-SPAWN",
                format!("git is required: failed to execute '{program}': {message}"),
            )));
        }
        Err(other) => return Err(GitError::Precondition(PreconditionError::from(other))),
    };

    if output.status != 0 {
        let subcmd = args.first().copied().unwrap_or("git");
        let stderr_str = String::from_utf8_lossy(&output.stderr);
        let detail = stderr_str
            .lines()
            .next()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(ToString::to_string)
            .unwrap_or_else(|| format!("exit {}", output.status));
        return Err(GitError::Operational(OperationalError::fail(format!(
            "git {subcmd}: {detail}"
        ))));
    }

    Ok(output.stdout)
}

/// Inspects a bound local git checkout for `extensions.partialClone` or `remote.*.promisor`
/// before running `cat-file` (`ENV-1`).
///
/// If either is configured, refuses immediately with [`PreconditionError`] (`exit 3`,
/// code `"RESOLVE-PARTIAL-CLONE"`).
pub fn check_not_partial_clone(name: &str, root: &Path) -> Result<(), PreconditionError> {
    let probe_args: &[&[&str]] = &[
        &["config", "--get", "extensions.partialClone"],
        &["config", "--get-regexp", r"^remote\..*\.promisor$"],
    ];
    for args in probe_args {
        let mut cmd = Command::new("git");
        cmd.args(SAFE_GIT_ARGS);
        cmd.arg("-C").arg(root);
        cmd.args(*args);
        for (k, _) in env::vars_os() {
            if k.to_string_lossy().starts_with("GIT_") {
                cmd.env_remove(&k);
            }
        }
        cmd.env("GIT_CONFIG_NOSYSTEM", "1");
        cmd.env("GIT_CONFIG_GLOBAL", "/dev/null");
        cmd.env("GIT_TERMINAL_PROMPT", "0");
        cmd.env("GIT_NO_LAZY_FETCH", "1");

        if let Ok(out) = run_bounded(&mut cmd, PipeLimits::default()) {
            if out.status == 0 {
                let val = String::from_utf8_lossy(&out.stdout);
                let trimmed = val.trim();
                if !trimmed.is_empty() && trimmed != "false" {
                    return Err(PreconditionError::new(
                        "RESOLVE-PARTIAL-CLONE",
                        format!(
                            "--repo {name}={}: repository is a partial clone: bind a full checkout ({trimmed})",
                            root.display()
                        ),
                    ));
                }
            }
        }
    }
    Ok(())
}

/// Validates a relative repository file path (`resolve.py:Repository._check_path`).
pub fn check_repo_relative_path(path: &str) -> Result<Vec<&str>, OperationalError> {
    if path.is_empty()
        || path.starts_with('-')
        || path.chars().any(|c| matches!(c, '\0' | '\r' | '\n'))
    {
        return Err(OperationalError::fail(format!(
            "invalid repository path {path:?}"
        )));
    }
    let parts: Vec<&str> = path.split('/').collect();
    if path.starts_with('/') || parts.iter().any(|p| matches!(*p, "" | "." | ".." | ".git")) {
        return Err(OperationalError::fail(format!(
            "invalid repository path {path:?}"
        )));
    }
    Ok(parts)
}

/// Read-only view of a single immutable commit in a git checkout (`resolve.py:Repository`).
#[derive(Debug)]
pub struct Repository {
    /// Repository checkout root directory.
    pub root: PathBuf,
    /// Full 40- or 64-character lowercase hex commit hash.
    pub commit: String,
    /// Per-blob byte limit.
    pub limit: usize,
    /// Whether this repository is a disposable scratch repository fetched over HTTPS
    /// (`--filter=blob:none`, allowing on-demand promisor blob fetch).
    pub fetched: bool,
    blob_cache: BTreeMap<String, String>,
    tree_cache: BTreeMap<(String, String), (String, String)>,
}

impl Repository {
    /// Creates a new [`Repository`] handle for `root` at `commit`.
    #[must_use]
    pub fn new(root: PathBuf, commit: String, limit: usize) -> Self {
        Self {
            root,
            commit,
            limit,
            fetched: false,
            blob_cache: BTreeMap::new(),
            tree_cache: BTreeMap::new(),
        }
    }

    /// Verifies that `self.commit` exists in `self.root` and resolves to a `"commit"` object.
    pub fn ensure_commit(&self) -> Result<(), GitError> {
        let out = run_git_with_lazy(
            &["cat-file", "-t", "--", &self.commit],
            &self.root,
            self.limit.max(4096),
            self.fetched,
        )?;
        let kind = String::from_utf8_lossy(&out);
        if kind.trim() != "commit" {
            return Err(GitError::Operational(OperationalError::fail(format!(
                "commit {} is not a commit object",
                self.commit
            ))));
        }
        Ok(())
    }

    /// Resolves `path` under `self.commit` to its `(mode, blob_oid)`, rejecting symlinks,
    /// gitlinks/submodules, and non-regular files (`resolve.py:Repository._oid`).
    pub fn resolve_oid(&mut self, path: &str) -> Result<(String, String), GitError> {
        let parts = check_repo_relative_path(path)?;
        let mut tree = self.commit.clone();
        for (idx, part) in parts.iter().enumerate() {
            let key = (tree.clone(), (*part).to_string());
            let (mode, oid) = if let Some(cached) = self.tree_cache.get(&key) {
                cached.clone()
            } else {
                let raw = run_git_with_lazy(
                    &["ls-tree", "-z", "--", &tree, part],
                    &self.root,
                    self.limit.max(65536),
                    self.fetched,
                )?;
                let mut entries: Vec<&[u8]> =
                    raw.split(|&b| b == 0).filter(|s| !s.is_empty()).collect();
                if entries.is_empty() {
                    return Err(GitError::Operational(OperationalError::fail(format!(
                        "{path}: path does not exist at {}",
                        &self.commit[..12.min(self.commit.len())]
                    ))));
                }
                let first = entries.remove(0);
                let Some(tab_pos) = first.iter().position(|&b| b == b'\t') else {
                    return Err(GitError::Operational(OperationalError::fail(format!(
                        "{path}: malformed ls-tree entry"
                    ))));
                };
                let meta_str = String::from_utf8_lossy(&first[..tab_pos]);
                let name_bytes = &first[tab_pos + 1..];
                if !entries.is_empty() || name_bytes != part.as_bytes() {
                    return Err(GitError::Operational(OperationalError::fail(format!(
                        "{path}: path did not resolve to a single tree entry"
                    ))));
                }
                let mut meta_parts = meta_str.split_whitespace();
                let mode = meta_parts.next().unwrap_or_default().to_string();
                let _obj_type = meta_parts.next().unwrap_or_default();
                let oid = meta_parts.next().unwrap_or_default().to_string();
                self.tree_cache.insert(key, (mode.clone(), oid.clone()));
                (mode, oid)
            };

            if idx + 1 < parts.len() {
                if mode != "040000" {
                    return Err(GitError::Operational(OperationalError::fail(format!(
                        "{path}: {} is not a directory",
                        parts[..=idx].join("/")
                    ))));
                }
                tree = oid;
            } else if mode != "100644" && mode != "100755" {
                return Err(GitError::Operational(OperationalError::fail(format!(
                    "{path} is not a regular file (mode {mode})"
                ))));
            } else {
                return Ok((mode, oid));
            }
        }
        Err(GitError::Operational(OperationalError::fail(format!(
            "{path}: empty repository path"
        ))))
    }

    /// Reads and validates a UTF-8 text blob by OID, enforcing `self.limit` and cumulative
    /// `blob_bytes` budget (`resolve.py:Repository._blob`).
    pub fn read_blob(
        &mut self,
        oid: &str,
        path: &str,
        cumulative_blob_bytes: &mut usize,
    ) -> Result<String, GitError> {
        if let Some(cached) = self.blob_cache.get(oid) {
            return Ok(cached.clone());
        }
        let size_out = run_git_with_lazy(
            &["cat-file", "-s", "--", oid],
            &self.root,
            self.limit.max(4096),
            self.fetched,
        )?;
        let size_str = String::from_utf8_lossy(&size_out);
        let size: usize = size_str.trim().parse().map_err(|_| {
            GitError::Operational(OperationalError::fail(format!(
                "{path}: invalid blob size {:?}",
                size_str.trim()
            )))
        })?;
        if size > self.limit {
            return Err(GitError::Operational(OperationalError::skipped(format!(
                "{path} is {size} bytes, limit is {}",
                self.limit
            ))));
        }
        if *cumulative_blob_bytes + size > TOTAL_BLOB_LIMIT {
            return Err(GitError::Operational(OperationalError::skipped(format!(
                "{path} would put read blobs over the {TOTAL_BLOB_LIMIT}-byte cumulative budget"
            ))));
        }
        let raw = run_git_with_lazy(
            &["cat-file", "blob", "--", oid],
            &self.root,
            self.limit,
            self.fetched,
        )?;
        if raw.contains(&0) {
            return Err(GitError::Operational(OperationalError::fail(format!(
                "{path} is binary"
            ))));
        }
        let text = String::from_utf8(raw).map_err(|_| {
            GitError::Operational(OperationalError::fail(format!("{path} is not valid UTF-8")))
        })?;
        *cumulative_blob_bytes += size;
        self.blob_cache.insert(oid.to_string(), text.clone());
        Ok(text)
    }

    /// Reads a single file's text at `self.commit`.
    pub fn read_text(
        &mut self,
        path: &str,
        cumulative_blob_bytes: &mut usize,
    ) -> Result<String, GitError> {
        let (_, oid) = self.resolve_oid(path)?;
        self.read_blob(&oid, path, cumulative_blob_bytes)
    }

    /// Reads multiple files at `self.commit`, deduplicating paths (`resolve.py:Repository.read_files`).
    pub fn read_files<I, S>(
        &mut self,
        paths: I,
        cumulative_blob_bytes: &mut usize,
    ) -> Result<BTreeMap<String, String>, GitError>
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
    {
        let mut unique = BTreeSet::new();
        let mut ordered = Vec::new();
        for p in paths {
            let s = p.as_ref().to_string();
            if unique.insert(s.clone()) {
                ordered.push(s);
            }
        }
        let mut oids = Vec::with_capacity(ordered.len());
        for p in &ordered {
            let (_, oid) = self.resolve_oid(p)?;
            oids.push((p.clone(), oid));
        }
        let mut out = BTreeMap::new();
        for (p, oid) in oids {
            let text = self.read_blob(&oid, &p, cumulative_blob_bytes)?;
            out.insert(p, text);
        }
        Ok(out)
    }
}

/// Checks whether identifier `symbol` appears as a whole C/Rust/DT token (`(?<![A-Za-z0-9_])symbol(?![A-Za-z0-9_])`)
/// within `lines[(span.0 - 200).max(1) - 1 .. span.1]` (`resolve.py:symbol_in`).
#[must_use]
pub fn symbol_in(symbol: &str, lines: &[String], span: (usize, usize)) -> bool {
    if symbol.is_empty() || lines.is_empty() || span.0 == 0 || span.1 == 0 || span.0 > span.1 {
        return false;
    }
    let start_idx = span.0.saturating_sub(200).max(1) - 1;
    let end_idx = span.1.min(lines.len());
    if start_idx >= end_idx {
        return false;
    }
    let is_ident_byte = |b: u8| b.is_ascii_alphanumeric() || b == b'_';
    for line in &lines[start_idx..end_idx] {
        let hay = line.as_bytes();
        let needle = symbol.as_bytes();
        if needle.len() > hay.len() {
            continue;
        }
        let mut pos = 0;
        while let Some(rel) = line[pos..].find(symbol) {
            let idx = pos + rel;
            let before_ok = idx == 0 || !is_ident_byte(hay[idx - 1]);
            let after_idx = idx + needle.len();
            let after_ok = after_idx == hay.len() || !is_ident_byte(hay[after_idx]);
            if before_ok && after_ok {
                return true;
            }
            pos = idx + 1;
        }
    }
    false
}

/// Locates a Devicetree node `node` in `lines` and returns its 1-based `(start_line, end_line)`
/// span (`resolve.py:node_range`).
pub fn node_range(lines: &[String], node: &str) -> Result<(usize, usize), OperationalError> {
    if node.is_empty() {
        return Err(OperationalError::fail("empty node name"));
    }
    let escaped = regex::escape(node);
    let head_re = Regex::new(&format!(
        r"(?:^|[;{{}}])\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*:\s*)*{escaped}\s*\{{"
    ))
    .map_err(|e| OperationalError::fail(format!("invalid node regex: {e}")))?;

    let mut matches: Vec<(usize, usize)> = Vec::new();
    let mut active: Vec<(usize, i32)> = Vec::new();
    let mut in_comment = false;
    let mut in_string = false;

    for (line_idx, raw_line) in lines.iter().enumerate() {
        let lineno = line_idx + 1;
        let bytes = raw_line.as_bytes();
        let mut i = 0;
        let mut code = String::with_capacity(raw_line.len());
        let mut open_columns = Vec::new();

        while i < bytes.len() {
            if in_comment {
                if i + 1 < bytes.len() && bytes[i] == b'*' && bytes[i + 1] == b'/' {
                    in_comment = false;
                    i += 2;
                } else {
                    i += 1;
                }
            } else if in_string {
                if bytes[i] == b'\\' {
                    i += 2;
                } else {
                    if bytes[i] == b'"' {
                        in_string = false;
                    }
                    i += 1;
                }
            } else if i + 1 < bytes.len() && bytes[i] == b'/' && bytes[i + 1] == b'/' {
                break;
            } else if i + 1 < bytes.len() && bytes[i] == b'/' && bytes[i + 1] == b'*' {
                in_comment = true;
                code.push(' ');
                i += 2;
            } else if bytes[i] == b'"' {
                in_string = true;
                code.push(' ');
                i += 1;
            } else {
                let ch = bytes[i] as char;
                if ch == '{' {
                    open_columns.push(code.len());
                }
                code.push(ch);
                i += 1;
            }
        }

        let start_cols: BTreeSet<usize> = head_re.find_iter(&code).map(|m| m.end() - 1).collect();

        for (col, ch) in code.char_indices() {
            if ch == '{' {
                for item in &mut active {
                    item.1 += 1;
                }
                if start_cols.contains(&col) {
                    active.push((lineno, 1));
                }
            } else if ch == '}' {
                let mut next_active = Vec::with_capacity(active.len());
                for (start, depth) in active {
                    if depth == 1 {
                        matches.push((start, lineno));
                    } else if depth > 1 {
                        next_active.push((start, depth - 1));
                    }
                }
                active = next_active;
            }
        }
        let _ = open_columns;
    }

    if !active.is_empty() {
        return Err(OperationalError::fail(format!(
            "unclosed devicetree node '{node}'"
        )));
    }
    if matches.is_empty() {
        return Err(OperationalError::fail(format!(
            "devicetree node '{node}' not found"
        )));
    }
    if matches.len() > 1 {
        return Err(OperationalError::fail(format!(
            "devicetree node '{node}' matched {} blocks",
            matches.len()
        )));
    }
    Ok(matches[0])
}

/// Manages repository checkouts and lazy scratch space across `resolve`, `show`, `inventory`,
/// and `drift` (`resolve.py:Resolver`).
pub struct Resolver<'a> {
    /// Bound `--repo <name>=<path>` checkouts.
    pub repo_map: BTreeMap<String, PathBuf>,
    /// Optional `--docs-dir <dir>` path.
    pub docs_dir: Option<PathBuf>,
    /// Optional `--root <dir>` path.
    pub root: Option<PathBuf>,
    /// Per-command timeout in seconds.
    pub timeout: u64,
    /// Per-blob / per-document text byte limit.
    pub limit: usize,
    /// Whether `--offline` is active (`ENV-1`).
    pub offline: bool,
    /// Lazy scratch resolver (`ENV-1`, `ENV-2`).
    pub scratch: &'a ScratchResolver,
    /// Cumulative blob bytes read in this session.
    pub blob_bytes: usize,
    repos: BTreeMap<(String, String, String), Repository>,
    fetched: BTreeMap<(String, String), PathBuf>,
    fetch_counter: usize,
}

impl<'a> Resolver<'a> {
    /// Constructs a [`Resolver`] from CLI options, validating `--repo`, `--docs-dir`, `--timeout`,
    /// and `--limit-mb` (`resolve.py:Resolver.from_args`).
    pub fn new(
        repo_specs: &[String],
        docs_dir: Option<PathBuf>,
        root: Option<PathBuf>,
        timeout: u64,
        limit_mb: usize,
        offline: bool,
        scratch: &'a ScratchResolver,
    ) -> Result<Self, UsageError> {
        if !(1..=600).contains(&timeout) {
            return Err(UsageError(
                "--timeout must be between 1 and 600 seconds".to_string(),
            ));
        }
        if !(1..=500).contains(&limit_mb) {
            return Err(UsageError(
                "--limit-mb must be between 1 and 500".to_string(),
            ));
        }
        if let Some(ref d) = docs_dir {
            check_dir_path(d, "--docs-dir")?;
        }
        let repo_map = parse_repo_specs(repo_specs)?;
        Ok(Self {
            repo_map,
            docs_dir,
            root,
            timeout,
            limit: limit_mb * 1024 * 1024,
            offline,
            scratch,
            blob_bytes: 0,
            repos: BTreeMap::new(),
            fetched: BTreeMap::new(),
            fetch_counter: 0,
        })
    }

    /// Emits a non-fatal warning (`RESOLVE-UNUSED-REPO`) for each `--repo <name>=<path>` mapping
    /// that does not match any `resources.repos[].name` in the target specs (`BF-GW-26`).
    pub fn check_unused_repos(
        &self,
        declared_repo_names: &BTreeSet<String>,
        default_path: &str,
        findings: &mut Vec<Finding>,
    ) {
        for name in self.repo_map.keys() {
            if !declared_repo_names.contains(name) {
                findings.push(Finding::warning(
                    "RESOLVE-UNUSED-REPO",
                    default_path,
                    1,
                    1,
                    format!(
                        "unused --repo mapping '{name}': no repos entry with this name in the target spec(s)"
                    ),
                ));
            }
        }
    }

    /// Resolves the checkout directory for `(name, url, commit)`:
    /// - If `name` is bound in `self.repo_map`, verifies it is not a partial clone (`ENV-1`, `exit 3`)
    ///   and verifies `rev-parse --show-toplevel` matches `root.canonicalize()`.
    /// - Otherwise, checks `--offline` (`ENV-1`, `exit 3`), lazily allocates a temporary bare repository
    ///   inside `self.scratch`, and fetches `commit` over HTTPS.
    pub fn checkout(&mut self, name: &str, url: &str, commit: &str) -> Result<PathBuf, GitError> {
        if let Some(bound_root) = self.repo_map.get(name).cloned() {
            check_not_partial_clone(name, &bound_root)?;
            let out = run_git(
                &["rev-parse", "--show-toplevel"],
                &bound_root,
                self.limit.max(4096),
            )
            .map_err(|_| {
                GitError::Operational(OperationalError::fail(format!(
                    "--repo {name}: {} is not a Git working tree",
                    bound_root.display()
                )))
            })?;
            let top_str = String::from_utf8_lossy(&out);
            let top_path = PathBuf::from(top_str.trim());
            let top_canon = fs::canonicalize(&top_path).unwrap_or(top_path);
            let root_canon = fs::canonicalize(&bound_root).unwrap_or_else(|_| bound_root.clone());
            if top_canon != root_canon {
                return Err(GitError::Operational(OperationalError::fail(format!(
                    "--repo {name}: {} is not the top level of a Git working tree",
                    bound_root.display()
                ))));
            }
            return Ok(bound_root);
        }

        if !url.starts_with("https://") || url.chars().any(char::is_whitespace) {
            return Err(GitError::Operational(OperationalError::fail(format!(
                "repos entry '{name}' URL must use https:// with no whitespace"
            ))));
        }

        if self.offline {
            return Err(GitError::Precondition(PreconditionError::from(
                SandboxError::OfflineForbidden {
                    operation: format!("git fetch {url} {commit} for unbound repo '{name}'"),
                },
            )));
        }

        let key = (url.to_string(), commit.to_string());
        if let Some(existing) = self.fetched.get(&key) {
            return Ok(existing.clone());
        }

        let scratch_base = self.scratch.ensure_dir()?;
        self.fetch_counter += 1;
        let dest = scratch_base.join(format!("repo-{}", self.fetch_counter));
        fs::create_dir_all(&dest).map_err(|e| SandboxError::Io {
            context: format!("failed to create repo dir {}", dest.display()),
            message: e.to_string(),
        })?;
        if commit.len() == 64 {
            run_git(
                &["init", "-q", "--object-format=sha256"],
                &dest,
                self.limit.max(4096),
            )?;
        } else {
            run_git(&["init", "-q"], &dest, self.limit.max(4096))?;
        }
        run_git(
            &[
                "fetch",
                "--quiet",
                "--no-tags",
                "--depth=1",
                "--filter=blob:none",
                "--",
                url,
                commit,
            ],
            &dest,
            self.limit,
        )?;
        self.fetched.insert(key, dest.clone());
        Ok(dest)
    }

    /// Opens and verifies the commit for `entry` (`name`, `url`, `commit`).
    pub fn open_repo(
        &mut self,
        name: &str,
        url: &str,
        commit: &str,
    ) -> Result<&mut Repository, GitError> {
        if !is_valid_commit_oid(commit) {
            return Err(GitError::Operational(OperationalError::fail(format!(
                "repos entry '{name}' has no full commit id"
            ))));
        }
        let key = (name.to_string(), url.to_string(), commit.to_string());
        if !self.repos.contains_key(&key) {
            let is_fetched = !self.repo_map.contains_key(name);
            let root = self.checkout(name, url, commit)?;
            let mut repo = Repository::new(root, commit.to_string(), self.limit);
            repo.fetched = is_fetched;
            repo.ensure_commit()?;
            self.repos.insert(key.clone(), repo);
        }
        Ok(self.repos.get_mut(&key).expect("just inserted"))
    }
}

// ============================================================================
// Inlined `check_blob` and `pinned-file-adapter` (`RT-6`, `ENV-1`)
// ============================================================================

/// Result of comparing opaque file bytes against an expected SHA-256 hex digest
/// (inlined from `evals/enc28j60/corpus_check.py:check_blob`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BlobCheck {
    /// `"ok"` when `actual == expected`, `"drift"` otherwise.
    pub status: String,
    /// Lowercase 64-char hex SHA-256 of `blob`.
    pub actual: String,
    /// Byte length of `blob`.
    pub bytes: usize,
}

/// Compares opaque `blob` bytes against `expected` SHA-256 hex digest
/// (`corpus_check.py:check_blob`).
#[must_use]
pub fn check_blob(blob: &[u8], expected: &str) -> BlobCheck {
    let actual = hex::encode(Sha256::digest(blob));
    BlobCheck {
        status: if actual == expected {
            "ok".to_string()
        } else {
            "drift".to_string()
        },
        actual,
        bytes: blob.len(),
    }
}

/// Valid `kind` values in a campaign `sources.yaml` registry (`source_registry.py:KINDS`).
pub const SOURCE_REGISTRY_KINDS: &[&str] = &[
    "spec",
    "document",
    "kernel",
    "reference",
    "harness",
    "guest_init",
    "emulator",
    "guest_kernel",
    "guest_image",
    "guest_busybox",
    "candidate",
    "toolchain",
    "model",
    "fixture",
];

fn validate_relative_no_traversal(value: &Value) -> Result<(), String> {
    let Some(s) = value.as_str() else {
        return Err("expected nonempty string".to_string());
    };
    if s.is_empty() {
        return Err("expected nonempty string".to_string());
    }
    if s.starts_with('/') || s.contains('\\') || s.contains(':') {
        return Err("expected a relative path without traversal".to_string());
    }
    for comp in Path::new(s).components() {
        if matches!(
            comp,
            Component::ParentDir | Component::RootDir | Component::Prefix(_)
        ) {
            return Err("expected a relative path without traversal".to_string());
        }
    }
    Ok(())
}

fn validate_sha(value: &Value, nullable: bool) -> Result<(), String> {
    if nullable && value.is_null() {
        return Ok(());
    }
    let Some(s) = value.as_str() else {
        return Err("expected full SHA-256 hex digest".to_string());
    };
    if s.len() != 64 || !s.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')) {
        return Err("expected full SHA-256 hex digest".to_string());
    }
    Ok(())
}

fn validate_iso_date(value: &Value) -> Result<(), String> {
    let Some(s) = value.as_str() else {
        return Err("expected YYYY-MM-DD date string".to_string());
    };
    if s.len() != 10 {
        return Err(format!("invalid ISO date: {s}"));
    }
    let parts: Vec<&str> = s.split('-').collect();
    if parts.len() != 3 || parts[0].len() != 4 || parts[1].len() != 2 || parts[2].len() != 2 {
        return Err(format!("invalid ISO date: {s}"));
    }
    let year: u32 = parts[0]
        .parse()
        .map_err(|_| format!("invalid ISO date: {s}"))?;
    let month: u32 = parts[1]
        .parse()
        .map_err(|_| format!("invalid ISO date: {s}"))?;
    let day: u32 = parts[2]
        .parse()
        .map_err(|_| format!("invalid ISO date: {s}"))?;
    if !(1..=12).contains(&month) || day == 0 {
        return Err(format!("invalid ISO date: {s}"));
    }
    let max_day = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if (year.is_multiple_of(4) && !year.is_multiple_of(100)) || year.is_multiple_of(400) {
                29
            } else {
                28
            }
        }
        _ => unreachable!(),
    };
    if day > max_day {
        return Err(format!("invalid ISO date: {s}"));
    }
    Ok(())
}

fn validate_mapping_keys(
    obj: &Map<String, Value>,
    required: &[&str],
    optional: &[&str],
) -> Result<(), String> {
    for &req in required {
        if !obj.contains_key(req) {
            return Err(format!("missing required field: {req}"));
        }
    }
    for k in obj.keys() {
        if !required.contains(&k.as_str()) && !optional.contains(&k.as_str()) {
            return Err(format!("unknown fields: {k}"));
        }
    }
    Ok(())
}

fn validate_nonempty_str(v: &Value) -> Result<&str, String> {
    let Some(s) = v.as_str() else {
        return Err("expected nonempty string".to_string());
    };
    if s.trim().is_empty() {
        return Err("expected nonempty string".to_string());
    }
    Ok(s)
}

fn validate_string_list(v: &Value, nonempty: bool) -> Result<(), String> {
    let Some(arr) = v.as_array() else {
        return Err("expected list of nonempty strings".to_string());
    };
    if nonempty && arr.is_empty() {
        return Err("expected nonempty list".to_string());
    }
    for item in arr {
        validate_nonempty_str(item)?;
    }
    Ok(())
}

/// Validates shared C8 adapter identity metadata (`source_registry.py:validate_identity`).
pub fn validate_source_identity(
    source: &Map<String, Value>,
    require_hash: bool,
) -> Result<(), String> {
    for field in ["id", "version", "sha256", "status", "checked", "provenance"] {
        if !source.contains_key(field) {
            return Err(format!("missing source field: {field}"));
        }
    }
    for field in ["id", "version", "status"] {
        validate_nonempty_str(source.get(field).expect("checked"))?;
    }
    let status = source
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !matches!(status, "ok" | "blocked" | "unknown") {
        return Err("invalid adapter status".to_string());
    }
    validate_sha(
        source.get("sha256").expect("checked"),
        !(require_hash && status == "ok"),
    )?;
    validate_iso_date(source.get("checked").expect("checked"))?;
    let Some(prov) = source.get("provenance").and_then(Value::as_object) else {
        return Err("provenance must be a mapping".to_string());
    };
    validate_mapping_keys(prov, &["adapter", "version", "version_method"], &[])?;
    for val in prov.values() {
        validate_nonempty_str(val)?;
    }
    Ok(())
}

/// Validates a campaign `sources.yaml` registry (`source_registry.py:validate`).
pub fn validate_source_registry(registry: &Value) -> Result<(), String> {
    let Some(reg_obj) = registry.as_object() else {
        return Err("registry must be a mapping".to_string());
    };
    validate_mapping_keys(
        reg_obj,
        &[
            "version",
            "campaign",
            "sources",
            "citations",
            "premises",
            "contradictions",
        ],
        &[],
    )?;
    if reg_obj.get("version").and_then(Value::as_i64) != Some(1)
        || reg_obj.get("version").is_some_and(Value::is_boolean)
    {
        return Err("unsupported registry version".to_string());
    }
    validate_nonempty_str(reg_obj.get("campaign").expect("checked"))?;
    let Some(sources) = reg_obj.get("sources").and_then(Value::as_array) else {
        return Err("sources must be a list".to_string());
    };
    let mut ids = BTreeSet::new();
    for source_val in sources {
        let Some(source) = source_val.as_object() else {
            return Err("source entry must be a mapping".to_string());
        };
        validate_mapping_keys(
            source,
            &[
                "id",
                "kind",
                "version",
                "sha256",
                "status",
                "checked",
                "provenance",
                "file",
                "expected_sha256",
            ],
            &[
                "pin",
                "commit",
                "revision",
                "changes",
                "bindings",
                "requirement_change",
            ],
        )?;
        let sid = validate_nonempty_str(source.get("id").expect("checked"))?;
        if !ids.insert(sid.to_string()) {
            return Err("duplicate source ID".to_string());
        }
        let kind = validate_nonempty_str(source.get("kind").expect("checked"))?;
        if !SOURCE_REGISTRY_KINDS.contains(&kind) {
            return Err("unknown source kind".to_string());
        }
        validate_sha(source.get("expected_sha256").expect("checked"), false)?;
        validate_source_identity(source, !matches!(kind, "toolchain" | "model" | "fixture"))?;
        let file_val = source.get("file").expect("checked");
        if !file_val.is_null() {
            let Some(file_obj) = file_val.as_object() else {
                return Err("file must be a mapping".to_string());
            };
            validate_mapping_keys(file_obj, &["root", "path"], &[])?;
            let froot = validate_nonempty_str(file_obj.get("root").expect("checked"))?;
            if !matches!(froot, "repository" | "run_store") {
                return Err("unknown file root".to_string());
            }
            validate_relative_no_traversal(file_obj.get("path").expect("checked"))?;
        }
        if let Some(pin) = source.get("pin") {
            validate_nonempty_str(pin)?;
        }
        if let Some(commit) = source.get("commit") {
            let Some(cstr) = commit.as_str() else {
                return Err("invalid commit".to_string());
            };
            if cstr.len() != 40 || !cstr.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')) {
                return Err("invalid commit".to_string());
            }
        }
        if kind == "spec" {
            let rev_ok = source
                .get("revision")
                .filter(|v| !v.is_boolean())
                .and_then(Value::as_i64)
                .is_some_and(|r| r > 0);
            if !rev_ok {
                return Err("spec needs revision".to_string());
            }
        }
        if let Some(rc) = source.get("requirement_change") {
            if !rc.is_boolean() {
                return Err("requirement_change must be boolean".to_string());
            }
        }
        if let Some(bindings) = source.get("bindings") {
            validate_string_list(bindings, true)?;
        }
        if let Some(changes_val) = source.get("changes") {
            let Some(changes) = changes_val.as_array() else {
                return Err("changes must be a list".to_string());
            };
            let mut seen_from = BTreeSet::new();
            for ch_val in changes {
                let Some(ch) = ch_val.as_object() else {
                    return Err("change entry must be a mapping".to_string());
                };
                validate_mapping_keys(
                    ch,
                    &[
                        "from_sha256",
                        "to_sha256",
                        "since",
                        "reviewed",
                        "sections",
                        "checks",
                        "scenarios",
                        "evidence",
                    ],
                    &[],
                )?;
                validate_sha(ch.get("from_sha256").expect("checked"), false)?;
                validate_sha(ch.get("to_sha256").expect("checked"), false)?;
                let from_s = ch
                    .get("from_sha256")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                if !seen_from.insert(from_s.to_string()) {
                    return Err("duplicate change origin".to_string());
                }
                if ch.get("to_sha256") != source.get("sha256") {
                    return Err("change map is not for current hash".to_string());
                }
                validate_nonempty_str(ch.get("since").expect("checked"))?;
                if !ch.get("reviewed").is_some_and(Value::is_boolean) {
                    return Err("reviewed must be boolean".to_string());
                }
                for key in ["sections", "checks", "scenarios"] {
                    let kv = ch.get(key).expect("checked");
                    if !kv.is_null() {
                        validate_string_list(kv, false)?;
                    }
                }
                validate_string_list(ch.get("evidence").expect("checked"), true)?;
            }
        }
    }
    for key in ["citations", "premises"] {
        let Some(m) = reg_obj.get(key).and_then(Value::as_object) else {
            return Err(format!("{key} must be a mapping"));
        };
        if key == "citations" {
            for cit_val in m.values() {
                let Some(cit_obj) = cit_val.as_object() else {
                    return Err("citations must be a mapping".to_string());
                };
                for (source_id, sections) in cit_obj {
                    if !ids.contains(source_id) {
                        return Err("citation source missing".to_string());
                    }
                    validate_string_list(sections, true)?;
                }
            }
        } else {
            for obs in m.values() {
                validate_string_list(obs, true)?;
            }
        }
    }
    let Some(contradictions) = reg_obj.get("contradictions").and_then(Value::as_array) else {
        return Err("contradictions must be a list".to_string());
    };
    for c_val in contradictions {
        let Some(c_obj) = c_val.as_object() else {
            return Err("contradiction must be a mapping".to_string());
        };
        validate_mapping_keys(c_obj, &["observation", "since", "conflict"], &[])?;
        validate_nonempty_str(c_obj.get("observation").expect("checked"))?;
        validate_nonempty_str(c_obj.get("since").expect("checked"))?;
        validate_relative_no_traversal(c_obj.get("conflict").expect("checked"))?;
    }
    Ok(())
}

/// Resolves a file entry inside `base` and verifies it is a regular file that does not escape
/// `base` via symlinks (`pinned_file_adapter.py:resolve_file`).
pub fn resolve_pinned_file(
    entry: &Map<String, Value>,
    root: &Path,
    run_store: Option<&Path>,
) -> Option<PathBuf> {
    let file_obj = entry.get("file")?.as_object()?;
    let file_root = file_obj.get("root")?.as_str()?;
    let rel_path = file_obj.get("path")?.as_str()?;
    validate_relative_no_traversal(&Value::String(rel_path.to_string())).ok()?;
    let base: PathBuf = if file_root == "repository" {
        root.to_path_buf()
    } else if let Some(rs) = run_store {
        rs.to_path_buf()
    } else if let Some(env_rs) = ["HWSPECS_RUNS", "DRIVER_LAB_RUNS"]
        .iter()
        .find_map(|name| env::var_os(name).filter(|v| !v.is_empty()))
    {
        PathBuf::from(env_rs)
    } else {
        return None;
    };
    let base_canon = fs::canonicalize(&base).ok()?;
    let candidate = base.join(rel_path);
    let cand_canon = fs::canonicalize(&candidate).ok()?;
    if !cand_canon.starts_with(&base_canon) {
        return None;
    }
    if !cand_canon.is_file() {
        return None;
    }
    Some(cand_canon)
}

/// Inspects a single source registry entry without parsing its bytes
/// (`pinned_file_adapter.py:inspect`).
pub fn inspect_pinned_source(
    source: &Map<String, Value>,
    root: &Path,
    run_store: Option<&Path>,
    today: &str,
) -> Result<Map<String, Value>, String> {
    let mut result = Map::new();
    let id = source
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let version = source
        .get("version")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let expected = source
        .get("expected_sha256")
        .and_then(Value::as_str)
        .unwrap_or_default();

    let mut prov = Map::new();
    prov.insert("adapter".to_string(), json!("pinned-file"));
    prov.insert("version".to_string(), json!("1"));
    prov.insert("version_method".to_string(), json!("registry-metadata"));

    result.insert("id".to_string(), json!(id));
    result.insert("version".to_string(), json!(version));
    result.insert("checked".to_string(), json!(today));
    result.insert("provenance".to_string(), Value::Object(prov));

    let has_file = source.get("file").is_some_and(|v| !v.is_null());
    if !has_file {
        result.insert("sha256".to_string(), Value::Null);
        result.insert("status".to_string(), json!("unknown"));
        result.insert("matches_pin".to_string(), json!(false));
    } else {
        let resolved = resolve_pinned_file(source, root, run_store);
        let blob_opt = resolved.and_then(|p| fs::read(p).ok());
        match blob_opt {
            None => {
                result.insert("sha256".to_string(), Value::Null);
                result.insert("status".to_string(), json!("blocked"));
                result.insert("matches_pin".to_string(), json!(false));
            }
            Some(bytes) => {
                let checked = check_blob(&bytes, expected);
                result.insert("sha256".to_string(), json!(checked.actual));
                result.insert("status".to_string(), json!("ok"));
                result.insert("matches_pin".to_string(), json!(checked.status == "ok"));
                result.insert("bytes".to_string(), json!(checked.bytes));
            }
        }
    }
    validate_source_identity(&result, true)?;
    Ok(result)
}

/// Applies an inspection result to `registry` in memory, returning `true` if any field changed
/// (`pinned_file_adapter.py:apply_update`).
pub fn apply_pinned_source_update(
    registry: &mut Value,
    result: &Map<String, Value>,
) -> Result<bool, String> {
    let target_id = result.get("id").and_then(Value::as_str).unwrap_or_default();
    let Some(sources) = registry.get_mut("sources").and_then(Value::as_array_mut) else {
        return Err("sources must be a list".to_string());
    };
    let Some(source_val) = sources
        .iter_mut()
        .find(|s| s.get("id").and_then(Value::as_str) == Some(target_id))
    else {
        return Err(format!("source is not registered: {target_id}"));
    };
    let Some(source_obj) = source_val.as_object_mut() else {
        return Err("source entry must be a mapping".to_string());
    };
    let mut changed = false;
    for field in ["sha256", "status", "checked", "provenance"] {
        let new_val = result.get(field).cloned().unwrap_or(Value::Null);
        if source_obj.get(field) != Some(&new_val) {
            source_obj.insert(field.to_string(), new_val);
            changed = true;
        }
    }
    validate_source_registry(registry)?;
    Ok(changed)
}

/// Serializes a JSON/YAML [`Value`] back to clean YAML for `sources.yaml` updates.
fn dump_yaml_value(val: &Value, indent: usize) -> String {
    let pad = "  ".repeat(indent);
    match val {
        Value::Null => "null".to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => crate::index::format_yaml_scalar_str(s, false),
        Value::Array(arr) => {
            if arr.is_empty() {
                "[]".to_string()
            } else {
                let mut out = String::new();
                for item in arr {
                    match item {
                        Value::Object(map) if !map.is_empty() => {
                            let mut iter = map.iter();
                            let (first_k, first_v) = iter.next().expect("non-empty");
                            out.push_str(&format!("\n{pad}- {first_k}: "));
                            out.push_str(&format_map_val(first_v, indent + 1));
                            for (k, v) in iter {
                                out.push_str(&format!("\n{pad}  {k}: "));
                                out.push_str(&format_map_val(v, indent + 1));
                            }
                        }
                        _ => {
                            out.push_str(&format!(
                                "\n{pad}- {}",
                                dump_yaml_value(item, indent + 1)
                            ));
                        }
                    }
                }
                out
            }
        }
        Value::Object(map) => {
            if map.is_empty() {
                "{}".to_string()
            } else {
                let mut out = String::new();
                for (k, v) in map {
                    out.push_str(&format!("\n{pad}{k}: "));
                    out.push_str(&format_map_val(v, indent));
                }
                out
            }
        }
    }
}

fn format_map_val(v: &Value, indent: usize) -> String {
    match v {
        Value::Array(arr) if !arr.is_empty() => dump_yaml_value(v, indent + 1),
        Value::Object(map) if !map.is_empty() => dump_yaml_value(v, indent + 1),
        _ => dump_yaml_value(v, indent + 1),
    }
}

/// Outcome of running `hwspecs pinned-file-adapter`.
#[derive(Debug, Clone)]
pub struct PinnedFileAdapterOutcome {
    /// Exit code (`0`, `1`, `2`, or `3`).
    pub exit_code: i32,
    /// Structured JSON payload matching `pinned_file_adapter.py`.
    pub payload: Value,
    /// Human-readable lines.
    pub lines: Vec<String>,
    /// Whether output is an error (`stderr` in text mode).
    pub is_error: bool,
}

/// Executes `pinned-file-adapter` (`pinned_file_adapter.py:main`).
///
/// If `out_dir` is provided (`--out <dir>`), also materializes the verified file into `<out_dir>/<path>`.
pub fn run_pinned_file_adapter(
    registry_path: &Path,
    source_id: &str,
    root: &Path,
    run_store: Option<&Path>,
    out_dir: Option<&Path>,
    write: bool,
    dry_run: bool,
    scratch: &ScratchResolver,
) -> PinnedFileAdapterOutcome {
    let make_err = |code: i32, msg: String, result: Value| -> PinnedFileAdapterOutcome {
        let payload = json!({
            "ok": false,
            "updated": false,
            "would_update": false,
            "result": result,
            "findings": [msg],
        });
        PinnedFileAdapterOutcome {
            exit_code: code,
            payload,
            lines: vec![msg],
            is_error: true,
        }
    };

    if dry_run && !write {
        return make_err(
            EXIT_USAGE_ERROR,
            "--dry-run requires --write".to_string(),
            Value::Null,
        );
    }
    if !registry_path.is_file() {
        return make_err(
            EXIT_SANDBOX_ERROR,
            format!("missing file: {}", registry_path.display()),
            Value::Null,
        );
    }

    let loaded = yaml_strict::load_file(registry_path);
    if let Some(err) = loaded.errors.first() {
        let msg = if err.message.contains("duplicate") {
            format!("duplicate YAML key: {}", err.message)
        } else {
            err.message.clone()
        };
        return make_err(EXIT_DOMAIN_FAILURE, msg, Value::Null);
    }
    let Some(mut registry) = loaded.data else {
        return make_err(
            EXIT_DOMAIN_FAILURE,
            "empty registry".to_string(),
            Value::Null,
        );
    };

    if let Err(e) = validate_source_registry(&registry) {
        return make_err(EXIT_DOMAIN_FAILURE, e, Value::Null);
    }

    let source_opt = registry
        .get("sources")
        .and_then(Value::as_array)
        .and_then(|arr| {
            arr.iter()
                .find(|s| s.get("id").and_then(Value::as_str) == Some(source_id))
        })
        .and_then(Value::as_object)
        .cloned();
    let Some(source_obj) = source_opt else {
        return make_err(
            EXIT_DOMAIN_FAILURE,
            format!("source is not registered: {source_id}"),
            Value::Null,
        );
    };

    let today = std::process::Command::new("date")
        .arg("+%Y-%m-%d")
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|_| "1970-01-01".to_string());
    let result = match inspect_pinned_source(&source_obj, root, run_store, &today) {
        Ok(r) => r,
        Err(e) => return make_err(EXIT_DOMAIN_FAILURE, e, Value::Null),
    };

    let status_str = result
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or("unknown");
    let matches_pin = result
        .get("matches_pin")
        .and_then(Value::as_bool)
        .unwrap_or(false);

    if write && status_str != "ok" {
        return make_err(
            EXIT_SANDBOX_ERROR,
            format!("refusing to write {status_str} adapter result; registry is unchanged"),
            Value::Object(result),
        );
    }

    // If `--out <dir>` was specified and the file resolved cleanly and matches its pin,
    // materialize the file into `<out_dir>`.
    if let Some(dest_root) = out_dir {
        if status_str == "ok" && matches_pin {
            if let Some(src_file) = resolve_pinned_file(&source_obj, root, run_store) {
                let rel_path = source_obj
                    .get("file")
                    .and_then(|f| f.get("path"))
                    .and_then(Value::as_str)
                    .unwrap_or(source_id);
                let target_path = dest_root.join(rel_path);
                if let Some(parent) = target_path.parent() {
                    if let Err(e) = fs::create_dir_all(parent) {
                        return make_err(
                            EXIT_SANDBOX_ERROR,
                            format!(
                                "failed to create output directory {}: {e}",
                                parent.display()
                            ),
                            Value::Object(result),
                        );
                    }
                }
                if let Err(e) = fs::copy(&src_file, &target_path) {
                    return make_err(
                        EXIT_SANDBOX_ERROR,
                        format!("failed to materialize {}: {e}", target_path.display()),
                        Value::Object(result),
                    );
                }
            }
        }
    }

    let mut updated = false;
    let mut would_update = false;
    if write {
        match apply_pinned_source_update(&mut registry, &result) {
            Ok(changed) => {
                would_update = changed && dry_run;
                if changed && !dry_run {
                    let dumped = dump_yaml_value(&registry, 0).trim_start().to_string() + "\n";
                    if let Err(e) = write_file_atomic(registry_path, dumped.as_bytes(), scratch) {
                        return make_err(
                            EXIT_SANDBOX_ERROR,
                            format!("failed to update registry: {e}"),
                            Value::Object(result),
                        );
                    }
                    updated = true;
                }
            }
            Err(e) => return make_err(EXIT_DOMAIN_FAILURE, e, Value::Object(result)),
        }
    }

    let exit_code = if status_str != "ok" {
        EXIT_SANDBOX_ERROR
    } else if !matches_pin {
        EXIT_DOMAIN_FAILURE
    } else {
        EXIT_OK
    };

    let sha_disp = result
        .get("sha256")
        .and_then(Value::as_str)
        .unwrap_or("none");
    let line = format!("{status_str} {source_id}: sha256={sha_disp} matches_pin={matches_pin}");
    let payload = json!({
        "ok": exit_code == 0,
        "updated": updated,
        "would_update": would_update,
        "result": Value::Object(result),
        "findings": [],
    });
    PinnedFileAdapterOutcome {
        exit_code,
        payload,
        lines: vec![line],
        is_error: false,
    }
}

/// Writes `bytes` atomically to `dest`, staging in `scratch` first when on the same filesystem
/// (`ENV-3`).
pub fn write_file_atomic(
    dest: &Path,
    bytes: &[u8],
    scratch: &ScratchResolver,
) -> Result<(), SandboxError> {
    if let Ok(staging_dir) = scratch.ensure_dir() {
        if let Ok(mut writer) = AtomicFileWriter::new_in(staging_dir, dest) {
            if writer.write_all(bytes).is_ok() && writer.commit().is_ok() {
                return Ok(());
            }
        }
    }
    let mut writer = AtomicFileWriter::new(dest)?;
    writer.write_all(bytes).map_err(|e| SandboxError::Io {
        context: format!("failed to write temporary file for {}", dest.display()),
        message: e.to_string(),
    })?;
    writer.commit()?;
    Ok(())
}

// ============================================================================
// `hwspecs fetch --cache <dir>` (`ENV-6`)
// ============================================================================

/// Outcome of running `hwspecs fetch --cache <dir>`.
#[derive(Debug, Clone)]
pub struct FetchOutcome {
    /// Exit code (`0`, `1`, `2`, or `3`).
    pub exit_code: ExitCode,
    /// Structured JSON payload.
    pub payload: Value,
    /// Human-readable output lines.
    pub text: Vec<String>,
    /// Diagnostic findings.
    pub findings: Vec<Finding>,
}

/// Collects `.spec.yaml` files from target files or root directories.
pub fn collect_spec_files_from_targets(targets: &[PathBuf]) -> Result<Vec<PathBuf>, UsageError> {
    if targets.is_empty() {
        return Err(UsageError(
            "at least one spec file or root directory is required".to_string(),
        ));
    }
    let mut out = Vec::new();
    for target in targets {
        let Ok(meta) = fs::symlink_metadata(target) else {
            return Err(UsageError(format!(
                "{}: no such file or directory",
                target.display()
            )));
        };
        if meta.file_type().is_symlink() {
            return Err(UsageError(format!(
                "{}: symbolic links are not accepted",
                target.display()
            )));
        }
        if meta.is_file() {
            check_file_path(target, "file")?;
            out.push(target.clone());
        } else if meta.is_dir() {
            let mut stack = vec![target.clone()];
            let mut found = Vec::new();
            while let Some(dir) = stack.pop() {
                let Ok(entries) = fs::read_dir(&dir) else {
                    continue;
                };
                let mut sorted: Vec<PathBuf> =
                    entries.filter_map(|e| e.ok().map(|e| e.path())).collect();
                sorted.sort();
                for p in sorted {
                    let Ok(m) = fs::symlink_metadata(&p) else {
                        continue;
                    };
                    if m.file_type().is_symlink() {
                        continue;
                    }
                    if m.is_dir() {
                        stack.push(p);
                    } else if m.is_file()
                        && p.file_name()
                            .and_then(|n| n.to_str())
                            .is_some_and(|n| n.ends_with(".spec.yaml"))
                    {
                        found.push(p);
                    }
                }
            }
            found.sort();
            out.extend(found);
        }
    }
    Ok(out)
}

/// Populates `<cache>` with full (non-partial) git checkouts/bare repos for pinned `resources.repos`
/// and verified document blobs for pinned `resources.documents` (`ENV-6`).
pub fn run_fetch_command(
    targets: &[PathBuf],
    cache_dir: &Path,
    repo_specs: &[String],
    docs_dir: Option<&Path>,
    offline: bool,
    scratch: &ScratchResolver,
) -> FetchOutcome {
    let usage = |msg: String| -> FetchOutcome {
        let f = Finding::error("FETCH-USAGE", "", 0, 0, msg.clone());
        FetchOutcome {
            exit_code: ExitCode::UsageError,
            payload: json!({
                "ok": false,
                "error": "usage",
                "repos": [],
                "documents": [],
                "findings": [f],
            }),
            text: vec![format!("usage error: {msg}")],
            findings: vec![f],
        }
    };
    let precond = |code: &str, msg: String| -> FetchOutcome {
        let f = Finding::error(code, "", 0, 0, msg.clone());
        FetchOutcome {
            exit_code: ExitCode::SandboxError,
            payload: json!({
                "ok": false,
                "error": "precondition",
                "repos": [],
                "documents": [],
                "findings": [f],
            }),
            text: vec![format!("missing precondition: {msg}")],
            findings: vec![f],
        }
    };

    let spec_files = match collect_spec_files_from_targets(targets) {
        Ok(f) => f,
        Err(e) => return usage(e.to_string()),
    };
    let repo_map = match parse_repo_specs(repo_specs) {
        Ok(m) => m,
        Err(e) => return usage(e.to_string()),
    };
    if let Some(d) = docs_dir {
        if let Err(e) = check_dir_path(d, "--docs-dir") {
            return usage(e.to_string());
        }
    }

    if let Err(e) = fs::create_dir_all(cache_dir) {
        return precond(
            "SANDBOX-IO",
            format!("cannot create cache directory {}: {e}", cache_dir.display()),
        );
    }

    let mut findings: Vec<Finding> = Vec::new();
    let mut cached_repos: Vec<Value> = Vec::new();
    let mut cached_docs: Vec<Value> = Vec::new();
    let mut text_lines: Vec<String> = Vec::new();
    let mut seen_repos: BTreeMap<String, (String, String)> = BTreeMap::new();
    let mut seen_docs: BTreeMap<String, (String, String)> = BTreeMap::new();

    for path in &spec_files {
        let loaded = yaml_strict::load_file(path);
        if !loaded.ok() {
            findings.extend(loaded.findings());
            continue;
        }
        let Some(ref data) = loaded.data else {
            continue;
        };
        if let Some(repos) = data
            .get("resources")
            .and_then(|r| r.get("repos"))
            .and_then(Value::as_array)
        {
            for r in repos {
                let Some(name) = r.get("name").and_then(Value::as_str) else {
                    continue;
                };
                let Some(url) = r.get("url").and_then(Value::as_str) else {
                    continue;
                };
                let Some(commit) = r.get("commit").and_then(Value::as_str) else {
                    continue;
                };
                if !is_valid_commit_oid(commit) {
                    findings.push(Finding::error(
                        "FETCH-INVALID-COMMIT",
                        path.display().to_string(),
                        1,
                        1,
                        format!("repos entry '{name}' does not pin a full 40/64-hex commit"),
                    ));
                    continue;
                }
                seen_repos
                    .entry(name.to_string())
                    .or_insert_with(|| (url.to_string(), commit.to_string()));
            }
        }
        if let Some(docs) = data
            .get("resources")
            .and_then(|r| r.get("documents"))
            .and_then(Value::as_array)
        {
            for d in docs {
                let Some(name) = d.get("name").and_then(Value::as_str) else {
                    continue;
                };
                let url = d
                    .get("url")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string();
                let Some(sha256) = d.get("sha256").and_then(Value::as_str) else {
                    continue;
                };
                seen_docs
                    .entry(name.to_string())
                    .or_insert_with(|| (url, sha256.to_string()));
            }
        }
    }

    for (name, (url, commit)) in &seen_repos {
        let dest = cache_dir.join(name);
        if let Some(bound) = repo_map.get(name) {
            if let Err(e) = check_not_partial_clone(name, bound) {
                return precond(&e.code, e.message);
            }
            if !dest.exists() {
                if let Err(e) = fs::create_dir_all(&dest) {
                    return precond(
                        "SANDBOX-IO",
                        format!("failed to create {}: {e}", dest.display()),
                    );
                }
                if let Err(e) = run_git(&["init", "-q"], &dest, DEFAULT_STDOUT_LIMIT) {
                    return precond("SANDBOX-IO", e.to_string());
                }
            }
            let src_str = bound.display().to_string();
            let mut cmd = Command::new("git");
            cmd.args([
                "-C",
                &dest.display().to_string(),
                "fetch",
                "--quiet",
                "--no-tags",
                "--",
                &src_str,
                commit,
            ]);
            let _ = run_bounded(&mut cmd, PipeLimits::default());
        } else {
            if offline {
                return precond(
                    "SANDBOX-OFFLINE",
                    SandboxError::OfflineForbidden {
                        operation: format!("git fetch {url} {commit} into cache for '{name}'"),
                    }
                    .to_string(),
                );
            }
            if !dest.exists() {
                if let Err(e) = fs::create_dir_all(&dest) {
                    return precond(
                        "SANDBOX-IO",
                        format!("failed to create {}: {e}", dest.display()),
                    );
                }
                if let Err(e) = run_git(&["init", "-q"], &dest, DEFAULT_STDOUT_LIMIT) {
                    return precond("SANDBOX-IO", e.to_string());
                }
            }
            if let Err(e) = run_git(
                &[
                    "fetch",
                    "--quiet",
                    "--no-tags",
                    "--depth=1",
                    "--",
                    url,
                    commit,
                ],
                &dest,
                DEFAULT_STDOUT_LIMIT,
            ) {
                findings.push(Finding::error(
                    "FETCH-REPO-FAILED",
                    dest.display().to_string(),
                    1,
                    1,
                    format!("repo '{name}' at {commit}: {e}"),
                ));
                continue;
            }
        }
        let repo_check = Repository::new(dest.clone(), commit.clone(), DEFAULT_STDOUT_LIMIT);
        if let Err(e) = repo_check.ensure_commit() {
            findings.push(Finding::error(
                "FETCH-REPO-FAILED",
                dest.display().to_string(),
                1,
                1,
                format!("repo '{name}' at {commit}: {e}"),
            ));
            continue;
        }
        text_lines.push(format!(
            "cached repo {name} at {commit} -> {}",
            dest.display()
        ));
        cached_repos.push(json!({
            "name": name,
            "commit": commit,
            "path": visible_name(&dest.display().to_string()),
        }));
    }

    let docs_cache_dir = cache_dir.join("docs");
    if !seen_docs.is_empty() {
        if let Err(e) = fs::create_dir_all(&docs_cache_dir) {
            return precond(
                "SANDBOX-IO",
                format!("cannot create {}: {e}", docs_cache_dir.display()),
            );
        }
    }

    for (name, (url, want_sha)) in &seen_docs {
        let dest = docs_cache_dir.join(name);
        let bytes_res: Result<Vec<u8>, String> = if let Some(d_dir) = docs_dir {
            let src = d_dir.join(name);
            fs::read(&src).map_err(|e| format!("cannot read {}: {e}", src.display()))
        } else if dest.is_file() {
            fs::read(&dest).map_err(|e| format!("cannot read {}: {e}", dest.display()))
        } else if offline {
            return precond(
                "SANDBOX-OFFLINE",
                SandboxError::OfflineForbidden {
                    operation: format!("download document '{name}' from {url}"),
                }
                .to_string(),
            );
        } else {
            Err(format!(
                "document '{name}' not present in cache and remote document fetch requires --docs-dir"
            ))
        };

        match bytes_res {
            Ok(bytes) => {
                let check = check_blob(&bytes, want_sha);
                if check.status != "ok" {
                    findings.push(Finding::error(
                        "DOC-HASH-MISMATCH",
                        dest.display().to_string(),
                        1,
                        1,
                        format!(
                            "document '{name}' sha256 is {}, expected {want_sha}",
                            check.actual
                        ),
                    ));
                    continue;
                }
                if let Err(e) = write_file_atomic(&dest, &bytes, scratch) {
                    return precond(e.code(), e.to_string());
                }
                text_lines.push(format!(
                    "cached document {name} ({want_sha}) -> {}",
                    dest.display()
                ));
                cached_docs.push(json!({
                    "name": name,
                    "sha256": want_sha,
                    "bytes": check.bytes,
                    "path": visible_name(&dest.display().to_string()),
                }));
            }
            Err(msg) => {
                findings.push(Finding::error(
                    "FETCH-DOC-FAILED",
                    dest.display().to_string(),
                    1,
                    1,
                    msg,
                ));
            }
        }
    }

    let has_errors = findings.iter().any(|f| f.level == "error");
    let exit_code = if has_errors {
        ExitCode::DomainFailure
    } else {
        ExitCode::Pass
    };
    for f in &findings {
        text_lines.push(f.to_string());
    }
    FetchOutcome {
        exit_code,
        payload: json!({
            "ok": !has_errors,
            "repos": cached_repos,
            "documents": cached_docs,
            "findings": findings,
        }),
        text: text_lines,
        findings,
    }
}
