---
name: peripheral-spec
description: >-
  Produce a format 2 peripheral implementation spec from driver source whose license fits the
  target spec repository. Every fact carries structured support at an immutable commit or a
  named document locator. Use for documenting, specifying or porting a peripheral from citable
  source or public datasheets; not for NDA source. Uses spec.py validate, check, resolve, show,
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

See the [glossary](../../GLOSSARY.md) and [spec-format contract](../spec-format/SKILL.md).
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

The format 2 root marker requires `format: 2`, `layer`, `name`, `license` and `accepts`.
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
`kind: peripheral`, `id`, `name`, `resources` and `facts`. Repository entries have HTTPS URLs,
full lowercase immutable `commit` values, file licenses and `role: source` or `target`.
Quote structured hex values in lowercase canonical form (`"0x0"`, never `"0x00"` or `"0xA"`);
omit unknown width, access or reset rather than guessing them. No Markdown frontmatter or
body surrounds the YAML.

- **Register map**: `section: registers`, `data.register: {name, offset, width, access, reset}`
  (last three optional), and optional `data.fields`. Each field has `id`, `name`, inclusive
  `bits: [low, high]`, and `meaning`. Follow databook order, including untouched registers
  when documents cover them. The register's `claim` may be omitted; the view derives it.
- **Sequences**: `section: sequences`, `data.sequence.steps` with stable ids and `action`,
  and optional `order` constraints `{before, after, requirement, support}`. Support every
  performing step precisely; record prerequisites, initialization, reset, power, error and
  teardown paths. Constraints describe required ordering separately from the driver's order.
- **Layouts**: `section: data-formats`, `data.layout: {name, size, fields}`; fields have
  ids, names, byte offsets, sizes and meanings. Include ownership, wrap, status, alignment
  and addressing facts with their evidence.
- **Ordinary claims**: `identity`, `interrupts`, `dma`, `sub-protocols`, `target`, `gotchas`,
  `open-questions`. Cover routing, ack/clear semantics, coherency and address translation,
  revision limits and target protocols/binding/packaging. Use `areas` for per-area confidence
  (`document-and-code`, `code-only`, `inferred`).

Set `requirement` for behavior and steps: `hw-required` needs document-class support that
actually states the requirement; `comment-explained` attributes the code's explanation;
`driver-choice` describes policy; `as-implemented` says only what the code does. Children
inherit the parent's requirement unless they override it. Independently supported register
fields and sequence steps get verdict sub-keys `fact-id.sub-id`; otherwise the parent's
verdict covers them. A changed independent child does not stale unrelated children.

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

Use Python from a virtual environment installed with spec-format's hash-pinned requirements.
`<python>` names that interpreter, `<spec.py>` the sibling `spec-format/scripts/spec.py`,
`<root>` the destination root, `<spec>` the spec file, `<source-checkout>` its `linux` checkout
and `<header>` a cited repo-relative header. Substitute actual repo names in `--repo`/`--pin`;
repeat `--repo NAME=CHECKOUT` for every cited source/target entry. These commands are tested
on SF2-7's widget peripheral fixture (whose register header is its synthetic C file).

```bash
<python> <spec.py> validate <spec> --root <root>
<python> <spec.py> check <root> --require-license
<python> <spec.py> resolve <spec> --root <root> --repo linux=<source-checkout>
<python> <spec.py> inventory <spec> --root <root> --repo linux=<source-checkout> --pin linux --headers <header> --strict
<python> <spec.py> show <spec> --root <root> --repo linux=<source-checkout>
```

`validate` takes files and checks strict YAML and schema shape; `check` takes spec roots and
checks semantic rules, dependencies and license policy. `resolve`, `show` and `inventory`
take files. Add context roots to `check` when references require them. For document hashes,
supply `--docs-dir DIR`; bytes must be named `DIR/NAME`. Inspect resolution counts:
zero errors with skipped anchors is not complete evidence resolution.

Without a `--repo NAME=CHECKOUT` binding for a repo entry, `resolve` fetches its URL at the
recorded commit. Only size or time limits produce skipped anchors; fetch or content errors
fail resolution. Inspect the `claim hex values absent from cited lines` warning: it flags
hex values in a claim that do not appear in its cited source lines and need review.

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
<python> <spec.py> drift <new-commit> <spec> --pin linux --root <root> --repo linux=<source-checkout>
<python> <spec.py> drift <new-commit> <spec> --pin linux --rewrite --root <root> --repo linux=<source-checkout>
```

`<new-commit>` is a full lowercase hash. Rewrite moves the resource commit and unique moved
line ranges; changed anchors get `stale: {was: <old commit>}`. Changed search scopes or read
failures refuse rewriting. Re-read affected evidence before clearing stale fields, update
verdict bases and run the gate again. Semantic edits stale per-fact verification bases;
`spec_sha256` is informational. Never clear a stale field just to make a check green.
