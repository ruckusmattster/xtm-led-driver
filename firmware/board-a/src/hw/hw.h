/* Board A hardware layer: everything that touches a register lives behind this header. */
#ifndef HW_H
#define HW_H

#include <stdint.h>
#include <stddef.h>

/* ------------------------------------------------------------------ core */
void hw_init_clock(void);              /* HSI16 -> PLL -> 170 MHz, boost mode, 4 wait states */
void hw_init_gpio(void);               /* safe states first: clamps on, buck off, CS high */
void hw_init_systick(void);
uint32_t hw_millis(void);
void hw_delay_us(uint32_t us);
void hw_iwdg_start(void);              /* ~50 ms watchdog */
void hw_iwdg_kick(void);
void hw_tick_start(uint32_t hz);       /* TIM6 periodic interrupt -> control_tick() */
uint32_t hw_reset_cause(void);         /* RCC_CSR reset flags, cleared after read */
void hw_reboot(void);

void hw_clamps(int on);                /* all four gate clamps */
void hw_buck_enable(int on);
int hw_buck_pg(void);
void hw_led(int on);
void hw_aok(int on);

/* ------------------------------------------------------------------ analog in (ADC1 + ADC2, DMA) */
typedef struct {
    float vdda;           /* from VREFINT */
    float v_out;          /* V_out, scaled */
    float v_cath;         /* cathode tap at the pin, volts */
    float v_48;           /* input rail */
    float ntc_v[4];       /* NTC divider voltages */
    float gmon[4];        /* op-amp outputs, volts (divider undone) */
} analog_t;

void hw_adc_init(void);
void hw_adc_read(analog_t *a);         /* latest averaged values */
float hw_adc_cath_fast(void);          /* cathode tap volts, callable from the tick */
float hw_adc_vout_fast(void);

/* ------------------------------------------------------------------ analog out */
void hw_buckdac_init(float v_dac);     /* DAC1 on PA4, buffered; value applied before the output enables */
void hw_buckdac_set(float v_dac);
float hw_buckdac_get(void);
void hw_set_vdda(float vdda);          /* scaling for DAC codes */
void hw_comp_init(void);               /* COMP1: PA1 vs DAC3_CH1, EXTI21 -> fault */
void hw_comp_threshold(float v);
void hw_comp_enable_irq(int en);
int hw_comp_output(void);

/* ------------------------------------------------------------------ DAC80504 on SPI1 */
int dac8_init(void);                   /* soft reset, config, sync mode, zero codes; 0 = ok */
void dac8_write(uint8_t reg, uint16_t val);
uint16_t dac8_read(uint8_t reg);
void dac8_load(void);                  /* TRIGGER.LDAC */
#define DAC8_REG_DEVICE_ID 0x01
#define DAC8_REG_SYNC      0x02
#define DAC8_REG_CONFIG    0x03
#define DAC8_REG_GAIN      0x04
#define DAC8_REG_TRIGGER   0x05
#define DAC8_REG_STATUS    0x07
#define DAC8_REG_DAC0      0x08
/* Register values the DAC must hold. GAIN: REF-DIV = 1 (2.5 V reference halved, keeping VREF/DIV under
 * VDD/2 on the 5 V supply) and gain 2 on all four buffers, so full scale stays 2.5 V. The GAIN and REFDIV
 * pins are strapped to VIO for the same power-up default. */
#define DAC8_CONFIG_VAL    0x0000u      /* SDO on, CRC off, internal reference on, all DACs on */
#define DAC8_GAIN_VAL      0x010Fu
#define DAC8_SYNC_VAL      0x000Fu      /* all four update on LDAC, no broadcast */
#define DAC8_STATUS_REFALM 0x0001u      /* reference alarm: buffer shut down, outputs at 0 V */

/* ------------------------------------------------------------------ UARTs (link = USART1, console = USART2) */
void hw_uart_init(void);
int hw_link_getc(void);                /* -1 if empty */
size_t hw_link_write(const uint8_t *p, size_t n);
int hw_con_getc(void);
size_t hw_con_write(const uint8_t *p, size_t n);

/* ------------------------------------------------------------------ flash (last 2 KB page) */
int hw_flash_load(void *dst, size_t n);        /* copies the page; returns 0 */
int hw_flash_store(const void *src, size_t n); /* erase + program; 0 = ok. Stalls the CPU ~25 ms */

/* ------------------------------------------------------------------ provided by the application */
void control_tick(void);               /* TIM6, 4 kHz */
void control_fault_isr(void);          /* COMP1 trip */

#endif
