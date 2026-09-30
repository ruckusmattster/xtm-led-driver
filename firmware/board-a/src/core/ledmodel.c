#include "ledmodel.h"
#include "config.h"
#include <math.h>

#define LN_I_LO (-13.815511f)   /* ln(1e-6) */
#define LN_I_HI (0.405465f)     /* ln(1.5) */
#define LED_CORR_LIMIT 8.0f     /* volts either way */

void led_defaults(ledmodel_t *m)
{
    m->vf0 = VF0_DEFAULT_V;
    m->nnvt = VF_NNVT_V;
    m->rs = VF_RS_OHM;
    m->h_hi = HEADROOM_HI_V;
    m->h_lo = HEADROOM_LO_V;
    for (int b = 0; b < LED_NBINS; b++)
        m->corr[b] = 0.0f;
}

float led_headroom(const ledmodel_t *m, float i)
{
    if (i <= 0.05f)
        return m->h_lo;
    if (i >= 0.10f)
        return m->h_hi;
    return m->h_lo + (m->h_hi - m->h_lo) * (i - 0.05f) / 0.05f;
}

static void bin_of(float i, int *b0, float *w)
{
    if (i < 1e-9f)
        i = 1e-9f;
    float x = (logf(i) - LN_I_LO) / ((LN_I_HI - LN_I_LO) / (float)(LED_NBINS - 1));
    if (x <= 0.0f) {
        *b0 = 0;
        *w = 0.0f;
    } else if (x >= (float)(LED_NBINS - 1)) {
        *b0 = LED_NBINS - 2;
        *w = 1.0f;
    } else {
        *b0 = (int)x;
        *w = x - (float)*b0;
    }
}

static float corr_at(const ledmodel_t *m, float i)
{
    int b;
    float w;
    bin_of(i, &b, &w);
    return m->corr[b] * (1.0f - w) + m->corr[b + 1] * w;
}

float led_vf(const ledmodel_t *m, float i)
{
    if (i < 1e-9f)
        i = 1e-9f;
    return m->vf0 + m->nnvt * logf(i / VF_REF_I_A) + m->rs * (i - VF_REF_I_A) + corr_at(m, i);
}

float led_vout_target(const ledmodel_t *m, float i)
{
    return led_vf(m, i) + led_headroom(m, i);
}

float led_current_allowed(const ledmodel_t *m, float vout)
{
    float lo = logf(1e-8f), hi = logf(I_ABS_MAX_A);
    if (led_vout_target(m, expf(hi)) <= vout)
        return I_ABS_MAX_A;
    if (led_vout_target(m, expf(lo)) > vout)
        return 0.0f;
    for (int n = 0; n < 24; n++) {
        float mid = 0.5f * (lo + hi);
        if (led_vout_target(m, expf(mid)) <= vout)
            lo = mid;
        else
            hi = mid;
    }
    return expf(lo);
}

void led_learn(ledmodel_t *m, float i, float dv)
{
    int b;
    float w;
    bin_of(i, &b, &w);
    m->corr[b] += dv * (1.0f - w);
    m->corr[b + 1] += dv * w;
    for (int k = b; k <= b + 1; k++) {
        if (m->corr[k] > LED_CORR_LIMIT)
            m->corr[k] = LED_CORR_LIMIT;
        if (m->corr[k] < -LED_CORR_LIMIT)
            m->corr[k] = -LED_CORR_LIMIT;
    }
}

float led_corr_mean(const ledmodel_t *m)
{
    float s = 0.0f;
    for (int b = 0; b < LED_NBINS; b++)
        s += m->corr[b];
    return s / (float)LED_NBINS;
}
