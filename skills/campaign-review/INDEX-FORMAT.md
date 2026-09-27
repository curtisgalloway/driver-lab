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
A **deployment manifest** declares plugins and model roles; a **contract check**
validates their output structure and provenance, not the truth of their results.

CR2 extends the CR1 format with verification history and linked revision and
candidate records. CR3 adds the registry and read-only freshness sweep; CR4 adds
the scope declaration, stopping-rule evaluation and guarded queue below. A clean index
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
The optional `scope` block is required for a sufficient-for-scope report (below).
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
policy change. Nonempty new rule identities are valid metadata; the sweep flags
entries differing from the scope's selected rules and excludes them from acceptance.

| Kind | Additional required fields and verdicts |
| --- | --- |
| `qualification` | `claim`, `validated_harness_sha256`; verdict qualified, shortfall, unqualified or insensitive. A shortfall also has `shortfall: {reason, reopen}`. The validated hash is the latest harness to which the cited diff/requalification chain carries the original qualification; the basis retains the original run harness |
| `result` | `claim`, `round`, `qualification` (entry ID), `qualified_evidence` (boolean); verdict PASS, FAIL or ERROR. Basis requires candidate and harness hashes. Q18's PASS has qualified_evidence: false |
| `observation` | `sections` (nonempty spec section list), `evidence_class: emulated`; verdict is a concise observation within the named runs, never a hardware conclusion |
| `item` | `class` is a nonempty string (R/E/W known; unknown treated as R), `source` integer 1/2/3, `target`, `disposition`; optional `aliases` for the same finding under another evidence key, `impact`, `execution`, `action` |
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

- Optional fields are `decision`, `cost`, `sequence` and `assessment` (CR4, below).
  `aliases` and `shortfall` are not verification fields.
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
three metadata files plus deployment settings and class definitions. It never
opens registered source paths, parses source content or diffs, hashes files,
invokes adapters or executes a harness. An explicit --target-spec reads only tag
definitions for manifest validation. Run the existing index
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

## Stopping report and queue (CR4)

**Terms:** a reading lineage is one reader's sequential fix passes, counted once
for independence; a batch is up to three proposed units of work, not an execution.
See the [glossary](../../GLOSSARY.md).

`scope` contains these required fields:

| Field | Meaning |
| --- | --- |
| `claims` | Nonempty list of claim IDs in this campaign's scope |
| `accepted_classes` | Mapping with exactly those claim IDs, each to a nonempty list of accepted evidence classes |
| `target` | Nonempty description of the device/environment and pin boundary |
| `rules` | Selected rule identity for each of qualification, result, verification and observation |
| `reader` | `{name, version}` of the last adopted reading role; the deployment manifest supplies the desired role |
| `evidence` | Public links supporting the scope declaration |

Run results currently carry emulated evidence only. A scope omitting `emulated`
cannot use their PASS to satisfy S2. A mandatory claim needs a current qualified
result linked to its current qualification, or a current shortfall approved by
the user. Stale shortfalls retain their reason/approval but do not count as current.

Revision headers may record `started` (ISO date). Revisions started through
2026-09-26 are historical for the cap; later revisions, or unknown dates, are
subject to it. Counts deduplicate section slices and count accuracy reading units,
including independent follow-up readings; numeric rounds provide a lower bound
when earlier attempts are missing. At round three, further reading/revision units
are held for the user; more than three is also a stopping-rule violation. The
orchestrator must also enforce C6's deletion/narrowing-only fixes after round two;
this metadata checker does not inspect text edits.

Verification entries may add `sequence` (positive integer, unique per reading,
identical across its slices) to order readings without guessing from entry order
or parsing dates out of IDs. `assessment` is a mapping containing
`accuracy_failures` (nonnegative integer), `r_items` (unique R-item IDs produced
by that reading), and `evidence` (public links for that classification).
These are explicit metadata assessments, never inferred from verdict prose.
Unknown current accuracy classifications block S3. S5 uses the latest independent
accuracy reading in sequence; any R it produced blocks S5 even after that R is
resolved. A missing sequence or assessment cannot establish S5.

