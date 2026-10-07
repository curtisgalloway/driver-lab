<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS8: documents split; frozen archive; open-side check

**Terms:** the *open side* is driver-lab outside its *frozen archive*, the history kept after the
license split (both in the [glossary](../GLOSSARY.md)). A *move list* maps each removed passage to
where it now lives. A *term* is one of the patterns `check-open-side.py` refuses; the *allowlist*
is the set of paths where they may stay. See also the [design's terms](../docs/LICENSE-SPLIT.md#terms).

Design: [LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md) (LS-R20; LS-R14's design-text part). Plan:
[LS8](../docs/LICENSE-SPLIT-PLAN.md#ls8--documents-split-frozen-archive-open-side-check).
Notebook: [LS8](../notebook/LS8.md). Starting revisions: driver-lab `6a58cb4` (origin/main,
LS1–LS7 merged), `cleanroom-skills` `c8754dd`; no pre-existing changes.

**Status: complete at the checkpoint;** pushes and pull requests are the orchestrator's. Commits:
driver-lab `driver-porting: LS8 — documents split; frozen archive; open-side check` and
`cleanroom-skills` `driver-porting: LS8 — clean-room design and instructions moved in`, each on
its `license-split/ls8` (hashes in the pull requests; a commit cannot name itself).

## What changed

**driver-lab:**

- `DESIGN.md` keeps the open method (scope, terms, the problem, the hardware map, the evidence
  model, the pieces, a three-step lifecycle, continuous review C1–C8, evaluation, shipped and
  proposed, extending, limits). 28 passages moved (table below), and the places listed after the table reworded
  where they named the method; a revision line says what moved and points here.
- `README.md`: the "Clean-room driver porting" section moved; the method is named in one line,
  the pointer to `cleanroom-skills` in "Why this exists"; the other mentions reworded or removed
  (list below).
- `AGENTS.md`: the Isolation rule moved; a new "Open side only" rule names the check; the check
  list gains `check-open-side.py` and `utilities/tests`; "What this is" says what is archive.
- `GLOSSARY.md`: five rows moved, one dropped, three reworded (below).
- Frozen-archive headers (below); `RECONSTRUCTION.md`'s four links into the skills LS7 deleted
  repointed to `cleanroom-skills`.
- `utilities/check-open-side.py` and `utilities/tests/test_check_open_side.py` (13 tests); two
  CI steps.

**cleanroom-skills:** new `DESIGN.md` (the moved passages, each with its source line range);
README "How the pipeline fits together" (the moved README section); AGENTS.md "Evaluation
rounds" and "Isolation"; glossary markers corrected and five rows added (strace, canary, frozen
archive, blind requirement list, operator); TRANSITION.md "What moved in LS8".

## Move list

Sources are driver-lab files at `6a58cb4`, by line. **CD** = `cleanroom-skills/DESIGN.md`, by
section. Passages marked *recast* were sentence fragments, completed with the words they need to
stand alone; everything else is verbatim except names (`os-investigator` → `cleanroom-investigator`;
in step 4, `spec-verifier` → `cleanroom-verifier`) and links.

| # | Source | What | Destination | What driver-lab keeps |
| --- | --- | --- | --- | --- |
| 1 | `DESIGN.md` 37–38 | `cleanroom-implementer` stays here as candidate producer and handoff contract | CD "Scope" | nothing |
| 2 | 68–71 | Terms: clean room, encumbered source, dirty side, clean side | CD "Terms" | nothing |
| 3 | 80 | Term: provenance map | CD "Terms" | nothing |
| 4 | 85 | Term: ledger, clean-room event-log sense | CD "Terms" (recast) | "an evaluation answer key" |
| 5 | 122–126 | the separate risk when the reference is encumbered | CD "The second wall" | nothing |
| 6 | 128–132 | "The licensing wall controls transfer" | CD "The second wall" | nothing |
| 7 | 136–138 | a boundary `PASS` is not an accuracy `PASS` | CD "The second wall" | the accuracy paragraph's first two sentences |
| 8 | 140–144 | the anchored route vs the clean-room route | CD "The second wall" | two sentences: specs are published where their sources' licenses fit |
| 9 | 261–262 | `[emulated]` rule: model source is encumbered, not carried across the wall | CD "Evidence model, behind the wall" (recast) | the rule up to "never how the model produces it" |
| 10a | 328–329 | an implementation context must not invoke the investigator roles (review S2) | CD "Investigation" (recast) | "The orchestrator delegates source reading." |
| 10 | 334–338 | the `os-investigator` piece | CD "Investigation" | nothing |
| 11 | 346–349 | stubs paragraph naming `cleanroom-spec` and the clean-side orchestrator | CD "Investigation" | stubs as names for `board-expert`'s role, none shipped |
| 12 | 360–365 | the `cleanroom-spec` piece | CD "Authoring" | nothing |
| 13 | 377–378 | anchored skill refuses the encumbered-source case, does not load the investigation role | CD "Authoring" | "refuses fabricated anchors, not a way to write a driver under a license the source's terms do not permit" (LS7's wording in the skill) |
| 14 | 391–392 | review is not an input channel for a clean-room implementer | CD "Authoring" (recast) | first clause |
| 15 | 403–404 | second reading for clean-room driver specs | CD "Verification" (recast) | board and anchored items |
| 16 | 407–421 | § "Implementation" (`cleanroom-implementer`, isolation) | CD "Implementation" | nothing |
| 17 | 428 | candidate production uses `cleanroom-spec` | CD "Evaluation" (recast) | "uses a spec-authoring skill" |
| 18 | 435–438 | lifecycle intro, "through a differently licensed target OS port" | CD lifecycle intro | intro without the port, naming the open authoring skill |
| 19 | 442–443 | step 1: `cleanroom-spec` resolves forks | CD step 1 | "The authoring skill resolves" |
| 20 | 461–476 | step 2 "Investigate behind the boundary" | CD step 2 | nothing |
| 21 | 478–495 | step 3 "Check what crosses the licensing wall" | CD step 3 | nothing |
| 22 | 499–501 | step 4: the boundary procedure; the implementer may not compare | CD step 4 | "Invoke `spec-verifier` for the landed spec…"; step renumbered 2 |
| 23 | 521–522 | step 4: the two-failure bound is the boundary check's | CD step 4 | "adding one is proposed work" |
| 24 | 524–537 | step 5 "Implement without reopening the reference" | CD step 5 | nothing; step 6 renumbered 3 |
| 25 | 1004–1006 | freeze: "clean-room scan"; the gold ledger is a clean-side artifact | CD "Evaluation inputs behind the wall" | "source-overlap scan"; the quotation sentence |
| 26 | 1094–1095 | `leak_scan.py` in the shipped tools | CD "Tools" | nothing |
| 27 | 1169–1170 | choose the clean-room or anchored skill | CD "Extending" | "use the anchored authoring skill and place the spec by its sources' licenses" |
| 28 | 1188–1191 | limits: the boundary check is about the wall | CD "Limits" | nothing |
| 29 | `README.md` 100–135 | § "Clean-room driver porting" (three skills, Antigravity install material) | `cleanroom-skills` README "How the pipeline fits together" | nothing |
| 30 | `AGENTS.md` 71–78 | Isolation rule and the 2026-09-25 sandbox approval | `cleanroom-skills` AGENTS.md "Isolation" (verbatim) | "Open side only" rule |
| 31 | `GLOSSARY.md` 35, 81, 85, 86, 144 | provenance ledger, clean-room boundary, transfer review, attractant, provenance attestation | `cleanroom-skills` GLOSSARY (rows already there; "shared" markers removed) | nothing |
| 32 | `GLOSSARY.md` 139 | `cleanroom-skills` row | dropped; the README pointer line says what it is | nothing |

**Reworded in place, nothing moved** (`DESIGN.md` at `6a58cb4`): revision note (12); scope list
(17) and the L01/L02 candidates (25–26); heading "The problem and the two walls" → "The problem"
(107); the investigation-method link (120) → `board-expert` § 3; the stub fixture's hand-off
(172); `board-expert` "answers with its own investigation method" (341–342); continuous review:
"the implementer" for "a clean-room implementer" (619, 721, 774), "implementer sandbox
settings" (850), "an isolated implementer" and "Codex in a bubblewrap sandbox with an strace
access audit (L02)" (881); shipped skills list (1085). Glossary: Bubblewrap and strace rows say
"L02's implementer sandbox/audit"; the run-ledger row drops "and the provenance ledger".
README: intro list, scope, "Why" terms sentence, the repositories sentence (said they "do not
exist yet"; they have since LS5), the pointer bullet, "Not for", three table rows, the anchored
skill's description and limit, board experts' introduction, spec location, method and
research-fill, the clean-room `spec-verifier` item (removed), "this pipeline", the plans list.

**Anchors:** every link into a `DESIGN.md` anchor targets a kept heading (scope, evidence model,
"when there is no existing driver", continuous review, C5, C6, the layer's acceptance; Markdown
links and `evals/e1000/status.yaml`), so no redirect stub was needed; `index_check.py` passes.
Nothing linked the lifecycle steps by number.

## Frozen-archive headers

A blockquote after the title: frozen as of the split (2026-10-06), the clean-room skills and new
rounds are in `cleanroom-skills` (with its `DESIGN.md`), names as they were then, LS-R20.

| Where | Files |
| --- | --- |
| Documents | `RECONSTRUCTION.md`, `QEMU-DIFFERENTIAL.md`, `EVAL-PLAN.md`, `VALIDATION-PROPOSAL.md`, `VALIDATION-REVIEW.md`, `IMPLEMENTATION-PLAN.md`, `DEFERRED-PLAN.md` |
| `evals/` | new `evals/README.md` (the directory); `evals/enc28j60/README.md`; `evals/e1000/harness/README.md` (the e1000 campaign has no top-level README; this is its only one) |
| `evidence/` | new `evidence/README.md`, naming which files are archive and that `LS*` record the split |
| `notebook/` | `notebook/index.md`: every chapter except `LS-design` and `LS1`–`LS12` |
| History records | `TRANSITION.md`, `docs/STORY.md` |

Not headed: `history/` (one machine-read commit map; `TRANSITION.md` documents it) and
`PROCESS-NOTES.md` (a live log, appended by every milestone).

## The open-side check

`python3 utilities/check-open-side.py [--root DIR]`: tracked files only; exit 0 clean, 1
findings (each `path:line: [term] text`), 2 usage or environment error.

**Terms** (case-insensitive): `clean[-_ ]?room` (clean-room, cleanroom, clean room, and so every
`cleanroom-*` skill and `cleanroom_*` script name), `os-investigator`, "the wall", "licensing
wall", "research subagent", "dirty side" / "clean side", and the moved scripts' names
`leak_scan`, `sandbox_audit`, `session_audit`, and the method's own vocabulary: "encumbered",
"attractant", "provenance ledger", "transfer review" (added after review S6). Not a term: prose
"leak scan"; C3 and C5 now say "source-overlap scan" (review S1).

**Allowlist**, item by item:

| Path | Why |
| --- | --- |
| `evals/`, `evidence/`, `notebook/`, `history/`, `RECONSTRUCTION.md`, `QEMU-DIFFERENTIAL.md`, `EVAL-PLAN.md`, `VALIDATION-PROPOSAL.md`, `VALIDATION-REVIEW.md`, `DEFERRED-PLAN.md` | the frozen archive as LS-R20 lists it |
| `IMPLEMENTATION-PLAN.md` (whole file) | LS-R20 names its L01/L02/CR sections; its other sections (deferred table, decisions D7–D9 on the sandbox, active blockers, checks, backlog, next session) are those campaigns' bookkeeping, and the license split has its own plan. A per-section allowlist would add heading parsing to the checker for no reader's benefit |
| `docs/LICENSE-SPLIT.md`, `docs/LICENSE-SPLIT-PLAN.md` | they describe the split |
| `skills/campaign-review/tests/fixtures/deployment-cr5.yaml` | LS7's recorded exception: a copy of the frozen CR5 deployment pinned by `test_sweep.py` |
| `PROCESS-NOTES.md` | an append-only process log; its entries record past events and say which skill a fix belongs in; rewriting them would falsify the log |
| `TRANSITION.md` | the record of the 2026-09-25 move out of public-skills, which lists the skills as they were |
| `docs/STORY.md` | a timeline of the project's history for a later write-up |
| `utilities/check-open-side.py`, `utilities/tests/test_check_open_side.py` | the checker names its terms; its tests plant them |
| `README.md`, one line | the pointer LS-R20 allows; a second matching line fails |

**Output.** Before the document edits (checker on the starting tree plus the new files): `FAIL`,
83 lines, in `DESIGN.md` (47), `README.md` (25), `GLOSSARY.md` (8), `AGENTS.md` (3). After,
with everything staged, this file included: `OK: 286 tracked files, no clean-room mention outside
the allowlist`.
It caught one more on the way, a comment in `checks.yml` that named the method; reworded.

**Tests** (13): clean repository passes; a planted mention fails with its path and line; every
term detected; near misses ("the walls", "a clean build") pass; every allowlisted path passes;
the allowlist matches whole paths only (`evals-notes.md`, `docs/evals/`, a `deployment-cr6.yaml`,
a nested `IMPLEMENTATION-PLAN.md` all fail); one README line naming `cleanroom-skills` passes, a second fails, and a single line that does not name it fails; untracked
files are not scanned; a missing repository and an unknown option exit 2; the script run as CI
runs it exits 1 on a planted glossary row.

## Acceptance

| Criterion | Evidence and result |
| --- | --- |
| `check-open-side.py` passes on driver-lab and fails on a planted mention | Met: `OK: 286 tracked files…`; the planted-mention tests above. In CI (`Open side only`, `utilities tests`) and the AGENTS.md list |
| No broken relative links (link check over changed files) | Met for every link LS8 wrote or touched; result below |
| The frozen archive's CI checks still pass | Met: `index_check.py` `OK: 28 claims, …`; ENC28J60 tests OK; author manifest exit 0; campaign-review 121 OK; e1000 harness 70 OK |
| Nothing the open side relies on moved away | The evidence model, continuous review, verification, evaluation, hardware map and every `DESIGN.md` anchor linked from elsewhere stay; reviewer below |
| Privacy | `check-no-private-paths.py` OK in both repositories after staging; the diffs add no host name, address, user name or home path |

**Checks.** driver-lab, the full AGENTS.md list after the change (`ls8-checks-driver-lab.log`,
session scratch): privacy `OK: 287 tracked files`; open side OK; utilities 13 OK; board-expert 69
OK (1 skipped); anchored-peripheral-spec 96 OK; `spec_check.py` OK; ENC28J60 tests OK; author
manifest exit 0; e1000 harness 70 OK; campaign-review 121 OK; `index_check.py` OK.
`cleanroom-skills` (`ls8-checks-cleanroom.log`): privacy `OK: 49 tracked files`; 7 and 61 tests
OK; portability scan `0 finding(s)` with the local public-skills checkout and again with the
scanner at the CI pin `d63e3f1`.

**Link check.** A stdlib script in the session scratch (`linkcheck.py`) reads every Markdown link
outside code, resolves relative paths and heading anchors (GitHub's slug rule), resolves
`github.com/curtisgalloway/driver-lab/blob/<rev>/…` links with `git cat-file` at that revision
(anchors via `git show`) and `…/blob/main/…` links in either repository against the local
checkouts after the change. Command, over the Markdown files each diff touches:

```bash
python3 linkcheck.py --repo driver-lab=<worktree> --repo cleanroom-skills=<checkout> \
  --git driver-lab=<driver-lab> --git cleanroom-skills=<checkout> <changed .md files>
```

Result (`ls8-linkcheck.log`, session scratch): 27 files, 566 links checked, 31 external links
not checked, 9 unresolved, all in the plan's status lines for LS9 to LS-G, which link the
evidence and notebook files those milestones will create (present at `6a58cb4` already). No
link LS8 wrote or touched is broken. A run over all 197 Markdown files before the fixes also
found `RECONSTRUCTION.md`'s four links into the skills LS7 deleted; repointed.

## Review

One independent docs reviewer subagent with fresh context read both staged diffs, the move
list, the check logs and the link-check log, rechecked every move-list range against
`6a58cb4:DESIGN.md` (all 28 correct, verbatim apart from the declared changes) and every
`DESIGN.md#` link (all resolve). Findings: `ls8-review.md`, session scratch. No blockers.

| # | Sev. | Finding | Resolution |
| --- | --- | --- | --- |
| S1 | should-fix | C3's tier 0 listed "leak scans" among CI checks and C5 required "the leak scan" and a session audit, tools driver-lab no longer ships | "a deployment's source-overlap scans"; "where the campaign uses one, the source-overlap scan"; "audits the session where the deployment has an access audit" |
| S2 | should-fix | `DESIGN.md` "an implementation context must not invoke these investigator roles" (lines 328–329) left behind, on neither list | Moved: row 10a; CD "Investigation" (recast) |
| S3 | should-fix | README: a spec "may live in the target OS tree" contradicted the GPL-derivative rule | Adds "or in a spec repository whose license fits the sources it cites" (SPEC-FORMAT's wording) |
| S4 | should-fix | Two moved sentences now false (the anchored skill no longer points callers to the clean-room route; research-fill loads `board-expert`) | Dated notes after each in CD |
| S5 | should-fix | `IMPLEMENTATION-PLAN.md` frozen while "Next session" holds pending work | Its header says revision 10 and the candidate round move with new rounds to `cleanroom-skills`; the upstream report stays the user's decision |
| S6 | should-fix | Terms miss "encumbered", "attractant", "provenance ledger", "transfer review" | Added as a seventh pattern, with tests |
| S7 | should-fix | "Open side" not in the glossary | Row added |
| N1 | nit | README exemption took any first matching line | The exempt line must name `cleanroom-skills`; test added (13 tests) |
| N2–N4 | nit | 27 vs 28 passages; 285 vs 286 files; index "open" | Aligned (28; 286 counts this file; index closed at the checkpoint) |
| N5, N6 | nit | "Establish accuracy separately" dangling; revision note "§6" | "Establish accuracy"; "(now step 3)" |
| N7 | nit | Pointer bullet 310 characters | Kept on one line: the check exempts one line, and wrapping would split the term across two. "Not for" rewrapped |
| N8 | nit | `cleanroom-skills` glossary marker "shared" on rows that now differ | Marker redefined: "also defined in driver-lab's glossary" |
| N9–N11 | nit | CD terms source lines, Ledger not marked recast, "second wall" numbering, unlinked step 6 | Fixed; heading "The licensing wall" |
| N12 | nit | Repointed links at `cleanroom-skills` `main`, not pinned | Declined for now: the commit to pin is the LS8 merge, unknown at this checkpoint; recorded under Limitations |
| N13 | nit | `docs/STORY.md` link via `../docs/` | Fixed |

The fixes were checked by rerunning both check lists, the open-side check and the link check;
no second review.

## Limitations

- Links from driver-lab's archive headers and `RECONSTRUCTION.md`, and from `cleanroom-skills`'s
  README, to `cleanroom-skills` at `main` (its `DESIGN.md`) resolve only after its LS8 pull
  request merges; the link check resolved them against the local branch.
- The allowlist is wider than LS-R20's list by five history and tooling paths and the rest of
  `IMPLEMENTATION-PLAN.md`; each is justified above, and the design's wording ("at most in one
  README line") is met for every other file.
- The notebook chapter was opened after the work began (process log, 2026-10-06T18:21).
- LS9's rename must keep the open side free of the terms: its prose edits now run under the
  check.
