<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# RG-regen: spec regeneration

Chapter for the [spec-regeneration plan](../docs/SPEC-REGEN-PLAN.md). Each unit's entries record
every review finding as a row; proposed skill changes roll up in
[SPEC-REGEN-learnings](SPEC-REGEN-learnings.md).

Finding rows use these columns: reviewer (`spec-verifier` or Codex), claim, finding, accepted or
rejected (why), caught by the other reviewer (yes/no), and the skill or format rule that would
have prevented it.

### 2026-10-07 — opening

Plan approved by the user. Decisions: implementer Opus 5.5, one fresh subagent per unit; Codex
is the second reviewer after `spec-verifier`, read-only, with the verifier's record in hand;
learnings recorded per unit here and rolled up. Units renamed `RG` (not `SR`) because
`evidence/SR-7.md` and `SR-8.md` already exist from earlier work.

### 2026-10-07 — Codex needs network to find sources

Probe with `codex exec --sandbox read-only`: curl failed DNS, web fetch returned a cache miss,
and web search found `armstub8.S` only on `master`, not at `439b619`. Read-only mode has no
network switch. Staging the sources locally would have given Codex the same bytes as the
verifier, but the user wants Codex to find sources the spec did not cite, which needs network.
Decision (user): Codex runs with `--sandbox workspace-write` and network access, in a throwaway
scratch directory only; the local permission rules allow exactly that form. Re-probe: curl
fetched the file at `439b619` and read its BSD-3-Clause header.

### 2026-10-07 — RG1 implementer: DT facts are all GPL-only; three decisions

The implementer wrote the `bcm2711` docs spec (28 bullets: `[databook]` 17, `[doc]` 14,
`[standard]` 1, `[DT]` 0) and a permissive overlay (8 bullets from `armstub8.S`). Every BCM2711
device tree is `GPL-2.0` only, in mainline v7.2 and in the Raspberry Pi kernel branch; none is
`GPL-2.0 OR MIT`. The 13 facts only a device tree supports (block addresses the datasheet omits,
PCIe `dma-ranges`, spin-table release addresses, among others) were left out, and the plan's
stop condition fired. Arm TRMs were reported unreachable (403 on `developer.arm.com`).

User decisions: the 13 DT facts go to a `hardware-specs-gpl` overlay; add a `[src]` provenance
class to the board-spec format (tooling unit RG-T1); keep the overlay's facts beyond audit facts
2, 3 and 6; drop the two `armstubs/Makefile` anchors (no license notice at the pin, no license
file in the repository).

### 2026-10-07 — RG1 reviews: verifiers, then Codex

Three verifiers (fresh Opus subagents): docs spec 27 PASS / 1 FAIL; overlay 8 PASS / 0 FAIL; an
independent second reader of the 12 bring-up-critical docs bullets 12 PASS. Then Codex (networked,
with the specs, cited sources and both records) found 20 items. The orchestrator confirmed
Codex's highest finding in the datasheet: chapter 2 puts SPI1 and SPI2 in the AUX block, which
shares VC IRQ 29, so "54 of all SPI controllers" is wrong for two of the seven.

