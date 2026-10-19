// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Integration tests for `RT-0c` and `RT-1`:
//! - `yaml_strict`: strict YAML 1.2 Core Schema loader, line/col marks, NFC & character checks,
//!   and 10,661-entry `.index.yaml` load under 200 ms (`BF-IMX-11`).
//! - `spdx`: SPDX 2.3 parser, compatibility checker, `LicenseRef-*` rejection in public roots
//!   (`BF-IMX-ISS-5`), source header scanner, copyright attribution scanner/comparator,
//!   `ATTRIBUTION.md` generator/checker, and `license-gate`.
//! - `sandbox`: lazy scratch resolver (`ENV-1`, `ENV-2`), bounded subprocess pipe runner (`ENV-1`),
//!   and RAII atomic file writer (`ENV-3`).
//! - `diagnostic` & CLI: `--version` (`ENV-3`, `ENV-6`), global flag placement before and after
//!   subcommands (`BF-IMX-18`), and exit codes `0`/`1`/`2`/`3`.

use driver_lab::diagnostic::{ExitCode, Finding, Level};
use driver_lab::sandbox::{run_bounded, AtomicFileWriter, PipeLimits, ScratchResolver};
use driver_lab::spdx::{self, AttributionEvidence, AttributionStatus, SpdxExpr};
use driver_lab::yaml_strict::{self, Mark, PathSegment};
use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Instant;
use tempfile::TempDir;

// ===========================================================================
// 1. Strict YAML 1.2 Loader (`yaml_strict`)
// ===========================================================================

