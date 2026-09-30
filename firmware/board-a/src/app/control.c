#include "control.h"
#include "config.h"
#include "fade.h"
#include <math.h>
#include <string.h>

#define DT                (1.0f / (float)TICK_HZ)
#define TAIL_FRACTION     0.15f
#define TAIL_MIN_S        0.10f
#define TAIL_MAX_S        3.0f
#define PROBE_MAX_A       1e-3f
#define VOUT_SETTLE_TICKS 8u        /* 2 ms for V_out to rise before a sink moves */
#define COMP_MASK_TICKS   12u       /* 3 ms: the cathode tap's RC plus margin */
#define CLAMP_DELAY_TICKS 2u        /* op-amps wind down before the clamps engage */
#define PROBE_TIMEOUT_S   0.25f
#define SAVE_MAX_A        10e-3f

enum { CMD_NONE, CMD_LEVEL, CMD_RAW, CMD_RAW_EXIT, CMD_CLEAR };

typedef struct {
    params_t *p;
    curve_t curve;
    channels_t ch;
    ledmodel_t led;
    analog_t an;
    float temp[4];

    /* mailbox, main loop -> tick */
    volatile uint32_t cmd_seq;
    uint32_t cmd_seen;
    volatile uint8_t cmd_kind;
    volatile uint16_t cmd_level;
    volatile float cmd_fade_s;
    volatile int8_t cmd_ch;
    volatile uint16_t cmd_code;

    /* flags into the tick */
    volatile uint8_t fault_req;
    volatile uint8_t fault_isr;
    volatile float derate;

    /* tick-owned */
    volatile ctl_state_t state;
    volatile uint8_t fault;
    fade_t fade;
    volatile uint16_t level_target;
    float b_target, fade_s;
    int off_after_fade;
    float tail_s, tail_v0;
    volatile float i_applied;
    float i_start, i_probe;
    float vcmd, vmodel;
    uint16_t codes[NCH], written[NCH];
    int force_write;
    uint32_t phase_ticks, pause_ticks;
    int phase;
    int raw_ch;
    uint16_t raw_code, raw_next;
    uint32_t raw_pending;
    uint32_t comp_mask;
    int comp_irq_on;
    int clamps_on;
    uint32_t clamp_delay;
    uint32_t rb_index;
    volatile uint32_t rb_errors;
    uint32_t ticks;
    volatile float b_now;
    float total_last;                   /* modelled total at the last applied codes, for monotonic fades */

    /* background */
    uint32_t last_ms, t_fault_ms, retries, uv_ms, pg_ms, open_ms, short_ms;
    uint32_t rb_seen, rb_window_ms, rb_window_errs;
    uint32_t last_learn_ms;
    int save_pending;
    struct {
        int active, step, blinks;
        uint32_t t_next;
        uint16_t l_orig, l_dim, l_final;
        uint32_t final_ms;
        int from_off;
    } seq;
} ctl_t;

static ctl_t C;
static const float VMODEL_K = 0.6321206f;   /* 1 - exp(-DT / VOUT_TAU_S), DT = tau = 250 us */
static const float NTC_DERATE_C[4] = NTC_DERATE;
static const float NTC_TRIP_C[4] = NTC_TRIP;

static float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }
static void request_fault(uint8_t f);
static float vout_target(float i) { return clampf(led_vout_target(&C.led, i), VOUT_FLOOR_V, VOUT_MAX_V); }

/* ================================================================== tick helpers */

static void codes_zero(void)
{
    for (int k = 0; k < NCH; k++)
        C.codes[k] = 0;
}

static void codes_for(float i)
{
    float s[NCH];
    channels_split(&C.ch, i, s);
    for (int k = 0; k < NCH; k++)
        C.codes[k] = channel_code(&C.ch, k, s[k]);
}

static float codes_total(const uint16_t *codes)
{
    float t = 0.0f;
    for (int k = 0; k < NCH; k++)
        t += channel_amps(&C.ch, k, codes[k]);
    return t;
}

