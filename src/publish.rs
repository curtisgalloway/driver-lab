// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::records::{Checker, SpecFile};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

// We assume these modules will be implemented by other swarm agents.
use crate::explorer;
use crate::render_html;
use crate::render_md;

/// Equivalent to argparse options.
#[derive(Debug, Clone)]
pub struct PublishOptions {
    pub root: PathBuf,
    pub context_root: Vec<PathBuf>,
    pub public_skill: Vec<String>,
    pub source_commit: Vec<String>,
    pub tool_commit: String,
    pub require_verified: Option<String>,
    pub out: PathBuf,
    pub fetch_anchors: bool,
}

pub struct PageInfo<'a> {
    pub stem: String,
    pub source: String,
    pub file: &'a SpecFile,
    pub merged: bool,
}

pub fn catalog(checker: &Checker) -> Result<Vec<PageInfo<'_>>, String> {
    let mut pages = Vec::new();
    for file in &checker.files {
        let root = &checker.roots[file.root_idx];
        if root.context {
            continue;
        }
        let rel_path = file.path.strip_prefix(&root.given).unwrap_or(&file.path);
        let source = format!("{}:{}", root.label(), rel_path.to_string_lossy());
        let mut hasher = Sha256::new();
        hasher.update(source.as_bytes());
        let stem = format!("spec-{:x}", hasher.finalize());
        pages.push(PageInfo {
            stem,
            source,
            file,
            merged: false,
        });
    }

    let mut overlays = BTreeSet::new();
    for file in &checker.files {
        let root = &checker.roots[file.root_idx];
        if !root.context && file.is_overlay() {
            overlays.insert(file.spec_id());
        }
    }

    for sid in overlays {
        let mut hasher = Sha256::new();
        hasher.update(sid.as_bytes());
        let stem = format!("merged-{:x}", hasher.finalize());
        let file = checker
            .files
            .iter()
            .find(|f| {
                let root = &checker.roots[f.root_idx];
                !root.context && f.spec_id() == sid
            })
            .expect("overlay file must exist");
        pages.push(PageInfo {
            stem,
            source: format!("merged:{}", sid),
            file,
            merged: true,
        });
    }

    if pages.is_empty() {
        return Err("no specs to publish".to_string());
    }
    Ok(pages)
}

pub fn payloads(
    checker: &Checker,
    args: &PublishOptions,
    anchors: Option<&serde_json::Value>,
) -> Result<std::collections::HashMap<String, String>, String> {
    let mut result = std::collections::HashMap::new();
    let mut entries = Vec::new();

    let pages = catalog(checker)?;
    for page in pages {
        let selected = checker;
        let mut roots = BTreeSet::new();
        for f in &selected.files {
            if f.spec_id() == page.file.spec_id() {
                let r = &selected.roots[f.root_idx];
                if page.merged || !r.context {
                    if let Ok(abs) = std::fs::canonicalize(&r.given) {
                        roots.insert(abs);
                    }
                }
            }
        }

        let mut commits = Vec::new();
        for value in &args.source_commit {
            if let Some((root_str, _sha)) = value.rsplit_once('=') {
                if let Ok(abs) = std::fs::canonicalize(Path::new(root_str)) {
                    if roots.contains(&abs) {
                        commits.push(value.clone());
                    }
                }
            } else {
                return Err("publishing requires ROOT=SHA source commits".into());
            }
        }

        let mut commit_roots = BTreeSet::new();
        for c in &commits {
            if let Some((root_str, _)) = c.rsplit_once('=') {
                if let Ok(abs) = std::fs::canonicalize(Path::new(root_str)) {
                    commit_roots.insert(abs);
                }
            }
        }
        if commit_roots != roots {
            return Err("every published root requires a source commit".into());
        }

        let spec_id = page.file.spec_id();
        let joined_commits = commits.join("\n");
        let commit_opt = if commits.is_empty() {
            None
        } else {
            Some(joined_commits.as_str())
        };
        let html = render_html::render(
            checker,
            Some(&spec_id),
            page.merged,
            true,
            commit_opt,
            Some(&args.tool_commit),
        )?;
        let md = render_md::render(
            checker,
            Some(&spec_id),
            page.merged,
            true,
            commit_opt,
            Some(&args.tool_commit),
        )?;

        result.insert(format!("{}.html", page.stem), html);
        result.insert(format!("{}.md", page.stem), md);

        let mut entry = serde_json::Map::new();
        entry.insert(
            "html".into(),
            serde_json::Value::String(format!("{}.html", page.stem)),
        );
        entry.insert(
            "markdown".into(),
            serde_json::Value::String(format!("{}.md", page.stem)),
        );
        entry.insert("source".into(), serde_json::Value::String(page.source));
        entry.insert(
            "spec".into(),
            serde_json::Value::String(page.file.spec_id()),
        );
        entries.push(serde_json::Value::Object(entry));
    }

    let default_anchors = explorer::empty_anchors_value();
    let anchors_ref = anchors.unwrap_or(&default_anchors);
    let anchors_json = explorer::dump_anchors(anchors_ref);
    result.insert("anchors.json".into(), anchors_json.clone());

    let loaded_anchors = explorer::load_anchors(&anchors_json, checker)?;
    let index_html = explorer::try_page(checker, &loaded_anchors, &entries, &args.tool_commit)?;
    result.insert("index.html".into(), index_html);

    let mut manifest_sha256 = serde_json::Map::new();
    let mut sorted_names: Vec<&String> = result.keys().collect();
    sorted_names.sort();
    for name in sorted_names {
        let text = &result[name];
        let mut hasher = Sha256::new();
        hasher.update(text.as_bytes());
        manifest_sha256.insert(
            name.clone(),
            serde_json::Value::String(format!("{:x}", hasher.finalize())),
        );
    }

    let mut manifest = serde_json::Map::new();
    manifest.insert("pages".into(), serde_json::Value::Array(entries));
    manifest.insert("sha256".into(), serde_json::Value::Object(manifest_sha256));

    let manifest_str = format!(
        "{}\n",
        serde_json::to_string_pretty(&manifest).unwrap_or_default()
    );
    result.insert("manifest.json".into(), manifest_str);

    Ok(result)
}

