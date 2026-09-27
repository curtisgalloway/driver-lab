<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR4: stopping rule and guarded queue

**Terms:** sufficient for scope means that S1–S5 and freshness hold for the
declared claims; a qualification shows that a check detected its intended defect;
a lineage is one reader's sequential passes counted once for independence.
Tier 1 is standing review work; tier 2 needs a recorded user decision.
See the [glossary](../GLOSSARY.md) and
[format](../skills/campaign-review/INDEX-FORMAT.md#stopping-report-and-queue-cr4).

The differential result remains CF-2's rebuilt driver and reference passing ten
scenarios twice. CR4 ran no drivers, spec readings or queued units. Its metadata
report says **not sufficient for scope**: 13 qualifications need reconciliation,
two review items have unrecorded impact, and current independent reading coverage
is incomplete. This does not retract
the recorded differential runs or assert that the driver failed.

Independent review completed; its eight retained findings are fixed as decided
by the orchestrator. No second independent review, commit, push or pull request
was performed by the implementer. Original private command/output artifacts
are in run `cr4-20260926-01`; paths below that run are relative to the run store.
The review-fix sandbox cannot write that run directory; new artifacts are in
temporary scratch storage for the orchestrator to retain.

## Acceptance

| Criterion | Implementation / artifact |
| --- | --- |
| Scope and S1–S5 | `status.yaml` declares 28 claims, accepted classes and emulated target; `stopping.py` evaluates current evidence, shortfalls, open accuracy findings, independent coverage and latest independent reading |
| Every open item classified and disposed | Report includes 14 open/shortfall items and preserves their dispositions; unknown classes become R; records findings stay separate |
| W never starts a revision; E only for status impact | Explicit impact metadata; conservative missing-impact handling; tested no-op and reopening cases |
| Three-round cap | Distinct accuracy readings, numerical round lower bounds and start dates; historical overruns retained, later/unknown-date round three holds further readings for a person, and overruns block sufficiency |
| Policy comparison guard | Different rule identities are reported with `compared: false`, excluded from selected-policy acceptance, and current differences block sufficiency |
| C2 matrix produces covering units | All nine existing matrix rows also assert exact unit-kind sets and coverage of every newly stale/contested entry |
| Tier-2 and batch guards | Every tier-2 action tested with missing, operator and user decisions; separate selection guard rejects a forged ready entry; fourth ready unit waits |
| Reader change | One comparison per campaign, including a synthetic sufficient campaign; unrelated registry model changes invalidate nothing |
| Annotations and workflow | A1 links the approved C5 amendment; AGENTS.md and skill require the session-start sweep, bounded batches and explicit push authorization |
| Scope exclusions | No manifest, scheduler, source adoption, spec edit or queued execution; independent review supplied by the orchestrator |

## Real report and differences from the worked example

The [status index](../evals/e1000/status.yaml) remains the item/status record.
The review-fix `real-sweep.json` and `real-sweep.txt` retain the full report, including every
blocking ID and all queue coverage. The freshness totals remain 96 stale,
84 current and 13 superseded; CR4 changes their interpretation, not their states.

| Condition | Result and reason |
| --- | --- |
| S1 | Met: all 28 mandatory claims, six permitted evidence classes per claim, emulated 82540EM at registry identities |
| S2 | Unmet: Q01, Q02, Q03, Q11–Q18, Q24 and Q26 have stale qualification context; Q18's approved unobservable shortfall is retained but cannot count as current |
| S3 | Unmet: AF-1-reading-coverage and SR-8-independent-reading have unrecorded impact. They are unresolved E review items, not established no-impact findings; carried candidate R and records findings remain separate |
| S4 | Unmet: baseline revision 3 and requirement changes 4, 5 and 6 have zero current independent lineages after conservative widening; revision 8 has one |
| S5 | Met: the most recent independent re-reading is `verify-r6-SR7`; its three form/citation findings produced no R item, supported by SR-7. This historical outcome does not make its stale coverage current |

Each difference from the design's worked example:

1. **S2 also blocks.** CR3's validated finding of 13 stale qualifications is
   carried forward. Q18's approval is not erased, but the changed expected-outcome
   context must be reconciled before that shortfall is current again.
2. **S4 is broader than TNCRS.** CR2 expressly did not prove that one additional
   TNCRS reading establishes sufficiency. Unknown older dependencies widen to the
   whole reading. AF-1's missing second line for the every-open claim remains
   covered by the revision-4 deficit; no new closure is invented.
3. **The queue has 17 tier-1 units, rather than one.** The second reading covers
   declared S4 gaps on the current text; one re-verification covers 63 stale
   accuracy slices; two re-verifications reconcile the review items' unrecorded
   impact; 13 per-claim units reconcile qualifications. The 20 stale
   acceptance/transfer gate slices remain history, not accuracy work. New current
   readings can discharge old accuracy history without rewriting those records.
4. **Two outward-reporting decisions are visible.** A-RR-4 and QF-1-F1-upstream
   are listed at tier 2, awaiting their own decisions; neither enters the batch.
5. **Historical round totals are explicit.** Revision 7's six readings predate
   the cap. Revision 6 has five accuracy reading units: four sequential rounds
   plus SR-7's independent follow-up. Both are historical, not new violations.
6. **S3 also blocks after F2's fix.** The original CR4 report incorrectly treated
   missing review-item impact as no status change. The two unresolved items now
   explicitly report `impact unrecorded`; no impact declaration was invented in
   the public index to preserve the earlier verdict or queue.

The first batch, in order, is `e1000:second-reading:current`,
`e1000:re-verification:AF-1-reading-coverage`, and
`e1000:re-verification:SR-8-independent-reading`. The unchanged deterministic
ordering puts these item IDs before `current` within the re-verification kind.
The historical-accuracy re-verification and all 13 qualification units now wait
(14 units), rather than the original 12 qualification units. Re-sweep after each
checkpoint, since a finding or newly recorded
coverage can change later work. CR6 owns execution; no unit was started here.

## Open items

The report preserves the index's classes and dispositions rather than replacing
them with queue membership:

- W: SR-8-1/2/3 and A-RR-1 ride the next spec revision; SR-8-4 goes to records
  maintenance; CF-2-RLEC-comment rides the next implementer brief.
- E: CF-2-AR-10 has no claim-status impact and rides the next spec revision;
  A-RR-4 and QF-1-F1-upstream await outward-reporting decisions;
  AF-1-reading-coverage and SR-8-independent-reading retain their review
  dispositions, with their unrecorded impact now blocking S3 and explicitly
  represented in the derived reading queue.
- R: A-RR-7 stays in the next implementer brief without a standalone round.
- Shortfalls: HF-1 is E/out of scope, reopened by the hardware fixture; recall-r3
  is E/out of scope, reopened by scope widening or authorized remeasurement.
  Mandatory Q18 remains unobservable, user-approved, reopened by hardware or a
  timing-capable tool; its freshness reconciliation is separate from accepting
  a new shortfall or starting hardware work.

## Verification

Command output and exact exits are recorded in the private run's `VERIFY.txt`;
`verification.json` indexes the commands and their separate artifacts. The
earlier pass is retained in `VERIFY-initial.txt`. Required uv commands use the
existing offline cache; no dependency or machine configuration was changed.
Review-fix commands and output use the same artifact names in temporary scratch
storage because the original run directory is read-only this turn.

| Command/check | Output |
| --- | --- |
| `uv run --with pyyaml python3 -m unittest discover -s skills/campaign-review/tests` | 81 tests, OK after review fixes; exit 0 |
| `uv run --with pyyaml python3 skills/campaign-review/scripts/index_check.py evals/e1000` | OK: 28 claims, 28 qualification, 28 result, 8 observation, 31 item, 95 verification, 3 candidate_round; exit 0 |
| `uv run --with pyyaml python3 skills/campaign-review/tests/test_sweep.py --matrix` | Nine rows, all `ok: true`, including exact unit kinds and affected-entry coverage; exit 0 |
| `uv run --with pyyaml python3 skills/campaign-review/scripts/sweep.py evals/e1000` and `--json` | Not sufficient: S2/S3/S4 unmet; 17 tier-1 units, two tier-2 decisions; JSON version 2, `fresh: false`, `ok: false`; exit 1 as expected |
| `python3 utilities/check-no-private-paths.py` | 260 tracked files, no absolute home paths; exit 0 |
| Privacy checker on untracked public files; requested diff privacy grep | Clean; grep exits 1 because there are no matches |
| Pylint on all changed Python files; Pyink formatting | Clean; exit 0 |
| Portability scan on campaign-review scripts | Zero findings; exit 0 |
| `git diff --check` and untracked whitespace check | Clean |

## Decisions and limits

- Use a separate pure `stopping.py` over the existing sweep result: freshness and
  qualification/reading policy have different jobs, with no duplicate invalidator.
- Extend format version 1 additively with optional scope/assessment metadata:
  historical fixtures remain readable, but absent scope cannot pass S1 or batch work.
- Accept nonempty new rules and unknown classes as data: policy differences are
  reported instead of rejected, while an unknown class is conservatively R.
- Declare all six existing evidence classes for e1000: they are the spec's accepted
  classes, while run PASS is explicitly limited to emulated evidence.
- Use Claude Fable 5.1 as the interim desired reader and adopted role: it is the
  latest recorded reader, so no fictitious model-change trigger is introduced.
- Add explicit reading sequence and evidence-backed assessments for SR-7 and SR-8:
  free-text verdicts cannot safely distinguish accuracy errors from wording findings.
- Require current coverage for baseline and each requirement-changing header:
  CR2's stale history and documented coverage exception cannot establish sufficiency.
- Keep S5's historical outcome separate from S4's freshness: “produced no R” is
  about the last independent reading, not a claim its dependencies remain unchanged.
- Count independent follow-ups as verification rounds: the cap says rounds regardless
  of finding class; start dates keep pre-cap history from becoming a violation.
- Group stale accuracy records into one current-text reading, omit old gates, and
  reconcile qualifications individually: the work stays reviewable without replaying
  obsolete revisions or conflating independent per-claim evidence.
- Route contested hardware/emulator facts to re-verification: unchanged emulated
  results cannot resolve a hardware conflict; stale emulator observations still rerun.
- Prioritize the second reading, then re-verification, then claim order: this retains
  the design's first unit and exposes spec findings before qualification work.
- Preserve explicit candidate carry dispositions and classify outward reports as
  tier 2: a queued item alone does not authorize an implementation or publication.
- Make no new shortfall approval or spec closure: Q18's existing approval survives,
  but its stale basis is not silently renewed.
- Keep decisions bound to their own item and allow only fixed tier-2 action kinds:
  unrelated approvals and arbitrary tier metadata cannot authorize work.
- Reserve schema/evidence truth for review: links validate file existence, not human
  identity or semantic completeness; no code parses the private spec or transcripts.

The source registry's recorded-pin limitations from CR3 still apply; no sources
were refreshed in CR4. The checkpoint remains with the orchestrator.

## Review

The orchestrator supplied a `review-swarm` with seven Claude reviewer arms:
security, correctness, compatibility, documentation, history, conventions and
performance. All seven completed. All ten candidate findings passed the quote
check; the referee retained eight and dropped F4/F5. F4 restated the deliberate,
documented missing-scope block; F5 restated the deliberate, documented explicit
claim-impact requirement for spec shortfalls. Both hypothetical compatibility
concerns were already addressed by migrating e1000, the existing index, in this
change. The referee reduced F3 from medium to low because the semantic change
was deliberate and documented; the missing output-version change remained.

The table and per-arm JSON are in `review-swarm/` under run
`cr4-20260926-01`. Locations below identify the reviewed lines before fixes.
Documentation-only fixes were checked against the final source and
Markdown text; they do not add tests that merely duplicate prose.

| Finding / severity / reviewed location | Disposition and coverage |
| --- | --- |
| F1, medium — `index_check.py:735,804` | Fixed, **decided by the orchestrator**: both history checks treat any class outside E/W as R. `test_unknown_applied_class_is_a_requirement_in_history` accepts an unknown-class applied item through the requirement header and linked candidate rounds, then rejects a header claiming no requirement change. |
| F2, low — `stopping.py:212–217,289–295` | Fixed, **decided by the orchestrator**: absent impact on review E items blocks S3, queues reconciliation and reports `impact unrecorded`. `test_review_e_without_impact_is_unresolved` checks both real item IDs; `test_real_blockers_and_first_batch` pins the changed S3 blockers and batch. Synthetic no-impact declarations isolate other tests; the public index is unchanged. |
| F3, low — `sweep.py:464` | Fixed, **decided by the orchestrator**: output version is 2, `fresh` retains CR3's former `ok`, and documentation/`--skill` explain the contract. `test_version_two_preserves_freshness_independently_of_ok` proves that sufficient current coverage can yield `ok: true` with `fresh: false` and retained stale history. |
| F6, low — `IMPLEMENTATION-PLAN.md:532,590,1031–1032` | Fixed, **decided by the orchestrator**: CR3 is complete at PR #31 in the overview, table, milestone status and summary. Manual status cross-check confirms all four locations agree. |
| F7, low — `INDEX-FORMAT.md:119` | Fixed, **decided by the orchestrator**: item row documents nonempty class strings, unknown-as-R behavior and optional impact/execution/action. Manual schema cross-check plus the existing unknown-class, impact and tier-2 tests cover the documented behavior. |
| F8, low — `test_stopping.py:150–152` | Fixed, **decided by the orchestrator**: `test_w_and_records_do_not_start_revisions` asserts S3 is met and that no unit contains SR-8-1/2/3 or A-RR-1, independent of its kind name; its separate records assertion remains. |
| F9, low — `INDEX-FORMAT.md:464–465` | Fixed, **decided by the orchestrator**: the original disposition is explicitly preserved in `open_items`, not queue units. Manual comparison with real report fields confirms the wording; queue schema is unchanged. |
| F10, low — `GLOSSARY.md` (usage at `AGENTS.md:57`) | Fixed, **decided by the orchestrator**: added Stopping report, Guarded queue and Comparison reading beside Reading lineage/Review batch. Manual term lookup confirms all three definitions and placement. |

The F1/F2/F3 regression tests reproduced their findings before the fixes. No
second swarm or independent review was launched by the implementer.
