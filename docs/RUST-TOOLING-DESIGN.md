<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Consolidated Rust tooling (`driver-lab`): design

## Terms

- **`driver-lab` CLI**: the single compiled Rust binary replacing the active Python scripts under
  `skills/`.
- **Zero-write read set**: subcommands that perform no filesystem writes (not even under
  `TMPDIR`, `/tmp`, or `$HOME`) and require no network access when repositories are locally bound.
- **Tool commit (`DRIVER_LAB_TOOL_COMMIT`)**: the git commit embedded in `driver-lab --version` at
  build time via `option_env!("DRIVER_LAB_TOOL_COMMIT")` and checked by sandbox wrappers,
  `patch-gate.py`, and CI.
- **Conformance corpus**: language-neutral test cases (`tests/conformance/`) mapping input spec/doc
  trees to expected `--json` output (`ok`, `level`, `code`, `path`, `line`) with stable finding
  codes.
- **Spec, fact record, fact reference, root-qualified reference, support entry, basis hash,
  rendered view, atlas** — see [SPEC-FORMAT.md](SPEC-FORMAT.md#terms),
  [ATLAS-CONNECTIONS-DESIGN.md](ATLAS-CONNECTIONS-DESIGN.md#terms), and the
  [glossary](../GLOSSARY.md).

Design revision: 2026-10-19 (user approved 2026-10-19 following Claude Opus 5.5 consultation).
Companion implementation plan: [RUST-TOOLING-PLAN.md](RUST-TOOLING-PLAN.md). Bug traceability
source: [BUGS-FOUND.md](../BUGS-FOUND.md).

---

## 1. Problem, scope, and non-goals

### 1.1 Problem

`driver-lab` currently distributes 40 active Python implementation files (15,017 lines) and 58
Python test files (23,709 lines) across six skill directories (`spec-format`, `board-expert`,
`board-spec-scaffold`, `hardware-investigator`, `spec-eval`, and `campaign-review`), alongside 12
host utility and test files in `utilities/` (3,291 lines) and 14 frozen evaluation archive files in
`evals/` (7,614 lines). This layout has produced three classes of defects:

1. **Cross-skill coupling and duplicated parsers**:
   - Because scripts are split across six skill directories without an installable package, they
     reach across skill boundaries by mutating `sys.path` (`stubgen.py:49`, `license_gate.py:89`,
     `publish.py:14`) or dynamically loading files by relative path via
     `importlib.util.spec_from_file_location` (`speccheck.py:111` loading `board-expert/scripts/spdx.py`,
     `pinned_file_adapter.py:48` loading `evals/enc28j60/corpus_check.py`,
     `utilities/check-no-hardware-facts.py:38` loading `spec-format/scripts/prosefacts.py`, and
     `evals/enc28j60/score.py:26` loading `board-expert/scripts/strict_accept.py`).
   - YAML loading is implemented separately in `skills/spec-format/scripts/specload.py` (which
     composes PyYAML's pure-Python `Reader`, `Scanner`, `Parser`, `Composer`, and `BaseResolver`
     at lines 153–166), `skills/campaign-review/scripts/index_check.py` (`UniqueLoader(yaml.SafeLoader)`
     at line 1074, which uses YAML 1.1 rules rather than YAML 1.2), and
     `skills/spec-format/scripts/drift.py` (`yaml.scan`/`yaml.compose` with `yaml.BaseLoader` at
     lines 89 and 183).
   - Git object and checkout plumbing is split between `skills/spec-format/scripts/resolve.py` and
     `skills/campaign-review/scripts/pinned_file_adapter.py`.
2. **Virtualenv and sandbox friction across isolated subagent environments**:
   - Every worktree and CI job must provision `.venv-spec` with `--require-hashes` before running
     `spec.py`.
   - Pure-Python YAML composition in `specload.py` eagerly parses all `<root>/index/*.index.yaml`
     files on every CLI invocation (`BUGS-FOUND.md` #11).
   - Eager `tempfile` creation in `resolve.py`, `docresolve.py`, `inventory.py`, and `drift.py`
     causes `spec.py` to fail inside `codex-review.py ro` (`--sandbox read-only`) and
     `codex-review.py net` (`exclude_slash_tmp=true`, `exclude_tmpdir_env_var=true`).
3. **31 corpus authoring, indexing, resolution, schema, and CI bugs** accumulated in
   [BUGS-FOUND.md](../BUGS-FOUND.md) across `hardware-specs-usb` (4 entries),
   `hardware-specs-imx95` (18 entries: `Issue 1`–`Issue 7` and `8`–`18`), `hardware-specs-arm`
   (3 entries: `19`–`21`), and `hardware-specs-gw9200` (6 entries: `22`–`27`).

### 1.2 Intended outcome and scope

Consolidate all active skill scripts into a single compiled Rust CLI binary, `driver-lab`, built
from a root Cargo package in this repository and invoked by thin Markdown skills (following the
single-CLI + bundled-skills architecture used in `paniolo`). Because there is no external user base
and all existing `hardware-specs-*` repositories are under project control, `driver-lab` is
designed without legacy Python CLI shims; at the same time, `src/records.rs` preserves byte-for-byte
identical `fact-v1` basis hashes so existing `.verify.yaml` freshness states are preserved without
laundering stale verdicts.

**In scope:**

- Replacing `skills/spec-format/scripts/*.py`, `skills/spec-format/ci/publish.py`,
  `skills/board-expert/scripts/*.py`, `skills/board-spec-scaffold/scripts/stubgen.py`,
  `skills/hardware-investigator/scripts/*.py`, `skills/spec-eval/scripts/*.py`, and
  `skills/campaign-review/scripts/*.py` with the `driver-lab` Rust crate and CLI.
- Extracting a language-neutral conformance test corpus with stable finding codes (`RT-0a`) before
  porting checkers so every existing check, basis-hash computation, and mutation guard is verified
  against both `spec.py` and `driver-lab`.
- Resolving all 31 entries in [BUGS-FOUND.md](../BUGS-FOUND.md) (`BF-USB-1`..`BF-USB-4`,
  `BF-IMX-ISS-1`..`BF-IMX-ISS-7`, `BF-IMX-8`..`BF-IMX-18`, `BF-ARM-19`..`BF-ARM-21`,
  `BF-GW-22`..`BF-GW-27`).
- Enforcing execution contracts across all six isolated subagent environments (`ENV-1`..`ENV-6`).
- Updating `utilities/codex-implement.py`, `utilities/codex-review.py`, `utilities/patch-gate.py`,
  `utilities/check-no-hardware-facts.py`, CI templates (`skills/spec-format/ci/*`), and skill
  `SKILL.md` files.
- Post-cutover authoring and verification automation subcommands (`AUTO-1`..`AUTO-6`) and
  evidence-gated model tiering (`TIER-1`..`TIER-4`).

**Explicit non-goals (kept separate):**

- **Frozen evaluation archive (`evals/`, `evidence/`, `notebook/`, `history/`)**: per
  [AGENTS.md](../AGENTS.md) and LS-R20, the frozen archive is historical record and is not ported
  to Rust. To decouple the frozen archive from `skills/` when Python skill scripts are removed:
  - `skills/board-expert/scripts/strict_accept.py` moves to `evals/enc28j60/strict_accept.py` (the
    local path `evals/enc28j60/score.py` line 24 already checks first).
  - The `evals/e1000`-specific Python AST harness verifier (`index_check.py`) moves to
    `evals/e1000/index_check.py`, while `driver-lab campaign` implements declarative manifest
    checking for active campaigns.
  - A minimal `evals/requirements.txt` pinning `PyYAML` by hash is retained solely for the frozen
    archive's CI steps.
- **Host containment and orchestration wrappers (`utilities/*.py`)**: `codex-implement.py`,
  `codex-review.py`, `patch-gate.py`, `run-store.py`, `check-no-private-paths.py`,
  `check-open-side.py`, and `check-no-hardware-facts.py` remain zero-dependency Python 3 stdlib
  scripts so the host gate that checks patches to the Rust crate never depends on executing code
  built from the worktree under test. `utilities/check-no-hardware-facts.py` embeds its own
  50-line stdlib `prosefacts` scanner (guarded by `GATE_INPUTS`), verified against a shared fixture
  file (`tests/conformance/prosefacts.json`) that both `check-no-hardware-facts.py` and Rust
  `src/prosefacts.rs` must match.

---

## 2. Architecture and component responsibilities

### 2.1 Repository layout

```text
Cargo.toml
Cargo.lock
rust-toolchain.toml
src/
  main.rs                 # CLI parser (clap), global flags, exit-code mapping (0/1/2/3)
  lib.rs                  # Public library entry points for integration tests
  diagnostic.rs           # Stable finding codes, file:line:col spans, text and --json output
  sandbox.rs              # Lazy scratch allocation, --scratch-dir / TMPDIR, subprocess pipes
  yaml_strict.rs          # Strict YAML 1.2 loader with byte/line/col Span table & caps
  schema.rs               # Embedded JSON Schemas + structural/type validation
  spdx.rs                 # SPDX expression parser, license compatibility & attribution
  specmd.rs               # GFM/CommonMark AST checker (comrak), parse-back verifier, placeholders
  prosefacts.rs           # Register/hex prose-fact detector for stubs and domains.yaml
  model.rs                # Spec Format 2 AST: root marker, specs, payloads, topology, records
  records.rs              # Canonical fact-v1 basis hashing, freshness DAG, .verify.yaml
  speccheck.rs            # Semantic checker, cross-root overlays, peripheral attachment, stubs
  topology.rs             # Atlas connection graph validation, owner traversal, export
  git_source.rs           # Hardened git plumbing, partial-clone rejection, pinned-file adapter
  pdf.rs                  # Native PDF outline/page-label reader (lopdf + AES) & pdftotext pipe
  index.rs                # Document section indexer (PDF, ATX Markdown, HTML, Trac wiki)
  docresolve.rs           # Cited PDF/Markdown/HTML/wiki locator and hex-evidence verifier
  resolve.rs              # Source repo & document evidence resolver
  inventory.rs            # C/Rust/ASM symbol & #define extractor and differential checker
  drift.rs                # Upstream commit drift reporter
  worklist.rs             # status and todo worklist commands
  corpus.rs               # corpus.yaml validator and coverage reporter
  render_md.rs            # Deterministic Markdown renderer (--merged, --self-contained)
  render_html.rs          # Offline HTML spec viewer, explorer, and interactive topology atlas
  publish.rs              # Multi-root static site builder and link/asset verifier
  stubgen.rs              # Domain expert stub generator and --check verifier
  author.rs               # Post-cutover resource pin-files/pin-doc and fact-slice assemble
  verify_flow.rs          # Post-cutover two-phase verify prepare, submit-blind, and assemble
  eval.rs                 # Spec evaluation prompt builder, fact/code graders, bwrap runner
  campaign.rs             # Campaign sweep, contract-check, index-check, stopping rules
tests/
  conformance/            # Language-neutral conformance corpus (validated on spec.py & Rust)
```

No `build.rs` is used (`codex-implement.py` runs in a `git archive` export with no `.git`
directory, and avoiding `build.rs` eliminates build-time arbitrary code execution). Instead,
`src/main.rs` reads `option_env!("DRIVER_LAB_TOOL_COMMIT")` (defaulting to `"unknown"` when unset,
which the version handshake rejects in gated/CI runs).

### 2.2 Crate dependencies and supply-chain pinning

All crate versions are pinned upfront in a dedicated host-prepared bootstrap unit (`RT-0c`) via
committed `Cargo.toml`, `Cargo.lock`, and `rust-toolchain.toml`, and pre-vendored into the host's
read-only `cargo_vendor_dir` (`cargo vendor <cargo_vendor_dir>`). Because `Cargo.toml`,
`Cargo.lock`, and `rust-toolchain.toml` are guarded by `GATE_INPUTS` and `codex-implement.py` runs
offline (`CARGO_NET_OFFLINE=true`), Codex implementer units (`RT-1`..`RT-12`) never modify
`Cargo.toml`, `Cargo.lock`, or `rust-toolchain.toml`; if a milestone ever requires a dependency
change, the orchestrator lands and vendors that dependency change in a separate host-prepared
commit first.

- **CLI & serialization**: `clap` (derive), `serde`, `serde_json`, `toml` (for
  `~/.config/driver-lab/config.toml`).
- **Strict YAML 1.2 parsing**: `saphyr-parser` (pure-Rust YAML 1.2 event parser with exact
  1-based line/column and byte offsets on every scalar and mapping key).
  - Enforces `specload.py`'s exact fail-closed rules: rejects non-NFC strings (`specload.py:222-223`,
    never silently normalizing author text), rejects duplicate mapping keys, rejects anchors,
    aliases, and merge keys (`<<`), rejects YAML directives/tags, and uses YAML 1.2 Core Schema
    scalar resolution (plain `true`/`false`/`null`/int/float; plain `yes`, `on`, and `1:30` remain
    strings).
  - Enforces a 10 MiB / 64-depth / 100,000-node cap on `.spec.yaml`, `.facts.yaml`, `.verify.yaml`,
    and `corpus.yaml` files, and a dedicated 32 MiB / 500,000-node cap on generated `*.index.yaml`
    files (`imx95-rm.index.yaml` with 10,661 outline entries contains ~55,000 YAML nodes).
- **JSON Schema validation**: `jsonschema` crate (Draft 2020-12) validating embedded
  `skills/spec-format/schema/*.schema.json` with exact JSON-pointer path and source-span reporting.
- **GFM / CommonMark parsing, containment, and parse-back verification**: `comrak` (the Rust port of
  GitHub's `cmark-gfm` with exact `sourcepos` line/column ranges), ensuring that link, HTML, and
  table containment checks match what GitHub renders, and supporting `specmd::check_view`
  parse-back verification on generated Markdown views.
- **HTML heading extraction**: `scraper` (`html5ever`) for standards-compliant `<h1>`–`<h6>`
  outline extraction in `driver-lab index` (`BF-IMX-8`).
- **PDF outline & encryption support**: `lopdf` with built-in decryption support for empty-password
  PDF Standard Security Handler Revisions 2–6 (including AES-128 and AES-256 permissions encryption,
  `BF-USB-3`), tested against synthetic `qpdf`-encrypted PDF fixtures.
- **HTTPS client, hashing & atomic files**: `ureq` (with `rustls`, for `fetch --cache`,
  `check --resolve-headings`, and `publish --fetch-anchors`), `sha2` (SHA-256),
  `unicode-normalization` (`is_nfc` check), `regex`, `tempfile` (RAII atomic writes and lazy
  scratch directories).

### 2.3 Unified CLI interface (`driver-lab`)

Every subcommand preserves the exit code contract: `0` pass, `1` spec/verification findings,
`2` CLI usage error, `3` environment or precondition error.

- **Global flags (accepted both before and after the subcommand name, `BF-IMX-18`)**:
  - `--json`: emit structured JSON output (including stable `code` identifiers on every finding).
  - `--scratch-dir <dir>`: explicit writable directory for lazy temporary directory allocation
    (`ENV-2`).
  - `--offline`: forbid network operations (`git fetch`, remote HTTP heading/resource retrieval);
    fail with exit `3` if an unbound repository or remote resource is requested (`ENV-1`).
  - `--version`: print `driver-lab <semver> (<DRIVER_LAB_TOOL_COMMIT>)` (`ENV-3`).
- **Spec Format 2 subcommands**:
  - `driver-lab validate <targets...> [--root <dir>] [--context-root <dir>...] [--require-license]`
  - `driver-lab check <targets...> [--root <dir>] [--context-root <dir>...] [--stubs-from <dir>] [--require-license] [--verify <file>...] [--resolve-headings]`
  - `driver-lab resolve <targets...> [--root <dir>] [--context-root <dir>...] [--repo <name>=<path>...] [--docs-dir <dir>] [--require-license]`
  - `driver-lab index <doc-id> --root <dir> --docs-dir <dir>`
  - `driver-lab status <targets...> [--root <dir>] [--context-root <dir>...] [--require-license] [--no-fail-on-pending]`
  - `driver-lab todo <targets...> [--root <dir>] [--context-root <dir>...] [--require-license]`
  - `driver-lab corpus <targets...> [--root <dir>] [--context-root <dir>...] [--docs-dir <dir>]`
  - `driver-lab render <targets...> [--root <dir>] [--context-root <dir>...] [--format md|html] [--merged] [--self-contained] [--out <path>]`
  - `driver-lab show <fact-ref> [--root <dir>] [--context-root <dir>...] [--repo <name>=<path>...] [--docs-dir <dir>]`
  - `driver-lab inventory <spec-file> [--root <dir>] [--repo <name>=<path>...] [--check]`
  - `driver-lab drift <targets...> [--root <dir>] [--repo <name>=<path>...]`
  - `driver-lab fetch <targets...> --cache <dir> [--root <dir>] [--context-root <dir>...]`
- **Companion subcommands**:
  - `driver-lab stubgen <domains.yaml> --out <skills-dir> [--check]`
  - `driver-lab publish build|check ...`
  - `driver-lab pinned-file-adapter --registry <yaml> --source-id <id> --out <dir> [--repo <path>]`
  - `driver-lab prose-facts [<paths...>]`
  - `driver-lab license-gate ...`
  - `driver-lab eval <extract|build-prompt|grade-facts|grade-code|run|score|validate-bank> ...`
  - `driver-lab campaign <sweep|contract-check|index-check|stopping> ...`
- **Post-cutover authoring & verification automation subcommands (`AUTO-1`..`AUTO-4`)**:
  - `driver-lab resource pin-files --root <dir> --repo <name>=<checkout> <paths...>`
  - `driver-lab resource pin-doc --root <dir> --id <doc-id> --class <class> --url <url> [--retrieval <url>] --file <path>`
  - `driver-lab assemble <target-spec.yaml> --from <slice.facts.yaml>...`
  - `driver-lab verify prepare <root> [--spec <id>] --phase blind|claims [--shard <k>/<n>] [--second-reader] --repo <name>=<path>... [--docs-dir <dir>] --out <packet.json>`
  - `driver-lab verify submit-blind --packet <packet.json> --input <blind.yaml>`
  - `driver-lab verify assemble <root> [--spec <id>] --packet <packet.json> --primary <r1.yaml>... [--second <r2.yaml>...]`

---

## 3. Isolated subagent environment contracts (`ENV-1`..`ENV-6`)

### `ENV-1` — Zero-write read set and lazy scratch allocation (`codex-review.py ro`)

`codex-review.py ro` runs Codex with `--sandbox read-only` and no network access. Nothing on the
filesystem is writable—not the workspace, not `/tmp` or `TMPDIR`, and not `$HOME`.

1. **In-memory subprocess pipes**: `git` (`git_source.rs`) and `pdftotext` (`pdf.rs`) capture
   `stdout` and `stderr` over OS pipes (`Stdio::piped()` with `.take(limit + 1)`) instead of
   `tempfile.TemporaryFile()`.
2. **Lazy scratch directory creation**: no subcommand allocates a temporary directory at startup.
   Scratch space is allocated only when an unbound repository actually requires a shallow fetch or
   when `eval grade-code` invokes `rustc`. Consequently, `validate`, `check` (without remote
   `--resolve-headings`), `status`, `todo`, `corpus`, `prose-facts`, `render` (to stdout), and
   `show` / `inventory` / `resolve` (when all cited repositories are locally bound via
   `--repo NAME=CHECKOUT`) perform **zero filesystem writes**.
3. **Offline and no-network failure mode**: when `--offline` is passed (or when a network fetch for
   an unbound repository or `check --resolve-headings` is attempted without network access),
   `driver-lab` fails fast with exit code `3` (precondition error) instructing the caller to bind
   repositories locally via `--repo NAME=CHECKOUT` / provide `--docs-dir`, or run in a networked
   phase.
4. **No implicit `$HOME` writes**: `driver-lab` never defaults any cache, state, or log path to
   `~/.cache`, `~/.local`, or `~/.config`.
5. **Partial-clone refusal on bound checkouts (exit `3`)**: before running `git cat-file` against a
   locally bound `--repo NAME=CHECKOUT`, `git_source.rs` inspects the checkout's git configuration
   for `extensions.partialClone` or `remote.*.promisor`. If either key is present, `driver-lab`
   exits `3` (precondition error: `partial clone: bind a full checkout`) rather than allowing `git`
   to attempt a lazy network fetch and `.git/objects` write inside a read-only sandbox.
   `GIT_NO_LAZY_FETCH=1` is also set in the `git` child environment as defense in depth.
6. **CI read-only sandbox enforcement**: CI runs the read-only subcommand suite inside a strict
   read-only, network-isolated container (`bwrap --ro-bind / / --unshare-net` on Linux) so any
   regression that reintroduces eager tempfiles or `$HOME` writes fails CI immediately.

### `ENV-2` — Explicit scratch and `TMPDIR` handling (`codex-review.py net`)

`codex-review.py net` runs Codex with `--sandbox workspace-write`, `exclude_slash_tmp=true`, and
`exclude_tmpdir_env_var=true`. Only `REVIEW_DIR` (`cwd`) is writable, while the inherited
`TMPDIR=/tmp` is unwritable.

1. **No silent fallback to `cwd`**: `driver-lab` never silently falls back to creating temporary
   files or directories inside `cwd` (in `codex-implement.py`, `cwd` is `work/`, where stray files
   become refused paths; in `ro`, `cwd` is read-only).
2. **`codex-review.py net` `TMPDIR` injection**: because Codex composes its own tool commands and
   child tools (`git`, `pdftotext`, `rustc`) read `TMPDIR` rather than `driver-lab` flags,
   `codex-review.py` in `net` mode creates `<REVIEW_DIR>/tmp` and passes
   `env={..., "TMPDIR": "<REVIEW_DIR>/tmp"}` to `subprocess.run` while keeping
   `exclude_tmpdir_env_var=true` (so the host `/tmp` is still not added as a writable root, while
   `<REVIEW_DIR>/tmp` is writable as a subdirectory of `REVIEW_DIR`).
3. **Scratch resolution order**: when a subcommand requires scratch space, `sandbox.rs` checks
   `--scratch-dir <dir>` first, then `TMPDIR` (`std::env::temp_dir()`), and exits `3` naming both
   if neither directory is writable.

### `ENV-3` — Milestone implementer sandbox (`codex-implement.py`)

`codex-implement.py` runs in `<scratch>/work` (a `git archive` export with **no `.git`
directory**), with only `work/` and `TMPDIR` (`<scratch>/tmp`) writable (`~/.cargo` and `~/.rustup`
are read-only), `PATH` scrubbed to `/usr/local/bin:/usr/bin:/bin:<dirname(codex)>`, and a post-run
`walk(work, entries)` check that refuses any binary file (`\x00` bytes), symlink, dotfile, or file
larger than 2 MiB and aborts (`exit 4`) above 200,000 entries.

1. **Configured tool binary and concrete Rust toolchain in `~/.config/driver-lab/config.toml`**:
   - Configure `driver_lab_binary`, `rust_toolchain_bin`, and `cargo_vendor_dir` in
     `~/.config/driver-lab/config.toml` (with `DRIVER_LAB_BIN`, `DRIVER_LAB_RUST_BIN`, and
     `DRIVER_LAB_CARGO_VENDOR` environment overrides).
   - Validate these paths using the same ownership and permission checks `codex_binary()` enforces
     in `codex-implement.py:199-217`: absolute path, `realpath`, regular executable file (or
     directory for toolchain/vendor), owned by current UID or root, not writable by group or
     others, and located outside `work/` and `TMPDIR`.
   - Append the concrete toolchain directory (`~/.rustup/toolchains/<toolchain>/bin` plus
     `RUSTUP_TOOLCHAIN=<toolchain>`) to `child_env["PATH"]` rather than `~/.cargo/bin`, avoiding
     `rustup` proxy shims that attempt to lock or write inside read-only `~/.rustup`.
2. **Version handshake (`DRIVER_LAB_TOOL_COMMIT`)**:
   - Releases and host installations compile `driver-lab` with
     `DRIVER_LAB_TOOL_COMMIT=$(git rev-parse HEAD)`.
   - Once `driver-lab` is cut over (`RT-11`/`RT-12`), `codex-implement.py` compares
     `driver-lab --version` against `BASE` (resolved to a full commit SHA from the repository) or
     `tool_commit` in `~/.config/driver-lab/config.toml`, and `patch-gate.py` compares it against
     the main checkout's `HEAD` (or `DRIVER_LAB_TOOL_COMMIT` in CI), rejecting `"unknown"` or
     mismatches with exit `3`. After merging any pull request that changes `src/` or `Cargo.*`, the
     operator rebuilds the installed binary (`DRIVER_LAB_TOOL_COMMIT=$(git rev-parse HEAD) cargo
     install --locked --path .`) so the host binary stays at `HEAD`.
3. **`CARGO_TARGET_DIR` inside `TMPDIR`**:
   - `codex-implement.py` sets `CARGO_TARGET_DIR = os.path.join(tmp, "cargo-target")` in
     `child_env()` so `cargo build` and `cargo test` never write `target/` (ELF binaries, `.rlib`
     files, >2 MiB artifacts, or thousands of build files) into `work/`.
4. **Offline Cargo with an out-of-tree vendor directory**:
   - Although `codex-implement.py` runs with `network_access=true`, `child_env()` sets
     `CARGO_NET_OFFLINE=true` and `CARGO_HOME = os.path.join(tmp, "cargo-home")`, writing a
     generated `config.toml` into `CARGO_HOME` that redirects `[source.crates-io]` to the read-only
     pre-vendored `cargo_vendor_dir` **outside the repository**.
   - `vendor/` is never committed inside the repository because upstream crates include binary test
     fixtures and files > 2 MiB that `walk()` refuses.
5. **RAII atomic file writes (no stray dotfiles in `work/`)**:
   - Subcommands that write output files (`index`, `stubgen`, `pinned-file-adapter`, `render --out`,
     `publish`) stage writes in the resolved scratch directory (or use RAII tempfiles cleaned up on
     drop) so an interrupted process never leaves a dotfile (such as `.index.tmp` or `.stubgen.tmp`)
     inside `work/`.

### `ENV-4` — Post-patch gate (`patch-gate.py`)

`patch-gate.py` runs suites against `WORKTREE` and fails (`exit 3`) if `worktree_digest` changes
or any untracked file appears.

1. `default_suites()` runs `cargo test --locked --offline` with `CARGO_TARGET_DIR` set to a
   temporary directory outside `WORKTREE` and `CARGO_HOME` pointed at an offline vendor config,
   leaving `WORKTREE` completely untouched.
2. `GATE_INPUTS` (`patch-gate.py:98-101`) is updated in `RT-0b` (before any Rust code milestone)
   to guard `Cargo\.toml`, `Cargo\.lock`, `rust-toolchain\.toml`, `\.cargo/.*`, and
   `tests/conformance/.*` alongside the existing Python gate inputs (so no implementer patch can
   modify dependencies or weaken conformance expectations without failing the gate-input check); at
   Python retirement (`RT-12`), `skills/spec-format/requirements\.txt` and
   `skills/spec-format/scripts/prosefacts\.py` are replaced by `evals/requirements\.txt` (while
   `utilities/check-no-hardware-facts\.py` is already guarded by `utilities/check-[^/]*\.py`).
3. `RISKY` (`patch-gate.py:88-91`) is extended with Rust-specific patterns (`std::process::Command`,
   `std::net`, `unsafe\b`, `include_bytes!`, `env!\(`) so the orchestrator reviews any new process,
   network, or `unsafe` usage in Rust patches.

### `ENV-5` — Untrusted candidate code execution (`driver-lab eval`)

`driver-lab eval grade-code` compiles LLM-generated Rust candidate answers with `rustc --test` and
executes the resulting test binary.

1. Compilation and test execution stage all intermediate artifacts and binaries in the resolved
   scratch directory (`--scratch-dir` or `TMPDIR`).
2. Execution of the compiled candidate test binary is wrapped in a minimal OS sandbox:
   - **Linux**: `bwrap` mounting read-only **only** `/usr`, `/lib`, `/lib64` (when present), and
     the compiled binary's scratch directory, plus `--tmpfs /tmp --unshare-all --die-with-parent
     --clearenv` (never `--ro-bind / /`, which would allow untrusted candidate code to read `$HOME`
     secrets and print them to test stdout).
   - **macOS**: `sandbox-exec` profile denying network and host home-directory reads/writes (noting
     that `sandbox-exec` is deprecated by Apple on macOS 14+ though still functional; if unavailable,
     `eval grade-code` requires `--allow-unsandboxed` to run candidate binaries).

### `ENV-6` — Claude Code subagents, release distribution, and skill preflight

1. **Auditable cache population (`driver-lab fetch --cache <dir>`)**: `board-expert` runs with
   `disallowedTools: Write, Edit, NotebookEdit` and materializes pinned repositories/documents via
   `Bash`. `driver-lab fetch --cache <dir>` replaces ad-hoc shell pipelines with one single
   command that validates SHA-256 digests and full git commit hashes.
2. **Release artifacts and CI bootstrap**: `driver-lab` provides a release workflow building
   static/self-contained binaries for `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`,
   `x86_64-apple-darwin`, and `aarch64-apple-darwin` with SHA-256 checksums, plus a reproducible
   `DRIVER_LAB_TOOL_COMMIT=<sha> cargo install --locked --path .` installation path.
3. **Fail-fast skill preflight**: every `SKILL.md` starts with `driver-lab --version` and stops
   with installation instructions if the binary is missing or its `DRIVER_LAB_TOOL_COMMIT`
   mismatches, rather than attempting to compile or install inside a restricted subagent.

---

## 4. Requirements derived from `BUGS-FOUND.md` (31 entries)

All 31 entries in [BUGS-FOUND.md](../BUGS-FOUND.md) (`BF-USB-1`..`BF-USB-4`,
`BF-IMX-ISS-1`..`BF-IMX-ISS-7`, `BF-IMX-8`..`BF-IMX-18`, `BF-ARM-19`..`BF-ARM-21`,
`BF-GW-22`..`BF-GW-27`) are converted into normative requirements below.

### 4.1 Document locator and hex-evidence verification (`src/docresolve.rs`, `src/resolve.rs`)

- **`BF-USB-1`, `BF-USB-2`, `BF-IMX-ISS-6` (part 2), & `BF-IMX-13` (Locator prefix normalization,
  trailing punctuation, en-dashes, and line-wrapped captions)**:
  When matching `table`, `figure`, or `section` locators in extracted document text:
  1. Strip any leading case-insensitive `table\s+` or `figure\s+` prefix from `value` before
     prepending the kind label so `table: "Table 16"` and `table: "16"` produce identical patterns
     (never `"table Table 16"`).
  2. Strip trailing period/colon punctuation (`[.:]+$`) from the locator number token so
     `table: "16."` (`BUGS-FOUND.md` #17) and `table: "16"` behave identically.
  3. Allow `-` in a locator token to match either ASCII hyphen (`-`, U+002D) or Unicode en-dash
     (`–`, U+2013) (`BF-USB-2`), and include `–` in both the lookbehind `(?<![\w.\-–])` and
     lookahead `(?![\w]|[.\-–]\w)`. This matches captions with trailing punctuation (`Table 9-2.
     Format of Setup Data`, `Figure 1-1. LPM State Transition Diagram`, `Table 2–3. USBLEGSUP`,
     `1.2. Purpose`) while still preventing `16` from matching `16.1` or `9-2` from matching
     `9-2-1` (`BF-USB-1`, `BF-IMX-13`).
  4. When a `table:` or `figure:` locator includes both a number and caption title (e.g.,
     `Table 282. Break character length`), allow optional punctuation (`.` or `:`) and arbitrary
     whitespace/newlines between the table/figure number and its caption title so line-wrapped PDF
     captions (`Table 282\nBreak character length`) match (`BF-IMX-ISS-6`).
- **`BF-IMX-ISS-6` (part 1) & `BF-IMX-17` (Multi-page section and table span lookup via verified
  `.index.yaml`)**:
  When `section:` is cited alongside `page:` or `pages:` on a mid-section or mid-table page (e.g.,
  citing pages `2582`–`2583` of a section spanning pages `2578`–`2586`, or page `90` of a table
  spanning pages `86`–`97`):
  1. If `<root>/index/<doc>.index.yaml` exists and its recorded `sha256` equals the document's
     pinned `sha256` in `resources.documents` (a stale index with a mismatched `sha256` is never
     trusted), `docresolve` looks up the cited `section:` in the index by exact normalized section
     `number` or exact normalized `title` (never by arbitrary substring).
  2. If a matching index section entry is found and all cited `page`/`pages` fall within its
     inclusive `[start_page, end_page]` span, the `section:` locator is satisfied without requiring
     the literal section heading string to reappear on the mid-section page. Because index page
     spans are inclusive of the next sibling section's start page `P` (`index.py:8-10`), a citation
     on shared boundary page `P` satisfies `section:` for either section ending or starting on `P`.
- **`BF-IMX-ISS-7` & `BF-IMX-16` (Vendor `h`-suffix hexadecimal notation in cited documents)**:
  Spec files continue to require canonical `0x`-prefixed hexadecimal literals in claims and
  payloads. When extracting hexadecimal values from cited document text (PDF, Markdown, HTML, wiki)
  for `claim hex values` and `register offset` cross-checking, `resolve` and `docresolve` recognize
  both `0[xX][0-9a-fA-F_']+` and vendor suffix-`h` hex tokens matching
  `\b(?:[0-9][0-9A-Fa-f_]*|[0-9A-F][0-9A-F_]+)[hH]\b` (requiring either a leading decimal digit
  `0-9` or uppercase-only hex digits `0-9A-F` of length >= 2 so English words such as `each` or
  `beach` never parse as hex). Extracted values are normalized to integer values so `0x44380000`,
  `0x04040007`, `0x14`, `0x1c`, and `0x580` match `4438_0000h`, `0404_0007h`, `14h`, `1Ch`, and
  `580h`.

### 4.2 Document indexing and outline extraction (`src/pdf.rs`, `src/index.rs`)

- **`BF-USB-3` (Empty-password AES-encrypted public PDFs)**:
  `src/pdf.rs` uses `lopdf`'s standard PDF decryption to read outlines, page counts, and page
  labels from public PDFs encrypted with an empty user password under Standard Security Handler
  Revisions 2–6 (including AES-128 and AES-256 permissions encryption, such as USB-IF
  `usb-bc-1.2.pdf`), tested in CI against synthetic PDFs encrypted with `qpdf`.
- **`BF-USB-4`, `BF-IMX-10`, & `BF-ARM-20` (PDF outline section number extraction for prefixed
  chapters, single-letter appendices, `Part N`, and Arm alphanumeric sections)**:
  `index.rs` extracts `number` from outline titles matching:
  1. Prefixed chapters/sections/appendices: leading `(?:Chapter|Section|Appendix)\s+([0-9A-Z]+(?:\.[0-9]+)*)\.?`
     extracts the identifier (`Chapter 1. Introduction` -> `number: "1"`,
     `Appendix A Release Notes` -> `number: "A"`). Leading `Part\s+([0-9A-Z]+)\.?` extracts
     `number: "Part <N>"` (e.g., `"Part 1"`, avoiding collision with `Chapter 1`'s `"1"`).
  2. Dotted numeric and alphanumeric hierarchies (`1.2.3`, `A.1`, `A1.2`, `B2.41`, `C1.2.3`).
  3. Bare Arm alphanumeric chapter/section tokens (`A1`, `B2`, `C1`, `D1`:
     `^[A-Z][0-9]+(?:\.[0-9]+)*\b`; `BF-ARM-20`).
  4. Top-level single-letter appendix bookmarks (`^([A-Z])\.?\s+\S`) when followed by a child
     entry numbered `<letter>.1` / `<letter>1` or appearing at outline level 1 after numbered
     chapters (excluding `"A"` and `"I"` unless followed by a `<letter>.1` child or preceded by
     `Appendix`).
- **`BF-IMX-8` & `BF-GW-22` (Indexing HTML and Trac/MoinMoin wiki documents)**:
  `driver-lab index` detects document format before parsing:
  1. `%PDF-` magic -> PDF outline indexer (`src/pdf.rs`).
  2. HTML documents (`<!DOCTYPE html` or `<html` in the first 4 KiB) -> HTML heading extractor
     using `scraper` (`html5ever`) over `<h1>`–`<h6>` elements (`BF-IMX-8`).
  3. Plain-text / Markdown documents -> ATX Markdown headings (`#`–`######`) via `comrak`; if zero
     ATX headings are present, fall back to Trac/MoinMoin wiki headings
     (`^(=+)\s*(.+?)\s*\1\s*$`), matching `docresolve`'s heading support (`BF-GW-22`).
- **`BF-IMX-9` (Disambiguating shared boundary pages in `index::links`)**:
  In `index.rs`:
  1. When a fact citation specifies `section:`, normalize `section:` (stripping leading
     `Section `/`Chapter `/`Appendix ` prefixes and trailing titles) and match against index
     entries by `number` or exact normalized `title` first before falling back to page-range
     containment.
  2. When a citation provides only `page:`/`pages:` (or `section:` does not match any index entry's
     number/title) and lands on a shared boundary page `P` where section $i$ ends and section
     $i+1$ starts, link the citation to the deepest section that *starts* on page `P`, and
     otherwise to the deepest section whose `[start, end]` span contains `P`.
- **`BF-IMX-11` (Lazy, fast loading of `*.index.yaml` files)**:
  `driver-lab` loads `<root>/index/*.index.yaml` lazily—only in subcommands and code paths that
  consume document indexes (`index`, `corpus`, `docresolve`, `render`, `publish`, and `check` when
  validating index files)—and never during `validate`, `status`, or `todo`.

### 4.3 Markdown, placeholder, and prose-fact checking (`src/specmd.rs`, `src/prosefacts.rs`, `src/stubgen.rs`)

- **`BF-IMX-12`, `BF-ARM-19`, & `BF-GW-24` (Template placeholder vocabulary extracted from non-comment
  template scalars and `<n>` register-index metavariables)**:
  1. Rather than matching every `<[A-Za-z]...>` substring or scanning raw template text including
     `#` comments (which in `skills/board-spec-scaffold/templates/corpus.yaml:4` mention prose words
     like `<id>`, `<fact>`, and `<note>`), `src/specmd.rs` embeds the repository's template files
     (`skills/board-spec-scaffold/templates/**` and `skills/peripheral-spec/templates/**`) via
     `include_str!`, parses the `.yaml` templates through `yaml_strict` to extract `<...>` tokens
     from **YAML scalar values only** (ignoring YAML comments) and from `.md` template bodies,
     supplemented by `<(?:board|soc|chip|ip|peripheral|doc|repo|domain|stub)-[^>\n]+>`. A unit test
     asserts that every scalar `<...>` placeholder in every template file is flagged.
  2. Non-template angle-bracket tokens in hardware/software prose—such as Arm register-index
     subscripts (`GICD_IGROUPR<n>`, `IRQ<0..239>`), Devicetree cells (`reg = <0x0>`), C headers
     (`<linux/...>`), and backticked metavariables in `corpus.yaml` notes (such as
     `` `(spec:imx95#<fact-id>)` ``)—are not flagged as unsubstituted template placeholders
     (`BF-IMX-12`, `BF-GW-24`).
  3. In Spec Markdown (`comrak` AST checking over `claim`, `todo.text`, and `.verify.yaml` notes),
     an inline HTML token consisting of a single lowercase ASCII letter immediately following an
     identifier character (`[A-Za-z0-9_]<[a-z]>`, e.g. `GICD_IGROUPR<n>`, `CNTACR<n>`) is accepted
     as a register-index subscript and escaped to `&lt;n&gt;` in HTML/Markdown rendering (verified
     by `specmd::check_view` parse-back). Any other raw inline HTML tag fails with a diagnostic
     that suggests wrapping metavariables in backticks (`` e.g. `GICD_IGROUPR<n>` ``; `BF-ARM-19`).
- **`BF-IMX-ISS-4` (Pairwise domain stub `split:` overlap and `domains.yaml` prose-facts guidance)**:
  1. In `stubgen.rs`, when generating domain expert stubs from `domains.yaml`, automatically include
     sibling domain stub names that share an `entry:` `spec` in each generated stub's `split:`
     clause, and in `speccheck.rs` (`check_overlap`), accept a domain stub whose `split:` names the
     primary board/SoC expert on that shared `spec` without requiring manual $O(N^2)$ cross-listing.
  2. Update `skills/board-spec-scaffold/templates/domains.yaml` to document that `prose-facts`
     forbids `UPPER_SNAKE_CASE` register/block identifiers and multi-digit hex literals in
     `domains.yaml` prose fields.

### 4.4 Schema and semantic checker rules (`schema/spec.schema.json`, `src/speccheck.rs`, `src/render_md.rs`, `src/render_html.rs`)

- **`BF-IMX-14` (`resources.documents[].class` enum and semantic rules for `datasheet`, `errata`,
  and `appnote`)**:
  Expand `$defs.document.properties.class` in `skills/spec-format/schema/spec.schema.json` and
  `src/speccheck.rs` to `["databook", "datasheet", "errata", "appnote", "standard", "doc"]`. In
  `speccheck.rs`, `datasheet`, `errata`, and `appnote` follow the same citability and page-bound
  rules as `databook` (they are directly citable by facts and require `pages` on PDF documents).
- **`BF-GW-25` (`check_unattached_peripherals` recognizes `parts:` on `board`/`soc`/`chip` specs)**:
  In `speccheck.rs` (`check_unattached_peripherals`), include all spec IDs referenced in `parts:`
  of `kind: board`, `kind: soc`, and `kind: chip` specs in the attached set, so a board-level
  peripheral spec listed in a board's `parts:` does not trigger a false-positive
  unattached-peripheral warning.
- **`BF-GW-27` (`render --merged` context-root taint rules and warning banner)**:
  Define explicit taint classes for `--context-root` during `render --merged`:
  1. **Tainting findings (block `render --merged` with exit `1`)**: YAML/JSON Schema load errors,
     root/layer/spec/fact ID collisions, license-gate violations (`accepts`), and
     refused-character/containment errors.
  2. **Non-tainting downgraded context warnings (permit `render --merged`)**: unresolved references
     from the context root to a third root not loaded for this render (e.g., an upstream SoC
     `instances[].ip` pointing to a separate IP root) and upstream `.verify.yaml` `spec_file` path
     warnings. All downgraded context-root warnings are rendered explicitly in the output's
     context-warnings banner so they are never hidden.

### 4.5 CLI flag consistency and exit codes (`src/main.rs`, `src/resolve.rs`, `src/worklist.rs`)

- **`BF-IMX-ISS-5` (No eager Python/PDF dependency failure on non-PDF commands)**:
  Eliminated by compiling `driver-lab` as a single self-contained Rust binary with embedded JSON
  Schemas and native `lopdf` outline parsing. External helper binaries (`pdftotext`, `git`,
  `rustc`) are checked lazily only by the subcommands that invoke them.
- **`BF-IMX-18` (Consistent `--root`, `--context-root`, and `--json` flags across subcommands)**:
  1. `--json` is registered as a global flag on the top-level `clap` parser (`global = true`).
  2. `--context-root <dir>` is accepted uniformly across `validate`, `check`, `resolve`, `status`,
     `todo`, `corpus`, `render`, `show`, and `fetch`.
  3. Standalone `.facts.yaml` mode in `check` is triggered by inspecting whether a target path ends
     with `.facts.yaml` (or has `kind: facts`), not whether `--root` was passed alongside a
     directory target.
- **`BF-ARM-21` (`status --no-fail-on-pending` for verifier workflows)**:
  Add `--no-fail-on-pending` to `driver-lab status` (and update `skills/spec-verifier/SKILL.md`
  Step 1 to use it) so extracting `basis` hashes for `unverified` or `needs-second-reader` specs
  exits `0` under `set -euo pipefail`, while still running `check` first and exiting `1` on any
  schema, semantic, or license error.
- **`BF-GW-26` (Warn, do not abort, on unused `--repo` mappings in `resolve`, `show`, `inventory`,
  and `drift`)**:
  When `--repo <name>=<path>` names a repository ID not referenced in the subset of `.spec.yaml`
  files passed on that invocation, emit a diagnostic warning (`warning: unused --repo mapping
  '<name>'`) rather than aborting with exit code `2`. This allows shared `--repo` flag lists across
  multi-spec repositories while still surfacing typos like `--repo linx=...`.

### 4.6 CI templates, `checks.sh`, and skill guidance (`skills/spec-format/ci/`, `skills/board-spec-scaffold/`)

- **`BF-IMX-ISS-1` (`skills/spec-format/ci/publish.yml` checkout path)**:
  Update `skills/spec-format/ci/publish.yml` and `skills/spec-format/ci/README.md` to check out the
  spec repository into `path: repo`, pass `repo/specs` and `--source-commit "repo/specs=$SOURCE_COMMIT"`
  to `driver-lab publish`, and pin `actions/checkout` to `3d3c42e5aac5ba805825da76410c181273ba90b1`
  (`v7.0.1`).
- **`BF-IMX-ISS-2` (`skills/spec-format/ci/checks.sh` cross-root overlay `self_test` on docs-only
  repositories)**:
  In `skills/spec-format/ci/checks.sh` `self_test()`, when `SRC_FIT=0` (or the repository root
  marker has `accepts: []`), construct a documents-only overlay fixture (without a `BSD-3-Clause`
  `resources.repos` entry) for the cross-root overlay check instead of copying
  `widgetchip-bsd-overlay.spec.yaml` verbatim.
- **`BF-IMX-ISS-3` (`skills/spec-format/ci/checks.sh` support for `--stubs-from` and
  `driver-lab stubgen --check`)**:
  In `skills/spec-format/ci/checks.sh` and `skills/board-spec-scaffold`'s `checks.sh` template,
  support `STUBS_DIR` (auto-detected when `skills/` contains stub `SKILL.md` files) and
  `DOMAINS_MANIFEST` (auto-detected when `domains.yaml` is present at the repo root) so
  `check_specs()` automatically passes `--stubs-from "$STUBS_DIR"` to `driver-lab check` and runs
  `driver-lab stubgen "$DOMAINS_MANIFEST" --out "$STUBS_DIR" --check`.
- **`BF-IMX-15` (Vendor CDN `retrieval:` guidance for NXP and Arm)**:
  Document in `skills/board-spec-scaffold/SKILL.md` and `skills/spec-format/SKILL.md` that:
  - Public NXP manuals blocked by CDN bot filtering on `https://www.nxp.com/docs/en/...` should
    record `url: https://www.nxp.com/docs/en/...` and
    `retrieval: https://cache.nxp.com/docs/en/...`.
  - Public Arm TRMs and architecture reference manuals blocked on `https://developer.arm.com/documentation/<doc_id>/latest`
    should query `https://documentation-service.arm.com/documentation/<doc_id>/latest/` to obtain
    the direct asset URL `https://documentation-service.arm.com/static/<object_id>` for `retrieval:`.
- **`BF-GW-23` (`checks.sh` `check_resolve` auto-binds valid local `cache/<name>` checkouts)**:
  In `skills/spec-format/ci/checks.sh` and `skills/board-spec-scaffold`'s `checks.sh` template,
  `check_resolve()` inspects `cache/<name>/.git` for each repo in `resources.repos`. If
  `cache/<name>` is a full clone (neither `extensions.partialClone` nor `remote.*.promisor` set)
  and contains the pinned commit (`git cat-file -e <commit>^{commit}`), `check_resolve()`
  automatically binds `--repo <name>=cache/<name>`; if `cache/<name>` is a partial clone or lacks
  the commit, `check_resolve()` prints a note and falls back to normal resolution.

---

## 5. Authoring & verification automation and model tiering (`AUTO-1`..`AUTO-6`, `TIER-1`..`TIER-4`)

To speed up spec authoring and verification without sacrificing verification rigor, the following
automation subcommands (`src/author.rs`, `src/verify_flow.rs`) and model-tiering rules are scheduled
as dedicated post-`RT-G` units (`RT-A1`..`RT-A4`) so they do not widen `RT-1`..`RT-12`'s porting
scope.

### 5.1 Direct tool automation (`AUTO-1`..`AUTO-6`)

- **`AUTO-1` — Resource pinning, license gating, and attribution (`driver-lab resource pin-files` /
  `pin-doc`)**:
  1. `driver-lab resource pin-files --root <dir> --repo <name>=<checkout> <paths...>` resolves the
     full 40-character git commit, scans `SPDX-License-Identifier` headers and copyright notices,
     gates each file's license against the target root's `accepts` list, and emits a schema-valid
     `resources.repos` YAML block with `files[].license_from` and `files[].attribution` populated.
  2. `driver-lab resource pin-doc --root <dir> --id <doc-id> --class <class> --url <url>
     [--retrieval <url>] --file <local-file>` hashes the local PDF/HTML/Markdown file, extracts PDF
     `pages` count via `lopdf`, applies the NXP/Arm CDN `retrieval` rewrite table (`BF-IMX-15`),
     emits the `resources.documents` YAML entry, and generates `<root>/index/<doc>.index.yaml`
     (honoring `--offline`).
- **`AUTO-2` — Deterministic `.verify.yaml` assembly, basis stamping, and `GAP` scaffolding
  (`driver-lab verify assemble`)**:
  Reader subagents return only `{key, verdict, contrary_evidence, citation_precision, note,
  correction?}` for the delta keys they read. `driver-lab verify assemble` deterministically:
  1. Verifies that neither `spec_sha256` nor any fact's `basis` hash drifted since `verify prepare`
     (preventing TOCTOU stamping of a newer basis; `spec-verifier/SKILL.md:138`).
  2. Auto-populates deterministic `GAP` verdict scaffolding (`verdict: GAP`, `citation_precision:
     imprecise`, `contrary_evidence: not-checked`, as required by `spec-verifier/SKILL.md:299`) for
     unsupported gap facts, leaving only the `todo` method observability note to the reader.
  3. Merges preserved `current` verdicts, copies exact `basis` and `upstream` hashes from
     `records.rs`, constructs `ADJUDICATE` + `readings` whenever primary and second readers
     disagree, and computes the five `summary` counts (`pass`, `fail`, `unverifiable`, `gap`,
     `adjudicate`).
- **`AUTO-3` — Two-phase verification work packets and parallel sharding
  (`driver-lab verify prepare --phase blind|claims [--shard K/N]`)**:
  1. **Guard 1 (Preserve blindness)**: `--phase blind` emits *only* the `spec_sha256`-seeded 10%
     anchor sample (`verifier-prompt.md:38-39`) with no claims. Only after `driver-lab verify
     submit-blind` records the reader's blind derivations does `--phase claims` release the delta
     claim packet (and strips the primary reader's verdicts/reasoning when preparing a
     `--second-reader` packet per `spec-verifier/SKILL.md:123`).
  2. **Guard 2 (Starting index, not a reading boundary)**: The packet pre-extracts cited source
     lines and PDF pages to save setup tool turns, while readers retain full access to the pinned
     source checkout and PDFs so they are not anchored solely to author-cited lines during
     contrary-evidence and governing-table-notes searches (`spec-verifier/SKILL.md:203-229`).
  3. **Parallel sharding (`--shard K/N`)**: Partitions delta facts deterministically by section/spec
     so $N$ verifier subagents run in parallel and merge cleanly via `verify assemble`.
- **`AUTO-4` — Fail-closed fact slice merging (`driver-lab assemble`)**:
  Merges `hardware-investigator` `.facts.yaml` slices into a target `.spec.yaml` (`resources`,
  `resetTypes`, `fieldAccessPolicyDefinitions`, `enumerationDefinitions`, `facts`), failing closed
  on any ID or resource collision and printing a mapping proposal (never silently renaming IDs;
  `peripheral-spec/SKILL.md:227-228`).
- **`AUTO-5` — Semi-mechanical verifier checks as coded `driver-lab check` warnings**:
  Emit warning codes in `driver-lab check` for:
  1. **#103**: register/layout field whose `meaning` names a finite value/mask table without
     `enumeratedValues`, `enumerationDefinitionRef`, or a `todo`.
  2. **#105**: `action` sequence step containing wait/poll/handshake verbs without a numeric bound,
     `#quantity` note reference, or `todo`.
  3. **#150**: numeric `section: target` fact lacking a `role: target` citation or `todo`.
  4. **D31/D32 duplicate candidates**: register facts whose only support is an accepted canonical
     source without `requirement`, `conflicts`, `todo`, or document citations.
  These rules remain on the verifier's checklist so warnings are still judged semantically.
- **`AUTO-6` — Declarative canonical register-source references instead of bulk `#define`
  transcription (D31/D32)**:
  Rather than bulk-emitting YAML facts for every `#define` in a C header (which violates D31/D32's
  rule against duplicating canonical sources and makes `inventory --strict` circular against the
  same parser), implement the Format 2 extension anticipated by `peripheral-spec/SKILL.md:204-205`:
  a declarative canonical register-source reference (`repo`, `path`, symbol scope) verified
  mechanically by `inventory`, so authors only record what the header lacks (`requirement`,
  `conflicts` where datasheet and header disagree, `todo`s, and `sequences` pointing at those
  symbols). Transcribing stand-in facts from a source whose license is outside the target root's
  `accepts` list remains a user policy decision per [LICENSE-SPLIT-PLAN.md](LICENSE-SPLIT-PLAN.md),
  regardless of tooling.

### 5.2 Evidence-first model tiering (`TIER-1`..`TIER-4`)

In verification, the dangerous error is a **false `PASS`** (rubber-stamping a claim that drops a
hardware condition or protocol ordering constraint). Routing rules that use a smaller model first
and escalate only `FAIL` verdicts leave false `PASS`es unexamined. Repository evidence
([CR6b.md](../evidence/CR6b.md), [AF-1.md](../evidence/AF-1.md), and
[DRIVER-QUALITY.md](../DRIVER-QUALITY.md)) shows that verification quality comes from **cross-family
reader diversity** (`CR6b` on revision 8 produced 84 upheld or partly upheld non-`PASS` lines,
including 12 driver-behavior `R` findings, most in kernel protocol order, that earlier readers had
passed or never read at that grain) and **pre-declared calibration thresholds**:

- **`TIER-1` (`T0`, Tools first)**: All deterministic resource pinning, indexing, slice merging,
  `GAP` scaffolding, `.verify.yaml` assembly, and coded warnings run in `driver-lab` with zero LLM
  tokens.
- **`TIER-2` (`T1`, Ground-truth calibration gate before adopting any cheaper reader)**: Before
  adopting a faster/cheaper model for any verification class, run the candidate model blind on the
  exact revision-8 input text and adjudicated non-`PASS` ground truth from
  [CR6b.md](../evidence/CR6b.md) (84 upheld or partly upheld, 16 rejected; excluding the 19
  input-limitation items), with [AF-1.md](../evidence/AF-1.md) as a secondary check, measuring its
  false-`PASS` rate by fact class against a threshold set in advance
  ([DRIVER-QUALITY.md](../DRIVER-QUALITY.md#L115-L117)).
- **`TIER-3` (`T2`, Focused/faster model with mandatory frontier audit sample)**:
  - *Authoring*: `corpus.yaml` drafting from `driver-lab index` outlines and DTS nodes; initial
    drafting of non-critical `registers` / `data-formats` / `instances` descriptions (tracking
    downstream verifier `FAIL` rework rate).
  - *Verification*: Only after passing `TIER-2` calibration, primary reading for non-critical
    `as-implemented` register, layout, and instance value facts whose hex/offset/mask values are
    verified by `resolve` / `inventory`, **paired with a mandatory 20% seeded frontier audit sample
    of `T2` `PASS`es**. Any audit disagreement triggers a full frontier re-read of that batch.
- **`TIER-4` (`T3`, Frontier model mandatory + cross-family diversity and parallel sharding)**:
  - Frontier models remain mandatory for `critical: true` facts, `sequences`/state machines/ordering
    constraints, DMA/coherency, interrupts, errata/gotchas, `inference` derivations, `hw-required`
    vs. `as-implemented` classification, the 10% blind anchor sample, contrary-evidence searches on
    `T3` facts, and adjudication.
  - Second readers on `critical: true` facts must use a **different model family** (`CR6b`, `AF-1`),
    and `verify prepare --shard K/N` runs multiple frontier readers concurrently for wall-clock
    speed.

---

## 6. Canonical hashing, conformance corpus, and migration strategy

1. **Language-neutral conformance corpus (`RT-0a`)**:
   Before any Rust checker code is written, `RT-0a` enumerates every finding emitted by the Python
   implementation, assigns stable finding codes, and materializes `tests/conformance/` cases
   verified against `spec.py`. `tests/conformance/.*` is added to `GATE_INPUTS` in `patch-gate.py`
   so no implementer patch can modify conformance expectations alongside code under test.
2. **Byte-for-byte `fact-v1` basis hash parity (`RT-3a`)**:
   `src/records.rs` implements the exact `fact-v1` canonical JSON digest and dependency DAG fold
   (`Freshness`) used by `records.py` (sorted keys, compact `","`/`":"` separators, UTF-8 NFC
   strings, integer-valued numbers formatted without `.0`). `RT-3a` verifies byte-for-byte
   `fact-v1` hash parity against `records.py` across all existing specs and conformance fixtures.
   Because `fact-v1` hashes are identical, existing `.verify.yaml` files require **no** basis-hash
   rewriting at cutover, preventing any stale verdict from being laundered into `current`.
3. **Cutover, automation units, and downstream rollout**:
   In `RT-12`, `driver-lab` cuts over inside this repository, retiring `skills/*/scripts/*.py`, and
   `RT-G` completes the core porting verification gate. Next, `RT-A1`..`RT-A4` deliver the
   authoring/verification automation subcommands (`AUTO-1`..`AUTO-6`) and model-tier calibration
   (`TIER-1`..`TIER-4`). Finally, downstream `hardware-specs-*` repositories are updated in
   rollout units (`RT-R1`..`RT-R7`) to use `driver-lab` in `checks.sh` / `publish.yml`, regenerate
   `.index.yaml` files and rendered views where affected by `BF-*` fixes, and verify all existing
   `.verify.yaml` records.

---

## 7. Acceptance criteria

1. **Single binary and conformance (`AC-1`)**: `cargo test --locked --offline` builds `driver-lab`
   and passes the full `tests/conformance/` corpus (including byte-for-byte `fact-v1` basis-hash
   parity) and mutation suite with zero active Python scripts remaining under `skills/`.
2. **Complete `BUGS-FOUND.md` coverage (`AC-2`)**: all 31 requirements (`BF-USB-1`..`BF-USB-4`,
   `BF-IMX-ISS-1`..`BF-IMX-ISS-7`, `BF-IMX-8`..`BF-IMX-18`, `BF-ARM-19`..`BF-ARM-21`, and
   `BF-GW-22`..`BF-GW-27`) have passing positive and negative conformance tests.
3. **Sandbox compliance (`AC-3`)**:
   - The zero-write read set passes inside `bwrap --ro-bind / / --unshare-net` (`ENV-1`).
   - `codex-review.py net` passes with `TMPDIR=<REVIEW_DIR>/tmp` (`ENV-2`).
   - `codex-implement.py` runs `driver-lab` and `cargo test --locked --offline` with zero refused
     files in `work/` (`ENV-3`).
   - `patch-gate.py` runs `cargo test --locked --offline` with an unchanged `worktree_digest` and
     guards the Rust and conformance gate inputs (`ENV-4`).
   - `driver-lab eval grade-code` sandboxes candidate test binaries with `bwrap` / `sandbox-exec`
     (`ENV-5`).
   - Release/CI binary bootstrap and `SKILL.md` `driver-lab --version` preflight checks pass
     (`ENV-6`).
4. **Repository policy and frozen archive checks (`AC-4`)**: `check-no-private-paths.py`,
   `check-open-side.py`, `check-no-hardware-facts.py`, and the frozen archive suites
   (`evals/enc28j60`, `evals/e1000`) all pass.
5. **Automation and model-tiering verification (`AC-5`)**: `resource pin-files|pin-doc`,
   `assemble`, two-phase `verify prepare --phase blind|claims`, `verify assemble` (with TOCTOU
   basis protection and `ADJUDICATE` construction), canonical register-source references, and the
   `CR6b` revision-8 calibration benchmark (`AUTO-1`..`AUTO-6`, `TIER-1`..`TIER-4`) pass their
   acceptance suites.
