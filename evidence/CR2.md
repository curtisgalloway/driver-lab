<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR2: spec verification history and the TNCRS revision chain

**Terms:** a reading is one verifier's pass; a section slice is the part of its
scope later revisions can invalidate separately. A basis records the identities
behind a verdict. An R item changes a driver requirement. TNCRS is the transmit
counter whose counts revision 8 attributes to the previous duplex sample.
See the [glossary](../GLOSSARY.md) and
[index format](../skills/campaign-review/INDEX-FORMAT.md).

The recorded differential result remains CF-2's: the rebuilt candidate and
reference each passed all ten scenarios twice on the final harness. CR2 links
that result to the requirement change and its readings; it ran no driver tests
and performed no new spec verification. The emulator cannot test TNCRS attribution
across a duplex change. Its PASS remains narrower than hardware verification.

The independent review ran; its five fixes are implemented, as decided by the
orchestrator. No second independent review or commit was made. Implementation records are in the supplied run
`cr2-20260926-01`; historical artifacts retain their original run IDs.

## Acceptance and traceability

| Criterion | Implementation |
| --- | --- |
| Every landed revision, 3–8 | Six revision headers, exact landed hashes and eleven distinct draft hashes; 22 recorded reading units represented by 95 section entries |
| Basis and scope | Every reading has sections, evidence classes, a verifier/model, round, original A1 policy, public evidence and run ID; unsupported dependency reconstructions withdrawn to unknown, with whole-revision widening |
| Preserve history | Draft verdicts stay superseded and retain their input hash; independent readings remain separate; no legacy record converted |
| C1 claims and open items | CR1's 28 claims, 28 qualifications, 28 current per-claim results, eight observations and 27 items retained without edits; four applied R items added to bind requirement-changing revisions |
| C5 worked chain | CF-1 finding → revision-8 requirement-change header → SR-8 readings → CF-2 a1 → CF-2 a2 → CR1's 28 results |
| Checker | Rejects missing revision coverage, wrong text hash, incomplete or inconsistent section slices, missing reader identity, and broken applied-item, reading or result links |
| Independent review | Read-only Codex reviewed all 95 entries; five orchestrator-decided fixes applied, including a [43-entry public provenance extract](CR2-provenance.md); no second independent review |

The [index](../evals/e1000/status.yaml) is the status record. These are reading-unit
locators for the reviewer; verdict totals belong to units, never to their slices.
`-s<section>` and `-remainder` suffixes partition a landed reading when a later
revision touched some of its sections. Drafts replaced as a whole stay unsplit.

