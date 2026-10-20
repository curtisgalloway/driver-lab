// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::diagnostic::ExitCode;
use crate::docresolve::{citations as doc_citations, DocReader, PdfPages};
use crate::git_source::{Resolver, OperationalError, collect_spec_files_from_targets};
use crate::yaml_strict::{load_file, Loaded, PathSegment};
use crate::sandbox::ScratchResolver;
use crate::{Cli, ResolveArgs, ShowArgs};
use regex::Regex;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::path::PathBuf;
use std::sync::OnceLock;
use std::io::Write;

pub fn hex_values(text: &str) -> BTreeSet<u64> {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| {
        Regex::new(r"(?i)\b0x([0-9a-f](?:[0-9a-f_']*[0-9a-f])?)(?:u(?:ll|l)?|(?:ll|l)u?)?\b").unwrap()
    });
    let mut set = BTreeSet::new();
    for cap in re.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            let s = m.as_str().replace('_', "").replace('\'', "");
            if let Ok(v) = u64::from_str_radix(&s, 16) {
                set.insert(v);
            }
        }
    }
    set
}

pub fn anchors<'a>(
    data: &'a Value,
    base: Vec<String>,
) -> Vec<(&'a Map<String, Value>, Vec<String>)> {
    let mut entries = Vec::new();
    crate::docresolve::supports(data, base, true, &mut entries);
    let mut res = Vec::new();
    for (entry, path) in entries {
        if let Some(cls) = entry.get("class").and_then(|v| v.as_str()) {
            if cls == "src" || cls == "DT" || cls == "rtl" {
                if let Some(arr) = entry.get("anchors").and_then(|v| v.as_array()) {
                    for (a, anchor) in arr.iter().enumerate() {
                        if let Some(anchor_map) = anchor.as_object() {
                            let mut p = path.clone();
                            if p.last().map(|s| s.as_str()) == Some("impl") || p.last().map(|s| s.as_str()) == Some("ref") {
                                p.push(a.to_string());
                            } else {
                                p.push("anchors".to_string());
                                p.push(a.to_string());
                            }
                            res.push((anchor_map, p));
                        }
                    }
                }
            }
        }
    }
    res
}

pub fn check_url(url: &Value) -> Result<(), OperationalError> {
    if let Some(s) = url.as_str() {
        if s.starts_with("https://") && !s.chars().any(char::is_whitespace) {
            return Ok(());
        }
    }
    Err(OperationalError::fail("repository URL must be an https:// URL"))
}

pub fn check_commit(commit: &Value) -> Result<(), OperationalError> {
    if let Some(s) = commit.as_str() {
        if crate::git_source::is_valid_commit_oid(s) {
            return Ok(());
        }
    }
    Err(OperationalError::fail("pin must be a full lowercase commit id"))
}

pub fn listed_file<'a>(entry: &'a Map<String, Value>, anchor: &Map<String, Value>) -> Result<&'a Map<String, Value>, OperationalError> {
    let path = anchor.get("path").and_then(|v| v.as_str()).unwrap_or("");
    let mut listed = None;
    if let Some(files) = entry.get("files").and_then(|v| v.as_array()) {
        for f in files {
            if let Some(fmap) = f.as_object() {
                if fmap.get("path").and_then(|v| v.as_str()) == Some(path) {
                    if listed.is_some() {
                        return Err(OperationalError::fail(format!("{path}: must occur exactly once in the closed files list")));
                    }
                    listed = Some(fmap);
                }
            }
        }
    }
    listed.ok_or_else(|| OperationalError::fail(format!("{path}: must occur exactly once in the closed files list")))
}

pub fn check_anchor(entry: &Map<String, Value>, anchor: &Map<String, Value>) -> Result<(), OperationalError> {
    if anchor.contains_key("stale") {
        return Err(OperationalError::fail("stale anchor; re-verify before resolving"));
    }
    check_url(entry.get("url").unwrap_or(&Value::Null))?;
    check_commit(entry.get("commit").unwrap_or(&Value::Null))?;
    listed_file(entry, anchor)?;
    
    if let Some(lines) = anchor.get("lines").and_then(|v| v.as_array()) {
        if lines.len() == 2 {
            let s = lines[0].as_u64().unwrap_or(0);
            let e = lines[1].as_u64().unwrap_or(0);
            if !(1 <= s && s <= e) {
                return Err(OperationalError::fail("line range must be positive and ordered"));
            }
        }
    }
    Ok(())
}

