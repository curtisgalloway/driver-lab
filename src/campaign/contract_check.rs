// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::campaign::{is_sha256, mapping, require, Invalid, VResult};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashSet};
use std::path::Path;

const AUXILIARY_GROUPS: &[&str] = &["trace", "capture"];
const ERROR_GROUPS: &[&str] = &["boot", "between scenarios"];
const VERDICTS: &[&str] = &["PASS", "FAIL", "ERROR"];

pub fn required_fields(document: &Value, fields: &[&str]) -> VResult<()> {
    let obj = document
        .as_object()
        .ok_or_else(|| Invalid("expected a mapping".to_string()))?;
    for &field in fields {
        if !obj.contains_key(field) {
            return Err(Invalid(format!("missing fixture field: {}", field)));
        }
    }
    Ok(())
}

pub fn source_output(document: &Value) -> VResult<Value> {
    require(document.is_object(), "source output must be a mapping")?;
    let mut doc = document;
    if doc.get("result").is_some() {
        mapping(
            doc,
            "document",
            Some(&["ok", "result", "updated", "would_update", "findings"]),
            None,
        )?;
        for field in &["ok", "updated", "would_update"] {
            require(
                doc.get(*field).unwrap().is_boolean(),
                format!("{} must be boolean", field),
            )?;
        }
        let findings = doc
            .get("findings")
            .unwrap()
            .as_array()
            .ok_or_else(|| Invalid("findings must be array".into()))?;
        for f in findings {
            require(f.is_string(), "finding must be string")?;
        }
        doc = doc.get("result").unwrap();
    }
    mapping(
        doc,
        "document",
        Some(&["id", "version", "sha256", "status", "checked", "provenance"]),
        Some(&["matches_pin"]),
    )?;
    crate::campaign::source_registry::validate_identity(doc, "")?;
    if let Some(mp) = doc.get("matches_pin") {
        require(
            mp.is_null() || mp.is_boolean(),
            "matches_pin must be boolean or null",
        )?;
    }
    Ok(json!({"status": doc.get("status").unwrap()}))
}

pub fn fixture_identity(identity: &Value) -> VResult<()> {
    require(identity.is_object(), "identities must be a mapping")?;

    let mut is_neutral = false;
    let keys_to_check = [
        "fixture",
        "harness_sha256",
        "kernel_sha256",
        "image_sha256",
        "conditions",
    ];
    if let Some(obj) = identity.as_object() {
        for k in keys_to_check.iter() {
            if obj.contains_key(*k) {
                is_neutral = true;
                break;
            }
        }
    }

    let scenarios;
    if is_neutral {
        required_fields(
            identity,
            &[
                "fixture",
                "harness_sha256",
                "kernel_sha256",
                "image_sha256",
                "conditions",
            ],
        )?;
        let fixture = identity.get("fixture").unwrap();
        required_fields(fixture, &["name", "version", "sha256"])?;
        require(
            fixture.get("name").unwrap().is_string(),
            "name must be string",
        )?;
        require(
            fixture.get("version").unwrap().is_string(),
            "version must be string",
        )?;
        require(
            is_sha256(fixture.get("sha256").unwrap()),
            "sha256 must be sha",
        )?;

        for field in &["harness_sha256", "kernel_sha256", "image_sha256"] {
            require(
                is_sha256(identity.get(*field).unwrap()),
                format!("{} must be sha", field),
            )?;
        }

        let conditions = identity.get("conditions").unwrap();
        require(
            conditions.is_object() && !conditions.as_object().unwrap().is_empty(),
            "conditions must be a nonempty mapping",
        )?;
        required_fields(conditions, &["scenarios"])?;
        scenarios = conditions.get("scenarios").unwrap();
    } else {
        required_fields(
            identity,
            &[
                "qemu_version",
                "sha256",
                "driver",
                "accel",
                "scenarios",
                "dut_mem",
                "host_kernel",
                "python",
            ],
        )?;
        for field in &[
            "qemu_version",
            "driver",
            "accel",
            "dut_mem",
            "host_kernel",
            "python",
        ] {
            require(
                identity.get(*field).unwrap().is_string(),
                format!("{} must be string", field),
            )?;
        }
        let scens = identity.get("scenarios").unwrap();
        require(
            scens.is_array() && !scens.as_array().unwrap().is_empty(),
            "scenarios must be nonempty string array",
        )?;
        scenarios = scens;

        let hashes = identity.get("sha256").unwrap();
        required_fields(
            hashes,
            &[
                "qemu",
                "harness:l02harness.py",
                "harness:guest-init.sh",
                "kernel",
                "initramfs",
                "busybox",
            ],
        )?;
        for val in hashes.as_object().unwrap().values() {
            require(is_sha256(val), "must be sha256")?;
        }
    }

    require(
        scenarios.is_array() && !scenarios.as_array().unwrap().is_empty(),
        "scenarios must be nonempty string array",
    )?;
    let scens_arr = scenarios.as_array().unwrap();
    for s in scens_arr {
        require(s.is_string(), "scenarios must contain strings")?;
    }
    require(
        scens_arr.len() == 1,
        "expected one scenario per isolated run",
    )?;

    let scens_set: HashSet<&str> = scens_arr.iter().map(|v| v.as_str().unwrap()).collect();
    let reserved: HashSet<&str> = AUXILIARY_GROUPS
        .iter()
        .chain(ERROR_GROUPS.iter())
        .copied()
        .collect();

    require(
        scens_set.intersection(&reserved).count() == 0,
        "requested scenario uses a reserved result-group name",
    )?;

    Ok(())
}

