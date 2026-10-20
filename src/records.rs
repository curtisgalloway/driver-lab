// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Verification records, canonical `fact-v1` basis and `fact-v1-cycle` hashing,
//! reference extraction, Tarjan SCC DAG fold, and verdict freshness (`records.py`, SF2-3).

use crate::diagnostic::{
    visible_name, Finding, EXIT_DOMAIN_FAILURE, EXIT_OK, EXIT_SANDBOX_ERROR, EXIT_USAGE_ERROR,
};
use crate::spdx::{self, SpdxError};
use crate::yaml_strict::{self, Loaded};
use jsonschema::error::ValidationErrorKind;
use jsonschema::{Retrieve, Uri};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet, VecDeque};
use std::fmt;
use std::hash::Hash;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use unicode_normalization::{is_nfc, UnicodeNormalization};

/// Canonical basis schema tag (`"fact-v1"`).
pub const CANONICAL: &str = "fact-v1";
/// Canonical cycle digest schema tag (`"fact-v1-cycle"`).
pub const CANONICAL_CYCLE: &str = "fact-v1-cycle";
/// Verification record filename suffix (`".verify.yaml"`).
pub const RECORD_SUFFIX: &str = ".verify.yaml";
/// Spec filename suffix (`".spec.yaml"`).
pub const SPEC_SUFFIX: &str = ".spec.yaml";
/// Root marker filename (`"board-specs.yaml"`).
pub const MARKER: &str = "board-specs.yaml";
/// Corpus ledger filename (`"corpus.yaml"`).
pub const CORPUS: &str = "corpus.yaml";

/// Ordered summary keys and their uppercase verdict names (`records.py:SUMMARY`).
pub const SUMMARY: &[(&str, &str)] = &[
    ("pass", "PASS"),
    ("fail", "FAIL"),
    ("unverifiable", "UNVERIFIABLE"),
    ("gap", "GAP"),
    ("adjudicate", "ADJUDICATE"),
];

/// Ordered freshness status strings (`records.py:STATUSES`).
pub const STATUSES: &[&str] = &["current", "stale", "upstream-stale", "unverified", "unknown"];

/// Ordered spec root layers (`speccheck.py:LAYERS`).
pub const LAYERS: &[&str] = &["public", "ip-vendor", "soc-vendor", "product", "local"];

/// Anchored support classes (`speccheck.py:ANCHORED`).
pub const ANCHORED: &[&str] = &["src", "DT", "rtl"];

/// Spec-level registries (`peripheral.py:REGISTRIES`).
pub const REGISTRIES: &[&str] = &[
    "resetTypes",
    "fieldAccessPolicyDefinitions",
    "enumerationDefinitions",
    "registerFiles",
];

/// Returns the human-readable label for a registry group (`peripheral.py:ENTRY_LABEL`).
#[must_use]
pub fn registry_entry_label(group: &str) -> &'static str {
    match group {
        "resetTypes" => "reset type",
        "fieldAccessPolicyDefinitions" => "access policy",
        "enumerationDefinitions" => "enumeration",
        "registerFiles" => "register file",
        _ => "registry entry",
    }
}

/// Returns the closed set of bookkeeping fields excluded from basis hashing for `kind`
/// (`records.py:BOOKKEEPING`).
#[must_use]
pub fn bookkeeping_fields(kind: &str) -> &'static [&'static str] {
    match kind {
        "documents" => &["verified", "fetch", "note"],
        "repos" => &["verified", "fetch", "fetch_via", "note"],
        "files" => &["note", "attribution"],
        "assumptions" => &["todo"],
        "registry" => &["note"],
        _ => &[],
    }
}

/// Verdict freshness status (`records.py:STATUSES`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Freshness {
    /// Verdict basis matches current fact basis (`"current"`).
    #[serde(rename = "current")]
    Current,
    /// Verdict basis differs due to local or returned-home changes (`"stale"`).
    #[serde(rename = "stale")]
    Stale,
    /// Verdict basis differs only because upstream root facts changed (`"upstream-stale"`).
    #[serde(rename = "upstream-stale")]
    UpstreamStale,
    /// No verdict recorded (`"unverified"`).
    #[serde(rename = "unverified")]
    Unverified,
    /// Basis cannot be established (`"unknown"`).
    #[serde(rename = "unknown")]
    Unknown,
}

impl Freshness {
    /// Returns the canonical status string.
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

    /// Parses a status string into [`Freshness`].
    #[must_use]
    pub fn from_str_name(s: &str) -> Option<Self> {
        match s {
            "current" => Some(Self::Current),
            "stale" => Some(Self::Stale),
            "upstream-stale" => Some(Self::UpstreamStale),
            "unverified" => Some(Self::Unverified),
            "unknown" => Some(Self::Unknown),
            _ => None,
        }
    }
}

impl fmt::Display for Freshness {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

// ---------------------------------------------------------------------------
// Canonical JSON & SHA-256 (`records.py:_plain`, `canonical`, `sha256`)
// ---------------------------------------------------------------------------

fn write_escaped_json_string(s: &str, out: &mut String) {
    out.push('"');
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\x08' => out.push_str("\\b"),
            '\x0c' => out.push_str("\\f"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

fn normalize_plain(value: &Value) -> Result<Value, String> {
    match value {
        Value::Null => Ok(Value::Null),
        Value::Bool(b) => Ok(Value::Bool(*b)),
        Value::Number(n) => {
            if n.is_i64() || n.is_u64() {
                Ok(Value::Number(n.clone()))
            } else {
                Err("canonical form: float is not part of the format".to_string())
            }
        }
        Value::String(s) => {
            let nfc: String = if is_nfc(s) {
                s.clone()
            } else {
                s.nfc().collect()
            };
            Ok(Value::String(nfc))
        }
        Value::Array(arr) => {
            let mut out = Vec::with_capacity(arr.len());
            for item in arr {
                out.push(normalize_plain(item)?);
            }
            Ok(Value::Array(out))
        }
        Value::Object(map) => {
            let mut out = Map::with_capacity(map.len());
            for (k, v) in map {
                let nk: String = if is_nfc(k) {
                    k.clone()
                } else {
                    k.nfc().collect()
                };
                if out.contains_key(&nk) {
                    return Err(format!("canonical form: keys {k:?} collide in NFC"));
                }
                out.insert(nk, normalize_plain(v)?);
            }
            Ok(Value::Object(out))
        }
    }
}

fn write_canonical_value(value: &Value, out: &mut String) -> Result<(), String> {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                out.push_str(&i.to_string());
            } else if let Some(u) = n.as_u64() {
                out.push_str(&u.to_string());
            } else {
                return Err("canonical form: float is not part of the format".to_string());
            }
        }
        Value::String(s) => {
            let nfc: String = if is_nfc(s) {
                s.clone()
            } else {
                s.nfc().collect()
            };
            write_escaped_json_string(&nfc, out);
        }
        Value::Array(arr) => {
            out.push('[');
            for (i, item) in arr.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_canonical_value(item, out)?;
            }
            out.push(']');
        }
        Value::Object(map) => {
            let mut sorted: BTreeMap<String, &Value> = BTreeMap::new();
            for (k, v) in map {
                let nk: String = if is_nfc(k) {
                    k.clone()
                } else {
                    k.nfc().collect()
                };
                if sorted.insert(nk, v).is_some() {
                    return Err(format!("canonical form: keys {k:?} collide in NFC"));
                }
            }
            out.push('{');
            for (i, (k, v)) in sorted.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_escaped_json_string(k, out);
                out.push(':');
                write_canonical_value(v, out)?;
            }
            out.push('}');
        }
    }
    Ok(())
}

/// Serializes `value` into `fact-v1` canonical JSON text (`records.py:canonical`):
/// - Every string and object key is normalized to Unicode NFC (refusing NFC key collisions).
/// - Object keys are sorted lexicographically by Unicode code point.
/// - Compact `,` and `:` separators with no whitespace.
/// - Raw UTF-8 characters (`ensure_ascii=False`).
/// - Only strings, 64-bit integers, booleans, `null`, arrays, and string-keyed objects are allowed
///   (floats are refused).
pub fn canonical(value: &Value) -> Result<String, String> {
    let _ = normalize_plain(value)?;
    let mut out = String::new();
    write_canonical_value(value, &mut out)?;
    Ok(out)
}

/// Serializes a list of `(key, value)` pairs as a JSON object into `fact-v1` canonical JSON,
/// detecting key collisions after Unicode NFC normalization even when the caller holds pre-NFC
/// duplicate keys that a `serde_json::Map` would otherwise overwrite.
pub fn canonical_pairs(pairs: &[(String, Value)]) -> Result<String, String> {
    let mut sorted: BTreeMap<String, Value> = BTreeMap::new();
    for (k, v) in pairs {
        let nk: String = k.nfc().collect();
        if sorted.contains_key(&nk) {
            return Err(format!("canonical form: keys {k:?} collide in NFC"));
        }
        sorted.insert(nk, normalize_plain(v)?);
    }
    let mut map = Map::with_capacity(sorted.len());
    for (k, v) in sorted {
        map.insert(k, v);
    }
    canonical(&Value::Object(map))
}

/// Computes the lowercase hex SHA-256 digest of UTF-8 string `text` (`records.py:sha256`).
#[must_use]
pub fn sha256_str(text: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(text.as_bytes());
    hex::encode(hasher.finalize())
}

fn traverse_mut<'a>(val: &'a mut Value, path: &[PathElem]) -> Option<&'a mut Value> {
    let mut cur = val;
    for elem in path {
        match elem {
            PathElem::Key(k) => {
                let m = cur.as_object_mut()?;
                cur = m.get_mut(k)?;
            }
            PathElem::Index(i) => {
                let a = cur.as_array_mut()?;
                cur = a.get_mut(*i)?;
            }
        }
    }
    Some(cur)
}

/// Returns a copy of `entry` with the bookkeeping fields for `kind` removed (`records.py:_entry`).
#[must_use]
pub fn strip_bookkeeping(kind: &str, entry: &Map<String, Value>) -> Value {
    let skip = bookkeeping_fields(kind);
    let mut out = Map::new();
    for (k, v) in entry {
        if !skip.contains(&k.as_str()) {
            out.insert(k.clone(), v.clone());
        }
    }
    Value::Object(out)
}

// ---------------------------------------------------------------------------
// Path representation & formatting (`speccheck.py:_where`)
// ---------------------------------------------------------------------------

/// Segment in a YAML/JSON document path (`("facts", 0, "support", 0)`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum PathElem {
    /// Mapping key.
    Key(String),
    /// Sequence index.
    Index(usize),
}

impl PathElem {
    /// Converts to [`yaml_strict::PathSegment`].
    #[must_use]
    pub fn to_yaml_segment(&self) -> yaml_strict::PathSegment {
        match self {
            Self::Key(k) => yaml_strict::PathSegment::Key(k.clone()),
            Self::Index(i) => yaml_strict::PathSegment::Index(*i),
        }
    }
}

impl From<&str> for PathElem {
    fn from(s: &str) -> Self {
        Self::Key(s.to_string())
    }
}

impl From<String> for PathElem {
    fn from(s: String) -> Self {
        Self::Key(s)
    }
}

impl From<usize> for PathElem {
    fn from(i: usize) -> Self {
        Self::Index(i)
    }
}

/// Formats a slice of [`PathElem`] matching `speccheck.py:_where` (e.g. `facts[0].support[0]`).
#[must_use]
pub fn format_where(path: &[PathElem]) -> String {
    if path.is_empty() {
        return "(top)".to_string();
    }
    let mut out = String::new();
    for p in path {
        match p {
            PathElem::Index(i) => out.push_str(&format!("[{i}]")),
            PathElem::Key(k) => {
                if !out.is_empty() {
                    out.push('.');
                }
                out.push_str(k);
            }
        }
    }
    out
}

fn python_tuple_repr(path: &[PathElem]) -> String {
    let parts: Vec<String> = path
        .iter()
        .map(|p| match p {
            PathElem::Key(k) => format!("'{k}'"),
            PathElem::Index(i) => i.to_string(),
        })
        .collect();
    if parts.len() == 1 {
        format!("({},)", parts[0])
    } else {
        format!("({})", parts.join(", "))
    }
}

// ---------------------------------------------------------------------------
// Peripheral projection & references (`peripheral.py`, `topology.py`, `speccheck.py`)
// ---------------------------------------------------------------------------

/// Yields `(child_value, path)` for all typed peripheral child rows (`peripheral.py:children`).
#[must_use]
pub fn peripheral_children(data: &Value, base: &[PathElem]) -> Vec<(Value, Vec<PathElem>)> {
    let mut out = Vec::new();
    let Some(payload) = data.get("data").and_then(Value::as_object) else {
        return out;
    };
    if let Some(fields) = payload.get("fields").and_then(Value::as_array) {
        for (i, field) in fields.iter().enumerate() {
            let mut p = base.to_vec();
            p.push(PathElem::from("data"));
            p.push(PathElem::from("fields"));
            p.push(PathElem::from(i));
            out.push((field.clone(), p));
        }
    }
    if let Some(layout_fields) = payload
        .get("layout")
        .and_then(Value::as_object)
        .and_then(|l| l.get("fields"))
        .and_then(Value::as_array)
    {
        for (i, field) in layout_fields.iter().enumerate() {
            let mut p = base.to_vec();
            p.push(PathElem::from("data"));
            p.push(PathElem::from("layout"));
            p.push(PathElem::from("fields"));
            p.push(PathElem::from(i));
            out.push((field.clone(), p));
        }
    }
    if let Some(seq) = payload.get("sequence").and_then(Value::as_object) {
        for group in ["steps", "order"] {
            if let Some(rows) = seq.get(group).and_then(Value::as_array) {
                for (i, row) in rows.iter().enumerate() {
                    let mut p = base.to_vec();
                    p.push(PathElem::from("data"));
                    p.push(PathElem::from("sequence"));
                    p.push(PathElem::from(group));
                    p.push(PathElem::from(i));
                    out.push((row.clone(), p));
                }
            }
        }
    }
    out
}

/// D16: supported register fields and sequence steps have verdict sub-keys (`peripheral.py:subrecords`).
#[must_use]
pub fn subrecords(data: &Value, base: &[PathElem]) -> Vec<(Value, Vec<PathElem>)> {
    let has_register = data
        .get("data")
        .and_then(Value::as_object)
        .is_some_and(|d| d.contains_key("register"));
    let mut out = Vec::new();
    for (row, path) in peripheral_children(data, base) {
        let Some(row_obj) = row.as_object() else {
            continue;
        };
        if !row_obj.contains_key("support") || path.len() < 2 {
            continue;
        }
        let parent_key = match &path[path.len() - 2] {
            PathElem::Key(k) => k.as_str(),
            PathElem::Index(_) => continue,
        };
        if (parent_key == "fields" || parent_key == "steps")
            && (parent_key == "steps" || has_register)
        {
            out.push((row, path));
        }
    }
    out
}

/// D16 projection: independent children, effective requirement and parent identity
/// (`peripheral.py:basis_data`).
#[must_use]
pub fn basis_data(rec_data: &Value, parent_data: Option<&Value>) -> Value {
    let mut data = rec_data.clone();
    if let Some(parent) = parent_data {
        if let (Some(data_obj), Some(parent_obj)) = (data.as_object_mut(), parent.as_object()) {
            if !data_obj.contains_key("requirement") {
                if let Some(req) = parent_obj.get("requirement") {
                    data_obj.insert("requirement".to_string(), req.clone());
                }
            }
            if let Some(payload) = parent_obj.get("data").and_then(Value::as_object) {
                if let Some(reg) = payload.get("register").and_then(Value::as_object) {
                    let mut pid = Map::new();
                    if let Some(name) = reg.get("name") {
                        pid.insert("name".to_string(), name.clone());
                    }
                    if let Some(offset) = reg.get("offset") {
                        pid.insert("offset".to_string(), offset.clone());
                    }
                    data_obj.insert("parent_identity".to_string(), Value::Object(pid));
                } else if let Some(seq) = payload.get("sequence").and_then(Value::as_object) {
                    if let Some(steps) = seq.get("steps").and_then(Value::as_array) {
                        let step_ids: Vec<Value> = steps
                            .iter()
                            .filter_map(|r| r.get("id").cloned())
                            .collect();
                        let mut pid = Map::new();
                        pid.insert("steps".to_string(), Value::Array(step_ids));
                        data_obj.insert("parent_identity".to_string(), Value::Object(pid));
                    }
                }
            }
        }
    } else {
        for (_, path) in subrecords(rec_data, &[]) {
            if path.is_empty() {
                continue;
            }
            if let Some(parent) = traverse_mut(&mut data, &path[..path.len() - 1]) {
                if let Some(PathElem::Index(last_idx)) = path.last() {
                    if let Some(arr) = parent.as_array_mut() {
                        if let Some(item) = arr.get_mut(*last_idx) {
                            if let Some(id_val) = item.get("id").cloned() {
                                let mut slim = Map::new();
                                slim.insert("id".to_string(), id_val);
                                *item = Value::Object(slim);
                            }
                        }
                    }
                }
            }
        }
    }
    data
}

/// Returns `true` when `path` is owned by `rec` rather than a separately supported subrecord
/// (`peripheral.py:owns_citation`).
#[must_use]
pub fn owns_citation(rec_data: &Value, rec_path: &[PathElem], path: &[PathElem]) -> bool {
    !subrecords(rec_data, rec_path)
        .iter()
        .any(|(_, at)| path.starts_with(at))
}

/// Yields `(support_entry, path)` for all own, premise, conflict, and settlement support entries,
/// plus `data.pair` sides (`speccheck.py:supports`).
#[must_use]
pub fn supports(data: &Value, base: &[PathElem]) -> Vec<(Value, Vec<PathElem>)> {
    let mut out = Vec::new();
    supports_inner(data, base, true, &mut out);
    out
}

fn supports_inner(
    data: &Value,
    base: &[PathElem],
    payload: bool,
    out: &mut Vec<(Value, Vec<PathElem>)>,
) {
    match data {
        Value::Object(map) => {
            for (key, value) in map {
                if key == "support" || key == "settled_by" {
                    if let Some(arr) = value.as_array() {
                        for (i, entry) in arr.iter().enumerate() {
                            let mut p = base.to_vec();
                            p.push(PathElem::Key(key.clone()));
                            p.push(PathElem::Index(i));
                            out.push((entry.clone(), p));
                        }
                    }
                }
                let mut child_base = base.to_vec();
                child_base.push(PathElem::Key(key.clone()));
                supports_inner(value, &child_base, false, out);
            }
            if payload {
                if let Some(pair) = map
                    .get("data")
                    .and_then(Value::as_object)
                    .and_then(|d| d.get("pair"))
                    .and_then(Value::as_object)
                {
                    for (side, value) in pair {
                        let mut p = base.to_vec();
                        p.push(PathElem::from("data"));
                        p.push(PathElem::from("pair"));
                        p.push(PathElem::Key(side.clone()));
                        out.push((json!({"class": "src", "anchors": value}), p));
                    }
                }
            }
        }
        Value::Array(arr) => {
            for (i, value) in arr.iter().enumerate() {
                let mut child_base = base.to_vec();
                child_base.push(PathElem::Index(i));
                supports_inner(value, &child_base, false, out);
            }
        }
        _ => {}
    }
}

/// Yields `(anchor, path)` for every anchor of an anchored support class (`src`, `DT`, `rtl`)
/// (`speccheck.py:anchors`).
#[must_use]
pub fn anchors(data: &Value, base: &[PathElem]) -> Vec<(Value, Vec<PathElem>)> {
    let mut out = Vec::new();
    for (entry, path) in supports(data, base) {
        let Some(cls) = entry.get("class").and_then(Value::as_str) else {
            continue;
        };
        if !ANCHORED.contains(&cls) {
            continue;
        }
        if let Some(arr) = entry.get("anchors").and_then(Value::as_array) {
            let is_pair_side = path
                .last()
                .is_some_and(|last| matches!(last, PathElem::Key(k) if k == "impl" || k == "ref"));
            for (a, anchor) in arr.iter().enumerate() {
                let mut p = path.clone();
                if !is_pair_side {
                    p.push(PathElem::from("anchors"));
                }
                p.push(PathElem::Index(a));
                out.push((anchor.clone(), p));
            }
        }
    }
    out
}

/// Returns `true` if `data` has `support` or `data.pair` (`speccheck.py:has_support`).
#[must_use]
pub fn has_support(data: &Value) -> bool {
    let has_sup = data
        .get("support")
        .and_then(Value::as_array)
        .is_some_and(|a| !a.is_empty());
    let has_pair = data
        .get("data")
        .and_then(Value::as_object)
        .and_then(|d| d.get("pair"))
        .and_then(Value::as_object)
        .is_some_and(|p| !p.is_empty());
    has_sup || has_pair
}

/// Extracts all topology fact references `(kind, ref_str, path)` (`topology.py:references`).
#[must_use]
pub fn topology_refs(data: &Value, base: &[PathElem]) -> Vec<(String, String, Vec<PathElem>)> {
    let mut out = Vec::new();
    let Some(fields) = data.get("data").and_then(Value::as_object) else {
        return out;
    };
    if let Some(node) = fields.get("topologyNode").and_then(Value::as_object) {
        for field in ["instance", "rate", "voltage"] {
            if let Some(val) = node.get(field).and_then(Value::as_str) {
                let mut p = base.to_vec();
                p.push(PathElem::from("data"));
                p.push(PathElem::from("topologyNode"));
                p.push(PathElem::from(field));
                out.push((format!("topology-{field}"), val.to_string(), p));
            }
        }
    }
    if let Some(conn) = fields.get("connection").and_then(Value::as_object) {
        for side in ["provider", "consumer"] {
            if let Some(node_val) = conn
                .get(side)
                .and_then(Value::as_object)
                .and_then(|s| s.get("node"))
                .and_then(Value::as_str)
            {
                let mut p = base.to_vec();
                p.push(PathElem::from("data"));
                p.push(PathElem::from("connection"));
                p.push(PathElem::from(side));
                p.push(PathElem::from("node"));
                out.push((format!("topology-{side}"), node_val.to_string(), p));
            }
        }
    }
    if let Some(sel) = fields.get("selection").and_then(Value::as_object) {
        for field in ["configuration", "selects"] {
            if let Some(val) = sel.get(field).and_then(Value::as_str) {
                let mut p = base.to_vec();
                p.push(PathElem::from("data"));
                p.push(PathElem::from("selection"));
                p.push(PathElem::from(field));
                out.push((format!("topology-{field}"), val.to_string(), p));
            }
        }
    }
    out
}

