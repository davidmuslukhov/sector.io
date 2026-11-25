"""Zone-based Chicago housing (2×): inner townhomes vs. suburban detached.

Zone 1 packs attached greystones / townhomes / two-flats; the outer city and
Chicagoland suburbs spread detached ranch / split-level / colonial / bungalow
stock with wide lawns. Airport voids stay clear. House bodies are stamped from
shared templates then ``flattenStrong``'d per mile-sector. Stoops, dormers,
garages, and driveways sit under an LODNode that drops past 450 units.
Suburban mile-sectors stream in as the camera approaches so startup stays light.
"""

from __future__ import annotations

import math
import time
from typing import Any

from panda3d.core import LODNode, NodePath

from city.geo import AIRPORT_VOIDS, MIDWAY_VOID, OHARE_VOID
from city.materials import rgba_material, roof_material, sidewalk_material
from city.mesh import box_instance, make_gable_roof, make_pyramid
from city.plan import CityPlan, _dist2_point_segment

# ---------------------------------------------------------------------------
# Scale / layout (2× Chicago)
# ---------------------------------------------------------------------------
UNITS_PER_MILE = 42.2
BLOCK_100 = 5.275  # 100 street numbers = 1/8 mile; also long side of a block
BLOCK_SHORT = BLOCK_100 * 0.5  # 330 ft half-block depth between street and alley mid

# Zone 2 / suburban envelope (outer city + suburbs).
RES_X0, RES_X1 = -759.6, 16.0
RES_Y0, RES_Y1 = -760.0, 680.0

# City of Chicago borders (Harlem / Howard / 95th / lakefront).
CITY_X0, CITY_X1 = -379.8, 16.0
CITY_Y0, CITY_Y1 = -501.1, 400.9

# Downtown Loop core — commercial / office, no residential fill.
LOOP_X0, LOOP_X1 = -35.0, 16.0
LOOP_Y0, LOOP_Y1 = -42.2, 32.0

# Zone 1 — inner-city townhome / row-house core (Kedzie→300 E, 47th→Irving Park).
ZONE1_X0, ZONE1_X1 = -168.8, 16.0
ZONE1_Y0, ZONE1_Y1 = -247.9, 211.0

# Smooth transition band (~1 mile) along the Zone 1 edge.
BLEND_WEST_X0, BLEND_WEST_X1 = -211.0, -168.8
BLEND_SOUTH_Y0, BLEND_SOUTH_Y1 = -290.1, -247.9
BLEND_NORTH_Y0, BLEND_NORTH_Y1 = 211.0, 253.2
BLEND_Y0, BLEND_Y1 = -290.1, 253.2
BLEND_X0, BLEND_X1 = -211.0, 16.0

# Named suburban belts (documentation / mix bias; fill uses _in_suburb).
NORTH_SHORE = (-379.8, 400.9, -42.2, 680.0)       # Evanston→Northbrook
NORTHWEST_SUBS = (-759.6, 211.0, -379.8, 680.0)    # Park Ridge→Mt Prospect
WEST_SUBS = (-759.6, -332.3, -379.8, 211.0)        # Oak Park→Oak Brook
SOUTH_SUBS = (-759.6, -760.0, 16.0, -501.1)        # Evergreen→Orland / Harvey

OHARE = OHARE_VOID
MIDWAY = MIDWAY_VOID
VOIDS = AIRPORT_VOIDS

# Zone 1 packing
INNER_LOT_W = 0.18
INNER_GANGWAY = 0.04
INNER_SETBACK = 0.10
INNER_STOOP = 0.06
INNER_CLUSTER_MIN = 4
INNER_CLUSTER_MAX = 8

# Suburban / outer packing (2× scale yards)
OUTER_LOT_W0, OUTER_LOT_W1 = 0.36, 0.48
OUTER_SETBACK0, OUTER_SETBACK1 = 0.24, 0.30
OUTER_SIDE_GAP0, OUTER_SIDE_GAP1 = 0.14, 0.20
GARAGE_CHANCE = 0.60  # inner-ring rear-alley garages
PLAZA_FACE_CHANCE = 0.30  # arterial strip-mall block faces

ALLEY_WIDTH = 0.14
INNER_RING_DIST = 2.0 * UNITS_PER_MILE  # 84.4 ≈ 2 miles from city border

CLEAR_EXPRESSWAY = 0.60
CLEAR_ARTERIAL = 0.42
CLEAR_COLLECTOR = 0.40
CLEAR_MINOR = 0.25

SECTOR_SIZE = UNITS_PER_MILE  # 1×1 mile sectors
HOUSING_HIDE_DIST = 200.0
HOUSING_VIEW_FACTOR = 0.28
HOUSING_VIEW_MIN = 45.0
HOUSING_MAX_TILES = 6  # each sector is heavy after bake — keep the cap tight
DETAIL_LOD_FAR = 450.0  # garages / driveways / dormers drop past this
# Stream budget — never bake a full mile-sector on one frame (that stuttered ~1s).
STREAM_BUDGET_S = 0.004  # soft fill budget; flatten always yields the frame
STREAM_PREFETCH = SECTOR_SIZE * 1.85  # start baking before the sector is in view
STREAM_FLATTEN_EVERY = 20  # small chunks so each flatten stays ~<12 ms

# Startup builds the dense inner box; suburban mile-sectors stream on approach.
HOUSING_BUILD_X0 = ZONE1_X0
HOUSING_BUILD_X1 = ZONE1_X1
HOUSING_BUILD_Y0 = ZONE1_Y0
HOUSING_BUILD_Y1 = ZONE1_Y1

# Full residential plate used for deferred suburban sector discovery.
SUBURB_BUILD_X0, SUBURB_BUILD_X1 = RES_X0, RES_X1
SUBURB_BUILD_Y0, SUBURB_BUILD_Y1 = RES_Y0, RES_Y1

# Facade / roof palettes
BRICK_RED = (0.45, 0.16, 0.13, 1.0)
BRICK_BURGUNDY = (0.40, 0.12, 0.14, 1.0)
BRICK_CHARCOAL = (0.28, 0.26, 0.25, 1.0)
BRICK_TAN = (0.62, 0.52, 0.40, 1.0)
BRICK_BUFF = (0.68, 0.58, 0.44, 1.0)
GREYSTONE = (0.62, 0.61, 0.58, 1.0)
BROWNSTONE = (0.42, 0.28, 0.22, 1.0)
TAPESTRY = (0.38, 0.18, 0.14, 1.0)
BLONDE_BRICK = (0.72, 0.62, 0.48, 1.0)
STUCCO_CREAM = (0.86, 0.82, 0.72, 1.0)
CLAPBOARD = (
    (0.82, 0.78, 0.68, 1.0),  # cream
    (0.55, 0.62, 0.48, 1.0),  # muted sage
    (0.45, 0.52, 0.62, 1.0),  # slate blue
    (0.58, 0.56, 0.54, 1.0),  # warm grey
)
RANCH_SIDING = (
    (0.92, 0.92, 0.90, 1.0),  # white
    (0.84, 0.78, 0.68, 1.0),  # cream
    (0.78, 0.78, 0.80, 1.0),  # pale grey
    (0.70, 0.78, 0.86, 1.0),  # pale blue
)
SPLIT_UPPER = (
    (0.84, 0.78, 0.68, 1.0),  # beige
    (0.55, 0.62, 0.48, 1.0),  # sage
    (0.52, 0.54, 0.56, 1.0),  # slate grey
)
COLONIAL_SIDING = (
    (0.94, 0.94, 0.92, 1.0),  # white clapboard
    (0.88, 0.82, 0.62, 1.0),  # warm yellow
    (0.86, 0.82, 0.72, 1.0),  # cream
    BRICK_RED,
)
ROOF_DARK = (0.18, 0.16, 0.14, 1.0)
ROOF_GREEN = (0.16, 0.22, 0.14, 1.0)
ROOF_BROWN = (0.28, 0.18, 0.12, 1.0)
ROOF_CHARCOAL = (0.22, 0.22, 0.22, 1.0)
WINDOW = (0.08, 0.09, 0.11, 1.0)
STOREFRONT_BRICK = (0.42, 0.18, 0.15, 1.0)
LIMESTONE = (0.72, 0.70, 0.64, 1.0)
DRIVEWAY = (0.42, 0.42, 0.40, 1.0)
ASPHALT = (0.22, 0.22, 0.22, 1.0)
PLAZA_BRICK = (0.48, 0.42, 0.36, 1.0)

_TEMPLATES: dict[str, NodePath] = {}
_TEMPLATE_POOL: NodePath | None = None

