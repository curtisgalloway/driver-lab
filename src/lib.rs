// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Consolidated Rust library and CLI dispatcher for `hwspecs`.

#![allow(clippy::too_many_arguments, clippy::type_complexity)]

pub mod author;
pub mod campaign;
pub mod claimbind;
pub mod corpus;
pub mod diagnostic;
pub mod docresolve;
pub mod drift;
pub mod eval;
pub mod explorer;
pub mod git_source;
pub mod index;
pub mod inventory;
pub mod model;
pub mod pdf;
pub mod peripheral;
pub mod prosefacts;
pub mod publish;
pub mod records;
pub mod render_html;
pub mod render_md;
pub mod resolve;
pub mod sandbox;
pub mod schema;
pub mod spdx;
pub mod speccheck;
pub mod specmd;
pub mod stubgen;
pub mod topology;
pub mod verify_flow;
pub mod worklist;
pub mod yaml_strict;

use clap::{Args, Parser, Subcommand, ValueEnum};
use diagnostic::{DiagnosticEnvelope, EXIT_OK, EXIT_SANDBOX_ERROR, EXIT_USAGE_ERROR};
use sandbox::ScratchResolver;
use std::io::Write;
use std::path::PathBuf;

/// Embedded git commit SHA (`HWSPECS_TOOL_COMMIT`), defaulting to `"unknown"` when unset.
pub const TOOL_COMMIT: &str = match option_env!("HWSPECS_TOOL_COMMIT") {
    Some(commit) if !commit.is_empty() => commit,
    _ => "unknown",
};

/// Package version from `Cargo.toml`.
pub const PKG_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Returns the formatted version string: `hwspecs <semver> (<HWSPECS_TOOL_COMMIT>)` (`ENV-3`, `ENV-6`).
#[must_use]
pub fn version_string() -> String {
    format!("hwspecs {PKG_VERSION} ({TOOL_COMMIT})")
}

/// Top-level `hwspecs` CLI parser (`RUST-TOOLING-DESIGN.md` §2.3, `BF-IMX-18`).
#[derive(Debug, Clone, Parser)]
#[command(
    name = "hwspecs",
    about = "Consolidated hardware specification, verification, and evaluation tooling",
    disable_version_flag = true,
    propagate_version = false
)]
pub struct Cli {
    /// Emit structured JSON output with stable finding codes (`BF-IMX-18`).
    #[arg(long = "json", global = true)]
    pub json: bool,

    /// Write structured JSON diagnostics to `<FILE>` while keeping `stdout`/`stderr` in normal mode (`PA-2`, `ENV-1`, `ENV-2`).
    #[arg(long = "diag-out", global = true, value_name = "FILE")]
    pub diag_out: Option<PathBuf>,

    /// Explicit writable directory for lazy temporary directory allocation (`ENV-2`, `BF-IMX-18`).
    #[arg(long = "scratch-dir", value_name = "DIR", global = true)]
    pub scratch_dir: Option<PathBuf>,

    /// Forbid network operations (`git fetch`, remote HTTP retrieval) (`ENV-1`, `BF-IMX-18`).
    #[arg(long = "offline", global = true)]
    pub offline: bool,

    /// Print `hwspecs <semver> (<HWSPECS_TOOL_COMMIT>)` and exit (`ENV-3`, `ENV-6`, `BF-IMX-18`).
    #[arg(short = 'V', long = "version", global = true)]
    pub version: bool,

    /// Subcommand to execute.
    #[command(subcommand)]
    pub command: Option<Command>,
}

impl Cli {
    /// Builds a lazy [`ScratchResolver`] from `--scratch-dir` without touching the filesystem (`ENV-1`, `ENV-2`).
    #[must_use]
    pub fn scratch_resolver(&self) -> ScratchResolver {
        ScratchResolver::new(self.scratch_dir.clone())
    }
}

/// Output format for `hwspecs render`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
pub enum RenderFormat {
    /// Deterministic Markdown view.
    Md,
    /// Offline HTML spec viewer, explorer, or interactive topology atlas.
    Html,
    /// Interactive topology atlas (`atlas.py`).
    Atlas,
}

