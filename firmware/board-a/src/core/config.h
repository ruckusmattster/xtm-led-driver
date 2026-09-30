/*
 * Board A constants and tunables. Every value here traces to the Phase 2 design (docs/design-record/),
 * section "Circuit design", or to design/calc.py.
 */
#ifndef CONFIG_H
#define CONFIG_H

#define FW_VERSION_MAJOR 1
#define FW_VERSION_MINOR 0
#define FW_VERSION ((FW_VERSION_MAJOR << 8) | FW_VERSION_MINOR)

/* ---------------------------------------------------------------- LED */
#define I_MAX_A              1.40f     /* XTM rated current */
#define I_ABS_MAX_A          1.50f     /* never commanded above this */
#define I_TAIL_END_DEFAULT_A 5e-6f     /* bottom of the curve; adjustable (param) */
#define VF_REF_I_A           1.40f
#define VF0_DEFAULT_V        29.9f     /* typical V_f at 1.4 A, datasheet */
#define VF_NNVT_V            0.65f     /* low-current slope, ~10 dies */
#define VF_RS_OHM            1.48f     /* series resistance fitted to 27.9 V @ 0.5 A, 29.9 V @ 1.4 A */

/* ---------------------------------------------------------------- channels */
#define NCH 4                          /* index 0..3 = ch1..ch4 */
#define DAC_VREF_V      2.5f
#define DIV_RATIO       (1.0f / 13.0f) /* 12.0k / 1.00k */
#define SENSE_LSB_V     (DAC_VREF_V * DIV_RATIO / 65536.0f)
#define ZB_SRC_V        (5.0f / 11.0f) /* BIAS node */
#define ZB_R_OHM        1.82e6f
#define RIN_OHM         1000.0f
#define E_KA_V          25e-6f         /* keep-alive: sense volts above the dead-zone edge */

/* shunts, ch1..ch4 */
#define RS_CH1 0.1f
#define RS_CH2 1.0f
#define RS_CH3 10.0f
#define RS_CH4 100.0f

/* blend bands between adjacent channels: band 0 = ch4->ch3, 1 = ch3->ch2, 2 = ch2->ch1 */
#define BAND_LO_0 1.4e-3f
#define BAND_HI_0 1.6e-3f
#define BAND_LO_1 14e-3f
#define BAND_HI_1 16e-3f
#define BAND_LO_2 140e-3f
#define BAND_HI_2 160e-3f
#define ARM_FRACTION    0.5f           /* arm the next channel up at this fraction of its band bottom */
#define DISARM_FRACTION 0.25f
#define ARM_LOOKAHEAD_S 0.4f           /* arm early when a fade will reach the band within this time */

/* ---------------------------------------------------------------- fades */
#define TICK_HZ         4000u          /* fade engine and DAC update rate */
#define LEVEL_MAX       65535u         /* link level 1..65535 maps onto the curve, 0 = off */

/* ---------------------------------------------------------------- tracking buck */
#define BUCK_V0         40.44f         /* V_out = BUCK_V0 - BUCK_K * V_dac (200k / 7.32k / 2 x 8.25k) */
#define BUCK_K          12.12f
#define VDAC_MIN_V      0.20f          /* buffered DAC limits */
#define VDAC_MAX_V      3.10f
#define VOUT_FLOOR_V    3.5f           /* blackout floor */
#define VOUT_MAX_V      38.0f          /* highest commanded V_out */
#define VOUT_TAU_S      0.00025f       /* V_out response to a DAC step, used to pace current rises */
#define HEADROOM_HI_V   1.0f           /* at >= 100 mA */
#define HEADROOM_LO_V   0.7f           /* at <= 50 mA */
#define HEADROOM_MIN_V  0.45f          /* below this the sink can't hold its current */
#define VOUT_SENSE_GAIN ((1000e3f + 82e3f) / 82e3f)
#define V48_SENSE_GAIN  ((100e3f + 6.2e3f) / 6.2e3f)
#define V48_ON_V        42.0f
#define V48_UV_V        40.0f
#define TAIL_DROP_V     9.0f           /* voltage-mode tail: ~6 decades below the tail end */

/* ---------------------------------------------------------------- protection */
#define SHORT_VF_MIN_V      15.0f      /* V_out - V_cath below this with current flowing = shorted LED */
#define CATH_TRIP_MARGIN_V  1.2f       /* comparator threshold above the headroom target */
#define CATH_TRIP_MAX_V     3.0f
#define OPEN_VCATH_V        0.15f
#define NTC_B               3380.0f
#define NTC_R25             10000.0f
#define NTC_RPULL           10000.0f

/* per-NTC derate start / trip, degrees C: FET, main buck, aux rails, precision section */
#define NTC_DERATE { 95.0f, 90.0f, 90.0f, 75.0f }
#define NTC_TRIP   { 110.0f, 105.0f, 105.0f, 90.0f }

/* ---------------------------------------------------------------- link */
#define LINK_TIMEOUT_MS     1500u
#define LINK_STATUS_MS      100u
#define LINK_HOLD_MAX_S     120u
#define FALLBACK_B_DEFAULT  0.20f      /* link loss: 20 % of the encoder's scale */

#endif
