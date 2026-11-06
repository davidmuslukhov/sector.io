"""Cached Panda3D materials for the software-city scene."""

from __future__ import annotations

from panda3d.core import Material

_SPHERE_MATERIAL: Material | None = None
_BLOCK_MATERIALS: dict[float, Material] = {}
_ROAD_MATERIAL: Material | None = None
_LAWN_MATERIAL: Material | None = None
_ROOF_MATERIAL: Material | None = None
_PLINTH_MATERIAL: Material | None = None
_STACK_MATERIAL: Material | None = None
_MARK_MATERIAL: Material | None = None
_CENTERLINE_MATERIAL: Material | None = None
_SQUARE_MATERIALS: dict[float, Material] = {}
_BROWN_MATERIALS: dict[float, Material] = {}
_SIGNAL_MATERIALS: dict[str, Material] = {}
_CAR_MATERIALS: dict[str | tuple[str, tuple[float, float, float]], Material] = {}


def sphere_material() -> Material:
    global _SPHERE_MATERIAL
    if _SPHERE_MATERIAL is None:
        material = Material()
        material.setAmbient((0.12, 0.22, 0.32, 1))
        material.setDiffuse((0.22, 0.48, 0.72, 1))
        material.setSpecular((0.55, 0.6, 0.65, 1))
        material.setShininess(48)
        _SPHERE_MATERIAL = material
    return _SPHERE_MATERIAL


# One cool grey. ``1`` is the original tower; the band is wide enough to tell
# neighbours apart and narrow enough that they stay the same colour.
BLOCK_SHADES = (
    0.860, 1.009, 0.916, 1.084, 0.972, 1.140, 0.897, 1.047,
    0.953, 1.103, 0.879, 1.028, 0.935, 1.121, 0.991, 1.065,
)


def block_material(lightness: float = 1.0) -> Material:
    """Matte concrete. Nearby ``lightness`` values stay the same colour at a different shade."""
    cached = _BLOCK_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    # Warm-leaning concrete rather than plastic cool grey.
    ambient = tuple(channel * lightness for channel in (0.36, 0.35, 0.33))
    diffuse = tuple(channel * lightness for channel in (0.58, 0.56, 0.52))
    specular = tuple(channel * lightness for channel in (0.14, 0.14, 0.13))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(6)
    _BLOCK_MATERIALS[lightness] = material
    return material


def road_material() -> Material:
    """Dark asphalt with a barely-there sheen."""
    global _ROAD_MATERIAL
    if _ROAD_MATERIAL is None:
        material = Material()
        material.setAmbient((0.08, 0.08, 0.085, 1))
        material.setDiffuse((0.18, 0.18, 0.19, 1))
        material.setSpecular((0.05, 0.05, 0.05, 1))
        material.setShininess(2)
        _ROAD_MATERIAL = material
    return _ROAD_MATERIAL


def lawn_material() -> Material:
    """Muted natural grass, same finish weight as the road."""
    global _LAWN_MATERIAL
    if _LAWN_MATERIAL is None:
        material = Material()
        material.setAmbient((0.12, 0.22, 0.09, 1))
        material.setDiffuse((0.28, 0.48, 0.20, 1))
        material.setSpecular((0.04, 0.06, 0.03, 1))
        material.setShininess(2)
        _LAWN_MATERIAL = material
    return _LAWN_MATERIAL


def roof_material() -> Material:
    """Dark membrane / slate for roofs and tower caps."""
    global _ROOF_MATERIAL
    if _ROOF_MATERIAL is None:
        material = Material()
        material.setAmbient((0.12, 0.12, 0.13, 1))
        material.setDiffuse((0.24, 0.24, 0.26, 1))
        material.setSpecular((0.1, 0.1, 0.1, 1))
        material.setShininess(8)
        _ROOF_MATERIAL = material
    return _ROOF_MATERIAL


def plinth_material() -> Material:
    """Darker stone base under each tower."""
    global _PLINTH_MATERIAL
    if _PLINTH_MATERIAL is None:
        material = Material()
        material.setAmbient((0.22, 0.21, 0.20, 1))
        material.setDiffuse((0.38, 0.36, 0.34, 1))
        material.setSpecular((0.1, 0.1, 0.09, 1))
        material.setShininess(4)
        _PLINTH_MATERIAL = material
    return _PLINTH_MATERIAL


