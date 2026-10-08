<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Board spec format

The contract between a **board spec** (the data), `board-expert` (the reader), `board-spec-scaffold`
(the author), and any vendor skill that overlays private material. Every rule the reader relies on is
stated here; the skills point at this file instead of restating it.

## Terms

- **Board spec** — a Markdown file with YAML frontmatter describing one piece of hardware: a board, an
  SoC, a companion chip, or an IP block. Cited facts plus pointers to sources, documents, and tools;
  never source code. Distinct from a *driver spec* (`peripheral-spec`),
  which describes one peripheral's programming model for an implementer.
- **IP spec** — a spec of kind `ip`: one silicon IP block (a PL011 UART, a DesignWare `dwc3` USB
  controller, a GIC-400) independent of any SoC. Its authorities are the IP databook and the public
  standards the block implements; its map is the mainline Linux driver.
- **Instance** — a row in an SoC or chip spec's `instances:` table: one placement of an IP block at
  an address, with its interrupt, clocks, and per-SoC quirks. The IP spec is the binding; the
  instance is the node.
- **Anchored / generic** — the two ways an IP spec resolves. *Anchored*: through a board, so the
  Linux tree is the board's repository at its ref and the instance facts apply. *Generic*: the IP
  spec alone, from mainline Linux at head plus the public standards, with no instance facts.
- **Needs decision** — the report block a subagent-role skill returns when a fork it cannot resolve
  blocks the work. Subagents never ask the user; the orchestrator turns this block into structured
  questions. See `QUESTIONS.md`.
- **Root** — a directory holding a `board-specs.yaml` marker. Every `*.spec.md` below it is a spec.
- **Accepts list / license gate / placement rule** — a root marker's `accepts:` names the SPDX
  licenses its specs' sources may carry; the license gate (`anchor_check.py --root` for
  peripheral specs, `spec_check.py --require-license` for board specs' `resources.repos`) fails
  a spec citing a source the list does not include; the placement rule says which
  repository a spec belongs in. **SPDX** is the standard license-identifier language
  (`GPL-2.0-only`, `GPL-2.0 OR MIT`). See *The root marker*, and driver-lab's `GLOSSARY.md`.
- **Peripheral spec** — a spec of one device's programming model whose facts are anchored to
  source lines at a **pin** (a named source tree at a commit) or to documents; written by
  `peripheral-spec`. See *Peripheral specs in a licensed root*.
- **Layer** — a root's position in the merge order: `public`, `ip-vendor`, `soc-vendor`, `product`,
  `local`. Declared in the root marker.
- **Overlay** — a spec file that adds to another spec instead of standing alone (`overlays: <id>`).
  Vendor and bench-local material is always an overlay.
- **Stub** — a short skill named `<board>-expert` whose content is trigger keywords and a spec id. It
  exists so the harness's skill matching finds the board by name and so consumers can call the expert
  by a stable name. Its description starts with the prefix "Board expert for" and contains the
  sentence "A stub over the `<id>` board spec": consumers match the prefix, and the checker's
  `--stubs-from` finds stubs by the sentence.
