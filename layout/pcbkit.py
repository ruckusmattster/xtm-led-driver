"""Board builder for the XTM driver layouts, on KiCad 9's pcbnew Python API.

A board script (board_a_layout.py, board_b_layout.py) creates a Layout from the netlist in
design/, places parts (by hand for anchors, with the greedy placer for the rest), adds copper it
wants drawn exactly (tracks, zones, keep-outs), then hands the remaining connections to
Freerouting through route.py. Nothing here needs more than the Python that ships with KiCad 9.

Coordinates are millimetres from the board's top-left corner, y down, as in LAYOUT.md.
Rotations are KiCad's (degrees, counter-clockwise on screen).
"""
import json
import math
import os
import shutil
import sys

import pcbnew

import kicadlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "design"))

MM = pcbnew.FromMM


def V(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def mm(v):
    return pcbnew.ToMM(v)


def rot_xy(x, y, deg):
    """Rotate a footprint-local offset the way KiCad does for an orientation of `deg`."""
    d = round(deg) % 360
    if d == 0:
        return x, y
    if d == 90:
        return y, -x
    if d == 180:
        return -x, -y
    if d == 270:
        return -y, x
    a = math.radians(deg)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


class Rect:
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    def grow(self, d):
        return Rect(self.x0 - d, self.y0 - d, self.x1 + d, self.y1 + d)

    def overlaps(self, o):
        return self.x0 < o.x1 and o.x0 < self.x1 and self.y0 < o.y1 and o.y0 < self.y1

    def inside(self, o):
        return self.x0 >= o.x0 and self.y0 >= o.y0 and self.x1 <= o.x1 and self.y1 <= o.y1

    def contains(self, x, y):
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2

    def __repr__(self):
        return f"Rect({self.x0:.2f},{self.y0:.2f},{self.x1:.2f},{self.y1:.2f})"


def dist_point_rect(px, py, r):
    dx = max(r.x0 - px, 0.0, px - r.x1)
    dy = max(r.y0 - py, 0.0, py - r.y1)
    return math.hypot(dx, dy)


def dist_seg_seg(a, b, c, d):
    """Distance between segments ab and cd (tuples)."""
    def dps(p, s0, s1):
        vx, vy = s1[0] - s0[0], s1[1] - s0[1]
        L = vx * vx + vy * vy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - s0[0]) * vx + (p[1] - s0[1]) * vy) / L))
        return math.hypot(p[0] - s0[0] - t * vx, p[1] - s0[1] - t * vy)

    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2 = cross(a, b, c), cross(a, b, d)
    d3, d4 = cross(c, d, a), cross(c, d, b)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(dps(a, c, d), dps(b, c, d), dps(c, a, b), dps(d, a, b))


def dist_seg_rect(a, b, r):
    if r.contains(*a) or r.contains(*b):
        return 0.0
    corners = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
    return min(dist_seg_seg(a, b, corners[i], corners[(i + 1) % 4]) for i in range(4))


class FpGeom:
    """A footprint's courtyard box and pad offsets at orientation 0, for fast trial placement."""

    def __init__(self, fp):
        pos = fp.GetPosition()
        ox, oy = mm(pos.x), mm(pos.y)
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount():
            bb = cy.BBox()
        else:
            bb = fp.GetBoundingBox(False)
        self.box = Rect(mm(bb.GetLeft()) - ox, mm(bb.GetTop()) - oy, mm(bb.GetRight()) - ox, mm(bb.GetBottom()) - oy)
        self.pads = []                       # (number, dx, dy)
        for p in fp.Pads():
            pp = p.GetPosition()
            self.pads.append((p.GetNumber(), mm(pp.x) - ox, mm(pp.y) - oy))

    def box_at(self, x, y, rot):
        pts = [rot_xy(px, py, rot) for px, py in ((self.box.x0, self.box.y0), (self.box.x1, self.box.y1))]
        return Rect(x + pts[0][0], y + pts[0][1], x + pts[1][0], y + pts[1][1])

    def pads_at(self, x, y, rot):
        out = []
        for n, dx, dy in self.pads:
            rx, ry = rot_xy(dx, dy, rot)
            out.append((n, x + rx, y + ry))
        return out


