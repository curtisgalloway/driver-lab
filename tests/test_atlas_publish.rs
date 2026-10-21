// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Integration tests for `atlas`, `explorer`, and `publish` (`test_atlas.py` and `test_explorer.py`).

use hwspecs::explorer::{
    self, atlas, clean_anchor, dump_anchors, empty_anchors_value, fetch_url, heading_key,
    load_anchors, parse_headings, plain, request_headers, resolve_anchors_with,
};
use hwspecs::publish::{self, PublishOptions};
use hwspecs::records::{self, Checker};
use regex::Regex;
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

struct TempDir {
    _inner: tempfile::TempDir,
    path: PathBuf,
}

impl TempDir {
    fn new() -> std::io::Result<Self> {
        let inner = tempfile::TempDir::new()?;
        let path = inner.path().canonicalize()?;
        Ok(Self {
            _inner: inner,
            path,
        })
    }

    fn path(&self) -> &Path {
        &self.path
    }
}

const HDR: &str =
    "# SPDX-FileCopyrightText: 2026 contributors\n# SPDX-License-Identifier: Apache-2.0\n";

fn marker(name: &str, layer: &str, accepts: &str, lic: &str) -> String {
    format!("{HDR}format: 2\nlayer: {layer}\nname: {name}\nlicense: {lic}\naccepts: {accepts}\n")
}

fn default_doc() -> &'static str {
    "    - {name: trm, class: databook, title: Widget TRM, url: \"https://example.invalid/trm.pdf\", pages: 80}\n"
}

fn chip(sid: &str, facts: &str, head: &str) -> String {
    format!(
        "{HDR}format: 2\nkind: chip\nid: {sid}\nname: Widget\ntriggers: [{sid}]\n{head}resources:\n  documents:\n{}facts:\n{facts}",
        default_doc()
    )
}

fn fact(fid: &str, extra: &str) -> String {
    let mut out = format!("  - id: {fid}\n");
    if !extra.contains("    section:") {
        out.push_str("    section: quick-facts\n");
    }
    if !extra.contains("    title:") {
        out.push_str(&format!("    title: T {fid}\n"));
    }
    if !extra.contains("    claim:") {
        out.push_str(&format!("    claim: C {fid}.\n"));
    }
    out.push_str("    support: [{class: databook, doc: trm, at: [{section: \"1\"}]}]\n");
    out.push_str(extra);
    out
}

fn inference(fid: &str, refs: &[&str], extra: &str) -> String {
    let mut out = format!(
        "  - id: {fid}\n    section: quick-facts\n    title: T {fid}\n    claim: C {fid}.\n    support:\n      - class: inference\n        premises:\n"
    );
    for r in refs {
        out.push_str(&format!("          - fact: \"{r}\"\n"));
    }
    out.push_str(&format!(
        "        derivation: it follows\n    todo: {{check: hardware, text: check it.}}\n{extra}"
    ));
    out
}

fn peripheral(sid: &str, head: &str, facts: Option<&str>) -> String {
    let f = facts.map(ToString::to_string).unwrap_or_else(|| {
        "  - id: ident\n    section: identity\n    title: T ident\n    claim: C ident.\n    support: [{class: databook, doc: trm, at: [{section: \"1\"}]}]\n"
            .to_string()
    });
    format!(
        "{HDR}format: 2\nkind: peripheral\nid: {sid}\nname: Widget {sid}\n{head}resources:\n  documents:\n{}facts:\n{f}",
        default_doc()
    )
}

fn write_root_files(dir: &Path, files: &[(&str, String)]) {
    fs::create_dir_all(dir).unwrap();
    for (rel, text) in files {
        let p = dir.join(rel);
        if let Some(parent) = p.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(p, text).unwrap();
    }
}

fn create_checker(roots: &[PathBuf], context_roots: &[PathBuf]) -> Checker {
    let schemas = records::load_schemas();
    let mut checker = Checker::new(false, HashSet::new(), None);
    hwspecs::speccheck::load_and_run_checker(
        &mut checker,
        roots,
        context_roots,
        &[],
        &[],
        false,
        false,
        schemas,
    )
    .unwrap();
    checker
}

fn setup_atlas_root(tmp: &Path) -> PathBuf {
    let r = tmp.join("r");
    let soc_head = concat!(
        "cache: wsoc-resources\n",
        "instances:\n",
        "  - id: u0\n    name: UART0\n    ip: wuart\n    reg: \"0x7e201000\"\n",
        "    irq: {kind: SPI, number: 5}\n    clocks: [uclk]\n",
        "    support: [{class: databook, doc: trm, at: [{section: \"2\"}]}]\n",
        "  - id: t0\n    name: Timer\n    ip: wuart\n    reg: \"0x10000000\"\n",
        "    irq: {kind: PPI, number: 14}\n    clocks: []\n",
        "    support: [{class: databook, doc: trm, at: [{section: \"3\"}]}]\n",
        "  - id: g0\n    name: GPIO\n    ip: wuart\n    reg: null\n",
        "    irq: {kind: SPI, number: 6}\n    clocks: []\n",
        "    todo: {check: document, text: find the base.}\n",
    );
    let soc = chip(
        "wsoc",
        &fact("uart-base", "    claim: UART0 sits at 0x7E201000.\n"),
        soc_head,
    )
    .replace("kind: chip", "kind: soc");

    let board = chip(
        "wb",
        &fact(
            "console",
            "    claim: \"Console when 1 < 2 & 3 > 2.\"\n    relates: [{fact: \"wsoc#uart-base\", relation: refines}]\n",
        ),
        "parts: [wsoc]\ncache: wb-resources\n",
    )
    .replace("kind: chip", "kind: board");

    let ip = chip("wuart", &fact("fifo", "    section: standards\n"), "")
        .replace("kind: chip", "kind: ip");

    let pmic_facts = format!(
        "{}{}",
        fact(
            "rail",
            "    relates: [{fact: \"wsoc#uart-base\", relation: qualifies}]\n"
        ),
        fact(
            "off",
            "    relates: [{fact: \"unrelated#reset\", relation: refines}]\n"
        )
    );
    let pmic = chip("wpmic", &pmic_facts, "");
    let farther = chip(
        "farther",
        &fact(
            "x",
            "    relates: [{fact: \"wpmic#rail\", relation: refines}]\n",
        ),
        "",
    );
    let unrelated = chip("unrelated", &fact("reset", ""), "");

    write_root_files(
        &r,
        &[
            ("board-specs.yaml", marker("r", "public", "[]", "CC-BY-4.0")),
            ("wb.spec.yaml", board),
            ("wsoc.spec.yaml", soc),
            ("wuart.spec.yaml", ip),
            ("wpmic.spec.yaml", pmic),
            ("farther.spec.yaml", farther),
            ("unrelated.spec.yaml", unrelated),
        ],
    );
    r
}

