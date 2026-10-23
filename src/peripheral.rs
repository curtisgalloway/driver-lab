// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Typed peripheral fact semantic checks, D16 subrecord projection, and generated
//! register/field/sequence views (`peripheral.py`, `RT-4`, `BF-IMX-14`).

use crate::records::{anchors, registry_entry_label, Checker, PathElem, SpecFile, SpecRecord};
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};

/// Spec-level registries (`peripheral.py:REGISTRIES`).
pub const REGISTRIES: &[&str] = &[
    "resetTypes",
    "fieldAccessPolicyDefinitions",
    "enumerationDefinitions",
    "registerFiles",
];

fn as_str<'a>(val: &'a Value, key: &str) -> Option<&'a str> {
    val.get(key).and_then(Value::as_str)
}

fn as_array<'a>(val: &'a Value, key: &str) -> Option<&'a Vec<Value>> {
    val.get(key).and_then(Value::as_array)
}

fn as_object<'a>(val: &'a Value, key: &str) -> Option<&'a Map<String, Value>> {
    val.get(key).and_then(Value::as_object)
}

fn parse_int(val: Option<&Value>) -> Option<u128> {
    let v = val?;
    if let Some(u) = v.as_u64() {
        return Some(u128::from(u));
    }
    if let Some(i) = v.as_i64() {
        return u128::try_from(i).ok();
    }
    if let Some(s) = v.as_str() {
        if let Some(hex_str) = s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")) {
            return u128::from_str_radix(hex_str, 16).ok();
        }
        return s.parse::<u128>().ok();
    }
    None
}

fn bit_length(val: u128) -> u64 {
    if val == 0 {
        0
    } else {
        u64::from(128 - val.leading_zeros())
    }
}

/// Yields `(child_value, path)` for all typed peripheral child rows (`peripheral.py:children`).
#[must_use]
pub fn children<'a>(data: &'a Value, base: &[PathElem]) -> Vec<(&'a Value, Vec<PathElem>)> {
    let mut out = Vec::new();
    if let Some(payload) = as_object(data, "data") {
        if let Some(fields) = payload.get("fields").and_then(Value::as_array) {
            for (i, field) in fields.iter().enumerate() {
                let mut path = base.to_vec();
                path.push(PathElem::Key("data".to_string()));
                path.push(PathElem::Key("fields".to_string()));
                path.push(PathElem::Index(i));
                out.push((field, path));
            }
        }
        if let Some(layout_fields) = payload.get("layout").and_then(|v| as_array(v, "fields")) {
            for (i, field) in layout_fields.iter().enumerate() {
                let mut path = base.to_vec();
                path.push(PathElem::Key("data".to_string()));
                path.push(PathElem::Key("layout".to_string()));
                path.push(PathElem::Key("fields".to_string()));
                path.push(PathElem::Index(i));
                out.push((field, path));
            }
        }
        if let Some(sequence) = payload.get("sequence").and_then(Value::as_object) {
            for group in &["steps", "order"] {
                if let Some(arr) = sequence.get(*group).and_then(Value::as_array) {
                    for (i, row) in arr.iter().enumerate() {
                        let mut path = base.to_vec();
                        path.push(PathElem::Key("data".to_string()));
                        path.push(PathElem::Key("sequence".to_string()));
                        path.push(PathElem::Key((*group).to_string()));
                        path.push(PathElem::Index(i));
                        out.push((row, path));
                    }
                }
            }
        }
    }
    out
}

/// D16: supported register fields, layout fields, and sequence steps have verdict sub-keys (`peripheral.py:subrecords`).
#[must_use]
pub fn subrecords<'a>(data: &'a Value, base: &[PathElem]) -> Vec<(&'a Value, Vec<PathElem>)> {
    let mut out = Vec::new();
    let has_register_or_layout = data
        .get("data")
        .and_then(Value::as_object)
        .is_some_and(|d| d.contains_key("register") || d.contains_key("layout"));
    for (row, path) in children(data, base) {
        if row.get("support").is_some() && path.len() >= 2 {
            let p_2 = &path[path.len() - 2];
            let is_fields = matches!(p_2, PathElem::Key(k) if k == "fields");
            let is_steps = matches!(p_2, PathElem::Key(k) if k == "steps");
            if is_steps || (is_fields && has_register_or_layout) {
                out.push((row, path));
            }
        }
    }
    out
}

/// D16 projection: independent children, effective requirement, and parent identity (`peripheral.py:basis_data`).
#[must_use]
pub fn basis_data(checker: &Checker, rec: &SpecRecord) -> Value {
    let parent_data = rec
        .parent_id
        .as_deref()
        .and_then(|pid| checker.files[rec.file_idx].get_record(pid))
        .map(|p| &p.data);
    crate::records::basis_data(&rec.data, parent_data)
}

/// Returns `true` when `path` is owned by `rec` rather than a separately supported subrecord (`peripheral.py:owns_citation`).
#[must_use]
pub fn owns_citation(rec: &SpecRecord, path: &[PathElem]) -> bool {
    crate::records::owns_citation(&rec.data, &rec.path, path)
}

/// Computes the referenced registries for `rec` (`peripheral.py:referenced_registries`).
pub fn referenced_registries(
    rec: &SpecRecord,
    file: &SpecFile,
) -> Result<Vec<(String, String, Value, Vec<PathElem>)>, String> {
    crate::records::referenced_registries(rec, file)
}

