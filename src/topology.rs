// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Hardware topology node, connection, configuration, selection, and cross-spec
//! boundary semantic validation (`topology.py`, `RT-4`).

use crate::records::{Checker, PathElem, RecordKey, SpecRecord};
use serde_json::Value;
use std::collections::{HashMap, HashSet};

/// Extracts all topology fact references `(kind, ref_str, path)` (`topology.py:references`).
#[must_use]
pub fn references(data: &Value, base: &[PathElem]) -> Vec<(String, String, Vec<PathElem>)> {
    crate::records::topology_refs(data, base)
}

const PAYLOADS: &[&str] = &[
    "topologyNode",
    "connection",
    "topologyConfiguration",
    "selection",
];
const OWNER_KINDS: &[&str] = &["board", "soc", "chip"];

fn payload<'a>(rec: &'a SpecRecord, name: &str) -> Option<&'a Value> {
    rec.data.get("data").and_then(|d| d.get(name))
}

fn bases(checker: &Checker) -> HashMap<String, usize> {
    let mut by_id: HashMap<String, Vec<usize>> = HashMap::new();
    for (idx, file) in checker.files.iter().enumerate() {
        if !file.is_overlay() {
            by_id.entry(file.spec_id()).or_default().push(idx);
        }
    }
    by_id
        .into_iter()
        .filter_map(|(k, v)| if v.len() == 1 { Some((k, v[0])) } else { None })
        .collect()
}

fn target(
    checker: &mut Checker,
    rec_file_idx: usize,
    rec_path: &[PathElem],
    rec_data: &Value,
    name: &str,
    field: &str,
    expected: &str,
) -> Option<RecordKey> {
    let value = rec_data.get("data").and_then(|d| d.get(name))?;
    let ref_str = value.get(field).and_then(|v| v.as_str())?;

    let (other_opt, _) = checker.resolve(rec_file_idx, ref_str);
    let other_key = other_opt?;

    let other_file = &checker.files[other_key.file_idx];
    let other_rec = &other_file.records[other_file.record_map[&other_key.id]].1;

    let valid = if expected == "instance" {
        other_rec
            .path
            .first()
            .map(|p| match p {
                PathElem::Key(k) => k == "instances",
                _ => false,
            })
            .unwrap_or(false)
    } else {
        payload(other_rec, expected).is_some()
    };

    if !valid {
        let mut path = rec_path.to_vec();
        path.push(PathElem::from("data"));
        path.push(PathElem::from(name));
        path.push(PathElem::from(field));
        checker.reject(
            rec_file_idx,
            &path,
            format!("topology {field} must reference a {expected} record"),
            false,
        );
        return None;
    }

    Some(other_key)
}

