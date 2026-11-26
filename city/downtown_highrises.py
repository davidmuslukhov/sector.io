"""Downtown Chicago landmark skyscrapers + procedural high-rise infill (2×).

Fills the Loop / River North / West Loop / South Loop core with low-poly
replicas of iconic towers and four archetype infill styles. Static day
geometry batches into ``downtown_landmarks_node`` and
``downtown_highrises_node`` (each ``flattenStrong``'d). Night window strips,
aviation beacons, and crown uplights live under ``downtown_night_glow_node``
and toggle with street lights / day-cycle night mode.
"""

from __future__ import annotations

import math
import random
from typing import Any

from panda3d.core import Material, NodePath

from city.materials import rgba_material
from city.mesh import box_instance, cone_instance, make_pyramid, z_cylinder_instance

# ---------------------------------------------------------------------------
# Scale / downtown footprint (2× Chicago)
# ---------------------------------------------------------------------------
UNITS_PER_MILE = 42.2
BLOCK_100 = 5.275

DT_X0, DT_X1 = -42.2, 16.0
DT_Y0, DT_Y1 = -63.3, 42.2

# Spec clear-box for low-rise (housing exclusion mirrors full footprint).
CLEAR_X0, CLEAR_X1 = -35.0, 16.0
CLEAR_Y0, CLEAR_Y1 = -42.2, 32.0

GRANT_X0, GRANT_X1 = 6.5, 16.0
GRANT_Y0, GRANT_Y1 = -63.3, 10.5
GRANT_RGBA = (0.16, 0.28, 0.15, 1.0)
GRANT_Z = -0.05

# Road clearances from centreline.
ARTERIAL_SETBACK = 0.32  # State, Michigan, Madison, Chicago, Roosevelt
LOOP_SETBACK = 0.22  # Wabash, Dearborn, Clark, LaSalle, Wells, Franklin, …
ARTERIAL_HALF = 0.55 * 0.5  # unused visual; setback measured from centreline

FOUNDATION_Z = 0.0

# Primary arterial N–S / E–W centreline coords inside the downtown plate.
ARTERIAL_X = frozenset({-42.2, 0.0, 5.3})  # Halsted, State, Michigan
ARTERIAL_Y = frozenset({-63.3, 0.0, 42.2})  # Roosevelt, Madison, Chicago Ave

# Loop cross-street centreline coords (plus Kinzie for river corridor).
NS_STREETS = (
    -42.2,  # Halsted
    -28.5,  # Clinton
    -26.4,  # Canal
    -21.1,  # approx Wacker west / river
    -15.8,  # Franklin
    -10.6,  # Wells
    -7.4,  # LaSalle
    -5.3,  # Clark
    -1.9,  # Dearborn
    0.0,  # State
    2.6,  # Wabash
    5.3,  # Michigan
    10.6,  # Columbus / Field
    16.0,  # east plate edge
)
EW_STREETS = (
    -63.3,  # Roosevelt
    -42.2,  # 800 S
    -31.6,  # Harrison
    -26.4,  # Ida B. Wells
    -21.1,  # Van Buren approx
    -15.8,  # Jackson
    -10.6,  # Adams
    -5.3,  # Monroe approx
    0.0,  # Madison
    5.3,  # Washington
    7.9,  # Randolph
    10.6,  # Lake approx
    15.8,  # Wacker
    21.1,  # Kinzie
    26.4,  # Illinois approx
    31.6,  # Ohio approx
    36.9,  # Ontario approx
    42.2,  # Chicago Ave
)

# Dense Loop financial core (2–4 towers / block).
LOOP_CORE_X0, LOOP_CORE_X1 = -26.4, 5.3
LOOP_CORE_Y0, LOOP_CORE_Y1 = -26.4, 15.8

# Facade palettes
WILLIS_RGBA = (0.08, 0.09, 0.11, 1.0)
HANCOCK_RGBA = (0.10, 0.11, 0.13, 1.0)
TRUMP_STEEL = (0.72, 0.76, 0.80, 1.0)
TRUMP_GLASS = (0.42, 0.55, 0.68, 1.0)
STREGIS_GLASS = (0.16, 0.36, 0.44, 1.0)
AON_RGBA = (0.82, 0.83, 0.85, 1.0)
PRU_GRANITE = (0.58, 0.56, 0.52, 1.0)
MARINA_CONCRETE = (0.78, 0.76, 0.72, 1.0)
MART_LIMESTONE = (0.76, 0.72, 0.64, 1.0)
LIMESTONE = (0.74, 0.71, 0.65, 1.0)
TERRACOTTA = (0.72, 0.52, 0.38, 1.0)
BRICK_RED = (0.52, 0.28, 0.22, 1.0)
BRONZE_GLASS = (0.22, 0.20, 0.18, 1.0)
CHARCOAL = (0.14, 0.15, 0.17, 1.0)
COOL_GLASS = (0.28, 0.38, 0.42, 1.0)
TEAL_GLASS = (0.22, 0.42, 0.46, 1.0)
BLUE_GLASS = (0.30, 0.42, 0.55, 1.0)
WHITE_CROWN = (0.92, 0.93, 0.94, 1.0)
ANTENNA_WHITE = (0.88, 0.88, 0.90, 1.0)
PODIUM_CONCRETE = (0.62, 0.62, 0.60, 1.0)

