// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Embedded JSON Schema registry, extension fragment validator, and `driver-lab validate`
//! implementation (`RT-2`, `BF-IMX-14`, `BF-IMX-18`).
//!
//! Ports the schema loading, extension fragment validation (`check_fragment`, `load_extension`),
//! error message normalization and `unevaluatedProperties` cascade suppression (`schema_findings`),
//! and `validate` command from `skills/spec-format/scripts/spec.py`.

use crate::diagnostic::{
    bad_file_name, char_label, is_yaml_refused_char, visible_name, DiagnosticEnvelope, Finding,
    EXIT_DOMAIN_FAILURE, EXIT_OK, EXIT_USAGE_ERROR,
};
use crate::model::{
    format_where, schema_kind, SchemaKind, ValidatedFileEntry, EXTENSION_URN, MARKER,
};
use crate::yaml_strict::{load_file, load_text, Loaded, Mark, PathSegment, MAX_BYTES};
use crate::ValidateArgs;
use jsonschema::error::{TypeKind, ValidationErrorKind};
use jsonschema::{Draft, Resource, ValidationError, Validator};
use regex::Regex;
use serde::de::{self, Deserializer, MapAccess, SeqAccess, Visitor};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::fs::File;
use std::io::{Read, Write};
use std::path::{Component, Path};
use std::sync::LazyLock;
use unicode_normalization::is_nfc;

/// Embedded `spec.schema.json` (`*.spec.yaml` and `*.facts.yaml`, including `BF-IMX-14`).
pub const SPEC_SCHEMA_JSON: &str = include_str!("../skills/spec-format/schema/spec.schema.json");

/// Embedded `root.schema.json` (`board-specs.yaml`).
pub const ROOT_SCHEMA_JSON: &str = include_str!("../skills/spec-format/schema/root.schema.json");

/// Embedded `verify.schema.json` (`*.verify.yaml`).
pub const VERIFY_SCHEMA_JSON: &str =
    include_str!("../skills/spec-format/schema/verify.schema.json");

/// Embedded `corpus.schema.json` (`corpus.yaml`).
pub const CORPUS_SCHEMA_JSON: &str =
    include_str!("../skills/spec-format/schema/corpus.schema.json");

/// Embedded `index.schema.json` (`*.index.yaml`).
pub const INDEX_SCHEMA_JSON: &str = include_str!("../skills/spec-format/schema/index.schema.json");

const FRAGMENT_KEYS: &[&str] = &[
    "$comment",
    "title",
    "description",
    "type",
    "properties",
    "required",
];

const CITATION_FIELDS: &[&str] = &[
    "repo", "path", "doc", "anchors", "lines", "symbol", "node", "url",
];

const FRAGMENT_PLAIN: &[&str] = &[
    "$comment",
    "title",
    "description",
    "type",
    "properties",
    "required",
    "enum",
    "const",
    "pattern",
    "format",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
    "uniqueItems",
    "items",
    "minProperties",
    "maxProperties",
    "additionalProperties",
    "unevaluatedProperties",
];

const KEYWORDS_2020_12: &[&str] = &[
    "$schema",
    "$id",
    "$ref",
    "$anchor",
    "$dynamicRef",
    "$dynamicAnchor",
    "$vocabulary",
    "$comment",
    "$defs",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "dependentSchemas",
    "prefixItems",
    "items",
    "contains",
    "properties",
    "patternProperties",
    "additionalProperties",
    "propertyNames",
    "unevaluatedItems",
    "unevaluatedProperties",
    "type",
    "enum",
    "const",
    "multipleOf",
    "maximum",
    "exclusiveMaximum",
    "minimum",
    "exclusiveMinimum",
    "maxLength",
    "minLength",
    "pattern",
    "maxItems",
    "minItems",
    "uniqueItems",
    "maxContains",
    "minContains",
    "maxProperties",
    "minProperties",
    "required",
    "dependentRequired",
    "format",
    "contentEncoding",
    "contentMediaType",
    "contentSchema",
    "title",
    "description",
    "default",
    "deprecated",
    "readOnly",
    "writeOnly",
    "examples",
];

const SCHEMA_ONE: &[&str] = &[
    "items",
    "contains",
    "not",
    "if",
    "then",
    "else",
    "propertyNames",
    "additionalProperties",
    "unevaluatedProperties",
    "unevaluatedItems",
    "additionalItems",
    "contentSchema",
];

const SCHEMA_MAP: &[&str] = &[
    "properties",
    "patternProperties",
    "dependentSchemas",
    "$defs",
    "definitions",
];

const SCHEMA_LIST: &[&str] = &["allOf", "anyOf", "oneOf", "prefixItems"];

static FRAGMENT_PROPERTY_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[a-z][a-z0-9_]*$").expect("valid FRAGMENT_PROPERTY_RE"));

static EMBEDDED_SCHEMAS: LazyLock<BTreeMap<String, Value>> = LazyLock::new(|| {
    let mut map = BTreeMap::new();
    let pairs = [
        ("spec", SPEC_SCHEMA_JSON),
        ("root", ROOT_SCHEMA_JSON),
        ("verify", VERIFY_SCHEMA_JSON),
        ("corpus", CORPUS_SCHEMA_JSON),
        ("index", INDEX_SCHEMA_JSON),
    ];
    for (kind, raw) in pairs {
        let val = parse_strict_json(raw).unwrap_or_else(|e| {
            panic!("embedded {kind}.schema.json must be valid strict JSON: {e}")
        });
        map.insert(kind.to_string(), val);
    }
    map
});

/// Default `source-observed` schema fragment used when no root extension fragment is loaded.
#[must_use]
pub fn default_extension_schema() -> Value {
    json!({
        "$id": EXTENSION_URN,
        "$comment": "message: a source-observed entry needs the extension's schema fragment; pass --root with a root marker whose extensions names it (D15)",
        "not": {}
    })
}

/// Returns the five embedded Format 2 JSON Schemas keyed by kind (`"spec"`, `"root"`, `"verify"`,
/// `"corpus"`, `"index"`).
#[must_use]
pub fn load_schemas() -> BTreeMap<String, Value> {
    EMBEDDED_SCHEMAS.clone()
}

/// Collects every field name declared by a core support class in `spec.schema.json`, plus `"class"`.
#[must_use]
pub fn core_fields(schemas: &BTreeMap<String, Value>) -> BTreeSet<String> {
    let mut names = BTreeSet::new();
    names.insert("class".to_string());
    if let Some(branches) = schemas
        .get("spec")
        .and_then(|s| s.get("$defs"))
        .and_then(|d| d.get("support"))
        .and_then(|sup| sup.get("allOf"))
        .and_then(Value::as_array)
    {
        for branch in branches {
            if let Some(props) = branch
                .get("then")
                .and_then(|t| t.get("properties"))
                .and_then(Value::as_object)
            {
                for k in props.keys() {
                    names.insert(k.clone());
                }
            }
        }
    }
    names
}

