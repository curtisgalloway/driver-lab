---
overlays: widgetchip
resources:
  repos:
    - name: tools
      url: https://example.invalid/tools
      ref: 439b619
      license: BSD-3-Clause
---
<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Widget chip: a BSD-3-Clause source (synthetic license-gate fixture)

An overlay whose `resources.repos` entry is licensed BSD-3-Clause: under
`spec_check.py --require-license` it fits the GPL and permissive roots, not the docs root.

## Quick-facts

- The boot stub sets the counter frequency. `[doc]` (Widget boot notes §2)
