<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# CR1: e1000 claim map and status index

**Terms:** a qualification shows a check caught an intended planted defect; a
candidate result records what a driver passed; a basis identifies the inputs to
that verdict. An item is a finding with a disposition. See the
[format](../skills/campaign-review/INDEX-FORMAT.md) and [glossary](../GLOSSARY.md).

Implementation and the orchestrator's five requested review fixes are ready for
checkpoint; the implementer made no commit. Implementation artifacts and the
independent review are in the orchestrator-provided run `cr1-20260926-01`.

The index records the existing differential result: CF-2's candidate passed all
ten scenarios twice on CS-1's harness, supporting 27 qualified claims within their
recorded scopes. Q18 remains an observed PASS with an accepted timing shortfall.
CR1 ran no new driver tests and makes no hardware or sufficient-for-scope claim.

## Deliverables and acceptance

The [claim map](../evals/e1000/claims.yaml) and
[status index](../evals/e1000/status.yaml) are the status record; completed evidence
files were not changed. The plan's follow-on summary now points there.

| CR1 criterion | Implementation |
| --- | --- |
| Q01–Q28, expected-outcome sections, exact checks and qualifying runs | All 28 mapped; public recall section locations and harness/evidence citations supply the section mapping; shared checks include reload and before/after names |
| Qualification per claim | 28 entries: 27 qualified, Q18 shortfall with reason unobservable, reopening condition and user-decision link to L02f3 |
| Current candidate results | 28 entries for CF-2 round a2, candidate module df37c7ad… on harness a1735b9f…; all PASS, Q18 explicitly not qualified evidence |
| Emulated observations | EM1–EM8, each with basis, sections, evidence and run IDs |
| Findings and dispositions | 27 items; 12 queued, 10 applied history, 3 rejected changes, 2 shortfalls. The index is authoritative for their individual dispositions |
| Orchestrator decisions | A-RR-1 W; A-RR-7 in the next implementer brief; SR-8-4 targets records, not the spec |
| Checker and fixtures | Schema, enums, identities, unique IDs/aliases, supersession, qualification coverage, exact check names, file links and mandatory-shortfall approval; good fixtures and mutated bad fixtures |
| CI and instructions | Test and real-index check added using CI's existing PyYAML environment; both commands in AGENTS.md |

## Verification

The private `VERIFY.txt` records the original commands, exit codes and output.
The table below reflects verification after the review fixes. The two `uv`
commands from the plan ran with an offline temporary cache copied from the existing
cache because network resolution was unavailable; no dependency was added to the
project and no system configuration changed.

| Check | Output |
| --- | --- |
| `uv run --with pyyaml python3 -m unittest discover -s skills/campaign-review/tests` | 22 tests, OK |
| `uv run --with pyyaml python3 skills/campaign-review/scripts/index_check.py evals/e1000` | OK: 28 claims, 28 qualification, 28 result, 8 observation, 27 item |
| Privacy checker | Clean on tracked files and separately on every new public file |
| `git diff --check` | Clean; new files also checked for whitespace |
| Diff privacy grep, including new files | No added-content hits |
| Pyink, Pylint, portability scan | Clean; portability: 0 findings |

The tests cover missing fields, invalid values, duplicate YAML keys and IDs,
missing and escaping links (including symlinks), missing qualification, superseding
a current entry, cycles, unapproved mandatory shortfalls, qualified-evidence misuse,
and check renames. Formatted-name tests reject an invented reload number, a changed
literal, and unsupported conversions and format specifications in the real HTTP
check. Disposition tests reject fields belonging to another state and malformed
optional destinations. The harness is parsed, never executed.

## Review

An independent, read-only Codex review is recorded in `codex-review-cr1.md` in run
`cr1-20260926-01`. It traced all 26 then-existing items, every fifth claim
(Q05, Q10, Q15, Q20, Q25), and all three shortfalls (Q18, HF-1, recall-r3) to the
public evidence. It inspected the checker and ran the real-index check,
real-campaign assertions, mutation probes, privacy checks and `git diff --check`.
The reviewer did not run the temporary-file-writing test suite or independently
verify private artifact availability and recovered hash suffixes. It recommended
changes before landing: three medium findings and two low findings.

