/*
 * The driver's controller: level commands in, sink DAC codes and V_out out.
 *
 * control_tick() runs at 4 kHz from TIM6 and owns the sinks, the buck DAC and the
 * comparator threshold. The main loop talks to it through a one-slot mailbox
 * (commands) and a few flags (faults, derating), and runs the slow loops in
 * control_background() at 1 kHz: headroom learning, fault monitors, retries and
 * the blink sequences.
 */
#ifndef CONTROL_H
#define CONTROL_H

#include <stdint.h>
#include "channels.h"
#include "curve.h"
#include "hw.h"
#include "ledmodel.h"
#include "link_protocol.h"
#include "params.h"

typedef enum { CTL_BOOT, CTL_OFF, CTL_STARTING, CTL_ON, CTL_TAIL, CTL_FAULT, CTL_RAW } ctl_state_t;

void control_init(params_t *p);                /* after the hardware is up; buck running at its floor */
void control_apply_params(void);               /* re-read calibration and settings from *p */

/* commands (main loop context) */
void control_level(uint16_t level, uint32_t fade_ms);
void control_raw(int ch, uint16_t code);       /* calibration: channel ch (0..3) alone at code; ch < 0: all off, V_out up */
void control_raw_exit(void);
void control_identify(int blinks);
void control_link_lost(void);                  /* blink twice, then settle at the fallback level or below */
void control_clear_fault(void);
void control_force_fault(uint8_t fault);        /* e.g. the DAC80504 failed its start-up check */

/* main loop, every millisecond */
void control_background(void);

/* state for status and the console */
ctl_state_t control_state(void);
uint8_t control_fault(void);
uint16_t control_level_target(void);
uint16_t control_level_now(void);
float control_current(void);                   /* A, applied */
void control_codes(uint16_t out[NCH]);
const analog_t *control_analog(void);
float control_temp(int i);                     /* degrees C */
void control_status(msg_status_t *s);
channels_t *control_channels(void);
ledmodel_t *control_led(void);
curve_t *control_curve(void);
int control_save_pending(void);
void control_request_save(void);               /* write params when the light is off or low */
uint32_t control_dac_errors(void);

#endif