#[test]
fn test_yaml_failing_pitfalls_with_line_and_column() {
    let cases: &[(&str, &[u8], usize, usize, &str)] = &[
        // Anchors, aliases, merge keys
        ("anchor", b"a: &x 1\nb: 2\n", 1, 4, "an anchor (&x)"),
        ("anchor on a mapping", b"a: &x {b: 1}\n", 1, 4, "an anchor"),
        ("alias", b"a: 1\nb: *x\n", 2, 4, "alias"),
        ("anchor and alias", b"a: &x 1\nb: *x\n", 1, 4, "an anchor"),
        ("merge key", b"a: 1\n<<: {b: 2}\n", 2, 1, "a merge key"),
        ("quoted merge key", b"\"<<\": {b: 2}\n", 1, 1, "a merge key"),
        // Explicit tags & directives
        (
            "python tag",
            b"a: !!python/object:os.system x\n",
            1,
            4,
            "an explicit tag",
        ),
        ("custom tag", b"a: !custom x\n", 1, 4, "an explicit tag"),
        ("str tag", b"a: !!str 1\n", 1, 4, "an explicit tag"),
        ("non-specific tag", b"a: ! 1\n", 1, 4, "an explicit tag"),
        (
            "tag on a sequence",
            b"a: !!seq [1]\n",
            1,
            4,
            "an explicit tag",
        ),
        ("directive", b"%YAML 1.1\n---\na: 1\n", 1, 1, "directive"),
        (
            "tag directive",
            b"%TAG !e! tag:example.com,2000:\n---\na: 1\n",
            1,
            1,
            "directive",
        ),
        (
            "reserved directive",
            b"%FOO bar\n---\na: 1\n",
            1,
            1,
            "a %FOO directive",
        ),
        // Multi-doc & empty files
        (
            "two documents",
            b"a: 1\n---\nb: 2\n",
            2,
            1,
            "more than one YAML document",
        ),
        (
            "two documents both marked",
            b"---\na: 1\n...\n---\nb: 2\n",
            4,
            1,
            "more than one",
        ),
        ("empty file", b"", 1, 1, "an empty file"),
        ("comments only", b"# nothing\n", 1, 1, "an empty file"),
        // Duplicate keys
        (
            "duplicate key",
            b"a: 1\nb: 2\na: 3\n",
            3,
            1,
            "a duplicate key: a",
        ),
        (
            "duplicate key quoted and plain",
            b"a: 1\n\"a\": 2\n",
            2,
            1,
            "a duplicate key: a",
        ),
        (
            "duplicate nested key",
            b"a:\n  b: 1\n  b: 2\n",
            3,
            3,
            "a duplicate key: b",
        ),
        // Non-string & complex keys
        ("integer key", b"1: x\n", 1, 1, "a non-string key (1)"),
        ("boolean key", b"true: y\n", 1, 1, "a non-string key (true)"),
        ("null key", b"null: y\n", 1, 1, "a non-string key (null)"),
        ("empty key", b": y\n", 1, 1, ""),
        (
            "sequence key",
            b"? [a, b]\n: y\n",
            1,
            3,
            "a mapping or list used as a key",
        ),
        (
            "mapping key",
            b"? {a: 1}\n: y\n",
            1,
            3,
            "a mapping or list used as a key",
        ),
        // Empty values
        ("empty value", b"a:\nb: 1\n", 1, 3, "an empty value"),
        (
            "empty list item",
            b"a:\n  -\n  - x\n",
            2,
            4,
            "an empty value",
        ),
        ("empty flow value", b"a: {b: }\n", 1, 7, "an empty value"),
        // Invisible & control chars, NFC
        ("zero-width space", b"a: x\xe2\x80\x8by\n", 1, 5, "U+200B"),
        (
            "zero-width space escaped",
            b"a: \"x\\u200by\"\n",
            1,
            4,
            "U+200B",
        ),
        (
            "bidirectional override",
            b"a: ab\xe2\x80\xaecd\n",
            1,
            6,
            "U+202E",
        ),
        (
            "bidirectional isolate",
            b"a: ab\xe2\x81\xa6cd\n",
            1,
            6,
            "U+2066",
        ),
        ("word joiner", b"a: ab\xe2\x81\xa0cd\n", 1, 6, "U+2060"),
        (
            "BOM inside a value",
            b"a: ab\xef\xbb\xbfcd\n",
            1,
            6,
            "U+FEFF",
        ),
        ("soft hyphen", b"a: ab\xc2\xadcd\n", 1, 6, "U+00AD"),
        ("no-break space", b"a: ab\xc2\xa0cd\n", 1, 6, "U+00A0"),
        (
            "line separator escaped",
            b"a: \"ab\\Lcd\"\n",
            1,
            4,
            "U+2028",
        ),
        (
            "paragraph separator escaped",
            b"a: \"ab\\Pcd\"\n",
            1,
            4,
            "U+2029",
        ),
        (
            "line separator in quoted value",
            b"a: \"ab\xe2\x80\xa8cd\"\n",
            1,
            7,
            "U+2028",
        ),
        ("private use", b"a: ab\xee\x80\x80cd\n", 1, 6, "U+E000"),
        ("tab in a value", b"a: 'ab\tcd'\n", 1, 7, "U+0009"),
        ("tab in a block scalar", b"a: |\n  ab\tcd\n", 2, 5, "U+0009"),
        ("escaped NUL", b"a: \"x\\0y\"\n", 1, 4, "U+0000"),
        ("escaped C0", b"a: \"x\\x01y\"\n", 1, 4, "U+0001"),
        ("escaped CR", b"a: \"x\\ry\"\n", 1, 4, "U+000D"),
        ("escaped DEL", b"a: \"x\\x7fy\"\n", 1, 4, "U+007F"),
        ("escaped C1", b"a: \"x\\x85y\"\n", 1, 4, "U+0085"),
        ("raw control in file", b"a: x\x01y\n", 1, 5, "U+0001"),
        ("raw control in comment", b"a: 1 # x\x02\n", 1, 9, "U+0002"),
        ("invisible key", b"a\xe2\x80\x8b: 1\n", 1, 2, "U+200B"),
        ("not NFC", b"a: \"e\xcc\x81\"\n", 1, 4, "not in Unicode NFC"),
        ("not NFC key", b"e\xcc\x81: 1\n", 1, 1, "not in Unicode NFC"),
        // Lone CR & NEL
        (
            "lone CR in quoted value",
            b"a: \"x\ry\"\n",
            1,
            6,
            "a lone CR",
        ),
        (
            "lone CR in block scalar",
            b"a: |\n  x\ry\n",
            2,
            4,
            "a lone CR",
        ),
        ("CR line endings", b"a: x\rb: y\r", 1, 5, "a lone CR"),
        (
            "NEL in quoted value",
            b"a: \"x\xc2\x85  y\"\n",
            1,
            6,
            "U+0085",
        ),
        (
            "NEL in block scalar",
            b"a: |\n  x\xc2\x85y\n",
            2,
            4,
            "U+0085",
        ),
        ("NEL as line ending", b"a: x\xc2\x85b: y\n", 1, 5, "U+0085"),
        // Default-ignorable & blank Braille
        (
            "combining grapheme joiner",
            b"a: OSC_FREQ\xcd\x8f\n",
            1,
            12,
            "U+034F",
        ),
        ("variation selector", b"a: x\xef\xb8\x8fy\n", 1, 5, "U+FE0F"),
        ("Hangul filler", b"a: x\xe3\x85\xa4y\n", 1, 5, "U+3164"),
        (
            "Hangul choseong filler",
            b"a: x\xe1\x85\x9fy\n",
            1,
            5,
            "U+115F",
        ),
        ("Mongolian selector", b"a: x\xe1\xa0\x8by\n", 1, 5, "U+180B"),
        (
            "blank Braille pattern",
            b"a: x\xe2\xa0\x80y\n",
            1,
            5,
            "U+2800",
        ),
        ("tag character", b"a: x\xf3\xa0\x80\x81y\n", 1, 5, "U+E0001"),
        (
            "escaped grapheme joiner",
            b"a: \"x\\u034fy\"\n",
            1,
            4,
            "U+034F",
        ),
        (
            "escaped supplementary variation selector",
            b"a: \"x\\U000e0100y\"\n",
            1,
            4,
            "U+E0100",
        ),
        // Invisible characters in comments & CRLF positions
        (
            "zero-width space in comment",
            b"a: 1 # x\xe2\x80\x8by\n",
            1,
            9,
            "U+200B",
        ),
        (
            "bidi override in comment",
            b"# \xe2\x80\xaeabc\na: 1\n",
            1,
            3,
            "U+202E",
        ),
        (
            "CRLF second line",
            b"a: x\r\nb: y\xe2\x80\x8bz\r\n",
            2,
            5,
            "U+200B",
        ),
        (
            "after two-byte character",
            b"a: \xc3\xa9\xe2\x80\x8b\n",
            1,
            5,
            "U+200B",
        ),
        // Malformed scalars & 64-bit integer range
        (
            "escape beyond Unicode",
            b"a: \"\\U00110000\"\n",
            1,
            7,
            "a malformed scalar",
        ),
        (
            "20-digit integer",
            b"a: 12345678901234567890\n",
            1,
            4,
            "64-bit",
        ),
        (
            "just past 64 bits",
            b"a: 9223372036854775808\n",
            1,
            4,
            "64-bit",
        ),
        (
            "just below -64 bits",
            b"a: -9223372036854775809\n",
            1,
            4,
            "64-bit",
        ),
        // BOMs & invalid UTF-8
        (
            "UTF-8 BOM",
            b"\xef\xbb\xbfa: 1\n",
            1,
            1,
            "a byte-order mark",
        ),
        (
            "UTF-16 BOM",
            b"\xff\xfea\x00:\x00 \x001\x00\n\x00",
            1,
            1,
            "a byte-order mark",
        ),
        ("Latin-1 byte", b"a: 1\nb: caf\xe9\n", 2, 7, "not UTF-8"),
        (
            "bad byte after two-byte char",
            b"a: \"\xc3\xa9\xff\"\n",
            1,
            6,
            "not UTF-8",
        ),
        ("truncated sequence", b"a: \xe2\x80\n", 1, 4, "not UTF-8"),
        ("overlong encoding", b"a: \xc0\xaf\n", 1, 4, "not UTF-8"),
        ("surrogate escape", b"a: \"\\ud800\"\n", 1, 4, "U+D800"),
        // Syntax errors
        ("bad indentation", b"a:\n  b: 1\n c: 2\n", 3, 2, ""),
        ("unclosed flow", b"a: [1, 2\n", 2, 1, ""),
    ];

    let tmp = TempDir::new().unwrap();
    for &(label, raw, expected_line, expected_col, expected_substr) in cases {
        let filename = format!("{}.yaml", label.replace([' ', ','], "-"));
        let path = tmp.path().join(filename);
        fs::write(&path, raw).unwrap();
        let loaded = yaml_strict::load_file(&path);
        assert!(
            !loaded.ok(),
            "case '{label}' unexpectedly succeeded: {:?}",
            loaded.data
        );
        let err = &loaded.errors[0];
        assert!(
            err.message.contains(expected_substr),
            "case '{label}': expected message containing {expected_substr:?}, got {:?}",
            err.message
        );
        assert_eq!(
            (err.line, err.column),
            (expected_line, expected_col),
            "case '{label}': wrong (line, col) in error: {err}"
        );
        assert!(
            err.to_string().starts_with(&format!(
                "{}:{expected_line}:{expected_col}: ",
                path.display()
            )),
            "case '{label}': unexpected Display format: {err}"
        );
    }

    // Also test a huge integer & deep nesting
    let huge_int = [b"a: ".as_slice(), &vec![b'9'; 4400], b"\n"].concat();
    let huge_path = tmp.path().join("huge-int.yaml");
    fs::write(&huge_path, &huge_int).unwrap();
    let huge_loaded = yaml_strict::load_file(&huge_path);
    assert!(!huge_loaded.ok());
    assert_eq!(
        (huge_loaded.errors[0].line, huge_loaded.errors[0].column),
        (1, 4)
    );
    assert!(huge_loaded.errors[0].message.contains("64-bit"));

    let deep_yaml = [
        b"a: ".as_slice(),
        &vec![b'['; 5000],
        &vec![b']'; 5000],
        b"\n",
    ]
    .concat();
    let deep_path = tmp.path().join("deep-nesting.yaml");
    fs::write(&deep_path, &deep_yaml).unwrap();
    let deep_loaded = yaml_strict::load_file(&deep_path);
    assert!(!deep_loaded.ok());
    assert_eq!(
        (deep_loaded.errors[0].line, deep_loaded.errors[0].column),
        (1, 1)
    );
    assert!(deep_loaded.errors[0].message.contains("nesting too deep"));
}

