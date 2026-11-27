"""Chicago Midway (MDW) and O'Hare (ORD) airfields at 2× map scale.

Clears residential fabric via shared voids in ``city.geo``, then lays turf,
runways, taxiways, markings, and low-poly terminals under two static parents
(``midway_airport_node`` / ``ohare_airport_node``) that are flattenStrong'd.
Returned as LOD tiles so overview / far camera drops them like housing.
"""

from __future__ import annotations

import math

from panda3d.core import NodePath

from city.collision2d import register_aabb, register_building
from city.geo import MIDWAY_VOID, OHARE_VOID
from city.materials import concrete_material, mark_material, rgba_material
from city.mesh import (
    box_instance,
    make_annulus_sector,
    make_flat_deck_batch,
)

# ---------------------------------------------------------------------------
# Materials / Z stack — keep to ≤4 states so flattenStrong stays few draw calls
# ---------------------------------------------------------------------------
TURF_RGBA = (0.18, 0.28, 0.16, 1.0)
ASPHALT_RGBA = (0.14, 0.15, 0.17, 1.0)
TERMINAL_RGBA = (0.72, 0.74, 0.76, 1.0)

TURF_Z = -0.05
RUNWAY_Z = 0.02
TAXI_Z = 0.025
MARK_Z = 0.027
TERMINAL_BASE_Z = 0.0
BRIDGE_Z = 0.45
ATS_Z = 0.50
ARRIVAL_Z = 0.12
DEPARTURE_Z = 0.28

DECK_THICK = 0.04
MARK_THICK = 0.02

# LOD tile centres / show radii (units) used by app._update_road_lod.
MIDWAY_LOD = (-274.3, -311.2, 55.0)
OHARE_LOD = (-535.0, 322.0, 120.0)


def _turf_pad(
    parent: NodePath,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    z: float = TURF_Z,
) -> None:
    sx = abs(x1 - x0)
    sy = abs(y1 - y0)
    pad = box_instance(parent, sx, sy, 0.06, top=True, bottom=False)
    pad.setPos((x0 + x1) * 0.5, (y0 + y1) * 0.5, z)
    pad.setMaterial(rgba_material(TURF_RGBA), 1)


def _deck(
    parent: NodePath,
    segs: list[tuple[float, float, float, float, float, float]],
    material,
    *,
    name: str,
    thickness: float = DECK_THICK,
) -> None:
    if not segs:
        return
    node = parent.attachNewNode(
        make_flat_deck_batch(segs, thickness, name=name, top_only=True)
    )
    node.setMaterial(material, 1)


def _box(
    parent: NodePath,
    cx: float,
    cy: float,
    sx: float,
    sy: float,
    sz: float,
    material,
    *,
    z0: float = TERMINAL_BASE_Z,
    collider: bool = True,
) -> None:
    body = box_instance(parent, sx, sy, sz)
    body.setPos(cx, cy, z0 + sz * 0.5)
    body.setMaterial(material, 1)
    if collider and sx > 0.4 and sy > 0.4:
        register_building(cx, cy, sx * 0.5, sy * 0.5, 0.0)


def _unit(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy) or 1.0
    return dx / length, dy / length


def _perp(ux: float, uy: float) -> tuple[float, float]:
    return -uy, ux


def _parallel_seg(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    offset: float,
) -> tuple[float, float, float, float]:
    ux, uy = _unit(x1 - x0, y1 - y0)
    nx, ny = _perp(ux, uy)
    return (
        x0 + nx * offset,
        y0 + ny * offset,
        x1 + nx * offset,
        y1 + ny * offset,
    )


def _centerline(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    width: float = 0.05,
    z: float = MARK_Z,
) -> list[tuple[float, float, float, float, float, float]]:
    """Single solid centre stripe — far cheaper than dashed segments."""
    return [(x0, y0, x1, y1, width, z)]


