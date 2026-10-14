<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 79 — Patch gate state drift and scan gaps

**Terms.** The patch gate (`utilities/patch-gate.py`) checks a Codex patch after it is
applied to a worktree. Its digest is a hash of the worktree taken before the suites run and
compared afterwards. The index is git's staging area. See the [glossary](../GLOSSARY.md).

The review findings "fail-open-state-drift" and "parser-differential" arrived as titles only.
A re-review at main found two kinds of hole, and #80's second limit had the same shape as the
second:

- **State drift.** The digest covered `git diff HEAD` and untracked files only. A suite could
  stage content and restore the file on disk, commit, switch branches, set index flags, write
  a hook or config, leave a `MERGE_HEAD` (the next commit becomes a merge with an unscanned
  parent), or forge the index's cache of directory trees (the next commit records files that
  `ls-files` and `git status` never show), and the gate still passed. The digest now also
  covers HEAD and its branch, the raw index file, and the git directory's `config`,
  `config.worktree`, `hooks`, `info` and merge, cherry-pick, revert and rebase state.
- **Scan skips.** Git treats a file as text unless it holds a NUL byte, but the privacy and
  open-side scans skip files that are not valid UTF-8, skip some suffixes (`.pdf`, `.zip` and
  the like) outright, and follow symlinks. A changed or new path that is a symlink, a
  directory, not UTF-8, or has a skipped suffix now fails the gate.
- **Ignored paths (#80).** A file the patch adds under an ignored name never reached the
  untracked scan. The gate now takes the patch's paths from `git apply --numstat` and fails on
  any that `git check-ignore` reports. A patch git cannot parse fails the gate.

| Acceptance | Evidence |
| --- | --- |
| Stage-then-restore fails | `test_suite_that_stages_then_restores_fails` |
| Commit, index flag, hook, config, hooks path, exclude, `MERGE_HEAD` and branch switch fail | `test_suite_that_changes_git_state_fails` (8 cases) |
| A forged directory-tree cache fails | `test_suite_that_forges_the_index_tree_cache_fails` (the forgery stays out of `ls-files`) |
| A non-UTF-8 tracked file, or one replaced by a symlink to a readable file, fails | `test_non_utf8_or_symlinked_tracked_file_fails` |
| A text file with a skipped suffix fails | `test_text_file_with_a_skipped_suffix_fails` |
| Touching an unchanged tracked file does not fail | `test_suite_that_only_touches_a_tracked_file_passes` |
| A tab in an ignored patch path survives parsing | `test_patch_path_hidden_by_ignore_rules_fails` |
| A deletion is not flagged | `test_deleted_file_is_not_unscannable` |
| An ignored new file fails; a tracked file matching an ignore rule does not | `test_patch_path_hidden_by_ignore_rules_fails` |
| An unparsable patch fails | `test_patch_git_cannot_parse_fails` |
| The tests fail without the fix | Reverting `patch-gate.py` alone: 15 failures of 31; the private-index and tab parsing changes each fail their own test when undone |
| No false positive end to end | Gate with default suites on a fresh clone, once with a new-file patch and once with a tracked-file patch: digest unchanged, spec-format 673 tests OK |

The gate's 31 tests pass. The first review round blocked on the merge state and the tree
cache; hashing a `write-tree` of a copy of the index was tried for the cache and missed it,
because the root's cached tree stays honest and only a later `git add` exposes the forged
subdirectory. The raw index is hashed instead. The second round found that the gate's own
`git diff` rewrites the index when a file's timestamp moves without its content changing,
which failed a harmless suite. `--no-optional-locks` did not stop that with the git version
here, so the gate's own diffs now read a private copy of the index (`GIT_INDEX_FILE`) and
never write the real one. In the end-to-end run the utilities suite failed only on the two
`test_codex_review` cases that fail on this host without the change (a stray `.git` marker in
the system temporary directory; see Issue 78's evidence). Private artifacts: run
`issue-79-20261014`.

Limitations: a process that leaves its process group can still change the worktree after the
gate (#80, first limit); the orchestrator should recheck before committing. The hooks and
config are shared by every worktree of the checkout, so another session changing them during
a gate run (`git worktree add -b`, `push -u`) fails that run, and so does a suite that runs
`git status` or `git add` in the worktree, since either rewrites the index. These failures
are safe. State outside the repository (global git config, the home directory) is not
covered. An empty patch fails, since `git apply --numstat` refuses it. A patch to a tracked
text file with a skipped suffix (the repository's one `.stl` model) fails as unscannable.
The scans still skip non-UTF-8 files in CI; only the gate refuses them.