fn add_peripherals(r: &Path) {
    let soc = fs::read_to_string(r.join("wsoc.spec.yaml")).unwrap();
    let soc = soc.replace(
        "  - id: g0\n    name: GPIO\n    ip: wuart\n",
        "  - id: g0\n    name: GPIO\n    peripheral: wgpio\n",
    );
    fs::write(r.join("wsoc.spec.yaml"), soc).unwrap();
    fs::write(
        r.join("wdma.spec.yaml"),
        peripheral("wdma", "describes: [wsoc]\n", None),
    )
    .unwrap();
    fs::write(r.join("wgpio.spec.yaml"), peripheral("wgpio", "", None)).unwrap();
    fs::write(
        r.join("wpwm.spec.yaml"),
        peripheral("wpwm", "describes: [wpmic]\n", None),
    )
    .unwrap();
    fs::write(
        r.join("wclk.spec.yaml"),
        chip("wclk", &inference("derived", &["wsoc#uart-base"], ""), ""),
    )
    .unwrap();
    let row_facts = format!(
        "{}{}{}",
        fact(
            "at-row",
            "    relates: [{fact: \"wsoc#u0\", relation: refines}]\n"
        ),
        fact(
            "at-fact",
            "    relates: [{fact: \"wb#console\", relation: refines}]\n"
        ),
        fact(
            "at-unmapped",
            "    relates: [{fact: \"wsoc#g0\", relation: refines}]\n"
        ),
    );
    fs::write(r.join("wrow.spec.yaml"), chip("wrow", &row_facts, "")).unwrap();
}

fn cli_atlas(root: &Path, extra_args: &[&str]) -> (i32, Value) {
    let mut out = Vec::new();
    let mut err = Vec::new();
    let mut argv = vec![
        "hwspecs".to_string(),
        "render".to_string(),
        "--format".to_string(),
        "atlas".to_string(),
        "--json".to_string(),
        root.to_string_lossy().into_owned(),
    ];
    for a in extra_args {
        argv.push((*a).to_string());
    }
    let code = hwspecs::run_from_args(argv, &mut out, &mut err);
    let val: Value = serde_json::from_slice(&out).unwrap();
    (code, val)
}

fn extract_embedded_json(html: &str) -> Value {
    let re =
        Regex::new(r#"(?s)<script type="application/json" id="spec-data">(.*?)</script>"#).unwrap();
    let caps = re
        .captures(html)
        .expect("HTML must contain <script type=\"application/json\" id=\"spec-data\">");
    serde_json::from_str(caps.get(1).unwrap().as_str()).unwrap()
}

// ===========================================================================
// Atlas Tests (port of `test_atlas.py`)
// ===========================================================================

#[test]
fn test_selection_is_parts_instances_and_one_link_away() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    let checker = create_checker(&[r], &[]);
    let d = atlas::data(&checker, "wb", false, &[], "unavailable").unwrap();
    let specs = d["specs"].as_array().unwrap();
    let joins: HashMap<String, (Option<String>, String)> = specs
        .iter()
        .map(|s| {
            (
                s["id"].as_str().unwrap().to_string(),
                (
                    s["parent"].as_str().map(ToString::to_string),
                    s["join"].as_str().unwrap().to_string(),
                ),
            )
        })
        .collect();
    assert_eq!(joins.len(), 4);
    assert_eq!(joins["wb"], (None, String::new()));
    assert_eq!(joins["wsoc"], (Some("wb".to_string()), "parts".to_string()));
    assert_eq!(joins["wuart"], (Some("wsoc".to_string()), "ip".to_string()));
    assert_eq!(
        joins["wpmic"],
        (Some("wsoc".to_string()), "related".to_string())
    );
    assert!(!joins.contains_key("farther"));
    assert!(!joins.contains_key("unrelated"));
}

#[test]
fn test_relations_resolve_to_full_references() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    let checker = create_checker(&[r], &[]);
    let d = atlas::data(&checker, "wb", false, &[], "unavailable").unwrap();
    let facts: HashMap<String, &Value> = d["facts"]
        .as_array()
        .unwrap()
        .iter()
        .map(|f| (f["key"].as_str().unwrap().to_string(), f))
        .collect();

    assert_eq!(
        facts["wb@r#console"]["relates"],
        json!([{
            "in_page": true,
            "relation": "refines",
            "target": "wsoc@r#uart-base",
            "target_spec": "wsoc",
        }])
    );
    assert_eq!(facts["wb@r#console"]["outside_links"], json!(0));
    assert_eq!(facts["wpmic@r#off"]["outside_links"], json!(1));
    assert_eq!(facts["wpmic@r#off"]["relates"][0]["in_page"], json!(false));
}

