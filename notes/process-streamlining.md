<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Process streamlining log — hardware-specs

**Terms:** a *round* is one write -> review/verify -> repair cycle of a specification or tooling
unit; a *gate cycle* is one `hwspecs check` or `hwspecs resolve` edit cycle before verification; a
*streamlining pass* is one measured review of how the process ran since the last pass; a *safety
boundary* is a check whose purpose is to prevent license, isolation, or privacy defects rather than
save time. See [`docs/PROCESS-AUDIT.md`](../docs/PROCESS-AUDIT.md) and the
[glossary](../docs/GLOSSARY.md).

The orchestrator measures, improves, and, when a change makes things worse, reverts process changes
on its own, recording every step here for audit. Status values: `active`, `reverted`, `proposal`
(awaiting user approval).

## Safety boundaries (never weakened without user approval)

A streamlining pass may never weaken or bypass these boundaries on its own; any idea touching one
is logged as `proposal`:

- **License gate:** `--require-license` enforcement and per-root source license rules in
  `board-specs.yaml` (`hardware-specs-docs`, `hardware-specs-permissive`, `hardware-specs-gpl`).
- **Read-only sandbox:** `bwrap --ro-bind / / --unshare-net` execution around `hwspecs` checks and
  untrusted specification inputs.
- **Primary and second reader independence:** fresh `spec-verifier` reader contexts without prior
  conclusions, and an independent second reader (`D14`) on every `critical: true` fact.
- **No private paths or restricted vocabulary:** `utilities/check-no-private-paths.py`,
  `utilities/check-open-side.py`, and `utilities/check-no-hardware-facts.py`, plus keeping all
  process audit artifacts in `<run_store>/<campaign_run>/` outside published spec roots.
- **Outward actions:** pushing branches, opening or merging pull requests, or filing upstream
  issues without explicit standing authorization.

## Baseline

Measured on the Gateworks Catalina GW9200 Format 2 regeneration campaign (2026-10-21):

| Measure | Observed |
| --- | --- |
| Specifications regenerated (Format 2 across 3 roots) | 15 specs |
| Stale / unverified facts checked (`spec-verifier` primary reading) | 31 stale facts checked |
| Critical facts checked by an independent second reader (`D14`) | 11 critical facts second-read |
| Verifier rounds to reach zero `FAIL` / zero unsettled `ADJUDICATE` | 1 verifier round (0 verifier FAILs) |
| Pre-verifier `hwspecs` tool defects encountered during gate closure | 4 pre-verifier `hwspecs` tool defects (`#197`–`#200`) |
| Pre-verifier `gate_edit_cycles` and `noop_reruns` captured in structured receipts | `unknown` (ran before `utilities/hwspecs-audit` existed; motivated `PA-1`–`PA-5`) |

## Changes

### S1 — Add `utilities/hwspecs-audit` and `Finding.code` / `--diag-out` (`active`, 2026-10-21)

- **Observation:** During the GW9200 Format 2 regeneration campaign (15 specs, 31 stale facts
  checked, 11 critical facts second-read), `spec-verifier` completed in 1 verifier round with 0
  verifier FAILs, so the verification records (`resources/*.verify.yaml`) looked completely frictionless.
  In reality, closing the pre-verifier `hwspecs check` and `hwspecs resolve` gates hit 4
  pre-verifier `hwspecs` tool defects (`#197`–`#200`) and multiple edit/rerun cycles that left no
  structured trace outside transient terminal output.
- **Change:** Wrap `hwspecs` invocations in `utilities/hwspecs-audit` (`HWSPECS_AUDIT_RUN`,
  `HWSPECS_AUDIT_STEP`) to emit collision-free `bringup-audit-1` (`audit/runs/<exec-id>/`) and
  `hwspecs-diag-1` (`audit/hwspecs/<event-id>-<subcmd>.json`) receipts into
  `<run_store>/<campaign_run>/audit/`; add a shared `Finding.code` registry (`CHK-*`, `RES-*`) and
  global `--diag-out <FILE>` to `hwspecs`; and emit unique per-event `run_id` receipts for
  `gate-clean.json`, `verified.json`, and `tool-issue.json` so `bringup-kit/tools/streamline_due.py`
  triggers on pre-verifier gate closures, verifier rounds, and tool bugs alike.
- **Applied in:** `utilities/hwspecs-audit`, `src/diagnostic.rs`, `src/records.rs`,
  `src/speccheck.rs`, `src/resolve.rs`, `src/lib.rs`, `docs/PROCESS-AUDIT.md`,
  `notes/plans/PROCESS-AUDIT-PLAN.md`, and `AGENTS.md`.
- **Reverse:** Stop invoking `utilities/hwspecs-audit` in orchestrator runs and revert the `PA-1`–`PA-3`
  commits on `hardware-specs` (and `PA-4` on `bringup-kit`); existing spec roots are untouched
  because no audit files live under `specs/`.