pub fn safe_output(out: &Path, checker: &Checker) -> Result<(), String> {
    let absolute = if out.is_absolute() {
        out.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(out)
    };

    let mut current = absolute.clone();
    loop {
        if let Ok(meta) = std::fs::symlink_metadata(&current) {
            if meta.file_type().is_symlink() {
                return Err("site output must not use symlinks".into());
            }
        }
        if let Some(parent) = current.parent() {
            current = parent.to_path_buf();
        } else {
            break;
        }
    }

    let absolute_resolved = absolute.canonicalize().unwrap_or(absolute);

    for root in &checker.roots {
        if let Ok(root_abs) = root.given.canonicalize() {
            if absolute_resolved.starts_with(&root_abs) {
                return Err("site output must be outside spec roots".into());
            }
        }
    }
    Ok(())
}

pub fn build(checker: &Checker, args: &PublishOptions) -> Result<(), String> {
    safe_output(&args.out, checker)?;
    if args.out.exists()
        && args
            .out
            .read_dir()
            .map(|mut i| i.next().is_some())
            .unwrap_or(false)
    {
        return Err("site output must be empty".into());
    }

    let anchors = if args.fetch_anchors {
        explorer::resolve_anchors(checker)
    } else {
        serde_json::from_str(&explorer::empty_anchors()).unwrap_or_default()
    };

    for line in explorer::unresolved_report(&anchors) {
        eprintln!("{}", line);
    }

    let expected = payloads(checker, args, Some(&anchors))?;
    std::fs::create_dir_all(&args.out).map_err(|e| e.to_string())?;

    for (name, text) in expected {
        std::fs::write(args.out.join(name), text).map_err(|e| e.to_string())?;
    }

    check(checker, args)
}

