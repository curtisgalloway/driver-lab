// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::sandbox::{run_bounded, PipeLimits};
use regex::{Regex, RegexBuilder};
use serde_json::{Map, Value};
use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Command;

pub struct PdfPages {
    path: PathBuf,
    limit_bytes: usize,
    cache: HashMap<usize, Result<Vec<String>, String>>,
    size: usize,
}

impl PdfPages {
    pub fn new(path: PathBuf, _timeout_secs: u64, limit_bytes: usize) -> Self {
        Self {
            path,
            limit_bytes,
            cache: HashMap::new(),
            size: 0,
        }
    }

    pub fn page(&mut self, number: usize) -> Result<Vec<String>, String> {
        if !self.cache.contains_key(&number) {
            let res = self.extract(number);
            self.cache.insert(number, res);
        }
        self.cache.get(&number).unwrap().clone()
    }

    fn extract(&mut self, number: usize) -> Result<Vec<String>, String> {
        let mut cmd = Command::new("pdftotext");
        cmd.args(&[
            "-f",
            &number.to_string(),
            "-l",
            &number.to_string(),
            "-layout",
            "-enc",
            "UTF-8",
            self.path.to_str().unwrap(),
            "-",
        ]);
        let limits = PipeLimits {
            stdout_limit: self.limit_bytes.saturating_sub(self.size),
            stderr_limit: 1024,
        };
        let res = run_bounded(&mut cmd, limits).map_err(|e| e.to_string())?;
        if res.status != 0 {
            let stderr = String::from_utf8_lossy(&res.stderr);
            return Err(format!("ResolutionError: PDF extraction failed: {}", stderr.trim()));
        }
        self.size += res.stdout.len();
        let text = String::from_utf8_lossy(&res.stdout);
        Ok(text.lines().map(|s| s.to_string()).collect())
    }
}

pub fn locator_pattern(kind: &str, value: &str) -> Regex {
    let trimmed = value.trim().trim_end_matches(['.', ':']).trim();
    let base = if trimmed.is_empty() { value.trim() } else { trimmed };
    let kind_lower = kind.to_lowercase();
    let mut raw_tokens: Vec<&str> = base.split_whitespace().collect();
    if (kind_lower == "table" || kind_lower == "figure")
        && !raw_tokens
            .first()
            .is_some_and(|first| first.eq_ignore_ascii_case(&kind_lower))
    {
        raw_tokens.insert(0, &kind_lower);
    }

    let token_regexes: Vec<String> = raw_tokens
        .into_iter()
        .map(|token| {
            token
                .split(['-', '–'])
                .map(regex::escape)
                .collect::<Vec<_>>()
                .join("[-–]")
        })
        .collect();
    let token_str = token_regexes.join(r"\s+");
    let pat = format!(
        r"(?i)(?:^|[^\w.])(?:{})(?:$|[^\w.\-–]|\.(?:\W|$)|[-–](?:\D|$))",
        token_str
    );
    RegexBuilder::new(&pat).case_insensitive(true).build().unwrap()
}

pub enum DocReader {
    Pdf(PdfPages),
    NonPdf { lines: Option<Vec<String>> },
    Unpinned,
    ResolutionError(String),
}

pub struct CitationItem {
    pub doc: String,
    pub locator: Value,
    pub fact: String,
    pub status: String,
    pub source: Vec<(usize, usize, String)>,
}

pub const DOC_CLASSES: &[&str] = &["databook", "datasheet", "errata", "appnote", "standard", "doc"];

pub fn supports<'a>(
    data: &'a Value,
    base: Vec<String>,
    payload: bool,
    out: &mut Vec<(&'a Map<String, Value>, Vec<String>)>,
) {
    match data {
        Value::Object(map) => {
            for (key, value) in map {
                if key == "support" || key == "settled_by" {
                    if let Value::Array(arr) = value {
                        for (i, entry) in arr.iter().enumerate() {
                            if let Value::Object(entry_map) = entry {
                                let mut at = base.clone();
                                at.push(key.clone());
                                at.push(i.to_string());
                                out.push((entry_map, at));
                            }
                        }
                    }
                }
                let mut at = base.clone();
                at.push(key.clone());
                supports(value, at, false, out);
            }
            if payload {
                if let Some(data_map) = map.get("data").and_then(|v| v.as_object()) {
                    if let Some(_pair_map) = data_map.get("pair").and_then(|v| v.as_object()) {
                        // skip for docresolve
                    }
                }
            }
        }
        Value::Array(arr) => {
            for (i, value) in arr.iter().enumerate() {
                let mut at = base.clone();
                at.push(i.to_string());
                supports(value, at, false, out);
            }
        }
        _ => {}
    }
}

