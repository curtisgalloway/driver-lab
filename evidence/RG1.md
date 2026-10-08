<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# RG1 and RG-T1: `bcm2711` regenerated, and the `[src]` checker

Plan: [spec regeneration](../docs/SPEC-REGEN-PLAN.md), units RG1 and RG-T1. Notebook:
[RG-regen](../notebook/RG-regen.md); review learnings: [rollup](../notebook/SPEC-REGEN-learnings.md).
Run ID: `rg1-20261007-01` (private run store).

**Terms.** A *spec* is a board, SoC or IP-block description in `SPEC-FORMAT.md`'s format; a
*root* is a spec directory whose marker names its license and accepted source licenses; an
*overlay* adds facts to a spec in another root; a *verification record* holds one verdict per
claim, written by a fresh verifier subagent. See the [glossary](../GLOSSARY.md).

**Status: complete; merged as is by user decision (2026-10-08).** The `bcm2711` SoC spec exists
in three roots, each with a verification record at zero FAIL that `spec_check --require-verified`
accepts. The Markdown spec format is to be replaced by YAML with a JSON Schema (user decision,
same day); the RG-T1 grammar below is merged for the record and retired by that work.

## What RG1 produced

| Root | Content | Facts | Record |
|---|---|---|---|
| `hardware-specs-docs` | SoC spec from documents only (datasheet, Arm TRMs and ARM, Raspberry Pi and TF-A docs, Linux boot protocol, Devicetree Specification) | 34 | 34 PASS |
| `hardware-specs-permissive` | overlay: facts read from the BSD-3-Clause boot stub (`raspberrypi/tools@439b619`, `armstubs/armstub8.S`) as `[src]` facts, plus `[inference]` bullets | 13 | 13 PASS |
| `hardware-specs-gpl` | overlay: facts that only GPL-2.0 device trees (and one GPL-2.0+ driver) support | 18 | 18 PASS |

Every BCM2711 device tree is GPL-2.0-only; no fact that only a device tree supports could go in
the docs or permissive roots. The cross-repository overlay (permissive and GPL onto docs) works
in CI.

## How it was reviewed

| Pass | Reviewers | Outcome |
|---|---|---|
| 1 | three Claude verifiers (one a second reader on bring-up facts) | 1 FAIL |
| 1 | Codex, networked, with the records | 20 findings, 18 the verifiers missed (one wrong interrupt routing) |
| 2–4 | fresh Claude verifiers and second readers each round | definiteness and citation FAILs, four adjudicated by the user (stricter reading) |
| 5 | Codex, networked, without the records | 20 findings, 18 new (PCIe DMA limit stated too broadly; A72 SMPEN prerequisite missing) |
| 6 | verifiers with a contrary-evidence step | found the pinned stub Makefile contradicting the vendor docs on high peripheral mode |
| 7 | delta verification of changed bullets only (user's stop rule) | zero FAIL in all three |

No address, interrupt number or register value was wrong after the first Codex pass; later
rounds found scope, locator and unstated-premise issues.

## Limitations

- High peripheral mode: the documentation says the firmware's stub lacks support; the pinned
  stub Makefile builds a high-peripheral image. The spec attributes the claim to the
  documentation and carries a hardware TODO (the Makefile has no license notice and is not
  cited, by user decision).
- The build identity of the firmware's built-in stub is an assumption, stated as one, with a
  hardware TODO.
- No fact was checked on hardware.

## RG-T1: the checker

Added the `[src]` class (pinned by `resources.repos`, license-gated by the root's `accepts`),
anchor resolution in CI by blob-less fetch, per-file verification records, context roots,
`--require-verified` in spec-repository CI, no symlinks in roots, and one Markdown parse
(markdown-it-py 4.2.0) shared by both checkers with a restricted Markdown profile. Eight review
rounds (a Claude reviewer and Codex) found a command injection through a spec's repository URL
(fixed) and a long series of ways to make text render as provenance while the checker read it
otherwise.

**Known gaps at merge** (Codex round 8, recorded rather than fixed): emphasis or invisible
characters inside an anchor (`[s**rc**:…]`, U+200B, fullwidth brackets) hide it from both
checkers; the two checkers classify some front matter differently (a quoted `"kind":` key);
escapes inside link destinations and titles are not rejected. The verification record, which a
verifier writes from the rendered claim, and review remain the gate. These go away with the YAML
format.
