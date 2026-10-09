---
name: spec-format
description: >-
  Reference skill: the format 2 contract for YAML hardware specs and verification records.
  Read when authoring or consuming board, SoC, chip, IP or overlay specs, or driving spec.py.
  Defines evidence classes, references, roots, rendering and freshness; schemas define shapes.
---

<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Spec format 2 (contract)

## Terms

- **Fact record**: one claim with a stable id and structured evidence, called **support**.
- **Root**: a directory of specs with a `board-specs.yaml` marker; its **layer** determines
  merge order. An **overlay** adds facts to a spec identified in another file.
- **Fact reference**: a structured link to another fact; a **full reference** also names its root.
- **Pin**: the exact commit and license of a cited source tree. An **anchor** names a place in it;
  a **locator** names a place in a document.
- **Verification record**: a separate file of verdicts. A **basis hash** fingerprints a fact's
  declared dependencies; **freshness** compares the recorded hash with the current one.
- **Rendered view**: generated Markdown for reading. The **viewer** is the later HTML view with
  provenance labels (**badges**) drawn only from fields.

See the [glossary](../../GLOSSARY.md) for these and the hardware terms. This is the shared
contract; the [design](../../docs/SPEC-FORMAT-V2.md) records its rationale and decisions D1–D22.
Read the schema branch for the kind you write and start from
[board-spec-scaffold's templates](../board-spec-scaffold/templates/).

## Files and shapes

The schemas are authoritative for required fields, enums, patterns and closed record shapes:

| File | Schema | Definitions to read |
| --- | --- | --- |
| `<name>.spec.yaml` | [spec.schema.json](schema/spec.schema.json) | kind branches; `$defs.fact`, `support`, `premise`, `resources`, `instance`, `variant`, `assumption`, `conflict` |
| `<name>.facts.yaml`, `kind: facts` | [spec.schema.json](schema/spec.schema.json) | facts branch; same evidence records, `section: facts` |
| `board-specs.yaml` | [root.schema.json](schema/root.schema.json) | marker, license policy, optional extension fragment |
| `<root>/resources/<name>.verify.yaml` | [verify.schema.json](schema/verify.schema.json) | record and verdict shapes |

Every `*.spec.yaml` below a root is a spec, regardless of subdirectory. The filename chooses the
schema; identity comes from `id`, or `overlays`. Conventionally name base files for the id and
use distinct filenames for overlays. Put SPDX copyright and license comments at the top,
matching the target repository's license. No frontmatter or Markdown body surrounds format 2.

Implemented kinds are `board`, `soc`, `chip`, `ip`, `overlay`, `facts`. Peripheral/review kinds,
`data`, `requirement` and verdict sub-keys arrive in SF2-7; the current checker refuses them.
Do not invent fields from a future design example.

Place facts by kind:

- `board`: wiring, boot media/configuration, console connector/routing, power, headers;
  `parts` composes the SoC and chips.
- `soc`: addressing, entry contract, core topology, interrupt controller, debug UART placement,
  timers, clocks/power, GPIO/pinmux, runtime device-tree changes; `instances` places IP blocks.
- `chip`: how the companion is reached, its address window, contents and hand-off state.
- `ip`: standards, register model/sequences, public variants/errata; no instance addresses.
- `overlay`: `kind: overlay` and `overlays` name the target; no `id` or `parts` override.

Sections are `quick-facts`, `gotchas` for board/SoC/chip; `standards`, `programming-model`,
`variants-quirks`, `gotchas` for IP. The schema admits their union for overlays; `check`
requires the target's sections. Facts retain reading order within sections.

## Authoring records

A fact holds one claim a reader could act on. Its id survives text, section and order changes,
is unique among facts, instances and variants of a spec id in a root, and is never reused
when deleted. Board-spec kinds require a plain title. Evidence lives only in `support`;
a tag or citation typed into `claim` has no evidentiary meaning.

Read classes can support a claim jointly. A conclusion none of the sources states is a separate
`inference` fact, even when a format 1 bullet mixed the read claim and conclusion. A gap has no
`support` key and carries `todo`, never `support: []`. `todo.check` is `hardware`, `document`
or `source`; `text` states the question and check; optional `method` describes how to observe
it. The method must observe the thing (an EL1-only probe cannot read an EL3-only register).
For a supported claim with a remaining unknown, keep support and add a TODO for that unknown.

Mark bring-up-critical addressing, entry and debug-console facts `critical: true`; omit it
otherwise. The record needs a fresh independent second reader. Declare dependencies with
`assumes` (same-file `assumptions` ids) or `relates` (fact references with `qualifies`,
`contradicts`, `refines`, `same-as`). Use `scope` for board, revision, mode, build or configuration
limits. Assumptions are conditional inputs, with no verdict of their own.

Keep conflicting readings in `conflicts` with their own read support. An unresolved conflict is
contested; a resolution records `decided` and, when relevant, the assumption that justified it.
`orientation` and `note` are uncited context, never a place for actionable facts. `notices`
carries required source-license notices, never source excerpts.

Instances and variants have stable ids and support like facts, verified under those ids.
An instance's `reg` is a canonical hex string such as `"0xfe201000"` (lowercase, no separators
or leading zeros), or null with a TODO; `irq` may likewise be null with a TODO. SPI/PPI numbers
and optional INTIDs must agree; extended interrupts name a parent. `clocks: []` is allowed.
Variants name shared/differing facts and evidence; use `variant_of` for a separate board spec
when wiring or console materially differs. Instance/variant rows cannot receive GAP, even
when a row still needs support.