/* Two channels with different step sizes can make the quantised sum dip by one step of the
 * finer channel inside a blend band. Along a fade, refuse any code set that would move the
 * total against the fade's direction: the output is then monotonic step by step. */
static void codes_for_monotonic(float i, float rate)
{
    uint16_t prev[NCH];
    for (int k = 0; k < NCH; k++)
        prev[k] = C.codes[k];
    codes_for(i);
    float t = codes_total(C.codes);
    if ((rate > 0.0f && t < C.total_last) || (rate < 0.0f && t > C.total_last)) {
        for (int k = 0; k < NCH; k++)
            C.codes[k] = prev[k];
        return;
    }
    C.total_last = t;
}

static void clamps(int on)
{
    if (on != C.clamps_on) {
        hw_clamps(on);
        C.clamps_on = on;
    }
}

static void enter_fault(uint8_t f)
{
    C.fault = f;
    C.state = CTL_FAULT;
    codes_zero();
    C.force_write = 1;
    C.vcmd = VOUT_FLOOR_V;
    C.i_applied = 0.0f;
    channels_disarm_all(&C.ch);
    fade_init(&C.fade, 0.0f);
    C.off_after_fade = 0;
    clamps(1);
}

static void go_off_now(void)
{
    codes_zero();
    C.vcmd = VOUT_FLOOR_V;
    C.state = CTL_OFF;
    C.i_applied = 0.0f;
    channels_disarm_all(&C.ch);
    fade_init(&C.fade, 0.0f);
    C.off_after_fade = 0;
    C.clamp_delay = CLAMP_DELAY_TICKS;
}

static float cap_current(float i)
{
    float cap = C.curve.i_max * C.derate;
    if (cap > I_ABS_MAX_A)
        cap = I_ABS_MAX_A;
    return i > cap ? cap : i;
}

static void start_on(float b, float fade_s)
{
    C.b_target = b;
    C.fade_s = fade_s;
    C.i_start = cap_current(curve_current(&C.curve, fade_s > 0.0f ? 0.0f : b));
    C.i_probe = C.i_start < PROBE_MAX_A ? C.i_start : PROBE_MAX_A;
    C.state = CTL_STARTING;
    C.phase = 0;
    C.phase_ticks = 0;
    codes_zero();
    channels_disarm_all(&C.ch);
    C.vcmd = vout_target(C.i_start);
    C.comp_mask = COMP_MASK_TICKS;
}

static float codes_total(const uint16_t *codes);

static void go_on(void)
{
    C.total_last = codes_total(C.codes);
    fade_init(&C.fade, C.fade_s > 0.0f ? 0.0f : C.b_target);
    fade_start(&C.fade, C.b_target, C.fade_s);
    C.off_after_fade = 0;
    C.state = CTL_ON;
    C.comp_mask = COMP_MASK_TICKS;
}

static void handle_cmd(void)
{
    switch (C.cmd_kind) {
    case CMD_LEVEL: {
        uint16_t level = C.cmd_level;
        float t = C.cmd_fade_s;
        float b = curve_b_from_level(level);
        C.level_target = level;
        switch (C.state) {
        case CTL_OFF:
            if (level > 0)
                start_on(b, t);
            break;
        case CTL_STARTING:
            if (level == 0)
                go_off_now();
            else {
                C.b_target = b;
                C.fade_s = t;
            }
            break;
        case CTL_ON:
            if (level == 0) {
                if (t <= 0.0f)
                    go_off_now();
                else {
                    C.tail_s = clampf(t * TAIL_FRACTION, TAIL_MIN_S, TAIL_MAX_S);
                    fade_start(&C.fade, 0.0f, t * (1.0f - TAIL_FRACTION));
                    C.off_after_fade = 1;
                }
            } else {
                fade_start(&C.fade, b, t);
                C.off_after_fade = 0;
            }
            C.total_last = codes_total(C.codes);
            break;
        case CTL_TAIL:
            if (level > 0) {
                /* let the saturated sink unwind before V_out comes back up */
                codes_zero();
                C.b_target = b;
                C.fade_s = t;
                C.state = CTL_STARTING;
                C.phase = -1;
                C.phase_ticks = 0;
                C.pause_ticks = TICK_HZ / 50u;      /* 20 ms */
            }
            break;
        default:
            break;                                   /* FAULT keeps the target; RAW ignores levels */
        }
        break;
    }
    case CMD_RAW:
        if (C.state == CTL_FAULT)
            break;
        if (C.state != CTL_RAW) {
            codes_zero();
            channels_disarm_all(&C.ch);
            fade_init(&C.fade, 0.0f);
            C.state = CTL_RAW;
            C.raw_ch = -1;
            C.raw_code = 0;
            clamps(0);
        }
        C.raw_next = C.cmd_code;
        if (C.cmd_ch != C.raw_ch) {                 /* new channel: zero the old one first */
            codes_zero();
            C.raw_code = 0;
            C.raw_ch = C.cmd_ch;
        }
        C.raw_pending = VOUT_SETTLE_TICKS;          /* V_out first, then the code */
        break;
    case CMD_RAW_EXIT:
        if (C.state == CTL_RAW)
            go_off_now();
        break;
    case CMD_CLEAR:
        if (C.state == CTL_FAULT) {
            C.fault = LFAULT_NONE;
            C.state = CTL_OFF;
        }
        break;
    default:
        break;
    }
}