/// Subcommands for `hwspecs` (`RUST-TOOLING-DESIGN.md` §2.3).
#[derive(Debug, Clone, Subcommand)]
pub enum Command {
    /// Validate YAML 1.2 syntax and JSON Schema compliance (`RT-2`).
    Validate(ValidateArgs),
    /// Run full semantic, cross-root, citation, and markdown containment checks (`RT-3`, `RT-4`).
    Check(CheckArgs),
    /// Verify cited source repository commits/lines and document locators/hex values (`RT-6`).
    Resolve(ResolveArgs),
    /// Extract a structural section index (`.index.yaml`) for a PDF, HTML, Markdown, or wiki document (`RT-5`).
    Index(IndexArgs),
    /// Report verification freshness status across specs and facts (`RT-7`).
    Status(StatusArgs),
    /// List open `todos` and unverified facts across specs (`RT-7`).
    Todo(TodoArgs),
    /// Validate `corpus.yaml` and report document/source coverage (`RT-7`).
    Corpus(CorpusArgs),
    /// Render deterministic Markdown or HTML views (`RT-8`).
    Render(RenderArgs),
    /// Inspect a single fact record and its resolved evidence (`RT-6`).
    Show(ShowArgs),
    /// Extract C/Rust/ASM symbols and `#define`s or check differential coverage (`RT-7`).
    Inventory(InventoryArgs),
    /// Report upstream commit drift for pinned source files (`RT-7`).
    Drift(DriftArgs),
    /// Populate an auditable local cache of pinned repositories and documents (`RT-6`, `ENV-6`).
    Fetch(FetchArgs),
    /// Generate or verify domain expert skill stubs from `domains.yaml` (`RT-9`).
    Stubgen(StubgenArgs),
    /// Build or check a multi-root static publication site (`RT-9`).
    Publish(PublishArgs),
    /// Materialize pinned repository files declared in a campaign source registry (`RT-9`).
    PinnedFileAdapter(PinnedFileAdapterArgs),
    /// Scan Markdown or YAML prose for unanchored hardware register/hex facts (`RT-2`).
    ProseFacts(ProseFactsArgs),
    /// Check source SPDX license expressions or a `.facts.yaml` file against a spec root (`RT-1`).
    LicenseGate(LicenseGateArgs),
    /// Spec evaluation prompt builder, fact/code graders, and runner (`RT-10`).
    Eval(EvalArgs),
    /// Campaign review index check (`RT-10`); `sweep`, `contract-check`, `stopping` and
    /// `pinned-file-adapter` are not implemented yet.
    Campaign(CampaignArgs),
    /// Pin repository files or documents into a spec root (`AUTO-1`, `AUTO-2`).
    Resource(ResourceArgs),
    /// Merge parallel `.facts.yaml` slices into a target `.spec.yaml` (`AUTO-3`; not implemented yet).
    Assemble(AssembleArgs),
    /// Two-phase blind and claim verification packet preparation and assembly (`AUTO-4`; not
    /// implemented yet).
    Verify(VerifyArgs),
}

/// Arguments for `hwspecs validate`.
#[derive(Debug, Clone, Args)]
pub struct ValidateArgs {
    /// Target `.spec.yaml`, `.facts.yaml`, `.verify.yaml`, `corpus.yaml`, or root directories.
    pub targets: Vec<PathBuf>,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Context spec root directories (`BF-IMX-18`).
    #[arg(long = "context-root", value_name = "DIR")]
    pub context_roots: Vec<PathBuf>,
    /// Require license compatibility check.
    #[arg(long = "require-license")]
    pub require_license: bool,
}

/// Arguments for `hwspecs check`.
#[derive(Debug, Clone, Args)]
pub struct CheckArgs {
    /// Target spec files, facts files, or root directories.
    pub targets: Vec<PathBuf>,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Context spec root directories (`BF-IMX-18`).
    #[arg(long = "context-root", value_name = "DIR")]
    pub context_roots: Vec<PathBuf>,
    /// Directory containing generated domain stub `SKILL.md` files.
    #[arg(long = "stubs-from", value_name = "DIR")]
    pub stubs_from: Vec<PathBuf>,
    /// Explicit domain stub `SKILL.md` file(s) to check.
    #[arg(long = "stub", value_name = "FILE")]
    pub stubs: Vec<PathBuf>,
    /// Require every cited source repository license to be accepted by the root.
    #[arg(long = "require-license")]
    pub require_license: bool,
    /// Verification record files (`.verify.yaml`).
    #[arg(long = "verify", value_name = "FILE")]
    pub verify: Vec<PathBuf>,
    /// Fetch remote HTML/Markdown documents to verify cited `#fragment` headings.
    #[arg(long = "resolve-headings")]
    pub resolve_headings: bool,
    /// Require verification mode (`pr` or `main`).
    #[arg(long = "require-verified", value_name = "MODE")]
    #[arg(value_parser = ["pr", "main"])]
    pub require_verified: Option<String>,
    /// Public skill names for skill containment checks.
    #[arg(long = "public-skill", value_name = "SKILL")]
    pub public_skills: Vec<String>,
}

