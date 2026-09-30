# Hardware reference

Both boards block by block: what each part of the circuit does, its values, and why. Every
number comes from [`design/calc.py`](../design/calc.py) (output in
[`calc_output.txt`](../design/calc_output.txt)) and the crossover model
[`design/sim/handover.c`](../design/sim/handover.c). For every part and pin, see the sheet tables
[`hardware/board_a/board_a-sheets.md`](../hardware/board_a/board_a-sheets.md) and
[`board_b-sheets.md`](../hardware/board_b/board_b-sheets.md); for the full reasoning, the
[Phase 2 design](design-record/phase2-detailed-design.md).

## Contents

- [System](#system)
- [Board A: power entry and aux rails](#board-a-power-entry-and-aux-rails)
- [Board A: tracking buck](#board-a-tracking-buck)
- [Board A: setpoints and the four sinks](#board-a-setpoints-and-the-four-sinks)
- [Board A: crossovers](#board-a-crossovers)
- [Board A: LED output, protection, off and on](#board-a-led-output-protection-off-and-on)
- [Board A: MCU](#board-a-mcu)
- [Board A: accuracy](#board-a-accuracy)
- [Board A: thermal](#board-a-thermal)
- [Board A: layout](#board-a-layout)
- [Board B](#board-b)
- [The ribbon link](#the-ribbon-link)

---

## System

| Item | Value |
| --- | --- |
| Supply | Mean Well LRS-100-48 (110 W, 43.2–52.8 V adjustable, left at 48 V), off-board, its case earthed |
| Load | Xicato XTM19803050CCA: 1.4 A rated (1.5 A with tolerance), V_f 28.6 / 29.9 / 36.0 V (min / typ / max at 1.4 A over 20–90 °C), ±10% flux |
| Draw at full output | About 45 W typical, 54 W worst case: 41–49% of the supply's rating |
| Board A | 90 × 60 mm, 4 layers, 206 parts, 96 nets |
| Board B | 60 × 45 mm, 2 layers, 42 parts, 32 nets |

The LED current is set entirely by four linear sinks under the LED's cathode. The buck only
supplies the voltage they need, set by the MCU ahead of every change in current.

## Board A: power entry and aux rails

*Sheet A1.*

| Block | Parts and values | Why |
| --- | --- | --- |
| Input | J1 Phoenix MSTBA 2,5/2-G-5,08 (pin 1 +48 V). F1 Littelfuse 0452003.MRL, 3 A slow-blow. D1 SMBJ58A. C1 47 µF 100 V electrolytic, 10 × 10.2 mm | F1 protects the wiring below the supply's hiccup threshold; D1 clamps surges and conducts on reverse polarity so F1 or the supply's hiccup takes over; C1 damps the supply leads |
| 48 V monitor | 100k / 6.2k with 10 nF, to PB0 | 52.8 V reads 3.08 V |
| Aux buck U3 | LMR38020FDDAR at 500 kHz: RT 52.3k, FB 100k / 22.1k (5.53 V), EN 280k / 10k from VIN, BOOT 100 nF. L3 SRR1260-150M (15 µH). In: 4.7 µF 100 V 1210 + 100 nF. Out: 3 × 22 µF 25 V 1206 | Starts at about 36 V (31.9–40.6 V over the EN tolerance); the same part as the main buck |
| +5VA | TPS7A2050PDBVR from 5.5 V | DAC, op-amp and the zero-bias source |
| +3V3 | LDL1117S33R from 5.5 V; a ferrite and 1 µF + 100 nF to VDDA/VREF+ | The MCU. The raw 5.5 V also feeds Board B over the ribbon |

## Board A: tracking buck

*Sheet A2.*

- **Converter:** U2, LMR38020FDDAR in **forced PWM** at 400 kHz (RT 64.9k). L2 SRR1260-330M,
  still 26.4 µH at −20%, above the 24.4 µH the datasheet needs at 39 V; its 2.8 A saturation
  current covers the 1.84 A peak in use. Input 2 × 4.7 µF 100 V 1210 + 100 nF; output 4 × 4.7 µF
  + 100 nF (about 10 µF effective at 30 V): 27 mV p-p ripple at 400 kHz.
- **Feedback with injection:** 200k top, 7.32k bottom; the MCU's DAC (PA4) injects through
  8.25k + 8.25k with 47 nF from the midpoint to ground. A 22 pF C_ff footprint (C29) is not fitted.
- **Transfer:** **V_out = 40.44 − 12.12 × V_dac**, 9.8 mV per 12-bit code.
  - DAC at its 0.2 V buffer limit: 38.0 V, 1 V above the worst-case need (36.0 V + 1.0 V headroom).
  - DAC at 3.05 V: the 3.5 V floor (off).
  - DAC stuck at 0 V: a 40.4 V ceiling, below D2's 43 V standoff.
  - V_out follows the DAC with a 0.19 ms time constant, 95% in about 0.6 ms.
- **Safe off:** EN comes from PC13 with a 100k pull-down, so the buck is off whenever the MCU is
  in reset, unprogrammed or in its ROM bootloader.
- **Status:** power-good to PC4 (100k pull-up); D2 SMBJ43A on V_out; V_out sensed through
  1M / 82k with 10 nF to PA0.
- **Loop:** the injection lowers loop gain to 0.38–0.72× of a plain divider, which lowers the
  crossover and adds phase margin. Every operating point from 3.5 V to the 40.4 V ceiling meets
  the 131 ns minimum on-time and 300 ns minimum off-time with 43.2–52.8 V in (38 V sits exactly
  at the off-time limit at 43.2 V, so the supply stays at 48 V).

## Board A: setpoints and the four sinks

*Sheets A3 and A4.*

**Setpoints.** A DAC80504 (U6), four 16-bit channels, runs its 2.5 V reference halved and its
gain doubled (REFDIV and GAIN strapped to VIO) for 2.5 V full scale; undivided, the reference
would sit at the datasheet's VDD/2 limit on 5 V, where an alarm turns every output off. REF has
220 nF; RSTSEL low, so it powers up at zero. SPI mode 1 on PA15/PB3/PB5/PB4 through 22 Ω; the
firmware reads the registers back every few milliseconds, the alarm included. Each channel then
goes through a **÷13 divider** (12.0k / 1.00k, 0.1%, 25 ppm/°C thin film, 10 nF C0G): 192 mV full
scale, 2.93 µV per code. The bottom of every range is code 4771, where one code is 0.021%.

**Sinks.** OPA4388 (U7) sections A–D, one per channel. Each loop:

| Element | Value | Role |
| --- | --- | --- |
| Integrator | R_IN 1.00k from the Kelvin sense to −IN; C_C 2.2 nF C0G from output to −IN | The loop's compensation, identical on every channel |
| Gate drive | R_G 220 Ω at the gate | Isolates the FET's capacitance |
| Zero bias | 1.82 MΩ from a BIAS node (10k / 1k from +5VA, 1 µF): 250 µV | Worst-case code-0 input is 126 µV, so code 0 is firmly off |
| Gate clamp | 2N7002BK gate to ground, its gate pulled up to +3V3 by 100k | On in reset; holds the gate at 90–210 mV even with the op-amp at its rail |
| Gate monitor | 100k / 100k from the op-amp output, 1 nF at the ADC pin | Firmware sees when a channel is primed or short of headroom |

| | ch1 | ch2 | ch3 | ch4 |
| --- | --- | --- | --- | --- |
| Range | 140 mA–1.5 A | 14–160 mA | 1.4–16 mA | 5 µA–1.6 mA |
| Shunt | Vishay WSK2512 0.1 Ω, four-terminal | 10 × 10 Ω 0.1% 0805 in a ladder, Kelvin via net ties | 10 Ω 0.1% 0805 | 100 Ω 0.1% 0805 |
| FET | NDT3055L (SOT-223) | 2N7002BK | 2N7002 | 2N7002 |
| Clamp pin / monitor pin | PC6 / PA6 | PA8 / PA7 | PC10 / PB2 | PB7 / PB15 |
| Loop crossover (keep-alive, range bottom, band top) | 43 Hz, 8.3 kHz, 21.6 kHz | 46 Hz, 7.6 kHz, 20.5 kHz | 46 Hz, 16 kHz, 36 kHz | 46 Hz, 0.9 kHz at 5 µA, 54 kHz |
| Phase margin | ≥ 89° | ≥ 89° | ≥ 89° | ≥ 89° |
| Keep-alive current | 250 µA | 25 µA | 2.5 µA | 0.25 µA |

The small FETs are chosen for leakage: off channels leak straight through the LED, and at 5 µA
every nanoamp counts. Nexperia's 2N7002 specifies gate leakage ≤100 nA at ±15 V, where the
2N7002BK allows 10 µA at 20 V, so the 10 Ω and 100 Ω channels use the plain 2N7002.

## Board A: crossovers

Where two ranges meet (1.4–1.6 mA, 14–16 mA, 140–160 mA) both channels carry current.

1. **Keep-alive.** An armed channel regulates 25 µV above its calibrated dead-zone edge (25 µV / R_s,
   2.5 µA on the 10 Ω channel), which parks its integrator at the FET's threshold. The firmware
   subtracts the keep-alive current from the active channel. A channel arms once the level passes
   half its band's bottom, or when a fade will reach its band within 0.4 s; it disarms below a
   quarter. Channel 4 stays armed whenever the light is on.
2. **Priming** from the dead zone takes 70–320 ms (threshold 1.0–2.5 V); the gate monitor shows
   when it's done.
3. **Log-ratio blend.** Inside a band, ln(I_high / I_low) runs linearly in log(I), so each
   channel's share grows exponentially. The blend stays monotonic unless the two channels'
   calibrated gains disagree by more than 3.6%; after calibration they agree to about 0.1%.

| Full-range fade | Deviation at a crossover, as built | Without priming (the Phase 1 plan) |
| --- | --- | --- |
| 1 s | 0.9–1.5% for about 10 ms, while the light changes 1.3% per ms | 15–17% |
| 10 s | 0.11–0.14% | 3.1–3.7% |
| 60 s | ≤ 0.03% | — |

Simulated summed sink current against the intended curve, after a 1 ms low-pass (roughly what a
240 fps frame integrates). Fades update the DAC at 4 kHz; static levels never update.

## Board A: LED output, protection, off and on

*Sheet A5.*

**The cathode node.** J2 (pin 1 LED−, pin 2 LED+) has C_a, 22 nF 100 V X7R, across its pins; the
node carries the four drains and a 1 MΩ tap into 1 nF, clamped by a BAV199, to PA1. From 100 Hz
to 20 kHz, down to 5 µA, it now takes over 200 mV of V_out ripple to make 1% of LED-current
modulation, against 6.5 mV without C_a.

**Short.** PA1 is also COMP1's input, at a fixed 3.0 V from the internal DAC3; its interrupt
engages all four gate clamps in about 1 µs, 50–100 µs in all with the tap's RC. The trip is masked
only while the expected cathode voltage is above 2.6 V (V_out leading a turn-on) and for 3 ms
after; a V_f reading under 15 V catches a short on the next ADC pass. A V_out stuck at its
ceiling, which would put 16 W in the FET, trips it too.

**Open LED.** V_out reaches its ceiling while the cathode stays near 0 V: firmware drops to the
floor and reports it. With the default LED model that only happens near full output; see the
[firmware's known issues](FIRMWARE.md#known-issues).

**Off:** every sink in its dead zone and V_out at its 3.5 V floor, where the array can't conduct.

**On:** V_out rises first, then the sink comes up; C_a lifts the cathode about 16 V on the way up
and the sink pulls it back, with the LED current appearing only in the last 2 V and no overshoot.

| Turn-on target | Time to first light |
| --- | --- |
| 5 µA | about 52 ms |
| 140 µA | about 1.9 ms |
| 1 mA | about 0.26 ms |
| Above 1 mA | under 0.1 ms, plus the 0.6 ms V_out step |

**Fade to black.** Below the tail's end point (5 µA by default, adjustable), the sink holds just
above the remaining current and V_out keeps falling instead. The LED current then follows V_out
exponentially, at 1.5% per buck-DAC code and a decade per 1.5 V, down to picoamps before the
floor. There is no last step to see.

## Board A: MCU

*Sheet A6.* STM32G431CBU6 (Cortex-M4F, 170 MHz from the internal HSI16). The full pin map is in
the [build guide's appendix](BUILD_GUIDE.md#appendix-a-connectors-and-pinouts). Each VDD pin and
VBAT has 100 nF, with one 4.7 µF bulk; VDDA and VREF+ have 1 µF + 100 nF behind a ferrite. Four
NTCs (at the channel-1 FET, the main buck, the aux rails and the precision section) feed the
thermal limits. J4 is ST's STDC14 connector for the STLINK-V3MINIE, which also carries the
calibration console on its virtual COM port.

## Board A: accuracy

After calibration, with the board within ±20 °C of its calibration temperature:

| Range | Current | Sense | RSS | Worst case |
| --- | --- | --- | --- | --- |
| 1 (0.1 Ω) | 140 mA / 1.4 A | 14 / 140 mV | ±0.11% / ±0.10% | ±0.27% / ±0.20% |
| 2 (1 Ω) | 14 / 140 mA | 14 / 140 mV | ±0.09% / ±0.09% | ±0.23% / ±0.17% |
| 3 (10 Ω) | 1.4 / 14 mA | 14 / 140 mV | ±0.09% / ±0.09% | ±0.23% / ±0.17% |
| 4 (100 Ω) | 140 µA / 1.4 mA | 14 / 140 mV | ±0.11% / ±0.09% | ±0.28% / ±0.17% |
| Tail | 14 µA / 5 µA | 1.4 / 0.5 mV | ±0.6% / ±1.6% | ±1.3% / ±3.4% |

Range 4 and the tail include about 70 nA of board and FET leakage, which always adds current.
With the WSL2512 fallback for R102, range 1 widens to ±0.17% RSS. The biggest terms are the two
discrete 25 ppm/°C divider resistors, budgeted as if they drifted in opposite directions; a
matched network would tighten every range. None of this touches smoothness: one DAC code is
0.021% at the bottom of a range.

The module's own flux tolerance (±10%) is far larger, which is why fixtures are matched on light,
not just current ([build guide, section 12](BUILD_GUIDE.md#12-calibrate)).

## Board A: thermal

About 2.8 W at full output on 90 × 60 mm of 4-layer board in still air: +22 °C of average rise
over the enclosure air.

- **Channel-1 FET:** 1.2 W. On 5 cm² of its own copper (2.3 cm² on top, 2.8 cm² on the bottom,
  39 vias between), taken at 50 °C/W, its junction runs about 82 °C over the air: about 127 °C in
  45 °C air, against a 150 °C limit. (onsemi rates it at 42 °C/W on 6.5 cm² of 2 oz copper and
  95 °C/W on 0.4 cm².)
- **If it runs hot:** 0.8 V of headroom instead of 1.0 V at full current saves 0.28 W; a
  100 × 70 mm outline would take about 5 °C off the board's rise.

| NTC | Derate from | Trip at |
| --- | --- | --- |
| Channel-1 FET | 95 °C | 110 °C |
| Main buck | 90 °C | 105 °C |
| Aux rails | 90 °C | 105 °C |
| Precision section | 75 °C | 90 °C |

## Board A: layout

The layout rules, in full, are [`hardware/LAYOUT.md`](../hardware/LAYOUT.md). In short:

| Layer | Copper | Use |
| --- | --- | --- |
| L1 top | 1 oz | Every part; signals, both switch nodes, the Kelvin pairs, local power copper, Q1's tab copper, then a GND pour |
| L2 | 0.5 oz | GND, solid: no splits, no tracks |
| L3 | 0.5 oz | Signals, then a GND pour |
| L4 bottom | 1 oz | Signals, Q1's heat spreader under its tab, then a GND pour |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/floorplan-dark.png">
  <img alt="Board A floorplan with seven zones" src="images/floorplan-light.png">
</picture>

- **Switch nodes** on L1 only, as small as the current allows, no vias; the input loops closed
  through L2 directly under each buck.
- **Kelvin pairs** start at each shunt's own sense points (R102's pads 2 and 3; net ties on the
  ladder and the 10 Ω and 100 Ω shunts); divider bottoms and their filter capacitors return to
  the sense-low net, never to the plane.
- **The precision island** is a ground cage: pour around and between its parts, stitching every
  3 mm, L2 solid under it. No 48 V-class net within 2 mm of a precision net (a DRC rule).
- **Leakage:** the cathode net compact and soldermasked, a 1 mm slot between J2's pads, and a
  mandatory wash after assembly.
- **High-voltage spacing** (IPC-2221B, 51–100 V): 0.5 mm wherever a bare pad is involved, 0.3 mm
  between coated tracks and on inner layers.

| Path | Current | As laid out |
| --- | --- | --- |
| +48V_RAW, J1 → F1 | 1.5 A | 2 mm, drawn |
| +48V, F1 → the bucks; VOUT | 1.5 A | 0.6 mm, routed (IPC-2221 minimum 0.53 mm) |
| CATHODE, J2 → Q1 | 1.5 A | The tab copper |
| SRC1, Q1 → R102 | 1.5 A | 1.5 mm, drawn; four vias at R102's ground end |
| +5V5 rails | 0.6 A | 0.5 mm |
| Signals, Kelvin pairs, logic rails | < 50 mA | 0.2 mm |

## Board B

A Waveshare ESP32-S3-Zero (ESP32-S3FH4R2: 4 MB flash, 2 MB PSRAM) in two 1 × 9 sockets on the back
of a 2-layer board. The module brings its own USB-C, 3.3 V regulator (ME6217C33, 800 mA) and
BOOT/RESET buttons, so Board B keeps only the power entry, the controls and the link.

<img src="images/board-b-iso-bottom.png" alt="Board B's back, with the two socket rows for the ESP32-S3-Zero" width="520">

- **Power:** ribbon +5V5 (pins 1 and 3) through a 2 A ferrite and a B5819W Schottky to the
  module's 5V pin, about 5.1 V. The module's regulator makes +3V3 for the encoder pull-ups and the
  LEDs. The Schottky keeps a USB supply out of Board A; nothing keeps Board A's supply out of a
  computer, so the module is flashed out of its sockets.
- **Encoder:** Bourns PEC11R-4220F-S0024 (24 detents, push switch), with Bourns' recommended
  filter on A, B and the push: 10k pull-up, 10k series, 10 nF.
- **Sync:** a 6 × 6 mm tactile switch in parallel with a JST PH header for a panel button, same RC.
- **Status LED:** separate red, green and blue LEDs, active low, dimmed with 25 kHz PWM.
- **Antenna:** the module's antenna end sits at the board's edge over a copper keep-out; keep
  15 mm of clearance from metal, and the board at least 100 mm from Board A and the LED leads.
- **Layout:** 60 × 45 mm, 1.6 mm, 1 oz, ENIG; power tracks 0.3 mm, the rest 0.2 mm; GND poured on
  both sides.

GPIO assignments are in the [build guide's appendix](BUILD_GUIDE.md#appendix-a-connectors-and-pinouts).

## The ribbon link

A 10-way, 2.54 mm IDC ribbon, straight through, up to about 0.5 m (good to 1 m).

| Pin | Signal | Pin | Signal |
| --- | --- | --- | --- |
| 1 | +5V5 (A → B) | 2 | GND |
| 3 | +5V5 (A → B) | 4 | GND |
| 5 | UART, A → B | 6 | GND |
| 7 | UART, B → A | 8 | BOOT0 (B → A) |
| 9 | A_OK (A → B) | 10 | NRST (B → A, open-drain) |

UART at 115200 8N1 with 100 Ω series resistors at each end; the transmit line sits between two
grounds. BOOT0 and NRST let Board B reset Board A, and later reflash it through the STM32's ROM
bootloader (the bootloader client isn't written yet). A_OK has a 100k pull-down on Board B, so an
unplugged ribbon reads "not OK". The protocol is in [the firmware reference](FIRMWARE.md#the-link-between-the-boards).
