<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS5 — the three spec repositories

Milestone of the [license-split plan](../docs/LICENSE-SPLIT-PLAN.md#ls5--the-three-spec-repositories).

### 2026-10-06T17:17-07:00 — opening

Goal: LS-R11 and LS-R12, in two parts. In driver-lab: the board-spec license gate and the
shipped root marker's license fields (both the user's decisions, next entry), a named-anchor
docs-only fixture for the docs repository's self-test, `SPEC-FORMAT.md`. Outside it: three local
repositories, `hardware-specs-gpl`, `hardware-specs-docs` and `hardware-specs-permissive`, one
commit each, with CI that pins driver-lab and a self-test of the gate; the orchestrator creates
the GitHub repositories and pushes. Starting revision `85fa05b` (origin/main, LS1–LS4 merged);
worktree `.claude/worktrees/ls5`, branch `license-split/ls5`, clean. This entry is written after
the work below had started; the entries that follow record it in order.

### 2026-10-06T17:17-07:00 — direction: the user's decisions of 2026-10-06

Relayed by the orchestrator with the milestone brief:

- **Board-spec gate:** "`spec_check.py --require-license` also fails a board spec whose
  `resources.repos[].license` the root's `accepts:` does not accept (same SPDX rules as the
  anchor gate; message names spec, repo, license, accepts list)."
- **Shipped root marker:** "`skills/board-expert/specs/board-specs.yaml` gets `license:
  Apache-2.0` and `accepts: [Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause]` (CI's two warnings go
  away)."
- **Repositories:** the orchestrator has the user's go to create the three public repositories
  under `curtisgalloway` and push them.

The first closes LS2's open limitation ("board specs' resource licenses are validated, not
gated"); the second closes its other one (the shipped root's two warnings).

### 2026-10-06T17:17-07:00 — attempt: the board-spec gate, tests first against the old script

`check_repo_license` now compares a parsed repos license with the root's accepts list when
`--require-license` is given, using `spdx.accepted` (the anchor gate's rule); an unparsable
license is reported once and not gated. The message is
`license gate: repos entry 'fw' (GPL-2.0-only), which root <root> does not accept (accepts: …)`
on the spec's path. One LS2 test asserted the old behavior (GPL-2.0-only passing under
`--require-license` in a root accepting Apache-2.0 and MIT); it now runs without the flag, and
the flagged case is a new test. With origin/main's `spec_check.py` swapped in
(`ls5-old-scripts.log`, session scratch): the seven gate tests fail, the four characterization
tests pass; swapped back and compared with `cmp`.

### 2026-10-06T17:17-07:00 — decision: self-test pairs, and a misfit for the GPL root

Each repository's self-test needs a spec that fits its root and one that does not. The GPL root
accepts every licensed fixture LS2 wrote, so its only misfits failed for a missing or invalid
license rather than an unaccepted one. Added `gpl3-only-spec.md` (GPL-3.0-only, which no
repository accepts) and `docs-named-spec.md` (a `docs:` registry, named anchors), which passes
the docs root under `--require-license` where LS2's `docs-only-spec.md` fails (LS3's
limitation). Pairs: GPL `gpl-only`/`gpl3-only`; docs `docs-named`/`gpl-only`; permissive
`bsd`/`gpl-only`.

### 2026-10-06T17:17-07:00 — decision: board fixtures in the self-test, and the cross-repo overlay

The design's risk section asks for the cross-repository overlay to be proven "with a fixture in
LS-R12", and the new board gate is otherwise unexercised in the repositories. Added
`license-gate/board/`: `widgetchip.spec.md` (documents only) and two overlays on it, with a
BSD-3-Clause and a GPL-3.0-only `resources.repos` entry. The self-tests check the board gate with
them, and the permissive one also places `widgetchip.spec.md` under the docs repository's marker
and shows the BSD overlay failing alone (`resolves to nothing`) and passing with both roots.

### 2026-10-06T17:17-07:00 — decision: accepts lists, CI shape, the docs checkout

- **Accepts lists** copy the fixture roots LS2 shaped like the repositories (the permissive
  list adds ISC, 0BSD, X11 and Zlib to the BSD/MIT/Apache names); the GPL list is GPL-2.0-only,
  GPL-2.0-or-later and the permissive list, as the design's table says. The shipped board-expert
  root keeps the user's shorter list.
- **One script per repository**, `scripts/checks.sh <step> <driver-lab> [<further root>]`, holds
  the steps; the workflow calls it once per step, so a local run executes the same code as CI.
- **driver-lab pin:** a single `ref: DRIVER_LAB_PIN  # replaced at push` line, for the
  orchestrator to replace with LS5's merge commit. The permissive repository checks out
  `hardware-specs-docs` at `main`, not a pin: it reads only spec data from it, and an overlay
  should resolve against the docs specs as published. Consequence: the docs repository must
  exist before the permissive one's first CI run.
