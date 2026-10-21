// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Domain expert skill stub generator and `--check` verifier (`stubgen.py`, `RT-4`, `BF-IMX-ISS-4`).

use crate::diagnostic::{DiagnosticEnvelope, EXIT_DOMAIN_FAILURE, EXIT_OK, EXIT_USAGE_ERROR};
use crate::{prosefacts, yaml_strict, Cli, StubgenArgs};
use regex::Regex;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::Write;
use std::sync::OnceLock;

const TEMPLATE: &str = include_str!("../skills/board-spec-scaffold/templates/domain-stub-SKILL.md");

fn name_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[a-z0-9][a-z0-9-]*$").unwrap())
}

fn instance_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^([a-z0-9][a-z0-9-]*)#([a-z0-9][a-z0-9-]*)$").unwrap())
}

fn word_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"[a-z0-9][a-z0-9-]*").unwrap())
}

fn template_token_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"<(name|title|description|entry-ids|copyright-year> <copyright-holder|file-license|board|entry-lines|preload|profile-line)>",
        )
        .unwrap()
    })
}

fn py_str_list(items: &[&str]) -> String {
    let quoted: Vec<String> = items.iter().map(|s| format!("'{s}'")).collect();
    format!("[{}]", quoted.join(", "))
}

fn one_line(where_str: &str, value: Option<&Value>) -> Result<String, String> {
    let Some(v) = value else {
        return Err(format!(
            "{where_str}: a single line of text without backticks"
        ));
    };
    let Some(s) = v.as_str() else {
        return Err(format!(
            "{where_str}: a single line of text without backticks"
        ));
    };
    if s.trim().is_empty() || s.contains('\n') || s.contains('`') {
        return Err(format!(
            "{where_str}: a single line of text without backticks"
        ));
    }
    Ok(s.split_whitespace().collect::<Vec<_>>().join(" "))
}

