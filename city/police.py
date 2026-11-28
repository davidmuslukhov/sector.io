"""Chicago PD pursuit AI, health HUD, and game-over loop (2× scale)."""

from __future__ import annotations

import math
import random
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    CardMaker,
    ColorBlendAttrib,
    LineSegs,
    NodePath,
    TextNode,
    TransparencyAttrib,
    Vec4,
)

from city.car import (
    ROAD_SHOULDER,
    _CAR_LENGTH,
    _CAR_WIDTH,
    _UNITS_PER_M,
    _apply_drive_lamps,
)
from city.collision2d import (
    COLLIDER_BUILDING,
    COLLIDER_HOUSE,
    COLLIDER_PILLAR,
    COP_HALF_L,
    COP_HALF_W,
    PLAYER_HALF_L,
    PLAYER_HALF_W,
    CollisionWorld2D,
    OBB2D,
    resolve_static_world_collisions,
)
from city.mesh import _dist2_point_segment, cpd_cruiser_template
from city.road_graph import TrafficLanesGraph, build_traffic_lanes_graph

# ---- Spec constants (world units @ 42.2 u / mile) ----
CPD_LENGTH = COP_HALF_L * 2.0
CPD_WIDTH = COP_HALF_W * 2.0
CPD_HEIGHT = 0.052
CPD_HALF_L = COP_HALF_L
CPD_HALF_W = COP_HALF_W
CPD_BODY_HALF_Z = CPD_HEIGHT * 0.5

SPAWN_MIN = 18.0
SPAWN_MAX = 28.0
DESPAWN_DIST = 40.0
CLOSE_RANGE = 3.5
# Pursuit cap as a fraction of the player's current world speed.
PLAYER_SPEED_FACTOR = 0.9
# Slow crawl floor (world u/s) so idle/spawn approach still works.
SPEED_FLOOR = 0.2
# Match PlayerCar._OFF_ROAD_SPEED — grass / off-pavement crawl.
OFF_ROAD_SPEED = 0.5
FOLLOW_BACK = 1.4
ATTACK_COOLDOWN = 7.0
DAMAGE_PER_HIT = 20
MAX_HEALTH = 100
PURSUIT_INDICATOR_DIST = 15.0
STROBE_INTERVAL = 0.18
SHAKE_DURATION = 0.22
PREDICT_LEAD = 1.2
UNIT_COUNT = 4

# Whisker wall-avoidance (close-range alley / yard intercept).
WHISKER_LEN = 0.85
WHISKER_ANGLE = 28.0
STEER_AVOID = 220.0  # deg/s bias when a side whisker hits
REVERSE_HOLD = 0.8
REVERSE_THROTTLE = -0.6
STUCK_WINDOW = 2.5
STUCK_MIN_DISP = 0.25
STUCK_PLAYER_CLEAR = 12.0
HITBOX_DEBUG_RADIUS = 15.0
_WHISKER_CATEGORIES = {COLLIDER_BUILDING, COLLIDER_HOUSE, COLLIDER_PILLAR}

# Proximity threat tiers (Euclidean world units; never shown as exact numbers).
TIER_CRITICAL = 100.0
TIER_CLOSE = 250.0
TIER_AREA = 500.0
PROXIMITY_HZ = 10.0
PROXIMITY_INTERVAL = 1.0 / PROXIMITY_HZ
CRITICAL_STROBE = 0.15
CLOSE_PULSE = 0.5

_TIER_DISTANT = (
    "distant",
    "CPD: DISTANT (> 500)",
    1,
    (0.35, 0.65, 0.85, 0.85),
)
_TIER_AREA = (
    "area",
    "CPD: IN AREA (251–500)",
    2,
    (0.96, 0.76, 0.12, 1.0),
)
_TIER_CLOSE = (
    "close",
    "CPD: CLOSE (101–250)",
    3,
    (1.0, 0.28, 0.10, 1.0),
)
_TIER_CRITICAL = (
    "critical",
    "CPD: CRITICAL (≤ 100)",
    4,
    (1.0, 0.15, 0.12, 1.0),
)
_BAR_UNLIT = (0.20, 0.22, 0.26, 0.6)


class PoliceCruiser:
    """One CPD interceptor with lightbar strobes and pursuit state."""

    def __init__(
        self,
        app,
        road_top: float,
        *,
        parent: NodePath | None = None,
    ) -> None:
        self.app = app
        self._road_top = float(road_top)
        root_parent = parent or getattr(app, "_fleet_root", None) or app.render
        self.node = cpd_cruiser_template().copyTo(root_parent)
        self.node.setName("cpd_cruiser_node")

        self._lightbar_red = self.node.find("**/lightbar-red")
        self._lightbar_blue = self.node.find("**/lightbar-blue")
        self._pool_red = self.node.find("**/pool-red")
        self._pool_blue = self.node.find("**/pool-blue")
        for pool in (self._pool_red, self._pool_blue):
            if pool is not None and not pool.isEmpty():
                pool.setLightOff(1)
                pool.setDepthWrite(False)
                pool.setAttrib(
                    ColorBlendAttrib.make(
                        ColorBlendAttrib.MAdd,
                        ColorBlendAttrib.OIncomingAlpha,
                        ColorBlendAttrib.OOne,
                    )
                )
        self._headlights = {
            "left": self.node.find("**/headlight-left"),
            "right": self.node.find("**/headlight-right"),
        }
        self._taillights = {
            "left": self.node.find("**/taillight-left"),
            "right": self.node.find("**/taillight-right"),
        }
        self._lamp_key: tuple | None = None

        self.pos = [0.0, 0.0]
        self.heading = 0.0
        self.speed = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.attack_cooldown_timer = 0.0
        self.target_node: int | None = None
        self._strobe_t = random.uniform(0.0, STROBE_INTERVAL)
        self._strobe_red = True
        self._active = False
        self._reverse_t = 0.0
        self._stuck_t = 0.0
        self._stuck_origin = (0.0, 0.0)
        self._place()
        self.node.hide()

    @property
    def active(self) -> bool:
        return self._active

    def activate(self, x: float, y: float, heading: float) -> None:
        self.pos = [float(x), float(y)]
        self.heading = float(heading)
        self.speed = SPEED_FLOOR
        self.vx = self.vy = 0.0
        self.attack_cooldown_timer = 0.0
        self.target_node = None
        self._reverse_t = 0.0
        self._stuck_t = 0.0
        self._stuck_origin = (float(x), float(y))
        self._active = True
        self.node.show()
        self._place()
        self._refresh_lamps()

    def deactivate(self) -> None:
        self._active = False
        self.speed = 0.0
        self.vx = self.vy = 0.0
        self._reverse_t = 0.0
        self._stuck_t = 0.0
        self.node.hide()

    def _place(self) -> None:
        z = self._road_top + CPD_BODY_HALF_Z
        self.node.setHpr(self.heading, 0.0, 0.0)
        self.node.setPos(self.pos[0], self.pos[1], z)

    def obb(self) -> OBB2D:
        return OBB2D(
            self.pos[0],
            self.pos[1],
            CPD_HALF_L,
            CPD_HALF_W,
            self.heading,
            self.vx,
            self.vy,
            tag=self,
        )

    def update_strobes(self, dt: float) -> None:
        if not self._active:
            return
        self._strobe_t += dt
        if self._strobe_t >= STROBE_INTERVAL:
            self._strobe_t = 0.0
            self._strobe_red = not self._strobe_red
        on = 1.35
        off = 0.08
        if not self._lightbar_red.isEmpty():
            s = on if self._strobe_red else off
            self._lightbar_red.setColorScale(s, s, s, 1)
        if not self._lightbar_blue.isEmpty():
            s = on if not self._strobe_red else off
            self._lightbar_blue.setColorScale(s, s, s, 1)
        if not self._pool_red.isEmpty():
            if self._strobe_red:
                self._pool_red.show()
            else:
                self._pool_red.hide()
        if not self._pool_blue.isEmpty():
            if not self._strobe_red:
                self._pool_blue.show()
            else:
                self._pool_blue.hide()

    def _refresh_lamps(self) -> None:
        night = bool(getattr(self.app, "_vehicle_lights_on", False))
        key = (night,)
        if self._lamp_key == key:
            return
        self._lamp_key = key
        _apply_drive_lamps(
            self._headlights,
            self._taillights,
            night=night,
            braking=False,
            reversing=False,
        )


