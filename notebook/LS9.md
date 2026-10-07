<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS9: Rename `anchored-peripheral-spec` to `peripheral-spec`

Milestone of the [license-split plan](../docs/LICENSE-SPLIT-PLAN.md#ls9--rename-anchored-peripheral-spec-to-peripheral-spec).

### 2026-10-07 — opening

Goal: LS-R16. Starting revisions: driver-lab `9003213`, `cleanroom-skills` `b0e36f7`, the three
spec repositories at `main`. Approach: rename the directory first, then replace the name in every
file outside the archive, then the prose, then the other four repositories, then check.

### 2026-10-07 — dead end: the first replace touched history

The file list for the name replacement was built with `grep -rIl … .` and filtered with patterns
that began `^./`. Without a leading `./` in the output the filter matched nothing, so the
replace also rewrote `evidence/`, `notebook/`, `docs/` and `TRANSITION.md`. `git status` showed
it before anything was staged; `git checkout --` on those paths restored them. After that, the
file list was printed and read before each replace.

### 2026-10-07 — decision: which "anchored" stays

"Anchored" has two meanings in the open skills: the kind of spec (renamed) and how a fact is
cited, or a board-attached mode of IP resolution ("anchored or generic"). Only the first moved;
a global replace of "anchored" would have broken the second. The `spec-verifier` section heading
counts as the first, so it and its four references were renamed together after the reviewer
noticed they disagreed.

### 2026-10-07 — decision: pins and permalinks

The spec repositories pin the LS9 commit, so the driver-lab commit comes first. A permalink in
`cleanroom-skills/DESIGN.md` that cited a fixed version also moves to that commit, not `main`.

### 2026-10-07 — review and checkpoint

One reviewer: three should-fix, two nits, all resolved (evidence). Checks rerun; checkpoint
commits in the five repositories on `license-split/ls9`. Next: LS10.
