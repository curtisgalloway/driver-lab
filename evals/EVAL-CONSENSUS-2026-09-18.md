<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

> **Record, not a live plan.** The evaluation consensus two reviewers reached on 2026-09-18,
> kept verbatim as the source of [EVAL-PLAN.md](../EVAL-PLAN.md), which is where its decisions
> are tracked and updated. The two drafts it supersedes are not in any repository.

# Driver-specification evaluation: final consensus

Date: 2026-09-18. Supersedes `driver-spec-eval-consensus.md` (FEC-side draft) and `driver-spec-eval-consensus-draft.md` (ENC28J60-side draft). Both reviewers accept every item below; the only remaining decision is one both agree to defer, marked at the end.

## Objective

Evaluate whether the skill produces a precise, adequately supported hardware contract that another implementer can use to write a driver and meaningful verification procedures. Measure four things separately: source comprehension, documentation integration, applicability reasoning, and downstream usability.

## Sequence

| Phase | Device | Purpose | Reference and execution evidence |
|---|---|---|---|
| Pilot | ENC28J60 B7 (EREVID 0x06) | Calibrate the requirement ledger, scoring, and test quality | Frozen DS39662E + DS80349C; SPI traces; physical-device fixture |
| Main benchmark | One precisely scoped NXP FEC/ENET target | Host DMA descriptors, SoC dependencies, variant-specific behavior, replacement-driver execution | Matching SoC RM and errata edition; Linux + corroborating implementations; QEMU for modeled behavior only |
| Held-out transfer test | OpenTitan UART at `earlgrey_1.0.0` | Does improvement transfer once skill tuning stops | Adjudicated docs and pinned RTL; independently prepared Verilator harness |
| Optional extension | Intel 82574L / `e1000e` | Driver and feature complexity | Matching Intel docs and QEMU `e1000e`; separately scoped errata checks |

ENC28J60 is the method pilot, not evidence of performance on complex SoC drivers. FEC is the main test of that use case. OpenTitan is an executable reference, not a substitute for commercial-silicon workaround testing.

## Corrections carried into the shared answer key (all accepted by both)

1. **ERR006358 flag ≠ workaround presence.** `FEC_QUIRK_ERR006358` is set only in `fec_imx6q_info` (`fec_main.c:125`) and never tested; `fec_enet_tx_queue()` performs the TDAR recovery (`:1714`) unconditionally. Grade the control flow, not the flag table. Recheck against the pinned commit. This becomes a benchmark probe: does the skill trace flow or infer from flags?
2. **An erratum absent from a vendor document does not prove the device unaffected.** Record vendor-confirmed, Linux-observed, and unresolved applicability as three separate columns. Never score an unconfirmed discrepancy as a proven contradiction. (ERR007885: Linux applies to 6SX/6UL/8MQ/8QM/S32V; vendor-confirmed only in IMX6SXCE.)
3. **Related IP is not an interchangeable reference.** The RT1060 RM and Teensy 4.1 may support an explicitly bounded portability experiment; they are not the authoritative reference or silicon target for an i.MX6/8M contract without a reviewed equivalence argument per tested behavior.
4. **Intel erratum #19 is 82574IT-only.** Linux applies `FLAG2_CHECK_PHY_HANG` to all 82574 (`82571.c:2014`) because L and IT share a device ID; for an 82574L target that is observed software behavior, not a hardware requirement.
5. **Use edition-specific errata identifiers.** DS80349C places the reset/CLKRDY issue at issue 2; the Linux comment's "#1" is recorded literally and not assumed to reference any particular edition. (The FEC-side reviewer could not fetch DS80349C and accepts the ENC28J60-side reading.)

## Common evaluation protocol