# Footprint lookup (width, depth) per archetype kind.
_FOOTPRINT: dict[str, tuple[float, float]] = {
    "greystone": (0.18, 0.54),
    "townhome": (0.17, 0.50),
    "two_flat": (0.16, 0.52),
    "bungalow": (0.22, 0.38),
    "foursquare": (0.22, 0.38),
    "ranch": (0.30, 0.24),
    "split_level": (0.28, 0.28),
    "colonial": (0.24, 0.30),
    "storefront": (0.22, 0.55),
    "plaza": (1.10, 0.28),
    "garage": (0.15, 0.15),
}

# Mutable stream state — filled by build_chicago_housing, consumed by ensure_*.
_STREAM: dict[str, Any] = {}


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


def _in_zone1(x: float, y: float) -> bool:
    return ZONE1_X0 <= x <= ZONE1_X1 and ZONE1_Y0 <= y <= ZONE1_Y1


def _in_city(x: float, y: float) -> bool:
    return CITY_X0 <= x <= CITY_X1 and CITY_Y0 <= y <= CITY_Y1


def _in_blend(x: float, y: float) -> bool:
    """1-mile transition ring just outside Zone 1 (not inside Zone 1)."""
    if _in_zone1(x, y):
        return False
    if BLEND_WEST_X0 <= x <= BLEND_WEST_X1 and BLEND_Y0 <= y <= BLEND_Y1:
        return True
    if BLEND_X0 <= x <= BLEND_X1 and BLEND_SOUTH_Y0 <= y <= BLEND_SOUTH_Y1:
        return True
    if BLEND_X0 <= x <= BLEND_X1 and BLEND_NORTH_Y0 <= y <= BLEND_NORTH_Y1:
        return True
    return False


def _in_res(x: float, y: float) -> bool:
    return RES_X0 <= x <= RES_X1 and RES_Y0 <= y <= RES_Y1


def _in_suburb(x: float, y: float) -> bool:
    """Outside Chicago city borders but inside the residential plate."""
    if not _in_res(x, y) or _in_city(x, y) or _in_void(x, y) or _in_loop(x, y):
        return False
    return x < CITY_X0 or y > CITY_Y1 or y < CITY_Y0


def _dist_to_city_border(x: float, y: float) -> float:
    """Outward distance to the City of Chicago rectangle (0 if inside)."""
    if _in_city(x, y):
        return 0.0
    dx = 0.0
    if x < CITY_X0:
        dx = CITY_X0 - x
    elif x > CITY_X1:
        dx = x - CITY_X1
    dy = 0.0
    if y < CITY_Y0:
        dy = CITY_Y0 - y
    elif y > CITY_Y1:
        dy = y - CITY_Y1
    if dx > 0.0 and dy > 0.0:
        return math.hypot(dx, dy)
    return max(dx, dy)


def _is_inner_ring(x: float, y: float) -> bool:
    """Streetcar / inner-ring suburbs within ~2 miles of the city border."""
    return _in_suburb(x, y) and _dist_to_city_border(x, y) <= INNER_RING_DIST


def _zone_of(x: float, y: float) -> str:
    """Return ``inner`` | ``blend`` | ``outer`` | ``suburb`` | ``none``."""
    if not _in_res(x, y) or _in_loop(x, y) or _in_void(x, y):
        return "none"
    if _in_suburb(x, y):
        return "suburb"
    if _in_blend(x, y):
        return "blend"
    if _in_zone1(x, y):
        return "inner"
    if _in_city(x, y):
        return "outer"
    return "none"


def _lot_fill(x: float, y: float) -> float:
    zone = _zone_of(x, y)
    if zone == "inner":
        return 0.88 + 0.08 * _hash01(x, y, 1.1)
    if zone == "blend":
        return 0.80 + 0.10 * _hash01(x, y, 1.15)
    if zone == "outer":
        return 0.72 + 0.12 * _hash01(x, y, 1.2)
    if zone == "suburb":
        # 65–80% lot fill — occasional empty corners / pocket parks.
        return 0.65 + 0.15 * _hash01(x, y, 1.25)
    return 0.0


def _pick_inner(x: float, y: float) -> str:
    r = _hash01(x, y, 2.0)
    if r < 0.45:
        return "greystone"
    if r < 0.80:
        return "townhome"
    return "two_flat"


def _pick_outer_city(x: float, y: float) -> str:
    """Within-city outer belt — bungalow / Foursquare / ranch mix."""
    r = _hash01(x, y, 2.1)
    if r < 0.45:
        return "bungalow"
    if r < 0.75:
        return "foursquare"
    return "ranch"


def _pick_suburb(x: float, y: float) -> str:
    """Suburban mix: ranch 40% / split-level 25% / colonial 20% / bungalow+FS 15%."""
    r = _hash01(x, y, 2.2)
    if r < 0.40:
        return "ranch"
    if r < 0.65:
        return "split_level"
    if r < 0.85:
        return "colonial"
    # Inner-ring streetcar suburbs lean bungalow; outer ring leans Foursquare.
    if _is_inner_ring(x, y):
        return "bungalow" if _hash01(x, y, 2.25) < 0.70 else "foursquare"
    return "foursquare" if _hash01(x, y, 2.26) < 0.45 else "bungalow"


def _pick_archetype(x: float, y: float) -> str:
    zone = _zone_of(x, y)
    if zone == "inner":
        return _pick_inner(x, y)
    if zone == "blend":
        return _pick_inner(x, y) if _hash01(x, y, 2.5) < 0.50 else _pick_outer_city(x, y)
    if zone == "suburb":
        return _pick_suburb(x, y)
    if zone == "outer":
        return _pick_outer_city(x, y)
    return "bungalow"


def _is_attached_kind(kind: str) -> bool:
    return kind in ("greystone", "townhome", "two_flat")


def _uses_rear_alley(x: float, y: float) -> bool:
    """Inner-ring suburbs + all in-city fabric keep the rear alley."""
    zone = _zone_of(x, y)
    if zone in ("inner", "blend", "outer"):
        return True
    if zone == "suburb":
        return _is_inner_ring(x, y)
    return False


def _suburb_setback(x: float, y: float) -> float:
    t = _hash01(x, y, 4.0)
    return OUTER_SETBACK0 + (OUTER_SETBACK1 - OUTER_SETBACK0) * t


# ---------------------------------------------------------------------------
# Road clearance index
# ---------------------------------------------------------------------------
class _RoadIndex:
    """Spatial hash of road segments with layer-based clearance radii."""

    __slots__ = ("cell", "bins", "axis_x", "axis_y")

    def __init__(self, arterials: list[dict[str, Any]], cell: float = 8.0) -> None:
        self.cell = cell
        self.bins: dict[tuple[int, int], list[tuple[float, float, float, float, float]]] = {}
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
            # Clearance from centreline; at least half-width + margin.
            # Arterials 0.50–0.55 → 0.42; minors 0.22 → 0.25; expressways 0.60.
            if layer == "arterial" and 0.48 <= width <= 0.58:
                clear = max(clear, CLEAR_ARTERIAL)
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
        """True if the axis is a collector (0.35) or arterial (0.50+)."""
        if x is not None:
            w = self._nearest_axis(self.axis_x, x)
            return w is not None and w >= 0.34
        if y is not None:
            w = self._nearest_axis(self.axis_y, y)
            return w is not None and w >= 0.34
        return False

    def is_suburban_arterial(
        self, x: float | None = None, y: float | None = None
    ) -> bool:
        """True for 0.50–0.55 suburban / city arterial spines (strip-plaza hosts)."""
        if x is not None:
            w = self._nearest_axis(self.axis_x, x)
            return w is not None and 0.48 <= w <= 0.58
        if y is not None:
            w = self._nearest_axis(self.axis_y, y)
            return w is not None and 0.48 <= w <= 0.58
        return False


