# Board layout scripts

These scripts turn the two netlists in `design/` into finished KiCad 9 boards and JLCPCB files,
without anyone drawing the layout by hand. For each board they:

1. build the outline, mounting holes, slots and keep-outs, and place every part: the connectors,
   ICs and power parts at fixed coordinates, the small parts next to the pins they serve;
2. draw the copper that decides whether the board works before anything is routed: both switch
   nodes and bootstrap links (L1 only, no vias), the fused 48 V input and the +48V trunk to the
   buck, Q1's source to its shunt, the ch2 shunt ladder's bus bars, the CATHODE tab copper and heat
   spreader with its vias, the L2 ground plane, escapes for the few pins the router can't get out
   of, and a via to the plane beside every ground pad, while there's still room for them;
3. route everything else with Freerouting (kept out of the CATHODE copper), clean up what it
   leaves (stubs, doubled segments, dangling vias), and route again whatever is still open;
4. pour ground, stitch every pour fragment and pad the pours miss, place the reference labels;
5. run KiCad's DRC with the project's custom rules (`hardware/board_x.kicad_dru`: the 48 V
   spacing from IPC-2221B, 0.5 mm where a bare pad is involved and 0.3 mm between coated tracks;
   2 mm between precision and HV nets; 10 mm from the switch nodes; no vias on them);
6. export Gerbers, drill files and a JLCPCB placement file, and preview images.

The result is a normal KiCad project you open, inspect and adjust like one you drew yourself.

## What you need

- **KiCad 9.0** (any 9.0.x) from https://www.kicad.org/download/windows/ , installed to its default
  folder. Nothing else from KiCad: the scripts use its own Python and `kicad-cli`.
