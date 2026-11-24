"""Chicago inner-city row houses, Two-Flats, Greystones, and bungalows (2×).

Fills residential blocks on the BLOCK_100 (5.275) minor grid with authentic
25×125 ft lots, rear alleys, and low-poly archetypes. Geometry is grouped into
1-mile sectors, flattenStrong'd, and LOD-culled for high FPS.
"""

from __future__ import annotations

import math
from typing import Any

from panda3d.core import NodePath

from city.materials import rgba_material, roof_material, sidewalk_material
from city.mesh import box_instance, make_gable_roof, make_pyramid
from city.plan import CityPlan, _dist2_point_segment

# ---------------------------------------------------------------------------
# Scale / layout (2× Chicago)
# ---------------------------------------------------------------------------
UNITS_PER_MILE = 42.2
BLOCK_100 = 5.275  # 100 street numbers = 1/8 mile; also long side of a block
BLOCK_SHORT = BLOCK_100 * 0.5  # 330 ft half-block depth between street and alley mid

RES_X0, RES_X1 = -379.8, 5.3  # Harlem → Michigan
RES_Y0, RES_Y1 = -501.1, 400.9  # 95th → Howard

# Spec Loop core reserved for commercial / high-rise (tighter than calibrate box).
LOOP_X0, LOOP_X1 = -35.0, 16.0
LOOP_Y0, LOOP_Y1 = -42.2, 32.0

INNER_X0, INNER_X1 = -211.0, 5.3
INNER_Y0, INNER_Y1 = -290.1, 253.2
BUNGALOW_X0, BUNGALOW_X1 = -379.8, -168.8

OHARE = (-548.6, 275.0, -464.2, 358.7)
MIDWAY = (-253.2, -332.3, -232.1, -290.1)
VOIDS = (OHARE, MIDWAY)

LOT_WIDTH = 0.20
HOUSE_GAP = 0.04  # gangway between brick walls
SETBACK = 0.12
STOOP_DEPTH = 0.08
ALLEY_WIDTH = 0.14

CLEAR_EXPRESSWAY = 0.55
CLEAR_ARTERIAL = 0.40
CLEAR_COLLECTOR = 0.40
CLEAR_MINOR = 0.25

SECTOR_SIZE = UNITS_PER_MILE  # 1×1 mile sectors
# Tight LOD — few mile-sectors on screen; each is one flattened GeomNode.
HOUSING_HIDE_DIST = 200.0
HOUSING_VIEW_FACTOR = 0.28
HOUSING_VIEW_MIN = 45.0
HOUSING_MAX_TILES = 9
# Kept for app import compat; detail is baked into the sector mesh now.
DETAIL_LOD_FAR = 120.0

# Bungalow-belt spines (Western / Kedzie / Pulaski / Cicero).
BUNGALOW_SPINES = (-126.6, -168.8, -211.0, -253.2)

# Facade / roof palettes
BRICK_RED = (0.45, 0.16, 0.13, 1.0)
BRICK_BUFF = (0.68, 0.58, 0.44, 1.0)
GREYSTONE = (0.62, 0.61, 0.58, 1.0)
TAPESTRY = (0.38, 0.18, 0.14, 1.0)
CLAPBOARD = (
    (0.82, 0.78, 0.68, 1.0),  # cream
    (0.55, 0.62, 0.48, 1.0),  # muted sage
    (0.45, 0.52, 0.62, 1.0),  # slate blue
    (0.58, 0.56, 0.54, 1.0),  # warm grey
)
ROOF_DARK = (0.18, 0.16, 0.14, 1.0)
ROOF_GREEN = (0.16, 0.22, 0.14, 1.0)
ROOF_BROWN = (0.28, 0.18, 0.12, 1.0)
WINDOW = (0.08, 0.09, 0.11, 1.0)
STOREFRONT_BRICK = (0.42, 0.18, 0.15, 1.0)
LIMESTONE = (0.72, 0.70, 0.64, 1.0)