S4 checks baseline requirements and every requirement-changing revision against
current landed accuracy coverage. The baseline uses the scope claims' citations;
later changes use header sections. A parent section covers a child, not conversely.
Readings must explicitly include each covered revision. Gates, adjudications,
drafts and stale slices do not count; all sequential passes count as at most one
lineage alongside independently recorded readers. Two lineages are required for
each requirement text. Enclosing section metadata is conservative: a reviewer
must confirm the reading actually covers those requirements before recording it.

The report does not compare verdicts across rules. `policy_changes` lists each
entry differing from the selected scope rule with `compared: false`; current
entries under a different rule prevent sufficiency. Historical policy identities
remain unchanged. `evaluation_policy` separately names C5's amended A1 standard,
which evaluates reading counts without rewriting or equating historical verdicts.

Items accept unknown nonempty classes; `effective_class` is R until resolved.
Optional `impact: {claims, changes_status}` declares whether an E item changes
a claim in scope. Missing impact on a spec or review E item is conservatively unresolved;
review items block S3 and report `impact unrecorded` until their impact is recorded.
explicitly no affected claims or no status change does not reopen the campaign.
Records findings are separate from spec items. Candidate R items do not assert
a spec error; `execution: carry` preserves the next-brief disposition without
starting an implementation round. W items never start a revision, regardless of
other metadata. A spec R/E shortfall requires explicit claim impact; any item
shortfall on a mandatory claim requires its own user decision.

Optional item `action` is one of requirement-change, implementation, hardware-run,
recall, adopt-source, accept-shortfall or outward-report. All are tier 2 and can
never be downgraded through caller-supplied tier data. Their own `decision` must
name `who: user`, a date and a resolvable public evidence link. No decision on
another item or a shortfall authorizes them. Unknown/malformed metadata fails
validation before batching. This is a record guard, not proof of the human's identity.

The queue contains stable campaign/kind/subject IDs, entry IDs, reasons, tiers,
states, and each unit's role and model from the deployment manifest. There is one requalification per
claim, one acceptance-set rerun per campaign, and one re-verification of affected
accuracy history against the current text. Contested hardware/emulator facts join
re-verification; rerunning an unchanged emulator cannot resolve that conflict.
Historical gate slices remain in
the freshness report but do not create work. Current readings that explicitly
cover an old reading's revisions and sections/dependencies discharge that stale
history from the queue without erasing it. Missing dependencies widen to that
reading's whole recorded section set. S4 still demands two independent lineages.

Unmet S4/S5 queues a second reading first, with its coverage gaps. A changed reader
role queues exactly one comparison reading for each campaign invocation, including
sufficient campaigns. The reference reader was Claude Fable 5.1 through CR6a; CR6 changed it to
Codex `gpt-6-astra` for its comparison reading, and the index's `scope.reader` stays the adopted
reader until that reading is adjudicated. Tests pin CR5's manifest and index as fixtures.
The manifest supplies the desired role.
Changing an unrelated registry model identity does not change that role.
After a reviewed comparison, record its verdicts and update the adopted `scope.reader`;
merely changing the manifest does neither. Repeated sweeps have no side effects.

Priority is second reading, comparison reading, re-verification, requalification
by claim ID, acceptance rerun, then other tier-1 work; authorized tier-2 entries
follow. `batch` is at most three IDs; `waiting` contains remaining ready IDs.
Unapproved tier-2 entries say `awaiting decision` and never enter either list.
The item's original disposition is preserved in `open_items`, not in queue units.
Missing scope holds the entire batch. Resweep
after every checkpoint; a batch is a proposal against this snapshot, not a lease
to ignore new findings or to adopt new source pins. No unit is executed here.

