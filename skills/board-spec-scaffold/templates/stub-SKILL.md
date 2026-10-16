---
name: <board>-expert
description: >-
  Board expert for <board-name> (<soc-name>): addresses, device tree, boot hand-off, interrupts,
  timers, clocks/power, debug UART and GPIO/pinmux. Use for <trigger-keywords> hardware or
  low-level questions. A stub over the `<board-id>` board spec: board-expert does the work.
---

<!--
SPDX-FileCopyrightText: <copyright-year> <copyright-holder>
SPDX-License-Identifier: <file-license>
-->

# <board-name> expert (stub)

Terms: a stub is a skill pointer; a spec records hardware facts. See the target repo's glossary.
The `<board-id>` board spec composes the `<soc-id>` SoC and `<chip-id>` companion.

`spec: <board-id>`

This is a subagent role. The orchestrator spawns an expert that loads board-expert, passes the
spec id and question, and receives its report. In Claude Code with the driver-porting plugin
installed, the expert is the `driver-porting:board-expert` agent; elsewhere it is a subagent
that loads the skill. The expert manages its own resource cache.
Facts go in YAML, procedure in board-expert, format rules in spec-format. Keep this a pointer.
