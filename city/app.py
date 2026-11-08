"""ShowBase app: assemble the city from CityPlan and run the viewer."""

from __future__ import annotations

import math
import random
import sys

from panda3d.core import Filename, TextNode
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase

from city.builders import SceneBuilders
from city.car import CarController
from city.materials import block_material, mark_material, road_material, sphere_material
from city.plan import default_city_plan
from city.signals import TrafficLightController


class CityApp(ShowBase):
    def __init__(self, screenshot: str | None = None) -> None:
        super().__init__()
        self.screenshot_path = screenshot
        self.disableMouse()
        # Soft daylight sky; fog in SceneBuilders matches this tint.
        self.setBackgroundColor(0.62, 0.72, 0.84, 1)

        plan = default_city_plan()
        self.plan = plan
        self.city = self.render.attachNewNode("city")
        builders = SceneBuilders(self.city, plan, self.render)
        self._builders = builders

        material = sphere_material()
        for x, y in plan.sphere_positions:
            builders._add_sphere(x + plan.group_shift, y, material)
        for index, (x0, y0) in enumerate(plan.sphere_positions):
            x1, y1 = plan.sphere_positions[(index + 1) % len(plan.sphere_positions)]
            builders._add_link(
                x0 + plan.group_shift,
                y0,
                x1 + plan.group_shift,
                y1,
                material,
            )

        block_size = plan.block_size
        for lot in plan.iter_tower_lots():
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
            )

        for lot in plan.iter_north_housing_lots():
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

        for lot in plan.iter_west_housing_lots():
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

        for lot in plan.iter_south_factory_lots():
            builders._add_city_block(
                lot.west_face,
                block_size,
                ((), (), (), ()),
                y_offset=lot.y_offset,
                eastern_road=lot.eastern_road,
                southern_road=lot.southern_road,
            )

        for lot in plan.iter_east_factory_lots():
            builders._add_city_block(
                lot.west_face,
                block_size,
                ((), (), (), ()),
                y_offset=lot.y_offset,
                eastern_road=lot.eastern_road,
                southern_road=lot.southern_road,
            )

        for lot in plan.iter_gap_housing_lots():
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

        half = plan.road_width / 2
        for h in range(1, plan.rows):
            iy = plan.south_road_full0 + h * plan.stride_y
            for v in range(1, plan.cols):
                ix = plan.west_road_full0 + v * plan.stride_x
                sw = plan.solid_lot(h - 1, v - 1)
                se = plan.solid_lot(h - 1, v)
                nw = plan.solid_lot(h, v - 1)
                ne = plan.solid_lot(h, v)
                for x0, y0, x1, y1 in (
                    (ix - half, iy - half, ix + half, iy - half),
                    (ix - half, iy + half, ix + half, iy + half),
                    (ix + half, iy - half, ix + half, iy + half),
                    (ix - half, iy - half, ix - half, iy + half),
                ):
                    builders._add_traffic_light(
                        x0,
                        y0,
                        x1,
                        y1,
                        plan.road_top,
                        block_size,
                        face_x=ix,
                        face_y=iy,
                    )
                # Housing corners have no wall for the span to meet, so drop a
                # vertical rod of the same thickness from each open corner.
                for px, py, solid in (
                    (ix - half, iy - half, sw),
                    (ix + half, iy - half, se),
                    (ix - half, iy + half, nw),
                    (ix + half, iy + half, ne),
                ):
                    if not solid:
                        builders._add_signal_post(px, py, plan.road_top, block_size)

        # Lone house east of the sphere group (same offset math as before).
        cube_size = (2.0, 2.0, 2.0)
        pyramid_size = (3.0, 3.0, 1.5)
        stack_right = plan.block_center_x + block_size[0] / 2
        cube_center_x = stack_right + plan.house_gap + cube_size[0] / 2 + plan.group_shift
        builders._add_house(cube_center_x, 0.0)
        builders._add_lights()

        self.city.flattenStrong()
        north_city = self.render.attachNewNode("city-north")
        north_city.setY(plan.north_shift)
        self.city.instanceTo(north_city)

        # Full housing blocks between the twins (outside the instanced city mesh).
        between = self.render.attachNewNode("between-housing")
        between_builders = SceneBuilders(between, plan, self.render)
        for lot in plan.iter_between_housing_lots():
            between_builders._add_housing_lot(
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
        between.flattenStrong()

        self._signals = TrafficLightController(self)
        self.taskMgr.add(self._signals.update, "traffic-lights")

        hwy = plan.highway_geometry()
        lane_width = hwy["lane_width"]
        highway_width = hwy["highway_width"]
        highway_east = hwy["highway_east"]
        highway_mid_x = hwy["highway_mid_x"]
        fence_x = hwy["fence_x"]
        city_south = hwy["city_south"]
        city_north = hwy["city_north"]
        highway_length = hwy["highway_length"]
        highway_mid_y = hwy["highway_mid_y"]
        road_z = hwy["road_z"]
        exit_ys = hwy["exit_ys"]
        road_thickness = hwy["road_thickness"]

        self.highway = self.render.attachNewNode("highway")
        builders._add_block(
            highway_mid_x,
            highway_mid_y,
            road_z,
            (highway_width, highway_length, road_thickness),
            road_material(),
            parent=self.highway,
        )
        road_top = road_z + road_thickness / 2
        centre_divider = plan.highway_lanes // 2
        for divider in range(1, plan.highway_lanes):
            # Physical median barrier occupies the center; skip its paint.
            if divider == centre_divider:
                continue
            mark_x = highway_east - divider * lane_width
            builders._add_road_marks(
                mark_x,
                highway_mid_y,
                road_top,
                highway_length,
                along_x=False,
                parent=self.highway,
                paint=mark_material(),
            )
        for exit_y in exit_ys:
            builders._add_road(
                highway_mid_x,
                exit_y,
                road_z,
                highway_width,
                along_x=True,
                parent=self.highway,
            )
        barrier_z = road_top + plan.barrier_h / 2
        fence_z = road_top + plan.fence_h / 2
        barrier_mat = block_material(0.75)
        fence_mat = block_material(0.55)
        opening_half = plan.road_width / 2

        def wall_segments(x: float, width: float, height: float, z: float, mat) -> None:
            cursor = city_south
            for exit_y in exit_ys:
                gap_start = exit_y - opening_half
                if gap_start > cursor:
                    seg_len = gap_start - cursor
                    builders._add_block(
                        x,
                        cursor + seg_len / 2,
                        z,
                        (width, seg_len, height),
                        mat,
                        parent=self.highway,
                    )
                cursor = exit_y + opening_half
            if city_north > cursor:
                seg_len = city_north - cursor
                builders._add_block(
                    x,
                    cursor + seg_len / 2,
                    z,
                    (width, seg_len, height),
                    mat,
                    parent=self.highway,
                )

        wall_segments(highway_mid_x, plan.barrier_w, plan.barrier_h, barrier_z, barrier_mat)
        wall_segments(fence_x, plan.fence_w, plan.fence_h, fence_z, fence_mat)
        self.highway.flattenStrong()

        self._cars: list[CarController] = []
        # Lane centres east→west. Northbound uses the eastern half (right side
        # when facing north); southbound uses the western half.
        hwy_lane_xs = [
            highway_east - lane_width * (i + 0.5) for i in range(plan.highway_lanes)
        ]
        hwy_east_lane = hwy_lane_xs[0]
        hwy_west_lane = hwy_lane_xs[-1]
        # Dense fleet across highway queues + both city grids so lights and
        # follow-gaps actually produce traffic. Stacked approaches sit 3 units
        # behind the lead car (body 2 + bumper gap 1).
        colours = (
            (0.22, 0.48, 0.72),  # blue
            (0.72, 0.18, 0.16),  # red
            (0.18, 0.55, 0.28),  # green
            (0.82, 0.62, 0.12),  # amber
            (0.78, 0.78, 0.8),  # silver
            (0.55, 0.22, 0.55),  # purple
            (0.9, 0.45, 0.12),  # orange
            (0.15, 0.15, 0.18),  # charcoal
            (0.2, 0.65, 0.7),  # teal
            (0.85, 0.35, 0.55),  # pink
            (0.45, 0.32, 0.18),  # brown
            (0.55, 0.7, 0.25),  # lime
        )
        follow_gap = 3.0
        city_origins = (
            plan.south_road_full0,
            plan.south_road_full0 + plan.north_shift,
        )
        spawns: list[dict] = []
        # Highway: 2-deep queues in each of the 3 right-hand lanes, both ways.
        hwy_half = plan.highway_lanes // 2
        for exit_i, origin_y in enumerate(city_origins):
            for start_dir in ((0, 1), (0, -1)):
                for lane in range(hwy_half):
                    for queue in range(2):
                        spawns.append(
                            {
                                "start_v": 0,
                                "start_h": plan.exit_row,
                                "start_dir": start_dir,
                                "on_highway": True,
                                "exit_i": exit_i,
                                "origin_y": origin_y,
                                "queue": queue,
                                "highway_lane": lane,
                            }
                        )
        # City streets: spread across both twins; short queues on the exit
        # arterials so red lights back up into real traffic.
        city_dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
        city_nodes = (
            (1, 1),
            (plan.cols // 2, 1),
            (plan.cols - 1, 2),
            (1, plan.exit_row),
            (plan.cols // 2, plan.exit_row),
            (plan.cols - 1, plan.exit_row),
            (2, plan.rows // 2),
            (plan.cols // 2, plan.rows // 2),
            (plan.cols - 1, plan.rows // 2),
            (1, plan.rows - 1),
            (plan.cols // 2, plan.rows - 1),
            (plan.cols - 1, plan.rows - 1),
        )
        for origin_y in city_origins:
            exit_i = 0 if origin_y == plan.south_road_full0 else 1
            for v, h in city_nodes:
                for di, start_dir in enumerate(city_dirs):
                    # Two directions per node keeps coverage without stacking
                    # four cars on every stop line.
                    if (v + h + di) % 2 != 0:
                        continue
                    if v == 0 and start_dir == (-1, 0):
                        continue
                    # Second car only for east-west traffic on the exit row.
                    queued = h == plan.exit_row and start_dir[1] == 0
                    for queue in range(2 if queued else 1):
                        spawns.append(
                            {
                                "start_v": v,
                                "start_h": h,
                                "start_dir": start_dir,
                                "on_highway": False,
                                "exit_i": exit_i,
                                "origin_y": origin_y,
                                "queue": queue,
                                "highway_lane": (v + h + di) % hwy_half,
                            }
                        )
        for index, spawn in enumerate(spawns):
            colour = colours[index % len(colours)]
            car = CarController(self, self._cars)
            car.setup(
                plan.road_top,
                plan.west_road_full0,
                spawn["origin_y"],
                plan.stride_x,
                plan.stride_y,
                plan.cols,
                plan.rows,
                start_h=spawn["start_h"],
                start_v=spawn["start_v"],
                start_dir=spawn["start_dir"],
                body_colour=colour,
            )
            car._car_highway_lane_xs = list(hwy_lane_xs)
            car._car_highway_lanes = plan.highway_lanes
            car._car_highway_east_lane_x = hwy_east_lane
            car._car_highway_west_lane_x = hwy_west_lane
            car._car_highway_exits = list(exit_ys)
            car._car_south_road0 = plan.south_road_full0
            car._car_north_shift = plan.north_shift
            car._car_exit_row = plan.exit_row
            car._car_on_highway = spawn["on_highway"]
            car._car_exit_i = spawn["exit_i"]
            car._car_highway_lane = spawn["highway_lane"]
            car._car_dir = spawn["start_dir"]
            car._car_heading = math.degrees(
                math.atan2(spawn["start_dir"][1], spawn["start_dir"][0])
            )
            if spawn["on_highway"]:
                car._car_set_highway_lane(car._car_dir)
                approach = car._car_highway_stop(car._car_exit_i, car._car_dir)
            else:
                approach = car._car_stop_xy(*car._car_to, car._car_dir)
            dx, dy = spawn["start_dir"]
            queue = spawn["queue"]
            # Queue behind the stop line; target stays the approach so followers
            # drive forward instead of treating their spawn point as arrival.
            pos = (
                approach[0] - dx * follow_gap * queue,
                approach[1] - dy * follow_gap * queue,
            )
            car._car_pos = list(pos)
            car._car_target = approach
            car._car_state = "drive"
            car._signals = self._signals
            car._place_car()
        self._car = self._cars[0]
        # Seed neighbor caches so the first tick has valid queue/leader data.
        for car in self._cars:
            car._car_refresh_neighbors(resolve=False)
        # One fleet task instead of N car tasks — less scheduler overhead.
        self.taskMgr.add(self._fleet_task, "car-fleet")

        bounds = plan.framing_bounds(cube_center_x, pyramid_size[0] / 2)
        left = bounds["left"]
        right = bounds["right"]
        stack_bottom = bounds["stack_bottom"]
        stack_top = bounds["stack_top"]
        self.look_at = (
            (left + right) / 2,
            (city_south + city_north) / 2,
            (stack_bottom + stack_top) / 2,
        )
        self.heading = 30.0
        self.pitch = 20.0
        half_fov = math.tan(math.radians(20.0))
        fit_x = ((right - left) / 2) / half_fov / math.cos(math.radians(self.heading))
        fit_y = ((city_north - city_south) / 2) / half_fov / math.cos(math.radians(self.pitch))
        self.distance = max(fit_x, fit_y) * 1.25
        self.min_distance = 2.0
        self.max_distance = max(80.0, self.distance * 2.0)
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
        self.fps_text.setText(f"FPS: {self.clock.getAverageFrameRate():.0f}")
        return task.cont

    def _fleet_task(self, task):
        for car in self._cars:
            car._car_task(task)
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

    def capture(self) -> None:
        for _ in range(3):
            self.graphicsEngine.renderFrame()
        path = Filename.fromOsSpecific(self.screenshot_path)
        if not self.win.saveScreenshot(path):
            raise SystemExit(f"Could not write {self.screenshot_path}")
        print(f"Wrote {self.screenshot_path}")