_TEMPLATES: dict[str, NodePath] = {}
_TEMPLATE_POOL: NodePath | None = None


def _hash01(x: float, y: float, salt: float = 0.0) -> float:
    n = math.sin(x * 12.9898 + y * 78.233 + salt * 43.17) * 43758.5453
    return n - math.floor(n)


def _in_bbox(x: float, y: float, box: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


def _in_loop(x: float, y: float) -> bool:
    return LOOP_X0 <= x <= LOOP_X1 and LOOP_Y0 <= y <= LOOP_Y1


def _in_void(x: float, y: float) -> bool:
    return any(_in_bbox(x, y, v) for v in VOIDS)


def _in_inner_city(x: float, y: float) -> bool:
    return INNER_X0 <= x <= INNER_X1 and INNER_Y0 <= y <= INNER_Y1


def _in_bungalow_belt(x: float, y: float) -> bool:
    return BUNGALOW_X0 <= x <= BUNGALOW_X1 and RES_Y0 <= y <= RES_Y1


def _near_bungalow_spine(x: float, radius: float = 21.1) -> bool:
    return any(abs(x - spine) <= radius for spine in BUNGALOW_SPINES)


def _lot_fill(x: float, y: float) -> float:
    if _in_inner_city(x, y):
        return 0.85 + 0.10 * _hash01(x, y, 1.1)
    if _in_bungalow_belt(x, y):
        return 0.75 + 0.10 * _hash01(x, y, 1.2)
    return 0.70 + 0.10 * _hash01(x, y, 1.3)


def _pick_archetype(x: float, y: float) -> str:
    """Return two_flat | cottage | bungalow | storefront weights by district."""
    r = _hash01(x, y, 2.0)
    if _in_inner_city(x, y):
        # Inner city: Two-Flats / Greystones dominate.
        if r < 0.62:
            return "two_flat"
        if r < 0.88:
            return "cottage"
        return "bungalow"
    if _in_bungalow_belt(x, y) or _near_bungalow_spine(x):
        # Bungalow belt: bump brick bungalows, keep two-flats secondary.
        if r < 0.45:
            return "bungalow"
        if r < 0.78:
            return "two_flat"
        return "cottage"
    # Default mix from the prompt (50 / 30 / 20).
    if r < 0.50:
        return "two_flat"
    if r < 0.80:
        return "cottage"
    return "bungalow"


# ---------------------------------------------------------------------------
# Road clearance index
# ---------------------------------------------------------------------------
class _RoadIndex:
    """Spatial hash of road segments with layer-based clearance radii."""

    __slots__ = ("cell", "bins", "axis_x", "axis_y")

    def __init__(self, arterials: list[dict[str, Any]], cell: float = 8.0) -> None:
        self.cell = cell
        self.bins: dict[tuple[int, int], list[tuple[float, float, float, float, float]]] = {}
        # Axis-aligned centreline keys → max road class width (for corner stores).
        self.axis_x: dict[float, float] = {}
        self.axis_y: dict[float, float] = {}
        for arterial in arterials:
            layer = str(arterial.get("layer", "arterial"))
            width = float(arterial.get("width", 0.55))
            clear = {
                "expressway": CLEAR_EXPRESSWAY,
                "arterial": CLEAR_ARTERIAL,
                "collector": CLEAR_COLLECTOR,
                "minor": CLEAR_MINOR,
            }.get(layer, CLEAR_ARTERIAL)
            # Clearance is measured from centreline; keep at least half-width + margin.
            clear = max(clear, width * 0.5 + 0.08)
            pts = list(arterial.get("points") or ())
            if len(pts) < 2:
                continue
            for i in range(len(pts) - 1):
                x0, y0 = float(pts[i][0]), float(pts[i][1])
                x1, y1 = float(pts[i + 1][0]), float(pts[i + 1][1])
                self._add_seg(x0, y0, x1, y1, clear)
                if abs(x1 - x0) < 1e-6:
                    key = round(x0, 1)
                    self.axis_x[key] = max(self.axis_x.get(key, 0.0), width)
                elif abs(y1 - y0) < 1e-6:
                    key = round(y0, 1)
                    self.axis_y[key] = max(self.axis_y.get(key, 0.0), width)

    def _add_seg(self, x0: float, y0: float, x1: float, y1: float, clear: float) -> None:
        pad = clear + 0.5
        min_x, max_x = (x0, x1) if x0 <= x1 else (x1, x0)
        min_y, max_y = (y0, y1) if y0 <= y1 else (y1, y0)
        tx0 = int(math.floor((min_x - pad) / self.cell))
        tx1 = int(math.floor((max_x + pad) / self.cell))
        ty0 = int(math.floor((min_y - pad) / self.cell))
        ty1 = int(math.floor((max_y + pad) / self.cell))
        seg = (x0, y0, x1, y1, clear)
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                self.bins.setdefault((tx, ty), []).append(seg)

    def hits_point(self, x: float, y: float, *, radius: float = 0.0) -> bool:
        """Fast centreline keepout test (point + optional footprint radius)."""
        tx = int(math.floor(x / self.cell))
        ty = int(math.floor(y / self.cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for ax, ay, bx, by, clear in self.bins.get((tx + dx, ty + dy), ()):
                    lim = clear + radius
                    if _dist2_point_segment(x, y, ax, ay, bx, by) <= lim * lim:
                        return True
        return False

    def hits_footprint(
        self, min_x: float, min_y: float, max_x: float, max_y: float
    ) -> bool:
        cx = 0.5 * (min_x + max_x)
        cy = 0.5 * (min_y + max_y)
        radius = 0.5 * math.hypot(max_x - min_x, max_y - min_y)
        return self.hits_point(cx, cy, radius=radius)

    def _nearest_axis(
        self, axis: dict[float, float], v: float, *, tol: float = 0.2
    ) -> float | None:
        """YAML rounds centreline coords to 0.1 — match BLOCK_100 edges fuzzily."""
        key = round(v, 1)
        if key in axis:
            return axis[key]
        best_w: float | None = None
        best_d = tol
        for k, w in axis.items():
            d = abs(k - v)
            if d <= best_d:
                best_d = d
                best_w = w
        return best_w

    def road_width_at_x(self, x: float) -> float:
        return self._nearest_axis(self.axis_x, x) or 0.22

    def road_width_at_y(self, y: float) -> float:
        return self._nearest_axis(self.axis_y, y) or 0.22

    def has_street_x(self, x: float) -> bool:
        return self._nearest_axis(self.axis_x, x) is not None

    def has_street_y(self, y: float) -> bool:
        return self._nearest_axis(self.axis_y, y) is not None

    def is_wide_frontage(self, x: float | None = None, y: float | None = None) -> bool:
        """True if the axis is a collector (0.35) or arterial (0.55+)."""
        if x is not None:
            w = self._nearest_axis(self.axis_x, x)
            return w is not None and w >= 0.34
        if y is not None:
            w = self._nearest_axis(self.axis_y, y)
            return w is not None and w >= 0.34
        return False


# ---------------------------------------------------------------------------
# Archetype templates (body + detail children)
# ---------------------------------------------------------------------------
def _ensure_templates(pool: NodePath | None = None) -> None:
    """Build pre-coloured archetype templates once (shared via instanceTo)."""
    global _TEMPLATE_POOL
    if _TEMPLATES:
        if pool is not None and _TEMPLATE_POOL is not None and _TEMPLATE_POOL != pool:
            for node in _TEMPLATES.values():
                node.reparentTo(pool)
            _TEMPLATE_POOL = pool
        return
    if pool is None:
        pool = NodePath("housing_templates")
    _TEMPLATE_POOL = pool
    pool.hide()

    for stories in (2, 3):
        for name, color in (
            ("red", BRICK_RED),
            ("buff", BRICK_BUFF),
            ("grey", GREYSTONE),
        ):
            key = f"two_flat_{stories}_{name}"
            node = _make_two_flat(stories=stories, facade=color)
            node.reparentTo(pool)
            _TEMPLATES[key] = node

    for i, color in enumerate(CLAPBOARD):
        node = _make_cottage(facade=color)
        node.reparentTo(pool)
        _TEMPLATES[f"cottage_{i}"] = node
    node = _make_cottage(facade=BRICK_RED)
    node.reparentTo(pool)
    _TEMPLATES["cottage_brick"] = node

    for name, roof in (("green", ROOF_GREEN), ("brown", ROOF_BROWN)):
        node = _make_bungalow(roof=roof)
        node.reparentTo(pool)
        _TEMPLATES[f"bungalow_{name}"] = node

    node = _make_storefront()
    node.reparentTo(pool)
    _TEMPLATES["storefront"] = node


def _part(parent: NodePath, name: str) -> NodePath:
    return parent.attachNewNode(name)


def _box(
    parent: NodePath,
    sx: float,
    sy: float,
    sz: float,
    x: float,
    y: float,
    z: float,
    mat,
) -> NodePath:
    node = box_instance(parent, sx, sy, sz)
    node.setPos(x, y, z)
    node.setMaterial(mat, 1)
    return node


def _make_two_flat(
    *,
    stories: int,
    facade: tuple[float, float, float, float] = BRICK_RED,
) -> NodePath:
    """Chicago Two-Flat / Three-Flat with bay, parapet, and side-offset stoop."""
    root = NodePath(f"two_flat_{stories}")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d = 0.16, 0.52
    h = 0.24 if stories == 2 else 0.34
    facade_mat = rgba_material(facade)
    win = rgba_material(WINDOW)
    stoop = sidewalk_material()
    # Mass seated on Z=0 (foundation bottom).
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade_mat)
    # Raised front parapet / cornice lip.
    _box(body, w + 0.01, 0.03, 0.03, 0.0, -d * 0.5 + 0.015, h + 0.015, facade_mat)
    # Flat roof deck.
    _box(body, w * 0.96, d * 0.96, 0.012, 0.0, 0.0, h + 0.006, roof_material())
    # Front bay spanning floors.
    bay_d = 0.04
    _box(detail, w * 0.45, bay_d, h * 0.85, 0.0, -d * 0.5 - bay_d * 0.5, h * 0.5, facade_mat)
    _box(detail, w * 0.38, 0.01, h * 0.55, 0.0, -d * 0.5 - bay_d - 0.005, h * 0.48, win)
    # Side-offset porch + concrete steps.
    porch_x = w * 0.28
    _box(detail, 0.06, STOOP_DEPTH, 0.02, porch_x, -d * 0.5 - STOOP_DEPTH * 0.5, 0.02, stoop)
    _box(detail, 0.05, 0.04, 0.06, porch_x, -d * 0.5 - STOOP_DEPTH - 0.02, 0.03, stoop)
    # Dark window cutouts on front wall.
    for wz in (h * 0.28, h * 0.68) if stories == 2 else (h * 0.22, h * 0.50, h * 0.78):
        _box(detail, 0.03, 0.01, 0.04, -w * 0.28, -d * 0.5 - 0.005, wz, win)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_cottage(
    *,
    facade: tuple[float, float, float, float] = CLAPBOARD[0],
) -> NodePath:
    """Workers' cottage — raised 1.5-story with street-facing gable."""
    root = NodePath("cottage")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = 0.15, 0.42, 0.16
    facade_mat = rgba_material(facade)
    win = rgba_material(WINDOW)
    stoop = sidewalk_material()
    roof_mat = rgba_material(ROOF_DARK)
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade_mat)
    # Front-facing gable: ridge along depth (local Y) → rotate 90°.
    gable = body.attachNewNode(make_gable_roof(d + 0.02, w + 0.04, 0.07))
    gable.setH(90.0)
    gable.setPos(0.0, 0.0, h)
    gable.setMaterial(roof_mat, 1)
    # Elevated porch + stair.
    _box(detail, w * 0.7, STOOP_DEPTH, 0.025, 0.0, -d * 0.5 - STOOP_DEPTH * 0.5, 0.06, stoop)
    _box(detail, 0.05, 0.05, 0.07, 0.0, -d * 0.5 - STOOP_DEPTH - 0.025, 0.035, stoop)
    _box(detail, 0.04, 0.01, 0.045, 0.0, -d * 0.5 - 0.005, h * 0.55, win)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_bungalow(
    *,
    roof: tuple[float, float, float, float] = ROOF_GREEN,
) -> NodePath:
    """Brick bungalow — hipped roof, front dormer, sun-porch."""
    root = NodePath("bungalow")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = 0.17, 0.48, 0.15
    facade_mat = rgba_material(TAPESTRY)
    win = rgba_material(WINDOW)
    sill = rgba_material(LIMESTONE)
    roof_mat = rgba_material(roof)
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade_mat)
    # Low-pitched hip with broad eaves.
    hip = body.attachNewNode(make_pyramid(w + 0.06, d + 0.08, 0.06))
    hip.setPos(0.0, 0.0, h)
    hip.setMaterial(roof_mat, 1)
    # Wide front dormer.
    _box(detail, w * 0.45, 0.06, 0.05, 0.0, -d * 0.15, h + 0.04, facade_mat)
    dormer_roof = detail.attachNewNode(make_gable_roof(w * 0.5, 0.08, 0.035))
    dormer_roof.setPos(0.0, -d * 0.15, h + 0.065)
    dormer_roof.setMaterial(roof_mat, 1)
    # Enclosed brick sun-porch.
    porch_d = 0.06
    _box(detail, w * 0.85, porch_d, h * 0.7, 0.0, -d * 0.5 - porch_d * 0.5, h * 0.35, facade_mat)
    _box(detail, w * 0.7, 0.01, h * 0.4, 0.0, -d * 0.5 - porch_d - 0.005, h * 0.4, win)
    _box(detail, w * 0.72, 0.015, 0.012, 0.0, -d * 0.5 - porch_d - 0.008, h * 0.18, sill)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_storefront() -> NodePath:
    """Corner mixed-use brick: chamfered storefront base + flats above."""
    root = NodePath("storefront")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = 0.22, 0.55, 0.28
    facade = rgba_material(STOREFRONT_BRICK)
    win = rgba_material(WINDOW)
    glass = rgba_material((0.15, 0.18, 0.22, 1.0))
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade)
    _box(body, w * 0.96, d * 0.96, 0.012, 0.0, 0.0, h + 0.006, roof_material())
    _box(body, w + 0.01, 0.025, 0.025, 0.0, -d * 0.5 + 0.012, h + 0.012, facade)
    # Storefront glass band + chamfered corner plate.
    _box(detail, w * 0.85, 0.012, 0.09, 0.0, -d * 0.5 - 0.006, 0.07, glass)
    _box(detail, 0.05, 0.05, 0.10, -w * 0.5 + 0.02, -d * 0.5 + 0.02, 0.07, glass)
    for wz in (0.16, 0.24):
        _box(detail, 0.04, 0.01, 0.04, -w * 0.2, -d * 0.5 - 0.005, wz, win)
        _box(detail, 0.04, 0.01, 0.04, w * 0.2, -d * 0.5 - 0.005, wz, win)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _template_for(kind: str, x: float, y: float) -> NodePath:
    _ensure_templates()
    if kind == "two_flat":
        stories = "3" if _hash01(x, y, 5.0) < 0.35 else "2"
        r = _hash01(x, y, 3.0)
        color = "red" if r < 0.40 else ("buff" if r < 0.70 else "grey")
        return _TEMPLATES[f"two_flat_{stories}_{color}"]
    if kind == "cottage":
        r = _hash01(x, y, 3.0)
        if r < 0.55:
            return _TEMPLATES[f"cottage_{int(r * 100) % len(CLAPBOARD)}"]
        return _TEMPLATES["cottage_brick"]
    if kind == "bungalow":
        roof = "green" if _hash01(x, y, 4.0) < 0.5 else "brown"
        return _TEMPLATES[f"bungalow_{roof}"]
    return _TEMPLATES["storefront"]


