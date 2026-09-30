#include "settings.h"
#include "control.h"
#include "curve.h"
#include "link_protocol.h"

static const char *const NAMES[PARAM_COUNT] = {
    "fallback_b", "tail_end_a", "lux_i0", "lux_v0", "lux_i1", "lux_v1", "lux_ref",
    "headroom_hi", "headroom_lo", "i_max", "link_timeout_s", "vf_corr", "lux_at_max",
};

const char *settings_name(uint8_t id)
{
    return id < PARAM_COUNT ? NAMES[id] : "?";
}

static int in(float v, float lo, float hi) { return v >= lo && v <= hi; }

int settings_set(params_t *p, uint8_t id, float v)
{
    switch (id) {
    case PARAM_FALLBACK_B:
        if (!in(v, 0.0f, 1.0f)) return -2;
        p->fallback_b = v;
        break;
    case PARAM_TAIL_END_A:
        if (!in(v, 0.5e-6f, 100e-6f)) return -2;
        p->i_tail_end = v;
        break;
    case PARAM_LUX_I0:
    case PARAM_LUX_I1:
        if (!in(v, 0.0f, 1.5f)) return -2;
        p->lux_i[id == PARAM_LUX_I1] = v;
        break;
    case PARAM_LUX_V0:
    case PARAM_LUX_V1:
        if (!in(v, 0.0f, 1e7f)) return -2;
        p->lux_v[id == PARAM_LUX_V1] = v;
        break;
    case PARAM_LUX_REF:
        if (!in(v, 0.0f, 1e7f)) return -2;
        p->lux_ref = v;
        break;
    case PARAM_HEADROOM_HI:
        if (!in(v, 0.5f, 2.0f)) return -2;
        p->h_hi = v;
        break;
    case PARAM_HEADROOM_LO:
        if (!in(v, 0.4f, 2.0f)) return -2;
        p->h_lo = v;
        break;
    case PARAM_I_MAX:
        if (!in(v, 0.1f, 1.4f)) return -2;
        p->i_max = v;
        break;
    case PARAM_LINK_TIMEOUT_S:
        if (!in(v, 0.5f, 30.0f)) return -2;
        p->link_timeout_s = v;
        break;
    default:
        return -1;
    }
    return 0;
}

int settings_get(const params_t *p, uint8_t id, float *v)
{
    switch (id) {
    case PARAM_FALLBACK_B: *v = p->fallback_b; break;
    case PARAM_TAIL_END_A: *v = p->i_tail_end; break;
    case PARAM_LUX_I0: *v = p->lux_i[0]; break;
    case PARAM_LUX_V0: *v = p->lux_v[0]; break;
    case PARAM_LUX_I1: *v = p->lux_i[1]; break;
    case PARAM_LUX_V1: *v = p->lux_v[1]; break;
    case PARAM_LUX_REF: *v = p->lux_ref; break;
    case PARAM_HEADROOM_HI: *v = p->h_hi; break;
    case PARAM_HEADROOM_LO: *v = p->h_lo; break;
    case PARAM_I_MAX: *v = p->i_max; break;
    case PARAM_LINK_TIMEOUT_S: *v = p->link_timeout_s; break;
    case PARAM_VF_CORR: *v = led_corr_mean(control_led()); break;
    case PARAM_LUX_AT_MAX: *v = curve_lux_at(control_curve(), control_curve()->i_max); break;
    default:
        return -1;
    }
    return 0;
}
