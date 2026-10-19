// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Sandbox primitives (`ENV-1`..`ENV-3`):
//! - Lazy scratch directory resolver (`--scratch-dir` -> `TMPDIR`, never `cwd` or `$HOME`,
//!   zero filesystem writes when unused, exit code `3` when neither is writable).
//! - Bounded in-memory subprocess pipe runner (`Stdio::piped()` + `.take(limit + 1)`)
//!   with configurable stdout/stderr caps (default 64 MiB stdout, 1 MiB stderr) and exit `3`
//!   on overflow.
//! - RAII atomic file writer (`NamedTempFile::new_in(parent)` + `persist(dest)`).

use crate::diagnostic::{ExitCode, Finding, EXIT_SANDBOX_ERROR};
use std::env;
use std::fmt;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::OnceLock;
use std::thread;
use tempfile::{NamedTempFile, TempDir};

/// Default maximum bytes captured from a child process's `stdout` (64 MiB).
pub const DEFAULT_STDOUT_LIMIT: usize = 64 * 1024 * 1024;
/// Default maximum bytes captured from a child process's `stderr` (1 MiB).
pub const DEFAULT_STDERR_LIMIT: usize = 1024 * 1024;

/// Error returned by sandbox, scratch, subprocess, or atomic file operations.
/// Always maps to [`ExitCode::SandboxError`] (`exit 3`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SandboxError {
    /// Neither `--scratch-dir` nor `TMPDIR` is a usable, writable scratch directory.
    ScratchUnavailable {
        scratch_dir: Option<PathBuf>,
        tmpdir: Option<PathBuf>,
        reason: String,
    },
    /// Offline mode (`--offline`) forbade a network operation.
    OfflineForbidden { operation: String },
    /// Failed to spawn a child process.
    SubprocessSpawn { program: String, message: String },
    /// Child process exceeded the configured `stdout` or `stderr` byte limit.
    OutputOverflow {
        program: String,
        stream: &'static str,
        limit: usize,
    },
    /// I/O error while reading from pipes or persisting an atomic file.
    Io { context: String, message: String },
}

impl SandboxError {
    /// Returns the exit code for any sandbox error (`ExitCode::SandboxError` = `3`).
    #[must_use]
    pub const fn exit_code(&self) -> ExitCode {
        ExitCode::SandboxError
    }

    /// Returns the numeric exit status (`3`).
    #[must_use]
    pub const fn exit_status(&self) -> i32 {
        EXIT_SANDBOX_ERROR
    }

    /// Stable diagnostic code for this sandbox error.
    #[must_use]
    pub const fn code(&self) -> &'static str {
        match self {
            Self::ScratchUnavailable { .. } => "SANDBOX-SCRATCH-UNAVAILABLE",
            Self::OfflineForbidden { .. } => "SANDBOX-OFFLINE",
            Self::SubprocessSpawn { .. } => "SANDBOX-SUBPROCESS-SPAWN",
            Self::OutputOverflow { .. } => "SANDBOX-PIPE-OVERFLOW",
            Self::Io { .. } => "SANDBOX-IO",
        }
    }

    /// Converts this error into a structured [`Finding`].
    #[must_use]
    pub fn to_finding(&self) -> Finding {
        Finding::error(self.code(), "", 0, 0, self.to_string())
    }
}

impl fmt::Display for SandboxError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ScratchUnavailable {
                scratch_dir,
                tmpdir,
                reason,
            } => {
                let s_disp = scratch_dir
                    .as_ref()
                    .map_or_else(|| "<unset>".to_string(), |p| p.display().to_string());
                let t_disp = tmpdir
                    .as_ref()
                    .map_or_else(|| "<unset>".to_string(), |p| p.display().to_string());
                write!(
                    f,
                    "cannot allocate scratch directory: neither --scratch-dir ({s_disp}) nor TMPDIR ({t_disp}) is writable ({reason}); pass --scratch-dir <dir> or set TMPDIR to a writable directory"
                )
            }
            Self::OfflineForbidden { operation } => {
                write!(
                    f,
                    "network operation forbidden under --offline: {operation}; bind repositories locally with --repo NAME=CHECKOUT or provide --docs-dir"
                )
            }
            Self::SubprocessSpawn { program, message } => {
                write!(f, "failed to execute '{program}': {message}")
            }
            Self::OutputOverflow {
                program,
                stream,
                limit,
            } => {
                write!(
                    f,
                    "subprocess '{program}' exceeded {stream} limit of {limit} bytes"
                )
            }
            Self::Io { context, message } => {
                write!(f, "{context}: {message}")
            }
        }
    }
}

