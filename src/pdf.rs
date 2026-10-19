// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Native PDF outline, page-count, and page-label reader built on `lopdf` (`BF-USB-3`).
//!
//! Supports public PDFs encrypted with an empty user password under Standard Security Handler
//! Revisions 2–6 (RC4-40, RC4-128, AES-128, and AES-256 permissions encryption) without external
//! Python or `qpdf` dependencies.

use crate::diagnostic::is_yaml_refused_char;
use lopdf::{Dictionary, Document, Object, ObjectId};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::fmt;
use unicode_normalization::UnicodeNormalization;

/// Maximum number of outline items visited before stopping traversal (guards against malformed or
/// hostile PDFs).
pub const MAX_OUTLINE_ITEMS: usize = 100_000;

/// Maximum outline recursion depth (`<h1>`–`<h6>` equivalent).
pub const DEFAULT_MAX_OUTLINE_DEPTH: usize = 6;

/// Maximum recursion depth when walking `/Names` or `/PageLabels` trees.
const MAX_TREE_DEPTH: usize = 64;

/// Maximum dereference hops when resolving indirect PDF objects.
const MAX_DEREF_HOPS: usize = 32;

/// Errors returned when inspecting a PDF document.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PdfError {
    /// Input does not begin with a `%PDF-` header within the first 1024 bytes.
    NotPdf(String),
    /// PDF is encrypted and requires a non-empty password or uses an unsupported security handler.
    Encrypted(String),
    /// PDF structure is malformed or unreadable.
    InvalidPdf(String),
}

impl fmt::Display for PdfError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NotPdf(msg) | Self::Encrypted(msg) | Self::InvalidPdf(msg) => f.write_str(msg),
        }
    }
}

impl std::error::Error for PdfError {}

/// A hierarchical outline bookmark item extracted from a PDF.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PdfOutlineItem {
    /// Cleaned single-line NFC title of the bookmark (may be empty if the bookmark had no text).
    pub title: String,
    /// 1-based destination page (`1..=pages`), if the bookmark resolves to an internal page.
    pub page: Option<usize>,
    /// Nested child bookmarks.
    pub children: Vec<PdfOutlineItem>,
}

/// A flattened outline entry with 1-based depth level and 1-based destination page.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PdfOutlineEntry {
    /// 1-based outline depth (`1..=max_depth`).
    pub level: usize,
    /// Cleaned single-line NFC title.
    pub title: String,
    /// 1-based destination page (`1..=pages`).
    pub page: usize,
}

/// Extracted metadata, page count, page labels, and outline from a PDF document.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PdfMetadata {
    /// Total number of pages in the PDF (`>= 1`).
    pub pages: usize,
    /// Optional 1-based page number -> formatted label map from `/PageLabels`.
    pub page_labels: BTreeMap<usize, String>,
    /// Hierarchical outline tree.
    pub outline_tree: Vec<PdfOutlineItem>,
    /// Flattened outline entries with resolved 1-based levels and 1-based pages.
    pub outline: Vec<PdfOutlineEntry>,
}

/// Returns `true` if `bytes` contains the `%PDF-` magic header within the first 1024 bytes.
#[must_use]
pub fn is_pdf_bytes(bytes: &[u8]) -> bool {
    let prefix = &bytes[..bytes.len().min(1024)];
    prefix.windows(5).any(|w| w == b"%PDF-")
}

/// Normalizes a raw heading or PDF bookmark title into a single-line NFC string free of
/// control/format characters (`index.py:title`).
#[must_use]
pub fn clean_outline_title(raw: &str) -> String {
    let mut mapped = String::with_capacity(raw.len());
    for ch in raw.chars() {
        if ch.is_whitespace() || is_yaml_refused_char(ch) {
            mapped.push(' ');
        } else {
            mapped.push(ch);
        }
    }
    let collapsed = mapped.split_whitespace().collect::<Vec<_>>().join(" ");
    collapsed.nfc().collect()
}

