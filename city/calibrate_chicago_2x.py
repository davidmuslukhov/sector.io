"""Generate Chicagoland 2× arterial + collector + minor city.yaml (roads only).

Scale: 42.2 units = 1.0 mile = 800 street numbers; 26.4 units = 1.0 km.
Origin (0,0): State Street & Madison Street (Downtown Loop).
Every 100 Chicago street numbers = 5.275 Panda3D units.
Plate: X ∈ [-760.0, +16.0], Y ∈ [-760.0, +680.0] (no lakefront yet).
Flat ribbon aesthetic: Z = 0 + hierarchy offsets; ground plane at Z = -0.25.
"""

from __future__ import annotations

from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent / "data" / "city.yaml"

UNITS_PER_MILE = 42.2
UNITS_PER_KM = 26.4
HALF_MILE = 21.1
BLOCK_100 = 5.275  # 100 street numbers = 1/8 mile

# Outer Chicagoland plate.
X_EAST = 16.0
X_WEST_CITY = -379.8  # Harlem
X_WEST = -759.6  # Route 83 / Kingery Hwy (14400 W)
X_PLATE_WEST = -760.0
Y_NORTH_CITY = 400.9  # Howard
Y_SOUTH_CITY = -501.1  # 95th
Y_NORTH = 675.2  # Lake-Cook (12800 N)
Y_SOUTH = -775.4  # 147th / Sibley
Y_PLATE_NORTH = 680.0
Y_PLATE_SOUTH = -760.0

# Fine-grid fill box.
GRID_X0, GRID_X1 = -548.6, 16.0
GRID_Y0, GRID_Y1 = -670.0, 550.0

# Downtown Loop / River North dense sub-grid box.
LOOP_X0, LOOP_X1 = -42.2, 16.0
LOOP_Y0, LOOP_Y1 = -63.3, 42.2

# Airport voids (no internal residential grid).
OHARE = (-548.6, 275.0, -464.2, 358.7)  # xmin, ymin, xmax, ymax
MIDWAY = (-253.2, -332.3, -232.1, -290.1)

# Hierarchy: minor / collector / arterial / expressway (LOD stack).
MINOR_WIDTH, MINOR_Z = 0.22, 0.00
COLLECTOR_WIDTH, COLLECTOR_Z = 0.35, 0.01
SUBURBAN_WIDTH, SUBURBAN_Z = 0.50, 0.02
ARTERIAL_WIDTH, ARTERIAL_Z = 0.55, 0.02
DIAGONAL_WIDTH, DIAGONAL_Z = 0.55, 0.02
EXPRESSWAY_WIDTH, EXPRESSWAY_Z = 0.85, 0.03

ROAD_WIDTH = 0.275  # lot metric; per-route width overrides ribbon size
BYRNE = (-32.0, -15.0)


def yaml_pts(points: list[tuple[float, float]]) -> list[list[float]]:
    return [[round(x, 1), round(y, 1)] for x, y in points]


def _r(v: float) -> float:
    return round(v, 1)


def _add_ns(
    highways: dict,
    key: str,
    x: float,
    y0: float,
    y1: float,
    *,
    lanes: int = 4,
    width: float,
    z_offset: float,
    layer: str,
) -> None:
    if y0 > y1:
        y0, y1 = y1, y0
    if abs(y1 - y0) < 0.05:
        return
    highways[key] = {
        "lanes": lanes,
        "width": width,
        "z_offset": z_offset,
        "layer": layer,
        "points": yaml_pts([(x, y0), (x, y1)]),
    }


def _add_ew(
    highways: dict,
    key: str,
    y: float,
    x0: float,
    x1: float,
    *,
    lanes: int = 4,
    width: float,
    z_offset: float,
    layer: str,
) -> None:
    if x0 > x1:
        x0, x1 = x1, x0
    if abs(x1 - x0) < 0.05:
        return
    highways[key] = {
        "lanes": lanes,
        "width": width,
        "z_offset": z_offset,
        "layer": layer,
        "points": yaml_pts([(x0, y), (x1, y)]),
    }


