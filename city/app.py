"""ShowBase app: assemble the city from CityPlan and run the viewer."""

from __future__ import annotations

import math
import random
import sys

from panda3d.core import (
    AmbientLight,
    DirectionalLight,
    Filename,
    KeyboardButton,
    TextNode,
)
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase

from city.builders import SceneBuilders
from city.car import CarController
from city.materials import (
    BLOCK_SHADES,
    block_material,
    concrete_material,
    lawn_material,
    mark_material,
    road_material,
)
from city.mesh import (
    _dist2_point_segment,
    arterial_crossing_gaps,
    box_instance,
    make_highway_ribbon,
    offset_polyline,
    split_polyline_around_gaps,
    z_cylinder_instance,
)
from city.plan import default_city_plan

# Readable names for arterial YAML keys (world-space map labels).
HIGHWAY_LABELS = {
    "hwy17": "Hwy 17",
    "hwy1": "Hwy 1",
    "fraser": "Fraser Hwy",
    "hwy15": "Hwy 15",
    "hwy10": "88 Ave",
    "hwy99": "Hwy 99",
    "hwy8": "Hwy 10",
    "king_george": "King George Blvd",
    "scott_120": "120 St",
    "ave_72": "72 Ave",
    "ave_96": "96 Ave",
    "ave_102": "102 Ave",
    "ave_108": "108 Ave",
    "ave_114": "114 Ave",
    "whalley_blvd": "Whalley Blvd",
    "university_dr": "University Dr",
    "st_128": "128 St",
    "st_140": "140 St",
    "st_152": "152 St",
}

# Thin side fences: provincial highways plus Fraser, 88 Ave, and King George.
SIDE_BORDER_ROUTES = frozenset(
    {
        "hwy17",
        "hwy1",
        "fraser",
        "hwy15",
        "hwy99",
        "hwy8",
        "hwy10",
        "king_george",
    }
)