#[test]
fn test_memory_map_orders_by_address_skips_null_and_finds_citing_facts() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    let checker = create_checker(&[r], &[]);
    let d = atlas::data(&checker, "wb", false, &[], "unavailable").unwrap();
    let mm = d["memory_map"].as_array().unwrap();
    let keys: Vec<&str> = mm.iter().map(|m| m["key"].as_str().unwrap()).collect();
    assert_eq!(keys, vec!["wsoc@r#t0", "wsoc@r#u0"]);
    assert_eq!(mm[0]["next_base"], json!("0x7e201000"));
    assert_eq!(mm[0]["span"], json!("1.7 GiB"));
    assert_eq!(mm[1]["cites"], json!(["wsoc@r#uart-base"]));
}

#[test]
fn test_author_text_is_escaped_and_the_page_loads_no_outside_script() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    let checker = create_checker(&[r], &[]);
    let html = atlas::page(&checker, "wb", false, &[], "unavailable").unwrap();
    assert_eq!(html.matches("<script").count(), 2);
    assert!(!html.contains("<script src"));
    assert!(!html.contains("<link "));
    let d = extract_embedded_json(&html);
    let console = d["facts"]
        .as_array()
        .unwrap()
        .iter()
        .find(|f| f["id"] == "console")
        .unwrap();
    assert!(console["claim_html"]
        .as_str()
        .unwrap()
        .contains("1 &lt; 2 &amp; 3 &gt; 2"));
    assert_eq!(console["text"], json!("Console when 1 < 2 & 3 > 2."));
}

#[test]
fn test_output_is_deterministic() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    let checker = create_checker(&[r], &[]);
    let first = atlas::page(&checker, "wb", false, &[], "unavailable").unwrap();
    let second = atlas::page(&checker, "wb", false, &[], "unavailable").unwrap();
    assert_eq!(first, second);
}

#[test]
fn test_any_spec_can_be_the_center() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    let checker = create_checker(&[r], &[]);
    let d = atlas::data(&checker, "wuart", false, &[], "unavailable").unwrap();
    assert_eq!(d["specs"][0]["id"], json!("wuart"));
}

#[test]
fn test_unknown_spec_is_a_usage_error() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    let checker = create_checker(&[r], &[]);
    let err = atlas::data(&checker, "nope", false, &[], "unavailable").unwrap_err();
    assert!(err.contains("no spec 'nope' in the rendered roots"));
}

#[test]
fn test_cli_needs_spec_and_returns_html_key() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    let (code, res) = cli_atlas(&r, &[]);
    assert_eq!(code, 2);
    assert_eq!(res["error"], json!("usage"));
    assert!(res["html"].is_null());

    let (code, res) = cli_atlas(&r, &["--spec", "nope"]);
    assert_eq!(code, 2);
    assert_eq!(res["error"], json!("usage"));

    let (code, res) = cli_atlas(&r, &["--spec", "wb"]);
    assert_eq!(code, 0);
    assert_eq!(res["ok"], json!(true));
    assert!(res["html"]
        .as_str()
        .unwrap()
        .contains("<title>Widget atlas</title>"));
}

#[test]
fn test_missing_spec_is_a_usage_error_even_when_files_have_errors() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    fs::write(
        r.join("wb.spec.yaml"),
        format!("{HDR}format: 2\nkind: board\n"),
    )
    .unwrap();
    let (code, res) = cli_atlas(&r, &[]);
    assert_eq!(code, 2);
    assert_eq!(res["error"], json!("usage"));
}

#[test]
fn test_small_base_addresses_cite_nothing() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    let text = fs::read_to_string(r.join("wsoc.spec.yaml")).unwrap();
    fs::write(
        r.join("wsoc.spec.yaml"),
        text.replace("\"0x10000000\"", "\"0x100\""),
    )
    .unwrap();
    let checker = create_checker(&[r], &[]);
    let d = atlas::data(&checker, "wb", false, &[], "unavailable").unwrap();
    assert_eq!(d["memory_map"][0]["cites"], json!([]));
}

#[test]
fn test_peripheral_specs_join_by_describes_and_by_instance() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    add_peripherals(&r);
    let checker = create_checker(&[r], &[]);
    let d = atlas::data(&checker, "wb", false, &[], "unavailable").unwrap();
    let joins: HashMap<String, (Option<String>, String)> = d["specs"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| {
            (
                s["id"].as_str().unwrap().to_string(),
                (
                    s["parent"].as_str().map(ToString::to_string),
                    s["join"].as_str().unwrap().to_string(),
                ),
            )
        })
        .collect();
    assert_eq!(
        joins["wdma"],
        (Some("wsoc".to_string()), "programming".to_string())
    );
    assert_eq!(
        joins["wgpio"],
        (Some("wsoc".to_string()), "programming".to_string())
    );
    assert!(!joins.contains_key("wpwm"));
}

