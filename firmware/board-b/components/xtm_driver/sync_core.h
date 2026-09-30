/*
 * Fixture group sync, free of ESPHome so it can be tested on a PC.
 *
 * Pressing the sync button on a fixture makes it the owner: every other fixture follows its
 * level. Pressing it on another fixture moves ownership there. Pressing it on the owner ends
 * the group; every fixture keeps its level. Adjusting a follower locally (knob, button, Home
 * Assistant) takes that one fixture out of the group.
 *
 * Messages are ESP-NOW broadcasts: STATE (the owner's target level and remaining fade time,
 * on every change, repeated after 100 and 300 ms, and once a second as a heartbeat) and
 * RELEASE (the group has ended). Each claim or release starts a new epoch, one above the
 * highest this fixture has seen and saved, so a later claim always beats an earlier one and
 * old packets are ignored. Two claims in the same epoch (pressed within milliseconds of each
 * other) resolve to the higher MAC address. Followers drop out after 5 s without a heartbeat.
 * The ESP-NOW glue appends and checks an HMAC so only fixtures sharing the key take part.
 */
#pragma once

#include <cstddef>
#include <cstdint>

namespace esphome {
namespace xtm_driver {

enum class SyncRole : uint8_t { INDEPENDENT = 0, OWNER = 1, FOLLOWER = 2 };
const char *sync_role_name(SyncRole role);

static constexpr uint8_t SYNC_STATE = 1;
static constexpr uint8_t SYNC_RELEASE = 2;
static constexpr uint8_t SYNC_VERSION = 1;
static constexpr size_t SYNC_BODY_LEN = 22;
static constexpr size_t SYNC_TAG_LEN = 8;
static constexpr size_t SYNC_PACKET_LEN = SYNC_BODY_LEN + SYNC_TAG_LEN;

struct SyncMsg {
  uint8_t type{0};
  uint32_t epoch{0};
  uint8_t owner[6]{};
  uint16_t seq{0};
  uint16_t level{0};  // the owner's target level, 0 = off
  uint32_t fade_ms{0};  // time left in the owner's fade
};

/// Little-endian body: "XS", version, type, epoch, owner MAC, seq, level, fade (22 bytes).
void sync_encode_body(const SyncMsg &m, uint8_t *out);
bool sync_decode_body(const uint8_t *in, size_t len, SyncMsg *m);

class SyncHost {
 public:
  virtual ~SyncHost() = default;
  virtual void sync_send(const SyncMsg &m) = 0;
  /// Follower: set the light to the owner's level (not a local change).
  virtual void sync_apply(uint16_t level, uint32_t fade_ms) = 0;
  virtual void sync_role_changed(SyncRole /*role*/) {}
  /// Save it: the next claim after a restart must still beat every earlier one.
  virtual void sync_epoch_changed(uint32_t /*epoch*/) {}
};

class SyncCore {
 public:
  explicit SyncCore(SyncHost *host) : host_(host) {}

  void set_self(const uint8_t mac[6]);
  void set_epoch(uint32_t epoch) { this->epoch_ = epoch; }

  void press(uint32_t now);
  void set_lead(bool lead, uint32_t now);
  /// Every change of the light's target. `local` is false for changes made by sync_apply().
  void on_target(uint16_t level, uint32_t fade_ms, bool local, uint32_t now);
  void receive(const SyncMsg &m, uint32_t now);
  void poll(uint32_t now);

  SyncRole role() const { return this->role_; }
  uint32_t epoch() const { return this->epoch_; }
  const uint8_t *owner() const { return this->owner_; }

  static constexpr uint32_t HEARTBEAT_MS = 1000;
  static constexpr uint32_t OWNER_TIMEOUT_MS = 5000;
  static constexpr uint32_t REPEAT_MS[2] = {100, 300};

 protected:
  void claim_(uint32_t now);
  void release_(uint32_t now);
  void follow_(const SyncMsg &m, uint32_t now);
  void send_state_(uint32_t now);
  void send_release_();
  void repeat_(uint8_t type, uint32_t now);
  void set_role_(SyncRole role);
  void set_epoch_(uint32_t epoch);

  SyncHost *host_;
  uint8_t self_[6]{};
  SyncRole role_{SyncRole::INDEPENDENT};
  uint32_t epoch_{0};
  bool detached_{false};  // left the group of `epoch_` on purpose: don't rejoin it
  uint8_t owner_[6]{};
  uint16_t seq_{0};
  uint32_t last_rx_ms_{0};
  uint32_t next_hb_ms_{0};
  uint32_t release_epoch_{0};
  uint8_t repeat_type_{0};
  bool repeat_pending_[2]{false, false};
  uint32_t repeat_at_[2]{0, 0};
  uint16_t target_level_{0};
  uint32_t target_end_ms_{0};
  bool applied_{false};
  uint16_t applied_level_{0};
};

}  // namespace xtm_driver
}  // namespace esphome
