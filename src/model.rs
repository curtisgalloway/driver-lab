// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Typed data structures and constants for Format 2 hardware specifications (`RT-2`).
//!
//! Covers schema kinds (`root`, `corpus`, `index`, `verify`, `spec`), document classes
//! (`BF-IMX-14`: `databook`, `datasheet`, `errata`, `appnote`, `standard`, `doc`),
//! spec kinds, support classes, authority labels, fact categories, verification verdicts,
//! and JSON path formatting (`_where` in `spec.py`).

use crate::yaml_strict::PathSegment;
use serde::{Deserialize, Serialize};
use std::fmt;
use std::path::Path;

/// Alias for [`PathSegment`] used in path formatting.
pub type PathElem = PathSegment;

/// Base URI for embedded Format 2 JSON Schemas.
pub const SCHEMA_BASE: &str = "https://github.com/curtisgalloway/driver-lab/spec-format/2/";

/// URN for the `source-observed` support extension schema fragment (D15).
pub const EXTENSION_URN: &str = "urn:driver-lab:spec-format:2:extension:source-observed";

/// Root marker file name (`board-specs.yaml`).
pub const MARKER: &str = "board-specs.yaml";

/// Corpus ledger file name (`corpus.yaml`).
pub const CORPUS: &str = "corpus.yaml";

/// Which embedded JSON Schema applies to a file based on its file name (`spec.py:schema_kind`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SchemaKind {
    /// `*.spec.yaml` and `*.facts.yaml` (`spec.schema.json`).
    Spec,
    /// `board-specs.yaml` (`root.schema.json`).
    Root,
    /// `*.verify.yaml` (`verify.schema.json`).
    Verify,
    /// `corpus.yaml` (`corpus.schema.json`).
    Corpus,
    /// `*.index.yaml` (`index.schema.json`).
    Index,
}

impl SchemaKind {
    /// Canonical lowercase schema name (`"spec"`, `"root"`, `"verify"`, `"corpus"`, `"index"`).
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Spec => "spec",
            Self::Root => "root",
            Self::Verify => "verify",
            Self::Corpus => "corpus",
            Self::Index => "index",
        }
    }

    /// All five Format 2 schema kinds.
    pub const ALL: [Self; 5] = [
        Self::Spec,
        Self::Root,
        Self::Verify,
        Self::Corpus,
        Self::Index,
    ];
}

impl fmt::Display for SchemaKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Determines which [`SchemaKind`] applies to `path` based on its file name (`spec.py:schema_kind`).
///
/// # Errors
///
/// Returns the exact usage error message if `path` does not match a known Format 2 file name.
pub fn schema_kind(path: &Path) -> Result<SchemaKind, String> {
    let name = path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or_default();
    if name == MARKER {
        return Ok(SchemaKind::Root);
    }
    if name == CORPUS {
        return Ok(SchemaKind::Corpus);
    }
    if name.ends_with(".index.yaml") {
        return Ok(SchemaKind::Index);
    }
    if name.ends_with(".verify.yaml") {
        return Ok(SchemaKind::Verify);
    }
    if name.ends_with(".spec.yaml") || name.ends_with(".facts.yaml") {
        return Ok(SchemaKind::Spec);
    }
    Err(format!(
        "{}: cannot tell which schema applies; name the file *.spec.yaml, *.facts.yaml, *.verify.yaml, *.index.yaml, {MARKER} or {CORPUS}",
        path.display()
    ))
}

/// Document class in `resources.documents` (`BF-IMX-14`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum DocumentClass {
    /// Reference manual or TRM (`databook`).
    Databook,
    /// Electrical/device datasheet (`datasheet`, added in `BF-IMX-14`).
    Datasheet,
    /// Silicon errata sheet (`errata`, added in `BF-IMX-14`).
    Errata,
    /// Application note (`appnote`, added in `BF-IMX-14`).
    Appnote,
    /// Architecture or protocol standard (`standard`).
    Standard,
    /// General documentation (`doc`).
    Doc,
}

impl DocumentClass {
    /// Canonical string representation.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Databook => "databook",
            Self::Datasheet => "datasheet",
            Self::Errata => "errata",
            Self::Appnote => "appnote",
            Self::Standard => "standard",
            Self::Doc => "doc",
        }
    }

    /// Parses a document class string.
    #[must_use]
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "databook" => Some(Self::Databook),
            "datasheet" => Some(Self::Datasheet),
            "errata" => Some(Self::Errata),
            "appnote" => Some(Self::Appnote),
            "standard" => Some(Self::Standard),
            "doc" => Some(Self::Doc),
            _ => None,
        }
    }

    /// Returns `true` if this class is an authoritative hardware specification document
    /// (`databook`, `datasheet`, `errata`, `appnote`, or `standard`).
    #[must_use]
    pub const fn is_authoritative_hardware_doc(self) -> bool {
        matches!(
            self,
            Self::Databook | Self::Datasheet | Self::Errata | Self::Appnote | Self::Standard
        )
    }
}