#[test]
fn test_inference_premises_are_fact_links() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    add_peripherals(&r);
    let checker = create_checker(&[r], &[]);
    let d = atlas::data(&checker, "wb", false, &[], "unavailable").unwrap();
    let joins: HashMap<String, (Option<String>, String)> = d["specs"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| {
            (
                s["id"].as_str().unwrap().to_string(),
                (
                    s["parent"].as_str().map(ToString::to_string),
                    s["join"].as_str().unwrap().to_string(),
                ),
            )
        })
        .collect();
    assert_eq!(
        joins["wclk"],
        (Some("wsoc".to_string()), "related".to_string())
    );
    let derived = d["facts"]
        .as_array()
        .unwrap()
        .iter()
        .find(|f| f["key"] == "wclk@r#derived")
        .unwrap();
    assert_eq!(
        derived["premises"],
        json!([{
            "in_page": true,
            "target": "wsoc@r#uart-base",
            "target_spec": "wsoc",
            "uses": "",
        }])
    );
    assert_eq!(derived["relates"][0]["relation"], json!("premise"));
}

#[test]
fn test_links_to_rows_on_the_page_are_not_outside_links() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    add_peripherals(&r);
    let checker = create_checker(&[r], &[]);
    let d = atlas::data(&checker, "wb", false, &[], "unavailable").unwrap();
    let facts: HashMap<String, &Value> = d["facts"]
        .as_array()
        .unwrap()
        .iter()
        .map(|f| (f["key"].as_str().unwrap().to_string(), f))
        .collect();
    assert_eq!(facts["wrow@r#at-row"]["outside_links"], json!(0));
    assert_eq!(facts["wrow@r#at-row"]["relates"][0]["in_page"], json!(true));
    assert_eq!(facts["wrow@r#at-unmapped"]["outside_links"], json!(0));
    assert_eq!(
        facts["wrow@r#at-unmapped"]["relates"][0]["in_page"],
        json!(true)
    );
    let u0 = d["memory_map"]
        .as_array()
        .unwrap()
        .iter()
        .find(|m| m["key"] == "wsoc@r#u0")
        .unwrap();
    let cites: Vec<&str> = u0["cites"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| c.as_str().unwrap())
        .collect();
    assert!(cites.contains(&"wrow@r#at-row"));
    assert!(cites.contains(&"wsoc@r#uart-base"));
}

#[test]
fn test_specs_left_out_are_listed_by_kind() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    add_peripherals(&r);
    let checker = create_checker(&[r], &[]);
    let d = atlas::data(&checker, "wb", false, &[], "unavailable").unwrap();
    let unplaced: HashMap<String, String> = d["unplaced"]
        .as_array()
        .unwrap()
        .iter()
        .map(|u| {
            (
                u["id"].as_str().unwrap().to_string(),
                u["kind"].as_str().unwrap().to_string(),
            )
        })
        .collect();
    assert_eq!(unplaced.len(), 3);
    assert_eq!(unplaced["farther"], "chip");
    assert_eq!(unplaced["unrelated"], "chip");
    assert_eq!(unplaced["wpwm"], "peripheral");
}

#[test]
fn test_context_roots_are_not_listed() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    add_peripherals(&r);
    let ctx = tmp.path().join("ctx");
    write_root_files(
        &ctx,
        &[
            (
                "board-specs.yaml",
                marker("ctx", "public", "[]", "CC-BY-4.0"),
            ),
            ("lonely.spec.yaml", chip("lonely", &fact("reset", ""), "")),
        ],
    );
    let checker = create_checker(&[r], &[ctx]);
    let d = atlas::data(&checker, "wb", false, &[], "unavailable").unwrap();
    let ids: Vec<&str> = d["unplaced"]
        .as_array()
        .unwrap()
        .iter()
        .map(|u| u["id"].as_str().unwrap())
        .collect();
    assert!(!ids.contains(&"lonely"));
}

#[test]
fn test_every_view_of_a_fact_todo_also_shows_its_row_todos() {
    let tmp = TempDir::new().unwrap();
    let r = setup_atlas_root(tmp.path());
    let reg_fact = concat!(
        "  - id: ident\n    section: identity\n    title: T ident\n    claim: C ident.\n",
        "    support: [{class: databook, doc: trm, at: [{section: \"1\"}]}]\n",
        "  - id: reg-ctrl\n    section: registers\n    title: CTRL\n",
        "    support: [{class: databook, doc: trm, at: [{section: \"1\"}]}]\n",
        "    data:\n      register: {name: CTRL, offset: \"0x0\", width: 32, access: read-write}\n",
        "      fields:\n        - {id: en, name: EN, bits: [0, 0], meaning: enable,\n",
        "           todo: {check: hardware, text: confirm reset bit.}}\n",
    );
    fs::write(
        r.join("wdma.spec.yaml"),
        peripheral("wdma", "describes: [wsoc]\n", Some(reg_fact)),
    )
    .unwrap();
    let checker = create_checker(&[r], &[]);
    let d = atlas::data(&checker, "wb", false, &[], "unavailable").unwrap();
    let ctrl = d["facts"]
        .as_array()
        .unwrap()
        .iter()
        .find(|f| f["key"] == "wdma@r#reg-ctrl")
        .unwrap();
    assert!(ctrl["todo"].is_null());
    assert_eq!(
        ctrl["row_todos"],
        json!([{
            "check": "hardware",
            "id": "en",
            "text": "confirm reset bit.",
        }])
    );
    let js = include_str!("../skills/spec-format/scripts/atlas.js");
    assert_eq!(js.matches("f.todo.check || 'check'").count(), 3);
    assert!(js.matches("f.row_todos").count() >= 4);
}

#[test]
fn test_search_reads_row_todo_text() {
    let js = include_str!("../skills/spec-format/scripts/explorer.js");
    let re = Regex::new(r"(?s)f\.hay = \[.*?\]\.join").unwrap();
    let m = re.find(js).expect("explorer.js must define f.hay = [...]");
    assert!(m.as_str().contains("f.row_todos"));
}

