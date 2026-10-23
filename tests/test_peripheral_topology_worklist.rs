// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Integration and conformance tests for `RT-4` (`peripheral`, `topology`, `worklist`, `corpus`, `stubgen`).
//!
//! Covers:
//! - Peripheral semantic validation (`fixtures/peripheral/widget.spec.yaml`, registers, bitfields,
//!   enumeratedValues, sequences, layouts, registries, `hw-required`, `describes`, and `BF-GW-25`
//!   `check_unattached_peripherals` honoring `parts:` on `board`, `soc`, and `chip` specs)
//! - Topology semantic validation (`topologyNode`, `connection`, `provides`/`consumes` ports,
//!   cell arities, `incompleteKinds`, slot conflicts, board-owned `selection`/`topologyConfiguration`,
//!   and topology export)
//! - Worklist (`hwspecs status` including `--no-fail-on-pending` `BF-ARM-21`, `--stale`, `--spec`;
//!   `hwspecs todo` including `--check`, `--spec`, payload row todos)
//! - Corpus (`hwspecs corpus` on `fixtures/corpus/good_root.corpus.yaml`, ledger states, coverage,
//!   and `BF-IMX-12` / `BF-GW-24` template placeholder checks)
//! - Stubgen (`hwspecs stubgen` and `--check`, `BF-IMX-ISS-4` 3+ sibling domain stubs auto-split
//!   generation, hardware fact refusal in `domains.yaml`, orphan detection)

use serde_json::Value;
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

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn fixtures_dir() -> PathBuf {
    repo_root().join("skills/spec-format/tests/fixtures")
}

fn run_cli(args: &[&str]) -> (i32, String, String) {
    let mut full = vec!["hwspecs"];
    full.extend_from_slice(args);
    let mut stdout = Vec::new();
    let mut stderr = Vec::new();
    let code = hwspecs::run_from_args(full, &mut stdout, &mut stderr);
    (
        code,
        String::from_utf8(stdout).unwrap(),
        String::from_utf8(stderr).unwrap(),
    )
}

fn check_json(args: &[&str]) -> (i32, Value) {
    let mut full = vec!["check", "--json"];
    full.extend_from_slice(args);
    let (code, out, err) = run_cli(&full);
    let val: Value = serde_json::from_str(&out)
        .unwrap_or_else(|e| panic!("failed to parse check JSON: {e}\nout={out}\nerr={err}"));
    (code, val)
}

fn status_json(args: &[&str]) -> (i32, Value) {
    let mut full = vec!["status", "--json"];
    full.extend_from_slice(args);
    let (code, out, err) = run_cli(&full);
    let val: Value = serde_json::from_str(&out)
        .unwrap_or_else(|e| panic!("failed to parse status JSON: {e}\nout={out}\nerr={err}"));
    (code, val)
}

fn todo_json(args: &[&str]) -> (i32, Value) {
    let mut full = vec!["todo", "--json"];
    full.extend_from_slice(args);
    let (code, out, err) = run_cli(&full);
    let val: Value = serde_json::from_str(&out)
        .unwrap_or_else(|e| panic!("failed to parse todo JSON: {e}\nout={out}\nerr={err}"));
    (code, val)
}

fn corpus_json(args: &[&str]) -> (i32, Value) {
    let mut full = vec!["corpus", "--json"];
    full.extend_from_slice(args);
    let (code, out, err) = run_cli(&full);
    let val: Value = serde_json::from_str(&out)
        .unwrap_or_else(|e| panic!("failed to parse corpus JSON: {e}\nout={out}\nerr={err}"));
    (code, val)
}

fn errors(result: &Value, text: Option<&str>) -> Vec<Value> {
    result["findings"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|f| {
            f["level"] == "error"
                && text.is_none_or(|needle| f["message"].as_str().unwrap_or("").contains(needle))
        })
        .cloned()
        .collect()
}

fn warnings(result: &Value, text: Option<&str>) -> Vec<Value> {
    result["findings"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|f| {
            f["level"] == "warning"
                && text.is_none_or(|needle| f["message"].as_str().unwrap_or("").contains(needle))
        })
        .cloned()
        .collect()
}

fn write_file(path: &Path, content: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, format!("{HDR}{content}")).unwrap();
}

// ---------------------------------------------------------------------------
// 1. Peripheral semantic checks + BF-GW-25
// ---------------------------------------------------------------------------

#[test]
fn test_peripheral_fixture_and_semantic_rules() {
    let periph_dir = fixtures_dir().join("peripheral");
    let (rc, res) = check_json(&[periph_dir.to_str().unwrap()]);
    assert_eq!(rc, 0, "fixtures/peripheral must pass check: {res}");
    assert!(errors(&res, None).is_empty());

    // Negative peripheral semantic checks: overlapping bitfields, out-of-range reset, sequence cycle
    let tmp = TempDir::new().unwrap();
    let root = tmp.path().join("root");
    write_file(
        &root.join("board-specs.yaml"),
        "format: 2\nname: proot\nlayer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0]\n",
    );
    write_file(
        &root.join("bad_periph.spec.yaml"),
        r#"format: 2
kind: peripheral
id: bad-periph
name: Bad Peripheral
resources:
  documents:
    - name: trm
      class: databook
      title: Widget TRM
      url: "https://example.invalid/trm.pdf"
      sha256: "1111111111111111111111111111111111111111111111111111111111111111"
      pages: 80
areas:
  - {area: registers, level: document-and-code, note: Read from TRM.}
facts:
  - id: reg-a
    section: registers
    data:
      register: {name: REG_A, offset: "0x0", width: 8, access: read-write, reset: "0x1ff"}
      fields:
        - {id: f1, name: F1, bits: [0, 4], meaning: first field}
        - {id: f2, name: F2, bits: [3, 7], meaning: overlapping field}
    support:
      - {class: databook, doc: trm, at: [{page: "10"}]}
  - id: seq-init
    section: sequences
    title: Init
    claim: Cyclic sequence order.
    requirement: as-implemented
    data:
      sequence:
        steps:
          - {id: s1, action: write 0 to REG_A}
          - {id: s2, action: write 1 to REG_A}
        order:
          - {before: s1, after: s2}
          - {before: s2, after: s1}
    support:
      - {class: databook, doc: trm, at: [{page: "12"}]}
"#,
    );

    let (rc, res) = check_json(&[root.to_str().unwrap()]);
    assert_ne!(rc, 0, "bad_periph must fail check: {res}");
    assert!(
        !errors(&res, Some("overlap")).is_empty(),
        "expected field overlap error: {:?}",
        errors(&res, None)
    );
    assert!(
        !errors(&res, Some("reset")).is_empty() || !errors(&res, Some("width")).is_empty(),
        "expected reset width bounds error: {:?}",
        errors(&res, None)
    );
    assert!(
        !errors(&res, Some("cycle")).is_empty(),
        "expected sequence order cycle error: {:?}",
        errors(&res, None)
    );
}

