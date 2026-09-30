"""Routing, checking and manufacturing outputs around KiCad 9 and Freerouting.

  export_dsn / run_freerouting / import_ses   the Freerouting round trip
  drc                                          kicad-cli DRC, parsed
  stitch_unconnected                           vias for pads a pour didn't reach
  render                                       PNG previews of the board
  export_fab                                   Gerbers, drill, CPL, zip for JLCPCB
"""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

import pcbnew

import pcbkit
from pcbkit import MM, V, Rect, dist_point_rect, dist_seg_rect, mm

HERE = os.path.dirname(os.path.abspath(__file__))
# 1.9.0 rather than 2.x: on these boards 2.1 leaves a hundred connections open where 1.9 leaves a
# handful, and 2.1 ignores its pass limit. 1.9 opens its window while it works (on Linux without a
# display it runs under xvfb-run).
FREEROUTING_VERSION = "1.9.0"
FREEROUTING_URL = (f"https://github.com/freerouting/freerouting/releases/download/v{FREEROUTING_VERSION}/"
                   f"freerouting-{FREEROUTING_VERSION}.jar")


# ---------------------------------------------------------------------- tools
def kicad_cli():
    if os.environ.get("KICAD_CLI"):
        return os.environ["KICAD_CLI"]
    exe = shutil.which("kicad-cli")
    if exe:
        return exe
    for p in (r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
              "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"):
        if os.path.exists(p):
            return p
    raise FileNotFoundError("kicad-cli not found; set KICAD_CLI or run from the KiCad 9 command prompt")


def freerouting_jar():
    if os.environ.get("FREEROUTING_JAR"):
        return os.environ["FREEROUTING_JAR"]
    jar = os.path.join(HERE, "tools", f"freerouting-{FREEROUTING_VERSION}.jar")
    if not os.path.exists(jar):
        os.makedirs(os.path.dirname(jar), exist_ok=True)
        print(f"  downloading Freerouting {FREEROUTING_VERSION}")
        with urllib.request.urlopen(FREEROUTING_URL, timeout=300) as r, open(jar, "wb") as f:
            shutil.copyfileobj(r, f)
    return jar


def java():
    exe = os.environ.get("JAVA") or shutil.which("java")
    if not exe:
        raise FileNotFoundError("Java 21 or later is needed for Freerouting (set JAVA to java.exe)")
    return exe


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0 and not kw.get("check_ok"):
        pass
    return r


# ---------------------------------------------------------------------- Freerouting
def export_dsn(board, path, power_layers=(), skip_nets=(), class_clearances=(), keepouts=()):
    """Write a Specctra DSN. Inner plane layers become 'power' so nothing routes on them,
    `skip_nets` are removed from the network so Freerouting leaves them to pours, and
    `class_clearances` [(class, class, mm)] become class-to-class rules (KiCad's DSN only carries
    one clearance per class; the .kicad_dru rules are invisible to Freerouting).
    `keepouts` [(layer, [(x0, y0, x1, y1), ...])] are areas the router stays out of, in the DSN
    only: Freerouting treats a zone on a signal layer as copper its own net can use, but routes
    other nets straight through it."""
    if not pcbnew.ExportSpecctraDSN(board, path):
        raise RuntimeError("DSN export failed")
    s = open(path, encoding="utf-8").read()
    if keepouts:
        extra = ""
        for layer, rects in keepouts:
            for x0, y0, x1, y1 in rects:
                pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
                coords = "  ".join(f"{x * 1000:.1f} {-y * 1000:.1f}" for x, y in pts)
                extra += f'    (keepout "" (polygon {layer} 0  {coords}))\n'
        if extra:
            i = s.find("    (keepout ")
            if i < 0:
                i = s.find("    (via ")
            if i < 0:
                raise RuntimeError("unexpected DSN layout: nowhere to put the keep-outs")
            s = s[:i] + extra + s[i:]
    if class_clearances:
        rules = "".join(f"    (class_class (classes {a} {b})\n      (rule (clearance {mm_ * 1000:.0f}))\n    )\n"
                        for a, b, mm_ in class_clearances)
        i = s.rfind("  )\n  (wiring")
        if i < 0:
            raise RuntimeError("unexpected DSN layout: no wiring section after the network")
        s = s[:i] + rules + s[i:]
    for layer in power_layers:
        s = re.sub(r"\(layer %s\s*\(type signal\)" % re.escape(layer), f"(layer {layer}\n      (type power)", s)
    for net in skip_nets:
        # keep the net (its fan-out vias refer to it) but give it no pins to join
        q = re.escape(net)
        s = re.sub(r"(\(net \"?%s\"?)\s*\(pins[^)]*\)" % q, r"\1", s)
    # Freerouting draws round vias and pads as octagons, whose flats sit a few hundredths of a mm
    # inside the circle: route with 0.03 mm more clearance than KiCad checks, so KiCad's DRC passes
    s = re.sub(r"\(clearance (\d+(?:\.\d+)?)", lambda m: f"(clearance {float(m.group(1)) + 30:g}", s)
    # KiCad already exports locked tracks and vias as (type fix), so Freerouting leaves them alone;
    # unlocked routing stays (type route) so a repair pass can move it. No vias in SMD pads.
    s = s.replace("  (structure\n", "  (structure\n    (control (via_at_smd off))\n", 1)
    open(path, "w", encoding="utf-8").write(s)
    return path


