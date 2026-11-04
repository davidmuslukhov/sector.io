"""Intersection traffic-light timing and lens updates."""

from __future__ import annotations

from city.materials import apply_signal_lenses

# One axis greens while the other stays red; yellow clears before the swap.
_GREEN_S = 15.0
_YELLOW_S = 2.0
_HALF_S = _GREEN_S + _YELLOW_S
_CYCLE_S = 2.0 * _HALF_S


class TrafficLightController:
    """Alternates N–S and E–W: green 15s, yellow 2s, then the other pair.

    Opposing heads share an axis material set so flattened city meshes
    keep animating without per-head NodePaths.
    """

    def __init__(self, app) -> None:
        self.app = app
        self.clock = app.clock
        self._phase: tuple[str, str] | None = None
        self._apply("green", "red")

    def update(self, task):
        t = self.clock.getFrameTime() % _CYCLE_S
        if t < _GREEN_S:
            self._apply("green", "red")
        elif t < _HALF_S:
            self._apply("amber", "red")
        elif t < _HALF_S + _GREEN_S:
            self._apply("red", "green")
        else:
            self._apply("red", "amber")
        return task.cont

    def _apply(self, ns: str, ew: str) -> None:
        phase = (ns, ew)
        if phase == self._phase:
            return
        self._phase = phase
        apply_signal_lenses(ns, ew)