/// Extracts every fact reference a record makes: `(kind, ref_str, path)` (`speccheck.py:references`).
#[must_use]
pub fn parse_refs(data: &Value, base: &[PathElem]) -> Vec<(String, String, Vec<PathElem>)> {
    let mut out = topology_refs(data, base);
    for (entry, at) in supports(data, base) {
        if entry.get("class").and_then(Value::as_str) == Some("inference") {
            if let Some(premises) = entry.get("premises").and_then(Value::as_array) {
                for (j, premise) in premises.iter().enumerate() {
                    if let Some(f) = premise.get("fact").and_then(Value::as_str) {
                        let mut p = at.clone();
                        p.push(PathElem::from("premises"));
                        p.push(PathElem::Index(j));
                        p.push(PathElem::from("fact"));
                        out.push(("premise".to_string(), f.to_string(), p));
                    }
                }
            }
        }
    }
    if let Some(relates) = data.get("relates").and_then(Value::as_array) {
        for (r, relation) in relates.iter().enumerate() {
            if let Some(f) = relation.get("fact").and_then(Value::as_str) {
                let mut p = base.to_vec();
                p.push(PathElem::from("relates"));
                p.push(PathElem::Index(r));
                p.push(PathElem::from("fact"));
                out.push(("relates".to_string(), f.to_string(), p));
            }
        }
    }
    for (entry, path) in supports(data, base) {
        if entry.get("class").and_then(Value::as_str) == Some("emulated") {
            if let Some(obs) = entry.get("observation").and_then(Value::as_str) {
                let mut p = path;
                p.push(PathElem::from("observation"));
                out.push(("observation".to_string(), obs.to_string(), p));
            }
        }
    }
    out
}

/// Alias for [`parse_refs`] (`speccheck.py:references`).
#[must_use]
pub fn references(data: &Value, base: &[PathElem]) -> Vec<(String, String, Vec<PathElem>)> {
    parse_refs(data, base)
}

// ---------------------------------------------------------------------------
// Generic cycle-safe Tarjan SCC `compute` (`records.py:compute`)
// ---------------------------------------------------------------------------

/// Node trait for [`compute_graph`], providing the full `<spec>@<root>#<id>` reference string.
pub trait GraphRecord: Clone + Eq + Hash {
    /// Returns the full reference (`<spec>@<root>#<id>`).
    fn full_ref(&self) -> &str;
}

impl GraphRecord for String {
    fn full_ref(&self) -> &str {
        self.as_str()
    }
}

/// Fills `out[record] = (Some(basis), None)` or `(None, Some(why))` for every record reachable
/// from `starts` using Tarjan's strongly connected components algorithm (`records.py:compute`).
///
/// - `edges(record)` returns `Vec<(ref_str, Option<Target>, Option<Why>)>` for each reference.
/// - `local(record)` returns `( Option<local_text>, Option<Why> )`.
/// - `fixed` maps records to a pre-fixed basis (leaves, never entered).
pub fn compute_graph<K, FEdges, FLocal>(
    starts: &[K],
    mut edges: FEdges,
    mut local: FLocal,
    fixed: &HashMap<K, String>,
    out: &mut HashMap<K, (Option<String>, Option<String>)>,
) where
    K: GraphRecord,
    FEdges: FnMut(&K) -> Vec<(String, Option<K>, Option<String>)>,
    FLocal: FnMut(&K) -> (Option<String>, Option<String>),
{
    let mut index: HashMap<K, usize> = HashMap::new();
    let mut low: HashMap<K, usize> = HashMap::new();
    let mut stack: Vec<K> = Vec::new();
    let mut on_stack: HashSet<K> = HashSet::new();
    let mut counter: usize = 0;
    let mut cache: HashMap<K, Vec<(String, Option<K>, Option<String>)>> = HashMap::new();

    fn get_succ<K: GraphRecord, FEdges: FnMut(&K) -> Vec<(String, Option<K>, Option<String>)>>(
        v: &K,
        cache: &mut HashMap<K, Vec<(String, Option<K>, Option<String>)>>,
        edges: &mut FEdges,
        fixed: &HashMap<K, String>,
        out: &HashMap<K, (Option<String>, Option<String>)>,
    ) -> Vec<K> {
        let entry = cache.entry(v.clone()).or_insert_with(|| edges(v));
        entry
            .iter()
            .filter_map(|(_, t, _)| {
                let target = t.as_ref()?;
                if !fixed.contains_key(target) && !out.contains_key(target) {
                    Some(target.clone())
                } else {
                    None
                }
            })
            .collect()
    }

    for s in starts {
        if out.contains_key(s) || fixed.contains_key(s) || index.contains_key(s) {
            continue;
        }
        index.insert(s.clone(), counter);
        low.insert(s.clone(), counter);
        counter += 1;
        stack.push(s.clone());
        on_stack.insert(s.clone());
        let first_succ = get_succ(s, &mut cache, &mut edges, fixed, out);
        let mut work: Vec<(K, std::vec::IntoIter<K>)> = vec![(s.clone(), first_succ.into_iter())];

        while let Some((node, mut it)) = work.pop() {
            let mut advanced = false;
            while let Some(w) = it.next() {
                if !index.contains_key(&w) {
                    index.insert(w.clone(), counter);
                    low.insert(w.clone(), counter);
                    counter += 1;
                    stack.push(w.clone());
                    on_stack.insert(w.clone());
                    let w_succ = get_succ(&w, &mut cache, &mut edges, fixed, out);
                    work.push((node.clone(), it));
                    work.push((w, w_succ.into_iter()));
                    advanced = true;
                    break;
                }
                if on_stack.contains(&w) {
                    let w_idx = index[&w];
                    let node_low = low.get_mut(&node).unwrap();
                    if w_idx < *node_low {
                        *node_low = w_idx;
                    }
                }
            }
            if advanced {
                continue;
            }
            let node_low = low[&node];
            if let Some((parent, _)) = work.last() {
                let p_low = low.get_mut(parent).unwrap();
                if node_low < *p_low {
                    *p_low = node_low;
                }
            }
            if node_low == index[&node] {
                let mut scc = Vec::new();
                while let Some(w) = stack.pop() {
                    on_stack.remove(&w);
                    let done = w == node;
                    scc.push(w);
                    if done {
                        break;
                    }
                }
                let members: HashSet<K> = scc.iter().cloned().collect();
                let cyclic = scc.len() > 1
                    || cache[&scc[0]]
                        .iter()
                        .any(|(_, t, _)| t.as_ref() == Some(&scc[0]));
                let mut parts: HashMap<K, String> = HashMap::new();
                let mut problem: Option<String> = None;
                let mut external: BTreeSet<String> = BTreeSet::new();

                for m in &scc {
                    let (text_opt, why_opt) = local(m);
                    if let Some(t) = text_opt {
                        parts.insert(m.clone(), t);
                    } else if problem.is_none() {
                        problem = why_opt;
                    }
                    for (ref_str, t_opt, why_ref) in &cache[m] {
                        match t_opt {
                            None => {
                                if problem.is_none() {
                                    problem = Some(format!(
                                        "{}: reference '{ref_str}' {}",
                                        m.full_ref(),
                                        why_ref.as_deref().unwrap_or("failed")
                                    ));
                                }
                            }
                            Some(t) if !members.contains(t) => {
                                let val = fixed
                                    .get(t)
                                    .cloned()
                                    .or_else(|| out.get(t).and_then(|(b, _)| b.clone()));
                                if let Some(b) = val {
                                    external.insert(format!("{} {b}", t.full_ref()));
                                } else if problem.is_none() {
                                    problem = out.get(t).and_then(|(_, w)| w.clone());
                                }
                            }
                            Some(_) => {}
                        }
                    }
                }

                if let Some(prob) = problem {
                    for m in scc {
                        out.insert(m, (None, Some(prob.clone())));
                    }
                    continue;
                }

                let digest = if cyclic {
                    let mut member_lines: Vec<String> = scc
                        .iter()
                        .map(|m| format!("{} {}", m.full_ref(), sha256_str(&parts[m])))
                        .collect();
                    member_lines.sort();
                    let ext_lines: Vec<String> = external.into_iter().collect();
                    Some(sha256_str(&format!(
                        "{CANONICAL_CYCLE}\n{}\n{}",
                        member_lines.join("\n"),
                        ext_lines.join("\n")
                    )))
                } else {
                    None
                };

                for m in scc {
                    let mut lines: BTreeSet<String> = BTreeSet::new();
                    for (_, t_opt, _) in &cache[&m] {
                        if let Some(t) = t_opt {
                            let b = if members.contains(t) {
                                digest.as_ref().unwrap().clone()
                            } else {
                                fixed
                                    .get(t)
                                    .cloned()
                                    .or_else(|| out.get(t).and_then(|(v, _)| v.clone()))
                                    .unwrap()
                            };
                            lines.insert(format!("{} {b}", t.full_ref()));
                        }
                    }
                    let lines_vec: Vec<String> = lines.into_iter().collect();
                    let basis = sha256_str(&format!(
                        "{CANONICAL}\n{}\n{}",
                        parts[&m],
                        lines_vec.join("\n")
                    ));
                    out.insert(m, (Some(basis), None));
                }
            }
        }
    }
}
// ---------------------------------------------------------------------------
// Data model (`Root`, `SpecFile`, `SpecRecord`) & `local_part` (`records.py`)
// ---------------------------------------------------------------------------

/// Identifier for a record inside a [`Checker`] (`(file_index, record_key)`).
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct RecordKey {
    /// Index into `checker.files`.
    pub file_idx: usize,
    /// Record key within the file (e.g. `"reset-cycles"` or `"ctrl.en"`).
    pub id: String,
    /// Full reference string (`"<spec_id>@<root_label>#<id>"`).
    pub full: String,
}

impl GraphRecord for RecordKey {
    fn full_ref(&self) -> &str {
        self.full.as_str()
    }
}

/// A verifiable record (a fact, an instance row, a variant row, or a D16 sub-record)
/// (`speccheck.py:Record`).
#[derive(Debug, Clone)]
pub struct SpecRecord {
    /// Index of the owning [`SpecFile`] in `checker.files`.
    pub file_idx: usize,
    /// Path within `file.data` (`("facts", i)`, `("instances", i)`, `("variants", i)`, or subrecord path).
    pub path: Vec<PathElem>,
    /// Record JSON value (`id`, `title`, `claim`, `support`, ...).
    pub data: Value,
    /// Parent record ID when this is a D16 subrecord (`"ctrl"` for `"ctrl.en"`).
    pub parent_id: Option<String>,
    /// Record key (`data["id"]`).
    pub id: String,
    /// Full reference (`"<spec_id>@<root_label>#<id>"`).
    pub full: String,
}

/// Loaded spec root (`speccheck.py:Root`).
#[derive(Debug, Clone)]
pub struct SpecRoot {
    /// Path as passed by the caller.
    pub given: PathBuf,
    /// Canonicalized real path.
    pub real: PathBuf,
    /// `true` if passed via `--context-root`.
    pub context: bool,
    /// Input order index.
    pub order: usize,
    /// Root name from `board-specs.yaml`.
    pub name: Option<String>,
    /// Root layer (`"public"`, `"ip-vendor"`, `"soc-vendor"`, `"product"`, `"local"`).
    pub layer: Option<String>,
    /// Layer rank (`0..5`).
    pub rank: usize,
    /// Accepted SPDX identifiers (`None` when marker failed validation).
    pub accepts: Option<BTreeSet<String>>,
    /// Optional `source-observed` schema fragment loaded from `extensions`.
    pub extension: Option<Value>,
    /// Strict YAML load of `board-specs.yaml`.
    pub marker: Option<Loaded>,
    /// Indices into `checker.files` belonging to this root.
    pub files: Vec<usize>,
    /// Discovered `*.spec.yaml` paths.
    pub spec_paths: Vec<PathBuf>,
    /// Discovered `resources/*.verify.yaml` paths.
    pub record_paths: Vec<PathBuf>,
    /// Optional `corpus.yaml` path.
    pub corpus_path: Option<PathBuf>,
    /// Loaded `corpus.yaml` when valid.
    pub corpus: Option<Loaded>,
    /// Discovered `index/*.index.yaml` paths.
    pub index_paths: Vec<PathBuf>,
    /// Error-severity findings in this root (`(location, message)`), making it untrusted.
    pub untrusted: Vec<(String, String)>,
}

impl SpecRoot {
    /// Label used in references and diagnostics (`root.name` or `root.given`).
    #[must_use]
    pub fn label(&self) -> String {
        self.name
            .clone()
            .unwrap_or_else(|| self.given.to_string_lossy().into_owned())
    }
}

/// Ambiguity key within a single [`SpecFile`] (`speccheck.py:SpecFile.ambiguous`).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum AmbiguousItem {
    /// `("documents", name)`, `("repos", name)`, `("assumptions", id)`, or `(registry_group, name)`.
    GroupName(String, String),
    /// `("files", repo_name, file_path)`.
    RepoFile(String, String),
}

/// Loaded `.spec.yaml` or `.facts.yaml` file (`speccheck.py:SpecFile`).
#[derive(Debug, Clone)]
pub struct SpecFile {
    /// File path.
    pub path: PathBuf,
    /// Index of owning [`SpecRoot`] in `checker.roots`.
    pub root_idx: usize,
    /// Strict YAML load result (for line/column marks).
    pub loaded: Loaded,
    /// Parsed JSON value.
    pub data: Value,
    /// Ordered verifiable records (`id -> SpecRecord`), preserving insertion order.
    pub records: Vec<(String, SpecRecord)>,
    /// Fast lookup from record ID to index in `records`.
    pub record_map: HashMap<String, usize>,
    /// Fact IDs declared more than once in this file.
    pub duplicated: HashSet<String>,
    /// Assumptions (`id -> (entry, path)`).
    pub assumptions: HashMap<String, (Value, Vec<PathElem>)>,
    /// Documents (`name -> (entry, path)`).
    pub documents: HashMap<String, (Value, Vec<PathElem>)>,
    /// Repos (`name -> (entry, path)`).
    pub repos: HashMap<String, (Value, Vec<PathElem>)>,
    /// Items declared twice in this file.
    pub ambiguous: HashSet<AmbiguousItem>,
    /// Spec-level registries (`group -> name -> (entry, path)`).
    pub registries: HashMap<String, HashMap<String, (Value, Vec<PathElem>)>>,
    /// Verification record state (`"none"`, `"ok"`, `"invalid"`, `"shared"`).
    pub record_state: String,
    /// Path to `resources/<stem>.verify.yaml` when matched.
    pub record_path: Option<PathBuf>,
    /// Loaded `.verify.yaml` when valid.
    pub record_loaded: Option<Loaded>,
    /// Validated verdicts (`key -> (verdict_value, key_path)`).
    pub verdicts: HashMap<String, (Value, Vec<PathElem>)>,
}

impl SpecFile {
    /// Spec kind (`"chip"`, `"soc"`, `"board"`, `"ip"`, `"peripheral"`, `"overlay"`, `"facts"`, `"review"`).
    #[must_use]
    pub fn kind(&self) -> &str {
        self.data
            .get("kind")
            .and_then(Value::as_str)
            .unwrap_or("")
    }

    /// `true` if `kind == "overlay"`.
    #[must_use]
    pub fn is_overlay(&self) -> bool {
        self.kind() == "overlay"
    }

    /// Spec identifier (`overlays` for an overlay, `id` otherwise, or filename stem for `.facts.yaml`).
    #[must_use]
    pub fn spec_id(&self) -> String {
        if self.is_overlay() {
            self.data
                .get("overlays")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string()
        } else if let Some(id) = self.data.get("id").and_then(Value::as_str) {
            id.to_string()
        } else {
            let fname = self
                .path
                .file_name()
                .map(|s| s.to_string_lossy().into_owned())
                .unwrap_or_default();
            fname
                .strip_suffix(".facts.yaml")
                .unwrap_or(&fname)
                .to_string()
        }
    }

    /// Looks up a [`SpecRecord`] by ID.
    #[must_use]
    pub fn get_record(&self, id: &str) -> Option<&SpecRecord> {
        let &idx = self.record_map.get(id)?;
        Some(&self.records[idx].1)
    }
}

/// Computes the referenced registries for `rec` (`peripheral.py:referenced_registries`).
/// Returns `Ok(vec_of_(group, name, entry, path))` sorted by `(group, name)`, or `Err(why)`.
pub fn referenced_registries(
    rec: &SpecRecord,
    file: &SpecFile,
) -> Result<Vec<(String, String, Value, Vec<PathElem>)>, String> {
    let parent_data = rec
        .parent_id
        .as_deref()
        .and_then(|pid| file.get_record(pid))
        .map(|p| &p.data);
    let data = basis_data(&rec.data, parent_data);

    let (fields, register): (Vec<Value>, Map<String, Value>) = if rec.parent_id.is_some() {
        (vec![data], Map::new())
    } else {
        let payload = data.get("data").and_then(Value::as_object);
        let mut f_list = payload
            .and_then(|p| p.get("fields"))
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        if let Some(layout_fields) = payload
            .and_then(|p| p.get("layout"))
            .and_then(Value::as_object)
            .and_then(|l| l.get("fields"))
            .and_then(Value::as_array)
        {
            f_list.extend(layout_fields.iter().cloned());
        }
        let reg = payload
            .and_then(|p| p.get("register"))
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        (f_list, reg)
    };

    let mut wanted: HashSet<(String, String)> = HashSet::new();
    let mut queue: Vec<(String, String)> = Vec::new();
    let mut want = |group: &str, name: &str| {
        let key = (group.to_string(), name.to_string());
        if !wanted.contains(&key) {
            wanted.insert(key.clone());
            queue.push(key);
        }
    };

    if let Some(rf) = register.get("registerFile").and_then(Value::as_str) {
        want("registerFiles", rf);
    }
    for field in &fields {
        if let Some(resets) = field.get("resets").and_then(Value::as_array) {
            for reset in resets {
                if let Some(rref) = reset.get("resetTypeRef").and_then(Value::as_str) {
                    want("resetTypes", rref);
                }
            }
        }
        if let Some(unaff) = field.get("unaffectedBy").and_then(Value::as_array) {
            for item in unaff {
                if let Some(name) = item.as_str() {
                    want("resetTypes", name);
                }
            }
        }
        if let Some(eref) = field.get("enumerationDefinitionRef").and_then(Value::as_str) {
            want("enumerationDefinitions", eref);
        }
        if let Some(pref) = field
            .get("fieldAccessPolicyDefinitionRef")
            .and_then(Value::as_str)
        {
            want("fieldAccessPolicyDefinitions", pref);
        }
    }

    let mut out = Vec::new();
    while let Some((group, name)) = queue.pop() {
        if file
            .ambiguous
            .contains(&AmbiguousItem::GroupName(group.clone(), name.clone()))
        {
            let label = registry_entry_label(&group);
            return Err(format!(
                "{}: {label} '{name}' is listed twice in its file",
                rec.full
            ));
        }
        let Some((entry, path)) = file
            .registries
            .get(&group)
            .and_then(|t| t.get(&name))
            .cloned()
        else {
            let label = registry_entry_label(&group);
            return Err(format!(
                "{}: {label} '{name}' is not in its file's {group}",
                rec.full
            ));
        };
        if group == "fieldAccessPolicyDefinitions" {
            if let Some(unaff) = entry.get("unaffectedBy").and_then(Value::as_array) {
                for reset in unaff {
                    if let Some(rname) = reset.as_str() {
                        let key = ("resetTypes".to_string(), rname.to_string());
                        if !wanted.contains(&key) {
                            wanted.insert(key.clone());
                            queue.push(key);
                        }
                    }
                }
            }
        }
        out.push((group, name, entry, path));
    }
    out.sort_by(|a, b| (a.0.as_str(), a.1.as_str()).cmp(&(b.0.as_str(), b.1.as_str())));
    Ok(out)
}

/// Computes the local part of `rec`'s basis decided by its own file (`records.py:local_part`).
/// Returns `Ok(local_text)` or `Err(why)`.
pub fn local_part(rec: &SpecRecord, file: &SpecFile) -> Result<String, String> {
    let parent_data = rec
        .parent_id
        .as_deref()
        .and_then(|pid| file.get_record(pid))
        .map(|p| &p.data);
    let data = basis_data(&rec.data, parent_data);
    let mut fact_map = data.as_object().cloned().unwrap_or_default();
    fact_map.remove("section");
    let fact = Value::Object(fact_map);

    let named = referenced_registries(rec, file)?;

    let mut cited: Vec<Value> = supports(&data, &[]).into_iter().map(|(e, _)| e).collect();
    for (_, _, reg, _) in &named {
        for (e, _) in supports(reg, &[]) {
            cited.push(e);
        }
    }

    let mut documents = Map::new();
    let mut repos = Map::new();
    let mut paths: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();

    for entry in &cited {
        if let Some(name) = entry.get("doc").and_then(Value::as_str) {
            if file.ambiguous.contains(&AmbiguousItem::GroupName(
                "documents".to_string(),
                name.to_string(),
            )) {
                return Err(format!(
                    "{}: document '{name}' is listed twice in its file",
                    rec.full
                ));
            }
            let Some((doc_val, _)) = file.documents.get(name) else {
                return Err(format!(
                    "{}: document '{name}' is not in its file's resources",
                    rec.full
                ));
            };
            if let Some(doc_obj) = doc_val.as_object() {
                documents.insert(name.to_string(), strip_bookkeeping("documents", doc_obj));
            }
        }
        if let Some(cls) = entry.get("class").and_then(Value::as_str) {
            if ANCHORED.contains(&cls) {
                if let Some(anchs) = entry.get("anchors").and_then(Value::as_array) {
                    for anchor in anchs {
                        let Some(name) = anchor.get("repo").and_then(Value::as_str) else {
                            continue;
                        };
                        if file.ambiguous.contains(&AmbiguousItem::GroupName(
                            "repos".to_string(),
                            name.to_string(),
                        )) {
                            return Err(format!(
                                "{}: repos entry '{name}' is listed twice in its file",
                                rec.full
                            ));
                        }
                        if !file.repos.contains_key(name) {
                            return Err(format!(
                                "{}: repos entry '{name}' is not in its file's resources",
                                rec.full
                            ));
                        }
                        if let Some(p) = anchor.get("path").and_then(Value::as_str) {
                            paths
                                .entry(name.to_string())
                                .or_default()
                                .insert(p.to_string());
                        }
                    }
                }
            }
        }
    }

    for (name, cited_paths) in &paths {
        let (repo_val, _) = &file.repos[name];
        let Some(repo_obj) = repo_val.as_object() else {
            continue;
        };
        if !repo_obj.contains_key("commit") {
            return Err(format!(
                "{}: repos entry '{name}' pins a ref, not a commit, so what the fact cites through it is not fixed",
                rec.full
            ));
        }
        let mut listed: HashMap<String, &Map<String, Value>> = HashMap::new();
        if let Some(files_arr) = repo_obj.get("files").and_then(Value::as_array) {
            for item in files_arr {
                if let Some(item_obj) = item.as_object() {
                    if let Some(p) = item_obj.get("path").and_then(Value::as_str) {
                        listed.insert(p.to_string(), item_obj);
                    }
                }
            }
        }
        let missing: Vec<&String> = cited_paths
            .iter()
            .filter(|p| !listed.contains_key(*p))
            .collect();
        if let Some(first_missing) = missing.first() {
            return Err(format!(
                "{}: '{first_missing}' is not in the files of repos entry '{name}', so its license entry is unknown",
                rec.full
            ));
        }
        let twice: Vec<&String> = cited_paths
            .iter()
            .filter(|p| {
                file.ambiguous
                    .contains(&AmbiguousItem::RepoFile(name.clone(), (*p).clone()))
            })
            .collect();
        if let Some(first_twice) = twice.first() {
            return Err(format!(
                "{}: repos entry '{name}' lists '{first_twice}' twice in files, so its license entry is ambiguous",
                rec.full
            ));
        }
        let mut stripped_repo = strip_bookkeeping("repos", repo_obj);
        let stripped_files: Vec<Value> = cited_paths
            .iter()
            .map(|p| strip_bookkeeping("files", listed[p]))
            .collect();
        if let Some(obj) = stripped_repo.as_object_mut() {
            obj.insert("files".to_string(), Value::Array(stripped_files));
        }
        repos.insert(name.clone(), stripped_repo);
    }

    let mut assumption_names: Vec<String> = Vec::new();
    if let Some(assumes) = data.get("assumes").and_then(Value::as_array) {
        for a in assumes {
            if let Some(s) = a.as_str() {
                assumption_names.push(s.to_string());
            }
        }
    }
    for (entry, _) in supports(&data, &[]) {
        if let Some(premises) = entry.get("premises").and_then(Value::as_array) {
            for p in premises {
                if let Some(s) = p.get("assumption").and_then(Value::as_str) {
                    assumption_names.push(s.to_string());
                }
            }
        }
    }

    let mut assumptions = Map::new();
    for name in &assumption_names {
        if file.ambiguous.contains(&AmbiguousItem::GroupName(
            "assumptions".to_string(),
            name.clone(),
        )) {
            return Err(format!(
                "{}: assumption '{name}' is declared twice in its file",
                rec.full
            ));
        }
        let Some((assump_val, _)) = file.assumptions.get(name) else {
            return Err(format!(
                "{}: assumption '{name}' is not in its file's assumptions",
                rec.full
            ));
        };
        if let Some(assump_obj) = assump_val.as_object() {
            assumptions.insert(name.clone(), strip_bookkeeping("assumptions", assump_obj));
        }
    }

    let mut registries = Map::new();
    for (group, name, reg, _) in &named {
        if let Some(reg_obj) = reg.as_object() {
            let group_entry = registries
                .entry(group.clone())
                .or_insert_with(|| Value::Object(Map::new()));
            if let Some(gmap) = group_entry.as_object_mut() {
                gmap.insert(name.clone(), strip_bookkeeping("registry", reg_obj));
            }
        }
    }

    let mut res_outer = Map::new();
    res_outer.insert("documents".to_string(), Value::Object(documents));
    res_outer.insert("repos".to_string(), Value::Object(repos));

    let mut text = format!(
        "{}\n{}\n{}",
        canonical(&fact)?,
        canonical(&Value::Object(res_outer))?,
        canonical(&Value::Object(assumptions))?
    );
    if !registries.is_empty() {
        text.push('\n');
        text.push_str(&canonical(&Value::Object(registries))?);
    }
    Ok(text)
}
// ---------------------------------------------------------------------------
// Freshness Engine (`records.py:Freshness`)
// ---------------------------------------------------------------------------

