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

        car = CarController(self)
        self._car = car
        car.setup(
            plan.road_top,
            plan.west_road_full0,
            plan.south_road_full0,
            plan.stride_x,
            plan.stride_y,
            plan.cols,
            plan.rows,
            start_h=plan.exit_row,
            start_v=0,
            start_dir=(0, 1),
        )
        car._car_highway_east_lane_x = highway_east - lane_width / 2
        car._car_highway_west_lane_x = highway_east - highway_width + lane_width / 2
        car._car_highway_x = car._car_highway_east_lane_x
        car._car_highway_exits = list(exit_ys)
        car._car_south_road0 = plan.south_road_full0
        car._car_north_shift = plan.north_shift
        car._car_exit_row = plan.exit_row
        car._car_on_highway = True
        car._car_exit_i = 0
        car._car_dir = (0, 1)
        car._car_heading = 90.0
        car._car_pos = list(car._car_highway_stop(0, car._car_dir))
        car._car_target = car._car_highway_stop(0, car._car_dir)
        car._car_state = "drive"
        car._signals = self._signals
        car._place_car()
        self.taskMgr.add(car._car_task, "car-drive")

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
        self._update_camera()

        self.accept("escape", sys.exit)
        self.accept("wheel_up", self._zoom, [0.94])
        self.accept("wheel_down", self._zoom, [1.0 / 0.94])
        self.accept("mouse1", self._start_drag)
        self.accept("mouse1-up", self._end_drag)
        self.taskMgr.add(self._drag_task, "orbit-drag")
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
