"""Board A (driver) layout: 90 x 60 mm, four layers.

Floorplan (see hardware/LAYOUT.md): MCU and debug top-left, aux rails and the Board B link
top-right, the precision island below the MCU, the sinks along the bottom-left with the LED
connector J2, the tracking buck bottom-middle and the 48 V entry bottom-right.

Stackup as built by this script: L1 parts, signals, power copper and a GND pour; L2 and L3 solid
GND; L4 signals, the CATHODE heat spreader under Q1 and a GND pour. Both inner layers are planes
(nothing routes on them), so every signal has an unbroken ground under it.
"""
import math

import pcbnew

import board_a
import pcbkit
import route
from pcbkit import Rect

W, H = 90.0, 60.0

HV_NETS = ["+48V_RAW", "+48V", "VOUT", "BUCK_SW", "BUCK_BOOT", "AUX_SW", "AUX_BOOT", "CATHODE"]
PRECISION = ["SET*", "NINV*", "SNSHI*", "SNSLO*", "DAC_OUT*", "DAC_REF", "BIAS"]

# Track widths are what the router uses. They have to fit the pins they land on: 0.2 mm reaches the
# 0.5 mm-pitch QFN pads of U1 and U6, and the HV class's 0.6 mm (IPC-2221 wants 0.53 mm for 1.5 A
# on 1 oz at a 10 degC rise) fits U2's and U3's 1.27 mm pitch with the HV clearance.
NET_CLASSES = {
    # signal vias 0.5/0.2 mm (JLCPCB's four-layer minimum is 0.45/0.2; U2's and U3's footprints
    # already have 0.2 mm thermal vias): more of them fit around the fine-pitch parts
    "Default": {"clearance": 0.2, "track_width": 0.2, "via_diameter": 0.5, "via_drill": 0.2},
    # 0.5 mm: IPC-2221B's figure for bare pads at 51-100 V; the rules file allows 0.3 mm between
    # soldermasked copper, but the router can't tell a pad from a track
    "HV": {"clearance": 0.5, "track_width": 0.6, "via_diameter": 0.6, "via_drill": 0.3},
    "Aux": {"clearance": 0.2, "track_width": 0.5, "via_diameter": 0.6, "via_drill": 0.3},
    "Precision": {"clearance": 0.2, "track_width": 0.2, "via_diameter": 0.5, "via_drill": 0.2},
}
PATTERNS = ([(n, "HV") for n in HV_NETS] + [(n, "Aux") for n in ("+5V5", "+5V5_LINK")]
            + [(n, "Precision") for n in PRECISION])

HOLES = [(4.0, 4.0), (86.0, 4.0), (4.0, 56.0), (86.0, 56.0)]
SPACING = 0.3                 # mm between the courtyards of autoplaced parts
MCU_SPACING = 0.5             # more around the MCU, whose 48 pins all have to get out
LADDER = [f"R{90 + i}" for i in range(10)]
LADDER_Y = 44.4


def rung_x(i):
    """x of ladder rung i: 2 mm pitch with a 0.8 mm gap in the middle for the Kelvin net ties."""
    return 8.3 + 2.0 * i + (0.8 if i >= 5 else 0.0)
HOLE_KEEPOUT = 3.25          # 6.5 mm keep-out circle on every layer


def octagon(cx, cy, r):
    k = r / math.cos(math.pi / 8)
    return [(cx + k * math.cos(math.pi / 8 + i * math.pi / 4), cy + k * math.sin(math.pi / 8 + i * math.pi / 4))
            for i in range(8)]


