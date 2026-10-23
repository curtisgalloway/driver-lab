// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Integration and unit tests for `src/pdf.rs` and `src/index.rs` (`RT-5`).
//!
//! Covers all cases ported from `skills/spec-format/tests/test_index.py` plus positive and
//! negative tests for `BF-USB-3`, `BF-USB-4`, `BF-IMX-8`, `BF-IMX-9`, `BF-IMX-10`, `BF-ARM-20`,
//! and `BF-GW-22`.

use hwspecs::diagnostic::{ExitCode, Level};
use hwspecs::index::{
    build, check_root_indexes, compute_index_links, dump, extract_section_number, from_html,
    from_markdown, from_pdf, links_for_root_dir, normalize_cited_section, run_index_command,
    scan_root_documents, section, title, validate_index_loaded, DocumentIndex,
    FactDocumentCitation, IndexSection,
};
use hwspecs::pdf::{
    decode_pdf_string, extract_page_labels, is_pdf_bytes, load_pdf_document, read_pdf_metadata,
    PdfError, DEFAULT_MAX_OUTLINE_DEPTH,
};
use hwspecs::sandbox::ScratchResolver;
use hwspecs::yaml_strict;
use lopdf::encryption::crypt_filters::{
    Aes128CryptFilter, Aes256CryptFilter, CryptFilter, Rc4CryptFilter,
};
use lopdf::{
    dictionary, Dictionary, Document, EncryptionState, EncryptionVersion, Object, ObjectId,
    Permissions, Stream, StringFormat,
};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::os::unix::fs::symlink;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tempfile::TempDir;

/// Nested outline specification for synthetic test PDFs: `(title, 0-based page, children)`.
#[derive(Debug, Clone)]
struct OutlineSpec {
    title: String,
    page_idx: Option<usize>,
    children: Vec<OutlineSpec>,
}

impl OutlineSpec {
    fn node(title: &str, page_idx: usize, children: Vec<OutlineSpec>) -> Self {
        Self {
            title: title.to_string(),
            page_idx: Some(page_idx),
            children,
        }
    }

    fn leaf(title: &str, page_idx: usize) -> Self {
        Self::node(title, page_idx, Vec::new())
    }

    fn without_page(title: &str, children: Vec<OutlineSpec>) -> Self {
        Self {
            title: title.to_string(),
            page_idx: None,
            children,
        }
    }
}

fn default_outline() -> Vec<OutlineSpec> {
    vec![
        OutlineSpec::leaf("1 Overview", 0),
        OutlineSpec::node(
            "6 UART",
            89,
            vec![
                OutlineSpec::leaf("6.1 Registers", 91),
                OutlineSpec::leaf("6.2 FIFO", 95),
            ],
        ),
        OutlineSpec::leaf("Appendix A Errata", 110),
    ]
}

/// Encodes a title string as either `PDFDocEncoding` (when all characters fit in Latin-1 /
/// `PDFDocEncoding`, matching `pypdf`'s behavior on e.g. `"soft\u{00ad}hyphen"`) or `UTF-16BE`
/// with `FE FF` BOM.
fn encode_pdf_title_bytes(s: &str) -> Vec<u8> {
    if s.chars()
        .all(|c| (c as u32) <= 0xFF && (c as u32) >= 0x20 || c == '\n' || c == '\t')
    {
        s.chars().map(|c| c as u8).collect()
    } else {
        let mut out = vec![0xFE, 0xFF];
        for unit in s.encode_utf16() {
            out.extend_from_slice(&unit.to_be_bytes());
        }
        out
    }
}

fn add_outline_siblings(
    doc: &mut Document,
    parent_id: ObjectId,
    items: &[OutlineSpec],
    page_ids: &[ObjectId],
) -> Option<(ObjectId, ObjectId)> {
    if items.is_empty() {
        return None;
    }
    let item_ids: Vec<ObjectId> = items.iter().map(|_| doc.new_object_id()).collect();

    for (i, spec) in items.iter().enumerate() {
        let my_id = item_ids[i];
        let child_bounds = add_outline_siblings(doc, my_id, &spec.children, page_ids);

        let mut dict = Dictionary::new();
        dict.set(
            "Title",
            Object::String(encode_pdf_title_bytes(&spec.title), StringFormat::Literal),
        );
        dict.set("Parent", Object::Reference(parent_id));
        if i > 0 {
            dict.set("Prev", Object::Reference(item_ids[i - 1]));
        }
        if i + 1 < item_ids.len() {
            dict.set("Next", Object::Reference(item_ids[i + 1]));
        }
        if let Some((first_child, last_child)) = child_bounds {
            dict.set("First", Object::Reference(first_child));
            dict.set("Last", Object::Reference(last_child));
            dict.set("Count", Object::Integer(spec.children.len() as i64));
        }
        if let Some(p_idx) = spec.page_idx {
            if let Some(&page_obj_id) = page_ids.get(p_idx) {
                dict.set(
                    "Dest",
                    Object::Array(vec![
                        Object::Reference(page_obj_id),
                        Object::Name(b"Fit".to_vec()),
                    ]),
                );
            }
        }
        doc.objects.insert(my_id, Object::Dictionary(dict));
    }

    Some((*item_ids.first().unwrap(), *item_ids.last().unwrap()))
}

/// Builds a synthetic PDF document with `pages` blank pages and `outline` bookmarks.
fn build_pdf_doc(pages: usize, outline: &[OutlineSpec]) -> (Document, Vec<ObjectId>) {
    let mut doc = Document::with_version("1.7");
    let pages_id = doc.new_object_id();
    let mut page_ids = Vec::with_capacity(pages);

    for _ in 0..pages {
        let page_id = doc.add_object(dictionary! {
            "Type" => "Page",
            "Parent" => pages_id,
            "MediaBox" => vec![0.into(), 0.into(), 200.into(), 200.into()],
        });
        page_ids.push(page_id);
    }

    let kids: Vec<Object> = page_ids.iter().map(|&id| Object::Reference(id)).collect();
    doc.objects.insert(
        pages_id,
        Object::Dictionary(dictionary! {
            "Type" => "Pages",
            "Kids" => kids,
            "Count" => pages as i64,
        }),
    );

    let mut catalog = dictionary! {
        "Type" => "Catalog",
        "Pages" => pages_id,
    };

    if !outline.is_empty() {
        let outlines_id = doc.new_object_id();
        if let Some((first_id, last_id)) =
            add_outline_siblings(&mut doc, outlines_id, outline, &page_ids)
        {
            doc.objects.insert(
                outlines_id,
                Object::Dictionary(dictionary! {
                    "Type" => "Outlines",
                    "First" => first_id,
                    "Last" => last_id,
                    "Count" => outline.len() as i64,
                }),
            );
            catalog.set("Outlines", Object::Reference(outlines_id));
        }
    }

    let catalog_id = doc.add_object(Object::Dictionary(catalog));
    doc.trailer.set("Root", Object::Reference(catalog_id));
    // Set a deterministic 16-byte file ID pair in trailer (required by PDF standard encryption).
    let file_id = b"0123456789abcdef".to_vec();
    doc.trailer.set(
        "ID",
        Object::Array(vec![
            Object::string_literal(file_id.clone()),
            Object::string_literal(file_id),
        ]),
    );
    (doc, page_ids)
}

fn save_pdf_bytes(mut doc: Document) -> Vec<u8> {
    let mut buf = Vec::new();
    doc.save_to(&mut buf).expect("save PDF to memory");
    buf
}

fn make_pdf(pages: usize, outline: &[OutlineSpec]) -> Vec<u8> {
    let (doc, _) = build_pdf_doc(pages, outline);
    save_pdf_bytes(doc)
}

/// Test fixture helper copying `skills/spec-format/tests/fixtures/check/good_root` into a temp
/// directory.
struct TestFixture {
    _tmp: TempDir,
    root: PathBuf,
    docs: PathBuf,
    scratch: ScratchResolver,
}

