<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SF2-7a — Peripheral specs and facts files in format 2

**Terms:** a payload is a fact's structured register, sequence or byte layout; a pin names
an immutable source commit; a sub-key names a supported field or step's separate verdict.
See the [glossary](../GLOSSARY.md). Plan: [SF2-7](../docs/SPEC-FORMAT-V2-PLAN.md#sf2-7--peripheral-specs-reviews-and-facts-files-in-format-2).
Run: `sf2-7a-20261009-01`. Reviews and HTML generation belong to separate units.

## 2026-10-09T19:23:01-07:00 — Implementation and first checks

- The license matrix already had 15 format 2 copies using the IP kind. They now use the
  peripheral kind, with the same expected exit codes; format 1 tools remain available.
- Nested support needs the same citation traversal as top-level support, including the
  license gate, references, resolution and basis hashes. Separately supported register
  fields and sequence steps get sub-keys; their bases also depend on the parent fact.
- C integer suffix removal must match numbers, not identifiers: a broad suffix regex
  truncated `CTRL`. The named-constant parser test now covers that case.
- The first mutation pass found a test that never moved HEAD and tests that indexed
  missing sub-keys before asserting their existence. The tests now move HEAD, retain the
  older pin, and assert presence before reading a record. Header membership uses the
  resolver's existing closed-file rule before source access.
- Both safety-check command defaults require a Git index. This export has none; the
  same scan functions were run with an explicit list of regular exported files.

## 2026-10-09T19:32:15-07:00 — Mutation qualification finished

- The remaining surviving mutation exposed an invalid control: the SoC fixture includes
  extension-class support and needs its root marker during validation. The test now
  validates each unchanged control first, with that marker, before adding a forbidden
  payload or requirement. Every mutation qualifies through assertion failures.
- The patch collector flags four empty directories reserved read-only by the harness;
  no authored file is refused. The orchestrator needs that collector detail in its ledger.
