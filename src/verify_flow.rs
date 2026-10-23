// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::diagnostic::{not_implemented, EXIT_USAGE_ERROR};
use crate::sandbox::ScratchResolver;
use crate::VerifyArgs;
use clap::Parser;
use std::io::Write;

// `hwspecs verify` subcommands. None is implemented yet: each reports
// `verify <subcommand>: not implemented` and exits non-zero.
#[derive(Debug, Parser)]
#[command(name = "verify")]
pub enum VerifyCmd {
    /// Emit a blind or claims work packet (not implemented yet).
    Prepare(UnimplementedArgs),
    /// Record a reader's blind derivations (not implemented yet).
    SubmitBlind(UnimplementedArgs),
    /// Assemble reader verdicts into a verify record (not implemented yet).
    Assemble(UnimplementedArgs),
}

/// Accepts any arguments, so every invocation of an unimplemented subcommand reaches the
/// not-implemented report instead of a usage error about flags that do nothing.
#[derive(Debug, clap::Args)]
pub struct UnimplementedArgs {
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

pub fn run_verify_cmd(
    args: &VerifyArgs,
    _scratch: &ScratchResolver,
    _stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let mut args_vec = vec!["verify".to_string()];
    args_vec.extend(args.args.clone());
    let cmd = match VerifyCmd::try_parse_from(&args_vec) {
        Ok(c) => c,
        Err(e) => {
            let _ = write!(stderr, "{}", e);
            return EXIT_USAGE_ERROR;
        }
    };
    let command = match cmd {
        VerifyCmd::Prepare(_) => "verify prepare",
        VerifyCmd::SubmitBlind(_) => "verify submit-blind",
        VerifyCmd::Assemble(_) => "verify assemble",
    };
    not_implemented(command, stderr)
}