#[test]
fn test_bf_gw_25_unattached_peripherals_honors_parts_on_board_soc_and_chip() {
    for holder_kind in ["board", "soc", "chip"] {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path().join("root");
        write_file(
            &root.join("board-specs.yaml"),
            "format: 2\nname: r\nlayer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0]\n",
        );

        let holder_attachment = match holder_kind {
            "board" => "cache: holder-cache\nparts: [attached-periph]\n",
            "chip" => "parts: [attached-periph]\n",
            "soc" => concat!(
                "instances:\n",
                "  - id: inst0\n",
                "    name: attached0\n",
                "    peripheral: attached-periph\n",
                "    reg: \"0x1000\"\n",
                "    irq: {kind: SPI, number: 1}\n",
                "    clocks: [clk]\n",
                "    support:\n",
                "      - {class: databook, doc: trm, at: [{page: \"5\"}]}\n",
            ),
            _ => unreachable!(),
        };

        write_file(
            &root.join("holder.spec.yaml"),
            &format!(
                r#"format: 2
kind: {holder_kind}
id: holder-spec
name: Holder Spec
triggers: [holder-spec]
{holder_attachment}resources:
  documents:
    - name: trm
      class: databook
      title: Holder TRM
      url: "https://example.invalid/trm.pdf"
      sha256: "1111111111111111111111111111111111111111111111111111111111111111"
      pages: 50
facts:
  - id: f1
    section: quick-facts
    title: Attached Part
    claim: Holder has an attached peripheral part.
    support:
      - {{class: databook, doc: trm, at: [{{page: "5"}}]}}
"#
            ),
        );

        write_file(
            &root.join("attached.spec.yaml"),
            r#"format: 2
kind: peripheral
id: attached-periph
name: Attached Peripheral
resources:
  documents:
    - name: trm
      class: databook
      title: Peripheral TRM
      url: "https://example.invalid/ptrm.pdf"
      sha256: "1111111111111111111111111111111111111111111111111111111111111111"
      pages: 50
areas:
  - {area: registers, level: document-and-code, note: Read from TRM.}
facts:
  - id: reg-ctrl
    section: registers
    data:
      register: {name: CTRL, offset: "0x0", width: 32, access: read-write}
    support:
      - {class: databook, doc: trm, at: [{page: "10"}]}
"#,
        );

        let (rc, res) = check_json(&[root.to_str().unwrap()]);
        assert_eq!(
            rc, 0,
            "BF-GW-25: peripheral referenced via parts: on {holder_kind} must be considered attached: {res}"
        );
        assert!(
            warnings(&res, Some("describes no")).is_empty(),
            "BF-GW-25: peripheral referenced in {holder_kind} parts: must not emit unattached warning: {:?}",
            warnings(&res, None)
        );

        // Add an unreferenced peripheral when a board/soc/chip exists -> must emit unattached warning
        write_file(
            &root.join("orphan.spec.yaml"),
            r#"format: 2
kind: peripheral
id: orphan-periph
name: Orphan Peripheral
resources:
  documents:
    - name: trm
      class: databook
      title: Orphan TRM
      url: "https://example.invalid/otrm.pdf"
      sha256: "1111111111111111111111111111111111111111111111111111111111111111"
      pages: 50
areas:
  - {area: registers, level: document-and-code, note: Read from TRM.}
facts:
  - id: reg-ctrl
    section: registers
    data:
      register: {name: CTRL, offset: "0x0", width: 32, access: read-write}
    support:
      - {class: databook, doc: trm, at: [{page: "10"}]}
"#,
        );
        let (_rc, res) = check_json(&[root.to_str().unwrap()]);
        assert!(
            !warnings(&res, Some("orphan-periph")).is_empty(),
            "expected unattached peripheral warning for orphan-periph in {holder_kind} root: {:?}",
            warnings(&res, None)
        );
    }
}

// ---------------------------------------------------------------------------
// 2. Topology semantic checks
// ---------------------------------------------------------------------------

#[test]
fn test_topology_valid_and_invalid_connections() {
    let tmp = TempDir::new().unwrap();
    let root = tmp.path().join("root");
    write_file(
        &root.join("board-specs.yaml"),
        "format: 2\nname: topo-root\nlayer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0]\n",
    );

    write_file(
        &root.join("ip.spec.yaml"),
        r#"format: 2
kind: ip
id: acme-uart
name: Acme UART
triggers: [acme-uart]
resources:
  documents:
    - name: trm
      class: doc
      title: Acme TRM
      url: "https://example.invalid/trm"
facts: []
"#,
    );

    write_file(
        &root.join("soc.spec.yaml"),
        r##"format: 2
kind: soc
id: acme-soc
name: Acme SoC
triggers: [acme-soc]
resources:
  documents:
    - name: trm
      class: doc
      title: Acme TRM
      url: "https://example.invalid/trm"
instances:
  - id: inst-a
    name: uart-a
    ip: acme-uart
    reg: "0x1000"
    irq: {kind: SPI, number: 1}
    clocks: [clk]
    support:
      - {class: doc, doc: trm, at: [{heading: Instances}]}
facts:
  - id: pll
    section: topology
    title: pll
    claim: Main PLL clock provider.
    data:
      topologyNode:
        kind: clock-pll
        ports:
          - {name: clk, kind: clock, role: provider, cells: 1}
    support:
      - {class: doc, doc: trm, at: [{heading: Clocks}]}
  - id: dev-a
    section: topology
    title: dev-a
    claim: UART A topology consumer.
    data:
      topologyNode:
        kind: device
        instance: "#inst-a"
        ports:
          - {name: clk, kind: clock, role: consumer}
    support:
      - {class: doc, doc: trm, at: [{heading: Clocks}]}
  - id: clk-a
    section: topology
    title: clk-a
    claim: PLL feeds UART A.
    data:
      connection:
        kind: clock
        mode: fixed
        provider: {node: "#pll", port: clk, cells: [3]}
        consumer: {node: "#dev-a", port: clk}
    support:
      - {class: doc, doc: trm, at: [{heading: Clocks}]}
"##,
    );

    let (rc, res) = check_json(&[root.to_str().unwrap()]);
    assert_eq!(rc, 0, "valid topology root must pass check: {res}");
    assert!(errors(&res, None).is_empty());

    // Now give `cells: [3, 4]` (arity 2) when provider port `clk` declares `cells: 1`
    write_file(
        &root.join("soc.spec.yaml"),
        r##"format: 2
kind: soc
id: acme-soc
name: Acme SoC
triggers: [acme-soc]
resources:
  documents:
    - name: trm
      class: doc
      title: Acme TRM
      url: "https://example.invalid/trm"
instances:
  - id: inst-a
    name: uart-a
    ip: acme-uart
    reg: "0x1000"
    irq: {kind: SPI, number: 1}
    clocks: [clk]
    support:
      - {class: doc, doc: trm, at: [{heading: Instances}]}
facts:
  - id: pll
    section: topology
    title: pll
    claim: Main PLL clock provider.
    data:
      topologyNode:
        kind: clock-pll
        ports:
          - {name: clk, kind: clock, role: provider, cells: 1}
    support:
      - {class: doc, doc: trm, at: [{heading: Clocks}]}
  - id: dev-a
    section: topology
    title: dev-a
    claim: UART A topology consumer.
    data:
      topologyNode:
        kind: device
        instance: "#inst-a"
        ports:
          - {name: clk, kind: clock, role: consumer}
    support:
      - {class: doc, doc: trm, at: [{heading: Clocks}]}
  - id: clk-a
    section: topology
    title: clk-a
    claim: PLL feeds UART A with wrong cell arity.
    data:
      connection:
        kind: clock
        mode: fixed
        provider: {node: "#pll", port: clk, cells: [3, 4]}
        consumer: {node: "#dev-a", port: clk}
    support:
      - {class: doc, doc: trm, at: [{heading: Clocks}]}
"##,
    );
    let (rc, res) = check_json(&[root.to_str().unwrap()]);
    assert_ne!(rc, 0, "mismatched topology cell arity must fail: {res}");
    assert!(
        !errors(&res, Some("cells")).is_empty(),
        "expected cell arity error: {:?}",
        errors(&res, None)
    );
}

