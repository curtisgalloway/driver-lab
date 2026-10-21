// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Campaign review subcommands and library API (`RT-10b`):
//! - `source_registry`: `sources.yaml` validation and identity checking.
//! - `deployment`: `deployment.yaml` validation, config resolution, and evidence classes.
//! - `index_check`: `claims.yaml` and `status.yaml` verification (with both declarative
//!   check manifests and static Python harness AST check-name extraction).
//! - `stopping`: CR4 stopping-rule evaluation, coverage, round caps, and guarded queue.
//! - `sweep`: CR3/CR4 read-only freshness sweep and stopping report.
//! - `contract_check`: CR5 deployment, source-adapter, and fixture-backend contract checks.
//! - `pinned_file_adapter`: C8 pinned-file identity inspection and `--write` / `--dry-run`.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::fmt;
use std::fs;
use std::path::{Component, Path, PathBuf};

use regex::Regex;
use saphyr_parser::{Event, Parser as YamlParser, ScalarStyle, Tag};
use serde::de::{self, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{json, Map, Number, Value};

/// Domain validation error (`exit 1`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Invalid(pub String);

impl fmt::Display for Invalid {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Invalid {}

/// Missing input file or environment precondition error (`exit 3`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Precondition(pub String);

impl fmt::Display for Precondition {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Precondition {}

pub type VResult<T> = Result<T, Invalid>;

#[inline]
pub fn require(condition: bool, message: impl Into<String>) -> VResult<()> {
    if !condition {
        return Err(Invalid(message.into()));
    }
    Ok(())
}

pub fn is_sha256(val: &Value) -> bool {
    match val.as_str() {
        Some(s) => s.len() == 64 && s.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')),
        None => false,
    }
}

pub fn is_commit(val: &Value) -> bool {
    match val.as_str() {
        Some(s) => s.len() == 40 && s.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')),
        None => false,
    }
}

pub fn is_iso_date(val: &Value) -> bool {
    let Some(s) = val.as_str() else {
        return false;
    };
    is_iso_date_str(s)
}

pub fn is_iso_date_str(s: &str) -> bool {
    if s.len() != 10 {
        return false;
    }
    let bytes = s.as_bytes();
    if bytes[4] != b'-' || bytes[7] != b'-' {
        return false;
    }
    let Ok(year) = s[0..4].parse::<u32>() else {
        return false;
    };
    let Ok(month) = s[5..7].parse::<u32>() else {
        return false;
    };
    let Ok(day) = s[8..10].parse::<u32>() else {
        return false;
    };
    if year == 0 || !(1..=12).contains(&month) || day == 0 {
        return false;
    }
    let leap = (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
    let max_day = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if leap {
                29
            } else {
                28
            }
        }
        _ => return false,
    };
    day <= max_day
}

pub fn nonempty_str<'a>(val: &'a Value, what: &str) -> VResult<&'a str> {
    match val.as_str() {
        Some(s) if !s.trim().is_empty() => Ok(s),
        _ => Err(Invalid(format!("{what} must be a nonempty string"))),
    }
}

pub fn optional_str<'a>(val: &'a Value, what: &str) -> VResult<Option<&'a str>> {
    if val.is_null() {
        return Ok(None);
    }
    nonempty_str(val, what).map(Some)
}

pub fn mapping<'a>(
    val: &'a Value,
    what: &str,
    required: Option<&[&str]>,
    optional: Option<&[&str]>,
) -> VResult<&'a Map<String, Value>> {
    let Some(obj) = val.as_object() else {
        return Err(Invalid(format!("{what} must be a mapping")));
    };
    if let Some(req) = required {
        let req_set: BTreeSet<&str> = req.iter().copied().collect();
        let opt_set: BTreeSet<&str> = optional.unwrap_or(&[]).iter().copied().collect();
        let allowed: BTreeSet<&str> = req_set.union(&opt_set).copied().collect();
        let missing: Vec<&str> = req_set
            .iter()
            .copied()
            .filter(|k| !obj.contains_key(*k))
            .collect();
        let extra: Vec<&str> = obj
            .keys()
            .map(String::as_str)
            .filter(|k| !allowed.contains(k))
            .collect();
        require(
            missing.is_empty(),
            format!("{what} missing keys: {missing:?}"),
        )?;
        require(
            extra.is_empty(),
            format!("{what} has unexpected keys: {extra:?}"),
        )?;
    }
    Ok(obj)
}

pub fn list<'a>(val: &'a Value, what: &str, nonempty: bool) -> VResult<&'a Vec<Value>> {
    let Some(arr) = val.as_array() else {
        return Err(Invalid(format!("{what} must be a list")));
    };
    if nonempty {
        require(!arr.is_empty(), format!("{what} must not be empty"))?;
    }
    Ok(arr)
}

pub fn unique_strs(val: &Value, what: &str, nonempty: bool) -> VResult<Vec<String>> {
    let arr = list(val, what, nonempty)?;
    let mut seen = HashSet::new();
    let mut out = Vec::with_capacity(arr.len());
    for (i, item) in arr.iter().enumerate() {
        let s = nonempty_str(item, &format!("{what}[{i}]"))?;
        require(seen.insert(s.to_string()), format!("{what} repeats {s:?}"))?;
        out.push(s.to_string());
    }
    Ok(out)
}

pub fn is_exact_int(val: &Value) -> Option<i64> {
    match val {
        Value::Number(n) => n.as_i64(),
        _ => None,
    }
}

pub fn is_positive_int(val: &Value) -> bool {
    matches!(is_exact_int(val), Some(n) if n > 0)
}

pub fn is_nonneg_int(val: &Value) -> bool {
    matches!(is_exact_int(val), Some(n) if n >= 0)
}

pub fn value_repr(val: &Value) -> String {
    match val {
        Value::String(s) => format!("'{s}'"),
        other => other.to_string(),
    }
}

// ============================================================================
// Strict Campaign YAML & JSON Loaders
// ============================================================================

const MAX_YAML_BYTES: usize = 16 * 1024 * 1024;
const MAX_YAML_DEPTH: usize = 64;
const MAX_YAML_NODES: usize = 200_000;