### Evidence classes

Field shapes are in `$defs.support` and its referenced definitions, not prose tag grammars.

| `class` | Meaning and authoring rule |
| --- | --- |
| `databook` | Datasheet, TRM or IP databook; name a matching document and precise locators. |
| `standard` | Architecture or public standard, including Linux's boot protocol; cite clauses/sections. A heading alone suffices only for an unpaged document. |
| `doc` | Vendor/project documentation, product page, maintainer reply or cover letter; name which document and where. |
| `rtl` | Digital design on the named revision/module; cite a document with locators or source anchors. Says nothing about analog behavior or wiring. |
| `DT` | Device-tree values, including a decompiled production blob; name source lines or a blob node and its pinned origin. Takes the tree's license and is gated like `src`. |
| `src` | What code defines or does at an exact commit; source anchors required. No hardware TODO is needed for a claim about that code. |
| `hardware` | Measurement on a named board by a stated method/date; retain revision, firmware, conditions and run IDs when relevant. |
| `emulated` | Observation from outside a named/versioned device model, with runs or an observation fact reference. Never the only support class; requires a TODO. |
| `press` | Third-party reporting, a lead requiring a TODO. Vendor documentation belongs in `doc`. |
| `inference` | Conclusion with explicit premises and derivation, optionally confidence; alone in support, with a TODO. |
| `source-observed` | Extension-defined class needing a TODO and root-declared schema fragment; never a substitute for core source citations. |

A `src` fact about where hardware actually is needs a document class too. If code is the only
evidence, state what that code maps or writes; put a hardware conclusion in a separate inference
with a TODO. A shipped product's use of a source build is also an inference until established.
Trace executed control flow rather than infer behavior from a flag table.

Document support names `resources.documents` in the same file and matches the document's class.
Locator values are strings: `page: "92"`, `pages: ["4", "6"]`. Databooks and paged standards
need a section, page/range, table, figure or clause; a `doc` may use a heading alone. Numeric
pages lie within the document's count, ranges run in order; `page_numbering` is printed or PDF.
Whether a locator is correct remains the verifier's job.

Anchors name `resources.repos` in the same file, overlays included. `src` uses a relative path,
inclusive 1-based `lines: [first, last]` and a nearby symbol. For a negative/global claim,
`search` replaces lines/symbol: describe the file/directory search the verifier must repeat.
Tools check scope existence only, never execute the prose or prove the negative claim. DT
source files require lines; blobs require a node (lines may also be present). Use `comment: true`
and attribute a comment's statement as a comment. `stale: {was: <commit>}` marks changed anchors
after drift and fails checks until re-verified and removed.

