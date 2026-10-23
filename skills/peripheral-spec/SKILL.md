---
name: peripheral-spec
description: >-
  Produce a YAML peripheral implementation spec from driver source whose license fits the
  target spec repository. Every fact carries structured support at an immutable commit or a
  named document locator. Use for documenting, specifying or porting a peripheral from citable
  source or public datasheets; not for NDA source. Uses hwspecs validate, check, resolve, show,
  drift and inventory, with independent verification through spec-verifier.
---

<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# Peripheral driver spec

Produce one `kind: peripheral` implementation spec per peripheral: hardware programming
requirements plus target operating-system integration. The YAML records are the source of
truth; the register tables and reading views are generated. A reader must be able to trace
any actionable claim to evidence at the recorded revision.

## Terms

- **Fact record**: a stable `id`, section, claim or typed payload, and structured `support`.
- **Payload**: a fact's `data` fields describing registers, ordered steps or byte layouts.
- **Root**: a directory with a `board-specs.yaml` marker declaring format and license policy.
- **Anchor / locator**: a source path and lines or search scope / a place in a named document.
- **Pin / role**: a repository's full commit and file license / its use as `source` or `target`.
- **Requirement**: why behavior is needed, distinct from a verification verdict.
- **OS framework**: the OS's driver interface for a device class; MTU, frame versus payload and
  head or tail room are in the glossary.

See the [glossary](../../docs/GLOSSARY.md) and [spec-format contract](../spec-format/SKILL.md).
Read the `peripheral` branch and payload definitions of the
[spec schema](../spec-format/schema/spec.schema.json); those define the accepted shapes.

## Where the spec goes: which repository's license fits?

A peripheral spec restates the sources it cites. **Placement rule:** publish it in the most
restrictive repository among its cited sources, including dependencies reached through fact
references. It may cite less restrictive repositories, never more restrictive ones.

| Repository | Spec license | Citable evidence |
| --- | --- | --- |
| `hardware-specs-docs` | CC-BY-4.0 | Public documents only; `accepts: []` |
| `hardware-specs-permissive` | Apache-2.0, plus required source notices | Public documents and accepted BSD, ISC, 0BSD, MIT, Apache or permissively dual-licensed source |
| `hardware-specs-gpl` | GPL-2.0-only | The above plus accepted GPL-2.0-only or GPL-2.0-or-later source |

