"""Scale municipalities by land area vs Vancouver (124 km²).

Keeps Vancouver fixed, then scales roads + district rings. Run from repo root:

  python -m city.scale_areas
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "city" / "data" / "city.yaml"
DISTRICTS_PATH = ROOT / "city" / "districts.py"

VAN_KM2 = 124.0
REAL_KM2 = {
    "surrey": 316.0,
    "district_of_langley": 308.0,
    "delta": 180.0,
    "richmond": 129.0,
}

PARENT = {
    "city_centre": "surrey",
    "whalley": "surrey",
    "newton": "surrey",
    "guildford": "surrey",
    "fleetwood": "surrey",
    "cloverdale": "surrey",
    "south_surrey": "surrey",
    "white_rock_centre": "surrey",
    "surrey": "surrey",
    "north_delta": "delta",
    "ladner": "delta",
    "tsawwassen": "delta",
    "delta": "delta",
    "bridgeport": "richmond",
    "seaforth": "richmond",
    "steveston": "richmond",
    "brighouse": "richmond",
    "cambie": "richmond",
    "broadmoor": "richmond",
    "east_richmond": "richmond",
    "richmond": "richmond",
    "port_kells": "district_of_langley",
    "walnut_grove": "district_of_langley",
    "willowbrook": "district_of_langley",
    "rural_north_langley": "district_of_langley",
    "fort_langley": "district_of_langley",  # legacy alias
    "east_clayton": "district_of_langley",
    "willoughby": "district_of_langley",
    "hopington": "district_of_langley",
    "fern_ridge": "district_of_langley",
    "brookswood": "district_of_langley",
    "campbell_valley": "district_of_langley",
    "murrayville": "district_of_langley",
    "aldergrove": "district_of_langley",
    "rural_south_langley": "district_of_langley",
    "langley_city": "district_of_langley",
    "district_of_langley": "district_of_langley",
    "downtown_vancouver": "vancouver",
    "ubc": "vancouver",
    "vancouver": "vancouver",
}


def main() -> None:
    with YAML_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    import city.districts as districts_mod

    DISTRICT_DEFS = districts_mod.DISTRICT_DEFS
    CITY_CENTRE_BLOCKS = districts_mod.CITY_CENTRE_BLOCKS

    van_area = shoelace(DISTRICT_DEFS["vancouver"]["ring"])
    s_surrey = math.sqrt(
        (van_area * (REAL_KM2["surrey"] / VAN_KM2))
        / shoelace(DISTRICT_DEFS["surrey"]["ring"])
    )
    scales = {
        "surrey": s_surrey,
        "district_of_langley": s_surrey,  # shared grid / 196 St
        "delta": math.sqrt(
            (van_area * (REAL_KM2["delta"] / VAN_KM2))
            / shoelace(DISTRICT_DEFS["delta"]["ring"])
        ),
        "richmond": math.sqrt(
            (van_area * (REAL_KM2["richmond"] / VAN_KM2))
            / shoelace(DISTRICT_DEFS["richmond"]["ring"])
        ),
        "vancouver": 1.0,
    }
    # Shared SE anchor so Scott Rd (x=18) stays a vertical seam.
    anchors = {
        "surrey": SE_ANCHOR,
        "district_of_langley": SE_ANCHOR,
        "delta": SE_ANCHOR,
        "richmond": (-480.0, 400.0),
        "vancouver": (0.0, 0.0),
    }
    print("scale factors:", {k: round(v, 4) for k, v in scales.items() if k != "vancouver"})

    def xform(x: float, y: float, region: str) -> tuple[float, float]:
        if region == "vancouver":
            return x, y
        ax, ay = anchors[region]
        s = scales[region]
        return ax + s * (x - ax), ay + s * (y - ay)

    def classify(x: float, y: float) -> str:
        # Hard Scott Rd split keeps SE seam clean despite different Delta/Surrey scales.
        if x <= -120 and y >= 800:
            return "vancouver"
        if point_in_ring(DISTRICT_DEFS["vancouver"]["ring"], x, y):
            return "vancouver"
        if point_in_ring(DISTRICT_DEFS["richmond"]["ring"], x, y):
            return "richmond"
        if x >= SCOTT_X - 0.05:
            if point_in_ring(DISTRICT_DEFS["district_of_langley"]["ring"], x, y):
                return "district_of_langley"
            return "surrey"
        if point_in_ring(DISTRICT_DEFS["delta"]["ring"], x, y) or y < 200:
            return "delta"
        if x <= -400:
            return "richmond"
        return "surrey"

    def xform_pt(x: float, y: float) -> tuple[float, float]:
        return xform(x, y, classify(x, y))

    # Transform rings.
    new_defs = {}
    for key, spec in DISTRICT_DEFS.items():
        parent = PARENT.get(key, "vancouver")
        ring = spec["ring"]
        new_ring = ring if parent == "vancouver" else tuple(
            xform(px, py, parent) for px, py in ring
        )
        new_spec = dict(spec)
        new_spec["ring"] = new_ring
        new_defs[key] = new_spec

    new_blocks = []
    for x0, x1, y0, y1 in CITY_CENTRE_BLOCKS:
        nx0, ny0 = xform(x0, y0, "surrey")
        nx1, ny1 = xform(x1, y1, "surrey")
        new_blocks.append((nx0, nx1, ny0, ny1))

    # Transform highways.
    for _name, entry in data["highways"].items():
        if isinstance(entry, dict):
            entry["points"] = [
                round_pt(*xform_pt(float(p[0]), float(p[1]))) for p in entry["points"]
            ]
        else:
            data["highways"][_name] = [
                round_pt(*xform_pt(float(p[0]), float(p[1]))) for p in entry
            ]

    header = f"""# Surrey / Langley / Delta / Richmond / Vancouver, BC —