const TRM_SNIPPET: &str = "{name: widget-trm, class: databook, title: Widget SoC TRM, url: \"https://example.invalid/widget-trm.pdf\", pages: 120}";

impl TestFixture {
    fn new() -> Self {
        let tmp = TempDir::new().expect("create tempdir");
        let root = tmp.path().join("good_root");
        let docs = tmp.path().join("docs");
        let scratch_dir = tmp.path().join("scratch");
        fs::create_dir_all(&docs).unwrap();
        fs::create_dir_all(&scratch_dir).unwrap();

        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let good_src = manifest_dir.join("skills/spec-format/tests/fixtures/check/good_root");
        copy_dir_recursive(&good_src, &root);

        Self {
            _tmp: tmp,
            root,
            docs,
            scratch: ScratchResolver::new(Some(scratch_dir)),
        }
    }

    fn install(&self, data: &[u8], name: &str, pages: Option<usize>, numbering: &str) {
        fs::write(self.docs.join(name), data).unwrap();
        let soc_path = self.root.join("widgetsoc.spec.yaml");
        let text = fs::read_to_string(&soc_path).unwrap();
        let digest = hex::encode(Sha256::digest(data));
        let extra = match pages {
            Some(p) => format!(", pages: {p}, page_numbering: {numbering}, sha256: {digest}"),
            None => format!(", sha256: {digest}"),
        };
        let replacement = TRM_SNIPPET.replace(", pages: 120}", &format!("{extra}}}"));
        assert!(
            text.contains(TRM_SNIPPET),
            "expected TRM_SNIPPET in widgetsoc.spec.yaml"
        );
        fs::write(&soc_path, text.replace(TRM_SNIPPET, &replacement)).unwrap();
    }

    fn run_index(&self, name: &str) -> hwspecs::index::IndexCommandOutcome {
        run_index_command(name, &self.root, &self.docs, &self.scratch)
    }

    fn check_indexes(&self) -> Vec<hwspecs::diagnostic::Finding> {
        let (root_label, _, docs) = scan_root_documents(&self.root).expect("scan root");
        let (_, findings) = check_root_indexes(&self.root, &root_label, &docs);
        findings
    }
}

fn copy_dir_recursive(src: &Path, dst: &Path) {
    fs::create_dir_all(dst).unwrap();
    for entry in fs::read_dir(src).unwrap() {
        let entry = entry.unwrap();
        let path = entry.path();
        let target = dst.join(entry.file_name());
        if path.is_dir() {
            copy_dir_recursive(&path, &target);
        } else {
            fs::copy(&path, &target).unwrap();
        }
    }
}

// ===============================================================================================
// 1. Ported tests from `skills/spec-format/tests/test_index.py`
// ===============================================================================================

#[test]
fn test_pdf_outline_becomes_sections() {
    let fx = TestFixture::new();
    fx.install(
        &make_pdf(120, &default_outline()),
        "widget-trm",
        Some(120),
        "pdf",
    );
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::Pass, "{res:?}");
    let out_path = res.path.as_ref().unwrap();
    let loaded = yaml_strict::load_file(out_path);
    assert!(loaded.errors.is_empty(), "{:?}", loaded.errors);
    assert!(validate_index_loaded(out_path, &loaded).is_empty());

    let idx = DocumentIndex::from_value(loaded.data.as_ref().unwrap()).unwrap();
    assert_eq!(idx.source, "pdf");
    assert_eq!(idx.pages, Some(120));
    assert_eq!(
        idx.sections,
        vec![
            IndexSection {
                number: Some("1".to_string()),
                title: "1 Overview".to_string(),
                level: 1,
                pages: Some([1, 90]),
                lines: None,
            },
            IndexSection {
                number: Some("6".to_string()),
                title: "6 UART".to_string(),
                level: 1,
                pages: Some([90, 111]),
                lines: None,
            },
            IndexSection {
                number: Some("6.1".to_string()),
                title: "6.1 Registers".to_string(),
                level: 2,
                pages: Some([92, 96]),
                lines: None,
            },
            IndexSection {
                number: Some("6.2".to_string()),
                title: "6.2 FIFO".to_string(),
                level: 2,
                pages: Some([96, 111]),
                lines: None,
            },
            IndexSection {
                number: Some("A".to_string()),
                title: "Appendix A Errata".to_string(),
                level: 1,
                pages: Some([111, 120]),
                lines: None,
            },
        ]
    );
}

#[test]
fn test_out_of_order_outline_keeps_parents_around_children() {
    let fx = TestFixture::new();
    let outline = vec![
        OutlineSpec::leaf("1 Intro", 0),
        OutlineSpec::node(
            "2 Body",
            9,
            vec![
                OutlineSpec::leaf("2.1 Late", 49),
                OutlineSpec::leaf("2.2 Early", 19),
            ],
        ),
        OutlineSpec::leaf("3 End", 29),
    ];
    fx.install(&make_pdf(120, &outline), "widget-trm", Some(120), "pdf");
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::Pass);
    let loaded = yaml_strict::load_file(res.path.as_ref().unwrap());
    let idx = DocumentIndex::from_value(loaded.data.as_ref().unwrap()).unwrap();
    let got: BTreeMap<String, [usize; 2]> = idx
        .sections
        .into_iter()
        .map(|s| (s.title, s.pages.unwrap()))
        .collect();
    assert_eq!(got["2.1 Late"], [50, 120]);
    assert_eq!(got["2.2 Early"], [20, 30]);
    assert_eq!(got["2 Body"], [10, 120]);
    for (name, [first, last]) in &got {
        assert!(first <= last, "{name}: {first} > {last}");
    }
}

#[test]
fn test_hostile_titles_load_again() {
    let fx = TestFixture::new();
    let long_x = "x".repeat(2000);
    let raw_titles = [
        "soft\u{00ad}hyphen",
        "zero\u{200b}width",
        "\u{feff}bom",
        "bidi \u{202e}evil",
        "private \u{e000}use",
        "nonchar \u{fffe}",
        "decomposed e\u{0301}",
        "- dash",
        "# hash",
        "{brace}",
        "key: value",
        "'quote\"",
        "tab\there",
        "line\nbreak",
        "yes",
        "1",
        long_x.as_str(),
    ];
    let outline: Vec<OutlineSpec> = raw_titles
        .iter()
        .enumerate()
        .map(|(i, t)| OutlineSpec::leaf(t, i))
        .collect();
    fx.install(&make_pdf(120, &outline), "widget-trm", Some(120), "pdf");
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::Pass, "{res:?}");

    let out_path = res.path.as_ref().unwrap();
    let loaded = yaml_strict::load_file(out_path);
    assert!(loaded.errors.is_empty(), "{:?}", loaded.errors);
    assert!(validate_index_loaded(out_path, &loaded).is_empty());
    assert!(fx.check_indexes().is_empty());

    let idx = DocumentIndex::from_value(loaded.data.as_ref().unwrap()).unwrap();
    let got: Vec<String> = idx.sections.into_iter().map(|s| s.title).collect();
    assert!(got.contains(&"decomposed \u{00e9}".to_string()), "{got:?}");
    assert!(got.contains(&"soft hyphen".to_string()), "{got:?}");
    assert!(got.contains(&"zero width".to_string()), "{got:?}");
    assert!(got.contains(&"bom".to_string()), "{got:?}");
    assert!(got.contains(&"yes".to_string()), "{got:?}");
}

