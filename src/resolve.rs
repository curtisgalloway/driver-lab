// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::claimbind::{claim_findings, CitedSpan};
use crate::diagnostic::{ExitCode, Finding};
use crate::docresolve::{
    citations_with_options, DocReader, DocResolveOptions, PdfPages, DOC_CLASSES,
};
use crate::git_source::{
    collect_spec_files_from_targets, display_line, is_valid_commit_oid, node_range, symbol_in,
    GitError, OperationalError, PreconditionError, Resolver,
};
use crate::sandbox::ScratchResolver;
use crate::yaml_strict::{load_file, Loaded, PathSegment};
use crate::{Cli, ResolveArgs, ShowArgs};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

pub fn hex_values(text: &str) -> BTreeSet<u64> {
    crate::claimbind::hex_occurrences(text)
        .into_iter()
        .map(|(_, v)| v)
        .collect()
}

pub fn anchors(data: &Value, base: Vec<String>) -> Vec<(&Map<String, Value>, Vec<String>)> {
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
                            if p.last().map(|s| s.as_str()) == Some("impl")
                                || p.last().map(|s| s.as_str()) == Some("ref")
                            {
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
    Err(OperationalError::fail(
        "repository URL must be an https:// URL",
    ))
}

pub fn check_commit(commit: &Value) -> Result<(), OperationalError> {
    if let Some(s) = commit.as_str() {
        if is_valid_commit_oid(s) {
            return Ok(());
        }
    }
    Err(OperationalError::fail(
        "pin must be a full lowercase commit id",
    ))
}

pub fn listed_file<'a>(
    entry: &'a Map<String, Value>,
    anchor: &Map<String, Value>,
) -> Result<&'a Map<String, Value>, OperationalError> {
    let path = anchor.get("path").and_then(|v| v.as_str()).unwrap_or("");
    let mut listed = None;
    if let Some(files) = entry.get("files").and_then(|v| v.as_array()) {
        for f in files {
            if let Some(fmap) = f.as_object() {
                if fmap.get("path").and_then(|v| v.as_str()) == Some(path) {
                    if listed.is_some() {
                        return Err(OperationalError::fail(format!(
                            "{path}: must occur exactly once in the closed files list"
                        )));
                    }
                    listed = Some(fmap);
                }
            }
        }
    }
    listed.ok_or_else(|| {
        OperationalError::fail(format!(
            "{path}: must occur exactly once in the closed files list"
        ))
    })
}

pub fn check_anchor(
    entry: &Map<String, Value>,
    anchor: &Map<String, Value>,
) -> Result<(), OperationalError> {
    if anchor.contains_key("stale") {
        return Err(OperationalError::fail(
            "stale anchor; re-verify before resolving",
        ));
    }
    check_url(entry.get("url").unwrap_or(&Value::Null))?;
    check_commit(entry.get("commit").unwrap_or(&Value::Null))?;
    listed_file(entry, anchor)?;

    if let Some(lines) = anchor.get("lines").and_then(|v| v.as_array()) {
        if lines.len() == 2 {
            let s = lines[0].as_u64().unwrap_or(0);
            let e = lines[1].as_u64().unwrap_or(0);
            if !(1 <= s && s <= e) {
                return Err(OperationalError::fail(
                    "line range must be positive and ordered",
                ));
            }
        }
    }
    Ok(())
}

/// Collects unique `(name, commit)` pairs from `resources.repos` across `target_files`,
/// parsed strictly with `yaml_strict::load_file` (`BF-GW-23`).
pub fn discover_repo_pins(target_files: &[PathBuf]) -> Vec<(String, String)> {
    let mut seen = Vec::new();
    for path in target_files {
        let loaded = load_file(path);
        let Some(data) = &loaded.data else {
            continue;
        };
        let Some(repos) = data
            .get("resources")
            .and_then(|v| v.get("repos"))
            .and_then(Value::as_array)
        else {
            continue;
        };
        for entry in repos {
            let Some(m) = entry.as_object() else {
                continue;
            };
            let Some(name) = m.get("name").and_then(Value::as_str) else {
                continue;
            };
            let Some(commit) = m.get("commit").and_then(Value::as_str) else {
                continue;
            };
            if !name.is_empty() && is_valid_commit_oid(commit) {
                let pair = (name.to_string(), commit.to_string());
                if !seen.contains(&pair) {
                    seen.push(pair);
                }
            }
        }
    }
    seen
}