impl std::error::Error for SandboxError {}

/// Canonicalizes a path if possible, otherwise returns the path with trailing slashes stripped.
fn normalize_dir_path(p: &Path) -> PathBuf {
    fs::canonicalize(p).unwrap_or_else(|_| p.to_path_buf())
}

/// Returns `true` if `candidate` is the current working directory (`cwd`) or `$HOME`.
/// Per `ENV-1` and `ENV-2`, scratch resolution must never use `cwd` or `$HOME`.
fn is_forbidden_fallback_dir(candidate: &Path) -> Option<&'static str> {
    let norm_cand = normalize_dir_path(candidate);
    if let Ok(cwd) = env::current_dir() {
        if norm_cand == normalize_dir_path(&cwd) {
            return Some("refusing to use current working directory (cwd) as scratch space");
        }
    }
    if let Some(home) = env::var_os("HOME").filter(|h| !h.is_empty()) {
        let home_path = PathBuf::from(home);
        if norm_cand == normalize_dir_path(&home_path) {
            return Some("refusing to use $HOME as scratch space");
        }
    }
    None
}

/// Lazy scratch directory resolver (`ENV-1`, `ENV-2`).
///
/// Creating a [`ScratchResolver`] performs **zero** filesystem operations or writes.
/// A temporary directory is only probed and created when [`ScratchResolver::ensure_dir`],
/// [`ScratchResolver::temp_dir`], or [`ScratchResolver::named_temp_file`] is called.
#[derive(Debug)]
pub struct ScratchResolver {
    scratch_dir: Option<PathBuf>,
    tmpdir_override: Option<PathBuf>,
    use_env_tmpdir: bool,
    allocated: OnceLock<TempDir>,
}

impl ScratchResolver {
    /// Creates a lazy scratch resolver using `--scratch-dir` (if provided) and process `TMPDIR`.
    /// Performs zero filesystem writes until scratch space is requested.
    #[must_use]
    pub const fn new(scratch_dir: Option<PathBuf>) -> Self {
        Self {
            scratch_dir,
            tmpdir_override: None,
            use_env_tmpdir: true,
            allocated: OnceLock::new(),
        }
    }

    /// Creates a lazy scratch resolver with explicit `--scratch-dir` and `TMPDIR` values
    /// (useful for deterministic testing without mutating process-wide environment variables).
    #[must_use]
    pub const fn with_tmpdir(scratch_dir: Option<PathBuf>, tmpdir: Option<PathBuf>) -> Self {
        Self {
            scratch_dir,
            tmpdir_override: tmpdir,
            use_env_tmpdir: false,
            allocated: OnceLock::new(),
        }
    }

    /// Returns `true` if a scratch directory has been materialized by this resolver.
    #[must_use]
    pub fn is_allocated(&self) -> bool {
        self.allocated.get().is_some()
    }

    fn effective_tmpdir(&self) -> Option<PathBuf> {
        if self.use_env_tmpdir {
            env::var_os("TMPDIR")
                .filter(|v| !v.is_empty())
                .map(PathBuf::from)
                .or_else(|| Some(env::temp_dir()))
        } else {
            self.tmpdir_override.clone()
        }
    }

    /// Validates a candidate parent directory and creates a new [`TempDir`] inside it.
    fn try_allocate_in(candidate: &Path) -> Result<TempDir, String> {
        if candidate.as_os_str().is_empty() {
            return Err("empty path".to_string());
        }
        if let Some(reason) = is_forbidden_fallback_dir(candidate) {
            return Err(reason.to_string());
        }
        if !candidate.exists() {
            fs::create_dir_all(candidate).map_err(|e| format!("{}: {e}", candidate.display()))?;
        }
        let meta = fs::metadata(candidate).map_err(|e| format!("{}: {e}", candidate.display()))?;
        if !meta.is_dir() {
            return Err(format!("{} is not a directory", candidate.display()));
        }
        TempDir::new_in(candidate).map_err(|e| format!("{}: {e}", candidate.display()))
    }