#[test]
fn test_yaml_scalar_resolution_and_core_schema_rules() {
    let text = concat!(
        "a: [no, yes, on, off, NO, YES, ON, OFF, y, n, True, FALSE, Null, NULL, ~]\n",
        "b: [08, 012, 0o12, 0x7E20_1000, 1_000, +1, -0, 1e3, .inf, .nan, 1.10, 1:20, 12:34]\n",
        "c: [2026-10-08, 2026-10-08T12:00:00Z]\n",
        "d: [true, false, null, 0, 7, -7, 0x10, 9223372036854775807, -9223372036854775808]\n",
        "e: ['true', \"null\", '7', '0x10']\n",
        "f: |\n  7\n",
    );
    let loaded = yaml_strict::load_text(text, Path::new("x.yaml"));
    assert!(loaded.ok(), "{:?}", loaded.errors);
    let data = loaded.data.unwrap();

    assert_eq!(
        data["a"],
        json!([
            "no", "yes", "on", "off", "NO", "YES", "ON", "OFF", "y", "n", "True", "FALSE", "Null",
            "NULL", "~"
        ])
    );
    assert_eq!(
        data["b"],
        json!([
            "08",
            "012",
            "0o12",
            "0x7E20_1000",
            "1_000",
            "+1",
            "-0",
            "1e3",
            ".inf",
            ".nan",
            "1.10",
            "1:20",
            "12:34"
        ])
    );
    assert_eq!(data["c"], json!(["2026-10-08", "2026-10-08T12:00:00Z"]));
    assert_eq!(
        data["d"],
        json!([
            true,
            false,
            null,
            0,
            7,
            -7,
            16,
            9_223_372_036_854_775_807_i64,
            -9_223_372_036_854_775_808_i64
        ])
    );
    assert_eq!(data["e"], json!(["true", "null", "7", "0x10"]));
    assert_eq!(data["f"], json!("7\n"));

    // Block scalars stay strings
    let block = yaml_strict::load_text(
        "a: |-\n  true\nb: >-\n  7\nc: |-\n  null\n",
        Path::new("block.yaml"),
    );
    assert!(block.ok());
    assert_eq!(
        block.data.unwrap(),
        json!({"a": "true", "b": "7", "c": "null"})
    );

    // Tab in comment & CRLF line endings allowed
    let crlf = yaml_strict::load_text(
        "a: 1 # a\ttab in a comment\r\nb: 2\r\n",
        Path::new("crlf.yaml"),
    );
    assert!(crlf.ok());
    assert_eq!(crlf.data.unwrap(), json!({"a": 1, "b": 2}));

    // Keys that look like YAML 1.1 booleans are strings when plain words
    let keys = yaml_strict::load_text("no: 1\non: 2\nyes: 3\n'1': 4\n", Path::new("keys.yaml"));
    assert!(keys.ok());
    let obj = keys.data.unwrap();
    let key_names: Vec<&str> = obj
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(key_names, vec!["no", "on", "yes", "1"]);
}