Generic facts of a public standard (a register interface, capability structures, protocol
behavior) go in that standard's documents-only repository where one exists, such as
`hardware-specs-usb` for the USB family (CC-BY-4.0, `accepts: []`), and a peripheral spec
composes them rather than restating them
([LICENSE-SPLIT.md](../../docs/LICENSE-SPLIT.md#standards-and-architecture-specs-154)).

The spec root marker requires `format: 2`, `layer`, `name`, `license` and `accepts`.
`layer` is its merge position (`public`, `ip-vendor`, `soc-vendor`, `product` or `local`);
`name` is the stable root identifier used in cross-root fact references.
Read the actual destination marker's `license` and `accepts`; fixture roots are not a promise
that published roots accept the same identifiers. Each accepted identifier is an SPDX license
name. `A OR B` passes if either alternative is accepted; `A AND B` requires both. GPL-3.0,
NDA material or an unaccepted vendor license fits none of these roots: do not publish a spec
citing it. Do not relabel a source to pass the gate.

Confirm the license of **each cited file at the commit read**: its SPDX line, else its notice
or the applicable license file. A tree with files under different licenses needs separate
`resources.repos` entries with distinct names, one license per entry. Each entry's closed
`files` list names every cited path and records `license_from: spdx-line`, `notice` or
`license-file`. `resolve` checks SPDX lines; notice and license-file confirmation still need
human reading. Retain required attribution in `notices` and the repository's NOTICE file.
Also record each cited file's source copyright `attribution` from `resolve`'s scan (the JSON
anchor item's `attribution`, already in the schema's shape): copy it. For `ambiguous`, read the
notice, record the names you read in addition to any the scan lists, and add the continuation
line to `evidence`. Absent means
not recorded. It is the source's declared attribution, not authorship.
Both source and target roles are gated. A device-tree citation has the tree's license too.
Run `check --require-license` before publication, including unused resource entries.

A reader choosing docs or permissive specs still follows those sources' terms when writing
code. A GPL spec deliberately leads into GPL source. Quote only a few lines when the exact
expression matters, and cite them; a spec must not become another copy of the driver.
For findings comparing two implementations, use `reference-driver-review`.

## Documents first, structured support always

Identify the silicon block, vendor, revision and instance. Find an authoritative public
manual, or name the public sibling/proxy and its applicability limits. The document can say
why hardware requires an operation; source alone says what that driver defines or does.
Keep code observations and hardware conclusions separate when the latter are inferred.

Every document goes in `resources.documents` with name, class, title, canonical HTTPS `url`,
SHA-256 when available and precise locators in support. Use `databook`, `standard` or `doc`
as the contract defines, not interchangeable classes. Store usable fetch URLs in `retrieval`,
separate from the citation URL. For Arm manuals cite the developer documentation page and
record the documentation-service static PDF in retrieval. Record revision and page count.
A fact that states a document value carries the notes that govern it, wherever they appear
(table footnotes, exception rows, clauses for another actor), and cites them.
Public roots never cite confidential or NDA documents, even when copies are obtainable.

Every source citation uses `class: src` with `anchors: [{repo, path, lines, symbol}]`.
Paths are repository-relative; lines are inclusive and 1-based. Cite the actual definition,
performing statement or call site, not its enclosing function or guard. Negative/global
claims use `search` instead of lines/symbol; state the scope and repeatable search in words.
Every search scope must also be listed as a path in that repo entry's `files`, including a
directory scope spelled with its trailing slash (`dir/`).
The resolver checks scope existence, not the truth of an absence. Use `comment: true` for a
comment and attribute the claim to it. Never invent an anchor for unread lines.
Target integration uses the same `src` class, with a repo entry whose `role` is `target`.
If source and target are one tree, use a distinct target entry for target-section citations.
The peripheral checker enforces `role: target` only on facts in `section: target`; it does
not enforce a source/target role for citations in other sections.
There are no citation aliases or table-wide evidence: each fact/row carries its support.

## Record types and requirements

Start `<device>.spec.yaml` with SPDX comments matching the destination, `format: 2`,
`kind: peripheral`, `id`, `name`, `resources` and `facts`. Link the spec to the hardware it
belongs to: `describes: [<soc-or-board-id>]` names the soc, chip or board specs whose block
this is (the same or an earlier layer), or the SoC's instance row names this spec in
`peripheral`. When a soc, chip or board spec is in the same check, the checker warns on a
peripheral spec with neither, since a reader composing the board would never find it.

Repository entries have HTTPS URLs, full lowercase immutable `commit` values, file licenses
and `role: source` or `target`. Quote structured hex values in lowercase canonical form
(`"0x0"`, never `"0x00"` or `"0xA"`); omit unknown width, access or reset rather than guessing
them. No Markdown frontmatter or
body surrounds the YAML.

- **Register map**: `section: registers`, `data.register: {name, offset, width, access, reset}`
  (last three optional), and optional `data.fields`. Each field has `id`, `name`, inclusive
  `bits: [low, high]`, and `meaning`. Follow databook order, including untouched registers
  when documents cover them. The register's `claim` may be omitted; the view derives it.
  `access` takes IP-XACT values (`read-only`, `read-write`, ...; the short `ro`/`rw`/`w1c` still
  parse, with a warning). A field may add IP-XACT properties (`access`, `modifiedWriteValue`,
  `readAction`, `reserved`, `resets`, `enumeratedValues`, ...; the table is in
  [SPEC-FORMAT.md](../../docs/SPEC-FORMAT.md#register-fields-ip-xact-properties)), and a spec may
  hold the registries `resetTypes`, `fieldAccessPolicyDefinitions`, `enumerationDefinitions` and
  `registerFiles`; a `kind: facts` file may carry them too, and they are copied into the spec
  with the facts that name them. A document abbreviation such as RW1CS becomes one
  `fieldAccessPolicyDefinitions` entry, cited once. Sticky bits are `unaffectedBy`, HwInit is
  `initializedBy`, a write-enable lock is `lockedBy`.
  **Authoring rule**: a field, opcode or mask whose source gives a table of values or bit
  assignments gets `enumeratedValues` (or an `enumerationDefinitionRef`, or bit-level fields).
  When the table is left out on purpose, the field carries `todo: {check: document, text:
  "<what is omitted and where>"}`. Naming the table in `meaning` alone is a defect the verifier
  reports.
- **Sequences**: `section: sequences`, `data.sequence.steps` with stable ids and `action`,
  and optional `order` constraints `{before, after, requirement, support}`. Support every
  performing step precisely; record prerequisites, initialization, reset, power, error and
  teardown paths. Constraints describe required ordering separately from the driver's order.
  A step that is a register write, a set or clear of bits, a read, a poll, a delay or an
  interrupt wait takes `op` (`write`, `setBits`, `clearBits`, `read`, `poll`, `delay`,
  `waitInterrupt`) instead of `action`: `target` (`#reg-fact` or `#reg-fact.field` in the same
  file; an interrupts fact for `waitInterrupt`), `value` (canonical hex, or an enumerated
  value's name), `until`, and `timeout`, `interval` and `duration` as quantities (a UCUM
  `unit`, IEC 61360 levels `min`/`nom`/`typ`/`max`, decimal integers). Such a step has no
  `action`, because the renderer writes its English; explanations go in `note`. Other steps keep
  `action`. **Every wait, poll or handshake step states its bound or carries** `todo: {check:
  document, text: "<the source gives no bound>"}` (#105). A `poll` or `waitInterrupt` states it
  as a `timeout` quantity, with the document's tolerance as `min`/`max`, and the checker
  enforces the rule; an `action` step (a handshake no `op` expresses) cannot take `timeout`, so
  its `action` states the bound and tolerance, or a `data.quantity` fact holds them and the
  step's `note` names that fact, and the verifier enforces the rule. A fact whose whole claim is one limit
  carries `data.quantity`. See
  [SPEC-FORMAT](../../docs/SPEC-FORMAT.md#sequences-an-operation-per-step).
- **Layouts**: `section: data-formats`, `data.layout: {name, size, fields}`; fields have
  ids, names, byte offsets, sizes and meanings. A field packed inside a word takes
  `bits: [a, b]` within its `offset`/`size` container, numbered as the cited document numbers
  them, with the layout's `bitNumbering` (`lsb0`/`msb0`) and `byteOrder`
  (`bigEndian`/`littleEndian`, required when a multi-byte container has `bits`); value tables use
  `enumeratedValues` or `enumerationDefinitionRef` as on register fields (see
  [SPEC-FORMAT](../../docs/SPEC-FORMAT.md#layouts-bit-packed-fields-and-byte-order)).
  Include ownership, wrap, status, alignment and addressing facts with their evidence.
- **Ordinary claims**: `identity`, `interrupts`, `dma`, `sub-protocols`, `target`, `gotchas`,
  `open-questions`. Cover routing, ack/clear semantics, coherency and address translation,
  revision limits and target protocols/binding/packaging. Use `areas` for per-area confidence
  (`document-and-code`, `code-only`, `inferred`).
- **Values reported to the OS framework (#150)**: every value the driver hands the framework
  (MTU or frame size, buffer lengths, head and tail room, rates) is a `target` fact that states
  its unit, the layer of a size (frame or payload, with or without header and FCS) or what a rate
  counts, and a `src` citation of the framework's interface definition of that field (`role:
  target`). It also states the quantity the framework derives from it, such as "reported MTU
  1514, minus the 14-byte Ethernet header, is the IP MTU, 1500". A driver test asserts that derived quantity, with a comment citing the
  interface definition; asserting the literal constant again only repeats the code's reading.
  An undefined field gets `todo: {check: source, ...}`. See
  [SPEC-FORMAT](../../docs/SPEC-FORMAT.md#data-formats-interrupts-dma-target-mapping).

Set `requirement` for behavior and steps: `hw-required` needs document-class support that
actually states the requirement; `comment-explained` attributes the code's explanation;
`driver-choice` describes policy; `as-implemented` says only what the code does. Children
inherit the parent's requirement unless they override it. Independently supported register
fields, layout fields and sequence steps get verdict sub-keys `fact-id.sub-id`; otherwise the parent's
verdict covers them. A changed independent child does not stale unrelated children.

**Authoring rule (D31, D32)**: do not copy a fact that a canonical source already gives. A
canonical source is machine-readable, pinned and efficient to use, and your readers may use it
under their root's license (a register database, an IP-XACT or SVD file, a device tree
binding, a header). Cite it, and record only what it lacks: citations, the
`requirement`, verdict-relevant notes, `todo`s, sequences that point at it, and `conflicts`
where the documentation and the source disagree. A fact from a source the reader cannot be
pointed to (its license is outside the root's, or it is private) is a stand-in and stays, with
its citations; so does a reading of driver code and a summary that saves the reader the cost of
reading a long document. A fact whose only support is a usable canonical source is a
duplicate, which the verifier fails. Until the format has a reference for that source, strip the
fact to what the source lacks or leave it out. See
[SPEC-FORMAT](../../docs/SPEC-FORMAT.md#what-a-spec-holds-d31).

Inference is its own fact with premises and derivation, alone in support, plus a `todo`.
A gap omits support and carries `todo: {check, text}` and an observable `method` when needed.
Do not replace unsupported values with invented ones. Rendered hardware and open-question
lists come from records; add hardware TODOs for code-only width/reset/bit assumptions and
state what to probe. An empty list needs a coverage explanation. Milestones and reading
orientation may be prose in `orientation`/`note`; actionable facts belong in records.

## How to run it

Resolve source commit, peripheral/instance, target OS and destination root first. Missing
choices become a structured decision batch following `board-expert/QUESTIONS.md`; evidence
that cannot settle a value becomes a TODO. `board-expert` supplies the board map and pointers.

For more than a small single-file driver, the orchestrator starts a drafting subagent with
[the spec prompt](templates/spec-subagent-prompt.md). It fans out register, sequence,
firmware/tuning and target-tree slices to `hardware-investigator`, each returning
`kind: facts` records and resources. Run the register slice twice independently; compare
names, offsets, widths and bits, and resolve disagreements against the headers. Preserve
returned ids and evidence; change only `section: facts` to the destination section when
assembling the spec. Resolve id/resource collisions explicitly, with returned mappings;
never silently rename an id used by a fact reference. The drafter opens sources only to
settle conflicts or tighten citations. A small driver can be read in one context.

### Check, verify, land

Before running any subcommand, run `hwspecs --version` first. If `hwspecs` is missing or
reports an `unknown` or mismatched `HWSPECS_TOOL_COMMIT`, stop and report the missing
precondition with installation instructions (`HWSPECS_TOOL_COMMIT=$(git rev-parse HEAD)
cargo install --locked --path <hardware-specs>`) rather than compiling or installing inside a
subagent. `<root>` names the destination root, `<spec>` the spec file, `<source-checkout>` its
`linux` checkout and `<header>` a cited repo-relative header. Substitute actual repo names in
`--repo`/`--pin`; repeat `--repo NAME=CHECKOUT` for every cited source/target entry. These
commands are tested on SF2-7's widget peripheral fixture (whose register header is its synthetic
C file).

```bash
hwspecs validate <spec> --root <root>
hwspecs check <root> --require-license
hwspecs resolve <spec> --root <root> --repo linux=<source-checkout>
hwspecs inventory <spec> --root <root> --repo linux=<source-checkout> --pin linux --headers <header> --strict
hwspecs show <spec> --root <root> --repo linux=<source-checkout>
```

`validate` takes files and checks strict YAML and schema shape; `check` takes spec roots and
checks semantic rules, dependencies and license policy. `resolve`, `show` and `inventory`
take files. Add context roots to `check` when references require them. For document hashes,
supply `--docs-dir DIR`; bytes must be named `DIR/NAME`. Inspect resolution counts:
zero errors with skipped anchors is not complete evidence resolution.

When a run store is configured (`python3 utilities/run-store.py <campaign_run>`), the orchestrator
sets `HWSPECS_AUDIT_RUN=<campaign_run>` and wraps `hwspecs check`, `hwspecs resolve`, and
`hwspecs status` invocations with `python3 utilities/hwspecs-audit --step <step> -- hwspecs ...`,
logs any `hwspecs` tool defects via `python3 utilities/hwspecs-audit record-issue`, and records
subagent completion notices via `python3 utilities/hwspecs-audit record-subagent` (see
[PROCESS-AUDIT.md](../../docs/PROCESS-AUDIT.md)).

Without a `--repo NAME=CHECKOUT` binding for a repo entry, `resolve` fetches its URL at the
recorded commit. Only size or time limits produce skipped anchors; fetch or content errors
fail resolution. Inspect the `claim hex values absent from cited lines` warning: it flags
hex values in a claim that do not appear in its cited source lines and need review.
`RES-CLAIM-HEX-UNBOUND` flags a claim hex value that appears in the cited lines but only on
lines that share no identifier with the claim sentence holding it (the line, its nearest
preceding line ending in `{`, or the anchor's `symbol`); `--strict-claims` makes it an
error. `RES-CLAIM-RANGE-END` and `RES-CLAIM-RANGE-SUCCESSOR` fail an identifier range
`PREFIX<n>..PREFIX<m>` whose end is absent from the cited text or whose successor
`PREFIX<m+1>` is present, and `RES-CLAIM-NGPIOS` fails an `ngpios = <N>` the cited text
does not contain.

Inventory compares structured register offsets and field masks, not prose; cover omissions
or explicitly record scope limitations. Unsupported, conditional or ambiguous header
expressions are unknown and fail even when covered. Do not claim they passed; resolve them
by reading and record the limitation. `--strict` also
fails omissions, so a deliberately partial map cannot claim a strict pass.

A fresh verifier uses [the verifier prompt](templates/verifier-prompt.md) and
[spec-verifier](../spec-verifier/SKILL.md). It reads cited files in full once, then checks each
record and independently supported child against the performing lines. It repeats searches,
recomputes counts, checks hardware requirements against documents, tests coverage, and blindly
re-derives roughly 10% of anchors before comparing claims. Record unavailable documents and
TODO-method limits. Critical facts need an independent second reader coordinated by the
orchestrator. Verification records live in `<root>/resources/<device>.verify.yaml`, keyed by
fact/sub-key and using per-fact bases from `status --json`, not whole-file freshness.

Fix FAILs by finding the right evidence or correcting/removing the claim, then re-verify.
After acceptable verdicts and the verification gate, publish the spec at its destination and
link the generated view from the docs index. The verifier writes the record; the author must
not insert an empty placeholder record. Preserve GAPs and other non-PASS outcomes explicitly.

### Keeping it true

For claims about code, disagreement with the pinned code means fix the spec. A hardware
claim requires its own evidence; code being citable does not prove that code is correct.
Before moving one commit, inspect drift and then rewrite only the reviewed pin:

```bash
hwspecs drift <new-commit> <spec> --pin linux --root <root> --repo linux=<source-checkout>
hwspecs drift <new-commit> <spec> --pin linux --rewrite --root <root> --repo linux=<source-checkout>
```

`<new-commit>` is a full lowercase hash. Rewrite moves the resource commit and unique moved
line ranges; changed anchors get `stale: {was: <old commit>}`. Changed search scopes or read
failures refuse rewriting. Re-read affected evidence before clearing stale fields, update
verdict bases and run the gate again. Semantic edits stale per-fact verification bases;
`spec_sha256` is informational. Never clear a stale field just to make a check green.
