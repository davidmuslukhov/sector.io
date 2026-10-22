"""Software-city scene. Three identical lit spheres form an equilateral triangle,
joined center to center by thin cylinders of the same colour."""

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


def sphere_material() -> Material:
    material = Material()
    material.setAmbient((0.15, 0.28, 0.4, 1))
    material.setDiffuse((0.25, 0.55, 0.85, 1))
    material.setSpecular((0.45, 0.45, 0.5, 1))
    material.setShininess(32)
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
        for x, y in positions:
            self._add_sphere(x, y, material)
        # Each sphere joins its two neighbours, so the three links close the triangle.
        for index, (x0, y0) in enumerate(positions):
            x1, y1 = positions[(index + 1) % len(positions)]
            self._add_link(x0, y0, x1, y1, material)
        self._add_lights()

        self.heading = 30.0
        self.pitch = 20.0
        self.distance = 16.0
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
        self.camera.setPos(
            self.distance * math.sin(heading) * cos_pitch,
            -self.distance * math.cos(heading) * cos_pitch,
            self.distance * math.sin(pitch),
        )
        self.camera.lookAt(0, 0, 0)

    def _zoom(self, delta: float) -> None:
        self.distance = min(40.0, max(2.0, self.distance + delta))
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
