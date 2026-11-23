"""Intersection traffic-light timing and lens updates (Chicago green wave)."""

from __future__ import annotations

from city.materials import SIGNAL_WAVE_GROUPS, apply_signal_lenses

# Spec: 12s phase halves, yellow in the final 2.0s of each half.
_PHASE_S = 12.0
_YELLOW_S = 2.0
_GREEN_S = _PHASE_S - _YELLOW_S  # 10.0
_CYCLE_S = 2.0 * _PHASE_S  # 24.0


def _phase_colours(local_t: float) -> tuple[str, str]:
    """Return (ns, ew) lens colours for a local wave timer."""
    t = local_t % _CYCLE_S
    if t < _GREEN_S:
        return ("green", "red")
    if t < _PHASE_S:
        return ("amber", "red")
    if t < _PHASE_S + _GREEN_S:
        return ("red", "green")
    return ("red", "amber")


class TrafficLightController:
    """Chicago grid green wave: 12s N–S / 12s E–W with 2s yellow clearance.

    Spatial progression uses ``(abs(X)+abs(Y))*0.015`` quantized into
    ``SIGNAL_WAVE_GROUPS`` shared material buckets so flattened meshes still
    animate without per-head NodePaths.
    """

    def __init__(self, app) -> None:
        self.app = app
        self.clock = app.clock
        self._phase_by_wave: list[tuple[str, str] | None] = [
            None
        ] * SIGNAL_WAVE_GROUPS
        # Seed materials immediately.
        self.update(None)

    def update(self, task):
        t = self.clock.getFrameTime()
        for wave in range(SIGNAL_WAVE_GROUPS):
            # wave index ≈ offset seconds modulo cycle group count.
            local_t = t + float(wave)
            colours = _phase_colours(local_t)
            if colours == self._phase_by_wave[wave]:
                continue
            self._phase_by_wave[wave] = colours
            apply_signal_lenses(colours[0], colours[1], wave=wave)
        if task is None:
            return None
        return task.cont

    def approach_colour(self, direction: tuple[int, int], *, x: float = 0.0, y: float = 0.0) -> str:
        """Active lens colour for traffic approaching along ``direction``."""
        dx, dy = direction
        offset = (abs(x) + abs(y)) * 0.015
        wave = int(offset % SIGNAL_WAVE_GROUPS)
        ns, ew = self._phase_by_wave[wave] or ("green", "red")
        return ns if abs(dy) >= abs(dx) else ew

    def may_proceed(
        self,
        approach: tuple[int, int],
        turn: tuple[int, int],
        *,
        x: float = 0.0,
        y: float = 0.0,
    ) -> bool:
        """Whether a stopped car may leave the stop line for ``turn``."""
        cross = approach[0] * turn[1] - approach[1] * turn[0]
        if cross < 0:
            return True
        return self.approach_colour(approach, x=x, y=y) == "green"
