<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR3: tier-0 sweep

**Terms:** a sweep compares recorded identities and reports stale verdicts; a
qualification shows that a check detected an intended defect; a change map ties
reviewed section/check changes to exact file hashes. An adapter hashes opaque
files and returns metadata only. See the [glossary](../GLOSSARY.md) and
[registry format](../skills/campaign-review/INDEX-FORMAT.md#source-registry-sourcesyaml-version-1).

The existing differential result remains CF-2's rebuilt driver and reference
passing ten scenarios twice. CR3 ran no driver tests. Its real-index sweep flags
13 qualifications whose expected-outcome sections changed after their recorded
spec context, in addition to CR2's 83 historical stale readings. This does not
retract those runs or claim the driver failed; their qualification evidence needs
reconciliation with the later text before it counts as current.

Independent review is complete; its three fixes are implemented as decided by
the orchestrator. No second independent review or commit was performed. Checkpoint
remains with the orchestrator. No push, PR, model reading, spec edit or remote
action was performed by the implementer. Original private artifacts and the
independent review are in the supplied run `cr3-20260926-01`.

## Acceptance

| Criterion | Result |
| --- | --- |
| Registry covers the requested current identities | [19 sources](../evals/e1000/sources.yaml): manual; eight Linux files and their shared commit; QEMU package version/binary hash; guest kernel, BusyBox and candidate image; both harness files; candidate/reference modules; landed spec; compiler string |
| C8 reference adapter | [pinned_file_adapter.py](../skills/campaign-review/scripts/pinned_file_adapter.py) returns ID/version/hash/status/date and provenance, compares pins with the shared ENC28J60 `check_blob`, supports explicit writes and dry runs, rejects escapes, and never returns content |
| C2 detection and widening | [sweep.py](../skills/campaign-review/scripts/sweep.py): kind-to-rule dispatch, accumulated spec headers, hash-bound reviewed maps, section/document and check/scenario/harness widening, contested observations, preserved historical states |
| Synthetic change matrix | Nine rows below, exact expected sets asserted against copies of the real e1000 index; model and fixture rows mark nothing |
| Narrow and unmappable harness changes | One named check marks Q01 only; scenario mapping tested; missing/unreviewed/wrong-origin/unknown-name mappings widen; all widened cases reported |
| Recorded identities only | Missing compiler registration or null compiler basis cannot trigger; registered compiler changes do. The sweep's in-memory test raises if any source file or harness parser is opened |
| Stale entries cannot count as current | No stale/contested entry appears in `eligible` or its counts; this is only a freshness filter, not S1–S5 evaluation |
| Real-index sweep | 96 stale, 84 current, 13 superseded; every stale entry explained below; zero unmapped harness changes and zero unavailable registry observations |
| Orchestrator instructions | Skill says to refresh applicable identities and sweep at session start and after known input changes; CI runs synthetic tests, not the private refresh or real sweep |
| Housekeeping | CR1 complete at PR #29 and CR2 complete at PR #30 in their status lines, CR table and summary |

## Synthetic matrix

`matrix.json` contains the full expected and actual entry lists and nine `ok: true`
results. Reproduce with the test module's `--matrix` flag. The tests copy the real
index and give each active qualification a separate synthetic revision-8 basis
to isolate the single change being tested. They preserve original hashes,
claims, check mappings, historical states and candidate/reading records. This
normalization is test-only; it is not written to the campaign index. The 83
already-stale entries remain reported but are excluded from the delta below.

In this table, **results** means `result-Q01`–`result-Q28` plus the current
aggregate `candidate-CF2-a2` (29 entries), **qualifications** means
`qualification-Q01`–`qualification-Q28`, and **reading** means `verify-r8-round2`.

| C2 row and mutation | Newly stale | Newly contested |
| --- | --- | --- |
| Spec: revision 9 changes §5.3 and a driver requirement | qualification-Q01; reading (unknown dependencies); all results — 31 | — |
| Document: new manual hash, section mapping unavailable | reading — 1 | — |
| Reference/kernel: Linux source version changes | reading's kernel verdict — 1 | — |
| Harness: reviewed diff changes only `MAC matches QEMU's` | qualification-Q01 — 1 | — |
| Emulator: QEMU binary changes | EM1–EM8; all qualifications; all results — 65 | — |
| Candidate: candidate module changes | all results — 29 | — |
| Hardware: EM1 contradicted, Q01 explicitly uses it as premise | qualification-Q01 — 1 | EM1, with a conflict locator |
| Fixture: new fixture identity | none | — |
| Model: new model identity | none | — |

Additional assertions cover wording-only revisions, declared dependencies,
missing headers, parent section boundaries, mapped/unmapped manual citations,
manual-only readings surviving kernel changes, changed reference control run IDs,
guest kernel/image identities, and emulated-reading dependence on observations.
They also cover adapter write idempotence, dry runs, drift without pin adoption,
binary input, missing files, symlink escapes, duplicate keys, CLI exits/JSON and
unavailable dependencies. Existing index mutation tests continue to run unchanged.

## Real sweep and explanations

`real-sweep.txt` and `real-sweep.json` contain every entry and its reasons. Exit 1
is expected because findings exist; it is not a command failure. Summary:

```text
Counts: {"current": 84, "stale": 96, "superseded": 13}
Eligible records (not acceptance): {"candidate_round": 1, "observation": 8,
  "qualification": 15, "result": 28, "verification": 1}
Unavailable sources: none
Unmapped harness changes: none
```

The 84 current entries include 31 item records, excluded from eligible-verdict
counts. Qualified-evidence flags, shortfalls and reading independence still need
CR4's stopping-rule evaluation; these counts do not certify acceptance.

These are all 13 newly stale qualifications; the first applicable header supplies
`stale_since`, even when later revisions touched the same dependency again:

| Entries | Recorded spec context | First invalidation | Explanation |
| --- | --- | --- | --- |
| qualification-Q01 | revision 4 | spec-r6 | Expected outcome cites §5.3, changed in revision 6 (and again in 7) |
| qualification-Q02, Q03, Q11, Q12, Q13, Q14, Q15, Q16, Q17 | revision 4 | spec-r7 | Each expected outcome cites §10.3, changed in revision 7; revision 8 also touches §10.3 and some cite §5.9 |
| qualification-Q18 | revision 6 | spec-r7 | Cites §§4.1 and 5.2, both changed in revision 7; §5.2 changes again in 8 |
| qualification-Q24, Q26 | revision 6 | spec-r7 | Both cite §10.3, changed in revision 7 and again in 8 |

The harness's validated-hash carry-forward does not carry the expected outcome
forward across spec edits. CR3 does not invent that missing reconciliation or
silently relabel the index. This is a conservative freshness finding, not proof
that the qualifying defect must be rerun unchanged.

The independent reviewer checked the named public evidence and found later
candidate acceptance and harness carry-forward records, but no renewal of these
13 qualifications against the later spec text. They are supported reconciliation
findings, not false positives. Carry all 13 into CR4 as inputs for its tier-1
queue: Q01; Q02, Q03, Q11–Q17, Q24, Q26; and Q18. CR4 must account for their
expected-outcome dependencies; no qualification was renewed or rerun in CR3.

These are all 83 preexisting stale verification entries, grouped by `reading_id`.
Every slice of each listed reading is stale; their exact IDs remain in the JSON
and the status index. Their reason is already recorded by CR2: later revisions
touched a reading or an unknown dependency, so the whole revision widens.

| Reading IDs | Entries | Existing stale-since |
| --- | --- | --- |
| verify-r3-A, verify-r3-B, verify-r3-acceptance, verify-r3-transfer | 10 each, 40 total | revision-4 |
| verify-r3-adjudication | 1 | revision-4 |
| verify-r4-AF1 | 11 | revision-5 |
| verify-r5-round2 | 3 | revision-6 |
| verify-r6-SR7 | 12 | revision-7 |
| verify-r6-round4 | 10 | revision-7 |
| verify-r7-round6 | 6 | revision-8 |

The sweep preserves those reasons and dates, adds relevant current comparisons,
and never resurrects a stale reading because another hash happens to match.

## Identity and mapping limits

The adapter rehashed five available files: landed revision-8 spec, candidate
module, candidate a2 image, harness Python file and guest-init script. All matched
their recorded pins. `adapter-observations.json` contains their metadata only.
The other 14 entries are explicitly labeled `recorded-pin`: historical public
L02a pins or CF-2 execution identities. The manual and Linux source bytes are not
available in their supplied local run; QEMU, guest kernel/BusyBox and reference
module identities remain snapshots, not live remote probes. The exact compiler
build remains unknown (`gcc-14`, no binary hash). No private source was parsed.
An operator must supply refreshed identities to detect subsequent host changes.

No actual harness difference needed mapping in this run: the current file is
exactly the validated CS-1 hash. The implementation takes reviewer-confirmed diff
metadata rather than parsing diff/source content. The map must cover the entire
old-to-current diff; the test's named-check change is synthetic. Shared helpers,
deleted/renamed checks and incomplete mappings cannot safely be assigned to a
nearby check. The scenario or whole-harness fallback is the supported answer;
`unmapped_harness` reports whole-harness fallbacks. There are no outstanding
real harness diffs claimed to be mapped.

Reference controls are run IDs projected from the claim map because the index
does not have a control-entry kind. Hardware contradictions are supplied by the
operator with a §12 conflict locator; the sweep reports the record to carry into
the spec and makes no spec edits. No stopping rule, queue, deployment manifest,
service, or automatic source-edition adoption was added.

## Verification

Original commands, output and exit codes are retained in `VERIFY.txt`. Review-fix
verification is retained in the implementer's temporary scratch artifacts because
the run directory is read-only in this follow-up sandbox. Required uv commands
use an existing temporary offline cache. The first attempted temporary cache lacked
PyYAML; switching to the previously populated offline cache resolved that. No
project dependency or machine configuration was changed. Multi-file Pyink workers
stalled in this sandbox; each file completed when formatted separately.

| Check | Output |
| --- | --- |
| `uv run --with pyyaml python3 -m unittest discover -s skills/campaign-review/tests` | 56 tests, OK after review fixes; exit 0 |
| `uv run --with pyyaml python3 -m unittest discover -s evals/enc28j60/tests` | 105 tests, OK; exit 0 |
| `uv run --with pyyaml python3 skills/campaign-review/scripts/index_check.py evals/e1000` | OK: 28 claims, 28 qualification, 28 result, 8 observation, 31 item, 95 verification, 3 candidate_round; exit 0 |
| `uv run --with pyyaml python3 skills/campaign-review/tests/test_sweep.py --matrix` | Nine exact expected sets, all true; exit 0 |
| `uv run --with pyyaml python3 skills/campaign-review/scripts/sweep.py evals/e1000` (also `--json`) | 96 stale, 84 current, 13 superseded; exit 1, explained above |
| Privacy checker, including explicit untracked public files | Clean |
| Requested diff privacy grep, including untracked public files | No hits |
| `git diff --check` and untracked whitespace check | Clean |
| Pyink per changed Python file; Pylint | Clean; exit 0 |
| Portability scan on campaign-review scripts | 0 findings; exit 0 |

## Review

A read-only Codex reviewer, `gpt-6-astra` (identified by the orchestrator), reviewed
the diff, C2 rules, matrix and real-sweep artifacts. Its report is
`codex-review-cr3.md` in run `cr3-20260926-01`. It recommended holding CR3 for three
medium findings. All three fixes below were decided by the orchestrator.

| Finding | Disposition |
| --- | --- |
| R1, medium: observations already contested in the index did not invalidate dependents without a registry contradiction | Fixed, decided by the orchestrator: after applying registry contradictions, propagate from every effectively contested observation using the same premise/section/dependency rules. The reproduction marks EM1 contested in the index, gives Q01 that premise and tags the current reading emulated; both dependent entries now become stale without a registry contradiction. Unknown contention dates use the index observation locator, not an invented date. |
| R2, medium: a null artifact hash with status ok was treated as available | Fixed, decided by the orchestrator: require a full SHA-256 for every hash-compared source marked ok. Invalid combinations produce JSON findings and exit 1 in both CLIs. The version-compared compiler exception remains; model and fixture changes remain non-invalidating. Tests cover every source kind and the reviewer's null candidate/new-version reproduction. |
| R3, medium: non-scalar kind, status or file.root raised TypeError and broke JSON output | Fixed, decided by the orchestrator: validate each as a nonempty string before set membership. Tests run both CLIs with kind: [], status: {} and file.root: []; all six cases produce a JSON error document, exit 1 and no traceback. |

The new reproduction tests failed before the fixes and pass afterward. The
reviewer also confirmed the nine-row matrix, real sweep, metadata-only boundary,
relative registry paths and compatibility of the shared ENC28J60 pin logic.
Its public-evidence review supports all 13 qualification reconciliations as CR4
tier-1 queue inputs, as recorded above. No requalification was performed.

The reviewer's uv invocation could not create its cache lock in the read-only
sandbox; full unittest discovery encountered 36 temporary-directory errors,
while its 16 tests without that requirement passed. Those were review-environment
limitations. The implementer's post-fix run passed all 56 campaign tests and 105
ENC28J60 tests, plus the matrix and required checks. No second independent review
was performed; checkpoint remains with the orchestrator.

## Implementation decisions

- Keep the sweep read-only and separate refreshes into the adapter: source bytes
  and state writes stay outside the metadata comparison engine.
- Import unavailable identities as explicitly attributed historical snapshots:
  the registry can compare known pins without pretending to have probed the host.
- Keep expected and observed hashes separate, and require explicit adapter writes:
  detecting drift must not adopt a new manual edition or erase the approved pin.
- Require reviewed, exact old/new hash maps for narrowing: source content alone
  cannot prove every semantic dependency of a changed harness helper.
- Store source citations and observation premises in registry metadata: existing
  immutable historical bases remain unchanged; absent detail widens conservatively.
- Compare qualification harnesses at their validated hash, and spec contexts at
  their original revision: they record different carry-forward evidence.
- Scope the candidate image to its recorded basis: module-specific generated
  images cannot be compared as if every defect/control run used the same bytes.
- Invalidate run verdicts when a recorded compiler string changes: this makes the
  toolchain identity useful while preserving C2's unrecorded-input limitation.
- Report reference controls separately and carry conflict locators in the report:
  the existing index has no control-run entry kind, and CR3 cannot edit a spec.
- Preserve stale history and expose only freshness eligibility: C2 forbids stale
  acceptance, while S1–S5 and the execution queue belong to CR4.
- Normalize qualification spec contexts only in matrix copies: one row then tests
  one input change independently of the real campaign's already-stale context.
- Use the supplied implementation run ID: the orchestrator already established
  its writable artifact directory; no second run or checkout was created.