/// ISO 32000-1 Table D.2 `PDFDocEncoding` mapping for bytes `0x00..=0xFF`.
///
/// Control characters `0x00..=0x17` and `0x7F` map to their Unicode control code points so
/// [`clean_outline_title`] can convert them into spaces (matching `pypdf`'s `PDFDocEncoding`
/// behavior).
const PDF_DOC_ENCODING_TABLE: [char; 256] = [
    '\u{0000}', '\u{0001}', '\u{0002}', '\u{0003}', '\u{0004}', '\u{0005}', '\u{0006}', '\u{0007}',
    '\u{0008}', '\u{0009}', '\u{000A}', '\u{000B}', '\u{000C}', '\u{000D}', '\u{000E}', '\u{000F}',
    '\u{0010}', '\u{0011}', '\u{0012}', '\u{0013}', '\u{0014}', '\u{0015}', '\u{0016}', '\u{0017}',
    '\u{02D8}', '\u{02C7}', '\u{02C6}', '\u{02D9}', '\u{02DD}', '\u{02DB}', '\u{02DA}', '\u{02DC}',
    ' ', '!', '"', '#', '$', '%', '&', '\'', '(', ')', '*', '+', ',', '-', '.', '/', '0', '1', '2',
    '3', '4', '5', '6', '7', '8', '9', ':', ';', '<', '=', '>', '?', '@', 'A', 'B', 'C', 'D', 'E',
    'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X',
    'Y', 'Z', '[', '\\', ']', '^', '_', '`', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k',
    'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', '{', '|', '}', '~',
    '\u{007F}', '\u{2022}', '\u{2020}', '\u{2021}', '\u{2026}', '\u{2014}', '\u{2013}', '\u{0192}',
    '\u{2044}', '\u{2039}', '\u{203A}', '\u{2212}', '\u{2030}', '\u{201E}', '\u{201C}', '\u{201D}',
    '\u{2018}', '\u{2019}', '\u{201A}', '\u{2122}', '\u{FB01}', '\u{FB02}', '\u{0141}', '\u{0152}',
    '\u{0160}', '\u{0178}', '\u{017D}', '\u{0131}', '\u{0142}', '\u{0153}', '\u{0161}', '\u{017E}',
    '\u{009F}', '\u{20AC}', '\u{00A1}', '\u{00A2}', '\u{00A3}', '\u{00A4}', '\u{00A5}', '\u{00A6}',
    '\u{00A7}', '\u{00A8}', '\u{00A9}', '\u{00AA}', '\u{00AB}', '\u{00AC}', '\u{00AD}', '\u{00AE}',
    '\u{00AF}', '\u{00B0}', '\u{00B1}', '\u{00B2}', '\u{00B3}', '\u{00B4}', '\u{00B5}', '\u{00B6}',
    '\u{00B7}', '\u{00B8}', '\u{00B9}', '\u{00BA}', '\u{00BB}', '\u{00BC}', '\u{00BD}', '\u{00BE}',
    '\u{00BF}', '\u{00C0}', '\u{00C1}', '\u{00C2}', '\u{00C3}', '\u{00C4}', '\u{00C5}', '\u{00C6}',
    '\u{00C7}', '\u{00C8}', '\u{00C9}', '\u{00CA}', '\u{00CB}', '\u{00CC}', '\u{00CD}', '\u{00CE}',
    '\u{00CF}', '\u{00D0}', '\u{00D1}', '\u{00D2}', '\u{00D3}', '\u{00D4}', '\u{00D5}', '\u{00D6}',
    '\u{00D7}', '\u{00D8}', '\u{00D9}', '\u{00DA}', '\u{00DB}', '\u{00DC}', '\u{00DD}', '\u{00DE}',
    '\u{00DF}', '\u{00E0}', '\u{00E1}', '\u{00E2}', '\u{00E3}', '\u{00E4}', '\u{00E5}', '\u{00E6}',
    '\u{00E7}', '\u{00E8}', '\u{00E9}', '\u{00EA}', '\u{00EB}', '\u{00EC}', '\u{00ED}', '\u{00EE}',
    '\u{00EF}', '\u{00F0}', '\u{00F1}', '\u{00F2}', '\u{00F3}', '\u{00F4}', '\u{00F5}', '\u{00F6}',
    '\u{00F7}', '\u{00F8}', '\u{00F9}', '\u{00FA}', '\u{00FB}', '\u{00FC}', '\u{00FD}', '\u{00FE}',
    '\u{00FF}',
];

