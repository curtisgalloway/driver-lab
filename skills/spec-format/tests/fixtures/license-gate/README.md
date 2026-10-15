<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# License-gate fixtures

The license-gate matrix for `spec.py check`, converted from the fixtures of the retired Markdown format. Everything is synthetic and self-contained: the gate reads only the repos
entries' licenses and the root marker, so no repository is fetched.

- `roots/gpl`, `roots/docs`, `roots/permissive`: root markers shaped like the three spec
  repositories (`hardware-specs-gpl`, `hardware-specs-docs`, `hardware-specs-permissive`). The
  GPL and permissive fixture roots also accept `X11` and `Zlib`, which the published markers do
  not, so a spec citing either passes the fixture check and fails the published one (LS-G F1;
  SF2-G G6). No fixture spec cites either.
- `specs/<row>.spec.yaml`: one spec per row of the earlier matrix (`<row>-spec.md` there). The
  spec format uses `kind: peripheral` (SF2-7a), carrying the same repos entries and anchors.
  Two rows changed shape with the format: `dual-gpl-mit` cites its `.dtsi`
  as `DT` (the earlier format gated only `[src]`; the spec format gates `DT` and `rtl` too), and `docs-only` and
  `docs-named` both cite named documents, since the spec format has no free-text citation.
- `expected.json`: the exit code of `spec.py check <root> --require-license` for every pair, the
  root holding one marker and one spec; 0 passes, 1 fails. The codes are the earlier file's,
  row for row. `without_require_license` lists the only codes that differ without the flag: a
  repos entry no anchor or notice names (`uncited-gpl-pin`) is gated only under
  `--require-license` (design, "Roots, layers, overlays and the license gate").
  `bsd-target` restores the earlier target binding citation, so its license is gated with or
  without the flag. `docs-only` restores the FIFO depth and both original TRM citations.
- `board/`: `widgetchip.spec.yaml` cites a document only and fits every root;
  `widgetchip-bsd-overlay` adds a BSD-3-Clause repos entry no anchor cites (fits the GPL and
  permissive roots under `--require-license`, not the docs root); `widgetchip-gpl3-overlay` adds a
  GPL-3.0-only one (fits none); `widgetchip-src-overlay` anchors a `src` fact to a BSD-3-Clause
  entry (fits the GPL and permissive roots and fails the docs root with or without the flag).
  The tests also put `widgetchip` under the docs marker and an overlay under the permissive one:
  the overlay fails alone and passes beside its target, given as a checked or a context root.

`test_check.py` (`LicenseGateMatrix`, `BoardOverlays`) runs all of it and asserts that
`expected.json` lists exactly the specs present.