fn endpoint(
    checker: &mut Checker,
    rec_file_idx: usize,
    rec_path: &[PathElem],
    rec_data: &Value,
    side: &str,
) -> Option<RecordKey> {
    let conn_val = rec_data.get("data").and_then(|d| d.get("connection"))?;
    let value = conn_val.get(side)?;
    let ref_str = value.get("node").and_then(|v| v.as_str())?;

    let (other_opt, _) = checker.resolve(rec_file_idx, ref_str);
    let other_key = other_opt?;

    let mut at = rec_path.to_vec();
    at.push(PathElem::from("data"));
    at.push(PathElem::from("connection"));
    at.push(PathElem::from(side));

    let other_file = &checker.files[other_key.file_idx];
    let other_rec = &other_file.records[other_file.record_map[&other_key.id]].1;
    let node = payload(other_rec, "topologyNode");

    if node.is_none() {
        let mut path = at.clone();
        path.push(PathElem::from("node"));
        checker.reject(
            rec_file_idx,
            &path,
            "connection endpoint must reference a topologyNode fact",
            false,
        );
        return None;
    }
    let node = node.unwrap();

    let want_port = value.get("port").and_then(|v| v.as_str());
    let mut matching_ports = Vec::new();
    if let Some(ports) = node.get("ports").and_then(|p| p.as_array()) {
        for port in ports {
            if port.get("name").and_then(|v| v.as_str()) == want_port {
                matching_ports.push(port);
            }
        }
    }

    if matching_ports.len() != 1 {
        let mut path = at.clone();
        path.push(PathElem::from("port"));
        checker.add_file(
            rec_file_idx,
            &path,
            "connection port is missing or ambiguous",
            "error",
            false,
            true,
            true,
        );
        return None;
    }

    let port = matching_ports[0].clone();
    let port_role = port
        .get("role")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());
    let port_kind = port
        .get("kind")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());
    let conn_kind = conn_val
        .get("kind")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    if port_role.as_deref() != Some(side) || port_kind != conn_kind {
        let mut path = at.clone();
        path.push(PathElem::from("port"));
        checker.add_file(
            rec_file_idx,
            &path,
            "connection port role/kind does not match endpoint",
            "error",
            false,
            true,
            true,
        );
    }

    if side == "provider" {
        if let Some(cells_val) = port.get("cells") {
            if let Some(arity) = cells_val.as_u64() {
                let val_cells_len = value
                    .get("cells")
                    .and_then(|c| c.as_array())
                    .map(|a| a.len() as u64)
                    .unwrap_or(0);
                if val_cells_len != arity {
                    let mut path = at.clone();
                    path.push(PathElem::from("cells"));
                    checker.add_file(
                        rec_file_idx,
                        &path,
                        format!("provider requires exactly {arity} specifier cells"),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }
    }

    Some(other_key)
}

/// Topology context for a focus board/soc/chip spec (`topology.py:Context`).
#[derive(Debug, Clone)]
pub struct Context {
    /// Index of focus [`SpecFile`] in `checker.files`.
    pub focus_idx: usize,
    /// Admitted owner spec IDs.
    pub owners: HashSet<String>,
    /// Admitted topology record keys.
    pub records: Vec<RecordKey>,
    /// Cross-boundary rejected endpoints `(record_key, side, target_node_key)`.
    pub boundaries: Vec<(RecordKey, String, RecordKey)>,
}

impl Context {
    /// Filters `records` to those carrying topology payload `name` (`topology.py:Context.of_kind`).
    #[must_use]
    pub fn of_kind(&self, checker: &Checker, name: &str) -> Vec<RecordKey> {
        self.records
            .iter()
            .filter(|&k| {
                let file = &checker.files[k.file_idx];
                let rec = &file.records[file.record_map[&k.id]].1;
                payload(rec, name).is_some()
            })
            .cloned()
            .collect()
    }
}

/// Builds the topology [`Context`] for `focus_idx` (`topology.py:context`).
#[must_use]
pub fn context(checker: &Checker, focus_idx: usize) -> Context {
    let real = bases(checker);
    get_context(checker, focus_idx, &real)
}

fn get_context(checker: &Checker, focus_idx: usize, real: &HashMap<String, usize>) -> Context {
    let focus = &checker.files[focus_idx];
    let mut owners = HashSet::new();
    let mut pending: Vec<String> = vec![focus.spec_id().to_string()];

    let admit = |sid: &str, owners: &mut HashSet<String>| -> bool {
        let Some(&f_idx) = real.get(sid) else {
            return false;
        };
        let f = &checker.files[f_idx];
        if f.kind() == "board" && f_idx != focus_idx {
            return false;
        }
        if owners.contains(sid) {
            return false;
        }
        owners.insert(sid.to_string());
        true
    };

    while let Some(sid) = pending.pop() {
        if !admit(&sid, &mut owners) {
            continue;
        }
        let f_idx = *real.get(&sid).unwrap();
        let f = &checker.files[f_idx];
        if let Some(parts) = f.data.get("parts").and_then(|p| p.as_array()) {
            for p in parts {
                if let Some(s) = p.as_str() {
                    pending.push(s.to_string());
                }
            }
        }
    }

    let composed = owners.clone();
    for file in &checker.files {
        if composed.contains(&file.spec_id()) {
            if let Some(instances) = file.data.get("instances").and_then(|i| i.as_array()) {
                for row in instances {
                    for key in ["ip", "peripheral"] {
                        if let Some(val) = row.get(key).and_then(|v| v.as_str()) {
                            admit(val, &mut owners);
                        }
                    }
                }
            }
        }
        if file.kind() == "peripheral" {
            let mut has_intersection = false;
            if let Some(describes) = file.data.get("describes").and_then(|d| d.as_array()) {
                for d in describes {
                    if let Some(s) = d.as_str() {
                        if composed.contains(s) {
                            has_intersection = true;
                            break;
                        }
                    }
                }
            }
            if has_intersection {
                admit(&file.spec_id(), &mut owners);
            }
        }
    }

    let mut candidates = Vec::new();
    for (f_idx, f) in checker.files.iter().enumerate() {
        if let Some(&real_idx) = real.get(&f.spec_id()) {
            let real_f = &checker.files[real_idx];
            if OWNER_KINDS.contains(&real_f.kind()) {
                for rec in f.records.iter().map(|(_, r)| r) {
                    if PAYLOADS.iter().any(|&n| payload(rec, n).is_some()) {
                        candidates.push(RecordKey {
                            file_idx: f_idx,
                            id: rec.id.clone(),
                            full: rec.full.clone(),
                        });
                    }
                }
            }
        }
    }
    candidates.sort_by(|a, b| a.full.cmp(&b.full));

    let mut changed = true;
    while changed {
        changed = false;
        for key in &candidates {
            let rec_file = &checker.files[key.file_idx];
            if !owners.contains(&rec_file.spec_id()) {
                continue;
            }
            let rec = &rec_file.records[rec_file.record_map[&key.id]].1;
            if let Some(conn) = payload(rec, "connection") {
                for side in ["provider", "consumer"] {
                    if let Some(ref_str) = conn
                        .get(side)
                        .and_then(|s| s.get("node"))
                        .and_then(|n| n.as_str())
                    {
                        let (node_opt, _) = checker.resolve(key.file_idx, ref_str);
                        if let Some(node_key) = node_opt {
                            let node_file = &checker.files[node_key.file_idx];
                            let node_rec = &node_file.records[node_file.record_map[&node_key.id]].1;
                            if payload(node_rec, "topologyNode").is_some() {
                                if let Some(&owner_idx) = real.get(&node_file.spec_id()) {
                                    let owner_f = &checker.files[owner_idx];
                                    if (owner_f.kind() == "soc" || owner_f.kind() == "chip")
                                        && admit(&owner_f.spec_id(), &mut owners)
                                    {
                                        changed = true;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    let mut records = Vec::new();
    let mut boundaries = Vec::new();

    for key in &candidates {
        let rec_file = &checker.files[key.file_idx];
        if !owners.contains(&rec_file.spec_id()) {
            continue;
        }
        let rec = &rec_file.records[rec_file.record_map[&key.id]].1;

        if (payload(rec, "topologyConfiguration").is_some() || payload(rec, "selection").is_some())
            && (focus.kind() != "board" || rec_file.spec_id() != focus.spec_id())
        {
            continue;
        }

        let mut excluded = false;
        if let Some(conn) = payload(rec, "connection") {
            for side in ["provider", "consumer"] {
                if let Some(ref_str) = conn
                    .get(side)
                    .and_then(|s| s.get("node"))
                    .and_then(|n| n.as_str())
                {
                    let (node_opt, _) = checker.resolve(key.file_idx, ref_str);
                    if let Some(node_key) = node_opt {
                        let node_file = &checker.files[node_key.file_idx];
                        if !owners.contains(&node_file.spec_id()) {
                            boundaries.push((key.clone(), side.to_string(), node_key));
                            excluded = true;
                        }
                    }
                }
            }
        }
        if !excluded {
            records.push(key.clone());
        }
    }

    Context {
        focus_idx,
        owners,
        records,
        boundaries,
    }
}

fn slot(checker: &Checker, key: &RecordKey) -> Option<(String, String)> {
    let rec_file = &checker.files[key.file_idx];
    let rec = &rec_file.records[rec_file.record_map[&key.id]].1;
    let end = payload(rec, "connection")?.get("consumer")?;
    let ref_str = end.get("node")?.as_str()?;
    let (node_opt, _) = checker.resolve(key.file_idx, ref_str);
    let node_key = node_opt?;
    let port = end.get("port")?.as_str()?;
    Some((node_key.full, port.to_string()))
}

pub fn check(checker: &mut Checker) {
    let real = bases(checker);
    let mut configs = HashMap::new();
    let mut selections = Vec::new();

    let files_len = checker.files.len();
    for file_idx in 0..files_len {
        let spec_id = checker.files[file_idx].spec_id();
        let owner_idx = real.get(&spec_id).copied();

        let mut rec_keys = Vec::new();
        for (_, rec) in &checker.files[file_idx].records {
            if rec.data.get("data").is_some() {
                rec_keys.push((rec.id.clone(), rec.path.clone(), rec.data.clone()));
            }
        }

        for (rec_id, rec_path, rec_data) in rec_keys {
            let data = match rec_data.get("data") {
                Some(d) => d,
                None => continue,
            };

            if !PAYLOADS.iter().any(|&n| data.get(n).is_some()) {
                continue;
            }

            let is_valid_owner = owner_idx
                .map(|idx| OWNER_KINDS.contains(&checker.files[idx].kind()))
                .unwrap_or(false);
            if !is_valid_owner {
                let mut path = rec_path.clone();
                path.push(PathElem::from("data"));
                checker.add_file(
                    file_idx,
                    &path,
                    "topology payload requires a real board, soc or chip target",
                    "error",
                    false,
                    true,
                    true,
                );
                continue;
            }

            if let Some(node) = data.get("topologyNode") {
                let mut seen = HashSet::new();
                if let Some(ports) = node.get("ports").and_then(|p| p.as_array()) {
                    for (i, port) in ports.iter().enumerate() {
                        if let Some(name) = port.get("name").and_then(|n| n.as_str()) {
                            if seen.contains(name) {
                                let mut path = rec_path.clone();
                                path.extend(vec![
                                    PathElem::from("data"),
                                    PathElem::from("topologyNode"),
                                    PathElem::from("ports"),
                                    PathElem::Index(i),
                                    PathElem::from("name"),
                                ]);
                                checker.add_file(
                                    file_idx,
                                    &path,
                                    "topology node port name is duplicated",
                                    "error",
                                    false,
                                    true,
                                    true,
                                );
                            }
                            seen.insert(name.to_string());
                        }
                    }
                }

                if node.get("incompleteKinds").is_some()
                    && rec_data
                        .get("todo")
                        .and_then(|t| t.get("check"))
                        .and_then(|c| c.as_str())
                        != Some("document")
                {
                    let mut path = rec_path.clone();
                    path.extend(vec![
                        PathElem::from("data"),
                        PathElem::from("topologyNode"),
                        PathElem::from("incompleteKinds"),
                    ]);
                    checker.add_file(
                        file_idx,
                        &path,
                        "incompleteKinds requires a document TODO explaining the gap",
                        "error",
                        false,
                        true,
                        true,
                    );
                }

                for (field, expected) in [
                    ("instance", "instance"),
                    ("rate", "quantity"),
                    ("voltage", "quantity"),
                ] {
                    target(
                        checker,
                        file_idx,
                        &rec_path,
                        &rec_data,
                        "topologyNode",
                        field,
                        expected,
                    );
                }
            }

            if data.get("connection").is_some() {
                endpoint(checker, file_idx, &rec_path, &rec_data, "provider");
                endpoint(checker, file_idx, &rec_path, &rec_data, "consumer");
            }

            if let Some(config) = data.get("topologyConfiguration") {
                if let Some(board_ref) = config.get("board").and_then(|b| b.as_str()) {
                    let mut is_valid = false;
                    let mut belongs = false;
                    if let Some(&b_idx) = real.get(board_ref) {
                        let board_f = &checker.files[b_idx];
                        if board_f.kind() == "board" {
                            is_valid = true;
                            belongs = spec_id == board_f.spec_id();
                        }
                    }
                    if !is_valid {
                        let mut path = rec_path.clone();
                        path.extend(vec![
                            PathElem::from("data"),
                            PathElem::from("topologyConfiguration"),
                            PathElem::from("board"),
                        ]);
                        checker.add_file(
                            file_idx,
                            &path,
                            "topology configuration board must resolve to a real board",
                            "error",
                            false,
                            true,
                            true,
                        );
                    } else if !belongs {
                        let mut path = rec_path.clone();
                        path.extend(vec![
                            PathElem::from("data"),
                            PathElem::from("topologyConfiguration"),
                            PathElem::from("board"),
                        ]);
                        checker.add_file(
                            file_idx,
                            &path,
                            "topology configuration must belong to its configured board",
                            "error",
                            false,
                            true,
                            true,
                        );
                    } else {
                        configs.insert(
                            RecordKey {
                                file_idx,
                                id: rec_id.clone(),
                                full: checker.files[file_idx].records
                                    [checker.files[file_idx].record_map[&rec_id]]
                                    .1
                                    .full
                                    .clone(),
                            },
                            board_ref.to_string(),
                        );
                    }
                }
            }

            if data.get("selection").is_some() {
                let config_rec = target(
                    checker,
                    file_idx,
                    &rec_path,
                    &rec_data,
                    "selection",
                    "configuration",
                    "topologyConfiguration",
                );
                let conn_rec = target(
                    checker,
                    file_idx,
                    &rec_path,
                    &rec_data,
                    "selection",
                    "selects",
                    "connection",
                );
                if let Some(conn_key) = conn_rec.clone() {
                    let conn_f = &checker.files[conn_key.file_idx];
                    let conn_r = &conn_f.records[conn_f.record_map[&conn_key.id]].1;
                    if payload(conn_r, "connection")
                        .and_then(|c| c.get("mode"))
                        .and_then(|m| m.as_str())
                        != Some("selectable")
                    {
                        let mut path = rec_path.clone();
                        path.extend(vec![
                            PathElem::from("data"),
                            PathElem::from("selection"),
                            PathElem::from("selects"),
                        ]);
                        checker.reject(
                            file_idx,
                            &path,
                            "selection must reference a selectable connection, never fixed",
                            false,
                        );
                    }
                }
                selections.push((
                    RecordKey {
                        file_idx,
                        id: rec_id.clone(),
                        full: checker.files[file_idx].records
                            [checker.files[file_idx].record_map[&rec_id]]
                            .1
                            .full
                            .clone(),
                    },
                    config_rec,
                    conn_rec,
                ));
            }
        }
    }

    let mut contexts = HashMap::new();
    for &f_idx in real.values() {
        if OWNER_KINDS.contains(&checker.files[f_idx].kind()) {
            contexts.insert(f_idx, get_context(checker, f_idx, &real));
        }
    }

    for (ctx_idx, ctx) in &contexts {
        let ctx_focus_spec_id = checker.files[*ctx_idx].spec_id();
        for (rec_key, side, _) in &ctx.boundaries {
            let rec_file = &checker.files[rec_key.file_idx];
            let rec = &rec_file.records[rec_file.record_map[&rec_key.id]].1;
            let mut path = rec.path.clone();
            path.extend(vec![
                PathElem::from("data"),
                PathElem::from("connection"),
                PathElem::from(side.as_str()),
                PathElem::from("node"),
            ]);
            checker.reject(
                rec_key.file_idx,
                &path,
                format!("endpoint is outside topology context '{ctx_focus_spec_id}'; board-specific topology must belong to that board"),
                false,
            );
        }

        let mut slots: HashMap<(String, String), Vec<RecordKey>> = HashMap::new();
        for rec_key in ctx.of_kind(checker, "connection") {
            if let Some(key) = slot(checker, &rec_key) {
                slots.entry(key).or_default().push(rec_key);
            }
        }

        for (key, records) in &slots {
            let fixed: Vec<_> = records
                .iter()
                .filter(|&r| {
                    let f = &checker.files[r.file_idx];
                    let rec = &f.records[f.record_map[&r.id]].1;
                    payload(rec, "connection")
                        .and_then(|c| c.get("mode"))
                        .and_then(|m| m.as_str())
                        == Some("fixed")
                })
                .collect();

            if fixed.len() > 1 || (!fixed.is_empty() && records.len() > 1) {
                for rec_key in records {
                    let f = &checker.files[rec_key.file_idx];
                    let rec = &f.records[f.record_map[&rec_key.id]].1;
                    let mut path = rec.path.clone();
                    path.extend(vec![
                        PathElem::from("data"),
                        PathElem::from("connection"),
                        PathElem::from("consumer"),
                    ]);
                    checker.add_file(
                        rec_key.file_idx,
                        &path,
                        format!("consumer slot ('{}', '{}') has multiple fixed connections or mixes fixed/selectable connections in context '{ctx_focus_spec_id}'", key.0, key.1),
                        "error",
                        false,
                        true,
                        true,
                    );
                }
            }
        }
    }

    let mut chosen: HashMap<(String, (String, String)), Vec<(RecordKey, RecordKey)>> =
        HashMap::new();
    for (rec_key, config_opt, conn_opt) in selections {
        let config_key = match config_opt {
            Some(k) => k,
            None => continue,
        };
        let board_idx = configs.get(&config_key).and_then(|b| real.get(b).copied());
        let rec_spec_id = checker.files[rec_key.file_idx].spec_id();

        let board_f = board_idx.map(|idx| &checker.files[idx]);
        if board_f.is_none() || rec_spec_id != board_f.unwrap().spec_id() {
            let rec_file = &checker.files[rec_key.file_idx];
            let rec = &rec_file.records[rec_file.record_map[&rec_key.id]].1;
            let mut path = rec.path.clone();
            path.extend(vec![
                PathElem::from("data"),
                PathElem::from("selection"),
                PathElem::from("configuration"),
            ]);
            checker.reject(
                rec_key.file_idx,
                &path,
                "selection must belong to the configured board",
                false,
            );
            continue;
        }
        let board_idx = board_idx.unwrap();

        let conn_key = match conn_opt {
            Some(k) => k,
            None => continue,
        };

        if !contexts[&board_idx]
            .of_kind(checker, "connection")
            .contains(&conn_key)
        {
            let rec_file = &checker.files[rec_key.file_idx];
            let rec = &rec_file.records[rec_file.record_map[&rec_key.id]].1;
            let mut path = rec.path.clone();
            path.extend(vec![
                PathElem::from("data"),
                PathElem::from("selection"),
                PathElem::from("selects"),
            ]);
            checker.reject(
                rec_key.file_idx,
                &path,
                "selected connection is not admitted to the configured board topology",
                false,
            );
            continue;
        }

        if let Some(s) = slot(checker, &conn_key) {
            chosen
                .entry((config_key.full.clone(), s))
                .or_default()
                .push((rec_key, conn_key));
        }
    }

    for choices in chosen.values() {
        let unique_conns: HashSet<String> = choices.iter().map(|(_, c)| c.full.clone()).collect();
        if unique_conns.len() > 1 {
            for (rec_key, _) in choices {
                let rec_file = &checker.files[rec_key.file_idx];
                let rec = &rec_file.records[rec_file.record_map[&rec_key.id]].1;
                let mut path = rec.path.clone();
                path.extend(vec![
                    PathElem::from("data"),
                    PathElem::from("selection"),
                    PathElem::from("selects"),
                ]);
                checker.reject(
                    rec_key.file_idx,
                    &path,
                    "configuration selects different candidates in one consumer slot",
                    false,
                );
            }
        }
    }
}
