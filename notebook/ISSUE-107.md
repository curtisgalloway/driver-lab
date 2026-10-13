<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 107

**Terms.** Physical PDF pages count from one; printed page labels may differ.
See the [glossary](../GLOSSARY.md).

## 2026-10-13 — PDF evidence resolution

Confirmed that document resolution checked whole-file identity without reading cited
pages. Used the existing optional Poppler extractor rather than adding a Python
dependency. A generated PDF made extraction tests independent of external documents.
Review exposed unchecked page arguments; bounded them before integer conversion and
the subprocess call. Utility tests needed a temporary directory outside an existing
Git marker. Closed with the [acceptance evidence](../evidence/ISSUE-107.md).
