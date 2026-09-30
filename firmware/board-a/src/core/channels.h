/*
 * Sink channels: calibration model, blend of the total current across channels,
 * keep-alive arming.  Index 0..3 = ch1 (0.1 ohm) .. ch4 (100 ohm).
 *
 * Calibration: each channel keeps up to CH_MAX_PTS points (DAC code, measured amps),
 * sorted by code, and interpolates piecewise-linearly between them, extrapolating the
 * end segments.  The nominal model supplies two points from component values; the
 * calibration procedure replaces them with measured points (two per range plus the
 * keep-alive point on ch1-ch3).
 */
#ifndef CHANNELS_H
#define CHANNELS_H

#include <stdint.h>
#include "config.h"

#define CH_MAX_PTS 4

typedef struct {
    uint8_t n;                     /* number of points */
    uint16_t code[CH_MAX_PTS];
    float amps[CH_MAX_PTS];
} chcal_t;

typedef struct {
    chcal_t cal[NCH];
    float ka[NCH];                 /* keep-alive current actually delivered (A) */
    uint8_t armed[NCH];
} channels_t;

extern const float CH_RS[NCH];
extern const float BAND_LO[NCH - 1];
extern const float BAND_HI[NCH - 1];

void channels_nominal(channels_t *ch);
/* nominal current (A) for a DAC code on channel k, from component values */
float channel_nominal_amps(int k, uint16_t code);
float channel_nominal_code(int k, float amps);

uint16_t channel_code(const channels_t *ch, int k, float amps);   /* amps <= 0 -> 0 (dead zone) */
float channel_amps(const channels_t *ch, int k, uint16_t code);   /* model estimate, >= 0 */
uint16_t channel_ka_code(const channels_t *ch, int k);

/* insert or replace a calibration point (keeps the list sorted; replaces a point within 64 codes) */
int channel_cal_point(channels_t *ch, int k, uint16_t code, float amps);
void channel_cal_reset(channels_t *ch, int k);
/* recompute ka[k] from the calibration (called after calibration changes) */
void channels_update_ka(channels_t *ch);

/* Split total current i across the channels. armed[] says which channels hold a keep-alive.
 * Output shares sum to i (when i exceeds the sum of keep-alives). */
void channels_split(const channels_t *ch, float i, float share[NCH]);

/* Arming with hysteresis. i_now: present total; i_ahead: where the fade will be
 * ARM_LOOKAHEAD_S from now (= i_now when not fading). */
void channels_arm(channels_t *ch, float i_now, float i_ahead);
void channels_disarm_all(channels_t *ch);

#endif
