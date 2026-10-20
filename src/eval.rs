// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Hardware specification code and fact evaluation harness (`driver-lab eval`).
//!
//! Replaces `skills/spec-eval/scripts/speceval.py`, `grade_code.py`, and
//! `rust_check.py`, and implements `ENV-5` candidate test binary containment
//! using `bwrap` on Linux and `sandbox-exec` on macOS.

use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::fmt;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::OnceLock;
use std::thread;
use std::time::{Duration, Instant};

use clap::{Args, Parser, Subcommand};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

use crate::sandbox::ScratchResolver;

/// Marker line separating the prepended hardware evaluation prelude from its
/// internal self-test module.
pub const PRELUDE_MARKER: &str = "// ---- end of prelude: test module below is not prepended ----";

/// Path of the generated abstention probe test inside a candidate test crate.
pub const PROBE_PATH: &str = "__eval_probe::__eval_probe_spec_gap";

/// Standard `rustc` flags used to compile candidate answers and test harnesses.
pub const RUSTC_FLAGS: &[&str] = &[
    "--edition",
    "2021",
    "-A",
    "dead_code",
    "-A",
    "unused_variables",
    "-A",
    "unused_imports",
];

/// Timeout in seconds for `rustc` invocations (`COMPILE_TIMEOUT` in `speceval.py`).
pub const COMPILE_TIMEOUT_SECS: u64 = 180;

/// Canonical outcomes in `grade_code.py` sweep reports.
pub const OUTCOMES: &[&str] = &[
    "correct",
    "abstain-ok",
    "abstain-wrong",
    "test-fail",
    "compile-error",
];

/// Canonical and legacy field name pairs accepted in question bank items.
pub const ALIAS_PAIRS: &[(&str, &str)] = &[
    ("fn_signature", "signature"),
    ("reference_rust", "ref_rs"),
    ("trap_rust", "trap_rs"),
    ("test_harness", "tests_rs"),
    ("preamble", "preamble_rs"),
    ("chapter_or_block", "domain"),
    ("doc_pages_primary", "pdf_pages"),
    ("doc_pages_secondary", "pdf_pages_secondary"),
];

/// Keys that must never appear in contestant-facing preamble exports.
pub const FORBIDDEN_EXPORT_KEYS: &[&str] = &[
    "reference_rust",
    "ref_rs",
    "trap_rust",
    "trap_rs",
    "test_harness",
    "tests_rs",
    "trap_description",
    "abstain_probe",
    "spec_facts",
    "doc_pages_primary",
    "pdf_pages",
    "doc_pages_secondary",
    "pdf_pages_secondary",
];

/// Embedded default `hw_eval_prelude.rs` source.
pub const DEFAULT_PRELUDE_RS: &str = include_str!("../skills/spec-eval/rust/hw_eval_prelude.rs");

/// Embedded default `code_bank.schema.json` schema.
pub const DEFAULT_SCHEMA_JSON: &str =
    include_str!("../skills/spec-eval/schema/code_bank.schema.json");

const SCHEMA_IGNORED: &[&str] = &[
    "$schema",
    "$id",
    "$comment",
    "title",
    "description",
    "$defs",
    "default",
];

const SCHEMA_IMPLEMENTED: &[&str] = &[
    "type",
    "enum",
    "const",
    "required",
    "properties",
    "additionalProperties",
    "items",
    "anyOf",
    "oneOf",
    "allOf",
    "minLength",
    "minItems",
    "$ref",
];

/// Error raised when a question bank, schema, sweep input, or sandbox environment fails.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvalError(pub String);

impl EvalError {
    pub fn new(msg: impl Into<String>) -> Self {
        Self(msg.into())
    }
}

impl fmt::Display for EvalError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for EvalError {}

/// Result of compiling and executing a Rust test program (`compile_and_run_tests` in `speceval.py`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct TestRun {
    pub compiled: bool,
    pub diagnostics: String,
    pub exit_code: Option<i32>,
    pub timed_out: bool,
    pub stdout: String,
    pub results: BTreeMap<String, String>,
    pub declared: usize,
    pub complete: bool,
}

/// Graded outcome of a single fact/citation evaluation record (`grade-facts`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GradedFactRecord {
    pub id: String,
    pub model: String,
    pub arm: String,
    pub stratum: String,
    pub abstained: bool,
    pub passed: bool,
    pub outcome: String,
    pub expected_facts: usize,
    pub matched_facts: usize,
    pub fact_recall: f64,
    pub page_hit: bool,
}

fn alias_map() -> &'static BTreeMap<&'static str, &'static str> {
    static MAP: OnceLock<BTreeMap<&'static str, &'static str>> = OnceLock::new();
    MAP.get_or_init(|| ALIAS_PAIRS.iter().copied().collect())
}

/// Return the canonical or legacy value for `canonical` on a bank item object.
pub fn get_field<'a>(item: &'a Value, canonical: &str) -> Option<&'a Value> {
    let obj = item.as_object()?;
    if let Some(v) = obj.get(canonical) {
        return Some(v);
    }
    if let Some(&legacy) = alias_map().get(canonical) {
        if let Some(v) = obj.get(legacy) {
            return Some(v);
        }
    }
    None
}

/// Return the string value for `canonical` (or its legacy alias), or `""` if absent.
pub fn get_field_str<'a>(item: &'a Value, canonical: &str) -> &'a str {
    get_field(item, canonical)
        .and_then(Value::as_str)
        .unwrap_or("")
}

// ============================================================================
// 1. Bank Loading, Normalization, and Schema Validation (`speceval.py`)
// ============================================================================

/// Read a bank file as parsed JSON without interpreting it (`speceval.load_document`).
pub fn load_document(path: &Path) -> Result<Value, EvalError> {
    let text =
        fs::read_to_string(path).map_err(|e| EvalError::new(format!("{}: {e}", path.display())))?;
    serde_json::from_str(&text).map_err(|e| EvalError::new(format!("{}: {e}", path.display())))
}

/// Return the item list of a bank document (an array, or an object's `items`), or `[]` if neither.
pub fn items_of(document: &Value) -> Vec<Value> {
    if let Some(arr) = document.as_array() {
        return arr.clone();
    }
    if let Some(arr) = document
        .as_object()
        .and_then(|o| o.get("items"))
        .and_then(Value::as_array)
    {
        return arr.clone();
    }
    Vec::new()
}

/// Read a bank file: a JSON array of items, or an object holding them under `items`.
pub fn load_bank(path: &Path) -> Result<Vec<Value>, EvalError> {
    let doc = load_document(path)?;
    let is_valid_shape = doc.is_array()
        || doc
            .as_object()
            .and_then(|o| o.get("items"))
            .map(Value::is_array)
            .unwrap_or(false);
    if !is_valid_shape {
        return Err(EvalError::new(format!(
            "{}: not an array of items or an object with an items array",
            path.display()
        )));
    }
    Ok(items_of(&doc))
}

/// Load a JSON Schema from `path` or return the embedded `code_bank.schema.json`.
pub fn load_schema(path: Option<&Path>) -> Result<Value, EvalError> {
    match path {
        Some(p) => load_document(p),
        None => serde_json::from_str(DEFAULT_SCHEMA_JSON)
            .map_err(|e| EvalError::new(format!("invalid embedded schema: {e}"))),
    }
}

fn type_ok(value: &Value, name: &str) -> Result<bool, EvalError> {
    match name {
        "string" => Ok(value.is_string()),
        "integer" => Ok(value.is_i64() || value.is_u64()),
        "number" => Ok(value.is_number()),
        "boolean" => Ok(value.is_boolean()),
        "array" => Ok(value.is_array()),
        "object" => Ok(value.is_object()),
        "null" => Ok(value.is_null()),
        other => Err(EvalError::new(format!(
            "schema type not implemented: {other}"
        ))),
    }
}

fn py_type_name(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) => {
            if n.is_i64() || n.is_u64() {
                "int"
            } else {
                "float"
            }
        }
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

fn resolve_ref<'a>(ref_str: &str, root: &'a Value) -> Result<&'a Value, EvalError> {
    let Some(rest) = ref_str.strip_prefix("#/") else {
        return Err(EvalError::new(format!(
            "only local $ref values are implemented: {ref_str}"
        )));
    };
    let mut node = root;
    for part in rest.split('/') {
        let key = part.replace("~1", "/").replace("~0", "~");
        node = node
            .as_object()
            .and_then(|o| o.get(&key))
            .ok_or_else(|| EvalError::new(format!("unresolved $ref: {ref_str}")))?;
    }
    Ok(node)
}

/// Fail-closed upfront walk over `node` rejecting any unimplemented JSON Schema keywords.
pub fn check_schema(node: &Value, path: &str) -> Result<(), EvalError> {
    if node == &Value::Bool(true) {
        return Ok(());
    }
    let Some(obj) = node.as_object() else {
        return Err(EvalError::new(format!(
            "schema node is not an object at {path}"
        )));
    };
    for (key, value) in obj {
        if !SCHEMA_IMPLEMENTED.contains(&key.as_str()) && !SCHEMA_IGNORED.contains(&key.as_str()) {
            return Err(EvalError::new(format!(
                "schema keyword not implemented by speceval.validate: {key}"
            )));
        }
        if key == "additionalProperties" && !value.is_boolean() {
            return Err(EvalError::new(
                "schema keyword not implemented by speceval.validate: additionalProperties with a schema value",
            ));
        }
        if key == "properties" || key == "$defs" {
            if let Some(sub_map) = value.as_object() {
                for (name, sub) in sub_map {
                    check_schema(sub, &format!("{path}/{key}/{name}"))?;
                }
            }
        } else if key == "items" {
            check_schema(value, &format!("{path}/items"))?;
        } else if key == "anyOf" || key == "oneOf" || key == "allOf" {
            if let Some(arr) = value.as_array() {
                for (i, sub) in arr.iter().enumerate() {
                    check_schema(sub, &format!("{path}/{key}/{i}"))?;
                }
            }
        }
    }
    Ok(())
}

