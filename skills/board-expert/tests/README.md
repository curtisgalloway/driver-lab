<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SPDX acceptance tests

**Terms:** SPDX expressions identify licenses and combine them with `OR`, `AND` and `WITH`.
See the [glossary](../../../GLOSSARY.md).

```bash
cargo test --locked --offline --test test_yaml_spdx
```

`tests/test_yaml_spdx.rs` tests the shared SPDX expression parser and acceptance rules (`src/spdx.rs`).
Spec structure, references, license gates, records and stub resolution are tested in the crate's
integration and conformance test suites (`cargo test --locked --offline`); the fixtures live under
`skills/spec-format/tests/fixtures`.
