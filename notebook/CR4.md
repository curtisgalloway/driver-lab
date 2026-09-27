<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR4 notebook

**Terms:** a stopping report evaluates the campaign's scope; a queue lists work
without running it. See the [glossary](../GLOSSARY.md). Conclusions and acceptance
are in [the evidence](../evidence/CR4.md); commands and attempts are in run
`cr4-20260926-01`.

## 2026-09-26T19:59:33-07:00 — Reading the coverage boundary

CR2's explicit warning about the missing every-open line matters as much as
CR3's qualification staleness. Built the stopping calculation over the existing
freshness report; retained reading scopes and immutable bases. The synthetic
sufficient case exposed the need to let current coverage discharge old stale
history without changing the old records. Acceptance/transfer gates do not become
accuracy work merely because their historical identity is stale.

## 2026-09-26T20:03:00-07:00 — Guard and metadata checks

Added separate tests for every tier-2 action, missing versus operator versus user
decisions, repeated sweeps and new readers on sufficient campaigns. The old tests
that rejected unknown nonempty rules/classes now test malformed empty values;
new tests exercise the conservative policy/class behavior. Compacting the scope's
repeated class lists initially collided with an older YAML anchor; naming the new
anchor explicitly fixed the parse errors without changing existing anchors.

Round-three handling now holds additional readings before a fourth can be
proposed; historical overruns remain visible. The command logger and final checks
are the last implementation steps. Independent review belongs to the orchestrator.

## 2026-09-26T20:05:58-07:00 — Verification artifacts

The required checks completed; outputs and exact exits are in `VERIFY.txt`.
The last guard cases cover claim-status impact even when an item also names a
tier-2 action, and routing a hardware conflict to re-verification rather than
an unchanged emulator rerun. No queued work or independent review was launched.

## 2026-09-26T20:18:50-07:00 — Orchestrator-directed review fixes

The supplied seven-arm swarm and referee left eight approved fixes. New tests
reproduced the class-history mismatch, unrecorded review-item impact and unchanged
JSON version before code changes. Test fixtures now explicitly isolate unrelated
review impact; the real index keeps its missing declarations visible. Verification
artifacts go to temporary scratch storage because the run directory is read-only.
The evidence file records each disposition and the resulting report change.
