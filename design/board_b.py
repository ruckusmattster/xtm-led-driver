"""Board B: ESP32-S3 controller (ESPHome), encoder, sync button, ribbon link to Board A.

The ESP32 is a Waveshare ESP32-S3-Zero plugged into two 1x9 sockets on the bottom of the board:
it brings its own USB-C, 3.3 V regulator and BOOT/RESET buttons, and comes out to be flashed.
"""
from netlib import Board, NC

SHEETS = [
    ("B1", "Power"),
    ("B2", "ESP32-S3-Zero"),
    ("B3", "Controls, indicators and link"),
]


def build():
    b = Board("board_b", "Board B (controller)", SHEETS)
    b.power_sources = {"+5V_SYS": "D1", "+3V3": "U1 (the ESP32-S3-Zero's own 3.3 V regulator)"}

    # ------------------------------------------------------------------ B1 power
    s = "B1"
    b.add("J1", "IDC2x5", {"1": "+5V5_IN", "2": "GND", "3": "+5V5_IN", "4": "GND", "5": "TXD_A", "6": "GND",
                           "7": "RXD_A", "8": "BOOT0_A", "9": "A_OK", "10": "NRST_A"}, s,
          note="Same pinout as Board A's J3; a straight-through ribbon")
    b.two("FB1", "FB600_2A", "+5V5_IN", "+5V5_F", s)
    b.add("D1", "B5819W", {"1": "+5V_SYS", "2": "+5V5_F"}, s,
          note="Keeps the module's USB 5 V (its 5V pin) out of Board A when it's powered from USB")
    b.two("C1", "C_10U", "+5V_SYS", "GND", s, note="At U1's 5V pin")

    # ------------------------------------------------------------------ B2 module
    s = "B2"
    b.add("U1", "ESP32-S3-ZERO", {
        "1": "+5V_SYS", "2": "GND", "3": "+3V3", "4": "LINK_TX", "5": "LINK_RX", "6": "SPARE_IO3",
        "7": "ENC_A", "8": "ENC_B", "9": "ENC_SW", "10": "SYNC", "11": "BOOT0_OUT", "12": "A_OK_IN",
        "13": "NRST_OUT", "14": "LED_R", "15": "LED_G", "16": "LED_B", "17": "SPARE_IO44", "18": "SPARE_IO43"}, s,
        note="Plugged into two 1x9 sockets on the bottom side, component side away from the board, antenna end "
             "at the board edge. IO4-IO13 keep the WROOM design's assignments; the link moves to IO1/IO2 so "
             "UART0 (IO43/IO44, which the boot ROM talks on) stays off Board A's line. IO3 is a strapping pin: "
             "left as a spare")
    b.extras.append(("U1 sockets", "SOCKET_1x9", 2))
    b.two("C3", "C_100N", "+3V3", "GND", s, note="At U1's 3V3 pin")

    # ------------------------------------------------------------------ B3 controls and link
    s = "B3"
    b.add("SW3", "PEC11R", {"A": "ENC_A_RAW", "B": "ENC_B_RAW", "C": "GND", "S1": "ENC_SW_RAW", "S2": "GND",
                            "MP": "GND"}, s, note="Mounting lugs to GND")
    for raw, sig, rpu, rs, cf in (("ENC_A_RAW", "ENC_A", "R7", "R8", "C8"), ("ENC_B_RAW", "ENC_B", "R9", "R10", "C9"),
                                  ("ENC_SW_RAW", "ENC_SW", "R11", "R12", "C10"), ("SYNC_RAW", "SYNC", "R13", "R14", "C11")):
        b.two(rpu, "R_10K", "+3V3", raw, s)
        b.two(rs, "R_10K", raw, sig, s)
        b.two(cf, "C_10N", sig, "GND", s)
    b.add("SW4", "TACT6", {"1": "SYNC_RAW", "2": "GND"}, s, value="SYNC")
    b.add("J3", "JSTPH2", {"1": "SYNC_RAW", "2": "GND"}, s, note="External panel sync button in parallel with SW4")
    # indicators, active low from +3V3
    for led, key, res, rkey, net in (("D3", "LED_R", "R15", "R_1K", "LED_R"), ("D4", "LED_G", "R16", "R_220", "LED_G"),
                                     ("D5", "LED_B", "R17", "R_220", "LED_B")):
        b.two(res, rkey, "+3V3", f"{net}_A", s)
        b.add(led, key, {"1": net, "2": f"{net}_A"}, s)
    # link to Board A
    b.two("R18", "R_100", "LINK_TX", "RXD_A", s)
    b.two("R19", "R_100", "TXD_A", "LINK_RX", s)
    b.two("R20", "R_100", "BOOT0_OUT", "BOOT0_A", s)
    b.two("R21", "R_100", "A_OK", "A_OK_IN", s)
    b.two("R22", "R_100K", "A_OK_IN", "GND", s, note="Unplugged ribbon reads as 'Board A not OK'")
    b.two("R23", "R_100", "NRST_OUT", "NRST_A", s, note="IO10 is driven open-drain by firmware")
    b.add("J4", "HDR1x5", {"1": "+3V3", "2": "SPARE_IO3", "3": "SPARE_IO43", "4": "SPARE_IO44", "5": "GND"}, s,
          note="Optional spare header: IO43/IO44 are UART0 (the ESP32's console), IO3 a strapping pin")
    for ref, net in (("TP1", "+5V_SYS"), ("TP2", "+3V3"), ("TP3", "GND")):
        b.add(ref, "TP", {"1": net}, s)
    b.single_ok.update({"SPARE_IO3", "SPARE_IO43", "SPARE_IO44"})
    for i in (1, 2):
        b.add(f"H{i}", "MH", {}, s)
    for i in range(1, 4):
        b.add(f"FID{i}", "FID", {}, s)
    return b


if __name__ == "__main__":
    brd = build()
    e, w = brd.erc()
    print(f"{len(brd.parts)} parts, {len(brd.nets())} nets, {len(e)} errors, {len(w)} warnings")
    for x in e + w:
        print(" ", x)