_EMISSIVE_CACHE: dict[tuple, Material] = {}


def _emissive(rgb: tuple[float, float, float], strength: float = 1.0) -> Material:
    key = (round(rgb[0], 3), round(rgb[1], 3), round(rgb[2], 3), round(strength, 2))
    cached = _EMISSIVE_CACHE.get(key)
    if cached is not None:
        return cached
    mat = Material()
    em = (rgb[0] * strength, rgb[1] * strength, rgb[2] * strength)
    mat.setAmbient((*rgb, 1))
    mat.setDiffuse((*rgb, 1))
    mat.setEmission((*em, 1))
    mat.setShininess(24)
    _EMISSIVE_CACHE[key] = mat
    return mat


# ---------------------------------------------------------------------------
# Primitive helpers — foundations seat at Z = 0
# ---------------------------------------------------------------------------
def _box(
    parent: NodePath,
    cx: float,
    cy: float,
    sx: float,
    sy: float,
    sz: float,
    material: Material,
    *,
    z0: float = FOUNDATION_Z,
) -> NodePath:
    body = box_instance(parent, sx, sy, sz)
    body.setPos(cx, cy, z0 + sz * 0.5)
    body.setMaterial(material, 1)
    return body


def _box_at_z(
    parent: NodePath,
    cx: float,
    cy: float,
    sx: float,
    sy: float,
    sz: float,
    z_center: float,
    material: Material,
) -> NodePath:
    body = box_instance(parent, sx, sy, sz)
    body.setPos(cx, cy, z_center)
    body.setMaterial(material, 1)
    return body


def _cyl(
    parent: NodePath,
    cx: float,
    cy: float,
    radius: float,
    height: float,
    material: Material,
    *,
    z0: float = FOUNDATION_Z,
    segments: int = 12,
) -> NodePath:
    body = z_cylinder_instance(parent, radius, height, segments=segments)
    body.setPos(cx, cy, z0 + height * 0.5)
    body.setMaterial(material, 1)
    return body


def _pyramid(
    parent: NodePath,
    cx: float,
    cy: float,
    sx: float,
    sy: float,
    height: float,
    material: Material,
    *,
    z0: float,
) -> NodePath:
    node = parent.attachNewNode(make_pyramid(sx, sy, height))
    node.setPos(cx, cy, z0)
    node.setMaterial(material, 1)
    return node


def _spire(
    parent: NodePath,
    cx: float,
    cy: float,
    z0: float,
    height: float,
    material: Material,
    *,
    radius: float = 0.06,
) -> NodePath:
    tip = cone_instance(parent, radius, height, segments=6)
    tip.setPos(cx, cy, z0)
    tip.setMaterial(material, 1)
    return tip


# ---------------------------------------------------------------------------
# Night glow — window strips / beacons / crowns (separate node, show at night)
# ---------------------------------------------------------------------------
def _window_strips(
    night: NodePath,
    cx: float,
    cy: float,
    sx: float,
    sy: float,
    z0: float,
    z1: float,
    *,
    warm: bool = True,
    step: float = 0.55,
) -> None:
    """Horizontal lit bands on four faces between ``z0`` and ``z1``."""
    if z1 <= z0 + 0.2:
        return
    rgb = (1.0, 0.82, 0.55) if warm else (0.75, 0.88, 1.0)
    mat = _emissive(rgb, 0.85)
    depth = 0.04
    band_h = 0.12
    z = z0 + 0.35
    while z < z1 - 0.2:
        _box_at_z(night, cx, cy + sy * 0.5 + depth * 0.5, sx * 0.88, depth, band_h, z, mat)
        _box_at_z(night, cx, cy - sy * 0.5 - depth * 0.5, sx * 0.88, depth, band_h, z, mat)
        _box_at_z(night, cx + sx * 0.5 + depth * 0.5, cy, depth, sy * 0.88, band_h, z, mat)
        _box_at_z(night, cx - sx * 0.5 - depth * 0.5, cy, depth, sy * 0.88, band_h, z, mat)
        z += step


