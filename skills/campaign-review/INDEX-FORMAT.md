<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Campaign index format, version 1

**Terms** (see the [glossary](../../GLOSSARY.md)): a **claim** is a behavior a
check's PASS is used to support; **qualification** shows that a planted defect
made that check fail for the intended reason. A **basis** records the identities
behind a verdict. An **item** is a finding with a recorded disposition.
A **status index** keeps those verdicts and items together for a campaign.

CR2 extends the CR1 format with verification history and linked revision and
candidate records. CR3 adds the registry and read-only freshness sweep described
below; stopping-rule evaluation and the execution queue remain later milestones. A clean index
check does not establish that a campaign is sufficient for scope.

The claim map and status index live in a campaign directory. Both have `version: 1` and the same
nonempty `campaign` ID. Mappings are closed: unknown and duplicate keys fail.
Use strings for dates and hashes. Lists of IDs and links must not repeat members.
The index contains public-safe IDs, hashes, verdicts, scope and disposition
reasons, run IDs and links. Source excerpts, commands, infrastructure identities,
transcripts and raw run artifacts stay in private records.

## Claim map: claims.yaml

Top-level fields are `version`, `campaign`, `harness` (a repository-relative
Python file), and a nonempty `claims` list. Each claim has:

| Field | Meaning |
| --- | --- |
| `id`, `title` | Stable claim ID and its frozen behavior statement |
| `mandatory` | Boolean; all e1000 Q01–Q28 claims are mandatory |
| `cites` | Nonempty list of spec section IDs, such as `"5.2"`; expected-outcome dependencies for later invalidation, not manual section numbers |
| `checks` | Exact emitted names, including expanded sizes and reload suffixes; no wildcards |
| `scenarios` | Scenarios in which the result is cited; shared claims include reload and before/after names |
| `scope` | Qualification limits; a PASS must not broaden these |
| `defects` | List of `{id, run_ids, control_runs, outcome, evidence}` records |
| `evidence` | Nonempty list of repository-relative file links, optionally with fragments |

A defect outcome is `detected`, `unobservable`, `insensitive`, `equivalent`, or
`not specific`. Each defect has nonempty run and control lists. A qualified claim
needs at least one detected defect. Nonqualifying attempts remain in the cited
run store; the map need not duplicate the entire attempt history. Q18 explicitly
records the attempt that established its shortfall. For Q27 the map uses FC-1's
final-harness f2 confirmations; its evidence also preserves the original f1 ×3.

Run IDs are either a named run store or `run-id/scenario-run-id`. Store-only IDs
mean the evidence aggregates runs; they are not glob patterns or filesystem paths.
The checker does not require private artifacts to be locally present.

The e1000 `cites` mapping is an operator mapping of public recall locations and
harness/evidence requirements. It uses enclosing sections when the prose does
not identify a narrower passage; it is not a new spec reading. Q17 uses the
whole driver integration section, 10.3. A future uncertain dependency must widen,
not silently disappear.

## Status index: status.yaml

Top-level fields are `version`, `campaign`, `revision_range` (inclusive first and
last landed revision numbers), `revisions` (headers keyed by string revision
number), `bases` (a mapping from basis ID to identity record), and `entries` (a list).
Every revision in the declared range must have a header and accuracy reading.
Basis records are shared to avoid
repeating long hashes; an entry's `basis` refers to exactly one record. Once cited,
a basis is immutable: a changed identity gets a new basis ID.

Every basis has all of these keys:

| Field | Type and meaning |
| --- | --- |
| `spec_revision`, `spec_sha256` | Positive integer and full 64-character lowercase SHA-256 |
| `sections_read` | Section IDs actually read for a reading; empty for run verdicts |
| `dependencies` | Declared section IDs; `null` means unrecorded, requiring whole-revision widening; `[]` means explicitly none |
| `source_pins` | List of `{id, version, sha256? , commit?}`; at least one full hash or 40-character commit per pin |
| `harness_sha256`, `guest_init_sha256` | Harness and guest initialization script identities, or `null` |
| `emulator` | `{id, version, sha256, accel}` or `null` for non-run work |
| `guest` | `{kernel_sha256, busybox_sha256, initramfs_sha256}` or `null`; component hashes may be `null` when unrecovered |
| `reference_module_sha256`, `candidate_module_sha256` | Full hashes or `null` when not applicable/unrecovered |
| `toolchain` | Recorded compiler name/version string, or `null`; `gcc-14` is not an exact compiler build |
| `model` | `{role, name, version}` or `null`; roles are reader, implementer, reviewer |
| `missing` | Explicit limitations on recovered identities; never fill an unknown by guessing |

