"""Design calculations for the 4-decade XTM driver, Board A.

Run:  python3 calc.py            (prints the report used in the Phase 2 design,
                                 docs/design-record/phase2-detailed-design.md)
Every number that design quotes comes from this file or from sim/handover.c,
which this script compiles and runs for section 5.
Needs python3 with numpy, and gcc for section 5.
"""
import math
import os
import subprocess

import numpy as np

pi = math.pi
VT = 0.02585            # thermal voltage at 27 C
HERE = os.path.dirname(os.path.abspath(__file__))


def hdr(title):
    print("\n" + "=" * 78 + "\n" + title + "\n" + "=" * 78)


def rss(v):
    return math.sqrt(sum(x * x for x in v))


# ---------------------------------------------------------------------------
# 1. Setpoint chain: DAC80504 (2.5 V reference halved by REF-DIV, gain 2: 2.5 V FS) into a /13 divider
# ---------------------------------------------------------------------------
DAC_FS = 2.5
R_DT, R_DB = 12.0e3, 1.00e3          # divider top / bottom (Yageo RT0805, 0.1 %, 25 ppm/C)
C_DIV = 10e-9                        # C0G across the bottom resistor
DIV = R_DB / (R_DT + R_DB)
FS_SENSE = DAC_FS * DIV
LSB = FS_SENSE / 65536
R_DIV_THEV = R_DT * R_DB / (R_DT + R_DB)

# Channel table: shunt, range bottom/top (A), top of the blend band above it
CH = {
    1: dict(name="0.1 ohm", Rs=0.1, lo=0.140, hi=1.40, top=1.50),
    2: dict(name="1 ohm", Rs=1.0, lo=14e-3, hi=0.140, top=0.160),
    3: dict(name="10 ohm", Rs=10.0, lo=1.4e-3, hi=14e-3, top=16e-3),
    4: dict(name="100 ohm", Rs=100.0, lo=140e-6, hi=1.4e-3, top=1.6e-3),
}

hdr("1. Setpoint chain")
print(f"Divider {R_DT/1e3:.1f}k/{R_DB/1e3:.2f}k -> ratio 1/{1/DIV:.0f}; sense full scale {FS_SENSE*1e3:.1f} mV; "
      f"LSB {LSB*1e6:.3f} uV; Thevenin {R_DIV_THEV:.0f} ohm; with {C_DIV*1e9:.0f} nF C0G, tau {R_DIV_THEV*C_DIV*1e6:.1f} us")
for k, c in CH.items():
    v_lo, v_top = c['lo'] * c['Rs'], c['top'] * c['Rs']
    print(f"ch{k} ({c['name']}): {v_lo*1e3:.0f}-{v_top*1e3:.0f} mV sense -> codes {v_lo/LSB:.0f}-{v_top/LSB:.0f} "
          f"(full scale is {FS_SENSE/v_top:.2f}x the band top); one code at range bottom = {LSB/v_lo*100:.4f} %")
assert FS_SENSE > 1.15 * 0.160, "full scale must clear the 160 mV blend-band top with margin"

# Zero bias: BIAS node = +5VA * 1k/11k, then 1.82 Mohm into each -IN; R_IN 1k to the Kelvin sense
V_BIAS_SRC = 5.0 * 1.0 / 11.0
R_BIAS, R_IN = 1.82e6, 1.00e3
I_BIAS = V_BIAS_SRC / R_BIAS
V_ZERO = I_BIAS * R_IN
DAC_ZERO_MAX, OPA_VOS_MAX = 1.5e-3, 10.5e-6
print(f"Zero bias: {I_BIAS*1e9:.0f} nA -> {V_ZERO*1e6:.0f} uV at -IN; worst-case code-0 input "
      f"{(DAC_ZERO_MAX*DIV + OPA_VOS_MAX)*1e6:.0f} uV -> margin {(V_ZERO - DAC_ZERO_MAX*DIV - OPA_VOS_MAX)*1e6:.0f} uV")
print(f"  bias falls to {(V_BIAS_SRC-0.160)/R_BIAS*1e9:.0f} nA at 160 mV setpoint: a {R_IN/R_BIAS*100:.3f} % linear gain term, "
      f"removed by the two-point calibration")