- **Ledger.** Atomic requirements authored independently of any generated spec, then reviewed and adjudicated. Each records applicability (device/revision/mode), preconditions, behavior, timing/order, side effects, evidence citation, confidence, verification method; labeled documented hardware requirement / observed software behavior / inference / implementation choice / unresolved conflict. Unresolved claims are excluded from binary scoring.
- **Primary comparison.** Same model, sources, tools, and budget, with vs. without the skill. Memory-only, driver-only, datasheet-only runs are diagnostics. High baseline performance indicates limited headroom, not proven memorization; the 80% figure is a planning heuristic. When recall nears its ceiling, read precision, applicability, traceability, and test quality instead.
- **Tracks.** Reconstruction (driver + selected sections) and full-documentation integration stay distinct. Withheld documents may contain facts or mechanisms the supplied evidence cannot reveal: score observable behavior separately from mechanism, reward justified uncertainty, do not reward confident guessing.
- **Scoring.** Requirement recall and factual precision reported separately, by category and severity; compound claims split first; severity-based gates retained and recalibrated after the first reviewed run (initial: ≥95% weighted recall, ≥98% precision, no omitted required workaround in scope).
- **Checks.** Reference checks built from adjudicated sources, never from the generated spec. Deliberate mutations (flip a dummy read cycle, a wraparound op, a recovery ordering) establish that each test discriminates.
- **Pinning.** Source commits, file hashes, document IDs and editions, generated headers, configuration. Skill frozen before the OpenTitan run; OpenTitan scoring material kept out of tuning inputs.
- **Corroborating implementations** (Zephyr/NuttX/EtherCard for ENC28J60; FreeBSD/NetBSD/NuttX/U-Boot/QNEthernet for FEC; Tock for OpenTitan) are completeness evidence only, after checking lineage and hardware-version compatibility.

## Interpretation of executable results

| Evidence | Establishes | Does not establish by itself |
|---|---|---|
| QEMU boot | The image boots | Network operation or replacement-driver correctness |
| QEMU traffic tests | Tested behavior works against that model | Silicon timing errata or unmodeled behavior |
| SPI/register trace assertions | The observed sequence satisfies the checked requirements | Complete hardware correctness |
| Ordinary physical traffic | Basic operation on the identified device | Recovery from faults never triggered |
| Fault injection / affected-silicon reproduction | Behavior under the exercised conditions | Coverage of untriggered errata |
| Pinned RTL simulation | The digital implementation under test conditions | Analog or fabrication-dependent properties |

Known limits recorded now: QEMU `imx_fec.c` transmits on TDAR write and clears the register, so the TDAR race is unobservable there; `test_imx8mm_evk.py` checks a console string, not DHCP. Networking bring-up and errata validation are explicit additional work. Physical-fixture coverage is stated test by test, with silicon revision confirmed.

## First deliverable

A reproducible ENC28J60 evaluation package: frozen corpus manifest (v6.12 driver + header hashes, document editions and hashes, edition-specific errata map), reviewed requirement ledger (initial sizing 50–80 requirements, 10–15 boundary/recovery scenarios), conflict log, baseline results, fixture instructions with a reference-driver smoke-test result, independently authored boundary/recovery checks, and a scored skill run. Unavailable fault coverage recorded explicitly.

## Suggested first actions (estimates provisional until actual bring-up)

1. Approve purchase of two ENC28J60 modules (~$4 each) — recommendation, not a decision made here.
2. Corpus manifest (~2 h).
3. Blind ledger and conflict log (~4 h, second reviewer adjudicates).
4. With/without-skill pair plus diagnostics (~1 h of runs).
5. Score; recalibrate gates; decide which measures are informative on this device.
6. In parallel: create the free NXP account and download the candidate FEC target's RM and errata so phase 2 can start without delay.

## Deferred decision (both agree)

**FEC target SoC/revision** is chosen only once its matching RM, errata edition, and a demonstrated QEMU network setup are in hand. Qualification order: i.MX6Q / `sabrelite` first (IMX6DQRM Rev. 6, IMX6DQCE Rev. 7; documented erratum ↔ code pairs; needs a cross-built `imx_v6_v7_defconfig` kernel), then i.MX8M Mini / `imx8mm-evk` (stock Debian boots; errata content uncorroborated). Freeze commits and hashes at that point.