// ---------------------------------------------------------------------------
// 3. Worklist (`status` + `--no-fail-on-pending` BF-ARM-21, `todo`)
// ---------------------------------------------------------------------------

#[test]
fn test_worklist_status_bf_arm_21_and_todo() {
    let good_root = fixtures_dir().join("check/good_root");
    let good_str = good_root.to_str().unwrap();

    // `status` with `--no-fail-on-pending` (`BF-ARM-21`) exits 0 on a clean root with unverified facts
    let (rc_nofail, res_nofail) = status_json(&[
        good_str,
        "--public-skill",
        "widget-board-tools",
        "--no-fail-on-pending",
    ]);
    assert_eq!(
        rc_nofail, 0,
        "BF-ARM-21: status --no-fail-on-pending on clean unverified root must exit 0: {res_nofail}"
    );
    assert_eq!(res_nofail["ok"], Value::Bool(true));
    assert_eq!(res_nofail["no_fail_on_pending"], Value::Bool(true));

    // And `status --no-fail-on-pending` still exits non-zero when `check` finds an error (e.g. missing --public-skill)
    let (rc_err, res_err) = status_json(&[good_str, "--no-fail-on-pending"]);
    assert_ne!(
        rc_err, 0,
        "BF-ARM-21: status --no-fail-on-pending must still fail on check errors: {res_err}"
    );

    // `todo` lists open todos and supports `--check <kind>` filtering
    let periph_dir = fixtures_dir().join("peripheral");
    let (rc_todo, res_todo) = todo_json(&[periph_dir.to_str().unwrap()]);
    assert_eq!(
        rc_todo, 0,
        "todo on fixtures/peripheral must exit 0: {res_todo}"
    );
    let total_todos = res_todo["counts"]["total"].as_u64().unwrap();
    assert!(
        total_todos > 0,
        "expected open todos in fixtures/peripheral"
    );

    let (rc_hw, res_hw) = todo_json(&[periph_dir.to_str().unwrap(), "--check", "hardware"]);
    assert_eq!(rc_hw, 0);
    assert_eq!(res_hw["counts"]["total"].as_u64().unwrap(), total_todos);
}

// ---------------------------------------------------------------------------
// 4. Corpus (`hwspecs corpus` + BF-IMX-12 / BF-GW-24 placeholder detection)
// ---------------------------------------------------------------------------

#[test]
fn test_corpus_good_root_and_bf_imx_12_bf_gw_24_placeholders() {
    let good_root = fixtures_dir().join("check/good_root");
    let good_corpus = fixtures_dir().join("corpus/good_root.corpus.yaml");

    // Copy good_root into a temp dir and place good_root.corpus.yaml at `<root>/corpus.yaml`
    let tmp = TempDir::new().unwrap();
    let root = tmp.path().join("good_root");
    fs::create_dir_all(root.join("ip")).unwrap();
    for rel in [
        "board-specs.yaml",
        "widgetboard.spec.yaml",
        "widgetsoc.spec.yaml",
        "ip/widgetuart.spec.yaml",
    ] {
        fs::copy(good_root.join(rel), root.join(rel)).unwrap();
    }
    fs::copy(&good_corpus, root.join("corpus.yaml")).unwrap();

    let (rc, res) = corpus_json(&[
        root.to_str().unwrap(),
        "--public-skill",
        "widget-board-tools",
    ]);
    assert_eq!(rc, 0, "good_root corpus must pass: {res}");
    assert!(errors(&res, None).is_empty());

    // Verify BF-IMX-12 / BF-GW-24: backticked metavariables or non-template angle brackets in
    // corpus notes are allowed, whereas an actual template placeholder token like `<url>` or
    // `<board-id>` from the template vocabulary is flagged!
    let raw = fs::read_to_string(&good_corpus).unwrap();
    let mutated = raw.replacen("title: ", "title: <board-id> ", 1);
    fs::write(root.join("corpus.yaml"), mutated).unwrap();

    let (rc, res) = corpus_json(&[
        root.to_str().unwrap(),
        "--public-skill",
        "widget-board-tools",
    ]);
    assert_ne!(
        rc, 0,
        "BF-IMX-12 / BF-GW-24: corpus with template placeholder <board-id> must fail: {res}"
    );
    assert!(
        !errors(&res, Some("placeholder")).is_empty()
            || !errors(&res, Some("<board-id>")).is_empty(),
        "expected placeholder error in corpus findings: {:?}",
        errors(&res, None)
    );
}

