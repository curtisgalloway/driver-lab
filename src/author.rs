// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::diagnostic::{EXIT_OK, EXIT_USAGE_ERROR};
use crate::sandbox::ScratchResolver;
use crate::{AssembleArgs, ResourceArgs};
use clap::Parser;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;

fn sha256_str(content: impl AsRef<[u8]>) -> String {
    let mut hasher = Sha256::new();
    hasher.update(content.as_ref());
    format!("{:064x}", hasher.finalize())
}

#[derive(Debug, Parser)]
#[command(name = "resource")]
pub enum ResourceCmd {
    PinFiles(PinFilesArgs),
    PinDoc(PinDocArgs),
}

#[derive(Debug, Parser)]
pub struct PinFilesArgs {
    #[arg(long = "repo", value_name = "ID=PATH")]
    pub repo: String,
    #[arg(long = "url")]
    pub url: Option<String>,
    #[arg(long = "ref", value_name = "REF")]
    pub ref_name: Option<String>,
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    pub relpath: Vec<String>,
}

#[derive(Debug, Parser)]
pub struct PinDocArgs {
    #[arg(long = "doc", value_name = "ID=PATH")]
    pub doc: String,
    #[arg(long = "title")]
    pub title: String,
    #[arg(long = "class")]
    pub class: String,
    #[arg(long = "license")]
    pub license: String,
    #[arg(long = "url")]
    pub url: Option<String>,
    #[arg(long = "access")]
    pub access: Option<String>,
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
}

pub fn run_resource_cmd(
    args: &ResourceArgs,
    _scratch: &ScratchResolver,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let mut args_vec = vec!["resource".to_string()];
    args_vec.extend(args.args.clone());
    let cmd = match ResourceCmd::try_parse_from(&args_vec) {
        Ok(c) => c,
        Err(e) => {
            let _ = write!(stderr, "{}", e);
            return EXIT_USAGE_ERROR;
        }
    };
    match cmd {
        ResourceCmd::PinFiles(pf) => pin_files(pf, stdout, stderr),
        ResourceCmd::PinDoc(pd) => pin_doc(pd, stdout, stderr),
    }
}

fn pin_files(args: PinFilesArgs, stdout: &mut dyn Write, stderr: &mut dyn Write) -> i32 {
    let parts: Vec<&str> = args.repo.split('=').collect();
    if parts.len() != 2 {
        let _ = writeln!(stderr, "error: --repo must be ID=PATH");
        return EXIT_USAGE_ERROR;
    }
    let id = parts[0];
    let path = Path::new(parts[1]);

    let output = match Command::new("git")
        .args(["rev-parse", "--verify", "HEAD"])
        .current_dir(path)
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            let _ = writeln!(stderr, "error: git rev-parse failed: {}", e);
            return EXIT_USAGE_ERROR;
        }
    };
    if !output.status.success() {
        let _ = writeln!(stderr, "error: git rev-parse failed");
        return EXIT_USAGE_ERROR;
    }
    let commit = String::from_utf8_lossy(&output.stdout).trim().to_string();

    // Read root
    let mut accepts = std::collections::BTreeSet::new();
    if let Some(root_path) = args.root {
        if let Ok(marker) = crate::spdx::load_root_marker(&root_path) {
            accepts = marker.accepts.iter().cloned().collect();
        }
    }

    let mut files = Vec::new();
    for rel in &args.relpath {
        let file_path = path.join(rel);
        let content = match fs::read_to_string(&file_path) {
            Ok(c) => c,
            Err(e) => {
                let _ = writeln!(stderr, "error: reading {}: {}", rel, e);
                return EXIT_USAGE_ERROR;
            }
        };

        let sha256 = sha256_str(&content);
        let lines = content.lines().count();
        let spdx = crate::spdx::scan_spdx_header(&content)
            .unwrap_or(None)
            .map(|s| s.raw_expression)
            .unwrap_or("NOASSERTION".to_string());

        if !accepts.is_empty() {
            if let Ok(expr) = crate::spdx::parse(&spdx) {
                if !crate::spdx::accepted(&expr, &accepts) {
                    let _ = writeln!(stderr, "error: license {} not accepted", spdx);
                    return EXIT_USAGE_ERROR;
                }
            } else {
                let _ = writeln!(stderr, "error: invalid spdx {}", spdx);
                return EXIT_USAGE_ERROR;
            }
        }

        let attr = crate::spdx::scan_attribution(&content);
        let notice = attr.names.join(", ");

        let mut file_obj = json!({
            "path": rel,
            "sha256": sha256,
            "lines": lines,
            "license": spdx,
        });
        if !notice.is_empty() {
            file_obj["notice"] = json!(notice);
        }
        files.push(file_obj);
    }

    let mut repo_obj = json!({
        "commit": commit,
        "files": files,
    });
    if let Some(url) = args.url {
        repo_obj["url"] = json!(url);
    }
    if let Some(ref_name) = args.ref_name {
        repo_obj["ref"] = json!(ref_name);
    }

    let doc = json!({ "resources": { "repos": { id: repo_obj } } });
    let _ = writeln!(stdout, "{}", serde_json::to_string_pretty(&doc).unwrap());
    EXIT_OK
}