| Finding | Disposition |
| --- | --- |
| R1, medium: formatted-string conversions were ignored, allowing an HTTP check rename through | Fixed, decided by the orchestrator: reject conversions and explicit format specifications; test the real HTTP check with `!r`, `!s`, `!a`, a width specification and an empty specification |
| R2, medium: CF-2's stale RLEC comment was missing | Fixed, decided by the orchestrator: add `CF-2-RLEC-comment`, W/source 1, targeting the candidate and carried to the next implementer brief with no standalone round |
| R3, medium: `cf2-review` omitted known applicable identities | Fixed, decided by the orchestrator: restore the candidate and original a1 harness, guest, emulator, reference module and toolchain identities; the a1 run record confirms the full hashes, and CF-2 records the versions |
| R4, low: optional disposition fields bypassed validation | Fixed, decided by the orchestrator: allow only each state's documented fields and validate optional destinations; tests reproduce HF-1's mapping destination and queued revision/reopening fields |
| R5, low: Q15 linked the wrong evidence fragment | Fixed, decided by the orchestrator: both the claim's defect evidence and qualification entry now link to `L02f2b.md#requalification` |

The implementer reran the checks after these fixes. No second independent review
was performed; checkpoint and any further review remain with the orchestrator.

## Recovery and limits

- Full spec hashes for revisions 4, 6, 7 and 8, later harness hashes, and the CF-2
  candidate and initramfs identities were recovered from the named private records.
  Only identities were copied. The original L02d3 harness hash was recovered from
  repository history and matches the published prefix.
- The named L02d2 and L02d3 run stores were unavailable locally. Their run IDs and
  controls come from public evidence (L02d2's control is r010); their raw artifacts
  were not rechecked. All 58 distinct qualification/control run directories named
  in the map that belong to available stores exist. The candidate's 20 a2 identity
  files report one common initramfs hash.
- Exact compiler versions and several historical reader/operator model versions
  were not recovered. Bases say so. Qualification initramfs identities vary with
  the planted module and remain in per-run records. Observations spanning multiple
  historical harnesses explicitly have no single harness hash; CR3 must widen any
  uncertain invalidation rather than treat null as a matching identity.
- Section mappings are operator mappings from public evidence, using enclosing
  sections when necessary. They are not a new verification reading. Historical
  reading dependencies remain null, requiring whole-revision widening.
- The checker validates file links, not Markdown fragment anchors, evidence truth,
  or the availability of private artifacts. Finite literal name extraction checks
  names, not runtime reachability or stimulus. These remain artifact-review work.

## Implementation decisions

- Shared immutable bases avoid repeating full identity records on every entry.
- A target distinguishes spec, candidate, records, upstream, hardware and review
  findings so later work does not mistake every R item for a spec change.
- Applied AF-1/SR-7 findings and the carried SF-1 pointer finding remain as history;
  A-RR-5 aliases SR-8-2 because both name the same pending sentence.
- Deferred candidate behavior changes and rejected candidate changes use R
  conservatively; upstream/evidence/review work uses E; form/wording uses W.
- HF-1 and revision-3-only recall are scoped shortfalls with explicit reopening
  conditions; outstanding reading coverage remains queued for later review work.
- Q27 points to FC-1's final-harness f2 confirmations; the original f1 ×3 evidence
  remains linked. Q15 points to its L02f2b requalification.
- The latest validated harness identity is separate from the original qualification
  basis, with the public carry-forward evidence retained.
- Exact check names are expanded statically from the harness, avoiding wildcard
  acceptance and avoiding a QEMU dependency in CI.
- The explicit repository root defaults to the working directory; evidence links
  may not escape it. No private run-store lookup is part of the checker.
- Review fixes keep formatted conversions and explicit format specifications
  unsupported rather than expanding the evaluator; rejecting them prevents a
  changed check name from silently matching its old spelling.
- Disposition fields are restricted by state, including when their values would
  otherwise be well typed, so contradictory disposition metadata cannot pass.
- `cf2-review` uses the original a1 execution basis because CF-2-AR-10's observed
  link checks came from that round; the later a2 result basis remains separate.
- The unnumbered RLEC finding is named `CF-2-RLEC-comment`, with source 1, to give
  CF-2's field finding a stable identity without inventing a numbered review item.

## Handoff

CR2 still owns verification entries for revisions 3–8, the requirement-change
headers and linked SR-8 → CF-2 R-item chain, and confirmation of the worked S4
example. This implementation does not backfill that chain or declare S4 met.
The checkpoint commit and any further independent review belong to the orchestrator.
