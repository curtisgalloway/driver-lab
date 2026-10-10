<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# SPDX acceptance tests

**Terms:** SPDX expressions identify licenses and combine them with `OR`, `AND` and `WITH`.
See the [glossary](../../../GLOSSARY.md).

```bash
python3 -m unittest discover -s skills/board-expert/tests -v
```

`test_spdx.py` tests the shared SPDX expression parser and acceptance rules. Format 2
structure, references, license gates, records and stub resolution are tested under
`skills/spec-format/tests`; its fixtures include the board and peripheral license matrices.