    /// Resolves and creates a new isolated [`TempDir`] inside `--scratch-dir` or `TMPDIR`.
    ///
    /// Resolution rules (`ENV-1`, `ENV-2`):
    /// 1. If `--scratch-dir <dir>` was specified, try `<dir>`. If `<dir>` is not writable and
    ///    `TMPDIR` was not also usable, fail with [`ExitCode::SandboxError`] (`3`).
    /// 2. If `--scratch-dir` was not specified, try `TMPDIR` (`$TMPDIR` / `env::temp_dir()`).
    /// 3. Never fall back to `cwd` or `$HOME`.
    pub fn temp_dir(&self) -> Result<TempDir, SandboxError> {
        let tmpdir = self.effective_tmpdir();

        if let Some(ref sdir) = self.scratch_dir {
            match Self::try_allocate_in(sdir) {
                Ok(td) => return Ok(td),
                Err(s_err) => {
                    return Err(SandboxError::ScratchUnavailable {
                        scratch_dir: Some(sdir.clone()),
                        tmpdir,
                        reason: s_err,
                    });
                }
            }
        }

        if let Some(ref tdir) = tmpdir {
            match Self::try_allocate_in(tdir) {
                Ok(td) => return Ok(td),
                Err(t_err) => {
                    return Err(SandboxError::ScratchUnavailable {
                        scratch_dir: None,
                        tmpdir: Some(tdir.clone()),
                        reason: t_err,
                    });
                }
            }
        }

        Err(SandboxError::ScratchUnavailable {
            scratch_dir: self.scratch_dir.clone(),
            tmpdir: None,
            reason: "no scratch directory or TMPDIR configured".to_string(),
        })
    }

    /// Lazily allocates (at most once per [`ScratchResolver`] instance) a shared scratch
    /// directory and returns its path.
    pub fn ensure_dir(&self) -> Result<&Path, SandboxError> {
        if let Some(td) = self.allocated.get() {
            return Ok(td.path());
        }
        let td = self.temp_dir()?;
        let _ = self.allocated.set(td);
        Ok(self.allocated.get().expect("just initialized").path())
    }

    /// Lazily allocates a [`NamedTempFile`] inside this resolver's scratch space.
    pub fn named_temp_file(&self) -> Result<NamedTempFile, SandboxError> {
        let dir = self.ensure_dir()?;
        NamedTempFile::new_in(dir).map_err(|e| SandboxError::Io {
            context: format!("failed to create temporary file in {}", dir.display()),
            message: e.to_string(),
        })
    }
}

/// Configurable byte caps for bounded in-memory subprocess pipes (`ENV-1`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PipeLimits {
    /// Maximum allowed bytes on `stdout` before aborting with exit `3`.
    pub stdout_limit: usize,
    /// Maximum allowed bytes on `stderr` before aborting with exit `3`.
    pub stderr_limit: usize,
}

impl Default for PipeLimits {
    fn default() -> Self {
        Self {
            stdout_limit: DEFAULT_STDOUT_LIMIT,
            stderr_limit: DEFAULT_STDERR_LIMIT,
        }
    }
}

impl PipeLimits {
    /// Creates custom `stdout` and `stderr` byte limits.
    #[must_use]
    pub const fn new(stdout_limit: usize, stderr_limit: usize) -> Self {
        Self {
            stdout_limit,
            stderr_limit,
        }
    }
}

/// Output captured in memory from a bounded child process execution.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SubprocessOutput {
    /// Process exit status code (or `-1` if killed by a signal).
    pub status: i32,
    /// Captured `stdout` bytes (guaranteed `<= limits.stdout_limit`).
    pub stdout: Vec<u8>,
    /// Captured `stderr` bytes (guaranteed `<= limits.stderr_limit`).
    pub stderr: Vec<u8>,
}

