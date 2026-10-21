<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Process audit trail and continuous streamlining for hardware-specs

**Revision:** 2026-10-21 (approved by the user on 2026-10-21; implementation plan:
[PROCESS-AUDIT-PLAN.md](../notes/plans/PROCESS-AUDIT-PLAN.md)).

## Purpose and scope

Verification records (`specs/resources/*.verify.yaml`) prove the state of a finished specification
at a pinned basis, but they do not record the **process cost** required to reach that state: how
many `hwspecs check` and `hwspecs resolve` edit cycles ran before the gate closed, which diagnostic
codes recurred across runs, whether failures came from specification defects or `hwspecs` tool bugs,
how many verifier rounds and standing-check failures occurred, or how many subagent runs and tokens
the campaign consumed.

During the Gateworks Catalina GW9200 Format 2 regeneration campaign (15 specs across three roots,
31 stale facts checked, 11 critical facts second-read), `spec-verifier` passed on the first round
with zero `FAIL` verdicts — yet four pre-verifier `hwspecs` tool defects (`#197`–`#200`) caused
repeated check and resolution cycles that left no trace in the verification records.

This document specifies the process audit trail and continuous streamlining loop for
`hardware-specs`:

1. Storage boundary, concurrency guarantees, and public-repository hygiene.
2. Two-phase `hwspecs` diagnostic capture (`utilities/hwspecs-audit` wrapper plus shared
   `Finding.code` and `--diag-out <FILE>` in the Rust CLI).
3. First-class metrics for pre-verifier gate churn and verifier rounds.
4. Multi-harness subagent and token telemetry across Claude Code, Codex, and out-of-band harness
   APIs.
5. Continuous streamlining triggers (`streamline_due.py`) and `Mistakes -> rules` foldback.

---

## 1. Storage architecture, concurrency, and public-repo hygiene

### Product vs. process separation

Published specification roots (`specs/`, `skills/board-expert/specs/`, and the external
`hardware-specs-docs`, `hardware-specs-permissive`, and `hardware-specs-gpl` repositories) hold
**product records only**:

- `.spec.yaml` and `.index.yaml` files,
- `corpus.yaml` and `board-specs.yaml` root manifests, and
- `resources/*.verify.yaml` verification records.

Process audit receipts, diagnostic captures, gate-transition markers, tool-issue records, and
subagent telemetry **never** live inside a spec root. They are written exclusively to the user's
private run store under `<run_store>/<campaign_run>/`, resolved via `utilities/run-store.py`
(`HWSPECS_RUNS`, `DRIVER_LAB_RUNS`, or `run_store` in `~/.config/hwspecs/config.toml`).

### Run-store directory layout

Within `<run_store>/<campaign_run>/`, files are partitioned so that `bringup-kit`'s execution
audit (`bringupkit/audit.py`, which globs `runs/*/*.json` and rejects any JSON file whose `schema`
is not `bringup-audit-1`) can validate and project `<run_store>/<campaign_run>/audit` directly without
colliding with `hwspecs`-specific receipts:

```text
<run_store>/<campaign_run>/
├── audit/
│   ├── runs/
│   │   └── <exec-id>/
│   │       ├── <start-id>.json          # schema: "bringup-audit-1" (kind: "start")
│   │       ├── <finish-id>.json         # schema: "bringup-audit-1" (kind: "finish")
│   │       ├── <model-id>.json          # schema: "bringup-audit-1" (kind: "model", optional)
│   │       └── <usage-id>.json          # schema: "bringup-audit-1" (kind: "usage", optional)
│   ├── hwspecs/
│   │   └── <event-id>-<subcmd>.json     # schema: "hwspecs-diag-1"
│   ├── gates/
│   │   └── <event-id>/
│   │       └── gate-clean.json          # schema: "hwspecs-gate-1"
│   ├── issues/
│   │   └── <event-id>/
│   │       └── tool-issue.json          # schema: "hwspecs-issue-1"
│   └── subagents.jsonl                  # Tier 1 harness-notice subagent log
└── review/
    └── <spec>-r<n>/
        ├── report.md                    # human-readable reviewer/verifier report
        └── verified.json                # schema: "hwspecs-verified-1"
```

### Collision-free `<event-id>` and atomic publication

Parallel workers and rapid sequential invocations can finish within the same second. Every receipt
and event directory uses a collision-free identifier:

```text
<event-id> := <YYYYMMDDTHHMMSSffffffZ>-<rand8>
```

