// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Structured diagnostic model, JSON envelope output, exit code classification,
//! and terminal-safe visible name formatting.

use serde::de::{self, Deserializer, MapAccess, Visitor};
use serde::ser::{SerializeStruct, Serializer};
use serde::{Deserialize, Serialize};
use std::cmp::Ordering;
use std::fmt;
use std::path::Path;
use std::str::FromStr;

/// Process exit code when a command succeeds with zero errors.
pub const EXIT_OK: i32 = 0;
/// Process exit code when domain or validation errors are found.
pub const EXIT_DOMAIN_FAILURE: i32 = 1;
/// Alias for [`EXIT_DOMAIN_FAILURE`].
pub const EXIT_INVALID: i32 = 1;
/// Process exit code when CLI usage or argument validation fails.
pub const EXIT_USAGE_ERROR: i32 = 2;
/// Alias for [`EXIT_USAGE_ERROR`].
pub const EXIT_USAGE: i32 = 2;
/// Process exit code when sandbox, environment, or precondition checks fail.
pub const EXIT_SANDBOX_ERROR: i32 = 3;
/// Alias for [`EXIT_SANDBOX_ERROR`].
pub const EXIT_ENV_ERROR: i32 = 3;
/// Alias for [`EXIT_SANDBOX_ERROR`].
pub const EXIT_PRECONDITION: i32 = 3;
/// Process exit code for unexpected internal tool errors.
pub const EXIT_INTERNAL: i32 = 100;

/// Exit code classification for `driver-lab` commands.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[repr(i32)]
pub enum ExitCode {
    /// `0` — command succeeded (warnings allowed).
    Pass = EXIT_OK,
    /// `1` — domain, schema, semantic, or verification failure.
    DomainFailure = EXIT_DOMAIN_FAILURE,
    /// `2` — CLI argument or usage error.
    UsageError = EXIT_USAGE_ERROR,
    /// `3` — sandbox, environment, or precondition error.
    SandboxError = EXIT_SANDBOX_ERROR,
}

impl ExitCode {
    /// Alias for [`ExitCode::Pass`].
    pub const OK: Self = Self::Pass;
    /// Alias for [`ExitCode::DomainFailure`].
    pub const VALIDATION_FAILURE: Self = Self::DomainFailure;
    /// Alias for [`ExitCode::DomainFailure`].
    pub const INVALID: Self = Self::DomainFailure;
    /// Alias for [`ExitCode::UsageError`].
    pub const CLI_USAGE_ERROR: Self = Self::UsageError;
    /// Alias for [`ExitCode::SandboxError`].
    pub const ENVIRONMENT_ERROR: Self = Self::SandboxError;
    /// Alias for [`ExitCode::SandboxError`].
    pub const PRECONDITION_ERROR: Self = Self::SandboxError;

    /// Returns the numeric exit status (`0`, `1`, `2`, or `3`).
    #[must_use]
    pub const fn code(self) -> i32 {
        self as i32
    }

    /// Returns the numeric exit status (`0`, `1`, `2`, or `3`).
    #[must_use]
    pub const fn as_i32(self) -> i32 {
        self as i32
    }

    /// Classifies an integer exit status into an [`ExitCode`].
    #[must_use]
    pub const fn from_i32(code: i32) -> Option<Self> {
        match code {
            0 => Some(Self::Pass),
            1 => Some(Self::DomainFailure),
            2 => Some(Self::UsageError),
            3 => Some(Self::SandboxError),
            _ => None,
        }
    }
}

impl From<ExitCode> for i32 {
    fn from(value: ExitCode) -> Self {
        value.code()
    }
}

impl From<ExitCode> for std::process::ExitCode {
    fn from(value: ExitCode) -> Self {
        std::process::ExitCode::from(value.code() as u8)
    }
}

/// Severity level of a diagnostic finding.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Level {
    /// Blocks validation or checking (`exit 1`).
    Error,
    /// Non-blocking warning (`exit 0` unless promoted by strict flags).
    Warning,
    /// Informational diagnostic note.
    Note,
}

impl Level {
    /// Returns the lowercase string representation (`"error"`, `"warning"`, or `"note"`).
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Error => "error",
            Self::Warning => "warning",
            Self::Note => "note",
        }
    }
}

impl fmt::Display for Level {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for Level {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "error" => Ok(Self::Error),
            "warning" => Ok(Self::Warning),
            "note" => Ok(Self::Note),
            other => Err(format!("unknown diagnostic level: {other}")),
        }
    }
}

impl PartialEq<&str> for Level {
    fn eq(&self, other: &&str) -> bool {
        self.as_str() == *other
    }
}

impl PartialEq<str> for Level {
    fn eq(&self, other: &str) -> bool {
        self.as_str() == other
    }
}

/// A structured diagnostic finding with stable code and 1-based source coordinates.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Finding {
    /// Severity level (`error`, `warning`, or `note`).
    pub level: Level,
    /// Stable finding code (e.g., `"YAML-DUPLICATE-KEY"`, `"SPDX-LICENSEREF-PUBLIC"`).
    pub code: String,
    /// File path (escaped with [`visible_name`] when rendered).
    pub path: String,
    /// 1-based line number (`0` when not attached to a specific line).
    pub line: usize,
    /// 1-based column number (`0` when not attached to a specific column).
    pub col: usize,
    /// Human-readable diagnostic message.
    pub message: String,
}

impl Finding {
    /// Constructs a new [`Finding`].
    #[must_use]
    pub fn new(
        level: Level,
        code: impl Into<String>,
        path: impl Into<String>,
        line: usize,
        col: usize,
        message: impl Into<String>,
    ) -> Self {
        Self {
            level,
            code: code.into(),
            path: path.into(),
            line,
            col,
            message: message.into(),
        }
    }

    /// Constructs an error-level [`Finding`].
    #[must_use]
    pub fn error(
        code: impl Into<String>,
        path: impl Into<String>,
        line: usize,
        col: usize,
        message: impl Into<String>,
    ) -> Self {
        Self::new(Level::Error, code, path, line, col, message)
    }

