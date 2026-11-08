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
north road and the north city's south road. A six-lane north-south highway
runs along the west edge of both cities, with exits onto each city's fifth
east-west road. The sphere group and a brown cube capped by a pyramid stand
30 units to the right of the road.
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

    gap_row_span: int
    gap_houses_across: int
    gap_houses_deep: int
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
    gap_lot_width: float
    gap_lot_depth: float
    gap_west_face: float
    gap_housing_rows: int
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

    def iter_gap_housing_lots(self) -> Iterator[HousingLot]:
        for grow in range(self.gap_housing_rows):
            h_south = grow * self.gap_row_span
            lot_south = self.south_road_full0 + h_south * self.stride_y + self.road_width / 2
            y_offset = lot_south - (-1.0 - self.block_size[1] / 2)
            yield HousingLot(
                west_face=self.gap_west_face,
                y_offset=y_offset,
                lot_width=self.gap_lot_width,
                lot_depth=self.gap_lot_depth,
                eastern_road=False,
                southern_road=grow == 0,
                northern_road=True,
                houses_across=self.gap_houses_across,
                houses_deep=self.gap_houses_deep,
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
        """Derived highway placement shared by scene assembly and the car."""
        lane_width = self.road_width / 2
        highway_width = self.highway_lanes * lane_width
        west_road_west = self.gap_west_face - self.road_width
        highway_east = west_road_west - self.fence_w
        highway_mid_x = highway_east - highway_width / 2
        fence_x = west_road_west - self.fence_w / 2
        city_south = self.south_face - self.factory_rows * self.stride_y - self.road_width
        city_north = (
            self.south_face
            + (self.grid + self.housing_rows) * self.road_depth
            + (self.grid + self.housing_rows) * self.road_width
            + self.north_shift
        )
        highway_length = city_north - city_south
        highway_mid_y = (city_north + city_south) / 2
        road_thickness = 0.1
        road_z = -self.block_size[2] / 2 + road_thickness / 2
        exit_ys = [
            self.south_road_full0 + self.exit_row * self.stride_y + origin
            for origin in (0.0, self.north_shift)
        ]
        return {
            "lane_width": lane_width,
            "highway_width": highway_width,
            "highway_east": highway_east,
            "highway_mid_x": highway_mid_x,
            "fence_x": fence_x,
            "city_south": city_south,
            "city_north": city_north,
            "highway_length": highway_length,
            "highway_mid_y": highway_mid_y,
            "road_thickness": road_thickness,
            "road_z": road_z,
            "exit_ys": exit_ys,
        }

    def framing_bounds(self, cube_center_x: float, pyramid_half_x: float) -> dict[str, float]:
        hwy = self.highway_geometry()
        left = min(
            self.city_west_edge,
            self.circle_left + self.group_shift,
            hwy["highway_east"] - hwy["highway_width"],
        )
        right = cube_center_x + pyramid_half_x
        stack_bottom = -self.block_size[2] / 2
        stack_top = (self.tallest - 1) * self.block_size[2] + self.block_size[2] / 2
        return {
            "left": left,
            "right": right,
            "city_south": hwy["city_south"],
            "city_north": hwy["city_north"],
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
    gap_row_span = int(_require(data, "districts", "gap", "row_span"))
    gap_houses_across = int(_require(data, "districts", "gap", "houses_across"))
    gap_houses_deep = int(_require(data, "districts", "gap", "houses_deep"))
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
    gap_lot_width = road_depth
    gap_lot_depth = gap_row_span * stride_y - road_width
    gap_west_face = city_west_edge - gap_lot_width
    gap_housing_rows = rows // gap_row_span
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
        gap_row_span=gap_row_span,
        gap_houses_across=gap_houses_across,
        gap_houses_deep=gap_houses_deep,
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
        gap_lot_width=gap_lot_width,
        gap_lot_depth=gap_lot_depth,
        gap_west_face=gap_west_face,
        gap_housing_rows=gap_housing_rows,
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