/// Normalizes a verifier string for comparing readers: Unicode NFC, whitespace collapsed,
/// Unicode case-folded / lowercased (`records.py:_who`).
#[must_use]
pub fn who_verifier(verifier: &str) -> String {
    let nfc: String = verifier.nfc().collect();
    let collapsed: Vec<&str> = nfc.split_whitespace().collect();
    collapsed.join(" ").to_lowercase()
}

/// Truncates whitespace-collapsed text to at most 120 characters (`records.py:_cut`).
#[must_use]
pub fn cut_text(text: &str) -> String {
    let collapsed: Vec<&str> = text.split_whitespace().collect();
    let joined = collapsed.join(" ");
    let chars: Vec<char> = joined.chars().collect();
    if chars.len() <= 120 {
        joined
    } else {
        let prefix: String = chars[..117].iter().collect();
        format!("{prefix}...")
    }
}

/// Engine computing `fact-v1` bases, cross-root frontiers, and verdict freshness over a [`Checker`]
/// (`records.py:Freshness`).
pub struct FreshnessEngine<'a> {
    checker: &'a Checker,
    failed: Option<HashSet<(usize, Vec<PathElem>)>>,
    cites: HashMap<usize, Vec<Vec<PathElem>>>,
    edges_cache: HashMap<RecordKey, Vec<(String, Option<RecordKey>, Option<String>)>>,
    /// Computed `(Option<basis>, Option<why>)` for each record key.
    pub bases: HashMap<RecordKey, (Option<String>, Option<String>)>,
}

impl<'a> FreshnessEngine<'a> {
    /// Creates a new [`FreshnessEngine`] over `checker`.
    #[must_use]
    pub fn new(
        checker: &'a Checker,
        failed: Option<HashSet<(usize, Vec<PathElem>)>>,
        failed_cites: Option<&HashSet<(usize, Vec<PathElem>)>>,
    ) -> Self {
        let mut cites: HashMap<usize, Vec<Vec<PathElem>>> = HashMap::new();
        if let Some(fc) = failed_cites {
            for (f_idx, path) in fc {
                cites.entry(*f_idx).or_default().push(path.clone());
            }
        }
        Self {
            checker,
            failed,
            cites,
            edges_cache: HashMap::new(),
            bases: HashMap::new(),
        }
    }

    /// Outgoing reference edges `(ref_str, Option<TargetKey>, Option<Why>)` (`records.py:Freshness.edges`).
    pub fn edges(
        &mut self,
        key: &RecordKey,
    ) -> Vec<(String, Option<RecordKey>, Option<String>)> {
        if let Some(cached) = self.edges_cache.get(key) {
            return cached.clone();
        }
        let file = &self.checker.files[key.file_idx];
        let rec = file.get_record(&key.id).unwrap();
        let parent_data = rec
            .parent_id
            .as_deref()
            .and_then(|pid| file.get_record(pid))
            .map(|p| &p.data);
        let bdata = basis_data(&rec.data, parent_data);
        let mut out = Vec::new();
        for (_, ref_str, path) in parse_refs(&bdata, &rec.path) {
            let (mut target, mut why) = self.checker.resolve(key.file_idx, &ref_str);
            if target.is_some()
                && self
                    .failed
                    .as_ref()
                    .is_some_and(|f| f.contains(&(key.file_idx, path.clone())))
            {
                target = None;
                why = Some("failed the check (see the error at that reference)".to_string());
            }
            out.push((ref_str, target, why));
        }
        self.edges_cache.insert(key.clone(), out.clone());
        out
    }

    /// Local basis text or unknown reason (`records.py:Freshness.local`).
    #[must_use]
    pub fn local(&self, key: &RecordKey) -> (Option<String>, Option<String>) {
        let file = &self.checker.files[key.file_idx];
        let rec = file.get_record(&key.id).unwrap();
        let text = match local_part(rec, file) {
            Ok(t) => t,
            Err(why) => return (None, Some(why)),
        };
        if let Some(file_cites) = self.cites.get(&key.file_idx) {
            let named = referenced_registries(rec, file).unwrap_or_default();
            let mut bad: Vec<&Vec<PathElem>> = file_cites
                .iter()
                .filter(|p| {
                    (p.starts_with(&rec.path) && owns_citation(&rec.data, &rec.path, p))
                        || named.iter().any(|(_, _, _, at)| p.starts_with(at))
                })
                .collect();
            bad.sort_by_key(|p| python_tuple_repr(p));
            if let Some(first_bad) = bad.first() {
                return (
                    None,
                    Some(format!(
                        "{}: the citation at {} failed the check (see the error there)",
                        rec.full,
                        format_where(first_bad)
                    )),
                );
            }
        }
        (Some(text), None)
    }

    /// Computes bases for all `records` (`records.py:Freshness.all`).
    pub fn compute_all(&mut self, records: &[RecordKey]) {
        for r in records {
            let _ = self.edges(r);
        }
        let mut queue: Vec<RecordKey> = records.to_vec();
        let mut seen: HashSet<RecordKey> = records.iter().cloned().collect();
        while let Some(cur) = queue.pop() {
            for (_, t_opt, _) in self.edges(&cur) {
                if let Some(t) = t_opt {
                    if seen.insert(t.clone()) {
                        queue.push(t);
                    }
                }
            }
        }
        let edges_snapshot = self.edges_cache.clone();
        let mut bases = std::mem::take(&mut self.bases);
        compute_graph(
            records,
            |k| edges_snapshot.get(k).cloned().unwrap_or_default(),
            |k| self.local(k),
            &HashMap::new(),
            &mut bases,
        );
        self.bases = bases;
    }

    /// Returns `(Option<basis>, Option<why>)` for `key` (`records.py:Freshness.basis`).
    pub fn basis(&mut self, key: &RecordKey) -> (Option<String>, Option<String>) {
        if !self.bases.contains_key(key) {
            self.compute_all(std::slice::from_ref(key));
        }
        self.bases.get(key).cloned().unwrap_or((None, None))
    }

    /// Facts in other roots that `key` reaches through references staying in its own root until
    /// they cross: `{full_ref -> RecordKey}` (`records.py:Freshness.frontier`).
    pub fn frontier(&mut self, key: &RecordKey) -> BTreeMap<String, RecordKey> {
        let own_root = self.checker.files[key.file_idx].root_idx;
        let mut seen: HashSet<RecordKey> = HashSet::new();
        seen.insert(key.clone());
        let mut queue: Vec<RecordKey> = vec![key.clone()];
        let mut out: BTreeMap<String, RecordKey> = BTreeMap::new();
        while let Some(cur) = queue.pop() {
            for (_, t_opt, _) in self.edges(&cur) {
                let Some(t) = t_opt else {
                    continue;
                };
                let t_root = self.checker.files[t.file_idx].root_idx;
                if t_root != own_root {
                    out.insert(t.full.clone(), t);
                } else if seen.insert(t.clone()) {
                    queue.push(t);
                }
            }
        }
        out
    }

    /// Whether anything the `frontier` facts rest on, transitively, lies in `key`'s own root
    /// (`records.py:Freshness.returns_home`).
    pub fn returns_home(
        &mut self,
        key: &RecordKey,
        frontier: &BTreeMap<String, RecordKey>,
    ) -> bool {
        let own_root = self.checker.files[key.file_idx].root_idx;
        let mut seen: HashSet<RecordKey> = frontier.values().cloned().collect();
        let mut queue: Vec<RecordKey> = frontier.values().cloned().collect();
        while let Some(cur) = queue.pop() {
            for (_, t_opt, _) in self.edges(&cur) {
                let Some(t) = t_opt else {
                    continue;
                };
                if seen.contains(&t) {
                    continue;
                }
                let t_root = self.checker.files[t.file_idx].root_idx;
                if t_root == own_root {
                    return true;
                }
                seen.insert(t.clone());
                queue.push(t);
            }
        }
        false
    }

    /// `{full_ref: current_basis}` over the frontier, or `None` if any frontier basis is unknown
    /// (`records.py:Freshness.upstream_now`).
    pub fn upstream_now(&mut self, key: &RecordKey) -> Option<BTreeMap<String, String>> {
        let frontier = self.frontier(key);
        let mut out = BTreeMap::new();
        for (full, t) in frontier {
            let (b_opt, _) = self.basis(&t);
            let b = b_opt?;
            out.insert(full, b);
        }
        Some(out)
    }

    /// Computes `(Freshness, changed_upstream, unknown_reason)` for `key` and optional `verdict`
    /// (`records.py:Freshness.status`).
    pub fn status(
        &mut self,
        key: &RecordKey,
        verdict: Option<&Value>,
    ) -> (Freshness, Vec<String>, Option<String>) {
        let (basis_opt, why_opt) = self.basis(key);
        let Some(basis) = basis_opt else {
            return (Freshness::Unknown, Vec::new(), why_opt);
        };
        let Some(v) = verdict else {
            return (Freshness::Unverified, Vec::new(), None);
        };
        let v_basis = v.get("basis").and_then(Value::as_str).unwrap_or("");
        if v_basis == basis {
            return (Freshness::Current, Vec::new(), None);
        }
        let Some(recorded) = v.get("upstream").and_then(Value::as_object) else {
            return (Freshness::Stale, Vec::new(), None);
        };
        let frontier = self.frontier(key);
        if recorded.is_empty() {
            return (Freshness::Stale, Vec::new(), None);
        }
        let rec_keys: BTreeSet<&String> = recorded.keys().collect();
        let front_keys: BTreeSet<&String> = frontier.keys().collect();
        if rec_keys != front_keys {
            return (Freshness::Stale, Vec::new(), None);
        }
        if self.returns_home(key, &frontier) {
            return (Freshness::Stale, Vec::new(), None);
        }
        let mut fixed: HashMap<RecordKey, String> = HashMap::new();
        for (full, t) in &frontier {
            if let Some(b_str) = recorded.get(full).and_then(Value::as_str) {
                fixed.insert(t.clone(), b_str.to_string());
            }
        }
        // Ensure all reachable edges from `key` are cached.
        let _ = self.basis(key);
        let edges_snapshot = self.edges_cache.clone();
        let mut again: HashMap<RecordKey, (Option<String>, Option<String>)> = HashMap::new();
        compute_graph(
            std::slice::from_ref(key),
            |k| edges_snapshot.get(k).cloned().unwrap_or_default(),
            |k| self.local(k),
            &fixed,
            &mut again,
        );
        if again.get(key).and_then(|(b, _)| b.as_deref()) != Some(v_basis) {
            return (Freshness::Stale, Vec::new(), None);
        }
        let mut changed: Vec<String> = Vec::new();
        for (full, t) in &frontier {
            let (now_b, _) = self.basis(t);
            let rec_b = recorded.get(full).and_then(Value::as_str);
            if now_b.as_deref() != rec_b {
                changed.push(full.clone());
            }
        }
        changed.sort();
        if changed.is_empty() {
            return (Freshness::Stale, Vec::new(), None);
        }
        (Freshness::UpstreamStale, changed, None)
    }
}
// ---------------------------------------------------------------------------
// Embedded JSON Schemas & Schema Validation (`spec.py:validate_file`)
// ---------------------------------------------------------------------------

const SCHEMA_SPEC_STR: &str = include_str!("../skills/spec-format/schema/spec.schema.json");
const SCHEMA_ROOT_STR: &str = include_str!("../skills/spec-format/schema/root.schema.json");
const SCHEMA_VERIFY_STR: &str = include_str!("../skills/spec-format/schema/verify.schema.json");
const SCHEMA_CORPUS_STR: &str = include_str!("../skills/spec-format/schema/corpus.schema.json");
const SCHEMA_INDEX_STR: &str = include_str!("../skills/spec-format/schema/index.schema.json");

const EXTENSION_URN: &str = "urn:driver-lab:spec-format:2:extension:source-observed";

/// Loaded JSON Schemas (`spec`, `root`, `verify`, `corpus`, `index`).
#[derive(Debug, Clone)]
pub struct Schemas {
    /// Map of schema kind (`"spec"`, `"root"`, `"verify"`, `"corpus"`, `"index"`) to parsed JSON.
    pub by_kind: HashMap<String, Value>,
}

static DEFAULT_SCHEMAS: OnceLock<Schemas> = OnceLock::new();

/// Returns the embedded JSON schemas.
#[must_use]
pub fn load_schemas() -> &'static Schemas {
    DEFAULT_SCHEMAS.get_or_init(|| {
        let mut by_kind = HashMap::new();
        for (kind, raw) in [
            ("spec", SCHEMA_SPEC_STR),
            ("root", SCHEMA_ROOT_STR),
            ("verify", SCHEMA_VERIFY_STR),
            ("corpus", SCHEMA_CORPUS_STR),
            ("index", SCHEMA_INDEX_STR),
        ] {
            let val: Value = serde_json::from_str(raw).expect("embedded schema must be valid JSON");
            by_kind.insert(kind.to_string(), val);
        }
        Schemas { by_kind }
    })
}

struct SchemaRetriever {
    by_uri: HashMap<String, Value>,
}

impl Retrieve for SchemaRetriever {
    fn retrieve(
        &self,
        uri: &Uri<String>,
    ) -> Result<Value, Box<dyn std::error::Error + Send + Sync>> {
        self.by_uri
            .get(uri.as_str())
            .cloned()
            .ok_or_else(|| format!("schema URI not found: {uri}").into())
    }
}

fn default_extension_schema() -> Value {
    json!({
        "$id": EXTENSION_URN,
        "$comment": "message: a source-observed entry needs the extension's schema fragment; pass --root with a root marker whose extensions names it (D15)",
        "not": {}
    })
}

/// Determines the schema kind from a filename (`spec.py:schema_kind`).
pub fn schema_kind(path: &Path) -> Result<&'static str, String> {
    let name = path
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default();
    if name == MARKER {
        return Ok("root");
    }
    if name == CORPUS {
        return Ok("corpus");
    }
    if name.ends_with(".index.yaml") {
        return Ok("index");
    }
    if name.ends_with(".verify.yaml") {
        return Ok("verify");
    }
    if name.ends_with(".spec.yaml") || name.ends_with(".facts.yaml") {
        return Ok("spec");
    }
    Err(format!(
        "{}: cannot tell which schema applies; name the file *.spec.yaml, *.facts.yaml, *.verify.yaml, *.index.yaml, {MARKER} or {CORPUS}",
        path.display()
    ))
}

fn pointer_to_path_elems(pointer: &str, root_value: &Value) -> Vec<PathElem> {
    if pointer.is_empty() || pointer == "/" {
        return Vec::new();
    }
    let mut out = Vec::new();
    let mut cur = Some(root_value);
    for seg in pointer.trim_start_matches('/').split('/') {
        let unescaped = seg.replace("~1", "/").replace("~0", "~");
        match cur {
            Some(Value::Array(arr)) => {
                if let Ok(idx) = unescaped.parse::<usize>() {
                    out.push(PathElem::Index(idx));
                    cur = arr.get(idx);
                } else {
                    out.push(PathElem::Key(unescaped));
                    cur = None;
                }
            }
            Some(Value::Object(map)) => {
                cur = map.get(&unescaped);
                out.push(PathElem::Key(unescaped));
            }
            _ => {
                if let Ok(idx) = unescaped.parse::<usize>() {
                    out.push(PathElem::Index(idx));
                } else {
                    out.push(PathElem::Key(unescaped));
                }
                cur = None;
            }
        }
    }
    out
}

fn lookup_custom_message_in_schema(
    root_schema: &Value,
    schemas: &Schemas,
    schema_pointer: &str,
) -> Option<String> {
    let segs: Vec<String> = if schema_pointer.is_empty() || schema_pointer == "/" {
        Vec::new()
    } else {
        schema_pointer
            .trim_start_matches('/')
            .split('/')
            .map(|s| s.replace("~1", "/").replace("~0", "~"))
            .collect()
    };

    let mut cur = root_schema;
    let mut found_msg: Option<String> = None;

    let check_node = |node: &Value| -> Option<String> {
        let comment = node.get("$comment").and_then(Value::as_str)?;
        comment.strip_prefix("message: ").map(ToString::to_string)
    };

    if let Some(m) = check_node(cur) {
        found_msg = Some(m);
    }

    for seg in &segs {
        if seg == "$ref" {
            if let Some(ref_str) = cur.get("$ref").and_then(Value::as_str) {
                if let Some(resolved) = resolve_schema_ref(root_schema, schemas, ref_str) {
                    cur = resolved;
                    if let Some(m) = check_node(cur) {
                        found_msg = Some(m);
                    }
                }
            }
            continue;
        }

        if cur.get(seg).is_none() {
            if let Some(ref_str) = cur.get("$ref").and_then(Value::as_str) {
                if let Some(resolved) = resolve_schema_ref(root_schema, schemas, ref_str) {
                    cur = resolved;
                    if let Some(m) = check_node(cur) {
                        found_msg = Some(m);
                    }
                }
            }
        }

        match cur {
            Value::Object(map) => {
                if let Some(next) = map.get(seg) {
                    cur = next;
                } else {
                    break;
                }
            }
            Value::Array(arr) => {
                if let Ok(idx) = seg.parse::<usize>() {
                    if let Some(next) = arr.get(idx) {
                        cur = next;
                    } else {
                        break;
                    }
                } else {
                    break;
                }
            }
            _ => break,
        }
        if let Some(m) = check_node(cur) {
            found_msg = Some(m);
        }
    }
    found_msg
}

fn resolve_schema_ref<'a>(
    root_schema: &'a Value,
    schemas: &'a Schemas,
    ref_str: &str,
) -> Option<&'a Value> {
    let (doc, pointer) = match ref_str.split_once('#') {
        Some((d, p)) => (d, p),
        None => (ref_str, ""),
    };
    let mut node = if doc.is_empty() {
        root_schema
    } else {
        schemas.by_kind.values().find(|v| {
            v.get("$id")
                .and_then(Value::as_str)
                .is_some_and(|id| id == doc || id.ends_with(&format!("/{doc}")))
        })?
    };
    let trimmed = pointer.trim_start_matches('/');
    if !trimmed.is_empty() {
        for part in trimmed.split('/') {
            let unescaped = part.replace("~1", "/").replace("~0", "~");
            node = node.get(&unescaped)?;
        }
    }
    Some(node)
}

