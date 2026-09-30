#include "link.h"
#include "config.h"
#include "control.h"
#include "frame.h"
#include "hw.h"
#include "link_protocol.h"
#include "settings.h"
#include <string.h>

static struct {
    frame_rx_t rx;
    uint32_t last_rx_ms, last_tx_ms, hold_until_ms;
    uint8_t seq;
    int ever_connected, lost, fallback;
    uint16_t level_link;
} L;

void link_init(void)
{
    memset(&L, 0, sizeof(L));
    L.last_rx_ms = L.last_tx_ms = hw_millis();
}

static void send(uint8_t type, const void *payload, size_t len)
{
    uint8_t out[LINK_MAX_ENCODED + 4];
    size_t n = frame_build(type, L.seq++, payload, len, out, sizeof(out));
    if (n)
        hw_link_write(out, n);
}

static void send_status(void)
{
    msg_status_t s;
    control_status(&s);
    if (L.lost)
        s.flags |= LFLAG_LINK_LOST;
    if ((int32_t)(L.hold_until_ms - hw_millis()) > 0)
        s.flags |= LFLAG_HOLD;
    if (L.fallback)
        s.flags |= LFLAG_FALLBACK;
    s.level_link = L.level_link;
    send(MSG_STATUS, &s, sizeof(s));
    L.last_tx_ms = hw_millis();
}

static void ack(uint8_t seq, uint8_t result)
{
    msg_ack_t a = { seq, result };
    send(MSG_ACK, &a, sizeof(a));
}

static void handle(const uint8_t *f, size_t n)
{
    uint8_t type = f[0], seq = f[1];
    const uint8_t *pl = f + 2;
    size_t len = n - 2;
    params_t *p = NULL;
    switch (type) {
    case MSG_SET_LEVEL: {
        msg_set_level_t m;
        if (len != sizeof(m)) { ack(seq, RESULT_BAD_FRAME); return; }
        memcpy(&m, pl, sizeof(m));
        uint32_t fade = m.fade_ms > 3600000u ? 3600000u : m.fade_ms;
        L.level_link = m.level;
        L.fallback = 0;
        control_level(m.level, fade);
        send_status();
        break;
    }
    case MSG_PING:
        send_status();
        break;
    case MSG_HOLD: {
        msg_hold_t m;
        if (len != sizeof(m)) { ack(seq, RESULT_BAD_FRAME); return; }
        memcpy(&m, pl, sizeof(m));
        uint32_t s = m.seconds > LINK_HOLD_MAX_S ? LINK_HOLD_MAX_S : m.seconds;
        L.hold_until_ms = hw_millis() + s * 1000u;
        ack(seq, RESULT_OK);
        break;
    }
    case MSG_CLEAR_FAULT:
        control_clear_fault();
        ack(seq, RESULT_OK);
        break;
    case MSG_SET_PARAM: {
        msg_set_param_t m;
        if (len != sizeof(m)) { ack(seq, RESULT_BAD_FRAME); return; }
        memcpy(&m, pl, sizeof(m));
        p = app_params();
        if (settings_set(p, m.id, m.value) != 0) { ack(seq, RESULT_BAD_PARAM); return; }
        control_apply_params();
        if (m.save)
            control_request_save();
        float v = 0.0f;
        settings_get(p, m.id, &v);
        msg_param_t r = { m.id, v };
        send(MSG_PARAM, &r, sizeof(r));
        break;
    }
    case MSG_GET_PARAM: {
        msg_get_param_t m;
        if (len != sizeof(m)) { ack(seq, RESULT_BAD_FRAME); return; }
        memcpy(&m, pl, sizeof(m));
        float v = 0.0f;
        if (settings_get(app_params(), m.id, &v) != 0) { ack(seq, RESULT_BAD_PARAM); return; }
        msg_param_t r = { m.id, v };
        send(MSG_PARAM, &r, sizeof(r));
        break;
    }
    case MSG_IDENTIFY: {
        msg_identify_t m;
        if (len != sizeof(m)) { ack(seq, RESULT_BAD_FRAME); return; }
        memcpy(&m, pl, sizeof(m));
        control_identify(m.count > 10 ? 10 : m.count);
        ack(seq, RESULT_OK);
        break;
    }
    default:
        ack(seq, RESULT_BAD_FRAME);
        break;
    }
}

void link_poll(void)
{
    uint8_t f[LINK_MAX_FRAME];
    int c;
    while ((c = hw_link_getc()) >= 0) {
        size_t n = frame_rx_byte(&L.rx, (uint8_t)c, f, sizeof(f));
        if (n >= 2) {
            L.last_rx_ms = hw_millis();
            L.ever_connected = 1;
            L.lost = 0;
            handle(f, n);
        }
    }
    uint32_t now = hw_millis();
    uint32_t timeout_ms = (uint32_t)(app_params()->link_timeout_s * 1000.0f);
    if (L.ever_connected && !L.lost && now - L.last_rx_ms > timeout_ms &&
        (int32_t)(L.hold_until_ms - now) <= 0) {
        L.lost = 1;
        L.fallback = 1;
        control_link_lost();
    }
    if (now - L.last_tx_ms >= LINK_STATUS_MS)
        send_status();
}

int link_is_lost(void) { return L.lost; }
uint32_t link_bad_frames(void) { return L.rx.bad; }
