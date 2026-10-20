use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

use saphyr_parser::{Parser, Span};

pub fn rewrite_file_check(path: &Path) -> Result<u32, String> {
    let info = path
        .symlink_metadata()
        .map_err(|_| "cannot rewrite a missing spec file".to_string())?;
    if info.is_symlink() {
        return Err("cannot rewrite a symbolic link spec file".to_string());
    }
    if info.nlink() > 1 {
        return Err("cannot rewrite a spec file with more than one hard link".to_string());
    }
    let mode = info.mode();
    if (mode & 0o4000) != 0 || (mode & 0o2000) != 0 {
        return Err("cannot rewrite a setuid or setgid spec file".to_string());
    }
    if (mode & 0o222) == 0 {
        return Err("cannot rewrite a spec file not writable by the user".to_string());
    }
    Ok(mode & 0o7777)
}

pub fn first_difference(
    expected: &serde_json::Value,
    actual: &serde_json::Value,
    at: &[String],
) -> Option<Vec<String>> {
    use serde_json::Value;
    if std::mem::discriminant(expected) != std::mem::discriminant(actual) {
        return Some(at.to_vec());
    }
    match (expected, actual) {
        (Value::Object(exp_map), Value::Object(act_map)) => {
            for (k, v) in exp_map {
                if let Some(act_v) = act_map.get(k) {
                    let mut new_at = at.to_vec();
                    new_at.push(k.clone());
                    if let Some(diff) = first_difference(v, act_v, &new_at) {
                        return Some(diff);
                    }
                } else {
                    let mut new_at = at.to_vec();
                    new_at.push(k.clone());
                    return Some(new_at);
                }
            }
            for k in act_map.keys() {
                if !exp_map.contains_key(k) {
                    let mut new_at = at.to_vec();
                    new_at.push(k.clone());
                    return Some(new_at);
                }
            }
        }
        (Value::Array(exp_arr), Value::Array(act_arr)) => {
            for (i, (left, right)) in exp_arr.iter().zip(act_arr.iter()).enumerate() {
                let mut new_at = at.to_vec();
                new_at.push(i.to_string());
                if let Some(diff) = first_difference(left, right, &new_at) {
                    return Some(diff);
                }
            }
            if exp_arr.len() != act_arr.len() {
                let mut new_at = at.to_vec();
                new_at.push(std::cmp::min(exp_arr.len(), act_arr.len()).to_string());
                return Some(new_at);
            }
        }
        _ => {
            if expected != actual {
                return Some(at.to_vec());
            }
        }
    }
    None
}

pub fn expected_rewrite(
    expected: &serde_json::Value,
    commit_at: &[String],
    commit: &str,
    changes: &[(Vec<String>, String, Option<Vec<usize>>)],
    was: &str,
) -> serde_json::Value {
    let mut data = expected.clone();

    fn get_mut<'a>(val: &'a mut serde_json::Value, path: &[String]) -> &'a mut serde_json::Value {
        let mut curr = val;
        for key in path {
            if curr.is_object() {
                curr = curr.as_object_mut().unwrap().get_mut(key).unwrap();
            } else if curr.is_array() {
                let idx: usize = key.parse().unwrap();
                curr = curr.as_array_mut().unwrap().get_mut(idx).unwrap();
            }
        }
        curr
    }

    if let Some((last, prefix)) = commit_at.split_last() {
        let parent = get_mut(&mut data, prefix);
        if parent.is_object() {
            parent
                .as_object_mut()
                .unwrap()
                .insert(last.clone(), serde_json::Value::String(commit.to_string()));
        } else if parent.is_array() {
            let idx: usize = last.parse().unwrap();
            parent.as_array_mut().unwrap()[idx] = serde_json::Value::String(commit.to_string());
        }
    }

    for (at, status, span) in changes {
        let node = get_mut(&mut data, at);
        if status == "moved" {
            if let Some(span) = span {
                let arr = span
                    .iter()
                    .map(|&x| serde_json::Value::Number(x.into()))
                    .collect();
                if node.is_object() {
                    node.as_object_mut()
                        .unwrap()
                        .insert("lines".to_string(), serde_json::Value::Array(arr));
                }
            }
        } else if status == "stale" {
            let mut stale_obj = serde_json::Map::new();
            stale_obj.insert(
                "was".to_string(),
                serde_json::Value::String(was.to_string()),
            );
            if node.is_object() {
                node.as_object_mut()
                    .unwrap()
                    .insert("stale".to_string(), serde_json::Value::Object(stale_obj));
            }
        }
    }

    data
}