/// Strict JSON value wrapper that rejects duplicate object keys during deserialization.
struct StrictJsonValue(Value);

impl<'de> serde::Deserialize<'de> for StrictJsonValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct StrictVisitor;

        impl<'de> Visitor<'de> for StrictVisitor {
            type Value = StrictJsonValue;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("any valid JSON value without duplicate keys")
            }

            fn visit_bool<E>(self, v: bool) -> Result<Self::Value, E> {
                Ok(StrictJsonValue(Value::Bool(v)))
            }

            fn visit_i64<E>(self, v: i64) -> Result<Self::Value, E> {
                Ok(StrictJsonValue(Value::Number(v.into())))
            }

            fn visit_u64<E>(self, v: u64) -> Result<Self::Value, E> {
                Ok(StrictJsonValue(Value::Number(v.into())))
            }

            fn visit_f64<E>(self, v: f64) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                serde_json::Number::from_f64(v)
                    .map(|n| StrictJsonValue(Value::Number(n)))
                    .ok_or_else(|| de::Error::custom("NaN or Infinity is not JSON"))
            }

            fn visit_str<E>(self, v: &str) -> Result<Self::Value, E> {
                Ok(StrictJsonValue(Value::String(v.to_owned())))
            }

            fn visit_string<E>(self, v: String) -> Result<Self::Value, E> {
                Ok(StrictJsonValue(Value::String(v)))
            }

            fn visit_unit<E>(self) -> Result<Self::Value, E> {
                Ok(StrictJsonValue(Value::Null))
            }

            fn visit_seq<A>(self, mut seq: A) -> Result<Self::Value, A::Error>
            where
                A: SeqAccess<'de>,
            {
                let mut vec = Vec::new();
                while let Some(elem) = seq.next_element::<StrictJsonValue>()? {
                    vec.push(elem.0);
                }
                Ok(StrictJsonValue(Value::Array(vec)))
            }

            fn visit_map<M>(self, mut access: M) -> Result<Self::Value, M::Error>
            where
                M: MapAccess<'de>,
            {
                let mut map = Map::new();
                while let Some((k, v)) = access.next_entry::<String, StrictJsonValue>()? {
                    if map.contains_key(&k) {
                        return Err(de::Error::custom(format!(
                            "duplicate key {}",
                            py_repr_str(&k)
                        )));
                    }
                    map.insert(k, v.0);
                }
                Ok(StrictJsonValue(Value::Object(map)))
            }
        }

        deserializer.deserialize_any(StrictVisitor)
    }
}

/// Parses a JSON string strictly: rejects duplicate keys, `NaN`/`Infinity`/`-Infinity`, and
/// trailing tokens (`spec.py:_strict_json`).
pub fn parse_strict_json(text: &str) -> Result<Value, String> {
    let mut de = serde_json::Deserializer::from_str(text);
    match StrictJsonValue::deserialize(&mut de) {
        Ok(StrictJsonValue(val)) => match de.end() {
            Ok(()) => Ok(val),
            Err(e) => Err(normalize_json_err(text, &e.to_string())),
        },
        Err(e) => Err(normalize_json_err(text, &e.to_string())),
    }
}

fn normalize_json_err(text: &str, err: &str) -> String {
    if err.contains("duplicate key") {
        return err.to_string();
    }
    for tok in ["-Infinity", "Infinity", "NaN"] {
        if text.contains(tok) {
            return format!("{tok} is not JSON");
        }
    }
    format!("Expecting value: {err}")
}

