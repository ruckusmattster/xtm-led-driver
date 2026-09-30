/* Board A pin map (matches design/board_a.py, sheet A6). */
#ifndef BOARD_H
#define BOARD_H

#include "stm32g4xx.h"

/* gate clamps ch1..ch4: high = clamp on (gate held low). Pulled up in hardware. */
#define CLAMP1_PORT GPIOC
#define CLAMP1_PIN  LL_GPIO_PIN_6
#define CLAMP2_PORT GPIOA
#define CLAMP2_PIN  LL_GPIO_PIN_8
#define CLAMP3_PORT GPIOC
#define CLAMP3_PIN  LL_GPIO_PIN_10
#define CLAMP4_PORT GPIOB
#define CLAMP4_PIN  LL_GPIO_PIN_7

/* PC13, not PB9: the ROM bootloader drives PB9 (its FDCAN1_TX) high, and PC13 has no bootloader
 * function, so R10's 100k pull-down keeps the buck off in reset, in the bootloader and when unprogrammed. */
#define BUCK_EN_PORT GPIOC
#define BUCK_EN_PIN  LL_GPIO_PIN_13
#define BUCK_PG_PORT GPIOC
#define BUCK_PG_PIN  LL_GPIO_PIN_4

#define LED_PORT GPIOA
#define LED_PIN  LL_GPIO_PIN_12
#define AOK_PORT GPIOA
#define AOK_PIN  LL_GPIO_PIN_11

#define DAC_CS_PORT GPIOA
#define DAC_CS_PIN  LL_GPIO_PIN_15

/* analog inputs */
#define ADC1_CH_VOUT  LL_ADC_CHANNEL_1    /* PA0 */
#define ADC1_CH_CATH  LL_ADC_CHANNEL_2    /* PA1, also COMP1_INP */
#define ADC1_CH_V48   LL_ADC_CHANNEL_15   /* PB0 */
#define ADC1_CH_NTC1  LL_ADC_CHANNEL_12   /* PB1  FET */
#define ADC1_CH_NTC2  LL_ADC_CHANNEL_14   /* PB11 main buck */
#define ADC1_CH_NTC3  LL_ADC_CHANNEL_11   /* PB12 aux rails */
#define ADC1_CH_NTC4  LL_ADC_CHANNEL_5    /* PB14 precision section */
#define ADC2_CH_GMON1 LL_ADC_CHANNEL_3    /* PA6 */
#define ADC2_CH_GMON2 LL_ADC_CHANNEL_4    /* PA7 */
#define ADC2_CH_GMON3 LL_ADC_CHANNEL_12   /* PB2 */
#define ADC2_CH_GMON4 LL_ADC_CHANNEL_15   /* PB15 */

#endif