pub fn check(checker: &Checker, args: &PublishOptions) -> Result<(), String> {
    safe_output(&args.out, checker)?;
    let stored = args.out.join("anchors.json");

    if let Ok(meta) = std::fs::symlink_metadata(&stored) {
        if meta.file_type().is_symlink() || !meta.is_file() {
            return Err("site is missing anchors.json".into());
        }
    } else {
        return Err("site is missing anchors.json".into());
    }

    let anchors_text = std::fs::read_to_string(&stored).map_err(|e| e.to_string())?;
    explorer::load_anchors(&anchors_text, checker)?;

    let anchors_val: serde_json::Value =
        serde_json::from_str(&anchors_text).map_err(|_| "invalid anchors.json".to_string())?;
    let expected = payloads(checker, args, Some(&anchors_val))?;

    if !args.out.is_dir() {
        return Err("site is missing a spec page or has unexpected files".into());
    }

    let mut actual_files = BTreeSet::new();
    if let Ok(entries) = args.out.read_dir() {
        for entry in entries.flatten() {
            actual_files.insert(entry.file_name().to_string_lossy().to_string());
        }
    }

    let expected_files: BTreeSet<String> = expected.keys().cloned().collect();
    if actual_files != expected_files {
        return Err("site is missing a spec page or has unexpected files".into());
    }

    for (name, text) in expected {
        let path = args.out.join(&name);
        if let Ok(meta) = std::fs::symlink_metadata(&path) {
            if meta.file_type().is_symlink() || !meta.is_file() {
                return Err(format!("site entry must be a regular file: {}", name));
            }
        } else {
            return Err(format!("site entry must be a regular file: {}", name));
        }

        let actual_text = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
        if actual_text != text {
            return Err(format!("site page differs from checked sources: {}", name));
        }
    }

    Ok(())
}

