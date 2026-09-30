#include "channels.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

const float CH_RS[NCH] = { RS_CH1, RS_CH2, RS_CH3, RS_CH4 };
const float BAND_LO[NCH - 1] = { BAND_LO_0, BAND_LO_1, BAND_LO_2 };
const float BAND_HI[NCH - 1] = { BAND_HI_0, BAND_HI_1, BAND_HI_2 };

/* band j sits between low channel 3-j and high channel 2-j */
#define BAND_LOW_CH(j)  (3 - (j))
#define BAND_HIGH_CH(j) (2 - (j))

static float q_of(int k) { return (RIN_OHM / CH_RS[k] + 1.0f) / ZB_R_OHM; }

float channel_nominal_amps(int k, uint16_t code)
{
    float v = (float)code * SENSE_LSB_V;
    float i = v * (1.0f / CH_RS[k] + q_of(k)) - ZB_SRC_V * q_of(k);
    return i > 0.0f ? i : 0.0f;
}

float channel_nominal_code(int k, float amps)
{
    float v = (amps + ZB_SRC_V * q_of(k)) / (1.0f / CH_RS[k] + q_of(k));
    return v / SENSE_LSB_V;
}

void channel_cal_reset(channels_t *ch, int k)
{
    chcal_t *c = &ch->cal[k];
    memset(c, 0, sizeof(*c));
    /* nominal points at 14 mV and 150 mV of sense */
    float codes[2] = { 0.014f / SENSE_LSB_V, 0.150f / SENSE_LSB_V };
    for (int i = 0; i < 2; i++) {
        c->code[i] = (uint16_t)lroundf(codes[i]);
        c->amps[i] = channel_nominal_amps(k, c->code[i]);
    }
    c->n = 2;
}

void channels_nominal(channels_t *ch)
{
    memset(ch, 0, sizeof(*ch));
    for (int k = 0; k < NCH; k++)
        channel_cal_reset(ch, k);
    channels_update_ka(ch);
}

static float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }

uint16_t channel_code(const channels_t *ch, int k, float amps)
{
    const chcal_t *c = &ch->cal[k];
    if (amps <= 0.0f || c->n < 2)
        return 0;
    int i = 0;
    while (i < c->n - 2 && amps > c->amps[i + 1])
        i++;
    float x0 = c->code[i], x1 = c->code[i + 1], y0 = c->amps[i], y1 = c->amps[i + 1];
    float x = x0 + (amps - y0) * (x1 - x0) / (y1 - y0);
    return (uint16_t)clampf(roundf(x), 0.0f, 65535.0f);
}

float channel_amps(const channels_t *ch, int k, uint16_t code)
{
    const chcal_t *c = &ch->cal[k];
    if (c->n < 2)
        return 0.0f;
    int i = 0;
    while (i < c->n - 2 && code > c->code[i + 1])
        i++;
    float x0 = c->code[i], x1 = c->code[i + 1], y0 = c->amps[i], y1 = c->amps[i + 1];
    float y = y0 + ((float)code - x0) * (y1 - y0) / (x1 - x0);
    return y > 0.0f ? y : 0.0f;
}

/* dead-zone edge from the two highest points, plus E_KA of sense */
static uint16_t ka_code_of(const chcal_t *c)
{
    if (c->n < 2)
        return 0;
    int i = c->n - 2;
    float x0 = c->code[i], x1 = c->code[i + 1], y0 = c->amps[i], y1 = c->amps[i + 1];
    float z = x0 - y0 * (x1 - x0) / (y1 - y0);
    float kc = z + E_KA_V / SENSE_LSB_V;
    return (uint16_t)clampf(roundf(kc), 1.0f, 65535.0f);
}

uint16_t channel_ka_code(const channels_t *ch, int k)
{
    const chcal_t *c = &ch->cal[k];
    /* a calibration point below the lowest range point is the measured keep-alive: use its code */
    if (c->n >= 3 && c->code[0] < c->code[c->n - 2] / 8)
        return c->code[0];
    return ka_code_of(c);
}

