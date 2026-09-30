"""Board A: 4-decade LED driver (power, tracking buck, four linear sinks, STM32G431).

Values and their reasoning: see calc.py and docs/design-record/phase2-detailed-design.md,
section "Circuit design".
Net names: +48V_RAW, +48V, +5V5, +5VA, +3V3, +3V3A, VOUT and GND are power nets;
CATHODE is the LED cathode node; SRCk/SNSHIk/SNSLOk are channel k's FET source,
Kelvin sense top and Kelvin sense bottom.
"""
from netlib import Board, NC

SHEETS = [
    ("A1", "Power entry and auxiliary rails"),
    ("A2", "Tracking buck (V_out)"),
    ("A3", "DAC, dividers and zero bias"),
    ("A4", "Sink channels 1-4"),
    ("A5", "LED output and cathode sensing"),
    ("A6", "MCU, debug, link and monitoring"),
]


def build():
    b = Board("board_a", "Board A (driver)", SHEETS)
    b.power_sources = {"+48V": "J1 via F1", "+5V5": "U3", "+5VA": "U4", "+3V3": "U5", "+3V3A": "FB1", "VOUT": "U2"}

    # ------------------------------------------------------------------ A1 power entry and rails
    s = "A1"
    b.two("J1", "MSTBA2", "+48V_RAW", "GND", s, note="Pin 1 +48 V, pin 2 return. Mark polarity on the silkscreen")
    b.two("F1", "FUSE3A", "+48V_RAW", "+48V", s)
    b.add("D1", "SMBJ58A", {"1": "+48V", "2": "GND"}, s,
          note="Surge clamp; conducts on reverse polarity so F1 or the supply's hiccup takes over")
    b.add("C1", "C_47U_100V", {"1": "+48V", "2": "GND"}, s)
    b.two("R1", "R_100K", "+48V", "V48_SENSE", s)
    b.two("R2", "R_6K2", "V48_SENSE", "GND", s)
    b.two("C2", "C_10N", "V48_SENSE", "GND", s)
    # aux buck 5.5 V, 500 kHz
    b.add("U3", "LMR38020FDDAR", {"1": "GND", "2": "AUX_EN", "3": "+48V", "4": "AUX_RT", "5": "AUX_FB",
                                  "6": NC, "7": "AUX_BOOT", "8": "AUX_SW", "9": "GND"}, s,
          note="PG unused. Exposed pad to GND with a via array")
    b.two("R3", "R_280K", "+48V", "AUX_EN", s)
    b.two("R4", "R_10K", "AUX_EN", "GND", s, note="R3/R4: starts at ~36 V")
    b.two("R5", "R_52K3", "AUX_RT", "GND", s, note="500 kHz")
    b.two("R6", "R_100K", "+5V5", "AUX_FB", s)
    b.two("R7", "R_22K1", "AUX_FB", "GND", s, note="R6/R7: 5.53 V")
    b.two("C3", "C_100N", "AUX_BOOT", "AUX_SW", s)
    b.two("L3", "SRR1260-150M", "AUX_SW", "+5V5", s)
    b.two("C4", "C_4U7_100V", "+48V", "GND", s, note="At U3 VIN/GND, shortest possible loop")
    b.two("C5", "C_100N_100V", "+48V", "GND", s)
    for ref in ("C6", "C7", "C8"):
        b.two(ref, "C_22U", "+5V5", "GND", s)
    # +5VA analog
    b.add("U4", "TPS7A2050PDBVR", {"1": "+5V5", "2": "GND", "3": "+5V5", "4": NC, "5": "+5VA"}, s)
    b.two("C9", "C_1U", "+5V5", "GND", s)
    b.two("C10", "C_4U7", "+5VA", "GND", s)
    b.two("C11", "C_100N", "+5VA", "GND", s)
    # +3V3 digital
    b.add("U5", "LDL1117S33R", {"1": "GND", "2": "+3V3", "3": "+5V5"}, s)
    b.two("C12", "C_4U7", "+5V5", "GND", s)
    b.two("C13", "C_10U", "+3V3", "GND", s)
    b.two("C14", "C_100N", "+3V3", "GND", s)
    b.two("FB1", "FB600", "+3V3", "+3V3A", s)
    b.two("C15", "C_1U", "+3V3A", "GND", s)
    b.two("C16", "C_100N", "+3V3A", "GND", s)

    # ------------------------------------------------------------------ A2 tracking buck
    s = "A2"
    b.add("U2", "LMR38020FDDAR", {"1": "GND", "2": "BUCK_EN", "3": "+48V", "4": "BUCK_RT", "5": "BUCK_FB",
                                  "6": "BUCK_PG", "7": "BUCK_BOOT", "8": "BUCK_SW", "9": "GND"}, s,
          note="Forced-PWM variant only (the F in LMR38020F). Exposed pad to GND with a via array")
    b.two("R10", "R_100K", "BUCK_EN", "GND", s, note="Holds the buck off while the MCU is in reset")
    b.two("R11", "R_64K9", "BUCK_RT", "GND", s, note="400 kHz")
    b.two("C20", "C_4U7_100V", "+48V", "GND", s)
    b.two("C21", "C_4U7_100V", "+48V", "GND", s)
    b.two("C22", "C_100N_100V", "+48V", "GND", s, note="C22 closest to U2 pins 1 and 3")
    b.two("C23", "C_100N", "BUCK_BOOT", "BUCK_SW", s)
    b.two("L2", "SRR1260-330M", "BUCK_SW", "VOUT", s)
    for ref in ("C24", "C25", "C26", "C27"):
        b.two(ref, "C_4U7_100V", "VOUT", "GND", s)
    b.two("C28", "C_100N_100V", "VOUT", "GND", s)
    b.two("R12", "R_200K", "VOUT", "BUCK_FB", s)
    b.two("C29", "C_22P_C0G", "VOUT", "BUCK_FB", s, dnp=True, note="Feed-forward cap footprint, not fitted")
    b.two("R13", "R_7K32", "BUCK_FB", "GND", s)
    b.two("R14", "R_8K25", "BUCK_FB", "INJ_MID", s)
    b.two("R15", "R_8K25", "INJ_MID", "BUCK_DAC", s)
    b.two("C30", "C_47N", "INJ_MID", "GND", s,
          note="R12-R15, C30: V_out = 40.44 - 12.12 x V_dac; 38.0 V at 0.2 V, 3.5 V floor at 3.05 V")
    b.two("R16", "R_100K", "BUCK_PG", "+3V3", s)
    b.add("D2", "SMBJ43A", {"1": "VOUT", "2": "GND"}, s)
    b.two("R17", "R_1M", "VOUT", "VOUT_SENSE", s)
    b.two("R18", "R_82K", "VOUT_SENSE", "GND", s)
    b.two("C31", "C_10N", "VOUT_SENSE", "GND", s)

    # ------------------------------------------------------------------ A3 DAC, dividers, bias
    s = "A3"
    b.add("U6", "DAC80504RTET", {"1": "DAC_REF", "2": "DAC_OUT1", "3": "DAC_OUT2", "4": "DAC_OUT3", "5": "DAC_OUT4",
                                 "6": "GND", "7": "+5VA", "8": "+3V3", "9": "GND", "10": "+3V3", "11": "DAC_LDAC",
                                 "12": "DAC_CS", "13": "DAC_SCLK", "14": "DAC_SDI", "15": "DAC_SDO", "16": "+3V3",
                                 "17": "GND"}, s,
          note="REFDIV and GAIN to VIO: the 2.5 V internal reference divided to 1.25 V, gain 2, so 0-2.5 V "
               "full scale with VREF/DIV well under VDD/2 (undivided, 2.5 V sits at the VDD/2 limit on a 5 V "
               "supply and the DAC shuts its outputs off). RSTSEL low: resets to zero scale")
    b.two("C40", "C_220N", "DAC_REF", "GND", s, note="Nothing else may load REF")
    b.two("C41", "C_100N", "+5VA", "GND", s)
    b.two("C42", "C_1U", "+5VA", "GND", s)
    b.two("C43", "C_100N", "+3V3", "GND", s)
    b.two("R40", "R_22", "MCU_DAC_CS", "DAC_CS", s)
    b.two("R41", "R_22", "MCU_SCLK", "DAC_SCLK", s)
    b.two("R42", "R_22", "MCU_MOSI", "DAC_SDI", s)
    b.two("R43", "R_22", "DAC_SDO", "MCU_MISO", s)
    b.two("R44", "R_10K", "DAC_LDAC", "+3V3", s, note="Updates are triggered in software (TRIGGER register)")
    for k, (rt, rb, cd) in enumerate((("R45", "R46", "C44"), ("R47", "R48", "C45"),
                                      ("R49", "R50", "C46"), ("R51", "R52", "C47")), start=1):
        b.two(rt, "RT_12K", f"DAC_OUT{k}", f"SET{k}", s)
        b.two(rb, "RT_1K", f"SET{k}", f"SNSLO{k}", s,
              note=f"Returns to channel {k}'s Kelvin sense bottom, not to the plane" if k == 1 else "")
        b.two(cd, "C_10N_C0G", f"SET{k}", f"SNSLO{k}", s)
    b.two("R53", "R_10K", "+5VA", "BIAS", s)
    b.two("R54", "R_1K", "BIAS", "GND", s)
    b.two("C48", "C_1U", "BIAS", "GND", s, note="R53/R54: 0.455 V bias source for the four 1.82 M zero-bias resistors")

    # ------------------------------------------------------------------ A4 sink channels
    s = "A4"
    b.add("U7", "OPA4388IPWR", {"1": "GDRV1", "2": "NINV1", "3": "SET1", "4": "+5VA", "5": "SET2", "6": "NINV2",
                                "7": "GDRV2", "8": "GDRV3", "9": "NINV3", "10": "SET3", "11": "GND",
                                "12": "SET4", "13": "NINV4", "14": "GDRV4"}, s)
    b.two("C50", "C_100N", "+5VA", "GND", s)
    b.two("C51", "C_1U", "+5VA", "GND", s)
    fets = {1: ("Q1", "NDT3055L"), 2: ("Q2", "2N7002BK"), 3: ("Q3", "2N7002"), 4: ("Q4", "2N7002")}
    clamp_pin = {1: "CLAMP1", 2: "CLAMP2", 3: "CLAMP3", 4: "CLAMP4"}
    for k in (1, 2, 3, 4):
        n = 60 + (k - 1)
        b.two(f"R{n}", "R_1K", f"SNSHI{k}", f"NINV{k}", s)                        # R60-R63  R_IN
        b.two(f"C{52 + k - 1}", "C_2N2_C0G", f"GDRV{k}", f"NINV{k}", s)             # C52-C55  C_C
        b.two(f"R{64 + k - 1}", "R_1M82", "BIAS", f"NINV{k}", s)                    # R64-R67  zero bias
        b.two(f"R{68 + k - 1}", "R_220", f"GDRV{k}", f"GATE{k}", s)                 # R68-R71  R_G
        qref, qkey = fets[k]
        if qkey == "NDT3055L":
            b.add(qref, qkey, {"1": f"GATE{k}", "2": "CATHODE", "3": f"SRC{k}"}, s)
        else:
            b.add(qref, qkey, {"1": f"GATE{k}", "2": f"SRC{k}", "3": "CATHODE"}, s)
        b.add(f"Q{4 + k}", "2N7002BK", {"1": clamp_pin[k], "2": "GND", "3": f"GATE{k}"}, s)   # Q5-Q8 clamps
        b.two(f"R{72 + k - 1}", "R_100K", clamp_pin[k], "+3V3", s)                  # R72-R75 clamp on in reset
        b.two(f"R{76 + 2 * (k - 1)}", "R_100K", f"GDRV{k}", f"GMON{k}", s)         # R76,78,80,82
        b.two(f"R{77 + 2 * (k - 1)}", "R_100K", f"GMON{k}", "GND", s)              # R77,79,81,83
        b.two(f"C{56 + k - 1}", "C_1N_C0G", f"GMON{k}", "GND", s)                   # C56-C59
    # shunts
    b.add("R102", "WSK2512_0R1", {"1": "SRC1", "2": "SNSHI1", "3": "SNSLO1", "4": "GND"}, s,
          note="Pads 1/4 carry current, 2/3 are the Kelvin sense pads")
    for i in range(10):
        b.two(f"R{90 + i}", "RT_10R", "SRC2", "GND", s)
    b.two("NT1", "NETTIE", "SRC2", "SNSHI2", s, note="Mid-point of the SRC2 bus bar of R90-R99")
    b.two("NT2", "NETTIE", "GND", "SNSLO2", s, note="Mid-point of the ground bus bar of R90-R99")
    b.two("R100", "RT_10R", "SRC3", "GND", s)
    b.two("NT3", "NETTIE", "SRC3", "SNSHI3", s, note="At R100's pad")
    b.two("NT4", "NETTIE", "GND", "SNSLO3", s, note="At R100's pad")
    b.two("R101", "RT_100R", "SRC4", "GND", s)
    b.two("NT5", "NETTIE", "SRC4", "SNSHI4", s, note="At R101's pad")
    b.two("NT6", "NETTIE", "GND", "SNSLO4", s, note="At R101's pad")

    # ------------------------------------------------------------------ A5 LED output and cathode
    s = "A5"
    b.two("J2", "MSTBA2", "CATHODE", "VOUT", s,
          note="Pin 1 LED- (toward the sinks), pin 2 LED+ (red lead, toward the buck); a 1 mm slot between the pads")
    b.two("C60", "C_22N_100V", "VOUT", "CATHODE", s, note="C_a: directly across J2's pins")
    b.two("R110", "R_1M", "CATHODE", "CATH_TAP", s)
    b.two("C61", "C_1N_C0G", "CATH_TAP", "GND", s)
    b.add("D3", "BAV199", {"1": "GND", "2": "+3V3", "3": "CATH_TAP"}, s)

    # ------------------------------------------------------------------ A6 MCU, debug, link, monitoring
    s = "A6"
    b.add("U1", "STM32G431CBU6", {
        "1": "+3V3", "2": "BUCK_EN", "3": NC, "4": NC, "5": NC, "6": NC, "7": "NRST",
        "8": "VOUT_SENSE", "9": "CATH_TAP", "10": "VCP_TX", "11": "VCP_RX", "12": "BUCK_DAC", "13": "SPARE_PA5",
        "14": "GMON1", "15": "GMON2", "16": "BUCK_PG", "17": "V48_SENSE", "18": "NTC1", "19": "GMON3",
        "20": "+3V3A", "21": "+3V3A", "22": NC, "23": "+3V3", "24": "NTC2", "25": "NTC3", "26": NC,
        "27": "NTC4", "28": "GMON4", "29": "CLAMP1", "30": "CLAMP2", "31": "LINK_TX", "32": "LINK_RX",
        "33": "A_OK_MCU", "34": "LED_STAT", "35": "+3V3", "36": "SWDIO", "37": "SWCLK", "38": "MCU_DAC_CS",
        "39": "CLAMP3", "40": NC, "41": "MCU_SCLK", "42": "MCU_MISO", "43": "MCU_MOSI", "44": NC, "45": "CLAMP4",
        "46": "BOOT0", "47": NC, "48": "+3V3", "49": "GND"}, s,
        note="Exposed pad is VSS: solder it and stitch it to GND. PB6 and PB4 carry the UCPD dead-battery pull-downs "
             "until firmware disables them, so no clamp sits on PB6. BUCK_EN is on PC13 because the ROM bootloader "
             "drives PB9 (its FDCAN1_TX) high; PC13 has no bootloader function, so R10 holds the buck off")
    for ref in ("C70", "C71", "C72", "C73"):
        b.two(ref, "C_100N", "+3V3", "GND", s)
    b.two("C74", "C_4U7", "+3V3", "GND", s)
    b.two("C75", "C_1U", "+3V3A", "GND", s)
    b.two("C76", "C_100N", "+3V3A", "GND", s)
    b.two("C77", "C_100N", "+3V3A", "GND", s, note="C77 at VREF+ (pin 20), C76 at VDDA (pin 21)")
    b.two("C78", "C_100N", "NRST", "GND", s)
    b.two("R120", "R_10K", "BOOT0", "GND", s)
    b.add("J4", "STDC14", {"1": NC, "2": NC, "3": "+3V3", "4": "SWDIO", "5": "GND", "6": "SWCLK", "7": "GND",
                           "8": NC, "9": NC, "10": NC, "11": "GND", "12": "NRST", "13": "VCP_RX", "14": "VCP_TX"}, s,
          note="STLINK-V3MINIE: pin 13 drives the target RX (PA3), pin 14 receives the target TX (PA2). "
               "Pin 8 (SWO) stays open because PB3 is SPI1_SCK")
    b.add("J3", "IDC2x5", {"1": "+5V5_LINK", "2": "GND", "3": "+5V5_LINK", "4": "GND", "5": "TXD_A", "6": "GND",
                           "7": "RXD_A", "8": "BOOT0", "9": "A_OK", "10": "NRST"}, s,
          note="Place next to the aux buck so Board B's return current never crosses the precision section")
    b.two("FB2", "FB600_2A", "+5V5", "+5V5_LINK", s)
    b.two("C79", "C_10U", "+5V5_LINK", "GND", s)
    b.two("R121", "R_100", "LINK_TX", "TXD_A", s)
    b.two("R122", "R_100", "RXD_A", "LINK_RX", s)
    b.two("R123", "R_100K", "LINK_RX", "+3V3", s)
    b.two("R124", "R_100", "A_OK_MCU", "A_OK", s)
    b.two("R125", "R_1K", "LED_STAT", "LED_STAT_A", s)
    b.add("D4", "LED_G", {"1": "GND", "2": "LED_STAT_A"}, s)
    ntc_notes = {1: "at the ch1 FET (Q1) tab copper", 2: "between U2 and L2", 3: "between U3 and the LDOs",
                 4: "in the precision section, between U6 and U7"}
    for k in (1, 2, 3, 4):
        b.two(f"RT{k}", "NTC10K", f"NTC{k}", "GND", s, note=f"NTC{k} {ntc_notes[k]}")
        b.two(f"R{126 + k - 1}", "R_10K", "+3V3A", f"NTC{k}", s)
        b.two(f"C{80 + k - 1}", "C_10N", f"NTC{k}", "GND", s)
    # test points
    tps = [("TP1", "+48V"), ("TP2", "+5V5"), ("TP3", "+5VA"), ("TP4", "+3V3"), ("TP5", "VOUT"), ("TP6", "CATH_TAP"),
           ("TP7", "BIAS"), ("TP8", "GND"), ("TP9", "GND"), ("TP10", "BUCK_DAC"), ("TP11", "SPARE_PA5")]
    for k in (1, 2, 3, 4):
        tps += [(f"TP{11 + 2 * k - 1}", f"SET{k}"), (f"TP{11 + 2 * k}", f"SNSHI{k}")]
    for ref, net in tps:
        b.add(ref, "TP", {"1": net}, s)
    b.single_ok.update({"SPARE_PA5"})
    for i in range(1, 5):
        b.add(f"H{i}", "MH", {}, s)
    b.extras.append(("J1 J2 plugs (off-board)", "MSTB_PLUG", 2))
    for i in range(1, 4):
        b.add(f"FID{i}", "FID", {}, s)
    return b


if __name__ == "__main__":
    brd = build()
    e, w = brd.erc()
    print(f"{len(brd.parts)} parts, {len(brd.nets())} nets, {len(e)} errors, {len(w)} warnings")
    for x in e + w:
        print(" ", x)