class PolicePursuitManager:
    """Spawns / steers CPD interceptors, applies damage, drives HUD + game over."""

    def __init__(
        self,
        app,
        arterials: list[dict],
        road_top: float,
        *,
        unit_count: int = UNIT_COUNT,
        collision_world: CollisionWorld2D | None = None,
    ) -> None:
        self.app = app
        self.road_top = float(road_top)
        self.graph: TrafficLanesGraph = build_traffic_lanes_graph(arterials)
        self.collision = collision_world or CollisionWorld2D()
        self.app._collision_world = self.collision
        self.app._traffic_lanes_graph = self.graph

        parent = getattr(app, "_fleet_root", None) or app.render
        self.cruisers: list[PoliceCruiser] = [
            PoliceCruiser(app, road_top, parent=parent) for _ in range(unit_count)
        ]

        self.player_health = MAX_HEALTH
        self.max_health = MAX_HEALTH
        self.game_over = False
        self.survival_time = 0.0
        self._shake_t = 0.0
        self._vignette_t = 0.0
        self._sparks: list[tuple[NodePath, float, float, float, float]] = []
        self._smoke: list[tuple[NodePath, float]] = []
        self._effects_root = app.render.attachNewNode("pursuit-fx")
        self._pursuit_near = False
        self.min_cop_distance = float("inf")
        self._proximity_tier_id = "distant"
        self._proximity_accum = 0.0
        self._radar_pulse_t = 0.0
        self._hitbox_debug = False
        self._hitbox_debug_np: NodePath | None = None
        self._setup_hud()
        self._seed_all()

        app.taskMgr.add(self.update_police_ai, "police-pursuit-ai")
        app.accept("r", self._on_restart_key)
        app.accept("R", self._on_restart_key)
        app.accept("f3", self._toggle_hitbox_debug)
        app.accept("F3", self._toggle_hitbox_debug)

    # ------------------------------------------------------------------ HUD
    def _setup_hud(self) -> None:
        a2d = self.app.aspect2d
        self._hud_root = a2d.attachNewNode("pursuit-hud")

        cm = CardMaker("health-bar-bg")
        cm.setFrame(0.0, 0.42, -0.018, 0.018)
        self._health_bg = self.app.a2dTopLeft.attachNewNode(cm.generate())
        self._health_bg.setPos(0.05, 0, -0.16)
        self._health_bg.setColor(0.08, 0.09, 0.1, 0.65)
        self._health_bg.setTransparency(TransparencyAttrib.MAlpha)

        cm2 = CardMaker("health-bar-fill")
        cm2.setFrame(0.0, 0.42, -0.014, 0.014)
        self._health_fill = self.app.a2dTopLeft.attachNewNode(cm2.generate())
        self._health_fill.setPos(0.05, 0, -0.16)
        self._health_fill.setTransparency(TransparencyAttrib.MAlpha)

        self._health_text = OnscreenText(
            text="HEALTH: 100 / 100",
            parent=self.app.a2dTopLeft,
            pos=(0.05, -0.22),
            scale=0.042,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ALeft,
            mayChange=True,
        )

        self._pursuit_text = OnscreenText(
            text="",
            parent=self.app.a2dTopCenter,
            pos=(0.0, -0.2),
            scale=0.05,
            fg=(1.0, 0.2, 0.2, 1),
            shadow=(0.0, 0.0, 0.0, 0.75),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self._pursuit_text.hide()
        self._setup_pursuit_arrow()

        self._setup_proximity_hud()

        self._game_over_root = a2d.attachNewNode("game-over")
        cm3 = CardMaker("go-panel")
        cm3.setFrame(-0.7, 0.7, -0.32, 0.32)
        panel = self._game_over_root.attachNewNode(cm3.generate())
        panel.setColor(0.02, 0.03, 0.05, 0.82)
        panel.setTransparency(TransparencyAttrib.MAlpha)
        panel.setPos(0, 0, 0.05)

        self._go_title = OnscreenText(
            text="BUSTED / WRECKED — GAME OVER",
            parent=self._game_over_root,
            pos=(0.0, 0.14),
            scale=0.07,
            fg=(1.0, 0.85, 0.75, 1),
            shadow=(0.0, 0.0, 0.0, 0.85),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self._go_stats = OnscreenText(
            text="",
            parent=self._game_over_root,
            pos=(0.0, 0.0),
            scale=0.05,
            fg=(0.9, 0.92, 0.95, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self._go_prompt = OnscreenText(
            text="Press R to Restart",
            parent=self._game_over_root,
            pos=(0.0, -0.14),
            scale=0.055,
            fg=(0.7, 0.85, 1.0, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ACenter,
            mayChange=False,
        )
        self._game_over_root.hide()

        # Red edge vignette cards.
        self._vignette = a2d.attachNewNode("damage-vignette")
        for name, frame, pos in (
            ("v-left", (-0.15, 0.0, -1.05, 1.05), (-1.0, 0, 0)),
            ("v-right", (0.0, 0.15, -1.05, 1.05), (1.0, 0, 0)),
            ("v-top", (-1.05, 1.05, 0.0, 0.12), (0, 0, 1.0)),
            ("v-bottom", (-1.05, 1.05, -0.12, 0.0), (0, 0, -1.0)),
        ):
            cmv = CardMaker(name)
            cmv.setFrame(*frame)
            card = self._vignette.attachNewNode(cmv.generate())
            card.setPos(*pos)
            card.setColor(0.85, 0.05, 0.02, 0.0)
            card.setTransparency(TransparencyAttrib.MAlpha)
        self._vignette.hide()

        self._refresh_health_hud(force=True)
        self._apply_proximity_tier(_TIER_DISTANT, force=True)
        # Hidden until Enter car mode (app shows them).
        self.hide_tactical_hud()

    def _setup_proximity_hud(self) -> None:
        """Police proximity scanner — bracketed threat tier, no exact coords."""
        panel_w, panel_h = 0.56, 0.11
        half_w, half_h = panel_w * 0.5, panel_h * 0.5
        border = 0.004
        # Same a2dTopLeft anchor as health; sit just under HEALTH readout.
        # Health bar z=-0.16, label z=-0.22 → panel center below that.
        self._radar_root = self.app.a2dTopLeft.attachNewNode("cpd-proximity-radar")
        self._radar_root.setPos(0.05 + half_w, 0.0, -0.22 - 0.04 - half_h)

        cm_bg = CardMaker("prox-panel")
        cm_bg.setFrame(-half_w, half_w, -half_h, half_h)
        self._radar_panel = self._radar_root.attachNewNode(cm_bg.generate())
        self._radar_panel.setColor(0.06, 0.08, 0.11, 0.78)
        self._radar_panel.setTransparency(TransparencyAttrib.MAlpha)

        # Thin border frame (four edge cards) — color tracks threat tier.
        self._radar_border_parts: list[NodePath] = []
        edges = (
            (-half_w, half_w, half_h, half_h + border),  # top
            (-half_w, half_w, -half_h - border, -half_h),  # bottom
            (-half_w - border, -half_w, -half_h, half_h),  # left
            (half_w, half_w + border, -half_h, half_h),  # right
        )
        for i, frame in enumerate(edges):
            cm_b = CardMaker(f"prox-border-{i}")
            cm_b.setFrame(*frame)
            edge = self._radar_root.attachNewNode(cm_b.generate())
            edge.setColor(0.35, 0.65, 0.85, 0.85)
            edge.setTransparency(TransparencyAttrib.MAlpha)
            self._radar_border_parts.append(edge)

        # 4 stepped signal bars on the left.
        self._radar_bars: list[NodePath] = []
        bar_heights = (0.025, 0.035, 0.045, 0.055)
        bar_w = 0.018
        gap = 0.008
        bar_origin_x = -half_w + 0.03
        for i, bh in enumerate(bar_heights):
            cm_bar = CardMaker(f"prox-bar-{i}")
            cm_bar.setFrame(0.0, bar_w, 0.0, bh)
            bar = self._radar_root.attachNewNode(cm_bar.generate())
            bar.setPos(bar_origin_x + i * (bar_w + gap), 0.0, -bh * 0.5)
            bar.setColor(*_BAR_UNLIT)
            bar.setTransparency(TransparencyAttrib.MAlpha)
            self._radar_bars.append(bar)

        self._radar_label = OnscreenText(
            text=_TIER_DISTANT[1],
            parent=self._radar_root,
            pos=(-0.08, -0.012),
            scale=0.036,
            fg=(0.35, 0.65, 0.85, 0.95),
            shadow=(0.0, 0.0, 0.0, 0.75),
            align=TextNode.ALeft,
            mayChange=True,
        )

        # Non-directional concentric radar sweep on the right edge.
        self._radar_icon = self._radar_root.attachNewNode("radar-icon")
        self._radar_icon.setPos(half_w - 0.045, 0.0, 0.0)
        self._radar_rings: list[NodePath] = []
        radius = 0.032
        for i, r_scale in enumerate((0.45, 0.75, 1.0)):
            ring = self._make_hud_circle(radius * r_scale, segments=28)
            ring.reparentTo(self._radar_icon)
            ring.setColor(0.35, 0.65, 0.85, 0.55 - i * 0.12)
            ring.setTransparency(TransparencyAttrib.MAlpha)
            self._radar_rings.append(ring)
        # Expanding pulse rings (recycled).
        self._radar_pulses: list[NodePath] = []
        for i in range(2):
            pulse = self._make_hud_circle(radius, segments=24)
            pulse.reparentTo(self._radar_icon)
            pulse.setScale(0.2)
            pulse.setColor(0.35, 0.65, 0.85, 0.0)
            pulse.setTransparency(TransparencyAttrib.MAlpha)
            self._radar_pulses.append(pulse)
        self._radar_pulse_phases = [0.0, 0.5]

    @staticmethod
    def _make_hud_circle(radius: float, *, segments: int = 24) -> NodePath:
        segs = LineSegs()
        segs.setThickness(1.4)
        for i in range(segments + 1):
            ang = (2.0 * math.pi) * (i / segments)
            x = radius * math.cos(ang)
            z = radius * math.sin(ang)
            if i == 0:
                segs.moveTo(x, 0.0, z)
            else:
                segs.drawTo(x, 0.0, z)
        return NodePath(segs.create())

    def _setup_pursuit_arrow(self) -> None:
        """Screen-space arrow: tip = nearest cop relative to player heading."""
        self._pursuit_arrow_root = self.app.a2dTopCenter.attachNewNode("pursuit-arrow")
        self._pursuit_arrow_root.setPos(0.0, 0.0, -0.32)
        # Shaft + chevron tip in local +Z (screen up = player forward).
        segs = LineSegs()
        segs.setThickness(3.0)
        segs.moveTo(0.0, 0.0, -0.04)
        segs.drawTo(0.0, 0.0, 0.05)
        segs.moveTo(-0.028, 0.0, 0.012)
        segs.drawTo(0.0, 0.0, 0.05)
        segs.drawTo(0.028, 0.0, 0.012)
        self._pursuit_arrow = self._pursuit_arrow_root.attachNewNode(segs.create())
        self._pursuit_arrow.setColor(1.0, 0.2, 0.15, 1)
        self._pursuit_arrow.setTransparency(TransparencyAttrib.MAlpha)
        # Soft disc behind the arrow so it reads on bright sky.
        cm = CardMaker("pursuit-arrow-bg")
        cm.setFrame(-0.055, 0.055, -0.055, 0.055)
        bg = self._pursuit_arrow_root.attachNewNode(cm.generate())
        bg.setColor(0.04, 0.05, 0.07, 0.55)
        bg.setTransparency(TransparencyAttrib.MAlpha)
        bg.setBin("fixed", 40)
        self._pursuit_arrow.setBin("fixed", 41)
        self._pursuit_arrow_root.hide()

    def show_tactical_hud(self) -> None:
        self._health_bg.show()
        self._health_fill.show()
        self._health_text.show()
        if not self.game_over:
            self._radar_root.show()

    def hide_tactical_hud(self) -> None:
        self._health_bg.hide()
        self._health_fill.hide()
        self._health_text.hide()
        self._radar_root.hide()
        self._pursuit_text.hide()
        self._pursuit_arrow_root.hide()

    def _refresh_health_hud(self, *, force: bool = False) -> None:
        hp = self.player_health
        frac = max(0.0, min(1.0, hp / float(self.max_health)))
        self._health_fill.setScale(frac, 1, 1)
        if hp > 60:
            color = (0.2, 0.78, 0.28, 0.95)
        elif hp > 40:
            color = (0.92, 0.7, 0.12, 0.95)
        else:
            pulse = 0.55 + 0.45 * abs(math.sin(self.app.clock.getFrameTime() * 8.0))
            color = (0.95, 0.12, 0.1, pulse)
        self._health_fill.setColor(*color)
        text = f"HEALTH: {int(hp)} / {self.max_health}"
        if force or text != getattr(self, "_health_label", ""):
            self._health_label = text
            self._health_text.setText(text)

    def _nearest_cop(self, player) -> tuple[PoliceCruiser | None, float]:
        px, py = player._car_pos[0], player._car_pos[1]
        best: PoliceCruiser | None = None
        best_d = float("inf")
        for cop in self.cruisers:
            if not cop.active:
                continue
            d = math.hypot(cop.pos[0] - px, cop.pos[1] - py)
            if d < best_d:
                best_d = d
                best = cop
        return best, best_d

    def _min_cop_distance(self, player) -> float:
        _cop, dist = self._nearest_cop(player)
        return dist

    @staticmethod
    def _tier_for_distance(min_dist: float) -> tuple:
        if min_dist <= TIER_CRITICAL:
            return _TIER_CRITICAL
        if min_dist <= TIER_CLOSE:
            return _TIER_CLOSE
        if min_dist <= TIER_AREA:
            return _TIER_AREA
        return _TIER_DISTANT

    def _apply_proximity_tier(self, tier: tuple, *, force: bool = False) -> None:
        tier_id, label, bars_lit, color = tier
        if not force and tier_id == self._proximity_tier_id:
            return
        self._proximity_tier_id = tier_id
        self._radar_label.setText(label)
        self._radar_label.setFg(Vec4(*color))
        for i, bar in enumerate(self._radar_bars):
            if i < bars_lit:
                bar.setColor(*color)
            else:
                bar.setColor(*_BAR_UNLIT)
        for edge in self._radar_border_parts:
            edge.setColor(*color)
        for ring in self._radar_rings:
            ring.setColor(color[0], color[1], color[2], 0.55)

    def _update_proximity_hud(self, dt: float, player, *, force: bool = False) -> None:
        """Throttled tier refresh (10 Hz) + every-frame pulse / strobe polish."""
        if self.game_over:
            return

        self._proximity_accum += dt
        if force or self._proximity_accum >= PROXIMITY_INTERVAL:
            self._proximity_accum = 0.0
            self.min_cop_distance = self._min_cop_distance(player)
            tier = self._tier_for_distance(self.min_cop_distance)
            self._apply_proximity_tier(tier, force=force)

        tier_id = self._proximity_tier_id
        t = self.app.clock.getFrameTime()
        color = _TIER_DISTANT[3]
        if tier_id == "critical":
            color = _TIER_CRITICAL[3]
            # Fast red/blue strobe on label, bars, and border.
            red_lead = (int(t / CRITICAL_STROBE) % 2) == 0
            strobe = (
                (1.0, 0.12, 0.1, 1.0) if red_lead else (0.2, 0.35, 1.0, 1.0)
            )
            pulse = 0.7 + 0.3 * abs(math.sin(t * math.pi / CRITICAL_STROBE))
            border_c = (strobe[0], strobe[1], strobe[2], pulse)
            self._radar_label.setFg(Vec4(*strobe))
            for i, bar in enumerate(self._radar_bars):
                if i < 4:
                    bar.setColor(*strobe)
            for edge in self._radar_border_parts:
                edge.setColor(*border_c)
            sweep_rate = 2.8
        elif tier_id == "close":
            color = _TIER_CLOSE[3]
            pulse = 0.72 + 0.28 * abs(math.sin(t * math.pi / CLOSE_PULSE))
            c = (color[0], color[1], color[2], pulse)
            self._radar_label.setFg(Vec4(*c))
            for i, bar in enumerate(self._radar_bars):
                if i < 3:
                    bar.setColor(*c)
            for edge in self._radar_border_parts:
                edge.setColor(*c)
            sweep_rate = 1.6
        elif tier_id == "area":
            color = _TIER_AREA[3]
            sweep_rate = 0.9
        else:
            color = _TIER_DISTANT[3]
            sweep_rate = 0.45

        # Concentric non-directional pulse rings — faster when closer.
        for i, pulse_np in enumerate(self._radar_pulses):
            phase = (self._radar_pulse_phases[i] + dt * sweep_rate) % 1.0
            self._radar_pulse_phases[i] = phase
            scale = 0.25 + phase * 1.15
            alpha = max(0.0, 0.65 * (1.0 - phase))
            pulse_np.setScale(scale)
            pulse_np.setColor(color[0], color[1], color[2], alpha)

    def _set_pursuit_indicator(self, active: bool, player) -> None:
        if not active or self.game_over:
            if self._pursuit_near:
                self._pursuit_text.hide()
                self._pursuit_arrow_root.hide()
            self._pursuit_near = False
            return
        self._pursuit_near = True
        t = self.app.clock.getFrameTime()
        red_lead = (int(t / STROBE_INTERVAL) % 2) == 0
        if red_lead:
            fg = Vec4(1.0, 0.18, 0.15, 1)
            arrow_rgb = (1.0, 0.18, 0.15, 1)
        else:
            fg = Vec4(0.25, 0.45, 1.0, 1)
            arrow_rgb = (0.25, 0.45, 1.0, 1)
        self._pursuit_text.setFg(fg)
        self._pursuit_text.setText("CPD PURSUIT ACTIVE")
        self._pursuit_text.show()
        self._pursuit_arrow.setColor(*arrow_rgb)
        self._update_pursuit_arrow(player)
        self._pursuit_arrow_root.show()

    def _update_pursuit_arrow(self, player) -> None:
        """Rotate arrow so tip aims at nearest cop (screen-up = car forward)."""
        cop, dist = self._nearest_cop(player)
        if cop is None or dist < 1e-6:
            return
        dx = cop.pos[0] - player._car_pos[0]
        dy = cop.pos[1] - player._car_pos[1]
        rad = math.radians(player._car_heading)
        fx, fy = math.cos(rad), math.sin(rad)
        # Forward / left in player frame → screen up / left.
        fwd = dx * fx + dy * fy
        left = -dx * fy + dy * fx
        # aspect2d +R is clockwise; negate so left-of-car rotates arrow CCW.
        self._pursuit_arrow_root.setR(-math.degrees(math.atan2(left, fwd)))

    # ----------------------------------------------------------- Spawning
    def _seed_all(self) -> None:
        player = getattr(self.app, "_player_car", None)
        px = py = 0.0
        hx, hy = 0.0, -1.0
        if player is not None:
            px, py = player._car_pos[0], player._car_pos[1]
            rad = math.radians(player._car_heading)
            hx, hy = math.cos(rad), math.sin(rad)
        used: set[int] = set()
        for cruiser in self.cruisers:
            nid = self._pick_spawn_node(px, py, hx, hy, used)
            if nid is None:
                cruiser.deactivate()
                continue
            used.add(nid)
            node = self.graph.nodes[nid]
            heading = math.degrees(math.atan2(py - node.y, px - node.x))
            cruiser.activate(node.x, node.y, heading)
            cruiser.target_node = self._pick_next_node(cruiser, px, py, 0.0, 0.0)

    def _pick_spawn_node(
        self,
        px: float,
        py: float,
        hx: float,
        hy: float,
        used: set[int],
    ) -> int | None:
        candidates = self.graph.nodes_in_ring(px, py, SPAWN_MIN, SPAWN_MAX)
        if not candidates:
            # Fallback: nearest nodes outside SPAWN_MIN.
            scored = []
            for n in self.graph.nodes:
                d = math.hypot(n.x - px, n.y - py)
                if d < SPAWN_MIN:
                    continue
                scored.append((abs(d - 22.0), n.id))
            scored.sort()
            candidates = [i for _, i in scored[:40]]
        # Prefer flanks / ahead of travel.
        ranked: list[tuple[float, int]] = []
        for nid in candidates:
            if nid in used:
                continue
            n = self.graph.nodes[nid]
            dx, dy = n.x - px, n.y - py
            d = math.hypot(dx, dy) or 1.0
            ahead = (dx * hx + dy * hy) / d
            # Score: prefer forward hemisphere, slight random.
            ranked.append((-ahead + random.uniform(-0.15, 0.15), nid))
        if not ranked:
            return None
        ranked.sort()
        return ranked[0][1]

    def _recycle(self, cruiser: PoliceCruiser) -> None:
        player = getattr(self.app, "_player_car", None)
        if player is None:
            cruiser.deactivate()
            return
        px, py = player._car_pos[0], player._car_pos[1]
        rad = math.radians(player._car_heading)
        hx, hy = math.cos(rad), math.sin(rad)
        used = {
            c.target_node
            for c in self.cruisers
            if c is not cruiser and c.active and c.target_node is not None
        }
        # Also avoid current cruiser positions.
        nid = self._pick_spawn_node(px, py, hx, hy, used)
        if nid is None:
            cruiser.deactivate()
            return
        node = self.graph.nodes[nid]
        heading = math.degrees(math.atan2(py - node.y, px - node.x))
        cruiser.activate(node.x, node.y, heading)
        cruiser.target_node = self._pick_next_node(cruiser, px, py, 0.0, 0.0)

    # ----------------------------------------------------------- AI
    def _player_vel_world(self, player) -> tuple[float, float]:
        rad = math.radians(player._car_heading)
        # Player speed is m/s → world units/sec.
        speed_u = float(player._car_speed) * _UNITS_PER_M
        return math.cos(rad) * speed_u, math.sin(rad) * speed_u

    def _pick_next_node(
        self,
        cruiser: PoliceCruiser,
        px: float,
        py: float,
        pvx: float,
        pvy: float,
    ) -> int | None:
        pred_x = px + pvx * PREDICT_LEAD
        pred_y = py + pvy * PREDICT_LEAD
        here = self.graph.nearest_node(cruiser.pos[0], cruiser.pos[1], max_dist=12.0)
        if here is None:
            return self.graph.nearest_node(pred_x, pred_y, max_dist=40.0)
        best: tuple[float, int] | None = None
        for nid, _length, _ex in self.graph.neighbors(here):
            n = self.graph.nodes[nid]
            # Heading from cruiser toward neighbor vs toward predicted player.
            to_n = (n.x - cruiser.pos[0], n.y - cruiser.pos[1])
            to_p = (pred_x - cruiser.pos[0], pred_y - cruiser.pos[1])
            ln = math.hypot(*to_n) or 1.0
            lp = math.hypot(*to_p) or 1.0
            align = (to_n[0] * to_p[0] + to_n[1] * to_p[1]) / (ln * lp)
            # Prefer alignment; slight bias to closer nodes.
            score = -align + 0.02 * ln
            if best is None or score < best[0]:
                best = (score, nid)
        if best is None:
            return self.graph.nearest_node(pred_x, pred_y, max_dist=40.0)
        return best[1]

    def _cop_max_speed(self, player_speed_u: float) -> float:
        """Max pursuit speed: 0.9× player world speed (with a small floor)."""
        return max(SPEED_FLOOR, PLAYER_SPEED_FACTOR * abs(player_speed_u))

    def _cruiser_on_road(self, cruiser: PoliceCruiser) -> bool:
        """True when the cruiser is on/near any drivable pavement (incl. minors)."""
        px, py = cruiser.pos[0], cruiser.pos[1]
        nearby = getattr(self.app, "nearby_drive_roads", None)
        if nearby is not None:
            for ax, ay, bx, by, half_w in nearby(px, py, 2.0):
                d2, _qx, _qy = _dist2_point_segment(px, py, ax, ay, bx, by)
                limit = half_w + ROAD_SHOULDER
                if d2 <= limit * limit:
                    return True
            return False
        nearby_named = getattr(self.app, "nearby_roads", None)
        if nearby_named is None:
            roads = getattr(self.app, "_named_roads", None) or ()
            if not roads:
                return True
        else:
            roads = nearby_named(px, py, 2.0)
        for entry in roads:
            if len(entry) == 6:
                _name, ax, ay, bx, by, half_w = entry
            else:
                ax, ay, bx, by, half_w = entry
            d2, _qx, _qy = _dist2_point_segment(px, py, ax, ay, bx, by)
            limit = half_w + ROAD_SHOULDER
            if d2 <= limit * limit:
                return True
        return False

    def _whisker_bias(self, cruiser: PoliceCruiser) -> float:
        """3-whisker building probe → steering bias (deg/s). May start reverse."""
        rad = math.radians(cruiser.heading)
        fx, fy = math.cos(rad), math.sin(rad)
        # Front bumper origin.
        ox = cruiser.pos[0] + fx * CPD_HALF_L
        oy = cruiser.pos[1] + fy * CPD_HALF_L

        def _probe(angle_deg: float) -> bool:
            a = math.radians(cruiser.heading + angle_deg)
            hx, hy = math.cos(a), math.sin(a)
            hit = self.collision.segment_hits_static(
                ox,
                oy,
                ox + hx * WHISKER_LEN,
                oy + hy * WHISKER_LEN,
                categories=_WHISKER_CATEGORIES,
                samples=3,
            )
            return hit is not None

        left_hit = _probe(+WHISKER_ANGLE)
        right_hit = _probe(-WHISKER_ANGLE)
        center_hit = _probe(0.0)

        if center_hit and left_hit and right_hit:
            cruiser._reverse_t = REVERSE_HOLD
            return 0.0
        if left_hit and not right_hit:
            return -STEER_AVOID  # strong rightward
        if right_hit and not left_hit:
            return +STEER_AVOID  # strong leftward
        if left_hit and right_hit:
            # Both sides blocked but centre clear — pick a side by heading noise.
            return STEER_AVOID if (cruiser.heading % 2.0) < 1.0 else -STEER_AVOID
        return 0.0

    def _steer_toward(
        self,
        cruiser: PoliceCruiser,
        tx: float,
        ty: float,
        dt: float,
        max_speed: float,
        *,
        avoid_walls: bool = True,
    ) -> None:
        bias_rate = 0.0
        if cruiser._reverse_t <= 0.0 and avoid_walls:
            bias_rate = self._whisker_bias(cruiser)

        # Reverse-and-turn failsafe when whiskers are boxed in head-on.
        if cruiser._reverse_t > 0.0:
            cruiser._reverse_t = max(0.0, cruiser._reverse_t - dt)
            turn_rate = 160.0
            cruiser.heading += turn_rate * dt
            cruiser.speed = REVERSE_THROTTLE * max(max_speed, SPEED_FLOOR)
            rad = math.radians(cruiser.heading)
            cruiser.vx = math.cos(rad) * cruiser.speed
            cruiser.vy = math.sin(rad) * cruiser.speed
            cruiser.pos[0] += cruiser.vx * dt
            cruiser.pos[1] += cruiser.vy * dt
            return

        dx = tx - cruiser.pos[0]
        dy = ty - cruiser.pos[1]
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            return
        desired_h = math.degrees(math.atan2(dy, dx))
        # Turn toward target (unwrap).
        delta = (desired_h - cruiser.heading + 180.0) % 360.0 - 180.0
        turn_rate = 160.0  # deg/s
        steer = max(-turn_rate * dt, min(turn_rate * dt, delta))
        steer += bias_rate * dt
        cruiser.heading += steer
        # Grass / off-pavement: same half-speed penalty as the player car.
        if not self._cruiser_on_road(cruiser):
            max_speed *= OFF_ROAD_SPEED
        # Accelerate / match speed.
        if cruiser.speed < max_speed:
            cruiser.speed = min(max_speed, cruiser.speed + 6.0 * dt)
        else:
            cruiser.speed = max(max_speed, cruiser.speed - 8.0 * dt)
        rad = math.radians(cruiser.heading)
        step = cruiser.speed * dt
        cruiser.vx = math.cos(rad) * cruiser.speed
        cruiser.vy = math.sin(rad) * cruiser.speed
        cruiser.pos[0] += math.cos(rad) * step
        cruiser.pos[1] += math.sin(rad) * step

    def _separate_static(self, cruiser: PoliceCruiser) -> None:
        box = cruiser.obb()
        resolve_static_world_collisions(box)
        # Also use barrier capsules (L pillars / fences when present).
        nearby = getattr(self.app, "nearby_barriers", None)
        if nearby is not None:
            radius = max(CPD_HALF_L, CPD_HALF_W) + 0.08
            for ax, ay, bx, by, half_w in nearby(box.x, box.y, radius + 0.5):
                d2, qx, qy = _dist2_point_segment(box.x, box.y, ax, ay, bx, by)
                min_d = half_w + radius
                if d2 >= min_d * min_d:
                    continue
                dist = math.sqrt(max(d2, 1e-12))
                nx = (box.x - qx) / dist
                ny = (box.y - qy) / dist
                pen = min_d - dist
                box.x += nx * pen
                box.y += ny * pen
        cruiser.pos[0] = box.x
        cruiser.pos[1] = box.y
        cruiser.vx, cruiser.vy = box.vx, box.vy
        rad = math.radians(cruiser.heading)
        cruiser.speed = box.vx * math.cos(rad) + box.vy * math.sin(rad)

    def _update_stuck(self, cruiser: PoliceCruiser, dt: float, px: float, py: float) -> None:
        """Snap a pinned cruiser back onto an open road node away from the player."""
        ox, oy = cruiser._stuck_origin
        disp = math.hypot(cruiser.pos[0] - ox, cruiser.pos[1] - oy)
        if disp >= STUCK_MIN_DISP:
            cruiser._stuck_origin = (cruiser.pos[0], cruiser.pos[1])
            cruiser._stuck_t = 0.0
            return
        cruiser._stuck_t += dt
        if cruiser._stuck_t < STUCK_WINDOW:
            return
        cruiser._stuck_t = 0.0
        # Prefer a centreline node clear of the player.
        candidates = self.graph.nodes_in_ring(
            px, py, STUCK_PLAYER_CLEAR, STUCK_PLAYER_CLEAR + 20.0
        )
        if not candidates:
            nid = self.graph.nearest_node(cruiser.pos[0], cruiser.pos[1], max_dist=40.0)
            if nid is None:
                return
            node = self.graph.nodes[nid]
            if math.hypot(node.x - px, node.y - py) < STUCK_PLAYER_CLEAR:
                return
        else:
            nid = random.choice(candidates)
            node = self.graph.nodes[nid]
        cruiser.pos[0] = node.x
        cruiser.pos[1] = node.y
        cruiser.heading = math.degrees(math.atan2(py - node.y, px - node.x))
        cruiser.speed = SPEED_FLOOR
        cruiser.vx = cruiser.vy = 0.0
        cruiser.target_node = nid
        cruiser._reverse_t = 0.0
        cruiser._stuck_origin = (node.x, node.y)
        cruiser._place()

    def _toggle_hitbox_debug(self) -> None:
        self._hitbox_debug = not self._hitbox_debug
        if not self._hitbox_debug and self._hitbox_debug_np is not None:
            self._hitbox_debug_np.removeNode()
            self._hitbox_debug_np = None

    def _draw_obb_wire(
        self, segs: LineSegs, box: OBB2D, rgba: tuple[float, float, float, float]
    ) -> None:
        segs.setColor(*rgba)
        corners = box.corners()
        for i in range(4):
            x0, y0 = corners[i]
            x1, y1 = corners[(i + 1) % 4]
            segs.moveTo(x0, y0, self.road_top + 0.06)
            segs.drawTo(x1, y1, self.road_top + 0.06)

    def _refresh_hitbox_debug(self, player) -> None:
        if self._hitbox_debug_np is not None:
            self._hitbox_debug_np.removeNode()
            self._hitbox_debug_np = None
        if not self._hitbox_debug or player is None:
            return
        px, py = player._car_pos[0], player._car_pos[1]
        segs = LineSegs("hitbox-debug")
        segs.setThickness(2.0)
        # Green static houses / buildings / pillars nearby.
        for box in self.collision.nearby_static(px, py, HITBOX_DEBUG_RADIUS):
            self._draw_obb_wire(segs, box, (0.25, 0.95, 0.35, 1.0))
        # Cyan player OBB.
        pvx, pvy = self._player_vel_world(player)
        player_obb = OBB2D(
            px, py, PLAYER_HALF_L, PLAYER_HALF_W, player._car_heading, pvx, pvy
        )
        self._draw_obb_wire(segs, player_obb, (0.2, 0.95, 1.0, 1.0))
        # Red pursuing cruisers.
        for cruiser in self.cruisers:
            if not cruiser.active:
                continue
            if math.hypot(cruiser.pos[0] - px, cruiser.pos[1] - py) > HITBOX_DEBUG_RADIUS:
                continue
            self._draw_obb_wire(segs, cruiser.obb(), (1.0, 0.2, 0.15, 1.0))
        np = self.app.render.attachNewNode(segs.create())
        np.setLightOff(1)
        np.setBin("fixed", 60)
        self._hitbox_debug_np = np

    def update_police_ai(self, task):
        dt = min(self.app.clock.getDt(), 0.05)
        if dt <= 0.0:
            return task.cont

        player = getattr(self.app, "_player_car", None)
        if player is None:
            return task.cont

        # Pursuit loop is a drive-mode game feature.
        if not getattr(self.app, "_car_mode", False) and not self.game_over:
            if self._hitbox_debug:
                self._refresh_hitbox_debug(player)
            return task.cont

        if not self.game_over:
            self.survival_time += dt

        self._update_effects(dt)
        self._refresh_health_hud()
        if not self.game_over:
            self._update_proximity_hud(dt, player)

        if self.game_over:
            self._update_smoke(dt, player)
            for c in self.cruisers:
                if c.active:
                    c.update_strobes(dt)
                    c._place()
            if self._hitbox_debug:
                self._refresh_hitbox_debug(player)
            return task.cont

        px, py = player._car_pos[0], player._car_pos[1]
        pvx, pvy = self._player_vel_world(player)
        pursuit_near = False

        # ---- 1) Player OBB (static already solved in PlayerCar.update) ----
        player_obb = OBB2D(
            px,
            py,
            PLAYER_HALF_L,
            PLAYER_HALF_W,
            player._car_heading,
            pvx,
            pvy,
            tag=player,
        )

        for cruiser in self.cruisers:
            if not cruiser.active:
                continue
            cruiser.attack_cooldown_timer = max(0.0, cruiser.attack_cooldown_timer - dt)
            cruiser.update_strobes(dt)
            cruiser._refresh_lamps()

            dx = cruiser.pos[0] - px
            dy = cruiser.pos[1] - py
            dist = math.hypot(dx, dy)
            if dist > DESPAWN_DIST:
                self._recycle(cruiser)
                continue
            if dist <= PURSUIT_INDICATOR_DIST:
                pursuit_near = True

            player_speed_u = math.hypot(pvx, pvy)
            cop_cap = self._cop_max_speed(player_speed_u)

            backing_off = cruiser.attack_cooldown_timer > 0.0
            # Whiskers matter most off-lane (close intercept) and while backing off.
            use_whiskers = (not backing_off and dist <= CLOSE_RANGE) or backing_off
            if backing_off:
                # Hold ~1.4 u behind the player, no ram (still under 0.9× cap).
                rad = math.radians(player._car_heading)
                fx, fy = math.cos(rad), math.sin(rad)
                tx = px - fx * FOLLOW_BACK
                ty = py - fy * FOLLOW_BACK
                self._steer_toward(
                    cruiser, tx, ty, dt, cop_cap, avoid_walls=use_whiskers
                )
            elif dist > CLOSE_RANGE:
                # Long-range road navigation.
                if cruiser.target_node is None:
                    cruiser.target_node = self._pick_next_node(
                        cruiser, px, py, pvx, pvy
                    )
                else:
                    tn = self.graph.nodes[cruiser.target_node]
                    if math.hypot(tn.x - cruiser.pos[0], tn.y - cruiser.pos[1]) < 0.55:
                        here = cruiser.target_node
                        cruiser.target_node = self._pick_next_node(
                            cruiser, px, py, pvx, pvy
                        )
                        # Avoid instantly re-picking the same node.
                        if cruiser.target_node == here:
                            nbrs = self.graph.neighbors(here)
                            if nbrs:
                                cruiser.target_node = random.choice(nbrs)[0]
                if cruiser.target_node is not None:
                    tn = self.graph.nodes[cruiser.target_node]
                    # Long-range stays on graph edges — skip whisker probes.
                    self._steer_toward(
                        cruiser, tn.x, tn.y, dt, cop_cap, avoid_walls=False
                    )
            else:
                # Close-range direct intercept / pit through alleys & yards.
                self._steer_toward(
                    cruiser, px, py, dt, cop_cap, avoid_walls=True
                )

            self._separate_static(cruiser)
            self._update_stuck(cruiser, dt, px, py)

        # Refresh player OBB after any earlier static push (cops may have moved).
        px, py = player._car_pos[0], player._car_pos[1]
        pvx, pvy = self._player_vel_world(player)
        player_obb = OBB2D(
            px,
            py,
            PLAYER_HALF_L,
            PLAYER_HALF_W,
            player._car_heading,
            pvx,
            pvy,
            tag=player,
        )

        # ---- 2) Dynamic player ↔ cop OBB collisions ----
        for cruiser in self.cruisers:
            if not cruiser.active:
                continue
            cop_obb = cruiser.obb()
            hit = self.collision.resolve_pair(
                player_obb, cop_obb, mass_a=1.0, mass_b=1.15
            )
            if hit is not None:
                player._car_pos[0] = player_obb.x
                player._car_pos[1] = player_obb.y
                cruiser.pos[0] = cop_obb.x
                cruiser.pos[1] = cop_obb.y
                rad = math.radians(player._car_heading)
                fx, fy = math.cos(rad), math.sin(rad)
                player._car_speed = (
                    player_obb.vx * fx + player_obb.vy * fy
                ) / max(_UNITS_PER_M, 1e-9)
                cruiser.vx, cruiser.vy = cop_obb.vx, cop_obb.vy
                cruiser.speed = math.hypot(cruiser.vx, cruiser.vy)

                if cruiser.attack_cooldown_timer <= 0.0:
                    self._apply_damage(cruiser, hit)

        # ---- 3) Final static pass (no shoving into brick after a ram) ----
        resolve_static_world_collisions(player_obb)
        player._car_pos[0] = player_obb.x
        player._car_pos[1] = player_obb.y
        rad = math.radians(player._car_heading)
        fx, fy = math.cos(rad), math.sin(rad)
        player._car_speed = (
            player_obb.vx * fx + player_obb.vy * fy
        ) / max(_UNITS_PER_M, 1e-9)

        for cruiser in self.cruisers:
            if not cruiser.active:
                continue
            self._separate_static(cruiser)
            cruiser._place()

        player._place()
        self._set_pursuit_indicator(pursuit_near, player)
        if self._hitbox_debug:
            self._refresh_hitbox_debug(player)
        return task.cont

    # ----------------------------------------------------------- Combat FX
    def _apply_damage(self, cruiser: PoliceCruiser, hit: tuple[float, float, float]) -> None:
        self.player_health = max(0, self.player_health - DAMAGE_PER_HIT)
        cruiser.attack_cooldown_timer = ATTACK_COOLDOWN
        self._shake_t = SHAKE_DURATION
        self._vignette_t = 0.35
        self._vignette.show()
        # Sparks at contact midpoint.
        nx, ny, _pen = hit
        cx = cruiser.pos[0] - nx * CPD_HALF_L * 0.4
        cy = cruiser.pos[1] - ny * CPD_HALF_L * 0.4
        self._spawn_sparks(cx, cy)
        self._refresh_health_hud(force=True)
        if self.player_health <= 0:
            self._trigger_game_over()

    def _spawn_sparks(self, x: float, y: float) -> None:
        z = self.road_top + 0.04
        cm = CardMaker("spark")
        cm.setFrame(-0.008, 0.008, -0.008, 0.008)
        for _ in range(10):
            spark = self._effects_root.attachNewNode(cm.generate())
            spark.setPos(x, y, z)
            spark.setColor(1.0, 0.85, 0.35, 1)
            spark.setBillboardPointEye()
            spark.setLightOff(1)
            ang = random.uniform(0.0, math.tau)
            spd = random.uniform(0.4, 1.4)
            self._sparks.append(
                (spark, math.cos(ang) * spd, math.sin(ang) * spd, random.uniform(0.8, 1.6), z)
            )

    def _update_effects(self, dt: float) -> None:
        self._shake_t = max(0.0, self._shake_t - dt)
        if self._vignette_t > 0.0:
            self._vignette_t = max(0.0, self._vignette_t - dt)
            alpha = min(0.55, self._vignette_t * 1.6)
            for child in self._vignette.getChildren():
                child.setColor(0.85, 0.05, 0.02, alpha)
            if self._vignette_t <= 0.0:
                self._vignette.hide()

        alive: list[tuple[NodePath, float, float, float, float]] = []
        for spark, vx, vy, life, z in self._sparks:
            life -= dt
            if life <= 0.0:
                spark.removeNode()
                continue
            spark.setPos(spark.getX() + vx * dt, spark.getY() + vy * dt, z + dt * 0.4)
            spark.setScale(max(0.2, life))
            alive.append((spark, vx * 0.92, vy * 0.92, life, z + dt * 0.4))
        self._sparks = alive

    def _update_smoke(self, dt: float, player) -> None:
        # Keep a few smoke puffs rising from the hood.
        if len(self._smoke) < 8 and random.random() < 0.35:
            cm = CardMaker("smoke")
            cm.setFrame(-0.03, 0.03, -0.03, 0.03)
            puff = self._effects_root.attachNewNode(cm.generate())
            rad = math.radians(player._car_heading)
            hx, hy = math.cos(rad), math.sin(rad)
            px = player._car_pos[0] + hx * _CAR_LENGTH * 0.35
            py = player._car_pos[1] + hy * _CAR_LENGTH * 0.35
            puff.setPos(px, py, player._car_z + 0.04)
            puff.setColor(0.35, 0.35, 0.36, 0.55)
            puff.setTransparency(TransparencyAttrib.MAlpha)
            puff.setBillboardPointEye()
            puff.setLightOff(1)
            self._smoke.append((puff, random.uniform(1.2, 2.2)))
        alive: list[tuple[NodePath, float]] = []
        for puff, life in self._smoke:
            life -= dt
            if life <= 0.0:
                puff.removeNode()
                continue
            puff.setZ(puff.getZ() + dt * 0.18)
            puff.setScale(1.0 + (2.2 - life) * 0.6)
            puff.setAlphaScale(max(0.0, life * 0.35))
            alive.append((puff, life))
        self._smoke = alive

    # ----------------------------------------------------------- Game over
    def _trigger_game_over(self) -> None:
        if self.game_over:
            return
        self.game_over = True
        player = getattr(self.app, "_player_car", None)
        if player is not None:
            player._car_speed = 0.0
            player._place()
        self.app._pursuit_game_over = True
        mins = int(self.survival_time // 60)
        secs = int(self.survival_time % 60)
        self._go_stats.setText(f"Survived {mins:02d}:{secs:02d}")
        self._game_over_root.show()
        self._pursuit_text.hide()
        self._pursuit_arrow_root.hide()
        # Dim / hide scanner during GAME OVER.
        self._radar_root.hide()

    def _on_restart_key(self) -> None:
        if not self.game_over:
            return
        self.restart()

    def restart(self) -> None:
        self.game_over = False
        self.app._pursuit_game_over = False
        self.player_health = MAX_HEALTH
        self.survival_time = 0.0
        self._shake_t = 0.0
        self._vignette_t = 0.0
        self._vignette.hide()
        self._game_over_root.hide()
        for spark, *_rest in self._sparks:
            spark.removeNode()
        self._sparks.clear()
        for puff, _life in self._smoke:
            puff.removeNode()
        self._smoke.clear()

        player = getattr(self.app, "_player_car", None)
        if player is not None:
            # State & Madison origin — match spawn (right lane, southbound).
            start_x = getattr(self, "_player_start_x", -0.0)
            start_y = getattr(self, "_player_start_y", -1.5)
            start_h = getattr(self, "_player_start_heading", -90.0)
            # Prefer values recorded at build time.
            sx = getattr(self.app, "_player_spawn_xyh", None)
            if sx is not None:
                start_x, start_y, start_h = sx
            player._car_pos[0] = float(start_x)
            player._car_pos[1] = float(start_y)
            player._car_heading = float(start_h)
            player._car_speed = 0.0
            player._brake_hold_t = 0.0
            player._place()

        self._seed_all()
        self._refresh_health_hud(force=True)
        # Spec: restart snaps scanner to DISTANT; 10 Hz tick re-evaluates next.
        self.min_cop_distance = float("inf")
        self._proximity_accum = 0.0
        self._apply_proximity_tier(_TIER_DISTANT, force=True)
        if getattr(self.app, "_car_mode", False):
            self._radar_root.show()
            self.app._update_chase_camera()