# ---------------------------------------------------------------------------
# Archetype templates (body + detail children)
# ---------------------------------------------------------------------------
def _ensure_templates(pool: NodePath | None = None) -> None:
    """Build pre-coloured archetype templates once (stamped via instanceTo)."""
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

    # Zone 1 — greystones / brick row houses
    for name, color in (
        ("grey", GREYSTONE),
        ("red", BRICK_RED),
        ("brown", BROWNSTONE),
    ):
        for hi, h in enumerate((0.28, 0.32, 0.36)):
            node = _make_greystone(facade=color, height=h)
            node.reparentTo(pool)
            _TEMPLATES[f"greystone_{name}_{hi}"] = node

    # Zone 1 — townhomes (stepped parapet height variants)
    for name, color in (
        ("red", BRICK_BURGUNDY),
        ("charcoal", BRICK_CHARCOAL),
        ("tan", BRICK_TAN),
    ):
        for hi, h in enumerate((0.28, 0.30, 0.32)):
            node = _make_townhome(facade=color, height=h)
            node.reparentTo(pool)
            _TEMPLATES[f"townhome_{name}_{hi}"] = node

    # Zone 1 — two-flats
    for name, color in (("red", BRICK_RED), ("buff", BRICK_BUFF), ("grey", GREYSTONE)):
        node = _make_two_flat(facade=color)
        node.reparentTo(pool)
        _TEMPLATES[f"two_flat_{name}"] = node

    # Suburban / outer — bungalows
    for facade_name, facade in (("tapestry", TAPESTRY), ("blonde", BLONDE_BRICK)):
        for roof_name, roof in (("green", ROOF_GREEN), ("brown", ROOF_BROWN)):
            node = _make_bungalow(facade=facade, roof=roof)
            node.reparentTo(pool)
            _TEMPLATES[f"bungalow_{facade_name}_{roof_name}"] = node

    # Suburban / outer — Foursquares
    for i, color in enumerate((STUCCO_CREAM, CLAPBOARD[1], CLAPBOARD[2], BRICK_TAN)):
        node = _make_foursquare(facade=color)
        node.reparentTo(pool)
        _TEMPLATES[f"foursquare_{i}"] = node

    # Mid-century ranch (with / without baked driveway for outer-ring)
    for i, color in enumerate(RANCH_SIDING):
        for drive in (False, True):
            node = _make_ranch(facade=color, with_driveway=drive)
            node.reparentTo(pool)
            _TEMPLATES[f"ranch_{i}_{1 if drive else 0}"] = node

    # Split-level / bi-level
    for i, upper in enumerate(SPLIT_UPPER):
        for drive in (False, True):
            node = _make_split_level(upper=upper, with_driveway=drive)
            node.reparentTo(pool)
            _TEMPLATES[f"split_level_{i}_{1 if drive else 0}"] = node

    # Colonial / Cape Cod
    for i, color in enumerate(COLONIAL_SIDING):
        for drive in (False, True):
            node = _make_colonial(facade=color, with_driveway=drive)
            node.reparentTo(pool)
            _TEMPLATES[f"colonial_{i}_{1 if drive else 0}"] = node

    node = _make_storefront()
    node.reparentTo(pool)
    _TEMPLATES["storefront"] = node

    for i, w in enumerate((0.85, 1.10, 1.40)):
        node = _make_plaza(width=w)
        node.reparentTo(pool)
        _TEMPLATES[f"plaza_{i}"] = node

    node = _make_garage()
    node.reparentTo(pool)
    _TEMPLATES["garage"] = node


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


def _make_greystone(
    *,
    facade: tuple[float, float, float, float],
    height: float,
) -> NodePath:
    """Classic Chicago Greystone / brick row house with bay + parapet."""
    root = NodePath("greystone")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = 0.18, 0.54, height
    facade_mat = rgba_material(facade)
    win = rgba_material(WINDOW)
    stoop = sidewalk_material()
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade_mat)
    _box(body, w + 0.01, 0.03, 0.03, 0.0, -d * 0.5 + 0.015, h + 0.015, facade_mat)
    _box(body, w * 0.96, d * 0.96, 0.012, 0.0, 0.0, h + 0.006, roof_material())
    bay_d = 0.04
    _box(detail, w * 0.48, bay_d, h * 0.88, 0.0, -d * 0.5 - bay_d * 0.5, h * 0.48, facade_mat)
    _box(detail, w * 0.40, 0.01, h * 0.58, 0.0, -d * 0.5 - bay_d - 0.005, h * 0.50, win)
    _box(
        detail,
        0.07,
        INNER_STOOP,
        0.025,
        w * 0.28,
        -d * 0.5 - INNER_STOOP * 0.5,
        0.04,
        stoop,
    )
    _box(
        detail,
        0.06,
        0.04,
        0.07,
        w * 0.28,
        -d * 0.5 - INNER_STOOP - 0.02,
        0.035,
        stoop,
    )
    for wz in (h * 0.22, h * 0.50, h * 0.78):
        _box(detail, 0.03, 0.01, 0.04, -w * 0.30, -d * 0.5 - 0.005, wz, win)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_townhome(
    *,
    facade: tuple[float, float, float, float],
    height: float,
) -> NodePath:
    """Modern / historic brick townhome with stepped parapet + balcony cutout."""
    root = NodePath("townhome")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = 0.17, 0.50, height
    facade_mat = rgba_material(facade)
    win = rgba_material(WINDOW)
    trim = rgba_material(ROOF_DARK)
    stoop = sidewalk_material()
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade_mat)
    _box(body, w * 0.96, d * 0.96, 0.012, 0.0, 0.0, h + 0.006, roof_material())
    _box(body, w + 0.008, 0.028, 0.028, 0.0, -d * 0.5 + 0.014, h + 0.014, facade_mat)
    _box(detail, w * 0.55, 0.03, 0.06, 0.0, -d * 0.5 - 0.01, h * 0.55, trim)
    _box(detail, w * 0.50, 0.01, 0.045, 0.0, -d * 0.5 - 0.02, h * 0.55, win)
    _box(
        detail,
        0.06,
        INNER_STOOP,
        0.02,
        0.0,
        -d * 0.5 - INNER_STOOP * 0.5,
        0.025,
        stoop,
    )
    for wz in (h * 0.22, h * 0.78):
        _box(detail, 0.035, 0.01, 0.045, -w * 0.28, -d * 0.5 - 0.005, wz, win)
        _box(detail, 0.035, 0.01, 0.045, w * 0.28, -d * 0.5 - 0.005, wz, win)
    _box(detail, w * 0.92, 0.008, 0.01, 0.0, -d * 0.5 - 0.004, h * 0.35, trim)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_two_flat(
    *,
    facade: tuple[float, float, float, float] = BRICK_RED,
) -> NodePath:
    """Narrow frame / brick two-flat with double-decker porch."""
    root = NodePath("two_flat")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = 0.16, 0.52, 0.24
    facade_mat = rgba_material(facade)
    win = rgba_material(WINDOW)
    stoop = sidewalk_material()
    trim = rgba_material(ROOF_DARK)
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade_mat)
    _box(body, w + 0.01, 0.03, 0.025, 0.0, -d * 0.5 + 0.015, h + 0.012, facade_mat)
    _box(body, w * 0.96, d * 0.96, 0.012, 0.0, 0.0, h + 0.006, roof_material())
    porch_d = INNER_STOOP + 0.02
    _box(detail, w * 0.70, porch_d, 0.02, 0.0, -d * 0.5 - porch_d * 0.5, 0.04, stoop)
    _box(detail, w * 0.70, porch_d, 0.02, 0.0, -d * 0.5 - porch_d * 0.5, h * 0.52, stoop)
    _box(detail, 0.015, 0.015, h * 0.50, -w * 0.30, -d * 0.5 - porch_d + 0.01, h * 0.28, trim)
    _box(detail, 0.015, 0.015, h * 0.50, w * 0.30, -d * 0.5 - porch_d + 0.01, h * 0.28, trim)
    for wz in (h * 0.28, h * 0.68):
        _box(detail, 0.03, 0.01, 0.04, 0.0, -d * 0.5 - 0.005, wz, win)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_bungalow(
    *,
    facade: tuple[float, float, float, float] = TAPESTRY,
    roof: tuple[float, float, float, float] = ROOF_GREEN,
) -> NodePath:
    """Suburban brick bungalow — low hip + dormer + enclosed front porch."""
    root = NodePath("bungalow")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = 0.22, 0.38, 0.16
    facade_mat = rgba_material(facade)
    win = rgba_material(WINDOW)
    sill = rgba_material(LIMESTONE)
    roof_mat = rgba_material(roof)
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade_mat)
    hip = body.attachNewNode(make_pyramid(w + 0.06, d + 0.08, 0.06))
    hip.setPos(0.0, 0.0, h)
    hip.setMaterial(roof_mat, 1)
    _box(detail, w * 0.45, 0.06, 0.05, 0.0, -d * 0.15, h + 0.04, facade_mat)
    dormer_roof = detail.attachNewNode(make_gable_roof(w * 0.5, 0.08, 0.035))
    dormer_roof.setPos(0.0, -d * 0.15, h + 0.065)
    dormer_roof.setMaterial(roof_mat, 1)
    porch_d = 0.06
    _box(detail, w * 0.85, porch_d, h * 0.7, 0.0, -d * 0.5 - porch_d * 0.5, h * 0.35, facade_mat)
    _box(detail, w * 0.70, 0.01, h * 0.4, 0.0, -d * 0.5 - porch_d - 0.005, h * 0.4, win)
    _box(detail, w * 0.72, 0.015, 0.012, 0.0, -d * 0.5 - porch_d - 0.008, h * 0.18, sill)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_foursquare(
    *,
    facade: tuple[float, float, float, float],
) -> NodePath:
    """American Foursquare — pyramid hip + full-width porch (height 0.22)."""
    root = NodePath("foursquare")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = 0.22, 0.38, 0.22
    facade_mat = rgba_material(facade)
    win = rgba_material(WINDOW)
    roof_mat = rgba_material(ROOF_DARK)
    stoop = sidewalk_material()
    trim = rgba_material(ROOF_DARK)
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade_mat)
    hip = body.attachNewNode(make_pyramid(w + 0.04, d + 0.04, 0.07))
    hip.setPos(0.0, 0.0, h)
    hip.setMaterial(roof_mat, 1)
    _box(detail, w * 0.28, 0.05, 0.04, 0.0, -d * 0.12, h + 0.05, facade_mat)
    dormer = detail.attachNewNode(make_gable_roof(w * 0.32, 0.07, 0.03))
    dormer.setPos(0.0, -d * 0.12, h + 0.07)
    dormer.setMaterial(roof_mat, 1)
    porch_d = 0.08
    _box(detail, w * 0.95, porch_d, 0.02, 0.0, -d * 0.5 - porch_d * 0.5, 0.03, stoop)
    _box(detail, w * 0.95, porch_d, 0.015, 0.0, -d * 0.5 - porch_d * 0.5, 0.12, stoop)
    _box(detail, 0.02, 0.02, 0.10, -w * 0.40, -d * 0.5 - porch_d + 0.01, 0.08, trim)
    _box(detail, 0.02, 0.02, 0.10, w * 0.40, -d * 0.5 - porch_d + 0.01, 0.08, trim)
    for wx in (-w * 0.28, w * 0.28):
        for wz in (h * 0.30, h * 0.70):
            _box(detail, 0.035, 0.01, 0.04, wx, -d * 0.5 - 0.005, wz, win)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _add_front_driveway(detail: NodePath, gx: float, front_y: float, length: float) -> None:
    """Flat grey concrete strip (width 0.07, Z=+0.005) from street to side garage."""
    drive = rgba_material(DRIVEWAY)
    _box(detail, 0.07, length, 0.008, gx, front_y - length * 0.5, 0.005, drive)


