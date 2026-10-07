<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS7: driver-lab's skills neutral; clean-room rules moved

**Terms:** the *open skills* are driver-lab's skills that carry no clean-room rule
(`board-expert`, `board-spec-scaffold`, `spec-verifier`, `anchored-peripheral-spec`,
`reference-driver-review`, `campaign-review`). To *wrap* a skill is to load it and add rules that
win where the two differ. A *move list* maps each removed passage to where it now lives. See the
[glossary](../GLOSSARY.md) and the [design's terms](../docs/LICENSE-SPLIT.md#terms).

Design: [LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md) (LS-R15; LS-R14's `spec-verifier` part). Plan:
[LS7](../docs/LICENSE-SPLIT-PLAN.md#ls7--driver-labs-skills-neutral-clean-room-rules-moved).
Notebook: [LS7](../notebook/LS7.md). Starting revisions: driver-lab `b9b60f7` (origin/main,
LS1–LS6 merged), `cleanroom-skills` `adeb0ff`; no pre-existing changes.

**Status: complete at the checkpoint;** pushes and pull requests are the orchestrator's. Commits:
driver-lab `driver-porting: LS7 — open skills neutral; clean-room skills removed` on
`license-split/ls7` (its hash is in the pull request; a commit cannot name itself), and
`cleanroom-skills` `670cecd` (`driver-porting: LS7 — clean-room rules moved in from driver-lab`)
on its `license-split/ls7`.

## What changed

**driver-lab:**

- `board-expert` no longer loads `os-investigator`. Its sections 3 and 4 carry a method and
  report format of its own, taken from the investigator's parts that say nothing about the wall
  (pin the commit, ground truth, device trees first, cross-check, cite documents, the
  driver-versus-hardware rules, untrusted fetched content, report headings); a fact read from
  code is cited by file and line. It says a wrapping skill's rules win where they differ.
- `SPEC-FORMAT.md`: `[source-observed]` is "defined by an extension, not by this format"; the
  checker still accepts it and requires the TODO. A new sentence under *Provenance tag* says how a
  fact read only from code appears on the open side (cited by `<repo>@<commit>` file and line; in
  a spec only as a cited premise of an `[inference]`); the variants, anchored-IP and ip-template
  text point at it. "Clean-room rules for spec content" became "Rules for spec content" (the
  neutral residue). `QUESTIONS.md`, `VENDOR-GUIDE.md`, `board-spec-scaffold` and its templates
  lose their clean-room text.
- `spec-verifier` loses "Clean-room driver specs" and the clean-room text in its shared parts; it
  gains one sentence saying a skill defining its own kind may wrap it, and the record rule
  becomes "The record cites; it does not quote".
- `anchored-peripheral-spec` (and its subagent template) and `reference-driver-review` no longer
  name the clean-room skills; the "not for" limit is restated without them.
- `skills/cleanroom-spec`, `skills/cleanroom-implementer`, `skills/os-investigator` deleted;
  CI drops their two test steps, the portability scan and the public-skills checkout (nothing
  else used it); `AGENTS.md`'s check list and the README's Tests block drop them too.
- `campaign-review`'s stand-in no longer copies the investigator's SKILL.md into a reader
  workspace; **test changed:** `test_standin.py` expects six frozen inputs instead of seven.
  `board-expert`'s tests needed no change: none read the clean-room text.
- `plugin.json` and `marketplace.json` descriptions rewritten without the clean-room pipeline
  and the deleted board experts (one of LS8's listed items, done here); keywords lose
  `clean-room`, `raspberry-pi`, `rockchip`.

**cleanroom-skills** (`670cecd`): `cleanroom-investigator` wraps `board-expert` (a table of which
sections it uses as written and which it replaces) and carries the moved rules; new
`skills/cleanroom-investigator/BOARD-SPECS.md`; new skill `cleanroom-verifier`, wrapping
`spec-verifier`; `cleanroom-spec` and its `PROVENANCE.md` point at it; README's duplicate-skills
paragraph deleted; AGENTS, glossary, TRANSITION and both manifests updated.

**Where the clean-room verification landed: a new `cleanroom-verifier` skill**, not a section of
`cleanroom-spec`. It is the on-demand re-run of both the transfer review and the accuracy pass;
its record rules (no source, `leak_scan.py`) apply to any spec verified from encumbered source,
not only to `cleanroom-spec`'s; and it wraps `spec-verifier` the way `cleanroom-investigator`
wraps `board-expert`, keeping `cleanroom-spec` about producing and landing a spec.

## Move list

Sources are driver-lab files at `b9b60f7` (line numbers there). Destinations are in
`cleanroom-skills`: **CI** = `skills/cleanroom-investigator/SKILL.md` § "Wrapping `board-expert`";
**BS** = `skills/cleanroom-investigator/BOARD-SPECS.md`; **CV** = `skills/cleanroom-verifier/SKILL.md` (new).
"Ref" = a cross-reference or contrast, not a rule; removed, with the counterpart named.

| # | Source (driver-lab `b9b60f7`) | What | Destination |
|---|---|---|---|
| 1 | `board-expert/SKILL.md` 10–11 | description: pairs with os-investigator, method and clean-room rule | CI intro; cleanroom-investigator description |
| 2 | `board-expert/SKILL.md` 35–39 | load os-investigator; main agent never reads GPL source; receives clean-room facts | CI "Running it" |
| 3 | `board-expert/SKILL.md` 41–43 | the split is the whole point; clean-room boundary | CI "Running it" |
| 4 | `board-expert/SKILL.md` 45–52 | "Method and constraints live in os-investigator" | CI "Method and constraints" |
| 5 | `board-expert/SKILL.md` 89–92 | cache for the expert only; preserves the clean-room boundary | CI "Cache and documents" |
| 6 | `board-expert/SKILL.md` 95–96 | `cite: true` docs are the clean-room authority | CI "Cache and documents" |
| 7 | `board-expert/SKILL.md` 106–108 | § 3: apply os-investigator; never emit source | CI "Method and constraints"; table row § 3 |
| 8 | `board-expert/SKILL.md` 112 | § 4: os-investigator's format, clean-room attestation | CI table row § 4 |
| 9 | `board-expert/SKILL.md` 142–143 | without a spec: run os-investigator | CI "Method and constraints"; table row |
| 10 | `board-expert/SKILL.md` 148–152 | cache rule: wall-crossing, verifier-PASSed | CI "Caching rule" (merged with the investigator's own caching rule) |
| 11 | `board-expert/SPEC-FORMAT.md` 16 | `cleanroom-spec` named as a driver-spec kind | Ref; cleanroom-spec defines itself |
| 12 | `SPEC-FORMAT.md` 49–50 | cache = encumbered side of the wall, spec = clean side | CI "Cache and documents" |
| 13 | `SPEC-FORMAT.md` 51–52 | five classes "are os-investigator's" | BS `[source-observed]` bullet 1 |
| 14 | `SPEC-FORMAT.md` 63–64 | `[rtl]` not public = encumbered; facts cross the wall | BS "Encumbered designs" |
| 15 | `SPEC-FORMAT.md` 79–81 | `[source-observed]` definition | BS bullet 1 (SPEC-FORMAT now: "defined by an extension") |
| 16 | `SPEC-FORMAT.md` 83–84 | inference example naming `[source-observed]` | BS bullet 2 |
| 17 | `SPEC-FORMAT.md` 96–98 | `[emulated]`: model source encumbered, not a channel | BS "Encumbered designs" |
| 18 | `SPEC-FORMAT.md` 104 | series = map (`[DT]`, `[source-observed]`) | BS bullet 3 |
| 19 | `SPEC-FORMAT.md` 115–120 | "A spec is the artifact allowed to cross the clean-room wall…" | BS "What a spec is, behind the wall" (verbatim) |
| 20 | `SPEC-FORMAT.md` 125 | "source-invented identifiers" | BS same section, last line |
| 21 | `SPEC-FORMAT.md` 227, 234 | `cite: true` = "a clean-room authority: cite it, not the kernel" | CI "Cache and documents" |
| 22 | `SPEC-FORMAT.md` 299–301 | variants `tag: source-observed` | BS bullet 4 |
| 23 | `SPEC-FORMAT.md` 345 | tag rules list `[source-observed]` | kept as checker behavior ("an extension's class"); BS bullet 7 |
| 24 | `SPEC-FORMAT.md` 459–460 | anchored IP: board-tree-only fact tagged `[source-observed]` | BS bullet 5 |
| 25 | `SPEC-FORMAT.md` 527–551 | § "Clean-room rules for spec content" (all six bullets) | BS § of the same name, verbatim (name updated); neutral residue stays as SPEC-FORMAT § "Rules for spec content" |
| 26 | `board-expert/QUESTIONS.md` 14–17, 26, 31 | `cleanroom-spec` orchestrator, `os-investigator` subagent | CI "Who asks" |
| 27 | `board-expert/VENDOR-GUIDE.md` 6 | title "…and the wall" | Ref (the section is about NDA material); title now "…and what may leave" |
| 28 | `VENDOR-GUIDE.md` 109–110 | layer tags let a downstream clean-room verifier see non-public citations | CV "Vendor layers"; also BS rules bullet 5 |
| 29 | `board-spec-scaffold/SKILL.md` 25 | "the clean-room rules are in SPEC-FORMAT" | pointer; BS intro |
| 30 | `board-spec-scaffold/SKILL.md` 63–70 | convention "Clean-room first" | BS "Writing a board spec behind the wall" bullet 1 (verbatim) |
| 31 | `board-spec-scaffold/SKILL.md` 107–117 | research-fill with os-investigator, clean-room report, only the subagent reads code | BS "Research-fill" |
| 32 | `board-spec-scaffold/SKILL.md` 124–125 | `[source-observed]` carries the TODO | BS bullet 7 |
| 33 | `board-spec-scaffold/templates/stub-SKILL.md` 9–10, 31–34 | stub: os-investigator supplies the clean-room rule; receive clean-room facts | BS "Stubs and vendor skills" bullet 1 |
| 34 | `templates/vendor-board-tools-SKILL.md` 17 | load alongside os-investigator | BS "Stubs and vendor skills" bullet 2 |
| 35 | `templates/ip.spec.md` 52–53 | driver-only orderings are `[source-observed]` | BS bullet 6 |
| 36 | `templates/board.spec.md` 15 | variants tag option `source-observed` | BS bullet 4 |
| 37 | `spec-verifier/SKILL.md` 5 | description: clean-room driver specs (cleanroom-spec) | CV description |
| 38 | `spec-verifier/SKILL.md` 24–25 | `cleanroom-spec` runs this phase for clean-room driver specs | CV "Which skills create which kind" |
| 39 | `spec-verifier/SKILL.md` 31–32 | claim of a clean-room driver spec | CV "Claims" |
| 40 | `spec-verifier/SKILL.md` 95–97 | "No source in the record… clean-side artifact… leak_scan" | CV "No source in the record" (verbatim); neutral residue "The record cites; it does not quote" |
| 41 | `spec-verifier/SKILL.md` 107–109 | kind detection by cleanroom-spec structure | CV "Identify the kind" |
| 42 | `spec-verifier/SKILL.md` 115–116 | verifier gets os-investigator for the rule and cache discipline | CV "Spawn the verifier" |
| 43 | `spec-verifier/SKILL.md` 153–154 | `[source-observed]` names a tree and is compared | CV "Board specs" |
| 44 | `spec-verifier/SKILL.md` 224–253 | § "Clean-room driver specs" | CV § of the same name (verbatim, name updated) |
| 45 | `anchored-peripheral-spec/SKILL.md` 11–12 | "use cleanroom-spec instead, whose wall…" | Ref; counterpart: cleanroom-spec 28–31, cleanroom-skills README "What it is not for" |
| 46 | `anchored-peripheral-spec/SKILL.md` 27–28 | "same shape as a clean-room spec… opposite discipline" | Ref |
| 47 | `anchored-peripheral-spec/SKILL.md` 34–35 | "The clean-room skill answers…" | Ref |
| 48 | `anchored-peripheral-spec/SKILL.md` 85–86 | "or runs cleanroom-spec privately: its output is never published" | Ref; policy stated in cleanroom-skills README |
| 49 | `anchored-peripheral-spec/SKILL.md` 92–97 | don't load os-investigator here; cleanroom-implementer does not apply | Ref (an open-side instruction about itself) |
| 50 | `anchored-peripheral-spec/SKILL.md` 100 | "The advice from cleanroom-spec still holds" | Ref; the advice stays in cleanroom-spec |
| 51 | `anchored-peripheral-spec/SKILL.md` 241–242 | "anchored analog of the clean-room spec-gap list" | Ref |
| 52 | `anchored-peripheral-spec/SKILL.md` 339 | "Unlike the clean-room verifier" | Ref; cleanroom-spec 290–296 says its verifier skips accuracy |
| 53 | `anchored-peripheral-spec/templates/spec-subagent-prompt.md` 62 | "Do NOT load os-investigator" | Ref |
| 54 | `reference-driver-review/SKILL.md` 13, 37–39 | "use cleanroom-spec instead… wall not needed" | Ref |
| 55 | `campaign-review/tests/standin.py` 462, 483 | copies os-investigator's SKILL.md into a reader workspace | removed (path deleted); `test_standin.py` input count 7 → 6 |
| 56 | `campaign-review/tests/fixtures/deployment-cr5.yaml` 11, 15, 24, 25 | `via: skill:cleanroom-implementer`, sandbox agent | kept: a copy of the frozen CR5 deployment; names the skill, which keeps its name in cleanroom-skills |
| 57 | `skills/cleanroom-spec/`, `skills/cleanroom-implementer/`, `skills/os-investigator/` | deleted | identical (`diff -r`) to cleanroom-skills' filtered tip `225d95d^`, i.e. already moved in LS6 |

Passages not moved verbatim: row 10 (the caching rule is the union of `board-expert`'s and the
investigator's own), and in `BOARD-SPECS.md` the `[source-observed]` bullets and the
`[rtl]`/`[emulated]` notes, which recast sentence fragments from several places into one list.

## Acceptance

| Criterion | Evidence and result |
| --- | --- |
| `rg -i 'os-investigator\|clean-?room\|the wall\|research subagent' skills/` matches nothing except `[source-observed]` handling | **Met with one recorded exception.** `spec_check.py` and its test do not match the pattern at all. The only matches are `skills/campaign-review/tests/fixtures/deployment-cr5.yaml` lines 11, 15, 24, 25 (`via: skill:cleanroom-implementer` ×3, `agent: Codex under cleanroom_sandbox.sh with sandbox_audit.py`): `test_sweep.py` pins the file as the reference manifest as CR5 left it, a copy of the frozen `evals/deployment.yaml`; the names are data about a past deployment, and the skill keeps its name in `cleanroom-skills`. Kept; LS8's `check-open-side.py` must allowlist it. |
| Every removed passage has a destination | Met: the move list above, 57 rows; the reviewer checked every row and found no unlisted rule. The deleted directories are `diff -r` identical to `cleanroom-skills`' filtered tip `225d95d^` (the reviewer confirmed all 35 blob hashes). |
| driver-lab's remaining list and `cleanroom-skills`' CI pass | Met. driver-lab, the nine commands in `AGENTS.md` (`ls7-checks-driver-lab.log`, session scratch, run before and after the review fixes): privacy `OK: 279 tracked files`; board-expert 69 tests OK (1 skipped); anchored-peripheral-spec 96 OK; `spec_check.py` OK; enc28j60 OK; author manifest exit 0; e1000 harness 70 OK; campaign-review 121 OK; `index_check.py` OK. `cleanroom-skills` (`ls7-checks-cleanroom.log`): privacy `OK: 48 tracked files` after staging; 7 and 61 tests OK; portability scan at the CI pin `d63e3f1` `0 finding(s)`. |
| Privacy | Both privacy checks pass after staging; neither diff adds a host name, address, user name or home path. |

## Review

One independent reviewer subagent with fresh context read both diffs, the move list and both
check logs (`ls7-review.md`, session scratch). No blockers.

| # | Sev. | Finding | Resolution |
| --- | --- | --- | --- |
| S1 | should-fix | With `[source-observed]` defined elsewhere, the open format had no class for a fact read only from code; variants, anchored IP and the ip template each improvised, and the template's `[inference]` plus "order not known to be required" contradicted itself | One sentence under SPEC-FORMAT's *Provenance tag*; the three places and `board-expert` § 3 point at it; the template now says such an ordering goes in only as a cited premise of an `[inference]` |
| S2 | should-fix | `anchored-peripheral-spec`'s "not for" limit changed meaning (source's license instead of the target's) | Restated: "not a way to write a driver under a license the source's terms do not permit" |
| S3 | should-fix | The fixture exception was not recorded | Recorded above; LS8's allowlist noted in the plan |
| S4 | should-fix | README's Tests block still ran the deleted test directories | Two lines deleted (a broken command, not prose; the rest of the README is LS8's) |
| S5 | should-fix | `evidence/LS7.md` missing though `cleanroom-skills` cites it | This file |
| S6 | should-fix | "There is no wall here" left in `anchored-peripheral-spec` | Removed |
| N1 | nit | `BOARD-SPECS.md` replaced the scaffold's research-fill step wholesale, dropping its neutral fallbacks | "added to its counterparts and winning where they differ" |
| N2 | nit | A moved sentence referred to the investigator as if it might not be loaded | Reworded to "if `board-expert` is ever loaded without `cleanroom-investigator`" |
| N3 | nit | "Unchanged apart from names" overstated | "except where noted in driver-lab's `evidence/LS7.md`" (the note after the move list) |
| N4 | nit | Long lines | The ones this change introduced rewrapped; older ones left |
| N5 | nit | Marketplace fix is an LS8 item; unstaged process-log entry | LS8 item marked done in the plan; the entry is committed |

The fixes were checked by rerunning both check lists and the acceptance grep; no second review.

## Limitations

- driver-lab's root `README.md`, `AGENTS.md` (beyond the check list), `GLOSSARY.md` and
  `DESIGN.md` still describe the clean-room skills as driver-lab's until LS8.
- Installing both plugins side by side was not exercised.
- The open format's rule for code-only facts is new wording (review S1), settled here rather
  than in the design; LS-R15 required the class to leave, not what replaces it.
- LS12's step "driver-lab's CI pin of public-skills bumped" no longer applies: the pin is gone.
