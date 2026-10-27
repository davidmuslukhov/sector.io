"""Software-city scene. Three identical lit spheres form an equilateral triangle,
joined center to center by thin cylinders. Sixteen rings, each two towers deep
and five wide, form a square with four on each side. Each ring has stacks of
unique random heights, from ten to twenty-five floors, each a slightly different
shade of the same grey, one unit apart, with one row of yellow squares on each
floor and yellow dashes along the road. Each stack has a brown door on every face
that meets a road, so a corner stack has two. A block leaves out the road on any
side that faces another block, so neighbours share one road: eastern towers meet
the western edge of the road to their east, and southern towers meet the northern
edge of the road to their south. The sphere group and a brown cube capped by a
pyramid stand 30 units to the right of the road."""

import argparse
import math
import random
import sys

from panda3d.core import loadPrcFileData


def _configure() -> argparse.Namespace:
    """Apply window settings before Panda3D reads its config on import."""
    parser = argparse.ArgumentParser(description="Open the software-city scene.")
    parser.add_argument(
        "--screenshot",
        metavar="PATH",
        help="Render one offscreen frame to this image and exit.",
    )
    args = parser.parse_args()
    # The conda package keeps Config.prc under Library/etc, which Panda
    # does not find on its own when python.exe is launched directly.
    loadPrcFileData("", "load-display pandagl")
    loadPrcFileData("", "aux-display p3tinydisplay")
    if args.screenshot:
        loadPrcFileData("", "window-type offscreen")
        loadPrcFileData("", "audio-library-name null")
    loadPrcFileData("", "win-size 960 960")
    return args


_ARGS = _configure()

from panda3d.core import (  # noqa: E402
    AmbientLight,
    DirectionalLight,
    Filename,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    Material,
    NodePath,
    TextNode,
)
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402