/// Loads YAML for campaign metadata files (`claims.yaml`, `status.yaml`, `sources.yaml`,
/// `deployment.yaml`). Supports YAML anchors and aliases (`&id` / `*id`) as used in
/// `evals/e1000/claims.yaml`, while rejecting duplicate mapping keys, non-string keys,
/// unquoted `YYYY-MM-DD` date literals, and non-standard tags.
pub fn load_yaml(text: &str) -> VResult<Value> {
    require(
        text.len() <= MAX_YAML_BYTES,
        format!("YAML exceeds maximum size of {MAX_YAML_BYTES} bytes"),
    )?;
    for ch in text.chars() {
        let code = ch as u32;
        let printable = ch == '\t'
            || ch == '\n'
            || ch == '\r'
            || (0x20..=0x7E).contains(&code)
            || code == 0x85
            || (0xA0..=0xD7FF).contains(&code)
            || (0xE000..=0xFFFD).contains(&code)
            || (0x10000..=0x10FFFF).contains(&code);
        require(printable, format!("unacceptable character {ch:?} in YAML"))?;
    }

    enum Frame {
        Seq {
            anchor_id: usize,
            items: Vec<Value>,
        },
        Map {
            anchor_id: usize,
            entries: Map<String, Value>,
            seen_keys: HashSet<String>,
            pending_key: Option<String>,
        },
    }

    let parser = YamlParser::new_from_str(text);
    let mut stack: Vec<Frame> = Vec::new();
    let mut anchors: HashMap<usize, Value> = HashMap::new();
    let mut root: Option<Value> = None;
    let mut doc_count = 0usize;
    let mut node_count = 0usize;

    let count_nodes = |v: &Value| -> usize {
        fn walk(v: &Value) -> usize {
            match v {
                Value::Array(a) => 1 + a.iter().map(walk).sum::<usize>(),
                Value::Object(m) => 1 + m.values().map(walk).sum::<usize>(),
                _ => 1,
            }
        }
        walk(v)
    };

    let push_val = |val: Value,
                    anchor_id: usize,
                    stack: &mut Vec<Frame>,
                    anchors: &mut HashMap<usize, Value>,
                    root: &mut Option<Value>|
     -> VResult<()> {
        if anchor_id > 0 {
            anchors.insert(anchor_id, val.clone());
        }
        match stack.last_mut() {
            Some(Frame::Seq { items, .. }) => {
                items.push(val);
                Ok(())
            }
            Some(Frame::Map {
                entries,
                seen_keys,
                pending_key,
                ..
            }) => {
                if let Some(k) = pending_key.take() {
                    entries.insert(k, val);
                    Ok(())
                } else {
                    let Value::String(k) = val else {
                        return Err(Invalid("YAML mapping keys must be strings".to_string()));
                    };
                    if !seen_keys.insert(k.clone()) {
                        return Err(Invalid(format!("duplicate YAML key {k:?}")));
                    }
                    *pending_key = Some(k);
                    Ok(())
                }
            }
            None => {
                *root = Some(val);
                Ok(())
            }
        }
    };

    for item in parser {
        let (event, span) = item.map_err(|e| Invalid(format!("YAML syntax error: {e}")))?;
        let line = span.start.line();
        match event {
            Event::StreamStart | Event::StreamEnd => {}
            Event::DocumentStart(_) => {
                doc_count += 1;
                require(doc_count <= 1, "multiple YAML documents are not permitted")?;
            }
            Event::DocumentEnd => {}
            Event::Alias(anchor_id) => {
                let Some(target) = anchors.get(&anchor_id).cloned() else {
                    return Err(Invalid(format!("unresolved YAML alias at line {line}")));
                };
                node_count += count_nodes(&target);
                require(
                    node_count <= MAX_YAML_NODES,
                    "YAML node count limit exceeded",
                )?;
                push_val(target, 0, &mut stack, &mut anchors, &mut root)?;
            }
            Event::Scalar(raw, style, anchor_id, tag) => {
                node_count += 1;
                require(
                    node_count <= MAX_YAML_NODES,
                    "YAML node count limit exceeded",
                )?;
                let val = resolve_campaign_scalar(&raw, style, tag.as_deref(), line)?;
                push_val(val, anchor_id, &mut stack, &mut anchors, &mut root)?;
            }
            Event::SequenceStart(anchor_id, tag) => {
                if let Some(t) = tag.as_deref() {
                    require(
                        t.handle == "tag:yaml.org,2002:" && t.suffix == "seq",
                        format!("unsupported YAML tag {:?} at line {line}", t.suffix),
                    )?;
                }
                if let Some(Frame::Map { pending_key, .. }) = stack.last() {
                    require(
                        pending_key.is_some(),
                        format!("sequence cannot be a mapping key at line {line}"),
                    )?;
                }
                require(
                    stack.len() < MAX_YAML_DEPTH,
                    "YAML nesting depth limit exceeded",
                )?;
                node_count += 1;
                stack.push(Frame::Seq {
                    anchor_id,
                    items: Vec::new(),
                });
            }
            Event::SequenceEnd => {
                let Some(Frame::Seq { anchor_id, items }) = stack.pop() else {
                    return Err(Invalid(format!("unexpected sequence end at line {line}")));
                };
                push_val(
                    Value::Array(items),
                    anchor_id,
                    &mut stack,
                    &mut anchors,
                    &mut root,
                )?;
            }
            Event::MappingStart(anchor_id, tag) => {
                if let Some(t) = tag.as_deref() {
                    require(
                        t.handle == "tag:yaml.org,2002:" && t.suffix == "map",
                        format!("unsupported YAML tag {:?} at line {line}", t.suffix),
                    )?;
                }
                if let Some(Frame::Map { pending_key, .. }) = stack.last() {
                    require(
                        pending_key.is_some(),
                        format!("mapping cannot be a mapping key at line {line}"),
                    )?;
                }
                require(
                    stack.len() < MAX_YAML_DEPTH,
                    "YAML nesting depth limit exceeded",
                )?;
                node_count += 1;
                stack.push(Frame::Map {
                    anchor_id,
                    entries: Map::new(),
                    seen_keys: HashSet::new(),
                    pending_key: None,
                });
            }
            Event::MappingEnd => {
                let Some(Frame::Map {
                    anchor_id,
                    entries,
                    pending_key,
                    ..
                }) = stack.pop()
                else {
                    return Err(Invalid(format!("unexpected mapping end at line {line}")));
                };
                require(
                    pending_key.is_none(),
                    format!("dangling mapping key at line {line}"),
                )?;
                push_val(
                    Value::Object(entries),
                    anchor_id,
                    &mut stack,
                    &mut anchors,
                    &mut root,
                )?;
            }
            Event::Nothing => {}
        }
    }

    Ok(root.unwrap_or(Value::Null))
}

