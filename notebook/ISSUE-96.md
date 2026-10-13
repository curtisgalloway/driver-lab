<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 96

**Terms.** A heading anchor is a page fragment identifying a rendered heading.
See the [glossary](../GLOSSARY.md).

## 2026-10-13 — Heading locator check

The explorer already provided complete-heading matching, GitHub URL boundaries,
per-document fetching and authentication handling. Reused that resolver through
an explicit checker flag, then mapped unresolved results back to YAML locators.
Kept network failures distinct from missing headings and excluded dependency roots.
The [acceptance evidence](../evidence/ISSUE-96.md) records the outcome.
