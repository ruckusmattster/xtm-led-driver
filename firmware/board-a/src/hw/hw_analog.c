/* DAC1 (buck FB injection on PA4), DAC3 (comparator threshold) and COMP1 (cathode short trip). */
#include "hw.h"
#include "board.h"
#include "config.h"
#include "stm32g4xx_ll_bus.h"
#include "stm32g4xx_ll_comp.h"
#include "stm32g4xx_ll_dac.h"
#include "stm32g4xx_ll_exti.h"

static volatile float g_vdda_out = 3.3f;
static volatile float g_vdac = VDAC_MAX_V;

void hw_set_vdda(float vdda)
{
    if (vdda > 2.9f && vdda < 3.6f)
        g_vdda_out = vdda;
}

static uint32_t code_of(float v)
{
    float c = v / g_vdda_out * 4095.0f;
    if (c < 0.0f)
        c = 0.0f;
    if (c > 4095.0f)
        c = 4095.0f;
    return (uint32_t)(c + 0.5f);
}

void hw_buckdac_init(float v_dac)
{
    LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_DAC1);
    LL_DAC_SetHighFrequencyMode(DAC1, LL_DAC_HIGH_FREQ_MODE_ABOVE_160MHZ);
    LL_DAC_ConfigOutput(DAC1, LL_DAC_CHANNEL_1, LL_DAC_OUTPUT_MODE_NORMAL, LL_DAC_OUTPUT_BUFFER_ENABLE,
                        LL_DAC_OUTPUT_CONNECT_GPIO);
    LL_DAC_DisableTrigger(DAC1, LL_DAC_CHANNEL_1);
    g_vdac = v_dac;
    LL_DAC_ConvertData12RightAligned(DAC1, LL_DAC_CHANNEL_1, code_of(v_dac));   /* before the output wakes */
    LL_DAC_Enable(DAC1, LL_DAC_CHANNEL_1);
    hw_delay_us(20);
}

void hw_buckdac_set(float v_dac)
{
    if (v_dac < VDAC_MIN_V)
        v_dac = VDAC_MIN_V;
    if (v_dac > VDAC_MAX_V)
        v_dac = VDAC_MAX_V;
    g_vdac = v_dac;
    LL_DAC_ConvertData12RightAligned(DAC1, LL_DAC_CHANNEL_1, code_of(v_dac));
}

float hw_buckdac_get(void)
{
    return g_vdac;
}

void hw_comp_init(void)
{
    LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_DAC3);
    LL_DAC_SetHighFrequencyMode(DAC3, LL_DAC_HIGH_FREQ_MODE_ABOVE_160MHZ);
    LL_DAC_ConfigOutput(DAC3, LL_DAC_CHANNEL_1, LL_DAC_OUTPUT_MODE_NORMAL, LL_DAC_OUTPUT_BUFFER_DISABLE,
                        LL_DAC_OUTPUT_CONNECT_INTERNAL);
    LL_DAC_DisableTrigger(DAC3, LL_DAC_CHANNEL_1);
    LL_DAC_ConvertData12RightAligned(DAC3, LL_DAC_CHANNEL_1, code_of(CATH_TRIP_MAX_V));
    LL_DAC_Enable(DAC3, LL_DAC_CHANNEL_1);
    hw_delay_us(20);

    LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_SYSCFG);
    LL_COMP_SetInputPlus(COMP1, LL_COMP_INPUT_PLUS_IO1);          /* PA1: cathode tap */
    LL_COMP_SetInputMinus(COMP1, LL_COMP_INPUT_MINUS_DAC3_CH1);
    LL_COMP_SetInputHysteresis(COMP1, LL_COMP_HYSTERESIS_10MV);
    LL_COMP_SetOutputPolarity(COMP1, LL_COMP_OUTPUTPOL_NONINVERTED);
    LL_COMP_SetOutputBlankingSource(COMP1, LL_COMP_BLANKINGSRC_NONE);
    LL_COMP_Enable(COMP1);
    hw_delay_us(10);

    LL_EXTI_EnableRisingTrig_0_31(LL_EXTI_LINE_21);
    LL_EXTI_ClearFlag_0_31(LL_EXTI_LINE_21);
    LL_EXTI_DisableIT_0_31(LL_EXTI_LINE_21);
    NVIC_SetPriority(COMP1_2_3_IRQn, 0);
    NVIC_EnableIRQ(COMP1_2_3_IRQn);
}

void hw_comp_threshold(float v)
{
    LL_DAC_ConvertData12RightAligned(DAC3, LL_DAC_CHANNEL_1, code_of(v));
}

void hw_comp_enable_irq(int en)
{
    if (en) {
        LL_EXTI_ClearFlag_0_31(LL_EXTI_LINE_21);
        NVIC_ClearPendingIRQ(COMP1_2_3_IRQn);
        LL_EXTI_EnableIT_0_31(LL_EXTI_LINE_21);
    } else {
        LL_EXTI_DisableIT_0_31(LL_EXTI_LINE_21);
    }
}

int hw_comp_output(void)
{
    return LL_COMP_ReadOutputLevel(COMP1) == LL_COMP_OUTPUT_LEVEL_HIGH;
}

void COMP1_2_3_IRQHandler(void)
{
    if (LL_EXTI_IsActiveFlag_0_31(LL_EXTI_LINE_21)) {
        LL_EXTI_ClearFlag_0_31(LL_EXTI_LINE_21);
        hw_clamps(1);                              /* first, before anything else */
        LL_EXTI_DisableIT_0_31(LL_EXTI_LINE_21);
        control_fault_isr();
    }
}