where `<YYYYMMDDTHHMMSSffffffZ>` is the microsecond-resolution UTC timestamp and `<rand8>` is
eight lowercase hexadecimal characters from `os.urandom(4)`.

All JSON receipts are immutable once published and are written atomically:

1. Serialize the JSON object to a temporary `.pending-<uuid>` file in the target directory.
2. Flush and `os.fsync` the temporary file descriptor.
3. Publish the receipt via `os.link(tmp_path, final_path)` (hard link, which fails with `FileExistsError`
   rather than overwriting an existing file) and `os.unlink(tmp_path)`.
4. `os.fsync` the parent directory.

### Scrubbing and privacy invariants

Even though `<run_store>` is private, audit receipts may be summarized into public pull requests or
streamlining logs. `utilities/hwspecs-audit` enforces strict scrubbing before writing any receipt:

- **No raw `argv` or environment dumps**: receipts record the `hwspecs` subcommand (`check`,
  `resolve`, `status`, `validate`, `render`, `index`, `todo`, `prose-facts`) and scrubbed root
  identifiers, never raw command-line arguments.
- **No raw diagnostic prose**: receipts store stable `Finding.code` values or normalized template
  slugs, never raw error strings that could echo file paths or source snippets.
- **Root-relative paths only**: every `.spec.yaml` or finding path inside the target spec root is
  normalized to a root-relative POSIX path. Any path outside the spec root is replaced with
  `<external>:<sha256[:12]>`.
- **No home paths or hostnames**: any remaining `/home/<user>/` or `/Users/<user>/` substring is
  scrubbed so receipts and derived reports always pass `utilities/check-no-private-paths.py`.

---

## 2. Two-phase `hwspecs` diagnostic capture

### Phase 1: External wrapper (`utilities/hwspecs-audit`)

`utilities/hwspecs-audit` is a standalone, zero-dependency Python 3 wrapper around `hwspecs`.

```bash
export HWSPECS_AUDIT_RUN="<campaign_run>"
export HWSPECS_AUDIT_STEP="author-check"
utilities/hwspecs-audit -- target/release/hwspecs check <root> --require-license
```

Key design properties of `utilities/hwspecs-audit`:

- **Never mutates `argv` by default**: `hwspecs` has subcommand-specific output behavior when
  `--json` is injected (for example, `CheckReport.text_lines` carries `#[serde(skip)]` and
  `src/resolve.rs` strips `_text` from JSON output while `resolve` in text mode prints per-anchor
  progress and `N anchor(s) resolved, M skipped`). By default, `utilities/hwspecs-audit` runs the
  exact command the caller requested, tees `stdout` and `stderr` unchanged to the terminal, and
  parses the output stream in parallel.
- **Supports `--use-diag-out` when Phase 2 is available**: when `--use-diag-out` is passed, the
  wrapper creates a temporary path, passes `--diag-out <tmpfile>` to `hwspecs`, and reads the
  structured JSON payload from `<tmpfile>` while leaving `stdout` and `stderr` untouched.
- **Parses text and JSON findings**:
  - In text mode, matches `^(.+?):([0-9]+):([0-9]+): (error|warning): (.+)$` and `resolve` summary
    lines `^([0-9]+) anchor\(s\) resolved, ([0-9]+) skipped$`.
  - In JSON or `--diag-out` mode, reads structured `findings[]` objects directly.
- **Normalizes `(tool_commit, code_or_slug)`**:
  - When `finding["code"]` is present and non-empty (Phase 2), uses `finding["code"]` directly.
  - Otherwise (Phase 1 fallback), normalizes `message` into a deterministic template slug by
    replacing path-like tokens, single- and double-quoted strings, hexadecimal literals, and bare
    integers with placeholders before slugifying, and pairs it with `tool_commit` from
    `hwspecs --version`.
- **Hashes `.spec.yaml` files before and after execution**: records `spec_hashes_before` and
  `spec_hashes_after` (mapping root-relative `.spec.yaml` paths to SHA-256 digests) to measure edit
  cycles vs. no-op reruns.
- **Flags tool-bug candidates automatically**: sets `tool_bug_candidate: true` whenever `hwspecs`
  exits with code `100`, emits an `"internal-error"` JSON envelope, or panics on `stderr`.
- **Emits dual receipts**:
  1. Strict `bringup-audit-1` `start` and `finish` receipts in
     `audit/runs/<exec-id>/` (compatible with `bringupkit/audit.py`).
  2. A `hwspecs-diag-1` receipt in `audit/hwspecs/<event-id>-<subcmd>.json`:

