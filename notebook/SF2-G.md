<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF2-G — Whole-outcome gate

**Terms:** format 2 stores cited facts as YAML records; a pin is the driver-lab commit a spec
repository's workflows run; upstream-stale is a verdict staled only by another repository's
fact. See the [glossary](../GLOSSARY.md).

Plan: [SF2-G](../docs/SPEC-FORMAT-V2-PLAN.md#sf2-g--whole-outcome-gate).
Run: `sf2-g-20261010-01`. Starting revision: `59df6e1` (origin/main), worktree clean. Fresh
clones of driver-lab and the three spec repositories in a scratch directory; commands and
outputs are in the run ledger.

### 2026-10-10T10:05-07:00 — the repositories still run an older tool

All six workflow pins in the three spec repositories name driver-lab `b86af093`, 27 commits
behind `main`: it predates SF2-7a, SF2-7b, SF2-9 and SF2-12. Every `checks.sh all` run passed
with that pin and with `main`, in both modes. Rendering with `main` adds verifier and
second-reader lines to the viewer, so the published sites are a version behind (G5).

### 2026-10-10T10:20-07:00 — the worked example holds on the published specs

The cross-root inference, its `upstream` map and the carried verdicts read as the design says.
One added word in docs' `addressing-model`, on a local branch, staled exactly one gpl fact:
an error in pull-request mode, a warning in `main` mode. Reordering keys and adding a comment
staled nothing. The published files differ from the design's slice where SF2-10 chose to:
`gic-node` is not `critical`, and the split facts already carry verdicts.

### 2026-10-10T10:30-07:00 — a long path breaks the suite

The checks list in the fresh clone, which sits under the system temp directory, failed 9
`spec-format` tests and 1 `utilities` test. The `spec-format` failures are the SF2-2 nit about
untrusted-root messages: the 200-character cut counted the path, so a deep path left no reason
text to match. The `utilities` failure is a test that takes the checkout's own `README.md` as a
brief "outside temp". CI's short path hides both. Fixed the first (cut the message, not the
location); reported the second (G2).

### 2026-10-10T10:40-07:00 — the gate's own checks need care to mean anything

The first viewer run reported 204 violations, all from my script: the page's own `<style>` in
`<head>`, and refusals that print their diagnostics on stdout. My first injection target, an
inference premise's `states`, was refused by the schema every time, so it tested nothing; a
verification note replaced it. A gate script that always refuses or always passes checks
nothing; count the outcomes per target before trusting it.

### 2026-10-10T10:50-07:00 — coverage: a branch with no test

A read-only mapping of the design's 22 validation rows to tests found a test for 21. The
missing one is an `instances[].ip` that names no spec. Only the wrong-kind branch was tested.
Added a bad-root fixture, and checked that removing the branch fails the test. The Resources
row's "non-https URL" had no plain `http://` case; added it.

### 2026-10-10T11:00-07:00 — draft checkpoint

Evidence drafted ([SF2-G](../evidence/SF2-G.md)). The plan's status stays pending until the
review (`review-swarm` and a Codex `ro` review) has run.
