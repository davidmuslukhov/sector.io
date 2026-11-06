"""Blocky car traffic on the city road grid and highway."""

from __future__ import annotations

import math
import random

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
        self._car_z = road_top + size[2] / 2
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

    def _car_set_highway_lane(
        self,
        direction: tuple[int, int],
        *,
        pick: bool = False,
        snap: bool = False,
    ) -> None:
        """Stay in the three right-hand lanes for this travel direction.

        Northbound uses the eastern half; southbound the western half. Lane
        preference 0 is the rightmost (outer) lane from the driver's view,
        2 is nearest the median. Never places a car in the oncoming half.
        """
        dx, dy = direction
        if dy == 0:
            return
        half = max(1, self._car_highway_lanes // 2)
        if pick or not hasattr(self, "_car_highway_lane"):
            self._car_highway_lane = random.randrange(half)
        else:
            self._car_highway_lane = max(0, min(half - 1, self._car_highway_lane))
        # Lane centres east→west: 0 is easternmost (rightmost when heading north).
        if dy > 0:
            lane_i = self._car_highway_lane
        else:
            # Southbound rightmost is westernmost = last index.
            lane_i = self._car_highway_lanes - 1 - self._car_highway_lane
        self._car_highway_x = self._car_highway_lane_xs[lane_i]
        # U-turns / joins must move onto the new carriageway immediately so the
        # car never drives north in a southbound lane (or the reverse).
        if snap:
            self._car_pos[0] = self._car_highway_x

    def _car_hold_highway_lane(self) -> None:
        """Keep N/S highway travel glued to the assigned right-hand lane centre."""
        if not self._car_on_highway:
            return
        # Let merge arcs curve freely; snap once they finish.
        if self._car_state == "turning":
            return
        dx, dy = self._car_dir
        if dy == 0:
            return
        self._car_set_highway_lane(self._car_dir)
        self._car_pos[0] = self._car_highway_x

    def _car_highway_intersection_xy(self, exit_i: int) -> tuple[float, float]:
        return (self._car_highway_x, self._car_highway_exits[exit_i])

    def _car_highway_stop(
        self,
        exit_i: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Approach stop at a highway exit, centered in the active highway lane."""
        dx, dy = direction
        if dy != 0:
            self._car_set_highway_lane(direction)
        cx, cy = self._car_highway_intersection_xy(exit_i)
        offset = self._car_stop_offset
        # Highway lane X is already the lane centre — do not apply city lane shift
        # sideways along the highway (that was pushing the car into the barriers).
        if dx == 0:
            return cx, cy - dy * offset
        # City↔highway exit spur: keep the right-hand side of that road.
        _, ly = self._car_lane_shift(direction)
        return cx - dx * offset, cy + ly

    def _car_highway_leave(
        self,
        exit_i: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Far edge leaving a highway exit, centered in the active highway lane."""
        dx, dy = direction
        if dy != 0:
            self._car_set_highway_lane(direction)
        cx, cy = self._car_highway_intersection_xy(exit_i)
        offset = self._car_stop_offset
        if dx == 0:
            return cx, cy + dy * offset
        _, ly = self._car_lane_shift(direction)
        return cx + dx * offset, cy + ly

    def _car_next_highway_exit(self, exit_i: int, dy: int) -> int | None:
        """Next exit index along the highway, or None at the end."""
        nxt = exit_i + (1 if dy > 0 else -1)
        if 0 <= nxt < len(self._car_highway_exits):
            return nxt
        return None

    def _car_gateway_exit_i(self) -> int | None:
        """Highway exit index reachable from the current city node, if any."""
        v, h = self._car_to
        if v != 0 or h != self._car_exit_row:
            return None
        if abs(self._car_origin_y - self._car_south_road0) < 1e-6:
            return 0
        if abs(self._car_origin_y - (self._car_south_road0 + self._car_north_shift)) < 1e-6:
            return 1
        return None

    def _car_enter_city_from_highway(self, exit_i: int) -> None:
        """Switch from a highway exit onto the connected city's western road."""
        self._car_on_highway = False
        if exit_i == 0:
            self._car_origin_y = self._car_south_road0
        else:
            self._car_origin_y = self._car_south_road0 + self._car_north_shift
        self._car_to = (0, self._car_exit_row)

    def _car_enter_highway_from_city(self, exit_i: int) -> None:
        """Switch from the city's western road onto the highway exit."""
        self._car_on_highway = True
        self._car_origin_y = self._car_south_road0
        self._car_exit_i = exit_i
        # Exit spur stop uses the eastern (city-facing) edge until a N/S lane
        # is chosen; prefer the rightmost northbound lane as the reference.
        self._car_highway_x = self._car_highway_lane_xs[0]

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
        for ndx, ndy in (
            (dx, dy),
            (-dy, dx),
            (dy, -dx),
        ):
            if ndx == -1 and ndy == 0 and self._car_gateway_exit_i() is not None:
                options.append((ndx, ndy))
                continue
            if self._car_in_bounds(v + ndx, h + ndy):
                options.append((ndx, ndy))
        if not options:
            return (-dx, -dy)
        return random.choice(options)

    def _car_choose_highway_turn(self) -> tuple[int, int]:
        """At a highway exit: continue, turn into the city, or reverse."""
        dx, dy = self._car_dir
        options: list[tuple[int, int]] = []
        if dy != 0:
            # Traveling along the highway.
            if self._car_next_highway_exit(self._car_exit_i, dy) is not None:
                options.append((0, dy))
            options.append((1, 0))
            if self._car_next_highway_exit(self._car_exit_i, -dy) is not None:
                options.append((0, -dy))
        else:
            # Arrived from the city along the exit: join highway or go back.
            if self._car_next_highway_exit(self._car_exit_i, 1) is not None:
                options.append((0, 1))
            if self._car_next_highway_exit(self._car_exit_i, -1) is not None:
                options.append((0, -1))
            options.append((1, 0))
        if not options:
            return (-dx, -dy)
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
        dx, dy = self._car_dir
        if dx or dy:
            return float(dx), float(dy)
        rad = math.radians(self._car_heading)
        return math.cos(rad), math.sin(rad)

    def _car_approach_stop(self) -> tuple[float, float]:
        """Ideal stop-line position for the current approach."""
        if self._car_on_highway:
            return self._car_highway_stop(self._car_exit_i, self._car_dir)
        return self._car_stop_xy(*self._car_to, self._car_dir)

    def _car_refresh_neighbors(self, *, resolve: bool = True) -> None:
        """One fleet pass: leader, queue index, optional collision separation."""
        dx, dy = self._car_travel_dir()
        stop = self._car_approach_stop()
        sx = self._car_pos[0]
        sy = self._car_pos[1]
        my_behind = (stop[0] - sx) * dx + (stop[1] - sy) * dy
        on_hwy = self._car_on_highway
        my_exit = self._car_exit_i
        my_to = self._car_to
        origin_y = self._car_origin_y
        hwy_x = self._car_highway_x if on_hwy else 0.0
        follow = _CAR_FOLLOW
        touch = _CAR_TOUCH
        lane_tol = _CAR_LANE_TOL
        follow_sq = (follow - 0.01) * (follow - 0.01)
        touch_sq = (touch - 0.01) * (touch - 0.01)

        leader: CarController | None = None
        best_along = float("inf")
        queue_index = 0

        for other in self.fleet:
            if other is self:
                continue
            ox = other._car_pos[0] - sx
            oy = other._car_pos[1] - sy
            dist_sq = ox * ox + oy * oy

            other_hwy = other._car_on_highway
            if on_hwy != other_hwy:
                same_corridor = False
            elif on_hwy:
                same_corridor = abs(hwy_x - other._car_highway_x) < 0.5
            else:
                same_corridor = abs(origin_y - other._car_origin_y) < 1e-6

            odx, ody = other._car_dir
            if odx or ody:
                odx_f, ody_f = float(odx), float(ody)
            else:
                odx_f, ody_f = other._car_travel_dir()
            heading_ok = odx_f * dx + ody_f * dy >= 0.5

            if resolve:
                if dist_sq < 1e-12:
                    sx -= dx * follow
                    sy -= dy * follow
                    self._car_pos[0] = sx
                    self._car_pos[1] = sy
                    self._car_speed = 0.0
                    continue
                along = ox * dx + oy * dy
                lateral = abs(ox * -dy + oy * dx)
                same_lane = (
                    same_corridor and heading_ok and lateral <= lane_tol and along > 0.0
                )
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
                    push = touch - dist
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
                    continue
            else:
                along = ox * dx + oy * dy
                lateral = abs(ox * -dy + oy * dx)

            if not same_corridor or not heading_ok:
                continue
            if along > 0.05 and lateral <= lane_tol and along < best_along:
                best_along = along
                leader = other

            if other._car_state in ("turning", "u-turn"):
                continue
            if on_hwy:
                if other._car_exit_i != my_exit:
                    continue
            elif other._car_to != my_to:
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
        # West from the gateway: leave the city intersection toward the highway exit.
        if new_dir == (-1, 0) and gateway is not None:
            self._car_dir = new_dir
            self._car_enter_highway_from_city(gateway)
            self._car_after_cross = self._car_highway_stop(gateway, new_dir)
            self._car_clear_signals()
            self._car_state = "crossing"
            self._car_target = self._car_exit_xy(v, h, new_dir)
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
        """Maneuver at a highway exit intersection."""
        exit_i = self._car_exit_i
        cx, cy = self._car_highway_intersection_xy(exit_i)

        # Onto the exit toward the city (east).
        if new_dir == (1, 0) and old_dir != (1, 0):
            self._car_dir = new_dir
            self._car_enter_city_from_highway(exit_i)
            self._car_after_cross = self._car_stop_xy(*self._car_to, new_dir)
            if cross == 0:
                self._car_start_u_turn(new_dir)
            else:
                self._car_start_arc(old_dir, new_dir, cx, cy)
            return

        self._car_dir = new_dir

        # Continue or join travel along the highway (north/south).
        if new_dir[0] == 0 and new_dir[1] != 0:
            # Joining from the exit spur or reversing: pick a right-side lane and
            # snap onto that carriageway. Continuing straight keeps the lane.
            reversing = old_dir[1] * new_dir[1] < 0
            joining = old_dir[1] == 0 or reversing
            self._car_set_highway_lane(new_dir, pick=joining, snap=joining)
            cx, cy = self._car_highway_intersection_xy(exit_i)
            nxt = self._car_next_highway_exit(exit_i, new_dir[1])
            if nxt is None:
                # End of highway: u-turn in the new right-hand lane at this exit.
                self._car_set_highway_lane(new_dir, pick=True, snap=True)
                self._car_after_cross = self._car_highway_stop(exit_i, new_dir)
                self._car_start_u_turn(new_dir)
                return
            if dot > 0:
                self._car_exit_i = nxt
                self._car_after_cross = self._car_highway_stop(nxt, new_dir)
                self._car_clear_signals()
                self._car_state = "crossing"
                self._car_target = self._car_highway_leave(exit_i, new_dir)
                return
            if cross == 0:
                # Reverse direction: already snapped to the correct half above.
                self._car_exit_i = nxt
                self._car_after_cross = self._car_highway_stop(nxt, new_dir)
                self._car_start_u_turn(new_dir)
                return
            # Turn from the exit onto the highway in the correct right-side lane.
            self._car_exit_i = nxt
            self._car_after_cross = self._car_highway_stop(nxt, new_dir)
            self._car_start_arc(old_dir, new_dir, cx, cy)
            return

        # East while already facing east: head to the city stop.
        if new_dir == (1, 0):
            self._car_enter_city_from_highway(exit_i)
            self._car_after_cross = self._car_stop_xy(*self._car_to, new_dir)
            self._car_clear_signals()
            self._car_state = "crossing"
            self._car_target = self._car_highway_leave(exit_i, new_dir)
            return

        self._car_set_highway_lane(new_dir, pick=True, snap=True)
        self._car_after_cross = self._car_highway_stop(exit_i, new_dir)
        self._car_start_u_turn(new_dir)

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
        self._car_refresh_neighbors(resolve=True)
        # Collisions can nudge sideways; re-assert the right-hand highway lane.
        self._car_hold_highway_lane()
        self._place_car()

    def _car_task(self, task):
        dt = min(self.clock.getDt(), 0.05)
        # Targeting uses last tick's neighbor cache; we rescan once at the end.

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

        if self._car_state == "drive":
            self._car_target = self._car_drive_target()

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
