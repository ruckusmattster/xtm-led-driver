# Changelog

Design revisions, newest first. Board A's silkscreen says **rev 1**, Board B's **rev 2**. Nothing
has been fabricated yet.

## Board B rev 2: socketed ESP32-S3-Zero (30 September 2026)

- The ESP32-S3-WROOM-1 and its USB-C receptacle, USB ESD part, 3.3 V regulator and reset/boot
  circuit are replaced by a **Waveshare ESP32-S3-Zero-M** plugged into two 1 × 9 sockets on the
  back of the board: 17 fewer parts, no 0.5 mm-pitch USB-C to hand-solder, and a module that comes
  out to be flashed.
- The link to Board A moves from IO17/IO18 to **IO1/IO2**, keeping UART0 off Board A's line; every
  other signal keeps its GPIO. IO3, IO43 and IO44 go to a spare header, J4.
- New footprint `layout/lib/XTM.pretty/ESP32-S3-Zero_Socket` with an antenna copper keep-out;
  back silkscreen marks the module's name, both ends, and pins 5V and TX.
- Board B: 42 parts, 32 nets; layout 0 DRC errors, 0 unconnected.
- ESPHome config: 4 MB flash, new UART pins.

## Scripted layout (29–30 September 2026)

- Both boards laid out by `layout/` scripts in KiCad 9 with Freerouting 1.9.0: 0 DRC errors and
  0 unconnected on both.
- Ground fan-out before routing, router keep-outs around the cathode copper, clean-up of router
  leftovers, pour stitching with island removal held off, pad tracking by UUID.
- High-voltage clearances per IPC-2221B (0.5 mm with bare pads, 0.3 mm coated); L3 carries
  signals; Q1 gets 2.3 cm² + 2.8 cm² of copper and 39 vias (thermal estimate 50 °C/W, junction
  about 127 °C in 45 °C air).
- Gerbers, drill files and JLCPCB placement files exported to `layout/out/`.

## Phase 2 final check (29 September 2026)

- DAC80504 reference halved and gain doubled (REFDIV and GAIN strapped high); footprint TI
  RTE0016D with the 0.8 mm exposed pad.
- Main buck enable moved from PB9 (the ROM bootloader's CAN TX, which idles high) to PC13.
- WSL2512R1000FEA named as a stocked fallback for the WSK2512 0.1 Ω shunt.
- J4 is the FTSH-107-01-L-DV-K; round lug holes for the encoder; a tactile-switch footprint KiCad
  still ships.
- BOM corrections: encoder, inductor saturation currents, JLC classes and fees, stock notes,
  J1/J2 plugs.
- Thermal estimate redone on the real 90 × 60 mm outline.

## Phase 2 detailed design (27–29 September 2026)

- Every value on both boards, from `design/calc.py` and `design/sim/handover.c`.
- Crossover fix: keep-alive priming and a log-domain blend (simulated dip from 3.5% to 0.14% on
  a 10 s fade).
- 22 nF across the LED; free-running bucks; buck held off while the MCU is in reset; feedback
  network rescaled for the DAC's output range; C_C 2.2 nF on all channels; op-amp output
  monitors; 3 A input fuse; sequenced on/off with a voltage-mode tail to black.
- Schematics as code with a connectivity check; BOMs with verified part numbers.
- Board A firmware (C, STM32G431) and Board B firmware (ESPHome + external component), both
  tested on a PC.
- Bring-up, calibration and flicker-verification procedures.

## Phase 1 design review (26 September 2026)

- Forced-PWM buck instead of pulse-skipping; a fourth DC range (100 Ω) instead of PWM for the
  bottom decade; the headroom loop moves into an MCU on Board A with feed-forward.
- 100 W supply, a static blend without hysteresis, a fast short-circuit trip, a V_out floor, a
  zero bias and gate clamps.
- STM32G431 on Board A; UART over a 10-way ribbon; ESP-NOW for fixture sync.