/// Decodes a PDF text string (`UTF-16BE`, `UTF-16LE`, `UTF-8`, or `PDFDocEncoding`) into a Rust
/// `String`.
#[must_use]
pub fn decode_pdf_string(bytes: &[u8]) -> String {
    if let Some(rest) = bytes.strip_prefix(&[0xFE, 0xFF]) {
        let units: Vec<u16> = rest
            .chunks_exact(2)
            .map(|pair| u16::from_be_bytes([pair[0], pair[1]]))
            .collect();
        return String::from_utf16_lossy(&units);
    }
    if let Some(rest) = bytes.strip_prefix(&[0xFF, 0xFE]) {
        let units: Vec<u16> = rest
            .chunks_exact(2)
            .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
            .collect();
        return String::from_utf16_lossy(&units);
    }
    if let Some(rest) = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF]) {
        return String::from_utf8_lossy(rest).into_owned();
    }
    // PDF 2.0 allows UTF-8 strings without BOM when valid UTF-8. Single high bytes (such as 0xAD
    // soft hyphen in PDFDocEncoding) are not valid UTF-8, so they fall through to PDFDocEncoding.
    if let Ok(utf8) = std::str::from_utf8(bytes) {
        return utf8.to_string();
    }
    bytes
        .iter()
        .map(|&b| PDF_DOC_ENCODING_TABLE[b as usize])
        .collect()
}

/// Normalizes direct `/Encrypt` dictionaries or indirect `/CF` filter entries so `lopdf::Document`
/// decryption succeeds even on non-standard PDF writers.
fn normalize_encryption_dictionaries(doc: &mut Document) {
    // If trailer /Encrypt is a direct dictionary instead of an indirect reference, promote it.
    let direct_encrypt = match doc.trailer.get(b"Encrypt") {
        Ok(Object::Dictionary(d)) => Some(d.clone()),
        _ => None,
    };
    if let Some(enc_dict) = direct_encrypt {
        let id = doc.add_object(Object::Dictionary(enc_dict));
        doc.trailer.set(b"Encrypt", Object::Reference(id));
    }

    // If /Encrypt -> /CF contains indirect references to CryptFilter dictionaries, inline them.
    let Ok(enc_id) = doc.trailer.get(b"Encrypt").and_then(Object::as_reference) else {
        return;
    };
    let cf_resolved: Option<Dictionary> = doc
        .get_dictionary(enc_id)
        .ok()
        .and_then(|enc| match enc.get(b"CF").ok()? {
            Object::Reference(cf_id) => doc.get_dictionary(*cf_id).ok().cloned(),
            Object::Dictionary(cf) => Some(cf.clone()),
            _ => None,
        })
        .map(|mut cf_dict| {
            let keys: Vec<Vec<u8>> = cf_dict.iter().map(|(k, _)| k.clone()).collect();
            for k in keys {
                if let Ok(Object::Reference(sub_id)) = cf_dict.get(&k) {
                    if let Ok(sub_dict) = doc.get_dictionary(*sub_id).cloned() {
                        cf_dict.set(k, Object::Dictionary(sub_dict));
                    }
                }
            }
            cf_dict
        });

    if let Some(cf_dict) = cf_resolved {
        if let Ok(enc_mut) = doc.get_dictionary_mut(enc_id) {
            enc_mut.set(b"CF", Object::Dictionary(cf_dict));
        }
    }
}

