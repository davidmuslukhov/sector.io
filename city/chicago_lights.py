"""Chicago street lights — emissive bulbs + additive ground-glow pools (2×).

Poles / bulbs / pools are batched per 1-mile sector with flattenStrong. Night
illumination is fake (no PointLights): glowing fixtures + additive asphalt pools.
"""

from __future__ import annotations

import math
from typing import Any

from panda3d.core import (
    ColorBlendAttrib,
    Material,
    NodePath,
    TransparencyAttrib,
)

from city.chicago_housing import (
    HOUSING_BUILD_X0,
    HOUSING_BUILD_X1,
    HOUSING_BUILD_Y0,
    HOUSING_BUILD_Y1,
)
from city.geo import AIRPORT_VOIDS
from city.materials import rgba_material
from city.mesh import (
    arterial_junctions,
    box_instance,
    make_glow_disk,
    z_cylinder_instance,
)

# Match housing startup envelope (+ pad) so lights don't walk the whole metro.
_LIGHTS_PAD = 40.0
_LIGHTS_X0 = HOUSING_BUILD_X0 - _LIGHTS_PAD
_LIGHTS_X1 = HOUSING_BUILD_X1 + _LIGHTS_PAD
_LIGHTS_Y0 = HOUSING_BUILD_Y0 - _LIGHTS_PAD
_LIGHTS_Y1 = HOUSING_BUILD_Y1 + _LIGHTS_PAD


def _in_airport_void(x: float, y: float) -> bool:
    """Skip street-light samples that fall inside Midway / O'Hare airfields."""
    for x0, y0, x1, y1 in AIRPORT_VOIDS:
        if x0 < x < x1 and y0 < y < y1:
            return True
    return False


def _in_lights_box(x: float, y: float) -> bool:
    return _LIGHTS_X0 <= x <= _LIGHTS_X1 and _LIGHTS_Y0 <= y <= _LIGHTS_Y1


def _polyline_hits_lights_box(pts: list) -> bool:
    """True if any vertex or the bbox overlaps the startup lights envelope."""
    if not pts:
        return False
    min_x = min_y = 1e18
    max_x = max_y = -1e18
    for p in pts:
        x, y = float(p[0]), float(p[1])
        if _in_lights_box(x, y):
            return True
        if x < min_x:
            min_x = x
        if y < min_y:
            min_y = y
        if x > max_x:
            max_x = x
        if y > max_y:
            max_y = y
    # Segment may cross the box without a vertex inside.
    return not (
        max_x < _LIGHTS_X0
        or min_x > _LIGHTS_X1
        or max_y < _LIGHTS_Y0
        or min_y > _LIGHTS_Y1
    )

UNITS_PER_MILE = 42.2
# 2-mile tiles (same as minor roads) — fewer LOD nodes, bigger flatten batches.
SECTOR_SIZE = UNITS_PER_MILE * 2.0
BLOCK_100 = 5.275

# Downtown Loop — cool LED white fixtures (full downtown footprint).
LOOP_X0, LOOP_X1 = -42.2, 16.0
LOOP_Y0, LOOP_Y1 = -63.3, 42.2

POLE_RADIUS = 0.02
CORNER_EXCLUDE = 0.8

# Spacing / offsets (thinned vs literal Chicago density for FPS)
ARTERIAL_SPACING = 3.5  # ~every 1.3 half-blocks
ARTERIAL_OFFSET = 0.32
COLLECTOR_OFFSET = 0.22
EXPRESSWAY_SPACING = 5.5
MINOR_SPACING = BLOCK_100 * 2.0  # one pole every two blocks
MINOR_OFFSET = 0.16

# Heights / arms
COBRA_H = 0.62
COBRA_ARM = 0.18
MAST_H = 0.85
MAST_ARM = 0.22
RES_H = 0.45
RES_ARM = 0.10

# Road decks use top_only: surface = z_offset - thickness/2 + 0.002 (see mesh).
_ROAD_THICKNESS = 0.1
_POOL_LIFT = 0.004  # just above asphalt — avoids z-fight without floating
POOL_R_MAJOR = 0.48
POOL_R_MINOR = 0.28
BULB_W, BULB_D, BULB_H = 0.055, 0.035, 0.028