for k, c in CH.items():
    print(f"  ch{k}: dead zone (code-0 margin) = {(V_ZERO + I_BIAS*c['Rs'])/c['Rs']*1e6:8.1f} uA-equivalent")
assert V_ZERO > 1.5 * (DAC_ZERO_MAX * DIV + OPA_VOS_MAX)

# Keep-alive: an armed channel regulates E_KA of sense above its calibrated dead-zone edge
E_KA = 25e-6
print(f"Keep-alive: {E_KA*1e6:.0f} uV above the dead-zone edge -> " +
      ", ".join(f"ch{k} {E_KA/c['Rs']*1e6:g} uA" for k, c in CH.items()))

# ---------------------------------------------------------------------------
# 2. Error budget per range (after calibration, board within +-20 C of calibration)
# ---------------------------------------------------------------------------
hdr("2. Error budget")
dT = 20.0
off_terms = {
    "op-amp offset drift 0.05 uV/C max": 0.05 * dT,
    "DAC INL left after 2-point cal, +-1 LSB": LSB * 1e6,
    "DAC offset drift 1 uV/C x1.5 margin, /13": 1.0 * 1.5 * dT * DIV,
    "thermal EMF at shunt terminations": 1.0,
    "op-amp Ib 800 pA max into ~1 kohm": 800e-12 * max(R_DIV_THEV, R_IN) * 1e6,
    "zero-bias drift (1.82M 100 ppm/C, divider, LDO)": V_ZERO * 1e6 * (100e-6 + 50e-6 + 100e-6) * dT,
}
off_terms_ch1 = dict(off_terms, **{"thermal EMF at shunt terminations": 2.0})
gain_common = {"DAC ref 5 ppm/C max + gain drift 1 ppm/C": 6 * dT,
               "divider ratio, 2 x 25 ppm/C (RSS)": math.sqrt(2) * 25 * dT}
gain_ch = {1: {"WSK2512 35 ppm/C": 35 * dT, "self-heating residual": 100.0},
           2: {"thin film 25 ppm/C": 25 * dT}, 3: {"thin film 25 ppm/C": 25 * dT},
           4: {"thin film 25 ppm/C": 25 * dT}}
gain_worst_div = 2 * 25 * dT                   # worst case: the two resistors drift in opposite directions
LEAK = 70e-9                                   # estimated cathode-node leakage at 55 C (section 10)
OFF_RSS, OFF_LIN = rss(off_terms.values()), sum(off_terms.values())
OFF1_RSS, OFF1_LIN = rss(off_terms_ch1.values()), sum(off_terms_ch1.values())
for name, v in off_terms.items():
    print(f"  offset  {name:50s} {v:5.2f} uV")
print(f"  offset RSS (ch2-4) {OFF_RSS:.2f} uV (sum {OFF_LIN:.2f}), ch1 {OFF1_RSS:.2f} uV (sum {OFF1_LIN:.2f})")
for k in CH:
    g = dict(gain_common, **gain_ch[k])
    print(f"  gain ch{k}: " + ", ".join(f"{n} {v:.0f} ppm" for n, v in g.items()))


def budget(k, I, extra_rss=0.0, extra_lin=0.0):
    """Return (RSS %, worst %) at current I on channel k. extra_* are absolute currents (A)."""
    c = CH[k]
    o_r, o_l = (OFF1_RSS, OFF1_LIN) if k == 1 else (OFF_RSS, OFF_LIN)
    s = I * c['Rs'] * 1e6
    g = dict(gain_common, **gain_ch[k])
    g_r = rss(g.values()) * 1e-4
    g_l = (sum(g.values()) - g["divider ratio, 2 x 25 ppm/C (RSS)"] + gain_worst_div) * 1e-4
    lk = LEAK / I * 100 if k == 4 else 0.0
    r = math.sqrt((o_r / s * 100) ** 2 + g_r ** 2 + lk ** 2 + (extra_rss / I * 100) ** 2)
    w = o_l / s * 100 + g_l + lk + extra_lin / I * 100
    return r, w


