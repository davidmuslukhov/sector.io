"""Scale municipalities by land area vs Vancouver (124 km²).

Keeps Vancouver fixed. Restores Burnaby / New Westminster if missing, then
scales roads + district rings. Run from repo root:

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
    "burnaby": 90.6,
    "new_westminster": 15.6,
}

# Van-scale Burnaby / New West (pre-area-scale), restored if absent.
BURNABY_HIGHWAYS = {
    "willingdon_ave": {
        "lanes": 4,
        "points": [
            [40, 820], [40, 890], [40, 945], [40, 1000],
            [40, 1100], [40, 1120], [40, 1230], [40, 1280],
        ],
    },
    "royal_oak_ave": {
        "lanes": 4,
        "points": [
            [135, 820], [135, 890], [135, 920], [135, 1000],
            [135, 1090], [135, 1120], [135, 1230], [135, 1280],
        ],
    },
    "kensington_ave": {
        "lanes": 4,
        "points": [
            [260, 780], [260, 840], [260, 900], [260, 1000],
            [260, 1070], [260, 1120], [260, 1230], [260, 1280],
        ],
    },
    "sperling_ave": {
        "lanes": 4,
        "points": [
            [355, 740], [355, 820], [355, 900], [355, 1000],
            [355, 1045], [355, 1120], [355, 1230], [355, 1280],
        ],
    },
    "north_rd": {
        "lanes": 4,
        "points": [
            [510, 720], [510, 800], [510, 900], [510, 1000],
            [510, 1120], [510, 1230], [510, 1280],
        ],
    },
    "marine_way": {
        "lanes": 4,
        "points": [
            [-120, 820], [40, 820], [135, 820], [220, 810],
            [300, 790], [360, 760], [400, 730],
        ],
    },
    "imperial_st": {
        "lanes": 4,
        "points": [
            [-120, 890], [40, 890], [135, 890], [260, 890],
            [355, 890], [510, 890],
        ],
    },
    "canada_way": {
        "lanes": 4,
        "points": [
            [-120, 1000], [40, 1000], [135, 1000], [220, 990],
            [260, 980], [320, 940], [355, 900], [400, 850],
            [440, 800], [460, 760],
        ],
    },
    "lougheed_hwy": {
        "lanes": 4,
        "points": [
            [-120, 1120], [40, 1120], [135, 1120], [260, 1120],
            [355, 1120], [510, 1120],
        ],
    },
    "columbia_st": {
        "lanes": 4,
        "points": [
            [290, 730], [340, 740], [390, 750], [440, 760],
            [490, 775], [530, 790],
        ],
    },
    "sixth_ave_nw": {
        "lanes": 4,
        "points": [
            [300, 780], [350, 790], [400, 800], [450, 812], [500, 825],
        ],
    },
    "eighth_ave_nw": {
        "lanes": 4,
        "points": [
            [310, 830], [360, 840], [410, 850], [460, 860], [510, 870],
        ],
    },
    "mcbride_blvd": {
        "lanes": 4,
        "points": [
            [420, 875], [420, 850], [420, 800], [415, 760], [410, 750],
        ],
    },
    "twelfth_st_nw": {
        "lanes": 4,
        "points": [
            [340, 870], [340, 840], [335, 790], [330, 740],
        ],
    },
    "twentieth_st_nw": {
        "lanes": 4,
        "points": [
            [490, 875], [490, 850], [490, 800], [490, 775],
        ],
    },
}

HWY1_BURNABY_PREFIX = [
    [-120, 1105], [40, 1100], [135, 1090], [260, 1070], [355, 1045],
    [450, 1000], [510, 940], [500, 850], [450, 750], [360, 620],
    [260, 500], [200, 430],
]

HASTINGS_BURNABY_SUFFIX = [
    [40, 1230], [135, 1230], [260, 1230], [355, 1230], [510, 1230],
]

KINGSWAY_BURNABY_SUFFIX = [
    [-40, 955], [40, 945], [135, 920], [200, 880], [260, 840],
    [320, 800], [380, 770], [420, 750],
]

BURNABY_LABELS = {
    "willingdon_ave": "Willingdon Ave",
    "royal_oak_ave": "Royal Oak Ave",
    "kensington_ave": "Kensington Ave",
    "sperling_ave": "Sperling Ave",
    "north_rd": "North Rd",
    "marine_way": "Marine Way",
    "imperial_st": "Imperial St",
    "canada_way": "Canada Way",
    "lougheed_hwy": "Lougheed Hwy",
    "columbia_st": "Columbia St",
    "sixth_ave_nw": "6th Ave",
    "eighth_ave_nw": "8th Ave",
    "mcbride_blvd": "McBride Blvd",
    "twelfth_st_nw": "12th St",
    "twentieth_st_nw": "20th St",
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
    "metrotown": "burnaby",
    "brentwood": "burnaby",
    "burnaby_heights": "burnaby",
    "edmonds": "burnaby",
    "burnaby": "burnaby",
    "downtown_new_west": "new_westminster",
    "sapperton": "new_westminster",
    "new_westminster": "new_westminster",
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

BURNABY_DISTRICTS = {
    "metrotown": {
        "title": "Metrotown",
        "ring": (
            (-120.0, 820.0), (135.0, 820.0), (135.0, 1000.0), (-120.0, 1000.0),
        ),
    },
    "brentwood": {
        "title": "Brentwood",
        "ring": (
            (-120.0, 1080.0), (135.0, 1080.0), (135.0, 1230.0), (-120.0, 1230.0),
        ),
    },
    "burnaby_heights": {
        "title": "Burnaby Heights",
        "ring": (
            (-120.0, 1230.0), (260.0, 1230.0), (260.0, 1280.0), (-120.0, 1280.0),
        ),
    },
    "edmonds": {
        "title": "Edmonds",
        "ring": (
            (135.0, 740.0), (355.0, 740.0), (355.0, 920.0), (135.0, 920.0),
        ),
    },
    "burnaby": {
        "title": "Burnaby",
        "ring": (
            (-120.0, 820.0), (40.0, 820.0), (135.0, 820.0), (220.0, 810.0),
            (300.0, 790.0), (360.0, 760.0), (400.0, 730.0), (510.0, 730.0),
            (510.0, 1280.0), (-120.0, 1280.0),
        ),
        "hotkey_only": True,
    },
    "downtown_new_west": {
        "title": "Downtown New Westminster",
        "ring": (
            (290.0, 730.0), (420.0, 745.0), (420.0, 830.0), (290.0, 815.0),
        ),
    },
    "sapperton": {
        "title": "Sapperton",
        "ring": (
            (420.0, 760.0), (530.0, 790.0), (530.0, 875.0), (420.0, 860.0),
        ),
    },
    "new_westminster": {
        "title": "New Westminster",
        "ring": (
            (290.0, 720.0), (390.0, 735.0), (480.0, 760.0), (530.0, 790.0),
            (530.0, 875.0), (460.0, 875.0), (400.0, 865.0), (340.0, 850.0),
            (300.0, 830.0), (290.0, 780.0),
        ),
        "hotkey_only": True,
    },
}

    # 2× Whalley-anchored map: Scott Rd / 120 St at X=-84.4.
    SCOTT_X = -84.4
    SE_ANCHOR = (-84.4, 0.0)


def shoelace(ring) -> float:
    a = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) * 0.5


def point_in_ring(ring, x: float, y: float) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def round_pt(x: float, y: float) -> list[float]:
    def r(v: float) -> float:
        v = round(v, 1)
        if abs(v - round(v)) < 1e-9:
            return float(int(round(v)))
        return v

    return [r(x), r(y)]


def ensure_burnaby(data: dict) -> None:
    highways = data["highways"]
    if "willingdon_ave" in highways:
        return
    # Extend hwy1 / hastings / kingsway then insert Burnaby roads.
    hwy1 = highways["hwy1"]
    if isinstance(hwy1, dict):
        pts = hwy1["points"]
    else:
        pts = hwy1
    if float(pts[0][0]) > -100:
        prefix = [list(map(float, p)) for p in HWY1_BURNABY_PREFIX]
        new_pts = prefix + [list(map(float, p)) for p in pts]
        if isinstance(hwy1, dict):
            highways["hwy1"]["points"] = new_pts
        else:
            highways["hwy1"] = new_pts

    for key, suffix in (
        ("hastings_st", HASTINGS_BURNABY_SUFFIX),
        ("kingsway", KINGSWAY_BURNABY_SUFFIX),
    ):
        entry = highways[key]
        pts = entry["points"] if isinstance(entry, dict) else entry
        extra = [list(map(float, p)) for p in suffix]
        if isinstance(entry, dict):
            entry["points"] = [list(map(float, p)) for p in pts] + extra
        else:
            highways[key] = [list(map(float, p)) for p in pts] + extra

    # Insert Burnaby highways before Williams Rd if present, else append.
    for name, spec in BURNABY_HIGHWAYS.items():
        highways[name] = {
            "lanes": spec["lanes"],
            "points": [list(map(float, p)) for p in spec["points"]],
        }


def ensure_burnaby_districts(defs: dict) -> None:
    if "burnaby" in defs:
        return
    # Insert before surrey.
    items = list(defs.items())
    out = {}
    for key, val in items:
        if key == "surrey":
            out.update(BURNABY_DISTRICTS)
        out[key] = val
    if "surrey" not in defs:
        out.update(BURNABY_DISTRICTS)
    defs.clear()
    defs.update(out)


def patch_districts_source_for_burnaby(src: str) -> str:
    if '"burnaby": {' in src and "Willingdon Ave" in src:
        return src
    if "Willingdon Ave" not in src:
        src = src.replace(
            '"kingsway": "Kingsway",\n',
            '"kingsway": "Kingsway",\n'
            + "".join(f'    "{k}": "{v}",\n' for k, v in BURNABY_LABELS.items()),
        )
    if '("vancouver", "Vancouver", "Vancouver"),\n    ("port_kells"' in src:
        src = src.replace(
            '("vancouver", "Vancouver", "Vancouver"),\n    ("port_kells"',
            '("vancouver", "Vancouver", "Vancouver"),\n'
            '    ("metrotown", "Metrotown", "Burnaby"),\n'
            '    ("brentwood", "Brentwood", "Burnaby"),\n'
            '    ("burnaby_heights", "Burnaby Heights", "Burnaby"),\n'
            '    ("edmonds", "Edmonds", "Burnaby"),\n'
            '    ("burnaby", "Burnaby", "Burnaby"),\n'
            '    ("downtown_new_west", "Downtown New Westminster", "New Westminster"),\n'
            '    ("sapperton", "Sapperton", "New Westminster"),\n'
            '    ("new_westminster", "New Westminster", "New Westminster"),\n'
            '    ("port_kells"',
        )
    if '"burnaby": {' not in src:
        block = []
        for key, spec in BURNABY_DISTRICTS.items():
            block.append(f'    "{key}": {{')
            block.append(f'        "title": \'{spec["title"]}\',')
            block.append('        "ring": (')
            for x, y in spec["ring"]:
                block.append(f"            ({x}, {y}),")
            block.append("        ),")
            if spec.get("hotkey_only"):
                block.append('        "hotkey_only": True,')
            block.append("    },")
        insertion = "\n".join(block) + "\n"
        src = src.replace('    "surrey": {', insertion + '    "surrey": {', 1)
    return src


def main() -> None:
    # Load YAML and ensure Burnaby roads exist before measuring/scaling.
    with YAML_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    ensure_burnaby(data)

    # Load districts module after optional source patch.
    src = patch_districts_source_for_burnaby(DISTRICTS_PATH.read_text(encoding="utf-8"))
    DISTRICTS_PATH.write_text(src, encoding="utf-8")

    # Fresh import of districts after patch.
    import importlib
    import city.districts as districts_mod

    importlib.reload(districts_mod)
    DISTRICT_DEFS = districts_mod.DISTRICT_DEFS
    CITY_CENTRE_BLOCKS = districts_mod.CITY_CENTRE_BLOCKS
    ensure_burnaby_districts(DISTRICT_DEFS)

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
        "burnaby": math.sqrt(
            (van_area * (REAL_KM2["burnaby"] / VAN_KM2))
            / shoelace(DISTRICT_DEFS["burnaby"]["ring"])
        ),
        "new_westminster": math.sqrt(
            (van_area * (REAL_KM2["new_westminster"] / VAN_KM2))
            / shoelace(DISTRICT_DEFS["new_westminster"]["ring"])
        ),
        "vancouver": 1.0,
    }
    # Shared SE anchor so Scott Rd (x=18) stays a vertical seam.
    anchors = {
        "surrey": SE_ANCHOR,
        "district_of_langley": SE_ANCHOR,
        "delta": SE_ANCHOR,
        "richmond": (-480.0, 400.0),
        "burnaby": (-120.0, 1000.0),
        "new_westminster": (400.0, 800.0),
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
        if point_in_ring(DISTRICT_DEFS["new_westminster"]["ring"], x, y):
            return "new_westminster"
        if point_in_ring(DISTRICT_DEFS["burnaby"]["ring"], x, y):
            return "burnaby"
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
        if -120 < x < 560 and y >= 700:
            return "burnaby"
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

    header = f"""# Surrey / Langley / Delta / Richmond / Vancouver / Burnaby / New Westminster, BC —
# arterial highways + local streets.
# World XY: X=east, Y=north. Schematic but oriented like the real map.
# Area baseline: Vancouver = {VAN_KM2:g} km² (model shoelace fixed). Other cities
# scaled so model area ≈ Vancouver × (city_km² / {VAN_KM2:g}).
#   Vancouver  {VAN_KM2:g}   Surrey {REAL_KM2['surrey']:g}   Langley Twp {REAL_KM2['district_of_langley']:g}
#   Delta {REAL_KM2['delta']:g}   Richmond {REAL_KM2['richmond']:g}   Burnaby {REAL_KM2['burnaby']:g}
#   New Westminster {REAL_KM2['new_westminster']:g}
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

    # Rewrite districts.py: patch labels/HUD, then regenerate blocks + DISTRICT_DEFS.
    src = DISTRICTS_PATH.read_text(encoding="utf-8")
    src = patch_districts_source_for_burnaby(src)

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
