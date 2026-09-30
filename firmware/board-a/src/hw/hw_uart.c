/* USART1 = link to Board B (PA9/PA10), USART2 = calibration console on the STLINK VCP (PA2/PA3). */
#include "hw.h"
#include "link_protocol.h"
#include "stm32g4xx_ll_bus.h"
#include "stm32g4xx_ll_rcc.h"
#include "stm32g4xx_ll_usart.h"

typedef struct {
    volatile uint16_t head, tail;
    uint8_t buf[512];
} ring_t;

static ring_t link_rx, link_tx, con_rx, con_tx;

static int ring_put(ring_t *r, uint8_t b)
{
    uint16_t next = (uint16_t)((r->head + 1u) % sizeof(r->buf));
    if (next == r->tail)
        return 0;
    r->buf[r->head] = b;
    r->head = next;
    return 1;
}

static int ring_get(ring_t *r)
{
    if (r->head == r->tail)
        return -1;
    uint8_t b = r->buf[r->tail];
    r->tail = (uint16_t)((r->tail + 1u) % sizeof(r->buf));
    return b;
}

static void uart_setup(USART_TypeDef *u, uint32_t pclk, IRQn_Type irq)
{
    LL_USART_Disable(u);
    LL_USART_SetTransferDirection(u, LL_USART_DIRECTION_TX_RX);
    LL_USART_ConfigCharacter(u, LL_USART_DATAWIDTH_8B, LL_USART_PARITY_NONE, LL_USART_STOPBITS_1);
    LL_USART_SetOverSampling(u, LL_USART_OVERSAMPLING_16);
    LL_USART_SetBaudRate(u, pclk, LL_USART_PRESCALER_DIV1, LL_USART_OVERSAMPLING_16, LINK_BAUD);
    LL_USART_Enable(u);
    while (!LL_USART_IsActiveFlag_TEACK(u) || !LL_USART_IsActiveFlag_REACK(u)) {
    }
    LL_USART_EnableIT_RXNE_RXFNE(u);
    NVIC_SetPriority(irq, 3);
    NVIC_EnableIRQ(irq);
}

void hw_uart_init(void)
{
    LL_RCC_SetUSARTClockSource(LL_RCC_USART1_CLKSOURCE_PCLK2);
    LL_RCC_SetUSARTClockSource(LL_RCC_USART2_CLKSOURCE_PCLK1);
    LL_APB2_GRP1_EnableClock(LL_APB2_GRP1_PERIPH_USART1);
    LL_APB1_GRP1_EnableClock(LL_APB1_GRP1_PERIPH_USART2);
    uart_setup(USART1, SystemCoreClock, USART1_IRQn);
    uart_setup(USART2, SystemCoreClock, USART2_IRQn);
}

static void uart_irq(USART_TypeDef *u, ring_t *rx, ring_t *tx)
{
    uint32_t isr = u->ISR;
    if (isr & (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE | USART_ISR_PE))
        u->ICR = USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NECF | USART_ICR_PECF;
    if (isr & USART_ISR_RXNE_RXFNE)
        ring_put(rx, (uint8_t)u->RDR);
    if ((u->CR1 & USART_CR1_TXEIE_TXFNFIE) && (isr & USART_ISR_TXE_TXFNF)) {
        int b = ring_get(tx);
        if (b < 0)
            LL_USART_DisableIT_TXE_TXFNF(u);
        else
            u->TDR = (uint8_t)b;
    }
}

void USART1_IRQHandler(void) { uart_irq(USART1, &link_rx, &link_tx); }
void USART2_IRQHandler(void) { uart_irq(USART2, &con_rx, &con_tx); }

static size_t uart_write(USART_TypeDef *u, ring_t *tx, const uint8_t *p, size_t n)
{
    size_t i = 0;
    for (; i < n; i++)
        if (!ring_put(tx, p[i]))
            break;
    LL_USART_EnableIT_TXE_TXFNF(u);
    return i;
}

int hw_link_getc(void) { return ring_get(&link_rx); }
size_t hw_link_write(const uint8_t *p, size_t n) { return uart_write(USART1, &link_tx, p, n); }
int hw_con_getc(void) { return ring_get(&con_rx); }
size_t hw_con_write(const uint8_t *p, size_t n) { return uart_write(USART2, &con_tx, p, n); }