print(f"\n  {'range':6s} {'shunt':8s} {'current':>11s} {'sense':>9s} {'RSS':>8s} {'worst':>8s}  note")
rows = []
for k, c in CH.items():
    for I in (c['lo'], c['hi']):
        r, w = budget(k, I)
        rows.append((str(k), c['name'], I, r, w, ""))
for I in (14e-6, 5e-6):
    r, w = budget(4, I)
    rows.append(("tail", CH[4]['name'], I, r, w, ""))
# keep-alive of the next channel up, armed from half the band bottom: its drift is an absolute error
for k_act, k_ka in ((4, 3), (3, 2), (2, 1)):
    I = CH[k_ka]['lo'] / 2
    ka_rss = OFF_RSS * 1e-6 / CH[k_ka]['Rs'] if k_ka > 1 else OFF1_RSS * 1e-6 / CH[k_ka]['Rs']
    ka_lin = OFF_LIN * 1e-6 / CH[k_ka]['Rs'] if k_ka > 1 else OFF1_LIN * 1e-6 / CH[k_ka]['Rs']
    r, w = budget(k_act, I, ka_rss, ka_lin)
    rows.append((str(k_act), CH[k_act]['name'], I, r, w, f"ch{k_ka} keep-alive armed"))
for kk, n, I, r, w, note in rows:
    cur = f"{I*1e3:.3f} mA" if I < 1 else f"{I:.2f} A"
    sense = I * CH[4 if kk == 'tail' else int(kk)]['Rs'] * 1e3
    print(f"  {kk:6s} {n:8s} {cur:>11s} {sense:7.2f}mV {r:7.3f}% {w:7.3f}%  {note}")
print("  (range-4 and tail rows include ~70 nA of board/FET leakage, always additive)")
# Range 1 with the in-stock fallback shunt (two-terminal WSL2512, +-75 ppm/C) on the same pads
_wsk = gain_ch[1]
gain_ch[1] = {"WSL2512 75 ppm/C": 75 * dT, "self-heating residual": 100.0}
for I in (CH[1]['lo'], CH[1]['hi']):
    r, w = budget(1, I)
    cur = f"{I*1e3:.3f} mA" if I < 1 else f"{I:.2f} A"
    print(f"  {'1':6s} {'WSL2512':8s} {cur:>11s} {I*0.1*1e3:7.2f}mV {r:7.3f}% {w:7.3f}%  fallback shunt")
gain_ch[1] = _wsk

# ---------------------------------------------------------------------------
# 3. LED output network: C_a across the LED vs C_g cathode-to-ground
# ---------------------------------------------------------------------------
hdr("3. V_out ripple -> LED current, with and without C_a across the LED")
nNVT = 0.65
C_OSS_NDT_1V = 110e-12 * math.sqrt(25.7 / 1.7)      # C_oss ~ 1/sqrt(V+phi), from 110 pF at 25 V
C_OSS_SMALL_1V = 6.8e-12 * math.sqrt(10.7 / 1.7)     # 2N7002 6.8 pF at 10 V
C_G = C_OSS_NDT_1V + 3 * C_OSS_SMALL_1V + 20e-12 + 1e-12
C_A_NOM, C_A_EFF = 22e-9, 22e-9 * 0.7                # X7R 100 V 1206 at ~30 V bias keeps ~70 %
C_NODE = C_A_EFF + C_G
print(f"C_g estimate {C_G*1e12:.0f} pF (NDT3055L {C_OSS_NDT_1V*1e12:.0f} pF at 1 V, 3 small FETs, trace, tap); "
      f"C_a {C_A_NOM*1e9:.0f} nF nominal, ~{C_A_EFF*1e9:.1f} nF at 30 V")


def i_led_per_v(I, f, Cg, Ca):
    rd = nNVT / I
    s = 2j * pi * f
    return abs(s * Cg / (1 + s * rd * (Ca + Cg)))