- **Worse if:** Wrapping `hwspecs` alters `stdout`/`stderr` text formatting or exit codes (`ENV-1`
  / `ENV-2`), leaks any path into a spec root or fails `utilities/check-no-private-paths.py`,
  causes `bringupkit/audit.py doctor` to reject `<run_store>/<campaign_run>/audit`, or adds more
  than 100 ms of wrapper overhead per `hwspecs` invocation.

## Passes

| Date | Trigger | Rechecked | Reverted | Added |
| --- | --- | --- | --- | --- |
| 2026-10-21 | GW9200 Format 2 regeneration baseline & `PA-1`–`PA-5` rollout | — | — | `S1` |

### Pass 2026-10-21 — Mistakes -> rules

Interval: GW9200 Format 2 regeneration baseline through 2026-10-21 (`Mistakes → rules` /
`Mistakes -> rules`). Includes pre-verifier `hwspecs` tool defects (`#197`–`#200`), schema/checker
mismatches, and process visibility gaps discovered while regenerating the 15 GW9200 specs.

| Mistake and evidence | Existing rule (or none) | Action | Link |
| --- | --- | --- | --- |
| **Issue `#197`** (`i2c` `reg.bus` validation & `src/peripheral.rs` `op: poll` sequence step validation): during GW9200 Format 2 migration and check closure, `i2c` `reg.bus` validation and `src/peripheral.rs` (`check_step` checking `step.get("value")` instead of `step.get("until")`) contradicted `skills/spec-format/schema/spec.schema.json`, making valid Format 2 payloads fail `hwspecs check`. | `skills/spec-format/SKILL.md` and `spec.schema.json` define the Format 2 payload contract, but `src/peripheral.rs` / checker rules diverged from the JSON Schema. | Filed `#197`, aligned Rust semantic checks with `spec.schema.json`, and added `CHK-*` diagnostic codes plus `hwspecs-audit record-issue` so schema-vs-checker contradictions are tracked as tool defects rather than spec-authoring churn. | [Issue #197](https://github.com/curtisgalloway/hardware-specs/issues/197), `S1` |
| **Issue `#198`** (cross-repo `overlay_target` in `corpus.yaml` & `skills/spec-format/ci/checks.sh` symlinked `--repo` path resolution): cross-repo overlay resolution across `hardware-specs-docs`, `hardware-specs-permissive`, and `hardware-specs-gpl` (`overlay_target` in `corpus.yaml` and symlinked `cache/<name>` checkouts passed to `hwspecs resolve --repo`) failed with usage/resolution errors because `check_dir_path` rejected symlinks that `checks.sh` passed uncanonicalized. | `SPEC-FORMAT.md` permits cross-repo overlays and shared local repo caches (`spec-verifier` input reuse), but `checks.sh` did not canonicalize symlinked cache paths with `pwd -P`. | Filed `#198`, updated `checks.sh` path canonicalization and cross-repo overlay handling, and added `RES-*` diagnostic codes in `hwspecs resolve`. | [Issue #198](https://github.com/curtisgalloway/hardware-specs/issues/198), `S1` |
| **Issue `#199`** (`status --stale` semantic basis hash vs `review_invalidated: false` & `hwspecs index`/`render` legacy `spec.py` banners): running `hwspecs status --stale` during Format 2 migration flagged 31 facts whose semantic basis hash changed (even where `review_invalidated: false` was set on format-only migration commits), and `hwspecs index` / `hwspecs render` still emitted legacy `Generated by spec.py ...` banners after the `RT-12` Rust cutover. | `spec-verifier` step 2 requires re-reading every `stale` fact whose computed `basis` differs from `recorded`, and `RT-12` cut over all CLI banners from `spec.py` to `hwspecs`. | Filed `#199`, performed full fresh primary readings on all 31 stale facts plus independent second readings on 11 critical facts, and tracked `stale_checked` and `critical_second_read` in `verified.json` via `hwspecs-audit record-verified`. | [Issue #199](https://github.com/curtisgalloway/hardware-specs/issues/199), `S1` |
| **Issue `#200`** (`todo` item `tracking` requirement during migration & `skills/spec-format/schema/index.schema.json` `section.level` `maximum: 6` mismatch): migrating Format 1 `todo` items and `.index.yaml` files exposed schema/checker discrepancies (`todo` item `tracking` field handling during migration and `index.schema.json` omitting `"maximum": 6` on `section.level` while `src/index.rs:1481` enforced `1..=6`). | `skills/spec-format/SKILL.md` states `section.level` is `1` to `6` and defines `todo` fields, but `index.schema.json` lacked the upper bound. | Filed `#200`, added `"maximum": 6` to `index.schema.json`, and added `utilities/hwspecs-audit` (`S1`) so pre-verifier schema/checker mismatches are captured on first occurrence. | [Issue #200](https://github.com/curtisgalloway/hardware-specs/issues/200), `S1` |
