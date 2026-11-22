"""Shift Richmond/Vancouver/Burnaby 200 units west; lengthen Hwy 99 straight."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

DX = -200
ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "city" / "data" / "city.yaml"
DIST_PATH = ROOT / "city" / "districts.py"

WEST_ROADS = {
    "bridgeport_rd",
    "no_1_rd",
    "no_2_rd",
    "no_3_rd",
    "no_4_rd",
    "steveston_hwy",
    "williams_rd",
    "francis_rd",
    "blundell_rd",
    "westminster_hwy",
    "hwy91",
    "sw_marine",
    "broadway",
    "hastings_st",
    "kingsway",
    "granville_st",
    "boundary_rd",
}

WEST_DISTRICTS = {
    "richmond",
    "bridgeport",
    "seaforth",
    "steveston",
    "brighouse",
    "cambie",
    "broadmoor",
    "east_richmond",
    "vancouver",
    "downtown_vancouver",
    "ubc",
    "burnaby",
    "metrotown",
    "brentwood",
    "burnaby_heights",
    "edmonds",
    "new_westminster",
    "downtown_new_west",
    "sapperton",
}


def round_pt(x: float, y: float) -> list[float]:
    def r(v: float) -> float:
        v = round(v, 1)
        if abs(v - round(v)) < 1e-9:
            return float(int(round(v)))
        return v

    return [r(x), r(y)]


def shift_pts(pts: list) -> list[list[float]]:
    return [round_pt(float(p[0]) + DX, float(p[1])) for p in pts]


def main() -> None:
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    highways = data["highways"]

    for name in WEST_ROADS:
        if name not in highways:
            print("missing road", name)
            continue
        entry = highways[name]
        if isinstance(entry, dict):
            entry["points"] = shift_pts(entry["points"])
        else:
            highways[name] = shift_pts(entry)

    # Hwy 99: move western/Richmond side west; leave Surrey approach fixed so
    # the y≈-160 straight run grows by 200 toward the west.
    entry = highways["hwy99"]
    pts = entry if not isinstance(entry, dict) else entry["points"]
    new_pts = []
    for p in pts:
        x, y = float(p[0]), float(p[1])
        if x < 120:
            x += DX
        new_pts.append(round_pt(x, y))
    if isinstance(entry, dict):
        entry["points"] = new_pts
    else:
        highways["hwy99"] = new_pts

    straight = [p[0] for p in new_pts if abs(p[1] + 160) < 1]
    print("hwy99 y=-160 x span:", min(straight), "->", max(straight), "len", max(straight) - min(straight))

    header = (
        "# Surrey / Langley / Delta / Richmond / Vancouver / Burnaby / New Westminster, BC —\n"
        "# arterial highways + local streets.\n"
        "# World XY: X=east, Y=north. Schematic but oriented like the real map.\n"
        "# Van/Burnaby/New West: six traced corridors. Richmond/Van/Burnaby shifted -200x\n"
        "# to lengthen the Hwy 99 straight connector toward Surrey.\n"
        "# Provincial: Hwy 1, 10, 15, 17, 17A, 91, 99.\n"
        "\n"
    )
    body = yaml.dump(
        data,
        default_flow_style=None,
        sort_keys=False,
        width=100,
        allow_unicode=True,
    )
    YAML_PATH.write_text(header + body, encoding="utf-8")

    src = DIST_PATH.read_text(encoding="utf-8")
    for key in sorted(WEST_DISTRICTS, key=len, reverse=True):
        pattern = (
            rf'("{re.escape(key)}":\s*\{{.*?"ring":\s*\()'
            rf'((?:\n\s*\(-?\d+\.?\d*,\s*-?\d+\.?\d*\),)+)'
            rf'(\n\s*\),)'
        )
        match = re.search(pattern, src, flags=re.DOTALL)
        if match is None:
            print("no ring", key)
            continue

        def repl_pt(mm: re.Match[str]) -> str:
            x = float(mm.group(1)) + DX
            y = float(mm.group(2))
            px, py = round_pt(x, y)
            return f"({px}, {py})"

        new_inner = re.sub(
            r"\((-?\d+\.?\d*),\s*(-?\d+\.?\d*)\)",
            repl_pt,
            match.group(2),
        )
        src = src[: match.start(2)] + new_inner + src[match.end(2) :]
        print("shifted district", key)

    DIST_PATH.write_text(src, encoding="utf-8")
    print("done")


if __name__ == "__main__":
    main()
