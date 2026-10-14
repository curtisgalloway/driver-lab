<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 95

**Terms.** An input root is any directory given to `render`; a rendered root is one that
contributes files to the selected view. See the [glossary](../GLOSSARY.md).

## 2026-10-14 — Source commits for rendered roots

Reproduced the triage case on a copy of the worked example: a commit for a context root
that the unmerged view does not render exits 2, and dropping it succeeds. The rule is
intended; the usage error and the contract did not say which roots count. Moved the
source-commit parsing into one helper both renderers call, so the error lists the
rendered roots as the caller gave them and the HTML renderer gains the separate duplicate
and hex messages. The worked example's context root does not check clean, so a merged
render of it fails before rendering; the contract's example stays unmerged. Closed with
the [acceptance evidence](../evidence/ISSUE-95.md).