`null` never compares equal to a newly discovered identity as proof of freshness.
Historical observations spanning several harnesses have a null harness identity
and name that limitation; their emulator identity remains recorded. The candidate
result basis records its initramfs hash; qualification initramfs files vary by
planted module and remain recoverable per run. Qualification bases name the spec
used for the claim context, not a claim that the reference was built from it.

Every entry has:

| Field | Meaning |
| --- | --- |
| `id`, `kind`, `basis` | Globally unique ID, kind below, existing basis ID |
| `verdict` | Recorded verdict; short descriptive observation/finding for those kinds |
| `rule` | Named scoring/qualification rule; values below |
| `status` | `{state, reason, stale_since}`; state is current, stale, contested or superseded; a nonempty change ID/date/link in stale_since is required only for stale, otherwise null |
| `supersedes` | IDs of replaced entries; targets must exist, have the same kind and claim, and be superseded; self-links and cycles fail |
| `run_ids`, `evidence` | Nonempty run-ID and public evidence-link lists |
| `decision` (optional) | `{who, date, link}`; a mandatory claim's shortfall requires who: user and the approval evidence |
| `cost` (optional) | Nonempty mapping of nonnegative finite seconds, tokens and/or usd; omitted means unmeasured |

The initial rules are `isolated-defect-specific-A6-2026-09-25`,
`isolated-acceptance-set-2-repetitions`, `emulated-observation-not-hardware`, and
`C6-item-classification-2026-09-26`. `A1-as-written` and
`A1-amended-2026-09-26` name the reading policies for CR2. Rules are identities:
verdicts under different rules must not be compared without explicitly noting the
policy change. CR4 will implement the comparison guard.

| Kind | Additional required fields and verdicts |
| --- | --- |
| `qualification` | `claim`, `validated_harness_sha256`; verdict qualified, shortfall, unqualified or insensitive. A shortfall also has `shortfall: {reason, reopen}`. The validated hash is the latest harness to which the cited diff/requalification chain carries the original qualification; the basis retains the original run harness |
| `result` | `claim`, `round`, `qualification` (entry ID), `qualified_evidence` (boolean); verdict PASS, FAIL or ERROR. Basis requires candidate and harness hashes. Q18's PASS has qualified_evidence: false |
| `observation` | `sections` (nonempty spec section list), `evidence_class: emulated`; verdict is a concise observation within the named runs, never a hardware conclusion |
| `item` | `class` R/E/W, `source` integer 1/2/3, `target`, `disposition`; optional `aliases` for the same finding under another evidence key |
| `verification` | `reading_id`, `text`, `sections`, `evidence_classes`, `verifier`, `round`, `independence`, `purpose`, `covers_revisions`, `scope`; verdict is the historical reading's summary, including unresolved or subsequently corrected findings |
| `candidate_round` | `round`, `applied_items`, `verification`, `results`, `scope`; verdict is the historical acceptance summary, not another qualification |

Each map claim has exactly one nonsuperseded qualification, even if stale or
contested. At most one current candidate result per claim is permitted. A verdict
is never edited into a different verdict: append a replacement and supersede the
old entry, preserving its basis, rule and attempts. Status changes record why the
existing verdict can no longer be cited as current. Applied findings remain current
records of an applied disposition; `applied` is not the same as `superseded`.

## Revision headers and verification history

Each revision header has `spec_sha256` (the landed text), `drafts` (draft ID to
full hash), `requirement_change` (boolean), `changed_sections`, `items` (applied
spec-item IDs), `evidence` and `run_ids`. Only the first indexed revision may use
`requirement_change: null`, meaning baseline, with no change sections. Older
requirement-change declarations may be reconstructed from public evidence rather
than quoted from a historical header; the evidence must say which. A true header
requires an R item applied to that revision; a false header cannot link an R item.
Conversely, every applied spec item must name an existing revision and appear in
that revision's item list; an unlisted item cannot bypass header validation.
The e1000 backfill covers revisions 3–8, with revision 7 explicitly wording/evidence
only. Header changes are the union across that revision's attempts; the header
itself is not a numbered spec section.

For a verification entry:

- Only the common optional fields `decision` and `cost` are allowed. `aliases`
  and `shortfall` are not verification fields.
- `text` is `landed` or a draft ID in its basis revision's header. The basis hash
  must match exactly. A failed draft never inherits the landed hash. Draft entries
  stay superseded; a corrected sequential reading links them through `supersedes`.
