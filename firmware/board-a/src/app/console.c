/*
 * Line console. Every reply line is "key=value ..." so tools/calibrate.py can parse it;
 * a line starting with "ok" or "err" ends each command.
 */
#include "console.h"
#include "config.h"
#include "control.h"
#include "curve.h"
#include "hw.h"
#include "link.h"
#include "link_protocol.h"
#include "settings.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char line[96];
static size_t line_n;
static int raw_ch = -1;
static uint16_t raw_code;

void con_printf(const char *fmt, ...)
{
    char buf[200];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    if (n > 0)
        hw_con_write((const uint8_t *)buf, (size_t)(n < (int)sizeof(buf) ? n : (int)sizeof(buf) - 1));
}

static const char *state_name(ctl_state_t s)
{
    static const char *const n[] = { "boot", "off", "starting", "on", "tail", "fault", "raw" };
    return (unsigned)s < 7u ? n[s] : "?";
}

static void status_line(void)
{
    const analog_t *a = control_analog();
    uint16_t c[NCH];
    control_codes(c);
    con_printf("state=%s fault=%u level=%u target=%u i=%.6g vout=%.3f vcath=%.3f v48=%.2f vdda=%.4f "
               "codes=%u,%u,%u,%u gmon=%.2f,%.2f,%.2f,%.2f t=%.1f,%.1f,%.1f,%.1f link=%s dacerr=%lu\r\n",
               state_name(control_state()), control_fault(), control_level_now(), control_level_target(),
               (double)control_current(), (double)a->v_out, (double)a->v_cath, (double)a->v_48, (double)a->vdda,
               c[0], c[1], c[2], c[3], (double)a->gmon[0], (double)a->gmon[1], (double)a->gmon[2],
               (double)a->gmon[3], (double)control_temp(0), (double)control_temp(1), (double)control_temp(2),
               (double)control_temp(3), link_is_lost() ? "lost" : "ok", (unsigned long)control_dac_errors());
}

static void cal_show(void)
{
    channels_t *ch = control_channels();
    params_t *p = app_params();
    for (int k = 0; k < NCH; k++) {
        const chcal_t *c = &p->cal[k];
        con_printf("ch=%d calibrated=%d ka_code=%u ka_a=%.6g points=", k + 1, (int)((p->calibrated >> k) & 1u),
                   channel_ka_code(ch, k), (double)ch->ka[k]);
        for (int i = 0; i < c->n; i++)
            con_printf("%s%u:%.7g", i ? "," : "", c->code[i], (double)c->amps[i]);
        con_printf("\r\n");
    }
}

static int parse_ch(const char *s)
{
    int k = s ? atoi(s) : 0;
    return (k >= 1 && k <= NCH) ? k - 1 : -1;
}

static void set_raw(int k, uint16_t code)
{
    raw_ch = k;
    raw_code = code;
    control_raw(k, code);
}

/* Measured points collected this session, per channel. Two or more replace the channel's model. */
static chcal_t meas[NCH];

static void cal_point(int k, float amps)
{
    params_t *p = app_params();
    channels_t tmp;
    memset(&tmp, 0, sizeof(tmp));
    tmp.cal[k] = meas[k];
    if (tmp.cal[k].n == 0) {
        tmp.cal[k].n = 1;
        tmp.cal[k].code[0] = raw_code;
        tmp.cal[k].amps[0] = amps;
    } else if (channel_cal_point(&tmp, k, raw_code, amps) != 0) {
        con_printf("err rejected: points must rise in both code and current\r\n");
        return;
    }
    meas[k] = tmp.cal[k];
    if (meas[k].n >= 2) {
        p->cal[k] = meas[k];
        p->calibrated |= 1u << k;
        control_apply_params();
    }
    con_printf("ok ch=%d code=%u amps=%.7g points=%u\r\n", k + 1, raw_code, (double)amps, meas[k].n);
}

