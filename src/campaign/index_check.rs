use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use serde_json::{json, Value};
use crate::campaign::{Invalid, VResult, require, nonempty_str, mapping, is_sha256, is_iso_date_str};
use regex::Regex;

fn strings(value: &Value, nonempty: bool, pattern: Option<&Regex>) -> VResult<()> {
    require(value.is_array(), "expected a list")?;
    let arr = value.as_array().unwrap();
    require(!nonempty || !arr.is_empty(), "expected a nonempty list")?;
    let mut seen = HashSet::new();
    for part in arr {
        let s = nonempty_str(part, "")?;
        if let Some(pat) = pattern {
            require(pat.is_match(s), &format!("invalid value: {}", s))?;
        }
        require(seen.insert(s.to_string()), "duplicate list member")?;
    }
    Ok(())
}

fn local_file(root: Option<&Path>, value: &Value) -> VResult<PathBuf> {
    let s = nonempty_str(value, "")?;
    let part = s.splitn(2, '#').next().unwrap();
    let p = PathBuf::from(part);
    require(!part.is_empty() && !p.is_absolute(), "expected repository-relative file link")?;
    
    if let Some(r) = root {
        let path = r.join(&p).canonicalize().map_err(|_| Invalid(format!("link does not resolve to a file: {}", s)))?;
        let canon_root = r.canonicalize().map_err(|_| Invalid("invalid root".to_string()))?;
        require(path.starts_with(&canon_root), "link escapes repository")?;
        require(path.is_file(), &format!("link does not resolve to a file: {}", s))?;
        Ok(path)
    } else {
        require(!p.components().any(|c| matches!(c, std::path::Component::ParentDir)), "link escapes repository")?;
        Ok(p)
    }
}

fn links(root: Option<&Path>, values: &Value) -> VResult<()> {
    strings(values, true, None)?;
    if let Some(arr) = values.as_array() {
        for value in arr {
            local_file(root, value)?;
        }
    }
    Ok(())
}

fn check_basis(basis: &Value) -> VResult<()> {
    mapping(basis, "",
        Some(&["spec_revision", "spec_sha256", "sections_read", "dependencies", "source_pins",
          "harness_sha256", "guest_init_sha256", "emulator", "guest", "reference_module_sha256",
          "candidate_module_sha256", "toolchain", "model", "missing"]),
        Some(&[])
    )?;
    
    require(basis["spec_revision"].is_i64() && basis["spec_revision"].as_i64().unwrap() > 0, "invalid spec revision")?;
    
    for key in &["spec_sha256", "harness_sha256", "guest_init_sha256", "reference_module_sha256", "candidate_module_sha256"] {
        let nullable = *key != "spec_sha256";
        let val = &basis[*key];
        if nullable && val.is_null() {
            continue;
        }
        require(is_sha256(val), "expected full SHA-256")?;
    }
    let section_pat = regex::Regex::new(r"^[0-9]+(?:\.[0-9]+)*$").unwrap();
    strings(&basis["sections_read"], false, Some(&section_pat))?;
    if !basis["dependencies"].is_null() {
        strings(&basis["dependencies"], false, Some(&section_pat))?;
    }
    strings(&basis["missing"], false, None)?;
    
    require(basis["source_pins"].is_array(), "source_pins must be a list")?;
    let mut pin_ids = HashSet::new();
    for pin in basis["source_pins"].as_array().unwrap() {
        mapping(pin, "", Some(&["id", "version"]), Some(&["sha256", "commit"]))?;
        let id_str = nonempty_str(&pin["id"], "")?;
        nonempty_str(&pin["version"], "")?;
        pin_ids.insert(id_str.to_string());
        
        require(!pin["sha256"].is_null() || !pin["commit"].is_null(), "source pin lacks identity")?;
        if !pin["sha256"].is_null() {
            require(is_sha256(&pin["sha256"]), "expected full SHA-256")?;
        }
        if !pin["commit"].is_null() {
            let commit_str = pin["commit"].as_str().unwrap_or("");
            let commit_pat = regex::Regex::new(r"^[0-9a-f]{40}$").unwrap();
            require(commit_pat.is_match(commit_str), "invalid commit")?;
        }
    }
    require(pin_ids.len() == basis["source_pins"].as_array().unwrap().len(), "duplicate source pin")?;
    
    if !basis["emulator"].is_null() {
        mapping(&basis["emulator"], "", Some(&["id", "version", "sha256", "accel"]), Some(&[]))?;
        for key in &["id", "version", "accel"] {
            nonempty_str(&basis["emulator"][key], "")?;
        }
        require(is_sha256(&basis["emulator"]["sha256"]), "expected full SHA-256")?;
    }
    
    if !basis["guest"].is_null() {
        mapping(&basis["guest"], "", Some(&["kernel_sha256", "busybox_sha256", "initramfs_sha256"]), Some(&[]))?;
        for value in basis["guest"].as_object().unwrap().values() {
            if !value.is_null() {
                require(is_sha256(value), "expected full SHA-256")?;
            }
        }
    }
    
    if !basis["toolchain"].is_null() {
        nonempty_str(&basis["toolchain"], "")?;
    }
    
    if !basis["model"].is_null() {
        mapping(&basis["model"], "", Some(&["role", "name", "version"]), Some(&[]))?;
        let role = basis["model"]["role"].as_str().unwrap_or("");
        require(role == "reader" || role == "implementer" || role == "reviewer", "invalid model role")?;
        nonempty_str(&basis["model"]["name"], "")?;
        nonempty_str(&basis["model"]["version"], "")?;
    }
    
    Ok(())
}

