"""Entry point: ``python -m city``."""

from __future__ import annotations

from city.bootstrap import configure

_ARGS = configure()

from city.app import CityApp  # noqa: E402


def main() -> None:
    app = CityApp(screenshot=_ARGS.screenshot)
    if _ARGS.screenshot:
        app.capture()
    else:
        app.run()


if __name__ == "__main__":
    main()