/// Python-compatible single-quoted string representation (`'...'`).
#[must_use]
pub fn py_repr_str(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('\'');
    for ch in s.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\'' => out.push_str("\\'"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 || (c as u32) == 0x7f => {
                out.push_str(&format!("\\x{:02x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out.push('\'');
    out
}

/// Python-compatible `repr(value)` for `serde_json::Value`.
#[must_use]
pub fn py_repr_value(v: &Value) -> String {
    match v {
        Value::Null => "None".to_string(),
        Value::Bool(true) => "True".to_string(),
        Value::Bool(false) => "False".to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => py_repr_str(s),
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(py_repr_value).collect();
            format!("[{}]", parts.join(", "))
        }
        Value::Object(map) => {
            let parts: Vec<String> = map
                .iter()
                .map(|(k, val)| format!("{}: {}", py_repr_str(k), py_repr_value(val)))
                .collect();
            format!("{{{}}}", parts.join(", "))
        }
    }
}

/// Checks why a fragment's regex pattern would not mean the same in Python and ECMA-262
/// (`spec.py:_pattern_problem`).
#[must_use]
pub fn pattern_problem(pattern: &str) -> Option<String> {
    if pattern.contains("(?#") {
        return Some("uses a (?#...) comment, which ECMA-262 does not have".to_string());
    }
    let chars: Vec<char> = pattern.chars().collect();
    let mut escaped = false;
    let mut in_class = false;
    let mut class_start: isize = -1;
    for (at, &ch) in chars.iter().enumerate() {
        let at_isize = at as isize;
        if escaped {
            escaped = false;
            if ch == 'Z' {
                return Some(
                    "uses \\Z, an end anchor only in Python; end it with (?![\\s\\S])".to_string(),
                );
            }
        } else if ch == '\\' {
            escaped = true;
        } else if in_class {
            let first = at_isize == class_start + 1
                || (at_isize == class_start + 2
                    && chars.get((class_start + 1) as usize) == Some(&'^'));
            if ch == ']' && !first {
                in_class = false;
            }
        } else if ch == '[' {
            in_class = true;
            class_start = at_isize;
        } else if ch == '$' {
            return Some(
                "uses $, which in Python also matches before a final newline; end it with (?![\\s\\S])"
                    .to_string(),
            );
        }
    }
    None
}

/// Validates an extension schema fragment (`spec.py:check_fragment`, D15).
#[must_use]
pub fn check_fragment(
    fragment: &Value,
    where_path: &Path,
    reserved: &BTreeSet<String>,
) -> Vec<String> {
    let where_str = where_path.display().to_string();
    let Some(frag_obj) = fragment.as_object() else {
        return vec![format!("{where_str}: a schema fragment is a JSON object")];
    };

    let mut problems = Vec::new();
    if let Err(err) = jsonschema::meta::validate(fragment) {
        problems.push(format!("{where_str}: not a valid JSON Schema: {err}"));
    }

    let allowed_top: BTreeSet<&str> = FRAGMENT_KEYS.iter().copied().collect();
    let extra: Vec<&str> = frag_obj
        .keys()
        .map(String::as_str)
        .filter(|k| !allowed_top.contains(k))
        .collect();
    if !extra.is_empty() {
        problems.push(format!(
            "{where_str}: keywords not allowed in a fragment: {}",
            extra.join(", ")
        ));
    }

    if frag_obj.get("type").and_then(Value::as_str) != Some("object") {
        problems.push(format!(
            "{where_str}: a fragment declares \"type\": \"object\""
        ));
    }

    let empty_map = Map::new();
    let props = match frag_obj.get("properties").and_then(Value::as_object) {
        Some(p) if !p.is_empty() => p,
        _ => {
            problems.push(format!(
                "{where_str}: a fragment declares its fields in a non-empty properties"
            ));
            &empty_map
        }
    };

    for name in props.keys() {
        if reserved.contains(name) {
            problems.push(format!(
                "{where_str}: field name {} is a core field; choose another",
                py_repr_str(name)
            ));
        } else if !FRAGMENT_PROPERTY_RE.is_match(name) || name.contains('\n') {
            problems.push(format!(
                "{where_str}: field name {} not allowed (lowercase letters, digits and _)",
                py_repr_str(name)
            ));
        }
    }

    if let Some(req_val) = frag_obj.get("required") {
        let valid_req = req_val.as_array().is_some_and(|arr| {
            arr.iter()
                .all(|r| r.as_str().is_some_and(|s| props.contains_key(s)))
        });
        if !valid_req {
            problems.push(format!(
                "{where_str}: required lists only fields the fragment declares"
            ));
        }
    }

    fn walk(schema: &Value, trail: &[String], where_str: &str, problems: &mut Vec<String>) {
        let Some(obj) = schema.as_object() else {
            return;
        };
        for (key, value) in obj {
            let mut next_trail = trail.to_vec();
            next_trail.push(key.clone());
            let at = next_trail.join("/");

            if key.starts_with('$') && key != "$comment" {
                problems.push(format!("{where_str}: {key} at {at} not allowed"));
            } else if !KEYWORDS_2020_12.contains(&key.as_str()) {
                problems.push(format!(
                    "{where_str}: {key} at {at} is not a draft 2020-12 keyword"
                ));
            } else if !FRAGMENT_PLAIN.contains(&key.as_str()) {
                problems.push(format!(
                    "{where_str}: {key} at {at} not allowed: a fragment uses plain properties and value constraints only"
                ));
            } else if matches!(
                key.as_str(),
                "additionalProperties" | "unevaluatedProperties"
            ) && !value.is_boolean()
            {
                problems.push(format!(
                    "{where_str}: {key} at {at} not allowed with a schema value; write true or false"
                ));
            } else if key == "items" && !value.is_object() {
                problems.push(format!("{where_str}: items at {at} must be one schema"));
            }

            if key == "pattern" {
                if let Some(pat) = value.as_str() {
                    if let Some(prob) = pattern_problem(pat) {
                        problems.push(format!("{where_str}: pattern at {at} {prob}"));
                    }
                }
            }
            if key == "patternProperties" {
                if let Some(pat_map) = value.as_object() {
                    for pat_name in pat_map.keys() {
                        if let Some(prob) = pattern_problem(pat_name) {
                            problems.push(format!(
                                "{where_str}: pattern {} at {at} {prob}",
                                py_repr_str(pat_name)
                            ));
                        }
                    }
                }
            }
            if key == "properties" {
                if let Some(prop_map) = value.as_object() {
                    for prop_name in prop_map.keys() {
                        if CITATION_FIELDS.contains(&prop_name.as_str()) {
                            problems.push(format!(
                                "{where_str}: field name {} at {at} carries a citation in the core format; an extension may not declare it (the license gate would not see it)",
                                py_repr_str(prop_name)
                            ));
                        }
                    }
                }
            }

            if SCHEMA_ONE.contains(&key.as_str()) {
                walk(value, &next_trail, where_str, problems);
            } else if SCHEMA_MAP.contains(&key.as_str()) {
                if let Some(sub_map) = value.as_object() {
                    for (sub_name, sub_val) in sub_map {
                        let mut sub_trail = next_trail.clone();
                        sub_trail.push(sub_name.clone());
                        walk(sub_val, &sub_trail, where_str, problems);
                    }
                }
            } else if SCHEMA_LIST.contains(&key.as_str()) {
                if let Some(sub_list) = value.as_array() {
                    for (idx, sub_val) in sub_list.iter().enumerate() {
                        let mut sub_trail = next_trail.clone();
                        sub_trail.push(idx.to_string());
                        walk(sub_val, &sub_trail, where_str, problems);
                    }
                }
            }
        }
    }

    walk(fragment, &[], &where_str, &mut problems);
    problems
}

fn bad_character_in_str(value: &str) -> Option<String> {
    for ch in value.chars() {
        if ch != '\n' && ch != ' ' && is_yaml_refused_char(ch) {
            return Some(char_label(ch));
        }
    }
    if !is_nfc(value) {
        return Some("a string that is not in Unicode NFC form".to_string());
    }
    None
}

fn bad_json_string(node: &Value) -> Option<String> {
    match node {
        Value::String(s) => bad_character_in_str(s).map(|b| format!("a string holding {b}")),
        Value::Object(map) => {
            for (k, v) in map {
                if let Some(b) = bad_character_in_str(k) {
                    return Some(format!("a string holding {b}"));
                }
                if let Some(found) = bad_json_string(v) {
                    return Some(found);
                }
            }
            None
        }
        Value::Array(items) => {
            for v in items {
                if let Some(found) = bad_json_string(v) {
                    return Some(found);
                }
            }
            None
        }
        _ => None,
    }
}

fn check_raw_fragment_file(
    target: &Path,
) -> Result<(String, Value), Result<(usize, usize, String), String>> {
    if bad_file_name(target) {
        let name = target
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        return Err(Ok((
            1,
            1,
            format!(
                "a refused character in the file name: {}",
                visible_name(&name)
            ),
        )));
    }
    let file = File::open(target).map_err(|e| Err(e.to_string()))?;
    let mut raw = Vec::new();
    let cap = (MAX_BYTES as u64).saturating_add(1);
    file.take(cap)
        .read_to_end(&mut raw)
        .map_err(|e| Err(e.to_string()))?;
    if raw.len() > MAX_BYTES {
        return Err(Ok((
            1,
            1,
            format!("file exceeds the {MAX_BYTES}-byte limit"),
        )));
    }
    for bom in [b"\xef\xbb\xbf".as_slice(), b"\xff\xfe", b"\xfe\xff"] {
        if raw.starts_with(bom) {
            return Err(Ok((
                1,
                1,
                "a byte-order mark; save the file as UTF-8 without one".to_string(),
            )));
        }
    }
    let text = match std::str::from_utf8(&raw) {
        Ok(s) => s.to_owned(),
        Err(exc) => {
            let before = std::str::from_utf8(&raw[..exc.valid_up_to()]).unwrap_or("");
            let line = before.bytes().filter(|&b| b == b'\n').count() + 1;
            let last_line = before.rsplit('\n').next().unwrap_or(before);
            let col = last_line.chars().count() + 1;
            return Err(Ok((line, col, format!("bytes that are not UTF-8 ({exc})"))));
        }
    };

    // Parse JSON first (matching `spec.py`: `_strict_json(target)` then `specload.check_text`).
    let parsed = parse_strict_json(&text).map_err(Err)?;

    let mut line = 1usize;
    let mut col = 1usize;
    let mut chars = text.chars().peekable();
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
            return Err(Ok((
                line,
                col,
                "a refused character in the file: a lone CR (use LF or CRLF line endings)"
                    .to_string(),
            )));
        }
        if is_yaml_refused_char(ch) {
            return Err(Ok((
                line,
                col,
                format!("a refused character in the file: {}", char_label(ch)),
            )));
        }
        col += 1;
    }

    Ok((text, parsed))
}

fn lexically_within_root(rel: &str) -> bool {
    let mut depth = 0isize;
    for comp in Path::new(rel).components() {
        match comp {
            Component::Prefix(_) | Component::RootDir => return false,
            Component::ParentDir => {
                depth -= 1;
                if depth < 0 {
                    return false;
                }
            }
            Component::Normal(_) => depth += 1,
            Component::CurDir => {}
        }
    }
    depth > 0
}

/// Loads the `source-observed` extension schema fragment named by a valid `board-specs.yaml`
/// marker (`spec.py:load_extension`).
pub fn load_extension(marker: &Path, data: &Value, findings: &mut Vec<Finding>) -> Option<Value> {
    let exts = data.as_object()?.get("extensions")?.as_array()?;
    if exts.is_empty() {
        return None;
    }
    let rel = exts[0].get("schema")?.as_str()?;
    let marker_str = marker.to_string_lossy().into_owned();
    let parent = marker.parent().unwrap_or_else(|| Path::new("."));

    if !lexically_within_root(rel) {
        findings.push(Finding::error(
            "SCHEMA-EXTENSION-INVALID",
            &marker_str,
            1,
            1,
            format!("extensions: {rel} lies outside the root"),
        ));
        return None;
    }

    let Ok(root_canon) = parent.canonicalize() else {
        findings.push(Finding::error(
            "SCHEMA-EXTENSION-INVALID",
            &marker_str,
            1,
            1,
            format!("extensions: {rel} lies outside the root"),
        ));
        return None;
    };

    let joined = parent.join(rel);
    if joined.is_symlink() {
        if let Ok(target_canon) = joined.canonicalize() {
            if !target_canon.starts_with(&root_canon) || target_canon == root_canon {
                findings.push(Finding::error(
                    "SCHEMA-EXTENSION-INVALID",
                    &marker_str,
                    1,
                    1,
                    format!("extensions: {rel} lies outside the root"),
                ));
                return None;
            }
        } else {
            findings.push(Finding::error(
                "SCHEMA-EXTENSION-INVALID",
                &marker_str,
                1,
                1,
                format!("extensions: {rel} lies outside the root"),
            ));
            return None;
        }
    }

    if let Ok(target_canon) = joined.canonicalize() {
        if !target_canon.starts_with(&root_canon) || target_canon == root_canon {
            findings.push(Finding::error(
                "SCHEMA-EXTENSION-INVALID",
                &marker_str,
                1,
                1,
                format!("extensions: {rel} lies outside the root"),
            ));
            return None;
        }
    }

    let (_, fragment) = match check_raw_fragment_file(&joined) {
        Ok(pair) => pair,
        Err(Ok((line, col, problem))) => {
            findings.push(Finding::error(
                "SCHEMA-EXTENSION-INVALID",
                &marker_str,
                1,
                1,
                format!("extensions: {rel}:{line}:{col}: {problem}"),
            ));
            return None;
        }
        Err(Err(msg)) => {
            findings.push(Finding::error(
                "SCHEMA-EXTENSION-INVALID",
                &marker_str,
                1,
                1,
                format!("extensions: {rel}: {msg}"),
            ));
            return None;
        }
    };

    if let Some(bad) = bad_json_string(&fragment) {
        findings.push(Finding::error(
            "SCHEMA-EXTENSION-INVALID",
            &marker_str,
            1,
            1,
            format!("extensions: {rel}: {bad}"),
        ));
        return None;
    }

    let schemas = load_schemas();
    let reserved = core_fields(&schemas);
    let problems = check_fragment(&fragment, Path::new(rel), &reserved);
    for p in &problems {
        findings.push(Finding::error(
            "SCHEMA-EXTENSION-INVALID",
            &marker_str,
            1,
            1,
            format!("extensions: {p}"),
        ));
    }

    if problems.is_empty() {
        Some(fragment)
    } else {
        None
    }
}

fn build_validator(
    schema: &Value,
    schemas: &BTreeMap<String, Value>,
    extension: Option<&Value>,
) -> Validator {
    let mut opts = jsonschema::options().with_draft(Draft::Draft202012);
    for s in schemas.values() {
        if let Some(id) = s.get("$id").and_then(Value::as_str) {
            if let Ok(res) = Resource::from_contents(s.clone()) {
                opts = opts.with_resource(id.to_string(), res);
            }
        }
    }
    let ext_val = if let Some(ext) = extension {
        let mut obj = ext.as_object().cloned().unwrap_or_default();
        obj.insert("$id".to_string(), Value::String(EXTENSION_URN.to_string()));
        Value::Object(obj)
    } else {
        default_extension_schema()
    };
    if let Ok(ext_res) = Resource::from_contents(ext_val) {
        opts = opts.with_resource(EXTENSION_URN.to_string(), ext_res);
    }
    opts.build(schema)
        .expect("embedded Format 2 schema and validated extension fragment must compile")
}

fn resolve_ref<'a>(
    reference: &str,
    current_root: &'a Value,
    schemas: &'a BTreeMap<String, Value>,
    extension: Option<&'a Value>,
    default_ext: &'a Value,
) -> Option<(&'a Value, &'a Value)> {
    if reference == EXTENSION_URN {
        let ext = extension.unwrap_or(default_ext);
        return Some((ext, ext));
    }
    let (doc, pointer) = match reference.split_once('#') {
        Some((d, p)) => (d, p),
        None => (reference, ""),
    };
    let target_root = if doc.is_empty() {
        current_root
    } else {
        schemas
            .values()
            .find(|s| {
                s.get("$id")
                    .and_then(Value::as_str)
                    .is_some_and(|id| id == doc || id.ends_with(&format!("/{doc}")))
            })
            .unwrap_or(current_root)
    };
    let mut node = target_root;
    for part in pointer.trim_start_matches('/').split('/') {
        if part.is_empty() {
            continue;
        }
        node = match node {
            Value::Object(map) => map.get(part)?,
            Value::Array(arr) => arr.get(part.parse::<usize>().ok()?)?,
            _ => return None,
        };
    }
    Some((target_root, node))
}

