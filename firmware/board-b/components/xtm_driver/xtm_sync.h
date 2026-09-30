#pragma once

#include "esphome/core/defines.h"

#ifdef USE_ESPNOW

#include "esphome/components/espnow/espnow_component.h"
#include "esphome/core/preferences.h"
#include "sync_core.h"

#include <string>

namespace esphome {
namespace xtm_driver {

class XtmDriver;

/// Carries SyncCore's messages as ESP-NOW broadcasts, each with an 8-byte HMAC-SHA256 tag
/// under the shared key, and keeps the epoch in flash.
class XtmSync : public espnow::ESPNowBroadcastHandler, public espnow::ESPNowUnknownPeerHandler, public SyncHost {
 public:
  XtmSync(XtmDriver *driver, espnow::ESPNowComponent *espnow, const char *key)
      : driver_(driver), espnow_(espnow), key_(key), core_(this) {}

  void setup();
  void poll(uint32_t now) { this->core_.poll(now); }
  SyncCore &core() { return this->core_; }
  uint32_t rejected() const { return this->rejected_; }
  uint32_t send_errors() const { return this->send_errors_; }

  bool on_broadcast(const espnow::ESPNowRecvInfo &info, const uint8_t *data, uint16_t size) override;
  bool on_unknown_peer(const espnow::ESPNowRecvInfo &info, const uint8_t *data, uint16_t size) override;

  void sync_send(const SyncMsg &m) override;
  void sync_apply(uint16_t level, uint32_t fade_ms) override;
  void sync_role_changed(SyncRole role) override;
  void sync_epoch_changed(uint32_t epoch) override;

 protected:
  bool handle_(const espnow::ESPNowRecvInfo &info, const uint8_t *data, uint16_t size);
  void tag_(const uint8_t *body, uint8_t *tag) const;

  XtmDriver *driver_;
  espnow::ESPNowComponent *espnow_;
  std::string key_;
  SyncCore core_;
  ESPPreferenceObject pref_;
  uint32_t rejected_{0};
  uint32_t send_errors_{0};
  uint32_t last_warn_ms_{0};
};

}  // namespace xtm_driver
}  // namespace esphome

#endif  // USE_ESPNOW