def _beacon(night: NodePath, cx: float, cy: float, z: float) -> None:
    mat = _emissive((1.0, 0.08, 0.05), 1.4)
    bulb = box_instance(night, 0.12, 0.12, 0.12)
    bulb.setPos(cx, cy, z)
    bulb.setMaterial(mat, 1)
    bulb.setLightOff(1)


def _crown_band(
    night: NodePath,
    cx: float,
    cy: float,
    sx: float,
    sy: float,
    z: float,
    *,
    rgb: tuple[float, float, float] = (1.0, 1.0, 0.95),
) -> None:
    mat = _emissive(rgb, 1.1)
    h = 0.18
    _box_at_z(night, cx, cy, sx * 1.02, sy * 1.02, h, z, mat)


# ---------------------------------------------------------------------------
# Landmark towers
# ---------------------------------------------------------------------------
def _willis(landmarks: NodePath, night: NodePath) -> tuple[float, float, float, float]:
    """Willis / Sears Tower — bundled-tube cluster at Wacker & Adams."""
    cx, cy = -18.5, -10.5
    mat = rgba_material(WILLIS_RGBA, shininess=40.0)
    white = rgba_material(ANTENNA_WHITE, shininess=20.0)
    # 3×3 tube grid; tube pitch 0.8 → overall ~2.4
    pitch = 0.80
    tube = 0.78
    # Heights: two full (center/west), five mid, two stepped corners.
    # Layout (N↑): indices row-major from SW.
    #   NW  N   NE     11.8 11.8 11.8
    #   W   C   E      14.5 14.5 11.8
    #   SW  S   SE      8.5 11.8  6.5
    heights = (
        8.5, 11.8, 6.5,
        14.5, 14.5, 11.8,
        11.8, 11.8, 11.8,
    )
    for i, h in enumerate(heights):
        col = i % 3
        row = i // 3
        tx = cx + (col - 1) * pitch
        ty = cy + (row - 1) * pitch
        _box(landmarks, tx, ty, tube, tube, h, mat)
        _window_strips(night, tx, ty, tube, tube, 0.4, h - 0.3, warm=False, step=0.70)
    # Twin antennas atop the two tallest west/center tubes.
    for ox, oy in ((-pitch, 0.0), (0.0, 0.0)):
        ant_z = 14.5
        shaft = z_cylinder_instance(landmarks, 0.05, 2.8, segments=6)
        shaft.setPos(cx + ox, cy + oy, ant_z + 1.4)
        shaft.setMaterial(white, 1)
        _beacon(night, cx + ox, cy + oy, ant_z + 2.8)
    _crown_band(night, cx, cy, 2.4, 2.4, 14.5)
    return (cx - 1.4, cy - 1.4, cx + 1.4, cy + 1.4)


def _hancock(landmarks: NodePath, night: NodePath) -> tuple[float, float, float, float]:
    """875 N Michigan / John Hancock Center — tapered X-braced tower."""
    cx, cy = 5.3, 44.0
    base_sx, base_sy = 2.1, 1.6
    taper = 0.72
    top_z = 11.4
    mat = rgba_material(HANCOCK_RGBA, shininess=36.0)
    brace_mat = rgba_material((0.18, 0.18, 0.20, 1.0), shininess=50.0)
    white = rgba_material(WHITE_CROWN, shininess=18.0)
    # Stepped taper approximating continuous frustum.
    tiers = 6
    for i in range(tiers):
        t0 = i / tiers
        t1 = (i + 1) / tiers
        s = 1.0 - (1.0 - taper) * ((t0 + t1) * 0.5)
        z0 = top_z * t0
        z1 = top_z * t1
        _box(landmarks, cx, cy, base_sx * s, base_sy * s, z1 - z0, mat, z0=z0)
    # Signature X-bracing on four faces (two diagonals each).
    for face in range(4):
        for sign in (1.0, -1.0):
            brace = box_instance(landmarks, 0.08, 0.08, top_z * 1.05)
            if face == 0:  # +Y
                brace.setPos(cx + sign * base_sx * 0.28, cy + base_sy * 0.52, top_z * 0.5)
                brace.setP(28.0 * sign)
            elif face == 1:  # -Y
                brace.setPos(cx + sign * base_sx * 0.28, cy - base_sy * 0.52, top_z * 0.5)
                brace.setP(-28.0 * sign)
            elif face == 2:  # +X
                brace.setPos(cx + base_sx * 0.52, cy + sign * base_sy * 0.28, top_z * 0.5)
                brace.setR(-28.0 * sign)
            else:
                brace.setPos(cx - base_sx * 0.52, cy + sign * base_sy * 0.28, top_z * 0.5)
                brace.setR(28.0 * sign)
            brace.setMaterial(brace_mat, 1)
    # White crown band + twin spires.
    _box(landmarks, cx, cy, base_sx * taper * 1.02, base_sy * taper * 1.02, 0.22, white, z0=top_z)
    for ox in (-0.25, 0.25):
        shaft = z_cylinder_instance(landmarks, 0.045, 3.2, segments=6)
        shaft.setPos(cx + ox, cy, top_z + 1.6)
        shaft.setMaterial(white, 1)
        _beacon(night, cx + ox, cy, top_z + 3.2)
    _crown_band(night, cx, cy, base_sx * taper, base_sy * taper, top_z + 0.1)
    _window_strips(
        night, cx, cy, base_sx * 0.9, base_sy * 0.9, 0.5, top_z - 0.4, warm=False, step=0.65
    )
    return (cx - 1.2, cy - 1.0, cx + 1.2, cy + 1.0)