def _make_ranch(
    *,
    facade: tuple[float, float, float, float],
    with_driveway: bool = False,
) -> NodePath:
    """Mid-century suburban ranch — wide 1-story, garage wing, picture window."""
    root = NodePath("ranch")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = 0.30, 0.24, 0.11
    facade_mat = rgba_material(facade)
    brick = rgba_material(BLONDE_BRICK)
    win = rgba_material(WINDOW)
    roof_mat = rgba_material(ROOF_CHARCOAL)
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade_mat)
    _box(body, w + 0.002, d + 0.002, h * 0.35, 0.0, 0.0, h * 0.18, brick)
    # Low-pitched side-gable with broad eaves (peak +0.04).
    gable = body.attachNewNode(make_gable_roof(d + 0.06, w + 0.08, 0.04))
    gable.setH(90.0)
    gable.setPos(0.0, 0.0, h)
    gable.setMaterial(roof_mat, 1)
    # Attached single-story garage wing (LOD detail when far).
    gw, gd, gh = 0.12, 0.20, 0.10
    gx = w * 0.5 + gw * 0.5 - 0.01
    _box(detail, gw, gd, gh, gx, d * 0.05, gh * 0.5, facade_mat)
    gable_g = detail.attachNewNode(make_gable_roof(gd + 0.02, gw + 0.03, 0.03))
    gable_g.setH(90.0)
    gable_g.setPos(gx, d * 0.05, gh)
    gable_g.setMaterial(roof_mat, 1)
    _box(detail, gw * 0.75, 0.01, gh * 0.65, gx, d * 0.05 - gd * 0.5 - 0.005, gh * 0.4, win)
    # Wide front picture-window recess.
    _box(detail, w * 0.42, 0.01, h * 0.55, -w * 0.08, -d * 0.5 - 0.005, h * 0.52, win)
    if with_driveway:
        drive_len = OUTER_SETBACK1 + 0.04
        _add_front_driveway(detail, gx, -d * 0.5, drive_len)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_split_level(
    *,
    upper: tuple[float, float, float, float],
    with_driveway: bool = False,
) -> NodePath:
    """Suburban split-level / bi-level — tucked garage + raised living wing."""
    root = NodePath("split_level")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d = 0.28, 0.28
    brick = rgba_material(BRICK_RED)
    upper_mat = rgba_material(upper)
    win = rgba_material(WINDOW)
    roof_mat = rgba_material(ROOF_DARK)
    # Low wing over tucked-under garage (height 0.11).
    low_w = w * 0.48
    _box(body, low_w, d, 0.11, -w * 0.26, 0.0, 0.055, brick)
    # Raised wing (height 0.17) with side-gable.
    high_w = w * 0.52
    _box(body, high_w, d, 0.17, w * 0.24, 0.0, 0.085, upper_mat)
    gable = body.attachNewNode(make_gable_roof(d + 0.04, high_w + 0.04, 0.05))
    gable.setH(90.0)
    gable.setPos(w * 0.24, 0.0, 0.17)
    gable.setMaterial(roof_mat, 1)
    # Low wing flat/hip cap.
    hip = body.attachNewNode(make_pyramid(low_w + 0.03, d + 0.03, 0.03))
    hip.setPos(-w * 0.26, 0.0, 0.11)
    hip.setMaterial(roof_mat, 1)
    # Garage door under low wing (detail).
    _box(detail, low_w * 0.70, 0.01, 0.07, -w * 0.26, -d * 0.5 - 0.005, 0.045, win)
    _box(detail, 0.05, 0.01, 0.04, w * 0.20, -d * 0.5 - 0.005, 0.12, win)
    _box(detail, 0.05, 0.01, 0.04, w * 0.32, -d * 0.5 - 0.005, 0.12, win)
    if with_driveway:
        _add_front_driveway(detail, -w * 0.26, -d * 0.5, OUTER_SETBACK1 + 0.04)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_colonial(
    *,
    facade: tuple[float, float, float, float],
    with_driveway: bool = False,
) -> NodePath:
    """Classic suburban two-story Colonial / Cape Cod with dormers + portico."""
    root = NodePath("colonial")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = 0.24, 0.30, 0.21
    facade_mat = rgba_material(facade)
    win = rgba_material(WINDOW)
    roof_mat = rgba_material(ROOF_DARK)
    trim = rgba_material(ROOF_DARK)
    stoop = sidewalk_material()
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade_mat)
    # Steep side-gable (peak +0.07).
    gable = body.attachNewNode(make_gable_roof(d + 0.04, w + 0.05, 0.07))
    gable.setH(90.0)
    gable.setPos(0.0, 0.0, h)
    gable.setMaterial(roof_mat, 1)
    # 2–3 front-facing attic dormers (detail).
    for dx in (-w * 0.28, 0.0, w * 0.28):
        _box(detail, 0.045, 0.05, 0.035, dx, -d * 0.08, h + 0.04, facade_mat)
        dorm = detail.attachNewNode(make_gable_roof(0.055, 0.06, 0.025))
        dorm.setPos(dx, -d * 0.08, h + 0.055)
        dorm.setMaterial(roof_mat, 1)
    # Centered front entry portico.
    _box(detail, 0.08, 0.06, 0.015, 0.0, -d * 0.5 - 0.03, 0.12, stoop)
    _box(detail, 0.015, 0.015, 0.10, -0.03, -d * 0.5 - 0.05, 0.07, trim)
    _box(detail, 0.015, 0.015, 0.10, 0.03, -d * 0.5 - 0.05, 0.07, trim)
    for wx in (-w * 0.30, w * 0.30):
        for wz in (h * 0.28, h * 0.68):
            _box(detail, 0.035, 0.01, 0.04, wx, -d * 0.5 - 0.005, wz, win)
    # Optional attached side garage wing.
    gw, gd, gh = 0.12, 0.18, 0.10
    gx = w * 0.5 + gw * 0.5 - 0.01
    _box(detail, gw, gd, gh, gx, d * 0.05, gh * 0.5, facade_mat)
    gable_g = detail.attachNewNode(make_gable_roof(gd + 0.02, gw + 0.03, 0.03))
    gable_g.setH(90.0)
    gable_g.setPos(gx, d * 0.05, gh)
    gable_g.setMaterial(roof_mat, 1)
    if with_driveway:
        _add_front_driveway(detail, gx, -d * 0.5, OUTER_SETBACK1 + 0.04)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_storefront() -> NodePath:
    """Corner mixed-use brick: storefront base + flats above."""
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
    _box(detail, w * 0.85, 0.012, 0.09, 0.0, -d * 0.5 - 0.006, 0.07, glass)
    _box(detail, 0.05, 0.05, 0.10, -w * 0.5 + 0.02, -d * 0.5 + 0.02, 0.07, glass)
    for wz in (0.16, 0.24):
        _box(detail, 0.04, 0.01, 0.04, -w * 0.2, -d * 0.5 - 0.005, wz, win)
        _box(detail, 0.04, 0.01, 0.04, w * 0.2, -d * 0.5 - 0.005, wz, win)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_plaza(*, width: float = 1.10) -> NodePath:
    """Low-slung 1-story suburban strip-mall plaza + asphalt front parking."""
    root = NodePath("plaza")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w, d, h = width, 0.28, 0.13
    facade = rgba_material(PLAZA_BRICK)
    glass = rgba_material((0.18, 0.20, 0.24, 1.0))
    asphalt = rgba_material(ASPHALT)
    roof_mat = rgba_material(ROOF_CHARCOAL)
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade)
    _box(body, w + 0.04, d + 0.04, 0.02, 0.0, 0.0, h + 0.01, roof_mat)
    # Storefront glass band.
    _box(detail, w * 0.90, 0.012, 0.07, 0.0, -d * 0.5 - 0.006, 0.06, glass)
    # Parking lot plate sits in front (−Y); stamped with plaza at setback 0.35.
    park_d = 0.35
    _box(detail, w * 0.98, park_d, 0.006, 0.0, -d * 0.5 - park_d * 0.5, 0.004, asphalt)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _make_garage() -> NodePath:
    """Detached rear-alley garage (0.15² × 0.10, low pitch)."""
    root = NodePath("garage")
    body = _part(root, "body")
    detail = _part(root, "detail")
    w = d = 0.15
    h = 0.10
    facade = rgba_material(BRICK_CHARCOAL)
    roof_mat = rgba_material(ROOF_DARK)
    door = rgba_material(ROOF_BROWN)
    _box(body, w, d, h, 0.0, 0.0, h * 0.5, facade)
    hip = body.attachNewNode(make_pyramid(w + 0.02, d + 0.02, 0.03))
    hip.setPos(0.0, 0.0, h)
    hip.setMaterial(roof_mat, 1)
    _box(detail, w * 0.7, 0.01, h * 0.55, 0.0, -d * 0.5 - 0.005, h * 0.4, door)
    body.flattenStrong()
    detail.flattenStrong()
    return root