`stopping` adds `sufficient`, S1–S5 conditions, all blockers, coverage, latest
independent reading, cap findings, policy differences, open items, shortfalls,
historical stale IDs, reopening IDs, queue, batch and waiting IDs to sweep JSON.
The sweep's output is **JSON version 2**: `ok` and the exit code now describe
stopping sufficiency and ready work, changing CR3's version-1 contract. `fresh`
preserves CR3's former `ok`: true only when there are no stale/contested entries,
stale reference controls or unavailable identities. `fresh: false` can coexist
with `ok: true` when sufficient current coverage discharges stale history.
The three metadata input files remain version 1.
Exit 0 means sufficient with no ready work; exit 1 means blockers or ready work;
exit 3 still means unavailable required inputs. Historical stale records alone
do not prevent a sufficient campaign once current coverage replaces their use.

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
stale findings when any source is unavailable. Otherwise exit 1 means stopping
blockers, ready work or invalid metadata; exit 0 means sufficient with no ready work.
Both commands use exit 2 for usage errors and support `--skill`. No real sweep
or private adapter invocation is added to public CI; their synthetic tests run
with the existing campaign-review discovery command.

## Deployment manifest, version 1 (CR5)

The reference is [evals/deployment.yaml](../../evals/deployment.yaml). Both the
sweep and contract checker accept `--deployment PATH`; otherwise they read the
`deployment` key beside `run_store` in the user config located by
`utilities/run-store.py`. With no key, the reference applies. Relative config
values resolve beside the config file; explicit CLI paths resolve from the working
directory. An invalid configured manifest fails; it never silently selects the
reference. These commands do not write user settings.

The closed schema is `{version: 1, plugins: [...]}`. Entries have unique `id`
strings, `kind` and `via: skill:<name>`. Required additional fields:

| Kind | Fields | Meaning |
| --- | --- | --- |
| `source` | `command` | Nonempty argument list for the adapter entry point |
| `fixture` | `command` | Nonempty argument list for the fixture entry point |
| `producer` | `class` | Evidence class, without brackets |
| `role` | `agent`, `model: {name, version}` | Invocation mechanism and model identity; `id` is reader, implementer or reviewer |

All three roles are required. Model names and versions are nonempty strings;
the version is a recorded model identifier, not a claim that a service exposes
an immutable weight revision. The reference implementer uses CF-2's recorded
`gpt-6-astra` identifier for both fields. It does not authorize an implementation.
The queue assigns readings to reader, implementation to implementer, and other
units (including fixture/requalification work) to reviewer as the operating agent.
Every unit reports its `role` and corresponding `model`; tier-2 authorization
and batch guards still apply independently.

The `via` skill owns arguments, authentication and safety. Reference command
paths are relative to the repository root; a deployment documents its own command
working directory and arguments in that skill. Commands are declarations only:
neither checker nor sweep executes them or interpolates shell strings. No plugin
loader, scheduler, source-refresh executor or universal invocation wrapper is added.

Producer classes come from the provenance definitions in SPEC-FORMAT.md.
`--target-spec PATH` additionally reads the explicitly supplied spec's tag-table
rows (`| \`[class]\` | ... |`); prose mentions do not define a class. Thus
`kernel` passes with the e1000 spec's table, but is not globally promoted.
No filesystem search discovers private specs or plugins.

## Output contracts, version 1 (CR5)

From the repository root, capture an adapter's output and supply one existing
isolated run directory:

```bash
uv run --with pyyaml python3 skills/campaign-review/scripts/contract_check.py \
  --source-json adapter-output.json --run-dir isolated-run --json
```

With neither output flag, check only the manifest. With either or both, check
those artifacts as well. Missing inputs exit 3; structural findings exit 1;
usage errors exit 2; satisfied contracts exit 0. `--skill` describes the CLI.
When `--json` is requested, argument errors also return one JSON findings
document on stdout with exit 2 and no argparse prose; the sweep follows the
same rule. Invalid YAML syntax and construction (including invalid dates) yield
findings with exit 1, not a traceback.
The JSON report contains `version`, `ok`, `checks` and `findings`, and deliberately
omits source IDs, input paths, raw details and command strings. JSON duplicate
keys are rejected. The checker reads only metadata and never starts a guest,
opens the source bytes or changes a run directory.