def _piano_keys(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    runway_w: float,
    *,
    z: float = MARK_Z,
) -> list[tuple[float, float, float, float, float, float]]:
    """White threshold bars at both runway ends (4 bars each)."""
    ux, uy = _unit(x1 - x0, y1 - y0)
    nx, ny = _perp(ux, uy)
    length = math.hypot(x1 - x0, y1 - y0)
    bar_len = min(1.2, length * 0.035)
    bar_w = 0.14
    n_bars = 4
    span = runway_w * 0.7
    segs: list[tuple[float, float, float, float, float, float]] = []
    for end in (0.0, 1.0):
        along = bar_len * 0.6 if end < 0.5 else length - bar_len * 0.6
        cx = x0 + ux * along
        cy = y0 + uy * along
        for i in range(n_bars):
            frac = (i + 0.5) / n_bars - 0.5
            ox = nx * frac * span
            oy = ny * frac * span
            ax = cx + ox - ux * bar_len * 0.5
            ay = cy + oy - uy * bar_len * 0.5
            bx = cx + ox + ux * bar_len * 0.5
            by = cy + oy + uy * bar_len * 0.5
            segs.append((ax, ay, bx, by, bar_w, z))
    return segs


def _flank_taxiways(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    runway_w: float,
    taxi_w: float,
    *,
    z: float = TAXI_Z,
) -> list[tuple[float, float, float, float, float, float]]:
    gap = runway_w * 0.5 + taxi_w * 0.5 + 0.35
    segs: list[tuple[float, float, float, float, float, float]] = []
    for sign in (-1.0, 1.0):
        a, b, c, d = _parallel_seg(x0, y0, x1, y1, sign * gap)
        segs.append((a, b, c, d, taxi_w, z))
    return segs


def _ring_deck(
    cx: float,
    cy: float,
    radius: float,
    width: float,
    z: float,
    *,
    segments: int = 16,
) -> list[tuple[float, float, float, float, float, float]]:
    """Approximate a circular track with short flat-deck chords (no wall verts)."""
    segs: list[tuple[float, float, float, float, float, float]] = []
    for i in range(segments):
        a0 = (2.0 * math.pi * i) / segments
        a1 = (2.0 * math.pi * (i + 1)) / segments
        segs.append(
            (
                cx + radius * math.cos(a0),
                cy + radius * math.sin(a0),
                cx + radius * math.cos(a1),
                cy + radius * math.sin(a1),
                width,
                z,
            )
        )
    return segs


# ---------------------------------------------------------------------------
# Midway (MDW)
# ---------------------------------------------------------------------------
def _build_midway(parent: NodePath) -> NodePath:
    node = parent.attachNewNode("midway_airport_node")
    x0, y0, x1, y1 = MIDWAY_VOID
    _turf_pad(node, x0, y0, x1, y1)

    asphalt = rgba_material(ASPHALT_RGBA)
    paint = mark_material()
    concrete = concrete_material()
    terminal_mat = rgba_material(TERMINAL_RGBA)

    runways = [
        (-292.0, -329.0, -256.5, -293.5, 1.1),
        (-293.0, -323.0, -262.0, -292.0, 0.85),
        (-292.0, -293.5, -256.5, -329.0, 1.1),
        (-286.0, -292.0, -256.5, -321.5, 0.85),
    ]

    asphalt_segs: list[tuple[float, float, float, float, float, float]] = []
    mark_segs: list[tuple[float, float, float, float, float, float]] = []
    for ax, ay, bx, by, w in runways:
        asphalt_segs.append((ax, ay, bx, by, w, RUNWAY_Z))
        asphalt_segs.extend(_flank_taxiways(ax, ay, bx, by, w, 0.55))
        mark_segs.extend(_centerline(ax, ay, bx, by))
        mark_segs.extend(_piano_keys(ax, ay, bx, by, w))

    asphalt_segs.append((-268.0, -316.0, -268.0, -304.0, 0.55, TAXI_Z))
    asphalt_segs.append((-268.0, -310.0, -254.5, -310.0, 0.55, TAXI_Z))
    asphalt_segs.append((-253.2, -311.2, -258.5, -311.2, 0.55, TAXI_Z))

    _deck(node, asphalt_segs, asphalt, name="midway_pavement")
    _deck(node, mark_segs, paint, name="midway_markings", thickness=MARK_THICK)

    _box(node, -258.0, -310.0, 8.0, 12.0, 0.35, terminal_mat)
    for cy, sy in ((-314.5, 3.2), (-310.0, 3.2), (-305.5, 3.2)):
        _box(node, -263.5, cy, 9.0, sy, 0.25, terminal_mat)
    _box(node, -268.0, -310.0, 1.6, 11.0, 0.22, terminal_mat)

    bridge = box_instance(node, 9.5, 2.4, 0.12)
    bridge.setPos(-249.0, -310.0, BRIDGE_Z)
    bridge.setMaterial(concrete, 1)
    for px in (-253.2, -248.0):
        pier = box_instance(node, 0.35, 0.55, BRIDGE_Z - 0.05)
        pier.setPos(px, -310.0, (BRIDGE_Z - 0.05) * 0.5)
        pier.setMaterial(concrete, 1)

    _box(node, -248.5, -310.0, 7.0, 10.0, 0.55, concrete)
    tower = box_instance(node, 0.55, 0.55, 1.1)
    tower.setPos(-260.5, -307.0, 0.55)
    tower.setMaterial(concrete, 1)

    node.flattenStrong()
    node.hide()
    return node