fn resolve_campaign_scalar(
    val: &str,
    style: ScalarStyle,
    tag: Option<&Tag>,
    line: usize,
) -> VResult<Value> {
    if let Some(t) = tag {
        if t.handle == "tag:yaml.org,2002:" {
            return match t.suffix.as_str() {
                "str" => Ok(Value::String(val.to_string())),
                "null" => Ok(Value::Null),
                "bool" => match val {
                    "true" | "True" | "TRUE" => Ok(Value::Bool(true)),
                    "false" | "False" | "FALSE" => Ok(Value::Bool(false)),
                    _ => Err(Invalid(format!("invalid bool {val:?} at line {line}"))),
                },
                "int" => parse_yaml_int(val)
                    .ok_or_else(|| Invalid(format!("invalid int {val:?} at line {line}"))),
                "float" => parse_yaml_float(val)
                    .ok_or_else(|| Invalid(format!("invalid float {val:?} at line {line}"))),
                other => Err(Invalid(format!(
                    "unsupported YAML tag {other:?} at line {line}"
                ))),
            };
        }
        return Err(Invalid(format!(
            "unsupported YAML tag {:?} at line {line}",
            t.suffix
        )));
    }

    if style != ScalarStyle::Plain {
        return Ok(Value::String(val.to_string()));
    }

    match val {
        "" | "~" | "null" | "Null" | "NULL" => return Ok(Value::Null),
        "true" | "True" | "TRUE" => return Ok(Value::Bool(true)),
        "false" | "False" | "FALSE" => return Ok(Value::Bool(false)),
        ".nan" | ".NaN" | ".NAN" | ".inf" | ".Inf" | ".INF" | "+.inf" | "+.Inf" | "+.INF"
        | "-.inf" | "-.Inf" | "-.INF" => {
            return Err(Invalid(format!(
                "non-finite float literal {val:?} is not permitted at line {line}"
            )));
        }
        _ => {}
    }

    // Reject unquoted YYYY-MM-DD timestamps (INDEX-FORMAT.md: "Use strings for dates and hashes",
    // and PyYAML SafeLoader constructs datetime.date / raises ConstructorError on bad dates).
    if val.len() >= 10 {
        let b = val.as_bytes();
        if b[0..4].iter().all(u8::is_ascii_digit)
            && b[4] == b'-'
            && b[5..7].iter().all(u8::is_ascii_digit)
            && b[7] == b'-'
            && b[8..10].iter().all(u8::is_ascii_digit)
            && (val.len() == 10 || matches!(b[10], b'T' | b't' | b' '))
        {
            return Err(Invalid(format!(
                "unquoted YAML timestamp {val:?} at line {line}; quote dates as strings"
            )));
        }
    }

    if let Some(num) = parse_yaml_int(val) {
        return Ok(num);
    }
    if let Some(num) = parse_yaml_float(val) {
        return Ok(num);
    }

    Ok(Value::String(val.to_string()))
}

fn parse_yaml_int(val: &str) -> Option<Value> {
    if val.is_empty() {
        return None;
    }
    if let Some(hex) = val.strip_prefix("0x").or_else(|| val.strip_prefix("0X")) {
        if !hex.is_empty() && hex.bytes().all(|b| b.is_ascii_hexdigit()) {
            if let Ok(n) = u64::from_str_radix(hex, 16) {
                return Some(Value::Number(Number::from(n)));
            }
        }
        return None;
    }
    if let Some(oct) = val.strip_prefix("0o").or_else(|| val.strip_prefix("0O")) {
        if !oct.is_empty() && oct.bytes().all(|b| matches!(b, b'0'..=b'7')) {
            if let Ok(n) = u64::from_str_radix(oct, 8) {
                return Some(Value::Number(Number::from(n)));
            }
        }
        return None;
    }
    let digits = val.strip_prefix(['+', '-']).unwrap_or(val);
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    if digits.len() > 1 && digits.starts_with('0') {
        return None;
    }
    if let Ok(n) = val.parse::<i64>() {
        return Some(Value::Number(Number::from(n)));
    }
    if !val.starts_with('-') {
        if let Ok(n) = digits.parse::<u64>() {
            return Some(Value::Number(Number::from(n)));
        }
    }
    None
}

fn parse_yaml_float(val: &str) -> Option<Value> {
    let s = val.strip_prefix(['+', '-']).unwrap_or(val);
    if s.is_empty() || (!s.contains('.') && !s.contains('e') && !s.contains('E')) {
        return None;
    }
    let (mantissa, exp) = match s.find(['e', 'E']) {
        Some(idx) => (&s[..idx], Some(&s[idx + 1..])),
        None => (s, None),
    };
    if let Some(dot) = mantissa.find('.') {
        let before = &mantissa[..dot];
        let after = &mantissa[dot + 1..];
        if (before.is_empty() && after.is_empty())
            || !before.bytes().all(|b| b.is_ascii_digit())
            || !after.bytes().all(|b| b.is_ascii_digit())
        {
            return None;
        }
    } else if mantissa.is_empty() || !mantissa.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    if let Some(e) = exp {
        let edigits = e.strip_prefix(['+', '-']).unwrap_or(e);
        if edigits.is_empty() || !edigits.bytes().all(|b| b.is_ascii_digit()) {
            return None;
        }
    }
    let f = val.parse::<f64>().ok()?;
    let num = Number::from_f64(f)?;
    Some(Value::Number(num))
}

pub fn load_yaml_file(path: &Path) -> Result<Value, Result<Invalid, Precondition>> {
    let text = fs::read_to_string(path)
        .map_err(|e| Err(Precondition(format!("{}: {e}", path.display()))))?;
    load_yaml(&text).map_err(Ok)
}

