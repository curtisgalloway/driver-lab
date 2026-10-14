<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 79

**Terms.** The patch gate checks an applied Codex patch; its digest hashes the worktree before
and after the suites. See the [glossary](../GLOSSARY.md).

## 2026-10-14 — What the digest did not see

The finding titles alone gave no reproduction, so the re-review asked what a suite could
change that the orchestrator would then commit. `git diff HEAD` compares the files on disk
with HEAD, so the index, HEAD and the git directory were all outside it. Review found two
more: a written `MERGE_HEAD`, and a forged entry in the index's cache of directory trees,
which `git commit` reuses and nothing lists. A `write-tree` of an index copy missed the
forgery (the root's cache entry stays honest), so the raw index is hashed; the cost is that
a suite running `git status` in the worktree now fails the gate. The gate's own `git diff`
refreshed the index too, and `--no-optional-locks` did not prevent it, so those diffs read
an index copy. The scan gap was a differential between git's text test (no NUL) and the
scans' (strict UTF-8). Fixed in the gate rather than in the shared check scripts, which CI
also runs. For #80's ignored paths, the worktree cannot say what the patch added under an
ignored name, so the patch is read with git's own parser instead. Closed with the
[acceptance evidence](../evidence/ISSUE-79.md).
