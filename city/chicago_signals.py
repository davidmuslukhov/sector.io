"""Chicago-style traffic signals + intersection pavement markings."""

from __future__ import annotations

import math
from collections import defaultdict

from panda3d.core import NodePath

from city.materials import (
    SIGNAL_WAVE_GROUPS,
    mark_material,
    signal_lens_material,
    signal_material,
)
from city.mesh import arterial_junctions, box_instance, z_cylinder_instance

# Spatial tiles for static flattenStrong batching (same 2-mile cells as minors).
_TILE = 84.4

LOOP_X0, LOOP_X1 = -42.2, 16.0
LOOP_Y0, LOOP_Y1 = -63.3, 42.2

# Geometry (2× road plate).
_CORNER = 0.38
_POLE_H = 0.45
_POLE_R = 0.025
_MAST_H = 0.65
_MAST_LEN = 0.32
_HEAD_W = 0.055
_HEAD_D = 0.04
_HEAD_H = 0.14
_LENS = 0.032
_PED_Z = 0.22
_STOP_BACK = 0.45
_STOP_W = 0.06
_XWALK_LEN = 0.16
_XWALK_BAR_W = 0.04
_MARK_H = 0.004
# Match make_flat_deck_batch(top_only=True): surface = zc - hz + 0.002
_DECK_TOP_BIAS = 0.002
_MARK_LIFT = 0.001


def _wave_id(x: float, y: float) -> int:
    offset = (abs(x) + abs(y)) * 0.015
    return int(offset % SIGNAL_WAVE_GROUPS)


def _is_signal_route(arterial: dict) -> bool:
    layer = str(arterial.get("layer", "arterial"))
    if layer == "expressway":
        return False
    if layer == "minor":
        return False
    # Arterials + collectors (+ Loop streets tagged arterial).
    return layer in ("arterial", "collector")


def detect_signal_junctions(arterials: list[dict]) -> list[dict]:
    """Arterial×arterial, arterial×collector, and Loop crossings (no expressways)."""
    signal_routes = [a for a in arterials if _is_signal_route(a)]
    raw = arterial_junctions(signal_routes, merge=1.25)
    out: list[dict] = []
    by_name = {str(a.get("name", "")): a for a in signal_routes}
    for junc in raw:
        roads = junc["roads"]
        layers = []
        widths = []
        for name in roads:
            route = by_name.get(name)
            if route is None:
                continue
            layers.append(str(route.get("layer", "arterial")))
            widths.append(float(route.get("width", 0.55)))
        if not layers or any(layer == "expressway" for layer in layers):
            continue
        # Need at least one arterial (or Loop street) in the crossing.
        if not any(layer == "arterial" for layer in layers):
            # Collector×collector only — skip.
            if "collector" in layers and layers.count("collector") == len(layers):
                continue
        z_offs = []
        for name in roads:
            route = by_name.get(name)
            if route is not None:
                z_offs.append(float(route.get("z_offset", 0.02)))
        junc = dict(junc)
        junc["widths"] = widths
        junc["max_width"] = max(widths) if widths else 0.55
        junc["z_offset"] = max(z_offs) if z_offs else 0.02
        junc["wave"] = _wave_id(junc["x"], junc["y"])
        # Primary arterial axis: prefer wider road; tie → north-south arms.
        junc["primary_ns"] = _primary_is_ns(junc)
        out.append(junc)
    return out


def _paint_z(road_z: float, road_thickness: float, z_offset: float) -> float:
    """Centre Z for paint boxes sitting flush on a top_only arterial deck."""
    zc = road_z + z_offset
    hz = road_thickness * 0.5
    surface = zc - hz + _DECK_TOP_BIAS
    return surface + _MARK_H * 0.5 + _MARK_LIFT


def _primary_is_ns(junc: dict) -> bool:
    arms = junc.get("arms") or ()
    ns = sum(1 for ux, uy in arms if abs(uy) >= abs(ux))
    ew = len(arms) - ns
    # Slight preference for N–S when equal (State / Western spines).
    return ns >= ew


