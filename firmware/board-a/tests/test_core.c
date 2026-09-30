/* Host tests for the portable core: make -C tests */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "channels.h"
#include "config.h"
#include "curve.h"
#include "fade.h"
#include "frame.h"
#include "ledmodel.h"
#include "link_protocol.h"
#include "params.h"

static int fails, checks;
#define CHECK(cond, ...) do { checks++; if (!(cond)) { fails++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void test_frame(void)
{
    CHECK(crc16_ccitt((const uint8_t *)"123456789", 9) == 0x29B1, "crc16 check value");
    uint8_t in[300], enc[320], dec[320];
    srand(1);
    for (int trial = 0; trial < 200; trial++) {
        size_t n = (size_t)(rand() % 300);
        for (size_t i = 0; i < n; i++)
            in[i] = (rand() % 4 == 0) ? 0 : (uint8_t)rand();
        size_t e = cobs_encode(in, n, enc);
        int has_zero = 0;
        for (size_t i = 0; i < e; i++)
            has_zero |= enc[i] == 0;
        size_t d = cobs_decode(enc, e, dec);
        CHECK(!has_zero && d == n && memcmp(in, dec, n) == 0, "cobs round trip n=%zu", n);
    }
    /* full frame through the streaming receiver */
    msg_set_level_t m = { 12345, 2500, 0 };
    uint8_t wire[80], out[64];
    size_t w = frame_build(MSG_SET_LEVEL, 7, &m, sizeof(m), wire, sizeof(wire));
    frame_rx_t rx;
    memset(&rx, 0, sizeof(rx));
    size_t got = 0;
    for (size_t i = 0; i < w; i++)
        got = frame_rx_byte(&rx, wire[i], out, sizeof(out));
    msg_set_level_t r;
    memcpy(&r, out + 2, sizeof(r));
    CHECK(got == 2 + sizeof(m) && out[0] == MSG_SET_LEVEL && out[1] == 7 && r.level == 12345 && r.fade_ms == 2500,
          "frame round trip");
    wire[3] ^= 0x10;                                  /* corrupt one byte */
    got = 0;
    for (size_t i = 0; i < w; i++)
        got |= frame_rx_byte(&rx, wire[i], out, sizeof(out));
    CHECK(got == 0 && rx.bad == 1, "corrupted frame rejected");
    CHECK(sizeof(msg_status_t) <= LINK_MAX_PAYLOAD, "status fits: %zu", sizeof(msg_status_t));
}

static void test_curve(void)
{
    curve_t c;
    curve_defaults(&c);
    CHECK(curve_b_from_level(0) < 0.0f && curve_b_from_level(1) == 0.0f && curve_b_from_level(65535) == 1.0f, "level map");
    CHECK(fabsf(curve_current(&c, 0.0f) - 5e-6f) < 1e-9f, "bottom %g", (double)curve_current(&c, 0.0f));
    CHECK(fabsf(curve_current(&c, 1.0f) - 1.4f) < 1e-5f, "top");
    float prev = 0.0f;
    int mono = 1;
    for (int l = 1; l <= 65535; l++) {
        float i = curve_current(&c, curve_b_from_level((uint16_t)l));
        if (i < prev) mono = 0;
        prev = i;
    }
    CHECK(mono, "curve monotonic over all levels");
    for (float b = 0.0f; b <= 1.0f; b += 0.01f) {
        float i = curve_current(&c, b);
        CHECK(fabsf(curve_b_from_current(&c, i) - b) < 1e-4f, "inverse at b=%g", (double)b);
    }
    /* light matching: this fixture is 10 % brighter than the fleet reference at full */
    c.lux_i[0] = 0.14f; c.lux_v[0] = 110.0f;
    c.lux_i[1] = 1.40f; c.lux_v[1] = 1000.0f;       /* efficacy drops 9 % at full current */
    c.lux_ref = 900.0f;
    CHECK(curve_lux_enabled(&c), "lux enabled");
    float itop = curve_current(&c, 1.0f);
    CHECK(fabsf(curve_lux_at(&c, itop) - 900.0f) < 1.0f && itop < 1.4f, "matched top %g A -> %g lux", (double)itop,
          (double)curve_lux_at(&c, itop));
    prev = 0.0f;
    mono = 1;
    for (int l = 1; l <= 65535; l += 7) {
        float i = curve_current(&c, curve_b_from_level((uint16_t)l));
        if (i < prev) mono = 0;
        prev = i;
    }
    CHECK(mono, "lux-matched curve monotonic");
}

static float total_of(const channels_t *ch, float i)
{
    float s[NCH], t = 0.0f;
    channels_split(ch, i, s);
    for (int k = 0; k < NCH; k++)
        t += s[k];
    return t;
}