/// Arguments for `hwspecs resolve`.
#[derive(Debug, Clone, Args)]
pub struct ResolveArgs {
    /// Target spec files or root directories.
    pub targets: Vec<PathBuf>,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Context spec root directories (`BF-IMX-18`).
    #[arg(long = "context-root", value_name = "DIR")]
    pub context_roots: Vec<PathBuf>,
    /// Local repository checkout bindings (`<name>=<path>`).
    #[arg(long = "repo", value_name = "NAME=PATH")]
    pub repos: Vec<String>,
    /// Local directory containing downloaded reference documents.
    #[arg(long = "docs-dir", value_name = "DIR")]
    pub docs_dir: Option<PathBuf>,
    /// Require license compatibility check.
    #[arg(long = "require-license")]
    pub require_license: bool,
    /// Seconds per Git or PDF extraction operation (`resolve.py:--timeout`).
    #[arg(long = "timeout", value_name = "SECS", default_value_t = 300)]
    pub timeout: u64,
    /// Retained objects and output limit in MiB (`resolve.py:--limit-mb`).
    #[arg(long = "limit-mb", value_name = "MB", default_value_t = 50)]
    pub limit_mb: usize,
    /// Print `<name>\t<commit>` lines for all `resources.repos` entries in the target files (`BF-GW-23`).
    #[arg(long = "list-repos")]
    pub list_repos: bool,
    /// Report a claim hex literal that no single cited line binds to its sentence
    /// (`RES-CLAIM-HEX-UNBOUND`) as an error instead of a warning.
    #[arg(long = "strict-claims")]
    pub strict_claims: bool,
    /// Report every document citation that could not be resolved (skipped) as an error, so the
    /// command fails unless every document citation resolves. Requires `--docs-dir`.
    #[arg(long = "fail-on-skipped-documents", requires = "docs_dir")]
    pub fail_on_skipped_documents: bool,
}

/// Arguments for `hwspecs index`.
#[derive(Debug, Clone, Args)]
pub struct IndexArgs {
    /// Document identifier declared in `resources.documents`.
    pub doc_id: String,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: PathBuf,
    /// Local directory containing downloaded reference documents.
    #[arg(long = "docs-dir", value_name = "DIR")]
    pub docs_dir: PathBuf,
    /// Optional explicit output file path.
    #[arg(long = "out", value_name = "PATH")]
    pub out: Option<PathBuf>,
}

/// Arguments for `hwspecs status`.
#[derive(Debug, Clone, Args)]
pub struct StatusArgs {
    /// Target spec files or root directories.
    pub targets: Vec<PathBuf>,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Context spec root directories (`BF-IMX-18`).
    #[arg(long = "context-root", value_name = "DIR")]
    pub context_roots: Vec<PathBuf>,
    /// Require license compatibility check.
    #[arg(long = "require-license")]
    pub require_license: bool,
    /// Exit `0` even when facts are `unverified` or `needs-second-reader` (`BF-ARM-21`).
    #[arg(long = "no-fail-on-pending")]
    pub no_fail_on_pending: bool,
    /// Show only facts whose status is not `current` or that need a second reader.
    #[arg(long = "stale")]
    pub stale: bool,
    /// Restrict output to one spec id or `id@root`.
    #[arg(long = "spec", value_name = "SPEC")]
    pub spec: Option<String>,
    /// Public skill names for skill containment checks.
    #[arg(long = "public-skill", value_name = "SKILL")]
    pub public_skills: Vec<String>,
}

/// Arguments for `hwspecs todo`.
#[derive(Debug, Clone, Args)]
pub struct TodoArgs {
    /// Target spec files or root directories.
    pub targets: Vec<PathBuf>,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Context spec root directories (`BF-IMX-18`).
    #[arg(long = "context-root", value_name = "DIR")]
    pub context_roots: Vec<PathBuf>,
    /// Require license compatibility check.
    #[arg(long = "require-license")]
    pub require_license: bool,
    /// Public skill names for skill containment checks.
    #[arg(long = "public-skill", value_name = "SKILL")]
    pub public_skills: Vec<String>,
    /// Filter by todo check kind (`hardware`, `doc`, `code`, `driver`).
    #[arg(long = "check", value_name = "KIND")]
    pub check: Option<String>,
    /// Restrict output to one spec id or `id@root`.
    #[arg(long = "spec", value_name = "SPEC")]
    pub spec: Option<String>,
}

