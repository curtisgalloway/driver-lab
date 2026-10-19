// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Consolidated Rust library and CLI dispatcher for `driver-lab`.

pub mod diagnostic;
pub mod index;
pub mod pdf;
pub mod sandbox;
pub mod spdx;
pub mod yaml_strict;

use clap::{Args, Parser, Subcommand, ValueEnum};
use diagnostic::{DiagnosticEnvelope, EXIT_OK, EXIT_SANDBOX_ERROR, EXIT_USAGE_ERROR};
use sandbox::ScratchResolver;
use std::io::Write;
use std::path::PathBuf;

/// Embedded git commit SHA (`DRIVER_LAB_TOOL_COMMIT`), defaulting to `"unknown"` when unset.
pub const TOOL_COMMIT: &str = match option_env!("DRIVER_LAB_TOOL_COMMIT") {
    Some(commit) if !commit.is_empty() => commit,
    _ => "unknown",
};

/// Package version from `Cargo.toml`.
pub const PKG_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Returns the formatted version string: `driver-lab <semver> (<DRIVER_LAB_TOOL_COMMIT>)` (`ENV-3`, `ENV-6`).
#[must_use]
pub fn version_string() -> String {
    format!("driver-lab {PKG_VERSION} ({TOOL_COMMIT})")
}

/// Top-level `driver-lab` CLI parser (`RUST-TOOLING-DESIGN.md` §2.3, `BF-IMX-18`).
#[derive(Debug, Clone, Parser)]
#[command(
    name = "driver-lab",
    about = "Consolidated hardware specification, verification, and evaluation tooling",
    disable_version_flag = true,
    propagate_version = false
)]
pub struct Cli {
    /// Emit structured JSON output with stable finding codes (`BF-IMX-18`).
    #[arg(long = "json", global = true)]
    pub json: bool,

    /// Explicit writable directory for lazy temporary directory allocation (`ENV-2`, `BF-IMX-18`).
    #[arg(long = "scratch-dir", value_name = "DIR", global = true)]
    pub scratch_dir: Option<PathBuf>,

    /// Forbid network operations (`git fetch`, remote HTTP retrieval) (`ENV-1`, `BF-IMX-18`).
    #[arg(long = "offline", global = true)]
    pub offline: bool,

    /// Print `driver-lab <semver> (<DRIVER_LAB_TOOL_COMMIT>)` and exit (`ENV-3`, `ENV-6`, `BF-IMX-18`).
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

/// Output format for `driver-lab render`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
pub enum RenderFormat {
    /// Deterministic Markdown view.
    Md,
    /// Offline HTML spec viewer, explorer, or interactive topology atlas.
    Html,
}

/// Subcommands for `driver-lab` (`RUST-TOOLING-DESIGN.md` §2.3).
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
    /// Campaign review sweep, contract check, index check, and stopping rules (`RT-10`).
    Campaign(CampaignArgs),
    /// Pin repository files or documents into a spec root (`AUTO-1`, `AUTO-2`).
    Resource(ResourceArgs),
    /// Merge parallel `.facts.yaml` slices into a target `.spec.yaml` (`AUTO-3`).
    Assemble(AssembleArgs),
    /// Two-phase blind and claim verification packet preparation and assembly (`AUTO-4`).
    Verify(VerifyArgs),
}

/// Arguments for `driver-lab validate`.
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

/// Arguments for `driver-lab check`.
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
    pub stubs_from: Option<PathBuf>,
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
    pub require_verified: Option<String>,
}

/// Arguments for `driver-lab resolve`.
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
}

/// Arguments for `driver-lab index`.
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

/// Arguments for `driver-lab status`.
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
}

/// Arguments for `driver-lab todo`.
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
}

/// Arguments for `driver-lab corpus`.
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
}

