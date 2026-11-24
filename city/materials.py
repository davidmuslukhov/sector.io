"""Cached Panda3D materials for the Surrey city scene."""

from __future__ import annotations

from panda3d.core import Material

_BLOCK_MATERIALS: dict[float, Material] = {}
_CONCRETE_MATERIALS: dict[float, Material] = {}
_FACTORY_MATERIALS: dict[float, Material] = {}
_ROAD_MATERIAL: Material | None = None
_LAWN_MATERIAL: Material | None = None
_WATER_MATERIAL: Material | None = None
_SIDEWALK_MATERIAL: Material | None = None
_CURB_MATERIAL: Material | None = None
_ROOF_MATERIAL: Material | None = None
_PLINTH_MATERIAL: Material | None = None
_STACK_MATERIAL: Material | None = None
_MARK_MATERIAL: Material | None = None
_CENTERLINE_MATERIAL: Material | None = None
_FOLIAGE_MATERIAL: Material | None = None
_BARK_MATERIAL: Material | None = None
_SQUARE_MATERIALS: dict[float, Material] = {}
_BROWN_MATERIALS: dict[float, Material] = {}
_SIGNAL_MATERIALS: dict[str, Material] = {}
_CAR_MATERIALS: dict[str | tuple[str, tuple[float, float, float]], Material] = {}
_RGBA_MATERIALS: dict[tuple[float, float, float, float], Material] = {}


# Cool glass-blue towers. ``1`` is the base tint; the band keeps neighbours
# distinct without leaving the glass look.
BLOCK_SHADES = (
    0.860, 1.009, 0.916, 1.084, 0.972, 1.140, 0.897, 1.047,
    0.953, 1.103, 0.879, 1.028, 0.935, 1.121, 0.991, 1.065,
)


def block_material(lightness: float = 1.0) -> Material:
    """Reflective dark glass-blue facade for towers."""
    cached = _BLOCK_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    # Deep curtain-wall glass: dark blue body, bright specular highlights.
    ambient = tuple(channel * lightness for channel in (0.04, 0.08, 0.16))
    diffuse = tuple(channel * lightness for channel in (0.1, 0.2, 0.38))
    specular = tuple(channel * lightness for channel in (0.4, 0.55, 0.8))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(96)
    _BLOCK_MATERIALS[lightness] = material
    return material


def concrete_material(lightness: float = 1.0) -> Material:
    """Matte concrete for highway barriers, fences, and piers."""
    cached = _CONCRETE_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    # Slightly brighter so thin walls still read as solid under side lighting.
    ambient = tuple(channel * lightness for channel in (0.34, 0.33, 0.31))
    diffuse = tuple(channel * lightness for channel in (0.72, 0.7, 0.66))
    specular = tuple(channel * lightness for channel in (0.12, 0.12, 0.11))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(6)
    _CONCRETE_MATERIALS[lightness] = material
    return material


def factory_material(lightness: float = 1.0) -> Material:
    """Dark industrial brown for factory halls."""
    cached = _FACTORY_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    ambient = tuple(channel * lightness for channel in (0.12, 0.06, 0.035))
    diffuse = tuple(channel * lightness for channel in (0.28, 0.14, 0.08))
    specular = tuple(channel * lightness for channel in (0.06, 0.04, 0.03))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(4)
    _FACTORY_MATERIALS[lightness] = material
    return material


def road_material() -> Material:
    """Dark weathered asphalt — slightly warm so it sits in daylight."""
    global _ROAD_MATERIAL
    if _ROAD_MATERIAL is None:
        material = Material()
        material.setAmbient((0.055, 0.055, 0.06, 1))
        material.setDiffuse((0.14, 0.14, 0.145, 1))
        material.setSpecular((0.05, 0.05, 0.055, 1))
        material.setShininess(4)
        _ROAD_MATERIAL = material
    return _ROAD_MATERIAL


def lawn_material() -> Material:
    """Muted midsummer grass; low specular so it reads as turf, not plastic."""
    global _LAWN_MATERIAL
    if _LAWN_MATERIAL is None:
        material = Material()
        material.setAmbient((0.07, 0.15, 0.05, 1))
        material.setDiffuse((0.2, 0.42, 0.14, 1))
        material.setSpecular((0.025, 0.04, 0.018, 1))
        material.setShininess(2)
        _LAWN_MATERIAL = material
    return _LAWN_MATERIAL


def water_material() -> Material:
    """Fraser / Mud Bay water — cool blue readable even under dim sunrise light."""
    global _WATER_MATERIAL
    if _WATER_MATERIAL is None:
        material = Material()
        material.setAmbient((0.12, 0.28, 0.42, 1))
        material.setDiffuse((0.18, 0.48, 0.72, 1))
        material.setSpecular((0.35, 0.5, 0.62, 1))
        material.setShininess(64)
        material.setEmission((0.02, 0.06, 0.1, 1))
        _WATER_MATERIAL = material
    return _WATER_MATERIAL


_FOLIAGE_VARIANTS: dict[int, Material] = {}


