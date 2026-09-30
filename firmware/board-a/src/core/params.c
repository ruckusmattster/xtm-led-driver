#include "params.h"
#include "config.h"
#include <stddef.h>
#include <string.h>

static uint32_t crc32(const uint8_t *p, size_t n)
{
    uint32_t crc = 0xFFFFFFFFu;
    while (n--) {
        crc ^= *p++;
        for (int i = 0; i < 8; i++)
            crc = (crc & 1u) ? (crc >> 1) ^ 0xEDB88320u : (crc >> 1);
    }
    return ~crc;
}

void params_defaults(params_t *p)
{
    channels_t ch;
    memset(p, 0, sizeof(*p));
    channels_nominal(&ch);
    memcpy(p->cal, ch.cal, sizeof(p->cal));
    p->calibrated = 0;
    p->i_tail_end = I_TAIL_END_DEFAULT_A;
    p->i_max = I_MAX_A;
    p->fallback_b = FALLBACK_B_DEFAULT;
    p->h_hi = HEADROOM_HI_V;
    p->h_lo = HEADROOM_LO_V;
    p->link_timeout_s = LINK_TIMEOUT_MS / 1000.0f;
    params_seal(p);
}

uint32_t params_crc(const params_t *p)
{
    return crc32((const uint8_t *)p, offsetof(params_t, crc));
}

int params_valid(const params_t *p)
{
    return p->magic == PARAMS_MAGIC && p->version == PARAMS_VERSION && p->size == sizeof(params_t) &&
           p->crc == params_crc(p);
}

void params_seal(params_t *p)
{
    p->magic = PARAMS_MAGIC;
    p->version = PARAMS_VERSION;
    p->size = sizeof(params_t);
    p->crc = params_crc(p);
}