static void test_channels(void)
{
    channels_t ch;
    channels_nominal(&ch);
    /* nominal model round trip */
    for (int k = 0; k < NCH; k++) {
        for (float sense = 0.001f; sense < 0.19f; sense *= 1.3f) {
            float a = sense / CH_RS[k];
            uint16_t code = channel_code(&ch, k, a);
            float back = channel_amps(&ch, k, code);
            float lsb = SENSE_LSB_V / CH_RS[k];
            CHECK(fabsf(back - a) <= 0.51f * lsb, "ch%d round trip at %g A", k + 1, (double)a);
        }
        CHECK(channel_code(&ch, k, 0.0f) == 0, "zero -> dead zone");
        float kv = ch.ka[k] * CH_RS[k];
        CHECK(kv > 20e-6f && kv < 30e-6f, "ch%d keep-alive %g V of sense", k + 1, (double)kv);
    }
    /* split sums to the total and never goes negative, all arming combinations */
    for (int arm = 0; arm < 16; arm++) {
        for (int k = 0; k < NCH; k++)
            ch.armed[k] = (uint8_t)((arm >> k) & 1);
        for (float i = 5e-6f; i < 1.5f; i *= 1.01f) {
            float s[NCH], ka_sum = 0.0f;
            channels_split(&ch, i, s);
            for (int k = 0; k < NCH; k++) {
                CHECK(s[k] >= 0.0f, "negative share");
                if (ch.armed[k]) ka_sum += ch.ka[k];
            }
            if (i > 2.0f * ka_sum)
                CHECK(fabsf(total_of(&ch, i) - i) < 1e-6f * i + 1e-12f, "sum at %g", (double)i);
        }
    }
    /* continuity across each band edge with the normal arming */
    channels_disarm_all(&ch);
    for (int j = 0; j < NCH - 1; j++) {
        float edges[2] = { BAND_LO[j], BAND_HI[j] };
        for (int e = 0; e < 2; e++) {
            float lo = edges[e] * 0.99999f, hi = edges[e] * 1.00001f;
            channels_arm(&ch, lo, lo);
            float a[NCH], b[NCH];
            channels_split(&ch, lo, a);
            channels_split(&ch, hi, b);
            for (int k = 0; k < NCH; k++)
                CHECK(fabsf(a[k] - b[k]) < 1e-4f * edges[e], "band %d edge %d ch%d jump %g", j, e, k + 1,
                      (double)(b[k] - a[k]));
        }
    }
    /* arming hysteresis */
    channels_disarm_all(&ch);
    channels_arm(&ch, 0.8e-3f, 0.8e-3f);
    CHECK(ch.armed[2] && !ch.armed[1], "ch3 armed at 0.8 mA");
    channels_arm(&ch, 0.5e-3f, 0.5e-3f);
    CHECK(ch.armed[2], "ch3 stays armed at 0.5 mA");
    channels_arm(&ch, 0.3e-3f, 0.3e-3f);
    CHECK(!ch.armed[2], "ch3 disarmed at 0.3 mA");
    channels_arm(&ch, 0.1e-3f, 2e-3f);
    CHECK(ch.armed[2], "ch3 armed ahead of a fade");
    /* calibration points: insertion keeps order, rejects non-monotonic sets */
    channels_t t;
    channels_nominal(&t);
    t.cal[2].n = 0;
    t.cal[2].n = 1; t.cal[2].code[0] = 50000; t.cal[2].amps[0] = 14.6e-3f;
    CHECK(channel_cal_point(&t, 2, 5000, 1.4e-3f) == 0 && t.cal[2].n == 2 && t.cal[2].code[0] == 5000, "insert sorted");
    CHECK(channel_cal_point(&t, 2, 30000, 1.0e-3f) == -2, "reject non-monotonic");
    uint16_t kc = channel_ka_code(&t, 2);
    CHECK(channel_cal_point(&t, 2, kc, 2.4e-6f) == 0 && t.cal[2].n == 3 && channel_ka_code(&t, 2) == kc,
          "keep-alive point sticks at code %u", kc);
    CHECK(fabsf(t.ka[2] - 2.4e-6f) < 1e-9f, "measured keep-alive used: %g", (double)t.ka[2]);
}

/* A full-range fade through the whole chain: level -> current -> split -> codes -> modelled total.
 * The modelled total must never step backwards once the controller's monotonic guard is applied. */