#[test]
fn test_yaml_marks_on_values_and_keys() {
    let loaded = yaml_strict::load_text("a:\n  - b: 1\n    c: [x, y]\n", Path::new("marks.yaml"));
    assert!(loaded.ok());
    assert_eq!(
        loaded.mark(
            &[
                PathSegment::from("a"),
                PathSegment::from(0usize),
                PathSegment::from("c"),
                PathSegment::from(1usize)
            ],
            None
        ),
        Mark::new(3, 12)
    );
    assert_eq!(
        loaded.mark(
            &[PathSegment::from("a"), PathSegment::from(0usize)],
            Some("c")
        ),
        Mark::new(3, 5)
    );
    assert_eq!(
        loaded.mark(
            &[
                PathSegment::from("a"),
                PathSegment::from(0usize),
                PathSegment::from("missing")
            ],
            None
        ),
        Mark::new(2, 5)
    );
}

#[test]
fn test_yaml_10661_entry_index_loads_under_200ms_bf_imx_11() {
    // Construct a synthetic 10,661-entry `.index.yaml` (~117,000 YAML nodes, exceeding the
    // 100,000-node default cap while fitting within the 500,000-node `.index.yaml` cap).
    let mut yaml = String::with_capacity(1_500_000);
    yaml.push_str("format: 2\ndocument: imx95-rm\nsha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\npages: 4500\nsections:\n");
    for i in 1..=10_661 {
        use std::fmt::Write;
        let _ = writeln!(
            yaml,
            "  - number: \"1.{i}\"\n    title: \"Section {i} Register Description\"\n    level: 2\n    start_page: {i}\n    end_page: {}",
            i + 1
        );
    }

    // Verify that default spec limits (100,000 nodes) reject it, whereas `.index.yaml` limits accept it.
    let rejected = yaml_strict::load_text(&yaml, Path::new("imx95-rm.spec.yaml"));
    assert!(!rejected.ok());
    assert_eq!(rejected.errors[0].code, "YAML-NODE-LIMIT");

    let start = Instant::now();
    let loaded = yaml_strict::load_text(&yaml, Path::new("imx95-rm.index.yaml"));
    let elapsed = start.elapsed();

    assert!(loaded.ok(), "index load failed: {:?}", loaded.errors);
    let sections = loaded.data.unwrap()["sections"].as_array().unwrap().len();
    assert_eq!(sections, 10_661);
    assert!(
        elapsed.as_millis() < 200,
        "BF-IMX-11: expected 10,661-entry .index.yaml load in < 200 ms, took {} ms",
        elapsed.as_millis()
    );
}

// ===========================================================================
// 2. SPDX 2.3 Parser, Attribution, and License Gate (`spdx`)
// ===========================================================================

const GPL_ROOT: &[&str] = &[
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "Apache-2.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
];
const PERMISSIVE_ROOT: &[&str] = &["Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause"];
const DOCS_ROOT: &[&str] = &[];

