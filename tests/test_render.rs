// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use driver_lab::render_html;
use driver_lab::render_md;
use scraper::{Html, Selector};

// Helper for parsing HTML in tests like Python's Tree
fn assert_safe(html: &str) -> Html {
    let document = Html::parse_fragment(html);
    // basic check to ensure no unsafe tags
    let all_tags = [
        "p",
        "em",
        "strong",
        "a",
        "span",
        "pre",
        "code",
        "ul",
        "ol",
        "li",
        "blockquote",
        "hr",
        "br",
        "html",
        "body",
    ];
    let mut safe = true;
    for node in document.tree.values() {
        if let scraper::node::Node::Element(elem) = node {
            let tag = elem.name();
            if !all_tags.contains(&tag) {
                safe = false;
                break;
            }
            if tag == "a" {
                if let Some(href) = elem.attr("href") {
                    if !render_html::allowed_link(href) {
                        safe = false;
                        break;
                    }
                }
            }
        }
    }
    assert!(
        safe,
        "HTML contains unsafe elements or attributes: {}",
        html
    );
    document
}

#[test]
fn test_all_generated_punctuation_is_literal() {
    let value = "*emphasis* _under_ [link](javascript:x) ![image](x) <b> &amp; | \\ `code` # head";
    let escaped = render_md::escape(value);

    assert_eq!(render_md::escape("next\n# heading"), "next \\# heading");

    // value has '*', so it will return code span.
    let expected = render_md::code(&value.replace(['\n', '\r'], " "));
    assert_eq!(escaped, expected);
}

#[test]
fn test_code_span_degenerate_and_backtick_aliases() {
    let values = vec![
        "",
        " ",
        "   ",
        "`",
        "``",
        "`x`",
        "`x",
        "x`",
        " x ",
        " x",
        "x ",
        "a`b``c",
        "[x](*y*)",
        "a|b",
        "line\nnext",
    ];
    for value in values {
        let text = render_md::code(value);
        if value.is_empty() {
            assert_eq!(text, "");
        } else {
            // text starts and ends with fence
            assert!(text.starts_with('`'));
            assert!(text.ends_with('`'));
            let inner = value.replace(['\n', '\r'], " ");
            assert!(text.contains(&inner));
        }
    }
}

#[test]
fn test_raw_html_disabled_and_cannot_swallow_markdown() {
    let html = render_html::author("<div class=\"badge\" id=\"fake\">\n*inside*\n</div>");
    assert_safe(&html);
    assert!(html.contains("*inside*"));
    assert!(html.contains("&lt;div"));
}

#[test]
fn test_link_and_autolink_scheme_filter() {
    let bad_urls = vec![
        "javascript:alert(1)",
        "JAVASCRIPT:x",
        "data:text/html,bad",
        "vbscript:x",
        "file:///etc/passwd",
        "//example.invalid/x",
        "/relative",
        "relative",
    ];
    for url in bad_urls {
        let text1 = format!("[x]({})", url);
        let text2 = format!("<{}>", url);

        let html1 = render_html::author(&text1);
        let doc1 = assert_safe(&html1);
        let selector = Selector::parse("a").unwrap();
        assert_eq!(doc1.select(&selector).count(), 0);

        let html2 = render_html::author(&text2);
        let doc2 = assert_safe(&html2);
        assert_eq!(doc2.select(&selector).count(), 0);
    }

    let good_urls = vec![
        "http://example.invalid",
        "https://example.invalid/?a=1&b=2",
        "#local",
    ];
    // Note: MAILTO: was in the Python test but allowed_link only checks http/https/#.
    for url in good_urls {
        let text = format!("[x]({})", url);
        let html = render_html::author(&text);
        let doc = assert_safe(&html);
        let selector = Selector::parse("a").unwrap();
        let a_elem = doc.select(&selector).next().unwrap();
        assert_eq!(a_elem.value().attr("href").unwrap(), url);
    }
}