pub fn run_resolve_cmd(
    cli: &Cli,
    args: &ResolveArgs,
    scratch: &ScratchResolver,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let diag_out = cli.diag_out.as_deref();
    let target_files = match collect_spec_files_from_targets(&args.targets) {
        Ok(t) => t,
        Err(e) => {
            return return_error(
                e.0,
                ExitCode::UsageError,
                cli.json,
                diag_out,
                stdout,
                stderr,
            )
        }
    };

    if args.list_repos {
        let pins = discover_repo_pins(&target_files);
        let items: Vec<Value> = pins
            .iter()
            .map(|(n, c)| json!({"name": n, "commit": c}))
            .collect();
        let json_payload =
            serde_json::to_string_pretty(&json!({"ok": true, "repos": items})).unwrap();
        let _ = crate::diagnostic::write_diag_out(diag_out, &json_payload);
        if cli.json {
            let _ = writeln!(stdout, "{json_payload}");
        } else {
            for (name, commit) in pins {
                let _ = writeln!(stdout, "{name}\t{commit}");
            }
        }
        return ExitCode::Pass as i32;
    }

    let mut resolver = match Resolver::new(
        &args.repos,
        args.docs_dir.clone(),
        args.root.clone(),
        args.timeout,
        args.limit_mb,
        cli.offline,
        scratch,
    ) {
        Ok(r) => r,
        Err(e) => {
            return return_error(
                e.0,
                ExitCode::UsageError,
                cli.json,
                diag_out,
                stdout,
                stderr,
            )
        }
    };

    let doc_opts = DocResolveOptions {
        fail_on_skipped: args.fail_on_skipped_documents,
    };
    match run_impl(
        cli,
        false,
        args.strict_claims,
        &target_files,
        &mut resolver,
        doc_opts,
    ) {
        Ok((code, res)) => {
            print_result(&res, cli.json, diag_out, stdout, stderr);
            code
        }
        Err(pre) => return_error(
            pre.message,
            ExitCode::SandboxError,
            cli.json,
            diag_out,
            stdout,
            stderr,
        ),
    }
}

pub fn run_show_cmd(
    cli: &Cli,
    args: &ShowArgs,
    scratch: &ScratchResolver,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let diag_out = cli.diag_out.as_deref();
    let raw_targets = if !args.targets.is_empty() {
        args.targets.clone()
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
            Err(e) => {
                return return_error(
                    e.0,
                    ExitCode::UsageError,
                    cli.json,
                    diag_out,
                    stdout,
                    stderr,
                )
            }
        }
    };

    let mut resolver = match Resolver::new(
        &args.repos,
        args.docs_dir.clone(),
        args.root.clone(),
        args.timeout,
        args.limit_mb,
        cli.offline,
        scratch,
    ) {
        Ok(r) => r,
        Err(e) => {
            return return_error(
                e.0,
                ExitCode::UsageError,
                cli.json,
                diag_out,
                stdout,
                stderr,
            )
        }
    };

    match run_impl(
        cli,
        true,
        false,
        &target_files,
        &mut resolver,
        DocResolveOptions::default(),
    ) {
        Ok((code, res)) => {
            print_result(&res, cli.json, diag_out, stdout, stderr);
            code
        }
        Err(pre) => return_error(
            pre.message,
            ExitCode::SandboxError,
            cli.json,
            diag_out,
            stdout,
            stderr,
        ),
    }
}

fn return_error(
    msg: String,
    code: ExitCode,
    json_out: bool,
    diag_out: Option<&Path>,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let finding_code = crate::diagnostic::classify_resolve_finding_code(&msg);
    let out = json!({
        "ok": false,
        "findings": [{
            "level": "error",
            "code": finding_code,
            "message": msg,
            "path": "",
            "line": 0,
            "column": 0
        }]
    });
    if diag_out.is_some() {
        if let Ok(json_str) = serde_json::to_string_pretty(&out) {
            let _ = crate::diagnostic::write_diag_out(diag_out, &json_str);
        }
    }
    if json_out {
        let _ = writeln!(stdout, "{}", serde_json::to_string_pretty(&out).unwrap());
    } else {
        let prefix = match code {
            ExitCode::UsageError => "usage error",
            ExitCode::SandboxError => "missing precondition",
            _ => "error",
        };
        let _ = writeln!(stderr, "{prefix}: {msg}");
    }
    code as i32
}