def _stamp(
    template: NodePath,
    parent: NodePath,
    x: float,
    y: float,
    heading: float,
) -> None:
    """Copy body + detail under ``parent`` (caller flattenStrong's the sector)."""
    body_src = template.find("body")
    detail_src = template.find("detail")
    body = body_src.copyTo(parent)
    body.setPos(x, y, 0.0)
    body.setH(heading)
    if not detail_src.isEmpty():
        detail = detail_src.copyTo(parent)
        detail.setPos(x, y, 0.0)
        detail.setH(heading)


# ---------------------------------------------------------------------------
# Block fill
# ---------------------------------------------------------------------------
def _footprint_depth(kind: str) -> float:
    return {"two_flat": 0.52, "cottage": 0.42, "bungalow": 0.48, "storefront": 0.55}[kind]


def _footprint_width(kind: str) -> float:
    return {"two_flat": 0.16, "cottage": 0.15, "bungalow": 0.17, "storefront": 0.22}[kind]


def _place_frontage(
    *,
    parent: NodePath,
    roads: _RoadIndex,
    street_x: float | None,
    street_y: float | None,
    along0: float,
    along1: float,
    inward_sign: float,
    heading: float,
    corner_wide: bool,
) -> int:
    """Place lots along one street face of a half-block. Returns house count."""
    if along1 - along0 < LOT_WIDTH * 1.5:
        return 0
    # Only build along centreline that actually exists in the road network.
    if street_y is not None and not roads.has_street_y(street_y):
        return 0
    if street_x is not None and not roads.has_street_x(street_x):
        return 0
    # Inset from cross-streets so corner clearance holds.
    margin = CLEAR_MINOR
    a0 = along0 + margin
    a1 = along1 - margin
    if a1 <= a0 + LOT_WIDTH:
        return 0

    count = 0
    cursor = a0
    first = True
    while cursor + LOT_WIDTH <= a1 + 1e-6:
        mid = cursor + LOT_WIDTH * 0.5
        # World centre of lot frontage.
        if street_y is not None:
            # Frontage along X, street is E–W at street_y.
            hx = mid
            clear = max(CLEAR_MINOR, roads.road_width_at_y(street_y) * 0.5 + 0.08)
            hy = street_y + inward_sign * (clear + SETBACK)
            cx_lot, cy_lot = hx, hy
            is_corner = first or (cursor + LOT_WIDTH * 2 > a1)
            wide = corner_wide and is_corner
        else:
            assert street_x is not None
            hy = mid
            clear = max(CLEAR_MINOR, roads.road_width_at_x(street_x) * 0.5 + 0.08)
            hx = street_x + inward_sign * (clear + SETBACK)
            cx_lot, cy_lot = hx, hy
            is_corner = first or (cursor + LOT_WIDTH * 2 > a1)
            wide = corner_wide and is_corner

        if _in_loop(cx_lot, cy_lot) or _in_void(cx_lot, cy_lot):
            cursor += LOT_WIDTH
            first = False
            continue

        fill = _lot_fill(cx_lot, cy_lot)
        if _hash01(cx_lot, cy_lot, 6.0) > fill:
            cursor += LOT_WIDTH
            first = False
            continue

        kind = "storefront" if wide else _pick_archetype(cx_lot, cy_lot)
        depth = _footprint_depth(kind)
        width = _footprint_width(kind)
        # Push centre inward by half depth so front sits at setback line.
        if street_y is not None:
            cx = cx_lot
            cy = hy + inward_sign * (depth * 0.5)
            min_x, max_x = cx - width * 0.5, cx + width * 0.5
            y_front = cy - inward_sign * depth * 0.5
            y_back = cy + inward_sign * depth * 0.5
            min_y, max_y = (y_front, y_back) if y_front <= y_back else (y_back, y_front)
        else:
            cy = cy_lot
            cx = hx + inward_sign * (depth * 0.5)
            min_y, max_y = cy - width * 0.5, cy + width * 0.5
            x_front = cx - inward_sign * depth * 0.5
            x_back = cx + inward_sign * depth * 0.5
            min_x, max_x = (x_front, x_back) if x_front <= x_back else (x_back, x_front)

        # Keep rear clear of the alley strip (half-block mid-line).
        if street_y is not None:
            alley_y = street_y + inward_sign * BLOCK_SHORT
            alley_edge = alley_y - inward_sign * (ALLEY_WIDTH * 0.5)
            if inward_sign > 0 and max_y > alley_edge - 0.02:
                cursor += LOT_WIDTH
                first = False
                continue
            if inward_sign < 0 and min_y < alley_edge + 0.02:
                cursor += LOT_WIDTH
                first = False
                continue
        else:
            alley_x = street_x + inward_sign * BLOCK_SHORT
            alley_edge = alley_x - inward_sign * (ALLEY_WIDTH * 0.5)
            if inward_sign > 0 and max_x > alley_edge - 0.02:
                cursor += LOT_WIDTH
                first = False
                continue
            if inward_sign < 0 and min_x < alley_edge + 0.02:
                cursor += LOT_WIDTH
                first = False
                continue

        if roads.hits_footprint(min_x, min_y, max_x, max_y):
            cursor += LOT_WIDTH
            first = False
            continue

        template = _template_for(kind, cx, cy)
        _stamp(template, parent, cx, cy, heading)
        count += 1
        # Storefronts are wider — advance by storefront width + gangway.
        step = (_footprint_width(kind) + HOUSE_GAP) if kind == "storefront" else LOT_WIDTH
        cursor += step
        first = False
    return count


