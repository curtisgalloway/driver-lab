<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS2 — root license fields and the license gate

Milestone of the [license-split plan](../docs/LICENSE-SPLIT-PLAN.md#ls2--root-license-fields-and-the-license-gate).

### 2026-10-06T09:54-07:00 — opening

Goal: root marker `license:` and `accepts:` validated by `spec_check.py` (warning when absent,
error under `--require-license`), `resources.repos[].license` validated as SPDX, a small SPDX
parser, and `anchor_check.py --root` failing anchors whose pin license the root does not accept
(LS-R1, LS-R2, LS-R4). Starting revision `88ca073` (origin/main, LS1 merged); worktree
`.claude/worktrees/ls2`, branch `license-split/ls2`, clean. Approach: characterization of the
marker and resource behavior first, then the parser, then each script, then fixture roots shaped
like the three spec repositories for LS5 to copy.

### 2026-10-06T09:59-07:00 — attempt: characterization, parser, both scripts

Characterization first: `LegacyMarkers` (a `layer`-only marker and a `layer`+`name` marker load
with no error; a repos entry may omit `license:`) passes on the unchanged checker. Then
`spdx.py` in `board-expert/scripts` (the plan's proposed location: `spec_check.py` imports it
directly, `anchor_check.py` through a path beside its own skill, together with `spec_check`'s
YAML reader and marker validation, so the marker rules live in one place). The two new absence
warnings broke seven existing exact-findings assertions; the test helpers now drop exactly
those two warnings (`without_license_absent`), and the fixture markers stay pre-LS2 on purpose.

### 2026-10-06T09:59-07:00 — decision: what the gate covers

Choices the design left open, all made toward failing closed: both sides are gated (`[tgt:]`
too: the design's repo table says what anchors each repo allows, not which side); a pin no
anchor cites is gated as well (a pin declares a source the spec derives from); a root with no
`accepts:` fails `--root` rather than skipping it; `accepts: []` is a declared empty list; a
pin license that does not parse is an error even without `--root` (LS1's open item); `WITH`
passes when its base license does; resource licenses are validated, not gated (LS-R2 asks only
for presence and validity). Known identifiers are a short list; anything else is an error
with a pointer to `LicenseRef-`.

### 2026-10-06T09:59-07:00 — attempt: fixtures shaped like the three repositories

`anchored-peripheral-spec/tests/fixtures/license-gate/`: `roots/{gpl,docs,permissive}` markers
and 13 specs, with `expected.json` holding the exit code per spec and root (the test asserts
the file and the directory agree). Self-contained: no git repository needed, so LS5 can copy
the directory. Matrix run by hand matched `expected.json`; the suite now has 64 anchor tests
and 58 board-expert tests (7 of them `spdx.py` table tests).

### 2026-10-06T10:09-07:00 — attempt: tests against the old code; one could not fail

With `origin/main`'s scripts swapped in (and `spdx.py` removed), every new `RootLicense` and
gate test failed, but `test_repo_license_is_not_gated_by_accepts` passed: it guards against
over-gating, which code that ignores licenses cannot do. Folded into a test that fails on the
old code. This corrects the 09:59 entry's count: board-expert now has 57 tests, not 58.

### 2026-10-06T10:09-07:00 — attempt: review-swarm and fixes

Seven arms and a referee; 5 findings kept (see the [evidence](../evidence/LS2.md#review)). The
one that matters: a pin line the pattern did not read (lowercase `or`, `DocumentRef-…:`, spaced
parentheses) was silently not a pin, so with two pins an unnamed anchor could bind to the other
one and pass the gate. Now such licenses are read and rejected with the parser's message, and
any other pin-shaped line warns, failing under `--root`. All fix tests fail on the old and
pre-fix scripts; full check list green again.

### 2026-10-06T10:09-07:00 — checkpoint (closing)

LS2 complete: gate, marker and resource license checks, 21 gate tests, 7 parser tests,
fixtures for LS5. Next: LS3 (may already be running) and LS4.