static void tick_starting(void)
{
    C.phase_ticks++;
    if (C.phase < 0) {                               /* pause after aborting a tail */
        C.vcmd = VOUT_FLOOR_V > C.vcmd ? VOUT_FLOOR_V : C.vcmd;
        if (C.phase_ticks >= C.pause_ticks)
            start_on(C.b_target, C.fade_s);
        return;
    }
    if (C.phase == 0) {                              /* V_out rises with every sink in its dead zone */
        if (C.phase_ticks >= VOUT_SETTLE_TICKS) {
            clamps(0);
            channels_arm(&C.ch, C.i_probe, C.i_probe);
            codes_for(C.i_probe);
            C.i_applied = C.i_probe;
            C.phase = 1;
            C.phase_ticks = 0;
        }
        return;
    }
    /* phase 1: a small probe current pulls the cathode down; a shorted LED can't be pulled down */
    float vc = hw_adc_cath_fast();
    float h = led_headroom(&C.led, C.i_probe);
    if (C.phase_ticks > 8u && vc < h + 1.0f)
        go_on();
    else if (C.phase_ticks > (uint32_t)(PROBE_TIMEOUT_S * TICK_HZ)) {
        if (vc > 2.5f)
            enter_fault(LFAULT_SHORT);
        else
            go_on();
    }
}

static void tick_on(void)
{
    float b = fade_step(&C.fade);
    C.b_now = b;
    if (C.off_after_fade && !C.fade.active && b <= 0.0f) {
        C.state = CTL_TAIL;
        C.phase_ticks = 0;
        C.tail_v0 = C.vcmd;
        for (int k = 0; k < NCH - 1; k++)
            C.ch.armed[k] = 0;
        return;
    }
    float i_des = cap_current(curve_current(&C.curve, b));
    float rate = fade_rate(&C.fade);
    float i_lead = i_des;
    float i_arm = i_des;
    if (rate > 0.0f) {
        float il = cap_current(curve_current(&C.curve, fade_ahead(&C.fade, 0.002f)));
        if (il > i_lead)
            i_lead = il;
        i_arm = cap_current(curve_current(&C.curve, fade_ahead(&C.fade, ARM_LOOKAHEAD_S)));
    }
    /* V_out leads rising current and follows falling current one tick later */
    float i_prev = C.i_applied;
    C.vcmd = vout_target(i_lead > i_prev ? i_lead : i_prev);
    float i_app = i_des;
    if (i_des > i_prev) {
        float v_req = led_vout_target(&C.led, i_des);
        if (v_req > C.vmodel + 0.05f && C.vmodel < VOUT_MAX_V - 0.1f) {
            float i_ok = led_current_allowed(&C.led, C.vmodel + 0.05f);
            if (i_ok < i_prev)
                i_ok = i_prev;
            if (i_ok < i_app)
                i_app = i_ok;
        }
    }
    C.i_applied = i_app;
    channels_arm(&C.ch, i_app, i_arm);
    codes_for_monotonic(i_app, rate);
}