FREQS = (100, 1e3, 10e3, 20e3, 400e3)
print(f"\n  V_out ripple giving 1 % LED-current modulation (mV):")
print(f"  {'I_LED':>9s}        " + " ".join(f"{f:>9.0f}Hz" for f in FREQS))
for I in (5e-6, 14e-6, 140e-6, 1.4e-3, 14e-3, 140e-3, 1.4):
    no_ca = [0.01 * I / i_led_per_v(I, f, C_G, 0) * 1e3 for f in FREQS]
    ca = [0.01 * I / i_led_per_v(I, f, C_G, C_A_EFF) * 1e3 for f in FREQS]
    print(f"  {I*1e3:8.3f}mA  no C_a: " + " ".join(f"{x:11.1f}" for x in no_ca))
    print(f"  {'':9s}  C_a   : " + " ".join(f"{x:11.1f}" for x in ca))
worst_no = min(0.01 * I / i_led_per_v(I, f, C_G, 0) for I in (5e-6, 140e-6) for f in (1e3, 10e3, 20e3))
worst_ca = min(0.01 * I / i_led_per_v(I, f, C_G, C_A_EFF) for I in (5e-6, 140e-6) for f in (100, 1e3, 10e3, 20e3))
print(f"  worst in 0.1-20 kHz down to 5 uA: {worst_no*1e3:.1f} mV without C_a, {worst_ca*1e3:.0f} mV with C_a")
for cg in (0.25e-9, 1e-9):
    w = min(0.01 * I / i_led_per_v(I, f, cg, C_A_EFF) for I in (5e-6, 140e-6) for f in (100, 1e3, 10e3, 20e3))
    print(f"  sensitivity: C_g = {cg*1e12:.0f} pF -> {w*1e3:.0f} mV")
print(f"  C_a ripple current at 400 kHz, 30 mV p-p: {2*pi*400e3*C_A_EFF*0.030*1e3:.2f} mA p-p (stays on the board)")

# ---------------------------------------------------------------------------
# 4. Sink loops
# ---------------------------------------------------------------------------
hdr("4. Sink loop stability (C_C 2.2 nF on all four channels)")
GBW, A0, P2 = 10e6, 10 ** (126 / 20), 30e6
R_G, R_O = 220.0, 100.0
C_C = 2.2e-9
TAU = R_IN * C_C
fets = {"NDT3055L": dict(K=7.0 ** 2 / (2 * 4.0), Ciss=345e-12, Crss=30e-12, n=1.6),
        "2N7002BK": dict(K=0.5, Ciss=33e-12, Crss=4e-12, n=1.5),
        "2N7002": dict(K=0.3, Ciss=31e-12, Crss=4e-12, n=1.5)}
chan = {1: ("NDT3055L", 0.1), 2: ("2N7002BK", 1.0), 3: ("2N7002", 10.0), 4: ("2N7002", 100.0)}


def gm_of(fet, I):
    p = fets[fet]
    return min(math.sqrt(2 * p['K'] * I), I / (p['n'] * VT))


def loop(fet, Rs, Cc, I):
    p = fets[fet]
    gm = gm_of(fet, I)
    f = np.logspace(0, 8, 8000)
    s = 2j * pi * f
    A = A0 / (1 + s * A0 / (2 * pi * GBW)) / (1 + s / (2 * pi * P2))
    integ = 1 / (1 / A + s * R_IN * Cc * (1 + 1 / A))
    Cgs = p['Ciss'] - p['Crss']
    gate = 1 / (1 + s * (R_G + R_O) * p['Ciss'])
    y = gm + s * Cgs
    sf = y * Rs / (1 + y * Rs)
    T = integ * gate * sf
    mag = np.abs(T)
    i = int(np.argmax(mag < 1))
    pm = 180 + np.degrees(np.angle(T[i]))
    return gm, f[i], pm, gm * Rs / (1 + gm * Rs)


for k, (fet, Rs) in chan.items():
    c = CH[k]
    currents = [E_KA / Rs, c['lo'], c['top']]
    if k == 4:
        currents.insert(1, 5e-6)
    for I in currents:
        gm, fc, pm, att = loop(fet, Rs, C_C, I)
        tag = "keep-alive" if I == E_KA / Rs else ""
        print(f"  ch{k} {fet:9s} Rs={Rs:>5}  I={I*1e3:10.5f} mA  gm={gm:9.5f} S  follower {att:.4f}  "
              f"crossover {fc/1e3:8.3f} kHz  PM {pm:5.1f} deg {tag}")
        assert pm > 60, "phase margin"
