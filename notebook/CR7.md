<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR7 notebook

**Terms:** a stand-in is an invented deployment; a reader handoff supplies a fresh
verification session with only its spec and authorities. See the
[glossary](../GLOSSARY.md). Conclusions and acceptance are in
[the evidence](../evidence/CR7.md).

## 2026-09-26T22:56:17-07:00 — automated checks and reader preparation

- The existing sweep needs no implementation change to run from a separate root.
  Its configured manifest and metadata-only source handling already provide the
  boundaries CR7 needs. Added test scaffolding around those commands.
- The CR5 contract stub reads a reduced QEMU fixture. Added a self-contained
  invented stub so the new deployment has no reference-backend dependency.
- Empty temporary uv caches had no PyYAML, and DNS blocked a download. An existing
  populated temporary cache supported the required command offline.
- The first scan's only overlap was the standard SPDX banner. Preserved that
  report and made derived inputs removing only the exact banners.
- Prepared the live workspace and queued reading; stopped before launching it,
  as the brief assigns the reading to the orchestrator.

## 2026-09-27T06:49:42-07:00 — live result integration

- The returned record's hashes and four stable keys validate. Its second source
  correctly says no edition is stated; the registry version is an operator label.
- Preserving the canned entries alongside the actual reading leaves the old
  source reading stale but removes it from queued work. The cap counts those
  three entries even though only the last is a live reading.
- The resumed sandbox removed write access to the run store. Prepared and checked
  a relocated copy and a private installation payload; kept its configuration
  change out of that payload so the original run-store setting stays correct.
- Kept the live record verbatim and the transcript untouched. Stopped before
  independent review; private update installation remains with the orchestrator.

## 2026-09-27T07:05:00-07:00 — installation (orchestrator's note)

- The orchestrator's harness blocked it from running the installer and the
  stand-in sweep (code generated outside the repository). The user ran both:
  `--check` reported 24 pending files, the install wrote 24, and the original
  stand-in's sweep reported sufficient, S1–S5 met, empty queue, one historical
  stale entry. Output saved in the private run as `post-install-sweep.txt`.