#[test]
fn test_spdx_normalized_forms_and_errors() {
    let valid_cases = [
        ("MIT", "MIT"),
        ("mit", "MIT"),
        ("GPL-2.0", "GPL-2.0-only"),
        ("GPL-2.0+", "GPL-2.0-or-later"),
        ("GPL-2.0-only+", "GPL-2.0-or-later"),
        ("GPL-2.0-or-later", "GPL-2.0-or-later"),
        ("LGPL-2.1+", "LGPL-2.1-or-later"),
        ("Apache-2.0+", "Apache-2.0+"),
        ("GPL-2.0 OR MIT", "GPL-2.0-only OR MIT"),
        ("(GPL-2.0+ OR MIT)", "GPL-2.0-or-later OR MIT"),
        (
            "GPL-2.0 WITH Linux-syscall-note",
            "GPL-2.0-only WITH Linux-syscall-note",
        ),
        (
            "MIT AND BSD-3-Clause OR ISC",
            "(MIT AND BSD-3-Clause) OR ISC",
        ),
        (
            "MIT AND (BSD-3-Clause OR ISC)",
            "MIT AND (BSD-3-Clause OR ISC)",
        ),
        ("LicenseRef-vendor-blob", "LicenseRef-vendor-blob"),
        ("DocumentRef-x:LicenseRef-y", "DocumentRef-x:LicenseRef-y"),
        ("  BSD-3-Clause  ", "BSD-3-Clause"),
    ];
    for (input, expected) in valid_cases {
        let parsed = spdx::parse(input).unwrap_or_else(|e| panic!("failed on {input:?}: {e}"));
        assert_eq!(parsed.to_string(), expected, "input: {input:?}");
    }
    let nested_32 = format!("{}MIT{}", "(".repeat(32), ")".repeat(32));
    assert_eq!(spdx::parse(&nested_32).unwrap().to_string(), "MIT");

    let error_cases = [
        ("", "empty license expression"),
        ("mainline", "unknown SPDX license identifier 'mainline'"),
        ("GPL-2", "unknown SPDX license identifier 'GPL-2'"),
        ("GPL-2.0 or MIT", "write the operator in uppercase (OR)"),
        (
            "MIT OR",
            "expression ends where a license identifier was expected",
        ),
        ("OR MIT", "'OR' where a license identifier was expected"),
        ("(MIT OR ISC", "unbalanced parenthesis: '(' without ')'"),
        ("MIT OR ISC)", "unbalanced parenthesis: ')' without '('"),
        ("MIT ISC", "unexpected 'ISC' after a complete expression"),
        (
            "GPL-2.0 WITH",
            "WITH must be followed by an exception identifier",
        ),
        (
            "GPL-2.0 WITH no-such-exception",
            "unknown SPDX exception identifier",
        ),
        (
            "(MIT) WITH Linux-syscall-note",
            "WITH must follow a single license identifier",
        ),
        ("+", "is not a license identifier"),
        (
            "(MIT and ISC)",
            "'and': write the operator in uppercase (AND)",
        ),
        ("(MIT ISC)", "unexpected 'ISC' after a complete expression"),
    ];
    for (input, fragment) in error_cases {
        let err = spdx::parse(input).expect_err(&format!("expected error on {input:?}"));
        assert!(
            err.message().contains(fragment),
            "for {input:?}, expected {fragment:?} in {:?}",
            err.message()
        );
    }
    let nested_200 = format!("{}MIT{}", "(".repeat(200), ")".repeat(200));
    let deep_err = spdx::parse(&nested_200).unwrap_err();
    assert!(deep_err
        .message()
        .contains("parentheses nested more than 32 deep"));

    assert_eq!(spdx::parse_identifier("GPL-2.0").unwrap(), "GPL-2.0-only");
    assert_eq!(spdx::parse_identifier("0BSD").unwrap(), "0BSD");
    for compound in ["MIT OR ISC", "GPL-2.0 WITH Linux-syscall-note"] {
        let err = spdx::parse_identifier(compound).unwrap_err();
        assert!(err
            .message()
            .contains("an accepts list holds single license identifiers"));
    }
}

#[test]
fn test_spdx_acceptance_table_and_public_licenseref_rejection_bf_imx_iss_5() {
    let table = [
        ("GPL-2.0-only", true, false, false),
        ("GPL-2.0", true, false, false),
        ("GPL-2.0+", true, false, false),
        ("GPL-2.0 OR MIT", true, true, false),
        ("(GPL-2.0+ OR MIT)", true, true, false),
        ("GPL-2.0-only AND MIT", true, false, false),
        ("MIT AND BSD-3-Clause", true, true, false),
        ("GPL-2.0 WITH Linux-syscall-note", true, false, false),
        ("BSD-3-Clause", true, true, false),
        ("GPL-3.0-only", false, false, false),
        ("GPL-3.0-only OR MIT", true, true, false),
        ("LicenseRef-vendor-blob", false, false, false),
        ("Apache-2.0+", false, false, false),
    ];
    for (expr, gpl, perm, docs) in table {
        assert_eq!(spdx::check(expr, GPL_ROOT).unwrap(), gpl, "GPL: {expr}");
        assert_eq!(
            spdx::check(expr, PERMISSIVE_ROOT).unwrap(),
            perm,
            "PERMISSIVE: {expr}"
        );
        assert_eq!(spdx::check(expr, DOCS_ROOT).unwrap(), docs, "DOCS: {expr}");
    }

    assert!(!spdx::check("GPL-2.0-or-later", &["GPL-2.0-only"]).unwrap());
    assert!(!spdx::check("GPL-2.0+", &["GPL-2.0-only"]).unwrap());
    assert!(!spdx::check("GPL-2.0-only", &["GPL-2.0-or-later"]).unwrap());
    assert!(spdx::check("GPL-2.0+", &["GPL-2.0-or-later"]).unwrap());

    // BF-IMX-ISS-5: `licenseref-*` / `LicenseRef-*` / `DocumentRef-*` rejected in public roots
    let err = spdx::check_for_layer(
        "LicenseRef-nxp-proprietary OR MIT",
        PERMISSIVE_ROOT,
        "public",
    )
    .unwrap_err();
    assert!(err.message().contains("not permitted in a public root"));

    let err_accepts = spdx::check_for_layer("MIT", &["LicenseRef-custom"], "public").unwrap_err();
    assert!(err_accepts
        .message()
        .contains("not permitted in a public root"));

    // Allowed in private roots when listed in `accepts`
    assert!(spdx::check_for_layer("LicenseRef-custom", &["LicenseRef-custom"], "private").unwrap());
}

