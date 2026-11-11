"""Software-city layout architecture.

Three identical lit spheres form an equilateral triangle, joined center to
center by thin cylinders. Sixteen rings, each two towers deep and five wide,
form a square with four on each side. Twelve housing blocks in a six-by-two
grid sit north of the tower city, west-aligned with it, and sixteen more in a
two-by-eight grid sit west of the towers, spanning the southern factories
through the northern housing; each lot shares roads with neighbours and holds
a six-by-two grid of brown houses (2x2 cube under a 3x3 pyramid), two units
between roofs, with a green slab as thick as the road filling the gaps. Eight
empty road loops with the same 29-by-11 inner footprint form a two-by-four grid
south of the tower city, and twelve more form a two-by-six grid east of the
tower city and its southern factories; each shares roads with its neighbours
and holds a grey factory building 29 by 11 by 9 with three 2-by-2-by-6 stacks
on the roof. Each ring has stacks of unique random heights, from ten to
twenty-five floors. A block leaves out the road on any side that faces another
block, so neighbours share one road. Twelve rows of full housing blocks fill
the strip between the two cities, spanning the full city width; the northern
copy sits exactly far enough north that those lots share the south city's
north road and the north city's south road. A six-lane ring beltway wraps
    both cities with a six-lane ring (west, north, east, south), quarter-turn
    rounded corners cleared past the street grid, and a diamond interchange on
    each side (``<||>`` chevrons with an elevated cross bridge) linking the
    beltway to the city grid. The sphere group and a brown cube capped by a
    pyramid stand 30 units to the right of the road.
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
class CityPlan:
    """District grids, strides, shared-road rules, twin city, highway, landmarks."""

    block_size: tuple[float, float, float]
    tower_count: int
    tower_gap: float
    road_width: float
    floor_min: int
    floor_max: int
    towers_per_ring: int

    grid: int
    housing_cols: int
    housing_rows: int
    factory_rows: int
    factory_cols: int
    west_housing_cols: int
    west_housing_rows: int
    east_factory_cols: int
    east_factory_rows: int

    between_housing_rows: int

    north_shift_lots: int
    highway_lanes: int
    fence_w: float
    fence_h: float
    barrier_w: float
    barrier_h: float
    exit_row: int

    sphere_side: float
    sphere_radius: float
    landmark_east_gap: float
    house_gap: float
    block_gap: float

    # Derived placement anchors (computed by load_city_plan from YAML).
    road_left: float
    road_right: float
    road_length: float
    road_depth: float
    stride_x: float
    stride_y: float
    lot_width: float
    road_center_x: float
    block_center_x: float
    group_shift: float
    circle_left: float
    sphere_positions: tuple[tuple[float, float], ...]
    tower_west: float
    cols: int
    rows: int
    west_housing_cols_count: int
    housing_south: int
    south_road0: float
    west_road0: float
    south_road_full0: float
    west_road_full0: float
    road_top: float
    south_face: float
    city_west_edge: float
    north_shift: float
    tallest: int

    def solid_lot(self, brow: int, bcol: int) -> bool:
        """True when the lot has a tower or factory wall at the road."""
        if bcol < 0 or bcol >= self.cols or brow < 0 or brow >= self.rows:
            return False
        if bcol < self.west_housing_cols:
            return False
        if brow >= self.housing_south:
            return False
        return True

    def iter_tower_lots(self) -> Iterator[TowerLot]:
        for row in range(self.grid):
            for col in range(self.grid):
                yield TowerLot(
                    west_face=self.road_left - (self.grid - 1 - col) * self.stride_x,
                    y_offset=row * self.stride_y,
                    eastern_road=False,
                    southern_road=False,
                    empty=False,
                )

    def iter_north_housing_lots(self) -> Iterator[HousingLot]:
        for hrow in range(self.housing_rows):
            for hcol in range(self.housing_cols):
                yield HousingLot(
                    west_face=self.road_left - (self.grid - 1) * self.stride_x + hcol * self.stride_x,
                    y_offset=(self.grid + hrow) * self.stride_y,
                    lot_width=self.lot_width,
                    lot_depth=self.road_depth,
                    eastern_road=hcol == self.housing_cols - 1,
                    southern_road=False,
                    northern_road=True,
                    houses_across=6,
                    houses_deep=2,
                )

    def iter_west_housing_lots(self) -> Iterator[HousingLot]:
        for wrow in range(self.west_housing_rows):
            for wcol in range(self.west_housing_cols):
                yield HousingLot(
                    west_face=self.tower_west - (self.west_housing_cols - wcol) * self.stride_x,
                    y_offset=(wrow - self.factory_rows) * self.stride_y,
                    lot_width=self.lot_width,
                    lot_depth=self.road_depth,
                    eastern_road=False,
                    southern_road=wrow == 0,
                    northern_road=True,
                    houses_across=6,
                    houses_deep=2,
                )

    def iter_south_factory_lots(self) -> Iterator[TowerLot]:
        for frow in range(self.factory_rows):
            for fcol in range(self.factory_cols):
                yield TowerLot(
                    west_face=self.road_left - (self.factory_cols - 1 - fcol) * self.stride_x,
                    y_offset=-(frow + 1) * self.stride_y,
                    eastern_road=False,
                    southern_road=frow == self.factory_rows - 1,
                    empty=True,
                )

    def iter_east_factory_lots(self) -> Iterator[TowerLot]:
        for erow in range(self.east_factory_rows):
            for ecol in range(self.east_factory_cols):
                yield TowerLot(
                    west_face=self.road_left + (ecol + 1) * self.stride_x,
                    y_offset=(erow - self.factory_rows) * self.stride_y,
                    eastern_road=ecol == self.east_factory_cols - 1,
                    southern_road=erow == 0,
                    empty=True,
                )

    def iter_between_housing_lots(self) -> Iterator[HousingLot]:
        """Full-size housing grid filling the strip between the twin cities."""
        west0 = self.tower_west - self.west_housing_cols * self.stride_x
        y0 = (self.grid + self.housing_rows) * self.stride_y
        for brow in range(self.between_housing_rows):
            for bcol in range(self.cols):
                yield HousingLot(
                    west_face=west0 + bcol * self.stride_x,
                    y_offset=y0 + brow * self.stride_y,
                    lot_width=self.lot_width,
                    lot_depth=self.road_depth,
                    eastern_road=bcol == self.cols - 1,
                    southern_road=False,
                    northern_road=brow < self.between_housing_rows - 1,
                    houses_across=6,
                    houses_deep=2,
                )

    def highway_geometry(self) -> dict[str, float | list[float]]:
        """Derived beltway placement shared by scene assembly and the car.

        City-facing edges of the four legs form an inner rounded rectangle around
        the twin footprint: west of the city-west fence, a road-width clearance
        past the easternmost city road, and flush with the north/south extents.
        Those keep-outs are then pushed outward by the corner-fillet depth so the
        quarter-annulus pads cannot cut into the street grid. Each leg is
        ``highway_lanes`` wide; ``corner_radius`` is the inner arc radius.
        """
        lane_width = self.road_width / 2
        highway_width = self.highway_lanes * lane_width
        # Keep-out rectangle: city footprint plus the existing service clearances.
        keepout_west = self.city_west_edge - self.fence_w
        city_south = self.south_face - self.factory_rows * self.stride_y - self.road_width
        city_north = (
            self.south_face
            + (self.grid + self.housing_rows) * self.road_depth
            + (self.grid + self.housing_rows) * self.road_width
            + self.north_shift
        )
        city_east = (
            self.west_road_full0 + self.cols * self.stride_x + self.road_width / 2
        )
        # Mirror the west clearance: one road width + fence past the east edge.
        keepout_east = city_east + self.road_width + self.fence_w
        keepout_south = city_south
        keepout_north = city_north
        # Inner-corner radius: two highway widths keeps a clear curve without
        # swallowing the straight legs of the twin footprint.
        corner_radius = 2.0 * highway_width
        keepout_width = keepout_east - keepout_west
        keepout_height = keepout_north - keepout_south
        max_radius = min(keepout_width, keepout_height) / 2 - lane_width
        if corner_radius > max_radius:
            corner_radius = max(lane_width, max_radius)
        # A rounded-rect inner edge bites ``inset`` into a sharp rectangle of the
        # same bounds; push the belt out so that bite stays in empty margin.
        inset = corner_radius * (1.0 - math.sqrt(2.0) / 2.0)
        belt_west_inner = keepout_west - inset
        belt_east_inner = keepout_east + inset
        belt_south_inner = keepout_south - inset
        belt_north_inner = keepout_north + inset
        belt_west_outer = belt_west_inner - highway_width
        belt_east_outer = belt_east_inner + highway_width
        belt_south_outer = belt_south_inner - highway_width
        belt_north_outer = belt_north_inner + highway_width
        # City-facing edge of the west carriageway; fence sits on that curb.
        highway_east = belt_west_inner
        highway_mid_x = highway_east - highway_width / 2
        fence_x = highway_east + self.fence_w / 2
        east_mid_x = belt_east_inner + highway_width / 2
        south_mid_y = belt_south_inner - highway_width / 2
        north_mid_y = belt_north_inner + highway_width / 2
        ring_mid_x = (belt_west_outer + belt_east_outer) / 2
        ring_mid_y = (belt_south_outer + belt_north_outer) / 2
        ring_outer_width = belt_east_outer - belt_west_outer
        ring_outer_height = belt_north_outer - belt_south_outer
        # Straight N-S legs stop where the corner arcs begin.
        ns_y0 = belt_south_inner + corner_radius
        ns_y1 = belt_north_inner - corner_radius
        ew_x0 = belt_west_inner + corner_radius
        ew_x1 = belt_east_inner - corner_radius
        highway_length = ns_y1 - ns_y0
        highway_mid_y = (ns_y0 + ns_y1) / 2
        road_thickness = 0.1
        road_z = -self.block_size[2] / 2 + road_thickness / 2
        # One diamond per side, snapped to the city grid so cars can use them.
        # Ordered CCW from west: west → north → east → south.
        west_exit_y = self.south_road_full0 + self.exit_row * self.stride_y
        east_exit_y = west_exit_y
        mid_col = self.cols // 2
        south_exit_x = self.west_road_full0 + mid_col * self.stride_x
        north_exit_x = south_exit_x
        north_origin_y = self.south_road_full0 + self.north_shift
        north_exit_y = north_origin_y + self.rows * self.stride_y
        south_exit_y = self.south_road_full0
        # Along-highway half-span of each city-side diamond rhombus.
        slip_len = highway_width * 0.85
        diamonds = (
            {
                "side": "west",
                "axis": "ns",
                "hx": highway_mid_x,
                "hy": west_exit_y,
                "city_v": 0,
                "city_h": self.exit_row,
                "city_origin_y": self.south_road_full0,
                "into_city": (1, 0),
                "ccw_dir": (0, 1),
                "cw_dir": (0, -1),
                "city_x": self.west_road_full0,
                "city_y": west_exit_y,
                "slip_len": slip_len,
            },
            {
                "side": "north",
                "axis": "ew",
                "hx": north_exit_x,
                "hy": north_mid_y,
                "city_v": mid_col,
                "city_h": self.rows,
                "city_origin_y": north_origin_y,
                "into_city": (0, -1),
                "ccw_dir": (1, 0),
                "cw_dir": (-1, 0),
                "city_x": north_exit_x,
                "city_y": north_exit_y,
                "slip_len": slip_len,
            },
            {
                "side": "east",
                "axis": "ns",
                "hx": east_mid_x,
                "hy": east_exit_y,
                "city_v": self.cols,
                "city_h": self.exit_row,
                "city_origin_y": self.south_road_full0,
                "into_city": (-1, 0),
                "ccw_dir": (0, -1),
                "cw_dir": (0, 1),
                "city_x": self.west_road_full0 + self.cols * self.stride_x,
                "city_y": east_exit_y,
                "slip_len": slip_len,
            },
            {
                "side": "south",
                "axis": "ew",
                "hx": south_exit_x,
                "hy": south_mid_y,
                "city_v": mid_col,
                "city_h": 0,
                "city_origin_y": self.south_road_full0,
                "into_city": (0, 1),
                "ccw_dir": (-1, 0),
                "cw_dir": (1, 0),
                "city_x": south_exit_x,
                "city_y": south_exit_y,
                "slip_len": slip_len,
            },
        )
        # Lane centres per leg (index 0 = inner/city-side = right-hand for CCW).
        west_lane_xs = [
            belt_west_inner - lane_width * (i + 0.5) for i in range(self.highway_lanes)
        ]
        east_lane_xs = [
            belt_east_inner + lane_width * (i + 0.5) for i in range(self.highway_lanes)
        ]
        south_lane_ys = [
            belt_south_inner - lane_width * (i + 0.5) for i in range(self.highway_lanes)
        ]
        north_lane_ys = [
            belt_north_inner + lane_width * (i + 0.5) for i in range(self.highway_lanes)
        ]
        return {
            "lane_width": lane_width,
            "highway_width": highway_width,
            "highway_east": highway_east,
            "highway_mid_x": highway_mid_x,
            "fence_x": fence_x,
            "city_south": city_south,
            "city_north": city_north,
            "city_east": city_east,
            "highway_length": highway_length,
            "highway_mid_y": highway_mid_y,
            "road_thickness": road_thickness,
            "road_z": road_z,
            "exit_ys": [west_exit_y, east_exit_y],
            "diamonds": diamonds,
            "west_lane_xs": west_lane_xs,
            "east_lane_xs": east_lane_xs,
            "south_lane_ys": south_lane_ys,
            "north_lane_ys": north_lane_ys,
            "belt_west_inner": belt_west_inner,
            "belt_east_inner": belt_east_inner,
            "belt_south_inner": belt_south_inner,
            "belt_north_inner": belt_north_inner,
            "belt_west_outer": belt_west_outer,
            "belt_east_outer": belt_east_outer,
            "belt_south_outer": belt_south_outer,
            "belt_north_outer": belt_north_outer,
            "east_mid_x": east_mid_x,
            "south_mid_y": south_mid_y,
            "north_mid_y": north_mid_y,
            "ring_mid_x": ring_mid_x,
            "ring_mid_y": ring_mid_y,
            "ring_outer_width": ring_outer_width,
            "ring_outer_height": ring_outer_height,
            "east_fence_x": belt_east_inner - self.fence_w / 2,
            "south_fence_y": belt_south_inner + self.fence_w / 2,
            "north_fence_y": belt_north_inner - self.fence_w / 2,
            "corner_radius": corner_radius,
            "ns_y0": ns_y0,
            "ns_y1": ns_y1,
            "ew_x0": ew_x0,
            "ew_x1": ew_x1,
            "ew_span": ew_x1 - ew_x0,
            "ew_mid_x": (ew_x0 + ew_x1) / 2,
            "corner_sw": (belt_west_inner + corner_radius, belt_south_inner + corner_radius),
            "corner_se": (belt_east_inner - corner_radius, belt_south_inner + corner_radius),
            "corner_ne": (belt_east_inner - corner_radius, belt_north_inner - corner_radius),
            "corner_nw": (belt_west_inner + corner_radius, belt_north_inner - corner_radius),
        }

    def framing_bounds(self, cube_center_x: float, pyramid_half_x: float) -> dict[str, float]:
        hwy = self.highway_geometry()
        left = min(
            self.city_west_edge,
            self.circle_left + self.group_shift,
            hwy["belt_west_outer"],
        )
        right = max(cube_center_x + pyramid_half_x, hwy["belt_east_outer"])
        stack_bottom = -self.block_size[2] / 2
        stack_top = (self.tallest - 1) * self.block_size[2] + self.block_size[2] / 2
        return {
            "left": left,
            "right": right,
            "city_south": hwy["belt_south_outer"],
            "city_north": hwy["belt_north_outer"],
            "stack_bottom": stack_bottom,
            "stack_top": stack_top,
        }


def _require(data: dict[str, Any], *keys: str) -> Any:
    """Walk nested dict keys; raise KeyError with a dotted path on failure."""
    cursor: Any = data
    path: list[str] = []
    for key in keys:
        path.append(key)
        if not isinstance(cursor, dict) or key not in cursor:
            raise KeyError(f"Missing city YAML key: {'.'.join(path)}")
        cursor = cursor[key]
    return cursor


def _build_city_plan(data: dict[str, Any]) -> CityPlan:
    """Derive a CityPlan from authored YAML knobs."""
    block_size = tuple(float(v) for v in _require(data, "lot", "block_size"))
    if len(block_size) != 3:
        raise ValueError("lot.block_size must have three numbers")
    tower_count = int(_require(data, "lot", "tower_count"))
    tower_gap = float(_require(data, "lot", "tower_gap"))
    road_width = float(_require(data, "lot", "road_width"))
    floor_min = int(_require(data, "lot", "floor_min"))
    floor_max = int(_require(data, "lot", "floor_max"))
    towers_per_ring = int(_require(data, "lot", "towers_per_ring"))

    grid = int(_require(data, "districts", "grid"))
    housing_cols = int(_require(data, "districts", "housing", "cols"))
    housing_rows = int(_require(data, "districts", "housing", "rows"))
    west_housing_cols = int(_require(data, "districts", "west_housing", "cols"))
    west_housing_rows = int(_require(data, "districts", "west_housing", "rows"))
    factory_rows = int(_require(data, "districts", "south_factories", "rows"))
    factory_cols = int(_require(data, "districts", "south_factories", "cols"))
    east_factory_cols = int(_require(data, "districts", "east_factories", "cols"))
    east_factory_rows = int(_require(data, "districts", "east_factories", "rows"))
    between_housing_rows = int(_require(data, "districts", "between_housing", "rows"))

    highway_lanes = int(_require(data, "highway", "lanes"))
    fence_w = float(_require(data, "highway", "fence_w"))
    fence_h = float(_require(data, "highway", "fence_h"))
    barrier_w = float(_require(data, "highway", "barrier_w"))
    barrier_h = float(_require(data, "highway", "barrier_h"))
    exit_row = int(_require(data, "highway", "exit_row"))

    sphere_side = float(_require(data, "landmarks", "sphere_side"))
    sphere_radius = float(_require(data, "landmarks", "sphere_radius"))
    block_gap = float(_require(data, "landmarks", "block_gap"))
    landmark_east_gap = float(_require(data, "landmarks", "landmark_east_gap"))
    house_gap = float(_require(data, "landmarks", "house_gap"))

    height = sphere_side * math.sqrt(3) / 2
    sphere_positions = (
        (-sphere_side / 2, -height / 3),
        (sphere_side / 2, -height / 3),
        (0.0, 2 * height / 3),
    )
    right_surface = sphere_side / 2 + sphere_radius
    block_center_x = right_surface + block_gap + block_size[0] / 2
    # Historical: road_left used 25.0/2 (5 towers * 5 units) rather than lot_width/2.
    road_left = block_center_x - 25.0 / 2
    road_right = road_left + tower_count * block_size[0] + (tower_count - 1) * tower_gap
    road_length = road_right - road_left
    road_center_x = (road_left + road_right) / 2
    road_depth = 2 * block_size[1] + tower_gap
    stride_x = road_width + road_length
    stride_y = road_width + road_depth
    lot_width = tower_count * block_size[0] + (tower_count - 1) * tower_gap

    circle_left = -sphere_side / 2 - sphere_radius
    group_shift = road_right + east_factory_cols * stride_x + landmark_east_gap - circle_left

    tower_west = road_left - (grid - 1) * stride_x
    cols = west_housing_cols + grid + east_factory_cols
    rows = factory_rows + grid + housing_rows
    housing_south = factory_rows + grid

    road_y0 = -(block_size[1] / 2 + 1.0 + road_width / 2)
    tower_y0 = road_y0 + road_width / 2 + block_size[1] / 2
    south_road0 = tower_y0 - block_size[1] / 2 - road_width / 2
    west_road0 = road_left - (grid - 1) * stride_x - road_width / 2
    south_road_full0 = south_road0 - factory_rows * stride_y
    west_road_full0 = west_road0 - west_housing_cols * stride_x
    road_top = -block_size[2] / 2 + 0.1
    south_face = -1.0 - block_size[1] / 2

    city_west_edge = west_road_full0 - road_width / 2
    # Twin offset: city footprint (rows) plus the between-housing strip so the
    # connector lots share the south city's north road and north city's south road.
    north_shift_lots = rows + between_housing_rows
    north_shift = north_shift_lots * stride_y

    return CityPlan(
        block_size=block_size,
        tower_count=tower_count,
        tower_gap=tower_gap,
        road_width=road_width,
        floor_min=floor_min,
        floor_max=floor_max,
        towers_per_ring=towers_per_ring,
        grid=grid,
        housing_cols=housing_cols,
        housing_rows=housing_rows,
        factory_rows=factory_rows,
        factory_cols=factory_cols,
        west_housing_cols=west_housing_cols,
        west_housing_rows=west_housing_rows,
        east_factory_cols=east_factory_cols,
        east_factory_rows=east_factory_rows,
        between_housing_rows=between_housing_rows,
        north_shift_lots=north_shift_lots,
        highway_lanes=highway_lanes,
        fence_w=fence_w,
        fence_h=fence_h,
        barrier_w=barrier_w,
        barrier_h=barrier_h,
        exit_row=exit_row,
        sphere_side=sphere_side,
        sphere_radius=sphere_radius,
        landmark_east_gap=landmark_east_gap,
        house_gap=house_gap,
        block_gap=block_gap,
        road_left=road_left,
        road_right=road_right,
        road_length=road_length,
        road_depth=road_depth,
        stride_x=stride_x,
        stride_y=stride_y,
        lot_width=lot_width,
        road_center_x=road_center_x,
        block_center_x=block_center_x,
        group_shift=group_shift,
        circle_left=circle_left,
        sphere_positions=sphere_positions,
        tower_west=tower_west,
        cols=cols,
        rows=rows,
        west_housing_cols_count=west_housing_cols,
        housing_south=housing_south,
        south_road0=south_road0,
        west_road0=west_road0,
        south_road_full0=south_road_full0,
        west_road_full0=west_road_full0,
        road_top=road_top,
        south_face=south_face,
        city_west_edge=city_west_edge,
        north_shift=north_shift,
        tallest=floor_max,
    )


def load_city_plan(path: str | Path | None = None) -> CityPlan:
    """Load authored layout from YAML and derive a CityPlan."""
    yaml_path = Path(path) if path is not None else DEFAULT_CITY_YAML
    with yaml_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"City YAML must be a mapping: {yaml_path}")
    return _build_city_plan(data)


def default_city_plan() -> CityPlan:
    """Return the packaged software-city layout from ``city/data/city.yaml``."""
    return load_city_plan()