def _template_for(kind: str, x: float, y: float) -> NodePath:
    _ensure_templates()
    drive = 0 if _uses_rear_alley(x, y) else 1
    if kind == "greystone":
        r = _hash01(x, y, 3.0)
        color = "grey" if r < 0.40 else ("red" if r < 0.75 else "brown")
        hi = int(_hash01(x, y, 3.1) * 3.0) % 3
        return _TEMPLATES[f"greystone_{color}_{hi}"]
    if kind == "townhome":
        r = _hash01(x, y, 3.2)
        color = "red" if r < 0.40 else ("charcoal" if r < 0.70 else "tan")
        hi = int(_hash01(x, y, 3.3) * 3.0) % 3
        return _TEMPLATES[f"townhome_{color}_{hi}"]
    if kind == "two_flat":
        r = _hash01(x, y, 3.4)
        color = "red" if r < 0.45 else ("buff" if r < 0.75 else "grey")
        return _TEMPLATES[f"two_flat_{color}"]
    if kind == "bungalow":
        facade = "tapestry" if _hash01(x, y, 3.5) < 0.65 else "blonde"
        roof = "green" if _hash01(x, y, 3.6) < 0.5 else "brown"
        return _TEMPLATES[f"bungalow_{facade}_{roof}"]
    if kind == "foursquare":
        return _TEMPLATES[f"foursquare_{int(_hash01(x, y, 3.7) * 4.0) % 4}"]
    if kind == "ranch":
        i = int(_hash01(x, y, 3.8) * len(RANCH_SIDING)) % len(RANCH_SIDING)
        return _TEMPLATES[f"ranch_{i}_{drive}"]
    if kind == "split_level":
        i = int(_hash01(x, y, 3.85) * len(SPLIT_UPPER)) % len(SPLIT_UPPER)
        return _TEMPLATES[f"split_level_{i}_{drive}"]
    if kind == "colonial":
        i = int(_hash01(x, y, 3.9) * len(COLONIAL_SIDING)) % len(COLONIAL_SIDING)
        return _TEMPLATES[f"colonial_{i}_{drive}"]
    if kind == "plaza":
        i = int(_hash01(x, y, 3.95) * 3.0) % 3
        return _TEMPLATES[f"plaza_{i}"]
    if kind == "garage":
        return _TEMPLATES["garage"]
    return _TEMPLATES["storefront"]


def _stamp(
    template: NodePath,
    body_parent: NodePath,
    detail_parent: NodePath,
    x: float,
    y: float,
    heading: float,
    *,
    include_detail: bool = True,
) -> None:
    """Stamp house body; optionally instance detail under the sector LODNode."""
    body_src = template.find("body")
    body = body_parent.attachNewNode("h")
    body.setPos(x, y, 0.0)
    body.setH(heading)
    body_src.instanceTo(body)
    if include_detail:
        detail_src = template.find("detail")
        if not detail_src.isEmpty():
            det = detail_parent.attachNewNode("d")
            det.setPos(x, y, 0.0)
            det.setH(heading)
            detail_src.instanceTo(det)


def _footprint_width(kind: str) -> float:
    return _FOOTPRINT[kind][0]


def _footprint_depth(kind: str) -> float:
    return _FOOTPRINT[kind][1]


# ---------------------------------------------------------------------------
# Block fill
# ---------------------------------------------------------------------------
def _house_bounds(
    *,
    street_x: float | None,
    street_y: float | None,
    mid: float,
    inward_sign: float,
    setback: float,
    clear: float,
    width: float,
    depth: float,
) -> tuple[float, float, float, float, float, float]:
    """Return (cx, cy, min_x, min_y, max_x, max_y) for a house footprint."""
    if street_y is not None:
        hx = mid
        hy = street_y + inward_sign * (clear + setback)
        cx = hx
        cy = hy + inward_sign * (depth * 0.5)
        min_x, max_x = cx - width * 0.5, cx + width * 0.5
        y_front = cy - inward_sign * depth * 0.5
        y_back = cy + inward_sign * depth * 0.5
        min_y, max_y = (y_front, y_back) if y_front <= y_back else (y_back, y_front)
    else:
        assert street_x is not None
        hy = mid
        hx = street_x + inward_sign * (clear + setback)
        cy = hy
        cx = hx + inward_sign * (depth * 0.5)
        min_y, max_y = cy - width * 0.5, cy + width * 0.5
        x_front = cx - inward_sign * depth * 0.5
        x_back = cx + inward_sign * depth * 0.5
        min_x, max_x = (x_front, x_back) if x_front <= x_back else (x_back, x_front)
    return cx, cy, min_x, min_y, max_x, max_y


def _alley_ok(
    *,
    street_x: float | None,
    street_y: float | None,
    inward_sign: float,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    use_alley: bool,
) -> bool:
    """True if the footprint stays clear of the rear alley strip (when used)."""
    if not use_alley:
        return True
    if street_y is not None:
        alley_y = street_y + inward_sign * BLOCK_SHORT
        alley_edge = alley_y - inward_sign * (ALLEY_WIDTH * 0.5)
        if inward_sign > 0 and max_y > alley_edge - 0.02:
            return False
        if inward_sign < 0 and min_y < alley_edge + 0.02:
            return False
    else:
        assert street_x is not None
        alley_x = street_x + inward_sign * BLOCK_SHORT
        alley_edge = alley_x - inward_sign * (ALLEY_WIDTH * 0.5)
        if inward_sign > 0 and max_x > alley_edge - 0.02:
            return False
        if inward_sign < 0 and min_x < alley_edge + 0.02:
            return False
    return True


def _garage_pos(
    *,
    street_x: float | None,
    street_y: float | None,
    mid: float,
    inward_sign: float,
) -> tuple[float, float]:
    """Seat a detached garage near the rear alley edge of the lot."""
    gw = _footprint_width("garage")
    if street_y is not None:
        alley_y = street_y + inward_sign * BLOCK_SHORT
        gy = alley_y - inward_sign * (ALLEY_WIDTH * 0.5 + gw * 0.5 + 0.02)
        return mid, gy
    assert street_x is not None
    alley_x = street_x + inward_sign * BLOCK_SHORT
    gx = alley_x - inward_sign * (ALLEY_WIDTH * 0.5 + gw * 0.5 + 0.02)
    return gx, mid