- `sections` are the entry's scope; `basis.sections_read` holds the full reading
  unit's section list. Changed-claim readings do not certify every sentence of an
  enclosing section. Parent section IDs conservatively cover their descendants.
- `reading_id` identifies one historical reading, even when later changes require
  section slices. Slices must partition the basis section list without duplicates
  and share verdict, round, model basis, policy, scope, and citations. Repeated
  verdict totals are the reading's totals, **not per-section counts**; deduplicate
  by reading_id. No split is needed for a draft replaced as a whole or for the
  latest reading when no later revision has touched it.
- `evidence_classes` lists the relevant classes: databook, standard,
  source-observed, inference, kernel, emulated. For broad historical scopes this
  is a conservative union, not a claim that a source-observed fact was re-read
  against driver source. Such readers checked the tag and caveat only.
- `verifier` names the agent role/harness; `basis.model` names the reader model and
  version. `round` is a string. `independence` is independent, sequential,
  adjudication or gate. `purpose` is accuracy, transfer or acceptance; gate is
  required for the latter two, which cannot satisfy accuracy coverage.
- `covers_revisions` names the changes the reading considered. SR-7's combined
  reading covers 5 and 6, but its actual text and hash remain revision 6. It counts
  as one reading, not two. Adjudication is likewise not another full reading.
- `scope` records limits, exceptions and unresolved results. A current status
  means the recorded verdict still applies within that scope, not that every
  verdict is PASS or that two independent readings exist.

Independent readings remain separate records; agreement does not supersede the
first reading. `supersedes` expresses a replacement, not an additional reading.
Historical records retain `A1-as-written`; applying the later amended stopping
rule must not rewrite their policy identity. No legacy verification file is
converted by this backfill.

Complete dependencies recorded as section IDs in historical briefs are retained
on every slice. A reconstructed union of cross-check locations is not a complete
declaration and must not be presented as one. When no complete set is recoverable,
`null` requires whole-revision widening. Thus section slicing does not promise
fine-grained freshness when the recorded dependency information cannot support it.
An older reading with null dependencies cannot remain current. The sweep evaluates
changed identities and dependency overlap; this checker does not implement those rules.

Candidate-round entries link the header's applied R items, landed accuracy
readings and per-claim results on the exact same basis and round. Historical
aggregates may have an empty `results` list when per-claim history was not
backfilled; their scope must say so. CF-2 a2 links CR1's existing 28 results.
CF-2 a1 supersedes CF-1 a1; CF-2 a2 supersedes a1 because the harness changed.
The TNCRS rule's presence in the candidate comes from the linked implementation
review and trace attribution. The emulated acceptance PASS does not establish
correct attribution across a duplex change.

## Items and shortfalls

Classes are **R**, changes what a driver must do; **E**, evidence for a claim;
**W**, wording or form. Source **1** is field evidence, **2** updated sources,
**3** improved models/tools or a new reading of the same inputs.
Targets are `spec`, `candidate`, `records`, `upstream`, `hardware`, or `review`.
R is the conservative class for a deferred candidate behavior change; a candidate
item does not itself assert that the spec is wrong. Records findings never become
spec items merely by sharing the same file of findings.

Dispositions:

- `queued`: requires `destination`, the named brief, revision, milestone or decision.
- `applied`: requires positive integer `revision` and evidence of the resolution.
- `shortfall`: requires `reason` and a nonempty `reopen` condition; optionally destination.
- `rejected`: requires a nonempty `reason`.

Each disposition allows only the fields listed for its state. Every destination,
including an optional shortfall destination, must be a nonempty string.

The four shortfall reasons are `unobservable`, `blocked`, `out of scope`, and
`not worth it`. A mandatory qualification shortfall also requires a user decision.
An alias shares a disposition and is globally unique; A-RR-5 aliases SR-8-2 rather
than adding a second open item. A-RR-7 targets the next candidate brief. SR-8-4
is a records finding. Outward reports remain user decisions.

## Checker boundary

From the repository root:

```bash
uv run --with pyyaml python3 skills/campaign-review/scripts/index_check.py evals/e1000
uv run --with pyyaml python3 -m unittest discover -s skills/campaign-review/tests
```