/// Renders domain stub `SKILL.md` texts keyed by domain skill name (`stubgen.py:render`, `BF-IMX-ISS-4`).
pub fn render(manifest: &Value) -> Result<BTreeMap<String, String>, String> {
    let Some(obj) = manifest.as_object() else {
        let kind = if manifest.is_array() {
            "list"
        } else if manifest.is_string() {
            "str"
        } else if manifest.is_boolean() {
            "bool"
        } else if manifest.is_number() {
            "int"
        } else {
            "NoneType"
        };
        return Err(format!("the manifest is a mapping, not a {kind}"));
    };
    let top = ["format", "board", "copyright", "license", "domains"];
    let mut unknown: Vec<&str> = obj
        .keys()
        .map(String::as_str)
        .filter(|k| !top.contains(k))
        .collect();
    if !unknown.is_empty() {
        unknown.sort_unstable();
        let mut sorted_top = top.to_vec();
        sorted_top.sort_unstable();
        return Err(format!(
            "unknown top-level key(s) {}; the keys are {}",
            py_str_list(&unknown),
            py_str_list(&sorted_top)
        ));
    }
    if obj.get("format").and_then(Value::as_i64) != Some(2)
        || obj.get("format").is_some_and(Value::is_boolean)
    {
        return Err("format: 2 is required".into());
    }
    let board = obj
        .get("board")
        .and_then(Value::as_str)
        .filter(|s| name_regex().is_match(s))
        .ok_or_else(|| "board: a spec id".to_string())?;

    let copyright_ = one_line("copyright", obj.get("copyright"))?;
    let license_ = one_line("license", obj.get("license"))?;

    let domains = obj
        .get("domains")
        .and_then(Value::as_array)
        .filter(|a| !a.is_empty())
        .ok_or_else(|| "domains: a non-empty list".to_string())?;

    let fields = [
        "name",
        "title",
        "description",
        "entry",
        "instances",
        "preload",
        "split",
        "profile",
    ];
    let mut sorted_fields = fields.to_vec();
    sorted_fields.sort_unstable();

    struct ParsedDomain {
        name: String,
        unique_entries: Vec<String>,
        unique_insts: Vec<String>,
        preload: Vec<String>,
        text: BTreeMap<&'static str, String>,
    }

    let mut parsed_domains: Vec<ParsedDomain> = Vec::with_capacity(domains.len());
    let mut seen_names: BTreeSet<String> = BTreeSet::new();

    for (i, d_val) in domains.iter().enumerate() {
        let where_str = format!("domains[{i}]");
        let Some(d) = d_val.as_object() else {
            return Err(format!(
                "{where_str}: name, title, description and entry, and only {}",
                py_str_list(&sorted_fields)
            ));
        };
        let has_req = ["name", "title", "description", "entry"]
            .iter()
            .all(|k| d.contains_key(*k));
        let only_allowed = d.keys().all(|k| fields.contains(&k.as_str()));
        if !has_req || !only_allowed {
            return Err(format!(
                "{where_str}: name, title, description and entry, and only {}",
                py_str_list(&sorted_fields)
            ));
        }
        let name = d
            .get("name")
            .and_then(Value::as_str)
            .filter(|s| name_regex().is_match(s))
            .ok_or_else(|| format!("{where_str}.name: lower-case letters, digits and hyphens"))?;

        if !seen_names.insert(name.to_string()) {
            return Err(format!(
                "{where_str}.name: '{name}' is used twice; installed names must differ"
            ));
        }

        let entry = d
            .get("entry")
            .and_then(Value::as_array)
            .ok_or_else(|| format!("{where_str}.entry: a non-empty list of spec ids"))?;
        if entry.is_empty()
            || !entry
                .iter()
                .all(|e| e.as_str().is_some_and(|s| name_regex().is_match(s)))
        {
            return Err(format!("{where_str}.entry: a non-empty list of spec ids"));
        }

        let mut instances = Vec::new();
        if let Some(insts) = d.get("instances") {
            let arr = insts.as_array().ok_or_else(|| {
                format!("{where_str}.instances: a list of <spec>#<instance row> ids")
            })?;
            for x in arr {
                let s = x.as_str().ok_or_else(|| {
                    format!("{where_str}.instances: a list of <spec>#<instance row> ids")
                })?;
                if !instance_regex().is_match(s) {
                    return Err(format!(
                        "{where_str}.instances: a list of <spec>#<instance row> ids"
                    ));
                }
                instances.push(s.to_string());
            }
        }

        let mut preload = vec!["board-expert".to_string()];
        if let Some(p) = d.get("preload") {
            let arr = p
                .as_array()
                .ok_or_else(|| format!("{where_str}.preload: a non-empty list of skill names"))?;
            if arr.is_empty()
                || !arr
                    .iter()
                    .all(|x| x.as_str().is_some_and(|s| name_regex().is_match(s)))
            {
                return Err(format!(
                    "{where_str}.preload: a non-empty list of skill names"
                ));
            }
            preload = arr
                .iter()
                .map(|v| v.as_str().unwrap().to_string())
                .collect();
        }

        let mut text = BTreeMap::new();
        for k in ["title", "description", "split", "profile"] {
            if let Some(val) = d.get(k) {
                text.insert(k, one_line(&format!("{where_str}.{k}"), Some(val))?);
            }
        }
        for (&k, v) in &text {
            let findings = prosefacts::scan_text(v);
            if let Some(first) = findings.first() {
                return Err(format!(
                    "{where_str}.{k}: {}",
                    prosefacts::format_message(&first.what)
                ));
            }
        }

        let mut unique_entries = Vec::new();
        for e in entry {
            let e_str = e.as_str().unwrap().to_string();
            if !unique_entries.contains(&e_str) {
                unique_entries.push(e_str);
            }
        }
        let mut unique_insts = Vec::new();
        for x in instances {
            if !unique_insts.contains(&x) {
                unique_insts.push(x);
            }
        }

        parsed_domains.push(ParsedDomain {
            name: name.to_string(),
            unique_entries,
            unique_insts,
            preload,
            text,
        });
    }

    // BF-IMX-ISS-4: When multiple domain stubs share an entry spec, check whether each pair
    // already names the other in `split:`. If a pair of sibling domain stubs sharing an entry spec
    // does not name each other in either stub's `split:`, automatically include the unmentioned
    // sibling names in the generated `split:` clause so 3+ domain stubs sharing an entry spec
    // satisfy pairwise `check_overlap`.
    let split_words: Vec<BTreeSet<String>> = parsed_domains
        .iter()
        .map(|d| {
            d.text
                .get("split")
                .map(|s| {
                    word_regex()
                        .find_iter(s)
                        .map(|m| m.as_str().to_string())
                        .collect()
                })
                .unwrap_or_default()
        })
        .collect();

    let mut auto_siblings: Vec<Vec<String>> = vec![Vec::new(); parsed_domains.len()];
    for i in 0..parsed_domains.len() {
        for j in (i + 1)..parsed_domains.len() {
            let shares_entry = parsed_domains[i]
                .unique_entries
                .iter()
                .any(|e| parsed_domains[j].unique_entries.contains(e));
            if !shares_entry {
                continue;
            }
            let i_mentions_j = split_words[i].contains(&parsed_domains[j].name);
            let j_mentions_i = split_words[j].contains(&parsed_domains[i].name);
            if !i_mentions_j && !j_mentions_i {
                auto_siblings[i].push(parsed_domains[j].name.clone());
            }
        }
    }

    let mut out = BTreeMap::new();
    for (idx, d) in parsed_domains.into_iter().enumerate() {
        let mut lines = Vec::new();
        for e in &d.unique_entries {
            lines.push(format!("`spec: {e}`"));
        }
        for x in &d.unique_insts {
            lines.push(format!("`instance: {x}`"));
        }
        let extra_siblings = &auto_siblings[idx];
        match (d.text.get("split"), extra_siblings.is_empty()) {
            (Some(split), true) => {
                lines.push(format!("`split: {split}`"));
            }
            (Some(split), false) => {
                lines.push(format!(
                    "`split: {}; sibling domains: {}`",
                    split.trim_end_matches('.'),
                    extra_siblings.join(", ")
                ));
            }
            (None, false) => {
                lines.push(format!(
                    "`split: {board}-expert owns board integration; sibling domains: {}`",
                    extra_siblings.join(", ")
                ));
            }
            (None, true) => {}
        }

        let entry_ids = d
            .unique_entries
            .iter()
            .map(|e| format!("`{e}`"))
            .collect::<Vec<_>>()
            .join(", ");
        let preload_str = d
            .preload
            .iter()
            .map(|p| format!("`{p}`"))
            .collect::<Vec<_>>()
            .join(", ");
        let profile_line = d.text.get("profile").map_or_else(String::new, |p| {
            format!("\nOutput profile: {}.\n", p.trim_end_matches('.'))
        });
        let entry_lines_joined = lines.join("\n");
        let title_str = d.text.get("title").unwrap().as_str();
        let desc_str = d.text.get("description").unwrap().trim_end_matches('.');

        // Single-pass substitution so manifest values containing `<board>` etc. are not re-expanded.
        let out_text = template_token_regex()
            .replace_all(TEMPLATE, |caps: &regex::Captures<'_>| match &caps[1] {
                "name" => d.name.as_str(),
                "title" => title_str,
                "description" => desc_str,
                "entry-ids" => entry_ids.as_str(),
                "copyright-year> <copyright-holder" => copyright_.as_str(),
                "file-license" => license_.as_str(),
                "board" => board,
                "entry-lines" => entry_lines_joined.as_str(),
                "preload" => preload_str.as_str(),
                "profile-line" => profile_line.as_str(),
                _ => "",
            })
            .into_owned();

        out.insert(d.name, out_text);
    }

    Ok(out)
}