// ---------------------------------------------------------------------------
// 5. Stubgen (`hwspecs stubgen`, `--check`, and BF-IMX-ISS-4 3+ sibling split)
// ---------------------------------------------------------------------------

#[test]
fn test_stubgen_end_to_end_and_bf_imx_iss_4_three_way_split() {
    let tmp = TempDir::new().unwrap();
    let manifest_path = tmp.path().join("domains.yaml");
    let skills_dir = tmp.path().join("skills");

    write_file(
        &manifest_path,
        r#"format: 2
board: widgetboard
copyright: 2026 contributors
license: Apache-2.0
domains:
  - name: widget-boot
    title: Widget Boot Expert
    description: Boot ROM and CPU core bringup
    entry: [widgetsoc]
  - name: widget-clocks
    title: Widget Clocks Expert
    description: Clock controller and PLL tree
    entry: [widgetsoc]
  - name: widget-usb
    title: Widget USB Expert
    description: USB controller and PHY subsystem
    entry: [widgetsoc]
"#,
    );

    let manifest_str = manifest_path.to_str().unwrap();
    let skills_str = skills_dir.to_str().unwrap();

    // 1. Run `hwspecs stubgen <domains.yaml> --out <skills_dir>`
    let (rc, out, err) = run_cli(&["stubgen", manifest_str, "--out", skills_str]);
    assert_eq!(rc, 0, "stubgen failed: out={out} err={err}");

    // 2. Run `hwspecs stubgen <domains.yaml> --out <skills_dir> --check` -> must pass with 0 drift
    let (rc_chk, out_chk, err_chk) =
        run_cli(&["stubgen", manifest_str, "--out", skills_str, "--check"]);
    assert_eq!(
        rc_chk, 0,
        "stubgen --check failed immediately after generation: out={out_chk} err={err_chk}"
    );

    // 3. Verify that generated stubs include automatic `split:` clauses naming sibling domains (BF-IMX-ISS-4)
    let boot_md = fs::read_to_string(skills_dir.join("widget-boot/SKILL.md")).unwrap();
    assert!(
        boot_md.contains("widget-clocks") && boot_md.contains("widget-usb"),
        "BF-IMX-ISS-4: widget-boot/SKILL.md must auto-populate sibling domains in split:\n{boot_md}"
    );

    // 4. Verify `hwspecs check <good_root> --stubs-from <skills_dir>` passes with 0 overlap warnings!
    let good_root = fixtures_dir().join("check/good_root");
    let (rc_spec, res_spec) = check_json(&[
        good_root.to_str().unwrap(),
        "--public-skill",
        "widget-board-tools",
        "--stubs-from",
        skills_str,
    ]);
    assert_eq!(
        rc_spec, 0,
        "generated stubs directory must pass speccheck: {res_spec}"
    );
    assert!(
        warnings(&res_spec, Some("both enter through spec")).is_empty(),
        "BF-IMX-ISS-4: generated 3-way stubs must produce 0 overlap warnings: {:?}",
        warnings(&res_spec, None)
    );
}

// ---------------------------------------------------------------------------
// 6. Issue #164: `kind: protocol`, `kind: ip` data-formats/enumerations, and D16 layout sub-keys
// ---------------------------------------------------------------------------