- **docs repository licenses:** specs, marker and prose CC-BY-4.0; CI files Apache-2.0, with the
  text in `LICENSES/Apache-2.0.txt` (the design's "per-file Apache-2.0 SPDX headers on CI
  files").

### 2026-10-06T17:17-07:00 — surprise: two faults in the first self-test script

The first local run (`ls5-local-ci-*.log`, overwritten by the reruns) passed every check and
then exited 1: the `EXIT` trap named a `local` variable that no longer existed when it fired
(`tmp: unbound variable` under `set -u`). Reading that log also showed the misfit check could
not tell a gate failure from any other: it looked for `license gate:` in the output, and
`anchor_check.py` prints `license gate: root … accepts: …` for every spec under `--root`, pass or
fail. The patterns now match only error lines (`^ERROR L[0-9]+: license gate: `,
`^error: .*: license gate: repos entry `). Flipping the GPL and docs markers in scratch copies
then failed both self-tests (`misfit … exited 0, expected 1`).

### 2026-10-06T17:17-07:00 — attempt: licenses, local CI, commits

License texts from SPDX's license-list-data (`GPL-2.0-only.txt`, `CC-BY-4.0.txt`), checked for
sections 0–12 and "END OF TERMS AND CONDITIONS", and Sections 1–8 with the closing notice;
Apache-2.0 copied from driver-lab's `LICENSE`. All three repositories' checks pass locally
against the worktree (`ls5-local-ci-hardware-specs-{gpl,docs,permissive}.log`). One commit each,
privacy check clean in each (`OK: 7`, `8`, `8 tracked files`), and a grep for host names,
addresses, user names and home paths found nothing.

### 2026-10-06T17:24-07:00 — attempt: independent review and fixes

One reviewer subagent, fresh context (`ls5-review.md`, session scratch): no blockers, five
should-fix and six nits. It proved the self-test can fail six ways (marker widened, marker
emptied, fit license removed, pre-LS5 `spec_check.py`, a misfit failing for another reason) and
found the license texts byte-identical to SPDX's and the repo table identical in all five places.
Fixed: the anchor misfit pattern now requires `does not accept (accepts: ` (an invalid or
missing pin license used to satisfy it; a scratch run with `invalid-license-spec.md` as the
misfit now fails the self-test); Markdown under `specs/` that no check reads fails the anchors
step; the first-screen sentence says what CI enforces for board specs; bash before 4.4 handles
an empty further-root list; the permissive repository requires its further root; all fixture
files are preconditions; comment and wording slips; the plan's stale LS2 note. Each repository's
single commit was amended; local CI and the privacy check rerun clean.

### 2026-10-06T17:24-07:00 — decision (corrects the accepts-list entry above): the design's names only

The reviewer pointed out that ISC, 0BSD, X11 and Zlib are not in the design's "BSD, MIT or
Apache", and that each repository's AGENTS.md calls widening `accepts:` the user's decision. The
markers now carry the list the user chose for driver-lab's own root: permissive `[Apache-2.0,
MIT, BSD-2-Clause, BSD-3-Clause]`, GPL the same plus GPL-2.0-only and GPL-2.0-or-later. Widening
later breaks nothing that is published; narrowing after publication could. Raised with the
orchestrator as a question for the user. The driver-lab fixture roots keep their wider lists
(they test the parser on more identifiers).

### 2026-10-06T17:31-07:00 — checkpoint (closing): published

Orchestrator: PR #48 merged as `5d7eac2`; each repository's `DRIVER_LAB_PIN` replaced with it,
`scripts/checks.sh all` rerun against driver-lab at that commit (all exit 0), the single
unpublished commits amended; `hardware-specs-docs`, then `-gpl` and `-permissive` created
public and pushed. First CI runs green (docs 37552264900, gpl 37552281514, permissive
37552293363), self-test lines quoted in the evidence. LS5 complete.
