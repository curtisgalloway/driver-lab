<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Synthetic Widget programming guide {#top}

This guide describes no real hardware.

## 1. Overview

The synthetic Widget has one control register and one status register.

## 2. Registers

### 2.1 Control register {#ctrl}

The control register sits at offset 0x10. Writing 0x1 starts a conversion.

Table 2-1. Control register fields

```text
# Not a heading: inside a fenced block
bit 0  START
```

### 2.2 Status register

The status register sits at offset 0x14.

## 3. Reset behavior

Reset completes in 10 clock cycles.