def run_freerouting(dsn, ses, passes=100, timeout=3600, threads=1, tag=""):
    """Run Freerouting on a DSN, write the SES. Returns (log, unrouted count or None)."""
    if os.path.exists(ses):
        os.remove(ses)
    cmd = [java(), "-jar", freerouting_jar(), "-de", dsn, "-do", ses, "-mp", str(passes),
           "-mt", str(threads), "-da"]                      # -da: no usage analytics
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a"] + cmd
    log_path = os.path.splitext(ses)[0] + f"_freerouting{tag}.log"
    with open(log_path, "w") as f:           # streamed, so a long run can be watched
        try:
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            f.write(f"\n*** stopped after {timeout} s ***\n")
    log = open(log_path, errors="replace").read()
    if not os.path.exists(ses):
        raise RuntimeError("Freerouting produced no session file; see " + log_path)
    return log, freerouting_unrouted(log)


def freerouting_unrouted(log):
    """Connections Freerouting left open (0 when it reported none)."""
    m = re.findall(r'"incomplete_count":\s*(\d+)', log)
    if m:
        return int(m[-1])
    passes = re.findall(r"Auto-router pass #\d+ .*", log)
    if not passes:
        return None
    m = re.search(r"\((\d+) unrouted\)", passes[-1])
    return int(m.group(1)) if m else 0


def import_ses(board, ses):
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise RuntimeError("SES import failed")


def rip_up(board, nets):
    """Delete the unlocked tracks and vias of `nets` so the next routing pass starts them afresh."""
    nets = set(nets)
    dead = [t for t in board.GetTracks() if t.GetNetname() in nets and not t.IsLocked()]
    for t in dead:
        board.Delete(t)          # Delete, not Remove: a removed via left to Python breaks SWIG
    return len(dead)


def rip_up_near(board, points, radius=4.0, keep_nets=()):
    """Delete the unlocked tracks and vias of any net within `radius` mm of `points`, so the next
    routing pass has room to finish the connections that ended there."""
    keep = set(keep_nets)
    dead = []
    for t in board.GetTracks():
        if t.IsLocked() or t.GetNetname() in keep:
            continue
        s, e = t.GetStart(), t.GetEnd()
        a, b = (mm(s.x), mm(s.y)), (mm(e.x), mm(e.y))
        if any(pcbkit.dist_seg_seg(p, p, a, b) < radius for p in points):
            dead.append(t)
    for t in dead:
        board.Delete(t)
    return len(dead)


ROUTING_ERRORS = {"clearance", "shorting_items", "tracks_crossing", "hole_clearance", "copper_edge_clearance"}


def routing_errors(d):
    """DRC errors that involve a track or via (the router's work), as DRC items."""
    out = []
    for v in d.get("violations", []):
        if v["severity"] == "error" and v["type"] in ROUTING_ERRORS and \
                any(i["description"].startswith(("Track", "Via")) for i in v["items"]):
            out.append(v)
    return out


def open_points(items):
    """(x, y) of every end of the DRC's unconnected items."""
    return [(it["pos"]["x"], it["pos"]["y"]) for u in items for it in u["items"]]


def nets_of(items):
    """Net names mentioned in DRC items."""
    pat = re.compile(r"\[([^\]]*)\]")
    return {m for u in items for it in u["items"] for m in pat.findall(it["description"])}


# ---------------------------------------------------------------------- DRC
def drc(pcb, out_json=None, schematic_parity=False):
    out_json = out_json or os.path.splitext(pcb)[0] + "_drc.json"
    cmd = [kicad_cli(), "pcb", "drc", "--format", "json", "--severity-all", "--units", "mm", "-o", out_json, pcb]
    subprocess.run(cmd, capture_output=True, text=True)
    with open(out_json) as f:
        d = json.load(f)
    return d