/// Deserializes JSON while rejecting duplicate object keys at any nesting level.
pub fn load_json_strict(text: &str) -> VResult<Value> {
    struct StrictVal(Value);

    impl<'de> de::Deserialize<'de> for StrictVal {
        fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
        where
            D: Deserializer<'de>,
        {
            struct V;
            impl<'de> Visitor<'de> for V {
                type Value = StrictVal;
                fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                    f.write_str("any valid JSON value without duplicate keys")
                }
                fn visit_bool<E>(self, v: bool) -> Result<StrictVal, E> {
                    Ok(StrictVal(Value::Bool(v)))
                }
                fn visit_i64<E>(self, v: i64) -> Result<StrictVal, E> {
                    Ok(StrictVal(Value::Number(v.into())))
                }
                fn visit_u64<E>(self, v: u64) -> Result<StrictVal, E> {
                    Ok(StrictVal(Value::Number(v.into())))
                }
                fn visit_f64<E: de::Error>(self, v: f64) -> Result<StrictVal, E> {
                    Number::from_f64(v)
                        .map(|n| StrictVal(Value::Number(n)))
                        .ok_or_else(|| E::custom("non-finite JSON number"))
                }
                fn visit_str<E>(self, v: &str) -> Result<StrictVal, E> {
                    Ok(StrictVal(Value::String(v.to_string())))
                }
                fn visit_string<E>(self, v: String) -> Result<StrictVal, E> {
                    Ok(StrictVal(Value::String(v)))
                }
                fn visit_unit<E>(self) -> Result<StrictVal, E> {
                    Ok(StrictVal(Value::Null))
                }
                fn visit_none<E>(self) -> Result<StrictVal, E> {
                    Ok(StrictVal(Value::Null))
                }
                fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<StrictVal, A::Error> {
                    let mut vec = Vec::new();
                    while let Some(elem) = seq.next_element::<StrictVal>()? {
                        vec.push(elem.0);
                    }
                    Ok(StrictVal(Value::Array(vec)))
                }
                fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<StrictVal, A::Error> {
                    let mut out = Map::new();
                    while let Some((k, v)) = map.next_entry::<String, StrictVal>()? {
                        if out.contains_key(&k) {
                            return Err(de::Error::custom(format!("duplicate JSON key {k:?}")));
                        }
                        out.insert(k, v.0);
                    }
                    Ok(StrictVal(Value::Object(out)))
                }
            }
            deserializer.deserialize_any(V)
        }
    }

    let val: StrictVal =
        serde_json::from_str(text).map_err(|e| Invalid(format!("invalid JSON: {e}")))?;
    Ok(val.0)
}

// ============================================================================
// source_registry
// ============================================================================

pub mod source_registry {
    use super::*;