// ===========================================================================
// Explorer & Publish Tests (port of `test_explorer.py`)
// ===========================================================================

const BLOB: &str =
    "https://github.com/o/r/blob/cccccccccccccccccccccccccccccccccccccccc/doc/boot.rst";
const WIKI: &str = "https://github.com/o/r/wiki/Mailboxes";

fn setup_explorer_root(tmp: &Path, name: &str, url: &str) -> PathBuf {
    let r = tmp.join(name);
    let docs = format!(
        "    - {{name: guide, class: doc, title: Boot Guide, url: \"{url}\"}}\n{}",
        default_doc()
    );
    let facts = format!(
        "  - id: boot-seq\n    section: quick-facts\n    title: Boot sequence\n    claim: \"See *Boot* and `UART0`.\"\n    support:\n      - class: doc\n        doc: guide\n        at:\n          - {{heading: \"Setup & Boot\", section: \"2.1\"}}\n          - {{heading: \"Missing Heading\"}}\n      - class: databook\n        doc: trm\n        at:\n          - {{page: \"12\", section: \"3.4\"}}\n{}",
        fact("plain-fact", "")
    );
    let spec = format!(
        "{HDR}format: 2\nkind: chip\nid: widgetchip\nname: Widget\ntriggers: [widgetchip]\norientation: \"Start at *boot-seq*.\"\nresources:\n  documents:\n{docs}facts:\n{facts}"
    );
    write_root_files(
        &r,
        &[
            ("board-specs.yaml", marker("r", "public", "[]", "CC-BY-4.0")),
            ("widgetchip.spec.yaml", spec),
        ],
    );
    r
}

fn decode_explorer_payload(html: &str) -> Value {
    let prefix = "<script type=\"application/json\" id=\"spec-data\">";
    let start = html
        .find(prefix)
        .expect("explorer html must have spec-data")
        + prefix.len();
    let end = start + html[start..].find("</script>").unwrap();
    let raw = &html[start..end];
    assert!(
        !raw.contains('<') && !raw.contains('>'),
        "raw JSON script block must escape < and >"
    );
    serde_json::from_str(raw).unwrap()
}

#[test]
fn test_both_github_shapes_first_occurrence_wins_and_prefix_dropped() {
    let html = r##"
    <div class="markdown-heading">
      <h2 class="heading-element">2.1   Setup &amp; Boot</h2>
      <a id="user-content-21-setup--boot" class="anchor" href="#21-setup--boot"></a>
    </div>
    <h3><a id="user-content-old" class="anchor" href="#kernel_old"></a>Old Style</h3>
    <h2>Duplicate</h2><a href="#first"></a>
    <h2>Duplicate</h2><a href="#second"></a>
    <h2><a href="https://example.invalid/out#wrong">External</a></h2>
    "##;
    let found = parse_headings(html);
    assert_eq!(
        found.get(&heading_key("Setup & Boot")).map(String::as_str),
        Some("21-setup--boot")
    );
    assert_eq!(
        found
            .get(&heading_key("2.1 Setup & Boot"))
            .map(String::as_str),
        Some("21-setup--boot")
    );
    assert_eq!(
        found.get(&heading_key("Old Style")).map(String::as_str),
        Some("kernel_old")
    );
    assert_eq!(
        found.get(&heading_key("Duplicate")).map(String::as_str),
        Some("first")
    );
    assert!(!found.contains_key(&heading_key("External")));
    assert_eq!(
        heading_key("2. Setup the device tree"),
        "setup the device tree"
    );
}

#[test]
fn test_only_pinned_blobs_and_wikis_are_fetched() {
    assert_eq!(
        fetch_url(BLOB),
        Some((
            "https://api.github.com/repos/o/r/contents/doc/boot.rst?ref=cccccccccccccccccccccccccccccccccccccccc".to_string(),
            "application/vnd.github.html+json".to_string()
        ))
    );
    assert_eq!(
        fetch_url(WIKI),
        Some((WIKI.to_string(), "text/html".to_string()))
    );
    for refused in [
        "https://github.com/o/r/blob/main/doc/boot.rst",
        "https://github.com/o/r/blob/cccccccccccccccccccccccccccccccccccccccc/../secret",
        "https://github.com/o/r/wiki/..",
        "https://github.com/o/r/wiki/a/b",
        "https://example.invalid/doc/boot.rst",
        "http://github.com/o/r/wiki/Mailboxes",
    ] {
        assert!(
            fetch_url(refused).is_none(),
            "expected fetch_url to refuse {refused}"
        );
    }
}

#[test]
fn test_token_only_to_the_api_and_never_on_redirect() {
    let mut env = HashMap::new();
    env.insert("GITHUB_TOKEN".to_string(), "secret-token".to_string());
    let (api_target, api_accept) = fetch_url(BLOB).unwrap();
    let api_headers = request_headers(&api_target, &api_accept, &env);
    assert_eq!(
        api_headers.get("Authorization").map(String::as_str),
        Some("Bearer secret-token")
    );

    let (wiki_target, wiki_accept) = fetch_url(WIKI).unwrap();
    let wiki_headers = request_headers(&wiki_target, &wiki_accept, &env);
    assert!(!wiki_headers.contains_key("Authorization"));
}