static void tick_tail(void)
{
    C.phase_ticks++;
    float t = (float)C.phase_ticks * DT;
    float frac = t / C.tail_s;
    if (frac > 1.0f)
        frac = 1.0f;
    C.vcmd = fmaxf(C.tail_v0 - TAIL_DROP_V * frac, VOUT_FLOOR_V);
    float i_min = C.curve.i_min;
    codes_zero();
    C.codes[3] = channel_code(&C.ch, 3, i_min);
    float excess = (C.tail_v0 - C.vcmd) - led_headroom(&C.led, i_min);
    C.i_applied = excess > 0.0f ? i_min * expf(-excess / C.led.nnvt) : i_min;
    C.b_now = 0.0f;
    if (frac >= 1.0f)
        go_off_now();
}

static void tick_raw(void)
{
    if (C.raw_pending) {
        C.raw_pending--;
        float i_now = C.raw_ch >= 0 ? channel_amps(&C.ch, C.raw_ch, C.raw_code) : 0.0f;
        float i_next = C.raw_ch >= 0 ? channel_amps(&C.ch, C.raw_ch, C.raw_next) : 0.0f;
        C.vcmd = vout_target(fmaxf(fmaxf(i_now, i_next), 1e-6f));
        if (i_next <= i_now || C.raw_pending == 0) {
            C.raw_code = C.raw_next;
            C.raw_pending = 0;
        }
    } else {
        float i = C.raw_ch >= 0 ? channel_amps(&C.ch, C.raw_ch, C.raw_code) : 0.0f;
        C.vcmd = vout_target(fmaxf(i, 1e-6f));
    }
    codes_zero();
    if (C.raw_ch >= 0 && C.raw_ch < NCH)
        C.codes[C.raw_ch] = C.raw_code;
    C.i_applied = C.raw_ch >= 0 ? channel_amps(&C.ch, C.raw_ch, C.raw_code) : 0.0f;
}

static void comp_update(void)
{
    int mask = 1;
    if (C.state == CTL_ON || C.state == CTL_RAW) {
        float i = C.i_applied > 1e-9f ? C.i_applied : 1e-9f;
        float expect = C.vmodel - led_vf(&C.led, i);
        mask = expect > CATH_TRIP_MAX_V - 0.4f;
    }
    if (mask)
        C.comp_mask = COMP_MASK_TICKS;
    if (C.comp_mask) {
        C.comp_mask--;
        if (C.comp_irq_on) {
            hw_comp_enable_irq(0);
            C.comp_irq_on = 0;
        }
        return;
    }
    if (!C.comp_irq_on) {
        if (hw_comp_output()) {                     /* already above the trip level when it should not be */
            enter_fault(LFAULT_SHORT);
            return;
        }
        hw_comp_enable_irq(1);
        C.comp_irq_on = 1;
    }
}

static void outputs_write(void)
{
    hw_buckdac_set((BUCK_V0 - C.vcmd) / BUCK_K);
    int changed = 0;
    for (int k = 0; k < NCH; k++) {
        if (C.codes[k] != C.written[k] || C.force_write) {
            dac8_write((uint8_t)(DAC8_REG_DAC0 + k), C.codes[k]);
            C.written[k] = C.codes[k];
            changed = 1;
        }
    }
    C.force_write = 0;
    if (changed) {
        dac8_load();
        return;
    }
    if ((C.ticks & 15u) != 0u)
        return;
    /* idle tick: read one register back and compare with what it should hold; STATUS must show no
     * reference alarm (the DAC shuts its outputs off while one is present) */
    static const uint8_t regs[8] = { DAC8_REG_DAC0, DAC8_REG_DAC0 + 1, DAC8_REG_DAC0 + 2, DAC8_REG_DAC0 + 3,
                                     DAC8_REG_SYNC, DAC8_REG_GAIN, DAC8_REG_CONFIG, DAC8_REG_STATUS };
    uint8_t r = regs[C.rb_index++ % 8u];
    uint16_t v = dac8_read(r);
    int bad;
    if (r >= DAC8_REG_DAC0)
        bad = v != C.written[r - DAC8_REG_DAC0];
    else if (r == DAC8_REG_STATUS)
        bad = (v & DAC8_STATUS_REFALM) != 0u;
    else
        bad = v != (r == DAC8_REG_SYNC ? DAC8_SYNC_VAL : r == DAC8_REG_GAIN ? DAC8_GAIN_VAL : DAC8_CONFIG_VAL);
    if (bad) {
        C.rb_errors++;
        dac8_write(DAC8_REG_CONFIG, DAC8_CONFIG_VAL);
        dac8_write(DAC8_REG_GAIN, DAC8_GAIN_VAL);
        dac8_write(DAC8_REG_SYNC, DAC8_SYNC_VAL);
        C.force_write = 1;
    }
}

