<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 107 — Cited PDF evidence

**Terms.** A locator identifies a section, table, figure or page in a document.
PDF page numbering counts physical pages starting at one; printed numbering refers
to labels inside the document. See the [glossary](../GLOSSARY.md).

`spec.py resolve` and `show --docs-dir` now extract cited physical PDF pages after
checking the document's SHA-256 identity. They warn when section, table or figure
tokens, claim hex literals or a register offset are absent from the cited text.
`show` presents the document locator and page text beside the fact.

| Acceptance | Evidence |
| --- | --- |
| Locator presence, including adjacent-page hints | `test_adjacent_and_absent_locators_warn`, `test_locator_tokens_do_not_match_prefixes` |
| Claim literals and structured register offsets | `test_inclusive_range_and_missing_register_offset`, direct-support scope test |
| Document-only side-by-side evidence | `test_document_only_show_and_terminal_output` |
| Physical numbering only; optional extraction | Printed numbering, missing pages, missing extractor, empty text and unpinned-document tests |
| Immutable document identity prerequisite | Hash mismatch test refuses extraction |
| Real extraction and bounded output | Generated three-page PDF, cache and text-limit test |
| Oversized page numbers cannot mislabel evidence | Signed integer boundary checked before invoking Poppler |

The independent review found that an oversized page number could wrap in Poppler
and return page 1 labeled as page 4294967297; very long numbers also caused an
internal conversion error. The final implementation rejects both before extraction.
The review cleared the revised change. Private artifacts: run `issue-107-20261013`.

The final full spec-format suite passes: 663 tests, including 13 document regression
tests and the existing resolver tests (one opt-in network test skipped). All other
repository checks pass. Two utility tests initially failed because the temporary
directory's ancestor contained a Git marker; the unchanged base reproduced this,
and using a temporary directory outside that ancestor made those tests pass.

Limitations: text presence is a warning heuristic, not verification of meaning or
proof that a table caption rather than a cross-reference was cited. Scanned pages
without text, printed numbering and nonnumeric locators explicitly skip extraction.
Poppler's `pdftotext` is optional; the pinned Python dependency list is unchanged.
The issue's optional inventory/coverage proposal is outside this fix.
