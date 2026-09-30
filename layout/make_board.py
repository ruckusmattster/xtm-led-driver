"""Generate a routed, checked board and its manufacturing files.

    python make_board.py board_b                  # place, route, pour, check, export
    python make_board.py board_a --stage place    # placement only, with a preview image
    python make_board.py board_a --stage route    # everything except the fabrication files
    python make_board.py board_a --stage export   # after editing the board in KiCad: refill,
                                                  # check and export again, without touching it

Run it with the Python that ships with KiCad 9 (on Windows: run_layout.bat, or the "KiCad 9.0
Command Prompt"). Freerouting needs Java 21 or later on the PATH (or set JAVA). Outputs go to
layout/out/<board>/, with a log of the run. The exit status is 0 only when DRC reports no errors
and nothing unconnected.
"""
import argparse
import importlib
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "design"))

import pcbnew  # noqa: E402

import pcbkit  # noqa: E402
import route  # noqa: E402

SEVERITIES = {
    # footprints come straight from the library files; KiCad can't compare them with a library
    # table in a headless run, so this check would only list every part
    "lib_footprint_issues": "ignore",
    "lib_footprint_mismatch": "ignore",
    "silk_overlap": "warning",
    "silk_over_copper": "warning",
    "silk_edge_clearance": "warning",
}
# JLCPCB's standard capabilities with some margin
RULES = {"min_copper_edge_clearance": 0.5, "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25,
         "min_through_hole_diameter": 0.2, "min_via_diameter": 0.5, "min_via_annular_width": 0.13,
         "min_track_width": 0.15, "min_clearance": 0.15, "min_resolved_spokes": 1}
CPL_CONVERTER = os.path.join(HERE, "..", "design", "kicad_pos_to_jlc_cpl.py")

_log_file = None


def log(msg):
    print(msg, flush=True)
    if _log_file:
        _log_file.write(msg + "\n")
        _log_file.flush()


def preview(pcb, out_dir, name, layer_sets):
    out = []
    for i, layers in enumerate(layer_sets):
        tag = "_".join(l.replace(".", "") for l in layers[:2])
        out.append(route.render(pcb, os.path.join(out_dir, f"{name}-{i + 1}-{tag}.png"), layers))
    return out


def check_java():
    """Freerouting 2.1 needs Java 21. Say so plainly instead of failing inside the router."""
    try:
        r = subprocess.run([route.java(), "-version"], capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, OSError) as e:
        raise SystemExit(f"Java not found ({e}). Install a Java 21 runtime (see README.md) or set JAVA.")
    m = re.search(r'version "(\d+)', r.stderr + r.stdout)
    if m and int(m.group(1)) < 21:
        raise SystemExit(f"Java {m.group(1)} found; Freerouting needs Java 21 or later (see README.md).")


