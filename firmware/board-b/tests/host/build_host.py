#!/usr/bin/env python3
"""Compile the ESPHome host build of the xtm_driver component with the system compiler.

    esphome compile --only-generate xtm-host.yaml   # writes .esphome/build/xtm-host/src
    python3 build_host.py                           # builds ./xtm-host

PlatformIO's native platform isn't needed: the generated tree is plain C++20.
"""
import concurrent.futures as cf
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / ".esphome/build/xtm-host/src"
OBJ = HERE / ".esphome/host-obj"
COMMON = [
    "-DESPHOME_LOG_LEVEL=ESPHOME_LOG_LEVEL_DEBUG", "-DUSE_HOST", f"-I{SRC}", "-O1", "-g",
    "-Wall", "-Wextra", "-Wno-sign-compare", "-Wno-unused-but-set-variable", "-Wno-unused-variable",
    "-Wno-unused-parameter", "-Wno-missing-field-initializers",
]


def compile_one(src: pathlib.Path):
    obj = OBJ / (str(src.relative_to(SRC)).replace("/", "__") + ".o")
    if obj.exists() and obj.stat().st_mtime > src.stat().st_mtime:
        return obj, ""
    if src.suffix == ".c":
        cmd = ["gcc", *COMMON, "-std=gnu17", "-c", str(src), "-o", str(obj)]
    else:
        cmd = ["g++", *COMMON, "-std=gnu++20", "-fno-exceptions", "-c", str(src), "-o", str(obj)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{src.relative_to(SRC)}:\n{r.stderr}")
    return obj, r.stderr


def main():
    if not SRC.exists():
        sys.exit("run: esphome compile --only-generate xtm-host.yaml")
    OBJ.mkdir(parents=True, exist_ok=True)
    sources = sorted(p for p in SRC.rglob("*") if p.suffix in (".c", ".cpp"))
    objs, failed = [], False
    with cf.ThreadPoolExecutor(os.cpu_count() or 4) as ex:
        for fut in [ex.submit(compile_one, s) for s in sources]:
            try:
                obj, warn = fut.result()
                objs.append(obj)
                if warn and "xtm_driver" in warn:
                    print(warn)
            except RuntimeError as e:
                failed = True
                print(e)
    if failed:
        sys.exit(1)
    out = HERE / "xtm-host"
    subprocess.run(["g++", "-o", str(out), *map(str, objs), "-lpthread"], check=True)
    print(f"built {out} from {len(objs)} files")


if __name__ == "__main__":
    main()
