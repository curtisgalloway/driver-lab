use clap::{Args, Parser, Subcommand};
use std::path::PathBuf;

#[derive(Debug, Parser)]
pub struct CampaignSubcommands {
    #[command(subcommand)]
    pub command: CampaignCommand,
}

#[derive(Debug, Subcommand)]
pub enum CampaignCommand {
    /// Freshness sweep and stopping report (not implemented yet).
    Sweep(UnimplementedArgs),
    /// Plugin contract check (not implemented yet).
    ContractCheck(UnimplementedArgs),
    IndexCheck(IndexCheckArgs),
    /// Stopping-rule evaluation (not implemented yet).
    Stopping(UnimplementedArgs),
    /// Campaign source refresh (not implemented yet).
    PinnedFileAdapter(UnimplementedArgs),
}

/// Accepts any arguments, so every invocation of an unimplemented subcommand reaches the
/// not-implemented report instead of a usage error about flags that do nothing.
#[derive(Debug, Clone, Args)]
pub struct UnimplementedArgs {
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

#[derive(Debug, Clone, Args)]
pub struct IndexCheckArgs {
    pub campaign: Option<PathBuf>,
    #[arg(long)]
    pub root: Option<PathBuf>,
    #[arg(long)]
    pub json: bool,
}
