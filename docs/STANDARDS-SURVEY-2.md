<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Standards survey 2: public CSR JSON formats and inter-block connectivity

Research agent report, 2026-10-14. It extends `docs/STANDARDS-SURVEY.md` (the first survey) and
does not repeat it: SystemRDL access properties, SVD register fields, OpenTitan `swaccess`,
UVM, PSS, DFDL and the IP-XACT field vocabulary are covered there. It answers three questions
about the design section "Precise payloads: standard vocabularies (proposed 2026-10-14)" in
`docs/SPEC-FORMAT.md`.

**Legend.** **[P]** I read the primary source myself (a spec page, a schema file, a source
file, or `gh api` repository metadata). **[S]** a secondary source (a search-result summary, or
a page about the thing rather than the thing itself). **[U]** unverified: I could not fetch the
source, or I am inferring. Licenses tagged "GitHub API" are the `license.spdx_id` that
`gh api repos/<owner>/<repo>` returned on 2026-10-14; `NOASSERTION` means GitHub could not
classify the license, and I then read the license file.

**Terms**

- **CSR** — control and status register.
- **Specifier** — in Devicetree, the list of numbers (cells) that a consumer writes after a
  provider's phandle to say which of the provider's outputs it means: `<&gic GIC_SPI 121
  IRQ_TYPE_LEVEL_HIGH>`. The provider's `#…-cells` property says how many cells there are.
- **Provider / consumer** — Devicetree's names for the node that supplies a clock, reset,
  interrupt, DMA channel or power domain, and the node that uses it.
- **Nexus node** — a Devicetree node that translates specifiers from one domain to another
  (`interrupt-map`, `gpio-map`).
- **dt-schema** — devicetree.org's validator and its core JSON-Schema-in-YAML schemas.
- **CCF** — the Linux Common Clock Framework, the kernel's clock-tree model.
- **IP-XACT design** — the IP-XACT document that instantiates components and connects their
  bus interfaces and ports (as opposed to a `component`, which describes one block).

---

## A. Public "CSR JSON" style register formats

### Finding 0: there is no standard JSON register format