# Warm high-pressure sodium / soft warm-white (no blue LED cast).
AMBER = (1.0, 0.55, 0.14, 1.0)
COOL = (1.0, 0.82, 0.52, 1.0)  # warm white for Loop / expressways
POLE_COLOR = (0.08, 0.12, 0.09, 1.0)  # dark hunter green / black
BASE_COLOR = (0.42, 0.40, 0.36, 1.0)  # concrete footing
UNLIT_BULB = (0.4, 0.4, 0.42, 1.0)
POOL_ALPHA = 0.55


def _deck_top(z_offset: float = 0.0) -> float:
    """Match make_flat_deck_batch(top_only=True) road surface."""
    return float(z_offset) - _ROAD_THICKNESS * 0.5 + 0.002

LIGHTS_HIDE_DIST = 150.0
LIGHTS_VIEW_FACTOR = 0.22
LIGHTS_VIEW_MIN = 40.0
LIGHTS_MAX_TILES = 5  # poles / bulbs
LIGHTS_MAX_POOL_TILES = 3  # additive pools are the expensive draw
WARMUP_SECONDS = 1.2

_TEMPLATES: dict[str, NodePath] = {}
_POOL_TEMPLATES: dict[str, NodePath] = {}
_BULB_TEMPLATES: dict[str, NodePath] = {}
_MAT_CACHE: dict[tuple, Material] = {}


def _emissive_material(rgb: tuple[float, float, float], *, lit: bool) -> Material:
    key = (round(rgb[0], 3), round(rgb[1], 3), round(rgb[2], 3), lit)
    cached = _MAT_CACHE.get(key)
    if cached is not None:
        return cached
    mat = Material()
    if lit:
        # Bias emission toward amber so lenses read warm even under cool moonlight.
        warm = (min(1.0, rgb[0] * 1.55), rgb[1] * 1.25, rgb[2] * 0.85)
        mat.setAmbient((*rgb, 1))
        mat.setDiffuse((*rgb, 1))
        mat.setEmission((*warm, 1))
        mat.setShininess(28)
    else:
        mat.setAmbient((0.25, 0.25, 0.26, 1))
        mat.setDiffuse(UNLIT_BULB)
        mat.setEmission((0, 0, 0, 1))
        mat.setShininess(8)
    _MAT_CACHE[key] = mat
    return mat


def _in_loop(x: float, y: float) -> bool:
    return LOOP_X0 <= x <= LOOP_X1 and LOOP_Y0 <= y <= LOOP_Y1


def _cool_light(layer: str, x: float, y: float) -> bool:
    return layer == "expressway" or _in_loop(x, y)


def _sector_key(x: float, y: float) -> tuple[int, int]:
    return (int(math.floor(x / SECTOR_SIZE)), int(math.floor(y / SECTOR_SIZE)))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
def _ensure_templates() -> None:
    if _TEMPLATES:
        return
    pole_mat = rgba_material(POLE_COLOR, shininess=12.0)
    _TEMPLATES["cobra"] = _make_cobra_pole(pole_mat, COBRA_H, COBRA_ARM, single=True)
    _TEMPLATES["mast"] = _make_cobra_pole(pole_mat, MAST_H, MAST_ARM, single=False)
    _TEMPLATES["res"] = _make_cobra_pole(pole_mat, RES_H, RES_ARM, single=True)

    for name, rgb in (("amber", AMBER[:3]), ("cool", COOL[:3])):
        bulb = NodePath(f"bulb_{name}")
        lens = box_instance(bulb, BULB_W, BULB_D, BULB_H)
        lens.setPos(0.0, 0.0, 0.0)
        lens.setMaterial(_emissive_material(rgb, lit=True), 1)
        bulb.flattenStrong()
        bulb.setLightOff(1)
        _BULB_TEMPLATES[name] = bulb

    for name, rgb, radius in (
        ("amber_major", AMBER, POOL_R_MAJOR),
        ("cool_major", COOL, POOL_R_MAJOR),
        ("amber_minor", AMBER, POOL_R_MINOR),
        ("cool_minor", COOL, POOL_R_MINOR),
    ):
        r, g, b, _a = rgb
        pool = NodePath(make_glow_disk(radius, (r, g, b, POOL_ALPHA), segments=8))
        pool.setLightOff(1)
        _POOL_TEMPLATES[name] = pool