/// Loads a PDF document from `bytes` and decrypts it with an empty user password if encrypted
/// (`BF-USB-3`).
pub fn load_pdf_document(bytes: &[u8]) -> Result<Document, PdfError> {
    if !is_pdf_bytes(bytes) {
        return Err(PdfError::NotPdf(
            "input does not start with a %PDF- header".to_string(),
        ));
    }
    let mut doc = Document::load_mem(bytes)
        .map_err(|e| PdfError::InvalidPdf(format!("cannot read PDF: {e}")))?;

    if doc.trailer.get(b"Encrypt").is_ok() {
        normalize_encryption_dictionaries(&mut doc);
        if doc.is_encrypted() {
            if let Err(err) = doc.decrypt("") {
                return Err(PdfError::Encrypted(format!(
                    "PDF is encrypted and could not be decrypted with an empty user password: {err}"
                )));
            }
        }
    }

    Ok(doc)
}

/// Loads and extracts page count, page labels, and outline bookmarks from `bytes`.
pub fn read_pdf_metadata(bytes: &[u8], max_depth: usize) -> Result<PdfMetadata, PdfError> {
    let doc = load_pdf_document(bytes)?;
    let pages_map = doc.get_pages();
    let pages = pages_map.len();
    if pages == 0 {
        return Err(PdfError::InvalidPdf("PDF has 0 pages".to_string()));
    }
    let page_labels = extract_page_labels(&doc, pages);
    let (outline_tree, outline) = extract_outline_from_doc(&doc, &pages_map, max_depth);
    Ok(PdfMetadata {
        pages,
        page_labels,
        outline_tree,
        outline,
    })
}

/// Dereferences an [`Object`] through up to [`MAX_DEREF_HOPS`] indirect references.
fn deref_object<'a>(doc: &'a Document, mut obj: &'a Object) -> Option<(&'a Object, Option<ObjectId>)> {
    let mut last_id = None;
    for _ in 0..MAX_DEREF_HOPS {
        match obj {
            Object::Reference(id) => {
                last_id = Some(*id);
                obj = doc.objects.get(id)?;
            }
            other => return Some((other, last_id)),
        }
    }
    None
}

/// Dereferences an [`Object`] expecting a [`Dictionary`].
fn deref_dict<'a>(doc: &'a Document, obj: &'a Object) -> Option<(&'a Dictionary, Option<ObjectId>)> {
    let (resolved, id) = deref_object(doc, obj)?;
    match resolved {
        Object::Dictionary(d) => Some((d, id)),
        _ => None,
    }
}

/// Formats an integer `n >= 1` as a Roman numeral.
fn format_roman(mut n: usize, uppercase: bool) -> String {
    const TABLE: &[(usize, &str)] = &[
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ];
    let mut out = String::new();
    for &(val, sym) in TABLE {
        while n >= val {
            out.push_str(sym);
            n -= val;
        }
    }
    if uppercase {
        out
    } else {
        out.to_ascii_lowercase()
    }
}

/// Formats an integer `n >= 1` as alphabetic page labels (`A..Z, AA..ZZ`).
fn format_alpha(n: usize, uppercase: bool) -> String {
    if n == 0 {
        return String::new();
    }
    let idx = (n - 1) % 26;
    let repeat = ((n - 1) / 26) + 1;
    let base = if uppercase { b'A' } else { b'a' };
    let ch = char::from(base + idx as u8);
    std::iter::repeat(ch).take(repeat).collect()
}

fn collect_number_tree_entries<'a>(
    doc: &'a Document,
    node: &'a Dictionary,
    depth: usize,
    seen: &mut HashSet<ObjectId>,
    out: &mut BTreeMap<i64, &'a Dictionary>,
) {
    if depth > MAX_TREE_DEPTH {
        return;
    }
    if let Ok(nums_obj) = node.get(b"Nums") {
        if let Some((Object::Array(arr), _)) = deref_object(doc, nums_obj) {
            for pair in arr.chunks_exact(2) {
                let idx = match deref_object(doc, &pair[0]) {
                    Some((Object::Integer(i), _)) => *i,
                    _ => continue,
                };
                if let Some((dict, _)) = deref_dict(doc, &pair[1]) {
                    out.insert(idx, dict);
                }
            }
        }
    }
    if let Ok(kids_obj) = node.get(b"Kids") {
        if let Some((Object::Array(kids), _)) = deref_object(doc, kids_obj) {
            for kid in kids {
                if let Some((kid_dict, kid_id)) = deref_dict(doc, kid) {
                    if let Some(id) = kid_id {
                        if !seen.insert(id) {
                            continue;
                        }
                    }
                    collect_number_tree_entries(doc, kid_dict, depth + 1, seen, out);
                }
            }
        }
    }
}

