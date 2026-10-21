<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Process audit trail — implementation plan

Design: [PROCESS-AUDIT.md](../../docs/PROCESS-AUDIT.md), approved by the user on 2026-10-21.
Streamlining log: [process-streamlining.md](../process-streamlining.md); decision log:
[decision-audit-log.md](../decision-audit-log.md); pass brief:
[streamlining-pass-brief.md](../streamlining-pass-brief.md).
Project checks: the full list in [AGENTS.md](../../AGENTS.md#checks), plus the unit and
integration suites added by this plan.

## Goal

Add a structured, privacy-scrubbed process audit trail and continuous streamlining loop to
`hardware-specs` so that specification authoring and regeneration campaigns measure both
**pre-verifier gate churn** (`hwspecs check` and `hwspecs resolve` edit cycles, recurring diagnostic
codes, and `hwspecs` tool defects) and **verifier round outcomes** (`spec-verifier` rounds,
standing-check failure categories, and multi-harness subagent/token cost), feeding directly into
`bringup-kit`'s execution audit (`bringupkit/audit.py`) and streamlining trigger
(`tools/streamline_due.py`) while keeping specification roots strictly limited to product records.

## Requirements summary

| ID | Requirement | Verification |
| --- | --- | --- |
| **R1 (Clean Spec Root & Run-Store Layout)** | Keep `specs/` strictly limited to product records (`.spec.yaml`, `.index.yaml`, `corpus.yaml`, `board-specs.yaml`, `resources/*.verify.yaml`). Store all process audit artifacts under `<run_store>/<campaign_run>/audit/` with `bringup-audit-1` receipts isolated in `audit/runs/<exec-id>/*.json` and `hwspecs-diag-1` receipts in `audit/hwspecs/<event-id>-<subcmd>.json`. | `utilities/tests/test_hwspecs_audit.py` + `bringupkit/audit.py doctor` |
| **R2 (Collision-Free Atomic Receipts & Scrubbing)** | Use `<utc-compact>-<rand8>` `<event-id>`s published via temporary file + `os.link` (no-overwrite). Scrub all paths to spec-root-relative and never store raw `argv`, raw error message strings, home directory paths, or hostnames in receipts. | `utilities/tests/test_hwspecs_audit.py` + `utilities/check-no-private-paths.py` |
| **R3 (Phase 1 Wrapper `utilities/hwspecs-audit`)** | External Python 3 wrapper (standard library only) supporting `--run` / `HWSPECS_AUDIT_RUN` and `--step` / `HWSPECS_AUDIT_STEP`. Never mutates `argv` by default; tees `stdout`/`stderr` unchanged; parses text findings (`path:line:col: level: message`) and `resolve` summary lines (`N anchor(s) resolved, M skipped`), or JSON when `--json` / `--use-diag-out` is used. Records before/after `.spec.yaml` SHA-256 hashes, `(tool_commit, code_or_slug)` histograms, `bringup-audit-1` `start`/`finish` receipts, and auto-flags exit `100` / `internal-error` / panic as tool-bug candidates. | `python3 -m unittest discover -s utilities/tests` |
| **R4 (Phase 2 Shared `Finding.code` & `--diag-out <FILE>`)** | Populate a deterministic, non-empty `code` field on every `SpecFinding` (`src/records.rs`, `src/speccheck.rs`) and `resolve` finding (`src/resolve.rs`) in `hwspecs` JSON output, backed by a shared classifier/registry in `src/diagnostic.rs`. Add global `--diag-out <FILE>` to `hwspecs` (`src/lib.rs`) to emit the structured JSON report to `<FILE>` while keeping `stdout`/`stderr` in human-readable text mode (`ENV-1`/`ENV-2` compliant). | `cargo test --locked --offline` |
| **R5 (Gate Edit Cycles, Verifier Rounds, & Coverage Honesty)** | `hwspecs-audit report --run <campaign_run> [--json]` computes per-spec `gate_edit_cycles`, `noop_reruns`, finding persistence, tool-defect vs. spec-defect attribution (`audit/issues/<event-id>/tool-issue.json`), verifier round tallies (`review/<spec>-r<n>/verified.json` with all 11 standing-check `FAIL` categories), and explicit wrapper/usage coverage (`unknown`, never `0`, when uncaptured). | `utilities/tests/test_hwspecs_audit.py` |
| **R6 (Streamlining Triggers & Method Foldback Docs)** | Emit unique per-event `run_id`s (`<campaign_run>.gate.<event-id>`, `<campaign_run>.<spec>.r<n>`, `<campaign_run>.issue.<event-id>`) with `campaign_run` separate so `bringup-kit/tools/streamline_due.py` triggers on every gate-close, verifier round, and tool bug. Initialize `docs/PROCESS-AUDIT.md`, `notes/plans/PROCESS-AUDIT-PLAN.md`, `notes/process-streamlining.md` (with GW9200 `#197`–`#200` baseline), `notes/decision-audit-log.md`, `notes/streamlining-pass-brief.md`, and update `AGENTS.md` ("Records, one job each"). | `streamline_due.py` integration test + `check-open-side.py` + `check-no-private-paths.py` |
| **R7 (Multi-Harness Usage & `harness-api-1` Adapter)** | Add `"harness-api-1"` to allowed `provenance.adapter` values in `bringup-kit/bringupkit/audit.py` with tests and documentation. Provide a user-local session-close usage importer that imports per-conversation token buckets (`Input -> input`, `Cache Read -> cache_read`, `Output -> output`), verifies that the reported output total equals the sum of its reported components (e.g. reasoning + response), never requests recursive subagent rollups, and enforces one usage source per run. | `pytest` in `bringup-kit` + importer unit tests |

## Milestones

| # | Milestone | Kind | Owned files | Design coverage | Status |
| --- | --- | --- | --- | --- | --- |
| PA-1 | `utilities/hwspecs-audit` wrapper, subcommands, and unit tests | code | `utilities/hwspecs-audit`, `utilities/tests/test_hwspecs_audit.py` | R1, R2, R3, R5, R6 | complete |
| PA-2 | Rust CLI `Finding.code` unification and `--diag-out <FILE>` | code | `src/lib.rs`, `src/diagnostic.rs`, `src/records.rs`, `src/speccheck.rs`, `src/resolve.rs`, `src/stubgen.rs`, `tests/diag_out_and_codes.rs` | R4 | complete |
| PA-3 | Design doc, plan, streamlining log, templates, skill wiring, and `AGENTS.md` | docs | `docs/PROCESS-AUDIT.md`, `notes/plans/PROCESS-AUDIT-PLAN.md`, `notes/process-streamlining.md`, `notes/decision-audit-log.md`, `notes/streamlining-pass-brief.md`, `AGENTS.md`, `notes/README.md`, `skills/board-spec-scaffold/SKILL.md`, `skills/peripheral-spec/SKILL.md`, `skills/spec-verifier/SKILL.md` | R1, R6 | complete |
| PA-4 | `bringup-kit` `harness-api-1` adapter and local usage importer | code | `bringup-kit`: `bringupkit/audit.py`, `docs/execution-audit.md`, `tests/test_audit.py`; user-local session-close usage importer | R7 | complete |
| PA-5 | Independent verification, integration branch, and full gate suite | gate | Read-only verification across all worktrees + integration branch `process-audit/pa-integrated` | R1–R7 | complete |

## Milestone details

### PA-1 — `utilities/hwspecs-audit` wrapper, subcommands, and unit tests

- **Scope:** implement `utilities/hwspecs-audit` (Python 3 standard library only) supporting `run`
  (default when `--` is passed), `record-issue`, `record-verified`, `record-subagent`, and `report`.
- **Key invariants:**
  - Resolves `<run_store>/<campaign_run>` using `utilities/run-store.py` lookup order
    (`HWSPECS_RUNS`, `DRIVER_LAB_RUNS`, or `~/.config/hwspecs/config.toml`).
  - Publishes all JSON receipts atomically via temporary file + `os.link` using
    `<YYYYMMDDTHHMMSSffffffZ>-<rand8>` `<event-id>`s.
  - Never mutates `argv` unless `--use-diag-out` is passed; tees `stdout` and `stderr` unchanged.
  - Scrubs all paths to spec-root-relative (or `<external>:<sha256[:12]>`) and omits raw `argv`,
    raw diagnostic prose, home paths, and hostnames.
  - Emits `audit/gates/<event-id>/gate-clean.json` when `check` or `resolve` reaches `errors == 0`
    after at least one prior failing `check`/`resolve` receipt for the same root since the last
    `gate-clean.json`.
- **Verification:** `python3 -m unittest discover -s utilities/tests`.

### PA-2 — Rust CLI `Finding.code` unification and `--diag-out <FILE>`

- **Scope:** add deterministic `CHK-*` and `RES-*` rule codes to `src/diagnostic.rs`, `SpecFinding`
  (`src/records.rs`, `src/speccheck.rs`), and `resolve` JSON output (`src/resolve.rs`), plus global
  `--diag-out <FILE>` on `Cli` (`src/lib.rs`).
- **Key invariants:**
  - Human-readable text output (`path:line:col: level: message`) and exit codes (`ENV-1`, `ENV-2`)
    remain unchanged.
  - Every JSON finding object emitted by `check`, `status`, `validate`, or `resolve` carries a
    non-empty `code` string.
  - `--diag-out <FILE>` writes the structured JSON diagnostic report to `<FILE>` while leaving
    `stdout` and `stderr` in text mode.
- **Verification:** `cargo test --locked --offline`.

### PA-3 — Design doc, plan, streamlining log, templates, skill wiring, and `AGENTS.md`

- **Scope:** write [`docs/PROCESS-AUDIT.md`](../../docs/PROCESS-AUDIT.md), this plan,
  [`notes/process-streamlining.md`](../process-streamlining.md) (seeded with the GW9200 Format 2
  regeneration baseline and `Pass 2026-10-21 — Mistakes -> rules` for issues `#197`–`#200` and
  change `S1`), [`notes/decision-audit-log.md`](../decision-audit-log.md), and
  [`notes/streamlining-pass-brief.md`](../streamlining-pass-brief.md); wire `utilities/hwspecs-audit`
  and `verified.json` into [`skills/board-spec-scaffold/SKILL.md`](../../skills/board-spec-scaffold/SKILL.md),
  [`skills/peripheral-spec/SKILL.md`](../../skills/peripheral-spec/SKILL.md), and
  [`skills/spec-verifier/SKILL.md`](../../skills/spec-verifier/SKILL.md); update
  [`AGENTS.md`](../../AGENTS.md) ("Records, one job each") and [`notes/README.md`](../README.md).
- **Verification:** `python3 utilities/check-no-private-paths.py`,
  `python3 utilities/check-open-side.py`, and `python3 utilities/check-no-hardware-facts.py`.

### PA-4 — `bringup-kit` `harness-api-1` adapter and local usage importer

- **Scope:** add `"harness-api-1"` to the allowed `provenance.adapter` set in
  `bringup-kit/bringupkit/audit.py`, document it in `bringup-kit/docs/execution-audit.md`, add unit
  tests in `bringup-kit/tests/test_audit.py`, and provide the user-local session-close usage
  importer for out-of-band harness usage CLIs.
- **Verification:** `pytest` in `bringup-kit` plus unit tests for the session-close usage importer.

### PA-5 — Independent verification, integration branch, and full gate suite

- **Scope:** verify `PA-1` through `PA-4` in an independent verifier context, merge `PA-1`, `PA-2`,
  and `PA-3` into `process-audit/pa-integrated`, run the full `AGENTS.md` check suite, and run an
  end-to-end smoke test of `utilities/hwspecs-audit` with `target/release/hwspecs`,
  `bringupkit/audit.py`, and `tools/streamline_due.py`.
