<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# LS2: root license fields and the license gate

**Terms:** a *root marker* (`board-specs.yaml`) marks a directory of specs; its new `license:`
is the root's own SPDX license and `accepts:` lists the licenses an anchored source may carry.
The *license gate* is `anchor_check.py --root`, which fails anchors whose pin's license the root
does not accept. *SPDX* is the standard license-identifier language (`GPL-2.0-only`,
`GPL-2.0 OR MIT`). See the [glossary](../GLOSSARY.md) and the
[design's terms](../docs/LICENSE-SPLIT.md#terms).

Design: [LICENSE-SPLIT.md](../docs/LICENSE-SPLIT.md), revision 2026-10-05 (LS-R1, LS-R2,
LS-R4). Plan: [LS2](../docs/LICENSE-SPLIT-PLAN.md#ls2--root-license-fields-and-the-license-gate).
Notebook: [LS2](../notebook/LS2.md). Starting revision `88ca073` (origin/main, LS1 merged); no
pre-existing changes.

**Result: complete.** A spec citing a GPL-2.0-only source now fails the gate in roots shaped
like the docs and permissive repositories and passes in the GPL one; `GPL-2.0 OR MIT` passes in
the permissive and GPL roots; a datasheet-only spec passes everywhere. Markers with only `layer`
and `name` still load, with two warnings.

```text
$ anchor_check.py .../specs/gpl-only-spec.md --root .../roots/docs
ERROR L13: license gate: [src: drivers/widget.c:2 (WIDGET_CTRL)] cites source pin 'linux'
  (GPL-2.0-only), which root .../roots/docs does not accept (accepts: none)
result: FAIL (1 errors, 1 warnings)        # exit 1
```

## What changed

- `skills/board-expert/scripts/spdx.py` (new): SPDX expressions (identifiers, `LicenseRef-`,
  `+`, `AND`, `OR`, `WITH`, parentheses up to 32 deep), a short known-identifier list,
  deprecated GNU forms normalized (`GPL-2.0` is `GPL-2.0-only`, `GPL-2.0+` is
  `GPL-2.0-or-later`), and the acceptance rule. Placed where the plan proposed:
  `anchor_check.py` also needs `spec_check.py`'s YAML reader and marker validation, so both
  live in one directory.
- `spec_check.py`: `check_root_license` validates `license:` and `accepts:`; absent fields
  warn, `--require-license` makes them errors. `check_repo_license`: `repos[].license` must
  parse; it is required in a root that declares `accepts:`.
- `anchor_check.py`: pin licenses must parse (always); `--root DIR` gates every `[src:]` and
  `[tgt:]` anchor (and the `impl`/`ref` aliases) and every uncited pin against DIR's accepts
  list; a root without `accepts:` fails; a line that starts like a pin but is not read as one
  warns, and fails under `--root`.
- Fixtures: `skills/anchored-peripheral-spec/tests/fixtures/license-gate/` (three
  repository-shaped roots, 13 specs, `expected.json` with the exit code per pair, a README),
  self-contained for LS5's CI self-test.
- Tests: `test_spdx.py` (7, table-driven), `test_spec_check.py` (`LegacyMarkers` 2,
  `RootLicense` 6), `test_anchor_check.py` (`TestLicenseGate` 21). Existing suites unchanged
  in what they assert; their exact-findings checks now drop the two absence warnings.
- `SPEC-FORMAT.md`: the two marker fields, `--require-license`, and the new check rules (full
  guidance is LS4). No new CI step: the new tests run under the existing discovery steps.

## Acceptance

| Criterion | Evidence and result |
| --- | --- |
| Design item 2 on fixtures (GPL pin fails docs/permissive, passes GPL; `GPL-2.0 OR MIT` passes permissive and GPL; no pins passes everywhere) | `TestLicenseGate.test_fixture_matrix` runs all 39 spec-root pairs against `expected.json`; also `OR`, `AND`, `WITH`, `+`, two pins, target side, uncited pin. **Met.** |
| No license fields: warning; with `--require-license` exit 1 | `RootLicense.test_absent_fields_warn_and_require_license_makes_them_errors`, `test_one_field_missing_is_reported_alone`. **Met.** |
| Invalid SPDX in a marker or a resource exits 1 with the field named | `test_invalid_marker_fields_are_errors_naming_the_field` (`root marker: license: …`, `root marker: accepts entry 'GPL-2': …`), `test_repo_license_must_be_spdx` (`repos entry 'fw': license: …`). **Met.** |
| bringup-kit-style markers (`layer` only) pass without the flag | `LegacyMarkers` (characterization, passes on old and new code); the shipped `skills/board-expert/specs` root still exits 0. **Met.** |
| Full check list passes | All 14 commands exit 0 after the review fixes (`ls2-checks.log`, session scratch): board-expert `Ran 57 … OK`, anchored-peripheral-spec `Ran 68 … OK`. **Met.** |

**New tests against the pre-change code** (`origin/main`'s `spec_check.py` and
`anchor_check.py`, `spdx.py` removed; log `ls2-old-scripts.log`): board-expert `Ran 52 …
FAILED (failures=15, errors=1)`, where every `RootLicense` test failed and `test_spdx` could not
import; anchored-peripheral-spec `Ran 64 … FAILED (failures=54, errors=1)`, where all 17 gate
tests failed (the matrix's pass cells fail only because `--root` did not exist). The two
`LegacyMarkers` tests and all earlier tests passed. One new test that passed on the old code
(`test_repo_license_is_not_gated_by_accepts`, a guard against over-gating) was folded into a
test that fails there. The review-fix tests fail on both `origin/main` (4 of 4) and the pre-fix
LS2 scripts (4 of 4, plus the three new parser subtests) (`ls2-prefix-scripts.log`).

## Decisions the design left open

All taken toward failing closed: both sides are gated; a pin no anchor cites is gated; a root
without `accepts:` fails `--root`; `accepts: []` is declared and empty; `WITH` passes when its
license does; resource licenses are validated, not gated (LS-R2); an unknown identifier is an
error (write `LicenseRef-<name>`).

## Review

`review-swarm`, seven arms and a referee, on the staged diff against `88ca073`. Run directory
`ls2-review-swarm/` in the session scratch (`verified.json`, `final.json`, `table.txt`). All
seven arms delivered; the checker dropped 0 of 8 findings; the referee dropped 2, merged 1, and
kept 5. Fixing was authorized by the milestone brief; every kept finding was fixed:

| ID | Sev. | Finding | Resolution |
| --- | --- | --- | --- |
| F6 (+F2) | medium | A pin line that did not match the pin pattern (lowercase `or`, `DocumentRef-…:`, spaced parentheses) was silently not a pin, so its license was never checked; with two pins, unnamed anchors could bind to the other pin and pass the gate | Operators match in any case and `:` is allowed, so such licenses reach `spdx.py`'s message; any other line starting `<Side> pin:` that is not read warns, and is an error under `--root`. Tests: `test_lowercase_operator_is_read_and_rejected`, `test_document_ref_license_is_read`, `test_unread_pin_line_warns_and_fails_the_gate` |
| F8 | low | No `notebook/index.md` row for LS2 | Row added at the checkpoint |
| F7 | low | Without board-expert beside the skill, a non-SPDX pin license only warned (exit 0) | Now an error. `test_license_unverifiable_without_board_expert_is_an_error` |
| F1 | low | Unbounded paren nesting raised `RecursionError` | `MAX_DEPTH = 32`, a `SpdxError` past it. Parser test |
| F3 | low | `(MIT and ISC)` reported as an unbalanced parenthesis | The token is named: uppercase hint or "unexpected". Parser tests |

Dropped by the referee as the change's stated intent: an invalid repo license failing roots
without `accepts:` (the plan's acceptance requires exit 1), and pin licenses validated without
`--root` (LS1's hand-off). Both behaviors are deliberate.

## Limitations

- The gate covers anchored peripheral specs (`anchor_check.py`). Board specs' `[DT]` and
  `resources.repos` licenses are validated but not gated; a GPL repo listed in a docs-root
  board spec passes. The design asks for no more; noted for LS4/LS5.
- The shipped `skills/board-expert/specs` root has no license fields, so CI prints two
  warnings there. Choosing its `accepts:` is a policy decision left open.
- The known-identifier list is short; a valid SPDX identifier not on it is an error until added.
