/*
 * Fade engine: moves the curve position b linearly in time (a constant rate in
 * log current), from where it is to a target, over a duration. Time is counted in
 * whole ticks so a ten-minute fade lands exactly on time (float seconds would not).
 */
#ifndef FADE_H
#define FADE_H

#include <stdint.h>

typedef struct {
    float b;              /* present position, 0..1 */
    float from, to;       /* endpoints */
    uint32_t t, dur;      /* elapsed and total ticks */
    uint32_t tick_hz;
    int active;
} fade_t;

void fade_init(fade_t *f, float b);                   /* uses TICK_HZ */
void fade_start(fade_t *f, float to, float dur_s);
float fade_step(fade_t *f);                           /* advance one tick, return b */
float fade_ahead(const fade_t *f, float dt_s);        /* b dt_s from now, without advancing */
float fade_rate(const fade_t *f);                     /* db/dt (per second) of the running fade, 0 if idle */

#endif