def _add_signal_head(
    parent: NodePath,
    x: float,
    y: float,
    z: float,
    *,
    face_x: float,
    face_y: float,
    axis: str,
    wave: int,
    housing,
    trim,
) -> None:
    """Vertical 3-lens head facing ``(face_x, face_y)``."""
    root = parent.attachNewNode("signal-head")
    root.setPos(x, y, z)
    root.lookAt(face_x, face_y, z)
    board = box_instance(root, _HEAD_W * 1.35, 0.012, _HEAD_H * 1.08)
    board.setPos(0.0, -_HEAD_D * 0.55, 0.0)
    board.setMaterial(trim, 1)
    head = box_instance(root, _HEAD_W, _HEAD_D, _HEAD_H)
    head.setMaterial(housing, 1)
    colours = ("red", "amber", "green")
    gap = 0.008
    span = 3 * _LENS + 2 * gap
    for index, name in enumerate(colours):
        lz = span * 0.5 - _LENS * 0.5 - index * (_LENS + gap)
        lens = box_instance(root, _LENS, 0.012, _LENS)
        lens.setPos(0.0, _HEAD_D * 0.5 + 0.006, lz)
        # Keep lighting on: LightOff ignores MaterialAttrib and forces white.
        lens.setMaterial(signal_lens_material(name, axis, wave), 1)


def _add_pedestal(
    parent: NodePath,
    jx: float,
    jy: float,
    sx: float,
    sy: float,
    *,
    road_z: float,
    wave: int,
    mast: bool,
    primary_ns: bool,
    housing,
    pole_mat,
) -> None:
    """Corner pedestal; optional mast arm over the primary arterial."""
    px = jx + sx * _CORNER
    py = jy + sy * _CORNER
    # Face the approach that this corner stops (into the intersection).
    # NW (-,+): faces southbound? Use face toward junction center for simplicity,
    # then axis from approach direction.
    # Pedestal head faces the traffic arriving along the secondary curb.
    # For NE (+,+): faces westbound EW traffic (look toward -X) and/or southbound.
    # Spec: "facing oncoming traffic" — use the axis of the nearer road edge.
    if abs(sx) >= abs(sy):
        # Prefer facing E/W approach (look toward junction along X).
        face_x, face_y = jx, py
        axis = "ew"
    else:
        face_x, face_y = px, jy
        axis = "ns"
    # Better: dual-readability — face approaching traffic on the primary if mast.
    if mast:
        if primary_ns:
            # Mast over N–S lanes: head faces south or north into traffic.
            face_x, face_y = px, jy - sy * 2.0
            axis = "ns"
        else:
            face_x, face_y = jx - sx * 2.0, py
            axis = "ew"
    else:
        # Pedestal faces the cross street approach.
        if primary_ns:
            face_x, face_y = jx - sx * 2.0, py
            axis = "ew"
        else:
            face_x, face_y = px, jy - sy * 2.0
            axis = "ns"

    pole_h = _MAST_H if mast else _POLE_H
    pole = z_cylinder_instance(parent, _POLE_R, pole_h, segments=8)
    pole.setPos(px, py, road_z + pole_h * 0.5)
    pole.setMaterial(pole_mat, 1)

    # Pedestrian walk/don't-walk box halfway up.
    ped = box_instance(parent, 0.04, 0.02, 0.05)
    ped.setPos(px + sx * 0.03, py + sy * 0.03, road_z + _PED_Z)
    ped.setMaterial(housing, 1)

    head_z = road_z + pole_h - 0.02
    _add_signal_head(
        parent,
        px,
        py,
        head_z,
        face_x=face_x,
        face_y=face_y,
        axis=axis,
        wave=wave,
        housing=housing,
        trim=pole_mat,
    )

    if not mast:
        return
    # Horizontal mast arm out over the driving lane.
    if primary_ns:
        # Arm extends along ±X toward the N–S roadway center.
        arm_len = _MAST_LEN
        arm = box_instance(parent, arm_len, _POLE_R * 1.6, _POLE_R * 1.6)
        arm.setPos(px - sx * arm_len * 0.5, py, road_z + _MAST_H)
        arm.setMaterial(pole_mat, 1)
        tip_x = px - sx * arm_len
        tip_y = py
        tip_face_x, tip_face_y = tip_x, jy - sy * 2.0
        tip_axis = "ns"
    else:
        arm_len = _MAST_LEN
        arm = box_instance(parent, _POLE_R * 1.6, arm_len, _POLE_R * 1.6)
        arm.setPos(px, py - sy * arm_len * 0.5, road_z + _MAST_H)
        arm.setMaterial(pole_mat, 1)
        tip_x = px
        tip_y = py - sy * arm_len
        tip_face_x, tip_face_y = jx - sx * 2.0, tip_y
        tip_axis = "ew"
    # Drop pipe + tip head.
    drop = box_instance(parent, _POLE_R * 0.9, _POLE_R * 0.9, 0.06)
    drop.setPos(tip_x, tip_y, road_z + _MAST_H - 0.04)
    drop.setMaterial(pole_mat, 1)
    _add_signal_head(
        parent,
        tip_x,
        tip_y,
        road_z + _MAST_H - 0.12,
        face_x=tip_face_x,
        face_y=tip_face_y,
        axis=tip_axis,
        wave=wave,
        housing=housing,
        trim=pole_mat,
    )


