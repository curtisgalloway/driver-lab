<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Spec regeneration — implementation plan

Approved by the user on 2026-10-07. Notebook: [RG-regen](../notebook/RG-regen.md); review
learnings rollup: [SPEC-REGEN-learnings](../notebook/SPEC-REGEN-learnings.md).

**Terms.** A *spec* is a board, SoC or IP-block description in the format of
[`SPEC-FORMAT.md`](../skills/board-expert/SPEC-FORMAT.md). A *root* is a spec directory with a
`board-specs.yaml` marker naming its license and the source licenses it accepts; the three
published roots are `hardware-specs-docs` (documents only), `hardware-specs-permissive` (also
BSD, MIT, ISC, 0BSD, Apache and `GPL-2.0 OR MIT` sources) and `hardware-specs-gpl`. An *overlay*
is a spec in one root that adds facts to a spec in another. Everything else:
[glossary](../GLOSSARY.md).

## Goal

Regenerate the 11 specs deleted on 2026-10-01 ([license-split design,
History](LICENSE-SPLIT.md#history-the-11-deleted-specs-2026-09-30-to-10-01)) into the three spec
repositories, with the current skills, each fact in the root its source's license allows. Along
the way, measure what the skills and the verifier miss, using Codex as an independent second
reviewer, and turn that into skill changes.

**Non-goals:** the four per-board expert stubs (`rpi-expert` and the others; board bring-up
lives in bringup-kit); new specs beyond the 11; changing `SPEC-FORMAT.md` except where a unit
proves a change is needed (then it is its own driver-lab pull request).

## Rules for every unit

- **From sources, not from the deleted text.** The implementer may read the deleted spec
  (driver-lab `6f69cf5^`) for its list of topics only. Every fact is re-derived from the source it
  cites; no sentence is copied. The design's [audit of the 12
  facts](LICENSE-SPLIT.md#audit-of-the-12-facts-2026-09-30) says where those facts belong.
- **Placement by license, fact by fact.** Default root: `hardware-specs-docs`. A fact whose only
  support is a permissively licensed source goes in a `hardware-specs-permissive` overlay; one
  whose only support is GPL source goes in a `hardware-specs-gpl` overlay. A fact with no source
  any root accepts is left out and listed in the unit's evidence.
- **One fresh implementer subagent per unit, Opus 5.5** (user choice, 2026-10-07). It commits on
  a topic branch in each spec repository it touches; it does not push.
- **Gates, in order:** (1) each touched repository's `scripts/checks.sh` passes; (2)
  `spec-verifier` (fresh subagent) checks every claim and writes its verification record;
  (3) **Codex** reviews the same claims, with the spec, its list of cited sources and the
  verifier's record in hand, asked for claims the verifier passed but should not have, for
  missing coverage, and for **sources the spec should have cited but did not**. It runs with
  network access in a throwaway scratch directory (`--sandbox workspace-write` with
  `sandbox_workspace_write.network_access=true`; user decision 2026-10-07), never in a checkout;
  (4) the implementer fixes accepted findings; checks and the verifier re-run on changed claims.
- **Every review finding is recorded** in the unit's notebook entry as a row: reviewer (verifier
  or Codex), claim, finding, accepted or rejected (why), whether the other reviewer also caught it,
  and which skill or format rule would have prevented it. The rollup collects the proposed skill
  changes across units; they are made in separate driver-lab pull requests, not inside a unit.
- **Records:** the run ledger (private run store) holds identities, commands, transcripts'
  paths and attempts; `evidence/RG<n>.md` holds conclusions and limitations; the notebook
  holds findings and dead ends; this plan holds status.
- **Git:** one branch and pull request per repository per unit; spec-repository pull requests
  merge after green CI. Merge commits.

## Units

| # | Unit | Kind | Expected roots | Notes | Status |
|---|---|---|---|---|---|
| RG1 | `bcm2711` | SoC | docs + permissive overlay | Audit facts 2, 3, 6 to the overlay at `raspberrypi/tools@439b619`; proves cross-repo overlays | complete ([evidence](../evidence/RG1.md)); also a GPL overlay (all BCM2711 device trees are GPL-2.0-only) |
| RG-T1 | `[src]` class and checker | tooling | driver-lab + spec-repo CI | Added during RG1 (user decision) | complete; merged as is, Markdown grammar to be retired ([evidence](../evidence/RG1.md#rg-t1-the-checker)) |
| RG2 | `rpi4` | board | docs (+ overlay if needed) | Reads RG1 | not started |
| RG3 | `pl011` | IP block | docs | Arm TRM is the main source | not started |
| RG4 | `dw-apb-uart` | IP block | docs | Synopsys databook availability decides coverage | not started |
| RG5 | `bcm2712` | SoC | docs (+ overlays) | | not started |
| RG6 | `rp1` | companion chip | docs (+ overlays) | | not started |
| RG7 | `rpi5` | board | docs (+ overlays) | Reads RG5, RG6 | not started |
| RG8 | `rk3588s` | SoC | docs + overlay for DT facts | Audit fact 1 | not started |
| RG9 | `indiedroid-nova` | board | docs (+ overlays) | Reads RG8 | not started |
| RG10 | `tensor-g5` | SoC | to be decided | Needs the `[repo]` tag decision first (tag `archive/source-observed-audit-fixes`) | blocked on decision |
| RG11 | `pixel10` | board | to be decided | Same decision; audit facts 7–10 | blocked on decision |

Order: the Raspberry Pi 4 chain first (it carries the decided overlay), then the UART IP blocks
the boards reference, then Pi 5, Rockchip, and the Google pair last. One unit per session.

## Risks

- **Device-tree licenses.** `[DT]` facts cite device-tree source. Many mainline `.dts` files are
  `GPL-2.0` only, which neither docs nor permissive accepts; others are `GPL-2.0 OR MIT`. RG1
  will show how many facts move to a GPL overlay because of this; if most do, revisit placement
  before RG2.
- **Codex access to sources.** Its read-only sandbox has no network (measured 2026-10-07: curl
  failed DNS, web fetch missed, web search found only `master`), so it runs networked in a
  scratch directory instead. A source it fetches may differ from the pinned revision; the
  notebook records any mismatch.

## Next session

- Current unit: none. RG1 and RG-T1 are complete and merged (2026-10-08).
- **Paused for a format change** (user decision, 2026-10-08): specs, board and peripheral, move
  from Markdown with inline tags to YAML validated by a JSON Schema, rendered to Markdown (and
  later a viewer and search) for reading. Eight review rounds of the Markdown checker showed the
  ambiguity is in Markdown itself. Resume action: write the format design for the user's
  approval; then convert RG1's three specs and continue with RG2 in the new format.
- Before RG2: apply the verifier and scaffold learnings in the [rollup](../notebook/SPEC-REGEN-learnings.md).
