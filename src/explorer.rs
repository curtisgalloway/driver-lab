use crate::records::Checker;
use serde_json::{json, Value};

pub fn empty_anchors() -> String {
    let v = json!({
        "format": 1,
        "anchors": {},
        "unresolved": []
    });
    serde_json::to_string(&v).unwrap()
}

pub fn dump_anchors(anchors: &Value) -> String {
    let mut s = serde_json::to_string_pretty(anchors).unwrap_or_else(|_| "{}".to_string());
    s.push('\n');
    s
}

pub fn load_anchors(anchors_json: &str, _checker: &Checker) -> Value {
    if let Ok(data) = serde_json::from_str::<Value>(anchors_json) {
        if data.get("format").and_then(|v| v.as_i64()) == Some(1) {
            return data;
        }
    }
    json!({
        "format": 1,
        "anchors": {},
        "unresolved": []
    })
}

pub fn page(checker: &Checker, _loaded_anchors: &Value, entries: &[Value], tool_commit: &str) -> String {
    // Extract specs data roughly corresponding to python data()
    let mut specs_map = std::collections::BTreeMap::new();
    
    for file in &checker.files {
        let root = &checker.roots[file.root_idx];
        if root.context { continue; }
        
        let spec_id = file.data.get("id").and_then(|v| v.as_str()).unwrap_or("");
        if !specs_map.contains_key(spec_id) {
            specs_map.insert(spec_id.to_string(), json!({
                "id": spec_id,
                "name": file.data.get("name").and_then(|v| v.as_str()).unwrap_or(spec_id),
                "kind": file.data.get("kind").and_then(|v| v.as_str()).unwrap_or(""),
                "triggers": file.data.get("triggers").unwrap_or(&json!([])),
                "orientation_html": "",
                "documents": [],
                "facts": [],
                "pages": []
            }));
        }
        
        let spec = specs_map.get_mut(spec_id).unwrap().as_object_mut().unwrap();
        
        if let Some(docs) = file.data.get("resources").and_then(|r| r.get("documents")).and_then(|d| d.as_array()) {
            let mut docs_arr = spec.get("documents").unwrap().as_array().unwrap().clone();
            for doc in docs {
                let class = doc.get("class").and_then(|v| v.as_str()).unwrap_or("");
                let title = doc.get("title").or(doc.get("name")).and_then(|v| v.as_str()).unwrap_or("");
                let url = doc.get("url").and_then(|v| v.as_str()).unwrap_or("");
                let pgs = doc.get("pages").and_then(|v| v.as_str()).unwrap_or("");
                docs_arr.push(json!({
                    "class": class,
                    "title": title,
                    "url": url, // Simplified: specmd.allowed_link validation omitted
                    "pages": pgs
                }));
            }
            spec.insert("documents".to_string(), json!(docs_arr));
        }
        
        let mut facts_arr = spec.get("facts").unwrap().as_array().unwrap().clone();
        for (id, rec) in &file.records {
            let title = rec.data.get("title").or(rec.data.get("name")).and_then(|v| v.as_str()).unwrap_or(id);
            let section = rec.data.get("section").and_then(|v| v.as_str()).unwrap_or("");
            let critical = rec.data.get("critical").and_then(|v| v.as_bool()).unwrap_or(false);
            
            facts_arr.push(json!({
                "ref": format!("{}:{}", root.label(), id),
                "id": id,
                "source": root.label().clone(),
                "section": section,
                "title": title,
                "claim_html": "",
                "text": "",
                "notes_html": [],
                "critical": critical,
                "gap": false,
                "contested": false,
                "conflicts": [],
                "assumes": [],
                "todo": null,
                "verdict": "",
                "date": "",
                "status": "",
                "carried": false,
                "second_reader_missing": false,
                "children": [],
                "verifier": "",
                "readers": [],
                "origin": root.label().clone(),
                "cites": []
            }));
        }
        spec.insert("facts".to_string(), json!(facts_arr));
    }
    
    for entry in entries {
        if let Some(spec_id) = entry.get("spec").and_then(|v| v.as_str()) {
            if let Some(spec) = specs_map.get_mut(spec_id) {
                let spec_obj = spec.as_object_mut().unwrap();
                let mut pgs = spec_obj.get("pages").unwrap().as_array().unwrap().clone();
                pgs.push(json!({
                    "label": entry.get("source").and_then(|v| v.as_str()).unwrap_or(""),
                    "html": entry.get("html").and_then(|v| v.as_str()).unwrap_or(""),
                    "markdown": entry.get("markdown").and_then(|v| v.as_str()).unwrap_or("")
                }));
                spec_obj.insert("pages".to_string(), json!(pgs));
            }
        }
    }
    
    let specs_arr: Vec<Value> = specs_map.into_values().collect();
    
    let payload = json!({
        "specs": specs_arr,
        "tool_commit": tool_commit
    });
    
    let payload_str = serde_json::to_string(&payload).unwrap()
        .replace("&", "\u{0026}")
        .replace("<", "\u{003c}")
        .replace(">", "\u{003e}");
    
    let html = include_str!("../skills/spec-format/scripts/explorer.html");
    let css = include_str!("../skills/spec-format/scripts/explorer.css");
    let js = include_str!("../skills/spec-format/scripts/explorer.js");

    format!(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">\n        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n        <title>Spec explorer</title><style>{}</style></head><body>\n        {}<script type=\"application/json\" id=\"spec-data\">{}</script>\n        <script>{}</script>\n</body></html>\n",
        css, html, payload_str, js
    )
}

pub fn resolve_anchors(_checker: &Checker) -> Value {
    json!({
        "format": 1,
        "anchors": {},
        "unresolved": []
    })
}

pub fn unresolved_report(anchors: &Value) -> Vec<String> {
    let mut res = Vec::new();
    if let Some(unresolved) = anchors.get("unresolved").and_then(|v| v.as_array()) {
        for u in unresolved {
            if let (Some(url), Some(heading), Some(reason)) = (
                u.get("url").and_then(|v| v.as_str()),
                u.get("heading").and_then(|v| v.as_str()),
                u.get("reason").and_then(|v| v.as_str())
            ) {
                res.push(format!("unresolved heading: {} :: {} ({})", url, heading, reason));
            }
        }
    }
    res
}
