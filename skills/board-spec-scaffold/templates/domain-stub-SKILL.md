---
name: <name>
description: >-
  Domain expert for <title>: <description>. A stub over the <entry-ids> spec(s):
  board-expert does the work.
---

<!--
SPDX-FileCopyrightText: <copyright-year> <copyright-holder>
SPDX-License-Identifier: <file-license>
-->

# <title> expert (stub)

Terms: a stub is a skill pointer; a spec records hardware facts. See the target repo's glossary.
This stub scopes board-expert to one domain of the `<board>` board. It holds procedure and
pointers only: every address, instance and register it needs is in the specs below.

<entry-lines>

This is a subagent role. The orchestrator spawns an expert that loads <preload>, passes the
spec ids above and the question, and receives its report. In Claude Code with the
driver-porting plugin installed, the expert is the `driver-porting:board-expert` agent;
elsewhere it is a subagent that loads the skill. Questions outside this domain go to the
board's own expert.
<profile-line>
Facts go in YAML, procedure in board-expert, format rules in spec-format. Keep this a pointer:
`spec.py check --stubs-from` refuses hex values and register names here.
