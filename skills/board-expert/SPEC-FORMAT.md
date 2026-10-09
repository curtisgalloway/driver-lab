<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Board spec format

**Terms:** a spec records cited hardware facts; a root is a marked directory of specs;
an overlay adds facts to another spec. See the [glossary](../../GLOSSARY.md).

The shared contract is [spec-format](../spec-format/SKILL.md). Read it before authoring or
consuming format 2 YAML. Its schemas define shapes; its text defines classes, references,
roots, records, rendering and commands. Start from
[board-spec-scaffold's YAML templates](../board-spec-scaffold/templates/).

For existing format 1 Markdown roots only, use
[board-expert's transition path](SKILL.md#format-1-reading-until-sf2-12) and the unchanged
format 1 tools. They remain until SF2-12; the current authoring contract is format 2.