#[test]
fn test_output_is_deterministic_and_carries_the_marker_header() {
    let fx = TestFixture::new();
    fx.install(
        &make_pdf(120, &default_outline()),
        "widget-trm",
        Some(120),
        "pdf",
    );
    let first = fx.run_index("widget-trm");
    let path_a = first.path.unwrap();
    let text_a = fs::read_to_string(&path_a).unwrap();

    let second = fx.run_index("widget-trm");
    let text_b = fs::read_to_string(second.path.unwrap()).unwrap();
    assert_eq!(text_a, text_b);
    assert!(text_a.starts_with(
        "# SPDX-FileCopyrightText: 2026 contributors\n# SPDX-License-Identifier: Apache-2.0\n"
    ));
    assert_eq!(path_a, fx.root.join("index/widget-trm.index.yaml"));
}

#[test]
fn test_markdown_headings_become_line_ranges() {
    let fx = TestFixture::new();
    let text = b"# Guide\n\nintro\n\n## 1 Setup\n\nx\n\n## 2 Use\n\ny\n### 2.1 Detail\nz\n";
    fx.install(text, "widget-trm", None, "pdf");
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::Pass, "{res:?}");
    let loaded = yaml_strict::load_file(res.path.as_ref().unwrap());
    let idx = DocumentIndex::from_value(loaded.data.as_ref().unwrap()).unwrap();
    assert_eq!(idx.source, "markdown");
    assert_eq!(idx.lines, Some(13));
    let spans: Vec<(String, [usize; 2])> = idx
        .sections
        .into_iter()
        .map(|s| (s.title, s.lines.unwrap()))
        .collect();
    assert_eq!(
        spans,
        vec![
            ("Guide".to_string(), [1, 13]),
            ("1 Setup".to_string(), [5, 8]),
            ("2 Use".to_string(), [9, 13]),
            ("2.1 Detail".to_string(), [12, 13]),
        ]
    );
}

#[test]
fn test_index_holds_no_page_text_and_no_dotfiles_in_index_dir() {
    let fx = TestFixture::new();
    let (mut doc, page_ids) = build_pdf_doc(1, &[OutlineSpec::leaf("1 Only", 0)]);
    let stream_id = doc.add_object(Stream::new(
        Dictionary::new(),
        b"BT /F1 12 Tf 20 100 Td (SECRETBODYTEXT) Tj ET".to_vec(),
    ));
    doc.get_dictionary_mut(page_ids[0])
        .unwrap()
        .set("Contents", Object::Reference(stream_id));
    let pdf_bytes = save_pdf_bytes(doc);

    fx.install(&pdf_bytes, "widget-trm", Some(1), "pdf");
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::Pass);
    let out_path = res.path.unwrap();
    let text = fs::read_to_string(&out_path).unwrap();
    assert!(!text.contains("SECRETBODYTEXT"));
    assert_eq!(text.matches('\n').count(), 10, "{text}");

    // ENV-3: verify no dotfile exists inside `<root>/index/`.
    for entry in fs::read_dir(fx.root.join("index")).unwrap() {
        let name = entry.unwrap().file_name().to_string_lossy().into_owned();
        assert!(
            !name.starts_with('.'),
            "unexpected dotfile in index/: {name}"
        );
    }
}

#[test]
fn test_refuses_to_write_through_a_link() {
    let fx = TestFixture::new();
    fx.install(
        &make_pdf(120, &default_outline()),
        "widget-trm",
        Some(120),
        "pdf",
    );
    let outside = fx.docs.join("outside.txt");
    fs::write(&outside, "keep me").unwrap();

    let idx_dir = fx.root.join("index");
    fs::create_dir_all(&idx_dir).unwrap();
    let link_file = idx_dir.join("widget-trm.index.yaml");
    symlink(&outside, &link_file).unwrap();

    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::UsageError);
    assert_eq!(fs::read_to_string(&outside).unwrap(), "keep me");

    fs::remove_file(&link_file).unwrap();
    fs::remove_dir(&idx_dir).unwrap();
    symlink(&fx.docs, &idx_dir).unwrap();

    let res2 = fx.run_index("widget-trm");
    assert_eq!(res2.exit_code, ExitCode::UsageError);
    assert!(!fx.docs.join("widget-trm.index.yaml").exists());
}

#[test]
fn test_refuses_when_index_is_a_file() {
    let fx = TestFixture::new();
    fx.install(
        &make_pdf(120, &default_outline()),
        "widget-trm",
        Some(120),
        "pdf",
    );
    fs::write(fx.root.join("index"), "not a directory").unwrap();
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::UsageError);
}

#[test]
fn test_markdown_titles_are_plain_text() {
    let fx = TestFixture::new();
    let text =
        b"# The **bold** [link](https://example.invalid/x) and `code`\n\nbody\r\nmore\x0cstill\n";
    fx.install(text, "widget-trm", None, "pdf");
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::Pass);
    let loaded = yaml_strict::load_file(res.path.as_ref().unwrap());
    let idx = DocumentIndex::from_value(loaded.data.as_ref().unwrap()).unwrap();
    assert_eq!(idx.sections[0].title, "The bold link and code");
    assert_eq!(idx.lines, Some(4));
}

#[test]
fn test_quantities_are_not_section_numbers() {
    let fx = TestFixture::new();
    let outline = vec![
        OutlineSpec::leaf("12 MHz clock", 0),
        OutlineSpec::leaf("64 bit mode", 1),
        OutlineSpec::leaf("3 Registers", 2),
        OutlineSpec::leaf("4.2 Reset", 3),
    ];
    fx.install(&make_pdf(120, &outline), "widget-trm", Some(120), "pdf");
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::Pass);
    let loaded = yaml_strict::load_file(res.path.as_ref().unwrap());
    let idx = DocumentIndex::from_value(loaded.data.as_ref().unwrap()).unwrap();
    let got: BTreeMap<String, Option<String>> = idx
        .sections
        .into_iter()
        .map(|s| (s.title, s.number))
        .collect();
    assert_eq!(got["12 MHz clock"], None);
    assert_eq!(got["64 bit mode"], None);
    assert_eq!(got["3 Registers"], Some("3".to_string()));
    assert_eq!(got["4.2 Reset"], Some("4.2".to_string()));

    for qty in [
        "12 MHz clock",
        "64 bit mode",
        "8 x USB",
        "5 V supply",
        "100 % duty",
        "3 mA load",
        "2 KiB buffer",
        "9 ns setup",
        "4 Mbps link",
        "7 V.",
    ] {
        assert_eq!(
            section(qty, 1, [1, 2], "lines").number,
            None,
            "quantity should not have a section number: {qty}"
        );
    }

    for sec_title in [
        "1 A Note on Errata",
        "3 A Brief Overview",
        "2 B Channel",
        "4 V Series Boards",
        "2 Pins",
        "2 Pin Description",
        "3 Port Description",
        "4 Channels",
        "2 A/D Converter",
        "5 V-Bus",
        "6 S-Parameters",
        "7 X-Bar",
        "1 Introduction",
    ] {
        let expected = sec_title.split_whitespace().next().unwrap().to_string();
        assert_eq!(
            section(sec_title, 1, [1, 2], "lines").number,
            Some(expected),
            "section should extract leading number: {sec_title}"
        );
    }
}

#[test]
fn test_markdown_line_count_ignores_a_trailing_break() {
    for (text, expected_lines) in [("# A\r\nb\r\n", 2), ("# A\nb", 2), ("# A\rb\r", 2)] {
        let (lines, _) = from_markdown(text.as_bytes()).unwrap();
        assert_eq!(lines, expected_lines, "text: {text:?}");
    }
}

#[test]
fn test_children_of_an_item_without_a_place_keep_its_level() {
    let outline = vec![
        OutlineSpec::leaf("1 Intro", 0),
        OutlineSpec::without_page(
            "Web resources",
            vec![
                OutlineSpec::leaf("Datasheet portal", 4),
                OutlineSpec::leaf("Errata", 6),
            ],
        ),
        OutlineSpec::leaf("2 Body", 9),
    ];
    let pdf_bytes = make_pdf(20, &outline);
    let (_, sections) = from_pdf(&pdf_bytes).unwrap();
    let got: Vec<(String, usize)> = sections.into_iter().map(|s| (s.title, s.level)).collect();
    assert_eq!(
        got,
        vec![
            ("1 Intro".to_string(), 1),
            ("Datasheet portal".to_string(), 1),
            ("Errata".to_string(), 1),
            ("2 Body".to_string(), 1),
        ]
    );
}