def _fill_cell(
    parent: NodePath,
    roads: _RoadIndex,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> int:
    """Fill one BLOCK_100 cell as two half-blocks split by a rear alley."""
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    if _in_loop(cx, cy) or _in_void(cx, cy):
        return 0
    if not (RES_X0 <= cx <= RES_X1 and RES_Y0 <= cy <= RES_Y1):
        return 0

    # Skip cells whose centre is already inside an expressway / arterial keepout.
    if roads.hits_point(cx, cy, radius=0.35):
        return 0

    # Corner storefronts where this cell meets a wide N–S or E–W spine.
    wide_south = roads.is_wide_frontage(y=y0)
    wide_north = roads.is_wide_frontage(y=y1)
    # Alternate alley orientation by mile section for visual variety.
    section = int(math.floor(cx / UNITS_PER_MILE) + math.floor(cy / UNITS_PER_MILE))
    ns_lots = section % 2 == 0

    total = 0
    if ns_lots:
        # Lots face N/S streets; alley runs E–W through mid-Y.
        total += _place_frontage(
            parent=parent,
            roads=roads,
            street_x=None,
            street_y=y0,
            along0=x0,
            along1=x1,
            inward_sign=1.0,
            heading=0.0,  # front −Y toward south street
            corner_wide=wide_south,
        )
        total += _place_frontage(
            parent=parent,
            roads=roads,
            street_x=None,
            street_y=y1,
            along0=x0,
            along1=x1,
            inward_sign=-1.0,
            heading=180.0,
            corner_wide=wide_north,
        )
    else:
        wide_west = roads.is_wide_frontage(x=x0)
        wide_east = roads.is_wide_frontage(x=x1)
        # Lots face E/W streets; alley runs N–S through mid-X.
        # Local front is −Y. H=-90 → front −X (west); H=+90 → front +X (east).
        total += _place_frontage(
            parent=parent,
            roads=roads,
            street_x=x0,
            street_y=None,
            along0=y0,
            along1=y1,
            inward_sign=1.0,
            heading=-90.0,
            corner_wide=wide_west,
        )
        total += _place_frontage(
            parent=parent,
            roads=roads,
            street_x=x1,
            street_y=None,
            along0=y0,
            along1=y1,
            inward_sign=-1.0,
            heading=90.0,
            corner_wide=wide_east,
        )
    return total


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def build_chicago_housing(
    parent: NodePath,
    plan: CityPlan,
    arterials: list[dict[str, Any]],
) -> tuple[list[tuple[float, float, NodePath]], list[tuple[float, float, NodePath]]]:
    """Generate residential fabric. Returns ``(sector_tiles, [])`` for LOD.

    Each mile-sector is filled then ``flattenStrong``'d into one GeomNode so the
    runtime cull path never walks hundreds of thousands of house NodePaths.
    """
    del plan  # roads come from arterials; plan kept for API symmetry with signals
    roads = _RoadIndex(arterials)

    root = parent.attachNewNode("chicago_housing")
    pool = root.attachNewNode("templates")
    _ensure_templates(pool)

    # Bucket cells by mile-sector so we can flatten one sector at a time.
    ix0 = int(math.floor(RES_X0 / BLOCK_100))
    ix1 = int(math.floor(RES_X1 / BLOCK_100))
    iy0 = int(math.floor(RES_Y0 / BLOCK_100))
    iy1 = int(math.floor(RES_Y1 / BLOCK_100))
    cells_by_sector: dict[tuple[int, int], list[tuple[float, float, float, float]]] = {}
    for ix in range(ix0, ix1):
        x0 = ix * BLOCK_100
        x1 = x0 + BLOCK_100
        if x1 < RES_X0 or x0 > RES_X1:
            continue
        for iy in range(iy0, iy1):
            y0 = iy * BLOCK_100
            y1 = y0 + BLOCK_100
            if y1 < RES_Y0 or y0 > RES_Y1:
                continue
            sx = int(math.floor((x0 + 0.5 * BLOCK_100) / SECTOR_SIZE))
            sy = int(math.floor((y0 + 0.5 * BLOCK_100) / SECTOR_SIZE))
            cells_by_sector.setdefault((sx, sy), []).append((x0, y0, x1, y1))

    total_houses = 0
    body_tiles: list[tuple[float, float, NodePath]] = []
    for (sx, sy), cells in cells_by_sector.items():
        sector = root.attachNewNode(f"sector_{sx}_{sy}")
        mesh = sector.attachNewNode("mesh")
        placed = 0
        since_flatten = 0
        for x0, y0, x1, y1 in cells:
            n = _fill_cell(mesh, roads, x0, y0, x1, y1)
            placed += n
            since_flatten += n
            # Chunked flatten keeps peak NodePaths and flatten cost bounded.
            if since_flatten >= 280:
                mesh.flattenStrong()
                since_flatten = 0
        if placed <= 0:
            sector.removeNode()
            continue
        if since_flatten > 0 or mesh.getNumChildren() > 0:
            mesh.flattenStrong()
        total_houses += placed
        cx = (sx + 0.5) * SECTOR_SIZE
        cy = (sy + 0.5) * SECTOR_SIZE
        sector.hide()
        body_tiles.append((cx, cy, sector))

    root.setTag("house_count", str(total_houses))
    root.setTag("sector_count", str(len(body_tiles)))
    print(
        "[housing] %d houses → %d flattened mile-sectors"
        % (total_houses, len(body_tiles))
    )
    return body_tiles, []