def _make_cobra_pole(
    pole_mat: Material,
    height: float,
    arm_len: float,
    *,
    single: bool,
) -> NodePath:
    """Vertical shaft + davit arm(s). Origin at footing; local +Y toward centreline."""
    root = NodePath("pole")
    base_mat = rgba_material(BASE_COLOR, shininess=4.0)
    # Concrete footing so the pole reads planted on the deck, not hovering.
    footing = z_cylinder_instance(root, POLE_RADIUS * 2.4, 0.025, segments=6)
    footing.setPos(0.0, 0.0, 0.012)
    footing.setMaterial(base_mat, 1)
    shaft = z_cylinder_instance(root, POLE_RADIUS, height, segments=6)
    shaft.setPos(0.0, 0.0, height * 0.5)
    shaft.setMaterial(pole_mat, 1)
    arms = (0.0,) if single else (-1.0, 1.0)
    for sign in arms:
        # Arm extends along ±Y over the curb lane.
        arm = box_instance(root, POLE_RADIUS * 1.6, arm_len, POLE_RADIUS * 1.4)
        arm.setPos(0.0, sign * arm_len * 0.5, height - 0.02)
        arm.setMaterial(pole_mat, 1)
        # Small fixture housing at tip.
        head = box_instance(root, 0.05, 0.06, 0.035)
        head.setPos(0.0, sign * arm_len, height - 0.04)
        head.setMaterial(pole_mat, 1)
    root.flattenStrong()
    return root


