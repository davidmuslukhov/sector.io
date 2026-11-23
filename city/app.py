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
    DISTRICT_DEFS,
    HIGHWAY_LABELS,
    LOCATION_AREAS,
)
from city.materials import (
    concrete_material,
    lawn_material,
    mark_material,
    road_material,
)
from city.mesh import (
    _dist2_point_segment,
    arterial_topology,
    box_instance,
    make_highway_ribbon,
    make_sky_dome,
    offset_polyline,
    split_polyline_around_gaps,
    z_cylinder_instance,
)
from city.plan import default_city_plan
# Spatial hash cell size for barrier / road lookups (car-mode hot path).
_SEG_CELL = 4.0
# Barrier prism length target — thin 2× ribbons; coarsen lightly for FPS.
_BARRIER_SPAN = 1.2
# Drop leftover stubs between nearby crossings.
_BARRIER_MIN_RUN = 2.5


class CityApp(ShowBase):
    def __init__(self, screenshot: str | None = None) -> None:
        super().__init__()
        self.screenshot_path = screenshot
        self.disableMouse()
        self.setBackgroundColor(0.7, 0.78, 0.88, 1)

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
        # Buildings, water, and bridges stripped — roads + green baseplate.
        self._build_city_centre(plan, road_z, arterials)
        self._build_districts(road_z, road_thickness)
        self._build_highways(plan, hwy, arterials, road_z, road_thickness, road_top)
        self._build_streets(plan, hwy, road_z, road_thickness, road_top)
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
        bright_nodes = {"city_centre": self.city_centre}
        self._districts: dict[str, dict] = {}
        for key, spec in DISTRICT_DEFS.items():
            district = {
                "title": spec["title"],
                "ring": spec["ring"],
                "bbox": spec.get("bbox"),
                "anchor": spec.get("anchor"),
                "bright": bright_nodes.get(spec.get("bright_key")),
                "hotkey_only": bool(spec.get("hotkey_only")),
            }
            outline = self._build_district_outline(key, district["ring"], outline_z)
            outline.hide()
            district["outline"] = outline
            district["label"] = None
            district["label_scale"] = 1.0
            self._districts[key] = district
        self._selected_district: str | None = None
        self.city_centre_ring = self._districts["city_centre"]["ring"]

    def _build_highways(
        self,
        plan,
        hwy: dict,
        arterials: list,
        road_z: float,
        road_thickness: float,
        road_top: float,
    ) -> None:
        lane_width = hwy["lane_width"]
        highway_width = hwy["highway_width"]
        self.highway = self.render.attachNewNode("highway")
        road_mat = road_material()
        mark_paint = mark_material()
        barrier_mat = concrete_material(0.75)

        def paint_route_marks(
            pts: list[tuple[float, float]],
            z_top: float,
            *,
            lanes: int,
            width: float,
            mark_gaps: list[tuple[float, float, float]],
        ) -> None:
            if len(pts) < 2 or lanes < 2:
                return
            mark_len = max(0.35, lane_width * 1.1)
            mark_w = max(0.04, lane_width * 0.18)
            mark_h = 0.004
            mark_gap = mark_len * 1.2
            period = mark_len + mark_gap
            # Sit flush on the deck: box centre at half thickness above road top.
            mark_z = z_top + mark_h / 2
            centre_divider = lanes // 2
            dist = [0.0]
            for i in range(len(pts) - 1):
                dist.append(
                    dist[-1]
                    + math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                )
            total = dist[-1]
            if total < period:
                return

            def sample(s: float) -> tuple[float, float, float, float]:
                s = max(0.0, min(total, s))
                j = 0
                while j < len(dist) - 2 and dist[j + 1] < s:
                    j += 1
                span = dist[j + 1] - dist[j]
                t = 0.0 if span < 1e-9 else (s - dist[j]) / span
                x0, y0 = pts[j]
                x1, y1 = pts[j + 1]
                dx = x1 - x0
                dy = y1 - y0
                length = math.hypot(dx, dy) or 1.0
                return (x0 + dx * t, y0 + dy * t, dx / length, dy / length)

            def in_gap(x: float, y: float) -> bool:
                for gx, gy, radius in mark_gaps:
                    if radius <= 0.0:
                        continue
                    dx = x - gx
                    dy = y - gy
                    if dx * dx + dy * dy <= radius * radius:
                        return True
                return False

            s = mark_len * 0.5
            while s < total:
                x, y, ux, uy = sample(s)
                if not in_gap(x, y):
                    px, py = -uy, ux
                    heading = math.degrees(math.atan2(uy, ux))
                    for divider in range(1, lanes):
                        if divider == centre_divider:
                            continue
                        offset = -width / 2 + divider * lane_width
                        mark = box_instance(self.highway, mark_len, mark_w, mark_h)
                        mark.setPos(x + px * offset, y + py * offset, mark_z)
                        mark.setH(heading)
                        mark.setMaterial(mark_paint, 1)
                s += period

        self._highway_labels = self.render.attachNewNode("highway_labels")
        labels_root = self._highway_labels
        self._highway_label_nodes: list = []
        self._label_base_scale = max(2.4, highway_width * 4.5)
        self._label_ref_distance = 1.0
        crossing_gaps, _junctions = arterial_topology(arterials)
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

        def place_barrier_prisms(
            piece: list,
            width: float,
            height: float,
            z_center: float,
        ) -> None:
            if width <= 0.0 or height <= 0.0 or len(piece) < 2:
                return
            run = 0.0
            for i in range(1, len(piece)):
                run += math.hypot(
                    float(piece[i][0]) - float(piece[i - 1][0]),
                    float(piece[i][1]) - float(piece[i - 1][1]),
                )
            if run < _BARRIER_MIN_RUN:
                return
            half_w = width * 0.5
            pts = coarsen_polyline(piece, _BARRIER_SPAN)
            for i in range(len(pts) - 1):
                x0 = float(pts[i][0])
                y0 = float(pts[i][1])
                x1 = float(pts[i + 1][0])
                y1 = float(pts[i + 1][1])
                dx = x1 - x0
                dy = y1 - y0
                length = math.hypot(dx, dy)
                if length < 0.05:
                    continue
                box = box_instance(self.highway, length, width, height)
                box.setPos((x0 + x1) * 0.5, (y0 + y1) * 0.5, z_center)
                box.setH(math.degrees(math.atan2(dy, dx)))
                box.setMaterial(barrier_mat, 1)
                self._solid_barriers.append((x0, y0, x1, y1, half_w))

        for arterial in arterials:
            pts = list(arterial["points"])
            if len(pts) < 2:
                continue
            route_lanes = int(arterial.get("lanes", plan.highway_lanes))
            route_width = float(arterial.get("width", highway_width))
            name = str(arterial.get("name", ""))
            z_off = float(arterial.get("z_offset", 0.0))
            route_z = road_z + z_off
            route_top = road_top + z_off
            median_gaps = list(crossing_gaps.get(name, []))
            deck = self.highway.attachNewNode(
                make_highway_ribbon(pts, route_width, road_thickness)
            )
            deck.setPos(0.0, 0.0, route_z)
            deck.setMaterial(road_mat, 1)
            if route_lanes > 2:
                if plan.barrier_w > 0.0 and plan.barrier_h > 0.0:
                    for piece in split_polyline_around_gaps(pts, median_gaps):
                        place_barrier_prisms(
                            piece,
                            plan.barrier_w,
                            plan.barrier_h,
                            route_top + plan.barrier_h / 2,
                        )
                # Side fences only on 6-lane arterials (not 2-/4-lane roads).
                if route_lanes >= 6 and plan.fence_w > 0.0 and plan.fence_h > 0.0:
                    edge = route_width / 2 + plan.fence_w / 2
                    fence_gaps = [(x, y, radius + edge) for x, y, radius in median_gaps]
                    for side in (-1.0, 1.0):
                        edge_pts = offset_polyline(pts, side * edge)
                        for piece in split_polyline_around_gaps(edge_pts, fence_gaps):
                            place_barrier_prisms(
                                piece,
                                plan.fence_w,
                                plan.fence_h,
                                route_top + plan.fence_h / 2,
                            )
            paint_route_marks(
                pts,
                route_top,
                lanes=route_lanes,
                width=route_width,
                mark_gaps=median_gaps,
            )

            title = HIGHWAY_LABELS.get(name)
            if title is None:
                # Urban fill / anonymous collectors stay unlabeled.
                if name.startswith(("wg_", "wb_", "lc_", "ag_", "sw_fill_")):
                    title = ""
                elif name.endswith(("_w", "_e")) and name.startswith(
                    ("ave_", "col_ave_")
                ):
                    # ALR-split avenue halves share one label family.
                    title = HIGHWAY_LABELS.get(name.rsplit("_", 1)[0], "")
                    if not title:
                        base = name.rsplit("_", 1)[0]
                        title = base.replace("_", " ").title()
                else:
                    title = name.replace("_", " ").title()
            if title:
                half_w = route_width * 0.5
                road_pts = coarsen_polyline(pts, 1.5)
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
            if not title:
                continue
            mid = pts[len(pts) // 2]
            text = TextNode(f"hwy-label-{name}")
            text.setText(title)
            text.setAlign(TextNode.ACenter)
            text.setTextColor(1.0, 1.0, 1.0, 1)
            text.setShadow(0.06, 0.06)
            text.setShadowColor(0.05, 0.06, 0.08, 0.9)
            pivot = labels_root.attachNewNode(f"hwy-label-pivot-{name}")
            pivot.setPos(mid[0], mid[1], road_top + 0.55)
            label = pivot.attachNewNode(text)
            label.setScale(self._label_base_scale)
            label.setBillboardPointEye()
            label.setDepthTest(False)
            label.setDepthWrite(False)
            self._highway_label_nodes.append(label)

        self._barrier_cell = _SEG_CELL
        self._road_cell = _SEG_CELL
        self._barrier_grid = self._build_segment_grid(
            self._solid_barriers, xy_offset=0, cell=self._barrier_cell
        )
        self._road_grid = self._build_segment_grid(
            self._named_roads, xy_offset=1, cell=self._road_cell
        )

        # Traffic lights disabled for the road-network pass.
        self._signals = None

        for key, district in self._districts.items():
            ring = district["ring"]
            text = TextNode(f"district-label-{key}")
            text.setText(district["title"])
            text.setAlign(TextNode.ACenter)
            text.setTextColor(0.86, 0.12, 0.1, 1)
            text.setShadow(0.05, 0.05)
            text.setShadowColor(0.08, 0.02, 0.02, 0.75)
            pivot = self.render.attachNewNode(f"district-label-pivot-{key}")
            anchor = district.get("anchor")
            if anchor is not None:
                label_x, label_y = anchor
            else:
                label_x = sum(p[0] for p in ring) / len(ring)
                label_y = sum(p[1] for p in ring) / len(ring)
            pivot.setPos(label_x, label_y, road_top + 6.0)
            label = pivot.attachNewNode(text)
            label_scale = self._label_base_scale * 4.0
            label.setScale(label_scale)
            label.setBillboardPointEye()
            label.setDepthTest(False)
            label.setDepthWrite(False)
            label.hide()
            district["label"] = label
            district["label_scale"] = label_scale

        self.highway.flattenStrong()

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

    def _build_ground(self, hwy: dict, road_z: float) -> None:
        lawn_mat = lawn_material()
        ground_pad = 40.0
        self._ground = box_instance(
            self.render,
            (hwy["bounds_east"] - hwy["bounds_west"]) + ground_pad,
            (hwy["bounds_north"] - hwy["bounds_south"]) + ground_pad,
            0.16,
        )
        self._ground.setPos(
            (hwy["bounds_west"] + hwy["bounds_east"]) / 2,
            (hwy["bounds_south"] + hwy["bounds_north"]) / 2,
            road_z - 0.12,
        )
        self._ground.setMaterial(lawn_mat, 1)

    def _build_lighting(self) -> None:
        self._ambient_light = AmbientLight("ambient")
        self._ambient_np = self.render.attachNewNode(self._ambient_light)
        self.render.setLight(self._ambient_np)
        self._sun_light = DirectionalLight("sun")
        self._sun_np = self.render.attachNewNode(self._sun_light)
        self.render.setLight(self._sun_np)
        self._fill_light = DirectionalLight("fill")
        self._fill_np = self.render.attachNewNode(self._fill_light)
        self.render.setLight(self._fill_np)

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

        # Green player car on King George Blvd at Whalley (right lane, southbound).
        king = next((a for a in arterials if a.get("name") == "king_george"), None)
        if king is not None:
            kg_w = float(king.get("width", plan.road_width))
            self._player_car = PlayerCar(
                self,
                road_top,
                -kg_w / 4.0,
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
        # Full Ferry tip → UBC / Ironworkers / 276 St regional span.
        self.camLens.setFar(4500.0)
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
            )
        )
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
        self.accept("c", self._toggle_car_mode)
        self.accept("space", self._cycle_car_focus)
        self.accept("backspace", self._clear_district_selection)
        self.accept("s", self._select_surrey)
        self.accept("l", self._select_district_of_langley)
        self.accept("e", self._select_delta)
        self.accept("r", self._select_richmond)
        self.accept("v", self._select_vancouver)
        self.accept("wheel_up", self._zoom, [0.94])
        self.accept("wheel_down", self._zoom, [1.0 / 0.94])
        self.accept("arrow_up", self._bump_player_speed_limit, [10.0])
        self.accept("arrow_down", self._bump_player_speed_limit, [-10.0])
        self.accept("mouse1", self._start_drag)
        self.accept("mouse1-up", self._end_drag)
        self.taskMgr.add(self._drag_task, "orbit-drag")
        self.taskMgr.add(self._pan_task, "camera-pan")
        self.taskMgr.add(self._follow_focus_task, "follow-car-focus")
        self.taskMgr.add(self._car_hud_task, "car-hud")
        self.taskMgr.add(self._day_cycle_task, "day-night-cycle")
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
        """Map mode: top centre. C mode: bottom left (street name keeps the top)."""
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
        self._apply_day_cycle(self._day_cycle.sample())
        return task.cont

    def _apply_day_cycle(self, sample, *, force_sky: bool = False) -> None:
        """Push cycle sample into lights, clear colour, sky dome, and clock."""
        self._vehicle_lights_on = sample.vehicle_lights_on
        ar, ag, ab = sample.ambient
        self._ambient_light.setColor((ar, ag, ab, 1))
        sr, sg, sb = sample.sun_color
        self._sun_light.setColor((sr, sg, sb, 1))
        self._sun_np.setHpr(*sample.sun_hpr)
        fr, fg, fb = sample.fill_color
        self._fill_light.setColor((fr, fg, fb, 1))
        self._fill_np.setHpr(*sample.fill_hpr)
        br, bg, bb = sample.background
        self.setBackgroundColor(br, bg, bb, 1)

        # Rebuild the dome when the palette moves enough — cheap 8×24 mesh.
        sky_key = (
            round(sample.zenith[0], 3),
            round(sample.zenith[1], 3),
            round(sample.zenith[2], 3),
            round(sample.horizon_cool[0], 3),
            round(sample.horizon_cool[1], 3),
            round(sample.horizon_cool[2], 3),
            round(sample.horizon_warm[0], 3),
            round(sample.horizon_warm[1], 3),
            round(sample.horizon_warm[2], 3),
            round(sample.sun_phi_deg, 1),
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

        # Player car only runs its update loop in C mode — sync night lamps here.
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
        """C: enter/exit third-person drive mode on the green player car."""
        if self._player_car is None:
            return
        if self._car_mode:
            self._exit_car_mode()
        else:
            self._enter_car_mode()

    def _enter_car_mode(self) -> None:
        self._car_mode = True
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
        """↑/↓: nudge forward cruise cap by 10 km/h (0–300), car mode only."""
        if not self._car_mode or self._player_car is None:
            return
        self._player_car.bump_speed_limit(delta_kmh)

    def _player_drive_task(self, task):
        """C mode: WASD drive; ←/→ trim heading; ↑/↓ set cruise limit."""
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
        # Keep label screen size roughly constant while zooming.
        ref = max(self._label_ref_distance, 1e-6)
        zoom = self.distance / ref
        scale = self._label_base_scale * zoom
        for label in self._highway_label_nodes:
            label.setScale(scale)
        for district in self._districts.values():
            label = district.get("label")
            if label is not None:
                label.setScale(district["label_scale"] * zoom)

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
        label = district.get("label")
        if label is not None:
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

    def _select_surrey(self) -> None:
        """S: outline Greater Surrey (disabled in C / car mode)."""
        if self._car_mode:
            return
        self._select_district("surrey")

    def _select_district_of_langley(self) -> None:
        """L: outline District of Langley (disabled in C / car mode)."""
        if self._car_mode:
            return
        self._select_district("district_of_langley")

    def _select_delta(self) -> None:
        """E: outline Delta (disabled in C / car mode)."""
        if self._car_mode:
            return
        self._select_district("delta")

    def _select_richmond(self) -> None:
        """R: outline Richmond / Lulu Island, no YVR (disabled in C / car mode)."""
        if self._car_mode:
            return
        self._select_district("richmond")

    def _select_vancouver(self) -> None:
        """V: outline Vancouver including UBC / Point Grey (disabled in C mode)."""
        if self._car_mode:
            return
        self._select_district("vancouver")

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
        """Arrow keys: pan look_at on the ground plane (disabled in C mode)."""
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