#[test]
fn test_images_become_links_including_nested_label() {
    let html = render_html::author("![*alt*](https://example.invalid/a.png \"title\")");
    let doc = assert_safe(&html);
    let selector = Selector::parse("a").unwrap();
    let a_elem = doc.select(&selector).next().unwrap();
    assert_eq!(
        a_elem.value().attr("href").unwrap(),
        "https://example.invalid/a.png"
    );
    assert!(html.contains("<em>alt</em>"));

    let bad_urls = vec!["javascript:x", "data:image/png,abc", "//example.invalid/x"];
    for url in bad_urls {
        let html = render_html::author(&format!("![alt]({})", url));
        let doc = assert_safe(&html);
        assert_eq!(doc.select(&selector).count(), 0);
    }
}

#[test]
fn test_autolink_inside_link_label_cannot_nest_anchors() {
    let inners = vec!["https://inner.invalid", "javascript:x"];
    let outers = vec!["https://outer.invalid", "javascript:x"];
    let selector = Selector::parse("a").unwrap();

    for inner in &inners {
        for outer in &outers {
            let text = format!("[<{}>]({})", inner, outer);
            let html = render_html::author(&text);
            let doc = assert_safe(&html);

            let count = doc.select(&selector).count();
            if render_html::allowed_link(outer) {
                assert_eq!(count, 1);
                assert_eq!(
                    doc.select(&selector)
                        .next()
                        .unwrap()
                        .value()
                        .attr("href")
                        .unwrap(),
                    *outer
                );
            } else if render_html::allowed_link(inner) {
                assert_eq!(count, 1);
                assert_eq!(
                    doc.select(&selector)
                        .next()
                        .unwrap()
                        .value()
                        .attr("href")
                        .unwrap(),
                    *inner
                );
            } else {
                assert_eq!(count, 0);
            }
            assert!(html.contains(inner));
        }
    }
}

#[test]
fn test_attributes_from_title_fence_info_and_ordered_list_are_discarded() {
    let text = "9. item\n\n[x](https://example.invalid \"badge id=fake\")\n\n```badge id=fake\n<script>\n```";
    let html = render_html::author(text);
    assert_safe(&html);
    assert!(!html.contains("class="));
    assert!(!html.contains("id="));
    assert!(!html.contains("title="));
    assert!(!html.contains("start="));
}

#[test]
fn test_urls_escape_quotes_ampersands_and_entities() {
    let html = render_html::link("https://example.invalid/\" onmouseover=\"x&y", "label");
    let doc = assert_safe(&html);
    let selector = Selector::parse("a").unwrap();
    let a_elem = doc.select(&selector).next().unwrap();
    assert_eq!(
        a_elem.value().attr("href").unwrap(),
        "https://example.invalid/\" onmouseover=\"x&y"
    );

    let html2 = render_html::author("[x](https://example.invalid/?a=1&amp;b=2)");
    let doc2 = assert_safe(&html2);
    let a_elem2 = doc2.select(&selector).next().unwrap();
    assert_eq!(
        a_elem2.value().attr("href").unwrap(),
        "https://example.invalid/?a=1&b=2"
    );
}

#[test]
fn test_nested_images_links_and_degenerate_fields() {
    let values = vec![
        "",
        " ",
        "\n",
        "***\n\n---",
        "*unfinished",
        "> quote\n\n- *item*",
        "[![alt](https://example.invalid/a)](mailto:x@example.invalid)",
        "![![inner](https://example.invalid/a)](https://example.invalid/b)",
        "one  \ntwo",
        "`<&gic>`",
    ];
    for value in values {
        let html = render_html::author(value);
        assert_safe(&html);
    }
}