/// Extracts 1-based page labels from `/Catalog -> /PageLabels` if present.
#[must_use]
pub fn extract_page_labels(doc: &Document, pages: usize) -> BTreeMap<usize, String> {
    let mut labels = BTreeMap::new();
    let Ok(catalog) = doc.catalog() else {
        return labels;
    };
    let Ok(pl_obj) = catalog.get(b"PageLabels") else {
        return labels;
    };
    let Some((pl_dict, _)) = deref_dict(doc, pl_obj) else {
        return labels;
    };

    let mut ranges = BTreeMap::new();
    let mut seen = HashSet::new();
    collect_number_tree_entries(doc, pl_dict, 0, &mut seen, &mut ranges);
    if ranges.is_empty() {
        return labels;
    }

    for page_idx in 0..pages {
        let idx_i64 = page_idx as i64;
        let Some((&range_start, &label_dict)) = ranges.range(..=idx_i64).next_back() else {
            continue;
        };
        if range_start < 0 {
            continue;
        }
        let prefix = label_dict
            .get(b"P")
            .ok()
            .and_then(|o| deref_object(doc, o))
            .and_then(|(o, _)| match o {
                Object::String(bytes, _) => Some(clean_outline_title(&decode_pdf_string(bytes))),
                _ => None,
            })
            .unwrap_or_default();
        let start_num = label_dict
            .get(b"St")
            .ok()
            .and_then(|o| deref_object(doc, o))
            .and_then(|(o, _)| match o {
                Object::Integer(i) if *i >= 1 => Some(*i as usize),
                _ => None,
            })
            .unwrap_or(1);
        let offset = (idx_i64 - range_start) as usize;
        let num = start_num.saturating_add(offset);
        let style = label_dict
            .get(b"S")
            .ok()
            .and_then(|o| deref_object(doc, o))
            .and_then(|(o, _)| match o {
                Object::Name(name) => Some(name.as_slice()),
                _ => None,
            });
        let num_str = match style {
            Some(b"D") => num.to_string(),
            Some(b"R") => format_roman(num, true),
            Some(b"r") => format_roman(num, false),
            Some(b"A") => format_alpha(num, true),
            Some(b"a") => format_alpha(num, false),
            _ => String::new(),
        };
        let combined = format!("{prefix}{num_str}");
        if !combined.is_empty() {
            labels.insert(page_idx + 1, combined);
        }
    }

    labels
}

/// Resolves a destination array `[page_ref, ...]` or dictionary `<< /D [page_ref, ...] >>` to a
/// 1-based page number (`1..=pages`).
fn resolve_dest_array_or_dict(
    doc: &Document,
    obj: &Object,
    page_id_to_num: &HashMap<ObjectId, usize>,
) -> Option<usize> {
    let (resolved, _) = deref_object(doc, obj)?;
    let arr = match resolved {
        Object::Array(a) => a,
        Object::Dictionary(d) => {
            let d_entry = d.get(b"D").ok()?;
            match deref_object(doc, d_entry)?.0 {
                Object::Array(a) => a,
                _ => return None,
            }
        }
        _ => return None,
    };
    let first = arr.first()?;
    match first {
        Object::Reference(page_id) => page_id_to_num.get(page_id).copied(),
        _ => None,
    }
}

