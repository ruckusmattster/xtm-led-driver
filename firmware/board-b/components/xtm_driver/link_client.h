/*
 * Board B side of the Board A link, free of ESPHome so it can be tested on a PC.
 *
 * Level ownership: Board B decides what the light should do. It sends a level whenever the
 * light's target changes and otherwise leaves Board A alone. It re-sends only when STATUS
 * shows Board A missed or lost that level:
 *   - level_link differs from the wanted level (a SET_LEVEL was lost on the wire),
 *   - Board A restarted (uptime went backwards, level_link back to 0),
 *   - Board A dropped to its link-loss fallback (LFLAG_FALLBACK).
 * A level set on Board A's console changes neither level_link nor the flag, so it stands.
 *
 * Start-up: the light's restored state is held back until the first STATUS arrives. If
 * Board A has been running longer than Board B (Board B rebooted alone), Board B adopts
 * Board A's level_link, the last level it asked for, so an OTA update or a crash of the
 * ESP32 never changes the light. Otherwise the restored state is sent with a gentle fade.
 */
#pragma once

#include <cstddef>
#include <cstdint>

#include "xtm_wire.h"

namespace esphome {
namespace xtm_driver {

static constexpr uint32_t LEVEL_SPAN = 65534;  // levels 1..65535 cover brightness 0..1

struct DriverStatus {
  uint16_t level_target{0};
  uint16_t level_now{0};
  uint16_t level_link{0};
  uint8_t state{LSTATE_BOOT};
  uint8_t fault{LFAULT_NONE};
  uint16_t flags{0};
  float i_led{0.0f};
  float v_led{0.0f};
  float v_out{0.0f};
  float v_in{0.0f};
  float temp_c[4]{0.0f, 0.0f, 0.0f, 0.0f};
  uint16_t fw_version{0};
  uint32_t uptime_s{0};
};

class LinkHost {
 public:
  virtual ~LinkHost() = default;
  virtual void link_write(const uint8_t *data, size_t len) = 0;
  virtual void on_status(const DriverStatus & /*status*/) {}
  virtual void on_param(uint8_t /*id*/, float /*value*/) {}
  virtual void on_link_change(bool /*up*/) {}
  /// Board B has just started and Board A was already running: show this level without sending it.
  virtual void on_adopt(uint16_t /*level*/) {}
  virtual void on_board_a_restart() {}
  virtual void on_command_failed(uint8_t /*type*/, uint8_t /*result*/) {}
  virtual void on_resync(uint16_t /*level*/, uint32_t /*fade_ms*/, const char * /*why*/) {}
};

class LinkClient {
 public:
  explicit LinkClient(LinkHost *host) : host_(host) {}

  void set_timing(uint32_t ping_ms, uint32_t timeout_ms, uint32_t resync_fade_ms) {
    this->ping_ms_ = ping_ms;
    this->timeout_ms_ = timeout_ms;
    this->resync_fade_ms_ = resync_fade_ms;
  }

  void rx_byte(uint8_t byte, uint32_t now);
  void poll(uint32_t now);

  /// The light's target: go to `level` (0 = off) over `fade_ms`.
  void set_level(uint16_t level, uint32_t fade_ms, uint32_t now);

  /// Sent at once, twice, not queued: used just before a planned reboot, when the loop stops.
  void hold(uint16_t seconds);
  void clear_fault();
  void identify(uint8_t count);
  void set_param(uint8_t id, float value, bool save);
  void get_param(uint8_t id);

  bool link_up() const { return this->link_up_; }
  bool has_status() const { return this->have_status_; }
  bool boot_decided() const { return this->boot_decided_; }
  const DriverStatus &status() const { return this->st_; }
  uint16_t wanted_level() const { return this->want_level_; }
  uint32_t bad_frames() const { return this->rx_.bad; }
  uint32_t resyncs() const { return this->resyncs_; }
  uint32_t failed_commands() const { return this->failed_; }

  static constexpr uint32_t RETRY_MS = 250;
  static constexpr uint8_t TRIES = 3;
  static constexpr uint32_t QUIET_AFTER_SEND_MS = 300;
  static constexpr uint8_t RESENDS_FAST = 4;  // then one try every RESEND_SLOW_MS
  static constexpr uint32_t RESEND_SLOW_MS = 5000;

 protected:
  struct Cmd {
    uint8_t type;
    uint8_t len;
    uint8_t payload[8];
    int16_t param;  // id a PARAM reply must carry, -1 if the command is answered by ACK
    uint8_t seq;
    uint8_t tries;
  };
  static constexpr size_t QLEN = 8;

  uint8_t send_(uint8_t type, const void *payload, size_t len);
  void send_level_(uint16_t level, uint32_t fade_ms, uint32_t now, const char *why);
  void handle_(const uint8_t *f, size_t n, uint32_t now);
  void handle_status_(const uint8_t *p, size_t len, uint32_t now);
  void decide_boot_(uint32_t now);
  void reconcile_(uint32_t now, bool restarted);
  void queue_(uint8_t type, const void *payload, uint8_t len, int16_t param);
  void pump_(uint32_t now);
  void finish_(bool ok, uint8_t result);

  LinkHost *host_;
  frame_rx_t rx_{};
  DriverStatus st_{};
  bool have_status_{false};
  bool link_up_{false};
  bool boot_decided_{false};
  uint32_t last_status_ms_{0};
  uint32_t last_ping_ms_{0};
  bool pinged_{false};
  uint32_t ping_ms_{200};
  uint32_t timeout_ms_{1000};
  uint32_t resync_fade_ms_{1000};
  uint8_t seq_{0};

  uint16_t want_level_{0};
  uint32_t want_end_ms_{0};  // when the wanted fade ends
  bool level_sent_{false};
  uint32_t level_sent_ms_{0};
  uint32_t resyncs_{0};
  uint8_t resends_{0};  // re-sends of the present wanted level; backs off after a few

  Cmd q_[QLEN]{};
  size_t q_head_{0};
  size_t q_count_{0};
  bool in_flight_{false};
  uint32_t sent_ms_{0};
  uint32_t failed_{0};
};

/// Level (0 = off, 1..65535) for a brightness position; the same mapping Board A uses.
uint16_t level_from_brightness(bool on, float brightness);
float brightness_from_level(uint16_t level);

}  // namespace xtm_driver
}  // namespace esphome
