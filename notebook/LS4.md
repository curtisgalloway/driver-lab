<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS4 — placement guidance, provenance template and format docs

Milestone of the [license-split plan](../docs/LICENSE-SPLIT-PLAN.md#ls4--guidance-provenance-template-why-this-exists-format-docs).

### 2026-10-06T10:26-07:00 — opening

Goal: document what LS1–LS3 built and the policy around it (LS-R1 docs, LS-R7, LS-R8, LS-R9's
`spec-verifier` text, LS-R10): the placement rule and "which repo" table in
`anchored-peripheral-spec`, the format docs in `SPEC-FORMAT.md`, marker fields in the scaffold
templates, a private `PROVENANCE.md` template for `cleanroom-spec`, the verifier's anchored
procedure with named pins and the gate, and the README's "Why this exists" section. Starting
revision `b3a0440` (LS3's checkpoint, stacked on LS2 `7092822`; neither merged); worktree
`.claude/worktrees/ls4`, branch `license-split/ls4`, clean. Approach: write each document from
the scripts' own help and docstrings, then run every command the docs show against the
license-gate fixtures and log the runs.

### 2026-10-06T10:33-07:00 — decision: where "spec templates show named pins" lands

Plan step 3 asks the scaffold's spec templates to show named pins, but `board-spec-scaffold`'s
templates are board specs, which carry no pins (their sources are `resources.repos` entries,
whose `license:` the templates already show). The templates that state pins are
`anchored-peripheral-spec`'s spec-writer and verifier prompts, so named, licensed pins and the
`docs:` registry went there; the scaffold got only the marker's `license:`/`accepts:`
placeholders and one line in its root step. The design's repo table is copied verbatim into the
skill (the acceptance asks for an exact match), with a sentence explaining its "facts 2, 3, 6
below", which points into the design.

### 2026-10-06T10:33-07:00 — attempt: every documented command run against scratch specs

`ls4-verify.sh` (session scratch) builds a one-commit source tree, a 120-page "document" with a
known hash, and specs with two pins on one tree (`GPL-2.0-only` and `GPL-2.0 OR MIT`), and runs
each command and flag the docs show: the gate on the three fixture roots, `--require-license`,
`--docs-dir`, every registry fault, pin faults, `--drift --drift-pin --rewrite`, a named Target
pin, `--show`, `-o`, `inventory_check.py` with a named pin, `spec_check.py --require-license`.
Log `ls4-doc-commands.log`. Two claims I had drafted were wrong and were corrected: a pin given
no `--repo` is only a warning ("anchors not resolved"), not a failure; `--drift` with several
`--repo` checkouts requires `--drift-pin` (exit 2). One case was built wrong (a malformed pin
line in a two-pin spec stops at `--repo names pin 'linux-dt'`, exit 2) and was rerun on a
one-pin spec: warning, error under `--root`.

### 2026-10-06T10:33-07:00 — surprise: peripheral specs must not be named `*.spec.md`

`spec_check.py` loads every `*.spec.md` under a root as a board spec, so a peripheral spec named
`widget.spec.md` in a spec repository fails it (`unknown kind None`, exit 1); as
`widget-spec.md` it is ignored. `SPEC-FORMAT.md` now says to use the `<device>-spec.md` name
`anchored-peripheral-spec` already uses. Input for LS5's repository layout.

### 2026-10-06T10:39-07:00 — attempt: independent review and fixes

One reviewer subagent, fresh context: no blockers, three should-fix and five nits (findings in
the [evidence](../evidence/LS4.md#review)). The one that mattered: the spec-writer template
asked for several named pins but its inventory self-check still used a bare `--repo`, which
exits 2 on exactly that spec. All eight fixed in text; the repo table was byte-identical to the
design's. Full check list green (12 of 12, `ls4-checks.log`).

### 2026-10-06T10:39-07:00 — checkpoint (closing)

LS4 complete: placement rule and table, format docs for the LS1–LS3 tools, private provenance
template, README "Why this exists". Next: LS5, after the LS2–LS4 stack merges and the user gives
the go to create the three public repositories.