`--root` explicitly selects the evidence root (default: working directory).
Links must resolve to files inside it, including after symlink resolution;
fragments are locators, not checked Markdown anchors. Home-path privacy is checked
separately by `utilities/check-no-private-paths.py`. The checker reads the
harness syntax tree and expands finite literal name construction, visiting both
runtime branches. It never executes the harness. Unsupported dynamic construction
fails to produce a matching name, so a new construction may need a checker update.
Formatted-string conversions and explicit format specifications are unsupported
and cannot supply a matching check name.
Name existence does not prove stimulus, scenario reachability or qualification;
the artifact reviewer traces those to evidence.

Exit codes: 0 clean, 1 findings, 2 usage, 3 missing input/PyYAML. `--json` emits
one object with `ok`, `counts`, `findings`; `--skill` prints embedded usage.

## Source registry: sources.yaml (version 1)

**Terms:** a pinned-file adapter returns identity metadata for opaque bytes; a
change map narrows a change using reviewed metadata bound to its exact old and
new hashes. An eligible record is current after identity checks, not accepted by
the stopping rule. See the [glossary](../../GLOSSARY.md).

The registry is a third file, with `version: 1`, matching `campaign`, `sources`
(list), `citations` and `premises` (mappings), and `contradictions` (list). The
last three may be empty. Duplicate keys and source IDs fail. The sweep reads these
three metadata files only; it never opens source paths, parses a spec or diff,
hashes files, invokes adapters or executes a harness. Run the existing index
checker first for evidence links and harness check-name existence. The sweep
reuses its metadata validation with file inspection disabled.

Each source has these required fields:

| Field | Meaning |
| --- | --- |
| `id`, `kind`, `version` | Local identity, kind below, and operator-declared version string |
| `sha256` | Observed full hash, or null when unavailable/not recorded; never fabricated from a version string |
| `expected_sha256` | Adopted file pin used by the adapter's comparison; a refresh never changes it |
| `status` | `ok` (identity available), `blocked` (file inaccessible), `unknown` (no local file supplied) |
| `checked` | ISO date of the observation or historical pin check; importing metadata is not a new byte check |
| `provenance` | `{adapter, version, version_method}`; adapter name/version and how the source version was determined |
| `file` | `{root: repository or run_store, path: relative/path}` or null for externally supplied identities; absolute paths, traversal and symlink escapes are rejected |

`kind` is `spec`, `document`, `kernel`, `reference`, `harness`, `guest_init`,
`emulator`, `guest_kernel`, `guest_image`, `guest_busybox`, `candidate`, `toolchain`,
`model`, or `fixture`. Kinds bind to the corresponding index basis fields.
Artifacts compared by hash require a non-null `sha256` when `status` is `ok`;
otherwise the registry is invalid (JSON findings, exit 1). Use `blocked` or
`unknown` when the hash is unavailable. The compiler compares by its nonempty
version string; model and fixture changes do not invalidate prior verdicts, so
these three kinds permit null hashes. Kind, status and file-root values must be
strings before their allowed values are checked.

Source documents and kernel files match `source_pins.id`; optional `pin` overrides that
match (the eight Linux files share the `linux` commit pin). Optional `commit`
compares the recorded upstream commit. Per-file drift against `expected_sha256`
also invalidates readings at that shared commit, even if its version stays fixed.
Optional `bindings` is a nonempty list of basis IDs limiting an artifact's scope;
the candidate initramfs uses this because its contents include a particular module.

A `spec` source also requires positive integer `revision`. Landed revision
headers supply changed sections and requirement changes; every intervening
header matters. The earliest applicable header is the reported stale-since
revision. When a new revision has not been indexed yet, a reviewed hash-bound
change map supplies its sections, with an optional source `requirement_change`
boolean. Without that boolean, a missing header conservatively means a
requirement change. Without mapped sections, the whole document is affected.

`toolchain.version` compares the recorded compiler string. A change to a recorded
compiler invalidates run verdicts using it; null basis values cannot trigger it.
For e1000, `gcc-14` remains an incomplete identity with null binary hash, explicitly
documented in the provenance. Neither a hidden package upgrade nor an unregistered
compiler can be detected. Model and fixture identities cause no invalidation.

`recorded-pin` provenance means an operator imported a historical public pin or
run identity. Its `ok` is availability of that recorded identity, not live proof
of the host's state. The public e1000 registry carries those snapshots for the
manual, Linux files, emulator package/binary, guest kernel/BusyBox, reference
module and compiler. Five available files were refreshed locally for CR3; the
evidence lists them. A deployment must refresh its external identities when the
host changes. The sweep does not silently reach out to that host.

### Change and dependency mappings

Optional `changes` on a source is a list with one record per prior hash:

