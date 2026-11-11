"""Procedural mesh primitives and cached templates."""

from __future__ import annotations

import math

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    Material,
    NodePath,
)

from city.materials import (
    block_material,
    car_material,
    roof_material,
    square_lightness,
    square_material,
    stack_material,
)

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


def make_annulus_sector(
    inner_radius: float,
    outer_radius: float,
    start_angle: float,
    end_angle: float,
    thickness: float,
    segments: int = 24,
) -> GeomNode:
    """Flat annular sector in XY, centred on the origin, extruded along Z.

    Angles are radians from +X toward +Y (standard CCW). ``segments`` is the
    number of wedges across the arc. Suitable for highway corner pads.
    """
    if outer_radius <= inner_radius:
        raise ValueError("outer_radius must exceed inner_radius")
    if segments < 1:
        raise ValueError("segments must be at least 1")
    hz = thickness / 2.0
    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("annulus_sector", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    def add_cap(z: float, nz: float, reverse: bool) -> None:
        base = vertex.getWriteRow()
        for i in range(segments + 1):
            t = i / segments
            angle = start_angle + (end_angle - start_angle) * t
            c = math.cos(angle)
            s = math.sin(angle)
            vertex.addData3(inner_radius * c, inner_radius * s, z)
            normal.addData3(0.0, 0.0, nz)
            vertex.addData3(outer_radius * c, outer_radius * s, z)
            normal.addData3(0.0, 0.0, nz)
        for i in range(segments):
            i0 = base + 2 * i
            i1 = i0 + 1
            i2 = i0 + 2
            i3 = i0 + 3
            # reverse=False is CCW from +Z (top); reverse=True flips for the underside.
            if reverse:
                tris.addVertices(i0, i3, i1)
                tris.addVertices(i0, i2, i3)
            else:
                tris.addVertices(i0, i1, i3)
                tris.addVertices(i0, i3, i2)

    # Top (+Z) and bottom (-Z) decks.
    add_cap(hz, 1.0, reverse=False)
    add_cap(-hz, -1.0, reverse=True)

    def add_arc_wall(radius: float, outward: bool) -> None:
        base = vertex.getWriteRow()
        for i in range(segments + 1):
            t = i / segments
            angle = start_angle + (end_angle - start_angle) * t
            c = math.cos(angle)
            s = math.sin(angle)
            nx = c if outward else -c
            ny = s if outward else -s
            vertex.addData3(radius * c, radius * s, -hz)
            normal.addData3(nx, ny, 0.0)
            vertex.addData3(radius * c, radius * s, hz)
            normal.addData3(nx, ny, 0.0)
        for i in range(segments):
            i0 = base + 2 * i
            i1 = i0 + 1
            i2 = i0 + 2
            i3 = i0 + 3
            if outward:
                tris.addVertices(i0, i2, i1)
                tris.addVertices(i1, i2, i3)
            else:
                tris.addVertices(i0, i1, i2)
                tris.addVertices(i1, i3, i2)

    add_arc_wall(outer_radius, outward=True)
    add_arc_wall(inner_radius, outward=False)

    def add_radial_wall(angle: float, at_end: bool) -> None:
        c = math.cos(angle)
        s = math.sin(angle)
        # Outward normals point into the missing sector: opposite the CCW sweep
        # at the start cut, along the CCW sweep at the end cut.
        if at_end:
            nx, ny = -s, c
        else:
            nx, ny = s, -c
        corners = (
            (inner_radius * c, inner_radius * s, -hz),
            (outer_radius * c, outer_radius * s, -hz),
            (outer_radius * c, outer_radius * s, hz),
            (inner_radius * c, inner_radius * s, hz),
        )
        base = vertex.getWriteRow()
        for corner in corners:
            vertex.addData3(*corner)
            normal.addData3(nx, ny, 0.0)
        if at_end:
            tris.addVertices(base, base + 1, base + 2)
            tris.addVertices(base, base + 2, base + 3)
        else:
            tris.addVertices(base, base + 2, base + 1)
            tris.addVertices(base, base + 3, base + 2)

    add_radial_wall(start_angle, at_end=False)
    add_radial_wall(end_angle, at_end=True)

    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("annulus_sector")
    node.addGeom(geom)
    return node


def make_rhombus_slab(
    vertices: tuple[tuple[float, float], ...],
    thickness: float,
) -> GeomNode:
    """Flat slab whose top outline is the XY polygon ``vertices`` (CCW)."""
    if len(vertices) < 3:
        raise ValueError("rhombus slab needs at least 3 vertices")
    hz = thickness / 2.0
    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("rhombus_slab", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    # Ensure CCW in XY so the top deck faces +Z under right-hand winding.
    area = 0.0
    count = len(vertices)
    for index in range(count):
        x0, y0 = vertices[index]
        x1, y1 = vertices[(index + 1) % count]
        area += x0 * y1 - x1 * y0
    ordered = vertices if area > 0 else tuple(reversed(vertices))

    # Top face (normal +Z), fan from vertex 0.
    top_base = vertex.getWriteRow()
    for x, y in ordered:
        vertex.addData3(x, y, hz)
        normal.addData3(0.0, 0.0, 1.0)
    for index in range(1, len(ordered) - 1):
        tris.addVertices(top_base, top_base + index, top_base + index + 1)

    # Bottom face (normal -Z), opposite winding.
    bot_base = vertex.getWriteRow()
    for x, y in ordered:
        vertex.addData3(x, y, -hz)
        normal.addData3(0.0, 0.0, -1.0)
    for index in range(1, len(ordered) - 1):
        tris.addVertices(bot_base, bot_base + index + 1, bot_base + index)

    # Side walls (outward for a CCW polygon).
    for index in range(count):
        x0, y0 = ordered[index]
        x1, y1 = ordered[(index + 1) % count]
        edge_x, edge_y = x1 - x0, y1 - y0
        length = math.hypot(edge_x, edge_y) or 1.0
        nx, ny = edge_y / length, -edge_x / length
        base = vertex.getWriteRow()
        for corner in (
            (x0, y0, -hz),
            (x1, y1, -hz),
            (x1, y1, hz),
            (x0, y0, hz),
        ):
            vertex.addData3(*corner)
            normal.addData3(nx, ny, 0.0)
        tris.addVertices(base, base + 1, base + 2)
        tris.addVertices(base, base + 2, base + 3)

    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("rhombus_slab")
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
BOX_TEMPLATES: dict[tuple[float, float, float, bool, bool], NodePath] = {}
# Flattened factory buildings. Keyed by plan, height, and bottom z.
FACTORY_TEMPLATES: dict[tuple[float, float, float, float], NodePath] = {}
# Flattened blocky car mesh. Copied once per scene.
CAR_TEMPLATE: NodePath | None = None


def box_instance(
    parent: NodePath,
    sx: float,
    sy: float,
    sz: float,
    top: bool = True,
    bottom: bool = True,
) -> NodePath:
    """Copy a cached box Geom into ``parent`` instead of rebuilding vertices."""
    key = (sx, sy, sz, top, bottom)
    template = BOX_TEMPLATES.get(key)
    if template is None:
        template = NodePath(make_box(sx, sy, sz, top=top, bottom=bottom))
        BOX_TEMPLATES[key] = template
    return template.copyTo(parent)


def factory_template(
    sx: float,
    sy: float,
    height: float,
    bottom_z: float,
) -> NodePath:
    """One flattened factory. Origin at plan centre; place with ``setPos(x, y, 0)``."""
    key = (sx, sy, height, bottom_z)
    cached = FACTORY_TEMPLATES.get(key)
    if cached is not None:
        return cached

    root = NodePath("factory")
    body = box_instance(root, sx, sy, height)
    body.setPos(0.0, 0.0, bottom_z + height / 2)
    body.setMaterial(block_material(0.92), 1)

    # Cornice lip and dark roof deck on the factory hall.
    roof_z = bottom_z + height
    cornice = box_instance(root, sx + 0.2, sy + 0.2, 0.2)
    cornice.setPos(0.0, 0.0, roof_z + 0.08)
    cornice.setMaterial(block_material(0.78), 1)
    deck = box_instance(root, sx - 0.3, sy - 0.3, 0.12)
    deck.setPos(0.0, 0.0, roof_z + 0.2)
    deck.setMaterial(roof_material(), 1)

    stack_size = (1.8, 1.8, 5.5)
    stack_z = roof_z + 0.3 + stack_size[2] / 2
    sooty = stack_material()
    for stack_x in (-sx / 4, 0.0, sx / 4):
        stack = box_instance(root, *stack_size)
        stack.setPos(stack_x, 0.0, stack_z)
        stack.setMaterial(sooty, 1)

    window_w = 0.85
    window_h = 1.2
    window_depth = 0.05
    side_count = 5
    window_gap = (sy - side_count * window_w) / (side_count + 1)
    long_count = int((sx - window_gap) / (window_w + window_gap))
    lower_z = bottom_z + height * 0.38
    window_zs = (lower_z, lower_z + 2.4)
    level = 0

    def window_offsets(span: float, count: int) -> list[float]:
        return [
            -span / 2
            + window_gap
            + window_w / 2
            + index * (window_w + window_gap)
            for index in range(count)
        ]

    for sign in (1.0, -1.0):
        face_x = sign * (sx / 2 + window_depth / 2)
        for window_z in window_zs:
            for offset_y in window_offsets(sy, side_count):
                panel = box_instance(root, window_depth, window_w, window_h)
                panel.setPos(face_x, offset_y, window_z)
                panel.setMaterial(square_material(square_lightness(level)), 1)
                level += 1
        face_y = sign * (sy / 2 + window_depth / 2)
        for window_z in window_zs:
            for offset_x in window_offsets(sx, long_count):
                panel = box_instance(root, window_w, window_depth, window_h)
                panel.setPos(offset_x, face_y, window_z)
                panel.setMaterial(square_material(square_lightness(level)), 1)
                level += 1

    root.flattenStrong()
    FACTORY_TEMPLATES[key] = root
    return root


def car_template() -> NodePath:
    """Blocky blue car. Origin at the bounding-box centre; +X is forward.

    Body parts are flattened; corner lamps stay named children so turn signals
    can blink left or right without rebuilding the mesh.
    """
    global CAR_TEMPLATE
    if CAR_TEMPLATE is not None:
        return CAR_TEMPLATE

    root = NodePath("car")
    # Body stays its own node so copies can swap paint without retinting trim.
    body_np = root.attachNewNode("body")
    detail = root.attachNewNode("detail")
    body = car_material("body")
    glass = car_material("glass")
    trim = car_material("trim")
    headlight = car_material("headlight")
    taillight = car_material("taillight")
    wheel = car_material("wheel")

    def part(
        parent: NodePath,
        sx: float,
        sy: float,
        sz: float,
        x: float,
        y: float,
        z: float,
        material: Material,
        name: str | None = None,
    ) -> NodePath:
        box = box_instance(parent, sx, sy, sz)
        box.setPos(x, y, z)
        box.setMaterial(material, 1)
        if name is not None:
            box.setName(name)
        return box

    # Lower hull and raised cabin keep the familiar 2×1×1 silhouette.
    part(body_np, 1.7, 0.92, 0.42, 0.0, 0.0, -0.12, body)
    part(body_np, 1.05, 0.84, 0.36, -0.05, 0.0, 0.27, body)

    # Dark window panes inset on the cabin faces.
    part(detail, 0.06, 0.72, 0.26, 0.505, 0.0, 0.28, glass)
    part(detail, 0.06, 0.72, 0.26, -0.58, 0.0, 0.28, glass)
    for side in (-1.0, 1.0):
        part(detail, 0.7, 0.05, 0.24, -0.05, side * 0.445, 0.28, glass)

    # Front and rear bumpers, plus a grille between the headlights.
    part(detail, 0.18, 1.0, 0.22, 0.94, 0.0, -0.2, trim)
    part(detail, 0.18, 1.0, 0.22, -0.94, 0.0, -0.2, trim)
    part(detail, 0.08, 0.5, 0.16, 0.9, 0.0, -0.08, trim)

    # Side mirrors and a thin roof light bar.
    for side in (-1.0, 1.0):
        part(detail, 0.14, 0.12, 0.1, 0.28, side * 0.52, 0.12, trim)
    part(detail, 0.5, 0.2, 0.06, -0.05, 0.0, 0.48, trim)

    # Four blocky wheels under the corners.
    for wx, wy in ((0.55, 0.42), (0.55, -0.42), (-0.55, 0.42), (-0.55, -0.42)):
        part(detail, 0.38, 0.2, 0.38, wx, wy, -0.31, wheel)

    body_np.flattenStrong()
    detail.flattenStrong()

    # +Y is the car's left; -Y is right. Lamps stay unflattened for signalling.
    for side, label in ((1.0, "left"), (-1.0, "right")):
        part(
            root, 0.1, 0.18, 0.14, 0.96, side * 0.34, -0.05, headlight,
            f"headlight-{label}",
        )
        part(
            root, 0.1, 0.18, 0.14, -0.96, side * 0.34, -0.05, taillight,
            f"taillight-{label}",
        )

    CAR_TEMPLATE = root
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
        add_face(corners, face_normal(*corners))
    add_face((base[3], base[2], base[1], base[0]), (0.0, 0.0, -1.0))
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("pyramid")
    node.addGeom(geom)
    return node


def face_normal(
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

