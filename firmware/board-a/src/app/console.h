/* Calibration and bring-up console on USART2 (STLINK-V3MINIE virtual COM port, 115200 8N1). */
#ifndef CONSOLE_H
#define CONSOLE_H

#include <stdint.h>

void console_init(uint32_t reset_cause, int dac_err);
void console_poll(void);
void con_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

#endif