#[test]
fn test_outline_from_dests_name_tree_and_catalog_dests_and_goto_actions() {
    let (mut doc, page_ids) = build_pdf_doc(20, &[]);
    let outlines_id = doc.new_object_id();
    let item1_id = doc.new_object_id();
    let item2_id = doc.new_object_id();
    let item3_id = doc.new_object_id();

    // Item 1: uses PDF 1.1 `/Catalog -> /Dests` with an `Object::Name` destination `/ch1`.
    doc.objects.insert(
        item1_id,
        Object::Dictionary(dictionary! {
            "Title" => Object::string_literal("1 Named Dict Dest"),
            "Parent" => outlines_id,
            "Next" => item2_id,
            "Dest" => Object::Name(b"ch1".to_vec()),
        }),
    );

    // Item 2: uses `/A << /S /GoTo /D (ch2_str) >>` pointing into `/Catalog -> /Names -> /Dests`.
    doc.objects.insert(
        item2_id,
        Object::Dictionary(dictionary! {
            "Title" => Object::string_literal("2 GoTo Action NameTree Dest"),
            "Parent" => outlines_id,
            "Prev" => item1_id,
            "Next" => item3_id,
            "A" => dictionary! {
                "S" => Object::Name(b"GoTo".to_vec()),
                "D" => Object::string_literal("ch2_str"),
            },
        }),
    );

    // Item 3: uses `/A << /S /URI /URI (https://example.invalid) >>` (external action -> skipped).
    doc.objects.insert(
        item3_id,
        Object::Dictionary(dictionary! {
            "Title" => Object::string_literal("External URI Link"),
            "Parent" => outlines_id,
            "Prev" => item2_id,
            "A" => dictionary! {
                "S" => Object::Name(b"URI".to_vec()),
                "URI" => Object::string_literal("https://example.invalid"),
            },
        }),
    );

    doc.objects.insert(
        outlines_id,
        Object::Dictionary(dictionary! {
            "Type" => "Outlines",
            "First" => item1_id,
            "Last" => item3_id,
            "Count" => 3,
        }),
    );

    let dests_dict_id = doc.add_object(dictionary! {
        "ch1" => Object::Array(vec![Object::Reference(page_ids[2]), Object::Name(b"Fit".to_vec())]),
    });

    let name_tree_leaf_id = doc.add_object(dictionary! {
        "Names" => Object::Array(vec![
            Object::string_literal("ch2_str"),
            Object::Dictionary(dictionary! {
                "D" => Object::Array(vec![Object::Reference(page_ids[9]), Object::Name(b"Fit".to_vec())]),
            }),
        ]),
    });
    let names_id = doc.add_object(dictionary! {
        "Dests" => dictionary! {
            "Kids" => Object::Array(vec![Object::Reference(name_tree_leaf_id)]),
        },
    });

    let cat_id = doc.trailer.get(b"Root").unwrap().as_reference().unwrap();
    let cat = doc.get_dictionary_mut(cat_id).unwrap();
    cat.set("Outlines", Object::Reference(outlines_id));
    cat.set("Dests", Object::Reference(dests_dict_id));
    cat.set("Names", Object::Reference(names_id));

    let bytes = save_pdf_bytes(doc);
    let (_, sections) = from_pdf(&bytes).unwrap();
    assert_eq!(
        sections,
        vec![
            IndexSection {
                number: Some("1".to_string()),
                title: "1 Named Dict Dest".to_string(),
                level: 1,
                pages: Some([3, 10]),
                lines: None,
            },
            IndexSection {
                number: Some("2".to_string()),
                title: "2 GoTo Action NameTree Dest".to_string(),
                level: 1,
                pages: Some([10, 20]),
                lines: None,
            },
        ]
    );
}

#[test]
fn test_cyclic_outline_stops() {
    let (mut doc, page_ids) = build_pdf_doc(10, &[]);
    let outlines_id = doc.new_object_id();
    let a_id = doc.new_object_id();
    let b_id = doc.new_object_id();

    doc.objects.insert(
        a_id,
        Object::Dictionary(dictionary! {
            "Title" => Object::string_literal("1 First"),
            "Parent" => outlines_id,
            "Next" => b_id,
            "Dest" => Object::Array(vec![Object::Reference(page_ids[0]), Object::Name(b"Fit".to_vec())]),
        }),
    );
    // `b` points its `/Next` back to `a` (cycle!).
    doc.objects.insert(
        b_id,
        Object::Dictionary(dictionary! {
            "Title" => Object::string_literal("2 Second"),
            "Parent" => outlines_id,
            "Prev" => a_id,
            "Next" => a_id,
            "Dest" => Object::Array(vec![Object::Reference(page_ids[4]), Object::Name(b"Fit".to_vec())]),
        }),
    );
    doc.objects.insert(
        outlines_id,
        Object::Dictionary(dictionary! {
            "Type" => "Outlines",
            "First" => a_id,
            "Last" => b_id,
            "Count" => 2,
        }),
    );
    let cat_id = doc.trailer.get(b"Root").unwrap().as_reference().unwrap();
    doc.get_dictionary_mut(cat_id)
        .unwrap()
        .set("Outlines", Object::Reference(outlines_id));

    let bytes = save_pdf_bytes(doc);
    let (_, sections) = from_pdf(&bytes).unwrap();
    assert_eq!(sections.len(), 2);
    assert_eq!(sections[0].title, "1 First");
    assert_eq!(sections[1].title, "2 Second");
}

#[test]
fn test_refuses_bytes_with_another_hash() {
    let fx = TestFixture::new();
    fx.install(
        &make_pdf(120, &default_outline()),
        "widget-trm",
        Some(120),
        "pdf",
    );
    fs::write(
        fx.docs.join("widget-trm"),
        make_pdf(121, &default_outline()),
    )
    .unwrap();
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::DomainFailure);
    assert!(!fx.root.join("index").exists());
}

#[test]
fn test_refuses_a_document_without_sha256() {
    let fx = TestFixture::new();
    fs::write(
        fx.docs.join("widget-trm"),
        make_pdf(120, &default_outline()),
    )
    .unwrap();
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::UsageError);
    assert!(res.to_json_value().to_string().contains("has no sha256"));
}

#[test]
fn test_refuses_an_unlisted_document() {
    let fx = TestFixture::new();
    let res = fx.run_index("nosuch-doc");
    assert_eq!(res.exit_code, ExitCode::UsageError);
}

#[test]
fn test_refuses_a_pdf_without_outline() {
    let fx = TestFixture::new();
    fx.install(&make_pdf(120, &[]), "widget-trm", Some(120), "pdf");
    let res = fx.run_index("widget-trm");
    assert_eq!(res.exit_code, ExitCode::DomainFailure);
    assert_eq!(res.findings[0].code, "IDX-NOT-INDEXABLE");
    assert!(!fx.root.join("index").exists());
}

