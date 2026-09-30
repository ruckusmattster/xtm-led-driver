/*
 * LED forward-voltage model and the V_out it needs.
 *
 * V_f(I) = vf0 + nnvt * ln(I / 1.4 A) + rs * (I - 1.4 A) + corr(ln I)
 * corr is a table learned in operation from the cathode (headroom) reading, so the
 * feed-forward V_out becomes right for this module, at each current, over time.
 * V_out target = V_f(I) + headroom(I).
 */
#ifndef LEDMODEL_H
#define LEDMODEL_H

#define LED_NBINS 12

typedef struct {
    float vf0, nnvt, rs;
    float h_hi, h_lo;             /* headroom at >= 100 mA and <= 50 mA */
    float corr[LED_NBINS];        /* learned correction, volts */
} ledmodel_t;

void led_defaults(ledmodel_t *m);
float led_headroom(const ledmodel_t *m, float i);
float led_vf(const ledmodel_t *m, float i);
float led_vout_target(const ledmodel_t *m, float i);
/* largest current whose V_out target is <= vout (bisection in log I); 0 if none */
float led_current_allowed(const ledmodel_t *m, float vout);
/* nudge the correction at current i by dv (spread over the two nearest bins) */
void led_learn(ledmodel_t *m, float i, float dv);
float led_corr_mean(const ledmodel_t *m);

#endif