def _add_markings(
    parent: NodePath,
    junc: dict,
    *,
    paint,
    road_z: float,
    road_thickness: float,
) -> None:
    """Stop bars + continental crosswalks on all approaches."""
    jx, jy = float(junc["x"]), float(junc["y"])
    half = float(junc.get("max_width", 0.55)) * 0.5
    z = _paint_z(road_z, road_thickness, float(junc.get("z_offset", 0.02)))
    # Approaches: +Y, -Y, +X, -X (outward from center).
    approaches = (
        (0.0, 1.0, True),
        (0.0, -1.0, True),
        (1.0, 0.0, False),
        (-1.0, 0.0, False),
    )
    for ux, uy, ns_approach in approaches:
        # Stop bar center 0.45 back from intersection center.
        bx = jx + ux * _STOP_BACK
        by = jy + uy * _STOP_BACK
        # Span right-hand half of the approach width.
        span = half
        if ns_approach:
            # Bar along X; right-hand lanes are +X for northbound (+Y), -X for southbound.
            side = 1.0 if uy > 0 else -1.0
            bar = box_instance(parent, span, _STOP_W, _MARK_H)
            bar.setPos(bx + side * span * 0.5, by, z)
        else:
            side = 1.0 if ux > 0 else -1.0
            bar = box_instance(parent, _STOP_W, span, _MARK_H)
            bar.setPos(bx, by + side * span * 0.5, z)
        bar.setMaterial(paint, 1)

        # Continental ladder between stop bar and the intersection box.
        inner = half + 0.02
        outer = _STOP_BACK - _STOP_W * 0.5 - 0.02
        mid = 0.5 * (inner + outer)
        for k in range(5):
            # Bars perpendicular to the curb, spaced across the crosswalk width.
            t = (k - 2) * (_XWALK_BAR_W * 1.7)
            if ns_approach:
                streak = box_instance(parent, _XWALK_BAR_W, _XWALK_LEN, _MARK_H)
                streak.setPos(jx + t, jy + uy * mid, z)
            else:
                streak = box_instance(parent, _XWALK_LEN, _XWALK_BAR_W, _MARK_H)
                streak.setPos(jx + ux * mid, jy + t, z)
            streak.setMaterial(paint, 1)


def build_chicago_signals(
    parent: NodePath,
    arterials: list[dict],
    *,
    road_z: float = 0.0,
    road_thickness: float = 0.1,
) -> tuple[NodePath, list[dict], list[tuple[float, float, NodePath]]]:
    """Place Chicago signal assemblies + markings.

    Returns ``(root, junctions, tiles)`` where ``tiles`` is
    ``(cx, cy, node)`` for distance LOD.
    """
    junctions = detect_signal_junctions(arterials)
    root = parent.attachNewNode("chicago_signals")
    static_root = root.attachNewNode("signals_static")
    housing = signal_material("housing")
    pole_mat = signal_material("pole")
    paint = mark_material()

    tiles: dict[tuple[int, int], NodePath] = {}

    def tile_node(x: float, y: float) -> NodePath:
        key = (int(math.floor(x / _TILE)), int(math.floor(y / _TILE)))
        node = tiles.get(key)
        if node is None:
            node = static_root.attachNewNode(f"signals_tile_{key[0]}_{key[1]}")
            tiles[key] = node
        return node

    for junc in junctions:
        jx, jy = float(junc["x"]), float(junc["y"])
        wave = int(junc["wave"])
        primary_ns = bool(junc["primary_ns"])
        chunk = tile_node(jx, jy)
        # Spec: mast arms on the two far-side corners facing the primary arterial.
        if primary_ns:
            mast_corners = {(-1, 1), (1, 1)}
        else:
            mast_corners = {(1, -1), (1, 1)}

        for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            _add_pedestal(
                chunk,
                jx,
                jy,
                float(sx),
                float(sy),
                road_z=road_z,
                wave=wave,
                mast=(sx, sy) in mast_corners,
                primary_ns=primary_ns,
                housing=housing,
                pole_mat=pole_mat,
            )
        _add_markings(
            chunk,
            junc,
            paint=paint,
            road_z=road_z,
            road_thickness=road_thickness,
        )

    tile_list: list[tuple[float, float, NodePath]] = []
    for (tx, ty), node in tiles.items():
        node.flattenStrong()
        node.hide()
        cx = (tx + 0.5) * _TILE
        cy = (ty + 0.5) * _TILE
        tile_list.append((cx, cy, node))
    return root, junctions, tile_list