#[test]
fn test_spdx_header_scanner_and_attribution() {
    let src = "/*\n * SPDX-FileCopyrightText: 2026 Example Inc.\n * SPDX-License-Identifier: (GPL-2.0-only OR MIT)\n */\nint main(void) { return 0; }\n";
    let hdr = spdx::scan_spdx_header(src).unwrap().unwrap();
    assert_eq!(hdr.line, 3);
    assert_eq!(
        hdr.expr,
        SpdxExpr::Or(
            Box::new(SpdxExpr::License("GPL-2.0-only".to_string())),
            Box::new(SpdxExpr::License("MIT".to_string()))
        )
    );

    let attr = spdx::scan_attribution(src);
    assert_eq!(attr.status, AttributionStatus::Recorded);
    assert_eq!(attr.names, vec!["Example Inc."]);
    assert_eq!(
        attr.evidence,
        vec![AttributionEvidence {
            line: 2,
            text: "SPDX-FileCopyrightText: 2026 Example Inc.".to_string()
        }]
    );

    // Mid-line notice -> ambiguous
    let mid = spdx::scan_attribution_lines(&[" * Portions Copyright (C) 2001 Foo"]);
    assert_eq!(mid.status, AttributionStatus::Ambiguous);
    assert!(mid.names.is_empty());
    assert_eq!(mid.evidence.len(), 1);

    // BSD boilerplate -> none-found
    let bsd = spdx::scan_attribution_lines(&[
        " * Redistributions of source code must retain the above copyright",
        " * IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE",
    ]);
    assert_eq!(bsd.status, AttributionStatus::NoneFound);

    // Summary & cell formatting
    let summary = spdx::attribution_summary(&[Some(attr.clone()), Some(bsd.clone()), None], false);
    assert_eq!(
        summary.as_deref(),
        Some("Example Inc.; attribution incomplete (1 unrecorded, 1 no notice found)")
    );
    assert_eq!(
        spdx::attribution_cell(Some(&attr)),
        "recorded: Example Inc."
    );
    assert_eq!(spdx::attribution_cell(Some(&bsd)), "no notice found");
    assert_eq!(spdx::attribution_cell(None), "");

    // Deterministic ATTRIBUTION.md generation & check
    let spec_val = json!({
        "id": "widget",
        "resources": {
            "repos": [{
                "name": "linux",
                "url": "https://example.invalid/linux.git",
                "commit": "0123456789abcdef0123456789abcdef01234567",
                "license": "GPL-2.0-only",
                "files": [{
                    "path": "drivers/widget.c",
                    "license_from": "spdx-line",
                    "attribution": attr.to_schema_value()
                }]
            }]
        }
    });
    let md = spdx::generate_attribution_md(std::slice::from_ref(&spec_val));
    assert!(md.contains("recorded: Example Inc."));
    assert!(spdx::check_attribution_md(&md, std::slice::from_ref(&spec_val)).is_ok());
}

