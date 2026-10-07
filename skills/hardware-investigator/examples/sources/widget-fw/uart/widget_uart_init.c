/* SPDX-License-Identifier: MIT */
/* Widget firmware UART bring-up (synthetic fixture; not real code). */

#define UART_CTRL	0x00	/* control; bit 0 enables the block */
#define UART_BAUD	0x04	/* baud divisor */
#define UART_LCR	0x08	/* line control; a write latches BAUD */

void uart_early_init(volatile unsigned int *base, unsigned int divisor)
{
	base[UART_CTRL / 4] = 0;	/* disable before reprogramming */
	base[UART_BAUD / 4] = divisor;
	base[UART_LCR / 4] = 0x03;	/* 8N1; also latches the divisor */
	base[UART_CTRL / 4] = 1;	/* enable */
}