def foliage_material(variant: int = 0) -> Material:
    """Tree canopy — a touch darker/richer than lawn turf.

    ``variant`` picks among a few greens so a street of trees isn't identical.
    """
    key = variant % 3
    cached = _FOLIAGE_VARIANTS.get(key)
    if cached is not None:
        return cached
    looks = (
        ((0.08, 0.16, 0.05), (0.18, 0.38, 0.12)),
        ((0.07, 0.15, 0.06), (0.16, 0.36, 0.14)),
        ((0.1, 0.15, 0.04), (0.22, 0.36, 0.1)),
    )
    ambient, diffuse = looks[key]
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((0.05, 0.08, 0.04, 1))
    material.setShininess(4)
    _FOLIAGE_VARIANTS[key] = material
    # Keep the no-arg cache pointing at variant 0 for older call sites.
    global _FOLIAGE_MATERIAL
    if key == 0:
        _FOLIAGE_MATERIAL = material
    return material


def bark_material() -> Material:
    """Warm trunk wood for street trees."""
    global _BARK_MATERIAL
    if _BARK_MATERIAL is None:
        material = Material()
        material.setAmbient((0.16, 0.1, 0.06, 1))
        material.setDiffuse((0.32, 0.2, 0.1, 1))
        material.setSpecular((0.06, 0.05, 0.04, 1))
        material.setShininess(4)
        _BARK_MATERIAL = material
    return _BARK_MATERIAL


def sidewalk_material() -> Material:
    """Pale poured concrete for walkways between curb and lot."""
    global _SIDEWALK_MATERIAL
    if _SIDEWALK_MATERIAL is None:
        material = Material()
        material.setAmbient((0.32, 0.31, 0.29, 1))
        material.setDiffuse((0.62, 0.6, 0.56, 1))
        material.setSpecular((0.12, 0.12, 0.11, 1))
        material.setShininess(5)
        _SIDEWALK_MATERIAL = material
    return _SIDEWALK_MATERIAL


def curb_material() -> Material:
    """Slightly darker concrete lip between asphalt and sidewalk."""
    global _CURB_MATERIAL
    if _CURB_MATERIAL is None:
        material = Material()
        material.setAmbient((0.26, 0.25, 0.24, 1))
        material.setDiffuse((0.48, 0.46, 0.43, 1))
        material.setSpecular((0.1, 0.1, 0.09, 1))
        material.setShininess(4)
        _CURB_MATERIAL = material
    return _CURB_MATERIAL


def roof_material() -> Material:
    """Dark membrane / slate for roofs and tower caps."""
    global _ROOF_MATERIAL
    if _ROOF_MATERIAL is None:
        material = Material()
        material.setAmbient((0.1, 0.1, 0.11, 1))
        material.setDiffuse((0.2, 0.2, 0.22, 1))
        material.setSpecular((0.08, 0.08, 0.09, 1))
        material.setShininess(10)
        _ROOF_MATERIAL = material
    return _ROOF_MATERIAL


def plinth_material() -> Material:
    """Dark grey stone base under each tower."""
    global _PLINTH_MATERIAL
    if _PLINTH_MATERIAL is None:
        material = Material()
        material.setAmbient((0.08, 0.08, 0.09, 1))
        material.setDiffuse((0.18, 0.18, 0.2, 1))
        material.setSpecular((0.06, 0.06, 0.07, 1))
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
_GLASS_DARK = (0.05, 0.08, 0.12)
_GLASS_LIT = (0.95, 0.74, 0.4)
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
    ambient = tuple(channel * 0.35 for channel in diffuse)
    specular = (0.7, 0.76, 0.84)
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(110)
    if mix > 0.35:
        material.setEmission((*tuple(channel * 0.5 * mix for channel in diffuse), 1))
    _SQUARE_MATERIALS[lightness] = material
    return material


def square_lightness(index: int) -> float:
    return _YELLOW_LEVELS[(index * 5 + 1) % len(_YELLOW_LEVELS)]


def brown_material(lightness: float = 1.0) -> Material:
    """Weathered wood / brick. ``lightness`` 1 matches the door; lower is darker."""
    cached = _BROWN_MATERIALS.get(lightness)
    if cached is not None:
        return cached
    # Slightly redder brick so houses separate from concrete towers.
    ambient = tuple(channel * lightness for channel in (0.24, 0.13, 0.09))
    diffuse = tuple(channel * lightness for channel in (0.48, 0.28, 0.18))
    specular = tuple(channel * lightness for channel in (0.1, 0.07, 0.05))
    material = Material()
    material.setAmbient((*ambient, 1))
    material.setDiffuse((*diffuse, 1))
    material.setSpecular((*specular, 1))
    material.setShininess(5)
    _BROWN_MATERIALS[lightness] = material
    return material