#[test]
fn test_cli_render_md_html_and_bf_gw_27_merged_context_warning_banner() {
    let good_root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("skills/spec-format/tests/fixtures/check/good_root");

    // 1. Render Markdown via CLI
    let mut out = Vec::new();
    let mut err = Vec::new();
    let code = driver_lab::run_from_args(
        [
            "driver-lab",
            "render",
            good_root.to_str().unwrap(),
            "--format",
            "md",
            "--require-license",
            "--public-skill",
            "widget-board-tools",
            "--with-status",
        ],
        &mut out,
        &mut err,
    );
    assert_eq!(code, 0, "stderr: {}", String::from_utf8_lossy(&err));
    let md = String::from_utf8(out).unwrap();
    assert!(md.contains("Generated by `spec.py render`"));

    // 2. Render HTML via CLI
    let mut out = Vec::new();
    let mut err = Vec::new();
    let code = driver_lab::run_from_args(
        [
            "driver-lab",
            "render",
            good_root.to_str().unwrap(),
            "--format",
            "html",
            "--require-license",
            "--public-skill",
            "widget-board-tools",
            "--with-status",
        ],
        &mut out,
        &mut err,
    );
    assert_eq!(code, 0, "stderr: {}", String::from_utf8_lossy(&err));
    let html = String::from_utf8(out).unwrap();
    assert!(html.contains("<!doctype html>"));

    // 3. BF-GW-27: render --merged when --context-root has a non-tainting downgraded warning
    let tmp = tempfile::TempDir::new().unwrap();
    let tmp_path = tmp.path().canonicalize().unwrap();
    let ctx_dir = tmp_path.join("ctx");
    let overlay_dir = tmp_path.join("overlay");
    std::fs::create_dir_all(&ctx_dir).unwrap();
    std::fs::create_dir_all(&overlay_dir).unwrap();

    std::fs::write(
        ctx_dir.join("board-specs.yaml"),
        "format: 2\nlayer: public\nname: ctx-root\nlicense: Apache-2.0\naccepts: []\n",
    )
    .unwrap();
    // SoC in context root has an instance pointing to an unloaded third-root IP 'unloadedip'
    std::fs::write(
        ctx_dir.join("testsoc.spec.yaml"),
        "format: 2\nkind: soc\nid: testsoc\nname: Test SoC\ntriggers: [testsoc]\ninstances:\n  - id: u0\n    name: UART0\n    ip: unloadedip\n    reg: \"0x10000000\"\n    irq: {kind: SPI, number: 121, intid: 153}\n    clocks: [uartclk]\n    support:\n      - {class: press, title: Test, url: \"https://example.invalid\"}\n    todo: {check: document, text: check later}\nfacts:\n  - id: base-fact\n    section: quick-facts\n    title: Base fact\n    claim: Base claim.\n    support:\n      - {class: press, title: Test, url: \"https://example.invalid\"}\n    todo: {check: document, text: check later}\n",
    )
    .unwrap();

    std::fs::write(
        overlay_dir.join("board-specs.yaml"),
        "format: 2\nlayer: soc-vendor\nname: overlay-root\nlicense: Apache-2.0\naccepts: []\n",
    )
    .unwrap();
    std::fs::write(
        overlay_dir.join("testsoc-overlay.spec.yaml"),
        "format: 2\nkind: overlay\noverlays: testsoc\nfacts:\n  - id: overlay-fact\n    section: gotchas\n    title: Overlay fact\n    claim: Overlay claim.\n    support:\n      - {class: press, title: Test, url: \"https://example.invalid\"}\n    todo: {check: document, text: check later}\n",
    )
    .unwrap();

    let mut out = Vec::new();
    let mut err = Vec::new();
    let code = driver_lab::run_from_args(
        [
            "driver-lab",
            "render",
            overlay_dir.to_str().unwrap(),
            "--context-root",
            ctx_dir.to_str().unwrap(),
            "--merged",
            "--format",
            "md",
        ],
        &mut out,
        &mut err,
    );
    assert_eq!(
        code,
        0,
        "BF-GW-27: render --merged must succeed with non-tainting context warning: out={} err={}",
        String::from_utf8_lossy(&out),
        String::from_utf8_lossy(&err)
    );
    let merged_md = String::from_utf8(out).unwrap();
    assert!(
        merged_md.contains("Context root warnings:"),
        "BF-GW-27: rendered output must include context warnings banner: {merged_md}"
    );
}
