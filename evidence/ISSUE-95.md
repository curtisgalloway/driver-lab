<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 95 — Source commits for rendered roots

**Terms.** An input root is any directory given to `render`; a rendered root is one
that contributes files to the selected view. A context root supplies dependencies.
See the [glossary](../GLOSSARY.md).

`spec.py render` still rejects a `--source-commit` for a root that is not rendered
(exit 2), but the usage error now lists the rendered roots as the caller gave them:
`--source-commit ROOT must name a rendered root directory (rendered: docs)`. Both
renderers call one shared parser, so the HTML renderer also reports duplicate roots and
malformed commits separately, as the Markdown renderer does. The spec-format contract
states the rule with a two-input-root, one-contributing-root example, `spec.py` help
repeats it, and board-expert step 5 links the example.

| Acceptance | Evidence |
| --- | --- |
| Rejected and accepted invocation documented | Contract example "Source commits name rendered roots" |
| Error lists given root labels, no absolute path | Test on a relative-path copy of the worked example asserts the exact message |
| Accepted invocation succeeds | Same fixture, Markdown and HTML, commit appears in the view |
| Markdown and HTML reject identically | Identical JSON findings; shared duplicate, hex and unknown-root messages |
| Unknown roots remain a hard error | Misspelled-root test raises the usage error; review compared exit codes before and after on 216 CLI combinations (all equal) |
| board-expert references the rule | Step 5 link to the contract example |

The full spec-format suite passes: 676 tests (one opt-in network test skipped), including
three focused tests. Board-expert tests, privacy and open-side checks
pass. Private artifacts: run `issue-95-20261014`.

Limitations: the publishing template still filters commits to each page's roots, so CI
and the CLI accept different flag sets by design. The worked example's context root does
not check clean, so the contract example covers only the unmerged case.
Review found that "rendered" also excludes a checked root holding no file for the `--spec`
id (`render docs other --spec bcm2711` rejects `other=`); the contract, help text and
glossary say so, but no test pins that case.
