// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! `driver-lab` binary entry point.

use std::io;
use std::process;

fn main() {
    let mut stdout = io::stdout();
    let mut stderr = io::stderr();
    let code = driver_lab::run_from_args(std::env::args_os(), &mut stdout, &mut stderr);
    process::exit(code);
}
