<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Publishing spec views

**Terms:** a viewer is the generated HTML reading copy; a root is a directory with a
`board-specs.yaml` marker; context roots supply referenced facts; an artifact is a build's
downloadable files. See the repository [glossary](../../../GLOSSARY.md).

`publish.yml` is a workflow template for a spec repository, not an active driver-lab workflow.
Copy it into that repository's workflows directory during SF2-11. Replace `TOOL_COMMIT` with
the full driver-lab commit containing this viewer. The zero placeholder deliberately fails.
The template assumes the checked root's marker is at the repository top level. Enable GitHub
Pages with Actions as its source during cutover, then link the generated index from the README.

For roots with dependencies, add separate context checkouts beside `specs` in **both** jobs,
pin each to a full commit, and pass `--context-root DIRECTORY` and
`--source-commit DIRECTORY=COMMIT` to **every** build and verify invocation. Add
`--public-skill NAME` where a public tool skill is declared. Context checkouts must be siblings,
never nested in a spec root. Own pages show same-id files in separate unmerged groups; each
overlaid spec also gets a merged page with the context base and every supplied overlay. The generated index lists all
pages and their Markdown copies. Nothing generated is committed.

Pull requests build at their merge SHA, enforce the `pr` verification policy, and upload both
views. Main and weekly builds enforce `main`, which permits upstream-stale records. Only the
deploy job has write permissions; its branch/event condition excludes pull requests. The deploy
job downloads the build, rechecks the same sources and re-renders every expected page before
uploading the Pages artifact. The source inventory determines completeness; editing a manifest
cannot hide a missing or modified page. All actions are pinned by full commit SHA.

Local dry run, using a pinned Python environment and a scratch copy of a fixture root:

```text
python skills/spec-format/ci/publish.py build ROOT --out SITE --source-commit ROOT=SHA --tool-commit SHA
python skills/spec-format/ci/publish.py verify ROOT --out SITE --source-commit ROOT=SHA --tool-commit SHA
```

`SITE` must be empty and outside every supplied root; neither command follows output symlinks.

The site's `index.html` is the **explorer**: one page that searches and filters every fact in the
published specs and links each to its full viewer page and Markdown copy. Its author text is the
viewer renderer's output, embedded as JSON that cannot close its script element.

`build --fetch-anchors` makes the explorer's heading citations open the document at that
heading. It fetches each cited GitHub page once (a `blob` URL pinned to a full commit, through the
API, or a wiki page), records each heading's anchor in the site's `anchors.json`, and prints the
headings it could not find, which usually means a locator does not match the document. A fetch
failure leaves those headings unresolved and never fails the build. Set `GITHUB_TOKEN` for the
API rate limit. `verify` and the deploy job do not fetch: they validate the stored `anchors.json`
(format, well-formed anchors, only headings the specs cite) and re-render from it, so the byte
comparison still holds. An edited `anchors.json` can at most change a heading fragment on a
declared document URL. Without the flag, `anchors.json` is empty and citations link to the
document.
The helper returns 0 for a complete build/verification and 1 for a refused site. The workflow
adds `--require-verified pr|main`; omit that only for synthetic fixtures without records. The
local tests exercise both policies. Real deployment and repository README links belong to
SF2-11. Pages' required job structure follows
[GitHub's custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
