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
  named pins, a target-side pin, and a license that is not SPDX.
- `expected.json`: the exit code of `anchor_check.py <spec> --root roots/<root>` for every pair
  (0 passes, 1 fails). `test_anchor_check.py` (`TestLicenseGate.test_fixture_matrix`) runs the
  whole matrix and asserts the file lists exactly the specs present.

A spec repository's CI self-test can copy its root's column: the specs marked 0 must pass and
those marked 1 must fail with a `license gate:` message (or, for `invalid-license-spec.md`,
`is not an SPDX expression`).