for rds in (4.0, 10.0):
    print(f"  clamp: 2N7002BK at Vgs 3.3 V, Rds ~{rds:.0f} ohm -> gate held at {4.9*rds/(R_G+rds)*1e3:.0f} mV "
          f"with the op-amp at its 4.9 V rail (NDT3055L Vth min 1.0 V at 25 C, ~0.7 V at 100 C)")
v_rip = 30e-3
i_m = 2 * pi * 400e3 * fets['NDT3055L']['Crss'] * v_rip
print(f"  Miller: 30 mV of 400 kHz on the drain -> {i_m*1e6:.1f} uA into the gate -> "
      f"{i_m*(R_G+R_O)*1e3:.2f} mV -> {gm_of('NDT3055L',1.4)*i_m*(R_G+R_O)/1.4*100:.2f} % at 1.4 A (out of band)")

# Priming: an armed channel leaves its dead zone and winds its integrator from 0 V to V_on
print("\n  Priming (dead zone -> keep-alive), integrator ramps at e/tau until the FET conducts:")
for fet, vth in (("2N7002", 1.0), ("2N7002", 2.5), ("NDT3055L", 1.0), ("NDT3055L", 2.0)):
    p = fets[fet]
    Rs = 10.0 if fet == "2N7002" else 0.1
    I = E_KA / Rs
    i_s = 2 * p['n'] ** 2 * VT ** 2 * p['K']
    v_on = vth + p['n'] * VT * math.log(I / i_s)
    for e in (E_KA - OFF_LIN * 1e-6, E_KA):
        print(f"    {fet:8s} Vth {vth:.1f} V: V_on at {I*1e6:g} uA = {v_on:.2f} V; e = {e*1e6:4.1f} uV -> "
              f"{v_on*TAU/e*1e3:5.0f} ms")
print(f"  gate-monitor tap: 100k/100k from each op-amp output, 1 nF at the ADC pin -> 0-2.45 V, tau 50 us, "
      f"load {4.9/200e3*1e6:.0f} uA max")

# ---------------------------------------------------------------------------
# 5. Handover dynamics (time-domain model in sim/handover.c)
# ---------------------------------------------------------------------------
hdr("5. Blend-band handover during fades (sim/handover.c)")
sim_dir = os.path.join(HERE, "sim")
exe = os.path.join(sim_dir, "handover")
src = os.path.join(sim_dir, "handover.c")
if not os.path.exists(exe) or os.path.getmtime(exe) < os.path.getmtime(src):
    subprocess.run(["gcc", "-O2", "-o", exe, src, "-lm"], check=True)
print("  Fade time is for the full 5 uA-1.4 A range; a shorter fade over part of the range with the same")
print("  rate of change in log(I) behaves the same.  Deviation of the summed sink current from the ideal")
print("  curve, after a 1 ms low-pass (roughly what an eye or a 240 fps frame integrates):")
for primed in (1, 0):
    for band in (1, 2, 3):
        for T in (1, 10, 60):
            if not primed and T == 60:
                continue
            for d in (1, -1):
                if not primed and d == -1:
                    continue
                out = subprocess.run([exe, str(band), str(T), str(primed), "2.2", str(d)],
                                     capture_output=True, text=True, check=True, env=dict(os.environ, BLEND="1"))
                print("  " + out.stdout.strip())

# ---------------------------------------------------------------------------
# 6. Tracking buck (LMR38020F, 400 kHz) and DAC injection network
# ---------------------------------------------------------------------------
hdr("6. Tracking buck and FB injection")
VIN, FSW = 48.0, 400e3
L2, L2_TOL = 33e-6, 0.2
R_FBT, R_FBB, R_INJ1, R_INJ2, C_INJ = 200e3, 7.32e3, 8.25e3, 8.25e3, 47e-9
VREF = 1.0
R_INJ = R_INJ1 + R_INJ2
K_INJ = R_FBT / R_INJ


def vout_of(vd):
    return VREF + R_FBT * (VREF / R_FBB + (VREF - vd) / R_INJ)