static void cmd(char *s)
{
    char *argv[6];
    int argc = 0;
    for (char *t = strtok(s, " \t"); t && argc < 6; t = strtok(NULL, " \t"))
        argv[argc++] = t;
    if (argc == 0)
        return;
    const char *c = argv[0];
    params_t *p = app_params();

    if (!strcmp(c, "help")) {
        con_printf("st | lvl L [ms] | b pos [ms] | off | raw ch code | rawi ch amps | ka ch | dark | exit |\r\n"
                   "cal ch amps | calreset ch | calshow | dark_a amps | set id val | get id | params | save |\r\n"
                   "defaults | vf | clear | id [n] | reboot\r\nok\r\n");
    } else if (!strcmp(c, "st")) {
        status_line();
        con_printf("ok\r\n");
    } else if (!strcmp(c, "lvl") && argc >= 2) {
        control_level((uint16_t)atoi(argv[1]), argc >= 3 ? (uint32_t)atoi(argv[2]) : 0u);
        con_printf("ok\r\n");
    } else if (!strcmp(c, "b") && argc >= 2) {
        control_level(curve_level_from_b(strtof(argv[1], NULL)), argc >= 3 ? (uint32_t)atoi(argv[2]) : 0u);
        con_printf("ok\r\n");
    } else if (!strcmp(c, "off")) {
        control_level(0, 0);
        con_printf("ok\r\n");
    } else if (!strcmp(c, "raw") && argc >= 3) {
        int k = parse_ch(argv[1]);
        if (k < 0) { con_printf("err channel\r\n"); return; }
        set_raw(k, (uint16_t)atoi(argv[2]));
        con_printf("ok ch=%d code=%u est=%.6g\r\n", k + 1, raw_code, (double)channel_amps(control_channels(), k, raw_code));
    } else if (!strcmp(c, "rawi") && argc >= 3) {
        int k = parse_ch(argv[1]);
        if (k < 0) { con_printf("err channel\r\n"); return; }
        uint16_t code = channel_code(control_channels(), k, strtof(argv[2], NULL));
        set_raw(k, code);
        con_printf("ok ch=%d code=%u\r\n", k + 1, code);
    } else if (!strcmp(c, "ka") && argc >= 2) {
        int k = parse_ch(argv[1]);
        if (k < 0) { con_printf("err channel\r\n"); return; }
        set_raw(k, channel_ka_code(control_channels(), k));
        con_printf("ok ch=%d code=%u est=%.6g\r\n", k + 1, raw_code, (double)control_channels()->ka[k]);
    } else if (!strcmp(c, "dark")) {
        set_raw(-1, 0);
        con_printf("ok\r\n");
    } else if (!strcmp(c, "exit")) {
        raw_ch = -1;
        control_raw_exit();
        con_printf("ok\r\n");
    } else if (!strcmp(c, "cal") && argc >= 3) {
        int k = parse_ch(argv[1]);
        if (k < 0 || k != raw_ch || control_state() != CTL_RAW) { con_printf("err use raw on that channel first\r\n"); return; }
        cal_point(k, strtof(argv[2], NULL));
    } else if (!strcmp(c, "calreset") && argc >= 2) {
        int k = parse_ch(argv[1]);
        if (k < 0) { con_printf("err channel\r\n"); return; }
        channels_t tmp;
        channel_cal_reset(&tmp, k);
        p->cal[k] = tmp.cal[k];
        p->calibrated &= ~(1u << k);
        memset(&meas[k], 0, sizeof(meas[k]));
        control_apply_params();
        con_printf("ok\r\n");
    } else if (!strcmp(c, "calshow")) {
        cal_show();
        con_printf("ok\r\n");
    } else if (!strcmp(c, "dark_a") && argc >= 2) {
        p->dark_a = strtof(argv[1], NULL);
        con_printf("ok dark_a=%.4g\r\n", (double)p->dark_a);
    } else if (!strcmp(c, "set") && argc >= 3) {
        int r = settings_set(p, (uint8_t)atoi(argv[1]), strtof(argv[2], NULL));
        if (r) { con_printf("err %d\r\n", r); return; }
        control_apply_params();
        con_printf("ok\r\n");
    } else if (!strcmp(c, "get") && argc >= 2) {
        float v;
        uint8_t id = (uint8_t)atoi(argv[1]);
        if (settings_get(p, id, &v)) { con_printf("err\r\n"); return; }
        con_printf("%s=%.7g\r\nok\r\n", settings_name(id), (double)v);
    } else if (!strcmp(c, "params")) {
        for (uint8_t id = 0; id < PARAM_COUNT; id++) {
            float v;
            if (!settings_get(p, id, &v))
                con_printf("%u %s=%.7g\r\n", id, settings_name(id), (double)v);
        }
        con_printf("dark_a=%.4g calibrated=0x%lx\r\nok\r\n", (double)p->dark_a, (unsigned long)p->calibrated);
    } else if (!strcmp(c, "save")) {
        control_request_save();
        con_printf("ok saved when the light is off or below 10 mA\r\n");
    } else if (!strcmp(c, "defaults")) {
        params_defaults(p);
        control_apply_params();
        con_printf("ok defaults loaded (not saved)\r\n");
    } else if (!strcmp(c, "vf")) {
        ledmodel_t *m = control_led();
        con_printf("vf0=%.3f nnvt=%.3f rs=%.3f corr=", (double)m->vf0, (double)m->nnvt, (double)m->rs);
        for (int b = 0; b < LED_NBINS; b++)
            con_printf("%s%.3f", b ? "," : "", (double)m->corr[b]);
        con_printf("\r\nok\r\n");
    } else if (!strcmp(c, "clear")) {
        control_clear_fault();
        con_printf("ok\r\n");
    } else if (!strcmp(c, "id")) {
        control_identify(argc >= 2 ? atoi(argv[1]) : 3);
        con_printf("ok\r\n");
    } else if (!strcmp(c, "reboot")) {
        con_printf("ok\r\n");
        hw_delay_us(20000);
        hw_reboot();
    } else {
        con_printf("err unknown command (help)\r\n");
    }
}

void console_init(uint32_t reset_cause, int dac_err)
{
    line_n = 0;
    con_printf("\r\nxtm-driver board A fw %d.%d reset=0x%08lx dac80504=%s\r\n", FW_VERSION_MAJOR, FW_VERSION_MINOR,
               (unsigned long)reset_cause, dac_err ? "ERROR" : "ok");
}

void console_poll(void)
{
    int ch;
    while ((ch = hw_con_getc()) >= 0) {
        if (ch == '\r' || ch == '\n') {
            if (line_n) {
                line[line_n] = 0;
                cmd(line);
                line_n = 0;
            }
        } else if (line_n < sizeof(line) - 1) {
            line[line_n++] = (char)ch;
        }
    }
}
