"""Chicago, IL — geographic arterial layout (roads-only plate).

Highways are open polylines on the Chicago address grid (State & Madison
origin) plus radial expressways and signature diagonals. Neighborhoods are
local lot grids that may be rotated to follow nearby corridors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml

DEFAULT_CITY_YAML = Path(__file__).resolve().parent / "data" / "city.yaml"


@dataclass(frozen=True)
class TowerLot:
    west_face: float
    y_offset: float
    eastern_road: bool
    southern_road: bool
    empty: bool


@dataclass(frozen=True)
class HousingLot:
    west_face: float
    y_offset: float
    lot_width: float
    lot_depth: float
    eastern_road: bool
    southern_road: bool
    northern_road: bool
    houses_across: int
    houses_deep: int


@dataclass(frozen=True)
class Neighborhood:
    name: str
    kind: str
    origin_x: float
    origin_y: float
    heading_deg: float
    cols: int
    rows: int


@dataclass(frozen=True)
class StreetRoute:
    """Local residential centreline with optional cul-de-sac bulbs."""

    name: str
    points: tuple[tuple[float, float], ...]
    bulb_start: bool = False
    bulb_end: bool = False
    bulb_radius: float | None = None


@dataclass(frozen=True)
class HighwayRoute:
    """Arterial centreline with a per-route lane count and optional width."""

    name: str
    points: tuple[tuple[float, float], ...]
    lanes: int
    z_offset: float = 0.0
    width: float | None = None
    layer: str = "arterial"


@dataclass(frozen=True)
class CityPlan:
    """Chicago neighborhoods, lot metrics, and geographic highway polylines."""

    block_size: tuple[float, float, float]
    tower_count: int
    tower_gap: float
    road_width: float
    floor_min: int
    floor_max: int
    towers_per_ring: int

    highway_lanes: int
    fence_w: float
    fence_h: float
    barrier_w: float
    barrier_h: float
    highway_keepout: float
    highway_routes: tuple[HighwayRoute, ...]
    street_routes: tuple[StreetRoute, ...]
    neighborhoods: tuple[Neighborhood, ...]

    @property
    def highway_polylines(self) -> tuple[tuple[str, tuple[tuple[float, float], ...]], ...]:
        """Compatibility view: ``(name, points)`` pairs."""
        return tuple((route.name, route.points) for route in self.highway_routes)

    road_left: float
    road_right: float
    road_length: float
    road_depth: float
    stride_x: float
    stride_y: float
    lot_width: float
    road_top: float
    south_road0: float
    west_road0: float
    south_road_full0: float
    west_road_full0: float
    south_face: float
    city_west_edge: float
    tallest: int

    # Compatibility for car/signal helpers that still expect a host grid.
    cols: int
    rows: int
    north_shift: float
    north_shift_lots: int
    exit_row: int
    between_housing_rows: int
    grid: int
    housing_cols: int
    housing_rows: int
    factory_rows: int
    factory_cols: int
    west_housing_cols: int
    west_housing_rows: int
    east_factory_cols: int
    east_factory_rows: int
    tower_west: float
    housing_south: int
    west_housing_cols_count: int
    west_cols: int
    east_cols: int
    south_rows: int
    north_rows: int
    arterial_gap_x: float
    arterial_gap_y: float
    gap_after_v: tuple[int, ...]
    gap_after_h: tuple[int, ...]
    road_xs_list: tuple[float, ...]
    road_ys_list: tuple[float, ...]

    def grid_x(self, v: int) -> float:
        return self.road_xs_list[min(max(v, 0), len(self.road_xs_list) - 1)]

    def grid_y(self, h: int) -> float:
        return self.road_ys_list[min(max(h, 0), len(self.road_ys_list) - 1)]

    def road_xs(self) -> list[float]:
        return list(self.road_xs_list)

    def road_ys(self) -> list[float]:
        return list(self.road_ys_list)

    def crosses_arterial(self, v0: int, h0: int, v1: int, h1: int) -> bool:
        return False

    def solid_lot(self, brow: int, bcol: int) -> bool:
        return False

    def local_to_world(
        self, neighborhood: Neighborhood, lx: float, ly: float
    ) -> tuple[float, float]:
        rad = math.radians(neighborhood.heading_deg)
        c = math.cos(rad)
        s = math.sin(rad)
        return (
            neighborhood.origin_x + lx * c - ly * s,
            neighborhood.origin_y + lx * s + ly * c,
        )

    def lot_local_west_face(self, col: int) -> float:
        return col * self.stride_x + self.road_width / 2

    def lot_local_y_offset(self, row: int) -> float:
        return row * self.stride_y

    def highway_half_width(self) -> float:
        return self.highway_lanes * (self.road_width / 2) / 2

    def point_near_highway(self, x: float, y: float, clearance: float | None = None) -> bool:
        clear = self.highway_keepout if clearance is None else clearance
        clear2 = clear * clear
        for _name, points in self.highway_polylines:
            for i in range(len(points) - 1):
                ax, ay = points[i]
                bx, by = points[i + 1]
                if _dist2_point_segment(x, y, ax, ay, bx, by) <= clear2:
                    return True
        return False

    def lot_hits_highway(
        self,
        neighborhood: Neighborhood,
        west_face: float,
        y_offset: float,
        *,
        lot_width: float | None = None,
        lot_depth: float | None = None,
    ) -> bool:
        """True if the lot lawn + street apron would overlap a highway ribbon."""
        width = self.lot_width if lot_width is None else lot_width
        depth = self.road_depth if lot_depth is None else lot_depth
        # Lawn footprint only — local streets may approach arterials, houses may not.
        local_corners = (
            (west_face, y_offset),
            (west_face + width, y_offset),
            (west_face + width, y_offset + depth),
            (west_face, y_offset + depth),
        )
        world = [self.local_to_world(neighborhood, lx, ly) for lx, ly in local_corners]
        xs = [p[0] for p in world]
        ys = [p[1] for p in world]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        # Stay outside the paved highway half-width plus YAML keepout margin.
        clear = self.highway_half_width() + self.highway_keepout
        clear2 = clear * clear
        for _name, points in self.highway_polylines:
            for i in range(len(points) - 1):
                ax, ay = points[i]
                bx, by = points[i + 1]
                if _dist2_aabb_segment(min_x, min_y, max_x, max_y, ax, ay, bx, by) <= clear2:
                    return True
        return False

    def iter_neighborhood_lots(
        self, neighborhood: Neighborhood
    ) -> Iterator[tuple[str, TowerLot | HousingLot]]:
        """Yield ``(kind, lot)`` in neighborhood-local coordinates."""
        for row in range(neighborhood.rows):
            for col in range(neighborhood.cols):
                west = self.lot_local_west_face(col)
                y_off = self.lot_local_y_offset(row)
                if self.lot_hits_highway(neighborhood, west, y_off):
                    continue
                eastern = col == neighborhood.cols - 1
                southern = row == 0
                if neighborhood.kind == "tower":
                    yield (
                        "tower",
                        TowerLot(
                            west_face=west,
                            y_offset=y_off,
                            eastern_road=eastern,
                            southern_road=southern,
                            empty=False,
                        ),
                    )
                elif neighborhood.kind == "factory":
                    yield (
                        "factory",
                        TowerLot(
                            west_face=west,
                            y_offset=y_off,
                            eastern_road=eastern,
                            southern_road=southern,
                            empty=True,
                        ),
                    )
                else:
                    yield (
                        "housing",
                        HousingLot(
                            west_face=west,
                            y_offset=y_off,
                            lot_width=self.lot_width,
                            lot_depth=self.road_depth,
                            eastern_road=eastern,
                            southern_road=southern,
                            northern_road=True,
                            houses_across=6,
                            houses_deep=2,
                        ),
                    )

    # Empty legacy iterators — assembly uses neighborhoods instead.
    def iter_tower_lots(self) -> Iterator[TowerLot]:
        return iter(())

    def iter_factory_lots(self) -> Iterator[TowerLot]:
        return iter(())

    def iter_housing_lots(self) -> Iterator[HousingLot]:
        return iter(())

    def iter_north_housing_lots(self) -> Iterator[HousingLot]:
        return iter(())

    def iter_west_housing_lots(self) -> Iterator[HousingLot]:
        return iter(())

    def iter_south_factory_lots(self) -> Iterator[TowerLot]:
        return iter(())

    def iter_east_factory_lots(self) -> Iterator[TowerLot]:
        return iter(())

    def iter_between_housing_lots(self) -> Iterator[HousingLot]:
        return iter(())

    def highway_geometry(self) -> dict[str, Any]:
        lane_width = self.road_width / 2
        highway_width = self.highway_lanes * lane_width
        road_thickness = 0.1
        # Coplanar road network at Z = 0 (minor thickness only).
        road_z = 0.0
        bridge_clearance = self.barrier_h + 2.8
        bridge_z = road_z + bridge_clearance
        # Chaikin + Catmull-Rom → ~25–30 samples per control span (no faceting).
        sample_spacing = max(1.4, highway_width * 1.2)

        arterials: list[dict[str, Any]] = []
        xs: list[float] = []
        ys: list[float] = []
        for route in self.highway_routes:
            lanes = max(2, int(route.lanes))
            width = float(route.width) if route.width is not None else lanes * lane_width
            control = route.points
            bent = not _is_axis_aligned(control)
            # Axis-aligned ribbons keep endpoints only — critical for dense minor grids.
            if bent:
                refined = _chaikin(control, iterations=2)
                chords = [
                    math.hypot(
                        control[i + 1][0] - control[i][0],
                        control[i + 1][1] - control[i][1],
                    )
                    for i in range(len(control) - 1)
                ]
                mean_chord = sum(chords) / len(chords) if chords else 1.0
                spacing = max(0.9, mean_chord / 28.0)
                smooth = tuple(_smooth_polyline(refined, spacing))
            else:
                smooth = control
            arterials.append(
                {
                    "name": route.name,
                    "points": smooth,
                    "control_points": route.points,
                    "axis": "poly",
                    "lanes": lanes,
                    "width": width,
                    "z_offset": float(route.z_offset),
                    "layer": str(route.layer or "arterial"),
                }
            )
            for x, y in smooth:
                xs.append(x)
                ys.append(y)

        pad = highway_width + 40.0
        return {
            "lane_width": lane_width,
            "highway_width": highway_width,
            "road_thickness": road_thickness,
            "road_z": road_z,
            "bridge_clearance": bridge_clearance,
            "bridge_z": bridge_z,
            "arterials": tuple(arterials),
            "diamonds": (),
            "bounds_west": min(xs) - pad,
            "bounds_east": max(xs) + pad,
            "bounds_south": min(ys) - pad,
            "bounds_north": max(ys) + pad,
            "west_lane_xs": [],
            "east_lane_xs": [],
            "south_lane_ys": [],
            "north_lane_ys": [],
            "ns_y0": min(ys),
            "ns_y1": max(ys),
            "ew_x0": min(xs),
            "ew_x1": max(xs),
            "corner_nw": (0.0, 0.0),
            "corner_ne": (0.0, 0.0),
            "corner_se": (0.0, 0.0),
            "corner_sw": (0.0, 0.0),
            "belt_west_outer": min(xs) - pad,
            "belt_east_outer": max(xs) + pad,
            "belt_south_outer": min(ys) - pad,
            "belt_north_outer": max(ys) + pad,
            "opening_half": highway_width * 0.85,
        }

    def street_geometry(self) -> dict[str, Any]:
        """Local residential ribbons — narrower than highways, same smoothing."""
        street_width = self.road_width
        road_thickness = 0.1
        road_z = 0.0
        sample_spacing = max(0.9, street_width * 0.18)
        default_bulb = street_width * 1.55
        routes: list[dict[str, Any]] = []
        bulbs: list[tuple[float, float, float]] = []
        for route in self.street_routes:
            radius = route.bulb_radius if route.bulb_radius is not None else default_bulb
            # Straight runs stay crisp; only bend control polylines get Chaikin.
            if _is_axis_aligned(route.points):
                stem = tuple(_smooth_polyline(route.points, sample_spacing))
            else:
                stem = tuple(
                    _smooth_polyline(
                        _chaikin(route.points, iterations=2), sample_spacing
                    )
                )
            if route.bulb_start:
                bulbs.append(_cul_de_sac_center(stem, at_start=True, radius=radius))
            if route.bulb_end:
                bulbs.append(_cul_de_sac_center(stem, at_start=False, radius=radius))
            routes.append(
                {
                    "name": route.name,
                    "points": stem,
                    "control_points": route.points,
                }
            )
        return {
            "street_width": street_width,
            "road_thickness": road_thickness,
            "road_z": road_z,
            "routes": tuple(routes),
            "bulbs": tuple(bulbs),
        }

    def framing_bounds(self) -> dict[str, float]:
        hwy = self.highway_geometry()
        stack_bottom = -self.block_size[2] / 2
        stack_top = (self.tallest - 1) * self.block_size[2] + self.block_size[2] / 2
        return {
            "left": hwy["bounds_west"],
            "right": hwy["bounds_east"],
            "city_south": hwy["bounds_south"],
            "city_north": hwy["bounds_north"],
            "stack_bottom": stack_bottom,
            "stack_top": stack_top,
        }


def _is_axis_aligned(points: tuple[tuple[float, float], ...]) -> bool:
    """True when every segment is horizontal or vertical (within a hair)."""
    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        if abs(x1 - x0) > 1e-6 and abs(y1 - y0) > 1e-6:
            return False
    return len(points) >= 2


def _cul_de_sac_center(
    points: tuple[tuple[float, float], ...],
    *,
    at_start: bool,
    radius: float,
) -> tuple[float, float, float]:
    """World-space disc centre for a cul-de-sac pad at a stem tip."""
    if at_start:
        x_end, y_end = points[0]
        x_prev, y_prev = points[1]
    else:
        x_end, y_end = points[-1]
        x_prev, y_prev = points[-2]
    dx = x_end - x_prev
    dy = y_end - y_prev
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    # Pull the pad slightly past the tip so the stem meets the disc cleanly.
    inset = radius * 0.35
    return (x_end + ux * inset, y_end + uy * inset, radius)


def _chaikin(
    points: tuple[tuple[float, float], ...],
    *,
    iterations: int = 2,
) -> tuple[tuple[float, float], ...]:
    """Corner-cutting subdivision — softens polyline joints before splining."""
    if len(points) < 3 or iterations <= 0:
        return points
    pts = list(points)
    for _ in range(iterations):
        nxt: list[tuple[float, float]] = [pts[0]]
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            nxt.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            nxt.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        nxt.append(pts[-1])
        pts = nxt
    return tuple(pts)


def _catmull_rom(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    """Uniform cubic Catmull-Rom between p1→p2."""
    t2 = t * t
    t3 = t2 * t
    x = 0.5 * (
        (2.0 * p1[0])
        + (-p0[0] + p2[0]) * t
        + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2
        + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3
    )
    y = 0.5 * (
        (2.0 * p1[1])
        + (-p0[1] + p2[1]) * t
        + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2
        + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
    )
    return (x, y)


def _smooth_polyline(
    points: tuple[tuple[float, float], ...],
    spacing: float,
) -> list[tuple[float, float]]:
    """Densify a control polyline with Catmull-Rom curves between vertices."""
    n = len(points)
    if n < 2:
        return list(points)
    if n == 2:
        x0, y0 = points[0]
        x1, y1 = points[1]
        chord = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, int(math.ceil(chord / max(spacing, 0.5))))
        return [
            (x0 + (x1 - x0) * (s / steps), y0 + (y1 - y0) * (s / steps))
            for s in range(steps + 1)
        ]

    def at(i: int) -> tuple[float, float]:
        if i < 0:
            # Reflect past the start so the first span still curves naturally.
            return (
                points[0][0] - (points[1][0] - points[0][0]),
                points[0][1] - (points[1][1] - points[0][1]),
            )
        if i >= n:
            return (
                points[-1][0] + (points[-1][0] - points[-2][0]),
                points[-1][1] + (points[-1][1] - points[-2][1]),
            )
        return points[i]

    out: list[tuple[float, float]] = [points[0]]
    for i in range(n - 1):
        p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
        chord = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        steps = max(1, int(math.ceil(chord / max(spacing, 0.5))))
        for step in range(1, steps + 1):
            out.append(_catmull_rom(p0, p1, p2, p3, step / steps))
    return out


def _dist2_point_segment(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    abx = bx - ax
    aby = by - ay
    denom = abx * abx + aby * aby
    if denom <= 1e-9:
        dx = px - ax
        dy = py - ay
        return dx * dx + dy * dy
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / denom))
    qx = ax + t * abx
    qy = ay + t * aby
    dx = px - qx
    dy = py - qy
    return dx * dx + dy * dy


def _dist2_aabb_segment(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    """Squared distance between an axis-aligned rect and a segment (0 if they hit)."""
    # Clamp segment endpoints into the rect to detect intersection / interior.
    for px, py in ((ax, ay), (bx, by)):
        if min_x <= px <= max_x and min_y <= py <= max_y:
            return 0.0
    # Sample the closest point on the segment to the rect centre, then to corners.
    cx = 0.5 * (min_x + max_x)
    cy = 0.5 * (min_y + max_y)
    best = _dist2_point_segment(cx, cy, ax, ay, bx, by)
    for px, py in (
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
    ):
        best = min(best, _dist2_point_segment(px, py, ax, ay, bx, by))
    # Also project segment endpoints onto the rect (outside → edge distance).
    for px, py in ((ax, ay), (bx, by)):
        qx = max(min_x, min(max_x, px))
        qy = max(min_y, min(max_y, py))
        dx = px - qx
        dy = py - qy
        best = min(best, dx * dx + dy * dy)
    # Dense sample along the segment catches crossings that miss corners.
    abx = bx - ax
    aby = by - ay
    steps = max(2, int(math.ceil(math.hypot(abx, aby) / 4.0)))
    for s in range(steps + 1):
        t = s / steps
        px = ax + abx * t
        py = ay + aby * t
        if min_x <= px <= max_x and min_y <= py <= max_y:
            return 0.0
        qx = max(min_x, min(max_x, px))
        qy = max(min_y, min(max_y, py))
        dx = px - qx
        dy = py - qy
        best = min(best, dx * dx + dy * dy)
    return best


def _require(data: dict[str, Any], *keys: str) -> Any:
    cursor: Any = data
    path: list[str] = []
    for key in keys:
        path.append(key)
        if not isinstance(cursor, dict) or key not in cursor:
            raise KeyError(f"Missing city YAML key: {'.'.join(path)}")
        cursor = cursor[key]
    return cursor


def _build_city_plan(data: dict[str, Any]) -> CityPlan:
    block_size = tuple(float(v) for v in _require(data, "lot", "block_size"))
    if len(block_size) != 3:
        raise ValueError("lot.block_size must have three numbers")
    tower_count = int(_require(data, "lot", "tower_count"))
    tower_gap = float(_require(data, "lot", "tower_gap"))
    road_width = float(_require(data, "lot", "road_width"))
    floor_min = int(_require(data, "lot", "floor_min"))
    floor_max = int(_require(data, "lot", "floor_max"))
    towers_per_ring = int(_require(data, "lot", "towers_per_ring"))

    highway_lanes = int(_require(data, "highway", "lanes"))
    fence_w = float(_require(data, "highway", "fence_w"))
    fence_h = float(_require(data, "highway", "fence_h"))
    barrier_w = float(_require(data, "highway", "barrier_w"))
    barrier_h = float(_require(data, "highway", "barrier_h"))
    highway_keepout = float(_require(data, "highway", "keepout"))

    raw_highways = _require(data, "highways")
    if not isinstance(raw_highways, dict) or not raw_highways:
        raise ValueError("highways must be a non-empty mapping of polylines")
    highway_routes: list[HighwayRoute] = []
    for name, entry in raw_highways.items():
        lanes = highway_lanes
        z_offset = 0.0
        width: float | None = None
        layer = "arterial"
        if isinstance(entry, dict):
            pts = entry.get("points", [])
            if entry.get("lanes") is not None:
                lanes = int(entry["lanes"])
            if entry.get("z_offset") is not None:
                z_offset = float(entry["z_offset"])
            if entry.get("width") is not None:
                width = float(entry["width"])
            if entry.get("layer") is not None:
                layer = str(entry["layer"])
        else:
            pts = entry
        if not isinstance(pts, list) or len(pts) < 2:
            raise ValueError(f"highways.{name} needs at least two [x, y] points")
        if lanes < 2:
            raise ValueError(f"highways.{name}.lanes must be >= 2")
        highway_routes.append(
            HighwayRoute(
                name=str(name),
                points=tuple((float(p[0]), float(p[1])) for p in pts),
                lanes=lanes,
                z_offset=z_offset,
                width=width,
                layer=layer,
            )
        )

    raw_streets = data.get("streets", {})
    if raw_streets is None:
        raw_streets = {}
    if not isinstance(raw_streets, dict):
        raise ValueError("streets must be a mapping of polylines")
    street_routes: list[StreetRoute] = []
    for name, entry in raw_streets.items():
        bulb_start = False
        bulb_end = False
        bulb_radius: float | None = None
        if isinstance(entry, dict):
            pts = entry.get("points", [])
            bulb_start = bool(entry.get("bulb_start", False))
            bulb_end = bool(entry.get("bulb_end", False))
            if entry.get("bulb_radius") is not None:
                bulb_radius = float(entry["bulb_radius"])
        else:
            pts = entry
        if not isinstance(pts, list) or len(pts) < 2:
            raise ValueError(f"streets.{name} needs at least two [x, y] points")
        street_routes.append(
            StreetRoute(
                name=str(name),
                points=tuple((float(p[0]), float(p[1])) for p in pts),
                bulb_start=bulb_start,
                bulb_end=bulb_end,
                bulb_radius=bulb_radius,
            )
        )

    raw_hoods = data.get("neighborhoods", [])
    if raw_hoods is None:
        raw_hoods = []
    if not isinstance(raw_hoods, list):
        raise ValueError("neighborhoods must be a list")
    neighborhoods: list[Neighborhood] = []
    for entry in raw_hoods:
        kind = str(entry["kind"])
        if kind not in ("housing", "tower", "factory"):
            raise ValueError(f"Unknown neighborhood kind: {kind}")
        origin = entry["origin"]
        neighborhoods.append(
            Neighborhood(
                name=str(entry["name"]),
                kind=kind,
                origin_x=float(origin[0]),
                origin_y=float(origin[1]),
                heading_deg=float(entry.get("heading", 0.0)),
                cols=int(entry["cols"]),
                rows=int(entry["rows"]),
            )
        )

    block_center_x = 9.75
    road_left = block_center_x - 25.0 / 2
    road_right = road_left + tower_count * block_size[0] + (tower_count - 1) * tower_gap
    road_length = road_right - road_left
    road_depth = 2 * block_size[1] + tower_gap
    stride_x = road_width + road_length
    stride_y = road_width + road_depth
    lot_width = tower_count * block_size[0] + (tower_count - 1) * tower_gap

    road_y0 = -(block_size[1] / 2 + 1.0 + road_width / 2)
    tower_y0 = road_y0 + road_width / 2 + block_size[1] / 2
    south_road0 = tower_y0 - block_size[1] / 2 - road_width / 2
    west_road0 = road_left - road_width / 2
    road_top = -block_size[2] / 2 + 0.1
    south_face = -1.0 - block_size[1] / 2

    # Host grid for optional later city traffic (unused while neighborhoods empty).
    if neighborhoods:
        host = next((n for n in neighborhoods if n.name == "newton"), neighborhoods[0])
        cols = host.cols
        rows = host.rows
        road_xs = tuple(host.origin_x + c * stride_x for c in range(cols + 1))
        road_ys = tuple(host.origin_y + r * stride_y for r in range(rows + 1))
    else:
        cols = 1
        rows = 1
        road_xs = (0.0, stride_x)
        road_ys = (0.0, stride_y)

    return CityPlan(
        block_size=block_size,
        tower_count=tower_count,
        tower_gap=tower_gap,
        road_width=road_width,
        floor_min=floor_min,
        floor_max=floor_max,
        towers_per_ring=towers_per_ring,
        highway_lanes=highway_lanes,
        fence_w=fence_w,
        fence_h=fence_h,
        barrier_w=barrier_w,
        barrier_h=barrier_h,
        highway_keepout=highway_keepout,
        highway_routes=tuple(highway_routes),
        street_routes=tuple(street_routes),
        neighborhoods=tuple(neighborhoods),
        road_left=road_left,
        road_right=road_right,
        road_length=road_length,
        road_depth=road_depth,
        stride_x=stride_x,
        stride_y=stride_y,
        lot_width=lot_width,
        road_top=road_top,
        south_road0=south_road0,
        west_road0=west_road0,
        south_road_full0=road_ys[0],
        west_road_full0=road_xs[0],
        south_face=south_face,
        city_west_edge=road_xs[0] - road_width / 2,
        tallest=floor_max,
        cols=cols,
        rows=rows,
        north_shift=0.0,
        north_shift_lots=0,
        exit_row=1,
        between_housing_rows=0,
        grid=0,
        housing_cols=cols,
        housing_rows=rows,
        factory_rows=0,
        factory_cols=0,
        west_housing_cols=0,
        west_housing_rows=0,
        east_factory_cols=0,
        east_factory_rows=0,
        tower_west=road_left,
        housing_south=rows,
        west_housing_cols_count=0,
        west_cols=cols,
        east_cols=0,
        south_rows=rows,
        north_rows=0,
        arterial_gap_x=0.0,
        arterial_gap_y=0.0,
        gap_after_v=(),
        gap_after_h=(),
        road_xs_list=road_xs,
        road_ys_list=road_ys,
    )


def load_city_plan(path: str | Path | None = None) -> CityPlan:
    yaml_path = Path(path) if path is not None else DEFAULT_CITY_YAML
    with yaml_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"City YAML must be a mapping: {yaml_path}")
    return _build_city_plan(data)


def default_city_plan() -> CityPlan:
    """Return the packaged Chicago layout from ``city/data/city.yaml``."""
    return load_city_plan()