def finish_and_export(L, spec, pcb, t0, export=True):
    """Pours, stitching, labels, final DRC, previews and (optionally) the fabrication files."""
    pour_nets = spec.get("pour_nets", ["GND"])
    excl = spec.get("via_exclude", {})
    hv = spec.get("hv_nets", ())
    pv = spec.get("pad_via", (0.6, 0.3))
    # fill keeping the islands, so the ones walled in by tracks show up and get a via of their own
    # instead of vanishing; what still has no via afterwards goes with the final fill
    pours = [z for z in L.board.Zones() if not z.GetIsRuleArea() and z.GetNetname() in pour_nets]
    modes = {z.m_Uuid.AsString(): z.GetIslandRemovalMode() for z in pours}
    for z in pours:
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    L.fill()
    for _ in range(4):
        n = sum(route.stitch_islands(L, net=net, exclude=excl.get(net, ()), hv_nets=hv) for net in pour_nets)
        if not n:
            break
        log(f"  {n} vias added to pour fragments")
        L.fill()
    for z in pours:
        z.SetIslandRemovalMode(modes[z.m_Uuid.AsString()])
    L.fill()
    pcbnew.SaveBoard(pcb, L.board)
    L.write_project()
    for _ in range(3):
        d = route.drc(pcb)
        stray = [(r, p, net) for net in pour_nets for r, p in route.unconnected_pads(d, net)]
        if not stray:
            break
        n = 0
        for net in {s[2] for s in stray}:
            n += route.stitch_pads(L, [(r, p) for r, p, nn in stray if nn == net], net=net, hv_nets=hv,
                                   via=pv[0], drill=pv[1], keep_out=excl.get(net, ()),
                                   near=route.unconnected_pad_positions(d, net))
        log(f"  stitched {n} pad(s) the pours missed")
        if not n:
            break
        L.fill()
        pcbnew.SaveBoard(pcb, L.board)
        L.write_project()

    # what's left hanging: the router's crumbs (stubs a few hundredths of a mm long) and stitching
    # vias the pours ended up missing (in a corner, a sliver)
    for _ in range(3):
        d = route.drc(pcb)
        stubs, vias = route.prune_from_drc(L.board, d, pour_nets)
        if not stubs and not vias:
            break
        log(f"  removed {stubs} dangling stub(s) and {vias} stitching via(s) no pour reached")
        L.fill()
        pcbnew.SaveBoard(pcb, L.board)
        L.write_project()

    d = route.drc(pcb)
    log(route.summarize(d))
    for note in dict.fromkeys(L.notes):
        log("  note: " + note)
    for p in preview(pcb, L.out_dir, L.name, spec["render_layers"]):
        log("  preview " + p)
    if export:
        fab = route.export_fab(pcb, L.out_dir, CPL_CONVERTER)
        log(f"  fabrication files: {fab['zip']}; CPL {fab['cpl']}")
    errors = [v for v in d["violations"] if v["severity"] == "error"]
    log(f"done in {time.time() - t0:.0f} s: {len(errors)} DRC errors, {len(d['unconnected_items'])} unconnected")
    return 0 if not errors and not d["unconnected_items"] else 1


