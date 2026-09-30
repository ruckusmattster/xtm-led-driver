"""Build every generated hardware file from board_a.py and board_b.py.

    python3 build.py

Writes, for each board, into ../hardware/<board>/:
  <board>-sheets.md        every part, pin and net, sheet by sheet
  <board>.net              KiCad netlist (Pcbnew: File > Import > Netlist)
  <board>-bom-hand.csv     hand-assembly BOM with distributor part numbers and buy quantities
  <board>-bom-jlc.csv      JLC-format BOM (Comment, Designator, Footprint, LCSC Part #)
  <board>-cpl-template.csv designators for JLC's CPL; kicad_pos_to_jlc_cpl.py fills it from your layout
Exits non-zero if the connectivity check (ERC) finds an error.
"""
import os
import sys

import board_a
import board_b
from catalog import CATALOG

SETS = 7          # six builds (four fixtures + two spares) plus parts for one more

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "hardware")


def main():
    failed = False
    used = set()
    for mod in (board_a, board_b):
        b = mod.build()
        errors, warnings = b.erc()
        print(f"{b.title}: {len(b.parts)} parts, {len(b.nets())} nets, {len(errors)} ERC errors, {len(warnings)} warnings")
        for e in errors:
            print("  ERROR", e)
        for w in warnings:
            print("  warning", w)
        failed |= bool(errors)
        d = os.path.join(OUT, b.name)
        os.makedirs(d, exist_ok=True)
        files = {
            f"{b.name}-sheets.md": b.sheet_tables_md(),
            f"{b.name}.net": b.kicad_netlist(),
            f"{b.name}-bom-hand.csv": b.bom_hand(SETS),
            f"{b.name}-bom-jlc.csv": b.bom_jlc(),
            f"{b.name}-cpl-template.csv": b.cpl_template(),
        }
        for name, text in files.items():
            with open(os.path.join(d, name), "w", newline="") as f:
                f.write(text)
        used |= {p.key for p in b.parts.values()}
        used |= {key for _, key, _ in b.extras}
    todo = sorted(k for k in used if CATALOG[k].get("status", "").startswith("to verify"))
    desc = sorted(k for k in used if CATALOG[k].get("status", "") == "describe")
    print(f"\nCatalog: {len(used)} part types used; {len(todo)} still marked 'to verify', {len(desc)} bought by description")
    for k in todo:
        c = CATALOG[k]
        print(f"  to verify: {k:22s} {c.get('mpn',''):24s} LCSC {c.get('lcsc','') or '-':10s} {c.get('desc','')}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
