/* ADC1 (housekeeping) and ADC2 (gate monitors): continuous scans, 16x oversampling, DMA circular. */
#include "hw.h"
#include "board.h"
#include "config.h"
#include "stm32g4xx_ll_adc.h"
#include "stm32g4xx_ll_bus.h"
#include "stm32g4xx_ll_dma.h"
#include "stm32g4xx_ll_dmamux.h"

enum { R1_VOUT, R1_CATH, R1_V48, R1_NTC1, R1_NTC2, R1_NTC3, R1_NTC4, R1_VREF, R1_N };
enum { R2_G1, R2_G2, R2_G3, R2_G4, R2_N };

static volatile uint16_t adc1_buf[R1_N];
static volatile uint16_t adc2_buf[R2_N];
static volatile float g_vdda = 3.3f;

static const uint32_t seq1[R1_N] = { ADC1_CH_VOUT, ADC1_CH_CATH, ADC1_CH_V48, ADC1_CH_NTC1, ADC1_CH_NTC2,
                                     ADC1_CH_NTC3, ADC1_CH_NTC4, LL_ADC_CHANNEL_VREFINT };
static const uint32_t seq2[R2_N] = { ADC2_CH_GMON1, ADC2_CH_GMON2, ADC2_CH_GMON3, ADC2_CH_GMON4 };
static const uint32_t ranks[8] = { LL_ADC_REG_RANK_1, LL_ADC_REG_RANK_2, LL_ADC_REG_RANK_3, LL_ADC_REG_RANK_4,
                                   LL_ADC_REG_RANK_5, LL_ADC_REG_RANK_6, LL_ADC_REG_RANK_7, LL_ADC_REG_RANK_8 };
static const uint32_t seqlen[9] = { 0, LL_ADC_REG_SEQ_SCAN_DISABLE, LL_ADC_REG_SEQ_SCAN_ENABLE_2RANKS,
                                    LL_ADC_REG_SEQ_SCAN_ENABLE_3RANKS, LL_ADC_REG_SEQ_SCAN_ENABLE_4RANKS,
                                    LL_ADC_REG_SEQ_SCAN_ENABLE_5RANKS, LL_ADC_REG_SEQ_SCAN_ENABLE_6RANKS,
                                    LL_ADC_REG_SEQ_SCAN_ENABLE_7RANKS, LL_ADC_REG_SEQ_SCAN_ENABLE_8RANKS };

static void adc_bringup(ADC_TypeDef *adc)
{
    LL_ADC_DisableDeepPowerDown(adc);
    LL_ADC_EnableInternalRegulator(adc);
    hw_delay_us(LL_ADC_DELAY_INTERNAL_REGUL_STAB_US + 5u);
    LL_ADC_StartCalibration(adc, LL_ADC_SINGLE_ENDED);
    while (LL_ADC_IsCalibrationOnGoing(adc)) {
    }
    hw_delay_us(5);
    LL_ADC_ClearFlag_ADRDY(adc);
    LL_ADC_Enable(adc);
    while (!LL_ADC_IsActiveFlag_ADRDY(adc)) {
    }
}

static void adc_sequence(ADC_TypeDef *adc, const uint32_t *seq, int n)
{
    LL_ADC_SetResolution(adc, LL_ADC_RESOLUTION_12B);
    LL_ADC_SetDataAlignment(adc, LL_ADC_DATA_ALIGN_RIGHT);
    LL_ADC_REG_SetTriggerSource(adc, LL_ADC_REG_TRIG_SOFTWARE);
    LL_ADC_REG_SetContinuousMode(adc, LL_ADC_REG_CONV_CONTINUOUS);
    LL_ADC_REG_SetDMATransfer(adc, LL_ADC_REG_DMA_TRANSFER_UNLIMITED);
    LL_ADC_REG_SetOverrun(adc, LL_ADC_REG_OVR_DATA_OVERWRITTEN);
    LL_ADC_REG_SetSequencerLength(adc, seqlen[n]);
    for (int i = 0; i < n; i++) {
        LL_ADC_REG_SetSequencerRanks(adc, ranks[i], seq[i]);
        LL_ADC_SetChannelSamplingTime(adc, seq[i], LL_ADC_SAMPLINGTIME_247CYCLES_5);
        LL_ADC_SetChannelSingleDiff(adc, seq[i], LL_ADC_SINGLE_ENDED);
    }
    LL_ADC_SetOverSamplingScope(adc, LL_ADC_OVS_GRP_REGULAR_CONTINUED);
    LL_ADC_ConfigOverSamplingRatioShift(adc, LL_ADC_OVS_RATIO_16, LL_ADC_OVS_SHIFT_RIGHT_4);
}

