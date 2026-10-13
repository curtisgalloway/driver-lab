<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 96 — Optional heading resolution

**Terms.** A heading anchor is the fragment used to link to a heading on a
rendered page. A pinned blob is a file URL identifying a complete Git commit.
See the [glossary](../GLOSSARY.md).

`spec.py check --resolve-headings` now warns at document heading locators that
the explorer's resolver cannot match to an anchor. It fetches each supported
document once and checks complete heading text, normalizing case and whitespace.
The default check makes no heading requests. Structural errors prevent requests.

| Acceptance | Evidence |
| --- | --- |
| Explicit network opt-in | Default-check test asserts no fetch |
| Reuse existing resolver and fetch once | Tests exercise the explorer HTML parser and verify one request for repeated citations |
| Warning at each missing locator | JSON location and terminal warning tests |
| Loose headings and bullets rejected | Shortened heading and bullet-only HTML tests |
| Wiki support and URL boundaries | Pinned blob/wiki fetch; unpinned and other-host URLs skip with warnings |
| Request failures remain warnings | Offline fetch test; message distinguishes missing from unavailable |
| Dependency roots excluded | Context-root test |
| Recursive evidence included | Nested-premise heading test |

The full spec-format suite passes: 660 tests (one opt-in network test skipped),
including ten focused tests, 15 existing explorer tests and 73 existing checker
tests. Independent review cleared the implementation. Privacy, open-side and
skill portability checks pass. Private artifacts: run `issue-96-20261013`.

Limitations: GitHub heading anchors are a mechanical locator check, not proof
that a passage supports a claim. Unanchored headings may require manual reading.
Wiki pages reflect current content rather than an immutable commit. Other hosts,
unpinned blob URLs and PDF page locators are outside the resolver's fetch scope.
The existing explorer's authentication, redirect policy and request limits apply.
