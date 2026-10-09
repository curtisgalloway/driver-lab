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

What exists so far (SF2-1 to SF2-3):

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
  [--public-skill <name>]... [--stub <SKILL.md>]... [--stubs-from <dir>]...
  [--require-verified pr|main] [--json]`
  (`scripts/speccheck.py`): discovers every `*.spec.yaml` below each root, validates it, then
  checks names, ids, composition, overlays, the three reference forms with layer order and no
  premise cycles, and the license gate direct and through references (D1, D12, D13). Findings in
  a `--context-root`'s own files are warnings. Exit 0 no error, 1 an error, 2 usage, 3 a missing
  marker or dependency, 100 internal. The license gate fails closed: a reference may only rest on a
  root that checks clean. A root with any error of its own (before context downgrading) is
  untrusted, and every reference into it, direct or transitive, is an error on the citing file;
  so is a reference that dangles or is ambiguous, and, while any marker is unreadable, every
  root-qualified reference. A template placeholder is `<`, a letter, then letters, digits,
  spaces, `-` or `_`, then `>`, outside code; an extension fragment may not declare the citation
  fields `repo`, `path`, `doc`, `anchors`, `lines`, `symbol`, `node`, `url`.
- Verification records (`scripts/records.py`, SF2-3): `<root>/resources/<name>.verify.yaml`
  belongs to `<name>.spec.yaml`; `check` requires its `spec` and `spec_file` to name that file,
  every verdict key to name one of its facts, instances or variants, `summary` to count the
  verdicts, GAP only for gap facts, readers agreeing with the verdict, and a current verdict's
  `upstream` map to match. Each verdict is current, stale, upstream-stale, unverified or unknown
  by its **basis hash** (canonical form `fact-v1`: the fact without `section`, what it cites and
  its assumptions, each whole but for a named list of bookkeeping fields, and the bases of the
  facts it references; a reference cycle hashes as one). Upstream-stale also needs everything
  the upstream facts rest on to stay outside the fact's own root; a reference or citation the
  check rejected, a cited name listed twice, or a cited repos entry pinned by a ref leaves the
  basis unknown. A current FAIL is an error; the rest, and a `critical` fact without
  a second reader (a reader with the verdict's own verifier does not count), are warnings for checked roots, errors under `--require-verified pr` and, except
  upstream-stale, under `--require-verified main` (D19). A record's defects and a current FAIL
  make the root untrusted.
- `scripts/spec.py status <root>... [--context-root <dir>]... [--stale] [--json]`: per spec
  file, its record and each fact's freshness, basis hash and `upstream` map (what a verifier
  writes into the record); `--stale` lists only what a re-verification covers.
- `scripts/specmd.py`: the one CommonMark parse (markdown-it-py), used so far only to find text
  outside code for the placeholder check; SF2-4 adds the D20–D22 checks there.
- `requirements.txt`: PyYAML, jsonschema and markdown-it-py with their dependencies, pinned by
  hash. Install with `pip install --require-hashes -r skills/spec-format/requirements.txt`.