The SystemRDL compiler's own JSON example says so: "Since there isn't really a "standard" JSON
schema available, we'll make up our own simple one." Its example supports no arrays, and "Only
the field's "reset" and "sw" properties are encoded" [P]
(https://systemrdl-compiler.readthedocs.io/en/stable/examples/json_exporter.html). The PeakRDL
community-plugin page lists 23 plugins and no JSON exporter or importer; its only format
converter is PeakRDL-opentitan (SystemRDL to and from OpenTitan hjson) [P]
(https://peakrdl.readthedocs.io/en/latest/community.html). I found no "PeakRDL-json" package.

The public JSON formats fall into three families:

1. **Address exports** for software (LiteX `csr.json`): base addresses and register addresses,
   no field semantics.
2. **IP-XACT vocabulary written as JSON** (rocket-chip `RegFieldDesc` JSON, SiFive DUH JSON5).
3. **RTL-generator inputs** (Corsair, OpenTitan hjson, hdl-registers): full field semantics plus
   hardware-side hooks that a driver never sees.

### A1. LiteX `csr.json`

- **Maintainer, license:** enjoy-digital/LiteX; BSD-2-Clause (LICENSE file read; `export.py`
  carries `SPDX-License-Identifier: BSD-2-Clause`) [P]
  (https://github.com/enjoy-digital/litex, https://raw.githubusercontent.com/enjoy-digital/litex/master/litex/soc/integration/export.py).
- **It is literally called `csr.json`:** the builder defaults to `<output_dir>/csr.json`, and the
  CLI flag is `--soc-json`/`--csr-json`, "Write SoC mapping to the specified JSON file" [P]
  (https://raw.githubusercontent.com/enjoy-digital/litex/master/litex/soc/integration/builder.py,
  lines 142 and 661). This is the most likely public referent of the phrase "CSR JSON".
- **Carries** (`get_csr_json`) [P]: `csr_bases` (region name → base address), `csr_registers`
  (per register: `addr`, `size` in bus words, `type` `ro` or `rw`), `constants` (lowercased SoC
  constants, which include `<name>_interrupt` interrupt numbers: `soc.py` calls
  `add_constant(name + "_INTERRUPT", loc)`,
  https://raw.githubusercontent.com/enjoy-digital/litex/master/litex/soc/integration/soc.py),
  `memories` (`base`, `size`, `type`) and `cores` (class name per region).
- **Loses against IP-XACT 2022:** everything below the register: no fields, no reset values, no
  enumerations, no write or read side effects, access only `ro`/`rw`. LiteX's SVD exporter in
  the same file does emit fields and enumerated values [P] (same `export.py`).
- **Converters:** none to IP-XACT found. Path: LiteX → SVD (built in) → our format, or read the
  Python `CSRField` objects directly [U for anything beyond the SVD exporter].

### A2. Corsair

- **Maintainer, license:** esynr3z/corsair; MIT (GitHub API); last push 2025-05-24; README says
  "The code for version 1.x is frozen" [P] (https://github.com/esynr3z/corsair).
- **Carries** [P] (https://corsair.readthedocs.io/en/latest/regmap.html): a flat `regmap` list;
  register `name`, `description`, `address`, `bitfields`; field `name`, `description`, `reset`,
  `width`, `lsb`, `access`, `hardware`, `enums` (`name`, `description`, `value`). Access values:
  `rw`, `rw1c`, `rw1s`, `ro`, `roc`, `roll`, `rolh`, `wo`, `wosc`. Hardware options: `i o c s e
  l a q f n`, combinable as a string such as `ioel`. JSON and YAML carry the same content.
- **Loses:** arrays, hierarchy, reset types, write-value constraints, reserved fields.
  `roll`/`rolh` (latch low/high) and `wosc` (write-one-self-clear) have no single IP-XACT
  property: `wosc` is closest to `write-only` plus a hardware clear, and the latches are
  `volatile` plus prose [U: mapping is mine].
- **Converters:** none to or from IP-XACT or SystemRDL listed [P] (README lists JSON, YAML, txt
  inputs and HDL, C, Python, Markdown, AsciiDoc outputs).

### A3. rocket-chip `RegFieldDesc` JSON (Chisel)

- **Maintainer, license:** chipsalliance/rocket-chip; GitHub reports NOASSERTION; the repository
  carries `LICENSE.Berkeley` and `LICENSE.SiFive`, the latter Apache-2.0 [P] (`gh api`).
- **Carries** [P]
  (https://raw.githubusercontent.com/chipsalliance/rocket-chip/master/src/main/scala/regmapper/RegFieldDesc.scala):
  `name`, `desc`, `group`, `groupDesc`, `access` (`R`, `W`, `RW`), `wrType` (`ONE_TO_CLEAR`,
  `ONE_TO_SET`, `ONE_TO_TOGGLE`, `ZERO_TO_CLEAR`, `ZERO_TO_SET`, `ZERO_TO_TOGGLE`, `CLEAR`,
  `SET`, `MODIFY`), `rdAction` (`CLEAR`, `SET`, `MODIFY`), `volatile`, `reset`, `enumerations`,
  `addressBlock`. The source says this "is similar to the IP-XACT concept of a Field" and names
  "The IP-XACT concept of an addressBlock". `RegField.toJson` writes `byteOffset`, `bitOffset`,
  `bitWidth`, `name`, `description`, `resetValue`, `group`, `groupDesc`, `accessType`,
  `writeType`, `readAction`, `volatile`, `enumerations` [P]
  (https://raw.githubusercontent.com/chipsalliance/rocket-chip/master/src/main/scala/regmapper/RegField.scala).
- **Loses:** reset types, write-value constraints, `reserved`, `writeOnce`, `testable`.
- **Converters:** none found; the values are IP-XACT's `modifiedWriteValue` and `readAction` in
  upper snake case, so the mapping is mechanical.

### A4. SiFive DUH (JSON5)

- **Maintainer, license:** sifive/duh, duh-schema, duh-ipxact; all Apache-2.0 (GitHub API);
  duh-schema pushed 2026-09-17 [P].
- **What it is:** "a suite of tools for packaging reusable hardware components and designs",
  documents in JSON5 [P] (https://github.com/sifive/duh). The schema's modules mirror IP-XACT's
  documents one for one: `component`, `design`, `busDefinition`, `abstractionDefinition`,
  `busInterface`, `memoryMap`, `register`, `registerFile`, `field`, `enumeratedValues`,
  `catalog` [P] (`gh api repos/sifive/duh-schema/git/trees/HEAD`).
- **Field properties** [P] (`lib/field.js` in duh-schema): `name`, `description`, `bitOffset`,
  `bitWidth`, `resetValue`, `resetMask`, `volatile`, `access`, `enumeratedValues`,
  `modifiedWriteValue` (the nine IP-XACT values, verbatim camelCase), `readAction` (`clear`,
  `set`, `modify`), `testable`, `reserved` (commented "ipxactish").
- **Loses against 2022:** one reset (no reset types), no `writeValueConstraint`, no
  `fieldAccessPolicies` [P, from the same file].
- **Converters:** `duh-ipxact`, "Import / export bridge between DUH and IP-XACT / SPIRIT":
  export to 1685-2009 and SPIRIT 1.4; import from IP-XACT with no version named [S, README via
  WebFetch] (https://github.com/sifive/duh-ipxact). Also `duh-systemrdl`, `duh-svd` [P, listed in
  the duh README].
- **Relevance:** DUH is a public precedent for D24 — IP-XACT names, verbatim, in a JSON-family
  document validated by a JSON Schema.

### A5. OpenTitan hjson (what the first survey did not cover)

The first survey covered `swaccess`, `hwaccess`, `resval`, `enum`. Additional register-level
features [P] (https://opentitan.org/book/util/reggen/index.html): `multireg` ("group defining
registers generated from a base instance", `count`, `cname`); `window` ("an address range for
something other than standard registers"); `skipto`, `reserved`; `hwext` ("stored outside of
the register module"); `hwqe`/`hwre` (write/read pulse to hardware); `regwen` (a register whose
writes are gated by another, "a one-bit `rw1c` register that defaults to true"); `tags`.
Block-level keys: `interrupt_list`, `alert_list`, `wakeup_list`, `reset_request_list`,
`clocking` (clock and reset pairs), `bus_interfaces`, `inter_signal_list`,
`available_input_list` and friends, `param_list` [P, same page]. The top-level file is covered in
B below. Converter: PeakRDL-opentitan (SystemRDL ↔ hjson) [P, community page].

### A6. hdl-registers, RgGen, Cheby

- **hdl-registers:** BSD-3-Clause (GitHub API), pushed 2026-10-06 [P]; registers defined "in a
  TOML/JSON/YAML data file or the Python API" [S]
  (https://pypi.org/project/hdl-registers/). Field vocabulary not read [U].
- **RgGen:** MIT (GitHub API), pushed 2026-09-11 [P]. Format and converters not read [U].
- **Cheby (CERN, YAML):** the GitLab page returned a bot-protection "Access Denied" page;
  unverified [U] (https://gitlab.cern.ch/be-cem-edl/common/cheby).
- **cocotb:** no register format of its own found; PeakRDL-cocotb-ralgen converts SystemRDL for
  cocotb [P, community page].

### A7. Converters to and from IP-XACT (summary)

| Tool | License | Direction | Versions |
| --- | --- | --- | --- |
| PeakRDL-ipxact | LGPL-3.0 | SystemRDL → IP-XACT | 2009, 2014 (first survey) |
| PeakRDL-ipxact importer | LGPL-3.0 | IP-XACT → SystemRDL | namespace regexes accept SPIRIT, `spirit/1685-2009` and any `accellera.org/XMLSchema/IPXACT…` URI "not strict about the exact version" [P] (https://raw.githubusercontent.com/SystemRDL/PeakRDL-ipxact/main/src/peakrdl_ipxact/importer.py). Whether 2022 elements import correctly: [U] |
| duh-ipxact | Apache-2.0 | DUH ↔ IP-XACT | export 2009 and SPIRIT 1.4 [S] |
| Kactus2 | GPL-2.0 | editor, 2014 and 2022 | first survey |
| Corsair, LiteX, rocket-chip, hdl-registers | — | none found | — |

### A8. Answer: what an unknown internal CSR JSON would map to

**IP-XACT is the realistic pivot, as a vocabulary more than as a file.** Every public JSON format
I read either uses IP-XACT's field semantics outright (rocket-chip, DUH) or uses token sets
(Corsair `rw1c`/`roc`, OpenTitan `rw1c`/`rc`, LiteX `ro`/`rw`) that map onto `access` +
`modifiedWriteValue` + `readAction` with a small table, which the first survey already showed
for SystemRDL and UVM. SystemRDL is the realistic second: it has the mature open compiler, and
PeakRDL-ipxact goes both ways. A file-level IP-XACT round trip is weaker than the vocabulary
mapping: the open converters stop at 2014, and the formats that lack reset types and write
constraints lose nothing in the mapping but gain nothing either. For an internal format, the
cheap path is a direct adapter from that JSON to our YAML, with its access tokens mapped to
IP-XACT values once and checked once.

**Register properties JSON formats carry that the proposed design does not:**

| Property | Where seen | Driver-relevant? | IP-XACT 2022 element |
| --- | --- | --- | --- |
| Address-map hierarchy: block bases, register files, more than one block | LiteX `csr_bases`, rocket-chip `addressBlock`, DUH `registerFile`, OpenTitan `base_addr` | yes | `memoryMap`, `addressBlock`, `registerFile`, `bank` [P, memoryMap.xsd] |
| Register arrays | OpenTitan `multireg`, LiteX `size` (multi-word), SVD `dim` | yes | `array`/`dim`, `stride` [P] |
| Memory windows (buffers, FIFOs inside the map) | OpenTitan `window`, LiteX `memories` | yes | `addressBlock` `usage`, `memoryMap` [P] |
| Write-enable lock by another register | OpenTitan `regwen` | yes | no exact element; 2022 `accessPolicies` with `modeRef` is mode-based [U whether it fits] |
| Aliases | OpenTitan `alias_target` | yes | `aliasOf` [P] |
| Reset value undefined for some bits | OpenTitan `resval: x` | yes | `reset` `mask` (already in the design as `mask?`) |
| Grouping for documentation | rocket-chip `group`/`groupDesc` | minor | none (prose) |
| Register stored outside the block (`hwext`), write/read pulses (`hwqe`, `hwre`), hardware access (`hwaccess`, Corsair `hardware`) | OpenTitan, Corsair | rarely: hardware writes imply `volatile` | `volatile`; the rest are RTL implementation, not driver facts |
| Interrupt numbers as constants | LiteX `*_interrupt` | yes, but belongs to B | — |

IP-XACT 2022's `memoryMap.xsd` also has `broadcasts`, `readResponse`, `accessRestrictions`,
`memoryRemap`, `alternateRegisters`, `testable` [P]
(https://www.accellera.org/XMLSchema/IPXACT/1685-2022/memoryMap.xsd, element list extracted
with grep). The design's exporter writes "one `memoryMap` and `addressBlock` at base 0"; the
first three rows above would need more.

---

## B. Inter-block connectivity

### B1. Devicetree Specification and dt-schema

- **Licenses:** the specification source is `SPDX-License-Identifier: Apache-2.0` (its
  `license.rst`); latest release v0.4, 2023-06-28 [P]
  (https://github.com/devicetree-org/devicetree-specification). dt-schema is BSD-2-Clause (GitHub
  API), and each core schema file carries `SPDX-License-Identifier: BSD-2-Clause` [P]
  (https://github.com/devicetree-org/dt-schema). Linux kernel binding schemas use
  `(GPL-2.0-only OR BSD-2-Clause)` in the kernel's example [P]
  (https://docs.kernel.org/devicetree/bindings/writing-schema.html); kernel `.dtsi` files are
  GPL (`bcm2711.dtsi`: `GPL-2.0`) [P]; `dt-bindings/interrupt-controller/irq.h` is `GPL-2.0 OR
  MIT` [P] (https://raw.githubusercontent.com/torvalds/linux/master/include/dt-bindings/interrupt-controller/irq.h).
- **Where each connection kind is defined:** the specification itself defines interrupts
  (`interrupt-parent`, `interrupts`, `#interrupt-cells`, `interrupt-controller`,
  `interrupt-map`, `interrupt-map-mask`) and generic nexus nodes for "some specifier space such
  as 'gpio', 'clock', 'reset'" [P] (chapter 2 source, sections on interrupts and "Nexus Nodes
  and Specifier Mapping"). Clocks, resets, power domains, pin control and DMA are defined only in
  dt-schema core schemas [P]: `clock/clock.yaml` (`clocks`, `clock-names`, `#clock-cells`,
  `clock-output-names`, `clock-indices`, `assigned-clocks`, `assigned-clock-parents`,
  `assigned-clock-rates`, `protected-clocks`), `reset/reset.yaml` (`resets`, `reset-names`),
  `power-domain/power-domain-consumer.yaml` (`power-domains`, `power-domain-names`),
  `pinctrl/pinctrl-consumer.yaml` (`pinctrl-0…`, `pinctrl-names`), `dma/dma.yaml` (`dmas`,
  `dma-names`), plus `interrupts.yaml`, `iommu`, `opp`, `gpio` [P]
  (https://github.com/devicetree-org/dt-schema/tree/main/dtschema/schemas).
- **Expresses well:** the provider/consumer graph; named inputs on the consumer (`clock-names`,
  `reset-names`); interrupt cascades through `interrupt-parent` chains and nexus translation;
  trigger type and polarity as a specifier cell with shared constants (`IRQ_TYPE_EDGE_RISING 1`,
  `EDGE_FALLING 2`, `EDGE_BOTH 3`, `LEVEL_HIGH 4`, `LEVEL_LOW 8`) [P, irq.h]; a device's
  operational state (`status`: `okay`, `disabled` "might become operational in the future",
  `reserved` "controlled by another software component", `fail`) [P, chapter 2 table].
- **Cannot express, or deliberately leaves out** (the facts a datasheet states that DT omits):
  - **Clock-tree internals.** A consumer names a provider output by index; parents, muxes,
    dividers and their register fields live in driver code. Example: `bcm283x.dtsi` gives
    `uart0` `clocks = <&clocks BCM2835_CLOCK_UART>, <&clocks BCM2835_CLOCK_VPU>` [P]
    (https://raw.githubusercontent.com/torvalds/linux/master/arch/arm/boot/dts/broadcom/bcm283x.dtsi,
    lines 304–312), while the eight-way parent list (`gnd`, `xosc`, `testdebug0`, `testdebug1`,
    `plla_per`, `pllc_per`, `plld_per`, `pllh_aux`), the `CM_UARTCTL`/`CM_UARTDIV` registers and
    the 10.12 divider (`int_bits = 10`, `frac_bits = 12`) exist only in the GPL-2.0+ driver [P]
    (https://raw.githubusercontent.com/torvalds/linux/master/drivers/clk/bcm/clk-bcm2835.c).
    `assigned-clock-parents`/`-rates` record a *chosen* configuration, and the schema forbids
    conflicting settings for a shared clock across consumers [P, clock.yaml description].
  - **Which reset reaches which block.** reset.yaml says the binding exists "to give appropriate
    software access to the reset signals in order to manage the HW, rather than to slavishly
    enumerate the reset signal that affects each HW block" [P]. A reset affecting several blocks
    is put on one node (a bus node, for example), so "reset X clears domain Y" is not
    recoverable.
  - **Power-domain contents and sequencing.** A consumer points at a domain; what else is in it,
    its always-on status, isolation and the on/off order are provider driver code [P for the
    consumer schema; U for "nothing else" beyond the files read].
  - **Pin-mux options not used.** A SoC `.dtsi` lists some groups: `bcm283x.dtsi` has
    `uart0_gpio14` (ALT0), `uart0_gpio32` (ALT3), `uart0_gpio36` (ALT2) and a comment about a
    conflict with `spi1_gpio16` [P, lines 246–272]; the full alternate-function table is in the
    datasheet. Whether a SoC `.dtsi` is complete is a convention, not a rule.
  - **Interrupt specifier meaning** is defined per controller binding ("interrupt domain
    specific") [P, chapter 2], so the numbers are not comparable without the controller's
    binding: `bcm283x.dtsi` writes `interrupts = <2 25>` for the legacy controller, and
    `bcm2711.dtsi` overrides it with `<GIC_SPI 121 IRQ_TYPE_LEVEL_HIGH>` [P, line 1180].
- **Tooling:** `dtc` (compiler); `dtschema` Python package with `dt-validate`, `dt-doc-validate`,
  `dt-mk-schema`; kernel `make dt_binding_check` and `make dtbs_check`, and "dtbs_check will skip
  any binding schema files with errors" [P, kernel writing-schema page]. Lopper (below) reads
  and writes DTS from Python.
- **Per-value citation:** none in the data model. DTS comments survive only in source; `dtc`
  drops them, and lopper's README says compiling to DTB loses source information, with
  `--enhanced` restoring "comments, labels, and symbolic phandles" [P]
  (https://raw.githubusercontent.com/devicetree-org/lopper/master/README.md). A vendor-prefixed
  property could carry a fact id, but a binding with `unevaluatedProperties: false` rejects it
  [U: per-binding]. Citations have to stay outside the DTS, keyed by node path or label.

### B2. System Device Tree (Linaro/Xilinx) and lopper

- **Licenses:** the specification's `index.rst` carries `SPDX-License-Identifier: Apache-2.0`;
  the lopper repository's `LICENSE.md` is the 3-clause BSD license, "Copyright (c) 2020, Xilinx
  Inc. and Contributors" (GitHub reports NOASSERTION) [P]
  (https://github.com/devicetree-org/lopper/tree/master/specification).
- **Adds** [P] (chapters 1 and 2): multiple CPU clusters (`cpus,cluster`), each with an
  `address-map` saying which resources it can address; `indirect-bus` for resources not in the
  parent's address space; per-cluster interrupt controllers, with a device's interrupts "routed
  to both" the R5 and A72 GICs via `interrupt-map`; `/domains` for execution domains and
  resource assignment. Lopper then cuts "a standard devicetree … for each execution domain"
  [P, chapter 1].
- **Relevance:** it is the one DT variant meant to describe the whole SoC rather than one OS's
  view, and it shows one interrupt routed to several controllers. Chapter 2 says nothing about
  clocks, resets, power domains or pin mux [P].
- **Tooling:** lopper is Python 3 (3.10+), reads DTS, DTB and YAML, validates phandles, and has
  memory-overlap warnings [P, README].
- **Per-value citation:** as for DT.

### B3. IP-XACT 2022: design, ports, power domains

From the official 2022 XSDs (Apache-2.0, read in `component.xsd`'s header) [P]
(https://www.accellera.org/XMLSchema/IPXACT/1685-2022/):

- `design` holds `componentInstances`, `interconnections` (bus-interface to bus-interface,
  with `activeInterface`/`hierInterface`), `adHocConnections` (port to port, with
  `internalPortReference`/`externalPortReference`), `monitorInterconnection` [P, design.xsd,
  subInstances.xsd].
- Component `powerDomains`: each `powerDomain` has a name, optional `alwaysOn`, `subDomainOf`
  ("Reference to a power domain defined on this component"), `parameters`,
  `vendorExtensions`; ports carry `powerDomainRef`; a `componentInstance` carries
  `powerDomainLinks` (`externalPowerDomainReference` → `internalPowerDomainReference`) [P,
  component.xsd lines 40–60, port.xsd line 1122, subInstances.xsd lines 339–371].
- Port qualifiers: `isClock`, `isReset` (with `level` `low`/`high`), `isInterrupt` (boolean
  only), `isClockEn`, `isPowerEn` (with `level`), `isRequest`, and others [P,
  commonStructures.xsd lines 50–206].
- `clockDriver`: `clockPeriod`, `clockPulseOffset`, `clockPulseValue`, `clockPulseDuration`;
  component `otherClockDrivers`; `resetTypes` [P, signalDrivers.xsd, component.xsd].
- **Expresses well:** which port connects to which; reset polarity; power-domain nesting and
  always-on; the nominal clock period.
- **Cannot:** interrupt trigger type (the qualifier is a boolean), controller line numbers,
  clock muxes and dividers as structured objects (they are component internals plus registers),
  pin multiplexing, DMA request numbering. It describes *wiring*, not the options software
  chooses among.
- **Tooling:** Kactus2 (GPL-2.0) is the open editor with 2022 support (first survey); Python
  support for 2022 designs is weak (first survey). `xmlschema` validates.
- **Per-value citation:** `vendorExtensions` on `design`, `powerDomain`, and 9 places in
  subInstances.xsd [P, grep count]; `xml:id` attributes elsewhere.

### B4. OpenTitan top-level hjson (a public whole-SoC connectivity model)

`hw/top_earlgrey/data/top_earlgrey.hjson`, Apache-2.0 header [P]
(https://raw.githubusercontent.com/lowRISC/opentitan/master/hw/top_earlgrey/data/top_earlgrey.hjson):

- `power`: `domains: ["Aon", "Main"]`, `default: "Main"`.
- `clocks.srcs`: per source `name`, `aon`, `freq` in Hz, generating `module` and `signal`; then
  derived groups.
- `resets.nodes`: per reset `name`, `gen`, `type` (`ext`, `int`, `top`), `parent`, `domains`
  ("The power domains of a particular reset"), `clk` ("related clock domain for synchronous
  release").
- `module`: per instance `type` (the IP), `clock_srcs` (`{clk_i: "io_div4"}`),
  `reset_connections` (`{rst_ni: "lc_io_div4"}`), `base_addr`.
- `pinmux`: each signal's `connection` is `direct` (to a fixed pad), `manual`, or `muxed`.
- Interrupts and alerts go to `default_plic: "rv_plic"` and `default_alert_handler`.

It is the closest public example of a single file holding clock tree, reset tree, power
domains, instance wiring and pin mux together. It describes one design's configuration
(the RTL is generated from it), has no per-value citation, and is not a standard.

### B5. Zephyr's Devicetree usage

- **License:** Zephyr is Apache-2.0 (GitHub API); bindings are "YAML files" in Zephyr's own key
  structure, not JSON Schema [P]
  (https://docs.zephyrproject.org/latest/build/dts/bindings-syntax.html). Keys include
  `compatible`, `include`, `properties` (with `type`, `required`, `enum`, `min`/`max`, `const`),
  `child-binding`, `bus`/`on-bus`, and `*-cells` to name the cells of a specifier [P].
- **Clock trees in DT:** Zephyr binds hardware constraints that Linux keeps in code.
  `st,stm32h7-pll-clock.yaml` lists the PLL's possible inputs (`clk_hse`, `clk_hsi`,
  `clk_csi`), its formula, and ranges (`div-m` 1–63, `mul-n` 4–512, `div-p` 1–128) [P]
  (https://github.com/zephyrproject-rtos/zephyr/blob/main/dts/bindings/clock/st,stm32h7-pll-clock.yaml).
  The binding holds the allowed values, and a board's DTS picks one.
- **All pin-mux options, pruned by use:** `hal_stm32/scripts/genpinctrl/genpinctrl.py`
  (Apache-2.0) generates, from ST's pin data, a `-pinctrl.dtsi` per package listing every
  option as an `/omit-if-no-ref/` node, such as `usart1_tx_pa9` and `usart1_tx_remap1_pb6` [P]
  (https://github.com/zephyrproject-rtos/hal_stm32, files `scripts/genpinctrl/genpinctrl.py`
  and `dts/st/f1/stm32f103r(8-b)tx-pinctrl.dtsi`). The source data, STM32_open_pin_data
  (BSD-3-Clause, GitHub API), "provides all the information required for the pin configuration"
  and is "a subset of STM32CubeMx internal database" [P]
  (https://github.com/STMicroelectronics/STM32_open_pin_data).

### B6. Others, briefly

- **CMSIS-SVD:** `<interrupt>` has `name`, `description`, `value` (the "enumeration index") and
  nothing else: no trigger, priority, controller or routing; no elements for clocks, resets,
  power domains, pin mux or DMA requests [P]
  (https://open-cmsis-pack.github.io/svd-spec/main/elem_peripherals.html). CMSIS-Pack's
  device description was not checked [U].
- **SystemRDL:** interrupts are *field* properties: `intr`, level by default, `posedge`,
  `negedge`, `bothedge`, `nonsticky`, `enable`/`mask`, `haltenable`/`haltmask` [P, as
  documented by PeakRDL-regblock] (https://peakrdl-regblock.readthedocs.io/en/latest/props/field.html).
  It describes how a status bit latches inside a block, not where the line goes. No clocks,
  resets, power domains or pin mux [U beyond that page].
- **ACPI:** read-only license, as the first survey found; its interrupt resource descriptors
  and power resources are AML, not data. Not pursued.

### B7. Summary table

| Kind | DT / dt-schema | System DT | IP-XACT 2022 design | OpenTitan top | Zephyr DT | SVD |
| --- | --- | --- | --- | --- | --- | --- |
| Interrupt line, controller, cascade | yes | yes, several controllers | wiring only | to one PLIC | yes | number only |
| Trigger and polarity | yes (`IRQ_TYPE_*`) | yes | no | no | yes | no |
| Clock consumer edges | yes | as DT | ports | yes | yes | no |
| Clock tree internals (parents, mux, dividers) | no (driver code) | no | no | sources and groups | partly, in bindings | no |
| Reset lines | yes, deliberately incomplete | as DT | ports, polarity | tree with domains | yes | no |
| Power domains | consumer edge only | as DT | domains, nesting, always-on | list | as DT | no |
| Pin mux | chosen groups | as DT | no | direct/muxed | all options (STM32) | no |
| DMA request lines | yes (`dmas`) | as DT | no | no | yes | no |
| Every possible option, not one board's choice | no | no | no | no | pin mux only | — |
| Per-value citation | no | no | `vendorExtensions` | no | no | no |
| License | Apache-2.0 spec, BSD-2 schemas | Apache-2.0 spec, BSD-3 tool | Apache-2.0 XSD; standard paywalled (first survey) | Apache-2.0 | Apache-2.0 | Apache-2.0 |

---

## C. Facts about hardware versus one board's configuration

**The relation.** Devicetree describes a configuration: which inputs a device uses and, through
`assigned-clock-*`, `pinctrl-0` and `status`, what was chosen. A spec of facts describes what the
hardware allows, with a citation for each option. The two meet in the SoC `.dtsi`, which already
mixes the two: instances with `status = "disabled"` until a board enables them, and some pin
groups offered for boards to pick (B1). Zephyr goes further for pins, generating every option and
letting `/omit-if-no-ref/` drop the unused ones (B5), and it puts allowed ranges in bindings
(B5). So a fact spec maps onto DT as: **instance and connection facts → SoC `.dtsi` content;
option facts → labeled alternatives a board selects; allowed values and constraints → binding
schemas, not DTS.** Clock-tree internals and "which reset clears which block" have no DT home at
all (B1).

**Recommended model: own records, DT vocabulary for the connection edges, CCF names for clock
internals, IP-XACT for the registers they point at.**

1. **Connection edges** (interrupts, clocks, resets, power domains, DMA requests) as typed facts
   in DT's terms: consumer instance, consumer input name (DT's `*-names` value), provider
   instance, provider output (specifier cells, with the cells *named* the way Zephyr's `*-cells`
   names them), plus the interrupt trigger as one of DT's five `IRQ_TYPE_*` meanings. Driver
   writers, Linux, Zephyr, U-Boot and Fuchsia's board files all read this vocabulary, and each
   edge stays a fact with `support`.
2. **Options** as separate facts, one per alternative (a pin function per pad and ALT number, a
   clock mux parent per selector value), each with its own citation; a board spec selects among
   them. This is the shape that neither DT nor IP-XACT has (B7, "every possible option").
3. **Clock-tree internals** in the CCF's basic types: `fixed-rate`, `gate`, `divider`, `mux`,
   `fixed-factor`, `fractional-divider`, `multiplier`, `composite`, with parents [P, the struct
   names in `clk-provider.h`] (https://raw.githubusercontent.com/torvalds/linux/master/include/linux/clk-provider.h).
   Each node points at the register field facts that control it (`#reg-cm-uartctl.src`), so the
   IP-XACT register design and the connectivity model join through fact references. Using these
   type names copies no GPL code [U: a judgment, not legal advice].
4. **Resets and power domains:** own records saying what each reset clears and what each domain
   contains (OpenTitan's `resets.nodes` with `parent`, `domains`, `clk` is a good public shape;
   IP-XACT's `alwaysOn` and `subDomainOf` names fit power domains).

IP-XACT design connectivity is not recommended as the model: no trigger types, no line numbers,
no pin mux, no options, weak open tooling (B3).

**Is a DTS export a realistic conformance check?** Partly. Exporting a SoC `.dtsi`-like fragment
and running `dt-validate` against the kernel's binding for each `compatible` checks *form*: cell
counts against the provider's `#…-cells`, names against the binding's `enum`, required
properties present. It needs the provider nodes in the same tree, a binding for every
compatible (kernel bindings are dual GPL-2.0-only OR BSD-2-Clause, so a BSD-licensed copy is
usable), and `dtc`. It cannot check that the values are true. The stronger and cheaper check is
a **differential one**: compare the exported edges with the upstream `.dtsi` that facts already
cite through `DT` anchors (SPEC-FORMAT "Anchors"), and report each disagreement, e.g. our
`uart0` interrupt against `bcm2711.dtsi`'s `<GIC_SPI 121 IRQ_TYPE_LEVEL_HIGH>`. Recommended
order: differential comparison first, `dt-validate` second, and only for instances whose
compatible has a kernel schema.

---

## Recommendations

- **A.** Keep IP-XACT (D24) as the pivot for any CSR JSON, internal or public, and treat
  SystemRDL as the second route. Reason: every public JSON register format I read either uses
  IP-XACT's field semantics outright (rocket-chip, DUH) or maps onto them with a small table,
  and no standard JSON format exists.
- **A, follow-up.** Add address-map hierarchy, register arrays and aliases to the register
  model before the exporter unit. Reason: they are the driver-relevant properties the JSON
  formats carry and the design lacks, and IP-XACT 2022 has elements for all three.
- **B.** Use DT/dt-schema vocabulary for connection edges, own records for the facts DT omits
  (clock internals, reset reach, domain contents, unused options), and treat IP-XACT design,
  SVD and SystemRDL as non-fits. Reason: DT has the only widely used, openly licensed vocabulary
  for interrupt, clock, reset, power-domain, pin and DMA edges, and its schemas say outright that
  they leave out what a datasheet states.
- **C.** Model *all* options as cited facts that a board selects from, and export a DTS
  fragment checked first against the cited upstream `.dtsi` (differential) and second by
  `dt-validate`. Reason: DT describes one chosen configuration, and dt-schema checks shape, not
  truth.

### Parts of the proposed design the findings would change

1. **Export (`spec.py export ipxact`):** "one `memoryMap` and `addressBlock` at base 0" cannot
   carry several blocks, arrays or windows; emit one `addressBlock` per block (A8).
2. **Register model (Units of work 1):** add optional `dim`/`stride` (arrays), block grouping,
   `aliasOf`; `resets[].mask` (already present) covers undefined reset bits; a write-enable lock
   (`regwen`) has no IP-XACT element and would need an extension or a `relates` link (A8).
3. **Instances (schema `instance`, `irq`):** `irq.trigger` is free text today; make it an enum of
   DT's five `IRQ_TYPE_*` meanings. `irq.kind` (`SPI`, `PPI`, `extended`) is GIC-specific;
   generalize to controller plus named specifier cells. `clocks` is a list of consumer names
   today (`[uartclk, apb_pclk]` in the fixture); each entry needs a provider and specifier. Add
   `resets`, `power_domains`, `dmas` and pin-function edges in the same shape. This is outside
   the "Precise payloads" section and would be a new section or design note.
4. **New payload kinds** for clock nodes (CCF types), reset and power-domain records, and pin
   option tables, each linking to register field facts.
5. **No change** to D23, D25, D26, D27 or D28. D24 gains two public precedents (rocket-chip,
   DUH) for IP-XACT names verbatim in JSON-family data.

Files read for this survey (OpenTitan top_earlgrey.hjson, six dt-schema core schemas, four
Devicetree specification chapters, eight IP-XACT 2022 XSDs, Linux bcm283x.dtsi and bcm2711.dtsi)
were read with grep or sed only and are not kept in this repository.
