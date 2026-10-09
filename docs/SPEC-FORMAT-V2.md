<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Spec format 2: facts as YAML records, validated by a JSON Schema (design)

Status: **approved by the user on 2026-10-08 (decisions D1–D22 below).** Nothing here is built yet. The
direction (one YAML format for every spec, validated by a JSON Schema, with Markdown as a rendered
view) was approved by the user on 2026-10-08 ([RG-regen](../notebook/RG-regen.md), "RG-T1 rounds
6–8, merge, and the format decision"). The user settled the design's open choices the same day;
they are recorded under [Decisions (2026-10-08)](#decisions-2026-10-08), and the body below
follows them. Where the body depends on one, it names it (D1–D22).

## Terms

- **Spec** — a hardware description an agent reads instead of the original sources: a board, an
  SoC, a companion chip, an IP block (the *board-spec* kinds), one peripheral's programming model
  (a *peripheral spec*), or a driver compared against a reference driver (a *review*).
- **YAML** — a text format for structured data (mappings, lists, strings, numbers). **JSON
  Schema** — a standard language for stating what shape a JSON-like document must have (which
  keys, which types, which values); a **validator** is the library that checks a document against
  a schema. **Draft 2020-12** is the current published version of that language.
- **Fact record** — one claim in a spec, stored as a YAML mapping with a stable **fact id**, the
  claim text, and structured **support entries**. A **support entry** is one piece of evidence:
  its **provenance class** (`databook`, `src`, `inference`, …) and the fields that class requires.
- **Fact reference** — how a premise or a relation names a fact: `#<fact id>` in the same file,
  `<spec id>#<fact id>` in the same root, and `<spec id>@<root name>#<fact id>` (a
  **root-qualified reference**) in another root (D1).
- **Root / root marker / layer / overlay / accepts list / license gate** — as today
  ([`SPEC-FORMAT.md`](../skills/board-expert/SPEC-FORMAT.md), [license split](LICENSE-SPLIT.md)):
  a directory of specs with a `board-specs.yaml` marker; the marker's position in the merge
  order; a spec in one root that adds to a spec of the same id; the SPDX licenses the root's
  cited sources may carry; the check that fails a citation of a source the list does not
  include.
- **Pin** — a `resources.repos` entry carrying a full commit and an SPDX license; every citation
  into source code names one.
- **Verification record** — the file, outside the spec, holding one verdict per fact. A
  **basis hash** is a fingerprint of everything one verdict depends on (the fact record, the
  resource entries it cites, and the basis hashes of the facts it references); when it changes,
  that verdict is stale.
- **Rendered view** — the Markdown generated from the YAML for people to read, built and
  published by CI, never committed, never edited and never parsed for meaning.
- **Viewer** — the published HTML view CI builds from the same YAML. It shows each fact's
  provenance as **badges**: labels drawn from the structured fields (class, verdict, TODO,
  origin), placed outside the author's text, which author text cannot produce. The viewer, not the
  Markdown view, is where a cited fact is guaranteed to look different from prose.
- **Canonical form** — one fixed serialization of parsed YAML data (sorted keys, no whitespace),
  so that two files holding the same data hash the same whatever their layout.

New terms are in the [glossary](../GLOSSARY.md).

## Why

The Markdown spec format stores facts as prose bullets and provenance as text patterns at the end
of each bullet (`[databook]` (…), `[src:<repo>: path:L]`). Every check has to parse that text
back into structure, and every disagreement between what a reader sees and what the parser
extracts is a way to ship a fact with wrong or missing provenance.

RG-T1 measured this. Eight review rounds of the `[src]` checker found, in turn: an empty anchor
that passed both checkers; an alias tag that evaded every rule; a regex claim scanner that lost
wrapped bullets; two fence scanners that disagreed and blanked a fact between code blocks; and,
after the rewrite onto one CommonMark parser, text that renders as provenance while the checker
reads it otherwise (quoted headings, comments closed early, entities, emphasis inside an anchor,
invisible characters). The three gaps still open at merge go away only by changing the format
([RG1 evidence](../evidence/RG1.md), "Known gaps at merge"). A proposed "plain-ASCII tail" rule
would have failed 94 already verified bullets. The lesson recorded in the notebook: *a schema
imposed on a format designed for many equivalent spellings will keep leaking; when the data is
structured, store it structured.*

RG1's verification history adds three costs a structured format removes:

- **Whole-file staleness.** Any edit stales the whole record. RG1 wrote three "delta"
  records by hand, each carrying unchanged lines from the previous record, and one record whose
  `spec_sha256` the orchestrator updated by hand after a format-only change. Per-fact basis hashes
  make both mechanical ([Verification records](#verification-records)).
- **Prose premises.** A GPL inference cited a docs fact as "as the `bcm2711` spec in
  hardware-specs-docs states, Addressing model", and its record pinned the docs spec by commit to
  make that checkable. A fact reference (`bcm2711@hardware-specs-docs#addressing-model`) does it
  directly.
- **Unchecked parentheticals.** `[DT]` parentheticals such as "(bcm2711.dtsi lines 10-11,
  linux)" were never resolved against the pinned tree, and `[doc]` locators were never checked
  against the document's page count. Structured citations make both mechanical.

## Requirements

User decisions of 2026-10-08:

- **R1 One format for every spec**: board, SoC, chip, IP block, peripheral spec, review, and the
  facts file `hardware-investigator` returns. YAML, validated by a JSON Schema (draft 2020-12).
- **R2 Markdown is a rendered view** (with an HTML viewer, later also search). It is generated,
  never edited, and never parsed for meaning.
- **R3 Facts are records with stable ids; citations are structured fields**, never prose
  patterns.

Carried over unchanged from the license split ([LICENSE-SPLIT.md](LICENSE-SPLIT.md)): three
spec repositories (`hardware-specs-docs`, `hardware-specs-permissive`, `hardware-specs-gpl`), the
placement rule, root markers with `license:` and `accepts:`, overlays across repositories, the
license gate, and per-file verification records.

Non-goals: changing what the evidence classes mean ([DESIGN.md](../DESIGN.md), "Evidence
model"); new specs; the viewer's search and navigation beyond the first static version
([Rendering](#rendering-and-the-viewer)); the frozen archive (it stays as it is, see
[Migration](#migration)).

## Overview

| File | Today | Format 2 |
| --- | --- | --- |
| Board, SoC, chip, IP spec | `<id>.spec.md` (YAML front matter, Markdown body) | `<name>.spec.yaml` |
| Overlay | `<id>.spec.md` with `overlays:` | `<name>.spec.yaml` with `kind: overlay` |
| Peripheral spec | `<device>-spec.md` (`Source pin:` lines, anchors in prose) | `<name>.spec.yaml`, `kind: peripheral` |
| Review | `<driver>-review.md` (`Impl pin:`/`Ref pin:`) | `<name>.spec.yaml`, `kind: review` |
| Investigator facts file | Markdown with `Source pin:` | `<name>.facts.yaml`, `kind: facts` |
| Root marker | `board-specs.yaml` | `board-specs.yaml`, plus `format: 2`; `name` becomes required |
| Verification record | `<root>/resources/<name>.verify.md` | `<root>/resources/<name>.verify.yaml` |
| Rendered view and viewer | none (the spec is the view) | Markdown and HTML built by CI and published (Pages, and an artifact on pull requests); not committed (D5) |
| Schema | none | `spec.schema.json`, `verify.schema.json`, `root.schema.json` (D7) |

One loader reads every file (the [YAML loader](#the-yaml-loader)); the validator checks it
against the schema; a small checker does what a schema cannot
([Validation](#validation-schema-and-checker)). One command-line tool, `spec.py`, has the
subcommands `check`, `resolve`, `render` (Markdown and the HTML viewer), `show`, `status`,
`drift`, `inventory` and `migrate`,
following the house exit-code contract (0 passed, 1 a check failed, 2 usage, 3 missing
precondition) and `--json`.

## The spec file

### Top level

```yaml
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: CC-BY-4.0
format: 2                 # the schema version this file is written against
kind: soc                 # board | soc | chip | ip | overlay | peripheral | review | facts
id: bcm2711               # normalized: [a-z0-9-], unique across every root read together
name: Broadcom BCM2711 (Raspberry Pi 4, Raspberry Pi 400, Compute Module 4 and 4S)
triggers: [bcm2711, raspberry pi 4 soc, pi 4 soc, pi 400 soc, cm4 soc]
not_triggers: [bcm2712]
aliases: [...]            # optional lists: absent or non-empty, never []
cache: rpi4-resources
instances: []             # soc and chip only, required for soc (may be empty); see Instances
resources: {...}          # documents, repos, series, tools; absent or non-empty; see Resources
assumptions: [...]        # named assumptions facts rest on; see Assumptions
orientation: >-           # prose, not facts; see Prose that is not a fact
  The BCM2711 is the SoC of ...
facts: []                 # the fact records, in reading order
notices: [...]            # source notices a license asks the spec to carry
```

The SPDX header stays as YAML comment lines at the top of the file, where REUSE tooling reads
them. Comments carry no meaning anywhere else and do not appear in the rendered view.

Keys by kind (closed: any key not listed for the kind is a schema error):

| Key | board | soc | chip | ip | overlay | peripheral | review | facts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `format`, `kind`, `facts` | required | required | required | required | required | required | required | required |
| `id`, `name` | required | required | required | required | no | required | required | optional |
| `triggers`, `not_triggers`, `aliases` | required / opt. / opt. | same | same | same | no | optional | no | no |
| `overlays` (the target id) | no | no | no | no | required | no | no | no |
| `parts` | required | no | optional | no | no | no | no | no |
| `instances` | no | required (may be empty) | recommended | no | optional | no | no | no |
| `variants`, `variant_of` | optional | no | no | no | no | no | no | no |
| `cache` | required | recommended | optional | recommended | no | optional | optional | no |
| `resources` | optional | optional | optional | required | optional | required | required | required |
| `assumptions`, `orientation`, `notices` | optional | optional | optional | optional | optional | optional | optional | optional |
| `areas` (per-area confidence) | no | no | no | no | no | optional | optional | no |

Ids normalize as today (lowercase, `[a-z0-9-]`, "Tensor G5" is `tensor-g5`). The file name is a
convention; `id` (or `overlays`) resolves. Every `*.spec.yaml` below a root is a spec, whatever its
kind, so the naming split between `*.spec.md` and `*-spec.md` disappears (D17).

### Sections

Every fact names its section. Sections are a closed list per kind, and the renderer prints them
in this order:

| Kind | Sections |
| --- | --- |
| board, soc, chip | `quick-facts`, `gotchas` |
| ip | `standards`, `programming-model`, `variants-quirks`, `gotchas` |
| overlay | the sections of the kind it overlays |
| peripheral | `identity`, `registers`, `sequences`, `data-formats`, `interrupts`, `dma`, `sub-protocols`, `target`, `gotchas`, `open-questions` |
| review | `identity`, `correspondence`, `coverage`, `findings`, `agreements`, `open-questions` |
| facts | `facts` |

The peripheral spec's provenance notice, canonical-references table and verify-on-hardware list,
and the review's notice and reference-provenance section, are no longer written by hand: the
renderer generates them from `resources` and from the facts' `todo` and `requirement` fields, so
they cannot disagree with the data.

### The fact record

```yaml
- id: gic-arm-local-not-legacy        # [a-z0-9][a-z0-9-]*; unique among this spec's files in this root
  section: gotchas
  title: The GIC and ARM_LOCAL bases are not legacy addresses.
  claim: >-
    Every other peripheral address in the datasheet is a legacy master address to translate;
    these two are Arm-only and translate differently (`0x4_C004_0000` or `0xFF84_0000` for the GIC).
  support:                            # absent: a gap fact (todo required)
    - class: databook
      doc: bcm2711-peripherals
      at: [{section: "6.5.1 and 6.5.2", page: "92"}]
  # optional fields:
  todo: {check: hardware, text: "..."}        # required for press, inference, emulated
  assumes: [stub-build-identity]              # named assumptions (spec-level registry)
  scope: {boards: [...], revisions: [...], modes: [...], builds: [...]}
  critical: true                              # bring-up-critical: two verifiers required
  requirement: as-implemented                 # peripheral and review facts; see below
  relates: [{fact: "#addressing-model", relation: qualifies}]   # fact references: see References
  conflicts: [...]                            # see Conflict entries
  data: {...}                                 # typed payload: register, sequence, finding, ...
  note: "..."                                 # uninterpreted remark for readers
```

| Field | Rule |
| --- | --- |
| `id` | Stable for the life of the fact: editing the claim, moving the section or reordering never changes it. Unique among the files of one spec id in one root; facts in different roots may share an id, because a reference into another root names the root (D1). A deleted fact's id is not reused. |
| `title` | The bold lead-in today; plain text, escaped when rendered. Required for board-spec kinds (every bcm2711 bullet has one); optional elsewhere. |
| `claim` | CommonMark (lists, emphasis, links, tables, code), with no raw HTML (D4). No tool parses it for meaning. Never contains a citation: provenance lives only in `support`, and only the viewer's badges, drawn from `support`, show it. One claim per fact: a sentence concluded rather than read is its own `inference` fact (D3). |
| `support` | One or more support entries ([Provenance classes](#provenance-classes)). Entries of read classes support the claim jointly, as a v1 tag clause does. An `inference` entry stands alone. `emulated` never stands alone. |
| `todo` | `check`: `hardware`, `document` or `source` (what kind of check would settle it); `text`: what to check and how; optional `method` when the method is worth stating apart, so the verifier can judge whether it can observe the thing (RG1 C4). Required for `press`, `inference`, `emulated` and extension classes; allowed on any fact. |
| `assumes` | Ids from the spec's `assumptions` registry. A fact resting on an unstated assumption was a recurring verifier finding (RG1 A4); here the assumption is named once and every fact that rests on it lists it. |
| `scope` | Lists of strings naming where the claim holds: `boards`, `revisions`, `modes`, `builds`, `configurations`. Rendered beside the claim. A claim true of one tree and written as true of both was a recurring `FAIL` on definiteness; `scope` gives it a place. |
| `critical` | Marks a bring-up-critical fact (addressing model, entry state, debug UART, debug console). The checker requires two readers in the record for it (D14). |
| `requirement` | Peripheral specs and reviews: `hw-required` (must have a document-class support entry), `comment-explained` (must cite a code comment), `driver-choice`, `as-implemented` (goes on the generated verify-on-hardware list). |
| `relates` | Typed links to other facts: `qualifies`, `contradicts`, `refines`, `same-as`. Used by the renderer, by staleness ([Verification records](#verification-records)) and later by the viewer. |
| `data` | A typed payload for structured facts (instances, registers, sequences, findings); see [Peripheral specs and reviews](#peripheral-specs-and-reviews). |
| `note` | CommonMark with no raw HTML, like `claim`; rendered as a note; never evidence. |

A **gap fact** has no `support` and must carry a `todo`; it renders as "Gap" and gets the verdict
`GAP`. `open-questions` facts in peripheral specs and reviews are gap facts.

### Conflict entries

[DESIGN.md](../DESIGN.md) ("Conflicts are recorded, never overwritten") proposes a conflict entry
beside a claim when two classes disagree. Format 2 gives it a field (D18):

```yaml
conflicts:
  - reading: "the documentation says Arm stub support for high peripheral mode is missing"
    support: [{class: doc, doc: rpi-docs-legacy-boot, at: [{heading: arm_peri_high}]}]
    resolution: "attributed to the documentation; hardware TODO added"
    assumption: "the vendor document can lag the source tree"   # the evidence-model row that decided it
    decided: {by: user, date: 2026-10-08}
```

An unresolved conflict (no `resolution`) makes the fact render as contested.

### Assumptions

```yaml
assumptions:
  - id: stub-build-identity
    text: >-
      The firmware's built-in 64-bit stubs are built from `armstubs/armstub8.S`, which no
      document states.
    todo: {check: hardware, text: "capture the stub image the firmware loads and compare it with this build"}
```

An assumption is not a fact and gets no verdict of its own. Each fact that `assumes` it is
verified on whether the fact follows given the assumption, and the record says the verdict is
conditional. Changing an assumption's text changes the basis hash of every fact that assumes it.

### Instances and variants

`instances:` rows keep their shape (name, `ip`, `reg`, `irq`, `clocks`, `role`, `note`) and gain
`id` and `support`, so each row is verified like any fact (today keyed `instances/<name>` with no
citation of its own). `reg` is a hex string (D6). `variants:` rows gain `id` and `support` in
place of today's `tag` and `source`, so a variant known only from press carries a `press` entry
and its TODO like any fact. A row is never a gap fact: a `GAP` verdict on an instance or variant
row is an error (settled in SF2-3; made explicit in review round 1, 2026-10-08).

### Prose that is not a fact

`orientation` (all kinds) and a few kind-specific prose fields (`milestones` for peripheral
specs, `notes` for reviews) hold text that no tool interprets. They may use CommonMark with no
raw HTML, like claims (D4). The renderer prints them under their headings, marked as uncited
context; the viewer gives them no badges. A fact never lives in prose: a statement a reader would
act on goes in `facts`. Prose can still be written to look like a cited fact in the Markdown view;
[Rendering and the viewer](#rendering-and-the-viewer) says why the viewer, not the text, is where
that distinction holds.

`notices` carries the source notices a license asks a spec to carry, each `{repo, path, text}`,
rendered as a fenced text block under "Source notices". Nothing in a notice is a citation.

## Provenance classes

`class` is a closed enum. Each class has its own required fields; the schema enforces them with
one `if`/`then` per class (an excerpt is in [Validation](#validation-schema-and-checker)).

| Class | Required fields | Optional | `todo` | Gated by `accepts` | Rules carried from v1 |
| --- | --- | --- | --- | --- | --- |
| `databook` | `doc` (a document of class `databook`), `at` (one or more locators) | `note` | no | no | the IP databook, TRM or datasheet |
| `standard` | `doc` (class `standard`), `at` | `note` | no | no | standards and architecture specifications; Linux's `booting.rst` |
| `doc` | `doc` (class `doc`), `at` | `note` | no | no | a vendor's or project's own documentation; the document entry names which page |
| `rtl` | `design`, `revision`, `module`, and `doc` or `anchors` | `note` | no | anchors only | strongest for digital register behavior on the revision named |
| `DT` | `anchors` (each: `repo`, `path`, and `lines` for a source `.dts`/`.dtsi`, or `node` for a decompiled blob) | `node`, `comment` per anchor | no | yes | a value read out of a device tree; a blob anchor names the repos entry it came from |
| `src` | `anchors` (each: `repo`, `path`, `lines`, `symbol`) | `comment`, `search` per anchor | no | yes | what the cited code defines or does; never a hardware requirement on its own |
| `hardware` | `board`, `method`, `date` | `revision`, `firmware`, `conditions`, `runs` | no | no | measured on a live board |
| `emulated` | `model`, `version`, and `runs` or `observation` (a fact id holding a numbered observation) | `note` | yes | no | never the only class of a fact; phrased as an observation from outside the model |
| `press` | `title`, `url` | `date`, `note` | yes | no | third-party reporting; a lead |
| `inference` | `premises`, `derivation` | `confidence` (`high`, `medium`, `low`) | yes | through its premises | concluded rather than read; stands alone in `support` |
| `source-observed` | defined by the extension that uses it; never the citation fields `repo`, `path`, `doc`, `anchors`, `lines`, `symbol`, `node`, `url`, at any depth (SF2-2 review: the gate reads citations only from core fields) | | yes | per the extension | kept as the one extension class in use (D15) |

### Locators (`at`)

A locator is a mapping with at least one of `section`, `page`, `pages`, `table`, `figure`,
`clause`, `heading`; all values are strings, so "92", "D24-9638" and "4-91" all fit. `pages` is a
two-item list. When the document entry gives `pages` (a count) and a locator's page is a plain
number, the checker requires it within the count; the entry's `page_numbering` says whether the
numbers are printed or PDF page numbers. A `databook` locator must carry `section`, `page`,
`pages`, `table`, `figure` or `clause`; so must a `standard` locator when its document entry gives
`pages` (a paged document; the checker enforces it), while an unpaged standard such as Linux's
`booting.rst` may be cited by `heading` (amended 2026-10-08 by the orchestrator's SF2-1 decision);
a `doc` locator may be a `heading` alone (most project documentation has no page numbers). This is the citation-precision rule RG1 asked for (V2)
in its mechanical part; whether a locator is the *right* one stays the verifier's.

### Anchors (`src`, `DT`, `rtl`)

```yaml
anchors:
  - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [53, 57], symbol: OSC_FREQ}
  - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [190, 192], symbol: spin_cpu3, comment: true}
  - {repo: rpi-tools, path: armstubs/, search: "no other AArch64 source in the directory"}
```

- `repo` names a `resources.repos` entry of the same file (an overlay's own entries: the gate is
  its root's). The entry must carry a full `commit` and a `license`.
- `lines` is `[first, last]`, 1-based and inclusive; a single line is `[n, n]`. `symbol` is
  required for `src` (line numbers drift; symbols survive) and optional for `DT`, which may give
  `node` instead. A symbol is written as the source spells it, C++ and assembler names included
  (`~Foo`, `operator<<`, `ns::Class::method`, `$label`, `struct gic_chip_data`): one line, no
  leading `-` (orchestrator decision, 2026-10-08).
- Symbols, nodes, refs and paths reach a command line (`spec.py resolve`, SF2-6) only as
  separate arguments after `--`, never through a shell, so the schema refuses option-like values
  and white space but not shell characters.
- `comment: true` says the cited lines are a comment and the claim attributes it ("the tree
  comments that…"), so a reader and the verifier can tell a comment's statement from the code's
  behavior (the learning behind GPL Quick-facts/6 and /7: comments attributed).
- `search` replaces `lines` for a negative or global claim ("only AArch64 source", "never
  written"): `path` is the file or directory searched, and the value says what the search
  established, so the verifier repeats the search. Today such premises sit in prose with no
  citation at all.
- `stale: {was: <commit>}` is added by `spec.py drift --rewrite` to an anchor whose lines changed
  at the new commit; it fails every check until a person re-verifies and removes it. It replaces
  the `[stale: was …]` text marker.

### Inference

```yaml
support:
  - class: inference
    premises:
      - fact: "bcm2711@hardware-specs-docs#addressing-model"   # a fact; its claim is the premise
        uses: "Low Peripheral mode places Main peripherals at 0x0_FC00_0000-0x0_FF7F_FFFF"
      - states: "the stub writes all-ones to eight group words"
        support:                                     # read classes only; never another inference
          - class: src
            anchors: [{repo: rpi-tools, path: armstubs/armstub8.S, lines: [228, 234], symbol: setup_gic}]
      - assumption: stub-build-identity               # a named assumption
    derivation: >-
      ITLinesNumber is 6, so 7 registers cover IDs 0–223; ...
```

A premise is exactly one of: a `fact` reference (with an optional `uses` saying which part of the
fact is used), a `states` text with its own `support`, or an `assumption` id. A premise's support
may not itself be an `inference`: a conclusion another fact needs is written as its own
inference fact and referenced by id. That is how a named inference is reused, the way the
permissive overlay's "build-identity step in the first bullet" is used by three later facts.

## References

Fact ids are unique per spec id per root, not globally (D1): the docs spec and a GPL overlay of
the same id may both hold a fact named `addressing-model`. A reference therefore says how far it
reaches:

| Form | Resolves to | Example |
| --- | --- | --- |
| `#<fact id>` | a fact in the same file | `#scr-el3-bits` |
| `<spec id>#<fact id>` | a fact in the files of spec `<spec id>` in the citing file's own root (a base spec, or overlays of that id there) | `bcm2711#which-build-ships` |
| `<spec id>@<root name>#<fact id>` | a fact in the files of spec `<spec id>` in the root whose marker `name` is `<root name>` | `bcm2711@hardware-specs-docs#addressing-model` |
| `<assumption id>` | an entry of the same file's `assumptions` (a separate namespace, never written with `#`) | `stub-build-identity` |

Precisely:

- The grammar is `^((<spec id>)(@<root name>)?)?#<fact id>$`, with `<spec id>` and `<fact id>`
  normalized ids (`[a-z0-9][a-z0-9-]*`) and `<root name>` matching `[a-z0-9][a-z0-9._-]*`.
- A reference into **another root must** name it. Naming the citing file's own root is allowed
  and means the same as the short form. The short forms never search other roots, so adding a fact
  in one repository can never change what a reference in another resolves to.
- Root `name` becomes required in a format 2 marker, and two roots read together with the same
  name are an error. Root names are therefore part of every cross-root reference: renaming a root
  is a breaking change, and the checker reports every reference it leaves dangling.
- A `#` starts a comment after a space in YAML, so a reference is always quoted:
  `fact: "#scr-el3-bits"`.
- A fact's **full reference**, `<spec id>@<root name>#<fact id>`, is what the merged view,
  the viewer and the basis hash use, so two facts with the same id in different roots never
  collide anywhere.
- Verification records are per file and are keyed by the bare fact id
  ([Verification records](#verification-records)).

The checker resolves every reference against the roots it was given, and rejects:

- a reference that resolves to nothing, or to a fact in a layer that merges *after* the citing
  file's (a public fact may not rest on a vendor or local overlay's fact);
- a cycle among inference premises (premises form a directed acyclic graph);
- a reference whose target, followed transitively through its own premises and citations,
  reaches a repos entry whose license the citing file's root does not accept (D13). Facts in the
  documents-only root cite no repository, so every root may reference them; a docs fact can never
  reference a GPL overlay's fact. This makes the placement rule hold through references, not only
  through direct citations.

A reference is not a copy: the citing fact's claim states what it concludes, and the rendered
view names the target by its fact reference.

## Resources

```yaml
resources:
  documents:
    - name: gic400-trm                      # the id citations use: [a-z0-9][a-z0-9._-]*
      class: databook                       # databook | standard | doc; citations must match
      title: "Arm CoreLink GIC-400 Generic Interrupt Controller TRM"
      revision: "r0p1, issue B (DDI 0471B), 2012-08-07"
      url: https://developer.arm.com/documentation/ddi0471/latest      # canonical citation form
      retrieval:                            # how a fetcher actually gets the bytes
        - url: https://documentation-service.arm.com/static/5e8f15e27100066a414f7424
          via: documentation-service
      sha256: 15463e9ac6c82114378b4dc7cee1fb4eaa545f4b5073af4bf8a57d22b9403c52
      pages: 59
      page_numbering: printed               # printed | pdf; offset when they differ
      access: public                        # public | internal
      verified: 2026-10-07
      fetch: ok                             # ok | blocked | truncated | partial
  repos:
    - name: rpi-tools
      url: https://github.com/raspberrypi/tools          # https only
      commit: 439b6198a9b340de5998dd14a26a0d9d38a6bcac   # full: 40 or 64 lowercase hex
      license: BSD-3-Clause                 # SPDX expression for every file cited through it
      role: source                          # source | target | impl | ref (peripheral, review)
      files:                                # closed list: a cited path must be listed (D12)
        - {path: armstubs/armstub8.S, license_from: notice}   # spdx-line | notice | license-file
      verified: 2026-10-07
      fetch: ok
      fetch_via: git
  series: [...]                             # unchanged; never cited
  tools: [...]                              # unchanged; declarative, `via:` a skill
```

What changes from today:

- **One document list for every kind.** Board specs' `resources.docs` (title, URL, `cite`) and
  peripheral specs' `docs:` registry (name, URL, `sha256`, `pages`) merge into
  `resources.documents`. Every document has a `name`, a `class`, and, when the file is
  obtainable, a `sha256`; today the bcm2711 hashes sit in free-text `note` and `fetch_via`
  fields. `cite: false` (a document that is a map only) stays; citing such a document is an error.
- **Canonical and retrieval URLs are separate fields** (RG1 C6, C17, C19): `url` is the citation
  form (`developer.arm.com/documentation/<id>/latest` for Arm), `retrieval` lists the URLs that
  work for a fetcher. Documentation kept in git (the Raspberry Pi documentation, wikis) records
  its `commit`. A retrieval entry's `via` and a repos entry's `fetch_via` are prose for a reader,
  never executed by any tool (orchestrator decision, 2026-10-08).
- **Repos carry `commit`, not `ref`, when cited.** A repos entry that any anchor names must carry
  a full commit. A map-only entry may keep a branch in `ref`. `url` must be `https://`: the
  schema rejects anything else before any tool runs (RG-T1 R1, where a URL reached `git fetch` as
  an option).
- **Per-file licenses** (RG1 V3): an entry's `files` is the closed list of paths cited through
  it, each saying how its license was confirmed (`spdx-line`, `notice`, `license-file`). With a
  checkout, `spec.py resolve` reads each cited file's `SPDX-License-Identifier:` line where there
  is one and fails when it does not fit the entry's `license`. A file under another license needs
  its own entry, as the GPL overlay already does with `linux` and `linux-pcie`.
- **Roles replace pin kinds.** `Source pin:`/`Target pin:`/`Impl pin:`/`Ref pin:` lines become
  repos entries with `role`. The license gate reads every entry the same way.

## Roots, layers, overlays and the license gate

The rules of [SPEC-FORMAT.md](../skills/board-expert/SPEC-FORMAT.md) ("Roots and layers") and
the license split carry over. Restated for format 2:

- **Root marker.** `board-specs.yaml` keeps its name and fields (`layer`, `name`, `roots`,
  `license`, `accepts`) and gains `format: 2`. `license` and `accepts` become required (`license`:
  orchestrator decision during SF2-2's review, 2026-10-08), and `accepts: []`
  means documents only (orchestrator decision, 2026-10-08; format 1 read an absent `accepts` as
  undeclared, with a warning). `name` becomes required, because root-qualified
  references name it (D1): the three repositories' markers already declare
  `hardware-specs-docs`, `hardware-specs-permissive` and `hardware-specs-gpl`. Two roots read
  together with the same name are an error.
- **Discovery.** The same four pointer sources; never a tree walk. Every `*.spec.yaml` below a
  root is a spec. No symbolic links inside a root.
- **Merge order.** By layer (`public` < `ip-vendor` < `soc-vendor` < `product` < `local`), then
  pointer order; the spec repositories in the order docs, permissive, gpl. Composition first
  (`parts`, then `instances[].ip`), then overlays.
- **Merging.** An overlay's `facts` are appended to the target's facts, each keeping its
  `origin` (root name and layer) and its full reference in the merged view; the renderer groups them under the target's
  sections with an "Overlay: <layer> (<root>)" sub-heading, as today. `resources` lists
  concatenate (a later entry with the same `name` replaces the earlier one); scalars: later wins;
  `id`, `kind` and `parts` cannot be overridden. An overlay never edits a base fact: it adds a
  fact that `relates` to it (`qualifies`, `contradicts`) or a conflict entry.
- **Placement rule.** A spec lives in the most restrictive repository among the sources it cites,
  directly or through references (D13).
- **License gate.** Every anchor of every `src`, `DT` and `rtl` support entry, in facts,
  premises, instances and variants, names a repos entry whose `license` the file's root accepts
  (`A OR B` passes when either side is accepted, `A AND B` only when both are; `GPL-2.0` is read as
  `GPL-2.0-only`). A root with `accepts: []` accepts no anchor. A repos entry no anchor cites is
  still gated under `--require-license`, as today. The gate is one function applied to one data
  structure: there is no second scanner, so there is no second reading to disagree with the
  first. What v1 gated only for `[src:]` anchors now covers `DT` too, which is what kept every
  BCM2711 device-tree fact out of the docs and permissive roots by hand during RG1.
- **A reference may only rest on a root that checks clean** (user decision, 2026-10-08, during
  SF2-2's review). The gate fails closed: what it cannot establish is an error on the checked
  citing file. A root whose own check produced any error is *untrusted*, counting errors from
  before a context root's findings are reported as warnings: a file that fails to load or
  validate, a file named like a spec that discovery passes over (`.spec.yml`, a case variant,
  a backup such as `.bak` or `~`, a format 1 `.spec.md`), a nested marker, a duplicate name, an
  unlistable directory, a failing reference. Every reference into an untrusted root, direct or
  reached through other facts, is an error, and that error makes the citing root untrusted in
  turn. A reference that resolves to nothing, or to more than one fact, is an error too. A
  marker that cannot be read leaves its root's name unknown, so while any given marker is
  unreadable, every root-qualified reference fails. `parts` and `instances[].ip` into another
  root are composition, not a fact resting on a source, and are not gated.

## Verification records

### File and naming

`<root>/resources/<name>.verify.yaml`, where `<name>` is the spec file's name without
`.spec.yaml`; one record per spec file, overlays included; two spec files whose records would
collide are an error, as today. Inside `resources/`, any other file whose name contains
`verify` (in any case: `w.verify`, `wverify.yaml`, `w.Verify.yaml`) is an error, and a record
anywhere but the root's own `resources/` (a nested `sub/resources/` included) is an error (review
round 1, 2026-10-08). The reader never loads a record body; `spec.py status` prints the
summary and freshness for each spec in a composition.

```yaml
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: GPL-2.0-only
format: 2
spec: bcm2711                       # the id (an overlay: the id it overlays)
spec_file: bcm2711.spec.yaml        # relative to the root; must be the file beside this record
spec_sha256: <64 hex>               # the file's hash when written; informational (D2)
canonical: fact-v1                  # the canonicalization the basis hashes use
sources:                            # everything consulted, with what identifies the bytes read
  - {name: linux, commit: 8d3ae59288f1e7d58d76558a6ee96d533bc5019f, fetch: ok}
  - {name: gic400-trm, url: "https://documentation-service.arm.com/static/5e8f15e27100066a414f7424",
     sha256: 15463e9ac6c82114378b4dc7cee1fb4eaa545f4b5073af4bf8a57d22b9403c52, fetch: ok}
summary: {pass: 2, fail: 0, unverifiable: 0, gap: 0, adjudicate: 0}
verdicts:
  gic-node:                         # the bare fact id: records are per file
    basis: <64 hex>                 # the fact's basis hash when this verdict was reached
    upstream: {...}                 # facts in other roots it rests on, with their bases (see Freshness)
    verdict: PASS                   # PASS | FAIL | UNVERIFIABLE | GAP | ADJUDICATE
    date: 2026-10-08
    verifier: "<agent, model, harness>"
    note: "what was compared against what"
    contrary_evidence: none-found   # none-found | found | not-checked
    citation_precision: exact       # exact | imprecise
    readers: [...]                  # a second reader's {verifier, verdict, note}; absent until one runs
    carried_from: {...}             # present when the verdict was carried forward, not re-read
```

Rules (all checked by `spec.py check`):

- **Keyed by fact id.** A record belongs to one spec file, so a verdict key is the bare fact id
  of a fact in that file (never a reference), or `<fact id>.<sub-id>` for a register field or
  sequence step that carries its own support (fact ids hold no `.`, so the separator is
  unambiguous). Keys survive every edit that keeps the id, and
  a mapping cannot hold a key twice (the loader rejects duplicates). A key that names no fact is
  an error.
- **`summary` has all five keys**, `adjudicate` included, and equals the counts of `verdict`
  values. It stays stored so a reader can be told the status without loading the body.
- **`FAIL`** carries `correction` (the proposed fix); **`ADJUDICATE`** carries `readings` (each
  reader's verdict and reasoning) and, once settled, `adjudication: {decision, by, date, rule}`,
  after which the verdict becomes `PASS` or `FAIL` and the history stays in `adjudication`.
- **Two readers.** A fact marked `critical` needs a second reader in `readers` with its own
  verdict (D14). A reader whose `verifier` is the verdict's own (compared after NFC, collapsing
  white space and folding case) is not a second reader (review round 1, 2026-10-08). This answers RG1's "add a record field showing whether the second verifier ran".
- **`carried_from`** names the earlier record (repository, commit, path), the key it had there and
  its format version. A carried verdict is a carry-forward, not a fresh reading, and the
  rendered status says so.
- **Documents in `sources` carry `sha256`** (RG1's re-verification reports: "`sources` has no
  place for a document hash").
- **`contrary_evidence` and `citation_precision`** are required on a verdict reached under
  format 2 and absent from a carried one whose earlier record did not state them.

### Freshness: per-fact basis hashes (D2)

Each verdict records the **basis hash** of its fact at the time of the verdict:

```
basis(fact) = sha256( "fact-v1\n"
                      + canonical(fact without `section`)
                      + "\n" + canonical(the resource entries the fact cites, all but bookkeeping)
                      + "\n" + canonical(the assumptions it names, all but bookkeeping)
                      + "\n" + sorted "<full reference> <basis(ref)>" lines for every fact it references )
```

- *Canonical* is JSON with sorted keys, no insignificant whitespace, UTF-8, strings in Unicode
  NFC. The data holds only strings, integers, booleans, null, lists and mappings (no floats), so
  this is deterministic without a canonicalization library.
- *All but bookkeeping*: a cited entry counts whole, except a short, closed list of
  **bookkeeping** fields per kind, which never stale a verdict:

  | Entry | Bookkeeping fields (everything else counts) |
  | --- | --- |
  | a document | `verified`, `fetch`, `note` |
  | a repos entry | `verified`, `fetch`, `fetch_via`, `note` |
  | a repos entry's `files` item | `note` |
  | an assumption | `todo` |

  A field not in the list, including one the schema gains later, counts by default. A repos
  entry's `files` contributes only the items of the paths the fact cites (each without its
  `note`), so listing another path stales nothing. A field joins the list only by a recorded
  decision that names it here. (User decision, 2026-10-08, review round 2: "hash all but
  bookkeeping". Rounds 1 and 2 each found a field missing from the earlier allow-list of
  *identity fields* — a document's `commit`, then a `files` item's `status` and a repos entry's
  `ref`, `status` and `role` — and each time an edit to that field left the verdict current.
  Inverting the list makes the mistake fail safe: forgetting a field now stales too much, never
  too little. `records.BOOKKEEPING` holds the list; the tests change every schema property of
  each kind and fail when the schema gains one the test does not list.)
- References recurse, so the hash is a Merkle hash over the fact's dependencies: editing the docs
  spec's `addressing-model` stales the GPL overlay's inference that rests on it, and nothing
  else.
- Layout does not count. Reflowing a folded block scalar, reordering keys, moving a fact to another
  section, or editing comments leaves every basis hash unchanged. The docs record's hand-updated
  `spec_sha256` after a format-only change (2026-10-08) would not have been needed.

A verdict is **current** when its `basis` equals the fact's basis now, **stale** otherwise; a
fact with no verdict is **unverified**. `spec.py status --stale` lists the stale and unverified
facts, which is exactly the delta a re-verification has to cover. RG1's stop rule ("re-verify
only the changed bullets") becomes mechanical.

Three points the formula leaves open, settled in SF2-3 (proposed by the implementer, accepted
by the orchestrator on 2026-10-08; `skills/spec-format/scripts/records.py` implements them):

- **Telling upstream-stale apart needs a second stored value.** One hash cannot say which of its
  inputs changed. A verdict therefore also records **`upstream`**: the facts in other roots its
  fact rests on, reached through references that stay in the fact's own root until they cross,
  each with its basis when the verdict was reached (absent when there are none). A stale verdict
  is upstream-stale when recomputing the basis with those recorded upstream bases gives back the
  verdict's `basis` (nothing in the fact's own root changed), the fact's whole dependency
  closure beyond those upstream facts stays outside its own root, and the status names the
  upstream facts whose basis moved. If anything an upstream fact rests on, directly or
  transitively, lies in the fact's own root (`A#a` rests on `B#b`, which rests on `A#c`), the
  verdict is stale: the recorded upstream bases would otherwise also freeze a fact of the own
  root and hide its edit (review round 1, 2026-10-08). A current verdict's `upstream` must match exactly, which the checker
  enforces; without it, an upstream change reads as plain stale, the stricter outcome.
  `spec.py status --json` prints each fact's basis and `upstream` map for the verifier to copy.
- **Reference cycles.** `relates` can form a cycle (`same-as` both ways); premises cannot. A
  cycle (a strongly connected set of facts) is hashed as one: its digest is
  `sha256("fact-v1-cycle\n" + sorted "<full reference> sha256(local part)" lines of its members +
  "\n" + sorted "<full reference> <basis>" lines of the facts outside it they reference)`, and a
  member's line for another member carries the digest in place of a basis. Outside cycles this
  is the formula above unchanged; on a cycle, any change to any member stales every member. (The
  *local part* is the formula's first three canonical terms.)
- **A basis that cannot be established is unknown, never current**: a reference the check
  rejected for any reason (it does not resolve, names the fact itself or a fact its list already
  names, merges in a later layer, fails the license gate or the trust rule, closes a premise
  cycle), a citation the check rejected for any reason (a `cite: false` document, a document of
  another class than the citation, a locator outside the document or written wrong, an anchor's
  backward lines, an anchor naming a repos entry the license gate refuses or one pinned by a
  ref), a cited `doc`, `repo` or assumption the file does not list or lists twice, a cited
  repos entry pinned by `ref` rather than `commit` (a ref names no fixed tree), a cited path not
  in the repos entry's `files` or listed there twice, or a fact resting on such a fact.
  (Rejections and names listed twice were added in review round 1, 2026-10-08; citation
  rejections and the ref pin in review round 2, the same day. Citation rejections are recorded
  by the same `Checker.reject` that records reference rejections.) Unknown is a
  warning, and an error under either `--require-verified` mode.

What the checker does: a current `FAIL` is an error. Stale and unverified facts are warnings, and
errors under `--require-verified`. A stale verdict caused only by a fact in another root
changing (through a root-qualified reference) is reported as **upstream-stale**, naming the
upstream fact. A record's own defects (a key naming no fact, a summary that does not match) and
a current `FAIL` make the root untrusted, like any error in its files; the freshness findings
(stale, unverified, a missing second reader) are a policy on the checked root, reported for
checked roots only, and do not (settled in SF2-3 with the points above).

How the spec repositories' CI uses this (D19):

- **On pull requests** to a repository, its CI runs `--require-verified`: every stale or
  unverified fact of that repository is an error, upstream-stale ones included. A pull request
  to the GPL repository cannot merge until the facts a docs edit staled there are re-verified.
- **On `main`** (pushes and the weekly scheduled run), the same CI reports upstream-stale facts
  as warnings and does not fail, so an edit merged in one repository never turns another
  repository's `main` red. Facts staled by the repository's own files cannot reach `main`
  without a pull request, which already required them verified.
- A pull request to the *upstream* repository is not blocked by the staleness it causes
  downstream: its CI does not read the downstream roots. The warning on the downstream `main`
  is the signal, and the next pull request there carries the re-verification.

Evaluation against the alternatives (the decision is D2):

| Option | Delta verification | Format-only edits | Cross-spec premises | Cost |
| --- | --- | --- | --- | --- |
| Per-fact basis hashes (chosen) | mechanical: the stale set is computed | no staleness | stale exactly when the premise fact changes | the canonicalization is a contract; changing it stales everything once |
| Whole-file `spec_sha256` (today) | by hand, as RG1 did three times | stale everything | not tracked (the record pins the other spec by commit in prose) | none new |
| Both, stale if either changes | none (the file hash dominates) | stale everything | tracked | most conservative; gives up the delta |

The per-fact hash does not see dependencies the fact does not declare: a verdict that silently
relied on a sibling fact or on the orientation text is not staled when they change. Coverage
("what the spec leaves out") was never a per-fact property; RG1 showed it is a separate review
(learning rollup, "a coverage review is a different job"), so the record keeps `spec_sha256` as
information for that review and for audits.

## Peripheral specs and reviews

The same fact record carries peripheral and review content; what was a table or a labeled bullet
becomes a typed `data` payload. The examples use the `widget` UART fixture
(`skills/hardware-investigator/examples/sources/widget-linux/drivers/tty/serial/widget.c`, a
synthetic GPL-2.0-only file) and the license-gate fixtures.

### Pins become repos entries

`Source pin: linux@REV GPL-2.0-only` in the investigator's expected answer, and the two pins of
`two-pins-spec.md` (`tools@439b619 BSD-3-Clause`, `linux@1111111 GPL-2.0-only`), become:

```yaml
resources:
  repos:
    - {name: tools, url: "https://github.com/raspberrypi/tools", commit: 439b6198a9b340de5998dd14a26a0d9d38a6bcac,
       license: BSD-3-Clause, role: source, files: [{path: armstubs/armstub8.S, license_from: notice}]}
    - {name: linux, url: "https://example.invalid/linux", commit: 1111111111111111111111111111111111111111,
       license: GPL-2.0-only, role: source, files: [{path: drivers/widget.c, license_from: spdx-line}]}
  documents:
    - {name: trm, class: databook, title: Widget TRM v1.0, url: "https://example.invalid/widget-trm.pdf",
       sha256: 1218036a6a0562504adedd37088e5136036a3099cf8581832e0c7353d7256cbd, pages: 120}
```

Named and unnamed pins, aliases (`impl`≡`src`) and free-text versus named `[doc:]` tags all
disappear: there is one citation form per class. The `docs-named-spec.md` shape (every document
named, hashed, and cited by name and page) is the only shape.

### Registers and bit fields

```yaml
- id: reg-ctrl
  section: registers
  title: CTRL
  data:
    register: {name: WIDGET_CTRL, offset: "0x00", width: 32, access: rw}
    fields:
      - id: en
        name: WIDGET_CTRL_EN
        bits: [0, 0]
        meaning: block enable
        support:
          - class: src
            anchors: [{repo: linux, path: drivers/tty/serial/widget.c, lines: [5, 5], symbol: WIDGET_CTRL_EN}]
  claim: CTRL is at offset 0x00, and bit 0 enables the block.
  support:
    - class: src
      anchors: [{repo: linux, path: drivers/tty/serial/widget.c, lines: [4, 4], symbol: WIDGET_CTRL}]
```

- The register map is the list of `registers` facts in the databook's order; the renderer builds
  the table (offset, name, width, access, reset, fields) from `data`, so the table and the facts
  cannot disagree. Today's block anchors (one tag line covering a table) go away: each row cites
  its own definition, which the tightness rule already asked for.
- `claim` is optional for a register fact: when absent, the renderer writes it from `data`. The
  basis hash covers `data`, so a changed offset stales the verdict.
- A field with its own `support` gets its own verdict key (`reg-ctrl.en`); otherwise the
  register's verdict covers its fields (D16).
- `inventory` (today's `inventory_check.py`) compares `data.register.name` and `offset`, and each
  field's `name` and `bits`, with the header at the pin. It no longer guesses names and hex values
  out of prose, so its value-mismatch report becomes exact.

### Sequences

```yaml
- id: seq-init
  section: sequences
  title: Initialization
  claim: The driver initializes the block by clearing CTRL, writing BAUD, writing LCR, then setting the enable bit.
  requirement: as-implemented
  data:
    sequence:
      steps:
        - {id: s1, action: "write 0 to CTRL", support: [{class: src, anchors: [{repo: linux, path: drivers/tty/serial/widget.c, lines: [12, 12], symbol: widget_uart_init}]}]}
        - {id: s2, action: "write the divisor to BAUD", support: [{class: src, anchors: [{repo: linux, path: drivers/tty/serial/widget.c, lines: [13, 13], symbol: widget_uart_init}]}]}
        - {id: s3, action: "write WIDGET_LCR_8N1 to LCR", support: [{class: src, anchors: [{repo: linux, path: drivers/tty/serial/widget.c, lines: [14, 14], symbol: widget_uart_init}]}]}
        - {id: s4, action: "set WIDGET_CTRL_EN in CTRL", support: [{class: src, anchors: [{repo: linux, path: drivers/tty/serial/widget.c, lines: [15, 15], symbol: widget_uart_init}]}]}
      order:
        - {before: s3, after: s2, requirement: comment-explained,
           support: [{class: src, anchors: [{repo: linux, path: drivers/tty/serial/widget.c, lines: [7, 7], symbol: WIDGET_LCR, comment: true}]}]}
  support:
    - class: src
      anchors: [{repo: linux, path: drivers/tty/serial/widget.c, lines: [12, 15], symbol: widget_uart_init}]
```

Each step and each ordering constraint carries its own `requirement` label where it differs from
the fact's, so "which orderings the datasheet requires, which the driver merely does" is data,
and the generated verify-on-hardware list collects every `as-implemented` step.

### Data formats, interrupts, DMA, target mapping

`data-formats` facts carry `data.layout` (`name`, `size`, and `fields` shaped like register
fields with byte offsets); `interrupts` and `dma` facts are ordinary claims with support; `target`
facts cite repos entries with `role: target`. Per-area confidence is the spec-level `areas` list
(`{area, level: document-and-code | code-only | inferred, note}`).

### Review findings

```yaml
- id: f-baud-latch
  section: findings
  title: BAUD written after LCR
  claim: >-
    The implementation writes LCR before BAUD; the reference writes BAUD first, and its comment
    says a write to LCR latches BAUD, so the implementation latches the old divisor.
  data:
    finding:
      category: differs              # differs | missing | extra
      assessment: bug                # bug | suspect | benign | ref-issue
      consequence: the first frames go out at the previous baud rate
      settled_by: [{class: databook, doc: trm, at: [{section: "4.2", page: "40"}]}]
      resolution: {status: open}     # open | fixed (with commit) | wontfix (with reason)
  support:
    - class: src
      anchors:
        - {repo: impl, path: drivers/widget/widget_uart.c, lines: [30, 31], symbol: widget_init}
        - {repo: ref, path: drivers/tty/serial/widget.c, lines: [13, 14], symbol: widget_uart_init}
        - {repo: ref, path: drivers/tty/serial/widget.c, lines: [7, 7], symbol: WIDGET_LCR, comment: true}
```

(The `impl` side here is illustrative; no fixture implementation exists.) The finding's own
judgment is named `assessment`, not `verdict`, so it cannot be confused with the verifier's
verdict on the finding. A `missing` finding's implementation side is a `search` anchor. `bug`
requires `settled_by` with a document class, or `self_evident: true` with the reason; `suspect`
lands on the generated verify-on-hardware list. `correspondence` facts carry
`data.pair: {impl: [anchors], ref: [anchors]}`; `coverage` facts carry
`data.coverage: {area, compared: true|false, read: "...", reason: "..."}`. A fix landing sets
`resolution: {status: fixed, commit: <full>}` and moves the `impl` pin through `spec.py drift`.

### The investigator's facts file

`hardware-investigator` returns `kind: facts`: `resources` (its pins and documents) and a
`facts` list in the `facts` section, no identity, no triggers. It goes through the same loader,
schema and license gate (`spec.py check <file> --root <target root>`), and `peripheral-spec`
copies its records into the spec unchanged, ids included.

## Validation: schema and checker

### What each layer checks

| Check | JSON Schema | `spec.py check` | `spec.py resolve` (needs checkouts) |
| --- | --- | --- | --- |
| Keys by kind, closed records, required fields | yes | | |
| Enums: `kind`, `class`, `section` by kind, `layer`, verdicts, `fetch`, `role` | yes | | |
| Per-class required fields; `todo` for press, inference, emulated | yes | | |
| `emulated` not alone; `inference` alone; gap facts have `todo` | yes | | |
| Patterns: fact ids, fact references, commits, sha256, `https://` URLs, hex values, dates | yes | | |
| Unique fact ids within a file | | yes (`uniqueItems` compares whole items, not a key) | |
| Fact ids unique per spec id per root; root names present and unique; references into another root qualified by root | | yes | |
| No raw HTML in claim, prose and note fields; each field self-contained: no heading, no unclosed fence (CommonMark parse, below; D20, D22) | | yes | |
| Every `repo`, `doc`, `assumption` name resolves in the file's `resources` | | yes | |
| Citation `class` matches the document's `class`; numeric pages within `pages` | | yes | |
| Fact references resolve; no cycles; layer order respected | | yes | |
| License gate (SPDX expression logic), direct and transitive | | yes | |
| `parts`, `overlays`, `variant_of`, `instances[].ip` resolve; stubs resolve | | yes | |
| Public-layer privacy (`access: internal`, `via:` to a private skill) | | yes | |
| Template placeholders left in: `<`, a letter, then letters, digits, spaces, `-` or `_`, then `>`, outside code (`<linux/of.h>`, `<a@b>` and URLs are not placeholders; SF2-2 review) | | yes | |
| Records: shape (schema), key per fact, summary counts, basis freshness, two readers for `critical` | shape | yes | |
| Markdown view and viewer build, every claim self-contained (publish step, D5) | | yes (`render`) | |
| Anchors resolve at the pin: path, line range, symbol near the range | | | yes |
| Cited files' SPDX lines fit the entry's license | | | yes |
| Document files hash to `sha256` (`--docs-dir`) | | | yes |
| Values in a claim appear in the cited lines (warning); `inventory` against headers | | | yes |

Everything in the schema column is declarative and can be read by people and other tools; the
checker column is a small amount of Python over already-parsed data. Neither ever reads prose
for meaning.

**One CommonMark parse, for safety and layout only** (D4, D20, D22). The checker parses every
claim, title, prose and `note` string with one pinned CommonMark library (markdown-it-py is the
candidate; [Dependencies](#dependencies)) and fails, naming the fact and field:

- **raw HTML**: any token CommonMark itself classifies as raw HTML, block or inline (a tag, a
  comment, a declaration, a processing instruction, CDATA). Text inside code spans and fenced or
  indented code is not HTML and passes, so `` `<linux/of.h>` `` is fine; values such as `<0 0 0>`
  and `<&gic>` are not HTML to CommonMark either. "No raw HTML" is a decision (D4), not a
  default a root can turn off;
- **autolinks** (`<https://example.com>`) are links, not HTML, and are **allowed**: the viewer
  applies the same link-scheme rule to them as to `[text](url)` links (D21), and the checker fails
  an autolink or link whose scheme that rule would drop, so the author learns at check time, not
  from a missing link in the viewer;
- **a heading** of any level (ATX or setext) inside the field, and **a code fence that never
  closes** (D22): either would split or swallow the blocks that follow in the Markdown view. The
  publish step repeats the check.

The parse never derives meaning. Its result is only "this field contains raw HTML, a disallowed
link scheme, a heading or an unclosed fence, at this line"; no provenance, class, citation, id
or value is ever read from it. Provenance comes only from the structured fields. This is
deliberately not the v1 arrangement, where the parse *was* the source of provenance and every
disagreement between it and the rendered text was a bypass: here a disagreement can at worst let
a piece of layout through to a view, never change what a fact cites. The viewer also renders with
HTML disabled, so the check is a guard, not the only defense. `notices` are exempt: they are
rendered only as fenced text. No claim in the three bcm2711 specs contains raw HTML or a heading
(checked 2026-10-08 for angle brackets; the parse itself is SF2-2's to run on the migrated files).

A warning (not an error) flags text in claims and prose that spells a v1 tag (`[databook]`,
`[src:`): harmless to tools, misleading in the Markdown view.

### Schema excerpt

The schema is one file with `$defs` per record. The support entry dispatches on `class`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/curtisgalloway/driver-lab/spec-format/2/spec.schema.json",
  "type": "object",
  "required": ["format", "kind", "facts"],
  "properties": {
    "format": {"const": 2},
    "kind": {"enum": ["board", "soc", "chip", "ip", "overlay", "peripheral", "review", "facts"]},
    "facts": {"type": "array", "items": {"$ref": "#/$defs/fact"}}
  },
  "allOf": [
    {"if": {"properties": {"kind": {"const": "overlay"}}},
     "then": {"required": ["overlays"], "not": {"required": ["id"]}}},
    {"if": {"properties": {"kind": {"enum": ["board", "soc", "chip", "ip"]}}},
     "then": {"required": ["id", "name", "triggers"]}}
  ],
  "unevaluatedProperties": false,
  "$defs": {
    "factId": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
    "factRef": {"type": "string",
                "pattern": "^([a-z0-9][a-z0-9-]*(@[a-z0-9][a-z0-9._-]*)?)?#[a-z0-9][a-z0-9-]*$"},
    "fact": {
      "type": "object",
      "required": ["id", "section"],
      "properties": {
        "id": {"$ref": "#/$defs/factId"},
        "claim": {"type": "string", "minLength": 1},
        "support": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/support"}},
        "todo": {"$ref": "#/$defs/todo"}
      },
      "anyOf": [{"required": ["support"]}, {"required": ["todo"]}],
      "allOf": [
        {"if": {"required": ["support"],
                "properties": {"support": {"contains": {"properties": {"class": {"enum": ["press", "inference", "emulated"]}}}}}},
         "then": {"required": ["todo"]}},
        {"if": {"required": ["support"],
                "properties": {"support": {"contains": {"properties": {"class": {"const": "inference"}}}}}},
         "then": {"properties": {"support": {"maxItems": 1}}}},
        {"if": {"required": ["support"],
                "properties": {"support": {"contains": {"properties": {"class": {"const": "emulated"}}}}}},
         "then": {"properties": {"support": {"contains": {"properties": {"class": {"not": {"const": "emulated"}}}}}}}}
      ],
      "unevaluatedProperties": false
    },
    "support": {
      "type": "object",
      "required": ["class"],
      "properties": {
        "class": {"enum": ["databook", "standard", "doc", "rtl", "DT", "src", "hardware",
                           "emulated", "press", "inference", "source-observed"]}
      },
      "allOf": [
        {"if": {"properties": {"class": {"const": "src"}}},
         "then": {"required": ["anchors"],
                  "properties": {"anchors": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/srcAnchor"}}}}},
        {"if": {"properties": {"class": {"enum": ["databook", "standard", "doc"]}}},
         "then": {"required": ["doc", "at"]}}
      ],
      "unevaluatedProperties": false
    },
    "srcAnchor": {
      "type": "object",
      "required": ["repo", "path"],
      "oneOf": [{"required": ["lines", "symbol"]}, {"required": ["search"]}],
      "properties": {
        "repo": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._-]*$"},
        "path": {"type": "string", "pattern": "^[^/\\s][^\\s]*$"},
        "lines": {"type": "array", "prefixItems": [{"type": "integer", "minimum": 1}, {"type": "integer", "minimum": 1}], "items": false, "minItems": 2},
        "symbol": {"type": "string", "minLength": 1},
        "comment": {"type": "boolean"},
        "search": {"type": "string", "minLength": 1}
      },
      "additionalProperties": false
    }
  }
}
```

(Excerpt: the real schema declares every property the `allOf` branches use, so
`unevaluatedProperties: false` closes each record; `todo`, locators, references and the other
classes follow the same pattern.)

### The YAML loader

YAML has many equivalent spellings too; the loader removes them before the schema sees the data.
One function, `load_strict(path)`, used by every tool:

| YAML pitfall | What goes wrong | What the loader does |
| --- | --- | --- |
| Implicit typing (YAML 1.1): `no`, `on`, `yes` become booleans; `012` octal; `1.10` a float; `2026-10-08` a date; `0x7E20_1000` an integer | a trigger `no` becomes `false`; a version loses its trailing zero; an address loses its spelling | resolves only `true`, `false`, `null` and decimal integers (`-?(0|[1-9][0-9]*)`); every other plain scalar is a string (D6) |
| Anchors and aliases (`&a`, `*a`), merge keys (`<<`) | one value silently shared by two facts; an alias expansion bomb | any anchor, alias or merge key is an error |
| Explicit tags (`!!python/object`, `!custom`) | object construction; type confusion | any explicit tag is an error |
| Several documents in one file (`---` … `---`) | a second document ignored by one tool and read by another | exactly one document, or error |
| Duplicate mapping keys | the later value wins silently | error (the `UniqueLoader` pattern already in `campaign-review/scripts/index_check.py`) |
| Non-string keys (`1: x`, `true: y`) | keys that compare unequal to their spelling | error |
| Invisible and control characters (U+200B, bidirectional controls, U+0000–U+001F except newline) | text that looks like one id and is another; RG-T1 round 8's hidden anchor | error in every string, with the line and column; strings must be NFC |
| Byte-order mark, non-UTF-8 bytes | | error |

PyYAML gives line and column marks for every node, so every loader, schema and checker error
names the file line, which keeps the format writable by agents and people alike.

### Dependencies

- **YAML**: PyYAML, already used in this repository (`campaign-review`, the frozen evaluations).
  `spec.py drift --rewrite` edits anchors in place by replacing the scalar spans PyYAML's node
  marks locate, so comments and layout survive without a round-trip library (D9).
- **JSON Schema validator** (D8), candidates: `jsonschema` (python-jsonschema; supports 2020-12;
  pulls in `attrs`, `referencing`, `jsonschema-specifications` and the compiled `rpds-py`);
  `jschon` (pure Python, supports 2020-12). `fastjsonschema` is excluded: it does not support
  draft 2020-12.
- **Step before pinning**: score the candidates with the `dep-quality` skill, as the house rule
  requires before any new dependency is pinned. Not run for this design.
- **CommonMark library, in the checker and the publish step** (D20, D22): the checker's
  raw-HTML, link-scheme and containment checks, the publish step's repeat of them, and the
  viewer's HTML all use one CommonMark implementation, with raw HTML disabled when rendering.
  markdown-it-py, already pinned here at 4.2.0, is the obvious candidate; it still goes through
  `dep-quality` in SF2-1, like the validator, before it is pinned for format 2. The consequence
  is stated plainly: **the checker imports a pinned CommonMark library**, used only to detect raw
  HTML, disallowed link schemes, headings and unclosed fences in claim and prose fields, never to
  derive meaning; provenance still comes only from structured fields.
- **Retired from the checking path**: `mdtokens.py` and its profile rules, and every Markdown
  parse of a spec body in `spec_check.py` and `anchor_check.py`, once v1 is gone (D11). The
  format 2 checker needs PyYAML, the validator and the CommonMark library, pinned in CI with
  hashes; without them it exits 3, never falling back to a second parser (the RG-T1 lesson: count
  the parsers). There is one Markdown parse, in one module, shared by the checker and the publish
  step.

## Rendering and the viewer

`spec.py render <root>... [--spec <id>] [--merged] [--with-status] --format md|html` builds two
views from the YAML and the records: the **Markdown view** and the **viewer** (static HTML). Both
are generated; neither is committed or edited (D5). Both carry the same content:

- a generated-file banner naming the YAML files, the commits they were built from, the
  canonical-form version and the `driver-lab` commit, and saying the view must not be edited;
- the identity block (kind, id, name, triggers) and the resources as tables (documents with
  class, revision and hash; repos with commit and license);
- `orientation` and other prose under "Context (not facts)";
- each section's facts in order, each with its generated provenance (support entries with their
  rendered citations, inference premises naming the facts they reference, derivation, TODO,
  scope) and its full fact reference, so a reader can cite it;
- in a merged view, overlay facts under "Overlay: <layer> (<root>)" sub-headings;
- with `--with-status`, each fact's verdict, date, freshness and whether it was carried forward;
- for peripheral specs and reviews, the generated provenance notice, canonical-references table,
  register tables, verify-on-hardware list and open-questions list.

### Publishing (D5)

- **Pull requests.** Each spec repository's CI builds both views and uploads them as a workflow
  artifact, so a reviewer can read the rendered result beside the YAML diff. A build failure (a
  claim that is not self-contained, below) fails the pull request.
- **Main.** On every merge, and in the weekly scheduled run, a publish workflow builds both views
  and deploys them to the repository's GitHub Pages site, following the house pattern of a docs
  workflow that assembles and deploys a site. The repository README links each spec's page.
- **Merged views.** Each repository publishes views of its own files, and the merged view of
  every spec it overlays, built with the other roots as context (the GPL repository publishes the
  docs, permissive and GPL `bcm2711` merged).
- Nothing generated is committed, so there is no freshness check: what is published is what the
  last build of `main` produced, and the banner says which commits it was built from.

### The Markdown view: how author Markdown is embedded

Claims, prose and notes are CommonMark without raw HTML (D4). The renderer keeps them apart from
everything it generates:

1. **Generated text is generated.** Titles, fact references, citations, scope, TODOs and status
   come only from structured fields and are escaped (backslash escapes for Markdown syntax
   characters; code spans with a backtick fence longer than their content), so a title or a
   citation is never interpreted as Markdown.
2. **One block per fact.** Each fact is a heading (`####` under its section, the escaped title),
   then the claim exactly as written, as its own blocks separated by blank lines, then a
   generated **provenance block**: a fixed label line followed by a list, one item per support
   entry (class, then the rendered citation), then premises and derivation for an inference, the
   TODO, the scope, and the fact's full reference as a code span.
   Author notes on support, nested premise citations and conflicts follow the complete
   generated list as top-level blocks, then the fact's own note. A blank line and a heading
   or a non-indented generated paragraph separate each author block from following content.
3. **Containment** (D22). A claim or prose field must stand alone: no heading and no unclosed
   code fence (either would split or swallow the blocks that follow), and no link reference
   definition (which could resolve a link in another field). Verification-record notes use
   the same checks and report their own file locations. The checker fails such a
   field ([Validation](#validation-schema-and-checker)), and the publish step checks again with
   the same parse before it renders, then checks the assembled view: no unplaced link, image,
   raw HTML or heading may appear. A failure emits diagnostics and no partial view.
   The parse checks layout only; it decides nothing about the fact.

What the Markdown view **cannot** do: an author can type anything the renderer emits. A claim or
an orientation paragraph can contain a bold "Provenance" line and a list that looks like a
citation, and in plain Markdown it will look like one. The Markdown view is a convenience for
reading on GitHub, in a terminal or in an agent's context; it does not guarantee that a cited
fact looks different from prose that imitates one. The viewer does.

### The viewer: badges prose cannot produce

The viewer renders each fact as an HTML element whose structure comes from the fields:

```html
<article class="fact" id="bcm2711@hardware-specs-gpl#gic-node">
  <header><h4>GIC node</h4></header>
  <div class="claim"><!-- the claim, rendered by CommonMark with raw HTML disabled --></div>
  <div class="provenance">
    <span class="badge class-dt">DT</span> <a href="...">linux@8d3ae59 bcm2711.dtsi 56–66</a>
    <span class="badge verdict-pass">PASS 2026-10-08 · carried</span>
    <span class="badge critical">bring-up critical · second reader missing</span>
    <span class="badge origin">public · hardware-specs-gpl</span>
  </div>
</article>
```

The guarantee rests on two facts: author Markdown is rendered with raw HTML disabled (and the
checker already rejects it), and a CommonMark renderer emits only its fixed set of elements,
with no `class` or `id` attributes. So no author text can produce an element carrying a badge
class, and nothing author-written can appear outside its `claim` container (each field is
rendered separately, so an unbalanced construct ends at the container's edge). Further rules:
images in author text render as links, not `<img>` elements; link URLs, autolinks included, are
limited to `https:`, `http:`, `mailto:` and in-page anchors (D21; the checker rejects any other
scheme); prose sections render in a container labeled "Context
(not facts)" that never carries badges.

Badges, all drawn from fields:

| Badge | From | Shows |
| --- | --- | --- |
| Class | each support entry's `class` | `databook`, `standard`, `doc`, `rtl`, `DT`, `src`, `hardware`, `emulated`, `press`, `inference`, or the extension class, each linked to its citation (the document and locator; the repository at its commit, path and lines) |
| Verdict | the record | `PASS`, `FAIL`, `UNVERIFIABLE`, `GAP`, `ADJUDICATE` with date; `stale`, `upstream-stale`, `unverified`; `carried` when carried forward |
| TODO | `todo.check` | what would settle the fact (`verify on hardware`, on a document, in source) |
| Critical | `critical` and the record's `readers` | bring-up critical; "second reader missing" until one is recorded |
| Origin | the file's root and layer | which repository and layer the fact comes from |
| Assumes | `assumes` | the named assumptions the fact rests on |
| Contested | `conflicts` without `resolution` | an open conflict entry |
| Requirement / assessment | `requirement`; a finding's `assessment` | `hw-required`, `as-implemented`, …; `bug`, `suspect`, … |
| Gap | no `support` | the fact records something unknown |

The viewer reads the YAML and the records, not the Markdown view. Search and navigation across
specs build on the same data later; this design covers the first static version only.

## Migration

### What converts

| Item | Count | How |
| --- | --- | --- |
| `hardware-specs-docs/specs/bcm2711.spec.md` | 34 facts | `spec.py migrate`, then a citation pass (below) |
| `hardware-specs-permissive/specs/bcm2711.spec.md` | 13 facts, 31 anchors, one source notice | same |
| `hardware-specs-gpl/specs/bcm2711.spec.md` | 18 facts | same; every `[DT]` parenthetical becomes `DT` anchors |
| Their three `resources/bcm2711.verify.md` | 65 verdicts | verdicts carried by id (below) |
| `skills/peripheral-spec/tests/fixtures/license-gate/` | 15 peripheral specs, 6 board specs, 3 root markers, `expected.json` | rewritten as `*.spec.yaml`; the expected matrix keeps its rows |
| `skills/board-expert/tests/fixtures/` | good, bad, vendor and verify roots, stubs | rewritten; each bad fixture keeps the one defect it tests, now as a data defect |
| `skills/hardware-investigator/examples/` | expected facts files | rewritten as `kind: facts` |
| `skills/board-spec-scaffold/templates/` | 6 spec templates and the root marker | rewritten as YAML templates |
| `skills/board-expert/specs/board-specs.yaml` | the shipped root (no specs) | `format: 2`; keeps its `name` |
| The three spec repositories' root markers | `layer`, `name`, `license`, `accepts` | `format: 2`; `name`, `license` and `accepts` (all already present) are now required; references use `name` |
| The three spec repositories' CI | `scripts/checks.sh`, one workflow | `checks.sh` on format 2, plus a publish workflow for the Pages site (D5); nothing generated is committed |

### Converting a spec

1. **Mechanical part** (`spec.py migrate <v1 file>`, using today's one Markdown parse for the
   last time): identity and resources; one fact per bullet, its `id` the slug of the bold
   lead-in (unique among the spec's files in its root; no prefix), its `section`, its `claim`
   (the bullet text before the tag clause, byte for byte), its `todo` text; every `[src:]` anchor
   into `anchors`; every `[DT]` parenthetical of the form "(<file> lines A-B, <repo>)" into `DT`
   anchors; hashes moved out of `note` into `sha256`; `fetch_via` URLs into `retrieval`.
2. **Citation part** (a fresh agent with the v1 and the draft v2 file, no sources): turn each
   free-text document parenthetical into a `doc` name and structured locators, and each inference
   parenthetical into `premises` and `derivation`, keeping the premise wording. A premise that
   names a fact of another bullet becomes a fact reference: `#<id>` in the same file, and the
   root-qualified form for a fact in another repository (the GPL overlay's prose "as the
   `bcm2711` spec in hardware-specs-docs states, Addressing model" becomes
   `bcm2711@hardware-specs-docs#addressing-model`).
3. **Split mixed bullets** (D3): a bullet whose tag clause mixes `[inference]` with read classes
   becomes a read fact and an inference fact that references it. In bcm2711: docs Quick-facts/2
   (two facts), permissive Gotchas/3 (three: the `src`+`databook` fact about the two builds' bases,
   the `doc` fact about the documentation, and the inference), GPL Quick-facts/1 (two). Three
   bullets become seven facts.
4. **Conversion-fidelity check** (D10): a fresh agent compares each v1 bullet with its v2 record
   and the Markdown view: claim text identical, every v1 citation present with the same target
   and locator, nothing added. It writes a fidelity report; it opens no source.

### Carrying verdicts

A v1 verdict carries to the v2 fact when the claim text is byte-identical and the fidelity check
passes the fact; it is written with `carried_from: {repo, commit, path, key: 'Quick-facts/2 "GIC
node"', format: 1}` and the fact's new basis hash. Everything else is unverified and goes to a
delta verification: the seven facts from split bullets, any fact the fidelity check flags, and any
fact whose citations gained structure the v1 text did not have (a premise that was prose with no
citation and now carries a `search` anchor, as in the permissive "Which build ships" inference).
Of the 65 v1 verdicts, the three split bullets cannot carry and neither can "Which build ships",
so at most 61 carry; the exact number is what the fidelity check passes.

`DT` anchors become resolvable at the pin for the first time. `spec.py resolve` runs on all 18
GPL facts during migration; a resolution failure there is a real finding about the v1 spec, not a
conversion error, and is recorded as one.

### What stays as it is

- **The frozen archive** (`evals/`, `evidence/`, `notebook/`, `history/` and the archive documents
  listed in `utilities/check-open-side.py`): unchanged, still checked by CI with its own tools. It
  describes format 1, and its references to `.spec.md` files and anchors stay as history.
- `evidence/RG1.md` and the notebook keep describing the v1 run; the migration gets its own
  evidence file.
- The `*.verify.md` records in the spec repositories' history: superseded by the YAML records,
  which point to them through `carried_from`.

### Transition (D11)

driver-lab ships format 2 alongside a read-only v1 checker; each spec repository migrates in one
pull request that bumps its driver-lab pin, converts the spec and the record, switches
`scripts/checks.sh` and adds the publish workflow; the three migrate in sequence docs,
permissive, gpl within one unit, so no mixed v1 and v2 composition has to be supported. When all
three are on format 2, driver-lab removes the v1 code and `mdtokens.py` in one change.
markdown-it-py is not removed: it stays, pinned, as the one CommonMark library the format 2
checker and the publish step share (D20, D22), subject to its `dep-quality` score in SF2-1.

## Effects on the skills and the spec repositories

| Component | Today | Format 2 |
| --- | --- | --- |
| `SPEC-FORMAT.md` | the contract, 780 lines, much of it the Markdown profile and tag-clause parsing rules | a shorter contract in the new `skills/spec-format/` reference skill (D7), pointing at the schema for shapes; classes, references, roots, records, rendering. The profile and tag-clause sections are deleted; `board-expert/SPEC-FORMAT.md` becomes a pointer |
| `board-expert` (reader) | reads `*.spec.md` and record front matter | reads `spec.py render --merged --with-status` output for the composition (smaller than raw YAML, and verdicts included), and the YAML when it needs a citation's exact fields; reports full fact references (`bcm2711@hardware-specs-docs#addressing-model`) in answers; "Suggested spec change" names the fact id or proposes a new record |
| `board-spec-scaffold` | Markdown templates, tag-clause rules | YAML templates per kind; the subagent that researches facts returns fact records directly; `spec.py check` instead of `spec_check.py`; RG1's checklist items (console routing, entry contract, memory reservations, interrupt table) stay prose guidance |
| `hardware-investigator` | Markdown facts file, `Source pin:` lines, `anchor_check.py --root` | `kind: facts` YAML; `license_gate.py` reads the same SPDX logic; per-file license confirmation is a field (`license_from`) checked by `resolve` |
| `peripheral-spec` | anchor grammar, pins, block anchors, labels in prose; `anchor_check.py`, `inventory_check.py` | the grammar section is replaced by the record types above; `requirement` field; `spec.py check/resolve/show/drift/inventory`; templates for the spec subagent and verifier rewritten around records |
| `reference-driver-review` | `[impl:]`/`[ref:]` aliases, Markdown findings | `role: impl`/`ref` repos, `findings` with `data.finding`, `assessment` in place of the finding verdict |
| `spec-verifier` | keys by section and ordinal or anchor text; whole-file hash; `summary` without `adjudicate` in board specs | keys by fact id; basis hashes; `readers`, `contrary_evidence`, `citation_precision`, `carried_from`; delta verification from `spec.py status --stale`; the verifier writes YAML and `spec.py check` validates it |
| `campaign-review` | `claims.yaml` `cites` spec section ids of the frozen e1000 spec | unchanged for the frozen campaign; a new campaign cites full fact references, and its sweep can use fact basis hashes as the basis identities of verdicts (DESIGN, continuous review C1 and C2) |
| Spec repository `scripts/checks.sh` | `specs` (spec_check), `anchors` (anchor_check, fetch, resolve), `self-test` | `check` (`spec.py check specs --context-root ... --require-license`, plus `--require-verified` on pull requests), `resolve` (fetch pins, resolve `src` and `DT` anchors, per-file licenses), `render` (builds the Markdown view and the viewer, uploads them as an artifact on pull requests), `self-test` (the v2 fixtures; same fit/misfit pairs). On `main`, upstream-stale facts warn (D19) |
| Spec repository publish workflow | none | builds both views on merges to `main` and weekly, deploys them to GitHub Pages (D5) |
| Spec repository CI dependencies | markdown-it-py 4.2.0 in a venv | PyYAML, the chosen validator and the CommonMark library (markdown-it-py, subject to `dep-quality`), pinned, for checks, render and publish alike |
| Spec repository `AGENTS.md`/README citation rules | describe peripheral `[doc:]` anchors and board tags | describe records; the README links each spec's page on the published site |
| driver-lab `AGENTS.md` check list and CI | `uv run --with markdown-it-py==4.2.0 ...` | `uv run --with pyyaml --with <validator> --with markdown-it-py==<pin> ...` |
| Consumers outside driver-lab | `bringup-kit` roots point at the docs and permissive repositories and read specs through `board-expert`; `fuchsia-skills` hands off by skill name | no skill is renamed; `board-expert` reads both formats only during the transition; bringup-kit test markers without `format:` are read as v1 until it migrates |

## Worked example

A slice of the bcm2711 specs as the migration would produce it, with every claim text copied
unchanged from the published files except where a split is noted. Facts and resources the slice
does not show (for example the permissive overlay's `patch-words`) are in the full migrated files. Hashes in the
record are shown as `<64 hex>`, since the canonical form is not built yet.

### `hardware-specs-docs/specs/bcm2711.spec.yaml` (slice)

```yaml
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: CC-BY-4.0
format: 2
kind: soc
id: bcm2711
name: Broadcom BCM2711 (Raspberry Pi 4, Raspberry Pi 400, Compute Module 4 and 4S)
triggers: [bcm2711, raspberry pi 4 soc, pi 4 soc, pi 400 soc, cm4 soc]
not_triggers: [bcm2712]
cache: rpi4-resources
instances: []
resources:
  documents:
    - name: bcm2711-peripherals
      class: databook
      title: BCM2711 ARM Peripherals
      revision: release 4 (2022-01-18), Raspberry Pi document RP-008248-DS
      url: https://datasheets.raspberrypi.com/bcm2711/bcm2711-peripherals.pdf
      retrieval:
        - url: https://pip.raspberrypi.com/documents/RP-008248-DS
      sha256: d6e16ea089a1716e80621f99a26e130a2379f0a81d945dc22e4f80dc49dcdc78
      pages: 166
      page_numbering: printed
      access: public
      verified: 2026-10-07
      fetch: ok
      note: "Page numbers in this spec are the printed page numbers (the PDF page is one higher)."
    - name: rpi-docs-legacy-boot
      class: doc
      title: Raspberry Pi documentation, legacy config.txt boot options (legacy_config_txt/boot.adoc)
      url: https://github.com/raspberrypi/documentation/blob/42deaefbc8b4edfe342b0d759ec16cda3be5e7d8/documentation/asciidoc/computers/legacy_config_txt/boot.adoc
      commit: 42deaefbc8b4edfe342b0d759ec16cda3be5e7d8
      access: public
      verified: 2026-10-07
      fetch: ok
    - name: rpi-docs-uarts
      class: doc
      title: Raspberry Pi documentation, UARTs (configuration/interfaces.adoc)
      url: https://github.com/raspberrypi/documentation/blob/42deaefbc8b4edfe342b0d759ec16cda3be5e7d8/documentation/asciidoc/computers/configuration/interfaces.adoc
      commit: 42deaefbc8b4edfe342b0d759ec16cda3be5e7d8
      access: public
      verified: 2026-10-07
      fetch: ok
    - name: rpi-docs-bcm2712
      class: doc
      title: Raspberry Pi documentation, BCM2712 processor page (processors/bcm2712.adoc)
      url: https://github.com/raspberrypi/documentation/blob/42deaefbc8b4edfe342b0d759ec16cda3be5e7d8/documentation/asciidoc/computers/processors/bcm2712.adoc
      commit: 42deaefbc8b4edfe342b0d759ec16cda3be5e7d8
      access: public
      verified: 2026-10-07
      fetch: ok
    - name: rpi-wiki-property-interface
      class: doc
      title: Raspberry Pi firmware wiki, Mailbox property interface
      url: https://github.com/raspberrypi/firmware/wiki/Mailbox-property-interface
      commit: c9e615a74d377a7e94ac2140336d1352941ef9a2
      retrieval:
        - url: https://github.com/raspberrypi/firmware.wiki.git
          via: git clone
      access: public
      verified: 2026-10-07
      fetch: ok
      note: "covers every Raspberry Pi, not only BCM2711"
    - name: linux-booting
      class: standard
      title: Linux arm64 boot protocol (Documentation/arch/arm64/booting.rst), Linux v7.2
      url: https://github.com/torvalds/linux/blob/8d3ae59288f1e7d58d76558a6ee96d533bc5019f/Documentation/arch/arm64/booting.rst
      commit: 8d3ae59288f1e7d58d76558a6ee96d533bc5019f
      access: public
      verified: 2026-10-07
      fetch: ok
orientation: >-
  The BCM2711 is the SoC of the Raspberry Pi 4 Model B, the Raspberry Pi 400 and Compute Modules
  4 and 4S: four 64-bit Cortex-A72 cores beside a VideoCore VI GPU. (The rest of the published
  Orientation text follows unchanged.)
facts:
  - id: addressing-model
    section: quick-facts
    title: Addressing model
    critical: true
    claim: >-
      The chip has a full 35-bit address map, seen by the Arm cores and by "large address"
      masters such as the DMA4 engines, and a 32-bit "legacy master" view seen by the other DMA
      masters. The datasheet gives peripheral addresses in the legacy view, except the Arm-only
      GIC-400 and ARM_LOCAL blocks. In the full map, Main peripherals are
      `0x4_7C00_0000`–`0x4_7FFF_FFFF` and ARM Local peripherals `0x4_C000_0000`–`0x4_FFFF_FFFF`.
      When the VideoCore enables Low Peripheral mode, the Arm cores alone see Main peripherals at
      `0x0_FC00_0000`–`0x0_FF7F_FFFF` and ARM Local at `0x0_FF80_0000`–`0x0_FFFF_FFFF`.
      Translation: legacy `0x7Enn_nnnn` is full-map `0x4_7Enn_nnnn` and Low Peripheral
      `0x0_FEnn_nnnn`, so UART0 at legacy `0x7E20_1000` is `0x0_FE20_1000` in Low Peripheral
      mode.
    support:
      - class: databook
        doc: bcm2711-peripherals
        at:
          - {section: "1.2.1–1.2.4", pages: ["4", "6"]}
          - {section: "6.5.1–6.5.2", page: "92"}
          - {section: "11.5", pages: ["146", "147"]}

  # Split from v1 Quick-facts/2 "Peripheral mode selection" (D3): the read part ...
  - id: peripheral-mode-selection
    section: quick-facts
    title: Peripheral mode selection
    claim: >-
      `arm_peri_high=1` in `config.txt` selects high peripheral mode, and the firmware also
      selects it on its own when it loads a device tree that suits it. Turning it on without a
      matching device tree stops the board booting, and the stub the firmware supplies does not
      support it, so an `armstub` of your own is needed.
    support:
      - class: doc
        doc: rpi-docs-legacy-boot
        at: [{heading: arm_peri_high}]

  # ... and the concluded part.
  - id: high-peripheral-mode-is-full-map
    section: quick-facts
    title: High peripheral mode is likely the full map
    claim: High peripheral mode is likely the one in which the Arm cores use the full-map addresses.
    support:
      - class: inference
        premises:
          - states: the documentation names high peripheral mode as the alternative to the default
            support:
              - {class: doc, doc: rpi-docs-legacy-boot, at: [{heading: arm_peri_high}]}
          - states: the datasheet gives the Arm cores only two views, the full 35-bit map and Low Peripheral mode
            support:
              - class: databook
                doc: bcm2711-peripherals
                at: [{section: "1.2.1", page: "4"}, {section: "1.2.3", page: "6"}]
        derivation: >-
          if high peripheral mode is not Low Peripheral mode, it is the full map; neither source
          uses both names
    todo:
      check: hardware
      text: with arm_peri_high=1, read the GIC distributor's ID registers at the full-map address.

  - id: secondary-core-release
    section: quick-facts
    title: Secondary-core release (Linux's protocol)
    claim: >-
      The live device tree names each CPU's enable method. For `spin-table`, the CPU's
      `cpu-release-addr` is a naturally aligned, zero-initialized 64-bit word that must lie in a
      region reserved with `/memreserve/`, and the CPU should spin in reserved memory outside the
      kernel; the kernel writes its entry address there little-endian and issues `sev`, and the
      CPU enters with `x0`–`x3` = 0. For `psci`, the CPU stays outside the kernel's memory, the
      tree should carry a `psci` node, and the kernel brings it in with PSCI `CPU_ON` calls.
    support:
      - class: standard
        doc: linux-booting
        at:
          - {heading: CPU enable methods}
          - {heading: Secondary CPU general-purpose register settings}
    todo:
      check: hardware
      text: >-
        which method the stock firmware's device tree names; the permissive and GPL overlays
        cover the stub's spin-table and the tree's release addresses.

  - id: mailbox-buffers-below-4gb
    section: quick-facts
    title: Mailbox buffers below 4 GB
    claim: A property-channel buffer must start below 4 GB.
    support:
      - class: inference
        premises:
          - states: >-
              a mailbox word is 32 bits, carrying the buffer address in its upper 28 bits with the
              low 4 bits holding the channel, and the buffer is 16-byte aligned
            support:
              - {class: doc, doc: rpi-wiki-property-interface, at: [{heading: opening sections}]}
        derivation: >-
          28 bits of address above a 4-bit alignment reach only the first 4 GB; the firmware may
          impose tighter limits that no document states
    todo:
      check: hardware
      text: on an 8 GB board, send a request from a buffer above 1 GB and above 3 GB and check the response.

  - id: gic-arm-local-not-legacy
    section: gotchas
    title: The GIC and ARM_LOCAL bases are not legacy addresses.
    claim: >-
      Every other peripheral address in the datasheet is a legacy master address to translate;
      these two are Arm-only and translate differently (`0x4_C004_0000` or `0xFF84_0000` for the
      GIC).
    support:
      - class: databook
        doc: bcm2711-peripherals
        at: [{section: "6.5.1 and 6.5.2", page: "92"}]

  - id: mini-uart-baud-follows-core-clock
    section: gotchas
    title: The mini UART's baud rate follows the core clock.
    claim: Use UART0 (PL011) for a console that must survive frequency changes, or fix the core clock.
    support:
      - class: doc
        doc: rpi-docs-uarts
        at: [{heading: Mini UART and core frequency}]

  - id: not-the-pi-5-chip
    section: gotchas
    title: Not the Pi 5 chip.
    claim: >-
      The Raspberry Pi 5 family uses the BCM2712, its successor; do not assume any address,
      interrupt number or boot detail here holds for it, and use a `bcm2712` spec instead.
    support:
      - class: doc
        doc: rpi-docs-bcm2712
        at: [{heading: BCM2712}]
```

### `hardware-specs-permissive/specs/bcm2711.spec.yaml` (slice)

```yaml
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
format: 2
kind: overlay
overlays: bcm2711
resources:
  repos:
    - name: rpi-tools
      url: https://github.com/raspberrypi/tools
      commit: 439b6198a9b340de5998dd14a26a0d9d38a6bcac
      license: BSD-3-Clause
      role: source
      files:
        - {path: armstubs/armstub8.S, license_from: notice}
        - {path: armstubs/, license_from: notice, note: "searched for which sources are AArch64; armstub.S and armstub7.S carry BSD notices; the Makefile carries none and is not read for any claim"}
      verified: 2026-10-07
      fetch: ok
      fetch_via: git
  documents:
    - name: rpi-docs-config-boot
      class: doc
      title: Raspberry Pi documentation, config.txt boot options (config_txt/boot.adoc)
      url: https://github.com/raspberrypi/documentation/blob/42deaefbc8b4edfe342b0d759ec16cda3be5e7d8/documentation/asciidoc/computers/config_txt/boot.adoc
      commit: 42deaefbc8b4edfe342b0d759ec16cda3be5e7d8
      access: public
      verified: 2026-10-07
      fetch: ok
    - name: arm-arm
      class: standard
      title: Arm Architecture Reference Manual for A-profile architecture (DDI 0487)
      revision: issue M.d, published 2026-09-29
      url: https://developer.arm.com/documentation/ddi0487/latest
      retrieval:
        - url: https://documentation-service.arm.com/static/6abbec2a6db85c5e6614a4a1
          via: documentation-service
      sha256: 80d589a4645feba6bdb9d77edfaf04d4394d5d5444a4c41f97cf4fdd20eee3d5
      pages: 17150
      access: public
      fetch: ok
    # (also rpi-docs-legacy-boot, tfa-rpi4, bcm2711-peripherals and gic400-trm, as in the base)
assumptions:
  - id: stub-build-identity
    text: >-
      the firmware's built-in 64-bit stubs are built from `armstubs/armstub8.S`, which no
      document states
    todo:
      check: hardware
      text: compare the stub image the firmware loads with this build (see #which-build-ships)
facts:
  - id: which-build-ships
    section: quick-facts
    title: Which build ships
    claim: >-
      For a 64-bit boot on the boards the `enable_gic` page names (it says Raspberry Pi 4B; this
      spec takes its wording to cover every BCM2711 board), the stub the firmware runs by default
      in Low Peripheral mode is most likely `armstub8.S` built with `BCM2711` and `GIC` defined;
      this is a candidate build, held with limited confidence, not an identified shipped
      revision.
    scope:
      modes: [Low Peripheral mode]
      configurations: [64-bit boot]
    support:
      - class: inference
        premises:
          - states: the default stub is built into the firmware and chosen by model and settings
            support: [{class: doc, doc: rpi-docs-config-boot, at: [{heading: armstub}]}]
          - states: >-
              `arm_64bit` defaults to 1 on Raspberry Pi 4, 400 and Compute Module 4 and 4S, so the
              default stub is an AArch64 one
            support: [{class: doc, doc: rpi-docs-config-boot, at: [{heading: arm_64bit}]}]
          - states: the GIC-400 is the default interrupt controller
            support: [{class: doc, doc: rpi-docs-legacy-boot, at: [{heading: enable_gic}]}]
          - states: >-
              in `armstubs/` at the pin, `armstub8.S` is the only AArch64 source, as `armstub.S`
              and `armstub7.S` are 32-bit
            support:
              - class: src
                anchors: [{repo: rpi-tools, path: armstubs/, search: "armstub8.S is the only AArch64 source; armstub.S and armstub7.S are 32-bit"}]
          - assumption: stub-build-identity
          - states: >-
              the firmware finds a magic value in the stub and writes the kernel and device-tree
              load addresses into it
            support: [{class: doc, doc: tfa-rpi4, at: [{heading: TF-A port design}]}]
          - fact: "#patch-words"
            uses: this source carries the magic word and those two words
          - states: its comment says the firmware clears the magic slot for reuse as a release slot
            support:
              - class: src
                anchors: [{repo: rpi-tools, path: armstubs/armstub8.S, lines: [190, 192], symbol: spin_cpu3, comment: true}]
          - states: >-
              its non-`HIGH_PERI` ARM Local base and GIC distributor and CPU-interface addresses
              are the datasheet's Low Peripheral ones
            support: [{class: databook, doc: bcm2711-peripherals, at: [{section: "6.5.1–6.5.2", page: "92"}]}]
          - states: with the distributor at `+0x1000` and the CPU interface at `+0x2000` from the GIC base
            support: [{class: databook, doc: gic400-trm, at: [{section: "3.2", table: "3-1", page: "3-3"}]}]
        derivation: >-
          `BCM2711`, `GIC` and `HIGH_PERI` are the only conditionals in `armstub8.S`, so if the
          assumption holds the default is the `BCM2711` and `GIC` build
    todo:
      check: hardware
      text: >-
        on a recorded board, configuration and firmware release, capture the whole stub image
        the firmware loads (through `setup_gic` past `0x100` and the trailing literals), and
        compare it with this build, excluding the words the firmware patches at
        `0xF0`–`0xFF`; or boot this build with `armstub=` and scope observations to it.

  - id: generic-timer-frequency
    section: quick-facts
    title: Generic timer frequency
    claim: The BCM2711 build writes 54000000 (54 MHz) to `CNTFRQ_EL0` and 0 to `CNTVOFF_EL2`.
    support:
      - class: src
        anchors:
          - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [53, 57], symbol: OSC_FREQ}
          - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [110, 112], symbol: OSC_FREQ}
          - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [114, 115], symbol: CNTVOFF_EL2}

  - id: scr-el3-bits
    section: quick-facts
    title: SCR_EL3 bits
    claim: >-
      The stub's `SCR_EL3` value sets RW (bit 10), HCE (bit 8), SMD (bit 7), bits 5 and 4, and NS
      (bit 0), and writes it to `SCR_EL3`. By the architecture's field definitions, EL2 then runs
      in AArch64 and non-secure, HVC is enabled, and SMC is undefined at EL2; at EL1 it is
      undefined unless EL2 traps it first through `HCR_EL2.TSC`, which takes priority.
    support:
      - class: src
        anchors:
          - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [59, 66], symbol: SCR_VAL}
          - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [121, 123], symbol: SCR_VAL}
      - class: standard
        doc: arm-arm
        at:
          - {section: "D24.2.168", heading: "SCR_EL3 RW", page: "D24-9638"}
          - {section: "D24.2.168", heading: "SCR_EL3 HCE and SMD", pages: ["D24-9639", "D24-9640"]}
          - {section: "D24.2.168", heading: "SCR_EL3 NS", page: "D24-9641"}

  - id: scr-el3-value
    section: quick-facts
    title: SCR_EL3 value
    claim: The value the stub writes is `0x5B1`.
    support:
      - class: inference
        premises:
          - fact: "#scr-el3-bits"
            uses: the six bits its anchors show, which the source names by bit position and never sums
        derivation: 0x400 + 0x100 + 0x80 + 0x20 + 0x10 + 0x1 = 0x5B1
    todo:
      check: hardware
      text: the register is EL3-only, so read it with a debugger that can access EL3 state.

  - id: smpen-at-el3
    section: quick-facts
    title: SMPEN at EL3
    claim: Before dropping to EL2 the stub writes `CPUECTLR_EL1` with only bit 6, SMPEN, set.
    support:
      - class: src
        anchors:
          - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [71, 72], symbol: CPUECTLR_EL1_SMPEN}
          - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [129, 131], symbol: CPUECTLR_EL1_SMPEN}
notices:
  - repo: rpi-tools
    path: armstubs/armstub8.S
    text: |
      Copyright (c) 2016-2019 Raspberry Pi (Trading) Ltd.
      (the second copyright line and the BSD-3-Clause text follow unchanged)
```

The "Which build ships" record shows four things the Markdown bullet held only in prose: the
assumption is a named entry that other facts can list in `assumes`; the "only AArch64 source"
premise, which had no citation in v1, is a `search` anchor the verifier repeats; the reference to
the "Patch words" bullet is a fact reference; the comment premise is an anchor marked `comment`.
Because its citations gained structure, this fact's verdict does not carry: it is re-verified.

### `hardware-specs-gpl/specs/bcm2711.spec.yaml` (slice)

```yaml
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: GPL-2.0-only
format: 2
kind: overlay
overlays: bcm2711
resources:
  repos:
    - name: linux
      url: https://github.com/torvalds/linux
      commit: 8d3ae59288f1e7d58d76558a6ee96d533bc5019f
      license: GPL-2.0-only
      role: source
      status: merged
      files:
        - {path: arch/arm/boot/dts/broadcom/bcm2711.dtsi, license_from: spdx-line}
        - {path: arch/arm/boot/dts/broadcom/bcm283x.dtsi, license_from: license-file}
      verified: 2026-10-07
      fetch: ok
      fetch_via: git
      note: "Linux v7.2. bcm283x.dtsi carries no SPDX line and falls under the tree's GPL-2.0 COPYING."
facts:
  # Split from v1 Quick-facts/1 "Address translation in the tree" (D3): the DT part ...
  - id: address-translation-in-the-tree
    section: quick-facts
    title: Address translation in the tree
    critical: true
    claim: >-
      The root uses two address cells and one size cell. The `soc` bus maps legacy `0x7E00_0000`
      (24 MB) to `0xFE00_0000`, `0x7C00_0000` (32 MB) to `0xFC00_0000`, and the ARM Local block,
      which the tree addresses as `0x4000_0000`, to `0xFF80_0000` (8 MB). Its `dma-ranges` maps
      bus `0xC000_0000` to physical `0x0` for 1 GB.
    support:
      - class: DT
        anchors:
          - {repo: linux, path: arch/arm/boot/dts/broadcom/bcm2711.dtsi, lines: [10, 11]}
          - {repo: linux, path: arch/arm/boot/dts/broadcom/bcm2711.dtsi, lines: [34, 45], node: soc}

  # ... and the cross-spec inference, which now references the docs fact by id.
  - id: tree-describes-low-peripheral-mode
    section: quick-facts
    title: The tree describes Low Peripheral mode
    claim: The tree describes Low Peripheral mode.
    support:
      - class: inference
        premises:
          - fact: "#address-translation-in-the-tree"
            uses: the tree's physical targets
          - fact: "bcm2711@hardware-specs-docs#addressing-model"
            uses: >-
              Low Peripheral mode places Main peripherals at `0x0_FC00_0000`–`0x0_FF7F_FFFF` and
              ARM Local at `0x0_FF80_0000`
        derivation: >-
          the targets fall in those ranges, not in the full-map ranges at `0x4_7C00_0000` and
          `0x4_C000_0000`
    todo:
      check: hardware
      text: compare the live tree on a board booted with arm_peri_high=1.

  - id: gic-node
    section: quick-facts
    title: GIC node
    critical: true
    claim: >-
      `arm,gic-400`, `#interrupt-cells = <3>`, with distributor `0x4004_1000` (4 KB), CPU
      interface `0x4004_2000` (8 KB), virtual interface control `0x4004_4000` and virtual CPU
      interface `0x4004_6000` in the `soc` bus's ARM Local range, so `0xFF84_1000` and
      `0xFF84_2000` for the first two; its maintenance interrupt is PPI 9 (ID 25), encoded with
      the `IRQ_TYPE_LEVEL_HIGH` flag on all four CPUs.
    support:
      - class: DT
        anchors:
          - {repo: linux, path: arch/arm/boot/dts/broadcom/bcm2711.dtsi, lines: [56, 66]}

  - id: reserved-stub-page
    section: quick-facts
    title: Reserved stub page
    claim: >-
      A `/memreserve/` covers physical `0x0`-`0xFFF`, commented as where the firmware's startup
      stubs live and the secondary CPUs spin.
    support:
      - class: DT
        anchors:
          - {repo: linux, path: arch/arm/boot/dts/broadcom/bcm283x.dtsi, lines: [8, 11]}
```

The cross-root inference names its premise's root, `bcm2711@hardware-specs-docs#addressing-model`;
the GPL overlay may also hold a fact named `addressing-model` without any clash. The reference is
gated transitively: its premise lives in
the documents-only root and cites no repository, so nothing it reaches is outside the GPL root's
accepts list. The same reference written from the docs root to a GPL fact would fail the gate.

### `hardware-specs-gpl/specs/resources/bcm2711.verify.yaml` (slice, right after migration)

```yaml
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: GPL-2.0-only
format: 2
spec: bcm2711
spec_file: bcm2711.spec.yaml
spec_sha256: <64 hex>
canonical: fact-v1
sources:
  - {name: linux, commit: 8d3ae59288f1e7d58d76558a6ee96d533bc5019f, fetch: ok}
summary: {pass: 2, fail: 0, unverifiable: 0, gap: 0, adjudicate: 0}
verdicts:
  gic-node:
    basis: <64 hex>
    verdict: PASS
    date: 2026-10-08
    verifier: "Claude Opus 5.5, Claude Code subagent"
    note: >-
      lines 56-66: `arm,gic-400`, three interrupt cells, reg 0x40041000/0x1000,
      0x40042000/0x2000, 0x40044000, 0x40046000; translated through the ARM Local range to
      0xff841000 and 0xff842000; maintenance interrupt GIC_PPI 9 with GIC_CPU_MASK_SIMPLE(4) and
      IRQ_TYPE_LEVEL_HIGH (PPI 9 is ID 25).
    carried_from:
      repo: hardware-specs-gpl
      commit: cd911120663da72f4101161eef5a22dc13d0cc86
      path: specs/resources/bcm2711.verify.md
      key: 'Quick-facts/2 "GIC node"'
      format: 1
  reserved-stub-page:
    basis: <64 hex>
    verdict: PASS
    date: 2026-10-08
    verifier: "Claude Opus 5.5, Claude Code subagent"
    note: >-
      bcm283x.dtsi line 11 reserves 0x0 for 0x1000; the comment on lines 8-10 is attributed as a
      comment and matches (firmware startup stubs, secondary CPUs spinning). bcm2711.dtsi
      includes bcm283x.dtsi (line 2).
    carried_from:
      repo: hardware-specs-gpl
      commit: cd911120663da72f4101161eef5a22dc13d0cc86
      path: specs/resources/bcm2711.verify.md
      key: 'Quick-facts/6 "Reserved stub page"'
      format: 1
```

The carried verdicts leave out `contrary_evidence` and `citation_precision`: the format 1 record
did not state them per bullet, and a carried verdict records only what the earlier record said.
They also have no `readers`: an optional list is absent rather than empty (SF2-1, 2026-10-08).
What `spec.py status` reports for this slice: `gic-node` and `reserved-stub-page`
current (carried); `address-translation-in-the-tree` and
`tree-describes-low-peripheral-mode` unverified, because the split changed the first claim's
text and created the second. `gic-node` is `critical` and has one reader, so under
`--require-verified` the check also asks for a second reader (the v1 record ran its second reader
separately and recorded no verdict of its own, so there is nothing to carry). Delta verification
covers exactly those items; nothing else is re-read. If the docs spec later edits
`addressing-model`, only `tree-describes-low-peripheral-mode` goes stale here: it shows as
upstream-stale, a warning on the GPL repository's `main`, and an error on the next pull request
to that repository until it is re-verified (D19).

### Markdown view (merged, with status; slice)

The Markdown view CI publishes for the merged `bcm2711`. Headings, provenance blocks and status
are generated from fields; the claim paragraphs are the authors' text as written. The viewer shows
the same facts with badges ([Rendering and the viewer](#rendering-and-the-viewer)).

This slice follows the SF2-4 fixture view: resource tables and other facts are omitted.
`uses` and `derivation` are escaped literal text, not code or emphasis; premise citations
are nested list items. Repository citations retain full commits. The banner uses explicit
`--source-commit` and `--tool-commit` values when supplied, otherwise “unavailable”; SHA256
is over the checked bytes (hashes below are abbreviated as a label). The docs fixture has
no verification record, and carried zero basis hashes in the GPL fixture read stale.

~~~markdown
> Generated by `spec.py render`. Do not edit.
> Canonical form `fact-v1`; driver-lab unavailable.
> Source `hardware-specs-docs:bcm2711.spec.yaml`; commit unavailable; SHA256 `<checked-byte hash>`.
> Source `hardware-specs-permissive:bcm2711.spec.yaml`; commit unavailable; SHA256 `<checked-byte hash>`.
> Source `hardware-specs-gpl:bcm2711.spec.yaml`; commit unavailable; SHA256 `<checked-byte hash>`.

# Broadcom BCM2711 \(Raspberry Pi 4\, Raspberry Pi 400\, Compute Module 4 and 4S\)

`bcm2711` · soc · triggers: bcm2711, raspberry pi 4 soc, pi 4 soc, pi 400 soc, cm4 soc

## Context (not facts)

The BCM2711 is the SoC of the Raspberry Pi 4 Model B, the Raspberry Pi 400 and Compute Modules 4 and 4S: four 64-bit Cortex-A72 cores beside a VideoCore VI GPU. (The rest of the published Orientation text follows unchanged.)

## Quick\-facts

#### Addressing model

The chip has a full 35-bit address map, seen by the Arm cores and by "large address" masters such as the DMA4 engines, and a 32-bit "legacy master" view seen by the other DMA masters. The datasheet gives peripheral addresses in the legacy view, except the Arm-only GIC-400 and ARM_LOCAL blocks. In the full map, Main peripherals are `0x4_7C00_0000`–`0x4_7FFF_FFFF` and ARM Local peripherals `0x4_C000_0000`–`0x4_FFFF_FFFF`. When the VideoCore enables Low Peripheral mode, the Arm cores alone see Main peripherals at `0x0_FC00_0000`–`0x0_FF7F_FFFF` and ARM Local at `0x0_FF80_0000`–`0x0_FFFF_FFFF`. Translation: legacy `0x7Enn_nnnn` is full-map `0x4_7Enn_nnnn` and Low Peripheral `0x0_FEnn_nnnn`, so UART0 at legacy `0x7E20_1000` is `0x0_FE20_1000` in Low Peripheral mode.

**Provenance** (generated):

- databook: BCM2711 ARM Peripherals \(release 4 \(2022\-01\-18\)\, Raspberry Pi document RP\-008248\-DS\); §1\.2\.1–1\.2\.4\, pp\. 4–6; §6\.5\.1–6\.5\.2\, p\. 92; §11\.5\, pp\. 146–147
- `bcm2711@hardware-specs-docs#addressing-model` · bring-up critical · unverified (second reader missing)

#### High peripheral mode is likely the full map

High peripheral mode is likely the one in which the Arm cores use the full-map addresses.

**Provenance** (generated):

- inference, from:
  - the documentation names high peripheral mode as the alternative to the default
    - doc: Raspberry Pi documentation\, legacy config\.txt boot options \(legacy\_config\_txt\/boot\.adoc\); heading\: arm\_peri\_high
  - the datasheet gives the Arm cores only two views\, the full 35\-bit map and Low Peripheral mode
    - databook: BCM2711 ARM Peripherals \(release 4 \(2022\-01\-18\)\, Raspberry Pi document RP\-008248\-DS\); §1\.2\.1\, p\. 4; §1\.2\.3\, p\. 6
- derivation: if high peripheral mode is not Low Peripheral mode\, it is the full map\; neither source uses both names
- TODO (verify on hardware): with arm\_peri\_high\=1\, read the GIC distributor\'s ID registers at the full\-map address\.
- `bcm2711@hardware-specs-docs#high-peripheral-mode-is-full-map` · unverified

### Overlay: public (hardware\-specs\-gpl)

#### The tree describes Low Peripheral mode

The tree describes Low Peripheral mode.

**Provenance** (generated):

- inference, from:
  - `bcm2711@hardware-specs-gpl#address-translation-in-the-tree` (Address translation in the tree): the tree\'s physical targets
  - `bcm2711@hardware-specs-docs#addressing-model` (Addressing model): Low Peripheral mode places Main peripherals at \`0x0\_FC00\_0000\`–\`0x0\_FF7F\_FFFF\` and ARM Local at \`0x0\_FF80\_0000\`
- derivation: the targets fall in those ranges\, not in the full\-map ranges at \`0x4\_7C00\_0000\` and \`0x4\_C000\_0000\`
- TODO (verify on hardware): compare the live tree on a board booted with arm\_peri\_high\=1\.
- `bcm2711@hardware-specs-gpl#tree-describes-low-peripheral-mode` · unverified

#### GIC node

`arm,gic-400`, `#interrupt-cells = <3>`, with distributor `0x4004_1000` (4 KB), CPU interface `0x4004_2000` (8 KB), virtual interface control `0x4004_4000` and virtual CPU interface `0x4004_6000` in the `soc` bus's ARM Local range, so `0xFF84_1000` and `0xFF84_2000` for the first two; its maintenance interrupt is PPI 9 (ID 25), encoded with the `IRQ_TYPE_LEVEL_HIGH` flag on all four CPUs.

**Provenance** (generated):

- DT: linux\@8d3ae59288f1e7d58d76558a6ee96d533bc5019f \(GPL\-2\.0\-only\) arch\/arm\/boot\/dts\/broadcom\/bcm2711\.dtsi lines 56–66
- `bcm2711@hardware-specs-gpl#gic-node` · bring-up critical · PASS 2026\-10\-08 · stale (carried from format 1\; second reader missing)
~~~

Nothing in this Markdown stops a claim from containing its own "**Provenance** (generated):"
line; that is the limit the viewer exists to close.

## Decisions (2026-10-08)

The user settled each open choice of the first draft on 2026-10-08. The body above follows these;
where the user chose other than the draft's recommendation, the entry says so. D20–D22 settle three calls the first revision
left open, also decided by the user on 2026-10-08.

| # | Question | Decision | Reason |
| --- | --- | --- | --- |
| D1 | Fact ids in overlays | **Root-qualified references** (not the recommended root prefix). Ids are free and unique per spec id per root; a reference into another root names it, `bcm2711@hardware-specs-gpl#gic-node`; `#<id>` and `<spec id>#<id>` stay short within a root | no collisions across repositories and no extra marker field; every cross-root reference says which repository it points into ([References](#references)) |
| D2 | Freshness of verdicts | Per-fact basis hashes; `spec_sha256` kept for information | delta verification becomes mechanical and format-only edits stale nothing |
| D3 | Facts that mix classes | Read classes support a claim jointly; an `inference` stands alone in its fact | keeps most v1 bullets whole while every conclusion gets its own verifiable record |
| D4 | Markup in claims and prose | **CommonMark allowed, enforced separation in the viewer** (not the recommended plain text). Claims, prose and notes may use lists, emphasis, links, tables and code; **no raw HTML**, rejected by the checker (a decision, confirmed by the user, not an overridable default); no tool parses the Markdown for meaning; the viewer's badges, drawn from fields, carry provenance | authors keep full Markdown; the Markdown view cannot stop prose that imitates a cited fact, so the guarantee lives in the viewer, where author text cannot produce a badge ([Rendering and the viewer](#rendering-and-the-viewer)) |
| D5 | Where rendered views live | **Built and published by CI** (Pages on `main`, an artifact on pull requests), **not committed** (not the recommended committed `rendered/`) | no generated files in the repositories and no freshness check; readers use the published site |
| D6 | Scalar types | The loader resolves only `true`, `false`, `null` and decimal integers; hex values are strings with patterns | no implicit-typing surprises; values keep their spelling |
| D7 | Where the format lives | A new reference skill, `skills/spec-format/`; `board-expert/SPEC-FORMAT.md` becomes a pointer | one home for rules every spec skill shares; no skill renamed |
| D8 | JSON Schema validator | `jsonschema`, subject to a `dep-quality` score before pinning | full 2020-12 support in the most used implementation |
| D9 | YAML library and rewriting | PyYAML; `drift --rewrite` replaces scalar spans found by node marks | one library, already used here; comments and the SPDX header survive |
| D10 | Carrying v1 verdicts | Carry when the claim text is byte-identical and a fresh conversion-fidelity check passes; re-verify the rest (at most 61 of 65 carry) | does not repeat RG1's verification for unchanged facts, and no conversion error carries a PASS |
| D11 | Transition | Read-only v1 checker; migrate docs, then permissive, then gpl in one unit; then remove v1 and `mdtokens.py` (markdown-it-py stays as the one CommonMark library, D20) | no mixed v1 and v2 composition, and no second parser left behind |
| D12 | Licenses per cited file | One license per repos entry, a closed `files` list stating how each license was confirmed, checked by `resolve` | catches a file whose license differs from its entry without a per-file gate |
| D13 | References across roots | Transitive license gate | the placement rule holds through references, for any root's accepts list |
| D14 | Second readers | `critical: true`; a second reader's verdict is required for each critical fact | the record shows whether the second verifier ran |
| D15 | `source-observed` | Kept as the extension class; its fields come from a schema fragment the extension supplies, named in the root marker | the extension keeps working without driver-lab defining its content |
| D16 | Verdict granularity | One verdict per register or sequence fact; sub-keys for fields or steps with their own support | precise where the author cited precisely, without hundreds of records |
| D17 | File names | Every spec is `<name>.spec.yaml`; `kind` says what it is | one glob, one rule |
| D18 | Conflict entries | The `conflicts` field now | DESIGN.md's proposal gets a home, and RG1's documentation-versus-source contradiction is recorded as one |
| D19 | Cross-root staleness (raised from the draft's Risks table) | A fact staled through a reference into another root is a **warning on the dependent repository's `main`**; **any pull request to the dependent repository must re-verify** it (`--require-verified` treats it as an error there) | an upstream merge never turns another repository's `main` red, and stale facts cannot ride along on the next change there ([Freshness](#freshness-per-fact-basis-hashes-d2)) |
| D20 | How "no raw HTML" is checked (raised by the first revision) | **Parse with CommonMark**: the checker rejects only what CommonMark treats as raw HTML, inline or block; code spans and code blocks are not HTML; autolinks (`<https://…>`) are allowed, under the link-scheme rule. Replaces the draft's lexical rule | no false rejections of angle brackets in code, at the cost of the checker importing a pinned CommonMark library, used only for this and D22, never for meaning |
| D21 | Links and images in author text (raised by the first revision) | As drafted: images render as links, never `<img>`; link and autolink schemes limited to `https`, `http`, `mailto` and in-page anchors | no remote content loads from a spec page, and no script URL becomes a link |
| D22 | Containment (raised by the first revision) | **In the checker too**: a heading inside a claim or prose field, or a code fence that never closes, fails the checker, and still the publish step | an author learns at check time, before review, not when the published view is built |

## Risks

| Risk | Consequence | Mitigation |
| --- | --- | --- |
| Author Markdown imitates provenance (D4) | in the Markdown view, a claim or prose paragraph can look like a cited fact | stated as a limit of the Markdown view; the viewer's badges cannot be produced by author text; a lint warns on v1 tag spellings in text; review reads the viewer, not the Markdown |
| Author Markdown breaks layout (an unclosed fence, a heading in a claim) | later facts swallowed or split in the Markdown view | the checker's containment check fails it, naming the fact, and the publish step checks again (D22); each field is rendered separately in the viewer |
| Raw HTML reaches a page | script or markup injected into the published site | the checker rejects what CommonMark parses as raw HTML (D20); the viewer renders with HTML disabled; image and link URL rules (D21) |
| YAML authoring errors by agents (indentation, quoting long claims) | failed checks, retries | block scalars for long text; every error carries a line and column; templates per kind; `spec.py check` run before any review |
| The canonical form changes | every verdict stale at once | versioned (`canonical: fact-v1`); a change ships with a re-hash command that re-keys verdicts only when the old and new forms agree on the data |
| A verdict depends on something its fact does not cite | not staled when that changes | coverage review separate; `spec_sha256` kept; the verifier is told to record any extra dependency as a `relates` link |
| Cross-root staleness | a docs edit stales facts in the GPL repository | decided (D19): a warning on that repository's `main`, an error on its next pull request; the status line names the upstream fact |
| A root is renamed | every root-qualified reference into it dangles (D1) | root names are an interface: the checker reports each dangling reference, and a rename is a planned change across the repositories that cite it |
| Published views are stale or the Pages deploy fails | readers see an older view than `main` | the banner names the commits the view was built from; the weekly scheduled build; the YAML on GitHub is always current |
| Reviewers miss the rendered effect of a change, since nothing is committed | a layout or badge regression merges | pull requests upload both views as an artifact; the containment check fails the checker and the build |
| Conversion error carried as PASS | a wrong citation keeps a verdict | fidelity check (D10); `resolve` runs on every anchor during migration |
| New dependency risk (validator, compiled `rpds-py`, the CommonMark library) | supply-chain and build breakage in CI | `dep-quality` score before pinning; hash-pinned CI requirements; exit 3 without them |
| The checker's CommonMark parse is used for more than safety and layout | provenance drifts back into text, the v1 failure | the parse lives in one module whose only outputs are raw-HTML, link-scheme, heading and unclosed-fence findings; review rejects any other use; provenance is read only from structured fields |
| The CommonMark library changes what counts as HTML or a heading between versions | a field passes under one version and fails under another | one pinned version shared by checker and publish step; a version bump is its own reviewed change with the fixtures re-run |
| The schema grows its own equivalent spellings (optional fields that mean the same) | the leak returns at the data level | closed records (`unevaluatedProperties: false`); one field per meaning; review asks "is there a second way to say this?" for every schema change |
| Consumers outside driver-lab read `*.spec.md` | they break at the cutover | `board-expert` is the only reader of specs; bringup-kit reads through it; transition window (D11) |
| The viewer grows past its first static version | scope creep | this design covers the static viewer with badges only; search and navigation are later work on the same data |

## Implementation outline

Session-sized units; the plan with acceptance criteria comes after this design is approved. Each
tooling unit is reviewed by an executing reviewer (break cases including degenerate inputs,
mutation checks) and a diff reader, the pairing RG-T1 showed finds different holes.

1. **SF2-1 Loader and schema.** `dep-quality` on the validator candidates, PyYAML and the
   CommonMark library (markdown-it-py), then pin;
   `load_strict` with every pitfall in the loader table as a failing fixture; `spec.schema.json`,
   `verify.schema.json`, `root.schema.json`; schema fixtures (one good file per kind, one bad file
   per rule).
2. **SF2-2 Checker.** `spec.py check`: id uniqueness per spec per root, root names, the three
   reference forms with root-qualified references across roots, cycles, layer order, license gate
   direct and transitive, records (keys, summary, basis hashes, upstream-stale, two readers),
   `--require-verified` behavior on pull requests versus `main` (D19), the CommonMark checks
   (raw HTML, link schemes, headings, unclosed fences; D20–D22) in one module with adversarial
   fixtures (HTML in every CommonMark form, HTML-like text in code, autolinks, `javascript:`
   links, setext headings, fences closed by an over-indented line), privacy, placeholders; the license-gate fixture matrix and the
   board-expert fixtures rewritten in format 2, with `expected.json` carried over.
3. **SF2-3 Resolve and drift.** `spec.py resolve` (fetch pins, `src` and `DT` anchors, per-file
   licenses, document hashes), `show`, `drift --rewrite` on YAML, `inventory` on register records.
4. **SF2-4 Render, viewer and status.** `spec.py render` for the Markdown view and the static
   viewer (single and merged, with status); escaping of generated text, the containment check and
   the viewer's badge and HTML rules, each with adversarial fixtures (claims that imitate
   provenance, unclosed fences, headings, HTML, `javascript:` links); the publish step's repeat
   of the D22 check through the same module; `status --stale`.
5. **SF2-5 Skills.** The contract document (D7), `spec-verifier`, `board-expert`,
   `board-spec-scaffold` templates, `hardware-investigator`, `peripheral-spec` and its subagent
   and verifier templates, `reference-driver-review`; glossary; grep every skill for v1 rules (the
   RG-T1 T7 lesson).
6. **SF2-6 Migration of bcm2711.** `spec.py migrate`, citation pass, splits, fidelity check,
   carried records, delta verification of the rest; the three spec repositories' pull requests
   (docs, permissive, gpl) with their `checks.sh` and CI on format 2, and each repository's
   publish workflow and Pages site.
7. **SF2-7 Retire format 1.** Remove the v1 checker, `mdtokens.py` and `anchor_check.py`'s
   Markdown mode; markdown-it-py stays as the pinned CommonMark library (D20); update
   driver-lab's `AGENTS.md` check list and CI.

## What this design does not cover

- The viewer and search UI (it reads the YAML and records; designed later).
- A coverage-review record (what a spec leaves out); RG1 showed it is a separate job.
- Changes to what the provenance classes mean or how much each is trusted.
- Specs for hardware with no existing driver ([DESIGN.md](../DESIGN.md), "When there is no
  existing driver").

## How the learnings map to this design

The format-related rows of [SPEC-REGEN-learnings](../notebook/SPEC-REGEN-learnings.md) and the
RG-T1 rounds:

| Learning (source) | Where it lands |
| --- | --- |
| Store facts as structured data; do not parse provenance out of Markdown (RG-T1 rounds 3–8) | the whole format |
| Parse a format once; two scanners disagree (RG-T1 rounds 3–5) | one loader, one schema, one checker over parsed data |
| Empty anchors and aliases evaded the gate (RG-T1 T1, T2) | closed records; one citation form per class; `minLength` and required fields |
| A URL reached `git fetch` as an option (RG-T1 R1) | `https://` pattern in the schema; `--` before positional arguments kept |
| Invisible characters and emphasis hid an anchor (RG-T1 round 8) | provenance is not text; the loader rejects invisible and control characters |
| `summary` lacks `adjudicate`; `sources` has no document hash (RG1 re-verification) | five-key `summary`; `sha256` in record sources |
| Say whether the second verifier ran (RG1) | `critical` and `readers` (D14) |
| A derivation inside a `[doc]` bullet needs `[inference]` (RG1 V5); mixed bullets | inference stands alone; splits (D3) |
| A `[src]` bullet about where hardware is needs a document class too (RG1 V8) | a verifier rule, now stated against the `support` list a verifier can see at a glance |
| Explicit build-identity assumption (RG1 A4) | `assumptions` registry and `assumes` |
| DT comments attributed (RG1 GPL Quick-facts/6, /7) | `comment: true` on anchors |
| Confirm the license per cited file (RG1 V3, C5) | `files` with `license_from`, checked by `resolve` (D12) |
| Canonical resource and retrieval URL for Arm documents (RG1 C6, C17, C19) | `url` and `retrieval` |
| Citation precision graded explicitly (RG1 V2) | structured locators; `citation_precision` in the record |
| TODO methods must be able to observe the thing (RG1 C4) | `todo.method` beside `todo.text` |
| Contrary-evidence step (RG1 final pass) | `contrary_evidence` in the record |
| Delta verification by hand, five rounds (RG1) | basis hashes and `status --stale` (D2) |
| Overlay records skipped; one record path for base and overlay (RG1 V4, RG-T1 T3) | per-file records, checked by key against the file they sit beside |
| `[DT]` facts take the tree's license (RG1 implementer) | `DT` anchors gated like `src` |