def make_sphere(radius: float = 1.0, rings: int = 32, segments: int = 48) -> GeomNode:
    """UV sphere. Normals point outward so a single light shades the surface."""
    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("sphere", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")

    for ring in range(rings + 1):
        phi = math.pi * ring / rings
        sin_phi = math.sin(phi)
        cos_phi = math.cos(phi)
        for seg in range(segments + 1):
            theta = 2.0 * math.pi * seg / segments
            x = sin_phi * math.cos(theta)
            y = sin_phi * math.sin(theta)
            z = cos_phi
            vertex.addData3(radius * x, radius * y, radius * z)
            normal.addData3(x, y, z)

    tris = GeomTriangles(Geom.UHStatic)
    stride = segments + 1
    for ring in range(rings):
        for seg in range(segments):
            i0 = ring * stride + seg
            i1 = i0 + 1
            i2 = i0 + stride
            i3 = i2 + 1
            tris.addVertices(i0, i2, i1)
            tris.addVertices(i1, i2, i3)
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("sphere")
    node.addGeom(geom)
    return node


def make_cylinder(radius: float, length: float, segments: int = 24) -> GeomNode:
    """Open cylinder along +Y, from the origin out to ``length``."""
    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("cylinder", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")

    for y in (0.0, length):
        for seg in range(segments + 1):
            theta = 2.0 * math.pi * seg / segments
            nx = math.cos(theta)
            nz = math.sin(theta)
            vertex.addData3(radius * nx, y, radius * nz)
            normal.addData3(nx, 0.0, nz)

    tris = GeomTriangles(Geom.UHStatic)
    stride = segments + 1
    for seg in range(segments):
        i0 = seg
        i1 = i0 + 1
        i2 = i0 + stride
        i3 = i2 + 1
        tris.addVertices(i0, i2, i1)
        tris.addVertices(i1, i2, i3)
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("cylinder")
    node.addGeom(geom)
    return node


def make_box(
    sx: float,
    sy: float,
    sz: float,
    top: bool = True,
    bottom: bool = True,
) -> GeomNode:
    """Closed box centred on the origin, with a flat outward normal on each face."""
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    # Four corners per face, wound counter-clockwise when seen from outside.
    faces = [
        ((hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz), (1.0, 0.0, 0.0)),
        ((-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz), (-1.0, 0.0, 0.0)),
        ((hx, hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz), (0.0, 1.0, 0.0)),
        ((-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz), (0.0, -1.0, 0.0)),
    ]
    if top:
        faces.append(
            ((-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz), (0.0, 0.0, 1.0))
        )
    if bottom:
        faces.append(
            ((-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz), (-hx, -hy, -hz), (0.0, 0.0, -1.0))
        )

    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("box", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    for corners in faces:
        nx, ny, nz = corners[4]
        base = vertex.getWriteRow()
        for corner in corners[:4]:
            vertex.addData3(*corner)
            normal.addData3(nx, ny, nz)
        tris.addVertices(base, base + 1, base + 2)
        tris.addVertices(base, base + 2, base + 3)
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("box")
    node.addGeom(geom)
    return node


# Shared box Geoms. Keyed by size and which caps are present.
_BOX_TEMPLATES: dict[tuple[float, float, float, bool, bool], NodePath] = {}


def _box_instance(
    parent: NodePath,
    sx: float,
    sy: float,
    sz: float,
    top: bool = True,
    bottom: bool = True,
) -> NodePath:
    """Copy a cached box Geom into ``parent`` instead of rebuilding vertices."""
    key = (sx, sy, sz, top, bottom)
    template = _BOX_TEMPLATES.get(key)
    if template is None:
        template = NodePath(make_box(sx, sy, sz, top=top, bottom=bottom))
        _BOX_TEMPLATES[key] = template
    return template.copyTo(parent)


def make_pyramid(sx: float, sy: float, height: float) -> GeomNode:
    """Square pyramid. The base sits on z = 0, centred on the origin, with the apex above it."""
    hx, hy = sx / 2.0, sy / 2.0
    apex = (0.0, 0.0, height)
    # Same corner order as make_box: front-left, front-right, back-right, back-left.
    base = (
        (-hx, -hy, 0.0),
        (hx, -hy, 0.0),
        (hx, hy, 0.0),
        (-hx, hy, 0.0),
    )
    # Triangles wound counter-clockwise when seen from outside.
    sides = (
        (base[1], base[2], apex),
        (base[0], apex, base[3]),
        (base[2], base[3], apex),
        (base[0], base[1], apex),
    )

    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("pyramid", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    def add_face(corners: tuple[tuple[float, float, float], ...], face_normal: tuple[float, float, float]) -> None:
        start = vertex.getWriteRow()
        for corner in corners:
            vertex.addData3(*corner)
            normal.addData3(*face_normal)
        tris.addVertices(start, start + 1, start + 2)
        if len(corners) == 4:
            tris.addVertices(start, start + 2, start + 3)

    for corners in sides:
        add_face(corners, _face_normal(*corners))
    add_face((base[3], base[2], base[1], base[0]), (0.0, 0.0, -1.0))
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("pyramid")
    node.addGeom(geom)
    return node


def _face_normal(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Unit normal of a counter-clockwise triangle."""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.hypot(nx, ny, nz)
    return (nx / length, ny / length, nz / length)


_SPHERE_MATERIAL: Material | None = None
_BLOCK_MATERIALS: dict[float, Material] = {}
_ROAD_MATERIAL: Material | None = None
_SQUARE_MATERIALS: dict[float, Material] = {}
_BROWN_MATERIALS: dict[float, Material] = {}


def sphere_material() -> Material:
    global _SPHERE_MATERIAL
    if _SPHERE_MATERIAL is None:
        material = Material()
        material.setAmbient((0.15, 0.28, 0.4, 1))
        material.setDiffuse((0.25, 0.55, 0.85, 1))
        material.setSpecular((0.45, 0.45, 0.5, 1))
        material.setShininess(32)
        _SPHERE_MATERIAL = material
    return _SPHERE_MATERIAL


# One cool grey. ``1`` is the original tower; the band is wide enough to tell
# neighbours apart and narrow enough that they stay the same colour.
_BLOCK_SHADES = (
    0.860, 1.009, 0.916, 1.084, 0.972, 1.140, 0.897, 1.047,
    0.953, 1.103, 0.879, 1.028, 0.935, 1.121, 0.991, 1.065,
)


def block_material(lightness: float = 1.0) -> Material:
    """Cool grey. Nearby ``lightness`` values stay the same colour at a different shade."""
    cached = _BLOCK_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    ambient = tuple(channel * lightness for channel in (0.45, 0.45, 0.47))
    diffuse = tuple(channel * lightness for channel in (0.78, 0.78, 0.80))
    specular = tuple(channel * lightness for channel in (0.55, 0.55, 0.55))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(32)
    _BLOCK_MATERIALS[lightness] = material
    return material


def road_material() -> Material:
    """Darker grey than the tower so the slab reads as a road."""
    global _ROAD_MATERIAL
    if _ROAD_MATERIAL is None:
        material = Material()
        material.setAmbient((0.22, 0.22, 0.23, 1))
        material.setDiffuse((0.42, 0.42, 0.43, 1))
        material.setSpecular((0.12, 0.12, 0.12, 1))
        material.setShininess(4)
        _ROAD_MATERIAL = material
    return _ROAD_MATERIAL


# One yellow hue. Brightness scales this colour, so every square stays the same shade.
_YELLOW = (1.0, 0.82 / 0.95, 0.12 / 0.95)
_YELLOW_LEVELS = (0.50, 0.62, 0.74, 0.86, 1.0)


def square_material(lightness: float) -> Material:
    """Yellow of a single hue. ``lightness`` 0.95 matches the original square."""
    cached = _SQUARE_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    diffuse = tuple(channel * lightness for channel in _YELLOW)
    ambient = tuple(channel * 0.47 for channel in diffuse)
    specular = tuple(channel * 0.45 for channel in diffuse)
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(24)
    _SQUARE_MATERIALS[lightness] = material
    return material


def _square_lightness(index: int) -> float:
    return _YELLOW_LEVELS[(index * 3) % len(_YELLOW_LEVELS)]


def brown_material(lightness: float = 1.0) -> Material:
    """Same brown hue. ``lightness`` 1 matches the door; lower values are darker."""
    cached = _BROWN_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    ambient = tuple(channel * lightness for channel in (0.28, 0.16, 0.07))
    diffuse = tuple(channel * lightness for channel in (0.50, 0.30, 0.13))
    specular = tuple(channel * lightness for channel in (0.25, 0.18, 0.1))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(16)
    _BROWN_MATERIALS[lightness] = material
    return material


class CityApp(ShowBase):
    def __init__(self, screenshot: str | None = None) -> None:
        super().__init__()
        self.screenshot_path = screenshot
        self.disableMouse()
        self.setBackgroundColor(0.08, 0.09, 0.12, 1)

        self.city = self.render.attachNewNode("city")
        # Equilateral triangle in the XY plane. The tower stays put; the spheres
        # and the house are shifted together once the road's right edge is known.
        side = 2.5
        height = side * math.sqrt(3) / 2
        positions = (
            (-side / 2, -height / 3),
            (side / 2, -height / 3),
            (0.0, 2 * height / 3),
        )
        material = sphere_material()
        sphere_radius = 1.0
        block_size = (5.0, 5.0, 2.0)
        block_gap = 5.0
        # Depth-2 rings: five south, empty west/east, five north (including corners).
        # Every floor is one block and one window row. Heights are unique within
        # each ring; only sixteen values exist between 10 and 25 inclusive.
        floor_min, floor_max = 10, 25
        tallest = floor_max
        right_surface = side / 2 + sphere_radius
        block_center_x = right_surface + block_gap + block_size[0] / 2
        # Left edge stays with the first tower. The right edge meets the last tower.
        tower_count = 5
        tower_gap = 1.0
        road_left = block_center_x - 25.0 / 2
        road_right = road_left + tower_count * block_size[0] + (tower_count - 1) * tower_gap
        road_length = road_right - road_left
        road_center_x = (road_left + road_right) / 2
        circle_left = -side / 2 - sphere_radius
        group_shift = road_right + 30.0 - circle_left

        for x, y in positions:
            self._add_sphere(x + group_shift, y, material)
        # Each sphere joins its two neighbours, so the three links close the triangle.
        for index, (x0, y0) in enumerate(positions):
            x1, y1 = positions[(index + 1) % len(positions)]
            self._add_link(x0 + group_shift, y0, x1 + group_shift, y1, material)
        # Four by four of 2x5 rings. Columns west of the east edge leave out
        # their eastern road and rows north of the south edge leave out their
        # southern road, so neighbours share the road already drawn by the
        # block to the east or the south. The eastern column stays on road_left.
        road_width = 5.0
        road_depth = 2 * block_size[1] + tower_gap
        stride_x = road_width + road_length
        stride_y = road_width + road_depth
        grid = 4
        towers_per_ring = 10
        for row in range(grid):
            for col in range(grid):
                heights = random.sample(range(floor_min, floor_max + 1), towers_per_ring)
                block_floors = (tuple(heights[:5]), (), (), tuple(heights[5:]))
                self._add_city_block(
                    road_left - (grid - 1 - col) * stride_x,
                    block_size,
                    block_floors,
                    y_offset=row * stride_y,
                    eastern_road=col == grid - 1,
                    southern_road=row == 0,
                )

        south_face = -(block_size[1] / 2 + 1.0)

        cube_size = (2.0, 2.0, 2.0)
        stack_right = block_center_x + block_size[0] / 2
        cube_center_x = stack_right + 5.0 + cube_size[0] / 2 + group_shift
        self._add_block(cube_center_x, 0.0, 0.0, cube_size, brown_material(0.6), top=False)
        self._add_cube_squares(cube_center_x, 0.0, 0.0, cube_size)
        pyramid_size = (3.0, 3.0, 1.5)
        pyramid = self.city.attachNewNode(make_pyramid(*pyramid_size))
        pyramid.setPos(cube_center_x, 0.0, cube_size[2] / 2)
        pyramid.setMaterial(brown_material(0.6), 1)
        self._add_lights()
        # Merge thousands of tiny boxes into few Geoms so orbit stays smooth.
        self.city.flattenStrong()

        # Outer edges of the 4x4: southern road of the south row, northern road
        # of the north row, and the western road of the west column.
        city_north = south_face + grid * road_depth + grid * road_width
        city_south = south_face - road_width
        left = min(
            road_left - (grid - 1) * stride_x - road_width,
            circle_left + group_shift,
        )
        right = cube_center_x + pyramid_size[0] / 2
        stack_bottom = -block_size[2] / 2
        stack_top = (tallest - 1) * block_size[2] + block_size[2] / 2
        self.look_at = (
            (left + right) / 2,
            (city_south + city_north) / 2,
            (stack_bottom + stack_top) / 2,
        )
        self.heading = 30.0
        self.pitch = 20.0
        # Square window, 40 degree FOV. Pull back so the widened scene still fits.
        half_fov = math.tan(math.radians(20.0))
        fit_x = ((right - left) / 2) / half_fov / math.cos(math.radians(self.heading))
        fit_y = ((city_north - city_south) / 2) / half_fov / math.cos(math.radians(self.pitch))
        self.distance = max(fit_x, fit_y) * 1.25
        self.dragging = False
        self.last_x = 0.0
        self.last_y = 0.0
        self._update_camera()

        self.accept("escape", sys.exit)
        self.accept("wheel_up", self._zoom, [-0.4])
        self.accept("wheel_down", self._zoom, [0.4])
        self.accept("mouse1", self._start_drag)
        self.accept("mouse1-up", self._end_drag)
        self.taskMgr.add(self._drag_task, "orbit-drag")
        if not self.screenshot_path:
            self.fps_text = OnscreenText(
                text="",
                parent=self.a2dTopRight,
                pos=(-0.04, -0.08),
                scale=0.09,
                fg=(1, 1, 1, 1),
                align=TextNode.ARight,
                mayChange=True,
            )
            self.taskMgr.add(self._fps_task, "fps-counter")

    def _fps_task(self, task):
        self.fps_text.setText(f"FPS: {self.clock.getAverageFrameRate():.0f}")
        return task.cont

    def _add_city_block(
        self,
        west_face: float,
        block_size: tuple[float, float, float],
        floors: tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]],
        *,
        y_offset: float = 0.0,
        eastern_road: bool,
        southern_road: bool,
    ) -> None:
        """One ring of towers with a road along each outer face.

        ``west_face`` is the western face of the western towers. ``y_offset``
        shifts the whole ring north. A road that faces another block is left
        out, along with its corner squares, so the rings share one road.
        """
        south_floors, west_floors, east_floors, north_floors = floors
        tower_gap = 1.0
        tower_count = len(south_floors)
        road_length = tower_count * block_size[0] + (tower_count - 1) * tower_gap
        # East-west slab. Each tower's front face meets the near edge, and the slab
        # runs from the first tower's left edge to the last tower's right edge.
        road_size = (road_length, 5.0, 0.1)
        road_y = -(block_size[1] / 2 + 1.0 + road_size[1] / 2)
        road_z = -block_size[2] / 2 + road_size[2] / 2
        tower_y = road_y + road_size[1] / 2 + block_size[1] / 2 + y_offset

        shades = iter(_BLOCK_SHADES)
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
        spacing_y = block_size[1] + tower_gap
        if west_floors:
            north_step = len(west_floors)
        elif north_floors:
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
        """Stack ``floors`` blocks. Each floor gets one row of windows on every face."""
        parent = None
        if heading:
            parent = self.city.attachNewNode("tower")
            parent.setPos(x, y, 0)
            parent.setH(heading)
            x, y = 0.0, 0.0
        for floor in range(floors):
            floor_z = floor * size[2]
            self._add_block(
                x,
                y,
                floor_z,
                size,
                material,
                top=floor == floors - 1,
                bottom=floor == 0,
                parent=parent,
            )
            self._add_face_squares(x, y, floor_z, size, floor * 12, parent=parent, doors=doors)

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
        block = _box_instance(root, *size, top=top, bottom=bottom)
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
        """Three 1×1 squares on every vertical face, inset 0.5 from the edges.

        ``doors`` names ground-floor faces that meet a road ("-y", "+y", "-x", "+x").
        The centre window on each of those faces is a door instead.
        """
        root = self.city if parent is None else parent
        sx, sy, sz = size
        square = 1.0
        margin = 0.5
        depth = 0.04
        row_z = z - sz / 2 + margin + square / 2
        level = level_start
        door_faces = set(doors)

        def centers(span: float) -> tuple[float, float, float]:
            left = -span / 2 + margin + square / 2
            right = span / 2 - margin - square / 2
            return (left, (left + right) / 2, right)

        def add_door(px: float, py: float, width_along_x: bool) -> None:
            door_width = 1.0
            door_height = 1.25
            door_bottom = z - sz / 2
            if width_along_x:
                panel = _box_instance(root, door_width, depth, door_height)
            else:
                panel = _box_instance(root, depth, door_width, door_height)
            panel.setPos(px, py, door_bottom + door_height / 2)
            panel.setMaterial(brown_material(), 1)

        along_x = centers(sx)
        along_y = centers(sy)
        for sign in (1.0, -1.0):
            face = "+y" if sign > 0 else "-y"
            face_y = y + sign * (sy / 2 + depth / 2)
            for offset in along_x:
                tone = _square_lightness(level)
                level += 1
                if z == 0 and offset == 0 and face in door_faces:
                    add_door(x + offset, face_y, width_along_x=True)
                    continue
                panel = _box_instance(root, square, depth, square)
                panel.setPos(x + offset, face_y, row_z)
                panel.setMaterial(square_material(tone), 1)
            face = "+x" if sign > 0 else "-x"
            face_x = x + sign * (sx / 2 + depth / 2)
            for offset in along_y:
                tone = _square_lightness(level)
                level += 1
                if z == 0 and offset == 0 and face in door_faces:
                    add_door(face_x, y + offset, width_along_x=False)
                    continue
                panel = _box_instance(root, depth, square, square)
                panel.setPos(face_x, y + offset, row_z)
                panel.setMaterial(square_material(tone), 1)

    def _add_road(self, x: float, y: float, z: float, length: float, along_x: bool) -> None:
        """Grey slab with center dashes. ``along_x`` runs the length east-west."""
        width = 5.0
        thickness = 0.1
        size = (length, width, thickness) if along_x else (width, length, thickness)
        self._add_block(x, y, z, size, road_material())
        self._add_road_marks(x, y, z + thickness / 2, length, along_x)

    def _add_road_marks(
        self,
        x: float,
        y: float,
        road_top: float,
        road_length: float,
        along_x: bool = True,
    ) -> None:
        """Yellow dashes on the road centerline, one unit apart edge to edge."""
        length = 2.0
        width = 0.5
        gap = 1.0
        thickness = 0.04
        # As many 2-unit dashes as fit with a 1-unit gap, centered on the road.
        count = int((road_length + gap) / (length + gap))
        span = count * length + (count - 1) * gap
        z = road_top + thickness / 2
        yellow = square_material(1.0)
        for index in range(count):
            offset = -span / 2 + length / 2 + index * (length + gap)
            if along_x:
                mark = _box_instance(self.city, length, width, thickness)
                mark.setPos(x + offset, y, z)
            else:
                mark = _box_instance(self.city, width, length, thickness)
                mark.setPos(x, y + offset, z)
            mark.setMaterial(yellow, 1)

    def _add_cube_squares(
        self,
        x: float,
        y: float,
        z: float,
        size: tuple[float, float, float],
    ) -> None:
        """One centered 0.75×0.75 square on each vertical face except the front (−Y)."""
        sx, sy, sz = size
        square = 0.75
        depth = 0.04
        # Right, left, then back. The front face, toward the camera, has no square.
        faces = (
            (x + sx / 2 + depth / 2, y, z, depth, square, 0),
            (x - sx / 2 - depth / 2, y, z, depth, square, 1),
            (x, y + sy / 2 + depth / 2, z, square, depth, 2),
        )
        for px, py, pz, panel_x, panel_y, level in faces:
            panel = _box_instance(self.city, panel_x, panel_y, square)
            panel.setPos(px, py, pz)
            panel.setMaterial(square_material(_square_lightness(level)), 1)

        # Lighter than the cube so the rectangle reads on the bare front face.
        rectangle_height = 0.75
        rectangle_bottom = z - sz / 2
        rectangle = _box_instance(self.city, 0.5, depth, rectangle_height)
        rectangle.setPos(x, y - sy / 2 - depth / 2, rectangle_bottom + rectangle_height / 2)
        rectangle.setMaterial(brown_material(), 1)

    def _add_lights(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.setColor((0.35, 0.38, 0.42, 1))
        ambient_np = self.render.attachNewNode(ambient)
        self.render.setLight(ambient_np)

        sun = DirectionalLight("sun")
        sun.setColor((0.95, 0.93, 0.88, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(35, -45, 0)
        self.render.setLight(sun_np)
        self.render.setShaderAuto()

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

    def _zoom(self, delta: float) -> None:
        self.distance = min(80.0, max(2.0, self.distance + delta))
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


def main() -> None:
    app = CityApp(screenshot=_ARGS.screenshot)
    if _ARGS.screenshot:
        app.capture()
    else:
        app.run()


if __name__ == "__main__":
    main()
