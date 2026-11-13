"""Blocky car traffic on the city road grid and highway."""

from __future__ import annotations

import math
import random
from collections import defaultdict

from city.materials import car_material
from city.mesh import car_template

# Body length along travel; bumper gap when queued or following.
# Centre-to-centre spacing is length + gap so bodies never touch.
_CAR_LENGTH = 2.0
_CAR_WIDTH = 1.0
_CAR_GAP = 1.0
_CAR_FOLLOW = _CAR_LENGTH + _CAR_GAP
# Hard overlap radius (above body length so 2×1 boxes never clip at angles).
_CAR_TOUCH = 2.25
# Same-lane lateral tolerance (road is 5 wide; right-lane centre ± a bit).
_CAR_LANE_TOL = 1.6
# Spatial hash for collision candidates; larger than touch so one-frame drift stays covered.
_CAR_CELL = 4.0

# Rebuilt once per fleet tick so each car avoids a full O(n) scan.
_FLEET_LANES: dict[tuple, list] = {}
_FLEET_QUEUES: dict[tuple, list] = {}
_FLEET_CELLS: dict[tuple[int, int], list] = {}


class CarController:
    """Drives one blocky car; owns car state and the per-frame task."""

    def __init__(self, app, fleet: list[CarController] | None = None) -> None:
        self.app = app
        self.render = app.render
        self.clock = app.clock
        self.fleet = fleet if fleet is not None else []

    def setup(
        self,
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
        start_dir: tuple[int, int] = (1, 0),
        body_colour: tuple[float, float, float] = (0.22, 0.48, 0.72),
    ) -> None:
        """Blocky 2×1×1 car on the road grid, long axis along travel."""
        size = (_CAR_LENGTH, 1.0, 1.0)
        self.car = car_template().copyTo(self.render)
        # Flatten bakes paint onto geom state; replace it so each car keeps a unique colour.
        body = self.car.find("**/body")
        if not body.isEmpty():
            body.replaceMaterial(
                car_material("body"),
                car_material("body", body_colour),
            )
        self._car_lights = {
            "left": [
                self.car.find("**/headlight-left"),
                self.car.find("**/taillight-left"),
            ],
            "right": [
                self.car.find("**/headlight-right"),
                self.car.find("**/taillight-right"),
            ],
        }
        self._car_body_half_z = size[2] / 2
        self._car_grade_z = road_top
        self._car_z = road_top + self._car_body_half_z
        self._car_origin_x = origin_x
        self._car_origin_y = origin_y
        self._car_stride_x = stride_x
        self._car_stride_y = stride_y
        self._car_cols = cols
        self._car_rows = rows
        # Stop with the front bumper on the 5-wide intersection edge.
        self._car_stop_offset = 5.0 / 2 + size[0] / 2
        # Right-hand traffic: sit in the middle of the right half of the road.
        # Never use a negative offset (that would be the oncoming/left lane).
        self._car_lane_offset = abs(5.0 / 4)
        # Cruise ~one short block per couple of seconds; decel into the stop line.
        self._car_cruise = 10.0
        self._car_accel = 12.0
        self._car_decel_dist = 6.0
        # Brief stop so blinkers read and right-on-red is a full stop first.
        self._car_min_stop = 0.75
        # No signal (city edge or highway): full stop, then go.
        self._car_unsignalized_wait = 3.0
        self._car_blink_period = 0.35
        self._car_speed = self._car_cruise
        self._car_state = "drive"
        self._car_wait = 0.0
        self._car_dir = start_dir
        self._car_heading = math.degrees(math.atan2(start_dir[1], start_dir[0]))
        # Next intersection ahead; start on the approach stop for that node.
        self._car_to = (start_v, start_h)
        self._car_pending_dir: tuple[int, int] | None = None
        self._car_signal: str | None = None
        self._car_blink_t = 0.0
        self._signals = None
        self._car_on_highway = False
        self._car_diamonds: list[dict] = []
        self._car_exit_i = 0
        self._car_ring_phase = "leg"  # leg | to_corner
        self._car_pending_exit: int | None = None
        self._car_highway_lane = 0
        self._car_highway_x = 0.0
        self._car_highway_y = 0.0
        # Elevated diamond ramp path: list of (x, y, surface_z).
        self._car_path: list[tuple[float, float, float]] = []
        self._car_path_i = 0
        self._car_path_kind: str | None = None
        self._car_path_from_z = road_top
        self._car_path_seg_len = 1.0
        self._car_surface_z = road_top
        self._car_pos = list(self._car_stop_xy(*self._car_to, self._car_dir))
        self._car_target = self._car_stop_xy(*self._car_to, self._car_dir)
        self._nb_leader: CarController | None = None
        self._nb_leader_along: float | None = None
        self._nb_queue_index = 0
        self._nb_dir = self._car_travel_dir()
        self._nb_stop = self._car_approach_stop()
        self._nb_slot = self._nb_stop
        self._nb_hold: tuple[float, float] | None = None
        self._car_signal_applied: tuple[str | None, bool] | None = None
        self._place_car()
        self._car_apply_signals(None, True)
        if self not in self.fleet:
            self.fleet.append(self)

    def _car_intersection_xy(self, v: int, h: int) -> tuple[float, float]:
        return (
            self._car_origin_x + v * self._car_stride_x,
            self._car_origin_y + h * self._car_stride_y,
        )

    def _car_diamond(self, exit_i: int | None = None) -> dict:
        idx = self._car_exit_i if exit_i is None else exit_i
        return self._car_diamonds[idx]

    def _car_is_ccw(self, direction: tuple[int, int] | None = None) -> bool:
        """True when ``direction`` matches the diamond's counter-clockwise leg."""
        diamond = self._car_diamond()
        dx, dy = direction if direction is not None else self._car_dir
        return (dx, dy) == tuple(diamond["ccw_dir"])

    def _car_set_highway_lane(
        self,
        direction: tuple[int, int],
        *,
        pick: bool = False,
        snap: bool = False,
    ) -> None:
        """Stay in the three right-hand lanes for this travel direction.

        Lane preference 0 is rightmost from the driver's view (outer edge of the
        half), 2 is nearest the median. CCW uses the inner half; CW the outer.
        """
        if not self._car_diamonds:
            return
        half = max(1, self._car_highway_lanes // 2)
        if pick:
            self._car_highway_lane = random.randrange(half)
        else:
            self._car_highway_lane = max(0, min(half - 1, self._car_highway_lane))
        ccw = self._car_is_ccw(direction)
        # Inner half = indices 0..half-1; outer half = reversed high indices.
        if ccw:
            lane_i = self._car_highway_lane
        else:
            lane_i = self._car_highway_lanes - 1 - self._car_highway_lane
        diamond = self._car_diamond()
        side = diamond["side"]
        if side == "west":
            self._car_highway_x = self._car_west_lane_xs[lane_i]
            self._car_highway_y = diamond["hy"]
        elif side == "east":
            self._car_highway_x = self._car_east_lane_xs[lane_i]
            self._car_highway_y = diamond["hy"]
        elif side == "south":
            self._car_highway_y = self._car_south_lane_ys[lane_i]
            self._car_highway_x = diamond["hx"]
        else:
            self._car_highway_y = self._car_north_lane_ys[lane_i]
            self._car_highway_x = diamond["hx"]
        if snap:
            if diamond["axis"] == "ns":
                self._car_pos[0] = self._car_highway_x
            else:
                self._car_pos[1] = self._car_highway_y

    def _car_hold_highway_lane(self) -> None:
        """Keep highway travel glued to the assigned right-hand lane centre."""
        if not self._car_on_highway or not self._car_diamonds:
            return
        if self._car_state in ("turning", "path"):
            return
        if self._car_path_kind in ("exit_city", "enter_ccw", "enter_cw", "enter_deck"):
            return
        dx, dy = self._car_dir
        if dx == 0 and dy == 0:
            return
        self._car_set_highway_lane(self._car_dir)
        # N/S travel holds X; E/W travel holds Y.
        if dx == 0:
            self._car_pos[0] = self._car_highway_x
        if dy == 0:
            self._car_pos[1] = self._car_highway_y

    def _car_highway_intersection_xy(self, exit_i: int) -> tuple[float, float]:
        """Lane-centred point at a diamond (uses current lane assignment)."""
        diamond = self._car_diamond(exit_i)
        if diamond["axis"] == "ns":
            return (self._car_highway_x, diamond["hy"])
        return (diamond["hx"], self._car_highway_y)

    def _car_diverge_xy(
        self,
        exit_i: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Lane-centred diverge/merge station before an interchange."""
        self._car_exit_i = exit_i
        self._car_set_highway_lane(direction)
        diamond = self._car_diamond(exit_i)
        ramps = diamond["ramps"]
        key = "diverge_ccw" if self._car_is_ccw(direction) else "diverge_cw"
        dx, dy = direction
        if diamond["axis"] == "ns":
            return self._car_highway_x, ramps[key][1]
        return ramps[key][0], self._car_highway_y

    def _car_merge_xy(
        self,
        exit_i: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Lane-centred merge station after joining from an on-ramp."""
        self._car_exit_i = exit_i
        self._car_set_highway_lane(direction)
        diamond = self._car_diamond(exit_i)
        ramps = diamond["ramps"]
        key = "merge_ccw" if self._car_is_ccw(direction) else "merge_cw"
        if diamond["axis"] == "ns":
            return self._car_highway_x, ramps[key][1]
        return ramps[key][0], self._car_highway_y

    def _car_highway_stop(
        self,
        exit_i: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Approach stop at the off-ramp diverge, in the active highway lane."""
        dx, dy = direction
        cx, cy = self._car_diverge_xy(exit_i, direction)
        offset = self._car_stop_offset
        if dx == 0 and dy != 0:
            return cx, cy - dy * offset
        if dy == 0 and dx != 0:
            return cx - dx * offset, cy
        lx, ly = self._car_lane_shift(direction)
        return cx - dx * offset + lx, cy - dy * offset + ly

    def _car_highway_leave(
        self,
        exit_i: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Far edge past the diverge, still in the active highway lane."""
        dx, dy = direction
        cx, cy = self._car_diverge_xy(exit_i, direction)
        offset = self._car_stop_offset
        if dx == 0 and dy != 0:
            return cx, cy + dy * offset
        if dy == 0 and dx != 0:
            return cx + dx * offset, cy
        lx, ly = self._car_lane_shift(direction)
        return cx + dx * offset + lx, cy + dy * offset + ly

    def _car_set_surface_z(self, surface_z: float) -> None:
        """Place the car body on a road/bridge/ramp surface."""
        self._car_surface_z = surface_z
        self._car_z = surface_z + self._car_body_half_z

    def _car_begin_path(
        self,
        points: list[tuple[float, float, float]],
        *,
        kind: str,
    ) -> None:
        """Follow elevated diamond ramp waypoints; ``kind`` selects the finish."""
        cleaned: list[tuple[float, float, float]] = []
        for pt in points:
            if cleaned:
                prev = cleaned[-1]
                if math.hypot(pt[0] - prev[0], pt[1] - prev[1]) < 0.15:
                    cleaned[-1] = pt
                    continue
            cleaned.append(pt)
        if not cleaned:
            self._car_finish_path(kind)
            return
        self._car_path = cleaned
        self._car_path_i = 0
        self._car_path_kind = kind
        self._car_state = "path"
        self._car_speed = max(self._car_speed, self._car_cruise * 0.35)
        self._car_target = (cleaned[0][0], cleaned[0][1])
        self._car_path_from_z = self._car_surface_z
        self._car_path_seg_len = max(
            math.hypot(
                cleaned[0][0] - self._car_pos[0],
                cleaned[0][1] - self._car_pos[1],
            ),
            0.05,
        )
        # Don't snap Z yet — lerp along the first segment toward the waypoint.

    def _car_finish_path(self, kind: str | None = None) -> None:
        """Hand off after the last ramp waypoint."""
        kind = self._car_path_kind if kind is None else kind
        self._car_path = []
        self._car_path_i = 0
        self._car_path_kind = None
        exit_i = self._car_exit_i
        diamond = self._car_diamond(exit_i)
        grade = diamond.get("grade_top", self._car_grade_z)

        if kind == "exit_city":
            into = tuple(diamond["into_city"])
            self._car_dir = into
            self._car_enter_city_from_highway(exit_i)
            self._car_set_surface_z(grade)
            self._car_after_cross = self._car_stop_xy(*self._car_to, into)
            self._car_clear_signals()
            self._car_state = "drive"
            self._car_target = self._car_after_cross
            return

        if kind == "enter_deck":
            # Arrived on the bridge deck from the city arterial; pick a ring dir.
            self._car_on_highway = True
            self._car_ring_phase = "deck"
            city_ix = diamond["ramps"]["city_ix"]
            self._car_pos[0], self._car_pos[1] = city_ix
            self._car_set_surface_z(diamond.get("bridge_top", grade))
            self._car_clear_signals()
            self._car_state = "wait"
            self._car_wait = self._car_unsignalized_wait
            self._car_pending_dir = self._car_choose_highway_turn()
            self._car_signal = self._car_signal_side(
                tuple(diamond["into_city"]), self._car_pending_dir,
            )
            self._car_blink_t = 0.0
            self._car_update_signals(0.0)
            return

        if kind in ("enter_ccw", "enter_cw"):
            new_dir = (
                tuple(diamond["ccw_dir"])
                if kind == "enter_ccw"
                else tuple(diamond["cw_dir"])
            )
            self._car_dir = new_dir
            self._car_on_highway = True
            self._car_ring_phase = "to_corner"
            self._car_set_highway_lane(new_dir, pick=True, snap=True)
            self._car_set_surface_z(grade)
            merge = self._car_merge_xy(exit_i, new_dir)
            self._car_pos[0], self._car_pos[1] = merge
            nxt = self._car_next_highway_exit(exit_i, new_dir)
            self._car_pending_exit = nxt
            corner = self._car_corner_approach(exit_i, new_dir)
            self._car_clear_signals()
            self._car_state = "drive"
            self._car_target = corner
            self._car_after_cross = corner
            return

        self._car_set_surface_z(grade)
        self._car_state = "drive"

    def _car_next_highway_exit(self, exit_i: int, direction: tuple[int, int]) -> int:
        """Next diamond index around the ring for this travel direction."""
        n = len(self._car_diamonds)
        diamond = self._car_diamond(exit_i)
        if tuple(direction) == tuple(diamond["ccw_dir"]):
            return (exit_i + 1) % n
        if tuple(direction) == tuple(diamond["cw_dir"]):
            return (exit_i - 1) % n
        # Joining from the city spur: prefer CCW (inner) carriageway.
        return (exit_i + 1) % n

    def _car_gateway_exit_i(self) -> int | None:
        """Diamond index reachable from the current city node, if any."""
        v, h = self._car_to
        for index, diamond in enumerate(self._car_diamonds):
            if diamond["city_v"] != v or diamond["city_h"] != h:
                continue
            if abs(self._car_origin_y - diamond["city_origin_y"]) < 1e-6:
                return index
        return None

    def _car_enter_city_from_highway(self, exit_i: int) -> None:
        """Switch from a diamond onto the connected city grid node."""
        diamond = self._car_diamond(exit_i)
        self._car_on_highway = False
        self._car_ring_phase = "leg"
        self._car_origin_y = diamond["city_origin_y"]
        self._car_to = (diamond["city_v"], diamond["city_h"])

    def _car_enter_highway_from_city(self, exit_i: int) -> None:
        """Mark the diamond we are joining; lane picked when the on-ramp merges."""
        self._car_exit_i = exit_i
        self._car_ring_phase = "leg"

    def _car_route_points(self, name: str, exit_i: int | None = None) -> list[tuple[float, float, float]]:
        """Copy annotated ramp waypoints for this diamond."""
        diamond = self._car_diamond(exit_i)
        return [tuple(pt) for pt in diamond["routes"][name]]

    def _car_corner_approach(
        self,
        exit_i: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Point at the end of the current straight leg, before the corner arc."""
        self._car_exit_i = exit_i
        self._car_set_highway_lane(direction)
        diamond = self._car_diamond(exit_i)
        dx, dy = direction
        if diamond["side"] == "west":
            y = self._car_ns_y1 if dy > 0 else self._car_ns_y0
            return self._car_highway_x, y
        if diamond["side"] == "east":
            y = self._car_ns_y0 if dy < 0 else self._car_ns_y1
            return self._car_highway_x, y
        if diamond["side"] == "south":
            x = self._car_ew_x0 if dx < 0 else self._car_ew_x1
            return x, self._car_highway_y
        x = self._car_ew_x1 if dx > 0 else self._car_ew_x0
        return x, self._car_highway_y

    def _car_corner_center(
        self,
        from_i: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Arc pivot between ``from_i`` and the next diamond along ``direction``."""
        nxt = self._car_next_highway_exit(from_i, direction)
        a = self._car_diamond(from_i)["side"]
        b = self._car_diamond(nxt)["side"]
        key = frozenset((a, b))
        if key == frozenset(("west", "north")):
            return self._car_corner_nw
        if key == frozenset(("north", "east")):
            return self._car_corner_ne
        if key == frozenset(("east", "south")):
            return self._car_corner_se
        return self._car_corner_sw

    def _car_start_highway_corner_arc(
        self,
        old_dir: tuple[int, int],
        new_dir: tuple[int, int],
        cx: float,
        cy: float,
    ) -> None:
        """Quarter-turn around a beltway corner centre onto the next leg."""
        cross = old_dir[0] * new_dir[1] - old_dir[1] * new_dir[0]
        sign = 1.0 if cross > 0 else -1.0
        self._car_state = "turning"
        self._car_arc_center = (cx, cy)
        rx = self._car_pos[0] - cx
        ry = self._car_pos[1] - cy
        self._car_arc_radius = max(math.hypot(rx, ry), 1.0)
        self._car_arc_sign = sign
        self._car_arc_angle = math.atan2(ry, rx)
        self._car_arc_end = self._car_arc_angle + sign * (math.pi / 2)

    def _car_begin_corner_turn(self) -> None:
        """At the end of a straight leg: arc onto the next diamond's carriageway."""
        from_i = self._car_exit_i
        old_dir = self._car_dir
        nxt = self._car_pending_exit
        if nxt is None:
            nxt = self._car_next_highway_exit(from_i, old_dir)
        next_diamond = self._car_diamond(nxt)
        if self._car_is_ccw(old_dir):
            new_dir = tuple(next_diamond["ccw_dir"])
        else:
            new_dir = tuple(next_diamond["cw_dir"])
        cx, cy = self._car_corner_center(from_i, old_dir)
        self._car_exit_i = nxt
        self._car_dir = new_dir
        self._car_set_highway_lane(new_dir, pick=False, snap=False)
        self._car_ring_phase = "leg"
        self._car_pending_exit = None
        self._car_after_cross = self._car_highway_stop(nxt, new_dir)
        self._car_start_highway_corner_arc(old_dir, new_dir, cx, cy)

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
        if self._car_on_highway:
            return self._car_choose_highway_turn()
        v, h = self._car_to
        dx, dy = self._car_dir
        options: list[tuple[int, int]] = []
        gateway = self._car_gateway_exit_i()
        into = None
        if gateway is not None:
            into = tuple(self._car_diamonds[gateway]["into_city"])
            # Toward the highway is opposite the into-city vector.
            toward_hwy = (-into[0], -into[1])
        for ndx, ndy in (
            (dx, dy),
            (-dy, dx),
            (dy, -dx),
        ):
            if gateway is not None and (ndx, ndy) == toward_hwy:
                options.append((ndx, ndy))
                continue
            if self._car_in_bounds(v + ndx, h + ndy):
                options.append((ndx, ndy))
        if not options:
            return (-dx, -dy)
        return random.choice(options)

    def _car_choose_highway_turn(self) -> tuple[int, int]:
        """At a diverge or bridge deck: continue, exit, join a ring dir, or reverse."""
        diamond = self._car_diamond()
        into = tuple(diamond["into_city"])
        ccw = tuple(diamond["ccw_dir"])
        cw = tuple(diamond["cw_dir"])
        dx, dy = self._car_dir
        options: list[tuple[int, int]] = []
        if (dx, dy) in (ccw, cw):
            # On the carriageway at the diverge: continue, exit, or reverse.
            options.append((dx, dy))
            options.append((dx, dy))  # prefer staying on the ring
            options.append(into)
            options.append((-dx, -dy))
        else:
            # On the bridge deck after climbing from the city.
            options.extend((ccw, cw, into))
        return random.choice(options)

    @staticmethod
    def _car_signal_side(
        old_dir: tuple[int, int],
        new_dir: tuple[int, int],
    ) -> str | None:
        """Which corner lamps blink for this turn: left, right, or none."""
        cross = old_dir[0] * new_dir[1] - old_dir[1] * new_dir[0]
        if cross > 0:
            return "left"
        if cross < 0:
            return "right"
        return None

    def _car_apply_signals(self, side: str | None, lit: bool) -> None:
        """Dim the signalling side when ``lit`` is false; other lamps stay on."""
        key = (side, lit)
        if getattr(self, "_car_signal_applied", None) == key:
            return
        self._car_signal_applied = key
        for name, lamps in self._car_lights.items():
            if side is not None and name == side and not lit:
                scale = 0.12
            else:
                scale = 1.0
            for lamp in lamps:
                if not lamp.isEmpty():
                    lamp.setColorScale(scale, scale, scale, 1)

    def _car_update_signals(self, dt: float) -> None:
        """Blink the pending turn side, or restore steady lamps when idle."""
        if self._car_signal is None:
            self._car_apply_signals(None, True)
            return
        self._car_blink_t += dt
        lit = (int(self._car_blink_t / self._car_blink_period) % 2) == 0
        self._car_apply_signals(self._car_signal, lit)

    def _car_clear_signals(self) -> None:
        self._car_signal = None
        self._car_pending_dir = None
        self._car_blink_t = 0.0
        self._car_signal_applied = None
        self._car_apply_signals(None, True)

    def _car_has_traffic_light(self) -> bool:
        """Interior city crosses get signals; edges and the highway do not."""
        if self._car_on_highway or self._signals is None:
            return False
        v, h = self._car_to
        return 1 <= v < self._car_cols and 1 <= h < self._car_rows

    def _car_may_proceed(self, new_dir: tuple[int, int]) -> bool:
        """True once the stop is legal for ``new_dir`` given the light (if any)."""
        if not self._car_has_traffic_light():
            return True
        return self._signals.may_proceed(self._car_dir, new_dir)

    def _car_travel_dir(self) -> tuple[float, float]:
        """Unit travel vector for spacing checks (grid dir, else heading)."""
        if self._car_state == "path":
            rad = math.radians(self._car_heading)
            return math.cos(rad), math.sin(rad)
        dx, dy = self._car_dir
        if dx or dy:
            return float(dx), float(dy)
        rad = math.radians(self._car_heading)
        return math.cos(rad), math.sin(rad)

    def _car_approach_stop(self) -> tuple[float, float]:
        """Ideal stop-line position for the current approach."""
        if self._car_on_highway:
            if self._car_ring_phase == "deck":
                return tuple(self._car_diamond()["ramps"]["city_ix"])
            return self._car_highway_stop(self._car_exit_i, self._car_dir)
        return self._car_stop_xy(*self._car_to, self._car_dir)

    def _car_lane_key(self) -> tuple:
        """Same travel lane / twin city corridor for leader search."""
        dx, dy = self._car_dir if (self._car_dir[0] or self._car_dir[1]) else self._car_travel_dir()
        if self._car_on_highway:
            axis = (
                round(self._car_highway_y * 2.0) / 2.0
                if self._car_diamonds
                and self._car_diamond()["axis"] == "ew"
                else round(self._car_highway_x * 2.0) / 2.0
            )
            return ("h", axis, int(dx), int(dy))
        return ("c", round(self._car_origin_y), int(dx), int(dy))

    def _car_queue_key(self) -> tuple:
        """Cars sharing one stop-line queue."""
        dx, dy = self._car_dir if (self._car_dir[0] or self._car_dir[1]) else self._car_travel_dir()
        if self._car_on_highway:
            return ("h", self._car_exit_i, int(dx), int(dy))
        return ("c", round(self._car_origin_y), self._car_to, int(dx), int(dy))

    @staticmethod
    def build_fleet_index(fleet: list[CarController]) -> None:
        """Bucket the fleet once per tick for near-linear neighbor queries."""
        lanes: dict[tuple, list] = defaultdict(list)
        queues: dict[tuple, list] = defaultdict(list)
        cells: dict[tuple[int, int], list] = defaultdict(list)
        inv = 1.0 / _CAR_CELL
        for car in fleet:
            lanes[car._car_lane_key()].append(car)
            queues[car._car_queue_key()].append(car)
            cells[
                (int(math.floor(car._car_pos[0] * inv)), int(math.floor(car._car_pos[1] * inv)))
            ].append(car)
        global _FLEET_LANES, _FLEET_QUEUES, _FLEET_CELLS
        _FLEET_LANES = lanes
        _FLEET_QUEUES = queues
        _FLEET_CELLS = cells

    def _car_cell_mates(self) -> list[CarController]:
        """Cars in this cell and its 8 neighbours (collision candidates)."""
        inv = 1.0 / _CAR_CELL
        cx = int(math.floor(self._car_pos[0] * inv))
        cy = int(math.floor(self._car_pos[1] * inv))
        cells = _FLEET_CELLS
        out: list[CarController] = []
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                bucket = cells.get((cx + ox, cy + oy))
                if bucket:
                    out.extend(bucket)
        return out

    def _car_refresh_neighbors(self, *, resolve: bool = True) -> None:
        """Leader, queue index, optional collision — using the per-tick index."""
        dx, dy = self._car_travel_dir()
        stop = self._car_approach_stop()
        sx = self._car_pos[0]
        sy = self._car_pos[1]
        my_behind = (stop[0] - sx) * dx + (stop[1] - sy) * dy
        follow = _CAR_FOLLOW
        lane_tol = _CAR_LANE_TOL
        follow_sq = (follow - 0.01) * (follow - 0.01)
        touch_sq = (_CAR_TOUCH - 0.01) * (_CAR_TOUCH - 0.01)

        leader: CarController | None = None
        best_along = float("inf")
        queue_index = 0

        if resolve:
            for other in self._car_cell_mates():
                if other is self:
                    continue
                ox = other._car_pos[0] - sx
                oy = other._car_pos[1] - sy
                dist_sq = ox * ox + oy * oy
                if dist_sq >= follow_sq and dist_sq >= touch_sq:
                    continue
                if dist_sq < 1e-12:
                    sx -= dx * follow
                    sy -= dy * follow
                    self._car_pos[0] = sx
                    self._car_pos[1] = sy
                    self._car_speed = 0.0
                    continue
                along = ox * dx + oy * dy
                lateral = abs(ox * -dy + oy * dx)
                same_lane = lateral <= lane_tol and along > 0.0
                if same_lane and dist_sq < follow_sq:
                    dist = math.sqrt(dist_sq)
                    push = follow - dist
                    sx -= dx * push
                    sy -= dy * push
                    self._car_pos[0] = sx
                    self._car_pos[1] = sy
                    self._car_speed = 0.0
                    continue
                if dist_sq < touch_sq:
                    dist = math.sqrt(dist_sq)
                    push = _CAR_TOUCH - dist
                    if along > 0.0:
                        sx -= dx * push
                        sy -= dy * push
                    else:
                        inv = 1.0 / dist
                        sx -= ox * inv * push
                        sy -= oy * inv * push
                    self._car_pos[0] = sx
                    self._car_pos[1] = sy
                    self._car_speed = 0.0

        for other in _FLEET_LANES.get(self._car_lane_key(), ()):
            if other is self:
                continue
            ox = other._car_pos[0] - sx
            oy = other._car_pos[1] - sy
            along = ox * dx + oy * dy
            if along <= 0.05:
                continue
            lateral = abs(ox * -dy + oy * dx)
            if lateral <= lane_tol and along < best_along:
                best_along = along
                leader = other

        for other in _FLEET_QUEUES.get(self._car_queue_key(), ()):
            if other is self or other._car_state in ("turning", "u-turn"):
                continue
            other_behind = (
                (stop[0] - other._car_pos[0]) * dx + (stop[1] - other._car_pos[1]) * dy
            )
            if other_behind < my_behind - 0.05:
                queue_index += 1

        self._nb_leader = leader
        self._nb_queue_index = queue_index
        self._nb_dir = (dx, dy)
        self._nb_stop = stop
        self._nb_slot = (
            stop[0] - dx * follow * queue_index,
            stop[1] - dy * follow * queue_index,
        )
        if leader is None:
            self._nb_hold = None
            self._nb_leader_along = None
        else:
            hold = (
                leader._car_pos[0] - dx * follow,
                leader._car_pos[1] - dy * follow,
            )
            hold_along = (hold[0] - self._car_pos[0]) * dx + (
                hold[1] - self._car_pos[1]
            ) * dy
            self._nb_hold = hold if hold_along > 0.1 else None
            self._nb_leader_along = best_along

    def _car_queue_slot_xy(self) -> tuple[float, float]:
        """Equally spaced hold: stop, stop−FOLLOW, stop−2·FOLLOW, …"""
        return self._nb_slot

    def _car_follow_hold_xy(self) -> tuple[float, float] | None:
        """Point one bumper-gap behind the live leader, or None if clear ahead."""
        return self._nb_hold

    def _car_drive_target(self) -> tuple[float, float]:
        """Nearest of: equal queue slot, live follow hold."""
        slot = self._nb_slot
        hold = self._nb_hold
        if hold is None:
            return slot
        dx, dy = self._nb_dir

        def along(pt: tuple[float, float]) -> float:
            return (pt[0] - self._car_pos[0]) * dx + (pt[1] - self._car_pos[1]) * dy

        return hold if along(hold) < along(slot) else slot

    def _car_at_stop_line(self) -> bool:
        """True when this car has reached its equal-spaced queue slot."""
        sx, sy = self._nb_slot
        return math.hypot(sx - self._car_pos[0], sy - self._car_pos[1]) < 0.2

    def _car_is_queue_head(self) -> bool:
        return self._nb_queue_index == 0

    def _car_resolve_collisions(self) -> None:
        """Re-scan fleet and push this car clear of overlaps."""
        self._car_refresh_neighbors(resolve=True)

    def _car_snap_queue_slot(self) -> None:
        """Lock a stopped car onto its equal-spaced approach slot."""
        if self._car_state != "wait":
            return
        sx, sy = self._nb_slot
        if math.hypot(sx - self._car_pos[0], sy - self._car_pos[1]) < 0.35:
            self._car_pos[0] = sx
            self._car_pos[1] = sy

    def _car_begin_wait(self) -> None:
        """Stop at the queue slot; only the head picks a turn / watches the light."""
        self._car_speed = 0.0
        self._car_state = "wait"
        # Queued behind another car: hold the equal-spaced slot; no turn yet.
        if not self._car_is_queue_head():
            self._car_wait = 0.0
            self._car_pending_dir = None
            self._car_signal = None
            self._car_apply_signals(None, True)
            return
        self._car_wait = (
            self._car_min_stop
            if self._car_has_traffic_light()
            else self._car_unsignalized_wait
        )
        self._car_pending_dir = self._car_choose_turn()
        self._car_signal = self._car_signal_side(self._car_dir, self._car_pending_dir)
        self._car_blink_t = 0.0
        self._car_update_signals(0.0)

    def _car_start_arc(
        self,
        old_dir: tuple[int, int],
        new_dir: tuple[int, int],
        cx: float,
        cy: float,
    ) -> None:
        """Begin a right-lane quarter-circle from old_dir to new_dir at (cx, cy)."""
        o = self._car_stop_offset
        cross = old_dir[0] * new_dir[1] - old_dir[1] * new_dir[0]
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

    def _car_start_u_turn(self, new_dir: tuple[int, int]) -> None:
        """Spin in place to face ``new_dir``, then drive to ``_car_after_cross``."""
        self._car_clear_signals()
        self._car_state = "u-turn"
        self._car_heading_from = self._car_heading
        self._car_heading_to = math.degrees(math.atan2(new_dir[1], new_dir[0]))
        delta = (self._car_heading_to - self._car_heading_from + 180.0) % 360.0 - 180.0
        self._car_heading_to = self._car_heading_from + delta
        self._car_u_turn_span = abs(delta) if abs(delta) > 1e-3 else 180.0
        self._car_u_turn_progress = 0.0

    def _car_begin_maneuver(self, new_dir: tuple[int, int]) -> None:
        """Leave the stop line: arc on turns, straight when going forward."""
        old_dir = self._car_dir
        cross = old_dir[0] * new_dir[1] - old_dir[1] * new_dir[0]
        dot = old_dir[0] * new_dir[0] + old_dir[1] * new_dir[1]
        self._car_speed = 0.0
        self._car_pending_dir = None

        if self._car_on_highway:
            self._car_begin_highway_maneuver(old_dir, new_dir, cross, dot)
            return

        v, h = self._car_to
        gateway = self._car_gateway_exit_i()
        if gateway is not None:
            diamond = self._car_diamonds[gateway]
            into = tuple(diamond["into_city"])
            toward_hwy = (-into[0], -into[1])
            if new_dir == toward_hwy:
                self._car_dir = new_dir
                self._car_enter_highway_from_city(gateway)
                self._car_clear_signals()
                # Leave the city node, then climb the arterial onto the bridge deck.
                grade = diamond.get("grade_top", self._car_grade_z)
                city_end = diamond["ramps"]["city_end"]
                city_ix = diamond["ramps"]["city_ix"]
                bridge_top = diamond.get("bridge_top", grade)
                leave = self._car_exit_xy(v, h, new_dir)
                self._car_begin_path(
                    [
                        (leave[0], leave[1], grade),
                        (city_end[0], city_end[1], grade),
                        (city_ix[0], city_ix[1], bridge_top),
                    ],
                    kind="enter_deck",
                )
                return

        cx, cy = self._car_intersection_xy(v, h)
        self._car_dir = new_dir
        self._car_to = (v + new_dir[0], h + new_dir[1])
        self._car_after_cross = self._car_stop_xy(*self._car_to, new_dir)

        if dot > 0:
            self._car_clear_signals()
            self._car_state = "crossing"
            self._car_target = self._car_exit_xy(v, h, new_dir)
            return

        if cross == 0:
            self._car_start_u_turn(new_dir)
            return

        self._car_start_arc(old_dir, new_dir, cx, cy)

    def _car_begin_highway_maneuver(
        self,
        old_dir: tuple[int, int],
        new_dir: tuple[int, int],
        cross: float,
        dot: float,
    ) -> None:
        """Maneuver at a diverge or bridge deck: exit ramp, on-ramp, or continue."""
        exit_i = self._car_exit_i
        diamond = self._car_diamond(exit_i)
        into = tuple(diamond["into_city"])
        ccw = tuple(diamond["ccw_dir"])
        cw = tuple(diamond["cw_dir"])
        grade = diamond.get("grade_top", self._car_grade_z)

        # Peel off into the city via the diamond off-ramp.
        if new_dir == into:
            self._car_clear_signals()
            if old_dir in (ccw, cw):
                route_name = "exit_ccw" if self._car_is_ccw(old_dir) else "exit_cw"
                diverge = self._car_diverge_xy(exit_i, old_dir)
                path = [
                    (diverge[0], diverge[1], grade),
                    *self._car_route_points(route_name, exit_i),
                ]
                self._car_begin_path(path, kind="exit_city")
                return
            # Already on the deck: descend the city arterial.
            city_end = diamond["ramps"]["city_end"]
            city_ix = diamond["ramps"]["city_ix"]
            bridge_top = diamond.get("bridge_top", grade)
            self._car_begin_path(
                [
                    (city_ix[0], city_ix[1], bridge_top),
                    (city_end[0], city_end[1], grade),
                ],
                kind="exit_city",
            )
            return

        if new_dir in (ccw, cw):
            joining = old_dir not in (ccw, cw)
            reversing = old_dir[0] * new_dir[0] + old_dir[1] * new_dir[1] < 0
            if joining:
                # From the bridge deck onto an on-ramp, then merge.
                self._car_clear_signals()
                route_name = "enter_ccw" if new_dir == ccw else "enter_cw"
                # enter_* routes start at city_end; deck wait is already at city_ix.
                path = self._car_route_points(route_name, exit_i)
                if len(path) >= 2:
                    path = path[1:]  # drop city_end; start from city_ix
                self._car_begin_path(path, kind=route_name)
                return

            self._car_dir = new_dir
            self._car_set_highway_lane(new_dir, pick=reversing, snap=reversing)
            nxt = self._car_next_highway_exit(exit_i, new_dir)
            self._car_pending_exit = nxt
            self._car_ring_phase = "to_corner"
            corner = self._car_corner_approach(exit_i, new_dir)
            if cross == 0 and reversing:
                self._car_after_cross = corner
                self._car_start_u_turn(new_dir)
                return
            # Continue past the interchange along the lane toward the corner.
            self._car_clear_signals()
            self._car_state = "crossing"
            self._car_target = self._car_highway_leave(exit_i, new_dir)
            self._car_after_cross = corner
            return

        # Facing back toward the city from the deck.
        city_end = diamond["ramps"]["city_end"]
        city_ix = diamond["ramps"]["city_ix"]
        bridge_top = diamond.get("bridge_top", grade)
        self._car_clear_signals()
        self._car_begin_path(
            [
                (city_ix[0], city_ix[1], bridge_top),
                (city_end[0], city_end[1], grade),
            ],
            kind="exit_city",
        )

    def _place_car(self) -> None:
        self.car.setPos(self._car_pos[0], self._car_pos[1], self._car_z)
        self.car.setH(self._car_heading)

    def _car_advance_speed(self, dt: float, dist: float | None = None) -> None:
        if dist is not None and dist < self._car_decel_dist:
            # Cap speed for the remaining distance, but still accelerate up to
            # that cap — otherwise a car that stopped behind a leader (speed 0)
            # can never leave once the gap opens inside decel range.
            target = self._car_cruise * math.sqrt(max(dist, 0.0) / self._car_decel_dist)
            if self._car_speed < target:
                self._car_speed = min(target, self._car_speed + self._car_accel * dt)
            else:
                self._car_speed = target
        else:
            self._car_speed = min(self._car_cruise, self._car_speed + self._car_accel * dt)

    def _car_gap_clear(self) -> bool:
        """True when no same-lane leader sits closer than FOLLOW ahead."""
        along = self._nb_leader_along
        if along is None:
            return True
        return along >= _CAR_FOLLOW - 0.05

    def _car_finish_frame(self) -> None:
        """One neighbor/collision scan + scene graph sync per tick."""
        # Ramp paths are grade-separated; resolving against ground cars shoves
        # climbers off the waypoint polyline, so only scan leaders there.
        resolve = self._car_state != "path"
        self._car_refresh_neighbors(resolve=resolve)
        # Collisions can nudge sideways; re-assert the right-hand highway lane.
        self._car_hold_highway_lane()
        self._place_car()

    def _car_task(self, task):
        dt = min(self.clock.getDt(), 0.05)
        # Targeting uses last tick's neighbor cache; we rescan once at the end.

        if self._car_state == "path":
            if not self._car_path or self._car_path_i >= len(self._car_path):
                self._car_finish_path()
                self._car_finish_frame()
                return task.cont
            # Only yield to another ramp car clearly ahead on this path; ignore
            # at-grade traffic under the overpass so climbs are not pinned.
            leader = self._nb_leader
            if (
                leader is not None
                and leader._car_state == "path"
                and leader._car_exit_i == self._car_exit_i
                and self._nb_leader_along is not None
                and self._nb_leader_along < _CAR_FOLLOW - 0.05
            ):
                self._car_speed = max(0.0, self._car_speed - self._car_accel * dt)
                self._car_finish_frame()
                return task.cont
            tx, ty, tz = self._car_path[self._car_path_i]
            dx = tx - self._car_pos[0]
            dy = ty - self._car_pos[1]
            dist = math.hypot(dx, dy)
            if dist <= max(self._car_speed * dt, 0.08):
                self._car_pos[0] = tx
                self._car_pos[1] = ty
                self._car_set_surface_z(tz)
                self._car_path_i += 1
                if self._car_path_i >= len(self._car_path):
                    self._car_finish_path()
                else:
                    nxt = self._car_path[self._car_path_i]
                    self._car_target = (nxt[0], nxt[1])
                    self._car_path_from_z = tz
                    self._car_path_seg_len = max(
                        math.hypot(nxt[0] - tx, nxt[1] - ty), 0.05,
                    )
                self._car_finish_frame()
                return task.cont
            self._car_advance_speed(dt, dist)
            step = min(self._car_speed * dt, dist)
            if dist > 1e-6:
                self._car_pos[0] += dx / dist * step
                self._car_pos[1] += dy / dist * step
                self._car_heading = math.degrees(math.atan2(dy, dx))
            remain = math.hypot(tx - self._car_pos[0], ty - self._car_pos[1])
            frac = 1.0 - min(1.0, remain / self._car_path_seg_len)
            self._car_set_surface_z(
                self._car_path_from_z + (tz - self._car_path_from_z) * frac
            )
            self._car_finish_frame()
            return task.cont

        if self._car_state == "wait":
            # Hold equal-spaced slots; creep forward when the queue advances.
            if not self._car_is_queue_head() or not self._car_at_stop_line():
                goal = self._car_drive_target()
                gx = goal[0] - self._car_pos[0]
                gy = goal[1] - self._car_pos[1]
                if math.hypot(gx, gy) > 0.08:
                    self._car_state = "drive"
                    self._car_target = goal
                else:
                    self._car_snap_queue_slot()
                self._car_finish_frame()
                return task.cont
            self._car_snap_queue_slot()
            self._car_wait -= dt
            self._car_update_signals(dt)
            if self._car_wait <= 0.0:
                pending = self._car_pending_dir or self._car_choose_turn()
                # Re-roll a blocked turn occasionally so a left on red does not
                # pin a whole queue while a right is legal.
                if (
                    pending is not None
                    and not self._car_may_proceed(pending)
                    and self._car_wait < -4.0
                ):
                    pending = self._car_choose_turn()
                    self._car_pending_dir = pending
                    self._car_signal = self._car_signal_side(self._car_dir, pending)
                    self._car_blink_t = 0.0
                    self._car_signal_applied = None
                if self._car_gap_clear() and self._car_may_proceed(pending):
                    self._car_begin_maneuver(pending)
            self._car_finish_frame()
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
            self._car_finish_frame()
            return task.cont

        if self._car_state == "turning":
            # Pause the arc if we'd nose into another car.
            if not self._car_gap_clear():
                self._car_speed = 0.0
                self._car_finish_frame()
                return task.cont
            self._car_advance_speed(dt)
            self._car_update_signals(dt)
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
                self._car_clear_signals()
            else:
                self._car_arc_angle += angle_step
                acx, acy = self._car_arc_center
                self._car_pos[0] = acx + radius * math.cos(self._car_arc_angle)
                self._car_pos[1] = acy + radius * math.sin(self._car_arc_angle)
                # Tangent to the arc: CCW is angle+90°, CW is angle-90°.
                self._car_heading = math.degrees(
                    self._car_arc_angle + self._car_arc_sign * (math.pi / 2)
                )
            self._car_finish_frame()
            return task.cont

        if self._car_state == "drive" and not (
            self._car_on_highway and self._car_ring_phase == "to_corner"
        ):
            self._car_target = self._car_drive_target()

        tx, ty = self._car_target
        dx = tx - self._car_pos[0]
        dy = ty - self._car_pos[1]
        dist = math.hypot(dx, dy)
        if dist <= max(self._car_speed * dt, 0.02):
            self._car_pos[0] = tx
            self._car_pos[1] = ty
            if self._car_on_highway and self._car_ring_phase == "to_corner":
                self._car_begin_corner_turn()
                self._car_finish_frame()
                return task.cont
            if self._car_state == "crossing":
                self._car_target = self._car_after_cross
                self._car_state = "drive"
                self._car_finish_frame()
                return task.cont
            # Refresh queue rank at the stop before choosing head vs follower.
            self._car_refresh_neighbors(resolve=False)
            self._car_begin_wait()
            self._car_finish_frame()
            return task.cont

        if self._car_state == "drive":
            # Decel for the bumper gap / queue slot ahead.
            limit = dist
            hold = self._nb_hold
            if hold is not None:
                limit = min(
                    limit,
                    math.hypot(hold[0] - self._car_pos[0], hold[1] - self._car_pos[1]),
                )
            self._car_advance_speed(dt, limit)
        else:
            # Crossing: still respect a leader so we don't rear-end in the box.
            if not self._car_gap_clear():
                self._car_speed = max(0.0, self._car_speed - self._car_accel * dt)
            else:
                self._car_advance_speed(dt)

        step = min(self._car_speed * dt, dist)
        if dist > 1e-6:
            self._car_pos[0] += dx / dist * step
            self._car_pos[1] += dy / dist * step
            self._car_heading = math.degrees(math.atan2(dy, dx))
        self._car_finish_frame()
        return task.cont