/// Top-level `kind` of a `.spec.yaml` or `.facts.yaml` file.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SpecKind {
    /// Reusable IP block specification (`ip`).
    Ip,
    /// Concrete peripheral specification (`peripheral`).
    Peripheral,
    /// System-on-Chip integration specification (`soc`).
    Soc,
    /// Board-level integration specification (`board`).
    Board,
    /// Investigator fact slice (`facts`).
    Facts,
}

impl SpecKind {
    /// Canonical string representation.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Ip => "ip",
            Self::Peripheral => "peripheral",
            Self::Soc => "soc",
            Self::Board => "board",
            Self::Facts => "facts",
        }
    }
}

/// Root visibility layer (`board-specs.yaml` `layer`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Layer {
    /// Publicly redistributable (`public`).
    Public = 0,
    /// Partner-shared (`partner`).
    Partner = 1,
    /// Confidential/internal (`confidential`).
    Confidential = 2,
}

impl Layer {
    /// Canonical string representation.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Public => "public",
            Self::Partner => "partner",
            Self::Confidential => "confidential",
        }
    }
}

/// Support entry `class` in a fact's `support` list.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum SupportClass {
    /// Cited hardware document (`doc`).
    Doc,
    /// Cited source code observation (`source-observed`).
    SourceObserved,
    /// Direct hardware observation (`hardware`).
    Hardware,
    /// Logical deduction from premises (`deduction`).
    Deduction,
}

impl SupportClass {
    /// Canonical string representation.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Doc => "doc",
            Self::SourceObserved => "source-observed",
            Self::Hardware => "hardware",
            Self::Deduction => "deduction",
        }
    }
}

/// Authority level of a fact (`authority`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Authority {
    /// Backed by an authoritative hardware specification or standard (`authoritative`).
    Authoritative,
    /// Backed by corroborative documentation (`corroborative`).
    Corroborative,
    /// Backed by source or hardware observation (`observed`).
    Observed,
    /// Provisional claim (`provisional`).
    Provisional,
    /// Unverified hypothesis or gap (`hypothesis`).
    Hypothesis,
}

impl Authority {
    /// Canonical string representation.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Authoritative => "authoritative",
            Self::Corroborative => "corroborative",
            Self::Observed => "observed",
            Self::Provisional => "provisional",
            Self::Hypothesis => "hypothesis",
        }
    }
}

/// Verification verdict in `.verify.yaml`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum Verdict {
    /// Verified pass (`PASS`).
    Pass,
    /// Verification failure (`FAIL`).
    Fail,
    /// Acknowledged gap (`GAP`).
    Gap,
    /// Needs human adjudication (`ADJUDICATE`).
    Adjudicate,
}

impl Verdict {
    /// Canonical string representation.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Pass => "PASS",
            Self::Fail => "FAIL",
            Self::Gap => "GAP",
            Self::Adjudicate => "ADJUDICATE",
        }
    }
}

/// Verification freshness status (`records.STATUSES`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum FreshnessStatus {
    /// Basis hash matches current fact and upstream dependencies (`current`).
    Current,
    /// Fact basis hash changed since recorded verdict (`stale`).
    Stale,
    /// Only upstream cross-root facts changed (`upstream-stale`).
    UpstreamStale,
    /// No recorded verdict (`unverified`).
    Unverified,
    /// Basis hash cannot be computed (`unknown`).
    Unknown,
}

impl FreshnessStatus {
    /// Canonical string representation.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Current => "current",
            Self::Stale => "stale",
            Self::UpstreamStale => "upstream-stale",
            Self::Unverified => "unverified",
            Self::Unknown => "unknown",
        }
    }
}

/// Formats a sequence of [`PathElem`] steps into the `spec.py` `_where(path)` string
/// (e.g., `"(top)"`, `"facts[0].id"`, `"resources.documents[1].class"`).
#[must_use]
pub fn format_where(path: &[PathElem]) -> String {
    let mut out = String::new();
    for p in path {
        match p {
            PathElem::Index(idx) => {
                out.push_str(&format!("[{idx}]"));
            }
            PathElem::Key(key) => {
                if !out.is_empty() {
                    out.push('.');
                }
                out.push_str(key);
            }
        }
    }
    if out.is_empty() {
        "(top)".to_string()
    } else {
        out
    }
}

/// Per-file result entry in `validate` output (`{"path", "schema", "valid"}`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ValidatedFileEntry {
    /// File path as given on the command line.
    pub path: String,
    /// Schema kind (`"spec"`, `"root"`, `"verify"`, `"corpus"`, `"index"`).
    pub schema: String,
    /// Whether the file passed YAML and JSON Schema validation.
    pub valid: bool,
}
