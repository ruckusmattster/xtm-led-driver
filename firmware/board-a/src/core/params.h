/* Persistent settings and calibration, stored in the last flash page with a CRC. */
#ifndef PARAMS_H
#define PARAMS_H

#include <stdint.h>
#include "channels.h"
#include "ledmodel.h"

#define PARAMS_MAGIC   0x31544D58u    /* "XTM1" */
#define PARAMS_VERSION 1u

typedef struct {
    uint32_t magic;
    uint16_t version;
    uint16_t size;
    chcal_t cal[NCH];
    uint32_t calibrated;              /* bit k: channel k has measured points */
    float i_tail_end;                 /* A */
    float i_max;                      /* A */
    float fallback_b;                 /* 0..1 */
    float lux_i[2], lux_v[2], lux_ref;
    float h_hi, h_lo;
    float link_timeout_s;
    float vf_corr[LED_NBINS];
    float dark_a;                     /* measured cathode-node leakage with every sink off (info) */
    uint32_t reserved[4];
    uint32_t crc;                     /* CRC-32 of everything above */
} params_t;

void params_defaults(params_t *p);
uint32_t params_crc(const params_t *p);
int params_valid(const params_t *p);
void params_seal(params_t *p);        /* set magic/version/size/crc */

#endif