def summarize(d, show=12):
    from collections import Counter
    viol = d.get("violations", [])
    unc = d.get("unconnected_items", [])
    cnt = Counter((v["severity"], v["type"]) for v in viol)
    lines = [f"violations: {len(viol)}  unconnected: {len(unc)}"]
    for (sev, typ), n in sorted(cnt.items()):
        lines.append(f"  {sev:8s} {typ:28s} {n}")
    shown = 0
    for v in viol:
        if v["severity"] == "error" and shown < show:
            items = "; ".join(i["description"] for i in v["items"])
            lines.append(f"    - {v['type']}: {items}")
            shown += 1
    for u in unc[:show]:
        lines.append("    - unconnected: " + "; ".join(i["description"] for i in u["items"]))
    return "\n".join(lines)


# ---------------------------------------------------------------------- stitching
def _obstacles(board, exclude_net=None):
    """Copper on the front and back as rects/segments: (kind, geom, netname, layerset, clearance class)."""
    obs = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            r = Rect(mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
            obs.append(("pad", r, p.GetNetname(), p.GetLayerSet(), p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)))
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            r = mm(t.GetWidth(pcbnew.F_Cu)) / 2
            obs.append(("via", (mm(p.x), mm(p.y), r), t.GetNetname(), None, True))
        else:
            s, e = t.GetStart(), t.GetEnd()
            obs.append(("track", ((mm(s.x), mm(s.y)), (mm(e.x), mm(e.y)), mm(t.GetWidth()) / 2),
                        t.GetNetname(), t.GetLayer(), False))
    return obs


def _clear_of(obs, x, y, radius, net, layer_ids, clearance, hv_nets=(), hv_clear=0.6):
    for kind, g, onet, olayers, through in obs:
        if onet == net and kind != "via":
            continue
        c = hv_clear if (onet in hv_nets or net in hv_nets) and onet != net else clearance
        if kind == "pad":
            if onet == net:
                continue
            if dist_point_rect(x, y, g) < radius + c:
                return False
        elif kind == "via":
            vx, vy, vr = g
            need = 0.25 + radius + vr if onet == net else radius + vr + c
            if math.hypot(x - vx, y - vy) < need:
                return False
        else:
            (a, b, w) = g
            if dist_seg_rect(a, b, Rect(x - radius, y - radius, x + radius, y + radius)) < w + c - 1e-9 * 0 and onet != net:
                return False
    return True


