"""ShowBase app: assemble the city from CityPlan and run the viewer."""

from __future__ import annotations

import math
import random
import sys
from collections import defaultdict

from panda3d.core import (
    AmbientLight,
    CompassEffect,
    DirectionalLight,
    Filename,
    KeyboardButton,
    LineSegs,
    Point3,
    TextNode,
)
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase

from city.builders import SceneBuilders
from city.car import ROAD_SHOULDER, CarController, PlayerCar
from city.daycycle import SUNRISE_SECONDS, DayNightCycle
from city.districts import (
    CITY_CENTRE_BLOCKS,
    DISTRICT_DEFS as _DISTRICT_DEFS_RAW,
    HIGHWAY_LABELS,
    LOCATION_AREAS,
)
from city.geo import CAMERA_FAR_CLIP, apply_district_transforms

DISTRICT_DEFS = apply_district_transforms(_DISTRICT_DEFS_RAW)
from city.materials import (
    lawn_material,
    mark_material,
    road_material,
)
from city.mesh import (
    _dist2_point_segment,
    box_instance,
    make_flat_deck_batch,
    make_highway_ribbon,
    make_sky_dome,
    z_cylinder_instance,
)
from city.chicago_housing import (
    HOUSING_HIDE_DIST,
    HOUSING_MAX_TILES,
    HOUSING_VIEW_FACTOR,
    HOUSING_VIEW_MIN,
    SECTOR_SIZE,
    build_chicago_housing,
    ensure_housing_sectors,
)
from city.chicago_lights import (
    LIGHTS_HIDE_DIST,
    LIGHTS_MAX_POOL_TILES,
    LIGHTS_MAX_TILES,
    LIGHTS_VIEW_FACTOR,
    LIGHTS_VIEW_MIN,
    WARMUP_SECONDS,
    build_chicago_lights,
)
from city.chicago_airports import build_chicago_airports
from city.chicago_signals import build_chicago_signals
from city.plan import default_city_plan
from city.signals import TrafficLightController
# Spatial hash cell size for barrier / road lookups (car-mode hot path).
_SEG_CELL = 4.0
# Barrier prism length target — thin 2× ribbons; coarsen lightly for FPS.
_BARRIER_SPAN = 1.2
# Drop leftover stubs between nearby crossings.
_BARRIER_MIN_RUN = 2.5
# Minor-street spatial tiles (2 miles) — only nearby tiles draw when zoomed in.
_MINOR_TILE = 84.4
_MINOR_HIDE_DIST = 220.0
_COLLECTOR_HIDE_DIST = 450.0
_SIGNAL_HIDE_DIST = 320.0
_HOUSING_HIDE_DIST = HOUSING_HIDE_DIST
_HOUSING_MAX_TILES = HOUSING_MAX_TILES
_LIGHTS_HIDE_DIST = LIGHTS_HIDE_DIST
_LIGHTS_MAX_TILES = LIGHTS_MAX_TILES
_LIGHTS_MAX_POOL_TILES = LIGHTS_MAX_POOL_TILES
_AIRPORT_HIDE_DIST = 380.0
_LABEL_HIDE_DIST = 500.0
_LABEL_MAX_VISIBLE = 8
_DAY_CYCLE_HZ = 1.0
# Billboard labels only on these spines (not every suburban arterial).
_LABEL_ROADS = frozenset(
    {
        "state",
        "madison",
        "michigan",
        "halsted",
        "ashland",
        "western",
        "kedzie",
        "pulaski",
        "cicero",
        "harlem",
        "kennedy",
        "edens",
        "kennedy_ohare",
        "dan_ryan",
        "eisenhower",
        "stevenson",
        "tri_state",
        "i57",
        "bishop_ford",
        "milwaukee",
        "archer",
        "lake_cook",
        "route_83",
    }
)