/// Walks `schema_path` from `root_schema` (following `$ref` edges) and returns
/// `(active_root_schema, failing_schema_object, comments_along_path)`.
fn locate_schema_node<'a>(
    schema_path: &str,
    root_schema: &'a Value,
    schemas: &'a BTreeMap<String, Value>,
    extension: Option<&'a Value>,
    default_ext: &'a Value,
) -> (&'a Value, Option<&'a Value>, Vec<String>) {
    let parts: Vec<&str> = schema_path
        .trim_start_matches('/')
        .split('/')
        .filter(|s| !s.is_empty())
        .collect();
    if parts.is_empty() {
        return (root_schema, Some(root_schema), Vec::new());
    }
    let parent_parts = &parts[..parts.len() - 1];
    let mut cur_root = root_schema;
    let mut cur_node: Option<&'a Value> = Some(root_schema);
    let mut comments = Vec::new();

    if let Some(msg) = extract_comment_message(root_schema) {
        comments.push(msg);
    }

    for &seg in parent_parts {
        let Some(node) = cur_node else {
            break;
        };
        if seg == "$ref" {
            if let Some(ref_str) = node.get("$ref").and_then(Value::as_str) {
                if let Some((new_root, resolved)) =
                    resolve_ref(ref_str, cur_root, schemas, extension, default_ext)
                {
                    cur_root = new_root;
                    cur_node = Some(resolved);
                    if let Some(msg) = extract_comment_message(resolved) {
                        comments.push(msg);
                    }
                } else {
                    cur_node = None;
                }
            } else {
                cur_node = None;
            }
        } else {
            cur_node = match node {
                Value::Object(map) => map.get(seg),
                Value::Array(arr) => seg.parse::<usize>().ok().and_then(|i| arr.get(i)),
                _ => None,
            };
            if let Some(n) = cur_node {
                if let Some(msg) = extract_comment_message(n) {
                    comments.push(msg);
                }
            }
        }
    }
    (cur_root, cur_node, comments)
}