fn check_instance(
    inst: &Value,
    schema: &Value,
    root: &Value,
    path: &str,
) -> Result<Vec<String>, EvalError> {
    if schema == &Value::Bool(true) {
        return Ok(Vec::new());
    }
    let Some(schema_obj) = schema.as_object() else {
        return Err(EvalError::new(format!(
            "schema node is not an object at {path}: {schema:?}"
        )));
    };
    if schema_obj.is_empty() {
        return Ok(Vec::new());
    }
    for key in schema_obj.keys() {
        if !SCHEMA_IMPLEMENTED.contains(&key.as_str()) && !SCHEMA_IGNORED.contains(&key.as_str()) {
            return Err(EvalError::new(format!(
                "schema keyword not implemented by speceval.validate: {key}"
            )));
        }
    }

    let mut errors = Vec::new();
    if let Some(ref_str) = schema_obj.get("$ref").and_then(Value::as_str) {
        let resolved = resolve_ref(ref_str, root)?;
        errors.extend(check_instance(inst, resolved, root, path)?);
    }

    if let Some(type_val) = schema_obj.get("type") {
        let names: Vec<&str> = if let Some(s) = type_val.as_str() {
            vec![s]
        } else if let Some(arr) = type_val.as_array() {
            arr.iter().filter_map(Value::as_str).collect()
        } else {
            Vec::new()
        };
        let mut matched_type = false;
        for n in &names {
            if type_ok(inst, n)? {
                matched_type = true;
                break;
            }
        }
        if !matched_type {
            errors.push(format!(
                "{path}: expected type {}, got {}",
                names.join("|"),
                py_type_name(inst)
            ));
            return Ok(errors);
        }
    }

    if let Some(enum_arr) = schema_obj.get("enum").and_then(Value::as_array) {
        if !enum_arr.iter().any(|v| v == inst) {
            errors.push(format!("{path}: {inst} is not one of {enum_arr:?}"));
        }
    }

    if let Some(const_val) = schema_obj.get("const") {
        if inst != const_val {
            errors.push(format!("{path}: expected {const_val}"));
        }
    }

    if let Some(s) = inst.as_str() {
        if let Some(min_len) = schema_obj.get("minLength").and_then(Value::as_u64) {
            if (s.chars().count() as u64) < min_len {
                errors.push(format!("{path}: shorter than {min_len} characters"));
            }
        }
    }

    if let Some(arr) = inst.as_array() {
        if let Some(min_items) = schema_obj.get("minItems").and_then(Value::as_u64) {
            if (arr.len() as u64) < min_items {
                errors.push(format!("{path}: fewer than {min_items} items"));
            }
        }
        if let Some(items_schema) = schema_obj.get("items") {
            for (i, elem) in arr.iter().enumerate() {
                errors.extend(check_instance(
                    elem,
                    items_schema,
                    root,
                    &format!("{path}[{i}]"),
                )?);
            }
        }
    }

    if let Some(obj) = inst.as_object() {
        if let Some(req) = schema_obj.get("required").and_then(Value::as_array) {
            for name in req.iter().filter_map(Value::as_str) {
                if !obj.contains_key(name) {
                    errors.push(format!("{path}: missing required field {name:?}"));
                }
            }
        }
        let props = schema_obj.get("properties").and_then(Value::as_object);
        if let Some(p_map) = props {
            for (name, sub) in p_map {
                if let Some(val) = obj.get(name) {
                    errors.extend(check_instance(val, sub, root, &format!("{path}.{name}"))?);
                }
            }
        }
        let extra = schema_obj.get("additionalProperties");
        if let Some(extra_val) = extra {
            let Some(extra_bool) = extra_val.as_bool() else {
                return Err(EvalError::new(
                    "schema keyword not implemented by speceval.validate: additionalProperties with a schema value",
                ));
            };
            if !extra_bool {
                for name in obj.keys() {
                    let known = props.map(|p| p.contains_key(name)).unwrap_or(false);
                    if !known {
                        errors.push(format!("{path}: unknown field {name:?}"));
                    }
                }
            }
        }
    }

    if let Some(all_of) = schema_obj.get("allOf").and_then(Value::as_array) {
        for sub in all_of {
            errors.extend(check_instance(inst, sub, root, path)?);
        }
    }

    if let Some(any_of) = schema_obj.get("anyOf").and_then(Value::as_array) {
        let mut results = Vec::with_capacity(any_of.len());
        for sub in any_of {
            results.push(check_instance(inst, sub, root, path)?);
        }
        if !results.iter().any(Vec::is_empty) {
            let detail: Vec<String> = results
                .into_iter()
                .filter_map(|mut r| {
                    if r.is_empty() {
                        None
                    } else {
                        Some(r.swap_remove(0))
                    }
                })
                .collect();
            errors.push(format!(
                "{path}: matches none of the allowed forms ({})",
                detail.join("; ")
            ));
        }
    }

    if let Some(one_of) = schema_obj.get("oneOf").and_then(Value::as_array) {
        let mut matches = 0usize;
        for sub in one_of {
            if check_instance(inst, sub, root, path)?.is_empty() {
                matches += 1;
            }
        }
        if matches != 1 {
            errors.push(format!(
                "{path}: matches {matches} of the oneOf forms, expected exactly 1"
            ));
        }
    }

    Ok(errors)
}

/// Validate `instance` against `schema` (`speceval.validate`).
///
/// Returns `Ok(Vec<String>)` containing any validation findings (empty when valid), or
/// `Err(EvalError)` if `schema` itself uses unsupported keywords.
pub fn validate(instance: &Value, schema: &Value) -> Result<Vec<String>, EvalError> {
    check_schema(schema, "#")?;
    check_instance(instance, schema, schema, "$")
}

/// Check semantic invariants on bank items (`speceval.check_bank`):
/// duplicate IDs, both names of an alias pair, `{` in `fn_signature`, and
/// `out-of-spec` without `abstain_probe`.
pub fn check_bank(items: &[Value]) -> Vec<String> {
    let mut errors = Vec::new();
    let mut seen = BTreeSet::new();
    for (i, item) in items.iter().enumerate() {
        let Some(obj) = item.as_object() else {
            continue;
        };
        let item_id = obj.get("id").and_then(Value::as_str);
        let label = item_id
            .map(ToString::to_string)
            .unwrap_or_else(|| format!("#{i}"));
        if let Some(id_str) = item_id {
            if seen.contains(id_str) {
                errors.push(format!("{label}: duplicate id"));
            }
            seen.insert(id_str.to_string());
        }
        for &(first, second) in ALIAS_PAIRS {
            if obj.contains_key(first) && obj.contains_key(second) {
                errors.push(format!(
                    "{label}: carries both '{first}' and '{second}'; use one"
                ));
            }
        }
        let signature = get_field_str(item, "fn_signature");
        if signature.contains('{') {
            errors.push(format!(
                "{label}: fn_signature must be a header only; it holds a '{{'"
            ));
        }
        let stratum = obj.get("stratum").and_then(Value::as_str).unwrap_or("");
        let probe = obj
            .get("abstain_probe")
            .and_then(Value::as_str)
            .unwrap_or("");
        if stratum == "out-of-spec" && probe.is_empty() {
            errors.push(format!(
                "{label}: an out-of-spec item needs an abstain_probe"
            ));
        }
    }
    errors
}

/// Return schema errors for the whole document followed by semantic checks on its items
/// (`speceval.bank_findings`).
pub fn bank_findings(document: &Value, schema: &Value) -> Result<Vec<String>, EvalError> {
    let mut errs = validate(document, schema)?;
    errs.extend(check_bank(&items_of(document)));
    Ok(errs)
}

/// Normalize an item with canonical keys (see `ALIAS_PAIRS`) and defaults filled in
/// (`speceval.normalize`).
pub fn normalize(item: &Value) -> Value {
    let Some(orig) = item.as_object() else {
        return item.clone();
    };
    let mut out = orig.clone();
    for &(first, second) in ALIAS_PAIRS {
        if let Some(val) = out.remove(second) {
            out.entry(first.to_string()).or_insert(val);
        }
    }
    for key in [
        "fn_signature",
        "reference_rust",
        "trap_rust",
        "test_harness",
        "preamble",
    ] {
        if !out.contains_key(key) {
            out.insert(key.to_string(), Value::String(String::new()));
        }
    }
    let use_hw = out
        .get("use_hw_prelude")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    out.insert("use_hw_prelude".to_string(), Value::Bool(use_hw));

    if let Some(tier_str) = out.get("tier").and_then(Value::as_str) {
        if let Ok(parsed) = tier_str.trim_start_matches("tier").parse::<i64>() {
            out.insert("tier".to_string(), json!(parsed));
        }
    }

    for key in ["doc_pages_primary", "doc_pages_secondary"] {
        if !out.contains_key(key) {
            out.insert(key.to_string(), Value::Array(Vec::new()));
        }
    }

    Value::Object(out)
}

// ============================================================================
// 2. Prelude, Item Preamble, and Signature Stub (`speceval.py`)
// ============================================================================

/// Return the text before `PRELUDE_MARKER` of the prelude file (`speceval.read_prelude`).
pub fn read_prelude(path: Option<&Path>) -> Result<String, EvalError> {
    let (label, text) = match path {
        Some(p) => {
            let content = fs::read_to_string(p)
                .map_err(|e| EvalError::new(format!("{}: {e}", p.display())))?;
            (p.display().to_string(), content)
        }
        None => (
            "<embedded hw_eval_prelude.rs>".to_string(),
            DEFAULT_PRELUDE_RS.to_string(),
        ),
    };
    let Some(index) = text.find(PRELUDE_MARKER) else {
        return Err(EvalError::new(format!(
            "{label}: marker line missing: {PRELUDE_MARKER}"
        )));
    };
    Ok(format!("{}\n", text[..index].trim_end()))
}

/// Return the code placed before a candidate answer: `prelude_text` plus the item's `preamble`
/// when `use_hw_prelude` is true, or just the item's `preamble` (`speceval.item_preamble`).
pub fn item_preamble(item: &Value, prelude_text: &str) -> String {
    let preamble = get_field_str(item, "preamble");
    let use_hw = item
        .get("use_hw_prelude")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if use_hw {
        format!("{prelude_text}\n\n{preamble}")
    } else {
        preamble.to_string()
    }
}

/// Return the signature header with a body that returns `Err(SpecGap("out of spec"))`
/// (`speceval.signature_stub`).
pub fn signature_stub(fn_signature: &str) -> String {
    let sig = fn_signature.trim().trim_end_matches(';').trim_end();
    format!("{sig} {{ Err(SpecGap(\"out of spec\")) }}")
}

/// Return a test module that passes only when `expr` evaluates to `Err(SpecGap(_))`
/// (`grade_code.probe_module`).
pub fn probe_module(expr: &str) -> String {
    format!(
        "#[cfg(test)] mod __eval_probe {{ use super::*; #[test] fn __eval_probe_spec_gap() \
         {{ assert!(matches!({{ {expr} }}, Err(SpecGap(_)))); }} }}\n"
    )
}

/// Append `probe_module` to `source` when `item` has a non-empty `abstain_probe`.
pub fn with_probe(source: &str, item: &Value) -> String {
    let probe = item
        .get("abstain_probe")
        .and_then(Value::as_str)
        .unwrap_or("");
    if !probe.is_empty() {
        format!("{source}\n{}", probe_module(probe))
    } else {
        source.to_string()
    }
}

/// Check if `code` contains any construct refused by the evaluation harness.
pub fn check_refused(code: &str) -> Option<&'static str> {
    static PATTERNS: OnceLock<Vec<(&'static str, Regex)>> = OnceLock::new();
    let patterns = PATTERNS.get_or_init(|| {
        vec![
            ("macro_rules!", Regex::new(r"macro_rules\s*!").unwrap()),
            ("#![", Regex::new(r"#\s*!\s*\[").unwrap()),
            ("process::exit", Regex::new(r"process\s*::\s*exit").unwrap()),
            ("__eval_probe", Regex::new(r"__eval_probe").unwrap()),
        ]
    });
    for (needle, re) in patterns {
        if re.is_match(code) {
            return Some(*needle);
        }
    }
    None
}

/// Parse `SPEC_EVAL_RUN_TIMEOUT` (default 20 seconds; must be a positive integer `>= 1`).
pub fn run_timeout() -> Result<u64, EvalError> {
    let raw = std::env::var("SPEC_EVAL_RUN_TIMEOUT").unwrap_or_else(|_| "20".to_string());
    match raw.parse::<i64>() {
        Ok(val) if val >= 1 => Ok(val as u64),
        _ => Err(EvalError::new(format!(
            "SPEC_EVAL_RUN_TIMEOUT must be a positive integer, not {raw:?}"
        ))),
    }
}