#[test]
fn test_license_gate_all_cases_and_bf_imx_iss_5() {
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let roots_dir = repo_root.join("skills/hardware-investigator/examples/roots");
    let permissive = roots_dir.join("permissive");
    let gpl = roots_dir.join("gpl");

    // 1. Root alone prints accepts list and exits 0
    let mut out = Vec::new();
    let mut err = Vec::new();
    let rc = driver_lab::run_from_args(
        [
            "driver-lab",
            "license-gate",
            "--root",
            permissive.to_str().unwrap(),
        ],
        &mut out,
        &mut err,
    );
    let out_str = String::from_utf8(out).unwrap();
    assert_eq!(rc, 0, "{out_str}");
    assert!(out_str.contains("accepts: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause"));
    assert!(out_str.contains("example-permissive"));

    // 2. Accepted license
    let rep = spdx::gate_licenses(&permissive, &["MIT".to_string()]);
    assert_eq!(rep.exit_code, 0);
    assert!(rep.stdout_lines.iter().any(|l| l == "accepted: MIT"));

    // 3. Refused license names reason
    let rep = spdx::gate_licenses(&permissive, &["GPL-2.0-only".to_string()]);
    assert_eq!(rep.exit_code, 1);
    let joined = rep.stdout_lines.join("\n");
    assert!(joined.contains("refused: GPL-2.0-only"));
    assert!(joined.contains("root example-permissive"));
    assert!(joined.contains("accepts: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause"));

    // 4. OR passes when one side accepted; AND needs both sides
    assert_eq!(
        spdx::gate_licenses(&permissive, &["GPL-2.0-only OR MIT".to_string()]).exit_code,
        0
    );
    assert_eq!(
        spdx::gate_licenses(&permissive, &["GPL-2.0-only AND MIT".to_string()]).exit_code,
        1
    );

    // 5. GPL family not interchangeable
    assert_eq!(
        spdx::gate_licenses(&gpl, &["GPL-2.0-or-later".to_string()]).exit_code,
        0
    );
    assert_eq!(
        spdx::gate_licenses(&permissive, &["GPL-2.0+".to_string()]).exit_code,
        1
    );

    // 6. Multiple expressions: one refusal makes exit 1, all reported
    let rep = spdx::gate_licenses(
        &permissive,
        &["MIT".to_string(), "GPL-3.0-only".to_string()],
    );
    assert_eq!(rep.exit_code, 1);
    let joined = rep.stdout_lines.join("\n");
    assert!(joined.contains("accepted: MIT"));
    assert!(joined.contains("refused: GPL-3.0-only"));

    // 7. Invalid SPDX expression refused with exit 1
    let rep = spdx::gate_licenses(&permissive, &["Totally Free License".to_string()]);
    assert_eq!(rep.exit_code, 1);
    let joined = rep.stdout_lines.join("\n");
    assert!(joined.contains("refused: Totally Free License"));
    assert!(joined.contains("not an SPDX expression"));

    // 8. BF-IMX-ISS-5: LicenseRef-* refused in public root
    let rep = spdx::gate_licenses(&permissive, &["LicenseRef-vendor-proprietary".to_string()]);
    assert_eq!(rep.exit_code, 1);
    assert!(rep
        .stdout_lines
        .join("\n")
        .contains("not permitted in public root"));

    // 9. Invalid markers never accept a license
    let valid_marker = "format: 2\nlayer: public\nname: test\nlicense: MIT\naccepts: [MIT]\n";
    let invalid_markers = [
        (
            "format missing",
            "layer: public\nname: test\nlicense: MIT\naccepts: [MIT]\n",
        ),
        (
            "format one",
            "format: 1\nlayer: public\nname: test\nlicense: MIT\naccepts: [MIT]\n",
        ),
        (
            "duplicate key",
            "format: 2\nlayer: public\nname: test\nlicense: MIT\naccepts: [MIT]\naccepts: []\n",
        ),
        (
            "noncanonical identifier",
            "format: 2\nlayer: public\nname: test\nlicense: MIT\naccepts: [GPL-2.0]\n",
        ),
        (
            "duplicate identifier",
            "format: 2\nlayer: public\nname: test\nlicense: MIT\naccepts: [MIT, MIT]\n",
        ),
        (
            "bad license",
            "format: 2\nlayer: public\nname: test\nlicense: Foo\naccepts: [MIT]\n",
        ),
        (
            "accepts expression",
            "format: 2\nlayer: public\nname: test\nlicense: MIT\naccepts: [MIT OR BSD-3-Clause]\n",
        ),
        (
            "public licenseref in accepts",
            "format: 2\nlayer: public\nname: test\nlicense: MIT\naccepts: [LicenseRef-foo]\n",
        ),
        ("not a mapping", "[]\n"),
        ("malformed YAML", "format: [\n"),
    ];
    let _ = valid_marker;
    let tmp = TempDir::new().unwrap();
    for (label, text) in invalid_markers {
        fs::write(tmp.path().join("board-specs.yaml"), text).unwrap();
        let rep = spdx::gate_licenses(tmp.path(), &["MIT".to_string()]);
        let joined = rep.stdout_lines.join("\n");
        assert_eq!(rep.exit_code, 1, "case {label}: {joined}");
        assert!(
            joined.contains("invalid spec format root marker"),
            "case {label}: {joined}"
        );
        assert!(!joined.contains("accepted: MIT"), "case {label}: {joined}");
    }

    // 10. Not a spec root -> exit 2
    let empty_dir = TempDir::new().unwrap();
    let rep = spdx::gate_licenses(empty_dir.path(), &["MIT".to_string()]);
    assert_eq!(rep.exit_code, 2);
    assert!(rep.errors[0].contains("not a spec root"));
}

// ===========================================================================
// 3. Sandbox Primitives (`sandbox`: `ENV-1`, `ENV-2`, `ENV-3`)
// ===========================================================================

#[test]
fn test_sandbox_lazy_scratch_resolver_env_1_env_2() {
    let base = TempDir::new().unwrap();
    let non_existent_scratch = base.path().join("lazy-scratch");

    // Creating a ScratchResolver performs zero filesystem writes (ENV-1).
    let resolver = ScratchResolver::new(Some(non_existent_scratch.clone()));
    assert!(!resolver.is_allocated());
    assert!(!non_existent_scratch.exists());

    // Calling ensure_dir() materializes the directory only when needed.
    let dir = resolver.ensure_dir().unwrap();
    assert!(resolver.is_allocated());
    assert!(dir.is_dir());

    // Rejects cwd and $HOME as scratch roots (ENV-2).
    let cwd = std::env::current_dir().unwrap();
    let cwd_resolver = ScratchResolver::with_tmpdir(Some(cwd), None);
    let err = cwd_resolver.ensure_dir().unwrap_err();
    assert_eq!(err.exit_code(), ExitCode::SandboxError);

    // Fails with exit 3 when neither --scratch-dir nor TMPDIR is writable.
    let unwritable = ScratchResolver::with_tmpdir(
        Some(PathBuf::from("/proc/nonexistent-driver-lab-scratch")),
        Some(PathBuf::from("/proc/nonexistent-driver-lab-tmpdir")),
    );
    let err = unwritable.ensure_dir().unwrap_err();
    assert_eq!(err.exit_code(), ExitCode::SandboxError);
    assert_eq!(err.exit_code().as_i32(), 3);
}

