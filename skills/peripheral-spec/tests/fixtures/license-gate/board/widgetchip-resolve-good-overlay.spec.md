---
overlays: widgetchip
resources:
  repos:
    - name: rpi-tools
      url: https://github.com/raspberrypi/tools
      ref: 439b6198a9b340de5998dd14a26a0d9d38a6bcac
      license: BSD-3-Clause
---
<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Widget chip: an anchor resolved against a real pinned repository (synthetic fixture)

Used by the spec repositories' self-test when `RESOLVE_SRC=1`: `fetch_src_pins.py` fetches the
pinned commit and `anchor_check.py` resolves the anchor below, which exists at the pin, so it must pass. The pass and fail pair
proves that resolution ran, not only the form and license checks. It names a symbol only.

## Quick-facts

- **Counter frequency.** The stub defines the counter frequency. `[src]` ([src:rpi-tools: armstubs/armstub8.S:53-57 (OSC_FREQ)])