```json
{
  "schema": "hwspecs-diag-1",
  "event_id": "20261021T220500000000Z-a1b2c3d4",
  "campaign_run": "gw9200-regen-20261021",
  "exec_id": "20261021T220500000000Z-a1b2c3d4",
  "step": "author-check",
  "attempt": "1",
  "subcmd": "check",
  "tool_commit": "c1d10d8",
  "started_at": "2026-10-21T22:05:00Z",
  "finished_at": "2026-10-21T22:05:01Z",
  "duration_ms": 842,
  "exit_code": 1,
  "errors": 2,
  "warnings": 0,
  "anchors_resolved": null,
  "anchors_skipped": null,
  "tool_bug_candidate": false,
  "finding_codes": {
    "c1d10d8:CHK-POLL-UNTIL": 2
  },
  "findings_by_spec": {
    "soc/cns3xxx.spec.yaml": {
      "errors": 2,
      "warnings": 0,
      "codes": ["CHK-POLL-UNTIL"]
    }
  },
  "spec_hashes_before": {
    "soc/cns3xxx.spec.yaml": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  },
  "spec_hashes_after": {
    "soc/cns3xxx.spec.yaml": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }
}
```

### Phase 2: Shared `Finding.code` registry and `--diag-out <FILE>`

To eliminate dependence on message-slug heuristics over time, the Rust `hwspecs` CLI provides two
native features:

1. **Deterministic `Finding.code` registry (`src/diagnostic.rs`, `src/records.rs`,
   `src/speccheck.rs`, `src/resolve.rs`)**:
   - Every `SpecFinding` emitted by `check`, `status`, or `validate` carries a stable, non-empty
     `CHK-*` code in JSON output (`classify_check_finding_code`), while its `Display` output
     remains `path:line:col: level: message`.
   - Every finding emitted by `resolve` carries a stable, non-empty `RES-*` code in JSON output
     (`classify_resolve_finding_code`).
2. **Global `--diag-out <FILE>` flag (`src/lib.rs`)**:
   - When `--diag-out <FILE>` is passed to `hwspecs check`, `hwspecs resolve`, or `hwspecs status`,
     `hwspecs` writes the structured JSON diagnostic report to `<FILE>` while keeping `stdout` and
     `stderr` in their default human-readable text format (`ENV-1` and `ENV-2` compliant).

---

## 3. First-class metrics for pre-verifier gate churn and verifier rounds

### Pre-verifier gate churn metrics

Most specification authoring effort happens *before* `spec-verifier` is launched, while closing
`hwspecs check` and `hwspecs resolve`. `utilities/hwspecs-audit report --run <campaign_run> [--json]`
computes four pre-verifier metrics from `audit/hwspecs/*.json` and `audit/issues/*/tool-issue.json`:

1. **`gate_edit_cycles` (per spec and per root)**:
   - The number of distinct `.spec.yaml` SHA-256 content hashes observed across failing (`errors > 0`)
     `check` or `resolve` runs up to the first clean run (`errors == 0`).
   - A spec that passes on the first check has `gate_edit_cycles = 0`. A spec that fails, is edited
     twice, and passes on the third check has `gate_edit_cycles = 2`.
2. **`noop_reruns`**:
   - The number of consecutive `check` or `resolve` invocations where `spec_hashes_before` is
     identical to the preceding invocation's `spec_hashes_after` and `tool_commit` did not change.
3. **Finding persistence**:
   - For each `(tool_commit, code_or_slug)`, the number of invocations and distinct edit cycles in
     which that code appeared before disappearing, highlighting rules where authors repeatedly
     struggle with schema or semantic constraints.
4. **Tool-defect separation (`record-issue`)**:
   - When a gate failure is caused by a defect in `hwspecs` or its schemas/scripts rather than a
     defect in the specification under authoring, the orchestrator records it via:

     ```bash
     utilities/hwspecs-audit record-issue \
       --run "<campaign_run>" \
       --issue "#197" \
       --subcmd check \
       --code CHK-PERIPHERAL-POLL \
       --summary "peripheral.rs poll step validation mismatch"
     ```

   - This writes `<run_store>/<campaign_run>/audit/issues/<event-id>/tool-issue.json` (`schema:
     "hwspecs-issue-1"`). `hwspecs-audit report` separates cycles and failures attributed to
     recorded tool issues (or `tool_bug_candidate: true` runs) from specification-authoring cycles.

### Coverage honesty

