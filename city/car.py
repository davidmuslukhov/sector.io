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
        # City edge (no signal): full stop, then go. Highway exits are fluid.
        self._car_unsignalized_wait = 3.0
        # Commit to exit vs continue this far before the diverge (no stop bar).
        self._car_highway_decide_dist = 22.0
        # Exit blinker only inside this range of the diverge.
        self._car_exit_signal_dist = 20.0
        # One-lane lateral slide duration; keep cruise speed the whole time.
        self._car_lane_change_duration = 1.15
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
        self._car_ring_phase = "leg"  # leg | to_corner | corner | deck
        self._car_pending_exit: int | None = None
        self._car_pending_turn_dir: tuple[int, int] | None = None
        self._car_pending_turn_exit: int | None = None
        self._car_highway_lane = 0
        self._car_highway_x = 0.0
        self._car_highway_y = 0.0
        # Rightmost lane (0) = next-exit only; 1/2 = through traffic.
        self._car_exit_intent = False
        self._car_lane_goal = 0
        self._car_lane_changing = False
        self._car_lane_change_from = 0
        self._car_lane_change_to = 0
        self._car_lane_change_t = 0.0
        self._car_lane_heading_bias = 0.0
        # Nose pitch (Panda roll on +X-forward body) while climbing/descending ramps.
        self._car_grade_pitch = 0.0
        # Elevated diamond ramp path: list of (x, y, surface_z).
        self._car_path: list[tuple[float, float, float]] = []
        self._car_path_i = 0
        self._car_path_kind: str | None = None
        self._car_path_from_z = road_top
        self._car_path_seg_len = 1.0
        self._car_surface_z = road_top
        # Optional (path, kind) started once a deck/highway u-turn finishes.
        self._car_post_u_turn_path: tuple[
            list[tuple[float, float, float]], str
        ] | None = None
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

    def _car_is_ccw(
        self,
        direction: tuple[int, int] | None = None,
        exit_i: int | None = None,
    ) -> bool:
        """True when ``direction`` matches the diamond's counter-clockwise leg."""
        diamond = self._car_diamond(exit_i)
        dx, dy = direction if direction is not None else self._car_dir
        return (dx, dy) == tuple(diamond["ccw_dir"])

    def _car_highway_half(self) -> int:
        return max(1, getattr(self, "_car_highway_lanes", 2) // 2)

    def _car_clamp_highway_lane(self, lane: int) -> int:
        return max(0, min(self._car_highway_half() - 1, int(lane)))

    def _car_highway_lane_xy(
        self,
        lane: int,
        direction: tuple[int, int],
        exit_i: int | None = None,
    ) -> tuple[float, float]:
        """World centre of a driver-relative lane on the active carriageway."""
        lane = self._car_clamp_highway_lane(lane)
        ccw = self._car_is_ccw(direction, exit_i=exit_i)
        lane_i = lane if ccw else self._car_highway_lanes - 1 - lane
        diamond = self._car_diamond(exit_i)
        side = diamond["side"]
        if side == "west":
            return self._car_west_lane_xs[lane_i], diamond["hy"]
        if side == "east":
            return self._car_east_lane_xs[lane_i], diamond["hy"]
        if side == "south":
            return diamond["hx"], self._car_south_lane_ys[lane_i]
        return diamond["hx"], self._car_north_lane_ys[lane_i]

    def _car_set_highway_lane(
        self,
        direction: tuple[int, int],
        *,
        pick: bool = False,
        snap: bool = False,
    ) -> None:
        """Stay in the three right-hand lanes for this travel direction.

        Lane preference 0 is rightmost from the driver's view (exit lane),
        2 is nearest the median. CCW uses the inner half; CW the outer.
        """
        if not self._car_diamonds:
            return
        if pick:
            self._car_highway_lane = random.randrange(self._car_highway_half())
        else:
            self._car_highway_lane = self._car_clamp_highway_lane(self._car_highway_lane)
        self._car_highway_x, self._car_highway_y = self._car_highway_lane_xy(
            self._car_highway_lane, direction,
        )
        if snap:
            diamond = self._car_diamond()
            if diamond["axis"] == "ns":
                self._car_pos[0] = self._car_highway_x
            else:
                self._car_pos[1] = self._car_highway_y

    def _car_plan_for_exit(self, _exit_i: int | None = None) -> None:
        """Choose whether the upcoming diverge is an exit and set lane goals.

        Right lane (0) is reserved for cars taking that exit; through cars use
        the middle/left lanes and slide over fluidly without stopping.
        ``_exit_i`` is the diverge being planned for (does not move ``_car_exit_i``).
        """
        self._car_exit_intent = random.random() < 0.28
        if self._car_exit_intent:
            self._car_lane_goal = 0
        elif self._car_highway_lane >= 1:
            self._car_lane_goal = self._car_highway_lane
        else:
            half = self._car_highway_half()
            choices = [lane for lane in (1, 2) if lane < half]
            self._car_lane_goal = random.choice(choices) if choices else 0
        self._car_try_start_lane_change()

    def _car_lane_change_clear(self, target_lane: int) -> bool:
        """True when the neighbouring target lane has room to slide into."""
        key = self._car_highway_lane_key(target_lane)
        dx, dy = self._car_travel_dir()
        sx, sy = self._car_pos[0], self._car_pos[1]
        for other in _FLEET_LANES.get(key, ()):
            if other is self:
                continue
            along = (other._car_pos[0] - sx) * dx + (other._car_pos[1] - sy) * dy
            if -_CAR_FOLLOW * 0.85 < along < _CAR_FOLLOW * 1.35:
                return False
        return True

    def _car_try_start_lane_change(self) -> None:
        """Begin a one-lane slide toward ``_car_lane_goal`` if the gap is clear."""
        if not self._car_on_highway or self._car_lane_changing:
            return
        if self._car_state in ("turning", "path", "u-turn", "wait"):
            return
        if self._car_ring_phase == "corner":
            return
        # Bridge deck / exit zone: right lane only (still allow slides *onto* 0).
        if self._car_ring_phase == "deck":
            self._car_lane_goal = 0
        goal = self._car_clamp_highway_lane(self._car_lane_goal)
        self._car_lane_goal = goal
        cur = self._car_highway_lane
        if cur == goal:
            return
        step = cur + (1 if goal > cur else -1)
        if self._car_ring_phase == "deck" and step != 0 and goal != 0:
            return
        if not self._car_lane_change_clear(step):
            return
        self._car_lane_change_from = cur
        self._car_lane_change_to = step
        self._car_lane_change_t = 0.0
        self._car_lane_changing = True
        # Blink toward the destination lane: higher index = left (median).
        self._car_signal = "left" if step > cur else "right"
        self._car_blink_t = 0.0

    def _car_finish_lane_change_snap(self) -> None:
        """Abort an in-progress slide and lock onto the current logical lane."""
        was_changing = self._car_lane_changing
        self._car_lane_changing = False
        self._car_lane_change_t = 0.0
        self._car_lane_heading_bias = 0.0
        if was_changing and self._car_signal in ("left", "right"):
            # Drop lane-change blinkers; exit signal is armed separately by range.
            self._car_signal = None
            self._car_apply_signals(None, True)
        self._car_set_highway_lane(self._car_dir, snap=True)
        if was_changing and self._car_ring_phase == "to_corner":
            corner = self._car_refresh_corner_target()
            self._car_target = self._car_along_highway_target(corner)

    def _car_update_lane_change(self, dt: float) -> None:
        """Advance a fluid lateral lane change without slowing the car."""
        if not self._car_lane_changing:
            if (
                self._car_on_highway
                and self._car_state == "drive"
                and self._car_highway_lane != self._car_lane_goal
            ):
                self._car_try_start_lane_change()
            return
        # Never pin to a stop mid-slide — keep rolling even if a neighbor brushes us.
        self._car_speed = max(self._car_speed, self._car_cruise * 0.65)
        duration = max(self._car_lane_change_duration, 0.35)
        self._car_lane_change_t = min(1.0, self._car_lane_change_t + dt / duration)
        t = self._car_lane_change_t
        # Smoothstep keeps the slide ease-in/out.
        u = t * t * (3.0 - 2.0 * t)
        fr = self._car_lane_change_from
        to = self._car_lane_change_to
        x0, y0 = self._car_highway_lane_xy(fr, self._car_dir)
        x1, y1 = self._car_highway_lane_xy(to, self._car_dir)
        dx, dy = self._car_dir
        if dx == 0:
            self._car_pos[0] = x0 + (x1 - x0) * u
            self._car_highway_x = self._car_pos[0]
        if dy == 0:
            self._car_pos[1] = y0 + (y1 - y0) * u
            self._car_highway_y = self._car_pos[1]
        # Mild nose lean into the move; never a stop.
        sign = 1.0 if to > fr else -1.0
        self._car_lane_heading_bias = sign * 7.0 * math.sin(t * math.pi)
        self._car_update_signals(dt)
        if t < 1.0:
            return
        self._car_highway_lane = to
        self._car_lane_changing = False
        self._car_lane_change_t = 0.0
        self._car_lane_heading_bias = 0.0
        self._car_set_highway_lane(self._car_dir, snap=True)
        if self._car_ring_phase == "to_corner":
            # Lane centre moved — refresh the fillet aim so we don't yaw at it.
            corner = self._car_refresh_corner_target()
            self._car_target = self._car_along_highway_target(corner)
        if self._car_highway_lane != self._car_lane_goal:
            self._car_try_start_lane_change()
            return
        # Arrived in the goal lane — drop lane-change blinkers.
        self._car_signal = None
        self._car_apply_signals(None, True)

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
        if self._car_lane_changing:
            # Lateral pose is owned by the lane-change lerp this frame.
            return
        self._car_set_highway_lane(self._car_dir)
        # N/S travel holds X; E/W travel holds Y.
        if dx == 0:
            self._car_pos[0] = self._car_highway_x
        if dy == 0:
            self._car_pos[1] = self._car_highway_y

    def _car_diverge_xy(
        self,
        exit_i: int,
        direction: tuple[int, int],
        *,
        commit: bool = True,
    ) -> tuple[float, float]:
        """Lane-centred diverge/merge station before an interchange."""
        diamond = self._car_diamond(exit_i)
        ccw = tuple(direction) == tuple(diamond["ccw_dir"])
        if commit:
            self._car_exit_i = exit_i
            self._car_set_highway_lane(direction)
            hx, hy = self._car_highway_x, self._car_highway_y
        else:
            hx, hy = self._car_highway_lane_xy(
                self._car_highway_lane, direction, exit_i=exit_i,
            )
        ramps = diamond["ramps"]
        key = "diverge_ccw" if ccw else "diverge_cw"
        if diamond["axis"] == "ns":
            return hx, ramps[key][1]
        return ramps[key][0], hy

    def _car_merge_xy(
        self,
        exit_i: int,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Lane-centred merge station after joining from an on-ramp."""
        diamond = self._car_diamond(exit_i)
        ccw = tuple(direction) == tuple(diamond["ccw_dir"])
        self._car_exit_i = exit_i
        self._car_set_highway_lane(direction)
        ramps = diamond["ramps"]
        key = "merge_ccw" if ccw else "merge_cw"
        if diamond["axis"] == "ns":
            return self._car_highway_x, ramps[key][1]
        return ramps[key][0], self._car_highway_y

    def _car_set_surface_z(self, surface_z: float) -> None:
        """Place the car body on a road/bridge/ramp surface."""
        self._car_surface_z = surface_z
        self._car_z = surface_z + self._car_body_half_z

    def _car_set_grade_pitch(self, dz: float, dist_xy: float) -> None:
        """Nose-down/up for pitched ramps (+X-forward body uses roll as pitch)."""
        self._car_grade_pitch = math.degrees(
            math.atan2(-dz, max(dist_xy, 0.05))
        )

    def _car_clear_grade_pitch(self) -> None:
        self._car_grade_pitch = 0.0

    def _car_smooth_path_corners(
        self,
        points: list[tuple[float, float, float]],
        *,
        corner_degrees: float = 22.0,
        radius: float = 5.5,
        samples: int = 8,
    ) -> list[tuple[float, float, float]]:
        """Replace sharp polyline bends with short circular arcs.

        Used on diamond ramps so the peel from the highway slip onto the bridge
        deck (and the reverse join) animates as a smooth turn instead of a yaw snap.
        """
        if len(points) < 3:
            return list(points)
        out: list[tuple[float, float, float]] = [points[0]]
        min_turn = math.radians(corner_degrees)
        for i in range(1, len(points) - 1):
            ax, ay, az = points[i - 1]
            bx, by, bz = points[i]
            cx, cy, cz = points[i + 1]
            # Prefer the already-emitted point when the previous corner ate into
            # this segment (keeps the fillet continuous).
            ax, ay, az = out[-1]
            vax, vay = bx - ax, by - ay
            vbx, vby = cx - bx, cy - by
            len_a = math.hypot(vax, vay)
            len_b = math.hypot(vbx, vby)
            if len_a < 0.4 or len_b < 0.4:
                out.append(points[i])
                continue
            uax, uay = vax / len_a, vay / len_a
            ubx, uby = vbx / len_b, vby / len_b
            cross = uax * uby - uay * ubx
            dot = uax * ubx + uay * uby
            turn = math.atan2(cross, dot)
            if abs(turn) < min_turn:
                out.append(points[i])
                continue
            # Never fillet grade changes — a bridge-height arc cuts through the
            # gore and leaves cars floating beside the pitched arterial ramp.
            if max(abs(az - bz), abs(bz - cz), abs(az - cz)) > 0.15:
                out.append(points[i])
                continue
            # Fillet trim; keep enough of each leg so arcs don't collapse.
            trim = radius * abs(math.tan(turn * 0.5))
            trim = min(trim, len_a * 0.42, len_b * 0.42)
            if trim < 0.35:
                out.append(points[i])
                continue
            t1x, t1y = bx - uax * trim, by - uay * trim
            t2x, t2y = bx + ubx * trim, by + uby * trim
            # Arc centre sits on the inside of the turn.
            if cross > 0.0:
                nx, ny = -uay, uax
            else:
                nx, ny = uay, -uax
            acx = t1x + nx * radius
            acy = t1y + ny * radius
            a0 = math.atan2(t1y - acy, t1x - acx)
            a1 = math.atan2(t2y - acy, t2x - acx)
            # Sweep the short way matching the turn sign.
            sweep = a1 - a0
            if cross > 0.0 and sweep < 0.0:
                sweep += 2.0 * math.pi
            elif cross < 0.0 and sweep > 0.0:
                sweep -= 2.0 * math.pi
            z1 = az + (bz - az) * min(1.0, max(0.0, 1.0 - trim / len_a))
            z2 = bz + (cz - bz) * min(1.0, max(0.0, trim / len_b))
            # Drop a near-duplicate of the previous point at T1.
            if math.hypot(t1x - out[-1][0], t1y - out[-1][1]) > 0.2:
                out.append((t1x, t1y, z1))
            for step in range(1, samples):
                t = step / samples
                ang = a0 + sweep * t
                z = z1 + (z2 - z1) * t
                out.append(
                    (acx + radius * math.cos(ang), acy + radius * math.sin(ang), z)
                )
            out.append((t2x, t2y, z2))
        out.append(points[-1])
        # Collapse accidental near-duplicates from consecutive fillets.
        cleaned: list[tuple[float, float, float]] = []
        for pt in out:
            if cleaned and math.hypot(pt[0] - cleaned[-1][0], pt[1] - cleaned[-1][1]) < 0.18:
                cleaned[-1] = pt
                continue
            cleaned.append(pt)
        return cleaned

    def _car_densify_grade_segments(
        self,
        points: list[tuple[float, float, float]],
        *,
        spacing: float = 1.15,
    ) -> list[tuple[float, float, float]]:
        """Sample pitched ramp segments so descent/ascent stays glued to the slab."""
        if len(points) < 2:
            return list(points)
        out: list[tuple[float, float, float]] = [points[0]]
        for i in range(1, len(points)):
            x0, y0, z0 = out[-1]
            x1, y1, z1 = points[i]
            dist = math.hypot(x1 - x0, y1 - y0)
            dz = z1 - z0
            if abs(dz) > 0.2 and dist > spacing:
                steps = max(2, int(math.ceil(dist / spacing)))
                for step in range(1, steps):
                    t = step / steps
                    out.append(
                        (
                            x0 + (x1 - x0) * t,
                            y0 + (y1 - y0) * t,
                            z0 + dz * t,
                        )
                    )
            out.append(points[i])
        return out

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
        # Smooth flat highway↔bridge corners; densify pitched runs for descent.
        if kind in ("exit_city", "enter_ccw", "enter_cw", "enter_deck"):
            cleaned = self._car_smooth_path_corners(cleaned)
            cleaned = self._car_densify_grade_segments(cleaned)
        if not cleaned:
            self._car_finish_path(kind)
            return
        self._car_path = cleaned
        self._car_path_i = 0
        self._car_path_kind = kind
        self._car_state = "path"
        # Ease through ramp fillets so the turn reads; still faster than a crawl.
        if kind in ("exit_city", "enter_ccw", "enter_cw", "enter_deck"):
            self._car_speed = min(
                max(self._car_speed, self._car_cruise * 0.35),
                self._car_cruise * 0.72,
            )
        else:
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
        self._car_set_grade_pitch(cleaned[0][2] - self._car_path_from_z, self._car_path_seg_len)
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
            self._car_heading = math.degrees(math.atan2(into[1], into[0]))
            self._car_enter_city_from_highway(exit_i)
            self._car_set_surface_z(grade)
            self._car_clear_grade_pitch()
            # Path already ends on the city stop — join the intersection queue
            # instead of aiming at a stop behind us (that reverse caused piles).
            stop = self._car_stop_xy(*self._car_to, into)
            self._car_pos[0], self._car_pos[1] = stop
            self._car_after_cross = stop
            self._car_target = stop
            self._car_clear_signals()
            self._car_refresh_neighbors(resolve=False)
            self._car_begin_wait()
            return

        if kind == "enter_deck":
            # Arrived on the bridge deck in the right lane; choose join / return.
            self._car_on_highway = True
            self._car_ring_phase = "deck"
            old_dir = self._car_dir
            city_ix = diamond["ramps"]["city_ix"]
            deck_xy = self._car_right_lane_xy(city_ix[0], city_ix[1], old_dir)
            self._car_pos[0], self._car_pos[1] = deck_xy
            self._car_force_right_highway_lane(old_dir, snap=False)
            self._car_set_surface_z(diamond.get("bridge_top", grade))
            self._car_clear_grade_pitch()
            self._car_speed = max(self._car_speed, self._car_cruise * 0.5)
            choice = self._car_choose_highway_turn()
            # Arm blinkers before the maneuver so the turn reads on the deck.
            reverse = choice == (-old_dir[0], -old_dir[1])
            self._car_arm_turn_signal(
                old_dir, choice, fallback="left" if reverse else None,
            )
            cross = old_dir[0] * choice[1] - old_dir[1] * choice[0]
            dot = old_dir[0] * choice[0] + old_dir[1] * choice[1]
            self._car_begin_highway_maneuver(old_dir, choice, cross, dot)
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
            # Merge into the right lane, then plan lanes for the upcoming exit.
            self._car_force_right_highway_lane(new_dir, snap=True)
            self._car_set_surface_z(grade)
            self._car_clear_grade_pitch()
            merge = self._car_merge_xy(exit_i, new_dir)
            self._car_pos[0], self._car_pos[1] = merge
            nxt = self._car_next_highway_exit(exit_i, new_dir)
            self._car_pending_exit = nxt
            corner = self._car_corner_approach(exit_i, new_dir)
            self._car_clear_signals()
            self._car_state = "drive"
            self._car_target = corner
            self._car_after_cross = corner
            self._car_plan_for_exit(nxt)
            return

        self._car_set_surface_z(grade)
        self._car_clear_grade_pitch()
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
        *,
        lane: int | None = None,
        commit: bool = True,
    ) -> tuple[float, float]:
        """Point at the end of the current straight leg, before the corner arc.

        ``commit=False`` peeks the aim point for ``lane`` without moving highway
        lane state — needed while retargeting during a lane change.
        """
        if lane is None:
            lane = self._car_highway_lane
        if commit:
            self._car_exit_i = exit_i
            self._car_highway_lane = self._car_clamp_highway_lane(lane)
            self._car_set_highway_lane(direction)
            hx, hy = self._car_highway_x, self._car_highway_y
        else:
            hx, hy = self._car_highway_lane_xy(lane, direction, exit_i=exit_i)
        diamond = self._car_diamond(exit_i)
        dx, dy = direction
        if diamond["side"] == "west":
            y = self._car_ns_y1 if dy > 0 else self._car_ns_y0
            return hx, y
        if diamond["side"] == "east":
            y = self._car_ns_y0 if dy < 0 else self._car_ns_y1
            return hx, y
        if diamond["side"] == "south":
            x = self._car_ew_x0 if dx < 0 else self._car_ew_x1
            return x, hy
        x = self._car_ew_x1 if dx > 0 else self._car_ew_x0
        return x, hy

    def _car_along_highway_target(
        self,
        station: tuple[float, float],
    ) -> tuple[float, float]:
        """Keep the current cross-highway pose; aim only along travel."""
        dx, dy = self._car_dir
        if abs(dx) >= abs(dy):
            return station[0], self._car_pos[1]
        return self._car_pos[0], station[1]

    def _car_refresh_corner_target(self) -> tuple[float, float]:
        """Retarget the fillet for the lane we are in (or sliding into)."""
        aim_lane = (
            self._car_lane_change_to
            if self._car_lane_changing
            else self._car_highway_lane
        )
        corner = self._car_corner_approach(
            self._car_exit_i,
            self._car_dir,
            lane=aim_lane,
            commit=False,
        )
        self._car_after_cross = corner
        return corner

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
        """Quarter-turn around a beltway corner centre onto the next leg.

        Radius and start angle come from the lane-centre approach point, not the
        (possibly drifted) body pose, so every car in a lane shares one annulus.
        """
        cross = old_dir[0] * new_dir[1] - old_dir[1] * new_dir[0]
        sign = 1.0 if cross > 0 else -1.0
        self._car_state = "turning"
        self._car_arc_center = (cx, cy)
        # Snap onto the ideal approach before measuring the arc.
        self._car_set_highway_lane(old_dir, pick=False, snap=True)
        ax, ay = self._car_corner_approach(self._car_exit_i, old_dir)
        self._car_pos[0], self._car_pos[1] = ax, ay
        rx = ax - cx
        ry = ay - cy
        self._car_arc_radius = max(math.hypot(rx, ry), 1.0)
        self._car_arc_sign = sign
        self._car_arc_angle = math.atan2(ry, rx)
        self._car_arc_end = self._car_arc_angle + sign * (math.pi / 2)
        self._car_snap_arc_pose()

    def _car_commit_corner_turn(self) -> None:
        """Apply the post-corner carriageway once the quarter-arc finishes."""
        new_dir = self._car_pending_turn_dir
        nxt = self._car_pending_turn_exit
        self._car_pending_turn_dir = None
        self._car_pending_turn_exit = None
        if new_dir is None or nxt is None:
            return
        self._car_exit_i = nxt
        self._car_dir = new_dir
        self._car_ring_phase = "leg"
        self._car_set_highway_lane(new_dir, pick=False, snap=True)
        self._car_heading = math.degrees(math.atan2(new_dir[1], new_dir[0]))
        self._car_target = self._car_after_cross

    def _car_corner_entry_clear(self) -> bool:
        """True when this lane's corner arc has room to accept another car."""
        for other in _FLEET_LANES.get(self._car_lane_key(), ()):
            if other is self:
                continue
            if not (
                other._car_ring_phase == "corner"
                or (other._car_on_highway and other._car_state == "turning")
            ):
                continue
            # Arc length from the other's start angle to its current pose.
            start = other._car_arc_end - other._car_arc_sign * (math.pi / 2)
            progressed = abs(other._car_arc_angle - start) * other._car_arc_radius
            if progressed < _CAR_FOLLOW:
                return False
        return True

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
        self._car_finish_lane_change_snap()
        # Keep approach dir/exit through the arc so followers still see this car
        # as their same-lane leader. Flipping early made the pack stack mid-corner.
        self._car_pending_turn_dir = new_dir
        self._car_pending_turn_exit = nxt
        self._car_pending_exit = None
        self._car_pending_dir = None
        self._car_ring_phase = "corner"
        # Next goal is the diverge on the *next* leg — peek without committing.
        self._car_after_cross = self._car_diverge_xy(nxt, new_dir, commit=False)
        # Keep the exit/through lane plan chosen before this corner.
        self._car_lane_goal = 0 if self._car_exit_intent else max(1, self._car_highway_lane)
        if not self._car_exit_intent and self._car_lane_goal < 1:
            self._car_lane_goal = min(1, self._car_highway_half() - 1)
        # Corner quarter-turn keeps its blinker through the arc animation.
        self._car_arm_turn_signal(old_dir, new_dir)
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

    def _car_right_lane_xy(
        self,
        x: float,
        y: float,
        direction: tuple[int, int],
    ) -> tuple[float, float]:
        """Offset a centre-line point into the right-hand travel lane."""
        lx, ly = self._car_lane_shift(direction)
        return x + lx, y + ly

    def _car_force_right_highway_lane(
        self,
        direction: tuple[int, int] | None = None,
        *,
        snap: bool = False,
    ) -> None:
        """Lock onto driver lane 0 (rightmost) for bridge / exit work."""
        direction = self._car_dir if direction is None else direction
        self._car_highway_lane = 0
        self._car_lane_goal = 0
        self._car_lane_changing = False
        self._car_lane_change_t = 0.0
        self._car_lane_heading_bias = 0.0
        self._car_set_highway_lane(direction, pick=False, snap=snap)

    def _car_arterial_anchors(
        self, exit_i: int | None = None,
    ) -> set[tuple[float, float]]:
        """Diamond arterial / bridge centre-line points (not slip-ramp centres)."""
        ramps = self._car_diamond(exit_i)["ramps"]
        anchors = {
            (round(ramps["city_end"][0], 3), round(ramps["city_end"][1], 3)),
            (round(ramps["city_ix"][0], 3), round(ramps["city_ix"][1], 3)),
            (round(ramps["outer_ix"][0], 3), round(ramps["outer_ix"][1], 3)),
            (round(ramps["outer_end"][0], 3), round(ramps["outer_end"][1], 3)),
        }
        # Throat points sit on the arterial centre-line where slips merge.
        for key in ("city_throat", "outer_throat"):
            if key in ramps:
                anchors.add((round(ramps[key][0], 3), round(ramps[key][1], 3)))
        return anchors

    def _car_shift_arterial_path(
        self,
        points: list[tuple[float, float, float]],
        direction: tuple[int, int],
        exit_i: int | None = None,
    ) -> list[tuple[float, float, float]]:
        """Move bridge/arterial waypoints into the right lane; leave slip ramps."""
        anchors = self._car_arterial_anchors(exit_i)
        lx, ly = self._car_lane_shift(direction)
        shifted: list[tuple[float, float, float]] = []
        for x, y, z in points:
            if (round(x, 3), round(y, 3)) in anchors:
                shifted.append((x + lx, y + ly, z))
            else:
                shifted.append((x, y, z))
        return shifted

    def _car_terminate_exit_at_city_stop(
        self,
        path: list[tuple[float, float, float]],
        exit_i: int,
        into: tuple[int, int],
    ) -> list[tuple[float, float, float]]:
        """Keep the ramp-foot ``city_end`` then roll flat to the city stop.

        Replacing ``city_end`` with the stop shortens the pitched descent so Z
        no longer matches the arterial slab (cars sink or float). Preserve the
        grade foot, then append the stop at the same grade height.
        """
        diamond = self._car_diamond(exit_i)
        grade = diamond.get("grade_top", self._car_grade_z)
        stop = self._car_stop_xy(diamond["city_v"], diamond["city_h"], into)
        stop_pt = (stop[0], stop[1], grade)
        if not path:
            return [stop_pt]
        out = list(path)
        # Ensure the last elevated→grade foot lands at grade_top.
        fx, fy, fz = out[-1]
        if abs(fz - grade) > 0.05:
            # Path somehow still elevated — drop a grade foot at city_end then stop.
            end = diamond["ramps"]["city_end"]
            lx, ly = self._car_lane_shift(into)
            out.append((end[0] + lx, end[1] + ly, grade))
            fx, fy, fz = out[-1]
        if math.hypot(fx - stop[0], fy - stop[1]) < 0.4:
            out[-1] = stop_pt
        else:
            out.append(stop_pt)
        return out

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
        """Fluid interchange choice: continue, exit, or join a ring direction."""
        diamond = self._car_diamond()
        into = tuple(diamond["into_city"])
        ccw = tuple(diamond["ccw_dir"])
        cw = tuple(diamond["cw_dir"])
        dx, dy = self._car_dir
        if (dx, dy) in (ccw, cw):
            # Exit only from the right lane after an earlier intent + lane change.
            if (
                self._car_exit_intent
                and self._car_highway_lane == 0
                and not self._car_lane_changing
            ):
                return into
            return (dx, dy)
        # Bridge deck after climbing from the city.
        return random.choice([ccw, cw, into])

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

    def _car_arm_turn_signal(
        self,
        old_dir: tuple[int, int],
        new_dir: tuple[int, int],
        *,
        fallback: str | None = None,
    ) -> None:
        """Blink for a pending turn; keep an explicit fallback for U-turns."""
        side = self._car_signal_side(old_dir, new_dir)
        if side is None:
            side = fallback
        if side is None:
            return
        self._car_signal = side
        self._car_blink_t = 0.0
        self._car_signal_applied = None
        self._car_update_signals(0.0)

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
        # During arcs, ``_car_dir`` is already the post-turn cardinal; use the
        # tangent heading so follow/collision stay circumferential, not radial.
        if self._car_state in ("path", "turning"):
            rad = math.radians(self._car_heading)
            return math.cos(rad), math.sin(rad)
        dx, dy = self._car_dir
        if dx or dy:
            return float(dx), float(dy)
        rad = math.radians(self._car_heading)
        return math.cos(rad), math.sin(rad)

    def _car_snap_arc_pose(self) -> None:
        """Lock position and heading onto the active turn arc."""
        acx, acy = self._car_arc_center
        radius = self._car_arc_radius
        angle = self._car_arc_angle
        self._car_pos[0] = acx + radius * math.cos(angle)
        self._car_pos[1] = acy + radius * math.sin(angle)
        self._car_heading = math.degrees(
            angle + self._car_arc_sign * (math.pi / 2)
        )

    def _car_approach_stop(self) -> tuple[float, float]:
        """Ideal stop-line position for the current approach."""
        if self._car_on_highway:
            if self._car_state == "turning" or self._car_ring_phase == "corner":
                # Mid-corner: aim at the already-computed next-leg diverge.
                return tuple(self._car_after_cross)
            if self._car_ring_phase == "to_corner":
                return self._car_refresh_corner_target()
            if self._car_ring_phase == "deck":
                return tuple(self._car_diamond()["ramps"]["city_ix"])
            # Highway uses the diverge as a decision point, not a stop bar.
            return self._car_diverge_xy(self._car_exit_i, self._car_dir)
        return self._car_stop_xy(*self._car_to, self._car_dir)

    def _car_highway_continue(self, direction: tuple[int, int]) -> None:
        """Stay on the ring past this interchange and head for the next corner."""
        exit_i = self._car_exit_i
        self._car_dir = direction
        self._car_set_highway_lane(direction, pick=False, snap=False)
        nxt = self._car_next_highway_exit(exit_i, direction)
        self._car_pending_exit = nxt
        self._car_pending_dir = None
        self._car_ring_phase = "to_corner"
        corner = self._car_corner_approach(exit_i, direction)
        self._car_clear_signals()
        self._car_state = "drive"
        self._car_target = corner
        self._car_after_cross = corner
        # Plan lanes early for the exit beyond the upcoming corner.
        self._car_plan_for_exit(nxt)

    def _car_commit_highway(self, choice: tuple[int, int] | None = None) -> None:
        """Apply an interchange choice without stopping."""
        old_dir = self._car_dir
        new_dir = choice if choice is not None else (
            self._car_pending_dir or self._car_choose_highway_turn()
        )
        self._car_pending_dir = None
        cross = old_dir[0] * new_dir[1] - old_dir[1] * new_dir[0]
        dot = old_dir[0] * new_dir[0] + old_dir[1] * new_dir[1]
        self._car_begin_highway_maneuver(old_dir, new_dir, cross, dot)

    def _car_dist_to_diverge(self) -> float:
        """Distance to the active interchange diverge along this carriageway."""
        diverge = self._car_diverge_xy(self._car_exit_i, self._car_dir)
        return math.hypot(diverge[0] - self._car_pos[0], diverge[1] - self._car_pos[1])

    def _car_update_exit_signal(self) -> None:
        """Arm the off-ramp blinker only within ``_car_exit_signal_dist``."""
        if not self._car_on_highway or not self._car_exit_intent:
            return
        if self._car_lane_changing:
            return
        if self._car_ring_phase != "leg" or self._car_state not in ("drive", "crossing"):
            return
        dist = self._car_dist_to_diverge()
        if dist <= self._car_exit_signal_dist:
            if self._car_signal != "right":
                self._car_signal = "right"
                self._car_blink_t = 0.0
        elif self._car_signal == "right":
            self._car_signal = None
            self._car_apply_signals(None, True)

    def _car_maybe_decide_highway(self) -> bool:
        """Early exit/continue commit on approach so the diverge stays fluid.

        Returns True when this tick already started a new maneuver/target.
        """
        if not self._car_on_highway or self._car_ring_phase != "leg":
            return False
        if self._car_state != "drive":
            return False
        dx, dy = self._car_dir
        if dx == 0 and dy == 0:
            return False
        diamond = self._car_diamond()
        ccw = tuple(diamond["ccw_dir"])
        cw = tuple(diamond["cw_dir"])
        if (dx, dy) not in (ccw, cw):
            return False
        into = tuple(diamond["into_city"])
        diverge = self._car_diverge_xy(self._car_exit_i, self._car_dir)
        dist = math.hypot(diverge[0] - self._car_pos[0], diverge[1] - self._car_pos[1])
        # Keep pushing toward the right lane if we still intend to exit.
        if self._car_exit_intent and (
            self._car_highway_lane != 0 or self._car_lane_changing
        ):
            self._car_lane_goal = 0
            self._car_try_start_lane_change()
            if dist < 6.0:
                # Too close and still not in the exit lane — skip this off-ramp.
                self._car_exit_intent = False
                self._car_pending_dir = None
                self._car_highway_continue((dx, dy))
                return True
            self._car_target = diverge
            return False
        if self._car_pending_dir is None:
            if dist > self._car_highway_decide_dist:
                return False
            self._car_pending_dir = self._car_choose_highway_turn()
            if self._car_pending_dir == (dx, dy):
                self._car_highway_continue(self._car_pending_dir)
                return True
            if self._car_pending_dir == into:
                # Blinker is owned by ``_car_update_exit_signal`` (20-unit gate).
                self._car_target = diverge
                self._car_after_cross = diverge
                return False
            self._car_target = diverge
            return False
        if dist <= max(self._car_speed * 0.05, 0.35):
            self._car_pos[0], self._car_pos[1] = diverge
            self._car_commit_highway(self._car_pending_dir)
            return True
        self._car_target = diverge
        return False

    def _car_highway_lane_key(self, lane: int) -> tuple:
        """Fleet bucket for one driver-relative highway lane."""
        dx, dy = self._car_dir if (self._car_dir[0] or self._car_dir[1]) else self._car_travel_dir()
        side = self._car_diamond()["side"] if self._car_diamonds else "?"
        return ("h", side, int(self._car_clamp_highway_lane(lane)), int(dx), int(dy))

    def _car_is_exit_stream(self) -> bool:
        """True while draining a diamond exit into the city approach."""
        if self._car_path_kind == "exit_city":
            return True
        if self._car_on_highway or not self._car_diamonds:
            return False
        diamond = self._car_diamond(self._car_exit_i)
        if self._car_to != (diamond["city_v"], diamond["city_h"]):
            return False
        return tuple(self._car_dir) == tuple(diamond["into_city"])

    def _car_lane_key(self) -> tuple:
        """Same travel lane / twin city corridor for leader search."""
        # One shared bucket for the whole exit stream so ramp cars keep yielding
        # to leaders that have already handed off onto the city stop.
        if self._car_is_exit_stream():
            return ("x", int(self._car_exit_i))
        dx, dy = self._car_dir if (self._car_dir[0] or self._car_dir[1]) else self._car_travel_dir()
        if self._car_on_highway:
            lane = self._car_highway_lane
            if self._car_lane_changing and self._car_lane_change_t >= 0.5:
                lane = self._car_lane_change_to
            return self._car_highway_lane_key(lane)
        return ("c", round(self._car_origin_y), int(dx), int(dy))

    def _car_queue_key(self) -> tuple:
        """Cars sharing one stop-line queue."""
        if self._car_is_exit_stream():
            return ("x", int(self._car_exit_i))
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

    def _car_start_u_turn(
        self,
        new_dir: tuple[int, int],
        *,
        clear_signals: bool = True,
    ) -> None:
        """Spin in place to face ``new_dir``, then drive to ``_car_after_cross``."""
        if clear_signals:
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
        self._car_pending_dir = None

        if self._car_on_highway:
            # Keep speed through ramps and ring continues — no intersection stop.
            self._car_begin_highway_maneuver(old_dir, new_dir, cross, dot)
            return

        self._car_speed = 0.0

        v, h = self._car_to
        gateway = self._car_gateway_exit_i()
        if gateway is not None:
            diamond = self._car_diamonds[gateway]
            into = tuple(diamond["into_city"])
            toward_hwy = (-into[0], -into[1])
            if new_dir == toward_hwy:
                self._car_dir = new_dir
                self._car_enter_highway_from_city(gateway)
                # Keep the approach blinker through the climb onto the deck.
                self._car_arm_turn_signal(old_dir, new_dir)
                # Leave the city node, then climb the arterial onto the bridge deck.
                grade = diamond.get("grade_top", self._car_grade_z)
                city_end = diamond["ramps"]["city_end"]
                city_ix = diamond["ramps"]["city_ix"]
                bridge_top = diamond.get("bridge_top", grade)
                leave = self._car_exit_xy(v, h, new_dir)
                end_xy = self._car_right_lane_xy(city_end[0], city_end[1], new_dir)
                ix_xy = self._car_right_lane_xy(city_ix[0], city_ix[1], new_dir)
                self._car_begin_path(
                    [
                        (leave[0], leave[1], grade),
                        (end_xy[0], end_xy[1], grade),
                        (ix_xy[0], ix_xy[1], bridge_top),
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
            self._car_arm_turn_signal(old_dir, new_dir, fallback="left")
            self._car_start_u_turn(new_dir, clear_signals=False)
            return

        self._car_arm_turn_signal(old_dir, new_dir)
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
            self._car_exit_intent = False
            self._car_finish_lane_change_snap()
            self._car_force_right_highway_lane(old_dir, snap=False)
            # Exit is always a right peel; keep blinkers through the bridge path.
            self._car_arm_turn_signal(old_dir, new_dir, fallback="right")
            if old_dir in (ccw, cw):
                route_name = "exit_ccw" if self._car_is_ccw(old_dir) else "exit_cw"
                diverge = self._car_diverge_xy(exit_i, old_dir)
                route = self._car_route_points(route_name, exit_i)
                # First ramp point shares the diverge's along-station but sits on
                # the slip curb — prepending it causes a pure lateral 90° yaw.
                # Skip that gore point and peel diagonally into the slip lane.
                if route:
                    r0x, r0y, _r0z = route[0]
                    odx, ody = old_dir
                    along_same = abs((r0x - diverge[0]) * odx + (r0y - diverge[1]) * ody) < 0.75
                    if along_same and len(route) > 1:
                        route = route[1:]
                path = [
                    (diverge[0], diverge[1], grade),
                    *route,
                ]
                path = self._car_shift_arterial_path(path, into, exit_i)
                path = self._car_terminate_exit_at_city_stop(path, exit_i, into)
                self._car_begin_path(path, kind="exit_city")
                return
            # Already on the deck facing the wrong way: U-turn, then descend
            # the arterial in the right lane (turning animation, not a snap).
            city_end = diamond["ramps"]["city_end"]
            city_ix = diamond["ramps"]["city_ix"]
            bridge_top = diamond.get("bridge_top", grade)
            ix_xy = self._car_right_lane_xy(city_ix[0], city_ix[1], into)
            end_xy = self._car_right_lane_xy(city_end[0], city_end[1], into)
            self._car_dir = into
            stop = self._car_stop_xy(diamond["city_v"], diamond["city_h"], into)
            self._car_post_u_turn_path = (
                [
                    (ix_xy[0], ix_xy[1], bridge_top),
                    (end_xy[0], end_xy[1], grade),
                    (stop[0], stop[1], grade),
                ],
                "exit_city",
            )
            self._car_after_cross = stop
            self._car_start_u_turn(into, clear_signals=False)
            return

        if new_dir in (ccw, cw):
            joining = old_dir not in (ccw, cw)
            reversing = old_dir[0] * new_dir[0] + old_dir[1] * new_dir[1] < 0
            if joining:
                # From the bridge deck onto an on-ramp, then merge in lane 0.
                self._car_force_right_highway_lane(old_dir, snap=False)
                self._car_arm_turn_signal(old_dir, new_dir)
                route_name = "enter_ccw" if new_dir == ccw else "enter_cw"
                # enter_* routes start at city_end; deck arrival is already at city_ix.
                path = self._car_route_points(route_name, exit_i)
                if len(path) >= 2:
                    path = path[1:]  # drop city_end
                city_ix = diamond["ramps"]["city_ix"]
                bridge_top = diamond.get("bridge_top", grade)
                # City-side slips merge mid-arterial (no city_ix on the route).
                # Prepend the deck abutment so we descend onto the throat.
                if path:
                    p0x, p0y, _p0z = path[0]
                    if math.hypot(p0x - city_ix[0], p0y - city_ix[1]) > 0.75:
                        path = [(city_ix[0], city_ix[1], bridge_top), *path]
                # Keep the deck waypoint in the arrival right lane.
                if path:
                    x, y, z = path[0]
                    rx, ry = self._car_right_lane_xy(x, y, old_dir)
                    path[0] = (rx, ry, z)
                self._car_begin_path(path, kind=route_name)
                return

            if cross == 0 and reversing:
                self._car_dir = new_dir
                self._car_force_right_highway_lane(new_dir, snap=True)
                nxt = self._car_next_highway_exit(exit_i, new_dir)
                self._car_pending_exit = nxt
                self._car_ring_phase = "to_corner"
                corner = self._car_corner_approach(exit_i, new_dir)
                self._car_after_cross = corner
                self._car_arm_turn_signal(old_dir, new_dir, fallback="left")
                self._car_start_u_turn(new_dir, clear_signals=False)
                return
            # Continue past the interchange — no leave-box crossing stop.
            self._car_highway_continue(new_dir)
            return

        # Facing back toward the city from the deck (non-cardinal leftover).
        city_end = diamond["ramps"]["city_end"]
        city_ix = diamond["ramps"]["city_ix"]
        bridge_top = diamond.get("bridge_top", grade)
        self._car_force_right_highway_lane(into, snap=False)
        self._car_arm_turn_signal(old_dir, into, fallback="left")
        ix_xy = self._car_right_lane_xy(city_ix[0], city_ix[1], into)
        end_xy = self._car_right_lane_xy(city_end[0], city_end[1], into)
        stop = self._car_stop_xy(diamond["city_v"], diamond["city_h"], into)
        self._car_begin_path(
            [
                (ix_xy[0], ix_xy[1], bridge_top),
                (end_xy[0], end_xy[1], grade),
                (stop[0], stop[1], grade),
            ],
            kind="exit_city",
        )

    def _place_car(self) -> None:
        self.car.setPos(self._car_pos[0], self._car_pos[1], self._car_z)
        self.car.setH(self._car_heading + self._car_lane_heading_bias)
        # +X-forward body: Panda pitch is around X (roll), so grade uses roll.
        self.car.setP(0.0)
        self.car.setR(self._car_grade_pitch)

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
        # Corner/intersection arcs are radius-locked the same way: a push along
        # the post-turn cardinal walks cars off the pad (outer curb is tight).
        resolve = self._car_state not in ("path", "turning")
        self._car_refresh_neighbors(resolve=resolve)
        if self._car_state == "turning":
            # Keep the annulus pose even if a neighbor scan mutates nothing else.
            self._car_snap_arc_pose()
        # Collisions can nudge sideways; re-assert the right-hand highway lane.
        self._car_hold_highway_lane()
        # Collision resolution may zero speed; lane changes must keep rolling.
        if self._car_lane_changing:
            self._car_speed = max(self._car_speed, self._car_cruise * 0.65)
        self._place_car()

    def _car_task(self, task):
        dt = min(self.clock.getDt(), 0.05)
        # Targeting uses last tick's neighbor cache; we rescan once at the end.
        if self._car_on_highway and self._car_state == "drive":
            self._car_update_lane_change(dt)
            self._car_update_exit_signal()

        if self._car_state == "path":
            if not self._car_path or self._car_path_i >= len(self._car_path):
                self._car_finish_path()
                self._car_finish_frame()
                return task.cont
            # Exit streams yield to any same-bucket leader (still on the ramp or
            # already queued at the city stop). Other ramp kinds only yield to
            # live path leaders so underpass traffic does not pin climbs.
            leader = self._nb_leader
            yield_to_leader = False
            if (
                leader is not None
                and self._nb_leader_along is not None
                and self._nb_leader_along < _CAR_FOLLOW - 0.05
            ):
                if self._car_path_kind == "exit_city":
                    yield_to_leader = True
                elif (
                    leader._car_state == "path"
                    and leader._car_exit_i == self._car_exit_i
                ):
                    yield_to_leader = True
            if yield_to_leader:
                self._car_speed = max(0.0, self._car_speed - self._car_accel * dt)
                if self._car_signal is not None:
                    self._car_update_signals(dt)
                self._car_finish_frame()
                return task.cont
            tx, ty, tz = self._car_path[self._car_path_i]
            dx = tx - self._car_pos[0]
            dy = ty - self._car_pos[1]
            dist = math.hypot(dx, dy)
            last_exit_wp = (
                self._car_path_kind == "exit_city"
                and self._car_path_i >= len(self._car_path) - 1
            )
            if dist <= max(self._car_speed * dt, 0.08):
                # Don't snap onto the shared city stop while a leader still owns it.
                if (
                    last_exit_wp
                    and self._nb_leader_along is not None
                    and self._nb_leader_along < _CAR_FOLLOW - 0.05
                ):
                    self._car_speed = 0.0
                    if self._car_signal is not None:
                        self._car_update_signals(dt)
                    self._car_finish_frame()
                    return task.cont
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
                    self._car_set_grade_pitch(
                        nxt[2] - tz, self._car_path_seg_len,
                    )
                if self._car_signal is not None:
                    self._car_update_signals(dt)
                self._car_finish_frame()
                return task.cont
            # Decel into the bumper gap when an exit leader is ahead.
            limit = dist
            if (
                self._car_path_kind == "exit_city"
                and self._nb_leader_along is not None
            ):
                limit = min(limit, max(0.0, self._nb_leader_along - _CAR_GAP))
            self._car_advance_speed(dt, limit)
            step = min(self._car_speed * dt, dist)
            if dist > 1e-6:
                self._car_pos[0] += dx / dist * step
                self._car_pos[1] += dy / dist * step
                self._car_heading = math.degrees(math.atan2(dy, dx))
            remain = math.hypot(tx - self._car_pos[0], ty - self._car_pos[1])
            frac = 1.0 - min(1.0, remain / self._car_path_seg_len)
            # Stay glued to the pitched slab; nose follows the grade.
            self._car_set_surface_z(
                self._car_path_from_z + (tz - self._car_path_from_z) * frac
            )
            self._car_set_grade_pitch(
                tz - self._car_path_from_z, self._car_path_seg_len,
            )
            if self._car_signal is not None:
                self._car_update_signals(dt)
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
            if self._car_signal is not None:
                self._car_update_signals(dt)
            # Match turn rate to cruise so the spin feels like a tight pivot.
            rate = math.degrees(self._car_cruise / max(self._car_stop_offset, 1.0))
            step = rate * dt
            remain = self._car_u_turn_span - self._car_u_turn_progress
            if step >= remain:
                self._car_heading = self._car_heading_to
                pending = self._car_post_u_turn_path
                self._car_post_u_turn_path = None
                if pending is not None:
                    path, kind = pending
                    self._car_begin_path(path, kind=kind)
                else:
                    self._car_target = self._car_after_cross
                    self._car_state = "drive"
                    self._car_clear_signals()
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
            # Pause the arc if we'd nose into another car; stay glued to the pad.
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
                self._car_snap_arc_pose()
                if self._car_pending_turn_dir is not None:
                    self._car_commit_corner_turn()
                else:
                    self._car_heading = math.degrees(
                        math.atan2(self._car_dir[1], self._car_dir[0])
                    )
                    self._car_target = self._car_after_cross
                self._car_state = "drive"
                self._car_clear_signals()
            else:
                self._car_arc_angle += angle_step
                self._car_snap_arc_pose()
            self._car_finish_frame()
            return task.cont

        if self._car_state == "drive" and self._car_on_highway:
            if self._car_maybe_decide_highway():
                self._car_finish_frame()
                return task.cont
            if self._car_ring_phase == "leg":
                # Follow a leader if needed; otherwise hold the diverge aim point.
                hold = self._nb_hold
                diverge = self._car_diverge_xy(self._car_exit_i, self._car_dir)
                if hold is not None:
                    self._car_target = hold
                elif self._car_pending_dir is not None:
                    self._car_target = diverge
                else:
                    self._car_target = diverge
            elif self._car_ring_phase == "to_corner":
                # Retarget every tick: a lane change shifts the fillet centre, and
                # a stale cross-lane target leaves a pure-lateral residual that
                # never trips arrival — cars yaw 90° into the curb (right lane
                # near diamonds is the common case).
                corner = self._car_refresh_corner_target()
                tdx, tdy = self._car_dir
                along = (
                    (corner[0] - self._car_pos[0]) * tdx
                    + (corner[1] - self._car_pos[1]) * tdy
                )
                if along <= max(self._car_speed * dt, 0.35):
                    if self._car_lane_changing:
                        self._car_finish_lane_change_snap()
                    self._car_set_highway_lane(self._car_dir, snap=True)
                    corner = self._car_corner_approach(
                        self._car_exit_i, self._car_dir,
                    )
                    self._car_pos[0], self._car_pos[1] = corner
                    self._car_after_cross = corner
                    if self._car_corner_entry_clear():
                        self._car_begin_corner_turn()
                    else:
                        self._car_speed = 0.0
                    self._car_finish_frame()
                    return task.cont
                hold = self._nb_hold
                if hold is not None:
                    self._car_target = self._car_along_highway_target(hold)
                else:
                    self._car_target = self._car_along_highway_target(corner)
        elif self._car_state == "drive":
            self._car_target = self._car_drive_target()

        tx, ty = self._car_target
        dx = tx - self._car_pos[0]
        dy = ty - self._car_pos[1]
        dist = math.hypot(dx, dy)
        if dist <= max(self._car_speed * dt, 0.02):
            self._car_pos[0] = tx
            self._car_pos[1] = ty
            # Leave-point crossing finishes first; only then drive the leg to the
            # corner. Starting the arc here would pivot around the far fillet
            # from mid-interchange and jam the fleet off the asphalt.
            if self._car_state == "crossing":
                self._car_target = self._car_after_cross
                self._car_state = "drive"
                self._car_finish_frame()
                return task.cont
            if self._car_on_highway:
                # to_corner fillet arrival is handled above via along-distance.
                # Reaching a follow-hold here just waits for the leader.
                if self._car_ring_phase == "to_corner":
                    self._car_finish_frame()
                    return task.cont
                # Diverge / deck arrival: commit without an intersection wait.
                self._car_commit_highway(self._car_pending_dir)
                self._car_finish_frame()
                return task.cont
            # Refresh queue rank at the stop before choosing head vs follower.
            self._car_refresh_neighbors(resolve=False)
            self._car_begin_wait()
            self._car_finish_frame()
            return task.cont

        if self._car_state == "drive":
            hold = self._nb_hold
            if self._car_on_highway:
                # Cruise the ring; only slow for a leader, or gently for an exit.
                if hold is not None:
                    limit = math.hypot(
                        hold[0] - self._car_pos[0], hold[1] - self._car_pos[1],
                    )
                    self._car_advance_speed(dt, limit)
                elif self._car_pending_dir is not None and self._car_pending_dir != self._car_dir:
                    # Peeling onto an off-ramp — ease in without a full stop.
                    self._car_advance_speed(dt, max(dist, self._car_decel_dist * 0.85))
                else:
                    self._car_advance_speed(dt)
            else:
                # City: decel for the bumper gap / queue slot ahead.
                limit = dist
                if hold is not None:
                    limit = min(
                        limit,
                        math.hypot(
                            hold[0] - self._car_pos[0], hold[1] - self._car_pos[1],
                        ),
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
        if self._car_on_highway and self._car_signal is not None:
            self._car_update_signals(dt)
        self._car_finish_frame()
        return task.cont
