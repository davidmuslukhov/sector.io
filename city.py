"""Software-city scene. Three identical lit spheres form an equilateral triangle,
joined center to center by thin cylinders. Sixteen rings, each two towers deep
and five wide, form a square with four on each side. Twelve housing blocks in a
six-by-two grid sit north of the tower city, west-aligned with it, and sixteen
more in a two-by-eight grid sit west of the towers, spanning the southern
factories through the northern housing; each lot shares roads with neighbours
and holds a six-by-two grid of brown houses (2x2 cube under a 3x3 pyramid), two
units between roofs, with a green slab as thick as the road filling the gaps.
Eight empty road loops with the same 29-by-11 inner footprint form a two-by-four
grid south of the tower city, and twelve more form a two-by-six grid east of the
tower city and its southern factories; each shares roads with its neighbours and
holds a grey factory building 29 by 11 by 9 with three 2-by-2-by-6 stacks on the
roof.
Each ring has stacks of unique random heights, from ten to twenty-five floors,
each a slightly different shade of the same grey, one unit apart with the gaps
paved in a thin road-coloured layer, with one row of yellow squares on each
floor and yellow dashes along the road. Each stack has a brown door on every
face that meets a road, so a corner stack has two. A block leaves out the road
on any side that faces another block, so neighbours share one road: eastern
towers meet the western edge of the road to their east, and southern towers
meet the northern edge of the road to their south. Blocky traffic lights hang
under thin black rods that span each approach at four-way intersections, eight
units above the road; approaches with no tower or factory wall get matching
vertical rods down to the road. A blue 2x1x1 car drives the road grid: it
cruises, decelerates into each intersection, waits three seconds, then goes
forward, left, or right relative to its front. The sphere group and a brown
cube capped by a pyramid stand 30 units to the right of the road."""

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
# Flattened factory buildings. Keyed by plan, height, and bottom z.
_FACTORY_TEMPLATES: dict[tuple[float, float, float, float], NodePath] = {}


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


def _factory_template(
    sx: float,
    sy: float,
    height: float,
    bottom_z: float,
) -> NodePath:
    """One flattened factory. Origin at plan centre; place with ``setPos(x, y, 0)``."""
    key = (sx, sy, height, bottom_z)
    cached = _FACTORY_TEMPLATES.get(key)
    if cached is not None:
        return cached

    root = NodePath("factory")
    body = _box_instance(root, sx, sy, height)
    body.setPos(0.0, 0.0, bottom_z + height / 2)
    body.setMaterial(block_material(), 1)

    stack_size = (2.0, 2.0, 6.0)
    stack_z = bottom_z + height + stack_size[2] / 2
    for stack_x in (-sx / 4, 0.0, sx / 4):
        stack = _box_instance(root, *stack_size)
        stack.setPos(stack_x, 0.0, stack_z)
        stack.setMaterial(block_material(), 1)

    window = 1.0
    window_depth = 0.04
    side_count = 5
    window_gap = (sy - side_count * window) / (side_count + 1)
    long_count = int((sx - window_gap) / (window + window_gap))
    lower_z = bottom_z + height / 2
    window_zs = (lower_z, lower_z + 2.0)
    level = 0

    def window_offsets(span: float, count: int) -> list[float]:
        return [
            -span / 2
            + window_gap
            + window / 2
            + index * (window + window_gap)
            for index in range(count)
        ]

    for sign in (1.0, -1.0):
        face_x = sign * (sx / 2 + window_depth / 2)
        for window_z in window_zs:
            for offset_y in window_offsets(sy, side_count):
                panel = _box_instance(root, window_depth, window, window)
                panel.setPos(face_x, offset_y, window_z)
                panel.setMaterial(square_material(_square_lightness(level)), 1)
                level += 1
        face_y = sign * (sy / 2 + window_depth / 2)
        for window_z in window_zs:
            for offset_x in window_offsets(sx, long_count):
                panel = _box_instance(root, window, window_depth, window)
                panel.setPos(offset_x, face_y, window_z)
                panel.setMaterial(square_material(_square_lightness(level)), 1)
                level += 1

    root.flattenStrong()
    _FACTORY_TEMPLATES[key] = root
    return root


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
_LAWN_MATERIAL: Material | None = None
_SQUARE_MATERIALS: dict[float, Material] = {}
_BROWN_MATERIALS: dict[float, Material] = {}
_SIGNAL_MATERIALS: dict[str, Material] = {}


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