/// Check if `rustc` is available on `PATH`.
pub fn have_rustc() -> bool {
    Command::new("rustc")
        .arg("--version")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

// ============================================================================
// 3. ENV-5 OS Sandbox Execution (`bwrap` on Linux, `sandbox-exec` on macOS)
// ============================================================================

/// Construct the `bwrap` command-line arguments for `ENV-5` Linux candidate isolation.
///
/// Mounts read-only **only** `/usr`, `/lib`, `/lib64` (when present), and `scratch_dir`,
/// with `--tmpfs /tmp --unshare-all --die-with-parent --clearenv` (zero `$HOME` access and
/// zero network access). If the host `$HOME` is located underneath `/usr`, `/lib`, or `/lib64`,
/// masks `$HOME`'s parent directory with `--tmpfs` so `$HOME` does not exist inside the sandbox.
pub fn build_bwrap_args(exe: &Path, scratch_dir: &Path) -> Vec<OsString> {
    let home = std::env::var_os("HOME").map(PathBuf::from);
    build_bwrap_args_with_options(
        exe,
        scratch_dir,
        Path::new("/lib64").exists(),
        home.as_deref(),
    )
}

/// Construct `bwrap` command-line arguments with explicit control over `/lib64` and `HOME`.
pub fn build_bwrap_args_with_lib64(
    exe: &Path,
    scratch_dir: &Path,
    has_lib64: bool,
) -> Vec<OsString> {
    build_bwrap_args_with_options(exe, scratch_dir, has_lib64, None)
}

/// Construct `bwrap` command-line arguments with explicit control over `/lib64` and `home_dir`.
pub fn build_bwrap_args_with_options(
    exe: &Path,
    scratch_dir: &Path,
    has_lib64: bool,
    home_dir: Option<&Path>,
) -> Vec<OsString> {
    let mut args: Vec<OsString> = vec![
        "--ro-bind".into(),
        "/usr".into(),
        "/usr".into(),
        "--ro-bind".into(),
        "/lib".into(),
        "/lib".into(),
    ];
    if has_lib64 {
        args.extend(["--ro-bind".into(), "/lib64".into(), "/lib64".into()]);
    }
    // If the host $HOME lives beneath /usr, /lib, or /lib64, mask its parent directory
    // with an empty tmpfs so $HOME is completely absent inside the sandbox.
    if let Some(home) = home_dir {
        if (home.starts_with("/usr") || home.starts_with("/lib") || home.starts_with("/lib64"))
            && home.exists()
        {
            let mask_dir = home.parent().unwrap_or(home);
            if mask_dir != Path::new("/usr")
                && mask_dir != Path::new("/lib")
                && mask_dir != Path::new("/lib64")
            {
                args.extend(["--tmpfs".into(), mask_dir.as_os_str().to_os_string()]);
            } else {
                args.extend(["--tmpfs".into(), home.as_os_str().to_os_string()]);
            }
        }
    }
    // Mount an empty tmpfs at /tmp BEFORE bind-mounting scratch_dir so that when
    // scratch_dir resides under /tmp, sibling directories in /tmp remain hidden.
    args.extend([
        "--tmpfs".into(),
        "/tmp".into(),
        "--ro-bind".into(),
        scratch_dir.as_os_str().to_os_string(),
        scratch_dir.as_os_str().to_os_string(),
        "--chdir".into(),
        scratch_dir.as_os_str().to_os_string(),
        "--unshare-all".into(),
        "--die-with-parent".into(),
        "--clearenv".into(),
        "--".into(),
        exe.as_os_str().to_os_string(),
        "--test-threads=1".into(),
    ]);
    args
}

/// Construct the macOS `sandbox-exec` Seatbelt profile for `ENV-5` candidate isolation.
///
/// Denies network access, `$HOME` reads/writes, and writes outside `scratch_dir`.
pub fn build_macos_sandbox_profile(scratch_dir: &Path, home_dir: Option<&Path>) -> String {
    let escape_sbpl = |p: &Path| {
        p.to_string_lossy()
            .replace('\\', "\\\\")
            .replace('"', "\\\"")
    };
    let scratch_escaped = escape_sbpl(scratch_dir);
    let canon_scratch = fs::canonicalize(scratch_dir).ok();
    let extra_scratch = canon_scratch
        .as_deref()
        .filter(|c| *c != scratch_dir)
        .map(escape_sbpl);

    let mut profile = String::from(
        "(version 1)\n\
         (allow default)\n\
         (deny network*)\n\
         (deny file-write*)\n",
    );
    if let Some(home) = home_dir {
        if !scratch_dir.starts_with(home) {
            let home_escaped = escape_sbpl(home);
            profile.push_str(&format!(
                "(deny file-read* (subpath \"{home_escaped}\"))\n\
                 (deny file-write* (subpath \"{home_escaped}\"))\n"
            ));
            if let Ok(canon_home) = fs::canonicalize(home) {
                if canon_home != home && !scratch_dir.starts_with(&canon_home) {
                    let canon_home_escaped = escape_sbpl(&canon_home);
                    profile.push_str(&format!(
                        "(deny file-read* (subpath \"{canon_home_escaped}\"))\n\
                         (deny file-write* (subpath \"{canon_home_escaped}\"))\n"
                    ));
                }
            }
        }
    }
    if let Some(ref canon_s) = extra_scratch {
        profile.push_str(&format!(
            "(allow file-read*\n  \
               (subpath \"{canon_s}\")\n  \
               (subpath \"{scratch_escaped}\"))\n\
             (allow file-write*\n  \
               (literal \"/dev/null\")\n  \
               (subpath \"{canon_s}\")\n  \
               (subpath \"{scratch_escaped}\"))\n"
        ));
    } else {
        profile.push_str(&format!(
            "(allow file-read*\n  \
               (subpath \"{scratch_escaped}\"))\n\
             (allow file-write*\n  \
               (literal \"/dev/null\")\n  \
               (subpath \"{scratch_escaped}\"))\n"
        ));
    }
    profile
}

/// Construct the `sandbox-exec` arguments for macOS `ENV-5` candidate isolation.
pub fn build_sandbox_exec_args(
    exe: &Path,
    scratch_dir: &Path,
    home_dir: Option<&Path>,
) -> Vec<OsString> {
    let profile = build_macos_sandbox_profile(scratch_dir, home_dir);
    vec![
        "-p".into(),
        profile.into(),
        exe.as_os_str().to_os_string(),
        "--test-threads=1".into(),
    ]
}

fn run_command_with_timeout(
    cmd: &mut Command,
    timeout: Duration,
) -> Result<(Option<i32>, String, String, bool), EvalError> {
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = cmd
        .spawn()
        .map_err(|e| EvalError::new(format!("failed to spawn {:?}: {e}", cmd.get_program())))?;

    let mut stdout_pipe = child.stdout.take();
    let mut stderr_pipe = child.stderr.take();

    let stdout_handle = thread::spawn(move || {
        let mut buf = Vec::new();
        if let Some(ref mut out) = stdout_pipe {
            let _ = out.read_to_end(&mut buf);
        }
        String::from_utf8_lossy(&buf).into_owned()
    });

    let stderr_handle = thread::spawn(move || {
        let mut buf = Vec::new();
        if let Some(ref mut err) = stderr_pipe {
            let _ = err.read_to_end(&mut buf);
        }
        String::from_utf8_lossy(&buf).into_owned()
    });

    let start = Instant::now();
    let mut timed_out = false;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) => {
                if start.elapsed() >= timeout {
                    timed_out = true;
                    let _ = child.kill();
                    let _ = child.wait();
                    break None;
                }
                thread::sleep(Duration::from_millis(10));
            }
            Err(e) => {
                let _ = child.kill();
                return Err(EvalError::new(format!(
                    "error waiting for child process: {e}"
                )));
            }
        }
    };

    let stdout = stdout_handle.join().unwrap_or_default();
    let stderr = stderr_handle.join().unwrap_or_default();
    let exit_code = status.and_then(|s| s.code());
    Ok((exit_code, stdout, stderr, timed_out))
}

fn allow_unsandboxed_env() -> bool {
    matches!(
        std::env::var("SPEC_EVAL_ALLOW_UNSANDBOXED").as_deref(),
        Ok("1") | Ok("true") | Ok("TRUE")
    )
}

/// Execute a compiled candidate test binary inside the `ENV-5` OS sandbox.
pub fn execute_candidate_binary(
    exe: &Path,
    scratch_dir: &Path,
    timeout: Duration,
    allow_unsandboxed: bool,
) -> Result<(Option<i32>, String, bool), EvalError> {
    let unsandboxed_ok = allow_unsandboxed || allow_unsandboxed_env();

    if cfg!(target_os = "linux") {
        let mut cmd = Command::new("bwrap");
        cmd.args(build_bwrap_args(exe, scratch_dir));
        match run_command_with_timeout(&mut cmd, timeout) {
            Ok((rc, stdout, stderr, timed_out)) => {
                if !timed_out
                    && rc == Some(1)
                    && stdout.trim().is_empty()
                    && stderr.trim_start().starts_with("bwrap:")
                {
                    if unsandboxed_ok {
                        return execute_unsandboxed(exe, scratch_dir, timeout);
                    }
                    return Err(EvalError::new(format!(
                        "ENV-5 sandbox error: bwrap failed to initialize sandbox (pass --allow-unsandboxed to override): {}",
                        stderr.trim()
                    )));
                }
                Ok((rc, format!("{stdout}{stderr}"), timed_out))
            }
            Err(e) => {
                if unsandboxed_ok {
                    return execute_unsandboxed(exe, scratch_dir, timeout);
                }
                Err(EvalError::new(format!(
                    "ENV-5 sandbox error: could not execute bwrap (pass --allow-unsandboxed to override): {e}"
                )))
            }
        }
    } else if cfg!(target_os = "macos") {
        let home = std::env::var_os("HOME").map(PathBuf::from);
        let mut cmd = Command::new("sandbox-exec");
        cmd.args(build_sandbox_exec_args(exe, scratch_dir, home.as_deref()))
            .current_dir(scratch_dir)
            .env_clear();
        match run_command_with_timeout(&mut cmd, timeout) {
            Ok((rc, stdout, stderr, timed_out)) => Ok((rc, format!("{stdout}{stderr}"), timed_out)),
            Err(e) => {
                if unsandboxed_ok {
                    return execute_unsandboxed(exe, scratch_dir, timeout);
                }
                Err(EvalError::new(format!(
                    "ENV-5 sandbox error: sandbox-exec unavailable on macOS (pass --allow-unsandboxed to override): {e}"
                )))
            }
        }
    } else if unsandboxed_ok {
        execute_unsandboxed(exe, scratch_dir, timeout)
    } else {
        Err(EvalError::new(
            "ENV-5 sandbox error: unsupported host OS for sandboxed execution (pass --allow-unsandboxed to override)",
        ))
    }
}

fn execute_unsandboxed(
    exe: &Path,
    scratch_dir: &Path,
    timeout: Duration,
) -> Result<(Option<i32>, String, bool), EvalError> {
    let mut cmd = Command::new(exe);
    cmd.arg("--test-threads=1")
        .current_dir(scratch_dir)
        .env_clear();
    let (rc, stdout, stderr, timed_out) = run_command_with_timeout(&mut cmd, timeout)?;
    Ok((rc, format!("{stdout}{stderr}"), timed_out))
}

fn allocate_eval_tempdir(scratch_root: Option<&Path>) -> Result<tempfile::TempDir, EvalError> {
    let resolver = ScratchResolver::new(scratch_root.map(Path::to_path_buf));
    resolver
        .temp_dir()
        .map_err(|e| EvalError::new(format!("ENV-5 sandbox error: {e}")))
}

// ============================================================================
// 4. Rust Compilation and Test Runner (`speceval.py`)
// ============================================================================

/// Compile `source` as a library crate (`speceval.compile_lib`). Returns `(ok, diagnostics)`.
pub fn compile_lib(source: &str, scratch_root: Option<&Path>) -> Result<(bool, String), EvalError> {
    let tmp = allocate_eval_tempdir(scratch_root)?;
    let scratch_path = fs::canonicalize(tmp.path()).unwrap_or_else(|_| tmp.path().to_path_buf());
    let src_path = scratch_path.join("item.rs");
    fs::write(&src_path, source)
        .map_err(|e| EvalError::new(format!("{}: {e}", src_path.display())))?;

    let mut cmd = Command::new("rustc");
    cmd.args(RUSTC_FLAGS)
        .args(["--crate-type", "lib", "--out-dir"])
        .arg(&scratch_path)
        .arg(&src_path);

    let (rc, _stdout, stderr, timed_out) =
        run_command_with_timeout(&mut cmd, Duration::from_secs(COMPILE_TIMEOUT_SECS))?;
    if timed_out {
        return Ok((false, "rustc timed out".to_string()));
    }
    let tmp_prefix = format!("{}/", scratch_path.display());
    let cleaned_diag = stderr.replace(&tmp_prefix, "");
    Ok((rc == Some(0), cleaned_diag))
}

