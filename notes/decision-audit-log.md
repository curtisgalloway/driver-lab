<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Decision audit log — hardware-specs

**Terms:** a *decision audit log* records choices the orchestrator made on its own instead of
stopping to ask the user; a *safety boundary* is a check whose purpose is to prevent license,
isolation, or privacy defects rather than save time. See
[`docs/PROCESS-AUDIT.md`](../docs/PROCESS-AUDIT.md),
[`notes/process-streamlining.md`](process-streamlining.md), and the
[glossary](../docs/GLOSSARY.md).

Decide-and-log is the default for routine implementation and orchestration choices that have a
clear recommended option: the orchestrator takes the recommended option and records it here so the
user can inspect and reverse any entry later.

## Rules

- **Covered:** choices the orchestrator would otherwise have asked as a question with a recommended
  option: which review findings to fix first, fix ordering, worktree and history shape, tie-breaks
  between equivalent implementation approaches, subagent sharding, and retry versus stop after a
  transient failure inside an existing stop-rule budget.
- **Still asked, never decided here (safety boundaries):**
  - **License gate:** `--require-license` enforcement, root license rules in `board-specs.yaml`, or
    moving facts between `hardware-specs-docs`, `hardware-specs-permissive`, and
    `hardware-specs-gpl`.
  - **Read-only sandbox:** `bwrap --ro-bind / / --unshare-net` execution around `hwspecs` checks
    and untrusted specification inputs.
  - **Primary and second reader independence:** fresh `spec-verifier` reader contexts, independent
    second readers (`D14`) on `critical: true` facts, and user adjudication of `ADJUDICATE`
    disagreements (`spec-verifier` never votes or settles disagreements on its own).
  - **No private paths or restricted vocabulary:** `utilities/check-no-private-paths.py`,
    `utilities/check-open-side.py`, and `utilities/check-no-hardware-facts.py`, plus keeping all
    process audit artifacts in `<run_store>/<campaign_run>/` outside published spec roots.
  - **Outward actions and destructive operations:** pushing branches, opening or merging pull
    requests, filing issues without standing authorization, or any tier-2 campaign change that
    requires a recorded user decision per `AGENTS.md`.
- **Every entry records:** UTC ISO-8601 date and time (`YYYY-MM-DDTHH:MM:SSZ`) on new entries,
  decision title, actor (`orchestrator` or `*user*`), options considered with their consequences,
  the chosen option and reason, where it is applied, how to reverse it, and status (`active` or
  `reversed`).

## Entries

### D1 — 2026-10-21 — Store process audit receipts in `<run_store>/<campaign_run>/audit/` and streamline logs in `notes/` (*user* + orchestrator)

- **Options:**
  1. Write diagnostic and verification-round telemetry inside each spec root under `specs/`.
     Consequence: pollutes published spec repositories with process churn and risks leaking local
     run metadata.
  2. Write all machine-captured process receipts under `<run_store>/<campaign_run>/audit/` (with
     `bringup-audit-1` receipts isolated in `audit/runs/<exec-id>/` and `hwspecs-diag-1` receipts
     in `audit/hwspecs/`) and keep method-level streamlining records in `hardware-specs/notes/`.
     Consequence: `specs/` remains product-only, `bringupkit/audit.py` validates `audit/runs/`
     without schema collisions, and `streamline_due.py` tracks commits to
     `notes/process-streamlining.md`.
- **Picked:** Option 2, approved by the user on 2026-10-21 after cross-family architecture review.
- **Applied:** `docs/PROCESS-AUDIT.md`, `notes/plans/PROCESS-AUDIT-PLAN.md`,
  `utilities/hwspecs-audit`, and `AGENTS.md`.
- **Reverse:** Revert the `PA-1`–`PA-4` branches and remove `<run_store>/<campaign_run>/audit/`.
- **Status:** active.