| # | Reviewer | Claim | Finding | Verdict | Other caught? | Would have prevented it |
|---|---|---|---|---|---|---|
| V1 | verifier | docs Gotchas/7 "Not the Pi 5 chip" | "nothing here applies" overstates the BCM2712 page, which says the families share architecture | accepted | no (Codex: already failed) | spec-verifier definiteness rule worked |
| V2 | verifier | docs Quick-facts/16, 17, 13, 2, 20 | five citations correct but imprecise (page range, table not named, derived wording) | accepted as fixes | partly (Codex #13 on 20) | SPEC-FORMAT: a citation-precision rule; spec-verifier: grade imprecise citations |
| V3 | verifier | overlay, `rpi-tools` pin | `armstubs/Makefile` has no license notice; NOTICE's BSD claim unsupported | accepted (user: drop anchors) | yes (Codex #5) | hardware-investigator: confirm the license per cited file, not per repository |
| V4 | verifier | overlay | checker skips overlay records; CI never anchor-checks board-spec overlays | accepted (RG-T1) | no | spec_check bug; checks.sh scope |
| C1 | Codex | docs Quick-facts/12, Gotchas/2 | SPI1/2 route to AUX (VC 29, GIC 125), not VC 54 / GIC 150 | accepted, confirmed in datasheet ch. 2 | no | spec-verifier: check a summary table against the figure and chapter it summarizes |
| C2 | Codex | docs Gotchas/2 | PACTL_CS does not cover EMMC/EMMC2 (GIC 158) | accepted | no | same as C1 |
| C3 | Codex | overlay Quick-facts/6 | eight IGROUPR writes cover IDs 0–255, but only 224 are implemented | accepted | no | spec-verifier: check a code fact's stated consequence against the hardware document |
| C4 | Codex | overlay Quick-facts/6 TODO | proposed check (read registers from non-secure EL2) cannot observe the secure state | accepted | no | spec-verifier: verify a TODO's proposed method is possible |
| C5 | Codex | overlay `rpi-tools` license | Makefile unlicensed (as V3) | accepted (user decision) | yes (V3) | as V3 |
| C6 | Codex | docs Quick-facts/10 | GIC-400 TRM reachable at `documentation-service.arm.com/static/…`; resolves the offsets TODO | accepted | no | board-spec-scaffold / hardware-investigator: name the Arm static-PDF route |
| C7 | Codex | docs Quick-facts/13, 14, Gotchas/6 | missing which UART is the header console per model, `enable_uart`, Bluetooth overlays | accepted | no | board-spec-scaffold: console-routing checklist item |
| C8 | Codex | docs Quick-facts/5, 7 | Linux entry contract omits image/DTB placement, alignment, cache state | accepted | no | scaffold: entry-contract checklist |
| C9 | Codex | docs Quick-facts/3, 21 | RAM size is not an allocation map; reserved memory and `/memory` must be honored | accepted | no | scaffold: memory-map checklist |
| C10 | Codex | docs Quick-facts/11 | PPI 25 (virtual maintenance) and PPI/SPI input types missing | accepted | no | GIC TRM unread (C6) |
| C11 | Codex | docs Quick-facts/11 | PCIe INTA–D, MSI, GENET, xHCI GIC IDs in Table 103 omitted | accepted | no | spec-verifier: coverage check against the cited table |
| C12 | Codex | docs Quick-facts/16 | ARM timer registers start at +0x400 from the quoted base | accepted | no | spec-verifier: compare a base against its register table |
| C13 | Codex | docs Quick-facts/20 | handler barrier positions not spelled out | accepted | partly (V2) | — |
| C14 | Codex | docs Quick-facts/15 | AUX_ENABLES vs AUX_MU_CNTL enables; reset values start RX early | accepted | no | — |
| C15 | Codex | docs Quick-facts/9 | spin-table and PSCI release procedure is documented in `booting.rst` | accepted | no | — |
| C16 | Codex | docs Quick-facts/18 | "get clock rate" returns the last requested rate; measured-rate tag exists | accepted | no | — |
| C17 | Codex | docs Quick-facts/13 | PL011 TRM reachable; reprogramming order (disable, IBRD/FBRD, then LCR_H) | accepted | no | as C6 |
| C18 | Codex | docs Quick-facts/18 | mailbox transport documents (Mailboxes, Accessing mailboxes) omitted | accepted | no | — |
| C19 | Codex | docs Quick-facts/9 | Cortex-A72 TRM gives the MPIDR CPU-number encoding | accepted | no | as C6 |
| C20 | Codex | docs Quick-facts/7, overlay 2–3 | Arm ARM defines SCR_EL3 and entry state | accepted with change: cite the canonical Arm resource; do not record the third-party mirror Codex used | no | as C6 |

Reading: the verifiers checked what each claim says against its citation and found it right
almost every time; Codex found what the claims leave out, routing a summary table hides, and
sources the author did not reach. The second Claude verifier agreed with the first on every
shared bullet, so it added no new findings here.