def stitch_pads(layout, pads, net="GND", via=0.6, drill=0.3, clearance=0.25, hv_nets=(), keep_out=(),
                track_w=0.4, max_r=3.0, near=None):
    """Drop a via next to each (ref, pad) and join it with a short track, for pads a pour can't reach.
    Where a footprint repeats a pad number (a switch's two pins 2, a connector shell), `near`
    {(ref, pad): [(x, y), ...]} says which of them: the one nearest a position given."""
    board = layout.board
    added = 0
    for ref, num in pads:
        fp = board.FindFootprintByReference(ref)
        same = [p for p in fp.Pads() if p.GetNumber() == str(num) and p.GetNetname() == net]
        if not same:
            continue
        spots = (near or {}).get((ref, str(num)))
        if spots and len(same) > 1:
            same.sort(key=lambda p: min(math.hypot(mm(p.GetPosition().x) - x, mm(p.GetPosition().y) - y)
                                        for x, y in spots))
        pad = same[0]
        obs = _obstacles(board)
        pp = pad.GetPosition()
        px, py = mm(pp.x), mm(pp.y)
        bb = pad.GetBoundingBox()
        pr = Rect(mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
        # a fine-pitch pin gets a track no wider than itself, or it would crowd its neighbours
        ps = pad.GetSize()
        tw = max(0.2, min(track_w, round(0.75 * min(mm(ps.x), mm(ps.y)), 2)))
        best = None
        for r10 in range(int((max(pr.x1 - pr.x0, pr.y1 - pr.y0) / 2 + via / 2 + 0.2) * 10), int(max_r * 10) + 1, 2):
            r = r10 / 10
            for k in range(16):
                a = 2 * math.pi * k / 16
                x, y = px + r * math.cos(a), py + r * math.sin(a)
                if not layout.board_rect.grow(-0.8).contains(x, y):
                    continue
                if any(z.contains(x, y) for z in keep_out):
                    continue
                if not _clear_of(obs, x, y, via / 2, net, None, clearance, hv_nets):
                    continue
                if via_blocked(board, x, y, via / 2):
                    continue
                # the joining track must clear other copper too
                ok = True
                for kind, g, onet, olayers, through in obs:
                    if onet == net:
                        continue
                    c = 0.6 if onet in hv_nets else clearance
                    if kind == "pad" and dist_seg_rect((px, py), (x, y), g) < tw / 2 + c:
                        ok = False
                        break
                    if kind == "via" and pcbkit.dist_seg_seg((px, py), (x, y), (g[0], g[1]), (g[0], g[1])) < tw / 2 + g[2] + c:
                        ok = False
                        break
                    if kind == "track" and olayers == pcbnew.F_Cu and pcbkit.dist_seg_seg((px, py), (x, y), g[0], g[1]) < tw / 2 + g[2] + c:
                        ok = False
                        break
                if ok:
                    best = (x, y)
                    break
            if best:
                break
        if best is None:
            layout.notes.append(f"no room for a {net} via at {ref}.{num}")
            continue
        layout.via(net, round(best[0], 3), round(best[1], 3), via, drill)
        layer = pcbnew.F_Cu if pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        layout.track(net, [(px, py), (round(best[0], 3), round(best[1], 3))], tw, layer)
        added += 1
    return added


def pad_center(board, ref, num):
    """(x, y) of a footprint's pad, in mm."""
    fp = board.FindFootprintByReference(ref)
    for p in fp.Pads():
        if p.GetNumber() == str(num):
            return mm(p.GetPosition().x), mm(p.GetPosition().y)
    raise KeyError(f"{ref} has no pad {num}")


def unconnected_pad_positions(d, net):
    """{(ref, pad): [(x, y), ...]} for the pads of `net` in DRC 'unconnected' items, to tell apart
    pads that share a number."""
    out = {}
    pat = re.compile(r"Pad (\S+) \[([^\]]*)\] of (\S+)")
    for u in d.get("unconnected_items", []):
        for it in u["items"]:
            m = pat.search(it["description"])
            if m and m.group(2) == net:
                out.setdefault((m.group(3), m.group(1)), []).append((it["pos"]["x"], it["pos"]["y"]))
    return out


def unconnected_pads(d, net):
    """(ref, pad) pairs named in DRC 'unconnected' items for `net`."""
    out = set()
    pat = re.compile(r"Pad (\S+) \[([^\]]*)\] of (\S+)")
    for u in d.get("unconnected_items", []):
        for it in u["items"]:
            m = pat.search(it["description"])
            if m and m.group(2) == net:
                out.add((m.group(3), m.group(1)))
    return sorted(out)


# ---------------------------------------------------------------------- previews
def render(pcb, png, layers, width=1600, mirror=False):
    svg = os.path.splitext(png)[0] + ".svg"
    cmd = [kicad_cli(), "pcb", "export", "svg", "--mode-single", "--page-size-mode", "2", "--exclude-drawing-sheet",
           "--layers", ",".join(layers), "-o", svg, pcb]
    if mirror:
        cmd.insert(4, "--mirror")
    subprocess.run(cmd, capture_output=True, text=True)
    conv = shutil.which("rsvg-convert")
    if conv:
        s = open(svg, encoding="utf-8").read()
        # white background so the PNG reads in any viewer
        s = s.replace("<svg ", "<svg style=\"background:white\" ", 1)
        open(svg, "w", encoding="utf-8").write(s)
        subprocess.run([conv, "-w", str(width), "-b", "white", "-o", png, svg], capture_output=True)
        return png
    return svg


# ---------------------------------------------------------------------- manufacturing
def export_fab(pcb, out_dir, cpl_converter=None):
    """Gerbers + Excellon drill + position file for JLCPCB, zipped."""
    cli = kicad_cli()
    g = os.path.join(out_dir, "gerbers")
    if os.path.isdir(g):
        shutil.rmtree(g)
    os.makedirs(g)
    board = pcbnew.LoadBoard(pcb)
    n = board.GetCopperLayerCount()
    cu = ["F.Cu", "B.Cu"] + [f"In{i}.Cu" for i in range(1, n - 1)]
    layers = cu + ["F.Paste", "B.Paste", "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "Edge.Cuts"]
    r1 = subprocess.run([cli, "pcb", "export", "gerbers", "--layers", ",".join(layers), "--subtract-soldermask",
                         "--use-drill-file-origin", "-o", g + os.sep, pcb], capture_output=True, text=True)
    r2 = subprocess.run([cli, "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
                         "--generate-map", "--map-format", "gerberx2", "--drill-origin", "absolute",
                         "-o", g + os.sep, pcb], capture_output=True, text=True)
    name = os.path.splitext(os.path.basename(pcb))[0]
    zpath = os.path.join(out_dir, f"{name}-gerbers.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(g)):
            z.write(os.path.join(g, f), f)
    pos = os.path.join(out_dir, f"{name}-pos.csv")
    subprocess.run([cli, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "front",
                    "--exclude-dnp", "-o", pos, pcb], capture_output=True, text=True)
    cpl = None
    if cpl_converter and os.path.exists(pos):
        cpl = os.path.join(out_dir, f"{name}-cpl-jlc.csv")
        subprocess.run([sys.executable, cpl_converter, pos, cpl], capture_output=True, text=True)
    return {"zip": zpath, "pos": pos, "cpl": cpl, "log": r1.stdout + r1.stderr + r2.stdout + r2.stderr}


# ---------------------------------------------------------------------- clean-up and stitching
def remove_dangling(board, tol=0.01, pour_nets=("GND",)):
    """Tidy what the router left: zero-length and doubled-back segments, track ends that touch
    nothing, and vias of routed nets that join fewer than two layers. Locked items stay."""
    removed = 0
    # zero-length and duplicate segments (Freerouting sometimes writes a segment there and back)
    seen = set()
    segs = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    for t in sorted(segs, key=lambda t: not t.IsLocked()):        # locked ones claim their key first
        a = (round(mm(t.GetStart().x), 3), round(mm(t.GetStart().y), 3))
        b = (round(mm(t.GetEnd().x), 3), round(mm(t.GetEnd().y), 3))
        key = (t.GetNetname(), t.GetLayer(), min(a, b), max(a, b))
        if not t.IsLocked() and (a == b or key in seen):
            board.Delete(t)          # Delete, not Remove: a removed via left to Python breaks SWIG
            removed += 1
        else:
            seen.add(key)
    while True:
        removed_vias = _remove_dangling_vias(board, pour_nets)
        removed += removed_vias
        n = _remove_dangling_tracks(board, tol)
        removed += n
        if not n and not removed_vias:
            return removed


def _remove_dangling_vias(board, pour_nets):
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    dead = []
    for v in board.GetTracks():
        if v.GetClass() != "PCB_VIA" or v.IsLocked() or v.GetNetname() in pour_nets:
            continue
        vx, vy, vr = mm(v.GetPosition().x), mm(v.GetPosition().y), mm(v.GetWidth(pcbnew.F_Cu)) / 2
        layers = set()
        for t in tracks:
            if t.GetNetname() != v.GetNetname():
                continue
            s, e = t.GetStart(), t.GetEnd()
            if pcbkit.dist_seg_seg((vx, vy), (vx, vy), (mm(s.x), mm(s.y)), (mm(e.x), mm(e.y))) <= vr:
                layers.add(t.GetLayer())
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() == v.GetNetname() and p.HitTest(v.GetPosition()):
                    layers |= {l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if p.IsOnLayer(l)}
        if len(layers) < 2:
            dead.append(v)
    for v in dead:
        board.Delete(v)          # Delete, not Remove: a removed via left to Python breaks SWIG
    return len(dead)


def _remove_dangling_tracks(board, tol):
    removed = 0
    while True:
        tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
        vias = [(mm(v.GetPosition().x), mm(v.GetPosition().y), mm(v.GetWidth(pcbnew.F_Cu)) / 2, v.GetNetname())
                for v in board.GetTracks() if v.GetClass() == "PCB_VIA"]
        pads = []
        for fp in board.GetFootprints():
            for p in fp.Pads():
                bb = p.GetBoundingBox()
                pads.append((Rect(mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())),
                             p.GetNetname(), p.GetLayerSet()))
        ends = {}
        for t in tracks:
            for e in (t.GetStart(), t.GetEnd()):
                k = (round(mm(e.x), 2), round(mm(e.y), 2), t.GetLayer())
                ends[k] = ends.get(k, 0) + 1
        dead = []
        for t in tracks:
            if t.IsLocked():
                continue
            for e in (t.GetStart(), t.GetEnd()):
                x, y = mm(e.x), mm(e.y)
                k = (round(x, 2), round(y, 2), t.GetLayer())
                if ends[k] > 1:
                    continue
                if any(math.hypot(x - vx, y - vy) <= vr + tol and vn == t.GetNetname() for vx, vy, vr, vn in vias):
                    continue
                if any(n == t.GetNetname() and ls.Contains(t.GetLayer()) and r.grow(tol).contains(x, y) for r, n, ls in pads):
                    continue
                # an end resting on the middle of another segment of the same net counts as joined
                if any(o is not t and o.GetNetname() == t.GetNetname() and o.GetLayer() == t.GetLayer() and
                       pcbkit.dist_seg_seg((x, y), (x, y), (mm(o.GetStart().x), mm(o.GetStart().y)),
                                           (mm(o.GetEnd().x), mm(o.GetEnd().y))) < mm(o.GetWidth()) / 2 for o in tracks):
                    continue
                dead.append(t)
                break
        if not dead:
            return removed
        for t in dead:
            board.Delete(t)          # Delete, not Remove: a removed via left to Python breaks SWIG
        removed += len(dead)


def via_blocked(board, x, y, r):
    """True if a via at (x, y) would sit in a rule area that forbids vias."""
    pts = [V(x, y)] + [V(x + r * math.cos(a * math.pi / 4), y + r * math.sin(a * math.pi / 4)) for a in range(8)]
    zones = list(board.Zones()) + [z for fp in board.GetFootprints() for z in fp.Zones()]
    for z in zones:
        if z.GetIsRuleArea() and z.GetDoNotAllowVias():
            ol = z.Outline()
            if any(ol.Contains(p) for p in pts):
                return True
    return False


def _copper_clear(obs, x, y, r, net, clearance, hv_nets=(), hv_clear=0.6):
    for kind, g, onet, olayers, through in obs:
        c = hv_clear if (onet in hv_nets) else clearance
        if kind == "pad":
            if onet == net and not through:
                continue
            if dist_point_rect(x, y, g) < r + (0.3 if onet == net else c):
                return False
        elif kind == "via":
            vx, vy, vr = g
            if math.hypot(x - vx, y - vy) < r + vr + (0.3 if onet == net else c):
                return False
        else:
            a, b, w = g
            if onet != net and pcbkit.dist_seg_seg((x, y), (x, y), a, b) < r + w + c:
                return False
    return True


def prune_from_drc(board, d, nets, max_stub=1.0):
    """Remove what the final DRC finds hanging: the router's crumbs (unlocked track stubs shorter
    than `max_stub` mm with an unconnected end; their other end stays joined, so nothing opens)
    and stitching vias no pour reached. Returns (stubs, vias) removed."""
    ids = set()
    for v in d.get("violations", []):
        if v["type"] == "track_dangling":
            for it in v["items"]:
                m = re.search(r"length ([\d.]+) mm", it["description"])
                if it["description"].startswith("Track") and m and float(m.group(1)) < max_stub:
                    ids.add(it.get("uuid"))
    dead = [t for t in board.GetTracks()
            if t.GetClass() == "PCB_TRACK" and not t.IsLocked() and t.m_Uuid.AsString() in ids]
    for t in dead:
        board.Delete(t)
    return len(dead), remove_lone_vias(board, d, nets)


def remove_lone_vias(board, d, nets):
    """Delete unlocked vias of `nets` that DRC finds joined to nothing (dangling, or an island of
    their own) and that carry no track: stitching vias a pour didn't reach."""
    spots = []
    for v in d.get("violations", []):
        if v["type"] == "via_dangling":
            spots += [(it["pos"]["x"], it["pos"]["y"]) for it in v["items"] if it["description"].startswith("Via")]
    for u in d.get("unconnected_items", []):
        spots += [(it["pos"]["x"], it["pos"]["y"]) for it in u["items"] if it["description"].startswith("Via")]
    ends = set()
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA":
            ends.add((round(mm(t.GetStart().x), 2), round(mm(t.GetStart().y), 2)))
            ends.add((round(mm(t.GetEnd().x), 2), round(mm(t.GetEnd().y), 2)))
    dead = []
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA" or t.IsLocked() or t.GetNetname() not in nets:
            continue
        x, y = mm(t.GetPosition().x), mm(t.GetPosition().y)
        if any(abs(x - sx) < 0.01 and abs(y - sy) < 0.01 for sx, sy in spots) and (round(x, 2), round(y, 2)) not in ends:
            dead.append(t)
    for t in dead:
        board.Delete(t)
    return len(dead)


def stitch_grid(layout, net="GND", pitch=4.0, margin=1.2, via=0.6, drill=0.3, exclude=(), hv_nets=(), clearance=0.25):
    """Vias on a grid wherever there's room, tying the pours on every layer together."""
    board = layout.board
    obs = _obstacles(board)
    n = 0
    y = margin
    while y <= layout.h - margin:
        x = margin
        while x <= layout.w - margin:
            if (not any(r.contains(x, y) for r in exclude) and _copper_clear(obs, x, y, via / 2, net, clearance, hv_nets)
                    and not via_blocked(board, x, y, via / 2)):
                layout.via(net, round(x, 3), round(y, 3), via, drill, lock=False)
                obs.append(("via", (x, y, via / 2), net, None, True))
                n += 1
            x += pitch
        y += pitch
    return n


# ---------------------------------------------------------------------- silkscreen
def place_labels(board, size=0.8, keep_clear=(), board_rect=None):
    """Move each reference to a free spot beside its part; parts with no room get their reference
    on the fab layer only (it still prints on the assembly drawing)."""
    pads = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            pads.append(Rect(mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())))
    taken = []
    for d in board.GetDrawings():            # board text already on the silkscreen (labels)
        if d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS:
            tb = d.GetBoundingBox()
            taken.append(Rect(mm(tb.GetLeft()), mm(tb.GetTop()), mm(tb.GetRight()), mm(tb.GetBottom())).grow(0.15))
    moved = hidden = 0
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        if fp.IsFlipped():
            continue                    # parts on the back keep their own reference text
        ref = fp.Reference()
        if fp.GetReference().startswith(("FID", "H", "TP", "NT")):
            ref.SetVisible(False)
            continue
        ref.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
        ref.SetTextThickness(MM(0.15))
        ref.SetKeepUpright(True)
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
        box = Rect(mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom()))
        cands = []
        for ang in (0, 90):
            cands += [(box.cx, box.y0 - 0.2 - size / 2, ang), (box.cx, box.y1 + 0.2 + size / 2, ang),
                      (box.x0 - 0.2 - size / 2, box.cy, ang), (box.x1 + 0.2 + size / 2, box.cy, ang),
                      (box.cx, box.cy, ang)]
        placed = False
        for x, y, ang in cands:
            ref.SetTextAngleDegrees(ang)
            ref.SetPosition(pcbkit.V(x, y))
            tb = ref.GetBoundingBox()
            r = Rect(mm(tb.GetLeft()), mm(tb.GetTop()), mm(tb.GetRight()), mm(tb.GetBottom())).grow(0.15)
            if board_rect and not r.inside(board_rect.grow(-0.3)):
                continue
            if any(r.overlaps(p) for p in pads) or any(r.overlaps(t) for t in taken) or any(r.overlaps(k) for k in keep_clear):
                continue
            taken.append(r)
            placed = True
            moved += 1
            break
        if not placed:
            ref.SetLayer(pcbnew.F_Fab)
            hidden += 1
    return moved, hidden