def rect_pts(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def build(out_dir=None):
    L = pcbkit.Layout(board_a.build(), W, H, corner=2.0, layers=4, out_dir=out_dir)
    L.outline()
    L.overhang_ok = {"J1": True, "J2": True}
    cu = L.copper_layers()

    # ---- mounting holes: non-plated, 6.5 mm keep-out on every layer, not grounded
    for i, (x, y) in enumerate(HOLES, start=1):
        L.place(f"H{i}", x, y, 0)
        L.keepout(cu, octagon(x, y, HOLE_KEEPOUT), tracks=True, vias=True, pour=True, name="hole")
        L.blocked.append(Rect(x - HOLE_KEEPOUT, y - HOLE_KEEPOUT, x + HOLE_KEEPOUT, y + HOLE_KEEPOUT))

    # ---- connectors on the edges
    L.place("J1", 73.0, 50.0, 0)           # 48 V in; pin 1 +48V_RAW, wire entry off the bottom edge
    L.place("J2", 39.5, 50.0, 0)           # LED out; pin 1 CATHODE (left), pin 2 VOUT (right)
    L.place("J3", 56.0, 7.0, 90)           # ribbon to Board B, top edge
    L.place("J4", 6.8, 13.5, 0)            # STDC14 debug, left edge, with room outside its pins
    # 1 mm slot between J2's pads, 6 mm long (leakage across flux at the bottom of the range)
    L.slot(41.54, 47.0, 42.54, 53.0)
    L.blocked.append(Rect(41.3, 46.8, 42.8, 53.2))

    # ---- 48 V entry
    L.place("F1", 73.0, 41.9, 90)          # pad 1 (+48V_RAW) toward J1
    L.place("D1", 74.5, 35.8, 0)           # pad 1 +48V left, pad 2 GND right
    L.place("C1", 84.0, 40.8, 270)         # pad 1 +48V top, pad 2 GND bottom

    # ---- tracking buck: U2 pins 1-4 (GND, EN, VIN, RT) up, 5-8 (FB, PG, BOOT, SW) down
    L.place("U2", 53.1, 40.5, 270)
    L.place("C23", 54.5, 45.1, 0)          # BOOT cap straight across BOOT and SW, below the pins
    L.place("L2", 55.4, 53.0, 270)         # pad 1 (SW) up under C23, pad 2 (VOUT) at the bottom
    L.place("C22", 52.465, 35.2, 90)       # 100 nF on VIN; its GND pad takes a via to the planes
    L.blocked.append(Rect(53.3, 35.6, 54.7, 37.0))      # EN's escape via (see prerouted)
    L.blocked.append(Rect(52.6, 32.7, 56.4, 36.6))      # +48V from C20 to C22 (see prerouted)
    L.place("C20", 57.6, 34.8, 270)        # bulk input cap, pad 1 (+48V) up to meet the input trunk
    L.blocked.append(Rect(58.4, 30.6, 74.0, 33.0))      # the +48V trunk from the input (see prerouted)
    L.blocked.append(Rect(71.2, 30.6, 73.5, 34.7))

    # ---- aux buck: U3 pins 5-8 (FB, PG, BOOT, SW) left toward L3, 1-4 right
    L.place("U3", 82.0, 15.0, 180)
    L.place("C3", 77.3, 16.27, 270)        # BOOT cap beside BOOT and SW
    L.place("L3", 68.6, 17.5, 180)         # pad 1 (SW) right, pad 2 (+5V5) left
    L.place("C5", 87.3, 14.365, 0)         # 100 nF at VIN
    # nothing but plane copper under either inductor on the inner signal layer and the bottom
    for ref in ("L2", "L3"):
        b = L.box(ref)
        L.keepout([L.board.GetLayerID("In2.Cu"), pcbnew.B_Cu], rect_pts(b.x0, b.y0, b.x1, b.y1),
                  tracks=True, vias=True, pour=False, name="under " + ref)

    # ---- sinks and LED output
    L.place("Q1", 24.2, 51.0, 0)           # tab (CATHODE) right, onto the heat-spreading copper
    L.place("R102", 13.5, 53.0, 180)       # pad 1 SRC1 right toward Q1's source, pad 4 GND left
    L.place("C60", 42.0, 45.5, 180)        # across J2: pad 2 CATHODE left, pad 1 VOUT right
    for i, ref in enumerate(LADDER):       # ch2 shunt: ten rungs, SRC2 bar on top, GND bar below
        L.place(ref, rung_x(i), LADDER_Y, 270)
    mid = (rung_x(4) + rung_x(5)) / 2
    # the three small sinks in a row along the top of the tab copper, drains down onto it,
    # ch3 and ch4 shunts straight above their sources
    L.place("Q2", 30.0, 43.2, 270)         # source top-left onto the SRC2 bar
    L.place("Q3", 33.7, 43.2, 270)
    L.place("Q4", 37.3, 43.2, 270)
    L.place("R100", 33.7 - 0.95, 39.45, 90)    # pad 1 (SRC3) down to Q3's source, pad 2 (GND) up
    L.place("R101", 37.3 - 0.95, 39.45, 90)
    L.place("NT1", mid, 42.55, 90)         # SRC2 bar mid-point -> SNSHI2
    L.place("NT2", mid, 46.25, 270)        # GND bar mid-point -> SNSLO2
    L.place("R110", 40.6, 43.2, 0)         # cathode tap: pad 1 on the tab copper, pad 2 toward the MCU
    L.blocked.append(Rect(26.0, 44.6, 41.0, 59.4))      # CATHODE copper
    L.blocked.append(Rect(6.4, 46.2, 9.6, 47.8))        # the ladder's ground vias

    # ---- MCU and precision island anchors, each with a clear ring so its pins can fan out
    L.place("U1", 21.0, 10.5, 0)
    L.place("U7", 22.0, 31.0, 0)           # op-amp: ch1/ch2 on the left pins, ch3/ch4 on the right
    L.place("U6", 22.0, 24.6, 0)           # DAC: SPI on top toward the MCU, outputs left and bottom
    for ref, ring in (("U1", 3.0), ("U6", 1.4), ("U7", 1.0)):
        L.blocked.append(L.box(ref).grow(ring))

    # ---- fiducials first, in three corners' free spots
    L.place("FID1", 11.0, 2.6, 0)
    L.place("FID2", 47.2, 2.6, 0)
    L.place("FID3", 87.6, 31.0, 0)
    for f in ("FID1", "FID2", "FID3"):
        x, y, _ = L.placed[f]
        L.blocked.append(Rect(x - 1.6, y - 1.6, x + 1.6, y + 1.6))

    # ---- small parts, next to what they serve, with room between them for the router's channels
    def A(refs, region, **kw):
        kw.setdefault("gap", MCU_SPACING if region is mcu else SPACING)
        L.autoplace(refs, region, **kw)
    island = Rect(4.5, 21.0, 46.0, 41.0)
    mcu = Rect(0.6, 1.6, 47.0, 21.0)
    aux = Rect(46.5, 0.6, 89.4, 29.0)
    buck = Rect(44.8, 29.0, 70.6, 59.4)
    entry = Rect(68.5, 33.0, 89.4, 47.3)
    sinks = Rect(4.0, 40.0, 41.0, 59.4)

    # buck power parts first
    A(["C21"], Rect(44.8, 29.0, 60.0, 36.8), anchor_pad={"C21": ("U2", "3")})
    A(["C24", "C25", "C26", "C27", "C28"], Rect(61.4, 42.0, 69.0, 59.4), anchor_pad={r: ("L2", "2") for r in
                                                                                 ("C24", "C25", "C26", "C27", "C28")})
    A(["D2"], Rect(56.5, 36.0, 70.0, 47.0), anchor_pad={"D2": ("C24", "1")})
    A(["R12", "C29", "R17", "TP5"], Rect(56.0, 29.0, 70.6, 47.0), near=("C24", "1"))
    A(["R13", "R14", "C30", "R15"], Rect(44.8, 38.0, 51.0, 47.0), near=("U2", "5"))
    A(["R10", "R11", "R16"], Rect(44.8, 29.0, 62.0, 38.0), near=("U2", "2"))
    A(["RT2"], Rect(56.0, 29.0, 70.6, 47.0), near=("U2", "1"))
    A(["TP10"], buck, near=("R15", "2"))
    A(["R18", "C31"], mcu, anchor_pad={"R18": ("U1", "8"), "C31": ("U1", "8")})

    # 48 V entry
    A(["R1", "TP1", "TP8"], entry, near=("F1", "2"))
    A(["R2", "C2"], mcu, anchor_pad={"R2": ("U1", "17"), "C2": ("U1", "17")})

    # aux rails
    A(["C4"], Rect(80.0, 7.5, 89.4, 13.0), anchor_pad={"C4": ("U3", "3")})
    A(["R3", "R4", "R5"], Rect(76.0, 17.9, 89.4, 29.0), near=("U3", "2"))
    A(["R6", "R7"], Rect(71.0, 7.0, 80.0, 14.0), near=("U3", "5"))
    A(["C6", "C7", "C8"], Rect(48.0, 11.0, 62.0, 26.0), anchor_pad={r: ("L3", "2") for r in ("C6", "C7", "C8")})
    A(["U5"], Rect(46.5, 18.0, 62.0, 29.0), near=("L3", "2"))
    A(["C13", "C14"], aux, anchor_pad={"C13": ("U5", "2"), "C14": ("U5", "2")})
    A(["FB2", "C79"], Rect(46.5, 10.8, 62.0, 18.0), near=("J3", "1"))
    A(["RT3", "TP2", "TP4"], aux, near=(66.0, 26.0))

    # MCU
    A(["C70"], mcu, anchor_pad={"C70": ("U1", "1")})
    A(["C71"], mcu, anchor_pad={"C71": ("U1", "23")})
    A(["C72"], mcu, anchor_pad={"C72": ("U1", "35")})
    A(["C73"], mcu, anchor_pad={"C73": ("U1", "48")})
    A(["C74"], mcu, near=("U1", "48"))
    A(["C77"], mcu, anchor_pad={"C77": ("U1", "20")})
    A(["C76"], mcu, anchor_pad={"C76": ("U1", "21")})
    A(["FB1", "C75", "C15", "C16"], mcu, near=("U1", "21"))
    A(["C78", "R120"], mcu, anchor_pad={"C78": ("U1", "7"), "R120": ("U1", "46")})
    A(["C61", "D3"], mcu, anchor_pad={"C61": ("U1", "9"), "D3": ("U1", "9")})
    A(["R40", "R41", "R42"], mcu, anchor_pad={"R40": ("U1", "38"), "R41": ("U1", "41"), "R42": ("U1", "43")})
    A(["C56", "C57", "C58", "C59"], mcu, anchor_pad={"C56": ("U1", "14"), "C57": ("U1", "15"),
                                                     "C58": ("U1", "19"), "C59": ("U1", "28")})
    A(["R126", "R127", "R128", "R129", "C80", "C81", "C82", "C83"], mcu, near=("U1", "24"))
    A(["R121", "R122", "R123", "R124"], mcu, anchor_pad={"R121": ("U1", "31"), "R122": ("U1", "32"),
                                                         "R123": ("U1", "32"), "R124": ("U1", "33")})
    A(["R125", "D4"], mcu, near=("U1", "34"))
    A(["TP6", "TP11"], mcu, near=(30.0, 17.0))

    # precision island
    A(["C40"], island, anchor_pad={"C40": ("U6", "1")})
    A(["C41", "C42"], island, anchor_pad={"C41": ("U6", "7"), "C42": ("U6", "7")})
    A(["C43"], island, anchor_pad={"C43": ("U6", "10")})
    A(["R43", "R44"], island, anchor_pad={"R43": ("U6", "15"), "R44": ("U6", "11")})
    A(["C50", "C51"], island, anchor_pad={"C50": ("U7", "4"), "C51": ("U7", "4")})
    A(["C44", "C45"], island, anchor_pad={"C44": ("U7", "3"), "C45": ("U7", "5")})
    A(["C46", "C47"], island, anchor_pad={"C46": ("U7", "10"), "C47": ("U7", "12")})
    for k, (rt, rb) in enumerate((("R45", "R46"), ("R47", "R48"), ("R49", "R50"), ("R51", "R52")), start=1):
        pin = {1: "3", 2: "5", 3: "10", 4: "12"}[k]
        A([rt, rb], island, anchor_pad={rt: ("U7", pin), rb: ("U7", pin)}, rotations=(0,))
    for k in range(4):
        npin = {0: "2", 1: "6", 2: "9", 3: "13"}[k]
        A([f"C{52 + k}", f"R{60 + k}", f"R{64 + k}"], island,
          anchor_pad={f"C{52 + k}": ("U7", npin), f"R{60 + k}": ("U7", npin), f"R{64 + k}": ("U7", npin)})
    A(["R53", "R54", "C48", "TP7"], island, near=("U7", "4"))
    A(["RT4"], island, near=(22.0, 27.8))
    A(["U4"], Rect(36.0, 21.0, 44.0, 39.6), near=(40.0, 30.0))
    L.blocked.append(L.box("U4").grow(0.8))     # room for +5V5 to reach both IN and EN
    A(["C9", "C10", "C11", "C12", "TP3"], Rect(34.0, 21.0, 44.0, 39.6), near=("U4", "5"))
    A(["R76", "R77", "R78", "R79", "R80", "R81", "R82", "R83"], island, near=(22.0, 37.5))
    A(["TP12", "TP13", "TP14", "TP15", "TP16", "TP17", "TP18", "TP19", "TP9"], island, near=(22.0, 38.0))

    # sinks: the Kelvin net ties right at the ch3/ch4 shunts' pads
    ties = Rect(28.0, 35.0, 41.0, 44.6)
    A(["NT3", "NT4"], ties, anchor_pad={"NT3": ("R100", "1"), "NT4": ("R100", "2")}, gap=0.2)
    A(["NT5", "NT6"], ties, anchor_pad={"NT5": ("R101", "1"), "NT6": ("R101", "2")}, gap=0.2)
    # gate stoppers at the FET gates; the reset clamps and their pull-ups where there's room on the way
    for k, q in enumerate(("Q1", "Q2", "Q3", "Q4")):
        A([f"R{68 + k}"], sinks, anchor_pad={f"R{68 + k}": (q, "1")})
    clamps = Rect(4.5, 28.0, 47.0, 59.4)
    for k in range(4):
        A([f"Q{5 + k}", f"R{72 + k}"], clamps, anchor_pad={f"Q{5 + k}": (f"R{68 + k}", "2"),
                                                          f"R{72 + k}": (f"R{68 + k}", "2")})
    A(["RT1"], sinks, near=("Q1", "2"))

    for f in ("FID1", "FID2", "FID3"):
        if f not in L.placed:
            continue
        x, y, _ = L.placed[f]
        L.keepout(cu, rect_pts(x - 1.6, y - 1.6, x + 1.6, y + 1.6), tracks=True, vias=True, pour=True, name="fiducial")
    return L


def cathode_copper(L):
    """Q1's tab copper on L1 (J2 pin 1, C60, the four drains, R110) and the heat spreader under it
    on L4, joined by a grid of vias. Drawn before routing so the router keeps clear of it."""
    x0, y0, x1, y1 = 26.0, 44.6, 41.0, 59.4
    rects = [(x0, y0, x1, y1), (20.0, 50.25, x0 + 0.5, 51.75)]          # Q1's middle pin under its body
    for ref in ("Q2", "Q3", "Q4"):                                        # the small sinks' drains, from above
        px, py = L.pad_xy(ref, "3")
        rects.append((px - 0.3, py - 0.5, px + 0.3, y0 + 0.5))
    px, py = L.pad_xy("R110", "1")                                        # the tap resistor, from above
    rects.append((px - 0.45, py - 0.45, px + 0.35, y0 + 0.5))
    L.zone_rects("CATHODE", pcbnew.F_Cu, rects, priority=2, min_width=0.3, solid=True, name="CATHODE tab copper")
    L.zone_rects("CATHODE", pcbnew.B_Cu, [(22.0, y0, x1, y1)], priority=2, min_width=0.3, solid=True,
                 name="CATHODE heat spreader")
    # the router treats these zones as copper it can cross: keep it out of the tab copper, and off
    # the spreader under it (vias there would hit the tab); the spreader's strip under Q1's body
    # stays open to vias for the parts beside it
    L.router_keepouts = [("F.Cu", rects), ("B.Cu", [(x0, y0, x1, y1)])]


def prerouted(L):
    """Copper drawn by hand before routing: both switch nodes and bootstrap links (L1 only, no vias),
    the fused input, Q1's source to its shunt, and the ground vias of the exposed pads."""
    # tracking buck: U2 SW -> C23 -> L2, BOOT -> C23
    sw = L.pad_xy("U2", "8")
    c23b, c23s = L.pad_xy("C23", "1"), L.pad_xy("C23", "2")
    l2 = L.pad_xy("L2", "1")
    # narrow past C23's BOOT pad (0.6 mm HV spacing), full width once clear of it
    x = c23s[0] - 0.15
    L.track("BUCK_SW", [sw, (x, sw[1] + 1.0), (x, c23s[1] + 1.1)], 0.5)
    L.track("BUCK_SW", [(x, c23s[1] + 1.1), (l2[0], l2[1] - 1.0)], 1.2)
    L.track("BUCK_BOOT", [L.pad_xy("U2", "7"), c23b], 0.4)
    # aux buck: U3 SW -> C3 -> L3, BOOT -> C3
    sw = L.pad_xy("U3", "8")
    c3b, c3s = L.pad_xy("C3", "1"), L.pad_xy("C3", "2")
    l3 = L.pad_xy("L3", "1")
    L.track("AUX_SW", [sw, (sw[0] - 1.0, sw[1])], 0.6)
    L.track("AUX_SW", [(sw[0] - 1.0, sw[1]), (sw[0] - 1.2, c3s[1] + 0.05), (l3[0] + 1.1, c3s[1] + 0.05)], 0.8)
    L.track("AUX_BOOT", [L.pad_xy("U3", "7"), c3b], 0.4)
    # ch2 ladder: SRC2 bar along the top pads (and on to Q2's source), GND bar along the bottom,
    # the GND bar taken to the planes at the far end from Q2
    top = [L.pad_xy(r, "1") for r in LADDER]
    bot = [L.pad_xy(r, "2") for r in LADDER]
    L.track("SRC2", [top[0], top[-1], L.pad_xy("Q2", "2")], 1.0)
    L.track("GND", [(7.4, bot[0][1]), bot[-1]], 1.0)
    for x, y in ((7.4, 46.9), (8.8, 46.9)):
        L.track("GND", [(x, bot[0][1]), (x, y)], 0.6)
        L.via("GND", x, y)
    # Board B's supply: J3's two +5V5_LINK pins tied together
    L.track("+5V5_LINK", [L.pad_xy("J3", "1"), L.pad_xy("J3", "3")], 0.8)
    # U2's EN pin sits between VIN and GND, fenced by 0.6 mm HV spacing: up past C22 to a via
    ex, ey = L.pad_xy("U2", "2")
    L.track("BUCK_EN", [(ex, ey), (ex + 0.05, ey - 1.0), (ex + 0.3, ey - 1.5)], 0.2)
    L.via("BUCK_EN", ex + 0.3, ey - 1.5)
    # +48V from C20 into C22 and U2's VIN, between C22's GND pad and EN's via
    c20, c22 = L.pad_xy("C20", "1"), L.pad_xy("C22", "1")
    L.track("+48V", [c20, (c20[0] - 2.1, c20[1]), (c22[0] + 0.475, c22[1] + 0.325), c22], 0.4)
    L.track("+48V", [c22, L.pad_xy("U2", "3")], 0.6)
    # U2's PG pin is boxed in by FB, BOOT and L2's switch-node pad: take it straight to a via
    px, py = L.pad_xy("U2", "6")
    L.track("BUCK_PG", [(px, py), (px - 0.1, py + 1.85)], 0.25)
    L.via("BUCK_PG", px - 0.1, py + 1.85)
    # +48V trunk: the input (D1, F1, C1) to the buck's bulk capacitor C20, clear of everything
    c20 = L.pad_xy("C20", "1")
    d1 = L.pad_xy("D1", "1")
    L.track("+48V", [c20, (c20[0] + 1.6, 31.8), (d1[0], 31.8), d1], 0.8)
    # fused input: J1 pin 1 -> F1
    L.track("+48V_RAW", [L.pad_xy("J1", "1"), L.pad_xy("F1", "1")], 2.0)
    # Q1 source -> R102 force pad
    L.track("SRC1", [L.pad_xy("Q1", "3"), L.pad_xy("R102", "1")], 1.5)
    # exposed pads: a 3 x 3 via array under U1, one via in U6's 0.8 mm pad
    ux, uy, _ = L.placed["U1"]
    for dx in (-1.6, 0.0, 1.6):
        for dy in (-1.6, 0.0, 1.6):
            L.via("GND", ux + dx, uy + dy)
    L.via("GND", *L.pad_xy("U6", "17"))
    # U6's GND pins to its exposed pad under the part (0.5 mm pitch: no room for a via beside them)
    ex, ey = L.pad_xy("U6", "17")
    L.track("GND", [L.pad_xy("U6", "6"), (ex - 0.25, ey + 0.4)], 0.2)
    L.track("GND", [L.pad_xy("U6", "9"), (ex + 1.0, ey + 0.75), (ex + 0.4, ey + 0.35)], 0.2)
    # four vias at R102's ground end
    gx, gy = L.pad_xy("R102", "4")
    for dx, dy in ((-0.7, -0.6), (0.7, -0.6), (-0.7, 0.6), (0.7, 0.6)):
        L.via("GND", gx + dx, gy + dy)
    cathode_copper(L)
    # L2 is a solid GND plane; it goes in before routing so the router sees it as a plane
    # (a 'power' layer without a plane blocks every via)
    e = 1.0
    L.zone("GND", L.board.GetLayerID("In1.Cu"), [(e, e), (W - e, e), (W - e, H - e), (e, H - e)], priority=0,
           min_width=0.25, name="GND In1.Cu")
    # vias between the tab copper and the heat spreader: dense beside Q1's tab, where the heat
    # enters the copper, three under its body along the middle pin's strip, a sparse grid beyond
    spots = [(x, 47.0 + 1.2 * i) for x in (29.4, 30.6, 31.8) for i in range(9)]
    spots += [(x, 51.0) for x in (22.8, 24.0, 25.2)]
    spots += [(x, y) for x in (34.5, 37.0, 39.5) for y in (47.0, 53.5, 56.5)]
    for x, y in spots:
        if not route.via_blocked(L.board, x, y, 0.3):
            L.via("CATHODE", x, y)


def finish(L):
    """Copper added after routing: GND pours on L1, L3 and L4."""
    e = 1.0
    pts = [(e, e), (W - e, e), (W - e, H - e), (e, H - e)]
    L.zone("GND", L.board.GetLayerID("In2.Cu"), pts, priority=0, min_width=0.25, name="GND In2.Cu")
    L.zone("GND", pcbnew.F_Cu, pts, priority=0, min_width=0.25, name="GND top")
    L.zone("GND", pcbnew.B_Cu, pts, priority=0, min_width=0.25, name="GND bottom")


def labels(L):
    """Silkscreen text: connector polarity, the 48 V warning, board name and revision."""
    j1a, j1b = L.pad_xy("J1", "1"), L.pad_xy("J1", "2")
    L.text("+48V", j1a[0], j1a[1] - 3.0, 1.0, bold=True)
    L.text("GND", j1b[0], j1b[1] - 3.0, 1.0, bold=True)
    j2a, j2b = L.pad_xy("J2", "1"), L.pad_xy("J2", "2")
    L.text("LED-", j2a[0] - 1.0, j2a[1] - 3.2, 1.0, bold=True)
    L.text("LED+", j2b[0] + 0.4, j2b[1] - 6.8, 1.0, bold=True)
    L.text("48 V DC", 80.2, 32.4, 1.0, bold=True)
    L.text("XTM driver A  rev 1", 32.0, 1.6, 1.0)


SPEC = dict(module=__name__, build=build, prerouted=[prerouted], finish=finish, labels=labels,
            net_classes=NET_CLASSES, patterns=PATTERNS,
            # every net stays in the routing: the router takes each GND pad to the L2 plane with its own
            # via, and the CATHODE pads sit in the tab copper drawn before routing (keeping their pins
            # also keeps the HV clearance around them)
            skip_nets=[], power_layers=["In1.Cu"], route_timeout=1800, attempts=6, keep_nets=["CATHODE"],
            pour_nets=["GND", "CATHODE"], plane_nets=["GND"], pad_via=(0.5, 0.2), hv_nets=HV_NETS,
            # every GND pad gets its via to L2 before routing, while there's room beside it (U1's,
            # U2's and U3's exposed pads, U6's GND pins, R102 and the ladder have theirs already)
            fanout=[dict(net="GND", via=0.5, drill=0.2, hv_nets=HV_NETS, skip_refs=["U1"],
                         skip_pads=[("U2", "9"), ("U3", "9"), ("U6", "6"), ("U6", "9"), ("U6", "17"),
                                    ("R102", "4")] + [(r, "2") for r in LADDER],
                         keep_out=[Rect(20.0, 42.0, 42.0, 60.0)])],
            class_clearances=[("Precision", "HV", 2.0)],
            stitch_grid=[dict(net="GND", pitch=3.0, hv_nets=HV_NETS, exclude=[Rect(20.0, 42.0, 42.0, 60.0)])],
            via_exclude={"GND": [Rect(20.0, 42.0, 42.0, 60.0)]},
            dru="board_a.kicad_dru",
            render_layers=[["F.Cu", "F.SilkS", "Edge.Cuts"], ["B.Cu", "Edge.Cuts"], ["In2.Cu", "Edge.Cuts"]])
