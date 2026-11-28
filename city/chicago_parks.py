"""Chicago civic parks, boulevard medians, and neighborhood pocket parks (2×).

Clears residential / commercial fabric via ``PARK_VOIDS`` in ``city.geo``, then
lays multi-tone turf, winding paths, low-poly trees, athletic fields, landmarks,
and vintage acorn lamps. Geometry batches into 1-mile ``parks_sector_X_Y`` nodes
with ``flattenStrong`` for 100+ FPS. Night bulbs / glow pools toggle with the
street-light day-cycle (same path as L-key / dusk illumination).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from panda3d.core import (
    ColorBlendAttrib,
    Material,
    NodePath,
    TransparencyAttrib,
)

from city.collision2d import (
    COLLIDER_BUILDING,
    register_building,
    register_pillar,
    register_static,
)
from city.geo import (
    BLOCK_100,
    DOUGLAS_PARK_VOID,
    GARFIELD_PARK_VOID,
    GRANT_PARK_VOID,
    HUMBOLDT_PARK_VOID,
    JACKSON_PARK_VOID,
    LINCOLN_PARK_VOID,
    MARQUETTE_PARK_VOID,
    PARK_VOIDS,
    UNITS_PER_MILE,
    WASHINGTON_PARK_VOID,
)
from city.materials import rgba_material
from city.mesh import (
    box_instance,
    chamfer_box_instance,
    make_flat_deck_batch,
    make_glow_disk,
    make_pyramid,
    z_cylinder_instance,
)

# ---------------------------------------------------------------------------
# Scale / Z stack
# ---------------------------------------------------------------------------
SECTOR_SIZE = UNITS_PER_MILE
BLOCK_SHORT = BLOCK_100 * 0.5

TURF_Z = -0.04
PATH_Z = 0.008
FIELD_Z = 0.006
MEDIAN_Z = 0.005
POOL_Z = 0.012
LAMP_H = 0.32

TURF_EMERALD = (0.15, 0.30, 0.14, 1.0)
TURF_MEADOW = (0.18, 0.34, 0.15, 1.0)
TURF_FAIRWAY = (0.14, 0.32, 0.13, 1.0)
TURF_DARK = (0.12, 0.26, 0.12, 1.0)
PATH_RGBA = (0.62, 0.60, 0.55, 1.0)
DIRT_RGBA = (0.68, 0.54, 0.38, 1.0)
COURT_RGBA = (0.16, 0.36, 0.48, 1.0)
LINE_RGBA = (0.92, 0.92, 0.90, 1.0)
LIMESTONE = (0.78, 0.74, 0.66, 1.0)
BRICK = (0.48, 0.28, 0.22, 1.0)
IRON = (0.12, 0.12, 0.13, 1.0)
LEAF_A = (0.14, 0.34, 0.13, 1.0)
LEAF_B = (0.20, 0.42, 0.16, 1.0)
LEAF_C = (0.11, 0.27, 0.11, 1.0)
BARK = (0.28, 0.18, 0.10, 1.0)
WATER_TEAL = (0.12, 0.55, 0.58, 1.0)
WATER_AMBER = (0.55, 0.42, 0.18, 1.0)
GLASS_GREEN = (0.55, 0.72, 0.52, 0.45)
GOLD = (0.85, 0.68, 0.18, 1.0)
SILVER = (0.78, 0.80, 0.84, 1.0)
WARM_GLOW = (1.0, 0.82, 0.48, 1.0)

BOULEVARD_WIDTH = 1.1
MEDIAN_WIDTH = 0.35
PATH_WIDTH = 0.12

PARKS_HIDE_DIST = 420.0
PARKS_VIEW_FACTOR = 0.55
PARKS_VIEW_MIN = 90.0
PARKS_MAX_TILES = 6

_TREE_TEMPLATES: dict[str, NodePath] = {}
_LAMP_TEMPLATES: dict[str, NodePath] = {}


@dataclass(frozen=True)
class ParkDef:
    key: str
    void: tuple[float, float, float, float]
    turf: tuple[float, float, float, float] = TURF_EMERALD


MAJOR_PARKS: tuple[ParkDef, ...] = (
    ParkDef("grant", GRANT_PARK_VOID, TURF_EMERALD),
    ParkDef("lincoln", LINCOLN_PARK_VOID, TURF_MEADOW),
    ParkDef("humboldt", HUMBOLDT_PARK_VOID, TURF_MEADOW),
    ParkDef("garfield", GARFIELD_PARK_VOID, TURF_EMERALD),
    ParkDef("douglas", DOUGLAS_PARK_VOID, TURF_MEADOW),
    ParkDef("washington", WASHINGTON_PARK_VOID, TURF_FAIRWAY),
    ParkDef("jackson", JACKSON_PARK_VOID, TURF_MEADOW),
    ParkDef("marquette", MARQUETTE_PARK_VOID, TURF_FAIRWAY),
)

# Half-mile / named spines — turf, trees, and boulevard medians leave these open.
ROAD_GAP = 0.62  # arterial half-deck + shoulder so grass never covers pavement
INTERSECT_GAP = 0.90  # boulevard median break at cross-street intersections
POCKET_INSET = 0.38  # curb setback so pocket turf stays inside the lot

ARTERIAL_X: tuple[float, ...] = (
    -379.8,
    -337.6,
    -316.5,
    -295.4,
    -274.3,
    -253.2,
    -232.1,
    -211.0,
    -189.9,
    -179.4,
    -168.8,
    -158.2,
    -147.7,
    -126.6,
    -105.5,
    -84.4,
    -63.3,
    -42.2,
    -28.5,
    -26.4,
    -21.1,
    -15.8,
    -10.6,
    -7.4,
    -5.3,
    -1.9,
    0.0,
    2.6,
    5.3,
    10.6,
    16.0,
    21.1,
    42.2,
    47.5,
    63.3,
    84.4,
)
ARTERIAL_Y: tuple[float, ...] = (
    -501.1,
    -458.9,
    -437.8,
    -416.7,
    -395.6,
    -374.5,
    -353.4,
    -332.3,
    -311.2,
    -290.1,
    -269.0,
    -247.9,
    -226.8,
    -205.7,
    -184.6,
    -163.5,
    -147.7,
    -126.6,
    -116.0,
    -95.0,
    -74.0,
    -63.3,
    -42.2,
    -31.6,
    -26.4,
    -21.1,
    -15.8,
    -10.6,
    -5.3,
    0.0,
    5.3,
    7.9,
    15.8,
    21.1,
    26.4,
    42.2,
    63.3,
    84.4,
    105.5,
    126.6,
    137.1,
    147.7,
    168.8,
    189.9,
    211.0,
    232.1,
    253.2,
    274.3,
    295.4,
    337.6,
    400.9,
)


def _mid_block(
    x_street: float, y_street: float, *, east: bool = True, north: bool = True
) -> tuple[float, float]:
    """Lot center of the block adjacent to an intersection (never on the cross)."""
    sx = BLOCK_100 * 0.5 if east else -BLOCK_100 * 0.5
    sy = BLOCK_100 * 0.5 if north else -BLOCK_100 * 0.5
    return _clear_of_spines(x_street + sx, y_street + sy)


def _clear_of_spines(x: float, y: float) -> tuple[float, float]:
    """Nudge a point off any arterial spine so pocket centres stay in the lot."""
    gap = ROAD_GAP + 0.15
    for _ in range(4):
        moved = False
        for sx in ARTERIAL_X:
            if abs(x - sx) < gap:
                x = sx + gap if x >= sx else sx - gap
                moved = True
        for sy in ARTERIAL_Y:
            if abs(y - sy) < gap:
                y = sy + gap if y >= sy else sy - gap
                moved = True
        if not moved:
            break
    return (round(x, 3), round(y, 3))


# Compact neighborhood squares — centers are mid-block, not on street spines.
POCKET_PARKS: tuple[tuple[float, float, str], ...] = (
    (*_mid_block(-84.4, 84.4, east=True, north=False), "wicker_park"),
    (*_mid_block(-168.8, 147.7, east=True, north=False), "palmer_square"),
    # Oz Park: Webster / Larrabee — stay west of Canal, south of Fullerton.
    (*_mid_block(-15.8, 126.6, east=False, north=False), "oz_park"),
    (*_mid_block(-84.4, 274.3, east=True, north=False), "winnemac_park"),
    (*_mid_block(-42.2, 42.2, east=False, north=True), "eckhart_park"),
    (*_mid_block(-105.5, -184.6, east=True, north=True), "mckinley_park"),
    # Ping Tom: east of Wentworth band, north of 18th — avoid State/Wabash.
    (*_mid_block(-5.3, -95.0, east=False, north=True), "ping_tom_park"),
    (*_mid_block(-126.6, 137.1, east=True, north=True), "logan_boulevard_park"),
    (*_mid_block(-63.3, 105.5, east=True, north=False), "wrightwood_park"),
    (*_mid_block(-21.1, 168.8, east=False, north=False), "hamlin_park"),
    (*_mid_block(-42.2, 189.9, east=True, north=False), "chalmers_park"),
    (*_mid_block(-84.4, 211.0, east=True, north=False), "gossler_park"),
    (*_mid_block(-147.7, 42.2, east=False, north=True), "humboldt_pocket"),
    (*_mid_block(-189.9, 0.0, east=True, north=True), "garfield_pocket"),
    (*_mid_block(-168.8, -74.0, east=True, north=False), "douglas_pocket"),
    (*_mid_block(-63.3, -126.6, east=True, north=True), "sherman_park"),
    (*_mid_block(-105.5, -226.8, east=True, north=False), "cornell_square"),
    (*_mid_block(-42.2, -269.0, east=True, north=True), "washington_pocket"),
    # Armour Square: west of State, north of 31st band.
    (*_mid_block(0.0, -147.7, east=False, north=True), "armour_square"),
    (*_mid_block(16.0, -232.1, east=True, north=False), "washington_park_west"),
    (*_mid_block(-211.0, 84.4, east=True, north=True), "austin_town_hall"),
    (*_mid_block(-232.1, -42.2, east=True, north=True), "columbus_park_east"),
    (*_mid_block(-84.4, -63.3, east=True, north=False), "harrison_park"),
    (*_mid_block(-126.6, -147.7, east=True, north=True), "park_no_321"),
    (*_mid_block(-21.1, 232.1, east=False, north=False), "river_park_south"),
    (*_mid_block(-63.3, 253.2, east=True, north=False), "welles_park"),
    (*_mid_block(-147.7, 211.0, east=False, north=False), "kelvyn_park"),
    (*_mid_block(5.3, 63.3, east=True, north=True), "lake_shore_pocket"),
)

BOULEVARDS: tuple[tuple[str, str, float, float, float, float], ...] = (
    # key, axis, coord, t0, t1, tree_spacing
    ("logan", "y", 137.1, -179.4, -105.5, 1.9),
    ("kedzie", "x", -168.8, -95.0, 211.0, 2.0),
    ("humboldt", "x", -158.2, 63.3, 126.6, 1.8),
    ("douglas", "y", -74.0, -200.5, -126.6, 1.9),
    ("drexel", "x", 47.5, -332.3, -211.0, 1.8),
    ("garfield", "y", -290.1, -211.0, 42.2, 2.0),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hash01(x: float, y: float, salt: float = 0.0) -> float:
    n = math.sin(x * 12.9898 + y * 78.233 + salt * 43.17) * 43758.5453
    return n - math.floor(n)


def _in_bbox(x: float, y: float, box: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


def pocket_park_size() -> tuple[float, float]:
    """Inset footprint so pocket turf never reaches curb / intersection."""
    return (BLOCK_100 - 2.0 * POCKET_INSET, BLOCK_SHORT - 2.0 * POCKET_INSET)


def pocket_park_voids() -> tuple[tuple[float, float, float, float], ...]:
    """Inset AABB keep-outs for housing (does not swallow bounding streets)."""
    pw, pd = pocket_park_size()
    hw, hd = pw * 0.5, pd * 0.5
    return tuple((cx - hw, cy - hd, cx + hw, cy + hd) for cx, cy, _name in POCKET_PARKS)


def in_park_void(x: float, y: float) -> bool:
    """True if a point sits inside any major civic park clearance void."""
    return any(_in_bbox(x, y, v) for v in PARK_VOIDS)


def in_any_park(x: float, y: float) -> bool:
    """Major parks + neighborhood pocket parks (housing purge)."""
    if in_park_void(x, y):
        return True
    return any(_in_bbox(x, y, v) for v in pocket_park_voids())


def park_voids() -> tuple[tuple[float, float, float, float], ...]:
    """Major park voids only — used to clip minor streets (not pocket lots)."""
    return PARK_VOIDS


def _sector_key(x: float, y: float) -> tuple[int, int]:
    return (int(math.floor(x / SECTOR_SIZE)), int(math.floor(y / SECTOR_SIZE)))


def _split_spans(
    a: float, b: float, spines: tuple[float, ...] | list[float], gap: float
) -> list[tuple[float, float]]:
    """Keep open intervals of [a,b] that stay clear of spine ± gap corridors."""
    if a > b:
        a, b = b, a
    cuts = [a, b]
    for s in spines:
        if a < s < b:
            cuts.append(s - gap)
            cuts.append(s + gap)
    cuts = sorted(set(round(c, 4) for c in cuts))
    spans: list[tuple[float, float]] = []
    for i in range(len(cuts) - 1):
        lo, hi = cuts[i], cuts[i + 1]
        if hi - lo < 0.08:
            continue
        mid = 0.5 * (lo + hi)
        if any(abs(mid - s) < gap for s in spines):
            continue
        spans.append((lo, hi))
    return spans


def _on_road(x: float, y: float, gap: float = ROAD_GAP) -> bool:
    """True when a prop would sit on an arterial / boulevard pavement corridor."""
    return any(abs(x - sx) < gap for sx in ARTERIAL_X) or any(
        abs(y - sy) < gap for sy in ARTERIAL_Y
    )


def _on_intersection(x: float, y: float, gap: float = INTERSECT_GAP) -> bool:
    """True only at a cross-street junction (both an N–S and E–W spine nearby)."""
    on_x = any(abs(x - sx) < gap for sx in ARTERIAL_X)
    on_y = any(abs(y - sy) < gap for sy in ARTERIAL_Y)
    return on_x and on_y


def _metallic(rgb: tuple[float, float, float], shininess: float = 96.0) -> Material:
    mat = Material()
    mat.setAmbient((rgb[0] * 0.35, rgb[1] * 0.35, rgb[2] * 0.35, 1))
    mat.setDiffuse((*rgb, 1))
    mat.setSpecular((0.95, 0.95, 0.98, 1))
    mat.setShininess(shininess)
    return mat


def _emissive(rgb: tuple[float, float, float]) -> Material:
    mat = Material()
    mat.setAmbient((*rgb, 1))
    mat.setDiffuse((*rgb, 1))
    mat.setEmission((min(1.0, rgb[0] * 1.4), min(1.0, rgb[1] * 1.3), rgb[2] * 0.9, 1))
    mat.setShininess(24)
    return mat


class _SectorBins:
    """Lazy per-mile-sector NodePaths for day mesh + night lamps."""

    def __init__(self, root: NodePath, night_root: NodePath) -> None:
        self.root = root
        self.night_root = night_root
        self.day: dict[tuple[int, int], NodePath] = {}
        self.bulbs: dict[tuple[int, int], NodePath] = {}
        self.pools: dict[tuple[int, int], NodePath] = {}

    def day_np(self, x: float, y: float) -> NodePath:
        key = _sector_key(x, y)
        node = self.day.get(key)
        if node is None:
            sx, sy = key
            node = self.root.attachNewNode(f"parks_sector_{sx}_{sy}")
            self.day[key] = node
        return node

    def night_bins(self, x: float, y: float) -> tuple[NodePath, NodePath]:
        key = _sector_key(x, y)
        bulbs = self.bulbs.get(key)
        pools = self.pools.get(key)
        if bulbs is None:
            sx, sy = key
            bulbs = self.night_root.attachNewNode(f"park_bulbs_{sx}_{sy}")
            pools = self.night_root.attachNewNode(f"park_pools_{sx}_{sy}")
            self.bulbs[key] = bulbs
            self.pools[key] = pools
        return bulbs, pools


def _turf_rect(
    bins: _SectorBins,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    rgba: tuple[float, float, float, float],
) -> None:
    sx = abs(x1 - x0)
    sy = abs(y1 - y0)
    if sx < 0.05 or sy < 0.05:
        return
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    pad = box_instance(bins.day_np(cx, cy), sx, sy, 0.05, top=True, bottom=False)
    pad.setPos(cx, cy, TURF_Z)
    pad.setMaterial(rgba_material(rgba), 1)


def _turf(
    bins: _SectorBins,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    rgba: tuple[float, float, float, float],
) -> None:
    """Lay turf in patches that leave arterial corridors / intersections clear."""
    for xa, xb in _split_spans(x0, x1, ARTERIAL_X, ROAD_GAP):
        for ya, yb in _split_spans(y0, y1, ARTERIAL_Y, ROAD_GAP):
            _turf_rect(bins, xa, ya, xb, yb, rgba)


def _path_seg(
    segs: list[tuple[float, float, float, float, float, float]],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    width: float = PATH_WIDTH,
) -> None:
    segs.append((x0, y0, x1, y1, width, PATH_Z))


def _flush_paths(
    bins: _SectorBins, segs: list[tuple[float, float, float, float, float, float]], name: str
) -> None:
    if not segs:
        return
    # Bin by sector of segment midpoint so flatten stays local.
    by_sector: dict[tuple[int, int], list] = {}
    for seg in segs:
        x0, y0, x1, y1, w, z = seg
        key = _sector_key(0.5 * (x0 + x1), 0.5 * (y0 + y1))
        by_sector.setdefault(key, []).append(seg)
    path_mat = rgba_material(PATH_RGBA, shininess=4.0)
    for key, chunk in by_sector.items():
        parent = bins.day.get(key)
        if parent is None:
            sx, sy = key
            parent = bins.root.attachNewNode(f"parks_sector_{sx}_{sy}")
            bins.day[key] = parent
        node = parent.attachNewNode(
            make_flat_deck_batch(chunk, 0.02, name=name, top_only=True)
        )
        node.setMaterial(path_mat, 1)


def _box(
    parent: NodePath,
    cx: float,
    cy: float,
    sx: float,
    sy: float,
    sz: float,
    material,
    *,
    z0: float = 0.0,
    collider: int | None = COLLIDER_BUILDING,
) -> NodePath:
    body = box_instance(parent, sx, sy, sz)
    body.setPos(cx, cy, z0 + sz * 0.5)
    body.setMaterial(material, 1)
    if collider is not None and sx > 0.15 and sy > 0.15:
        register_static(cx, cy, sx * 0.5, sy * 0.5, 0.0, collider)
    return body


# ---------------------------------------------------------------------------
# Trees & lamps (shared templates)
# ---------------------------------------------------------------------------
def _ensure_tree_templates() -> None:
    if _TREE_TEMPLATES:
        return
    bark = rgba_material(BARK, shininess=4.0)
    leaves = (
        rgba_material(LEAF_A, shininess=3.0),
        rgba_material(LEAF_B, shininess=3.0),
        rgba_material(LEAF_C, shininess=3.0),
    )

    def _oak(height: float, name: str) -> NodePath:
        root = NodePath(name)
        trunk_h = height * 0.42
        trunk = z_cylinder_instance(root, 0.025, trunk_h, segments=6)
        trunk.setPos(0.0, 0.0, trunk_h * 0.5)
        trunk.setMaterial(bark, 1)
        # 2–3 overlapping canopy blobs.
        for i, (rx, ry, rz, lift, leaf) in enumerate(
            (
                (0.11, 0.11, 0.10, height * 0.62, leaves[0]),
                (0.09, 0.10, 0.09, height * 0.78, leaves[1]),
                (0.07, 0.08, 0.08, height * 0.90, leaves[2]),
            )
        ):
            canopy = z_cylinder_instance(root, rx, rz * 2.0, segments=8)
            canopy.setPos(0.02 * (i - 1), 0.015 * (i % 2), lift)
            canopy.setScale(1.0, ry / max(rx, 1e-6), 1.0)
            canopy.setMaterial(leaf, 1)
        root.flattenStrong()
        return root

    def _locust(height: float, name: str) -> NodePath:
        root = NodePath(name)
        trunk_h = height * 0.48
        trunk = z_cylinder_instance(root, 0.018, trunk_h, segments=6)
        trunk.setPos(0.0, 0.0, trunk_h * 0.5)
        trunk.setMaterial(bark, 1)
        for i, (r, lift, leaf) in enumerate(
            (
                (0.09, height * 0.70, leaves[1]),
                (0.07, height * 0.88, leaves[0]),
            )
        ):
            canopy = z_cylinder_instance(root, r, r * 1.1, segments=8)
            canopy.setPos(0.01 * i, -0.01 * i, lift)
            canopy.setMaterial(leaf, 1)
        root.flattenStrong()
        return root

    _TREE_TEMPLATES["oak_a"] = _oak(0.32, "oak_a")
    _TREE_TEMPLATES["oak_b"] = _oak(0.38, "oak_b")
    _TREE_TEMPLATES["oak_c"] = _oak(0.42, "oak_c")
    _TREE_TEMPLATES["locust_a"] = _locust(0.24, "locust_a")
    _TREE_TEMPLATES["locust_b"] = _locust(0.28, "locust_b")


def _ensure_lamp_templates() -> None:
    if _LAMP_TEMPLATES:
        return
    iron = rgba_material(IRON, shininess=18.0)
    pole = NodePath("park_lamp_pole")
    shaft = z_cylinder_instance(pole, 0.012, LAMP_H, segments=6)
    shaft.setPos(0.0, 0.0, LAMP_H * 0.5)
    shaft.setMaterial(iron, 1)
    base = z_cylinder_instance(pole, 0.028, 0.02, segments=6)
    base.setPos(0.0, 0.0, 0.01)
    base.setMaterial(iron, 1)
    pole.flattenStrong()
    _LAMP_TEMPLATES["pole"] = pole

    globe = NodePath("park_lamp_globe")
    bulb = z_cylinder_instance(globe, 0.035, 0.055, segments=8)
    bulb.setPos(0.0, 0.0, 0.0)
    bulb.setMaterial(_emissive(WARM_GLOW[:3]), 1)
    globe.flattenStrong()
    globe.setLightOff(1)
    _LAMP_TEMPLATES["globe"] = globe

    pool = NodePath(make_glow_disk(0.22, (*WARM_GLOW[:3], 0.45), segments=8))
    pool.setLightOff(1)
    _LAMP_TEMPLATES["pool"] = pool


def _place_tree(
    bins: _SectorBins,
    x: float,
    y: float,
    *,
    ornamental: bool = False,
    collider: bool = True,
    boulevard: bool = False,
) -> None:
    # Park interiors avoid all pavement; boulevard rows only skip cross junctions.
    if boulevard:
        if _on_intersection(x, y):
            return
    elif _on_road(x, y):
        return
    _ensure_tree_templates()
    h = _hash01(x, y, 2.2)
    if ornamental:
        key = "locust_a" if h < 0.5 else "locust_b"
    else:
        key = "oak_a" if h < 0.34 else ("oak_b" if h < 0.67 else "oak_c")
    inst = _TREE_TEMPLATES[key].copyTo(bins.day_np(x, y))
    inst.setPos(x, y, 0.0)
    inst.setH(h * 360.0)
    s = 0.92 + 0.18 * _hash01(x, y, 4.1)
    inst.setScale(s)
    if collider:
        register_pillar(x, y, 0.03)


def _place_lamp(
    bins: _SectorBins, x: float, y: float, *, boulevard: bool = False
) -> None:
    if boulevard:
        if _on_intersection(x, y):
            return
    elif _on_road(x, y, gap=INTERSECT_GAP * 0.85):
        return
    _ensure_lamp_templates()
    parent = bins.day_np(x, y)
    pole = _LAMP_TEMPLATES["pole"].copyTo(parent)
    pole.setPos(x, y, 0.0)
    bulbs, pools = bins.night_bins(x, y)
    globe = _LAMP_TEMPLATES["globe"].copyTo(bulbs)
    globe.setPos(x, y, LAMP_H + 0.02)
    pool = _LAMP_TEMPLATES["pool"].copyTo(pools)
    pool.setPos(x, y, POOL_Z)
    pool.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd))
    pool.setTransparency(TransparencyAttrib.MAlpha)


def _tree_line(
    bins: _SectorBins,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    spacing: float,
    *,
    ornamental: bool = False,
    phase: float = 0.0,
    boulevard: bool = False,
) -> None:
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 0.2:
        return
    ux, uy = dx / length, dy / length
    n = max(1, int(length / spacing))
    for i in range(n + 1):
        t = (i + phase) / max(n, 1)
        if t > 1.0:
            break
        x = x0 + ux * length * t
        y = y0 + uy * length * t
        # Jitter off the exact line so rows don't look mechanical.
        j = (_hash01(x, y, 7.7) - 0.5) * 0.08
        _place_tree(
            bins,
            x - uy * j,
            y + ux * j,
            ornamental=ornamental,
            collider=(i % 2 == 0),
            boulevard=boulevard,
        )


def _grove(
    bins: _SectorBins,
    cx: float,
    cy: float,
    radius: float,
    count: int,
    *,
    ornamental: bool = False,
) -> None:
    for i in range(count):
        ang = (i / max(count, 1)) * math.tau + _hash01(cx, cy, i) * 0.7
        r = radius * (0.25 + 0.75 * _hash01(cx + i, cy, 3.3))
        x = cx + math.cos(ang) * r
        y = cy + math.sin(ang) * r
        _place_tree(bins, x, y, ornamental=ornamental, collider=True)


def _diamond(
    bins: _SectorBins,
    cx: float,
    cy: float,
    size: float = 0.85,
    heading: float = 0.0,
) -> None:
    if _on_road(cx, cy, gap=ROAD_GAP + size * 0.35):
        return
    parent = bins.day_np(cx, cy)
    dirt = box_instance(parent, size, size, 0.02, top=True, bottom=False)
    dirt.setPos(cx, cy, FIELD_Z)
    dirt.setH(heading)
    dirt.setMaterial(rgba_material(DIRT_RGBA), 1)
    # White foul-line cross.
    line_mat = rgba_material(LINE_RGBA, shininess=2.0)
    for hx, hy, sx, sy in (
        (0.0, 0.0, size * 0.04, size * 0.95),
        (0.0, 0.0, size * 0.95, size * 0.04),
    ):
        line = box_instance(parent, sx, sy, 0.012, top=True, bottom=False)
        line.setPos(cx + hx, cy + hy, FIELD_Z + 0.004)
        line.setH(heading)
        line.setMaterial(line_mat, 1)
    # Outfield grass pad behind home.
    rad = math.radians(heading)
    ox = math.cos(rad) * size * 0.55
    oy = math.sin(rad) * size * 0.55
    out = box_instance(parent, size * 1.15, size * 0.7, 0.018, top=True, bottom=False)
    out.setPos(cx + ox, cy + oy, FIELD_Z - 0.001)
    out.setH(heading)
    out.setMaterial(rgba_material(TURF_DARK), 1)


def _court(
    bins: _SectorBins,
    cx: float,
    cy: float,
    sx: float = 0.55,
    sy: float = 0.95,
    heading: float = 0.0,
) -> None:
    if _on_road(cx, cy, gap=ROAD_GAP + max(sx, sy) * 0.35):
        return
    parent = bins.day_np(cx, cy)
    pad = box_instance(parent, sx, sy, 0.02, top=True, bottom=False)
    pad.setPos(cx, cy, FIELD_Z)
    pad.setH(heading)
    pad.setMaterial(rgba_material(COURT_RGBA), 1)
    mid = box_instance(parent, sx * 0.9, 0.02, 0.01, top=True, bottom=False)
    mid.setPos(cx, cy, FIELD_Z + 0.003)
    mid.setH(heading)
    mid.setMaterial(rgba_material(LINE_RGBA), 1)


def _path_grid(
    segs: list[tuple[float, float, float, float, float, float]],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    step: float = 8.0,
    diagonal: bool = True,
) -> None:
    """Sparse formal / meadow path network inside a park rectangle."""
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    # Cross axes.
    _path_seg(segs, x0 + 0.4, cy, x1 - 0.4, cy)
    _path_seg(segs, cx, y0 + 0.4, cx, y1 - 0.4)
    if diagonal:
        _path_seg(segs, x0 + 0.6, y0 + 0.6, x1 - 0.6, y1 - 0.6, PATH_WIDTH * 0.85)
        _path_seg(segs, x0 + 0.6, y1 - 0.6, x1 - 0.6, y0 + 0.6, PATH_WIDTH * 0.85)
    # Perimeter walk.
    _path_seg(segs, x0 + 0.35, y0 + 0.35, x1 - 0.35, y0 + 0.35)
    _path_seg(segs, x0 + 0.35, y1 - 0.35, x1 - 0.35, y1 - 0.35)
    _path_seg(segs, x0 + 0.35, y0 + 0.35, x0 + 0.35, y1 - 0.35)
    _path_seg(segs, x1 - 0.35, y0 + 0.35, x1 - 0.35, y1 - 0.35)
    # Occasional interior laterals.
    y = y0 + step
    while y < y1 - step * 0.4:
        _path_seg(segs, x0 + 0.5, y, x1 - 0.5, y, PATH_WIDTH * 0.7)
        y += step
    x = x0 + step
    while x < x1 - step * 0.4:
        _path_seg(segs, x, y0 + 0.5, x, y1 - 0.5, PATH_WIDTH * 0.7)
        x += step


def _perimeter_trees(
    bins: _SectorBins,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    spacing: float = 1.7,
    *,
    inset: float = 0.55,
) -> None:
    _tree_line(bins, x0 + inset, y0 + inset, x1 - inset, y0 + inset, spacing)
    _tree_line(bins, x0 + inset, y1 - inset, x1 - inset, y1 - inset, spacing)
    _tree_line(bins, x0 + inset, y0 + inset, x0 + inset, y1 - inset, spacing)
    _tree_line(bins, x1 - inset, y0 + inset, x1 - inset, y1 - inset, spacing)


def _path_lamps(
    bins: _SectorBins,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    spacing: float = 3.2,
) -> None:
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    for ax0, ay0, ax1, ay1 in (
        (x0 + 0.5, cy, x1 - 0.5, cy),
        (cx, y0 + 0.5, cx, y1 - 0.5),
        (x0 + 0.4, y0 + 0.4, x1 - 0.4, y0 + 0.4),
        (x0 + 0.4, y1 - 0.4, x1 - 0.4, y1 - 0.4),
    ):
        dx, dy = ax1 - ax0, ay1 - ay0
        length = math.hypot(dx, dy)
        if length < 0.5:
            continue
        n = max(1, int(length / spacing))
        for i in range(n + 1):
            t = i / n
            _place_lamp(bins, ax0 + dx * t, ay0 + dy * t)


# ---------------------------------------------------------------------------
# Landmark builders
# ---------------------------------------------------------------------------
def _buckingham_fountain(bins: _SectorBins, cx: float, cy: float) -> None:
    parent = bins.day_np(cx, cy)
    limestone = rgba_material(LIMESTONE, shininess=22.0)
    # Tiered octagonal basin (chamfer approximates octagon).
    basin = chamfer_box_instance(parent, 1.7, 1.7, 0.08, chamfer=0.35)
    basin.setPos(cx, cy, 0.04)
    basin.setMaterial(limestone, 1)
    register_building(cx, cy, 0.85, 0.85, 0.0)
    water = z_cylinder_instance(parent, 0.72, 0.04, segments=10)
    water.setPos(cx, cy, 0.07)
    water.setMaterial(_emissive(WATER_TEAL[:3]), 1)
    water.setLightOff(1)
    # Animated-look jets (static emissive columns — cheap night presence).
    for i, (r, h, tint) in enumerate(
        (
            (0.04, 0.55, WATER_TEAL),
            (0.03, 0.38, WATER_AMBER),
            (0.025, 0.28, WATER_TEAL),
        )
    ):
        for k in range(8 if i == 0 else 6):
            ang = k * math.tau / (8 if i == 0 else 6) + i * 0.2
            rad = 0.12 + i * 0.18
            jx = cx + math.cos(ang) * rad
            jy = cy + math.sin(ang) * rad
            jet = z_cylinder_instance(parent, r, h, segments=5)
            jet.setPos(jx, jy, 0.08 + h * 0.5)
            jet.setMaterial(_emissive(tint[:3]), 1)
            jet.setLightOff(1)
    # Formal paths around the fountain.
    segs: list[tuple[float, float, float, float, float, float]] = []
    for a in range(8):
        ang0 = a * math.tau / 8
        ang1 = (a + 1) * math.tau / 8
        _path_seg(
            segs,
            cx + math.cos(ang0) * 1.35,
            cy + math.sin(ang0) * 1.35,
            cx + math.cos(ang1) * 1.35,
            cy + math.sin(ang1) * 1.35,
            0.14,
        )
    for dx, dy in ((0.0, 2.2), (0.0, -2.2), (2.2, 0.0), (-2.2, 0.0)):
        _path_seg(segs, cx, cy, cx + dx, cy + dy, 0.14)
    _flush_paths(bins, segs, "buckingham_paths")


def _cloud_gate(bins: _SectorBins, cx: float, cy: float) -> None:
    parent = bins.day_np(cx, cy)
    silver = _metallic(SILVER[:3], 110.0)
    # Ellipsoid approx: flattened vertical cylinder + cheek bulges.
    bean = z_cylinder_instance(parent, 0.18, 0.28, segments=12)
    bean.setPos(cx, cy, 0.14)
    bean.setScale(0.45 / 0.36, 0.28 / 0.36, 0.18 / 0.28)
    bean.setMaterial(silver, 1)
    cheek = z_cylinder_instance(parent, 0.14, 0.16, segments=10)
    cheek.setPos(cx, cy, 0.10)
    cheek.setScale(1.35, 0.85, 0.7)
    cheek.setMaterial(silver, 1)
    register_building(cx, cy, 0.22, 0.14, 0.0)


def _pritzker_pavilion(bins: _SectorBins, cx: float, cy: float) -> None:
    parent = bins.day_np(cx, cy)
    steel = _metallic((0.55, 0.58, 0.62), 64.0)
    stage = _box(parent, cx, cy - 0.25, 0.55, 0.35, 0.18, rgba_material(LIMESTONE))
    del stage
    # Sweeping trellis ribs.
    for i in range(7):
        t = (i - 3) / 3.0
        rib = box_instance(parent, 0.035, 0.95, 0.04)
        rib.setPos(cx + t * 0.45, cy + 0.15, 0.35 + abs(t) * 0.08)
        rib.setP(-18.0)
        rib.setH(t * 12.0)
        rib.setMaterial(steel, 1)
    canopy = box_instance(parent, 1.1, 0.8, 0.03, top=True, bottom=True)
    canopy.setPos(cx, cy + 0.1, 0.48)
    canopy.setMaterial(steel, 1)
    register_building(cx, cy, 0.55, 0.4, 0.0)


def _glass_conservatory(
    bins: _SectorBins, cx: float, cy: float, sx: float, sy: float
) -> None:
    parent = bins.day_np(cx, cy)
    glass = rgba_material(GLASS_GREEN, shininess=48.0)
    steel = rgba_material((0.35, 0.38, 0.36, 1.0), shininess=30.0)
    hall = box_instance(parent, sx, sy, 0.35)
    hall.setPos(cx, cy, 0.18)
    hall.setMaterial(glass, 1)
    hall.setTransparency(TransparencyAttrib.MAlpha)
    hall.setColor(*GLASS_GREEN)
    # Domed greenhouse ribs.
    for i, ox in enumerate((-0.35, 0.0, 0.35)):
        dome = z_cylinder_instance(parent, 0.22, 0.28, segments=10)
        dome.setPos(cx + ox * sx, cy, 0.42)
        dome.setScale(1.0, sy * 0.55, 1.0)
        dome.setMaterial(glass, 1)
        dome.setTransparency(TransparencyAttrib.MAlpha)
        rib = box_instance(parent, 0.03, sy * 0.9, 0.4)
        rib.setPos(cx + ox * sx, cy, 0.25)
        rib.setMaterial(steel, 1)
    register_building(cx, cy, sx * 0.5, sy * 0.5, 0.0)


def _gold_dome_fieldhouse(bins: _SectorBins, cx: float, cy: float) -> None:
    parent = bins.day_np(cx, cy)
    brick = rgba_material(BRICK, shininess=8.0)
    _box(parent, cx, cy, 0.95, 0.65, 0.32, brick)
    dome = z_cylinder_instance(parent, 0.28, 0.22, segments=12)
    dome.setPos(cx, cy, 0.42)
    dome.setMaterial(_metallic(GOLD[:3], 80.0), 1)
    cap = NodePath(make_pyramid(0.35, 0.35, 0.12))
    cap.reparentTo(parent)
    cap.setPos(cx, cy, 0.58)
    cap.setMaterial(_metallic(GOLD[:3], 80.0), 1)


def _museum_palace(
    bins: _SectorBins, cx: float, cy: float, sx: float, sy: float
) -> None:
    parent = bins.day_np(cx, cy)
    stone = rgba_material(LIMESTONE, shininess=18.0)
    _box(parent, cx, cy, sx, sy, 0.45, stone)
    wings = (
        (cx - sx * 0.38, cy, sx * 0.28, sy * 0.85, 0.38),
        (cx + sx * 0.38, cy, sx * 0.28, sy * 0.85, 0.38),
    )
    for wx, wy, wsx, wsy, wsz in wings:
        _box(parent, wx, wy, wsx, wsy, wsz, stone)
    dome = z_cylinder_instance(parent, 0.32, 0.35, segments=12)
    dome.setPos(cx, cy, 0.62)
    dome.setMaterial(stone, 1)
    register_building(cx, cy, sx * 0.5, sy * 0.5, 0.0)


def _brick_pavilion(bins: _SectorBins, cx: float, cy: float, sx: float, sy: float) -> None:
    parent = bins.day_np(cx, cy)
    _box(parent, cx, cy, sx, sy, 0.28, rgba_material(BRICK, shininess=8.0))
    roof = box_instance(parent, sx * 1.05, sy * 1.05, 0.04)
    roof.setPos(cx, cy, 0.30)
    roof.setMaterial(rgba_material((0.25, 0.22, 0.20, 1.0)), 1)


def _boat_house(bins: _SectorBins, cx: float, cy: float) -> None:
    parent = bins.day_np(cx, cy)
    stone = rgba_material(LIMESTONE, shininess=14.0)
    _box(parent, cx, cy, 0.85, 0.45, 0.28, stone)
    tower = _box(parent, cx + 0.28, cy, 0.22, 0.22, 0.48, stone)
    del tower


# ---------------------------------------------------------------------------
# Major parks
# ---------------------------------------------------------------------------
def _build_grant(bins: _SectorBins) -> None:
    x0, y0, x1, y1 = GRANT_PARK_VOID
    # Lawn terraces east of Michigan; split by Congress / Jackson.
    bands = (
        (y0, -21.1, TURF_EMERALD),
        (-21.1, -15.8, TURF_DARK),
        (-15.8, 2.5, TURF_EMERALD),
        (2.5, 10.5, TURF_MEADOW),  # Millennium Park
    )
    for ya, yb, tint in bands:
        _turf(bins, x0, max(y0, ya), x1, min(y1, yb), tint)
    segs: list[tuple[float, float, float, float, float, float]] = []
    _path_grid(segs, x0, y0, x1, y1, step=10.5)
    _flush_paths(bins, segs, "grant_paths")
    _perimeter_trees(bins, x0, y0, x1, y1, spacing=2.0)
    _grove(bins, 11.0, -5.0, 2.5, 10)
    _grove(bins, 12.0, -40.0, 2.2, 8)
    _buckingham_fountain(bins, 11.5, -21.1)
    _cloud_gate(bins, 10.5, 6.5)
    _pritzker_pavilion(bins, 12.2, 5.0)
    _path_lamps(bins, x0, y0, x1, y1, spacing=4.0)
    _diamond(bins, 9.5, -35.0, 0.7, 15.0)
    _court(bins, 13.0, -8.0)


def _build_lincoln(bins: _SectorBins) -> None:
    x0, y0, x1, y1 = LINCOLN_PARK_VOID
    # Long greenbelt — turf in mile bands for sector locality.
    y = y0
    flip = False
    while y < y1 - 0.1:
        yb = min(y + UNITS_PER_MILE, y1)
        _turf(bins, x0, y, x1, yb, TURF_MEADOW if not flip else TURF_EMERALD)
        flip = not flip
        y = yb
    segs: list[tuple[float, float, float, float, float, float]] = []
    _path_grid(segs, x0, y0, x1, y1, step=12.0)
    # Stockton / lakefront parallel walk.
    _path_seg(segs, x1 - 1.2, y0 + 1.0, x1 - 1.2, y1 - 1.0, 0.16)
    _path_seg(segs, x0 + 1.5, y0 + 1.0, x0 + 1.5, y1 - 1.0, 0.14)
    _flush_paths(bins, segs, "lincoln_paths")
    _perimeter_trees(bins, x0, y0, x1, y1, spacing=2.2, inset=0.7)
    # Cross-arterial tree gaps already handled by void clip; densify mid-blocks.
    for cy in (95.0, 115.0, 135.0, 160.0, 185.0, 220.0, 250.0):
        if y0 < cy < y1:
            _grove(bins, -8.0, cy, 3.0, 12)
            _grove(bins, 6.0, cy, 2.5, 9, ornamental=True)
    # Conservatory & Zoo.
    _glass_conservatory(bins, -14.0, 122.0, 1.1, 0.7)
    _brick_pavilion(bins, -12.0, 110.0, 1.0, 0.7)
    _brick_pavilion(bins, -10.5, 112.5, 0.55, 0.45)
    _grove(bins, -14.0, 122.0, 1.8, 6, ornamental=True)
    for i, cy in enumerate((100.0, 130.0, 155.0, 175.0, 205.0, 240.0)):
        _diamond(bins, -5.0 + (i % 3) * 4.0, cy, 0.8, 20.0 * (i % 2))
        if i % 2 == 0:
            _court(bins, 2.0, cy + 3.0)
    _path_lamps(bins, x0, y0, x1, y1, spacing=5.0)


def _build_humboldt(bins: _SectorBins) -> None:
    x0, y0, x1, y1 = HUMBOLDT_PARK_VOID
    _turf(bins, x0, y0, x1, y1, TURF_MEADOW)
    segs: list[tuple[float, float, float, float, float, float]] = []
    _path_grid(segs, x0, y0, x1, y1, step=7.0)
    # Curving carriage-drive approx (polyline).
    curve = (
        (-166.0, 66.0),
        (-162.0, 72.0),
        (-158.0, 79.0),
        (-154.0, 86.0),
        (-150.0, 92.0),
    )
    for i in range(len(curve) - 1):
        _path_seg(segs, *curve[i], *curve[i + 1], 0.28)
    _flush_paths(bins, segs, "humboldt_paths")
    _perimeter_trees(bins, x0, y0, x1, y1, spacing=1.6)
    _grove(bins, -160.0, 70.0, 3.5, 16)
    _grove(bins, -152.0, 88.0, 3.0, 14)
    _boat_house(bins, -158.0, 79.0)
    # Stable & Receptory along Division (south edge).
    _brick_pavilion(bins, -158.0, y0 + 1.1, 1.2, 0.55)
    _diamond(bins, -155.0, 85.0)
    _diamond(bins, -162.0, 72.0, heading=25.0)
    _court(bins, -151.0, 68.0)
    _path_lamps(bins, x0, y0, x1, y1, spacing=3.5)


def _build_garfield(bins: _SectorBins) -> None:
    x0, y0, x1, y1 = GARFIELD_PARK_VOID
    # Split by Madison (Y=0) and Washington Blvd (Y=+5.3).
    _turf(bins, x0, y0, x1, 0.0, TURF_EMERALD)
    _turf(bins, x0, 0.0, x1, 5.3, TURF_DARK)
    _turf(bins, x0, 5.3, x1, y1, TURF_MEADOW)
    segs: list[tuple[float, float, float, float, float, float]] = []
    _path_grid(segs, x0, y0, x1, y1, step=6.5)
    _flush_paths(bins, segs, "garfield_paths")
    _perimeter_trees(bins, x0, y0, x1, y1, spacing=1.7)
    _glass_conservatory(bins, -190.0, 12.5, 1.2, 0.6)
    _gold_dome_fieldhouse(bins, -190.0, -4.0)
    _grove(bins, -185.0, 8.0, 2.5, 10, ornamental=True)
    _grove(bins, -194.0, -10.0, 2.8, 12)
    _diamond(bins, -185.0, -10.0)
    _court(bins, -195.0, 2.0)
    _path_lamps(bins, x0, y0, x1, y1, spacing=3.4)


def _build_douglas(bins: _SectorBins) -> None:
    x0, y0, x1, y1 = DOUGLAS_PARK_VOID
    _turf(bins, x0, y0, x1, y1, TURF_MEADOW)
    segs: list[tuple[float, float, float, float, float, float]] = []
    _path_grid(segs, x0, y0, x1, y1, step=6.5)
    _flush_paths(bins, segs, "douglas_paths")
    _perimeter_trees(bins, x0, y0, x1, y1, spacing=1.7)
    # Classical limestone Flower Hall / Refectory.
    parent = bins.day_np(-158.0, -79.0)
    hall = chamfer_box_instance(parent, 1.15, 0.55, 0.22, chamfer=0.12)
    hall.setPos(-158.0, -79.0, 0.14)
    hall.setMaterial(rgba_material(LIMESTONE, shininess=16.0), 1)
    register_building(-158.0, -79.0, 0.55, 0.28, 0.0)
    for i, (dx, dy) in enumerate(((-6, -6), (5, -8), (-4, 6), (6, 5))):
        _diamond(bins, -158.0 + dx, -79.0 + dy, 0.75, 15.0 * i)
    _grove(bins, -162.0, -70.0, 2.8, 12)
    _grove(bins, -152.0, -88.0, 2.5, 10)
    _path_lamps(bins, x0, y0, x1, y1, spacing=3.5)


def _build_washington(bins: _SectorBins) -> None:
    x0, y0, x1, y1 = WASHINGTON_PARK_VOID
    _turf(bins, x0, y0, x1, y1, TURF_FAIRWAY)
    segs: list[tuple[float, float, float, float, float, float]] = []
    _path_grid(segs, x0, y0, x1, y1, step=9.0)
    _flush_paths(bins, segs, "washington_paths")
    _perimeter_trees(bins, x0, y0, x1, y1, spacing=1.8)
    # DuSable Museum.
    _museum_palace(bins, 28.0, -285.0, 1.4, 0.85)
    _grove(bins, 22.0, -290.0, 4.0, 18)
    _grove(bins, 35.0, -300.0, 3.5, 14)
    for i in range(4):
        _diamond(bins, 24.0 + i * 4.0, -305.0, 0.9, 10.0 * i)
    _court(bins, 32.0, -275.0, 0.7, 1.1)
    _path_lamps(bins, x0, y0, x1, y1, spacing=4.2)


def _build_jackson(bins: _SectorBins) -> None:
    x0, y0, x1, y1 = JACKSON_PARK_VOID
    y = y0
    flip = False
    while y < y1 - 0.1:
        yb = min(y + UNITS_PER_MILE * 0.5, y1)
        _turf(bins, x0, y, x1, yb, TURF_MEADOW if not flip else TURF_FAIRWAY)
        flip = not flip
        y = yb
    segs: list[tuple[float, float, float, float, float, float]] = []
    _path_grid(segs, x0, y0, x1, y1, step=10.0)
    # Cornell Drive winding approx.
    cornell = (
        (48.0, -350.0),
        (55.0, -340.0),
        (63.3, -320.0),
        (70.0, -310.0),
        (78.0, -300.0),
    )
    for i in range(len(cornell) - 1):
        _path_seg(segs, *cornell[i], *cornell[i + 1], 0.32)
        _tree_line(bins, *cornell[i], *cornell[i + 1], 2.0, ornamental=True)
    _flush_paths(bins, segs, "jackson_paths")
    _perimeter_trees(bins, x0, y0, x1, y1, spacing=2.0)
    _museum_palace(bins, 63.3, -300.0, 2.2, 1.1)  # MSI
    # Garden of the Phoenix pavilion.
    _brick_pavilion(bins, 72.0, -330.0, 0.7, 0.5)
    parent = bins.day_np(72.0, -330.0)
    roof = NodePath(make_pyramid(0.85, 0.65, 0.22))
    roof.reparentTo(parent)
    roof.setPos(72.0, -330.0, 0.38)
    roof.setMaterial(rgba_material((0.55, 0.22, 0.18, 1.0), shininess=20.0), 1)
    _grove(bins, 55.0, -340.0, 4.0, 16)
    _grove(bins, 75.0, -315.0, 3.5, 14)
    _diamond(bins, 50.0, -345.0)
    _diamond(bins, 68.0, -340.0, heading=30.0)
    _path_lamps(bins, x0, y0, x1, y1, spacing=4.5)


def _build_marquette(bins: _SectorBins) -> None:
    x0, y0, x1, y1 = MARQUETTE_PARK_VOID
    _turf(bins, x0, y0, x1, y1, TURF_FAIRWAY)
    segs: list[tuple[float, float, float, float, float, float]] = []
    _path_grid(segs, x0, y0, x1, y1, step=8.0, diagonal=False)
    # Fairway ribbons.
    for i in range(5):
        fx0 = x0 + 3.0 + i * 7.5
        _path_seg(segs, fx0, y0 + 1.5, fx0 + 4.0, y1 - 1.5, 0.55)
    _flush_paths(bins, segs, "marquette_paths")
    _perimeter_trees(bins, x0, y0, x1, y1, spacing=1.9)
    for i in range(6):
        _grove(
            bins,
            x0 + 5.0 + i * 6.5,
            y0 + 4.0 + (i % 2) * 8.0,
            2.2,
            8,
        )
    _path_lamps(bins, x0, y0, x1, y1, spacing=4.0)


MAJOR_BUILDERS = {
    "grant": _build_grant,
    "lincoln": _build_lincoln,
    "humboldt": _build_humboldt,
    "garfield": _build_garfield,
    "douglas": _build_douglas,
    "washington": _build_washington,
    "jackson": _build_jackson,
    "marquette": _build_marquette,
}


# ---------------------------------------------------------------------------
# Boulevards & pocket parks
# ---------------------------------------------------------------------------
def _build_boulevards(bins: _SectorBins) -> None:
    median_mat = rgba_material(TURF_EMERALD)
    for key, axis, coord, t0, t1, spacing in BOULEVARDS:
        if axis == "y":
            # E–W boulevard — break the median at every N–S cross street.
            y = coord
            for xa, xb in _split_spans(t0, t1, ARTERIAL_X, INTERSECT_GAP):
                cx = 0.5 * (xa + xb)
                pad = box_instance(
                    bins.day_np(cx, y),
                    abs(xb - xa),
                    MEDIAN_WIDTH,
                    0.02,
                    top=True,
                    bottom=False,
                )
                pad.setPos(cx, y, MEDIAN_Z)
                pad.setMaterial(median_mat, 1)
                _tree_line(
                    bins,
                    xa,
                    y + 0.12,
                    xb,
                    y + 0.12,
                    spacing,
                    ornamental=False,
                    boulevard=True,
                )
                _tree_line(
                    bins,
                    xa,
                    y - 0.12,
                    xb,
                    y - 0.12,
                    spacing,
                    ornamental=False,
                    phase=0.5,
                    boulevard=True,
                )
                n = max(1, int(abs(xb - xa) / 3.4))
                for i in range(n + 1):
                    tx = xa + (xb - xa) * (i / n)
                    _place_lamp(bins, tx, y, boulevard=True)
        else:
            # N–S boulevard — break at every E–W cross street.
            x = coord
            for ya, yb in _split_spans(t0, t1, ARTERIAL_Y, INTERSECT_GAP):
                cy = 0.5 * (ya + yb)
                pad = box_instance(
                    bins.day_np(x, cy),
                    MEDIAN_WIDTH,
                    abs(yb - ya),
                    0.02,
                    top=True,
                    bottom=False,
                )
                pad.setPos(x, cy, MEDIAN_Z)
                pad.setMaterial(median_mat, 1)
                _tree_line(
                    bins, x + 0.12, ya, x + 0.12, yb, spacing, boulevard=True
                )
                _tree_line(
                    bins,
                    x - 0.12,
                    ya,
                    x - 0.12,
                    yb,
                    spacing,
                    phase=0.5,
                    boulevard=True,
                )
                n = max(1, int(abs(yb - ya) / 3.4))
                for i in range(n + 1):
                    ty = ya + (yb - ya) * (i / n)
                    _place_lamp(bins, x, ty, boulevard=True)
        del key


def _build_pocket_parks(bins: _SectorBins) -> None:
    pw, pd = pocket_park_size()
    half_w, half_d = pw * 0.5, pd * 0.5
    turf = rgba_material(TURF_EMERALD)
    path_mat = rgba_material(PATH_RGBA)
    for cx, cy, name in POCKET_PARKS:
        # Guard: never stamp a pocket whose centre still sits on a spine.
        if _on_road(cx, cy, gap=POCKET_INSET):
            continue
        parent = bins.day_np(cx, cy)
        pad = box_instance(parent, pw, pd, 0.05, top=True, bottom=False)
        pad.setPos(cx, cy, TURF_Z)
        pad.setMaterial(turf, 1)
        # Diagonal cross-paths.
        segs = [
            (
                cx - half_w + 0.12,
                cy - half_d + 0.12,
                cx + half_w - 0.12,
                cy + half_d - 0.12,
                0.1,
                PATH_Z,
            ),
            (
                cx - half_w + 0.12,
                cy + half_d - 0.12,
                cx + half_w - 0.12,
                cy - half_d + 0.12,
                0.1,
                PATH_Z,
            ),
        ]
        node = parent.attachNewNode(
            make_flat_deck_batch(segs, 0.02, name=f"{name}_paths", top_only=True)
        )
        node.setMaterial(path_mat, 1)
        # Playground pad.
        play = box_instance(parent, 0.5, 0.35, 0.018, top=True, bottom=False)
        play.setPos(cx + half_w * 0.25, cy - half_d * 0.15, FIELD_Z)
        play.setMaterial(rgba_material((0.55, 0.45, 0.28, 1.0)), 1)
        # Perimeter trees (inset from the already-inset edge).
        for ox, oy in (
            (-half_w + 0.28, -half_d + 0.22),
            (half_w - 0.28, -half_d + 0.22),
            (-half_w + 0.28, half_d - 0.22),
            (half_w - 0.28, half_d - 0.22),
            (0.0, -half_d + 0.2),
            (0.0, half_d - 0.2),
        ):
            _place_tree(bins, cx + ox, cy + oy, ornamental=True, collider=True)
        _place_lamp(bins, cx - half_w * 0.35, cy)
        _place_lamp(bins, cx + half_w * 0.35, cy)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def build_chicago_parks(parent: NodePath) -> dict[str, Any]:
    """Build civic parks / boulevards / pocket parks. Returns LOD + night handles."""
    root = parent.attachNewNode("chicago_parks")
    night = root.attachNewNode("park_night_glow_node")
    night.setLightOff(1)
    night.hide()
    bins = _SectorBins(root, night)

    for park in MAJOR_PARKS:
        MAJOR_BUILDERS[park.key](bins)
    _build_boulevards(bins)
    _build_pocket_parks(bins)

    day_tiles: list[tuple[float, float, NodePath]] = []
    bulb_tiles: list[tuple[float, float, NodePath]] = []
    pool_tiles: list[tuple[float, float, NodePath]] = []

    for (sx, sy), node in bins.day.items():
        if node.getNumChildren() == 0:
            node.removeNode()
            continue
        node.flattenStrong()
        cx = (sx + 0.5) * SECTOR_SIZE
        cy = (sy + 0.5) * SECTOR_SIZE
        day_tiles.append((cx, cy, node))

    for (sx, sy), bulbs in bins.bulbs.items():
        pools = bins.pools[(sx, sy)]
        if bulbs.getNumChildren() == 0:
            bulbs.removeNode()
            pools.removeNode()
            continue
        bulbs.flattenStrong()
        pools.flattenStrong()
        # Additive pools.
        pools.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd))
        pools.setTransparency(TransparencyAttrib.MAlpha)
        cx = (sx + 0.5) * SECTOR_SIZE
        cy = (sy + 0.5) * SECTOR_SIZE
        bulbs.hide()
        pools.hide()
        bulb_tiles.append((cx, cy, bulbs))
        pool_tiles.append((cx, cy, pools))

    print(
        "[parks] %d day sectors, %d night sectors, %d pocket parks"
        % (len(day_tiles), len(bulb_tiles), len(POCKET_PARKS))
    )
    return {
        "root": root,
        "night_glow": night,
        "tiles": day_tiles,
        "bulb_tiles": bulb_tiles,
        "pool_tiles": pool_tiles,
        "count": len(day_tiles),
    }