- **Cache** — the out-of-tree directory `~/src/<cache>/` where the expert clones reference source.
- **Provenance tag** — the class of authority behind a fact. This format defines `[databook]`,
  `[standard]`, `[rtl]`, `[DT]`, `[src]`, `[doc]`, `[hardware]`, `[press]` and `[inference]`;
  testing against a device model adds `[emulated]`; `[source-observed]` is defined by an
  extension. A fact read from code is `[src]` when the code is a repository the spec pins to a
  commit under a license its root accepts (*Facts read from source*); otherwise (a tree the root
  does not accept, a prebuilt tree's file listing, a ref that is a branch) a report cites it by
  `<repo>@<commit>` file and line, and a spec uses it only as a cited premise of an
  `[inference]`, or under a class an extension defines. What each class is trusted for, what that
  trust assumes, and how conflicts between classes are recorded is in `DESIGN.md`, "Evidence
  model". The classes, with what falls in each:
  - `[databook]` — the IP databook, TRM, or datasheet; cite the section.
  - `[standard]` — a public standard or architecture specification (ARM ARM, GICv3, PSCI, USB, IEEE
    802.3, the 16550 register model, the arm64 boot protocol in `booting.rst`); cite the clause.
  - `[rtl]` — the hardware design itself: RTL such as Verilog or VHDL, or a register description
    generated from it (IP-XACT, SystemRDL). Always followed by a parenthetical naming the design,
    its revision, and the module, so `[rtl]` (usb2_wrap r2p1, `ctrl_regs`) is complete. It is the
    strongest authority for digital register behavior on the revision it names, and says nothing
    about analog or electrical behavior, firmware, or board wiring.
  - `[DT]` — a value read out of a device tree. Always followed by a parenthetical naming the file it
    came from and, when that file is not a source `.dts`/`.dtsi` (a decompiled production DTB or an
    entry in a DTBO image), where the blob came from; the origin may be the `name` of a
    `resources.repos` entry declared once, so `[DT] (lga-b0.dtb, laguna-kernel-prebuilts)` is
    complete.
  - `[src]` — read from source code at a pinned commit: what the cited code defines or does (a
    constant's value, the value a register write stores, the order of operations in that code, a
    file the tree carries). Always followed by a parenthetical holding one or more anchors in
    `peripheral-spec`'s grammar, `[src:<repo>: path:L1-L2 (symbol)]`, each naming a
    `resources.repos` entry of the same spec file that carries a full commit `ref` and a
    `license:` the root accepts. It is a fact about the code. That the hardware requires what the
    code does, or that a shipped product runs this code, is an `[inference]` whose premises are
    the anchors. Needs no `TODO (verify on hardware)`. See *Facts read from source*.
  - `[doc]` — a project's or vendor's own published documentation: a vendor's official
    specification page, a platform documentation site, a repository README, a commit message, a
    patch cover letter, or a maintainer's reply on a list. Always followed by a parenthetical naming
    which, so a store page, a platform guide, and a cover letter cannot be confused.
  - `[hardware]` — measured on a live board; say which board and how.
  - `[press]` — third-party press, teardowns, reviews, and marketing claims that appear nowhere in
    the vendor's own documentation (a modem part named only by reviewers, a GPU model, clock speeds
    from a launch article). Allowed in a fact bullet only with `TODO (verify on hardware)`, and
    freely in Orientation prose.
  - `[source-observed]` — defined by an extension, not by this format. The checker accepts it and,
    as for `[press]`, requires `TODO (verify on hardware)`.
  - `[inference]` — concluded rather than read: no authority states it, and the fact follows from
    premises that do. "The driver programs this register before releasing reset" is a fact about
    the driver; "the hardware requires this ordering" is `[inference]`. Always followed by
    a parenthetical giving the **premises and the derivation** — what was observed, each premise
    carrying its own class, and why the conclusion follows — and always with `TODO (verify on
    hardware)`, which names the verification method. State the confidence in the bullet where it is
    not obvious. An inference is the one class whose support is an argument rather than a citation,
    so the argument has to be on the page.
  - `[emulated]` — observed on a device model (QEMU or another emulator), not on silicon: a
    register value read back, a gap in a trace, frames in a capture. Always followed by a
    parenthetical naming the model, its version and the run IDs the observation comes from, the
    way `[hardware]` names the board, so `[emulated]` (QEMU 10.2.1 `e1000`, runs
    `e1000-l02f1-20260925-01` r001–r010) is complete; a spec that keeps its observations in a
    numbered table carrying the version and run IDs may point at the entry instead, so
    `[emulated]` (§12.5 EM2) is also complete. Phrased as what was observed from outside
    the model, never as the model's mechanism. A model result is never a hardware requirement
    and never the sole authority for a fact: it stands beside another class (the databook the
    model departs from or confirms), or it is one premise of an `[inference]`. Always with
    `TODO (verify on hardware)`, because a model can accept programming the silicon would not.
    Adopted 2026-09-25 from its use in L02 (SF-1; see `DESIGN.md`, "Evidence model").
- **Series** — a patch series on a mailing list that adds or changes device trees or drivers before
  it is merged. A `resources.series` entry; a map, never an authority.
- **Variant** — a model of a board that shares the SoC and most facts with a base model (a "Pro"
  phone, a board revision). Listed under `variants:` on the base spec, or a spec of its own with
  `variant_of:` when its board facts differ materially.
- **Verification record** — `<root>/resources/<id>.verify.md`, where `<root>` is the directory
  holding the root marker `board-specs.yaml` (not the repository top): the verdicts a fresh verifier
  reached when it re-derived every fact bullet from the authority it cites, kept outside the spec so
  no reader spends context on it. Written by `spec-verifier` as the scaffold's last step and on
  demand; the checker reads only its frontmatter. See *Verification*.

## What a spec is, and is not

A spec carries cited facts and pointers to where the sources live: the *where* and the *what*. It
may live in a target OS tree next to the code it describes, or in a spec repository whose license
fits the sources it cites (*The root marker*). The *how* (investigation method, report format)
belongs to `board-expert` and is not repeated in a spec.

A spec is not:

- a driver spec (a per-peripheral programming model for an implementer);
- a place for source excerpts or unverified extracts;
- a home for private hostnames, internal tools, or NDA documents when its root's layer is `public`.

## Files

### `board-specs.yaml` — the root marker

```yaml
layer: public                 # public | ip-vendor | soc-vendor | product | local
name: driver-porting          # optional; shown in reports
roots: []                     # optional; further roots, relative to this file or absolute
license: Apache-2.0           # optional; SPDX expression for this root's own license
accepts: [Apache-2.0, MIT, BSD-3-Clause]  # optional; SPDX identifiers anchored sources may carry
```

**License fields.** `license:` and `accepts:` are for the published spec repositories, one per
license (`hardware-specs-gpl`, `hardware-specs-docs`, `hardware-specs-permissive`; created in
milestone LS5 of the license-split plan, not yet public). Which repository a spec goes in is the
**placement rule**: the most restrictive repository among the sources the spec anchors to. The
rule and the "which repo does my spec go in?" table are in `peripheral-spec`, "Where the
spec goes".

- `license:` is an SPDX expression for the root's own license (`GPL-2.0-only`, `CC-BY-4.0`,
  `Apache-2.0`).
- `accepts:` is a list of single SPDX identifiers that the pins of the root's peripheral specs,
  and the `resources.repos` entries of its board specs (the pins of their `[src]` facts), may
  carry; no expressions in the list. `accepts: []` is declared and empty: the root accepts no
  source tree, so its specs cite documents only.