# arterial highways + local streets.
# World XY: X=east, Y=north. Schematic but oriented like the real map.
# Area baseline: Vancouver = {VAN_KM2:g} km² (model shoelace fixed). Other cities
# scaled so model area ≈ Vancouver × (city_km² / {VAN_KM2:g}).
#   Vancouver  {VAN_KM2:g}   Surrey {REAL_KM2['surrey']:g}   Langley Twp {REAL_KM2['district_of_langley']:g}
#   Delta {REAL_KM2['delta']:g}   Richmond {REAL_KM2['richmond']:g}
# Provincial: Hwy 1, 10, 15, 17, 17A, 91, 99. Major arterials: Fraser Hwy, 88 Ave,
# King George Blvd, Scott Rd / 120 St. Surrey–Langley border is 196 St.
# Richmond is Lulu Island only (Sea Island / YVR excluded).
# Vancouver is north of the North Arm, including Point Grey / UBC.

"""
    body = yaml.dump(
        data,
        default_flow_style=None,
        sort_keys=False,
        width=100,
        allow_unicode=True,
    )
    YAML_PATH.write_text(header + body, encoding="utf-8")

    # Rewrite districts.py: regenerate blocks + DISTRICT_DEFS.
    src = DISTRICTS_PATH.read_text(encoding="utf-8")

    def rf(v: float) -> float:
        return float(round_pt(v, 0)[0])

    def ry(v: float) -> float:
        return float(round_pt(0, v)[1])

    def fmt_ring(ring) -> str:
        lines = ['        "ring": (']
        for x, y in ring:
            px, py = round_pt(x, y)
            lines.append(f"            ({float(px)}, {float(py)}),")
        lines.append("        ),")
        return "\n".join(lines)

    blocks_txt = "CITY_CENTRE_BLOCKS = (\n" + "".join(
        f"    ({rf(a)}, {rf(b)}, {ry(c)}, {ry(d)}),\n" for a, b, c, d in new_blocks
    ) + ")"

    defs_lines = ["DISTRICT_DEFS: dict[str, dict] = {"]
    for key, spec in new_defs.items():
        title = spec["title"].replace("'", "\\'")
        defs_lines.append(f'    "{key}": {{')
        defs_lines.append(f"        \"title\": '{title}',")
        defs_lines.append(fmt_ring(spec["ring"]))
        if spec.get("bright_key"):
            defs_lines.append(f"        \"bright_key\": '{spec['bright_key']}',")
        if spec.get("hotkey_only"):
            defs_lines.append('        "hotkey_only": True,')
        defs_lines.append("    },")
    defs_lines.append("}")
    defs_txt = "\n".join(defs_lines)

    # Replace from CITY_CENTRE_BLOCKS through end of DISTRICT_DEFS.
    m = re.search(
        r"CITY_CENTRE_BLOCKS = \([\s\S]*\n\)\n\nDISTRICT_DEFS: dict\[str, dict\] = \{[\s\S]*\n\}\n?\Z",
        src,
    )
    if not m:
        raise SystemExit("Could not locate CITY_CENTRE_BLOCKS / DISTRICT_DEFS block")
    src = src[: m.start()] + blocks_txt + "\n\n" + defs_txt + "\n"
    DISTRICTS_PATH.write_text(src, encoding="utf-8")

    print("--- area ratios vs Vancouver (target) ---")
    for key, km2 in REAL_KM2.items():
        a = shoelace(new_defs[key]["ring"])
        ratio = a / van_area
        target = km2 / VAN_KM2
        err = abs(ratio - target) / target * 100.0
        print(f"{key:22} model={ratio:.3f}x  target={target:.3f}x  err={err:.1f}%")


if __name__ == "__main__":
    main()