void control_tick(void)
{
    C.ticks++;
    if (C.fault_isr && C.state != CTL_FAULT) {
        C.fault_isr = 0;
        enter_fault(LFAULT_SHORT);
    }
    if (C.fault_req) {
        if (C.state != CTL_FAULT)
            enter_fault(C.fault_req);
        C.fault_req = 0;
    }
    if (C.cmd_seq != C.cmd_seen) {
        C.cmd_seen = C.cmd_seq;
        handle_cmd();
    }
    switch (C.state) {
    case CTL_STARTING: tick_starting(); break;
    case CTL_ON: tick_on(); break;
    case CTL_TAIL: tick_tail(); break;
    case CTL_RAW: tick_raw(); break;
    case CTL_OFF:
    case CTL_FAULT:
    default:
        codes_zero();
        C.vcmd = VOUT_FLOOR_V;
        C.i_applied = 0.0f;
        C.b_now = 0.0f;
        if (C.clamp_delay)
            C.clamp_delay--;
        else
            clamps(1);
        break;
    }
    C.vmodel += (C.vcmd - C.vmodel) * VMODEL_K;
    comp_update();
    outputs_write();
}

void control_fault_isr(void)
{
    C.fault_isr = 1;
    hw_buckdac_set(VDAC_MAX_V);                     /* V_out to its floor straight away */
}

/* ================================================================== commands (main loop) */

static void post(uint8_t kind)
{
    C.cmd_kind = kind;
    __asm volatile("" ::: "memory");
    C.cmd_seq++;
}

static void seq_cancel(void) { C.seq.active = 0; }

static void level_raw(uint16_t level, uint32_t fade_ms)
{
    C.cmd_level = level;
    C.cmd_fade_s = (float)fade_ms / 1000.0f;
    post(CMD_LEVEL);
}

void control_level(uint16_t level, uint32_t fade_ms)
{
    seq_cancel();
    level_raw(level, fade_ms);
}

void control_raw(int ch, uint16_t code)
{
    seq_cancel();
    C.cmd_ch = (int8_t)ch;
    C.cmd_code = code;
    post(CMD_RAW);
}

void control_raw_exit(void) { post(CMD_RAW_EXIT); }

void control_force_fault(uint8_t fault)
{
    request_fault(fault);
}

void control_clear_fault(void)
{
    C.retries = 0;
    post(CMD_CLEAR);
}

static void seq_begin(int blinks, uint16_t l_final, uint32_t final_ms)
{
    uint16_t l = control_level_now();
    C.seq.from_off = (C.state == CTL_OFF);
    if (C.seq.from_off)
        l = curve_level_from_b(0.35f);
    float b = curve_b_from_level(l);
    float ratio = logf(C.curve.i_max / C.curve.i_min);
    float db = logf(8.0f) / ratio;                     /* one eighth of the current */
    C.seq.l_orig = l;
    C.seq.l_dim = C.seq.from_off ? 0 : curve_level_from_b(b - db > 0.0f ? b - db : 0.0f);
    C.seq.l_final = l_final;
    C.seq.final_ms = final_ms;
    C.seq.blinks = blinks;
    C.seq.step = 0;
    C.seq.t_next = hw_millis();
    C.seq.active = 1;
}