#[test]
fn test_resolve_records_anchor_and_unresolved_without_failing() {
    let tmp = TempDir::new().unwrap();
    let r = setup_explorer_root(tmp.path(), "r", BLOB);
    let checker = create_checker(&[r], &[]);
    let result = resolve_anchors_with(&checker, |_url| {
        Ok("<h2>2.1 Setup &amp; Boot</h2><a href=\"#21-setup--boot\"></a>".to_string())
    });
    assert_eq!(
        result["anchors"],
        json!({BLOB: {"Setup & Boot": "21-setup--boot"}})
    );
    assert_eq!(
        result["unresolved"],
        json!([{
            "heading": "Missing Heading",
            "reason": "heading not found in document",
            "url": BLOB,
        }])
    );
    assert_eq!(
        explorer::unresolved_report(&result),
        vec![format!(
            "unresolved heading: {BLOB} :: Missing Heading (heading not found in document)"
        )]
    );
}

#[test]
fn test_fetch_failure_leaves_headings_unresolved() {
    let tmp = TempDir::new().unwrap();
    let r = setup_explorer_root(tmp.path(), "r", BLOB);
    let checker = create_checker(&[r], &[]);
    let result = resolve_anchors_with(&checker, |_url| Err("HTTP 404".to_string()));
    assert_eq!(result["anchors"], json!({}));
    assert_eq!(result["unresolved"].as_array().unwrap().len(), 2);
}

#[test]
fn test_unsafe_fetched_anchor_is_not_kept() {
    let tmp = TempDir::new().unwrap();
    let r = setup_explorer_root(tmp.path(), "r", BLOB);
    let checker = create_checker(&[r], &[]);
    assert!(clean_anchor("bad\"><script>alert(1)</script>").is_none());
    let result = resolve_anchors_with(&checker, |_url| {
        Ok("<h2>Setup &amp; Boot</h2><a href=\"#bad%22%3E\"></a>".to_string())
    });
    assert_eq!(result["anchors"], json!({}));
}

#[test]
fn test_load_refuses_anything_build_would_not_write() {
    let tmp = TempDir::new().unwrap();
    let r = setup_explorer_root(tmp.path(), "r", BLOB);
    let checker = create_checker(&[r], &[]);
    let good = json!({
        "format": 1,
        "anchors": {BLOB: {"Setup & Boot": "21-setup--boot"}},
        "unresolved": [{"url": BLOB, "heading": "Missing Heading", "reason": "not found"}],
    });
    let loaded = load_anchors(&dump_anchors(&good), &checker).unwrap();
    assert_eq!(loaded[BLOB]["Setup & Boot"], "21-setup--boot");

    let bad_cases = vec![
        "{not json".to_string(),
        dump_anchors(&json!({"format": 2, "anchors": {}, "unresolved": []})),
        format!(" {}", dump_anchors(&empty_anchors_value())),
        dump_anchors(&json!({
            "format": 1,
            "anchors": {"https://evil.invalid/doc": {"Setup & Boot": "x"}},
            "unresolved": [],
        })),
        dump_anchors(&json!({
            "format": 1,
            "anchors": {BLOB: {"Uncited": "x"}},
            "unresolved": [],
        })),
        dump_anchors(&json!({
            "format": 1,
            "anchors": {BLOB: {"Setup & Boot": "bad\"quote"}},
            "unresolved": [],
        })),
        dump_anchors(&json!({
            "format": 1,
            "anchors": {BLOB: {}},
            "unresolved": [],
        })),
        dump_anchors(&json!({
            "format": 1,
            "anchors": {},
            "unresolved": [{"url": BLOB, "heading": "Uncited", "reason": "x"}],
        })),
        dump_anchors(&json!({
            "format": 1,
            "anchors": {BLOB: {"Setup & Boot": "ok"}},
            "unresolved": [{"url": BLOB, "heading": "Setup & Boot", "reason": "dup"}],
        })),
    ];
    for text in bad_cases {
        assert!(
            load_anchors(&text, &checker).is_err(),
            "expected load_anchors to refuse: {text}"
        );
    }
}

#[test]
fn test_jump_link_only_on_the_declared_document_url() {
    let tmp = TempDir::new().unwrap();
    let r = setup_explorer_root(tmp.path(), "r", BLOB);
    let checker = create_checker(&[r], &[]);
    let mut anchors = BTreeMap::new();
    let mut inner = BTreeMap::new();
    inner.insert("Setup & Boot".to_string(), "21-setup--boot".to_string());
    anchors.insert(BLOB.to_string(), inner);

    let d = explorer::data(
        &checker,
        &anchors,
        &[],
        "0123456789abcdef0123456789abcdef01234567",
    )
    .unwrap();
    let cites = &d["specs"][0]["facts"][0]["cites"];
    assert_eq!(
        cites[0]["locators"][0]["url"],
        json!(format!("{BLOB}#21-setup--boot"))
    );
    assert_eq!(cites[0]["locators"][1]["url"], json!(""));
    assert_eq!(
        cites[1]["locators"][0]["url"],
        json!("https://example.invalid/trm.pdf#page=12")
    );
}

#[test]
fn test_hostile_text_stays_inside_the_json_and_author_html_is_sanitized() {
    let tmp = TempDir::new().unwrap();
    let r = setup_explorer_root(tmp.path(), "r", BLOB);
    let hostile = "</script><script>alert(1)</script> & [bad](javascript:alert(1))";
    let path = r.join("widgetchip.spec.yaml");
    let text = fs::read_to_string(&path).unwrap();
    fs::write(
        &path,
        text.replace(
            "claim: \"See *Boot* and `UART0`.\"",
            &format!("claim: {hostile:?}"),
        ),
    )
    .unwrap();
    let checker = create_checker(&[r], &[]);
    let html = explorer::try_page_with_check(
        &checker,
        &BTreeMap::new(),
        &[],
        "0123456789abcdef0123456789abcdef01234567",
        false,
    )
    .unwrap();
    assert_eq!(html.matches("<script").count(), 2);
    assert_eq!(html.matches("</script>").count(), 2);
    let payload = decode_explorer_payload(&html);
    let fact = &payload["specs"][0]["facts"][0];
    assert!(!fact["claim_html"].as_str().unwrap().contains("javascript:"));
    assert!(!fact["claim_html"].as_str().unwrap().contains("<script>"));
    assert!(fact["claim_html"]
        .as_str()
        .unwrap()
        .contains("&lt;/script&gt;"));
    assert_eq!(
        plain(&hwspecs::render_html::author(
            "See *Boot*, `UART0` and [the guide](https://example.invalid)."
        )),
        "See Boot, UART0 and the guide."
    );
}

