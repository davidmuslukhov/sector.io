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
    block_material,
    car_material,
    foliage_material,
    lamp_material,
    roof_material,
    square_lightness,
    square_material,
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
# Flattened factory buildings. Keyed by plan, height, and bottom z.
FACTORY_TEMPLATES: dict[tuple[float, float, float, float], NodePath] = {}
# Flattened blocky car mesh. Copied once per scene.
CAR_TEMPLATE: NodePath | None = None
TREE_TEMPLATE: NodePath | None = None
LAMP_TEMPLATE: NodePath | None = None


def make_sky_dome(
    radius: float = 900.0,
    *,
    rings: int = 4,
    sectors: int = 12,
) -> GeomNode:
    """Upper hemisphere with a zenith→horizon colour wash (no textures)."""
    # Cool zenith, warmer wash at the horizon.
    zenith = (0.35, 0.55, 0.85, 1.0)
    horizon = (0.72, 0.8, 0.9, 1.0)
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
        t = theta / (0.5 * math.pi)
        row = vertex.getWriteRow()
        vertex.addData3(x, y, z)
        color.addData4(
            zenith[0] + (horizon[0] - zenith[0]) * t,
            zenith[1] + (horizon[1] - zenith[1]) * t,
            zenith[2] + (horizon[2] - zenith[2]) * t,
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


def tree_template() -> NodePath:
    """Simple street tree: trunk + stacked canopy. Flattened for copyTo."""
    global TREE_TEMPLATE
    if TREE_TEMPLATE is not None:
        return TREE_TEMPLATE
    root = NodePath("tree")
    trunk = box_instance(root, 0.28, 0.28, 1.4)
    trunk.setPos(0.0, 0.0, 0.7)
    trunk.setMaterial(bark_material(), 1)
    # Three staggered canopy slabs ≈ a rounded crown without a sphere mesh.
    canopy = (
        (1.6, 1.6, 0.7, 1.85),
        (1.25, 1.25, 0.65, 2.35),
        (0.85, 0.85, 0.55, 2.75),
    )
    leaf = foliage_material()
    for sx, sy, sz, z in canopy:
        crown = box_instance(root, sx, sy, sz)
        crown.setPos(0.0, 0.0, z)
        crown.setMaterial(leaf, 1)
    root.flattenStrong()
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
    # Stepped hall: lower wings + taller centre bay so it isn't one slab.
    wing_h = height * 0.72
    body = box_instance(root, sx, sy, wing_h)
    body.setPos(0.0, 0.0, bottom_z + wing_h / 2)
    body.setMaterial(block_material(0.92), 1)
    centre = box_instance(root, sx * 0.45, sy * 0.7, height)
    centre.setPos(0.0, 0.0, bottom_z + height / 2)
    centre.setMaterial(block_material(0.88), 1)

    # Cornice lip and dark roof deck on the factory hall.
    roof_z = bottom_z + height
    cornice = box_instance(root, sx * 0.5, sy * 0.75, 0.2)
    cornice.setPos(0.0, 0.0, roof_z + 0.08)
    cornice.setMaterial(block_material(0.78), 1)
    deck = box_instance(root, sx * 0.42, sy * 0.62, 0.12)
    deck.setPos(0.0, 0.0, roof_z + 0.2)
    deck.setMaterial(roof_material(), 1)
    # Lower wing roofs.
    for sign in (-1.0, 1.0):
        wing_roof = box_instance(root, sx * 0.28, sy + 0.15, 0.14)
        wing_roof.setPos(sign * sx * 0.36, 0.0, bottom_z + wing_h + 0.05)
        wing_roof.setMaterial(roof_material(), 1)

    stack_size = (1.5, 1.5, 5.0)
    stack_z = roof_z + 0.3 + stack_size[2] / 2
    sooty = stack_material()
    for stack_x in (-sx / 5, sx / 5):
        stack = box_instance(root, *stack_size)
        stack.setPos(stack_x, sy * 0.15, stack_z)
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
    """Sedan-ish car. Origin at the bounding-box centre; +X is forward.

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
    ) -> NodePath:
        box = box_instance(parent, sx, sy, sz)
        box.setPos(x, y, z)
        if pitch:
            box.setP(pitch)
        box.setMaterial(material, 1)
        if name is not None:
            box.setName(name)
        return box

    # Rocker / lower hull — slightly narrower than the shoulder line.
    part(body_np, 1.82, 0.9, 0.28, 0.02, 0.0, -0.22, body)
    # Shoulder / belt line, a touch wider for a less cubic read.
    part(body_np, 1.7, 0.98, 0.22, 0.0, 0.0, -0.02, body)
    # Cabin greenhouse, inset from the belt.
    part(body_np, 0.88, 0.86, 0.32, -0.2, 0.0, 0.24, body)
    # Trunk deck behind the cabin.
    part(body_np, 0.42, 0.9, 0.14, -0.72, 0.0, 0.08, body)
    # Sloped hood wedge toward the nose.
    hood = body_np.attachNewNode(make_wedge(0.7, 0.92, 0.22))
    hood.setPos(0.48, 0.0, 0.02)
    hood.setMaterial(body, 1)

    # Windshield / backlight as wedges so slopes don't spear through the roof.
    windshield = detail.attachNewNode(make_wedge(0.32, 0.8, 0.3))
    windshield.setPos(0.22, 0.0, 0.26)
    windshield.setMaterial(glass, 1)
    backlight = detail.attachNewNode(make_wedge(0.28, 0.8, 0.24))
    backlight.setPos(-0.58, 0.0, 0.22)
    backlight.setH(180.0)  # tall end toward the cabin
    backlight.setMaterial(glass, 1)
    for side in (-1.0, 1.0):
        part(detail, 0.66, 0.04, 0.24, -0.18, side * 0.45, 0.24, glass)
        # Soft wheel-arch cue carved into the rocker.
        part(detail, 0.34, 0.06, 0.2, 0.52, side * 0.48, -0.22, trim)
        part(detail, 0.34, 0.06, 0.2, -0.5, side * 0.48, -0.22, trim)

    # Bumpers wrap slightly around the corners.
    part(detail, 0.12, 0.96, 0.16, 0.98, 0.0, -0.24, trim)
    part(detail, 0.12, 0.96, 0.16, -0.98, 0.0, -0.24, trim)
    part(detail, 0.05, 0.48, 0.1, 0.94, 0.0, -0.1, trim)
    for side in (-1.0, 1.0):
        part(detail, 0.12, 0.1, 0.08, 0.22, side * 0.52, 0.12, trim)

    # Tire + inset hub so wheels read as discs, not cubes.
    for wx, wy in ((0.55, 0.46), (0.55, -0.46), (-0.52, 0.46), (-0.52, -0.46)):
        part(detail, 0.34, 0.12, 0.34, wx, wy, -0.34, wheel)
        part(detail, 0.2, 0.14, 0.2, wx, wy, -0.34, trim)

    body_np.flattenStrong()
    detail.flattenStrong()

    # +Y is the car's left; -Y is right. Lamps stay unflattened for signalling.
    for side, label in ((1.0, "left"), (-1.0, "right")):
        part(
            root, 0.08, 0.16, 0.12, 0.98, side * 0.32, -0.08, headlight,
            f"headlight-{label}",
        )
        part(
            root, 0.08, 0.16, 0.1, -0.98, side * 0.32, -0.06, taillight,
            f"taillight-{label}",
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

