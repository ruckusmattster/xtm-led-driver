#include "xtm_driver.h"
#include "xtm_entities.h"
#include "xtm_light.h"
#include "xtm_sync.h"

#include "esphome/core/log.h"
#ifdef USE_WIFI
#include "esphome/components/wifi/wifi_component.h"
#endif

#include <cinttypes>
#include <cmath>
#include <cstdio>

namespace esphome {
namespace xtm_driver {

static const char *const TAG = "xtm_driver";

const char *state_name(uint8_t state) {
  switch (state) {
    case LSTATE_BOOT:
      return "starting up";
    case LSTATE_OFF:
      return "off";
    case LSTATE_ON:
      return "on";
    case LSTATE_FAULT:
      return "fault";
    case LSTATE_STARTING:
      return "turning on";
    case LSTATE_TAIL:
      return "fading out";
    default:
      return "unknown";
  }
}

const char *fault_name(uint8_t fault) {
  switch (fault) {
    case LFAULT_NONE:
      return "none";
    case LFAULT_SHORT:
      return "LED short";
    case LFAULT_OPEN:
      return "LED open";
    case LFAULT_OVERTEMP:
      return "over temperature";
    case LFAULT_UNDERVOLT:
      return "48 V low";
    case LFAULT_DAC:
      return "DAC";
    case LFAULT_BUCK:
      return "buck";
    default:
      return "unknown";
  }
}

// ---------------------------------------------------------------- lifecycle

void XtmDriver::setup() {
  if (this->boot0_pin_ != nullptr) {
    this->boot0_pin_->setup();
    this->boot0_pin_->digital_write(false);  // Board A boots its own firmware
  }
  if (this->nrst_pin_ != nullptr) {
    this->nrst_pin_->setup();
    this->nrst_pin_->digital_write(true);  // open drain: released
  }
  this->link_.set_timing(this->ping_ms_, this->timeout_ms_, this->resync_ms_);
#ifdef USE_ESPNOW
  if (this->sync_ != nullptr)
    this->sync_->setup();
#endif
  this->publish_text_(TEXT_SYNC_ROLE, sync_role_name(this->sync_role()));
  this->publish_binary_(BINARY_LINK, false);
}

void XtmDriver::loop() {
  const uint32_t now = millis();
  uint8_t buf[64];
  size_t avail;
  while ((avail = this->available()) > 0) {
    size_t n = avail < sizeof(buf) ? avail : sizeof(buf);
    if (!this->read_array(buf, n))
      break;
    for (size_t i = 0; i < n; i++)
      this->link_.rx_byte(buf[i], now);
  }
  this->link_.poll(now);
#ifdef USE_ESPNOW
  if (this->sync_ != nullptr)
    this->sync_->poll(now);
#endif
  if (now - this->last_publish_ms_ >= this->update_ms_) {
    this->last_publish_ms_ = now;
    this->publish_measurements_();
  }
  this->update_leds_(now);
}

void XtmDriver::dump_config() {
  ESP_LOGCONFIG(TAG, "XTM driver (Board A link):");
  LOG_PIN("  BOOT0 pin: ", this->boot0_pin_);
  LOG_PIN("  NRST pin: ", this->nrst_pin_);
  ESP_LOGCONFIG(TAG,
                "  Ping every %" PRIu32 " ms, link lost after %" PRIu32 " ms, re-sync fade %" PRIu32 " ms\n"
                "  Encoder: step %.3f, minimum %.3f, transition %" PRIu32 " ms",
                this->ping_ms_, this->timeout_ms_, this->resync_ms_, this->enc_step_, this->enc_min_,
                this->enc_transition_ms_);
  ESP_LOGCONFIG(TAG, "  Sync: %s", this->sync_ != nullptr ? "ESP-NOW" : "not configured");
}

void XtmDriver::on_shutdown() {
  // A planned reboot (OTA, restart button): keep Board A from treating the silence as a lost
  // link. The ESP32 is back well inside 30 s; Board A resumes normal checks on the first frame.
  this->link_.hold(30);
  this->flush();
}

// ---------------------------------------------------------------- UART link

void XtmDriver::link_write(const uint8_t *data, size_t len) { this->write_array(data, len); }

void XtmDriver::on_link_change(bool up) {
  this->publish_binary_(BINARY_LINK, up);
  if (up) {
    const DriverStatus &s = this->link_.status();
    ESP_LOGI(TAG, "Board A link up (firmware %u.%u, running %" PRIu32 " s)", s.fw_version >> 8, s.fw_version & 0xFF,
             s.uptime_s);
    this->request_params_();
  } else {
    ESP_LOGW(TAG, "Board A link lost: no STATUS for %" PRIu32 " ms", this->timeout_ms_);
  }
  this->publish_measurements_();
}

void XtmDriver::request_params_() {
#ifdef USE_NUMBER
  for (auto *n : this->numbers_)
    this->link_.get_param(n->param_id());
#endif
#ifdef USE_SENSOR
  if (this->sensors_[SENSOR_FULL_SCALE_LUX] != nullptr)
    this->link_.get_param(PARAM_LUX_AT_MAX);
#endif
}

void XtmDriver::on_status(const DriverStatus &st) {
  if (st.state != this->last_state_) {
    this->last_state_ = st.state;
    this->publish_text_(TEXT_STATE, state_name(st.state));
  }
  if (st.fault != this->last_fault_) {
    this->last_fault_ = st.fault;
    this->publish_text_(TEXT_FAULT, fault_name(st.fault));
    if (st.fault != LFAULT_NONE)
      ESP_LOGW(TAG, "Board A fault: %s", fault_name(st.fault));
  }
  if (st.flags != this->last_flags_) {
    this->last_flags_ = st.flags;
    this->publish_binary_(BINARY_DERATING, (st.flags & LFLAG_DERATING) != 0);
    this->publish_binary_(BINARY_CALIBRATED, (st.flags & LFLAG_CALIBRATED) != 0);
    this->publish_binary_(BINARY_LIGHT_MATCHED, (st.flags & LFLAG_LUX_MATCH) != 0);
  }
  if (st.fw_version != this->last_fw_) {
    this->last_fw_ = st.fw_version;
    char buf[12];
    snprintf(buf, sizeof(buf), "%u.%u", st.fw_version >> 8, st.fw_version & 0xFF);
    this->publish_text_(TEXT_FIRMWARE, buf);
  }
}

void XtmDriver::on_param(uint8_t id, float value) {
#ifdef USE_NUMBER
  for (auto *n : this->numbers_) {
    if (n->param_id() == id)
      n->publish_state(value / n->scale());
  }
#endif
#ifdef USE_SENSOR
  if (id == PARAM_LUX_AT_MAX && this->sensors_[SENSOR_FULL_SCALE_LUX] != nullptr)
    this->sensors_[SENSOR_FULL_SCALE_LUX]->publish_state(value > 0.0f ? value : NAN);
#endif
}

void XtmDriver::on_adopt(uint16_t level) {
  ESP_LOGI(TAG, "Board A was already running: keeping its level %u", level);
  this->set_light_quietly_(level, 0);
}

void XtmDriver::on_board_a_restart() { ESP_LOGW(TAG, "Board A restarted"); }

void XtmDriver::on_command_failed(uint8_t type, uint8_t result) {
  if (result == 0xFF)
    ESP_LOGW(TAG, "Board A did not answer command 0x%02X", type);
  else
    ESP_LOGW(TAG, "Board A refused command 0x%02X (result %u)", type, result);
}

void XtmDriver::on_resync(uint16_t level, uint32_t fade_ms, const char *why) {
  ESP_LOGI(TAG, "Sent level %u again over %" PRIu32 " ms: %s", level, fade_ms, why);
}

// ---------------------------------------------------------------- publishing

void XtmDriver::publish_text_(uint8_t kind, const char *value) {
#ifdef USE_TEXT_SENSOR
  if (kind < TEXT_COUNT && this->texts_[kind] != nullptr)
    this->texts_[kind]->publish_state(value);
#endif
}

void XtmDriver::publish_binary_(uint8_t kind, bool value) {
#ifdef USE_BINARY_SENSOR
  if (kind < BINARY_COUNT && this->binaries_[kind] != nullptr)
    this->binaries_[kind]->publish_state(value);
#endif
}

void XtmDriver::publish_measurements_() {
#ifdef USE_SENSOR
  const bool up = this->link_.link_up();
  const DriverStatus &s = this->link_.status();
  auto pub = [this, up](uint8_t kind, float value) {
    if (this->sensors_[kind] != nullptr)
      this->sensors_[kind]->publish_state(up ? value : NAN);
  };
  pub(SENSOR_LED_CURRENT, s.i_led);
  pub(SENSOR_LED_VOLTAGE, s.v_led > 0.0f ? s.v_led : NAN);  // 0 means not measurable (dark, or sink saturated)
  pub(SENSOR_OUTPUT_VOLTAGE, s.v_out);
  pub(SENSOR_INPUT_VOLTAGE, s.v_in);
  pub(SENSOR_TEMP_FET, s.temp_c[0]);
  pub(SENSOR_TEMP_BUCK, s.temp_c[1]);
  pub(SENSOR_TEMP_AUX, s.temp_c[2]);
  pub(SENSOR_TEMP_PRECISION, s.temp_c[3]);
  pub(SENSOR_BOARD_A_UPTIME, (float) s.uptime_s);
  if (this->sensors_[SENSOR_LINK_ERRORS] != nullptr)
    this->sensors_[SENSOR_LINK_ERRORS]->publish_state((float) (this->link_.bad_frames() + this->link_.failed_commands()));
#endif
}

// ---------------------------------------------------------------- the light

light::LightState *XtmDriver::light_state() const {
  return this->light_ != nullptr ? this->light_->get_state() : nullptr;
}

void XtmDriver::light_target(uint16_t level, uint32_t fade_ms) {
  const uint32_t now = millis();
  bool local = true;
  if (this->expect_active_ && level == this->expect_level_ && now - this->expect_ms_ < 1000) {
    local = false;  // made by sync or at start-up, not by someone at this fixture
    this->expect_active_ = false;
  }
  const bool running = (int32_t) (this->target_end_ms_ - now) > 20;
  const bool changed = level != this->target_level_ || fade_ms != 0 || running;
  this->target_level_ = level;
  this->target_end_ms_ = now + fade_ms;
  this->link_.set_level(level, fade_ms, now);
  if (!changed)
    return;
  ESP_LOGD(TAG, "Level %u over %" PRIu32 " ms%s", level, fade_ms, local ? "" : " (sync or start-up)");
#ifdef USE_ESPNOW
  if (this->sync_ != nullptr)
    this->sync_->core().on_target(level, fade_ms, local, now);
#endif
}

void XtmDriver::set_light_quietly_(uint16_t level, uint32_t fade_ms) {
  auto *ls = this->light_state();
  if (ls == nullptr)
    return;
  this->expect_active_ = true;
  this->expect_level_ = level;
  this->expect_ms_ = millis();
  auto call = ls->make_call();
  if (level == 0) {
    call.set_state(false);
  } else {
    call.set_state(true);
    call.set_brightness(brightness_from_level(level));
  }
  call.set_transition_length(fade_ms);
  call.perform();
}

void XtmDriver::encoder_step(int direction) {
  auto *ls = this->light_state();
  if (ls == nullptr || direction == 0)
    return;
  const uint32_t now = millis();
  const uint32_t dt = now - this->enc_last_ms_;
  this->enc_last_ms_ = now;
  float step = this->enc_step_;
  if (dt < 40)
    step *= 4.0f;  // spun fast
  else if (dt < 80)
    step *= 2.0f;
  const auto &remote = ls->remote_values;
  const auto &current = ls->current_values;
  float b;
  if (dt < 400 && remote.is_on()) {
    b = remote.get_brightness() + (float) direction * step;  // mid-turn: build on the last detent
  } else if (current.is_on()) {
    b = current.get_brightness() + (float) direction * step;  // from where the light is now, even mid-fade
  } else if (remote.is_on()) {
    b = remote.get_brightness() + (float) direction * step;
  } else {
    if (direction < 0)
      return;  // turning down while off does nothing
    b = this->enc_min_;  // turning up from off starts at the bottom
  }
  if (b < this->enc_min_)
    b = this->enc_min_;  // the knob never switches off; the push does
  if (b > 1.0f)
    b = 1.0f;
  auto call = ls->make_call();
  call.set_state(true);
  call.set_brightness(b);
  call.set_transition_length(this->enc_transition_ms_);
  call.perform();
}

// ---------------------------------------------------------------- sync

SyncRole XtmDriver::sync_role() const {
#ifdef USE_ESPNOW
  if (this->sync_ != nullptr)
    return this->sync_->core().role();
#endif
  return SyncRole::INDEPENDENT;
}

void XtmDriver::sync_press() {
#ifdef USE_ESPNOW
  if (this->sync_ != nullptr) {
    this->sync_->core().press(millis());
    return;
  }
#endif
  ESP_LOGW(TAG, "Sync pressed, but sync is not configured");
}

void XtmDriver::set_sync_lead(bool lead) {
#ifdef USE_ESPNOW
  if (this->sync_ != nullptr) {
    this->sync_->core().set_lead(lead, millis());
    return;
  }
#endif
  ESP_LOGW(TAG, "Sync is not configured");
#ifdef USE_SWITCH
  if (this->sync_switch_ != nullptr)
    this->sync_switch_->publish_state(false);
#endif
}

void XtmDriver::apply_sync_level(uint16_t level, uint32_t fade_ms) {
  if (level == this->target_level_)
    return;  // already there or on the way
  this->set_light_quietly_(level, fade_ms);
}

void XtmDriver::on_sync_role(SyncRole role) {
  ESP_LOGI(TAG, "Sync: %s", sync_role_name(role));
  this->publish_text_(TEXT_SYNC_ROLE, sync_role_name(role));
#ifdef USE_SWITCH
  if (this->sync_switch_ != nullptr)
    this->sync_switch_->publish_state(role == SyncRole::OWNER);
#endif
}

// ---------------------------------------------------------------- commands

void XtmDriver::hold(uint16_t seconds) {
  ESP_LOGD(TAG, "Asking Board A to ignore link silence for %u s", seconds);
  this->link_.hold(seconds);
}

void XtmDriver::identify(uint8_t count) { this->link_.identify(count); }

void XtmDriver::clear_fault() { this->link_.clear_fault(); }

void XtmDriver::set_param(uint8_t id, float value, bool save) { this->link_.set_param(id, value, save); }

void XtmDriver::restart_board_a() {
  if (this->nrst_pin_ == nullptr) {
    ESP_LOGW(TAG, "No nrst_pin configured");
    return;
  }
  ESP_LOGW(TAG, "Restarting Board A");
  if (this->boot0_pin_ != nullptr)
    this->boot0_pin_->digital_write(false);
  this->nrst_pin_->digital_write(false);
  delay(20);
  this->nrst_pin_->digital_write(true);
}

// ---------------------------------------------------------------- status LED

void XtmDriver::update_leds_(uint32_t now) {
  if (this->led_[0] == nullptr || this->led_[1] == nullptr || this->led_[2] == nullptr)
    return;
  if (now - this->led_last_ms_ < 20)
    return;
  this->led_last_ms_ = now;
  float c[3] = {0.0f, 0.0f, 0.0f};  // red, green, blue
  const SyncRole role = this->sync_role();
  bool wifi_ok = true;
#ifdef USE_WIFI
  if (wifi::global_wifi_component != nullptr)
    wifi_ok = wifi::global_wifi_component->is_connected();
#endif
  if (now < 2000) {
    c[1] = 1.0f;  // just started
  } else if (!this->link_.link_up()) {
    c[0] = (now % 1000) < 500 ? 1.0f : 0.0f;  // no Board A: slow red
  } else if (this->link_.status().state == LSTATE_FAULT) {
    c[0] = (now % 250) < 125 ? 1.0f : 0.0f;  // fault: fast red
  } else if (role == SyncRole::OWNER) {
    c[2] = 1.0f;  // leading the group: steady blue
  } else if (role == SyncRole::FOLLOWER) {
    c[2] = (now % 1000) < 150 ? 1.0f : 0.0f;  // following: blue blip
  } else if (!wifi_ok) {
    c[0] = c[1] = (now % 3000) < 100 ? 1.0f : 0.0f;  // no Wi-Fi: amber blip
  }
  for (int k = 0; k < 3; k++) {
    float v = c[k] * this->led_brightness_;
    if (v != this->led_last_[k]) {
      this->led_[k]->set_level(v);
      this->led_last_[k] = v;
    }
  }
}

}  // namespace xtm_driver
}  // namespace esphome