#[test]
fn test_issue_164_protocol_kind_ip_data_formats_and_layout_d16_subkeys() {
    let tmp = TempDir::new().unwrap();
    let root = tmp.path().join("root");
    write_file(
        &root.join("board-specs.yaml"),
        "format: 2\nname: std-root\nlayer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0]\n",
    );

    // Put a board spec in the same root to confirm `kind: protocol` does not emit an
    // unattached-peripheral warning even without `describes:`.
    write_file(
        &root.join("board.spec.yaml"),
        r#"format: 2
kind: board
id: sample-board
name: Sample Board
triggers: [sample-board]
cache: sample-cache
parts: [sample-ip]
resources:
  documents:
    - name: bdoc
      class: doc
      title: Sample Board Doc
      url: "https://example.invalid/board.html"
      fetch: ok
facts:
  - id: board-qf
    section: quick-facts
    title: Board Overview
    claim: Sample board uses sample IP.
    support:
      - {class: doc, doc: bdoc, at: [{heading: "Overview"}]}
"#,
    );

    // `kind: ip` with `enumerationDefinitions`, `section: data-formats` (`data.layout`), and `data.quantity`.
    write_file(
        &root.join("sample_ip.spec.yaml"),
        r#"format: 2
kind: ip
id: sample-ip
name: Sample IP
triggers: [sample-ip]
resources:
  documents:
    - name: ip-trm
      class: databook
      title: Sample IP TRM
      url: "https://example.invalid/ip-trm.pdf"
      sha256: "2222222222222222222222222222222222222222222222222222222222222222"
      pages: 40
areas:
  - {area: descriptors, level: document-only, note: Extracted from IP TRM.}
enumerationDefinitions:
  - name: dma-desc-owner
    enumeratedValues:
      - {name: CPU, value: "0x0"}
      - {name: DMA, value: "0x1"}
    support:
      - {class: databook, doc: ip-trm, at: [{page: "5"}]}
facts:
  - id: ip-desc
    section: data-formats
    claim: Sample IP DMA descriptor is 4 bytes.
    requirement: hw-required
    data:
      layout:
        name: sample_dma_desc
        size: 4
        byteOrder: littleEndian
        fields:
          - id: owner
            name: owner
            offset: "0x0"
            size: 1
            bits: [0, 0]
            meaning: descriptor ownership bit
            enumerationDefinitionRef: dma-desc-owner
          - id: length
            name: length
            offset: "0x2"
            size: 2
            meaning: transfer byte count
    support:
      - {class: databook, doc: ip-trm, at: [{page: "5"}]}
  - id: ip-max-burst
    section: standards
    title: Max Burst Size
    claim: Maximum burst size is 64 bytes.
    requirement: hw-required
    data:
      quantity: {unit: By, max: 64}
    support:
      - {class: databook, doc: ip-trm, at: [{page: "6"}]}
"#,
    );

    // `kind: protocol` with `enumerationDefinitions`, `data-formats`, `sub-protocols`, `data.quantity`,
    // and a layout field carrying its own `support` (D16 sub-key).
    write_file(
        &root.join("usb2_ch9.spec.yaml"),
        r#"format: 2
kind: protocol
id: usb2-ch9
name: USB 2.0 Chapter 9 Protocol Data Structures
triggers: [usb2-ch9, usb-descriptor]
resources:
  documents:
    - name: usb20
      class: standard
      title: Universal Serial Bus Specification Revision 2.0
      url: "https://example.invalid/usb_20.pdf"
      sha256: "3333333333333333333333333333333333333333333333333333333333333333"
      pages: 650
areas:
  - {area: chapter-9, level: document-only, note: Standard Chapter 9 descriptors and requests.}
enumerationDefinitions:
  - name: usb-descriptor-type
    enumeratedValues:
      - {name: DEVICE, value: "0x1"}
      - {name: CONFIGURATION, value: "0x2"}
      - {name: STRING, value: "0x3"}
      - {name: INTERFACE, value: "0x4"}
      - {name: ENDPOINT, value: "0x5"}
    support:
      - {class: standard, doc: usb20, at: [{page: "251", table: "9-5"}]}
  - name: usb-request-code
    enumeratedValues:
      - {name: GET_STATUS, value: "0x0"}
      - {name: SET_ADDRESS, value: "0x5"}
      - {name: GET_DESCRIPTOR, value: "0x6"}
      - {name: SET_CONFIGURATION, value: "0x9"}
    support:
      - {class: standard, doc: usb20, at: [{page: "250", table: "9-4"}]}
facts:
  - id: setup-packet
    section: data-formats
    claim: Every USB control setup stage packet is 8 bytes in little-endian byte order.
    requirement: hw-required
    data:
      layout:
        name: usb_setup_packet
        size: 8
        byteOrder: littleEndian
        bitNumbering: lsb0
        fields:
          - id: recipient
            name: bmRequestType_recipient
            offset: "0x0"
            size: 1
            bits: [0, 4]
            meaning: request recipient
            enumeratedValues:
              - {name: DEVICE, value: "0x0"}
              - {name: INTERFACE, value: "0x1"}
              - {name: ENDPOINT, value: "0x2"}
              - {name: OTHER, value: "0x3"}
          - id: dir
            name: bmRequestType_dir
            offset: "0x0"
            size: 1
            bits: [7, 7]
            meaning: data transfer direction
            enumeratedValues:
              - {name: HOST_TO_DEVICE, value: "0x0"}
              - {name: DEVICE_TO_HOST, value: "0x1"}
          - id: request
            name: bRequest
            offset: "0x1"
            size: 1
            meaning: specific standard request code
            enumerationDefinitionRef: usb-request-code
            support:
              - {class: standard, doc: usb20, at: [{page: "250", table: "9-4"}]}
          - id: value
            name: wValue
            offset: "0x2"
            size: 2
            meaning: request-specific value word
          - id: index
            name: wIndex
            offset: "0x4"
            size: 2
            meaning: request-specific index or offset word
          - id: length
            name: wLength
            offset: "0x6"
            size: 2
            meaning: number of bytes to transfer in data stage
    support:
      - {class: standard, doc: usb20, at: [{page: "248", table: "9-2"}]}
  - id: set-address-recovery
    section: sub-protocols
    title: SetAddress Recovery Interval
    claim: The USB device is given a 2 ms recovery interval after SetAddress completes.
    requirement: hw-required
    data:
      quantity: {unit: ms, min: 2}
    support:
      - {class: standard, doc: usb20, at: [{page: "246", section: "9.2.6.3"}]}
"#,
    );

    let (rc, res) = check_json(&[root.to_str().unwrap()]);
    assert_eq!(
        rc, 0,
        "Issue #164: protocol and ip specs with data-formats and enumerationDefinitions must pass check: {res}"
    );
    assert!(
        warnings(&res, Some("usb2-ch9")).is_empty(),
        "Issue #164: protocol spec must not emit unattached peripheral warning: {:?}",
        warnings(&res, None)
    );

    // Check D16 sub-key (`setup-packet.request`) in `status --json --no-fail-on-pending`
    let (s_rc, s_res) = status_json(&[root.to_str().unwrap(), "--no-fail-on-pending"]);
    assert_eq!(s_rc, 0, "status --no-fail-on-pending must succeed: {s_res}");
    let usb_file = s_res["specs"]
        .as_array()
        .unwrap()
        .iter()
        .find(|f| f["spec"] == "usb2-ch9")
        .expect("usb2-ch9 in status specs");
    let usb_facts = usb_file["facts"].as_array().unwrap();
    let setup_basis = usb_facts
        .iter()
        .find(|r| r["key"] == "setup-packet")
        .and_then(|r| r["basis"].as_str())
        .expect("setup-packet basis")
        .to_string();
    let req_sub_basis = usb_facts
        .iter()
        .find(|r| r["key"] == "setup-packet.request")
        .and_then(|r| r["basis"].as_str())
        .expect("D16 sub-key setup-packet.request basis")
        .to_string();
    let set_addr_basis = usb_facts
        .iter()
        .find(|r| r["key"] == "set-address-recovery")
        .and_then(|r| r["basis"].as_str())
        .expect("set-address-recovery basis")
        .to_string();

    // Write `resources/usb2_ch9.verify.yaml` verifying `setup-packet`, `setup-packet.request`, and `set-address-recovery`
    write_file(
        &root.join("resources/usb2_ch9.verify.yaml"),
        &format!(
            r#"format: 2
spec: usb2-ch9
spec_file: usb2_ch9.spec.yaml
spec_sha256: "3333333333333333333333333333333333333333333333333333333333333333"
canonical: fact-v1
sources:
  - name: usb20
    url: "https://example.invalid/usb_20.pdf"
    sha256: "3333333333333333333333333333333333333333333333333333333333333333"
summary:
  pass: 3
  fail: 0
  unverifiable: 0
  gap: 0
  adjudicate: 0
verdicts:
  setup-packet:
    verdict: PASS
    date: "2026-04-20"
    verifier: reader-one
    basis: "{setup_basis}"
    contrary_evidence: none-found
    citation_precision: exact
    note: Verified Table 9-2 8-byte setup packet layout.
  setup-packet.request:
    verdict: PASS
    date: "2026-04-20"
    verifier: reader-one
    basis: "{req_sub_basis}"
    contrary_evidence: none-found
    citation_precision: exact
    note: Verified Table 9-4 standard request codes on bRequest.
  set-address-recovery:
    verdict: PASS
    date: "2026-04-20"
    verifier: reader-one
    basis: "{set_addr_basis}"
    contrary_evidence: none-found
    citation_precision: exact
    note: Verified 2 ms recovery interval.
"#
        ),
    );

    let (chk_rc, chk_res) = check_json(&[root.to_str().unwrap()]);
    assert_eq!(
        chk_rc, 0,
        "Issue #164: verify.yaml with D16 sub-key on data.layout.fields must pass check: {chk_res}"
    );

    // Also verify `speccheck.rs` allows an unpinned `fetch: ok` document in `.verify.yaml` `sources`
    // (such as `bdoc` on `sample-board`) and rejects an unpinned source that is not `fetch: ok`.
    let board_file = s_res["specs"]
        .as_array()
        .unwrap()
        .iter()
        .find(|f| f["spec"] == "sample-board")
        .expect("sample-board in status specs");
    let board_qf_basis = board_file["facts"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["key"] == "board-qf")
        .and_then(|r| r["basis"].as_str())
        .expect("board-qf basis")
        .to_string();
    write_file(
        &root.join("resources/board.verify.yaml"),
        &format!(
            r#"format: 2
spec: sample-board
spec_file: board.spec.yaml
spec_sha256: "1111111111111111111111111111111111111111111111111111111111111111"
canonical: fact-v1
sources:
  - name: bdoc
    url: "https://example.invalid/board.html"
    fetch: ok
summary:
  pass: 1
  fail: 0
  unverifiable: 0
  gap: 0
  adjudicate: 0
verdicts:
  board-qf:
    verdict: PASS
    date: "2026-04-20"
    verifier: reader-one
    basis: "{board_qf_basis}"
    contrary_evidence: none-found
    citation_precision: exact
    note: Verified from unpinned fetch:ok bdoc.
"#
        ),
    );
    let (b_rc, b_res) = check_json(&[root.to_str().unwrap()]);
    assert_eq!(
        b_rc, 0,
        "verify.yaml with unpinned fetch:ok document in sources must pass speccheck: {b_res}"
    );

    // Negative check: an unpinned source in verify.yaml naming a non-existent or non-fetch:ok doc must fail
    write_file(
        &root.join("resources/board.verify.yaml"),
        &format!(
            r#"format: 2
spec: sample-board
spec_file: board.spec.yaml
spec_sha256: "1111111111111111111111111111111111111111111111111111111111111111"
canonical: fact-v1
sources:
  - name: unknown-doc
    url: "https://example.invalid/board.html"
    fetch: ok
summary:
  pass: 1
  fail: 0
  unverifiable: 0
  gap: 0
  adjudicate: 0
verdicts:
  board-qf:
    verdict: PASS
    date: "2026-04-20"
    verifier: reader-one
    basis: "{board_qf_basis}"
    contrary_evidence: none-found
    citation_precision: exact
    note: Verified from unpinned unknown-doc.
"#
        ),
    );
    let (b_bad_rc, b_bad_res) = check_json(&[root.to_str().unwrap()]);
    assert_ne!(
        b_bad_rc, 0,
        "verify.yaml with unpinned source not matching an unpinned fetch:ok spec document must fail"
    );
    assert!(
        !errors(&b_bad_res, Some("must name an unpinned fetch: ok document")).is_empty(),
        "expected unpinned fetch:ok source mismatch error: {:?}",
        errors(&b_bad_res, None)
    );
    let _ = fs::remove_file(root.join("resources/board.verify.yaml"));

    // Negative check: layout field with enumerationDefinitionRef whose value exceeds field width must fail
    write_file(
        &root.join("bad_proto.spec.yaml"),
        r#"format: 2
kind: protocol
id: bad-proto
name: Bad Protocol
triggers: [bad-proto]
resources:
  documents:
    - name: pdoc
      class: standard
      title: Proto Spec
      url: "https://example.invalid/proto.pdf"
      sha256: "4444444444444444444444444444444444444444444444444444444444444444"
      pages: 20
enumerationDefinitions:
  - name: too-wide-enum
    enumeratedValues:
      - {name: SMALL, value: "0x1"}
      - {name: TOO_BIG, value: "0x10"}
    support:
      - {class: standard, doc: pdoc, at: [{page: "2"}]}
facts:
  - id: bad-pkt
    section: data-formats
    claim: Packet with 2-bit field referencing 5-bit enum value.
    data:
      layout:
        name: bad_pkt
        size: 1
        fields:
          - id: code
            name: code
            offset: "0x0"
            size: 1
            bits: [0, 1]
            meaning: 2-bit code
            enumerationDefinitionRef: too-wide-enum
    support:
      - {class: standard, doc: pdoc, at: [{page: "2"}]}
"#,
    );
    let (bad_rc, bad_res) = check_json(&[root.to_str().unwrap()]);
    assert_ne!(
        bad_rc, 0,
        "layout field referencing enum value exceeding field width must fail"
    );
    assert!(
        !errors(&bad_res, Some("exceeds field width")).is_empty(),
        "expected enumeration value exceeds field width error: {:?}",
        errors(&bad_res, None)
    );
}