static void dma_ring(uint32_t ch, uint32_t req, ADC_TypeDef *adc, volatile uint16_t *buf, uint32_t n)
{
    LL_DMA_SetPeriphRequest(DMA1, ch, req);
    LL_DMA_ConfigTransfer(DMA1, ch, LL_DMA_DIRECTION_PERIPH_TO_MEMORY | LL_DMA_MODE_CIRCULAR |
                                        LL_DMA_PERIPH_NOINCREMENT | LL_DMA_MEMORY_INCREMENT |
                                        LL_DMA_PDATAALIGN_HALFWORD | LL_DMA_MDATAALIGN_HALFWORD |
                                        LL_DMA_PRIORITY_MEDIUM);
    LL_DMA_ConfigAddresses(DMA1, ch, LL_ADC_DMA_GetRegAddr(adc, LL_ADC_DMA_REG_REGULAR_DATA), (uint32_t)buf,
                           LL_DMA_DIRECTION_PERIPH_TO_MEMORY);
    LL_DMA_SetDataLength(DMA1, ch, n);
    LL_DMA_EnableChannel(DMA1, ch);
}

void hw_adc_init(void)
{
    LL_AHB1_GRP1_EnableClock(LL_AHB1_GRP1_PERIPH_DMA1 | LL_AHB1_GRP1_PERIPH_DMAMUX1);
    LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_ADC12);
    LL_ADC_SetCommonClock(__LL_ADC_COMMON_INSTANCE(ADC1), LL_ADC_CLOCK_SYNC_PCLK_DIV4);   /* 42.5 MHz */
    LL_ADC_SetCommonPathInternalCh(__LL_ADC_COMMON_INSTANCE(ADC1), LL_ADC_PATH_INTERNAL_VREFINT);
    adc_bringup(ADC1);
    adc_bringup(ADC2);
    adc_sequence(ADC1, seq1, R1_N);
    adc_sequence(ADC2, seq2, R2_N);
    dma_ring(LL_DMA_CHANNEL_1, LL_DMAMUX_REQ_ADC1, ADC1, adc1_buf, R1_N);
    dma_ring(LL_DMA_CHANNEL_2, LL_DMAMUX_REQ_ADC2, ADC2, adc2_buf, R2_N);
    LL_ADC_REG_StartConversion(ADC1);
    LL_ADC_REG_StartConversion(ADC2);
}

static float pin_v(uint16_t raw)
{
    return (float)raw * g_vdda / 4095.0f;
}

void hw_adc_read(analog_t *a)
{
    uint16_t vref = adc1_buf[R1_VREF];
    if (vref > 1000u)
        g_vdda = 3.0f * (float)(*VREFINT_CAL_ADDR) / (float)vref;
    a->vdda = g_vdda;
    a->v_out = pin_v(adc1_buf[R1_VOUT]) * VOUT_SENSE_GAIN;
    a->v_cath = pin_v(adc1_buf[R1_CATH]);
    a->v_48 = pin_v(adc1_buf[R1_V48]) * V48_SENSE_GAIN;
    a->ntc_v[0] = pin_v(adc1_buf[R1_NTC1]);
    a->ntc_v[1] = pin_v(adc1_buf[R1_NTC2]);
    a->ntc_v[2] = pin_v(adc1_buf[R1_NTC3]);
    a->ntc_v[3] = pin_v(adc1_buf[R1_NTC4]);
    for (int i = 0; i < 4; i++)
        a->gmon[i] = pin_v(adc2_buf[i]) * 2.0f;      /* 100k / 100k tap */
    hw_set_vdda(g_vdda);
}

float hw_adc_cath_fast(void)
{
    return pin_v(adc1_buf[R1_CATH]);
}

float hw_adc_vout_fast(void)
{
    return pin_v(adc1_buf[R1_VOUT]) * VOUT_SENSE_GAIN;
}