pub fn comment_bytes(source: &str) -> Vec<u8> {
    use regex::Regex;
    let mut comments = Vec::new();
    let re = Regex::new(r"#[^\n]*").unwrap();
    for cap in re.captures_iter(source) {
        comments.extend_from_slice(cap[0].as_bytes());
    }
    comments
}

pub fn header_bytes(source: &str) -> Vec<u8> {
    let mut header = String::new();
    let mut rest = source;
    while let Some(pos) = rest.find('\n') {
        let (line, next_rest) = rest.split_at(pos + 1);
        if !line.trim().is_empty() && !line.trim_start().starts_with('#') {
            break;
        }
        header.push_str(line);
        rest = next_rest;
    }
    if header.is_empty() && (source.trim().is_empty() || source.trim_start().starts_with('#')) {
        header = source.to_string();
    }
    header.into_bytes()
}

pub fn verify_rewrite(
    source: &str,
    replacement: &str,
    _expected: &serde_json::Value,
    _actual: &serde_json::Value,
) -> Result<(), String> {
    if comment_bytes(source) != comment_bytes(replacement) {
        return Err("rewritten spec changed comment bytes; original retained".to_string());
    }
    if header_bytes(source) != header_bytes(replacement) {
        return Err("rewritten spec changed SPDX header bytes; original retained".to_string());
    }
    Ok(())
}

pub fn nodes(source: &str) -> HashMap<Vec<String>, Span> {
    let found = HashMap::new();
    let parser = Parser::new_from_str(source);
    for _event in parser {
        // ... saphyr parser events
    }
    found
}

pub fn rewrite(
    source: &str,
    _commit_at: &[&str],
    _commit: &str,
    _changes: &[(Vec<String>, String, Option<Vec<usize>>)],
    _was: &str,
) -> Result<String, String> {
    let _parser = Parser::new_from_str(source);
    // ... rewriting using saphyr-parser ...
    Ok(source.to_string())
}

pub fn replace_snapshot(path: &Path, original: &[u8], replacement: &[u8]) -> Result<(), String> {
    let mode = rewrite_file_check(path)?;
    let staged = path.with_extension("staged-rewrite");
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(mode)
        .open(&staged)
        .map_err(|_| "failed to create staged file")?;

    file.write_all(replacement).unwrap();
    file.sync_all().unwrap();

    if rewrite_file_check(path)? != mode {
        return Err("spec file mode changed during drift; original retained".to_string());
    }
    if fs::read(path).unwrap() != original {
        return Err("spec changed during drift; original retained".to_string());
    }
    fs::rename(staged, path).unwrap();
    Ok(())
}

pub fn run_drift_cmd(
    _cli: &crate::Cli,
    _args: &crate::DriftArgs,
    _scratch: &crate::sandbox::ScratchResolver,
    _stdout: &mut dyn std::io::Write,
    _stderr: &mut dyn std::io::Write,
) -> i32 {
    crate::diagnostic::EXIT_SANDBOX_ERROR
}

pub fn run(
    _args: &serde_json::Value,
    local: &HashMap<String, PathBuf>,
) -> Result<(i32, serde_json::Value), String> {
    let pin = "some_pin"; // logic based on args

    // Ensure no tempfiles when --repo is locally bound (ENV-1).
    let _scratch = if local.contains_key(pin) {
        None
    } else {
        Some(
            tempfile::Builder::new()
                .prefix("spec-drift-")
                .tempdir()
                .unwrap(),
        )
    };

    // Use scratch logic ...

    Ok((0, serde_json::Value::Null))
}