def _trump(landmarks: NodePath, night: NodePath) -> tuple[float, float, float, float]:
    """Trump International Hotel & Tower — stepped stainless / blue glass."""
    cx, cy = 2.6, 21.1
    sx, sy = 2.6, 1.3
    steel = rgba_material(TRUMP_STEEL, shininess=55.0)
    glass = rgba_material(TRUMP_GLASS, shininess=48.0)
    # Three setback tiers.
    tiers = (
        (sx, sy, 5.5, glass),
        (sx * 0.82, sy * 0.82, 8.8 - 5.5, steel),
        (sx * 0.62, sy * 0.62, 11.8 - 8.8, glass),
    )
    z = 0.0
    for tw, td, th, mat in tiers:
        _box(landmarks, cx, cy, tw, td, th, mat, z0=z)
        _window_strips(night, cx, cy, tw, td, z + 0.3, z + th - 0.2, warm=False, step=0.60)
        z += th
    _spire(landmarks, cx, cy, 11.8, 2.2, rgba_material(ANTENNA_WHITE), radius=0.07)
    _beacon(night, cx, cy, 11.8 + 2.2)
    _crown_band(night, cx, cy, sx * 0.62, sy * 0.62, 11.8)
    return (cx - 1.4, cy - 0.8, cx + 1.4, cy + 0.8)


def _st_regis(landmarks: NodePath, night: NodePath) -> tuple[float, float, float, float]:
    """St. Regis / Vista Tower — three undulating blue-green frustums."""
    cx, cy = 13.5, 16.5
    glass = rgba_material(STREGIS_GLASS, shininess=45.0)
    # Three side-by-side towers stepping up E→W-ish with slight Y wave.
    specs = (
        (-1.05, -0.15, 1.05, 1.05, 6.2),
        (0.05, 0.12, 1.05, 1.05, 8.9),
        (1.15, -0.08, 1.05, 1.05, 12.0),
    )
    for ox, oy, sx, sy, h in specs:
        # Two-tier frustum per shaft.
        _box(landmarks, cx + ox, cy + oy, sx, sy, h * 0.55, glass)
        _box(
            landmarks,
            cx + ox,
            cy + oy,
            sx * 0.78,
            sy * 0.78,
            h * 0.45,
            glass,
            z0=h * 0.55,
        )
        _window_strips(
            night, cx + ox, cy + oy, sx * 0.9, sy * 0.9, 0.4, h - 0.3, warm=False, step=0.70
        )
    _crown_band(night, cx + 1.15, cy - 0.08, 0.9, 0.9, 12.0)
    _beacon(night, cx + 1.15, cy - 0.08, 12.3)
    return (cx - 1.7, cy - 0.9, cx + 1.9, cy + 0.9)


