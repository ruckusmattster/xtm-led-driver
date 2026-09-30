# Board B firmware (ESPHome, ESP32-S3)

Board B is an ESPHome device. A local external component, `xtm_driver`, talks to Board A over
the ribbon UART, exposes the fixture to Home Assistant as a dimmable light, reads the knob,
and runs the ESP-NOW group sync.

## Layout

| Path | What |
| --- | --- |
| `xtm-common.yaml` | The device configuration, shared by every fixture |
| `xtm-1.yaml` … `xtm-4.yaml` | One per fixture: name and keys, then includes `xtm-common.yaml` |
| `secrets.yaml.example` | Copy to `secrets.yaml` and fill in |
| `components/xtm_driver/` | The external component |
| `components/xtm_driver/link_client.*` | The Board A link: framing, pings, level ownership, start-up, retries (no ESPHome code, so it's tested on a PC) |
| `components/xtm_driver/sync_core.*` | Group sync logic (no ESPHome code either) |
| `components/xtm_driver/xtm_*.{h,cpp}` | ESPHome glue: the hub, the light, entities, ESP-NOW transport |
| `components/xtm_driver/link_protocol.h`, `frame.h`, `frame_c.h` | Verbatim copies of Board A's `src/core` files; the tests fail if they drift |
| `tests/` | Unit tests, and an end-to-end test on ESPHome's Linux build (`tests/host`) |

## Build and flash

Needs ESPHome 2026.9.0 or later (Python 3.12 or later): `pip install esphome`, or `uv tool install esphome`.

```sh
cp secrets.yaml.example secrets.yaml      # then edit it
esphome run xtm-1.yaml                    # first time: the module's USB-C; afterwards over Wi-Fi
```

Board B's ESP32 is a Waveshare ESP32-S3-Zero plugged into two sockets on the back of the board.
For the first flash, pull it out and plug it into the computer with a USB-C cable. If the port
doesn't show up, unplug it, hold its BOOT button while plugging the cable back in, and run the
command again. Then put it back in its sockets, USB-C end toward the middle of the board (the
silkscreen on the back marks both ends). Every later update goes over Wi-Fi. Logs:
`esphome logs xtm-1.yaml` (over Wi-Fi once it's running).

Never plug USB into the module while it's in Board B with the ribbon from Board A connected:
its 5V pin is its USB supply, so Board A's 5.5 V would push back into the computer. For USB logs
in place, unplug the ribbon first; the module then runs from USB, with no link to Board A.

Each fixture needs its own API key in `secrets.yaml` (it also encrypts OTA updates). All
fixtures share `sync_key`.

## What it does

**The light.** Home Assistant sees one dimmable light. Brightness goes to Board A as a 16-bit
level on Board A's own curve (so `gamma_correct` is fixed at 1.0), and a transition goes as
one "fade to X over T ms" command that Board A runs itself. ESPHome's loop timing never
touches the light.

**Knob and buttons.** One detent is 1% of the brightness scale, about a 13% change in light,
as an 80 ms fade; spinning fast takes 2× or 4× steps. Turning up from off starts at the
bottom; turning down stops at the bottom (the push switches off). Push toggles with a 400 ms
fade. The sync button is described below.

**Who decides the level.** Board B does. It sends a level when the light's target changes and
otherwise leaves Board A alone. Board A echoes the last level it received in every STATUS
(`level_link`), so Board B re-sends only when that echo shows a problem: a frame lost on the
wire, Board A reset, or Board A's link-loss fallback. A level typed on Board A's console
stands until Board B next changes the light.

**Restarts.**

| What restarts | What happens |
| --- | --- |
| Both boards (power-up) | The light's saved state (`restore_mode: RESTORE_DEFAULT_OFF`) fades in over 1 s |
| Board B, planned (OTA, restart button) | Board B asks Board A to hold for 30 s (120 s for OTA); the light doesn't change; Board B adopts Board A's level when it's back |
| Board B, crash | Board A blinks twice and drops to the link-loss level (20%) after 1.5 s; Board B restores the previous level over 1 s when it's back |
| Board A | Board B sends its level again over 1 s |

**Status LED** (on Board B, dimmed to 30%, 25 kHz PWM):

| Pattern | Meaning |
| --- | --- |
| Green, first 2 s | Starting |
| Red, slow blink | No link to Board A |
| Red, fast blink | Board A reports a fault (see the Fault sensor) |
| Blue, steady | This fixture leads the sync group |
| Blue, short blip each second | This fixture follows the group |
| Amber blip every 3 s | Not connected to Wi-Fi (the fixture still works) |
| Off | Normal |

**Entities.** Light; LED current and voltage; driver output and 48 V input voltages; four
temperatures; driver state, fault, sync role and firmware; link, derating, calibrated and
light-matched flags; clear fault, identify and restart buttons; Board A settings (link-loss
level, bottom current, full-scale current, fleet reference light, link timeout); a Sync lead
switch.

## Group sync

Press the sync button on any fixture: it becomes the lead and every other fixture follows its
level. Press it on another fixture and the lead moves there. Press it on the lead to end the
group; every fixture keeps its level. Adjusting a follower by hand (knob, push, Home
Assistant) takes that fixture out of the group. A fixture that restarts while a group is
running rejoins it.

It runs over ESP-NOW broadcasts, fixture to fixture, with no Home Assistant or router in the
path. The lead sends its target and remaining fade time on every change (repeated after 100
and 300 ms) and once a second; followers let go after 5 s without hearing it. Every packet
carries an HMAC-SHA256 tag under `sync_key`, so fixtures with a different key, and anyone
else's radio, are ignored.

ESP-NOW shares the Wi-Fi radio's channel, so every fixture in a group must be on the same
access point. Without one, sync is unreliable: each ESP32 keeps scanning channels looking for
it. For a venue with no Wi-Fi at all, a variant of `xtm-common.yaml` with `wifi:`, `api:`,
`ota:` and `captive_portal:` removed and `espnow: channel: 1` added syncs reliably, at the
cost of Home Assistant and over-the-air updates (reflash with the module out, over its USB-C).

## Tests

```sh
make -C tests                        # unit tests: link client and sync (ASan/UBSan)

cd tests/host                        # ESPHome's Linux build against a simulated Board A
esphome compile --only-generate xtm-host.yaml
python3 build_host.py                # compiles it with the system g++
python3 run_host_test.py             # drives it through the native API, as Home Assistant does
python3 check_sync_glue.py           # type-checks the ESP-NOW glue against ESPHome's headers
```

`run_host_test.py` covers turn on and off with transitions, the knob and push, settings,
buttons, a lost frame, a Board A reset, a Board A fallback, link silence, planned and
unplanned restarts of Board B, and power-up restore.

What could not be run here: the ESP32-S3 build itself (`esphome compile xtm-1.yaml`), because
it downloads the toolchain from the PlatformIO registry. The component sources are the same
ones compiled and tested in the host build above. Run that compile first.

## Not included

Flashing Board A from Board B. The ribbon carries BOOT0 and NRST for it, and the component
already drives both (the Restart driver button pulses NRST), but the STM32 bootloader client
isn't written. Flash Board A with the STLINK.
