/* DAC80504 on SPI1: mode 1, 8-bit transfers, 10.6 MHz (reads are specified to 12 MHz with FSDO = 0). */
#include "hw.h"
#include "board.h"
#include "stm32g4xx_ll_bus.h"
#include "stm32g4xx_ll_gpio.h"
#include "stm32g4xx_ll_spi.h"

static inline void cs_low(void) { DAC_CS_PORT->BRR = DAC_CS_PIN; }
static inline void cs_high(void) { DAC_CS_PORT->BSRR = DAC_CS_PIN; }

static uint8_t xfer(uint8_t b)
{
    while (!LL_SPI_IsActiveFlag_TXE(SPI1)) {
    }
    LL_SPI_TransmitData8(SPI1, b);
    while (!LL_SPI_IsActiveFlag_RXNE(SPI1)) {
    }
    return LL_SPI_ReceiveData8(SPI1);
}

static uint32_t frame(uint32_t w)
{
    cs_low();
    __NOP(); __NOP(); __NOP(); __NOP();
    uint32_t r = (uint32_t)xfer((uint8_t)(w >> 16)) << 16;
    r |= (uint32_t)xfer((uint8_t)(w >> 8)) << 8;
    r |= xfer((uint8_t)w);
    while (LL_SPI_IsActiveFlag_BSY(SPI1)) {
    }
    cs_high();
    for (volatile int i = 0; i < 8; i++) {   /* CS high time between frames */
    }
    return r;
}

void dac8_write(uint8_t reg, uint16_t val)
{
    frame(((uint32_t)(reg & 0x0Fu) << 16) | val);
}

uint16_t dac8_read(uint8_t reg)
{
    frame(0x800000u | ((uint32_t)(reg & 0x0Fu) << 16));
    return (uint16_t)(frame(0x000000u) & 0xFFFFu);     /* NOP frame clocks the data out */
}

void dac8_load(void)
{
    dac8_write(DAC8_REG_TRIGGER, 1u << 4);             /* LDAC */
}

int dac8_init(void)
{
    LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_SPI1);
    LL_SPI_Disable(SPI1);
    LL_SPI_SetMode(SPI1, LL_SPI_MODE_MASTER);
    LL_SPI_SetTransferDirection(SPI1, LL_SPI_FULL_DUPLEX);
    LL_SPI_SetClockPolarity(SPI1, LL_SPI_POLARITY_LOW);
    LL_SPI_SetClockPhase(SPI1, LL_SPI_PHASE_2EDGE);           /* mode 1: data latched on the falling edge */
    LL_SPI_SetBaudRatePrescaler(SPI1, LL_SPI_BAUDRATEPRESCALER_DIV16);
    LL_SPI_SetTransferBitOrder(SPI1, LL_SPI_MSB_FIRST);
    LL_SPI_SetDataWidth(SPI1, LL_SPI_DATAWIDTH_8BIT);
    LL_SPI_SetNSSMode(SPI1, LL_SPI_NSS_SOFT);
    LL_SPI_SetRxFIFOThreshold(SPI1, LL_SPI_RX_FIFO_TH_QUARTER);
    LL_SPI_Enable(SPI1);

    dac8_write(DAC8_REG_TRIGGER, 0x000Au);                     /* soft reset */
    hw_delay_us(1000);
    dac8_write(DAC8_REG_CONFIG, DAC8_CONFIG_VAL);
    dac8_write(DAC8_REG_GAIN, DAC8_GAIN_VAL);                  /* 2.5 V / 2 x gain 2: 0-2.5 V */
    dac8_write(DAC8_REG_SYNC, DAC8_SYNC_VAL);
    for (uint8_t k = 0; k < 4; k++)
        dac8_write((uint8_t)(DAC8_REG_DAC0 + k), 0);
    dac8_load();

    int err = 0;
    if (dac8_read(DAC8_REG_SYNC) != DAC8_SYNC_VAL)
        err |= 1;
    if (dac8_read(DAC8_REG_GAIN) != DAC8_GAIN_VAL)
        err |= 2;
    if (dac8_read(DAC8_REG_CONFIG) != DAC8_CONFIG_VAL)
        err |= 4;
    if (dac8_read(DAC8_REG_STATUS) & DAC8_STATUS_REFALM)
        err |= 16;
    uint16_t id = dac8_read(DAC8_REG_DEVICE_ID);
    if (id == 0x0000u || id == 0xFFFFu)
        err |= 8;
    return err;
}