def _aon(landmarks: NodePath, night: NodePath) -> tuple[float, float, float, float]:
    """Aon Center — monolithic white granite prism."""
    cx, cy = 9.5, 8.0
    sx = sy = 2.1
    h = 11.4
    mat = rgba_material(AON_RGBA, shininess=22.0)
    rib = rgba_material((0.70, 0.71, 0.73, 1.0), shininess=18.0)
    _box(landmarks, cx, cy, sx, sy, h, mat)
    # Vertical granite ribs on facades.
    for i in range(-2, 3):
        ox = i * 0.38
        _box(landmarks, cx + ox, cy + sy * 0.51, 0.08, 0.05, h, rib)
        _box(landmarks, cx + ox, cy - sy * 0.51, 0.08, 0.05, h, rib)
        _box(landmarks, cx + sx * 0.51, cy + ox, 0.05, 0.08, h, rib)
        _box(landmarks, cx - sx * 0.51, cy + ox, 0.05, 0.08, h, rib)
    _window_strips(night, cx, cy, sx, sy, 0.5, h - 0.4, warm=True, step=0.55)
    _crown_band(night, cx, cy, sx, sy, h)
    _beacon(night, cx, cy, h + 0.3)
    return (cx - 1.2, cy - 1.2, cx + 1.2, cy + 1.2)


def _prudential(landmarks: NodePath, night: NodePath) -> tuple[float, float, float, float]:
    """Two Prudential Plaza — chevron granite to pyramidal peak."""
    cx, cy = 7.8, 8.0
    sx = sy = 1.7
    mat = rgba_material(PRU_GRANITE, shininess=28.0)
    # Stacked diamond-ish chevron tiers (slightly rotated boxes).
    z = 0.0
    for i, (scale, th, yaw) in enumerate(
        ((1.0, 3.2, 0.0), (0.88, 2.6, 8.0), (0.72, 2.2, -6.0), (0.55, 1.2, 10.0))
    ):
        body = box_instance(landmarks, sx * scale, sy * scale, th)
        body.setPos(cx, cy, z + th * 0.5)
        body.setH(yaw)
        body.setMaterial(mat, 1)
        _window_strips(
            night, cx, cy, sx * scale * 0.9, sy * scale * 0.9, z + 0.3, z + th - 0.2, step=0.65
        )
        z += th
    peak_h = 10.0 - z
    if peak_h > 0.2:
        _pyramid(landmarks, cx, cy, sx * 0.5, sy * 0.5, peak_h, mat, z0=z)
    _spire(landmarks, cx, cy, 10.0, 1.4, rgba_material(ANTENNA_WHITE), radius=0.05)
    _crown_band(night, cx, cy, sx * 0.5, sy * 0.5, 10.0)
    _beacon(night, cx, cy, 11.4)
    return (cx - 1.0, cy - 1.0, cx + 1.0, cy + 1.0)


def _marina_city(landmarks: NodePath, night: NodePath) -> tuple[float, float, float, float]:
    """Marina City twin corn-cob towers."""
    cx, cy = -1.5, 21.1
    radius = 0.68
    h = 5.9
    gap = 1.6
    concrete = rgba_material(MARINA_CONCRETE, shininess=14.0)
    for ox in (-gap * 0.5, gap * 0.5):
        # Spiral parking base (shorter fat cylinder).
        _cyl(landmarks, cx + ox, cy, radius * 1.05, 1.1, concrete, segments=16)
        # Residential shaft.
        _cyl(landmarks, cx + ox, cy, radius, h - 1.1, concrete, z0=1.1, segments=16)
        # Scalloped balcony rings every ~0.45 units.
        z = 1.3
        while z < h - 0.2:
            ring = z_cylinder_instance(landmarks, radius * 1.12, 0.08, segments=16)
            ring.setPos(cx + ox, cy, z)
            ring.setMaterial(concrete, 1)
            z += 0.45
        _window_strips(
            night,
            cx + ox,
            cy,
            radius * 1.6,
            radius * 1.6,
            1.2,
            h - 0.3,
            warm=True,
            step=0.50,
        )
    return (cx - gap * 0.5 - radius - 0.2, cy - radius - 0.2, cx + gap * 0.5 + radius + 0.2, cy + radius + 0.2)


def _merchandise_mart(
    landmarks: NodePath, night: NodePath
) -> tuple[float, float, float, float]:
    """Merchandise Mart — Art Deco limestone spanning two blocks."""
    cx, cy = -10.5, 21.1
    sx, sy = 4.6, 2.8
    mat = rgba_material(MART_LIMESTONE, shininess=16.0)
    _box(landmarks, cx, cy, sx, sy, 3.4, mat)
    # Stepped corner turrets.
    for ox, oy in (
        (-sx * 0.42, -sy * 0.38),
        (sx * 0.42, -sy * 0.38),
        (-sx * 0.42, sy * 0.38),
        (sx * 0.42, sy * 0.38),
    ):
        _box(landmarks, cx + ox, cy + oy, 0.55, 0.55, 3.9, mat)
    # Central tower pavilion.
    _box(landmarks, cx, cy, 1.2, 1.0, 4.6, mat)
    _window_strips(night, cx, cy, sx, sy, 0.4, 3.2, warm=True, step=0.45)
    return (cx - sx * 0.5 - 0.1, cy - sy * 0.5 - 0.1, cx + sx * 0.5 + 0.1, cy + sy * 0.5 + 0.1)


