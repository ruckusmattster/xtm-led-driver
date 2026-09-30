#include "fade.h"
#include "config.h"
#include <math.h>

void fade_init(fade_t *f, float b)
{
    f->b = f->from = f->to = b;
    f->t = f->dur = 0;
    f->tick_hz = TICK_HZ;
    f->active = 0;
}

void fade_start(fade_t *f, float to, float dur_s)
{
    f->from = f->b;
    f->to = to;
    f->t = 0;
    float ticks = dur_s * (float)f->tick_hz;
    f->dur = ticks >= 4.0e9f ? 4000000000u : (uint32_t)lroundf(ticks);
    if (f->dur == 0 || to == f->b) {
        f->b = to;
        f->active = 0;
    } else {
        f->active = 1;
    }
}

static float pos(const fade_t *f, uint32_t t)
{
    if (t >= f->dur)
        return f->to;
    return f->from + (f->to - f->from) * ((float)t / (float)f->dur);
}

float fade_step(fade_t *f)
{
    if (!f->active)
        return f->b;
    f->t++;
    f->b = pos(f, f->t);
    if (f->t >= f->dur)
        f->active = 0;
    return f->b;
}

float fade_ahead(const fade_t *f, float dt_s)
{
    if (!f->active)
        return f->b;
    uint32_t ahead = (uint32_t)(dt_s * (float)f->tick_hz);
    return pos(f, f->t + ahead);
}

float fade_rate(const fade_t *f)
{
    if (!f->active || f->dur == 0)
        return 0.0f;
    return (f->to - f->from) * (float)f->tick_hz / (float)f->dur;
}