### Source adapter

The JSON object requires `id`, `version`, `sha256`, `status`, `checked`, and
`provenance: {adapter, version, version_method}`. These reuse the registry's
validator: strings are nonempty, checked is an ISO date string, status is
`ok`, `blocked` or `unknown`, and hashes are full lowercase SHA-256 values.
An `ok` source must have a hash; blocked/unknown may use null. `matches_pin`
is optional and boolean or null. No content fields are accepted. The existing
pinned-file adapter's `{ok, result, updated, would_update, findings}` envelope
is also accepted; its `result` must satisfy the same identity contract.
Envelope success and matching a pin are separate from satisfying this contract.
A blocked, unknown or drifted observation may be structurally valid.

### Fixture backend

One directory contains `identities.json` and `verdicts.json`. The neutral
identity representation requires:

- `fixture: {name, version, sha256}` identifying the fixture or emulator;
- `harness_sha256`, `kernel_sha256`, `image_sha256`, all full hashes;
- `conditions`, a nonempty mapping including `scenarios: [one scenario name]`.

The native QEMU representation remains supported without changing the harness:
`qemu_version` and `sha256.qemu` identify the emulator; the sha256 mapping also
requires `harness:l02harness.py`, `harness:guest-init.sh`, `kernel`, `initramfs`
and `busybox`. Conditions are `driver`, `accel`, `scenarios` (one name),
`dut_mem`, `host_kernel` and `python`. Additional identity fields, such as
private `paths` and module hashes, are allowed but never echoed by the checker.

Verdicts use the existing `{overall, results}` structure. Each result requires
`scenario`, `verdict` and `checks`; each check has a nonempty `check` name and
either `verdict: PASS|FAIL|ERROR` or native QEMU `ok: true|false` (mapped to
PASS|FAIL). Names are unique within each scenario; result-group names are unique
within the directory. Results may contain only the declared scenario and the
reserved auxiliary/error groups below. Declaring a reserved name as the requested
scenario is invalid; adding an undeclared executed scenario is invalid even if it
passes. Both native QEMU and neutral backends use this rule:

| Reserved group | Required meaning and constraints |
| --- | --- |
| `trace` | Postprocessing for the executed scenario. If startup or collection failed before that scenario, only trace ERROR is valid. |
| `capture` | Capture postprocessing, requiring a result for the declared scenario. Native QEMU emits this only for smoke; neutral backends may capture any declared scenario. |
| `boot` | Startup failure: ERROR, no completed checks, no executed scenario or between-scenarios result. |
| `between scenarios` | Collection/infrastructure failure before or after the requested scenario: ERROR, no completed checks. The native harness uses this when guest-log collection fails. |

The requested scenario must appear unless boot or between-scenarios ERROR records
why it could not run. Trace/capture errors alone cannot justify its absence.
Neutral backends translate startup/collection failures to these same reserved
groups; arbitrary auxiliary names are not accepted.

Overall must agree with the worst result-group verdict. PASS groups need completed
checks and cannot hide failing checks; ERROR checks require ERROR groups. FAIL and
ERROR scenarios may have zero completed checks: the native harness records an
initial module-load guest failure as FAIL, and startup/infrastructure failures as
ERROR. These outcomes remain failures even when the metadata contract is valid.

Contract success means the output is interpretable, even when the driver FAILs
or the run ERRORs. It does not qualify any claim or prove physical isolation.
Raw artifacts remain in the original private run for review; the checker only
requires the two metadata files so the reduced CI fixture can use the same check.
Test fixtures omit every required provenance field in turn. Real isolation,
provenance truth, conditions' adequacy and raw-artifact completeness remain the
artifact reviewer's job. Producer observations and role session records follow
C8's conventions (tool/model identity, date, sandbox/audit and private transcript
locator); mechanical checks for them wait for a first private plugin.