fn extract_comment_message(schema: &Value) -> Option<String> {
    let comment = schema.as_object()?.get("$comment")?.as_str()?;
    comment.strip_prefix("message: ").map(str::to_owned)
}

fn subschema_is_valid(
    sub: &Value,
    instance: &Value,
    active_root: &Value,
    schemas: &BTreeMap<String, Value>,
    extension: Option<&Value>,
) -> bool {
    let mut schema_to_compile = sub.clone();
    if let Value::Object(ref mut map) = schema_to_compile {
        if !map.contains_key("$id") {
            if let Some(base_id) = active_root.get("$id").and_then(Value::as_str) {
                if let Some((prefix, _)) = base_id.rsplit_once('/') {
                    map.insert(
                        "$id".to_string(),
                        Value::String(format!("{prefix}/__subschema__.json")),
                    );
                }
            }
        }
        if !map.contains_key("$defs") {
            if let Some(defs) = active_root.get("$defs") {
                map.insert("$defs".to_string(), defs.clone());
            }
        }
    }
    let validator = build_validator(&schema_to_compile, schemas, extension);
    validator.is_valid(instance)
}

fn find_custom_message_in_branches(
    error_schema: &Value,
    combinator_key: &str,
    instance: &Value,
    active_root: &Value,
    schemas: &BTreeMap<String, Value>,
    extension: Option<&Value>,
    default_ext: &Value,
) -> Option<String> {
    let branches = error_schema.get(combinator_key)?.as_array()?;
    for branch in branches {
        let (branch_root, branch_node) =
            if let Some(ref_str) = branch.get("$ref").and_then(Value::as_str) {
                resolve_ref(ref_str, active_root, schemas, extension, default_ext)
                    .unwrap_or((active_root, branch))
            } else {
                (active_root, branch)
            };
        if !subschema_is_valid(branch_node, instance, branch_root, schemas, extension) {
            if let Some(msg) = extract_comment_message(branch_node) {
                return Some(msg);
            }
        }
    }
    None
}

fn branch_names(
    schema: &Value,
    instance: &Value,
    active_root: &Value,
    schemas: &BTreeMap<String, Value>,
    extension: Option<&Value>,
    default_ext: &Value,
    depth: usize,
) -> BTreeSet<String> {
    let mut names = BTreeSet::new();
    if depth > 32 {
        return names;
    }
    let Some(obj) = schema.as_object() else {
        return names;
    };
    if let Some(props) = obj.get("properties").and_then(Value::as_object) {
        for k in props.keys() {
            names.insert(k.clone());
        }
    }
    if let Some(all_of) = obj.get("allOf").and_then(Value::as_array) {
        for sub in all_of {
            names.extend(branch_names(
                sub,
                instance,
                active_root,
                schemas,
                extension,
                default_ext,
                depth + 1,
            ));
        }
    }
    for key in ["anyOf", "oneOf"] {
        if let Some(branches) = obj.get(key).and_then(Value::as_array) {
            for sub in branches {
                if subschema_is_valid(sub, instance, active_root, schemas, extension) {
                    names.extend(branch_names(
                        sub,
                        instance,
                        active_root,
                        schemas,
                        extension,
                        default_ext,
                        depth + 1,
                    ));
                }
            }
        }
    }
    if let Some(ref_str) = obj.get("$ref").and_then(Value::as_str) {
        if let Some((new_root, resolved)) =
            resolve_ref(ref_str, active_root, schemas, extension, default_ext)
        {
            names.extend(branch_names(
                resolved,
                instance,
                new_root,
                schemas,
                extension,
                default_ext,
                depth + 1,
            ));
        }
    }
    if let Some(if_schema) = obj.get("if") {
        let branch_key = if subschema_is_valid(if_schema, instance, active_root, schemas, extension)
        {
            "then"
        } else {
            "else"
        };
        if let Some(branch_schema) = obj.get(branch_key) {
            names.extend(branch_names(
                branch_schema,
                instance,
                active_root,
                schemas,
                extension,
                default_ext,
                depth + 1,
            ));
        }
    }
    names
}

fn location_to_segments(loc: &jsonschema::paths::Location) -> Vec<PathSegment> {
    let s = loc.as_str();
    if s.is_empty() {
        return Vec::new();
    }
    s.trim_start_matches('/')
        .split('/')
        .filter(|part| !part.is_empty())
        .map(|part| {
            let unescaped = part.replace("~1", "/").replace("~0", "~");
            if let Ok(idx) = unescaped.parse::<usize>() {
                PathSegment::Index(idx)
            } else {
                PathSegment::Key(unescaped)
            }
        })
        .collect()
}