    pub const VERSION: i64 = 1;
    pub const SOURCE_KINDS: &[&str] = &[
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
    pub const HASH_FREE_OK_KINDS: &[&str] = &["toolchain", "model", "fixture"];
    pub const SOURCE_STATUSES: &[&str] = &["ok", "blocked", "unknown"];
    pub const FILE_ROOTS: &[&str] = &["repository", "run_store"];

    pub const SOURCE_REQUIRED: &[&str] = &[
        "id",
        "kind",
        "version",
        "sha256",
        "expected_sha256",
        "status",
        "checked",
        "provenance",
        "file",
    ];
    pub const SOURCE_OPTIONAL: &[&str] = &[
        "pin",
        "commit",
        "revision",
        "requirement_change",
        "bindings",
        "changes",
    ];
    pub const IDENTITY_REQUIRED: &[&str] =
        &["id", "version", "sha256", "status", "checked", "provenance"];
    pub const CHANGE_REQUIRED: &[&str] = &[
        "from_sha256",
        "to_sha256",
        "since",
        "reviewed",
        "sections",
        "checks",
        "scenarios",
        "evidence",
    ];

    pub fn relative(value: &Value, what: &str) -> VResult<()> {
        let s = nonempty_str(value, what)?;
        require(
            !s.contains('#'),
            format!("{what} must not contain a fragment"),
        )?;
        let p = Path::new(s);
        let has_parent = p.components().any(|c| matches!(c, Component::ParentDir));
        require(
            !p.is_absolute() && !has_parent,
            format!("{what} must be a relative path inside its root"),
        )?;
        Ok(())
    }

    pub fn validate_identity(source: &Value, label: &str) -> VResult<()> {
        validate_identity_with_keys(source, label, Some(IDENTITY_REQUIRED), None)
    }

    pub fn validate_identity_with_keys(
        source: &Value,
        label: &str,
        required: Option<&[&str]>,
        optional: Option<&[&str]>,
    ) -> VResult<()> {
        let obj = mapping(source, label, required, optional)?;
        nonempty_str(&obj["id"], &format!("{label}.id"))?;
        nonempty_str(&obj["version"], &format!("{label}.version"))?;
        let status = nonempty_str(&obj["status"], &format!("{label}.status"))?;
        require(
            SOURCE_STATUSES.contains(&status),
            format!("{label}.status not allowed: {status:?}"),
        )?;
        let sha = &obj["sha256"];
        if status == "ok" {
            let kind_exempt = obj
                .get("kind")
                .and_then(Value::as_str)
                .is_some_and(|k| HASH_FREE_OK_KINDS.contains(&k));
            if kind_exempt {
                require(
                    sha.is_null() || is_sha256(sha),
                    format!("{label}.sha256 must be null or a full SHA-256"),
                )?;
            } else {
                require(
                    is_sha256(sha),
                    format!("{label}.sha256 is required when status is ok"),
                )?;
            }
        } else {
            require(
                sha.is_null() || is_sha256(sha),
                format!("{label}.sha256 must be null or a full SHA-256"),
            )?;
        }
        require(
            is_iso_date(&obj["checked"]),
            format!("{label}.checked must be YYYY-MM-DD"),
        )?;
        let prov = mapping(
            &obj["provenance"],
            &format!("{label}.provenance"),
            Some(&["adapter", "version", "version_method"]),
            None,
        )?;
        for key in ["adapter", "version", "version_method"] {
            nonempty_str(&prov[key], &format!("{label}.provenance.{key}"))?;
        }
        Ok(())
    }

    pub fn validate_change(
        change: &Value,
        label: &str,
        known_checks: &HashSet<String>,
        known_scenarios: &HashSet<String>,
    ) -> VResult<()> {
        let obj = mapping(change, label, Some(CHANGE_REQUIRED), None)?;
        for key in ["from_sha256", "to_sha256"] {
            require(
                is_sha256(&obj[key]),
                format!("{label}.{key} must be a full SHA-256"),
            )?;
        }
        require(
            obj["from_sha256"] != obj["to_sha256"],
            format!("{label} must describe a hash change"),
        )?;
        nonempty_str(&obj["since"], &format!("{label}.since"))?;
        require(
            obj["reviewed"].is_boolean(),
            format!("{label}.reviewed must be a boolean"),
        )?;
        for key in ["sections", "checks", "scenarios"] {
            if !obj[key].is_null() {
                unique_strs(&obj[key], &format!("{label}.{key}"), false)?;
            }
        }
        if !known_checks.is_empty() && !obj["checks"].is_null() {
            if let Some(arr) = obj["checks"].as_array() {
                let unknown: Vec<&str> = arr
                    .iter()
                    .filter_map(Value::as_str)
                    .filter(|c| !known_checks.contains(*c))
                    .collect();
                require(
                    unknown.is_empty(),
                    format!("{label}.checks has unknown check(s): {unknown:?}"),
                )?;
            }
        }
        if !known_scenarios.is_empty() && !obj["scenarios"].is_null() {
            if let Some(arr) = obj["scenarios"].as_array() {
                let unknown: Vec<&str> = arr
                    .iter()
                    .filter_map(Value::as_str)
                    .filter(|s| !known_scenarios.contains(*s))
                    .collect();
                require(
                    unknown.is_empty(),
                    format!("{label}.scenarios has unknown scenario(s): {unknown:?}"),
                )?;
            }
        }
        unique_strs(&obj["evidence"], &format!("{label}.evidence"), true)?;
        Ok(())
    }

    pub fn validate_source(
        source: &Value,
        known_bases: &HashSet<String>,
        known_checks: &HashSet<String>,
        known_scenarios: &HashSet<String>,
    ) -> VResult<String> {
        let sid_hint = source
            .as_object()
            .and_then(|o| o.get("id"))
            .map(value_repr)
            .unwrap_or_else(|| "<missing>".to_string());
        let label = format!("source {sid_hint}");
        let obj = mapping(source, &label, Some(SOURCE_REQUIRED), Some(SOURCE_OPTIONAL))?;
        let sid = nonempty_str(&obj["id"], &format!("{label}.id"))?.to_string();
        let kind = nonempty_str(&obj["kind"], &format!("{label}.kind"))?;
        require(
            SOURCE_KINDS.contains(&kind),
            format!("{label}.kind not allowed: {kind:?}"),
        )?;
        validate_identity_with_keys(source, &label, Some(SOURCE_REQUIRED), Some(SOURCE_OPTIONAL))?;
        if !obj["expected_sha256"].is_null() {
            require(
                is_sha256(&obj["expected_sha256"]),
                format!("{label}.expected_sha256 must be null or a full SHA-256"),
            )?;
        }
        if !obj["file"].is_null() {
            let file_obj = mapping(
                &obj["file"],
                &format!("{label}.file"),
                Some(&["root", "path"]),
                None,
            )?;
            let root = nonempty_str(&file_obj["root"], &format!("{label}.file.root"))?;
            require(
                FILE_ROOTS.contains(&root),
                format!("{label}.file.root not allowed: {root:?}"),
            )?;
            relative(&file_obj["path"], &format!("{label}.file.path"))?;
        }
        if let Some(pin) = obj.get("pin") {
            nonempty_str(pin, &format!("{label}.pin"))?;
        }
        if let Some(commit) = obj.get("commit") {
            if !commit.is_null() {
                require(
                    is_commit(commit),
                    format!("{label}.commit must be a 40-char lowercase commit"),
                )?;
            }
        }
        if kind == "spec" {
            let rev = obj.get("revision").unwrap_or(&Value::Null);
            require(
                is_positive_int(rev),
                format!("{label}.revision must be a positive int"),
            )?;
            if let Some(rc) = obj.get("requirement_change") {
                require(
                    rc.is_boolean(),
                    format!("{label}.requirement_change must be a boolean"),
                )?;
            }
        } else {
            require(
                !obj.contains_key("revision") && !obj.contains_key("requirement_change"),
                format!("{label} cannot declare spec revision fields"),
            )?;
        }
        if let Some(bindings_val) = obj.get("bindings") {
            let bindings = unique_strs(bindings_val, &format!("{label}.bindings"), true)?;
            if !known_bases.is_empty() {
                let unknown: Vec<&String> = bindings
                    .iter()
                    .filter(|b| !known_bases.contains(b.as_str()))
                    .collect();
                require(
                    unknown.is_empty(),
                    format!("{label}.bindings has unknown basis ID(s): {unknown:?}"),
                )?;
            }
        }
        let mut seen_pairs = HashSet::new();
        if let Some(changes_val) = obj.get("changes") {
            let arr = list(changes_val, &format!("{label}.changes"), false)?;
            for (i, change) in arr.iter().enumerate() {
                validate_change(
                    change,
                    &format!("{label}.changes[{i}]"),
                    known_checks,
                    known_scenarios,
                )?;
                let c_obj = change.as_object().unwrap();
                let pair = (
                    c_obj["from_sha256"].as_str().unwrap().to_string(),
                    c_obj["to_sha256"].as_str().unwrap().to_string(),
                );
                require(
                    seen_pairs.insert(pair.clone()),
                    format!("{label}.changes repeats {pair:?}"),
                )?;
            }
        }
        Ok(sid)
    }

    pub fn validate(
        registry: &Value,
        claims_doc: Option<&Value>,
        status_doc: Option<&Value>,
    ) -> VResult<BTreeMap<String, usize>> {
        let reg = mapping(
            registry,
            "sources.yaml",
            Some(&["version", "campaign", "sources"]),
            Some(&["citations", "premises", "contradictions"]),
        )?;
        require(
            is_exact_int(&reg["version"]) == Some(VERSION),
            "sources.yaml.version must be 1",
        )?;
        let campaign = nonempty_str(&reg["campaign"], "sources.yaml.campaign")?;

        let mut known_claims = HashSet::new();
        let mut known_checks = HashSet::new();
        let mut known_scenarios = HashSet::new();
        let mut known_bases = HashSet::new();
        let mut entries: HashMap<String, &Value> = HashMap::new();
        let mut observations = HashSet::new();

        if let Some(cd) = claims_doc.and_then(Value::as_object) {
            if let Some(c_camp) = cd.get("campaign").and_then(Value::as_str) {
                require(
                    campaign == c_camp,
                    "sources.yaml.campaign must match claims.yaml.campaign",
                )?;
            }
            if let Some(claims_arr) = cd.get("claims").and_then(Value::as_array) {
                for c in claims_arr {
                    if let Some(c_obj) = c.as_object() {
                        if let Some(id) = c_obj.get("id").and_then(Value::as_str) {
                            known_claims.insert(id.to_string());
                        }
                        if let Some(chks) = c_obj.get("checks").and_then(Value::as_array) {
                            for chk in chks.iter().filter_map(Value::as_str) {
                                known_checks.insert(chk.to_string());
                            }
                        }
                        if let Some(scens) = c_obj.get("scenarios").and_then(Value::as_array) {
                            for s in scens.iter().filter_map(Value::as_str) {
                                known_scenarios.insert(s.to_string());
                            }
                        }
                    }
                }
            }
        }

        if let Some(sd) = status_doc.and_then(Value::as_object) {
            if let Some(s_camp) = sd.get("campaign").and_then(Value::as_str) {
                require(
                    campaign == s_camp,
                    "sources.yaml.campaign must match status.yaml.campaign",
                )?;
            }
            if let Some(bases_obj) = sd.get("bases").and_then(Value::as_object) {
                for k in bases_obj.keys() {
                    known_bases.insert(k.clone());
                }
            }
            if let Some(entries_arr) = sd.get("entries").and_then(Value::as_array) {
                for e in entries_arr {
                    if let Some(e_obj) = e.as_object() {
                        if let Some(id) = e_obj.get("id").and_then(Value::as_str) {
                            entries.insert(id.to_string(), e);
                            if e_obj.get("kind").and_then(Value::as_str) == Some("observation") {
                                observations.insert(id.to_string());
                            }
                        }
                    }
                }
            }
        }

        let sources_arr = list(&reg["sources"], "sources.yaml.sources", true)?;
        let mut source_ids = HashSet::new();
        let mut sources_by_id: HashMap<String, &Value> = HashMap::new();
        for s in sources_arr {
            let sid = validate_source(s, &known_bases, &known_checks, &known_scenarios)?;
            require(
                source_ids.insert(sid.clone()),
                format!("duplicate source id {sid:?}"),
            )?;
            sources_by_id.insert(sid, s);
        }

        let empty_map = Value::Object(Map::new());
        let citations = mapping(
            reg.get("citations").unwrap_or(&empty_map),
            "sources.yaml.citations",
            None,
            None,
        )?;
        for (entry_id, by_source) in citations {
            nonempty_str(
                &Value::String(entry_id.clone()),
                "sources.yaml.citations key",
            )?;
            if !entries.is_empty() {
                require(
                    entries.contains_key(entry_id),
                    format!("citations references unknown entry {entry_id:?}"),
                )?;
                let kind = entries[entry_id]
                    .as_object()
                    .and_then(|o| o.get("kind"))
                    .and_then(Value::as_str);
                require(
                    matches!(kind, Some("verification" | "item")),
                    format!("citations.{entry_id} must name a verification or item entry"),
                )?;
            }
            let source_map = mapping(by_source, &format!("citations.{entry_id}"), None, None)?;
            require(
                !source_map.is_empty(),
                format!("citations.{entry_id} must not be empty"),
            )?;
            for (source_id, sections) in source_map {
                require(
                    sources_by_id.contains_key(source_id),
                    format!("citations.{entry_id} references unknown source {source_id:?}"),
                )?;
                let skind = sources_by_id[source_id]
                    .as_object()
                    .and_then(|o| o.get("kind"))
                    .and_then(Value::as_str);
                require(
                    matches!(skind, Some("document" | "kernel")),
                    format!("citations.{entry_id}.{source_id} must reference a document or kernel source"),
                )?;
                unique_strs(sections, &format!("citations.{entry_id}.{source_id}"), true)?;
            }
        }

        let premises = mapping(
            reg.get("premises").unwrap_or(&empty_map),
            "sources.yaml.premises",
            None,
            None,
        )?;
        for (claim_id, obs_ids) in premises {
            nonempty_str(
                &Value::String(claim_id.clone()),
                "sources.yaml.premises key",
            )?;
            if !known_claims.is_empty() {
                require(
                    known_claims.contains(claim_id),
                    format!("premises references unknown claim {claim_id:?}"),
                )?;
            }
            let ids = unique_strs(obs_ids, &format!("premises.{claim_id}"), true)?;
            if !observations.is_empty() {
                for obs_id in ids {
                    require(
                        observations.contains(&obs_id),
                        format!("premises.{claim_id} references non-observation {obs_id:?}"),
                    )?;
                }
            }
        }

        let empty_list = Value::Array(Vec::new());
        let contradictions = list(
            reg.get("contradictions").unwrap_or(&empty_list),
            "sources.yaml.contradictions",
            false,
        )?;
        let mut seen_contradictions = HashSet::new();
        for (i, item) in contradictions.iter().enumerate() {
            let label = format!("contradictions[{i}]");
            let obj = mapping(
                item,
                &label,
                Some(&["observation", "since", "conflict"]),
                None,
            )?;
            let obs_id = nonempty_str(&obj["observation"], &format!("{label}.observation"))?;
            if !observations.is_empty() {
                require(
                    observations.contains(obs_id),
                    format!("{label}.observation references non-observation {obs_id:?}"),
                )?;
            }
            nonempty_str(&obj["since"], &format!("{label}.since"))?;
            let conflict = nonempty_str(&obj["conflict"], &format!("{label}.conflict"))?;
            let (path_part, _) = conflict.split_once('#').unwrap_or((conflict, ""));
            relative(
                &Value::String(path_part.to_string()),
                &format!("{label}.conflict"),
            )?;
            let key = (obs_id.to_string(), conflict.to_string());
            require(
                seen_contradictions.insert(key),
                format!("{label} duplicates an existing contradiction"),
            )?;
        }

        let mut counts = BTreeMap::new();
        counts.insert("sources".to_string(), sources_arr.len());
        counts.insert("citations".to_string(), citations.len());
        counts.insert("premises".to_string(), premises.len());
        counts.insert("contradictions".to_string(), contradictions.len());
        Ok(counts)
    }
}

// ============================================================================
// deployment
// ============================================================================

pub mod deployment {
    use super::*;

