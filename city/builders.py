"""Scene builders: lots, roads, signals, houses, lights."""

from __future__ import annotations

import math

from panda3d.core import (
    AmbientLight,
    ColorAttrib,
    DirectionalLight,
    Material,
    NodePath,
)

from city.materials import (
    BLOCK_SHADES,
    block_material,
    brown_material,
    centerline_material,
    lawn_material,
    mark_material,
    plinth_material,
    road_material,
    roof_material,
    sidewalk_material,
    signal_lens_material,
    signal_material,
    square_lightness,
    square_material,
    stack_material,
)
from city.mesh import (
    box_instance,
    factory_template,
    lamp_template,
    make_annulus_sector,
    make_gable_roof,
    make_sky_dome,
    tree_template,
)
from city.plan import CityPlan


class SceneBuilders:
    """Mesh placement helpers bound to a city NodePath and layout plan."""

    def __init__(self, city: NodePath, plan: CityPlan, render: NodePath) -> None:
        self.city = city
        self.plan = plan
        self.render = render

    def _add_city_block(
        self,
        west_face: float,
        block_size: tuple[float, float, float],
        floors: tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]],
        *,
        y_offset: float = 0.0,
        eastern_road: bool,
        southern_road: bool,
        factory: bool = True,
    ) -> None:
        """One ring of towers with a road along each outer face.

        ``west_face`` is the western face of the western towers. ``y_offset``
        shifts the whole ring north. A road that faces another block is left
        out, along with its corner squares, so the rings share one road.
        All-empty floors still draw a 2x5-sized road loop (29 by 11); with
        ``factory`` True they also get a grey factory from the shared
        flattened template, nine units tall.
        """
        south_floors, west_floors, east_floors, north_floors = floors
        empty = not (south_floors or west_floors or east_floors or north_floors)
        tower_gap = self.plan.tower_gap
        # Empty rings keep the same footprint as a depth-2, five-wide ring.
        tower_count = self.plan.tower_count if empty else len(south_floors)
        road_length = tower_count * block_size[0] + (tower_count - 1) * tower_gap
        # East-west slab. Each tower's front face meets the near edge, and the slab
        # runs from the first tower's left edge to the last tower's right edge.
        road_size = (road_length, self.plan.road_width, 0.1)
        road_y = -(block_size[1] / 2 + 1.0 + road_size[1] / 2)
        road_z = -block_size[2] / 2 + road_size[2] / 2
        tower_y = road_y + road_size[1] / 2 + block_size[1] / 2 + y_offset

        shades = iter(BLOCK_SHADES)
        # Front (-Y) meets the south road. The two end stacks also meet a side road.
        for tower, count in enumerate(south_floors):
            tower_x = west_face + block_size[0] / 2 + tower * (block_size[0] + tower_gap)
            doors = ("-y",)
            if tower == 0:
                doors = ("-y", "-x")
            elif tower == len(south_floors) - 1:
                doors = ("-y", "+x")
            self._add_stack(tower_x, tower_y, count, block_size, block_material(next(shades)), doors=doors)

        # North of the leftmost tower. Positive heading turns the front (+X);
        # -90 degrees sends the front face from -Y to -X, 90 degrees clockwise.
        # The northern end also meets the north road on its local -X face.
        leftmost_x = west_face + block_size[0] / 2
        for index, count in enumerate(west_floors):
            north_y = tower_y + (index + 1) * (block_size[1] + tower_gap)
            doors = ("-y", "-x") if index == len(west_floors) - 1 else ("-y",)
            self._add_stack(
                leftmost_x,
                north_y,
                count,
                block_size,
                block_material(next(shades)),
                heading=-90,
                doors=doors,
            )

        # North of the rightmost tower. +90 degrees sends the front from -Y to +X,
        # 90 degrees counterclockwise. The northern end meets the north road on +X.
        rightmost_x = west_face + block_size[0] / 2 + (tower_count - 1) * (block_size[0] + tower_gap)
        for index, count in enumerate(east_floors):
            north_y = tower_y + (index + 1) * (block_size[1] + tower_gap)
            doors = ("-y", "+x") if index == len(east_floors) - 1 else ("-y",)
            self._add_stack(
                rightmost_x,
                north_y,
                count,
                block_size,
                block_material(next(shades)),
                heading=90,
                doors=doors,
            )

        # North row. Side columns put the corners; an empty west/east column
        # means this row is the full width, including the NW and NE corners.
        # Depth matches the side columns, or one step north of south when none.
        # A fully empty ring still uses depth 2 so the road loop stays 11 deep.
        spacing_y = block_size[1] + tower_gap
        if west_floors:
            north_step = len(west_floors)
        elif north_floors or empty:
            north_step = 1
        else:
            north_step = 0
        top_y = tower_y + north_step * spacing_y
        stride = block_size[0] + tower_gap
        if west_floors or east_floors:
            north_indices = range(1, len(north_floors) + 1)
            north_items = zip(north_indices, north_floors)
        else:
            north_items = enumerate(north_floors)
        for index, count in north_items:
            doors = ("-y",)
            if not (west_floors or east_floors):
                if index == 0:
                    # Heading 180: local +X faces west.
                    doors = ("-y", "+x")
                elif index == len(north_floors) - 1:
                    # Heading 180: local -X faces east.
                    doors = ("-y", "-x")
            self._add_stack(
                leftmost_x + index * stride,
                top_y,
                count,
                block_size,
                block_material(next(shades)),
                heading=180,
                doors=doors,
            )

        # One road in front of each side. The near edge meets that side's outer face.
        road_width = road_size[1]
        south = tower_y - block_size[1] / 2
        north = top_y + block_size[1] / 2
        west = leftmost_x - block_size[0] / 2
        east = rightmost_x + block_size[0] / 2
        mid_x = (west + east) / 2
        mid_y = (south + north) / 2
        if empty and factory:
            # Same plan as the ring, nine units tall, bottom flush with the towers.
            # Identical lots reuse one flattened template via copyTo.
            factory_height = 9.0
            building = factory_template(
                east - west,
                north - south,
                factory_height,
                -block_size[2] / 2,
            ).copyTo(self.city)
            building.setPos(mid_x, mid_y, 0.0)
        # Thin road-coloured pads in the one-unit gaps between neighbouring towers.
        gap_thickness = road_size[2]
        if south_floors and north_floors and not west_floors and not east_floors:
            depth = north - south
            for index in range(tower_count - 1):
                gap_x = west + block_size[0] + index * stride + tower_gap / 2
                self._add_block(
                    gap_x,
                    mid_y,
                    road_z,
                    (tower_gap, depth, gap_thickness),
                    road_material(),
                )
            for index in range(tower_count):
                tower_x = leftmost_x + index * stride
                self._add_block(
                    tower_x,
                    mid_y,
                    road_z,
                    (block_size[0], tower_gap, gap_thickness),
                    road_material(),
                )
        if southern_road:
            self._add_road(
                mid_x, south - road_width / 2, road_z, east - west, along_x=True,
                sidewalk_inner=1.0,
            )
        self._add_road(
            mid_x, north + road_width / 2, road_z, east - west, along_x=True,
            sidewalk_inner=-1.0,
        )
        self._add_road(
            west - road_width / 2, mid_y, road_z, north - south, along_x=False,
            sidewalk_inner=1.0,
        )
        if eastern_road:
            self._add_road(
                east + road_width / 2, mid_y, road_z, north - south, along_x=False,
                sidewalk_inner=-1.0,
            )
        # The straight sections stop at the building faces. Each corner square
        # joins the two roads that meet there, so a side with no road has no corners.
        x_edges = ((west, -1.0), (east, 1.0)) if eastern_road else ((west, -1.0),)
        y_edges = ((south, -1.0), (north, 1.0)) if southern_road else ((north, 1.0),)
        walk_w = 0.95
        for x_edge, x_sign in x_edges:
            for y_edge, y_sign in y_edges:
                cx = x_edge + x_sign * road_width / 2
                cy = y_edge + y_sign * road_width / 2
                self._add_block(
                    cx,
                    cy,
                    road_z,
                    (road_width, road_width, road_size[2]),
                    road_material(),
                )
                # Corner walk pads sit on the lot-side quadrant of the asphalt.
                road_top = road_z + road_size[2] / 2
                self._add_block(
                    cx - x_sign * (road_width / 2 - walk_w / 2),
                    cy - y_sign * (road_width / 2 - walk_w / 2),
                    road_top + 0.04,
                    (walk_w, walk_w, 0.08),
                    sidewalk_material(),
                )

    def _add_stack(
        self,
        x: float,
        y: float,
        floors: int,
        size: tuple[float, float, float],
        material: Material,
        heading: float = 0.0,
        doors: tuple[str, ...] = ("-y",),
    ) -> None:
        """Stack ``floors`` with setbacks, belt courses, and a roof crown.

        Upper thirds step in so the silhouette isn't a single extruded box.
        """
        parent = None
        if heading:
            parent = self.city.attachNewNode("tower")
            parent.setPos(x, y, 0)
            parent.setH(heading)
            x, y = 0.0, 0.0
        sx, sy, sz = size
        # Slightly proud base so the ground floor meets the sidewalk.
        plinth_h = 0.32
        self._add_block(
            x,
            y,
            -sz / 2 + plinth_h / 2,
            (sx + 0.45, sy + 0.45, plinth_h),
            plinth_material(),
            parent=parent,
        )
        # Slim corner pilasters on the lowest massing step.
        pilaster = block_material(0.78)
        for px, py in (
            (-sx / 2, -sy / 2),
            (sx / 2, -sy / 2),
            (-sx / 2, sy / 2),
            (sx / 2, sy / 2),
        ):
            self._add_block(
                x + px * 0.92,
                y + py * 0.92,
                (min(floors, 6) * sz) / 2 - sz / 2,
                (0.22, 0.22, min(floors, 6) * sz),
                pilaster,
                parent=parent,
            )

        for floor in range(floors):
            # Step the plan in for mid and upper tiers.
            if floor >= max(2, (floors * 3) // 4):
                inset = 0.45
            elif floor >= max(1, floors // 2):
                inset = 0.22
            else:
                inset = 0.0
            floor_size = (sx - 2.0 * inset, sy - 2.0 * inset, sz)
            floor_z = floor * sz
            self._add_block(
                x,
                y,
                floor_z,
                floor_size,
                material,
                top=False,
                bottom=floor == 0,
                parent=parent,
            )
            self._add_face_squares(
                x, y, floor_z, floor_size, floor * 12, parent=parent, doors=doors,
            )
            # Thin belt course every few floors — breaks the flat curtain wall.
            if floor > 0 and floor % 3 == 0 and inset < 0.4:
                self._add_block(
                    x,
                    y,
                    floor_z - sz / 2 + 0.06,
                    (floor_size[0] + 0.12, floor_size[1] + 0.12, 0.12),
                    block_material(0.88),
                    parent=parent,
                )

        top_inset = 0.45 if floors >= 4 else 0.0
        top_sx = sx - 2.0 * top_inset
        top_sy = sy - 2.0 * top_inset
        top_z = (floors - 1) * sz + sz / 2
        # Cornice + mechanical crown, sized to the uppermost setback.
        self._add_block(
            x,
            y,
            top_z + 0.06,
            (top_sx + 0.22, top_sy + 0.22, 0.14),
            block_material(0.82),
            parent=parent,
        )
        self._add_block(
            x,
            y,
            top_z + 0.18,
            (top_sx - 0.1, top_sy - 0.1, 0.12),
            roof_material(),
            parent=parent,
        )
        if floors >= 10:
            unit = stack_material()
            self._add_block(
                x - top_sx * 0.22,
                y + top_sy * 0.18,
                top_z + 0.55,
                (0.65, 0.5, 0.75),
                unit,
                parent=parent,
            )
            self._add_block(
                x + top_sx * 0.18,
                y - top_sy * 0.12,
                top_z + 0.48,
                (0.5, 0.5, 0.55),
                unit,
                parent=parent,
            )
            # Slim antenna / mast so the crown isn't another box.
            self._add_block(
                x + top_sx * 0.05,
                y + top_sy * 0.05,
                top_z + 1.1,
                (0.12, 0.12, 1.4),
                unit,
                parent=parent,
            )

    def _add_block(
        self,
        x: float,
        y: float,
        z: float,
        size: tuple[float, float, float],
        material: Material,
        top: bool = True,
        bottom: bool = True,
        parent=None,
    ) -> None:
        root = self.city if parent is None else parent
        block = box_instance(root, *size, top=top, bottom=bottom)
        block.setPos(x, y, z)
        block.setMaterial(material, 1)

    def _add_annulus_sector(
        self,
        x: float,
        y: float,
        z: float,
        inner_radius: float,
        outer_radius: float,
        start_angle: float,
        end_angle: float,
        thickness: float,
        material: Material,
        parent=None,
        segments: int = 24,
    ) -> None:
        """Place a flat annular sector centred at ``(x, y, z)``."""
        root = self.city if parent is None else parent
        pad = root.attachNewNode(
            make_annulus_sector(
                inner_radius,
                outer_radius,
                start_angle,
                end_angle,
                thickness,
                segments=segments,
            )
        )
        pad.setPos(x, y, z)
        pad.setMaterial(material, 1)

    def _add_face_squares(
        self,
        x: float,
        y: float,
        z: float,
        size: tuple[float, float, float],
        level_start: int = 0,
        parent=None,
        doors: tuple[str, ...] = ("-y",),
    ) -> None:
        """Three portrait windows on every vertical face, inset from the edges.

        ``doors`` names ground-floor faces that meet a road ("-y", "+y", "-x", "+x").
        The centre window on each of those faces is a door instead.
        """
        root = self.city if parent is None else parent
        sx, sy, sz = size
        # Portrait office panes leave a concrete frame around each opening.
        win_w = 0.78
        win_h = 1.15
        margin_x = 0.55
        depth = 0.05
        row_z = z - sz / 2 + (sz - win_h) / 2 + win_h / 2
        level = level_start
        door_faces = set(doors)

        def centers(span: float) -> tuple[float, float, float]:
            left = -span / 2 + margin_x + win_w / 2
            right = span / 2 - margin_x - win_w / 2
            return (left, (left + right) / 2, right)

        def add_door(px: float, py: float, width_along_x: bool) -> None:
            door_width = 0.9
            door_height = 1.35
            door_bottom = z - sz / 2
            if width_along_x:
                panel = box_instance(root, door_width, depth, door_height)
            else:
                panel = box_instance(root, depth, door_width, door_height)
            panel.setPos(px, py, door_bottom + door_height / 2)
            panel.setMaterial(brown_material(), 1)

        along_x = centers(sx)
        along_y = centers(sy)
        for sign in (1.0, -1.0):
            face = "+y" if sign > 0 else "-y"
            # Sit slightly proud so glass catches the sun against the wall.
            face_y = y + sign * (sy / 2 + depth / 2)
            for offset in along_x:
                tone = square_lightness(level)
                level += 1
                if z == 0 and offset == 0 and face in door_faces:
                    add_door(x + offset, face_y, width_along_x=True)
                    continue
                panel = box_instance(root, win_w, depth, win_h)
                panel.setPos(x + offset, face_y, row_z)
                panel.setMaterial(square_material(tone), 1)
            face = "+x" if sign > 0 else "-x"
            face_x = x + sign * (sx / 2 + depth / 2)
            for offset in along_y:
                tone = square_lightness(level)
                level += 1
                if z == 0 and offset == 0 and face in door_faces:
                    add_door(face_x, y + offset, width_along_x=False)
                    continue
                panel = box_instance(root, depth, win_w, win_h)
                panel.setPos(face_x, y + offset, row_z)
                panel.setMaterial(square_material(tone), 1)

    def _add_signal_post(
        self,
        x: float,
        y: float,
        road_top: float,
        block_size: tuple[float, float, float],
    ) -> None:
        """Mast post with a wider base flange up to traffic-light height."""
        floor = block_size[2]
        rod_thin = floor * 0.06
        rod_z = road_top + 8.0
        post_h = rod_z - road_top
        trim = signal_material("trim")
        housing = signal_material("housing")
        base_h = floor * 0.2
        base = box_instance(self.city, rod_thin * 3.2, rod_thin * 3.2, base_h)
        base.setPos(x, y, road_top + base_h / 2)
        base.setMaterial(trim, 1)
        post = box_instance(self.city, rod_thin, rod_thin, post_h - base_h)
        post.setPos(x, y, road_top + base_h + (post_h - base_h) / 2)
        post.setMaterial(housing, 1)

    def _add_traffic_light(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        road_top: float,
        block_size: tuple[float, float, float],
        *,
        face_x: float,
        face_y: float,
    ) -> None:
        """Signal hung under a mast arm: backboard, yellow head, visored lenses."""
        floor = block_size[2]
        rod_z = road_top + 8.0
        box_w = floor * 0.42
        box_d = floor * 0.22
        box_h = floor * 1.35
        lamp = floor * 0.26
        lamp_depth = floor * 0.05
        gap = floor * 0.08
        rod_thin = floor * 0.06
        housing = signal_material("housing")
        trim = signal_material("trim")

        along_x = abs(x1 - x0) >= abs(y1 - y0)
        # Mast along X faces N/S traffic; mast along Y faces E/W.
        axis = "ns" if along_x else "ew"
        rod_len = abs(x1 - x0) if along_x else abs(y1 - y0)
        mid_x = (x0 + x1) / 2
        mid_y = (y0 + y1) / 2
        if along_x:
            rod = box_instance(self.city, rod_len, rod_thin, rod_thin)
        else:
            rod = box_instance(self.city, rod_thin, rod_len, rod_thin)
        rod.setPos(mid_x, mid_y, rod_z)
        rod.setMaterial(housing, 1)

        # Hang from the underside of the mast arm, facing the intersection.
        hang = floor * 0.2
        root = self.city.attachNewNode("traffic-light")
        root.setPos(mid_x, mid_y, rod_z - rod_thin / 2 - hang - box_h / 2)
        root.lookAt(face_x, face_y, root.getZ())

        # Short drop pipe from the arm into the head.
        drop = box_instance(root, rod_thin * 0.9, rod_thin * 0.9, hang)
        drop.setPos(0.0, 0.0, box_h / 2 + hang / 2)
        drop.setMaterial(trim, 1)

        # Dark backboard behind the head (reads clearly from a distance).
        board_w = box_w * 1.55
        board_h = box_h * 1.12
        board = box_instance(root, board_w, floor * 0.04, board_h)
        board.setPos(0.0, -box_d / 2 - floor * 0.02, 0.0)
        board.setMaterial(trim, 1)

        head = box_instance(root, box_w, box_d, box_h)
        head.setPos(0.0, 0.0, 0.0)
        head.setMaterial(housing, 1)

        lamp_y = box_d / 2 + lamp_depth / 2
        # Top to bottom: red, amber, green. Axis materials are phase-mutated.
        colours = ("red", "amber", "green")
        span = 3 * lamp + 2 * gap
        visor_depth = floor * 0.14
        visor_h = floor * 0.05
        for index, name in enumerate(colours):
            lamp_z = span / 2 - lamp / 2 - index * (lamp + gap)
            lens = box_instance(root, lamp, lamp_depth, lamp)
            lens.setPos(0.0, lamp_y, lamp_z)
            lens.setMaterial(signal_lens_material(name, axis), 1)
            # Hood over each lens so they read as real signal visors.
            visor = box_instance(root, lamp * 1.15, visor_depth, visor_h)
            visor.setPos(
                0.0,
                box_d / 2 + visor_depth / 2,
                lamp_z + lamp / 2 - visor_h / 2,
            )
            visor.setMaterial(trim, 1)

    def _add_road(
        self,
        x: float,
        y: float,
        z: float,
        length: float,
        along_x: bool,
        parent=None,
        *,
        sidewalk_inner: float | None = None,
    ) -> None:
        """Asphalt slab with center dashes and optional inner curb/sidewalk.

        ``sidewalk_inner`` is the signed offset from the road centre toward the
        lot (+Y for an EW road, +X for an NS road). Omit for highway-only pads.
        """
        width = self.plan.road_width
        thickness = 0.1
        size = (length, width, thickness) if along_x else (width, length, thickness)
        self._add_block(x, y, z, size, road_material(), parent=parent)
        self._add_road_marks(
            x, y, z + thickness / 2, length, along_x, parent=parent
        )
        if sidewalk_inner is None:
            return
        # Towers sit flush with the curb line, so the walk overlays the lot-side
        # strip of asphalt instead of disappearing under the facade.
        walk_w = 0.85
        walk_h = 0.08
        road_top = z + thickness / 2
        sign = 1.0 if sidewalk_inner >= 0 else -1.0
        edge = width / 2
        if along_x:
            walk_y = y + sign * (edge - walk_w / 2)
            self._add_block(
                x, walk_y, road_top + walk_h / 2,
                (length, walk_w, walk_h), sidewalk_material(), parent=parent,
            )
        else:
            walk_x = x + sign * (edge - walk_w / 2)
            self._add_block(
                walk_x, y, road_top + walk_h / 2,
                (walk_w, length, walk_h), sidewalk_material(), parent=parent,
            )

    def _add_road_marks(
        self,
        x: float,
        y: float,
        road_top: float,
        road_length: float,
        along_x: bool = True,
        parent=None,
        *,
        paint: Material | None = None,
    ) -> None:
        """Dashes on the road centerline, one unit apart edge to edge."""
        length = 2.0
        width = 0.5
        gap = 1.0
        thickness = 0.04
        # As many 2-unit dashes as fit with a 1-unit gap, centered on the road.
        count = int((road_length + gap) / (length + gap))
        span = count * length + (count - 1) * gap
        z = road_top + thickness / 2
        paint = paint if paint is not None else centerline_material()
        root = self.city if parent is None else parent
        for index in range(count):
            offset = -span / 2 + length / 2 + index * (length + gap)
            if along_x:
                mark = box_instance(root, length, width, thickness)
                mark.setPos(x + offset, y, z)
            else:
                mark = box_instance(root, width, length, thickness)
                mark.setPos(x, y + offset, z)
            mark.setMaterial(paint, 1)

    def _add_housing_lot(
        self,
        west_face: float,
        block_size: tuple[float, float, float],
        lot_width: float,
        lot_depth: float,
        *,
        y_offset: float,
        eastern_road: bool,
        southern_road: bool,
        northern_road: bool = True,
        houses_across: int = 6,
        houses_deep: int = 2,
    ) -> None:
        """Road loop sized to the lot, lawn, and a centred grid of brown houses."""
        road_width = self.plan.road_width
        road_thickness = 0.1
        road_z = -block_size[2] / 2 + road_thickness / 2
        # Same south face as an empty city-block ring at this y_offset.
        south = -1.0 + y_offset - block_size[1] / 2
        north = south + lot_depth
        west = west_face
        east = west_face + lot_width
        mid_x = (west + east) / 2
        mid_y = (south + north) / 2
        if southern_road:
            self._add_road(
                mid_x, south - road_width / 2, road_z, east - west, along_x=True,
                sidewalk_inner=1.0,
            )
        if northern_road:
            self._add_road(
                mid_x, north + road_width / 2, road_z, east - west, along_x=True,
                sidewalk_inner=-1.0,
            )
        self._add_road(
            west - road_width / 2, mid_y, road_z, north - south, along_x=False,
            sidewalk_inner=1.0,
        )
        if eastern_road:
            self._add_road(
                east + road_width / 2, mid_y, road_z, north - south, along_x=False,
                sidewalk_inner=-1.0,
            )
        x_edges = ((west, -1.0), (east, 1.0)) if eastern_road else ((west, -1.0),)
        y_edges: list[tuple[float, float]] = []
        if southern_road:
            y_edges.append((south, -1.0))
        if northern_road:
            y_edges.append((north, 1.0))
        walk_w = 0.95
        for x_edge, x_sign in x_edges:
            for y_edge, y_sign in y_edges:
                self._add_block(
                    x_edge + x_sign * road_width / 2,
                    y_edge + y_sign * road_width / 2,
                    road_z,
                    (road_width, road_width, road_thickness),
                    road_material(),
                )
                road_top = road_z + road_thickness / 2
                cx = x_edge + x_sign * road_width / 2
                cy = y_edge + y_sign * road_width / 2
                self._add_block(
                    cx - x_sign * (road_width / 2 - walk_w / 2),
                    cy - y_sign * (road_width / 2 - walk_w / 2),
                    road_top + 0.04,
                    (walk_w, walk_w, 0.08),
                    sidewalk_material(),
                )
        # Yard sits a touch above the asphalt so grass meets the sidewalk lip.
        self._add_block(
            mid_x,
            mid_y,
            road_z + 0.04,
            (lot_width, lot_depth, road_thickness),
            lawn_material(),
        )
        house_pitch = 5.0
        for crow in range(houses_deep):
            for ccol in range(houses_across):
                shade = 0.62 + 0.08 * ((crow * 3 + ccol * 5) % 5)
                hx = mid_x + (ccol - (houses_across - 1) / 2) * house_pitch
                hy = mid_y + (crow - (houses_deep - 1) / 2) * house_pitch
                self._add_house(
                    hx,
                    hy,
                    brick=shade,
                    chimney=(crow + ccol) % 3 != 0,
                )
                # Yard tree beside every other house — softens the grid.
                if (crow + ccol) % 2 == 0:
                    tree = tree_template().copyTo(self.city)
                    tree.setPos(hx + 1.6, hy + 1.1, road_z + 0.05)
                    tree.setH((crow * 37 + ccol * 19) % 360)
                    tree.setScale(0.85 + 0.12 * ((crow + ccol) % 3))
        # Street lamps along the lot edges, spaced to avoid a forest of poles.
        lamp_z = road_z + 0.05
        if southern_road:
            for t in (0.25, 0.75):
                lamp = lamp_template().copyTo(self.city)
                lamp.setPos(west + (east - west) * t, south - 0.35, lamp_z)
                lamp.setH(90.0)
        if northern_road:
            for t in (0.25, 0.75):
                lamp = lamp_template().copyTo(self.city)
                lamp.setPos(west + (east - west) * t, north + 0.35, lamp_z)
                lamp.setH(-90.0)

    def _add_house(
        self,
        x: float,
        y: float,
        *,
        brick: float = 0.7,
        chimney: bool = True,
    ) -> None:
        """Gabled brick house with porch and optional side garage on ``(x, y)``."""
        # Rectangular plan reads less like a toy cube than 2×2×2.
        body = (2.4, 1.85, 1.85)
        sx, sy, sz = body
        brick_mat = brown_material(brick)
        # Concrete foundation lip under the brick mass.
        self._add_block(
            x, y, -sz / 2 + 0.08, (sx + 0.25, sy + 0.25, 0.18), sidewalk_material(),
        )
        self._add_block(x, y, 0.0, body, brick_mat, top=False)
        self._add_house_openings(x, y, 0.0, body)
        # Front porch slab + posts + shed roof.
        porch_y = y - sy / 2 - 0.35
        self._add_block(
            x, porch_y, -sz / 2 + 0.1, (1.5, 0.7, 0.16), sidewalk_material(),
        )
        for side in (-0.55, 0.55):
            self._add_block(
                x + side, porch_y, -0.15, (0.12, 0.12, 1.35), brick_mat,
            )
        porch_roof = self.city.attachNewNode(make_gable_roof(1.7, 0.85, 0.35))
        porch_roof.setPos(x, porch_y, sz / 2 - 0.15)
        porch_roof.setMaterial(roof_material(), 1)
        # Main gable roof with eave overhang.
        roof = self.city.attachNewNode(make_gable_roof(sx + 0.35, sy + 0.45, 1.05))
        roof.setPos(x, y, sz / 2)
        roof.setMaterial(roof_material(), 1)
        if chimney:
            self._add_block(
                x + sx * 0.28,
                y + sy * 0.05,
                sz / 2 + 0.85,
                (0.32, 0.32, 0.95),
                brown_material(brick * 0.85),
            )
        # Occasional one-car garage wing for lot variety.
        if int((x * 3 + y * 5) * 10) % 5 == 0:
            gx = x + sx / 2 + 0.55
            self._add_block(
                gx, y, -0.15, (1.1, 1.5, 1.4), brick_mat, top=False,
            )
            door = box_instance(self.city, 0.06, 1.1, 1.05)
            door.setPos(gx, y - 0.78, -0.25)
            door.setMaterial(brown_material(0.45), 1)
            garage_roof = self.city.attachNewNode(make_gable_roof(1.3, 1.7, 0.55))
            garage_roof.setPos(gx, y, 0.55)
            garage_roof.setH(90.0)
            garage_roof.setMaterial(roof_material(), 1)

    def _add_house_openings(
        self,
        x: float,
        y: float,
        z: float,
        size: tuple[float, float, float],
    ) -> None:
        """Door on −Y plus framed windows on the other faces."""
        sx, sy, sz = size
        depth = 0.05
        frame = brown_material(0.45)
        # Front door with a simple frame.
        door_h = 1.15
        door = box_instance(self.city, 0.55, depth, door_h)
        door.setPos(x, y - sy / 2 - depth / 2, z - sz / 2 + door_h / 2)
        door.setMaterial(brown_material(), 1)
        frame_door = box_instance(self.city, 0.7, depth * 0.6, door_h + 0.12)
        frame_door.setPos(x, y - sy / 2 - depth * 0.2, z - sz / 2 + door_h / 2)
        frame_door.setMaterial(frame, 1)

        windows = (
            (x + sx / 2 + depth / 2, y - 0.25, depth, 0.55, 0),
            (x + sx / 2 + depth / 2, y + 0.35, depth, 0.55, 1),
            (x - sx / 2 - depth / 2, y - 0.25, depth, 0.55, 2),
            (x - sx / 2 - depth / 2, y + 0.35, depth, 0.55, 3),
            (x, y + sy / 2 + depth / 2, 0.7, depth, 4),
        )
        win_h = 0.7
        for px, py, panel_x, panel_y, level in windows:
            # Frame is a slightly larger slab behind/around the glass.
            if panel_x <= panel_y:
                trim = box_instance(self.city, panel_x + 0.04, panel_y + 0.1, win_h + 0.1)
            else:
                trim = box_instance(self.city, panel_x + 0.1, panel_y + 0.04, win_h + 0.1)
            trim.setPos(px, py, z + 0.12)
            trim.setMaterial(frame, 1)
            pane = box_instance(self.city, panel_x, panel_y, win_h)
            pane.setPos(px, py, z + 0.12)
            pane.setMaterial(square_material(square_lightness(level)), 1)

    def _add_crosswalk(
        self,
        x: float,
        y: float,
        road_top: float,
        *,
        along_x: bool,
        span: float | None = None,
    ) -> None:
        """Zebra stripes across one approach, just outside the intersection."""
        road_w = self.plan.road_width
        span = road_w * 0.85 if span is None else span
        stripe_w = 0.5
        stripe_len = 1.6
        gap = 0.45
        paint = mark_material()
        # Four stripes reads as a crosswalk without packing the flatten budget.
        count = 4
        total = count * stripe_w + (count - 1) * gap
        z = road_top + 0.03
        for index in range(count):
            offset = -total / 2 + stripe_w / 2 + index * (stripe_w + gap)
            if along_x:
                # Stripes run along Y (across an EW road).
                mark = box_instance(self.city, stripe_w, stripe_len, 0.04)
                mark.setPos(x + offset, y, z)
            else:
                mark = box_instance(self.city, stripe_len, stripe_w, 0.04)
                mark.setPos(x, y + offset, z)
            mark.setMaterial(paint, 1)

    def _add_lights(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.setColor((0.34, 0.37, 0.42, 1))
        ambient_np = self.render.attachNewNode(ambient)
        self.render.setLight(ambient_np)

        # Warm late-morning key — no shadow map / shader-auto (those crushed FPS).
        sun = DirectionalLight("sun")
        sun.setColor((1.15, 1.05, 0.9, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(38, -48, 0)
        self.render.setLight(sun_np)

        # Soft bounce from the opposite sky so towers don't go pure black.
        fill = DirectionalLight("fill")
        fill.setColor((0.18, 0.22, 0.3, 1))
        fill_np = self.render.attachNewNode(fill)
        fill_np.setHpr(220, -25, 0)
        self.render.setLight(fill_np)

        # Gradient sky; depth-write off so it never fights the city.
        sky = self.render.attachNewNode(make_sky_dome(rings=4, sectors=12))
        sky.setBin("background", 0)
        sky.setDepthWrite(False)
        sky.setLightOff()
        sky.setShaderOff()
        sky.setAttrib(ColorAttrib.makeVertex())
        bounds = self.plan.framing_bounds()
        sky.setPos(
            (bounds["left"] + bounds["right"]) / 2,
            (bounds["city_south"] + bounds["city_north"]) / 2,
            0.0,
        )
        # Fixed-function lighting: same materials, far cheaper than setShaderAuto.