def lawn_material() -> Material:
    """Flat green for the housing-block pad, same finish weight as the road."""
    global _LAWN_MATERIAL
    if _LAWN_MATERIAL is None:
        material = Material()
        material.setAmbient((0.12, 0.28, 0.12, 1))
        material.setDiffuse((0.28, 0.55, 0.28, 1))
        material.setSpecular((0.08, 0.12, 0.08, 1))
        material.setShininess(4)
        _LAWN_MATERIAL = material
    return _LAWN_MATERIAL


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


def signal_material(name: str) -> Material:
    """Dark housing or a lit lamp colour for the blocky traffic lights."""
    cached = _SIGNAL_MATERIALS.get(name)
    if cached is not None:
        return cached
    colours = {
        "housing": ((0.08, 0.08, 0.09), (0.18, 0.18, 0.20), (0.08, 0.08, 0.08), 8),
        "red": ((0.55, 0.05, 0.05), (0.95, 0.12, 0.10), (0.6, 0.15, 0.1), 32),
        "amber": ((0.55, 0.35, 0.04), (0.95, 0.7, 0.1), (0.55, 0.4, 0.1), 32),
        "green": ((0.04, 0.45, 0.12), (0.1, 0.85, 0.25), (0.15, 0.5, 0.2), 32),
    }
    ambient, diffuse, specular, shininess = colours[name]
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(shininess)
    if name != "housing":
        material.setEmission((*tuple(channel * 0.35 for channel in diffuse), 1))
    _SIGNAL_MATERIALS[name] = material
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
        # Four by four of 2x5 rings. Columns west of the east edge leave out
        # their eastern road and rows north of the south edge leave out their
        # southern road, so neighbours share the road already drawn by the
        # block to the east or the south. The eastern column stays on road_left.
        road_width = 5.0
        road_depth = 2 * block_size[1] + tower_gap
        stride_x = road_width + road_length
        stride_y = road_width + road_depth
        grid = 4
        east_factory_cols = 2
        # Spheres stay 30 units east of the easternmost factory face.
        circle_left = -side / 2 - sphere_radius
        group_shift = road_right + east_factory_cols * stride_x + 30.0 - circle_left

        for x, y in positions:
            self._add_sphere(x + group_shift, y, material)
        # Each sphere joins its two neighbours, so the three links close the triangle.
        for index, (x0, y0) in enumerate(positions):
            x1, y1 = positions[(index + 1) % len(positions)]
            self._add_link(x0 + group_shift, y0, x1 + group_shift, y1, material)
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
                    # East edge omits its eastern road; the factory grid east of
                    # it draws each shared north-south road as a western edge.
                    eastern_road=False,
                    # South edge omits its southern road; the factory grid south
                    # of it draws each shared east-west road as a northern edge.
                    southern_road=False,
                )
        # Twelve housing blocks in a 6x2 north of the towers, west-aligned with
        # the tower city. Each lot shares roads with neighbours; only the east
        # column draws an eastern outer edge. South edges share the tower (or
        # southern housing) northern roads.
        housing_cols, housing_rows = 6, 2
        factory_rows, factory_cols = 2, 4
        lot_width = tower_count * block_size[0] + (tower_count - 1) * tower_gap
        for hrow in range(housing_rows):
            for hcol in range(housing_cols):
                self._add_housing_lot(
                    road_left - (grid - 1) * stride_x + hcol * stride_x,
                    block_size,
                    lot_width,
                    road_depth,
                    y_offset=(grid + hrow) * stride_y,
                    eastern_road=hcol == housing_cols - 1,
                    southern_road=False,
                )
        # Sixteen housing blocks in a 2x8 west of the towers: two columns, eight
        # rows spanning the southern factories, tower city, and northern housing.
        # Eastern roads are omitted so lots share the western roads of the block
        # to their east (neighbour housing, towers, or factories).
        west_housing_cols, west_housing_rows = 2, 8
        tower_west = road_left - (grid - 1) * stride_x
        for wrow in range(west_housing_rows):
            for wcol in range(west_housing_cols):
                self._add_housing_lot(
                    tower_west - (west_housing_cols - wcol) * stride_x,
                    block_size,
                    lot_width,
                    road_depth,
                    y_offset=(wrow - factory_rows) * stride_y,
                    eastern_road=False,
                    southern_road=wrow == 0,
                )
        # Two-by-four empty lots south of the tower city: road loops plus factories.
        for frow in range(factory_rows):
            for fcol in range(factory_cols):
                self._add_city_block(
                    road_left - (factory_cols - 1 - fcol) * stride_x,
                    block_size,
                    ((), (), (), ()),
                    y_offset=-(frow + 1) * stride_y,
                    eastern_road=False,
                    southern_road=frow == factory_rows - 1,
                )
        # Two-by-six empty lots east of the tower city and its southern factories.
        # Six rows span the four tower rows plus the two factory rows to the south.
        east_factory_rows = 6
        for erow in range(east_factory_rows):
            for ecol in range(east_factory_cols):
                self._add_city_block(
                    road_left + (ecol + 1) * stride_x,
                    block_size,
                    ((), (), (), ()),
                    y_offset=(erow - factory_rows) * stride_y,
                    eastern_road=ecol == east_factory_cols - 1,
                    southern_road=erow == 0,
                )

        # Interior east-west roads cross interior north-south roads at true
        # four-ways across the full city (west housing, towers, east factories;
        # south factories through northern housing). Outer edges are T or L
        # junctions and get no lights. One signal per approach, hung under a
        # rod that spans building to building; housing approaches also get
        # vertical rods down to the road.
        road_y0 = -(block_size[1] / 2 + 1.0 + road_width / 2)
        tower_y0 = road_y0 + road_width / 2 + block_size[1] / 2
        south_road0 = tower_y0 - block_size[1] / 2 - road_width / 2
        west_road0 = road_left - (grid - 1) * stride_x - road_width / 2
        # Westernmost / southernmost roads sit outside the west housing and
        # south factory blocks; tower roads are offset from those edges.
        cols = west_housing_cols + grid + east_factory_cols
        rows = factory_rows + grid + housing_rows
        south_road_full0 = south_road0 - factory_rows * stride_y
        west_road_full0 = west_road0 - west_housing_cols * stride_x
        road_top = -block_size[2] / 2 + 0.1
        half = road_width / 2
        housing_south = factory_rows + grid

        def solid_lot(brow: int, bcol: int) -> bool:
            """True when the lot has a tower or factory wall at the road."""
            if bcol < 0 or bcol >= cols or brow < 0 or brow >= rows:
                return False
            if bcol < west_housing_cols:
                return False
            if brow >= housing_south:
                return False
            return True

        for h in range(1, rows):
            iy = south_road_full0 + h * stride_y
            for v in range(1, cols):
                ix = west_road_full0 + v * stride_x
                sw = solid_lot(h - 1, v - 1)
                se = solid_lot(h - 1, v)
                nw = solid_lot(h, v - 1)
                ne = solid_lot(h, v)
                for x0, y0, x1, y1 in (
                    # South, north (span east-west); east, west (span north-south).
                    (ix - half, iy - half, ix + half, iy - half),
                    (ix - half, iy + half, ix + half, iy + half),
                    (ix + half, iy - half, ix + half, iy + half),
                    (ix - half, iy - half, ix - half, iy + half),
                ):
                    self._add_traffic_light(
                        x0,
                        y0,
                        x1,
                        y1,
                        road_top,
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
                        self._add_signal_post(px, py, road_top, block_size)

        south_face = -(block_size[1] / 2 + 1.0)

        cube_size = (2.0, 2.0, 2.0)
        pyramid_size = (3.0, 3.0, 1.5)
        stack_right = block_center_x + block_size[0] / 2
        cube_center_x = stack_right + 5.0 + cube_size[0] / 2 + group_shift
        self._add_house(cube_center_x, 0.0)
        self._add_lights()
        # Merge thousands of tiny boxes into few Geoms so orbit stays smooth.
        self.city.flattenStrong()

        # Car stays outside flattenStrong so it can move each frame.
        self._init_car(
            road_center_x,
            road_y0,
            road_top,
            west_road_full0,
            south_road_full0,
            stride_x,
            stride_y,
            cols,
            rows,
            start_h=factory_rows,
            start_v=west_housing_cols + grid - 1,
        )
        self.taskMgr.add(self._car_task, "car-drive")

        # Outer edges: southern factory/housing road, northern housing road, and
        # the western road of the west housing columns.
        city_north = (
            south_face
            + (grid + housing_rows) * road_depth
            + (grid + housing_rows) * road_width
        )
        city_south = south_face - factory_rows * stride_y - road_width
        left = min(
            tower_west - west_housing_cols * stride_x - road_width,
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
        self.min_distance = 2.0
        # Allow zooming out past the initial framing so the full scene stays reachable.
        self.max_distance = max(80.0, self.distance * 2.0)
        self.dragging = False
        self.last_x = 0.0
        self.last_y = 0.0
        self._update_camera()

        self.accept("escape", sys.exit)
        # Multiplicative zoom: each notch scales distance so zoom-in and zoom-out
        # feel the same at every range (additive steps crawl when zoomed in).
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
        tower_gap = 1.0
        # Empty rings keep the same footprint as a depth-2, five-wide ring.
        tower_count = 5 if empty else len(south_floors)
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
            building = _factory_template(
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

    def _add_signal_post(
        self,
        x: float,
        y: float,
        road_top: float,
        block_size: tuple[float, float, float],
    ) -> None:
        """Vertical rod from the road up to traffic-light height."""
        floor = block_size[2]
        rod_thin = floor * 0.05
        rod_z = road_top + 8.0
        post_h = rod_z - road_top
        post = _box_instance(self.city, rod_thin, rod_thin, post_h)
        post.setPos(x, y, road_top + post_h / 2)
        post.setMaterial(signal_material("housing"), 1)

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
        """Signal hung under a thin rod that spans building to building."""
        floor = block_size[2]
        rod_z = road_top + 8.0
        box_w = floor * 0.4
        box_d = floor * 0.18
        box_h = floor * 1.2
        lamp = floor * 0.28
        lamp_depth = floor * 0.06
        gap = floor * 0.06
        rod_thin = floor * 0.05
        housing = signal_material("housing")

        along_x = abs(x1 - x0) >= abs(y1 - y0)
        rod_len = abs(x1 - x0) if along_x else abs(y1 - y0)
        mid_x = (x0 + x1) / 2
        mid_y = (y0 + y1) / 2
        if along_x:
            rod = _box_instance(self.city, rod_len, rod_thin, rod_thin)
        else:
            rod = _box_instance(self.city, rod_thin, rod_len, rod_thin)
        rod.setPos(mid_x, mid_y, rod_z)
        rod.setMaterial(housing, 1)

        # Hang from the underside of the rod, centred on the span.
        root = self.city.attachNewNode("traffic-light")
        root.setPos(mid_x, mid_y, rod_z - rod_thin / 2 - box_h / 2)
        root.lookAt(face_x, face_y, root.getZ())

        head = _box_instance(root, box_w, box_d, box_h)
        head.setPos(0.0, 0.0, 0.0)
        head.setMaterial(housing, 1)

        lamp_y = box_d / 2 + lamp_depth / 2
        # Top to bottom: red, amber, green, same stacking as a real signal.
        colours = ("red", "amber", "green")
        span = 3 * lamp + 2 * gap
        for index, name in enumerate(colours):
            lamp_z = span / 2 - lamp / 2 - index * (lamp + gap)
            lens = _box_instance(root, lamp, lamp_depth, lamp)
            lens.setPos(0.0, lamp_y, lamp_z)
            lens.setMaterial(signal_material(name), 1)

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
    ) -> None:
        """Empty road loop with lawn and a centred 6x2 of brown houses."""
        self._add_city_block(
            west_face,
            block_size,
            ((), (), (), ()),
            y_offset=y_offset,
            eastern_road=eastern_road,
            southern_road=southern_road,
            factory=False,
        )
        lot_mid_x = west_face + lot_width / 2
        # Empty-ring south face at y_offset: tower_y(-1 + offset) - half depth.
        lot_mid_y = -1.0 + y_offset - block_size[1] / 2 + lot_depth / 2
        road_thickness = 0.1
        self._add_block(
            lot_mid_x,
            lot_mid_y,
            -block_size[2] / 2 + road_thickness / 2,
            (lot_width, lot_depth, road_thickness),
            lawn_material(),
        )
        house_pitch = 5.0
        houses_across, houses_deep = 6, 2
        for crow in range(houses_deep):
            for ccol in range(houses_across):
                self._add_house(
                    lot_mid_x + (ccol - (houses_across - 1) / 2) * house_pitch,
                    lot_mid_y + (crow - (houses_deep - 1) / 2) * house_pitch,
                )

    def _add_house(self, x: float, y: float) -> None:
        """Brown 2x2 cube capped by a 3x3 pyramid, centred on ``(x, y)``."""
        cube_size = (2.0, 2.0, 2.0)
        pyramid_size = (3.0, 3.0, 1.5)
        self._add_block(x, y, 0.0, cube_size, brown_material(0.6), top=False)
        self._add_cube_squares(x, y, 0.0, cube_size)
        pyramid = self.city.attachNewNode(make_pyramid(*pyramid_size))
        pyramid.setPos(x, y, cube_size[2] / 2)
        pyramid.setMaterial(brown_material(0.6), 1)

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

    def _init_car(
        self,
        x: float,
        y: float,
        road_top: float,
        origin_x: float,
        origin_y: float,
        stride_x: float,
        stride_y: float,
        cols: int,
        rows: int,
        *,
        start_h: int,
        start_v: int,
    ) -> None:
        """Blue 2×1×1 car on the road grid, long axis along travel."""
        size = (2.0, 1.0, 1.0)
        self.car = _box_instance(self.render, *size)
        self.car.setMaterial(sphere_material(), 1)
        self._car_z = road_top + size[2] / 2
        self._car_origin_x = origin_x
        self._car_origin_y = origin_y
        self._car_stride_x = stride_x
        self._car_stride_y = stride_y
        self._car_cols = cols
        self._car_rows = rows
        # Stop with the front bumper on the 5-wide intersection edge.
        self._car_stop_offset = 5.0 / 2 + size[0] / 2
        # Two lanes on a 5-wide road; sit in the middle of the right lane.
        self._car_lane_offset = 5.0 / 4
        # Cruise ~one short block per couple of seconds; decel into the stop line.
        self._car_cruise = 10.0
        self._car_accel = 12.0
        self._car_decel_dist = 6.0
        self._car_wait_time = 3.0
        self._car_speed = self._car_cruise
        self._car_state = "drive"
        self._car_wait = 0.0
        self._car_dir = (1, 0)
        self._car_heading = 0.0
        self._car_to = (start_v + 1, start_h)
        rx, ry = self._car_right(self._car_dir)
        self._car_pos = [
            x + rx * self._car_lane_offset,
            y + ry * self._car_lane_offset,
        ]
        self._car_target = self._car_stop_xy(*self._car_to, self._car_dir)
        self._place_car()

    def _car_intersection_xy(self, v: int, h: int) -> tuple[float, float]:
        return (
            self._car_origin_x + v * self._car_stride_x,
            self._car_origin_y + h * self._car_stride_y,
        )

    @staticmethod
    def _car_right(direction: tuple[int, int]) -> tuple[int, int]:
        """Unit right vector relative to travel (right-hand traffic)."""
        dx, dy = direction
        return (dy, -dx)

    def _car_lane_shift(self, direction: tuple[int, int]) -> tuple[float, float]:
        rx, ry = self._car_right(direction)
        lane = self._car_lane_offset
        return rx * lane, ry * lane

    def _car_stop_xy(
        self,
        v: int,
        h: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Approach stop: front on the near edge, centered in the right lane."""
        cx, cy = self._car_intersection_xy(v, h)
        dx, dy = direction
        offset = self._car_stop_offset
        lx, ly = self._car_lane_shift(direction)
        return cx - dx * offset + lx, cy - dy * offset + ly

    def _car_exit_xy(
        self,
        v: int,
        h: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Far-edge point leaving an intersection in the right lane."""
        cx, cy = self._car_intersection_xy(v, h)
        dx, dy = direction
        offset = self._car_stop_offset
        lx, ly = self._car_lane_shift(direction)
        return cx + dx * offset + lx, cy + dy * offset + ly

    def _car_in_bounds(self, v: int, h: int) -> bool:
        return 0 <= v <= self._car_cols and 0 <= h <= self._car_rows

    def _car_choose_turn(self) -> tuple[int, int]:
        """Pick forward, left, or right from the car's front among open roads."""
        v, h = self._car_to
        dx, dy = self._car_dir
        options: list[tuple[int, int]] = []
        for ndx, ndy in (
            (dx, dy),
            (-dy, dx),
            (dy, -dx),
        ):
            if self._car_in_bounds(v + ndx, h + ndy):
                options.append((ndx, ndy))
        if not options:
            return (-dx, -dy)
        return random.choice(options)

    def _car_begin_maneuver(self, new_dir: tuple[int, int]) -> None:
        """Leave the stop line: arc on turns, straight when going forward."""
        old_dir = self._car_dir
        v, h = self._car_to
        cx, cy = self._car_intersection_xy(v, h)
        o = self._car_stop_offset
        cross = old_dir[0] * new_dir[1] - old_dir[1] * new_dir[0]
        dot = old_dir[0] * new_dir[0] + old_dir[1] * new_dir[1]
        self._car_dir = new_dir
        self._car_to = (v + new_dir[0], h + new_dir[1])
        self._car_speed = 0.0
        self._car_after_cross = self._car_stop_xy(*self._car_to, new_dir)

        if dot > 0:
            # Straight through to the far edge, then on to the next stop.
            self._car_state = "crossing"
            self._car_target = self._car_exit_xy(v, h, new_dir)
            return

        if cross == 0:
            # Rare dead-end U-turn: spin in place, then drive back.
            self._car_state = "u-turn"
            self._car_heading_from = self._car_heading
            self._car_heading_to = math.degrees(math.atan2(new_dir[1], new_dir[0]))
            delta = (self._car_heading_to - self._car_heading_from + 180.0) % 360.0 - 180.0
            self._car_heading_to = self._car_heading_from + delta
            self._car_u_turn_span = abs(delta) if abs(delta) > 1e-3 else 180.0
            self._car_u_turn_progress = 0.0
            return

        # Quarter-circle in the right lane: left turns are wider, right tighter.
        sign = 1.0 if cross > 0 else -1.0
        lane = self._car_lane_offset
        self._car_state = "turning"
        self._car_arc_center = (
            cx - old_dir[0] * o + new_dir[0] * o,
            cy - old_dir[1] * o + new_dir[1] * o,
        )
        self._car_arc_radius = o + lane if cross > 0 else o - lane
        self._car_arc_sign = sign
        rx = self._car_pos[0] - self._car_arc_center[0]
        ry = self._car_pos[1] - self._car_arc_center[1]
        self._car_arc_angle = math.atan2(ry, rx)
        self._car_arc_end = self._car_arc_angle + sign * (math.pi / 2)

    def _place_car(self) -> None:
        self.car.setPos(self._car_pos[0], self._car_pos[1], self._car_z)
        self.car.setH(self._car_heading)

    def _car_advance_speed(self, dt: float, dist: float | None = None) -> None:
        if dist is not None and dist < self._car_decel_dist:
            target = self._car_cruise * math.sqrt(max(dist, 0.0) / self._car_decel_dist)
            self._car_speed = min(self._car_speed, target)
        else:
            self._car_speed = min(self._car_cruise, self._car_speed + self._car_accel * dt)

    def _car_task(self, task):
        dt = min(self.clock.getDt(), 0.05)
        if self._car_state == "wait":
            self._car_wait -= dt
            if self._car_wait <= 0.0:
                self._car_begin_maneuver(self._car_choose_turn())
                self._place_car()
            return task.cont

        if self._car_state == "u-turn":
            self._car_advance_speed(dt)
            # Match turn rate to cruise so the spin feels like a tight pivot.
            rate = math.degrees(self._car_cruise / max(self._car_stop_offset, 1.0))
            step = rate * dt
            remain = self._car_u_turn_span - self._car_u_turn_progress
            if step >= remain:
                self._car_heading = self._car_heading_to
                self._car_target = self._car_after_cross
                self._car_state = "drive"
            else:
                self._car_u_turn_progress += step
                t = self._car_u_turn_progress / self._car_u_turn_span
                self._car_heading = (
                    self._car_heading_from
                    + (self._car_heading_to - self._car_heading_from) * t
                )
            self._place_car()
            return task.cont

        if self._car_state == "turning":
            self._car_advance_speed(dt)
            radius = self._car_arc_radius
            angle_step = (self._car_speed / radius) * dt * self._car_arc_sign
            remain = self._car_arc_end - self._car_arc_angle
            if abs(angle_step) >= abs(remain):
                self._car_arc_angle = self._car_arc_end
                acx, acy = self._car_arc_center
                self._car_pos[0] = acx + radius * math.cos(self._car_arc_angle)
                self._car_pos[1] = acy + radius * math.sin(self._car_arc_angle)
                self._car_heading = math.degrees(
                    math.atan2(self._car_dir[1], self._car_dir[0])
                )
                self._car_target = self._car_after_cross
                self._car_state = "drive"
            else:
                self._car_arc_angle += angle_step
                acx, acy = self._car_arc_center
                self._car_pos[0] = acx + radius * math.cos(self._car_arc_angle)
                self._car_pos[1] = acy + radius * math.sin(self._car_arc_angle)
                # Tangent to the arc: CCW is angle+90°, CW is angle-90°.
                self._car_heading = math.degrees(
                    self._car_arc_angle + self._car_arc_sign * (math.pi / 2)
                )
            self._place_car()
            return task.cont

        tx, ty = self._car_target
        dx = tx - self._car_pos[0]
        dy = ty - self._car_pos[1]
        dist = math.hypot(dx, dy)
        if dist <= max(self._car_speed * dt, 0.02):
            self._car_pos[0] = tx
            self._car_pos[1] = ty
            if self._car_state == "crossing":
                self._car_target = self._car_after_cross
                self._car_state = "drive"
                self._place_car()
                return task.cont
            self._car_speed = 0.0
            self._car_state = "wait"
            self._car_wait = self._car_wait_time
            self._place_car()
            return task.cont

        if self._car_state == "drive":
            self._car_advance_speed(dt, dist)
        else:
            self._car_advance_speed(dt)

        step = min(self._car_speed * dt, dist)
        self._car_pos[0] += dx / dist * step
        self._car_pos[1] += dy / dist * step
        self._car_heading = math.degrees(math.atan2(dy, dx))
        self._place_car()
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


def main() -> None:
    app = CityApp(screenshot=_ARGS.screenshot)
    if _ARGS.screenshot:
        app.capture()
    else:
        app.run()


if __name__ == "__main__":
    main()