    pub const VERSION: i64 = 1;
    pub const PLUGIN_KINDS: &[&str] = &["source", "fixture", "producer", "role"];
    pub const ROLES: &[&str] = &["reader", "implementer", "reviewer"];

    /// Authoritative support classes from `skills/spec-format/schema/spec.schema.json`.
    pub const SCHEMA_SUPPORT_CLASSES: &[&str] = &[
        "hw-datasheet",
        "standard",
        "src-fit",
        "src-ref",
        "inference",
        "silicon",
        "emulated",
        "gap",
    ];

    /// `hwspecs/config.toml` under the config directory, or the pre-rename
    /// `driver-lab/config.toml` when only that one exists.
    pub fn default_config_path() -> PathBuf {
        let base = match std::env::var("XDG_CONFIG_HOME") {
            Ok(xdg) if !xdg.is_empty() => PathBuf::from(xdg),
            _ => match std::env::var("HOME") {
                Ok(home) => PathBuf::from(home).join(".config"),
                Err(_) => PathBuf::from(".config"),
            },
        };
        let current = base.join("hwspecs/config.toml");
        let legacy = base.join("driver-lab/config.toml");
        if !current.exists() && legacy.exists() {
            return legacy;
        }
        current
    }

    pub fn expand_user_path(raw: &str) -> PathBuf {
        if let Some(rest) = raw.strip_prefix("~/") {
            if let Ok(home) = std::env::var("HOME") {
                return PathBuf::from(home).join(rest);
            }
        }
        PathBuf::from(raw)
    }