def _pour_clusters(board, net, frags):
    """Which of `frags` [(layer, polys, index)] are joined to the main pours: the biggest fragment
    on each layer, and everything tied to one through vias, pads and tracks of `net`. Returns the
    set of joined fragment indices and a function that ties a new via in."""
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    def inside(k, x, y):
        f = frags[k]
        return f[1].Contains(V(x, y), f[2])

    def tie_point(item, x, y, layer=None):
        for k, f in enumerate(frags):
            if (layer is None or f[0] == layer) and inside(k, x, y):
                union(item, ("f", k))

    vias, ends = [], []
    for t in board.GetTracks():
        if t.GetNetname() != net:
            continue
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            vias.append((mm(p.x), mm(p.y), mm(t.GetWidth(pcbnew.F_Cu)) / 2))
            tie_point(("v", len(vias) - 1), mm(p.x), mm(p.y))
        else:
            item = ("t", len(ends))
            for q in (t.GetStart(), t.GetEnd()):
                ends.append((item, mm(q.x), mm(q.y), t.GetLayer()))
                tie_point(item, mm(q.x), mm(q.y), t.GetLayer())
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != net:
                continue
            item = ("p", p.m_Uuid.AsString())      # pads sharing a number aren't joined inside the part
            c = p.GetPosition()
            through = p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            for k, f in enumerate(frags):
                if (through or p.IsOnLayer(f[0])) and inside(k, mm(c.x), mm(c.y)):
                    union(item, ("f", k))
            for it, x, y, layer in ends:
                if p.IsOnLayer(layer) and p.HitTest(V(x, y)):
                    union(item, it)
    for it, x, y, layer in ends:                       # tracks meeting tracks and vias
        for j, (vx, vy, vr) in enumerate(vias):
            if math.hypot(x - vx, y - vy) <= vr:
                union(it, ("v", j))
        for it2, x2, y2, layer2 in ends:
            if layer2 == layer and it2 != it and abs(x - x2) < 0.01 and abs(y - y2) < 0.01:
                union(it, it2)
    roots = {}
    for k, f in enumerate(frags):
        a = pcbnew.SHAPE_POLY_SET(f[1].Outline(f[2])).Area()
        if f[0] not in roots or a > roots[f[0]][1]:
            roots[f[0]] = (k, a)
    for k, _ in roots.values():
        union(("f", k), "main")

    def joined():
        m = find("main")
        return {k for k in range(len(frags)) if find(("f", k)) == m}

    def add_via(x, y):
        vias.append((x, y, 0.3))
        tie_point(("v", len(vias) - 1), x, y)

    return joined, add_via