#[test]
fn test_index_check_warnings_and_errors() {
    // 1. Clean index checks with 0 findings.
    let fx = TestFixture::new();
    fx.install(
        &make_pdf(120, &default_outline()),
        "widget-trm",
        Some(120),
        "pdf",
    );
    assert_eq!(fx.run_index("widget-trm").exit_code, ExitCode::Pass);
    assert!(fx.check_indexes().is_empty());

    // 2. Hash mismatch warns.
    let idx_path = fx.root.join("index/widget-trm.index.yaml");
    let orig_text = fs::read_to_string(&idx_path).unwrap();
    let old_sha = orig_text
        .lines()
        .find_map(|l| l.strip_prefix("sha256: "))
        .unwrap()
        .to_string();
    let zero_sha = "0".repeat(64);
    fs::write(&idx_path, orig_text.replace(&old_sha, &zero_sha)).unwrap();
    let findings = fx.check_indexes();
    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].level, Level::Warning);
    assert!(findings[0].message.contains("is not the registry's"));
    fs::write(&idx_path, &orig_text).unwrap();

    // 3. Page count mismatch warns.
    fs::write(&idx_path, orig_text.replace("pages: 120\n", "pages: 121\n")).unwrap();
    let findings = fx.check_indexes();
    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].level, Level::Warning);
    assert!(findings[0].message.contains("index counts 121 pages"));
    fs::write(&idx_path, &orig_text).unwrap();

    // 4. Unlisted document warns.
    let unlisted_path = fx.root.join("index/other-doc.index.yaml");
    fs::write(
        &unlisted_path,
        orig_text.replace("document: widget-trm", "document: other-doc"),
    )
    .unwrap();
    let findings = fx.check_indexes();
    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].level, Level::Warning);
    assert!(findings[0].message.contains("lists document 'other-doc'"));
    fs::remove_file(&unlisted_path).unwrap();

    // 5. Second index for the same document warns.
    let copy_path = fx.root.join("index/copy.index.yaml");
    fs::write(&copy_path, &orig_text).unwrap();
    let findings = fx.check_indexes();
    assert!(findings.iter().any(|f| f.level == Level::Warning
        && f.message
            .contains("a second index for document 'widget-trm'")));
    fs::remove_file(&copy_path).unwrap();

    // 6. Near-miss filename `.index.yml` is an error.
    let bad_ext = fx.root.join("index/widget-trm.index.yml");
    fs::rename(&idx_path, &bad_ext).unwrap();
    let findings = fx.check_indexes();
    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].level, Level::Error);
    assert!(findings[0].message.contains("not read as a document index"));
    fs::rename(&bad_ext, &idx_path).unwrap();

    // 7. Misplaced `.index.yaml` at root top-level is an error.
    let misplaced = fx.root.join("widget-trm.index.yaml");
    fs::rename(&idx_path, &misplaced).unwrap();
    let findings = fx.check_indexes();
    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].level, Level::Error);
    assert!(findings[0]
        .message
        .contains("lives in the root's own index/"));
    fs::rename(&misplaced, &idx_path).unwrap();

    // 8. Malformed index (`source: word`) is an error.
    fs::write(&idx_path, orig_text.replace("source: pdf", "source: word")).unwrap();
    let findings = fx.check_indexes();
    assert!(!findings.is_empty());
    assert!(findings.iter().all(|f| f.level == Level::Error));
}

#[test]
fn test_links_by_section_heading_and_pdf_page() {
    let fx = TestFixture::new();
    fx.install(
        &make_pdf(120, &default_outline()),
        "widget-trm",
        Some(120),
        "pdf",
    );
    assert_eq!(fx.run_index("widget-trm").exit_code, ExitCode::Pass);

    let linked = links_for_root_dir(&fx.root);
    assert_eq!(linked.len(), 1);
    let facts: BTreeMap<String, Vec<String>> = linked[0]
        .sections
        .iter()
        .map(|s| (s.title.clone(), s.facts.clone()))
        .collect();
    assert_eq!(facts["1 Overview"], Vec::<String>::new());
    assert_eq!(
        facts["6 UART"],
        vec!["widgetsoc@good#uart-base".to_string()]
    );
    assert_eq!(
        facts["6.1 Registers"],
        vec!["widgetsoc@good#uart-base".to_string()]
    );
    assert_eq!(facts["6.2 FIFO"], Vec::<String>::new());
    assert_eq!(facts["Appendix A Errata"], Vec::<String>::new());
}

#[test]
fn test_printed_page_numbers_link_by_section_only() {
    let fx = TestFixture::new();
    fx.install(
        &make_pdf(120, &default_outline()),
        "widget-trm",
        Some(120),
        "printed",
    );
    let soc_path = fx.root.join("widgetsoc.spec.yaml");
    let text = fs::read_to_string(&soc_path).unwrap();
    fs::write(&soc_path, text.replace("section: \"6.1\", ", "")).unwrap();
    assert_eq!(fx.run_index("widget-trm").exit_code, ExitCode::Pass);

    let linked = links_for_root_dir(&fx.root);
    assert_eq!(linked.len(), 1);
    for sec in &linked[0].sections {
        assert!(sec.facts.is_empty(), "expected no facts on {}", sec.title);
    }
}

#[test]
fn test_section_number_matches_whole_components() {
    let fx = TestFixture::new();
    fx.install(
        &make_pdf(120, &default_outline()),
        "widget-trm",
        Some(120),
        "printed",
    );
    let soc_path = fx.root.join("widgetsoc.spec.yaml");
    let text = fs::read_to_string(&soc_path).unwrap();
    fs::write(
        &soc_path,
        text.replace("section: \"6.1\"", "section: \"6.10\""),
    )
    .unwrap();
    assert_eq!(fx.run_index("widget-trm").exit_code, ExitCode::Pass);

    let linked = links_for_root_dir(&fx.root);
    let facts: BTreeMap<String, Vec<String>> = linked[0]
        .sections
        .iter()
        .map(|s| (s.title.clone(), s.facts.clone()))
        .collect();
    assert_eq!(
        facts["6 UART"],
        vec!["widgetsoc@good#uart-base".to_string()]
    );
    assert_eq!(facts["6.1 Registers"], Vec::<String>::new());
}

// ===============================================================================================
// 2. BF-USB-3: Empty-password encrypted PDFs (RC4-40 R2, RC4-128 R3, AES-128 R4, AES-256 R6)
// ===============================================================================================