    /// Constructs a warning-level [`Finding`].
    #[must_use]
    pub fn warning(
        code: impl Into<String>,
        path: impl Into<String>,
        line: usize,
        col: usize,
        message: impl Into<String>,
    ) -> Self {
        Self::new(Level::Warning, code, path, line, col, message)
    }

    /// Constructs a note-level [`Finding`].
    #[must_use]
    pub fn note(
        code: impl Into<String>,
        path: impl Into<String>,
        line: usize,
        col: usize,
        message: impl Into<String>,
    ) -> Self {
        Self::new(Level::Note, code, path, line, col, message)
    }

    /// Returns the 1-based column number (alias for `self.col`).
    #[must_use]
    pub const fn column(&self) -> usize {
        self.col
    }

    /// Formats the finding as `path:line:col: level: message` with terminal-safe path escaping.
    #[must_use]
    pub fn format_with_level(&self) -> String {
        if self.path.is_empty() && self.line == 0 && self.col == 0 {
            format!("{}: {}", self.level, self.message)
        } else {
            format!(
                "{}:{}:{}: {}: {}",
                visible_name(&self.path),
                self.line,
                self.col,
                self.level,
                self.message
            )
        }
    }

    /// Formats the finding as `path:line:col: message` (used by `validate`).
    #[must_use]
    pub fn format_without_level(&self) -> String {
        if self.path.is_empty() && self.line == 0 && self.col == 0 {
            self.message.clone()
        } else {
            format!(
                "{}:{}:{}: {}",
                visible_name(&self.path),
                self.line,
                self.col,
                self.message
            )
        }
    }
}

impl fmt::Display for Finding {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.format_with_level())
    }
}

impl Serialize for Finding {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut st = serializer.serialize_struct("Finding", 7)?;
        st.serialize_field("level", &self.level)?;
        st.serialize_field("code", &self.code)?;
        st.serialize_field("path", &visible_name(&self.path))?;
        st.serialize_field("line", &self.line)?;
        st.serialize_field("col", &self.col)?;
        st.serialize_field("column", &self.col)?;
        st.serialize_field("message", &self.message)?;
        st.end()
    }
}

impl<'de> Deserialize<'de> for Finding {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct FindingVisitor;

        impl<'de> Visitor<'de> for FindingVisitor {
            type Value = Finding;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("struct Finding")
            }

            fn visit_map<V>(self, mut map: V) -> Result<Finding, V::Error>
            where
                V: MapAccess<'de>,
            {
                let mut level = None;
                let mut code = None;
                let mut path = None;
                let mut line = None;
                let mut col = None;
                let mut column = None;
                let mut message = None;

                while let Some(key) = map.next_key::<String>()? {
                    match key.as_str() {
                        "level" => level = Some(map.next_value()?),
                        "code" => code = Some(map.next_value()?),
                        "path" => path = Some(map.next_value()?),
                        "line" => line = Some(map.next_value()?),
                        "col" => col = Some(map.next_value()?),
                        "column" => column = Some(map.next_value()?),
                        "message" => message = Some(map.next_value()?),
                        _ => {
                            let _: serde::de::IgnoredAny = map.next_value()?;
                        }
                    }
                }

                let resolved_col = col.or(column).unwrap_or(0);
                Ok(Finding {
                    level: level.unwrap_or(Level::Error),
                    code: code.unwrap_or_default(),
                    path: path.unwrap_or_default(),
                    line: line.unwrap_or(0),
                    col: resolved_col,
                    message: message.ok_or_else(|| de::Error::missing_field("message"))?,
                })
            }
        }

        deserializer.deserialize_map(FindingVisitor)
    }
}

/// Structured JSON output envelope (`--json`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DiagnosticEnvelope {
    /// `true` when the command succeeded with zero errors.
    pub ok: bool,
    /// Optional failure class (`"usage"`, `"precondition"`, `"sandbox"`, `"internal"`) when
    /// the command aborted before completing domain validation.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    /// Number of error-level findings.
    pub errors: usize,
    /// Number of warning-level findings.
    pub warnings: usize,
    /// Ordered list of diagnostic findings.
    pub findings: Vec<Finding>,
    /// Additional subcommand-specific payload fields (`files`, `roots`, `specs`, etc.).
    #[serde(flatten)]
    pub extra: serde_json::Map<String, serde_json::Value>,
}

/// Type alias for [`DiagnosticEnvelope`].
pub type JsonEnvelope = DiagnosticEnvelope;

impl DiagnosticEnvelope {
    /// Builds a [`DiagnosticEnvelope`] from a list of findings.
    #[must_use]
    pub fn from_findings(findings: Vec<Finding>) -> Self {
        let errors = findings.iter().filter(|f| f.level == Level::Error).count();
        let warnings = findings
            .iter()
            .filter(|f| f.level == Level::Warning)
            .count();
        Self {
            ok: errors == 0,
            error: None,
            errors,
            warnings,
            findings,
            extra: serde_json::Map::new(),
        }
    }

    /// Builds a CLI usage error envelope (`exit 2`).
    #[must_use]
    pub fn usage_error(code: impl Into<String>, message: impl Into<String>) -> Self {
        let finding = Finding::error(code, "", 0, 0, message);
        Self {
            ok: false,
            error: Some("usage".to_string()),
            errors: 1,
            warnings: 0,
            findings: vec![finding],
            extra: serde_json::Map::new(),
        }
    }

    /// Builds a sandbox/environment/precondition error envelope (`exit 3`).
    #[must_use]
    pub fn sandbox_error(code: impl Into<String>, message: impl Into<String>) -> Self {
        let finding = Finding::error(code, "", 0, 0, message);
        Self {
            ok: false,
            error: Some("precondition".to_string()),
            errors: 1,
            warnings: 0,
            findings: vec![finding],
            extra: serde_json::Map::new(),
        }
    }