fn collect_name_tree_dests(
    doc: &Document,
    node: &Dictionary,
    page_id_to_num: &HashMap<ObjectId, usize>,
    depth: usize,
    seen: &mut HashSet<ObjectId>,
    out: &mut HashMap<Vec<u8>, usize>,
) {
    if depth > MAX_TREE_DEPTH {
        return;
    }
    if let Ok(names_obj) = node.get(b"Names") {
        if let Some((Object::Array(arr), _)) = deref_object(doc, names_obj) {
            for pair in arr.chunks_exact(2) {
                let key = match deref_object(doc, &pair[0]) {
                    Some((Object::String(bytes, _), _)) => bytes.clone(),
                    Some((Object::Name(bytes), _)) => bytes.clone(),
                    _ => continue,
                };
                if let Some(page) = resolve_dest_array_or_dict(doc, &pair[1], page_id_to_num) {
                    out.insert(key, page);
                }
            }
        }
    }
    if let Ok(kids_obj) = node.get(b"Kids") {
        if let Some((Object::Array(kids), _)) = deref_object(doc, kids_obj) {
            for kid in kids {
                if let Some((kid_dict, kid_id)) = deref_dict(doc, kid) {
                    if let Some(id) = kid_id {
                        if !seen.insert(id) {
                            continue;
                        }
                    }
                    collect_name_tree_dests(doc, kid_dict, page_id_to_num, depth + 1, seen, out);
                }
            }
        }
    }
}

/// Collects all named destinations from `/Catalog -> /Names -> /Dests` and `/Catalog -> /Dests`.
fn collect_named_destinations(
    doc: &Document,
    page_id_to_num: &HashMap<ObjectId, usize>,
) -> HashMap<Vec<u8>, usize> {
    let mut named = HashMap::new();
    let Ok(catalog) = doc.catalog() else {
        return named;
    };

    // PDF 1.1 `/Catalog -> /Dests` dictionary
    if let Ok(dests_obj) = catalog.get(b"Dests") {
        if let Some((dests_dict, _)) = deref_dict(doc, dests_obj) {
            for (k, v) in dests_dict.iter() {
                if let Some(page) = resolve_dest_array_or_dict(doc, v, page_id_to_num) {
                    named.insert(k.clone(), page);
                }
            }
        }
    }

    // PDF 1.2+ `/Catalog -> /Names -> /Dests` name tree
    if let Ok(names_obj) = catalog.get(b"Names") {
        if let Some((names_dict, _)) = deref_dict(doc, names_obj) {
            if let Ok(dests_tree_obj) = names_dict.get(b"Dests") {
                if let Some((dests_tree_dict, _)) = deref_dict(doc, dests_tree_obj) {
                    let mut seen = HashSet::new();
                    collect_name_tree_dests(
                        doc,
                        dests_tree_dict,
                        page_id_to_num,
                        0,
                        &mut seen,
                        &mut named,
                    );
                }
            }
        }
    }

    named
}

/// Resolves an outline item's `/Dest` or `/A` entry to a 1-based page number (`1..=pages`).
fn resolve_outline_item_page(
    doc: &Document,
    item_dict: &Dictionary,
    page_id_to_num: &HashMap<ObjectId, usize>,
    named_dests: &HashMap<Vec<u8>, usize>,
) -> Option<usize> {
    let raw_dest = if let Ok(d) = item_dict.get(b"Dest") {
        Some(d)
    } else if let Ok(a) = item_dict.get(b"A") {
        let (action_dict, _) = deref_dict(doc, a)?;
        let subtype = action_dict
            .get(b"S")
            .ok()
            .and_then(|s| deref_object(doc, s))
            .and_then(|(s, _)| match s {
                Object::Name(n) => Some(n.as_slice()),
                _ => None,
            })?;
        // Only internal `/GoTo` actions point to a page inside this document; external `/URI` or
        // `/GoToR` actions are skipped.
        if subtype != b"GoTo" {
            return None;
        }
        action_dict.get(b"D").ok()
    } else {
        None
    }?;

    let (resolved_dest, _) = deref_object(doc, raw_dest)?;
    match resolved_dest {
        Object::Array(_) | Object::Dictionary(_) => {
            resolve_dest_array_or_dict(doc, resolved_dest, page_id_to_num)
        }
        Object::String(name_bytes, _) | Object::Name(name_bytes) => {
            named_dests.get(name_bytes).copied()
        }
        _ => None,
    }
}