static void test_fade_chain(void)
{
    channels_t ch;
    curve_t c;
    fade_t f;
    channels_nominal(&ch);
    curve_defaults(&c);
    fade_init(&f, 0.0f);
    fade_start(&f, 1.0f, 10.0f);
    uint16_t codes[NCH] = { 0 };
    float last = 0.0f, worst_dev = 0.0f;
    int held = 0, steps = 0;
    while (f.active) {
        float b = fade_step(&f);
        float i = curve_current(&c, b);
        channels_arm(&ch, i, curve_current(&c, fade_ahead(&f, ARM_LOOKAHEAD_S)));
        float s[NCH];
        uint16_t nc[NCH];
        channels_split(&ch, i, s);
        float tot = 0.0f;
        for (int k = 0; k < NCH; k++) {
            nc[k] = channel_code(&ch, k, s[k]);
            tot += channel_amps(&ch, k, nc[k]);
        }
        if (tot < last) {
            held++;
        } else {
            memcpy(codes, nc, sizeof(codes));
            last = tot;
        }
        float applied = 0.0f;
        for (int k = 0; k < NCH; k++)
            applied += channel_amps(&ch, k, codes[k]);
        float dev = fabsf(applied - i) / i;
        if (i > 20e-6f && dev > worst_dev)
            worst_dev = dev;
        steps++;
    }
    CHECK(steps == 40000, "10 s at 4 kHz: %d ticks", steps);
    CHECK(worst_dev < 0.01f, "quantised output within 1 %% of the curve above 20 uA (worst %.4f %%)",
          (double)(worst_dev * 100.0f));
    printf("  fade chain: %d ticks, %d held by the monotonic guard, worst deviation %.4f %% above 20 uA\n", steps,
           held, (double)(worst_dev * 100.0f));
}

static void test_fade(void)
{
    fade_t f;
    fade_init(&f, 0.2f);
    fade_start(&f, 0.8f, 2.0f);
    float b = 0.0f;
    for (int i = 0; i < 4000; i++)
        b = fade_step(&f);
    CHECK(fabsf(b - 0.5f) < 1e-3f && f.active, "half way %g", (double)b);
    CHECK(fabsf(fade_ahead(&f, 0.5f) - 0.65f) < 1e-3f, "ahead");
    for (int i = 0; i < 5000; i++)
        b = fade_step(&f);
    CHECK(b == 0.8f && !f.active, "arrives");
    /* ten minutes lands on the tick */
    fade_init(&f, 0.0f);
    fade_start(&f, 1.0f, 600.0f);
    uint32_t n = 0;
    while (f.active) { fade_step(&f); n++; }
    CHECK(n == 600u * TICK_HZ, "600 s fade: %u ticks", n);
    fade_start(&f, 0.1f, 0.0f);
    CHECK(f.b == 0.1f && !f.active, "snap");
}

static void test_ledmodel(void)
{
    ledmodel_t m;
    led_defaults(&m);
    CHECK(fabsf(led_vf(&m, 1.4f) - 29.9f) < 1e-3f, "vf at 1.4 A");
    CHECK(fabsf(led_vf(&m, 0.5f) - 27.9f) < 0.1f, "vf at 0.5 A %g", (double)led_vf(&m, 0.5f));
    float prev = 0.0f;
    int mono = 1;
    for (float i = 1e-7f; i < 1.5f; i *= 1.05f) {
        float v = led_vout_target(&m, i);
        if (v < prev) mono = 0;
        prev = v;
    }
    CHECK(mono, "vout target monotonic");
    for (float i = 5e-6f; i < 1.4f; i *= 3.0f) {
        float a = led_current_allowed(&m, led_vout_target(&m, i));
        CHECK(fabsf(a - i) / i < 1e-3f, "allowed inverse at %g: %g", (double)i, (double)a);
    }
    /* the headroom loop: nudge by 10 % of the error each step; it converges on the target */
    float v0 = led_vf(&m, 0.14f), target = v0 + 0.8f;
    for (int n = 0; n < 200; n++)
        led_learn(&m, 0.14f, 0.1f * (target - led_vf(&m, 0.14f)));
    CHECK(fabsf(led_vf(&m, 0.14f) - target) < 0.01f, "learning converges: %g vs %g", (double)led_vf(&m, 0.14f),
          (double)target);
    CHECK(fabsf(led_vf(&m, 5e-6f) - (29.9f + 0.65f * logf(5e-6f / 1.4f) + 1.48f * (5e-6f - 1.4f))) < 1e-3f,
          "learning is local");
}

static void test_params(void)
{
    params_t p;
    params_defaults(&p);
    CHECK(params_valid(&p), "defaults valid");
    p.fallback_b = 0.3f;
    CHECK(!params_valid(&p), "edit detected");
    params_seal(&p);
    CHECK(params_valid(&p), "resealed");
    CHECK(sizeof(params_t) <= 2048, "fits the flash page (%zu bytes)", sizeof(params_t));
}

int main(void)
{
    test_frame();
    test_curve();
    test_channels();
    test_fade();
    test_ledmodel();
    test_params();
    test_fade_chain();
    printf("%d checks, %d failures\n", checks, fails);
    return fails ? 1 : 0;
}
