<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Spec format 2: facts as YAML records, validated by a JSON Schema (design)

Status: **design draft, 2026-10-08, for the user's approval.** Nothing here is built. The
direction (one YAML format for every spec, validated by a JSON Schema, with Markdown as a rendered
view) was approved by the user on 2026-10-08 ([RG-regen](../notebook/RG-regen.md), "RG-T1 rounds
6–8, merge, and the format decision"). The choices the user still has to make are listed under
[Open decisions](#open-decisions); where the body below depends on one, it states the
recommended option and points there.

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
- **Fact reference** — `<spec id>#<fact id>`, or a bare `<fact id>` inside the same spec: how a
  premise, a relation or a verification verdict names a fact.
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
- **Rendered view** — the Markdown generated from the YAML for people to read. It is never
  edited and never parsed for meaning.
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
  make that checkable. A fact reference (`bcm2711#addressing-model`) does it directly.
- **Unchecked parentheticals.** `[DT]` parentheticals such as "(bcm2711.dtsi lines 10-11,
  linux)" were never resolved against the pinned tree, and `[doc]` locators were never checked
  against the document's page count. Structured citations make both mechanical.

## Requirements

User decisions of 2026-10-08:

- **R1 One format for every spec**: board, SoC, chip, IP block, peripheral spec, review, and the
  facts file `hardware-investigator` returns. YAML, validated by a JSON Schema (draft 2020-12).
- **R2 Markdown is a rendered view** (later also a viewer and search UI). It is generated, never
  edited, and never parsed for meaning.
- **R3 Facts are records with stable ids; citations are structured fields**, never prose
  patterns.

Carried over unchanged from the license split ([LICENSE-SPLIT.md](LICENSE-SPLIT.md)): three
spec repositories (`hardware-specs-docs`, `hardware-specs-permissive`, `hardware-specs-gpl`), the
placement rule, root markers with `license:` and `accepts:`, overlays across repositories, the
license gate, and per-file verification records.

Non-goals: changing what the evidence classes mean ([DESIGN.md](../DESIGN.md), "Evidence
model"); new specs; the viewer itself; the frozen archive (it stays as it is, see
[Migration](#migration)).

## Overview

| File | Today | Format 2 |
| --- | --- | --- |
| Board, SoC, chip, IP spec | `<id>.spec.md` (YAML front matter, Markdown body) | `<name>.spec.yaml` |
| Overlay | `<id>.spec.md` with `overlays:` | `<name>.spec.yaml` with `kind: overlay` |
| Peripheral spec | `<device>-spec.md` (`Source pin:` lines, anchors in prose) | `<name>.spec.yaml`, `kind: peripheral` |
| Review | `<driver>-review.md` (`Impl pin:`/`Ref pin:`) | `<name>.spec.yaml`, `kind: review` |
| Investigator facts file | Markdown with `Source pin:` | `<name>.facts.yaml`, `kind: facts` |
| Root marker | `board-specs.yaml` | `board-specs.yaml`, plus `format: 2` and `fact_prefix` |
| Verification record | `<root>/resources/<name>.verify.md` | `<root>/resources/<name>.verify.yaml` |
| Rendered view | none (the spec is the view) | `rendered/<name>.md`, generated (D5) |
| Schema | none | `spec.schema.json`, `verify.schema.json`, `root.schema.json` (D7) |

One loader reads every file (the [YAML loader](#the-yaml-loader)); the validator checks it
against the schema; a small checker does what a schema cannot
([Validation](#validation-schema-and-checker)). One command-line tool, `spec.py`, has the
subcommands `check`, `resolve`, `render`, `show`, `status`, `drift`, `inventory` and `migrate`,
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
aliases: []
cache: rpi4-resources
instances: []             # soc and chip only; see Instances
resources: {}             # documents, repos, series, tools; see Resources
assumptions: []           # named assumptions facts rest on; see Assumptions
orientation: >-           # prose, not facts; see Prose that is not a fact
  The BCM2711 is the SoC of ...
facts: []                 # the fact records, in reading order
notices: []               # source notices a license asks the spec to carry
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
- id: gic-arm-local-not-legacy        # [a-z0-9-] (overlay facts: <prefix>.<id>); unique in the merged spec
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
  relates: [{fact: "bcm2711#addressing-model", relation: qualifies}]
  conflicts: [...]                            # see Conflict entries
  data: {...}                                 # typed payload: register, sequence, finding, ...
  note: "..."                                 # uninterpreted remark for readers
```

| Field | Rule |
| --- | --- |
| `id` | Stable for the life of the fact: editing the claim, moving the section or reordering never changes it. Overlay facts carry their root's prefix (D1). A deleted fact's id is not reused. |
| `title` | The bold lead-in today. Required for board-spec kinds (every bcm2711 bullet has one); optional elsewhere. |
| `claim` | Plain text with `` `code spans` `` (D4). Never contains a citation: provenance lives only in `support`. One claim per fact: a sentence concluded rather than read is its own `inference` fact (D3). |
| `support` | One or more support entries ([Provenance classes](#provenance-classes)). Entries of read classes support the claim jointly, as a v1 tag clause does. An `inference` entry stands alone. `emulated` never stands alone. |
| `todo` | `check`: `hardware`, `document` or `source` (what kind of check would settle it); `text`: what to check and how; optional `method` when the method is worth stating apart, so the verifier can judge whether it can observe the thing (RG1 C4). Required for `press`, `inference`, `emulated` and extension classes; allowed on any fact. |
| `assumes` | Ids from the spec's `assumptions` registry. A fact resting on an unstated assumption was a recurring verifier finding (RG1 A4); here the assumption is named once and every fact that rests on it lists it. |
| `scope` | Lists of strings naming where the claim holds: `boards`, `revisions`, `modes`, `builds`, `configurations`. Rendered beside the claim. A claim true of one tree and written as true of both was a recurring `FAIL` on definiteness; `scope` gives it a place. |
| `critical` | Marks a bring-up-critical fact (addressing model, entry state, debug UART, debug console). The checker requires two readers in the record for it (D14). |
| `requirement` | Peripheral specs and reviews: `hw-required` (must have a document-class support entry), `comment-explained` (must cite a code comment), `driver-choice`, `as-implemented` (goes on the generated verify-on-hardware list). |
| `relates` | Typed links to other facts: `qualifies`, `contradicts`, `refines`, `same-as`. Used by the renderer, by staleness ([Verification records](#verification-records)) and later by the viewer. |
| `data` | A typed payload for structured facts (instances, registers, sequences, findings); see [Peripheral specs and reviews](#peripheral-specs-and-reviews). |
| `note` | Free text, rendered as a note; never evidence. |

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
and its TODO like any fact.

### Prose that is not a fact

`orientation` (all kinds) and a few kind-specific prose fields (`milestones` for peripheral
specs, `notes` for reviews) hold text that no tool interprets. The renderer prints them under
their headings, marked as uncited context, and escapes them (D4). A fact never lives in prose: a
statement a reader would act on goes in `facts`.

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
| `source-observed` | defined by the extension that uses it | | yes | per the extension | kept as the one extension class in use (D15) |

### Locators (`at`)

A locator is a mapping with at least one of `section`, `page`, `pages`, `table`, `figure`,
`clause`, `heading`; all values are strings, so "92", "D24-9638" and "4-91" all fit. `pages` is a
two-item list. When the document entry gives `pages` (a count) and a locator's page is a plain
number, the checker requires it within the count; the entry's `page_numbering` says whether the
numbers are printed or PDF page numbers. A `databook` or `standard` locator must carry `section`,
`page`, `pages`, `table`, `figure` or `clause`; a `doc` locator may be a `heading` alone (most
project documentation has no page numbers). This is the citation-precision rule RG1 asked for (V2)
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
  `node` instead.
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
      - fact: "bcm2711#addressing-model"             # a fact; its claim is the premise
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

| Form | Resolves to | Where allowed |
| --- | --- | --- |
| `<fact id>` | a fact in the same merged spec (base and every overlay) | premises, `relates`, records |
| `<spec id>#<fact id>` | a fact in another spec, or in this spec across files | the same; required when the target lives in another file |
| `<assumption id>` | an entry of the same file's `assumptions` | `assumes`, premises |

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
  series: []                                # unchanged; never cited
  tools: []                                 # unchanged; declarative, `via:` a skill
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
  its `commit`.
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
  `license`, `accepts`) and gains `format: 2` and `fact_prefix` (required when the root holds
  an overlay; D1). The three repositories would declare `fact_prefix: perm` and `gpl`; the
  documents-only root holds base specs and needs none. Two roots read together with the same
  prefix are an error.
- **Discovery.** The same four pointer sources; never a tree walk. Every `*.spec.yaml` below a
  root is a spec. No symbolic links inside a root.
- **Merge order.** By layer (`public` < `ip-vendor` < `soc-vendor` < `product` < `local`), then
  pointer order; the spec repositories in the order docs, permissive, gpl. Composition first
  (`parts`, then `instances[].ip`), then overlays.
- **Merging.** An overlay's `facts` are appended to the target's facts, each keeping its
  `origin` (root name and layer) in the merged view; the renderer groups them under the target's
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

## Verification records

### File and naming

`<root>/resources/<name>.verify.yaml`, where `<name>` is the spec file's name without
`.spec.yaml`; one record per spec file, overlays included; two spec files whose records would
collide are an error, as today. The reader never loads a record body; `spec.py status` prints the
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
  gpl.gic-node:
    basis: <64 hex>                 # the fact's basis hash when this verdict was reached
    verdict: PASS                   # PASS | FAIL | UNVERIFIABLE | GAP | ADJUDICATE
    date: 2026-10-08
    verifier: "<agent, model, harness>"
    note: "what was compared against what"
    contrary_evidence: none-found   # none-found | found | not-checked
    citation_precision: exact       # exact | imprecise
    readers: []                     # a second reader's {verifier, verdict, note}, when it ran
    carried_from: {...}             # present when the verdict was carried forward, not re-read
```

Rules (all checked by `spec.py check`):

- **Keyed by fact id.** A verdict key is a fact id, or `<fact id>.<sub-id>` for a register field
  or sequence step that carries its own support. Keys survive every edit that keeps the id, and
  a mapping cannot hold a key twice (the loader rejects duplicates). A key that names no fact is
  an error.
- **`summary` has all five keys**, `adjudicate` included, and equals the counts of `verdict`
  values. It stays stored so a reader can be told the status without loading the body.
- **`FAIL`** carries `correction` (the proposed fix); **`ADJUDICATE`** carries `readings` (each
  reader's verdict and reasoning) and, once settled, `adjudication: {decision, by, date, rule}`,
  after which the verdict becomes `PASS` or `FAIL` and the history stays in `adjudication`.
- **Two readers.** A fact marked `critical` needs a second reader in `readers` with its own
  verdict (D14). This answers RG1's "add a record field showing whether the second verifier ran".
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
                      + "\n" + canonical(the resource entries the fact cites, identity fields only)
                      + "\n" + canonical(the assumptions it names)
                      + "\n" + sorted "<ref> <basis(ref)>" lines for every fact it references )
```

- *Canonical* is JSON with sorted keys, no insignificant whitespace, UTF-8, strings in Unicode
  NFC. The data holds only strings, integers, booleans, null, lists and mappings (no floats), so
  this is deterministic without a canonicalization library.
- *Identity fields* are the ones a verdict depends on: for a repos entry `url`, `commit`,
  `license`, and the listed file's entry; for a document `url`, `revision`, `sha256`, `pages`,
  `page_numbering`. Bookkeeping (`verified`, `fetch`, `fetch_via`, `note`) does not stale a
  verdict.
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

What the checker does: a current `FAIL` is an error. Stale and unverified facts are warnings, and
errors under `--require-verified` (the spec repositories' CI). A stale verdict caused only by a
fact in another root changing (a cross-root reference) is reported as such, so the repository
whose CI fails can see the cause is upstream (see [Risks](#risks)).

Evaluation against the alternatives (the decision is D2):

| Option | Delta verification | Format-only edits | Cross-spec premises | Cost |
| --- | --- | --- | --- | --- |
| Per-fact basis hashes (recommended) | mechanical: the stale set is computed | no staleness | stale exactly when the premise fact changes | the canonicalization is a contract; changing it stales everything once |
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
| Patterns: ids, prefixed overlay ids, commits, sha256, `https://` URLs, hex values, dates | yes | | |
| Unique fact ids within a file | | yes (`uniqueItems` compares whole items, not a key) | |
| Fact ids unique across the merged spec; overlay prefix matches the root's | | yes | |
| Every `repo`, `doc`, `assumption` name resolves in the file's `resources` | | yes | |
| Citation `class` matches the document's `class`; numeric pages within `pages` | | yes | |
| Fact references resolve; no cycles; layer order respected | | yes | |
| License gate (SPDX expression logic), direct and transitive | | yes | |
| `parts`, `overlays`, `variant_of`, `instances[].ip` resolve; stubs resolve | | yes | |
| Public-layer privacy (`access: internal`, `via:` to a private skill) | | yes | |
| Template placeholders left in | | yes | |
| Records: shape (schema), key per fact, summary counts, basis freshness, two readers for `critical` | shape | yes | |
| Rendered views current | | yes (`render --check`) | |
| Anchors resolve at the pin: path, line range, symbol near the range | | | yes |
| Cited files' SPDX lines fit the entry's license | | | yes |
| Document files hash to `sha256` (`--docs-dir`) | | | yes |
| Values in a claim appear in the cited lines (warning); `inventory` against headers | | | yes |

Everything in the schema column is declarative and can be read by people and other tools; the
checker column is a small amount of Python over already-parsed data. Neither ever reads prose.

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
    "factId": {"type": "string", "pattern": "^([a-z0-9]+\\.)?[a-z0-9][a-z0-9-]*$"},
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
- **Retired**: markdown-it-py and `mdtokens.py`, once v1 is gone (D11). The checker then needs
  PyYAML and the validator, pinned in CI with hashes; without them it exits 3, never falling back
  to a second parser (the RG-T1 lesson: count the parsers).

## Rendering

`spec.py render <root>... [--spec <id>] [--merged] [--with-status]` writes Markdown. The rendered
view:

- opens with a generated-file banner naming the YAML file, the canonical-form version and the
  `driver-lab` commit that rendered it, and saying it must not be edited;
- prints the identity block (kind, id, name, triggers) and the resources as tables (documents
  with class, revision and hash; repos with commit and license);
- prints `orientation` under its heading, labeled "Context (not facts)";
- prints each section's facts in order as `**Title.** claim`, then the scope, then one line per
  support entry with its class and a rendered citation, then the TODO, then the fact reference
  as a code span (`bcm2711#gic-node`) so a reader can cite it;
- prints inference premises as a nested list, each naming the fact it references by its fact
  reference;
- in a merged view, prints overlay facts under "Overlay: <layer> (<root>)" sub-headings;
- with `--with-status`, adds each fact's verdict, date and whether it was carried forward;
- for peripheral specs and reviews, generates the provenance notice, the canonical-references
  table, the register tables, the verify-on-hardware list and the open-questions list.

Every string from the YAML is escaped for Markdown (backslash-escaping of Markdown syntax
characters; code spans re-emitted with a fence long enough for their content), so a claim that
contains `[databook]` renders as that literal text and cannot pass for a citation. Because no
tool parses the rendered view, the profile restrictions of today's format (no HTML, no block
quotes, no character references) stop being needed for safety; the renderer simply never emits
them.

Where rendered files live is D5. The later viewer reads the YAML (and the records), not the
rendered Markdown: the data already carries fact ids, classes, sources and verdicts to index.

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
| `skills/board-expert/specs/board-specs.yaml` | the shipped root (no specs) | `format: 2` |

### Converting a spec

1. **Mechanical part** (`spec.py migrate <v1 file>`, using today's one Markdown parse for the
   last time): identity and resources; one fact per bullet, its `id` the slug of the bold
   lead-in (unique in the file, with the root's prefix for overlays), its `section`, its `claim`
   (the bullet text before the tag clause, byte for byte), its `todo` text; every `[src:]` anchor
   into `anchors`; every `[DT]` parenthetical of the form "(<file> lines A-B, <repo>)" into `DT`
   anchors; hashes moved out of `note` into `sha256`; `fetch_via` URLs into `retrieval`.
2. **Citation part** (a fresh agent with the v1 and the draft v2 file, no sources): turn each
   free-text document parenthetical into a `doc` name and structured locators, and each inference
   parenthetical into `premises` and `derivation`, keeping the premise wording.
3. **Split mixed bullets** (D3): a bullet whose tag clause mixes `[inference]` with read classes
   becomes a read fact and an inference fact that references it. In bcm2711: docs Quick-facts/2
   (two facts), permissive Gotchas/3 (three: the `src`+`databook` fact about the two builds' bases,
   the `doc` fact about the documentation, and the inference), GPL Quick-facts/1 (two). Three
   bullets become seven facts.
4. **Conversion-fidelity check** (D10): a fresh agent compares each v1 bullet with its v2 record
   and the rendered output: claim text identical, every v1 citation present with the same target
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

Recommended: driver-lab ships format 2 alongside a read-only v1 checker; each spec repository
migrates in one pull request that bumps its driver-lab pin, converts the spec and the record, and
switches `scripts/checks.sh`; when all three are on format 2, driver-lab removes the v1 code,
`mdtokens.py` and the markdown-it-py dependency in one change. During the window, v1 and v2 roots
can be read together for overlays only if the reader supports both; the recommendation is to
migrate the three repositories in sequence docs, permissive, gpl within one unit so no mixed
composition has to be supported.

## Effects on the skills and the spec repositories

| Component | Today | Format 2 |
| --- | --- | --- |
| `SPEC-FORMAT.md` | the contract, 780 lines, much of it the Markdown profile and tag-clause parsing rules | a shorter contract pointing at the schema for shapes; classes, references, roots, records, rendering. The profile and tag-clause sections are deleted (D7 decides where it lives) |
| `board-expert` (reader) | reads `*.spec.md` and record front matter | reads `spec.py render --merged --with-status` output for the composition (smaller than raw YAML, and verdicts included), and the YAML when it needs a citation's exact fields; reports `bcm2711#fact` references in answers; "Suggested spec change" names the fact id or proposes a new record |
| `board-spec-scaffold` | Markdown templates, tag-clause rules | YAML templates per kind; the subagent that researches facts returns fact records directly; `spec.py check` instead of `spec_check.py`; RG1's checklist items (console routing, entry contract, memory reservations, interrupt table) stay prose guidance |
| `hardware-investigator` | Markdown facts file, `Source pin:` lines, `anchor_check.py --root` | `kind: facts` YAML; `license_gate.py` reads the same SPDX logic; per-file license confirmation is a field (`license_from`) checked by `resolve` |
| `peripheral-spec` | anchor grammar, pins, block anchors, labels in prose; `anchor_check.py`, `inventory_check.py` | the grammar section is replaced by the record types above; `requirement` field; `spec.py check/resolve/show/drift/inventory`; templates for the spec subagent and verifier rewritten around records |
| `reference-driver-review` | `[impl:]`/`[ref:]` aliases, Markdown findings | `role: impl`/`ref` repos, `findings` with `data.finding`, `assessment` in place of the finding verdict |
| `spec-verifier` | keys by section and ordinal or anchor text; whole-file hash; `summary` without `adjudicate` in board specs | keys by fact id; basis hashes; `readers`, `contrary_evidence`, `citation_precision`, `carried_from`; delta verification from `spec.py status --stale`; the verifier writes YAML and `spec.py check` validates it |
| `campaign-review` | `claims.yaml` `cites` spec section ids of the frozen e1000 spec | unchanged for the frozen campaign; a new campaign cites `spec#fact`, and its sweep can use fact basis hashes as the basis identities of verdicts (DESIGN, continuous review C1 and C2) |
| Spec repository `scripts/checks.sh` | `specs` (spec_check), `anchors` (anchor_check, fetch, resolve), `self-test` | `check` (`spec.py check specs --context-root ... --require-license --require-verified`), `resolve` (fetch pins, resolve `src` and `DT` anchors, per-file licenses), `render` (`rendered/` current, if D5 commits it), `self-test` (the v2 fixtures; same fit/misfit pairs) |
| Spec repository CI dependencies | markdown-it-py 4.2.0 in a venv | PyYAML and the chosen validator, pinned |
| Spec repository `AGENTS.md`/README citation rules | describe peripheral `[doc:]` anchors and board tags | describe records; the README links each spec's rendered view |
| driver-lab `AGENTS.md` check list and CI | `uv run --with markdown-it-py==4.2.0 ...` | `uv run --with pyyaml --with <validator> ...` |
| Consumers outside driver-lab | `bringup-kit` roots point at the docs and permissive repositories and read specs through `board-expert`; `fuchsia-skills` hands off by skill name | no skill is renamed; `board-expert` reads both formats only during the transition; bringup-kit test markers without `format:` are read as v1 until it migrates |

## Worked example

A slice of the bcm2711 specs as the migration would produce it, with every claim text copied
unchanged from the published files except where a split is noted. Facts and resources the slice
does not show (for example `perm.patch-words`) are in the full migrated files. Hashes in the
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
aliases: []
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
      text: compare the stub image the firmware loads with this build (see perm.which-build-ships)
facts:
  - id: perm.which-build-ships
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
          - fact: perm.patch-words
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

  - id: perm.generic-timer-frequency
    section: quick-facts
    title: Generic timer frequency
    claim: The BCM2711 build writes 54000000 (54 MHz) to `CNTFRQ_EL0` and 0 to `CNTVOFF_EL2`.
    support:
      - class: src
        anchors:
          - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [53, 57], symbol: OSC_FREQ}
          - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [110, 112], symbol: OSC_FREQ}
          - {repo: rpi-tools, path: armstubs/armstub8.S, lines: [114, 115], symbol: CNTVOFF_EL2}

  - id: perm.scr-el3-bits
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

  - id: perm.scr-el3-value
    section: quick-facts
    title: SCR_EL3 value
    claim: The value the stub writes is `0x5B1`.
    support:
      - class: inference
        premises:
          - fact: perm.scr-el3-bits
            uses: the six bits its anchors show, which the source names by bit position and never sums
        derivation: 0x400 + 0x100 + 0x80 + 0x20 + 0x10 + 0x1 = 0x5B1
    todo:
      check: hardware
      text: the register is EL3-only, so read it with a debugger that can access EL3 state.

  - id: perm.smpen-at-el3
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
  - id: gpl.address-translation-in-the-tree
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
  - id: gpl.tree-describes-low-peripheral-mode
    section: quick-facts
    title: The tree describes Low Peripheral mode
    claim: The tree describes Low Peripheral mode.
    support:
      - class: inference
        premises:
          - fact: gpl.address-translation-in-the-tree
            uses: the tree's physical targets
          - fact: "bcm2711#addressing-model"
            uses: >-
              Low Peripheral mode places Main peripherals at `0x0_FC00_0000`–`0x0_FF7F_FFFF` and
              ARM Local at `0x0_FF80_0000`
        derivation: >-
          the targets fall in those ranges, not in the full-map ranges at `0x4_7C00_0000` and
          `0x4_C000_0000`
    todo:
      check: hardware
      text: compare the live tree on a board booted with arm_peri_high=1.

  - id: gpl.gic-node
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

  - id: gpl.reserved-stub-page
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

The cross-root inference is gated transitively: its premise `bcm2711#addressing-model` lives in
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
  gpl.gic-node:
    basis: <64 hex>
    verdict: PASS
    date: 2026-10-08
    verifier: "Claude Opus 5.5, Claude Code subagent"
    note: >-
      lines 56-66: `arm,gic-400`, three interrupt cells, reg 0x40041000/0x1000,
      0x40042000/0x2000, 0x40044000, 0x40046000; translated through the ARM Local range to
      0xff841000 and 0xff842000; maintenance interrupt GIC_PPI 9 with GIC_CPU_MASK_SIMPLE(4) and
      IRQ_TYPE_LEVEL_HIGH (PPI 9 is ID 25).
    readers: []
    carried_from:
      repo: hardware-specs-gpl
      commit: cd911120663da72f4101161eef5a22dc13d0cc86
      path: specs/resources/bcm2711.verify.md
      key: 'Quick-facts/2 "GIC node"'
      format: 1
  gpl.reserved-stub-page:
    basis: <64 hex>
    verdict: PASS
    date: 2026-10-08
    verifier: "Claude Opus 5.5, Claude Code subagent"
    note: >-
      bcm283x.dtsi line 11 reserves 0x0 for 0x1000; the comment on lines 8-10 is attributed as a
      comment and matches (firmware startup stubs, secondary CPUs spinning). bcm2711.dtsi
      includes bcm283x.dtsi (line 2).
    readers: []
    carried_from:
      repo: hardware-specs-gpl
      commit: cd911120663da72f4101161eef5a22dc13d0cc86
      path: specs/resources/bcm2711.verify.md
      key: 'Quick-facts/6 "Reserved stub page"'
      format: 1
```

The carried verdicts leave out `contrary_evidence` and `citation_precision`: the format 1 record
did not state them per bullet, and a carried verdict records only what the earlier record said.
What `spec.py status` reports for this slice: `gpl.gic-node` and `gpl.reserved-stub-page`
current (carried); `gpl.address-translation-in-the-tree` and
`gpl.tree-describes-low-peripheral-mode` unverified, because the split changed the first claim's
text and created the second. `gpl.gic-node` is `critical` and has one reader, so under
`--require-verified` the check also asks for a second reader (the v1 record ran its second reader
separately and recorded no verdict of its own, so there is nothing to carry). Delta verification
covers exactly those items; nothing else is re-read. If the docs spec later edits
`addressing-model`, only `gpl.tree-describes-low-peripheral-mode` goes stale here.

### Rendered view (merged, with status; slice)

~~~markdown
<!-- Generated by spec.py render from hardware-specs-docs/specs/bcm2711.spec.yaml and its
     overlays (canonical form fact-v1, driver-lab <commit>). Do not edit. -->

# Broadcom BCM2711 (Raspberry Pi 4, Raspberry Pi 400, Compute Module 4 and 4S)

`bcm2711` · soc · triggers: bcm2711, raspberry pi 4 soc, pi 4 soc, pi 400 soc, cm4 soc

## Context (not facts)

The BCM2711 is the SoC of the Raspberry Pi 4 Model B, ...

## Quick-facts

- **Addressing model.** The chip has a full 35-bit address map, ... is `0x0_FE20_1000` in Low
  Peripheral mode.
  - databook: BCM2711 ARM Peripherals (release 4), §1.2.1–1.2.4, pp. 4–6; §6.5.1–6.5.2, p. 92;
    §11.5, pp. 146–147
  - `bcm2711#addressing-model` · bring-up critical · PASS 2026-10-08 (carried from format 1)
- **High peripheral mode is likely the full map.** High peripheral mode is likely the one in
  which the Arm cores use the full-map addresses.
  - inference, from:
    - the documentation names high peripheral mode as the alternative to the default (doc:
      Raspberry Pi documentation, legacy config.txt boot options, "arm_peri_high")
    - the datasheet gives the Arm cores only two views, ... (databook: BCM2711 ARM Peripherals,
      §1.2.1, p. 4; §1.2.3, p. 6)
  - derivation: if high peripheral mode is not Low Peripheral mode, it is the full map; ...
  - TODO (verify on hardware): with arm_peri_high=1, read the GIC distributor's ID registers at
    the full-map address.
  - `bcm2711#high-peripheral-mode-is-full-map` · unverified

### Overlay: public (hardware-specs-gpl)

- **The tree describes Low Peripheral mode.** The tree describes Low Peripheral mode.
  - inference, from:
    - `bcm2711#gpl.address-translation-in-the-tree` (Address translation in the tree): the
      tree's physical targets
    - `bcm2711#addressing-model` (Addressing model): Low Peripheral mode places Main peripherals
      at `0x0_FC00_0000`–`0x0_FF7F_FFFF` and ARM Local at `0x0_FF80_0000`
  - derivation: the targets fall in those ranges, not in the full-map ranges ...
  - TODO (verify on hardware): compare the live tree on a board booted with arm_peri_high=1.
  - `bcm2711#gpl.tree-describes-low-peripheral-mode` · unverified
- **GIC node.** `arm,gic-400`, `#interrupt-cells = <3>`, ...
  - DT: linux@8d3ae59 (GPL-2.0-only) arch/arm/boot/dts/broadcom/bcm2711.dtsi lines 56–66
  - `bcm2711#gpl.gic-node` · bring-up critical · PASS 2026-10-08 (carried from format 1; second
    reader missing)
~~~

## Open decisions

Each is a choice for the user; the recommended option is first.

**D1. Fact ids in overlays.**
1. *(Recommended)* Each root that holds overlays declares `fact_prefix` in its marker
   (`perm`, `gpl`); overlay fact ids must start with it (`gpl.gic-node`). Collisions across
   repositories are impossible by construction, and a reference shows which root it points into.
   Cost: one more marker field; ids are a little longer.
2. Free ids, unique across the merged spec, checked when the roots are read together. Shorter
   ids; but a docs commit can later add an id that collides with an existing GPL overlay fact and
   break the GPL repository's CI after the fact.
3. Free ids, with references qualified by root (`bcm2711@hardware-specs-gpl#gic-node`). No
   collisions; every reference is long, and the root name becomes part of every citation.

**D2. Freshness of verdicts.**
1. *(Recommended)* Per-fact basis hashes decide staleness; `spec_sha256` is kept for information.
   Delta verification becomes mechanical and format-only edits stale nothing. Cost: the
   canonical form is a contract (changing it stales every verdict once); a verdict that relied on
   something the fact does not cite is not staled by it.
2. Whole-file `spec_sha256`, as today. Simple; every edit stales every verdict, and delta records
   stay manual.
3. Both: stale when either changes. Most conservative; in practice the file hash dominates and
   the delta is lost.

**D3. Facts that mix classes.**
1. *(Recommended)* Read classes may support one claim jointly (as v1 tag clauses do); an
   `inference` stands alone in its fact; a sentence that is concluded rather than read becomes its
   own inference fact referencing the read fact. Migration splits three bcm2711 bullets into
   seven facts, whose verdicts do not carry.
2. Exactly one class per fact. Simplest to verify and render; splits most multi-citation
   bullets (the interrupt-controller bullet alone cites three classes), so far fewer verdicts carry.
3. Allow mixing, with a `covers:` text on each support entry saying which part of the claim it
   supports. Nothing splits; `covers:` is prose again, which the format exists to avoid.

**D4. Markup in claims and prose.**
1. *(Recommended)* Plain text plus `` `code spans` `` everywhere; the renderer escapes everything
   else. A claim can never render as a citation or as structure.
2. Plain text in claims; CommonMark passed through in `orientation` and notes. Richer context
   prose (lists, links); a prose paragraph can be made to look like a cited fact in the rendered
   view.
3. CommonMark everywhere, rendered as written. Most familiar to authors; reopens the
   render-versus-meaning gap for human readers.

**D5. Where the rendered Markdown lives.**
1. *(Recommended)* Committed under `rendered/` (outside the spec root) in each spec repository,
   with CI failing when it is not current. People browsing the repository on GitHub see readable
   specs; pull requests show the rendered diff beside the YAML diff.
2. Built by CI and published (Pages or an artifact), nothing committed. No duplicate files; a
   reader on GitHub sees only YAML until the viewer exists.
3. On demand only (`spec.py render`). Least machinery; the published repositories have no
   human-readable view.

**D6. Numbers and scalar types in YAML.**
1. *(Recommended)* The loader resolves only `true`, `false`, `null` and decimal integers;
   addresses, offsets and masks are hex strings with schema patterns; dates are strings. No
   implicit-typing surprises; hex keeps its spelling (`0x4_7C00_0000`). Cost: the checker parses
   hex strings where it needs arithmetic.
2. YAML integers, hex allowed (`reg: 0x107d001000`, as today's `instances:`). Arithmetic is free;
   the spelling is lost, and loaders disagree (YAML 1.1 and 1.2 read `0o`, `012` and underscores
   differently).
3. Every scalar a string (PyYAML's base loader); booleans become `"true"`/`"false"` enums. Fully
   predictable; awkward for anyone reading the schema or using another tool.

**D7. Where the format lives.**
1. *(Recommended)* A new reference skill, `skills/spec-format/` (not user-invocable), holding the
   contract document, the schemas, the loader, `spec.py` and the renderer; `board-expert`,
   `peripheral-spec`, `spec-verifier` and the others point at it, and
   `board-expert/SPEC-FORMAT.md` becomes a pointer. One home for rules every spec skill shares.
   Adds a skill name (none is renamed).
2. Keep everything under `board-expert`, as today. No new skill; the peripheral and review
   skills keep depending on a board skill's directory.
3. A separate repository for the format and tools, pinned by driver-lab and the spec
   repositories. Clean versioning; one more repository and pin to keep in step.

**D8. JSON Schema validator** (each to be scored with `dep-quality` before pinning).
1. *(Recommended, subject to the score)* `jsonschema` (python-jsonschema): the most used Python
   implementation, full 2020-12 support; brings `rpds-py`, a compiled dependency.
2. `jschon`: pure Python, 2020-12; smaller community.
3. A restricted validator written here for the schema subset used. No dependency; a second
   implementation of a standard, which is the kind of parser this design is trying to stop
   writing.

**D9. YAML library and in-place rewriting.**
1. *(Recommended)* PyYAML for loading; `drift --rewrite` replaces scalar spans located by
   PyYAML's node marks, keeping comments and layout. One library, already used here.
2. ruamel.yaml, which round-trips comments and layout. Rewriting is simpler; a second YAML
   library, and its YAML 1.2 defaults differ from the loader's rules.
3. PyYAML, and rewrite by dumping the whole file. Simplest; comments (including the SPDX header)
   and layout are lost on every rewrite.

**D10. Carrying v1 verdicts.**
1. *(Recommended)* Carry a verdict when the claim text is byte-identical and a fresh agent's
   conversion-fidelity check passes the fact's citations; re-verify split facts and anything
   flagged. At most 61 of the 65 v1 verdicts carry; cost is one fidelity pass per spec.
2. Re-verify all 65 facts fresh, with second readers for the critical ones. Cleanest record; the
   cost of RG1's verification rounds again, for facts whose text did not change.
3. Carry every verdict whose claim text is unchanged, with no fidelity check. Cheapest; a
   conversion error in a citation would carry a PASS it never earned.

**D11. Transition.**
1. *(Recommended)* driver-lab ships format 2 plus a read-only v1 checker; the three spec
   repositories migrate in sequence (docs, permissive, gpl) in one unit; then v1 code and
   markdown-it-py are removed in one change.
2. Hard cutover: one coordinated change across driver-lab and the three repositories. No
   dual-format code; four pull requests must land together.
3. Support both formats indefinitely. No deadline; two parsers forever, the condition RG-T1
   showed leaks.

**D12. Licenses per cited file.**
1. *(Recommended)* One license per repos entry; a closed `files` list naming how each file's
   license was confirmed; `resolve` checks each cited file's SPDX line against the entry. A
   repository with files under two licenses gets two entries, as the GPL overlay does today.
2. Entry-level license only, as today. Less to write; RG1's unlicensed-Makefile case is caught
   only by the verifier.
3. A license on every file entry, gated per file. Most precise; every citation's license lives on
   a different line from its entry, and the gate becomes per file.

**D13. References across roots.**
1. *(Recommended)* Transitive gate: everything a referenced fact cites, followed through its own
   references, must pass the citing root's accepts list. Docs facts are referenceable from
   everywhere; a docs fact can never rest on a GPL fact.
2. Direction by merge order only (later roots may reference earlier ones). Simple; equivalent
   for the three public repositories, wrong for a vendor root whose accepts list differs.
3. No references across roots; restate a premise with its own citations. Each root stands alone;
   premises are duplicated and drift apart.

**D14. Second readers.**
1. *(Recommended)* `critical: true` on facts; the checker requires a second reader's verdict in
   the record for each critical fact under `--require-verified`. Answers RG1's "say whether the
   second verifier ran".
2. Keep it a procedural rule in `spec-verifier` only. No schema change; nothing shows whether it
   happened.
3. Two readers for every fact. Strongest; doubles verification cost (RG1 found the second
   reader's value concentrated in disagreements on a few facts).

**D15. The extension class `source-observed`.**
1. *(Recommended)* Keep the name in the class enum with v1's rule (needs a TODO); its citation
   fields come from a schema fragment the extension supplies, named in the root marker. The
   extension keeps working without driver-lab defining its content.
2. Drop it from format 2; the extension defines its own spec kind. A cleaner core; the extension
   must change before it can use format 2.
3. A generic `x-<name>` class mechanism for any extension. Most general; more machinery than one
   known extension needs.

**D16. Verdict granularity for registers and sequences.**
1. *(Recommended)* One verdict per register or sequence fact; a field or step that carries its
   own support gets its own sub-key (`reg-ctrl.en`, `seq-init.s2`).
2. Every field and step is its own fact. Uniform; register maps become hundreds of records.
3. One verdict per table (all registers). Fewest verdicts; one wrong bit fails a whole map.

**D17. File names.**
1. *(Recommended)* Every spec is `<name>.spec.yaml`; `kind` says what it is. One glob, one rule.
2. Keep the split (`<id>.spec.yaml` board kinds, `<device>-spec.yaml` peripheral). Familiar;
   the split existed only because the board checker globbed `*.spec.md`.

**D18. Conflict entries.**
1. *(Recommended)* Include the `conflicts` field now. The DESIGN.md proposal gets a home, and
   RG1's documentation-versus-source contradiction (high peripheral mode) is recorded as one.
2. Defer it to a later revision of the format. Less to build now; contradictions stay in claim
   prose and `note`.

## Risks

| Risk | Consequence | Mitigation |
| --- | --- | --- |
| Free text still exists (claims, premises' `states`, notes) | a misleading string can still mislead a person | no tool reads it; the renderer escapes it; a lint warns on tag-like tokens (`[databook]`, `[src:`) in text |
| YAML authoring errors by agents (indentation, quoting long claims) | failed checks, retries | block scalars for long text; every error carries a line and column; templates per kind; `spec.py check` run before any review |
| The canonical form changes | every verdict stale at once | versioned (`canonical: fact-v1`); a change ships with a re-hash command that re-keys verdicts only when the old and new forms agree on the data |
| A verdict depends on something its fact does not cite | not staled when that changes | coverage review separate; `spec_sha256` kept; the verifier is told to record any extra dependency as a `relates` link |
| Cross-root staleness | a docs edit fails the GPL repository's CI under `--require-verified` | the status line names the upstream fact; an option (in the unit plan) to report cross-root staleness as a warning in CI and an error only at release |
| Conversion error carried as PASS | a wrong citation keeps a verdict | fidelity check (D10); `resolve` runs on every anchor during migration |
| New dependency risk (validator, compiled `rpds-py`) | supply-chain and build breakage in CI | `dep-quality` score before pinning; hash-pinned CI requirements; exit 3 without them |
| The schema grows its own equivalent spellings (optional fields that mean the same) | the leak returns at the data level | closed records (`unevaluatedProperties: false`); one field per meaning; review asks "is there a second way to say this?" for every schema change |
| Consumers outside driver-lab read `*.spec.md` | they break at the cutover | `board-expert` is the only reader of specs; bringup-kit reads through it; transition window (D11) |
| Viewer demand pulls design forward | scope creep | the viewer reads the same YAML; nothing here waits for it |

## Implementation outline

Session-sized units; the plan with acceptance criteria comes after this design is approved. Each
tooling unit is reviewed by an executing reviewer (break cases including degenerate inputs,
mutation checks) and a diff reader, the pairing RG-T1 showed finds different holes.

1. **SF2-1 Loader and schema.** `dep-quality` on the validator candidates and PyYAML, then pin;
   `load_strict` with every pitfall in the loader table as a failing fixture; `spec.schema.json`,
   `verify.schema.json`, `root.schema.json`; schema fixtures (one good file per kind, one bad file
   per rule).
2. **SF2-2 Checker.** `spec.py check`: id uniqueness and prefixes, name resolution, references
   and cycles, layer order, license gate direct and transitive, records (keys, summary, basis
   hashes, two readers), privacy, placeholders; the license-gate fixture matrix and the
   board-expert fixtures rewritten in format 2, with `expected.json` carried over.
3. **SF2-3 Resolve and drift.** `spec.py resolve` (fetch pins, `src` and `DT` anchors, per-file
   licenses, document hashes), `show`, `drift --rewrite` on YAML, `inventory` on register records.
4. **SF2-4 Render and status.** `spec.py render` (single and merged, with status), the escaping
   rules with adversarial fixtures, `status --stale`; a decision on D5 applied.
5. **SF2-5 Skills.** The contract document (D7), `spec-verifier`, `board-expert`,
   `board-spec-scaffold` templates, `hardware-investigator`, `peripheral-spec` and its subagent
   and verifier templates, `reference-driver-review`; glossary; grep every skill for v1 rules (the
   RG-T1 T7 lesson).
6. **SF2-6 Migration of bcm2711.** `spec.py migrate`, citation pass, splits, fidelity check,
   carried records, delta verification of the rest; the three spec repositories' pull requests
   (docs, permissive, gpl) with their `checks.sh` and CI on format 2.
7. **SF2-7 Retire format 1.** Remove the v1 checker, `mdtokens.py`, `anchor_check.py`'s Markdown
   mode and markdown-it-py; update driver-lab's `AGENTS.md` check list and CI.

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
