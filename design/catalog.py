"""Part catalog: one entry per orderable part, shared by both boards.

status values:
  "verified <where>"   part number checked against the distributor page named
  "to verify"          believed correct but not yet checked; build.py prints these
  "describe"           no part number given on purpose; search by the description

Footprint names follow the KiCad 8-10 standard libraries unless prefixed PCM_Espressif
(install "Espressif KiCad library" from KiCad's Plugin and Content Manager). KiCad 7 lacks the
DAC's Texas_RTE0016D footprint.
"""

R0603 = "Resistor_SMD:R_0603_1608Metric"
R0805 = "Resistor_SMD:R_0805_2012Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
SOT23 = "Package_TO_SOT_SMD:SOT-23"


def res(value, lcsc="", mpn="", mfr="UNI-ROYAL", status="describe", jlc="Basic", fp=R0603, desc=None, **kw):
    d = dict(value=value, footprint=fp, symbol="Device:R", kind="R", lcsc=lcsc, mpn=mpn, manufacturer=mfr,
             jlc=jlc, status=status, desc=desc or f"Resistor {value} 1% 0603 thick film")
    d.update(kw)
    return d


def cap(value, desc, lcsc="", mpn="", mfr="", status="to verify", jlc="Basic", fp=C0603, **kw):
    d = dict(value=value, footprint=fp, symbol="Device:C", kind="C", lcsc=lcsc, mpn=mpn, manufacturer=mfr,
             jlc=jlc, status=status, desc=desc)
    d.update(kw)
    return d


STM32_PINS = {
    "1": "VBAT", "2": "PC13", "3": "PC14", "4": "PC15", "5": "PF0", "6": "PF1", "7": "PG10-NRST", "8": "PA0",
    "9": "PA1", "10": "PA2", "11": "PA3", "12": "PA4", "13": "PA5", "14": "PA6", "15": "PA7", "16": "PC4",
    "17": "PB0", "18": "PB1", "19": "PB2", "20": "VREF+", "21": "VDDA", "22": "PB10", "23": "VDD", "24": "PB11",
    "25": "PB12", "26": "PB13", "27": "PB14", "28": "PB15", "29": "PC6", "30": "PA8", "31": "PA9", "32": "PA10",
    "33": "PA11", "34": "PA12", "35": "VDD", "36": "PA13", "37": "PA14", "38": "PA15", "39": "PC10", "40": "PC11",
    "41": "PB3", "42": "PB4", "43": "PB5", "44": "PB6", "45": "PB7", "46": "PB8-BOOT0", "47": "PB9", "48": "VDD",
    "49": "VSS",
}

ESP32S3_PINS = {
    "1": "GND", "2": "3V3", "3": "EN", "4": "IO4", "5": "IO5", "6": "IO6", "7": "IO7", "8": "IO15", "9": "IO16",
    "10": "IO17", "11": "IO18", "12": "IO8", "13": "IO19/USB_D-", "14": "IO20/USB_D+", "15": "IO3", "16": "IO46",
    "17": "IO9", "18": "IO10", "19": "IO11", "20": "IO12", "21": "IO13", "22": "IO14", "23": "IO21", "24": "IO47",
    "25": "IO48", "26": "IO45", "27": "IO0", "28": "IO35", "29": "IO36", "30": "IO37", "31": "IO38", "32": "IO39",
    "33": "IO40", "34": "IO41", "35": "IO42", "36": "RXD0/IO44", "37": "TXD0/IO43", "38": "IO2", "39": "IO1",
    "40": "GND", "41": "GND_EP",
}

# Waveshare ESP32-S3-Zero, top view, USB-C end up: left column 1-9 from the USB end, right column
# 10-18 from the antenna end (pin 18 is top right). GPIO14-18, 21, 38-42 and 45-48 sit on pads
# underneath and are out of reach of a socket.
ZERO_PINS = {
    "1": "5V", "2": "GND", "3": "3V3", "4": "GP1", "5": "GP2", "6": "GP3", "7": "GP4", "8": "GP5", "9": "GP6",
    "10": "GP7", "11": "GP8", "12": "GP9", "13": "GP10", "14": "GP11", "15": "GP12", "16": "GP13",
    "17": "RX/GP44", "18": "TX/GP43",
}

