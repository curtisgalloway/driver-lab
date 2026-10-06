<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS3: checkable doc anchors

**Terms:** a *doc anchor* (`[doc: …]`) cites a document for a fact. A spec's *docs registry* is
a `docs:` list in its YAML *front matter* (the `---` block at the top of the file) naming each
document with its title, URL and SHA-256 hash; a *named* doc anchor (`[doc:trm p.12]`) cites a
registry entry by name. *Root marker*, `accepts:` and the *license gate* are as in
[LS2](LS2.md); see the [glossary](../GLOSSARY.md) and the
[design's terms](../docs/LICENSE-SPLIT.md#terms).

Design: [LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md), revision 2026-10-05 (LS-R5, with LS-R1's
`--require-license`). Plan: [LS3](../docs/LICENSE-SPLIT-PLAN.md#ls3--checkable-doc-anchors).
Notebook: [LS3](../notebook/LS3.md). Starting revision `7092822` (LS2's checkpoint, stacked;
LS2 not yet merged); no pre-existing changes.

**Result: complete.** A spec may list its documents and cite them by name and page; an unknown
name, a page past the document's end, or a malformed hash fails, and `--docs-dir` checks the
local files' hashes. Specs with only unnamed `[doc: …]` tags check exactly as before unless
`--require-license` is given with a root that accepts no source.

```text
$ anchor_check.py .../license-gate/specs/docs-only-spec.md --root .../roots/docs --require-license
ERROR L11: unnamed [doc: Widget TRM v1.0 §4.2]: root .../roots/docs accepts no source, so
  documents are its specs' only provenance and --require-license requires named ones: list the
  document under docs: in the front matter and cite [doc:<name> p.N]
result: FAIL (2 errors, 0 warnings)        # exit 1; without --require-license, exit 0
```

## What changed

- `skills/anchored-peripheral-spec/scripts/anchor_check.py`:
  - Front matter is read with board-expert's YAML reader and skipped by the body scan: a
    leading `---` block with a closing `---` that has a `docs:` line, or parses as a YAML
    mapping and carries no anchor tag. Any other leading block (horizontal rules) is body text,
    as before. `docs:` entries need `name`, `title`, `url`, `sha256`
    (64 hex digits); `pages` (a positive count) and `file` (a relative path) are optional; an
    unknown key warns. A missing or malformed field is an error naming the entry.
  - Named anchors: `[doc:<name> p.N]`, `pp.N-M`, `§x.y`, several locators per document and
    several documents per tag with `;`. A named anchor has no space after `doc:`; one that is
    not `<name> <locator>…` is an error telling the author to add the space for a free-text
    citation. Unknown name, page 0, an inverted range and a page past `pages` are errors.
  - `--docs-dir DIR` hashes `DIR/<file>` (default `DIR/<name>.pdf`) for every entry; a mismatch
    is an error naming the document, the path and both hashes; a missing file is a warning.
    The `url` is never opened; the script imports no network module.
  - `--require-license` (needs `--root`): the root marker's missing `license:` becomes an error
    (as in `spec_check.py`), and in a root whose `accepts:` is empty every unnamed `[doc: …]`
    tag is an error.
  - JSON gains `docs`, `doc_anchors` and `unnamed_docs`; the human report prints one
    `doc <name>: <title>` line per registry entry, and nothing new for a spec without one.
- Tests: `TestDocTagCharacterization` (5, written first, pass on LS2's checker and now),
  `TestNamedDocAnchors` (16), `TestRequireNamedDocs` (5). The two documents are generated per
  run from fixed bytes whose SHA-256 the tests pin.
- `skills/anchored-peripheral-spec/SKILL.md`: one grammar line for the named form (full format
  docs are LS4). No new CI step: the tests run under the existing discovery step.

## Acceptance

| Criterion | Evidence and result |
| --- | --- |
| Each failure exits 1 with the anchor and document named; a correct spec passes | `test_unknown_document_fails_naming_anchor_and_registry`, `test_page_out_of_range_fails`, `test_page_zero_and_inverted_range_fail`, `test_malformed_named_anchor_fails`, `test_malformed_or_missing_sha256_fails`, `test_registry_fields_are_validated` assert exit 1 and the exact messages; `test_correct_spec_passes` (also under `--strict` and `--docs-dir`) exits 0 with no findings. **Met.** |
| A hash mismatch fails only with `--docs-dir`; without it the check is structural | `test_hash_mismatch_fails_only_with_docs_dir` (exit 0 and no findings without, exit 1 with the message with), `test_explicit_file_is_hashed`, `test_missing_file_is_skipped_with_a_note`. **Met.** |
| Existing specs with unnamed doc anchors pass without `--require-license` | `TestDocTagCharacterization` passes on LS2's script and this one (counts, warnings, exact human output, every gate root); `test_unnamed_doc_passes_in_roots_that_accept_sources`; LS2's license-gate matrix unchanged. **Met.** |
| The full check list passes | All 12 commands exit 0 after the review fixes (`ls3-checks.log`, session scratch): anchored-peripheral-spec `Ran 94 … OK`, board-expert `Ran 57 … OK (skipped=1)`. **Met.** |

**New tests against the pre-change code** (LS2's `anchor_check.py` from `7092822` swapped in,
then restored and compared with `cmp`; log `ls3-old-scripts.log`): `Ran 94 … FAILED
(failures=22, errors=2)`. All 21 new behavior tests fail (some in several subtests); the 5
characterization tests and the 68 earlier tests pass. The review-fix tests (3) also fail on the
pre-fix LS3 script (`ls3-prefix-scripts.log`: `failures=5`, the same 3 tests).

## Decisions the design left open

- **Where named anchors are required.** The design requires them in `hardware-specs-docs`
  while all three spec repositories run `--require-license`. `anchor_check.py --require-license`
  therefore requires named anchors only in a root whose `accepts:` is empty (the docs repo's
  shape), so every repository can pass the same flag to both tools. A separate flag, or keying
  on the marker's `name:`, was rejected.
- **Named versus unnamed** is the space after `doc:`. Judging by content would turn an existing
  `[doc: UG585 §16.3]` into an unknown-name error. No tracked file has a `[doc:` tag without
  the space.
- **Missing file under `--docs-dir`** is a warning (the plan's "skip with a note").

## Review

One independent reviewer subagent with fresh context read the diff, the plan's LS3 section,
the check log and the old-code log, and probed the checker with its own specs. Its returned
findings are saved as `ls3-review.md` in the session scratch. It ran LS2's and LS3's checkers
on all 19 tagged files in the repository: same human output and exit codes, JSON differing
only by the three new keys; it found no network import in either skill's scripts. No
blockers; every acceptance criterion met.

| # | Sev. | Finding | Resolution |
| --- | --- | --- | --- |
| 1 | should-fix | A spec opening with a `---` horizontal rule had its first section taken for front matter and skipped, so a malformed `[src:]` there passed (LS2: exit 1) | A leading block is front matter only with a `docs:` line, or as a tag-free YAML mapping; otherwise it is scanned. `test_leading_horizontal_rule_block_is_body_text` |
| 2 | nit | `[doc:Widget TRM §4]` (no space) was valid on LS2 and now fails; the unknown-name error did not say how to write a free-text citation | Kept the rule (no such tag in driver-lab or the three consumers, per the reviewer); the unknown-name message now carries the space hint |
| 3 | nit | SKILL.md shows the forms but not the registry shape, `--docs-dir` or `--require-license` | One more line (the space rule, a pointer to the docstring); the format docs are LS4's scope, noted in the plan |
| 4 | nit | Notebook said "all 20 new tests fail"; 5 of the 25 new tests are characterization tests | Corrected by a later notebook entry |

## Limitations

- The registry is checked against the file's bytes, not its content: quoted text and page
  contents are not compared with the PDF (out of scope).
- `pages` is the author's statement; the checker does not count a PDF's pages.
- LS2's `license-gate/specs/docs-only-spec.md` uses unnamed anchors, so it fails the docs root
  under `--require-license` (exit 1, shown above). LS5's self-test runs the gate without the flag
  or needs a named-anchor fixture.