fn display_line(line: &str) -> String {
    line.to_string()
}

pub fn run_resolve_cmd(cli: &Cli, args: &ResolveArgs, scratch: &ScratchResolver, stdout: &mut dyn Write, _stderr: &mut dyn Write) -> i32 {
    let timeout = 300;
    let limit_mb = 50;
    
    let target_files = match collect_spec_files_from_targets(&args.targets) {
        Ok(t) => t,
        Err(e) => return return_error(e.0, cli.json, stdout),
    };

    let mut resolver = match Resolver::new(
        &args.repos,
        args.docs_dir.clone(),
        args.root.clone(),
        timeout,
        limit_mb,
        cli.offline,
        scratch,
    ) {
        Ok(r) => r,
        Err(e) => return return_error(e.0, cli.json, stdout),
    };

    let (code, res) = run_impl(cli, false, &target_files, &mut resolver);
    print_result(res, cli.json, stdout);
    code
}

pub fn run_show_cmd(cli: &Cli, args: &ShowArgs, scratch: &ScratchResolver, stdout: &mut dyn Write, _stderr: &mut dyn Write) -> i32 {
    let timeout = 300;
    let limit_mb = 50;

    let mut resolver = match Resolver::new(
        &args.repos,
        args.docs_dir.clone(),
        args.root.clone(),
        timeout,
        limit_mb,
        cli.offline,
        scratch,
    ) {
        Ok(r) => r,
        Err(e) => return return_error(e.0, cli.json, stdout),
    };

    let raw_targets = if PathBuf::from(&args.fact_ref).exists() {
        vec![PathBuf::from(&args.fact_ref)]
    } else if let Some(ref r) = args.root {
        vec![r.clone()]
    } else {
        vec![]
    };
    let target_files = if raw_targets.is_empty() {
        vec![]
    } else {
        match collect_spec_files_from_targets(&raw_targets) {
            Ok(t) => t,
            Err(e) => return return_error(e.0, cli.json, stdout),
        }
    };
    let (code, res) = run_impl(cli, true, &target_files, &mut resolver);
    print_result(res, cli.json, stdout);
    code
}

fn return_error(msg: String, json_out: bool, stdout: &mut dyn Write) -> i32 {
    if json_out {
        let out = json!({
            "ok": false,
            "findings": [{
                "level": "error",
                "message": msg,
                "path": "",
                "line": 0,
                "column": 0
            }]
        });
        let _ = writeln!(stdout, "{}", serde_json::to_string_pretty(&out).unwrap());
    } else {
        let _ = writeln!(stdout, "error: {}", msg);
    }
    ExitCode::UsageError as i32
}

fn print_result(res: Value, json_out: bool, stdout: &mut dyn Write) {
    if json_out {
        let mut out = res.clone();
        if let Some(map) = out.as_object_mut() {
            map.remove("_text");
        }
        let _ = writeln!(stdout, "{}", serde_json::to_string_pretty(&out).unwrap());
    } else {
        if let Some(arr) = res.get("_text").and_then(|v| v.as_array()) {
            for line in arr {
                if let Some(s) = line.as_str() {
                    let _ = writeln!(stdout, "{}", s);
                }
            }
        }
    }
}

fn records(data: &Value) -> Vec<(&Value, Vec<String>)> {
    let mut res = Vec::new();
    for group in ["facts", "instances", "variants"] {
        if let Some(arr) = data.get(group).and_then(|v| v.as_array()) {
            for (i, rec) in arr.iter().enumerate() {
                if rec.is_object() {
                    res.push((rec, vec![group.to_string(), i.to_string()]));
                }
            }
        }
    }
    res
}

fn mark_for_at(loaded: &Loaded, at: &[String]) -> crate::yaml_strict::Mark {
    let segs: Vec<PathSegment> = at
        .iter()
        .map(|s| {
            if let Ok(idx) = s.parse::<usize>() {
                PathSegment::Index(idx)
            } else {
                PathSegment::Key(s.clone())
            }
        })
        .collect();
    loaded.mark(&segs, None)
}

