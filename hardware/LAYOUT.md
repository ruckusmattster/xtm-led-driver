# Layout guide

The scripts in `layout/` draw both boards in KiCad 9 by following this guide (`layout/README.md` says how to run them and what to check); the guide is also what to review their result against, or to draw a board by hand from `hardware/board_a.net` and `board_b.net`. It fixes everything that decides whether the boards work: layers, zones, loops, sense routing, widths and clearances. `board_a.kicad_dru` / `board_b.kicad_dru` hold the clearances as KiCad custom rules, with the net classes listed at the top. Coordinates are millimetres from each board's top-left corner.

## Board A: stackup and outline

JLCPCB's standard 1.6 mm four-layer stackup (7628 prepreg, about 0.2 mm from L1 to L2), ENIG. Nothing needs controlled impedance.

| Layer | Copper | Use |
| --- | --- | --- |
| L1 top | 1 oz | Every part. Signals, both switch nodes, the Kelvin pairs, local power copper, Q1's tab copper, then a GND pour |
| L2 | 0.5 oz | GND, solid. No splits, no tracks |
| L3 | 0.5 oz | Signals, then a GND pour over everything else |
| L4 bottom | 1 oz | Signals, Q1's heat spreader (CATHODE) under its tab, then a GND pour |

Routing some 200 parts on L1 and L4 alone left too many connections open, so L3 carries signals as well (an earlier version of this guide kept it for +48V and VOUT pours). Every L1 track still has the unbroken L2 plane under it, and the power paths are wide enough on L1 without the L3 pours (see the width table).