def _try_place(
    *,
    body_parent: NodePath,
    detail_parent: NodePath,
    roads: _RoadIndex,
    street_x: float | None,
    street_y: float | None,
    mid: float,
    inward_sign: float,
    heading: float,
    kind: str,
    setback: float,
    clear: float,
    with_garage: bool = False,
    use_alley: bool = True,
    include_detail: bool = True,
) -> bool:
    """Place one house (and optional garage). Returns True if stamped."""
    width = _footprint_width(kind)
    depth = _footprint_depth(kind)
    cx, cy, min_x, min_y, max_x, max_y = _house_bounds(
        street_x=street_x,
        street_y=street_y,
        mid=mid,
        inward_sign=inward_sign,
        setback=setback,
        clear=clear,
        width=width,
        depth=depth,
    )
    if _in_loop(cx, cy) or _in_void(cx, cy):
        return False
    if not _alley_ok(
        street_x=street_x,
        street_y=street_y,
        inward_sign=inward_sign,
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        use_alley=use_alley,
    ):
        return False
    if roads.hits_footprint(min_x, min_y, max_x, max_y):
        return False

    template = _template_for(kind, cx, cy)
    _stamp(
        template,
        body_parent,
        detail_parent,
        cx,
        cy,
        heading,
        include_detail=include_detail,
    )

    # Detached rear-alley garages land in detail (LOD-culled past 450).
    if (
        include_detail
        and with_garage
        and kind not in ("ranch", "split_level", "colonial", "plaza", "storefront")
    ):
        gx, gy = _garage_pos(
            street_x=street_x,
            street_y=street_y,
            mid=mid,
            inward_sign=inward_sign,
        )
        gww = _footprint_width("garage")
        gdd = _footprint_depth("garage")
        gmin_x, gmax_x = gx - gww * 0.5, gx + gww * 0.5
        gmin_y, gmax_y = gy - gdd * 0.5, gy + gdd * 0.5
        if not roads.hits_footprint(gmin_x, gmin_y, gmax_x, gmax_y) and not _in_void(gx, gy):
            # Garage body is itself a silhouette — stamp body into detail LOD bucket.
            gtmp = _template_for("garage", gx, gy)
            _stamp(gtmp, detail_parent, detail_parent, gx, gy, heading, include_detail=True)
    return True


def _try_place_plaza(
    *,
    body_parent: NodePath,
    detail_parent: NodePath,
    roads: _RoadIndex,
    street_x: float | None,
    street_y: float | None,
    along0: float,
    along1: float,
    inward_sign: float,
    heading: float,
    clear: float,
    include_detail: bool = True,
) -> bool:
    """Place one strip-mall plaza centred on a suburban arterial block face."""
    span = along1 - along0
    if span < 0.90:
        return False
    mid = 0.5 * (along0 + along1)
    # Pick plaza width that fits the face.
    for w in (1.40, 1.10, 0.85):
        if w <= span - 0.10:
            break
    else:
        w = min(0.85, span * 0.85)
    depth = 0.28
    setback = 0.35  # behind asphalt parking lot
    cx, cy, min_x, min_y, max_x, max_y = _house_bounds(
        street_x=street_x,
        street_y=street_y,
        mid=mid,
        inward_sign=inward_sign,
        setback=setback,
        clear=clear,
        width=w,
        depth=depth,
    )
    if _in_loop(cx, cy) or _in_void(cx, cy):
        return False
    if roads.hits_footprint(min_x, min_y, max_x, max_y):
        return False
    # Override footprint temporarily for the chosen width.
    i = 0 if w < 0.95 else (1 if w < 1.25 else 2)
    template = _TEMPLATES[f"plaza_{i}"]
    _stamp(
        template,
        body_parent,
        detail_parent,
        cx,
        cy,
        heading,
        include_detail=include_detail,
    )
    return True


def _place_frontage(
    *,
    body_parent: NodePath,
    detail_parent: NodePath,
    roads: _RoadIndex,
    street_x: float | None,
    street_y: float | None,
    along0: float,
    along1: float,
    inward_sign: float,
    heading: float,
    corner_wide: bool,
    include_detail: bool = True,
) -> int:
    """Place lots along one street face of a half-block. Returns house count."""
    span = along1 - along0
    if span < INNER_LOT_W * 1.5:
        return 0
    if street_y is not None and not roads.has_street_y(street_y):
        return 0
    if street_x is not None and not roads.has_street_x(street_x):
        return 0

    margin = CLEAR_MINOR
    a0 = along0 + margin
    a1 = along1 - margin
    if a1 <= a0 + INNER_LOT_W:
        return 0

    if street_y is not None:
        clear = max(CLEAR_MINOR, roads.road_width_at_y(street_y) * 0.5 + 0.08)
        arterial_face = roads.is_suburban_arterial(y=street_y)
    else:
        assert street_x is not None
        clear = max(CLEAR_MINOR, roads.road_width_at_x(street_x) * 0.5 + 0.08)
        arterial_face = roads.is_suburban_arterial(x=street_x)

    # Probe zone at frontage mid-span.
    probe_mid = 0.5 * (a0 + a1)
    if street_y is not None:
        probe_x, probe_y = probe_mid, street_y + inward_sign * (clear + INNER_SETBACK)
    else:
        probe_x, probe_y = street_x + inward_sign * (clear + INNER_SETBACK), probe_mid
    zone = _zone_of(probe_x, probe_y)
    if zone == "none":
        return 0

    # Suburban arterial strip plazas — 30% of block faces.
    if zone == "suburb" and arterial_face:
        if _hash01(probe_x, probe_y, 7.5) < PLAZA_FACE_CHANCE:
            _ensure_templates()
            return 1 if _try_place_plaza(
                body_parent=body_parent,
                detail_parent=detail_parent,
                roads=roads,
                street_x=street_x,
                street_y=street_y,
                along0=a0,
                along1=a1,
                inward_sign=inward_sign,
                heading=heading,
                clear=clear,
                include_detail=include_detail,
            ) else 0

    count = 0
    cursor = a0
    first = True

    def _front_xy(mid: float, setback: float) -> tuple[float, float]:
        if street_y is not None:
            return mid, street_y + inward_sign * (clear + setback)
        assert street_x is not None
        return street_x + inward_sign * (clear + setback), mid

    def _place_attached_run() -> None:
        """Zero-lot-line clusters of 4–8 with a 0.04 gangway between runs."""
        nonlocal count, cursor, first
        while cursor + INNER_LOT_W * 0.5 <= a1 + 1e-6:
            if zone == "blend":
                peek_x, peek_y = _front_xy(cursor + INNER_LOT_W * 0.5, INNER_SETBACK)
                if not _is_attached_kind(_pick_archetype(peek_x, peek_y)):
                    return
            cluster_n = INNER_CLUSTER_MIN + int(
                _hash01(cursor, probe_y if street_y is not None else probe_x, 9.0)
                * (INNER_CLUSTER_MAX - INNER_CLUSTER_MIN + 1)
            )
            cluster_n = max(INNER_CLUSTER_MIN, min(INNER_CLUSTER_MAX, cluster_n))
            placed_in_cluster = 0
            for _i in range(cluster_n):
                if cursor + INNER_LOT_W * 0.5 > a1 + 1e-6:
                    break
                lx, ly = _front_xy(cursor + INNER_LOT_W * 0.5, INNER_SETBACK)
                if _hash01(lx, ly, 6.0) > _lot_fill(lx, ly):
                    cursor += INNER_LOT_W
                    first = False
                    continue
                is_corner = first or (cursor + INNER_LOT_W * 2 > a1)
                kind = (
                    "storefront"
                    if (corner_wide and is_corner)
                    else (_pick_inner(lx, ly) if zone != "outer" else _pick_archetype(lx, ly))
                )
                width = _footprint_width(kind)
                step = width if _is_attached_kind(kind) else width + INNER_GANGWAY
                if cursor + width > a1 + 1e-6:
                    break
                mid = cursor + width * 0.5
                if _try_place(
                    body_parent=body_parent,
                    detail_parent=detail_parent,
                    roads=roads,
                    street_x=street_x,
                    street_y=street_y,
                    mid=mid,
                    inward_sign=inward_sign,
                    heading=heading,
                    kind=kind,
                    setback=INNER_SETBACK,
                    clear=clear,
                    use_alley=True,
                    include_detail=include_detail,
                ):
                    count += 1
                    placed_in_cluster += 1
                cursor += step
                first = False
            if placed_in_cluster > 0:
                cursor += INNER_GANGWAY
            else:
                cursor += INNER_LOT_W

    def _place_detached_one() -> bool:
        """One wider suburban / outer lot; returns False when frontage is exhausted."""
        nonlocal count, cursor, first
        lot_w = OUTER_LOT_W0 + (OUTER_LOT_W1 - OUTER_LOT_W0) * _hash01(
            cursor, probe_y if street_y is not None else probe_x, 10.0
        )
        if cursor + lot_w > a1 + 1e-6:
            lot_w = a1 - cursor
            if lot_w < OUTER_LOT_W0 * 0.75:
                return False
        mid = cursor + lot_w * 0.5
        setback = _suburb_setback(mid, probe_y if street_y is not None else probe_x)
        if zone in ("outer", "blend"):
            setback = min(setback, 0.22 + 0.04 * _hash01(mid, setback, 4.1))
        lx, ly = _front_xy(mid, setback)
        if _in_loop(lx, ly) or _in_void(lx, ly):
            cursor += lot_w
            first = False
            return True
        if _hash01(lx, ly, 6.0) > _lot_fill(lx, ly):
            cursor += lot_w
            first = False
            return True
        is_corner = first or (cursor + lot_w * 2 > a1)
        if zone == "suburb":
            kind = "storefront" if (corner_wide and is_corner and not arterial_face) else _pick_suburb(lx, ly)
        else:
            kind = "storefront" if (corner_wide and is_corner) else _pick_outer_city(lx, ly)
        # Enforce house width + side-yard gap within the lot.
        side_gap = OUTER_SIDE_GAP0 + (OUTER_SIDE_GAP1 - OUTER_SIDE_GAP0) * _hash01(lx, ly, 10.5)
        if _footprint_width(kind) + side_gap > lot_w and kind != "storefront":
            # Prefer a narrower archetype that still fits with a grass gap.
            for fallback in ("colonial", "bungalow", "foursquare"):
                if _footprint_width(fallback) + OUTER_SIDE_GAP0 <= lot_w:
                    kind = fallback
                    break
        use_alley = _uses_rear_alley(lx, ly)
        with_garage = (
            use_alley
            and kind not in ("storefront", "ranch", "split_level", "colonial", "plaza")
            and _hash01(lx, ly, 11.0) < GARAGE_CHANCE
        )
        if _try_place(
            body_parent=body_parent,
            detail_parent=detail_parent,
            roads=roads,
            street_x=street_x,
            street_y=street_y,
            mid=mid,
            inward_sign=inward_sign,
            heading=heading,
            kind=kind,
            setback=setback,
            clear=clear,
            with_garage=with_garage,
            use_alley=use_alley,
            include_detail=include_detail,
        ):
            count += 1
        cursor += lot_w
        first = False
        return True

    if zone == "inner":
        _place_attached_run()
        return count

    if zone == "blend":
        while cursor + INNER_LOT_W * 0.5 <= a1 + 1e-6:
            lx, ly = _front_xy(cursor + INNER_LOT_W * 0.5, INNER_SETBACK)
            if _is_attached_kind(_pick_archetype(lx, ly)):
                before = cursor
                _place_attached_run()
                if cursor <= before + 1e-6:
                    cursor += INNER_LOT_W
            else:
                if not _place_detached_one():
                    break
        return count

    # Outer city + suburbs — fully detached belt.
    while cursor + OUTER_LOT_W0 * 0.5 <= a1 + 1e-6:
        if not _place_detached_one():
            break
    return count