```yaml
changes:
- from_sha256: <full old hash>
  to_sha256: <full observed current hash>
  since: <change ID or date>
  reviewed: true
  sections: null
  checks: [<exact emitted check name>]
  scenarios: null
  evidence: [<reviewed diff artifact or run ID>]
```

All fields are required; `sections`, `checks`, and `scenarios` are lists or null.
The current hash must match `to_sha256`, and narrowing applies only to entries
whose old hash matches `from_sha256`. `reviewed: false` cannot narrow anything.
An explicitly empty reviewed list means no changes at that level; use null for
unknown. A reviewer must confirm the map covers the entire diff, including shared
helpers and deleted checks. The sweep maps names to claims using `claims.checks`.
Unknown check names or absent check mapping widen to the supplied enclosing
scenarios using `claims.scenarios`; absent/unknown scenarios widen to every
qualification. A mapped check change affects every claim using that check.
All end-to-end mappings must be supplied for multiple prior hashes, or the
unmapped bases widen. Qualification comparisons use `validated_harness_sha256`,
not the original run's older harness.

This metadata boundary is deliberate: the operator/reviewer reads diffs and
supplies the maps; the sweep cannot infer semantic dependencies from source text.
Changes inside a shared helper must use all affected scenarios or the whole
harness, not a nearby check name. No automatic diff parser claims otherwise.

`citations` maps entry ID → source ID → cited source section IDs, distinct from
spec section IDs. A document change intersects these with its mapped sections.
Use the enclosing section for uncertain item mappings. Missing citation or change
detail widens to all verification verdicts citing that document. Parent IDs cover
descendants (`5` includes `5.10`; `5.1` does not). `source_pins` on run records are
context, not a claim that a run is a manual reading.

`premises` maps claim ID → nonempty observation-ID list. A hardware contradiction
is `{observation, since, conflict}`, where `conflict` is a relative conflict-record
locator (for e1000, the spec's §12 conflict table). It marks the observation
contested and premise qualifications stale. Without an exact premise mapping,
the sweep widens to claims whose spec sections overlap the observation's sections.
The same rules apply to observations already contested in the index, even without
a registry contradiction. When the original contention has no recorded date,
dependent staleness cites `index:<observation ID>` rather than inventing one.
Readings tagged `emulated` follow stale/contested observations through their sections
and declared dependencies; null dependencies widen to the reading unit. Candidate
results remain true of the emulator. Conflict locators are reported for the
operator to record; the sweep never edits the spec or invents hardware evidence.

### Adapter and report

```bash
uv run --with pyyaml python3 skills/campaign-review/scripts/pinned_file_adapter.py evals/e1000/sources.yaml spec --json
uv run --with pyyaml python3 skills/campaign-review/scripts/sweep.py evals/e1000 --json
```

The adapter supports `--root`, `--run-store`, `--write` and `--dry-run`. With no
explicit run store it reuses `utilities/run-store.py` configuration; it never
searches. It wraps `corpus_check.check_blob` for hashing and pin comparison.
JSON contains `result` with C8's identity fields/provenance and `matches_pin`,
plus `ok`, `updated`, `would_update` and `findings`. Missing sources produce
blocked/unknown with null observed hash, without leaking an absolute path or
content. `--write` updates observation fields only and drops obsolete change maps
if the hash changes. It never adopts a new expected pin or guesses a version.

Sweep JSON contains `entries` (all stale/contested records, previous state,
reasons and stale-since), `stale_controls` (reference control run IDs from the
claim map), `conflicts`, `unavailable`, `unmapped_harness`, state `counts`,
`eligible` record IDs and `eligible_counts`. Eligibility is only a freshness
filter: it does not count independent readings, prove qualification, apply S1–S5,
or declare sufficient-for-scope. Existing stale/contested states persist, even
if today's hashes match; superseded entries remain history. Stale and contested
entries never appear in eligible counts. A reference-module change reports its
control runs separately because CR1 did not make them independent index entries.

The sweep supports `--registry` to select deployment-owned metadata. Blocked or
unknown source observations are explicit incomplete-precondition findings, not
identity changes; they cannot prove freshness. Exit 3 takes precedence over
stale findings when any source is unavailable. Otherwise exit 1 means stale or
contested verdicts/controls (or invalid metadata), and exit 0 means no findings.
Both commands use exit 2 for usage errors and support `--skill`. No real sweep
or private adapter invocation is added to public CI; their synthetic tests run
with the existing campaign-review discovery command.