impl SubprocessOutput {
    /// Returns `true` if the child exited with status `0`.
    #[must_use]
    pub const fn success(&self) -> bool {
        self.status == 0
    }
}

fn read_bounded<R: Read>(mut reader: R, limit: usize) -> io::Result<(Vec<u8>, bool)> {
    let mut buf = Vec::new();
    let max_read = (limit as u64).saturating_add(1);
    reader.by_ref().take(max_read).read_to_end(&mut buf)?;
    if buf.len() > limit {
        buf.truncate(limit);
        Ok((buf, true))
    } else {
        Ok((buf, false))
    }
}

/// Runs `cmd` with `Stdio::piped()` and reads `stdout` and `stderr` in memory using
/// `.take(limit + 1)` without creating any temporary files (`ENV-1`).
///
/// If either `stdout` or `stderr` exceeds its configured limit in `limits`, the child
/// process is terminated and [`SandboxError::OutputOverflow`] (`exit 3`) is returned.
pub fn run_bounded(
    cmd: &mut Command,
    limits: PipeLimits,
) -> Result<SubprocessOutput, SandboxError> {
    let program = cmd.get_program().to_string_lossy().into_owned();
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = cmd.spawn().map_err(|e| SandboxError::SubprocessSpawn {
        program: program.clone(),
        message: e.to_string(),
    })?;

    let stdout_pipe = child.stdout.take().ok_or_else(|| SandboxError::Io {
        context: format!("failed to capture stdout for '{program}'"),
        message: "stdout pipe missing".to_string(),
    })?;
    let stderr_pipe = child.stderr.take().ok_or_else(|| SandboxError::Io {
        context: format!("failed to capture stderr for '{program}'"),
        message: "stderr pipe missing".to_string(),
    })?;

    let stdout_limit = limits.stdout_limit;
    let stderr_limit = limits.stderr_limit;

    let (out_res, err_res) = thread::scope(|s| {
        let out_handle = s.spawn(move || read_bounded(stdout_pipe, stdout_limit));
        let err_handle = s.spawn(move || read_bounded(stderr_pipe, stderr_limit));
        let out = out_handle
            .join()
            .unwrap_or_else(|_| Err(io::Error::other("stdout reader thread panicked")));
        let err = err_handle
            .join()
            .unwrap_or_else(|_| Err(io::Error::other("stderr reader thread panicked")));
        (out, err)
    });

    let (stdout, out_overflow) = out_res.map_err(|e| {
        let _ = child.kill();
        let _ = child.wait();
        SandboxError::Io {
            context: format!("reading stdout from '{program}'"),
            message: e.to_string(),
        }
    })?;

    let (stderr, err_overflow) = err_res.map_err(|e| {
        let _ = child.kill();
        let _ = child.wait();
        SandboxError::Io {
            context: format!("reading stderr from '{program}'"),
            message: e.to_string(),
        }
    })?;

    if out_overflow {
        let _ = child.kill();
        let _ = child.wait();
        return Err(SandboxError::OutputOverflow {
            program,
            stream: "stdout",
            limit: stdout_limit,
        });
    }

    if err_overflow {
        let _ = child.kill();
        let _ = child.wait();
        return Err(SandboxError::OutputOverflow {
            program,
            stream: "stderr",
            limit: stderr_limit,
        });
    }

    let exit_status = child.wait().map_err(|e| SandboxError::Io {
        context: format!("waiting for subprocess '{program}'"),
        message: e.to_string(),
    })?;

    Ok(SubprocessOutput {
        status: exit_status.code().unwrap_or(-1),
        stdout,
        stderr,
    })
}

/// Runs `cmd` with the default pipe limits (64 MiB `stdout`, 1 MiB `stderr`).
pub fn run_subprocess(cmd: &mut Command) -> Result<SubprocessOutput, SandboxError> {
    run_bounded(cmd, PipeLimits::default())
}

