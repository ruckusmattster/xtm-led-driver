# 4-decade LED driver — Phase 2 detailed design

30 September 2026

> **About this document.** This is the Phase 2 detailed design as it was written: every value on
> both boards, the reasoning behind it, and the bring-up, calibration and flicker procedures,
> addressed to me and built on my answers to the [Phase 1 review](phase1-review.md). It's the
> most complete single description of the design. Paths are relative to the repository root.
> The only edits since: the embedded floorplan is now an image, two notes about KiCad versions and
> the ESP32 footprint are brought up to date, and a location is generalised.
>
> **Errata, found later.** Where these differ, follow the [build guide](../BUILD_GUIDE.md):
> - Bring-up step 4 should use `b 1`, not `b 0.3`: the firmware only flags an open LED once V_out
>   reaches its ceiling, which happens near full output. Follow it with `reboot` to discard the
>   corrections learned with nothing connected ([known issues](../FIRMWARE.md#known-issues)).
> - The console prints faults as numbers (`fault=1` short, `fault=2` open), and the LED voltage is
>   `vout` minus `vcath`.
> - In step 5, `b 0 10000` ends at 5 µA, not dark; use `lvl 0 10000`.
> - Restoring a calibration by hand needs a final `save`.
> - The layouts don't mark a spot for JLC's order number, and U6's footprint splits its paste
>   into four windows.

## Summary

Phase 2 turns the reviewed plan into a buildable design: every value on both boards, netlists to capture in KiCad, BOM files, a layout guide, firmware for both boards, and the bring-up, calibration and flicker procedures. Every section is finished and checked, and the files are this repository. A final independent review against data sheets and distributor pages made the six changes listed under Changes from the final check.

**Decisions from your answers**

| # | Your answer | What it changes |
| --- | --- | --- |
| 1–2 | Yes to the fourth DC range and the other Phase 1 changes | Built as proposed |
| 3, and your note on LED testing | Keep testing to a minimum | No bench tests before layout. The design assumes ≤50 nA of bypass leakage inside the XTM, and firmware makes the tail's end point adjustable in case the last few µA misbehave |
| 4 | Wood or plastic enclosure; metal only for heatsinking; earthing if needed | An ESP32-S3 module with its own antenna: a Waveshare ESP32-S3-Zero in sockets on Board B's back. Board A cools through its own copper. Only the LRS-100-48's case is earthed, because it's a Class I supply |
| 5 | Distances are flexible | Board A sits close enough for the XTM's 400 mm leads to reach unextended; Board B on the control face, ≤0.5 m of ribbon |
| 6 | Up to me | Snaps settle within \~10 ms; fades run up to 10 minutes |
| 7 | No haze; 3D-printing plastics and laser-cut materials | No conformal coating, but cleaning stays mandatory. Use PETG or ASA, not PLA, for anything touching Board A or the LED heatsink |
| 8 | Default | One access point, Home Assistant optional, every fixture fully standalone |
| 9 | Toggling sync on makes every other fixture follow this one; ownership moves to whoever toggles on | Built over ESP-NOW. One rule added: adjusting a follower locally takes it out of the group |
| 10 | Blink and drop to 20% | If the light is on, it blinks twice and settles at 20% on the encoder's brightness scale, or stays put if already lower. A blacked-out fixture stays dark. Planned Board B reboots, such as OTA updates, send a hold first so they don't trigger it |
| 11 | No DMX | — |
| 12 | A university electronics lab's bench equipment | Procedures assume a bench DMM, a scope and a bench supply |
| 13 | Lux at a set distance, at a couple of levels | Two-point light matching per fixture, stored on Board A. Skip it and the fixtures match on current alone |

**Changes since Phase 1**

- **A 22 nF capacitor across the LED output.** It makes the cathode follow V\_out at audio frequencies, so buck ripple barely reaches the LED current. The V\_out ripple allowed at the bottom of the range rises from \~6 mV to over 100 mV.
- **The bucks free-run instead of syncing to the MCU.** With that capacitor in place, their beat can't reach the LED.
- **Board A's MCU holds the main buck off** whenever it's in reset, so a crashed or unflashed MCU can't light the LED.
- **The LED heatsink and the 48 V side stay unearthed.** A floating heatsink follows the array's voltage, which keeps its capacitance out of the ripple path.

**Changes from the final check**

- **DAC80504 reference and pad.** REFDIV and GAIN now strap to 3.3 V: the 2.5 V reference is halved and the gain doubled, so full scale stays 2.5 V. Undivided, the reference sits at the data sheet's VDD/2 limit on the 5 V supply, where a reference alarm switches every output off. The footprint is now TI's RTE0016D, with a 0.8 mm exposed pad instead of 1.68 mm.
- **Buck enable on PC13 instead of PB9.** The STM32's ROM bootloader uses PB9 as its CAN transmit pin, which idles high, so the buck would have started during a reflash and on an unprogrammed chip.
- **A stocked fallback for R102.** No distributor had the WSK2512R1000FEA on 29 September. The two-terminal WSL2512R1000FEA fits the same pads and widens range 1 to ±0.17% RSS.
- **Footprints and connectors.** J4 is the FTSH-107-01-L-DV-K, because the -K-A version's alignment pins need holes. The encoder footprint gets round 2.6 mm lug holes, the tactile switches move to a footprint that KiCad 8–10 still include, and the layout scripts need KiCad 9.
- **BOM corrections.** LCSC's encoder number, the knurled -4220K, is gone. Inductor saturation currents, JLC classes and fees are corrected, stock notes cover the TDK 4.7 µF, TPS7A2050 and STM32, and the J1/J2 plugs have their own line.
- **Thermal estimate on the real outline.** It now uses the 90 × 60 mm board: +22 °C on average and a 127 °C FET junction in 45 °C air, taking 50 °C/W for the 5 cm² of copper the layout gives Q1.
- **Board B's ESP32 on sockets.** The ESP32-S3-WROOM-1 and its USB-C, ESD, 3.3 V regulator and reset/boot parts give way to a Waveshare ESP32-S3-Zero plugged into two 1 × 9 sockets on the back: 17 fewer parts, no 0.5 mm-pitch USB-C to hand-solder, and a module that comes out to be flashed. The link moves from IO17/IO18 to IO1/IO2; every other pin keeps its GPIO.

## Circuit design

Every number here comes from `design/calc.py` and the time-domain model `design/sim/handover.c`, both in this repository. Rerun them after changing any value; the script asserts the limits that matter (phase margin, buck on- and off-times, inductance, the V\_out ceiling).

Working through the dynamics turned up one real flaw in my Phase 1 plan, now fixed. The incoming channel of a crossfade started from a wound-down integrator, so each crossover would have dipped the light by about 3.5% on a 10-second fade and 16% on a 1-second one. Channels now idle at a small keep-alive current before a crossover, and the blend is shaped in the log domain. The dip falls to about 0.14% on a 10-second fade.

Other changes since Phase 1:

- **Buck feedback network rescaled.** The STM32's buffered DAC can't swing within 0.2 V of its rails, which the old network needed to reach full V\_out.
- **C\_C is 2.2 nF on all four channels**, for faster handovers.
- **Each op-amp output gets an ADC tap**, so firmware sees when a channel is primed or short of headroom.
- **A 3 A fuse on the 48 V input.**
- **Off and on are sequenced, with a voltage-mode tail**, so the final fade to black is continuous rather than a cut from 5 µA.

### Board A: power

| Block | Parts and values | Why |
| --- | --- | --- |
| Input | J1 Phoenix MSTBA 2,5/2-G-5,08 (pin 1 +48 V). F1 Littelfuse 0452003.MRL, 3 A slow-blow, 125 V AC/DC, 2410. D1 SMBJ58A. C1 47 µF 100 V electrolytic, 10 × 10.2 mm (RVT2A470M1010). | F1 protects the wiring below the supply's hiccup threshold. D1 clamps surges and conducts on reverse polarity, so F1 or the supply's hiccup takes over. C1 damps the supply leads. |
| 48 V monitor | 100k / 6.2k with 10 nF, to PB0 | 52.8 V reads 3.08 V |
| Aux buck U3 | LMR38020FDDAR at 500 kHz: RT 52.3k, FB 100k / 22.1k (5.53 V), EN 280k / 10k from VIN, BOOT 100 nF. L3 SRR1260-150M (15 µH). In: 4.7 µF 100 V 1210 + 100 nF. Out: 3 × 22 µF 25 V 1206. | Starts at \~36 V (31.9–40.6 V over the EN tolerance). Same part as the main buck. 0.65 A p-p ripple. |
| +5VA | TPS7A2050PDBVR from 5.5 V | DAC, op-amp and zero bias |
| +3V3 | LDL1117S33R from 5.5 V; ferrite + 1 µF + 100 nF to VDDA/VREF+ | MCU. The raw 5.5 V also feeds Board B over the ribbon |

### Tracking buck

- **Converter.** U2 is an LMR38020FDDAR (forced PWM) at 400 kHz (RT 64.9k).
  - L2 is an SRR1260-330M. At −20% it is still 26.4 µH, above the 24.4 µH the datasheet requires at 39 V. Its 2.8 A saturation current covers the 1.84 A peak in use, though not the LMR38020's 3.2 A typical current limit, which only a hard short from V\_out to ground reaches.
  - Input: 2 × 4.7 µF 100 V 1210 (TDK C3225X7S2A475K200AB) + 100 nF.
  - Output: 4 × the same 4.7 µF + 100 nF. That is about 10 µF effective at 30 V, so ripple is 27 mV p-p at 400 kHz.
- **FB network.** 200k top and 7.32k bottom. PA4 (DAC1\_OUT1) injects through 8.25k + 8.25k, with 47 nF from the midpoint to ground. A 22 pF C\_ff footprint sits across the top resistor, not fitted.
- **Transfer: V\_out = 40.44 − 12.12 × V\_dac**, at 9.8 mV per 12-bit code.
  - DAC at its 0.2 V buffer limit gives 38.0 V, 1.0 V above the worst-case need (36.0 V V\_f + 1.0 V headroom).
  - DAC at 3.05 V gives the 3.5 V blackout floor.
  - A DAC stuck at 0 V can only reach a 40.4 V ceiling, below D2's 43 V standoff.
  - V\_out follows the DAC with a 0.19 ms time constant, settling to 95% in about 0.6 ms.
- **Safety off.** EN comes from PC13 with a 100k pull-down, so the buck is off whenever the MCU is in reset, unprogrammed or in its ROM bootloader, which replaces Phase 1's high-impedance-DAC floor. PB9 would not do: the bootloader uses it as its CAN transmit pin, which idles high.
- **Status and sensing.** PG goes to PC4 through a 100k pull-up. D2 is an SMBJ43A on V\_out. V\_out sense is 1M / 82k with 10 nF to PA0 (40.4 V reads 3.06 V).
- **Loop.** Injection lowers the loop gain to 0.38–0.72× of a plain divider, which lowers crossover and adds phase margin. Bring-up checks it with a load step.
- **On- and off-time limits.** Every operating point from 3.5 V to the 40.4 V ceiling meets the 131 ns minimum on-time and 300 ns minimum off-time between 43.2 V and 52.8 V in. With the supply turned down to 43.2 V, 38 V sits exactly at the off-time limit, so leave the LRS-100-48 at 48 V.

### Setpoints and sinks

The DAC80504 (U6) halves its 2.5 V internal reference and runs at gain 2, for 2.5 V full scale.

- **Supplies:** VDD on +5VA, VIO on +3V3.
- **Reference and straps:** REF has 220 nF to ground. REFDIV and GAIN are tied to VIO and RSTSEL to GND, so the DAC powers up halved, at gain 2 and at zero scale. Undivided, the 2.5 V reference would sit at the data sheet's VDD/2 limit on the 5 V supply, where a reference alarm turns every output off. LDAC has 10k to VIO.
- **SPI 1 (mode 1):** CS on PA15, SCLK on PB3, SDI from PB5 and SDO to PB4, each through 22 Ω. Firmware reads the registers back every few milliseconds, the reference alarm included, so a corrupted SPI write can't persist.

Each channel's divider is 12.0k / 1.00k, 0.1%, 25 ppm/°C thin film, with 10 nF C0G.

- **Scaling:** ÷13 gives 192 mV full scale and 2.93 µV per code. The bottom of every range is code 4771, where one code is 0.021%.

The OPA4388 (U7) sections A–D drive channels 1–4. Each loop has:

- **Integrator:** R\_IN 1.00k from the Kelvin sense to −IN, and C\_C 2.2 nF C0G from output to −IN.
- **Gate drive:** R\_G 220 Ω to the gate.
- **Zero bias:** 1.82 MΩ from a BIAS node (10k / 1k from +5VA, 1 µF), giving 250 µV. Worst-case code-0 input is 126 µV, so code 0 is firmly off.
- **Gate clamp:** a 2N7002BK from gate to ground, gate pulled up to +3V3 by 100k. The clamp is on in reset, and holds the gate at 90–210 mV even with the op-amp at its rail.
- **Gate monitor (new):** 100k / 100k from the op-amp output, with 1 nF at the ADC2 pin (0–2.45 V).

|  | ch1 | ch2 | ch3 | ch4 |
| --- | --- | --- | --- | --- |
| Range carried | 140 mA–1.5 A | 14–160 mA | 1.4–16 mA | 5 µA–1.6 mA |
| Shunt | Vishay WSK2512 0.1 Ω, four-terminal | 10 × 10 Ω 0.1% 0805 thin film, Kelvin via net ties | 10 Ω 0.1% 0805 | 100 Ω 0.1% 0805 |
| FET | NDT3055L | 2N7002BK | 2N7002 | 2N7002 |
| Clamp gate / monitor pin | PC6 / PA6 | PA8 / PA7 | PC10 / PB2 | PB7 / PB15 |
| Crossover: keep-alive, range bottom, band top | 43 Hz, 8.3 kHz, 21.6 kHz | 46 Hz, 7.6 kHz, 20.5 kHz | 46 Hz, 16 kHz, 36 kHz | 46 Hz, 0.9 kHz at 5 µA, 54 kHz |
| Phase margin | ≥89° | ≥89° | ≥89° | ≥89° |
| Keep-alive current | 250 µA | 25 µA | 2.5 µA | 0.25 µA |

Miller feedthrough of 30 mV of 400 kHz drain ripple is 0.2% at 1.4 A, far outside the flicker band.

### Crossovers: keep-alive and a log-domain blend

A channel in its dead zone has its integrator wound down to 0 V. Before it can carry current it must ramp up by the FET's threshold, about 2 V, at a rate set by its tiny error. With the Phase 1 blend, the incoming channel's current therefore lagged its setpoint through the whole band.

The fix has three parts:

1. **Keep-alive.** An armed channel regulates 25 µV above its calibrated dead-zone edge. That is 25 µV / R\_s: 2.5 µA on the 10 Ω channel, for example. Its integrator then sits at the FET's threshold, ready to move.
   - The keep-alive current is calibrated, and firmware subtracts it from the active channel.
   - A channel arms once the level passes half of its band's bottom (0.7 mA, 7 mA or 70 mA). It also arms when a fade's trajectory will reach its band within 0.4 s.
   - It disarms below a quarter of the band bottom. Channel 4 stays armed whenever the light is on.
2. **Priming takes 70–320 ms** from the dead zone (FET threshold 1.0–2.5 V). Firmware sees completion on the gate monitor. Arming adds at most 0.5% of the level, applied gradually.
3. **Log-ratio blend.** Inside each band, ln(I\_high / I\_low) runs linearly in log(I), from the incoming channel's keep-alive to the outgoing channel's. Each channel's share then grows exponentially, which a subthreshold-biased loop can follow.
   - The blend stays monotonic unless the two channels' calibrated gains disagree by more than 3.6%. After calibration they agree to about 0.1%.

Simulated deviation of the summed sink current from the intended curve at each crossover, after a 1 ms low-pass (roughly what a 240 fps frame integrates). Fade times are for the full 5 µA–1.4 A range; a shorter fade with the same rate of change in log(I) behaves the same.

| Full-range fade | As built: primed, log blend | Phase 1 plan: unprimed |
| --- | --- | --- |
| 1 s | 0.9–1.5% for \~10 ms, while the light changes 1.3% per ms | 15–17% |
| 10 s | 0.11–0.14% | 3.1–3.7% |
| 60 s | ≤0.03% | — |

Fades update the DAC at 4 kHz, so a 1-second full-range fade moves 0.3% per step. Static levels never update, so there's nothing to flicker.

### LED output, protection, off and on

**Cathode node.** J2 (Phoenix MSTBA, pin 1 LED−, pin 2 LED+) carries C\_a, 22 nF 100 V X7R 1206, across its pins. The node also has the four drains and a 1 MΩ tap into 1 nF, clamped by a BAV199 to GND and +3V3, feeding PA1.

- **What C\_a buys.** From 100 Hz to 20 kHz, down to 5 µA, it takes over 200 mV of V\_out ripple to make 1% of LED-current modulation, against 6.5 mV without it.
- **What it costs.** It delays first light from blackout, below.

**Short protection.** PA1 is also COMP1's input, with a fixed 3.0 V threshold from the internal DAC3. The trip interrupt engages all four clamps in about 1 µs. With the tap's RC the whole path takes 50–100 µs, a few millijoules in the FET at full power.

- The trip is masked only while the expected cathode voltage is above 2.6 V (V\_out leading a turn-on) and for 3 ms after; a comparator still tripped when the mask lifts counts as a short. A V\_f reading below 15 V then catches a short on the next ADC pass.
- A V\_out stuck at the ceiling would put 16 W on the FET. The comparator catches that too.

**Open LED.** V\_out reaches its ceiling while the cathode stays near 0 V. Firmware drops to the floor and reports it.

**Off.** Every sink sits in its dead zone and V\_out at its 3.5 V floor, where the array can't conduct at all.

**On.** V\_out rises first, then the sink comes up. C\_a lifts the cathode about 16 V on the way up, and the sink pulls it back. The LED current appears only in the last \~2 V, with the sink regulating throughout, so nothing overshoots.

| Turn-on target | Time to first light |
| --- | --- |
| 5 µA | about 52 ms |
| 140 µA | about 1.9 ms |
| 1 mA | about 0.26 ms |
| Above 1 mA | under 0.1 ms, plus the 0.6 ms V\_out step |

**Final fade to black.** Below the tail's end point (5 µA by default, adjustable), the sink is set just above the remaining current and V\_out keeps falling instead. The array current then follows V\_out exponentially, at 1.5% per buck-DAC code and one decade per 1.5 V. That runs down to picoamps before the floor, so there is no last step to see. The array can't dim faster than its own capacitance allows (an e-fold in 10 ms at 1 µA, 100 ms at 100 nA), which sets how fast the tail can finish.

### Board A MCU (STM32G431CBU6, internal HSI16, 170 MHz)

| Pin | Use |
| --- | --- |
| PA0 | V\_out sense (ADC1\_IN1) |
| PA1 | Cathode tap (ADC1\_IN2, COMP1\_INP) |
| PA2 / PA3 | USART2 to the STDC14 debug connector's VCP, for the calibration console |
| PA4 | DAC1\_OUT1 to buck FB injection |
| PA6, PA7, PB2, PB15 | Gate monitors ch1–4 (ADC2\_IN3, IN4, IN12, IN15) |
| PC6, PA8, PC10, PB7 | Gate clamps ch1–4 |
| PA9 / PA10 | USART1 to Board B (100 Ω each, PA10 100k pull-up). Also the ROM bootloader port |
| PA11 | A\_OK to Board B |
| PA12 | Status LED |
| PA13 / PA14 | SWD |
| PA15, PB3, PB4, PB5 | SPI1 to the DAC80504 |
| PB0 | 48 V sense (ADC1\_IN15) |
| PB1, PB11, PB12, PB14 | NTCs at the ch1 FET, main buck, aux rails and precision section |
| PB8-BOOT0 | 10k pull-down; Board B can raise it |
| PC13 / PC4 | Main buck EN / PG |
| PG10-NRST | 100 nF; driven by the STDC14 and by Board B (open-drain) |

Free for later: PA5 (DAC1\_OUT2, on TP11), PB6, PB9, PB10, PB13, PC11, PC14, PC15, PF0, PF1. PA5, PB6, PB9, PB10 and PB13 belong to ROM-bootloader interfaces, so nothing that must stay off during a reflash goes on them.

The exposed pad is VSS. Each VDD pin (23, 35, 48) and VBAT (1) gets 100 nF, with one 4.7 µF bulk. VDDA (21) and VREF+ (20) get 1 µF + 100 nF behind a ferrite.

### Error budget, updated

After calibration, with the board within ±20 °C of its calibration temperature:

| Range | Current | Sense | RSS | Worst case |
| --- | --- | --- | --- | --- |
| 1 (0.1 Ω) | 140 mA / 1.4 A | 14 / 140 mV | ±0.11% / ±0.10% | ±0.27% / ±0.20% |
| 2 (1 Ω) | 14 / 140 mA | 14 / 140 mV | ±0.09% / ±0.09% | ±0.23% / ±0.17% |
| 3 (10 Ω) | 1.4 / 14 mA | 14 / 140 mV | ±0.09% / ±0.09% | ±0.23% / ±0.17% |
| 4 (100 Ω) | 140 µA / 1.4 mA | 14 / 140 mV | ±0.11% / ±0.09% | ±0.28% / ±0.17% |
| Tail | 14 µA / 5 µA | 1.4 / 0.5 mV | ±0.6% / ±1.6% | ±1.3% / ±3.4% |
| Next channel's keep-alive armed | e.g. 0.7 mA | 70 mV | ±0.11% | ±0.32% |

Range 4 and the tail include \~70 nA of board and FET leakage, which always adds current. With the fallback shunt for R102 (Parts and ordering), range 1 widens to ±0.17% RSS and ±0.35% / ±0.28% worst case.

The budget is looser than Phase 1's ±0.05–0.08% for two reasons:

- The divider is now two discrete 25 ppm/°C resistors, budgeted as if they drifted in opposite directions (707 ppm RSS). Parts from one reel usually track far better, and a matched network would restore the Phase 1 figure.
- A 1.25 µV zero-bias drift term is new.

None of this touches smoothness: one DAC code is still 0.021% at the bottom of a range.

### Thermal

Board A dissipates about 2.8 W at full output. On its 90 × 60 mm of 4-layer board in still air, that is about +22 °C of average rise over the enclosure air.

- **FET.** The NDT3055L's 1.2 W at \~50 °C/W, on 5 cm² of its own 1 oz copper split between L1 and L4 and joined by 39 vias, puts its junction \~82 °C over air: about 127 °C in 45 °C air, against a 150 °C limit. (onsemi rates it at 42 °C/W on 6.5 cm² of 2 oz copper and 95 °C/W on 0.4 cm².) RT1 beside it reports that copper's temperature.
- **If it runs hot.** Headroom of 0.8 V instead of 1.0 V at full current would save 0.28 W, and a 100 × 70 mm outline would take about 5 °C off the board's rise.
- **Thresholds.** Without a chassis to sink into, the NTC limits are now per sensor:

| NTC | Derate from | Trip at |
| --- | --- | --- |
| ch1 FET | 95 °C | 110 °C |
| Main buck | 90 °C | 105 °C |
| Aux rails | 90 °C | 105 °C |
| Precision section | 75 °C | 90 °C |

At 45 °C air the 48 V draw is 45 W typical and 54 W worst case, 41–49% of the LRS-100-48's rating.

### Board B

Board B is a Waveshare ESP32-S3-Zero (ESP32-S3FH4R2: 4 MB flash, 2 MB PSRAM) plugged into two 1 × 9 sockets on the back of a 2-layer board of about 60 × 45 mm. The module brings its own USB-C, 3.3 V regulator and BOOT/RESET buttons, so Board B keeps only the power entry, the controls and the link.

**Why a socketed module.** It takes 17 parts off the board, among them the USB-C receptacle (0.5 mm pitch, the hardest part to hand-solder and the one the router struggled with), the USB ESD part, the 3.3 V regulator and the reset circuit. A spare module is a ten-second swap, and it's flashed out of the board. It hangs on the back because the operator panel sits a few millimetres above the top side, on the encoder, and the module on its sockets stands 12–14 mm tall.

**Power.** Ribbon +5V5 (pins 1 and 3) runs through a ferrite and a B5819W Schottky to the module's 5V pin, at about 5.1 V. The module's own ME6217C33 (800 mA) makes +3V3, which also feeds the encoder pull-ups and the LEDs. The 5V pin is the module's USB supply too: the Schottky keeps a USB supply out of Board A, but nothing keeps Board A's supply out of a computer, so the module is flashed out of its sockets, or with the ribbon unplugged.

**Controls.**

- Bourns PEC11R-4220F-S0024 encoder (24 detents, push switch). A and B use the Bourns filter: 10k pull-up, 10k series, 10 nF. The push input uses the same filter.
- The sync button is a 6 × 6 mm tactile switch in parallel with a 2-pin header for a panel button, with the same RC.
- Reset and BOOT are the module's own buttons.

| GPIO | Module pin | Use |
| --- | --- | --- |
| IO1 / IO2 | 4 / 5 | UART1 TX / RX to Board A, 100 Ω each |
| IO4 / IO5 / IO6 | 7 / 8 / 9 | Encoder A / B / push |
| IO7 | 10 | Sync button and external-button header |
| IO8 | 11 | BOOT0\_A to Board A |
| IO9 | 12 | A\_OK from Board A (100k pull-down, so an unplugged ribbon reads "not OK") |
| IO10 | 13 | NRST\_A, open-drain, 100 Ω |
| IO11 / IO12 / IO13 | 14 / 15 / 16 | Red / green / blue status LEDs, active low |
| IO3, IO43, IO44 | 6, 18, 17 | Spare header J4 with 3V3 and GND (IO43/IO44 are UART0, the ESP32's console) |

Only the module's edge pins reach the sockets: 5V, GND, 3V3, IO1–IO13 and IO43/IO44. IO4–IO13 keep the earlier WROOM design's assignments. The link moved to IO1/IO2 so UART0, which the boot ROM talks on, stays off Board A's line. IO3 is a strapping pin, so it's the spare. The module's RGB LED (IO21) isn't used.

The antenna end sits at a board edge over a copper keep-out; in a metal enclosure give it a plastic window or 15 mm of clearance. Mount the board at least 100 mm from Board A and the LED leads.

## Schematics

The schematic lives in code, so every connection has one source and every build runs a connectivity check. `design/board_a.py` and `design/board_b.py` declare each part and each pin's net; `design/catalog.py` holds the parts. `python3 design/build.py` regenerates everything and stops on any error.

The current build has no errors: Board A has 206 parts on 96 nets, and Board B has 42 parts on 32 nets.

| File | What it is |
| --- | --- |
| `hardware/board_a/board_a-sheets.md`, `hardware/board_b/board_b-sheets.md` | Every part, every pin with its datasheet name, and its net, sheet by sheet, then the full net list |
| `board_a.net`, `board_b.net` | KiCad netlists with footprints and part numbers attached |
| `design/compare_netlists.py` | Checks a netlist you export from your own schematic against the generated one, ignoring net names |

**Two ways into KiCad:**

1. **Straight to layout.** In the PCB editor, use File → Import → Netlist and pick `board_a.net`. Footprints and the ratsnest arrive together. The board then has no schematic behind it, so "Update PCB from Schematic" won't be available.
2. **Draw it, then prove it.** Enter each sheet from its table and use the net names as labels. Then export a netlist and run `compare_netlists.py` against the generated file. It lists any pin whose connections differ.

| Sheet | Contents |
| --- | --- |
| A1 | 48 V entry (J1, F1, D1, C1), 48 V monitor, aux buck U3, +5VA and +3V3 LDOs |
| A2 | Tracking buck U2, FB injection network, V\_out sense, D2 |
| A3 | DAC80504, SPI resistors, the four ÷13 dividers, BIAS source |
| A4 | OPA4388, four FETs, shunts and Kelvin net ties, gate clamps, gate monitors |
| A5 | LED connector J2, C\_a, cathode tap |
| A6 | STM32G431, STDC14 debug header, ribbon J3, NTCs, test points |
| B1 | Ribbon J1, ferrite and Schottky to the module's 5V pin |
| B2 | ESP32-S3-Zero on its two sockets (the module has its own USB-C, regulator, reset and boot) |
| B3 | Encoder, sync button and header, LEDs, link resistors, spare header |

**Conventions:**

- **Kelvin sense.** Kelvin connections on the 1, 10 and 100 Ω shunts use net ties NT1–NT6, so SNSHI*k* and SNSLO*k* route as their own nets from the pad. The WSK2512 has its own sense pads 2 and 3.
- **Markings.** NC means deliberately unconnected. DNP means a footprint only (C29).
- **Footprints.** Footprints are from the KiCad 8–10 standard libraries; KiCad 7 lacks the DAC's RTE0016D footprint. Board B's ESP32-S3-Zero socket footprint is this project's own, in `layout/lib/XTM.pretty`.
- **Footprints to check against datasheets before ordering:**
  - the LMR38020's HSOP-8 pad, 2.41 × 3.1 mm, against TI's DDA land pattern;
  - the DAC80504's RTE0016D footprint, with its 0.8 mm pad, against page 47 of TI's data sheet;
  - J4's 1.27 mm SMD header footprint against Samtec's FTSH drawing, and the PEC11R's lugs in the EC11E footprint's round 2.6 mm holes (a 1:1 print and a real encoder).

## Layout

Both boards are laid out by scripts in `layout/`: they place every part, draw the copper that matters by hand (switch nodes, the cathode tab copper, the shunt bus bars, the L2 plane), route the rest with Freerouting, pour and stitch ground, run KiCad 9's DRC against the rules below and write the Gerbers and placement files. `layout/README.md` says how to run them on Windows and what to check before ordering; `layout/out/` holds the boards they produced, both with no DRC errors and nothing unconnected. This section is what they follow and what to review their result against: layers, zones, loops, sense routing, widths and clearances. `hardware/LAYOUT.md` holds the same text, and `hardware/board_a.kicad_dru` / `board_b.kicad_dru` hold the clearances as KiCad custom rules. Coordinates are millimetres from each board's top-left corner.

### Board A: stackup and outline

JLCPCB's standard 1.6 mm four-layer stackup (7628 prepreg, about 0.2 mm from L1 to L2), ENIG. Nothing needs controlled impedance.

| Layer | Copper | Use |
| --- | --- | --- |
| L1 top | 1 oz | Every part. Signals, both switch nodes, the Kelvin pairs, local power copper, Q1's tab copper, then a GND pour |
| L2 | 0.5 oz | GND, solid. No splits, no tracks |
| L3 | 0.5 oz | Signals, then a GND pour over everything else |
| L4 bottom | 1 oz | Signals, Q1's heat spreader (CATHODE) under its tab, then a GND pour |

Routing some 200 parts on L1 and L4 alone left too many connections open, so L3 carries signals too (an earlier version kept it for +48V and VOUT pours). Every L1 track still has the unbroken L2 plane under it, and the power paths are wide enough on L1 without the L3 pours.

- 90.0 × 60.0 mm, 2 mm corner radius. Four non-plated M3 holes (3.2 mm, 6.5 mm keep-out on every layer) at (4, 4), (86, 4), (4, 56) and (86, 56). None connects to GND: the 48 V side stays unearthed (answer 4).
- Bottom edge: J1 (48 V in) between x = 70 and 80, J2 (LED out) between x = 36 and 48, wire entry facing off the board; its pin 1 is LED− (CATHODE, on the sinks' side) and pin 2 LED+ (VOUT, on the buck's side), so neither path crosses the other. Top edge: J3 (ribbon) between x = 50 and 72. Left edge: J4 (STDC14).
- No heatsink: in the wood or plastic enclosure (your answer 4) Board A cools through its own copper, 2.8 W at full, about 22 °C above the enclosure air on average (a 100 × 70 mm outline would take about 5 °C off that). Mount it on 10 mm standoffs with free air on both faces, near a vent. If it stands vertical, put the J1/J2 edge at the top so the power band's warm air doesn't rise across the precision island.
- Mount it within about 300 mm of the XTM, whose leads are 400 mm.

### Board A: floorplan

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/floorplan-dark.png">
  <img alt="Board A floorplan: seven zones on a 90 by 60 mm board" src="../images/floorplan-light.png">
</picture>

Every part except the holes and fiducials sits in exactly one zone (checked against the netlist):

| Zone | Where | Parts |
| --- | --- | --- |
| 48 V in | x 70–90, y 34–60 | J1, F1, D1, C1, R1, TP1, TP8 |
| Tracking buck | x 48–70, y 30–60 | U2, L2, C20–C30, D2, R10–R17, RT2, TP5, TP10 |
| LED output | x 36–48, bottom edge | J2 with C60 across its pins; R110, the cathode end of the cathode tap |
| Sinks | x 4–41, y 37–60 | Q1 on its tab copper with R102 and RT1; Q2–Q4 in a row along the top edge of the tab copper, R100/R101 with NT3–NT6 above Q3/Q4; the R90–R99 ladder with NT1/NT2; R68–R71 at the gates, Q5–Q8 and R72–R75 where there's room between the island and the sinks |
| Precision island | x 4–44, y 22–40 | U6, U7, R44–R54, R60–R67, R76–R83, C40–C48, C50–C55, RT4, TP7, TP9, TP12–TP19; U4 with C10–C12 and TP3 at its right edge |
| MCU and debug | x 0–44, y 0–20 | U1, J4, C56–C59, C70–C78, C80–C83, FB1, C15, C16, R40–R43, R120–R129, D4, TP6, TP11; R18/C31, R2/C2 and C61/D3 at their ADC pins |
| Aux rails and link | x 48–90, y 0–28 | U3, L3, C3–C9, C13, C14, R3–R7, U5, FB2, C79, J3, RT3, TP2, TP4 |

The 1.4 A loop (buck → J2 → LED → sinks → shunts → back to the buck and J1) stays in the bottom band, so none of its return current crosses the precision island. Board B's supply current returns through J3 in the aux corner, also clear of it. Both switch nodes sit at least 10 mm from every precision net.

### Board A: power layout

1. U2's input loop: C22 (100 nF) right at U2's VIN pin with a GND via beside its other pad; U2's own GND reaches the same L2 plane through its exposed pad's vias, so the loop closes through L2 directly under the part. C20/C21 beside it. U3 has C5 at its VIN pin and C4 beside it. (EN sits between VIN and GND on these parts; a capacitor straddling both pins would wall EN in behind the HV spacing, so EN leaves through a via and +48V comes in from C20 between C22's GND pad and that via.)
2. Both switch nodes (BUCK\_SW, AUX\_SW) on L1 only, as small as the current allows, with no vias: 0.5 mm past the BOOT capacitor's pad, then 1.2 mm to the inductor, about 5 mm in all. BOOT capacitors C23 and C3 straight across BOOT and SW.
3. L2 against U2's SW pin. Only plane copper under either inductor, on every layer.
4. U2's feedback network (R12–R15, C29, C30) beside its FB pin, on the side away from L2. R12 takes VOUT at the output capacitors C24–C27, not at J2.
5. U2 and U3 exposed pads: the footprint's own thermal vias (0.2 mm) to L2, L3 and L4. These, a 3 × 3 array of 0.3 mm vias under U1's exposed pad and a single one in U6's 0.8 mm pad are the only vias in any pad, all tented on L4 so solder can't run through.
6. C60 (C\_a) directly across J2's pins, above the slot. J2 pin 1 sits on the CATHODE tab copper; VOUT reaches pin 2 from the output capacitors, so the loop through the LED leads closes at the board edge.
7. Q1: 2.3 cm² of CATHODE copper from its tab to J2 on L1, and 39 vias of 0.3 mm, densest beside the tab, to 2.8 cm² on L4; the router is kept out of both. At 50 °C/W for that copper, the junction runs about 82 °C above the enclosure air at 1.4 A, 127 °C at 45 °C air, against a 150 °C limit. It adds about 110 pF to the cathode, well inside the 1000 pF the ripple budget allows. RT1 at the edge of the L1 tab copper.
8. R102 at least 2 mm from Q1's tab copper. Its I− pad goes to GND with four or more vias at the pad and wide L1 copper toward the buck's GND.

### Board A: sinks and the precision island

1. **Kelvin pairs.** Each channel's SNSHIx and SNSLOx start at the shunt's own sense points below and run to the island in 0.2 mm tracks, ideally together, on L1 over the L2 plane, with the same number of vias on both. The layout script gets the start points right and leaves the rest to the router, which doesn't keep the two tracks side by side; for these slow signals where they start matters far more, but redrawing each pair side by side by hand is the one refinement worth making. The divider bottoms (R46, R48, R50, R52) and the 10 nF C44–C47 return to SNSLOx, never to the plane.
   - Ch1: R102's pads 2 and 3.
   - Ch2: the ten 10 Ω resistors R90–R99 as rungs between two 1 mm bus bars, SRC2 fed at one end and GND taken out at the opposite end so every rung sees the same path. NT1 at the SRC2 bar's midpoint, NT2 at the GND bar's midpoint.
   - Ch3 and ch4: NT3/NT4 on R100's pads, NT5/NT6 on R101's.
2. **Setpoints.** Each divider pair (R45/R46 and so on) side by side in the same orientation, so both resistors sit at one temperature; C44–C47 at U7's +IN pins. Only the divider tops load DAC\_OUT1–4. C40 on U6's REF pin, and nothing else on that net.
3. **Op-amp.** C52–C55 (2.2 nF) and R60–R63 (1 kΩ) at U7's −IN pins; R64–R67 (1.82 MΩ) from BIAS straight to those pins; R53, R54 and C48 (the bias source) in the middle of the island. C50/C51 on U7's V+ pin; C41, C42 and C43 on U6's VDD and VIO.
4. **Gates.** R68–R71 (220 Ω) at the FET gates, not at the op-amp, with the clamp FETs Q5–Q8 and their pull-ups R72–R75 beside them. The gate-monitor dividers R76–R83 at U7's outputs, and C56–C59 at the MCU's ADC pins.
5. **Guarding.** The island is a ground cage: L1 GND pour around and between its parts, stitching vias every 3 mm across it and along its edges, L2 solid under it, and the GND pours of L3 and L4 filling around whatever tracks pass there. Every node inside sits within 0.2 V of GND, so the pour is also an equipotential guard. No HV-class net comes within 2 mm of a precision net (a DRC rule).
6. **Leakage at the bottom of the range.** At 5 µA, 50 nA of stray current is 1%. Keep the CATHODE net compact and soldermasked, cut a 1.0 mm non-plated slot, 6 mm long, between J2's two pads so flux or dirt can't bridge them, and wash the board after assembly.
7. **Temperature sensors.** RT2 between U2 and L2, RT3 between U3 and the LDOs, RT4 between U6 and U7.

### Board A: MCU

1. 100 nF on each VDD pin (C70–C73), C74 at the 3.3 V entry, C76 on VDDA (pin 21) and C77 on VREF+ (pin 20), fed through FB1. U1's exposed pad soldered and stitched to L2.
2. SPI series resistors at the driving end: R40–R42 at U1, R43 at U6's SDO.
3. The sense dividers put their high-voltage resistor at the high-voltage end and the rest at the MCU: R17 at the output capacitors with R18/C31 at PA0; R1 at +48 V with R2/C2 at PB0; R110 at the cathode with C61 and D3 at PA1. Each long trace then carries only a few volts, filtered at the pin.
4. BUCK\_DAC (PA4) runs to R15 beside U2 over the plane and away from the switch nodes; C30 filters it at the buck.
5. Link: R121–R123 at U1; R120 (BOOT0 pull-down) and C78 (NRST) at their pins.

### Track widths and clearances

IPC-2221 widths for a 10 °C rise, from `design/calc.py`, and what the layout script uses. Routed tracks take their net class's width, so the HV class is set to what still reaches U2's and U3's 1.27 mm-pitch pins with the HV spacing; the paths drawn before routing are wider.

| Path | Current | Minimum on L1 (1 oz) | As laid out |
| --- | --- | --- | --- |
| +48V\_RAW: J1 → F1 | 1.5 A | 0.53 mm | 2 mm, drawn |
| +48V: F1 → U2, U3 | 1.5 A | 0.53 mm | 0.6 mm, routed (HV class) |
| VOUT: L2 → C24–C27 → J2 pin 2 | 1.5 A | 0.53 mm | 0.6 mm, routed (HV class) |
| CATHODE: J2 pin 1 → Q1 | 1.5 A | 0.53 mm | The tab copper (a pour) |
| SRC1: Q1 → R102 | 1.5 A | 0.53 mm | 1.5 mm, drawn; four vias at R102's GND end |
| BUCK\_SW | 1.5 A rms, 1.84 A peak | 0.53 mm | 0.5 mm past C23's BOOT pad, then 1.2 mm; drawn |
| SRC2 and GND bus bars | 0.16 A | — | 1 mm, drawn, for rung symmetry rather than current |
| +5V5, +5V5\_LINK | 0.6 A | 0.15 mm | 0.5 mm, routed (Aux class) |
| AUX\_SW | 0.6 A | 0.15 mm | 0.5 mm, then 0.8 mm; drawn |
| Signals, Kelvin pairs, +3V3, +3V3A, +5VA | < 50 mA | — | 0.2 mm, to reach the 0.5 mm-pitch QFN pins |

- Vias 0.2 mm drill, 0.5 mm pad for signals and for each GND pad's own via to the L2 plane, placed before routing while there's still room beside every pad (JLCPCB's four-layer minimum is 0.2 / 0.45 mm, so no extra cost); 0.3 / 0.6 mm on the HV and Aux nets and for the stitching vias, every 3 mm across the board wherever there's room.
- HV-class nets (+48V\_RAW, +48V, VOUT, BUCK\_SW, BUCK\_BOOT, AUX\_SW, AUX\_BOOT, CATHODE): from IPC-2221B's Table 6-1 for 51–100 V: 0.5 mm to any other net where a bare pad is involved (A6, component terminations), 0.3 mm between copper under solder mask on L1 and L4 (B4 asks 0.13 mm), 0.3 mm on L2 and L3 (B1 asks 0.1 mm). The router keeps 0.5 mm throughout, since it can't tell a pad from a track. (An earlier version used 0.6 mm everywhere, B2's figure for bare copper conductors, which these boards don't have outside the pads; it walled U2's EN pin in.) Everything else 0.2 mm. Checked against KiCad 9's footprints, every part's own pins meet 0.5 mm: the tightest are the SOT-23 sinks Q2–Q4, 0.53 mm from the drain (CATHODE) to the gate and source pads (the rules file exempts them anyway, since a part sets its own pin spacing), then 0.645 mm from U2's and U3's lead pads to their exposed pads.
- Copper 0.5 mm from the board edge, pours 1 mm.

### Fabrication, silkscreen and cleaning

- Order: 4 layers, 1.6 mm, JLC's standard stackup, ENIG, 1 oz outer and 0.5 oz inner, tented vias, the order-number position marked on the silkscreen, and a 0.12 mm stencil. Exposed pads of U1, U2 and U3 at about 70% paste, as a windowpane that keeps paste off their vias; U6 keeps its footprint's single paste square.
- Silkscreen: +48V and − at J1; LED+ (red) and LED− at J2; pin-1 marks on J3, J4, U1, U6 and U7; a 48 V warning at J1; board name and revision.
- After assembly, wash the board with isopropyl alcohol and a soft brush, especially around J2, the CATHODE net, the sinks and the precision island, then dry it warm (50 °C, 30 minutes). Flux residue between a 40 V node and the cathode is the one thing that can visibly shift the bottom of the range.

### Board B

1.6 mm, two layers, 1 oz, ENIG: parts, signals and a GND pour on top, a GND pour on the bottom. 60.0 × 45.0 mm with a 2 mm corner radius; non-plated M3 holes at (4, 41) and (56, 4), with the encoder's panel nut as the third fixing. The ESP32-S3-Zero, bought with its pin headers fitted (ESP32-S3-Zero-M), plugs into two 1 × 9 2.54 mm female headers 15.24 mm apart on the **bottom**: allow 12–14 mm behind Board B in the enclosure, plus a millimetre or two.

| Part | Where |
| --- | --- |
| U1 ESP32-S3-Zero on two 1 × 9 sockets | Bottom side, centred at (48.1, 33.0), long axis across the board: antenna end at the right-hand edge, USB-C end pointing into the board. Pins 1–9 (5V, GND, 3V3, IO1–IO6) along y = 25.4 from x 37.9 to 58.3; pins 10–18 (IO7–IO13, RX, TX) back along y = 40.6. No copper on either layer under the antenna end (a keep-out in the footprint); the silkscreen on the back names the module and marks both ends |
| SW3 encoder | Top-left, shaft and nut through the operator panel |
| D3–D5 with R15–R17, SW4 | Below the encoder, visible and reachable through the panel; J3 (external sync button) in the top-left corner |
| J1 ribbon with R18–R23 | Left edge, the series resistors and R22 at the connector |
| FB1, D1, C1, C3 | Between J1 and U1; C1 at U1's 5V pin, C3 at its 3V3 pin |
| R7–R14, C8–C11 | R7, R9, R11, R13 at the encoder; R8, R10, R12, R14 and C8–C11 at U1's IO4–IO7 |
| J4, TP1–TP3 | Bottom edge and bottom middle |

- Power tracks 0.3 mm (0.5 A at most), everything else 0.2 mm.
- Solder the two sockets with the module plugged in, so they end up exactly parallel.
- Print the board 1:1 (B.Cu, B.SilkS and Edge.Cuts, mirrored) and lay the module on it, pins into the pads, before ordering: its footprint is this project's own (`layout/lib/XTM.pretty`), drawn from Waveshare's figures and product photo.

## Parts and ordering

**Recommendation: hand-assemble both boards**, for the reasons in Phase 1. The precision parts come from franchised distributors, a single stencil pass gives the cleanest analog region, and JLC placement saves little at six builds. JLC files are included for the fallback.

| File | Use |
| --- | --- |
| `board_a-bom-hand.csv`, `board_b-bom-hand.csv` | One line per part type: references, quantity per board, quantity to buy for 7 sets plus spares, MPN, LCSC number, footprint, verification status |
| `board_a-bom-jlc.csv`, `board_b-bom-jlc.csv` | JLC format (Comment, Designator, Footprint, LCSC Part #), with each line's Basic/Extended class and fee |
| `board_*-cpl-template.csv` and `design/kicad_pos_to_jlc_cpl.py` | A CPL needs coordinates, which only exist once the board is laid out. The script turns KiCad's position export into JLC's CPL, applying rotation corrections for these footprints. Check JLC's placement preview anyway |

**Verification.** Every part number in the BOMs was checked against a distributor or manufacturer page, and again in an independent review on 29 September 2026. Twenty-one generic parts are listed by description, because any maker's part will do: passives, the box header, pin headers and tactile switches.

The first round of checks changed four earlier picks:

- **Input electrolytic.** EEE-FK2A470AQ turned out to be a 12.5 mm can. It is replaced by a 10 × 10.2 mm Honor Elec RVT2A470M1010 (LCSC C87862), and any 47 µF 100 V 10 mm SMD can fits.
- **LEDs.** The Everlight green and blue LEDs are out of stock. Hubei KENTO KT-0603G, -R and -B (C12624, C2286, C2288) replace them.
- **Ferrite bead.** The GZ2012D601TF bead is rated only 500 mA, so it stays on VDDA. The ribbon supply gets the 2 A UPZ2012E601-2R0TF (C98308).
- **Encoder.** LCSC's encoder (C462143) is the knurled-shaft PEC11R-4220K with under 100 in stock. Buy the flatted PEC11R-4220F-S0024 from Digi-Key or Mouser.

| Part | Where from | Notes |
| --- | --- | --- |
| DAC80504RTET | TI, Digi-Key, Mouser | RTER is the same part on a larger reel. Package RTE0016D |
| OPA4388IPWR | TI, Digi-Key, Mouser |  |
| WSK2512R1000FEA | Vishay, factory order | 0.1 Ω 1%, ±35 ppm/°C, four-terminal. No distributor stock on 29 Sep 2026. If the lead time is long, fit WSL2512R1000FEA (Newark, Avnet, Future; two-terminal, ±75 ppm/°C) on the same pads |
| RT0805BRD0712KL, RT0805BRD071KL, RT0805BRD0710RL, RT0805BRD07100RL | Newark, Arrow, TME | 0.1%, 25 ppm/°C thin film. The 10 ppm/°C grade (RT0805BRB…) exists in the same values. If you can find it, it roughly halves the drift terms in the budget |
| STM32G431CBU6 | LCSC C529356; Avnet, Arrow, Newark | LCSC had 61 on 29 Sep 2026, so order early |
| LMR38020FDDAR × 2 | LCSC C5149193 | Forced-PWM variant only |
| TPS7A2050PDBVR | Digi-Key, Mouser | Out of stock at LCSC on 29 Sep 2026 |
| TDK C3225X7S2A475K200AB × 7 | Newark, Avnet, Future | Out of stock at LCSC on 29 Sep 2026. Any 4.7 µF ≥100 V X7R/X7S 1210 fits |
| NDT3055L, 2N7002BK,215, 2N7002,215, BAV199,215 | LCSC C274612, C282405, C65189, C40919 | Nexperia 2N7002 specifically, for its gate-leakage limit |
| Waveshare ESP32-S3-Zero-M (headers fitted) × 1 per board, plus two 1 × 9 2.54 mm female headers | Waveshare's store; also sold on Amazon and AliExpress | The 4 MB flash / 2 MB PSRAM version (without headers it's SKU 25081). Sockets: any 1 × 9 female header about 8.5 mm tall, gold-plated contacts |
| Littelfuse 0452003.MRL | Digi-Key, Mouser | 3 A slow-blow, 125 V AC/DC |
| Phoenix 1757242 header × 2 per board, plug 1757019 × 2 | Digi-Key, Mouser |  |
| Samtec FTSH-107-01-L-DV-K | Samtec | STDC14 debug header. Not the -K-A version ST names: its alignment pins need holes the footprint lacks |
| Bourns PEC11R-4220F-S0024 | Newark, Digi-Key | LCSC stocks only the knurled -4220K |

**Not on either BOM:**

- Mean Well LRS-100-48, from an authorized distributor.
- STLINK-V3MINIE.
- A 10-way 28 AWG ribbon with two IDC sockets.
- Encoder knobs.
- A USB-C cable, for flashing the ESP32-S3-Zero.

**Quantities.** Order 10 bare boards of each design (JLC's minimum is 5) and one stencil per design. Parts are counted for 7 sets: the 6 you build (4 fixtures and 2 spares) plus one more. Cheap passives get at least 10 extra.

**If you use JLC after all:**

- Board A carries 28 Extended part types: about $86 of feeder-loading fees per order at JLC's $3.07 per type (Economic PCBA). JLC can't place the DAC, op-amp, 0.1 Ω shunt, fuse, three connectors or the sixteen 0.1% resistors LCSC doesn't list (12.0k, 10 Ω and 100 Ω), so those are soldered by hand afterwards.
- Board B carries 3 Extended types (the green and blue LEDs and the ferrite), about $9; J1, J3, J4, the encoder and U1's two sockets are soldered by hand, and the ESP32-S3-Zero plugs in.
- JLC had little or none of the TDK 4.7 µF 100 V capacitors, the TPS7A2050 and the STM32 on 29 Sep 2026: pick an in-stock 4.7 µF 100 V 1210 in JLC's BOM tool, and pre-order or consign the two ICs.
- Descriptive lines need a part picked in JLC's BOM tool.

## Firmware

Both boards' firmware is written, builds and passes its tests: Board A is 49.9 KB of C (of 126 KB) and passes 97,146 host checks; Board B is an ESPHome configuration plus one external component, tested on ESPHome's own Linux build. Everything is under `firmware/`, with a README per board.

### Board A: STM32G431, bare-metal C on ST's LL drivers

| Part | What it does |
| --- | --- |
| 4 kHz control tick (TIM6) | Advances the fade (curve position b, linear in time, so a constant rate in log current), splits the current across the four sinks (log-ratio blend, keep-alive, arming), writes the DAC80504 codes under a monotonic guard, and leads or lags V\_out: rising current waits for V\_out, falling current goes first |
| Protection | COMP1 on the cathode tap (fixed 3.0 V, masked while the expected cathode exceeds 2.6 V) engages all four gate clamps from its interrupt in about 1 µs. Monitors: 48 V under 40 V for 20 ms, buck power-good, open LED (V\_out at its ceiling with the cathode near 0 V for 200 ms), short (V\_out − V\_cathode under 15 V), DAC read-back errors, four NTCs with derating from 95/90/90/75 °C and a trip 15 °C higher |
| Fault policy | Short and open retry three times, 5 s apart, then latch until cleared; undervoltage and over-temperature clear by themselves |
| Background | 16× oversampled ADCs on DMA, headroom learning every 10 ms (a 12-bin V\_f table), deferred flash save, the link, the console, the status LED, a 50 ms watchdog |
| States | BOOT → OFF → STARTING (V\_out first, then a probe of at most 1 mA) → ON → TAIL (the voltage-mode fade to black) → OFF, plus FAULT and RAW (calibration) |

`src/core` holds everything portable (curve and light matching, channel calibration and blend, fade engine, LED model, framing, parameter storage) and is what the host tests cover; `src/hw` holds everything that touches a register.

Build and flash (CMake 3.20+, Ninja, arm-none-eabi-gcc 12 or later; built here with xPack 14.2.1):

```sh
cd firmware/board-a
cmake -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake
cmake --build build
STM32_Programmer_CLI -c port=SWD mode=UR -w build/board_a.elf -v -rst   # or OpenOCD / pyOCD
make -C tests                                                          # host tests, ASan/UBSan
```

The STLINK-V3MINIE on J4 also carries the console (115200 8N1): `st` for status, `lvl`/`b` for levels, `raw`/`rawi`/`ka`/`dark`/`cal` for calibration, `set`/`get`/`params`/`save` for settings. Leave the option byte nSWBOOT0 at its factory 1 so the BOOT0 pin, driven low by Board B, decides the boot mode.

### The link between the boards

UART at 115200 8N1 over the ribbon. Frames are `[type][seq][payload][CRC-16]`, COBS-encoded and 0x00-terminated, defined once in `link_protocol.h` and shared by both boards (Board B's test fails if its copy drifts).

| Message | Direction | Payload |
| --- | --- | --- |
| SET\_LEVEL | B → A | level 0–65535 (0 = off), fade in ms |
| PING | B → A | none; B sends one every 200 ms |
| HOLD | B → A | seconds to ignore link silence (planned reboot, OTA) |
| CLEAR\_FAULT, IDENTIFY | B → A | none; blink count |
| SET\_PARAM, GET\_PARAM | B → A | parameter id, value, save flag |
| STATUS | A → B | every 100 ms and on each command: levels, state, fault, flags, LED current and voltage, V\_out, 48 V, four temperatures, firmware, uptime, level\_link |
| ACK, PARAM | A → B | result; parameter value |

Board B owns the level. Board A echoes the last level it received (`level_link`) and flags a link-loss fallback, so Board B re-sends only when a frame was lost, Board A restarted or Board A fell back, and a level typed on the console stands. If Board A hears nothing for 1.5 s, it blinks twice and drops to 20% (your answer to question 10). A planned Board B restart sends HOLD first, so the light doesn't move; after a crash, Board B restores the pre-loss level when it's back. Board B adopts Board A's level when Board A was already running, so an OTA update never changes the light.

### Board B: ESPHome 2026.9.0 on the ESP32-S3

`firmware/board-b/xtm-common.yaml` is the device, shared by all four fixtures; `xtm-1.yaml` to `xtm-4.yaml` set each one's name and keys. The external component `xtm_driver` provides:

- **The light.** One dimmable light in Home Assistant. Brightness goes to Board A as a level on Board A's own curve (so `gamma_correct` is fixed at 1.0), and a transition goes as one fade command that Board A runs.
- **The knob.** 1% of the scale per detent (about a 13% change in light) as an 80 ms fade, ×2 or ×4 when spun fast; up from off starts at the bottom, down stops there. The push toggles with a 400 ms fade.
- **Sync.** The sync button makes this fixture the lead: the others follow its level over ESP-NOW, fixture to fixture, with no router or Home Assistant in the path. Pressing it on another fixture moves the lead; pressing it on the lead ends the group, and every fixture keeps its level. Adjusting a follower by hand takes it out of the group. Packets carry an HMAC-SHA256 tag under a shared key. All fixtures must be on the same Wi-Fi access point, because ESP-NOW shares the radio's channel.
- **Entities.** LED current and voltage, driver output and input voltages, four temperatures, state, fault, sync role, firmware, link and derating flags; clear-fault, identify and restart buttons; Board A's settings (link-loss level, bottom current, full-scale current, fleet reference light, link timeout); a Sync lead switch.
- **Status LED** (dimmed, 25 kHz): green for 2 s at start; red slow blink = no Board A; red fast blink = fault; steady blue = leading the group; blue blip = following; amber blip = no Wi-Fi; off = normal.

```sh
cd firmware/board-b
cp secrets.yaml.example secrets.yaml     # Wi-Fi, a per-fixture API key, the shared sync key
esphome run xtm-1.yaml                   # first time with the module out, over its USB-C; then over Wi-Fi
```

Tests: `make -C tests` (89 checks on the link client and sync logic, including 30% packet loss); `tests/host/run_host_test.py` runs the component in ESPHome's Linux build against a simulated Board A on a pseudo-terminal and drives it through the native API as Home Assistant does (43 checks: transitions, knob, settings, a lost frame, a Board A reset, link silence, planned and unplanned restarts, power-up restore); `check_sync_glue.py` compiles the ESP-NOW code against ESPHome's real headers. The one thing not run here is the ESP32-S3 build itself: it downloads its toolchain from the PlatformIO registry, which this environment can't reach. Run `esphome compile xtm-1.yaml` before ordering.

## Bring-up

Seven steps take the first fixture from bare board to a calibrated light in about two hours; the next three take about 30 minutes each. Each step has a pass line; stop at the first miss. Per your note, the tests are the minimum that proves the board is safe and the loops behave. Everything else is assumed and caught by calibration or the flicker check.

**You need:** a bench supply to 60 V with a current limit, a DMM, an oscilloscope, the STLINK-V3MINIE, a dummy load of ten 1 W white LEDs in series on a heatsink (about 30 V, good for 350 mA), and the XTM on its heatsink. Never plug or unplug the LED while the light is on: J2 can sit at 38 V.

1. **Before power.** Inspect U1, U2, U3, U6 and U7 under magnification, and the polarity of D1–D3 and C1. Ohms to GND: TP1 (+48V) about 78 kΩ, TP5 (VOUT) about 170 kΩ, TP2–TP4 (+5V5, +5VA, +3V3) above 1 kΩ once the capacitors charge.
   - Pass: no reading under 10 Ω.
2. **First power.** No LED, no Board B. Bench supply at 48 V, limit 100 mA. Raise it slowly from 0 V: the aux rails start between 32 and 41 V.
   - Pass: input current under 30 mA; TP2 5.53 V ±3%, TP3 5.00 V ±1.5%, TP4 3.30 V ±2%, TP7 (BIAS) 0.455 V ±2%; TP5 near 0 V (the main buck is held off until firmware runs).
3. **Flash and boot.** Flash Board A (Firmware section) and open the console. D4 blips every 2 s when idle.
   - Pass: the banner reads `dac80504=ok`; `st` shows state off, `v48` within 1% of the supply, V\_out 3.5 V (check at TP5) and all four temperatures within 3 °C of the room.
4. **No-load protection.** Type `b 0.3`. With nothing to drive, V\_out climbs to about 38 V, then Board A reports an open LED and drops back to the floor. It retries three times, 5 s apart, then latches; `clear` resets it.
   - Pass: `st` shows `fault=open` within about 3 s, and V\_out returns to 3.5 V.
5. **Dummy load, every channel.** `set 9 0.3` (full scale 0.3 A for this step, not saved). Connect the dummy with the DMM in series, then step through `b 0.2`, `0.4`, `0.6`, `0.8` and `1.0`: about 45 µA, 0.4 mA, 3.7 mA, 33 mA and 300 mA, which exercises all four channels (channel 4 twice).
   - Pass, per point: the DMM within 3% of `st` (5% at 45 µA; calibration fixes the rest), and the cathode 0.5–1.2 V.
   - Loops: on the scope, TP5 shows only the 400 kHz ripple (about 27 mV p-p) and the active channel's sense point (TP13, 15, 17 or 19) is flat DC, with no oscillation at any point. A snap from `b 0.3` to `b 0.9` moves V\_out smoothly within about 2 ms.
   - Fades: `b 1 10000`, then `b 0 10000`. No fault; smooth both ways, ending dark.
   - Short: at `b 0.4`, short J2's pins with a wire. Pass: `fault=short` at once and the light off. Remove the wire, `clear`.
6. **The XTM.** `set 9 1.4`, then connect the XTM with the light off and raise the supply limit to 2 A. `b 1`.
   - Pass: `st` shows about 1.40 A, LED voltage 28.6–36 V and cathode about 1.0 V. After 10 minutes at full, the FET sensor stays under 90 °C with no derating flag, and the supply draws about 1 A.
7. **Board B.** Flash the ESP32-S3-Zero out of the board, over its USB-C (`esphome run xtm-1.yaml`), plug it into Board B's sockets (USB-C end toward the middle of the board), fit the ribbon and power Board A. The status LED shows green for 2 s, then goes dark.
   - Pass: Home Assistant shows the fixture, Driver link on; a 50% turn-on with a 2 s transition fades in; the knob steps and the push toggles.
   - Link loss: unplug the ribbon with the light on. Pass: after 1.5 s the light blinks twice and settles at 20%; plugged back in, it returns to its level within about a second.

Then calibrate, then run the flicker check.

## Calibration

Each fixture needs one current calibration, about 10 minutes with a script; light matching across the four fixtures is optional and takes another 10 minutes each. Both run over the Board A console from `firmware/board-a/tools/calibrate.py` (`pip install pyserial`, plus `pyvisa` to read a SCPI meter directly).

### Current, per fixture

**Setup.** A 6½-digit DMM (a 100 µA range for the bottom points, 3 A for the top) in series with the XTM's red lead: J2 pin 2 → DMM → LED+. The XTM on its heatsink, the room near 25 °C, and Board A warmed for 10 minutes at a middle level: the error budget assumes the board stays within ±20 °C of this temperature.

```sh
python3 tools/calibrate.py current --port /dev/ttyACM0                 # type each DMM reading
python3 tools/calibrate.py current --port /dev/ttyACM0 --dmm "USB0::…"   # or let it read a SCPI meter
```

The script clears the old calibration, then:

1. Reads the dark current with every sink off (tens of nA: board and FET leakage, always additive).
2. Drives one channel at a time in raw mode at eight points, two per band, and each band on **both** channels that share it, so the two agree at every crossover: ch4 at 140 µA and 1.5 mA, ch3 at 1.5 and 15 mA, ch2 at 15 and 150 mA, ch1 at 150 mA and 1.4 A. The 1.4 A point settles for 30 s.
3. Measures the keep-alive current of channels 3, 2 and 1, minus the dark reading, as each channel's low point.
4. Prints the result (`calshow`) and saves it.

Each channel's model becomes piecewise-linear through its measured points. Board A raises V\_out on its own to cover the meter's burden voltage; if `st` shows the cathode under 0.4 V at the 1.4 A point (a high-V\_f module with a high-burden meter), measure that point across a 0.1 Ω four-terminal reference resistor with the DMM on volts instead.

**Result.** Per the error budget: ±0.09–0.11% RSS (±0.17–0.32% worst case) in each of the four ranges, and in the tail ±0.6% at 14 µA and ±1.6% at 5 µA RSS (±1.3% and ±3.4% worst). To spot-check, put the meter back and compare `st` at a few `b` positions per range.

### Light matching across fixtures (optional)

The XTM's flux tolerance is ±10%, so four fixtures at the same current can differ by up to 20% in light. Matching makes them agree at every level instead: the brightest fixtures run a little under 1.4 A at 100%.

1. On each fixture, after its current calibration: a lux meter on the beam axis at a fixed distance in a dark room, the fixture warmed 5 minutes at full, then `python3 tools/calibrate.py lux --port …`. It drives 0.14 A and 1.4 A, asks for the two lux readings and stores them. Home Assistant then shows the fixture's **Full scale light**.
2. Take the lowest full-scale reading of the four as the fleet reference and set it on every fixture: `python3 tools/calibrate.py fleet --port … --ref <lux>`, or the **Fleet reference light** number in Home Assistant. Setting it to 0 turns matching off (current matching).

Each fixture then solves η(I) × I = reference × φ(b) for its current, with its efficacy η interpolated in log(I) between its two measured points. Matching holds at the calibration temperature; the XTMs' own thermal and ageing drift is outside it.

### Storage

Everything lives in the last 2 KB flash page of Board A (magic `XTM1`, format version 1, CRC-32): per-channel calibration points, the dark current, curve end points, the link-loss level, the light calibration and reference, headroom settings and the learned V\_f table. `save` on the console, or any setting changed from Home Assistant, writes it, but only once the light is off or under 10 mA and not fading, because erasing flash stalls the CPU for about 20 ms. A failed CRC at boot loads defaults and clears the Calibrated flag in Home Assistant. Firmware updates leave that page alone, unless you mass-erase the chip. Keep each board's `calshow` and `params` output as a text file: if its flash is ever erased, `raw ch code` followed by `cal ch amps` for each listed point, and `set` for each parameter, restores it without the meter. A replacement Board A needs its own calibration.

## Flicker verification

The photodiode rig is the measurement; the phone check is a quick look anyone can repeat. Pass means nothing over 1% between 100 Hz and 20 kHz at any level, no step or reversal during a fade, and a smooth fade to black. By design the only periodic content is the buck's 400 kHz ripple (about 0.1% at the bottom of the range) and the 4 kHz fade update, whose steps are 0.03% in a 10 s full-range fade and 0.3% in a 1 s one.

### Photodiode rig

- **Sensor.** A BPW34 PIN photodiode (or any PIN photodiode of a few mm²) at zero bias into a transimpedance amplifier: cathode to the op-amp's −IN, anode to ground, output positive. Use a FET-input op-amp (TI's OPA140, for example) on two 9 V batteries, so no bench-supply ripple gets in.
- **Gain.** 10 kΩ ∥ 100 pF for the top of the range (160 kHz bandwidth); 1 MΩ ∥ 2.2 pF for the bottom (72 kHz). Both cover the band to 20 kHz.
- **Placement.** Down to about 1 mA, the photodiode 0.5–1 m from the fixture on its axis at 10 kΩ. Below that, against the fixture's front at 1 MΩ, under a black cloth. Adjust the distance for an output between 0.3 and 3 V.
- **Scope and analysis.** Read the DC level DC-coupled, then capture the ripple AC-coupled on a fine scale: 200 ms at 1 MS/s or faster, exported as CSV. `firmware/board-a/tools/flicker.py ripple.csv --mean <DC level>` reports percent flicker below 20 kHz, the largest line from 100 Hz to 20 kHz and the largest line at 25 kHz and above, then PASS or FAIL. `--dark` subtracts the reading with the light off.

### What to capture

Run with light matching off (fleet reference 0), so each `b` below is the current shown; the console is on the STLINK.

| Capture | Console | Pass |
| --- | --- | --- |
| Steady levels | `b 1` (1.4 A), `b 0.822` (150 mA, ch1 and ch2 sharing), `b 0.638` (15 mA), `b 0.455` (1.5 mA), `b 0.266` (140 µA), `b 0.082` (14 µA), `b 0` (5 µA) | Percent flicker and every line from 100 Hz to 20 kHz ≤ 1% |
| Band crossings at the 10 s full-range rate | `b 0.78`, then `b 0.86 800` and back with `b 0.78 800`; the same between 0.60 and 0.68, and between 0.41 and 0.49 | Largest departure ≤ 0.3% (simulated 0.11–0.14%), no reversal |
| Band crossings at the 1 s rate | The same with 80 ms instead of 800 | ≤ 2% (simulated 0.9–1.5%), no reversal |
| Fade to black | From `b 0.3`, `lvl 0 3000` | Smooth to dark with no step at the end |
| Snaps | From off, `b 0.5`; then `b 1` | One rise to the target within 5 ms, no overshoot |

For fades, capture DC-coupled in the scope's high-resolution mode (100 kS/s is plenty) and run `flicker.py fade.csv --fade`. It compares a 1 ms average with the fade's own trend, the measure the handover simulation used, and counts any moments the light moves against the fade.

### Phone check

In slow-motion mode (240 fps), film a white wall lit by the fixture and a pencil waved quickly in front of it, at the steady levels above and during a 10 s fade. Then, in the camera's manual mode at 1/4000 s or faster, watch the lit wall in the live view. Pass: no rolling bands, no pulsing in playback, a smooth fade. A PWM-dimmed light shows bands in the same test, which makes a useful reference.

## Pre-order checklist

Tick these off as you go (the [build guide](../BUILD_GUIDE.md) has the same list). Nothing on the list is a new test; each one catches a mistake that would cost a board revision or a parts order.

### Design files

- [ ] Schematics captured in KiCad match the generated netlists: export a netlist from each schematic and run `python3 design/compare_netlists.py hardware/board_a/board_a.net <yours>.net` (and the same for Board B). It compares connectivity, so net names may differ.
- [ ] ERC clean. DRC clean with `hardware/board_a.kicad_dru` and `board_b.kicad_dru` in place (KiCad 9, which the layout scripts use) and their net classes created.
- [ ] Every Board A part in its floorplan zone; the Layout section's rules met (Kelvin pairs, switch nodes on L1 only, the precision island's ground cage, J2's slot).
- [ ] Footprints checked pin by pin against the datasheets for the parts that bite: U6 DAC80504RTET (RTE0016D, 0.8 mm pad, pin 1), U7 OPA4388 (TSSOP-14), U2 and U3 LMR38020 (HSOP-8 with exposed pad), U1 STM32G431CBU6, R102 WSK2512 (pads 1 and 4 carry current, 2 and 3 sense), Q1 NDT3055L (G-D-S, tab = drain), D3 BAV199, J4 STDC14, Board B's ESP32-S3-Zero socket footprint (the project's own) and the PEC11R on the EC11E footprint with round lug holes.
- [ ] Both boards printed 1:1 on paper, with the parts that can surprise laid on their footprints: the SRR1260 inductors, the 10 × 10 mm electrolytic, the MSTBA connectors, the box header, the encoder, and the ESP32-S3-Zero laid on Board B's back (a mirrored print).
- [ ] Mechanics: Board A's holes and standoffs, air space on both faces and wire access to J1/J2 in the enclosure; Board B's encoder shaft length against the panel, 12–14 mm of room behind Board B for the ESP32-S3-Zero on its sockets, and its antenna end clear of any metal with 15 mm around it.
- [ ] Silkscreen: polarity at J1 and J2, pin-1 marks, the 48 V warning.
- [ ] Gerbers opened in a viewer (KiCad's GerbView or JLC's): four copper layers in order, the drill file including J2's slot, paste layers present.

### Fabrication order (JLCPCB)

- [ ] Board A: 4 layers, 1.6 mm, the standard stackup, ENIG, 1 oz outer and 0.5 oz inner, tented vias, order-number position specified. Board B: 2 layers, 1.6 mm, ENIG.
- [ ] Quantity 10 of each (JLC's minimum is 5): six sets to build, four fixtures and two spares.
- [ ] A 0.12 mm stencil for each board.
- [ ] Only if JLC places parts: CPL regenerated from KiCad's position file with `design/kicad_pos_to_jlc_cpl.py`, and every part's rotation checked in JLC's placement preview before paying.

### Parts order

- [ ] Stock checked on the day, for seven sets, from the hand-assembly BOMs (`hardware/*/…-bom-hand.csv`, spares included).
- [ ] The buck is **LMR38020FDDAR**, the forced-PWM variant, not the SDDAR. The encoder is **PEC11R-4220F-S0024** from Digi-Key or Mouser (LCSC stocks only the knurled -4220K).
- [ ] J4 is the **FTSH-107-01-L-DV-K**, not the -K-A that ST's manual names. The J1/J2 plugs (Phoenix 1757019) are on Board A's BOM.
- [ ] The precision parts from franchised distributors: DAC80504RTET, OPA4388IPWR, the 0.1% thin-film resistors (RT0805 series) and NDT3055L. For R102, the WSK2512R1000FEA if Vishay's lead time suits, otherwise the stocked WSL2512R1000FEA.
- [ ] The parts the BOM describes rather than numbers (18 lines on Board A, 6 on Board B): value, voltage rating, dielectric (C0G where it says C0G, 100 V where it says 100 V) and size each checked.
- [ ] Off-board items: four XTM19803050CCA modules and heatsinks, the LRS-100-48 and its fused inlet, 10 mm M3 standoffs, 10-way ribbon cable with two IDC sockets per set, M3 hardware, the STLINK-V3MINIE.

### Firmware

- [ ] `esphome compile xtm-1.yaml` succeeds on your machine; it's the one build that couldn't be run here.
- [ ] `secrets.yaml` created, with one API key per fixture and a shared sync key.
- [ ] Board A still builds with your toolchain (`cmake --build build`) and `make -C tests` passes.

### Bench

- [ ] Bring-up: a 60 V current-limited supply, a DMM, a scope, the dummy load (ten 1 W white LEDs in series on a heatsink).
- [ ] Calibration: a 6½-digit DMM with a 100 µA range; a lux meter if the fixtures will be light-matched.
- [ ] Flicker: a BPW34 photodiode, a FET-input op-amp, 10 kΩ, 1 MΩ, 100 pF and 2.2 pF parts, two 9 V batteries; a phone with 240 fps slow motion.

## Assumptions, in one list

Every figure in this design rests on these. Correct any line and I'll re-run what depends on it.

1. Six board sets are built, four fixtures and two spares, with parts bought for seven.
2. The XTM matches its June 2023 Standard Series datasheet: 1,400 mA rated (1,500 mA with tolerance), V\_f 28.6 / 29.9 / 36.0 V at 1.4 A over 20–90 °C, ±10% flux, fixed 20 AWG leads 400 mm long, damaged by reverse polarity.
3. At low current the array's slope nNV\_T is about 0.65 V (1.5 V per decade), it bypasses at most about 50 nA, and its cathode sees 0.3–1 nF outside the loop. None is measured before layout, per your note. If the bottom of a fade shows a jump, raise the Bottom current setting.
4. Board A stays within ±20 °C of its roughly 25 °C calibration temperature, in enclosure air at or below 45 °C, cooling through its own copper on standoffs (no heatsink, per your answer 4).
5. 48 V comes from a Mean Well LRS-100-48 (at most 52.8 V) with its own fused inlet; neither board carries mains.
6. Headroom is 1.0 V at full current and 0.7 V at low current. V\_out runs from a 3.5 V floor to a 38 V usable ceiling, and 40.4 V only if the MCU's DAC fails low.
7. The calibrated range is 1.4 A to 140 µA, with a monotonic, less accurate tail to 5 µA. Off means every sink off and V\_out at its floor.
8. Brightness 0–100% maps to 5 µA–1.4 A on an exponential curve: 1% of the scale is about 13% in light, and Home Assistant's lowest step is about 5.3 µA.
9. Board A runs every fade itself at 4 kHz (Phase 1 said 1 kHz); a snap completes within 5 ms.
10. The flicker limit means under 1% between 100 Hz and 20 kHz, read as percent flicker and as spectral lines; deliberate content at 25 kHz or above is allowed.
11. Phone cameras run exposures from 1/8000 s to 1/30 s at 30–240 fps.
12. The venue is indoor, dry, possibly hazed and unattended, with one Wi-Fi access point and usually Home Assistant; every fixture works on its own, and sync needs all of them on that access point.
13. When Board B goes quiet, Board A blinks twice and drops to 20% (your answer); a planned Board B restart holds the level instead.
14. The error budget uses datasheet maximums for drift and typical values for noise.
15. The boards are made at JLCPCB on its standard stackups with ENIG, and hand-assembled with stencils; precision parts come from franchised distributors. The layout is drawn by the scripts in `layout/` with KiCad 9.
16. You have a 60 V current-limited supply, a 6½-digit DMM with a 100 µA range, a scope with FFT and CSV export, an STLINK-V3MINIE, a lux meter if you'll light-match, and a phone with 240 fps video.
17. Board B's ESP32-S3 build compiles on your machine: the same component sources compiled and passed their tests on ESPHome 2026.9.0's Linux build here, but the ESP32 toolchain couldn't be downloaded. The configuration validates for the ESP32-S3-Zero's 4 MB of flash; check the size the first build reports.
18. Board B sits at least 100 mm from Board A and the LED leads, with its antenna not behind metal.
19. No DMX input and no LED temperature sensing, per the brief.

## Sources

Links checked 29 September 2026. The LCSC and JLC part page for every LCSC number in the BOMs was checked in this phase; the numbers are in the BOM files.

- [Xicato XTM Standard Series detailed data sheet, June 2023](https://www.xicato.com/wp-content/themes/xicato/documentuploads/DS%20XTM%20Standard%20Series%20062723.pdf)
- [TI LMR38020 product page and data sheet](https://www.ti.com/product/LMR38020)
- [TI DAC80504 product page and data sheet](https://www.ti.com/product/DAC80504)
- [TI OPAx388 data sheet](https://www.ti.com/lit/ds/symlink/opa388.pdf)
- [ST STM32G431CB data sheet](https://www.st.com/resource/en/datasheet/stm32g431cb.pdf)
- [onsemi NDT3055L data sheet](https://www.onsemi.com/download/data-sheet/pdf/ndt3055l-d.pdf)
- [Nexperia 2N7002BK data sheet](https://assets.nexperia.com/documents/data-sheet/2N7002BK.pdf) and [2N7002 data sheet](https://assets.nexperia.com/documents/data-sheet/2N7002.pdf)
- [Vishay WSK2512 data sheet](https://www.vishay.com/docs/30108/wsk2512.pdf)
- [Waveshare ESP32-S3-Zero wiki](https://www.waveshare.com/wiki/ESP32-S3-Zero) (chip, regulator, antenna, row spacing)
- [Waveshare ESP32-S3-Zero product page](https://www.waveshare.com/esp32-s3-zero.htm?sku=26976) (variants: -M with headers, N8R8)
- [Community KiCad footprint for the ESP32-S3-Zero](https://github.com/jtomka/kicad-esp32-s3-zero) (pin order cross-check)
- [Espressif ESP32-S3 hardware design guidelines: PCB layout](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html)
- [Mean Well LRS-100 specification](https://www.meanwell.com/scripts/resource/pdfJS/web/viewer.html?f=LRS-100&pdf=LRS-100-spec.pdf)
- [ESPHome ESP-NOW component](https://esphome.io/components/espnow/) and [ESPNowComponent API reference](https://api-docs.esphome.io/classesphome_1_1espnow_1_1_e_s_p_now_component)
- [ESPHome source](https://github.com/esphome/esphome) (2026.9.0: the light, espnow, uart and hmac\_sha256 components the external component builds on)
- [IEEE 1789-2015, modulating current in high-brightness LEDs](https://ieeexplore.ieee.org/document/7118618)
- [JLCPCB layer stackups](https://jlcpcb.com/impedance)
- [KiCad custom design rules examples](https://forum.kicad.info/t/custom-design-rules-examples/43987) and [a JLCPCB rules file](https://gist.github.com/darkxst/f713268e5469645425eed40115fb8b49)
- [JLCKicadTools rotation table](https://github.com/matthewlai/JLCKicadTools), for the CPL converter
- [TI DAC80504RTET part details](https://www.ti.com/product/DAC80504/part-details/DAC80504RTET) (package RTE0016D)
- [ST AN2606, STM32 system memory boot mode](https://www.st.com/resource/en/application_note/an2606-introduction-to-system-memory-boot-mode-on-stm32-mcus-stmicroelectronics.pdf) and [a summary of the STM32G4 bootloader pins](https://blog.carrese.eu/articles/2026-06-17-stm32-system-bootloader-uart-dfu/)
- [Vishay WSL data sheet](https://www.vishay.com/docs/30100/wsl.pdf)
- [Samtec FTSH-107-01-L-DV-K](https://www.samtec.com/products/ftsh-107-01-l-dv-k)
- [Bourns PEC11R data sheet](https://www.bourns.com/docs/Product-Datasheets/PEC11R.pdf) and [SRR1260 data sheet](https://www.bourns.com/docs/Product-Datasheets/SRR1260.pdf)
- [JLCPCB PCB assembly price](https://jlcpcb.com/help/article/pcb-assembly-price)
- Octopart stock for [WSK2512R1000FEA](https://octopart.com/search?q=WSK2512R1000FEA), [WSL2512R1000FEA](https://octopart.com/search?q=WSL2512R1000FEA), [C3225X7S2A475K200AB](https://octopart.com/search?q=C3225X7S2A475K200AB) and [STM32G431CBU6](https://octopart.com/search?q=STM32G431CBU6)