def stack_material() -> Material:
    """Sooty factory / HVAC stacks."""
    global _STACK_MATERIAL
    if _STACK_MATERIAL is None:
        material = Material()
        material.setAmbient((0.14, 0.14, 0.15, 1))
        material.setDiffuse((0.28, 0.28, 0.30, 1))
        material.setSpecular((0.08, 0.08, 0.08, 1))
        material.setShininess(4)
        _STACK_MATERIAL = material
    return _STACK_MATERIAL


def mark_material() -> Material:
    """White lane paint for dashes and highway dividers."""
    global _MARK_MATERIAL
    if _MARK_MATERIAL is None:
        material = Material()
        material.setAmbient((0.55, 0.55, 0.52, 1))
        material.setDiffuse((0.92, 0.92, 0.88, 1))
        material.setSpecular((0.15, 0.15, 0.14, 1))
        material.setShininess(6)
        _MARK_MATERIAL = material
    return _MARK_MATERIAL


def centerline_material() -> Material:
    """Muted yellow centerline paint."""
    global _CENTERLINE_MATERIAL
    if _CENTERLINE_MATERIAL is None:
        material = Material()
        material.setAmbient((0.42, 0.34, 0.08, 1))
        material.setDiffuse((0.78, 0.64, 0.14, 1))
        material.setSpecular((0.2, 0.18, 0.08, 1))
        material.setShininess(6)
        _CENTERLINE_MATERIAL = material
    return _CENTERLINE_MATERIAL


# Most panes stay cool reflective glass; a few read as warm interiors.
_GLASS_DARK = (0.08, 0.11, 0.15)
_GLASS_LIT = (0.78, 0.62, 0.34)
_YELLOW_LEVELS = (0.50, 0.55, 0.62, 0.78, 1.0)


def square_material(lightness: float) -> Material:
    """Window glass. Higher ``lightness`` reads as a warmer lit pane."""
    cached = _SQUARE_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    t = max(0.0, min(1.0, (lightness - 0.50) / 0.50))
    # Bias toward dark glass so lit panes pop instead of washing the facade.
    mix = t * t
    diffuse = tuple(
        dark + (lit - dark) * mix for dark, lit in zip(_GLASS_DARK, _GLASS_LIT)
    )
    ambient = tuple(channel * 0.5 for channel in diffuse)
    specular = (0.42, 0.46, 0.5)
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(64)
    if mix > 0.45:
        material.setEmission((*tuple(channel * 0.32 * mix for channel in diffuse), 1))
    _SQUARE_MATERIALS[lightness] = material
    return material


def square_lightness(index: int) -> float:
    return _YELLOW_LEVELS[(index * 5 + 1) % len(_YELLOW_LEVELS)]


def brown_material(lightness: float = 1.0) -> Material:
    """Weathered wood / brick. ``lightness`` 1 matches the door; lower is darker."""
    cached = _BROWN_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    ambient = tuple(channel * lightness for channel in (0.22, 0.14, 0.08))
    diffuse = tuple(channel * lightness for channel in (0.42, 0.28, 0.16))
    specular = tuple(channel * lightness for channel in (0.12, 0.09, 0.06))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(6)
    _BROWN_MATERIALS[lightness] = material
    return material


# ambient, diffuse, specular, shininess, emission-or-None for each lens look.
_SIGNAL_LENS_LOOKS: dict[str, dict[bool, tuple]] = {
    "red": {
        True: (
            (0.55, 0.05, 0.04),
            (0.95, 0.12, 0.08),
            (0.55, 0.15, 0.1),
            48,
            (0.7, 0.08, 0.05),
        ),
        False: (
            (0.18, 0.04, 0.03),
            (0.28, 0.06, 0.05),
            (0.1, 0.04, 0.03),
            24,
            None,
        ),
    },
    "amber": {
        True: (
            (0.7, 0.35, 0.02),
            (1.0, 0.55, 0.05),
            (0.65, 0.3, 0.05),
            48,
            (1.0, 0.45, 0.0),
        ),
        False: (
            (0.18, 0.12, 0.02),
            (0.32, 0.22, 0.05),
            (0.12, 0.1, 0.04),
            24,
            None,
        ),
    },
    "green": {
        True: (
            (0.04, 0.45, 0.12),
            (0.1, 0.85, 0.28),
            (0.15, 0.5, 0.2),
            48,
            (0.08, 0.65, 0.18),
        ),
        False: (
            (0.02, 0.14, 0.05),
            (0.04, 0.22, 0.1),
            (0.06, 0.12, 0.08),
            24,
            None,
        ),
    },
}


