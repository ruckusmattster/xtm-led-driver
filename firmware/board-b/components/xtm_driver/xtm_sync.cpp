#include "xtm_sync.h"

#ifdef USE_ESPNOW

#include "esphome/components/espnow/espnow_packet.h"
#include "esphome/components/hmac_sha256/hmac_sha256.h"
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"
#include "xtm_driver.h"

#include <cstring>

namespace esphome {
namespace xtm_driver {

static const char *const TAG = "xtm_driver.sync";

void XtmSync::setup() {
  uint8_t mac[6];
  get_mac_address_raw(mac);
  this->core_.set_self(mac);
  this->pref_ = global_preferences->make_preference<uint32_t>(fnv1_hash("xtm_sync_epoch"), true);
  uint32_t epoch = 0;
  if (this->pref_.load(&epoch))
    this->core_.set_epoch(epoch);
  this->espnow_->register_broadcast_handler(this);
  this->espnow_->register_unknown_peer_handler(this);
  ESP_LOGCONFIG(TAG, "Sync ready, epoch %" PRIu32, this->core_.epoch());
}

void XtmSync::tag_(const uint8_t *body, uint8_t *tag) const {
  hmac_sha256::HmacSHA256 hmac;  // kept in this frame: the S3's SHA hardware requires it
  hmac.init(this->key_);
  hmac.add(body, SYNC_BODY_LEN);
  hmac.calculate();
  uint8_t full[32];
  hmac.get_bytes(full);
  memcpy(tag, full, SYNC_TAG_LEN);
}

bool XtmSync::on_broadcast(const espnow::ESPNowRecvInfo &info, const uint8_t *data, uint16_t size) {
  return this->handle_(info, data, size);
}

// Fixtures aren't added as ESP-NOW peers, so their broadcasts arrive here.
bool XtmSync::on_unknown_peer(const espnow::ESPNowRecvInfo &info, const uint8_t *data, uint16_t size) {
  return this->handle_(info, data, size);
}

bool XtmSync::handle_(const espnow::ESPNowRecvInfo &info, const uint8_t *data, uint16_t size) {
  if (size != SYNC_PACKET_LEN || memcmp(info.des_addr, espnow::ESPNOW_BROADCAST_ADDR, 6) != 0)
    return false;
  SyncMsg m;
  if (!sync_decode_body(data, size, &m))
    return false;  // someone else's protocol
  uint8_t tag[SYNC_TAG_LEN];
  this->tag_(data, tag);
  uint8_t diff = 0;
  for (size_t i = 0; i < SYNC_TAG_LEN; i++)
    diff |= (uint8_t) (tag[i] ^ data[SYNC_BODY_LEN + i]);
  if (diff != 0) {
    this->rejected_++;
    uint32_t now = millis();
    if (now - this->last_warn_ms_ > 10000) {
      this->last_warn_ms_ = now;
      ESP_LOGW(TAG, "Ignored a sync packet with a bad tag from %02X:%02X:%02X:%02X:%02X:%02X (sync keys differ?)",
               info.src_addr[0], info.src_addr[1], info.src_addr[2], info.src_addr[3], info.src_addr[4],
               info.src_addr[5]);
    }
    return true;
  }
  this->core_.receive(m, millis());
  return true;
}

void XtmSync::sync_send(const SyncMsg &m) {
  uint8_t pkt[SYNC_PACKET_LEN];
  sync_encode_body(m, pkt);
  this->tag_(pkt, pkt + SYNC_BODY_LEN);
  esp_err_t err = this->espnow_->send(espnow::ESPNOW_BROADCAST_ADDR, pkt, sizeof(pkt));
  if (err != ESP_OK) {
    this->send_errors_++;
    ESP_LOGD(TAG, "ESP-NOW send failed (%d)", (int) err);
  }
}

void XtmSync::sync_apply(uint16_t level, uint32_t fade_ms) { this->driver_->apply_sync_level(level, fade_ms); }

void XtmSync::sync_role_changed(SyncRole role) { this->driver_->on_sync_role(role); }

void XtmSync::sync_epoch_changed(uint32_t epoch) {
  this->pref_.save(&epoch);
  global_preferences->sync();  // rare (button presses); a stale epoch after power loss would lose claims
}

}  // namespace xtm_driver
}  // namespace esphome

#endif  // USE_ESPNOW