def _build_landmarks(
    landmarks: NodePath, night: NodePath
) -> list[tuple[float, float, float, float]]:
    reserves: list[tuple[float, float, float, float]] = []
    for builder in (
        _willis,
        _hancock,
        _trump,
        _st_regis,
        _aon,
        _prudential,
        _marina_city,
        _merchandise_mart,
    ):
        reserves.append(builder(landmarks, night))
    return reserves


# ---------------------------------------------------------------------------
# Grant Park lawn void
# ---------------------------------------------------------------------------
def _grant_park(parent: NodePath) -> None:
    sx = GRANT_X1 - GRANT_X0
    sy = GRANT_Y1 - GRANT_Y0
    lawn = box_instance(parent, sx, sy, 0.08, top=True, bottom=False)
    lawn.setPos((GRANT_X0 + GRANT_X1) * 0.5, (GRANT_Y0 + GRANT_Y1) * 0.5, GRANT_Z)
    lawn.setMaterial(rgba_material(GRANT_RGBA), 1)


# ---------------------------------------------------------------------------
# Infill high-rises — four archetypes
# ---------------------------------------------------------------------------
def _in_grant(x: float, y: float) -> bool:
    return GRANT_X0 <= x <= GRANT_X1 and GRANT_Y0 <= y <= GRANT_Y1


def _in_reserve(
    x: float, y: float, reserves: list[tuple[float, float, float, float]], pad: float = 0.35
) -> bool:
    for x0, y0, x1, y1 in reserves:
        if x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad:
            return True
    return False


def _setback_for_street(coord: float, arterial_set: frozenset[float]) -> float:
    for a in arterial_set:
        if abs(coord - a) < 0.05:
            return ARTERIAL_SETBACK
    return LOOP_SETBACK


def _usable_span(a: float, b: float, arterial_set: frozenset[float]) -> tuple[float, float] | None:
    """Interior pad between two street centrelines after setbacks."""
    lo = a + _setback_for_street(a, arterial_set)
    hi = b - _setback_for_street(b, arterial_set)
    if hi - lo < 1.2:
        return None
    return lo, hi


def _is_loop_core(x: float, y: float) -> bool:
    return LOOP_CORE_X0 <= x <= LOOP_CORE_X1 and LOOP_CORE_Y0 <= y <= LOOP_CORE_Y1


def _pick_mix(rng: random.Random, x: float, y: float) -> str:
    """Archetype mix biased by district."""
    # River North / Streeterville / South Loop → more condo glass.
    if y >= 15.8 or y <= -26.4 or x >= 5.3:
        weights = (
            ("mies", 0.20),
            ("deco", 0.20),
            ("condo", 0.45),
            ("chicago", 0.15),
        )
    # LaSalle canyon / Michigan Ave → Art Deco.
    elif abs(x + 7.4) < 3.0 or abs(x - 5.3) < 2.5:
        weights = (
            ("mies", 0.25),
            ("deco", 0.40),
            ("condo", 0.15),
            ("chicago", 0.20),
        )
    # Printers Row / Loop edge → Chicago School mid-rise.
    elif y <= -15.8 and x >= -15.8:
        weights = (
            ("mies", 0.25),
            ("deco", 0.20),
            ("condo", 0.20),
            ("chicago", 0.35),
        )
    else:
        # Loop financial — Miesian glass.
        weights = (
            ("mies", 0.45),
            ("deco", 0.25),
            ("condo", 0.15),
            ("chicago", 0.15),
        )
    roll = rng.random()
    acc = 0.0
    for name, w in weights:
        acc += w
        if roll <= acc:
            return name
    return "mies"


def _add_mies(
    day: NodePath,
    night: NodePath,
    cx: float,
    cy: float,
    rng: random.Random,
    max_w: float,
    max_d: float,
) -> None:
    w = min(max_w, rng.uniform(1.6, 2.4))
    d = min(max_d, rng.uniform(1.6, 2.4))
    h = rng.uniform(3.5, 7.5)
    palette = (BRONZE_GLASS, CHARCOAL, COOL_GLASS, BLUE_GLASS)
    mat = rgba_material(rng.choice(palette), shininess=42.0)
    _box(day, cx, cy, w, d, h, mat)
    # Vertical mullion stripes.
    mull = rgba_material((0.12, 0.12, 0.13, 1.0), shininess=30.0)
    for i in range(-2, 3):
        _box(day, cx + i * w * 0.18, cy + d * 0.51, 0.04, 0.03, h, mull)
        _box(day, cx + i * w * 0.18, cy - d * 0.51, 0.04, 0.03, h, mull)
    # Recessed mechanical penthouse.
    ph = 0.35
    _box(day, cx, cy, w * 0.55, d * 0.55, ph, rgba_material(CHARCOAL), z0=h)
    _window_strips(night, cx, cy, w, d, 0.4, h - 0.3, warm=False, step=0.60)
    if h > 6.0:
        _beacon(night, cx, cy, h + ph + 0.15)


