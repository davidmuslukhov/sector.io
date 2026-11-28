"""Chicago CTA \"L\" rapid transit at 2× map scale.

Builds the Downtown Loop elevated rectangle, 7 color-coded lines (Red, Blue,
Green, Orange, Brown, Pink, Purple), elevated / median stations, and animated
multi-car stainless trains. Static infrastructure is batched per 1-mile sector
with ``flattenStrong``; train cars share a single procedural GeomNode template.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from panda3d.core import Material, NodePath

from city.collision2d import register_pillar
from city.materials import concrete_material, rgba_material
from city.mesh import box_instance, make_flat_deck_batch

# ---------------------------------------------------------------------------
# Scale / elevations / materials
# ---------------------------------------------------------------------------
UNITS_PER_MILE = 42.2
SECTOR_SIZE = UNITS_PER_MILE
PILLAR_SPACING = 2.2
LOOP_CORNER_R = 0.65
LOOP_CORNER_SEGS = 12
# Colliders are denser than needed for driving under the L — keep every Nth.
PILLAR_COLLIDER_STRIDE = 2

Z_ELEV = 0.55
Z_RAIL = 0.57
Z_MEDIAN = 0.04
Z_SUBWAY = -0.45
Z_FLYOVER = 0.65
Z_PLATFORM_ELEV = 0.56
Z_PLATFORM_MED = 0.05
Z_CANOPY = 0.76

DECK_W_DBL = 0.34
DECK_W_SGL = 0.22
DECK_THICK = 0.04
RAIL_W = 0.018
RAIL_GAP = 0.09
TIE_SPACING = 0.42
PILLAR_SZ = 0.05
BARRIER_H = 0.14

STEEL_RGBA = (0.22, 0.24, 0.27, 1.0)
RAIL_RGBA = (0.55, 0.57, 0.60, 1.0)
TIE_RGBA = (0.35, 0.22, 0.12, 1.0)
BALLAST_RGBA = (0.32, 0.31, 0.30, 1.0)
PLATFORM_RGBA = (0.58, 0.52, 0.44, 1.0)
CANOPY_RGBA = (0.42, 0.44, 0.46, 1.0)
BRICK_RGBA = (0.48, 0.28, 0.22, 1.0)
CAR_STEEL_RGBA = (0.76, 0.78, 0.81, 1.0)
CAR_ROOF_RGBA = (0.18, 0.18, 0.20, 1.0)
WINDOW_RGB = (1.0, 0.85, 0.45)
HEADLIGHT_RGB = (1.0, 1.0, 0.92)
TAILLIGHT_RGB = (1.0, 0.12, 0.08)

CAR_LEN = 0.32
CAR_W = 0.11
CAR_H = 0.13
CAR_GAP = 0.02
TRAIN_SPEED_EXPRESS = 2.8
TRAIN_SPEED_LOOP = 1.6
DWELL_SEC = 3.0
HEADWAY = 2.5
STATION_STOP_R2 = 0.55 * 0.55

# LOD — hide far sectors in overview (same spirit as airports / housing).
CTA_HIDE_DIST = 380.0
CTA_VIEW_FACTOR = 0.40
CTA_VIEW_MIN = 70.0
CTA_MAX_TILES = 14
# Hide / skip placing train meshes beyond this look-at radius (sim still ticks).
CTA_TRAIN_HIDE_DIST = 110.0

# Downtown Loop rectangle (exact corridors).
LOOP_WELLS = -10.55
LOOP_WABASH = 2.64
LOOP_LAKE = 10.55
LOOP_VAN_BUREN = -21.10

LINE_COLORS: dict[str, tuple[float, float, float, float]] = {
    "red": (0.89, 0.10, 0.21, 1.0),
    "blue": (0.00, 0.63, 0.87, 1.0),
    "green": (0.00, 0.61, 0.29, 1.0),
    "orange": (0.98, 0.27, 0.11, 1.0),
    "brown": (0.38, 0.21, 0.14, 1.0),
    "pink": (0.89, 0.49, 0.65, 1.0),
    "purple": (0.32, 0.14, 0.60, 1.0),
}

_EMISSIVE: dict[tuple, Material] = {}


def _emissive(rgb: tuple[float, float, float], strength: float = 1.0) -> Material:
    key = (round(rgb[0], 3), round(rgb[1], 3), round(rgb[2], 3), round(strength, 2))
    cached = _EMISSIVE.get(key)
    if cached is not None:
        return cached
    mat = Material()
    em = (rgb[0] * strength, rgb[1] * strength, rgb[2] * strength)
    mat.setAmbient((*rgb, 1))
    mat.setDiffuse((*rgb, 1))
    mat.setEmission((*em, 1))
    mat.setShininess(16)
    _EMISSIVE[key] = mat
    return mat


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _unit(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy) or 1.0
    return dx / length, dy / length


def _perp(ux: float, uy: float) -> tuple[float, float]:
    return -uy, ux


def _sector_key(x: float, y: float) -> tuple[int, int]:
    return (int(math.floor(x / SECTOR_SIZE)), int(math.floor(y / SECTOR_SIZE)))


def _arc(
    cx: float,
    cy: float,
    radius: float,
    a0: float,
    a1: float,
    z: float,
    *,
    segs: int = LOOP_CORNER_SEGS,
) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = []
    for i in range(segs + 1):
        t = i / segs
        a = a0 + (a1 - a0) * t
        pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a), z))
    return pts


def _polyline_length(pts: list[tuple[float, float, float]]) -> float:
    total = 0.0
    for i in range(1, len(pts)):
        total += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
    return total


def _panda_heading(dx: float, dy: float) -> float:
    """Panda3D H degrees: 0 faces +Y, positive toward +X (``atan2(dx, dy)``)."""
    return math.degrees(math.atan2(dx, dy))


def _sample_polyline(
    pts: list[tuple[float, float, float]],
    dist: float,
) -> tuple[float, float, float, float]:
    """Return (x, y, z, panda_heading_deg) at arc-length ``dist`` along ``pts``."""
    if len(pts) < 2:
        p = pts[0] if pts else (0.0, 0.0, Z_ELEV)
        return p[0], p[1], p[2], 0.0
    if dist <= 0.0:
        dx = pts[1][0] - pts[0][0]
        dy = pts[1][1] - pts[0][1]
        return pts[0][0], pts[0][1], pts[0][2], _panda_heading(dx, dy)
    remaining = dist
    for i in range(1, len(pts)):
        x0, y0, z0 = pts[i - 1]
        x1, y1, z1 = pts[i]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg < 1e-9:
            continue
        if remaining <= seg:
            t = remaining / seg
            return (
                x0 + (x1 - x0) * t,
                y0 + (y1 - y0) * t,
                z0 + (z1 - z0) * t,
                _panda_heading(x1 - x0, y1 - y0),
            )
        remaining -= seg
    x0, y0, z0 = pts[-2]
    x1, y1, z1 = pts[-1]
    return x1, y1, z1, _panda_heading(x1 - x0, y1 - y0)


def _densify(
    pts: list[tuple[float, float, float]],
    step: float = 2.0,
) -> list[tuple[float, float, float]]:
    """Insert intermediate points so consecutive samples are ≤ ``step`` apart."""
    if len(pts) < 2:
        return list(pts)
    out: list[tuple[float, float, float]] = [pts[0]]
    for i in range(1, len(pts)):
        x0, y0, z0 = out[-1]
        x1, y1, z1 = pts[i]
        dist = math.hypot(x1 - x0, y1 - y0)
        if dist <= step:
            out.append(pts[i])
            continue
        n = max(1, int(math.ceil(dist / step)))
        for k in range(1, n + 1):
            t = k / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, z0 + (z1 - z0) * t))
    return out


# ---------------------------------------------------------------------------
# Track / station data buckets (per sector)
# ---------------------------------------------------------------------------
STRIPE_W = 0.055
STRIPE_Z_LIFT = 0.012
# Lateral offsets so multiple Loop lines stay readable side-by-side.
_LINE_STRIPE_OFFSET: dict[str, float] = {
    "red": 0.0,
    "blue": 0.0,
    "green": -0.08,
    "orange": -0.04,
    "brown": 0.04,
    "pink": 0.08,
    "purple": 0.12,
}


@dataclass
class _SectorBucket:
    decks: list[tuple[float, float, float, float, float, float]] = field(default_factory=list)
    rails: list[tuple[float, float, float, float, float, float]] = field(default_factory=list)
    ballast: list[tuple[float, float, float, float, float, float]] = field(default_factory=list)
    pillars: list[tuple[float, float, float]] = field(default_factory=list)  # x, y, h
    barriers: list[tuple[float, float, float, float, float, float]] = field(default_factory=list)
    ties: list[tuple[float, float, float, float]] = field(default_factory=list)  # x,y,z,heading
    # line -> colored center-stripe segments
    stripes: dict[str, list[tuple[float, float, float, float, float, float]]] = field(
        default_factory=dict
    )
    stations: list[dict] = field(default_factory=list)


def _add_track_seg(
    buckets: dict[tuple[int, int], _SectorBucket],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    z: float,
    *,
    double: bool = True,
    elevated: bool = True,
    line: str | None = None,
) -> None:
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 0.05:
        return
    ux, uy = _unit(x1 - x0, y1 - y0)
    nx, ny = _perp(ux, uy)
    width = DECK_W_DBL if double else DECK_W_SGL
    mid_x = (x0 + x1) * 0.5
    mid_y = (y0 + y1) * 0.5
    key = _sector_key(mid_x, mid_y)
    bucket = buckets.setdefault(key, _SectorBucket())

    if elevated:
        bucket.decks.append((x0, y0, x1, y1, width, z))
        for sign in (-1.0, 1.0):
            ox, oy = nx * RAIL_GAP * sign, ny * RAIL_GAP * sign
            bucket.rails.append(
                (x0 + ox, y0 + oy, x1 + ox, y1 + oy, RAIL_W, Z_RAIL)
            )
        n_ties = max(1, int(length / TIE_SPACING))
        heading = _panda_heading(ux, uy)
        for i in range(n_ties):
            t = (i + 0.5) / n_ties
            bucket.ties.append((x0 + ux * length * t, y0 + uy * length * t, z + 0.01, heading))
        n_pillars = max(1, int(length / PILLAR_SPACING))
        offset = width * 0.42
        for i in range(n_pillars + 1):
            t = i / max(n_pillars, 1)
            px = x0 + ux * length * t
            py = y0 + uy * length * t
            for sign in (-1.0, 1.0):
                bucket.pillars.append((px + nx * offset * sign, py + ny * offset * sign, z))
    else:
        bucket.ballast.append((x0, y0, x1, y1, width + 0.08, z))
        for sign in (-1.0, 1.0):
            ox, oy = nx * RAIL_GAP * sign, ny * RAIL_GAP * sign
            bucket.rails.append(
                (x0 + ox, y0 + oy, x1 + ox, y1 + oy, RAIL_W, z + 0.015)
            )
        wall_off = width * 0.5 + 0.06
        for sign in (-1.0, 1.0):
            ox, oy = nx * wall_off * sign, ny * wall_off * sign
            bucket.barriers.append(
                (x0 + ox, y0 + oy, x1 + ox, y1 + oy, 0.04, z + BARRIER_H * 0.5)
            )

    if line is not None and line in LINE_COLORS:
        off = _LINE_STRIPE_OFFSET.get(line, 0.0)
        sx0, sy0 = x0 + nx * off, y0 + ny * off
        sx1, sy1 = x1 + nx * off, y1 + ny * off
        stripe_z = (Z_RAIL if elevated else z + 0.02) + STRIPE_Z_LIFT
        bucket.stripes.setdefault(line, []).append(
            (sx0, sy0, sx1, sy1, STRIPE_W, stripe_z)
        )


def _add_polyline_track(
    buckets: dict[tuple[int, int], _SectorBucket],
    pts: list[tuple[float, float, float]],
    *,
    double: bool = True,
    elevated: bool | None = None,
    line: str | None = None,
) -> None:
    for i in range(1, len(pts)):
        x0, y0, z0 = pts[i - 1]
        x1, y1, z1 = pts[i]
        z = (z0 + z1) * 0.5
        if z < 0.0:
            continue  # subway — no surface infrastructure
        is_elev = elevated if elevated is not None else z >= 0.3
        _add_track_seg(
            buckets, x0, y0, x1, y1, z, double=double, elevated=is_elev, line=line
        )


def _add_polyline_stripes(
    buckets: dict[tuple[int, int], _SectorBucket],
    pts: list[tuple[float, float, float]],
    line: str,
) -> None:
    """Color stripe only (no deck) — used to paint Loop-shared corridors."""
    if line not in LINE_COLORS:
        return
    off = _LINE_STRIPE_OFFSET.get(line, 0.0)
    for i in range(1, len(pts)):
        x0, y0, z0 = pts[i - 1]
        x1, y1, z1 = pts[i]
        z = (z0 + z1) * 0.5
        if z < 0.0:
            continue
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 0.05:
            continue
        ux, uy = _unit(x1 - x0, y1 - y0)
        nx, ny = _perp(ux, uy)
        elevated = z >= 0.3
        stripe_z = (Z_RAIL if elevated else z + 0.02) + STRIPE_Z_LIFT
        key = _sector_key((x0 + x1) * 0.5, (y0 + y1) * 0.5)
        bucket = buckets.setdefault(key, _SectorBucket())
        bucket.stripes.setdefault(line, []).append(
            (
                x0 + nx * off,
                y0 + ny * off,
                x1 + nx * off,
                y1 + ny * off,
                STRIPE_W,
                stripe_z,
            )
        )


# ---------------------------------------------------------------------------
# Loop rectangle + line polylines
# ---------------------------------------------------------------------------
def _loop_circuit(z: float = Z_ELEV) -> list[tuple[float, float, float]]:
    """Clockwise elevated Loop from NW corner (Tower 18), rounded corners."""
    r = LOOP_CORNER_R
    w, e = LOOP_WELLS, LOOP_WABASH
    n, s = LOOP_LAKE, LOOP_VAN_BUREN
    pts: list[tuple[float, float, float]] = []
    # North: Lake St (W→E), then NE corner.
    pts.append((w + r, n, z))
    pts.append((e - r, n, z))
    pts.extend(_arc(e - r, n - r, r, math.pi * 0.5, 0.0, z)[1:])
    # East: Wabash (N→S), then SE corner.
    pts.append((e, s + r, z))
    pts.extend(_arc(e - r, s + r, r, 0.0, -math.pi * 0.5, z)[1:])
    # South: Van Buren (E→W), then SW corner.
    pts.append((w + r, s, z))
    pts.extend(_arc(w + r, s + r, r, -math.pi * 0.5, -math.pi, z)[1:])
    # West: Wells (S→N), then NW corner back to start.
    pts.append((w, n - r, z))
    pts.extend(_arc(w + r, n - r, r, math.pi, math.pi * 0.5, z)[1:])
    return pts


def _loop_partial(
    start: str,
    end: str,
    *,
    z: float = Z_ELEV,
    clockwise: bool = True,
) -> list[tuple[float, float, float]]:
    """Slice of the Loop between named corners: nw, ne, se, sw."""
    full = _loop_circuit(z)
    # Landmark indices roughly at corner mid-arcs.
    r = LOOP_CORNER_R
    landmarks = {
        "nw": (LOOP_WELLS + r * 0.3, LOOP_LAKE - r * 0.3),
        "ne": (LOOP_WABASH - r * 0.3, LOOP_LAKE - r * 0.3),
        "se": (LOOP_WABASH - r * 0.3, LOOP_VAN_BUREN + r * 0.3),
        "sw": (LOOP_WELLS + r * 0.3, LOOP_VAN_BUREN + r * 0.3),
    }

    def nearest(name: str) -> int:
        tx, ty = landmarks[name]
        best_i, best_d = 0, 1e18
        for i, (x, y, _z) in enumerate(full):
            d = (x - tx) ** 2 + (y - ty) ** 2
            if d < best_d:
                best_d = d
                best_i = i
        return best_i

    i0, i1 = nearest(start), nearest(end)
    n = len(full)
    if clockwise:
        if i1 <= i0:
            i1 += n
        return [full[i % n] for i in range(i0, i1 + 1)]
    # Counter-clockwise.
    if i0 <= i1:
        i0 += n
    return [full[i % n] for i in range(i0, i1 - 1, -1)]


def _line_paths() -> dict[str, list[tuple[float, float, float]]]:
    """Continuous spline waypoints for all 7 CTA lines (outbound primary)."""
    paths: dict[str, list[tuple[float, float, float]]] = {}

    # ---- Red: Howard → 95th/Dan Ryan ----
    red: list[tuple[float, float, float]] = [
        (-26.4, 400.9, Z_ELEV),  # Howard
        (-26.4, 358.0, Z_ELEV),  # Loyola
        (-26.4, 316.0, Z_ELEV),  # Bryn Mawr
        (-26.4, 253.2, Z_ELEV),  # Wilson
        (-26.4, 168.8, Z_ELEV),  # Belmont
        (-26.4, 126.6, Z_ELEV),  # Fullerton
        (-15.8, 84.4, Z_ELEV),  # North/Clybourn
        (-5.3, 63.3, Z_ELEV),  # Clark/Division
        (0.0, 42.2, Z_SUBWAY),  # State subway portal N
        (0.0, 10.55, Z_SUBWAY),
        (0.0, 0.0, Z_SUBWAY),
        (0.0, -21.1, Z_SUBWAY),
        (0.0, -63.3, Z_SUBWAY),  # Roosevelt subway
        (-10.5, -63.3, Z_ELEV),  # ramp / Roosevelt elevated
        (-21.1, -84.0, Z_MEDIAN),  # Dan Ryan median
        (-21.1, -185.0, Z_MEDIAN),
        (-21.1, -290.0, Z_MEDIAN),
        (-21.1, -400.0, Z_MEDIAN),
        (-21.1, -501.1, Z_MEDIAN),  # 95th
    ]
    paths["red"] = _densify(red, 4.0)

    # ---- Blue: O'Hare → Forest Park ----
    blue: list[tuple[float, float, float]] = [
        (-516.0, 329.0, Z_MEDIAN),  # O'Hare
        (-450.0, 310.0, Z_MEDIAN),
        (-380.0, 285.0, Z_MEDIAN),
        (-285.0, 253.2, Z_MEDIAN),  # Jefferson Park
        (-230.0, 210.0, Z_MEDIAN),
        (-185.0, 168.8, Z_MEDIAN),  # Logan Square
        (-145.0, 126.0, Z_ELEV),
        (-105.5, 84.4, Z_ELEV),  # Damen
        (-63.0, 55.0, Z_ELEV),
        (-5.3, 30.0, Z_SUBWAY),  # Dearborn subway
        (-5.3, 10.55, Z_SUBWAY),
        (-5.3, 0.0, Z_SUBWAY),
        (-5.3, -15.8, Z_SUBWAY),
        (-42.2, -15.8, Z_MEDIAN),  # Eisenhower median
        (-84.4, -15.8, Z_MEDIAN),  # UIC-Halsted
        (-168.8, -15.8, Z_MEDIAN),  # Western
        (-253.2, -15.8, Z_MEDIAN),  # Cicero
        (-337.6, -15.8, Z_MEDIAN),  # Oak Park
        (-400.9, -15.8, Z_MEDIAN),  # Forest Park
    ]
    paths["blue"] = _densify(blue, 4.0)

    # ---- Green: Harlem/Lake → Loop → 63rd split (Ashland branch as primary) ----
    green: list[tuple[float, float, float]] = [
        (-379.8, 10.55, Z_ELEV),  # Harlem/Lake
        (-337.6, 10.55, Z_ELEV),
        (-253.2, 10.55, Z_ELEV),  # Cicero
        (-168.8, 10.55, Z_ELEV),  # Kedzie
        (-84.4, 10.55, Z_ELEV),  # Ashland
        (-10.55, 10.55, Z_FLYOVER),  # Tower 18
    ]
    green.extend(_loop_partial("nw", "ne", z=Z_ELEV)[1:])
    green.extend(_loop_partial("ne", "se", z=Z_ELEV)[1:])
    green.extend(
        [
            (2.64, -63.3, Z_ELEV),
            (2.64, -126.0, Z_ELEV),
            (2.64, -211.0, Z_ELEV),  # 40th / Indiana jog
            (18.0, -211.0, Z_ELEV),
            (18.0, -290.0, Z_ELEV),
            (18.0, -332.3, Z_ELEV),  # 63rd
            (-84.4, -332.3, Z_ELEV),  # Ashland/63rd
        ]
    )
    paths["green"] = _densify(green, 4.0)
    # Cottage Grove branch stored as green_east for a second train set.
    green_e: list[tuple[float, float, float]] = [
        (18.0, -332.3, Z_ELEV),
        (42.2, -332.3, Z_ELEV),
    ]
    # Full path to Cottage Grove via same trunk.
    green_cot = list(green[:-1]) + green_e
    paths["green_cottage"] = _densify(green_cot, 4.0)

    # ---- Orange: Midway → Tower 12 / Loop ----
    orange: list[tuple[float, float, float]] = [
        (-250.0, -310.0, Z_ELEV),  # Midway
        (-210.0, -270.0, Z_ELEV),
        (-168.8, -230.0, Z_ELEV),  # Pulaski
        (-126.0, -190.0, Z_ELEV),  # Kedzie
        (-84.4, -160.0, Z_ELEV),  # Western
        (-42.2, -132.0, Z_ELEV),  # Halsted / 35th-Archer
        (-21.0, -84.0, Z_ELEV),
        (2.64, -42.0, Z_ELEV),
        (2.64, -21.10, Z_FLYOVER),  # Tower 12
    ]
    orange.extend(_loop_partial("se", "ne", clockwise=False, z=Z_ELEV)[1:])
    orange.extend(_loop_partial("ne", "nw", clockwise=False, z=Z_ELEV)[1:])
    orange.extend(_loop_partial("nw", "sw", clockwise=False, z=Z_ELEV)[1:])
    # Close back toward Tower 12 along Van Buren for a continuous circuit feel.
    orange.extend(_loop_partial("sw", "se", clockwise=False, z=Z_ELEV)[1:])
    paths["orange"] = _densify(orange, 3.5)

    # ---- Brown: Kimball → Tower 18 / Loop ----
    brown: list[tuple[float, float, float]] = [
        (-179.4, 253.2, Z_ELEV),  # Kimball
        (-140.0, 253.2, Z_ELEV),
        (-95.0, 253.2, Z_ELEV),  # Ravenswood turn
        (-95.0, 211.0, Z_ELEV),  # Irving Park
        (-95.0, 190.0, Z_ELEV),  # Addison
        (-95.0, 175.0, Z_ELEV),  # Southport approach
        (-26.4, 168.8, Z_ELEV),  # Belmont merge
        (-26.4, 126.6, Z_ELEV),  # Fullerton
        (-18.0, 84.0, Z_ELEV),
        (-10.55, 42.2, Z_ELEV),
        (-10.55, 10.55, Z_FLYOVER),  # Tower 18
    ]
    brown.extend(_loop_partial("nw", "ne", z=Z_ELEV)[1:])
    brown.extend(_loop_partial("ne", "se", z=Z_ELEV)[1:])
    brown.extend(_loop_partial("se", "sw", z=Z_ELEV)[1:])
    brown.extend(_loop_partial("sw", "nw", z=Z_ELEV)[1:])
    paths["brown"] = _densify(brown, 3.5)

    # ---- Pink: 54th/Cermak → Loop via Paulina ----
    pink: list[tuple[float, float, float]] = [
        (-285.0, -116.0, Z_ELEV),  # 54th/Cermak
        (-253.2, -110.0, Z_ELEV),
        (-168.8, -110.0, Z_ELEV),  # Kedzie
        (-126.0, -110.0, Z_ELEV),  # Western
        (-89.7, -110.0, Z_ELEV),  # Paulina turn
        (-89.7, -63.3, Z_ELEV),
        (-89.7, -21.1, Z_ELEV),  # Polk / IMD
        (-89.7, 10.55, Z_ELEV),  # Lake St merge
        (-42.2, 10.55, Z_ELEV),
        (-10.55, 10.55, Z_FLYOVER),  # Tower 18
    ]
    pink.extend(_loop_partial("nw", "ne", z=Z_ELEV)[1:])
    pink.extend(_loop_partial("ne", "se", z=Z_ELEV)[1:])
    pink.extend(_loop_partial("se", "sw", z=Z_ELEV)[1:])
    pink.extend(_loop_partial("sw", "nw", z=Z_ELEV)[1:])
    paths["pink"] = _densify(pink, 3.5)

    # ---- Purple Express: Linden → Howard → Loop ----
    purple: list[tuple[float, float, float]] = [
        (-68.0, 485.0, Z_ELEV),  # Linden
        (-55.0, 460.0, Z_ELEV),
        (-42.0, 440.0, Z_ELEV),  # Davis / Evanston
        (-35.0, 420.0, Z_ELEV),  # Dempster / Main
        (-26.4, 400.9, Z_ELEV),  # Howard
        (-26.4, 316.0, Z_ELEV),
        (-26.4, 253.2, Z_ELEV),
        (-26.4, 168.8, Z_ELEV),  # Belmont
        (-26.4, 126.6, Z_ELEV),  # Fullerton
        (-18.0, 84.0, Z_ELEV),
        (-10.55, 42.2, Z_ELEV),
        (-10.55, 10.55, Z_FLYOVER),  # Tower 18
    ]
    purple.extend(_loop_partial("nw", "ne", z=Z_ELEV)[1:])
    purple.extend(_loop_partial("ne", "se", z=Z_ELEV)[1:])
    purple.extend(_loop_partial("se", "sw", z=Z_ELEV)[1:])
    purple.extend(_loop_partial("sw", "nw", z=Z_ELEV)[1:])
    paths["purple"] = _densify(purple, 4.0)

    return paths


def _station_defs() -> list[dict]:
    """~45 key CTA stations with line color tags."""
    # name, x, y, lines, elevated?, hub?
    raw = [
        # Red
        ("Howard", -26.4, 400.9, ("red", "purple"), True, False),
        ("Loyola", -26.4, 358.0, ("red",), True, False),
        ("Bryn Mawr", -26.4, 316.0, ("red",), True, False),
        ("Wilson", -26.4, 253.2, ("red", "purple"), True, False),
        ("Belmont", -26.4, 168.8, ("red", "brown", "purple"), True, True),
        ("Fullerton", -26.4, 126.6, ("red", "brown", "purple"), True, True),
        ("North/Clybourn", -15.8, 84.4, ("red",), True, False),
        ("Clark/Division", -5.3, 63.3, ("red",), True, False),
        ("Chicago (State)", 0.0, 42.2, ("red",), False, False),
        ("Lake (State)", 0.0, 10.55, ("red",), False, True),
        ("Monroe (State)", 0.0, 0.0, ("red",), False, False),
        ("Jackson (State)", 0.0, -21.1, ("red",), False, False),
        ("Roosevelt", -10.5, -63.3, ("red", "orange", "green"), True, True),
        ("Sox-35th", -21.1, -185.0, ("red",), False, False),
        ("47th (Dan Ryan)", -21.1, -247.9, ("red",), False, False),
        ("63rd (Dan Ryan)", -21.1, -332.3, ("red",), False, False),
        ("79th", -21.1, -416.0, ("red",), False, False),
        ("95th/Dan Ryan", -21.1, -501.1, ("red",), False, False),
        # Blue
        ("O'Hare", -516.0, 329.0, ("blue",), False, True),
        ("Jefferson Park", -285.0, 253.2, ("blue",), False, False),
        ("Logan Square", -185.0, 168.8, ("blue",), False, False),
        ("Damen", -105.5, 84.4, ("blue",), True, False),
        ("Clark/Lake", -5.3, 10.55, ("blue", "green", "brown", "pink", "purple", "orange"), True, True),
        ("UIC-Halsted", -84.4, -15.8, ("blue",), False, False),
        ("Western (Forest Park)", -168.8, -15.8, ("blue",), False, False),
        ("Cicero (Eisenhower)", -253.2, -15.8, ("blue",), False, False),
        ("Forest Park", -400.9, -15.8, ("blue",), False, False),
        # Green
        ("Harlem/Lake", -379.8, 10.55, ("green",), True, False),
        ("Oak Park (Lake)", -337.6, 10.55, ("green",), True, False),
        ("Cicero (Lake)", -253.2, 10.55, ("green",), True, False),
        ("Kedzie (Lake)", -168.8, 10.55, ("green",), True, False),
        ("Ashland (Lake)", -84.4, 10.55, ("green", "pink"), True, False),
        ("State/Lake", 0.0, 10.55, ("green", "orange", "brown", "pink", "purple"), True, True),
        ("Adams/Wabash", 2.64, 0.0, ("green", "orange", "brown", "pink", "purple"), True, True),
        ("Library", 2.64, -21.10, ("green", "orange", "brown", "pink", "purple"), True, True),
        ("Indiana", 18.0, -211.0, ("green",), True, False),
        ("Cottage Grove", 42.2, -332.3, ("green",), True, False),
        ("Ashland/63rd", -84.4, -332.3, ("green",), True, False),
        # Orange
        ("Midway", -250.0, -310.0, ("orange",), True, True),
        ("Pulaski (Orange)", -168.8, -230.0, ("orange",), True, False),
        ("Western (Orange)", -84.4, -160.0, ("orange",), True, False),
        ("Halsted (Orange)", -42.2, -132.0, ("orange",), True, False),
        # Brown
        ("Kimball", -179.4, 253.2, ("brown",), True, False),
        ("Irving Park (Brown)", -95.0, 211.0, ("brown",), True, False),
        ("Southport", -95.0, 175.0, ("brown",), True, False),
        # Pink
        ("54th/Cermak", -285.0, -116.0, ("pink",), True, False),
        ("Kedzie (Pink)", -168.8, -110.0, ("pink",), True, False),
        ("Polk", -89.7, -21.1, ("pink",), True, False),
        # Purple
        ("Linden", -68.0, 485.0, ("purple",), True, False),
        ("Davis", -42.0, 440.0, ("purple",), True, False),
        ("Main", -35.0, 420.0, ("purple",), True, False),
    ]
    stations: list[dict] = []
    for name, x, y, lines, elev, hub in raw:
        primary = lines[0]
        stations.append(
            {
                "name": name,
                "x": x,
                "y": y,
                "lines": lines,
                "color": LINE_COLORS[primary],
                "elevated": elev,
                "hub": hub,
                "z": Z_PLATFORM_ELEV if elev else Z_PLATFORM_MED,
            }
        )
    return stations


# ---------------------------------------------------------------------------
# Mesh builders
# ---------------------------------------------------------------------------
def _build_station(parent: NodePath, st: dict) -> None:
    x, y = st["x"], st["y"]
    elev = st["elevated"]
    hub = st["hub"]
    z_plat = st["z"]
    length = 2.2 if hub else 1.6
    width = 0.85 if hub else 0.55
    plat_mat = rgba_material(PLATFORM_RGBA)
    canopy_mat = rgba_material(CANOPY_RGBA)
    brick_mat = rgba_material(BRICK_RGBA)
    steel_mat = rgba_material(STEEL_RGBA)
    sign_mat = _emissive(st["color"][:3], 1.15)

    # Twin flanking platforms (or wider island for hubs).
    if hub:
        deck = box_instance(parent, length, width, 0.04, top=True, bottom=False)
        deck.setPos(x, y, z_plat)
        deck.setMaterial(plat_mat, 1)
    else:
        for sign in (-1.0, 1.0):
            deck = box_instance(parent, length, width * 0.42, 0.04, top=True, bottom=False)
            deck.setPos(x, y + sign * 0.22, z_plat)
            deck.setMaterial(plat_mat, 1)

    if elev:
        # Pitched corrugated canopy (two roof slabs).
        for sign, pitch in ((-1.0, 8.0), (1.0, -8.0)):
            roof = box_instance(parent, length * 0.95, width * 0.48, 0.025, top=True, bottom=False)
            roof.setPos(x, y + sign * width * 0.22, Z_CANOPY)
            roof.setP(pitch)
            roof.setMaterial(canopy_mat, 1)
        # Slim iron columns.
        for lx in (-length * 0.35, length * 0.35):
            for ly in (-width * 0.28, width * 0.28):
                col = box_instance(parent, 0.025, 0.025, Z_CANOPY - z_plat)
                col.setPos(x + lx, y + ly, z_plat + (Z_CANOPY - z_plat) * 0.5)
                col.setMaterial(steel_mat, 1)
        # Brick station house + stair bridge.
        house = box_instance(parent, 0.35, 0.35, 0.22)
        house.setPos(x + length * 0.55, y, 0.11)
        house.setMaterial(brick_mat, 1)
        stair = box_instance(parent, 0.12, 0.55, 0.04)
        stair.setPos(x + length * 0.35, y, z_plat * 0.5)
        stair.setP(-35.0)
        stair.setMaterial(steel_mat, 1)

    # Glowing CTA signboard.
    sign = box_instance(parent, min(1.1, length * 0.7), 0.04, 0.08)
    sign.setPos(x, y, (Z_CANOPY + 0.06) if elev else (z_plat + 0.18))
    sign.setMaterial(sign_mat, 1)
    sign.setLightOff(1)


def _flush_sector(
    root: NodePath,
    key: tuple[int, int],
    bucket: _SectorBucket,
    mats: dict,
) -> tuple[float, float, NodePath]:
    sx, sy = key
    cx = (sx + 0.5) * SECTOR_SIZE
    cy = (sy + 0.5) * SECTOR_SIZE
    node = root.attachNewNode(f"cta_viaduct_sector_{sx}_{sy}")

    if bucket.decks:
        deck_np = node.attachNewNode(
            make_flat_deck_batch(bucket.decks, DECK_THICK, name="deck", top_only=False)
        )
        deck_np.setMaterial(mats["steel"], 1)
    if bucket.ballast:
        bal_np = node.attachNewNode(
            make_flat_deck_batch(bucket.ballast, 0.05, name="ballast", top_only=True)
        )
        bal_np.setMaterial(mats["ballast"], 1)
    if bucket.rails:
        rail_np = node.attachNewNode(
            make_flat_deck_batch(bucket.rails, 0.02, name="rails", top_only=True)
        )
        rail_np.setMaterial(mats["rail"], 1)
    # CTA line-color center stripes (one GeomNode per line in this sector).
    for line, segs in bucket.stripes.items():
        if not segs:
            continue
        stripe_np = node.attachNewNode(
            make_flat_deck_batch(segs, 0.015, name=f"stripe_{line}", top_only=True)
        )
        stripe_np.setMaterial(mats["line"][line], 1)
        stripe_np.setLightOff(1)
    if bucket.barriers:
        barrier_mat = mats["concrete"]
        for x0, y0, x1, y1, w, zc in bucket.barriers:
            length = math.hypot(x1 - x0, y1 - y0)
            if length < 0.08:
                continue
            heading = _panda_heading(x1 - x0, y1 - y0)
            wall = box_instance(node, w, length, BARRIER_H)
            wall.setPos((x0 + x1) * 0.5, (y0 + y1) * 0.5, zc)
            wall.setH(heading)
            wall.setMaterial(barrier_mat, 1)

    pillar_mat = mats["steel"]
    for pi, (px, py, h) in enumerate(bucket.pillars):
        if h < 0.2:
            continue
        col = box_instance(node, PILLAR_SZ, PILLAR_SZ, h)
        col.setPos(px, py, h * 0.5)
        col.setMaterial(pillar_mat, 1)
        # Tight ground-level collider so the player can weave under the "L".
        if pi % PILLAR_COLLIDER_STRIDE == 0:
            register_pillar(px, py, radius=0.035)

    # Ties span across the track (local X = right of travel).
    tie_mat = mats["tie"]
    for i, (tx, ty, tz, heading) in enumerate(bucket.ties):
        if i % 3:
            continue
        tie = box_instance(node, DECK_W_DBL * 0.9, 0.04, 0.015, top=True, bottom=False)
        tie.setPos(tx, ty, tz)
        tie.setH(heading)
        tie.setMaterial(tie_mat, 1)

    for st in bucket.stations:
        _build_station(node, st)

    node.flattenStrong()
    return cx, cy, node


def _make_car_template(parent: NodePath, line: str) -> NodePath:
    """Shared stainless car body; length along +Y (Panda forward)."""
    root = parent.attachNewNode(f"cta_car_tmpl_{line}")
    steel = rgba_material(CAR_STEEL_RGBA, shininess=48.0)
    roof_mat = rgba_material(CAR_ROOF_RGBA)
    win_mat = _emissive(WINDOW_RGB, 0.9)
    line_rgb = LINE_COLORS[line][:3]
    marker = _emissive(line_rgb, 1.2)
    band_mat = rgba_material(LINE_COLORS[line], shininess=24.0)

    # sx = width (X), sy = length (Y forward), sz = height.
    body = box_instance(root, CAR_W, CAR_LEN, CAR_H * 0.72)
    body.setPos(0.0, 0.0, CAR_H * 0.36)
    body.setMaterial(steel, 1)

    # Color band along both sides — line identity at a glance.
    for side in (-1.0, 1.0):
        band = box_instance(root, 0.012, CAR_LEN * 0.92, CAR_H * 0.22)
        band.setPos(side * CAR_W * 0.52, 0.0, CAR_H * 0.22)
        band.setMaterial(band_mat, 1)

    roof = box_instance(root, CAR_W * 0.92, CAR_LEN * 0.96, CAR_H * 0.18)
    roof.setPos(0.0, 0.0, CAR_H * 0.82)
    roof.setMaterial(roof_mat, 1)
    for oy in (-0.08, 0.08):
        pod = box_instance(root, 0.05, 0.06, 0.03)
        pod.setPos(0.0, oy, CAR_H * 0.95)
        pod.setMaterial(roof_mat, 1)

    for side in (-1.0, 1.0):
        for oy in (-0.1, 0.0, 0.1):
            win = box_instance(root, 0.01, 0.06, 0.05)
            win.setPos(side * CAR_W * 0.52, oy, CAR_H * 0.42)
            win.setMaterial(win_mat, 1)
            win.setLightOff(1)

    jewel = box_instance(root, 0.03, 0.03, 0.02)
    jewel.setPos(0.0, CAR_LEN * 0.35, CAR_H * 0.98)
    jewel.setMaterial(marker, 1)
    jewel.setLightOff(1)

    root.flattenStrong()
    root.hide()
    return root


def _attach_headlights(car: NodePath, *, lead: bool, line: str) -> None:
    if lead:
        mat = _emissive(HEADLIGHT_RGB, 1.5)
        for side in (-1.0, 1.0):
            lamp = box_instance(car, 0.02, 0.02, 0.02)
            lamp.setPos(side * 0.03, CAR_LEN * 0.52, CAR_H * 0.28)
            lamp.setMaterial(mat, 1)
            lamp.setLightOff(1)
        route = box_instance(car, 0.06, 0.04, 0.03)
        route.setPos(0.0, CAR_LEN * 0.52, CAR_H * 0.55)
        route.setMaterial(_emissive(LINE_COLORS[line][:3], 1.3), 1)
        route.setLightOff(1)
    else:
        mat = _emissive(TAILLIGHT_RGB, 1.2)
        for side in (-1.0, 1.0):
            lamp = box_instance(car, 0.02, 0.02, 0.02)
            lamp.setPos(side * 0.03, -CAR_LEN * 0.52, CAR_H * 0.28)
            lamp.setMaterial(mat, 1)
            lamp.setLightOff(1)


# ---------------------------------------------------------------------------
# Train simulation
# ---------------------------------------------------------------------------
@dataclass
class CtaTrain:
    line: str
    path: list[tuple[float, float, float]]
    path_len: float
    cars: list[NodePath]
    n_cars: int
    dist: float  # lead-car arc length
    dwell: float = 0.0
    stations: list[tuple[float, float]] = field(default_factory=list)
    _last_station: tuple[float, float] | None = None
    _culled: bool = False

    def car_spacing(self) -> float:
        return CAR_LEN + CAR_GAP


class CtaTrainController:
    """Spline-following multi-car trains with dwell stops and headway gaps."""

    def __init__(
        self,
        trains: list[CtaTrain],
        paths: dict[str, list[tuple[float, float, float]]],
    ) -> None:
        self.trains = trains
        self.paths = paths
        self._by_line: dict[str, list[CtaTrain]] = {}
        for t in trains:
            self._by_line.setdefault(t.line, []).append(t)
        # Look-at + hide radius² — CityApp refreshes these from road LOD.
        self.view_xy = (0.0, 0.0)
        self.view_r2 = CTA_TRAIN_HIDE_DIST * CTA_TRAIN_HIDE_DIST

    def update_cta_trains(self, task):
        """Panda taskMgr entry — ``update_cta_trains``."""
        from panda3d.core import ClockObject

        dt = min(0.05, ClockObject.getGlobalClock().getDt())
        for _line, group in self._by_line.items():
            group.sort(key=lambda t: t.dist)
            n = len(group)
            for i, train in enumerate(group):
                ahead = group[(i + 1) % n] if n > 1 else None
                self._step_train(train, dt, ahead)
        return task.cont

    def _speed_at(self, x: float, y: float, z: float) -> float:
        if (
            LOOP_WELLS - 1.5 <= x <= LOOP_WABASH + 1.5
            and LOOP_VAN_BUREN - 1.5 <= y <= LOOP_LAKE + 1.5
            and z >= 0.4
        ):
            return TRAIN_SPEED_LOOP
        return TRAIN_SPEED_EXPRESS

    def _train_in_view(self, train: CtaTrain, x: float, y: float) -> bool:
        vx, vy = self.view_xy
        dx = x - vx
        dy = y - vy
        return dx * dx + dy * dy <= self.view_r2

    def _set_train_culled(self, train: CtaTrain, culled: bool) -> None:
        if train._culled == culled:
            return
        train._culled = culled
        if culled:
            for car in train.cars:
                if not car.isHidden():
                    car.hide()

    def _step_train(self, train: CtaTrain, dt: float, ahead: CtaTrain | None) -> None:
        if train.dwell > 0.0:
            train.dwell = max(0.0, train.dwell - dt)
            x, y, _z, _h = _sample_polyline(train.path, train.dist)
            if self._train_in_view(train, x, y):
                self._set_train_culled(train, False)
                self._place_cars(train)
            else:
                self._set_train_culled(train, True)
            return

        x, y, z, _h = _sample_polyline(train.path, train.dist)
        speed = self._speed_at(x, y, z)

        if ahead is not None and ahead is not train:
            gap = ahead.dist - train.dist
            if gap <= 0.0:
                gap += train.path_len
            if gap < HEADWAY:
                speed *= max(0.0, gap / HEADWAY)

        for sx, sy in train.stations:
            if (x - sx) ** 2 + (y - sy) ** 2 <= STATION_STOP_R2:
                key = (round(sx, 1), round(sy, 1))
                if train._last_station != key:
                    train._last_station = key
                    train.dwell = DWELL_SEC
                    if self._train_in_view(train, x, y):
                        self._set_train_culled(train, False)
                        self._place_cars(train)
                    else:
                        self._set_train_culled(train, True)
                    return
                break
        else:
            if train._last_station is not None:
                lsx, lsy = train._last_station
                if (x - lsx) ** 2 + (y - lsy) ** 2 > STATION_STOP_R2 * 4.0:
                    train._last_station = None

        train.dist = (train.dist + speed * dt) % train.path_len
        # Re-sample lead after advance for culling (cheap vs placing every car).
        x, y, _z2, _h2 = _sample_polyline(train.path, train.dist)
        if self._train_in_view(train, x, y):
            self._set_train_culled(train, False)
            self._place_cars(train)
        else:
            self._set_train_culled(train, True)

    def _place_cars(self, train: CtaTrain) -> None:
        spacing = train.car_spacing()
        plen = train.path_len
        for i, car in enumerate(train.cars):
            d = train.dist - i * spacing
            while d < 0.0:
                d += plen
            x, y, z, heading = _sample_polyline(train.path, d)
            if z < 0.0:
                if not car.isHidden():
                    car.hide()
                continue
            if car.isHidden():
                car.show()
            # Prefer segment heading; only look ahead when it stays on this lap
            # (wrapping look-ahead would point across the map).
            look = 0.2
            if d + look <= plen:
                x2, y2, _z2, _h2 = _sample_polyline(train.path, d + look)
                dx, dy = x2 - x, y2 - y
                if dx * dx + dy * dy > 1e-8:
                    heading = _panda_heading(dx, dy)
            car.setPos(x, y, z + CAR_H * 0.02)
            car.setH(heading)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def build_chicago_cta(parent: NodePath) -> dict:
    """Build CTA infrastructure + trains. Returns roots, LOD tiles, controller."""
    root = parent.attachNewNode("chicago_cta")
    infra_root = root.attachNewNode("cta_infrastructure")
    trains_root = root.attachNewNode("cta_trains")
    templates_root = root.attachNewNode("cta_templates")
    templates_root.hide()

    line_mats = {
        name: _emissive(rgba[:3], 0.85) for name, rgba in LINE_COLORS.items()
    }
    mats = {
        "steel": rgba_material(STEEL_RGBA, shininess=18.0),
        "rail": rgba_material(RAIL_RGBA, shininess=40.0),
        "tie": rgba_material(TIE_RGBA),
        "ballast": rgba_material(BALLAST_RGBA),
        "concrete": concrete_material(),
        "line": line_mats,
    }

    paths = _line_paths()
    stations = _station_defs()
    buckets: dict[tuple[int, int], _SectorBucket] = {}

    def _line_key(path_name: str) -> str:
        return "green" if path_name.startswith("green") else path_name

    # --- Loop elevated rectangle (shared steel structure) ---
    loop_pts = _loop_circuit(Z_ELEV)
    _add_polyline_track(buckets, loop_pts, double=True, elevated=True)

    # Flyover pads at three junctions.
    for fx, fy in (
        (LOOP_WELLS, LOOP_LAKE),  # Tower 18
        (LOOP_WABASH, LOOP_VAN_BUREN),  # Tower 12
        (LOOP_WELLS, LOOP_VAN_BUREN),  # Wells & Van Buren
    ):
        key = _sector_key(fx, fy)
        b = buckets.setdefault(key, _SectorBucket())
        pad = 0.9
        b.decks.append((fx - pad, fy, fx + pad, fy, DECK_W_DBL * 1.35, Z_FLYOVER))
        b.decks.append((fx, fy - pad, fx, fy + pad, DECK_W_DBL * 1.35, Z_FLYOVER))

    # --- Line corridors (skip near-duplicate Loop decks; stripes painted full-path) ---
    for name, pts in paths.items():
        line = _line_key(name)
        if name == "green_cottage":
            spur = [p for p in pts if p[1] <= -330.0 or (p[0] >= 18.0 and p[1] <= -211.0)]
            if len(spur) >= 2:
                _add_polyline_track(buckets, spur, double=True)
            _add_polyline_stripes(buckets, pts, line)
            continue
        filtered: list[tuple[float, float, float]] = []
        for p in pts:
            x, y, z = p
            on_loop = (
                LOOP_WELLS - 0.8 <= x <= LOOP_WABASH + 0.8
                and LOOP_VAN_BUREN - 0.8 <= y <= LOOP_LAKE + 0.8
                and z >= 0.4
            )
            if on_loop and name in ("orange", "brown", "pink", "purple", "green"):
                continue
            filtered.append(p)
        run: list[tuple[float, float, float]] = []
        for p in filtered:
            if not run:
                run.append(p)
                continue
            gap = math.hypot(p[0] - run[-1][0], p[1] - run[-1][1])
            if gap > 12.0:
                if len(run) >= 2:
                    _add_polyline_track(buckets, run, double=True)
                run = [p]
            else:
                run.append(p)
        if len(run) >= 2:
            _add_polyline_track(buckets, run, double=True)
        # Full-path CTA color stripe (Loop + branches; lateral offset for shared track).
        _add_polyline_stripes(buckets, pts, line)

    # --- Assign stations to sectors ---
    for st in stations:
        key = _sector_key(st["x"], st["y"])
        buckets.setdefault(key, _SectorBucket()).stations.append(st)

    # --- Flatten sectors ---
    tiles: list[tuple[float, float, NodePath]] = []
    for key, bucket in buckets.items():
        cx, cy, node = _flush_sector(infra_root, key, bucket, mats)
        tiles.append((cx, cy, node))

    # --- Shared car templates per line colour ---
    templates: dict[str, NodePath] = {}
    for line in LINE_COLORS:
        templates[line] = _make_car_template(templates_root, line)

    # --- Spawn trains ---
    station_xy_by_line: dict[str, list[tuple[float, float]]] = {k: [] for k in LINE_COLORS}
    for st in stations:
        for ln in st["lines"]:
            if ln in station_xy_by_line:
                station_xy_by_line[ln].append((st["x"], st["y"]))

    # (path_key, line_color, count, cars) — thinned for FPS; still readable traffic.
    spawn_plan = [
        ("red", "red", 4, 4),
        ("blue", "blue", 4, 4),
        ("green", "green", 3, 3),
        ("green_cottage", "green", 1, 3),
        ("orange", "orange", 3, 3),
        ("brown", "brown", 3, 3),
        ("pink", "pink", 2, 3),
        ("purple", "purple", 2, 4),
    ]

    trains: list[CtaTrain] = []
    for path_key, line, count, n_cars in spawn_plan:
        pts = paths[path_key]
        plen = _polyline_length(pts)
        if plen < 1.0:
            continue
        for i in range(count):
            dist0 = (plen * (i + 0.15)) / count
            train_np = trains_root.attachNewNode(f"cta_train_{line}_{i}")
            cars: list[NodePath] = []
            for c in range(n_cars):
                car = templates[line].copyTo(train_np)
                car.show()
                if c == 0:
                    _attach_headlights(car, lead=True, line=line)
                elif c == n_cars - 1:
                    _attach_headlights(car, lead=False, line=line)
                cars.append(car)
            trains.append(
                CtaTrain(
                    line=line,
                    path=pts,
                    path_len=plen,
                    cars=cars,
                    n_cars=n_cars,
                    dist=dist0,
                    stations=list(station_xy_by_line.get(line, [])),
                )
            )

    controller = CtaTrainController(trains, paths)
    # Place once so trains aren't stacked at origin before first task tick.
    for t in trains:
        controller._place_cars(t)

    return {
        "root": root,
        "infra_root": infra_root,
        "trains_root": trains_root,
        "tiles": tiles,
        "controller": controller,
        "trains": trains,
        "stations": stations,
        "paths": paths,
    }
