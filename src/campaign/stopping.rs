// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::campaign::VResult;
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, HashSet};

const BATCH_CAP: usize = 3;
const ROUND_CAP: usize = 3;
const CAP_DATE: &str = "2026-09-26";
pub const POLICY: &str = "A1-amended-2026-09-26";

pub fn effective_class(entry: &Value) -> &str {
    let cls = entry.get("class").and_then(Value::as_str).unwrap_or("");
    if cls == "R" || cls == "E" || cls == "W" {
        cls
    } else {
        "R"
    }
}

pub fn covers(sections: &[&str], required: &[&str]) -> bool {
    required.iter().all(|&r| {
        sections
            .iter()
            .any(|&s| r == s || r.starts_with(&format!("{}.", s)))
    })
}

pub fn reading_groups(status: &Value) -> BTreeMap<&str, Vec<&Value>> {
    let mut groups: BTreeMap<&str, Vec<&Value>> = BTreeMap::new();
    if let Some(entries) = status.get("entries").and_then(Value::as_array) {
        for entry in entries {
            if entry.get("kind").and_then(Value::as_str) == Some("verification")
                && entry.get("purpose").and_then(Value::as_str) == Some("accuracy")
            {
                if let Some(reading_id) = entry.get("reading_id").and_then(Value::as_str) {
                    groups.entry(reading_id).or_default().push(entry);
                }
            }
        }
    }
    groups
}

pub fn round_report(status: &Value, groups: &BTreeMap<&str, Vec<&Value>>) -> Vec<Value> {
    let mut rows = Vec::new();
    if let Some(revisions) = status.get("revisions").and_then(Value::as_object) {
        for (revision_str, header) in revisions {
            let revision_int = revision_str.parse::<i64>().unwrap_or(0);
            let mut readings = Vec::new();
            for group in groups.values() {
                let first = group[0];
                let basis = first.get("basis").and_then(Value::as_str).unwrap_or("");
                let spec_rev = status
                    .get("bases")
                    .and_then(|b| b.get(basis))
                    .and_then(|b| b.get("spec_revision"))
                    .and_then(Value::as_i64)
                    .unwrap_or(-1);

                let indep = first
                    .get("independence")
                    .and_then(Value::as_str)
                    .unwrap_or("");
                if spec_rev == revision_int && indep != "adjudication" {
                    readings.push(first);
                }
            }

            let mut count = readings.len() as i64;
            for r in &readings {
                if let Some(rnd) = r.get("round").and_then(Value::as_str) {
                    if let Ok(c) = rnd.parse::<i64>() {
                        if c > count {
                            count = c;
                        }
                    }
                }
            }

            let started = header.get("started").and_then(Value::as_str).unwrap_or("");
            let historical = !started.is_empty() && started <= CAP_DATE;

            if count > ROUND_CAP as i64 || (count == ROUND_CAP as i64 && !historical) {
                let state = if historical {
                    "historical"
                } else if count > ROUND_CAP as i64 {
                    "awaiting decision"
                } else {
                    "limit reached"
                };

                let reason = if historical {
                    "pre-cap history"
                } else {
                    "round cap reached; send remaining findings to the user"
                };

                rows.push(json!({
                    "revision": revision_int,
                    "rounds": count,
                    "state": state,
                    "reason": reason,
                }));
            }
        }
    }
    rows
}

pub fn select_batch(queue: &[Value]) -> (Vec<String>, Vec<String>) {
    let mut ready = Vec::new();
    for u in queue {
        let state = u.get("state").and_then(Value::as_str).unwrap_or("");
        let tier = u.get("tier").and_then(Value::as_i64).unwrap_or(0);
        let user_decision = u
            .get("decision")
            .and_then(|d| d.get("who"))
            .and_then(Value::as_str)
            == Some("user");
        if state == "ready" && (tier == 1 || (tier == 2 && user_decision)) {
            if let Some(id) = u.get("id").and_then(Value::as_str) {
                ready.push(id.to_string());
            }
        }
    }
    let split = std::cmp::min(BATCH_CAP, ready.len());
    let (first, second) = ready.split_at(split);
    (first.to_vec(), second.to_vec())
}