def main():
    global _log_file
    ap = argparse.ArgumentParser()
    ap.add_argument("board", choices=["board_a", "board_b"])
    ap.add_argument("--stage", choices=["place", "route", "all", "export"], default="all")
    ap.add_argument("--passes", type=int, default=100, help="Freerouting passes per attempt")
    ap.add_argument("--attempts", type=int, default=0,
                    help="routing attempts before giving up (default: the board's own setting)")
    ap.add_argument("--timeout", type=int, default=0,
                    help="seconds per Freerouting run (default: the board's own setting)")
    args = ap.parse_args()
    mod = importlib.import_module(args.board + "_layout")
    spec = mod.SPEC
    timeout = args.timeout or spec.get("route_timeout", 300)
    args.attempts = args.attempts or spec.get("attempts", 4)
    t0 = time.time()
    out_dir = os.path.join(HERE, "out", args.board)
    os.makedirs(out_dir, exist_ok=True)
    if args.stage != "export":
        # a fresh run: last run's router logs and previews would only confuse
        for f in os.listdir(out_dir):
            if re.search(r"(_freerouting.*\.log|\.png|\.svg)$", f):
                os.remove(os.path.join(out_dir, f))
    _log_file = open(os.path.join(out_dir, f"{args.board}_run.log"), "a" if args.stage == "export" else "w")
    log(f"{args.board}: stage {args.stage}, KiCad {pcbnew.Version()}, {time.strftime('%Y-%m-%d %H:%M')}")

    # ---- export only: the board as it is on disk (after hand edits in KiCad)
    dru = os.path.join(HERE, "..", "hardware", spec["dru"]) if spec.get("dru") else None
    project = (spec["net_classes"], spec["patterns"], RULES, SEVERITIES, dru)
    if args.stage == "export":
        pcb = os.path.join(out_dir, args.board + ".kicad_pcb")
        if not os.path.exists(pcb):
            raise SystemExit(f"{pcb} doesn't exist yet: run the 'all' stage first")
        L = pcbkit.Layout.open(pcb, mod.W, mod.H, project)
        pcbkit.mark_dnp(L.board, importlib.import_module(args.board).build())
        return finish_and_export(L, spec, pcb, t0)

    if args.stage != "place":
        check_java()

    # ---- placement
    L = spec["build"]()
    L.edge_keepout()
    problems = L.check_placement()
    for p in problems:
        log("  placement: " + p)
    for note in L.notes:
        log("  note: " + note)
    pcb = L.save(*project)
    log(f"placed {len(L.placed)} parts in {time.time() - t0:.0f} s")
    if args.stage == "place" or problems:
        for p in preview(pcb, L.out_dir, L.name, [["F.Cu", "F.SilkS", "F.Fab", "F.CrtYd", "Edge.Cuts"]]):
            log("  preview " + p)
        return 1 if problems else 0

    # ---- copper drawn before routing: fan-out vias for plane nets, hand-drawn power copper
    board = L.reload()
    for pre in spec.get("prerouted", []):
        pre(L)
    for fo in spec.get("fanout", []):
        log(f"  {route.fanout(L, **fo)} fan-out vias on {fo.get('net', 'GND')}")
    pcbnew.SaveBoard(pcb, board)
    L.write_project()

    # ---- routing: Freerouting, then clean-up; open nets are ripped up and routed again
    dsn = os.path.join(L.out_dir, L.name + ".dsn")
    ses = os.path.join(L.out_dir, L.name + ".ses")
    skip = spec.get("skip_nets", ())
    pour_nets = spec.get("pour_nets", ["GND"])
    plane_nets = spec.get("plane_nets", ())
    pv = spec.get("pad_via", (0.6, 0.3))
    open_items, clashes, strays = [], [], []
    best = None
    best_dir = os.path.join(L.out_dir, "best-attempt")
    os.makedirs(best_dir, exist_ok=True)
    best_pcb = os.path.join(best_dir, L.name + ".kicad_pcb")
    # Freerouting doesn't give the same result twice: a board whose open connections come from a
    # bad start (Board B's USB-C pins) does better starting over every few attempts than repairing
    restart = spec.get("restart_every", 0)
    pre_pcb = os.path.join(best_dir, "unrouted.kicad_pcb")
    pcbnew.SaveBoard(pre_pcb, board)
    for attempt in range(args.attempts):
        if restart and attempt and attempt % restart == 0:
            shutil.copy(pre_pcb, pcb)
            board = L.reload()
            log("  starting again from the unrouted board")
        route.export_dsn(board, dsn, power_layers=spec.get("power_layers", ()), skip_nets=skip,
                         class_clearances=spec.get("class_clearances", ()),
                         keepouts=getattr(L, "router_keepouts", ()))
        log(f"routing with Freerouting (attempt {attempt + 1} of {args.attempts}, up to {timeout} s) ...")
        _, left = route.run_freerouting(dsn, ses, passes=args.passes, timeout=timeout, tag=f"-{attempt + 1}")
        route.import_ses(board, ses)
        stubs = route.remove_dangling(board, pour_nets=pour_nets)
        L.fill()                  # planes drawn before routing (if any) have to be filled to count
        pcbnew.SaveBoard(pcb, board)
        L.write_project()
        # pour nets don't count as open connections here: the pours after routing reach most of
        # their pads. But a plane net's pad with no via of its own (the router gave up on it) is
        # a problem: it gets a via now, clearing the router's tracks around it if needed.
        d = route.drc(pcb)
        open_items = route.signal_unconnected(d, set(skip) | set(pour_nets))
        clashes = route.routing_errors(d)
        strays = [(r, p, net) for net in plane_nets for r, p in route.unconnected_pads(d, net)]
        log(f"  routed at {time.time() - t0:.0f} s: {stubs} stubs removed, {len(open_items)} connections open, "
            f"{len(clashes)} clearance errors, {len(strays)} plane pads without a via")
        score = 10 * (len(open_items) + len(clashes)) + len(strays)     # strays are easy to fix later
        if best is None or score < best[0]:
            best = (score, attempt)
            if score:
                pcbnew.SaveBoard(best_pcb, board)
        if not score or attempt == args.attempts - 1:
            break
        if restart and (attempt + 1) % restart == 0:
            continue                                  # the next attempt starts over anyway
        keep = spec.get("keep_nets", ())
        # a via beside every stray plane pad; where there's no room, clear the tracks around the pad
        if strays:
            crowded = []
            for net in {s[2] for s in strays}:
                pads = [(r, p) for r, p, nn in strays if nn == net]
                before = len(L.notes)
                route.stitch_pads(L, pads, net=net, hv_nets=spec.get("hv_nets", ()), via=pv[0], drill=pv[1],
                                  keep_out=spec.get("via_exclude", {}).get(net, ()),
                                  near=route.unconnected_pad_positions(d, net))
                crowded += [(r, p, net) for r, p in pads
                            if any(f" at {r}.{p}" in n for n in L.notes[before:])]
                del L.notes[before:]
            if crowded:
                spots = [route.pad_center(board, r, p) for r, p, _ in crowded]
                n = route.rip_up_near(board, spots, 1.2, keep_nets=keep)
                for net in {c[2] for c in crowded}:
                    route.stitch_pads(L, [(r, p) for r, p, nn in crowded if nn == net], net=net,
                                      hv_nets=spec.get("hv_nets", ()), via=pv[0], drill=pv[1],
                                      keep_out=spec.get("via_exclude", {}).get(net, ()),
                                      near=route.unconnected_pad_positions(d, net))
                log(f"  gave {len(strays)} plane pads a via ({len(crowded)} after clearing {n} segments around them)")
            else:
                log(f"  gave {len(strays)} plane pads a via")
        # clear around every open end and every clash (all but the pre-drawn, locked copper) and
        # start small open nets again from nothing; the rest stays, and the router may push it aside
        if clashes:
            n = route.rip_up_near(board, route.open_points(clashes), 1.0, keep_nets=keep)
            log(f"  cleared {n} segments at the clearance errors")
        if open_items:
            nets = route.nets_of(open_items) - set(skip)
            count = {n: 0 for n in nets}
            for fp in board.GetFootprints():
                for p in fp.Pads():
                    if p.GetNetname() in count:
                        count[p.GetNetname()] += 1
            small = {n for n, k in count.items() if k <= 8}
            # a wider circle each time: what blocks a connection is often further out than its ends
            radius = 2.0 + (attempt % restart if restart else attempt)
            near = route.rip_up_near(board, route.open_points(open_items), radius, keep_nets=keep)
            whole = route.rip_up(board, small)
            log(f"  cleared {near} segments within {radius:g} mm of the open ends and {whole} of "
                f"{', '.join(sorted(small)) or 'no net'} for another attempt")
    if open_items or clashes or strays:
        if best and best[0] < 10 * (len(open_items) + len(clashes)) + len(strays) and os.path.exists(best_pcb):
            # the last attempt made things worse: go back to the best one
            shutil.copy(best_pcb, pcb)
            board = L.reload()
            L.fill()
            d = route.drc(pcb)
            open_items = route.signal_unconnected(d, set(skip) | set(pour_nets))
            clashes = route.routing_errors(d)
            log(f"  kept attempt {best[1] + 1}, with {len(open_items)} connections open and "
                f"{len(clashes)} clearance errors")
        for v in clashes:
            log("    - " + v["type"] + ": " + "; ".join(i["description"] for i in v["items"]))
    if open_items:
        log(f"  {len(open_items)} connection(s) still open after {args.attempts} attempts; they show as "
            "ratsnest lines in KiCad, to route by hand (see README.md):")
        for u in open_items:
            log("    - " + "; ".join(i["description"] for i in u["items"]))
    shutil.rmtree(best_dir, ignore_errors=True)

    # ---- stitching vias and pours, silkscreen, checks and outputs
    for st in spec.get("stitch_grid", []):
        log(f"  {route.stitch_grid(L, **st)} stitching vias on {st.get('net', 'GND')}")
    spec["finish"](L)
    if spec.get("labels"):
        spec["labels"](L)
    moved, hidden = route.place_labels(L.board, board_rect=L.board_rect)
    log(f"  references: {moved} on the silkscreen, {hidden} on the fab layer only (no room)")
    return finish_and_export(L, spec, pcb, t0, export=args.stage == "all")


if __name__ == "__main__":
    sys.exit(main())