An inference premise is exactly one of a quoted `fact` reference (optional `uses` selects the
relevant part), `states` with its own read support, or an `assumption` id. Premise support
cannot contain another inference; reference that conclusion's fact instead.

### References

Always quote references in YAML: an unquoted `#` can start a comment.

| Form | Resolution | Example |
| --- | --- | --- |
| `#<fact id>` | same file | `"#scr-el3-bits"` |
| `<spec id>#<fact id>` | files of that spec id in the citing root only | `"bcm2711#which-build-ships"` |
| `<spec id>@<root name>#<fact id>` | named root | `"bcm2711@hardware-specs-docs#addressing-model"` |

The third is the full reference used in answers, views and basis dependencies. Cross-root
references must use it; short forms never search another root. Root names are required and
unique among roots read together; renaming one breaks references. Fact ids can repeat across
roots. Assumptions have a separate same-file namespace without `#`.

Every reference resolves unambiguously, cannot rest on a later layer, and is license-gated
through every referenced fact's dependencies. Premises cannot cycle. Relations may cycle;
their bases are computed as a group, so an edit invalidates the whole cycle. References in
conflicts/observations and evidence in premises do not bypass the gate.

## Resources, roots and composition

`resources.documents` is the one document registry. `url` is the canonical citation URL;
`retrieval` lists working fetch URLs separately. For Arm manuals keep
`https://developer.arm.com/documentation/<id>/latest` as the citation and record the actual
documentation-service static PDF URL in retrieval, with revision, SHA-256 and page count when
bytes are available. Documents in git record the commit read. `cite: false` means map-only
and cannot be cited; otherwise omit `cite` (no `cite: true` in format 2). Fetch status
(`ok`, `blocked`, `truncated`, `partial`) records availability, never validity.

Cited repos need full lowercase 40- or 64-hex `commit`, not a branch in `ref`. Quote digit-only
commits/hashes. A map-only entry may use `ref`; never both. All resource URLs use HTTPS.
The entry's `license` describes every cited file; its closed `files` list names each cited
path with `license_from` (`spdx-line`, `notice`, `license-file`). Different licenses need
separate entries. `resolve` compares SPDX lines where available; confirmation from notices
or license files remains the reader's job. `role` is `source`, `target`, `impl`, `ref`, and
changes no gate rule.

`series` maps unmerged work, never a citation. Keep canonical mailing-list URLs and workable
retrieval guidance in a note. `tools` is declarative: `via: skill:<name>` names the driver
skill. Fetch-method strings (`fetch_via`, retrieval `via`) are prose, never commands. Internal
access goes through a loaded vendor skill declared among tools: documents and repos have no
invocation `via` field. A document may have `access: internal`; repos have no `access` field.

The marker requires `format: 2`, `name`, `layer`, `license`, `accepts`. Accepts holds single
SPDX identifiers, not expressions; `[]` means documents only. The gate accepts `A OR B` when
either is accepted, `A AND B` only when both are; use canonical ids (`GPL-2.0-only`). Placement
follows the most restrictive cited source, including transitive dependencies. `DT` is gated
as source despite describing hardware. `--require-license` also gates map-only repos.
Composition (`parts`, `instances[].ip`) is not evidence and is not license-gated.

Discover pointers from exactly four places, never by searching a checkout for markers:
board-expert's shipped `specs/`; loaded skills' `board-spec root: <path>` lines; the checkout's
top-level marker; the user's board-specs configuration marker. Pointer paths may be relative
to the checkout or user-supplied absolute paths; machine paths never go into specs. The reader
expands marker `roots` in order; CLI arguments are explicit (`spec.py` does not expand them).
Deduplicate roots and separate format 1/2 compositions. No symlinks within or on the route to
a root, no nested markers.

Order by layer (`public` < `ip-vendor` < `soc-vendor` < `product` < `local`), then pointer order;
for the spec repositories use docs, permissive, GPL order. Resolve `parts` recursively, then
needed `instances[].ip`; overlay every composed id. Added facts retain root/layer and full
reference. Resource lists concatenate, later same-name entries replacing earlier ones for the
reader; scalars follow layer precedence. Citations still resolve in their originating file,
never against a merged resource replacement. Overlays add facts/relations/conflicts, never
rewrite base facts. Do not depend on competing overlays within one root to select facts:
make ids distinct and relationships explicit.

