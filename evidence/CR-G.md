<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR-G: acceptance of the continuous-review layer

## Terms

- **Layer** — the continuous-review method built by CR1–CR8: the status index and claim map,
  the source registry, the deployment manifest, the sweep with its stopping rule and queue, the
  contract check, and their tests ([design](../DESIGN.md#continuous-review-keeping-specs-right-as-evidence-changes),
  [plan](../IMPLEMENTATION-PLAN.md#cr--continuous-review)).
- **C1–C8** — the design's eight requirements, each with an acceptance criterion; the layer is
  accepted when all eight are met on the e1000 campaign and the stand-in deployment
  ([design](../DESIGN.md#acceptance-for-the-layer-and-a-guard-against-over-building)).
- **Sweep** — the one local command that compares every recorded basis with the current
  identities and prints the stale set, the stopping report (S1–S5) and the queue.
  **Stand-in** — the invented private deployment CR7's tests generate outside the repository.
- **R/E/W item**, **tier 1 / tier 2** — a finding that changes what a driver must do, the
  evidence, or only wording; queued agent work versus work that waits for a person.

See the [glossary](../GLOSSARY.md) and the [notebook chapter](../notebook/CR-G.md).

## Status

**Complete, 2026-09-27; the layer is accepted.** C1–C5, C7 and C8 are met on their
milestones' evidence, five of them with a stated limit, and every cheap check was rerun on
today's tree. C6's last clause is met in the plan's form, extended here to CR8's blockers
(every blocker explained, classed and queued), not in the design's literal form (the e1000
campaign is not sufficient and its blockers are not the worked example's). **The user decided
on 2026-09-27 to accept the explained blockers:** the clause is met in that form, the layer is
accepted, and bringing e1000 to sufficient is the queue's work (see [the limits](#the-limits)).
The layer added nothing outside the guard. No spec, driver or harness was changed. Beyond the
acceptance table, this unit added one test for a cross-milestone check that had none and, by
the orchestrator's decision after the `review-swarm` over the layer's code, fixed all sixteen
of the swarm's findings and the round-cap hold the table's reviewer found ([Review](#review)).
Private run `crg-20260927-01` holds every command output named below; `index-check.txt` and
`ci-pre.txt` there predate this unit's two index entries, `index-check-final.txt` and
`ci-final.txt` follow them, and the `*-after-fixes*` and `ci-fixes.txt` outputs follow the
swarm fixes.

The driver result the layer tracks is unchanged: CF-2's rebuilt candidate and the reference
passed all ten acceptance scenarios twice on the emulated 82540EM. Spec revision 9 (CR8) has
since changed driver requirements, so those results are now stale in the index until a new
candidate round; they are not shown wrong.

## Acceptance table

| Criterion | Verdict | Evidence | Rerun today |
| --- | --- | --- | --- |
| **C1** Index and claim map cover every claim, every landed revision's verification and every open item in AF-1, SR-7, SR-8 and CF-2; each entry's basis traceable to public evidence and a run ID | Met, with a limit | [CR1](CR1.md) (28 claims, qualifications, results, EM1–EM8, items; review traced every item, every fifth claim and every shortfall); [CR2](CR2.md) (revisions 3–8, 95 entries, every one traced by the reviewer; [provenance extract](CR2-provenance.md)); later entries traced by the reviews of [CR6a](CR6a.md#review), [CR6b](CR6b.md#review) and [CR8](CR8.md#review) | Index checker OK: 28 claims, 28 qualifications, 28 results, 8 observations, 73 items, 102 verifications, 3 candidate rounds |
| **C2** A synthetic change matrix, one change per row, stales exactly the listed entries; a model change stales nothing; a one-check harness diff stales only that check's claims; an unmappable change widens | Met | [CR3](CR3.md#synthetic-matrix); unit kinds added in [CR4](CR4.md#acceptance) | Matrix: nine rows, all `ok`. Real sweep: 144 stale, each explained (below) |
| **C3** One changed identity yields the stale entries and covering tier-1 units; one batch of at least two tier-1 units ran from the queue to reviewed checkpoint commits with no person starting each unit, cost recorded; no tier-2 unit starts without a recorded decision | Met | [CR4](CR4.md#acceptance) (unit kinds per matrix row; tier-2 and batch guards); [CR6a](CR6a.md#status) and [CR6b](CR6b.md#status), each selected from the queue and launched by the orchestrator, PR #34. Reading costs: 8.8 min and 228,623 tokens; 41 min and 416,524 tokens. Adjudication costs: 2.7 min and 120,534 tokens; 1,521 s and 769,784 tokens | Matrix rows assert unit kinds and coverage. Today's queue: 31 tier-1 units, four tier-2; before this unit's decision records every tier-2 unit was `awaiting decision` and outside the batch |
| **C4** One comparison reading of the current revision by a different model, joined key by key, every disagreement adjudicated or listed, no verdict changed before adjudication | Met, with a limit | [CR6b](CR6b.md#method): Codex `gpt-6-astra` read revision 8 whole, 800 verdicts; all 119 non-PASS lines adjudicated key by key | — (a reading; not rerun) |
| **C5** The SR-8 → CF-2 path backfilled as the worked R path; one live W or E item carried through a revision with the index updated at each step | Met, with a limit | Backfill: [CR2](CR2.md#the-sr-8--cf-2-chain). Live item: [CR8](CR8.md#after-this-unit), revision 9 carried SR-8-1/2/3, A-RR-1 and the CR6b E and W aggregates, each superseded by an applied `-r9` entry | Index checker (above) |
| **C6** The sweep reports sufficient or lists exactly what blocks it; every open item has a class and a disposition; no W item alone started a revision; e1000 reaches sufficient or its blockers are the worked example's | Met, with a limit: the last clause in the plan's extended form, accepted by the user's decision (2026-09-27) | [CR4](CR4.md#real-report-and-differences-from-the-worked-example) (six differences from the worked example, each explained); [CR6a](CR6a.md#after-this-unit), [CR6b](CR6b.md#after-this-unit) and [CR8](CR8.md#after-this-unit) (each later change of blockers, with classes and dispositions); [CR8](CR8.md#after-this-unit) (revision 9 started by R items and the user's decision) | Sweep: not sufficient; S1 met; S2, S3, S4, S5 blocked, each blocker listed (below); twelve open items, each with a class and a disposition |
| **C7** A stand-in runs the sweep, C2's invalidation and one tier-1 re-verification; a registry change is detected with its sources unreadable; a role change changes the queued model without a code change; no stand-in ID in the public repository | Met, with a limit | [CR7](CR7.md#acceptance): live `gpt-6-astra` reading 4 PASS; the user's post-install sweep of the stand-in: sufficient, empty queue | Stand-in tests: 9 OK (each generates its own temporary stand-in; the suite ends with the public ID scan) |
| **C8** The contract check passes on the reference adapter, the QEMU backend and the stubs and fails on stubs missing each provenance field; the stand-in runs on stubs only; the manifest schema and contract check are the only new interfaces; no plugin but the reference plugins is named publicly | Met, with a limit | [CR5](CR5.md#contract-outputs) (32 missing-field stubs rejected); [CR7](CR7.md#acceptance) (stub plugins only) | Adapter on the harness and the spec: matches pin; contract check OK on both, on the canned QEMU run (19 PASS) and on the live reference run it was reduced from (19 PASS, input hashes unchanged); stub tests in the 116-test suite |

### The limits

- **C1:** the checker proves file links, IDs and hashes, not Markdown anchors or a verdict's
  truth; the historical readings' dependencies are unrecorded (null, so C2 widens to the whole
  revision); the exact compiler version and some historical model versions were not recovered
  ([CR1](CR1.md#recovery-and-limits), [CR2](CR2.md#recovery-limits-and-decisions)). Revision 9's
  verification is recorded as three draft readings; its landed text, three deletions after round
  3, has no reading yet, which the index says and S4 counts.
- **C4:** the 681 PASS lines were joined at section level, because no earlier record read at
  that grain; this shows no earlier record contradicts a new PASS, not that an earlier reader
  checked the same sentence. The adjudicators were one model family, and ten of the twelve R
  findings rest on one adjudicator. The reader's isolation from earlier records was by
  instruction and workspace contents, not a sandbox boundary, and its command log shows one read
  outside the permitted inputs (a conventions file holding no records)
  ([CR6b](CR6b.md#limitations)). The reading was of revision 8; it is now stale since revision
  9, so it stands as the event C4 asks for, not as current coverage.
- **C5:** revision 9 was made for R items (the user's decision), so the live W and E items rode
  along, as C6 requires; its landed text is not yet read, and two R findings from its rounds are
  still open (below). C5 asks for neither.
- **C6, last clause:** e1000 is not sufficient, and its blockers are wider than the worked
  example's single second reading. The plan the user approved accepted this form at two moments:
  CR4's criterion ("or each difference is explained in the evidence") for CR4's report, and
  CR6's ("or new ones this batch found, each with class and disposition") for CR6's. Neither
  clause covers the blockers CR8 introduced (revision 9's requirement change staling 28 claims'
  qualifications or results, the two CR8 R items, revisions 8 and 9 at 0/2); this unit's
  [table of differences](#every-difference-since-cr6) explains each of them, which extends the
  plan's form to them. That extension is this unit's, not the plan's. Read literally, the
  design's clause is not met until the campaign reaches sufficient. **The user's decision
  (2026-09-27, a structured question from the orchestrator): accept the explained blockers.**
  The clause is met in the plan's form, extended to CR8's blockers, and e1000 reaching
  sufficient is the queue's job: revision 10 for the two open R items, two independent readings
  of the changed text, the 27 requalifications and the acceptance-set rerun on a candidate
  updated to the new requirements (the CF-n round, tier 2, the user's launch), in that order
  (Next steps).
- **C3 and C6, the round-cap hold (fixed in this unit):** `stopping.py` held every
  second-reading, comparison-reading and re-verification unit whenever any revision's round cap
  reported "limit reached", and nothing released it, so the second reading after revision 10
  would have stayed held. The fix ([Review](#review)) holds nothing for a reached cap: the cap
  ends that revision's own fix-and-reread rounds, and the queue never emits such a round. A
  related rule is **not** changed and is open: the round count includes independent follow-up
  readings (a CR4 decision), so a revision that uses three sequential rounds and then gets its
  second independent reading counts four, an exceeded cap (`awaiting decision`) that holds
  reading work and blocks sufficiency. Revision 10 either stays within two sequential rounds or
  that counting rule needs a decision first.
- **C7:** the stand-in's scope is one optional synthetic claim with canned prior readings; its
  live reading was isolated by the brief and workspace, not by a read boundary, and without
  network isolation ([CR7](CR7.md#limits-and-pending-work)).
- **C8:** the evidence-producer and role points remain documented conventions, checked by each
  unit's reviewer, as the design says, until a first private plugin of that kind exists. The
  index and registry formats are also new, but they are C1's and C7's records, not extension
  points.

## Cross-milestone checks

| Check | Result |
| --- | --- |
| The sweep after CR6's entries still reports the same stale set and stopping state | The sweep code has not changed since CR6's merge (CR7 and CR8 changed only tests, fixtures and data). Run on CR6's merged tree, it reproduces CR6b's recorded state exactly: 96 stale; S2 13 stale qualifications; S3 AF-1's item, twelve R items and four readings with accuracy FAILs (CR6a's and CR6b's readings and adjudications); S4 revisions 3–6 at 1/2; S5 unmet; 15 tier-1 units. Today's differences, all from CR8's entries, are below |
| A harness check rename breaks the claim map and is caught | Existing tests: `test_static_and_formatted_renames` and `test_real_http_conversion_and_format_renames` (the real harness). Live probe on a scratch copy of the repository, one check renamed in `l02harness.py`: `Q01: unknown harness check: MAC matches QEMU's`, exit 1 |
| With no `deployment` key, the queue names the reference manifest's models | Live: the operator's config has no `deployment` key; every queued unit names `gpt-6-astra` (reader) or Claude Fable 5.1 (reviewer), the reference manifest's roles. No test covered this end to end (`test_reference_and_default` covers only the loader), so this unit adds one: `test_cli_without_deployment_key_names_reference_models` runs the sweep command with an empty config and compares every unit's model with [the reference manifest](../evals/deployment.yaml) |
| C5's live item | Met by CR8 (above) |
| The full CI list, locally | Every step exits 0 (the scanner from CI's pinned public-skills commit); `git diff --check` clean |

### Every difference since CR6

From CR6 to today the stale count rose from 96 to 144, current fell from 103 to 58 and
superseded rose from 15 to 40; no stale entry became current. CR7 added no e1000 entry.

| Change | Entries | Caused by |
| --- | --- | --- |
| 48 newly stale | the candidate round `candidate-CF2-a2` and all 28 per-claim results | Revision 9's header declares a driver-requirement change (C2's new-revision row) |
| | 14 qualifications (Q04–Q10, Q19–Q22, Q25, Q27, Q28), joining the 13 stale since CR3 | Revision 9 changed sections their expected outcomes cite; Q23's cited sections did not change, but it has no qualified PASS in an accepted class |
| | 5 readings of revision 8 (SR-8 round 2, CR6a's reading and adjudication, CR6b's reading and adjudication) | Revision 9 changed sections they read; they are recorded stale in the index |
| 23 newly superseded (CR8) | 19 queued items replaced by applied `-r9` entries, `CF-2-AR-10` by its re-destined replacement, and revision 9's three draft readings | CR8 |
| 2 newly superseded (CR-G) | `CR8-R-poll-tail-reopen`, `CR8-R-timeout-quiescence` | The user's decisions (below) |
| 25 new items | 23 from CR8 (19 applied `-r9` items, `CF-2-AR-10-r9`, the two R remainder items, now superseded, and `CR8-W-attestation-kernel`); the two decided replacements (CR-G) | CR8, CR-G |
| Stopping state | S2: 13 → 28 claims blocked. S3: twelve CR6b R items and four readings with accuracy FAILs → AF-1's item and the two CR8 R items (the R items were applied; the four readings left S3 because revision 9 made them stale). S4: revisions 3–6 at 1/2 → revisions 3–6, 8 and 9 at 0/2 (CR6b's whole-text reading is stale). S5 unchanged (CR6b is still the latest independent reading). Round cap: revision 9 has three rounds, "limit reached" | CR8's entries |
| Queue | The twelve CR6b requirement-change units are gone (applied); 14 requalifications, one acceptance-set rerun and one re-verification of the stale accuracy history are new (CR6b's whole-text reading, which had discharged that history from the queue, is now stale itself); the second reading and both re-verifications were held (`awaiting decision`) because revision 9 reached the round cap, until this unit's fix (they are now ready); the two CR8 requirement-change units are new, and ready since this unit's decision records | CR8's entries; CR-G |

At review time the sweep's first batch was three requalifications (Q01–Q03). After this
unit's round-cap fix it is the second reading and the two re-verifications, all ready. Both
batches would read or requalify against revision 9's text: revision 10 changes §10.3 again,
which 11 claims' expected outcomes cite (Q02, Q03, Q11–Q17, Q24, Q26) and which the readings
cover. The user's order puts revision 10 first, and the batch is a proposal, not a lease.

## The user's decisions after CR8

Relayed by the orchestrator, 2026-09-27, and recorded in the
[index](../evals/e1000/status.yaml) as decision records on replacement entries that supersede
the queued items (the verdicts are not edited):

| Item | Decision | Index entry |
| --- | --- | --- |
| `CR8-R-poll-tail-reopen` | Option (a): the poll calls `napi_complete_done()` and makes its unmask decision under the mask lock | `CR8-R-poll-tail-reopen-decided`, destination revision 10 (next follow-on unit) |
| `CR8-R-timeout-quiescence` | Option (a): transmit-timeout recovery through the stack's own close and open under RTNL | `CR8-R-timeout-quiescence-decided`, destination revision 10 (next follow-on unit) |
| `CR8-W-attestation-kernel` | Rides along in revision 10 | Unchanged: its destination is already the next revision made for another reason |

Revision 10 comes before the CF-n candidate round. This unit does not make it.

Standing decisions this unit relies on: each milestone's pull request merges without human
review; the reader role is Codex `gpt-6-astra` ([CR8](CR8.md#the-users-decisions-this-unit-ran-under));
option (b) for CR6a's TNCRS item ([CR6a](CR6a.md#the-users-decision)); all twelve CR6b R findings
in one revision ([CR8](CR8.md#the-users-decisions-this-unit-ran-under)).

## Guard against over-building

The layer's combined diff (from the commit before CR1's merge to CR8's merge) touches 61
files: 53 added, 8 changed. Every one falls in a category the guard allows. None adds a
service, database, scheduler, automated spec edit or automated merge.

| Category | Files |
| --- | --- |
| Index and claim map (C1) | `evals/e1000/status.yaml`, `evals/e1000/claims.yaml` |
| Registry (C3, C7) | `evals/e1000/sources.yaml`; `scripts/source_registry.py` (its validator) |
| Manifest schema and reference manifest (C8) | `scripts/deployment.py`; `evals/deployment.yaml` |
| Sweep, stopping rule and queue (C2, C3, C6) | `scripts/sweep.py`, `scripts/stopping.py` |
| Index check (C3 tier 0) | `scripts/index_check.py` |
| Contract check and reference adapter (C8) | `scripts/contract_check.py`, `scripts/pinned_file_adapter.py` (the design's reference source adapter); `scripts/cli.py` (shared argument errors for the commands) |
| Tests | six test modules and `standin.py` under `skills/campaign-review/tests/`; fixtures there (a small fake harness and index, stubs, the canned QEMU run with its license sidecars, frozen copies of the index, registry and manifest) |
| Existing code reused, not duplicated | `evals/enc28j60/corpus_check.py` (pin logic shared with the adapter, as CR3's scope asked); `utilities/run-store.py` (config reading shared with the `deployment` key, as CR5's scope asked) |
| Docs | `skills/campaign-review/SKILL.md`, `INDEX-FORMAT.md`; `AGENTS.md` (checks and the session-start sweep); `GLOSSARY.md`; `QEMU-DIFFERENTIAL.md` (A1's annotation); `IMPLEMENTATION-PLAN.md` |
| CI | `.github/workflows/checks.yml` (the campaign-review tests and the index check) |
| Records | `evidence/CR1.md`–`CR5.md`, `CR2-provenance.md`, `CR6a.md`, `CR6b.md`, `CR7.md`, `CR8.md`; `notebook/CR1.md`–`CR8.md`, `notebook/index.md` |

This unit adds this file, its notebook chapter, two index entries (and two status changes),
one cross-milestone test, the swarm fixes with their tests (changes to existing scripts, tests
and `INDEX-FORMAT.md`, no new file), and plan updates; none adds a category.

## Open items

In the [index](../evals/e1000/status.yaml), not repeated here: the two decided R items and the
W item for revision 10; AF-1's reading-coverage item (impact unrecorded); `CF-2-AR-10-r9`; the
candidate items A-RR-7 and `CF-2-RLEC-comment` for the next implementer brief; SR-8-4 (records);
the two outward-report decisions; the HF-1 and recall shortfalls (twelve items in all). Q18's
approved shortfall is a qualification, not an item. Not in the index: whether independent
follow-up readings count toward a revision's round cap (above), a rule for a decision before
revision 10's second reading.

## Next steps

1. **Revision 10**: the two R items, option (a) each, with `CR8-W-attestation-kernel`.
2. **A second independent reading** of the new text (tier 1; S4 needs two lineages on the
   revision 9 and 10 changes). The queue no longer holds it for revision 9's cap; if revision
   10 uses three sequential rounds, the counting rule above needs a decision first.
3. **The CF-n candidate round** on the new requirements, launched by the user (tier 2), then the
   requalifications and the acceptance-set rerun the queue holds.

## Checks

| Check | Result |
| --- | --- |
| `index_check.py evals/e1000` | OK: 28 claims, 73 items, 102 verification entries (before and after the fixes) |
| `sweep.py evals/e1000` | not sufficient, as above; exit 1. After the fixes: the same 58 current, 144 stale, 40 superseded and blockers; the second reading and both re-verifications ready and in the first batch |
| `test_sweep.py --matrix` | nine rows, all `ok`; exit 0 (before and after the fixes) |
| Contract check (reference adapter, canned fixture, live run) | above; exit 0 each |
| Stand-in tests | 9 OK |
| `campaign-review` tests | 116 OK before the fixes; 121 OK after |
| Pyink, Pylint (changed Python files); portability scan (campaign-review scripts) | clean; 0 findings |
| The full CI list | every step exit 0, before and after the fixes |
| `utilities/check-no-private-paths.py`; privacy grep of the diff (addresses, host and machine names, home paths, MAC addresses, banned words) | OK; no hits |

## Review

After the pre-review checkpoint, one fresh, read-only Claude Opus 5.5 reviewer checked this
table against the design, the milestone evidence files and every artifact in the run; its
report is in the run store under `review/`. It reran the index checker and the sweep (output
byte-identical to the run's), and confirmed every figure quoted here from earlier evidence, the
48 newly stale entries and the other differences since CR6, the queue before and after the
decision records, the two new index entries against the format and CR6a's precedent, the new
test, all 61 files in the guard table, every link anchor, and the public-file rules. Three
medium findings, eight low and four informational, all applied:

| ID | Sev | Finding | Resolution |
| --- | --- | --- | --- |
| G-1 | medium | "Accepted" and "every criterion met" were stated as final while C6's literal clause was left to the user | The question went to the user, who accepted the explained blockers; Status, plan and deferred plan cite that decision |
| G-2 | medium | CR4's and CR6's plan criteria covered their own moments, not CR8's blockers | The C6 limit says this unit extends the plan's form to CR8's blockers, and puts that to the user |
| G-3 | low | "Five with a stated limit" against six rows | C6 has its own verdict; five limits remain |
| G-4 | medium | The round-cap hold on reading units never releases in the code; the next second reading stays held after revision 10 | Fixed, decided by the orchestrator: see the swarm table below |
| G-5 | low | C4's limits omitted CR6b's isolation limit and that its reading is now stale | Added |
| G-6 | low | CR6's S3 also had four readings with accuracy FAILs; their exit was unexplained | Added to both descriptions |
| G-7 | low | The new re-verification is also held | Added |
| G-8 | low | The open-items list counted Q18, a qualification shortfall | Separated; twelve items |
| G-9 | low | Six test modules, not seven; "CR1–CR8" implied a CR6.md | Corrected |
| G-10 | low | The plan's CR-G review includes `review-swarm` | The swarm ran; recorded below |
| G-11 | low | Two run outputs predate the index entries | Said in Status; final outputs added to the run |
| G-12 | info | C3's text omitted "no person starting each unit"; adjudication costs missing | Both added |
| G-13 | info | Only 11 claims cite §10.3 | Narrowed |
| G-14 | info | DEFERRED-PLAN listed three of M16a's four rules | Completed |
| G-15 | info | The new test assumed exit 1 and a nonempty queue | Accepts exit 0 or 1 and an empty queue |

### `review-swarm` over the layer's code

The orchestrator ran `review-swarm` over the layer's code (base: the commit before CR1's merge;
head `70cdb0e`) in two runs, because the code diff, about 6,100 changed lines, exceeds the
skill's limit of roughly 3,000: **scripts** (11 files) and **tests** (10 files), seven arms
each (security, correctness, compatibility, documentation, history, conventions, performance).
All 14 arms completed. The quote check verified 18 findings (scripts 12: correctness 4,
compatibility 2, documentation 4, history 2; tests 6: correctness 1, compatibility 1,
documentation 2, history 2); the referees dropped none, merged two (scripts F1 into F5 and F9
into F12, the same lines and defect) and lowered scripts F7 from medium to low. Sixteen
remain. Tables and findings are under `review-swarm/` in the run. **Every fix below was decided
by the orchestrator**, which lifted this unit's no-code limit for these fixes only. Each new
test was run against the pre-fix code and failed there. The real harness yields the same 109
check names before and after the name-walker fixes.

| Run / ID | Sev | Location (reviewed code) | Finding | What changed | Covering test |
| --- | --- | --- | --- | --- | --- |
| scripts F5 | high | `pinned_file_adapter.py:131-134` | `--write` replaced a recorded hash, change maps and provenance with a `blocked`/`unknown` observation's nulls | A write is refused unless the source was hashed (`status == "ok"`); the registry is untouched, `updated` and `would_update` are false, a finding says so | `test_blocked_write_leaves_registry_unchanged` |
| scripts F11 | medium | `pinned_file_adapter.py:148-149` | An invalid date or malformed config raised a traceback (CR5's fix missed here) | Catches `ValueError` with `YAMLError`, as `sweep.py` does | `test_invalid_date_and_usage_errors_are_json` |
| scripts F12 | low | `pinned_file_adapter.py:97` | Usage errors printed no JSON (CR5's shared parser not used) | Uses `cli.Parser` with the adapter's payload fields | `test_invalid_date_and_usage_errors_are_json` |
| scripts F4 | low | `cli.py:20` | `--js` abbreviated `--json` without JSON-mode detection | `allow_abbrev=False`; `--json=` also detected | `test_usage_errors_are_json` (`--js` rejected, `--json=1` JSON) |
| scripts F8 | low | `index_check.py:63` | `--json` usage errors printed no JSON | Uses `cli.Parser` with `counts: {}` (imported in `main()`, since the tests load the module by path) | `test_usage_errors_are_json` |
| scripts F2 | low | `index_check.py:167-168` | A conditional with a runtime test yielded only its `else` name | `name_candidates()` collects both branches, also inside a formatted name | `test_runtime_conditional_handler_and_loop_names` |
| scripts F3 | low | `index_check.py:289-291` | Except handlers and runtime-iterable loop bodies were never walked | Handlers walked; a runtime loop body walked once with its target unknown | `test_runtime_conditional_handler_and_loop_names` |
| scripts F10 | low | `pinned_file_adapter.py:36` | Exit 0 was documented as "matched" but also covers a source with no pin | Documented (the orchestrator left the choice here): exit 0 means matched, or hashed with no pin to compare (`matches_pin` null). A distinct status would change the adapter's exit contract, which deployments already call | — (documentation) |
| scripts F6 | low | `pinned_file_adapter.py:141-144` | The registry was rewritten in place | Written to a temporary file beside it, then `os.replace`; the temporary file is removed on failure | `test_failed_write_keeps_registry_whole` |
| scripts F7 | low | `sweep.py:39` | `--skill` named Claude Fable 5.1 as the reference reader | Says the reader comes from the manifest's reader role (reference: Codex `gpt-6-astra`; reviewer: Claude Fable 5.1) | — (documentation) |
| tests F1 | low | `test_sweep.py:315-318` | Mappings accumulated, so the third case tested an unreviewed map | Each mapping starts from the reviewed row, under `subTest` | the test itself |
| tests F2 | low | `test_sweep.py:491-498` | The CLI test read the operator's own config | Runs with `XDG_CONFIG_HOME` empty and `DRIVER_LAB_RUNS` unset | `test_cli_json_skill_and_errors` |
| tests F3 | low | `test_stopping.py:50` | A comment said the live index; the test reads the frozen CR5 fixture | Comment corrected | — |
| tests F4 | low | `test_sweep.py:589-595` | "Unknown ID" was never tested | An unregistered ID now fails with `not registered`, exit 1 | `test_duplicate_keys_and_unknown_id` |
| tests F5 | low | `test_deployment.py:144-149` | G-15 not applied to the sibling routing test | Accepts exit 0 or 1 and any queue; the reviewer-presence assertion dropped | `test_cli_routes_models_from_config_without_code_changes` |
| tests F6 | low | `test_sweep.py:498-501` | Pinned the live index's stale count, so every new entry broke it | Pins 96 on a temporary campaign built from the frozen CR5 index and CR7 registry; the live index is checked for shape and exit code only | `test_cli_json_skill_and_errors` |
| reviewer G-4 | medium | `stopping.py:459-469` | A reached round cap held every reading and re-verification unit, with no release | A reached cap holds no queued unit (it ends that revision's own rounds, which the queue never emits); an exceeded cap still holds reading work. `INDEX-FORMAT.md` states the rule | `test_reached_cap_holds_no_queued_reading` (replaces `test_third_round_sends_remaining_readings_to_user`, which pinned the old hold): revision 8 is capped in the frozen fixture, standing in for revision 9, and the second reading, a comparison reading and re-verification stay ready. On the live index, with revision 9 at "limit reached", the second reading is ready |