void control_identify(int blinks)
{
    if (C.state == CTL_FAULT)
        return;
    uint16_t back = C.state == CTL_OFF ? 0 : control_level_now();
    seq_begin(blinks < 1 ? 1 : blinks, back, 300);
}

void control_link_lost(void)
{
    if (C.state != CTL_ON && C.state != CTL_STARTING)
        return;                                        /* a dark fixture stays dark */
    uint16_t now = C.level_target;
    uint16_t fb = curve_level_from_b(C.p->fallback_b);
    seq_begin(2, now < fb ? now : fb, 2000);
}

static void seq_run(uint32_t now)
{
    if (!C.seq.active || (int32_t)(now - C.seq.t_next) < 0)
        return;
    int step = C.seq.step++;
    if (step < 2 * C.seq.blinks) {
        if (C.seq.from_off)
            level_raw((step & 1) ? 0 : C.seq.l_orig, 0);
        else
            level_raw((step & 1) ? C.seq.l_orig : C.seq.l_dim, 0);
        C.seq.t_next = now + ((step & 1) ? 200u : 200u);
    } else {
        level_raw(C.seq.l_final, C.seq.final_ms);
        C.seq.active = 0;
    }
}

/* ================================================================== background */

static float ntc_c(float v, float vdda)
{
    if (v <= 0.01f || v >= vdda - 0.01f)
        return -99.0f;
    float r = NTC_RPULL * v / (vdda - v);
    float inv = 1.0f / 298.15f + logf(r / NTC_R25) / NTC_B;
    return 1.0f / inv - 273.15f;
}

static void request_fault(uint8_t f)
{
    if (C.state != CTL_FAULT && !C.fault_req)
        C.fault_req = f;
}

static void headroom_learn(void)
{
    if (!(C.state == CTL_ON || C.state == CTL_RAW) || C.comp_mask)
        return;
    float rate = fabsf(fade_rate(&C.fade));
    if (rate > 0.2f)
        return;
    float i = C.i_applied;
    if (i < 1e-7f)
        return;
    float h = led_headroom(&C.led, i);
    float vc = C.an.v_cath;
    float dv;
    if (vc >= 3.0f)
        dv = -0.2f;                                    /* tap clamped: far too much headroom */
    else if (vc < 0.08f)
        dv = 0.2f;                                     /* starving */
    else
        dv = -0.1f * (vc - h);
    /* the channel carrying the current is near its rail: short of headroom */
    float s[NCH];
    channels_split(&C.ch, i, s);
    int m = 0;
    for (int k = 1; k < NCH; k++)
        if (s[k] > s[m])
            m = k;
    if (C.an.gmon[m] > 4.3f && dv < 0.2f)
        dv = 0.2f;
    if (rate > 0.05f)
        dv *= 0.5f;
    led_learn(&C.led, i, dv);
}