pub fn evaluate(
    claims_doc: &Value,
    status: &Value,
    freshness: &Value,
    roles: &Value,
    reader_opt: Option<&Value>,
) -> VResult<Value> {
    let reader = reader_opt.unwrap_or_else(|| roles.get("reader").unwrap());

    let mut entries = HashMap::new();
    if let Some(arr) = status.get("entries").and_then(Value::as_array) {
        for e in arr {
            entries.insert(e.get("id").unwrap().as_str().unwrap(), e.clone());
        }
    }

    let mut claims = HashMap::new();
    if let Some(arr) = claims_doc.get("claims").and_then(Value::as_array) {
        for c in arr {
            claims.insert(c.get("id").unwrap().as_str().unwrap(), c.clone());
        }
    }

    let scope = status.get("scope").filter(|v| !v.is_null());
    let scoped: HashSet<&str> = if let Some(s) = scope {
        s.get("claims")
            .unwrap()
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect()
    } else {
        claims.keys().copied().collect()
    };

    let mut states = HashMap::new();
    for (id, e) in &entries {
        if let Some(s) = e
            .get("status")
            .and_then(|st| st.get("state"))
            .and_then(Value::as_str)
        {
            states.insert(*id, s.to_string());
        }
    }
    if let Some(arr) = freshness.get("entries").and_then(Value::as_array) {
        for e in arr {
            if let (Some(id), Some(st)) = (
                e.get("id").and_then(Value::as_str),
                e.get("state").and_then(Value::as_str),
            ) {
                states.insert(id, st.to_string());
            }
        }
    }

    let mut conditions = HashMap::new();
    for i in 1..=5 {
        conditions.insert(format!("S{}", i), json!({"met": true, "blockers": []}));
    }

    let block = |cond: &str, detail: &str, conditions: &mut HashMap<String, Value>| {
        let c = conditions.get_mut(cond).unwrap().as_object_mut().unwrap();
        c.insert("met".to_string(), json!(false));
        c.get_mut("blockers")
            .unwrap()
            .as_array_mut()
            .unwrap()
            .push(json!(detail));
    };

    if scope.is_none() {
        block("S1", "scope declaration missing", &mut conditions);
    }

    let policies = scope
        .and_then(|s| s.get("rules"))
        .and_then(Value::as_object);
    let mut policy_changes = Vec::new();
    let mut policy_blockers = Vec::new();
    let empty_vec = vec![];
    let eligible_arr = freshness
        .get("eligible")
        .and_then(Value::as_array)
        .unwrap_or(&empty_vec);
    let mut eligible: HashSet<&str> = eligible_arr.iter().map(|v| v.as_str().unwrap()).collect();

    for entry in entries.values() {
        let kind = entry.get("kind").and_then(Value::as_str).unwrap_or("");
        if let Some(exp) = policies.and_then(|p| p.get(kind)) {
            let rule = entry.get("rule").unwrap_or(&Value::Null);
            if exp != rule {
                let id = entry.get("id").unwrap().as_str().unwrap();
                policy_changes.push(json!({
                    "id": id,
                    "recorded": rule,
                    "expected": exp,
                    "compared": false
                }));
                eligible.remove(id);
                if states.get(id).map(String::as_str) == Some("current") {
                    let has_claim = entry.get("claim").and_then(Value::as_str);
                    if has_claim.is_none() || scoped.contains(has_claim.unwrap()) {
                        policy_blockers.push(id.to_string());
                    }
                }
            }
        }
    }

    let mut shortfalls = Vec::new();
    let mut sorted_scoped: Vec<&str> = scoped.iter().copied().collect();
    sorted_scoped.sort();

    for cid in sorted_scoped {
        let claim = claims.get(cid).unwrap();
        let mut qualifications = Vec::new();
        for e in entries.values() {
            let kind = e.get("kind").and_then(Value::as_str).unwrap_or("");
            let c = e.get("claim").and_then(Value::as_str).unwrap_or("");
            let id = e.get("id").unwrap().as_str().unwrap();
            if kind == "qualification"
                && c == cid
                && states.get(id).map(String::as_str) != Some("superseded")
            {
                qualifications.push(e.clone());
            }
        }
        if qualifications.is_empty() {
            continue;
        }
        let qualification = &qualifications[0];
        let qid = qualification.get("id").unwrap().as_str().unwrap();

        let qverdict = qualification
            .get("verdict")
            .and_then(Value::as_str)
            .unwrap_or("");
        if qverdict == "shortfall" {
            let mut obj = json!({
                "id": qid,
                "decision": qualification.get("decision").unwrap_or(&Value::Null),
                "current": eligible.contains(qid)
            });
            if let Some(sf) = qualification.get("shortfall").and_then(Value::as_object) {
                for (k, v) in sf {
                    obj.as_object_mut().unwrap().insert(k.clone(), v.clone());
                }
            }
            shortfalls.push(obj);
        }

        let is_mandatory = claim
            .get("mandatory")
            .and_then(Value::as_bool)
            .unwrap_or(false);
        if !is_mandatory {
            continue;
        }

        if !eligible.contains(qid) {
            block(
                "S2",
                &format!(
                    "{}: qualification/shortfall is not current under the scope rule",
                    cid
                ),
                &mut conditions,
            );
            continue;
        }

        if qverdict == "shortfall" {
            let who = qualification
                .get("decision")
                .and_then(|d| d.get("who"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if who != "user" {
                block(
                    "S2",
                    &format!("{}: mandatory shortfall requires user approval", cid),
                    &mut conditions,
                );
            }
            continue;
        }

        let mut results = Vec::new();
        for e in entries.values() {
            let kind = e.get("kind").and_then(Value::as_str).unwrap_or("");
            let c = e.get("claim").and_then(Value::as_str).unwrap_or("");
            let id = e.get("id").unwrap().as_str().unwrap();
            if kind == "result" && c == cid && eligible.contains(id) {
                results.push(e);
            }
        }

        let accepted = scope.is_some_and(|s| {
            if let Some(ac) = s
                .get("accepted_classes")
                .and_then(|ac| ac.get(cid))
                .and_then(Value::as_array)
            {
                ac.iter().any(|v| v.as_str() == Some("emulated"))
            } else {
                false
            }
        });

        let mut has_qualified_pass = false;
        for r in &results {
            if r.get("verdict").and_then(Value::as_str) == Some("PASS") {
                let qe = r
                    .get("qualified_evidence")
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
                let rqid = r.get("qualification").and_then(Value::as_str).unwrap_or("");
                if qe && rqid == qid {
                    has_qualified_pass = true;
                    break;
                }
            }
        }

        if qverdict != "qualified" || !has_qualified_pass || !accepted {
            block(
                "S2",
                &format!("{}: no qualified PASS in an accepted evidence class", cid),
                &mut conditions,
            );
        }
    }

    let mut queue = Vec::new();

    let unit = |kind: &str,
                ids: &[&str],
                reason: &str,
                tier: i64,
                decision: Option<&Value>,
                suffix: Option<&str>,
                q: &mut Vec<Value>|
     -> Value {
        let cmp = status.get("campaign").and_then(Value::as_str).unwrap_or("");
        let suf = suffix.unwrap_or("current");
        let id_str = format!("{}:{}:{}", cmp, kind, suf);
        let role = match kind {
            "second-reading" | "comparison-reading" | "re-verification" => "reader",
            "implementation" => "implementer",
            _ => "reviewer",
        };

        // dedup and sort ids
        let mut ids_vec: Vec<&str> = ids.to_vec();
        ids_vec.sort();
        ids_vec.dedup();

        let mut u = json!({
            "id": id_str,
            "kind": kind,
            "tier": tier,
            "entries": ids_vec,
            "reason": reason,
            "role": role,
            "model": if role == "reader" { reader.clone() } else { roles.get(role).cloned().unwrap_or(Value::Null) }
        });

        let state = if tier == 1
            || decision.and_then(|d| d.get("who")).and_then(Value::as_str) == Some("user")
        {
            "ready"
        } else {
            "awaiting decision"
        };
        u.as_object_mut()
            .unwrap()
            .insert("state".to_string(), json!(state));

        if let Some(d) = decision {
            u.as_object_mut()
                .unwrap()
                .insert("decision".to_string(), d.clone());
        }
        q.push(u.clone());
        u
    };

    let mut items = Vec::new();
    for entry in entries.values() {
        let kind = entry.get("kind").and_then(Value::as_str).unwrap_or("");
        let id = entry.get("id").unwrap().as_str().unwrap();
        if kind != "item" || states.get(id).map(String::as_str) == Some("superseded") {
            continue;
        }
        let disp = entry.get("disposition").unwrap();
        let disp_state = disp.get("state").and_then(Value::as_str).unwrap_or("");
        if disp_state != "queued" && disp_state != "shortfall" {
            continue;
        }

        let cls = effective_class(entry);
        let target = entry.get("target").and_then(Value::as_str).unwrap_or("");
        let mut row = json!({
            "id": id,
            "recorded_class": entry.get("class").unwrap_or(&Value::Null),
            "effective_class": cls,
            "target": target,
            "disposition": disp,
            "action": "recorded"
        });

        if disp_state == "shortfall" {
            let mut obj = json!({"id": id});
            if let Some(dobj) = disp.as_object() {
                for (k, v) in dobj {
                    obj.as_object_mut().unwrap().insert(k.clone(), v.clone());
                }
            }
            shortfalls.push(obj);
            items.push(row);
            continue;
        }

        let impact = entry.get("impact");
        let mut in_scope = true;
        if let Some(imp) = impact {
            if !imp.is_null() {
                if let Some(carr) = imp.get("claims").and_then(Value::as_array) {
                    in_scope = carr.iter().any(|c| scoped.contains(c.as_str().unwrap()));
                }
            }
        }
        let status_change = impact.is_none()
            || impact.unwrap().is_null()
            || impact
                .unwrap()
                .get("changes_status")
                .and_then(Value::as_bool)
                .unwrap_or(false);

        if cls == "E"
            && target != "spec"
            && target != "records"
            && (impact.is_some() && !impact.unwrap().is_null() || target == "review")
            && in_scope
            && status_change
        {
            let reason = if impact.is_none() || impact.unwrap().is_null() {
                "impact unrecorded"
            } else {
                "evidence changes a claim status in scope"
            };
            block("S3", &format!("{}: {}", id, reason), &mut conditions);
            if target == "review" && entry.get("action").is_none() {
                unit(
                    "re-verification",
                    &[id],
                    "review claim-status impact",
                    1,
                    None,
                    Some(id),
                    &mut queue,
                );
            }
        }

        if target == "records" {
            row.as_object_mut().unwrap().insert(
                "action".to_string(),
                json!("records maintenance; not a spec item"),
            );
        } else if cls == "W" {
            row.as_object_mut().unwrap().insert(
                "action".to_string(),
                json!("carry to next revision/brief; never starts a revision"),
            );
        } else if entry.get("action").is_some() {
            if in_scope
                && (target == "spec" && (cls == "R" || status_change)
                    || target == "review" && cls == "R")
            {
                block(
                    "S3",
                    &format!("{}: open {} item affecting scope", id, cls),
                    &mut conditions,
                );
            }
            unit(
                entry.get("action").unwrap().as_str().unwrap(),
                &[id],
                disp.get("destination")
                    .and_then(Value::as_str)
                    .unwrap_or(""),
                2,
                entry.get("decision"),
                Some(id),
                &mut queue,
            );
            row.as_object_mut()
                .unwrap()
                .insert("action".to_string(), json!("tier-2 decision"));
        } else if in_scope
            && (target == "spec" && (cls == "R" || status_change)
                || target == "review" && cls == "R")
        {
            block(
                "S3",
                &format!("{}: open {} item affecting scope", id, cls),
                &mut conditions,
            );
            let action = if cls == "R" {
                "requirement decision"
            } else {
                "evidence revision"
            };
            row.as_object_mut()
                .unwrap()
                .insert("action".to_string(), json!(action));
            let ukind = if cls == "R" {
                "requirement-change"
            } else {
                "evidence-revision"
            };
            unit(
                ukind,
                &[id],
                action,
                if cls == "R" { 2 } else { 1 },
                entry.get("decision"),
                Some(id),
                &mut queue,
            );
        } else if entry.get("execution").and_then(Value::as_str) == Some("carry") {
            row.as_object_mut().unwrap().insert(
                "action".to_string(),
                json!("carry to next brief; no standalone round"),
            );
        } else if target == "candidate"
            || target == "hardware"
            || target == "upstream"
            || entry.get("action").is_some()
        {
            let act_val = entry
                .get("action")
                .and_then(Value::as_str)
                .unwrap_or(match target {
                    "candidate" => "implementation",
                    "hardware" => "hardware-run",
                    "upstream" => "outward-report",
                    _ => "",
                });
            unit(
                act_val,
                &[id],
                disp.get("destination")
                    .and_then(Value::as_str)
                    .unwrap_or(""),
                2,
                entry.get("decision"),
                Some(id),
                &mut queue,
            );
            row.as_object_mut()
                .unwrap()
                .insert("action".to_string(), json!("tier-2 decision"));
        } else {
            let action = if target == "review" && in_scope && status_change {
                "re-verification of claim-status impact"
            } else {
                "carry; no change to a claim status in scope"
            };
            row.as_object_mut()
                .unwrap()
                .insert("action".to_string(), json!(action));
        }

        if cls == "E" && target == "review" && (impact.is_none() || impact.unwrap().is_null()) {
            let act = row.get("action").unwrap().as_str().unwrap().to_string();
            row.as_object_mut().unwrap().insert(
                "action".to_string(),
                json!(format!("impact unrecorded; {}", act)),
            );
        }

        items.push(row);
    }

    let groups = reading_groups(status);
    for entry in entries.values() {
        let id = entry.get("id").unwrap().as_str().unwrap();
        if states.get(id).map(String::as_str) == Some("superseded") {
            continue;
        }
        let kind = entry.get("kind").and_then(Value::as_str).unwrap_or("");
        if kind == "result" {
            if let Some(c) = entry.get("claim").and_then(Value::as_str) {
                if scoped.contains(c)
                    && entry.get("verdict").and_then(Value::as_str) != Some("PASS")
                {
                    block(
                        "S3",
                        &format!(
                            "{}: open result {}",
                            id,
                            entry.get("verdict").and_then(Value::as_str).unwrap_or("")
                        ),
                        &mut conditions,
                    );
                }
            }
        }
        if kind == "observation" && states.get(id).map(String::as_str) == Some("contested") {
            block("S3", &format!("{}: contested fact", id), &mut conditions);
        }
    }

    for (rid, group) in &groups {
        if group
            .iter()
            .any(|e| eligible.contains(e.get("id").unwrap().as_str().unwrap()))
        {
            let first = group[0];
            let assessment = first.get("assessment");
            if assessment.is_none()
                || assessment.unwrap().is_null()
                || assessment
                    .unwrap()
                    .get("accuracy_failures")
                    .is_some_and(|v| {
                        v.as_bool().unwrap_or(true) || v.as_array().is_some_and(|a| !a.is_empty())
                    })
            {
                block(
                    "S3",
                    &format!("{}: accuracy failures present or not classified", rid),
                    &mut conditions,
                );
            }
        }
    }

    let mut coverage = Vec::new();
    if let Some(revisions) = status.get("revisions").and_then(Value::as_object) {
        for (revision_str, header) in revisions {
            if header.get("requirement_change").and_then(Value::as_bool) == Some(false) {
                continue;
            }
            let revision_int = revision_str.parse::<i64>().unwrap_or(0);

            let mut required = Vec::new();
            if let Some(cs) = header.get("changed_sections").and_then(Value::as_array) {
                if !cs.is_empty() {
                    for v in cs {
                        required.push(v.as_str().unwrap());
                    }
                }
            }
            if required.is_empty() {
                let mut req_set = HashSet::new();
                for cid in &scoped {
                    if let Some(cites) = claims
                        .get(cid)
                        .and_then(|c| c.get("cites"))
                        .and_then(Value::as_array)
                    {
                        for v in cites {
                            req_set.insert(v.as_str().unwrap());
                        }
                    }
                }
                required = req_set.into_iter().collect();
                required.sort();
            }

            let mut candidates = Vec::new();
            let mut independent = Vec::new();

            for (rid, group) in &groups {
                let first = group[0];
                let mut sections = Vec::new();
                for e in group {
                    if eligible.contains(e.get("id").unwrap().as_str().unwrap()) {
                        if let Some(secs) = e.get("sections").and_then(Value::as_array) {
                            for s in secs {
                                sections.push(s.as_str().unwrap());
                            }
                        }
                    }
                }

                let cov_revs = first
                    .get("covers_revisions")
                    .and_then(Value::as_array)
                    .map(|a| a.iter().any(|v| v.as_i64() == Some(revision_int)))
                    .unwrap_or(false);
                let text = first.get("text").and_then(Value::as_str).unwrap_or("");
                let indep = first
                    .get("independence")
                    .and_then(Value::as_str)
                    .unwrap_or("");

                if cov_revs
                    && text == "landed"
                    && (indep == "independent" || indep == "sequential")
                    && covers(&sections, &required)
                {
                    candidates.push(rid.to_string());
                    if indep == "independent" {
                        independent.push(rid.to_string());
                    }
                }
            }

            let mut cand_set: HashSet<&String> = candidates.iter().collect();
            for i in &independent {
                cand_set.remove(i);
            }
            let count = independent.len() + if !cand_set.is_empty() { 1 } else { 0 };

            coverage.push(json!({
                "revision": revision_int,
                "readings": candidates,
                "independent_count": count,
                "required_sections": required,
            }));

            if count < 2 {
                block(
                    "S4",
                    &format!(
                        "revision {}: {}/2 current independent reading lineages",
                        revision_str, count
                    ),
                    &mut conditions,
                );
            }
        }
    }

    let mut independent_groups = Vec::new();
    for group in groups.values() {
        if group[0].get("independence").and_then(Value::as_str) == Some("independent") {
            independent_groups.push(group);
        }
    }

    let mut latest = None;
    let mut missing_seq = independent_groups.is_empty();
    for g in &independent_groups {
        if g[0].get("sequence").is_none() {
            missing_seq = true;
            break;
        }
    }

    if missing_seq {
        block(
            "S5",
            "latest independent re-reading is not recorded in sequence",
            &mut conditions,
        );
    } else {
        let mut max_seq = -1;
        for g in &independent_groups {
            let seq = g[0].get("sequence").and_then(Value::as_i64).unwrap_or(-1);
            if seq > max_seq {
                max_seq = seq;
                latest = Some(g[0].clone());
            }
        }
        if let Some(lat) = &latest {
            let assessment = lat.get("assessment");
            if assessment.is_none()
                || assessment.unwrap().is_null()
                || assessment.unwrap().get("r_items").is_some_and(|v| {
                    v.as_bool().unwrap_or(true) || v.as_array().is_some_and(|a| !a.is_empty())
                })
            {
                block(
                    "S5",
                    &format!(
                        "{}: R findings present or unclassified",
                        lat.get("reading_id").unwrap().as_str().unwrap()
                    ),
                    &mut conditions,
                );
            }
        }
    }

    let rounds = round_report(status, &groups);
    if !conditions
        .get("S4")
        .unwrap()
        .get("met")
        .unwrap()
        .as_bool()
        .unwrap()
        || !conditions
            .get("S5")
            .unwrap()
            .get("met")
            .unwrap()
            .as_bool()
            .unwrap()
    {
        let mut rd = unit(
            "second-reading",
            &[],
            "unmet S4/S5; read current text independently",
            1,
            None,
            None,
            &mut queue,
        );
        rd.as_object_mut()
            .unwrap()
            .insert("coverage".to_string(), json!(coverage));
        queue.pop();
        queue.push(rd);
    }
    if let Some(scp) = scope {
        if scp.get("reader") != Some(reader) {
            unit(
                "comparison-reading",
                &[],
                "reader role changed; compare and adjudicate before changing verdicts",
                1,
                None,
                None,
                &mut queue,
            );
        }
    }

    let mut stale_by_kind: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    let mut historical_stale = Vec::new();

    if let Some(f_entries) = freshness.get("entries").and_then(Value::as_array) {
        for row in f_entries {
            let id = row.get("id").unwrap().as_str().unwrap();
            let entry = entries.get(id).unwrap();
            if let Some(cl) = entry.get("claim").and_then(Value::as_str) {
                if !scoped.contains(cl) {
                    continue;
                }
            }
            let kind = entry.get("kind").and_then(Value::as_str).unwrap_or("");
            if kind == "verification" {
                if entry.get("purpose").and_then(Value::as_str) != Some("accuracy") {
                    historical_stale.push(id.to_string());
                    continue;
                }

                let basis_key = entry.get("basis").and_then(Value::as_str).unwrap_or("");
                let basis = status.get("bases").and_then(|b| b.get(basis_key)).unwrap();
                let deps = basis.get("dependencies");

                let mut required = Vec::new();
                match deps {
                    None | Some(Value::Null) => {
                        if let Some(sr) = basis.get("sections_read").and_then(Value::as_array) {
                            for s in sr {
                                required.push(s.as_str().unwrap());
                            }
                        }
                    }
                    Some(deps_val) => {
                        if let Some(secs) = entry.get("sections").and_then(Value::as_array) {
                            for s in secs {
                                required.push(s.as_str().unwrap());
                            }
                        }
                        if let Some(da) = deps_val.as_array() {
                            for d in da {
                                required.push(d.as_str().unwrap());
                            }
                        }
                    }
                }

                let mut renewed = false;
                for group in groups.values() {
                    let first = group[0];
                    let f_cov = first
                        .get("covers_revisions")
                        .and_then(Value::as_array)
                        .unwrap();
                    let e_cov = entry
                        .get("covers_revisions")
                        .and_then(Value::as_array)
                        .unwrap();

                    let e_set: HashSet<i64> = e_cov.iter().map(|v| v.as_i64().unwrap()).collect();
                    let f_set: HashSet<i64> = f_cov.iter().map(|v| v.as_i64().unwrap()).collect();

                    if e_set.is_subset(&f_set)
                        && first.get("text").and_then(Value::as_str) == Some("landed")
                        && (first.get("independence").and_then(Value::as_str)
                            == Some("independent")
                            || first.get("independence").and_then(Value::as_str)
                                == Some("sequential"))
                    {
                        let mut g_sections = Vec::new();
                        for e in group {
                            if eligible.contains(e.get("id").unwrap().as_str().unwrap()) {
                                if let Some(secs) = e.get("sections").and_then(Value::as_array) {
                                    for s in secs {
                                        g_sections.push(s.as_str().unwrap());
                                    }
                                }
                            }
                        }

                        if covers(&g_sections, &required) {
                            renewed = true;
                            break;
                        }
                    }
                }

                if renewed {
                    historical_stale.push(id.to_string());
                    continue;
                }
            }

            let mut mapped_kind = match kind {
                "verification" => "re-verification",
                "qualification" => "requalification",
                "result" | "candidate_round" | "observation" => "acceptance-set-rerun",
                _ => "",
            };
            if kind == "observation"
                && row.get("state").and_then(Value::as_str) == Some("contested")
            {
                mapped_kind = "re-verification";
            }
            if !mapped_kind.is_empty() {
                stale_by_kind.entry(mapped_kind).or_default().push(id);
            }
        }
    }

    for (kind, mut ids) in stale_by_kind.clone() {
        ids.sort();
        if kind == "requalification" {
            for eid in ids {
                unit(
                    kind,
                    &[eid],
                    "reconcile expected outcome and qualify on current identities",
                    1,
                    None,
                    entries
                        .get(eid)
                        .unwrap()
                        .get("claim")
                        .and_then(Value::as_str),
                    &mut queue,
                );
            }
        } else {
            unit(
                kind,
                &ids,
                "refresh affected evidence on current identities",
                1,
                None,
                None,
                &mut queue,
            );
        }
    }

    if let Some(sc) = freshness.get("stale_controls").and_then(Value::as_array) {
        if !sc.is_empty() {
            let mut sc_ids = Vec::new();
            for c in sc {
                sc_ids.push(c.get("id").unwrap().as_str().unwrap());
            }
            unit(
                "requalification",
                &sc_ids,
                "reference control changed",
                1,
                None,
                Some("controls"),
                &mut queue,
            );
        }
    }

    queue.sort_by(|a, b| {
        let t_a = a.get("tier").and_then(Value::as_i64).unwrap_or(0);
        let t_b = b.get("tier").and_then(Value::as_i64).unwrap_or(0);
        if t_a != t_b {
            return t_a.cmp(&t_b);
        }

        let p = |k: &str| match k {
            "second-reading" => 0,
            "comparison-reading" => 1,
            "re-verification" => 2,
            "requalification" => 3,
            "acceptance-set-rerun" => 4,
            _ => 5,
        };
        let p_a = p(a.get("kind").unwrap().as_str().unwrap());
        let p_b = p(b.get("kind").unwrap().as_str().unwrap());
        if p_a != p_b {
            return p_a.cmp(&p_b);
        }

        a.get("id")
            .unwrap()
            .as_str()
            .unwrap()
            .cmp(b.get("id").unwrap().as_str().unwrap())
    });

    let mut cap_blocked = false;
    for r in &rounds {
        if r.get("state").and_then(Value::as_str) == Some("awaiting decision") {
            cap_blocked = true;
            break;
        }
    }

    if cap_blocked || scope.is_none() {
        for q in &mut queue {
            let kind = q.get("kind").unwrap().as_str().unwrap();
            if scope.is_none()
                || [
                    "second-reading",
                    "comparison-reading",
                    "re-verification",
                    "evidence-revision",
                ]
                .contains(&kind)
            {
                q.as_object_mut()
                    .unwrap()
                    .insert("state".to_string(), json!("awaiting decision"));
            }
        }
    }

    let (batch, waiting) = select_batch(&queue);

    let mut sufficient = true;
    for c in conditions.values() {
        if !c.get("met").unwrap().as_bool().unwrap() {
            sufficient = false;
            break;
        }
    }
    if cap_blocked
        || freshness
            .get("unavailable")
            .and_then(Value::as_array)
            .is_some_and(|a| !a.is_empty())
        || freshness
            .get("stale_controls")
            .and_then(Value::as_array)
            .is_some_and(|a| !a.is_empty())
        || !stale_by_kind.is_empty()
        || !policy_blockers.is_empty()
    {
        sufficient = false;
    }

    let mut blockers = Vec::new();
    for (name, value) in &conditions {
        if let Some(blks) = value.get("blockers").and_then(Value::as_array) {
            for b in blks {
                blockers.push(format!("{}: {}", name, b.as_str().unwrap()));
            }
        }
    }
    for ids in stale_by_kind.values() {
        for e in ids {
            blockers.push(format!("{}: stale/contested evidence in scope", e));
        }
    }
    if let Some(unavail) = freshness.get("unavailable").and_then(Value::as_array) {
        for e in unavail {
            blockers.push(format!(
                "{}: unavailable source identity",
                e.as_str().unwrap()
            ));
        }
    }
    if let Some(sc) = freshness.get("stale_controls").and_then(Value::as_array) {
        for e in sc {
            blockers.push(format!(
                "{}: stale reference control",
                e.get("id").unwrap().as_str().unwrap()
            ));
        }
    }
    for e in &policy_blockers {
        blockers.push(format!("{}: different rule; not compared", e));
    }
    for r in &rounds {
        if r.get("state").and_then(Value::as_str) == Some("awaiting decision") {
            blockers.push(format!(
                "revision {}: round cap exceeded",
                r.get("revision").unwrap().as_i64().unwrap()
            ));
        }
    }
    blockers.sort();

    let mut reopening_entries = Vec::new();
    for ids in stale_by_kind.values() {
        for e in ids {
            reopening_entries.push(e.to_string());
        }
    }
    reopening_entries.sort();

    Ok(json!({
        "sufficient": sufficient,
        "conditions": conditions,
        "coverage": coverage,
        "blockers": blockers,
        "policy_blockers": policy_blockers,
        "latest_independent": latest.map(|lat| lat.get("reading_id").unwrap().as_str().unwrap().to_string()),
        "round_cap": rounds,
        "policy_changes": policy_changes,
        "evaluation_policy": POLICY,
        "open_items": items,
        "shortfalls": shortfalls,
        "queue": queue,
        "batch": batch,
        "waiting": waiting,
        "historical_stale": historical_stale,
        "reopening_entries": reopening_entries
    }))
}