def rgba_material(
    rgba: tuple[float, float, float, float],
    *,
    shininess: float = 6.0,
) -> Material:
    """Cached matte facade / roof colour from an RGBA tuple (A ignored for lighting)."""
    key = (
        round(rgba[0], 4),
        round(rgba[1], 4),
        round(rgba[2], 4),
        round(rgba[3], 4),
    )
    cached = _RGBA_MATERIALS.get(key)
    if cached is not None:
        return cached
    r, g, b, _a = key
    material = Material()
    material.setAmbient((r * 0.45, g * 0.45, b * 0.45, 1))
    material.setDiffuse((r, g, b, 1))
    material.setSpecular((r * 0.12, g * 0.12, b * 0.12, 1))
    material.setShininess(shininess)
    _RGBA_MATERIALS[key] = material
    return material


# ambient, diffuse, specular, shininess, emission-or-None for each lens look.
_SIGNAL_LENS_LOOKS: dict[str, dict[bool, tuple]] = {
    "red": {
        True: (
            (0.65, 0.04, 0.03),
            (1.0, 0.1, 0.06),
            (0.6, 0.12, 0.08),
            64,
            (1.2, 0.08, 0.04),
        ),
        False: (
            (0.08, 0.02, 0.015),
            (0.12, 0.03, 0.025),
            (0.04, 0.02, 0.015),
            12,
            None,
        ),
    },
    "amber": {
        True: (
            (0.75, 0.38, 0.02),
            (1.0, 0.58, 0.04),
            (0.7, 0.32, 0.04),
            64,
            (1.3, 0.55, 0.0),
        ),
        False: (
            (0.08, 0.055, 0.01),
            (0.14, 0.1, 0.02),
            (0.05, 0.04, 0.015),
            12,
            None,
        ),
    },
    "green": {
        True: (
            (0.03, 0.5, 0.12),
            (0.08, 0.95, 0.25),
            (0.12, 0.55, 0.18),
            64,
            (0.06, 1.1, 0.2),
        ),
        False: (
            (0.01, 0.06, 0.025),
            (0.02, 0.1, 0.04),
            (0.02, 0.05, 0.03),
            12,
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
# Chicago green-wave buckets: offset seconds quantized into this many groups.
SIGNAL_WAVE_GROUPS = 24


def signal_material(name: str) -> Material:
    """Traffic-signal paint: yellow head or dark Chicago pole/trim."""
    cached = _SIGNAL_MATERIALS.get(name)
    if cached is not None:
        return cached
    # ambient, diffuse, specular, shininess, emission-or-None
    colours = {
        # Classic traffic-signal yellow housings.
        "housing": (
            (0.55, 0.42, 0.04),
            (0.92, 0.72, 0.05),
            (0.3, 0.25, 0.08),
            14,
            None,
        ),
        # Matte black / dark hunter-green poles & mast arms.
        "trim": (
            (0.04, 0.06, 0.05),
            (0.08, 0.11, 0.09),
            (0.05, 0.06, 0.05),
            4,
            None,
        ),
        "pole": (
            (0.04, 0.06, 0.05),
            (0.08, 0.11, 0.09),
            (0.05, 0.06, 0.05),
            4,
            None,
        ),
    }
    material = Material()
    _write_signal_look(material, colours[name])
    _SIGNAL_MATERIALS[name] = material
    return material


def signal_lens_material(colour: str, axis: str, wave: int = 0) -> Material:
    """Shared lit/unlit lens for one approach axis and green-wave bucket.

    Mutated in place by ``apply_signal_lenses`` / ``apply_signal_wave`` so
    flattened meshes keep animating without per-head NodePaths.
    """
    wave = int(wave) % SIGNAL_WAVE_GROUPS
    key = f"{colour}:{axis}:{wave}"
    cached = _SIGNAL_MATERIALS.get(key)
    if cached is not None:
        return cached
    material = Material()
    _write_signal_look(material, _SIGNAL_LENS_LOOKS[colour][False])
    _SIGNAL_MATERIALS[key] = material
    return material


def apply_signal_lenses(ns: str, ew: str, wave: int = 0) -> None:
    """Set active lens colour for one wave bucket (other lenses go dark)."""
    for axis, active in (("ns", ns), ("ew", ew)):
        for colour in _SIGNAL_LENS_LOOKS:
            _write_signal_look(
                signal_lens_material(colour, axis, wave),
                _SIGNAL_LENS_LOOKS[colour][colour == active],
            )


def apply_signal_wave(wave: int, ns: str, ew: str) -> None:
    """Alias for ``apply_signal_lenses`` with an explicit wave bucket."""
    apply_signal_lenses(ns, ew, wave=wave)


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
    # Default body is a cool blue; lamps emit so they read under sun.
    if name == "body":
        diffuse = colour or (0.22, 0.48, 0.72)
        ambient = tuple(channel * 0.4 for channel in diffuse)
        specular = (0.72, 0.72, 0.78)
        shininess = 64
        emission = None
    else:
        colours = {
            "glass": ((0.03, 0.05, 0.08), (0.07, 0.11, 0.16), (0.55, 0.62, 0.7), 96, None),
            "trim": ((0.05, 0.05, 0.055), (0.12, 0.12, 0.13), (0.22, 0.22, 0.25), 14, None),
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