fn short_message(instance: &Value, raw_message: &str) -> String {
    let shown = py_repr_value(instance);
    let mut message = if shown.len() > 60 && raw_message.starts_with(&shown) {
        format!("the value{}", &raw_message[shown.len()..])
    } else {
        raw_message.to_string()
    };
    if message.len() > 300 {
        let mut trunc = 297;
        while !message.is_char_boundary(trunc) {
            trunc -= 1;
        }
        message = format!("{}...", &message[..trunc]);
    }
    message
}

fn format_error_kind(error: &ValidationError<'_>, error_schema: Option<&Value>) -> String {
    let inst = error.instance.as_ref();
    let shown = py_repr_value(inst);
    let schema_path = error.schema_path.as_str();

    match &error.kind {
        ValidationErrorKind::Required { property } => {
            let prop_str = property
                .as_str()
                .map_or_else(|| py_repr_value(property), py_repr_str);
            if schema_path.contains("/dependentRequired") {
                format!("{prop_str} is a dependency")
            } else {
                format!("{prop_str} is a required property")
            }
        }
        ValidationErrorKind::Pattern { pattern } => {
            format!("{shown} does not match {}", py_repr_str(pattern))
        }
        ValidationErrorKind::Enum { options } => {
            format!("{shown} is not one of {}", py_repr_value(options))
        }
        ValidationErrorKind::Constant { expected_value } => {
            format!("{} was expected", py_repr_value(expected_value))
        }
        ValidationErrorKind::Type { kind } => match kind {
            TypeKind::Single(prim) => {
                let prim_str = prim.to_string();
                if prim_str == "string"
                    && !matches!(inst, Value::String(_) | Value::Object(_) | Value::Array(_))
                {
                    let read_as = match inst {
                        Value::Bool(_) => "a boolean",
                        Value::Number(_) => "an integer",
                        Value::Null => "null",
                        _ => "a value",
                    };
                    return format!(
                        "{shown} was read as {read_as}, expected string; quote it to keep it a string (D6)"
                    );
                }
                format!("{shown} is not of type '{prim_str}'")
            }
            TypeKind::Multiple(bitmap) => {
                if let Some(type_arr) = error_schema
                    .and_then(|s| s.get("type"))
                    .and_then(Value::as_array)
                {
                    let quoted: Vec<String> = type_arr
                        .iter()
                        .filter_map(Value::as_str)
                        .map(py_repr_str)
                        .collect();
                    if !quoted.is_empty() {
                        return format!("{shown} is not of type {}", quoted.join(", "));
                    }
                }
                let mut names = Vec::new();
                for p in *bitmap {
                    names.push(format!("'{p}'"));
                }
                format!("{shown} is not of type {}", names.join(", "))
            }
        },
        ValidationErrorKind::MinItems { limit }
        | ValidationErrorKind::MinProperties { limit }
        | ValidationErrorKind::MinLength { limit } => {
            if *limit == 1 {
                format!("{shown} should be non-empty")
            } else {
                format!("{shown} is too short")
            }
        }
        ValidationErrorKind::MaxItems { limit }
        | ValidationErrorKind::MaxProperties { limit }
        | ValidationErrorKind::MaxLength { limit } => {
            format!("{shown} is too long (at most {limit} items)")
        }
        ValidationErrorKind::AdditionalItems { limit } => {
            format!("Expected at most {limit} items ( is too long)")
        }
        ValidationErrorKind::FalseSchema => {
            if schema_path.ends_with("/items") {
                if let Some(prefix_len) = error_schema
                    .and_then(|s| s.get("prefixItems"))
                    .and_then(Value::as_array)
                    .map(Vec::len)
                {
                    return format!("Expected at most {prefix_len} items ( is too long)");
                }
            }
            format!("{shown} should not be valid")
        }
        ValidationErrorKind::Not { .. } => {
            format!("{shown} should not be valid")
        }
        ValidationErrorKind::OneOfMultipleValid => {
            format!("{shown} is valid under each of the given schemas")
        }
        ValidationErrorKind::OneOfNotValid | ValidationErrorKind::AnyOf => {
            format!("{shown} is not valid under any of the given schemas")
        }
        ValidationErrorKind::UniqueItems => {
            format!("{shown} has non-unique elements")
        }
        ValidationErrorKind::Minimum { limit } => {
            format!("{shown} is less than the minimum of {limit}")
        }
        ValidationErrorKind::Maximum { limit } => {
            format!("{shown} is greater than the maximum of {limit}")
        }
        ValidationErrorKind::ExclusiveMinimum { limit } => {
            format!("{shown} is less than or equal to the minimum of {limit}")
        }
        ValidationErrorKind::ExclusiveMaximum { limit } => {
            format!("{shown} is greater than or equal to the maximum of {limit}")
        }
        ValidationErrorKind::Contains => {
            format!("{shown} does not contain items matching the given schema")
        }
        _ => error.to_string(),
    }
}

fn classify_schema_finding_code(message: &str) -> &'static str {
    if message.starts_with("extensions:") {
        "SCHEMA-EXTENSION-INVALID"
    } else if message.contains("unknown key ") && message.ends_with(" here") {
        "SCHEMA-UNKNOWN-KEY"
    } else if message.contains("is a required property") || message.contains("is a dependency") {
        "SCHEMA-REQUIRED-PROPERTY"
    } else if message.contains("is not one of [") || message.contains("was expected") {
        "SCHEMA-ENUM-OR-CONST"
    } else if message.contains("was read as a boolean")
        || message.contains("was read as an integer")
    {
        "LOAD-AMBIGUOUS-SCALAR"
    } else if message.contains("*.facts.yaml") {
        "SPEC-FACTS-KIND-MISMATCH"
    } else {
        "SCHEMA-PATTERN-OR-TYPE"
    }
}