If any step ran outside `utilities/hwspecs-audit` or if token usage was not imported for a run or
subagent, `hwspecs-audit report` explicitly reports `"unknown"` (never `0`) for the missing metric
and includes a `coverage` block stating how many runs have complete diagnostic and usage receipts.

### Verifier round metrics (`verified.json`)

After each `spec-verifier` round on a spec, the orchestrator records a machine-readable round
summary via `utilities/hwspecs-audit record-verified`:

```bash
utilities/hwspecs-audit record-verified \
  --run "<campaign_run>" \
  --spec "cns3xxx" \
  --round 1 \
  --spec-sha256 "<sha256>" \
  --stale-checked 31 \
  --critical-second-read 11 \
  --verdict PASS=31 \
  --verdict FAIL=0 \
  --verdict UNVERIFIABLE=0 \
  --verdict GAP=0 \
  --verdict ADJUDICATE=0
```

This writes `<run_store>/<campaign_run>/review/<spec>-r<n>/verified.json` (`schema:
"hwspecs-verified-1"`). When `FAIL > 0`, `--fail-category <category>=<count>` classifies every
verifier `FAIL` across the **11 standing-check failure categories** from
[`skills/spec-verifier/SKILL.md`](../skills/spec-verifier/SKILL.md):

| Category key | Standing check in `spec-verifier` |
| --- | --- |
| `locator` | Missing locator, wrong passage, or nonexistent anchor at the pin |
| `precision` | Citation precision insufficient to repeat or establish the claim |
| `class` | Wrong support class (for example, `src` alone for hardware behavior requiring document support) |
| `derivation` | Derived conclusion placed in a read-class fact instead of `inference` with `premises` and `derivation` (D3) |
| `too-broad` | Claim drops a governing condition or asserts an exclusivity contradicted by the source |
| `enumeration` | Named finite encoding, opcode set, or bitmask omitted from `enumeratedValues`/`enumerationDefinitionRef`/bit fields without a `todo` (#103) |
| `bound` | Wait, poll, or handshake step missing its timeout bound and tolerance or `todo` (#105) |
| `layer` | Value reported to an OS framework (`target` fact) missing its unit, frame/payload layer, or interface citation (#150) |
| `duplicate` | Inline restatement of a canonical machine-readable source available under the root's license (D31, D32) |
| `todo-method` | Impossible `todo.method` or trailing `todo` used to cover unsupported assertions |
| `other` | Any other factual discrepancy between the claim and the cited source bytes |

---

## 4. Multi-harness subagent and token telemetry

`hardware-specs` campaigns run across multiple agent harnesses (Claude Code, Codex, and
Antigravity). Token and subagent telemetry follows a two-tier design with a
strict **one usage source per run** invariant.

### Single-source rule

For any execution run, at most one token usage source is counted in totals:

- If a validated Tier 2 `bringup-audit-1` `usage` receipt exists in `audit/runs/<exec-id>/`, its
  token buckets (`input`, `cache_read`, `cache_write`, `output`) are authoritative and supersede
  any Tier 1 `reported_tokens` estimate for that run.
- Tier 1 and Tier 2 numbers are never added together for the same run.
- If neither Tier 1 nor Tier 2 usage is recorded for a run, its token cost is reported as
  `"unknown"`, never `0`.

### Tier 1: Harness-notice subagent log (`audit/subagents.jsonl`)

Per `AGENTS.md` ("Transcripts"), agents must never copy, read, or hash harness transcript files
from the shell during an unattended run because touching the harness's protected state directory
triggers permission prompts. Instead, when a subagent finishes and returns its completion notice to
the orchestrator, the orchestrator logs the reported metadata via:

```bash
utilities/hwspecs-audit record-subagent \
  --run "<campaign_run>" \
  --role "spec-verifier" \
  --shard "cns3xxx-primary" \
  --model "claude-opus-4-6" \
  --reported-tokens 84210 \
  --reported-duration-ms 41200
```

Each line appended to `<run_store>/<campaign_run>/audit/subagents.jsonl` carries
`"provenance": "harness-notice"`.

### Tier 2: Out-of-band normalized usage receipts (`bringup-audit-1`)

At session close (or out-of-band after a worker exits), exact per-message token buckets can be
imported into `<run_store>/<campaign_run>/audit/runs/<exec-id>/` as `bringup-audit-1` `model` and
`usage` receipts (`semantics: "exclusive-message-buckets"`), using one of three supported
`provenance.adapter` values in `bringupkit/audit.py`:

| `provenance.adapter` | Source | Importer |
| --- | --- | --- |
| `"claude-jsonl-1"` | Completed Claude Code JSONL transcript | `bringupkit/audit.py import-usage --format claude --complete` |
| `"codex-jsonl-1"` | Completed Codex JSONL transcript | `bringupkit/audit.py import-usage --format codex --complete` |
| `"harness-api-1"` | Out-of-band harness usage CLI/API | User-local session-close usage importer |

For `"harness-api-1"` (an out-of-band harness usage CLI or API):

- Queries each conversation or session ID individually via the out-of-band harness usage CLI at
  session close, **never** requesting recursive subagent rollups (which would double-count child
  conversations alongside their individual runs).
- Verifies that the reported output total equals the sum of its reported components (e.g. reasoning
  + response) on every parsed conversation and refuses the import with a `ValueError` if the
  equality does not hold.
- Maps `Input -> input`, `Cache Read -> cache_read`, and `Output -> output`, sets
  `provenance.session_key = sha256(session_id).hexdigest()` from the session ID, and publishes
  `model` and `usage` receipts atomically via temp-file + `os.link`.

---

## 5. Continuous streamlining loop

### Event-scoped `run_id`s for `streamline_due.py`

[`bringup-kit/tools/streamline_due.py`](https://github.com/curtisgalloway/bringup-kit) checks
whether new round artifacts have been written since the last commit to the repository's
streamlining log (`notes/process-streamlining.md`). Internally, `streamline_due.py` deduplicates
discovered artifacts by calling `run_key(path)` (`lines 86–96`), which returns
`"id:" + str(doc["run_id"])` whenever a JSON artifact contains a non-empty `run_id` field.

If multiple artifacts in a campaign shared `"run_id": "<campaign_run>"`, `streamline_due.py` would
collapse every gate-close, verifier round, and tool issue in the campaign into a single round key.
Therefore, `utilities/hwspecs-audit` assigns a **unique per-event `run_id`** to each trigger
artifact while keeping `"campaign_run": "<campaign_run>"` as a separate top-level field:

| Trigger event | Artifact path under `<run_store>/<campaign_run>/` | `run_id` |
| --- | --- | --- |
| Gate closes after prior failure | `audit/gates/<event-id>/gate-clean.json` | `"<campaign_run>.gate.<event-id>"` |
| Verifier round completes | `review/<spec>-r<n>/verified.json` | `"<campaign_run>.<spec>.r<n>"` |
| Tool defect recorded | `audit/issues/<event-id>/tool-issue.json` | `"<campaign_run>.issue.<event-id>"` |

Notice that `gate-clean.json` is emitted by `utilities/hwspecs-audit` **only** when `hwspecs check`
or `hwspecs resolve` succeeds (`errors == 0`) after at least one prior failing (`errors > 0`)
`check`/`resolve` receipt for the same root in `<campaign_run>` since the last `gate-clean.json`. A
routine one-shot green check does not fire a streamlining pass.

### Runtime invocation

Because `<run_store>` is user-specific and never hardcoded in tracked files, callers resolve the
campaign directory at runtime via `utilities/run-store.py`:

```bash
python3 <bringup-kit-checkout>/tools/streamline_due.py \
  --repo <hardware-specs-checkout> \
  --log notes/process-streamlining.md \
  --brief notes/streamlining-pass-brief.md \
  --root "$(python3 utilities/run-store.py <campaign_run>)" \
  --name gate-clean.json \
  --name verified.json \
  --name tool-issue.json
```

### Method-level records and `Mistakes -> rules` routing

When `streamline_due.py` prints a due notice, the orchestrator launches a background streamlining
pass following [`notes/streamlining-pass-brief.md`](../notes/streamlining-pass-brief.md):

1. Run `utilities/hwspecs-audit report --run <campaign_run> --json` to gather pre-verifier
   `gate_edit_cycles`, `noop_reruns`, recurring `(tool_commit, code_or_slug)` counts, tool-defect
   issues, verifier round verdicts/categories, and subagent/token usage.
2. Recheck active streamlining changes (`S1`, `S2`, …) in
   [`notes/process-streamlining.md`](../notes/process-streamlining.md) and record a
   **Mistakes -> rules** table mapping every tool defect, recurring gate error, or verifier `FAIL`
   to a concrete rule, schema constraint, or `hwspecs` checker improvement.
3. Log autonomous orchestrator choices in
   [`notes/decision-audit-log.md`](../notes/decision-audit-log.md).
4. Commit `notes/process-streamlining.md` by path (`git commit -- notes/process-streamlining.md`)
   to reset the `streamline_due.py` trigger clock.