/// Validates a YAML file on disk against its JSON Schema (`spec.py:validate_file`).
/// Appends any syntax or schema findings to `findings`, returning `(ok, kind, Option<Loaded>)`.
pub fn validate_file(
    path: &Path,
    schemas: &Schemas,
    extension: Option<&Value>,
    findings: &mut Vec<Finding>,
) -> Result<(bool, &'static str, Option<Loaded>), String> {
    let kind = schema_kind(path)?;
    let before = findings.len();
    let path_str = path.to_string_lossy().into_owned();

    let loaded = yaml_strict::load_file(path);
    if !loaded.ok() {
        for err in &loaded.errors {
            findings.push(Finding::error(
                "YAML-STRICT",
                &path_str,
                err.line,
                err.column,
                err.message.clone(),
            ));
        }
        return Ok((false, kind, None));
    }

    let Some(data) = loaded.data.as_ref() else {
        findings.push(Finding::error(
            "YAML-EMPTY",
            &path_str,
            1,
            1,
            "empty YAML document",
        ));
        return Ok((false, kind, None));
    };

    let ext_for_kind = if kind == "root" { None } else { extension };
    let root_schema = &schemas.by_kind[kind];
    static DEFAULT_VALIDATORS: OnceLock<HashMap<String, jsonschema::Validator>> = OnceLock::new();
    let custom_validator;
    let validator: &jsonschema::Validator = if let Some(ext) = ext_for_kind {
        let mut by_uri = HashMap::new();
        for s in schemas.by_kind.values() {
            if let Some(id) = s.get("$id").and_then(Value::as_str) {
                by_uri.insert(id.to_string(), s.clone());
            }
        }
        let mut obj = ext.as_object().cloned().unwrap_or_default();
        obj.insert("$id".to_string(), Value::String(EXTENSION_URN.to_string()));
        by_uri.insert(EXTENSION_URN.to_string(), Value::Object(obj));
        custom_validator = jsonschema::draft202012::options()
            .with_retriever(SchemaRetriever { by_uri })
            .build(root_schema)
            .map_err(|e| format!("failed to build schema validator for {kind}: {e}"))?;
        &custom_validator
    } else {
        let map = DEFAULT_VALIDATORS.get_or_init(|| {
            let s_all = load_schemas();
            let mut base_by_uri = HashMap::new();
            for s in s_all.by_kind.values() {
                if let Some(id) = s.get("$id").and_then(Value::as_str) {
                    base_by_uri.insert(id.to_string(), s.clone());
                }
            }
            base_by_uri.insert(EXTENSION_URN.to_string(), default_extension_schema());
            let mut out = HashMap::new();
            for (k, rs) in &s_all.by_kind {
                let v = jsonschema::draft202012::options()
                    .with_retriever(SchemaRetriever {
                        by_uri: base_by_uri.clone(),
                    })
                    .build(rs)
                    .expect("embedded schema validator must build");
                out.insert(k.clone(), v);
            }
            out
        });
        &map[kind]
    };

    for error in validator.iter_errors(data) {
        let at = pointer_to_path_elems(error.instance_path.as_str(), data);
        let schema_ptr = error.schema_path.as_str();
        let custom = lookup_custom_message_in_schema(root_schema, schemas, schema_ptr);

        match &error.kind {
            ValidationErrorKind::PropertyNames { error: inner } => {
                if let Some(key_str) = inner.instance.as_str() {
                    let mut key_path = at.clone();
                    key_path.push(PathElem::Key(key_str.to_string()));
                    let yaml_segs: Vec<yaml_strict::PathSegment> =
                        key_path.iter().map(PathElem::to_yaml_segment).collect();
                    let mark = loaded.mark(&yaml_segs, Some(key_str));
                    let inner_custom = lookup_custom_message_in_schema(
                        root_schema,
                        schemas,
                        inner.schema_path.as_str(),
                    )
                    .or(custom);
                    let msg = inner_custom.unwrap_or_else(|| inner.to_string());
                    findings.push(Finding::error(
                        "SCHEMA-INVALID",
                        &path_str,
                        mark.line,
                        mark.column,
                        format!("{}: key '{key_str}': {msg}", format_where(&at)),
                    ));
                    continue;
                }
            }
            ValidationErrorKind::AdditionalProperties { unexpected }
            | ValidationErrorKind::UnevaluatedProperties { unexpected } => {
                for key_str in unexpected {
                    let mut key_path = at.clone();
                    key_path.push(PathElem::Key(key_str.clone()));
                    let yaml_segs: Vec<yaml_strict::PathSegment> =
                        key_path.iter().map(PathElem::to_yaml_segment).collect();
                    let mark = loaded.mark(&yaml_segs, Some(key_str));
                    findings.push(Finding::error(
                        "SCHEMA-UNKNOWN-KEY",
                        &path_str,
                        mark.line,
                        mark.column,
                        format!("{}: unknown key '{key_str}' here", format_where(&key_path)),
                    ));
                }
                continue;
            }
            _ => {}
        }

        let yaml_segs: Vec<yaml_strict::PathSegment> =
            at.iter().map(PathElem::to_yaml_segment).collect();
        let mark = loaded.mark(&yaml_segs, None);
        let message = if let Some(c) = custom {
            c
        } else {
            match &error.kind {
                ValidationErrorKind::Required { property } => {
                    let prop_name = property.as_str().unwrap_or("?");
                    format!("'{prop_name}' is a required property")
                }
                ValidationErrorKind::MinProperties { limit: 1 } => {
                    "{} should be non-empty".to_string()
                }
                ValidationErrorKind::MinItems { limit: 1 } => {
                    "[] should be non-empty".to_string()
                }
                _ => error.to_string(),
            }
        };
        findings.push(Finding::error(
            "SCHEMA-INVALID",
            &path_str,
            mark.line,
            mark.column,
            format!("{}: {message}", format_where(&at)),
        ));
    }

    if kind == "spec" {
        if let Some(doc_kind) = data.get("kind").and_then(Value::as_str) {
            let is_facts_name = path_str.ends_with(".facts.yaml");
            if is_facts_name != (doc_kind == "facts") {
                let mark = loaded.mark(&[yaml_strict::PathSegment::Key("kind".to_string())], None);
                let want = if is_facts_name {
                    "a *.facts.yaml file holds kind: facts"
                } else {
                    "kind: facts belongs in a *.facts.yaml file"
                };
                findings.push(Finding::error(
                    "SCHEMA-KIND",
                    &path_str,
                    mark.line,
                    mark.column,
                    format!("kind: {want}"),
                ));
            }
        }
    }

    let ok = findings.len() == before;
    Ok((ok, kind, Some(loaded)))
}
// ---------------------------------------------------------------------------
// Status & Check Report Structures (`spec.py:cmd_status`, `cmd_check`)
// ---------------------------------------------------------------------------

/// One verifiable item's status row in `status --json` (`records.py:second_pass`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StatusRow {
    /// Record key within the spec file (`"reset-cycles"` or `"ctrl.en"`).
    pub key: String,
    /// Full reference (`"<spec_id>@<root_name>#<key>"`).
    pub r#ref: String,
    /// Record kind (`"fact"`, `"instance"`, or `"variant"`).
    pub kind: String,
    /// Freshness status (`"current"`, `"stale"`, `"upstream-stale"`, `"unverified"`, `"unknown"`).
    pub status: String,
    /// Recorded verdict (`"PASS"`, `"FAIL"`, `"UNVERIFIABLE"`, `"GAP"`, `"ADJUDICATE"`, or `null`).
    pub verdict: Option<String>,
    /// Current `fact-v1` basis SHA-256 hex digest (or `null` when `status == "unknown"`).
    pub basis: Option<String>,
    /// Basis SHA-256 hex digest recorded in `.verify.yaml` (or `null` when unverified).
    pub recorded: Option<String>,
    /// Current upstream frontier map (`{full_ref: basis}`), or `null` when `basis` is `None`.
    pub upstream: Option<BTreeMap<String, String>>,
    /// Upstream references whose bases changed when `status == "upstream-stale"`.
    pub changed: Vec<String>,
    /// Reason string when `status == "unknown"`.
    pub reason: Option<String>,
    /// Second-reader state (`"not-needed"`, `"present"`, or `"missing"`).
    pub second_reader: String,
}

/// Per-spec-file entry in `Checker::status` and `status --json`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SpecStatusEntry {
    /// Spec file path.
    pub path: String,
    /// Owning root label.
    pub root: String,
    /// Spec identifier.
    pub spec: String,
    /// Relative path to `resources/<name>.verify.yaml` if present.
    pub record: Option<String>,
    /// Record state (`"none"`, `"ok"`, `"invalid"`, `"shared"`).
    pub state: String,
    /// Per-fact status rows.
    pub facts: Vec<StatusRow>,
}

/// Root summary entry in `check --json` and `status --json`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RootInfo {
    /// Given path string.
    pub path: String,
    /// Root name from `board-specs.yaml`.
    pub name: Option<String>,
    /// Root layer.
    pub layer: Option<String>,
    /// `true` if context root.
    pub context: bool,
}

/// Finding item formatted as `spec.py` JSON finding (`{"path", "line", "column", "level", "message"}`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SpecFinding {
    /// File path.
    pub path: String,
    /// 1-based line number.
    pub line: usize,
    /// 1-based column number.
    pub column: usize,
    /// `"error"` or `"warning"`.
    pub level: String,
    /// Diagnostic message.
    pub message: String,
}

impl fmt::Display for SpecFinding {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{}",
            visible_name(&format!(
                "{}:{}:{}: {}: {}",
                self.path, self.line, self.column, self.level, self.message
            ))
        )
    }
}

/// Result of running `check` (`spec.py:cmd_check`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CheckReport {
    /// Exit code (`0`, `1`, `2`, `3`).
    #[serde(skip)]
    pub exit_code: i32,
    /// `true` when 0 errors were found.
    pub ok: bool,
    /// Error category (`"usage"`, `"precondition"`, `"internal"`) when `exit_code >= 2`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    /// Checked and context roots.
    pub roots: Vec<RootInfo>,
    /// Number of loaded spec files.
    pub specs: usize,
    /// Number of checked stubs.
    pub stubs: usize,
    /// Freshness counts across checked roots (`current`, `stale`, `upstream-stale`, `unverified`, `unknown`).
    pub verification: BTreeMap<String, usize>,
    /// Ordered findings.
    pub findings: Vec<SpecFinding>,
    /// Human-readable output lines.
    #[serde(skip)]
    pub text_lines: Vec<String>,
}

/// Result of running `status` (`spec.py:cmd_status`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StatusReport {
    /// Exit code (`0`, `1`, `2`, `3`).
    #[serde(skip)]
    pub exit_code: i32,
    /// `true` when 0 errors were found.
    pub ok: bool,
    /// Error category (`"usage"`, `"precondition"`, `"internal"`) when `exit_code >= 2`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    /// Checked and context roots.
    pub roots: Vec<RootInfo>,
    /// Number of error findings.
    pub errors: usize,
    /// Number of warning findings.
    pub warnings: usize,
    /// Per-spec freshness entries (for checked roots).
    pub specs: Vec<SpecStatusEntry>,
    /// Ordered findings.
    pub findings: Vec<SpecFinding>,
    /// Human-readable output lines.
    #[serde(skip)]
    pub text_lines: Vec<String>,
}

// ---------------------------------------------------------------------------
// Checker (`speccheck.py:Checker` + `records.py:check_structure`, `first_pass`, `second_pass`)
// ---------------------------------------------------------------------------

fn ref_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"^(?:([a-z0-9][a-z0-9-]*)(?:@([a-z0-9][a-z0-9._-]*))?)?#([a-z0-9][a-z0-9-]*)$")
            .unwrap()
    })
}

fn digits_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[0-9]+$").unwrap())
}

fn through_link(path: &Path) -> bool {
    let mut cur = if path.is_absolute() {
        PathBuf::from("/")
    } else {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    };
    for comp in path.components() {
        use std::path::Component;
        match comp {
            Component::RootDir => cur = PathBuf::from("/"),
            Component::CurDir => {
                cur.push(".");
                if cur.is_symlink() {
                    return true;
                }
            }
            Component::ParentDir => {
                cur.push("..");
                if cur.is_symlink() {
                    return true;
                }
            }
            Component::Normal(part) => {
                cur.push(part);
                if cur.is_symlink() {
                    return true;
                }
            }
            Component::Prefix(_) => {}
        }
    }
    false
}

fn rel_to_root(root: &SpecRoot, path: &Path) -> String {
    path.strip_prefix(&root.given)
        .map(|p| p.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| path.to_string_lossy().into_owned())
}

fn rel_spec_file(root: &SpecRoot, file: &SpecFile) -> String {
    match file.path.strip_prefix(&root.given) {
        Ok(rel) => format!(
            "{}:{}",
            root.label(),
            rel.to_string_lossy().replace('\\', "/")
        ),
        Err(_) => file.path.to_string_lossy().into_owned(),
    }
}

fn record_kind_word(rec: &SpecRecord) -> &'static str {
    match rec.path.first() {
        Some(PathElem::Key(k)) if k == "instances" => "instance",
        Some(PathElem::Key(k)) if k == "variants" => "variant",
        _ => "fact",
    }
}

fn what_record(rec: &SpecRecord) -> String {
    format!("{} '{}'", record_kind_word(rec), rec.id)
}

fn untrusted_message(root: &SpecRoot) -> String {
    let (where_str, raw_reason) = &root.untrusted[0];
    let chars: Vec<char> = raw_reason.chars().collect();
    let reason = if chars.len() > 200 {
        let p: String = chars[..197].iter().collect();
        format!("{p}...")
    } else {
        raw_reason.clone()
    };
    format!(
        "root {}, which is untrusted: its own check found {} error(s) (first: {where_str}: {reason}); a reference may only rest on a root that checks clean",
        root.label(),
        root.untrusted.len()
    )
}

fn number_key(digits: &str) -> (usize, &str) {
    let trimmed = digits.trim_start_matches('0');
    let norm = if trimmed.is_empty() { "0" } else { trimmed };
    (norm.len(), norm)
}

fn short_repr(value: &str) -> String {
    let chars: Vec<char> = value.chars().collect();
    if chars.len() <= 24 {
        format!("'{value}'")
    } else {
        let head: String = chars[..12].iter().collect();
        let tail: String = chars[chars.len() - 6..].iter().collect();
        format!("'{head}...{tail}'")
    }
}


/// Full specification & verification-record checker (`speccheck.py:Checker` + `records.py`).
pub struct Checker {
    /// Verification policy (`None`, `Some("pr")`, or `Some("main")`).
    pub require_verified: Option<String>,
    /// Whether `--require-license` was set.
    pub require_license: bool,
    /// Public skills allowed in `via:` under a `public` root.
    pub public_skills: HashSet<String>,
    /// Loaded roots.
    pub roots: Vec<SpecRoot>,
    /// Loaded spec files.
    pub files: Vec<SpecFile>,
    /// Collected findings.
    pub findings: Vec<SpecFinding>,
    /// Number of checked stubs.
    pub stubs: usize,
    /// Markers that failed validation (making root-qualified references fail closed).
    pub unreadable_markers: Vec<PathBuf>,
    /// Cached `resolve(file_idx, ref_str)` results.
    pub resolved: std::cell::RefCell<HashMap<(usize, String), (Option<RecordKey>, Option<String>)>>,
    /// `(file_idx, path)` of references rejected by the checker.
    pub failed_refs: HashSet<(usize, Vec<PathElem>)>,
    /// `(file_idx, path)` of citations rejected by the checker.
    pub failed_cites: HashSet<(usize, Vec<PathElem>)>,
    /// Per-spec-file status entries populated by `second_pass`.
    pub status: Vec<(usize, SpecStatusEntry)>,
}

impl Checker {
    /// Creates a new [`Checker`].
    #[must_use]
    pub fn new(
        require_license: bool,
        public_skills: HashSet<String>,
        require_verified: Option<String>,
    ) -> Self {
        Self {
            require_verified,
            require_license,
            public_skills,
            roots: Vec::new(),
            files: Vec::new(),
            findings: Vec::new(),
            stubs: 0,
            unreadable_markers: Vec::new(),
            resolved: std::cell::RefCell::new(HashMap::new()),
            failed_refs: HashSet::new(),
            failed_cites: HashSet::new(),
            status: Vec::new(),
        }
    }

    /// Adds a finding on `file_idx` at `path`.
    pub fn add_file(
        &mut self,
        file_idx: usize,
        path: &[PathElem],
        message: impl Into<String>,
        level: &str,
        key: bool,
        downgrade: bool,
        trust: bool,
    ) {
        let file_path = self.files[file_idx].path.clone();
        let root_idx = self.files[file_idx].root_idx;
        let yaml_segs: Vec<yaml_strict::PathSegment> =
            path.iter().map(PathElem::to_yaml_segment).collect();
        let key_name = if key {
            match path.last() {
                Some(PathElem::Key(k)) => Some(k.as_str()),
                _ => None,
            }
        } else {
            None
        };
        let mark = self.files[file_idx].loaded.mark(&yaml_segs, key_name);
        self.add_raw(
            &file_path,
            Some(root_idx),
            mark.line,
            mark.column,
            message.into(),
            level,
            downgrade,
            trust,
        );
    }

    /// Adds a finding on an arbitrary path/loaded YAML document in `root_idx`.
    pub fn add_where(
        &mut self,
        file_path: &Path,
        root_idx: Option<usize>,
        loaded: Option<&Loaded>,
        path: &[PathElem],
        message: impl Into<String>,
        level: &str,
        key: bool,
        downgrade: bool,
        trust: bool,
    ) {
        let (line, column) = if let Some(ld) = loaded {
            let yaml_segs: Vec<yaml_strict::PathSegment> =
                path.iter().map(PathElem::to_yaml_segment).collect();
            let key_name = if key {
                match path.last() {
                    Some(PathElem::Key(k)) => Some(k.as_str()),
                    _ => None,
                }
            } else {
                None
            };
            let m = ld.mark(&yaml_segs, key_name);
            (m.line, m.column)
        } else {
            (1, 1)
        };
        self.add_raw(
            file_path,
            root_idx,
            line,
            column,
            message.into(),
            level,
            downgrade,
            trust,
        );
    }

    fn add_raw(
        &mut self,
        file_path: &Path,
        root_idx: Option<usize>,
        line: usize,
        column: usize,
        mut message: String,
        level: &str,
        downgrade: bool,
        trust: bool,
    ) {
        let path_str = file_path.to_string_lossy().into_owned();
        let mut final_level = level.to_string();
        if let Some(r_idx) = root_idx {
            if level == "error" && trust {
                self.roots[r_idx]
                    .untrusted
                    .push((format!("{path_str}:{line}:{column}"), message.clone()));
            }
            if self.roots[r_idx].context && downgrade {
                final_level = "warning".to_string();
                message = format!("context root: {message}");
            }
        }
        self.findings.push(SpecFinding {
            path: path_str,
            line,
            column,
            level: final_level,
            message,
        });
    }

    /// Rejects a reference or citation (`citation = true`) on `file_idx` at `path`.
    pub fn reject(
        &mut self,
        file_idx: usize,
        path: &[PathElem],
        message: impl Into<String>,
        citation: bool,
    ) {
        if citation {
            self.failed_cites.insert((file_idx, path.to_vec()));
        } else {
            self.failed_refs.insert((file_idx, path.to_vec()));
        }
        self.add_file(file_idx, path, message, "error", false, true, true);
    }

    fn add_schema_findings(&mut self, raw: Vec<Finding>, root_idx: Option<usize>, trust: bool) {
        for f in raw {
            self.add_raw(
                Path::new(&f.path),
                root_idx,
                f.line,
                f.col,
                f.message,
                "error",
                true,
                trust,
            );
        }
    }

    /// Loads `checked` and `context` roots (`speccheck.py:Checker.load_roots`).
    /// Returns `Err((exit_code, message))` on usage (`2`) or precondition (`3`) errors.
    pub fn load_roots(
        &mut self,
        checked: &[PathBuf],
        context: &[PathBuf],
        schemas: &Schemas,
    ) -> Result<(), (i32, String)> {
        let mut given: Vec<(PathBuf, bool)> = Vec::new();
        for p in checked {
            given.push((p.clone(), false));
        }
        for p in context {
            given.push((p.clone(), true));
        }
        for (p, _) in &given {
            if !p.is_dir() {
                return Err((EXIT_USAGE_ERROR, format!("{}: not a directory", p.display())));
            }
        }
        let mut reals: Vec<(PathBuf, PathBuf, bool)> = Vec::with_capacity(given.len());
        for (p, ctx) in given {
            let real = p.canonicalize().unwrap_or_else(|_| p.clone());
            reals.push((real, p, ctx));
        }
        for i in 0..reals.len() {
            for j in (i + 1)..reals.len() {
                let (a, pa, ca) = &reals[i];
                let (b, pb, cb) = &reals[j];
                if a == b {
                    return Err((
                        EXIT_USAGE_ERROR,
                        format!(
                            "{} and {} are the same root; give each root once",
                            pa.display(),
                            pb.display()
                        ),
                    ));
                }
                if a.starts_with(b) || b.starts_with(a) {
                    let (inner, outer) = if a.starts_with(b) { (pa, pb) } else { (pb, pa) };
                    let kind = if ca != cb {
                        "a context root and a checked root"
                    } else {
                        "two roots"
                    };
                    return Err((
                        EXIT_USAGE_ERROR,
                        format!(
                            "{} sits inside {}: {kind} must be separate directories",
                            inner.display(),
                            outer.display()
                        ),
                    ));
                }
            }
        }

        for (order, (real, p, ctx)) in reals.into_iter().enumerate() {
            let root = SpecRoot {
                given: p.clone(),
                real,
                context: ctx,
                order,
                name: None,
                layer: None,
                rank: 0,
                accepts: None,
                extension: None,
                marker: None,
                files: Vec::new(),
                spec_paths: Vec::new(),
                record_paths: Vec::new(),
                corpus_path: None,
                corpus: None,
                index_paths: Vec::new(),
                untrusted: Vec::new(),
            };
            if through_link(&p) {
                if ctx {
                    return Err((
                        EXIT_USAGE_ERROR,
                        format!(
                            "--context-root {} is, or is reached through, a symbolic link; give its real path",
                            p.display()
                        ),
                    ));
                }
                let r_idx = self.roots.len();
                self.roots.push(root);
                self.add_where(
                    &p,
                    Some(r_idx),
                    None,
                    &[],
                    "spec root is, or is reached through, a symbolic link: give its real path",
                    "error",
                    false,
                    true,
                    true,
                );
                continue;
            }
            if !p.join(MARKER).is_file() {
                return Err((
                    EXIT_SANDBOX_ERROR,
                    format!("{}: no {MARKER} (not a spec root)", p.display()),
                ));
            }
            let r_idx = self.roots.len();
            self.roots.push(root);
            self.read_marker(r_idx, schemas);
            let files = self.walk_root(r_idx)?;
            if self.roots[r_idx].accepts.is_none() {
                self.roots[r_idx].record_paths.clear();
                continue;
            }
            self.roots[r_idx].spec_paths = files.clone();
            for path in files {
                self.load_spec(r_idx, &path, schemas);
            }
        }
        Ok(())
    }

