// Host tests for Board B's portable logic: the Board A link client and the group sync.
// Build and run: make -C tests
#include "link_client.h"
#include "sync_core.h"

#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <deque>
#include <string>
#include <vector>

using namespace esphome::xtm_driver;

static int checks = 0, failures = 0;
#define CHECK(cond, ...)                                     \
  do {                                                       \
    checks++;                                                \
    if (!(cond)) {                                           \
      failures++;                                            \
      printf("FAIL %s:%d: %s: ", __FILE__, __LINE__, #cond); \
      printf(__VA_ARGS__);                                   \
      printf("\n");                                          \
    }                                                        \
  } while (0)

// ============================================================================ link client

struct Frame {
  uint8_t type, seq;
  std::vector<uint8_t> payload;
};

struct FakeA : LinkHost {
  frame_rx_t rx{};
  std::vector<Frame> sent;  // frames Board B wrote
  std::vector<uint16_t> adopted;
  std::vector<std::pair<uint8_t, float>> params;
  std::vector<std::string> resyncs;
  int link_changes = 0, restarts = 0, failed = 0;
  bool up = false;

  void link_write(const uint8_t *data, size_t len) override {
    uint8_t f[LINK_MAX_FRAME];
    for (size_t i = 0; i < len; i++) {
      size_t n = frame_rx_byte(&rx, data[i], f, sizeof(f));
      if (n >= 2)
        sent.push_back({f[0], f[1], std::vector<uint8_t>(f + 2, f + n)});
    }
  }
  void on_param(uint8_t id, float v) override { params.push_back({id, v}); }
  void on_link_change(bool u) override {
    link_changes++;
    up = u;
  }
  void on_adopt(uint16_t level) override { adopted.push_back(level); }
  void on_board_a_restart() override { restarts++; }
  void on_command_failed(uint8_t, uint8_t) override { failed++; }
  void on_resync(uint16_t, uint32_t, const char *why) override { resyncs.push_back(why); }

  std::vector<msg_set_level_t> levels() const {
    std::vector<msg_set_level_t> v;
    for (auto &f : sent)
      if (f.type == MSG_SET_LEVEL && f.payload.size() == sizeof(msg_set_level_t)) {
        msg_set_level_t m;
        memcpy(&m, f.payload.data(), sizeof(m));
        v.push_back(m);
      }
    return v;
  }
  int count(uint8_t type) const {
    int n = 0;
    for (auto &f : sent)
      n += f.type == type;
    return n;
  }
};

static void feed(LinkClient &c, uint8_t type, uint8_t seq, const void *payload, size_t len, uint32_t now) {
  uint8_t out[LINK_MAX_ENCODED + 4];
  size_t n = frame_build(type, seq, payload, len, out, sizeof(out));
  for (size_t i = 0; i < n; i++)
    c.rx_byte(out[i], now);
}

static msg_status_t status(uint32_t uptime_s, uint16_t level_link, uint16_t flags = 0, uint8_t state = LSTATE_ON) {
  msg_status_t s;
  memset(&s, 0, sizeof(s));
  s.state = state;
  s.uptime_s = uptime_s;
  s.level_link = level_link;
  s.level_target = level_link;
  s.flags = flags;
  s.fw_version = 0x0100;
  s.i_led = 0.123f;
  return s;
}

static void send_status(LinkClient &c, const msg_status_t &s, uint32_t now) { feed(c, MSG_STATUS, 0, &s, sizeof(s), now); }

static void test_level_mapping() {
  int bad = 0;
  for (uint32_t l = 1; l <= 65535; l++) {
    uint16_t back = level_from_brightness(true, brightness_from_level((uint16_t) l));
    if (back != l)
      bad++;
  }
  CHECK(bad == 0, "%d levels don't survive the round trip through ESPHome's brightness", bad);
  CHECK(level_from_brightness(false, 0.5f) == 0, "off is level 0");
  CHECK(level_from_brightness(true, 0.0f) == 0, "zero brightness is off");
  CHECK(level_from_brightness(true, 1.0f) == 65535, "full is 65535");
  CHECK(level_from_brightness(true, 1.0f / 255.0f) == 258, "HA's lowest step is level %u",
        level_from_brightness(true, 1.0f / 255.0f));
  CHECK(brightness_from_level(1) > 0.0f, "level 1 is still on");
}

static void test_boot_fresh() {
  FakeA a;
  LinkClient c(&a);
  c.set_level(30000, 0, 100);  // the light's restored state, before Board A is heard
  c.poll(100);
  CHECK(a.levels().empty(), "nothing sent before the first STATUS");
  CHECK(a.count(MSG_PING) == 1, "pings from the start");
  send_status(c, status(1, 0, 0, LSTATE_OFF), 400);  // Board A started with us
  auto lv = a.levels();
  CHECK(lv.size() == 1 && lv[0].level == 30000 && lv[0].fade_ms == 1000, "restored level sent with a 1 s fade");
  CHECK(a.adopted.empty(), "no adopt when both boards start together");
  CHECK(c.link_up() && a.up, "link up");
}

static void test_boot_adopt() {
  FakeA a;
  LinkClient c(&a);
  c.set_level(10, 0, 50);  // stale restored state
  send_status(c, status(3600, 20000), 800);  // Board A has been running an hour
  CHECK(a.adopted.size() == 1 && a.adopted[0] == 20000, "adopted Board A's level");
  CHECK(a.levels().empty(), "nothing sent when adopting");
  c.set_level(20000, 0, 820);  // the light, updated to the adopted level, writes it back
  CHECK(a.levels().empty(), "the echo of the adopted level is not sent");
  c.set_level(21000, 200, 900);
  CHECK(a.levels().size() == 1 && a.levels()[0].level == 21000, "later changes are sent");
}

static void test_boot_adopt_fallback() {
  FakeA a;
  LinkClient c(&a);
  send_status(c, status(3600, 40000, LFLAG_FALLBACK), 1500);  // A fell back while B was rebooting
  CHECK(a.adopted.size() == 1 && a.adopted[0] == 40000, "adopt the pre-loss level");
  auto lv = a.levels();
  CHECK(lv.size() == 1 && lv[0].level == 40000 && lv[0].fade_ms == 1000, "and restore it from the fallback");
}

static LinkClient *booted(FakeA &a, uint16_t level) {
  static LinkClient *c = nullptr;
  delete c;
  c = new LinkClient(&a);
  c->set_level(level, 0, 0);
  send_status(*c, status(0, 0, 0, LSTATE_OFF), 100);
  send_status(*c, status(0, level), 200);
  a.sent.clear();
  a.resyncs.clear();
  return c;
}

static void test_lost_frame() {
  FakeA a;
  LinkClient &c = *booted(a, 5000);
  c.set_level(6000, 2000, 1000);
  CHECK(a.levels().size() == 1, "sent once");
  send_status(c, status(1, 5000), 1100);  // A still reports the old level_link: too soon to judge
  CHECK(a.levels().size() == 1, "no re-send inside 300 ms");
  send_status(c, status(1, 5000), 1400);
  auto lv = a.levels();
  CHECK(lv.size() == 2 && lv[1].level == 6000, "re-sent after 300 ms");
  CHECK(lv.size() == 2 && lv[1].fade_ms == 1600, "with the time left in the fade (%u)", lv.size() == 2 ? lv[1].fade_ms : 0);
  send_status(c, status(2, 6000), 1800);
  CHECK(a.levels().size() == 2, "settled once level_link matches");
}

static void test_console_level_left_alone() {
  FakeA a;
  LinkClient &c = *booted(a, 5000);
  msg_status_t s = status(10, 5000);
  s.level_target = 12345;  // someone typed `lvl 12345` on Board A's console
  for (uint32_t t = 1000; t < 5000; t += 100)
    send_status(c, s, t);
  CHECK(a.levels().empty(), "a console level is not overridden");
}

static void test_restart_and_fallback() {
  FakeA a;
  LinkClient &c = *booted(a, 5000);
  send_status(c, status(100, 5000), 1000);
  send_status(c, status(0, 0, 0, LSTATE_OFF), 1500);  // A was reset
  auto lv = a.levels();
  CHECK(a.restarts == 1, "restart noticed");
  CHECK(lv.size() == 1 && lv[0].level == 5000 && lv[0].fade_ms == 1000, "level restored with a 1 s fade");
  send_status(c, status(1, 5000), 2000);
  a.sent.clear();
  send_status(c, status(5, 5000, LFLAG_FALLBACK), 6000);  // A lost the link and dropped to 20%
  lv = a.levels();
  CHECK(lv.size() == 1 && lv[0].level == 5000 && lv[0].fade_ms == 1000, "fallback undone");
}

static void test_backoff() {
  FakeA a;
  LinkClient &c = *booted(a, 5000);
  c.set_level(7000, 0, 1000);
  for (uint32_t t = 1100; t <= 21000; t += 100)
    send_status(c, status(10, 5000), t);  // Board A never takes it
  int n = (int) a.levels().size();
  // first send + 4 fast re-sends (300 ms apart) + one every 5 s after
  CHECK(n >= 7 && n <= 9, "re-sends back off: %d sends in 20 s", n);
}

static void test_link_timeout_and_ping() {
  FakeA a;
  LinkClient c(&a);
  c.set_timing(200, 1000, 1000);
  for (uint32_t t = 0; t <= 1000; t += 10)
    c.poll(t);
  CHECK(a.count(MSG_PING) == 6, "a PING every 200 ms: %d", a.count(MSG_PING));
  send_status(c, status(1, 0, 0, LSTATE_OFF), 1000);
  CHECK(c.link_up(), "up");
  c.poll(1900);
  CHECK(c.link_up(), "still up 900 ms later");
  c.poll(2100);
  CHECK(!c.link_up() && a.link_changes == 2, "down after 1 s of silence");
  send_status(c, status(3, 0, 0, LSTATE_OFF), 2500);
  CHECK(c.link_up() && a.link_changes == 3, "back up");
}

static void test_commands() {
  FakeA a;
  LinkClient c(&a);
  c.set_param(PARAM_FALLBACK_B, 0.25f, true);
  c.poll(0);
  CHECK(a.count(MSG_SET_PARAM) == 1, "SET_PARAM sent");
  msg_param_t r = {PARAM_FALLBACK_B, 0.25f};
  feed(c, MSG_PARAM, 0, &r, sizeof(r), 50);
  c.poll(400);
  CHECK(a.count(MSG_SET_PARAM) == 1 && a.failed == 0, "answered: no retry");
  CHECK(a.params.size() == 1 && a.params[0].first == PARAM_FALLBACK_B, "value reported");

  c.identify(3);
  c.poll(500);
  CHECK(a.count(MSG_IDENTIFY) == 1, "IDENTIFY sent");
  msg_ack_t ack = {a.sent.back().seq, RESULT_OK};
  feed(c, MSG_ACK, 0, &ack, sizeof(ack), 520);
  c.poll(900);
  CHECK(a.count(MSG_IDENTIFY) == 1, "acked: no retry");

  c.clear_fault();
  for (uint32_t t = 1000; t < 2500; t += 10)
    c.poll(t);
  CHECK(a.count(MSG_CLEAR_FAULT) == 3 && a.failed == 1, "3 tries then reported: %d tries", a.count(MSG_CLEAR_FAULT));

  // a slider being dragged: while one value is in flight, only the newest waiting one goes next
  c.set_param(PARAM_I_MAX, 1.0f, true);
  c.poll(3000);
  int before = a.count(MSG_SET_PARAM);
  c.set_param(PARAM_I_MAX, 1.1f, true);
  c.set_param(PARAM_I_MAX, 1.2f, true);
  msg_param_t r2 = {PARAM_I_MAX, 1.0f};
  feed(c, MSG_PARAM, 0, &r2, sizeof(r2), 3010);
  c.poll(3020);
  CHECK(a.count(MSG_SET_PARAM) == before + 1, "second SET_PARAM sent");
  msg_set_param_t last;
  memcpy(&last, a.sent.back().payload.data(), sizeof(last));
  CHECK(fabsf(last.value - 1.2f) < 1e-6f, "the newest value, not the middle one (%.2f)", last.value);

  // Board A refuses a value: ACK with BAD_PARAM ends it as a failure
  c.set_param(PARAM_I_MAX, 9.0f, true);
  feed(c, MSG_PARAM, 0, &r2, sizeof(r2), 3030);  // finishes the 1.2 A one
  c.poll(3040);
  msg_ack_t nak = {a.sent.back().seq, RESULT_BAD_PARAM};
  int failed_before = a.failed;
  feed(c, MSG_ACK, 0, &nak, sizeof(nak), 3050);
  CHECK(a.failed == failed_before + 1, "refusal reported");
}

static void test_short_status() {
  FakeA a;
  LinkClient c(&a);
  msg_status_t s = status(1, 0, 0, LSTATE_OFF);
  feed(c, MSG_STATUS, 0, &s, offsetof(msg_status_t, level_link), 100);  // older firmware
  CHECK(c.has_status(), "a STATUS without level_link is accepted");
  feed(c, MSG_STATUS, 0, &s, 10, 200);
  CHECK(c.status().uptime_s == 1, "a truncated STATUS is ignored");
}

// ============================================================================ sync

struct Air;

struct Fixture : SyncHost {
  Air *air;
  SyncCore core;
  uint8_t mac[6];
  uint16_t level = 0;       // the light's target
  uint32_t fade = 0;
  uint32_t saved_epoch = 0;
  int role_changes = 0;
  uint32_t now = 0;

  Fixture(Air *a, uint8_t id) : air(a), core(this) {
    uint8_t m[6] = {0x24, 0x6F, 0x28, 0x00, 0x00, id};
    memcpy(mac, m, 6);
    core.set_self(mac);
  }
  void sync_send(const SyncMsg &m) override;
  void sync_apply(uint16_t l, uint32_t f) override {
    level = l;
    fade = f;
    core.on_target(l, f, false, now);  // what XtmDriver::light_target does for a sync change
  }
  void sync_role_changed(SyncRole) override { role_changes++; }
  void sync_epoch_changed(uint32_t e) override { saved_epoch = e; }
  // someone at this fixture: knob, push, Home Assistant
  void local(uint16_t l, uint32_t f) {
    level = l;
    fade = f;
    core.on_target(l, f, true, now);
  }
};

struct Air {
  std::vector<Fixture *> fx;
  std::deque<std::pair<Fixture *, std::vector<uint8_t>>> q;
  uint32_t loss_percent = 0, rng = 12345;
  uint32_t now = 0;
  int packets = 0;

  bool lose() {
    rng = rng * 1103515245u + 12345u;
    return (rng >> 16) % 100 < loss_percent;
  }
  void deliver() {
    while (!q.empty()) {
      auto [from, body] = q.front();
      q.pop_front();
      for (auto *f : fx) {
        if (f == from || lose())
          continue;
        SyncMsg m;
        if (sync_decode_body(body.data(), body.size(), &m))
          f->core.receive(m, now);
      }
    }
  }
  void run(uint32_t until, uint32_t step = 10) {
    for (; now <= until; now += step) {
      for (auto *f : fx) {
        f->now = now;
        f->core.poll(now);
      }
      deliver();
    }
  }
};

void Fixture::sync_send(const SyncMsg &m) {
  std::vector<uint8_t> b(SYNC_BODY_LEN);
  sync_encode_body(m, b.data());
  air->q.push_back({this, b});
  air->packets++;
}

static void test_sync_codec() {
  SyncMsg m;
  m.type = SYNC_STATE;
  m.epoch = 0x01020304;
  for (int i = 0; i < 6; i++)
    m.owner[i] = (uint8_t) (0xA0 + i);
  m.seq = 0xBEEF;
  m.level = 54321;
  m.fade_ms = 600000;
  uint8_t b[SYNC_BODY_LEN];
  sync_encode_body(m, b);
  SyncMsg d;
  CHECK(sync_decode_body(b, sizeof(b), &d), "decodes");
  CHECK(d.epoch == m.epoch && d.seq == m.seq && d.level == m.level && d.fade_ms == m.fade_ms &&
            memcmp(d.owner, m.owner, 6) == 0 && d.type == m.type,
        "round trip");
  b[0] = 'Y';
  CHECK(!sync_decode_body(b, sizeof(b), &d), "wrong magic rejected");
  b[0] = 'X';
  CHECK(!sync_decode_body(b, 10, &d), "short packet rejected");
  b[3] = 9;
  CHECK(!sync_decode_body(b, sizeof(b), &d), "unknown type rejected");
}

struct Four {
  Air air;
  Fixture a{&air, 1}, b{&air, 2}, c{&air, 3}, d{&air, 4};
  Four() { air.fx = {&a, &b, &c, &d}; }
  void at(uint32_t t) {
    air.now = t;
    for (auto *f : air.fx)
      f->now = t;
  }
};

static void test_sync_group() {
  Four w;
  w.at(0);
  w.a.local(30000, 0);
  w.b.local(1000, 0);
  w.c.local(0, 0);
  w.d.local(65535, 0);
  w.a.core.press(0);
  w.air.run(50);
  CHECK(w.a.core.role() == SyncRole::OWNER, "A leads");
  for (Fixture *f : {&w.b, &w.c, &w.d})
    CHECK(f->core.role() == SyncRole::FOLLOWER && f->level == 30000, "follower matches A (level %u)", f->level);

  // A's knob / Home Assistant: followers fade with it
  w.at(1000);
  w.a.local(45000, 2000);
  w.air.run(1010);
  for (Fixture *f : {&w.b, &w.c, &w.d})
    CHECK(f->level == 45000 && f->fade == 2000, "fade copied (level %u fade %u)", f->level, f->fade);

  // heartbeats alone don't restart a follower's fade
  w.b.fade = 0;
  w.air.run(4000);
  CHECK(w.b.fade == 0, "heartbeat with the same target is not re-applied");

  // ownership moves to whoever presses next
  w.at(4000);
  w.c.local(2000, 0);  // C adjusted locally first: it leaves the group ...
  CHECK(w.c.core.role() == SyncRole::INDEPENDENT, "a local change detaches a follower");
  w.air.run(6000);
  CHECK(w.c.level == 2000, "... and heartbeats don't pull it back (%u)", w.c.level);
  w.at(6000);
  w.c.core.press(6000);  // ... then takes the lead
  w.air.run(6100);
  CHECK(w.c.core.role() == SyncRole::OWNER, "C leads now");
  for (Fixture *f : {&w.a, &w.b, &w.d})
    CHECK(f->core.role() == SyncRole::FOLLOWER && f->level == 2000, "everyone follows C (%u)", f->level);

  // pressing on the owner ends the group, levels stay
  w.at(7000);
  w.c.core.press(7000);
  w.air.run(7500);
  for (Fixture *f : {&w.a, &w.b, &w.c, &w.d})
    CHECK(f->core.role() == SyncRole::INDEPENDENT && f->level == 2000, "group ended, level kept");
  w.air.run(20000);
  for (Fixture *f : {&w.a, &w.b, &w.c, &w.d})
    CHECK(f->core.role() == SyncRole::INDEPENDENT, "and stays ended");
  CHECK(w.a.saved_epoch == w.c.core.epoch() && w.c.saved_epoch == w.c.core.epoch(), "epochs saved");
}

static void test_sync_owner_silent() {
  Four w;
  w.at(0);
  w.a.local(20000, 0);
  w.a.core.press(0);
  w.air.run(100);
  // A drops off the air (power cut, out of range): followers let go after 5 s
  auto fx = w.air.fx;
  w.air.fx = {&w.b, &w.c, &w.d};
  w.air.run(6000);
  CHECK(w.b.core.role() == SyncRole::INDEPENDENT, "follower lets go after 5 s of silence");
  // A comes back still leading: they rejoin (they didn't leave on purpose)
  w.air.fx = fx;
  w.air.run(8000);
  CHECK(w.b.core.role() == SyncRole::FOLLOWER, "and rejoins when A is heard again");
}

static void test_sync_simultaneous() {
  Four w;
  w.at(0);
  w.a.local(100, 0);
  w.b.local(200, 0);
  w.a.core.press(0);
  w.b.core.press(0);  // before either hears the other: both claim epoch 1
  w.air.run(500);
  int owners = 0;
  for (Fixture *f : {&w.a, &w.b, &w.c, &w.d})
    owners += f->core.role() == SyncRole::OWNER;
  CHECK(owners == 1, "one owner after a tie: %d", owners);
  CHECK(w.b.core.role() == SyncRole::OWNER, "the higher MAC wins");
  for (Fixture *f : {&w.a, &w.c, &w.d})
    CHECK(f->level == 200, "everyone on B's level (%u)", f->level);
}

static void test_sync_restart() {
  Four w;
  w.at(0);
  w.a.local(5000, 0);
  w.a.core.press(0);
  w.air.run(100);
  // D restarts: roles are lost, the epoch is restored from flash; it rejoins on a heartbeat
  uint32_t kept = w.d.saved_epoch;
  w.d.core = SyncCore(&w.d);
  w.d.core.set_self(w.d.mac);
  w.d.core.set_epoch(kept);
  w.d.level = 0;
  w.air.run(1300);
  CHECK(w.d.core.role() == SyncRole::FOLLOWER && w.d.level == 5000, "restarted follower rejoins");

  // A (the owner) restarts: its group is gone; the others let go, then A can lead again
  kept = w.a.saved_epoch;
  w.a.core = SyncCore(&w.a);
  w.a.core.set_self(w.a.mac);
  w.a.core.set_epoch(kept);
  w.air.run(7000);
  CHECK(w.b.core.role() == SyncRole::INDEPENDENT, "old group lapses");
  w.at(7000);
  w.a.local(9000, 0);
  w.a.core.press(7000);
  w.air.run(7200);
  CHECK(w.b.core.role() == SyncRole::FOLLOWER && w.b.level == 9000, "restarted owner leads again");

  // a fixture that lost its saved epoch still can't be pulled into an old group by stale packets
  SyncMsg stale;
  stale.type = SYNC_STATE;
  stale.epoch = 1;
  memcpy(stale.owner, w.c.mac, 6);
  stale.seq = 999;
  stale.level = 1;
  w.b.core.receive(stale, 7300);
  CHECK(w.b.level == 9000, "stale epoch ignored");
}

static void test_sync_loss() {
  Four w;
  w.air.loss_percent = 30;
  w.at(0);
  w.a.local(12000, 0);
  w.a.core.press(0);
  w.air.run(2500);
  for (Fixture *f : {&w.b, &w.c, &w.d})
    CHECK(f->core.role() == SyncRole::FOLLOWER && f->level == 12000, "joins despite 30%% loss");
  // a burst of knob detents; after it stops every follower lands on the final level
  for (uint32_t t = 3000, l = 12000; t < 3600; t += 30, l += 300) {
    w.at(t);
    w.a.local((uint16_t) l, 80);
    w.air.run(t + 20);
  }
  uint16_t final_level = w.a.level;
  w.air.run(5000);
  for (Fixture *f : {&w.b, &w.c, &w.d})
    CHECK(f->level == final_level, "converged on %u (has %u)", final_level, f->level);
  int per_s = w.air.packets;
  w.air.packets = 0;
  w.air.run(15000);
  CHECK(w.air.packets <= 12, "quiet group costs about one packet a second: %d in 10 s", w.air.packets);
  (void) per_s;
}

int main() {
  test_level_mapping();
  test_boot_fresh();
  test_boot_adopt();
  test_boot_adopt_fallback();
  test_lost_frame();
  test_console_level_left_alone();
  test_restart_and_fallback();
  test_backoff();
  test_link_timeout_and_ping();
  test_commands();
  test_short_status();
  test_sync_codec();
  test_sync_group();
  test_sync_owner_silent();
  test_sync_simultaneous();
  test_sync_restart();
  test_sync_loss();
  printf("%d checks, %d failures\n", checks, failures);
  return failures != 0;
}