pub struct DocCitationsResult {
    pub items: Vec<CitationItem>,
    pub own_lines: Vec<String>,
    pub pdf_own_lines: Vec<String>,
    pub has_unextracted_own_doc: bool,
}

pub fn citations<F>(
    record: &Value,
    base: Vec<String>,
    documents: &mut HashMap<String, (Value, DocReader)>,
    add: F,
) -> (Vec<CitationItem>, Vec<String>)
where
    F: FnMut(Vec<String>, String, &str),
{
    let res = citations_with_status(record, base, documents, add);
    (res.items, res.own_lines)
}

pub fn citations_with_status<F>(
    record: &Value,
    base: Vec<String>,
    documents: &mut HashMap<String, (Value, DocReader)>,
    mut add: F,
) -> DocCitationsResult
where
    F: FnMut(Vec<String>, String, &str),
{
    let mut items = Vec::new();
    let mut own_lines = Vec::new();
    let mut pdf_own_lines = Vec::new();
    let mut has_unextracted_own_doc = false;
    let mut supports_list = Vec::new();
    supports(record, base.clone(), false, &mut supports_list);
    
    let fact_id = record.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let mut expected_support = base.clone();
    expected_support.push("support".to_string());

    for (support, at) in supports_list {
        let cls = match support.get("class").and_then(|v| v.as_str()) {
            Some(c) => c,
            None => continue,
        };
        if !DOC_CLASSES.contains(&cls) {
            continue;
        }
        let is_own_support = !at.is_empty() && at[..at.len() - 1] == expected_support;
        let name = match support.get("doc").and_then(|v| v.as_str()) {
            Some(n) => n.to_string(),
            None => {
                if is_own_support {
                    has_unextracted_own_doc = true;
                }
                continue;
            }
        };
        
        let at_locators = match support.get("at").and_then(|v| v.as_array()) {
            Some(arr) => arr.clone(),
            None => Vec::new(),
        };
        if at_locators.is_empty() && is_own_support {
            has_unextracted_own_doc = true;
        }

        for (index, locator) in at_locators.iter().enumerate() {
            let mut where_at = at.clone();
            where_at.push("at".to_string());
            where_at.push(index.to_string());

            let mut item = CitationItem {
                doc: name.clone(),
                locator: locator.clone(),
                fact: fact_id.clone(),
                status: "failed".to_string(),
                source: Vec::new(),
            };

            let doc_entry = documents.get_mut(&name);
            let (doc_info, reader_state) = match doc_entry {
                Some(entry) => entry,
                None => {
                    if is_own_support {
                        has_unextracted_own_doc = true;
                    }
                    item.status = "skipped".to_string();
                    add(where_at.clone(), format!("{}: {}: PDF evidence skipped: document is not declared", fact_id, name), "warning");
                    items.push(item);
                    continue;
                }
            };

            let has_pdf_url = ["url", "retrieval"].iter().any(|k| {
                doc_info
                    .get(*k)
                    .and_then(|v| v.as_str())
                    .is_some_and(|u| {
                        let path_part = u.split(['?', '#']).next().unwrap_or(u);
                        path_part.to_ascii_lowercase().ends_with(".pdf")
                    })
            });
            let is_pdf_doc = doc_info.get("page_numbering").and_then(|v| v.as_str()) == Some("pdf")
                || doc_info.get("pages").is_some()
                || has_pdf_url;
            let has_page_locator = locator.get("page").is_some() || locator.get("pages").is_some();

            let mut extracted_own = false;
            let result: Result<(), String> = (|| {
                let reader = match reader_state {
                    DocReader::Pdf(r) => r,
                    DocReader::ResolutionError(e) => {
                        if e.starts_with("ResolutionError:") {
                            return Err(e.clone());
                        }
                        return Err(format!("ResolutionError: {}", e));
                    }
                    DocReader::Unpinned => {
                        if is_pdf_doc || has_page_locator {
                            return Err("LimitExceeded: document has no sha256 pin".to_string());
                        }
                        item.status = "skipped".to_string();
                        return Ok(());
                    }
                    DocReader::NonPdf { lines } => {
                        if is_pdf_doc || has_page_locator {
                            return Err("LimitExceeded: document is not a PDF".to_string());
                        }
                        if let Some(doc_lines) = lines {
                            if is_own_support {
                                own_lines.extend(doc_lines.iter().cloned());
                                extracted_own = true;
                            }
                        }
                        item.status = "skipped".to_string();
                        return Ok(());
                    }
                };
                
                let page_numbering = doc_info.get("page_numbering").and_then(|v| v.as_str());
                if page_numbering != Some("pdf") {
                    return Err("LimitExceeded: page_numbering is not pdf".to_string());
                }
                
                let bounds = if let Some(pages) = locator.get("pages").and_then(|v| v.as_array()) {
                    vec![pages.get(0).unwrap_or(&Value::Null).clone(), pages.get(1).unwrap_or(&Value::Null).clone()]
                } else {
                    let page = locator.get("page").unwrap_or(&Value::Null).clone();
                    vec![page.clone(), page]
                };

                let mut normalized = Vec::new();
                for b in &bounds {
                    let s = match b.as_str() {
                        Some(s) if s.is_ascii() && s.chars().all(|c| c.is_ascii_digit()) => s,
                        _ => return Err("LimitExceeded: locator needs numeric PDF page(s)".to_string()),
                    };
                    let stripped = s.trim_start_matches('0');
                    let norm = if stripped.is_empty() { "0" } else { stripped };
                    if norm.len() > 10 || (norm.len() == 10 && norm > "2147483647") {
                        return Err("ResolutionError: PDF page exceeds extractor integer range".to_string());
                    }
                    normalized.push(norm.to_string());
                }

                let first: usize = normalized[0].parse().unwrap();
                let last: usize = normalized[1].parse().unwrap();
                let count = doc_info.get("pages").and_then(|v| v.as_u64()).map(|n| n as usize);

                if first < 1 || last < first || count.map_or(false, |c| last > c) {
                    return Err("ResolutionError: PDF page range outside declared pages".to_string());
                }

                let mut lines = Vec::new();
                for page in first..=last {
                    let page_lines = reader.page(page).map_err(|e| if e.starts_with("ResolutionError:") { e } else { format!("ResolutionError: {}", e) })?;
                    for (n, line) in page_lines.iter().enumerate() {
                        item.source.push((page, n + 1, line.clone()));
                    }
                    lines.extend(page_lines);
                }

                if !lines.iter().any(|l| !l.trim().is_empty()) {
                    return Err("LimitExceeded: cited PDF pages have no extractable text".to_string());
                }

                let text = lines.join("\n");
                for kind in ["section", "table", "figure"] {
                    if let Some(locator_kind) = locator.get(kind).and_then(|v| v.as_str()) {
                        let pattern = locator_pattern(kind, locator_kind);
                        if pattern.is_match(&text) {
                            continue;
                        }
                        
                        let mut nearby = Vec::new();
                        for &page in &[first.saturating_sub(1), last + 1] {
                            if page < 1 || count.map_or(false, |c| page > c) {
                                continue;
                            }
                            if let Ok(page_lines) = reader.page(page) {
                                let page_text = page_lines.join("\n");
                                if pattern.is_match(&page_text) {
                                    nearby.push(page.to_string());
                                }
                            }
                        }
                        
                        let suffix = if !nearby.is_empty() {
                            format!("; found on adjacent PDF page(s): {}", nearby.join(", "))
                        } else {
                            "".to_string()
                        };
                        
                        let mut warn_where = where_at.clone();
                        warn_where.push(kind.to_string());
                        add(warn_where, format!("{}: {}: {} {:?} absent from cited PDF pages{}", fact_id, name, kind, locator_kind, suffix), "warning");
                    }
                }

                item.status = "resolved".to_string();
                
                if is_own_support {
                    pdf_own_lines.extend(lines.iter().cloned());
                    own_lines.extend(lines);
                    extracted_own = true;
                }

                Ok(())
            })();

            if is_own_support && !extracted_own {
                has_unextracted_own_doc = true;
            }

            match result {
                Ok(_) => {}
                Err(e) => {
                    if e.starts_with("LimitExceeded:") {
                        item.status = "skipped".to_string();
                        add(where_at.clone(), format!("{}: {}: PDF evidence skipped: {}", fact_id, name, e.trim_start_matches("LimitExceeded: ").trim()), "warning");
                    } else if e.starts_with("ResolutionError:") {
                        add(where_at.clone(), format!("{}: {}: {}", fact_id, name, e.trim_start_matches("ResolutionError: ").trim()), "error");
                    } else {
                        item.status = "skipped".to_string();
                        add(where_at.clone(), format!("{}: {}: PDF evidence skipped: {}", fact_id, name, e), "warning");
                    }
                }
            }

            items.push(item);
        }
    }
    
    DocCitationsResult {
        items,
        own_lines,
        pdf_own_lines,
        has_unextracted_own_doc,
    }
}

pub fn hex_values(text: &str) -> Vec<String> {
    let mut values = Vec::new();
    let re1 = Regex::new(r"0[xX][0-9a-fA-F_']+").unwrap();
    for cap in re1.captures_iter(text) {
        values.push(cap[0].to_string());
    }
    let re2 = Regex::new(r"\b(?:[0-9][0-9A-Fa-f_]*|[0-9A-F][0-9A-F_]+)[hH]\b").unwrap();
    for cap in re2.captures_iter(text) {
        values.push(cap[0].to_string());
    }
    values
}
