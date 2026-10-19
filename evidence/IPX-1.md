<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# IPX-1: topwrap-ipxact-parser for the IP-XACT exporter and register adapter

**Terms:** *bindings* are Python classes generated from an XML schema (here by generateDS from
IP-XACT 2022); the *official XSD* is Accellera's published IEEE 1685-2022 schema; a *round trip*
parses a file and exports it again; *canonical equality* compares the two after dropping
comments and blank text. Units 4 and 5 are the [exporter and register-source
adapter](../docs/SPEC-FORMAT.md#export-spec.py-export-ipxact) of the precise-payloads design.

Issue: [#152](https://github.com/curtisgalloway/driver-lab/issues/152). Notebook:
[IPX-1](../notebook/IPX-1.md). Materials: [IPX-1/](IPX-1/) (fixtures, `run.py`, `decode.py`,
pins, results).

## Decision: reject for now

Do not adopt `topwrap-ipxact-parser` for the exporter or the adapter. Its bindings silently
drop registers and register files, lose their order (the export diff of `mixed-order.xml` in [results.json](IPX-1/results.json)), drop explicit values and add values the
source never stated, and export the damaged result as schema-valid XML, so no check downstream
would notice. Build both units on `xmlschema` alone, which D26 already requires for validation:
the exporter writes XML and validates it against the vendored official XSD; the adapter decodes
with the same schema **with `use_defaults=False`**, which kept every register, register file
and explicit value the checks in `decode.py` read, and exactly the source's attributes in every
valid fixture. With its default settings `to_dict` fills in schema
defaults the source never stated (`misalignmentAllowed`, `usage`), so the adapter must turn
them off. Revisit the package if upstream fixes the defects below and publishes versioned
releases.

## Identity

| Item | Value |
| --- | --- |
| Package | `topwrap-ipxact-parser` 0.0.1, [antmicro/topwrap-utils@06c10f7](https://github.com/antmicro/topwrap-utils/tree/06c10f727e2a2e8dd67d406a5aaf3e110a4e95cc/topwrap-ipxact-parser), Apache-2.0; not on PyPI (installed `--no-deps` from the checkout) |
| Its inputs | generateDS 2.44.3 with two patches; schema [edaa-org/IPXACT-Schema@3c68329](https://github.com/edaa-org/IPXACT-Schema/tree/3c683290483598378435ff93d38c5354fb9e5514) with two patches; `--no-pattern-validator` |
| Validation schema | the official 1685-2022 set fetched from accellera.org (HTTP; HTTPS redirects there) on 2026-10-19: 25 `.xsd` files, Apache-2.0 with NOTICE. Identity: `cd <xsd dir> && sha256sum *.xsd \| sort -k2 \| sha256sum` gives `e00b6a36e8aa4ccfce237631dae3559007e88a94183fb583d13421928862220b` |
| Environment | CPython 3.13.16; lxml 6.1.3, six 1.17.0, xmlschema 4.3.2, elementpath 5.1.4 ([pins](IPX-1/pins.txt), resolved with `--exclude-newer 2026-10-04`) |
| Fixtures | 25 component files ([fixtures/](IPX-1/fixtures/)): 21 schema-valid, of which one, `bad-offset-expression.xml`, was meant as a negative but is valid (`0x10` as an offset: 2022 offsets are expressions), and 4 schema-invalid |

Reproduce: create the environment from the pins, install the package from the pinned checkout
with `--no-deps`, fetch the official XSD files into a directory, then
`python IPX-1/run.py <xsd dir> IPX-1/fixtures` and `python IPX-1/decode.py <xsd dir>
IPX-1/fixtures`. [results.json](IPX-1/results.json) and [decode.json](IPX-1/decode.json) are
the outputs of this run.

## Acceptance (from #152)

| Criterion | Result |
| --- | --- |
| Pin commit, versions and schema; reproducible commands | Done (above). The mirror the bindings were generated from differs from the official XSD in `component.xsd` and `model.xsd` (the official adds key references and types `portRef`) |
| Omission versus explicit values, without asserting defaults | **Fails.** An explicit `<volatile>false</volatile>` on a field is dropped on export, and so are explicit default-valued attributes (`misalignmentAllowed="true"`, `usage="read-write"`); every `fieldAccessPolicy` gains `reserved` = 0, set when the object is built, so it is there right after parsing, not only on export (`removed`/`added` in [results.json](IPX-1/results.json)). xmlschema with `use_defaults=False` keeps the explicit `false` and every source attribute and adds none; with its default settings it adds `misalignmentAllowed` to 20 of the 21 valid fixtures (all but the one that states it) and `usage` to the two with an enumerated value that omits it ([decode.json](IPX-1/decode.json)) |
| Arrays, multidimensional dims and strides, register files, aliases, resets and reset types | Per element, survive a round trip **when the block holds one register**: 2-D register arrays with `indexVar`, field arrays with `bitStride`, `aliasOf`, default and named resets with masks. **Register files fail**: the registers inside one are dropped, and of two register files only the last is kept. **Order fails**: a block holding register A, register file RF and register B comes back as B, then RF |
| Access, modified-write, read action, policies, write constraints, enumerations | Survive on a single register (apart from the injected `reserved`), including a `fieldAccessPolicyDefinitionRef` to declared external type definitions. Register-level and field-level access both parse. Mapping driver-lab's register-level inheritance to field-level XML was not exercised: it is the exporter's own logic, which does not exist yet (Limitations) |
| Namespaced `vendorExtensions` (`unaffectedBy`, `initializedBy`, `lockedBy`, fact back-links) | Survive a single-register round trip unchanged, as do nested driver-lab elements with attributes and a foreign-namespace extension beside them; xmlschema decodes them too |
| Independent validation of positive and negative fixtures | All four schema-invalid fixtures parse in the bindings with no exception and no message on stdout or stderr (bad access enum, bad modified-write enum, a name failing `\i\c*`, a field without `bitWidth`), and the bindings export them again. Validation must come from xmlschema with the official XSD, as D26 says; nothing in the bindings substitutes for it |
| Export, parse, register-record round trips; partial records; digests | **Fails for any real block.** A block's `register` is one object, not a list: with registers A, B, C only C survives, so a register record set cannot round-trip. Partial records and canonical digests were not tested: with registers lost at parse time there is nothing faithful to digest, and the adapter that would build partial records does not exist yet |
| Gaps, dependency and license, maintenance; adopt, defer or reject | Reject for now (above). Apache-2.0, lxml and six only; one 132,347-line generated module; 2 commits touch the package in the repository's history; no release or PyPI upload. dep-quality could not score it (GitHub API unreachable from this session, no registry data); xmlschema scores 7.4/10 at confidence 0.35 (MIT, 530 dependents, 10 releases in 24 months) |

## Findings

1. **Last register wins, and order is lost.** generateDS modeled the address block's repeated
   `register`/`registerFile` choice as two single properties: each register parsed overwrites
   the previous one, each register file likewise, and their interleaving is gone. Reproduced
   with one, two and three registers, two register files and a mixed block
   ([decode.json](IPX-1/decode.json)). Silent data loss, and the export is schema-valid.
2. **A register file's registers are dropped.** A separate cause: generateDS turned the
   `registerData` group into an element (`registerFile.registerData`, always empty here), so
   the `<register>` children of a register file are skipped.
3. **Explicit values are dropped** on export: `volatile` set to `false` on a field, and
   attributes written with their default value. Omission and an explicit value cannot be told
   apart, which the precise-payloads design relies on.
4. **A default is invented**: `reserved` set to `0` in every `fieldAccessPolicy`, from the
   constructor, so it is present after parsing and written on export.
5. **No validation in the bindings** (`--no-pattern-validator`, and generateDS checks no
   enumerations on parse): every schema-invalid fixture parses and exports, silently.
6. **The mirror is older than the official XSD** in two files. Bindings regenerated from the
   official set would differ; validation must use the official set regardless.
7. **xmlschema needs `use_defaults=False`** to decode faithfully; with defaults on it adds
   `misalignmentAllowed` (20 of 21 valid fixtures) and `usage` (where an enumerated value omits
   it).

Upstream fixes that would reopen the question: findings 1 and 2, 3 (keep explicit values), 4
(emit only what was parsed), and a versioned release. Drafts of upstream issues were written for
the user to review and file; none was filed from here.

## Limitations

- Round trips beyond a single register could not be tested on the bindings, because finding 1
  destroys them first; the per-element results above are from single-register fixtures.
- Driver-lab's register-level access inheritance, partial records and canonical digests depend
  on the exporter and adapter, which do not exist yet; they were not exercised.
- xmlschema was tested as a decoder only. Its `encode` refused the decoded dictionaries of every
  fixture (`XMLSchemaEncodeError`); the design has the exporter write XML itself and validate
  it, so the encoder is not needed, but this run does not show it working.
- The dep-quality scores are low-confidence: this session reaches GitHub's API only for the
  repositories attached to it.
- No IP-XACT file from a vendor or another tool was tried; all fixtures are hand-written.

## Consequences

- Units 4 and 5 keep D26 unchanged: `xmlschema`, pinned with hashes after a dep-quality score,
  validates exports against the vendored official XSD, and the same schema decodes inputs for
  the `ipxact` adapter. No generated bindings.
- The 25 fixtures here are a starting set for unit 4's export tests and unit 5's adapter tests.