#[test]
fn test_bf_usb_3_empty_password_encrypted_pdfs_succeed_and_password_protected_fail() {
    let outline = default_outline();

    // 1. Revision 2 (V1, RC4-40) with empty user password
    {
        let (mut doc, _) = build_pdf_doc(120, &outline);
        let state = EncryptionState::try_from(EncryptionVersion::V1 {
            document: &doc,
            owner_password: "owner-password",
            user_password: "",
            permissions: Permissions::all(),
        })
        .unwrap();
        doc.encrypt(&state).unwrap();
        let bytes = save_pdf_bytes(doc);
        let (pages, sections) =
            from_pdf(&bytes).expect("V1 RC4-40 empty user password should decrypt");
        assert_eq!(pages, 120);
        assert_eq!(sections.len(), 5);
        assert_eq!(sections[1].title, "6 UART");
    }

    // 2. Revision 3 (V2, RC4-128) with empty user password
    {
        let (mut doc, _) = build_pdf_doc(120, &outline);
        let state = EncryptionState::try_from(EncryptionVersion::V2 {
            document: &doc,
            owner_password: "owner-password",
            user_password: "",
            key_length: 128,
            permissions: Permissions::all(),
        })
        .unwrap();
        doc.encrypt(&state).unwrap();
        let bytes = save_pdf_bytes(doc);
        let (pages, sections) =
            from_pdf(&bytes).expect("V2 RC4-128 empty user password should decrypt");
        assert_eq!(pages, 120);
        assert_eq!(sections.len(), 5);
    }

    // 3. Revision 4 (V4, AES-128 / AESV2) with empty user password (like USB-IF specs)
    {
        let (mut doc, _) = build_pdf_doc(120, &outline);
        let cf: Arc<dyn CryptFilter> = Arc::new(Aes128CryptFilter);
        let state = EncryptionState::try_from(EncryptionVersion::V4 {
            document: &doc,
            encrypt_metadata: true,
            crypt_filters: BTreeMap::from([(b"StdCF".to_vec(), cf)]),
            stream_filter: b"StdCF".to_vec(),
            string_filter: b"StdCF".to_vec(),
            owner_password: "usb-if-owner-password",
            user_password: "",
            permissions: Permissions::all(),
        })
        .unwrap();
        doc.encrypt(&state).unwrap();
        let bytes = save_pdf_bytes(doc);
        let (pages, sections) =
            from_pdf(&bytes).expect("V4 AES-128 empty user password should decrypt");
        assert_eq!(pages, 120);
        assert_eq!(sections.len(), 5);
        assert_eq!(sections[2].number.as_deref(), Some("6.1"));
    }

    // 4. Revision 6 (V5, AES-256 / AESV3) with empty user password
    {
        let (mut doc, _) = build_pdf_doc(120, &outline);
        let cf: Arc<dyn CryptFilter> = Arc::new(Aes256CryptFilter);
        let key = [0x42u8; 32];
        let state = EncryptionState::try_from(EncryptionVersion::V5 {
            encrypt_metadata: true,
            crypt_filters: BTreeMap::from([(b"StdCF".to_vec(), cf)]),
            file_encryption_key: &key,
            stream_filter: b"StdCF".to_vec(),
            string_filter: b"StdCF".to_vec(),
            owner_password: "owner-password",
            user_password: "",
            permissions: Permissions::all(),
        })
        .unwrap();
        doc.encrypt(&state).unwrap();
        let bytes = save_pdf_bytes(doc);
        let (pages, sections) =
            from_pdf(&bytes).expect("V5 AES-256 empty user password should decrypt");
        assert_eq!(pages, 120);
        assert_eq!(sections.len(), 5);
        assert_eq!(sections[4].number.as_deref(), Some("A"));
    }

    // 5. Negative: V4 AES-128 and V5 AES-256 with NON-EMPTY user password must fail cleanly.
    {
        let (mut doc, _) = build_pdf_doc(120, &outline);
        let cf: Arc<dyn CryptFilter> = Arc::new(Aes128CryptFilter);
        let state = EncryptionState::try_from(EncryptionVersion::V4 {
            document: &doc,
            encrypt_metadata: true,
            crypt_filters: BTreeMap::from([(b"StdCF".to_vec(), cf)]),
            stream_filter: b"StdCF".to_vec(),
            string_filter: b"StdCF".to_vec(),
            owner_password: "owner-password",
            user_password: "non-empty-user-secret",
            permissions: Permissions::all(),
        })
        .unwrap();
        doc.encrypt(&state).unwrap();
        let bytes = save_pdf_bytes(doc);
        let err = from_pdf(&bytes).expect_err("non-empty user password PDF must fail");
        assert!(
            err.to_string().contains("encrypted") || err.to_string().contains("cannot read"),
            "unexpected error: {err}"
        );
    }

    // 6. Negative: RC4 with non-empty user password must also fail cleanly.
    {
        let (mut doc, _) = build_pdf_doc(20, &outline);
        let cf: Arc<dyn CryptFilter> = Arc::new(Rc4CryptFilter);
        let state = EncryptionState::try_from(EncryptionVersion::V4 {
            document: &doc,
            encrypt_metadata: true,
            crypt_filters: BTreeMap::from([(b"StdCF".to_vec(), cf)]),
            stream_filter: b"StdCF".to_vec(),
            string_filter: b"StdCF".to_vec(),
            owner_password: "owner",
            user_password: "user-secret",
            permissions: Permissions::all(),
        })
        .unwrap();
        doc.encrypt(&state).unwrap();
        let bytes = save_pdf_bytes(doc);
        assert!(matches!(
            load_pdf_document(&bytes),
            Err(PdfError::Encrypted(_) | PdfError::InvalidPdf(_))
        ));
    }
}

// ===============================================================================================
// 3. BF-USB-4, BF-IMX-10, & BF-ARM-20: Section number extraction (Chapter/Appendix/Part/Arm/Letter)
// ===============================================================================================

#[test]
fn test_bf_usb_4_imx_10_arm_20_section_number_extraction_positive_and_negative() {
    // Positive standalone extractions:
    let positive_cases = [
        ("Chapter 1. Introduction", "1"),
        ("Chapter 10 Power Rules", "10"),
        ("Section 4.2 System interrupts", "4.2"),
        ("Appendix A Release Notes", "A"),
        ("Appendix B.1 Tables", "B.1"),
        ("Part 1 Overview", "Part 1"),
        ("Part A Architecture", "Part A"),
        ("A1 Introduction", "A1"),
        ("A1.2 Register summary", "A1.2"),
        ("B2.41 CLUSTERPWRCTLR_EL1", "B2.41"),
        ("C1.2.3 Event counter", "C1.2.3"),
        ("D1 System registers", "D1"),
    ];
    for (heading, expected_num) in positive_cases {
        assert_eq!(
            extract_section_number(heading).as_deref(),
            Some(expected_num),
            "failed on heading: {heading}"
        );
    }

    // Contextual single-letter appendix promotion in PDF outlines:
    // Case A: `A Release Notes` followed by `A.1 Overview`, and `B Debug Accessory Mode` after chapters.
    let outline = vec![
        OutlineSpec::leaf("Part 1 System Overview", 0),
        OutlineSpec::leaf("Chapter 1. Introduction", 2),
        OutlineSpec::node(
            "A1 Memory Map",
            10,
            vec![OutlineSpec::leaf("A1.1 Address Space", 12)],
        ),
        OutlineSpec::node(
            "A Release Notes",
            50,
            vec![OutlineSpec::leaf("A.1 Revision History", 52)],
        ),
        OutlineSpec::leaf("B Debug Accessory Mode", 60),
        OutlineSpec::leaf("C Power Management", 70),
    ];
    let pdf_bytes = make_pdf(80, &outline);
    let (_, sections) = from_pdf(&pdf_bytes).unwrap();
    let nums: BTreeMap<String, Option<String>> =
        sections.into_iter().map(|s| (s.title, s.number)).collect();
    assert_eq!(nums["Part 1 System Overview"].as_deref(), Some("Part 1"));
    assert_eq!(nums["Chapter 1. Introduction"].as_deref(), Some("1"));
    assert_eq!(nums["A1 Memory Map"].as_deref(), Some("A1"));
    assert_eq!(nums["A1.1 Address Space"].as_deref(), Some("A1.1"));
    assert_eq!(nums["A Release Notes"].as_deref(), Some("A"));
    assert_eq!(nums["A.1 Revision History"].as_deref(), Some("A.1"));
    assert_eq!(nums["B Debug Accessory Mode"].as_deref(), Some("B"));
    assert_eq!(nums["C Power Management"].as_deref(), Some("C"));

    // Case B: `usb-type-c` style level-1 `A Liquid Corrosion...` followed by `B Debug Accessory...`
    let outline_ab = vec![
        OutlineSpec::leaf("1 Introduction", 0),
        OutlineSpec::leaf("2 Cables", 10),
        OutlineSpec::leaf("A Liquid Corrosion Mitigation Mode", 30),
        OutlineSpec::leaf("B Debug Accessory Mode", 40),
    ];
    let (_, secs_ab) = from_pdf(&make_pdf(50, &outline_ab)).unwrap();
    assert_eq!(secs_ab[2].number.as_deref(), Some("A"));
    assert_eq!(secs_ab[3].number.as_deref(), Some("B"));

    // Negative: Lone `"A Note on Usage"` or `"I Index"` without dot, child `A.1`, or sibling `B`/`J`
    // must NOT be misclassified as an appendix number.
    let outline_neg = vec![
        OutlineSpec::leaf("1 Introduction", 0),
        OutlineSpec::leaf("A Note on Terminology", 10),
        OutlineSpec::leaf("I Summary and Index", 20),
    ];
    let (_, secs_neg) = from_pdf(&make_pdf(30, &outline_neg)).unwrap();
    assert_eq!(secs_neg[1].number, None);
    assert_eq!(secs_neg[2].number, None);
}