| Text revision | Reading IDs (before slice suffixes) | Units / entries | Public evidence and original run |
| --- | --- | --- | --- |
| 3 | `verify-r3-transfer`, `verify-r3-acceptance`; `verify-r3-A`, `verify-r3-B`, `verify-r3-adjudication` | 5 / 41 | [L02b](L02b.md#process-and-results), `e1000-l02b-20260923-01`; [L02c](L02c.md#process-and-results), `e1000-l02c-20260924-01` |
| 4 | `verify-r4-L02c`, `verify-r4-AF1` | 2 / 12 | [L02c](L02c.md#process-and-results), `e1000-l02c-20260924-01`; [AF-1](AF-1.md#the-two-readings-compared), `af1-20260925-01` |
| 5 | `verify-r5-round1`, `verify-r5-round2` | 2 / 4 | [L02s](L02s.md#process), `e1000-l02s-20260925-01` |
| 6 | `verify-r6-round1` through `round4`; `verify-r6-SR7` | 5 / 25 | [L02f3](L02f3.md#review-of-the-spec-changes), `e1000-l02f3-20260925-01`; [SR-7](SR-7.md#the-readings-of-revisions-5-and-6-compared), `e1000-sr7-20260926-01` |
| 7 | `verify-r7-round1` through `round6` | 6 / 11 | [SR-7](SR-7.md#method), `e1000-sr7-20260926-01` |
| 8 | `verify-r8-round1`, `verify-r8-round2` | 2 / 2 | [SR-8](SR-8.md#method), `e1000-sr8-20260926-01` |

Revision 3 has two full independent accuracy readings, a one-claim adjudication,
and two gates; the gates do not count as accuracy readings. L02c's revision-4
reading used a draft, not the landed hash. AF-1 read the landed revision and
independently checked the citation correction, but omitted the first reading's
G1-through-§5.10 every-open claim. The two verdict summaries are not interchangeable.
SR-7's combined reading covers revision-5 and revision-6 changes on the revision-6
hash; it is not another reading of the exact revision-5 file. Its 83 verdicts are
recorded once as a unit. Public evidence supplies all verdict totals and resolutions.

The current revision-8 reading covers changed claims in §§1, 4.7, 5.2, 5.5, 5.9,
10.3, 12.1, 12.2 and 12.6. It reports 68 PASS and one UNVERIFIABLE (the additional
micro-sign PDF check), with no FAIL. It does not certify every sentence of those
sections. The earlier landed readings remain historical and conservatively stale:
revision 8 changes §1's convention and other shared dependencies, while the older
unrecorded dependencies require whole-revision widening. Stale does not retract
a historical verdict or the public evidence's carry-forward reasoning.

## The SR-8 → CF-2 chain

1. `CF-1-TNCRS` aliases `CF-1-A-F5` and `CF-1-C-F1`, the same spec gap also filed
   by the implementer. Its basis is CF-1 a1's revision-6 candidate. It is R/source 1,
   applied to revision 8; its decision links the user's choice in
   [SR-8](SR-8.md#the-rule-as-revision-8-writes-it).
2. Revision 8's header marks a requirement change and links this item. Its landed
   hash is `e0f17ffa443d50e6ca97c918cd23adedd71cbe1b92857d4aae4e4d693e6326d7`.
   The other three applied items are SR-7's wording findings. Revision 7's header
   explicitly says no requirement change.
3. `verify-r8-round1` retains its draft hash and 50 PASS / 3 FAIL / 1 GAP.
   `verify-r8-round2` supersedes it and binds the landed hash, with 68 PASS /
   0 FAIL / 1 UNVERIFIABLE. These are sequential readings, not two independent
   readings of the final text.
4. `candidate-CF2-a1` links the applied R item and landed reading and supersedes
   `candidate-CF1-a1`. CF-2's implementation review confirms the rule's four code
   locations; its traces show the predicted reading changes. The a1 acceptance
   summary is 40/40 runs, 944 checks, zero failed.
5. `candidate-CF2-a2` supersedes a1 on the new harness, using the same candidate:
   40/40 runs, 972 checks, zero failed. It links `result-Q01` through `result-Q28`
   without copying their verdicts. Q18 remains an unqualified observation; the
   other 27 results retain CR1's qualification limits.

Historical candidate aggregates have no newly synthesized per-claim results.
Their public evidence and original run IDs retain the details. No acceptance
result in this chain qualifies the unobservable duplex transition behavior.

## S4 finding

**Confirmed:** revision 8's changed TNCRS requirement has only one reading of its
final text after sequential fixes. The design's S4 failure is supported by the
entries. Revision 7's wording/evidence changes do not require a second reading
under the amended A1 policy, although their original records remain A1-as-written.

**Qualification to the worked example:** the stronger statement that just one
additional TNCRS reading establishes sufficiency is not demonstrated by this
backfill. [AF-1](AF-1.md#limitations) explicitly retains a first-reading claim
without a second line (G1 through §5.10); no supplied later evidence records its
closure. Conservative dependency widening also leaves older entries stale rather
than mechanically establishing inherited section freshness. A later stopping-rule
evaluation must resolve these coverage limits before asserting that TNCRS is the
only remaining blocker. CR2 neither re-verifies the claim nor silently treats it
as covered. DESIGN.md is unchanged.

## Recovery limits and decisions

- Public evidence provides landed hashes, verdict summaries, scope descriptions,
  independence and run IDs. Full draft hashes and SR-7/SR-8 reader model versions
  were recovered from verification frontmatter only; those full identities were
  not all independently traceable from the older public files. The review fix
  publishes the recoverable metadata in [CR2-provenance.md](CR2-provenance.md),
  cited by each affected entry. No spec body or driver source was read, copied
  or re-verified.
- L02c's individual A/B and third-reader records are not present in the supplied
  local run. The retained merged frontmatter confirms the revision-3 identity;
  the public process table supplies the individual verdicts. L02b's gate records
  were not inspected. Neither gate is counted as accuracy verification.
- The earlier dependency lists were reconstructed section-ID unions, not complete
  declarations in the briefs. They are withdrawn to null; C2 therefore widens to
  the whole revision. The provenance extract records that uncertainty for each
  affected entry. Section scopes and evidence classes are explicitly labeled
  metadata mappings, not new verdicts; revision 4's unsupported standard class
  is removed. Enclosing sections are used where the record is coarser.
- The old format has no numbered header section: header and scan assertions stay
  in a reading's summary and scope, not in invented spec section numbers.
- Revisions 4–6 have reconstructed requirement-change declarations and aggregate
  applied R items, based on L02c's corrections, L02s's PSCON change and L02f3's
  driver rules. This conservative classification prevents unchanged-candidate
  conformance from being assumed. Revisions 7 and 8 explicitly declared their
  requirement-change status in the original evidence.
- CF-1's full candidate and image identities came from its run identity record;
  public evidence publishes only abbreviated candidate identities. The exact
  compiler version remains unrecovered; the implementer is `gpt-6-astra`, as
  [CF-1](CF-1.md#round-1-the-update-and-its-checks) explicitly records. Historical CF-2 rounds reuse
  CR1's existing bases; those identities were not changed.
- One reading ID joins section slices so comparisons cannot count slices as
  independent readings. Hash-addressed drafts preserve failed attempts without
  assigning their verdicts to corrected text. These decisions keep the record
  traceable while preserving C2's conservative invalidation rule.
- All historical reading policies remain A1-as-written. The amended A1 rule is
  an evaluation policy for later work, not a retroactive alteration of verdicts.
- The supplied implementation run ID is used as requested rather than creating
  another run to match the plan's default naming convention.

## Verification

The original implementation commands are recorded in `VERIFY.txt` in run
`cr2-20260926-01`. The table below is updated for the review fixes; their command
output is retained in the implementer's scratch log for the orchestrator. The
required uv commands use an existing temporary offline cache; no project
dependency or machine configuration was changed.

| Check | Output |
| --- | --- |
| `uv run --with pyyaml python3 -m unittest discover -s skills/campaign-review/tests` | 30 tests, OK; exit 0 |
| `uv run --with pyyaml python3 skills/campaign-review/scripts/index_check.py evals/e1000` | OK: 28 claims, 28 qualification, 28 result, 8 observation, 31 item, 95 verification, 3 candidate_round; exit 0 |
| `python3 utilities/check-no-private-paths.py` | OK: 246 tracked files, no absolute home paths; exit 0 |
| Privacy checker on all three new public files | No absolute home paths; exit 0 (explicit paths, not yet tracked) |
| `git diff --check`; separate new-file whitespace check | Clean |
| Requested diff privacy grep, including all three new public files | No hits; grep exit 1 |
| Pyink on each changed Python file; Pylint | Clean; exit 0 |
| Portability scanner on campaign-review scripts | 0 findings; exit 0 |

The mutation tests cover missing revision headers and readings, wrong landed or
draft hashes, attempts to mark a draft current, unknown evidence classes, absent
reader models, gates misclassified as accuracy, missing/overlapping/inconsistent
section slices, unsupported current status with unknown dependencies, and broken
R-item, reading and result links. The real-campaign assertions bind the six-revision
range, 22 reading identities, current revision-8 reading and CF-2 chain. The
checker still does not validate the truth of a verdict, Markdown fragment anchors,
private artifact availability, or sufficient-for-scope status.


## Review

A read-only Codex reviewer (`gpt-6-astra`, identified by the orchestrator) reviewed
all 95 verification entries across 22 reading units. Its report is
`codex-review-cr2.md` in run `cr2-20260926-01`. It confirmed the six landed hashes
against public evidence, the recorded SR-8 → CF-2 chain, and the S4 qualification,
and recommended changes before landing. Its 43-entry exception list identified
public provenance gaps and the adjudication's evidence-class error.

| Finding | Disposition |
| --- | --- |
| R1, high: private metadata prevented public tracing (H/D/M/S) | Fixed, decided by the orchestrator: publish one sanitized row for each of the 43 listed entries in CR2-provenance.md and cite it from the entry. Recoverable hashes/models/scopes are explicit; reconstructed dependency unions are withdrawn to null with whole-revision widening. Revision 4's class mapping is explained and its unsupported standard class removed. |
| R2, medium: applied spec items could point to nonexistent revisions | Fixed, decided by the orchestrator: every applied spec item's destination must exist and list the item. Regression tests reject both SR-8-1 → 999 and a new applied R item → 999, plus existing destinations that omit either item. |
| R3, medium: CTRL.FD adjudication inherited full-reading evidence classes | Fixed, decided by the orchestrator: verify-r3-adjudication now records only databook, matching L02c's Table 13-3 adjudication. |
| R4, low: CF-1 implementer model marked unknown | Fixed, decided by the orchestrator: cf1-a1 records gpt-6-astra using the CF-2 name/version convention; only the exact compiler version remains unresolved. |
| R5, low, extra probe: verification entries accepted undefined optional fields | Fixed, decided by the orchestrator: permit only common decision/cost optional fields on verification entries; regression tests reject otherwise valid aliases and shortfall mappings. |
| Completeness probes: deleting a landed reading, predecessor/result links or all candidate rounds could pass the checker | No change, decided by the orchestrator: specific real-campaign assertions remain the boundary; a general completeness proof is beyond CR2. |
| Review unittest discovery: 27 setup errors | No change, decided by the orchestrator: the reviewer's read-only sandbox prevented temporary-directory creation, so assertions never ran; this was not a code defect. |

The reviewer also ran the real checker and the real-campaign assertion directly,
both successfully, and reported clean privacy and whitespace checks. The
implementer reran the required checks after the fixes. No second independent
review was performed; the checkpoint remains with the orchestrator.
