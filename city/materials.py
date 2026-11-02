"""Cached Panda3D materials for the software-city scene."""

from __future__ import annotations

from panda3d.core import Material

_SPHERE_MATERIAL: Material | None = None
_BLOCK_MATERIALS: dict[float, Material] = {}
_ROAD_MATERIAL: Material | None = None
_LAWN_MATERIAL: Material | None = None
_SQUARE_MATERIALS: dict[float, Material] = {}
_BROWN_MATERIALS: dict[float, Material] = {}
_SIGNAL_MATERIALS: dict[str, Material] = {}
_CAR_MATERIALS: dict[str, Material] = {}


def sphere_material() -> Material:
    global _SPHERE_MATERIAL
    if _SPHERE_MATERIAL is None:
        material = Material()
        material.setAmbient((0.15, 0.28, 0.4, 1))
        material.setDiffuse((0.25, 0.55, 0.85, 1))
        material.setSpecular((0.45, 0.45, 0.5, 1))
        material.setShininess(32)
        _SPHERE_MATERIAL = material
    return _SPHERE_MATERIAL


# One cool grey. ``1`` is the original tower; the band is wide enough to tell
# neighbours apart and narrow enough that they stay the same colour.
BLOCK_SHADES = (
    0.860, 1.009, 0.916, 1.084, 0.972, 1.140, 0.897, 1.047,
    0.953, 1.103, 0.879, 1.028, 0.935, 1.121, 0.991, 1.065,
)


def block_material(lightness: float = 1.0) -> Material:
    """Cool grey. Nearby ``lightness`` values stay the same colour at a different shade."""
    cached = _BLOCK_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    ambient = tuple(channel * lightness for channel in (0.45, 0.45, 0.47))
    diffuse = tuple(channel * lightness for channel in (0.78, 0.78, 0.80))
    specular = tuple(channel * lightness for channel in (0.55, 0.55, 0.55))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(32)
    _BLOCK_MATERIALS[lightness] = material
    return material


def road_material() -> Material:
    """Darker grey than the tower so the slab reads as a road."""
    global _ROAD_MATERIAL
    if _ROAD_MATERIAL is None:
        material = Material()
        material.setAmbient((0.22, 0.22, 0.23, 1))
        material.setDiffuse((0.42, 0.42, 0.43, 1))
        material.setSpecular((0.12, 0.12, 0.12, 1))
        material.setShininess(4)
        _ROAD_MATERIAL = material
    return _ROAD_MATERIAL


def lawn_material() -> Material:
    """Flat green for the housing-block pad, same finish weight as the road."""
    global _LAWN_MATERIAL
    if _LAWN_MATERIAL is None:
        material = Material()
        material.setAmbient((0.12, 0.28, 0.12, 1))
        material.setDiffuse((0.28, 0.55, 0.28, 1))
        material.setSpecular((0.08, 0.12, 0.08, 1))
        material.setShininess(4)
        _LAWN_MATERIAL = material
    return _LAWN_MATERIAL


# One yellow hue. Brightness scales this colour, so every square stays the same shade.
_YELLOW = (1.0, 0.82 / 0.95, 0.12 / 0.95)
_YELLOW_LEVELS = (0.50, 0.62, 0.74, 0.86, 1.0)


def square_material(lightness: float) -> Material:
    """Yellow of a single hue. ``lightness`` 0.95 matches the original square."""
    cached = _SQUARE_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    diffuse = tuple(channel * lightness for channel in _YELLOW)
    ambient = tuple(channel * 0.47 for channel in diffuse)
    specular = tuple(channel * 0.45 for channel in diffuse)
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(24)
    _SQUARE_MATERIALS[lightness] = material
    return material


def square_lightness(index: int) -> float:
    return _YELLOW_LEVELS[(index * 3) % len(_YELLOW_LEVELS)]


def brown_material(lightness: float = 1.0) -> Material:
    """Same brown hue. ``lightness`` 1 matches the door; lower values are darker."""
    cached = _BROWN_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    ambient = tuple(channel * lightness for channel in (0.28, 0.16, 0.07))
    diffuse = tuple(channel * lightness for channel in (0.50, 0.30, 0.13))
    specular = tuple(channel * lightness for channel in (0.25, 0.18, 0.1))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(16)
    _BROWN_MATERIALS[lightness] = material
    return material


def signal_material(name: str) -> Material:
    """Dark housing or a lit lamp colour for the blocky traffic lights."""
    cached = _SIGNAL_MATERIALS.get(name)
    if cached is not None:
        return cached
    colours = {
        "housing": ((0.08, 0.08, 0.09), (0.18, 0.18, 0.20), (0.08, 0.08, 0.08), 8),
        "red": ((0.55, 0.05, 0.05), (0.95, 0.12, 0.10), (0.6, 0.15, 0.1), 32),
        "amber": ((0.55, 0.35, 0.04), (0.95, 0.7, 0.1), (0.55, 0.4, 0.1), 32),
        "green": ((0.04, 0.45, 0.12), (0.1, 0.85, 0.25), (0.15, 0.5, 0.2), 32),
    }
    ambient, diffuse, specular, shininess = colours[name]
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(shininess)
    if name != "housing":
        material.setEmission((*tuple(channel * 0.35 for channel in diffuse), 1))
    _SIGNAL_MATERIALS[name] = material
    return material


def car_material(name: str) -> Material:
    """Paint, glass, trim, lamps, and rubber for the blocky car parts."""
    cached = _CAR_MATERIALS.get(name)
    if cached is not None:
        return cached
    # body matches the old solid-blue car; lamps emit so they read under sun.
    colours = {
        "body": ((0.15, 0.28, 0.4), (0.25, 0.55, 0.85), (0.45, 0.45, 0.5), 32, None),
        "glass": ((0.05, 0.08, 0.12), (0.12, 0.2, 0.28), (0.35, 0.4, 0.45), 48, None),
        "trim": ((0.06, 0.06, 0.07), (0.14, 0.14, 0.16), (0.2, 0.2, 0.22), 12, None),
        "wheel": ((0.04, 0.04, 0.04), (0.08, 0.08, 0.09), (0.05, 0.05, 0.05), 4, None),
        "headlight": (
            (0.55, 0.5, 0.35),
            (0.95, 0.9, 0.65),
            (0.7, 0.65, 0.4),
            40,
            (0.55, 0.5, 0.3),
        ),
        "taillight": (
            (0.45, 0.05, 0.05),
            (0.9, 0.12, 0.1),
            (0.55, 0.15, 0.1),
            32,
            (0.4, 0.05, 0.04),
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
    _CAR_MATERIALS[name] = material
    return material
