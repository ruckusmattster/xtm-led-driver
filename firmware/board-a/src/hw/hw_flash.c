/* Parameter storage in the last 2 KB page of the 128 KB flash (page 63, reserved by the linker script). */
#include "hw.h"
#include "stm32g4xx.h"
#include <string.h>

#define PARAM_PAGE      63u
#define PARAM_ADDR      (FLASH_BASE + PARAM_PAGE * 2048u)
#define PARAM_PAGE_SIZE 2048u
#define FLASH_ERRORS (FLASH_SR_OPERR | FLASH_SR_PROGERR | FLASH_SR_WRPERR | FLASH_SR_PGAERR | FLASH_SR_SIZERR | \
                      FLASH_SR_PGSERR | FLASH_SR_MISERR | FLASH_SR_FASTERR | FLASH_SR_RDERR | FLASH_SR_OPTVERR)

int hw_flash_load(void *dst, size_t n)
{
    if (n > PARAM_PAGE_SIZE)
        return -1;
    memcpy(dst, (const void *)PARAM_ADDR, n);
    return 0;
}

static int wait_ready(void)
{
    while (FLASH->SR & FLASH_SR_BSY) {
    }
    if (FLASH->SR & FLASH_ERRORS) {
        FLASH->SR = FLASH_ERRORS;
        return -1;
    }
    FLASH->SR = FLASH_SR_EOP;
    return 0;
}

int hw_flash_store(const void *src, size_t n)
{
    if (n > PARAM_PAGE_SIZE)
        return -1;
    int err = 0;
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    if (FLASH->CR & FLASH_CR_LOCK) {
        FLASH->KEYR = 0x45670123u;
        FLASH->KEYR = 0xCDEF89ABu;
    }
    FLASH->SR = FLASH_ERRORS | FLASH_SR_EOP;
    /* erase */
    FLASH->CR = (FLASH->CR & ~(FLASH_CR_PNB | FLASH_CR_PG)) | (PARAM_PAGE << FLASH_CR_PNB_Pos) | FLASH_CR_PER;
    FLASH->CR |= FLASH_CR_STRT;
    err |= wait_ready();
    FLASH->CR &= ~FLASH_CR_PER;
    /* program 64-bit double words */
    const uint8_t *s = (const uint8_t *)src;
    FLASH->CR |= FLASH_CR_PG;
    for (size_t off = 0; off < n && !err; off += 8) {
        uint32_t w[2] = { 0xFFFFFFFFu, 0xFFFFFFFFu };
        memcpy(w, s + off, (n - off) >= 8 ? 8 : (n - off));
        *(volatile uint32_t *)(PARAM_ADDR + off) = w[0];
        __ISB();
        *(volatile uint32_t *)(PARAM_ADDR + off + 4u) = w[1];
        err |= wait_ready();
    }
    FLASH->CR &= ~FLASH_CR_PG;
    FLASH->CR |= FLASH_CR_LOCK;
    /* flush the data cache so reads see the new contents */
    FLASH->ACR &= ~FLASH_ACR_DCEN;
    FLASH->ACR |= FLASH_ACR_DCRST;
    FLASH->ACR &= ~FLASH_ACR_DCRST;
    FLASH->ACR |= FLASH_ACR_DCEN;
    if (!primask)
        __enable_irq();
    if (!err && memcmp((const void *)PARAM_ADDR, src, n) != 0)
        err = -2;
    return err;
}
