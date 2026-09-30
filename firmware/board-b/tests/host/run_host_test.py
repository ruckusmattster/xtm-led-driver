#!/usr/bin/env python3
"""End-to-end test of the xtm_driver ESPHome component on a PC.

The component runs in ESPHome's host (Linux) build, its UART connected over a
pseudo-terminal to board_a_sim.BoardA, and is driven through the native API the way
Home Assistant drives it. Needs ESPHome and aioesphomeapi (ESPHome installs it).

    esphome compile --only-generate xtm-host.yaml
    python3 build_host.py
    python3 run_host_test.py
"""
import asyncio
import math
import os
import pathlib
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time

from aioesphomeapi import APIClient

import board_a_sim as sim

HERE = pathlib.Path(__file__).resolve().parent
BIN = HERE / "xtm-host"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, bool(ok), detail))
    print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail and not ok else ''}", flush=True)


def f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def level_of(b: float) -> int:
    """Board B's mapping (lroundf on float32), for brightness as the API delivers it."""
    if b <= 0:
        return 0
    return 1 + int(math.floor(f32(f32(b) * 65534.0) + 0.5))


class Device:
    def __init__(self, prefdir: str):
        self.prefdir = prefdir
        self.proc = None
        self.lines: list[tuple[float, str]] = []

    def start(self):
        env = dict(os.environ, ESPHOME_PREFDIR=self.prefdir)
        self.proc = subprocess.Popen([str(BIN)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.append((time.monotonic(), line.rstrip()))

    def stop(self, sig=signal.SIGTERM):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(sig)
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    def saw(self, text: str, since: float = 0.0) -> bool:
        return any(text in line for (t, line) in self.lines if t >= since)


class Api:
    def __init__(self):
        self.client = None
        self.keys: dict[str, int] = {}
        self.names: dict[int, str] = {}
        self.states: dict[str, object] = {}

    async def connect(self, timeout=15.0):
        t0 = time.monotonic()
        while True:
            self.client = APIClient("127.0.0.1", 16053, None)
            try:
                await self.client.connect(login=True)
                break
            except Exception:
                if time.monotonic() - t0 > timeout:
                    raise
                await asyncio.sleep(0.3)
        entities, _ = await self.client.list_entities_services()
        for e in entities:
            self.keys[e.name] = e.key
            self.names[e.key] = e.name
        self.client.subscribe_states(self._on_state)

    def _on_state(self, st):
        name = self.names.get(st.key)
        if name:
            self.states[name] = st

    def value(self, name):
        st = self.states.get(name)
        return None if st is None else getattr(st, "state", None)

    async def close(self):
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass

    async def light(self, **kw):
        self.client.light_command(self.keys["Light"], **kw)  # queued; returns at once

    async def press(self, name):
        self.client.button_command(self.keys[name])

    async def number(self, name, value):
        self.client.number_command(self.keys[name], value)


async def wait_for(cond, timeout=3.0, step=0.02) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        await asyncio.sleep(step)
    return bool(cond())


def levels(a: sim.BoardA, since: float):
    return [p for (_, p) in a.commands(sim.MSG_SET_LEVEL, since)]


async def main():
    if not BIN.exists():
        sys.exit("build first: esphome compile --only-generate xtm-host.yaml && python3 build_host.py")
    prefdir = tempfile.mkdtemp(prefix="xtm-prefs-")
    a = sim.BoardA(uptime_s=0.0)
    dev = Device(prefdir)
    api = Api()
    try:
        # ------------------------------------------------ 1. both boards start together
        dev.start()
        await api.connect()
        check("link comes up", await wait_for(lambda: api.value("Driver link") is True, 5))
        check("firmware version shown", await wait_for(lambda: api.value("Driver firmware") == "1.0", 3),
              str(api.value("Driver firmware")))
        check("state shown", await wait_for(lambda: api.value("Driver state") == "off", 3),
              str(api.value("Driver state")))
        check("settings read from Board A",
              await wait_for(lambda: api.value("Link-loss level") is not None and
                             abs(api.value("Link-loss level") - 20.0) < 1e-3 and
                             abs((api.value("Bottom current") or 0) - 5.0) < 1e-3, 3),
              f"{api.value('Link-loss level')} %, {api.value('Bottom current')} uA")
        check("calibration read from Board A", await wait_for(lambda: api.value("Full scale light") == 850.0, 3))
        check("a dark first start sends nothing", not levels(a, 0.0), str(levels(a, 0.0)))
        check("pings arrive", await wait_for(lambda: len(a.commands(sim.MSG_PING)) >= 3, 2))

        # ------------------------------------------------ 2. Home Assistant commands
        t = time.monotonic()
        await api.light(state=True, brightness=0.5, transition_length=2.0)
        ok = await wait_for(lambda: levels(a, t) == [(level_of(0.5), 2000)], 2)
        check("turn on with a 2 s transition is one command", ok, str(levels(a, t)))
        await asyncio.sleep(2.3)
        check("no extra command when the transition ends", levels(a, t) == [(level_of(0.5), 2000)], str(levels(a, t)))
        check("LED current reported", await wait_for(lambda: (api.value("LED current") or 0) > 1e-3, 2),
              str(api.value("LED current")))

        t = time.monotonic()
        await api.light(state=True, brightness=0.25, transition_length=0.0)
        check("instant change", await wait_for(lambda: levels(a, t) == [(level_of(0.25), 0)], 2), str(levels(a, t)))

        t = time.monotonic()
        await api.light(state=True, brightness=0.8, transition_length=10.0)
        await asyncio.sleep(0.5)
        await api.light(state=True, brightness=0.8, transition_length=0.0)  # stop the fade where it's going
        ok = await wait_for(lambda: levels(a, t) == [(level_of(0.8), 10000), (level_of(0.8), 0)], 2)
        check("a snap to the target stops a running fade", ok, str(levels(a, t)))

        # ------------------------------------------------ 3. the knob
        await api.light(state=True, brightness=0.3, transition_length=0.0)
        await asyncio.sleep(0.6)
        t = time.monotonic()
        for _ in range(3):
            await api.press("Knob up")
            await asyncio.sleep(0.15)
        await wait_for(lambda: len(levels(a, t)) >= 3, 2)
        lv = levels(a, t)
        check("knob: three detents, three 80 ms fades",
              len(lv) == 3 and all(f == 80 for _, f in lv) and lv[0][0] < lv[1][0] < lv[2][0], str(lv))
        check("knob: 1% of the scale per slow detent",
              len(lv) == 3 and abs(lv[0][0] - level_of(0.31)) <= 2, f"{lv[:1]} vs {level_of(0.31)}")
        t = time.monotonic()
        await api.press("Knob down")
        check("knob down", await wait_for(lambda: len(levels(a, t)) == 1 and levels(a, t)[0][0] < lv[-1][0], 2),
              str(levels(a, t)))
        t = time.monotonic()
        await api.press("Knob push")
        check("push turns off over 400 ms", await wait_for(lambda: levels(a, t) == [(0, 400)], 2), str(levels(a, t)))
        await asyncio.sleep(0.6)
        t = time.monotonic()
        await api.press("Knob down")
        await asyncio.sleep(0.4)
        check("knob down while off does nothing", levels(a, t) == [], str(levels(a, t)))
        await api.press("Knob up")
        check("knob up from off starts at the bottom",
              await wait_for(lambda: levels(a, t) == [(level_of(0.01), 80)], 2), f"{levels(a, t)} vs {level_of(0.01)}")
        t = time.monotonic()
        await api.press("Knob push")
        await api.press("Knob push")
        await wait_for(lambda: len(levels(a, t)) >= 2, 2)
        lv = levels(a, t)
        check("push toggles back on at the previous level", len(lv) == 2 and lv[0] == (0, 400) and lv[1][0] > 0 and
              lv[1][1] == 400, str(lv))

        # ------------------------------------------------ 4. settings and buttons
        t = time.monotonic()
        await api.number("Link-loss level", 30.0)
        ok = await wait_for(lambda: any(abs(p[1] - 0.3) < 1e-6 and p[0] == 0 and p[2] == 1
                                        for _, p in a.commands(sim.MSG_SET_PARAM, t)), 2)
        check("setting sent to Board A and saved there", ok, str(a.commands(sim.MSG_SET_PARAM, t)))
        check("setting confirmed", await wait_for(lambda: abs((api.value("Link-loss level") or 0) - 30.0) < 1e-3, 2),
              str(api.value("Link-loss level")))
        t = time.monotonic()
        await api.number("Full-scale current", 1.2)
        check("full-scale current", await wait_for(lambda: any(p[0] == 9 and abs(p[1] - 1.2) < 1e-6
                                                                for _, p in a.commands(sim.MSG_SET_PARAM, t)), 2))
        t = time.monotonic()
        await api.press("Identify")
        check("identify", await wait_for(lambda: [p for _, p in a.commands(sim.MSG_IDENTIFY, t)] == [(3,)], 2))
        await api.press("Clear fault")
        check("clear fault", await wait_for(lambda: len(a.commands(sim.MSG_CLEAR_FAULT, t)) == 1, 2))
        await asyncio.sleep(1.5)
        check("identify blinks are left alone", levels(a, t) == [], str(levels(a, t)))

        # ------------------------------------------------ 5. recovering from trouble
        await api.light(state=True, brightness=0.6, transition_length=0.0)
        await asyncio.sleep(0.5)
        t = time.monotonic()
        a.drop_next_set_level = True
        await api.light(state=True, brightness=0.65, transition_length=0.0)
        ok = await wait_for(lambda: len(levels(a, t)) >= 2, 2)
        lv = levels(a, t)
        check("a lost SET_LEVEL is sent again", ok and lv[0] == lv[1] == (level_of(0.65), 0), str(lv))
        check("  ... and logged", dev.saw("Board A missed a level", t))
        await asyncio.sleep(0.5)
        check("  ... once", len(levels(a, t)) == 2, str(levels(a, t)))

        t = time.monotonic()
        a.reset(uptime_s=0.0)  # Board A reset (watchdog, brown-out)
        ok = await wait_for(lambda: levels(a, t) == [(level_of(0.65), 1000)], 3)
        check("Board A reset: level restored with a 1 s fade", ok, str(levels(a, t)))
        check("  ... and logged", dev.saw("Board A restarted", t) or dev.saw("missed a level", t))

        t = time.monotonic()
        a.force_fallback()
        ok = await wait_for(lambda: levels(a, t) == [(level_of(0.65), 1000)], 3)
        check("Board A fallback undone", ok, str(levels(a, t)))

        t = time.monotonic()
        a.silent = True
        check("silence: link reported down", await wait_for(lambda: api.value("Driver link") is False, 3))
        check("  ... and measurements unknown", await wait_for(lambda: math.isnan(api.value("LED current")), 2),
              str(api.value("LED current")))
        a.silent = False
        check("  ... and back", await wait_for(lambda: api.value("Driver link") is True, 3))
        check("  ... with no level change needed", levels(a, t) == [], str(levels(a, t)))

        # ------------------------------------------------ 6. Board B restarts while Board A keeps running
        await api.light(state=True, brightness=0.5, transition_length=0.0)
        await asyncio.sleep(0.5)
        t = time.monotonic()
        await api.close()
        dev.stop(signal.SIGTERM)  # planned: ESPHome runs its shutdown hooks
        ok = await wait_for(lambda: [p for _, p in a.commands(sim.MSG_HOLD, t)][:1] == [(30,)], 1)
        check("planned restart asks Board A to hold", ok, str(a.commands(sim.MSG_HOLD, t)))
        # while Board B was down, someone's automation... no: Board A keeps its level. Make the saved
        # state disagree with Board A, to prove Board A's level wins after a restart.
        with a.lock:
            a.level_link = level_of(0.33)
            a._fade(a.level_link, 0.0)
        a.t0 -= 3600  # Board A has been up an hour
        t = time.monotonic()
        dev.lines.clear()
        dev.start()
        await api.connect()
        await asyncio.sleep(2.0)
        lt = api.states.get("Light")
        check("restart: Board A's level adopted", lt is not None and lt.state and
              level_of(lt.brightness) == level_of(0.33), f"{lt}")
        check("  ... without sending anything", levels(a, t) == [], str(levels(a, t)))
        check("  ... logged", dev.saw("already running", t))

        # an unplanned restart (crash): Board A falls back, Board B restores the level when it's back
        await asyncio.sleep(0.5)
        await api.close()
        a.hold_until = 0.0  # long after the planned restart above
        dev.stop(signal.SIGKILL)
        await asyncio.sleep(2.5)  # past Board A's 1.5 s link timeout
        check("crash: Board A fell back", a.fallback and a.level_target == level_of(0.3),
              f"fallback={a.fallback} target={a.level_target}")
        t = time.monotonic()
        dev.start()
        await api.connect()
        ok = await wait_for(lambda: levels(a, t) == [(level_of(0.33), 1000)], 4)
        check("crash: level from before the loss restored", ok, str(levels(a, t)))
        lt = api.states.get("Light")
        check("  ... and shown", lt is not None and lt.state and level_of(lt.brightness) == level_of(0.33), f"{lt}")

        # both boards power up together: the saved state is restored with a fade
        await api.light(state=True, brightness=0.45, transition_length=0.0)
        await asyncio.sleep(1.0)
        await api.close()
        dev.stop(signal.SIGTERM)
        a.reset(uptime_s=0.0)
        t = time.monotonic()
        dev.start()
        await api.connect()
        ok = await wait_for(lambda: levels(a, t)[:1] == [(level_of(0.45), 1000)], 4)
        check("power-up: saved state restored with a 1 s fade", ok, str(levels(a, t)))
    except Exception:
        import traceback
        traceback.print_exc()
        check("test ran to the end", False)
    finally:
        await api.close()
        dev.stop()
        a.close()
        shutil.rmtree(prefdir, ignore_errors=True)
        failed = [r for r in results if not r[1]]
        print(f"\n{len(results)} checks, {len(failed)} failures")
        if failed:
            print("--- device log (last 60 lines) ---")
            for _, line in dev.lines[-60:]:
                print(line)
        sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
