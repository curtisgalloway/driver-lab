---
docs:
  - name: trm
    title: Widget TRM v1.0
    url: https://example.invalid/widget-trm.pdf
    sha256: 1218036a6a0562504adedd37088e5136036a3099cf8581832e0c7353d7256cbd
    pages: 120
---
<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Datasheet only, named document anchors (synthetic license-gate fixture)

The shape `hardware-specs-docs` requires: no pins, and every document listed under `docs:` and
cited by name, so it passes the docs root under `--require-license` (where the free-text
`docs-only-spec.md` fails).

## Facts

- The block resets in 10 us. [doc:trm §4.2 p.40]
- The FIFO is 64 entries deep. [doc:trm §5.1 p.52]