def _add_deco(
    day: NodePath,
    night: NodePath,
    cx: float,
    cy: float,
    rng: random.Random,
    max_w: float,
    max_d: float,
) -> None:
    w = min(max_w, rng.uniform(1.5, 2.2))
    d = min(max_d, rng.uniform(1.5, 2.2))
    h = rng.uniform(3.2, 6.5)
    stone = rgba_material(rng.choice((LIMESTONE, TERRACOTTA)), shininess=14.0)
    base_h = min(2.5, h * 0.45)
    _box(day, cx, cy, w, d, base_h, stone)
    z = base_h
    n_setbacks = rng.randint(2, 3)
    rem = h - base_h
    for i in range(n_setbacks):
        scale = 1.0 - 0.14 * (i + 1)
        th = rem / n_setbacks
        _box(day, cx, cy, w * scale, d * scale, th, stone, z0=z)
        z += th
    # Pyramid or lantern crown.
    if rng.random() < 0.55:
        _pyramid(day, cx, cy, w * 0.35, d * 0.35, 0.55, stone, z0=h)
    else:
        lantern = rgba_material(WHITE_CROWN)
        _box(day, cx, cy, w * 0.28, d * 0.28, 0.45, lantern, z0=h)
        _crown_band(night, cx, cy, w * 0.28, d * 0.28, h + 0.4)
    _window_strips(night, cx, cy, w, d, 0.4, h - 0.3, warm=True, step=0.55)


def _add_condo(
    day: NodePath,
    night: NodePath,
    cx: float,
    cy: float,
    rng: random.Random,
    max_w: float,
    max_d: float,
) -> None:
    podium = rgba_material(PODIUM_CONCRETE, shininess=10.0)
    glass = rgba_material(rng.choice((TEAL_GLASS, BLUE_GLASS, COOL_GLASS)), shininess=40.0)
    pw = min(max_w, 2.4)
    pd = min(max_d, 2.4)
    _box(day, cx, cy, pw, pd, 0.75, podium)
    tw = min(max_w * 0.85, rng.uniform(1.3, 1.8))
    td = min(max_d * 0.85, rng.uniform(1.3, 1.8))
    th = rng.uniform(3.0, 6.2)
    _box(day, cx, cy, tw, td, th, glass, z0=0.75)
    # Projecting balcony slabs.
    bal = rgba_material((0.75, 0.78, 0.80, 1.0), shininess=35.0)
    z = 1.1
    while z < 0.75 + th - 0.2:
        _box_at_z(day, cx, cy + td * 0.52, tw * 0.92, 0.12, 0.05, z, bal)
        _box_at_z(day, cx, cy - td * 0.52, tw * 0.92, 0.12, 0.05, z, bal)
        z += 0.55
    _window_strips(night, cx, cy, tw, td, 0.9, 0.75 + th - 0.3, warm=True, step=0.55)
    if 0.75 + th > 6.0:
        _beacon(night, cx, cy, 0.75 + th + 0.2)


def _add_chicago_school(
    day: NodePath,
    night: NodePath,
    cx: float,
    cy: float,
    rng: random.Random,
    max_w: float,
    max_d: float,
) -> None:
    w = min(max_w, rng.uniform(1.4, 2.2))
    d = min(max_d, rng.uniform(1.8, 2.4))
    h = rng.uniform(1.4, 2.6)
    mat = rgba_material(rng.choice((BRICK_RED, TERRACOTTA, LIMESTONE)), shininess=12.0)
    _box(day, cx, cy, w, d, h, mat)
    # Chicago-window grid suggestion — wide horizontal bands.
    trim = rgba_material((0.55, 0.52, 0.48, 1.0), shininess=10.0)
    z = 0.35
    while z < h - 0.25:
        _box_at_z(day, cx, cy + d * 0.51, w * 0.9, 0.04, 0.08, z, trim)
        _box_at_z(day, cx, cy - d * 0.51, w * 0.9, 0.04, 0.08, z, trim)
        z += 0.32
    # Heavy overhanging cornice.
    _box(day, cx, cy, w * 1.08, d * 1.08, 0.14, trim, z0=h)
    _window_strips(night, cx, cy, w, d, 0.3, h - 0.2, warm=True, step=0.40)