fn check_shortfall(value: &Value) -> VResult<()> {
    let reason = value["reason"].as_str().unwrap_or("");
    let reasons = ["unobservable", "blocked", "out of scope", "not worth it"];
    require(reasons.contains(&reason), "invalid shortfall reason")?;
    nonempty_str(&value["reopen"], "")?;
    Ok(())
}

fn check_entry(entry: &Value, bases: &Value, root: Option<&Path>) -> VResult<()> {
    let common = vec!["id", "kind", "basis", "verdict", "rule", "status", "supersedes", "run_ids", "evidence"];
    let mut fields: HashMap<&str, Vec<&str>> = HashMap::new();
    fields.insert("qualification", vec!["claim", "validated_harness_sha256"]);
    fields.insert("result", vec!["claim", "round", "qualification", "qualified_evidence"]);
    fields.insert("observation", vec!["sections", "evidence_class"]);
    fields.insert("item", vec!["class", "source", "target", "disposition"]);
    fields.insert("verification", vec!["text", "sections", "evidence_classes", "verifier", "round", "independence", "purpose", "covers_revisions", "scope", "reading_id"]);
    fields.insert("candidate_round", vec!["round", "applied_items", "verification", "results", "scope"]);
    
    let kind = entry["kind"].as_str().unwrap_or("");
    require(fields.contains_key(kind), "invalid entry kind")?;
    
    let mut required = common.clone();
    required.extend(fields[kind].iter());
    
    let mut optional = vec!["decision", "cost"];
    if kind == "verification" {
        optional.extend(vec!["sequence", "assessment"]);
    }
    if kind == "item" {
        optional.extend(vec!["impact", "execution", "action"]);
    }
    if kind != "verification" {
        optional.extend(vec!["shortfall", "aliases"]);
    }
    
    mapping(entry, "", Some(&required), Some(&optional))?;
    
    let id_pat = regex::Regex::new(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$").unwrap();
    let id = nonempty_str(&entry["id"], "")?;
    require(id_pat.is_match(id), "invalid entry ID")?;
    
    let basis_id = nonempty_str(&entry["basis"], "")?;
    require(bases.as_object().unwrap().contains_key(basis_id), "unknown basis")?;
    
    nonempty_str(&entry["verdict"], "")?;
    nonempty_str(&entry["rule"], "")?;
    
    let status = &entry["status"];
    mapping(status, "", Some(&["state", "reason", "stale_since"]), Some(&[]))?;
    let state = status["state"].as_str().unwrap_or("");
    let states = ["current", "stale", "contested", "superseded"];
    require(states.contains(&state), "invalid status")?;
    nonempty_str(&status["reason"], "")?;
    
    if state == "stale" {
        nonempty_str(&status["stale_since"], "")?;
    } else {
        require(status["stale_since"].is_null(), "stale_since requires stale status")?;
    }
    
    strings(&entry["supersedes"], false, Some(&id_pat))?;
    strings(&entry["run_ids"], true, None)?;
    links(root, &entry["evidence"])?;
    
    if !entry["aliases"].is_null() {
        strings(&entry["aliases"], true, Some(&id_pat))?;
    }
    if !entry["shortfall"].is_null() {
        mapping(&entry["shortfall"], "", Some(&["reason", "reopen"]), Some(&[]))?;
        check_shortfall(&entry["shortfall"])?;
    }
    if !entry["decision"].is_null() {
        let decision = &entry["decision"];
        mapping(decision, "", Some(&["who", "date", "link"]), Some(&[]))?;
        nonempty_str(&decision["who"], "")?;
        require(is_iso_date_str(decision["date"].as_str().unwrap_or("")), "expected ISO date")?;
        local_file(root, &decision["link"])?;
    }
    if !entry["cost"].is_null() {
        mapping(&entry["cost"], "", Some(&[]), Some(&["seconds", "tokens", "usd"]))?;
        require(!entry["cost"].as_object().unwrap().is_empty(), "empty cost")?;
        for value in entry["cost"].as_object().unwrap().values() {
            require(value.is_number() && value.as_f64().unwrap() >= 0.0, "invalid cost")?;
        }
    }
    
    if kind == "qualification" || kind == "result" {
        nonempty_str(&entry["claim"], "")?;
    }
    
    let section_pat = regex::Regex::new(r"^[0-9]+(?:\.[0-9]+)*$").unwrap();

    if kind == "qualification" {
        let verdict = entry["verdict"].as_str().unwrap_or("");
        let valids = ["qualified", "shortfall", "unqualified", "insensitive"];
        require(valids.contains(&verdict), "invalid qualification verdict")?;
        require(is_sha256(&entry["validated_harness_sha256"]), "expected full SHA-256")?;
        require(!entry["shortfall"].is_null() == (verdict == "shortfall"), "shortfall verdict and details must agree")?;
    } else if kind == "result" {
        let verdict = entry["verdict"].as_str().unwrap_or("");
        require(["PASS", "FAIL", "ERROR"].contains(&verdict), "invalid result verdict")?;
        require(entry["qualified_evidence"].is_boolean(), "invalid qualified_evidence")?;
        nonempty_str(&entry["round"], "")?;
        nonempty_str(&entry["qualification"], "")?;
        require(is_sha256(&bases[basis_id]["candidate_module_sha256"]), "expected full SHA-256")?;
        require(is_sha256(&bases[basis_id]["harness_sha256"]), "expected full SHA-256")?;
    } else if kind == "observation" {
        strings(&entry["sections"], true, Some(&section_pat))?;
        require(entry["evidence_class"].as_str().unwrap_or("") == "emulated", "invalid observation class")?;
    } else if kind == "verification" {
        for key in &["text", "verifier", "round", "scope", "reading_id"] {
            nonempty_str(&entry[key], "")?;
        }
        let reading_id = entry["reading_id"].as_str().unwrap();
        require(id_pat.is_match(reading_id), "invalid reading ID")?;
        strings(&entry["sections"], true, Some(&section_pat))?;
        strings(&entry["evidence_classes"], true, None)?;
        let evidence_classes: HashSet<&str> = ["databook", "standard", "source-observed", "inference", "kernel", "emulated"].iter().cloned().collect();
        for ec in entry["evidence_classes"].as_array().unwrap() {
            require(evidence_classes.contains(ec.as_str().unwrap_or("")), "invalid verification evidence class")?;
        }
        if !entry["sequence"].is_null() {
            require(entry["sequence"].is_i64() && entry["sequence"].as_i64().unwrap() > 0, "invalid reading sequence")?;
        }
        if !entry["assessment"].is_null() {
            let assessment = &entry["assessment"];
            mapping(assessment, "", Some(&["accuracy_failures", "r_items", "evidence"]), Some(&[]))?;
            require(assessment["accuracy_failures"].is_i64() && assessment["accuracy_failures"].as_i64().unwrap() >= 0, "invalid accuracy failure count")?;
            strings(&assessment["r_items"], false, Some(&id_pat))?;
            links(root, &assessment["evidence"])?;
        }
        let independence = entry["independence"].as_str().unwrap_or("");
        require(["independent", "sequential", "adjudication", "gate"].contains(&independence), "invalid reading independence")?;
        let purpose = entry["purpose"].as_str().unwrap_or("");
        require(["accuracy", "transfer", "acceptance"].contains(&purpose), "invalid reading purpose")?;
        require((independence == "gate") == (purpose != "accuracy"), "gate cannot count as accuracy")?;
        
        let covered = &entry["covers_revisions"];
        require(covered.is_array() && !covered.as_array().unwrap().is_empty(), "invalid covered revisions")?;
        let mut cov_set = HashSet::new();
        for r in covered.as_array().unwrap() {
            require(r.is_i64() && r.as_i64().unwrap() > 0, "invalid covered revisions")?;
            require(cov_set.insert(r.as_i64().unwrap()), "duplicate covered revision")?;
        }
        let basis = &bases[basis_id];
        
        let mut entry_sections = HashSet::new();
        for s in entry["sections"].as_array().unwrap() {
            entry_sections.insert(s.as_str().unwrap());
        }
        let mut basis_sections = HashSet::new();
        for s in basis["sections_read"].as_array().unwrap() {
            basis_sections.insert(s.as_str().unwrap());
        }
        require(entry_sections.is_subset(&basis_sections), "verification sections outside reading basis")?;
        require(!basis["model"].is_null() && basis["model"]["role"].as_str().unwrap_or("") == "reader", "verification requires reader model")?;
    } else if kind == "candidate_round" {
        nonempty_str(&entry["round"], "")?;
        nonempty_str(&entry["scope"], "")?;
        for key in &["applied_items", "verification", "results"] {
            strings(&entry[key], *key != "results", Some(&id_pat))?;
        }
        require(is_sha256(&bases[basis_id]["candidate_module_sha256"]), "expected full SHA-256")?;
        require(is_sha256(&bases[basis_id]["harness_sha256"]), "expected full SHA-256")?;
    } else {
        nonempty_str(&entry["class"], "")?;
        if !entry["impact"].is_null() {
            mapping(&entry["impact"], "", Some(&["claims", "changes_status"]), Some(&[]))?;
            strings(&entry["impact"]["claims"], false, Some(&id_pat))?;
            require(entry["impact"]["changes_status"].is_boolean(), "invalid item status impact")?;
        }
        if !entry["execution"].is_null() {
            let exec = entry["execution"].as_str().unwrap_or("");
            require(["carry", "standalone"].contains(&exec), "invalid item execution")?;
        }
        if !entry["action"].is_null() {
            let action = entry["action"].as_str().unwrap_or("");
            require(["requirement-change", "implementation", "hardware-run", "recall", "adopt-source", "accept-shortfall", "outward-report"].contains(&action), "invalid tier-2 action")?;
        }
        let src = entry["source"].as_i64().unwrap_or(0);
        require(src == 1 || src == 2 || src == 3, "invalid item source")?;
        let target = entry["target"].as_str().unwrap_or("");
        require(["spec", "candidate", "records", "upstream", "hardware", "review"].contains(&target), "invalid item target")?;
        
        let disp = &entry["disposition"];
        mapping(disp, "", Some(&["state"]), Some(&["revision", "reason", "reopen", "destination"]))?;
        let d_state = disp["state"].as_str().unwrap_or("");
        require(["queued", "applied", "shortfall", "rejected"].contains(&d_state), "invalid disposition")?;
        
        let mut d_opt = vec![];
        if d_state == "queued" {
            d_opt.push("destination");
        } else if d_state == "applied" {
            d_opt.push("revision");
        } else if d_state == "shortfall" {
            d_opt.extend(vec!["reason", "reopen", "destination"]);
        } else if d_state == "rejected" {
            d_opt.push("reason");
        }
        mapping(disp, "", Some(&["state"]), Some(&d_opt))?;
        
        if !disp["destination"].is_null() {
            nonempty_str(&disp["destination"], "")?;
        }
        if d_state == "shortfall" {
            check_shortfall(disp)?;
        }
        if d_state == "applied" {
            require(disp["revision"].is_i64() && disp["revision"].as_i64().unwrap() > 0, "applied item needs revision")?;
        }
        if d_state == "rejected" {
            nonempty_str(&disp["reason"], "")?;
        }
    }
    Ok(())
}

fn check_history(status_doc: &Value, by_id: &HashMap<&str, &Value>, root: Option<&Path>) -> VResult<()> {
    let span = &status_doc["revision_range"];
    require(span.is_array() && span.as_array().unwrap().len() == 2, "invalid revision range")?;
    let span_arr = span.as_array().unwrap();
    require(span_arr[0].is_i64() && span_arr[0].as_i64().unwrap() > 0, "invalid revision range")?;
    require(span_arr[1].is_i64() && span_arr[1].as_i64().unwrap() > 0, "invalid revision range")?;
    let r0 = span_arr[0].as_i64().unwrap();
    let r1 = span_arr[1].as_i64().unwrap();
    require(r0 <= r1, "invalid revision range")?;
    
    let revisions = &status_doc["revisions"];
    require(revisions.is_object(), "revisions must be a mapping")?;
    let rev_obj = revisions.as_object().unwrap();
    
    let mut expected_revs = HashSet::new();
    for r in r0..=r1 {
        expected_revs.insert(r.to_string());
    }
    let actual_revs: HashSet<String> = rev_obj.keys().cloned().collect();
    require(expected_revs == actual_revs, "missing or unexpected revision in declared range")?;
    
    let bases = &status_doc["bases"];
    let mut reading_groups: HashMap<&str, Vec<&Value>> = HashMap::new();
    for entry in by_id.values() {
        if entry["kind"].as_str().unwrap_or("") == "verification" {
            reading_groups.entry(entry["reading_id"].as_str().unwrap()).or_default().push(*entry);
        }
    }
    
    for group in reading_groups.values() {
        let first = group[0];
        let mut sections = vec![];
        for entry in group {
            for key in &["sequence", "assessment"] {
                require(entry[*key] == first[*key], "inconsistent reading slices")?;
            }
            for key in &["basis", "text", "verdict", "round", "verifier", "independence", "purpose", "covers_revisions", "rule", "evidence_classes", "run_ids", "evidence", "scope"] {
                require(entry[*key] == first[*key], "inconsistent reading slices")?;
            }
            if let Some(arr) = entry["sections"].as_array() {
                for s in arr {
                    sections.push(s.as_str().unwrap().to_string());
                }
            }
        }
        let sec_len = sections.len();
        let sec_set: HashSet<_> = sections.into_iter().collect();
        require(sec_len == sec_set.len(), "overlapping reading slices")?;
        
        let basis_id = first["basis"].as_str().unwrap();
        let basis_sections: HashSet<_> = bases[basis_id]["sections_read"].as_array().unwrap().iter().map(|s| s.as_str().unwrap().to_string()).collect();
        require(sec_set == basis_sections, "missing reading section slice")?;
    }
    
    let mut sequences = HashSet::new();
    let mut seq_list = vec![];
    for group in reading_groups.values() {
        if !group[0]["sequence"].is_null() {
            let seq = group[0]["sequence"].as_i64().unwrap();
            seq_list.push(seq);
            sequences.insert(seq);
        }
    }
    require(seq_list.len() == sequences.len(), "duplicate reading sequence")?;
    
    let section_pat = regex::Regex::new(r"^[0-9]+(?:\.[0-9]+)*$").unwrap();
    let id_pat = regex::Regex::new(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$").unwrap();

    for (number_str, revision) in rev_obj {
        let number = number_str.parse::<i64>().unwrap();
        mapping(revision, "", Some(&["spec_sha256", "drafts", "requirement_change", "changed_sections", "items", "evidence", "run_ids"]), Some(&["started"]))?;
        if !revision["started"].is_null() {
            require(is_iso_date_str(revision["started"].as_str().unwrap_or("")), "expected ISO date")?;
        }
        require(is_sha256(&revision["spec_sha256"]), "expected full SHA-256")?;
        require(revision["drafts"].is_object(), "drafts must be a mapping")?;
        let spec_sha = revision["spec_sha256"].as_str().unwrap();
        for (key, value) in revision["drafts"].as_object().unwrap() {
            require(id_pat.is_match(key) && key != "landed", "invalid draft ID")?;
            require(is_sha256(value), "expected full SHA-256")?;
            require(value.as_str().unwrap() != spec_sha, "draft duplicates landed hash")?;
        }
        
        let changed = &revision["requirement_change"];
        require(changed.is_boolean() || (changed.is_null() && number == r0), "invalid requirement-change header")?;
        let is_changed = changed.as_bool();
        strings(&revision["changed_sections"], is_changed.is_some(), Some(&section_pat))?;
        strings(&revision["items"], false, Some(&id_pat))?;
        links(root, &revision["evidence"])?;
        strings(&revision["run_ids"], true, None)?;
        
        let mut applied_r = vec![];
        for item_id_val in revision["items"].as_array().unwrap() {
            let item_id = item_id_val.as_str().unwrap();
            let item = by_id.get(item_id);
            require(item.is_some(), "revision item must be applied to this spec revision")?;
            let item = item.unwrap();
            require(item["kind"] == "item" && item["target"] == "spec" && item["disposition"]["state"] == "applied" && item["disposition"]["revision"] == number, "revision item must be applied to this spec revision")?;
            let cls = item["class"].as_str().unwrap_or("");
            if cls != "E" && cls != "W" {
                applied_r.push(item_id);
            }
        }
        require(!applied_r.is_empty() == (is_changed == Some(true)), "requirement-change header needs matching R item chain")?;
        
        let mut has_readings = false;
        for entry in by_id.values() {
            if entry["kind"] == "verification" && entry["purpose"] == "accuracy" {
                if entry["covers_revisions"].as_array().unwrap().iter().any(|v| v.as_i64().unwrap() == number) {
                    has_readings = true;
                    break;
                }
            }
        }
        require(has_readings, &format!("revision {}: missing verification", number))?;
    }
    
    for entry in by_id.values() {
        let kind = entry["kind"].as_str().unwrap();
        if kind == "item" && entry["target"] == "spec" && entry["disposition"]["state"] == "applied" {
            let rev_num = entry["disposition"]["revision"].as_i64().unwrap();
            let destination = rev_obj.get(&rev_num.to_string());
            require(destination.is_some(), "applied spec item destination is missing")?;
            let dest = destination.unwrap();
            let items = dest["items"].as_array().unwrap();
            require(items.iter().any(|v| v.as_str().unwrap() == entry["id"].as_str().unwrap()), "applied spec item missing from destination header")?;
        }
        if kind != "verification" && kind != "candidate_round" {
            continue;
        }
        let basis_id = entry["basis"].as_str().unwrap();
        let basis = &bases[basis_id];
        let number = basis["spec_revision"].as_i64().unwrap();
        let revision = rev_obj.get(&number.to_string());
        require(revision.is_some(), "unknown history revision")?;
        let revision = revision.unwrap();
        
        if kind == "verification" {
            let text = entry["text"].as_str().unwrap();
            let expected = if text == "landed" {
                revision["spec_sha256"].as_str()
            } else {
                revision["drafts"][text].as_str()
            };
            require(expected.is_some() && basis["spec_sha256"].as_str() == expected, "verification spec_sha256 does not match revision text")?;
            
            let covers = entry["covers_revisions"].as_array().unwrap();
            let mut all_valid = true;
            let mut has_number = false;
            for r in covers {
                let r_val = r.as_i64().unwrap();
                if r_val == number {
                    has_number = true;
                }
                if !(rev_obj.contains_key(&r_val.to_string()) && r_val <= number) {
                    all_valid = false;
                }
            }
            require(has_number && all_valid, "covered revision does not match reading basis")?;
            
            if text != "landed" {
                require(entry["status"]["state"] == "superseded", "draft reading must remain superseded")?;
            }
            if entry["status"]["state"] == "current" {
                require(number == span_arr[1].as_i64().unwrap() || !basis["dependencies"].is_null(), "older reading without dependencies must widen, not stay current")?;
            }
        } else {
            require(basis["spec_sha256"] == revision["spec_sha256"], "candidate round spec hash does not match landed revision")?;
            for item_id_val in entry["applied_items"].as_array().unwrap() {
                let item_id = item_id_val.as_str().unwrap();
                let item = by_id[item_id];
                let in_items = revision["items"].as_array().unwrap().iter().any(|v| v.as_str().unwrap() == item_id);
                let cls = item["class"].as_str().unwrap_or("");
                require(in_items && cls != "E" && cls != "W", "candidate round lacks matching applied R item")?;
            }
            for reading_id_val in entry["verification"].as_array().unwrap() {
                let reading_id = reading_id_val.as_str().unwrap();
                let reading = by_id.get(reading_id);
                let ok = reading.is_some() 
                    && reading.unwrap()["kind"] == "verification" 
                    && reading.unwrap()["purpose"] == "accuracy" 
                    && reading.unwrap()["text"] == "landed" 
                    && bases[reading.unwrap()["basis"].as_str().unwrap()]["spec_revision"] == number;
                require(ok, "candidate round lacks landed verification link")?;
            }
            for result_id_val in entry["results"].as_array().unwrap() {
                let result_id = result_id_val.as_str().unwrap();
                let result = by_id.get(result_id);
                let ok = result.is_some()
                    && result.unwrap()["kind"] == "result"
                    && result.unwrap()["basis"] == entry["basis"]
                    && result.unwrap()["round"] == entry["round"];
                require(ok, "candidate round result basis or round mismatch")?;
            }
        }
    }
    
    Ok(())
}

fn check_scope(scope: &Value, claims: &HashMap<&str, &Value>, root: Option<&Path>) -> VResult<()> {
    if scope.is_null() {
        return Ok(());
    }
    mapping(scope, "", Some(&["claims", "accepted_classes", "target", "rules", "reader", "evidence"]), Some(&[]))?;
    let id_pat = regex::Regex::new(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$").unwrap();
    strings(&scope["claims"], true, Some(&id_pat))?;
    for claim in scope["claims"].as_array().unwrap() {
        require(claims.contains_key(claim.as_str().unwrap()), "unknown scope claim")?;
    }
    
    let scope_claims: Vec<&str> = scope["claims"].as_array().unwrap().iter().map(|v| v.as_str().unwrap()).collect();
    mapping(&scope["accepted_classes"], "", Some(&scope_claims), Some(&[]))?;
    for classes in scope["accepted_classes"].as_object().unwrap().values() {
        strings(classes, true, None)?;
        let evidence_classes: HashSet<&str> = ["databook", "standard", "source-observed", "inference", "kernel", "emulated"].iter().cloned().collect();
        for ec in classes.as_array().unwrap() {
            require(evidence_classes.contains(ec.as_str().unwrap_or("")), "invalid scope evidence class")?;
        }
    }
    
    nonempty_str(&scope["target"], "")?;
    mapping(&scope["rules"], "", Some(&["qualification", "result", "verification", "observation"]), Some(&[]))?;
    for rule in scope["rules"].as_object().unwrap().values() {
        nonempty_str(rule, "")?;
    }
    
    mapping(&scope["reader"], "", Some(&["name", "version"]), Some(&[]))?;
    for value in scope["reader"].as_object().unwrap().values() {
        nonempty_str(value, "")?;
    }
    
    links(root, &scope["evidence"])?;
    Ok(())
}

fn harness_check_names(harness_path: &Path) -> VResult<HashSet<String>> {
    let script = r#"
import ast, operator, sys, json

class Invalid(ValueError): pass
def require(condition, message):
    if not condition: raise Invalid(message)

def literal(node, env):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.Attribute):
        return None
    if isinstance(node, (ast.List, ast.Tuple)):
        return [literal(x, env) for x in node.elts]
    if isinstance(node, ast.BinOp):
        op = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.FloorDiv: operator.floordiv,
        }.get(type(node.op))
        if op:
            return op(literal(node.left, env), literal(node.right, env))
    if isinstance(node, ast.IfExp):
        return literal(node.body if literal(node.test, env) else node.orelse, env)
    if isinstance(node, ast.Subscript):
        return literal(node.value, env)[literal(node.slice, env)]
    if isinstance(node, ast.Slice):
        return slice(
            *(
                literal(x, env) if x else None
                for x in (node.lower, node.upper, node.step)
            )
        )
    if isinstance(node, ast.JoinedStr):
        parts = []
        for part in node.values:
            if isinstance(part, ast.Constant):
                parts.append(part.value)
            else:
                require(part.conversion == -1, "formatted conversion unsupported")
                require(part.format_spec is None, "format specification unsupported")
                value = literal(part.value, env)
                require(value is not None, "unresolved name expression")
                parts.append(format(value))
        return "".join(parts)
    if isinstance(node, ast.ListComp) and len(node.generators) == 1:
        gen = node.generators[0]
        require(not gen.ifs, "filtered name comprehension unsupported")
        result = []
        for value in literal(gen.iter, env):
            child = dict(env)
            bind(gen.target, value, child)
            result.append(literal(node.elt, child))
        return result
    raise Invalid("unsupported literal expression")

def maybe_literal(node, env):
    try:
        return literal(node, env)
    except (Invalid, TypeError, ValueError, KeyError, IndexError):
        return None

def name_candidates(node, env):
    if isinstance(node, ast.IfExp):
        test = maybe_literal(node.test, env)
        if test is None and not isinstance(node.test, ast.Constant):
            return name_candidates(node.body, env) + name_candidates(node.orelse, env)
        return name_candidates(node.body if test else node.orelse, env)
    if isinstance(node, ast.JoinedStr):
        options = [""]
        for part in node.values:
            if isinstance(part, ast.Constant):
                values = [part.value]
            elif part.conversion != -1 or part.format_spec is not None:
                return [None]
            else:
                values = [
                    format(v) for v in name_candidates(part.value, env) if v is not None
                ]
            options = [o + v for o in options for v in values]
            if not options or len(options) > 64:
                return [None]
        return options
    return [maybe_literal(node, env)]

def bind(target, value, env):
    if isinstance(target, ast.Name):
        env[target.id] = value
    elif isinstance(target, (ast.Tuple, ast.List)):
        if isinstance(value, (tuple, list)) and len(value) == len(target.elts):
            for sub, part in zip(target.elts, value):
                bind(sub, part, env)

def harness_check_names(code):
    tree = ast.parse(code)
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    globals_ = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                bind(target, maybe_literal(node.value, globals_), globals_)
    names = set()

    def calls(node, env, stack):
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            if isinstance(call.func, ast.Attribute):
                if call.func.attr in {"check", "defer"} and call.args:
                    if any(
                        k.arg == "check" and maybe_literal(k.value, env) is False
                        for k in call.keywords
                    ):
                        continue
                    for name in name_candidates(call.args[0], env):
                        if isinstance(name, str):
                            names.add(name)
            elif isinstance(call.func, ast.Name) and call.func.id in funcs:
                name = call.func.id
                if name in stack:
                    continue
                fn = funcs[name]
                child = dict(globals_)
                for arg, default in zip(
                    fn.args.args[-len(fn.args.defaults) :], fn.args.defaults
                ):
                    child[arg.arg] = maybe_literal(default, env)
                for arg, value in zip(fn.args.args, call.args):
                    child[arg.arg] = maybe_literal(value, env)
                for kw in call.keywords:
                    child[kw.arg] = maybe_literal(kw.value, env)
                walk(fn.body, child, stack | {name})

    def walk(nodes, env, stack):
        for node in nodes:
            if isinstance(node, ast.FunctionDef):
                continue
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                if node.value:
                    calls(node.value, env, stack)
                    value = maybe_literal(node.value, env)
                    for target in (
                        node.targets if isinstance(node, ast.Assign) else [node.target]
                    ):
                        bind(target, value, env)
            elif isinstance(node, ast.For):
                values = maybe_literal(node.iter, env)
                if isinstance(values, (tuple, list)):
                    for value in values:
                        child = dict(env)
                        bind(node.target, value, child)
                        walk(node.body, child, stack)
                else:
                    calls(node.iter, env, stack)
                    child = dict(env)
                    for target in ast.walk(node.target):
                        if isinstance(target, ast.Name):
                            child[target.id] = None
                    walk(node.body, child, stack)
            elif isinstance(node, ast.If):
                calls(node.test, env, stack)
                walk(node.body, dict(env), stack)
                walk(node.orelse, dict(env), stack)
            elif isinstance(node, ast.Try):
                handlers = [h.body for h in node.handlers]
                for body in [node.body, *handlers, node.orelse, node.finalbody]:
                    walk(body, dict(env), stack)
            else:
                calls(node, env, stack)

    for name, fn in funcs.items():
        if name.startswith("scenario_") or name == "settle":
            walk(fn.body, dict(globals_), {name})
    fn = funcs.get("trace_rules")
    if fn:
        for node in ast.walk(fn):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == "checks" and isinstance(node.value, ast.List):
                    for row in node.value.elts:
                        if isinstance(row, ast.Tuple) and row.elts:
                            name = maybe_literal(row.elts[0], globals_)
                            if isinstance(name, str):
                                names.add(name)
    return list(names)

with open(sys.argv[1], "r", encoding="utf-8") as f:
    print(json.dumps(harness_check_names(f.read())))
"#;
    let output = std::process::Command::new("python3")
        .arg("-c")
        .arg(script)
        .arg(harness_path)
        .output()
        .map_err(|e| Invalid(format!("failed to run python3: {}", e)))?;
    require(output.status.success(), "failed to run python AST walker")?;
    let stdout = String::from_utf8(output.stdout).map_err(|_| Invalid("python output not utf8".to_string()))?;
    let names: HashSet<String> = serde_json::from_str(&stdout).map_err(|_| Invalid("python output not valid JSON".to_string()))?;
    Ok(names)
}

pub fn validate(claims_doc: &Value, status_doc: &Value, root: Option<&Path>) -> VResult<Value> {
    mapping(claims_doc, "", Some(&["version", "campaign", "harness", "claims"]), Some(&[]))?;
    mapping(status_doc, "", Some(&["version", "campaign", "revision_range", "revisions", "bases", "entries"]), Some(&["scope"]))?;
    
    require(claims_doc["version"].is_i64() && claims_doc["version"].as_i64().unwrap() == 1
         && status_doc["version"].is_i64() && status_doc["version"].as_i64().unwrap() == 1,
         "unsupported format version")?;
         
    nonempty_str(&claims_doc["campaign"], "")?;
    require(claims_doc["campaign"] == status_doc["campaign"], "campaign mismatch")?;
    
    let names = if let Some(r) = root {
        let harness = local_file(Some(r), &claims_doc["harness"])?;
        Some(harness_check_names(&harness)?)
    } else {
        None
    };
    if let Some(ref n) = names {
        require(!n.is_empty(), "no harness check names found")?;
    }
    
    let claims = &claims_doc["claims"];
    require(claims.is_array() && !claims.as_array().unwrap().is_empty(), "claims must be a nonempty list")?;
    
    let mut by_claim = HashMap::new();
    let id_pat = regex::Regex::new(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$").unwrap();
    let section_pat = regex::Regex::new(r"^[0-9]+(?:\.[0-9]+)*$").unwrap();
    
    for claim in claims.as_array().unwrap() {
        mapping(claim, "", Some(&["id", "title", "mandatory", "cites", "checks", "scenarios", "scope", "defects", "evidence"]), Some(&[]))?;
        let id_str = nonempty_str(&claim["id"], "")?;
        require(id_pat.is_match(id_str), "invalid claim ID")?;
        require(!by_claim.contains_key(id_str), "duplicate claim ID")?;
        by_claim.insert(id_str, claim);
        
        nonempty_str(&claim["title"], "")?;
        nonempty_str(&claim["scope"], "")?;
        require(claim["mandatory"].is_boolean(), "invalid mandatory flag")?;
        
        strings(&claim["cites"], true, Some(&section_pat))?;
        strings(&claim["checks"], true, None)?;
        
        for name in claim["checks"].as_array().unwrap() {
            if let Some(ref n) = names {
                require(n.contains(name.as_str().unwrap()), &format!("{}: unknown harness check: {}", id_str, name.as_str().unwrap()))?;
            }
        }
        
        strings(&claim["scenarios"], true, Some(&id_pat))?;
        links(root, &claim["evidence"])?;
        
        require(claim["defects"].is_array(), "defects must be a list")?;
        for defect in claim["defects"].as_array().unwrap() {
            mapping(defect, "", Some(&["id", "run_ids", "control_runs", "outcome", "evidence"]), Some(&[]))?;
            nonempty_str(&defect["id"], "")?;
            strings(&defect["run_ids"], true, None)?;
            strings(&defect["control_runs"], true, None)?;
            
            let outcome = defect["outcome"].as_str().unwrap_or("");
            require(["detected", "unobservable", "insensitive", "equivalent", "not specific"].contains(&outcome), "invalid defect outcome")?;
            links(root, &defect["evidence"])?;
        }
    }
    
    let bases = &status_doc["bases"];
    require(bases.is_object() && !bases.as_object().unwrap().is_empty(), "bases must be a nonempty mapping")?;
    for (key, value) in bases.as_object().unwrap() {
        require(id_pat.is_match(key), "invalid basis ID")?;
        check_basis(value)?;
    }
    
    let entries = &status_doc["entries"];
    require(entries.is_array(), "entries must be a list")?;
    
    let mut by_id = HashMap::new();
    let mut all_ids = HashSet::new();
    
    for entry in entries.as_array().unwrap() {
        require(entry.is_object(), "entry must be a mapping")?;
        check_entry(entry, bases, root)?;
        
        let mut keys_to_check = vec![entry["id"].as_str().unwrap()];
        if let Some(arr) = entry["aliases"].as_array() {
            for a in arr {
                keys_to_check.push(a.as_str().unwrap());
            }
        }
        
        for key in keys_to_check {
            require(!all_ids.contains(key), &format!("duplicate entry ID or alias: {}", key))?;
            all_ids.insert(key.to_string());
        }
        by_id.insert(entry["id"].as_str().unwrap(), entry);
    }
    
    let mut qualifications = HashMap::new();
    let mut results = HashMap::new();
    
    for entry in entries.as_array().unwrap() {
        let kind = entry["kind"].as_str().unwrap();
        if kind == "item" && !entry["impact"].is_null() {
            for c in entry["impact"]["claims"].as_array().unwrap() {
                require(by_claim.contains_key(c.as_str().unwrap()), "unknown impact claim")?;
            }
        }
        if kind == "item" && entry["disposition"]["state"] == "shortfall" {
            if entry["target"] == "spec" && entry["class"] != "W" {
                require(!entry["impact"].is_null(), "spec shortfall requires explicit claim impact")?;
            }
            let mut any_mandatory = false;
            if let Some(impact) = entry.get("impact") {
                if let Some(arr) = impact.get("claims").and_then(|c| c.as_array()) {
                    for c in arr {
                        if by_claim[c.as_str().unwrap()]["mandatory"].as_bool().unwrap_or(false) {
                            any_mandatory = true;
                            break;
                        }
                    }
                }
            }
            if any_mandatory {
                require(entry.get("decision").and_then(|d| d.get("who")).and_then(|w| w.as_str()) == Some("user"), "mandatory shortfall requires user decision")?;
            }
        }
        if kind == "verification" && !entry["assessment"].is_null() {
            for item_id_val in entry["assessment"]["r_items"].as_array().unwrap() {
                let item_id = item_id_val.as_str().unwrap();
                let item = by_id.get(item_id);
                let ok = item.is_some() && item.unwrap().get("kind").and_then(|v| v.as_str()) == Some("item")
                      && item.unwrap().get("class").and_then(|v| v.as_str()) != Some("W")
                      && item.unwrap().get("class").and_then(|v| v.as_str()) != Some("E");
                require(ok, "reading R item must reference an R finding")?;
            }
        }
        for target_val in entry["supersedes"].as_array().unwrap() {
            let target = target_val.as_str().unwrap();
            require(by_id.contains_key(target), "supersedes target missing")?;
            let old = by_id[target];
            require(target != entry["id"].as_str().unwrap(), "self supersession")?;
            require(old["status"]["state"] == "superseded", "supersedes target must be superseded, never current")?;
            require(old["kind"] == entry["kind"] && old.get("claim") == entry.get("claim"), "supersedes target has different kind or claim")?;
        }
        if kind == "qualification" || kind == "result" {
            require(by_claim.contains_key(entry["claim"].as_str().unwrap()), "unknown claim reference")?;
        }
        if kind == "qualification" {
            let claim = by_claim[entry["claim"].as_str().unwrap()];
            if entry["status"]["state"] != "superseded" {
                *qualifications.entry(entry["claim"].as_str().unwrap()).or_insert(0) += 1;
            }
            if entry["verdict"] == "qualified" {
                let mut detected = false;
                for d in claim["defects"].as_array().unwrap() {
                    if d["outcome"] == "detected" { detected = true; break; }
                }
                require(detected, "qualified claim lacks detected defect")?;
            }
            if entry["verdict"] == "shortfall" && claim["mandatory"].as_bool().unwrap_or(false) {
                require(entry.get("decision").and_then(|d| d.get("who")).and_then(|w| w.as_str()) == Some("user"), "mandatory shortfall requires user decision")?;
            }
        }
        if kind == "result" {
            let ref_id = entry["qualification"].as_str().unwrap();
            let r_ref = by_id.get(ref_id);
            require(r_ref.is_some() && r_ref.unwrap()["kind"] == "qualification" && r_ref.unwrap()["claim"] == entry["claim"], "invalid result qualification link")?;
            let r_ref = r_ref.unwrap();
            if entry["qualified_evidence"].as_bool().unwrap_or(false) {
                require(r_ref["verdict"] == "qualified", "unqualified result labeled qualified")?;
            }
            if entry["status"]["state"] == "current" {
                *results.entry(entry["claim"].as_str().unwrap()).or_insert(0) += 1;
            }
        }
    }
    
    for claim in by_claim.keys() {
        require(*qualifications.get(claim).unwrap_or(&0) == 1, &format!("{}: expected one nonsuperseded qualification", claim))?;
        require(*results.get(claim).unwrap_or(&0) <= 1, &format!("{}: duplicate current result", claim))?;
    }
    
    for entry in entries.as_array().unwrap() {
        let mut seen = HashSet::new();
        let mut pending = vec![];
        for s in entry["supersedes"].as_array().unwrap() {
            pending.push(s.as_str().unwrap());
        }
        while let Some(target) = pending.pop() {
            require(target != entry["id"].as_str().unwrap(), "supersedes cycle")?;
            if seen.insert(target) {
                if let Some(old) = by_id.get(target) {
                    for s in old["supersedes"].as_array().unwrap() {
                        pending.push(s.as_str().unwrap());
                    }
                }
            }
        }
    }
    
    check_history(status_doc, &by_id, root)?;
    check_scope(&status_doc["scope"], &by_claim, root)?;
    
    let mut kind_counts = HashMap::new();
    for entry in entries.as_array().unwrap() {
        *kind_counts.entry(entry["kind"].as_str().unwrap().to_string()).or_insert(0) += 1;
    }
    let mut map = serde_json::Map::new();
    map.insert("claims".to_string(), json!(claims.as_array().unwrap().len()));
    for (k, v) in kind_counts {
        map.insert(k, json!(v));
    }
    
    Ok(Value::Object(map))
}

pub fn check_index() -> VResult<()> {
    Ok(())
}