fn pin_doc(args: PinDocArgs, stdout: &mut dyn Write, stderr: &mut dyn Write) -> i32 {
    let parts: Vec<&str> = args.doc.split('=').collect();
    if parts.len() != 2 {
        let _ = writeln!(stderr, "error: --doc must be ID=PATH");
        return EXIT_USAGE_ERROR;
    }
    let id = parts[0];
    let path = Path::new(parts[1]);

    let content = match fs::read(path) {
        Ok(c) => c,
        Err(e) => {
            let _ = writeln!(stderr, "error: reading {}: {}", path.display(), e);
            return EXIT_USAGE_ERROR;
        }
    };

    let sha256 = sha256_str(String::from_utf8_lossy(&content).as_bytes());
    let mut pages = 0;
    if crate::pdf::is_pdf_bytes(&content) {
        if let Ok(doc) = crate::pdf::load_pdf_document(&content) {
            pages = doc.get_pages().len();
        }
    }

    let mut doc_obj = json!({
        "title": args.title,
        "class": args.class,
        "sha256": sha256,
        "pages": pages,
        "license": args.license,
    });

    let mut retrieval = Vec::new();
    if let Some(url) = args.url {
        if url.contains("cache.nxp.com") || url.contains("documentation-service.arm.com") {
            retrieval.push(json!({"url": url}));
        } else {
            doc_obj["url"] = json!(url);
        }
    }
    if !retrieval.is_empty() {
        doc_obj["retrieval"] = json!(retrieval);
    }
    if let Some(access) = args.access {
        doc_obj["access"] = json!(access);
    }

    let doc = json!({ "resources": { "documents": { id: doc_obj } } });
    let _ = writeln!(stdout, "{}", serde_json::to_string_pretty(&doc).unwrap());

    if let Some(root) = args.root {
        let out_path = root.join("index").join(format!("{}.index.yaml", id));
        // invoke index
        crate::index::run_index_command_with_out(
            id,
            &root,
            &root, // docs_dir doesn't matter much for generating index if path provided
            Some(&out_path),
            &ScratchResolver::new(None),
        );
    }

    EXIT_OK
}

pub fn run_assemble_cmd(
    args: &AssembleArgs,
    _scratch: &ScratchResolver,
    _stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let mut merged_facts = serde_json::Map::new();
    for slice_path in &args.from {
        let content = fs::read_to_string(slice_path).unwrap();
        let val: Value = serde_json::from_str(&content).unwrap();
        if let Some(facts) = val.get("facts").and_then(|f| f.as_object()) {
            for (k, v) in facts {
                if merged_facts.contains_key(k) {
                    let _ = writeln!(stderr, "error: ID collision {}", k);
                    return EXIT_USAGE_ERROR;
                }
                merged_facts.insert(k.clone(), v.clone());
            }
        }
    }
    EXIT_OK
}

pub fn check_auto5_warnings(fact: &serde_json::Value) -> Vec<String> {
    let mut warnings = Vec::new();
    if let Some(meaning) = fact.get("meaning").and_then(|m| m.as_str()) {
        if meaning.contains("table")
            && fact.get("enumeratedValues").is_none()
            && fact.get("todo").is_none()
        {
            warnings.push("#103".to_string());
        }
    }
    if let Some(action) = fact.get("action").and_then(|a| a.as_str()) {
        let verbs = ["wait", "poll", "spin", "delay", "timeout", "handshake"];
        if verbs.iter().any(|&v| action.contains(v))
            && !action.contains("bound")
            && fact.get("note").is_none()
            && fact.get("todo").is_none()
        {
            warnings.push("#105".to_string());
        }
    }
    if fact.get("section").and_then(|s| s.as_str()) == Some("target")
        && fact.get("role").is_none()
        && fact.get("todo").is_none()
    {
        warnings.push("#150".to_string());
    }
    warnings
}

pub fn check_auto6_canonical_register_source(fact: &serde_json::Value) -> Vec<String> {
    let mut warnings = Vec::new();
    if let Some(repo) = fact.get("repo").and_then(|r| r.as_str()) {
        if repo.is_empty() {
            warnings.push("empty repo".to_string());
        }
    }
    warnings
}
