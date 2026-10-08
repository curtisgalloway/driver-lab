<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# License-gate fixtures

Synthetic inputs for `anchor_check.py --root` (the license gate) and for
`spec_check.py --require-license`. Everything here is self-contained: the pins name made-up
revisions and no repository is needed, because the gate reads only the pins' licenses and the
root marker.

- `roots/gpl`, `roots/docs`, `roots/permissive`: root markers shaped like the three spec
  repositories (`hardware-specs-gpl`, `hardware-specs-docs`, `hardware-specs-permissive`), each
  with `license:` and `accepts:`. Each passes `spec_check.py --require-license`.
- `specs/*-spec.md`: peripheral specs whose pins carry different licenses, including `OR`,
  `AND`, `WITH`, `+`, a pin with no license, an anchor with no pin, a pin no anchor cites, two
  named pins, a target-side pin, a license no spec repository accepts (`gpl3-only-spec.md`), and
  a license that is not SPDX. Two specs have no pins: `docs-only-spec.md` cites documents in
  free text, and `docs-named-spec.md` lists them in a `docs:` registry and cites them by name,
  the shape the docs root requires under `--require-license`.
- `expected.json`: the exit code of `anchor_check.py <spec> --root roots/<root>` for every pair
  (0 passes, 1 fails). `test_anchor_check.py` (`TestLicenseGate.test_fixture_matrix`) runs the
  whole matrix and asserts the file lists exactly the specs present.
- `board/`: board specs for `spec_check.py --require-license`, whose board-spec gate compares
  `resources.repos[].license` with the root's `accepts:`. `widgetchip.spec.md` cites a document
  only and fits every root; `widgetchip-bsd-overlay.spec.md` adds a BSD-3-Clause repository
  (fits the GPL and permissive roots, not the docs root); `widgetchip-gpl3-overlay.spec.md` adds
  a GPL-3.0-only one (fits none); `widgetchip-src-overlay.spec.md` adds a `[src]` fact anchored
  to a BSD-3-Clause repository pinned to a commit (fits the GPL and permissive roots; the docs
  root accepts no `[src]`, so it fails there with `license gate: [src]`). The overlays also prove that an overlay in one root resolves
  against a spec in another when both roots are given (the permissive repository's overlays
  target specs in the docs repository). `board-expert/tests/test_spec_check.py`
  (`BoardSpecGate`, `SrcClass`) runs them, and `anchor_check.py --root` reads the `[src]`
  overlay's repository entry as its Source pin.

A spec repository's CI self-test can copy its root's column: the specs marked 0 must pass and
those marked 1 must fail with a `license gate:` message (or, for `invalid-license-spec.md`,
`is not an SPDX expression`). `expected.json` records runs without `--require-license`; the
spec repositories run with it, which also fails `docs-only-spec.md` in the docs root.

The pairs the three spec repositories' self-tests copy, each run with `--root <repo>/specs
--require-license` (`TestRequireNamedDocs.test_spec_repository_self_test_pairs` runs them here):

| Repository | Fit (must pass) | Misfit (must fail with `license gate:`) | Board overlay fit / misfit (beside `widgetchip.spec.md`) |
|---|---|---|---|
| `hardware-specs-gpl` | `gpl-only-spec.md` | `gpl3-only-spec.md` | `widgetchip-bsd-overlay` / `widgetchip-gpl3-overlay` |
| `hardware-specs-docs` | `docs-named-spec.md` | `gpl-only-spec.md` | none / `widgetchip-bsd-overlay` |
| `hardware-specs-permissive` | `bsd-spec.md` | `gpl-only-spec.md` | `widgetchip-bsd-overlay` / `widgetchip-gpl3-overlay` |

Each self-test also runs `widgetchip-src-overlay.spec.md` beside `widgetchip.spec.md` through
`spec_check.py --require-license` and `anchor_check.py --root --require-license`: both pass in
the GPL and permissive repositories and fail in the docs repository.

With `RESOLVE_SRC=1` (as CI runs), each self-test also proves anchor resolution ran:
`widgetchip-resolve-good-overlay.spec.md` and `widgetchip-resolve-bad-overlay.spec.md` pin the
real `raspberrypi/tools` repository at one commit; `fetch_src_pins.py` fetches it and
`anchor_check.py` must pass the good anchor and fail the bad one with `does not exist at`. They
run under a temporary marker that accepts BSD-3-Clause, so they test resolution in every
repository, the documents-only one included.

The permissive repository's self-test also places `widgetchip.spec.md` under the docs
repository's marker and the BSD overlay under its own, and checks that the overlay fails alone
and passes with both roots.