/// Executes `hwspecs stubgen` writing to `stdout` and `stderr`.
pub fn run_stubgen_cmd(
    cli: &Cli,
    args: &StubgenArgs,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let manifest_path = &args.domains_yaml;
    let loaded = yaml_strict::load_file(manifest_path);
    if !loaded.errors.is_empty() {
        let msgs: Vec<String> = loaded
            .errors
            .iter()
            .map(|err| {
                format!(
                    "{}:{}:{}: {}",
                    manifest_path.display(),
                    err.line,
                    err.column,
                    err.message
                )
            })
            .collect();
        if cli.json {
            let env = DiagnosticEnvelope::from_findings(Vec::new())
                .with_field("ok", json!(false))
                .with_field("errors", json!(msgs));
            let _ = writeln!(stdout, "{}", env.to_json_string());
        } else {
            for m in msgs {
                let _ = writeln!(stderr, "{m}");
            }
        }
        return EXIT_DOMAIN_FAILURE;
    }
    let manifest = loaded.data.unwrap_or(Value::Null);

    let stubs = match render(&manifest) {
        Ok(s) => s,
        Err(e) => {
            let msg = format!("{}: {e}", manifest_path.display());
            if cli.json {
                let env = DiagnosticEnvelope::from_findings(Vec::new())
                    .with_field("ok", json!(false))
                    .with_field("errors", json!([msg]));
                let _ = writeln!(stdout, "{}", env.to_json_string());
            } else {
                let _ = writeln!(stderr, "{msg}");
            }
            return EXIT_DOMAIN_FAILURE;
        }
    };

    let mut stale = 0;
    let mut status_lines = Vec::new();
    let mut err_lines = Vec::new();

    for (name, text) in &stubs {
        let path = args.out.join(name).join("SKILL.md");
        let current = fs::read_to_string(&path).ok();
        if current.as_deref() == Some(text.as_str()) {
            status_lines.push(format!("{}: current", path.display()));
            continue;
        }
        if args.check {
            status_lines.push(format!(
                "{}: {}",
                path.display(),
                if current.is_some() {
                    "stale"
                } else {
                    "missing"
                }
            ));
            stale += 1;
            continue;
        }
        if path.is_symlink() || path.parent().is_some_and(std::path::Path::is_symlink) {
            let msg = format!("{}: a symbolic link; not written", path.display());
            if cli.json {
                let env = DiagnosticEnvelope::from_findings(Vec::new())
                    .with_field("ok", json!(false))
                    .with_field("errors", json!([msg]));
                let _ = writeln!(stdout, "{}", env.to_json_string());
            } else {
                let _ = writeln!(stderr, "{msg}");
            }
            return EXIT_DOMAIN_FAILURE;
        }
        if let Err(e) = fs::create_dir_all(path.parent().unwrap()) {
            let msg = format!("{}: {e}", manifest_path.display());
            let _ = writeln!(stderr, "{msg}");
            return EXIT_USAGE_ERROR;
        }
        // Write atomically via a temporary sibling file without leaving `.tmp` behind.
        let tmp_path = path.with_extension("md.tmp");
        let write_res = (|| -> std::io::Result<()> {
            fs::write(&tmp_path, text.as_bytes())?;
            fs::rename(&tmp_path, &path)?;
            Ok(())
        })();
        if let Err(e) = write_res {
            let _ = fs::remove_file(&tmp_path);
            let msg = format!("{}: {e}", manifest_path.display());
            let _ = writeln!(stderr, "{msg}");
            return EXIT_USAGE_ERROR;
        }
        status_lines.push(format!("{}: written", path.display()));
    }

    let board = manifest.get("board").and_then(Value::as_str).unwrap_or("");
    let mark = format!("<!-- stubgen: {board} -->");

    if args.out.is_dir() {
        if let Ok(entries) = fs::read_dir(&args.out) {
            let mut dirs: Vec<_> = entries.flatten().map(|e| e.path()).collect();
            dirs.sort();
            for p in dirs {
                if p.is_dir() {
                    let skill_path = p.join("SKILL.md");
                    if skill_path.is_file() {
                        let name = p
                            .file_name()
                            .unwrap_or_default()
                            .to_string_lossy()
                            .to_string();
                        if !stubs.contains_key(&name) {
                            if let Ok(content) = fs::read_to_string(&skill_path) {
                                if content.lines().any(|l| l == mark) {
                                    err_lines.push(format!(
                                        "{}: orphan, not in the manifest; remove it or add it back",
                                        skill_path.display()
                                    ));
                                    stale += 1;
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    let exit_code = if stale > 0 {
        EXIT_DOMAIN_FAILURE
    } else {
        EXIT_OK
    };
    if cli.json {
        let mut env = DiagnosticEnvelope::from_findings(Vec::new())
            .with_field("subcommand", json!("stubgen"))
            .with_field("status", json!(status_lines))
            .with_field("errors", json!(err_lines));
        env.ok = exit_code == EXIT_OK;
        let _ = writeln!(stdout, "{}", env.to_json_string());
    } else {
        for line in status_lines {
            let _ = writeln!(stdout, "{line}");
        }
        for line in err_lines {
            let _ = writeln!(stderr, "{line}");
        }
    }
    exit_code
}

/// Convenience wrapper executing `stubgen` with standard stdout/stderr streams.
pub fn run(args: &StubgenArgs) -> i32 {
    let cli = Cli {
        json: false,
        scratch_dir: None,
        offline: false,
        version: false,
        command: None,
    };
    let mut out = std::io::stdout();
    let mut err = std::io::stderr();
    run_stubgen_cmd(&cli, args, &mut out, &mut err)
}
