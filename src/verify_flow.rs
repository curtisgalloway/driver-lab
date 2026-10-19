// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

use crate::VerifyArgs;
use crate::sandbox::ScratchResolver;
use crate::diagnostic::{EXIT_OK, EXIT_USAGE_ERROR};
use std::io::Write;
use clap::Parser;


#[derive(Debug, Parser)]
#[command(name = "verify")]
pub enum VerifyCmd {
    Prepare(PrepareArgs),
    SubmitBlind,
    Assemble,
}

#[derive(Debug, Parser)]
pub struct PrepareArgs {
    #[arg(long = "phase")]
    pub phase: String,
    #[arg(long = "shard")]
    pub shard: Option<String>,
    #[arg(long = "second-reader")]
    pub second_reader: bool,
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
    match cmd {
        VerifyCmd::Prepare(p) => {
            if p.phase == "blind" {
                // emit blind packet
            } else if p.phase == "claims" {
                // emit claims packet
            }
            EXIT_OK
        }
        VerifyCmd::SubmitBlind => EXIT_OK,
        VerifyCmd::Assemble => EXIT_OK,
    }
}