- Identifiers are checked against a short known list (`board-expert/scripts/spdx.py`) and matched
  without regard to case; one not on it is an error (write `LicenseRef-<name>`). `GPL-2.0` is read
  as `GPL-2.0-only` and `GPL-2.0+` as `GPL-2.0-or-later`, and a list naming one does not accept the
  other.
- A marker without these fields still loads, with a warning for each, so older roots (a marker with
  only `layer`) keep working. `spec_check.py --require-license` makes their absence an error; the
  spec repositories run with it.
- `spec_check.py --require-license` is also the license gate for board specs: a
  `resources.repos` entry whose `license:` the root's `accepts:` does not accept is an error
  (`license gate: repos entry 'fw' (GPL-2.0-only), which root … does not accept (accepts: …)`),
  with the same rules as the anchor gate (`OR` passes when either side is accepted, `AND` only
  when every part is). Overlays are gated by the root they live in. Without the flag, a repos
  license is validated as SPDX but not compared with `accepts:`.
- A `[src:]` anchor in a board spec is gated always, not only under `--require-license`: its
  repos entry's license must be accepted, and a root with no `accepts:` or with `accepts: []`
  accepts no `[src]` (*Facts read from source*).
- `anchor_check.py --root <dir>` (`peripheral-spec`) is the **license gate**: it fails
  every anchor whose pin's license `<dir>`'s `accepts:` does not list, and fails outright when the
  marker has no `accepts:`. Its own `--require-license` also requires the marker's `license:` and,
  where `accepts:` is empty, named document anchors. See *Peripheral specs in a licensed root*.

A root is found only through a pointer (see *Roots and layers*). The reader never searches a tree for
markers.

### `<id>.spec.md` — a spec

Found by globbing `**/*.spec.md` below a root. Placement under the root is free: next to the driver the
spec describes, so a driver change and its spec update land in one review under the same owners, or in
a central directory. The filename is a convention; the frontmatter `id` is what resolves.

**Ids.** An `id` (and every `aliases`, `parts`, `variant_of`, and `overlays` value) is normalized:
lowercase, spaces and underscores become hyphens, only `[a-z0-9-]`, so "Tensor G5" is `tensor-g5`
and "RK3588S" is `rk3588s`. The marketing name is the id; every codename is an alias (`aliases:
[laguna, lga]`) and a trigger.

```yaml
---
kind: board                   # board | soc | chip | ip
id: rpi5                      # normalized (see Ids); unique across every root the reader sees
name: Raspberry Pi 5 / Compute Module 5
triggers: [pi 5, raspberry pi 5, rpi5, cm5, compute module 5]
not_triggers: [pi 500]        # optional: a question containing one of these never matches this spec
aliases: []                   # optional: other ids this spec answers to (codenames)
parts: [bcm2712, rp1]         # board (required) and chip (optional): ids this spec composes
cache: rpi5-resources         # <board id>-resources by convention; cloned under ~/src/<cache>/
variants:                     # optional, board only: models that share this spec's facts
  - name: Raspberry Pi 5 (16 GB)
    triggers: [pi 5 16gb]
    shares: [soc, parts, boot, console]
    differs: DRAM size only
    tag: doc                  # optional: the provenance class the row rests on; default doc
    source: Raspberry Pi product page   # optional: which document or listing names the variant
resources:
  repos:
    - name: linux-rpi
      url: https://github.com/raspberrypi/linux
      ref: rpi-6.12.y
      license: GPL-2.0-only
      status: merged          # optional: the default for every file below (unmerged | merged)
      verified: 2026-09-18    # optional: the date the URL and ref were last checked (unquoted is fine)
      fetch: ok               # optional: ok | blocked | truncated | partial, for automated fetchers
      fetch_via: git          # optional: the method that worked (/raw, t.mbox.gz, curl with Wget UA, redirect)
      files:                  # highest-value paths, relative to the repo root
        - arch/arm64/boot/dts/broadcom/bcm2712-rpi-5-b.dts
        - {path: arch/arm64/boot/dts/google/lga.dtsi, status: unmerged, note: "lands with the series"}
      note: "the real Pi 5 device trees and drivers; read for behavior, cite the datasheet"
  series:                     # optional: unmerged patch series that are the public map
    - title: Add Laguna SoC and boards
      url: https://lore.kernel.org/linux-arm-kernel/<message-id>/
      message_id: <message-id>
      target: linux-mainline  # the repo entry it patches
      status: unmerged        # unmerged | merged | superseded
      files: [arch/arm64/boot/dts/google/lga.dtsi]
      note: "a map, never cite: true; the canonical lore URL is bot-challenged, see Paths and URLs"
  docs:
    - title: RP1 peripherals datasheet
      url: https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf
      access: public          # public | internal
      cite: true              # an authority: cite it; the kernel is the map
      verified: 2026-09-18
      fetch: ok
  tools: []                   # usually filled by overlays; see Tools
---
```

