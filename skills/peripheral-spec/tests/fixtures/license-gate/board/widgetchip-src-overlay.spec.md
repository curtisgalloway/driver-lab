---
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
overlays: widgetchip
resources:
  repos:
    - name: tools
      url: https://example.invalid/tools
      ref: 439b6198a9b340de5998dd14a26a0d9d38a6bcac
      license: BSD-3-Clause
---
# Widget chip: a fact read from BSD-3-Clause source (synthetic license-gate fixture)

An overlay with a `[src]` fact anchored to a BSD-3-Clause repository pinned to a commit: it fits
the GPL and permissive roots, and fails the docs root, which accepts no source.

## Quick-facts

- **Counter frequency.** The boot stub writes 54000000 to the counter-frequency register.
  `[src]` ([src:tools: boot/stub.S:53-57 (OSC_FREQ)])
