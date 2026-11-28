"""2D OBB collision world — SAT resolve for pursuit vehicles vs static blockers."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Category tags used by downtown highrises / CTA / housing registration helpers.
COLLIDER_BUILDING = 1
COLLIDER_HOUSE = 2
COLLIDER_PILLAR = 3
COLLIDER_PROP = 4

# Wall-slide response (shared by player + CPD cruisers).
WALL_RESTITUTION = 0.22
WALL_FRICTION = 0.88
STATIC_SOLVER_PASSES = 1

# Physics-grade vehicle half-extents (world units @ 42.2 u / mile).
PLAYER_HALF_L = 0.068
PLAYER_HALF_W = 0.032
COP_HALF_L = 0.071
COP_HALF_W = 0.033

_ACTIVE: CollisionWorld2D | None = None


def set_active_world(world: CollisionWorld2D | None) -> None:
    global _ACTIVE
    _ACTIVE = world


def get_active_world() -> CollisionWorld2D | None:
    return _ACTIVE


def register_static(
    cx: float,
    cy: float,
    half_x: float,
    half_y: float,
    yaw_deg: float,
    category: int,
) -> None:
    """No-op when no world is active (offline mesh builds / unit tests)."""
    world = _ACTIVE
    if world is None:
        return
    world.add_static(
        OBB2D(
            cx,
            cy,
            half_x,
            half_y,
            yaw_deg,
            tag=category,
        )
    )


def register_building(
    cx: float, cy: float, half_w: float, half_l: float, yaw_deg: float = 0.0
) -> None:
    register_static(cx, cy, half_w, half_l, yaw_deg, COLLIDER_BUILDING)


def register_house(
    cx: float, cy: float, half_w: float, half_l: float, yaw_deg: float = 0.0
) -> None:
    register_static(cx, cy, half_w, half_l, yaw_deg, COLLIDER_HOUSE)


def register_pillar(cx: float, cy: float, radius: float = 0.035) -> None:
    register_static(cx, cy, radius, radius, 0.0, COLLIDER_PILLAR)


def register_aabb(
    x0: float, y0: float, x1: float, y1: float, category: int = COLLIDER_BUILDING
) -> None:
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    register_static(cx, cy, abs(x1 - x0) * 0.5, abs(y1 - y0) * 0.5, 0.0, category)


def resolve_static_world_collisions(box: OBB2D, dt: float = 0.0) -> tuple[float, float]:
    """Module-level entry: resolve ``box`` against the active CollisionWorld2D."""
    del dt  # reserved for continuous sweeps; discrete SAT is frame-rate stable
    world = _ACTIVE
    if world is None:
        return 0.0, 0.0
    return world.resolve_static_world_collisions(box)


@dataclass
class OBB2D:
    """Oriented box in XY. ``heading`` is degrees from +X toward +Y (Panda H)."""

    x: float
    y: float
    half_l: float  # along forward axis
    half_w: float  # along left axis
    heading: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    tag: object = None

    def axes(self) -> tuple[tuple[float, float], tuple[float, float]]:
        rad = math.radians(self.heading)
        c, s = math.cos(rad), math.sin(rad)
        return (c, s), (-s, c)  # forward, left

    def corners(self) -> list[tuple[float, float]]:
        fx, fy = self.axes()[0]
        lx, ly = self.axes()[1]
        hl, hw = self.half_l, self.half_w
        return [
            (self.x + fx * hl + lx * hw, self.y + fy * hl + ly * hw),
            (self.x + fx * hl - lx * hw, self.y + fy * hl - ly * hw),
            (self.x - fx * hl - lx * hw, self.y - fy * hl - ly * hw),
            (self.x - fx * hl + lx * hw, self.y - fy * hl + ly * hw),
        ]

    def contains_point(self, px: float, py: float) -> bool:
        fx, fy = self.axes()[0]
        lx, ly = self.axes()[1]
        dx, dy = px - self.x, py - self.y
        return abs(dx * fx + dy * fy) <= self.half_l and abs(dx * lx + dy * ly) <= self.half_w


def _project(corners: list[tuple[float, float]], ax: float, ay: float) -> tuple[float, float]:
    dots = [cx * ax + cy * ay for cx, cy in corners]
    return min(dots), max(dots)


def sat_overlap(
    a: OBB2D, b: OBB2D
) -> tuple[float, float, float] | None:
    """Return (nx, ny, penetration) pushing A out of B, or None if separated."""
    ca, cb = a.corners(), b.corners()
    axes = (*a.axes(), *b.axes())
    best_pen = float("inf")
    best_n = (1.0, 0.0)
    for ax, ay in axes:
        al = math.hypot(ax, ay) or 1.0
        ux, uy = ax / al, ay / al
        amin, amax = _project(ca, ux, uy)
        bmin, bmax = _project(cb, ux, uy)
        if amax < bmin or bmax < amin:
            return None
        pen = min(amax - bmin, bmax - amin)
        if pen < best_pen:
            best_pen = pen
            # Normal should push A away from B.
            mid_a = 0.5 * (amin + amax)
            mid_b = 0.5 * (bmin + bmax)
            if mid_a < mid_b:
                best_n = (-ux, -uy)
            else:
                best_n = (ux, uy)
    if best_pen == float("inf") or best_pen <= 0.0:
        return None
    return best_n[0], best_n[1], best_pen


def _apply_wall_slide(box: OBB2D, nx: float, ny: float) -> None:
    """Strip inward normal speed, bounce lightly, scrape along the facade."""
    vn = box.vx * nx + box.vy * ny
    if vn >= 0.0:
        return
    tx = box.vx - vn * nx
    ty = box.vy - vn * ny
    box.vx = tx * WALL_FRICTION - WALL_RESTITUTION * vn * nx
    box.vy = ty * WALL_FRICTION - WALL_RESTITUTION * vn * ny


@dataclass
class CollisionWorld2D:
    """Spatial-hash OBB world for static props + dynamic vehicles."""

    cell: float = 5.275
    static: list[OBB2D] = field(default_factory=list)
    _static_grid: dict[tuple[int, int], list[int]] = field(default_factory=dict)
    dynamics: list[OBB2D] = field(default_factory=list)

    def clear_dynamics(self) -> None:
        self.dynamics.clear()

    def add_static(self, box: OBB2D) -> None:
        idx = len(self.static)
        self.static.append(box)
        self._insert_static(idx, box)

    def add_statics(self, boxes: list[OBB2D]) -> None:
        for box in boxes:
            self.add_static(box)

    def _insert_static(self, idx: int, box: OBB2D) -> None:
        cell = self.cell
        if cell <= 0.0:
            return
        pad = max(box.half_l, box.half_w) + 0.05
        i0 = int(math.floor((box.x - pad) / cell))
        i1 = int(math.floor((box.x + pad) / cell))
        j0 = int(math.floor((box.y - pad) / cell))
        j1 = int(math.floor((box.y + pad) / cell))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                self._static_grid.setdefault((i, j), []).append(idx)

    def nearby_static(self, x: float, y: float, radius: float) -> list[OBB2D]:
        cell = self.cell
        if not self._static_grid or cell <= 0.0:
            return list(self.static)
        i0 = int(math.floor((x - radius) / cell))
        i1 = int(math.floor((x + radius) / cell))
        j0 = int(math.floor((y - radius) / cell))
        j1 = int(math.floor((y + radius) / cell))
        seen: set[int] = set()
        out: list[OBB2D] = []
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                for idx in self._static_grid.get((i, j), ()):
                    if idx not in seen:
                        seen.add(idx)
                        out.append(self.static[idx])
        return out

    def nearby_static_3x3(self, x: float, y: float) -> list[OBB2D]:
        """Static OBBs in the 3×3 block cells around ``(x, y)``."""
        cell = self.cell
        if not self._static_grid or cell <= 0.0:
            return list(self.static)
        ci = int(math.floor(x / cell))
        cj = int(math.floor(y / cell))
        seen: set[int] = set()
        out: list[OBB2D] = []
        for i in range(ci - 1, ci + 2):
            for j in range(cj - 1, cj + 2):
                for idx in self._static_grid.get((i, j), ()):
                    if idx not in seen:
                        seen.add(idx)
                        out.append(self.static[idx])
        return out

    def register_dynamic(self, box: OBB2D) -> None:
        self.dynamics.append(box)

    def resolve_static_world_collisions(
        self, box: OBB2D, *, iterations: int = STATIC_SOLVER_PASSES
    ) -> tuple[float, float]:
        """SAT depenetration + wall-slide against the 3×3 static neighbourhood.

        Two solver passes so inside corners (storefront + greystone, alley garage)
        resolve cleanly without jitter. Mutates ``box`` position and velocity.
        Returns the last contact normal, or (0, 0).
        """
        hit_nx = hit_ny = 0.0
        for _ in range(iterations):
            deepest: tuple[float, float, float] | None = None
            for other in self.nearby_static_3x3(box.x, box.y):
                hit = sat_overlap(box, other)
                if hit is None:
                    continue
                if deepest is None or hit[2] > deepest[2]:
                    deepest = hit
            if deepest is None:
                break
            nx, ny, pen = deepest
            box.x += nx * pen
            box.y += ny * pen
            _apply_wall_slide(box, nx, ny)
            hit_nx, hit_ny = nx, ny
        return hit_nx, hit_ny

    def resolve_dynamic_vs_static(
        self, box: OBB2D, *, iterations: int = STATIC_SOLVER_PASSES
    ) -> tuple[float, float]:
        """Alias kept for older callers — same as resolve_static_world_collisions."""
        return self.resolve_static_world_collisions(box, iterations=iterations)

    def segment_hits_static(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        categories: set[int] | None = None,
        samples: int = 5,
    ) -> OBB2D | None:
        """Return the first static OBB hit by a short 2D probe (whisker)."""
        if samples < 2:
            samples = 2
        for i in range(1, samples + 1):
            t = i / samples
            px = x0 + (x1 - x0) * t
            py = y0 + (y1 - y0) * t
            for other in self.nearby_static_3x3(px, py):
                tag = other.tag
                if categories is not None and tag not in categories:
                    continue
                if other.contains_point(px, py):
                    return other
        return None

    def resolve_pair(
        self, a: OBB2D, b: OBB2D, *, mass_a: float = 1.0, mass_b: float = 1.0
    ) -> tuple[float, float, float] | None:
        """Separate overlapping pair and bounce velocities. Returns MTV on A."""
        hit = sat_overlap(a, b)
        if hit is None:
            return None
        nx, ny, pen = hit
        inv_a = 1.0 / max(mass_a, 1e-6)
        inv_b = 1.0 / max(mass_b, 1e-6)
        share = inv_a + inv_b
        a.x += nx * pen * (inv_a / share)
        a.y += ny * pen * (inv_a / share)
        b.x -= nx * pen * (inv_b / share)
        b.y -= ny * pen * (inv_b / share)

        # Relative velocity along normal; bounce lightly.
        rvx = a.vx - b.vx
        rvy = a.vy - b.vy
        vn = rvx * nx + rvy * ny
        if vn < 0.0:
            e = 0.35
            j = -(1.0 + e) * vn / share
            a.vx += j * nx * inv_a
            a.vy += j * ny * inv_a
            b.vx -= j * nx * inv_b
            b.vy -= j * ny * inv_b
        return nx, ny, pen
