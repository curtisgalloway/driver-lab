use clap::{Parser, Subcommand, Args};
use std::path::PathBuf;

#[derive(Debug, Parser)]
pub struct CampaignSubcommands {
    #[command(subcommand)]
    pub command: CampaignCommand,
}

#[derive(Debug, Subcommand)]
pub enum CampaignCommand {
    Sweep(SweepArgs),
    ContractCheck(ContractCheckArgs),
    IndexCheck(IndexCheckArgs),
    Stopping(StoppingArgs),
    PinnedFileAdapter(PinnedFileAdapterArgs),
}

#[derive(Debug, Clone, Args)]
pub struct SweepArgs {
    pub campaign: Option<PathBuf>,
    #[arg(long)]
    pub root: Option<PathBuf>,
    #[arg(long)]
    pub json: bool,
}

#[derive(Debug, Clone, Args)]
pub struct ContractCheckArgs {
    pub campaign: Option<PathBuf>,
    #[arg(long)]
    pub root: Option<PathBuf>,
    #[arg(long)]
    pub config: Option<PathBuf>,
    #[arg(long)]
    pub target_spec: Option<PathBuf>,
    #[arg(long)]
    pub json: bool,
}

#[derive(Debug, Clone, Args)]
pub struct IndexCheckArgs {
    pub campaign: Option<PathBuf>,
    #[arg(long)]
    pub root: Option<PathBuf>,
    #[arg(long)]
    pub json: bool,
}

#[derive(Debug, Clone, Args)]
pub struct StoppingArgs {
    pub campaign: Option<PathBuf>,
    #[arg(long)]
    pub root: Option<PathBuf>,
    #[arg(long)]
    pub json: bool,
}

#[derive(Debug, Clone, Args)]
pub struct PinnedFileAdapterArgs {
    pub registry: Option<PathBuf>,
    pub id: Option<String>,
    #[arg(long)]
    pub root: Option<PathBuf>,
    #[arg(long)]
    pub run_store: Option<PathBuf>,
    #[arg(long)]
    pub json: bool,
    #[arg(long)]
    pub write: bool,
    #[arg(long)]
    pub dry_run: bool,
}
