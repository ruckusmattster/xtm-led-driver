"""Board B (controller) layout: 60 x 45 mm, two layers.

The ESP32 is a Waveshare ESP32-S3-Zero plugged into two 1x9 sockets on the BOTTOM of the board, so
its 12-14 mm of height sits behind the board, not between the board and the operator panel (the
panel is clamped by the encoder's nut, a few millimetres above the top side). Its antenna end is at
the right-hand edge, over a copper keep-out; its USB-C end points into the board, and it comes out
of its sockets to be flashed. Everything else is on the top: the ribbon header on the left edge, the
encoder with its LEDs and sync button in the middle-left, the spare header on the bottom edge.
"""
import pcbnew

import board_b
import pcbkit
from pcbkit import Rect

W, H = 60.0, 45.0

# U1's centre: its antenna end (11.8 mm from the centre) a whisker inside the right-hand edge, its
# two socket rows at y = 25.4 and 40.6
U1_X, U1_Y = 48.1, 33.0

NET_CLASSES = {
    "Default": {"clearance": 0.2, "track_width": 0.2, "via_diameter": 0.6, "via_drill": 0.3},
    # 0.5 A at most (IPC-2221: about 0.1 mm on 1 oz for a 10 degC rise); 0.3 mm leaves the router room
    "Power": {"clearance": 0.2, "track_width": 0.3, "via_diameter": 0.6, "via_drill": 0.3},
}
PATTERNS = [("+5V5_IN", "Power"), ("+5V5_F", "Power"), ("+5V_SYS", "Power"), ("+3V3", "Power"), ("GND", "Power")]


def build(out_dir=None):
    L = pcbkit.Layout(board_b.build(), W, H, corner=2.0, layers=2, out_dir=out_dir)
    L.outline()
    L.overhang_ok = {"U1": True}          # its courtyard reaches half a millimetre past the edge

    # ---- anchors
    # U1 on the back, turned so that its pins 1-9 (5V, GND, 3V3, IO1-IO6) run along y = 25.4 from
    # the USB end (x 37.9) to the antenna end (x 58.3), and pins 10-18 (IO7-IO13, RX, TX) come back
    # along y = 40.6
    L.place("U1", U1_X, U1_Y, 270, side="bottom")
    L.place("J1", 4.3, 16.5, 0)            # ribbon header, left edge, pin 1 top-left
    L.place("J3", 4.5, 5.0, 0)             # external sync button, top-left corner
    L.place("SW3", 13.5, 6.5, 0)           # encoder: shaft at (21, 9)
    L.place("SW4", 21.0, 22.0, 0)          # sync button below the encoder
    L.place("H1", 4.0, 41.0, 0)
    L.place("H2", 56.0, 4.0, 0)
    L.place("J4", 13.5, 42.3, 90)          # spare header along the bottom edge

    # ---- small parts, placed next to what they serve
    A = L.autoplace
    A(["C1"], Rect(30, 18, 46, 32), anchor_pad={"C1": ("U1", "1")})
    A(["C3"], Rect(30, 18, 50, 32), anchor_pad={"C3": ("U1", "3")})
    A(["D1", "FB1"], Rect(12, 28, 40.3, 40.2), near=("U1", "1"))
    A(["R8", "R10", "R12", "R14", "C8", "C9", "C10", "C11"], Rect(34, 9.7, 60, 23.5))
    A(["R7", "R9", "R11", "R13"], Rect(12, 16.5, 30, 31), near=("SW3", "C"))
    A(["R18", "R19", "R20", "R21", "R22", "R23"], Rect(10.6, 11, 17, 38), near=("J1", "5"))
    A(["D3", "D4", "D5"], Rect(14, 25.5, 32, 30), near=(21, 27.5))
    A(["R15", "R16", "R17"], Rect(14, 25.5, 36, 33), near=(23, 29))
    A(["TP1", "TP2", "TP3"], Rect(26, 30, 38, 44.5))
    A(["FID1"], Rect(10.6, 30, 16, 40))
    A(["FID2"], Rect(0.6, 34, 8, 37.4))
    A(["FID3"], Rect(26, 2, 50, 12))
    # fiducials need 1 mm of bare board around them (their mask opening); keep tracks off
    for f in ("FID1", "FID2", "FID3"):
        x, y, _ = L.placed[f]
        L.keepout(L.copper_layers(), [(x - 1.6, y - 1.6), (x + 1.6, y - 1.6), (x + 1.6, y + 1.6), (x - 1.6, y + 1.6)],
                  tracks=True, vias=True, pour=True, name="fiducial")
    return L


def finish(L):
    """Copper added after routing: ground pours on both layers."""
    edge = 0.5
    pts = [(edge, edge), (W - edge, edge), (W - edge, H - edge), (edge, H - edge)]
    L.zone("GND", pcbnew.F_Cu, pts, priority=0, min_width=0.25, solid=True, name="GND top")
    L.zone("GND", pcbnew.B_Cu, pts, priority=0, min_width=0.25, solid=True, name="GND bottom")


def labels(L):
    """Silkscreen on the back: which part goes in the sockets and which way round (text on the
    back is mirrored, so it reads correctly from there), and the board's name."""
    B = pcbnew.B_SilkS
    L.text("ESP32-S3-Zero", U1_X, U1_Y - 1.5, 1.0, layer=B, bold=True)
    L.text("USB-C end", U1_X - 7.5, U1_Y + 1.5, 0.8, layer=B)
    L.text("antenna end", U1_X + 6.0, U1_Y + 1.5, 0.8, layer=B)
    # the module also fits turned round, which would put 5 V on a GPIO: mark its 5V and TX pins
    for num, label, dy in (("1", "5V", -2.4), ("18", "TX", 2.4)):
        x, y = L.pad_xy("U1", num)
        L.text(label, x, y + dy, 0.8, layer=B, bold=True)
    L.text("XTM controller B  rev 2", 18.0, 30.0, 1.0, layer=B)


# the antenna end of U1, kept free of stitching vias (the footprint's own keep-out does the rest)
ANTENNA = Rect(U1_X + 6.5, U1_Y - 7.0, W + 1, U1_Y + 7.0)

SPEC = dict(module=__name__, build=build, finish=finish, labels=labels, net_classes=NET_CLASSES, patterns=PATTERNS,
            route_timeout=900, skip_nets=["GND"], power_layers=[], attempts=6, restart_every=2,
            stitch_grid=[dict(net="GND", pitch=3.0, exclude=[ANTENNA])],
            via_exclude={"GND": [ANTENNA]},
            fanout=[dict(net="GND", skip_refs=["U1"], keep_out=[ANTENNA])], dru="board_b.kicad_dru",
            render_layers=[["F.Cu", "F.SilkS", "Edge.Cuts"], ["B.Cu", "B.SilkS", "Edge.Cuts"]])