/// Arguments for `hwspecs corpus`.
#[derive(Debug, Clone, Args)]
pub struct CorpusArgs {
    /// Target root directories or `corpus.yaml` files.
    pub targets: Vec<PathBuf>,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Context spec root directories (`BF-IMX-18`).
    #[arg(long = "context-root", value_name = "DIR")]
    pub context_roots: Vec<PathBuf>,
    /// Local directory containing downloaded reference documents.
    #[arg(long = "docs-dir", value_name = "DIR")]
    pub docs_dir: Option<PathBuf>,
    /// Require license compatibility check.
    #[arg(long = "require-license")]
    pub require_license: bool,
    /// Public skill names for skill containment checks.
    #[arg(long = "public-skill", value_name = "SKILL")]
    pub public_skills: Vec<String>,
}

/// Arguments for `hwspecs render`.
#[derive(Debug, Clone, Args)]
pub struct RenderArgs {
    /// Target spec files or root directories.
    pub targets: Vec<PathBuf>,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Context spec root directories (`BF-IMX-18`).
    #[arg(long = "context-root", value_name = "DIR")]
    pub context_roots: Vec<PathBuf>,
    /// Require license compatibility check.
    #[arg(long = "require-license")]
    pub require_license: bool,
    /// Public skill names for skill containment checks.
    #[arg(long = "public-skill", value_name = "SKILL")]
    pub public_skills: Vec<String>,
    /// Restrict output to one spec id.
    #[arg(long = "spec", value_name = "ID")]
    pub spec: Option<String>,
    /// Output format (`md`, `html`, or `atlas`).
    #[arg(long = "format", value_enum, default_value_t = RenderFormat::Md)]
    pub format: RenderFormat,
    /// Render an overlay merged with its base spec.
    #[arg(long = "merged")]
    pub merged: bool,
    /// Include verification verdict and freshness status.
    #[arg(long = "with-status")]
    pub with_status: bool,
    /// Source commit (`ROOT=SHA` or bare 40-hex SHA when rendering one root).
    #[arg(long = "source-commit", value_name = "COMMIT")]
    pub source_commits: Vec<String>,
    /// Tool commit (40 lowercase hex).
    #[arg(long = "tool-commit", value_name = "SHA")]
    pub tool_commit: Option<String>,
    /// Render a self-contained view inlining referenced context facts.
    #[arg(long = "self-contained")]
    pub self_contained: bool,
    /// Write output to `<PATH>` instead of stdout.
    #[arg(long = "out", value_name = "PATH")]
    pub out: Option<PathBuf>,
}

/// Arguments for `hwspecs show`.
#[derive(Debug, Clone, Args)]
pub struct ShowArgs {
    /// Target spec files or root directories (`hwspecs show <file>...`).
    pub targets: Vec<PathBuf>,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Context spec root directories (`BF-IMX-18`).
    #[arg(long = "context-root", value_name = "DIR")]
    pub context_roots: Vec<PathBuf>,
    /// Local repository checkout bindings (`<name>=<path>`).
    #[arg(long = "repo", value_name = "NAME=PATH")]
    pub repos: Vec<String>,
    /// Local directory containing downloaded reference documents.
    #[arg(long = "docs-dir", value_name = "DIR")]
    pub docs_dir: Option<PathBuf>,
    /// Seconds per Git or PDF extraction operation (`resolve.py:--timeout`).
    #[arg(long = "timeout", value_name = "SECS", default_value_t = 300)]
    pub timeout: u64,
    /// Retained objects and output limit in MiB (`resolve.py:--limit-mb`).
    #[arg(long = "limit-mb", value_name = "MB", default_value_t = 50)]
    pub limit_mb: usize,
}

/// Arguments for `hwspecs inventory`.
#[derive(Debug, Clone, Args)]
pub struct InventoryArgs {
    /// Target `.spec.yaml` file.
    pub spec_file: PathBuf,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Local repository checkout bindings (`<name>=<path>`).
    #[arg(long = "repo", value_name = "NAME=PATH")]
    pub repos: Vec<String>,
    /// Fail if uninventoried hardware symbols remain.
    #[arg(long = "check")]
    pub check: bool,
}

