---
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
---

# Two named pins: BSD firmware and a GPL-2.0-only kernel (synthetic license-gate fixture)

Source pin: tools@439b619 BSD-3-Clause
Source pin: linux@1111111 GPL-2.0-only

## Facts

- The stub magic is at 0xF0. [src:tools: armstubs/armstub8.S:30]
- CTRL is at offset 0x10. [src:linux: drivers/widget.c:2]
