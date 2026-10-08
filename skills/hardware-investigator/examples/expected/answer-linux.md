---
# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
---

# Widget UART: control register and init order (facts for peripheral-spec)

Source pin: linux@REV GPL-2.0-only

## Facts

- CTRL is at offset 0x00, and bit 0 enables the block. [src:linux: drivers/tty/serial/widget.c:4-5 (WIDGET_CTRL)]
- BAUD, the baud divisor, is at offset 0x04. [src:linux: drivers/tty/serial/widget.c:6 (WIDGET_BAUD)]
- LCR is at offset 0x08, and a write to it latches BAUD. [src:linux: drivers/tty/serial/widget.c:7 (WIDGET_LCR)]
- The driver initializes the block by clearing CTRL, writing BAUD, writing LCR, then setting the enable bit. [as-implemented] [src:linux: drivers/tty/serial/widget.c:12-15 (widget_uart_init)]