/// Arguments for `hwspecs drift`.
#[derive(Debug, Clone, Args)]
pub struct DriftArgs {
    /// Target spec files or root directories.
    pub targets: Vec<PathBuf>,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Local repository checkout bindings (`<name>=<path>`).
    #[arg(long = "repo", value_name = "NAME=PATH")]
    pub repos: Vec<String>,
}

/// Arguments for `hwspecs fetch`.
#[derive(Debug, Clone, Args)]
pub struct FetchArgs {
    /// Target spec files or root directories.
    pub targets: Vec<PathBuf>,
    /// Destination cache directory.
    #[arg(long = "cache", value_name = "DIR")]
    pub cache: PathBuf,
    /// Spec root directory.
    #[arg(long = "root", value_name = "DIR")]
    pub root: Option<PathBuf>,
    /// Context spec root directories (`BF-IMX-18`).
    #[arg(long = "context-root", value_name = "DIR")]
    pub context_roots: Vec<PathBuf>,
    /// Repository specs (`id=url`).
    #[arg(long = "repo", value_name = "ID=URL")]
    pub repos: Vec<String>,
    /// Output directory for documentation artifacts.
    #[arg(long = "docs-dir", value_name = "DIR")]
    pub docs_dir: Option<PathBuf>,
}

/// Arguments for `hwspecs stubgen`.
#[derive(Debug, Clone, Args)]
pub struct StubgenArgs {
    /// Path to `domains.yaml`.
    pub domains_yaml: PathBuf,
    /// Output `skills/` directory.
    #[arg(long = "out", value_name = "SKILLS_DIR")]
    pub out: PathBuf,
    /// Check that existing stub files match generated output without writing.
    #[arg(long = "check")]
    pub check: bool,
}

