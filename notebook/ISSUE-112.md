<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Issue 112

**Terms.** A readback worklist is the list of open questions a physical readback phase would
settle on hardware. A TODO is the `todo` field of a spec record. See the
[glossary](../GLOSSARY.md).

## 2026-10-14 — TODO worklist

The schema allows a `todo` in more places than the issue names: instance and variant rows,
assumptions, and the fields, layout fields, steps and order rows of a typed payload. The new
`spec.py todo` lists all of them and names the place in `kind`, so a readback plan does not miss one. A payload
row is listed under its parent fact's reference with the row id appended, because the record
keys only the supported rows. The shipped `skills/board-expert/specs` root holds no spec files,
so the smoke run lists nothing; the tests carry the coverage. The
[acceptance evidence](../evidence/ISSUE-112.md) records the outcome.