Public layers contain no internal documents/tools/host facts; vendor material stays private.
A reference may rest only on a root that checks clean. Context findings print as warnings,
but any underlying root error makes it untrusted; references into it fail transitively.
While any marker is unreadable, all root-qualified references fail. Repair root errors before
using their facts as verified evidence.

## Records and freshness

One record per spec file, overlays included: `<root>/resources/<name>.verify.yaml`, with the
filename's `.spec.yaml` removed. Records live at the root's own resources directory even if
the spec is nested; `spec_file` is relative to the root. Filenames that would share a record
are an error. The verifier, not board-expert, writes the body.

Record shape comes from the verify schema. `verdicts` keys are bare fact/instance/variant ids
of that file. All five `summary` counts (`pass`, `fail`, `unverifiable`, `gap`, `adjudicate`)
must match. GAP belongs to gap facts only. FAIL carries `correction`; ADJUDICATE carries
`readings` until settled to PASS/FAIL, retaining `adjudication` and readings. Fresh verdicts
state `contrary_evidence` and `citation_precision`; a format 1 carry omits them and records
`carried_from`. A carry is not a fresh source reading.

Use `spec.py status --json` to get each current `basis` and `upstream` map to write a verdict;
omit `upstream` when empty. `canonical: fact-v1` identifies the hash contract: fact except
`section`, cited resources, assumptions and referenced facts' bases. Whole cited entries count
except `records.BOOKKEEPING`: document `verified`, `fetch`, `note`; repos `verified`, `fetch`,
`fetch_via`, `note`; files-item `note`; assumption `todo`. Repos contribute only cited paths'
files items. Layout, comments, key order and folding do not count; semantic edits do.
`spec_sha256` is informational, never the freshness test.

Status is current, stale, upstream-stale, unverified or unknown. Unknown means no basis can be
established, never current. Upstream-stale means only external dependencies changed, with
none of their dependency closure returning to the own root; otherwise stale. A current FAIL
or malformed record is an error and untrusts its root. Freshness and a missing independent
second reader on a current critical verdict are warnings by default, errors under
`check --require-verified pr`; `main` keeps upstream-stale a warning but fails other freshness
cases. Policy applies to checked roots. Second readers differ from the main verifier and agree
with settled verdicts; disagreement needs adjudication. `status --stale` includes every
noncurrent fact and current critical facts lacking a second reader; it is a re-verification
list, not a list of all failed verdicts.

## Rendering and text safety

YAML is the source of truth. Views are generated, never edited, committed or parsed to recover
evidence. Read merged Markdown with status for orientation; YAML for exact fields. SF2-4 fences
author text verbatim in labeled top-level blocks without an info string, keeping it inert;
generated titles, citations and status remain literal. This supersedes the original design
sketch's inline author Markdown. Evidence still comes only from structured fields. HTML
rendering (`render --format html`) and the badge viewer arrive later in SF2-5; Pages and
pull-request publishing arrive with the SF2-11 cutover.

The strict UTF-8/NFC loader resolves only `true`, `false`, `null` and decimal 64-bit integers
as nonstrings. Dates, hex and versions remain strings. No YAML anchors, aliases, merge keys,
explicit tags/directives, duplicate/nonstring keys, multiple documents, BOM, invisible/control
characters (CRLF allowed). Optional lists are absent or nonempty; required empty lists like
`facts`, SoC `instances`, instance `clocks`, marker `accepts` are allowed.

SF2-4's CommonMark check rejects raw HTML, disallowed links/images, reference definitions,
footnotes, nesting deeper than 16, headings and unclosed fences in author fields, including
record notes. HTML-like text in code is allowed. Link schemes are HTTP, HTTPS, mailto and
in-page anchors. Format 1 tag spellings in prose are warnings, never evidence. Rendering
repeats containment checks and emits no partial view on errors. The later HTML viewer renders
images as links and separates generated badges from author containers (SF2-5).