#[allow(clippy::too_many_arguments)]
fn walk_outline_chain(
    doc: &Document,
    first_obj: &Object,
    level: usize,
    max_depth: usize,
    pages: usize,
    page_id_to_num: &HashMap<ObjectId, usize>,
    named_dests: &HashMap<Vec<u8>, usize>,
    seen: &mut HashSet<ObjectId>,
    flat_out: &mut Vec<PdfOutlineEntry>,
) -> Vec<PdfOutlineItem> {
    let mut tree_items = Vec::new();
    let mut cur_obj = Some(first_obj);

    while let Some(obj) = cur_obj {
        if seen.len() >= MAX_OUTLINE_ITEMS {
            break;
        }
        let Some((item_dict, obj_id)) = deref_dict(doc, obj) else {
            break;
        };
        if let Some(id) = obj_id {
            if !seen.insert(id) {
                break;
            }
        }

        let title = item_dict
            .get(b"Title")
            .ok()
            .and_then(|t| deref_object(doc, t))
            .and_then(|(t, _)| match t {
                Object::String(bytes, _) => Some(clean_outline_title(&decode_pdf_string(bytes))),
                _ => None,
            })
            .unwrap_or_default();

        let page = resolve_outline_item_page(doc, item_dict, page_id_to_num, named_dests)
            .filter(|&p| (1..=pages).contains(&p));

        let mut next_level = level;
        if !title.is_empty() && page.is_some() && level <= max_depth {
            flat_out.push(PdfOutlineEntry {
                level,
                title: title.clone(),
                page: page.expect("checked Some above"),
            });
            next_level = level + 1;
        }

        let children = if level <= max_depth {
            if let Ok(child_first) = item_dict.get(b"First") {
                walk_outline_chain(
                    doc,
                    child_first,
                    next_level,
                    max_depth,
                    pages,
                    page_id_to_num,
                    named_dests,
                    seen,
                    flat_out,
                )
            } else {
                Vec::new()
            }
        } else {
            Vec::new()
        };

        tree_items.push(PdfOutlineItem {
            title,
            page,
            children,
        });

        cur_obj = item_dict.get(b"Next").ok();
    }

    tree_items
}

/// Extracts the outline tree and flattened outline entries from a loaded [`Document`].
#[must_use]
pub fn extract_outline_from_doc(
    doc: &Document,
    pages_map: &BTreeMap<u32, ObjectId>,
    max_depth: usize,
) -> (Vec<PdfOutlineItem>, Vec<PdfOutlineEntry>) {
    let pages = pages_map.len();
    if pages == 0 {
        return (Vec::new(), Vec::new());
    }
    let page_id_to_num: HashMap<ObjectId, usize> = pages_map
        .iter()
        .map(|(&page_no, &obj_id)| (obj_id, page_no as usize))
        .collect();

    let Ok(catalog) = doc.catalog() else {
        return (Vec::new(), Vec::new());
    };
    let Ok(outlines_obj) = catalog.get(b"Outlines") else {
        return (Vec::new(), Vec::new());
    };
    let Some((outlines_dict, _)) = deref_dict(doc, outlines_obj) else {
        return (Vec::new(), Vec::new());
    };
    let Ok(first_obj) = outlines_dict.get(b"First") else {
        return (Vec::new(), Vec::new());
    };

    let named_dests = collect_named_destinations(doc, &page_id_to_num);
    let mut seen = HashSet::new();
    let mut flat_out = Vec::new();
    let tree = walk_outline_chain(
        doc,
        first_obj,
        1,
        max_depth,
        pages,
        &page_id_to_num,
        &named_dests,
        &mut seen,
        &mut flat_out,
    );
    (tree, flat_out)
}