- **A Java 21 runtime** for Freerouting. From a Command Prompt:
  `winget install EclipseAdoptium.Temurin.21.JRE` (or the Temurin 21 JRE installer from
  https://adoptium.net with "Add to PATH" ticked). Open a new Command Prompt afterwards.
- **Internet on the first run**, to download Freerouting 1.9.0 (5 MB, from its GitHub releases)
  into `layout\tools\`. If that's blocked, download `freerouting-1.9.0.jar` from
  https://github.com/freerouting/freerouting/releases/tag/v1.9.0 into `layout\tools\` yourself, or
  set `FREEROUTING_JAR` to where you put it. (Board B's footprint for the ESP32-S3-Zero on its
  sockets is this project's own, in `lib\XTM.pretty`.)

Freerouting 1.9.0 rather than the newer 2.x on purpose: on Board A, 2.1 left over a hundred
connections open where 1.9 leaves a handful, and 2.1 ignores its pass limit.

## Running it

Double-click `run_layout.bat`, or from a Command Prompt in this folder:

```bat
run_layout.bat                          :: both boards, start to finish
run_layout.bat board_b                  :: one board
run_layout.bat board_a --stage place    :: placement only, with a preview (a minute)
run_layout.bat board_a --attempts 10    :: more routing attempts (each board tries 6 by default)
```

Board B takes a few minutes and Board A 5 to 30, most of it in Freerouting, which opens its own
window while it works and closes it when it's done: leave it alone. The same command in the
"KiCad 9.0 Command Prompt" (Start menu) is `python make_board.py board_a`.

Each run writes `out\board_a\` (or `board_b`):

| File | What it is |
| --- | --- |
| `board_a.kicad_pro`, `.kicad_pcb`, `.kicad_dru` | The KiCad project: open the `.kicad_pro` |
| `board_a-gerbers.zip` | Gerbers and drill files for JLCPCB, ready to upload |
| `board_a-cpl-jlc.csv` | Placement file in JLCPCB's format (`board_a-pos.csv` is KiCad's own) |
| `board_a_drc.json` | The final DRC report |
| `board_a-1-FCu_FSilkS.png` and the others | Preview images of each copper layer (SVG if no PNG converter) |
| `board_a_run.log` | What happened, with the DRC summary at the end |
| `board_a_freerouting-1.log`, `.dsn`, `.ses` | The router's input, output and log |

The last line of the log reads `done in ... s: 0 DRC errors, 0 unconnected` when the board is
complete. `run_layout.bat` says so too, and exits with an error otherwise.

## If connections are left open

Freerouting's result changes from run to run. If the log ends with a few connections open:

1. Run the board again, perhaps with `--attempts 10`; each attempt clears a wider circle
   around what's still open before routing it again; or
2. open `out\board_a\board_a.kicad_pro` in KiCad, route the ratsnest lines that remain (they're
   listed in the log), press **B** to refill the zones, save, close KiCad, and run
   `run_layout.bat board_a --stage export`. That re-stitches the pours, re-runs the DRC and writes
   new Gerbers and placement files without touching anything you drew.

The export stage is also how to regenerate the outputs after any hand edit. Running the full
script again starts over from the netlist and discards hand edits.

## Checking the result before ordering

Open each `.kicad_pro` in KiCad 9 and go through this list. The DRC covers the numeric rules; these
are the things a rule can't see.

- **Inspect > Design Rules Checker**, "Refill all zones" ticked: no errors, nothing unconnected.
  Silkscreen warnings are fine; look at any that sit on a pad.
- **View > 3D Viewer**: every part present and on the right side; J1, J2 and J3's openings face
  off the board. Board B's U1 is on the back, shown by its outline on the F.Fab/B.Fab layers
  (there's no 3D model for the module).
- Board A power stage: U2's SW pin, C23 and L2 pad 1 joined by short, wide copper on L1 with no
  vias (the same for U3, C3 and L3); C22 right at U2's VIN pin with a ground via beside it.
- Board A cathode: J2 pin 1, C60, R110 and the four drains all on the tab copper; the heat
  spreader under it on the bottom layer, joined by the grid of vias; R102 at least 2 mm from it.
- Board A sinks: each channel's SNSHI and SNSLO tracks start at the shunt's Kelvin pads (R102
  pads 2 and 3; NT1/NT2 at the ladder's mid-points; NT3–NT6 at R100 and R101); the divider
  bottoms (R46, R48, R50, R52) and C44–C47 return to SNSLO, not to ground.
- Board A precision island: nothing from the switch nodes nearby; the DRC's 2 mm rule keeps HV
  copper away.
- Board B: U1's two socket rows on the back, pin 1 (square pad) at the USB-C end nearest the
  middle of the board; no copper on either side under the antenna end at the right-hand edge.
  Print the board 1:1 (File > Plot, B.Cu, B.SilkS and Edge.Cuts to PDF, mirrored) and lay the
  module on it, pins into the pads, before ordering.
- Holes: Board A's four M3 holes and Board B's two are unplated, with nothing inside their rings.
- The Gerbers in KiCad's Gerber viewer (or JLCPCB's): four copper layers for Board A and two for
  Board B, the slot between J2's pads in the drill/outline file, paste layers present.

References that didn't fit on the silkscreen are on the F.Fab layer: for hand assembly, print it
(File > Plot, F.Fab and Edge.Cuts to PDF) as the assembly drawing.

At JLCPCB: upload the Gerber zip; for assembly, use `hardware/board_x/board_x-bom-jlc.csv` as the
BOM and `board_x-cpl-jlc.csv` as the placement file, and check every part's rotation in their
preview (their library's zero angle doesn't always match KiCad's; polarised parts and the ICs are
the ones to look at).

## What the scripts don't do

- They don't keep each Kelvin pair (SNSHIx with SNSLOx) side by side: the router draws them
  separately. They start at the right sense points, which is what matters most at these slow
  signals; redrawing them as pairs by hand is the one refinement worth the time.
- The router doesn't know which tracks matter more than others: look over the power stage, the
  sinks and the precision island against `hardware/LAYOUT.md` before ordering.
- Freerouting's result varies from run to run, and the placement of small parts follows simple
  rules; a second run can come out better or worse.

## Changing the layout

Everything that decides the layout is in `board_a_layout.py` and `board_b_layout.py`:

- `L.place("U2", 53.1, 40.5, 270)`: fixed parts, in mm from the board's top-left corner, rotation
  in degrees counter-clockwise. Move one, run `--stage place` to see it, then run the whole board.
- `A([...], Rect(x0, y0, x1, y1), anchor_pad=...)`: small parts placed automatically inside the
  rectangle, as close as possible to the pad named (decoupling capacitors) or to the parts they
  connect to. `SPACING` sets the room left between them for routing.
- `NET_CLASSES` and `PATTERNS`: track widths and clearances per net. The widths have to fit the
  pins a net lands on (0.2 mm reaches the 0.5 mm-pitch QFN pins).
- `prerouted()`, `cathode_copper()` and `finish()`: the copper drawn by hand and the pours.
- `SPEC`: how the board is routed: attempts and the time each may take, whether to start over
  every few attempts (`restart_every`, Board B) or keep repairing (Board A), the ground fan-out,
  and which nets are poured rather than routed.

The netlists themselves come from `design/board_a.py` and `design/board_b.py`; after changing
those, run `python design/build.py` (BOMs, sheet tables and netlists) and then the layout.

## Files

| File | Role |
| --- | --- |
| `make_board.py` | The run itself: stages, routing attempts, checks, outputs |
| `board_a_layout.py`, `board_b_layout.py` | Each board's placement, pre-drawn copper, pours and rules |
| `pcbkit.py` | Building a board from a netlist: footprints, placement, tracks, vias, zones, keep-outs |
| `route.py` | Freerouting round trip, clean-up, stitching, DRC, previews, fabrication outputs |
| `kicadlib.py` | Finds KiCad 9's footprint libraries, and this project's own in `lib\` |
| `run_layout.bat` | Windows launcher: finds KiCad and Java, runs both boards |