`cite: true` marks an authority: cite it; the kernel is the map. `cite: false` or absent means
context or map only; the reader never cites such an entry as authority. A `series` entry can never
be `cite: true`. `status` on a repo or series entry says whether the listed `files` exist at the
`ref` yet (`unmerged` when they do not) and is the default for every file it lists; a `files:`
entry may also be a mapping `{path, status, note}` when one repository carries some of the listed
files and not others (mainline may carry a binding and a driver while the SoC's `.dtsi` is still on
the list). `verified` and `fetch` record when a URL was last checked and whether an automated fetcher
could read it; they make link rot detectable and are optional. `fetch` is `ok` (readable), `blocked`
(refused or bot-challenged), `truncated` (readable but cut short), or `partial` (readable by one
method only); `fetch_via` names the method that worked, so the next fetcher does not rediscover it.
`verified` is an ISO date; unquoted (`verified: 2026-09-18`) is fine under both parsers.

**Quoting.** Both parsers the checker uses reject an unquoted scalar that contains `: ` (a colon
followed by a space) or ends with a colon; a `#` after a space starts a comment. Inside a flow
mapping (`{...}`) an unquoted comma splits the entry and an unquoted `: ` starts a new key; quotes
protect both, so `irq: {kind: SPI, number: 3, note: "shared, see: the GIC spec"}` parses as one
entry with the whole note. Double-quote any `note`, `title`, or `name` that contains a comma, a
colon, or a `#`, as the examples do.

An SoC or chip spec also carries an `instances:` table, one row per placement of an IP block:

```yaml
instances:
  - name: uart10              # the instance name as the device tree or datasheet calls it
    ip: pl011                 # id of the IP spec (the binding)
    reg: 0x107d001000         # CPU-physical base as an integer, or null with a TODO in `note`
    irq: {kind: SPI, number: 121, intid: 153, trigger: level-high, note: "shared by all PL011s"}
                              # null, or a mapping: kind SPI | PPI | extended, integer number,
                              # optional integer intid, optional trigger and note strings (quoted)
    clocks: [clk_uart]        # the DT clock-names values; [] when the DT gives only clock-frequency
    role: debug console       # optional: what this instance is for
    note: "quirks, or TODO (verify on hardware): what is missing"   # quote it: it holds a colon
  - name: cli12_uart
    ip: dw-apb-uart
    reg: 0x3a352000
    irq: {kind: extended, number: 4, parent: gia_lsio, note: "GIA aggregator line, not a GIC SPI"}
```

`irq.kind` is `SPI` or `PPI` when the line goes to the GIC: `number` is the DT interrupt number and
`intid` (optional) the resulting INTID (`32 + number` for an SPI, `16 + number` for a PPI). It is
`extended` when the line goes to a secondary controller or aggregator (`interrupts-extended` in the
DT): `parent` names that controller by its DT label, `number` is the line on that parent, and
`intid` is absent; the parent's own GIC line, if known, goes in `note`.

`clocks` lists the DT `clock-names` values of the instance as the SoC's device tree gives them.
When two public trees disagree (a mainline `.dtsi` with only `clock-frequency`, a production blob
with named clocks), use the mainline names and put the other tree's in `note`; write `[]` when the
DT gives only `clock-frequency` or nothing, and say which in `note`.

Keys by kind:

| Key | board | soc | chip | ip | overlay |
| --- | --- | --- | --- | --- | --- |
| `kind`, `id`, `name`, `triggers` | required | required | required | required | not used |
| `not_triggers`, `aliases` | optional | optional | optional | optional | no |
| `parts` | required | no | optional | no | no |
| `instances` | no | required (may be empty) | recommended | no | optional |
| `variants`, `variant_of` | optional | no | no | no | no |
| `cache` | required | recommended | optional | recommended | no; inherited |
| `resources` | optional | optional | optional | required | optional |
| `overlays` | no | no | no | no | required |

