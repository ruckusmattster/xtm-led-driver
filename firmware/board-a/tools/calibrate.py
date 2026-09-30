#!/usr/bin/env python3
"""Board A current and light calibration over the STLINK-V3MINIE virtual COM port.

Current calibration (per fixture, once):
    python3 calibrate.py current --port /dev/ttyACM0            # you type each DMM reading
    python3 calibrate.py current --port COM5 --dmm "USB0::0x2A8D::0x1301::MY5700XXXX::INSTR"
                                                                  # reads a SCPI DMM (Keysight 3446x style)
Light calibration (per fixture, after the current calibration; lux meter at a fixed distance):
    python3 calibrate.py lux --port /dev/ttyACM0
Fleet reference (after every fixture has its light calibration):
    python3 calibrate.py fleet --port /dev/ttyACM0 --ref 850      # the dimmest fixture's full-scale lux

Wiring for the current calibration: the DMM's current input in series with the LED's anode lead
(LED+ from J2 pin 2 to the DMM, DMM to the XTM's red lead). Board A raises V_out to cover the
meter's burden voltage by itself. Needs: pip install pyserial (and pyvisa for --dmm).
"""
import argparse
import re
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")

# (channel, nominal amps) pairs, lowest point first; each band's current is measured on both
# channels that share it, on the same meter range, so the crossovers match.
POINTS = [(4, 140e-6), (4, 1.5e-3), (3, 1.5e-3), (3, 15e-3), (2, 15e-3), (2, 150e-3), (1, 150e-3), (1, 1.4)]
KEEPALIVE = [3, 2, 1]


class Console:
    def __init__(self, port):
        self.s = serial.Serial(port, 115200, timeout=0.2)
        time.sleep(0.2)
        self.s.reset_input_buffer()

    def cmd(self, line, timeout=3.0):
        self.s.write((line + "\r\n").encode())
        out, t0 = [], time.time()
        while time.time() - t0 < timeout:
            raw = self.s.readline().decode(errors="replace").strip()
            if not raw:
                continue
            out.append(raw)
            if raw.startswith("ok") or raw.startswith("err"):
                if raw.startswith("err"):
                    raise RuntimeError(f"{line!r}: {raw}")
                return out
        raise TimeoutError(f"no reply to {line!r}")

    def status(self):
        line = next(l for l in self.cmd("st") if l.startswith("state="))
        return dict(kv.split("=", 1) for kv in line.split())


class ManualMeter:
    def read(self, prompt):
        while True:
            v = input(f"  {prompt}: ").strip().lower().replace("a", "")
            m = re.fullmatch(r"([-+0-9.e]+)\s*([munk]?)", v)
            if m:
                scale = {"": 1, "m": 1e-3, "u": 1e-6, "n": 1e-9, "k": 1e3}[m.group(2)]
                return float(m.group(1)) * scale
            print("  enter a number, e.g. 1.4983m or 0.0014983")


class ScpiMeter:
    def __init__(self, resource):
        import pyvisa
        self.dmm = pyvisa.ResourceManager().open_resource(resource)
        self.dmm.timeout = 20000
        self.dmm.write("*RST")
        self.dmm.write("CONF:CURR:DC AUTO")
        self.dmm.write("CURR:DC:NPLC 10")

    def read(self, prompt):
        vals = [float(self.dmm.query("READ?")) for _ in range(5)]
        v = sorted(vals)[2]
        print(f"  {prompt}: {v:.7g} A")
        return v


def settle(con, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        st = con.status()
        if st["state"] == "fault":
            raise RuntimeError(f"fault {st['fault']} during calibration")
        time.sleep(0.5)


def current(args):
    con = Console(args.port)
    meter = ScpiMeter(args.dmm) if args.dmm else ManualMeter()
    print("Current calibration. Keep the fixture's heatsink attached; the 1.4 A point runs for 30 s.")
    for ch in (1, 2, 3, 4):
        con.cmd(f"calreset {ch}")
    con.cmd("dark")
    settle(con, 3)
    dark = meter.read("dark current, every sink off (expect tens of nA)")
    con.cmd(f"dark_a {dark:.6g}")
    for ch, amps in POINTS:
        con.cmd(f"rawi {ch} {amps:.6g}")
        settle(con, 30 if amps > 1 else 3)
        m = meter.read(f"ch{ch} near {amps:g} A")
        con.cmd(f"cal {ch} {m:.7g}")
    for ch in KEEPALIVE:
        con.cmd(f"ka {ch}")
        settle(con, 3)
        m = meter.read(f"ch{ch} keep-alive (tens of nA to hundreds of uA)")
        con.cmd(f"cal {ch} {m - dark:.7g}")
    con.cmd("exit")
    for line in con.cmd("calshow"):
        print(" ", line)
    con.cmd("save")
    print("Saved (it is written as soon as the light is off). Next: the light calibration, or you're done.")


def lux(args):
    con = Console(args.port)
    print("Light calibration: lux meter on the beam axis at the distance you'll use for every fixture.")
    print("Room dark; let the fixture run 5 minutes at full first so the reading is warm.")
    pts = []
    for amps in (0.14, 1.4):
        con.cmd(f"rawi 1 {amps:g}")
        settle(con, 60 if amps > 1 else 20)
        st = con.status()
        v = float(input(f"  lux at {float(st['i']):.4g} A: "))
        pts.append((float(st["i"]), v))
    con.cmd("exit")
    (i0, v0), (i1, v1) = pts
    for pid, val in ((2, i0), (3, v0), (4, i1), (5, v1)):
        con.cmd(f"set {pid} {val:.7g}")
    con.cmd("save")
    print(f"Stored. This fixture gives {v1:.0f} lux at full current.")
    print("When every fixture is done, run 'fleet --ref <lowest full-current lux>' on each.")


def fleet(args):
    con = Console(args.port)
    con.cmd(f"set 6 {args.ref:.7g}")
    con.cmd("save")
    print(f"Fleet reference set to {args.ref:g} lux (0 turns light matching off).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="what", required=True)
    for name in ("current", "lux", "fleet"):
        p = sub.add_parser(name)
        p.add_argument("--port", required=True)
        if name == "current":
            p.add_argument("--dmm", help="VISA resource of a SCPI multimeter (optional)")
        if name == "fleet":
            p.add_argument("--ref", type=float, required=True)
    args = ap.parse_args()
    {"current": current, "lux": lux, "fleet": fleet}[args.what](args)


if __name__ == "__main__":
    main()
