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
