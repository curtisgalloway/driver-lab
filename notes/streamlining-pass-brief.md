<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Streamlining pass brief (background agent) — hardware-specs

**Terms:** a *streamlining pass* is one measured review of how specification authoring, checking,
and verification ran since the last pass; a *gate cycle* is one `hwspecs check` or
`hwspecs resolve` edit cycle before verification; a *round* is one `spec-verifier` or code-review
cycle. See [`docs/PROCESS-AUDIT.md`](../docs/PROCESS-AUDIT.md),
[`notes/process-streamlining.md`](process-streamlining.md), and the
[glossary](../docs/GLOSSARY.md).

You run one streamlining pass as a non-blocking background task. The orchestrator continues working
on the main campaign; do not block it or message it except for your final report.

## Trigger command (reference)

The orchestrator or hook checks whether a pass is due with:

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

## Procedure

1. **Read context and safety boundaries.** Read `AGENTS.md`, `docs/PROCESS-AUDIT.md`,
   `notes/process-streamlining.md` (the safety boundaries it lists are binding: license gate
   `--require-license`, `bwrap --ro-bind / / --unshare-net` read-only sandbox, primary and second
   reader independence, and no private paths or restricted vocabulary),
   `notes/decision-audit-log.md`, and the campaign facts the orchestrator supplied in your prompt.
2. **Measure what happened since the last pass.** Use numbers from the audit trail, never
   impressions:
   - Run `git log` since the last commit touching `notes/process-streamlining.md`.
   - Run `utilities/hwspecs-audit report --run <campaign_run> --json` to measure per-spec
     `gate_edit_cycles`, `noop_reruns`, recurring `(tool_commit, code_or_slug)` diagnostic codes,
     recorded `hwspecs` tool defects (`audit/issues/*/tool-issue.json`), verifier round verdicts and
     standing-check failure categories (`review/<spec>-r<n>/verified.json`), and wrapper/usage
     coverage (`unknown` when uncaptured, never `0`).
   - When transcript or `bringup-audit-1` usage receipts are available, run:

     ```bash
     python3 <bringup-kit-checkout>/tools/agent_usage.py \
       --audit-dir "$(python3 utilities/run-store.py <campaign_run>)/audit" \
       --since <last_pass_iso> \
       --json <scratch>/usage.json
     ```

3. **Recheck active changes (`S1`, `S2`, …).** Compare each active change in
   `notes/process-streamlining.md` against the new measurements: keep, amend, or revert with
   explicit numbers. Add a new `S<n>` entry only with all five required fields (`Observation:`,
   `Change:`, `Applied in:`, `Reverse:`, `Worse if:`). Anything that touches a safety boundary is
   logged as `proposal`, never applied unilaterally. When enough samples exist across two passes,
   run `python3 <bringup-kit-checkout>/tools/streamline_regress.py` to check whether recent changes
   improved or regressed normalized cost and round counts.
4. **Route general improvements to their owning repository.** For every recurring diagnostic code,
   schema/checker mismatch, skill ambiguity, or tool gap found in the interval:
   - Map `hwspecs` CLI, schema, or skill improvements to `hardware-specs`.
   - Map shared execution-audit or streamlining-tool improvements to `bringup-kit`.
   - Search existing issues first, scrub all private paths and hostnames, and link the issue from
     the log entry (or record the drafted issue text as `proposal` when filing is not authorized).
5. **Append `Pass <date> — Mistakes -> rules` and update the `Passes` table.** In
   `notes/process-streamlining.md`, add a row to `## Passes` and a section
   `### Pass <date> — Mistakes -> rules` covering every pre-verifier tool issue, recurring gate
   failure, verifier `FAIL` category, user correction, or escaped defect since the last pass:
   mistake with evidence, existing rule (or `none`), action taken, and link. If an interval had no
   mistakes, record `none` explicitly.
6. **Verify hygiene and commit `notes/process-streamlining.md` by path.** Before committing, run:

   ```bash
   python3 utilities/check-no-private-paths.py
   python3 utilities/check-open-side.py
   python3 utilities/check-no-hardware-facts.py
   ```

   Then commit only the streamlining log by path so you never sweep up staged work:

   ```bash
   git commit -m "driver-porting: streamline — pass <date>" -- notes/process-streamlining.md
   ```

   Never push unless explicitly authorized in the current session.
7. **Report in at most 8 lines:** pass date, campaign run measured, `gate_edit_cycles` and verifier
   rounds observed, changes kept/reverted/added, `Mistakes -> rules` items recorded, any
   `proposal` items for the user, hygiene check results, and the commit SHA.
