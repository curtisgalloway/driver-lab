---
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
overlays: widgetchip
resources:
  repos:
    - name: gnutool
      url: https://example.invalid/gnutool
      ref: 3333333
      license: GPL-3.0-only
---
# Widget chip: a GPL-3.0-only source (synthetic license-gate fixture)

An overlay whose `resources.repos` entry is licensed GPL-3.0-only: under
`spec_check.py --require-license` it fits no spec repository.

## Quick-facts

- The boot stub sets the counter frequency. `[doc]` (Widget boot notes §2)
