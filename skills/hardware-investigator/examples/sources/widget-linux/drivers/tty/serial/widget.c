// SPDX-License-Identifier: GPL-2.0-only
/* Widget UART driver (synthetic fixture; not real code). */

#define WIDGET_CTRL		0x00	/* control */
#define WIDGET_CTRL_EN		BIT(0)	/* block enable */
#define WIDGET_BAUD		0x04	/* baud divisor */
#define WIDGET_LCR		0x08	/* line control; a write latches BAUD */
#define WIDGET_LCR_8N1		0x03

static void widget_uart_init(void __iomem *base, u32 divisor)
{
	writel(0, base + WIDGET_CTRL);
	writel(divisor, base + WIDGET_BAUD);
	writel(WIDGET_LCR_8N1, base + WIDGET_LCR);
	writel(WIDGET_CTRL_EN, base + WIDGET_CTRL);
}
