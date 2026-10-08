---
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
---

# Widget UART: control register and init order (facts for peripheral-spec)

Source pin: fw@REV MIT

## Facts

- CTRL is at offset 0x00, and bit 0 enables the block. [src:fw: uart/widget_uart_init.c:4 (UART_CTRL)]
- BAUD, the baud divisor, is at offset 0x04. [src:fw: uart/widget_uart_init.c:5 (UART_BAUD)]
- LCR is at offset 0x08, and a write to it latches BAUD. [src:fw: uart/widget_uart_init.c:6 (UART_LCR)]
- The firmware disables the block before reprogramming it, writes BAUD, writes LCR, then enables the block. [comment-explained] [src:fw: uart/widget_uart_init.c:10-13 (uart_early_init)]