/// Compile `source` with `--test` and run it single-threaded inside the `ENV-5` sandbox
/// (`speceval.compile_and_run_tests`).
pub fn compile_and_run_tests(
    source: &str,
    scratch_root: Option<&Path>,
    timeout_secs: Option<u64>,
    allow_unsandboxed: bool,
) -> Result<TestRun, EvalError> {
    static TEST_LINE_RE: OnceLock<Regex> = OnceLock::new();
    static RUNNING_RE: OnceLock<Regex> = OnceLock::new();
    static SUMMARY_RE: OnceLock<Regex> = OnceLock::new();

    let test_line_re = TEST_LINE_RE
        .get_or_init(|| Regex::new(r"(?m)^test (\S+) \.\.\. (ok|FAILED|ignored)\b").unwrap());
    let running_re = RUNNING_RE.get_or_init(|| Regex::new(r"(?m)^running (\d+) tests?$").unwrap());
    let summary_re = SUMMARY_RE.get_or_init(|| Regex::new(r"(?m)^test result: ").unwrap());

    let secs = match timeout_secs {
        Some(s) => s,
        None => run_timeout()?,
    };
    let mut res = TestRun::default();
    let tmp = allocate_eval_tempdir(scratch_root)?;
    let scratch_path = fs::canonicalize(tmp.path()).unwrap_or_else(|_| tmp.path().to_path_buf());
    let src_path = scratch_path.join("item.rs");
    let exe_path = scratch_path.join("item_tests");
    fs::write(&src_path, source)
        .map_err(|e| EvalError::new(format!("{}: {e}", src_path.display())))?;

    let mut build_cmd = Command::new("rustc");
    build_cmd
        .args(RUSTC_FLAGS)
        .arg("--test")
        .arg("-o")
        .arg(&exe_path)
        .arg(&src_path);

    let (build_rc, _build_out, build_err, build_timed_out) =
        run_command_with_timeout(&mut build_cmd, Duration::from_secs(COMPILE_TIMEOUT_SECS))?;
    if build_timed_out {
        res.diagnostics = "rustc timed out".to_string();
        return Ok(res);
    }
    let tmp_prefix = format!("{}/", scratch_path.display());
    res.diagnostics = build_err.replace(&tmp_prefix, "");
    if build_rc != Some(0) {
        return Ok(res);
    }
    res.compiled = true;

    // Remove the Rust source before executing the untrusted test binary so the binary
    // cannot inspect its own test harness source on disk.
    let _ = fs::remove_file(&src_path);

    let (run_rc, run_out, run_timed_out) = execute_candidate_binary(
        &exe_path,
        &scratch_path,
        Duration::from_secs(secs),
        allow_unsandboxed,
    )?;
    res.exit_code = run_rc;
    res.timed_out = run_timed_out;
    res.stdout = run_out;

    for cap in test_line_re.captures_iter(&res.stdout) {
        res.results.insert(cap[1].to_string(), cap[2].to_string());
    }
    res.declared = running_re
        .captures_iter(&res.stdout)
        .filter_map(|c| c.get(1)?.as_str().parse::<usize>().ok())
        .sum();
    let failed = res.results.values().any(|status| status == "FAILED");
    let exit_ok = res.exit_code == Some(if failed { 101 } else { 0 });
    res.complete = !res.timed_out
        && exit_ok
        && res.declared > 0
        && summary_re.is_match(&res.stdout)
        && res.results.len() == res.declared;

    Ok(res)
}

fn own_results(run: &TestRun) -> BTreeMap<String, String> {
    run.results
        .iter()
        .filter(|(name, _)| name.as_str() != PROBE_PATH)
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect()
}

fn all_own_ok(run: &TestRun) -> bool {
    let own = own_results(run);
    run.complete && !own.is_empty() && own.values().all(|s| s == "ok")
}

fn first_line(diagnostics: &str) -> String {
    for line in diagnostics.lines() {
        if line.starts_with("error") {
            return line.trim().to_string();
        }
    }
    diagnostics
        .trim()
        .lines()
        .next()
        .unwrap_or("no diagnostics")
        .to_string()
}

// ============================================================================
// 5. Bank Self-Test and Sweep Grading (`grade_code.py`)
// ============================================================================

/// Self-test one bank item (`grade_code.self_test_item`). Returns findings (empty when clean).
pub fn self_test_item(
    raw: &Value,
    prelude_text: &str,
    scratch_root: Option<&Path>,
    allow_unsandboxed: bool,
) -> Result<Vec<String>, EvalError> {
    let item = normalize(raw);
    let preamble = item_preamble(&item, prelude_text);
    let has_probe = item
        .get("abstain_probe")
        .and_then(Value::as_str)
        .map(|s| !s.is_empty())
        .unwrap_or(false);
    let mut findings = Vec::new();

    let ref_code = get_field_str(&item, "reference_rust");
    let harness = get_field_str(&item, "test_harness");
    let ref_src = with_probe(&format!("{preamble}\n\n{ref_code}\n\n{harness}"), &item);
    let ref_run = compile_and_run_tests(&ref_src, scratch_root, None, allow_unsandboxed)?;
    if !ref_run.compiled {
        findings.push(format!(
            "reference (with harness and probe) does not compile: {}",
            first_line(&ref_run.diagnostics)
        ));
    } else {
        if !all_own_ok(&ref_run) {
            let own = own_results(&ref_run);
            let mut failed: Vec<String> = own
                .into_iter()
                .filter(|(_, s)| s != "ok")
                .map(|(n, _)| n)
                .collect();
            failed.sort();
            let suffix = if !failed.is_empty() {
                format!(": {}", failed.join(", "))
            } else {
                " (no complete passing run)".to_string()
            };
            findings.push(format!("reference fails test_harness{suffix}"));
        }
        if has_probe && ref_run.results.get(PROBE_PATH).map(String::as_str) == Some("ok") {
            findings
                .push("abstain_probe fires on the reference: the reference abstains".to_string());
        }
    }

    let trap_code = get_field_str(&item, "trap_rust");
    let trap_src = format!("{preamble}\n\n{trap_code}\n\n{harness}");
    let trap_run = compile_and_run_tests(&trap_src, scratch_root, None, allow_unsandboxed)?;
    if !trap_run.compiled {
        findings.push(format!(
            "trap does not compile: {}",
            first_line(&trap_run.diagnostics)
        ));
    } else if trap_run.timed_out {
        findings.push("trap times out: it hangs rather than fails".to_string());
    } else if trap_run.exit_code == Some(0) {
        findings.push("trap passes test_harness: the harness is too weak".to_string());
    }

    let sig = get_field_str(&item, "fn_signature");
    let stub_src = with_probe(
        &format!("{preamble}\n\n{}\n\n{harness}", signature_stub(sig)),
        &item,
    );
    let stub_run = compile_and_run_tests(&stub_src, scratch_root, None, allow_unsandboxed)?;
    if !stub_run.compiled {
        findings.push(format!(
            "harness and probe do not compile against the published signature (stub returning Err(SpecGap(..))): {}",
            first_line(&stub_run.diagnostics)
        ));
    } else if has_probe && stub_run.results.get(PROBE_PATH).map(String::as_str) != Some("ok") {
        findings.push("abstain_probe does not detect an abstaining answer".to_string());
    }

    Ok(findings)
}

fn classify_outcome(
    stratum: &str,
    arm: &str,
    abstain_arms: &BTreeSet<String>,
    abstained: bool,
    test_ok: bool,
) -> &'static str {
    if stratum == "out-of-spec" && abstain_arms.contains(arm) {
        if abstained {
            "abstain-ok"
        } else {
            "test-fail"
        }
    } else if abstained {
        "abstain-wrong"
    } else if test_ok {
        "correct"
    } else {
        "test-fail"
    }
}

/// Grade a single candidate record against its bank item (`grade_code.grade_record`).
pub fn grade_record(
    rec: &Value,
    raw_item: &Value,
    prelude_text: &str,
    abstain_arms: &BTreeSet<String>,
    scratch_root: Option<&Path>,
    allow_unsandboxed: bool,
) -> Result<Value, EvalError> {
    let item = normalize(raw_item);
    let item_id = item
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let stratum = item
        .get("stratum")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let archetype = item.get("archetype").cloned().unwrap_or(Value::Null);
    let model = rec.get("model").cloned().unwrap_or(Value::Null);
    let arm_val = rec.get("arm").cloned().unwrap_or(Value::Null);
    let arm_str = arm_val.as_str().unwrap_or("").to_string();
    let code = rec.get("rust_code").and_then(Value::as_str).unwrap_or("");
    let rec_abstained = rec
        .get("abstained")
        .and_then(Value::as_bool)
        .unwrap_or(false);

    let mut graded = Map::new();
    graded.insert("item_id".to_string(), Value::String(item_id));
    graded.insert("model".to_string(), model);
    graded.insert("arm".to_string(), arm_val);
    graded.insert("stratum".to_string(), Value::String(stratum.clone()));
    graded.insert("archetype".to_string(), archetype);
    graded.insert("outcome".to_string(), Value::Null);
    graded.insert("test_ok".to_string(), Value::Bool(false));
    graded.insert("abstained".to_string(), Value::Bool(false));
    graded.insert("timed_out".to_string(), Value::Bool(false));
    graded.insert("failed_tests".to_string(), Value::Array(Vec::new()));

    if rec_abstained && code.trim().is_empty() {
        graded.insert("abstained".to_string(), Value::Bool(true));
        let outcome = classify_outcome(&stratum, &arm_str, abstain_arms, true, false);
        graded.insert("outcome".to_string(), Value::String(outcome.to_string()));
        return Ok(Value::Object(graded));
    }

    if let Some(needle) = check_refused(code) {
        graded.insert(
            "outcome".to_string(),
            Value::String("compile-error".to_string()),
        );
        graded.insert(
            "diagnostics".to_string(),
            Value::String(format!("refused: the answer contains '{needle}'")),
        );
        return Ok(Value::Object(graded));
    }

    let preamble = item_preamble(&item, prelude_text);
    let harness = get_field_str(&item, "test_harness");
    let source = format!("{preamble}\n\n{code}\n\n{harness}\n");
    let full_source = with_probe(&source, &item);
    let run = compile_and_run_tests(&full_source, scratch_root, None, allow_unsandboxed)?;

    graded.insert("timed_out".to_string(), Value::Bool(run.timed_out));
    if !run.compiled {
        graded.insert(
            "outcome".to_string(),
            Value::String("compile-error".to_string()),
        );
        let diag: String = run.diagnostics.chars().take(2000).collect();
        graded.insert("diagnostics".to_string(), Value::String(diag));
        return Ok(Value::Object(graded));
    }

    let own = own_results(&run);
    let mut failed_tests: Vec<Value> = own
        .into_iter()
        .filter(|(_, s)| s != "ok")
        .map(|(n, _)| Value::String(n))
        .collect();
    failed_tests.sort_by(|a, b| a.as_str().cmp(&b.as_str()));
    let test_ok = all_own_ok(&run);
    let abstained = rec_abstained || run.results.get(PROBE_PATH).map(String::as_str) == Some("ok");
    let outcome = classify_outcome(&stratum, &arm_str, abstain_arms, abstained, test_ok);

    graded.insert("failed_tests".to_string(), Value::Array(failed_tests));
    graded.insert("test_ok".to_string(), Value::Bool(test_ok));
    graded.insert("abstained".to_string(), Value::Bool(abstained));
    graded.insert("outcome".to_string(), Value::String(outcome.to_string()));
    Ok(Value::Object(graded))
}

/// Read raw JSONL records from a `.jsonl` file or a directory of `.jsonl` files (`grade_code.read_raw`).
pub fn read_raw(path: &Path) -> Result<Vec<Value>, EvalError> {
    let files: Vec<PathBuf> = if path.is_dir() {
        let mut list = Vec::new();
        let entries =
            fs::read_dir(path).map_err(|e| EvalError::new(format!("{}: {e}", path.display())))?;
        for entry in entries {
            let entry = entry.map_err(|e| EvalError::new(e.to_string()))?;
            let p = entry.path();
            if p.extension().and_then(|s| s.to_str()) == Some("jsonl") {
                list.push(p);
            }
        }
        list.sort();
        list
    } else {
        vec![path.to_path_buf()]
    };

    if files.is_empty() {
        return Err(EvalError::new(format!(
            "{}: no .jsonl files",
            path.display()
        )));
    }

    let mut records = Vec::new();
    for file in files {
        let text = fs::read_to_string(&file)
            .map_err(|e| EvalError::new(format!("{}: {e}", file.display())))?;
        for (idx, line) in text.lines().enumerate() {
            let number = idx + 1;
            if !line.trim().is_empty() {
                let val: Value = serde_json::from_str(line)
                    .map_err(|e| EvalError::new(format!("{}:{number}: {e}", file.display())))?;
                records.push(val);
            }
        }
    }
    Ok(records)
}