## Command line

Substitute the installed `spec-format/scripts/spec.py` path for the repository-relative path.
Install [requirements.txt](requirements.txt) in a virtual environment with pip's
`--require-hashes`; all commands require pinned versions, without a fallback parser.
`python3 skills/spec-format/scripts/spec.py --skill` prints usage.

```text
spec.py validate <file>... [--root <dir>] [--json]
spec.py check <root>... [--context-root <dir>]... [--require-license]
    [--public-skill <name>]... [--stub <SKILL.md>]... [--stubs-from <dir>]...
    [--require-verified pr|main] [--json]
spec.py status <root>... [--context-root <dir>]... [--require-license]
    [--public-skill <name>]... [--stale] [--json]
spec.py render <root>... [--context-root <dir>]... [--require-license]
    [--public-skill <name>]... [--spec <id>] [--merged] [--with-status]
    [--source-commit <ROOT=40-hex>]... [--tool-commit <40-hex>] --format md [--json]
spec.py resolve <file>... [--repo NAME=CHECKOUT]... [--docs-dir DIR]
    [--root DIR] [--timeout SECONDS] [--limit-mb N] [--json]
spec.py show <file>... [same resolver options]
spec.py drift <commit> <file> [--pin NAME] [--rewrite] [same resolver options]
```

Availability: validate/check/status are SF2-1–3; Markdown render is SF2-4; resolve/show/drift
are SF2-6. SF2-4 and SF2-6 are review branches at this implementation and must land before
consumers run the combined workflow. Inventory and migration arrive later.

`validate` checks shape only; `--root` loads extensions. `check` adds names, composition,
references, license/trust and records. `--context-root` supplies dependencies without enforcing
their freshness policy; it cannot overlap checked roots. `--public-skill` allows a named public
tool skill; stub options verify thin expert skills' ids.

`status` prints summaries and freshness even on error. `render --spec` selects one id, not
its composed parts automatically: render every id needed for the question. `--merged` includes
context bases/overlays of selected ids; `--with-status` adds verdicts. Supply one
`--source-commit ROOT=SHA` per rendered root directory and `--tool-commit SHA` for the tool
(40 lowercase hex); without them commits are explicitly unavailable and YAML hashes identify
inputs. A bare source SHA works with one root.

Resolver commands take files, not directories. `--repo` binds a name to a local checkout at
the declared commit; unbound entries fetch over HTTPS. `--docs-dir` supplies bytes named
exactly `DIR/NAME`. `--timeout` is seconds per git operation; `--limit-mb` limits retained
objects/output, not transferred bytes. Only size/time limits skip; skipped anchors are counted
and even a fully skipped run can exit 0. Inspect counts before claiming resolution. `show`
also prints facts beside cited lines. Search claims still need a reader.

`drift` compares one pin with a full lowercase 40- or 64-hex commit; `--pin` selects it when
several are cited. `--rewrite` mutates the file: moves the pin, rewrites unique moved line ranges,
marks changed anchors stale, preserving comments/layout. Changed search scopes or operational
read failures refuse rewriting. Re-verify before removing stale markers. A reader does not
rewrite specs without an authoring request.

All commands offer `--json` as one result object. Exit 0 means valid/no error (warnings or skips
may remain), 1 invalid/check failure, 2 usage, 3 missing precondition/pinned dependency, 100
internal tool error. Validity does not prove a claim: verification re-reads evidence using
[spec-verifier](../spec-verifier/SKILL.md).

## Format 1 transition

A marker without `format` (or with `format: 1`) is format 1: `*.spec.md`, provenance clauses,
`resources.docs`, `ref` pins, `*.verify.md` and whole-file hash freshness. Existing
`board-expert/scripts/spec_check.py` and peripheral `anchor_check.py` stay read-only until SF2-12.
The [board-expert transition path](../board-expert/SKILL.md#format-1-reading-until-sf2-12) labels
this legacy behavior. Never pass format 1 roots to the format 2 checker, compose formats together,
or write a new format 1 spec. The frozen archive remains history.
