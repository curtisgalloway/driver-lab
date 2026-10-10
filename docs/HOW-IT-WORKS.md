<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# How driver-lab works

## What it is for

A device driver is the software an operating system uses to control a piece of hardware. Writing one well takes knowledge scattered across datasheets, existing drivers and device trees (the files that tell an operating system where each device sits on a board). driver-lab is a set of AI agent skills that gathers that knowledge into a **spec**: a structured description of a device or board that a programmer or agent can write a driver from.

A spec is made of **facts**. A fact is one statement about the hardware ("this register resets to zero", "wait one millisecond after reset"), together with the exact source it came from.

**The core test:** take a device that already has a working Linux driver, write a new driver from the spec alone, without the writer seeing the original code, then run both drivers side by side against the same device and compare what they do. Each difference exposes a gap or error in the spec, the new driver or the test.

## How work flows

```
sources ──> investigate ──> author spec ──> verify ──> publish
(datasheets,   hardware-       peripheral-spec    spec-verifier   spec repositories
 drivers,      investigator,   board-spec-                        + rendered views
 device trees) board-expert    scaffold
```

1. **Investigate.** `board-expert` answers questions about a board (memory map, interrupts, clocks, boot). `hardware-investigator` answers one question at a time and returns cited facts.
2. **Author.** `peripheral-spec` writes the spec for one device; `board-spec-scaffold` writes board and chip specs. `reference-driver-review` compares an existing driver with another implementation of the same hardware and records the differences.
3. **Verify.** `spec-verifier` has fresh agents, who never saw the author's reasoning, re-derive each fact from its cited source and write a separate **verification record**: a pass, fail, gap or "needs a person" verdict for each fact. It never edits the spec.
4. **Publish.** Finished specs live in three public spec repositories, split by license (see below).

## How it tries to guarantee quality

- **Every fact cites its source** at an exact version: a datasheet section, or specific lines of code at a fixed commit. The fact also says what kind of evidence it is, so "a driver does this" is never confused with "the hardware requires this". A fact with no source is recorded as a gap, not guessed.
- **Independent checking.** Verifiers work without the author's context. The most critical facts, such as a board's memory layout or its debug console, need a **second reader**: a second independent verifier who must agree before the fact counts as checked. Disagreements go to a person.
- **Freshness.** Each verdict records a fingerprint of the fact, its sources, and every fact it builds on. If any of those change, the verdict becomes stale and only the affected facts need re-checking.
- **The license gate.** A spec built from GPL code is itself GPL; one built from datasheets or permissively licensed code is not. Each spec repository accepts only certain source licenses, and an automated check rejects any spec that cites a source its repository cannot accept.
- **Automation first, people for exceptions.** Hand-reviewing every spec would cost about as much as writing the driver. Automated checks cover structure, citations, licenses and verdict freshness on every change; people handle conflicting evidence and unresolved disagreements.
- **Visible status.** Published views of each spec show, beside every fact, its evidence type, its verdict, whether that verdict is current, and whether a critical fact still lacks its second reader.

## What it does not yet guarantee

Checks show that a fact matches its cited source, not that the source is right; two readers can share the same mistake, and only running on real hardware settles behavior. Hardware with no existing driver, where there is nothing to cite or compare against, is not yet designed or tested.