# ---------------------------------------------------------------------------
# Junction keepout
# ---------------------------------------------------------------------------
class _JunctionIndex:
    __slots__ = ("cell", "bins")

    def __init__(self, points: list[tuple[float, float]], cell: float = 4.0) -> None:
        self.cell = cell
        self.bins: dict[tuple[int, int], list[tuple[float, float]]] = {}
        for x, y in points:
            tx = int(math.floor(x / cell))
            ty = int(math.floor(y / cell))
            self.bins.setdefault((tx, ty), []).append((x, y))

    def near(self, x: float, y: float, radius: float) -> bool:
        r2 = radius * radius
        tx = int(math.floor(x / self.cell))
        ty = int(math.floor(y / self.cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for jx, jy in self.bins.get((tx + dx, ty + dy), ()):
                    if (x - jx) * (x - jx) + (y - jy) * (y - jy) <= r2:
                        return True
        return False


def _junction_points(arterials: list[dict[str, Any]]) -> list[tuple[float, float]]:
    # Minors + far suburbs make arterial_junctions take ~60s; only index the
    # routes we actually light inside the startup envelope.
    subset = [
        a
        for a in arterials
        if str(a.get("layer", "arterial")) in ("arterial", "collector", "expressway")
        and _polyline_hits_lights_box(list(a.get("points") or ()))
    ]
    raw = arterial_junctions(subset, merge=1.25)
    return [(float(j["x"]), float(j["y"])) for j in raw]


# ---------------------------------------------------------------------------
# Placement helpers
# ---------------------------------------------------------------------------
def _iter_polyline_samples(
    points: list[tuple[float, float]],
    spacing: float,
    *,
    phase: float = 0.0,
) -> list[tuple[float, float, float, float]]:
    """Yield (x, y, dx, dy) samples. ``dx,dy`` is unit tangent along the route."""
    if len(points) < 2 or spacing <= 1e-6:
        return []
    out: list[tuple[float, float, float, float]] = []
    dist_to_next = phase
    for i in range(len(points) - 1):
        x0, y0 = float(points[i][0]), float(points[i][1])
        x1, y1 = float(points[i + 1][0]), float(points[i + 1][1])
        seg_dx = x1 - x0
        seg_dy = y1 - y0
        seg_len = math.hypot(seg_dx, seg_dy)
        if seg_len < 1e-6:
            continue
        ux, uy = seg_dx / seg_len, seg_dy / seg_len
        cursor = 0.0
        while cursor + dist_to_next <= seg_len + 1e-9:
            t = cursor + dist_to_next
            out.append((x0 + ux * t, y0 + uy * t, ux, uy))
            cursor += dist_to_next
            dist_to_next = spacing
        dist_to_next = cursor + dist_to_next - seg_len
    return out


def _instance_at(
    template: NodePath,
    parent: NodePath,
    x: float,
    y: float,
    z: float,
    heading: float = 0.0,
) -> NodePath:
    """Place a hardware instance of ``template`` under ``parent``."""
    node = parent.attachNewNode("i")
    node.setPos(x, y, z)
    if heading:
        node.setH(heading)
    template.instanceTo(node)
    return node


def _place_fixture(
    *,
    poles: NodePath,
    bulbs: NodePath,
    pools: NodePath,
    flickers: list[NodePath],
    style: str,
    cool: bool,
    major_pool: bool,
    x: float,
    y: float,
    heading: float,
    arm_sign: float,
    arm_len: float,
    pole_h: float,
    want_flicker: bool,
    base_z: float,
) -> None:
    _ensure_templates()
    _instance_at(_TEMPLATES[style], poles, x, y, base_z, heading)

    color_key = "cool" if cool else "amber"
    # World offset: local +Y after heading → (-sin H, cos H) toward centreline.
    rad = math.radians(heading)
    inward_x = -math.sin(rad)
    inward_y = math.cos(rad)
    tip_x = x + inward_x * arm_sign * arm_len
    tip_y = y + inward_y * arm_sign * arm_len
    tip_z = base_z + pole_h - 0.05

    bulb = _instance_at(_BULB_TEMPLATES[color_key], bulbs, tip_x, tip_y, tip_z, heading)
    if want_flicker:
        flickers.append(bulb)

    pool_key = f"{color_key}_{'major' if major_pool else 'minor'}"
    # Glow sits on the asphalt under the fixture, not at a fixed world Z.
    _instance_at(
        _POOL_TEMPLATES[pool_key],
        pools,
        tip_x,
        tip_y,
        base_z + _POOL_LIFT,
    )


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def build_chicago_lights(
    parent: NodePath,
    arterials: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build batched street lights. Returns controllers + LOD tile lists."""
    _ensure_templates()
    junctions = _JunctionIndex(_junction_points(arterials))

    root = parent.attachNewNode("chicago_lights")
    poles_root = root.attachNewNode("poles")
    bulbs_root = root.attachNewNode("lamp_bulbs")
    pools_root = root.attachNewNode("light_pools")
    flicker_root = root.attachNewNode("flicker_bulbs")

    bulbs_root.setLightOff(1)
    pools_root.setLightOff(1)
    pools_root.setDepthWrite(False)
    pools_root.setDepthTest(True)  # occlude behind curbs / houses; sit on asphalt
    pools_root.setTransparency(TransparencyAttrib.MAlpha)
    pools_root.setAttrib(
        ColorBlendAttrib.make(
            ColorBlendAttrib.MAdd,
            ColorBlendAttrib.OIncomingAlpha,
            ColorBlendAttrib.OOne,
        )
    )
    pools_root.setBin("transparent", 20)
    flicker_root.setLightOff(1)

    # sector → (poles, bulbs, pools, flicker_list)
    sectors: dict[tuple[int, int], tuple[NodePath, NodePath, NodePath, list]] = {}

    def sector_bins(sx: int, sy: int):
        key = (sx, sy)
        got = sectors.get(key)
        if got is not None:
            return got
        poles = poles_root.attachNewNode(f"poles_{sx}_{sy}")
        bulbs = bulbs_root.attachNewNode(f"bulbs_{sx}_{sy}")
        pools = pools_root.attachNewNode(f"pools_{sx}_{sy}")
        flick: list[NodePath] = []
        sectors[key] = (poles, bulbs, pools, flick)
        return sectors[key]

    total = 0

    for arterial in arterials:
        layer = str(arterial.get("layer", "arterial"))
        pts = list(arterial.get("points") or ())
        if len(pts) < 2:
            continue
        if not _polyline_hits_lights_box(pts):
            continue
        width = float(arterial.get("width", 0.55))
        name = str(arterial.get("name", ""))
        z_off = float(arterial.get("z_offset", 0.0))
        base_z = _deck_top(z_off)

        if layer == "expressway":
            samples = _iter_polyline_samples(pts, EXPRESSWAY_SPACING, phase=1.0)
            for i, (x, y, ux, uy) in enumerate(samples):
                if not _in_lights_box(x, y):
                    continue
                if _in_airport_void(x, y):
                    continue
                if junctions.near(x, y, CORNER_EXCLUDE):
                    continue
                # Align local ±Y with left normal (−uy, ux) so twin arms span both decks.
                arm_heading = math.degrees(math.atan2(uy, ux))
                sx, sy = _sector_key(x, y)
                poles, bulbs, pools, flick = sector_bins(sx, sy)
                _instance_at(_TEMPLATES["mast"], poles, x, y, base_z, arm_heading)
                rad = math.radians(arm_heading)
                ix, iy = -math.sin(rad), math.cos(rad)
                for sign in (-1.0, 1.0):
                    tip_x = x + ix * sign * MAST_ARM
                    tip_y = y + iy * sign * MAST_ARM
                    _instance_at(
                        _BULB_TEMPLATES["cool"],
                        bulbs,
                        tip_x,
                        tip_y,
                        base_z + MAST_H - 0.05,
                    )
                    _instance_at(
                        _POOL_TEMPLATES["cool_major"],
                        pools,
                        tip_x,
                        tip_y,
                        base_z + _POOL_LIFT,
                    )
                total += 1
            continue

        if layer == "minor":
            # Startup skip: minor-grid poles dominate build time (~tens of
            # seconds) while arterial / expressway fixtures carry the night look.
            continue

        if layer not in ("arterial", "collector"):
            continue

        offset = COLLECTOR_OFFSET if abs(width - 0.35) < 0.05 else ARTERIAL_OFFSET
        samples = _iter_polyline_samples(pts, ARTERIAL_SPACING, phase=0.4)
        for i, (x, y, ux, uy) in enumerate(samples):
            if not _in_lights_box(x, y):
                continue
            if _in_airport_void(x, y):
                continue
            if junctions.near(x, y, CORNER_EXCLUDE):
                continue
            # Zig-zag: even → left, odd → right.
            side = 1.0 if (i % 2 == 0) else -1.0
            nx, ny = -uy, ux
            px = x + nx * side * offset
            py = y + ny * side * offset
            if _in_airport_void(px, py):
                continue
            heading = math.degrees(math.atan2(-side * uy, -side * ux))
            sx, sy = _sector_key(px, py)
            poles, bulbs, pools, flick = sector_bins(sx, sy)
            cool = _cool_light(layer, px, py)
            _place_fixture(
                poles=poles,
                bulbs=bulbs,
                pools=pools,
                flickers=flick,
                style="cobra",
                cool=cool,
                major_pool=True,
                x=px,
                y=py,
                heading=heading,
                arm_sign=1.0,
                arm_len=COBRA_ARM,
                pole_h=COBRA_H,
                want_flicker=False,
                base_z=base_z,
            )
            total += 1

    pole_tiles: list[tuple[float, float, NodePath]] = []
    bulb_tiles: list[tuple[float, float, NodePath]] = []
    pool_tiles: list[tuple[float, float, NodePath]] = []
    all_flickers: list[NodePath] = []

    for (sx, sy), (poles, bulbs, pools, flick) in sectors.items():
        if poles.getNumChildren() == 0:
            poles.removeNode()
            bulbs.removeNode()
            pools.removeNode()
            continue
        # Bake instances → few GeomNodes (same FPS issue as housing).
        for fnode in flick:
            if not fnode.isEmpty():
                fnode.reparentTo(flicker_root)
                all_flickers.append(fnode)
        if poles.getNumChildren():
            poles.flattenStrong()
        if bulbs.getNumChildren():
            bulbs.flattenStrong()
        if pools.getNumChildren():
            pools.flattenStrong()
        cx = (sx + 0.5) * SECTOR_SIZE
        cy = (sy + 0.5) * SECTOR_SIZE
        poles.hide()
        bulbs.hide()
        pools.hide()
        pole_tiles.append((cx, cy, poles))
        bulb_tiles.append((cx, cy, bulbs))
        pool_tiles.append((cx, cy, pools))

    # Start unlit (day); controller turns them on.
    bulbs_root.hide()
    pools_root.hide()
    flicker_root.hide()

    print(
        "[lights] %d fixtures → %d mile-sectors (poles/bulbs/pools)"
        % (total, len(pole_tiles))
    )
    return {
        "root": root,
        "poles_root": poles_root,
        "bulbs_root": bulbs_root,
        "pools_root": pools_root,
        "flicker_root": flicker_root,
        "pole_tiles": pole_tiles,
        "bulb_tiles": bulb_tiles,
        "pool_tiles": pool_tiles,
        "flickers": all_flickers,
        "count": total,
    }