/// Evaluates a compiled JSON Schema against `data` and returns line/column-anchored [`Finding`]s
/// (`spec.py:schema_findings`).
#[must_use]
pub fn schema_findings(
    kind: SchemaKind,
    schemas: &BTreeMap<String, Value>,
    extension: Option<&Value>,
    data: &Value,
    loaded: &Loaded,
    path: &Path,
) -> Vec<Finding> {
    let root_schema = &schemas[kind.as_str()];
    let default_ext = default_extension_schema();
    let effective_ext = if kind == SchemaKind::Root {
        None
    } else {
        extension
    };
    let validator = build_validator(root_schema, schemas, effective_ext);
    let errors: Vec<ValidationError<'_>> = validator.iter_errors(data).collect();

    let is_unknown_kind = |k: &ValidationErrorKind| {
        matches!(
            k,
            ValidationErrorKind::UnevaluatedProperties { .. }
                | ValidationErrorKind::AdditionalProperties { .. }
        )
    };

    let others: Vec<(Vec<PathSegment>, bool)> = errors
        .iter()
        .map(|e| {
            (
                location_to_segments(&e.instance_path),
                is_unknown_kind(&e.kind),
            )
        })
        .collect();

    let path_str = path.to_string_lossy().into_owned();
    let mut out = Vec::new();

    for error in &errors {
        let mut at = location_to_segments(&error.instance_path);

        // `propertyNames` errors: `error.kind` is `PropertyNames { error: inner }`.
        if let ValidationErrorKind::PropertyNames { error: inner } = &error.kind {
            if let Some(key) = inner.instance.as_str() {
                let m: Mark = loaded.mark(&at, Some(key));
                let inner_schema_path = format!(
                    "{}/propertyNames/{}",
                    error
                        .schema_path
                        .as_str()
                        .trim_end_matches("/propertyNames"),
                    inner.schema_path.as_str().trim_start_matches('/')
                );
                let (_, inner_schema_node, inner_comments) = locate_schema_node(
                    &inner_schema_path,
                    root_schema,
                    schemas,
                    effective_ext,
                    &default_ext,
                );
                let custom = inner_comments.last().cloned();
                let raw_msg = custom.unwrap_or_else(|| {
                    let formatted = format_error_kind(inner, inner_schema_node);
                    short_message(inner.instance.as_ref(), &formatted)
                });
                let full_msg =
                    format!("{}: key {}: {raw_msg}", format_where(&at), py_repr_str(key));
                let code = classify_schema_finding_code(&full_msg);
                out.push(Finding::error(code, &path_str, m.line, m.column, full_msg));
                continue;
            }
        }

        // `additionalProperties` / `unevaluatedProperties`: apply `_branch_names` cascade filter.
        match &error.kind {
            ValidationErrorKind::UnevaluatedProperties { unexpected }
            | ValidationErrorKind::AdditionalProperties { unexpected } => {
                let is_uneval = matches!(
                    error.kind,
                    ValidationErrorKind::UnevaluatedProperties { .. }
                );
                let shadowed = others.iter().any(|(p, other_is_unknown)| {
                    if p == &at && *other_is_unknown {
                        return false;
                    }
                    p.starts_with(&at) && (p.len() > at.len() || !*other_is_unknown)
                });

                let (active_root, error_schema_opt, _) = locate_schema_node(
                    error.schema_path.as_str(),
                    root_schema,
                    schemas,
                    effective_ext,
                    &default_ext,
                );

                let own = if is_uneval && shadowed {
                    if let Some(err_schema) = error_schema_opt {
                        branch_names(
                            err_schema,
                            error.instance.as_ref(),
                            active_root,
                            schemas,
                            effective_ext,
                            &default_ext,
                            0,
                        )
                    } else {
                        BTreeSet::new()
                    }
                } else {
                    BTreeSet::new()
                };

                // Preserve key order from the object instance.
                let unexpected_set: BTreeSet<&str> =
                    unexpected.iter().map(String::as_str).collect();
                if let Some(inst_obj) = error.instance.as_object() {
                    for key in inst_obj.keys() {
                        if !unexpected_set.contains(key.as_str()) {
                            continue;
                        }
                        if own.contains(key) {
                            continue;
                        }
                        let m = loaded.mark(&at, Some(key));
                        let mut key_path = at.clone();
                        key_path.push(PathSegment::Key(key.clone()));
                        let full_msg = format!(
                            "{}: unknown key {} here",
                            format_where(&key_path),
                            py_repr_str(key)
                        );
                        out.push(Finding::error(
                            "SCHEMA-UNKNOWN-KEY",
                            &path_str,
                            m.line,
                            m.column,
                            full_msg,
                        ));
                    }
                }
                continue;
            }
            _ => {}
        }

        let (active_root, error_schema_opt, comments) = locate_schema_node(
            error.schema_path.as_str(),
            root_schema,
            schemas,
            effective_ext,
            &default_ext,
        );

        // If `items: false` with `prefixItems` failed on element `idx >= prefixItems.len()`,
        // anchor the error on the array rather than the element, matching Python `jsonschema`.
        if matches!(error.kind, ValidationErrorKind::FalseSchema)
            && error.schema_path.as_str().ends_with("/items")
            && error_schema_opt
                .and_then(|s| s.get("prefixItems"))
                .is_some()
            && matches!(at.last(), Some(PathSegment::Index(_)))
        {
            at.pop();
        }

        let mark = loaded.mark(&at, None);

        let mut custom_msg = error_schema_opt.and_then(extract_comment_message);
        if custom_msg.is_none() {
            custom_msg = comments.last().cloned();
        }
        if custom_msg.is_none() {
            if let Some(err_schema) = error_schema_opt {
                match &error.kind {
                    ValidationErrorKind::AnyOf => {
                        custom_msg = find_custom_message_in_branches(
                            err_schema,
                            "anyOf",
                            error.instance.as_ref(),
                            active_root,
                            schemas,
                            effective_ext,
                            &default_ext,
                        );
                    }
                    ValidationErrorKind::OneOfNotValid => {
                        custom_msg = find_custom_message_in_branches(
                            err_schema,
                            "oneOf",
                            error.instance.as_ref(),
                            active_root,
                            schemas,
                            effective_ext,
                            &default_ext,
                        );
                    }
                    _ => {}
                }
            }
        }

        let message = custom_msg.unwrap_or_else(|| {
            let formatted = format_error_kind(error, error_schema_opt);
            short_message(error.instance.as_ref(), &formatted)
        });

        let full_msg = format!("{}: {message}", format_where(&at));
        let code = classify_schema_finding_code(&full_msg);
        out.push(Finding::error(
            code,
            &path_str,
            mark.line,
            mark.column,
            full_msg,
        ));
    }

    out
}

/// Validates a YAML file on disk against its Format 2 JSON Schema (`spec.py:validate_file`).
pub fn validate_file(
    path: &Path,
    schemas: &BTreeMap<String, Value>,
    extension: Option<&Value>,
    findings: &mut Vec<Finding>,
) -> Result<(bool, SchemaKind, Option<Loaded>), String> {
    let kind = schema_kind(path)?;
    let loaded = load_file(path);
    Ok(validate_loaded(
        path, kind, loaded, schemas, extension, findings,
    ))
}

/// Validates an in-memory YAML string against `path`'s Format 2 JSON Schema (`spec.py:validate_file(..., raw=...)`).
pub fn validate_text(
    path: &Path,
    raw: &str,
    schemas: &BTreeMap<String, Value>,
    extension: Option<&Value>,
    findings: &mut Vec<Finding>,
) -> Result<(bool, SchemaKind, Option<Loaded>), String> {
    let kind = schema_kind(path)?;
    let loaded = load_text(raw, path);
    Ok(validate_loaded(
        path, kind, loaded, schemas, extension, findings,
    ))
}

