<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS3 — checkable doc anchors

Milestone of the [license-split plan](../docs/LICENSE-SPLIT-PLAN.md#ls3--checkable-doc-anchors).

### 2026-10-06T10:14-07:00 — opening

Goal: a `docs:` registry in spec front matter and named `[doc:<name> p.N]` anchors checked
against it (unknown name, page out of range, malformed sha256), `--docs-dir` hash checks, and
unnamed `[doc: …]` anchors unchanged except where named ones are required (LS-R5). Starting
revision `7092822` (LS2's checkpoint, stacked; LS2 not yet merged); worktree
`.claude/worktrees/ls3`, branch `license-split/ls3`, clean. Approach: characterization tests of
today's doc-tag behavior first, then the registry, the anchor grammar, the hash check and the
requirement, each with tests shown to fail on LS2's scripts.

Found on reading: `anchor_check.py` reads no front matter today; it scans every line, so a
front-matter `- name:` line would count as a list item (an untagged-fact error under
`--strict`). Every `[doc:` tag in the repository has a space after the colon (`git grep` finds
none without), which leaves the no-space form free for named anchors.

### 2026-10-06T10:17-07:00 — decision: where the named-anchor requirement lives

The design puts it in `hardware-specs-docs` ("where `--require-license` also requires named
ones"), and LS-R1 has all three spec repositories run `--require-license`, so a plain flag
would also reject unnamed anchors in the GPL and permissive repos, which the design keeps
valid. Chosen: `anchor_check.py --require-license` (needs `--root`) mirrors spec_check's flag
on DIR's marker (a missing `license:` is an error) and, in a root whose `accepts:` is empty,
the only shape a datasheet-only root has, makes every unnamed `[doc: …]` an error. All three
repos can then pass the same flag to both tools. Rejected: a separate `--require-named-docs`
flag (one more thing each repo's CI must get right) and keying on the marker's `name:`.

### 2026-10-06T10:17-07:00 — decision: named versus unnamed is the space after `doc:`

`[doc:trm p.12]` is named; `[doc: trm p.12]` is the old free-text form. Deciding by content
("one word, then locators") would turn an existing `[doc: UG585 §16.3]` into an unknown-name
error. A no-space tag that is not `<name> <locator>…` is an error whose message says to add the
space for a free-text citation. Front matter (a leading `---` block with a closing `---`) is
now skipped by the body scan; without the closing line it is body text, as before.

### 2026-10-06T10:17-07:00 — attempt: characterization, implementation, old-code run

Five characterization tests of unnamed doc tags pass on LS2's checker and after the change.
Then the registry, named anchors, `--docs-dir` and the requirement, with 20 new tests (93 in
the suite, all pass). With LS2's `anchor_check.py` swapped back in: `Ran 93 … FAILED
(failures=21, errors=2)`; all 20 new tests fail, the 73 others pass; restored and compared
with `cmp`. Log `ls3-old-scripts.log` in the session scratch.

### 2026-10-06T10:24-07:00 — attempt: independent review and fixes

One reviewer subagent, fresh context: no blockers, one should-fix, three nits (findings in the
[evidence](../evidence/LS3.md#review)). The one that mattered: a spec opening with a `---`
horizontal rule had its first section skipped as "front matter", so a malformed anchor there
passed. Now a leading block is front matter only when it has a `docs:` line, or parses as a
YAML mapping and carries no anchor tag; otherwise it is scanned as before. Corrects the 10:17
entry's count: there are 25 new tests (5 characterization, passing on LS2 by design, and 20,
now 21, behavior tests that fail there). After the fixes: LS2's script `failures=22,
errors=2` across all 21 behavior tests; the pre-fix LS3 script fails the 3 fix tests. Full
check list green again (12 of 12).

### 2026-10-06T10:24-07:00 — checkpoint (closing)

LS3 complete: docs registry, named doc anchors, `--docs-dir` hashes, `--require-license` on
`anchor_check.py`. Next: LS4, whose format docs should cover the registry, the space rule,
`--docs-dir` and `--require-license` (review nit 3).