class CityApp(ShowBase):
    def __init__(self, screenshot: str | None = None) -> None:
        super().__init__()
        self.screenshot_path = screenshot
        self.disableMouse()
        self.setBackgroundColor(0.7, 0.78, 0.88, 1)
        # Unlit-ish roads don't need auto shaders; keeps the CPU cull path light.
        self.render.setShaderAuto(False)

        plan = default_city_plan()
        self.plan = plan
        self.city = self.render.attachNewNode("city")
        hwy = plan.highway_geometry()
        self._hwy = hwy
        road_z = hwy["road_z"]
        road_thickness = hwy["road_thickness"]
        road_top = road_z + road_thickness / 2
        arterials = list(hwy["arterials"])

        self._build_neighborhoods(plan)
        self._build_city_centre(plan, road_z, arterials)
        self._build_districts(road_z, road_thickness)
        self._build_highways(plan, hwy, arterials, road_z, road_thickness, road_top)
        self._build_streets(plan, hwy, road_z, road_thickness, road_top)
        self._build_signals(arterials, road_z, road_thickness)
        # Row houses / Two-Flats / bungalows on the minor-grid residential fabric.
        self._build_chicago_housing(plan, arterials)
        self._build_chicago_airports()
        self._build_chicago_lights(arterials)
        self._build_ground(hwy, road_z)
        self._build_lighting()
        self._build_traffic(plan, arterials, road_top)
        self._setup_camera(plan, road_z)
        self._setup_hud()
        self._bind_controls()

    def _build_neighborhoods(self, plan) -> None:
        block_size = plan.block_size
        for hood in plan.neighborhoods:
            node = self.city.attachNewNode(f"hood-{hood.name}")
            node.setPos(hood.origin_x, hood.origin_y, 0.0)
            node.setH(hood.heading_deg)
            builders = SceneBuilders(node, plan, self.render)
            for kind, lot in plan.iter_neighborhood_lots(hood):
                if kind == "tower":
                    heights = random.sample(
                        range(plan.floor_min, plan.floor_max + 1),
                        plan.towers_per_ring,
                    )
                    block_floors = (tuple(heights[:5]), (), (), tuple(heights[5:]))
                    builders._add_city_block(
                        lot.west_face,
                        block_size,
                        block_floors,
                        y_offset=lot.y_offset,
                        eastern_road=lot.eastern_road,
                        southern_road=lot.southern_road,
                        factory=False,
                    )
                elif kind == "factory":
                    builders._add_city_block(
                        lot.west_face,
                        block_size,
                        ((), (), (), ()),
                        y_offset=lot.y_offset,
                        eastern_road=lot.eastern_road,
                        southern_road=lot.southern_road,
                        factory=True,
                    )
                else:
                    builders._add_housing_lot(
                        lot.west_face,
                        block_size,
                        lot.lot_width,
                        lot.lot_depth,
                        y_offset=lot.y_offset,
                        eastern_road=lot.eastern_road,
                        southern_road=lot.southern_road,
                        northern_road=lot.northern_road,
                        houses_across=lot.houses_across,
                        houses_deep=lot.houses_deep,
                    )
    def _build_city_centre(self, plan, road_z: float, arterials: list) -> None:
        # Placeholder Whalley tower blocks removed for the 2× road-network pass.
        del plan, road_z, arterials
        self.city_centre_blocks = CITY_CENTRE_BLOCKS
        self.city_centre = self.city.attachNewNode("city-centre")

    def _build_districts(self, road_z: float, road_thickness: float) -> None:
        self._ground_z = road_z
        outline_z = road_z + road_thickness / 2 + 0.03
        bright_nodes = {"the_loop": self.city_centre, "city_centre": self.city_centre}
        self._districts: dict[str, dict] = {}
        for key, spec in DISTRICT_DEFS.items():
            district = {
                "title": spec["title"],
                "ring": spec["ring"],
                "bbox": spec.get("bbox"),
                "anchor": spec.get("anchor"),
                "bright": bright_nodes.get(spec.get("bright_key") or key),
                "hotkey_only": bool(spec.get("hotkey_only")),
            }
            outline = self._build_district_outline(key, district["ring"], outline_z)
            outline.hide()
            district["outline"] = outline
            district["label"] = None
            district["label_scale"] = 1.0
            self._districts[key] = district
        self._selected_district: str | None = None
        # Loop is the downtown anchor (was Surrey City Centre).
        centre_key = "the_loop" if "the_loop" in self._districts else next(iter(self._districts))
        self.city_centre_ring = self._districts[centre_key]["ring"]

    def _build_highways(
        self,
        plan,
        hwy: dict,
        arterials: list,
        road_z: float,
        road_thickness: float,
        road_top: float,
    ) -> None:
        highway_width = hwy["highway_width"]
        self.highway = self.render.attachNewNode("highway")
        # LOD stack parents — minors/collectors are single batched GeomNodes.
        self.minor_streets_node = self.highway.attachNewNode("minor_streets_node")
        self.collectors_node = self.highway.attachNewNode("collectors_node")
        self.arterials_node = self.highway.attachNewNode("arterials_node")
        self.expressways_node = self.highway.attachNewNode("expressways_node")
        layer_nodes = {
            "arterial": self.arterials_node,
            "expressway": self.expressways_node,
        }
        for node in (
            self.minor_streets_node,
            self.collectors_node,
            self.arterials_node,
            self.expressways_node,
        ):
            node.setDepthOffset(0)
        road_mat = road_material()

        self._highway_labels = self.render.attachNewNode("highway_labels")
        labels_root = self._highway_labels
        self._highway_label_nodes: list = []
        self._label_base_scale = max(2.4, highway_width * 4.5)
        self._label_ref_distance = 1.0
        self._named_roads: list[tuple[str, float, float, float, float, float]] = []
        self._solid_barriers: list[tuple[float, float, float, float, float]] = []

        def coarsen_polyline(points: list, max_span: float) -> list:
            if len(points) < 2:
                return list(points)
            out = [points[0]]
            acc = 0.0
            for i in range(1, len(points)):
                dx = points[i][0] - points[i - 1][0]
                dy = points[i][1] - points[i - 1][1]
                acc += math.hypot(dx, dy)
                if acc >= max_span or i == len(points) - 1:
                    out.append(points[i])
                    acc = 0.0
            return out

        # ---- Collectors: one batched deck ----
        collector_segs: list[tuple[float, float, float, float, float, float]] = []
        # Minors: spatial tiles so zoomed-in views don't rasterize the whole metro.
        minor_tiles: dict[tuple[int, int], list] = {}

        def _bin_minor_seg(
            x0: float, y0: float, x1: float, y1: float, width: float, zc: float
        ) -> None:
            tile = _MINOR_TILE
            if abs(x1 - x0) < 1e-6:  # vertical
                x = x0
                ya, yb = (y0, y1) if y0 <= y1 else (y1, y0)
                ty0 = int(math.floor(ya / tile))
                ty1 = int(math.floor(yb / tile))
                tx = int(math.floor(x / tile))
                for ty in range(ty0, ty1 + 1):
                    a = max(ya, ty * tile)
                    b = min(yb, (ty + 1) * tile)
                    if b - a > 0.05:
                        minor_tiles.setdefault((tx, ty), []).append(
                            (x, a, x, b, width, zc)
                        )
            elif abs(y1 - y0) < 1e-6:  # horizontal
                y = y0
                xa, xb = (x0, x1) if x0 <= x1 else (x1, x0)
                tx0 = int(math.floor(xa / tile))
                tx1 = int(math.floor(xb / tile))
                ty = int(math.floor(y / tile))
                for tx in range(tx0, tx1 + 1):
                    a = max(xa, tx * tile)
                    b = min(xb, (tx + 1) * tile)
                    if b - a > 0.05:
                        minor_tiles.setdefault((tx, ty), []).append(
                            (a, y, b, y, width, zc)
                        )
            else:
                mx = 0.5 * (x0 + x1)
                my = 0.5 * (y0 + y1)
                key = (int(math.floor(mx / tile)), int(math.floor(my / tile)))
                minor_tiles.setdefault(key, []).append((x0, y0, x1, y1, width, zc))

        for arterial in arterials:
            layer = str(arterial.get("layer", "arterial"))
            if layer not in ("minor", "collector"):
                continue
            pts = list(arterial["points"])
            if len(pts) < 2:
                continue
            width = float(arterial.get("width", highway_width))
            zc = road_z + float(arterial.get("z_offset", 0.0))
            if layer == "minor":
                for i in range(len(pts) - 1):
                    _bin_minor_seg(
                        float(pts[i][0]),
                        float(pts[i][1]),
                        float(pts[i + 1][0]),
                        float(pts[i + 1][1]),
                        width,
                        zc,
                    )
                continue
            for i in range(len(pts) - 1):
                x0, y0 = pts[i]
                x1, y1 = pts[i + 1]
                collector_segs.append(
                    (float(x0), float(y0), float(x1), float(y1), width, zc)
                )
            name = str(arterial.get("name", ""))
            base = name.rsplit("_", 1)[0] if name[-1:].isdigit() else name
            title = HIGHWAY_LABELS.get(name) or HIGHWAY_LABELS.get(base) or ""
            if title:
                half_w = width * 0.5
                for i in range(len(pts) - 1):
                    self._named_roads.append(
                        (
                            title,
                            float(pts[i][0]),
                            float(pts[i][1]),
                            float(pts[i + 1][0]),
                            float(pts[i + 1][1]),
                            half_w,
                        )
                    )

        self._minor_tiles: list[tuple[float, float, object]] = []
        for (tx, ty), segs in minor_tiles.items():
            deck = self.minor_streets_node.attachNewNode(
                make_flat_deck_batch(
                    segs,
                    road_thickness,
                    name=f"minor_tile_{tx}_{ty}",
                    top_only=True,
                )
            )
            deck.setMaterial(road_mat, 1)
            deck.flattenStrong()
            cx = (tx + 0.5) * _MINOR_TILE
            cy = (ty + 0.5) * _MINOR_TILE
            deck.hide()
            self._minor_tiles.append((cx, cy, deck))
        self._minor_tiles_hidden = True

        if collector_segs:
            deck = self.collectors_node.attachNewNode(
                make_flat_deck_batch(
                    collector_segs,
                    road_thickness,
                    name="collectors_deck",
                    top_only=True,
                )
            )
            deck.setMaterial(road_mat, 1)
        self.collectors_node.flattenStrong()
        self.collectors_node.hide()
        self._collectors_hidden = True

        # ---- Arterials + expressways (axis-aligned → batch; curves → ribbon) ----
        arterial_segs: list[tuple[float, float, float, float, float, float]] = []
        expressway_segs: list[tuple[float, float, float, float, float, float]] = []

        def _is_axis_aligned(pts: list) -> bool:
            for i in range(len(pts) - 1):
                if abs(pts[i + 1][0] - pts[i][0]) > 1e-6 and abs(
                    pts[i + 1][1] - pts[i][1]
                ) > 1e-6:
                    return False
            return len(pts) >= 2

        for arterial in arterials:
            layer = str(arterial.get("layer", "arterial"))
            if layer not in ("arterial", "expressway"):
                continue
            pts = list(arterial["points"])
            if len(pts) < 2:
                continue
            route_width = float(arterial.get("width", highway_width))
            name = str(arterial.get("name", ""))
            parent = layer_nodes.get(layer, self.arterials_node)
            z_off = float(arterial.get("z_offset", 0.0))
            route_z = road_z + z_off
            if _is_axis_aligned(pts):
                bucket = arterial_segs if layer == "arterial" else expressway_segs
                for i in range(len(pts) - 1):
                    bucket.append(
                        (
                            float(pts[i][0]),
                            float(pts[i][1]),
                            float(pts[i + 1][0]),
                            float(pts[i + 1][1]),
                            route_width,
                            route_z,
                        )
                    )
            else:
                deck = parent.attachNewNode(
                    make_highway_ribbon(pts, route_width, road_thickness)
                )
                deck.setPos(0.0, 0.0, route_z)
                deck.setMaterial(road_mat, 1)

            base_name = (
                name.rsplit("_", 1)[0]
                if name[:1].isalpha() and name[-1:].isdigit()
                else name
            )
            title = HIGHWAY_LABELS.get(name) or HIGHWAY_LABELS.get(base_name)
            if title is None:
                title = name.replace("_", " ").title()
            if title:
                half_w = route_width * 0.5
                # Coarse HUD segments for car mode only.
                road_pts = coarsen_polyline(pts, 24.0)
                for i in range(len(road_pts) - 1):
                    self._named_roads.append(
                        (
                            title,
                            road_pts[i][0],
                            road_pts[i][1],
                            road_pts[i + 1][0],
                            road_pts[i + 1][1],
                            half_w,
                        )
                    )
                if name in _LABEL_ROADS or layer == "expressway":
                    mid = pts[len(pts) // 2]
                    text = TextNode(f"hwy-label-{name}")
                    text.setText(title)
                    text.setAlign(TextNode.ACenter)
                    text.setTextColor(1.0, 1.0, 1.0, 1)
                    # No drop shadow — billboard shadows are expensive.
                    pivot = labels_root.attachNewNode(f"hwy-label-pivot-{name}")
                    pivot.setPos(mid[0], mid[1], road_top + 0.55)
                    label = pivot.attachNewNode(text)
                    label.setScale(self._label_base_scale)
                    label.setBillboardPointEye()
                    label.setDepthTest(False)
                    label.setDepthWrite(False)
                    label.hide()
                    self._highway_label_nodes.append(
                        (label, float(mid[0]), float(mid[1]))
                    )
        self._label_zoom_applied = None
        self._lod_key = None

        if arterial_segs:
            deck = self.arterials_node.attachNewNode(
                make_flat_deck_batch(
                    arterial_segs,
                    road_thickness,
                    name="arterials_deck",
                    top_only=True,
                )
            )
            deck.setMaterial(road_mat, 1)
        if expressway_segs:
            deck = self.expressways_node.attachNewNode(
                make_flat_deck_batch(
                    expressway_segs,
                    road_thickness,
                    name="expressways_axis_deck",
                    top_only=True,
                )
            )
            deck.setMaterial(road_mat, 1)

        self.arterials_node.flattenStrong()
        self.expressways_node.flattenStrong()

        self._barrier_cell = _SEG_CELL
        self._road_cell = _SEG_CELL
        self._barrier_grid = self._build_segment_grid(
            self._solid_barriers, xy_offset=0, cell=self._barrier_cell
        )
        self._road_grid = self._build_segment_grid(
            self._named_roads, xy_offset=1, cell=self._road_cell
        )

        # District billboards are created lazily on select (keeps overview light).
        for key, district in self._districts.items():
            ring = district["ring"]
            anchor = district.get("anchor")
            if anchor is not None:
                label_x, label_y = anchor
            else:
                label_x = sum(p[0] for p in ring) / len(ring)
                label_y = sum(p[1] for p in ring) / len(ring)
            district["label"] = None
            district["label_xy"] = (label_x, label_y)
            district["label_z"] = road_top + 6.0
            district["label_scale"] = self._label_base_scale * 20.0

    def _build_streets(
        self,
        plan,
        hwy: dict,
        road_z: float,
        road_thickness: float,
        road_top: float,
    ) -> None:
        streets = plan.street_geometry()
        self.streets = self.render.attachNewNode("streets")
        street_width = float(streets["street_width"])
        road_mat = road_material()
        mark_paint = mark_material()
        for route in streets["routes"]:
            pts = list(route["points"])
            if len(pts) < 2:
                continue
            deck = self.streets.attachNewNode(
                make_highway_ribbon(pts, street_width, road_thickness)
            )
            deck.setPos(0.0, 0.0, road_z)
            deck.setMaterial(road_mat, 1)
            mark_len = 2.5
            mark_w = 0.2
            mark_h = 0.004
            mark_gap = 4.0
            period = mark_len + mark_gap
            mark_z = road_top + mark_h / 2
            tip_clear = street_width * 1.1
            dist = [0.0]
            for i in range(len(pts) - 1):
                dist.append(
                    dist[-1]
                    + math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                )
            total = dist[-1]
            if total >= period + 2.0 * tip_clear:
                s = tip_clear + mark_len * 0.5
                while s < total - tip_clear:
                    ss = max(0.0, min(total, s))
                    j = 0
                    while j < len(dist) - 2 and dist[j + 1] < ss:
                        j += 1
                    span = dist[j + 1] - dist[j]
                    t = 0.0 if span < 1e-9 else (ss - dist[j]) / span
                    x0, y0 = pts[j]
                    x1, y1 = pts[j + 1]
                    dx = x1 - x0
                    dy = y1 - y0
                    length = math.hypot(dx, dy) or 1.0
                    ux, uy = dx / length, dy / length
                    x = x0 + dx * t
                    y = y0 + dy * t
                    heading = math.degrees(math.atan2(uy, ux))
                    mark = box_instance(self.streets, mark_len, mark_w, mark_h)
                    mark.setPos(x, y, mark_z)
                    mark.setH(heading)
                    mark.setMaterial(mark_paint, 1)
                    s += period
        for cx, cy, radius in streets["bulbs"]:
            pad = z_cylinder_instance(
                self.streets, radius, road_thickness, segments=28
            )
            pad.setPos(cx, cy, road_z)
            pad.setMaterial(road_mat, 1)
        self.streets.flattenStrong()

    def _build_chicago_housing(self, plan, arterials: list) -> None:
        """Inner-city fabric at startup; suburbs stream in via LOD ensure_housing_sectors."""
        body_tiles, _detail_tiles = build_chicago_housing(self.city, plan, arterials)
        self._housing_tiles = body_tiles
        self._housing_tiles_hidden = True

    def _build_chicago_airports(self) -> None:
        """Midway + O'Hare turf, runways, taxiways, and terminal massing."""
        self.airports, self._airport_tiles = build_chicago_airports(self.city)
        self._airport_tiles_hidden = True

    def _build_chicago_lights(self, arterials: list) -> None:
        """Street-light poles + emissive bulbs + additive ground-glow pools."""
        built = build_chicago_lights(self.city, arterials)
        self._lights_root = built["root"]
        self._lights_poles_root = built["poles_root"]
        self._lights_bulbs_root = built["bulbs_root"]
        self._lights_pools_root = built["pools_root"]
        self._lights_flicker_root = built["flicker_root"]
        self._lights_pole_tiles = built["pole_tiles"]
        self._lights_bulb_tiles = built["bulb_tiles"]
        self._lights_pool_tiles = built["pool_tiles"]
        self._lights_flickers = built["flickers"]
        self._street_lights_on = False
        self._lights_warmup_t = None
        self._lights_tiles_hidden = True

    def _build_signals(
        self, arterials: list, road_z: float, road_thickness: float
    ) -> None:
        """Chicago signal assemblies + crosswalk/stop-bar markings."""
        self.signals_root, self._signal_junctions, self._signal_tiles = (
            build_chicago_signals(
                self.render,
                arterials,
                road_z=road_z,
                road_thickness=road_thickness,
            )
        )
        self._signal_tiles_hidden = True
        self._signals = TrafficLightController(self)
        self.taskMgr.add(self._signals.update, "update_traffic_signals")

    def _build_ground(self, hwy: dict, road_z: float) -> None:
        lawn_mat = lawn_material()
        ground_pad = 40.0
        thickness = 0.16
        road_thickness = float(hwy.get("road_thickness", 0.1))
        # Top of baseplate flush with the underside of Z=0 road ribbons.
        ground_top = road_z - road_thickness * 0.5
        ground_center_z = ground_top - thickness * 0.5
        self._ground = box_instance(
            self.render,
            (hwy["bounds_east"] - hwy["bounds_west"]) + ground_pad,
            (hwy["bounds_north"] - hwy["bounds_south"]) + ground_pad,
            thickness,
        )
        self._ground.setPos(
            (hwy["bounds_west"] + hwy["bounds_east"]) / 2,
            (hwy["bounds_south"] + hwy["bounds_north"]) / 2,
            ground_center_z,
        )
        self._ground.setMaterial(lawn_mat, 1)
        self._ground_z = ground_top

    def _build_lighting(self) -> None:
        self._ambient_light = AmbientLight("ambient")
        self._ambient_np = self.render.attachNewNode(self._ambient_light)
        self.render.setLight(self._ambient_np)
        self._sun_light = DirectionalLight("sun")
        self._sun_np = self.render.attachNewNode(self._sun_light)
        self.render.setLight(self._sun_np)
        # Skip fill light — one directional + ambient is enough for flat roads.

        self._sky_root = self.camera.attachNewNode("sky-root")
        self._sky_root.setEffect(CompassEffect.make(self.render))
        self._sky_root.setBin("background", 0)
        self._sky_root.setDepthWrite(False)
        self._sky_root.setDepthTest(False)
        self._sky_root.setLightOff()
        self._sky_geom: object | None = None
        self._sky_key: tuple | None = None
        self._day_cycle = DayNightCycle(SUNRISE_SECONDS * 0.5)
        self._vehicle_lights_on = False
        self._apply_day_cycle(self._day_cycle.sample(), force_sky=True)

    def _build_traffic(self, plan, arterials: list, road_top: float) -> None:
        self._cars: list[CarController] = []
        self._car = None
        self._player_car: PlayerCar | None = None
        self._fleet_root = self.render.attachNewNode("fleet")

        # Green player car on State Street at Madison (right lane, southbound).
        state = next((a for a in arterials if a.get("name") == "state"), None)
        if state is not None:
            st_w = float(state.get("width", plan.road_width))
            # Deck top for this route + small lift so the body clears the ribbon.
            z_off = float(state.get("z_offset", 0.0))
            surface_z = road_top + z_off + 0.02
            self._player_car = PlayerCar(
                self,
                surface_z,
                -st_w / 4.0,
                -1.5,
                heading=-90.0,
                body_colour=(0.16, 0.62, 0.28),
            )
            self.taskMgr.add(self._player_drive_task, "player-drive")

    def _setup_camera(self, plan, road_z: float) -> None:
        del plan
        hwy = self._hwy
        left = hwy["bounds_west"]
        right = hwy["bounds_east"]
        frame_south = hwy["bounds_south"]
        frame_north = hwy["bounds_north"]
        self.look_at = (
            (left + right) / 2,
            (frame_south + frame_north) / 2,
            road_z,
        )
        self.heading = 0.0
        self.pitch = 68.0
        half_fov = math.tan(math.radians(20.0))
        fit_x = ((right - left) / 2) / half_fov
        fit_y = (
            ((frame_north - frame_south) / 2)
            / half_fov
            / max(0.25, math.cos(math.radians(self.pitch)))
        )
        self.distance = max(fit_x, fit_y) * 1.2
        self.min_distance = 2.0
        self.max_distance = max(200.0, self.distance * 2.5)
        # Chicago plate + O'Hare / I-57 spurs (see city.geo WORLD_*).
        self.camLens.setFar(CAMERA_FAR_CLIP)
        self.camLens.setNear(0.05)
        self._label_ref_distance = self.distance
        self.dragging = False
        self._drag_moved = False
        self._press_x = 0.0
        self._press_y = 0.0
        self.last_x = 0.0
        self.last_y = 0.0
        self._click_drag_threshold = 0.02
        self._dim_targets = list(self.city.getChildren())
        self._dim_targets.extend(
            (
                self.highway,
                self.streets,
                self._ground,
                self._fleet_root,
                self._highway_labels,
                self.signals_root,
                getattr(self, "_lights_root", None),
            )
        )
        self._dim_targets = [n for n in self._dim_targets if n is not None]
        self._default_look_at = list(self.look_at)
        self._default_distance = self.distance
        self._default_heading = self.heading
        self._default_pitch = self.pitch
        self._focus_index = -1
        # Chase / focus distances sized for the scaled 2× sedan (~0.05 wide).
        self._car_focus_distance = 1.2
        self._car_mode = False
        self._chase_back = 0.7
        self._chase_height = 0.28
        self._chase_look_ahead = 0.15
        self._chase_look_z = 0.06
        self._chase_yaw_offset = 0.0
        self._map_look_at = list(self.look_at)
        self._map_distance = self.distance
        self._map_heading = self.heading
        self._map_pitch = self.pitch

    def _setup_hud(self) -> None:
        self._hud_place_text = ""
        self._hud_street_text = ""
        self._hud_speed_text = ""
        self._hud_compass_text = ""
        self._speed_to_kmh = 3.6
        self._hud_place = OnscreenText(
            text="",
            parent=self.a2dTopLeft,
            pos=(0.05, -0.08),
            scale=0.055,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self._hud_street = OnscreenText(
            text="",
            parent=self.a2dTopCenter,
            pos=(0.0, -0.1),
            scale=0.07,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self._hud_compass = OnscreenText(
            text="",
            parent=self.a2dBottomRight,
            pos=(-0.06, 0.28),
            scale=0.07,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.75),
            align=TextNode.ARight,
            mayChange=True,
        )
        self._hud_speed = OnscreenText(
            text="",
            parent=self.a2dBottomRight,
            pos=(-0.06, 0.14),
            scale=0.1,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.75),
            align=TextNode.ARight,
            mayChange=True,
        )
        self._hud_speed_unit = OnscreenText(
            text="km/h",
            parent=self.a2dBottomRight,
            pos=(-0.06, 0.06),
            scale=0.045,
            fg=(0.85, 0.88, 0.92, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ARight,
            mayChange=False,
        )
        self._hud_place.hide()
        self._hud_street.hide()
        self._hud_compass.hide()
        self._hud_speed.hide()
        self._hud_speed_unit.hide()
        self._hud_clock = OnscreenText(
            text=self._day_cycle.clock_text(),
            parent=self.a2dTopCenter,
            pos=(0.0, -0.08),
            scale=0.065,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self._hud_clock_text = ""
        self._layout_clock_hud()
        self._update_camera()

    def _bind_controls(self) -> None:
        self.accept("escape", sys.exit)
        self.accept("enter", self._toggle_car_mode)
        self.accept("space", self._cycle_car_focus)
        self.accept("backspace", self._clear_district_selection)
        self.accept("c", self._select_chicago)
        self.accept("l", self._select_the_loop)
        self.accept("n", self._select_river_north)
        self.accept("w", self._select_west_town)
        self.accept("h", self._select_hyde_park)
        self.accept("wheel_up", self._zoom, [0.94])
        self.accept("wheel_down", self._zoom, [1.0 / 0.94])
        step = PlayerCar._SPEED_STEP_KMH
        self.accept("arrow_up", self._bump_player_speed_limit, [step])
        self.accept("arrow_down", self._bump_player_speed_limit, [-step])
        self.accept("mouse1", self._start_drag)
        self.accept("mouse1-up", self._end_drag)
        self.taskMgr.add(self._drag_task, "orbit-drag")
        self.taskMgr.add(self._pan_task, "camera-pan")
        self.taskMgr.add(self._follow_focus_task, "follow-car-focus")
        self.taskMgr.add(self._car_hud_task, "car-hud")
        self.taskMgr.add(self._day_cycle_task, "day-night-cycle")
        self.taskMgr.add(self._street_lights_task, "street-lights")
        if not self.screenshot_path:
            self.fps_text = OnscreenText(
                text="",
                parent=self.a2dTopRight,
                pos=(-0.04, -0.08),
                scale=0.09,
                fg=(0.12, 0.14, 0.18, 1),
                align=TextNode.ARight,
                mayChange=True,
            )
            self.taskMgr.add(self._fps_task, "fps-counter")

    def _fps_task(self, task):
        # Text updates are relatively expensive; twice a second is enough.
        slot = int(task.time * 2.0)
        if slot == getattr(self, "_fps_slot", -1):
            return task.cont
        self._fps_slot = slot
        self.fps_text.setText(f"FPS: {self.clock.getAverageFrameRate():.0f}")
        return task.cont

    def _layout_clock_hud(self) -> None:
        """Map mode: top centre. Car mode: bottom left (street name keeps the top)."""
        if not hasattr(self, "_hud_clock"):
            return
        if self._car_mode:
            self._hud_clock.reparentTo(self.a2dBottomLeft)
            self._hud_clock.setPos(0.05, 0.1)
            self._hud_clock.setAlign(TextNode.ALeft)
        else:
            self._hud_clock.reparentTo(self.a2dTopCenter)
            self._hud_clock.setPos(0.0, -0.08)
            self._hud_clock.setAlign(TextNode.ACenter)

    def _day_cycle_task(self, task):
        self._day_cycle.update(self.clock.getDt())
        # Lights/sky don't need per-frame updates — throttle heavily.
        slot = int(task.time * _DAY_CYCLE_HZ)
        if slot != getattr(self, "_day_slot", -1):
            self._day_slot = slot
            self._apply_day_cycle(self._day_cycle.sample())
        return task.cont

    def _set_street_lights(self, on: bool, *, warm_up: bool = False) -> None:
        """Show/hide bulbs + pools; on at night, off by day (driven by day cycle)."""
        self._street_lights_on = on
        bulbs = getattr(self, "_lights_bulbs_root", None)
        pools = getattr(self, "_lights_pools_root", None)
        flicker = getattr(self, "_lights_flicker_root", None)
        if bulbs is None or pools is None:
            return
        if on:
            self._lights_warmup_t = 0.0 if warm_up else None
            bulbs.show()
            pools.show()
            if flicker is not None:
                flicker.show()
            bulbs.setColorScale(1, 1, 1, 0.4 if warm_up else 1.0)
            pools.setColorScale(1, 1, 1, 0.2 if warm_up else 1.0)
        else:
            self._lights_warmup_t = None
            bulbs.hide()
            pools.hide()
            if flicker is not None:
                flicker.hide()
            bulbs.setColorScale(1, 1, 1, 1)
            pools.setColorScale(1, 1, 1, 1)

    def _street_lights_task(self, task):
        """Warm-up fade only — LOD owns which sectors are visible."""
        warm = getattr(self, "_lights_warmup_t", None)
        if warm is None or not self._street_lights_on:
            return task.cont
        self._lights_warmup_t = warm + self.clock.getDt()
        u = min(1.0, self._lights_warmup_t / WARMUP_SECONDS)
        bulbs = getattr(self, "_lights_bulbs_root", None)
        pools = getattr(self, "_lights_pools_root", None)
        if bulbs is not None:
            bulbs.setColorScale(1, 1, 1, 0.4 + 0.6 * u)
        if pools is not None:
            pools.setColorScale(1, 1, 1, 0.2 + 0.8 * u)
        if u >= 1.0:
            self._lights_warmup_t = None
            if bulbs is not None:
                bulbs.setColorScale(1, 1, 1, 1)
            if pools is not None:
                pools.setColorScale(1, 1, 1, 1)
        return task.cont

    def _apply_day_cycle(self, sample, *, force_sky: bool = False) -> None:
        """Push cycle sample into lights, clear colour, sky dome, and clock."""
        prev_vehicle = getattr(self, "_vehicle_lights_on", False)
        self._vehicle_lights_on = sample.vehicle_lights_on
        # Street lights follow dusk/dawn with the day cycle.
        if hasattr(self, "_lights_bulbs_root"):
            if prev_vehicle != self._vehicle_lights_on:
                self._set_street_lights(
                    self._vehicle_lights_on, warm_up=self._vehicle_lights_on
                )
            elif not getattr(self, "_street_lights_synced", False):
                self._street_lights_synced = True
                self._set_street_lights(self._vehicle_lights_on, warm_up=False)

        ar, ag, ab = sample.ambient
        self._ambient_light.setColor((ar, ag, ab, 1))
        sr, sg, sb = sample.sun_color
        self._sun_light.setColor((sr, sg, sb, 1))
        self._sun_np.setHpr(*sample.sun_hpr)
        br, bg, bb = sample.background
        self.setBackgroundColor(br, bg, bb, 1)

        # Coarse key — avoid rebuilding the sky dome every frame as the sun creeps.
        sky_key = (
            round(sample.zenith[0], 2),
            round(sample.zenith[1], 2),
            round(sample.zenith[2], 2),
            round(sample.horizon_cool[0], 2),
            round(sample.horizon_cool[1], 2),
            round(sample.horizon_cool[2], 2),
            round(sample.horizon_warm[0], 2),
            round(sample.horizon_warm[1], 2),
            round(sample.horizon_warm[2], 2),
            round(sample.sun_phi_deg, 0),
        )
        if force_sky or sky_key != self._sky_key:
            self._sky_key = sky_key
            if self._sky_geom is not None:
                self._sky_geom.removeNode()
            # Stronger horizon glow during warm sunrise/sunset keys.
            warm = sample.horizon_warm
            glow = 0.18 + 0.35 * max(0.0, warm[0] - warm[2])
            self._sky_geom = self._sky_root.attachNewNode(
                make_sky_dome(
                    zenith=sample.zenith,
                    horizon_cool=sample.horizon_cool,
                    horizon_warm=sample.horizon_warm,
                    sun_phi_deg=sample.sun_phi_deg,
                    glow_strength=glow,
                )
            )
            self._sky_geom.setBin("background", 0)
            self._sky_geom.setDepthWrite(False)
            self._sky_geom.setDepthTest(False)
            self._sky_geom.setLightOff()

        if hasattr(self, "_hud_clock") and sample.clock_text != self._hud_clock_text:
            self._hud_clock_text = sample.clock_text
            self._hud_clock.setText(sample.clock_text)

        # Player car only runs its update loop in car mode — sync night lamps here.
        player = getattr(self, "_player_car", None)
        if player is not None and not getattr(self, "_car_mode", False):
            player._refresh_lamps(braking=False, reversing=False)

    def _fleet_task(self, task):
        # One spatial/corridor index for the whole fleet, then each car updates.
        CarController.build_fleet_index(self._cars)
        for car in self._cars:
            car._car_task(task)
        # Overview: hide most cars (they're dots). Close-up: hide far cars.
        lx, ly, _lz = self.look_at
        if self.distance >= 70.0:
            hide_r2 = 55.0 * 55.0
        else:
            hide_r2 = 95.0 * 95.0
        for car in self._cars:
            dx = car._car_pos[0] - lx
            dy = car._car_pos[1] - ly
            far = dx * dx + dy * dy > hide_r2
            if far and not car.car.isHidden():
                car.car.hide()
            elif not far and car.car.isHidden():
                car.car.show()
        return task.cont

    def _focusable_cars(self) -> list:
        """Player car first, then AI fleet — Space cycles through these."""
        cars: list = []
        if self._player_car is not None:
            cars.append(self._player_car)
        cars.extend(self._cars)
        return cars

    def _car_look_at(self, car) -> list[float]:
        return [car._car_pos[0], car._car_pos[1], car._car_z + 0.5]

    def _toggle_car_mode(self) -> None:
        """Enter: enter/exit third-person drive mode on the green player car."""
        if self._player_car is None:
            return
        if self._car_mode:
            self._exit_car_mode()
        else:
            self._enter_car_mode()

    def _enter_car_mode(self) -> None:
        self._car_mode = True
        self._lod_key = None
        self._clear_district_selection()
        self._focus_index = -1
        self.dragging = False
        self._map_look_at = list(self.look_at)
        self._map_distance = self.distance
        self._map_heading = self.heading
        self._map_pitch = self.pitch
        self._chase_yaw_offset = 0.0
        self._hud_place_text = ""
        self._hud_street_text = ""
        self._hud_speed_text = ""
        self._hud_compass_text = ""
        # World-space arterial titles clutter the chase cam; HUD keeps the name.
        self._highway_labels.hide()
        self._hud_place.show()
        self._hud_street.show()
        self._hud_compass.show()
        self._hud_speed.show()
        self._hud_speed_unit.show()
        self._layout_clock_hud()
        self._refresh_car_hud(force=True)
        self._update_chase_camera()

    def _exit_car_mode(self) -> None:
        self._car_mode = False
        self._lod_key = None
        self.dragging = False
        self._highway_labels.show()
        self._hud_place.hide()
        self._hud_street.hide()
        self._hud_compass.hide()
        self._hud_speed.hide()
        self._hud_speed_unit.hide()
        self._hud_place.setText("")
        self._hud_street.setText("")
        self._hud_compass.setText("")
        self._hud_speed.setText("")
        self._layout_clock_hud()
        self.look_at = list(self._map_look_at)
        self.distance = self._map_distance
        self.heading = self._map_heading
        self.pitch = self._map_pitch
        self._update_camera()

    @staticmethod
    def _build_segment_grid(
        segments: list, *, xy_offset: int, cell: float
    ) -> dict[tuple[int, int], list[int]]:
        """Hash segment indices by AABB cells for nearby queries."""
        grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        if cell <= 0.0:
            return grid
        for idx, seg in enumerate(segments):
            ax = float(seg[xy_offset])
            ay = float(seg[xy_offset + 1])
            bx = float(seg[xy_offset + 2])
            by = float(seg[xy_offset + 3])
            half_w = float(seg[-1])
            pad = half_w + 1.0
            i0 = int(math.floor((min(ax, bx) - pad) / cell))
            i1 = int(math.floor((max(ax, bx) + pad) / cell))
            j0 = int(math.floor((min(ay, by) - pad) / cell))
            j1 = int(math.floor((max(ay, by) + pad) / cell))
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    grid[(i, j)].append(idx)
        return grid

    def _nearby_segment_indices(
        self,
        grid: dict[tuple[int, int], list[int]],
        x: float,
        y: float,
        radius: float,
        cell: float,
    ) -> list[int]:
        if not grid or cell <= 0.0:
            return []
        i0 = int(math.floor((x - radius) / cell))
        i1 = int(math.floor((x + radius) / cell))
        j0 = int(math.floor((y - radius) / cell))
        j1 = int(math.floor((y + radius) / cell))
        seen: set[int] = set()
        out: list[int] = []
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                for idx in grid.get((i, j), ()):
                    if idx not in seen:
                        seen.add(idx)
                        out.append(idx)
        return out

    def nearby_barriers(
        self, x: float, y: float, radius: float
    ) -> list[tuple[float, float, float, float, float]]:
        idxs = self._nearby_segment_indices(
            getattr(self, "_barrier_grid", {}),
            x,
            y,
            radius,
            getattr(self, "_barrier_cell", _SEG_CELL),
        )
        barriers = getattr(self, "_solid_barriers", None) or []
        return [barriers[i] for i in idxs]

    def nearby_roads(
        self, x: float, y: float, radius: float
    ) -> list[tuple[str, float, float, float, float, float]]:
        idxs = self._nearby_segment_indices(
            getattr(self, "_road_grid", {}),
            x,
            y,
            radius,
            getattr(self, "_road_cell", _SEG_CELL),
        )
        roads = getattr(self, "_named_roads", None) or []
        return [roads[i] for i in idxs]

    def _location_at(self, x: float, y: float) -> str:
        """Neighborhood + municipality for car HUD, e.g. 'Newton, Surrey'."""
        for key, area, city in LOCATION_AREAS:
            district = self._districts.get(key)
            if district is None:
                continue
            if self._point_in_ring(district["ring"], x, y):
                return f"{area}, {city}"
        return "Unknown area"

    def _street_at(self, x: float, y: float) -> str:
        """Nearest arterial name if the car is on/near its pavement."""
        best_name = ""
        best_d2 = float("inf")
        for name, ax, ay, bx, by, half_w in self.nearby_roads(x, y, 2.0):
            d2, _qx, _qy = _dist2_point_segment(x, y, ax, ay, bx, by)
            # Stay within the ribbon plus a small shoulder so lane offset still counts.
            limit = half_w + ROAD_SHOULDER
            if d2 <= limit * limit and d2 < best_d2:
                best_d2 = d2
                best_name = name
        return best_name or "Off road"

    @staticmethod
    def _compass_from_heading(heading_deg: float) -> str:
        """Cardinal label from car yaw (0° = +X east, 90° = +Y north)."""
        bearing = (90.0 - heading_deg) % 360.0
        dirs = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        return dirs[int((bearing + 22.5) // 45.0) % 8]

    def _refresh_speedometer(self, *, force: bool = False) -> None:
        if self._player_car is None:
            return
        kmh = int(round(abs(self._player_car._car_speed) * self._speed_to_kmh))
        text = str(kmh)
        if force or text != self._hud_speed_text:
            self._hud_speed_text = text
            self._hud_speed.setText(text)

    def _refresh_compass(self, *, force: bool = False) -> None:
        if self._player_car is None:
            return
        text = self._compass_from_heading(self._player_car._car_heading)
        if force or text != self._hud_compass_text:
            self._hud_compass_text = text
            self._hud_compass.setText(text)

    def _refresh_car_hud(self, *, force: bool = False) -> None:
        if self._player_car is None:
            return
        x, y = self._player_car._car_pos[0], self._player_car._car_pos[1]
        place = self._location_at(x, y)
        street = self._street_at(x, y)
        if force or place != self._hud_place_text:
            self._hud_place_text = place
            self._hud_place.setText(place)
        if force or street != self._hud_street_text:
            self._hud_street_text = street
            self._hud_street.setText(street)
        self._refresh_compass(force=force)
        self._refresh_speedometer(force=force)

    def _car_hud_task(self, task):
        if not self._car_mode:
            return task.cont
        # Speed / compass update snappier; place/street can lag a bit.
        speed_slot = int(task.time * 12.0)
        if speed_slot != getattr(self, "_hud_speed_slot", -1):
            self._hud_speed_slot = speed_slot
            self._refresh_speedometer()
            self._refresh_compass()
        slot = int(task.time * 4.0)
        if slot == getattr(self, "_hud_slot", -1):
            return task.cont
        self._hud_slot = slot
        self._refresh_car_hud()
        return task.cont

    def _update_chase_camera(self) -> None:
        """Fortnite-style chase: behind + above the car, optional mouse yaw offset."""
        car = self._player_car
        if car is None:
            return
        rad = math.radians(car._car_heading + self._chase_yaw_offset)
        fx = math.cos(rad)
        fy = math.sin(rad)
        px, py = car._car_pos[0], car._car_pos[1]
        pz = car._car_z
        self.camera.setPos(
            px - fx * self._chase_back,
            py - fy * self._chase_back,
            pz + self._chase_height,
        )
        look_x = px + fx * self._chase_look_ahead
        look_y = py + fy * self._chase_look_ahead
        look_z = pz + self._chase_look_z
        self.camera.lookAt(look_x, look_y, look_z)
        self.look_at = [look_x, look_y, look_z]
        # Local minor tiles around the car (map-mode distance would hide them).
        saved = self.distance
        self.distance = 60.0
        self._update_road_lod(px, py)
        self.distance = saved

    def _cycle_car_focus(self) -> None:
        """Space: zoom to next car; after the last car, restore the city overview."""
        if self._car_mode:
            return
        cars = self._focusable_cars()
        if not cars:
            return
        self._focus_index += 1
        if self._focus_index >= len(cars):
            self._focus_index = -1
            self.look_at = list(self._default_look_at)
            self.distance = self._default_distance
            self.heading = self._default_heading
            self.pitch = self._default_pitch
            self._update_camera()
            return

        car = cars[self._focus_index]
        self.look_at = self._car_look_at(car)
        self.distance = min(
            self.max_distance,
            max(self.min_distance, self._car_focus_distance),
        )
        # Top-down follow; keep heading so the city stays oriented.
        self.pitch = 85.0
        self._update_camera()

    def _follow_focus_task(self, task):
        if self._car_mode:
            self._update_chase_camera()
            return task.cont
        cars = self._focusable_cars()
        if 0 <= self._focus_index < len(cars):
            self.look_at = self._car_look_at(cars[self._focus_index])
            self._update_camera()
        return task.cont

    def _bump_player_speed_limit(self, delta_kmh: float) -> None:
        """↑/↓: nudge forward cruise cap by 10 km/h (0–600), car mode only."""
        if not self._car_mode or self._player_car is None:
            return
        self._player_car.bump_speed_limit(delta_kmh)

    def _player_drive_task(self, task):
        """Car mode: WASD drive; ←/→ trim heading; ↑/↓ set cruise limit."""
        if not self._car_mode or self._player_car is None:
            return task.cont
        mw = self.mouseWatcherNode
        self._player_car.update(
            self.clock.getDt(),
            gas=mw.is_button_down(KeyboardButton.ascii_key("w")),
            brake=mw.is_button_down(KeyboardButton.ascii_key("s")),
            steer_left=mw.is_button_down(KeyboardButton.ascii_key("a")),
            steer_right=mw.is_button_down(KeyboardButton.ascii_key("d")),
            nudge_left=mw.is_button_down(KeyboardButton.left()),
            nudge_right=mw.is_button_down(KeyboardButton.right()),
        )
        return task.cont

    def _update_camera(self) -> None:
        if self._car_mode:
            self._update_chase_camera()
            return
        pitch = math.radians(self.pitch)
        heading = math.radians(self.heading)
        cos_pitch = math.cos(pitch)
        look_x, look_y, look_z = self.look_at
        self.camera.setPos(
            look_x + self.distance * math.sin(heading) * cos_pitch,
            look_y - self.distance * math.cos(heading) * cos_pitch,
            look_z + self.distance * math.sin(pitch),
        )
        self.camera.lookAt(look_x, look_y, look_z)
        self._update_road_lod(look_x, look_y)

    def _update_road_lod(self, look_x: float, look_y: float) -> None:
        """Show only nearby minor tiles + a handful of road labels."""
        dist = self.distance
        # Skip work when the camera hasn't moved enough to change LOD.
        lod_key = (
            int(look_x // 8.0),
            int(look_y // 8.0),
            int(dist // 12.0),
            bool(self._car_mode),
        )
        if lod_key == getattr(self, "_lod_key", None):
            selected = getattr(self, "_selected_district", None)
            if selected is not None:
                district = self._districts.get(selected)
                if district is not None:
                    label = district.get("label")
                    if label is not None and not label.isHidden():
                        ref = max(self._label_ref_distance, 1e-6)
                        label.setScale(district["label_scale"] * (dist / ref))
            return
        self._lod_key = lod_key

        # ---- Collectors (citywide mesh — hide in overview) ----
        if dist >= _COLLECTOR_HIDE_DIST and not self._car_mode:
            if not getattr(self, "_collectors_hidden", False):
                self.collectors_node.hide()
                self._collectors_hidden = True
        else:
            if getattr(self, "_collectors_hidden", False):
                self.collectors_node.show()
                self._collectors_hidden = False

        def _show_nearby_tiles(tiles, *, hide_dist: float, pad: float, hidden_attr: str) -> None:
            if dist >= hide_dist and not self._car_mode:
                if not getattr(self, hidden_attr, False):
                    for _cx, _cy, node in tiles:
                        if not node.isHidden():
                            node.hide()
                    setattr(self, hidden_attr, True)
                return
            setattr(self, hidden_attr, False)
            radius = max(70.0, dist * 0.45) + pad
            r2 = radius * radius
            for cx, cy, node in tiles:
                dx = cx - look_x
                dy = cy - look_y
                near = dx * dx + dy * dy <= r2
                if near and node.isHidden():
                    node.show()
                elif not near and not node.isHidden():
                    node.hide()

        # ---- Minor street tiles ----
        _show_nearby_tiles(
            getattr(self, "_minor_tiles", None) or [],
            hide_dist=_MINOR_HIDE_DIST,
            pad=_MINOR_TILE * 0.5,
            hidden_attr="_minor_tiles_hidden",
        )
        # ---- Signal tiles ----
        _show_nearby_tiles(
            getattr(self, "_signal_tiles", None) or [],
            hide_dist=_SIGNAL_HIDE_DIST,
            pad=_MINOR_TILE * 0.5,
            hidden_attr="_signal_tiles_hidden",
        )
        # ---- Airports (hide in overview; show only when look-point is near) ----
        airport_tiles = getattr(self, "_airport_tiles", None) or []
        if airport_tiles:
            if dist >= _AIRPORT_HIDE_DIST and not self._car_mode:
                if not getattr(self, "_airport_tiles_hidden", False):
                    for _cx, _cy, _rad, node in airport_tiles:
                        if not node.isHidden():
                            node.hide()
                    self._airport_tiles_hidden = True
            else:
                self._airport_tiles_hidden = False
                # Radius grows slightly with zoom so approach from highways still shows.
                pad = max(40.0, dist * 0.25)
                for cx, cy, rad, node in airport_tiles:
                    dx = cx - look_x
                    dy = cy - look_y
                    near = dx * dx + dy * dy <= (rad + pad) * (rad + pad)
                    if near and node.isHidden():
                        node.show()
                    elif not near and not node.isHidden():
                        node.hide()

        # ---- Residential mile-sectors (flattened GeomNodes; cap count) ----
        housing_tiles = getattr(self, "_housing_tiles", None) or []
        if dist >= _HOUSING_HIDE_DIST and not self._car_mode:
            if not getattr(self, "_housing_tiles_hidden", False):
                for _cx, _cy, node in housing_tiles:
                    if not node.isHidden():
                        node.hide()
                self._housing_tiles_hidden = True
        else:
            self._housing_tiles_hidden = False
            radius = max(HOUSING_VIEW_MIN, dist * HOUSING_VIEW_FACTOR) + SECTOR_SIZE * 0.35
            # Time-sliced suburb bake (prefetch); never blocks a full sector/frame.
            ensure_housing_sectors(look_x, look_y, radius, housing_tiles)
            r2 = radius * radius
            scored: list[tuple[float, object]] = []
            for cx, cy, node in housing_tiles:
                dx = cx - look_x
                dy = cy - look_y
                d2 = dx * dx + dy * dy
                if d2 <= r2:
                    scored.append((d2, node))
                elif not node.isHidden():
                    node.hide()
            scored.sort(key=lambda item: item[0])
            for i, (_d2, node) in enumerate(scored):
                if i < _HOUSING_MAX_TILES:
                    if node.isHidden():
                        node.show()
                elif not node.isHidden():
                    node.hide()
        # ---- Street-light mile-sectors (poles always; bulbs/pools when lit) ----
        def _lod_light_tiles(
            tiles,
            *,
            hidden_attr: str,
            max_tiles: int,
            force_hide: bool = False,
        ) -> None:
            if not tiles:
                return
            if force_hide or (dist >= _LIGHTS_HIDE_DIST and not self._car_mode):
                if not getattr(self, hidden_attr, False):
                    for _cx, _cy, node in tiles:
                        if not node.isHidden():
                            node.hide()
                    setattr(self, hidden_attr, True)
                return
            setattr(self, hidden_attr, False)
            radius = max(LIGHTS_VIEW_MIN, dist * LIGHTS_VIEW_FACTOR) + SECTOR_SIZE * 0.25
            r2 = radius * radius
            scored: list[tuple[float, object]] = []
            for cx, cy, node in tiles:
                dx = cx - look_x
                dy = cy - look_y
                d2 = dx * dx + dy * dy
                if d2 <= r2:
                    scored.append((d2, node))
                elif not node.isHidden():
                    node.hide()
            scored.sort(key=lambda item: item[0])
            for i, (_d2, node) in enumerate(scored):
                if i < max_tiles:
                    if node.isHidden():
                        node.show()
                elif not node.isHidden():
                    node.hide()

        lit = getattr(self, "_street_lights_on", False)
        _lod_light_tiles(
            getattr(self, "_lights_pole_tiles", None) or [],
            hidden_attr="_lights_pole_tiles_hidden",
            max_tiles=_LIGHTS_MAX_TILES,
        )
        # Bulbs + additive pools only while lit — biggest night-time GPU cost.
        _lod_light_tiles(
            getattr(self, "_lights_bulb_tiles", None) or [],
            hidden_attr="_lights_bulb_tiles_hidden",
            max_tiles=_LIGHTS_MAX_TILES,
            force_hide=not lit,
        )
        _lod_light_tiles(
            getattr(self, "_lights_pool_tiles", None) or [],
            hidden_attr="_lights_pool_tiles_hidden",
            max_tiles=_LIGHTS_MAX_POOL_TILES,
            force_hide=not lit,
        )
        # ---- Highway labels (nearest N only; skip when far / car mode) ----
        labels = getattr(self, "_highway_label_nodes", None) or []
        if dist >= _LABEL_HIDE_DIST or self._car_mode:
            if not self._highway_labels.isHidden():
                self._highway_labels.hide()
        else:
            if self._highway_labels.isHidden():
                self._highway_labels.show()
            scored: list[tuple[float, object]] = []
            for label, lx, ly in labels:
                dx = lx - look_x
                dy = ly - look_y
                scored.append((dx * dx + dy * dy, label))
            scored.sort(key=lambda item: item[0])
            visible = {id(item[1]) for item in scored[:_LABEL_MAX_VISIBLE]}
            ref = max(self._label_ref_distance, 1e-6)
            zoom = dist / ref
            scale = self._label_base_scale * zoom
            for _d2, label in scored:
                show = id(label) in visible
                if show:
                    if label.isHidden():
                        label.show()
                    label.setScale(scale)
                elif not label.isHidden():
                    label.hide()

        # District label scale tracks zoom only when one is selected.
        selected = getattr(self, "_selected_district", None)
        if selected is not None:
            district = self._districts.get(selected)
            if district is not None:
                label = district.get("label")
                if label is not None and not label.isHidden():
                    ref = max(self._label_ref_distance, 1e-6)
                    label.setScale(district["label_scale"] * (dist / ref))

    def _zoom(self, factor: float) -> None:
        if self._car_mode:
            self._chase_back = min(2.5, max(0.25, self._chase_back * factor))
            self._chase_height = min(1.2, max(0.08, self._chase_height * factor))
            self._update_chase_camera()
            return
        self.distance = min(
            self.max_distance,
            max(self.min_distance, self.distance * factor),
        )
        # While following a car, keep wheel zoom as the new follow distance.
        if self._focus_index >= 0:
            self._car_focus_distance = self.distance
        self._update_camera()

    def _build_district_outline(self, key: str, ring: tuple, z: float):
        """Dashed red outline along a district's arterial ring."""
        segs = LineSegs(f"district-outline-{key}")
        segs.setThickness(3.0)
        segs.setColor(0.86, 0.12, 0.1, 1.0)
        dash = 2.4
        gap = 1.3
        for i in range(len(ring)):
            x0, y0 = ring[i]
            x1, y1 = ring[(i + 1) % len(ring)]
            dx = x1 - x0
            dy = y1 - y0
            length = math.hypot(dx, dy)
            if length < 1e-6:
                continue
            ux = dx / length
            uy = dy / length
            t = 0.0
            drawing = True
            while t < length:
                seg_len = dash if drawing else gap
                t_end = min(length, t + seg_len)
                if drawing:
                    segs.moveTo(x0 + ux * t, y0 + uy * t, z)
                    segs.drawTo(x0 + ux * t_end, y0 + uy * t_end, z)
                t = t_end
                drawing = not drawing
        return self.render.attachNewNode(segs.create())

    @staticmethod
    def _point_in_ring(ring: tuple, x: float, y: float) -> bool:
        """True if (x, y) is inside the ring (even-odd fill)."""
        n = len(ring)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi
            ):
                inside = not inside
            j = i
        return inside

    def _ground_hit_xy(self) -> tuple[float, float] | None:
        """Ray from camera through the mouse onto the ground plane."""
        if not self.mouseWatcherNode.hasMouse():
            return None
        mpos = self.mouseWatcherNode.getMouse()
        near = Point3()
        far = Point3()
        self.camLens.extrude(mpos, near, far)
        near_w = self.render.getRelativePoint(self.cam, near)
        far_w = self.render.getRelativePoint(self.cam, far)
        dz = far_w.z - near_w.z
        if abs(dz) < 1e-9:
            return None
        t = (self._ground_z - near_w.z) / dz
        if t < 0.0:
            return None
        return (
            near_w.x + (far_w.x - near_w.x) * t,
            near_w.y + (far_w.y - near_w.y) * t,
        )

    def _ensure_district_label(self, key: str):
        district = self._districts[key]
        label = district.get("label")
        if label is not None:
            return label
        text = TextNode(f"district-label-{key}")
        text.setText(district["title"])
        text.setAlign(TextNode.ACenter)
        text.setTextColor(0.86, 0.12, 0.1, 1)
        pivot = self.render.attachNewNode(f"district-label-pivot-{key}")
        lx, ly = district["label_xy"]
        pivot.setPos(lx, ly, district["label_z"])
        label = pivot.attachNewNode(text)
        label.setScale(district["label_scale"])
        label.setBillboardPointEye()
        label.setDepthTest(False)
        label.setDepthWrite(False)
        district["label"] = label
        return label

    def _select_district(self, key: str) -> None:
        if key not in self._districts:
            return
        if self._selected_district == key:
            return
        self._clear_district_selection()
        district = self._districts[key]
        self._selected_district = key
        dim = (0.55, 0.55, 0.55, 1.0)
        bright = district.get("bright")
        for node in self._dim_targets:
            if bright is not None and node == bright:
                continue
            node.setColorScale(*dim)
        district["outline"].show()
        label = self._ensure_district_label(key)
        label.show()

    def _clear_district_selection(self) -> None:
        if self._selected_district is None:
            return
        district = self._districts[self._selected_district]
        self._selected_district = None
        for node in self._dim_targets:
            node.clearColorScale()
        district["outline"].hide()
        label = district.get("label")
        if label is not None:
            label.hide()

    def _select_chicago(self) -> None:
        """C: outline City of Chicago plate (disabled in car mode)."""
        if self._car_mode:
            return
        self._select_district("chicago")

    def _select_the_loop(self) -> None:
        """L: outline The Loop (disabled in car mode)."""
        if self._car_mode:
            return
        self._select_district("the_loop")

    def _select_river_north(self) -> None:
        """N: outline River North (disabled in car mode)."""
        if self._car_mode:
            return
        self._select_district("river_north")

    def _select_west_town(self) -> None:
        """W: outline West Town (disabled in car mode)."""
        if self._car_mode:
            return
        self._select_district("west_town")

    def _select_hyde_park(self) -> None:
        """H: outline Hyde Park (disabled in car mode)."""
        if self._car_mode:
            return
        self._select_district("hyde_park")

    def _try_select_district(self) -> None:
        if self._car_mode:
            return
        hit = self._ground_hit_xy()
        if hit is None:
            return
        x, y = hit
        for key, district in self._districts.items():
            if district.get("hotkey_only"):
                continue
            if self._point_in_ring(district["ring"], x, y):
                self._select_district(key)
                return

    def _start_drag(self) -> None:
        if not self.mouseWatcherNode.hasMouse():
            return
        self.dragging = True
        self._drag_moved = False
        self.last_x = self.mouseWatcherNode.getMouseX()
        self.last_y = self.mouseWatcherNode.getMouseY()
        self._press_x = self.last_x
        self._press_y = self.last_y

    def _end_drag(self) -> None:
        was_click = self.dragging and not self._drag_moved
        self.dragging = False
        # District pick is map-only; car mode keeps mouse for chase orbit.
        if was_click and not self._car_mode:
            self._try_select_district()

    def _drag_task(self, task):
        if self.dragging and self.mouseWatcherNode.hasMouse():
            x = self.mouseWatcherNode.getMouseX()
            y = self.mouseWatcherNode.getMouseY()
            if (
                abs(x - self._press_x) > self._click_drag_threshold
                or abs(y - self._press_y) > self._click_drag_threshold
            ):
                self._drag_moved = True
            if self._drag_moved:
                dx = x - self.last_x
                dy = y - self.last_y
                if self._car_mode:
                    # Orbit chase yaw; nudge height like a light pitch look.
                    self._chase_yaw_offset -= dx * 120.0
                    self._chase_height = max(
                        0.08, min(1.2, self._chase_height + dy * 0.45)
                    )
                    self._update_chase_camera()
                else:
                    self.heading -= dx * 120.0
                    self.pitch = max(-85.0, min(85.0, self.pitch + dy * 90.0))
                    self._update_camera()
            self.last_x = x
            self.last_y = y
        return task.cont

    def _pan_task(self, task):
        """Arrow keys: pan look_at on the ground plane (disabled in car mode)."""
        if self._car_mode:
            return task.cont
        mw = self.mouseWatcherNode
        forward = 0.0
        right = 0.0
        if mw.is_button_down(KeyboardButton.up()):
            forward += 1.0
        if mw.is_button_down(KeyboardButton.down()):
            forward -= 1.0
        if mw.is_button_down(KeyboardButton.right()):
            right += 1.0
        if mw.is_button_down(KeyboardButton.left()):
            right -= 1.0
        if forward == 0.0 and right == 0.0:
            return task.cont

        # Leave car follow so pan isn't overwritten every frame.
        if self._focus_index >= 0:
            self._focus_index = -1

        heading = math.radians(self.heading)
        # Match _update_camera: heading 0 looks along +Y.
        fx = -math.sin(heading)
        fy = math.cos(heading)
        rx = math.cos(heading)
        ry = math.sin(heading)
        speed = self.distance * 0.85 * self.clock.getDt()
        look_x, look_y, look_z = self.look_at
        self.look_at = (
            look_x + (fx * forward + rx * right) * speed,
            look_y + (fy * forward + ry * right) * speed,
            look_z,
        )
        self._update_camera()
        return task.cont

    def capture(self) -> None:
        for _ in range(3):
            self.graphicsEngine.renderFrame()
        path = Filename.fromOsSpecific(self.screenshot_path)
        if not self.win.saveScreenshot(path):
            raise SystemExit(f"Could not write {self.screenshot_path}")
        print(f"Wrote {self.screenshot_path}")