pub fn verdict(value: &Value) -> VResult<()> {
    require(value.is_string(), "verdict must be a string")?;
    let s = value.as_str().unwrap();
    require(VERDICTS.contains(&s), "expected PASS, FAIL or ERROR")?;
    Ok(())
}

pub fn result_groups(identity: &Value, results: &[Value]) -> VResult<()> {
    let native = identity.get("fixture").is_none();
    let declared_val = if native {
        identity.get("scenarios").unwrap()
    } else {
        identity
            .get("conditions")
            .unwrap()
            .get("scenarios")
            .unwrap()
    };

    let declared: HashSet<&str> = declared_val
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap())
        .collect();

    let mut groups = BTreeMap::new();
    for row in results {
        let sc = row.get("scenario").unwrap().as_str().unwrap();
        groups.insert(sc, row);
    }

    let names: HashSet<&str> = groups.keys().copied().collect();
    let allowed: HashSet<&str> = declared
        .iter()
        .chain(AUXILIARY_GROUPS.iter())
        .chain(ERROR_GROUPS.iter())
        .copied()
        .collect();
    require(names.is_subset(&allowed), "undeclared scenario in verdicts")?;

    let error_groups: HashSet<&str> = ERROR_GROUPS.iter().copied().collect();
    for &name in names.intersection(&error_groups) {
        let g = groups.get(name).unwrap();
        let checks_empty = g
            .get("checks")
            .is_none_or(|c| c.as_array().is_none_or(|a| a.is_empty()));
        require(
            g.get("verdict").unwrap().as_str().unwrap() == "ERROR" && checks_empty,
            "error group must be ERROR with no completed checks",
        )?;
    }

    if names.contains("boot") {
        let mut no_boot: HashSet<&str> = declared.clone();
        no_boot.insert("between scenarios");
        require(
            names.intersection(&no_boot).count() == 0,
            "boot error cannot accompany executed scenarios",
        )?;
    }

    require(
        declared.is_subset(&names) || names.intersection(&error_groups).count() > 0,
        "declared scenario missing without a startup or collection error",
    )?;

    if names.contains("trace") && !declared.is_subset(&names) {
        require(
            groups
                .get("trace")
                .unwrap()
                .get("verdict")
                .unwrap()
                .as_str()
                .unwrap()
                == "ERROR",
            "trace without an executed scenario must be ERROR",
        )?;
    }

    if names.contains("capture") {
        require(
            declared.is_subset(&names) && (!native || declared.contains("smoke")),
            "capture requires an executed scenario (smoke for native QEMU)",
        )?;
    }

    Ok(())
}