    fn read_marker(&mut self, root_idx: usize, schemas: &Schemas) {
        let marker_path = self.roots[root_idx].given.join(MARKER);
        let mut raw = Vec::new();
        let (ok, _, loaded_opt) = match validate_file(&marker_path, schemas, None, &mut raw) {
            Ok(res) => res,
            Err(msg) => {
                self.add_where(
                    &marker_path,
                    Some(root_idx),
                    None,
                    &[],
                    msg,
                    "error",
                    false,
                    true,
                    true,
                );
                self.unreadable_markers.push(marker_path);
                return;
            }
        };
        self.add_schema_findings(raw, Some(root_idx), true);
        let Some(loaded) = loaded_opt else {
            self.unreadable_markers.push(marker_path);
            return;
        };
        if !ok {
            self.unreadable_markers.push(marker_path);
            return;
        }
        let Some(data) = loaded.data.clone() else {
            self.unreadable_markers.push(marker_path);
            return;
        };
        let name = data
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let layer = data
            .get("layer")
            .and_then(Value::as_str)
            .unwrap_or("public")
            .to_string();
        let rank = LAYERS.iter().position(|&l| l == layer).unwrap_or(0);
        self.roots[root_idx].name = Some(name);
        self.roots[root_idx].layer = Some(layer);
        self.roots[root_idx].rank = rank;
        self.roots[root_idx].marker = Some(loaded.clone());
        if let Some(rel) = data
            .get("extensions")
            .and_then(Value::as_array)
            .and_then(|arr| arr.first())
            .and_then(|ext| ext.get("schema"))
            .and_then(Value::as_str)
        {
            if let Some(parent) = marker_path.parent() {
                let root_real = parent.canonicalize().unwrap_or_else(|_| parent.to_path_buf());
                let target = parent.join(rel);
                if let Ok(target_real) = target.canonicalize() {
                    if target_real.starts_with(&root_real) && target_real != root_real {
                        if let Ok(raw_json) = std::fs::read_to_string(&target_real) {
                            if let Ok(frag) = serde_json::from_str::<Value>(&raw_json) {
                                self.roots[root_idx].extension = Some(frag);
                            }
                        }
                    }
                }
            }
        }

        if let Some(lic) = data.get("license").and_then(Value::as_str) {
            if let Err(SpdxError(msg)) = spdx::parse(lic) {
                self.add_where(
                    &marker_path,
                    Some(root_idx),
                    Some(&loaded),
                    &[PathElem::from("license")],
                    format!("license: {msg}"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }
        let mut accepts = BTreeSet::new();
        let mut seen: HashMap<String, String> = HashMap::new();
        if let Some(arr) = data.get("accepts").and_then(Value::as_array) {
            for (i, item) in arr.iter().enumerate() {
                let Some(s) = item.as_str() else {
                    continue;
                };
                match spdx::parse_identifier(s) {
                    Ok(canon) => {
                        if canon != s {
                            self.add_where(
                                &marker_path,
                                Some(root_idx),
                                Some(&loaded),
                                &[PathElem::from("accepts"), PathElem::Index(i)],
                                format!(
                                    "accepts entry '{s}': write it as '{canon}', its one spelling"
                                ),
                                "error",
                                false,
                                true,
                                true,
                            );
                        }
                        if let Some(prev) = seen.get(&canon) {
                            self.add_where(
                                &marker_path,
                                Some(root_idx),
                                Some(&loaded),
                                &[PathElem::from("accepts"), PathElem::Index(i)],
                                format!("accepts lists {canon} twice (as '{prev}' and '{s}')"),
                                "error",
                                false,
                                true,
                                true,
                            );
                        } else {
                            seen.insert(canon.clone(), s.to_string());
                        }
                        accepts.insert(canon);
                    }
                    Err(SpdxError(msg)) => {
                        self.add_where(
                            &marker_path,
                            Some(root_idx),
                            Some(&loaded),
                            &[PathElem::from("accepts"), PathElem::Index(i)],
                            format!("accepts entry '{s}': {msg}"),
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }
            }
        }
        self.roots[root_idx].accepts = Some(accepts);
    }

    fn walk_root(&mut self, root_idx: usize) -> Result<Vec<PathBuf>, (i32, String)> {
        let root_given = self.roots[root_idx].given.clone();
        let is_ctx = self.roots[root_idx].context;
        let root_label = self.roots[root_idx].label();
        let mut found = Vec::new();
        let mut stack = vec![root_given.clone()];

        while let Some(top) = stack.pop() {
            let entries = match std::fs::read_dir(&top) {
                Ok(rd) => rd,
                Err(err) => {
                    self.add_where(
                        &top,
                        Some(root_idx),
                        None,
                        &[],
                        format!(
                            "cannot list this directory ({err}); the root's specs are not all known, so the check cannot pass"
                        ),
                        "error",
                        false,
                        false,
                        true,
                    );
                    continue;
                }
            };
            let mut dirs = Vec::new();
            let mut names = Vec::new();
            for entry in entries.flatten() {
                let path = entry.path();
                let name = entry.file_name().to_string_lossy().into_owned();
                let ft = match std::fs::symlink_metadata(&path) {
                    Ok(m) => m.file_type(),
                    Err(_) => continue,
                };
                if ft.is_symlink() {
                    if is_ctx {
                        return Err((
                            EXIT_USAGE_ERROR,
                            format!(
                                "--context-root {}: {} is a symbolic link; a root holds its files itself",
                                root_given.display(),
                                path.display()
                            ),
                        ));
                    }
                    self.add_where(
                        &path,
                        Some(root_idx),
                        None,
                        &[],
                        "symbolic link in a spec root: a root holds its files itself, never through links",
                        "error",
                        false,
                        true,
                        true,
                    );
                    continue;
                }
                if ft.is_dir() {
                    dirs.push((name, path));
                } else {
                    names.push((name, path));
                }
            }
            dirs.sort_by(|a, b| a.0.cmp(&b.0));
            names.sort_by(|a, b| a.0.cmp(&b.0));

            for (name, path) in names {
                let lower = name.to_ascii_lowercase();
                if name == MARKER && top != root_given {
                    self.add_where(
                        &path,
                        Some(root_idx),
                        None,
                        &[],
                        format!("a nested {MARKER} inside root {root_label}: one root, one marker"),
                        "error",
                        false,
                        true,
                        true,
                    );
                } else if name == CORPUS {
                    if top == root_given {
                        self.roots[root_idx].corpus_path = Some(path);
                    } else {
                        self.add_where(
                            &path,
                            Some(root_idx),
                            None,
                            &[],
                            format!("a corpus ledger lives beside the root's {MARKER}: move it there"),
                            "error",
                            false,
                            true,
                            false,
                        );
                    }
                } else if lower.starts_with("corpus.") || lower == "corpus" {
                    self.add_where(
                        &path,
                        Some(root_idx),
                        None,
                        &[],
                        format!(
                            "not read as a corpus ledger: name it {CORPUS} beside the root's {MARKER}, or move it out of the root"
                        ),
                        "error",
                        false,
                        true,
                        false,
                    );
                } else if name.ends_with(".spec.yaml") {
                    found.push(path);
                } else if name.ends_with(".index.yaml") {
                    if top == root_given.join("index") {
                        self.roots[root_idx].index_paths.push(path);
                    } else {
                        self.add_where(
                            &path,
                            Some(root_idx),
                            None,
                            &[],
                            "a document index lives in the root's own index/ directory: move it there",
                            "error",
                            false,
                            true,
                            false,
                        );
                    }
                } else if lower.contains(".index.") {
                    self.add_where(
                        &path,
                        Some(root_idx),
                        None,
                        &[],
                        "not read as a document index: name it <document>.index.yaml in index/",
                        "error",
                        false,
                        true,
                        false,
                    );
                } else if name.ends_with(".verify.yaml") {
                    if top == root_given.join("resources") {
                        self.roots[root_idx].record_paths.push(path);
                    } else {
                        self.add_where(
                            &path,
                            Some(root_idx),
                            None,
                            &[],
                            "a verification record lives in the root's own resources/ directory: move it there",
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                } else if lower.ends_with(".spec.md") {
                    self.add_where(
                        &path,
                        Some(root_idx),
                        None,
                        &[],
                        "a Markdown spec (.spec.md) is not read: specs are <name>.spec.yaml files",
                        "error",
                        false,
                        true,
                        true,
                    );
                } else if lower.contains(".spec.") || lower.contains(".facts.") {
                    let want = if lower.contains(".facts.") {
                        "a facts file does not belong in a spec root"
                    } else {
                        "name it *.spec.yaml (lowercase, .yaml), or move it out of the root"
                    };
                    self.add_where(
                        &path,
                        Some(root_idx),
                        None,
                        &[],
                        format!("not read as a spec: {want}"),
                        "error",
                        false,
                        true,
                        true,
                    );
                } else if lower.contains(".verify.")
                    || (top == root_given.join("resources") && lower.contains("verify"))
                {
                    self.add_where(
                        &path,
                        Some(root_idx),
                        None,
                        &[],
                        "not read as a verification record: name it <name>.verify.yaml (lowercase, .yaml) in resources/, or move it out of the root",
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }

            for (_, dpath) in dirs.into_iter().rev() {
                stack.push(dpath);
            }
        }
        Ok(found)
    }

    fn load_spec(&mut self, root_idx: usize, path: &Path, schemas: &Schemas) {
        let ext = self.roots[root_idx].extension.clone();
        let mut raw = Vec::new();
        let (ok, _, loaded_opt) = match validate_file(path, schemas, ext.as_ref(), &mut raw) {
            Ok(res) => res,
            Err(msg) => {
                self.add_where(
                    path,
                    Some(root_idx),
                    None,
                    &[],
                    msg,
                    "error",
                    false,
                    true,
                    true,
                );
                return;
            }
        };
        self.add_schema_findings(raw, Some(root_idx), true);
        if !ok {
            return;
        }
        let Some(loaded) = loaded_opt else {
            return;
        };
        let Some(data) = loaded.data.clone() else {
            return;
        };
        let file_idx = self.files.len();
        self.files.push(SpecFile {
            path: path.to_path_buf(),
            root_idx,
            loaded,
            data,
            records: Vec::new(),
            record_map: HashMap::new(),
            duplicated: HashSet::new(),
            assumptions: HashMap::new(),
            documents: HashMap::new(),
            repos: HashMap::new(),
            ambiguous: HashSet::new(),
            registries: HashMap::new(),
            record_state: "none".to_string(),
            record_path: None,
            record_loaded: None,
            verdicts: HashMap::new(),
        });
        self.roots[root_idx].files.push(file_idx);
    }

    /// Indexes all records, assumptions, documents, repos, and registries in `file_idx`
    /// (`speccheck.py:Checker.index_file`).
    pub fn index_file(&mut self, file_idx: usize) {
        let root_idx = self.files[file_idx].root_idx;
        let root_label = self.roots[root_idx].label();
        let spec_id = self.files[file_idx].spec_id();
        let data = self.files[file_idx].data.clone();

        let mut dup_messages = Vec::new();

        for key in ["facts", "instances", "variants"] {
            if let Some(arr) = data.get(key).and_then(Value::as_array) {
                for (i, item) in arr.iter().enumerate() {
                    let Some(rid) = item.get("id").and_then(Value::as_str) else {
                        continue;
                    };
                    if let Some(&existing_idx) = self.files[file_idx].record_map.get(rid) {
                        self.files[file_idx].duplicated.insert(rid.to_string());
                        let other_path = self.files[file_idx].records[existing_idx].1.path.clone();
                        dup_messages.push((
                            vec![PathElem::from(key), PathElem::Index(i), PathElem::from("id")],
                            format!(
                                "fact id '{rid}' is used twice in this file (first at {}); ids are the record's keys",
                                format_where(&other_path)
                            ),
                        ));
                        continue;
                    }
                    let path = vec![PathElem::from(key), PathElem::Index(i)];
                    let full = format!("{spec_id}@{root_label}#{rid}");
                    let rec = SpecRecord {
                        file_idx,
                        path,
                        data: item.clone(),
                        parent_id: None,
                        id: rid.to_string(),
                        full,
                    };
                    let rec_idx = self.files[file_idx].records.len();
                    self.files[file_idx].records.push((rid.to_string(), rec));
                    self.files[file_idx]
                        .record_map
                        .insert(rid.to_string(), rec_idx);
                }
            }
        }

        let parent_records: Vec<SpecRecord> = self.files[file_idx]
            .records
            .iter()
            .map(|(_, r)| r.clone())
            .collect();
        for parent in parent_records {
            for (mut child, path) in subrecords(&parent.data, &parent.path) {
                let Some(child_id) = child.get("id").and_then(Value::as_str) else {
                    continue;
                };
                let rid = format!("{}.{child_id}", parent.id);
                if self.files[file_idx].record_map.contains_key(&rid) {
                    self.files[file_idx].duplicated.insert(rid.clone());
                    let mut p = path;
                    p.push(PathElem::from("id"));
                    dup_messages.push((p, format!("sub-key '{rid}' is used twice")));
                } else {
                    if let Some(obj) = child.as_object_mut() {
                        obj.insert("id".to_string(), Value::String(rid.clone()));
                        if parent.data.get("critical").and_then(Value::as_bool) == Some(true) {
                            obj.insert("critical".to_string(), Value::Bool(true));
                        }
                    }
                    let full = format!("{spec_id}@{root_label}#{rid}");
                    let rec = SpecRecord {
                        file_idx,
                        path,
                        data: child,
                        parent_id: Some(parent.id.clone()),
                        id: rid.clone(),
                        full,
                    };
                    let rec_idx = self.files[file_idx].records.len();
                    self.files[file_idx].records.push((rid.clone(), rec));
                    self.files[file_idx].record_map.insert(rid, rec_idx);
                }
            }
        }

        if let Some(assumptions) = data.get("assumptions").and_then(Value::as_array) {
            for (i, item) in assumptions.iter().enumerate() {
                let Some(aid) = item.get("id").and_then(Value::as_str) else {
                    continue;
                };
                if self.files[file_idx].assumptions.contains_key(aid) {
                    self.files[file_idx].ambiguous.insert(AmbiguousItem::GroupName(
                        "assumptions".to_string(),
                        aid.to_string(),
                    ));
                    dup_messages.push((
                        vec![
                            PathElem::from("assumptions"),
                            PathElem::Index(i),
                            PathElem::from("id"),
                        ],
                        format!("assumption id '{aid}' is used twice in this file"),
                    ));
                } else {
                    self.files[file_idx].assumptions.insert(
                        aid.to_string(),
                        (
                            item.clone(),
                            vec![PathElem::from("assumptions"), PathElem::Index(i)],
                        ),
                    );
                }
            }
        }

        if let Some(resources) = data.get("resources").and_then(Value::as_object) {
            for group in ["documents", "repos"] {
                if let Some(arr) = resources.get(group).and_then(Value::as_array) {
                    for (i, entry) in arr.iter().enumerate() {
                        let Some(ename) = entry.get("name").and_then(Value::as_str) else {
                            continue;
                        };
                        let table = if group == "documents" {
                            &mut self.files[file_idx].documents
                        } else {
                            &mut self.files[file_idx].repos
                        };
                        if table.contains_key(ename) {
                            self.files[file_idx].ambiguous.insert(AmbiguousItem::GroupName(
                                group.to_string(),
                                ename.to_string(),
                            ));
                            dup_messages.push((
                                vec![
                                    PathElem::from("resources"),
                                    PathElem::from(group),
                                    PathElem::Index(i),
                                    PathElem::from("name"),
                                ],
                                format!("{group} entry '{ename}' is listed twice in this file"),
                            ));
                        } else {
                            table.insert(
                                ename.to_string(),
                                (
                                    entry.clone(),
                                    vec![
                                        PathElem::from("resources"),
                                        PathElem::from(group),
                                        PathElem::Index(i),
                                    ],
                                ),
                            );
                        }
                    }
                }
            }
        }

        for &group in REGISTRIES {
            self.files[file_idx]
                .registries
                .entry(group.to_string())
                .or_default();
            if let Some(arr) = data.get(group).and_then(Value::as_array) {
                for (i, entry) in arr.iter().enumerate() {
                    let Some(ename) = entry.get("name").and_then(Value::as_str) else {
                        continue;
                    };
                    let table = self.files[file_idx].registries.get_mut(group).unwrap();
                    if table.contains_key(ename) {
                        self.files[file_idx].ambiguous.insert(AmbiguousItem::GroupName(
                            group.to_string(),
                            ename.to_string(),
                        ));
                        dup_messages.push((
                            vec![
                                PathElem::from(group),
                                PathElem::Index(i),
                                PathElem::from("name"),
                            ],
                            format!("{group} entry '{ename}' is listed twice in this file"),
                        ));
                    } else {
                        table.insert(
                            ename.to_string(),
                            (
                                entry.clone(),
                                vec![PathElem::from(group), PathElem::Index(i)],
                            ),
                        );
                    }
                }
            }
        }

        let repo_entries: Vec<(String, Value, Vec<PathElem>)> = self.files[file_idx]
            .repos
            .iter()
            .map(|(k, (v, p))| (k.clone(), v.clone(), p.clone()))
            .collect();
        for (rname, entry, rpath) in repo_entries {
            let mut seen_paths = HashSet::new();
            if let Some(files_arr) = entry.get("files").and_then(Value::as_array) {
                for (i, item) in files_arr.iter().enumerate() {
                    let Some(fpath) = item.get("path").and_then(Value::as_str) else {
                        continue;
                    };
                    if !seen_paths.insert(fpath.to_string()) {
                        self.files[file_idx]
                            .ambiguous
                            .insert(AmbiguousItem::RepoFile(rname.clone(), fpath.to_string()));
                        let mut p = rpath.clone();
                        p.push(PathElem::from("files"));
                        p.push(PathElem::Index(i));
                        p.push(PathElem::from("path"));
                        dup_messages.push((
                            p,
                            format!("repos entry '{rname}' lists '{fpath}' twice in files"),
                        ));
                    }
                }
            }
        }

        for (p, msg) in dup_messages {
            self.add_file(file_idx, &p, msg, "error", false, true, true);
        }
    }

    fn gate_expr(&self, root_idx: usize, expression: &str) -> Option<String> {
        let tree = match spdx::parse(expression) {
            Ok(t) => t,
            Err(SpdxError(msg)) => {
                return Some(format!(
                    "its license '{expression}' is not an SPDX expression ({msg})"
                ));
            }
        };
        let accepts = self.roots[root_idx].accepts.clone().unwrap_or_default();
        if spdx::accepted(&tree, &accepts) {
            return None;
        }
        let shown = if accepts.is_empty() {
            "none: documents only".to_string()
        } else {
            accepts.into_iter().collect::<Vec<_>>().join(", ")
        };
        Some(format!(
            "{tree} is not accepted by root {} (accepts: {shown})",
            self.roots[root_idx].label()
        ))
    }

    fn gate_name(
        &mut self,
        file_idx: usize,
        path: &[PathElem],
        name: &str,
        what: &str,
        citation: bool,
    ) -> bool {
        let root_idx = self.files[file_idx].root_idx;
        let Some((repo_val, _)) = self.files[file_idx].repos.get(name).cloned() else {
            self.reject(
                file_idx,
                path,
                format!("{what} names repos entry '{name}', which is not in this file's resources.repos"),
                citation,
            );
            return false;
        };
        let lic = repo_val
            .get("license")
            .and_then(Value::as_str)
            .unwrap_or("");
        if let Some(reason) = self.gate_expr(root_idx, lic) {
            self.reject(
                file_idx,
                path,
                format!("{what} names repos entry '{name}': {reason}"),
                citation,
            );
        }
        true
    }

    /// Checks a single [`SpecFile`] (`speccheck.py:Checker.check_file`).
    pub fn check_file(&mut self, file_idx: usize) {
        let mut cited: HashSet<String> = HashSet::new();
        let top_records: Vec<SpecRecord> = self.files[file_idx]
            .records
            .iter()
            .filter(|(_, r)| r.path.len() == 2)
            .map(|(_, r)| r.clone())
            .collect();
        for rec in top_records {
            let what = what_record(&rec);
            self.check_support(file_idx, &what, &rec.data, &rec.path, &mut cited);
            if let Some(irq) = rec.data.get("irq").and_then(Value::as_object) {
                if let (Some(intid), Some(kind), Some(num)) = (
                    irq.get("intid").and_then(Value::as_i64),
                    irq.get("kind").and_then(Value::as_str),
                    irq.get("number").and_then(Value::as_i64),
                ) {
                    let offset = match kind {
                        "SPI" => Some(32),
                        "PPI" => Some(16),
                        _ => None,
                    };
                    if let Some(off) = offset {
                        let want = num + off;
                        if intid != want {
                            let mut p = rec.path.clone();
                            p.push(PathElem::from("irq"));
                            p.push(PathElem::from("intid"));
                            self.add_file(
                                file_idx,
                                &p,
                                format!("{what}: intid {intid} does not agree with {kind} {num} (INTID {want})"),
                                "error",
                                false,
                                true,
                                true,
                            );
                        }
                    }
                }
            }
        }

        let data = self.files[file_idx].data.clone();
        for &group in REGISTRIES {
            if let Some(arr) = data.get(group).and_then(Value::as_array) {
                for (i, entry) in arr.iter().enumerate() {
                    let path = vec![PathElem::from(group), PathElem::Index(i)];
                    let ename = entry.get("name").and_then(Value::as_str).unwrap_or("");
                    let what = format!("{} '{ename}'", registry_entry_label(group));
                    for (sup, mut at) in supports(entry, &path) {
                        if let Some(cls) = sup.get("class").and_then(Value::as_str) {
                            if cls == "inference" || cls == "emulated" {
                                at.push(PathElem::from("class"));
                                self.reject(
                                    file_idx,
                                    &at,
                                    format!("{what}: {cls} support names facts, which a registry entry cannot; cite the source"),
                                    true,
                                );
                            }
                        }
                    }
                    self.check_support(file_idx, &what, entry, &path, &mut cited);
                }
            }
        }

        if let Some(notices) = data.get("notices").and_then(Value::as_array) {
            for (i, notice) in notices.iter().enumerate() {
                if let Some(rname) = notice.get("repo").and_then(Value::as_str) {
                    cited.insert(rname.to_string());
                    self.gate_name(
                        file_idx,
                        &[
                            PathElem::from("notices"),
                            PathElem::Index(i),
                            PathElem::from("repo"),
                        ],
                        rname,
                        "a notice",
                        false,
                    );
                }
            }
        }

        let repo_entries: Vec<(String, Value, Vec<PathElem>)> = self.files[file_idx]
            .repos
            .iter()
            .map(|(k, (v, p))| (k.clone(), v.clone(), p.clone()))
            .collect();
        let root_idx = self.files[file_idx].root_idx;
        let req_lic = self.require_license;
        for (name, entry, mut path) in repo_entries {
            let lic = entry.get("license").and_then(Value::as_str).unwrap_or("");
            path.push(PathElem::from("license"));
            if let Err(SpdxError(msg)) = spdx::parse(lic) {
                self.add_file(
                    file_idx,
                    &path,
                    format!("repos entry '{name}': license: {msg}"),
                    "error",
                    false,
                    true,
                    true,
                );
                continue;
            }
            if req_lic && !cited.contains(&name) {
                if let Some(reason) = self.gate_expr(root_idx, lic) {
                    self.add_file(
                        file_idx,
                        &path,
                        format!(
                            "repos entry '{name}': {reason} (--require-license gates every repos entry, cited or not)"
                        ),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }

        if self.roots[root_idx].layer.as_deref() == Some("public") {
            if let Some(resources) = data.get("resources").and_then(Value::as_object) {
                for (group, entries_val) in resources {
                    if let Some(entries) = entries_val.as_array() {
                        for (i, entry) in entries.iter().enumerate() {
                            let label = entry
                                .get("name")
                                .or_else(|| entry.get("title"))
                                .and_then(Value::as_str)
                                .unwrap_or("");
                            let access = entry.get("access").and_then(Value::as_str);
                            if access == Some("private") {
                                self.add_file(
                                    file_idx,
                                    &[
                                        PathElem::from("resources"),
                                        PathElem::from(group.as_str()),
                                        PathElem::Index(i),
                                        PathElem::from("access"),
                                    ],
                                    format!("{group} entry '{label}': access: private under a public root"),
                                    "error",
                                    false,
                                    true,
                                    true,
                                );
                            } else if access == Some("members-only")
                                && entry.get("cite").and_then(Value::as_bool) != Some(false)
                            {
                                self.add_file(
                                    file_idx,
                                    &[
                                        PathElem::from("resources"),
                                        PathElem::from(group.as_str()),
                                        PathElem::Index(i),
                                        PathElem::from("access"),
                                    ],
                                    format!(
                                        "{group} entry '{label}': a members-only document under a public root is a map only: mark it cite: false, or move the spec to a root whose readers have access"
                                    ),
                                    "error",
                                    false,
                                    true,
                                    true,
                                );
                            }
                        }
                    }
                }
            }
        }
    }

    fn check_support(
        &mut self,
        file_idx: usize,
        what: &str,
        data: &Value,
        base: &[PathElem],
        cited: &mut HashSet<String>,
    ) {
        for (entry, path) in supports(data, base) {
            if entry.get("doc").is_some() {
                self.check_citation(file_idx, what, &entry, &path);
            }
        }
        for (anchor, path) in anchors(data, base) {
            if anchor.get("stale").is_some() {
                let mut p = path.clone();
                p.push(PathElem::from("stale"));
                self.add_file(
                    file_idx,
                    &p,
                    format!("{what}: stale anchor; re-verify and remove stale"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
            let Some(name) = anchor.get("repo").and_then(Value::as_str) else {
                continue;
            };
            cited.insert(name.to_string());
            if let Some(lines) = anchor.get("lines").and_then(Value::as_array) {
                if lines.len() == 2 {
                    if let (Some(l0), Some(l1)) = (lines[0].as_i64(), lines[1].as_i64()) {
                        if l0 > l1 {
                            let mut p = path.clone();
                            p.push(PathElem::from("lines"));
                            self.reject(
                                file_idx,
                                &p,
                                format!("{what}: lines [{l0}, {l1}] run backwards; write [first, last]"),
                                true,
                            );
                        }
                    }
                }
            }
            let mut repo_path = path.clone();
            repo_path.push(PathElem::from("repo"));
            if !self.gate_name(file_idx, &repo_path, name, &format!("{what}: an anchor"), true) {
                continue;
            }
            let (entry, _) = self.files[file_idx].repos[name].clone();
            if entry.get("commit").is_none() {
                self.reject(
                    file_idx,
                    &repo_path,
                    format!(
                        "{what}: anchor names repos entry '{name}', which pins a ref, not a commit; a cited entry carries the full commit"
                    ),
                    true,
                );
            }
            let listed: HashSet<String> = entry
                .get("files")
                .and_then(Value::as_array)
                .map(|arr| {
                    arr.iter()
                        .filter_map(|item| item.get("path").and_then(Value::as_str).map(ToString::to_string))
                        .collect()
                })
                .unwrap_or_default();
            if let Some(apath) = anchor.get("path").and_then(Value::as_str) {
                if !listed.contains(apath) {
                    let mut p = path.clone();
                    p.push(PathElem::from("path"));
                    self.reject(
                        file_idx,
                        &p,
                        format!(
                            "{what}: '{apath}' is not in the files of repos entry '{name}' (the closed list of cited paths, D12)"
                        ),
                        true,
                    );
                }
            }
        }

        let mut names: Vec<(String, Vec<PathElem>)> = Vec::new();
        if let Some(assumes) = data.get("assumes").and_then(Value::as_array) {
            for (i, a) in assumes.iter().enumerate() {
                if let Some(s) = a.as_str() {
                    let mut p = base.to_vec();
                    p.push(PathElem::from("assumes"));
                    p.push(PathElem::Index(i));
                    names.push((s.to_string(), p));
                }
            }
        }
        for (entry, at) in supports(data, base) {
            if let Some(premises) = entry.get("premises").and_then(Value::as_array) {
                for (j, premise) in premises.iter().enumerate() {
                    if let Some(s) = premise.get("assumption").and_then(Value::as_str) {
                        let mut p = at.clone();
                        p.push(PathElem::from("premises"));
                        p.push(PathElem::Index(j));
                        p.push(PathElem::from("assumption"));
                        names.push((s.to_string(), p));
                    }
                }
            }
        }
        for (name, path) in names {
            if !self.files[file_idx].assumptions.contains_key(&name) {
                self.reject(
                    file_idx,
                    &path,
                    format!("{what}: assumption '{name}' is not in this file's assumptions"),
                    true,
                );
            }
        }
    }

    fn check_citation(
        &mut self,
        file_idx: usize,
        what: &str,
        entry: &Value,
        path: &[PathElem],
    ) {
        let Some(name) = entry.get("doc").and_then(Value::as_str) else {
            return;
        };
        let cls = entry.get("class").and_then(Value::as_str).unwrap_or("");
        let mut doc_path = path.to_vec();
        doc_path.push(PathElem::from("doc"));

        let Some((doc, _)) = self.files[file_idx].documents.get(name).cloned() else {
            self.reject(
                file_idx,
                &doc_path,
                format!("{what}: document '{name}' is not in this file's resources.documents"),
                true,
            );
            return;
        };
        if doc.get("cite").and_then(Value::as_bool) == Some(false) {
            self.reject(
                file_idx,
                &doc_path,
                format!(
                    "{what}: document '{name}' is marked cite: false (a map only); it cannot be cited"
                ),
                true,
            );
        }
        let doc_cls = doc.get("class").and_then(Value::as_str).unwrap_or("");
        if matches!(cls, "databook" | "standard" | "doc") && doc_cls != cls {
            self.reject(
                file_idx,
                &doc_path,
                format!("{what}: a {cls} citation names document '{name}' of class {doc_cls}"),
                true,
            );
        }
        let count = doc.get("pages").and_then(Value::as_i64);
        if let Some(at_arr) = entry.get("at").and_then(Value::as_array) {
            for (i, loc) in at_arr.iter().enumerate() {
                let mut lpath = path.to_vec();
                lpath.push(PathElem::from("at"));
                lpath.push(PathElem::Index(i));
                let has_precise = ["section", "page", "pages", "table", "figure", "clause"]
                    .iter()
                    .any(|k| loc.get(*k).is_some());
                if cls == "standard" && count.is_some() && !has_precise {
                    self.reject(
                        file_idx,
                        &lpath,
                        format!(
                            "{what}: document '{name}' is paged, so a standard locator needs a section, page, pages, table, figure or clause, not a heading alone"
                        ),
                        true,
                    );
                }
                let mut numbers: Vec<(String, Vec<PathElem>)> = Vec::new();
                if let Some(pg) = loc.get("page").and_then(Value::as_str) {
                    let mut p = lpath.clone();
                    p.push(PathElem::from("page"));
                    numbers.push((pg.to_string(), p));
                }
                if let Some(pgs) = loc.get("pages").and_then(Value::as_array) {
                    for (k, pval) in pgs.iter().enumerate() {
                        if let Some(pg) = pval.as_str() {
                            let mut p = lpath.clone();
                            p.push(PathElem::from("pages"));
                            p.push(PathElem::Index(k));
                            numbers.push((pg.to_string(), p));
                        }
                    }
                }
                for (value, vpath) in numbers {
                    if !digits_regex().is_match(&value) {
                        continue;
                    }
                    if value.len() > 1 && value.starts_with('0') {
                        let stripped = value.trim_start_matches('0');
                        let norm = if stripped.is_empty() { "0" } else { stripped };
                        self.reject(
                            file_idx,
                            &vpath,
                            format!(
                                "{what}: page {}: write {} (no leading zeros)",
                                short_repr(&value),
                                short_repr(norm)
                            ),
                            true,
                        );
                    }
                    if let Some(c) = count {
                        let c_str = c.to_string();
                        if !(number_key(&value) >= number_key("1")
                            && number_key(&value) <= number_key(&c_str))
                        {
                            self.reject(
                                file_idx,
                                &vpath,
                                format!(
                                    "{what}: page {} is outside the {c} pages of document '{name}'",
                                    short_repr(&value)
                                ),
                                true,
                            );
                        }
                    }
                }
                if let Some(pgs) = loc.get("pages").and_then(Value::as_array) {
                    if pgs.len() == 2 {
                        if let (Some(p0), Some(p1)) = (pgs[0].as_str(), pgs[1].as_str()) {
                            if digits_regex().is_match(p0)
                                && digits_regex().is_match(p1)
                                && number_key(p0) > number_key(p1)
                            {
                                let mut p = lpath;
                                p.push(PathElem::from("pages"));
                                self.reject(
                                    file_idx,
                                    &p,
                                    format!(
                                        "{what}: pages [{}, {}] run backwards; write [first, last]",
                                        short_repr(p0),
                                        short_repr(p1)
                                    ),
                                    true,
                                );
                            }
                        }
                    }
                }
            }
        }
    }

    /// Loads and checks all `.verify.yaml` records across every root (`records.py:check_structure`).
    pub fn check_structure(&mut self, schemas: &Schemas) {
        let mut by_path: HashMap<PathBuf, usize> = HashMap::new();
        for (idx, f) in self.files.iter().enumerate() {
            by_path.insert(f.path.clone(), idx);
        }

        for root_idx in 0..self.roots.len() {
            let spec_paths = self.roots[root_idx].spec_paths.clone();
            let mut stems: BTreeMap<String, Vec<PathBuf>> = BTreeMap::new();
            for p in &spec_paths {
                let fname = p
                    .file_name()
                    .map(|s| s.to_string_lossy().into_owned())
                    .unwrap_or_default();
                let stem = fname.strip_suffix(SPEC_SUFFIX).unwrap_or(&fname).to_string();
                stems.entry(stem).or_default().push(p.clone());
            }
            for (stem, paths) in &stems {
                if paths.len() > 1 {
                    for p in paths {
                        let others: Vec<String> = paths
                            .iter()
                            .filter(|q| *q != p)
                            .map(|q| rel_to_root(&self.roots[root_idx], q))
                            .collect();
                        let msg = format!(
                            "this file and {} would share the verification record resources/{stem}{RECORD_SUFFIX}; give spec files distinct names",
                            others.join(", ")
                        );
                        if let Some(&f_idx) = by_path.get(p) {
                            self.add_file(f_idx, &[], msg, "error", false, true, true);
                            self.files[f_idx].record_state = "shared".to_string();
                        } else {
                            self.add_where(
                                p,
                                Some(root_idx),
                                None,
                                &[],
                                msg,
                                "error",
                                false,
                                true,
                                true,
                            );
                        }
                    }
                }
            }

            let record_paths = self.roots[root_idx].record_paths.clone();
            for rpath in record_paths {
                self.check_verify_record(schemas, root_idx, &rpath, &stems, &by_path);
            }
        }
    }

    fn check_verify_record(
        &mut self,
        schemas: &Schemas,
        root_idx: usize,
        rpath: &Path,
        stems: &BTreeMap<String, Vec<PathBuf>>,
        by_path: &HashMap<PathBuf, usize>,
    ) {
        let mut raw = Vec::new();
        let (ok, _, loaded_opt) = match validate_file(rpath, schemas, None, &mut raw) {
            Ok(res) => res,
            Err(msg) => {
                self.add_where(
                    rpath,
                    Some(root_idx),
                    None,
                    &[],
                    msg,
                    "error",
                    false,
                    true,
                    true,
                );
                return;
            }
        };
        self.add_schema_findings(raw, Some(root_idx), true);

        let fname = rpath
            .file_name()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_default();
        let stem = fname.strip_suffix(RECORD_SUFFIX).unwrap_or(&fname);
        let owners = stems.get(stem).cloned().unwrap_or_default();

        if owners.is_empty() {
            let path_at = if ok {
                vec![PathElem::from("spec_file")]
            } else {
                Vec::new()
            };
            let root_label = self.roots[root_idx].label();
            self.add_where(
                rpath,
                Some(root_idx),
                loaded_opt.as_ref(),
                &path_at,
                format!(
                    "no spec file named {stem}{SPEC_SUFFIX} in root {root_label}: a record belongs to the spec file of its name"
                ),
                "error",
                false,
                true,
                true,
            );
            return;
        }
        if owners.len() > 1 {
            return;
        }
        let Some(&f_idx) = by_path.get(&owners[0]) else {
            return;
        };
        self.files[f_idx].record_path = Some(rpath.to_path_buf());
        if !ok {
            self.files[f_idx].record_state = "invalid".to_string();
            return;
        }
        let Some(loaded) = loaded_opt else {
            self.files[f_idx].record_state = "invalid".to_string();
            return;
        };
        let Some(data) = loaded.data.clone() else {
            self.files[f_idx].record_state = "invalid".to_string();
            return;
        };

        let rel = rel_to_root(&self.roots[root_idx], &self.files[f_idx].path);
        let spec_file_val = data.get("spec_file").and_then(Value::as_str).unwrap_or("");
        if spec_file_val != rel {
            self.add_where(
                rpath,
                Some(root_idx),
                Some(&loaded),
                &[PathElem::from("spec_file")],
                format!(
                    "spec_file '{spec_file_val}': this record belongs to '{rel}', the spec file of its name"
                ),
                "error",
                false,
                true,
                true,
            );
        }
        let spec_val = data.get("spec").and_then(Value::as_str).unwrap_or("");
        let f_spec_id = self.files[f_idx].spec_id();
        let is_ov = self.files[f_idx].is_overlay();
        if spec_val != f_spec_id {
            let kind_phrase = if is_ov { "an overlay of" } else { "spec" };
            self.add_where(
                rpath,
                Some(root_idx),
                Some(&loaded),
                &[PathElem::from("spec")],
                format!("spec '{spec_val}': the spec file '{rel}' is {kind_phrase} '{f_spec_id}'"),
                "error",
                false,
                true,
                true,
            );
        }

        if let Some(sources_arr) = data.get("sources").and_then(Value::as_array) {
            let spec_docs = self.files[f_idx]
                .data
                .get("resources")
                .and_then(|r| r.get("documents"))
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            for (s_idx, src_entry) in sources_arr.iter().enumerate() {
                let Some(src_obj) = src_entry.as_object() else {
                    continue;
                };
                if !src_obj.contains_key("commit") && !src_obj.contains_key("sha256") {
                    let src_name = src_obj.get("name").and_then(Value::as_str).unwrap_or("");
                    let matches_unpinned_doc = spec_docs.iter().any(|d| {
                        d.get("name").and_then(Value::as_str) == Some(src_name)
                            && !d.as_object().is_some_and(|m| m.contains_key("sha256"))
                            && d.get("fetch").and_then(Value::as_str) == Some("ok")
                    });
                    if !matches_unpinned_doc {
                        self.add_where(
                            rpath,
                            Some(root_idx),
                            Some(&loaded),
                            &[PathElem::from("sources"), PathElem::from(s_idx)],
                            format!(
                                "source '{src_name}' without commit or sha256 must name an unpinned fetch: ok document in '{rel}'"
                            ),
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }
            }
        }

        self.files[f_idx].record_state = "ok".to_string();
        let mut counts: HashMap<String, i64> = SUMMARY
            .iter()
            .map(|&(_, v)| (v.to_string(), 0))
            .collect();

        if let Some(verdicts_map) = data.get("verdicts").and_then(Value::as_object) {
            for (key, v) in verdicts_map {
                let v_str = v.get("verdict").and_then(Value::as_str).unwrap_or("");
                if let Some(c) = counts.get_mut(v_str) {
                    *c += 1;
                }
                let kpath = vec![PathElem::from("verdicts"), PathElem::Key(key.clone())];
                let (fid, sub_opt) = match key.split_once('.') {
                    Some((a, b)) => (a, Some(b)),
                    None => (key.as_str(), None),
                };
                if self.files[f_idx].duplicated.contains(fid) {
                    self.add_where(
                        rpath,
                        Some(root_idx),
                        Some(&loaded),
                        &kpath,
                        format!(
                            "verdict key '{key}': fact id '{fid}' is declared twice in {rel}, so the key is ambiguous"
                        ),
                        "error",
                        true,
                        true,
                        true,
                    );
                    continue;
                }
                if !self.files[f_idx].record_map.contains_key(fid) {
                    self.add_where(
                        rpath,
                        Some(root_idx),
                        Some(&loaded),
                        &kpath,
                        format!("verdict key '{key}' names no fact, instance or variant of {rel}"),
                        "error",
                        true,
                        true,
                        true,
                    );
                    continue;
                }
                if let Some(sub) = sub_opt {
                    if !self.files[f_idx].record_map.contains_key(key)
                        || self.files[f_idx].duplicated.contains(key)
                    {
                        self.add_where(
                            rpath,
                            Some(root_idx),
                            Some(&loaded),
                            &kpath,
                            format!(
                                "verdict key '{key}': '{fid}' has no field or step '{sub}' with its own support (a sub-key names a register field or sequence step, D16)"
                            ),
                            "error",
                            true,
                            true,
                            true,
                        );
                        continue;
                    }
                }

                let rec = self.files[f_idx].get_record(key).unwrap().clone();
                let mut vpath = kpath.clone();
                vpath.push(PathElem::from("verdict"));
                if rec.path.first() == Some(&PathElem::from("facts")) {
                    let gap = !has_support(&rec.data);
                    if gap && v_str != "GAP" {
                        self.add_where(
                            rpath,
                            Some(root_idx),
                            Some(&loaded),
                            &vpath,
                            format!(
                                "verdict {v_str} for '{fid}', a gap fact (no support): its verdict is GAP"
                            ),
                            "error",
                            false,
                            true,
                            true,
                        );
                    } else if !gap && v_str == "GAP" {
                        self.add_where(
                            rpath,
                            Some(root_idx),
                            Some(&loaded),
                            &vpath,
                            format!(
                                "verdict GAP for '{fid}', which has support: GAP is a gap fact's verdict"
                            ),
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                } else if v_str == "GAP" {
                    self.add_where(
                        rpath,
                        Some(root_idx),
                        Some(&loaded),
                        &vpath,
                        format!(
                            "verdict GAP for {}: GAP is a gap fact's verdict, and an instance or variant row is never a gap",
                            what_record(&rec)
                        ),
                        "error",
                        false,
                        true,
                        true,
                    );
                }

                if v_str != "ADJUDICATE" {
                    if let Some(readers) = v.get("readers").and_then(Value::as_array) {
                        for (i, reader) in readers.iter().enumerate() {
                            let r_verdict =
                                reader.get("verdict").and_then(Value::as_str).unwrap_or("");
                            if r_verdict != v_str {
                                let mut rpath_at = kpath.clone();
                                rpath_at.push(PathElem::from("readers"));
                                rpath_at.push(PathElem::Index(i));
                                rpath_at.push(PathElem::from("verdict"));
                                self.add_where(
                                    rpath,
                                    Some(root_idx),
                                    Some(&loaded),
                                    &rpath_at,
                                    format!(
                                        "verdict key '{key}': a reader's verdict {r_verdict} disagrees with {v_str}; record the disagreement as ADJUDICATE with readings"
                                    ),
                                    "error",
                                    false,
                                    true,
                                    true,
                                );
                            }
                        }
                    }
                }
                self.files[f_idx]
                    .verdicts
                    .insert(key.clone(), (v.clone(), kpath));
            }
        }

        if let Some(sum_obj) = data.get("summary").and_then(Value::as_object) {
            for &(name, value) in SUMMARY {
                let got = sum_obj.get(name).and_then(Value::as_i64).unwrap_or(0);
                let want = counts.get(value).copied().unwrap_or(0);
                if got != want {
                    self.add_where(
                        rpath,
                        Some(root_idx),
                        Some(&loaded),
                        &[PathElem::from("summary"), PathElem::from(name)],
                        format!("summary {name}: {got}, but {want} verdict(s) are {value}"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }
        self.files[f_idx].record_loaded = Some(loaded);
    }

    /// Resolves a fact reference (`#id`, `spec#id`, `spec@root#id`) from `file_idx`
    /// (`speccheck.py:Checker.resolve`).


    #[must_use]
    pub fn resolve(
        &self,
        file_idx: usize,
        ref_str: &str,
    ) -> (Option<RecordKey>, Option<String>) {
        let key = (file_idx, ref_str.to_string());
        if let Some(res) = self.resolved.borrow().get(&key) {
            return res.clone();
        }
        let res = self._resolve(file_idx, ref_str);
        self.resolved.borrow_mut().insert(key, res.clone());
        res
    }

    #[must_use]
    pub fn _resolve(


        &self,
        file_idx: usize,
        ref_str: &str,
    ) -> (Option<RecordKey>, Option<String>) {
        let Some(caps) = ref_regex().captures(ref_str) else {
            return (
                None,
                Some(format!("is not a valid fact reference '{ref_str}'")),
            );
        };
        let spec_id_opt = caps.get(1).map(|m| m.as_str());
        let root_name_opt = caps.get(2).map(|m| m.as_str());
        let fact_id = caps.get(3).unwrap().as_str();

        let f = &self.files[file_idx];
        if spec_id_opt.is_none() {
            if f.duplicated.contains(fact_id) {
                return (
                    None,
                    Some(format!(
                        "is ambiguous: this file declares fact '{fact_id}' twice"
                    )),
                );
            }
            if let Some(rec) = f.get_record(fact_id) {
                return (
                    Some(RecordKey {
                        file_idx,
                        id: rec.id.clone(),
                        full: rec.full.clone(),
                    }),
                    None,
                );
            }
            return (
                None,
                Some(format!(
                    "resolves to nothing: no fact '{fact_id}' in this file"
                )),
            );
        }

        let spec_id = spec_id_opt.unwrap();
        if let Some(root_name) = root_name_opt {
            if let Some(first_unreadable) = self.unreadable_markers.first() {
                return (
                    None,
                    Some(format!(
                        "cannot be resolved: the marker {} could not be read, so that root's name is unknown and could be '{root_name}'; every root-qualified reference fails closed",
                        first_unreadable.display()
                    )),
                );
            }
        }

        let matching_roots: Vec<usize> = if let Some(root_name) = root_name_opt {
            self.roots
                .iter()
                .enumerate()
                .filter_map(|(idx, r)| {
                    if r.name.as_deref() == Some(root_name) {
                        Some(idx)
                    } else {
                        None
                    }
                })
                .collect()
        } else {
            vec![f.root_idx]
        };

        if matching_roots.is_empty() {
            let root_name = root_name_opt.unwrap_or("");
            return (
                None,
                Some(format!(
                    "resolves to nothing: no root named '{root_name}' among the roots read (a renamed root leaves every reference to it dangling)"
                )),
            );
        }
        if matching_roots.len() > 1 {
            let root_name = root_name_opt.unwrap_or("");
            let places: Vec<String> = matching_roots
                .iter()
                .map(|&idx| self.roots[idx].given.to_string_lossy().into_owned())
                .collect();
            return (
                None,
                Some(format!(
                    "is ambiguous: {} roots read are named '{root_name}' ({})",
                    matching_roots.len(),
                    places.join(", ")
                )),
            );
        }

        let target_root_idx = matching_roots[0];
        let target_root = &self.roots[target_root_idx];
        if target_root_idx != f.root_idx && !target_root.untrusted.is_empty() {
            return (
                None,
                Some(format!(
                    "cannot be resolved: {}",
                    untrusted_message(target_root)
                )),
            );
        }

        let owners: Vec<usize> = target_root
            .files
            .iter()
            .copied()
            .filter(|&g_idx| self.files[g_idx].spec_id() == spec_id)
            .collect();
        let found: Vec<&SpecRecord> = owners
            .iter()
            .filter_map(|&g_idx| self.files[g_idx].get_record(fact_id))
            .collect();
        if found.len() > 1
            || owners
                .iter()
                .any(|&g_idx| self.files[g_idx].duplicated.contains(fact_id))
        {
            let places: Vec<String> = found
                .iter()
                .map(|r| rel_spec_file(&self.roots[self.files[r.file_idx].root_idx], &self.files[r.file_idx]))
                .collect();
            return (
                None,
                Some(format!(
                    "is ambiguous: spec '{spec_id}' declares fact '{fact_id}' more than once in root {} ({})",
                    target_root.label(),
                    places.join(", ")
                )),
            );
        }
        if let Some(rec) = found.first() {
            return (
                Some(RecordKey {
                    file_idx: rec.file_idx,
                    id: rec.id.clone(),
                    full: rec.full.clone(),
                }),
                None,
            );
        }

        let mut where_msg = if !owners.is_empty() {
            format!(
                "resolves to nothing: spec '{spec_id}' has no fact '{fact_id}' in root {}",
                target_root.label()
            )
        } else {
            format!(
                "resolves to nothing: root {} holds no spec '{spec_id}'",
                target_root.label()
            )
        };

        if root_name_opt.is_none() {
            if let Some(other_file) = self.files.iter().find(|g| {
                g.root_idx != target_root_idx
                    && g.spec_id() == spec_id
                    && g.record_map.contains_key(fact_id)
            }) {
                let other_label = self.roots[other_file.root_idx].label();
                where_msg.push_str(&format!(
                    "; it is in root {other_label}, and a reference into another root names it: {spec_id}@{other_label}#{fact_id}"
                ));
            }
        }
        (None, Some(where_msg))
    }

    fn reach_repos(
        &self,
        start: &RecordKey,
    ) -> (
        Vec<((usize, String), RecordKey)>,
        Vec<(RecordKey, String, String)>,
    ) {
        let mut out_map: HashMap<(usize, String), RecordKey> = HashMap::new();
        let mut problems: Vec<(RecordKey, String, String)> = Vec::new();
        let mut seen: HashSet<RecordKey> = HashSet::new();
        seen.insert(start.clone());
        let mut queue: VecDeque<RecordKey> = VecDeque::new();
        queue.push_back(start.clone());

        while let Some(cur) = queue.pop_front() {
            let file = &self.files[cur.file_idx];
            let rec = file.get_record(&cur.id).unwrap();
            for (anchor, _) in anchors(&rec.data, &rec.path) {
                if let Some(rname) = anchor.get("repo").and_then(Value::as_str) {
                    out_map
                        .entry((cur.file_idx, rname.to_string()))
                        .or_insert_with(|| cur.clone());
                }
            }
            for (_, ref_str, _) in parse_refs(&rec.data, &rec.path) {
                let (target_opt, why_opt) = self.resolve(cur.file_idx, &ref_str);
                match target_opt {
                    None => {
                        problems.push((
                            cur.clone(),
                            ref_str,
                            why_opt.unwrap_or_else(|| "failed".to_string()),
                        ));
                    }
                    Some(t) => {
                        if seen.insert(t.clone()) {
                            queue.push_back(t);
                        }
                    }
                }
            }
        }

        let mut reached: Vec<((usize, String), RecordKey)> = out_map.into_iter().collect();
        reached.sort_by(|a, b| {
            let pa = self.files[a.0 .0].path.to_string_lossy();
            let pb = self.files[b.0 .0].path.to_string_lossy();
            (pa.as_ref(), a.0 .1.as_str()).cmp(&(pb.as_ref(), b.0 .1.as_str()))
        });
        (reached, problems)
    }

    /// Checks root name uniqueness (`speccheck.py:Checker.check_roots`).
    pub fn check_roots_unique(&mut self) {
        let mut by_name: BTreeMap<String, Vec<usize>> = BTreeMap::new();
        for (idx, r) in self.roots.iter().enumerate() {
            if let Some(name) = &r.name {
                by_name.entry(name.clone()).or_default().push(idx);
            }
        }
        for (name, owners) in by_name {
            if owners.len() > 1 {
                for &r_idx in &owners {
                    let others: Vec<String> = owners
                        .iter()
                        .copied()
                        .filter(|&o| o != r_idx)
                        .map(|o| self.roots[o].given.to_string_lossy().into_owned())
                        .collect();
                    let marker_path = self.roots[r_idx].given.join(MARKER);
                    let marker_loaded = self.roots[r_idx].marker.clone();
                    self.add_where(
                        &marker_path,
                        Some(r_idx),
                        marker_loaded.as_ref(),
                        &[PathElem::from("name")],
                        format!(
                            "root name '{name}' is also the name of {}; roots read together have distinct names (references name them)",
                            others.join(", ")
                        ),
                        "error",
                        false,
                        false,
                        true,
                    );
                }
            }
        }
    }

    /// Checks composition across loaded files (`speccheck.py:Checker.check_composition`).
    pub fn check_composition(&mut self) {
        let mut base: BTreeMap<String, Vec<usize>> = BTreeMap::new();
        for (idx, f) in self.files.iter().enumerate() {
            if !f.is_overlay() {
                base.entry(f.spec_id()).or_default().push(idx);
            }
        }
        for (sid, owners) in &base {
            if owners.len() > 1 {
                for &f_idx in owners {
                    let others: Vec<String> = owners
                        .iter()
                        .copied()
                        .filter(|&g| g != f_idx)
                        .map(|g| rel_spec_file(&self.roots[self.files[g].root_idx], &self.files[g]))
                        .collect();
                    self.add_file(
                        f_idx,
                        &[PathElem::from("id")],
                        format!(
                            "spec id '{sid}' is also declared by {}; ids are unique across every root read together",
                            others.join(", ")
                        ),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }

        let mut records_seen: HashMap<(String, usize, String), RecordKey> = HashMap::new();
        let all_file_indices: Vec<usize> = (0..self.files.len()).collect();
        for f_idx in all_file_indices {
            let sid = self.files[f_idx].spec_id();
            let r_idx = self.files[f_idx].root_idx;
            let recs: Vec<SpecRecord> = self.files[f_idx]
                .records
                .iter()
                .map(|(_, r)| r.clone())
                .collect();
            for rec in recs {
                let key = (sid.clone(), r_idx, rec.id.clone());
                if let Some(first) = records_seen.get(&key).cloned() {
                    let first_rel = rel_spec_file(
                        &self.roots[self.files[first.file_idx].root_idx],
                        &self.files[first.file_idx],
                    );
                    let root_label = self.roots[r_idx].label();
                    let mut p = rec.path.clone();
                    p.push(PathElem::from("id"));
                    self.add_file(
                        f_idx,
                        &p,
                        format!(
                            "fact id '{}' is also used by {first_rel} (spec '{sid}', root {root_label}); ids are unique per spec id per root",
                            rec.id
                        ),
                        "error",
                        false,
                        true,
                        true,
                    );
                } else {
                    records_seen.insert(
                        key,
                        RecordKey {
                            file_idx: f_idx,
                            id: rec.id,
                            full: rec.full,
                        },
                    );
                }
            }
        }
    }

    /// Checks references, duplicate references, self-references, layer ordering, transitive license
    /// gate, and inference premise cycles (`speccheck.py:Checker.check_references`).
    pub fn check_references(&mut self) {
        let mut premise_edges: HashMap<RecordKey, Vec<(RecordKey, Vec<PathElem>)>> = HashMap::new();
        let mut edge_order: Vec<RecordKey> = Vec::new();

        let all_records: Vec<SpecRecord> = self
            .files
            .iter()
            .flat_map(|f| f.records.iter().map(|(_, r)| r.clone()))
            .collect();

        for rec in all_records {
            let f_idx = rec.file_idx;
            let f_root_idx = self.files[f_idx].root_idx;
            let f_rank = self.roots[f_root_idx].rank;
            let f_layer = self.roots[f_root_idx]
                .layer
                .clone()
                .unwrap_or_else(|| "public".to_string());
            let what = what_record(&rec);
            let rkey = RecordKey {
                file_idx: f_idx,
                id: rec.id.clone(),
                full: rec.full.clone(),
            };
            if !premise_edges.contains_key(&rkey) {
                edge_order.push(rkey.clone());
                premise_edges.insert(rkey.clone(), Vec::new());
            }

            let mut seen: HashMap<
                (String, RecordKey, Option<String>, Vec<PathElem>),
                String,
            > = HashMap::new();

            for (kind, ref_str, path) in parse_refs(&rec.data, &rec.path) {
                let (target_opt, why_opt) = self.resolve(f_idx, &ref_str);
                let Some(target) = target_opt else {
                    self.reject(
                        f_idx,
                        &path,
                        format!(
                            "{what}: reference '{ref_str}' {}",
                            why_opt.unwrap_or_else(|| "failed".to_string())
                        ),
                        false,
                    );
                    continue;
                };
                if kind != "observation" {
                    let relation = if kind == "relates" {
                        if let Some(PathElem::Index(r_idx)) = path.get(path.len().saturating_sub(2))
                        {
                            rec.data
                                .get("relates")
                                .and_then(Value::as_array)
                                .and_then(|a| a.get(*r_idx))
                                .and_then(|rel_obj| rel_obj.get("relation"))
                                .and_then(Value::as_str)
                                .map(ToString::to_string)
                        } else {
                            None
                        }
                    } else {
                        None
                    };
                    let scope = if kind == "premise" && path.len() >= 3 {
                        path[..path.len() - 3].to_vec()
                    } else {
                        Vec::new()
                    };
                    let dup_key = (kind.clone(), target.clone(), relation, scope);
                    if let Some(prev_ref) = seen.get(&dup_key) {
                        self.reject(
                            f_idx,
                            &path,
                            format!(
                                "{what}: '{ref_str}' names {}, as '{prev_ref}' already does in this {kind} list",
                                target.full
                            ),
                            false,
                        );
                    } else {
                        seen.insert(dup_key, ref_str.clone());
                    }
                }
                if target == rkey && kind != "premise" {
                    self.reject(
                        f_idx,
                        &path,
                        format!("{what}: '{ref_str}' names the fact itself"),
                        false,
                    );
                }
                if kind == "premise" {
                    premise_edges
                        .get_mut(&rkey)
                        .unwrap()
                        .push((target.clone(), path.clone()));
                }
                let target_root_idx = self.files[target.file_idx].root_idx;
                let target_rank = self.roots[target_root_idx].rank;
                if target_rank > f_rank {
                    let target_layer = self.roots[target_root_idx]
                        .layer
                        .clone()
                        .unwrap_or_default();
                    self.reject(
                        f_idx,
                        &path,
                        format!(
                            "{what}: '{ref_str}' names a fact in layer {target_layer}, which merges after this file's layer {f_layer}"
                        ),
                        false,
                    );
                }

                // Transitive license gate (`speccheck.py:Checker.gate_reference`)
                let (reached, unknown) = self.reach_repos(&target);
                let mut problems = Vec::new();
                for ((g_idx, rname), via) in reached {
                    let through = if via == target {
                        String::new()
                    } else {
                        format!(" through {}", via.full)
                    };
                    let g_file = &self.files[g_idx];
                    let Some((repo_val, _)) = g_file.repos.get(&rname) else {
                        problems.push(format!(
                            "an anchor of {} naming repos entry '{rname}', which its file does not list (its license is unknown)",
                            via.full
                        ));
                        continue;
                    };
                    let lic = repo_val
                        .get("license")
                        .and_then(Value::as_str)
                        .unwrap_or("");
                    if let Some(reason) = self.gate_expr(f_root_idx, lic) {
                        let g_rel = rel_spec_file(&self.roots[g_file.root_idx], g_file);
                        problems.push(format!(
                            "repos entry '{rname}' of {g_rel}{through}: {reason}"
                        ));
                    }
                }
                for problem in problems {
                    self.reject(
                        f_idx,
                        &path,
                        format!("{what}: reference '{ref_str}' reaches {problem} (license gate, D13)"),
                        false,
                    );
                }
                for (via, hop, why) in unknown {
                    self.reject(
                        f_idx,
                        &path,
                        format!(
                            "{what}: reference '{ref_str}' reaches {}, whose reference '{hop}' {why}; what lies beyond is unknown, so the license gate fails closed",
                            via.full
                        ),
                        false,
                    );
                }
            }
        }

        self.check_premise_cycles(&edge_order, &premise_edges);
    }

    fn check_premise_cycles(
        &mut self,
        order: &[RecordKey],
        edges: &HashMap<RecordKey, Vec<(RecordKey, Vec<PathElem>)>>,
    ) {
        let mut index: HashMap<RecordKey, usize> = HashMap::new();
        let mut low: HashMap<RecordKey, usize> = HashMap::new();
        let mut stack: Vec<RecordKey> = Vec::new();
        let mut on_stack: HashSet<RecordKey> = HashSet::new();
        let mut counter: usize = 0;
        let mut sccs: Vec<Vec<RecordKey>> = Vec::new();

        for v in order {
            if index.contains_key(v) {
                continue;
            }
            index.insert(v.clone(), counter);
            low.insert(v.clone(), counter);
            counter += 1;
            stack.push(v.clone());
            on_stack.insert(v.clone());
            let first = edges.get(v).cloned().unwrap_or_default();
            let mut work: Vec<(RecordKey, std::vec::IntoIter<(RecordKey, Vec<PathElem>)>)> =
                vec![(v.clone(), first.into_iter())];

            while let Some((node, mut it)) = work.pop() {
                let mut advanced = false;
                while let Some((w, _)) = it.next() {
                    if !index.contains_key(&w) {
                        index.insert(w.clone(), counter);
                        low.insert(w.clone(), counter);
                        counter += 1;
                        stack.push(w.clone());
                        on_stack.insert(w.clone());
                        let w_edges = edges.get(&w).cloned().unwrap_or_default();
                        work.push((node.clone(), it));
                        work.push((w, w_edges.into_iter()));
                        advanced = true;
                        break;
                    }
                    if on_stack.contains(&w) {
                        let w_idx = index[&w];
                        let n_low = low.get_mut(&node).unwrap();
                        if w_idx < *n_low {
                            *n_low = w_idx;
                        }
                    }
                }
                if advanced {
                    continue;
                }
                let node_low = low[&node];
                if let Some((parent, _)) = work.last() {
                    let p_low = low.get_mut(parent).unwrap();
                    if node_low < *p_low {
                        *p_low = node_low;
                    }
                }
                if node_low == index[&node] {
                    let mut scc = Vec::new();
                    while let Some(w) = stack.pop() {
                        on_stack.remove(&w);
                        let done = w == node;
                        scc.push(w);
                        if done {
                            break;
                        }
                    }
                    sccs.push(scc);
                }
            }
        }

        for scc in sccs {
            let members: HashSet<RecordKey> = scc.iter().cloned().collect();
            if scc.len() == 1
                && !edges
                    .get(&scc[0])
                    .is_some_and(|es| es.iter().any(|(t, _)| t == &scc[0]))
            {
                continue;
            }
            let mut names: Vec<String> = scc.iter().map(|r| r.full.clone()).collect();
            names.sort();
            let names_str = names.join(", ");
            for rkey in &scc {
                let rec = self.files[rkey.file_idx].get_record(&rkey.id).unwrap().clone();
                let what = what_record(&rec);
                if let Some(es) = edges.get(rkey) {
                    for (target, path) in es {
                        if members.contains(target) {
                            self.reject(
                                rkey.file_idx,
                                path,
                                format!("{what}: its inference premises form a cycle among {names_str}"),
                                false,
                            );
                        }
                    }
                }
            }
        }
    }

    fn reach_roots(&self, start: &RecordKey) -> Vec<(usize, RecordKey)> {
        let mut out_map: HashMap<usize, RecordKey> = HashMap::new();
        let mut out_order: Vec<usize> = Vec::new();
        let mut seen: HashSet<RecordKey> = HashSet::new();
        seen.insert(start.clone());
        let mut queue: VecDeque<RecordKey> = VecDeque::new();
        queue.push_back(start.clone());

        while let Some(cur) = queue.pop_front() {
            let r_idx = self.files[cur.file_idx].root_idx;
            if !out_map.contains_key(&r_idx) {
                out_order.push(r_idx);
                out_map.insert(r_idx, cur.clone());
            }
            let refs: Vec<_> = {
                let file = &self.files[cur.file_idx];
                let rec = file.get_record(&cur.id).unwrap();
                parse_refs(&rec.data, &rec.path)
            };
            for (_, ref_str, _) in refs {
                if let (Some(t), _) = self.resolve(cur.file_idx, &ref_str) {
                    if seen.insert(t.clone()) {
                        queue.push_back(t);
                    }
                }
            }
        }
        out_order
            .into_iter()
            .map(|r_idx| (r_idx, out_map.remove(&r_idx).unwrap()))
            .collect()
    }

    /// Runs `records.py:first_pass`: current FAIL verdicts and upstream map mismatches on current
    /// verdicts (before `check_trust`).
    pub fn first_pass(&mut self) {
        let all_keys: Vec<RecordKey> = self
            .files
            .iter()
            .flat_map(|f| {
                f.records.iter().map(|(_, r)| RecordKey {
                    file_idx: r.file_idx,
                    id: r.id.clone(),
                    full: r.full.clone(),
                })
            })
            .collect();

        let mut fail_findings = Vec::new();
        let mut upstream_findings = Vec::new();

        {
            let mut fresh = FreshnessEngine::new(self, None, None);
            fresh.compute_all(&all_keys);

            for (f_idx, f) in self.files.iter().enumerate() {
                if f.record_state != "ok" {
                    continue;
                }
                let rpath = f.record_path.clone().unwrap();
                let r_idx = f.root_idx;
                let rel_rec = rel_to_root(&self.roots[r_idx], &rpath);

                for (fid, (v, kpath)) in &f.verdicts {
                    let Some(rec) = f.get_record(fid) else {
                        continue;
                    };
                    let rkey = RecordKey {
                        file_idx: f_idx,
                        id: rec.id.clone(),
                        full: rec.full.clone(),
                    };
                    let (basis_opt, _) = fresh.basis(&rkey);
                    let Some(basis) = basis_opt else {
                        continue;
                    };
                    if v.get("basis").and_then(Value::as_str) != Some(basis.as_str()) {
                        continue;
                    }
                    if v.get("verdict").and_then(Value::as_str) == Some("FAIL") {
                        let corr = v.get("correction").and_then(Value::as_str).unwrap_or("");
                        let mut p = rec.path.clone();
                        p.push(PathElem::from("id"));
                        fail_findings.push((
                            f_idx,
                            p,
                            format!(
                                "{}: its current verdict in {rel_rec} is FAIL (correction: {})",
                                what_record(rec),
                                cut_text(corr)
                            ),
                        ));
                    }
                    let want = fresh.upstream_now(&rkey).unwrap_or_default();
                    let have: BTreeMap<String, String> = v
                        .get("upstream")
                        .and_then(Value::as_object)
                        .map(|m| {
                            m.iter()
                                .filter_map(|(k, val)| {
                                    Some((k.clone(), val.as_str()?.to_string()))
                                })
                                .collect()
                        })
                        .unwrap_or_default();
                    if have != want {
                        let shown = if want.is_empty() {
                            "none".to_string()
                        } else {
                            want.iter()
                                .map(|(k, b)| format!("{k}: {b}"))
                                .collect::<Vec<_>>()
                                .join(", ")
                        };
                        let has_upstream_key = v.get("upstream").is_some();
                        let mut up_path = kpath.clone();
                        if has_upstream_key {
                            up_path.push(PathElem::from("upstream"));
                        }
                        upstream_findings.push((
                            f_idx,
                            rpath.clone(),
                            r_idx,
                            up_path,
                            !has_upstream_key,
                            format!(
                                "verdict key '{fid}': upstream does not match the facts in other roots the fact rests on (now {shown}); a current verdict records their bases so a change upstream reads as upstream-stale"
                            ),
                        ));
                    }
                }
            }
        }

        for (f_idx, path, msg) in fail_findings {
            self.add_file(f_idx, &path, msg, "error", false, true, true);
        }
        for (f_idx, rpath, r_idx, up_path, is_key, msg) in upstream_findings {
            let loaded = self.files[f_idx].record_loaded.clone();
            self.add_where(
                &rpath,
                Some(r_idx),
                loaded.as_ref(),
                &up_path,
                msg,
                "error",
                is_key,
                true,
                true,
            );
        }
    }

    /// Propagates untrusted root errors across cross-root references (`speccheck.py:Checker.check_trust`).
    pub fn check_trust(&mut self) {
        let mut emitted: HashSet<(usize, Vec<PathElem>, usize)> = HashSet::new();
        loop {
            let mut changed = false;
            let all_records: Vec<SpecRecord> = self
                .files
                .iter()
                .flat_map(|f| f.records.iter().map(|(_, r)| r.clone()))
                .collect();
            for rec in all_records {
                let f_idx = rec.file_idx;
                let f_root_idx = self.files[f_idx].root_idx;
                let what = what_record(&rec);
                for (_, ref_str, path) in parse_refs(&rec.data, &rec.path) {
                    if self.failed_refs.contains(&(f_idx, path.clone())) {
                        continue;
                    }
                    let (Some(target), _) = self.resolve(f_idx, &ref_str) else {
                        continue;
                    };
                    for (r_idx, via) in self.reach_roots(&target) {
                        if r_idx == f_root_idx || self.roots[r_idx].untrusted.is_empty() {
                            continue;
                        }
                        if !emitted.insert((f_idx, path.clone(), r_idx)) {
                            continue;
                        }
                        let through = if via == target {
                            String::new()
                        } else {
                            format!(" through {}", via.full)
                        };
                        let was_trusted = self.roots[f_root_idx].untrusted.is_empty();
                        let msg = format!(
                            "{what}: reference '{ref_str}' rests on {}{through}",
                            untrusted_message(&self.roots[r_idx])
                        );
                        self.reject(f_idx, &path, msg, false);
                        changed = changed || was_trusted;
                    }
                }
            }
            if !changed {
                break;
            }
        }
    }

    /// Runs `records.py:second_pass`: computes freshness rows for all spec files and emits
    /// freshness and second-reader findings on checked roots.
    pub fn second_pass(&mut self) {
        let mode = self.require_verified.clone();
        let level_for = |kind: &str| -> &'static str {
            match mode.as_deref() {
                None => "warning",
                Some("main") if kind == "upstream-stale" || kind == "adjudicate" => "warning",
                _ => "error",
            }
        };

        let all_keys: Vec<RecordKey> = self
            .files
            .iter()
            .flat_map(|f| {
                f.records.iter().map(|(_, r)| RecordKey {
                    file_idx: r.file_idx,
                    id: r.id.clone(),
                    full: r.full.clone(),
                })
            })
            .collect();

        let mut status_entries = Vec::new();
        let mut pending_findings: Vec<(usize, Vec<PathElem>, String, &'static str)> = Vec::new();

        {
            let mut fresh = FreshnessEngine::new(
                self,
                Some(self.failed_refs.clone()),
                Some(&self.failed_cites),
            );
            fresh.compute_all(&all_keys);

            for (f_idx, f) in self.files.iter().enumerate() {
                let r_idx = f.root_idx;
                let root = &self.roots[r_idx];
                let fname = f
                    .path
                    .file_name()
                    .map(|s| s.to_string_lossy().into_owned())
                    .unwrap_or_default();
                let stem = fname.strip_suffix(SPEC_SUFFIX).unwrap_or(&fname);
                let record_rel = f
                    .record_path
                    .as_ref()
                    .map(|rp| rel_to_root(root, rp))
                    .unwrap_or_else(|| format!("resources/{stem}{RECORD_SUFFIX}"));

                let mut rows = Vec::new();
                for (_, rec) in &f.records {
                    let rkey = RecordKey {
                        file_idx: f_idx,
                        id: rec.id.clone(),
                        full: rec.full.clone(),
                    };
                    let v_opt = f.verdicts.get(&rec.id).map(|(v, _)| v);
                    let (st, changed, reason) = fresh.status(&rkey, v_opt);
                    let (basis_opt, _) = fresh.basis(&rkey);
                    let critical = rec.data.get("critical").and_then(Value::as_bool) == Some(true);

                    let v_verifier = v_opt
                        .and_then(|v| v.get("verifier"))
                        .and_then(Value::as_str)
                        .unwrap_or("");
                    let readers_arr = v_opt
                        .and_then(|v| v.get("readers"))
                        .and_then(Value::as_array);
                    let has_other_reader = readers_arr.is_some_and(|arr| {
                        arr.iter().any(|r| {
                            let rv = r.get("verifier").and_then(Value::as_str).unwrap_or("");
                            who_verifier(rv) != who_verifier(v_verifier)
                        })
                    });
                    let has_any_reader = readers_arr.is_some_and(|arr| !arr.is_empty());
                    let own_only = has_any_reader && !has_other_reader;
                    let second_reader = if !critical {
                        "not-needed"
                    } else if has_other_reader {
                        "present"
                    } else {
                        "missing"
                    };

                    let v_str_opt = v_opt
                        .and_then(|v| v.get("verdict"))
                        .and_then(Value::as_str)
                        .map(ToString::to_string);
                    let rec_basis_opt = v_opt
                        .and_then(|v| v.get("basis"))
                        .and_then(Value::as_str)
                        .map(ToString::to_string);
                    let upstream_opt = if basis_opt.is_some() {
                        fresh.upstream_now(&rkey)
                    } else {
                        None
                    };

                    rows.push(StatusRow {
                        key: rec.id.clone(),
                        r#ref: rec.full.clone(),
                        kind: record_kind_word(rec).to_string(),
                        status: st.as_str().to_string(),
                        verdict: v_str_opt.clone(),
                        basis: basis_opt,
                        recorded: rec_basis_opt,
                        upstream: upstream_opt,
                        changed: if st == Freshness::UpstreamStale {
                            changed.clone()
                        } else {
                            Vec::new()
                        },
                        reason: if st == Freshness::Unknown {
                            reason.clone()
                        } else {
                            None
                        },
                        second_reader: second_reader.to_string(),
                    });

                    if root.context {
                        continue;
                    }

                    let what = what_record(rec);
                    let mut at = rec.path.clone();
                    at.push(PathElem::from("id"));

                    match st {
                        Freshness::Unknown => {
                            let det = reason.unwrap_or_default();
                            pending_findings.push((
                                f_idx,
                                at.clone(),
                                format!(
                                    "{what}: freshness unknown: {det}; no verdict can be current"
                                ),
                                level_for("unknown"),
                            ));
                        }
                        Freshness::Unverified => {
                            let why = match f.record_state.as_str() {
                                "ok" => format!("no verdict in {record_rel}"),
                                "invalid" => format!("its record {record_rel} does not validate"),
                                "shared" => {
                                    "its record name is shared with another spec file".to_string()
                                }
                                _ => format!("no record at {record_rel}"),
                            };
                            pending_findings.push((
                                f_idx,
                                at.clone(),
                                format!("{what}: unverified: {why}"),
                                level_for("unverified"),
                            ));
                        }
                        Freshness::Stale => {
                            let v = v_opt.unwrap();
                            let v_verdict =
                                v.get("verdict").and_then(Value::as_str).unwrap_or("PASS");
                            let v_date = v.get("date").and_then(Value::as_str).unwrap_or("");
                            let old = if v_verdict != "PASS" {
                                format!(" (its {v_verdict} was for that version)")
                            } else {
                                String::new()
                            };
                            pending_findings.push((
                                f_idx,
                                at.clone(),
                                format!(
                                    "{what}: verdict stale: the fact, a resource it cites, an assumption it names or a fact it rests on changed since the verdict of {v_date}{old}"
                                ),
                                level_for("stale"),
                            ));
                        }
                        Freshness::UpstreamStale => {
                            let v = v_opt.unwrap();
                            let v_date = v.get("date").and_then(Value::as_str).unwrap_or("");
                            pending_findings.push((
                                f_idx,
                                at.clone(),
                                format!(
                                    "{what}: upstream-stale: {} changed since the verdict of {v_date}",
                                    changed.join(", ")
                                ),
                                level_for("upstream-stale"),
                            ));
                        }
                        Freshness::Current => {
                            if v_str_opt.as_deref() == Some("ADJUDICATE") {
                                pending_findings.push((
                                    f_idx,
                                    at.clone(),
                                    format!("{what}: its verdict is ADJUDICATE, not yet settled"),
                                    level_for("adjudicate"),
                                ));
                            }
                        }
                    }

                    if matches!(st, Freshness::Current | Freshness::UpstreamStale)
                        && second_reader == "missing"
                    {
                        let same = if own_only {
                            "; a reader with the verdict's own verifier is not a second reader"
                        } else {
                            ""
                        };
                        pending_findings.push((
                            f_idx,
                            at,
                            format!(
                                "{what}: critical, so its verdict needs a second reader's verdict in readers (D14){same}"
                            ),
                            level_for("reader"),
                        ));
                    }
                }

                status_entries.push((
                    f_idx,
                    SpecStatusEntry {
                        path: f.path.to_string_lossy().into_owned(),
                        root: root.label(),
                        spec: f.spec_id(),
                        record: f.record_path.as_ref().map(|_| record_rel),
                        state: f.record_state.clone(),
                        facts: rows,
                    },
                ));
            }
        }

        for (f_idx, at, msg, lvl) in pending_findings {
            self.add_file(f_idx, &at, msg, lvl, false, true, true);
        }
        self.status = status_entries;
    }

    /// Runs all check passes (`speccheck.py:Checker.run`).
    pub fn run(&mut self, schemas: &Schemas) {
        self.check_roots_unique();
        for f_idx in 0..self.files.len() {
            self.index_file(f_idx);
        }
        for f_idx in 0..self.files.len() {
            self.check_file(f_idx);
        }
        self.check_structure(schemas);
        self.check_composition();
        self.check_references();
        self.first_pass();
        self.check_trust();
        self.second_pass();
    }

    /// Deduplicates and sorts findings matching `spec.py:_ordered`.
    #[must_use]
    pub fn ordered_findings(&self) -> Vec<SpecFinding> {
        let mut seen: HashSet<(String, usize, usize, String, String)> = HashSet::new();
        let mut out: Vec<SpecFinding> = Vec::new();
        for f in &self.findings {
            let key = (
                f.path.clone(),
                f.line,
                f.column,
                f.level.clone(),
                f.message.clone(),
            );
            if seen.insert(key) {
                out.push(f.clone());
            }
        }
        out.sort_by(|a, b| {
            (
                a.path.as_str(),
                a.line,
                a.column,
                a.message.as_str(),
            )
                .cmp(&(
                    b.path.as_str(),
                    b.line,
                    b.column,
                    b.message.as_str(),
                ))
        });
        out
    }
}

/// Runs `check` over `roots` and `context_roots` (`spec.py:cmd_check`).
#[must_use]
pub fn check_roots(
    roots: &[PathBuf],
    context_roots: &[PathBuf],
    require_license: bool,
    public_skills: &HashSet<String>,
    require_verified: Option<String>,
) -> CheckReport {
    if roots.is_empty() {
        return CheckReport {
            exit_code: EXIT_USAGE_ERROR,
            ok: false,
            error: Some("usage".to_string()),
            roots: Vec::new(),
            specs: 0,
            stubs: 0,
            verification: STATUSES.iter().map(|&s| (s.to_string(), 0)).collect(),
            findings: vec![SpecFinding {
                path: String::new(),
                line: 0,
                column: 0,
                level: "error".to_string(),
                message: "at least one root directory is required".to_string(),
            }],
            text_lines: Vec::new(),
        };
    }

    let schemas = load_schemas();
    let mut checker = Checker::new(require_license, public_skills.clone(), require_verified);
    if let Err((code, msg)) = checker.load_roots(roots, context_roots, schemas) {
        let err_kind = if code == EXIT_USAGE_ERROR {
            "usage"
        } else {
            "precondition"
        };
        return CheckReport {
            exit_code: code,
            ok: false,
            error: Some(err_kind.to_string()),
            roots: Vec::new(),
            specs: 0,
            stubs: 0,
            verification: STATUSES.iter().map(|&s| (s.to_string(), 0)).collect(),
            findings: vec![SpecFinding {
                path: String::new(),
                line: 0,
                column: 0,
                level: "error".to_string(),
                message: msg,
            }],
            text_lines: Vec::new(),
        };
    }
    checker.run(schemas);

    let ordered = checker.ordered_findings();
    let errors = ordered.iter().filter(|f| f.level == "error").count();
    let warnings = ordered.len() - errors;

    let mut verification: BTreeMap<String, usize> =
        STATUSES.iter().map(|&s| (s.to_string(), 0)).collect();
    for (f_idx, entry) in &checker.status {
        let r_idx = checker.files[*f_idx].root_idx;
        if !checker.roots[r_idx].context {
            for row in &entry.facts {
                if let Some(c) = verification.get_mut(&row.status) {
                    *c += 1;
                }
            }
        }
    }

    let mut text_lines: Vec<String> = ordered.iter().map(ToString::to_string).collect();
    text_lines.push(format!(
        "{} root(s), {} spec file(s), {} stub(s): {errors} error(s), {warnings} warning(s)",
        checker.roots.len(),
        checker.files.len(),
        checker.stubs
    ));

    let root_infos = checker
        .roots
        .iter()
        .map(|r| RootInfo {
            path: r.given.to_string_lossy().into_owned(),
            name: r.name.clone(),
            layer: r.layer.clone(),
            context: r.context,
        })
        .collect();

    CheckReport {
        exit_code: if errors > 0 {
            EXIT_DOMAIN_FAILURE
        } else {
            EXIT_OK
        },
        ok: errors == 0,
        error: None,
        roots: root_infos,
        specs: checker.files.len(),
        stubs: checker.stubs,
        verification,
        findings: ordered,
        text_lines,
    }
}

/// Runs `status` over `roots` and `context_roots` (`spec.py:cmd_status`).
#[must_use]
pub fn status_roots(
    roots: &[PathBuf],
    context_roots: &[PathBuf],
    require_license: bool,
    public_skills: &HashSet<String>,
    stale_only: bool,
) -> StatusReport {
    if roots.is_empty() {
        return StatusReport {
            exit_code: EXIT_USAGE_ERROR,
            ok: false,
            error: Some("usage".to_string()),
            roots: Vec::new(),
            errors: 0,
            warnings: 0,
            specs: Vec::new(),
            findings: vec![SpecFinding {
                path: String::new(),
                line: 0,
                column: 0,
                level: "error".to_string(),
                message: "at least one root directory is required".to_string(),
            }],
            text_lines: Vec::new(),
        };
    }

    let schemas = load_schemas();
    let mut checker = Checker::new(require_license, public_skills.clone(), None);
    if let Err((code, msg)) = checker.load_roots(roots, context_roots, schemas) {
        let err_kind = if code == EXIT_USAGE_ERROR {
            "usage"
        } else {
            "precondition"
        };
        return StatusReport {
            exit_code: code,
            ok: false,
            error: Some(err_kind.to_string()),
            roots: Vec::new(),
            errors: 0,
            warnings: 0,
            specs: Vec::new(),
            findings: vec![SpecFinding {
                path: String::new(),
                line: 0,
                column: 0,
                level: "error".to_string(),
                message: msg,
            }],
            text_lines: Vec::new(),
        };
    }
    checker.run(schemas);

    let ordered = checker.ordered_findings();
    let errors = ordered.iter().filter(|f| f.level == "error").count();
    let warnings = ordered.len() - errors;

    let mut specs = Vec::new();
    let mut text = Vec::new();

    for (f_idx, entry) in &checker.status {
        let f = &checker.files[*f_idx];
        let root = &checker.roots[f.root_idx];
        if root.context {
            continue;
        }
        let mut rows = entry.facts.clone();
        if stale_only {
            rows.retain(|r| r.status != "current" || r.second_reader == "missing");
            if rows.is_empty() {
                continue;
            }
        }
        let rel = rel_to_root(root, &f.path);
        let summary = if entry.state == "ok" {
            let s = f
                .record_loaded
                .as_ref()
                .and_then(|ld| ld.data.as_ref())
                .and_then(|d| d.get("summary"));
            let parts: Vec<String> = SUMMARY
                .iter()
                .map(|&(k, _)| {
                    let n = s
                        .and_then(|sobj| sobj.get(k))
                        .and_then(Value::as_i64)
                        .unwrap_or(0);
                    format!("{k} {n}")
                })
                .collect();
            format!(
                "{}: {}",
                entry.record.as_deref().unwrap_or(""),
                parts.join(", ")
            )
        } else if entry.state != "none" {
            format!("{}: {}", entry.record.as_deref().unwrap_or(""), entry.state)
        } else {
            "no record".to_string()
        };

        text.push(format!("{}:{rel} ({}): {summary}", root.label(), f.spec_id()));
        for r in &rows {
            let mut notes = Vec::new();
            if let Some(v) = &r.verdict {
                notes.push(v.clone());
            }
            if r.second_reader == "missing" {
                notes.push("needs a second reader".to_string());
            }
            if !r.changed.is_empty() {
                notes.push(format!("upstream changed: {}", r.changed.join(", ")));
            }
            if let Some(reason) = &r.reason {
                notes.push(reason.clone());
            }
            let suffix = if notes.is_empty() {
                String::new()
            } else {
                format!("  ({})", notes.join("; "))
            };
            text.push(format!("  {:<15} {}{suffix}", r.status, r.key));
        }

        specs.push(SpecStatusEntry {
            path: entry.path.clone(),
            root: entry.root.clone(),
            spec: entry.spec.clone(),
            record: entry.record.clone(),
            state: entry.state.clone(),
            facts: rows,
        });
    }

    let mut tally: HashMap<&str, usize> = STATUSES.iter().map(|&s| (s, 0)).collect();
    for spec in &specs {
        for r in &spec.facts {
            if let Some(c) = tally.get_mut(r.status.as_str()) {
                *c += 1;
            }
        }
    }

    for f in &ordered {
        if f.level == "error" {
            text.push(f.to_string());
        }
    }
    let tally_parts: Vec<String> = STATUSES
        .iter()
        .map(|&k| format!("{} {k}", tally[k]))
        .collect();
    text.push(format!(
        "{}; the check found {errors} error(s), {warnings} warning(s)",
        tally_parts.join(", ")
    ));

    let root_infos = checker
        .roots
        .iter()
        .map(|r| RootInfo {
            path: r.given.to_string_lossy().into_owned(),
            name: r.name.clone(),
            layer: r.layer.clone(),
            context: r.context,
        })
        .collect();

    StatusReport {
        exit_code: if errors > 0 {
            EXIT_DOMAIN_FAILURE
        } else {
            EXIT_OK
        },
        ok: errors == 0,
        error: None,
        roots: root_infos,
        errors,
        warnings,
        specs,
        findings: ordered,
        text_lines: text,
    }
}

/// Runs the `status` CLI (`args` after `"status"`), returning `(exit_code, stdout, stderr)`.
#[must_use]
pub fn run_status_cli(args: &[String]) -> (i32, String, String) {
    let mut roots = Vec::new();
    let mut context_roots = Vec::new();
    let mut require_license = false;
    let mut public_skills = HashSet::new();
    let mut stale_only = false;
    let mut json_mode = false;
    let mut usage_err: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        let a = &args[i];
        if a == "--json" {
            json_mode = true;
            i += 1;
        } else if a == "--stale" {
            stale_only = true;
            i += 1;
        } else if a == "--require-license" {
            require_license = true;
            i += 1;
        } else if a == "--context-root" {
            if i + 1 >= args.len() {
                usage_err = Some("--context-root requires a directory argument".to_string());
                break;
            }
            context_roots.push(PathBuf::from(&args[i + 1]));
            i += 2;
        } else if let Some(val) = a.strip_prefix("--context-root=") {
            context_roots.push(PathBuf::from(val));
            i += 1;
        } else if a == "--public-skill" {
            if i + 1 >= args.len() {
                usage_err = Some("--public-skill requires a skill name".to_string());
                break;
            }
            public_skills.insert(args[i + 1].clone());
            i += 2;
        } else if let Some(val) = a.strip_prefix("--public-skill=") {
            public_skills.insert(val.to_string());
            i += 1;
        } else if a.starts_with('-') {
            usage_err = Some(format!("unrecognized argument: {a}"));
            break;
        } else {
            roots.push(PathBuf::from(a));
            i += 1;
        }
    }

    if usage_err.is_none() && roots.is_empty() {
        usage_err = Some("the following arguments are required: roots".to_string());
    }

    if let Some(msg) = usage_err {
        if json_mode {
            let payload = json!({
                "ok": false,
                "error": "usage",
                "roots": [],
                "errors": 0,
                "warnings": 0,
                "specs": [],
                "findings": [{"path": "", "line": 0, "column": 0, "level": "error", "message": msg}]
            });
            return (
                EXIT_USAGE_ERROR,
                format!("{}\n", serde_json::to_string(&payload).unwrap()),
                String::new(),
            );
        }
        return (EXIT_USAGE_ERROR, String::new(), format!("error: {msg}\n"));
    }

    let report = status_roots(
        &roots,
        &context_roots,
        require_license,
        &public_skills,
        stale_only,
    );
    if json_mode {
        (
            report.exit_code,
            format!("{}\n", serde_json::to_string(&report).unwrap()),
            String::new(),
        )
    } else if report.error.is_some() {
        let msg = report
            .findings
            .first()
            .map(|f| f.message.as_str())
            .unwrap_or("error");
        (report.exit_code, String::new(), format!("error: {msg}\n"))
    } else {
        (
            report.exit_code,
            format!("{}\n", report.text_lines.join("\n")),
            String::new(),
        )
    }
}

/// Runs the `check` CLI (`args` after `"check"`), returning `(exit_code, stdout, stderr)`.
#[must_use]
pub fn run_check_cli(args: &[String]) -> (i32, String, String) {
    let mut roots = Vec::new();
    let mut context_roots = Vec::new();
    let mut require_license = false;
    let mut public_skills = HashSet::new();
    let mut require_verified: Option<String> = None;
    let mut json_mode = false;
    let mut usage_err: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        let a = &args[i];
        if a == "--json" {
            json_mode = true;
            i += 1;
        } else if a == "--require-license" {
            require_license = true;
            i += 1;
        } else if a == "--context-root" {
            if i + 1 >= args.len() {
                usage_err = Some("--context-root requires a directory argument".to_string());
                break;
            }
            context_roots.push(PathBuf::from(&args[i + 1]));
            i += 2;
        } else if let Some(val) = a.strip_prefix("--context-root=") {
            context_roots.push(PathBuf::from(val));
            i += 1;
        } else if a == "--public-skill" {
            if i + 1 >= args.len() {
                usage_err = Some("--public-skill requires a skill name".to_string());
                break;
            }
            public_skills.insert(args[i + 1].clone());
            i += 2;
        } else if let Some(val) = a.strip_prefix("--public-skill=") {
            public_skills.insert(val.to_string());
            i += 1;
        } else if a == "--require-verified" {
            if i + 1 >= args.len() {
                usage_err = Some("--require-verified requires 'pr' or 'main'".to_string());
                break;
            }
            let val = &args[i + 1];
            if val != "pr" && val != "main" {
                usage_err = Some(format!(
                    "--require-verified: invalid choice '{val}' (choose from 'pr', 'main')"
                ));
                break;
            }
            require_verified = Some(val.clone());
            i += 2;
        } else if let Some(val) = a.strip_prefix("--require-verified=") {
            if val != "pr" && val != "main" {
                usage_err = Some(format!(
                    "--require-verified: invalid choice '{val}' (choose from 'pr', 'main')"
                ));
                break;
            }
            require_verified = Some(val.to_string());
            i += 1;
        } else if a.starts_with('-') {
            usage_err = Some(format!("unrecognized argument: {a}"));
            break;
        } else {
            roots.push(PathBuf::from(a));
            i += 1;
        }
    }

    if usage_err.is_none() && roots.is_empty() {
        usage_err = Some("the following arguments are required: roots".to_string());
    }

    if let Some(msg) = usage_err {
        if json_mode {
            let ver: BTreeMap<String, usize> =
                STATUSES.iter().map(|&s| (s.to_string(), 0)).collect();
            let payload = json!({
                "ok": false,
                "error": "usage",
                "roots": [],
                "specs": 0,
                "stubs": 0,
                "verification": ver,
                "findings": [{"path": "", "line": 0, "column": 0, "level": "error", "message": msg}]
            });
            return (
                EXIT_USAGE_ERROR,
                format!("{}\n", serde_json::to_string(&payload).unwrap()),
                String::new(),
            );
        }
        return (EXIT_USAGE_ERROR, String::new(), format!("error: {msg}\n"));
    }

    let report = check_roots(
        &roots,
        &context_roots,
        require_license,
        &public_skills,
        require_verified,
    );
    if json_mode {
        (
            report.exit_code,
            format!("{}\n", serde_json::to_string(&report).unwrap()),
            String::new(),
        )
    } else if report.error.is_some() {
        let msg = report
            .findings
            .first()
            .map(|f| f.message.as_str())
            .unwrap_or("error");
        (report.exit_code, String::new(), format!("error: {msg}\n"))
    } else {
        (
            report.exit_code,
            format!("{}\n", report.text_lines.join("\n")),
            String::new(),
        )
    }
}
