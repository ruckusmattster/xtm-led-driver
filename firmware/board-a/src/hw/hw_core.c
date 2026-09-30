/* Clock, GPIO, SysTick, watchdog, the 4 kHz tick timer, and the digital outputs. */
#include "hw.h"
#include "board.h"
#include "stm32g4xx_ll_bus.h"
#include "stm32g4xx_ll_cortex.h"
#include "stm32g4xx_ll_gpio.h"
#include "stm32g4xx_ll_iwdg.h"
#include "stm32g4xx_ll_pwr.h"
#include "stm32g4xx_ll_rcc.h"
#include "stm32g4xx_ll_system.h"
#include "stm32g4xx_ll_tim.h"

static volatile uint32_t g_ms;

void hw_init_clock(void)
{
    LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_SYSCFG);
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_PWR);
    /* The UCPD dead-battery pull-downs sit on PB4 (SPI MISO) and PB6 until disabled. */
    LL_PWR_DisableUCPDDeadBattery();

    LL_FLASH_SetLatency(LL_FLASH_LATENCY_4);
    while (LL_FLASH_GetLatency() != LL_FLASH_LATENCY_4) {
    }
    LL_PWR_SetRegulVoltageScaling(LL_PWR_REGU_VOLTAGE_SCALE1);
    LL_PWR_EnableRange1BoostMode();

    LL_RCC_HSI_Enable();
    while (!LL_RCC_HSI_IsReady()) {
    }
    /* 16 MHz / 4 * 85 / 2 = 170 MHz */
    LL_RCC_PLL_ConfigDomain_SYS(LL_RCC_PLLSOURCE_HSI, LL_RCC_PLLM_DIV_4, 85, LL_RCC_PLLR_DIV_2);
    LL_RCC_PLL_EnableDomain_SYS();
    LL_RCC_PLL_Enable();
    while (!LL_RCC_PLL_IsReady()) {
    }
    /* Boost-mode switch above 150 MHz: pass through AHB/2 for at least 1 us (RM0440 6.1.5) */
    LL_RCC_SetAHBPrescaler(LL_RCC_SYSCLK_DIV_2);
    LL_RCC_SetSysClkSource(LL_RCC_SYS_CLKSOURCE_PLL);
    while (LL_RCC_GetSysClkSource() != LL_RCC_SYS_CLKSOURCE_STATUS_PLL) {
    }
    for (volatile int i = 0; i < 200; i++) {
    }
    LL_RCC_SetAHBPrescaler(LL_RCC_SYSCLK_DIV_1);
    LL_RCC_SetAPB1Prescaler(LL_RCC_APB1_DIV_1);
    LL_RCC_SetAPB2Prescaler(LL_RCC_APB2_DIV_1);
    LL_FLASH_EnablePrefetch();
    LL_FLASH_EnableInstCache();
    LL_FLASH_EnableDataCache();
    SystemCoreClock = 170000000u;
}

static void out_pin(GPIO_TypeDef *port, uint32_t pin, int level, uint32_t speed)
{
    if (level)
        LL_GPIO_SetOutputPin(port, pin);
    else
        LL_GPIO_ResetOutputPin(port, pin);
    LL_GPIO_SetPinOutputType(port, pin, LL_GPIO_OUTPUT_PUSHPULL);
    LL_GPIO_SetPinSpeed(port, pin, speed);
    LL_GPIO_SetPinPull(port, pin, LL_GPIO_PULL_NO);
    LL_GPIO_SetPinMode(port, pin, LL_GPIO_MODE_OUTPUT);
}

static void af_pin(GPIO_TypeDef *port, uint32_t pin, uint32_t af, uint32_t pull)
{
    if (pin < LL_GPIO_PIN_8)
        LL_GPIO_SetAFPin_0_7(port, pin, af);
    else
        LL_GPIO_SetAFPin_8_15(port, pin, af);
    LL_GPIO_SetPinSpeed(port, pin, LL_GPIO_SPEED_FREQ_VERY_HIGH);
    LL_GPIO_SetPinOutputType(port, pin, LL_GPIO_OUTPUT_PUSHPULL);
    LL_GPIO_SetPinPull(port, pin, pull);
    LL_GPIO_SetPinMode(port, pin, LL_GPIO_MODE_ALTERNATE);
}