## Sources

- Linux: [fec_main.c](https://github.com/torvalds/linux/blob/master/drivers/net/ethernet/freescale/fec_main.c) · [fec.h](https://github.com/torvalds/linux/blob/master/drivers/net/ethernet/freescale/fec.h) · [e1000e/82571.c](https://github.com/torvalds/linux/blob/master/drivers/net/ethernet/intel/e1000e/82571.c) · [enc28j60.c v6.12](https://github.com/torvalds/linux/blob/v6.12/drivers/net/ethernet/microchip/enc28j60.c) · [enc28j60_hw.h v6.12](https://github.com/torvalds/linux/blob/v6.12/drivers/net/ethernet/microchip/enc28j60_hw.h)
- NXP: [IMX6DQCE](https://www.nxp.com/docs/en/errata/IMX6DQCE.pdf) · [IMX6SXCE p. 75](https://www.nxp.com/docs/en/errata/IMX6SXCE.pdf#page=75) · [IMX28CE](https://www.nxp.com/docs/en/errata/IMX28CE.pdf) · [IMX8MM_0N87W](https://www.nxp.com/docs/en/errata/IMX8MM_0N87W.pdf)
- Intel: [82574 Spec Update 320709 Rev. 4.1, p. 20](https://cdrdv2-public.intel.com/320709/82574-specupdate-rev4-1-external-320709.pdf#page=20)
- Microchip: [DS39662E](https://ww1.microchip.com/downloads/en/DeviceDoc/39662e.pdf) · [DS80349C p. 3](https://ww1.microchip.com/downloads/en/DeviceDoc/80349c.pdf#page=3)
- QEMU: [hw/net/imx_fec.c](https://github.com/qemu/qemu/blob/master/hw/net/imx_fec.c) · [sabrelite.rst](https://github.com/qemu/qemu/blob/master/docs/system/arm/sabrelite.rst) · [imx8m docs](https://www.qemu.org/docs/master/system/arm/imx8m.html) · [test_imx8mm_evk.py](https://github.com/qemu/qemu/blob/master/tests/functional/aarch64/test_imx8mm_evk.py)
- OpenTitan: [uart.hjson](https://github.com/lowRISC/opentitan/blob/earlgrey_1.0.0/hw/ip/uart/data/uart.hjson) · [uart_testplan.hjson](https://github.com/lowRISC/opentitan/blob/earlgrey_1.0.0/hw/ip/uart/data/uart_testplan.hjson) · [dif_uart.c](https://github.com/lowRISC/opentitan/blob/earlgrey_1.0.0/sw/device/lib/dif/dif_uart.c) · [uart_core.sv](https://github.com/lowRISC/opentitan/blob/earlgrey_1.0.0/hw/ip/uart/rtl/uart_core.sv)
- Corroborating drivers: [Zephyr eth_enc28j60.c](https://github.com/zephyrproject-rtos/zephyr/blob/main/drivers/ethernet/eth_enc28j60.c) · [NuttX enc28j60.c](https://github.com/apache/nuttx/blob/master/drivers/net/enc28j60.c) · [Raspberry Pi enc28j60 overlay](https://github.com/raspberrypi/linux/blob/rpi-6.12.y/arch/arm/boot/dts/overlays/enc28j60-overlay.dts) · [FreeBSD if_ffec.c](https://github.com/freebsd/freebsd-src/blob/main/sys/dev/ffec/if_ffec.c) · [NetBSD if_enet.c](https://github.com/NetBSD/src/blob/trunk/sys/arch/arm/imx/if_enet.c) · [Tock lowrisc uart.rs](https://github.com/tock/tock/blob/master/chips/lowrisc/src/uart.rs)