# ---------------------------------------------------------------------------
# O'Hare (ORD)
# ---------------------------------------------------------------------------
def _ohare_runways() -> list[tuple[float, float, float, float, float]]:
    w = 1.25
    return [
        (-582.0, 372.0, -518.0, 372.0, w),
        (-588.0, 358.0, -495.0, 358.0, w),
        (-575.0, 346.0, -502.0, 346.0, w),
        (-590.0, 312.0, -488.0, 312.0, w),
        (-588.0, 296.0, -496.0, 296.0, w),
        (-582.0, 280.0, -510.0, 280.0, w),
        (-535.0, 318.0, -498.0, 355.0, 1.1),
        (-522.0, 276.0, -485.0, 312.0, 1.1),
    ]


def _ohare_taxi_grid() -> list[tuple[float, float, float, float, float, float]]:
    w = 0.6
    z = TAXI_Z
    segs: list[tuple[float, float, float, float, float, float]] = []
    for y in (365.0, 352.0, 339.0, 304.0, 288.0):
        segs.append((-580.0, y, -500.0, y, w, z))
    for x in (-548.0, -536.0, -512.0, -500.0):
        segs.append((x, 280.0, x, 370.0, w, z))
    segs.append((-544.0, 318.0, -508.0, 318.0, w, z))
    segs.append((-544.0, 340.0, -508.0, 340.0, w, z))
    segs.append((-544.0, 318.0, -544.0, 340.0, w, z))
    segs.append((-508.0, 318.0, -508.0, 340.0, w, z))
    return segs


