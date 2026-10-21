<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# IPX-1: topwrap-ipxact-parser evaluation (#152)

Conclusions and the acceptance table are in the [evidence](../evidence/IPX-1.md). This chapter
holds what was found on the way and the dead ends.

## 2026-10-19T01:45Z — setup

- The package is not on PyPI (404); `git ls-remote` reaches antmicro/topwrap-utils and its HEAD
  is the issue's pinned commit `06c10f7`, so it was cloned and installed `--no-deps`.
- The generator's schema patches touch `ieee-1685-2009/memoryMap.xsd` (`access`) and the 2022
  `abstractionDefinition.xsd`; neither is in the 2022 register model, so the register classes
  come from the unpatched 2022 memory map.
- accellera.org redirects HTTPS to HTTP for the schema files; both serve the same bytes. The
  mirror commit the generator uses differs from the official files in `component.xsd` and
  `model.xsd` (added key references, a typed `portRef`): validation uses the official set.

## 2026-10-19T02:00Z — the first fixture

- Two schema errors in the hand-written fixture before it validated: `resets` follows
  `bitWidth` in a field, and a field array uses `bitStride`, not `stride`. Worth remembering for
  unit 4: the exporter's element order is the schema's, not the YAML's.
- The round trip of the full fixture was schema-valid and not equal. The diff showed the first
  register gone; inspecting the parsed object showed `addressBlock.register` as one object.
  One-, two- and three-register fixtures confirmed last-wins. `registerFile` is single-valued
  too (a dead end in `decode.py`, which first indexed it as a list), but its lost registers have
  a different cause, found in review: generateDS made the `registerData` group an element.

## 2026-10-19T02:20Z — single-register fixtures and the alternative

- Per element, the bindings keep arrays, resets, enumerations, aliases and vendor extensions on
  a single register; they drop an explicit `volatile false` and add `reserved 0` to every field
  access policy.
- xmlschema's `to_dict` keeps everything the bindings lost. Its default converter returns a
  single child as a mapping and repeated children as a list, so a reader needs a
  one-or-many accessor (or the `force_list` converter option) — a detail for unit 5.
- Dead end: `XMLSchema.encode` on the decoded dictionaries raised `XMLSchemaEncodeError` for
  every fixture. Not pursued; the exporter writes XML directly.

## 2026-10-19T03:00Z — review round 1

- Blocker found by the reviewer: "xmlschema adds nothing" was wrong. `to_dict` fills in schema
  defaults (`misalignmentAllowed`, `usage`) unless `use_defaults=False`; `decode.py` compared
  element keys only, so it could not see attributes. It now compares every attribute of every
  valid fixture with the source, both ways.
- A first attribute comparison flagged a fixture whose explicit `"true"` decoded as a boolean:
  a type artifact, normalized to text.
- Other fixes: `run.py` records the `removed`/`added` lines of each changed round trip and the
  bindings' stdout and stderr; four fixtures added (mixed order, explicit default attributes, a
  policy reference, nested and foreign extensions); the schema count (25) and its digest method,
  and the interpreter (3.13.16), corrected.