    pub fn evidence_classes(
        repo_root: &Path,
        target_spec: Option<&Path>,
    ) -> Result<BTreeSet<String>, Result<Invalid, Precondition>> {
        let mut classes: BTreeSet<String> = SCHEMA_SUPPORT_CLASSES
            .iter()
            .map(|s| (*s).to_string())
            .collect();

        // Also read skills/spec-format/schema/spec.schema.json if present on disk so tests
        // exercising custom repo roots see the schema file's enum if modified.
        let schema_path = repo_root.join("skills/spec-format/schema/spec.schema.json");
        if schema_path.is_file() {
            if let Ok(text) = fs::read_to_string(&schema_path) {
                if let Ok(schema) = serde_json::from_str::<Value>(&text) {
                    if let Some(arr) = schema
                        .pointer("/$defs/supportClass/enum")
                        .and_then(Value::as_array)
                    {
                        classes.clear();
                        for v in arr {
                            let s = nonempty_str(v, "spec.schema.json supportClass").map_err(Ok)?;
                            classes.insert(s.to_string());
                        }
                    }
                }
            }
        }

        if let Some(ts_path) = target_spec {
            let text = fs::read_to_string(ts_path)
                .map_err(|e| Err(Precondition(format!("{}: {e}", ts_path.display()))))?;
            let re = Regex::new(r"(?m)^\|\s*`\[([a-z0-9-]+)\]`\s*\|").unwrap();
            let mut spec_classes = BTreeSet::new();
            for caps in re.captures_iter(&text) {
                spec_classes.insert(caps[1].to_string());
            }
            if spec_classes.is_empty() {
                return Err(Ok(Invalid(
                    "target spec defines no evidence classes".to_string(),
                )));
            }
            classes.extend(spec_classes);
        }
        Ok(classes)
    }

    fn skill_ref(value: &Value, what: &str) -> VResult<()> {
        let text = nonempty_str(value, what)?;
        let re = Regex::new(r"^skill:[a-z0-9][a-z0-9-]*$").unwrap();
        require(
            re.is_match(text),
            format!("{what} must have the form 'skill:<name>'"),
        )
    }

    fn command(value: &Value, what: &str) -> VResult<()> {
        let items = list(value, what, true)?;
        for (i, item) in items.iter().enumerate() {
            nonempty_str(item, &format!("{what}[{i}]"))?;
        }
        Ok(())
    }

    pub fn validate(
        document: &Value,
        repo_root: &Path,
        target_spec: Option<&Path>,
    ) -> Result<Value, Result<Invalid, Precondition>> {
        let classes = evidence_classes(repo_root, target_spec)?;
        validate_with_classes(document, &classes).map_err(Ok)
    }

    pub fn validate_with_classes(document: &Value, classes: &BTreeSet<String>) -> VResult<Value> {
        let doc = mapping(document, "deployment", Some(&["version", "plugins"]), None)?;
        require(
            is_exact_int(&doc["version"]) == Some(VERSION),
            "deployment.version must be 1",
        )?;
        let plugins = list(&doc["plugins"], "deployment.plugins", true)?;

        let mut ids = HashSet::new();
        let mut roles = Map::new();
        for (i, raw) in plugins.iter().enumerate() {
            let label = format!("deployment.plugins[{i}]");
            let item = mapping(raw, &label, None, None)?;
            for req_key in ["id", "kind", "via"] {
                require(
                    item.contains_key(req_key),
                    format!("{label} missing key {req_key:?}"),
                )?;
            }
            let pid = nonempty_str(&item["id"], &format!("{label}.id"))?;
            require(
                ids.insert(pid.to_string()),
                format!("deployment.plugins repeats id {pid:?}"),
            )?;
            let kind = nonempty_str(&item["kind"], &format!("{label}.kind"))?;
            require(
                PLUGIN_KINDS.contains(&kind),
                format!("{label}.kind not allowed: {kind:?}"),
            )?;
            skill_ref(&item["via"], &format!("{label}.via"))?;

            if kind == "source" || kind == "fixture" {
                mapping(raw, &label, Some(&["id", "kind", "command", "via"]), None)?;
                command(&item["command"], &format!("{label}.command"))?;
            } else if kind == "producer" {
                mapping(raw, &label, Some(&["id", "kind", "class", "via"]), None)?;
                let cls = nonempty_str(&item["class"], &format!("{label}.class"))?;
                require(
                    classes.contains(cls),
                    format!("{label}.class {cls:?} is not defined by the target spec"),
                )?;
            } else {
                mapping(
                    raw,
                    &label,
                    Some(&["id", "kind", "agent", "model", "via"]),
                    None,
                )?;
                require(
                    ROLES.contains(&pid),
                    format!("{label}.id must be one of {ROLES:?} for role plugins"),
                )?;
                nonempty_str(&item["agent"], &format!("{label}.agent"))?;
                let model = mapping(
                    &item["model"],
                    &format!("{label}.model"),
                    Some(&["name", "version"]),
                    None,
                )?;
                let m_name = nonempty_str(&model["name"], &format!("{label}.model.name"))?;
                let m_ver = nonempty_str(&model["version"], &format!("{label}.model.version"))?;
                roles.insert(
                    pid.to_string(),
                    json!({
                        "agent": item["agent"],
                        "model": {
                            "name": m_name,
                            "version": m_ver,
                        },
                        "via": item["via"],
                    }),
                );
            }
        }

        let missing_roles: Vec<&&str> = ROLES.iter().filter(|r| !roles.contains_key(**r)).collect();
        require(
            missing_roles.is_empty(),
            format!("deployment.plugins missing role(s): {missing_roles:?}"),
        )?;

        let mut classes_vec: Vec<Value> = classes.iter().cloned().map(Value::String).collect();
        classes_vec.sort_by(|a, b| a.as_str().cmp(&b.as_str()));
        Ok(json!({
            "version": VERSION,
            "plugins": plugins,
            "roles": roles,
            "evidence_classes": classes_vec,
        }))
    }