/// Executes `hwspecs publish build|check` (`skills/spec-format/ci/publish.py`, `RT-8`).
pub fn run_publish_cmd(
    cli: &crate::Cli,
    args: &crate::PublishArgs,
    stdout: &mut dyn std::io::Write,
    stderr: &mut dyn std::io::Write,
) -> i32 {
    use crate::diagnostic::{EXIT_DOMAIN_FAILURE, EXIT_OK, EXIT_USAGE_ERROR};
    use serde_json::json;
    use std::collections::HashSet;

    let emit_fail = |code: i32,
                     msg: &str,
                     stdout: &mut dyn std::io::Write,
                     stderr: &mut dyn std::io::Write|
     -> i32 {
        if cli.json {
            let payload = json!({
                "ok": false,
                "error": if code == EXIT_USAGE_ERROR { "usage" } else { "domain" },
                "findings": [{"message": msg}],
            });
            let _ = writeln!(
                stdout,
                "{}",
                serde_json::to_string(&payload).unwrap_or_default()
            );
        } else {
            let _ = writeln!(stderr, "{msg}");
        }
        code
    };

    let mut mode: Option<String> = None;
    let mut root: Option<PathBuf> = None;
    let mut context_root = Vec::new();
    let mut public_skill = Vec::new();
    let mut source_commit = Vec::new();
    let mut tool_commit: Option<String> = None;
    let mut require_verified: Option<String> = None;
    let mut out: Option<PathBuf> = None;
    let mut fetch_anchors = false;

    let mut i = 0;
    while i < args.args.len() {
        let a = &args.args[i];
        match a.as_str() {
            "--context-root" => {
                i += 1;
                if let Some(v) = args.args.get(i) {
                    context_root.push(PathBuf::from(v));
                } else {
                    return emit_fail(
                        EXIT_USAGE_ERROR,
                        "--context-root requires a value",
                        stdout,
                        stderr,
                    );
                }
            }
            "--public-skill" => {
                i += 1;
                if let Some(v) = args.args.get(i) {
                    public_skill.push(v.clone());
                } else {
                    return emit_fail(
                        EXIT_USAGE_ERROR,
                        "--public-skill requires a value",
                        stdout,
                        stderr,
                    );
                }
            }
            "--source-commit" => {
                i += 1;
                if let Some(v) = args.args.get(i) {
                    source_commit.push(v.clone());
                } else {
                    return emit_fail(
                        EXIT_USAGE_ERROR,
                        "--source-commit requires a value",
                        stdout,
                        stderr,
                    );
                }
            }
            "--tool-commit" => {
                i += 1;
                if let Some(v) = args.args.get(i) {
                    tool_commit = Some(v.clone());
                } else {
                    return emit_fail(
                        EXIT_USAGE_ERROR,
                        "--tool-commit requires a value",
                        stdout,
                        stderr,
                    );
                }
            }
            "--require-verified" => {
                i += 1;
                if let Some(v) = args.args.get(i) {
                    require_verified = Some(v.clone());
                } else {
                    return emit_fail(
                        EXIT_USAGE_ERROR,
                        "--require-verified requires a value",
                        stdout,
                        stderr,
                    );
                }
            }
            "--out" => {
                i += 1;
                if let Some(v) = args.args.get(i) {
                    out = Some(PathBuf::from(v));
                } else {
                    return emit_fail(EXIT_USAGE_ERROR, "--out requires a value", stdout, stderr);
                }
            }
            "--root" => {
                i += 1;
                if let Some(v) = args.args.get(i) {
                    root = Some(PathBuf::from(v));
                } else {
                    return emit_fail(EXIT_USAGE_ERROR, "--root requires a value", stdout, stderr);
                }
            }
            "--fetch-anchors" => {
                fetch_anchors = true;
            }
            s if s.starts_with('-') => {
                return emit_fail(
                    EXIT_USAGE_ERROR,
                    &format!("unrecognized publish argument: {s}"),
                    stdout,
                    stderr,
                );
            }
            s => {
                if mode.is_none() {
                    mode = Some(s.to_string());
                } else if root.is_none() {
                    root = Some(PathBuf::from(s));
                } else {
                    return emit_fail(
                        EXIT_USAGE_ERROR,
                        &format!("unexpected positional argument: {s}"),
                        stdout,
                        stderr,
                    );
                }
            }
        }
        i += 1;
    }

    let Some(mode_str) = mode else {
        return emit_fail(
            EXIT_USAGE_ERROR,
            "publish requires a subcommand ('build' or 'check')",
            stdout,
            stderr,
        );
    };
    if !matches!(mode_str.as_str(), "build" | "check" | "verify") {
        return emit_fail(
            EXIT_USAGE_ERROR,
            &format!("unknown publish mode '{mode_str}' (expected 'build' or 'check')"),
            stdout,
            stderr,
        );
    }
    let Some(root_path) = root else {
        return emit_fail(
            EXIT_USAGE_ERROR,
            "publish requires a spec root path",
            stdout,
            stderr,
        );
    };
    let Some(out_path) = out else {
        return emit_fail(
            EXIT_USAGE_ERROR,
            "publish requires --out <DIR>",
            stdout,
            stderr,
        );
    };

    let opts = PublishOptions {
        root: root_path.clone(),
        context_root: context_root.clone(),
        public_skill: public_skill.clone(),
        source_commit,
        tool_commit: tool_commit.unwrap_or_else(|| crate::TOOL_COMMIT.to_string()),
        require_verified: require_verified.clone(),
        out: out_path,
        fetch_anchors,
    };

    let public_skills: HashSet<String> = public_skill.into_iter().collect();
    let schemas = crate::records::load_schemas();
    let mut checker = Checker::new(true, public_skills, require_verified);
    if let Err((_, msg)) = crate::speccheck::load_and_run_checker(
        &mut checker,
        &[root_path],
        &context_root,
        &[],
        &[],
        false,
        cli.offline,
        schemas,
    ) {
        return emit_fail(EXIT_DOMAIN_FAILURE, &msg, stdout, stderr);
    }

    let ordered = checker.ordered_findings();
    let errors: Vec<String> = ordered
        .iter()
        .filter(|f| f.level == "error")
        .map(ToString::to_string)
        .collect();
    if !errors.is_empty() {
        return emit_fail(EXIT_DOMAIN_FAILURE, &errors.join("\n"), stdout, stderr);
    }
    if checker.roots.iter().any(|r| !r.untrusted.is_empty()) {
        return emit_fail(
            EXIT_DOMAIN_FAILURE,
            "publishing context does not check clean",
            stdout,
            stderr,
        );
    }

    let res = if mode_str == "build" {
        build(&checker, &opts)
    } else {
        check(&checker, &opts)
    };

    match res {
        Ok(()) => {
            let count = catalog(&checker).map(|c| c.len()).unwrap_or(0);
            if cli.json {
                let payload = json!({
                    "ok": true,
                    "mode": mode_str,
                    "views": count,
                });
                let _ = writeln!(
                    stdout,
                    "{}",
                    serde_json::to_string(&payload).unwrap_or_default()
                );
            } else {
                let _ = writeln!(stdout, "{mode_str}: complete site ({count} spec views)");
            }
            EXIT_OK
        }
        Err(msg) => emit_fail(EXIT_DOMAIN_FAILURE, &msg, stdout, stderr),
    }
}