void channels_update_ka(channels_t *ch)
{
    for (int k = 0; k < NCH; k++)
        ch->ka[k] = channel_amps(ch, k, channel_ka_code(ch, k));
}

int channel_cal_point(channels_t *ch, int k, uint16_t code, float amps)
{
    chcal_t *c = &ch->cal[k];
    chcal_t t = *c;
    int j;
    for (j = 0; j < t.n; j++) {
        if (abs((int)t.code[j] - (int)code) <= 64) {
            t.code[j] = code;
            t.amps[j] = amps;
            break;
        }
    }
    if (j == t.n) {
        if (t.n >= CH_MAX_PTS)
            return -1;
        t.code[t.n] = code;
        t.amps[t.n] = amps;
        t.n++;
    }
    /* sort by code */
    for (int a = 1; a < t.n; a++)
        for (int b = a; b > 0 && t.code[b] < t.code[b - 1]; b--) {
            uint16_t tc = t.code[b]; t.code[b] = t.code[b - 1]; t.code[b - 1] = tc;
            float ta = t.amps[b]; t.amps[b] = t.amps[b - 1]; t.amps[b - 1] = ta;
        }
    /* must be strictly increasing in both code and amps */
    for (int a = 1; a < t.n; a++)
        if (!(t.code[a] > t.code[a - 1]) || !(t.amps[a] > t.amps[a - 1]))
            return -2;
    *c = t;
    channels_update_ka(ch);
    return 0;
}

static void blend(const channels_t *ch, int j, float i, float s[NCH])
{
    int L = BAND_LOW_CH(j), H = BAND_HIGH_CH(j);
    float lo = BAND_LO[j], hi = BAND_HI[j];
    float kH = ch->ka[H], kL = ch->ka[L];
    float u = logf(i / lo) / logf(hi / lo);
    float r0 = logf(kH / (lo - kH));
    float r1 = logf((hi - kL) / kL);
    float r = expf(r0 + (r1 - r0) * u);
    s[H] = i * r / (1.0f + r);
    s[L] = i / (1.0f + r);
}

void channels_split(const channels_t *ch, float i, float s[NCH])
{
    for (int k = 0; k < NCH; k++)
        s[k] = 0.0f;
    if (i <= 0.0f)
        return;
    if (i <= BAND_LO[0])
        s[3] = i;
    else if (i < BAND_HI[0])
        blend(ch, 0, i, s);
    else if (i <= BAND_LO[1])
        s[2] = i;
    else if (i < BAND_HI[1])
        blend(ch, 1, i, s);
    else if (i <= BAND_LO[2])
        s[1] = i;
    else if (i < BAND_HI[2])
        blend(ch, 2, i, s);
    else
        s[0] = i;

    /* keep-alives for armed channels not already carrying at least that much */
    float add = 0.0f;
    uint8_t fixed[NCH] = { 0 };
    for (int k = 0; k < NCH; k++) {
        if (ch->armed[k] && s[k] < ch->ka[k]) {
            add += ch->ka[k] - s[k];
            s[k] = ch->ka[k];
            fixed[k] = 1;
        }
    }
    if (add > 0.0f) {
        int m = -1;
        for (int k = 0; k < NCH; k++)
            if (!fixed[k] && (m < 0 || s[k] > s[m]))
                m = k;
        if (m >= 0) {
            s[m] -= add;
            if (s[m] < 0.0f)
                s[m] = 0.0f;   /* level below the keep-alives: they win (only at arming edges) */
        }
    }
}

void channels_arm(channels_t *ch, float i_now, float i_ahead)
{
    ch->armed[3] = 1;                               /* ch4 whenever the light is on */
    for (int j = 0; j < NCH - 1; j++) {
        int H = BAND_HIGH_CH(j);
        float on = BAND_LO[j] * ARM_FRACTION, off = BAND_LO[j] * DISARM_FRACTION;
        if (i_now >= on || i_ahead >= BAND_LO[j])
            ch->armed[H] = 1;
        else if (i_now < off && i_ahead < off)
            ch->armed[H] = 0;
    }
}

void channels_disarm_all(channels_t *ch)
{
    for (int k = 0; k < NCH; k++)
        ch->armed[k] = 0;
}