    /// Inserts an extra top-level JSON key-value pair into the envelope.
    #[must_use]
    pub fn with_field(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.extra.insert(key.into(), value);
        self
    }

    /// Determines the [`ExitCode`] corresponding to this envelope.
    #[must_use]
    pub fn exit_code(&self) -> ExitCode {
        match self.error.as_deref() {
            Some("usage") => ExitCode::UsageError,
            Some("precondition" | "sandbox" | "environment") => ExitCode::SandboxError,
            Some(_) => ExitCode::DomainFailure,
            None => {
                if self.ok && self.errors == 0 {
                    ExitCode::Pass
                } else {
                    ExitCode::DomainFailure
                }
            }
        }
    }

    /// Serializes the envelope as a single-line JSON string.
    #[must_use]
    pub fn to_json_string(&self) -> String {
        serde_json::to_string(self).expect("DiagnosticEnvelope serialization cannot fail")
    }

    /// Serializes the envelope as a pretty-printed JSON string.
    #[must_use]
    pub fn to_json_pretty(&self) -> String {
        serde_json::to_string_pretty(self).expect("DiagnosticEnvelope serialization cannot fail")
    }
}

#[inline]
fn range_contains(ranges: &[(u32, u32)], cp: u32) -> bool {
    ranges
        .binary_search_by(|&(start, end)| {
            if cp < start {
                Ordering::Greater
            } else if cp > end {
                Ordering::Less
            } else {
                Ordering::Equal
            }
        })
        .is_ok()
}

/// Returns `true` if `ch` is in Unicode categories `Cc`, `Cf`, `Zl`, `Zp`, `Co`, `Cs`, or `Cn`
/// (`NAME_CATEGORIES` in `textnames.py`).
#[must_use]
pub fn is_name_refused_char(ch: char) -> bool {
    range_contains(NAME_CATEGORY_RANGES, ch as u32)
}

/// Returns `true` if `ch` is in Unicode category `Zs` (`Separator, Space`).
#[must_use]
pub const fn is_space_separator_char(ch: char) -> bool {
    matches!(
        ch as u32,
        0x0020 | 0x00A0 | 0x1680 | 0x2000..=0x200A | 0x202F | 0x205F | 0x3000
    )
}

/// Default-ignorable and blank-looking code points outside `Cc`/`Cf`/`Zs` refused by `specload.py`.
const YAML_EXTRA_REFUSED_RANGES: &[(u32, u32)] = &[
    (0x034F, 0x034F), // COMBINING GRAPHEME JOINER (Mn)
    (0x115F, 0x1160), // HANGUL CHOSEONG/JUNGSEONG FILLER (Lo)
    (0x17B4, 0x17B5), // KHMER VOWEL INHERENT AQ/AA (Mn)
    (0x180B, 0x180F), // MONGOLIAN FREE VARIATION SELECTORS (Mn)
    (0x2065, 0x2065), // unassigned in Default_Ignorable_Code_Point range
    (0x2800, 0x2800), // BRAILLE PATTERN BLANK (So)
    (0x3164, 0x3164), // HANGUL FILLER (Lo)
    (0xFE00, 0xFE0F), // VARIATION SELECTOR-1..16 (Mn)
    (0xFFA0, 0xFFA0), // HALFWIDTH HANGUL FILLER (Lo)
    (0xFFF0, 0xFFF8), // unassigned specials block
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF), // tags and variation selectors supplement (Cf/Mn/Cn)
];

/// Returns `true` if `ch` is refused by strict YAML 1.2 checking (`specload.py:is_refused`).
/// Note: callers that allow `' '`, `'\n'`, or `'\t'` check those before calling this function.
#[must_use]
pub fn is_yaml_refused_char(ch: char) -> bool {
    is_name_refused_char(ch)
        || is_space_separator_char(ch)
        || range_contains(YAML_EXTRA_REFUSED_RANGES, ch as u32)
}

/// Formats a refused character as `U+XXXX (<description>)` matching `specload.py:char_label`.
#[must_use]
pub fn char_label(ch: char) -> String {
    let cp = ch as u32;
    let desc = match cp {
        0x0000 => "NULL",
        0x0007 => "BELL",
        0x0008 => "BACKSPACE",
        0x0009 => "CHARACTER TABULATION",
        0x000A => "LINE FEED",
        0x000B => "LINE TABULATION",
        0x000C => "FORM FEED",
        0x000D => "CARRIAGE RETURN",
        0x001B => "ESCAPE",
        0x007F => "DELETE",
        0x00A0 => "NO-BREAK SPACE",
        0x00AD => "SOFT HYPHEN",
        0x034F => "COMBINING GRAPHEME JOINER",
        0x061C => "ARABIC LETTER MARK",
        0x115F => "HANGUL CHOSEONG FILLER",
        0x1160 => "HANGUL JUNGSEONG FILLER",
        0x1680 => "OGHAM SPACE MARK",
        0x17B4 => "KHMER VOWEL INHERENT AQ",
        0x17B5 => "KHMER VOWEL INHERENT AA",
        0x180E => "MONGOLIAN VOWEL SEPARATOR",
        0x2000..=0x200A => "SPACE SEPARATOR",
        0x200B => "ZERO WIDTH SPACE",
        0x200C => "ZERO WIDTH NON-JOINER",
        0x200D => "ZERO WIDTH JOINER",
        0x200E => "LEFT-TO-RIGHT MARK",
        0x200F => "RIGHT-TO-LEFT MARK",
        0x2028 => "LINE SEPARATOR",
        0x2029 => "PARAGRAPH SEPARATOR",
        0x202A => "LEFT-TO-RIGHT EMBEDDING",
        0x202B => "RIGHT-TO-LEFT EMBEDDING",
        0x202C => "POP DIRECTIONAL FORMATTING",
        0x202D => "LEFT-TO-RIGHT OVERRIDE",
        0x202E => "RIGHT-TO-LEFT OVERRIDE",
        0x202F => "NARROW NO-BREAK SPACE",
        0x205F => "MEDIUM MATHEMATICAL SPACE",
        0x2060 => "WORD JOINER",
        0x2066 => "LEFT-TO-RIGHT ISOLATE",
        0x2067 => "RIGHT-TO-LEFT ISOLATE",
        0x2068 => "FIRST STRONG ISOLATE",
        0x2069 => "POP DIRECTIONAL ISOLATE",
        0x2800 => "BRAILLE PATTERN BLANK",
        0x3000 => "IDEOGRAPHIC SPACE",
        0x3164 => "HANGUL FILLER",
        0xFE00..=0xFE0F => "VARIATION SELECTOR",
        0xFEFF => "ZERO WIDTH NO-BREAK SPACE",
        0xFFA0 => "HALFWIDTH HANGUL FILLER",
        0xFFF9..=0xFFFB => "ANNOTATION CONTROL",
        0xE000..=0xF8FF | 0xF0000..=0xFFFFD | 0x100000..=0x10FFFD => "Co",
        _ => "control or format character",
    };
    format!("U+{cp:04X} ({desc})")
}