**Variants.** A model that shares the SoC and most board facts with a base model is a row under
the base spec's `variants:` (`name`, `triggers`, `shares`: which fact groups apply, `differs`: one
line, and optionally `tag` and `source`). A row rests on some authority like any fact: the default
is documentation-grade (`tag: doc`, the vendor's own page); a row known only from press says so
with `tag: press`; a row known only from code or the shape of a prebuilt tree is `tag: inference`,
its premise cited as *Provenance tag* says; either names the source in `source`. `src` is not a
`tag` value: a row has no place for the anchors a `[src]` fact needs. A model whose board
facts differ materially (another SoC stepping, another console path, another PMIC) is a board spec
of its own with `variant_of: <base id>`, carrying only
what differs and pointing at the base for the rest.

**Trigger matching.** A trigger matches when it appears in the question as a whole-word substring,
case-insensitively: `pi 5` matches "my Pi 5 board" and not "pi 500". `not_triggers` are checked
first, longest entry first: a question that contains one never matches this spec, whatever its
`triggers` say, so `not_triggers: [pixel 10a]` keeps a "pixel 10" spec away from a product whose
name merely extends it. When a question matches a variant's triggers, or the base's triggers with
a variant name present, the reader treats it as a `Needs decision` between the base and the variant
(`QUESTIONS.md` item 1).

Body: fixed `##` headings per kind. The templates under `board-spec-scaffold/templates/` carry the
exact list; in short:

- **board** — `Orientation`; `Quick-facts` covering what is on the board and how it is wired (which SoC
  and companion parts, boot media and boot configuration, the debug connector and which UART it is,
  power and PMIC, headers and board-level GPIO); `Gotchas`.
- **soc** — `Orientation`; `Quick-facts` covering the addressing model, boot chain and entry state, SMP
  topology, interrupts, debug UART, timers, clocks and power, GPIO and pinmux, DTB runtime patching;
  `Gotchas`.
- **chip** — `Orientation`; `Quick-facts` covering how the chip is reached, its address window, and
  what it carries; `Gotchas`.
- **ip** — `Orientation`; `Standards and databook` (which public standards the block implements and
  which databook or public proxy documents its registers); `Programming model` (register map
  organization, the init / reset / teardown sequences at the level of the databook, DMA and
  interrupt model); `Known variants and quirks` (IP versions, configuration options an SoC may set,
  errata that are public); `Gotchas`. No instance facts: those belong in the SoC spec's
  `instances:` row.

**Tag rules.** Every bullet in a fact section (`Quick-facts`, `Gotchas`, and for an IP spec
`Standards and databook`, `Programming model`, `Known variants and quirks`) ends with its **tag
clause**: one or more tags, each optionally followed by a parenthetical citation, then at most one
closing sentence that starts with `TODO (verify on hardware)`. Put the facts first and the tags
last. **Only the tail clause is a tag clause**: a tag name mentioned in the prose ("every address
here is a decompiled-blob `[DT]` fact") is not a tag, the checker ignores it, and the bullet still
needs a real tag clause at its end. The closing TODO sentence may not contain square brackets; a
tag token inside it would be read as a tag.

```
- **Debug UART.** PL011 `uart10` at `0x10_7D00_1000`, left enabled by firmware. `[DT]`
  (`bcm2712.dtsi`), `[databook]` (DDI 0183). `TODO (verify on hardware)`: the IRQ number.
```

- `[press]`, `[inference]` and `[emulated]` facts, and `[source-observed]` facts (an extension's
  class), must carry `TODO (verify on hardware)`. `[src]` facts need none.
- `[src]` is always followed by a parenthetical holding at least one `[src:<repo>: path:L]`
  anchor; the rules for those anchors are in *Facts read from source*. `[src:]` anchors may also
  appear as premises inside an `[inference]`'s parenthetical, under the same rules.
- `[inference]` is always followed by a parenthetical giving its premises and derivation, so a
  reader can check the reasoning without re-reading the source it was reasoned from.
- `[emulated]` is always followed by a parenthetical naming the device model, its version and the
  run IDs, or a numbered observation in the same spec that carries them, and is never the only
  tag in a tag clause: another class stands beside it, or the
  observation is a premise inside an `[inference]`'s parenthetical (which then carries the tag).
  A bullet whose only authority is a model observation is a lead, not a fact.
- `[doc]` is always followed by a parenthetical naming the page or document, so a store page, a
  platform guide, and a cover letter cannot be confused.
- `[DT]` is always followed by a parenthetical naming the file the value came from (`bcm2712.dtsi`,
  and the node when it helps) and, when the file is a decompiled production DTB or a DTBO entry
  rather than a source `.dts`/`.dtsi`, where the blob came from. The origin may be the `name` of a
  `resources.repos` entry declared once in the frontmatter, so `[DT] (lga-b0.dtb,
  laguna-kernel-prebuilts)` is complete and the spec need not repeat a sentence twenty times. A
  value from a mailing-list `lga-b0.dts` and one from a shipped `lga-b0.dtb` are both `[DT]`; the
  parenthetical, one letter apart, is what tells them apart.
- A **gap bullet** is one whose text, after the optional bold lead-in, starts with
  `TODO (verify on hardware)`; it records what is missing and carries no tag:
  `- **Power.** `TODO (verify on hardware)`: the PMIC part is not recorded here yet.`

### Facts read from source: `[src]`

A board spec states a fact read from source code with the `[src]` class and cites the lines with
anchors in `peripheral-spec`'s grammar ("The anchor grammar"), parsed by its `anchor_check.py`:

```
resources:
  repos:
    - name: rpi-tools
      url: https://github.com/raspberrypi/tools
      ref: 439b6198a9b340de5998dd14a26a0d9d38a6bcac
      license: BSD-3-Clause
...
- **Counter frequency.** The `armstub8-gic` build writes 54000000 to `CNTFRQ_EL0`. `[src]`
  ([src:rpi-tools: armstubs/armstub8.S:53-57 (OSC_FREQ)];
  [src:rpi-tools: armstubs/armstub8.S:110-112 (OSC_FREQ)])
```

- **The pin is the repos entry.** Each anchor names a `resources.repos` entry of the same spec
  file (`[src:<name>: path:L1-L2 (symbol)]`; the unnamed form `[src: path:L]` is an error). That
  entry is the pin: its `ref` is a full commit id (40 lowercase hex digits, or 64 for a SHA-256
  repository), never a branch or tag, and its `license:` is the SPDX expression of the files
  cited through it. An overlay's anchors name the overlay's own entries, since the license gate
  is the overlay's root's.
- **No `Source pin:` line is needed.** `anchor_check.py` reads each repos entry with a `name` and
  a `ref` as a Source pin of that name, so the commit and license are stated once and the two
  checkers gate the same license. A `Source pin:` line naming the same tree is allowed and must
  state the same commit and license, or `anchor_check.py` fails it.
- **The license gate always applies.** `spec_check.py` fails a `[src:]` anchor whose entry's
  license the root's `accepts:` does not accept, and every `[src:]` anchor in a root that declares
  no `accepts:` or `accepts: []` (the documents-only root), with or without `--require-license`.
  A fact whose only source the root does not accept moves to an overlay in a root that does.
- **One anchor per line.** `anchor_check.py` reads a line at a time, so an anchor broken across
  lines is never resolved; the checker fails it. Break the line between anchors instead.
- **What the anchors are checked for.** `spec_check.py` checks what the spec alone shows: the
  anchor's shape, the entry it names, the commit, the license. `anchor_check.py <spec> --root
  <root> --require-license` applies the same gate, and with `--repo <name>=<checkout>` per entry it
  resolves every anchor at the pin (path, line range, symbol, hex literals). A spec repository's
  CI runs it on every board spec carrying a `[src:]` anchor; whether the lines support the claim
  is the verifier's (`spec-verifier` § Board specs).
- **Names and values, not excerpts.** A `[src]` fact may name symbols and constants from the
  code; it never reproduces the code. When the license asks that its notice travel with
  material taken from the source, the spec carries the notice, as the permissive repository's
  overlays do.

### Peripheral specs in a licensed root

A spec repository also holds **peripheral specs**: one device's programming model, written by
`peripheral-spec`, with every fact anchored to source lines or a document. They are not
board specs: name them `<device>-spec.md` (as `peripheral-spec` does), not
`<id>.spec.md`, because `spec_check.py` loads every `*.spec.md` as a board spec.
`anchor_check.py` checks each one. The full grammar is that skill's "The anchor grammar"; what a licensed root relies on is:

- **Named, licensed pins.** `Source pin: <name>@<commit> <SPDX expression>`, one line per source
  tree (`Target pin:` likewise), each with a distinct name; an anchor names its pin
  (`[src:<name>: path:L]`) whenever the side has more than one. The license is what the gate
  reads, so it describes the files cited through that pin. The single unnamed pin with no license
  stays valid outside a licensed root; under `--root`, an unlicensed pin fails.
- **The `docs:` registry.** A list in the spec's YAML front matter, one entry per document:
  `name` (used in anchors), `title`, `url` (recorded, never fetched), `sha256` (64 hex digits of
  the file), optional `pages` (a positive count) and `file` (its name under `--docs-dir`). Anchors
  cite it as `[doc:<name> p.N]`, `pp.N-M` or `§x.y`, with no space after `doc:`; the free-text form
  keeps its space (`[doc: Widget TRM §4.3]`). This is not a board spec's `resources.docs`, which
  lists authorities by title and URL with `cite:` and `access:` and has no hash.
- **The checks a spec repository runs.** `spec_check.py <root> --require-license` on the root and
  its board specs; `anchor_check.py <spec> --repo <name>=<checkout>... --root <root>
  --require-license` on each peripheral spec and on each board spec carrying a `[src:]` anchor,
  with `--docs-dir <dir>` where the documents are at hand. A named anchor whose document is not listed, a page outside `pages`, a malformed registry
  entry, or (with `--docs-dir`) a file whose hash differs are errors.

### Overlays

```yaml
---
overlays: rpi5                # the id this file adds to
resources:
  docs:
    - title: <internal document>
      url: <internal URL>
      access: internal
      via: skill:<vendor>-board-tools     # the skill that knows how to reach it
  tools:
    - kind: bench
      name: <target name on the lab rig>
      via: skill:<vendor>-board-tools
---
```

The body uses the same headings as the spec it overlays. Merging appends each overlay section under a
sub-heading naming the layer and root, so a reader can see where every fact came from.

## Roots and layers

Pointers to roots come from exactly four places. The reader unions them and never walks a tree:

1. `board-expert`'s own `specs/` directory (layer `public`: boards with no home tree, and examples).
2. Any loaded skill that declares a root with one line in its body:
   `board-spec root: <path>` (relative to the checkout root, or absolute). A project skill that
   describes a source tree declares that tree's public root; a vendor skill declares its vendor roots.
3. `board-specs.yaml` at the root of the current checkout, if present. The checkout root is the top of
   the current git checkout, or the directory holding the tree's multi-repository marker when the
   project skill names one.
4. `~/.config/board-specs/board-specs.yaml`, if present (normally layer `local`).

Any marker may list further roots under `roots:`; those are added the same way.

Merge order is by layer, never by skill load order: `public` < `ip-vendor` < `soc-vendor` < `product`
< `local`. Within one layer, roots merge in pointer order (1 to 4 above). Two overlays for the same id
in the same layer is a checker warning.

Merge rules:

- Composition first, then overlays: a board's `parts` are resolved recursively, and every id in the
  composition receives its own overlays.
- Frontmatter lists (`resources.*`, `triggers`, `aliases`) concatenate; a later entry with the same
  `name`, `title`, or `url` replaces the earlier one.
- Frontmatter scalars: later wins. `id`, `kind`, and `parts` cannot be overridden.
- Body: each overlay `##` section is appended under the matching heading of the target, as
  `### Overlay: <layer> (<root name>)`.

## Resolution

Given a question, the reader finds the spec by:

1. A spec id handed to it by a stub or by the orchestrator (`spec: rpi5`, `ip: dwc3`, or both).
2. Otherwise, matching the board, SoC, chip, and IP names in the question against `triggers` and
   `aliases` across every root. A match on an SoC or chip without a board is still a hit; the report
   says the board-level facts are absent.
3. Otherwise, no spec: `board-expert` does its best from public sources, labels the report spec-less,
   and suggests `board-spec-scaffold`.

An IP spec resolves in one of two modes, and the report names which:

- **Anchored** (`spec: <board>` and `ip: <id>`, or an IP named in a question about a board): the
  reader composes the board, finds the `instances:` rows whose `ip` matches, and uses the board's
  Linux repository at its `ref` as the map. If several instances match and the question does not
  say which, that is a `Needs decision`. Mainline is still read for provenance; both commits go in
  the report. A fact present only in the board's tree is cited to that tree as *Provenance tag* says
  for code-only facts (`[src]` when the root accepts the tree's license), because it may be a
  vendor addition rather than the IP's behavior.
- **Generic** (`ip: <id>` alone): the IP spec's own repository entry is the map, by default
  `torvalds/linux` at head with the commit actually read recorded in the report. A caller may pin
  `ref:`. The public standards and databook in the IP spec's `docs` are the authority. The report
  carries no instance facts and says so.

When the question is under-specified in a way that changes the answer (which board variant, which
instance, which tree, anchored or generic), the reader does not guess. It returns a `Needs decision`
block per `QUESTIONS.md`, and the orchestrator asks.

## Paths and URLs

- A path inside a spec is relative to the checkout that contains the spec. A project may use its own
  label convention (for example a `//src/...` prefix) when its project skill defines it.
- Out-of-tree material is a URL plus, for repositories, the `cache` it is cloned under.
- Nothing in a spec points into a cache by absolute path; caches are per machine.
- Arm documents are cited by id (`DDI 0183`, `IHI 0069`, `DEN 0022`); the document id is the
  citation. `developer.arm.com/documentation/<id>/latest` is the citation form to write, **without
  fetching it**: it redirects to `support.arm.com/documentation/<id>/latest`, a portal that
  automated fetchers cannot read. Such an entry carries `fetch: blocked` and no `verified` date, or
  the date the redirect was observed with `fetch_via: redirect`. The rule that every URL in a spec
  was fetched or copied verbatim from a fetched page has this one exception.
- Mailing-list series are cited by their canonical `lore.kernel.org/<list>/<message-id>/` URL, whose
  HTML form is bot-challenged. Record that URL with `fetch: blocked` and a `note` naming the form
  that does work: the `/raw` suffix for one message, `/t.mbox.gz` for the whole thread, fetched
  with a `Wget` user agent. Do not substitute a mirror's URL for the canonical one; a mirror may go
  in `note`.

## Verification

A spec is written once by an author who read the sources as they went. Verification is the separate
pass that re-derives every fact bullet from the authority its tag clause cites, in a fresh context
that never saw the author's reasoning, and records the result **outside the spec**. The procedure is
`spec-verifier` § Board specs (the one statement of it; the scaffold runs it as its last step and it
runs again on demand). This section fixes only what the format and the checker rely on.

- **Location.** `<root>/resources/<id>.verify.md`, where `<root>` is the directory holding the
  root marker `board-specs.yaml` (in the spec repositories, `specs/`, so the record is
  `specs/resources/<id>.verify.md`), one file per spec. An overlay has its own record under its
  own root, named for the id it overlays (`<id>` is the `overlays:` value), and the checker
  treats it like any other record. It is not a spec: the reader
  globs `*.spec.md` only and loads nothing from `resources/`. `board-expert` reports a spec's
  verification status from the record's **frontmatter only**.
- **Frontmatter.** `spec` (the id), `spec_file` (relative to the root), `spec_sha256` (the spec
  file's SHA-256 when the record was written), `verified` (ISO date), `verifier` (free text: which
  agent and harness), `sources` (a list of `{name, commit | url, fetch}` for every repository,
  series, and document actually consulted), and `summary` (`{pass, fail, unverifiable, gap}`,
  integers that equal the verdict lines in the body).
- **Body.** One line per fact bullet, keyed `<Section>/<ordinal> "<bold lead-in>"` (1-based,
  top-level bullets only), never by line number: `PASS` with what was compared against what; `FAIL`
  with the discrepancy and the proposed correction; `UNVERIFIABLE` with the reason; `GAP` for a
  TODO-only bullet. `instances:` rows are keyed `instances/<name>`. No source is reproduced.
- **Staleness.** Any edit to the spec file changes its hash, so the record is stale until the phase
  runs again. Stale is a fact about the record, not a judgment of the edit.
- **What the checker does with it.** No record: warning `unverified`. Record whose `spec_sha256`
  differs from the file: warning `verification stale`. Record whose `summary.fail` is not zero:
  error, whether or not the record is also stale. A record with a malformed frontmatter: error.
  `--require-verified` turns the two warnings into errors, for a root whose policy is that nothing
  unverified lands. CI keeps the default so a new spec can merge before its first verification. A
  record reporting failures therefore never merges; a stale one merges with a warning unless the
  root runs the checker with `--require-verified`.

## Tools

`resources.tools` entries are declarative: what exists and which skill knows how to drive it. The
reader does not invent invocation syntax; it loads the `via:` skill and follows it. Kinds are
free-form; the shipped conventions are `bench` (a target on a lab rig: serial console, power, netboot,
screen), `mcp` (an MCP server or one of its tools), and `script` (a path in the tree). When the `via:`
skill is not loaded, the reader reports the tool as unavailable and continues.

## Rules for spec content

- Only facts tagged and cited as this format defines belong in a spec. `[press]` is allowed only with
  `TODO (verify on hardware)`; so is `[emulated]`, and only beside another class or as an
  `[inference]` premise, phrased as an observation from outside the model.
- **Device-tree content is hardware description.** Node names, labels, `compatible` strings,
  property names, and values (addresses, interrupt tuples, clock names, pin groups) are hardware
  facts, tagged `[DT]`.
- No source excerpts: a spec states facts and says where each comes from.
- An overlay in a vendor layer may cite NDA documents. Facts from it reach the report tagged with
  their layer, so a verifier can see that a citation is not publicly checkable. They are never
  copied into a public-layer spec.
- A public-layer root contains no `access: internal` entry, no `via:` naming a private skill, and no
  private hostname. The public-skills repository's privacy rules apply to every public root.

## What the checker enforces

`board-expert/scripts/spec_check.py <root>... [--stubs-from <skills dir>] [--stub SKILL.md]
[--public-skill NAME] [--require-verified] [--require-license]` fails on:

- frontmatter missing a key its kind requires, an unknown `kind` or `layer`, or a duplicate `id`;
  an `id`, alias, part, `variant_of`, or `overlays` value that is not a normalized id; a `triggers`
  or `not_triggers` that is not a list of strings;
- a `parts`, `overlays`, `variant_of`, or `instances[].ip` reference that resolves to nothing
  across the given roots, or an `ip` spec with no `docs` entry marked `cite: true`;
- an `instances:` row whose `reg` is not an integer or null, or whose `irq` is not null or a
  mapping with `kind` (SPI | PPI | extended) and an integer `number`; an `extended` irq without
  `parent`, or a SPI/PPI irq with one; a `variants:` entry without a `name`, or with a `tag` that
  is not a provenance class;
- a `series` entry with `cite: true`; a `fetch` value other than ok | blocked | truncated | partial,
  or a `fetch_via` that is not a string; a `status` other than unmerged | merged | superseded, on an
  entry or on one of its `files`;
- `access: internal`, or a `via:` naming a skill outside the public set, under a `public` root;
- a marker `license:` that is not an SPDX expression or an `accepts:` that is not a list of single
  SPDX identifiers (with `--require-license`, a marker missing either); a `resources.repos` entry
  whose `license:` is not an SPDX expression, or that has none in a root that declares `accepts:`,
  or (with `--require-license`) whose license the root's `accepts:` does not accept;
- a fact bullet that does not end with its tag clause; in the tail clause, a `[source-observed]`,
  `[press]`, `[inference]` or `[emulated]` without `TODO (verify on hardware)`; a `[doc]`, `[DT]`,
  `[rtl]`, `[inference]`, `[emulated]` or `[src]` without a following parenthetical (the format
  requires that it name the source; the checker tests only that it is there, and for `[src]` that
  it holds a `[src:]` anchor); or a tail clause whose only tag is `[emulated]` (tag names in the
  prose are ignored);
- anywhere in a spec's body, a `[src:]` anchor that is malformed, names no repo, names one the
  spec's `resources.repos` does not list, names one whose `ref` is not a full commit id or that
  has no `license:`, or whose license the root's `accepts:` does not accept (always; a root
  without `accepts:` or with `accepts: []` accepts none); or one broken across lines. The
  anchors are parsed by `peripheral-spec`'s `anchor_check.py`, so that skill must be installed
  beside this one when a spec uses them;
- an unsubstituted template placeholder, `<...>` starting with a letter outside backtick code spans
  (autolinks and message ids excepted), in a spec's frontmatter or body or in a stub;
- a stub whose `spec: <id>` does not resolve. `--stubs-from` finds every `*/SKILL.md` under a
  skills directory whose frontmatter says "stub over", so CI cannot forget one;
- a verification record (`<root>/resources/<id>.verify.md`, an overlay's included) whose
  frontmatter is malformed or whose `summary.fail` is not zero; with `--require-verified`, also a
  spec or overlay with no record or with a stale one.

It warns, without failing, on a root marker without `license:` or `accepts:`, on two overlays for one id in one layer, on a part whose `cache`
differs from its board's, on a spec or overlay with no verification record (`unverified`), and on a record
whose `spec_sha256` no longer matches the spec (`verification stale`). It is stdlib-only: PyYAML when available, otherwise its own parser for the
format's YAML subset, and its last line says which one ran (`parser: pyyaml` or `parser: subset`).
The two agree on the quoting traps above by construction. It does not check URL reachability. CI has
no PyYAML, so it runs the subset parser; run the checker once under a Python that has PyYAML (for
example `uv run --with pyyaml python ...`) to exercise the other path.

## Related documents

- `QUESTIONS.md` — the question catalog and the `Needs decision` protocol shared by every skill
  that produces or consumes specs.
- `VENDOR-GUIDE.md` — how a vendor sets up overlay roots, wraps internal tools as skills, and keeps
  internal material out of public roots.
- `../spec-verifier/SKILL.md` — the verification procedure for every spec kind, with the board-spec
  section this format's *Verification* section points at.