DAC_LO, DAC_HI = 0.2, 3.1          # STM32G4 buffered DAC output range assumed (0.2 V from each rail)
print(f"FB: {R_FBT/1e3:.0f}k / {R_FBB/1e3:.2f}k, injection {R_INJ1/1e3:.2f}k + {R_INJ2/1e3:.2f}k from PA4 (DAC1_OUT1), "
      f"{C_INJ*1e9:.0f} nF at the mid-point")
print(f"  V_out = {vout_of(0):.2f} - {K_INJ:.2f} x V_dac")
print(f"  DAC {DAC_LO} V (buffer low limit) -> {vout_of(DAC_LO):.2f} V (highest usable); DAC 0 V (fault) -> "
      f"{vout_of(0):.2f} V ceiling; DAC {DAC_HI} V -> {vout_of(DAC_HI):.2f} V; blackout floor at 3.05 V -> {vout_of(3.05):.2f} V")
print(f"  DAC pin high-impedance -> {VREF*(1+R_FBT/R_FBB):.1f} V target, but the buck is disabled whenever the MCU is in reset")
need = 36.0 + 1.0
print(f"  needed: worst-case V_f 36.0 V + 1.0 V headroom = {need:.1f} V -> margin {vout_of(DAC_LO)-need:.2f} V at the DAC's low limit")
assert vout_of(DAC_LO) >= need + 0.5 and vout_of(0) <= 41.0 and vout_of(DAC_HI) >= 2.8
print(f"  12-bit DAC on 3.3 V: {3.3/4096*1e3:.3f} mV/LSB -> {3.3/4096*K_INJ*1e3:.1f} mV of V_out per code")
print(f"  DAC load: sinks {(VREF-DAC_LO)/R_INJ*1e6:.0f} uA at {DAC_LO} V, sources {(DAC_HI-VREF)/R_INJ*1e6:.0f} uA at {DAC_HI} V")
r_mid = R_INJ1 * R_INJ2 / (R_INJ1 + R_INJ2)
print(f"  injection filter pole {1/(2*pi*r_mid*C_INJ):.0f} Hz (tau {r_mid*C_INJ*1e3:.2f} ms): V_out settles to 95 % "
      f"in ~{3*r_mid*C_INJ*1e3:.1f} ms after a DAC step")
z_bot_ac = R_FBB * R_INJ1 / (R_FBB + R_INJ1)
g_ac = z_bot_ac / (R_FBT + z_bot_ac)
for vo in (20, 30, 38):
    print(f"  loop gain vs. a plain divider at {vo} V: x{g_ac/(VREF/vo):.2f} (lower crossover, more phase margin)")
L_min = 0.25 * 39 / FSW
print(f"  L_min (datasheet, M=0.25) at 39 V = {L_min*1e6:.1f} uH; SRR1260-330M min {L2*(1-L2_TOL)*1e6:.1f} uH -> "
      f"{'OK' if L2*(1-L2_TOL) >= L_min else 'FAIL'}")
assert L2 * (1 - L2_TOL) >= L_min
TON_MIN, TOFF_MIN = 131e-9, 300e-9
for vin, vo in ((48.0, 3.5), (52.8, 3.5), (48.0, 20.0), (48.0, 30.0), (48.0, 38.0), (48.0, 40.44), (43.2, 38.0)):
    d = vo / vin
    ton, toff = d / FSW, (1 - d) / FSW
    ripple = (vin - vo) * d / (L2 * FSW)
    print(f"  Vin {vin:4.1f} V, V_out {vo:5.2f} V: D {d:.3f}, t_on {ton*1e9:5.0f} ns, t_off {toff*1e9:5.0f} ns, "
          f"ripple {ripple:.2f} A p-p, peak at 1.4 A {1.4 + ripple/2:.2f} A")
    assert ton >= TON_MIN and toff >= TOFF_MIN
C_OUT = 4 * 4.7e-6 * 0.55
for vo in (20.0, 30.0):
    d = vo / VIN
    ripple = (VIN - vo) * d / (L2 * FSW)
    print(f"  V_out ripple at {vo:.0f} V: {ripple/(8*FSW*C_OUT)*1e3:.0f} mV p-p with {C_OUT*1e6:.1f} uF effective")