#[test]
fn test_unsafe_fields_are_refused_like_the_viewer() {
    let tmp = TempDir::new().unwrap();
    let r = setup_explorer_root(tmp.path(), "r", BLOB);
    let mut checker = create_checker(&[r], &[]);
    checker.files[0].data["facts"][0]["claim"] = json!("<b>raw html</b>");
    assert!(explorer::try_page(&checker, &BTreeMap::new(), &[], "0123").is_err());
}

#[test]
fn test_payload_is_deterministic_and_carries_status_and_pages() {
    let good_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("skills/spec-format/tests/fixtures/check/good_root");
    let schemas = records::load_schemas();
    let mut checker = Checker::new(
        true,
        HashSet::from(["widget-board-tools".to_string()]),
        None,
    );
    hwspecs::speccheck::load_and_run_checker(
        &mut checker,
        &[good_root],
        &[],
        &[],
        &[],
        false,
        false,
        schemas,
    )
    .unwrap();
    let pages = vec![json!({
        "spec": "widgetboard",
        "source": "widget-specs:widgetboard.spec.yaml",
        "html": "spec-1.html",
        "markdown": "spec-1.md",
    })];
    let first = explorer::try_page(
        &checker,
        &BTreeMap::new(),
        &pages,
        "0123456789abcdef0123456789abcdef01234567",
    )
    .unwrap();
    let second = explorer::try_page(
        &checker,
        &BTreeMap::new(),
        &pages,
        "0123456789abcdef0123456789abcdef01234567",
    )
    .unwrap();
    assert_eq!(first, second);
    let payload = decode_explorer_payload(&first);
    let specs: HashMap<String, &Value> = payload["specs"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| (s["id"].as_str().unwrap().to_string(), s))
        .collect();
    assert_eq!(
        specs["widgetboard"]["pages"],
        json!([{
            "label": "widget-specs:widgetboard.spec.yaml",
            "html": "spec-1.html",
            "markdown": "spec-1.md",
        }])
    );
    assert!(specs["widgetsoc"]["facts"]
        .as_array()
        .unwrap()
        .iter()
        .any(|f| !f["status"].as_str().unwrap().is_empty()));
}

#[test]
fn test_premises_assumptions_conflicts_notes_and_second_reader() {
    let tmp = TempDir::new().unwrap();
    let r = tmp.path().join("r");
    let src_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("skills/spec-format/tests/fixtures/check/good_root");
    fs::create_dir_all(r.join("ip")).unwrap();
    for rel in [
        "board-specs.yaml",
        "widgetboard.spec.yaml",
        "widgetsoc.spec.yaml",
        "ip/widgetuart.spec.yaml",
    ] {
        fs::copy(src_root.join(rel), r.join(rel)).unwrap();
    }
    let soc_path = r.join("widgetsoc.spec.yaml");
    let soc_txt = fs::read_to_string(&soc_path).unwrap().replace(
        "    assumes: [same-silicon]\n",
        "    critical: true\n    note: \"Important fact note.\"\n    assumes: [same-silicon]\n",
    );
    fs::write(&soc_path, soc_txt).unwrap();

    let schemas = records::load_schemas();
    let mut checker = Checker::new(
        false,
        HashSet::from(["widget-board-tools".to_string()]),
        None,
    );
    hwspecs::speccheck::load_and_run_checker(
        &mut checker,
        std::slice::from_ref(&r),
        &[],
        &[],
        &[],
        false,
        false,
        schemas,
    )
    .unwrap();
    let soc_status = checker
        .status
        .iter()
        .find(|(idx, _)| checker.files[*idx].spec_id() == "widgetsoc")
        .unwrap();
    let basis = soc_status
        .1
        .facts
        .iter()
        .find(|row| row.key == "uart-base")
        .unwrap()
        .basis
        .clone()
        .unwrap();
    fs::create_dir_all(r.join("widget-resources")).unwrap();
    fs::write(
        r.join("widget-resources/widgetsoc.verify.yaml"),
        format!(
            "{HDR}format: 1\nspec: widgetsoc\nspec_file: widgetsoc.spec.yaml\nverdicts:\n  uart-base:\n    verdict: PASS\n    date: 2026-04-01\n    verifier: alice\n    basis: {basis}\n    method:\n      kind: document\n      checked: checked against TRM\n    reading:\n      quotes:\n        - doc: widget-trm\n          at: {{section: \"6.1\", pages: [\"92\", \"93\"]}}\n          quote: \"UART0 sits at legacy 0x7e201000.\"\n"
        ),
    )
    .unwrap();

    let mut checker = Checker::new(
        false,
        HashSet::from(["widget-board-tools".to_string()]),
        None,
    );
    hwspecs::speccheck::load_and_run_checker(
        &mut checker,
        &[r],
        &[],
        &[],
        &[],
        false,
        false,
        schemas,
    )
    .unwrap();

    let payload = explorer::data(
        &checker,
        &BTreeMap::new(),
        &[],
        "0123456789abcdef0123456789abcdef01234567",
    )
    .unwrap();
    let facts: Vec<&Value> = payload["specs"]
        .as_array()
        .unwrap()
        .iter()
        .flat_map(|s| s["facts"].as_array().unwrap())
        .collect();
    assert!(facts
        .iter()
        .any(|f| !f["assumes"].as_array().unwrap().is_empty()));
    assert!(facts
        .iter()
        .any(|f| f["contested"] == json!(true) && !f["conflicts"].as_array().unwrap().is_empty()));
    assert!(facts.iter().any(|f| f["cites"]
        .as_array()
        .unwrap()
        .iter()
        .any(|c| !c["premises"].as_array().unwrap().is_empty())));
    assert!(facts
        .iter()
        .any(|f| f["second_reader_missing"] == json!(true)));
    assert!(facts
        .iter()
        .any(|f| !f["notes_html"].as_array().unwrap().is_empty()));
    assert!(facts.iter().any(|f| f["cites"]
        .as_array()
        .unwrap()
        .iter()
        .any(|c| !c["anchors"].as_array().unwrap().is_empty())));
}

