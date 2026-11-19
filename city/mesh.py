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
    bark_material,
    car_material,
    factory_material,
    foliage_material,
    lamp_material,
    roof_material,
    stack_material,
)

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


def make_ramp_slab(
    length: float,
    width: float,
    thickness: float,
    dz: float,
) -> GeomNode:
    """Road slab along +Y with vertical ends and a constant vertical thickness.

    Centres on the origin. At ``y = -length/2`` the slab is centred at
    ``z = -dz/2``; at ``y = +length/2`` it is centred at ``z = +dz/2``. Vertical
    end caps let the high end butt cleanly against a flat bridge deck.
    """
    if length <= 0.0 or width <= 0.0 or thickness <= 0.0:
        raise ValueError("ramp slab dimensions must be positive")
    hw = width / 2.0
    hl = length / 2.0
    ht = thickness / 2.0
    z0 = -dz / 2.0
    z1 = dz / 2.0
    # Corner order: start-left, start-right, end-right, end-left.
    top = (
        (-hw, -hl, z0 + ht),
        (hw, -hl, z0 + ht),
        (hw, hl, z1 + ht),
        (-hw, hl, z1 + ht),
    )
    bot = (
        (-hw, -hl, z0 - ht),
        (hw, -hl, z0 - ht),
        (hw, hl, z1 - ht),
        (-hw, hl, z1 - ht),
    )
    hyp = math.hypot(length, dz) or 1.0
    top_n = (0.0, -dz / hyp, length / hyp)
    bot_n = (0.0, dz / hyp, -length / hyp)

    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("ramp_slab", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    def add_face(
        corners: tuple[tuple[float, float, float], ...],
        nrm: tuple[float, float, float],
    ) -> None:
        base = vertex.getWriteRow()
        for corner in corners:
            vertex.addData3(*corner)
            normal.addData3(*nrm)
        tris.addVertices(base, base + 1, base + 2)
        tris.addVertices(base, base + 2, base + 3)

    # Top (CCW from above) and bottom (outward = downward).
    add_face(top, top_n)
    add_face((bot[0], bot[3], bot[2], bot[1]), bot_n)
    # Start / end caps (vertical).
    add_face((bot[0], bot[1], top[1], top[0]), (0.0, -1.0, 0.0))
    add_face((bot[2], bot[3], top[3], top[2]), (0.0, 1.0, 0.0))
    # Left / right walls.
    add_face((bot[0], top[0], top[3], bot[3]), (-1.0, 0.0, 0.0))
    add_face((bot[1], bot[2], top[2], top[1]), (1.0, 0.0, 0.0))

    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("ramp_slab")
    node.addGeom(geom)
    return node


def make_pitched_slab(
    x0: float,
    y0: float,
    z0: float,
    x1: float,
    y1: float,
    z1: float,
    width: float,
    thickness: float,
    *,
    end0_along: tuple[float, float] | None = None,
    end1_along: tuple[float, float] | None = None,
) -> GeomNode:
    """World-space road slab along a centreline with vertical thickness.

    ``z0`` / ``z1`` are slab-centre heights. Optional ``end*_along`` sets that
    end's edge direction in XY (miter); default is square to the centreline.
    Place the node at the origin — corners are already in world coordinates.
    """
    if width <= 0.0 or thickness <= 0.0:
        raise ValueError("pitched slab dimensions must be positive")
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        raise ValueError("pitched slab centreline must have length")
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    hw = width / 2.0
    ht = thickness / 2.0

    def unit(vec: tuple[float, float]) -> tuple[float, float]:
        vx, vy = vec
        mag = math.hypot(vx, vy) or 1.0
        return (vx / mag, vy / mag)

    def rail_hit(
        side: float,
        end_x: float,
        end_y: float,
        along: tuple[float, float] | None,
    ) -> tuple[float, float]:
        ox = x0 + side * hw * nx
        oy = y0 + side * hw * ny
        if along is None:
            return (end_x + side * hw * nx, end_y + side * hw * ny)
        ex, ey = unit(along)
        cross = ux * ey - uy * ex
        if abs(cross) < 1e-8:
            return (end_x + side * hw * nx, end_y + side * hw * ny)
        t = ((end_x - ox) * ey - (end_y - oy) * ex) / cross
        return (ox + t * ux, oy + t * uy)

    def corner_z(cx: float, cy: float) -> float:
        along = (cx - x0) * ux + (cy - y0) * uy
        t = max(0.0, min(1.0, along / length))
        return (z0 + (z1 - z0) * t) + ht

    # CCW from above: start-left, start-right, end-right, end-left.
    sl = rail_hit(1.0, x0, y0, end0_along)
    sr = rail_hit(-1.0, x0, y0, end0_along)
    er = rail_hit(-1.0, x1, y1, end1_along)
    el = rail_hit(1.0, x1, y1, end1_along)
    top = (
        (sl[0], sl[1], corner_z(*sl)),
        (sr[0], sr[1], corner_z(*sr)),
        (er[0], er[1], corner_z(*er)),
        (el[0], el[1], corner_z(*el)),
    )
    bot = tuple((x, y, z - thickness) for x, y, z in top)
    top_n = face_normal(top[0], top[1], top[2])
    bot_n = (-top_n[0], -top_n[1], -top_n[2])

    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("pitched_slab", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    def add_face(
        corners: tuple[tuple[float, float, float], ...],
        nrm: tuple[float, float, float],
    ) -> None:
        base = vertex.getWriteRow()
        for corner in corners:
            vertex.addData3(*corner)
            normal.addData3(*nrm)
        tris.addVertices(base, base + 1, base + 2)
        tris.addVertices(base, base + 2, base + 3)

    add_face(top, top_n)
    add_face((bot[0], bot[3], bot[2], bot[1]), bot_n)

    def add_wall(
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        c: tuple[float, float, float],
        d: tuple[float, float, float],
    ) -> None:
        add_face((a, b, c, d), face_normal(a, b, c))

    add_wall(bot[0], bot[1], top[1], top[0])
    add_wall(bot[1], bot[2], top[2], top[1])
    add_wall(bot[2], bot[3], top[3], top[2])
    add_wall(bot[3], bot[0], top[0], top[3])

    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("pitched_slab")
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
# Chamfered floor slabs (cut corners). Keyed by size + chamfer.
CHAMFER_BOX_TEMPLATES: dict[tuple[float, float, float, float], NodePath] = {}
# Wheel cylinders (axis +Y). Keyed by radius, length, segments.
CYLINDER_TEMPLATES: dict[tuple[float, float, int], NodePath] = {}
# Vertical cylinders (axis +Z). Keyed by radius, height, segments.
Z_CYLINDER_TEMPLATES: dict[tuple[float, float, int], NodePath] = {}
# Cones / spires. Keyed by radius, height, segments.
CONE_TEMPLATES: dict[tuple[float, float, int], NodePath] = {}
# Equilateral triangular prisms. Keyed by side, height.
TRI_PRISM_TEMPLATES: dict[tuple[float, float], NodePath] = {}
# Equilateral triangular pyramids. Keyed by side, height.
TRI_PYRAMID_TEMPLATES: dict[tuple[float, float], NodePath] = {}
# Flattened factory buildings. Keyed by plan, height, and bottom z.
FACTORY_TEMPLATES: dict[tuple[float, float, float, float], NodePath] = {}
# Flattened car mesh. Copied once per scene.
CAR_TEMPLATE: NodePath | None = None
TREE_TEMPLATE: NodePath | None = None
LAMP_TEMPLATE: NodePath | None = None


def make_sky_dome(
    radius: float = 4000.0,
    *,
    rings: int = 8,
    sectors: int = 24,
) -> GeomNode:
    """Upper hemisphere with a zenith→horizon colour wash (no textures).

    Horizon warms toward the sun azimuth so the dome reads as daylight, not a
    flat fill. Cheap: vertex colours only, no textures or shaders.
    """
    # Deep cool zenith, pale warm haze at the horizon; sun side is brighter.
    zenith = (0.22, 0.42, 0.78)
    horizon_cool = (0.62, 0.72, 0.86)
    horizon_warm = (0.92, 0.82, 0.68)
    # Match the key light HPR (~38°) so the bright side faces the sun.
    sun_phi = math.radians(38.0)
    fmt = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData("sky", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    color = GeomVertexWriter(vdata, "color")
    tris = GeomTriangles(Geom.UHStatic)

    def vert(theta: float, phi: float) -> int:
        # theta: 0 at +Z zenith … π/2 at horizon. phi around Y-up cylinder.
        st = math.sin(theta)
        x = radius * st * math.cos(phi)
        y = radius * st * math.sin(phi)
        z = radius * math.cos(theta)
        # Ease toward the horizon so mid-sky stays richer blue.
        t = theta / (0.5 * math.pi)
        t = t * t * (3.0 - 2.0 * t)
        # 0..1 how aligned this azimuth is with the sun (cos falloff).
        sun = 0.5 + 0.5 * math.cos(phi - sun_phi)
        sun = sun * sun
        hz = (
            horizon_cool[0] + (horizon_warm[0] - horizon_cool[0]) * sun,
            horizon_cool[1] + (horizon_warm[1] - horizon_cool[1]) * sun,
            horizon_cool[2] + (horizon_warm[2] - horizon_cool[2]) * sun,
        )
        # Soft sun glow near the horizon on the warm side.
        glow = sun * t * t * 0.18
        row = vertex.getWriteRow()
        vertex.addData3(x, y, z)
        color.addData4(
            min(1.0, zenith[0] + (hz[0] - zenith[0]) * t + glow),
            min(1.0, zenith[1] + (hz[1] - zenith[1]) * t + glow * 0.85),
            min(1.0, zenith[2] + (hz[2] - zenith[2]) * t + glow * 0.45),
            1.0,
        )
        return row

    rows: list[list[int]] = []
    for ring in range(rings + 1):
        theta = (0.5 * math.pi) * (ring / rings)
        row_idx = [
            vert(theta, (2.0 * math.pi) * (s / sectors))
            for s in range(sectors)
        ]
        rows.append(row_idx)

    for ring in range(rings):
        for s in range(sectors):
            s1 = (s + 1) % sectors
            a = rows[ring][s]
            b = rows[ring][s1]
            c = rows[ring + 1][s1]
            d = rows[ring + 1][s]
            # Inward-facing so the camera inside sees the wash.
            tris.addVertices(a, d, c)
            tris.addVertices(a, c, b)
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("sky")
    node.addGeom(geom)
    return node


# Flattened street-tree variants (foliage colour / crown shape).
TREE_TEMPLATES: dict[int, NodePath] = {}


def tree_template(variant: int = 0) -> NodePath:
    """Simple street tree: trunk + stacked canopy. Flattened for copyTo."""
    key = variant % 3
    cached = TREE_TEMPLATES.get(key)
    if cached is not None:
        return cached
    root = NodePath(f"tree-{key}")
    trunk = z_cylinder_instance(root, 0.12, 1.5, segments=6)
    trunk.setPos(0.0, 0.0, 0.75)
    trunk.setMaterial(bark_material(), 1)
    leaf = foliage_material(key)
    # Cone + disc canopy — reads as a tree, not stacked crates.
    if key == 0:
        disc = z_cylinder_instance(root, 0.85, 0.55, segments=10)
        disc.setPos(0.0, 0.0, 1.85)
        disc.setMaterial(leaf, 1)
        cone = cone_instance(root, 0.95, 1.4, segments=10)
        cone.setPos(0.0, 0.0, 2.05)
        cone.setMaterial(leaf, 1)
    elif key == 1:
        disc = z_cylinder_instance(root, 0.7, 0.7, segments=10)
        disc.setPos(0.0, 0.0, 2.0)
        disc.setMaterial(leaf, 1)
        disc2 = z_cylinder_instance(root, 0.5, 0.55, segments=8)
        disc2.setPos(0.0, 0.0, 2.55)
        disc2.setMaterial(leaf, 1)
    else:
        cone = cone_instance(root, 1.05, 1.8, segments=10)
        cone.setPos(0.0, 0.0, 1.7)
        cone.setMaterial(leaf, 1)
    root.flattenStrong()
    TREE_TEMPLATES[key] = root
    global TREE_TEMPLATE
    if key == 0:
        TREE_TEMPLATE = root
    return root


def lamp_template() -> NodePath:
    """Street lamp: slim pole, arm, and glowing head."""
    global LAMP_TEMPLATE
    if LAMP_TEMPLATE is not None:
        return LAMP_TEMPLATE
    root = NodePath("lamp")
    pole_mat = lamp_material("pole")
    head_mat = lamp_material("head")
    pole = box_instance(root, 0.12, 0.12, 3.4)
    pole.setPos(0.0, 0.0, 1.7)
    pole.setMaterial(pole_mat, 1)
    arm = box_instance(root, 0.9, 0.1, 0.1)
    arm.setPos(0.35, 0.0, 3.35)
    arm.setMaterial(pole_mat, 1)
    head = box_instance(root, 0.35, 0.28, 0.18)
    head.setPos(0.75, 0.0, 3.2)
    head.setMaterial(head_mat, 1)
    root.flattenStrong()
    LAMP_TEMPLATE = root
    return root


def offset_polyline(
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    offset: float,
) -> list[tuple[float, float]]:
    """Shift a centreline left (positive) / right (negative) of travel."""
    if len(points) < 2:
        return list(points)
    out: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(points):
        if i == 0:
            dx = points[1][0] - x
            dy = points[1][1] - y
        elif i == len(points) - 1:
            dx = x - points[i - 1][0]
            dy = y - points[i - 1][1]
        else:
            dx = points[i + 1][0] - points[i - 1][0]
            dy = points[i + 1][1] - points[i - 1][1]
        length = math.hypot(dx, dy) or 1.0
        tx, ty = dx / length, dy / length
        nx, ny = -ty, tx
        out.append((x + nx * offset, y + ny * offset))
    return out


def _seg_intersection(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> tuple[float, float] | None:
    """Proper intersection of segments AB and CD, or None."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    abx, aby = bx - ax, by - ay
    cdx, cdy = dx - cx, dy - cy
    den = abx * cdy - aby * cdx
    if abs(den) < 1e-9:
        return None
    t = ((cx - ax) * cdy - (cy - ay) * cdx) / den
    u = ((cx - ax) * aby - (cy - ay) * abx) / den
    if t < 0.0 or t > 1.0 or u < 0.0 or u > 1.0:
        return None
    return (ax + t * abx, ay + t * aby)


def arterial_crossings(
    arterials: list[dict],
) -> dict[str, list[tuple[float, float]]]:
    """Map each arterial name to world-space crossings with other arterials."""
    gaps = arterial_crossing_gaps(arterials)
    return {name: [(x, y) for x, y, _radius in discs] for name, discs in gaps.items()}


def _dist2_point_segment(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> tuple[float, float, float]:
    """Return ``(dist2, qx, qy)`` for the closest point on segment AB to P."""
    abx = bx - ax
    aby = by - ay
    denom = abx * abx + aby * aby
    if denom < 1e-12:
        return (px - ax) * (px - ax) + (py - ay) * (py - ay), ax, ay
    t = ((px - ax) * abx + (py - ay) * aby) / denom
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    qx = ax + abx * t
    qy = ay + aby * t
    dx = px - qx
    dy = py - qy
    return dx * dx + dy * dy, qx, qy


def _seg_unit(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    return dx / length, dy / length


def _crossing_clear_radius(
    own_w: float,
    other_w: float,
    sin_angle: float,
) -> float:
    """Median/mark opening radius that clears the other ribbon at this angle.

    Shallow crossings (Fraser Hwy × 88 Ave) need a much larger disc than a
    right-angle junction so barriers don't clip through the skewed pad.
    """
    sin_a = max(0.22, min(1.0, abs(sin_angle)))
    return (other_w * 0.5) / sin_a + own_w * 0.35 + 3.0


def arterial_crossing_gaps(
    arterials: list[dict],
) -> dict[str, list[tuple[float, float, float]]]:
    """Map each arterial to ``(x, y, clear_radius)`` discs at crossings / T-tips.

    ``clear_radius`` already accounts for both paved widths and the crossing
    angle — use it directly for median / mark gaps (add edge offset for fences).
    """
    hits: dict[str, list[tuple[float, float, float]]] = {
        str(a.get("name", "")): [] for a in arterials
    }

    def add_hit(
        name: str, x: float, y: float, radius: float, *, merge: float = 4.0
    ) -> None:
        """Keep one disc per junction; keep the larger opening."""
        bucket = hits[name]
        for i, (hx, hy, hr) in enumerate(bucket):
            if (hx - x) * (hx - x) + (hy - y) * (hy - y) <= merge * merge:
                bucket[i] = (0.5 * (hx + x), 0.5 * (hy + y), max(hr, radius))
                return
        bucket.append((x, y, radius))

    def record(
        a_name: str,
        b_name: str,
        x: float,
        y: float,
        a_w: float,
        b_w: float,
        sin_angle: float,
    ) -> None:
        add_hit(a_name, x, y, _crossing_clear_radius(a_w, b_w, sin_angle))
        add_hit(b_name, x, y, _crossing_clear_radius(b_w, a_w, sin_angle))

    for i, a in enumerate(arterials):
        a_pts = list(a.get("points") or ())
        a_name = str(a.get("name", ""))
        a_w = float(a.get("width") or 0.0)
        if len(a_pts) < 2 or not a_name:
            continue
        for b in arterials[i + 1 :]:
            b_pts = list(b.get("points") or ())
            b_name = str(b.get("name", ""))
            b_w = float(b.get("width") or 0.0)
            if len(b_pts) < 2 or not b_name:
                continue
            found = False
            for ai in range(len(a_pts) - 1):
                for bi in range(len(b_pts) - 1):
                    hit = _seg_intersection(
                        a_pts[ai], a_pts[ai + 1], b_pts[bi], b_pts[bi + 1]
                    )
                    if hit is None:
                        continue
                    found = True
                    aux, auy = _seg_unit(a_pts[ai], a_pts[ai + 1])
                    bux, buy = _seg_unit(b_pts[bi], b_pts[bi + 1])
                    sin_a = abs(aux * buy - auy * bux)
                    record(a_name, b_name, hit[0], hit[1], a_w, b_w, sin_a)
            if found:
                continue
            # T-tips / near-miss shared ends after smoothing: snap endpoint→segment.
            tip_tol = max(2.5, 0.35 * max(a_w, b_w))
            tip_tol2 = tip_tol * tip_tol
            # T junctions are ~90° locally; use a healthy sin floor via helper.
            for tip in (a_pts[0], a_pts[-1]):
                best = None
                best_bi = 0
                for bi in range(len(b_pts) - 1):
                    d2, qx, qy = _dist2_point_segment(
                        tip[0], tip[1], b_pts[bi][0], b_pts[bi][1], b_pts[bi + 1][0], b_pts[bi + 1][1]
                    )
                    if d2 <= tip_tol2 and (best is None or d2 < best[0]):
                        best = (d2, qx, qy)
                        best_bi = bi
                if best is not None:
                    _d2, qx, qy = best
                    # Approach tangent of the stem vs through-road segment.
                    if tip is a_pts[0]:
                        aux, auy = _seg_unit(a_pts[0], a_pts[1])
                    else:
                        aux, auy = _seg_unit(a_pts[-2], a_pts[-1])
                    bux, buy = _seg_unit(b_pts[best_bi], b_pts[best_bi + 1])
                    record(a_name, b_name, qx, qy, a_w, b_w, abs(aux * buy - auy * bux))
            for tip in (b_pts[0], b_pts[-1]):
                best = None
                best_ai = 0
                for ai in range(len(a_pts) - 1):
                    d2, qx, qy = _dist2_point_segment(
                        tip[0], tip[1], a_pts[ai][0], a_pts[ai][1], a_pts[ai + 1][0], a_pts[ai + 1][1]
                    )
                    if d2 <= tip_tol2 and (best is None or d2 < best[0]):
                        best = (d2, qx, qy)
                        best_ai = ai
                if best is not None:
                    _d2, qx, qy = best
                    if tip is b_pts[0]:
                        bux, buy = _seg_unit(b_pts[0], b_pts[1])
                    else:
                        bux, buy = _seg_unit(b_pts[-2], b_pts[-1])
                    aux, auy = _seg_unit(a_pts[best_ai], a_pts[best_ai + 1])
                    record(a_name, b_name, qx, qy, a_w, b_w, abs(aux * buy - auy * bux))
    return hits


def _point_in_gaps(
    x: float,
    y: float,
    gaps: list[tuple[float, float, float]] | tuple[tuple[float, float, float], ...],
) -> bool:
    # Strict interior so circle-boundary cut points stay outside the gap.
    for gx, gy, radius in gaps:
        if radius <= 0.0:
            continue
        dx = x - gx
        dy = y - gy
        if dx * dx + dy * dy < radius * radius:
            return True
    return False


def _segment_gap_exit_points(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    gaps: list[tuple[float, float, float]] | tuple[tuple[float, float, float], ...],
) -> list[tuple[float, float, float]]:
    """``(t, x, y)`` where AB crosses a gap circle, sorted along the segment."""
    hits: list[tuple[float, float, float]] = []
    dx = bx - ax
    dy = by - ay
    aa = dx * dx + dy * dy
    if aa < 1e-12:
        return hits
    for gx, gy, radius in gaps:
        if radius <= 0.0:
            continue
        fx = ax - gx
        fy = ay - gy
        bb = 2.0 * (fx * dx + fy * dy)
        cc = fx * fx + fy * fy - radius * radius
        disc = bb * bb - 4.0 * aa * cc
        if disc < 0.0:
            continue
        root = math.sqrt(disc)
        for sign in (-1.0, 1.0):
            t = (-bb + sign * root) / (2.0 * aa)
            if 0.0 < t < 1.0:
                hits.append((t, ax + dx * t, ay + dy * t))
    hits.sort(key=lambda item: item[0])
    # Dedup near-identical crossings from overlapping discs.
    out: list[tuple[float, float, float]] = []
    for t, x, y in hits:
        if out and abs(t - out[-1][0]) < 1e-5:
            continue
        out.append((t, x, y))
    return out


def split_polyline_around_gaps(
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    gaps: list[tuple[float, float, float]] | tuple[tuple[float, float, float], ...],
) -> list[list[tuple[float, float]]]:
    """Split a polyline into runs that stay outside circular gaps.

    Cuts segments at the exact gap radii so openings stay square to the
    intersection pad instead of depending on sample spacing.
    """
    pts = list(points)
    if len(pts) < 2:
        return []
    active = [(gx, gy, r) for gx, gy, r in gaps if r > 0.0]
    if not active:
        return [pts]

    # Original vertices + circle crossings. Boundary hits are kept as piece ends.
    dense: list[tuple[float, float]] = [pts[0]]
    for i in range(len(pts) - 1):
        a = pts[i]
        b = pts[i + 1]
        for _t, x, y in _segment_gap_exit_points(a[0], a[1], b[0], b[1], active):
            dense.append((x, y))
        dense.append(b)

    pieces: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    def flush() -> None:
        nonlocal current
        if len(current) >= 2:
            pieces.append(current)
        current = []

    def emit(p: tuple[float, float]) -> None:
        if current and abs(current[-1][0] - p[0]) < 1e-9 and abs(current[-1][1] - p[1]) < 1e-9:
            return
        current.append(p)

    for i, p in enumerate(dense):
        if _point_in_gaps(p[0], p[1], active):
            flush()
            continue
        if current:
            prev = current[-1]
            mx = 0.5 * (prev[0] + p[0])
            my = 0.5 * (prev[1] + p[1])
            # Two boundary hits of the same disc are both "outside" — break
            # the span when the midpoint still sits inside the gap.
            if _point_in_gaps(mx, my, active):
                flush()
        emit(p)
    flush()
    return pieces


def split_polyline_around_points(
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    gaps: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    radius: float,
) -> list[list[tuple[float, float]]]:
    """Split a polyline into runs that stay outside circular gaps."""
    discs = [(gx, gy, radius) for gx, gy in gaps]
    return split_polyline_around_gaps(points, discs)


def make_highway_ribbon(
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    width: float,
    thickness: float,
) -> GeomNode:
    """Continuous road ribbon following a centreline polyline in XY.

    Builds a capped prism whose left/right edges track the path, so bends read
    as smooth curves instead of abutting rectangular slabs.
    """
    if len(points) < 2:
        raise ValueError("ribbon needs at least two centreline points")
    if width <= 0.0 or thickness <= 0.0:
        raise ValueError("ribbon width/thickness must be positive")

    # Per-vertex unit tangents (averaged at interior joints).
    tangents: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(points):
        if i == 0:
            dx = points[1][0] - x
            dy = points[1][1] - y
        elif i == len(points) - 1:
            dx = x - points[i - 1][0]
            dy = y - points[i - 1][1]
        else:
            dx = points[i + 1][0] - points[i - 1][0]
            dy = points[i + 1][1] - points[i - 1][1]
        length = math.hypot(dx, dy) or 1.0
        tangents.append((dx / length, dy / length))

    half = width / 2.0
    hz = thickness / 2.0
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for (x, y), (tx, ty) in zip(points, tangents):
        nx, ny = -ty, tx
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))

    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("highway_ribbon", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)
    n = len(points)

    def add_pair(side: list[tuple[float, float]], z: float, nz: float) -> int:
        base = vertex.getWriteRow()
        for x, y in side:
            vertex.addData3(x, y, z)
            normal.addData3(0.0, 0.0, nz)
        return base

    # Top deck (left→right strips).
    top_l = add_pair(left, hz, 1.0)
    top_r = add_pair(right, hz, 1.0)
    for i in range(n - 1):
        tris.addVertices(top_l + i, top_r + i, top_r + i + 1)
        tris.addVertices(top_l + i, top_r + i + 1, top_l + i + 1)

    # Bottom deck.
    bot_l = add_pair(left, -hz, -1.0)
    bot_r = add_pair(right, -hz, -1.0)
    for i in range(n - 1):
        tris.addVertices(bot_l + i, bot_r + i + 1, bot_r + i)
        tris.addVertices(bot_l + i, bot_l + i + 1, bot_r + i + 1)

    def add_side_wall(
        edge: list[tuple[float, float]], outward: bool
    ) -> None:
        base = vertex.getWriteRow()
        for i, (x, y) in enumerate(edge):
            tx, ty = tangents[i]
            nx, ny = (-ty, tx) if outward else (ty, -tx)
            vertex.addData3(x, y, -hz)
            normal.addData3(nx, ny, 0.0)
            vertex.addData3(x, y, hz)
            normal.addData3(nx, ny, 0.0)
        for i in range(n - 1):
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

    add_side_wall(left, outward=True)
    add_side_wall(right, outward=True)

    # End caps.
    for end_i, invert in ((0, False), (n - 1, True)):
        tx, ty = tangents[end_i]
        nx, ny = (tx, ty) if invert else (-tx, -ty)
        lx, ly = left[end_i]
        rx, ry = right[end_i]
        base = vertex.getWriteRow()
        for x, y, z in (
            (lx, ly, -hz),
            (rx, ry, -hz),
            (rx, ry, hz),
            (lx, ly, hz),
        ):
            vertex.addData3(x, y, z)
            normal.addData3(nx, ny, 0.0)
        if invert:
            tris.addVertices(base, base + 1, base + 2)
            tris.addVertices(base, base + 2, base + 3)
        else:
            tris.addVertices(base, base + 2, base + 1)
            tris.addVertices(base, base + 3, base + 2)

    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("highway_ribbon")
    node.addGeom(geom)
    return node


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


def chamfer_box_instance(
    parent: NodePath,
    sx: float,
    sy: float,
    sz: float,
    chamfer: float = 0.35,
) -> NodePath:
    """Floor slab with cut corners — breaks the pure extruded-box silhouette."""
    key = (sx, sy, sz, chamfer)
    template = CHAMFER_BOX_TEMPLATES.get(key)
    if template is None:
        template = NodePath(make_chamfer_box(sx, sy, sz, chamfer=chamfer))
        CHAMFER_BOX_TEMPLATES[key] = template
    return template.copyTo(parent)


def cylinder_instance(
    parent: NodePath,
    radius: float,
    length: float,
    segments: int = 10,
) -> NodePath:
    """Cylinder along local +Y (axle). Used for car wheels."""
    key = (radius, length, segments)
    template = CYLINDER_TEMPLATES.get(key)
    if template is None:
        template = NodePath(make_cylinder(radius, length, segments=segments))
        CYLINDER_TEMPLATES[key] = template
    return template.copyTo(parent)


def make_chamfer_box(
    sx: float,
    sy: float,
    sz: float,
    chamfer: float = 0.35,
) -> GeomNode:
    """Axis-aligned box with 45° corner cuts in plan (octagonal footprint)."""
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    c = min(chamfer, hx * 0.45, hy * 0.45)
    # CCW plan ring: start mid-front, walk around with cut corners.
    ring = (
        (-hx + c, -hy),
        (hx - c, -hy),
        (hx, -hy + c),
        (hx, hy - c),
        (hx - c, hy),
        (-hx + c, hy),
        (-hx, hy - c),
        (-hx, -hy + c),
    )
    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("chamfer_box", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)
    n = len(ring)

    # Top fan.
    top_c = (0.0, 0.0, hz)
    top_i = [0] * n
    for i, (x, y) in enumerate(ring):
        top_i[i] = vertex.getWriteRow()
        vertex.addData3(x, y, hz)
        normal.addData3(0.0, 0.0, 1.0)
    center_top = vertex.getWriteRow()
    vertex.addData3(*top_c)
    normal.addData3(0.0, 0.0, 1.0)
    for i in range(n):
        tris.addVertices(center_top, top_i[i], top_i[(i + 1) % n])

    # Bottom fan (CW when viewed from above so normal faces −Z).
    bot_i = [0] * n
    for i, (x, y) in enumerate(ring):
        bot_i[i] = vertex.getWriteRow()
        vertex.addData3(x, y, -hz)
        normal.addData3(0.0, 0.0, -1.0)
    center_bot = vertex.getWriteRow()
    vertex.addData3(0.0, 0.0, -hz)
    normal.addData3(0.0, 0.0, -1.0)
    for i in range(n):
        tris.addVertices(center_bot, bot_i[(i + 1) % n], bot_i[i])

    # Side quads.
    for i in range(n):
        j = (i + 1) % n
        ax, ay = ring[i]
        bx, by = ring[j]
        nx, ny = face_normal((ax, ay, -hz), (bx, by, -hz), (bx, by, hz))[:2]
        # Renormalize XY normal (sides are vertical).
        length = math.hypot(nx, ny) or 1.0
        nx, ny = nx / length, ny / length
        base = vertex.getWriteRow()
        for x, y, z in (
            (ax, ay, -hz),
            (bx, by, -hz),
            (bx, by, hz),
            (ax, ay, hz),
        ):
            vertex.addData3(x, y, z)
            normal.addData3(nx, ny, 0.0)
        tris.addVertices(base, base + 1, base + 2)
        tris.addVertices(base, base + 2, base + 3)

    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("chamfer_box")
    node.addGeom(geom)
    return node


def make_cylinder(
    radius: float,
    length: float,
    segments: int = 10,
) -> GeomNode:
    """Solid cylinder centred on the origin, axis along +Y."""
    if segments < 5:
        raise ValueError("segments must be at least 5")
    hy = length / 2.0
    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("cylinder", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    # Side strip.
    for i in range(segments):
        a0 = (2.0 * math.pi) * (i / segments)
        a1 = (2.0 * math.pi) * ((i + 1) / segments)
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        # Circle in XZ; +Y is the axle.
        p00 = (radius * c0, -hy, radius * s0)
        p10 = (radius * c1, -hy, radius * s1)
        p11 = (radius * c1, hy, radius * s1)
        p01 = (radius * c0, hy, radius * s0)
        n0 = (c0, 0.0, s0)
        n1 = (c1, 0.0, s1)
        base = vertex.getWriteRow()
        for p, n in ((p00, n0), (p10, n1), (p11, n1), (p01, n0)):
            vertex.addData3(*p)
            normal.addData3(*n)
        tris.addVertices(base, base + 1, base + 2)
        tris.addVertices(base, base + 2, base + 3)

    # Caps.
    for y, nz in ((-hy, -1.0), (hy, 1.0)):
        center = vertex.getWriteRow()
        vertex.addData3(0.0, y, 0.0)
        normal.addData3(0.0, nz, 0.0)
        rim = []
        for i in range(segments):
            a = (2.0 * math.pi) * (i / segments)
            rim.append(vertex.getWriteRow())
            vertex.addData3(radius * math.cos(a), y, radius * math.sin(a))
            normal.addData3(0.0, nz, 0.0)
        for i in range(segments):
            j = (i + 1) % segments
            if nz > 0:
                tris.addVertices(center, rim[i], rim[j])
            else:
                tris.addVertices(center, rim[j], rim[i])

    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("cylinder")
    node.addGeom(geom)
    return node


def z_cylinder_instance(
    parent: NodePath,
    radius: float,
    height: float,
    segments: int = 12,
) -> NodePath:
    """Vertical cylinder (axis +Z), centred on the origin."""
    key = (radius, height, segments)
    template = Z_CYLINDER_TEMPLATES.get(key)
    if template is None:
        template = NodePath(make_z_cylinder(radius, height, segments=segments))
        Z_CYLINDER_TEMPLATES[key] = template
    return template.copyTo(parent)


def cone_instance(
    parent: NodePath,
    radius: float,
    height: float,
    segments: int = 12,
) -> NodePath:
    """Cone with base on z=0 and apex at z=height (centred in XY)."""
    key = (radius, height, segments)
    template = CONE_TEMPLATES.get(key)
    if template is None:
        template = NodePath(make_cone(radius, height, segments=segments))
        CONE_TEMPLATES[key] = template
    return template.copyTo(parent)


def make_z_cylinder(
    radius: float,
    height: float,
    segments: int = 12,
) -> GeomNode:
    """Solid cylinder centred on the origin, axis along +Z."""
    if segments < 5:
        raise ValueError("segments must be at least 5")
    hz = height / 2.0
    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("z_cylinder", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    for i in range(segments):
        a0 = (2.0 * math.pi) * (i / segments)
        a1 = (2.0 * math.pi) * ((i + 1) / segments)
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        p00 = (radius * c0, radius * s0, -hz)
        p10 = (radius * c1, radius * s1, -hz)
        p11 = (radius * c1, radius * s1, hz)
        p01 = (radius * c0, radius * s0, hz)
        n0 = (c0, s0, 0.0)
        n1 = (c1, s1, 0.0)
        base = vertex.getWriteRow()
        for p, n in ((p00, n0), (p10, n1), (p11, n1), (p01, n0)):
            vertex.addData3(*p)
            normal.addData3(*n)
        tris.addVertices(base, base + 1, base + 2)
        tris.addVertices(base, base + 2, base + 3)

    for z, nz in ((-hz, -1.0), (hz, 1.0)):
        center = vertex.getWriteRow()
        vertex.addData3(0.0, 0.0, z)
        normal.addData3(0.0, 0.0, nz)
        rim = []
        for i in range(segments):
            a = (2.0 * math.pi) * (i / segments)
            rim.append(vertex.getWriteRow())
            vertex.addData3(radius * math.cos(a), radius * math.sin(a), z)
            normal.addData3(0.0, 0.0, nz)
        for i in range(segments):
            j = (i + 1) % segments
            if nz > 0:
                tris.addVertices(center, rim[i], rim[j])
            else:
                tris.addVertices(center, rim[j], rim[i])

    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("z_cylinder")
    node.addGeom(geom)
    return node


def make_cone(
    radius: float,
    height: float,
    segments: int = 12,
) -> GeomNode:
    """Cone: base disc in z=0, apex at (0,0,height)."""
    if segments < 5:
        raise ValueError("segments must be at least 5")
    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("cone", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)
    apex = (0.0, 0.0, height)
    # Side slope length for outward normals.
    slope = math.hypot(radius, height) or 1.0
    for i in range(segments):
        a0 = (2.0 * math.pi) * (i / segments)
        a1 = (2.0 * math.pi) * ((i + 1) / segments)
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        p0 = (radius * c0, radius * s0, 0.0)
        p1 = (radius * c1, radius * s1, 0.0)
        # Normal blends radial with up along the slant.
        n0 = (c0 * height / slope, s0 * height / slope, radius / slope)
        n1 = (c1 * height / slope, s1 * height / slope, radius / slope)
        na = (
            (n0[0] + n1[0]) * 0.5,
            (n0[1] + n1[1]) * 0.5,
            (n0[2] + n1[2]) * 0.5,
        )
        base = vertex.getWriteRow()
        for p, n in ((p0, n0), (p1, n1), (apex, na)):
            vertex.addData3(*p)
            normal.addData3(*n)
        tris.addVertices(base, base + 1, base + 2)

    # Base cap (down).
    center = vertex.getWriteRow()
    vertex.addData3(0.0, 0.0, 0.0)
    normal.addData3(0.0, 0.0, -1.0)
    rim = []
    for i in range(segments):
        a = (2.0 * math.pi) * (i / segments)
        rim.append(vertex.getWriteRow())
        vertex.addData3(radius * math.cos(a), radius * math.sin(a), 0.0)
        normal.addData3(0.0, 0.0, -1.0)
    for i in range(segments):
        j = (i + 1) % segments
        tris.addVertices(center, rim[j], rim[i])

    tris.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("cone")
    node.addGeom(geom)
    return node


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
    # Stepped hall: lower wings + taller centre bay so it isn't one slab.
    wing_h = height * 0.72
    body = box_instance(root, sx, sy, wing_h)
    body.setPos(0.0, 0.0, bottom_z + wing_h / 2)
    body.setMaterial(factory_material(0.92), 1)
    centre = box_instance(root, sx * 0.45, sy * 0.7, height)
    centre.setPos(0.0, 0.0, bottom_z + height / 2)
    centre.setMaterial(factory_material(0.88), 1)

    # Cornice lip and dark roof deck on the factory hall.
    roof_z = bottom_z + height
    cornice = box_instance(root, sx * 0.5, sy * 0.75, 0.2)
    cornice.setPos(0.0, 0.0, roof_z + 0.08)
    cornice.setMaterial(factory_material(0.78), 1)
    deck = box_instance(root, sx * 0.42, sy * 0.62, 0.12)
    deck.setPos(0.0, 0.0, roof_z + 0.2)
    deck.setMaterial(roof_material(), 1)
    # Lower wing roofs.
    for sign in (-1.0, 1.0):
        wing_roof = box_instance(root, sx * 0.28, sy + 0.15, 0.14)
        wing_roof.setPos(sign * sx * 0.36, 0.0, bottom_z + wing_h + 0.05)
        wing_roof.setMaterial(roof_material(), 1)

    sooty = stack_material()
    for stack_x in (-sx / 5, sx / 5):
        stack = z_cylinder_instance(root, 0.65, 5.0, segments=8)
        stack.setPos(stack_x, sy * 0.15, roof_z + 0.3 + 2.5)
        stack.setMaterial(sooty, 1)
        cap = cone_instance(root, 0.7, 0.55, segments=8)
        cap.setPos(stack_x, sy * 0.15, roof_z + 5.3)
        cap.setMaterial(sooty, 1)

    root.flattenStrong()
    FACTORY_TEMPLATES[key] = root
    return root


def car_template() -> NodePath:
    """Sedan with tapered nose/cabin. Origin at centre; +X is forward.

    Keeps the ~2×1 footprint used by traffic spacing. Body parts are flattened;
    corner lamps stay named children so turn signals can blink independently.
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
        *,
        pitch: float = 0.0,
        chamfer: float | None = None,
    ) -> NodePath:
        if chamfer is not None:
            box = chamfer_box_instance(parent, sx, sy, sz, chamfer=chamfer)
        else:
            box = box_instance(parent, sx, sy, sz)
        box.setPos(x, y, z)
        if pitch:
            box.setP(pitch)
        box.setMaterial(material, 1)
        if name is not None:
            box.setName(name)
        return box

    # Lower hull: chamfered so the rocker isn't a brick.
    part(body_np, 1.78, 0.88, 0.26, 0.04, 0.0, -0.24, body, chamfer=0.12)
    # Shoulder / belt — slightly wider, soft corners.
    part(body_np, 1.62, 0.96, 0.2, -0.02, 0.0, -0.02, body, chamfer=0.14)
    # Cabin greenhouse, inset and chamfered.
    part(body_np, 0.82, 0.82, 0.3, -0.22, 0.0, 0.22, body, chamfer=0.1)
    # Trunk deck with a soft rear taper.
    trunk = body_np.attachNewNode(make_wedge(0.5, 0.88, 0.16))
    trunk.setPos(-0.72, 0.0, 0.04)
    trunk.setH(180.0)
    trunk.setMaterial(body, 1)
    # Long hood wedge toward a pointed nose.
    hood = body_np.attachNewNode(make_wedge(0.85, 0.9, 0.24))
    hood.setPos(0.42, 0.0, 0.0)
    hood.setMaterial(body, 1)

    # Windshield / backlight as wedges so slopes don't spear through the roof.
    windshield = detail.attachNewNode(make_wedge(0.36, 0.76, 0.28))
    windshield.setPos(0.2, 0.0, 0.24)
    windshield.setMaterial(glass, 1)
    backlight = detail.attachNewNode(make_wedge(0.3, 0.76, 0.22))
    backlight.setPos(-0.56, 0.0, 0.2)
    backlight.setH(180.0)
    backlight.setMaterial(glass, 1)
    for side in (-1.0, 1.0):
        part(detail, 0.62, 0.04, 0.22, -0.2, side * 0.43, 0.22, glass)
        # Soft wheel-arch lips.
        part(detail, 0.32, 0.05, 0.16, 0.5, side * 0.47, -0.2, trim, chamfer=0.04)
        part(detail, 0.32, 0.05, 0.16, -0.48, side * 0.47, -0.2, trim, chamfer=0.04)

    # Rounded-ish bumpers (chamfered bars).
    part(detail, 0.1, 0.92, 0.14, 0.96, 0.0, -0.26, trim, chamfer=0.04)
    part(detail, 0.1, 0.92, 0.14, -0.96, 0.0, -0.26, trim, chamfer=0.04)
    part(detail, 0.05, 0.42, 0.08, 0.9, 0.0, -0.12, trim)
    for side in (-1.0, 1.0):
        part(detail, 0.1, 0.08, 0.07, 0.2, side * 0.5, 0.1, trim)

    # Cylindrical tires + hub caps.
    for wx, wy in ((0.52, 0.44), (0.52, -0.44), (-0.5, 0.44), (-0.5, -0.44)):
        tire = cylinder_instance(detail, 0.17, 0.14, segments=6)
        tire.setPos(wx, wy, -0.34)
        tire.setMaterial(wheel, 1)
        hub = cylinder_instance(detail, 0.09, 0.15, segments=6)
        hub.setPos(wx, wy, -0.34)
        hub.setMaterial(trim, 1)

    body_np.flattenStrong()
    detail.flattenStrong()

    # +Y is the car's left; -Y is right. Lamps stay unflattened for signalling.
    for side, label in ((1.0, "left"), (-1.0, "right")):
        part(
            root, 0.08, 0.14, 0.1, 0.95, side * 0.3, -0.1, headlight,
            f"headlight-{label}",
            chamfer=0.02,
        )
        part(
            root, 0.08, 0.14, 0.09, -0.95, side * 0.3, -0.08, taillight,
            f"taillight-{label}",
            chamfer=0.02,
        )

    CAR_TEMPLATE = root
    return root


def make_wedge(sx: float, sy: float, sz: float) -> GeomNode:
    """Hood-style wedge: full height at −X, tapers to the bottom edge at +X.

    Origin-centred; +X is forward (toward the thin nose).
    """
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    # Bottom rectangle + tall top edge at the cabin (−X).
    b0 = (-hx, -hy, -hz)
    b1 = (hx, -hy, -hz)
    b2 = (hx, hy, -hz)
    b3 = (-hx, hy, -hz)
    t0 = (-hx, -hy, hz)
    t1 = (-hx, hy, hz)

    faces: tuple[tuple[tuple[float, float, float], ...], ...] = (
        (b0, b3, t1, t0),  # tall cabin end
        (t0, t1, b2, b1),  # sloping top
        (b0, t0, b1),  # −Y side
        (b3, b2, t1),  # +Y side
        (b0, b1, b2, b3),  # bottom
    )

    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("wedge", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    for face in faces:
        n = face_normal(face[0], face[1], face[2])
        start = vertex.getWriteRow()
        for corner in face:
            vertex.addData3(*corner)
            normal.addData3(*n)
        tris.addVertices(start, start + 1, start + 2)
        if len(face) == 4:
            tris.addVertices(start, start + 2, start + 3)
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("wedge")
    node.addGeom(geom)
    return node


def make_gable_roof(sx: float, sy: float, height: float) -> GeomNode:
    """Gable roof: ridge along X, eaves along ±Y. Base on z = 0, centred."""
    hx, hy = sx / 2.0, sy / 2.0
    e_fl = (-hx, -hy, 0.0)
    e_fr = (hx, -hy, 0.0)
    e_bl = (-hx, hy, 0.0)
    e_br = (hx, hy, 0.0)
    r_l = (-hx, 0.0, height)
    r_r = (hx, 0.0, height)

    faces: tuple[tuple[tuple[float, float, float], ...], ...] = (
        (e_fl, e_fr, r_r, r_l),  # front slope (−Y)
        (e_br, e_bl, r_l, r_r),  # back slope (+Y)
        (e_fl, r_l, e_bl),  # −X gable
        (e_fr, e_br, r_r),  # +X gable
        (e_fl, e_bl, e_br, e_fr),  # underside
    )

    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("gable", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    for face in faces:
        n = face_normal(face[0], face[1], face[2])
        start = vertex.getWriteRow()
        for corner in face:
            vertex.addData3(*corner)
            normal.addData3(*n)
        tris.addVertices(start, start + 1, start + 2)
        if len(face) == 4:
            tris.addVertices(start, start + 2, start + 3)
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("gable")
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
        add_face(corners, face_normal(*corners))
    add_face((base[3], base[2], base[1], base[0]), (0.0, 0.0, -1.0))
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("pyramid")
    node.addGeom(geom)
    return node


def _equilateral_xy(side: float) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Centroid-centred equilateral triangle in XY (point toward +Y)."""
    h = math.sqrt(3.0) * 0.5 * side
    return (
        (0.0, (2.0 / 3.0) * h),
        (-0.5 * side, -(1.0 / 3.0) * h),
        (0.5 * side, -(1.0 / 3.0) * h),
    )


def make_tri_prism(side: float, height: float) -> GeomNode:
    """Equilateral triangular prism, centroid at origin, extruded ±height/2 on Z."""
    hz = height / 2.0
    p0, p1, p2 = _equilateral_xy(side)
    bot = ((p0[0], p0[1], -hz), (p1[0], p1[1], -hz), (p2[0], p2[1], -hz))
    top = ((p0[0], p0[1], hz), (p1[0], p1[1], hz), (p2[0], p2[1], hz))

    faces: tuple[tuple[tuple[float, float, float], ...], ...] = (
        (bot[0], bot[2], bot[1]),  # bottom (outward −Z)
        (top[0], top[1], top[2]),  # top
        (bot[0], bot[1], top[1], top[0]),
        (bot[1], bot[2], top[2], top[1]),
        (bot[2], bot[0], top[0], top[2]),
    )

    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("tri_prism", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    for face in faces:
        n = face_normal(face[0], face[1], face[2])
        start = vertex.getWriteRow()
        for corner in face:
            vertex.addData3(*corner)
            normal.addData3(*n)
        tris.addVertices(start, start + 1, start + 2)
        if len(face) == 4:
            tris.addVertices(start, start + 2, start + 3)
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("tri_prism")
    node.addGeom(geom)
    return node


def make_tri_pyramid(side: float, height: float) -> GeomNode:
    """Equilateral triangular pyramid. Base on z=0, apex at z=height."""
    p0, p1, p2 = _equilateral_xy(side)
    base = ((p0[0], p0[1], 0.0), (p1[0], p1[1], 0.0), (p2[0], p2[1], 0.0))
    apex = (0.0, 0.0, height)
    sides = (
        (base[0], base[1], apex),
        (base[1], base[2], apex),
        (base[2], base[0], apex),
    )

    fmt = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData("tri_pyramid", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    tris = GeomTriangles(Geom.UHStatic)

    def add_face(
        corners: tuple[tuple[float, float, float], ...],
        n: tuple[float, float, float],
    ) -> None:
        start = vertex.getWriteRow()
        for corner in corners:
            vertex.addData3(*corner)
            normal.addData3(*n)
        tris.addVertices(start, start + 1, start + 2)

    for corners in sides:
        add_face(corners, face_normal(*corners))
    add_face((base[0], base[2], base[1]), (0.0, 0.0, -1.0))
    tris.closePrimitive()

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("tri_pyramid")
    node.addGeom(geom)
    return node


def tri_prism_instance(parent: NodePath, side: float, height: float) -> NodePath:
    key = (side, height)
    template = TRI_PRISM_TEMPLATES.get(key)
    if template is None:
        template = NodePath(make_tri_prism(side, height))
        TRI_PRISM_TEMPLATES[key] = template
    return template.copyTo(parent)


def tri_pyramid_instance(parent: NodePath, side: float, height: float) -> NodePath:
    key = (side, height)
    template = TRI_PYRAMID_TEMPLATES.get(key)
    if template is None:
        template = NodePath(make_tri_pyramid(side, height))
        TRI_PYRAMID_TEMPLATES[key] = template
    return template.copyTo(parent)


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

