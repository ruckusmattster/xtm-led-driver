#include "curve.h"
#include "config.h"
#include <math.h>

static float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }

void curve_defaults(curve_t *c)
{
    c->i_min = I_TAIL_END_DEFAULT_A;
    c->i_max = I_MAX_A;
    c->lux_i[0] = c->lux_i[1] = 0.0f;
    c->lux_v[0] = c->lux_v[1] = 0.0f;
    c->lux_ref = 0.0f;
}

int curve_lux_enabled(const curve_t *c)
{
    return c->lux_ref > 0.0f && c->lux_i[0] > 0.0f && c->lux_i[1] > c->lux_i[0] * 1.5f &&
           c->lux_v[0] > 0.0f && c->lux_v[1] > c->lux_v[0];
}

float curve_b_from_level(uint16_t level)
{
    if (level == 0)
        return -1.0f;
    return (float)(level - 1u) / (float)(LEVEL_MAX - 1u);
}

uint16_t curve_level_from_b(float b)
{
    if (b < 0.0f)
        return 0;
    b = clampf(b, 0.0f, 1.0f);
    return (uint16_t)(1u + (uint32_t)lroundf(b * (float)(LEVEL_MAX - 1u)));
}

/* efficacy (lux per amp) interpolated in log(I) between the two points, flat outside */
static float eta_at(const curve_t *c, float i)
{
    float e0 = c->lux_v[0] / c->lux_i[0];
    float e1 = c->lux_v[1] / c->lux_i[1];
    float u = (logf(i) - logf(c->lux_i[0])) / (logf(c->lux_i[1]) - logf(c->lux_i[0]));
    u = clampf(u, 0.0f, 1.0f);
    return expf(logf(e0) + (logf(e1) - logf(e0)) * u);
}

float curve_lux_at(const curve_t *c, float i)
{
    if (!(c->lux_i[0] > 0.0f && c->lux_i[1] > c->lux_i[0] && c->lux_v[0] > 0.0f && c->lux_v[1] > 0.0f) || i <= 0.0f)
        return 0.0f;
    return eta_at(c, i) * i;
}

float curve_current(const curve_t *c, float b)
{
    if (b < 0.0f)
        return 0.0f;
    b = clampf(b, 0.0f, 1.0f);
    float ratio = c->i_max / c->i_min;
    float phi = powf(ratio, b) / ratio;            /* 1/ratio .. 1 */
    if (!curve_lux_enabled(c))
        return c->i_max * phi;
    float target = c->lux_ref * phi;
    float i = c->i_max * phi;                       /* start from current matching */
    for (int n = 0; n < 6; n++) {
        float next = target / eta_at(c, i);
        i = clampf(next, c->i_min * 0.1f, c->i_max);
    }
    return i;
}

float curve_b_from_current(const curve_t *c, float i)
{
    if (i <= 0.0f)
        return -1.0f;
    float ratio = c->i_max / c->i_min;
    float phi;
    if (curve_lux_enabled(c))
        phi = eta_at(c, i) * i / c->lux_ref;
    else
        phi = i / c->i_max;
    if (phi <= 0.0f)
        return 0.0f;
    return clampf(logf(phi * ratio) / logf(ratio), 0.0f, 1.0f);
}