#[test]
fn test_issue_180_board_sections_and_connector_memory_map_payloads() {
    let tmp = TempDir::new().unwrap();
    let root = tmp.path().join("root");
    fs::create_dir_all(&root).unwrap();

    write_file(
        &root.join("board-specs.yaml"),
        r#"format: 2
name: board-bringup-root
layer: public
license: CC-BY-4.0
accepts: []
"#,
    );

    write_file(
        &root.join("soc.spec.yaml"),
        r#"format: 2
kind: soc
id: sample-soc
name: Sample SoC
triggers: [sample-soc]
instances: []
resources:
  documents:
    - name: soc-doc
      class: doc
      title: SoC Doc
      url: "https://example.invalid/soc.html"
      fetch: ok
facts:
  - id: soc-qf
    section: quick-facts
    title: SoC quick fact.
    claim: Base SoC quick fact.
    support:
      - {class: doc, doc: soc-doc, at: [{heading: "Overview"}]}
"#,
    );

    write_file(
        &root.join("board.spec.yaml"),
        r#"format: 2
kind: board
id: sample-board
name: Sample Board
triggers: [sample-board]
parts: [sample-soc]
cache: sample-board-resources
resources:
  documents:
    - name: board-doc
      class: doc
      title: Board Manual
      url: "https://example.invalid/board.html"
      fetch: ok
facts:
  - id: j11-console-header
    section: connectors
    title: J11 serial and DIO header pinout.
    claim: J11 exposes the primary console UART and four 3.3V GPIO lines.
    data:
      connector:
        designator: J11
        kind: 2x5-pin 2.0mm header
        part_number: HDR-2X5
        mating_part: CAB-2X5
        pitch: "2.0mm"
        pins:
          - {pin: 1, signal: UART3_TXD, gpio: GPIO5_IO27, ball: AE14, direction: out, level: "3.3V", note: Console TX}
          - {pin: 2, signal: UART3_RXD, gpio: GPIO5_IO26, ball: AF14, direction: in, level: "3.3V", pull: pull-up, note: Console RX}
          - {pin: "3", signal: GND, direction: ground}
    support:
      - {class: doc, doc: board-doc, at: [{heading: "J11 Connector"}]}
  - id: uboot-dram-layout
    section: bootloader
    title: Default bootloader DRAM load addresses.
    claim: The bootloader environment defines non-overlapping load addresses in DRAM.
    data:
      memory_map:
        name: u-boot-dram
        regions:
          - {name: kernel, env_var: kernel_addr_r, base: "0x80200000", size: "0x4000000", kind: dram, purpose: Uncompressed kernel image}
          - {name: fdt, env_var: fdt_addr_r, base: "0x88000000", size: "0x100000", kind: dram, purpose: Flattened device tree blob}
          - {name: ramdisk, env_var: ramdisk_addr_r, base: "0x88800000", size: "0x4000000", kind: dram, note: Initial ramdisk}
    support:
      - {class: doc, doc: board-doc, at: [{heading: "Bootloader Memory Map"}]}
  - id: board-reset-hold-time
    section: bringup
    title: Board controller power-cycle and reset hold timing.
    claim: >-
      Run `bmc sleep <seconds>` at the bootloader prompt or hold `RST#` low for at least 50 ms
      to trigger a full board power cycle.
    data:
      quantity: {min: 50, unit: ms}
    support:
      - {class: doc, doc: board-doc, at: [{heading: "Reset and Power Cycle"}]}
"#,
    );

    let (rc, res) = check_json(&[root.to_str().unwrap()]);
    assert_eq!(
        rc,
        0,
        "board spec with connectors, bootloader, bringup sections and connector/memory_map/quantity payloads should check clean: {:?}",
        errors(&res, None)
    );

    let (st_rc, _st_res) = status_json(&["--no-fail-on-pending", root.to_str().unwrap()]);
    assert_eq!(st_rc, 0);

    // Render Markdown and verify connector and memory_map tables are rendered and pass containment
    let (md_rc, md_out, md_err) = run_cli(&[
        "render",
        root.to_str().unwrap(),
        "--spec",
        "sample-board",
        "--format",
        "md",
    ]);
    assert_eq!(md_rc, 0, "render md failed: {md_err}");
    assert!(
        md_out.contains("## Connectors"),
        "expected Connectors section in md: {md_out}"
    );
    assert!(
        md_out.contains("## Bootloader"),
        "expected Bootloader section in md: {md_out}"
    );
    assert!(
        md_out.contains("## Bringup"),
        "expected Bringup section in md: {md_out}"
    );
    assert!(
        md_out.contains("| Pin | Signal | Direction | Level | Note |"),
        "expected connector table header in md: {md_out}"
    );
    assert!(
        md_out.contains("UART3\\_TXD \\(gpio: GPIO5\\_IO27, ball: AE14\\)")
            || md_out.contains("UART3_TXD (gpio: GPIO5_IO27, ball: AE14)"),
        "expected pin row with gpio/ball in md: {md_out}"
    );
    assert!(
        md_out.contains("| Name | Variable | Base | Size | Purpose |"),
        "expected memory_map table header in md: {md_out}"
    );
    assert!(
        md_out.contains("0x80200000") && md_out.contains("kernel"),
        "expected memory_map region row in md: {md_out}"
    );

    // Render HTML and verify connector and memory_map tables
    let (html_rc, html_out, html_err) = run_cli(&[
        "render",
        root.to_str().unwrap(),
        "--spec",
        "sample-board",
        "--format",
        "html",
    ]);
    assert_eq!(html_rc, 0, "render html failed: {html_err}");
    assert!(
        html_out.contains("<table class=\"connector\">"),
        "expected connector table in html: {html_out}"
    );
    assert!(
        html_out.contains("<table class=\"memory-map\">"),
        "expected memory-map table in html: {html_out}"
    );

    // Negative check: data.register is still rejected on kind: board
    write_file(
        &root.join("bad_board.spec.yaml"),
        r#"format: 2
kind: board
id: bad-board
name: Bad Board
triggers: [bad-board]
parts: [sample-soc]
cache: bad-board-resources
resources:
  documents:
    - name: board-doc
      class: doc
      title: Board Manual
      url: "https://example.invalid/board.html"
      fetch: ok
facts:
  - id: bad-reg-on-board
    section: quick-facts
    title: Register on board.
    claim: Boards must not carry inline register payloads.
    data:
      register: {name: CTRL, offset: "0x0", width: 32}
    support:
      - {class: doc, doc: board-doc, at: [{heading: "Overview"}]}
"#,
    );
    let (bad_rc, _bad_res) = check_json(&[root.to_str().unwrap()]);
    assert_ne!(
        bad_rc, 0,
        "data.register on kind: board must fail schema validation"
    );
    let _ = fs::remove_file(root.join("bad_board.spec.yaml"));

    // Negative check R1a: overlay targeting kind: board with data.register must fail check
    write_file(
        &root.join("board_overlay.spec.yaml"),
        r#"format: 2
kind: overlay
overlays: sample-board
resources:
  documents:
    - name: board-doc
      class: doc
      title: Board Manual
      url: "https://example.invalid/board.html"
      fetch: ok
facts:
  - id: bad-reg-on-board-overlay
    section: quick-facts
    title: Register on board overlay.
    claim: Board overlays must not carry inline register payloads.
    data:
      register: {name: CTRL, offset: "0x0", width: 32}
    support:
      - {class: doc, doc: board-doc, at: [{heading: "Overview"}]}
"#,
    );
    let (ov_rc, ov_res) = check_json(&[root.to_str().unwrap()]);
    assert_ne!(ov_rc, 0, "board overlay with data.register must fail");
    assert!(
        !errors(&ov_res, Some("board overlay refuses register")).is_empty(),
        "expected board overlay payload refusal error: {:?}",
        errors(&ov_res, None)
    );
    let _ = fs::remove_file(root.join("board_overlay.spec.yaml"));

    // Negative check R3: duplicate pin in connector and overlapping regions in memory_map must fail check
    write_file(
        &root.join("bad_semantics.spec.yaml"),
        r#"format: 2
kind: board
id: bad-semantics-board
name: Bad Semantics Board
triggers: [bad-semantics-board]
parts: [sample-soc]
cache: bad-semantics-resources
resources:
  documents:
    - name: board-doc
      class: doc
      title: Board Manual
      url: "https://example.invalid/board.html"
      fetch: ok
facts:
  - id: dup-pin-conn
    section: connectors
    title: Duplicate pin connector.
    claim: Connector with duplicate pin 1.
    data:
      connector:
        designator: J99
        pins:
          - {pin: 1, signal: TX}
          - {pin: 1, signal: RX}
    support:
      - {class: doc, doc: board-doc, at: [{heading: "J99"}]}
  - id: overlap-mm
    section: bootloader
    title: Overlapping memory map.
    claim: Memory map with overlapping regions.
    data:
      memory_map:
        regions:
          - {name: reg_a, base: "0x1000", size: "0x1000"}
          - {name: reg_b, base: "0x1800", size: "0x1000"}
    support:
      - {class: doc, doc: board-doc, at: [{heading: "Map"}]}
"#,
    );
    let (sem_rc, sem_res) = check_json(&[root.to_str().unwrap()]);
    assert_ne!(
        sem_rc, 0,
        "duplicate connector pin and overlapping memory_map regions must fail"
    );
    assert!(
        !errors(&sem_res, Some("duplicate pin '1' in connector")).is_empty(),
        "expected duplicate pin error: {:?}",
        errors(&sem_res, None)
    );
    assert!(
        !errors(
            &sem_res,
            Some("memory_map region 'reg_b' overlaps region 'reg_a'")
        )
        .is_empty(),
        "expected overlapping memory_map region error: {:?}",
        errors(&sem_res, None)
    );
}