def _build_ohare_terminals(node: NodePath, asphalt, concrete, terminal_mat) -> None:
    horse = node.attachNewNode(
        make_annulus_sector(
            inner_radius=8.5,
            outer_radius=12.5,
            start_angle=math.pi * 0.5,
            end_angle=math.pi * 1.5,
            thickness=0.38,
            segments=14,
        )
    )
    horse.setPos(-524.0, 329.0, 0.19)
    horse.setMaterial(terminal_mat, 1)
    # Approximate horseshoe footprint for vehicle collision.
    register_aabb(-536.5, 316.5, -511.5, 341.5)

    _box(node, -536.0, 329.0, 2.2, 18.0, 0.28, terminal_mat)
    _box(node, -544.0, 329.0, 2.2, 18.0, 0.28, terminal_mat)
    _box(node, -540.0, 329.0, 6.0, 2.0, 0.12, concrete, z0=-0.02)

    _box(node, -528.0, 334.0, 10.0, 2.0, 0.28, terminal_mat)
    _box(node, -523.5, 338.0, 2.0, 8.0, 0.28, terminal_mat)
    _box(node, -518.0, 335.0, 8.0, 2.0, 0.28, terminal_mat)
    _box(node, -520.0, 326.0, 2.0, 7.0, 0.28, terminal_mat)
    _box(node, -526.0, 322.0, 9.0, 2.0, 0.28, terminal_mat)

    t5 = node.attachNewNode(
        make_annulus_sector(
            inner_radius=4.0,
            outer_radius=7.0,
            start_angle=-math.pi * 0.35,
            end_angle=math.pi * 0.35,
            thickness=0.32,
            segments=10,
        )
    )
    t5.setPos(-501.0, 332.0, 0.16)
    t5.setMaterial(terminal_mat, 1)
    _box(node, -501.0, 332.0, 6.0, 4.0, 0.28, terminal_mat)

    _box(node, -518.0, 329.0, 9.0, 8.0, 0.42, concrete)
    _box(node, -492.0, 355.0, 8.0, 6.0, 0.36, concrete)

    # ATS loop + spurs as top-only deck chords (no ribbon side walls).
    ats: list[tuple[float, float, float, float, float, float]] = []
    ats.extend(_ring_deck(-518.0, 329.0, 11.5, 0.25, ATS_Z, segments=16))
    ats.append((-506.5, 329.0, -496.0, 332.0, 0.25, ATS_Z))
    ats.append((-518.0, 340.5, -492.0, 355.0, 0.25, ATS_Z))
    _deck(node, ats, concrete, name="ohare_ats")

    for z, rad_in, rad_out in (
        (ARRIVAL_Z, 6.0, 7.2),
        (DEPARTURE_Z, 7.4, 8.6),
    ):
        loop = node.attachNewNode(
            make_annulus_sector(
                inner_radius=rad_in,
                outer_radius=rad_out,
                start_angle=-math.pi * 0.55,
                end_angle=math.pi * 0.55,
                thickness=0.08,
                segments=12,
            )
        )
        loop.setPos(-512.0, 329.0, z)
        loop.setMaterial(asphalt, 1)

    tower = box_instance(node, 0.7, 0.7, 1.6)
    tower.setPos(-528.0, 324.0, 0.8)
    tower.setMaterial(concrete, 1)


def _build_ohare(parent: NodePath) -> NodePath:
    node = parent.attachNewNode("ohare_airport_node")
    x0, y0, x1, y1 = OHARE_VOID
    _turf_pad(node, x0, y0, x1, y1)

    asphalt = rgba_material(ASPHALT_RGBA)
    paint = mark_material()
    concrete = concrete_material()
    terminal_mat = rgba_material(TERMINAL_RGBA)

    asphalt_segs = _ohare_taxi_grid()
    mark_segs: list[tuple[float, float, float, float, float, float]] = []
    for ax, ay, bx, by, w in _ohare_runways():
        asphalt_segs.append((ax, ay, bx, by, w, RUNWAY_Z))
        # Skip flank taxiways — the E–W/N–S grid already covers the field.
        mark_segs.extend(_centerline(ax, ay, bx, by))
        mark_segs.extend(_piano_keys(ax, ay, bx, by, w))

    _deck(node, asphalt_segs, asphalt, name="ohare_pavement")
    _deck(node, mark_segs, paint, name="ohare_markings", thickness=MARK_THICK)
    _build_ohare_terminals(node, asphalt, concrete, terminal_mat)

    node.flattenStrong()
    node.hide()
    return node


def build_chicago_airports(
    parent: NodePath,
) -> tuple[NodePath, list[tuple[float, float, float, NodePath]]]:
    """Build Midway + O'Hare. Returns ``(root, lod_tiles)``.

    Each LOD tile is ``(cx, cy, show_radius, node)`` — hidden until the camera
    look-point is nearby (see ``app._update_road_lod``).
    """
    root = parent.attachNewNode("chicago_airports")
    midway = _build_midway(root)
    ohare = _build_ohare(root)
    tiles = [
        (MIDWAY_LOD[0], MIDWAY_LOD[1], MIDWAY_LOD[2], midway),
        (OHARE_LOD[0], OHARE_LOD[1], OHARE_LOD[2], ohare),
    ]
    return root, tiles
