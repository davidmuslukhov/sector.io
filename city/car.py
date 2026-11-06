"""Blocky car traffic on the city road grid and highway."""

from __future__ import annotations

import math
import random

from city.materials import car_material
from city.mesh import car_template

# Body length along travel; bumper gap when queued or following.
_CAR_LENGTH = 2.0
_CAR_GAP = 1.0
_CAR_FOLLOW = _CAR_LENGTH + _CAR_GAP
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
        # Two lanes on a 5-wide road; sit in the middle of the right lane.
        self._car_lane_offset = 5.0 / 4
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
        self._place_car()
        self._car_apply_signals(None, True)
        if self not in self.fleet:
            self.fleet.append(self)

    def _car_intersection_xy(self, v: int, h: int) -> tuple[float, float]:
        return (
            self._car_origin_x + v * self._car_stride_x,
            self._car_origin_y + h * self._car_stride_y,
        )

    def _car_set_highway_lane(self, direction: tuple[int, int]) -> None:
        """Pick the right-hand highway lane for northbound or southbound travel."""
        dx, dy = direction
        if dy < 0:
            self._car_highway_x = self._car_highway_west_lane_x
        elif dy > 0:
            self._car_highway_x = self._car_highway_east_lane_x

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

    def _car_same_corridor(self, other: CarController) -> bool:
        """True when ``other`` shares this car's road corridor (city or highway)."""
        if bool(self._car_on_highway) != bool(other._car_on_highway):
            return False
        if self._car_on_highway:
            return abs(self._car_highway_x - other._car_highway_x) < 0.5
        return abs(self._car_origin_y - other._car_origin_y) < 1e-6

    def _car_find_leader(self) -> CarController | None:
        """Nearest same-lane car ahead, or None."""
        dx, dy = self._car_travel_dir()
        best: CarController | None = None
        best_along = float("inf")
        for other in self.fleet:
            if other is self:
                continue
            if not self._car_same_corridor(other):
                continue
            ox = other._car_pos[0] - self._car_pos[0]
            oy = other._car_pos[1] - self._car_pos[1]
            along = ox * dx + oy * dy
            if along <= 0.05:
                continue
            lateral = abs(ox * -dy + oy * dx)
            if lateral > _CAR_LANE_TOL:
                continue
            # Only treat cars with a similar heading as leaders in this lane.
            odx, ody = other._car_travel_dir()
            if odx * dx + ody * dy < 0.5:
                continue
            if along < best_along:
                best_along = along
                best = other
        return best

    def _car_approach_stop(self) -> tuple[float, float]:
        """Ideal stop-line position for the current approach."""
        if self._car_on_highway:
            return self._car_highway_stop(self._car_exit_i, self._car_dir)
        return self._car_stop_xy(*self._car_to, self._car_dir)

    def _car_follow_hold_xy(self) -> tuple[float, float] | None:
        """Point 1 unit bumper-gap behind the leader, or None if clear ahead."""
        leader = self._car_find_leader()
        if leader is None:
            return None
        dx, dy = self._car_travel_dir()
        return (
            leader._car_pos[0] - dx * _CAR_FOLLOW,
            leader._car_pos[1] - dy * _CAR_FOLLOW,
        )

    def _car_drive_target(self) -> tuple[float, float]:
        """Stop line, or the follow hold if a leader is closer than that."""
        stop = self._car_approach_stop()
        hold = self._car_follow_hold_xy()
        if hold is None:
            return stop
        dx, dy = self._car_travel_dir()
        # Choose whichever lies sooner along travel from our position.
        def along(pt: tuple[float, float]) -> float:
            return (pt[0] - self._car_pos[0]) * dx + (pt[1] - self._car_pos[1]) * dy

        return hold if along(hold) < along(stop) else stop

    def _car_at_stop_line(self) -> bool:
        sx, sy = self._car_approach_stop()
        return math.hypot(sx - self._car_pos[0], sy - self._car_pos[1]) < 0.2

    def _car_begin_wait(self) -> None:
        """Stop at the line (or in queue), pick the next move, and start signalling."""
        self._car_speed = 0.0
        self._car_state = "wait"
        # Queued behind another car: hold still until the gap opens; no turn yet.
        if not self._car_at_stop_line():
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
            self._car_set_highway_lane(new_dir)
            cx, cy = self._car_highway_intersection_xy(exit_i)
            nxt = self._car_next_highway_exit(exit_i, new_dir[1])
            if nxt is None:
                self._car_after_cross = self._car_highway_stop(exit_i, new_dir)
                self._car_start_u_turn(new_dir)
                return
            self._car_exit_i = nxt
            self._car_after_cross = self._car_highway_stop(nxt, new_dir)
            if dot > 0:
                self._car_clear_signals()
                self._car_state = "crossing"
                self._car_target = self._car_highway_leave(exit_i, new_dir)
                return
            if cross == 0:
                self._car_start_u_turn(new_dir)
                return
            # Turn from the exit onto the highway in the correct lane.
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

        self._car_after_cross = self._car_highway_stop(exit_i, new_dir)
        self._car_start_u_turn(new_dir)

    def _place_car(self) -> None:
        self.car.setPos(self._car_pos[0], self._car_pos[1], self._car_z)
        self.car.setH(self._car_heading)

    def _car_advance_speed(self, dt: float, dist: float | None = None) -> None:
        if dist is not None and dist < self._car_decel_dist:
            target = self._car_cruise * math.sqrt(max(dist, 0.0) / self._car_decel_dist)
            self._car_speed = min(self._car_speed, target)
        else:
            self._car_speed = min(self._car_cruise, self._car_speed + self._car_accel * dt)

    def _car_task(self, task):
        dt = min(self.clock.getDt(), 0.05)
        if self._car_state == "wait":
            # Still queued behind a leader: creep up when the 1-unit gap opens.
            if not self._car_at_stop_line():
                hold = self._car_follow_hold_xy()
                stop = self._car_approach_stop()
                goal = stop if hold is None else self._car_drive_target()
                gx = goal[0] - self._car_pos[0]
                gy = goal[1] - self._car_pos[1]
                if math.hypot(gx, gy) > 0.08:
                    self._car_state = "drive"
                    self._car_target = goal
                    self._car_speed = 0.0
                self._place_car()
                return task.cont
            self._car_wait -= dt
            self._car_update_signals(dt)
            if self._car_wait <= 0.0:
                pending = self._car_pending_dir or self._car_choose_turn()
                # Do not enter the intersection while nose-to-tail with a leader.
                leader = self._car_find_leader()
                clear = True
                if leader is not None:
                    dx, dy = self._car_travel_dir()
                    along = (
                        (leader._car_pos[0] - self._car_pos[0]) * dx
                        + (leader._car_pos[1] - self._car_pos[1]) * dy
                    )
                    clear = along >= _CAR_FOLLOW - 0.05
                if clear and self._car_may_proceed(pending):
                    self._car_begin_maneuver(pending)
                    self._place_car()
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
            self._place_car()
            return task.cont

        if self._car_state == "turning":
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
            self._place_car()
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
                self._place_car()
                return task.cont
            self._car_begin_wait()
            self._place_car()
            return task.cont

        if self._car_state == "drive":
            # Also decel for the bumper gap to a moving leader.
            hold = self._car_follow_hold_xy()
            follow_dist = None
            if hold is not None:
                follow_dist = math.hypot(
                    hold[0] - self._car_pos[0],
                    hold[1] - self._car_pos[1],
                )
            limit = dist if follow_dist is None else min(dist, follow_dist)
            self._car_advance_speed(dt, limit)
        else:
            self._car_advance_speed(dt)

        step = min(self._car_speed * dt, dist)
        self._car_pos[0] += dx / dist * step
        self._car_pos[1] += dy / dist * step
        self._car_heading = math.degrees(math.atan2(dy, dx))
        self._place_car()
        return task.cont
