<!--
SPDX-FileCopyrightText: 2026 Curtis Galloway
SPDX-License-Identifier: Apache-2.0
-->

# License split for published hardware specs (design)

Status: **design, revision 2026-10-05, approved by the user 2026-10-05.** The open decisions of the
2026-09-30 draft are settled (see [Decisions](#decisions)); requirements carry labels LS-R1 to
LS-R20 for the [implementation plan](LICENSE-SPLIT-PLAN.md). Nothing below is built yet except
the deletion of the old specs (PR #42).

## Terms

- **Spec** — a hardware description an agent reads instead of the original sources. A **board**
  spec covers a board or SoC; a **peripheral spec** (today "anchored spec") covers one device
  and cites source lines for each fact.
- **Anchor** — a citation inside a spec: `[src: path:L]` points at a line of a pinned source
  tree, `[doc: …]` at a document. A **pin** (`Source pin: linux@abc123`) names the tree and its
  commit.
- **Root** — a directory of specs with a `board-specs.yaml` **root marker**; the board-expert
  reader merges several roots in a fixed **layer** order. An **overlay** is a spec in one root
  that adds to a spec in another.
- **Clean-room** — producing a spec or driver so that no one who writes the result has read
  the original source; "the wall" is the separation between those who read and those who
  write. Clean-room output is never published (policy 1).
- **Placement rule**, **license gate**, **accepts list** — this design's terms; defined in
  [The policy](#the-policy) and LS-R1 to LS-R4.

Full definitions: [GLOSSARY.md](../GLOSSARY.md).

## Problem and outcome

The project published 11 board and IP specs from one Apache-2.0 repository. Four carried facts
learned by reading GPL code, which made them clean-room output; publishing them under Apache-2.0
was wrong on both counts. They were deleted on 2026-10-01 to be regenerated. Before anything is
regenerated, the project needs (a) somewhere to publish each spec under a license that fits
what it cites, (b) tools that refuse a spec in the wrong place, and (c) the clean-room method
separated from the open method, so that neither repository's purpose is in doubt.

Users: people writing drivers who want a spec they can cite (Linux developers: GPL is fine;
other OSes: datasheet or permissive only); the project's own consumers (`bringup-kit` writes
Fuchsia drivers and must never read GPL specs); people who want a clean-room spec and will run
the method themselves.

**Observable outcome:** three public spec repositories, each with a license, a root marker
declaring that license, and CI that fails a spec citing a source with an incompatible license;
`cleanroom-skills` public with the clean-room skills; driver-lab holding only the open method,
plus the frozen evaluation archive.

**Non-goals:** regenerating the deleted specs (a separate workstream that this one unblocks;
the bcm2711 permissive overlay waits for it); legal review; changing what the clean-room skills
do beyond moving and renaming them; new evaluation rounds.

## The policy

1. **Publish the method, not clean-room output.** The clean-room skills stay published, in
   `cleanroom-skills`. No clean-room spec is published. Anyone who wants a clean spec generates
   it themselves and attests to how they made it.
2. **Published specs use the anchored format**, and each one lives in a repo whose license fits
   the sources it anchors to.
3. **Placement rule:** a spec lives in the most restrictive repo among the sources it anchors to.
   Specs may reference repos with less restrictive licenses, never ones with more restrictive
   licenses.

## The repos

| Repo | License | Anchors allowed | Holds |
|---|---|---|---|
| `hardware-specs-gpl` | GPL-2.0-only | `[src:]` into any GPL-2.0-only or GPL-2.0-or-later tree, plus `[doc:]`, plus anything the permissive repo accepts | Linux-derived specs: references for Linux work, or for anyone who doesn't care about license. Easiest to verify. |
| `hardware-specs-docs` | CC-BY-4.0 (specs); per-file Apache-2.0 SPDX headers on CI files | `[doc:]` only | Specs built only from public datasheets, TRMs and standards |
| `hardware-specs-permissive` | Apache-2.0, plus a NOTICE file for the BSD/MIT sources | `[src:]` into BSD, MIT or Apache trees (and `GPL-2.0 OR MIT` files), plus `[doc:]` | TF-A, rpi-tools, Zephyr, FreeBSD, dual-licensed device trees. First material: the bcm2711 overlay (facts 2, 3, 6 below) |

All three are created together and are public. `bringup-kit`'s spec roots point at the docs and
permissive repos, never at the GPL repo.

## Current state (measured 2026-10-05 at `a82785c`)

- **Root marker** (`board-specs.yaml`): fields `layer`, `name`, optional `roots`
  ([SPEC-FORMAT.md](../skills/board-expert/SPEC-FORMAT.md) roots section). No license field.
  `spec_check.py` takes roots as arguments, rejects an unknown layer, checks overlays and
  `--stubs-from` stubs. The per-resource `license:` on `resources.repos` entries is documented
  but not validated by `check_resources`.
- **Anchors** (`skills/anchored-peripheral-spec/scripts/anchor_check.py`): one pin per side;
  a second `Source pin:` silently overwrites the first; a single `--repo`. `[doc:]` anchors are
  not resolved: an empty one errors, one with no section or page number warns. No hash.
  `inventory_check.py` uses only the first pin. **Neither script has tests, and CI runs
  neither.**
- **Clean-room content in open skills:** `board-expert` always loads `os-investigator`
  (SKILL.md "Method and constraints"); `SPEC-FORMAT.md` has about 25 clean-room lines, including
  the `[source-observed]` class and a "Clean-room rules for spec content" section;
  `board-spec-scaffold` loads `os-investigator` in its subagent; `spec-verifier` has a
  clean-room section plus clean-room text in its shared parts (leak scan, cleanroom-spec
  detection).
- **Firewall:** `cleanroom_hook.py` blocks paths, commands, URLs and search queries by
  substring; it blocks no skill by name. The ban on loading `os-investigator` or `board-expert`
  is prose only.
- **Name consumers outside this repo:** `fuchsia-skills` (README, AGENTS.md, onboarding doc,
  `fuchsia-source` skill), `bringup-kit` (templates/AGENTS.md, README, hardware-inventory
  template, Bringup.md), `public-skills` (README, marketplace description, and
  `agent-agnostic-skills` links to `cleanroom-implementer/scripts` that driver-lab's CI pins).
  Both marketplace descriptions still name the deleted board experts.
- **Evals:** about 210 links into `evals/` from 59 files; `campaign-review`'s tests and CI index
  check read `evals/e1000`.

## Requirements

### Format and tools (driver-lab)

- **LS-R1 Root license.** The root marker gains `license:` (an SPDX expression for the repo's
  own license) and `accepts:` (a list of SPDX identifiers that anchored sources may carry).
  `spec_check.py` validates both. A root without them still loads (bringup-kit's tests and
  local roots write markers with only `layer`), with a warning; `--require-license` turns that
  into an error, and the three spec repos run with it.
- **LS-R2 Resource license.** `resources.repos[].license` is validated as an SPDX expression;
  in a root that declares `accepts:`, every repo a spec lists must have one.
- **LS-R3 Several named pins.** A spec may carry several `Source pin: <name>@<rev> <SPDX>`
  lines and cite `[src:<name>: path:L]`. The existing single-pin form, with no name and no
  license, stays valid, so the frozen evals' specs still check. `anchor_check.py` takes one
  `--repo <name>=<path>` per pin. `inventory_check.py` follows the same grammar.
- **LS-R4 License gate.** `anchor_check.py --root <dir>` fails when an anchor's pin carries a
  license the root's `accepts:` does not list, or carries no license at all in a root that
  declares `accepts:`. It reports the anchor, the pin, its license and the root's list.
  `OR` expressions pass when any branch is accepted (`GPL-2.0 OR MIT` passes in the permissive
  repo).
- **LS-R5 Checkable doc anchors.** A spec may list documents in front matter (`docs:` with
  `name`, `title`, `url`, `sha256`, optional `pages`); `[doc:<name> p.N]` must name a listed
  document and a page within `pages` when given. With `--docs-dir`, the checker hashes the local
  file and fails on a mismatch. Unnamed `[doc: …]` anchors stay valid outside
  `hardware-specs-docs`, where `--require-license` also requires named ones.
- **LS-R6 Tests and CI for the anchor tools.** `anchor_check.py` and `inventory_check.py` get
  unit tests with fixtures covering the existing grammar and LS-R3 to LS-R5, and driver-lab's
  CI runs them (they have none today).
- **LS-R7 Placement guidance.** `anchored-peripheral-spec` (renamed under LS-R16) replaces its
  "is it yours?" test with "which repo's license fits?", states the placement rule and gives the
  "which repo does my spec go in?" table.
- **LS-R8 Provenance attestation.** A `PROVENANCE.md` template that `cleanroom-spec` fills in:
  who ran it, which sources were behind the wall, which agent saw what, pins, verifier reports,
  the spec's hash. It is for the user's private record (policy 1).
- **LS-R9 Per-repo pins in verification.** `spec-verifier`'s anchored-spec procedure and
  `inventory_check.py` handle several named pins (LS-R3).
- **LS-R10 Why this exists.** driver-lab's README opens with a short "Why this exists and what
  it is not for" section (the community-reaction notes below).

### Spec repositories

- **LS-R11 Three repos.** Each has a LICENSE (NOTICE for the permissive one), a root marker
  with `license:` and `accepts:`, a README with the placement rule and the "which repo" table, a
  `specs/` tree, and CI that checks out driver-lab at a pinned commit and runs `spec_check.py
  --require-license` and `anchor_check.py --root`. Public, under `curtisgalloway`.
- **LS-R12 Gate proven per repo.** Each repo's CI is shown to fail on a fixture spec that cites
  a source its root does not accept, and pass on one that fits (a test branch or a CI self-test
  step; not a published bad spec).
- **LS-R13 Consumers point at the right repos.** `bringup-kit`'s spec roots name the docs and
  permissive repos and never the GPL repo; `public-skills` README points at the spec repos.

### The clean-room split

- **LS-R14 `cleanroom-skills` exists, public.** It holds, with history: `cleanroom-spec`,
  `cleanroom-implementer`, `os-investigator` renamed `cleanroom-investigator` (with
  `leak_scan.py`), the clean-room part of `spec-verifier` (as a `cleanroom-verifier` skill or a
  section of `cleanroom-spec`, decided in the milestone), and the clean-room design text moved
  out of `DESIGN.md`. Its own CI runs the moved tests and the portability scan. It depends on
  driver-lab (installed alongside); driver-lab never depends on it.
- **LS-R15 Neutral board-expert.** `board-expert`, `board-spec-scaffold` and `SPEC-FORMAT.md`
  no longer load or name `os-investigator` and carry no clean-room rules; those move to
  `cleanroom-investigator`, which wraps `board-expert` and adds the wall. `spec_check.py` keeps
  accepting the `[source-observed]` tag, because clean-room specs are still checked with it, but
  the format describes it only as "defined by an extension".
- **LS-R16 Renames.** `anchored-peripheral-spec` → `peripheral-spec`; "anchored spec" →
  "peripheral spec" in prose; `anchor_check.py`, `[src:]` and "anchor grammar" unchanged.
- **LS-R17 `hardware-investigator`.** A new open-side skill that answers board and peripheral
  questions from sources whose licenses the target root accepts, producing anchored facts for
  `peripheral-spec`, through `board-expert`. No wall.
- **LS-R18 Firewall by name.** `cleanroom-implementer`'s hook blocks reads of the
  `board-expert`, `hardware-investigator` and `cleanroom-investigator` skill directories and of
  any `hardware-specs-gpl` checkout, with tests; the prose ban stays.
- **LS-R19 Consumers renamed.** `fuchsia-skills`, `bringup-kit` and `public-skills` (README,
  marketplace, `agent-agnostic-skills` links) use the new names and repo; driver-lab's CI pin of
  public-skills moves to a commit with the updated links. Both marketplace descriptions are
  corrected (they still name the deleted board experts). No alias stubs for the old names.
- **LS-R20 driver-lab is the open side.** Outside the frozen archive, driver-lab mentions
  clean-room at most in one README line pointing to `cleanroom-skills`. The **frozen archive**
  is `evals/`, `evidence/`, `notebook/`, `history/`, `RECONSTRUCTION.md`,
  `QEMU-DIFFERENTIAL.md`, `EVAL-PLAN.md`, `VALIDATION-*.md`, the L01/L02/CR sections of
  `IMPLEMENTATION-PLAN.md` and `DEFERRED-PLAN.md`: kept as history with a header pointing to
  `cleanroom-skills` for new rounds, and still checked by CI (`campaign-review` keeps reading
  `evals/e1000`). A check script with that allowlist enforces the rule in CI.

## Decisions

Settled by the user on 2026-10-05 ([notebook](../notebook/LS-design.md)):

| Question | Decision |
|---|---|
| Name of the clean-room skills repo | `cleanroom-skills` |
| Public from day one? | Yes. LS-R10 and its own README framing land before it is made public |
| ENC28J60 and e1000 evals | Frozen in driver-lab as an archive; new rounds run from `cleanroom-skills` |
| `hardware-specs-docs` license | CC-BY-4.0 |
| Spec repo names | `hardware-specs-gpl`, `hardware-specs-docs`, `hardware-specs-permissive` |
| `os-investigator`'s new name | `cleanroom-investigator` |
| When the permissive repo is created | With the other two |
| Order | License tooling and spec repos first, then the clean-room split |

Settled by the user on 2026-10-06, during LS5 ([notebook](../notebook/LS5.md)):

| Question | Decision |
|---|---|
| Are board specs' `resources.repos` licenses gated, not only validated (LS-R2)? | Yes: `spec_check.py --require-license` fails one the root's `accepts:` does not accept, with the anchor gate's SPDX rules |
| License fields of the shipped `skills/board-expert/specs` root | `license: Apache-2.0`, `accepts: [Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause]` |
| Create the three spec repositories (public) and push them | Go given |

Earlier: the 11 specs deleted, to be regenerated (2026-10-01); facts 2, 3 and 6 to a bcm2711
permissive overlay (2026-09-30); `hardware-investigator` and `peripheral-spec` names (draft).

Consequences of these decisions, decided in this revision:

- **Clean-room design docs that describe the frozen evals stay with them.** The draft moved
  `RECONSTRUCTION.md` and `QEMU-DIFFERENTIAL.md`; with the evals frozen in driver-lab, moving
  them would break about 44 links from the archive. They stay as archive (LS-R20).
  `cleanroom-skills` links to them at a pinned commit. Only `DESIGN.md`'s clean-room sections
  move.
- **Tooling lands under the old skill names, then moves.** Tooling first means LS-R1 to LS-R9 are
  made in `anchored-peripheral-spec` and are renamed with it later. That costs one more path
  update in the spec repos' CI.
- **The firewall is in the implementer's hook, not in board-expert.** The draft's change 6 made
  `board-expert` refuse GPL roots. After the split `board-expert` is neutral and returns GPL line
  references by design, so the refusal belongs to the consumer that needs it (LS-R18).

## Alternatives considered

- **One spec repo with per-file licenses (REUSE).** Rejected: a reader cannot tell from the repo
  what they may copy, and a docs-only consumer (bringup-kit) would have the GPL specs in its
  checkout.
- **Keep clean-room skills in driver-lab.** Rejected in the draft: the open project's purpose
  stays in doubt (the "GPL-laundering kit" reaction).
- **Alias stubs for renamed skills.** Rejected: three consumers, all the user's own repos,
  updated in the same milestone; stubs would linger.

## Risks

- **Renaming breaks consumers by name** (AGENTS.md: "Skill names are an interface"). Mitigated
  by LS-R19 in the same milestone as the renames, with a grep of each consumer as acceptance.
- **The license gate reads SPDX expressions.** A small parser (identifiers, `OR`, `AND`,
  `WITH`, `-or-later`/`+`) is enough; full SPDX semantics are not needed. `AND` passes only
  when every part is accepted.
- **Cross-repo overlays.** The bcm2711 overlay in the permissive repo targets a spec in the docs
  repo. The reader composes roots already; `spec_check.py` checks an overlay's target only
  within the roots it is given, so the permissive repo's CI passes the docs repo as a second
  root. Proven when the overlay is written (regeneration workstream), and with a fixture in
  LS-R12.
- **Moving history** with `git filter-repo` rewrites hashes in the new repo; the commit-map
  approach from [TRANSITION.md](../TRANSITION.md) applies.
- **Public repos and pushes** are outward-facing: each repo creation and first push happens on
  the user's explicit go.

## Acceptance for the whole outcome

1. LS-R1 to LS-R20 each met, with evidence linked from the plan.
2. In a scratch setup, a spec citing a GPL-2.0-only pin fails in the docs and permissive repos'
   CI and passes in the GPL repo; a datasheet-only spec passes in all three; a `GPL-2.0 OR MIT`
   device-tree pin passes in the permissive and GPL repos.
3. `cleanroom-skills` installed beside driver-lab: its moved tests pass, and a
   `cleanroom-implementer` session fixture that reads `board-expert` is blocked by the hook.
4. driver-lab's full check list (AGENTS.md) passes, plus the new anchor-tool tests and the
   open-side mention check; the frozen archive's checks still pass.
5. A grep of `fuchsia-skills`, `bringup-kit` and `public-skills` finds no stale skill names.

## Community reaction (expected)

- **GPL repo:** likely welcomed by Linux people. Saying plainly that the specs are GPL
  derivatives, anchored to lines at a pinned commit, is the accurate framing. The likely
  pushback is about the quality of AI-generated documentation. The answer is that every claim is
  anchored and the checker runs in CI; say that on the README's first screen.
- **Clean-room skills:** expect some people to call them a "GPL-laundering kit." In their favor:
  their output is never published, users must attest, verification is strict, and the same
  project offers the GPL route. LS-R10 addresses this before anyone raises it.
- **Datasheet publishers:** docs-only specs paraphrase and cite, with rationed quotes, which is
  the usual accepted practice.

## History: the 11 deleted specs (2026-09-30 to 10-01)

**Decided (2026-10-01):** all 11 published specs, their verification records, and the four
per-board stub skills (`rpi-expert`, `rpi4-expert`, `indiedroid-nova-expert`, `pixel10-expert`)
are deleted. They will be regenerated from scratch with the new skills, in the repos this note
describes. The options and audit below are kept as history.

Four of the 11 contained `[source-observed]` facts, meaning facts learned by reading GPL code
behind the wall:

| Spec | `[source-observed]` facts |
|---|---|
| `bcm2711.spec.md` | 5 |
| `pixel10.spec.md` | 4 |
| `tensor-g5.spec.md` | 2 |
| `rk3588s.spec.md` | 1 |
| The other 7 | 0 |

Options considered: A, strip the 12 facts (1–2 h); B, delete the 4 specs (2–3 h); C, delete all
11 (half a day). C was chosen.

### Audit of the 12 facts (2026-09-30)

Result: **none of the 12 needs GPL driver code as its only support.** The line numbers are the
`[source-observed]` tags in each spec on `main` at the time of the audit. They guide
regeneration.

| # | Spec, line | Fact | What it actually rests on | Proposed fix |
|---|---|---|---|---|
| 1 | rk3588s, 161 | SCMI shared memory at about `0x10F000` | Mainline `rk3588-base.dtsi`: `scmi_shmem: shmem@10f000`, `reg = <0x0 0x0010f000 0x0 0x100>`, `no-map` | Retag `[DT]`; state exactly `0x10F000`, 256 bytes, reserved; drop the TODO |
| 2 | bcm2711, 131 | Stock stub sets `CNTFRQ_EL0` = 54 MHz and `SCR_EL3` = {NS, RW, HCE, SMD} | `armstub8.S` in raspberrypi/tools, **BSD-3-Clause**; confirmed at `439b619` (`OSC_FREQ`, `SCR_VAL`) | Permissive source: anchor as `[src: rpi-tools armstubs/armstub8.S:…]` (permissive repo) |
| 3 | bcm2711, 134 | Firmware patches DTB pointer at `0xF8`, entry at `0xFC`; magic `0x5AFE570B` at `0xF0` | Same file (`stub_magic`, `dtb_ptr32`, `kernel_entry32`) | Same as 2 |
| 4 | bcm2711, 139 | Spin-table release words at `0xD8`/`0xE0`/`0xE8`/`0xF0` | Already carries `[DT]` (`cpu-release-addr`) and `[standard]`; the stub (`spin_cpu0`–`3`) agrees | Drop the redundant `[source-observed]` |
| 5 | bcm2711, 174 | Bring-up costs: UART0 none, EMMC2 clock plus voltage switching, GENET nothing | Mainline `bcm2711.dtsi`: EMMC2 has `clocks = <&clocks BCM2711_CLOCK_EMMC2>`, GENET has no `clocks`; the UART's 48 MHz default is a firmware setting | Retag `[DT]` plus `[doc]` (config.txt `init_uart_clock`; citation still to confirm) |
| 6 | bcm2711, 210 | Stock stub disables SMC (`SCR_EL3.SMD`) | Same file as 2 | Same as 2 |
| 7 | pixel10, 259 | Prebuilt DTB and DTBO file names | Repository file listing, not code | New tag for repository metadata (for example `[repo]`) |
| 8 | pixel10, 289 | Prebuilt blobs are build outputs, not copied vendor blobs | Build definitions, entry counts, commit histories | `[repo]` as an `[inference]` premise |
| 9 | pixel10, 307 | Kernel version string, per-board module lists | Version string in a binary; `init.insmod.*.cfg` config lists | `[repo]` |
| 10 | pixel10, 345 | Production overlay fixups reference labels the upstream tree lacks | A decompiled DTBO | Retag `[DT]` |
| 11 | tensor-g5, 211 | "Module file names are source-observed, never facts" | A policy note in frontmatter, not a fact | Reword to use the new `[repo]` tag |
| 12 | tensor-g5, 485 | Production command line (earlycon, console, pKVM options) | The `chosen` node of the production DTBs | Retag `[DT]` |

**Decided:** facts 2, 3 and 6 come from BSD code, so they move to a separate permissive overlay
for `bcm2711` in `hardware-specs-permissive`, as anchored `[src:]` facts pinned to
`raspberrypi/tools@439b619`. The rest of `bcm2711` stays docs-only. The overlay uses the
existing overlay mechanism in `SPEC-FORMAT.md`; the root license fields (LS-R1) keep it out of
the docs root.

## History: the draft's estimates

The 2026-09-30 draft estimated about 5–6 focused days of tooling work, about 2 hours per new
repo, and about 3 days for the clean-room split. The plan re-sizes the work by milestone.
