#include "sync_core.h"

#include <cstring>

namespace esphome {
namespace xtm_driver {

constexpr uint32_t SyncCore::REPEAT_MS[2];

const char *sync_role_name(SyncRole role) {
  switch (role) {
    case SyncRole::OWNER:
      return "lead";
    case SyncRole::FOLLOWER:
      return "following";
    default:
      return "independent";
  }
}

static void put16(uint8_t *p, uint16_t v) {
  p[0] = (uint8_t) v;
  p[1] = (uint8_t) (v >> 8);
}
static void put32(uint8_t *p, uint32_t v) {
  for (int i = 0; i < 4; i++)
    p[i] = (uint8_t) (v >> (8 * i));
}
static uint16_t get16(const uint8_t *p) { return (uint16_t) (p[0] | (p[1] << 8)); }
static uint32_t get32(const uint8_t *p) {
  return (uint32_t) p[0] | ((uint32_t) p[1] << 8) | ((uint32_t) p[2] << 16) | ((uint32_t) p[3] << 24);
}

void sync_encode_body(const SyncMsg &m, uint8_t *out) {
  out[0] = 'X';
  out[1] = 'S';
  out[2] = SYNC_VERSION;
  out[3] = m.type;
  put32(out + 4, m.epoch);
  memcpy(out + 8, m.owner, 6);
  put16(out + 14, m.seq);
  put16(out + 16, m.level);
  put32(out + 18, m.fade_ms);
}

bool sync_decode_body(const uint8_t *in, size_t len, SyncMsg *m) {
  if (len < SYNC_BODY_LEN || in[0] != 'X' || in[1] != 'S' || in[2] != SYNC_VERSION)
    return false;
  if (in[3] != SYNC_STATE && in[3] != SYNC_RELEASE)
    return false;
  m->type = in[3];
  m->epoch = get32(in + 4);
  memcpy(m->owner, in + 8, 6);
  m->seq = get16(in + 14);
  m->level = get16(in + 16);
  m->fade_ms = get32(in + 18);
  return true;
}

void SyncCore::set_self(const uint8_t mac[6]) { memcpy(this->self_, mac, 6); }

void SyncCore::set_role_(SyncRole role) {
  if (role == this->role_)
    return;
  this->role_ = role;
  if (role != SyncRole::OWNER && this->repeat_type_ == SYNC_STATE)
    this->repeat_pending_[0] = this->repeat_pending_[1] = false;
  this->host_->sync_role_changed(role);
}

void SyncCore::set_epoch_(uint32_t epoch) {
  if (epoch == this->epoch_)
    return;
  this->epoch_ = epoch;
  this->host_->sync_epoch_changed(epoch);
}

void SyncCore::press(uint32_t now) {
  if (this->role_ == SyncRole::OWNER)
    this->release_(now);
  else
    this->claim_(now);
}

void SyncCore::set_lead(bool lead, uint32_t now) {
  if (lead && this->role_ != SyncRole::OWNER)
    this->claim_(now);
  else if (!lead && this->role_ == SyncRole::OWNER)
    this->release_(now);
}

void SyncCore::claim_(uint32_t now) {
  this->set_epoch_(this->epoch_ + 1);
  memcpy(this->owner_, this->self_, 6);
  this->seq_ = 0;
  this->detached_ = false;
  this->applied_ = false;
  this->set_role_(SyncRole::OWNER);
  this->send_state_(now);
  this->repeat_(SYNC_STATE, now);
  this->next_hb_ms_ = now + HEARTBEAT_MS;
}

void SyncCore::release_(uint32_t now) {
  this->set_epoch_(this->epoch_ + 1);
  this->release_epoch_ = this->epoch_;
  this->detached_ = false;
  this->set_role_(SyncRole::INDEPENDENT);
  this->send_release_();
  this->repeat_(SYNC_RELEASE, now);
}

void SyncCore::follow_(const SyncMsg &m, uint32_t now) {
  this->set_epoch_(m.epoch);
  memcpy(this->owner_, m.owner, 6);
  this->seq_ = m.seq;
  this->last_rx_ms_ = now;
  this->detached_ = false;
  this->set_role_(SyncRole::FOLLOWER);
  this->applied_ = true;
  this->applied_level_ = m.level;
  this->host_->sync_apply(m.level, m.fade_ms);
}

void SyncCore::on_target(uint16_t level, uint32_t fade_ms, bool local, uint32_t now) {
  this->target_level_ = level;
  this->target_end_ms_ = now + fade_ms;
  if (!local)
    return;
  if (this->role_ == SyncRole::FOLLOWER) {
    this->detached_ = true;  // adjusted by hand: this fixture leaves the group
    this->set_role_(SyncRole::INDEPENDENT);
  } else if (this->role_ == SyncRole::OWNER) {
    this->send_state_(now);
    this->repeat_(SYNC_STATE, now);
    this->next_hb_ms_ = now + HEARTBEAT_MS;
  }
}

void SyncCore::receive(const SyncMsg &m, uint32_t now) {
  if (memcmp(m.owner, this->self_, 6) == 0 || m.epoch < this->epoch_)
    return;  // our own, or older than anything we have seen
  if (m.type == SYNC_RELEASE) {
    if (m.epoch > this->epoch_) {
      this->set_epoch_(m.epoch);
      this->detached_ = false;
      this->set_role_(SyncRole::INDEPENDENT);  // the group has ended; keep the level
    }
    return;
  }
  if (m.type != SYNC_STATE)
    return;
  if (m.epoch > this->epoch_) {
    this->follow_(m, now);  // a newer claim; an owner yields to it too
    return;
  }
  int by_owner = memcmp(m.owner, this->owner_, 6);
  switch (this->role_) {
    case SyncRole::FOLLOWER:
      if (by_owner == 0) {
        if ((int16_t) (m.seq - this->seq_) <= 0)
          return;  // a repeat we already have
        this->seq_ = m.seq;
        this->last_rx_ms_ = now;
        if (!this->applied_ || m.level != this->applied_level_) {
          this->applied_ = true;
          this->applied_level_ = m.level;
          this->host_->sync_apply(m.level, m.fade_ms);
        }
      } else if (by_owner > 0) {
        this->follow_(m, now);  // two claims in one epoch: the higher MAC wins
      }
      return;
    case SyncRole::OWNER:
      if (memcmp(m.owner, this->self_, 6) > 0)
        this->follow_(m, now);
      return;
    case SyncRole::INDEPENDENT:
    default:
      if (!this->detached_)
        this->follow_(m, now);  // e.g. this fixture restarted while its group was running
      return;
  }
}

void SyncCore::poll(uint32_t now) {
  if (this->role_ == SyncRole::OWNER && (int32_t) (now - this->next_hb_ms_) >= 0) {
    this->send_state_(now);
    this->next_hb_ms_ = now + HEARTBEAT_MS;
  }
  if (this->role_ == SyncRole::FOLLOWER && now - this->last_rx_ms_ > OWNER_TIMEOUT_MS)
    this->set_role_(SyncRole::INDEPENDENT);  // owner gone quiet; rejoins if it comes back
  for (int i = 0; i < 2; i++) {
    if (!this->repeat_pending_[i] || (int32_t) (now - this->repeat_at_[i]) < 0)
      continue;
    this->repeat_pending_[i] = false;
    if (this->repeat_type_ == SYNC_STATE && this->role_ == SyncRole::OWNER)
      this->send_state_(now);
    else if (this->repeat_type_ == SYNC_RELEASE)
      this->send_release_();
  }
}

void SyncCore::repeat_(uint8_t type, uint32_t now) {
  this->repeat_type_ = type;
  for (int i = 0; i < 2; i++) {
    this->repeat_pending_[i] = true;
    this->repeat_at_[i] = now + REPEAT_MS[i];
  }
}

void SyncCore::send_state_(uint32_t now) {
  SyncMsg m;
  m.type = SYNC_STATE;
  m.epoch = this->epoch_;
  memcpy(m.owner, this->self_, 6);
  m.seq = ++this->seq_;
  m.level = this->target_level_;
  int32_t left = (int32_t) (this->target_end_ms_ - now);
  m.fade_ms = left > 0 ? (uint32_t) left : 0u;
  this->host_->sync_send(m);
}

void SyncCore::send_release_() {
  SyncMsg m;
  m.type = SYNC_RELEASE;
  m.epoch = this->release_epoch_;
  memcpy(m.owner, this->self_, 6);
  m.seq = ++this->seq_;
  this->host_->sync_send(m);
}

}  // namespace xtm_driver
}  // namespace esphome