#[test]
fn test_sandbox_bounded_pipe_runner_env_1() {
    let mut cmd = Command::new("python3");
    cmd.args(["-c", "import sys; sys.stdout.write('hello\\n')"]);
    let out = run_bounded(&mut cmd, PipeLimits::default()).unwrap();
    assert!(out.success());
    assert_eq!(out.stdout, b"hello\n");

    // Exceeding stdout cap fails closed with exit 3 (SandboxError::OutputOverflow)
    let mut overflow_cmd = Command::new("python3");
    overflow_cmd.args(["-c", "import sys; sys.stdout.write('x' * 2048)"]);
    let limits = PipeLimits::new(1024, 1024);
    let err = run_bounded(&mut overflow_cmd, limits).unwrap_err();
    assert_eq!(err.exit_code(), ExitCode::SandboxError);
    assert_eq!(err.exit_code().as_i32(), 3);
    assert!(err
        .to_string()
        .contains("exceeded stdout limit of 1024 bytes"));
}

#[test]
fn test_sandbox_atomic_file_writer_raii() {
    let tmp = TempDir::new().unwrap();
    let dest = tmp.path().join("output.yaml");

    // Dropping without commit leaves no file behind
    {
        let mut writer = AtomicFileWriter::new(&dest).unwrap();
        writer.write_all_bytes(b"partial").unwrap();
    }
    assert!(!dest.exists());

    // Committing atomically persists the file
    {
        let mut writer = AtomicFileWriter::new(&dest).unwrap();
        writer.write_all_bytes(b"format: 2\n").unwrap();
        writer.commit().unwrap();
    }
    assert_eq!(fs::read_to_string(&dest).unwrap(), "format: 2\n");
}

// ===========================================================================
// 4. CLI Global Flag Placement (`BF-IMX-18`), `--version` (`ENV-6`), & Diagnostics
// ===========================================================================

#[test]
fn test_cli_version_and_global_flags_in_any_position_bf_imx_18() {
    // 1. Top-level `--version`
    let mut out = Vec::new();
    let mut err = Vec::new();
    let rc = driver_lab::run_from_args(["driver-lab", "--version"], &mut out, &mut err);
    assert_eq!(rc, 0);
    let ver = String::from_utf8(out).unwrap();
    assert!(
        ver.starts_with("driver-lab 0.1.0 (") && ver.trim_end().ends_with(')'),
        "unexpected version output: {ver:?}"
    );

    // 2. `--version` after a subcommand name (`BF-IMX-18`)
    let mut out = Vec::new();
    let mut err = Vec::new();
    let rc = driver_lab::run_from_args(["driver-lab", "validate", "--version"], &mut out, &mut err);
    assert_eq!(rc, 0);
    assert_eq!(String::from_utf8(out).unwrap(), ver);

    // 3. Global flags (`--json`, `--scratch-dir`, `--offline`) before AND after subcommand (`BF-IMX-18`)
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let permissive = repo_root.join("skills/hardware-investigator/examples/roots/permissive");
    let scratch_tmp = TempDir::new().unwrap();

    for args in [
        vec![
            "driver-lab",
            "--json",
            "--offline",
            "--scratch-dir",
            scratch_tmp.path().to_str().unwrap(),
            "license-gate",
            "--root",
            permissive.to_str().unwrap(),
            "MIT",
        ],
        vec![
            "driver-lab",
            "license-gate",
            "--root",
            permissive.to_str().unwrap(),
            "MIT",
            "--json",
            "--offline",
            "--scratch-dir",
            scratch_tmp.path().to_str().unwrap(),
        ],
    ] {
        let mut out = Vec::new();
        let mut err = Vec::new();
        let rc = driver_lab::run_from_args(&args, &mut out, &mut err);
        assert_eq!(
            rc,
            0,
            "args: {args:?}, stderr: {}",
            String::from_utf8_lossy(&err)
        );
        let parsed: Value = serde_json::from_slice(&out).unwrap();
        assert_eq!(parsed["ok"], json!(true));
        assert_eq!(parsed["exit_code"], json!(0));
        assert_eq!(parsed["subcommand"], json!("license-gate"));
    }

    // 4. Finding JSON serialization includes both `col` and `column`
    let f = Finding::new(
        Level::Error,
        "TEST-CODE",
        "foo.yaml",
        10,
        4,
        "sample problem",
    );
    let f_json = serde_json::to_value(&f).unwrap();
    assert_eq!(f_json["col"], json!(4));
    assert_eq!(f_json["column"], json!(4));
    assert_eq!(f_json["code"], json!("TEST-CODE"));
}