/// Escapes control, format, and non-standard characters in `text` for safe terminal and
/// Markdown/HTML diagnostic output (port of `textnames.py:visible_name`).
#[must_use]
pub fn visible_name(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for ch in text.chars() {
        match ch {
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if is_name_refused_char(c) => {
                let cp = c as u32;
                if cp < 0x100 {
                    out.push_str(&format!("\\x{cp:02x}"));
                } else if cp < 0x10000 {
                    out.push_str(&format!("\\u{cp:04x}"));
                } else {
                    out.push_str(&format!("\\U{cp:08x}"));
                }
            }
            c => out.push(c),
        }
    }
    out
}

/// Returns `true` if the final path component of `path` contains any character in
/// `NAME_CATEGORIES` (`textnames.py:bad_file_name`).
#[must_use]
pub fn bad_file_name(path: &Path) -> bool {
    let name = path
        .file_name()
        .map(|s| s.to_string_lossy())
        .unwrap_or_else(|| path.to_string_lossy());
    name.chars().any(is_name_refused_char)
}

#[rustfmt::skip]
pub(crate) const NAME_CATEGORY_RANGES: &[(u32, u32)] = &[
    (0x0000, 0x001F), (0x007F, 0x009F), (0x00AD, 0x00AD), (0x0378, 0x0379),
    (0x0380, 0x0383), (0x038B, 0x038B), (0x038D, 0x038D), (0x03A2, 0x03A2),
    (0x0530, 0x0530), (0x0557, 0x0558), (0x058B, 0x058C), (0x0590, 0x0590),
    (0x05C8, 0x05CF), (0x05EB, 0x05EE), (0x05F5, 0x0605), (0x061C, 0x061C),
    (0x06DD, 0x06DD), (0x070E, 0x070F), (0x074B, 0x074C), (0x07B2, 0x07BF),
    (0x07FB, 0x07FC), (0x082E, 0x082F), (0x083F, 0x083F), (0x085C, 0x085D),
    (0x085F, 0x085F), (0x086B, 0x086F), (0x088F, 0x0897), (0x08E2, 0x08E2),
    (0x0984, 0x0984), (0x098D, 0x098E), (0x0991, 0x0992), (0x09A9, 0x09A9),
    (0x09B1, 0x09B1), (0x09B3, 0x09B5), (0x09BA, 0x09BB), (0x09C5, 0x09C6),
    (0x09C9, 0x09CA), (0x09CF, 0x09D6), (0x09D8, 0x09DB), (0x09DE, 0x09DE),
    (0x09E4, 0x09E5), (0x09FF, 0x0A00), (0x0A04, 0x0A04), (0x0A0B, 0x0A0E),
    (0x0A11, 0x0A12), (0x0A29, 0x0A29), (0x0A31, 0x0A31), (0x0A34, 0x0A34),
    (0x0A37, 0x0A37), (0x0A3A, 0x0A3B), (0x0A3D, 0x0A3D), (0x0A43, 0x0A46),
    (0x0A49, 0x0A4A), (0x0A4E, 0x0A50), (0x0A52, 0x0A58), (0x0A5D, 0x0A5D),
    (0x0A5F, 0x0A65), (0x0A77, 0x0A80), (0x0A84, 0x0A84), (0x0A8E, 0x0A8E),
    (0x0A92, 0x0A92), (0x0AA9, 0x0AA9), (0x0AB1, 0x0AB1), (0x0AB4, 0x0AB4),
    (0x0ABA, 0x0ABB), (0x0AC6, 0x0AC6), (0x0ACA, 0x0ACA), (0x0ACE, 0x0ACF),
    (0x0AD1, 0x0ADF), (0x0AE4, 0x0AE5), (0x0AF2, 0x0AF8), (0x0B00, 0x0B00),
    (0x0B04, 0x0B04), (0x0B0D, 0x0B0E), (0x0B11, 0x0B12), (0x0B29, 0x0B29),
    (0x0B31, 0x0B31), (0x0B34, 0x0B34), (0x0B3A, 0x0B3B), (0x0B45, 0x0B46),
    (0x0B49, 0x0B4A), (0x0B4E, 0x0B54), (0x0B58, 0x0B5B), (0x0B5E, 0x0B5E),
    (0x0B64, 0x0B65), (0x0B78, 0x0B81), (0x0B84, 0x0B84), (0x0B8B, 0x0B8D),
    (0x0B91, 0x0B91), (0x0B96, 0x0B98), (0x0B9B, 0x0B9B), (0x0B9D, 0x0B9D),
    (0x0BA0, 0x0BA2), (0x0BA5, 0x0BA7), (0x0BAB, 0x0BAD), (0x0BBA, 0x0BBD),
    (0x0BC3, 0x0BC5), (0x0BC9, 0x0BC9), (0x0BCE, 0x0BCF), (0x0BD1, 0x0BD6),
    (0x0BD8, 0x0BE5), (0x0BFB, 0x0BFF), (0x0C0D, 0x0C0D), (0x0C11, 0x0C11),
    (0x0C29, 0x0C29), (0x0C3A, 0x0C3B), (0x0C45, 0x0C45), (0x0C49, 0x0C49),
    (0x0C4E, 0x0C54), (0x0C57, 0x0C57), (0x0C5B, 0x0C5C), (0x0C5E, 0x0C5F),
    (0x0C64, 0x0C65), (0x0C70, 0x0C76), (0x0C8D, 0x0C8D), (0x0C91, 0x0C91),
    (0x0CA9, 0x0CA9), (0x0CB4, 0x0CB4), (0x0CBA, 0x0CBB), (0x0CC5, 0x0CC5),
    (0x0CC9, 0x0CC9), (0x0CCE, 0x0CD4), (0x0CD7, 0x0CDC), (0x0CDF, 0x0CDF),
    (0x0CE4, 0x0CE5), (0x0CF0, 0x0CF0), (0x0CF4, 0x0CFF), (0x0D0D, 0x0D0D),
    (0x0D11, 0x0D11), (0x0D45, 0x0D45), (0x0D49, 0x0D49), (0x0D50, 0x0D53),
    (0x0D64, 0x0D65), (0x0D80, 0x0D80), (0x0D84, 0x0D84), (0x0D97, 0x0D99),
    (0x0DB2, 0x0DB2), (0x0DBC, 0x0DBC), (0x0DBE, 0x0DBF), (0x0DC7, 0x0DC9),
    (0x0DCB, 0x0DCE), (0x0DD5, 0x0DD5), (0x0DD7, 0x0DD7), (0x0DE0, 0x0DE5),
    (0x0DF0, 0x0DF1), (0x0DF5, 0x0E00), (0x0E3B, 0x0E3E), (0x0E5C, 0x0E80),
    (0x0E83, 0x0E83), (0x0E85, 0x0E85), (0x0E8B, 0x0E8B), (0x0EA4, 0x0EA4),
    (0x0EA6, 0x0EA6), (0x0EBE, 0x0EBF), (0x0EC5, 0x0EC5), (0x0EC7, 0x0EC7),
    (0x0ECF, 0x0ECF), (0x0EDA, 0x0EDB), (0x0EE0, 0x0EFF), (0x0F48, 0x0F48),
    (0x0F6D, 0x0F70), (0x0F98, 0x0F98), (0x0FBD, 0x0FBD), (0x0FCD, 0x0FCD),
    (0x0FDB, 0x0FFF), (0x10C6, 0x10C6), (0x10C8, 0x10CC), (0x10CE, 0x10CF),
    (0x1249, 0x1249), (0x124E, 0x124F), (0x1257, 0x1257), (0x1259, 0x1259),
    (0x125E, 0x125F), (0x1289, 0x1289), (0x128E, 0x128F), (0x12B1, 0x12B1),
    (0x12B6, 0x12B7), (0x12BF, 0x12BF), (0x12C1, 0x12C1), (0x12C6, 0x12C7),
    (0x12D7, 0x12D7), (0x1311, 0x1311), (0x1316, 0x1317), (0x135B, 0x135C),
    (0x137D, 0x137F), (0x139A, 0x139F), (0x13F6, 0x13F7), (0x13FE, 0x13FF),
    (0x169D, 0x169F), (0x16F9, 0x16FF), (0x1716, 0x171E), (0x1737, 0x173F),
    (0x1754, 0x175F), (0x176D, 0x176D), (0x1771, 0x1771), (0x1774, 0x177F),
    (0x17DE, 0x17DF), (0x17EA, 0x17EF), (0x17FA, 0x17FF), (0x180E, 0x180E),
    (0x181A, 0x181F), (0x1879, 0x187F), (0x18AB, 0x18AF), (0x18F6, 0x18FF),
    (0x191F, 0x191F), (0x192C, 0x192F), (0x193C, 0x193F), (0x1941, 0x1943),
    (0x196E, 0x196F), (0x1975, 0x197F), (0x19AC, 0x19AF), (0x19CA, 0x19CF),
    (0x19DB, 0x19DD), (0x1A1C, 0x1A1D), (0x1A5F, 0x1A5F), (0x1A7D, 0x1A7E),
    (0x1A8A, 0x1A8F), (0x1A9A, 0x1A9F), (0x1AAE, 0x1AAF), (0x1ACF, 0x1AFF),
    (0x1B4D, 0x1B4F), (0x1B7F, 0x1B7F), (0x1BF4, 0x1BFB), (0x1C38, 0x1C3A),
    (0x1C4A, 0x1C4C), (0x1C89, 0x1C8F), (0x1CBB, 0x1CBC), (0x1CC8, 0x1CCF),
    (0x1CFB, 0x1CFF), (0x1F16, 0x1F17), (0x1F1E, 0x1F1F), (0x1F46, 0x1F47),
    (0x1F4E, 0x1F4F), (0x1F58, 0x1F58), (0x1F5A, 0x1F5A), (0x1F5C, 0x1F5C),
    (0x1F5E, 0x1F5E), (0x1F7E, 0x1F7F), (0x1FB5, 0x1FB5), (0x1FC5, 0x1FC5),
    (0x1FD4, 0x1FD5), (0x1FDC, 0x1FDC), (0x1FF0, 0x1FF1), (0x1FF5, 0x1FF5),
    (0x1FFF, 0x1FFF), (0x200B, 0x200F), (0x2028, 0x202E), (0x2060, 0x206F),
    (0x2072, 0x2073), (0x208F, 0x208F), (0x209D, 0x209F), (0x20C1, 0x20CF),
    (0x20F1, 0x20FF), (0x218C, 0x218F), (0x2427, 0x243F), (0x244B, 0x245F),
    (0x2B74, 0x2B75), (0x2B96, 0x2B96), (0x2CF4, 0x2CF8), (0x2D26, 0x2D26),
    (0x2D28, 0x2D2C), (0x2D2E, 0x2D2F), (0x2D68, 0x2D6E), (0x2D71, 0x2D7E),
    (0x2D97, 0x2D9F), (0x2DA7, 0x2DA7), (0x2DAF, 0x2DAF), (0x2DB7, 0x2DB7),
    (0x2DBF, 0x2DBF), (0x2DC7, 0x2DC7), (0x2DCF, 0x2DCF), (0x2DD7, 0x2DD7),
    (0x2DDF, 0x2DDF), (0x2E5E, 0x2E7F), (0x2E9A, 0x2E9A), (0x2EF4, 0x2EFF),
    (0x2FD6, 0x2FEF), (0x3040, 0x3040), (0x3097, 0x3098), (0x3100, 0x3104),
    (0x3130, 0x3130), (0x318F, 0x318F), (0x31E4, 0x31EE), (0x321F, 0x321F),
    (0xA48D, 0xA48F), (0xA4C7, 0xA4CF), (0xA62C, 0xA63F), (0xA6F8, 0xA6FF),
    (0xA7CB, 0xA7CF), (0xA7D2, 0xA7D2), (0xA7D4, 0xA7D4), (0xA7DA, 0xA7F1),
    (0xA82D, 0xA82F), (0xA83A, 0xA83F), (0xA878, 0xA87F), (0xA8C6, 0xA8CD),
    (0xA8DA, 0xA8DF), (0xA954, 0xA95E), (0xA97D, 0xA97F), (0xA9CE, 0xA9CE),
    (0xA9DA, 0xA9DD), (0xA9FF, 0xA9FF), (0xAA37, 0xAA3F), (0xAA4E, 0xAA4F),
    (0xAA5A, 0xAA5B), (0xAAC3, 0xAADA), (0xAAF7, 0xAB00), (0xAB07, 0xAB08),
    (0xAB0F, 0xAB10), (0xAB17, 0xAB1F), (0xAB27, 0xAB27), (0xAB2F, 0xAB2F),
    (0xAB6C, 0xAB6F), (0xABEE, 0xABEF), (0xABFA, 0xABFF), (0xD7A4, 0xD7AF),
    (0xD7C7, 0xD7CA), (0xD7FC, 0xF8FF), (0xFA6E, 0xFA6F), (0xFADA, 0xFAFF),
    (0xFB07, 0xFB12), (0xFB18, 0xFB1C), (0xFB37, 0xFB37), (0xFB3D, 0xFB3D),
    (0xFB3F, 0xFB3F), (0xFB42, 0xFB42), (0xFB45, 0xFB45), (0xFBC3, 0xFBD2),
    (0xFD90, 0xFD91), (0xFDC8, 0xFDCE), (0xFDD0, 0xFDEF), (0xFE1A, 0xFE1F),
    (0xFE53, 0xFE53), (0xFE67, 0xFE67), (0xFE6C, 0xFE6F), (0xFE75, 0xFE75),
    (0xFEFD, 0xFF00), (0xFFBF, 0xFFC1), (0xFFC8, 0xFFC9), (0xFFD0, 0xFFD1),
    (0xFFD8, 0xFFD9), (0xFFDD, 0xFFDF), (0xFFE7, 0xFFE7), (0xFFEF, 0xFFFB),
    (0xFFFE, 0xFFFF), (0x1000C, 0x1000C), (0x10027, 0x10027), (0x1003B, 0x1003B),
    (0x1003E, 0x1003E), (0x1004E, 0x1004F), (0x1005E, 0x1007F), (0x100FB, 0x100FF),
    (0x10103, 0x10106), (0x10134, 0x10136), (0x1018F, 0x1018F), (0x1019D, 0x1019F),
    (0x101A1, 0x101CF), (0x101FE, 0x1027F), (0x1029D, 0x1029F), (0x102D1, 0x102DF),
    (0x102FC, 0x102FF), (0x10324, 0x1032C), (0x1034B, 0x1034F), (0x1037B, 0x1037F),
    (0x1039E, 0x1039E), (0x103C4, 0x103C7), (0x103D6, 0x103FF), (0x1049E, 0x1049F),
    (0x104AA, 0x104AF), (0x104D4, 0x104D7), (0x104FC, 0x104FF), (0x10528, 0x1052F),
    (0x10564, 0x1056E), (0x1057B, 0x1057B), (0x1058B, 0x1058B), (0x10593, 0x10593),
    (0x10596, 0x10596), (0x105A2, 0x105A2), (0x105B2, 0x105B2), (0x105BA, 0x105BA),
    (0x105BD, 0x105FF), (0x10737, 0x1073F), (0x10756, 0x1075F), (0x10768, 0x1077F),
    (0x10786, 0x10786), (0x107B1, 0x107B1), (0x107BB, 0x107FF), (0x10806, 0x10807),
    (0x10809, 0x10809), (0x10836, 0x10836), (0x10839, 0x1083B), (0x1083D, 0x1083E),
    (0x10856, 0x10856), (0x1089F, 0x108A6), (0x108B0, 0x108DF), (0x108F3, 0x108F3),
    (0x108F6, 0x108FA), (0x1091C, 0x1091E), (0x1093A, 0x1093E), (0x10940, 0x1097F),
    (0x109B8, 0x109BB), (0x109D0, 0x109D1), (0x10A04, 0x10A04), (0x10A07, 0x10A0B),
    (0x10A14, 0x10A14), (0x10A18, 0x10A18), (0x10A36, 0x10A37), (0x10A3B, 0x10A3E),
    (0x10A49, 0x10A4F), (0x10A59, 0x10A5F), (0x10AA0, 0x10ABF), (0x10AE7, 0x10AEA),
    (0x10AF7, 0x10AFF), (0x10B36, 0x10B38), (0x10B56, 0x10B57), (0x10B73, 0x10B77),
    (0x10B92, 0x10B98), (0x10B9D, 0x10BA8), (0x10BB0, 0x10BFF), (0x10C49, 0x10C7F),
    (0x10CB3, 0x10CBF), (0x10CF3, 0x10CF9), (0x10D28, 0x10D2F), (0x10D3A, 0x10E5F),
    (0x10E7F, 0x10E7F), (0x10EAA, 0x10EAA), (0x10EAE, 0x10EAF), (0x10EB2, 0x10EFC),
    (0x10F28, 0x10F2F), (0x10F5A, 0x10F6F), (0x10F8A, 0x10FAF), (0x10FCC, 0x10FDF),
    (0x10FF7, 0x10FFF), (0x1104E, 0x11051), (0x11076, 0x1107E), (0x110BD, 0x110BD),
    (0x110C3, 0x110CF), (0x110E9, 0x110EF), (0x110FA, 0x110FF), (0x11135, 0x11135),
    (0x11148, 0x1114F), (0x11177, 0x1117F), (0x111E0, 0x111E0), (0x111F5, 0x111FF),
    (0x11212, 0x11212), (0x11242, 0x1127F), (0x11287, 0x11287), (0x11289, 0x11289),
    (0x1128E, 0x1128E), (0x1129E, 0x1129E), (0x112AA, 0x112AF), (0x112EB, 0x112EF),
    (0x112FA, 0x112FF), (0x11304, 0x11304), (0x1130D, 0x1130E), (0x11311, 0x11312),
    (0x11329, 0x11329), (0x11331, 0x11331), (0x11334, 0x11334), (0x1133A, 0x1133A),
    (0x11345, 0x11346), (0x11349, 0x1134A), (0x1134E, 0x1134F), (0x11351, 0x11356),
    (0x11358, 0x1135C), (0x11364, 0x11365), (0x1136D, 0x1136F), (0x11375, 0x113FF),
    (0x1145C, 0x1145C), (0x11462, 0x1147F), (0x114C8, 0x114CF), (0x114DA, 0x1157F),
    (0x115B6, 0x115B7), (0x115DE, 0x115FF), (0x11645, 0x1164F), (0x1165A, 0x1165F),
    (0x1166D, 0x1167F), (0x116BA, 0x116BF), (0x116CA, 0x116FF), (0x1171B, 0x1171C),
    (0x1172C, 0x1172F), (0x11747, 0x117FF), (0x1183C, 0x1189F), (0x118F3, 0x118FE),
    (0x11907, 0x11908), (0x1190A, 0x1190B), (0x11914, 0x11914), (0x11917, 0x11917),
    (0x11936, 0x11936), (0x11939, 0x1193A), (0x11947, 0x1194F), (0x1195A, 0x1199F),
    (0x119A8, 0x119A9), (0x119D8, 0x119D9), (0x119E5, 0x119FF), (0x11A48, 0x11A4F),
    (0x11AA3, 0x11AAF), (0x11AF9, 0x11AFF), (0x11B0A, 0x11BFF), (0x11C09, 0x11C09),
    (0x11C37, 0x11C37), (0x11C46, 0x11C4F), (0x11C6D, 0x11C6F), (0x11C90, 0x11C91),
    (0x11CA8, 0x11CA8), (0x11CB7, 0x11CFF), (0x11D07, 0x11D07), (0x11D0A, 0x11D0A),
    (0x11D37, 0x11D39), (0x11D3B, 0x11D3B), (0x11D3E, 0x11D3E), (0x11D48, 0x11D4F),
    (0x11D5A, 0x11D5F), (0x11D66, 0x11D66), (0x11D69, 0x11D69), (0x11D8F, 0x11D8F),
    (0x11D92, 0x11D92), (0x11D99, 0x11D9F), (0x11DAA, 0x11EDF), (0x11EF9, 0x11EFF),
    (0x11F11, 0x11F11), (0x11F3B, 0x11F3D), (0x11F5A, 0x11FAF), (0x11FB1, 0x11FBF),
    (0x11FF2, 0x11FFE), (0x1239A, 0x123FF), (0x1246F, 0x1246F), (0x12475, 0x1247F),
    (0x12544, 0x12F8F), (0x12FF3, 0x12FFF), (0x13430, 0x1343F), (0x13456, 0x143FF),
    (0x14647, 0x167FF), (0x16A39, 0x16A3F), (0x16A5F, 0x16A5F), (0x16A6A, 0x16A6D),
    (0x16ABF, 0x16ABF), (0x16ACA, 0x16ACF), (0x16AEE, 0x16AEF), (0x16AF6, 0x16AFF),
    (0x16B46, 0x16B4F), (0x16B5A, 0x16B5A), (0x16B62, 0x16B62), (0x16B78, 0x16B7C),
    (0x16B90, 0x16E3F), (0x16E9B, 0x16EFF), (0x16F4B, 0x16F4E), (0x16F88, 0x16F8E),
    (0x16FA0, 0x16FDF), (0x16FE5, 0x16FEF), (0x16FF2, 0x16FFF), (0x187F8, 0x187FF),
    (0x18CD6, 0x18CFF), (0x18D09, 0x1AFEF), (0x1AFF4, 0x1AFF4), (0x1AFFC, 0x1AFFC),
    (0x1AFFF, 0x1AFFF), (0x1B123, 0x1B131), (0x1B133, 0x1B14F), (0x1B153, 0x1B154),
    (0x1B156, 0x1B163), (0x1B168, 0x1B16F), (0x1B2FC, 0x1BBFF), (0x1BC6B, 0x1BC6F),
    (0x1BC7D, 0x1BC7F), (0x1BC89, 0x1BC8F), (0x1BC9A, 0x1BC9B), (0x1BCA0, 0x1CEFF),
    (0x1CF2E, 0x1CF2F), (0x1CF47, 0x1CF4F), (0x1CFC4, 0x1CFFF), (0x1D0F6, 0x1D0FF),
    (0x1D127, 0x1D128), (0x1D173, 0x1D17A), (0x1D1EB, 0x1D1FF), (0x1D246, 0x1D2BF),
    (0x1D2D4, 0x1D2DF), (0x1D2F4, 0x1D2FF), (0x1D357, 0x1D35F), (0x1D379, 0x1D3FF),
    (0x1D455, 0x1D455), (0x1D49D, 0x1D49D), (0x1D4A0, 0x1D4A1), (0x1D4A3, 0x1D4A4),
    (0x1D4A7, 0x1D4A8), (0x1D4AD, 0x1D4AD), (0x1D4BA, 0x1D4BA), (0x1D4BC, 0x1D4BC),
    (0x1D4C4, 0x1D4C4), (0x1D506, 0x1D506), (0x1D50B, 0x1D50C), (0x1D515, 0x1D515),
    (0x1D51D, 0x1D51D), (0x1D53A, 0x1D53A), (0x1D53F, 0x1D53F), (0x1D545, 0x1D545),
    (0x1D547, 0x1D549), (0x1D551, 0x1D551), (0x1D6A6, 0x1D6A7), (0x1D7CC, 0x1D7CD),
    (0x1DA8C, 0x1DA9A), (0x1DAA0, 0x1DAA0), (0x1DAB0, 0x1DEFF), (0x1DF1F, 0x1DF24),
    (0x1DF2B, 0x1DFFF), (0x1E007, 0x1E007), (0x1E019, 0x1E01A), (0x1E022, 0x1E022),
    (0x1E025, 0x1E025), (0x1E02B, 0x1E02F), (0x1E06E, 0x1E08E), (0x1E090, 0x1E0FF),
    (0x1E12D, 0x1E12F), (0x1E13E, 0x1E13F), (0x1E14A, 0x1E14D), (0x1E150, 0x1E28F),
    (0x1E2AF, 0x1E2BF), (0x1E2FA, 0x1E2FE), (0x1E300, 0x1E4CF), (0x1E4FA, 0x1E7DF),
    (0x1E7E7, 0x1E7E7), (0x1E7EC, 0x1E7EC), (0x1E7EF, 0x1E7EF), (0x1E7FF, 0x1E7FF),
    (0x1E8C5, 0x1E8C6), (0x1E8D7, 0x1E8FF), (0x1E94C, 0x1E94F), (0x1E95A, 0x1E95D),
    (0x1E960, 0x1EC70), (0x1ECB5, 0x1ED00), (0x1ED3E, 0x1EDFF), (0x1EE04, 0x1EE04),
    (0x1EE20, 0x1EE20), (0x1EE23, 0x1EE23), (0x1EE25, 0x1EE26), (0x1EE28, 0x1EE28),
    (0x1EE33, 0x1EE33), (0x1EE38, 0x1EE38), (0x1EE3A, 0x1EE3A), (0x1EE3C, 0x1EE41),
    (0x1EE43, 0x1EE46), (0x1EE48, 0x1EE48), (0x1EE4A, 0x1EE4A), (0x1EE4C, 0x1EE4C),
    (0x1EE50, 0x1EE50), (0x1EE53, 0x1EE53), (0x1EE55, 0x1EE56), (0x1EE58, 0x1EE58),
    (0x1EE5A, 0x1EE5A), (0x1EE5C, 0x1EE5C), (0x1EE5E, 0x1EE5E), (0x1EE60, 0x1EE60),
    (0x1EE63, 0x1EE63), (0x1EE65, 0x1EE66), (0x1EE6B, 0x1EE6B), (0x1EE73, 0x1EE73),
    (0x1EE78, 0x1EE78), (0x1EE7D, 0x1EE7D), (0x1EE7F, 0x1EE7F), (0x1EE8A, 0x1EE8A),
    (0x1EE9C, 0x1EEA0), (0x1EEA4, 0x1EEA4), (0x1EEAA, 0x1EEAA), (0x1EEBC, 0x1EEEF),
    (0x1EEF2, 0x1EFFF), (0x1F02C, 0x1F02F), (0x1F094, 0x1F09F), (0x1F0AF, 0x1F0B0),
    (0x1F0C0, 0x1F0C0), (0x1F0D0, 0x1F0D0), (0x1F0F6, 0x1F0FF), (0x1F1AE, 0x1F1E5),
    (0x1F203, 0x1F20F), (0x1F23C, 0x1F23F), (0x1F249, 0x1F24F), (0x1F252, 0x1F25F),
    (0x1F266, 0x1F2FF), (0x1F6D8, 0x1F6DB), (0x1F6ED, 0x1F6EF), (0x1F6FD, 0x1F6FF),
    (0x1F777, 0x1F77A), (0x1F7DA, 0x1F7DF), (0x1F7EC, 0x1F7EF), (0x1F7F1, 0x1F7FF),
    (0x1F80C, 0x1F80F), (0x1F848, 0x1F84F), (0x1F85A, 0x1F85F), (0x1F888, 0x1F88F),
    (0x1F8AE, 0x1F8AF), (0x1F8B2, 0x1F8FF), (0x1FA54, 0x1FA5F), (0x1FA6E, 0x1FA6F),
    (0x1FA7D, 0x1FA7F), (0x1FA89, 0x1FA8F), (0x1FABE, 0x1FABE), (0x1FAC6, 0x1FACD),
    (0x1FADC, 0x1FADF), (0x1FAE9, 0x1FAEF), (0x1FAF9, 0x1FAFF), (0x1FB93, 0x1FB93),
    (0x1FBCB, 0x1FBEF), (0x1FBFA, 0x1FFFF), (0x2A6E0, 0x2A6FF), (0x2B73A, 0x2B73F),
    (0x2B81E, 0x2B81F), (0x2CEA2, 0x2CEAF), (0x2EBE1, 0x2EBEF), (0x2EE5E, 0x2F7FF),
    (0x2FA1E, 0x2FFFF), (0x3134B, 0x3134F), (0x323B0, 0xE00FF), (0xE01F0, 0x10FFFF),
];