static void monitors(uint32_t now)
{
    /* temperatures and derating */
    float f = 1.0f;
    int ot = 0;
    for (int n = 0; n < 4; n++) {
        C.temp[n] = ntc_c(C.an.ntc_v[n], C.an.vdda);
        if (C.temp[n] > NTC_DERATE_C[n]) {
            float x = 1.0f - 0.75f * (C.temp[n] - NTC_DERATE_C[n]) / (NTC_TRIP_C[n] - NTC_DERATE_C[n]);
            if (x < f)
                f = x;
        }
        if (C.temp[n] >= NTC_TRIP_C[n])
            ot = 1;
    }
    C.derate = clampf(f, 0.25f, 1.0f);
    if (ot)
        request_fault(LFAULT_OVERTEMP);
    /* input undervoltage, 20 ms persistence */
    if (C.an.v_48 < V48_UV_V) {
        if (++C.uv_ms > 20u)
            request_fault(LFAULT_UNDERVOLT);
    } else
        C.uv_ms = 0;
    /* buck power-good */
    if (!hw_buck_pg()) {
        if (++C.pg_ms > 20u)
            request_fault(LFAULT_BUCK);
    } else
        C.pg_ms = 0;
    /* open LED: V_out pinned at its ceiling, the cathode still near zero */
    if (C.state == CTL_ON && C.i_applied > 50e-6f && C.vcmd >= VOUT_MAX_V - 0.05f && C.an.v_cath < OPEN_VCATH_V) {
        if (++C.open_ms > 200u)
            request_fault(LFAULT_OPEN);
    } else
        C.open_ms = 0;
    /* shorted LED with the tap in range: V_out - V_cath far below any real V_f */
    if (C.state == CTL_ON && C.i_applied > 100e-6f && !C.comp_mask && C.an.v_cath < 3.0f &&
        (C.an.v_out - C.an.v_cath) < SHORT_VF_MIN_V) {
        if (++C.short_ms > 20u)
            request_fault(LFAULT_SHORT);
    } else
        C.short_ms = 0;
    /* DAC80504 read-back mismatches: more than 3 in a second is a fault */
    if (now - C.rb_window_ms >= 1000u) {
        C.rb_window_ms = now;
        C.rb_window_errs = 0;
    }
    uint32_t e = C.rb_errors;
    if (e != C.rb_seen) {
        C.rb_window_errs += e - C.rb_seen;
        C.rb_seen = e;
        if (C.rb_window_errs > 3u)
            request_fault(LFAULT_DAC);
    }
}

static void fault_policy(uint32_t now)
{
    if (C.state != CTL_FAULT) {
        C.t_fault_ms = now;
        return;
    }
    uint32_t in_fault = now - C.t_fault_ms;
    int clear = 0;
    switch (C.fault) {
    case LFAULT_UNDERVOLT:
        clear = C.an.v_48 > V48_ON_V && in_fault > 500u;
        break;
    case LFAULT_OVERTEMP: {
        clear = 1;
        for (int n = 0; n < 4; n++)
            if (C.temp[n] > NTC_DERATE_C[n] - 10.0f)
                clear = 0;
        break;
    }
    case LFAULT_BUCK:
        clear = hw_buck_pg() && in_fault > 1000u && C.retries < 3u;
        break;
    case LFAULT_DAC:
        if (in_fault > 1000u && C.retries < 3u)
            clear = dac8_init() == 0;
        break;
    default:                                           /* SHORT, OPEN: three tries, 5 s apart, then latch */
        clear = in_fault > 5000u && C.retries < 3u;
        break;
    }
    if (clear) {
        C.retries++;
        post(CMD_CLEAR);
        if (C.level_target)
            level_raw(C.level_target, 1000);
        C.t_fault_ms = now;
    }
}

static void deferred_save(void)
{
    if (!C.save_pending)
        return;
    int quiet = C.state == CTL_OFF || C.state == CTL_FAULT ||
                ((C.state == CTL_ON || C.state == CTL_RAW) && C.i_applied < SAVE_MAX_A && !C.fade.active);
    if (!quiet)
        return;
    memcpy(C.p->cal, C.ch.cal, sizeof(C.p->cal));
    memcpy(C.p->vf_corr, C.led.corr, sizeof(C.p->vf_corr));
    params_seal(C.p);
    hw_iwdg_kick();
    hw_flash_store(C.p, sizeof(*C.p));
    C.save_pending = 0;
}

void control_background(void)
{
    uint32_t now = hw_millis();
    if (now == C.last_ms)
        return;
    C.last_ms = now;
    hw_adc_read(&C.an);
    monitors(now);
    fault_policy(now);
    if (now - C.last_learn_ms >= 10u) {
        C.last_learn_ms = now;
        headroom_learn();
    }
    seq_run(now);
    deferred_save();
}

/* ================================================================== init and accessors */