def _write_signal_look(material: Material, look: tuple) -> None:
    ambient, diffuse, specular, shininess, emission = look
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(shininess)
    if emission is not None:
        material.setEmission((*emission, 1))
    else:
        material.setEmission((0, 0, 0, 1))


# Opposing approaches share a material set so flattenStrong still updates.
SIGNAL_AXES = ("ns", "ew")


def signal_material(name: str) -> Material:
    """Traffic-signal paint: yellow head or dark trim."""
    cached = _SIGNAL_MATERIALS.get(name)
    if cached is not None:
        return cached
    # ambient, diffuse, specular, shininess, emission-or-None
    colours = {
        # Classic US signal yellow.
        "housing": (
            (0.42, 0.34, 0.06),
            (0.78, 0.62, 0.12),
            (0.25, 0.22, 0.08),
            12,
            None,
        ),
        "trim": (
            (0.05, 0.05, 0.055),
            (0.1, 0.1, 0.11),
            (0.08, 0.08, 0.08),
            6,
            None,
        ),
    }
    material = Material()
    _write_signal_look(material, colours[name])
    _SIGNAL_MATERIALS[name] = material
    return material


def signal_lens_material(colour: str, axis: str) -> Material:
    """Shared lit/unlit lens for one approach axis (``ns`` or ``ew``).

    Mutated in place by ``apply_signal_lenses`` so flattened meshes update.
    """
    key = f"{colour}:{axis}"
    cached = _SIGNAL_MATERIALS.get(key)
    if cached is not None:
        return cached
    material = Material()
    _write_signal_look(material, _SIGNAL_LENS_LOOKS[colour][False])
    _SIGNAL_MATERIALS[key] = material
    return material


def apply_signal_lenses(ns: str, ew: str) -> None:
    """Set active lens colour per opposing pair (other lenses go dark)."""
    for axis, active in (("ns", ns), ("ew", ew)):
        for colour in _SIGNAL_LENS_LOOKS:
            _write_signal_look(
                signal_lens_material(colour, axis),
                _SIGNAL_LENS_LOOKS[colour][colour == active],
            )


def car_material(
    name: str,
    colour: tuple[float, float, float] | None = None,
) -> Material:
    """Paint, glass, trim, lamps, and rubber for the blocky car parts.

    Pass ``colour`` with ``name="body"`` for a custom paint job; other part
    names ignore it and share the usual cached materials.
    """
    key: str | tuple[str, tuple[float, float, float]]
    if name == "body" and colour is not None:
        key = ("body", colour)
    else:
        key = name
    cached = _CAR_MATERIALS.get(key)
    if cached is not None:
        return cached
    # Default body matches the landmark spheres; lamps emit so they read under sun.
    if name == "body":
        diffuse = colour or (0.22, 0.48, 0.72)
        ambient = tuple(channel * 0.45 for channel in diffuse)
        specular = (0.55, 0.55, 0.6)
        shininess = 40
        emission = None
    else:
        colours = {
            "glass": ((0.04, 0.06, 0.09), (0.08, 0.12, 0.18), (0.45, 0.5, 0.55), 64, None),
            "trim": ((0.05, 0.05, 0.055), (0.12, 0.12, 0.13), (0.18, 0.18, 0.2), 10, None),
            "wheel": ((0.03, 0.03, 0.03), (0.06, 0.06, 0.065), (0.04, 0.04, 0.04), 3, None),
            "headlight": (
                (0.5, 0.48, 0.35),
                (0.92, 0.88, 0.7),
                (0.65, 0.6, 0.4),
                48,
                (0.5, 0.48, 0.32),
            ),
            "taillight": (
                (0.4, 0.04, 0.04),
                (0.82, 0.1, 0.08),
                (0.5, 0.12, 0.08),
                36,
                (0.38, 0.04, 0.03),
            ),
        }
        ambient, diffuse, specular, shininess, emission = colours[name]
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(shininess)
    if emission is not None:
        material.setEmission((*emission, 1))
    _CAR_MATERIALS[key] = material
    return material