/// Arguments for `driver-lab render`.
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
    /// Output format (`md` or `html`).
    #[arg(long = "format", value_enum, default_value_t = RenderFormat::Md)]
    pub format: RenderFormat,
    /// Render an overlay merged with its base spec.
    #[arg(long = "merged")]
    pub merged: bool,
    /// Render a self-contained view inlining referenced context facts.
    #[arg(long = "self-contained")]
    pub self_contained: bool,
    /// Write output to `<PATH>` instead of stdout.
    #[arg(long = "out", value_name = "PATH")]
    pub out: Option<PathBuf>,
}

/// Arguments for `driver-lab show`.
#[derive(Debug, Clone, Args)]
pub struct ShowArgs {
    /// Fact reference (`#fact-id`, `spec#fact-id`, or `spec@root#fact-id`).
    pub fact_ref: String,
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
}

/// Arguments for `driver-lab inventory`.
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

/// Arguments for `driver-lab drift`.
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

/// Arguments for `driver-lab fetch`.
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
}

/// Arguments for `driver-lab stubgen`.
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

/// Arguments for `driver-lab publish`.
#[derive(Debug, Clone, Args)]
pub struct PublishArgs {
    /// Subcommand action (`build` or `check`) and arguments.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Arguments for `driver-lab pinned-file-adapter`.
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

/// Arguments for `driver-lab prose-facts`.
#[derive(Debug, Clone, Args)]
pub struct ProseFactsArgs {
    /// Paths to scan for unanchored hardware prose facts.
    pub paths: Vec<PathBuf>,
}

/// Arguments for `driver-lab license-gate`.
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

/// Arguments for `driver-lab eval`.
#[derive(Debug, Clone, Args)]
pub struct EvalArgs {
    /// Evaluation subcommand (`extract`, `build-prompt`, `grade-facts`, `grade-code`, `run`, `score`, `validate-bank`) and arguments.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Arguments for `driver-lab campaign`.
#[derive(Debug, Clone, Args)]
pub struct CampaignArgs {
    /// Campaign subcommand (`sweep`, `contract-check`, `index-check`, `stopping`) and arguments.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Arguments for `driver-lab resource`.
#[derive(Debug, Clone, Args)]
pub struct ResourceArgs {
    /// Resource subcommand (`pin-files`, `pin-doc`) and arguments.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Arguments for `driver-lab assemble`.
#[derive(Debug, Clone, Args)]
pub struct AssembleArgs {
    /// Target `.spec.yaml` file.
    pub target_spec: PathBuf,
    /// Input `.facts.yaml` slices to merge.
    #[arg(long = "from", value_name = "SLICE", required = true)]
    pub from: Vec<PathBuf>,
}

/// Arguments for `driver-lab verify`.
#[derive(Debug, Clone, Args)]
pub struct VerifyArgs {
    /// Verify subcommand (`prepare`, `submit-blind`, `assemble`) and arguments.
    #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
    pub args: Vec<String>,
}

/// Parses CLI arguments and executes `driver-lab`, writing to `stdout` and `stderr` and
/// returning the numeric exit code (`0`, `1`, `2`, or `3`).
pub fn run_from_args<I, T>(args: I, stdout: &mut dyn Write, stderr: &mut dyn Write) -> i32
where
    I: IntoIterator<Item = T>,
    T: Into<std::ffi::OsString> + Clone,
{
    let cli = match Cli::try_parse_from(args) {
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
                    let _ = write!(stderr, "{err}");
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
        let _ = writeln!(
            stderr,
            "error: a subcommand is required (pass --help for usage)"
        );
        return EXIT_USAGE_ERROR;
    };

    // Note: `ScratchResolver` is constructed lazily (`ENV-1`, `ENV-2`); zero filesystem writes occur
    // unless a subcommand explicitly requests scratch space via `scratch.ensure_dir()`.
    let scratch = cli.scratch_resolver();

    match command {
        Command::Index(idx_args) => run_index_cmd(&cli, idx_args, &scratch, stdout, stderr),
        Command::LicenseGate(gate_args) => run_license_gate_cmd(&cli, gate_args, stdout, stderr),
        other => run_stub_subcommand(&cli, other, stdout, stderr),
    }
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