    pub fn load(
        path: Option<&Path>,
        config_path: Option<&Path>,
        repo_root: &Path,
        target_spec: Option<&Path>,
    ) -> Result<Value, Result<Invalid, Precondition>> {
        let chosen: PathBuf = if let Some(p) = path {
            expand_user_path(&p.to_string_lossy())
        } else {
            let cfg_file = config_path
                .map(Path::to_path_buf)
                .unwrap_or_else(default_config_path);
            let mut from_cfg: Option<PathBuf> = None;
            if cfg_file.exists() {
                let text = fs::read_to_string(&cfg_file)
                    .map_err(|e| Err(Precondition(format!("{}: {e}", cfg_file.display()))))?;
                let parsed: toml::Value = toml::from_str(&text)
                    .map_err(|e| Ok(Invalid(format!("config is not valid TOML: {e}"))))?;
                let Some(table) = parsed.as_table() else {
                    return Err(Ok(Invalid("config must be a TOML table".to_string())));
                };
                if let Some(dep_val) = table.get("deployment") {
                    let Some(s) = dep_val.as_str() else {
                        return Err(Ok(Invalid(
                            "deployment in config must be a nonempty string".to_string(),
                        )));
                    };
                    if s.trim().is_empty() {
                        return Err(Ok(Invalid(
                            "deployment in config must be a nonempty string".to_string(),
                        )));
                    }
                    let candidate = expand_user_path(s);
                    from_cfg = Some(if candidate.is_absolute() {
                        candidate
                    } else {
                        cfg_file
                            .parent()
                            .unwrap_or_else(|| Path::new("."))
                            .join(candidate)
                    });
                }
            }
            from_cfg.unwrap_or_else(|| repo_root.join("evals/deployment.yaml"))
        };

        let text = fs::read_to_string(&chosen)
            .map_err(|e| Err(Precondition(format!("{}: {e}", chosen.display()))))?;
        let raw = load_yaml(&text).map_err(|e| {
            Ok(Invalid(format!(
                "deployment manifest is not valid YAML: {e}"
            )))
        })?;
        validate(&raw, repo_root, target_spec)
    }
}

pub mod campaign_cli;
pub mod contract_check;
pub mod index_check;
pub mod pinned_file_adapter;
pub mod stopping;
pub mod sweep;

use clap::Parser;

pub fn run_campaign_cmd(
    _cli: &crate::Cli,
    args: &crate::CampaignArgs,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> i32 {
    let mut parse_args = vec!["hwspecs campaign".to_string()];
    parse_args.extend(args.args.iter().cloned());
    let sub = match crate::campaign::campaign_cli::CampaignSubcommands::try_parse_from(parse_args) {
        Ok(s) => s,
        Err(e) => {
            let _ = write!(stderr, "{}", e);
            return crate::diagnostic::EXIT_USAGE_ERROR;
        }
    };

    match sub.command {
        crate::campaign::campaign_cli::CampaignCommand::IndexCheck(cmd_args) => {
            run_index_check(&cmd_args, stdout, stderr)
        }
        crate::campaign::campaign_cli::CampaignCommand::Sweep(_args) => 0,
        crate::campaign::campaign_cli::CampaignCommand::ContractCheck(_args) => 0,
        crate::campaign::campaign_cli::CampaignCommand::Stopping(_args) => 0,
        _ => {
            let _ = writeln!(stderr, "campaign command not implemented");
            crate::diagnostic::EXIT_USAGE_ERROR
        }
    }
}

fn run_index_check(
    args: &crate::campaign::campaign_cli::IndexCheckArgs,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> i32 {
    let mut counts = serde_json::Map::new();
    let mut findings: Vec<String> = Vec::new();
    let mut code = 0;

    let campaign_path = if let Some(p) = &args.campaign {
        p.clone()
    } else {
        let _ = writeln!(stderr, "campaign is required");
        return crate::diagnostic::EXIT_USAGE_ERROR;
    };

    let claims_path = campaign_path.join("claims.yaml");
    let status_path = campaign_path.join("status.yaml");

    let claims_val = match crate::campaign::load_yaml_file(&claims_path) {
        Ok(val) => val,
        Err(Ok(invalid)) => {
            findings.push(invalid.to_string());
            code = 1;
            serde_json::Value::Null
        }
        Err(Err(precond)) => {
            findings.push(precond.to_string());
            code = 3;
            serde_json::Value::Null
        }
    };

    let status_val = match crate::campaign::load_yaml_file(&status_path) {
        Ok(val) => val,
        Err(Ok(invalid)) => {
            if code == 0 {
                findings.push(invalid.to_string());
                code = 1;
            }
            serde_json::Value::Null
        }
        Err(Err(precond)) => {
            if code == 0 {
                findings.push(precond.to_string());
                code = 3;
            }
            serde_json::Value::Null
        }
    };

    if code == 0 {
        let root = args
            .root
            .clone()
            .unwrap_or_else(|| std::env::current_dir().unwrap());
        match crate::campaign::index_check::validate(&claims_val, &status_val, Some(&root)) {
            Ok(res) => {
                if let serde_json::Value::Object(map) = res {
                    counts = map;
                }
            }
            Err(e) => {
                findings.push(e.to_string());
                code = 1;
            }
        }
    }

    if args.json {
        let report = serde_json::json!({
            "ok": code == 0,
            "counts": counts,
            "findings": findings
        });
        let _ = writeln!(stdout, "{}", serde_json::to_string(&report).unwrap());
    } else if !findings.is_empty() {
        let _ = writeln!(
            stdout,
            "{}",
            findings.join(
                "
"
            )
        );
    } else {
        let mut parts = Vec::new();
        for (k, v) in &counts {
            parts.push(format!("{} {}", v, k));
        }
        let _ = writeln!(stdout, "OK: {}", parts.join(", "));
    }

    code
}