/// RAII atomic file writer built on [`NamedTempFile::new_in`] and [`NamedTempFile::persist`]
/// (`ENV-3`).
///
/// Stages writes into a temporary file in the destination's parent directory (or an explicit
/// staging directory). If dropped before [`AtomicFileWriter::commit`] is called, the temporary
/// file is automatically removed so no partial or stray dotfile remains on disk.
#[derive(Debug)]
pub struct AtomicFileWriter {
    temp: NamedTempFile,
    dest: PathBuf,
}

impl AtomicFileWriter {
    /// Creates a new [`AtomicFileWriter`] staging in `dest`'s parent directory.
    pub fn new(dest: impl AsRef<Path>) -> Result<Self, SandboxError> {
        let dest = dest.as_ref().to_path_buf();
        let parent = match dest.parent() {
            Some(p) if !p.as_os_str().is_empty() => p.to_path_buf(),
            _ => PathBuf::from("."),
        };
        Self::new_in(&parent, dest)
    }

    /// Writes all bytes in `buf` to the underlying staged temporary file.
    pub fn write_all_bytes(&mut self, buf: &[u8]) -> Result<(), SandboxError> {
        self.temp.write_all(buf).map_err(|e| SandboxError::Io {
            context: format!(
                "failed to write temporary file for '{}'",
                self.dest.display()
            ),
            message: e.to_string(),
        })
    }

    /// Creates a new [`AtomicFileWriter`] staging in `staging_dir` and persisting to `dest`.
    pub fn new_in(
        staging_dir: impl AsRef<Path>,
        dest: impl AsRef<Path>,
    ) -> Result<Self, SandboxError> {
        let staging_dir = staging_dir.as_ref();
        let dest = dest.as_ref().to_path_buf();
        let temp = NamedTempFile::new_in(staging_dir).map_err(|e| SandboxError::Io {
            context: format!(
                "failed to create temporary file in '{}' for '{}'",
                staging_dir.display(),
                dest.display()
            ),
            message: e.to_string(),
        })?;
        Ok(Self { temp, dest })
    }

    /// Returns the path of the underlying staged temporary file.
    #[must_use]
    pub fn temp_path(&self) -> &Path {
        self.temp.path()
    }

    /// Returns the target destination path.
    #[must_use]
    pub fn dest_path(&self) -> &Path {
        &self.dest
    }

    /// Flushes and atomically persists the temporary file to `dest`.
    pub fn commit(mut self) -> Result<PathBuf, SandboxError> {
        self.temp.flush().map_err(|e| SandboxError::Io {
            context: format!(
                "failed to flush temporary file for '{}'",
                self.dest.display()
            ),
            message: e.to_string(),
        })?;
        self.temp
            .as_file()
            .sync_all()
            .map_err(|e| SandboxError::Io {
                context: format!(
                    "failed to sync temporary file for '{}'",
                    self.dest.display()
                ),
                message: e.to_string(),
            })?;
        self.temp
            .persist(&self.dest)
            .map_err(|e| SandboxError::Io {
                context: format!("failed to persist atomic file to '{}'", self.dest.display()),
                message: e.error.to_string(),
            })?;
        Ok(self.dest)
    }

    /// Alias for [`AtomicFileWriter::commit`].
    pub fn finish(self) -> Result<PathBuf, SandboxError> {
        self.commit()
    }
}

impl Write for AtomicFileWriter {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        self.temp.write(buf)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.temp.flush()
    }
}

/// Atomically writes `bytes` to `dest` via [`AtomicFileWriter`].
pub fn atomic_write(dest: impl AsRef<Path>, bytes: &[u8]) -> Result<PathBuf, SandboxError> {
    let mut writer = AtomicFileWriter::new(dest)?;
    writer.write_all(bytes).map_err(|e| SandboxError::Io {
        context: format!(
            "failed to write temporary file for '{}'",
            writer.dest_path().display()
        ),
        message: e.to_string(),
    })?;
    writer.commit()
}

/// Atomically writes UTF-8 `text` to `dest` via [`AtomicFileWriter`].
pub fn atomic_write_str(dest: impl AsRef<Path>, text: &str) -> Result<PathBuf, SandboxError> {
    atomic_write(dest, text.as_bytes())
}