fn print_result(
    res: &Value,
    json_out: bool,
    diag_out: Option<&Path>,
    stdout: &mut dyn Write,
    _stderr: &mut dyn Write,
) {
    if json_out || diag_out.is_some() {
        let mut out = res.clone();
        if let Some(map) = out.as_object_mut() {
            map.remove("_text");
        }
        let json_str = serde_json::to_string_pretty(&out).unwrap();
        let _ = crate::diagnostic::write_diag_out(diag_out, &json_str);
        if json_out {
            let _ = writeln!(stdout, "{json_str}");
        }
    }
    if !json_out {
        if let Some(arr) = res.get("_text").and_then(Value::as_array) {
            for line in arr {
                if let Some(s) = line.as_str() {
                    let _ = writeln!(stdout, "{s}");
                }
            }
        }
    }
}

fn records(data: &Value) -> Vec<(&Value, Vec<String>)> {
    let mut res = Vec::new();
    for group in ["facts", "instances", "variants"] {
        if let Some(arr) = data.get(group).and_then(Value::as_array) {
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

fn run_impl(
    _cli: &Cli,
    is_show: bool,
    strict_claims: bool,
    target_files: &[PathBuf],
    resolver: &mut Resolver,
    doc_opts: DocResolveOptions,
) -> Result<(i32, Value), PreconditionError> {
    let mut findings_out = Vec::new();
    let mut anchors_out = Vec::new();
    let mut document_citations_out = Vec::new();
    let mut facts_out = Vec::new();
    let mut declared_repo_names = BTreeSet::new();

    for path in target_files {
        let loaded = load_file(path);
        for lf in loaded.findings() {
            let code = crate::diagnostic::classify_resolve_finding_code(&lf.message);
            findings_out.push(json!({
                "path": lf.path,
                "line": lf.line,
                "column": lf.col,
                "level": lf.level.as_str(),
                "code": code,
                "message": lf.message,
            }));
        }
        let Some(data) = &loaded.data else {
            continue;
        };
        let path_str = path.to_string_lossy().to_string();

        let mut by_name = BTreeMap::new();
        if let Some(repos) = data
            .get("resources")
            .and_then(|v| v.get("repos"))
            .and_then(Value::as_array)
        {
            for entry in repos {
                if let Some(m) = entry.as_object() {
                    if let Some(name) = m.get("name").and_then(Value::as_str) {
                        declared_repo_names.insert(name.to_string());
                        by_name
                            .entry(name.to_string())
                            .or_insert_with(Vec::new)
                            .push(m.clone());
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
                    let reader = if let Some(expected_sha) =
                        doc.get("sha256").and_then(|v| v.as_str())
                    {
                        let doc_path = docs_dir.join(doc_name);
                        let check_res: Result<DocReader, String> = (|| {
                            let meta = fs::symlink_metadata(&doc_path).map_err(|_| {
                                format!("document {doc_name}: missing regular file")
                            })?;
                            if meta.file_type().is_symlink() || !meta.is_file() {
                                return Err(format!("document {doc_name}: missing regular file"));
                            }
                            let mut file = fs::File::open(&doc_path).map_err(|_| {
                                format!("document {doc_name}: missing regular file")
                            })?;
                            let mut hasher = Sha256::new();
                            let mut magic = [0u8; 5];
                            let mut magic_len = 0usize;
                            let mut buf = [0u8; 65536];
                            loop {
                                let n = std::io::Read::read(&mut file, &mut buf).map_err(|_| {
                                    format!("document {doc_name}: missing regular file")
                                })?;
                                if n == 0 {
                                    break;
                                }
                                if magic_len < 5 {
                                    let take = (5 - magic_len).min(n);
                                    magic[magic_len..magic_len + take]
                                        .copy_from_slice(&buf[..take]);
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
                                let code = crate::diagnostic::classify_resolve_finding_code(&msg);
                                findings_out.push(json!({
                                    "path": path_str,
                                    "line": mark.line,
                                    "column": mark.column,
                                    "level": "error",
                                    "code": code,
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
            let record_id = record.get("id").and_then(Value::as_str).unwrap_or("");
            let mut display = json!({
                "id": record.get("id").unwrap_or(&Value::Null),
                "claim": record.get("claim").unwrap_or_else(|| record.get("name").unwrap_or(&Value::Null)),
                "citations": []
            });
            let citations = display
                .get_mut("citations")
                .unwrap()
                .as_array_mut()
                .unwrap();
            let mut own_lines: Vec<String> = Vec::new();
            let mut pdf_own_lines: Vec<String> = Vec::new();
            let mut own_spans: Vec<CitedSpan> = Vec::new();

            for (anchor, at) in anchors(record, base.clone()) {
                let repo_name = anchor.get("repo").and_then(Value::as_str).unwrap_or("");
                let mut item = json!({
                    "repo": repo_name,
                    "path": anchor.get("path").unwrap_or(&Value::Null),
                    "fact": record.get("id").unwrap_or(&Value::Null),
                    "status": "failed",
                    "source": []
                });

                let mut resolve_err: Option<(String, bool)> = None;

                if anchor.contains_key("stale") {
                    resolve_err = Some((
                        "stale anchor; re-verify before resolving".to_string(),
                        false,
                    ));
                } else {
                    let choices = by_name.get(repo_name).cloned().unwrap_or_default();
                    if choices.len() != 1 {
                        resolve_err = Some((
                            "anchor repo must name exactly one repos entry".to_string(),
                            false,
                        ));
                    } else {
                        let entry = &choices[0];
                        if let Err(e) = check_anchor(entry, anchor) {
                            resolve_err = Some((e.message, e.skip));
                        } else {
                            let url = entry.get("url").and_then(Value::as_str).unwrap_or("");
                            let commit = entry.get("commit").and_then(Value::as_str).unwrap_or("");
                            let mut blob_bytes = resolver.blob_bytes;
                            match resolver.open_repo(repo_name, url, commit) {
                                Ok(repo) => {
                                    let p =
                                        anchor.get("path").and_then(Value::as_str).unwrap_or("");
                                    if !anchor.contains_key("search") {
                                        match repo.read_text(p, &mut blob_bytes) {
                                            Ok(text) => {
                                                resolver.blob_bytes = blob_bytes;
                                                let lines: Vec<String> =
                                                    text.lines().map(ToString::to_string).collect();
                                                let explicit_span = anchor
                                                    .get("lines")
                                                    .and_then(Value::as_array)
                                                    .filter(|a| a.len() == 2)
                                                    .map(|a| {
                                                        (
                                                            a[0].as_u64().unwrap_or(0) as usize,
                                                            a[1].as_u64().unwrap_or(0) as usize,
                                                        )
                                                    });
                                                let span_res: Result<
                                                    (usize, usize),
                                                    OperationalError,
                                                > = if let Some(node_name) =
                                                    anchor.get("node").and_then(Value::as_str)
                                                {
                                                    match node_range(&lines, node_name) {
                                                        Ok(nspan) => {
                                                            if let Some(espan) = explicit_span {
                                                                if !(nspan.0 <= espan.0
                                                                    && espan.0 <= espan.1
                                                                    && espan.1 <= nspan.1)
                                                                {
                                                                    Err(OperationalError::fail(
                                                                        "cited lines are outside the DT node",
                                                                    ))
                                                                } else {
                                                                    Ok(espan)
                                                                }
                                                            } else {
                                                                Ok(nspan)
                                                            }
                                                        }
                                                        Err(e) => Err(e),
                                                    }
                                                } else if let Some(espan) = explicit_span {
                                                    Ok(espan)
                                                } else {
                                                    Ok((1, lines.len()))
                                                };

                                                match span_res {
                                                    Ok((start, end)) => {
                                                        if start == 0
                                                            || start > end
                                                            || end > lines.len()
                                                        {
                                                            resolve_err = Some((
                                                                format!(
                                                                    "line range is outside the file's {} lines",
                                                                    lines.len()
                                                                ),
                                                                false,
                                                            ));
                                                        } else if let Some(sym) = anchor
                                                            .get("symbol")
                                                            .and_then(Value::as_str)
                                                        {
                                                            if !symbol_in(sym, &lines, (start, end))
                                                            {
                                                                resolve_err = Some((
                                                                    format!(
                                                                        "symbol '{sym}' is not near the cited range"
                                                                    ),
                                                                    false,
                                                                ));
                                                            }
                                                        }
                                                        if resolve_err.is_none() {
                                                            let source_arr = item
                                                                .get_mut("source")
                                                                .unwrap()
                                                                .as_array_mut()
                                                                .unwrap();
                                                            for (idx, line) in lines[start - 1..end]
                                                                .iter()
                                                                .enumerate()
                                                            {
                                                                source_arr.push(json!([
                                                                    start + idx,
                                                                    line
                                                                ]));
                                                            }
                                                            if at.len() == base.len() + 4
                                                                && at[..base.len()] == base[..]
                                                                && at
                                                                    .get(base.len())
                                                                    .map(String::as_str)
                                                                    == Some("support")
                                                            {
                                                                own_lines.extend(
                                                                    lines[start - 1..end]
                                                                        .iter()
                                                                        .cloned(),
                                                                );
                                                                own_spans.push(
                                                                    CitedSpan::from_file(
                                                                        &lines,
                                                                        start,
                                                                        end,
                                                                        anchor
                                                                            .get("symbol")
                                                                            .and_then(
                                                                                Value::as_str,
                                                                            ),
                                                                    ),
                                                                );
                                                            }
                                                            item["status"] = json!("resolved");
                                                            item["commit"] = json!(commit);
                                                        }
                                                    }
                                                    Err(e) => {
                                                        resolve_err = Some((e.message, e.skip));
                                                    }
                                                }
                                            }
                                            Err(GitError::Precondition(pre)) => return Err(pre),
                                            Err(GitError::Operational(op)) => {
                                                resolve_err = Some((op.message, op.skip));
                                            }
                                        }
                                    } else {
                                        item["status"] = json!("resolved");
                                        item["search"] =
                                            anchor.get("search").unwrap_or(&Value::Null).clone();
                                    }
                                }
                                Err(GitError::Precondition(pre)) => return Err(pre),
                                Err(GitError::Operational(op)) => {
                                    resolve_err = Some((op.message, op.skip));
                                }
                            }
                        }
                    }
                }

                if let Some((err, skip)) = resolve_err {
                    let mark = mark_for_at(&loaded, &at);
                    if skip {
                        item["status"] = json!("skipped");
                        let msg = format!("{record_id}: resolution skipped: {err}");
                        let code = crate::diagnostic::classify_resolve_finding_code(&msg);
                        findings_out.push(json!({
                            "path": path_str,
                            "line": mark.line,
                            "column": mark.column,
                            "level": "warning",
                            "code": code,
                            "message": msg
                        }));
                    } else {
                        let msg = format!("{record_id}: {err}");
                        let code = crate::diagnostic::classify_resolve_finding_code(&msg);
                        findings_out.push(json!({
                            "path": path_str,
                            "line": mark.line,
                            "column": mark.column,
                            "level": "error",
                            "code": code,
                            "message": msg
                        }));
                    }
                } else {
                    item["status"] = json!("resolved");
                }

                anchors_out.push(item.clone());
                citations.push(item);
            }

            let has_unextracted_own_doc = if resolver.docs_dir.is_some() {
                let doc_res = citations_with_options(
                    record,
                    base.clone(),
                    &mut documents,
                    doc_opts,
                    |where_at, msg, level| {
                        let mark = mark_for_at(&loaded, &where_at);
                        let code = crate::diagnostic::classify_resolve_finding_code(&msg);
                        findings_out.push(json!({
                            "path": path_str,
                            "line": mark.line,
                            "column": mark.column,
                            "level": level,
                            "code": code,
                            "message": msg
                        }));
                    },
                );
                if !doc_res.own_lines.is_empty() {
                    own_spans.push(CitedSpan::from_lines(&doc_res.own_lines));
                }
                own_lines.extend(doc_res.own_lines);
                pdf_own_lines.extend(doc_res.pdf_own_lines);
                for di in doc_res.items {
                    let mut source_json: Vec<Value> = di
                        .source
                        .into_iter()
                        .map(|(page, lineno, line)| json!([page, lineno, line]))
                        .collect();
                    source_json.extend(di.lines.into_iter().map(|(n, line)| json!([n, line])));
                    let mut ci_val = json!({
                        "doc": di.doc,
                        "locator": di.locator,
                        "fact": di.fact,
                        "status": di.status,
                        "source": source_json
                    });
                    if !di.format.is_empty() {
                        ci_val["format"] = json!(di.format);
                    }
                    if !di.headings.is_empty() {
                        ci_val["headings"] = json!(di.headings);
                    }
                    document_citations_out.push(ci_val.clone());
                    citations.push(ci_val);
                }
                doc_res.has_unextracted_own_doc
            } else {
                record
                    .get("support")
                    .and_then(Value::as_array)
                    .is_some_and(|arr| {
                        arr.iter().any(|s| {
                            s.get("class")
                                .and_then(Value::as_str)
                                .is_some_and(|cls| DOC_CLASSES.contains(&cls))
                        })
                    })
            };

            if !own_lines.is_empty() && !has_unextracted_own_doc {
                let claim_str = record.get("claim").and_then(Value::as_str).unwrap_or("");
                let claim_hex = hex_values(claim_str);
                let cited_hex = hex_values(&own_lines.join("\n"));
                let missing: Vec<String> = claim_hex
                    .difference(&cited_hex)
                    .map(|v| format!("0x{v:x}"))
                    .collect();
                if !missing.is_empty() {
                    let mut claim_at = base.clone();
                    claim_at.push("claim".to_string());
                    let mark = mark_for_at(&loaded, &claim_at);
                    let msg = format!(
                        "claim hex values absent from cited lines: {}",
                        missing.join(", ")
                    );
                    let code = crate::diagnostic::classify_resolve_finding_code(&msg);
                    findings_out.push(json!({
                        "path": path_str,
                        "line": mark.line,
                        "column": mark.column,
                        "level": "warning",
                        "code": code,
                        "message": msg
                    }));
                }
                for cf in claim_findings(claim_str, &own_spans) {
                    let mut claim_at = base.clone();
                    claim_at.push("claim".to_string());
                    let mark = mark_for_at(&loaded, &claim_at);
                    let level = if cf.always_error || strict_claims {
                        "error"
                    } else {
                        "warning"
                    };
                    findings_out.push(json!({
                        "path": path_str,
                        "line": mark.line,
                        "column": mark.column,
                        "level": level,
                        "code": cf.code,
                        "message": format!("{record_id}: {}", cf.message)
                    }));
                }
            }

            if !pdf_own_lines.is_empty() {
                if let Some(offset_str) = record
                    .get("data")
                    .and_then(|d| d.get("register"))
                    .and_then(|r| r.get("offset"))
                    .and_then(Value::as_str)
                {
                    let offset_hex = hex_values(offset_str);
                    let pdf_hex = hex_values(&pdf_own_lines.join("\n"));
                    if !offset_hex.is_subset(&pdf_hex) {
                        let mut off_at = base.clone();
                        off_at.push("data".to_string());
                        off_at.push("register".to_string());
                        off_at.push("offset".to_string());
                        let mark = mark_for_at(&loaded, &off_at);
                        let msg =
                            format!("register offset absent from cited PDF pages: {offset_str}");
                        let code = crate::diagnostic::classify_resolve_finding_code(&msg);
                        findings_out.push(json!({
                            "path": path_str,
                            "line": mark.line,
                            "column": mark.column,
                            "level": "warning",
                            "code": code,
                            "message": msg
                        }));
                    }
                }
            }

            if is_show {
                facts_out.push(display);
            }
        }
    }

    let default_path = target_files
        .first()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_default();
    let mut unused_findings: Vec<Finding> = Vec::new();
    resolver.check_unused_repos(&declared_repo_names, &default_path, &mut unused_findings);
    for uf in unused_findings {
        let code = if uf.code.is_empty() {
            crate::diagnostic::classify_resolve_finding_code(&uf.message).to_string()
        } else {
            uf.code
        };
        findings_out.push(json!({
            "path": uf.path,
            "line": uf.line,
            "column": uf.col,
            "level": uf.level.as_str(),
            "code": code,
            "message": uf.message,
        }));
    }

    let errors = findings_out
        .iter()
        .filter(|f| f.get("level").and_then(Value::as_str).unwrap_or("error") == "error")
        .count();

    let mut resolved = 0;
    let mut skipped = 0;
    for a in &anchors_out {
        if a.get("status").and_then(Value::as_str) == Some("resolved") {
            resolved += 1;
        } else if a.get("status").and_then(Value::as_str) == Some("skipped") {
            skipped += 1;
        }
    }

    let mut documents_resolved = 0;
    let mut documents_skipped = 0;
    let mut documents_failed = 0;
    for d in &document_citations_out {
        match d.get("status").and_then(|v| v.as_str()) {
            Some("resolved") => documents_resolved += 1,
            Some("skipped") => documents_skipped += 1,
            _ => documents_failed += 1,
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
        "documents_failed": documents_failed,
        "resolved": resolved,
        "skipped": skipped,
    });

    let mut text_lines = Vec::new();
    for fact in facts_out {
        text_lines.push(format!(
            "{}: {}",
            fact.get("id").and_then(Value::as_str).unwrap_or(""),
            fact.get("claim").and_then(Value::as_str).unwrap_or("")
        ));
        if let Some(citations) = fact.get("citations").and_then(Value::as_array) {
            for citation in citations {
                if citation.get("doc").is_some() {
                    text_lines.push(format!(
                        "  {} {} [{}]",
                        citation.get("doc").and_then(|v| v.as_str()).unwrap_or(""),
                        citation.get("locator").unwrap_or(&Value::Null),
                        citation
                            .get("status")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
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
                                } else if arr.len() == 2 {
                                    text_lines.push(format!(
                                        "  line {}: {}",
                                        arr[0].as_u64().unwrap_or(0),
                                        display_line(arr[1].as_str().unwrap_or(""))
                                    ));
                                }
                            }
                        }
                    }
                    continue;
                }
                text_lines.push(format!(
                    "  {}:{} [{}]",
                    citation.get("repo").and_then(Value::as_str).unwrap_or(""),
                    citation.get("path").and_then(Value::as_str).unwrap_or(""),
                    citation.get("status").and_then(Value::as_str).unwrap_or("")
                ));
                if let Some(src) = citation.get("source").and_then(Value::as_array) {
                    for src_item in src {
                        if let Some(arr) = src_item.as_array() {
                            if arr.len() == 2 {
                                text_lines.push(format!(
                                    "  {}: {}",
                                    arr[0].as_u64().unwrap_or(0),
                                    display_line(arr[1].as_str().unwrap_or(""))
                                ));
                            }
                        }
                    }
                }
            }
        }
    }
    for f in result
        .get("findings")
        .and_then(|v| v.as_array())
        .unwrap_or(&Vec::new())
    {
        text_lines.push(format!(
            "{}:{}:{}: {}: {}",
            f.get("path").and_then(|v| v.as_str()).unwrap_or(""),
            f.get("line").and_then(|v| v.as_u64()).unwrap_or(1),
            f.get("column").and_then(|v| v.as_u64()).unwrap_or(1),
            f.get("level").and_then(|v| v.as_str()).unwrap_or("error"),
            f.get("message").and_then(|v| v.as_str()).unwrap_or("")
        ));
    }
    text_lines.push(format!("{resolved} anchor(s) resolved, {skipped} skipped"));
    if resolver.docs_dir.is_some() || documents_resolved + documents_skipped + documents_failed > 0
    {
        text_lines.push(format!(
            "{documents_resolved} document citation(s) resolved, {documents_skipped} skipped"
        ));
    }

    result
        .as_object_mut()
        .unwrap()
        .insert("_text".to_string(), json!(text_lines));

    Ok((if errors > 0 { 1 } else { 0 }, result))
}
