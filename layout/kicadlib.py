"""Find KiCad 9 footprint libraries and load footprints through pcbnew.

Search order for a library nickname such as "Package_SO":
  1. $XTM_FOOTPRINT_DIRS (os.pathsep-separated folders that contain <lib>.pretty)
  2. $KICAD9_FOOTPRINT_DIR, then the standard KiCad 9 install locations
  3. layout/lib (footprints this project supplies or downloads)
This project's own footprints are in layout/lib/XTM.pretty. An Espressif module footprint
(PCM_Espressif, used by earlier versions of Board B) comes from KiCad's Plugin and Content Manager
if installed; otherwise it is downloaded once from Espressif's GitHub library into layout/lib.
"""
import os
import sys
import urllib.request

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(HERE, "lib")

ESPRESSIF_URL = ("https://raw.githubusercontent.com/espressif/kicad-libraries/main/footprints/"
                 "Espressif.pretty/{name}.kicad_mod")


def _standard_dirs():
    dirs = []
    for var in ("XTM_FOOTPRINT_DIRS",):
        if os.environ.get(var):
            dirs += os.environ[var].split(os.pathsep)
    for var in ("KICAD9_FOOTPRINT_DIR", "KICAD_FOOTPRINT_DIR"):
        if os.environ.get(var):
            dirs.append(os.environ[var])
    if sys.platform.startswith("win"):
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        dirs.append(os.path.join(pf, "KiCad", "9.0", "share", "kicad", "footprints"))
    elif sys.platform == "darwin":
        dirs.append("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
    else:
        dirs += ["/usr/share/kicad/footprints", "/usr/local/share/kicad/footprints"]
    return [d for d in dirs if d and os.path.isdir(d)]


def _pcm_dirs():
    """KiCad 9's Plugin and Content Manager installs third-party footprints under Documents."""
    home = os.path.expanduser("~")
    cands = [os.path.join(home, "Documents", "KiCad", "9.0", "3rdparty", "footprints"),
             os.path.join(home, ".local", "share", "kicad", "9.0", "3rdparty", "footprints")]
    out = []
    for c in cands:
        if os.path.isdir(c):
            for sub in os.listdir(c):           # e.g. com_github_espressif_kicad-libraries/Espressif.pretty
                p = os.path.join(c, sub)
                if os.path.isdir(p):
                    out.append(p)
    return out


def library_path(lib):
    if lib.startswith("PCM_"):
        name = lib[4:]
        for d in _pcm_dirs():
            p = os.path.join(d, name + ".pretty")
            if os.path.isdir(p):
                return p
        return os.path.join(LOCAL, name + ".pretty")
    for d in _standard_dirs() + [LOCAL]:
        p = os.path.join(d, lib + ".pretty")
        if os.path.isdir(p):
            return p
    raise FileNotFoundError(f"footprint library {lib}.pretty not found; set KICAD9_FOOTPRINT_DIR "
                            f"to KiCad 9's share/kicad/footprints folder")


def _ensure_espressif(path, name):
    f = os.path.join(path, name + ".kicad_mod")
    if os.path.exists(f):
        return
    os.makedirs(path, exist_ok=True)
    url = ESPRESSIF_URL.format(name=name)
    print(f"  downloading {name} from Espressif's KiCad library")
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    with open(f, "wb") as out:
        out.write(data)


def load_footprint(fpid):
    lib, name = fpid.split(":", 1)
    path = library_path(lib)
    if lib == "PCM_Espressif":
        _ensure_espressif(path, name)
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise FileNotFoundError(f"footprint {name} not found in {path}")
    fp.SetFPIDAsString(fpid) if hasattr(fp, "SetFPIDAsString") else None
    return fp