_ARCHETYPES = {
    "mies": _add_mies,
    "deco": _add_deco,
    "condo": _add_condo,
    "chicago": _add_chicago_school,
}


def _place_in_block(
    day: NodePath,
    night: NodePath,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    reserves: list[tuple[float, float, float, float]],
) -> None:
    """Pack 1–4 towers inside a street-bounded block pad."""
    mid_x = (x0 + x1) * 0.5
    mid_y = (y0 + y1) * 0.5
    if _in_grant(mid_x, mid_y):
        return
    if mid_x < DT_X0 or mid_x > DT_X1 or mid_y < DT_Y0 or mid_y > DT_Y1:
        return

    x_span = _usable_span(x0, x1, ARTERIAL_X)
    y_span = _usable_span(y0, y1, ARTERIAL_Y)
    if x_span is None or y_span is None:
        return
    pad_x0, pad_x1 = x_span
    pad_y0, pad_y1 = y_span
    pad_w = pad_x1 - pad_x0
    pad_d = pad_y1 - pad_y0
    if pad_w < 1.3 or pad_d < 1.3:
        return

    rng = random.Random(hash((round(mid_x, 2), round(mid_y, 2))) & 0xFFFFFFFF)
    if _is_loop_core(mid_x, mid_y):
        count = rng.randint(2, 4)
    else:
        count = rng.randint(1, 2)

    # Candidate slots: 2×2 grid inside the pad.
    slots: list[tuple[float, float, float, float]] = []
    if count == 1:
        slots.append((mid_x, mid_y, pad_w * 0.92, pad_d * 0.92))
    else:
        qx = (pad_x0 + pad_x1) * 0.5
        qy = (pad_y0 + pad_y1) * 0.5
        hw = pad_w * 0.46
        hd = pad_d * 0.46
        candidates = (
            ((pad_x0 + qx) * 0.5, (pad_y0 + qy) * 0.5, hw, hd),
            ((pad_x1 + qx) * 0.5, (pad_y0 + qy) * 0.5, hw, hd),
            ((pad_x0 + qx) * 0.5, (pad_y1 + qy) * 0.5, hw, hd),
            ((pad_x1 + qx) * 0.5, (pad_y1 + qy) * 0.5, hw, hd),
        )
        picks = list(candidates)
        rng.shuffle(picks)
        slots = picks[:count]

    for cx, cy, max_w, max_d in slots:
        if _in_grant(cx, cy) or _in_reserve(cx, cy, reserves):
            continue
        # Keep footprints inside the pad.
        max_w = min(max_w, (cx - pad_x0) * 2, (pad_x1 - cx) * 2)
        max_d = min(max_d, (cy - pad_y0) * 2, (pad_y1 - cy) * 2)
        if max_w < 1.2 or max_d < 1.2:
            continue
        kind = _pick_mix(rng, cx, cy)
        _ARCHETYPES[kind](day, night, cx, cy, rng, max_w, max_d)


def _build_infill(
    day: NodePath,
    night: NodePath,
    reserves: list[tuple[float, float, float, float]],
) -> None:
    xs = list(NS_STREETS)
    ys = list(EW_STREETS)
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            _place_in_block(day, night, xs[i], xs[i + 1], ys[j], ys[j + 1], reserves)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def build_downtown_highrises(parent: NodePath) -> dict[str, Any]:
    """Build downtown landmarks + infill. Returns node handles for night toggle.

    Keys: ``root``, ``landmarks``, ``highrises``, ``night_glow``, ``grant_park``.
    """
    root = parent.attachNewNode("downtown_chicago")
    grant = root.attachNewNode("grant_park")
    landmarks = root.attachNewNode("downtown_landmarks_node")
    highrises = root.attachNewNode("downtown_highrises_node")
    night = root.attachNewNode("downtown_night_glow_node")
    night.setLightOff(1)
    night.hide()

    _grant_park(grant)
    reserves = _build_landmarks(landmarks, night)
    _build_infill(highrises, night, reserves)

    landmarks.flattenStrong()
    highrises.flattenStrong()
    night.flattenStrong()
    grant.flattenStrong()

    return {
        "root": root,
        "landmarks": landmarks,
        "highrises": highrises,
        "night_glow": night,
        "grant_park": grant,
    }
