---
name: spec-format
description: >-
  Reference skill, not user-invocable: spec format 2, the YAML format for board specs, SoC,
  chip and IP specs, overlays and the investigator's facts files, with its JSON Schemas, its one
  strict YAML loader and the spec.py command line. Read by the spec skills; the contract text
  arrives in milestone SF2-8, and until then the design document is the contract.
---

<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# spec-format (reference)

Spec format 2 stores each fact as a YAML record with a stable id and its citations as
structured fields, validated by JSON Schemas; Markdown becomes a view built from the YAML. The
contract is the approved design, [docs/SPEC-FORMAT-V2.md](../../docs/SPEC-FORMAT-V2.md)
(decisions D1–D22), until milestone SF2-8 writes it here; the build order is
[docs/SPEC-FORMAT-V2-PLAN.md](../../docs/SPEC-FORMAT-V2-PLAN.md). The skills still read format 1
(`board-expert/SPEC-FORMAT.md`) until the spec repositories cut over (SF2-11).

What exists so far (SF2-1, SF2-2):

- `scripts/specload.py`: `load_strict(path)`, the one loader every format 2 tool uses (the
  design's loader table: four plain-scalar types, integers within 64 bits, no anchors,
  aliases, merge keys, tags or directives, one document, unique string keys, no invisible or
  control characters anywhere in the file (a lone CR and NEL included; CRLF is fine), NFC,
  UTF-8 without a BOM).
- `schema/spec.schema.json` (kinds `board`, `soc`, `chip`, `ip`, `overlay`, `facts`),
  `schema/root.schema.json` (`board-specs.yaml` with `format: 2`) and
  `schema/verify.schema.json` (`resources/<name>.verify.yaml`).
- `scripts/spec.py validate <file>... [--root <dir>] [--json]`; `spec.py --skill` prints how
  to drive it. Exit 0 valid, 1 invalid, 2 usage, 3 a pinned dependency missing, 100 an internal
  error.
- `scripts/spec.py check <root>... [--context-root <dir>]... [--require-license]
  [--public-skill <name>]... [--stub <SKILL.md>]... [--stubs-from <dir>]... [--json]`
  (`scripts/speccheck.py`): discovers every `*.spec.yaml` below each root, validates it, then
  checks names, ids, composition, overlays, the three reference forms with layer order and no
  premise cycles, and the license gate direct and through references (D1, D12, D13). Findings in
  a `--context-root`'s own files are warnings. Exit 0 no error, 1 an error, 2 usage, 3 a missing
  marker or dependency, 100 internal.
- `scripts/specmd.py`: the one CommonMark parse (markdown-it-py), used so far only to find text
  outside code for the placeholder check; SF2-4 adds the D20–D22 checks there.
- `requirements.txt`: PyYAML, jsonschema and markdown-it-py with their dependencies, pinned by
  hash. Install with `pip install --require-hashes -r skills/spec-format/requirements.txt`.