// ===============================================================================================
// 4. BF-IMX-8: HTML heading extraction (`<h1>`..`<h6>`)
// ===============================================================================================

#[test]
fn test_bf_imx_8_html_heading_extraction_positive_and_negative() {
    let html_doc = r##"<!DOCTYPE html>
<html lang="en">
<head>
  <title>Booting AArch64 Linux</title>
  <script>
    // <h1>Not a real heading inside script</h1>
  </script>
</head>
<body>
  <!-- <h1>Commented out heading</h1> -->
  <section id="booting-aarch64-linux">
    <h1>Booting AArch64 Linux<a class="headerlink" href="#booting-aarch64-linux" title="Permalink">¶</a></h1>
    <p>Intro paragraph.</p>
    <section id="setup-ram">
      <h2>1. Setup and initialise RAM<a class="headerlink" href="#setup-ram">¶</a></h2>
      <p>Mandatory requirement.</p>
      <h3>1.1 Alignment and <code>0x80000</code> offset</h3>
      <p>Details here.</p>
    </section>
    <section id="setup-dt">
      <h2>2. Setup the device tree</h2>
      <p>DT requirement.</p>
    </section>
  </section>
</body>
</html>
"##
    .as_bytes();

    let idx = build("linux-arm64-booting", html_doc).expect("HTML doc should index");
    assert_eq!(idx.source, "markdown");
    assert_eq!(idx.lines, Some(26));
    assert_eq!(
        idx.sections,
        vec![
            IndexSection {
                number: None,
                title: "Booting AArch64 Linux".to_string(),
                level: 1,
                pages: None,
                lines: Some([12, 26]),
            },
            IndexSection {
                number: Some("1".to_string()),
                title: "1. Setup and initialise RAM".to_string(),
                level: 2,
                pages: None,
                lines: Some([15, 20]),
            },
            IndexSection {
                number: Some("1.1".to_string()),
                title: "1.1 Alignment and 0x80000 offset".to_string(),
                level: 3,
                pages: None,
                lines: Some([17, 20]),
            },
            IndexSection {
                number: Some("2".to_string()),
                title: "2. Setup the device tree".to_string(),
                level: 2,
                pages: None,
                lines: Some([21, 26]),
            },
        ]
    );

    // Verify dumped YAML passes strict YAML + index schema validation.
    let yaml_text = dump(
        &idx,
        &[
            "# SPDX-FileCopyrightText: 2026 contributors".to_string(),
            "# SPDX-License-Identifier: Apache-2.0".to_string(),
        ],
    );
    // #199: the banner names the current tool.
    assert!(
        yaml_text.contains("# Generated by hwspecs index: headings and locators only."),
        "{yaml_text}"
    );
    assert!(!yaml_text.contains("spec.py"), "{yaml_text}");
    let loaded = yaml_strict::load_text_with_limits(
        &yaml_text,
        Path::new("linux-arm64-booting.index.yaml"),
        yaml_strict::YamlLimits::index(),
    );
    assert!(loaded.errors.is_empty());
    assert!(validate_index_loaded(Path::new("linux-arm64-booting.index.yaml"), &loaded).is_empty());

    // Negative: HTML document without any `<h1>`..`<h6>` elements fails with `NotIndexable`.
    let empty_html = b"<!DOCTYPE html><html><body><p>No headings here</p></body></html>";
    let err = from_html(empty_html).expect_err("HTML without headings must fail");
    assert!(err.to_string().contains("no headings to index"));
}

// ===============================================================================================
// 5. BF-GW-22: Trac/MoinMoin wiki heading fallback
// ===============================================================================================

#[test]
fn test_bf_gw_22_trac_wiki_headings_positive_and_negative() {
    let wiki_doc = br#"= Gateworks Catalina Family Support

{{{
#!html
= Fake heading inside code block =
}}}

[[PageOutline]]
||= Table Header =||= Value =||

== Note
Important note text.

== 1. Overview
Overview text.

=== 1.1. Device Trees === #dt
Device tree details.

= Third Party Linux Distros =
Distro details.
"#;

    let idx = build("gw-wiki-catalina", wiki_doc).expect("Trac wiki should index");
    assert_eq!(idx.source, "markdown");
    assert_eq!(idx.lines, Some(21));
    assert_eq!(
        idx.sections,
        vec![
            IndexSection {
                number: None,
                title: "Gateworks Catalina Family Support".to_string(),
                level: 1,
                pages: None,
                lines: Some([1, 19]),
            },
            IndexSection {
                number: None,
                title: "Note".to_string(),
                level: 2,
                pages: None,
                lines: Some([11, 13]),
            },
            IndexSection {
                number: Some("1".to_string()),
                title: "1. Overview".to_string(),
                level: 2,
                pages: None,
                lines: Some([14, 19]),
            },
            IndexSection {
                number: Some("1.1".to_string()),
                title: "1.1. Device Trees".to_string(),
                level: 3,
                pages: None,
                lines: Some([17, 19]),
            },
            IndexSection {
                number: None,
                title: "Third Party Linux Distros".to_string(),
                level: 1,
                pages: None,
                lines: Some([20, 21]),
            },
        ]
    );

    // Negative: Wiki file with only code-block `= ... =` and table rows `||= ... =||` fails.
    let no_headings_wiki = b"{{{\n= Not a heading =\n}}}\n||= Cell =||\nJust prose.\n";
    let err = from_markdown(no_headings_wiki).expect_err("wiki without real headings must fail");
    assert!(err.to_string().contains("no headings to index"));
}

// ===============================================================================================
// 6. BF-IMX-9: Shared boundary page disambiguation and normalized `section:` matching in `links`
// ===============================================================================================

#[test]
fn test_bf_imx_9_boundary_page_disambiguation_and_normalized_section_links() {
    let idx = DocumentIndex {
        format: 2,
        document: "imx95-rm".to_string(),
        sha256: "a".repeat(64),
        source: "pdf".to_string(),
        pages: Some(200),
        lines: None,
        sections: vec![
            IndexSection {
                number: Some("3".to_string()),
                title: "Chapter 3 Clocks".to_string(),
                level: 1,
                pages: Some([63, 112]),
                lines: None,
            },
            IndexSection {
                number: Some("4".to_string()),
                title: "Chapter 4 Interrupts".to_string(),
                level: 1,
                pages: Some([112, 144]),
                lines: None,
            },
            IndexSection {
                number: Some("4.1".to_string()),
                title: "4.1 Overview".to_string(),
                level: 2,
                pages: Some([112, 115]),
                lines: None,
            },
            IndexSection {
                number: Some("4.2".to_string()),
                title: "4.2 System interrupts".to_string(),
                level: 2,
                pages: Some([115, 144]),
                lines: None,
            },
        ],
    };

    let candidates = vec![("imx95-rm.index.yaml".to_string(), idx)];
    let citations = vec![
        // Citation 1: specifies `section: "Section 4.2 System interrupts"` and boundary page 112.
        // Must link ONLY to 4.2 and its ancestor 4 (never Chapter 3).
        FactDocumentCitation {
            fact_full_id: "imx95@soc#irq-table".to_string(),
            document: "imx95-rm".to_string(),
            pdf_numbered: true,
            section: Some("Section 4.2 System interrupts".to_string()),
            heading: None,
            page: Some("112".to_string()),
            pages: None,
        },
        // Citation 2: page-only citation on shared boundary page 112 (where Ch 3 ends and Ch 4 / 4.1 starts).
        // Must link to deepest section starting on page 112 (4.1) and its ancestor (4), NEVER Chapter 3.
        FactDocumentCitation {
            fact_full_id: "imx95@soc#boundary-page-only".to_string(),
            document: "imx95-rm".to_string(),
            pdf_numbered: true,
            section: None,
            heading: None,
            page: Some("112".to_string()),
            pages: None,
        },
        // Citation 3: interior page 100 inside Chapter 3.
        FactDocumentCitation {
            fact_full_id: "imx95@soc#clk-interior".to_string(),
            document: "imx95-rm".to_string(),
            pdf_numbered: true,
            section: None,
            heading: None,
            page: Some("100".to_string()),
            pages: None,
        },
    ];

    let linked = compute_index_links(&candidates, &citations);
    assert_eq!(linked.len(), 1);
    let facts_by_title: BTreeMap<String, Vec<String>> = linked[0]
        .sections
        .iter()
        .map(|s| (s.title.clone(), s.facts.clone()))
        .collect();

    assert_eq!(
        facts_by_title["Chapter 3 Clocks"],
        vec!["imx95@soc#clk-interior".to_string()]
    );
    assert_eq!(
        facts_by_title["Chapter 4 Interrupts"],
        vec![
            "imx95@soc#boundary-page-only".to_string(),
            "imx95@soc#irq-table".to_string(),
        ]
    );
    assert_eq!(
        facts_by_title["4.1 Overview"],
        vec!["imx95@soc#boundary-page-only".to_string()]
    );
    assert_eq!(
        facts_by_title["4.2 System interrupts"],
        vec!["imx95@soc#irq-table".to_string()]
    );

    // Also verify `normalize_cited_section` directly.
    assert_eq!(
        normalize_cited_section("Section 4.2 System interrupts").1,
        Some("4.2".to_string())
    );
    assert_eq!(
        normalize_cited_section("Chapter 10. Power Rules").1,
        Some("10".to_string())
    );
    assert_eq!(
        normalize_cited_section("Appendix A Errata").1,
        Some("A".to_string())
    );
}