fn run_impl(_cli: &Cli, is_show: bool, target_files: &[PathBuf], resolver: &mut Resolver) -> (i32, Value) {
    let mut findings_out = Vec::new();
    let mut anchors_out = Vec::new();
    let mut document_citations_out = Vec::new();
    let mut facts_out = Vec::new();

    for path in target_files {
        let loaded = load_file(path);
        let Some(data) = &loaded.data else {
            continue;
        };
        let path_str = path.to_string_lossy().to_string();

        let mut by_name = BTreeMap::new();
        if let Some(repos) = data.get("resources").and_then(|v| v.get("repos")).and_then(|v| v.as_array()) {
            for entry in repos {
                if let Some(m) = entry.as_object() {
                    if let Some(name) = m.get("name").and_then(|v| v.as_str()) {
                        by_name.entry(name.to_string()).or_insert_with(Vec::new).push(m.clone());
                    }
                }
            }
        }

        let mut documents: HashMap<String, (Value, DocReader)> = HashMap::new();
        if let Some(ref docs_dir) = resolver.docs_dir {
            if let Some(doc_arr) = data
                .get("resources")
                .and_then(|v| v.get("documents"))
                .and_then(|v| v.as_array())
            {
                for (i, doc) in doc_arr.iter().enumerate() {
                    let Some(doc_name) = doc.get("name").and_then(|v| v.as_str()) else {
                        continue;
                    };
                    let reader = if let Some(expected_sha) = doc.get("sha256").and_then(|v| v.as_str()) {
                        let doc_path = docs_dir.join(doc_name);
                        let check_res: Result<DocReader, String> = (|| {
                            let meta = fs::symlink_metadata(&doc_path)
                                .map_err(|_| format!("document {doc_name}: missing regular file"))?;
                            if meta.file_type().is_symlink() || !meta.is_file() {
                                return Err(format!("document {doc_name}: missing regular file"));
                            }
                            let mut file = fs::File::open(&doc_path)
                                .map_err(|_| format!("document {doc_name}: missing regular file"))?;
                            let mut hasher = Sha256::new();
                            let mut magic = [0u8; 5];
                            let mut magic_len = 0usize;
                            let mut buf = [0u8; 65536];
                            loop {
                                let n = std::io::Read::read(&mut file, &mut buf)
                                    .map_err(|_| format!("document {doc_name}: missing regular file"))?;
                                if n == 0 {
                                    break;
                                }
                                if magic_len < 5 {
                                    let take = (5 - magic_len).min(n);
                                    magic[magic_len..magic_len + take].copy_from_slice(&buf[..take]);
                                    magic_len += take;
                                }
                                hasher.update(&buf[..n]);
                            }
                            let digest = hex::encode(hasher.finalize());
                            if digest != expected_sha {
                                return Err(format!("document {doc_name}: sha256 mismatch"));
                            }
                            if magic_len == 5 && &magic == b"%PDF-" {
                                Ok(DocReader::Pdf(PdfPages::new(
                                    doc_path,
                                    resolver.timeout,
                                    resolver.limit,
                                )))
                            } else {
                                let lines = if meta.len() <= resolver.limit as u64 {
                                    fs::read(&doc_path).ok().and_then(|bytes| {
                                        if bytes.contains(&0) {
                                            None
                                        } else {
                                            std::str::from_utf8(&bytes)
                                                .ok()
                                                .map(|s| s.lines().map(String::from).collect())
                                        }
                                    })
                                } else {
                                    None
                                };
                                Ok(DocReader::NonPdf { lines })
                            }
                        })();
                        match check_res {
                            Ok(r) => r,
                            Err(msg) => {
                                let at = vec![
                                    "resources".to_string(),
                                    "documents".to_string(),
                                    i.to_string(),
                                    "sha256".to_string(),
                                ];
                                let mark = mark_for_at(&loaded, &at);
                                findings_out.push(json!({
                                    "path": path_str,
                                    "line": mark.line,
                                    "column": mark.column,
                                    "level": "error",
                                    "message": msg
                                }));
                                DocReader::ResolutionError(msg)
                            }
                        }
                    } else {
                        DocReader::Unpinned
                    };
                    documents.insert(doc_name.to_string(), (doc.clone(), reader));
                }
            }
        }

        for (record, base) in records(data) {
            let mut display = json!({
                "id": record.get("id").unwrap_or(&Value::Null),
                "claim": record.get("claim").unwrap_or_else(|| record.get("name").unwrap_or(&Value::Null)),
                "citations": []
            });
            let citations = display.get_mut("citations").unwrap().as_array_mut().unwrap();

            for (anchor, at) in anchors(record, base.clone()) {
                let repo_name = anchor.get("repo").and_then(|v| v.as_str()).unwrap_or("");
                let mut item = json!({
                    "repo": repo_name,
                    "path": anchor.get("path").unwrap_or(&Value::Null),
                    "fact": record.get("id").unwrap_or(&Value::Null),
                    "status": "failed",
                    "source": []
                });

                let mut resolve_err = None;

                if anchor.contains_key("stale") {
                    resolve_err = Some("stale anchor; re-verify before resolving".to_string());
                } else {
                    let choices = by_name.get(repo_name).cloned().unwrap_or_default();
                    if choices.len() != 1 {
                        resolve_err = Some("anchor repo must name exactly one repos entry".to_string());
                    } else {
                        let entry = &choices[0];
                        if let Err(e) = check_url(entry.get("url").unwrap_or(&Value::Null)) {
                            resolve_err = Some(e.message);
                        } else if let Err(e) = check_commit(entry.get("commit").unwrap_or(&Value::Null)) {
                            resolve_err = Some(e.message);
                        } else {
                            let url = entry.get("url").and_then(|v| v.as_str()).unwrap_or("");
                            let commit = entry.get("commit").and_then(|v| v.as_str()).unwrap_or("");
                            let mut blob_bytes = resolver.blob_bytes;
                            match resolver.open_repo(repo_name, url, commit) {
                                Ok(repo) => {
                                    let p = anchor.get("path").and_then(|v| v.as_str()).unwrap_or("");
                                    if !anchor.contains_key("search") {
                                        match repo.read_text(p, &mut blob_bytes) {
                                            Ok(text) => {
                                                resolver.blob_bytes = blob_bytes;
                                                let lines: Vec<String> = text.lines().map(|s| s.to_string()).collect();
                                                let mut start = 1;
                                                let mut end = lines.len();
                                                if let Some(arr) = anchor.get("lines").and_then(|v| v.as_array()) {
                                                    if arr.len() == 2 {
                                                        start = arr[0].as_u64().unwrap_or(0) as usize;
                                                        end = arr[1].as_u64().unwrap_or(0) as usize;
                                                    }
                                                }
                                                if start > 0 && start <= end && end <= lines.len() {
                                                    let source_arr = item.get_mut("source").unwrap().as_array_mut().unwrap();
                                                    for (idx, line) in lines[start - 1..end].iter().enumerate() {
                                                        source_arr.push(json!([start + idx, line]));
                                                    }
                                                    item["status"] = json!("resolved");
                                                    item["commit"] = json!(commit);
                                                } else {
                                                    resolve_err = Some(format!("line range is outside the file's {} lines", lines.len()));
                                                }
                                            }
                                            Err(_) => resolve_err = Some("git error".to_string()),
                                        }
                                    } else {
                                        item["status"] = json!("resolved");
                                        item["search"] = anchor.get("search").unwrap_or(&Value::Null).clone();
                                    }
                                }
                                Err(_) => resolve_err = Some("git error".to_string()),
                            }
                        }
                    }
                }

                if let Some(err) = resolve_err {
                    let mark = mark_for_at(&loaded, &at);
                    findings_out.push(json!({
                        "path": path_str,
                        "line": mark.line,
                        "column": mark.column,
                        "level": "error",
                        "message": format!("{}: {}", record.get("id").and_then(|v| v.as_str()).unwrap_or(""), err)
                    }));
                } else {
                    item["status"] = json!("resolved");
                }

                anchors_out.push(item.clone());
                citations.push(item);
            }

            if resolver.docs_dir.is_some() {
                let (doc_items, _doc_own_lines) = doc_citations(
                    record,
                    base.clone(),
                    &mut documents,
                    |where_at, msg, level| {
                        let mark = mark_for_at(&loaded, &where_at);
                        findings_out.push(json!({
                            "path": path_str,
                            "line": mark.line,
                            "column": mark.column,
                            "level": level,
                            "message": msg
                        }));
                    },
                );
                for di in doc_items {
                    let source_json: Vec<Value> = di
                        .source
                        .into_iter()
                        .map(|(page, lineno, line)| json!([page, lineno, line]))
                        .collect();
                    let ci_val = json!({
                        "doc": di.doc,
                        "locator": di.locator,
                        "fact": di.fact,
                        "status": di.status,
                        "source": source_json
                    });
                    document_citations_out.push(ci_val.clone());
                    citations.push(ci_val);
                }
            }

            if is_show {
                facts_out.push(display);
            }
        }
    }

    let errors = findings_out.iter().filter(|f| f.get("level").and_then(|v| v.as_str()).unwrap_or("error") == "error").count();
    
    let mut resolved = 0;
    let mut skipped = 0;
    for a in &anchors_out {
        if a.get("status").and_then(|v| v.as_str()) == Some("resolved") {
            resolved += 1;
        } else if a.get("status").and_then(|v| v.as_str()) == Some("skipped") {
            skipped += 1;
        }
    }

    let mut documents_resolved = 0;
    let mut documents_skipped = 0;
    for d in &document_citations_out {
        if d.get("status").and_then(|v| v.as_str()) == Some("resolved") {
            documents_resolved += 1;
        } else if d.get("status").and_then(|v| v.as_str()) == Some("skipped") {
            documents_skipped += 1;
        }
    }

    let mut result = json!({
        "ok": errors == 0,
        "files": target_files.iter().map(|p| {
            let p_str = p.to_string_lossy().to_string();
            let has_err = findings_out.iter().any(|f| {
                f.get("path").and_then(|v| v.as_str()) == Some(&p_str)
                    && f.get("level").and_then(|v| v.as_str()).unwrap_or("error") == "error"
            });
            json!({
                "path": p_str,
                "valid": !has_err
            })
        }).collect::<Vec<_>>(),
        "findings": findings_out,
        "anchors": anchors_out,
        "facts": facts_out,
        "document_citations": document_citations_out,
        "documents_resolved": documents_resolved,
        "documents_skipped": documents_skipped,
        "resolved": resolved,
        "skipped": skipped,
    });

    let mut text_lines = Vec::new();
    for fact in facts_out {
        text_lines.push(format!("{}: {}", fact.get("id").and_then(|v| v.as_str()).unwrap_or(""), fact.get("claim").and_then(|v| v.as_str()).unwrap_or("")));
        if let Some(citations) = fact.get("citations").and_then(|v| v.as_array()) {
            for citation in citations {
                if citation.get("doc").is_some() {
                    text_lines.push(format!(
                        "  {} {} [{}]",
                        citation.get("doc").and_then(|v| v.as_str()).unwrap_or(""),
                        citation.get("locator").unwrap_or(&Value::Null),
                        citation.get("status").and_then(|v| v.as_str()).unwrap_or("")
                    ));
                    if let Some(src) = citation.get("source").and_then(|v| v.as_array()) {
                        for src_item in src {
                            if let Some(arr) = src_item.as_array() {
                                if arr.len() == 3 {
                                    text_lines.push(format!(
                                        "  PDF page {}, {}: {}",
                                        arr[0].as_u64().unwrap_or(0),
                                        arr[1].as_u64().unwrap_or(0),
                                        display_line(arr[2].as_str().unwrap_or(""))
                                    ));
                                }
                            }
                        }
                    }
                    continue;
                }
                text_lines.push(format!("  {}:{} [{}]", citation.get("repo").and_then(|v| v.as_str()).unwrap_or(""), citation.get("path").and_then(|v| v.as_str()).unwrap_or(""), citation.get("status").and_then(|v| v.as_str()).unwrap_or("")));
                if let Some(src) = citation.get("source").and_then(|v| v.as_array()) {
                    for src_item in src {
                        if let Some(arr) = src_item.as_array() {
                            if arr.len() == 2 {
                                text_lines.push(format!("  {}: {}", arr[0].as_u64().unwrap_or(0), display_line(arr[1].as_str().unwrap_or(""))));
                            }
                        }
                    }
                }
            }
        }
    }
    for f in result.get("findings").and_then(|v| v.as_array()).unwrap_or(&Vec::new()) {
        text_lines.push(format!(
            "{}:{}:{}: {}: {}",
            f.get("path").and_then(|v| v.as_str()).unwrap_or(""),
            f.get("line").and_then(|v| v.as_u64()).unwrap_or(1),
            f.get("column").and_then(|v| v.as_u64()).unwrap_or(1),
            f.get("level").and_then(|v| v.as_str()).unwrap_or("error"),
            f.get("message").and_then(|v| v.as_str()).unwrap_or("")
        ));
    }
    text_lines.push(format!("{} anchor(s) resolved, {} skipped", resolved, skipped));
    if !result
        .get("document_citations")
        .and_then(|v| v.as_array())
        .map_or(true, Vec::is_empty)
    {
        text_lines.push(format!(
            "{} document citation(s) resolved, {} skipped",
            documents_resolved, documents_skipped
        ));
    }

    result.as_object_mut().unwrap().insert("_text".to_string(), json!(text_lines));

    (if errors > 0 { 1 } else { 0 }, result)
}
