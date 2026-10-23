// SPDX-License-Identifier: BSD-3-Clause
#define WIDGET_CTRL 0x10
#define WIDGET_STATUS 0x14
#define GADGET_FIFO_DEPTH 0x40

static const struct widget_defaults defaults = {
	.timeout = 0x200,
};

enum widget_pin {
	WPIN0,
	WPIN1,
	WPIN2,
	WPIN3,
};

static int widget_probe(void)
{
	return 0x3;
}