CATALOG = {
    # ------------------------------------------------------------------ ICs
    "STM32G431CBU6": dict(value="STM32G431CBU6", footprint="Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm",
                          symbol="MCU_ST_STM32G4:STM32G431CBUx", kind="IC", mpn="STM32G431CBU6",
                          manufacturer="STMicroelectronics", lcsc="C529356", jlc="Extended",
                          status="verified LCSC (Phase 2)",
                          desc="Cortex-M4F MCU, 128 KB flash, UFQFPN48", pins=STM32_PINS,
                          note="LCSC had 61 and JLC none on 29 Sep 2026: order early (Avnet, Arrow and Newark stock it too)"),
    "LMR38020FDDAR": dict(value="LMR38020FDDAR", footprint="Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm_ThermalVias",
                          symbol="Regulator_Switching:LMR33630ADDA", kind="IC", mpn="LMR38020FDDAR",
                          manufacturer="Texas Instruments", lcsc="C5149193", jlc="Extended",
                          status="verified LCSC (Phase 2)", desc="80 V 2 A sync buck, forced PWM, HSOIC-8 PowerPAD",
                          pins={"1": "GND", "2": "EN", "3": "VIN", "4": "RT/SYNC", "5": "FB", "6": "PG",
                                "7": "BOOT", "8": "SW", "9": "EP"},
                          note="Check the footprint's exposed pad against the datasheet's DDA0008B land pattern"),
    "TPS7A2050PDBVR": dict(value="TPS7A2050PDBVR", footprint="Package_TO_SOT_SMD:SOT-23-5",
                           symbol="Regulator_Linear:TPS7A2033PDBV", kind="IC", mpn="TPS7A2050PDBVR",
                           manufacturer="Texas Instruments", lcsc="C2864504", jlc="Extended",
                           status="verified LCSC (Phase 2); pinout from TI datasheet", desc="5.0 V 300 mA low-noise LDO",
                           pins={"1": "IN", "2": "GND", "3": "EN", "4": "NC", "5": "OUT"},
                           note="Out of stock at LCSC on 29 Sep 2026; Digi-Key and Mouser stock it"),
    "LDL1117S33R": dict(value="LDL1117S33R", footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
                        symbol="Regulator_Linear:LDL1117S33R", kind="IC", mpn="LDL1117S33R",
                        manufacturer="STMicroelectronics", lcsc="C435835", jlc="Extended",
                        status="verified LCSC (Phase 2); pinout from ST datasheet", desc="3.3 V 1.2 A LDO",
                        pins={"1": "GND", "2": "VOUT", "3": "VIN"}),
    "DAC80504RTET": dict(value="DAC80504RTET", footprint="Package_DFN_QFN:Texas_RTE0016D_WQFN-16-1EP_3x3mm_P0.5mm_EP0.8x0.8mm",
                         symbol="Analog_DAC:DAC80504", kind="IC", mpn="DAC80504RTET", manufacturer="Texas Instruments",
                         jlc="", place="stencil", status="verified TI and Digi-Key product pages",
                         digikey="product page 9692594", desc="Quad 16-bit DAC, 2.5 V internal reference, WQFN-16 (RTE0016D, 0.8 mm exposed pad)",
                         pins={"1": "REF", "2": "OUT0", "3": "OUT1", "4": "OUT2", "5": "OUT3", "6": "GND",
                               "7": "VDD", "8": "GAIN", "9": "RSTSEL", "10": "REFDIV", "11": "LDAC", "12": "CS",
                               "13": "SCLK", "14": "SDI", "15": "SDO", "16": "VIO", "17": "EP"},
                         note="RTET is the 250-piece reel; RTER the 3000-piece reel. Same part. TI lists it in RTE0016D, whose "
                              "exposed pad is 0.8 mm (dac80504.pdf p. 47; KiCad's Texas_RTE0016D footprint), not the "
                              "1.68 mm RTE0016C pad"),
    "OPA4388IPWR": dict(value="OPA4388IPWR", footprint="Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
                        symbol="Amplifier_Operational:OPA4388", kind="IC", mpn="OPA4388IPWR",
                        manufacturer="Texas Instruments", jlc="", status="verified TI and Digi-Key product pages",
                        digikey="product page 10434812", desc="Quad zero-drift RRIO op-amp, 10 MHz, TSSOP-14",
                        pins={"1": "OUTA", "2": "-INA", "3": "+INA", "4": "V+", "5": "+INB", "6": "-INB", "7": "OUTB",
                              "8": "OUTC", "9": "-INC", "10": "+INC", "11": "V-", "12": "+IND", "13": "-IND", "14": "OUTD"}),
    "USBLC6-2SC6": dict(value="USBLC6-2SC6", footprint="Package_TO_SOT_SMD:SOT-23-6", symbol="Power_Protection:USBLC6-2SC6",
                        kind="IC", mpn="USBLC6-2SC6", manufacturer="STMicroelectronics", lcsc="C7519", jlc="Extended",
                        status="verified LCSC (Phase 2)", desc="USB ESD array",
                        pins={"1": "I/O1", "2": "GND", "3": "I/O2", "4": "I/O2", "5": "VBUS", "6": "I/O1"}),
    "ESP32-S3-WROOM-1-N8": dict(value="ESP32-S3-WROOM-1-N8", footprint="PCM_Espressif:ESP32-S3-WROOM-1",
                                symbol="PCM_Espressif:ESP32-S3-WROOM-1", kind="IC", mpn="ESP32-S3-WROOM-1-N8",
                                manufacturer="Espressif", lcsc="C2913198", jlc="Extended",
                                status="verified LCSC (Phase 2)", desc="ESP32-S3 module, 8 MB flash, no PSRAM, PCB antenna",
                                pins=ESP32S3_PINS),
    "ESP32-S3-ZERO": dict(value="ESP32-S3-Zero-M", footprint="XTM:ESP32-S3-Zero_Socket", symbol="XTM:ESP32-S3-Zero",
                          kind="IC", mpn="ESP32-S3-Zero-M", manufacturer="Waveshare", jlc="",
                          place="hand: plugs into the two 1x9 sockets on the bottom",
                          status="verified waveshare.com product page (SKU 25081 without header; -M = header fitted)",
                          desc="Waveshare ESP32-S3-Zero with pre-soldered pin headers: ESP32-S3FH4R2 (4 MB flash, "
                               "2 MB PSRAM), USB-C, 3.3 V LDO (ME6217C33, 800 mA), BOOT and RESET buttons, ceramic "
                               "antenna, 23.5 x 18 mm",
                          pins=ZERO_PINS,
                          note="Pin order from Waveshare's top-view photo and the community KiCad footprint "
                               "(github.com/jtomka/kicad-esp32-s3-zero). Its 5V pin is its USB VBUS: never plug USB "
                               "into it while the ribbon from Board A is connected (flash it off the board)"),
    # ------------------------------------------------------------------ discretes
    "NDT3055L": dict(value="NDT3055L", footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2", symbol="Transistor_FET:Q_NMOS_GDS",
                     kind="Q", mpn="NDT3055L", manufacturer="onsemi", lcsc="C274612", jlc="Extended",
                     status="verified LCSC (Phase 2)", desc="60 V logic-level N-MOSFET, SOT-223",
                     pins={"1": "G", "2": "D", "3": "S"}),
    "2N7002BK": dict(value="2N7002BK", footprint=SOT23, symbol="Transistor_FET:2N7002", kind="Q", mpn="2N7002BK,215",
                     manufacturer="Nexperia", lcsc="C282405", jlc="Extended", status="verified LCSC (Phase 2)",
                     desc="60 V N-MOSFET, 2 ohm, SOT-23", pins={"1": "G", "2": "S", "3": "D"}),
    "2N7002": dict(value="2N7002", footprint=SOT23, symbol="Transistor_FET:2N7002", kind="Q", mpn="2N7002,215",
                   manufacturer="Nexperia", lcsc="C65189", jlc="Extended", status="verified LCSC C65189 = Nexperia 2N7002,215",
                   desc="60 V N-MOSFET, SOT-23 (Nexperia 2N7002,215 specifically: gate leakage <=100 nA)",
                   pins={"1": "G", "2": "S", "3": "D"}),
    "BAV199": dict(value="BAV199", footprint=SOT23, symbol="Diode:BAV199", kind="D", mpn="BAV199,215",
                   manufacturer="Nexperia", lcsc="C40919", jlc="Extended", status="verified LCSC C40919 = BAV199,215",
                   desc="Low-leakage series diode pair, SOT-23", pins={"1": "A1", "2": "K2", "3": "K1/A2"}),
    "SMBJ58A": dict(value="SMBJ58A", footprint="Diode_SMD:D_SMB", symbol="Diode:SMBJ58A", kind="D", mpn="SMBJ58A",
                    manufacturer="Littelfuse", lcsc="C157526", jlc="Extended", status="verified LCSC (Phase 2)",
                    desc="600 W TVS, 58 V standoff, unidirectional", pins={"1": "K", "2": "A"}),
    "SMBJ43A": dict(value="SMBJ43A", footprint="Diode_SMD:D_SMB", symbol="Diode:SMBJ43A", kind="D", mpn="SMBJ43A",
                    manufacturer="Littelfuse", lcsc="C315993", jlc="Extended", status="verified LCSC (Phase 2)",
                    desc="600 W TVS, 43 V standoff, unidirectional", pins={"1": "K", "2": "A"}),
    "B5819W": dict(value="B5819W", footprint="Diode_SMD:D_SOD-123", symbol="Diode:B5819W", kind="D", mpn="B5819W SL",
                   manufacturer="JSCJ", lcsc="C8598", jlc="Basic", status="verified LCSC C8598 = JSCJ B5819W SL", desc="40 V 1 A Schottky, SOD-123",
                   pins={"1": "K", "2": "A"}),
    "LED_G": dict(value="green", footprint="LED_SMD:LED_0603_1608Metric", symbol="Device:LED", kind="LED",
                  mpn="KT-0603G", manufacturer="Hubei KENTO", lcsc="C12624", jlc="Extended",
                  status="verified LCSC C12624", desc="Green LED 0603, Vf ~3.1 V", pins={"1": "K", "2": "A"}),
    "LED_R": dict(value="red", footprint="LED_SMD:LED_0603_1608Metric", symbol="Device:LED", kind="LED",
                  mpn="KT-0603R", manufacturer="Hubei KENTO", lcsc="C2286", jlc="Basic",
                  status="verified LCSC C2286", desc="Red LED 0603, Vf ~2 V", pins={"1": "K", "2": "A"}),
    "LED_B": dict(value="blue", footprint="LED_SMD:LED_0603_1608Metric", symbol="Device:LED", kind="LED",
                  mpn="KT-0603B", manufacturer="Hubei KENTO", lcsc="C2288", jlc="Extended",
                  status="verified LCSC C2288", desc="Blue LED 0603, Vf ~3.1 V", pins={"1": "K", "2": "A"}),
    "NTC10K": dict(value="10k NTC", footprint=R0603, symbol="Device:Thermistor_NTC", kind="R", mpn="NCP18XH103F03RB",
                   manufacturer="Murata", lcsc="C13564", jlc="Extended", status="verified LCSC C13564",
                   desc="NTC 10 k 1% B25/50 3380 K, 0603"),
    # ------------------------------------------------------------------ magnetics
    "SRR1260-330M": dict(value="33uH", footprint="Inductor_SMD:L_Bourns_SRR1260", symbol="Device:L", kind="L",
                         mpn="SRR1260-330M", manufacturer="Bourns", lcsc="C840528", jlc="Extended",
                         status="verified LCSC (Phase 2)", desc="33 uH shielded power inductor, Irms 3.0 A, Isat 2.8 A typ",
                         note="Isat is below the LMR38020's 3.2 A typical current limit: fine at the 1.84 A peak in "
                              "use; only a hard short of V_out to ground drives it into partial saturation"),
    "SRR1260-150M": dict(value="15uH", footprint="Inductor_SMD:L_Bourns_SRR1260", symbol="Device:L", kind="L",
                         mpn="SRR1260-150M", manufacturer="Bourns", lcsc="C2041333", jlc="Extended",
                         status="verified LCSC (Phase 2)", desc="15 uH shielded power inductor, Irms 5.0 A, Isat 4.6 A typ"),
    "FB600": dict(value="600R@100MHz", footprint="Inductor_SMD:L_0805_2012Metric", symbol="Device:FerriteBead", kind="FB",
                  mpn="GZ2012D601TF", manufacturer="Sunlord", lcsc="C1017", jlc="Basic", status="verified JLC C1017 (Basic)",
                  desc="Ferrite bead 600 ohm at 100 MHz, 0805, 500 mA, 0.3 ohm (VDDA only)"),
    "FB600_2A": dict(value="600R@100MHz 2A", footprint="Inductor_SMD:L_0805_2012Metric", symbol="Device:FerriteBead", kind="FB",
                     mpn="UPZ2012E601-2R0TF", manufacturer="Sunlord", lcsc="C98308", jlc="Extended",
                     status="verified JLC C98308", desc="Ferrite bead 600 ohm at 100 MHz, 0805, 2 A, 90 mohm"),
    # ------------------------------------------------------------------ precision passives
    "WSK2512_0R1": dict(value="0.1R 4T", footprint="Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm",
                        symbol="Device:R_Shunt", kind="R", mpn="WSK2512R1000FEA", manufacturer="Vishay Dale",
                        jlc="", status="verified Vishay WSK2512 datasheet; no distributor stock found 29 Sep 2026 (Octopart)",
                        desc="0.1 ohm 1% four-terminal metal strip, +-35 ppm/C, 1 W, 2512", spares=2,
                        note="Check Vishay's lead time before ordering. In-stock fallback on the same pads: Vishay "
                             "WSL2512R1000FEA (two-terminal, +-75 ppm/C; each end soldered across its current and "
                             "sense pads), which widens range 1's budget to +-0.17 % RSS",
                        pins={"1": "I+", "2": "S+", "3": "S-", "4": "I-"}),
    "RT_12K": dict(value="12.0k 0.1%", footprint=R0805, symbol="Device:R", kind="R", mpn="RT0805BRD0712KL", manufacturer="YAGEO",
                   jlc="", status="verified YAGEO spec sheet; Newark, Arrow, TME stock it (29 Sep 2026)",
                   desc="12.0 k 0.1% 25 ppm/C thin film 0805", note="No LCSC listing, so JLC can't place it"),
    "RT_1K": dict(value="1.00k 0.1%", footprint=R0805, symbol="Device:R", kind="R", mpn="RT0805BRD071KL", manufacturer="YAGEO",
                  jlc="Extended", lcsc="C110774", status="verified exists (LCSC C110774, RS)", desc="1.00 k 0.1% 25 ppm/C thin film 0805"),
    "RT_10R": dict(value="10R 0.1%", footprint=R0805, symbol="Device:R", kind="R", mpn="RT0805BRD0710RL", manufacturer="YAGEO",
                   jlc="", status="verified YAGEO spec sheet; Newark, Arrow, TME stock it (29 Sep 2026)",
                   desc="10 ohm 0.1% 25 ppm/C thin film 0805", note="No LCSC listing, so JLC can't place it"),
    "RT_100R": dict(value="100R 0.1%", footprint=R0805, symbol="Device:R", kind="R", mpn="RT0805BRD07100RL", manufacturer="YAGEO",
                    jlc="", status="verified YAGEO spec sheet; Newark, Arrow, TME stock it (29 Sep 2026)",
                    desc="100 ohm 0.1% 25 ppm/C thin film 0805", note="No LCSC listing, so JLC can't place it"),
    # ------------------------------------------------------------------ resistors, 0603 1 %
    "R_22": res("22R", lcsc="C23345", mpn="0603WAF220JT5E", status="verified LCSC C23345"), "R_100": res("100R", lcsc="C22775", mpn="0603WAF1000T5E", status="verified LCSC C22775"), "R_220": res("220R", lcsc="C22962", mpn="0603WAF2200T5E", status="verified LCSC C22962"), "R_470": res("470R"),
    "R_1K": res("1k", lcsc="C21190", mpn="0603WAF1001T5E", status="verified LCSC C21190"), "R_5K1": res("5.1k", lcsc="C23186", mpn="0603WAF5101T5E", status="verified LCSC C23186"), "R_6K2": res("6.2k"), "R_7K32": res("7.32k", jlc="Extended"),
    "R_8K25": res("8.25k", jlc="Extended"), "R_10K": res("10k", lcsc="C25804", mpn="0603WAF1002T5E", status="verified LCSC C25804"), "R_22K1": res("22.1k", jlc="Extended"),
    "R_52K3": res("52.3k", jlc="Extended"), "R_64K9": res("64.9k", jlc="Extended"), "R_82K": res("82k"),
    "R_100K": res("100k", lcsc="C25803", mpn="0603WAF1003T5E", status="verified LCSC C25803"), "R_200K": res("200k"), "R_280K": res("280k", jlc="Extended"), "R_1M": res("1M", lcsc="C22935", mpn="0603WAF1004T5E", status="verified LCSC C22935"),
    "R_1M82": res("1.82M", jlc="Extended"),
    # ------------------------------------------------------------------ capacitors
    "C_100N": cap("100nF", "100 nF 50 V X7R 0603", lcsc="C14663", mpn="CC0603KRX7R9BB104", mfr="YAGEO",
                  status="verified LCSC (this session)"),
    "C_100N_100V": cap("100nF 100V", "100 nF 100 V X7R 0603", status="describe"),
    "C_1U": cap("1uF", "1 uF 25 V X5R or X7R 0603", status="describe"),
    "C_220N": cap("220nF", "220 nF 25 V X7R 0603", lcsc="C21120", mpn="CL10B224KA8NNNC", mfr="Samsung", status="verified LCSC C21120"),
    "C_47N": cap("47nF", "47 nF 50 V X7R 0603", lcsc="C1622", mpn="CL10B473KB8NNNC", mfr="Samsung", status="verified LCSC C1622"),
    "C_10N": cap("10nF", "10 nF 50 V X7R 0603", status="describe"),
    "C_10N_C0G": cap("10nF C0G", "10 nF 50 V C0G/NP0 0805", fp=C0805, jlc="Extended", status="describe"),
    "C_2N2_C0G": cap("2.2nF C0G", "2.2 nF 50 V C0G/NP0 0603", jlc="Extended", status="describe"),
    "C_1N_C0G": cap("1nF C0G", "1 nF 50 V C0G/NP0 0603", status="describe", note="C0G, not X7R"),
    "C_22P_C0G": cap("22pF C0G", "22 pF 50 V C0G/NP0 0603", lcsc="C1653", mpn="CL10C220JB8NNNC", mfr="Samsung", status="verified LCSC C1653"),
    "C_4U7": cap("4.7uF", "4.7 uF 25 V X5R/X7R 0805", fp=C0805, lcsc="C1779", mpn="CL21A475KAQNNNE", mfr="Samsung", status="verified LCSC C1779"),
    "C_10U": cap("10uF", "10 uF 25 V X5R 0805", fp=C0805, lcsc="C15850", mpn="CL21A106KAYNNNE", mfr="Samsung", status="verified LCSC C15850"),
    "C_22U": cap("22uF", "22 uF 25 V X5R 1206", fp=C1206, lcsc="C12891", mpn="CL31A226KAHNNNE", mfr="Samsung", status="verified LCSC C12891"),
    "C_4U7_100V": cap("4.7uF 100V", "4.7 uF 100 V X7S 1210", fp=C1210, lcsc="C2167998", mpn="C3225X7S2A475K200AB",
                      mfr="TDK", jlc="Extended", status="verified LCSC (Phase 2)", spares=6,
                      note="LCSC and JLC out of stock on 29 Sep 2026; Newark, Avnet and Future stock it. Any 4.7 uF "
                           ">= 100 V X7R/X7S 1210 fits"),
    "C_22N_100V": cap("22nF 100V", "22 nF 100 V X7R 1206 (C_a across the LED)", fp=C1206, jlc="Extended", status="describe"),
    "C_47U_100V": dict(value="47uF 100V", footprint="Capacitor_SMD:CP_Elec_10x10", symbol="Device:C_Polarized", kind="C",
                       mpn="RVT2A470M1010", manufacturer="Honor Elec", lcsc="C87862", jlc="Extended",
                       status="verified LCSC C87862 (10 x 10.2 mm)",
                       desc="47 uF 100 V aluminium electrolytic, SMD 10 x 10.2 mm, 105 C", pins={"1": "+", "2": "-"}, spares=2,
                       note="Any 47 uF 100 V SMD electrolytic in a 10 x 10 mm can fits. (The EEE-FK2A470AQ named earlier is a 12.5 mm can)"),
    # ------------------------------------------------------------------ connectors and mechanics
    "MSTBA2": dict(value="MSTBA 2,5/2-G-5,08", footprint="Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal",
                   symbol="Connector:Screw_Terminal_01x02", kind="J", mpn="1757242", manufacturer="Phoenix Contact",
                   jlc="", place="hand", status="verified phoenixcontact.com (1757242 header, 1757019 plug)",
                   desc="2-pos 5.08 mm pluggable header; mating plug MSTB 2,5/2-ST-5,08 (1757019)"),
    "MSTB_PLUG": dict(value="MSTB 2,5/2-ST-5,08", footprint="-", symbol="-", kind="J", mpn="1757019",
                      manufacturer="Phoenix Contact", jlc="", place="off-board",
                      status="verified phoenixcontact.com", desc="2-pos 5.08 mm screw plug, mates J1 and J2"),
    "FUSE3A": dict(value="3A T", footprint="Fuse:Fuse_Littelfuse-NANO2-451_453", symbol="Device:Fuse", kind="F",
                   mpn="0452003.MRL", manufacturer="Littelfuse", jlc="", status="verified element14 listing",
                   desc="3 A slow-blow SMD fuse, 125 V AC/DC, 2410 (Nano2 452)"),
    "IDC2x5": dict(value="2x5 box header", footprint="Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical",
                   symbol="Connector_Generic:Conn_02x05_Odd_Even", kind="J", jlc="", place="hand", status="describe",
                   desc="2x5 2.54 mm shrouded box header, vertical, through-hole (any maker; key slot toward the board edge)"),
    "STDC14": dict(value="STDC14", footprint="Connector_PinHeader_1.27mm:PinHeader_2x07_P1.27mm_Vertical_SMD",
                   symbol="Connector_Generic:Conn_02x07_Odd_Even", kind="J", mpn="FTSH-107-01-L-DV-K",
                   manufacturer="Samtec", jlc="", status="verified samtec.com 29 Sep 2026 (in stock)",
                   desc="2x7 1.27 mm SMD header with keying notch, no alignment pins (STDC14 for the STLINK-V3MINIE)",
                   note="Not the -K-A version ST's manual names: its alignment pins need holes this footprint lacks"),
    "USBC_HRO": dict(value="USB-C", footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
                     symbol="Connector:USB_C_Receptacle_USB2.0", kind="J", mpn="TYPE-C-31-M-12", manufacturer="HRO",
                     lcsc="C165948", jlc="Extended", status="verified LCSC C165948", desc="USB-C 2.0 receptacle, 16-pin SMD",
                     pins={p: p for p in ("A1", "A4", "A5", "A6", "A7", "A8", "A9", "A12", "B1", "B4", "B5", "B6",
                                          "B7", "B8", "B9", "B12", "S1")}),
    "PEC11R": dict(value="PEC11R-4220F-S0024", footprint="Rotary_Encoder:RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm_CircularMountingHoles",
                   symbol="Device:RotaryEncoder_Switch", kind="SW", mpn="PEC11R-4220F-S0024", manufacturer="Bourns",
                   jlc="", place="hand",
                   status="verified Bourns ordering code; Newark, Digi-Key and Mouser stock it",
                   desc="24-detent encoder with push switch, 20 mm flatted shaft",
                   note="LCSC's C462143 is the knurled -4220K, so no LCSC number. The EC11E footprint's 1.5 mm "
                        "lug slots are narrower than Bourns' 1.8 x 2.1 mm lug holes, hence the round 2.6 mm holes: "
                        "test-fit a real encoder on a 1:1 print",
                   pins={"A": "A", "B": "B", "C": "C", "S1": "S1", "S2": "S2", "MP": "MP"}),
    "TACT6": dict(value="tactile 6x6", footprint="Button_Switch_SMD:SW_SPST_B3S-1000", symbol="Switch:SW_Push",
                  kind="SW", jlc="Basic", status="describe",
                  desc="6 x 6 mm SMD tactile switch, 4 gull-wing pads (Omron B3S-1000 or C&K PTS645 SMD land); "
                       "pick SW4's height so it reaches the panel"),
    "HDR1x8": dict(value="1x8 header", footprint="Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
                   symbol="Connector_Generic:Conn_01x08", kind="J", jlc="", place="hand", status="describe",
                   desc="1x8 2.54 mm pin header, optional"),
    "HDR1x5": dict(value="1x5 header", footprint="Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical",
                   symbol="Connector_Generic:Conn_01x05", kind="J", jlc="", place="hand", status="describe",
                   desc="1x5 2.54 mm pin header, optional"),
    "SOCKET_1x9": dict(value="1x9 socket", footprint="-", symbol="-", kind="J", jlc="", place="hand, bottom side",
                       status="describe", spares=2,
                       desc="1x9 2.54 mm female header, vertical, through-hole, about 8.5 mm tall, gold-plated "
                            "contacts (any maker): the ESP32-S3-Zero's socket, soldered into U1's pads from the top",
                       note="Solder both with the module plugged in, so the rows end up exactly parallel"),
    "JSTPH2": dict(value="JST PH 2", footprint="Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
                   symbol="Connector_Generic:Conn_01x02", kind="J", mpn="B2B-PH-K-S(LF)(SN)", manufacturer="JST",
                   jlc="", place="hand", status="describe", desc="2-pin JST PH header for an external sync button"),
    "NETTIE": dict(value="NetTie", footprint="NetTie:NetTie-2_SMD_Pad0.5mm", symbol="Device:NetTie_2", kind="mech",
                   no_bom=True, status="n/a", desc="Kelvin net tie (copper only)"),
    "TP": dict(value="TP", footprint="TestPoint:TestPoint_Pad_D1.0mm", symbol="Connector:TestPoint", kind="mech",
               no_bom=True, status="n/a", desc="1 mm test pad (copper only)"),
    "MH": dict(value="M3", footprint="MountingHole:MountingHole_3.2mm_M3", symbol="Mechanical:MountingHole", kind="mech",
               no_bom=True, status="n/a", desc="M3 mounting hole, unplated", pins={}),
    "FID": dict(value="FID", footprint="Fiducial:Fiducial_1mm_Mask2mm", symbol="Mechanical:Fiducial", kind="mech",
                no_bom=True, status="n/a", desc="Fiducial", pins={}),
}
