"""Software-city scene. Three identical lit spheres form an equilateral triangle,
joined center to center by thin cylinders, with a five-floor stack of
blocks to their right and a row of yellow squares on each vertical face.
A brown cube stands five units beyond the stack, capped by a brown pyramid."""

import argparse
import math
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
)
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


def sphere_material() -> Material:
    material = Material()
    material.setAmbient((0.15, 0.28, 0.4, 1))
    material.setDiffuse((0.25, 0.55, 0.85, 1))
    material.setSpecular((0.45, 0.45, 0.5, 1))
    material.setShininess(32)
    return material


def block_material() -> Material:
    material = Material()
    material.setAmbient((0.45, 0.45, 0.47, 1))
    material.setDiffuse((0.78, 0.78, 0.80, 1))
    material.setSpecular((0.55, 0.55, 0.55, 1))
    material.setShininess(32)
    return material


# One yellow hue. Brightness scales this colour, so every square stays the same shade.
_YELLOW = (1.0, 0.82 / 0.95, 0.12 / 0.95)
_YELLOW_LEVELS = (0.50, 0.62, 0.74, 0.86, 1.0)


def square_material(lightness: float) -> Material:
    """Yellow of a single hue. ``lightness`` 0.95 matches the original square."""
    diffuse = tuple(channel * lightness for channel in _YELLOW)
    ambient = tuple(channel * 0.47 for channel in diffuse)
    specular = tuple(channel * 0.45 for channel in diffuse)
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(24)
    return material


def _square_lightness(index: int) -> float:
    return _YELLOW_LEVELS[(index * 3) % len(_YELLOW_LEVELS)]


def brown_material(lightness: float = 1.0) -> Material:
    """Same brown hue. ``lightness`` 1 matches the door; lower values are darker."""
    ambient = tuple(channel * lightness for channel in (0.28, 0.16, 0.07))
    diffuse = tuple(channel * lightness for channel in (0.50, 0.30, 0.13))
    specular = tuple(channel * lightness for channel in (0.25, 0.18, 0.1))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(16)
    return material


class CityApp(ShowBase):
    def __init__(self, screenshot: str | None = None) -> None:
        super().__init__()
        self.screenshot_path = screenshot
        self.disableMouse()
        self.setBackgroundColor(0.08, 0.09, 0.12, 1)

        self.city = self.render.attachNewNode("city")
        # Same center spacing as the old row, laid out as an equilateral triangle
        # in the XY plane and centered on the origin.
        side = 2.5
        height = side * math.sqrt(3) / 2
        positions = (
            (-side / 2, -height / 3),
            (side / 2, -height / 3),
            (0.0, 2 * height / 3),
        )
        material = sphere_material()
        sphere_radius = 1.0
        for x, y in positions:
            self._add_sphere(x, y, material)
        # Each sphere joins its two neighbours, so the three links close the triangle.
        for index, (x0, y0) in enumerate(positions):
            x1, y1 = positions[(index + 1) % len(positions)]
            self._add_link(x0, y0, x1, y1, material)

        block_size = (5.0, 5.0, 2.0)
        block_gap = 5.0
        floor_count = 5
        right_surface = side / 2 + sphere_radius
        block_center_x = right_surface + block_gap + block_size[0] / 2
        grey = block_material()
        for floor in range(floor_count):
            floor_z = floor * block_size[2]
            self._add_block(
                block_center_x,
                0.0,
                floor_z,
                block_size,
                grey,
                top=floor == floor_count - 1,
                bottom=floor == 0,
            )
            self._add_face_squares(block_center_x, 0.0, floor_z, block_size, floor * 12)

        cube_size = (2.0, 2.0, 2.0)
        stack_right = block_center_x + block_size[0] / 2
        cube_center_x = stack_right + 5.0 + cube_size[0] / 2
        self._add_block(cube_center_x, 0.0, 0.0, cube_size, brown_material(0.6), top=False)
        self._add_cube_squares(cube_center_x, 0.0, 0.0, cube_size)
        pyramid_size = (3.0, 3.0, 1.5)
        pyramid = self.city.attachNewNode(make_pyramid(*pyramid_size))
        pyramid.setPos(cube_center_x, 0.0, cube_size[2] / 2)
        pyramid.setMaterial(brown_material(0.6), 1)
        self._add_lights()

        left = -side / 2 - sphere_radius
        right = cube_center_x + pyramid_size[0] / 2
        stack_bottom = -block_size[2] / 2
        stack_top = (floor_count - 1) * block_size[2] + block_size[2] / 2
        self.look_at = ((left + right) / 2, 0.0, (stack_bottom + stack_top) / 2)
        self.heading = 30.0
        self.pitch = 20.0
        self.distance = 44.0
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

    def _add_block(
        self,
        x: float,
        y: float,
        z: float,
        size: tuple[float, float, float],
        material: Material,
        top: bool = True,
        bottom: bool = True,
    ) -> None:
        block = self.city.attachNewNode(make_box(*size, top=top, bottom=bottom))
        block.setPos(x, y, z)
        block.setMaterial(material, 1)

    def _add_face_squares(
        self,
        x: float,
        y: float,
        z: float,
        size: tuple[float, float, float],
        level_start: int = 0,
    ) -> None:
        """Three 1×1 squares on every vertical face, inset 0.5 from the edges."""
        sx, sy, sz = size
        square = 1.0
        margin = 0.5
        depth = 0.04
        row_z = z - sz / 2 + margin + square / 2
        level = level_start

        def centers(span: float) -> tuple[float, float, float]:
            left = -span / 2 + margin + square / 2
            right = span / 2 - margin - square / 2
            return (left, (left + right) / 2, right)

        along_x = centers(sx)
        along_y = centers(sy)
        for sign in (1.0, -1.0):
            face_y = y + sign * (sy / 2 + depth / 2)
            for offset in along_x:
                tone = _square_lightness(level)
                level += 1
                # Front face is the one toward the camera (-Y). A brown door fills that gap.
                if z == 0 and sign < 0 and offset == 0:
                    door_height = 1.25
                    door_bottom = z - sz / 2
                    door = self.city.attachNewNode(make_box(1.0, depth, door_height))
                    door.setPos(x + offset, face_y, door_bottom + door_height / 2)
                    door.setMaterial(brown_material(), 1)
                    continue
                panel = self.city.attachNewNode(make_box(square, depth, square))
                panel.setPos(x + offset, face_y, row_z)
                panel.setMaterial(square_material(tone), 1)
            face_x = x + sign * (sx / 2 + depth / 2)
            for offset in along_y:
                panel = self.city.attachNewNode(make_box(depth, square, square))
                panel.setPos(face_x, y + offset, row_z)
                panel.setMaterial(square_material(_square_lightness(level)), 1)
                level += 1

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
            panel = self.city.attachNewNode(make_box(panel_x, panel_y, square))
            panel.setPos(px, py, pz)
            panel.setMaterial(square_material(_square_lightness(level)), 1)

        # Lighter than the cube so the rectangle reads on the bare front face.
        rectangle_height = 0.75
        rectangle_bottom = z - sz / 2
        rectangle = self.city.attachNewNode(make_box(0.5, depth, rectangle_height))
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