def buck_loss(vo, io, vin=VIN, f=FSW):
    d = vo / vin
    ripple = (vin - vo) * d / (L2 * f)
    irms = math.sqrt(io ** 2 + ripple ** 2 / 12)
    cond = irms ** 2 * (0.303 * d + 0.133 * (1 - d))
    sw = 0.5 * vin * io * 10e-9 * f
    ind = irms ** 2 * 0.060 + 0.1
    return cond + sw + 0.05, ind


ic, ind = buck_loss(31.0, 1.4)
print(f"  losses at 31 V / 1.4 A: IC {ic:.2f} W, inductor {ind:.2f} W, efficiency {31*1.4/(31*1.4+ic+ind)*100:.1f} %")
ic0, ind0 = buck_loss(20.0, 0.0)
print(f"  forced-PWM with the LED dark at 20 V: IC {ic0:.2f} W, inductor {ind0:.2f} W")
L3, F3 = 15e-6, 500e3
R3T, R3B = 100e3, 22.1e3
v5 = VREF * (1 + R3T / R3B)
d = v5 / VIN
print(f"Aux buck: {v5:.3f} V; t_on {d/F3*1e9:.0f} ns; ripple {(VIN-v5)*d/(L3*F3):.2f} A p-p; L_min {0.25*v5/F3*1e6:.1f} uH")
R_ENT, R_ENB = 280e3, 10e3
print(f"  aux UVLO: on {1.25*(1+R_ENT/R_ENB):.1f} V typ (EN threshold 1.1-1.4 V -> {1.1*(1+R_ENT/R_ENB):.1f}-"
      f"{1.4*(1+R_ENT/R_ENB):.1f} V)")
print(f"  RT: main 64.9k -> 400 kHz (table), aux 52.3k -> 500 kHz (table)")
for name, rt, rb, vmax in (("V_out", 1.0e6, 82e3, 40.44), ("48 V", 100e3, 6.2e3, 52.8)):
    print(f"{name} sense: {rt/1e3:.0f}k/{rb/1e3:.1f}k -> {vmax:.1f} V reads {vmax*rb/(rt+rb):.2f} V "
          f"(Thevenin {rt*rb/(rt+rb)/1e3:.1f} k)")

# ---------------------------------------------------------------------------
# 7. Turn-on, turn-off and the voltage-mode tail
# ---------------------------------------------------------------------------
hdr("7. Turn-on from blackout, final fade to black")
dv = 20.4 - 3.5
print(f"  blackout: sinks in their dead zones, V_out at the 3.5 V floor -> the array cannot conduct")
for I in (5e-6, 140e-6, 1e-3, 0.1):
    t = C_NODE * dv * 0.97 / I
    print(f"  turn-on to {I*1e6:g} uA: V_out rises first (C_a lifts the cathode ~{dv*0.97:.0f} V), then the sink pulls "
          f"it back down in {t*1e3:.2f} ms; the LED current rises only in the last ~2 V")
print(f"  voltage-mode tail: one buck-DAC code = {3.3/4096*K_INJ*1e3:.1f} mV -> "
      f"{(math.exp(3.3/4096*K_INJ/nNVT)-1)*100:.1f} % LED current per code; 1 decade per {nNVT*math.log(10):.2f} V of V_out")
for I in (5e-6, 1e-6, 100e-9, 10e-9):
    print(f"    natural decay limit at {I*1e9:6.0f} nA: e-fold in {C_NODE*nNVT/I*1e3:7.1f} ms")
print(f"  sink release from 5 uA without the tail: I(t) = C nNV_T/(t + {C_NODE*nNVT/5e-6*1e3:.1f} ms) -> "
      f"0.5 uA after {C_NODE*nNVT*(1/0.5e-6-1/5e-6)*1e3:.0f} ms")

# ---------------------------------------------------------------------------
# 8. Power and thermal (Board A cooled by its own copper, 90 x 60 mm, 4 layers)
# ---------------------------------------------------------------------------
hdr("8. Power and thermal")
aux = 1.0
for vf in (29.9, 36.0):
    led = 1.4 * vf
    fet = (1.0 - 0.14) * 1.4
    sh = 1.4 ** 2 * 0.1
    icl, indl = buck_loss(vf + 1.0, 1.4)
    tot = led + fet + sh + icl + indl + aux
    print(f"  V_f {vf} V: LED {led:.1f} W, FET {fet:.2f} W, shunt {sh:.2f} W, buck {icl+indl:.2f} W, aux+Board B {aux:.1f} W "
          f"-> 48 V load {tot:.1f} W = {tot/110.4*100:.0f} % of LRS-100-48")