def _fill_cell(
    body_parent: NodePath,
    detail_parent: NodePath,
    roads: _RoadIndex,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    include_detail: bool = True,
) -> int:
    """Fill one BLOCK_100 cell as two half-blocks split by a rear alley."""
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    if _zone_of(cx, cy) == "none":
        return 0
    if roads.hits_point(cx, cy, radius=0.35):
        return 0

    wide_south = roads.is_wide_frontage(y=y0)
    wide_north = roads.is_wide_frontage(y=y1)
    section = int(math.floor(cx / UNITS_PER_MILE) + math.floor(cy / UNITS_PER_MILE))
    ns_lots = section % 2 == 0

    total = 0
    if ns_lots:
        total += _place_frontage(
            body_parent=body_parent,
            detail_parent=detail_parent,
            roads=roads,
            street_x=None,
            street_y=y0,
            along0=x0,
            along1=x1,
            inward_sign=1.0,
            heading=0.0,
            corner_wide=wide_south,
            include_detail=include_detail,
        )
        total += _place_frontage(
            body_parent=body_parent,
            detail_parent=detail_parent,
            roads=roads,
            street_x=None,
            street_y=y1,
            along0=x0,
            along1=x1,
            inward_sign=-1.0,
            heading=180.0,
            corner_wide=wide_north,
            include_detail=include_detail,
        )
    else:
        wide_west = roads.is_wide_frontage(x=x0)
        wide_east = roads.is_wide_frontage(x=x1)
        total += _place_frontage(
            body_parent=body_parent,
            detail_parent=detail_parent,
            roads=roads,
            street_x=x0,
            street_y=None,
            along0=y0,
            along1=y1,
            inward_sign=1.0,
            heading=-90.0,
            corner_wide=wide_west,
            include_detail=include_detail,
        )
        total += _place_frontage(
            body_parent=body_parent,
            detail_parent=detail_parent,
            roads=roads,
            street_x=x1,
            street_y=None,
            along0=y0,
            along1=y1,
            inward_sign=-1.0,
            heading=90.0,
            corner_wide=wide_east,
            include_detail=include_detail,
        )
    return total


# ---------------------------------------------------------------------------
# Sector bake / streaming
# ---------------------------------------------------------------------------
def _collect_cells(
    x0b: float, x1b: float, y0b: float, y1b: float
) -> dict[tuple[int, int], list[tuple[float, float, float, float]]]:
    ix0 = int(math.floor(x0b / BLOCK_100))
    ix1 = int(math.floor(x1b / BLOCK_100)) + 1
    iy0 = int(math.floor(y0b / BLOCK_100))
    iy1 = int(math.floor(y1b / BLOCK_100)) + 1
    cells_by_sector: dict[tuple[int, int], list[tuple[float, float, float, float]]] = {}
    for ix in range(ix0, ix1):
        x0 = ix * BLOCK_100
        x1 = x0 + BLOCK_100
        if x1 < x0b or x0 > x1b:
            continue
        for iy in range(iy0, iy1):
            y0 = iy * BLOCK_100
            y1 = y0 + BLOCK_100
            if y1 < y0b or y0 > y1b:
                continue
            cx = x0 + 0.5 * BLOCK_100
            cy = y0 + 0.5 * BLOCK_100
            if _zone_of(cx, cy) == "none":
                continue
            sx = int(math.floor(cx / SECTOR_SIZE))
            sy = int(math.floor(cy / SECTOR_SIZE))
            cells_by_sector.setdefault((sx, sy), []).append((x0, y0, x1, y1))
    return cells_by_sector


def _bake_sector(
    root: NodePath,
    roads: _RoadIndex,
    sx: int,
    sy: int,
    cells: list[tuple[float, float, float, float]],
    *,
    include_detail: bool = True,
) -> tuple[float, float, NodePath, int] | None:
    """Generate + flatten one mile-sector (blocking). Used for startup only."""
    job = _begin_sector_job(root, roads, sx, sy, cells, include_detail=include_detail)
    while not _advance_sector_job(job, budget_s=1.0e6):
        pass
    return _finish_sector_job(job)


def _begin_sector_job(
    root: NodePath,
    roads: _RoadIndex,
    sx: int,
    sy: int,
    cells: list[tuple[float, float, float, float]],
    *,
    include_detail: bool = True,
) -> dict[str, Any]:
    """Allocate an empty sector node and return a resumable bake job."""
    cx = (sx + 0.5) * SECTOR_SIZE
    cy = (sy + 0.5) * SECTOR_SIZE
    suburb = _in_suburb(cx, cy)
    name = f"suburb_housing_sector_{sx}_{sy}" if suburb else f"housing_sector_{sx}_{sy}"
    sector = root.attachNewNode(name)
    body_mesh = sector.attachNewNode("body")
    lod = LODNode(f"detail_lod_{sx}_{sy}")
    lod_np = sector.attachNewNode(lod)
    detail_mesh = lod_np.attachNewNode("detail")
    lod_np.attachNewNode("detail_far_empty")
    lod.addSwitch(DETAIL_LOD_FAR, 0.0)
    lod.addSwitch(1.0e6, DETAIL_LOD_FAR)
    sector.hide()
    return {
        "sx": sx,
        "sy": sy,
        "cx": cx,
        "cy": cy,
        "cells": cells,
        "cell_i": 0,
        "sector": sector,
        "body": body_mesh,
        "detail": detail_mesh,
        "roads": roads,
        "placed": 0,
        "since_flatten": 0,
        "include_detail": include_detail,
        "done": False,
    }