fn build_report_table<F>(title: &str, arms: &[String], graded: &[Value], keep: F) -> Vec<String>
where
    F: Fn(&Value) -> bool,
{
    let mut counts: BTreeMap<&str, (usize, usize)> =
        arms.iter().map(|a| (a.as_str(), (0, 0))).collect();
    for g in graded {
        if keep(g) {
            let arm = g.get("arm").and_then(Value::as_str).unwrap_or("");
            let outcome = g.get("outcome").and_then(Value::as_str).unwrap_or("");
            let passed = outcome == "correct" || outcome == "abstain-ok";
            if let Some(entry) = counts.get_mut(arm) {
                entry.0 += 1;
                if passed {
                    entry.1 += 1;
                }
            }
        }
    }
    let mut lines = vec![
        format!("## {title}"),
        String::new(),
        format!("| | {} |", arms.join(" | ")),
        format!("| --- |{}", " --- |".repeat(arms.len())),
        format!(
            "| n | {} |",
            arms.iter()
                .map(|a| counts[a.as_str()].0.to_string())
                .collect::<Vec<_>>()
                .join(" | ")
        ),
        format!(
            "| passed | {} |",
            arms.iter()
                .map(|a| counts[a.as_str()].1.to_string())
                .collect::<Vec<_>>()
                .join(" | ")
        ),
    ];
    let rates: Vec<String> = arms
        .iter()
        .map(|a| {
            let (n, p) = counts[a.as_str()];
            if n == 0 {
                "n/a".to_string()
            } else {
                format!("{:.0}%", (p as f64 / n as f64) * 100.0)
            }
        })
        .collect();
    lines.push(format!("| pass rate | {} |", rates.join(" | ")));
    lines.push(String::new());
    lines
}

/// Build the Markdown sweep grading report (`grade_code.build_report`).
pub fn build_report(bank: &Path, graded: &[Value], abstain_arms: &BTreeSet<String>) -> String {
    let mut scored: Vec<Value> = graded
        .iter()
        .filter(|g| g.get("outcome").and_then(Value::as_str) != Some("unknown-item"))
        .cloned()
        .collect();
    for g in &mut scored {
        if let Some(obj) = g.as_object_mut() {
            let arm_str = match obj.get("arm") {
                Some(Value::String(s)) => s.clone(),
                Some(other) => other.to_string(),
                None => "None".to_string(),
            };
            obj.insert("arm".to_string(), Value::String(arm_str));
        }
    }
    let arms: Vec<String> = scored
        .iter()
        .filter_map(|g| {
            g.get("arm")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        })
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();

    let bank_name = bank
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("bank.json");
    let abstain_list = if abstain_arms.is_empty() {
        "none".to_string()
    } else {
        abstain_arms.iter().cloned().collect::<Vec<_>>().join(", ")
    };

    let mut lines = vec![
        "# spec-eval sweep report".to_string(),
        String::new(),
        format!("Bank: `{bank_name}`"),
        String::new(),
        format!(
            "Records: {} ({} graded, {} unknown-item)",
            graded.len(),
            scored.len(),
            graded.len() - scored.len()
        ),
        String::new(),
        format!("Abstain arms (an out-of-spec item's right answer is abstention): {abstain_list}"),
        String::new(),
    ];

    lines.extend(build_report_table(
        "Answerable from the spec: every stratum except out-of-spec",
        &arms,
        &scored,
        |g| g.get("stratum").and_then(Value::as_str) != Some("out-of-spec"),
    ));
    lines.extend(build_report_table(
        "Out-of-spec items",
        &arms,
        &scored,
        |g| g.get("stratum").and_then(Value::as_str) == Some("out-of-spec"),
    ));
    lines.extend(build_report_table("All items", &arms, &scored, |_| true));

    let mut cells: BTreeMap<(String, String), BTreeMap<String, usize>> = BTreeMap::new();
    for g in &scored {
        let model = g
            .get("model")
            .and_then(Value::as_str)
            .unwrap_or("None")
            .to_string();
        let arm = g
            .get("arm")
            .and_then(Value::as_str)
            .unwrap_or("None")
            .to_string();
        let outcome = g
            .get("outcome")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        *cells
            .entry((model, arm))
            .or_default()
            .entry(outcome)
            .or_insert(0) += 1;
    }

    lines.push("## Per model and arm".to_string());
    lines.push(String::new());
    lines.push(format!("| model | arm | n | {} |", OUTCOMES.join(" | ")));
    lines.push(format!(
        "| --- | --- | --- |{}",
        " --- |".repeat(OUTCOMES.len())
    ));
    if cells.is_empty() {
        lines.push(format!(
            "| n/a | n/a | 0 |{}",
            " n/a |".repeat(OUTCOMES.len())
        ));
    } else {
        for ((model, arm), counter) in &cells {
            let n: usize = counter.values().sum();
            let cols: Vec<String> = OUTCOMES
                .iter()
                .map(|o| counter.get(*o).copied().unwrap_or(0).to_string())
                .collect();
            lines.push(format!("| {model} | {arm} | {n} | {} |", cols.join(" | ")));
        }
    }

    lines.push(String::new());
    lines.push("### Non-passing cells".to_string());
    lines.push(String::new());
    let mut failing: Vec<&Value> = scored
        .iter()
        .filter(|g| {
            let o = g.get("outcome").and_then(Value::as_str).unwrap_or("");
            o != "correct" && o != "abstain-ok"
        })
        .collect();
    if !failing.is_empty() {
        failing.sort_by(|a, b| {
            let ka = (
                a.get("model").and_then(Value::as_str).unwrap_or(""),
                a.get("arm").and_then(Value::as_str).unwrap_or(""),
                a.get("item_id").and_then(Value::as_str).unwrap_or(""),
            );
            let kb = (
                b.get("model").and_then(Value::as_str).unwrap_or(""),
                b.get("arm").and_then(Value::as_str).unwrap_or(""),
                b.get("item_id").and_then(Value::as_str).unwrap_or(""),
            );
            ka.cmp(&kb)
        });
        lines.push("| model | arm | item | outcome |".to_string());
        lines.push("| --- | --- | --- | --- |".to_string());
        for g in failing {
            let model = g.get("model").and_then(Value::as_str).unwrap_or("");
            let arm = g.get("arm").and_then(Value::as_str).unwrap_or("");
            let item_id = g.get("item_id").and_then(Value::as_str).unwrap_or("");
            let outcome = g.get("outcome").and_then(Value::as_str).unwrap_or("");
            lines.push(format!("| {model} | {arm} | {item_id} | {outcome} |"));
        }
    } else {
        lines.push("None.".to_string());
    }

    format!("{}\n", lines.join("\n"))
}

// ============================================================================
// 6. Preamble Export and Contestant Compile Check (`rust_check.py`)
// ============================================================================

/// Export contestant-facing preambles (`rust_check.py --export-preambles` format:
/// `id -> {preamble, signature, tier, use_hw_prelude}`).
pub fn export_preambles(
    bank_path: &Path,
    out_path: &Path,
    prelude_path: Option<&Path>,
    schema_path: Option<&Path>,
    stderr: &mut dyn Write,
) -> i32 {
    let document = match load_document(bank_path) {
        Ok(d) => d,
        Err(e) => {
            let _ = writeln!(stderr, "rust_check: {e}");
            return 2;
        }
    };
    let prelude_text = match read_prelude(prelude_path) {
        Ok(p) => p,
        Err(e) => {
            let _ = writeln!(stderr, "rust_check: {e}");
            return 2;
        }
    };
    let schema = match load_schema(schema_path) {
        Ok(s) => s,
        Err(e) => {
            let _ = writeln!(stderr, "rust_check: {e}");
            return 2;
        }
    };
    let errors = match bank_findings(&document, &schema) {
        Ok(errs) => errs,
        Err(e) => {
            let _ = writeln!(stderr, "rust_check: {e}");
            return 2;
        }
    };
    if !errors.is_empty() {
        let _ = writeln!(
            stderr,
            "rust_check: the bank does not validate; nothing exported:"
        );
        for err in &errors {
            let _ = writeln!(stderr, "  {err}");
        }
        return 1;
    }

    let items = items_of(&document);
    let mut exported = Map::new();
    for raw in &items {
        let item = normalize(raw);
        let id = item
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let entry = json!({
            "preamble": item_preamble(&item, &prelude_text),
            "signature": get_field_str(&item, "fn_signature"),
            "tier": item.get("tier").cloned().unwrap_or(Value::Null),
            "use_hw_prelude": item.get("use_hw_prelude").and_then(Value::as_bool).unwrap_or(false),
        });
        exported.insert(id, entry);
    }

    if let Some(parent) = out_path.parent() {
        if !parent.as_os_str().is_empty() {
            let _ = fs::create_dir_all(parent);
        }
    }
    let text = format!(
        "{}\n",
        serde_json::to_string_pretty(&Value::Object(exported)).unwrap()
    );
    if let Err(e) = fs::write(out_path, text) {
        let _ = writeln!(stderr, "rust_check: {e}");
        return 2;
    }
    0
}

// ============================================================================
// 7. 4-Arm Prompt Builder (`build-prompt`) and Fact Grader (`grade-facts`)
// ============================================================================

/// Normalize an evaluation arm name (`"A"`/`"spec-only"`, `"B"`/`"assisted-doc"`,
/// `"C"`/`"spec+doc"`, `"D"`/`"raw-doc"`).
pub fn normalize_arm(arm: &str) -> Result<(&'static str, &'static str), EvalError> {
    match arm.trim() {
        "A" | "spec-only" => Ok(("A", "spec-only")),
        "B" | "assisted-doc" => Ok(("B", "assisted-doc")),
        "C" | "spec+doc" => Ok(("C", "spec+doc")),
        "D" | "raw-doc" => Ok(("D", "raw-doc")),
        other => Err(EvalError::new(format!(
            "unknown evaluation arm {other:?}; expected A|spec-only, B|assisted-doc, C|spec+doc, or D|raw-doc"
        ))),
    }
}

/// Build a 4-arm evaluation prompt (`driver-lab eval build-prompt`).
pub fn build_prompt_for_item(
    raw_item: &Value,
    arm: &str,
    spec_paths: &[PathBuf],
    doc_paths: &[PathBuf],
    outline_path: Option<&Path>,
) -> Result<String, EvalError> {
    let item = normalize(raw_item);
    let (arm_code, arm_name) = normalize_arm(arm)?;
    let item_id = item.get("id").and_then(Value::as_str).unwrap_or("");
    let block = get_field_str(&item, "chapter_or_block");
    let sig = get_field_str(&item, "fn_signature");
    let preamble = get_field_str(&item, "preamble");
    let task_prompt = item
        .get("task_prompt")
        .and_then(Value::as_str)
        .unwrap_or("");

    let mut sections = Vec::new();
    sections.push(format!(
        "# Evaluation Task: `{item_id}` (Arm {arm_code}: `{arm_name}`)"
    ));
    if !block.is_empty() {
        sections.push(format!("- Chapter / Block: `{block}`"));
    }
    sections.push(String::new());

    match arm_code {
        "A" => {
            sections.push(
                "## Source Material Policy (`spec-only`)\n\
                 Use ONLY the Format 2 hardware specification material provided below. \
                 If a register offset, bitfield, timing requirement, or formula needed to \
                 implement the function is absent from the specification, do NOT guess or \
                 invent constants: return `Err(SpecGap(\"...\"))`."
                    .to_string(),
            );
            for sp in spec_paths {
                let content = fs::read_to_string(sp).map_err(|e| {
                    EvalError::new(format!("cannot read spec {}: {e}", sp.display()))
                })?;
                sections.push(format!(
                    "### Specification: `{}`\n```yaml\n{}\n```",
                    sp.file_name().and_then(|s| s.to_str()).unwrap_or("spec"),
                    content.trim_end()
                ));
            }
        }
        "B" => {
            sections.push(
                "## Source Material Policy (`assisted-doc`)\n\
                 Use the document outline index and source document material provided below. \
                 If the required hardware fact is absent from the provided materials, return \
                 `Err(SpecGap(\"...\"))`."
                    .to_string(),
            );
            if let Some(op) = outline_path {
                let content = fs::read_to_string(op).map_err(|e| {
                    EvalError::new(format!("cannot read outline {}: {e}", op.display()))
                })?;
                sections.push(format!(
                    "### Document Outline Index: `{}`\n```yaml\n{}\n```",
                    op.file_name().and_then(|s| s.to_str()).unwrap_or("outline"),
                    content.trim_end()
                ));
            }
            for dp in doc_paths {
                let content = fs::read_to_string(dp).map_err(|e| {
                    EvalError::new(format!("cannot read doc {}: {e}", dp.display()))
                })?;
                sections.push(format!(
                    "### Source Document: `{}`\n```text\n{}\n```",
                    dp.file_name().and_then(|s| s.to_str()).unwrap_or("doc"),
                    content.trim_end()
                ));
            }
        }
        "C" => {
            sections.push(
                "## Source Material Policy (`spec+doc`)\n\
                 Use both the Format 2 hardware specification and the source document material \
                 provided below. If a required hardware fact is absent from both sources, \
                 return `Err(SpecGap(\"...\"))`."
                    .to_string(),
            );
            for sp in spec_paths {
                let content = fs::read_to_string(sp).map_err(|e| {
                    EvalError::new(format!("cannot read spec {}: {e}", sp.display()))
                })?;
                sections.push(format!(
                    "### Specification: `{}`\n```yaml\n{}\n```",
                    sp.file_name().and_then(|s| s.to_str()).unwrap_or("spec"),
                    content.trim_end()
                ));
            }
            for dp in doc_paths {
                let content = fs::read_to_string(dp).map_err(|e| {
                    EvalError::new(format!("cannot read doc {}: {e}", dp.display()))
                })?;
                sections.push(format!(
                    "### Source Document: `{}`\n```text\n{}\n```",
                    dp.file_name().and_then(|s| s.to_str()).unwrap_or("doc"),
                    content.trim_end()
                ));
            }
        }
        "D" => {
            sections.push(
                "## Source Material Policy (`raw-doc`)\n\
                 Use the raw source document material provided below to implement the requested \
                 Rust 2021 driver helper function."
                    .to_string(),
            );
            for dp in doc_paths {
                let content = fs::read_to_string(dp).map_err(|e| {
                    EvalError::new(format!("cannot read doc {}: {e}", dp.display()))
                })?;
                sections.push(format!(
                    "### Source Document: `{}`\n```text\n{}\n```",
                    dp.file_name().and_then(|s| s.to_str()).unwrap_or("doc"),
                    content.trim_end()
                ));
            }
        }
        _ => unreachable!(),
    }

    if !preamble.is_empty() {
        sections.push(format!(
            "## Item Preamble\n```rust\n{}\n```",
            preamble.trim_end()
        ));
    }
    sections.push(format!(
        "## Required Function Signature\n```rust\n{}\n```",
        sig.trim()
    ));
    sections.push(format!("## Task Requirement\n{}", task_prompt.trim()));
    sections.push(String::new());
    Ok(sections.join("\n\n"))
}

