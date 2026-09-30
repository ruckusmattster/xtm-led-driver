#!/usr/bin/env python3
"""Flicker figures from a photodiode capture (a scope's CSV export: time, volts).

    python3 flicker.py capture.csv --dark 0.0012          # a steady level, DC-coupled
    python3 flicker.py ripple.csv --mean 2.013             # AC-coupled, DC level read separately
    python3 flicker.py fade.csv --fade                     # a fade: steps and dips instead

Steady level (the brief's limit: nothing over ~1% between 100 Hz and 20 kHz; anything
intentional at 25 kHz or above):
  - percent flicker, (max - min) / (max + min), after a 20 kHz low-pass;
  - the largest spectral line from 100 Hz to 20 kHz, as % of the mean;
  - the largest line at 25 kHz and above (the 400 kHz buck ripple lands here).
Fade: the mean is moving, so the script compares a 1 ms average with a 50 ms trend (taken in
log space, where the fade is a straight line) and reports the largest departure, the same
measure the handover simulation used (design/sim).

Capture at least 100 ms at 1 MS/s or faster. `--dark` is the output with the light off (the
amplifier's offset plus stray light), subtracted first. Needs numpy.
"""
import argparse
import csv
import sys

import numpy as np


def load(path):
    t, v = [], []
    with open(path, newline="") as f:
        for row in csv.reader(f):
            try:
                t.append(float(row[0]))
                v.append(float(row[1]))
            except (ValueError, IndexError):
                continue  # header or metadata lines
    if len(t) < 1000:
        sys.exit(f"{path}: only {len(t)} samples; export at least 100 ms at 1 MS/s")
    t, v = np.asarray(t), np.asarray(v)
    dt = float(np.median(np.diff(t)))
    return v, 1.0 / dt


def lowpass(x, fs, fc):
    """Zero-phase low-pass in the frequency domain: flat to fc, raised-cosine roll-off to 1.5 fc."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / fs)
    g = np.ones_like(f)
    roll = (f > fc) & (f < 1.5 * fc)
    g[roll] = 0.5 * (1 + np.cos(np.pi * (f[roll] - fc) / (0.5 * fc)))
    g[f >= 1.5 * fc] = 0.0
    return np.fft.irfft(X * g, n=len(x))


def boxcar(x, n):
    n = max(1, int(n))
    c = np.cumsum(np.insert(x, 0, 0.0))
    y = (c[n:] - c[:-n]) / n
    pad = (len(x) - len(y)) // 2
    return np.pad(y, (pad, len(x) - len(y) - pad), mode="edge")


def steady(v, fs, mean=None):
    """mean=None: a DC-coupled capture. Otherwise an AC-coupled one (finer vertical scale), with
    the DC level measured separately and passed in."""
    if mean is None:
        mean = float(np.mean(v))
    ac = v - np.mean(v)
    if mean <= 0:
        sys.exit("mean is not positive: check --dark, --mean and the amplifier's polarity")
    lp = lowpass(ac, fs, 20e3)
    trim = int(0.005 * fs)  # skip the filter's edges
    lp = lp[trim:-trim]
    pf = (lp.max() - lp.min()) / (2 * mean) * 100  # = (max - min) / (max + min)
    w = np.hanning(len(ac))
    spec = np.abs(np.fft.rfft(ac * w)) * 2 / np.sum(w)  # amplitude of each line
    f = np.fft.rfftfreq(len(ac), 1 / fs)
    band = (f >= 100) & (f <= 20e3)
    high = f >= 25e3
    k = np.argmax(spec * band)
    print(f"mean                       {mean:.6g} V")
    print(f"percent flicker (<20 kHz)  {pf:.3f} %")
    print(f"largest line 100 Hz-20 kHz {spec[k] / mean * 100:.3f} % at {f[k]:.0f} Hz")
    if high.any():
        kh = np.argmax(spec * high)
        print(f"largest line >= 25 kHz     {spec[kh] / mean * 100:.3f} % at {f[kh] / 1e3:.1f} kHz")
    ok = pf <= 1.0 and spec[k] / mean * 100 <= 1.0
    print("PASS" if ok else "FAIL: over 1 % between 100 Hz and 20 kHz")
    return ok


def fade(v, fs):
    # The fade engine moves log(current) linearly in time, so the trend is taken in log space,
    # where a 50 ms average of a straight line is unbiased. Departures are relative.
    floor = 1e-6 * float(np.max(v))
    lv = np.log(np.maximum(v, floor))
    fast = np.log(np.maximum(boxcar(v, 1e-3 * fs), floor))
    slow = boxcar(lv, 50e-3 * fs)
    trim = int(0.05 * fs)
    fast, slow, raw = fast[trim:-trim], slow[trim:-trim], v[trim:-trim]
    lit = raw > 0.02 * raw.max()  # ignore the dark end, where the ratio means little
    dev = np.where(lit, np.expm1(fast - slow), 0.0)
    k = int(np.argmax(np.abs(dev)))
    print(f"largest departure of the 1 ms average from the 50 ms trend: {dev[k] * 100:+.3f} % "
          f"at {(k + trim) / fs * 1e3:.1f} ms")
    steps = np.diff(slow[lit]) if lit.sum() > 1 else np.array([0.0])
    rising = np.mean(steps) >= 0
    reversals = int(np.sum(steps < 0)) if rising else int(np.sum(steps > 0))
    print(f"direction: {'rising' if rising else 'falling'}; samples where the 50 ms trend "
          f"moves the other way: {reversals}")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--dark", type=float, default=0.0, help="output with the light off, volts")
    ap.add_argument("--invert", action="store_true", help="amplifier output goes negative with light")
    ap.add_argument("--fade", action="store_true", help="the capture is a fade, not a steady level")
    ap.add_argument("--mean", type=float, help="AC-coupled capture: the DC level, measured separately, volts")
    args = ap.parse_args()
    v, fs = load(args.csv)
    v = (-v if args.invert else v) - args.dark
    print(f"{len(v)} samples at {fs / 1e3:.0f} kS/s ({len(v) / fs * 1e3:.0f} ms)")
    if args.mean is not None:
        args.mean -= args.dark
    ok = fade(v, fs) if args.fade else steady(v, fs, args.mean)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