// ===============================================================================================
// 7. PDF Page Labels (`/PageLabels`) and string decoding unit tests
// ===============================================================================================

#[test]
fn test_pdf_page_labels_extraction_and_string_decoding() {
    let (mut doc, _) = build_pdf_doc(8, &default_outline()[..1]);
    let page_labels_id = doc.add_object(dictionary! {
        "Nums" => Object::Array(vec![
            Object::Integer(0),
            Object::Dictionary(dictionary! {
                "S" => Object::Name(b"r".to_vec()),
            }),
            Object::Integer(3),
            Object::Dictionary(dictionary! {
                "S" => Object::Name(b"D".to_vec()),
                "St" => Object::Integer(1),
            }),
            Object::Integer(6),
            Object::Dictionary(dictionary! {
                "P" => Object::string_literal("A-"),
                "S" => Object::Name(b"D".to_vec()),
                "St" => Object::Integer(1),
            }),
        ]),
    });
    let cat_id = doc.trailer.get(b"Root").unwrap().as_reference().unwrap();
    doc.get_dictionary_mut(cat_id)
        .unwrap()
        .set("PageLabels", Object::Reference(page_labels_id));

    let bytes = save_pdf_bytes(doc);
    assert!(is_pdf_bytes(&bytes));
    let meta = read_pdf_metadata(&bytes, DEFAULT_MAX_OUTLINE_DEPTH).unwrap();
    assert_eq!(meta.pages, 8);
    assert_eq!(meta.page_labels.get(&1).map(String::as_str), Some("i"));
    assert_eq!(meta.page_labels.get(&2).map(String::as_str), Some("ii"));
    assert_eq!(meta.page_labels.get(&3).map(String::as_str), Some("iii"));
    assert_eq!(meta.page_labels.get(&4).map(String::as_str), Some("1"));
    assert_eq!(meta.page_labels.get(&6).map(String::as_str), Some("3"));
    assert_eq!(meta.page_labels.get(&7).map(String::as_str), Some("A-1"));
    assert_eq!(meta.page_labels.get(&8).map(String::as_str), Some("A-2"));

    // Verify UTF-16BE, UTF-16LE, UTF-8 BOM, and PDFDocEncoding string decoding.
    assert_eq!(
        decode_pdf_string(&[0xFE, 0xFF, 0x00, b'H', 0x00, b'i']),
        "Hi"
    );
    assert_eq!(
        decode_pdf_string(&[0xFF, 0xFE, b'H', 0x00, b'i', 0x00]),
        "Hi"
    );
    assert_eq!(decode_pdf_string(&[0xEF, 0xBB, 0xBF, b'U', b'8']), "U8");
    assert_eq!(title(&decode_pdf_string(b"soft\xADhyphen")), "soft hyphen");
    let doc_loaded = load_pdf_document(&bytes).unwrap();
    assert_eq!(extract_page_labels(&doc_loaded, 8).len(), 8);
}

#[test]
fn test_cli_hwspecs_index_subcommand() {
    let fx = TestFixture::new();
    fx.install(
        &make_pdf(120, &default_outline()),
        "widget-trm",
        Some(120),
        "pdf",
    );

    let mut out = Vec::new();
    let mut err = Vec::new();
    let code = hwspecs::run_from_args(
        [
            "hwspecs",
            "--json",
            "index",
            "widget-trm",
            "--root",
            fx.root.to_str().unwrap(),
            "--docs-dir",
            fx.docs.to_str().unwrap(),
        ],
        &mut out,
        &mut err,
    );
    assert_eq!(code, 0, "stderr: {}", String::from_utf8_lossy(&err));
    let parsed: serde_json::Value =
        serde_json::from_slice(&out).expect("CLI --json output must be valid JSON");
    assert_eq!(parsed["ok"], serde_json::json!(true));
    assert_eq!(parsed["sections"], serde_json::json!(5));
    assert!(fx.root.join("index/widget-trm.index.yaml").is_file());

    // Also test explicit `--out <PATH>` and human text output.
    let custom_out = fx.docs.join("custom.index.yaml");
    out.clear();
    err.clear();
    let code2 = hwspecs::run_from_args(
        [
            "hwspecs",
            "index",
            "widget-trm",
            "--root",
            fx.root.to_str().unwrap(),
            "--docs-dir",
            fx.docs.to_str().unwrap(),
            "--out",
            custom_out.to_str().unwrap(),
        ],
        &mut out,
        &mut err,
    );
    assert_eq!(code2, 0);
    assert!(String::from_utf8_lossy(&out).contains("5 section(s) from pdf"));
    assert!(custom_out.is_file());
}

// ===============================================================================================
// #200: index.schema.json bounds section.level to 1..=6, matching the semantic check
// ===============================================================================================

#[test]
fn test_issue_200_index_schema_bounds_section_level() {
    let tmp = TempDir::new().unwrap();
    let validate = |level: u32| -> (i32, String) {
        let path = tmp.path().join(format!("guide{level}.index.yaml"));
        fs::write(
            &path,
            format!(
                "# SPDX-FileCopyrightText: 2026 contributors\n\
                 # SPDX-License-Identifier: Apache-2.0\n\
                 format: 2\n\
                 document: guide\n\
                 sha256: \"{}\"\n\
                 source: markdown\n\
                 lines: 40\n\
                 sections:\n  - {{title: Widget setup, level: {level}, lines: [1, 40]}}\n",
                "a".repeat(64)
            ),
        )
        .unwrap();
        let mut out = Vec::new();
        let mut err = Vec::new();
        let code = hwspecs::run_from_args(
            ["hwspecs", "validate", path.to_str().unwrap()],
            &mut out,
            &mut err,
        );
        let text = format!(
            "{}{}",
            String::from_utf8_lossy(&out),
            String::from_utf8_lossy(&err)
        );
        (code, text)
    };
    for level in [1, 6] {
        let (code, text) = validate(level);
        assert_eq!(code, 0, "level {level} must validate: {text}");
    }
    let (code, text) = validate(7);
    assert_ne!(code, 0, "level 7 must fail schema validation: {text}");
    assert!(
        text.contains("sections[0].level: 7 is greater than the maximum of 6"),
        "{text}"
    );
    let (code, text) = validate(0);
    assert_ne!(code, 0, "level 0 must fail schema validation: {text}");
}