def _advance_sector_job(job: dict[str, Any], *, budget_s: float) -> bool:
    """Fill cells until ``budget_s`` elapses. Returns True when cells are done."""
    if job["done"]:
        return True
    body: NodePath = job["body"]
    detail: NodePath = job["detail"]
    roads: _RoadIndex = job["roads"]
    cells: list = job["cells"]
    include_detail = bool(job["include_detail"])
    t_end = time.perf_counter() + budget_s
    while job["cell_i"] < len(cells):
        x0, y0, x1, y1 = cells[job["cell_i"]]
        job["cell_i"] += 1
        if _in_void(0.5 * (x0 + x1), 0.5 * (y0 + y1)):
            if time.perf_counter() >= t_end:
                return False
            continue
        n = _fill_cell(
            body, detail, roads, x0, y0, x1, y1, include_detail=include_detail
        )
        job["placed"] += n
        job["since_flatten"] += n
        if job["since_flatten"] >= STREAM_FLATTEN_EVERY:
            body.flattenStrong()
            if include_detail:
                detail.flattenStrong()
            job["since_flatten"] = 0
            # Always yield after flatten — it's the hitchy part.
            return False
        if time.perf_counter() >= t_end:
            return False
    job["done"] = True
    return True


def _finish_sector_job(
    job: dict[str, Any],
) -> tuple[float, float, NodePath, int] | None:
    """Final flatten + publish, or discard an empty sector."""
    sector: NodePath = job["sector"]
    body: NodePath = job["body"]
    detail: NodePath = job["detail"]
    placed = int(job["placed"])
    if placed <= 0:
        sector.removeNode()
        return None
    # Flatten any leftover instances from the last incomplete chunk.
    if int(job["since_flatten"]) > 0:
        body.flattenStrong()
        if job["include_detail"]:
            detail.flattenStrong()
        job["since_flatten"] = 0
    if not job["include_detail"] and not detail.isEmpty():
        detail.removeNode()
    sector.hide()
    return float(job["cx"]), float(job["cy"]), sector, placed


def _publish_finished_job(
    job: dict[str, Any],
    tiles: list[tuple[float, float, NodePath]],
    pending: dict[tuple[int, int], list],
    built: set[tuple[int, int]],
    root: NodePath,
) -> int:
    result = _finish_sector_job(job)
    _STREAM["job"] = None
    key = (int(job["sx"]), int(job["sy"]))
    built.add(key)
    added = 0
    if result is not None:
        cx, cy, sector, placed = result
        tiles.append((cx, cy, sector))
        _STREAM["house_count"] = int(_STREAM.get("house_count", 0)) + placed
        added = 1
        print(
            "[housing] streamed suburb sector %d,%d → %d houses (%d pending)"
            % (key[0], key[1], placed, len(pending))
        )
    root.setTag("house_count", str(int(_STREAM.get("house_count", 0))))
    root.setTag("sector_count", str(len(tiles)))
    return added


def ensure_housing_sectors(
    look_x: float,
    look_y: float,
    radius: float,
    tiles: list[tuple[float, float, NodePath]],
    *,
    max_new: int = 1,
) -> int:
    """Time-slice suburban sector bakes near the look point.

    At most one sector is in flight. Each call spends up to ``STREAM_BUDGET_S``
    so entering a new area no longer hitch-bakes a full mile of houses on one
    frame. Prefetch starts outside the visible radius so sectors finish before
    they are shown. Final flatten runs on its own tick after cells complete.
    """
    del max_new  # single in-flight job; kept for call-site compatibility
    pending: dict[tuple[int, int], list] = _STREAM.get("pending") or {}
    root: NodePath | None = _STREAM.get("root")
    roads: _RoadIndex | None = _STREAM.get("roads")
    built: set[tuple[int, int]] = _STREAM.setdefault("built", set())
    if root is None or roads is None:
        return 0

    job: dict[str, Any] | None = _STREAM.get("job")

    # Finalize on a dedicated tick so the last flatten isn't stacked on fill work.
    if job is not None and job.get("needs_finalize"):
        return _publish_finished_job(job, tiles, pending, built, root)

    if job is not None:
        finished = _advance_sector_job(job, budget_s=STREAM_BUDGET_S)
        if finished:
            job["needs_finalize"] = True
        return 0

    if not pending:
        return 0

    # Prefetch beyond the visible radius so work finishes before arrival.
    prefetch_r = radius + STREAM_PREFETCH
    r2 = prefetch_r * prefetch_r
    scored: list[tuple[float, tuple[int, int]]] = []
    for key in pending:
        if key in built:
            continue
        sx, sy = key
        cx = (sx + 0.5) * SECTOR_SIZE
        cy = (sy + 0.5) * SECTOR_SIZE
        d2 = (cx - look_x) ** 2 + (cy - look_y) ** 2
        if d2 <= r2:
            scored.append((d2, key))
    if not scored:
        return 0
    scored.sort(key=lambda item: item[0])
    _d2, key = scored[0]
    cells = pending.pop(key, None)
    if not cells:
        return 0

    # Body-only stream — silhouettes stay; detail LOD stays empty (no hitch).
    job = _begin_sector_job(root, roads, key[0], key[1], cells, include_detail=False)
    _STREAM["job"] = job
    finished = _advance_sector_job(job, budget_s=STREAM_BUDGET_S)
    if finished:
        job["needs_finalize"] = True
    return 0


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
def build_chicago_housing(
    parent: NodePath,
    plan: CityPlan,
    arterials: list[dict[str, Any]],
) -> tuple[list[tuple[float, float, NodePath]], list[tuple[float, float, NodePath]]]:
    """Generate residential fabric. Returns ``(sector_tiles, [])``.

    Zone 1 (dense inner city) bakes at startup. Suburban mile-sectors outside
    the city borders are catalogued and streamed via :func:`ensure_housing_sectors`
    as the camera approaches — each sector is ``flattenStrong``'d and detail sits
    under an LODNode that drops past ``DETAIL_LOD_FAR``.
    """
    del plan  # roads come from arterials; plan kept for API symmetry with signals
    roads = _RoadIndex(arterials)

    root = parent.attachNewNode("chicago_housing")
    pool = root.attachNewNode("templates")
    _ensure_templates(pool)

    # Startup: dense Zone 1 box only.
    startup_cells = _collect_cells(
        HOUSING_BUILD_X0, HOUSING_BUILD_X1, HOUSING_BUILD_Y0, HOUSING_BUILD_Y1
    )

    # Deferred: full suburban plate minus sectors already covered by startup.
    all_cells = _collect_cells(
        SUBURB_BUILD_X0, SUBURB_BUILD_X1, SUBURB_BUILD_Y0, SUBURB_BUILD_Y1
    )
    pending: dict[tuple[int, int], list[tuple[float, float, float, float]]] = {}
    for key, cells in all_cells.items():
        if key in startup_cells:
            continue
        # Only defer true suburban (or outer-city fringe) sectors.
        sx, sy = key
        cx = (sx + 0.5) * SECTOR_SIZE
        cy = (sy + 0.5) * SECTOR_SIZE
        zone = _zone_of(cx, cy)
        if zone in ("suburb", "outer", "blend"):
            pending[key] = cells

    total_houses = 0
    body_tiles: list[tuple[float, float, NodePath]] = []
    built: set[tuple[int, int]] = set()
    for (sx, sy), cells in startup_cells.items():
        result = _bake_sector(root, roads, sx, sy, cells)
        built.add((sx, sy))
        if result is None:
            continue
        cx, cy, sector, placed = result
        body_tiles.append((cx, cy, sector))
        total_houses += placed

    _STREAM.clear()
    _STREAM.update(
        {
            "root": root,
            "roads": roads,
            "pending": pending,
            "built": built,
            "house_count": total_houses,
            "tiles": body_tiles,
        }
    )

    root.setTag("house_count", str(total_houses))
    root.setTag("sector_count", str(len(body_tiles)))
    root.setTag("suburb_pending", str(len(pending)))
    print(
        "[housing] %d houses → %d flattened mile-sectors "
        "(startup box %.0f..%.0f × %.0f..%.0f; %d suburb sectors deferred)"
        % (
            total_houses,
            len(body_tiles),
            HOUSING_BUILD_X0,
            HOUSING_BUILD_X1,
            HOUSING_BUILD_Y0,
            HOUSING_BUILD_Y1,
            len(pending),
        )
    )
    return body_tiles, []