/// Checks `requirement` (`hw-required`, `comment-explained`) on a fact or child row (`peripheral.py:requirement`, `BF-IMX-14`).
pub fn requirement(
    checker: &mut Checker,
    file_idx: usize,
    row: &Value,
    path: &[PathElem],
    inherited: Option<&Value>,
    inherited_support: Option<&Value>,
) {
    let value = row.get("requirement").or(inherited);
    let support_val = row.get("support").or(inherited_support);

    if let Some(req) = value.and_then(Value::as_str) {
        if req == "hw-required" {
            let has_doc = support_val.and_then(Value::as_array).is_some_and(|arr| {
                arr.iter().any(|entry| {
                    matches!(
                        as_str(entry, "class"),
                        Some("databook" | "datasheet" | "errata" | "appnote" | "standard" | "doc")
                    )
                })
            });
            if !has_doc {
                let mut p = path.to_vec();
                p.push(PathElem::Key("requirement".to_string()));
                checker.add_file(
                    file_idx,
                    &p,
                    "hw-required needs document-class support",
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }
        if req == "comment-explained" {
            let has_comment = support_val.and_then(Value::as_array).is_some_and(|arr| {
                arr.iter().any(|entry| {
                    let cls = as_str(entry, "class").unwrap_or("");
                    if matches!(cls, "src" | "DT" | "rtl") {
                        as_array(entry, "anchors").is_some_and(|anchors| {
                            anchors.iter().any(|a| a.get("comment").is_some())
                        })
                    } else {
                        false
                    }
                })
            });
            if !has_comment {
                let mut p = path.to_vec();
                p.push(PathElem::Key("requirement".to_string()));
                checker.add_file(
                    file_idx,
                    &p,
                    "comment-explained needs a comment anchor",
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }
    }
}

/// Checks spec-level registries (`peripheral.py:check_registries`).
/// Note: `Checker::check_file` already checks `inference`/`emulated` support and `check_support` on registries;
/// this function performs the remainingenumeration and `unaffectedBy` reset-type checks.
pub fn check_registries(checker: &mut Checker, file_idx: usize, _cited: &mut HashSet<String>) {
    let data = checker.files[file_idx].data.clone();
    for &group in REGISTRIES {
        let Some(arr) = data.get(group).and_then(Value::as_array) else {
            continue;
        };
        for (i, entry) in arr.iter().enumerate() {
            let path = vec![PathElem::from(group), PathElem::Index(i)];
            let name = as_str(entry, "name").unwrap_or("");
            let what = format!("{} '{name}'", registry_entry_label(group));
            if group == "enumerationDefinitions" {
                check_enumeration(checker, file_idx, &what, entry, &path);
            }
            if group == "fieldAccessPolicyDefinitions" {
                if let Some(unaff) = as_array(entry, "unaffectedBy") {
                    for (j, reset_val) in unaff.iter().enumerate() {
                        let Some(reset) = reset_val.as_str() else {
                            continue;
                        };
                        let has_reset = checker.files[file_idx]
                            .registries
                            .get("resetTypes")
                            .is_some_and(|m| m.contains_key(reset));
                        if !has_reset {
                            let mut p = path.clone();
                            p.push(PathElem::from("unaffectedBy"));
                            p.push(PathElem::Index(j));
                            checker.reject(
                                file_idx,
                                &p,
                                format!(
                                    "{what}: reset type '{reset}' is not in this file's resetTypes"
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

/// Runs peripheral semantic checks on `file_idx` (`peripheral.py:check_file`).
pub fn check_file(checker: &mut Checker, file_idx: usize) {
    let mut areas = HashSet::new();
    let file_data = checker.files[file_idx].data.clone();

    if let Some(areas_arr) = as_array(&file_data, "areas") {
        for (i, row) in areas_arr.iter().enumerate() {
            if let Some(area) = as_str(row, "area") {
                if !areas.insert(area.to_string()) {
                    checker.add_file(
                        file_idx,
                        &[
                            PathElem::Key("areas".to_string()),
                            PathElem::Index(i),
                            PathElem::Key("area".to_string()),
                        ],
                        "area is listed twice",
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }
    }

    if let Some(facts) = as_array(&file_data, "facts") {
        for (i, fact) in facts.iter().enumerate() {
            let path = vec![PathElem::Key("facts".to_string()), PathElem::Index(i)];
            requirement(checker, file_idx, fact, &path, None, None);

            let payload = fact.get("data");
            let register = payload.and_then(|p| p.get("register"));

            if let Some(reg) = register {
                if let (Some(reset_val), Some(width)) = (
                    parse_int(reg.get("reset")),
                    reg.get("width").and_then(Value::as_u64),
                ) {
                    if bit_length(reset_val) > width {
                        let mut p = path.clone();
                        p.push(PathElem::Key("data".to_string()));
                        p.push(PathElem::Key("register".to_string()));
                        p.push(PathElem::Key("reset".to_string()));
                        checker.add_file(
                            file_idx,
                            &p,
                            "reset exceeds register width",
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }
            }

            let mut seen = HashSet::new();
            for (row, at) in children(fact, &path) {
                requirement(
                    checker,
                    file_idx,
                    row,
                    &at,
                    fact.get("requirement"),
                    fact.get("support"),
                );
                if let Some(id) = as_str(row, "id") {
                    let at_minus_2 = if at.len() >= 2 {
                        match &at[at.len() - 2] {
                            PathElem::Key(k) => k.clone(),
                            PathElem::Index(_) => String::new(),
                        }
                    } else {
                        String::new()
                    };
                    let key = (at_minus_2, id.to_string());
                    if !seen.insert(key) {
                        let mut p = at.clone();
                        p.push(PathElem::Key("id".to_string()));
                        checker.add_file(
                            file_idx,
                            &p,
                            "field or step id is listed twice",
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }

                if let Some(bits) = as_array(row, "bits") {
                    if at.len() >= 3
                        && matches!(&at[at.len() - 3], PathElem::Key(k) if k == "data")
                        && bits.len() >= 2
                    {
                        if let (Some(low), Some(high)) = (bits[0].as_u64(), bits[1].as_u64()) {
                            let w = register
                                .and_then(|r| r.get("width"))
                                .and_then(Value::as_u64);
                            if low > high || w.is_some_and(|w| high >= w) {
                                let mut p = at.clone();
                                p.push(PathElem::Key("bits".to_string()));
                                checker.add_file(
                                    file_idx,
                                    &p,
                                    "bits must be ordered and inside register width",
                                    "error",
                                    false,
                                    true,
                                    true,
                                );
                            }
                        }
                    }
                }

                if row.get("offset").is_some() {
                    if let Some(layout) = payload.and_then(|p| p.get("layout")) {
                        if let (Some(off), Some(size), Some(layout_size)) = (
                            parse_int(row.get("offset")),
                            row.get("size").and_then(Value::as_u64).map(u128::from),
                            layout.get("size").and_then(Value::as_u64).map(u128::from),
                        ) {
                            if off + size > layout_size {
                                let mut p = at.clone();
                                p.push(PathElem::Key("offset".to_string()));
                                checker.add_file(
                                    file_idx,
                                    &p,
                                    "field exceeds layout size",
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

            if let Some(seq) = payload.and_then(|p| p.get("sequence")) {
                let mut steps: Vec<String> = Vec::new();
                let mut steps_set: HashSet<String> = HashSet::new();
                if let Some(steps_arr) = as_array(seq, "steps") {
                    for row in steps_arr {
                        if let Some(sid) = as_str(row, "id") {
                            if steps_set.insert(sid.to_string()) {
                                steps.push(sid.to_string());
                            }
                        }
                    }
                }
                let mut edges: HashMap<String, Vec<String>> =
                    steps.iter().map(|s| (s.clone(), Vec::new())).collect();
                let mut seen_edges: HashSet<(String, String)> = HashSet::new();
                if let Some(order_arr) = as_array(seq, "order") {
                    for (j, edge) in order_arr.iter().enumerate() {
                        let epath = vec![
                            PathElem::from("facts"),
                            PathElem::Index(i),
                            PathElem::from("data"),
                            PathElem::from("sequence"),
                            PathElem::from("order"),
                            PathElem::Index(j),
                        ];
                        for key in ["before", "after"] {
                            if let Some(val) = as_str(edge, key) {
                                if !steps_set.contains(val) {
                                    let mut p = epath.clone();
                                    p.push(PathElem::from(key));
                                    checker.add_file(
                                        file_idx,
                                        &p,
                                        "order references unknown step",
                                        "error",
                                        false,
                                        true,
                                        true,
                                    );
                                }
                            }
                        }
                        let before = as_str(edge, "before").unwrap_or("");
                        let after = as_str(edge, "after").unwrap_or("");
                        if !before.is_empty() && before == after {
                            checker.add_file(
                                file_idx,
                                &epath,
                                "step cannot be ordered before itself",
                                "error",
                                false,
                                true,
                                true,
                            );
                        }
                        let pair = (before.to_string(), after.to_string());
                        if !seen_edges.insert(pair) {
                            checker.add_file(
                                file_idx,
                                &epath,
                                "order edge is listed twice",
                                "error",
                                false,
                                true,
                                true,
                            );
                        }
                        if steps_set.contains(before) && steps_set.contains(after) {
                            edges
                                .entry(before.to_string())
                                .or_default()
                                .push(after.to_string());
                        }
                    }
                }

                let mut state: HashMap<String, u8> = HashMap::new();
                fn visit(
                    node: &str,
                    edges: &HashMap<String, Vec<String>>,
                    state: &mut HashMap<String, u8>,
                ) -> bool {
                    match state.get(node).copied() {
                        Some(1) => return true,
                        Some(2) => return false,
                        _ => {}
                    }
                    state.insert(node.to_string(), 1);
                    if let Some(nexts) = edges.get(node) {
                        for nxt in nexts {
                            if visit(nxt, edges, state) {
                                return true;
                            }
                        }
                    }
                    state.insert(node.to_string(), 2);
                    false
                }
                for step in &steps {
                    if visit(step, &edges, &mut state) {
                        let mut p = path.clone();
                        p.push(PathElem::from("data"));
                        p.push(PathElem::from("sequence"));
                        p.push(PathElem::from("order"));
                        checker.add_file(
                            file_idx,
                            &p,
                            "sequence order has a cycle",
                            "error",
                            false,
                            true,
                            true,
                        );
                        break;
                    }
                }
            }

            if as_str(fact, "section") == Some("target") {
                for (anchor, apath) in anchors(fact, &path) {
                    if let Some(repo) = as_str(&anchor, "repo") {
                        let is_non_target = checker.files[file_idx]
                            .repos
                            .get(repo)
                            .is_some_and(|(r_entry, _)| as_str(r_entry, "role") != Some("target"));
                        if is_non_target {
                            let mut p = apath;
                            p.push(PathElem::from("repo"));
                            checker.add_file(
                                file_idx,
                                &p,
                                "target-section anchor must cite a target-role repo",
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

    check_registers(checker, file_idx);
    check_layouts(checker, file_idx);
    check_sequences(checker, file_idx);
}

fn field_index(data: &Value) -> HashMap<(String, String), (Value, Value)> {
    let mut out = HashMap::new();
    if let Some(facts) = as_array(data, "facts") {
        for fact in facts {
            let payload = fact.get("data");
            if let Some(register) = payload.and_then(|p| p.get("register")) {
                if let Some(fields) = payload.and_then(|p| as_array(p, "fields")) {
                    if let Some(fact_id) = as_str(fact, "id") {
                        for field in fields {
                            if let Some(field_id) = as_str(field, "id") {
                                out.insert(
                                    (fact_id.to_string(), field_id.to_string()),
                                    (field.clone(), register.clone()),
                                );
                            }
                        }
                    }
                }
            }
        }
    }
    out
}

/// Checks registers and bitfields (`peripheral.py:check_registers`).
pub fn check_registers(checker: &mut Checker, file_idx: usize) {
    let file_data = checker.files[file_idx].data.clone();
    let index = field_index(&file_data);
    let mut by_offset: HashMap<(Option<String>, u128), (String, String)> = HashMap::new();

    let Some(facts) = as_array(&file_data, "facts") else {
        return;
    };
    for (i, fact) in facts.iter().enumerate() {
        let Some(payload) = fact.get("data") else {
            continue;
        };
        let Some(register) = payload.get("register") else {
            continue;
        };
        let rpath = vec![
            PathElem::from("facts"),
            PathElem::Index(i),
            PathElem::from("data"),
            PathElem::from("register"),
        ];
        check_register(checker, file_idx, register, &rpath);

        let name = as_str(register, "name").unwrap_or("");
        let rf = as_str(register, "registerFile").map(ToString::to_string);
        if register.get("aliasOf").is_none() {
            if let Some(off) = parse_int(register.get("offset")) {
                let key = (rf, off);
                if let Some((prev_name, _)) = by_offset.get(&key) {
                    if prev_name != name {
                        let off_str = as_str(register, "offset").unwrap_or("");
                        let mut p = rpath.clone();
                        p.push(PathElem::from("offset"));
                        checker.add_file(
                            file_idx,
                            &p,
                            format!(
                                "registers '{prev_name}' and '{name}' share offset {off_str} without a distinct registerFile or alias"
                            ),
                            "warning",
                            false,
                            true,
                            true,
                        );
                    }
                } else {
                    by_offset.insert(
                        key,
                        (
                            name.to_string(),
                            as_str(fact, "id").unwrap_or("").to_string(),
                        ),
                    );
                }
            }
        }

        let mut field_ranges: Vec<(u64, u64, String, Option<String>)> = Vec::new();
        if let Some(fields) = as_array(payload, "fields") {
            for (j, field) in fields.iter().enumerate() {
                let fpath = vec![
                    PathElem::from("facts"),
                    PathElem::Index(i),
                    PathElem::from("data"),
                    PathElem::from("fields"),
                    PathElem::Index(j),
                ];
                check_field(checker, file_idx, fact, register, field, &fpath, &index);
                if let Some(bits) = as_array(field, "bits") {
                    if bits.len() >= 2 {
                        if let (Some(low), Some(high)) = (bits[0].as_u64(), bits[1].as_u64()) {
                            let when = as_str(field, "when").map(ToString::to_string);
                            let fid = as_str(field, "id").unwrap_or("").to_string();
                            for (pl, ph, pid, pwhen) in &field_ranges {
                                if !(high < *pl || low > *ph) {
                                    let mut p = fpath.clone();
                                    p.push(PathElem::from("bits"));
                                    if when.is_some() && &when == pwhen {
                                        checker.add_file(
                                            file_idx,
                                            &p,
                                            format!(
                                                "fields '{pid}' and '{fid}' overlap on bits [{low}, {high}] under the same condition"
                                            ),
                                            "error",
                                            false,
                                            true,
                                            true,
                                        );
                                    } else if when.is_none() || pwhen.is_none() {
                                        checker.add_file(
                                            file_idx,
                                            &p,
                                            format!(
                                                "fields '{pid}' and '{fid}' overlap on bits [{low}, {high}] without a condition"
                                            ),
                                            "error",
                                            false,
                                            true,
                                            true,
                                        );
                                    }
                                }
                            }
                            field_ranges.push((low, high, fid, when));
                        }
                    }
                }
            }
        }
    }
}

fn check_register(checker: &mut Checker, file_idx: usize, register: &Value, rpath: &[PathElem]) {
    let name = as_str(register, "name").unwrap_or("");
    if let Some(access) = as_str(register, "access") {
        let legacy = ["ro", "wo", "rw", "w1c", "w1s", "rc"];
        if legacy.contains(&access) {
            let mut p = rpath.to_vec();
            p.push(PathElem::from("access"));
            checker.add_file(
                file_idx,
                &p,
                format!(
                    "register '{name}': access '{access}' is a legacy value; prefer IP-XACT access and field policies"
                ),
                "warning",
                false,
                true,
                true,
            );
        }
    }
    if let Some(rf) = as_str(register, "registerFile") {
        let rf_opt = checker.files[file_idx]
            .registries
            .get("registerFiles")
            .and_then(|m| m.get(rf))
            .cloned();
        let Some((rf_entry, rf_path)) = rf_opt else {
            let mut p = rpath.to_vec();
            p.push(PathElem::from("registerFile"));
            checker.reject(
                file_idx,
                &p,
                format!(
                    "register '{name}': register file '{rf}' is not in this file's registerFiles"
                ),
                true,
            );
            return;
        };
        let width_bytes = register
            .get("width")
            .and_then(Value::as_u64)
            .map(|w| u128::from(w / 8))
            .unwrap_or(0);
        if let (Some(off), Some(rf_size)) = (
            parse_int(register.get("offset")),
            parse_int(rf_entry.get("size")),
        ) {
            if off + width_bytes > rf_size {
                let mut p = rpath.to_vec();
                p.push(PathElem::from("offset"));
                checker.add_file(
                    file_idx,
                    &p,
                    format!("register '{name}' exceeds registerFile '{rf}' size"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
            if let Some(stride) = parse_int(rf_entry.get("stride")) {
                let count = rf_entry.get("count").and_then(Value::as_u64).unwrap_or(1);
                if count > 1 && rf_size > stride {
                    let mut p = rf_path;
                    p.push(PathElem::from("size"));
                    checker.add_file(
                        file_idx,
                        &p,
                        format!("registerFile '{rf}': size exceeds stride"),
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

fn check_enumeration(
    checker: &mut Checker,
    file_idx: usize,
    what: &str,
    entry: &Value,
    path: &[PathElem],
) {
    let width = entry.get("width").and_then(Value::as_u64);
    let mut values_seen = HashSet::new();
    let mut names_seen = HashSet::new();
    let (val_key, values_opt) = if let Some(v) = as_array(entry, "enumeratedValues") {
        ("enumeratedValues", Some(v))
    } else {
        ("values", as_array(entry, "values"))
    };
    if let Some(values) = values_opt {
        for (i, row) in values.iter().enumerate() {
            let mut vpath = path.to_vec();
            vpath.push(PathElem::from(val_key));
            vpath.push(PathElem::Index(i));
            if let Some(val) = parse_int(row.get("value")) {
                let val_str = as_str(row, "value").unwrap_or("");
                if let Some(w) = width {
                    if bit_length(val) > w {
                        let mut p = vpath.clone();
                        p.push(PathElem::from("value"));
                        checker.add_file(
                            file_idx,
                            &p,
                            format!("{what}: value {val_str} exceeds width {w}"),
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }
                if !values_seen.insert(val) {
                    let mut p = vpath.clone();
                    p.push(PathElem::from("value"));
                    checker.add_file(
                        file_idx,
                        &p,
                        format!("{what}: value {val_str} is listed twice"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
            if let Some(rname) = as_str(row, "name") {
                if !names_seen.insert(rname.to_string()) {
                    let mut p = vpath;
                    p.push(PathElem::from("name"));
                    checker.add_file(
                        file_idx,
                        &p,
                        format!("{what}: name '{rname}' is listed twice"),
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

fn check_field(
    checker: &mut Checker,
    file_idx: usize,
    fact: &Value,
    register: &Value,
    field: &Value,
    fpath: &[PathElem],
    index: &HashMap<(String, String), (Value, Value)>,
) {
    let fid = as_str(field, "id").unwrap_or("");
    let what = format!("field '{fid}'");
    let bits = as_array(field, "bits");
    let fwidth = bits.and_then(|b| {
        if b.len() >= 2 {
            let low = b[0].as_u64()?;
            let high = b[1].as_u64()?;
            if high >= low {
                Some(high - low + 1)
            } else {
                None
            }
        } else {
            None
        }
    });

    if let (Some(fw), Some(reset_val)) = (fwidth, parse_int(field.get("reset"))) {
        if bit_length(reset_val) > fw {
            let mut p = fpath.to_vec();
            p.push(PathElem::from("reset"));
            checker.add_file(
                file_idx,
                &p,
                format!("{what}: reset exceeds field width"),
                "error",
                false,
                true,
                true,
            );
        }
    }

    let mut seen_resets = HashSet::new();
    if let Some(resets) = as_array(field, "resets") {
        for (k, r) in resets.iter().enumerate() {
            let mut rpath = fpath.to_vec();
            rpath.push(PathElem::from("resets"));
            rpath.push(PathElem::Index(k));
            if let (Some(fw), Some(rval)) = (fwidth, parse_int(r.get("value"))) {
                if bit_length(rval) > fw {
                    let mut p = rpath.clone();
                    p.push(PathElem::from("value"));
                    checker.add_file(
                        file_idx,
                        &p,
                        format!("{what}: reset value exceeds field width"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
            if let (Some(fw), Some(mval)) = (fwidth, parse_int(r.get("mask"))) {
                if bit_length(mval) > fw {
                    let mut p = rpath.clone();
                    p.push(PathElem::from("mask"));
                    checker.add_file(
                        file_idx,
                        &p,
                        format!("{what}: reset mask exceeds field width"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
            if let Some(rt) = as_str(r, "resetTypeRef") {
                let has_rt = checker.files[file_idx]
                    .registries
                    .get("resetTypes")
                    .is_some_and(|m| m.contains_key(rt));
                if !has_rt {
                    let mut p = rpath.clone();
                    p.push(PathElem::from("resetTypeRef"));
                    checker.reject(
                        file_idx,
                        &p,
                        format!("{what}: reset type '{rt}' is not in this file's resetTypes"),
                        true,
                    );
                }
                if !seen_resets.insert(rt.to_string()) {
                    let mut p = rpath;
                    p.push(PathElem::from("resetTypeRef"));
                    checker.add_file(
                        file_idx,
                        &p,
                        format!("{what}: resetTypeRef '{rt}' is listed twice"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }
    }

    if let Some(unaff) = as_array(field, "unaffectedBy") {
        for (k, rt_val) in unaff.iter().enumerate() {
            let Some(rt) = rt_val.as_str() else {
                continue;
            };
            let mut upath = fpath.to_vec();
            upath.push(PathElem::from("unaffectedBy"));
            upath.push(PathElem::Index(k));
            let has_rt = checker.files[file_idx]
                .registries
                .get("resetTypes")
                .is_some_and(|m| m.contains_key(rt));
            if !has_rt {
                checker.reject(
                    file_idx,
                    &upath,
                    format!("{what}: reset type '{rt}' is not in this file's resetTypes"),
                    true,
                );
            }
            if seen_resets.contains(rt) {
                checker.add_file(
                    file_idx,
                    &upath,
                    format!("{what}: reset type '{rt}' is in both resets and unaffectedBy"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }
    }

    if let Some(ap) = as_str(field, "fieldAccessPolicyDefinitionRef") {
        let has_ap = checker.files[file_idx]
            .registries
            .get("fieldAccessPolicyDefinitions")
            .is_some_and(|m| m.contains_key(ap));
        if !has_ap {
            let mut p = fpath.to_vec();
            p.push(PathElem::from("fieldAccessPolicyDefinitionRef"));
            checker.reject(
                file_idx,
                &p,
                format!(
                    "{what}: access policy '{ap}' is not in this file's fieldAccessPolicyDefinitions"
                ),
                true,
            );
        }
    }

    if let Some(ed) = as_str(field, "enumerationDefinitionRef") {
        let ed_opt = checker.files[file_idx]
            .registries
            .get("enumerationDefinitions")
            .and_then(|m| m.get(ed))
            .cloned();
        if let Some((ed_entry, _)) = ed_opt {
            if let Some(fw) = fwidth {
                if let Some(ew) = ed_entry.get("width").and_then(Value::as_u64) {
                    if ew > fw {
                        let mut p = fpath.to_vec();
                        p.push(PathElem::from("enumerationDefinitionRef"));
                        checker.add_file(
                            file_idx,
                            &p,
                            format!(
                                "{what}: enumeration '{ed}' width {ew} exceeds field width {fw}"
                            ),
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }
                if let Some(vals) = as_array(&ed_entry, "enumeratedValues")
                    .or_else(|| as_array(&ed_entry, "values"))
                {
                    for row in vals {
                        if let Some(val) = parse_int(row.get("value")) {
                            if bit_length(val) > fw {
                                let val_str = as_str(row, "value").unwrap_or("");
                                let mut p = fpath.to_vec();
                                p.push(PathElem::from("enumerationDefinitionRef"));
                                checker.add_file(
                                    file_idx,
                                    &p,
                                    format!(
                                        "{what}: enumeration '{ed}' value {val_str} exceeds field width {fw}"
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
        } else {
            let mut p = fpath.to_vec();
            p.push(PathElem::from("enumerationDefinitionRef"));
            checker.reject(
                file_idx,
                &p,
                format!("{what}: enumeration '{ed}' is not in this file's enumerationDefinitions"),
                true,
            );
        }
    }

    if field.get("enumeratedValues").is_some() {
        let mut ev_map = Map::new();
        if let Some(fw) = fwidth {
            ev_map.insert("width".to_string(), json!(fw));
        }
        ev_map.insert(
            "values".to_string(),
            field.get("enumeratedValues").cloned().unwrap_or(json!([])),
        );
        check_enumeration(checker, file_idx, &what, &Value::Object(ev_map), fpath);
    }

    if let Some(table) = field.get("table") {
        let mut tpath = fpath.to_vec();
        tpath.push(PathElem::from("table"));
        check_table(checker, file_idx, &what, table, fwidth, &tpath);
    }

    if let Some(constraints) = as_array(field, "constraints") {
        for (k, c) in constraints.iter().enumerate() {
            let mut cpath = fpath.to_vec();
            cpath.push(PathElem::from("constraints"));
            cpath.push(PathElem::Index(k));
            check_constraint(checker, file_idx, &what, c, fwidth, &cpath);
        }
    }

    if let Some(alias) = as_str(field, "aliasOf") {
        let mut apath = fpath.to_vec();
        apath.push(PathElem::from("aliasOf"));
        let rest = alias.strip_prefix('#').unwrap_or(alias);
        if let Some((reg_id, target_fid)) = rest.split_once('.') {
            if let Some((other_field, other_reg)) =
                index.get(&(reg_id.to_string(), target_fid.to_string()))
            {
                let fact_id = as_str(fact, "id").unwrap_or("");
                if reg_id == fact_id && target_fid == fid {
                    checker.add_file(
                        file_idx,
                        &apath,
                        format!("{what}: aliasOf names the field itself"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
                let ow = as_array(other_field, "bits").and_then(|ob| {
                    if ob.len() >= 2 {
                        Some(ob[1].as_u64()? - ob[0].as_u64()? + 1)
                    } else {
                        None
                    }
                });
                if let (Some(fw), Some(other_w)) = (fwidth, ow) {
                    if fw != other_w {
                        checker.add_file(
                            file_idx,
                            &apath,
                            format!("{what}: aliasOf '{alias}' has width {other_w}, not {fw}"),
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }
                if register.get("offset") == other_reg.get("offset")
                    && register.get("registerFile") == other_reg.get("registerFile")
                    && field.get("bits") == other_field.get("bits")
                    && reg_id == fact_id
                {
                    checker.add_file(
                        file_idx,
                        &apath,
                        format!("{what}: aliasOf points to the same register and bits"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            } else {
                checker.add_file(
                    file_idx,
                    &apath,
                    format!("{what}: aliasOf '{alias}' resolves to no register field"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }
    }
}

fn check_table(
    checker: &mut Checker,
    file_idx: usize,
    what: &str,
    table: &Value,
    fwidth: Option<u64>,
    tpath: &[PathElem],
) {
    let mut keys_seen = HashSet::new();
    if let Some(entries) = as_array(table, "entries") {
        for (i, row) in entries.iter().enumerate() {
            let mut rpath = tpath.to_vec();
            rpath.push(PathElem::from("entries"));
            rpath.push(PathElem::Index(i));
            if let Some(key) = parse_int(row.get("key")) {
                let key_str = as_str(row, "key").unwrap_or("");
                if let Some(fw) = fwidth {
                    if bit_length(key) > fw {
                        let mut p = rpath.clone();
                        p.push(PathElem::from("key"));
                        checker.add_file(
                            file_idx,
                            &p,
                            format!("{what}: table key {key_str} exceeds field width {fw}"),
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                }
                if !keys_seen.insert(key) {
                    let mut p = rpath;
                    p.push(PathElem::from("key"));
                    checker.add_file(
                        file_idx,
                        &p,
                        format!("{what}: table key {key_str} is listed twice"),
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

fn check_constraint(
    checker: &mut Checker,
    file_idx: usize,
    what: &str,
    c: &Value,
    fwidth: Option<u64>,
    cpath: &[PathElem],
) {
    let min_v = parse_int(c.get("min"));
    let max_v = parse_int(c.get("max"));
    if let (Some(mn), Some(mx)) = (min_v, max_v) {
        if mn > mx {
            checker.add_file(
                file_idx,
                cpath,
                format!("{what}: constraint min exceeds max"),
                "error",
                false,
                true,
                true,
            );
        }
    }
    if let Some(fw) = fwidth {
        for key in ["min", "max"] {
            if let Some(val) = parse_int(c.get(key)) {
                if bit_length(val) > fw {
                    let mut p = cpath.to_vec();
                    p.push(PathElem::from(key));
                    checker.add_file(
                        file_idx,
                        &p,
                        format!("{what}: constraint {key} exceeds field width {fw}"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }
        if let Some(allowed) = as_array(c, "allowed") {
            for (j, item) in allowed.iter().enumerate() {
                if let Some(val) = parse_int(Some(item)) {
                    if bit_length(val) > fw {
                        let mut p = cpath.to_vec();
                        p.push(PathElem::from("allowed"));
                        p.push(PathElem::Index(j));
                        checker.add_file(
                            file_idx,
                            &p,
                            format!("{what}: allowed value exceeds field width {fw}"),
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

/// Checks layout fields (`peripheral.py:check_layouts`).
pub fn check_layouts(checker: &mut Checker, file_idx: usize) {
    let file_data = checker.files[file_idx].data.clone();
    let Some(facts) = as_array(&file_data, "facts") else {
        return;
    };
    for (i, fact) in facts.iter().enumerate() {
        let Some(layout) = fact.get("data").and_then(|d| d.get("layout")) else {
            continue;
        };
        let mut ranges: Vec<(u128, u128, u64, u64, String, Option<String>)> = Vec::new();
        if let Some(fields) = as_array(layout, "fields") {
            for (j, field) in fields.iter().enumerate() {
                let fpath = vec![
                    PathElem::from("facts"),
                    PathElem::Index(i),
                    PathElem::from("data"),
                    PathElem::from("layout"),
                    PathElem::from("fields"),
                    PathElem::Index(j),
                ];
                let Some(off) = parse_int(field.get("offset")) else {
                    continue;
                };
                let Some(size) = field.get("size").and_then(Value::as_u64) else {
                    continue;
                };
                let size_u128 = u128::from(size);
                let fid = as_str(field, "id").unwrap_or("").to_string();
                let when = as_str(field, "when").map(ToString::to_string);
                let (bl, bh) = if let Some(bits) = as_array(field, "bits") {
                    let low = bits.first().and_then(Value::as_u64).unwrap_or(0);
                    let high = bits.get(1).and_then(Value::as_u64).unwrap_or(0);
                    if low > high || high >= size * 8 {
                        let mut p = fpath.clone();
                        p.push(PathElem::from("bits"));
                        checker.add_file(
                            file_idx,
                            &p,
                            "bits must be ordered and inside field size",
                            "error",
                            false,
                            true,
                            true,
                        );
                    }
                    (low, high)
                } else {
                    (0, size * 8 - 1)
                };

                let fwidth = bh.saturating_sub(bl) + 1;
                let what = format!("layout field '{fid}'");
                if let Some(ed) = as_str(field, "enumerationDefinitionRef") {
                    let ed_opt = checker.files[file_idx]
                        .registries
                        .get("enumerationDefinitions")
                        .and_then(|m| m.get(ed))
                        .cloned();
                    if let Some((ed_entry, _)) = ed_opt {
                        if let Some(ew) = ed_entry.get("width").and_then(Value::as_u64) {
                            if ew > fwidth {
                                let mut p = fpath.clone();
                                p.push(PathElem::from("enumerationDefinitionRef"));
                                checker.add_file(
                                    file_idx,
                                    &p,
                                    format!(
                                        "{what}: enumeration '{ed}' width {ew} exceeds field width {fwidth}"
                                    ),
                                    "error",
                                    false,
                                    true,
                                    true,
                                );
                            }
                        }
                        if let Some(vals) = as_array(&ed_entry, "enumeratedValues")
                            .or_else(|| as_array(&ed_entry, "values"))
                        {
                            for row in vals {
                                if let Some(val) = parse_int(row.get("value")) {
                                    if bit_length(val) > fwidth {
                                        let val_str = as_str(row, "value").unwrap_or("");
                                        let mut p = fpath.clone();
                                        p.push(PathElem::from("enumerationDefinitionRef"));
                                        checker.add_file(
                                            file_idx,
                                            &p,
                                            format!(
                                                "{what}: enumeration '{ed}' value {val_str} exceeds field width {fwidth}"
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
                    } else {
                        let mut p = fpath.clone();
                        p.push(PathElem::from("enumerationDefinitionRef"));
                        checker.reject(
                            file_idx,
                            &p,
                            format!(
                                "{what}: enumeration '{ed}' is not in this file's enumerationDefinitions"
                            ),
                            true,
                        );
                    }
                }
                if field.get("enumeratedValues").is_some() {
                    let mut ev_map = Map::new();
                    ev_map.insert("width".to_string(), json!(fwidth));
                    ev_map.insert(
                        "values".to_string(),
                        field.get("enumeratedValues").cloned().unwrap_or(json!([])),
                    );
                    check_enumeration(checker, file_idx, &what, &Value::Object(ev_map), &fpath);
                }

                for (poff, psize, pbl, pbh, pid, pwhen) in &ranges {
                    let bytes_overlap = !(off + size_u128 <= *poff || *poff + *psize <= off);
                    if !bytes_overlap {
                        continue;
                    }
                    let bits_overlap = if off == *poff && size_u128 == *psize {
                        !(bh < *pbl || bl > *pbh)
                    } else {
                        true
                    };
                    if bits_overlap {
                        if when.is_some() && &when == pwhen {
                            let mut p = fpath.clone();
                            p.push(PathElem::from("offset"));
                            checker.add_file(
                                file_idx,
                                &p,
                                format!(
                                    "layout fields '{pid}' and '{fid}' overlap under the same condition"
                                ),
                                "error",
                                false,
                                true,
                                true,
                            );
                        } else if when.is_none() || pwhen.is_none() {
                            let mut p = fpath.clone();
                            p.push(PathElem::from("offset"));
                            checker.add_file(
                                file_idx,
                                &p,
                                format!(
                                    "layout fields '{pid}' and '{fid}' overlap without a condition"
                                ),
                                "error",
                                false,
                                true,
                                true,
                            );
                        }
                    }
                }
                ranges.push((off, size_u128, bl, bh, fid, when));
            }
        }
    }
}

/// Checks sequences and quantities (`peripheral.py:check_sequences`).
pub fn check_sequences(checker: &mut Checker, file_idx: usize) {
    let file_data = checker.files[file_idx].data.clone();
    let index = field_index(&file_data);
    let mut registers = HashMap::new();
    let Some(facts) = as_array(&file_data, "facts") else {
        return;
    };
    for fact in facts {
        if let Some(reg) = fact.get("data").and_then(|d| d.get("register")) {
            if let Some(fid) = as_str(fact, "id") {
                registers.insert(fid.to_string(), reg.clone());
            }
        }
    }
    for (i, fact) in facts.iter().enumerate() {
        let Some(payload) = fact.get("data") else {
            continue;
        };
        if let Some(q) = payload.get("quantity") {
            let qpath = vec![
                PathElem::from("facts"),
                PathElem::Index(i),
                PathElem::from("data"),
                PathElem::from("quantity"),
            ];
            check_quantity(checker, file_idx, q, &qpath);
        }
        let Some(seq) = payload.get("sequence") else {
            continue;
        };
        if let Some(steps) = as_array(seq, "steps") {
            for (j, step) in steps.iter().enumerate() {
                let spath = vec![
                    PathElem::from("facts"),
                    PathElem::Index(i),
                    PathElem::from("data"),
                    PathElem::from("sequence"),
                    PathElem::from("steps"),
                    PathElem::Index(j),
                ];
                check_step(checker, file_idx, step, &spath, &registers, &index);
            }
        }
    }
}

fn check_quantity(checker: &mut Checker, file_idx: usize, q: &Value, qpath: &[PathElem]) {
    let mn = parse_int(q.get("min"));
    let val = parse_int(q.get("value"));
    let mx = parse_int(q.get("max"));
    if let (Some(a), Some(b)) = (mn, mx) {
        if a > b {
            checker.add_file(
                file_idx,
                qpath,
                "quantity min exceeds max",
                "error",
                false,
                true,
                true,
            );
        }
    }
    if let (Some(a), Some(v)) = (mn, val) {
        if a > v {
            checker.add_file(
                file_idx,
                qpath,
                "quantity min exceeds value",
                "error",
                false,
                true,
                true,
            );
        }
    }
    if let (Some(v), Some(b)) = (val, mx) {
        if v > b {
            checker.add_file(
                file_idx,
                qpath,
                "quantity value exceeds max",
                "error",
                false,
                true,
                true,
            );
        }
    }
}

fn check_step(
    checker: &mut Checker,
    file_idx: usize,
    step: &Value,
    spath: &[PathElem],
    registers: &HashMap<String, Value>,
    index: &HashMap<(String, String), (Value, Value)>,
) {
    let sid = as_str(step, "id").unwrap_or("");
    let what = format!("step '{sid}'");
    let op = as_str(step, "op");
    if matches!(op, Some("read" | "write" | "rmw" | "poll")) && step.get("target").is_none() {
        checker.add_file(
            file_idx,
            spath,
            format!("{what}: op '{}' requires a target", op.unwrap_or("")),
            "error",
            false,
            true,
            true,
        );
    }
    if op == Some("poll") && step.get("until").is_none() {
        checker.add_file(
            file_idx,
            spath,
            format!("{what}: op 'poll' requires an until condition"),
            "error",
            false,
            true,
            true,
        );
    }
    if op == Some("delay") && step.get("duration").is_none() {
        checker.add_file(
            file_idx,
            spath,
            format!("{what}: op 'delay' requires a duration"),
            "error",
            false,
            true,
            true,
        );
    }
    for key in ["duration", "timeout", "interval"] {
        if let Some(q) = step.get(key) {
            let mut p = spath.to_vec();
            p.push(PathElem::from(key));
            check_quantity(checker, file_idx, q, &p);
        }
    }

    let Some(target) = as_str(step, "target") else {
        return;
    };
    if let Some(rest) = target.strip_prefix('#') {
        if let Some((reg_id, fid)) = rest.split_once('.') {
            let key = (reg_id.to_string(), fid.to_string());
            let Some((field, _)) = index.get(&key) else {
                let mut p = spath.to_vec();
                p.push(PathElem::from("target"));
                checker.add_file(
                    file_idx,
                    &p,
                    format!("{what}: target '{target}' resolves to no register field"),
                    "error",
                    false,
                    true,
                    true,
                );
                return;
            };
            let fwidth = as_array(field, "bits").and_then(|b| {
                if b.len() >= 2 {
                    Some(b[1].as_u64()? - b[0].as_u64()? + 1)
                } else {
                    None
                }
            });
            check_step_value(checker, file_idx, &what, step, Some(field), fwidth, spath);
        } else if let Some(reg) = registers.get(rest) {
            check_step_value(
                checker,
                file_idx,
                &what,
                step,
                None,
                reg.get("width").and_then(Value::as_u64),
                spath,
            );
        }
    }
}

fn check_step_value(
    checker: &mut Checker,
    file_idx: usize,
    what: &str,
    step: &Value,
    field: Option<&Value>,
    width: Option<u64>,
    spath: &[PathElem],
) {
    if let Some(val) = step.get("value") {
        let mut p = spath.to_vec();
        p.push(PathElem::from("value"));
        check_value_literal(checker, file_idx, what, step, val, field, width, &p);
    }
    // A poll compares against `until.equals`, never a top-level `value` (#197).
    if let Some(val) = step.get("until").and_then(|u| u.get("equals")) {
        let mut p = spath.to_vec();
        p.push(PathElem::from("until"));
        p.push(PathElem::from("equals"));
        check_value_literal(checker, file_idx, what, step, val, field, width, &p);
    }
    check_step_mask(checker, file_idx, what, step, width, spath);
}

/// Checks one step value (`value` or `until.equals`): a number fits the target width, a name
/// is an enumerated value of the target field, and a poll does not compare against a
/// write-only meaning.
#[allow(clippy::too_many_arguments)]
fn check_value_literal(
    checker: &mut Checker,
    file_idx: usize,
    what: &str,
    step: &Value,
    val: &Value,
    field: Option<&Value>,
    width: Option<u64>,
    path: &[PathElem],
) {
    let val_str = val.as_str().unwrap_or("");
    let is_hex_or_int = val.is_number()
        || val_str.starts_with("0x")
        || val_str.starts_with("0X")
        || (!val_str.is_empty() && val_str.chars().all(|c| c.is_ascii_digit()));
    if is_hex_or_int {
        if let (Some(w), Some(ival)) = (width, parse_int(Some(val))) {
            if bit_length(ival) > w {
                checker.add_file(
                    file_idx,
                    path,
                    format!("{what}: value {val_str} exceeds target width {w}"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
        }
    } else if let Some(fld) = field {
        // name -> usage ("read-write" when the entry gives none).
        let mut entries: HashMap<String, String> = HashMap::new();
        let mut collect = |vals: &[Value]| {
            for r in vals {
                if let Some(n) = as_str(r, "name") {
                    let usage = as_str(r, "usage").unwrap_or("read-write");
                    entries.insert(n.to_string(), usage.to_string());
                }
            }
        };
        if let Some(evs) = as_array(fld, "enumeratedValues") {
            collect(evs);
        }
        if let Some(eref) = as_str(fld, "enumerationDefinitionRef") {
            if let Some((ed_entry, _)) = checker.files[file_idx]
                .registries
                .get("enumerationDefinitions")
                .and_then(|m| m.get(eref))
            {
                if let Some(vals) =
                    as_array(ed_entry, "enumeratedValues").or_else(|| as_array(ed_entry, "values"))
                {
                    collect(vals);
                }
            }
        }
        match entries.get(val_str) {
            None if !entries.is_empty() => {
                checker.add_file(
                    file_idx,
                    path,
                    format!("{what}: value '{val_str}' is not an enumerated name of target field"),
                    "error",
                    false,
                    true,
                    true,
                );
            }
            Some(usage) if usage == "write" && as_str(step, "op") == Some("poll") => {
                checker.add_file(
                    file_idx,
                    path,
                    format!(
                        "{what}: value '{val_str}' is a write meaning of the target field; a poll compares a read value"
                    ),
                    "error",
                    false,
                    true,
                    true,
                );
            }
            _ => {}
        }
    }
}

fn check_step_mask(
    checker: &mut Checker,
    file_idx: usize,
    what: &str,
    step: &Value,
    width: Option<u64>,
    spath: &[PathElem],
) {
    let Some(w) = width else {
        return;
    };
    let until = step.get("until");
    let masks = [
        ("mask", None, step.get("mask")),
        (
            "until",
            Some("bitsSet"),
            until.and_then(|u| u.get("bitsSet")),
        ),
        (
            "until",
            Some("bitsClear"),
            until.and_then(|u| u.get("bitsClear")),
        ),
    ];
    for (key, sub, mask) in masks {
        let Some(mval) = parse_int(mask) else {
            continue;
        };
        if bit_length(mval) > w {
            let mask_str = mask.and_then(Value::as_str).unwrap_or("");
            let mut p = spath.to_vec();
            p.push(PathElem::from(key));
            if let Some(sub) = sub {
                p.push(PathElem::from(sub));
            }
            checker.add_file(
                file_idx,
                &p,
                format!("{what}: mask {mask_str} exceeds target width {w}"),
                "error",
                false,
                true,
                true,
            );
        }
    }
}

/// Formats a quantity object into human-readable text (`peripheral.py:quantity_text`):
/// `min 60 s, nom 60 s, max 90 s`, the levels present in the order min, nom, typ, max.
#[must_use]
pub fn quantity_text(q: &Value) -> String {
    let unit = as_str(q, "unit").unwrap_or("");
    let val_str = |k: &str| -> Option<String> {
        let v = q.get(k)?;
        if let Some(s) = v.as_str() {
            Some(s.to_string())
        } else {
            Some(v.to_string())
        }
    };
    ["min", "nom", "typ", "max"]
        .iter()
        .filter_map(|level| val_str(level).map(|v| format!("{level} {v} {unit}")))
        .collect::<Vec<_>>()
        .join(", ")
}

/// Formats a sequence step into human-readable text (`peripheral.py:step_text`).
#[must_use]
pub fn step_text(step: &Value) -> String {
    let mut parts = Vec::new();
    if let Some(op) = as_str(step, "op") {
        parts.push(op.to_string());
    }
    if let Some(target) = as_str(step, "target") {
        parts.push(target.to_string());
    }
    if let Some(val) = step.get("value") {
        let v_str = if let Some(s) = val.as_str() {
            s.to_string()
        } else {
            val.to_string()
        };
        parts.push(format!("= {v_str}"));
    }
    if let Some(mask) = as_str(step, "mask") {
        parts.push(format!("(mask {mask})"));
    }
    if let Some(until) = step.get("until") {
        if let Some(v) = as_str(until, "equals") {
            parts.push(format!("until = {v}"));
        } else if let Some(m) = as_str(until, "bitsSet") {
            parts.push(format!("until bits {m} set"));
        } else if let Some(m) = as_str(until, "bitsClear") {
            parts.push(format!("until bits {m} clear"));
        }
    }
    if let Some(iv) = step.get("interval") {
        parts.push(format!("every {}", quantity_text(iv)));
    }
    if let Some(dur) = step.get("duration") {
        parts.push(format!("for {}", quantity_text(dur)));
    }
    if let Some(to) = step.get("timeout") {
        parts.push(format!("timeout {}", quantity_text(to)));
    }
    if let Some(w) = as_str(step, "when") {
        parts.push(format!("when {w}"));
    }
    if let Some(c) = as_str(step, "claim") {
        let head = if parts.is_empty() {
            String::new()
        } else {
            format!("{}: ", parts.join(" "))
        };
        return format!("{head}{c}");
    }
    parts.join(" ")
}

/// Builds generated register/layout/sequence summary views (`peripheral.py:generated`).
#[must_use]
pub fn generated(checker: &Checker, file_idx: usize) -> Map<String, Value> {
    let f = &checker.files[file_idx];
    let mut registers = Vec::new();
    let mut layouts = Vec::new();
    let mut sequences = Vec::new();
    if let Some(facts) = as_array(&f.data, "facts") {
        for fact in facts {
            let Some(payload) = fact.get("data") else {
                continue;
            };
            let fid = as_str(fact, "id").unwrap_or("");
            let title = as_str(fact, "title").unwrap_or(fid);
            if let Some(reg) = payload.get("register") {
                registers.push(json!({
                    "id": fid,
                    "title": title,
                    "requirement": fact.get("requirement"),
                    "register": reg,
                    "fields": payload.get("fields").cloned().unwrap_or_else(|| json!([])),
                }));
            }
            if let Some(layout) = payload.get("layout") {
                layouts.push(json!({
                    "id": fid,
                    "title": title,
                    "requirement": fact.get("requirement"),
                    "layout": layout,
                }));
            }
            if let Some(seq) = payload.get("sequence") {
                sequences.push(json!({
                    "id": fid,
                    "title": title,
                    "requirement": fact.get("requirement"),
                    "sequence": seq,
                }));
            }
        }
    }
    registers.sort_by(|a, b| {
        let ra = a.get("register").unwrap_or(&Value::Null);
        let rb = b.get("register").unwrap_or(&Value::Null);
        let rfa = as_str(ra, "registerFile").unwrap_or("");
        let rfb = as_str(rb, "registerFile").unwrap_or("");
        let oa = parse_int(ra.get("offset")).unwrap_or(0);
        let ob = parse_int(rb.get("offset")).unwrap_or(0);
        let na = as_str(ra, "name").unwrap_or("");
        let nb = as_str(rb, "name").unwrap_or("");
        (rfa, oa, na).cmp(&(rfb, ob, nb))
    });
    let mut out = Map::new();
    out.insert("registers".to_string(), Value::Array(registers));
    out.insert("layouts".to_string(), Value::Array(layouts));
    out.insert("sequences".to_string(), Value::Array(sequences));
    for &group in REGISTRIES {
        let mut entries: Vec<Value> = f
            .registries
            .get(group)
            .map(|m| m.values().map(|(e, _)| e.clone()).collect())
            .unwrap_or_default();
        entries.sort_by(|a, b| {
            as_str(a, "name")
                .unwrap_or("")
                .cmp(as_str(b, "name").unwrap_or(""))
        });
        out.insert(group.to_string(), Value::Array(entries));
    }
    out
}

/// Flattens register summary entries into table rows (`peripheral.py:register_rows`).
#[must_use]
pub fn register_rows(summary: &Map<String, Value>) -> Vec<Map<String, Value>> {
    let mut rows = Vec::new();
    let Some(regs) = summary.get("registers").and_then(Value::as_array) else {
        return rows;
    };
    for item in regs {
        let Some(r) = item.get("register") else {
            continue;
        };
        let mut m = Map::new();
        m.insert(
            "fact".to_string(),
            item.get("id").cloned().unwrap_or(Value::Null),
        );
        m.insert(
            "name".to_string(),
            r.get("name").cloned().unwrap_or(Value::Null),
        );
        m.insert(
            "offset".to_string(),
            r.get("offset").cloned().unwrap_or(Value::Null),
        );
        m.insert(
            "width".to_string(),
            r.get("width")
                .map(|w| Value::String(w.to_string()))
                .unwrap_or(Value::Null),
        );
        m.insert(
            "access".to_string(),
            Value::String(as_str(r, "access").unwrap_or("").to_string()),
        );
        m.insert(
            "reset".to_string(),
            Value::String(as_str(r, "reset").unwrap_or("").to_string()),
        );
        m.insert(
            "registerFile".to_string(),
            Value::String(as_str(r, "registerFile").unwrap_or("").to_string()),
        );
        rows.push(m);
    }
    rows
}

/// Flattens register field entries into table rows (`peripheral.py:field_rows`).
#[must_use]
pub fn field_rows(summary: &Map<String, Value>) -> Vec<Map<String, Value>> {
    let mut rows = Vec::new();
    let Some(regs) = summary.get("registers").and_then(Value::as_array) else {
        return rows;
    };
    for item in regs {
        let Some(r) = item.get("register") else {
            continue;
        };
        let Some(fields) = item.get("fields").and_then(Value::as_array) else {
            continue;
        };
        let mut sorted_fields = fields.clone();
        sorted_fields.sort_by(|a, b| {
            let ba = as_array(a, "bits");
            let bb = as_array(b, "bits");
            let a1 = ba
                .and_then(|v| v.get(1))
                .and_then(Value::as_i64)
                .unwrap_or(0);
            let a0 = ba
                .and_then(|v| v.first())
                .and_then(Value::as_i64)
                .unwrap_or(0);
            let b1 = bb
                .and_then(|v| v.get(1))
                .and_then(Value::as_i64)
                .unwrap_or(0);
            let b0 = bb
                .and_then(|v| v.first())
                .and_then(Value::as_i64)
                .unwrap_or(0);
            (-a1, -a0).cmp(&(-b1, -b0))
        });
        for fld in sorted_fields {
            let bits = as_array(&fld, "bits");
            let low = bits
                .and_then(|v| v.first())
                .and_then(Value::as_u64)
                .unwrap_or(0);
            let high = bits
                .and_then(|v| v.get(1))
                .and_then(Value::as_u64)
                .unwrap_or(0);
            let span = if low == high {
                format!("[{low}]")
            } else {
                format!("[{high}:{low}]")
            };
            let policy = as_str(&fld, "fieldAccessPolicyDefinitionRef")
                .or_else(|| as_str(&fld, "access"))
                .unwrap_or("");
            let reset = if let Some(res) = as_str(&fld, "reset") {
                res.to_string()
            } else if let Some(resets) = as_array(&fld, "resets") {
                resets
                    .iter()
                    .map(|x| {
                        if let Some(rt) = as_str(x, "resetTypeRef") {
                            format!("{rt}={}", as_str(x, "value").unwrap_or(""))
                        } else {
                            as_str(x, "value").unwrap_or("").to_string()
                        }
                    })
                    .collect::<Vec<_>>()
                    .join(", ")
            } else {
                String::new()
            };
            let mut m = Map::new();
            m.insert(
                "fact".to_string(),
                item.get("id").cloned().unwrap_or(Value::Null),
            );
            m.insert(
                "register".to_string(),
                r.get("name").cloned().unwrap_or(Value::Null),
            );
            m.insert(
                "field".to_string(),
                fld.get("id").cloned().unwrap_or(Value::Null),
            );
            m.insert("bits".to_string(), Value::String(span));
            m.insert("access".to_string(), Value::String(policy.to_string()));
            m.insert("reset".to_string(), Value::String(reset));
            m.insert(
                "claim".to_string(),
                Value::String(as_str(&fld, "claim").unwrap_or("").to_string()),
            );
            rows.push(m);
        }
    }
    rows
}

/// Flattens layout field entries into table rows (`peripheral.py:layout_field_rows`).
#[must_use]
pub fn layout_field_rows(summary: &Map<String, Value>) -> Vec<Map<String, Value>> {
    let mut rows = Vec::new();
    let Some(layouts) = summary.get("layouts").and_then(Value::as_array) else {
        return rows;
    };
    for item in layouts {
        let Some(layout) = item.get("layout") else {
            continue;
        };
        let Some(fields) = as_array(layout, "fields") else {
            continue;
        };
        for fld in fields {
            let bits = if let Some(b) = as_array(fld, "bits") {
                let low = b.first().and_then(Value::as_u64).unwrap_or(0);
                let high = b.get(1).and_then(Value::as_u64).unwrap_or(0);
                if low == high {
                    format!("[{low}]")
                } else {
                    format!("[{high}:{low}]")
                }
            } else {
                String::new()
            };
            let mut m = Map::new();
            m.insert(
                "fact".to_string(),
                item.get("id").cloned().unwrap_or(Value::Null),
            );
            m.insert(
                "layout".to_string(),
                layout.get("name").cloned().unwrap_or(Value::Null),
            );
            m.insert(
                "field".to_string(),
                fld.get("id").cloned().unwrap_or(Value::Null),
            );
            m.insert(
                "offset".to_string(),
                fld.get("offset").cloned().unwrap_or(Value::Null),
            );
            m.insert(
                "size".to_string(),
                fld.get("size")
                    .map(|s| Value::String(s.to_string()))
                    .unwrap_or(Value::Null),
            );
            m.insert("bits".to_string(), Value::String(bits));
            m.insert(
                "claim".to_string(),
                Value::String(as_str(fld, "claim").unwrap_or("").to_string()),
            );
            rows.push(m);
        }
    }
    rows
}