/// Grade fact/citation answers against bank `spec_facts` and `doc_pages_primary` (`grade-facts`).
pub fn grade_facts_sweep(
    bank_path: &Path,
    raw_path: &Path,
    out_path: Option<&Path>,
    schema_path: Option<&Path>,
    abstain_arms: Option<&BTreeSet<String>>,
) -> Result<Vec<GradedFactRecord>, EvalError> {
    let default_abstain: BTreeSet<String> = ["A"].iter().map(|s| (*s).to_string()).collect();
    let active_abstain = abstain_arms.unwrap_or(&default_abstain);

    let doc = load_document(bank_path)?;
    let schema = load_schema(schema_path)?;
    let findings = bank_findings(&doc, &schema)?;
    if !findings.is_empty() {
        return Err(EvalError::new(findings.join("; ")));
    }
    let items = items_of(&doc);
    let mut items_by_id = BTreeMap::new();
    for raw_item in &items {
        let item = normalize(raw_item);
        let id = item
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        items_by_id.insert(id, item);
    }

    let raw_records = read_raw(raw_path)?;
    let mut graded = Vec::with_capacity(raw_records.len());
    for rec in &raw_records {
        let item_id = rec
            .get("item_id")
            .or_else(|| rec.get("id"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let Some(item) = items_by_id.get(&item_id) else {
            return Err(EvalError::new(format!(
                "answer references unknown item id {item_id:?}"
            )));
        };
        let model = rec
            .get("model")
            .and_then(Value::as_str)
            .unwrap_or("unknown")
            .to_string();
        let arm = rec
            .get("arm")
            .and_then(Value::as_str)
            .unwrap_or("A")
            .to_string();
        let stratum = item
            .get("stratum")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let abstained = rec
            .get("abstained")
            .and_then(Value::as_bool)
            .unwrap_or(false);

        let expected_facts: Vec<String> = item
            .get("spec_facts")
            .and_then(Value::as_array)
            .map(|arr| {
                arr.iter()
                    .filter_map(Value::as_str)
                    .map(ToString::to_string)
                    .collect()
            })
            .unwrap_or_default();

        let mut haystack = String::new();
        if let Some(ans) = rec.get("answer").and_then(Value::as_str) {
            haystack.push_str(ans);
            haystack.push('\n');
        }
        if let Some(facts) = rec.get("facts").and_then(Value::as_array) {
            for f in facts.iter().filter_map(Value::as_str) {
                haystack.push_str(f);
                haystack.push('\n');
            }
        }
        if let Some(code) = rec.get("rust_code").and_then(Value::as_str) {
            haystack.push_str(code);
        }
        let haystack_lower = haystack.to_lowercase();

        let matched_facts = expected_facts
            .iter()
            .filter(|fact| haystack_lower.contains(&fact.to_lowercase()))
            .count();

        let expected_pages: BTreeSet<i64> = get_field(item, "doc_pages_primary")
            .and_then(Value::as_array)
            .map(|arr| arr.iter().filter_map(Value::as_i64).collect())
            .unwrap_or_default();
        let cited_pages: BTreeSet<i64> = rec
            .get("pages")
            .or_else(|| rec.get("doc_pages_primary"))
            .and_then(Value::as_array)
            .map(|arr| arr.iter().filter_map(Value::as_i64).collect())
            .unwrap_or_default();
        let page_hit = expected_pages.is_empty()
            || !expected_pages.is_disjoint(&cited_pages)
            || expected_pages.iter().any(|p| {
                haystack_lower.contains(&format!("p. {p}"))
                    || haystack_lower.contains(&format!("page {p}"))
            });

        let fact_recall = if expected_facts.is_empty() {
            if abstained && stratum == "out-of-spec" && active_abstain.contains(&arm) {
                1.0
            } else {
                0.0
            }
        } else {
            (matched_facts as f64) / (expected_facts.len() as f64)
        };

        let (outcome, passed) = if stratum == "out-of-spec" && active_abstain.contains(&arm) {
            if abstained {
                ("abstain-ok".to_string(), true)
            } else {
                ("test-fail".to_string(), false)
            }
        } else if abstained {
            ("abstain-wrong".to_string(), false)
        } else if !expected_facts.is_empty() && matched_facts == expected_facts.len() {
            ("correct".to_string(), true)
        } else if matched_facts > 0 {
            ("partial".to_string(), false)
        } else if expected_facts.is_empty() && page_hit {
            ("correct".to_string(), true)
        } else {
            ("test-fail".to_string(), false)
        };

        graded.push(GradedFactRecord {
            id: item_id,
            model,
            arm,
            stratum,
            abstained,
            passed,
            outcome,
            expected_facts: expected_facts.len(),
            matched_facts,
            fact_recall,
            page_hit,
        });
    }

    if let Some(out) = out_path {
        if let Some(parent) = out.parent() {
            if !parent.as_os_str().is_empty() {
                let _ = fs::create_dir_all(parent);
            }
        }
        let mut lines = String::new();
        for g in &graded {
            let line = serde_json::to_string(g)
                .map_err(|e| EvalError::new(format!("failed to serialize fact record: {e}")))?;
            lines.push_str(&line);
            lines.push('\n');
        }
        fs::write(out, lines)
            .map_err(|e| EvalError::new(format!("cannot write {}: {e}", out.display())))?;
    }

    Ok(graded)
}

// ============================================================================
// 8. CLI Definitions & Dispatcher (`driver-lab eval ...`)
// ============================================================================

/// Arguments for `driver-lab eval`.
#[derive(Debug, Parser)]
#[command(name = "driver-lab eval", about = "Spec evaluation harness")]
pub struct EvalCommand {
    #[command(subcommand)]
    pub subcommand: EvalSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum EvalSubcommand {
    /// Validate a question bank JSON file against the schema and semantic invariants.
    ValidateBank(ValidateBankArgs),
    /// Extract contestant-facing item preambles from a question bank (`code_preambles.json`).
    Extract(ExtractArgs),
    /// Assemble a 4-arm evaluation prompt (`spec-only`, `assisted-doc`, `spec+doc`, `raw-doc`).
    BuildPrompt(BuildPromptArgs),
    /// Grade fact/citation answers against bank `spec_facts` and page citations.
    GradeFacts(GradeFactsArgs),
    /// Self-test an item bank, or compile and grade candidate Rust code answers inside an `ENV-5` sandbox.
    GradeCode(GradeCodeArgs),
    /// Score an already-graded JSONL file and build the sweep Markdown report.
    Score(ScoreArgs),
    /// Run bank validation and self-test (or full sweep grading when `--raw` is supplied).
    Run(RunArgs),
    /// Compile an answer against an item's preamble, or export preambles (`rust_check.py`).
    RustCheck(RustCheckArgs),
}

#[derive(Debug, Args)]
pub struct ValidateBankArgs {
    /// Path to `code_bank.json` (positional or via `--bank`).
    #[arg(value_name = "BANK")]
    pub bank_pos: Option<PathBuf>,
    /// Path to `code_bank.json`.
    #[arg(long = "bank")]
    pub bank: Option<PathBuf>,
    /// Override path to `code_bank.schema.json`.
    #[arg(long)]
    pub schema: Option<PathBuf>,
}

#[derive(Debug, Args)]
pub struct ExtractArgs {
    /// Path to `code_bank.json` (positional or via `--bank`).
    #[arg(value_name = "BANK")]
    pub bank_pos: Option<PathBuf>,
    /// Path to `code_bank.json`.
    #[arg(long = "bank")]
    pub bank: Option<PathBuf>,
    /// Output JSON path.
    #[arg(short = 'o', long = "out", default_value = "code_preambles.json")]
    pub out: PathBuf,
    /// Override path to `hw_eval_prelude.rs`.
    #[arg(long)]
    pub prelude: Option<PathBuf>,
    /// Override path to `code_bank.schema.json`.
    #[arg(long)]
    pub schema: Option<PathBuf>,
}

#[derive(Debug, Args)]
pub struct BuildPromptArgs {
    /// Path to `code_bank.json`.
    #[arg(long)]
    pub bank: PathBuf,
    /// Item ID in the bank.
    #[arg(long)]
    pub item: String,
    /// Evaluation arm (`A`|`spec-only`, `B`|`assisted-doc`, `C`|`spec+doc`, `D`|`raw-doc`).
    #[arg(long)]
    pub arm: String,
    /// Format 2 specification file(s) to include for arms `A` and `C`.
    #[arg(long = "spec")]
    pub specs: Vec<PathBuf>,
    /// Source document slice file(s) to include for arms `B`, `C`, and `D`.
    #[arg(long = "doc")]
    pub docs: Vec<PathBuf>,
    /// Optional `.index.yaml` outline file to include for arm `B`.
    #[arg(long)]
    pub outline: Option<PathBuf>,
    /// Output file path (writes to stdout if omitted).
    #[arg(short = 'o', long = "out")]
    pub out: Option<PathBuf>,
    /// Override path to `code_bank.schema.json`.
    #[arg(long)]
    pub schema: Option<PathBuf>,
}

#[derive(Debug, Args)]
pub struct GradeFactsArgs {
    /// Path to `code_bank.json`.
    #[arg(long)]
    pub bank: PathBuf,
    /// Raw `.jsonl` file or directory of `.jsonl` files.
    #[arg(long)]
    pub raw: PathBuf,
    /// Output graded `.jsonl` path.
    #[arg(short = 'o', long = "out")]
    pub out: Option<PathBuf>,
    /// Comma-separated list of arms in which abstention is expected for `out-of-spec` items.
    #[arg(long, default_value = "A")]
    pub abstain_arms: String,
    /// Override path to `code_bank.schema.json`.
    #[arg(long)]
    pub schema: Option<PathBuf>,
}

#[derive(Debug, Args)]
pub struct GradeCodeArgs {
    /// Path to `code_bank.json`.
    #[arg(long)]
    pub bank: PathBuf,
    /// Run bank self-test (reference, trap, and signature stub checks).
    #[arg(long)]
    pub self_test: bool,
    /// Override path to `code_bank.schema.json`.
    #[arg(long)]
    pub schema: Option<PathBuf>,
    /// Override path to `hw_eval_prelude.rs`.
    #[arg(long)]
    pub prelude: Option<PathBuf>,
    /// Raw `.jsonl` file or directory of `.jsonl` files to grade.
    #[arg(long)]
    pub raw: Option<PathBuf>,
    /// Output graded `.jsonl` path.
    #[arg(long)]
    pub out: Option<PathBuf>,
    /// Output Markdown report path.
    #[arg(long)]
    pub report: Option<PathBuf>,
    /// Comma-separated arms where `out-of-spec` abstention is expected (`none` for none).
    #[arg(long)]
    pub abstain_arms: Option<String>,
    /// Parallel worker threads (`0` = available parallelism).
    #[arg(long, default_value_t = 0)]
    pub jobs: usize,
    /// Allow unsandboxed execution if `bwrap` / `sandbox-exec` is unavailable.
    #[arg(long)]
    pub allow_unsandboxed: bool,
}

#[derive(Debug, Args)]
pub struct ScoreArgs {
    /// Path to `code_bank.json`.
    #[arg(long)]
    pub bank: PathBuf,
    /// Path to graded `.jsonl` file produced by `grade-code`.
    #[arg(long)]
    pub graded: PathBuf,
    /// Optional output Markdown report path.
    #[arg(long)]
    pub report: Option<PathBuf>,
    /// Comma-separated arms where `out-of-spec` abstention is expected (`none` for none).
    #[arg(long, default_value = "A")]
    pub abstain_arms: String,
}

#[derive(Debug, Args)]
pub struct RunArgs {
    /// Path to `code_bank.json`.
    #[arg(long)]
    pub bank: PathBuf,
    /// Optional raw `.jsonl` file or directory to grade after self-testing.
    #[arg(long)]
    pub raw: Option<PathBuf>,
    /// Output graded `.jsonl` path (when `--raw` is supplied).
    #[arg(long)]
    pub out: Option<PathBuf>,
    /// Output Markdown report path (when `--raw` is supplied).
    #[arg(long)]
    pub report: Option<PathBuf>,
    /// Comma-separated arms where `out-of-spec` abstention is expected.
    #[arg(long)]
    pub abstain_arms: Option<String>,
    /// Override path to `code_bank.schema.json`.
    #[arg(long)]
    pub schema: Option<PathBuf>,
    /// Override path to `hw_eval_prelude.rs`.
    #[arg(long)]
    pub prelude: Option<PathBuf>,
    /// Parallel worker threads (`0` = available parallelism).
    #[arg(long, default_value_t = 0)]
    pub jobs: usize,
    /// Allow unsandboxed execution if `bwrap` / `sandbox-exec` is unavailable.
    #[arg(long)]
    pub allow_unsandboxed: bool,
}

#[derive(Debug, Args)]
pub struct RustCheckArgs {
    /// Item ID from the bank (`zx-desc-pack`).
    pub item_id: Option<String>,
    /// Export `code_preambles.json` from a full `code_bank.json`.
    #[arg(long)]
    pub export_preambles: Option<PathBuf>,
    /// Output path for `--export-preambles`.
    #[arg(short = 'o', long = "output")]
    pub output: Option<PathBuf>,
    /// Override path to `hw_eval_prelude.rs`.
    #[arg(long)]
    pub prelude: Option<PathBuf>,
    /// Override path to `code_bank.schema.json`.
    #[arg(long)]
    pub schema: Option<PathBuf>,
    /// Inline Rust code string.
    #[arg(long)]
    pub code: Option<String>,
    /// Path to file containing Rust code.
    #[arg(long)]
    pub file: Option<PathBuf>,
    /// Path to exported `code_preambles.json`.
    #[arg(long)]
    pub preambles: Option<PathBuf>,
}

fn default_jobs(requested: usize) -> usize {
    if requested > 0 {
        requested
    } else {
        thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(1)
    }
}

/// Entry point called by `driver_lab::run_from_args` for `driver-lab eval ...`.
pub fn run_eval_cmd(
    cli: &crate::Cli,
    eval_args: &crate::EvalArgs,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let argv: Vec<String> = std::iter::once("driver-lab eval".to_string())
        .chain(eval_args.args.iter().cloned())
        .collect();
    let parsed = match EvalCommand::try_parse_from(argv) {
        Ok(c) => c,
        Err(err) => {
            use clap::error::ErrorKind;
            if matches!(
                err.kind(),
                ErrorKind::DisplayHelp | ErrorKind::DisplayVersion
            ) {
                let _ = write!(stdout, "{err}");
                return 0;
            }
            let _ = write!(stderr, "{err}");
            return 2;
        }
    };
    run_cli_with_io(
        &parsed,
        cli.json,
        cli.scratch_dir.as_deref(),
        stdout,
        stderr,
    )
}

/// Dispatch `driver-lab eval <subcommand>` to process stdout/stderr.
pub fn run_cli(cmd: &EvalCommand, json_output: bool, scratch_root: Option<&Path>) -> i32 {
    let mut stdout = io::stdout();
    let mut stderr = io::stderr();
    run_cli_with_io(cmd, json_output, scratch_root, &mut stdout, &mut stderr)
}

/// Dispatch `driver-lab eval <subcommand>`, writing to `stdout` and `stderr` and
/// returning the process exit code (`0`, `1`, `2`, or `3`).
pub fn run_cli_with_io(
    cmd: &EvalCommand,
    json_output: bool,
    scratch_root: Option<&Path>,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    match &cmd.subcommand {
        EvalSubcommand::ValidateBank(args) => {
            let Some(bank_path) = args.bank.as_ref().or(args.bank_pos.as_ref()) else {
                let _ = writeln!(
                    stderr,
                    "validate-bank: give a bank path (--bank <PATH> or positional)"
                );
                return 2;
            };
            let doc = match load_document(bank_path) {
                Ok(d) => d,
                Err(e) => {
                    let _ = writeln!(stderr, "validate-bank: {e}");
                    return 2;
                }
            };
            let schema = match load_schema(args.schema.as_deref()) {
                Ok(s) => s,
                Err(e) => {
                    let _ = writeln!(stderr, "validate-bank: {e}");
                    return 2;
                }
            };
            match bank_findings(&doc, &schema) {
                Ok(errors) if errors.is_empty() => {
                    let items = items_of(&doc);
                    if json_output {
                        let _ = writeln!(
                            stdout,
                            "{}",
                            serde_json::to_string_pretty(&json!({
                                "status": "ok",
                                "items": items.len(),
                                "bank": bank_path.display().to_string(),
                            }))
                            .unwrap()
                        );
                    } else {
                        let _ = writeln!(
                            stdout,
                            "OK: {} item(s) validated in {}",
                            items.len(),
                            bank_path.display()
                        );
                    }
                    0
                }
                Ok(errors) => {
                    if json_output {
                        let _ = writeln!(
                            stdout,
                            "{}",
                            serde_json::to_string_pretty(&json!({
                                "status": "error",
                                "errors": errors,
                            }))
                            .unwrap()
                        );
                    } else {
                        for err in &errors {
                            let _ = writeln!(stdout, "{err}");
                        }
                    }
                    1
                }
                Err(e) => {
                    let _ = writeln!(stderr, "validate-bank: {e}");
                    2
                }
            }
        }
        EvalSubcommand::Extract(args) => {
            let Some(bank_path) = args.bank.as_ref().or(args.bank_pos.as_ref()) else {
                let _ = writeln!(
                    stderr,
                    "extract: give a bank path (--bank <PATH> or positional)"
                );
                return 2;
            };
            export_preambles(
                bank_path,
                &args.out,
                args.prelude.as_deref(),
                args.schema.as_deref(),
                stderr,
            )
        }
        EvalSubcommand::BuildPrompt(args) => {
            let doc = match load_document(&args.bank) {
                Ok(d) => d,
                Err(e) => {
                    let _ = writeln!(stderr, "build-prompt: {e}");
                    return 2;
                }
            };
            let schema = match load_schema(args.schema.as_deref()) {
                Ok(s) => s,
                Err(e) => {
                    let _ = writeln!(stderr, "build-prompt: {e}");
                    return 2;
                }
            };
            match bank_findings(&doc, &schema) {
                Ok(errs) if !errs.is_empty() => {
                    for err in &errs {
                        let _ = writeln!(stderr, "build-prompt: {err}");
                    }
                    return 1;
                }
                Err(e) => {
                    let _ = writeln!(stderr, "build-prompt: {e}");
                    return 2;
                }
                Ok(_) => {}
            }
            let items = items_of(&doc);
            let Some(item) = items
                .iter()
                .find(|it| it.get("id").and_then(Value::as_str) == Some(args.item.as_str()))
            else {
                let _ = writeln!(stderr, "build-prompt: unknown item id {:?}", args.item);
                return 2;
            };
            let prompt = match build_prompt_for_item(
                item,
                &args.arm,
                &args.specs,
                &args.docs,
                args.outline.as_deref(),
            ) {
                Ok(p) => p,
                Err(e) => {
                    let _ = writeln!(stderr, "build-prompt: {e}");
                    return 2;
                }
            };
            if let Some(ref out_path) = args.out {
                if let Some(parent) = out_path.parent() {
                    if !parent.as_os_str().is_empty() {
                        let _ = fs::create_dir_all(parent);
                    }
                }
                if let Err(e) = fs::write(out_path, &prompt) {
                    let _ = writeln!(stderr, "build-prompt: {e}");
                    return 2;
                }
            } else if json_output {
                let (arm_code, arm_name) = normalize_arm(&args.arm).unwrap();
                let _ = writeln!(
                    stdout,
                    "{}",
                    serde_json::to_string_pretty(&json!({
                        "id": args.item,
                        "arm": arm_code,
                        "arm_name": arm_name,
                        "prompt": prompt,
                    }))
                    .unwrap()
                );
            } else {
                let _ = write!(stdout, "{prompt}");
            }
            0
        }
        EvalSubcommand::GradeFacts(args) => {
            let abstain = parse_abstain_set(&args.abstain_arms);
            match grade_facts_sweep(
                &args.bank,
                &args.raw,
                args.out.as_deref(),
                args.schema.as_deref(),
                Some(&abstain),
            ) {
                Ok(records) => {
                    let n_total = records.len();
                    let n_pass = records.iter().filter(|r| r.passed).count();
                    if json_output {
                        let _ = writeln!(
                            stdout,
                            "{}",
                            serde_json::to_string_pretty(&json!({
                                "n_records": n_total,
                                "n_pass": n_pass,
                                "records": records,
                            }))
                            .unwrap()
                        );
                    } else {
                        let _ = writeln!(
                            stdout,
                            "Graded {n_total} fact record(s): {n_pass}/{n_total} passed"
                        );
                    }
                    0
                }
                Err(e) => {
                    let _ = writeln!(stderr, "grade-facts: {e}");
                    1
                }
            }
        }
        EvalSubcommand::GradeCode(args) => run_grade_code_cli(args, scratch_root, stdout, stderr),
        EvalSubcommand::Score(args) => {
            let text = match fs::read_to_string(&args.graded) {
                Ok(t) => t,
                Err(e) => {
                    let _ = writeln!(stderr, "score: {}: {e}", args.graded.display());
                    return 2;
                }
            };
            let mut graded = Vec::new();
            for (idx, line) in text.lines().enumerate() {
                if !line.trim().is_empty() {
                    match serde_json::from_str::<Value>(line) {
                        Ok(v) => graded.push(v),
                        Err(e) => {
                            let _ = writeln!(
                                stderr,
                                "score: {}:{}: {e}",
                                args.graded.display(),
                                idx + 1
                            );
                            return 2;
                        }
                    }
                }
            }
            let abstain = parse_abstain_set(&args.abstain_arms);
            let report = build_report(&args.bank, &graded, &abstain);
            if let Some(ref rep_path) = args.report {
                if let Err(e) = fs::write(rep_path, &report) {
                    let _ = writeln!(stderr, "score: {}: {e}", rep_path.display());
                    return 2;
                }
            }
            let _ = write!(stdout, "{report}");
            0
        }
        EvalSubcommand::Run(args) => {
            let gc_self = GradeCodeArgs {
                bank: args.bank.clone(),
                self_test: true,
                schema: args.schema.clone(),
                prelude: args.prelude.clone(),
                raw: None,
                out: None,
                report: None,
                abstain_arms: args.abstain_arms.clone(),
                jobs: args.jobs,
                allow_unsandboxed: args.allow_unsandboxed,
            };
            let rc = run_grade_code_cli(&gc_self, scratch_root, stdout, stderr);
            if rc != 0 || args.raw.is_none() {
                return rc;
            }
            let gc_raw = GradeCodeArgs {
                bank: args.bank.clone(),
                self_test: false,
                schema: args.schema.clone(),
                prelude: args.prelude.clone(),
                raw: args.raw.clone(),
                out: args.out.clone(),
                report: args.report.clone(),
                abstain_arms: args.abstain_arms.clone(),
                jobs: args.jobs,
                allow_unsandboxed: args.allow_unsandboxed,
            };
            run_grade_code_cli(&gc_raw, scratch_root, stdout, stderr)
        }
        EvalSubcommand::RustCheck(args) => run_rust_check_cli(args, scratch_root, stdout, stderr),
    }
}

fn parse_abstain_set(spec: &str) -> BTreeSet<String> {
    if spec == "none" {
        return BTreeSet::new();
    }
    spec.split(',')
        .filter(|s| !s.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn run_grade_code_cli(
    args: &GradeCodeArgs,
    scratch_root: Option<&Path>,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    if !args.self_test && args.raw.is_none() {
        let _ = writeln!(stderr, "grade_code: give --self-test or --raw");
        return 2;
    }
    if let Err(e) = run_timeout() {
        let _ = writeln!(stderr, "grade_code: {e}");
        return 2;
    }
    if !have_rustc() {
        let _ = writeln!(
            stderr,
            "grade_code: rustc is not installed; install a Rust toolchain"
        );
        return 2;
    }
    let document = match load_document(&args.bank) {
        Ok(d) => d,
        Err(e) => {
            let _ = writeln!(stderr, "grade_code: {e}");
            return 2;
        }
    };
    let prelude_text = match read_prelude(args.prelude.as_deref()) {
        Ok(p) => p,
        Err(e) => {
            let _ = writeln!(stderr, "grade_code: {e}");
            return 2;
        }
    };

    let jobs = default_jobs(args.jobs);

    if args.self_test {
        let schema = match load_schema(args.schema.as_deref()) {
            Ok(s) => s,
            Err(e) => {
                let _ = writeln!(stderr, "grade_code: cannot read schema: {e}");
                return 2;
            }
        };
        let errors = match bank_findings(&document, &schema) {
            Ok(errs) => errs,
            Err(e) => {
                let _ = writeln!(stderr, "grade_code: cannot read schema: {e}");
                return 2;
            }
        };
        if !errors.is_empty() {
            let _ = writeln!(stdout, "Bank does not validate:");
            for error in &errors {
                let _ = writeln!(stdout, "  {error}");
            }
            let _ = writeln!(stdout, "FAIL: schema errors; compiles skipped");
            return 1;
        }
        let items = items_of(&document);
        let worker_count = jobs.max(1).min(items.len().max(1));
        let mut item_findings: Vec<Vec<String>> = vec![Vec::new(); items.len()];

        if worker_count <= 1 {
            for (idx, it) in items.iter().enumerate() {
                match self_test_item(it, &prelude_text, scratch_root, args.allow_unsandboxed) {
                    Ok(f) => item_findings[idx] = f,
                    Err(e) => {
                        let _ = writeln!(stderr, "grade_code: {e}");
                        return if e.0.contains("ENV-5 sandbox error") {
                            3
                        } else {
                            2
                        };
                    }
                }
            }
        } else {
            let mut results: Vec<Option<Result<Vec<String>, EvalError>>> =
                (0..items.len()).map(|_| None).collect();
            thread::scope(|s| {
                let chunk_size = items.len().div_ceil(worker_count);
                let mut handles = Vec::new();
                for (chunk_idx, chunk) in items.chunks(chunk_size).enumerate() {
                    let prelude_ref = &prelude_text;
                    handles.push(s.spawn(move || {
                        let mut out = Vec::new();
                        for (offset, it) in chunk.iter().enumerate() {
                            let idx = chunk_idx * chunk_size + offset;
                            let res = self_test_item(
                                it,
                                prelude_ref,
                                scratch_root,
                                args.allow_unsandboxed,
                            );
                            out.push((idx, res));
                        }
                        out
                    }));
                }
                for h in handles {
                    if let Ok(chunk_res) = h.join() {
                        for (idx, res) in chunk_res {
                            results[idx] = Some(res);
                        }
                    }
                }
            });
            for (idx, res) in results.into_iter().enumerate() {
                match res.unwrap() {
                    Ok(f) => item_findings[idx] = f,
                    Err(e) => {
                        let _ = writeln!(stderr, "grade_code: {e}");
                        return if e.0.contains("ENV-5 sandbox error") {
                            3
                        } else {
                            2
                        };
                    }
                }
            }
        }

        let mut failed = 0usize;
        for (item, findings) in items.iter().zip(item_findings.iter()) {
            let id = item.get("id").and_then(Value::as_str).unwrap_or("");
            if !findings.is_empty() {
                failed += 1;
                let _ = writeln!(stdout, "FAIL {id}: {}", findings.join("; "));
            } else {
                let _ = writeln!(stdout, "PASS {id}");
            }
        }
        let _ = writeln!(
            stdout,
            "{} of {} items pass",
            items.len() - failed,
            items.len()
        );
        return if failed > 0 { 1 } else { 0 };
    }

    let schema = match load_schema(args.schema.as_deref()) {
        Ok(s) => s,
        Err(e) => {
            let _ = writeln!(stderr, "grade_code: {e}");
            return 2;
        }
    };
    let errors = match bank_findings(&document, &schema) {
        Ok(errs) => errs,
        Err(e) => {
            let _ = writeln!(stderr, "grade_code: {e}");
            return 2;
        }
    };
    if !errors.is_empty() {
        let _ = writeln!(
            stderr,
            "grade_code: the bank does not validate; run --self-test"
        );
        return 2;
    }

    let items = items_of(&document);
    let (Some(out_path), Some(report_path)) = (&args.out, &args.report) else {
        let _ = writeln!(stderr, "grade_code: grading needs --out and --report");
        return 2;
    };
    let has_oos = items
        .iter()
        .any(|i| i.get("stratum").and_then(Value::as_str) == Some("out-of-spec"));
    let abstain_opt = args
        .abstain_arms
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty());
    if abstain_opt.is_none() && has_oos {
        let _ = writeln!(
            stderr,
            "grade_code: the bank has out-of-spec items; give --abstain-arms A,B (the arms in which abstaining is right), or --abstain-arms none"
        );
        return 2;
    }
    let spec = abstain_opt.unwrap_or("none");
    let abstain_arms = parse_abstain_set(spec);

    let raw_path = args.raw.as_ref().unwrap();
    let records = match read_raw(raw_path) {
        Ok(r) => r,
        Err(e) => {
            let _ = writeln!(stderr, "grade_code: cannot read --raw: {e}");
            return 2;
        }
    };

    let record_arms: BTreeSet<String> = records
        .iter()
        .filter_map(|r| {
            r.get("arm")
                .and_then(Value::as_str)
                .map(ToString::to_string)
        })
        .collect();
    for arm in abstain_arms.difference(&record_arms) {
        let _ = writeln!(
            stderr,
            "grade_code: warning: abstain arm '{arm}' appears in no record"
        );
    }

    let mut bank_by_id = BTreeMap::new();
    for item in &items {
        if let Some(id) = item.get("id").and_then(Value::as_str) {
            bank_by_id.insert(id.to_string(), item.clone());
        }
    }

    let mut graded = Vec::with_capacity(records.len());
    for rec in &records {
        let item_id = rec
            .get("item_id")
            .or_else(|| rec.get("id"))
            .and_then(Value::as_str)
            .unwrap_or("");
        if let Some(bank_item) = bank_by_id.get(item_id) {
            match grade_record(
                rec,
                bank_item,
                &prelude_text,
                &abstain_arms,
                scratch_root,
                args.allow_unsandboxed,
            ) {
                Ok(g) => graded.push(g),
                Err(e) => {
                    let _ = writeln!(stderr, "grade_code: {e}");
                    return if e.0.contains("ENV-5 sandbox error") {
                        3
                    } else {
                        2
                    };
                }
            }
        } else {
            let _ = writeln!(stderr, "grade_code: warning: unknown item id '{item_id}'");
            graded.push(json!({
                "item_id": item_id,
                "model": rec.get("model").cloned().unwrap_or(Value::Null),
                "arm": rec.get("arm").cloned().unwrap_or(Value::Null),
                "outcome": "unknown-item",
            }));
        }
    }

    let mut jsonl_text = String::new();
    for g in &graded {
        jsonl_text.push_str(&serde_json::to_string(g).unwrap());
        jsonl_text.push('\n');
    }
    if let Err(e) = fs::write(out_path, jsonl_text) {
        let _ = writeln!(stderr, "grade_code: {e}");
        return 2;
    }
    let report_text = build_report(&args.bank, &graded, &abstain_arms);
    if let Err(e) = fs::write(report_path, report_text) {
        let _ = writeln!(stderr, "grade_code: {e}");
        return 2;
    }

    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for g in &graded {
        let o = g
            .get("outcome")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        *counts.entry(o).or_insert(0) += 1;
    }
    let summary_parts: Vec<String> = counts
        .into_iter()
        .map(|(o, n)| format!("{o} {n}"))
        .collect();
    let _ = writeln!(
        stdout,
        "graded {} records: {}",
        graded.len(),
        summary_parts.join(", ")
    );
    0
}

fn run_rust_check_cli(
    args: &RustCheckArgs,
    scratch_root: Option<&Path>,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    if let Some(ref bank_path) = args.export_preambles {
        let Some(ref out_path) = args.output else {
            let _ = writeln!(stderr, "rust_check: --export-preambles needs -o OUT");
            return 2;
        };
        return export_preambles(
            bank_path,
            out_path,
            args.prelude.as_deref(),
            args.schema.as_deref(),
            stderr,
        );
    }

    let Some(ref item_id) = args.item_id else {
        let _ = writeln!(stderr, "rust_check: give an ITEM_ID or --export-preambles");
        return 2;
    };

    let path = args
        .preambles
        .clone()
        .or_else(|| std::env::var_os("SPEC_EVAL_PREAMBLES").map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("code_preambles.json"));

    let text = match fs::read_to_string(&path) {
        Ok(t) => t,
        Err(e) => {
            let _ = writeln!(
                stderr,
                "rust_check: cannot read preambles {}: {e}",
                path.display()
            );
            return 2;
        }
    };
    let table: Value = match serde_json::from_str(&text) {
        Ok(v) => v,
        Err(e) => {
            let _ = writeln!(
                stderr,
                "rust_check: cannot read preambles {}: {e}",
                path.display()
            );
            return 2;
        }
    };
    let Some(table_obj) = table.as_object() else {
        let _ = writeln!(
            stderr,
            "rust_check: preambles file {} is not a JSON object",
            path.display()
        );
        return 2;
    };
    let Some(entry) = table_obj.get(item_id).and_then(Value::as_object) else {
        let _ = writeln!(stderr, "rust_check: unknown item id {item_id:?}");
        return 2;
    };
    let Some(preamble) = entry.get("preamble").and_then(Value::as_str) else {
        let _ = writeln!(stderr, "rust_check: unknown item id {item_id:?}");
        return 2;
    };

    let code = if let Some(ref c) = args.code {
        c.clone()
    } else if let Some(ref f) = args.file {
        match fs::read_to_string(f) {
            Ok(t) => t,
            Err(e) => {
                let _ = writeln!(stderr, "rust_check: {e}");
                return 2;
            }
        }
    } else {
        let mut buf = String::new();
        if let Err(e) = io::stdin().read_to_string(&mut buf) {
            let _ = writeln!(stderr, "rust_check: {e}");
            return 2;
        }
        buf
    };

    if !have_rustc() {
        let _ = writeln!(stderr, "rust_check: rustc is not installed");
        return 2;
    }

    let full_source = format!("{preamble}\n\n{code}");
    match compile_lib(&full_source, scratch_root) {
        Ok((true, _)) => {
            let _ = writeln!(stdout, "COMPILE_OK");
            0
        }
        Ok((false, diagnostics)) => {
            let _ = writeln!(stdout, "COMPILE_ERROR");
            let _ = writeln!(stdout, "{diagnostics}");
            1
        }
        Err(e) => {
            let _ = writeln!(stderr, "rust_check: {e}");
            2
        }
    }
}
