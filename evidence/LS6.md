<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS6: `cleanroom-skills` created with history

**Terms:** *`cleanroom-skills`* is the public repository and plugin that holds the clean-room
skills, split out of driver-lab; it depends on driver-lab, never the reverse. *`git
filter-repo`* rewrites a repository's history to keep only chosen paths, giving every kept commit
a new hash; its *commit map* lists old and new hashes. The *portability scan* is public-skills'
check that agent-facing scripts work under any coding agent. See the
[glossary](../GLOSSARY.md) and the [design's terms](../docs/LICENSE-SPLIT.md#terms).

Design: [LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md) (LS-R14 repository part, LS-R8 move). Plan:
[LS6](../docs/LICENSE-SPLIT-PLAN.md#ls6--cleanroom-skills-created-with-history). Notebook:
[LS6](../notebook/LS6.md). Starting revision `5d7eac2` (origin/main, LS5 merged).

**Status: complete** (published 2026-10-06 by the orchestrator, on the user's go). The
repository is public at `curtisgalloway/cleanroom-skills` with all 23 commits, and its first CI
run is green.

```text
git log --follow --format='%h %ad %s' --date=short -- skills/cleanroom-investigator/SKILL.md
225d95d 2026-10-06 driver-porting: LS6 — rename os-investigator to cleanroom-investigator
e402e93 2026-10-01 Remove the published board specs and per-board expert stubs
06f4141 2026-09-18 driver-porting: adjudication items, and an [inference] provenance tag
4b61868 2026-09-18 driver-porting: fix the 18 defects the third Pixel 10 run surfaced
6285e53 2026-09-18 driver-porting: fix the 15 defects the second Pixel 10 run surfaced
19602c0 2026-09-18 driver-porting: IP specs, instance tables, the question catalog, and a vendor guide
312b09a 2026-09-01 Package the skills by theme: plugins/<theme>/ with a README and plugin each (#32)
```

## What changed

**`cleanroom-skills`** (local, branch `main`, no remote): 21 filtered commits from driver-lab
`5d7eac2`, then

| Commit | Content |
| --- | --- |
| `225d95d` | `os-investigator` → `cleanroom-investigator` in the skill's name field and title and in every reference inside the three skills; references to `board-expert`, `anchored-peripheral-spec`, `spec-verifier`, `board-expert/QUESTIONS.md` and the license-split design say they are driver-lab's, installed alongside. Nothing else. |
| `adeb0ff` | `README.md`, `AGENTS.md`, `GLOSSARY.md`, `TRANSITION.md`, `LICENSE` (driver-lab's), `.gitignore`, `.claude-plugin/plugin.json` and `marketplace.json` (both `cleanroom-skills`), `.github/workflows/checks.yml`, `history/driver-lab-commit-map.txt` (21 rows), `utilities/check-no-private-paths.py` (driver-lab's, byte-identical) |

Tree: `skills/cleanroom-spec/` (SKILL.md, templates incl. `PROVENANCE.md`),
`skills/cleanroom-implementer/` (hooks, sandbox, audits, 61 tests),
`skills/cleanroom-investigator/` (`leak_scan.py`, 7 tests), and the files above.

The README's first screen: what the method is, that its output is never published and each user
keeps a private `PROVENANCE.md`, what it is not for (laundering GPL code: use driver-lab's
`anchored-peripheral-spec` instead), that it depends on driver-lab installed alongside, links to
driver-lab's `evals/` and `evidence/` at `5d7eac2`, and a Terms block. CI pins `actions/checkout`
at `3d3c42e5…` and public-skills at `d63e3f14…`, as driver-lab's workflow does, and runs the
portability scan, the privacy check and the two moved test suites (`cleanroom-spec` has none).

## Acceptance

| Criterion | Evidence and result |
| --- | --- |
| The repo is public, CI green | **Met.** `gh repo view --json isPrivate,visibility` gives `{"isPrivate":false,"visibility":"PUBLIC"}`; CI run 37553309706 `completed success`, its log showing `0 finding(s)`, `OK: 46 tracked files, no absolute home paths`, `Ran 7 tests … OK`, `Ran 61 tests … OK`. Before publication: Locally every CI step exits 0: portability `0 finding(s)`, privacy `OK: 46 tracked files, no absolute home paths`, `Ran 7 tests … OK`, `Ran 61 tests … OK` (`ls6-local-ci.log`, session scratch, run before and after the review fixes). |
| `git log --follow` on a moved file shows pre-split history | Met: quoted above, seven commits from 2026-09-01. The reviewer found the same commit counts in both repositories for six files and every file's content identical to driver-lab `5d7eac2`. |
| Name field and every internal reference use the new name; no `os-investigator` outside history and the commit map | Met: `name: cleanroom-investigator`; a whole-tree grep finds the old name only in `TRANSITION.md` (lines 22, 33, describing the rename) and the commit map header. |
| Installed beside driver-lab, the moved tests pass | Met for the tests (they need nothing from driver-lab). Installing both plugins side by side was not exercised. |
| Privacy check on files and new commit messages | Met: `check-no-private-paths.py` OK; a grep of the tree and of both new commit messages for host names, addresses, user names and home paths finds only the checker's fictional `/home/dev` fixture paths. Author is the noreply address. |
| Nothing outside the three skills came in with the filter | Met (reviewer): 35 distinct paths across all history, all under the three directories; one ref, no remotes, no tags. |

## Decisions

- **The user's (relayed with the brief):** name `cleanroom-skills`, public from day one; the
  rename; evals frozen in driver-lab and linked at a pinned commit; `RECONSTRUCTION.md` and
  `QEMU-DIFFERENTIAL.md` stay.
- **Pinned driver-lab commit for the links:** `5d7eac2`, the commit the history was cut from.
- **Commit map keeps only kept commits** (21 rows), as driver-lab's map does.
- **`GLOSSARY.md` added**, beyond the plan's file list, per the user's one-glossary-per-repo rule.
- **Overlap until LS7:** the README tells users to call the skills by plugin-qualified name or
  disable driver-lab's copies; LS7 deletes that paragraph.

## Review

One independent reviewer subagent with fresh context read the tree, all 21 commit-map rows, the
new commits and the CI log, and reran every step; findings in `ls6-review.md` (session scratch).
No blockers.

| # | Sev. | Finding | Resolution |
| --- | --- | --- | --- |
| 1 | should-fix | `TRANSITION.md` and the map header said the history starts at driver-lab's import; its root is public-skills' 2026-09-01 commit, and a pre-split hash may be a public-skills one | Reworded: two-step translation through driver-lab's map, then this one |
| 2 | should-fix | "Prefer the copies here" did not say how, with both plugins installed | README names plugin-qualified invocation or disabling driver-lab's copies; LS7 to delete the paragraph |
| 3–5 | nit | README: verifier read as a second gate; "answered without source" ambiguous; link text named the directory | Reworded |
| 6–9 | nit | Redundant title qualifier; lines past 100 columns in the rename commit; glossary lacks harness, orchestrator, verifier, landed spec, databook; workflow comment about public-skills' example points at driver-lab's copy until LS12 | Left: cosmetic, or settled by later milestones |

The fixes were checked by rerunning the local CI and the old-name grep; no second review.

## Limitations

- Installing both plugins at once was not exercised; the duplicate skill names are handled by a
  README note until LS7.
- `cleanroom-spec` has no tests; CI runs two suites.
- public-skills' `agent-agnostic-skills` still points at driver-lab's `cleanroom-implementer`
  scripts (LS12).