def _add_route(
    highways: dict,
    key: str,
    points: list[tuple[float, float]],
    *,
    lanes: int = 4,
    width: float,
    z_offset: float,
    layer: str,
) -> None:
    if len(points) < 2:
        return
    highways[key] = {
        "lanes": lanes,
        "width": width,
        "z_offset": z_offset,
        "layer": layer,
        "points": yaml_pts(points),
    }


def _in_rect(x: float, y: float, rect: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1


def _clip_ns(
    x: float, y0: float, y1: float, voids: list[tuple[float, float, float, float]]
) -> list[tuple[float, float]]:
    """Return open Y spans for a vertical line that avoid axis-aligned voids."""
    if y0 > y1:
        y0, y1 = y1, y0
    spans = [(y0, y1)]
    for vx0, vy0, vx1, vy1 in voids:
        if not (vx0 <= x <= vx1):
            continue
        nxt: list[tuple[float, float]] = []
        for a, b in spans:
            lo, hi = max(a, vy0), min(b, vy1)
            if lo >= hi:
                nxt.append((a, b))
                continue
            if a < lo - 0.05:
                nxt.append((a, lo))
            if hi + 0.05 < b:
                nxt.append((hi, b))
        spans = nxt
    return [(a, b) for a, b in spans if b - a > 0.1]


def _clip_ew(
    y: float, x0: float, x1: float, voids: list[tuple[float, float, float, float]]
) -> list[tuple[float, float]]:
    if x0 > x1:
        x0, x1 = x1, x0
    spans = [(x0, x1)]
    for vx0, vy0, vx1, vy1 in voids:
        if not (vy0 <= y <= vy1):
            continue
        nxt: list[tuple[float, float]] = []
        for a, b in spans:
            lo, hi = max(a, vx0), min(b, vx1)
            if lo >= hi:
                nxt.append((a, b))
                continue
            if a < lo - 0.05:
                nxt.append((a, lo))
            if hi + 0.05 < b:
                nxt.append((hi, b))
        spans = nxt
    return [(a, b) for a, b in spans if b - a > 0.1]


def _build_ns_arterials(highways: dict, reserved_x: set[float]) -> None:
    """Primary N–S arterials; listed corridors extend to Lake-Cook / 147th."""
    # (key, x, y0, y1) — extended corridors use full suburban Y.
    full = (Y_SOUTH, Y_NORTH)
    city = (Y_SOUTH_CITY, Y_NORTH_CITY)
    ns = (
        ("michigan", 5.3, *city),
        ("state", 0.0, *full),
        ("halsted", -42.2, *city),
        ("ashland", -84.4, *city),
        ("western", -126.6, *full),
        ("kedzie", -168.8, *full),
        ("pulaski", -211.0, *full),
        ("cicero", -253.2, *full),
        ("central", -295.4, *city),
        ("austin", -316.5, *city),
        ("harlem", -379.8, *full),
    )
    for key, x, y0, y1 in ns:
        reserved_x.add(_r(x))
        _add_ns(
            highways,
            key,
            x,
            y0,
            y1,
            lanes=4,
            width=ARTERIAL_WIDTH,
            z_offset=ARTERIAL_Z,
            layer="arterial",
        )


def _build_ew_arterials(highways: dict, reserved_y: set[float]) -> None:
    """Primary E–W arterials; selected corridors extend west to Route 83."""
    west_ext = {
        "north",
        "irving_park",
        "roosevelt",
        "cermak",
        "garfield",
        "st_79th",
        "st_95th",
        "howard",
        "madison",
    }
    ew = (
        ("howard", 400.9),
        ("devon", 337.6),
        ("bryn_mawr", 295.4),
        ("lawrence", 253.2),
        ("irving_park", 211.0),
        ("belmont", 168.8),
        ("fullerton", 126.6),
        ("north", 84.4),
        ("division", 63.3),
        ("chicago_ave", 42.2),
        ("madison", 0.0),
        ("roosevelt", -63.3),
        ("cermak", -116.0),
        ("st_31st", -163.5),
        ("pershing", -205.7),
        ("st_47th", -247.9),
        ("garfield", -290.1),
        ("st_63rd", -332.3),
        ("st_79th", -416.7),
        ("st_95th", -501.1),
    )
    for key, y in ew:
        reserved_y.add(_r(y))
        x0 = X_WEST if key in west_ext else X_WEST_CITY
        _add_ew(
            highways,
            key,
            y,
            x0,
            X_EAST,
            lanes=4,
            width=ARTERIAL_WIDTH,
            z_offset=ARTERIAL_Z,
            layer="arterial",
        )


def _build_loop_subgrid(highways: dict, reserved_x: set[float], reserved_y: set[float]) -> None:
    ns_loop = (
        ("wabash", 2.6),
        ("dearborn", -1.9),
        ("clark", -5.3),
        ("lasalle", -7.4),
        ("wells", -10.6),
        ("franklin", -15.8),
        ("canal", -26.4),
        ("clinton", -28.5),
    )
    for key, x in ns_loop:
        reserved_x.add(_r(x))
        _add_ns(
            highways,
            key,
            x,
            LOOP_Y0,
            LOOP_Y1,
            lanes=4,
            width=ARTERIAL_WIDTH,
            z_offset=ARTERIAL_Z,
            layer="arterial",
        )
    ew_loop = (
        ("wacker", 15.8),
        ("randolph", 7.9),
        ("washington", 5.3),
        ("adams", -10.6),
        ("jackson", -15.8),
        ("ida_b_wells", -26.4),
        ("harrison", -31.6),
    )
    for key, y in ew_loop:
        reserved_y.add(_r(y))
        _add_ew(
            highways,
            key,
            y,
            LOOP_X0,
            LOOP_X1,
            lanes=4,
            width=ARTERIAL_WIDTH,
            z_offset=ARTERIAL_Z,
            layer="arterial",
        )


def _build_expressways(highways: dict) -> None:
    w, z = EXPRESSWAY_WIDTH, EXPRESSWAY_Z
    _add_route(
        highways,
        "kennedy",
        [
            BYRNE,
            (-84.4, 84.4),
            (-168.8, 168.8),
            (-253.2, 253.2),
            (-265.0, 275.0),
        ],
        lanes=6,
        width=w,
        z_offset=z,
        layer="expressway",
    )
    _add_route(
        highways,
        "edens",
        [(-265.0, 275.0), (-285.0, Y_NORTH_CITY), (-300.0, Y_NORTH)],
        lanes=6,
        width=w,
        z_offset=z,
        layer="expressway",
    )
    _add_route(
        highways,
        "kennedy_ohare",
        [(-265.0, 275.0), (-475.0, 315.0)],
        lanes=6,
        width=w,
        z_offset=z,
        layer="expressway",
    )
    _add_route(
        highways,
        "dan_ryan",
        [BYRNE, (-21.1, Y_SOUTH_CITY), (-21.1, Y_SOUTH)],
        lanes=6,
        width=w,
        z_offset=z,
        layer="expressway",
    )
    _add_route(
        highways,
        "i57",
        [(-21.1, Y_SOUTH_CITY), (-84.4, -580.0), (-126.6, Y_PLATE_SOUTH)],
        lanes=6,
        width=w,
        z_offset=z,
        layer="expressway",
    )
    _add_route(
        highways,
        "bishop_ford",
        [(-21.1, Y_SOUTH_CITY), (65.0, -580.0)],
        lanes=6,
        width=w,
        z_offset=z,
        layer="expressway",
    )
    _add_route(
        highways,
        "eisenhower",
        [BYRNE, (X_WEST_CITY, -15.8), (X_WEST, -15.8)],
        lanes=6,
        width=w,
        z_offset=z,
        layer="expressway",
    )
    _add_route(
        highways,
        "stevenson",
        [
            (0.0, -132.0),
            (-84.4, -175.0),
            (-168.8, -215.0),
            (-253.2, -255.0),
            (X_WEST_CITY, -315.0),
            (X_WEST, -350.0),
        ],
        lanes=6,
        width=w,
        z_offset=z,
        layer="expressway",
    )
    # Tri-State Tollway (I-294) — outer suburban beltway.
    _add_route(
        highways,
        "tri_state",
        [
            (-168.8, -760.0),  # Kedzie & 147th
            (-295.4, -633.0),  # Central & 120th (Alsip / Oak Lawn)
            (-506.4, -332.3),  # 9600 W & 63rd (La Grange / Hinsdale)
            (-548.6, 168.8),  # 10400 W & Belmont (Elmhurst / O'Hare West)
            (-464.2, 464.2),  # Des Plaines / Glenview
            (-379.8, 680.0),  # Harlem & north plate
        ],
        lanes=6,
        width=w,
        z_offset=z,
        layer="expressway",
    )


def _build_diagonals(highways: dict) -> None:
    w, z = DIAGONAL_WIDTH, DIAGONAL_Z
    _add_route(
        highways,
        "milwaukee",
        [(0.0, 0.0), (-84.4, 84.4), (-211.0, 211.0), (-335.0, 335.0), (-379.8, 337.6)],
        lanes=4,
        width=w,
        z_offset=z,
        layer="arterial",
    )
    _add_route(
        highways,
        "archer",
        [(-10.0, -105.5), (-126.6, -211.0), (X_WEST_CITY, -332.3)],
        lanes=4,
        width=w,
        z_offset=z,
        layer="arterial",
    )
    _add_route(
        highways,
        "elston",
        [(-65.0, 42.2), (-285.0, 295.4)],
        lanes=4,
        width=w,
        z_offset=z,
        layer="arterial",
    )
    _add_route(
        highways,
        "lincoln",
        [(-63.3, 105.5), (-211.0, 337.6)],
        lanes=4,
        width=w,
        z_offset=z,
        layer="arterial",
    )


def _build_north_suburbs(
    highways: dict, reserved_x: set[float], reserved_y: set[float]
) -> None:
    """Evanston / Skokie / Lincolnwood / Wilmette arterial frame."""
    x0, x1 = X_WEST_CITY, -42.2
    y0, y1 = Y_NORTH_CITY, Y_PLATE_NORTH
    ew = (
        ("oakton", 422.0),
        ("dempster", 464.2),
        ("golf", 506.4),
        ("old_orchard", 517.0),
        ("glenview_rd", 548.6),
        ("lake_cook", 675.2),
    )
    for key, y in ew:
        reserved_y.add(_r(y))
        # Dempster / Golf / Lake-Cook also run west to Route 83.
        x_west = X_WEST if key in ("dempster", "golf", "lake_cook") else x0
        _add_ew(
            highways,
            key,
            y,
            x_west,
            X_EAST if key == "lake_cook" else x1,
            lanes=4,
            width=SUBURBAN_WIDTH,
            z_offset=SUBURBAN_Z,
            layer="arterial",
        )
    ns = (
        ("ridge", -75.0),
        ("mccormick", -168.8),  # coincides with Kedzie — skip if reserved
        ("crawford", -211.0),  # coincides with Pulaski
        ("skokie_blvd", -253.2),  # coincides with Cicero
        ("waukegan", -358.7),
    )
    for key, x in ns:
        if _r(x) in reserved_x and key != "waukegan" and key != "ridge":
            # Kedzie / Pulaski / Cicero already cover these spines; keep name alias skip.
            continue
        reserved_x.add(_r(x))
        _add_ns(
            highways,
            key,
            x,
            y0,
            y1,
            lanes=4,
            width=SUBURBAN_WIDTH,
            z_offset=SUBURBAN_Z,
            layer="arterial",
        )


def _build_ohare_corridor(
    highways: dict, reserved_x: set[float], reserved_y: set[float]
) -> None:
    """Park Ridge / Niles / Des Plaines / Rosemont + O'Hare perimeter."""
    # O'Hare perimeter frame.
    _add_ns(
        highways,
        "mannheim",
        -548.6,
        211.0,
        550.0,
        lanes=4,
        width=SUBURBAN_WIDTH,
        z_offset=SUBURBAN_Z,
        layer="arterial",
    )
    reserved_x.add(_r(-548.6))
    _add_ns(
        highways,
        "river_rd",
        -485.3,
        211.0,
        550.0,
        lanes=4,
        width=SUBURBAN_WIDTH,
        z_offset=SUBURBAN_Z,
        layer="arterial",
    )
    reserved_x.add(_r(-485.3))
    _add_ew(
        highways,
        "touhy",
        379.8,
        X_WEST,
        X_WEST_CITY,
        lanes=4,
        width=SUBURBAN_WIDTH,
        z_offset=SUBURBAN_Z,
        layer="arterial",
    )
    reserved_y.add(_r(379.8))
    # Higgins — diagonal NW approach past O'Hare south edge.
    _add_route(
        highways,
        "higgins",
        [(-379.8, 295.4), (-548.6, 337.6), (-680.0, 400.0)],
        lanes=4,
        width=SUBURBAN_WIDTH,
        z_offset=SUBURBAN_Z,
        layer="arterial",
    )
    # Northwest radials from Harlem & Devon.
    origin = (-379.8, 337.6)
    end = (-680.0, 580.0)
    _add_route(
        highways,
        "milwaukee_nw",
        [origin, (-506.4, 422.0), (-611.9, 506.4), end],
        lanes=4,
        width=SUBURBAN_WIDTH,
        z_offset=SUBURBAN_Z,
        layer="arterial",
    )
    _add_route(
        highways,
        "northwest_hwy",
        [origin, (-485.3, 400.9), (-548.6, 464.2), (-640.0, 548.6)],
        lanes=4,
        width=SUBURBAN_WIDTH,
        z_offset=SUBURBAN_Z,
        layer="arterial",
    )
    _add_route(
        highways,
        "rand_rd",
        [origin, (-464.2, 379.8), (-548.6, 443.1), (-680.0, 520.0)],
        lanes=4,
        width=SUBURBAN_WIDTH,
        z_offset=SUBURBAN_Z,
        layer="arterial",
    )


def _build_west_suburbs(
    highways: dict, reserved_x: set[float], reserved_y: set[float]
) -> None:
    """Oak Park / Berwyn / Cicero / Elmhurst / Oak Brook frame."""
    y0, y1 = -247.9, 211.0
    ns = (
        ("oak_park_ave", -358.7),
        ("ridgeland", -337.6),
        ("des_plaines_ave", -400.9),
        ("cumberland", -443.1),
        ("york_rd", -611.9),
        ("route_83", -759.6),
    )
    for key, x in ns:
        reserved_x.add(_r(x))
        _add_ns(
            highways,
            key,
            x,
            y0,
            y1,
            lanes=4,
            width=SUBURBAN_WIDTH,
            z_offset=SUBURBAN_Z,
            layer="arterial",
        )
    # Mannheim already added in O'Hare corridor; extend south through west suburbs.
    if "mannheim" in highways:
        # Rebuild full Mannheim spine Belmont band → south suburbs edge.
        _add_ns(
            highways,
            "mannheim",
            -548.6,
            -247.9,
            550.0,
            lanes=4,
            width=SUBURBAN_WIDTH,
            z_offset=SUBURBAN_Z,
            layer="arterial",
        )
    ew = (
        ("lake_st", 21.1),
        ("st_26th", -137.1),
    )
    for key, y in ew:
        reserved_y.add(_r(y))
        _add_ew(
            highways,
            key,
            y,
            X_WEST,
            X_WEST_CITY,
            lanes=4,
            width=SUBURBAN_WIDTH,
            z_offset=SUBURBAN_Z,
            layer="arterial",
        )
    # Ogden Ave (US-34) diagonal.
    _add_route(
        highways,
        "ogden",
        [(-253.2, -116.0), (-379.8, -163.5), (-548.6, -247.9), (X_WEST, -332.3)],
        lanes=4,
        width=SUBURBAN_WIDTH,
        z_offset=SUBURBAN_Z,
        layer="arterial",
    )


def _build_south_suburbs(
    highways: dict, reserved_x: set[float], reserved_y: set[float]
) -> None:
    """Evergreen Park / Oak Lawn / Burbank / Blue Island / Harvey frame."""
    x0, x1 = -548.6, X_EAST
    ew = (
        ("st_103rd", -543.3),
        ("st_111th", -585.5),
        ("st_119th", -627.7),
        ("st_127th", -669.9),
        ("st_147th", -775.4),
    )
    for key, y in ew:
        reserved_y.add(_r(y))
        x_west = X_WEST if key in ("st_111th", "st_127th", "st_147th") else x0
        _add_ew(
            highways,
            key,
            y,
            x_west,
            x1,
            lanes=4,
            width=SUBURBAN_WIDTH,
            z_offset=SUBURBAN_Z,
            layer="arterial",
        )
    _add_route(
        highways,
        "southwest_hwy",
        [(-126.6, -416.7), (-253.2, -501.1), (-379.8, -585.5), (-548.6, -669.9)],
        lanes=4,
        width=SUBURBAN_WIDTH,
        z_offset=SUBURBAN_Z,
        layer="arterial",
    )


def _build_collectors(
    highways: dict, reserved_x: set[float], reserved_y: set[float]
) -> None:
    """0.5-mile secondary collectors across the fine-grid box."""
    w, z = COLLECTOR_WIDTH, COLLECTOR_Z
    ns = (
        ("racine", -63.3),
        ("damen", -105.5),
        ("california", -147.7),
        ("central_park", -189.9),
        ("kostner", -232.1),
        ("laramie", -274.3),
        ("narragansett", -337.6),
    )
    for key, x in ns:
        if _r(x) in reserved_x:
            continue
        reserved_x.add(_r(x))
        for i, (a, b) in enumerate(_clip_ns(x, GRID_Y0, GRID_Y1, [OHARE, MIDWAY])):
            suffix = "" if i == 0 else f"_{i}"
            _add_ns(
                highways,
                f"{key}{suffix}",
                x,
                a,
                b,
                lanes=2,
                width=w,
                z_offset=z,
                layer="collector",
            )
    # Austin already arterial at -316.5 — do not duplicate as collector.
    ew = (
        ("foster", 274.3),
        ("montrose", 232.1),
        ("addison", 189.9),
        ("diversey", 147.7),
        ("armitage", 105.5),
        ("grand", 26.4),
        ("st_18th", -95.0),
        ("st_35th", -184.6),
        ("st_43rd", -226.8),
        ("st_51st", -269.0),
        ("st_59th", -311.2),
        ("st_67th", -353.4),
        ("st_71st", -374.5),
        ("st_75th", -395.6),
        ("st_83rd", -437.8),
        ("st_87th", -458.9),
        ("st_91st", -480.0),
        ("st_99th", -522.2),
        ("st_107th", -564.4),
        ("st_115th", -606.6),
    )
    for key, y in ew:
        if _r(y) in reserved_y:
            continue
        reserved_y.add(_r(y))
        for i, (a, b) in enumerate(_clip_ew(y, GRID_X0, GRID_X1, [OHARE, MIDWAY])):
            suffix = "" if i == 0 else f"_{i}"
            _add_ew(
                highways,
                f"{key}{suffix}",
                y,
                a,
                b,
                lanes=2,
                width=w,
                z_offset=z,
                layer="collector",
            )


def _mile_index(v: float, origin: float = 0.0) -> int:
    return int(__import__("math").floor((v - origin) / UNITS_PER_MILE))


def _suburban_orientation(mx: int, my: int) -> str:
    """Alternate N–S vs E–W minor fill per mile section."""
    return "ns" if (mx + my) % 2 == 0 else "ew"


def _build_minor_grid(
    highways: dict, reserved_x: set[float], reserved_y: set[float]
) -> None:
    """1/8-mile minor residential streets (batched as layer=minor)."""
    w, z = MINOR_WIDTH, MINOR_Z
    voids = [OHARE, MIDWAY]
    xs: list[float] = []
    yv = GRID_X0
    while yv <= GRID_X1 + 1e-6:
        xs.append(_r(yv))
        yv += BLOCK_100
    ys: list[float] = []
    xv = GRID_Y0
    while xv <= GRID_Y1 + 1e-6:
        ys.append(_r(xv))
        xv += BLOCK_100

    ns_n = 0
    for x in xs:
        if x in reserved_x:
            continue
        # Urban orthogonal core: east of Harlem and south of Howard.
        urban = x >= X_WEST_CITY
        if urban:
            for i, (a, b) in enumerate(_clip_ns(x, GRID_Y0, min(GRID_Y1, Y_NORTH_CITY), voids)):
                _add_ns(
                    highways,
                    f"mns_{ns_n}",
                    x,
                    a,
                    b,
                    lanes=2,
                    width=w,
                    z_offset=z,
                    layer="minor",
                )
                ns_n += 1
            # North of Howard: suburban orientation by mile section.
            if GRID_Y1 > Y_NORTH_CITY:
                for my_y0 in _frange(Y_NORTH_CITY, GRID_Y1, UNITS_PER_MILE):
                    my_y1 = min(my_y0 + UNITS_PER_MILE, GRID_Y1)
                    mx = _mile_index(x)
                    my = _mile_index(my_y0)
                    if _suburban_orientation(mx, my) != "ns":
                        continue
                    for i, (a, b) in enumerate(_clip_ns(x, my_y0, my_y1, voids)):
                        _add_ns(
                            highways,
                            f"mns_{ns_n}",
                            x,
                            a,
                            b,
                            lanes=2,
                            width=w,
                            z_offset=z,
                            layer="minor",
                        )
                        ns_n += 1
        else:
            # West of Harlem: suburban orientation by mile section.
            for my_y0 in _frange(GRID_Y0, GRID_Y1, UNITS_PER_MILE):
                my_y1 = min(my_y0 + UNITS_PER_MILE, GRID_Y1)
                mx = _mile_index(x)
                my = _mile_index(my_y0)
                if _suburban_orientation(mx, my) != "ns":
                    continue
                y_lo = max(my_y0, GRID_Y0)
                y_hi = min(my_y1, GRID_Y1)
                for i, (a, b) in enumerate(_clip_ns(x, y_lo, y_hi, voids)):
                    _add_ns(
                        highways,
                        f"mns_{ns_n}",
                        x,
                        a,
                        b,
                        lanes=2,
                        width=w,
                        z_offset=z,
                        layer="minor",
                    )
                    ns_n += 1

    ew_n = 0
    for y in ys:
        if y in reserved_y:
            continue
        # Urban: south of Howard, east of Harlem — full EW minors.
        if y <= Y_NORTH_CITY:
            for i, (a, b) in enumerate(
                _clip_ew(y, max(GRID_X0, X_WEST_CITY), GRID_X1, voids)
            ):
                _add_ew(
                    highways,
                    f"mew_{ew_n}",
                    y,
                    a,
                    b,
                    lanes=2,
                    width=w,
                    z_offset=z,
                    layer="minor",
                )
                ew_n += 1
            # West of Harlem at this Y: suburban orientation.
            if GRID_X0 < X_WEST_CITY:
                for mx_x0 in _frange(GRID_X0, X_WEST_CITY, UNITS_PER_MILE):
                    mx_x1 = min(mx_x0 + UNITS_PER_MILE, X_WEST_CITY)
                    mx = _mile_index(mx_x0)
                    my = _mile_index(y)
                    if _suburban_orientation(mx, my) != "ew":
                        continue
                    for i, (a, b) in enumerate(_clip_ew(y, mx_x0, mx_x1, voids)):
                        _add_ew(
                            highways,
                            f"mew_{ew_n}",
                            y,
                            a,
                            b,
                            lanes=2,
                            width=w,
                            z_offset=z,
                            layer="minor",
                        )
                        ew_n += 1
        else:
            # North of Howard: suburban EW by mile section across full grid X.
            for mx_x0 in _frange(GRID_X0, GRID_X1, UNITS_PER_MILE):
                mx_x1 = min(mx_x0 + UNITS_PER_MILE, GRID_X1)
                mx = _mile_index(mx_x0)
                my = _mile_index(y)
                if _suburban_orientation(mx, my) != "ew":
                    continue
                for i, (a, b) in enumerate(_clip_ew(y, mx_x0, mx_x1, voids)):
                    _add_ew(
                        highways,
                        f"mew_{ew_n}",
                        y,
                        a,
                        b,
                        lanes=2,
                        width=w,
                        z_offset=z,
                        layer="minor",
                    )
                    ew_n += 1


def _frange(start: float, stop: float, step: float) -> list[float]:
    out: list[float] = []
    v = start
    # Inclusive start; stop is exclusive upper bound for cell origins.
    while v < stop - 1e-6:
        out.append(_r(v))
        v += step
    return out


def build() -> dict:
    highways: dict = {}
    reserved_x: set[float] = set()
    reserved_y: set[float] = set()

    _build_ns_arterials(highways, reserved_x)
    _build_ew_arterials(highways, reserved_y)
    _build_loop_subgrid(highways, reserved_x, reserved_y)
    _build_expressways(highways)
    _build_diagonals(highways)
    _build_north_suburbs(highways, reserved_x, reserved_y)
    _build_ohare_corridor(highways, reserved_x, reserved_y)
    _build_west_suburbs(highways, reserved_x, reserved_y)
    _build_south_suburbs(highways, reserved_x, reserved_y)
    _build_collectors(highways, reserved_x, reserved_y)
    _build_minor_grid(highways, reserved_x, reserved_y)

    return {
        "lot": {
            "block_size": [0.5, 0.5, 0.4],
            "tower_count": 5,
            "tower_gap": 0.15,
            "road_width": ROAD_WIDTH,
            "floor_min": 10,
            "floor_max": 25,
            "towers_per_ring": 10,
        },
        "highway": {
            "lanes": 4,
            "fence_w": 0.0,
            "fence_h": 0.0,
            "barrier_w": 0.0,
            "barrier_h": 0.0,
            "keepout": 0.12,
        },
        "highways": highways,
        "neighborhoods": [],
        "streets": {},
    }


def main() -> None:
    data = build()
    layers = {}
    for entry in data["highways"].values():
        layer = entry.get("layer", "arterial")
        layers[layer] = layers.get(layer, 0) + 1
    header = (
        "# Chicagoland Pure Arterial Grid — 2× roads-only plate (suburbs + minors).\n"
        f"# Origin (0,0): State Street & Madison Street (Downtown Loop).\n"
        f"# Scale: {UNITS_PER_MILE:g} units = 1.0 mile = 800 street numbers; "
        f"{UNITS_PER_KM:g} units = 1.0 km.\n"
        f"# Every 100 street numbers = {BLOCK_100:g} Panda3D units.\n"
        f"# Plate: X∈[{X_PLATE_WEST:g},{X_EAST:g}]  Y∈[{Y_PLATE_SOUTH:g},{Y_PLATE_NORTH:g}].\n"
        f"# Layers: minor w={MINOR_WIDTH} Z={MINOR_Z}; "
        f"collector w={COLLECTOR_WIDTH} Z=+{COLLECTOR_Z}; "
        f"arterial w={ARTERIAL_WIDTH}/{SUBURBAN_WIDTH} Z=+{ARTERIAL_Z}; "
        f"expressway w={EXPRESSWAY_WIDTH} Z=+{EXPRESSWAY_Z}.\n"
        f"# Route counts by layer: {layers}.\n"
        "# Ground plane Z=-0.25. Camera far clip: 10000. 4× MSAA + flattenStrong.\n"
        "# Generated by city/calibrate_chicago_2x.py — re-run to regenerate.\n"
    )
    body = yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=None,
        width=88,
    )
    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len(data['highways'])} highway routes) layers={layers}")


if __name__ == "__main__":
    main()