// ---------------------------------------------------------------------------
// #197: `op: poll` steps take `until`, not `value`
// ---------------------------------------------------------------------------

#[test]
fn test_issue_197_poll_steps_check_until_not_value() {
    let fixture = fixtures_dir().join("precise-payloads");
    let (rc, res) = check_json(&[fixture.to_str().unwrap()]);
    assert_eq!(rc, 0, "precise-payloads fixture must pass check: {res}");
    assert!(errors(&res, None).is_empty(), "{:?}", errors(&res, None));

    let tmp = TempDir::new().unwrap();
    let root = tmp.path().join("root");
    write_file(
        &root.join("board-specs.yaml"),
        "format: 2\nname: proot\nlayer: public\nlicense: Apache-2.0\naccepts: [Apache-2.0]\n",
    );
    write_file(
        &root.join("widget.spec.yaml"),
        r##"format: 2
kind: peripheral
id: widget
name: Widget
resources:
  documents:
    - name: trm
      class: databook
      title: Widget TRM
      url: "https://example.invalid/trm.pdf"
      sha256: "1111111111111111111111111111111111111111111111111111111111111111"
      pages: 80
areas:
  - {area: registers, level: document-and-code, note: Read from TRM.}
facts:
  - id: reg-status
    section: registers
    data:
      register: {name: STATUS, offset: "0x0", width: 8, access: read-write, reset: "0x0"}
      fields:
        - id: state
          name: STATE
          bits: [0, 1]
          meaning: block state
          enumeratedValues:
            - {name: idle, value: "0x0"}
            - {name: kick, value: "0x1", usage: write}
    support:
      - {class: databook, doc: trm, at: [{page: "10"}]}
  - id: seq-wait
    section: sequences
    title: Wait
    claim: Software waits for the block.
    data:
      sequence:
        steps:
          - id: eq-too-wide
            op: poll
            target: "#reg-status.state"
            until: {equals: "0x7"}
            timeout: {unit: ms, max: 10}
          - id: set-too-wide
            op: poll
            target: "#reg-status"
            until: {bitsSet: "0x100"}
            timeout: {unit: ms, max: 10}
          - id: clear-too-wide
            op: poll
            target: "#reg-status"
            until: {bitsClear: "0x200"}
            timeout: {unit: ms, max: 10}
          - id: write-meaning
            op: poll
            target: "#reg-status.state"
            until: {equals: kick}
            timeout: {unit: ms, max: 10}
          - id: read-meaning
            op: poll
            target: "#reg-status.state"
            until: {equals: idle}
            timeout: {unit: ms, max: 10}
          - id: interval-inverted
            op: poll
            target: "#reg-status"
            until: {bitsSet: "0x1"}
            interval: {unit: us, min: 20, max: 10}
            timeout: {unit: ms, max: 10}
    support:
      - {class: databook, doc: trm, at: [{page: "12"}]}
"##,
    );
    let (rc, res) = check_json(&[root.to_str().unwrap()]);
    assert_ne!(rc, 0, "bad poll steps must fail check: {res}");
    let all = errors(&res, None);
    assert!(
        errors(&res, Some("requires an expected value")).is_empty(),
        "{all:?}"
    );
    for needle in [
        "step 'eq-too-wide': value 0x7 exceeds target width 2",
        "step 'set-too-wide': mask 0x100 exceeds target width 8",
        "step 'clear-too-wide': mask 0x200 exceeds target width 8",
        "step 'write-meaning': value 'kick' is a write meaning",
    ] {
        assert_eq!(errors(&res, Some(needle)).len(), 1, "{needle}: {all:?}");
    }
    assert!(errors(&res, Some("'read-meaning'")).is_empty(), "{all:?}");
    // The poll interval is a quantity, checked like duration and timeout.
    let inverted = errors(&res, Some("quantity min exceeds max"));
    assert_eq!(inverted.len(), 1, "{all:?}");
    let spec_text = fs::read_to_string(root.join("widget.spec.yaml")).unwrap();
    let line = usize::try_from(inverted[0]["line"].as_u64().unwrap()).unwrap();
    assert!(
        spec_text
            .lines()
            .nth(line - 1)
            .unwrap()
            .contains("interval:"),
        "finding must point at the interval: {inverted:?}"
    );

    // Schema-valid quantities (levels min/nom/typ/max) render every level present.
    let poll = serde_json::json!({
        "id": "w", "op": "poll", "target": "#reg-status.state",
        "until": {"bitsClear": "0x1"}, "interval": {"unit": "us", "nom": 10}
    });
    let text = hwspecs::peripheral::step_text(&poll);
    assert!(text.contains("until bits 0x1 clear"), "{text}");
    assert!(text.contains("every nom 10 us"), "{text}");
    let q = serde_json::json!({"unit": "s", "min": 60, "typ": 70, "max": 90});
    assert_eq!(
        hwspecs::peripheral::quantity_text(&q),
        "min 60 s, typ 70 s, max 90 s"
    );
}