void control_apply_params(void)
{
    params_t *p = C.p;
    curve_defaults(&C.curve);
    C.curve.i_min = clampf(p->i_tail_end, 0.5e-6f, 100e-6f);
    C.curve.i_max = clampf(p->i_max, 0.1f, I_MAX_A);
    C.curve.lux_i[0] = p->lux_i[0];
    C.curve.lux_i[1] = p->lux_i[1];
    C.curve.lux_v[0] = p->lux_v[0];
    C.curve.lux_v[1] = p->lux_v[1];
    C.curve.lux_ref = p->lux_ref;
    uint8_t armed[NCH];
    memcpy(armed, C.ch.armed, sizeof(armed));
    memcpy(C.ch.cal, p->cal, sizeof(C.ch.cal));
    channels_update_ka(&C.ch);
    memcpy(C.ch.armed, armed, sizeof(armed));
    C.led.h_hi = clampf(p->h_hi, 0.5f, 2.0f);
    C.led.h_lo = clampf(p->h_lo, 0.4f, 2.0f);
}

void control_init(params_t *p)
{
    memset(&C, 0, sizeof(C));
    C.p = p;
    led_defaults(&C.led);
    memcpy(C.led.corr, p->vf_corr, sizeof(C.led.corr));
    channels_nominal(&C.ch);
    control_apply_params();
    fade_init(&C.fade, 0.0f);
    C.derate = 1.0f;
    C.state = CTL_OFF;
    C.vcmd = C.vmodel = VOUT_FLOOR_V;
    C.clamps_on = 1;
    C.force_write = 1;
    C.last_ms = hw_millis();
    C.rb_window_ms = C.last_ms;
    hw_adc_read(&C.an);
}

ctl_state_t control_state(void) { return C.state; }
uint8_t control_fault(void) { return C.fault; }
uint16_t control_level_target(void) { return C.level_target; }
uint16_t control_level_now(void)
{
    if (C.state == CTL_ON || C.state == CTL_TAIL)
        return C.state == CTL_TAIL ? 1u : curve_level_from_b(C.b_now);
    return 0;
}
float control_current(void) { return C.i_applied; }
void control_codes(uint16_t out[NCH]) { memcpy(out, C.written, sizeof(C.written)); }
const analog_t *control_analog(void) { return &C.an; }
float control_temp(int i) { return C.temp[i & 3]; }
channels_t *control_channels(void) { return &C.ch; }
ledmodel_t *control_led(void) { return &C.led; }
curve_t *control_curve(void) { return &C.curve; }
int control_save_pending(void) { return C.save_pending; }
void control_request_save(void) { C.save_pending = 1; }
uint32_t control_dac_errors(void) { return C.rb_errors; }

void control_status(msg_status_t *s)
{
    memset(s, 0, sizeof(*s));
    s->level_target = C.level_target;
    s->level_now = control_level_now();
    s->state = (uint8_t)(C.state == CTL_RAW ? LSTATE_ON : C.state == CTL_BOOT ? LSTATE_BOOT :
                         C.state == CTL_OFF ? LSTATE_OFF : C.state == CTL_STARTING ? LSTATE_STARTING :
                         C.state == CTL_ON ? LSTATE_ON : C.state == CTL_TAIL ? LSTATE_TAIL : LSTATE_FAULT);
    s->fault = C.fault;
    uint16_t fl = 0;
    if (C.fade.active)
        fl |= LFLAG_FADING;
    if (C.derate < 0.999f)
        fl |= LFLAG_DERATING;
    if (curve_lux_enabled(&C.curve))
        fl |= LFLAG_LUX_MATCH;
    if (C.p->calibrated)
        fl |= LFLAG_CALIBRATED;
    if (C.seq.active)
        fl |= LFLAG_SEQUENCE;
    for (int k = 0; k < NCH; k++)
        if (C.ch.armed[k])
            fl |= (uint16_t)(1u << (LFLAG_ARMED_SHIFT + k));
    s->flags = fl;
    s->i_led = C.i_applied;
    s->v_out = C.an.v_out;
    s->v_led = (C.an.v_cath < 3.0f && C.i_applied > 0.0f) ? C.an.v_out - C.an.v_cath : 0.0f;
    s->v_in = C.an.v_48;
    for (int n = 0; n < 4; n++)
        s->temp_c10[n] = (int16_t)lroundf(C.temp[n] * 10.0f);
    s->fw_version = FW_VERSION;
    s->uptime_s = hw_millis() / 1000u;
}
