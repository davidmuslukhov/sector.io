"""Apply window settings before Panda3D reads its config on import."""

from __future__ import annotations

import argparse

from panda3d.core import loadPrcFileData


def configure() -> argparse.Namespace:
    """Apply window settings before Panda3D reads its config on import."""
    parser = argparse.ArgumentParser(description="Open the Chicago, IL city scene.")
    parser.add_argument(
        "--screenshot",
        metavar="PATH",
        help="Render one offscreen frame to this image and exit.",
    )
    args = parser.parse_args()
    # The conda package keeps Config.prc under Library/etc, which Panda
    # does not find on its own when python.exe is launched directly.
    loadPrcFileData("", "load-display pandagl")
    loadPrcFileData("", "aux-display p3tinydisplay")
    if args.screenshot:
        loadPrcFileData("", "window-type offscreen")
        loadPrcFileData("", "audio-library-name null")
    loadPrcFileData("", "win-size 960 960")
    # Sync-to-vblank can make a heavy frame feel like half FPS.
    loadPrcFileData("", "sync-video 0")
    # MSAA off — large road plate; AA was a major GPU cost.
    loadPrcFileData("", "framebuffer-multisample 0")
    loadPrcFileData("", "multisamples 0")
    # Roads are untextured; anisotropy does nothing useful here.
    loadPrcFileData("", "texture-anisotropic-degree 1")
    # Skip unused fixed-function extras.
    loadPrcFileData("", "show-frame-rate-meter 0")
    return args
