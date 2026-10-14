<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Standards survey for spec fact precision (issues #103, #105, #118)

Date: 2026-10-14. Read-only research; nothing in any repository was changed.

**How to read the evidence labels.** "Read in source" means I fetched the standard,
its schema, or the tool's source and quote it. "Secondary" means a page about the
standard (vendor manual, tool docs, search-engine summary). "Unverified" means I could
not fetch a source for that claim. Downloads mentioned below were kept only for the
survey and are not in this repository.

**Terms used below.**
- *IP-XACT*: IEEE 1685, an XML format for describing hardware blocks, including
  registers and fields.
- *XSD*: XML Schema Definition, the machine-readable grammar of an XML format.
- *SystemRDL*: Accellera's text language for describing registers.
- *SVD*: Arm's CMSIS System View Description, an XML register format for microcontrollers.
- *PSS*: Accellera Portable Test and Stimulus Standard, a language for writing test scenarios.
- *UVM*: IEEE 1800.2, the SystemVerilog verification class library. It has a register layer.
- *PDL*: Procedural Description Language from IEEE 1687, which uses commands such as `iWrite` and `iApply`.
- *UCUM*: Unified Code for Units of Measure, a set of unit codes such as `us` and `min`.
- *Standoff provenance*: citations kept beside the data and keyed by an identifier,
  rather than embedded in the data element.

---

## 0. What the current schema has (for orientation)

Read in `skills/spec-format/schema/spec.schema.json`:
- `$defs.register` has `name, offset, width, access, reset`, and its `access` enum is
  `ro, wo, rw, w1c, w1s, rc`.
- `$defs.field` has `id, name, meaning, requirement, support, todo, note, bits`, with no
  per-field access, reset, or values.
- `$defs.layoutField` has `offset, size` in whole bytes, with no bit range.
- `$defs.step` has `id, action, requirement, support, todo, note`, with no timeout or recovery.

`docs/SPEC-FORMAT-V2.md` §"Data formats…" says layouts are "shaped like register fields
with byte offsets".

---

## 1. Register and field semantics

### 1a. IEEE 1685-2022 (IP-XACT)

- **Governing body and number:** IEEE Std 1685-2022, "IEEE Standard for IP-XACT, Standard Structure for
  Packaging, Integrating, and Reusing IP within Tool Flows". The standard is active, published
  2023-02-28, and supersedes 1685-2014 (https://standards.ieee.org/ieee/1685/10583/). Accellera
  maintains the schema.
- **Availability and license.**
  - *Standard text:* free. Accellera's IEEE page marks 1685-2022 with "*" and says "The
    standards labeled with * are provided to the community at no cost courtesy of Accellera
    via the IEEE Get program" (https://www.accellera.org/downloads/ieee). The text stays under
    IEEE copyright. I did **not** read the normative text, because GET downloads need an IEEE
    login. Everything below comes from the XSD.
  - *Schema:* Apache-2.0. The official file at
    http://www.accellera.org/XMLSchema/IPXACT/1685-2022/memoryMap.xsd carries the header
    "Accellera licenses this file to you under the Apache License, Version 2.0". I downloaded it,
    and it is byte-identical to the mirror's copy (compared with `diff`). The mirror's
    `ieee-1685-2022/NOTICE` reads "Copyright 2011-2023 Accellera Systems Initiative Inc." and covers
    "the IP-XACT XML Schema Definition, the XSL Transformations, the TGI WDSL and YAML descriptions,
    and the XML document examples".
  - *Supplementary material:* the download page lists "1685-2022 Vendor Extensions 1.0", release
    notes, an issues list, and an IP-XACT User Guide (Sept 2023). It shows no license text
    (https://accellera.org/downloads/standards/ip-xact). I did not open those files.

**What the schema expresses.** All of the following was read in the 2022 `memoryMap.xsd`,
`component.xsd`, `typeDefinitions.xsd`, and `commonStructures.xsd` in the mirror.
- **Access:** `accessType` is one of `read-only`, `write-only`, `read-write`, `writeOnce`,
  `read-writeOnce`, or `no-access`.
- **Write side effects:** `modifiedWriteValue` is one of `oneToClear`, `oneToSet`, `oneToToggle`,
  `zeroToClear`, `zeroToSet`, `zeroToToggle`, `clear`, `set`, or `modify`. A `modify` attribute names a
  user-defined behavior.
- **Read side effects:** `readAction` is one of `clear`, `set`, or `modify`. `readResponse` gives the
  value a read returns.
- **Write constraints:** `writeValueConstraint` is a choice of three forms. `writeAsRead` means "only
  a value immediately read before a write is a legal value to be written". `useEnumeratedValues`
  limits writes to the enumerated values. The third form is a `minimum` plus `maximum` range.
- **Reserved:** `fieldAccessPolicy/reserved` (default 0) "Indicates that the field should be
  documented as reserved".
- **Testability:** `testable` takes a `testConstraint` of `unconstrained`, `restore`, `writeAsRead`,
  or `readOnly`.
- **Mode-dependent access:** each `fieldAccessPolicy` can carry `modeRef`s, so access can differ by
  mode. `accessRestrictions` also exist.
- **Reusable named policies:** `typeDefinitions/fieldAccessPolicyDefinitions/fieldAccessPolicyDefinition`
  is a *named, reusable* bundle of `access`, `modifiedWriteValue`, `writeValueConstraint`,
  `readAction`, and `readResponse`. This is the standard's own way to give names like "RW1C" to a
  combination.
- **Volatile:** `volatile` is a boolean.
- **Resets:**
  - `field/resets/reset` occurs one or more times. Each holds a `value`, an optional `mask`,
    and an attribute `resetTypeRef`, documented as "Reference to a user defined resetType.
    Assumed to be HARD if not present".
  - Reset type names are declared in `component/resetTypes/resetType` ("A user defined reset
    policy") or in `typeDefinitions/resetTypes`.
  - A schema key, `fieldResetTypeRefKey`, makes `resetTypeRef` unique per field.
- **Enumerations:** `enumeratedValues/enumeratedValue` holds `name`, `value`, and
  `vendorExtensions`, and has a `usage` attribute of `read`, `write`, or `read-write`.
  `enumerationDefinitionRef` lets a field reuse an enumeration defined in
  `typeDefinitions/enumerationDefinitions`. This matters for #103, where the same opcode table
  appears in several places.
- **Aliasing:** a field's definition is a choice: either `bitWidth`, `volatile`, and `resets`, or
  `aliasOf`, a full field reference through `fieldReferenceGroup`. The register level has
  `alternateRegisters/alternateRegister` with `modeRef`. A field policy can carry
  `broadcasts/broadcastTo`, meaning a write also lands in other fields.
- **Identifiers and extensions:** `xml:id` (the `id.att` group) appears on 44 element types in
  `memoryMap.xsd`, including `reset` and `fieldAccessPolicy`. `vendorExtensions` (`xs:any`, "Accepts
  any element(s)…") appears on fields, enumerated values, policies, and reset types.

**What it cannot express natively.**
- **Sticky (survives a given reset):**
  - The schema can say what value a field takes for each named reset type. It has no element
    meaning "this reset leaves the field unchanged".
  - A search-engine summary of an Accellera forum reply (forums.accellera.org topic 7673,
    "resettypes") says "if a field does not have a reset value then it means that it is not
    documented. You cannot assume it is not affected by a reset." I could not fetch the forum
    (HTTP 403), so this is **unverified** and in any case informal.
  - Treat "unaffected by reset X" as needing a vendor extension or our own property.
- **Hardware-initialized (HwInit):** no element says "set by straps or firmware before the driver
  runs". The closest is `read-only` with a reset value that is a parameter.
- **Sequences, timeouts, and units for software timing:** the only time units in the 2022
  schema are `ps` and `ns` (`delayValueUnitType`), used for clock and port timing.
- **The TGI files (`TGI/TGI.yaml`, OpenAPI 3.0.3):** these describe an API through which
  generators query an IP-XACT database. They do not describe procedures. A grep found reset
  accessors and nothing about sequences.

**Tooling.**
- **XSD validation:**
  - `xmlschema` (Python, MIT, last pushed 2026-06-30) or `lxml` validate against the XSD.
  - The mirror itself (`edaa-org/IPXACT-Schema`) has a top-level Apache-licensed `LICENSE.md`
    and an `__init__.py`. Following the safety rule, I did not run it.
- **Python importers and exporters for 2022 are weak:**
  - PeakRDL-ipxact (LGPL-3.0) exports only 2009 and 2014. Read in source: its `Standard` enum
    lists `IEEE_1685_2009` and `IEEE_1685_2014`, the docstring says "Currently supports IEEE
    1685-2009 and IEEE 1685-2014 (default)", and the 2014 namespace is hard-coded.
  - ipyxact (MIT) contains `ipxact2014.py` and no 2022 module (judged from the file list only).
  - Kactus2 (C++, GPL-2.0, active) says "supports both the IEEE 1685-2014 and IEEE 1685-2022"
    (README).
  - In practice our own exporter plus `xmlschema` validation is the realistic path. That matches
    the decision already taken.

**Fit next to per-value provenance.** It fits well. Our YAML stays the authoring form, and the
exporter can drop `support` or carry it in `vendorExtensions`, which `field`, `enumeratedValue`,
and `fieldAccessPolicy` all accept. `reset` has no `vendorExtensions`, but it does carry an
`xml:id`, so a standoff table keyed by `xml:id` can cite each reset value.

### 1b. SystemRDL 2.0 (Accellera)

- **Governing body and version:** Accellera, "SystemRDL 2.0 Register Description Language", January 2018. I
  downloaded the PDF from
  https://www.accellera.org/images/downloads/standards/systemrdl/SystemRDL_2.0_Jan2018.pdf.
  The download page shows no license agreement
  (https://www.accellera.org/downloads/standards/systemrdl).
- **License:** the PDF reads "Copyright © 2015 - 2018 Accellera. All rights reserved." and
  "Authorization to photocopy portions of any individual standard for internal or personal use
  must be granted by Accellera". The text is free to read but not open-licensed. Using its
  vocabulary is fine; copying its text is not.
- **Expressiveness (read in the PDF text):**
  - `sw` is one of `rw, wr, r, w, rw1, w1, na`.
  - `onread` is one of `rclr, rset, ruser`.
  - `onwrite` is one of `woset, woclr, wot, wzs, wzc, wzt, wclr, wset, wuser`, each defined
    bitwise, for example "woclr  Bitwise write one to clear (field = field & ~write_data)".
  - `singlepulse`; `reset` and `resetsignal` ("If no reset value given, the field is not reset,
    even if it has a resetsignal"); `encode` for enumerations; `donttest` and `dontcompare`;
    `ispresent`.
  - Address maps take `lsb0`/`msb0` (bit numbering) and `bigendian`/`littleendian`.
  - `rsvdset`/`rsvdsetX` set the read value of undefined bits.
  - Clause 15 defines user-defined properties.
- **Gaps:**
  - No field-level "reserved" flag. Reserved bits are simply undeclared, and `rsvdset`/`rsvdsetX`
    are address-map wide.
  - No write-value constraint comparable to RsvdP/RsvdZ.
  - **Vocabulary collision:** in SystemRDL, `sticky`/`stickybit` mean "latch until software
    clears" ("each bit in a stickybit field is handled individually, whereas sticky applies a
    sticky state to all bits"), an interrupt concept. In PCIe, "sticky" means "not reset by hot
    reset".
  - The PCIe meaning maps better to SystemRDL's `resetsignal` (the field is reset only by a named
    signal).
- **Tooling:**
  - `systemrdl-compiler` (Python, MIT, pushed 2026-10-07, 287 stars) is the mature reference
    compiler, with the PeakRDL family around it.
  - The PeakRDL-ipxact `typemaps.py` source maps `woclr→oneToClear`, `wzs→zeroToSet`,
    `rclr→clear` and so on one-to-one. SystemRDL and IP-XACT therefore share the same write and
    read semantics, so choosing IP-XACT names loses nothing.
- **Provenance:** user-defined properties can attach a citation to any component natively.

### 1c. CMSIS-SVD (Arm, Open-CMSIS-Pack)

- **Spec and license:** the spec is at https://open-cmsis-pack.github.io/svd-spec/main/ and the
  repository `Open-CMSIS-Pack/svd-spec` is Apache-2.0 (GitHub API).
- **Expressiveness (read on the spec pages):**
  - Field children: `access`, `modifiedWriteValues` (the same nine values as IP-XACT),
    `readAction` (`clear, set, modify, modifyExternal`), `writeConstraint` (`writeAsRead`,
    `useEnumeratedValues`, or `range`), and up to two `enumeratedValues` with `usage` and
    `isDefault`.
  - `access` is one of `read-only, write-only, read-write, writeOnce, read-writeOnce`.
  - Also `derivedFrom` and `alternateRegister`.
- **Gaps:**
  - **`resetValue`/`resetMask` exist only at register level.** The field page lists no field
    reset, and there is a single reset with no reset types.
  - No reserved flag.
  - `vendorExtensions` is device-level only: "The content and format of this section is
    unspecified" (elem_device page). There is no per-field metadata.
- **Tooling:** strong. `cmsis-svd` (Python, Apache-2.0, 1209 stars); `svd2rust` and `svdtools`
  (Apache-2.0).
- **Provenance:** poor. Only `description` text is available per field.

### 1d. OpenTitan reggen (hjson) and chiptool YAML

- **OpenTitan reggen** (https://opentitan.org/book/util/reggen/index.html; lowRISC/opentitan,
  Apache-2.0):
  - `swaccess` is one of `none, ro, rc, rw, r0w1c, rw1s, rw1c, rw0c, wo`, and `hwaccess` is one of
    `hro, hrw, hwo, none`.
  - Field `resval` can be a value or `x` (undefined); `enum` takes `{name, desc, value}`, with an
    `rsvdenum` flag; there are `alias_target` and `tags`. Vendor-specific fields are possible
    only via a `--vendor-specific-fields` flag.
  - There is a single reset; it has no sticky or reset-type concept.
  - It is a project format, not a standard.
- **chiptool** (embassy-rs, Apache-2.0) is "an experimental fork of `svd2rust`" with "standalone
  YAML files". Its separation of a *fieldset* (a set of fields) from a register is a useful idea
  for #103, because one bit layout can describe both a register and a descriptor word. It is not
  a standard.

### 1e. UVM (IEEE 1800.2) register field access policies

- **Availability and license:** free through IEEE GET (1800.2-2020 is marked "*" on
  https://www.accellera.org/downloads/ieee). The reference implementation `accellera-official/uvm-core`
  is Apache-2.0.
- **Access policies (read in `src/reg/uvm_reg_field.svh`):** the policy strings are
  `RO, RW, RC, RS, WRC, WRS, WC, WS, WSRC, WCRS, W1C, W1S, W1T, W0C, W0S, W0T, W1SRC, W1CRS, W0SRC,
  W0CRS, WO, WOC, WOS, W1, WO1` (plus `NOACCESS`).
- **Resets:** reset functions take `kind = "HARD"` by default (`reset(string kind = "HARD")`,
  `has_reset(string kind = "HARD", …)`). This matches IP-XACT's default reset type "HARD".
- **Assessment:** the compact names are a useful *rendering* vocabulary, but semantically they
  are IP-XACT tuples.

### 1f. PCIe register types and how each would map

- **Sources:**
  - The PCIe Base Specification is a PCI-SIG document. I did not check its access terms
    (unverified), so the definitions below are **secondary**.
  - They come from the Intel 41210 bridge manual mirror
    (https://manualsdump.com/en/manuals/intel-41210model/110147/73), which I fetched. Quotes:
    - "RsvdP Reserved and Preserved: … software must preserve the value read for writes to bits."
    - "RsvdZ Reserved and Zero: … software must use 0 for writes to bits."
    - "ROS Read-Only Sticky: … not cleared by reset and can be reset only with the PERST# reset
      condition."
    - "RWS Read-Write and Sticky: … The bit can be reset only by a PERST# reset."
  - That manual's text did not define RW1CS or HwInit. I could not fetch Intel's PCIe IP page
    (HTTP 403). The HwInit meaning ("initialized by hardware or firmware such as straps or EEPROM,
    read-only to software afterwards") is **unverified** here.

| PCIe type | IP-XACT 2022 mapping | Gap |
|---|---|---|
| RO | `access: read-only` | none |
| RW | `access: read-write` | none |
| RW1C | `read-write` + `modifiedWriteValue: oneToClear` | none |
| RWS | `read-write` + resets listed only for the reset types that clear it (e.g. a declared `resetType` for fundamental reset) | IP-XACT cannot say "unchanged by hot reset" (see 1a): needs an extension or our own property |
| RW1CS | RW1C + the same sticky treatment | same as RWS |
| ROS | `read-only` + sticky treatment | same as RWS |
| HwInit | `read-only` (the reset value may be a parameter) | "initialized by straps or firmware" has no element: extension or own property |
| RsvdP | `reserved: 1` + `writeValueConstraint/writeAsRead: true` | none: a clean fit |
| RsvdZ | `reserved: 1` + `writeValueConstraint` `minimum 0`/`maximum 0` | none: a clean fit |

**Recommended shape for the sticky gap.** Keep IP-XACT's `resets` list (value per `resetTypeRef`) and add
one project property, for example `unaffectedBy: [<resetType>…]`, which the exporter writes into
`vendorExtensions`. Under the standard's default, a missing reset type is ambiguous, and this
property makes "not affected" explicit and checkable. Do not call it `sticky`, because SystemRDL
uses that word for the latch concept. Name the PCIe type in a `fieldAccessPolicyDefinition`
(for example `RW1C`) so that both the IP-XACT tuple and the familiar abbreviation survive.

---

## 2. Ordered procedures (init, power and reset sequences, polling with timeouts, recovery)

### 2a. Accellera PSS 3.0

- **Version and availability:** "Portable Test and Stimulus Standard Version 3.0, August 2024". I
  downloaded https://www.accellera.org/images/downloads/standards/pss/Portable_Test_Stimulus_Standard_v3.0.pdf.
  The download page shows no license, and the PDF says "Copyright © 2024 Accellera. All rights
  reserved."
- **Register features (read in §24.11):**
  - `pure component reg_c <type R, reg_access ACC = READWRITE, int SZ…>` has target functions
    `read()`, `write()`, `read_val()`, `write_val()`, `write_masked()`, `write_field()`, and `write_fields()`.
  - `enum reg_access {READWRITE, READONLY, WRITEONLY}`.
  - Register groups (`reg_group_c`) are mapped to address regions through an implementation-defined
    `set_handle()`.
- **Status of the HSI part:** the abstract calls the hardware/software interface part "a preliminary
  mechanism to capture the programmer's view of a peripheral device".
- **Packed structs (read in §24.10.1):**
  - `packed_s<LITTLE_ENDIAN>`/`packed_s<BIG_ENDIAN>` define exact packing. In little-endian mode
    "fields are packed into registers from the LSB to the MSB in the order in which they are
    defined and packed in memory from the LSbyte to the MSbyte". The standard includes worked
    figures.
- **Assessment:** PSS is a **language** (actions, exec blocks, target functions). Sequences are
  code, not data. It has no timeout or recovery vocabulary for register polling.
- **Tooling:** commercial tools only. I found no Python PSS parser in this pass (unverified).

### 2b. IEEE 1800.2 UVM register sequences

- `uvm-core/src/reg/sequences/` contains `uvm_reg_hw_reset_seq.svh`, `uvm_reg_bit_bash_seq.svh`,
  `uvm_reg_access_seq.svh`, and similar files. These are generic verification sequences written
  in SystemVerilog code, not device procedures, and they are not a data format.

### 2c. IP-XACT 1685-2022

- Nothing in the 2022 XSDs describes a procedure. The TGI is a query API (see 1a).
- The one adjacent feature is `modes`, used with `modeRef` on access policies and alternate
  registers. It can say "in mode X this field is writable", but not "do A, then B".

### 2d. IEEE 1687 (IJTAG) PDL, the closest standard "procedure language"

- **Status:** IEEE 1687-2014 is listed as "Inactive-Reserved Standard", published 2014-12-05 and
  inactivated 2025-03-27 (https://standards.ieee.org/ieee/1687/3931/). The search summary also
  mentions a new active project authorization request for P1687 (unverified). The 2014 text is
  sold, not free (not in the GET list).
- **Secondary description:** an example from https://www.techdesignforums.com/practice/?p=3123
  shows `iWrite core1.instWTAP.IR enableIP3` followed by `iApply`, and the page explains that
  "iApply" closes the instruction block.
- **Unverified:** search summaries say `iRead R 0xFF` reads and compares against an expected
  value, and that `iRunLoop` gives coarse waits. I fetched no page that states either.
- **Assessment:** PDL is a Tcl-based command language for JTAG-reachable instruments. Its verbs
  (write, read-and-expect, apply, run-loop) are the right *shape*, but it is a language, it is
  inactive, and it is paywalled.

### 2e. Data-form precedents (not standards)

- **Linux `struct reg_sequence {reg; def; delay_us;}`.** Read in `include/linux/regmap.h`:
  "Register/value pairs for sequences of writes with an optional delay in microseconds to be
  applied after each write."
- **Linux `read_poll_timeout(op, val, cond, sleep_us, timeout_us, …)`.** Read in
  `include/linux/iopoll.h`: "@timeout_us: Timeout in us, 0 means never timeout". A poll step is
  fully described by {read operation, condition, sleep interval, timeout}.
- **NXP i.MX boot-ROM Device Configuration Data, as encoded in U-Boot.** Read in
  `include/imximage.h`: `DCD_WRITE_DATA_PARAM`, `DCD_WRITE_CLR_BIT_PARAM`,
  `DCD_WRITE_SET_BIT_PARAM`, `DCD_CHECK_BITS_SET_PARAM`, `DCD_CHECK_BITS_CLR_PARAM`. This is a
  real, data-only init-sequence format that a boot ROM executes: write, set bits, clear bits, and
  poll for bits set or clear.
- **Agnisys IDS-Validate.** Its sequences are "pseudo-code within the spec", spreadsheet or text
  input (https://www.agnisys.com/blog/setting-the-stage-for-the-next-abstraction). It is a
  commercial, proprietary product.

**Conclusion:** I found no recognized standard that is a *data* format for driver-level
procedures with timeouts and recovery. A search for an IEEE or Accellera HSI sequence data
standard found none (the search may be incomplete).

---

## 3. In-memory and on-wire data layouts

### 3a. Kaitai Struct (.ksy YAML)

- **Status and licenses:** Kaitai is a project, not a standards body.
  - Python runtime: MIT. The `ksy_schema` repository (a JSON Schema for .ksy): MIT.
  - Compiler: GPL-3.0. Documentation: GNU FDL 1.3.
  - These come from the GitHub API and license files. The umbrella repository's README defers
    licensing to kaitai.io.
- **Expressiveness (read in https://doc.kaitai.io/user_guide.html, v0.11):**
  - Bit-sized integers `bX`, with `bit-endian` `be` (default) or `le`. With `be`, parsing runs
    "from the most significant bit (MSB, 7) to the least significant bit (LSB, 0)"; with `le`,
    "bytes are filled from LSB (0) to MSB (7)".
  - Byte `endian`.
  - Enums, including "verbose enums" with `id`, `doc`, and `doc-ref`.
  - `valid` constraints (`eq`, `min`, `max`, `any-of`, `expr`).
- **Provenance:** **best of any candidate.** Quote: "The `doc` key has a 'sister' key `doc-ref`,
  which can be used to specify references to original documentation. Everywhere where you can use
  `doc`, you can use `doc-ref` as well." That covers each attribute and each enum value.
- **Gaps:** it describes parsing (read-only). It has no access semantics and no notion of a
  container word with masks the way datasheets draw them, though `bX` sequences reproduce the
  layout.

### 3b. ASN.1 (ITU-T X.680 family), PER (X.691), ECN (X.692)

- **Availability:** X.692 (02/21) is listed under "Freely available items", and I downloaded its
  PDF (https://www.itu.int/rec/T-REC-X.692-202102-I/en). X.691 (02/21) is in force. Its page did
  not state the access terms (I treated it as unverified for X.691).
- **PER:** encodes abstract values by fixed rules. It cannot describe an *existing* hand-drawn
  layout.
- **ECN (X.692):** read in the PDF, ECN exists for "established ('legacy') protocols where the
  encoding is already determined and differs from all standardized encoding rules". Annex D.5
  covers a "Legacy protocol specified with tabular notation". Bits are numbered "from 8 to 1,
  where bit 8 is the 'most significant bit'".
- **Tooling:** I found no open-source ECN implementation. asn1c and asn1tools support
  BER/PER/XER, not ECN (search, inconclusive).
- **Provenance:** comments only (my assessment).

### 3c. P4_16 headers

- **Spec and license:** P4_16 spec v1.2.5 (`p4lang/p4-spec`, `P4-16-spec.adoc`), with the header
  "SPDX-License-Identifier: Apache-2.0".
- **Layout:** "When extracting data into a bit-string or integer, the first packet bit is
  extracted to the most significant bit of the integer". It is network-order and big-endian only.
- **Fit:** a good fit for network headers, but not for the little-endian DMA descriptors that most
  PCIe and SoC devices use. It is code and has no citation mechanism.

### 3d. Wireshark dissector field model

- **Model (read in `doc/README.dissector`):** a field is `{name, abbrev, type FT_*, display
  BASE_*, strings (value_string), bitmask, blurb}`. "the bitmask is the mask which will leave only
  the bits needed to make the field when ANDed with a value". Byte order is given per item by
  `ENC_BIG_ENDIAN`/`ENC_LITTLE_ENDIAN`.
- **Fit:** this is code (C or Lua), not a data format. Its *model* is the one #103 needs: a
  container word at a byte offset, in a stated byte order, plus a bit mask or range, plus a value
  table.

### 3e. DFDL (Open Grid Forum GFD-R-P.240, Feb 2021)

- **Document and license:** read at https://daffodil.apache.org/docs/dfdl/: "Copyright © Open Grid
  Forum (2006-2021). Some Rights Reserved. Distribution is unlimited". The implementation, Apache
  Daffodil, is Apache-2.0 and Scala/JVM; there is no native Python implementation.
- **Bit and byte order:** `dfdl:bitOrder` is `mostSignificantBitFirst` or `leastSignificantBitFirst`,
  defined exactly by bit significance and adjacency ("The least significant bits of byte N are
  considered to be adjacent to the most significant bits of byte N+1"). §11.3 allows only
  `bigEndian`+`mostSignificantBitFirst`, `littleEndian`+`mostSignificantBitFirst`, and
  `littleEndian`+`leastSignificantBitFirst`; "Other combinations MUST produce Schema Definition
  Errors."
- **Assessment:** it is heavy (XSD annotations). Its bit- and byte-order vocabulary is the most
  precise recognized definition I found.

### 3f. IP-XACT for layouts

- The 2022 `port.xsd` adds `structured` ports (`struct`, `union`, `interface`, with a `packed`
  attribute) for *signals*, not memory layouts.
- `busInterface` `endianness` is `big` or `little`, documented as "If this element is not present
  the default is 'little' endian".
- A descriptor could be forced into a `register` inside a memory-usage `addressBlock`, but that is
  a misuse.
- The reusable `enumerationDefinitions` is the part worth sharing between register fields and
  layout fields.

### 3g. Bit numbering conventions to record explicitly

The standards differ:
- ITU X.692 numbers bits 8..1 with 8 as the MSB.
- SystemRDL `lsb0` (default) versus `msb0`: "lsb0 mode defines 0 as the least significant bit
  … msb0 defines regwidth-1 as the least significant bit".
- PSS packs fields LSB-first in little-endian mode and MSB-first in big-endian mode.
- P4 maps the first wire bit to the MSB.

A spec needs per-layout `byteOrder` and a bit-numbering value, or a field like
`bits: [high, low]` is ambiguous.

---

## 4. Timing values and tolerances

- **UCUM** (Regenstrief, v2.2, 2024-06-17, https://ucum.org/ucum):
  - Case-sensitive codes are `s`, `min` (60 s), `h`, `us` (prefix `u` = 1e-6), `ns`, `Hz`, `V`,
    and `%`.
  - It defines **no** tolerance, range, or uncertainty syntax. Annotations "do not contribute to
    the semantics".
  - License (read in `ucum-org/ucum` LICENSE.md, v1.1 June 2024): a no-charge, revocable license
    "to use the Work for the purposes of developing and commercializing Software Applications that
    will communicate with and interoperate with the Work". You may not "use the Work for the
    purpose of developing or promulgating a different standard" or "add, delete, or modify the
    Work's content". Using UCUM codes as unit strings is within the grant; copying or editing the
    UCUM tables is not.
  - Python: `pint` (BSD-style license text, active) parses units but is not UCUM-native (my
    assessment; I did not test UCUM parsers).
- **IEC 61360 LEVEL_TYPE (MIN, NOM, TYP, MAX):**
  - The standard is paywalled. Secondary source, ECLASS
    (https://eclass.eu/support/technical-specification/structure-and-elements/level-type):
    "The level type is an attribute of a numeric Property indicating its values are defined for
    different levels". MIN is "minimum of the value", NOM "value as designated", TYP "value as
    typically present", MAX "maximum of the value", and "This concept is described in EN
    61360-1:2017".
  - This is the recognized vocabulary for datasheet-style values. "1 minute (+50%/-0%)" becomes
    `nom: 1 min, min: 1 min, max: 1.5 min`.
- **PTB D-SI (Digital SI XML):** it represents *measurement uncertainty* (expanded uncertainty,
  coverage interval), according to search results on PTB GitLab commits. That is the wrong concept
  for a specification limit. No fit.
- **IP-XACT:** only `ps` and `ns` for clocks and port delays (see 1a). No tolerance.
- **dt-schema unit suffixes** (read in `dtschema/schemas/property-units.yaml`, BSD-2-Clause):
  "Properties which have a unit of measure are recommended to have a unit suffix appended to the
  property name". It lists `-sec`, `-ms`, `-us`, `-hz`, `-percent`, and others. This is precedent
  in the Linux and Fuchsia consumer ecosystem, but it has no tolerance either.

---

## 5. Device-level descriptions

- **dt-schema / Devicetree** (dt-schema BSD-2-Clause; devicetree-specification Apache-2.0):
  - It validates *board descriptions of device instances* (properties, `reg`, interrupts) with
    JSON Schema in YAML. It does not describe register internals or sequences.
  - It is a consumer-side target for our facts (bindings), not a container for them.
- **ACPI 6.6** (UEFI Forum, https://uefi.org/specifications):
  - The page says the specs are "available for downloading and to read only". It grants no
    license "to distribute, additionally reproduce, implement or otherwise use" without the
    (free) Adopter Membership Agreement.
  - The Generic Address Structure (§5.2.3.2: Address Space ID, Register Bit Width, Register Bit
    Offset, Access Size, Address) is a neat data form for "where is this register".
  - Power and reset procedures are AML code.
  - No fit as a container.
- **IP-XACT component:** the broadest standard container, covering memory maps, registers, reset
  types, modes, ports, and (in 2022) power domains. It still lacks procedures, layouts, and
  timing.
- **SystemRDL + PSS:** PSS `reg_c` consumes a register model, but sequences remain PSS code (2a).
- **Conclusion:** no single standard covers registers, sequences, layouts, and timing together.

---

## Provenance fit summary

| Format | Per-value citation |
|---|---|
| IP-XACT 2022 | `vendorExtensions` on field, enumeratedValue, policy, and register; `xml:id` on reset and 43 other types for standoff |
| SystemRDL | user-defined properties on any component (native) |
| SVD | none per field (device-level `vendorExtensions` only) |
| OpenTitan | `tags`, or an opt-in vendor-fields flag |
| Kaitai | `doc-ref` everywhere `doc` is allowed, including enum values (native) |
| DFDL | XSD `appinfo` annotations |
| ASN.1/ECN, P4, UCUM | none |

---

## Recommendations

1. **Register and field semantics: adopt IEEE 1685-2022.**
   - Use `access`, `modifiedWriteValue`, `readAction`, `readResponse`, `writeValueConstraint`
     (`writeAsRead`, `useEnumeratedValues`, `minimum`/`maximum`), `reserved`, `volatile`,
     `resets/reset{value, mask, resetTypeRef}` with declared `resetTypes`, `enumeratedValues`
     (plus `usage`), `aliasOf`, and `fieldAccessPolicyDefinition` for named types such as RW1C.
   - Add exactly two project extensions, exported via `vendorExtensions`:
     - `unaffectedBy: [resetType]`, for PCIe sticky.
     - `initializedBy`, for HwInit.
   - Reasoning: it covers RsvdP and RsvdZ exactly, maps one-to-one to SystemRDL, SVD, and UVM,
     and the XSD is Apache-2.0.
2. **Ordered procedures: no fit; define our own.**
   - Borrow verbs and fields from the Linux `reg_sequence`/`read_poll_timeout` shape and from
     i.MX DCD: `write`, `setBits`, `clearBits`, and `poll{field|mask, condition, interval,
     timeout}`, plus `delay`.
   - Add `onTimeout`/`recovery` as step references.
   - Point at fields with IP-XACT-style references.
   - Reasoning: PSS, UVM, and PDL are languages, not data; PDL is inactive and paywalled; and
     nothing standard has timeout or recovery fields.
3. **Data layouts: borrow vocabulary only.**
   - Model a layout field as a container word (`offset` in bytes, `width` in bits) plus
     `byteOrder` (`bigEndian`/`littleEndian`, as in DFDL) plus a `bitOrder` or bit-numbering value
     (DFDL `mostSignificantBitFirst`/`leastSignificantBitFirst`, or SystemRDL `lsb0`/`msb0`) plus
     `bits`.
   - Reuse IP-XACT `enumeratedValues` and `enumerationDefinitions` for opcode and bitmask
     tables (#103).
   - Optionally export layouts to Kaitai `.ksy` with `doc-ref`.
   - Reasoning: Kaitai, DFDL, ASN.1/ECN, and P4 each fail on one of tooling, little-endian
     support, or data-not-code. Their order terms are precise and recognized.
4. **Timing: adopt UCUM for unit codes and borrow IEC 61360's MIN/NOM/TYP/MAX for limits.**
   - Shape: `{nom, min, max, typ, unit: <UCUM>}`, with the verbatim source tolerance kept in the
     citation.
   - Reasoning: UCUM is the recognized unit-code standard and its license permits use as codes;
     no free standard represents spec tolerances, and the IEC 61360 level names are the
     recognized ones.
5. **Device-level container: no fit; keep the spec format's facts as the container.**
   - Export registers to IP-XACT, and optionally layouts to Kaitai.
   - Treat dt-schema and ACPI as consumer targets.
   - Reasoning: no candidate spans registers, sequences, layouts, and timing, and the
     broadest one (IP-XACT) is already adopted for its part.
