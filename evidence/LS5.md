<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS5: the three spec repositories

**Terms:** the *spec repositories* are `hardware-specs-gpl`, `hardware-specs-docs` and
`hardware-specs-permissive`, one public home for specs per license. Each has a *root marker*
(`specs/board-specs.yaml`) whose `accepts:` lists the licenses a cited source may carry; the
*license gate* fails a spec citing a source outside that list (`anchor_check.py --root` for a
peripheral spec's pins, and from this milestone `spec_check.py --require-license` for a board
spec's `resources.repos`). A *self-test* proves the gate inside each repository's CI with
fixture specs that are never published. See the [glossary](../GLOSSARY.md) and the
[design's terms](../docs/LICENSE-SPLIT.md#terms).

Design: [LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md) (LS-R11, LS-R12; proves LS-R4). Plan:
[LS5](../docs/LICENSE-SPLIT-PLAN.md#ls5--the-three-spec-repositories). Notebook:
[LS5](../notebook/LS5.md). Starting revision `85fa05b` (origin/main, LS1–LS4 merged); no
pre-existing changes.

**Status: in progress: awaiting publication.** Everything up to publication is done and
reviewed: the three repositories exist as local single-commit checkouts, and their CI steps pass
locally against this branch, each self-test failing the misfit with the gate's message and
passing the fit. Creating the public repositories, pinning their CI to this milestone's merge
commit and pushing are left to the orchestrator (rows marked *pending* below).

```text
hardware-specs-docs, scripts/checks.sh self-test (local):
self-test: fit docs-named-spec.md passed (exit 0)
self-test: misfit gpl-only-spec.md failed as required (exit 1) with:
    ERROR L13: license gate: [src: drivers/widget.c:2 (WIDGET_CTRL)] cites source pin 'linux'
    (GPL-2.0-only), which root <tmp>/anchors does not accept (accepts: none)
```

## What changed

**driver-lab** (this branch):

- `skills/board-expert/scripts/spec_check.py`: under `--require-license`, a `resources.repos`
  entry whose license the root's `accepts:` does not accept is an error,
  `license gate: repos entry '<name>' (<license>), which root <root> does not accept (accepts:
  …)`, on the spec's path, with `spdx.accepted`'s rules (`OR` any, `AND` all). Overlays are gated
  by their own root; an unparsable license is reported once, not gated. Without the flag nothing
  changes.
- `skills/board-expert/specs/board-specs.yaml`: `license: Apache-2.0`, `accepts: [Apache-2.0,
  MIT, BSD-2-Clause, BSD-3-Clause]`; CI's two marker warnings are gone.
- Fixtures under `skills/anchored-peripheral-spec/tests/fixtures/license-gate/`:
  `specs/docs-named-spec.md` (a `docs:` registry and named anchors; passes the docs root under
  `--require-license`), `specs/gpl3-only-spec.md` (a license no repository accepts: the GPL
  root's misfit), `board/widgetchip.spec.md` and two overlays on it with a BSD-3-Clause and a
  GPL-3.0-only `resources.repos` entry; `expected.json` rows; the README lists each repository's
  self-test pairs.
- Tests: `test_spec_check.py` class `BoardSpecGate` (11) and
  `GoodRoot.test_shipped_public_root_declares_its_license`; one LS2 test that asserted the old
  behavior now runs without the flag. `test_anchor_check.py`: the self-test pairs, and the named
  fixture in every root.
- `SPEC-FORMAT.md` (terms, license fields, checker list), `GLOSSARY.md` (license gate), the
  design's decisions table, the plan.

**Three repositories** (local, branch `main`, one commit each, no remote):

| Repository | Commit | Files | License, `accepts:` |
|---|---|---|---|
| `hardware-specs-gpl` | `b737c1b` | `.github/workflows/checks.yml`, `.gitignore`, `AGENTS.md`, `LICENSE`, `README.md`, `scripts/checks.sh`, `specs/board-specs.yaml` | GPL-2.0-only (SPDX text); GPL-2.0-only, GPL-2.0-or-later, Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause |
| `hardware-specs-docs` | `996d6a8` | the same plus `LICENSES/Apache-2.0.txt` | CC-BY-4.0 (SPDX legal code), CI files Apache-2.0; `[]` |
| `hardware-specs-permissive` | `85f76de` | the same as gpl plus `NOTICE` | Apache-2.0 (driver-lab's text) with NOTICE; Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause |

Each README's first screen holds what the repository holds, "Every claim is anchored, and the
checker runs in CI", a Terms paragraph, the placement rule and the design's "which repo" table
verbatim. `scripts/checks.sh <specs|anchors|self-test|all> <driver-lab> [<further root>]` holds
the steps and the workflow calls it per step, so a local run executes CI's code. The workflow
pins `actions/checkout` by the SHA driver-lab uses and checks out driver-lab at the placeholder
line `ref: DRIVER_LAB_PIN  # replaced at push`; the permissive repository also checks out
`hardware-specs-docs` at `main` as a second root (spec data only, no code runs from it).

The self-test copies the repository's own marker into temporary roots with these fixtures:

| Repository | Anchor gate fit / misfit | Board gate fit / misfit (beside `widgetchip.spec.md`) | Cross-repository overlay |
|---|---|---|---|
| gpl | `gpl-only` / `gpl3-only` | BSD overlay / GPL-3.0 overlay | — |
| docs | `docs-named` / `gpl-only` | none / BSD overlay | — |
| permissive | `bsd` / `gpl-only` | BSD overlay / GPL-3.0 overlay | BSD overlay fails alone (`resolves to nothing`), passes with the docs marker's root |

A misfit must exit 1 with a line matching `^ERROR L[0-9]+: license gate: .* does not accept
\(accepts: ` (anchors) or `^error: .*: license gate: repos entry ` (board), so neither the
informational `license gate: root … accepts:` line nor a pin with a missing or invalid license
can satisfy it.

## Acceptance

| Criterion | Evidence and result |
| --- | --- |
| All three repos exist, public, CI green on `main` | **Pending (orchestrator).** Locally, every step exits 0 in each repository against this branch: `ls5-local-ci-hardware-specs-{gpl,docs,permissive}.log` (session scratch). |
| Each self-test shows the misfit failing with the gate's message and the fit passing | **Met locally; CI log lines pending.** Local lines: gpl `misfit gpl3-only-spec.md failed as required (exit 1)` with `… cites source pin 'gnutool' (GPL-3.0-only), which root <tmp>/anchors does not accept (accepts: GPL-2.0-only, GPL-2.0-or-later, Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause)`; docs as quoted above; permissive `… pin 'linux' (GPL-2.0-only), which root <tmp>/anchors does not accept (accepts: Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause)`; each board misfit `license gate: repos entry …`; each fit `passed (exit 0)`. |
| The self-test can fail | Flipping markers in scratch copies fails it (`misfit gpl3-only-spec.md exited 0, expected 1`; docs likewise); the reviewer reproduced six ways, including origin/main's `spec_check.py` (`misfit widgetchip-gpl3-overlay.spec.md exited 0, expected 1`). |
| Board-spec gate: new tests fail on the old script | origin/main's `spec_check.py` swapped in, then restored and compared with `cmp` (`ls5-old-scripts.log`): `FAILED (failures=13, skipped=1)`, every gate test failing; the four characterization tests (no flag, accepted licenses, an invalid license reported once, cross-root overlay resolution) pass. The shipped-marker test fails with origin/main's marker and the fixture-pair tests with origin/main's fixtures (`ls5-old-fixtures.log`). |
| No private infrastructure in any file or commit message | `check-no-private-paths.py` from each repository: `OK: 7 tracked files`, `OK: 8`, `OK: 8`; a grep of files and `git log --format=%B` for host names, addresses, user names and home paths finds nothing. |
| driver-lab's full check list | All 12 commands exit 0 (`ls5-checks.log`, session scratch). |

## Decisions

- **The user's (2026-10-06)**, quoted in the [notebook](../notebook/LS5.md): the board-spec
  gate, the shipped marker's fields, and the go to create the repositories.
- **Accepts lists** are the design's named licenses only (the user's list for driver-lab's root,
  plus GPL-2.0 for the GPL repository); the fixture roots' extra ISC, 0BSD, X11 and Zlib were
  left out on review. Adding them is a question for the user.
- **Board fixtures in the self-test**, beyond the anchor pair the plan names: the new gate and
  the design's cross-repository overlay risk ("with a fixture in LS-R12") are otherwise unproven
  in the repositories.
- **Docs repository at `main`** in the permissive CI, not a pin; the docs repository must be
  pushed first.
- **docs repository licenses:** CI files Apache-2.0 with the text in `LICENSES/Apache-2.0.txt`.

## Review

One independent reviewer subagent with fresh context read the diff, the three repositories and
the logs, reran every check, and broke the self-test on purpose; findings in `ls5-review.md`
(session scratch). No blockers.

| # | Sev. | Finding | Resolution |
| --- | --- | --- | --- |
| 1 | should-fix | The anchor misfit pattern accepted any `license gate:` error, so a misfit with an invalid or missing pin license would pass | Pattern requires `does not accept \(accepts: `; a scratch run with `invalid-license-spec.md` as the misfit now fails the self-test |
| 2 | should-fix | Accepts lists added ISC, 0BSD, X11, Zlib beyond the design's names | Trimmed to the design's names; question raised for the user |
| 3 | should-fix | A peripheral spec not named `*-spec.md` would be checked by nothing | The anchors step fails on any Markdown under `specs/` other than `*-spec.md`, `*.spec.md`, `*.verify.md`, `README.md` (scratch run: `error: specs/enc28j60.md: not checked by anything`, exit 1) |
| 4 | should-fix | "Every fact names a line or page" overstated what CI enforces for board specs | First-screen text says board-spec facts carry a source tag and name documents and device trees; see Limitations |
| 5 | should-fix | The plan's LS2 limitation was stale; no evidence file | Annotated; this file |
| 6–10 | nit | Empty array under `set -u` on bash before 4.4; a comment slip; "accepts sources licensed nothing"; the overlay check skipped silently without a further root; misfit fixtures not in the precondition check | `${further[@]+…}`; comment rewritten; sentence rewritten; the permissive script requires its further root (exit 2); all fixtures checked (exit 3) |
| 11 | nit | Docs at `main` acceptable | Kept |

The fixes were checked by rerunning the local CI and the scratch probes above; no second review.

## Limitations

- Publication is pending: no repository exists on GitHub yet and no CI has run there.
- CI resolves no `[src:]` anchor against its tree (it has no checkout of the cited sources); it
  checks form, pins and licenses. Resolution is part of verification.
- Board-spec facts tagged `[inference]` or `[press]` pass the checks in every repository; whether
  public spec roots should forbid them is for the regeneration workstream.
- `scripts/checks.sh` was run with bash 5 only; the bash 3.2 handling of an empty further-root
  list is by construction, not by a run.
- After LS9's rename the fixture path in each `scripts/checks.sh` changes (one variable), with the
  repin.
