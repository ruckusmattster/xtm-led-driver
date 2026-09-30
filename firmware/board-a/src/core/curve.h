/*
 * Brightness curve: link level (0 = off, 1..65535) <-> position b (0..1) <-> LED current.
 *
 * Current matching (default): I = i_min * (i_max / i_min)^b, a constant ratio per step.
 * Light matching (after a two-point lux calibration and a fleet reference):
 * the fixture solves eta(I) * I = lux_ref * phi(b), where phi follows the same
 * curve shape normalised to 1 at b = 1, and eta(I) = lux / I is interpolated in
 * log(I) between the two measured points (held flat outside them).
 */
#ifndef CURVE_H
#define CURVE_H

#include <stdint.h>

typedef struct {
    float i_min;      /* A at b = 0 (the tail end) */
    float i_max;      /* A at b = 1 */
    /* light matching */
    float lux_i[2];   /* A at the two measured points, lux_i[0] < lux_i[1] */
    float lux_v[2];   /* lux measured at those currents */
    float lux_ref;    /* fleet reference lux at b = 1; 0 disables light matching */
} curve_t;

void curve_defaults(curve_t *c);
int curve_lux_enabled(const curve_t *c);

/* level 0 -> -1 (off); 1..65535 -> 0..1 */
float curve_b_from_level(uint16_t level);
uint16_t curve_level_from_b(float b);

float curve_current(const curve_t *c, float b);
float curve_b_from_current(const curve_t *c, float i);

/* fixture's own light output estimate at current i (lux at the calibration distance), 0 if uncalibrated */
float curve_lux_at(const curve_t *c, float i);

#endif