- 90.0 × 60.0 mm, 2 mm corner radius. Four non-plated M3 holes (3.2 mm, 6.5 mm keep-out on every layer) at (4, 4), (86, 4), (4, 56) and (86, 56). None connects to GND: the 48 V side stays unearthed (answer 4).
- Bottom edge: J1 (48 V in) between x = 70 and 80, J2 (LED out) between x = 36 and 48, wire entry facing off the board. J2's pin 1 is LED− (CATHODE, on the sinks' side) and pin 2 is LED+ (VOUT, on the buck's side), so neither path crosses the other. Top edge: J3 (ribbon) between x = 50 and 72. Left edge: J4 (STDC14).
- No heatsink: in the wood or plastic enclosure (your answer 4 in Phase 1) Board A cools through its own copper, 2.8 W at full, about 22 °C above the enclosure air on average (a 100 × 70 mm outline would take about 5 °C off that). Mount it on 10 mm standoffs with free air on both faces, near a vent. If it stands vertical, put the J1/J2 edge at the top so the power band's warm air doesn't rise across the precision island.
- Mount it within about 300 mm of the XTM, whose leads are 400 mm.

## Board A: floorplan

Top view, 1 character = 1 mm across, 1 line = 2 mm down:

```text
+-----------------------------------------------------------------------------------------+
| +-----------------------------------------+   +---------------------------------------+ |
| | MCU and debug                           |   | Aux rails and link                    | |
| | U1, J4 (left edge)                      |   | U3, L3, U5; J3 (top edge)             | |
| |                                         |   |                                       | |
| |                                         |   |                                       | |
| |                                         |   |                                       | |
| |                                         |   |                                       | |
| |                                         |   |                                       | |
| |                                         |   |                                       | |
| +-----------------------------------------+   |                                       | |
|   +---------------------------------------+   |                                       | |
|   | PRECISION ISLAND                      |   |                                       | |
|   | U6 DAC, U7 op-amp, dividers,          |   |                                       | |
|   | bias; U4 at the right edge;           |   +---------------------------------------+ |
|   | ground cage                           |   +---------------------+                   |
|   |                                       |   | Tracking buck       |                   |
|   |                                       |   | U2, L2,             +-----------------+ |
|   |                                       |   | C20-C30             | 48 V in         | |
|   |                                       |   |                     | J1, F1,         | |
|   +---------------------------------------+   |                     | D1, C1          | |
|   +-------------------------------+           |                     |                 | |
|   | Sinks                         |           |                     |                 | |
|   | Q1 + R102 on tab copper       +-----------+                     |                 | |
|   | Q2-Q4, R90-R101               | J2        |                     |                 | |
|   |                               | LED out   |                     |                 | |
|   |                               | + C60     |                     |                 | |
|   |                               |           |                     |                 | |
|   +-------------------------------+-----------+---------------------+-----------------+ |
|                                                                                         |
+-----------------------------------------------------------------------------------------+
```

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

## Board A: power layout

1. U2's input loop: C22 (100 nF) right at U2's VIN pin with a GND via beside its other pad; U2's own GND reaches the same L2 plane through its exposed pad's vias, so the loop closes through L2 directly under the part. C20/C21 beside it. U3 has C5 at its VIN pin and C4 beside it. (EN sits between VIN and GND on these parts; a capacitor straddling both pins would wall EN in behind the HV spacing, so EN leaves through a via and +48V comes in from C20 between C22's GND pad and that via.)
2. Both switch nodes (BUCK_SW, AUX_SW) on L1 only, as small as the current allows, with no vias: 0.5 mm past the BOOT capacitor's pad, then 1.2 mm to the inductor, about 5 mm in all. BOOT capacitors C23 and C3 straight across BOOT and SW.
3. L2 against U2's SW pin. Only plane copper under either inductor, on every layer.
4. U2's feedback network (R12–R15, C29, C30) beside its FB pin, on the side away from L2. R12 takes VOUT at the output capacitors C24–C27, not at J2.
5. U2 and U3 exposed pads: the footprint's own thermal vias (0.2 mm) to L2, L3 and L4. These, a 3 × 3 array of 0.3 mm vias under U1's exposed pad and a single one in U6's 0.8 mm pad are the only vias in any pad, all tented on L4 so solder can't run through.
6. C60 (C_a) directly across J2's pins, above the slot. J2 pin 1 sits on the CATHODE tab copper; VOUT reaches pin 2 from the output capacitors, so the loop through the LED leads closes at the board edge.
7. Q1: CATHODE copper on L1 from its tab to J2 pin 1 (x 26–41, y 44.6–59.4: 2.3 cm²), joined by 39 vias of 0.3 mm to a heat spreader on L4 (x 22–41, same rows: 2.8 cm²). The vias are densest right beside the tab, where the heat enters the copper, and three sit under Q1's body on its middle pin's strip. Q2–Q4's drains, C60 and R110 touch its top edge. The router is kept out of both areas. onsemi rates the NDT3055L at 42 °C/W on 6.5 cm² of 2 oz copper and 95 °C/W on 0.4 cm²; for these 5 cm² of 1 oz over two layers `design/calc.py` takes 50 °C/W, which puts the junction about 82 °C above the enclosure air at 1.4 A, 127 °C at 45 °C air, against a 150 °C limit. It adds about 110 pF to the cathode, well inside the 1000 pF the ripple budget allows. RT1 beside Q1.
8. R102 at least 2 mm from Q1's tab copper. Its I− pad goes to GND with four or more vias at the pad and wide L1 copper toward the buck's GND.

## Board A: sinks and the precision island

1. **Kelvin pairs.** Each channel's SNSHIx and SNSLOx start at the shunt's own sense points below and run to the island in 0.2 mm tracks, ideally together, on L1 over the L2 plane, with the same number of vias on both. The divider bottoms (R46, R48, R50, R52) and the 10 nF C44–C47 return to SNSLOx, never to the plane. The layout script gets the start points right and leaves the rest to the router, which doesn't keep the two tracks side by side; at these slow signals where they start matters far more, but redrawing each pair side by side by hand is the one refinement worth making.
   - Ch1: R102's pads 2 and 3.
   - Ch2: the ten 10 Ω resistors R90–R99 as rungs between two 1 mm bus bars, SRC2 fed at one end and GND taken out at the opposite end so every rung sees the same path. NT1 at the SRC2 bar's midpoint, NT2 at the GND bar's midpoint.
   - Ch3 and ch4: NT3/NT4 on R100's pads, NT5/NT6 on R101's.
2. **Setpoints.** Each divider pair (R45/R46 and so on) side by side in the same orientation, so both resistors sit at one temperature; C44–C47 at U7's +IN pins. Only the divider tops load DAC_OUT1–4. C40 on U6's REF pin, and nothing else on that net.
3. **Op-amp.** C52–C55 (2.2 nF) and R60–R63 (1 kΩ) at U7's −IN pins; R64–R67 (1.82 MΩ) from BIAS straight to those pins; R53, R54 and C48 (the bias source) in the middle of the island. C50/C51 on U7's V+ pin; C41, C42 and C43 on U6's VDD and VIO.
4. **Gates.** R68–R71 (220 Ω) at the FET gates, not at the op-amp, with the clamp FETs Q5–Q8 and their pull-ups R72–R75 beside them. The gate-monitor dividers R76–R83 at U7's outputs, and C56–C59 at the MCU's ADC pins.
5. **Guarding.** The island is a ground cage: L1 GND pour around and between its parts, stitching vias every 3 mm across it and along its edges, L2 solid under it, and the GND pours of L3 and L4 filling around whatever tracks pass there. Every node inside sits within 0.2 V of GND, so the pour is also an equipotential guard. No HV-class net comes within 2 mm of a precision net (a DRC rule).
6. **Leakage at the bottom of the range.** At 5 µA, 50 nA of stray current is 1%. Keep the CATHODE net compact and soldermasked, cut a 1.0 mm non-plated slot, 6 mm long, between J2's two pads so flux or dirt can't bridge them, and wash the board after assembly.
7. **Temperature sensors.** RT2 between U2 and L2, RT3 between U3 and the LDOs, RT4 between U6 and U7.

## Board A: MCU

1. 100 nF on each VDD pin (C70–C73), C74 at the 3.3 V entry, C76 on VDDA (pin 21) and C77 on VREF+ (pin 20), fed through FB1. U1's exposed pad soldered and stitched to L2.
2. SPI series resistors at the driving end: R40–R42 at U1, R43 at U6's SDO.
3. The sense dividers put their high-voltage resistor at the high-voltage end and the rest at the MCU: R17 at the output capacitors with R18/C31 at PA0; R1 at +48 V with R2/C2 at PB0; R110 at the cathode with C61 and D3 at PA1. Each long trace then carries only a few volts, filtered at the pin.
4. BUCK_DAC (PA4) runs to R15 beside U2 over the plane and away from the switch nodes; C30 filters it at the buck.
5. Link: R121–R123 at U1; R120 (BOOT0 pull-down) and C78 (NRST) at their pins.

## Track widths and clearances

IPC-2221 widths for a 10 °C rise, from `design/calc.py`, and what the layout script uses. Routed tracks take their net class's width (the router can't widen a track where there's room), so the HV class is set to what still reaches U2's and U3's 1.27 mm-pitch pins with the HV spacing; the paths drawn before routing are wider.

| Path | Current | Minimum on L1 (1 oz) | As laid out |
| --- | --- | --- | --- |
| +48V_RAW: J1 → F1 | 1.5 A | 0.53 mm | 2 mm, drawn |
| +48V: F1 → U2, U3 | 1.5 A | 0.53 mm | 0.6 mm, routed (HV class) |
| VOUT: L2 → C24–C27 → J2 pin 2 | 1.5 A | 0.53 mm | 0.6 mm, routed (HV class) |
| CATHODE: J2 pin 1 → Q1 | 1.5 A | 0.53 mm | the tab copper (a pour) |
| SRC1: Q1 → R102 | 1.5 A | 0.53 mm | 1.5 mm, drawn; R102's GND end has four vias |
| BUCK_SW | 1.5 A rms, 1.84 A peak | 0.53 mm | 0.5 mm past C23's BOOT pad, then 1.2 mm; drawn |
| SRC2 and GND bus bars | 0.16 A | — | 1 mm, drawn, for rung symmetry rather than current |
| +5V5, +5V5_LINK | 0.6 A | 0.15 mm | 0.5 mm, routed (Aux class) |
| AUX_SW | 0.6 A | 0.15 mm | 0.5 mm, then 0.8 mm; drawn |
| Signals, Kelvin pairs, +3V3, +3V3A, +5VA | < 50 mA | — | 0.2 mm, to reach the 0.5 mm-pitch QFN pins |

- Vias: 0.2 mm drill, 0.5 mm pad for signals and for each GND pad's own via to the L2 plane, placed before routing while there's still room beside every pad (JLCPCB's four-layer minimum is 0.2 mm / 0.45 mm, so this is standard pricing); 0.3 mm drill, 0.6 mm pad on the HV and Aux nets and for the stitching vias, which sit every 3 mm across the board wherever there's room.
- HV-class nets (+48V_RAW, +48V, VOUT, BUCK_SW, BUCK_BOOT, AUX_SW, AUX_BOOT, CATHODE), from IPC-2221B's Table 6-1 for 51–100 V: 0.5 mm to any other net where a bare pad is involved (A6, component terminations), 0.3 mm between copper under solder mask on L1 and L4 (B4 asks 0.13 mm), 0.3 mm on L2 and L3 (B1 asks 0.1 mm). The router keeps 0.5 mm throughout, since it can't tell a pad from a track. (An earlier version used 0.6 mm everywhere, B2's figure for bare copper conductors, which these boards don't have outside the pads; it walled U2's EN pin in.) Everything else 0.2 mm. Checked against KiCad 9's footprints, every part's own pins meet 0.5 mm: the tightest are the SOT-23 sinks Q2–Q4, 0.53 mm from the drain (CATHODE) to the gate and source pads (the rules file exempts them anyway, since a part sets its own pin spacing), then 0.645 mm from U2's and U3's lead pads to their exposed pads.
- Copper 0.5 mm from the board edge, pours 1 mm.

## Fabrication, silkscreen and cleaning

- Order: 4 layers, 1.6 mm, JLC's standard stackup, ENIG, 1 oz outer and 0.5 oz inner, tented vias, and a 0.12 mm stencil. The layouts don't reserve a spot for JLC's order number: have it removed, or let JLC place it (it's only silkscreen). The KiCad footprints split the paste on the exposed pads of U1, U2, U3 and U6 into windowpanes that keep paste off their vias.
- Silkscreen: +48V and − at J1; LED+ (red) and LED− at J2; pin-1 marks on J3, J4, U1, U6 and U7; a 48 V warning at J1; board name and revision.
- After assembly, wash the board with isopropyl alcohol and a soft brush, especially around J2, the CATHODE net, the sinks and the precision island, then dry it warm (50 °C, 30 minutes). Flux residue between a 40 V node and the cathode is the one thing that can visibly shift the bottom of the range.

## Board B

1.6 mm, two layers, 1 oz, ENIG: parts, signals and a GND pour on top, a GND pour on the bottom. 60.0 × 45.0 mm with a 2 mm corner radius; non-plated M3 holes at (4, 41) and (56, 4), with the encoder's panel nut as the third fixing.

The ESP32 is a Waveshare ESP32-S3-Zero, bought with its pin headers fitted (ESP32-S3-Zero-M), plugged into two 1×9 2.54 mm female headers 15.24 mm apart on the **bottom** of the board. It brings its own USB-C, 3.3 V regulator and BOOT/RESET buttons, and comes out of its sockets to be flashed. It hangs behind the board because the operator panel sits on the encoder, only a few millimetres above the top side, while the module on its sockets stands 12–14 mm tall: allow that much, plus a millimetre or two, behind Board B in the enclosure.

| Part | Where |
| --- | --- |
| U1 ESP32-S3-Zero on two 1×9 sockets | Bottom side, centred at (48.1, 33.0), long axis across the board: its antenna end at the right-hand edge, its USB-C end pointing into the board. Pins 1–9 (5V, GND, 3V3, IO1–IO6) along y = 25.4 from x 37.9 to 58.3; pins 10–18 (IO7–IO13, RX, TX) back along y = 40.6. No copper on either layer under the antenna end (a keep-out in the footprint); the silkscreen on the back names the module and marks both ends |
| SW3 encoder | Top-left, shaft and nut through the operator panel |
| D3–D5 with R15–R17, SW4 | Below the encoder, visible and reachable through the panel; J3 (external sync button) in the top-left corner |
| J1 ribbon with R18–R23 | Left edge, the series resistors and R22 at the connector |
| FB1, D1, C1, C3 | Between J1 and U1; C1 at U1's 5V pin, C3 at its 3V3 pin |
| R7–R14, C8–C11 | R7, R9, R11, R13 at the encoder; R8, R10, R12, R14 and C8–C11 at U1's IO4–IO7 |
| J4, TP1–TP3 | Bottom edge and bottom middle |

- Power: Board A's +5V5 through FB1 and D1 to U1's 5V pin, which is also the module's USB supply. D1 keeps USB power out of Board A; nothing keeps Board A's supply out of a computer plugged into the module, so the module is flashed out of its sockets, or with the ribbon unplugged.
- Power tracks 0.3 mm (0.5 A at most), everything else 0.2 mm.
- The two sockets must be exactly parallel: solder them with the module plugged in.
- If the enclosure is metal, the antenna end needs a plastic window or 15 mm of clearance to the metal (Espressif's figure for its modules).
- Mount Board B at least 100 mm from Board A and from the LED leads.
