"""Convert a KiCad footprint-position export into JLCPCB's CPL format.

In Pcbnew: File > Fabrication Outputs > Component Placement (.pos), format CSV, units mm,
one file for both sides. Then:

    python3 kicad_pos_to_jlc_cpl.py board_a-all-pos.csv board_a-cpl.csv

KiCad and JLC disagree about zero rotation for some packages. The corrections below cover the
footprints used on these boards; they follow the community table in JLCKicadTools
(github.com/matthewlai/JLCKicadTools, cpl_rotations_db.csv). Always check JLC's placement
preview before paying: it shows each part over its pads and lets you rotate any that are wrong.
Footprints with no entry (HSOP-8, QFN-48, SOD-123, SMB, the ESP32 module) are passed through
unchanged: check those in the preview first.
"""
import csv
import re
import sys

ROTATIONS = [                 # (footprint regex, degrees added to KiCad's rotation)
    (r"^SOT-223", 180),
    (r"^SOT-23", -90),        # also SOT-23-5 and SOT-23-6
    (r"^TSSOP-", 270),
    (r"^(.*?_)?[VW]?QFN-(16|20|24|28|40)(-|_|$)", 270),   # the DAC80504's WQFN-16 (TI RTE0016D)
    (r"^CP_Elec_10x10", 180),
    (r"^USB_C_Receptacle_HRO_TYPE-C-31-M-12", 180),
]


def correction(footprint):
    fp = footprint.split(":")[-1]
    for pat, rot in ROTATIONS:
        if re.search(pat, fp):
            return rot
    return 0


def main(src, dst):
    with open(src, newline="") as f:
        rows = list(csv.DictReader(f))
    with open(dst, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in rows:
            ref = r.get("Ref") or r.get("Designator")
            fp = r.get("Package") or r.get("Footprint") or ""
            rot = (float(r.get("Rot", 0)) + correction(fp)) % 360
            side = r.get("Side", "top").lower()
            w.writerow([ref, f"{float(r['PosX']):.3f}mm", f"{float(r['PosY']):.3f}mm",
                        "Top" if side.startswith("top") else "Bottom", f"{rot:g}"])
    print(f"wrote {len(rows)} placements to {dst}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
