<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Spec repository checks and publishing

**Terms:** a viewer is the generated HTML reading copy; a root is a directory with a
`board-specs.yaml` marker; context roots supply referenced facts; an artifact is a build's
downloadable files. See the repository [glossary](../../../GLOSSARY.md).

## Repository checks

Copy [checks.sh](checks.sh) to `scripts/checks.sh` (keep it executable) and
[checks.yml](checks.yml) to `.github/workflows/checks.yml` when creating a spec repository.
These are maintained templates, not active driver-lab workflows. They include physical
self-test temporary paths for macOS and run all check steps on Ubuntu and macOS. Existing
repositories hold independent copies; review and apply later template changes explicitly.
The script assumes the repository's marker is `specs/board-specs.yaml` and runs from the
repository top level. It needs Bash 3.2 or later and either `driver-lab` (`DRIVER_LAB_BIN`)
or the pinned spec-format Python dependencies.

Set `TOOL_COMMIT` in the check workflow to a full driver-lab commit on `main` that contains
the required fixtures and checker; use the same pin in the publishing workflow. The all-zero
placeholder deliberately fails. Keep action revisions pinned and workflow permissions read-only.
The copied scripts and workflows retain their Apache-2.0 headers; spec content uses its own
root's license.

Configure the script's top block to match the root marker's existing license policy. `REPO`
must equal the marker's `name`. The defaults are for `hardware-specs-docs`; a repository with
a different name must change `REPO`. Do not widen the marker's `accepts` list to pass a fixture.
A profile is the following set of fixture settings, not a new license decision:

| Variable | Documents only | Permissive sources | GPL-2 sources |
| --- | --- | --- | --- |
| `FIT` | `docs-named.spec.yaml` | `bsd.spec.yaml` | `gpl-only.spec.yaml` |
| `MISFIT` | `gpl-only.spec.yaml` | `gpl-only.spec.yaml` | `gpl3-only.spec.yaml` |
| `BOARD_FIT` | empty | `widgetchip-bsd-overlay.spec.yaml` | `widgetchip-bsd-overlay.spec.yaml` |
| `BOARD_MISFIT` | `widgetchip-bsd-overlay.spec.yaml` | `widgetchip-gpl3-overlay.spec.yaml` | `widgetchip-gpl3-overlay.spec.yaml` |
| `EXTRA_FIT_LICENSES` | empty | `"ISC 0BSD"` | `"ISC 0BSD"` |
| `SRC_FIT` | `0` | `1` | `1` |
| `REQUIRE_FURTHER` | `0` | `1` | `2` |
| Further roots, in argument order | none | docs | docs, permissive |

These profiles match the three hardware-specs repositories. For another policy, select fit
and misfit fixtures that actually exercise it, using the [fixture matrix](../tests/fixtures/license-gate/README.md).
`REQUIRE_FURTHER` is the minimum number of context roots, directories read alongside the own
root to resolve references and overlays. In the cross-root overlay self-test, when `SRC_FIT=0`
(or `specs/board-specs.yaml` has `accepts: []`), `checks.sh` constructs a documents-only overlay
fixture so documents-only repositories that depend on upstream context roots pass the cross-root
self-test without adding source licenses (`BF-IMX-ISS-2`).

When `STUBS_DIR` is set or `skills/` contains expert stub `SKILL.md` files, `check_specs`
automatically passes `--stubs-from "$STUBS_DIR"` to the checker; when `DOMAINS_MANIFEST` is set
or `domains.yaml` is present at the repository top level, `check_specs` also runs
`stubgen "$DOMAINS_MANIFEST" --out "${STUBS_DIR:-skills}" --check` (`BF-IMX-ISS-3`).

During `resolve`, `check_resolve` inspects `cache/<name>` for each repository declared in
`resources.repos`. When `cache/<name>` is a full (non-partial) git clone containing every pinned
commit cited for `<name>`, `check_resolve` automatically binds `--repo <name>=cache/<name>`;
partial clones (`extensions.partialClone` or `remote.*.promisor`) and checkouts missing the
pinned commit are skipped with a note (`BF-GW-23`).

The workflow initially has no context roots. For each required context, add an
`actions/checkout` step with its repository, explicit ref, `persist-credentials: false`, and a
separate path outside `specs/`. Append that checkout's `specs/` path to **all four** `checks.sh`
invocations, in the table's order. Existing hardware-specs checks use context repositories'
`main` refs so new spec data is checked together; the executable driver-lab tool stays pinned.
Set `REQUIRE_CORPUS=1` on the check step once the root keeps a corpus ledger
(`specs/corpus.yaml`, [spec-format](../SKILL.md#corpus-ledger)): the step then also runs
`corpus`, which fails when the ledger is missing. Without it, `check` still checks a
ledger that exists, but a root without one passes.
Keep `RESOLVE_SRC=1` on both resolve and self-test steps. It fetches cited source revisions;
the self-test proves a valid anchor resolves and a deliberately invalid anchor is rejected.

Before the first commit, run `scripts/checks.sh --mode pr all` with the pinned driver-lab
checkout and the configured context-root arguments, setting `DRIVER_LAB_BIN` (or `CHECKS_PYTHON`
to the pinned Python environment) and `RESOLVE_SRC=1`. Verify the license fit passes, the misfit
fails for the expected license reason, and both platform jobs run in CI. Never relax the
checker's symlink policy: the script canonicalizes only the temporary directory it just created.

## Publishing spec views

`publish.yml` is a workflow template for a spec repository, not an active driver-lab workflow.
Copy it into that repository's workflows directory during SF2-11. Replace `TOOL_COMMIT` with
the full driver-lab commit containing this viewer. The zero placeholder deliberately fails.
The template checks out the spec repository to `path: repo` and passes `repo/specs` with
`--source-commit "repo/specs=$SOURCE_COMMIT"` so repositories whose root marker is at
`specs/board-specs.yaml` build and verify cleanly (`BF-IMX-ISS-1`). Enable GitHub
Pages with Actions as its source during cutover, then link the generated index from the README.

For roots with dependencies, add separate context checkouts beside `repo` in **both** jobs,
pin each to a full commit, and pass `--context-root DIRECTORY` and
`--source-commit DIRECTORY=COMMIT` to **every** build and check/verify invocation. Add
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

Local dry run, using `driver-lab` (or a pinned Python environment) and a scratch copy of a fixture root:

```text
driver-lab publish build repo/specs --out site --source-commit repo/specs=SHA --tool-commit SHA
driver-lab publish check repo/specs --out site --source-commit repo/specs=SHA --tool-commit SHA
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
API rate limit. `check`/`verify` and the deploy job do not fetch: they validate the stored
`anchors.json` (format, well-formed anchors, only headings the specs cite) and re-render from it,
so the byte comparison still holds. An edited `anchors.json` can at most change a heading
fragment on a declared document URL. Without the flag, `anchors.json` is empty and citations
link to the document.
The helper returns 0 for a complete build/verification and 1 for a refused site. The workflow
adds `--require-verified pr|main`; omit that only for synthetic fixtures without records. The
local tests exercise both policies. Real deployment and repository README links belong to
SF2-11. Pages' required job structure follows
[GitHub's custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