board_a = 1.2 + 0.2 + ic + ind + 0.5
area = 0.090 * 0.060      # the Layout section's outline
h = 12.0
r_board = 1 / (h * 2 * area)
print(f"  Board A dissipation at full: {board_a:.1f} W; still air h ~{h:.0f} W/m2K both sides on {area*1e4:.0f} cm2 -> "
      f"{r_board:.1f} K/W, board average +{board_a*r_board:.0f} C over enclosure air")
# onsemi's datasheet: 42 C/W on a 1 in2 (6.5 cm2) pad of 2 oz copper, 95 C/W on 0.066 in2. Board A
# gives the tab ~2.2 cm2 of 1 oz on L1 and ~2.8 cm2 on L4, joined by ~40 vias: taken as 50 C/W.
rja_fet = 50.0
print(f"  NDT3055L 1.2 W at ~{rja_fet:.0f} C/W (SOT-223 tab on ~5 cm2 over L1 and L4, 1 oz) -> junction "
      f"+{1.2*rja_fet+board_a*r_board:.0f} C over air; at 45 C air: {45+1.2*rja_fet+board_a*r_board:.0f} C (150 C max)")
print(f"  headroom 0.8 V instead of 1.0 V at full current saves {0.2*1.4:.2f} W at the FET")
print(f"  short across the LED at full V_out: 1.4 A x 31 V = {1.4*31:.0f} W until the comparator trips (~0.1 ms)")
print(f"  V_out stuck at the 40.4 V ceiling with a 28.6 V LED: {(40.44-28.6-0.14)*1.4:.1f} W on the FET -> comparator trip")

# ---------------------------------------------------------------------------
# 9. Trace widths (IPC-2221, 1 oz outer, 0.5 oz inner, 10 C rise)
# ---------------------------------------------------------------------------
hdr("9. Trace widths (IPC-2221, 10 C rise)")


def width_mm(I, dT=10, oz=1.0, outer=True):
    k = 0.048 if outer else 0.024
    area_mil2 = (I / (k * dT ** 0.44)) ** (1 / 0.725)
    t_mil = 1.378 * oz
    return area_mil2 / t_mil * 0.0254


for net, I in (("48 V input", 1.5), ("V_out / LED+", 1.5), ("cathode, ch1 drain/source, 0.1 ohm force", 1.5),
               ("SW node (rms)", 1.5), ("ch2 force (160 mA)", 0.2), ("5.5 V aux", 0.6), ("signals", 0.05)):
    print(f"  {net:40s} {I:4.2f} A: outer 1 oz {width_mm(I):5.2f} mm, inner 0.5 oz {width_mm(I, oz=0.5, outer=False):5.2f} mm")

# ---------------------------------------------------------------------------
# 10. Leakage at the cathode node, range 4 (140 uA), 55 C, V_DS ~ 1 V
# ---------------------------------------------------------------------------
hdr("10. Leakage")


def scale(i_hot, t_hot, v_hot, t=55.0, v=1.0):
    return i_hot / 2 ** ((t_hot - t) / 10) * math.sqrt((v + 0.7) / (v_hot + 0.7))


l_ndt = scale(50e-6, 125, 60)
l_bk = scale(10e-6, 150, 60)
l_7002 = scale(10e-6, 150, 48)
total = l_ndt + l_bk + l_7002 + 2e-9 - 4e-9
print(f"  NDT3055L {l_ndt*1e9:.0f} nA, 2N7002BK {l_bk*1e9:.1f} nA, 2N7002 {l_7002*1e9:.1f} nA, tap 2 nA, "
      f"board -4 nA -> net {total*1e9:.0f} nA = {total/140e-6*100:.3f} % at 140 uA")
print(f"  cathode tap: 1 M into 1 nF, ADC 5 pF sampled at 100 Hz -> {5e-12*1.0*100*1e9:.1f} nA average")