void hw_init_gpio(void)
{
    LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOA | LL_AHB2_GRP1_PERIPH_GPIOB | LL_AHB2_GRP1_PERIPH_GPIOC);
    /* safe states before anything else */
    out_pin(CLAMP1_PORT, CLAMP1_PIN, 1, LL_GPIO_SPEED_FREQ_LOW);
    out_pin(CLAMP2_PORT, CLAMP2_PIN, 1, LL_GPIO_SPEED_FREQ_LOW);
    out_pin(CLAMP3_PORT, CLAMP3_PIN, 1, LL_GPIO_SPEED_FREQ_LOW);
    out_pin(CLAMP4_PORT, CLAMP4_PIN, 1, LL_GPIO_SPEED_FREQ_LOW);
    out_pin(BUCK_EN_PORT, BUCK_EN_PIN, 0, LL_GPIO_SPEED_FREQ_LOW);
    out_pin(LED_PORT, LED_PIN, 0, LL_GPIO_SPEED_FREQ_LOW);
    out_pin(AOK_PORT, AOK_PIN, 0, LL_GPIO_SPEED_FREQ_LOW);
    out_pin(DAC_CS_PORT, DAC_CS_PIN, 1, LL_GPIO_SPEED_FREQ_HIGH);
    LL_GPIO_SetPinMode(BUCK_PG_PORT, BUCK_PG_PIN, LL_GPIO_MODE_INPUT);
    LL_GPIO_SetPinPull(BUCK_PG_PORT, BUCK_PG_PIN, LL_GPIO_PULL_NO);
    /* SPI1: PB3 SCK, PB4 MISO, PB5 MOSI (AF5) */
    af_pin(GPIOB, LL_GPIO_PIN_3, LL_GPIO_AF_5, LL_GPIO_PULL_NO);
    af_pin(GPIOB, LL_GPIO_PIN_4, LL_GPIO_AF_5, LL_GPIO_PULL_DOWN);
    af_pin(GPIOB, LL_GPIO_PIN_5, LL_GPIO_AF_5, LL_GPIO_PULL_NO);
    /* USART1: PA9 TX, PA10 RX (AF7). USART2: PA2 TX, PA3 RX (AF7) */
    af_pin(GPIOA, LL_GPIO_PIN_9, LL_GPIO_AF_7, LL_GPIO_PULL_NO);
    af_pin(GPIOA, LL_GPIO_PIN_10, LL_GPIO_AF_7, LL_GPIO_PULL_UP);
    af_pin(GPIOA, LL_GPIO_PIN_2, LL_GPIO_AF_7, LL_GPIO_PULL_NO);
    af_pin(GPIOA, LL_GPIO_PIN_3, LL_GPIO_AF_7, LL_GPIO_PULL_UP);
    /* every analog input, PA4 (DAC1_OUT1) and the unused pins stay in their reset (analog) mode */
}

void hw_init_systick(void)
{
    SysTick_Config(SystemCoreClock / 1000u);
    NVIC_SetPriority(SysTick_IRQn, 4);
}

void SysTick_Handler(void)
{
    g_ms++;
}

uint32_t hw_millis(void)
{
    return g_ms;
}

void hw_delay_us(uint32_t us)
{
    /* DWT cycle counter */
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    uint32_t start = DWT->CYCCNT, n = us * (SystemCoreClock / 1000000u);
    while ((DWT->CYCCNT - start) < n) {
    }
}

void hw_iwdg_start(void)
{
    LL_DBGMCU_APB1_GRP1_FreezePeriph(LL_DBGMCU_APB1_GRP1_IWDG_STOP);
    LL_IWDG_Enable(IWDG);
    LL_IWDG_EnableWriteAccess(IWDG);
    LL_IWDG_SetPrescaler(IWDG, LL_IWDG_PRESCALER_16);   /* 32 kHz / 16 = 2 kHz */
    LL_IWDG_SetReloadCounter(IWDG, 100);                /* 50 ms */
    while (!LL_IWDG_IsReady(IWDG)) {
    }
    LL_IWDG_ReloadCounter(IWDG);
}

void hw_iwdg_kick(void)
{
    LL_IWDG_ReloadCounter(IWDG);
}

uint32_t hw_reset_cause(void)
{
    uint32_t csr = RCC->CSR;
    LL_RCC_ClearResetFlags();
    return csr;
}

void hw_reboot(void)
{
    NVIC_SystemReset();
}

void hw_tick_start(uint32_t hz)
{
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_TIM6);
    LL_TIM_SetPrescaler(TIM6, 0);
    LL_TIM_SetAutoReload(TIM6, SystemCoreClock / hz - 1u);
    LL_TIM_SetCounter(TIM6, 0);
    LL_TIM_ClearFlag_UPDATE(TIM6);
    LL_TIM_EnableIT_UPDATE(TIM6);
    NVIC_SetPriority(TIM6_DAC_IRQn, 1);
    NVIC_EnableIRQ(TIM6_DAC_IRQn);
    LL_TIM_EnableCounter(TIM6);
}

void TIM6_DAC_IRQHandler(void)
{
    if (LL_TIM_IsActiveFlag_UPDATE(TIM6)) {
        LL_TIM_ClearFlag_UPDATE(TIM6);
        control_tick();
    }
}

void hw_clamps(int on)
{
    uint32_t a = CLAMP2_PIN, b = CLAMP4_PIN, c = CLAMP1_PIN | CLAMP3_PIN;   /* PA8; PB7; PC6 + PC10 */
    if (on) {
        GPIOA->BSRR = a;
        GPIOB->BSRR = b;
        GPIOC->BSRR = c;
    } else {
        GPIOA->BRR = a;
        GPIOB->BRR = b;
        GPIOC->BRR = c;
    }
}

void hw_buck_enable(int on)
{
    if (on)
        LL_GPIO_SetOutputPin(BUCK_EN_PORT, BUCK_EN_PIN);
    else
        LL_GPIO_ResetOutputPin(BUCK_EN_PORT, BUCK_EN_PIN);
}

int hw_buck_pg(void)
{
    return LL_GPIO_IsInputPinSet(BUCK_PG_PORT, BUCK_PG_PIN) ? 1 : 0;
}

void hw_led(int on)
{
    if (on)
        LL_GPIO_SetOutputPin(LED_PORT, LED_PIN);
    else
        LL_GPIO_ResetOutputPin(LED_PORT, LED_PIN);
}

void hw_aok(int on)
{
    if (on)
        LL_GPIO_SetOutputPin(AOK_PORT, AOK_PIN);
    else
        LL_GPIO_ResetOutputPin(AOK_PORT, AOK_PIN);
}
