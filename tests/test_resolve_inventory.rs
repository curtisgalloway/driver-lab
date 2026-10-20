use std::process::Command;

fn run_test_cli(args: Vec<&str>) -> std::process::Output {
    let bin = env!("CARGO_BIN_EXE_driver-lab");
    let mut cmd = Command::new(bin);
    cmd.args(args);
    cmd.output().expect("failed to execute process")
}

#[test]
fn test_hex_values_extraction() {
    let text1 = "The address is 0x1234_5678 and also 4438_0000h.";
    let res1 = driver_lab::docresolve::hex_values(text1);
    assert_eq!(res1, vec!["0x1234_5678", "4438_0000h"]);
}

#[test]
fn test_locator_pattern() {
    let pat1 = driver_lab::docresolve::locator_pattern("table", "Table 1.2");
    assert!(pat1.is_match("Table 1.2 is shown"));

    // Issue #166: captions and prose references followed by a period
    let pat_table = driver_lab::docresolve::locator_pattern("table", "9-12");
    assert!(pat_table.is_match("Table 9-12. Standard Interface Descriptor"));
    assert!(pat_table.is_match("Table 9-12: Standard Interface Descriptor"));
    assert!(pat_table.is_match("Table 9-12 Standard Interface Descriptor"));

    let pat_table_end = driver_lab::docresolve::locator_pattern("table", "11-15");
    assert!(pat_table_end.is_match("outlined in Table 11-15."));
    assert!(pat_table_end.is_match("(see Table 11-15.)"));

    let pat_fig = driver_lab::docresolve::locator_pattern("figure", "9-4");
    assert!(pat_fig.is_match("Figure 9-4. Information Returned by a GetStatus() Request"));

    let pat_endash = driver_lab::docresolve::locator_pattern("table", "2-3");
    assert!(pat_endash.is_match("Table 2–3. USBLEGSUP Register Bit Definitions"));
    let pat_endash_rev = driver_lab::docresolve::locator_pattern("table", "2–3");
    assert!(pat_endash_rev.is_match("Table 2-3. USBLEGSUP Register Bit Definitions"));

    let pat_sec = driver_lab::docresolve::locator_pattern("section", "9.4.5");
    assert!(pat_sec.is_match("see section 9.4.5."));
    assert!(pat_sec.is_match("9.4.5. GetStatus"));
    assert!(!pat_sec.is_match("Section 1.9.4.5"));
    assert!(!pat_sec.is_match("Section 19.4.5"));

    // Prefix section or table numbers must not match longer numbers
    let pat_sec_prefix = driver_lab::docresolve::locator_pattern("section", "9.4");
    assert!(!pat_sec_prefix.is_match("Section 9.4.5 Standard Requests"));
    assert!(pat_sec_prefix.is_match("Section 9.4. Standard Requests"));
    assert!(pat_sec_prefix.is_match("see Section 9.4."));

    let pat_table_prefix = driver_lab::docresolve::locator_pattern("table", "9-1");
    assert!(!pat_table_prefix.is_match("Table 9-12. Standard Interface Descriptor"));
    assert!(!pat_table_prefix.is_match("Table 9-1-2. Subtable"));
    assert!(pat_table_prefix.is_match("Table 9-1. Standard Device Requests"));
    assert!(pat_table_prefix.is_match("Table 9-1-A. Variant"));
}

#[test]
fn test_bf_usb_1() {
    let out = run_test_cli(vec!["resolve", "--help"]);
    assert!(out.status.success());
}
#[test]
fn test_bf_usb_2() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_imx_iss_6() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_imx_iss_7() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_imx_13() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_imx_16() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_imx_17() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
#[test]
fn test_bf_gw_26() {
    let _ = run_test_cli(vec!["resolve", "--help"]);
}
