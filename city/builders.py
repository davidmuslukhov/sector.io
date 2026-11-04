"""Scene builders: lots, roads, signals, houses, lights."""

from __future__ import annotations

import math

from panda3d.core import (
    AmbientLight,
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
    plinth_material,
    road_material,
    roof_material,
    signal_lens_material,
    signal_material,
    square_lightness,
    square_material,
    stack_material,
)
from city.mesh import (
    box_instance,
    factory_template,
    make_cylinder,
    make_pyramid,
    make_sphere,
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
            self._add_road(mid_x, south - road_width / 2, road_z, east - west, along_x=True)
        self._add_road(mid_x, north + road_width / 2, road_z, east - west, along_x=True)
        self._add_road(west - road_width / 2, mid_y, road_z, north - south, along_x=False)
        if eastern_road:
            self._add_road(east + road_width / 2, mid_y, road_z, north - south, along_x=False)
        # The straight sections stop at the building faces. Each corner square
        # joins the two roads that meet there, so a side with no road has no corners.
        x_edges = ((west, -1.0), (east, 1.0)) if eastern_road else ((west, -1.0),)
        y_edges = ((south, -1.0), (north, 1.0)) if southern_road else ((north, 1.0),)
        for x_edge, x_sign in x_edges:
            for y_edge, y_sign in y_edges:
                self._add_block(
                    x_edge + x_sign * road_width / 2,
                    y_edge + y_sign * road_width / 2,
                    road_z,
                    (road_width, road_width, road_size[2]),
                    road_material(),
                )

    def _add_sphere(self, x: float, y: float, material: Material) -> None:
        sphere = self.city.attachNewNode(make_sphere())
        sphere.setPos(x, y, 0)
        sphere.setMaterial(material, 1)

    def _add_link(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        material: Material,
        radius: float = 0.08,
    ) -> None:
        """Cylinder from one sphere centre to the next, meeting each at its middle."""
        length = math.hypot(x1 - x0, y1 - y0)
        link = self.city.attachNewNode(make_cylinder(radius, length))
        link.setPos(x0, y0, 0)
        link.lookAt(x1, y1, 0)
        link.setMaterial(material, 1)

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
        """Stack ``floors`` blocks. Each floor gets one row of windows on every face.

        Adds a stone plinth, dark roof cap, and a couple of rooftop units so the
        silhouette reads more like a real tower without per-window extras.
        """
        parent = None
        if heading:
            parent = self.city.attachNewNode("tower")
            parent.setPos(x, y, 0)
            parent.setH(heading)
            x, y = 0.0, 0.0
        sx, sy, sz = size
        # Slightly proud base so the ground floor meets the sidewalk.
        plinth_h = 0.28
        self._add_block(
            x,
            y,
            -sz / 2 + plinth_h / 2,
            (sx + 0.35, sy + 0.35, plinth_h),
            plinth_material(),
            parent=parent,
        )
        for floor in range(floors):
            floor_z = floor * sz
            self._add_block(
                x,
                y,
                floor_z,
                size,
                material,
                top=False,
                bottom=floor == 0,
                parent=parent,
            )
            self._add_face_squares(x, y, floor_z, size, floor * 12, parent=parent, doors=doors)

        top_z = (floors - 1) * sz + sz / 2
        # Slight cornice overhang, then a dark roof deck inset inside it.
        self._add_block(
            x,
            y,
            top_z + 0.05,
            (sx + 0.18, sy + 0.18, 0.12),
            block_material(0.82),
            parent=parent,
        )
        self._add_block(
            x,
            y,
            top_z + 0.14,
            (sx - 0.08, sy - 0.08, 0.1),
            roof_material(),
            parent=parent,
        )
        if floors >= 12:
            unit = stack_material()
            self._add_block(
                x - sx * 0.22,
                y + sy * 0.18,
                top_z + 0.5,
                (0.7, 0.55, 0.7),
                unit,
                parent=parent,
            )
            self._add_block(
                x + sx * 0.2,
                y - sy * 0.15,
                top_z + 0.42,
                (0.55, 0.55, 0.5),
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
    ) -> None:
        """Grey slab with center dashes. ``along_x`` runs the length east-west."""
        width = self.plan.road_width
        thickness = 0.1
        size = (length, width, thickness) if along_x else (width, length, thickness)
        self._add_block(x, y, z, size, road_material(), parent=parent)
        self._add_road_marks(
            x, y, z + thickness / 2, length, along_x, parent=parent
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
            self._add_road(mid_x, south - road_width / 2, road_z, east - west, along_x=True)
        self._add_road(mid_x, north + road_width / 2, road_z, east - west, along_x=True)
        self._add_road(west - road_width / 2, mid_y, road_z, north - south, along_x=False)
        if eastern_road:
            self._add_road(east + road_width / 2, mid_y, road_z, north - south, along_x=False)
        x_edges = ((west, -1.0), (east, 1.0)) if eastern_road else ((west, -1.0),)
        y_edges = ((south, -1.0), (north, 1.0)) if southern_road else ((north, 1.0),)
        for x_edge, x_sign in x_edges:
            for y_edge, y_sign in y_edges:
                self._add_block(
                    x_edge + x_sign * road_width / 2,
                    y_edge + y_sign * road_width / 2,
                    road_z,
                    (road_width, road_width, road_thickness),
                    road_material(),
                )
        self._add_block(
            mid_x,
            mid_y,
            road_z,
            (lot_width, lot_depth, road_thickness),
            lawn_material(),
        )
        house_pitch = 5.0
        for crow in range(houses_deep):
            for ccol in range(houses_across):
                self._add_house(
                    mid_x + (ccol - (houses_across - 1) / 2) * house_pitch,
                    mid_y + (crow - (houses_deep - 1) / 2) * house_pitch,
                )

    def _add_house(self, x: float, y: float) -> None:
        """Brown 2x2 cube capped by a 3x3 slate pyramid, centred on ``(x, y)``."""
        cube_size = (2.0, 2.0, 2.0)
        pyramid_size = (3.0, 3.0, 1.5)
        self._add_block(x, y, 0.0, cube_size, brown_material(0.7), top=False)
        self._add_cube_squares(x, y, 0.0, cube_size)
        pyramid = self.city.attachNewNode(make_pyramid(*pyramid_size))
        pyramid.setPos(x, y, cube_size[2] / 2)
        pyramid.setMaterial(roof_material(), 1)

    def _add_cube_squares(
        self,
        x: float,
        y: float,
        z: float,
        size: tuple[float, float, float],
    ) -> None:
        """One centered glass pane on each vertical face except the front (−Y)."""
        sx, sy, sz = size
        win_w = 0.7
        win_h = 0.85
        depth = 0.04
        # Right, left, then back. The front face, toward the camera, has no square.
        faces = (
            (x + sx / 2 + depth / 2, y, z + 0.1, depth, win_w, 0),
            (x - sx / 2 - depth / 2, y, z + 0.1, depth, win_w, 1),
            (x, y + sy / 2 + depth / 2, z + 0.1, win_w, depth, 2),
        )
        for px, py, pz, panel_x, panel_y, level in faces:
            panel = box_instance(self.city, panel_x, panel_y, win_h)
            panel.setPos(px, py, pz)
            panel.setMaterial(square_material(square_lightness(level)), 1)

        # Lighter than the cube so the rectangle reads on the bare front face.
        rectangle_height = 0.75
        rectangle_bottom = z - sz / 2
        rectangle = box_instance(self.city, 0.5, depth, rectangle_height)
        rectangle.setPos(x, y - sy / 2 - depth / 2, rectangle_bottom + rectangle_height / 2)
        rectangle.setMaterial(brown_material(), 1)

    def _add_lights(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.setColor((0.35, 0.38, 0.42, 1))
        ambient_np = self.render.attachNewNode(ambient)
        self.render.setLight(ambient_np)

        sun = DirectionalLight("sun")
        sun.setColor((1.05, 0.98, 0.88, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(40, -50, 0)
        self.render.setLight(sun_np)
        self.render.setShaderAuto()
