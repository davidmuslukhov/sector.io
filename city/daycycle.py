"""Real-time day/night cycle: sunrise → day → sunset → night."""

from __future__ import annotations

import math
from dataclasses import dataclass

# Wall-clock halves: five minutes of day, five of night.
DAY_SECONDS = 5.0 * 60.0
NIGHT_SECONDS = 5.0 * 60.0
CYCLE_SECONDS = DAY_SECONDS + NIGHT_SECONDS
# Soft ramps at the edges of each half.
SUNRISE_SECONDS = 60.0
SUNSET_SECONDS = 60.0


def _clamp(t: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if t < lo else hi if t > hi else t


def _smoothstep(t: float) -> float:
    t = _clamp(t)
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp3(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    t: float,
) -> tuple[float, float, float]:
    return (_lerp(a[0], b[0], t), _lerp(a[1], b[1], t), _lerp(a[2], b[2], t))


@dataclass(frozen=True)
class CycleSample:
    """Lighting + sky palette for one instant of the cycle."""

    ambient: tuple[float, float, float]
    sun_color: tuple[float, float, float]
    sun_hpr: tuple[float, float, float]
    fill_color: tuple[float, float, float]
    fill_hpr: tuple[float, float, float]
    zenith: tuple[float, float, float]
    horizon_cool: tuple[float, float, float]
    horizon_warm: tuple[float, float, float]
    background: tuple[float, float, float]
    sun_phi_deg: float
    clock_text: str
    # Headlights / running tails: on from sunset through night until sunrise ends.
    vehicle_lights_on: bool


# Named palette anchors used by the phase blends.
_NIGHT = {
    "ambient": (0.06, 0.07, 0.12),
    "sun": (0.08, 0.1, 0.18),
    "fill": (0.04, 0.05, 0.09),
    "zenith": (0.02, 0.04, 0.1),
    "horizon_cool": (0.04, 0.05, 0.1),
    "horizon_warm": (0.07, 0.06, 0.12),
    "background": (0.03, 0.04, 0.09),
}
_DAWN = {
    "ambient": (0.28, 0.22, 0.26),
    "sun": (1.2, 0.55, 0.28),
    "fill": (0.22, 0.16, 0.2),
    "zenith": (0.18, 0.28, 0.48),
    "horizon_cool": (0.45, 0.4, 0.52),
    "horizon_warm": (1.0, 0.48, 0.22),
    "background": (0.55, 0.38, 0.32),
}
_DAY = {
    "ambient": (0.34, 0.37, 0.42),
    "sun": (1.15, 1.05, 0.9),
    "fill": (0.18, 0.22, 0.3),
    "zenith": (0.22, 0.42, 0.78),
    "horizon_cool": (0.62, 0.72, 0.86),
    "horizon_warm": (0.92, 0.82, 0.68),
    "background": (0.7, 0.78, 0.88),
}
_DUSK = {
    "ambient": (0.26, 0.2, 0.28),
    "sun": (1.15, 0.42, 0.22),
    "fill": (0.2, 0.14, 0.22),
    "zenith": (0.16, 0.2, 0.4),
    "horizon_cool": (0.38, 0.28, 0.42),
    "horizon_warm": (1.0, 0.4, 0.18),
    "background": (0.48, 0.28, 0.28),
}


def _mix_palettes(a: dict, b: dict, t: float) -> dict:
    t = _smoothstep(t)
    return {key: _lerp3(a[key], b[key], t) for key in a}


class DayNightCycle:
    """Advances on wall-clock dt; maps a 10-minute loop onto a 24h clock."""

    def __init__(self, start_elapsed: float = 0.0) -> None:
        # 0 = start of sunrise (06:00 on the HUD clock).
        self.elapsed = start_elapsed % CYCLE_SECONDS

    def update(self, dt: float) -> None:
        self.elapsed = (self.elapsed + max(0.0, dt)) % CYCLE_SECONDS

    def clock_hm(self) -> tuple[int, int]:
        # Full cycle → 24h, origin at 06:00 so sunrise lines up with morning.
        hours = (self.elapsed / CYCLE_SECONDS) * 24.0 + 6.0
        hours %= 24.0
        h = int(hours)
        m = int((hours - h) * 60.0)
        return h, m

    def clock_text(self) -> str:
        h, m = self.clock_hm()
        return f"{h:02d}:{m:02d}"

    def sample(self) -> CycleSample:
        t = self.elapsed
        # Phase blends for sky / light colour.
        if t < SUNRISE_SECONDS:
            # Night → dawn → day across the sunrise window.
            u = t / SUNRISE_SECONDS
            if u < 0.5:
                pal = _mix_palettes(_NIGHT, _DAWN, u * 2.0)
            else:
                pal = _mix_palettes(_DAWN, _DAY, (u - 0.5) * 2.0)
        elif t < DAY_SECONDS:
            pal = dict(_DAY)
        elif t < DAY_SECONDS + SUNSET_SECONDS:
            u = (t - DAY_SECONDS) / SUNSET_SECONDS
            if u < 0.5:
                pal = _mix_palettes(_DAY, _DUSK, u * 2.0)
            else:
                pal = _mix_palettes(_DUSK, _NIGHT, (u - 0.5) * 2.0)
        else:
            pal = dict(_NIGHT)

        sun_h, sun_p, sun_phi = self._sun_angles(t)
        # Night key becomes a dim cool moon; keep fill opposite the key.
        fill_h = (sun_h + 180.0) % 360.0
        fill_p = -22.0 if t < DAY_SECONDS + SUNSET_SECONDS * 0.5 else -18.0

        # On at sunset; stay on overnight; off once sunrise finishes into day.
        vehicle_lights_on = t >= DAY_SECONDS or t < SUNRISE_SECONDS
        return CycleSample(
            ambient=pal["ambient"],
            sun_color=pal["sun"],
            sun_hpr=(sun_h, sun_p, 0.0),
            fill_color=pal["fill"],
            fill_hpr=(fill_h, fill_p, 0.0),
            zenith=pal["zenith"],
            horizon_cool=pal["horizon_cool"],
            horizon_warm=pal["horizon_warm"],
            background=pal["background"],
            sun_phi_deg=sun_phi,
            clock_text=self.clock_text(),
            vehicle_lights_on=vehicle_lights_on,
        )

    def _sun_angles(self, t: float) -> tuple[float, float, float]:
        """Heading / pitch / sky-glow azimuth for the key light."""
        if t <= DAY_SECONDS:
            # 0 → east dawn, 0.5 → late-morning south, 1 → west dusk.
            u = t / DAY_SECONDS
            elevation = math.sin(u * math.pi)
            # Peek above the horizon during sunrise/sunset so the glow reads.
            sun_p = -4.0 - 56.0 * elevation
            sun_h = 90.0 - 180.0 * u
            sun_phi = sun_h
            return sun_h, sun_p, sun_phi

        # Night: moon arcs the opposite sky, low and cool.
        u = (t - DAY_SECONDS) / NIGHT_SECONDS
        elevation = math.sin(u * math.pi)
        sun_p = -12.0 - 28.0 * elevation
        sun_h = -90.0 - 180.0 * u
        return sun_h, sun_p, sun_h