pub fn fixture_output(directory: &Path) -> VResult<Value> {
    let id_path = directory.join("identities.json");
    let id_str = std::fs::read_to_string(&id_path)
        .map_err(|_| Invalid("cannot read identities.json".into()))?;
    let identity: Value =
        serde_json::from_str(&id_str).map_err(|_| Invalid("invalid json".into()))?;
    fixture_identity(&identity)?;

    let vd_path = directory.join("verdicts.json");
    let vd_str = std::fs::read_to_string(&vd_path)
        .map_err(|_| Invalid("cannot read verdicts.json".into()))?;
    let document: Value =
        serde_json::from_str(&vd_str).map_err(|_| Invalid("invalid json".into()))?;

    required_fields(&document, &["overall", "results"])?;
    verdict(document.get("overall").unwrap())?;

    let results = document.get("results").unwrap();
    require(
        results.is_array() && !results.as_array().unwrap().is_empty(),
        "results must be a nonempty list",
    )?;
    let results_arr = results.as_array().unwrap();

    let mut names = HashSet::new();
    let mut counts: BTreeMap<String, i32> = BTreeMap::new();
    let mut scenario_verdicts = HashSet::new();

    for result in results_arr {
        required_fields(result, &["scenario", "verdict", "checks"])?;
        require(
            result.get("scenario").unwrap().is_string(),
            "scenario must be string",
        )?;
        let scen = result.get("scenario").unwrap().as_str().unwrap();
        require(
            !names.contains(scen),
            "duplicate scenario: expected one isolated run",
        )?;
        names.insert(scen.to_string());

        verdict(result.get("verdict").unwrap())?;
        let r_verdict = result.get("verdict").unwrap().as_str().unwrap();
        scenario_verdicts.insert(r_verdict.to_string());

        let checks = result.get("checks").unwrap();
        require(checks.is_array(), "checks must be a list")?;
        let checks_arr = checks.as_array().unwrap();

        require(
            !checks_arr.is_empty() || r_verdict == "FAIL" || r_verdict == "ERROR",
            "PASS scenario needs named checks",
        )?;

        let mut seen = HashSet::new();
        let mut outcomes = HashSet::new();

        for row in checks_arr {
            required_fields(row, &["check"])?;
            require(
                row.get("check").unwrap().is_string(),
                "check must be string",
            )?;
            let check_name = row.get("check").unwrap().as_str().unwrap();
            require(!seen.contains(check_name), "duplicate check in scenario")?;
            seen.insert(check_name.to_string());

            let has_ok = row.as_object().unwrap().contains_key("ok");
            let has_verdict = row.as_object().unwrap().contains_key("verdict");
            require(
                has_ok != has_verdict,
                "check needs exactly one of ok or verdict",
            )?;

            let outcome = if has_ok {
                require(
                    row.get("ok").unwrap().is_boolean(),
                    "check ok must be boolean",
                )?;
                if row.get("ok").unwrap().as_bool().unwrap() {
                    "PASS"
                } else {
                    "FAIL"
                }
            } else {
                verdict(row.get("verdict").unwrap())?;
                row.get("verdict").unwrap().as_str().unwrap()
            };
            outcomes.insert(outcome.to_string());
            *counts.entry(outcome.to_string()).or_insert(0) += 1;
        }

        if r_verdict == "PASS" {
            let mut expected_outcomes = HashSet::new();
            expected_outcomes.insert("PASS".to_string());
            require(
                outcomes == expected_outcomes,
                "PASS scenario contradicts check verdicts",
            )?;
        }
        if outcomes.contains("ERROR") {
            require(r_verdict == "ERROR", "ERROR check needs ERROR scenario")?;
        }
    }

    let expected = if scenario_verdicts.contains("ERROR") {
        "ERROR"
    } else if scenario_verdicts.contains("FAIL") {
        "FAIL"
    } else {
        "PASS"
    };

    require(
        document.get("overall").unwrap().as_str().unwrap() == expected,
        "overall contradicts scenario verdicts",
    )?;

    result_groups(&identity, results_arr)?;

    Ok(json!({
        "overall": document.get("overall").unwrap().as_str().unwrap(),
        "scenarios": results_arr.len(),
        "verdicts": counts,
    }))
}