/// Arguments for `hwspecs publish`.
#[derive(Debug, Clone, Args)]
pub struct PublishArgs {
    /// Subcommand action (`build` or `check`) and arguments.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Arguments for `hwspecs pinned-file-adapter`.
#[derive(Debug, Clone, Args)]
pub struct PinnedFileAdapterArgs {
    /// Path to source registry YAML file.
    #[arg(long = "registry", value_name = "YAML")]
    pub registry: PathBuf,
    /// Source entry ID within the registry.
    #[arg(long = "source-id", value_name = "ID")]
    pub source_id: String,
    /// Output directory for materialized files.
    #[arg(long = "out", value_name = "DIR")]
    pub out: PathBuf,
    /// Optional local git repository checkout path.
    #[arg(long = "repo", value_name = "PATH")]
    pub repo: Option<PathBuf>,
}

/// Arguments for `hwspecs prose-facts`.
#[derive(Debug, Clone, Args)]
pub struct ProseFactsArgs {
    /// Paths to scan for unanchored hardware prose facts.
    pub paths: Vec<PathBuf>,
}

/// Arguments for `hwspecs license-gate`.
#[derive(Debug, Clone, Args)]
pub struct LicenseGateArgs {
    /// Target spec root directory (containing `board-specs.yaml` or `.spec-root.yaml`).
    #[arg(long = "root", value_name = "DIR")]
    pub root: PathBuf,
    /// Check all repository citations in a `.facts.yaml` file against the target root.
    #[arg(long = "facts", value_name = "FILE")]
    pub facts: Option<PathBuf>,
    /// SPDX license expressions to check against the target root's `accepts` list.
    #[arg(value_name = "LICENSE")]
    pub licenses: Vec<String>,
}

/// Arguments for `hwspecs eval`.
#[derive(Debug, Clone, Args)]
pub struct EvalArgs {
    /// Evaluation subcommand (`extract`, `build-prompt`, `grade-facts`, `grade-code`, `run`, `score`, `validate-bank`) and arguments.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Arguments for `hwspecs campaign`.
#[derive(Debug, Clone, Args)]
pub struct CampaignArgs {
    /// Campaign subcommand (`sweep`, `contract-check`, `index-check`, `stopping`,
    /// `pinned-file-adapter`) and arguments.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Arguments for `hwspecs resource`.
#[derive(Debug, Clone, Args)]
pub struct ResourceArgs {
    /// Resource subcommand (`pin-files`, `pin-doc`) and arguments.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Arguments for `hwspecs assemble`.
///
/// The command is not implemented yet, so it accepts any arguments and every invocation reaches
/// the not-implemented report. The planned form is `assemble <target.spec.yaml> --from <slice>...`.
#[derive(Debug, Clone, Args)]
pub struct AssembleArgs {
    /// Arguments (ignored until the command is implemented).
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Arguments for `hwspecs verify`.
#[derive(Debug, Clone, Args)]
pub struct VerifyArgs {
    /// Verify subcommand (`prepare`, `submit-blind`, `assemble`) and arguments.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Parses CLI arguments and executes `hwspecs`, writing to `stdout` and `stderr` and
/// returning the numeric exit code (`0`, `1`, `2`, or `3`).
pub fn run_from_args<I, T>(args: I, stdout: &mut dyn Write, stderr: &mut dyn Write) -> i32
where
    I: IntoIterator<Item = T>,
    T: Into<std::ffi::OsString> + Clone,
{
    let os_args: Vec<std::ffi::OsString> = args.into_iter().map(Into::into).collect();
    let want_json = os_args.iter().skip(1).any(|a| {
        let s = a.to_string_lossy();
        s == "--json" || s.starts_with("--json=")
    });

    let cli = match Cli::try_parse_from(os_args) {
        Ok(c) => c,
        Err(err) => {
            use clap::error::ErrorKind;
            match err.kind() {
                ErrorKind::DisplayHelp => {
                    let _ = write!(stdout, "{err}");
                    return EXIT_OK;
                }
                ErrorKind::DisplayVersion => {
                    let _ = writeln!(stdout, "{}", version_string());
                    return EXIT_OK;
                }
                _ => {
                    if want_json {
                        let env = DiagnosticEnvelope::usage_error("CLI-USAGE", err.to_string())
                            .with_field("files", serde_json::json!([]));
                        let _ = writeln!(stdout, "{}", env.to_json_string());
                    } else {
                        let _ = write!(stderr, "usage error: {err}");
                    }
                    return EXIT_USAGE_ERROR;
                }
            }
        }
    };

    if cli.version {
        let _ = writeln!(stdout, "{}", version_string());
        return EXIT_OK;
    }

    let Some(ref command) = cli.command else {
        let msg = "error: a subcommand is required (pass --help for usage)";
        let env = DiagnosticEnvelope::usage_error("CLI-USAGE", msg)
            .with_field("files", serde_json::json!([]));
        let _ = diagnostic::write_diag_out(cli.diag_out.as_deref(), &env.to_json_string());
        if cli.json {
            let _ = writeln!(stdout, "{}", env.to_json_string());
        } else {
            let _ = writeln!(stderr, "usage error: {msg}");
        }
        return EXIT_USAGE_ERROR;
    };

    // Note: `ScratchResolver` is constructed lazily (`ENV-1`, `ENV-2`); zero filesystem writes occur
    // unless a subcommand explicitly requests scratch space via `scratch.ensure_dir()`.

    let scratch = cli.scratch_resolver();

    match command {
        Command::Index(idx_args) => run_index_cmd(&cli, idx_args, &scratch, stdout, stderr),
        Command::Validate(val_args) => schema::run_validate(val_args, cli.json, stdout, stderr),
        Command::ProseFacts(pf_args) => {
            prosefacts::run_prose_facts_cmd(&pf_args.paths, cli.json, stdout, stderr)
        }
        Command::LicenseGate(gate_args) => run_license_gate_cmd(&cli, gate_args, stdout, stderr),
        Command::Resource(res_args) => author::run_resource_cmd(res_args, &scratch, stdout, stderr),
        Command::Assemble(asm_args) => author::run_assemble_cmd(asm_args, &scratch, stdout, stderr),
        Command::Verify(v_args) => verify_flow::run_verify_cmd(v_args, &scratch, stdout, stderr),
        Command::Resolve(args) => resolve::run_resolve_cmd(&cli, args, &scratch, stdout, stderr),
        Command::Show(args) => resolve::run_show_cmd(&cli, args, &scratch, stdout, stderr),
        Command::Inventory(args) => {
            inventory::run_inventory_cmd(&cli, args, &scratch, stdout, stderr)
        }
        Command::Drift(args) => drift::run_drift_cmd(&cli, args, &scratch, stdout, stderr),
        Command::Fetch(args) => run_fetch_cmd(&cli, args, &scratch, stdout, stderr),
        Command::PinnedFileAdapter(args) => {
            run_pinned_file_adapter_cmd(&cli, args, &scratch, stdout, stderr)
        }
        Command::Eval(eval_args) => eval::run_eval_cmd(&cli, eval_args, stdout, stderr),
        Command::Campaign(campaign_args) => {
            campaign::run_campaign_cmd(&cli, campaign_args, stdout, stderr)
        }
        Command::Check(check_args) => speccheck::run_check_cmd(&cli, check_args, stdout, stderr),
        Command::Status(status_args) => run_status_with_diag(&cli, status_args, stdout, stderr),
        Command::Todo(todo_args) => worklist::run_todo_cmd(&cli, todo_args, stdout, stderr),
        Command::Corpus(corpus_args) => corpus::run_corpus_cmd(&cli, corpus_args, stdout, stderr),
        Command::Stubgen(stub_args) => stubgen::run_stubgen_cmd(&cli, stub_args, stdout, stderr),
        Command::Render(render_args) => {
            render_md::run_render_cmd(&cli, render_args, stdout, stderr)
        }
        Command::Publish(pub_args) => publish::run_publish_cmd(&cli, pub_args, stdout, stderr),
    }
}

fn ensure_status_json_finding_codes(raw_json: &str) -> String {
    let Ok(mut val) = serde_json::from_str::<serde_json::Value>(raw_json) else {
        return raw_json.to_string();
    };
    let mut modified = false;
    if let Some(findings) = val
        .get_mut("findings")
        .and_then(serde_json::Value::as_array_mut)
    {
        for item in findings {
            if let Some(obj) = item.as_object_mut() {
                let needs_code = obj
                    .get("code")
                    .and_then(serde_json::Value::as_str)
                    .is_none_or(str::is_empty);
                if needs_code {
                    let msg = obj
                        .get("message")
                        .and_then(serde_json::Value::as_str)
                        .unwrap_or("");
                    let code = diagnostic::classify_check_finding_code(msg);
                    obj.insert("code".to_string(), serde_json::json!(code));
                    modified = true;
                }
            }
        }
    }
    if modified {
        serde_json::to_string(&val).unwrap_or_else(|_| raw_json.trim_end().to_string())
    } else {
        raw_json.trim_end().to_string()
    }
}

fn run_status_with_diag(
    cli: &Cli,
    status_args: &StatusArgs,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    if cli.json {
        let mut json_buf = Vec::new();
        let code = worklist::run_status_cmd(cli, status_args, &mut json_buf, stderr);
        let raw = String::from_utf8_lossy(&json_buf);
        let normalized = ensure_status_json_finding_codes(&raw);
        let _ = diagnostic::write_diag_out(cli.diag_out.as_deref(), &normalized);
        let _ = writeln!(stdout, "{normalized}");
        return code;
    }

    let code = worklist::run_status_cmd(cli, status_args, stdout, stderr);
    if let Some(ref diag_path) = cli.diag_out {
        let mut json_cli = cli.clone();
        json_cli.json = true;
        json_cli.diag_out = None;
        let mut json_buf = Vec::new();
        let mut sink_err = std::io::sink();
        let _ = worklist::run_status_cmd(&json_cli, status_args, &mut json_buf, &mut sink_err);
        let raw = String::from_utf8_lossy(&json_buf);
        let normalized = ensure_status_json_finding_codes(&raw);
        let _ = diagnostic::write_diag_out(Some(diag_path.as_path()), &normalized);
    }
    code
}

fn run_license_gate_cmd(
    cli: &Cli,
    args: &LicenseGateArgs,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    if args.facts.is_some() && !args.licenses.is_empty() {
        let msg = "error: --facts checks file citations; do not also give license expressions";
        if cli.json {
            let env = DiagnosticEnvelope::usage_error("CLI-USAGE", msg)
                .with_field("subcommand", serde_json::json!("license-gate"))
                .with_field("exit_code", serde_json::json!(EXIT_USAGE_ERROR));
            let _ = writeln!(stdout, "{}", env.to_json_string());
        } else {
            let _ = writeln!(stderr, "{msg}");
        }
        return EXIT_USAGE_ERROR;
    }

    let report = if let Some(ref facts_path) = args.facts {
        spdx::gate_facts_file(&args.root, facts_path)
    } else {
        spdx::gate_licenses(&args.root, &args.licenses)
    };

    if cli.json {
        let mut env = DiagnosticEnvelope::from_findings(report.findings.clone())
            .with_field("subcommand", serde_json::json!("license-gate"))
            .with_field("exit_code", serde_json::json!(report.exit_code))
            .with_field(
                "report",
                serde_json::to_value(&report).unwrap_or(serde_json::Value::Null),
            );
        env.ok = report.ok;
        if report.exit_code == EXIT_USAGE_ERROR {
            env.error = Some("usage".to_string());
        } else if report.exit_code == EXIT_SANDBOX_ERROR {
            env.error = Some("precondition".to_string());
        }
        let _ = writeln!(stdout, "{}", env.to_json_string());
    } else {
        for line in &report.stdout_lines {
            let _ = writeln!(stdout, "{line}");
        }
        for err in &report.errors {
            let _ = writeln!(stderr, "{err}");
        }
    }

    report.exit_code
}

#[allow(dead_code)]
fn subcommand_name(cmd: &Command) -> &'static str {
    match cmd {
        Command::Validate(_) => "validate",
        Command::Check(_) => "check",
        Command::Resolve(_) => "resolve",
        Command::Index(_) => "index",
        Command::Status(_) => "status",
        Command::Todo(_) => "todo",
        Command::Corpus(_) => "corpus",
        Command::Render(_) => "render",
        Command::Show(_) => "show",
        Command::Inventory(_) => "inventory",
        Command::Drift(_) => "drift",
        Command::Fetch(_) => "fetch",
        Command::Stubgen(_) => "stubgen",
        Command::Publish(_) => "publish",
        Command::PinnedFileAdapter(_) => "pinned-file-adapter",
        Command::ProseFacts(_) => "prose-facts",
        Command::LicenseGate(_) => "license-gate",
        Command::Eval(_) => "eval",
        Command::Campaign(_) => "campaign",
        Command::Resource(_) => "resource",
        Command::Assemble(_) => "assemble",
        Command::Verify(_) => "verify",
    }
}

#[allow(dead_code)]
fn run_stub_subcommand(
    cli: &Cli,
    cmd: &Command,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let name = subcommand_name(cmd);
    let msg = format!("subcommand '{name}' is not yet wired in this build");
    if cli.json {
        let env = DiagnosticEnvelope::sandbox_error("SUBCOMMAND-UNIMPLEMENTED", &msg)
            .with_field("subcommand", serde_json::json!(name))
            .with_field("exit_code", serde_json::json!(EXIT_SANDBOX_ERROR));
        let _ = writeln!(stdout, "{}", env.to_json_string());
    } else {
        let _ = writeln!(stderr, "error: {msg}");
    }
    EXIT_SANDBOX_ERROR
}
fn run_index_cmd(
    cli: &Cli,
    args: &IndexArgs,
    scratch: &ScratchResolver,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let outcome = index::run_index_command_with_out(
        &args.doc_id,
        &args.root,
        &args.docs_dir,
        args.out.as_deref(),
        scratch,
    );
    let code = outcome.exit_code.code();
    if cli.json {
        let val = outcome.to_json_value();
        let _ = writeln!(
            stdout,
            "{}",
            serde_json::to_string_pretty(&val).unwrap_or_else(|_| val.to_string())
        );
    } else if outcome.ok {
        for line in &outcome.text {
            let _ = writeln!(stdout, "{line}");
        }
    } else {
        for line in &outcome.text {
            let _ = writeln!(stderr, "{line}");
        }
    }
    code
}
fn run_fetch_cmd(
    cli: &Cli,
    args: &FetchArgs,
    scratch: &ScratchResolver,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let outcome = git_source::run_fetch_command(
        &args.targets,
        &args.cache,
        &args.repos,
        args.docs_dir.as_deref(),
        cli.offline,
        scratch,
    );
    let code: i32 = outcome.exit_code.into();
    if cli.json {
        let val = &outcome.payload;
        let _ = writeln!(
            stdout,
            "{}",
            serde_json::to_string_pretty(val).unwrap_or_else(|_| val.to_string())
        );
    } else {
        let out: &mut dyn Write = if code == 0 { stdout } else { stderr };
        for line in &outcome.text {
            let _ = writeln!(out, "{line}");
        }
    }
    code
}

fn run_pinned_file_adapter_cmd(
    cli: &Cli,
    args: &PinnedFileAdapterArgs,
    scratch: &ScratchResolver,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    let outcome = git_source::run_pinned_file_adapter(
        &args.registry,
        &args.source_id,
        args.repo
            .as_deref()
            .unwrap_or_else(|| std::path::Path::new("")),
        None,
        Some(&args.out),
        true,
        false,
        scratch,
    );
    let code = outcome.exit_code;
    if cli.json {
        let val = &outcome.payload;
        let _ = writeln!(
            stdout,
            "{}",
            serde_json::to_string_pretty(val).unwrap_or_else(|_| val.to_string())
        );
    } else if !outcome.is_error {
        for line in &outcome.lines {
            let _ = writeln!(stdout, "{line}");
        }
    } else {
        for line in &outcome.lines {
            let _ = writeln!(stderr, "{line}");
        }
    }
    code
}
