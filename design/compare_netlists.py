"""Compare two KiCad netlists by connectivity, ignoring net names.

Use it after drawing the schematic by hand: export a netlist from Eeschema
(File > Export > Netlist, KiCad format) and compare it with the generated one:

    python3 compare_netlists.py ../hardware/board_a/board_a.net my_board_a.net

Reports parts that differ in footprint or are missing, and any pin whose set of
connected pins differs between the two files. Net names may differ freely.
"""
import re
import sys


def parse(path):
    text = open(path, encoding="utf-8").read()
    comps = {}
    for m in re.finditer(r'\(comp\s+\(ref\s+"?([^"\s)]+)"?\)(.*?)\(tstamps', text, re.S):
        ref, body = m.group(1), m.group(2)
        fp = re.search(r'\(footprint\s+"?([^"\)]*)"?\)', body)
        comps[ref] = fp.group(1) if fp else ""
    nets = []
    for m in re.finditer(r'\(net\s+\(code\s+"?\d+"?\)\s+\(name\s+"((?:[^"\\]|\\.)*)"\)(.*?)(?=\(net\s+\(code|\Z)', text, re.S):
        nodes = frozenset(re.findall(r'\(node\s+\(ref\s+"?([^"\s)]+)"?\)\s+\(pin\s+"?([^"\s)]+)"?\)', m.group(2)))
        if nodes:
            nets.append((m.group(1), nodes))
    return comps, nets


def main(a, b):
    ca, na = parse(a)
    cb, nb = parse(b)
    problems = 0
    for ref in sorted(set(ca) | set(cb)):
        if ref not in cb:
            print(f"only in {a}: {ref}")
            problems += 1
        elif ref not in ca:
            print(f"only in {b}: {ref}")
            problems += 1
        elif ca[ref].split(":")[-1] != cb[ref].split(":")[-1]:
            print(f"footprint differs for {ref}: {ca[ref]} vs {cb[ref]}")
            problems += 1
    pin_net_a = {node: nodes for _, nodes in na for node in nodes}
    pin_net_b = {node: nodes for _, nodes in nb for node in nodes}
    names_a = {node: name for name, nodes in na for node in nodes}
    seen = set()
    for node in sorted(set(pin_net_a) | set(pin_net_b)):
        ga, gb = pin_net_a.get(node, frozenset({node})), pin_net_b.get(node, frozenset({node}))
        if ga != gb and (ga, gb) not in seen:
            seen.add((ga, gb))
            problems += 1
            print(f"{node[0]}.{node[1]} (net {names_a.get(node, '?')}):")
            print(f"   missing in second: {sorted(ga - gb)}")
            print(f"   extra in second:   {sorted(gb - ga)}")
    print("netlists match" if not problems else f"{problems} differences")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