def mark_dnp(board, design):
    """Parts the netlist marks 'not fitted' stay on the board but out of the BOM and placement file."""
    for ref, part in design.parts.items():
        if getattr(part, "dnp", False):
            fp = board.FindFootprintByReference(ref)
            if fp:
                fp.SetDNP(True)
                fp.SetExcludedFromPosFiles(True)
                fp.SetExcludedFromBOM(True)


class Layout:
    def __init__(self, design, width, height, corner=2.0, layers=2, out_dir=None, name=None):
        self.design = design
        self.name = name or design.name
        self.w, self.h, self.corner = width, height, corner
        self.layers = layers
        self.out_dir = out_dir or os.path.join(HERE, "out", self.name)
        os.makedirs(self.out_dir, exist_ok=True)
        self.pcb_path = os.path.join(self.out_dir, self.name + ".kicad_pcb")
        for ext in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            p = os.path.join(self.out_dir, self.name + ext)
            if os.path.exists(p):
                os.remove(p)
        self.board = pcbnew.NewBoard(self.pcb_path)
        self.board.SetCopperLayerCount(layers)
        self.board.SetEnabledLayers(self.board.GetEnabledLayers())
        self.nets = {}
        for net in sorted(design.nets()):
            if net is None:
                continue
            ni = pcbnew.NETINFO_ITEM(self.board, net)
            self.board.Add(ni)
            self.nets[net] = ni
        self.fps, self.geom, self.placed = {}, {}, {}
        for ref, part in design.parts.items():
            fp = kicadlib.load_footprint(part.footprint)
            fp.SetReference(ref)
            fp.SetValue(part.value)
            fp.SetPosition(V(0, 0))
            fp.SetOrientationDegrees(0)
            self.board.Add(fp)
            for pad in fp.Pads():
                pin = part.pins.get(pad.GetNumber())
                if pin and pin[1]:
                    pad.SetNet(self.nets[pin[1]])
            self.fps[ref] = fp
            self.geom[ref] = FpGeom(fp)
        mark_dnp(self.board, design)
        self.blocked = []          # Rects the placer must avoid (keep-outs, edge margin handled separately)
        self.regions = {}          # named placement regions
        self.board_rect = Rect(0, 0, width, height)
        self.notes = []

    @classmethod
    def open(cls, pcb_path, width, height, project):
        """A Layout around a board already on disk (for checking and exporting after hand edits)."""
        self = cls.__new__(cls)
        self.pcb_path = pcb_path
        self.out_dir = os.path.dirname(os.path.abspath(pcb_path))
        self.name = os.path.splitext(os.path.basename(pcb_path))[0]
        self.w, self.h = width, height
        self.board_rect = Rect(0, 0, width, height)
        self.design, self.geom, self.placed = None, {}, {}
        self.blocked, self.regions, self.notes = [], {}, []
        self._project = project
        self.board = pcbnew.LoadBoard(pcb_path)
        self.apply_net_classes()
        self.nets = {str(k): v for k, v in self.board.GetNetsByName().items()}
        self.fps = {fp.GetReference(): fp for fp in self.board.GetFootprints()}
        self.layers = self.board.GetCopperLayerCount()
        return self

    # ------------------------------------------------------------------ outline and graphics
    def outline(self):
        b, r, w, h = self.board, self.corner, self.w, self.h

        def seg(x1, y1, x2, y2):
            s = pcbnew.PCB_SHAPE(b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(V(x1, y1))
            s.SetEnd(V(x2, y2))
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetWidth(MM(0.1))
            b.Add(s)

        def arc(cx, cy, a0):
            s = pcbnew.PCB_SHAPE(b)
            s.SetShape(pcbnew.SHAPE_T_ARC)
            p = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in (a0, a0 + 45, a0 + 90)]
            s.SetArcGeometry(V(*p[0]), V(*p[1]), V(*p[2]))
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetWidth(MM(0.1))
            b.Add(s)
        seg(r, 0, w - r, 0)
        seg(w, r, w, h - r)
        seg(w - r, h, r, h)
        seg(0, h - r, 0, r)
        if r > 0:
            arc(w - r, r, 270)
            arc(w - r, h - r, 0)
            arc(r, h - r, 90)
            arc(r, r, 180)

    def text(self, s, x, y, size=1.0, layer=pcbnew.F_SilkS, bold=False, rot=0):
        t = pcbnew.PCB_TEXT(self.board)
        t.SetText(s)
        if layer in (pcbnew.B_SilkS, pcbnew.B_Fab, pcbnew.B_Cu):
            t.SetMirrored(True)             # reads the right way round from the back
        t.SetPosition(V(x, y))
        t.SetLayer(layer)
        t.SetTextSize(V(size, size))
        t.SetTextThickness(MM(max(0.15, size * 0.15)))
        t.SetBold(bold)
        if rot:
            t.SetTextAngleDegrees(rot)
        self.board.Add(t)
        return t

    def slot(self, x0, y0, x1, y1):
        """A non-plated routed slot (drawn on Edge.Cuts as a closed oval)."""
        w = min(abs(x1 - x0), abs(y1 - y0))
        s = pcbnew.PCB_SHAPE(self.board)
        s.SetShape(pcbnew.SHAPE_T_RECT)
        s.SetStart(V(x0, y0))
        s.SetEnd(V(x1, y1))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        self.board.Add(s)
        return w

    # ------------------------------------------------------------------ placement
    def place(self, ref, x, y, rot=0, lock=True, side="top"):
        """Put a part at (x, y), turned `rot` degrees; side="bottom" flips it onto the back (left to
        right, about its own centre), as KiCad's F key does."""
        fp = self.fps[ref]
        if fp.IsFlipped():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(rot)
        if side == "bottom":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            # a part on the back only takes room on the front where its through-hole pads are
            for p in fp.Pads():
                if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                    bb = p.GetBoundingBox()
                    self.blocked.append(Rect(mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())).grow(0.3))
            for z in fp.Zones():                   # and nothing goes in its keep-outs
                bb = z.Outline().BBox()
                self.blocked.append(Rect(mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())))
        fp.SetLocked(lock)
        self.placed[ref] = (x, y, rot)
        return fp

    def on_bottom(self, ref):
        return self.fps[ref].IsFlipped()

    def box(self, ref):
        if self.on_bottom(ref):
            fp = self.fps[ref]
            cy = fp.GetCourtyard(pcbnew.B_CrtYd)
            bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
            return Rect(mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
        x, y, r = self.placed[ref]
        return self.geom[ref].box_at(x, y, r)

    def pads_of(self, ref):
        """[(number, x, y)] of a placed part's pads."""
        if self.on_bottom(ref):
            return [(p.GetNumber(), mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in self.fps[ref].Pads()]
        x, y, r = self.placed[ref]
        return self.geom[ref].pads_at(x, y, r)

    def pad_xy(self, ref, num):
        """Absolute position of pad `num` (the first one with that number)."""
        for n, px, py in self.pads_of(ref):
            if n == str(num):
                return px, py
        raise KeyError(f"{ref} has no pad {num}")

    def net_of(self, ref, num):
        return self.design.parts[ref].pins[str(num)][1]

    def placed_pads_by_net(self):
        out = {}
        for ref in self.placed:
            part = self.design.parts[ref]
            for n, px, py in self.pads_of(ref):
                pin = part.pins.get(n)
                if pin and pin[1]:
                    out.setdefault(pin[1], []).append((px, py))
        return out

    def autoplace(self, refs, region, near=None, rotations=(0, 90), gap=0.3, step=0.25,
                  ignore_nets=("GND",), weight=None, edge=0.6, anchor_pad=None):
        """Greedy placement of `refs` (in order) inside `region` (Rect).

        Each part goes where the summed distance from its pads to already-placed pads of the same
        nets is smallest (ignore_nets are skipped: they go to planes). `near` = (x, y) or
        (ref, pad) adds an attraction to that point for every part; `anchor_pad` = {ref: (ref2, pad)}
        attracts a single part's nearest pad to a specific pad (decoupling capacitors).
        Courtyards (grown by gap/2 each) never overlap and stay `edge` mm inside the board.
        """
        region = region if isinstance(region, Rect) else self.regions[region]
        weight = weight or {}
        anchor_pad = anchor_pad or {}
        inner = Rect(self.board_rect.x0 + edge, self.board_rect.y0 + edge, self.board_rect.x1 - edge, self.board_rect.y1 - edge)
        for ref in refs:
            if ref in self.placed:
                continue
            g = self.geom[ref]
            part = self.design.parts[ref]
            pads_by_net = self.placed_pads_by_net()
            occupied = [self.box(r).grow(gap / 2) for r in self.placed if not self.on_bottom(r)] + self.blocked
            target = None
            if near is not None and not (isinstance(near[0], str) and near[0] not in self.placed):
                target = self.pad_xy(*near) if isinstance(near[0], str) else near
            ap = anchor_pad.get(ref)
            ap_xy = self.pad_xy(*ap) if ap and ap[0] in self.placed else None
            best = None
            nx = int((region.x1 - region.x0) / step) + 1
            ny = int((region.y1 - region.y0) / step) + 1
            for rot in rotations:
                b0 = g.box_at(0, 0, rot)
                offs = [(n, *rot_xy(dx, dy, rot)) for n, dx, dy in g.pads]
                for i in range(nx):
                    x = region.x0 + i * step - b0.x0
                    if x + b0.x1 > region.x1 + 1e-6:
                        break
                    for j in range(ny):
                        y = region.y0 + j * step - b0.y0
                        if y + b0.y1 > region.y1 + 1e-6:
                            break
                        bx = Rect(x + b0.x0, y + b0.y0, x + b0.x1, y + b0.y1)
                        if not bx.inside(inner):
                            continue
                        gb = bx.grow(gap / 2)
                        if any(gb.overlaps(o) for o in occupied):
                            continue
                        cost = 0.0
                        for n, dx, dy in offs:
                            pin = part.pins.get(n)
                            net = pin[1] if pin else None
                            if not net or net in ignore_nets:
                                continue
                            pts = pads_by_net.get(net)
                            if pts:
                                px, py = x + dx, y + dy
                                cost += weight.get(net, 1.0) * min(math.hypot(px - qx, py - qy) for qx, qy in pts)
                        if target is not None:
                            cost += 0.5 * math.hypot(bx.cx - target[0], bx.cy - target[1])
                        if ap_xy is not None:
                            cost += 3.0 * min(math.hypot(x + dx - ap_xy[0], y + dy - ap_xy[1]) for _, dx, dy in offs)
                        if best is None or cost < best[0]:
                            best = (cost, x, y, rot)
            if best is None:
                self.notes.append(f"no room for {ref} in {region}")
                continue
            self.place(ref, round(best[1], 3), round(best[2], 3), best[3], lock=False)

    def check_placement(self, gap=0.0):
        """Unplaced parts, courtyard overlaps and parts outside the board."""
        problems = []
        for ref in self.fps:
            if ref not in self.placed:
                problems.append(f"{ref} not placed")
        refs = list(self.placed)
        boxes = {r: self.box(r) for r in refs}
        for i, a in enumerate(refs):
            if not boxes[a].inside(self.board_rect) and not getattr(self, "overhang_ok", {}).get(a):
                problems.append(f"{a} courtyard leaves the board: {boxes[a]}")
            for b in refs[i + 1:]:
                if self.on_bottom(a) != self.on_bottom(b):
                    continue                     # one on each side: only their pads can clash (DRC)
                if boxes[a].grow(gap / 2).overlaps(boxes[b].grow(gap / 2)):
                    problems.append(f"courtyards overlap: {a} {b}")
        return problems

    # ------------------------------------------------------------------ copper
    def track(self, net, pts, width, layer=pcbnew.F_Cu, lock=True):
        items = []
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(V(x1, y1))
            t.SetEnd(V(x2, y2))
            t.SetWidth(MM(width))
            t.SetLayer(layer)
            t.SetNet(self.nets[net])
            t.SetLocked(lock)
            self.board.Add(t)
            items.append(t)
        return items

    def via(self, net, x, y, size=0.6, drill=0.3, lock=True):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(V(x, y))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetWidth(pcbnew.F_Cu, MM(size))
        v.SetDrill(MM(drill))
        v.SetNet(self.nets[net])
        v.SetLocked(lock)
        self.board.Add(v)
        return v

    def _poly(self, obj, pts):
        ol = obj.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(MM(x), MM(y))

    def zone(self, net, layers, pts, priority=0, clearance=None, min_width=0.25, solid=False,
             thermal_gap=0.3, spoke=0.5, name=None, remove_islands=True, tht_thermal=True):
        z = pcbnew.ZONE(self.board)
        ls = pcbnew.LSET()
        for l in (layers if isinstance(layers, (list, tuple)) else [layers]):
            ls.AddLayer(l)
        z.SetLayerSet(ls)
        if net:
            z.SetNet(self.nets[net])
        self._poly(z, pts)
        z.SetAssignedPriority(priority)
        if clearance is not None:
            z.SetLocalClearance(MM(clearance))
        z.SetMinThickness(MM(min_width))
        if solid:
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        elif tht_thermal:
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)   # SMD pads solid, through-hole relieved
        else:
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(MM(thermal_gap))
        z.SetThermalReliefSpokeWidth(MM(spoke))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS if remove_islands else pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        if name:
            z.SetZoneName(name)
        self.board.Add(z)
        return z

    def zone_rects(self, net, layer, rects, avoid=0.7, **kw):
        """A zone on one layer whose outline is the union of `rects` (x0, y0, x1, y1) minus every
        other net's pad grown by `avoid`, so the outline itself never covers foreign copper (the
        router treats the outline as copper). Notes any pad that ends up in a hole."""
        def poly(x0, y0, x1, y1):
            s = pcbnew.SHAPE_POLY_SET()
            s.NewOutline()
            for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                s.Append(MM(x), MM(y))
            return s
        shape = poly(*rects[0])
        for r in rects[1:]:
            shape.BooleanAdd(poly(*r))
        cut = pcbnew.SHAPE_POLY_SET()
        for fp in self.board.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() != net and p.IsOnLayer(layer):
                    p.TransformShapeToPolygon(cut, layer, MM(avoid), MM(0.01), pcbnew.ERROR_OUTSIDE)
        shape.BooleanSubtract(cut)
        shape.Simplify()
        for i in range(shape.OutlineCount()):
            if shape.HoleCount(i):
                self.notes.append(f"{net} zone on {self.board.GetLayerName(layer)} has {shape.HoleCount(i)} hole(s)"
                                  " around foreign pads")
        z = self.zone(net, layer, [(0, 0), (1, 0), (1, 1)], **kw)
        ol = z.Outline()
        ol.RemoveAllContours()
        ol.Append(shape)          # a copy: the zone must not own a Python-side polygon
        return z

    def keepout(self, layers, pts, tracks=True, vias=True, pour=True, pads=False, footprints=False, name=None):
        z = pcbnew.ZONE(self.board)
        z.SetIsRuleArea(True)
        ls = pcbnew.LSET()
        for l in (layers if isinstance(layers, (list, tuple)) else [layers]):
            ls.AddLayer(l)
        z.SetLayerSet(ls)
        self._poly(z, pts)
        z.SetDoNotAllowTracks(tracks)
        z.SetDoNotAllowVias(vias)
        z.SetDoNotAllowCopperPour(pour)
        z.SetDoNotAllowPads(pads)
        z.SetDoNotAllowFootprints(footprints)
        if name:
            z.SetZoneName(name)
        self.board.Add(z)
        return z

    def edge_keepout(self, width=0.6):
        """Keep tracks and vias `width` mm from every board edge (pours keep their own clearance)."""
        w, h, e = self.w, self.h, width
        ls = [pcbnew.F_Cu, pcbnew.B_Cu] + [pcbnew.In1_Cu + 2 * i for i in range(self.layers - 2)] if False else None
        layers = [l for l in self.copper_layers()]
        for pts in ([(0, 0), (w, 0), (w, e), (0, e)], [(0, h - e), (w, h - e), (w, h), (0, h)],
                    [(0, 0), (e, 0), (e, h), (0, h)], [(w - e, 0), (w, 0), (w, h), (w - e, h)]):
            self.keepout(layers, pts, tracks=True, vias=True, pour=False, name="edge")

    def copper_layers(self):
        out = [pcbnew.F_Cu]
        for i in range(1, self.layers - 1):
            out.append(self.board.GetLayerID(f"In{i}.Cu"))
        out.append(pcbnew.B_Cu)
        return out

    def fill(self):
        filler = pcbnew.ZONE_FILLER(self.board)
        filler.Fill(self.board.Zones())

    # ------------------------------------------------------------------ project and rules
    def save(self, net_classes, patterns, rules=None, severities=None, dru=None):
        """Save the board and write its .kicad_pro (net classes, rules) and .kicad_dru."""
        self._project = (net_classes, patterns, rules, severities, dru)
        self.apply_net_classes()
        pcbnew.SaveBoard(self.pcb_path, self.board)
        return self.write_project()

    def apply_net_classes(self, board=None):
        """Put the net classes and their patterns on the board in memory.

        KiCad keeps a project open for the whole Python session, so a board loaded again in the
        same run doesn't see a .kicad_pro edited on disk; without this, the DSN export (and so
        Freerouting) would route every net with the default width and clearance."""
        board = board or self.board
        net_classes, patterns = self._project[0], self._project[1]
        ns = board.GetDesignSettings().m_NetSettings
        for i, (name, c) in enumerate(net_classes.items()):
            if name == "Default":
                nc = ns.GetDefaultNetclass()
            else:
                nc = pcbnew.NETCLASS(name)
                nc.SetPriority(i)
            nc.SetClearance(MM(c["clearance"]))
            nc.SetTrackWidth(MM(c["track_width"]))
            nc.SetViaDiameter(MM(c["via_diameter"]))
            nc.SetViaDrill(MM(c["via_drill"]))
            if "diff_pair_width" in c:
                nc.SetDiffPairWidth(MM(c["diff_pair_width"]))
                nc.SetDiffPairGap(MM(c["diff_pair_gap"]))
            if name != "Default":
                ns.SetNetclass(name, nc)
        ns.ClearNetclassPatternAssignments()
        for pat, cls in patterns:
            ns.SetNetclassPatternAssignment(pat, cls)
        ns.ClearAllCaches()
        board.SynchronizeNetsAndNetClasses(True)

    def write_project(self):
        net_classes, patterns, rules, severities, dru = self._project
        pro = os.path.splitext(self.pcb_path)[0] + ".kicad_pro"
        with open(pro) as f:
            d = json.load(f)
        ns = d["net_settings"]
        default = dict(ns["classes"][0])
        classes = []
        for i, (cname, c) in enumerate(net_classes.items()):
            nc = dict(default)
            nc.update({"name": cname, "priority": 2147483647 if cname == "Default" else i})
            nc.update(c)
            classes.append(nc)
        ns["classes"] = classes
        ns["netclass_patterns"] = [{"netclass": c, "pattern": p} for p, c in patterns]
        ds = d["board"]["design_settings"]
        ds["rules"].update(rules or {})
        ds["rule_severities"].update(severities or {})
        with open(pro, "w") as f:
            json.dump(d, f, indent=2)
        if dru:
            shutil.copy(dru, os.path.splitext(self.pcb_path)[0] + ".kicad_dru")
        return self.pcb_path

    def reload(self):
        """Load the saved board again (with its net classes) and make it the working board."""
        self.board = pcbnew.LoadBoard(self.pcb_path)
        self.apply_net_classes()
        # everything that points into the board must now point into the new one
        self.nets = {n: self.board.FindNet(n) for n in self.nets}
        self.fps = {ref: self.board.FindFootprintByReference(ref) for ref in self.fps}
        return self.board