fn make_publish_opts(root: &Path, out: &Path) -> PublishOptions {
    PublishOptions {
        root: root.to_path_buf(),
        context_root: Vec::new(),
        public_skill: vec!["widget-board-tools".to_string()],
        source_commit: vec![format!(
            "{}=1111111111111111111111111111111111111111",
            root.display()
        )],
        tool_commit: "2222222222222222222222222222222222222222".to_string(),
        require_verified: Some("main".to_string()),
        out: out.to_path_buf(),
        fetch_anchors: false,
    }
}

#[test]
fn test_build_writes_explorer_and_anchors_and_verify_rechecks_them() {
    let good_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("skills/spec-format/tests/fixtures/check/good_root");
    let tmp = TempDir::new().unwrap();
    let out = tmp.path().join("site");
    let schemas = records::load_schemas();
    let mut checker = Checker::new(
        true,
        HashSet::from(["widget-board-tools".to_string()]),
        Some("main".to_string()),
    );
    hwspecs::speccheck::load_and_run_checker(
        &mut checker,
        std::slice::from_ref(&good_root),
        &[],
        &[],
        &[],
        false,
        false,
        schemas,
    )
    .unwrap();
    let opts = make_publish_opts(&good_root, &out);
    publish::build(&checker, &opts).unwrap();
    publish::check(&checker, &opts).unwrap();

    let manifest: Value =
        serde_json::from_str(&fs::read_to_string(out.join("manifest.json")).unwrap()).unwrap();
    assert!(manifest["sha256"].get("anchors.json").is_some());
    assert!(manifest["sha256"].get("index.html").is_some());
    let payload = decode_explorer_payload(&fs::read_to_string(out.join("index.html")).unwrap());
    assert_eq!(
        payload["tool_commit"],
        json!("2222222222222222222222222222222222222222")
    );
}

#[test]
fn test_verify_refuses_missing_malformed_or_rewritten_anchors() {
    let good_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("skills/spec-format/tests/fixtures/check/good_root");
    let tmp = TempDir::new().unwrap();
    let out = tmp.path().join("site");
    let schemas = records::load_schemas();
    let mut checker = Checker::new(
        true,
        HashSet::from(["widget-board-tools".to_string()]),
        Some("main".to_string()),
    );
    hwspecs::speccheck::load_and_run_checker(
        &mut checker,
        std::slice::from_ref(&good_root),
        &[],
        &[],
        &[],
        false,
        false,
        schemas,
    )
    .unwrap();
    let opts = make_publish_opts(&good_root, &out);
    publish::build(&checker, &opts).unwrap();

    let anchors_path = out.join("anchors.json");
    let saved = fs::read_to_string(&anchors_path).unwrap();

    fs::write(
        &anchors_path,
        dump_anchors(&json!({
            "format": 1,
            "anchors": {"https://evil.invalid": {"H": "a"}},
            "unresolved": [],
        })),
    )
    .unwrap();
    assert!(publish::check(&checker, &opts).is_err());

    fs::remove_file(&anchors_path).unwrap();
    assert!(publish::check(&checker, &opts).is_err());

    fs::write(&anchors_path, saved).unwrap();
    publish::check(&checker, &opts).unwrap();
}

#[test]
fn test_fetch_anchors_flag_uses_the_network_resolver() {
    let tmp = TempDir::new().unwrap();
    let r = setup_explorer_root(tmp.path(), "r", BLOB);
    let out = tmp.path().join("site");
    let checker = create_checker(std::slice::from_ref(&r), &[]);
    let anchors = resolve_anchors_with(&checker, |_url| {
        Ok("<h2>Setup &amp; Boot</h2><a href=\"#21-setup--boot\"></a>".to_string())
    });
    let opts = PublishOptions {
        root: r.clone(),
        context_root: Vec::new(),
        public_skill: Vec::new(),
        source_commit: vec![format!(
            "{}=1111111111111111111111111111111111111111",
            r.display()
        )],
        tool_commit: "2222222222222222222222222222222222222222".to_string(),
        require_verified: None,
        out: out.clone(),
        fetch_anchors: false,
    };
    let expected = publish::payloads(&checker, &opts, Some(&anchors)).unwrap();
    fs::create_dir_all(&out).unwrap();
    for (name, text) in expected {
        fs::write(out.join(name), text).unwrap();
    }
    publish::check(&checker, &opts).unwrap();
    let index_html = fs::read_to_string(out.join("index.html")).unwrap();
    assert!(index_html.contains("#21-setup--boot"));
}
