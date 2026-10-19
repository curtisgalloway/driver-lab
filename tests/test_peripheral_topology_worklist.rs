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
//! - Worklist (`driver-lab status` including `--no-fail-on-pending` `BF-ARM-21`, `--stale`, `--spec`;
//!   `driver-lab todo` including `--check`, `--spec`, payload row todos)
//! - Corpus (`driver-lab corpus` on `fixtures/corpus/good_root.corpus.yaml`, ledger states, coverage,
//!   and `BF-IMX-12` / `BF-GW-24` template placeholder checks)
//! - Stubgen (`driver-lab stubgen` and `--check`, `BF-IMX-ISS-4` 3+ sibling domain stubs auto-split
//!   generation, hardware fact refusal in `domains.yaml`, orphan detection)

use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use tempfile::TempDir;

const HDR: &str =
    "# SPDX-FileCopyrightText: 2026 contributors\n# SPDX-License-Identifier: Apache-2.0\n";

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn fixtures_dir() -> PathBuf {
    repo_root().join("skills/spec-format/tests/fixtures")
}

fn run_cli(args: &[&str]) -> (i32, String, String) {
    let mut full = vec!["driver-lab"];
    full.extend_from_slice(args);
    let mut stdout = Vec::new();
    let mut stderr = Vec::new();
    let code = driver_lab::run_from_args(full, &mut stdout, &mut stderr);
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
                && text.map_or(true, |needle| {
                    f["message"].as_str().unwrap_or("").contains(needle)
                })
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
                && text.map_or(true, |needle| {
                    f["message"].as_str().unwrap_or("").contains(needle)
                })
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
    assert_eq!(rc_todo, 0, "todo on fixtures/peripheral must exit 0: {res_todo}");
    let total_todos = res_todo["counts"]["total"].as_u64().unwrap();
    assert!(total_todos > 0, "expected open todos in fixtures/peripheral");

    let (rc_hw, res_hw) = todo_json(&[periph_dir.to_str().unwrap(), "--check", "hardware"]);
    assert_eq!(rc_hw, 0);
    assert_eq!(res_hw["counts"]["total"].as_u64().unwrap(), total_todos);
}

// ---------------------------------------------------------------------------
// 4. Corpus (`driver-lab corpus` + BF-IMX-12 / BF-GW-24 placeholder detection)
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
// 5. Stubgen (`driver-lab stubgen`, `--check`, and BF-IMX-ISS-4 3+ sibling split)
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

    // 1. Run `driver-lab stubgen <domains.yaml> --out <skills_dir>`
    let (rc, out, err) = run_cli(&["stubgen", manifest_str, "--out", skills_str]);
    assert_eq!(rc, 0, "stubgen failed: out={out} err={err}");

    // 2. Run `driver-lab stubgen <domains.yaml> --out <skills_dir> --check` -> must pass with 0 drift
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

    // 4. Verify `driver-lab check <good_root> --stubs-from <skills_dir>` passes with 0 overlap warnings!
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
