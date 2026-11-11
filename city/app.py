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
from city.materials import (
    block_material,
    centerline_material,
    lawn_material,
    mark_material,
    road_material,
    sphere_material,
)
from city.mesh import box_instance, make_rhombus_slab
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
        highway_length = hwy["highway_length"]
        highway_mid_y = hwy["highway_mid_y"]
        road_z = hwy["road_z"]
        diamonds = hwy["diamonds"]
        road_thickness = hwy["road_thickness"]
        east_mid_x = hwy["east_mid_x"]
        south_mid_y = hwy["south_mid_y"]
        north_mid_y = hwy["north_mid_y"]
        belt_west_inner = hwy["belt_west_inner"]
        belt_east_inner = hwy["belt_east_inner"]
        belt_south_inner = hwy["belt_south_inner"]
        belt_north_inner = hwy["belt_north_inner"]
        belt_west_outer = hwy["belt_west_outer"]
        belt_east_outer = hwy["belt_east_outer"]
        belt_south_outer = hwy["belt_south_outer"]
        belt_north_outer = hwy["belt_north_outer"]
        corner_radius = hwy["corner_radius"]
        ns_y0 = hwy["ns_y0"]
        ns_y1 = hwy["ns_y1"]
        ew_x0 = hwy["ew_x0"]
        ew_x1 = hwy["ew_x1"]
        ew_span = hwy["ew_span"]
        ew_mid_x = hwy["ew_mid_x"]
        corner_sw = hwy["corner_sw"]
        corner_se = hwy["corner_se"]
        corner_ne = hwy["corner_ne"]
        corner_nw = hwy["corner_nw"]
        corner_segments = 24

        self.highway = self.render.attachNewNode("highway")
        road_mat = road_material()
        mark_paint = mark_material()
        centre_divider = plan.highway_lanes // 2
        road_top = road_z + road_thickness / 2
        mark_z = road_top + 0.02
        mark_len = 2.0
        mark_w = 0.5
        mark_h = 0.04
        mark_gap = 1.0

        def add_ns_leg(mid_x: float, inner_edge_x: float, toward_east: bool) -> None:
            """Six-lane north-south carriageway between the rounded corners."""
            builders._add_block(
                mid_x,
                highway_mid_y,
                road_z,
                (highway_width, highway_length, road_thickness),
                road_mat,
                parent=self.highway,
            )
            for divider in range(1, plan.highway_lanes):
                if divider == centre_divider:
                    continue
                mark_x = (
                    inner_edge_x + divider * lane_width
                    if toward_east
                    else inner_edge_x - divider * lane_width
                )
                builders._add_road_marks(
                    mark_x,
                    highway_mid_y,
                    road_top,
                    highway_length,
                    along_x=False,
                    parent=self.highway,
                    paint=mark_paint,
                )

        def add_ew_leg(mid_y: float, inner_edge_y: float, toward_north: bool) -> None:
            """Six-lane east-west carriageway between the rounded corners."""
            builders._add_block(
                ew_mid_x,
                mid_y,
                road_z,
                (ew_span, highway_width, road_thickness),
                road_mat,
                parent=self.highway,
            )
            for divider in range(1, plan.highway_lanes):
                if divider == centre_divider:
                    continue
                mark_y = (
                    inner_edge_y + divider * lane_width
                    if toward_north
                    else inner_edge_y - divider * lane_width
                )
                builders._add_road_marks(
                    ew_mid_x,
                    mark_y,
                    road_top,
                    ew_span,
                    along_x=True,
                    parent=self.highway,
                    paint=mark_paint,
                )

        def add_corner(
            center: tuple[float, float],
            start_angle: float,
            end_angle: float,
        ) -> None:
            """Quarter-annulus road pad with curved lane dashes."""
            cx, cy = center
            builders._add_annulus_sector(
                cx,
                cy,
                road_z,
                corner_radius,
                corner_radius + highway_width,
                start_angle,
                end_angle,
                road_thickness,
                road_mat,
                parent=self.highway,
                segments=corner_segments,
            )
            sweep = end_angle - start_angle
            for divider in range(1, plan.highway_lanes):
                if divider == centre_divider:
                    continue
                radius = corner_radius + divider * lane_width
                arc_len = abs(sweep) * radius
                count = max(1, int((arc_len + mark_gap) / (mark_len + mark_gap)))
                for index in range(count):
                    t = (index + 0.5) / count
                    angle = start_angle + sweep * t
                    c = math.cos(angle)
                    s = math.sin(angle)
                    mark = box_instance(self.highway, mark_len, mark_w, mark_h)
                    mark.setPos(cx + radius * c, cy + radius * s, mark_z)
                    # Panda H is CCW from +X; local +X (dash length) follows the tangent.
                    mark.setH(math.degrees(angle) + 90.0)
                    mark.setMaterial(mark_paint, 1)

        add_ns_leg(highway_mid_x, highway_east, toward_east=False)
        add_ns_leg(east_mid_x, belt_east_inner, toward_east=True)
        add_ew_leg(south_mid_y, belt_south_inner, toward_north=False)
        add_ew_leg(north_mid_y, belt_north_inner, toward_north=True)
        add_corner(corner_sw, math.pi, 1.5 * math.pi)
        add_corner(corner_se, 1.5 * math.pi, 2.0 * math.pi)
        add_corner(corner_ne, 0.0, 0.5 * math.pi)
        add_corner(corner_nw, 0.5 * math.pi, math.pi)

        barrier_z = road_top + plan.barrier_h / 2
        fence_z = road_top + plan.fence_h / 2
        barrier_mat = block_material(0.75)
        fence_mat = block_material(0.55)
        # Slightly wider than a city road so angled diamond arms clear the curb.
        opening_half = plan.road_width * 0.75
        diamonds = hwy["diamonds"]
        ns_openings = sorted({d["hy"] for d in diamonds if d["axis"] == "ns"})
        ew_openings = sorted({d["hx"] for d in diamonds if d["axis"] == "ew"})

        def wall_segments_ns(
            x: float,
            width: float,
            height: float,
            z: float,
            mat,
            y0: float,
            y1: float,
            openings: list[float] | tuple[float, ...] = (),
        ) -> None:
            cursor = y0
            for open_y in openings:
                gap_start = open_y - opening_half
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
                cursor = open_y + opening_half
            if y1 > cursor:
                seg_len = y1 - cursor
                builders._add_block(
                    x,
                    cursor + seg_len / 2,
                    z,
                    (width, seg_len, height),
                    mat,
                    parent=self.highway,
                )

        def wall_segments_ew(
            y: float,
            depth: float,
            height: float,
            z: float,
            mat,
            x0: float,
            x1: float,
            openings: list[float] | tuple[float, ...] = (),
        ) -> None:
            cursor = x0
            for open_x in openings:
                gap_start = open_x - opening_half
                if gap_start > cursor:
                    seg_len = gap_start - cursor
                    builders._add_block(
                        cursor + seg_len / 2,
                        y,
                        z,
                        (seg_len, depth, height),
                        mat,
                        parent=self.highway,
                    )
                cursor = open_x + opening_half
            if x1 > cursor:
                seg_len = x1 - cursor
                builders._add_block(
                    cursor + seg_len / 2,
                    y,
                    z,
                    (seg_len, depth, height),
                    mat,
                    parent=self.highway,
                )

        def add_arc_wall(
            center: tuple[float, float],
            radius: float,
            start_angle: float,
            end_angle: float,
            radial_thickness: float,
            height: float,
            z: float,
            mat,
            segments: int = corner_segments,
        ) -> None:
            """Approximate a curved wall with short boxes tangent to the arc."""
            cx, cy = center
            sweep = end_angle - start_angle
            for index in range(segments):
                t0 = index / segments
                t1 = (index + 1) / segments
                a0 = start_angle + sweep * t0
                a1 = start_angle + sweep * t1
                mid = 0.5 * (a0 + a1)
                c = math.cos(mid)
                s = math.sin(mid)
                chord = max(abs(a1 - a0) * radius, 0.05)
                wall = box_instance(self.highway, radial_thickness, chord, height)
                wall.setPos(cx + radius * c, cy + radius * s, z)
                # Local +X is radial thickness; Panda H is CCW from +X.
                wall.setH(math.degrees(mid))
                wall.setMaterial(mat, 1)

        # Straight medians + city-side fences, gapped at diamond connectors.
        wall_segments_ns(
            highway_mid_x,
            plan.barrier_w,
            plan.barrier_h,
            barrier_z,
            barrier_mat,
            ns_y0,
            ns_y1,
            ns_openings,
        )
        wall_segments_ns(
            fence_x,
            plan.fence_w,
            plan.fence_h,
            fence_z,
            fence_mat,
            ns_y0,
            ns_y1,
            ns_openings,
        )
        wall_segments_ns(
            east_mid_x,
            plan.barrier_w,
            plan.barrier_h,
            barrier_z,
            barrier_mat,
            ns_y0,
            ns_y1,
            ns_openings,
        )
        wall_segments_ns(
            hwy["east_fence_x"],
            plan.fence_w,
            plan.fence_h,
            fence_z,
            fence_mat,
            ns_y0,
            ns_y1,
            ns_openings,
        )
        wall_segments_ew(
            south_mid_y,
            plan.barrier_w,
            plan.barrier_h,
            barrier_z,
            barrier_mat,
            ew_x0,
            ew_x1,
            ew_openings,
        )
        wall_segments_ew(
            hwy["south_fence_y"],
            plan.fence_w,
            plan.fence_h,
            fence_z,
            fence_mat,
            ew_x0,
            ew_x1,
            ew_openings,
        )
        wall_segments_ew(
            north_mid_y,
            plan.barrier_w,
            plan.barrier_h,
            barrier_z,
            barrier_mat,
            ew_x0,
            ew_x1,
            ew_openings,
        )
        wall_segments_ew(
            hwy["north_fence_y"],
            plan.fence_w,
            plan.fence_h,
            fence_z,
            fence_mat,
            ew_x0,
            ew_x1,
            ew_openings,
        )
        # Curved median + city-side fence through each rounded corner.
        median_r = corner_radius + highway_width / 2
        fence_r = corner_radius - plan.fence_w / 2
        for center, a0, a1 in (
            (corner_sw, math.pi, 1.5 * math.pi),
            (corner_se, 1.5 * math.pi, 2.0 * math.pi),
            (corner_ne, 0.0, 0.5 * math.pi),
            (corner_nw, 0.5 * math.pi, math.pi),
        ):
            add_arc_wall(
                center,
                median_r,
                a0,
                a1,
                plan.barrier_w,
                plan.barrier_h,
                barrier_z,
                barrier_mat,
            )
            add_arc_wall(
                center,
                fence_r,
                a0,
                a1,
                plan.fence_w,
                plan.fence_h,
                fence_z,
                fence_mat,
            )

        slip_paint = centerline_material()
        lawn_mat = lawn_material()

        def add_slip_segment(
            x0: float,
            y0: float,
            x1: float,
            y1: float,
            width: float,
        ) -> None:
            """Angled asphalt slab with a few centerline dashes."""
            dx = x1 - x0
            dy = y1 - y0
            length = math.hypot(dx, dy)
            if length < 0.05:
                return
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            heading = math.degrees(math.atan2(dy, dx))
            pad = box_instance(self.highway, length, width, road_thickness)
            pad.setPos(cx, cy, road_z)
            pad.setH(heading)
            pad.setMaterial(road_mat, 1)
            mark_len = 1.6
            mark_w = 0.35
            count = max(1, int((length + 1.0) / 3.2))
            for index in range(count):
                t = (index + 0.5) / count
                mark = box_instance(self.highway, mark_len, mark_w, mark_h)
                mark.setPos(x0 + dx * t, y0 + dy * t, mark_z)
                mark.setH(heading)
                mark.setMaterial(slip_paint, 1)

        def add_diamond_ground(
            verts: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]],
            inset: float,
        ) -> None:
            """Lawn under the whole footprint, then a tighter grass median island."""
            xs = [v[0] for v in verts]
            ys = [v[1] for v in verts]
            pad = plan.road_width * 0.6
            builders._add_block(
                (min(xs) + max(xs)) / 2,
                (min(ys) + max(ys)) / 2,
                road_z - 0.02,
                (max(xs) - min(xs) + pad, max(ys) - min(ys) + pad, road_thickness * 0.85),
                lawn_mat,
                parent=self.highway,
            )
            cx = sum(xs) / 4.0
            cy = sum(ys) / 4.0
            # Pull vertices inward so the island sits inside the road ribbons.
            scale = max(
                0.35,
                1.0 - inset / max(abs(verts[0][0] - cx), abs(verts[0][1] - cy), 1.0),
            )
            inner = tuple(
                (cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in verts
            )
            island = self.highway.attachNewNode(
                make_rhombus_slab(inner, road_thickness * 0.9)
            )
            island.setPos(0.0, 0.0, road_z - 0.01)
            island.setMaterial(lawn_mat, 1)

        def add_diamond(diamond: dict) -> None:
            """City-side diamond: four slip ramps, grass median, belt connector."""
            hx = diamond["hx"]
            hy = diamond["hy"]
            rw = plan.road_width
            side = diamond["side"]
            stub = rw * 0.7
            # Bite into the carriageway so slips visually merge with the belt.
            merge = rw * 0.55
            # Split the highway throat so the two slips meet the curb apart.
            throat = opening_half * 0.85

            if side == "west":
                city_x = diamond["city_x"]
                gap = abs(city_x - belt_west_inner)
                span = max(diamond["slip_len"], gap * 0.85)
                mid_x = (city_x + belt_west_inner) / 2
                hwy_n = (belt_west_inner - merge, hy + throat)
                hwy_s = (belt_west_inner - merge, hy - throat)
                city_v = (city_x, hy)
                north_v = (mid_x, hy + span)
                south_v = (mid_x, hy - span)
                add_diamond_ground(
                    (hwy_n, north_v, city_v, south_v),
                    rw * 0.55,
                )
                # Curb pad tying both slip ends into the carriageway opening.
                builders._add_block(
                    belt_west_inner - merge / 2,
                    hy,
                    road_z,
                    (merge + rw * 0.15, opening_half * 2, road_thickness),
                    road_mat,
                    parent=self.highway,
                )
                for a, b in (
                    (hwy_n, north_v),
                    (north_v, city_v),
                    (city_v, south_v),
                    (south_v, hwy_s),
                ):
                    add_slip_segment(a[0], a[1], b[0], b[1], rw)
                x_end = belt_west_outer - stub
                builders._add_block(
                    (city_x + x_end) / 2,
                    hy,
                    road_z,
                    (abs(x_end - city_x), rw, road_thickness),
                    road_mat,
                    parent=self.highway,
                )
            elif side == "east":
                city_x = diamond["city_x"]
                gap = abs(city_x - belt_east_inner)
                span = max(diamond["slip_len"], gap * 0.85)
                mid_x = (city_x + belt_east_inner) / 2
                hwy_n = (belt_east_inner + merge, hy + throat)
                hwy_s = (belt_east_inner + merge, hy - throat)
                city_v = (city_x, hy)
                north_v = (mid_x, hy + span)
                south_v = (mid_x, hy - span)
                add_diamond_ground(
                    (hwy_s, south_v, city_v, north_v),
                    rw * 0.55,
                )
                builders._add_block(
                    belt_east_inner + merge / 2,
                    hy,
                    road_z,
                    (merge + rw * 0.15, opening_half * 2, road_thickness),
                    road_mat,
                    parent=self.highway,
                )
                for a, b in (
                    (hwy_n, north_v),
                    (north_v, city_v),
                    (city_v, south_v),
                    (south_v, hwy_s),
                ):
                    add_slip_segment(a[0], a[1], b[0], b[1], rw)
                x_end = belt_east_outer + stub
                builders._add_block(
                    (city_x + x_end) / 2,
                    hy,
                    road_z,
                    (abs(x_end - city_x), rw, road_thickness),
                    road_mat,
                    parent=self.highway,
                )
            elif side == "south":
                city_y = diamond["city_y"]
                gap = abs(city_y - belt_south_inner)
                span = max(diamond["slip_len"], gap * 0.85)
                mid_y = (city_y + belt_south_inner) / 2
                hwy_w = (hx - throat, belt_south_inner - merge)
                hwy_e = (hx + throat, belt_south_inner - merge)
                city_v = (hx, city_y)
                west_v = (hx - span, mid_y)
                east_v = (hx + span, mid_y)
                add_diamond_ground(
                    (hwy_e, east_v, city_v, west_v),
                    rw * 0.55,
                )
                builders._add_block(
                    hx,
                    belt_south_inner - merge / 2,
                    road_z,
                    (opening_half * 2, merge + rw * 0.15, road_thickness),
                    road_mat,
                    parent=self.highway,
                )
                for a, b in (
                    (hwy_w, west_v),
                    (west_v, city_v),
                    (city_v, east_v),
                    (east_v, hwy_e),
                ):
                    add_slip_segment(a[0], a[1], b[0], b[1], rw)
                y_end = belt_south_outer - stub
                builders._add_block(
                    hx,
                    (city_y + y_end) / 2,
                    road_z,
                    (rw, abs(y_end - city_y), road_thickness),
                    road_mat,
                    parent=self.highway,
                )
            else:  # north
                city_y = diamond["city_y"]
                gap = abs(city_y - belt_north_inner)
                span = max(diamond["slip_len"], gap * 0.85)
                mid_y = (city_y + belt_north_inner) / 2
                hwy_w = (hx - throat, belt_north_inner + merge)
                hwy_e = (hx + throat, belt_north_inner + merge)
                city_v = (hx, city_y)
                west_v = (hx - span, mid_y)
                east_v = (hx + span, mid_y)
                add_diamond_ground(
                    (hwy_w, west_v, city_v, east_v),
                    rw * 0.55,
                )
                builders._add_block(
                    hx,
                    belt_north_inner + merge / 2,
                    road_z,
                    (opening_half * 2, merge + rw * 0.15, road_thickness),
                    road_mat,
                    parent=self.highway,
                )
                for a, b in (
                    (hwy_w, west_v),
                    (west_v, city_v),
                    (city_v, east_v),
                    (east_v, hwy_e),
                ):
                    add_slip_segment(a[0], a[1], b[0], b[1], rw)
                y_end = belt_north_outer + stub
                builders._add_block(
                    hx,
                    (city_y + y_end) / 2,
                    road_z,
                    (rw, abs(y_end - city_y), road_thickness),
                    road_mat,
                    parent=self.highway,
                )

        for diamond in diamonds:
            add_diamond(diamond)
        self.highway.flattenStrong()

        self._cars: list[CarController] = []
        west_lane_xs = list(hwy["west_lane_xs"])
        east_lane_xs = list(hwy["east_lane_xs"])
        south_lane_ys = list(hwy["south_lane_ys"])
        north_lane_ys = list(hwy["north_lane_ys"])
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
        hwy_half = plan.highway_lanes // 2
        # Highway: one car per lane/direction at each diamond (keeps FPS healthy).
        for exit_i, diamond in enumerate(diamonds):
            for start_dir in (tuple(diamond["ccw_dir"]), tuple(diamond["cw_dir"])):
                for lane in range(hwy_half):
                    spawns.append(
                        {
                            "start_v": diamond["city_v"],
                            "start_h": diamond["city_h"],
                            "start_dir": start_dir,
                            "on_highway": True,
                            "exit_i": exit_i,
                            "origin_y": diamond["city_origin_y"],
                            "queue": 0,
                            "highway_lane": lane,
                        }
                    )
        # City streets across both twins, including diamond gateway nodes.
        city_dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
        city_nodes = {
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
        }
        for diamond in diamonds:
            city_nodes.add((diamond["city_v"], diamond["city_h"]))
        for origin_y in city_origins:
            for v, h in city_nodes:
                for di, start_dir in enumerate(city_dirs):
                    if (v + h + di) % 2 != 0:
                        continue
                    queued = h == plan.exit_row and start_dir[1] == 0
                    for queue in range(2 if queued else 1):
                        spawns.append(
                            {
                                "start_v": v,
                                "start_h": h,
                                "start_dir": start_dir,
                                "on_highway": False,
                                "exit_i": 0,
                                "origin_y": origin_y,
                                "queue": queue,
                                "highway_lane": 0,
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
            car._car_diamonds = list(diamonds)
            car._car_highway_lanes = plan.highway_lanes
            car._car_west_lane_xs = west_lane_xs
            car._car_east_lane_xs = east_lane_xs
            car._car_south_lane_ys = south_lane_ys
            car._car_north_lane_ys = north_lane_ys
            car._car_highway_lane_xs = west_lane_xs  # legacy alias
            car._car_ns_y0 = ns_y0
            car._car_ns_y1 = ns_y1
            car._car_ew_x0 = ew_x0
            car._car_ew_x1 = ew_x1
            car._car_corner_nw = corner_nw
            car._car_corner_ne = corner_ne
            car._car_corner_se = corner_se
            car._car_corner_sw = corner_sw
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
                car._car_set_highway_lane(car._car_dir, pick=False, snap=True)
                approach = car._car_highway_stop(car._car_exit_i, car._car_dir)
            else:
                approach = car._car_stop_xy(*car._car_to, car._car_dir)
            dx, dy = spawn["start_dir"]
            queue = spawn["queue"]
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
        CarController.build_fleet_index(self._cars)
        for car in self._cars:
            car._car_refresh_neighbors(resolve=False)
        # One fleet task instead of N car tasks — less scheduler overhead.
        self.taskMgr.add(self._fleet_task, "car-fleet")

        bounds = plan.framing_bounds(cube_center_x, pyramid_size[0] / 2)
        left = bounds["left"]
        right = bounds["right"]
        frame_south = bounds["city_south"]
        frame_north = bounds["city_north"]
        stack_bottom = bounds["stack_bottom"]
        stack_top = bounds["stack_top"]
        self.look_at = (
            (left + right) / 2,
            (frame_south + frame_north) / 2,
            (stack_bottom + stack_top) / 2,
        )
        self.heading = 30.0
        self.pitch = 20.0
        half_fov = math.tan(math.radians(20.0))
        fit_x = ((right - left) / 2) / half_fov / math.cos(math.radians(self.heading))
        fit_y = ((frame_north - frame_south) / 2) / half_fov / math.cos(math.radians(self.pitch))
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
        # One spatial/corridor index for the whole fleet, then each car updates.
        CarController.build_fleet_index(self._cars)
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
