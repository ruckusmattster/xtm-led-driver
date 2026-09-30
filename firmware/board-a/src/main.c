/*
 * Board A firmware: 4-decade LED driver for the Xicato XTM.
 *
 * Start-up order matters: the gate clamps are driven on and the main buck held off
 * before anything else, the buck DAC is set to the V_out floor before its output
 * enables, and the main buck starts only once the 48 V rail is confirmed.
 */
#include "config.h"
#include "console.h"
#include "control.h"
#include "hw.h"
#include "link.h"
#include "params.h"
#include "settings.h"

static params_t g_params;

params_t *app_params(void) { return &g_params; }

static void status_led(uint32_t now)
{
    int on;
    ctl_state_t s = control_state();
    if (s == CTL_FAULT)
        on = (now / 100u) & 1u;                                   /* 5 Hz */
    else if (link_is_lost())
        on = (now % 1000u) < 100u || ((now % 1000u) >= 200u && (now % 1000u) < 300u);   /* double blink */
    else if (s == CTL_ON || s == CTL_STARTING || s == CTL_TAIL || s == CTL_RAW)
        on = 1;
    else
        on = (now % 2000u) < 50u;                                 /* alive */
    hw_led(on);
}

int main(void)
{
    hw_init_clock();
    hw_init_gpio();                    /* clamps on, buck off, DAC CS high */
    hw_init_systick();
    uint32_t reset_cause = hw_reset_cause();

    hw_flash_load(&g_params, sizeof(g_params));
    if (!params_valid(&g_params))
        params_defaults(&g_params);

    hw_adc_init();
    hw_buckdac_init((BUCK_V0 - VOUT_FLOOR_V) / BUCK_K);   /* floor before the buck ever runs */
    hw_comp_init();
    int dac_err = dac8_init();
    hw_uart_init();
    control_init(&g_params);
    console_init(reset_cause, dac_err);
    link_init();
    hw_iwdg_start();

    /* wait for a healthy 48 V rail before starting the main buck */
    analog_t a;
    uint32_t t0 = hw_millis(), last_msg = t0;
    for (;;) {
        hw_iwdg_kick();
        hw_adc_read(&a);
        if (a.v_48 >= V48_ON_V)
            break;
        uint32_t now = hw_millis();
        if (now - last_msg > 2000u) {
            con_printf("waiting for 48 V: v48=%.1f\r\n", (double)a.v_48);
            last_msg = now;
        }
        console_poll();
        hw_led(((now - t0) / 250u) & 1u);
    }
    hw_buck_enable(1);
    uint32_t t_pg = hw_millis();
    while (!hw_buck_pg() && hw_millis() - t_pg < 50u)
        hw_iwdg_kick();
    if (!hw_buck_pg())
        con_printf("warning: buck power-good not asserted after 50 ms\r\n");

    hw_tick_start(TICK_HZ);
    hw_aok(1);
    if (dac_err) {
        con_printf("DAC80504 did not respond as expected (err=%d); outputs stay off\r\n", dac_err);
        control_force_fault(LFAULT_DAC);
    }

    for (;;) {
        hw_iwdg_kick();
        control_background();
        link_poll();
        console_poll();
        status_led(hw_millis());
    }
}
