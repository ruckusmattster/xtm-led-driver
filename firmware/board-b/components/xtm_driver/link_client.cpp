#include "link_client.h"

#include <cmath>
#include <cstring>

namespace esphome {
namespace xtm_driver {

uint16_t level_from_brightness(bool on, float brightness) {
  if (!on || !(brightness > 0.0f))
    return 0;
  if (brightness > 1.0f)
    brightness = 1.0f;
  return (uint16_t) (1u + (uint32_t) lroundf(brightness * (float) (LEVEL_SPAN)));
}

float brightness_from_level(uint16_t level) {
  if (level == 0)
    return 0.0f;
  float b = (float) (level - 1u) / (float) LEVEL_SPAN;
  return b > 1e-6f ? b : 1e-6f;  // level 1 is the bottom of the curve, still on
}

uint8_t LinkClient::send_(uint8_t type, const void *payload, size_t len) {
  uint8_t out[LINK_MAX_ENCODED + 4];
  uint8_t seq = this->seq_++;
  size_t n = frame_build(type, seq, payload, len, out, sizeof(out));
  if (n > 0)
    this->host_->link_write(out, n);
  return seq;
}

void LinkClient::send_level_(uint16_t level, uint32_t fade_ms, uint32_t now, const char *why) {
  msg_set_level_t m;
  m.level = level;
  m.fade_ms = fade_ms;
  m.flags = 0;
  this->send_(MSG_SET_LEVEL, &m, sizeof(m));
  this->level_sent_ = true;
  this->level_sent_ms_ = now;
  if (why != nullptr) {
    this->resyncs_++;
    this->host_->on_resync(level, fade_ms, why);
  }
}

void LinkClient::set_level(uint16_t level, uint32_t fade_ms, uint32_t now) {
  bool fading = (int32_t) (this->want_end_ms_ - now) > 20;
  bool same = level == this->want_level_ && fade_ms == 0 && !fading;
  this->want_level_ = level;
  this->want_end_ms_ = now + fade_ms;
  if (!same)
    this->resends_ = 0;
  if (!this->boot_decided_ || same)
    return;  // held until Board A has been heard from, or nothing new
  this->send_level_(level, fade_ms, now, nullptr);
}

void LinkClient::rx_byte(uint8_t byte, uint32_t now) {
  uint8_t f[LINK_MAX_FRAME];
  size_t n = frame_rx_byte(&this->rx_, byte, f, sizeof(f));
  if (n >= 2)
    this->handle_(f, n, now);
}

void LinkClient::handle_(const uint8_t *f, size_t n, uint32_t now) {
  const uint8_t type = f[0];
  const uint8_t *p = f + 2;
  const size_t len = n - 2;
  switch (type) {
    case MSG_STATUS:
      this->handle_status_(p, len, now);
      break;
    case MSG_ACK: {
      if (len < sizeof(msg_ack_t))
        break;
      msg_ack_t a;
      memcpy(&a, p, sizeof(a));
      if (this->in_flight_ && this->q_[this->q_head_].seq == a.seq)
        this->finish_(a.result == RESULT_OK, a.result);
      break;
    }
    case MSG_PARAM: {
      if (len < sizeof(msg_param_t))
        break;
      msg_param_t m;
      memcpy(&m, p, sizeof(m));
      this->host_->on_param(m.id, m.value);
      if (this->in_flight_ && this->q_[this->q_head_].param == (int16_t) m.id)
        this->finish_(true, RESULT_OK);
      break;
    }
    default:
      break;
  }
}

void LinkClient::handle_status_(const uint8_t *p, size_t len, uint32_t now) {
  // Accept the older, shorter STATUS (no level_link) as well; missing fields read as zero.
  if (len < offsetof(msg_status_t, level_link))
    return;
  msg_status_t m;
  memset(&m, 0, sizeof(m));
  memcpy(&m, p, len < sizeof(m) ? len : sizeof(m));

  const bool restarted = this->have_status_ && (uint32_t) m.uptime_s + 1u < this->st_.uptime_s;
  DriverStatus &s = this->st_;
  s.level_target = m.level_target;
  s.level_now = m.level_now;
  s.level_link = m.level_link;
  s.state = m.state;
  s.fault = m.fault;
  s.flags = m.flags;
  s.i_led = m.i_led;
  s.v_led = m.v_led;
  s.v_out = m.v_out;
  s.v_in = m.v_in;
  for (int k = 0; k < 4; k++)
    s.temp_c[k] = (float) m.temp_c10[k] / 10.0f;
  s.fw_version = m.fw_version;
  s.uptime_s = m.uptime_s;

  this->have_status_ = true;
  this->last_status_ms_ = now;
  if (!this->link_up_) {
    this->link_up_ = true;
    this->host_->on_link_change(true);
  }
  if (restarted)
    this->host_->on_board_a_restart();
  if (!this->boot_decided_)
    this->decide_boot_(now);
  else
    this->reconcile_(now, restarted);
  this->host_->on_status(s);
}

void LinkClient::decide_boot_(uint32_t now) {
  this->boot_decided_ = true;
  const DriverStatus &s = this->st_;
  const bool a_was_running = (uint64_t) s.uptime_s * 1000u >= (uint64_t) now + 2000u;
  if (a_was_running) {
    // Board B restarted alone (OTA, crash, power glitch on USB): keep what Board A is doing.
    this->want_level_ = s.level_link;
    this->want_end_ms_ = now;
    this->host_->on_adopt(s.level_link);
    if (s.flags & LFLAG_FALLBACK)
      this->send_level_(s.level_link, this->resync_fade_ms_, now, "restoring the level from before the link loss");
  } else if (this->want_level_ != 0 || s.level_link != 0 || s.level_target != 0) {
    // Both boards starting together: the light's restored state, with a gentle fade.
    this->send_level_(this->want_level_, this->resync_fade_ms_, now, nullptr);
  }
}

void LinkClient::reconcile_(uint32_t now, bool restarted) {
  if (restarted)
    this->resends_ = 0;
  uint32_t quiet = this->resends_ < RESENDS_FAST ? QUIET_AFTER_SEND_MS : RESEND_SLOW_MS;
  if (this->level_sent_ && now - this->level_sent_ms_ < quiet)
    return;  // Board A hasn't had time to answer the last one yet
  const DriverStatus &s = this->st_;
  const bool needed = restarted || (s.flags & LFLAG_FALLBACK) || s.level_link != this->want_level_;
  if (!needed) {
    this->resends_ = 0;
    return;
  }
  if (this->resends_ < 255)
    this->resends_++;
  if (restarted) {
    this->send_level_(this->want_level_, this->resync_fade_ms_, now, "Board A restarted");
  } else if (s.flags & LFLAG_FALLBACK) {
    this->send_level_(this->want_level_, this->resync_fade_ms_, now, "Board A fell back after losing the link");
  } else if (s.level_link != this->want_level_) {
    int32_t left = (int32_t) (this->want_end_ms_ - now);
    uint32_t fade = left > 0 ? (uint32_t) left : 0u;
    if (s.level_link == 0 && fade < this->resync_fade_ms_)
      fade = this->resync_fade_ms_;  // Board A was reset or powered up since it last heard from us
    this->send_level_(this->want_level_, fade, now, "Board A missed a level");
  }
}

void LinkClient::poll(uint32_t now) {
  if (this->link_up_ && now - this->last_status_ms_ > this->timeout_ms_) {
    this->link_up_ = false;
    this->host_->on_link_change(false);
  }
  if (!this->pinged_ || now - this->last_ping_ms_ >= this->ping_ms_) {
    this->send_(MSG_PING, nullptr, 0);  // the first one at once, so Board A knows we're here
    this->last_ping_ms_ = now;
    this->pinged_ = true;
  }
  this->pump_(now);
}

void LinkClient::hold(uint16_t seconds) {
  msg_hold_t m;
  m.seconds = seconds;
  this->send_(MSG_HOLD, &m, sizeof(m));
  this->send_(MSG_HOLD, &m, sizeof(m));
}

void LinkClient::clear_fault() { this->queue_(MSG_CLEAR_FAULT, nullptr, 0, -1); }

void LinkClient::identify(uint8_t count) {
  msg_identify_t m;
  m.count = count;
  this->queue_(MSG_IDENTIFY, &m, sizeof(m), -1);
}

void LinkClient::set_param(uint8_t id, float value, bool save) {
  msg_set_param_t m;
  m.id = id;
  m.value = value;
  m.save = save ? 1 : 0;
  this->queue_(MSG_SET_PARAM, &m, sizeof(m), id);
}

void LinkClient::get_param(uint8_t id) {
  msg_get_param_t m;
  m.id = id;
  this->queue_(MSG_GET_PARAM, &m, sizeof(m), id);
}

void LinkClient::queue_(uint8_t type, const void *payload, uint8_t len, int16_t param) {
  // A newer value for the same parameter replaces one still waiting (a slider being dragged).
  for (size_t i = 0; i < this->q_count_; i++) {
    size_t k = (this->q_head_ + i) % QLEN;
    if (i == 0 && this->in_flight_)
      continue;
    Cmd &c = this->q_[k];
    if (c.type == type && c.param == param && (param >= 0 || type == MSG_IDENTIFY)) {
      if (len > 0)
        memcpy(c.payload, payload, len);
      return;
    }
  }
  if (this->q_count_ == QLEN) {
    this->failed_++;
    this->host_->on_command_failed(type, 0xFF);
    return;
  }
  Cmd &c = this->q_[(this->q_head_ + this->q_count_) % QLEN];
  c.type = type;
  c.len = len;
  if (len > 0)
    memcpy(c.payload, payload, len);
  c.param = param;
  c.seq = 0;
  c.tries = 0;
  this->q_count_++;
}

void LinkClient::pump_(uint32_t now) {
  if (this->q_count_ == 0)
    return;
  Cmd &c = this->q_[this->q_head_];
  if (this->in_flight_) {
    if (now - this->sent_ms_ < RETRY_MS)
      return;
    if (c.tries >= TRIES) {
      this->finish_(false, 0xFF);
      return;
    }
  }
  c.seq = this->send_(c.type, c.len ? c.payload : nullptr, c.len);
  c.tries++;
  this->in_flight_ = true;
  this->sent_ms_ = now;
}

void LinkClient::finish_(bool ok, uint8_t result) {
  uint8_t type = this->q_[this->q_head_].type;
  this->q_head_ = (this->q_head_ + 1) % QLEN;
  this->q_count_--;
  this->in_flight_ = false;
  if (!ok) {
    this->failed_++;
    this->host_->on_command_failed(type, result);
  }
}

}  // namespace xtm_driver
}  // namespace esphome