def stitch_islands(layout, net="GND", via=0.6, drill=0.3, clearance=0.25, step=0.2, exclude=(), hv_nets=()):
    """Give every filled fragment of `net`'s pours that isn't joined to the main pours a via into
    one that is, on another layer, so no fragment floats. Joined means tied to the biggest
    fragment of a layer through vias, pads and tracks: two islands with a via between them, or
    a connector shell's pad and the fragments around it, are still an island together."""
    board = layout.board
    obs = _obstacles(board)
    frags = []
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() != net:
            continue
        for layer in z.GetLayerSet().Seq():
            polys = z.GetFilledPolysList(layer)
            for i in range(polys.OutlineCount()):
                frags.append((layer, polys, i))
    joined, add_via = _pour_clusters(board, net, frags)

    added = 0
    r_in = 0.2          # the via only has to land on the fragment; the refill joins them
    ring = [(0, 0)] + [(r_in * math.cos(a * math.pi / 4), r_in * math.sin(a * math.pi / 4)) for a in range(8)]
    for k, f in enumerate(frags):
        layer, polys, i = f
        ok = joined()
        if k in ok:
            continue
        anchored = [frags[j] for j in ok if frags[j][0] != layer]
        bb = polys.Outline(i).BBox()
        x0, y0, x1, y1 = mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())
        done = False
        yy = y0 + step / 2
        while yy < y1 and not done:
            xx = x0 + step / 2
            while xx < x1 and not done:
                if (not any(r.contains(xx, yy) for r in exclude)
                        and all(polys.Contains(V(xx + dx, yy + dy), i) for dx, dy in ring)
                        and any(all(g[1].Contains(V(xx + dx, yy + dy), g[2]) for dx, dy in ring) for g in anchored)
                        and _copper_clear(obs, xx, yy, via / 2, net, clearance, hv_nets)
                        and not via_blocked(board, xx, yy, via / 2)):
                    layout.via(net, round(xx, 3), round(yy, 3), via, drill, lock=False)
                    obs.append(("via", (xx, yy, via / 2), net, None, True))
                    add_via(xx, yy)
                    added += 1
                    done = True
                xx += step
            yy += step
        if not done:
            # too small for a via of its own: fan out the SMD pads it holds instead
            smd = []
            for fp in board.GetFootprints():
                for p in fp.Pads():
                    if (p.GetNetname() == net and p.IsOnLayer(layer) and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                            and polys.Contains(p.GetPosition(), i)):
                        smd.append((fp.GetReference(), p.GetNumber()))
            if smd:
                n = stitch_pads(layout, smd, net=net, via=via, drill=drill, hv_nets=hv_nets, keep_out=exclude)
                if n:
                    added += n
                    obs = _obstacles(board)
                    # the pads' new vias and tracks tie this fragment in
                    joined, add_via = _pour_clusters(board, net, frags)
            # a fragment with no pad and no room for a via joins nothing: the final fill drops it
    return added


def signal_unconnected(d, skip=("GND",)):
    """Unconnected DRC items that belong to routed (non-pour) nets."""
    out = []
    pat = re.compile(r"\[([^\]]*)\]")
    for u in d.get("unconnected_items", []):
        nets = {m for it in u["items"] for m in pat.findall(it["description"])}
        if nets and not nets & set(skip):
            out.append(u)
    return out


def fanout(layout, net="GND", skip_refs=(), skip_pads=(), hv_nets=(), keep_out=(), via=0.6, drill=0.3, track_w=0.4):
    """Before routing: give every SMD pad of `net` its own via to the plane or the far-side pour,
    so the router works around them and no pad ends up walled in."""
    pads = []
    for fp in layout.board.GetFootprints():
        ref = fp.GetReference()
        if ref in skip_refs:
            continue
        for p in fp.Pads():
            if (p.GetNetname() == net and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                    and (ref, p.GetNumber()) not in skip_pads):
                pads.append((ref, p.GetNumber()))
    # one via per (ref, pad number): footprints repeat a number for split pads
    pads = sorted(set(pads))
    return stitch_pads(layout, pads, net=net, via=via, drill=drill, hv_nets=hv_nets, keep_out=keep_out,
                       track_w=track_w, max_r=2.5)