class CityApp(ShowBase):
    def __init__(self, screenshot: str | None = None) -> None:
        super().__init__()
        self.screenshot_path = screenshot
        self.disableMouse()
        self.setBackgroundColor(0.7, 0.78, 0.88, 1)

        plan = default_city_plan()
        self.plan = plan
        self.city = self.render.attachNewNode("city")
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

        # Demo towers on the NE plate, plus skyscrapers in the circled Whalley blocks.
        ne = SceneBuilders(self.city, plan, self.render)
        ne._add_house(560.0, 400.0, brick=0.68, chimney=True)
        ne._add_stack(
            590.0,
            400.0,
            18,
            block_size,
            block_material(BLOCK_SHADES[1]),
            footprint="rect",
            doors=("-y",),
        )
        ne._add_stack(
            605.0,
            400.0,
            18,
            block_size,
            block_material(BLOCK_SHADES[4]),
            footprint="round",
            doors=("-y",),
        )
        ne._add_stack(
            590.0,
            415.0,
            16,
            block_size,
            block_material(BLOCK_SHADES[7]),
            footprint="tri",
            heading=18.0,
            doors=("-y",),
        )
        hwy = plan.highway_geometry()
        lane_width = hwy["lane_width"]
        highway_width = hwy["highway_width"]
        road_z = hwy["road_z"]
        road_thickness = hwy["road_thickness"]
        arterials = list(hwy["arterials"])

        # Road corridors for tower sight checks: (ax, ay, bx, by, half_width).
        road_segs: list[tuple[float, float, float, float, float]] = []
        for route in arterials:
            pts = list(route.get("control_points") or route.get("points") or ())
            half_w = float(route.get("width") or 0.0) * 0.5
            for i in range(len(pts) - 1):
                road_segs.append(
                    (pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], half_w)
                )

        def _tower_sees_road(
            tx: float,
            ty: float,
            half: float,
            others: list[tuple[float, float]],
            *,
            max_dist: float = 48.0,
            step: float = 0.7,
        ) -> bool:
            """True if a cardinal ray hits pavement before another tower."""
            for dx, dy in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)):
                dist = half + 0.05
                while dist < max_dist:
                    px = tx + dx * dist
                    py = ty + dy * dist
                    blocked = False
                    for ox, oy in others:
                        if abs(px - ox) <= half and abs(py - oy) <= half:
                            blocked = True
                            break
                    if blocked:
                        break
                    for ax, ay, bx, by, hw in road_segs:
                        d2, _qx, _qy = _dist2_point_segment(px, py, ax, ay, bx, by)
                        if d2 <= hw * hw:
                            return True
                    dist += step
            return False

        # Circled blocks packed with towers, split around 102 Ave.
        # Each tuple is (west, east, south, north) inset from the arterials.
        tower_blocks = (
            (92.0, 113.0, 184.0, 204.0),   # 128–Uni, 96–102
            (127.0, 148.0, 184.0, 204.0),  # Uni–KG, 96–102
            (162.0, 180.0, 184.0, 204.0),  # KG–Whalley, 96–102
            (194.0, 211.0, 184.0, 204.0),  # Whalley–140, 96–102
            (92.0, 113.0, 216.0, 236.0),   # 128–Uni, 102–108
            (127.0, 148.0, 216.0, 236.0),  # Uni–KG, 102–108
            (162.0, 180.0, 216.0, 236.0),  # KG–Whalley, 102–108
            (194.0, 211.0, 216.0, 236.0),  # Whalley–140, 102–108
            (162.0, 180.0, 253.0, 282.0),  # KG–Whalley, above 108
            (194.0, 211.0, 253.0, 282.0),  # Whalley–140, above 108
        )
        # Dark grey lot pads under the tower blocks (above the lawn).
        pad_mat = concrete_material(0.32)
        pad_thickness = 0.14
        for west, east, south, north in tower_blocks:
            pad = box_instance(
                self.city,
                east - west,
                north - south,
                pad_thickness,
            )
            pad.setPos(
                (west + east) * 0.5,
                (south + north) * 0.5,
                road_z - 0.02,
            )
            pad.setMaterial(pad_mat, 1)

        footprints = ("rect", "round", "tri")
        tower_pitch = block_size[0] + plan.tower_gap + 0.6
        tower_half = block_size[0] * 0.5
        floor_hi = plan.floor_max + 6
        candidates: list[tuple[float, float, int, str, float, int]] = []
        for west, east, south, north in tower_blocks:
            cols = max(2, min(3, int((east - west) / tower_pitch)))
            rows = max(2, min(4, int((north - south) / tower_pitch)))
            for row in range(rows):
                for col in range(cols):
                    x = west + (col + 0.5) * (east - west) / cols
                    y = south + (row + 0.5) * (north - south) / rows
                    seed = abs(int(x * 17 + y * 31))
                    x += ((seed % 7) - 3) * 0.12
                    y += ((seed % 5) - 2) * 0.12
                    # Medium or tall only — no short stacks.
                    mid_lo = max(plan.floor_min, 14)
                    mid_hi = max(mid_lo + 4, plan.floor_max - 2)
                    tall_lo = mid_hi + 1
                    tall_hi = floor_hi
                    roll = (seed * 13 + seed // 5) % 100
                    if roll < 40:
                        span = max(1, tall_hi - tall_lo + 1)
                        floors = tall_lo + ((seed * 7) % span)
                    else:
                        span = max(1, mid_hi - mid_lo + 1)
                        floors = mid_lo + ((seed * 11) % span)
                    footprint = footprints[seed % 3]
                    heading = (seed % 9 - 4) * 5.0 if footprint == "tri" else 0.0
                    candidates.append((x, y, floors, footprint, heading, seed))

        # Drop towers with no clear cardinal sightline to a road.
        kept: list[tuple[float, float, int, str, float, int]] = []
        for x, y, floors, footprint, heading, seed in candidates:
            others = [(ox, oy) for ox, oy, *_rest in candidates if ox != x or oy != y]
            if _tower_sees_road(x, y, tower_half, others):
                kept.append((x, y, floors, footprint, heading, seed))
        for x, y, floors, footprint, heading, seed in kept:
            ne._add_stack(
                x,
                y,
                floors,
                block_size,
                block_material(BLOCK_SHADES[seed % len(BLOCK_SHADES)]),
                footprint=footprint,
                heading=heading,
                doors=("-y",),
            )

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
            """Lane dashes that follow the smoothed centreline."""
            if len(pts) < 2 or lanes < 2:
                return
            # Longer dashes / gaps so the continuous ribbon still reads at overview.
            mark_len = 3.5
            mark_w = 0.35
            mark_h = 0.04
            mark_gap = 4.0
            period = mark_len + mark_gap
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
                        mark.setPos(x + px * offset, y + py * offset, z_top + 0.02)
                        mark.setH(heading)
                        mark.setMaterial(mark_paint, 1)
                s += period

        road_top = road_z + road_thickness / 2
        labels_root = self.render.attachNewNode("highway_labels")
        self._highway_label_nodes: list = []
        self._label_base_scale = max(36.0, highway_width * 2.8)
        self._label_ref_distance = 1.0
        # Barriers, side fences, and lane marks open at arterial crossings.
        crossing_gaps = arterial_crossing_gaps(arterials)
        for arterial in arterials:
            pts = list(arterial["points"])
            if len(pts) < 2:
                continue
            route_lanes = int(arterial.get("lanes", plan.highway_lanes))
            route_width = float(arterial.get("width", highway_width))
            name = str(arterial.get("name", ""))
            # (x, y, clear_radius) — radius is angle-aware (shallow junctions open wider).
            median_gaps = list(crossing_gaps.get(name, []))
            # One continuous ribbon per route — smooth edges through bends.
            deck = self.highway.attachNewNode(
                make_highway_ribbon(pts, route_width, road_thickness)
            )
            deck.setPos(0.0, 0.0, road_z)
            deck.setMaterial(road_mat, 1)
            if plan.barrier_w > 0.0 and plan.barrier_h > 0.0:
                for piece in split_polyline_around_gaps(pts, median_gaps):
                    barrier = self.highway.attachNewNode(
                        make_highway_ribbon(piece, plan.barrier_w, plan.barrier_h)
                    )
                    barrier.setPos(0.0, 0.0, road_top + plan.barrier_h / 2)
                    barrier.setMaterial(barrier_mat, 1)
            if name in SIDE_BORDER_ROUTES and plan.fence_w > 0.0 and plan.fence_h > 0.0:
                # Thin concrete lips along both pavement edges; gapped at crossings.
                edge = route_width / 2 + plan.fence_w / 2
                fence_gaps = [(x, y, radius + edge) for x, y, radius in median_gaps]
                for side in (-1.0, 1.0):
                    edge_pts = offset_polyline(pts, side * edge)
                    for piece in split_polyline_around_gaps(edge_pts, fence_gaps):
                        fence = self.highway.attachNewNode(
                            make_highway_ribbon(piece, plan.fence_w, plan.fence_h)
                        )
                        fence.setPos(0.0, 0.0, road_top + plan.fence_h / 2)
                        fence.setMaterial(barrier_mat, 1)
            paint_route_marks(
                pts,
                road_top,
                lanes=route_lanes,
                width=route_width,
                mark_gaps=median_gaps,
            )

            title = HIGHWAY_LABELS.get(name, name.replace("_", " ").title())
            if not title:
                continue
            mid = pts[len(pts) // 2]
            text = TextNode(f"hwy-label-{name}")
            text.setText(title)
            text.setAlign(TextNode.ACenter)
            text.setTextColor(1.0, 1.0, 1.0, 1)
            text.setShadow(0.06, 0.06)
            text.setShadowColor(0.05, 0.06, 0.08, 0.9)
            # Pivot stays fixed in world space; only the text child is re-scaled.
            pivot = labels_root.attachNewNode(f"hwy-label-pivot-{name}")
            pivot.setPos(mid[0], mid[1], road_top + 4.0)
            label = pivot.attachNewNode(text)
            label.setScale(self._label_base_scale)
            label.setBillboardPointEye()
            label.setDepthTest(False)
            label.setDepthWrite(False)
            self._highway_label_nodes.append(label)

        self.highway.flattenStrong()

        # Local residential streets (Surrey interior fabric) — no median barrier.
        streets = plan.street_geometry()
        self.streets = self.render.attachNewNode("streets")
        street_width = float(streets["street_width"])
        for route in streets["routes"]:
            pts = list(route["points"])
            if len(pts) < 2:
                continue
            deck = self.streets.attachNewNode(
                make_highway_ribbon(pts, street_width, road_thickness)
            )
            deck.setPos(0.0, 0.0, road_z)
            deck.setMaterial(road_mat, 1)
            # Single centreline dash — skip tips so junctions / bulbs stay clean.
            mark_len = 2.0
            mark_w = 0.2
            mark_h = 0.04
            mark_gap = 3.0
            period = mark_len + mark_gap
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
                    mark.setPos(x, y, road_top + 0.02)
                    mark.setH(heading)
                    mark.setMaterial(mark_paint, 1)
                    s += period
        # Round cul-de-sac pads at dead ends.
        for cx, cy, radius in streets["bulbs"]:
            pad = z_cylinder_instance(
                self.streets, radius, road_thickness, segments=28
            )
            pad.setPos(cx, cy, road_z)
            pad.setMaterial(road_mat, 1)
        self.streets.flattenStrong()

        lawn_mat = lawn_material()
        ground_pad = 80.0
        ground = box_instance(
            self.render,
            (hwy["bounds_east"] - hwy["bounds_west"]) + ground_pad,
            (hwy["bounds_north"] - hwy["bounds_south"]) + ground_pad,
            0.16,
        )
        ground.setPos(
            (hwy["bounds_west"] + hwy["bounds_east"]) / 2,
            (hwy["bounds_south"] + hwy["bounds_north"]) / 2,
            road_z - 0.12,
        )
        ground.setMaterial(lawn_mat, 1)

        # Fixed-function lights (same stack the city builders used).
        ambient = AmbientLight("ambient")
        ambient.setColor((0.34, 0.37, 0.42, 1))
        self.render.setLight(self.render.attachNewNode(ambient))
        sun = DirectionalLight("sun")
        sun.setColor((1.15, 1.05, 0.9, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(38, -48, 0)
        self.render.setLight(sun_np)
        fill = DirectionalLight("fill")
        fill.setColor((0.18, 0.22, 0.3, 1))
        fill_np = self.render.attachNewNode(fill)
        fill_np.setHpr(220, -25, 0)
        self.render.setLight(fill_np)

        # One cruiser on Fraser Hwy (right lane); Space focuses it.
        self._cars: list[CarController] = []
        self._car = None
        self._signals = None
        self._fleet_root = self.render.attachNewNode("fleet")
        fraser = next((a for a in arterials if a.get("name") == "fraser"), None)
        if fraser is not None and len(fraser.get("points") or ()) >= 2:
            lane_pts = offset_polyline(
                list(fraser["points"]),
                -float(fraser["width"]) / 4,
            )
            loop = [(x, y, road_top) for x, y in lane_pts]
            car = CarController(self, self._cars)
            car.setup(
                road_top,
                plan.west_road_full0,
                plan.south_road_full0,
                plan.stride_x,
                plan.stride_y,
                plan.cols,
                plan.rows,
                start_h=0,
                start_v=0,
                start_dir=(1, 0),
                body_colour=(0.22, 0.48, 0.72),
            )
            car._car_diamonds = []
            car._car_loop_path = loop
            car._car_pos = [loop[0][0], loop[0][1]]
            car._car_set_surface_z(loop[0][2])
            car._car_begin_path(list(loop), kind="arterial_loop")
            car._place_car()
            self._car = car
            self.taskMgr.add(self._fleet_task, "fleet")

        bounds = plan.framing_bounds()
        left = bounds["left"]
        right = bounds["right"]
        frame_south = bounds["city_south"]
        frame_north = bounds["city_north"]
        # Highways sit near z=0; don't aim at tower mid-height when fabric is empty.
        self.look_at = (
            (left + right) / 2,
            (frame_south + frame_north) / 2,
            road_z,
        )
        # North-up overview so diagonal Fraser Hwy / Hwy 99 read clearly.
        self.heading = 0.0
        self.pitch = 68.0
        half_fov = math.tan(math.radians(20.0))
        fit_x = ((right - left) / 2) / half_fov
        fit_y = ((frame_north - frame_south) / 2) / half_fov / max(0.25, math.cos(math.radians(self.pitch)))
        self.distance = max(fit_x, fit_y) * 1.2
        self.min_distance = 2.0
        self.max_distance = max(200.0, self.distance * 2.5)
        # Overview distance → label world scale of 1× (see _update_camera).
        self._label_ref_distance = self.distance
        self.dragging = False
        self.last_x = 0.0
        self.last_y = 0.0
        # Space cycles: car 0..n-1, then restore this overview framing.
        self._default_look_at = list(self.look_at)
        self._default_distance = self.distance
        self._default_heading = self.heading
        self._default_pitch = self.pitch
        self._focus_index = -1  # -1 = overview; 0..len(_cars)-1 = follow car
        self._car_focus_distance = 14.0
        self._update_camera()

        self.accept("escape", sys.exit)
        self.accept("space", self._cycle_car_focus)
        self.accept("wheel_up", self._zoom, [0.94])
        self.accept("wheel_down", self._zoom, [1.0 / 0.94])
        self.accept("mouse1", self._start_drag)
        self.accept("mouse1-up", self._end_drag)
        self.taskMgr.add(self._drag_task, "orbit-drag")
        self.taskMgr.add(self._pan_task, "camera-pan")
        self.taskMgr.add(self._follow_focus_task, "follow-car-focus")
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

    def _car_look_at(self, car: CarController) -> list[float]:
        return [car._car_pos[0], car._car_pos[1], car._car_z + 0.5]

    def _cycle_car_focus(self) -> None:
        """Space: zoom to next car; after the last car, restore the city overview."""
        if not self._cars:
            return
        self._focus_index += 1
        if self._focus_index >= len(self._cars):
            self._focus_index = -1
            self.look_at = list(self._default_look_at)
            self.distance = self._default_distance
            self.heading = self._default_heading
            self.pitch = self._default_pitch
            self._update_camera()
            return

        car = self._cars[self._focus_index]
        self.look_at = self._car_look_at(car)
        self.distance = min(
            self.max_distance,
            max(self.min_distance, self._car_focus_distance),
        )
        # Top-down follow; keep heading so the city stays oriented.
        self.pitch = 85.0
        self._update_camera()

    def _follow_focus_task(self, task):
        if 0 <= self._focus_index < len(self._cars):
            self.look_at = self._car_look_at(self._cars[self._focus_index])
            self._update_camera()
        return task.cont

    def _update_camera(self) -> None:
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
        scale = self._label_base_scale * (self.distance / ref)
        for label in self._highway_label_nodes:
            label.setScale(scale)

    def _zoom(self, factor: float) -> None:
        self.distance = min(
            self.max_distance,
            max(self.min_distance, self.distance * factor),
        )
        # While following a car, keep wheel zoom as the new follow distance.
        if self._focus_index >= 0:
            self._car_focus_distance = self.distance
        self._update_camera()

    def _start_drag(self) -> None:
        if not self.mouseWatcherNode.hasMouse():
            return
        self.dragging = True
        self.last_x = self.mouseWatcherNode.getMouseX()
        self.last_y = self.mouseWatcherNode.getMouseY()

    def _end_drag(self) -> None:
        self.dragging = False

    def _drag_task(self, task):
        if self.dragging and self.mouseWatcherNode.hasMouse():
            x = self.mouseWatcherNode.getMouseX()
            y = self.mouseWatcherNode.getMouseY()
            self.heading -= (x - self.last_x) * 120.0
            self.pitch = max(-85.0, min(85.0, self.pitch + (y - self.last_y) * 90.0))
            self.last_x = x
            self.last_y = y
            self._update_camera()
        return task.cont

    def _pan_task(self, task):
        """WASD / arrows: pan look_at on the ground plane relative to heading."""
        mw = self.mouseWatcherNode
        forward = 0.0
        right = 0.0
        if mw.is_button_down(KeyboardButton.ascii_key("w")) or mw.is_button_down(
            KeyboardButton.up()
        ):
            forward += 1.0
        if mw.is_button_down(KeyboardButton.ascii_key("s")) or mw.is_button_down(
            KeyboardButton.down()
        ):
            forward -= 1.0
        if mw.is_button_down(KeyboardButton.ascii_key("d")) or mw.is_button_down(
            KeyboardButton.right()
        ):
            right += 1.0
        if mw.is_button_down(KeyboardButton.ascii_key("a")) or mw.is_button_down(
            KeyboardButton.left()
        ):
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