fn validate_loaded(
    path: &Path,
    kind: SchemaKind,
    loaded: Loaded,
    schemas: &BTreeMap<String, Value>,
    extension: Option<&Value>,
    findings: &mut Vec<Finding>,
) -> (bool, SchemaKind, Option<Loaded>) {
    let before = findings.len();
    if !loaded.ok() {
        for err in &loaded.errors {
            let mut f = err.to_finding();
            if f.code == "YAML-IO" && f.message.starts_with("cannot read file:") {
                f.message = f
                    .message
                    .replacen("cannot read file:", "cannot read the file:", 1);
            }
            findings.push(f);
        }
        return (false, kind, None);
    }

    let Some(ref data) = loaded.data else {
        return (false, kind, None);
    };

    let effective_ext = if kind == SchemaKind::Root {
        None
    } else {
        extension
    };
    findings.extend(schema_findings(
        kind,
        schemas,
        effective_ext,
        data,
        &loaded,
        path,
    ));

    if kind == SchemaKind::Spec {
        if let Some(doc_kind) = data.get("kind").and_then(Value::as_str) {
            let is_facts_name = path
                .file_name()
                .and_then(|s| s.to_str())
                .is_some_and(|n| n.ends_with(".facts.yaml"));
            if is_facts_name != (doc_kind == "facts") {
                let m = loaded.mark(&[PathSegment::Key("kind".to_string())], None);
                let want = if is_facts_name {
                    "a *.facts.yaml file holds kind: facts"
                } else {
                    "kind: facts belongs in a *.facts.yaml file"
                };
                findings.push(Finding::error(
                    "SPEC-FACTS-KIND-MISMATCH",
                    path.to_string_lossy().into_owned(),
                    m.line,
                    m.column,
                    format!("kind: {want}"),
                ));
            }
        }
    }

    if kind == SchemaKind::Root && findings.len() == before {
        load_extension(path, data, findings);
    }

    (findings.len() == before, kind, Some(loaded))
}

/// Validates `<root>/board-specs.yaml` and loads any `source-observed` extension schema fragment
/// it declares (`spec.py:read_root`).
pub fn read_root(
    root: &Path,
    schemas: &BTreeMap<String, Value>,
    findings: &mut Vec<Finding>,
) -> Result<Option<Value>, String> {
    if !root.is_dir() {
        return Err(format!("--root {}: not a directory", root.display()));
    }
    let marker = root.join(MARKER);
    if !marker.is_file() {
        return Err(format!("--root {}: no {MARKER} there", root.display()));
    }
    let (ok, _, loaded_opt) = validate_file(&marker, schemas, None, findings)?;
    if !ok {
        return Ok(None);
    }
    let Some(loaded) = loaded_opt else {
        return Ok(None);
    };
    let Some(ref data) = loaded.data else {
        return Ok(None);
    };
    let mut dummy = Vec::new();
    Ok(load_extension(&marker, data, &mut dummy))
}

/// Deduplicates and sorts findings by `(path, line, column, message)` (`spec.py:cmd_validate`).
#[must_use]
pub fn deduplicate_and_sort_findings(findings: Vec<Finding>) -> Vec<Finding> {
    let mut map: BTreeMap<(String, usize, usize, String), Finding> = BTreeMap::new();
    for f in findings {
        let key = (f.path.clone(), f.line, f.col, f.message.clone());
        map.entry(key).or_insert(f);
    }
    map.into_values().collect()
}

fn emit_validate_usage_error(
    msg: &str,
    json_mode: bool,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    if json_mode {
        let env = DiagnosticEnvelope::usage_error("CLI-USAGE", msg).with_field("files", json!([]));
        let _ = writeln!(stdout, "{}", env.to_json_string());
    } else {
        let _ = writeln!(stderr, "{}", visible_name(&format!("usage error: {msg}")));
    }
    EXIT_USAGE_ERROR
}

/// Executes `driver-lab validate` (`spec.py:cmd_validate` + `BF-IMX-18`).
pub fn run_validate(
    args: &ValidateArgs,
    json_mode: bool,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    if args.targets.is_empty() {
        return emit_validate_usage_error(
            "validate requires at least one target file",
            json_mode,
            stdout,
            stderr,
        );
    }

    for p in &args.targets {
        if !p.is_file() {
            return emit_validate_usage_error(
                &format!("{}: no such file", p.display()),
                json_mode,
                stdout,
                stderr,
            );
        }
        if let Err(msg) = schema_kind(p) {
            return emit_validate_usage_error(&msg, json_mode, stdout, stderr);
        }
    }

    if let Some(ref root) = args.root {
        if !root.is_dir() {
            return emit_validate_usage_error(
                &format!("--root {}: not a directory", root.display()),
                json_mode,
                stdout,
                stderr,
            );
        }
    }
    for ctx_root in &args.context_roots {
        if !ctx_root.is_dir() {
            return emit_validate_usage_error(
                &format!("--context-root {}: not a directory", ctx_root.display()),
                json_mode,
                stdout,
                stderr,
            );
        }
    }

    let schemas = load_schemas();
    let mut findings: Vec<Finding> = Vec::new();
    let extension = if let Some(ref root) = args.root {
        match read_root(root, &schemas, &mut findings) {
            Ok(ext) => ext,
            Err(msg) => return emit_validate_usage_error(&msg, json_mode, stdout, stderr),
        }
    } else {
        None
    };

    let mut files: Vec<ValidatedFileEntry> = Vec::with_capacity(args.targets.len());
    for p in &args.targets {
        let (ok, kind, _) = validate_file(p, &schemas, extension.as_ref(), &mut findings)
            .expect("schema_kind was already checked above");
        files.push(ValidatedFileEntry {
            path: p.to_string_lossy().into_owned(),
            schema: kind.as_str().to_string(),
            valid: ok,
        });
    }

    let ordered = deduplicate_and_sort_findings(findings);
    let ok = ordered.is_empty();
    let code = if ok { EXIT_OK } else { EXIT_DOMAIN_FAILURE };

    if json_mode {
        let env = DiagnosticEnvelope::from_findings(ordered).with_field(
            "files",
            serde_json::to_value(&files).unwrap_or(Value::Array(Vec::new())),
        );
        let _ = writeln!(stdout, "{}", env.to_json_string());
    } else {
        for f in &ordered {
            let _ = writeln!(stdout, "{}", f.format_without_level());
        }
        let bad = files.iter().filter(|f| !f.valid).count();
        let _ = writeln!(
            stdout,
            "{} file(s), {bad} invalid, {} finding(s)",
            files.len(),
            ordered.len()
        );
    }

    code
}
