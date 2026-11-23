"""WGS84 → Metro Vancouver 2× Panda3D world projection & city plate alignment.

Master origin: King George Blvd & 104 Ave (Whalley / Surrey City Centre).
Scale lock: 26.4 units = 1.0 km  →  1 unit = 37.9 m.
Pure north-up (X, Y) translation only — no city rotation (setH = 0).
All road geometry stays coplanar at Z = 0 (hierarchy may use 0.001–0.04).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

# ---------------------------------------------------------------------------
# 1. Master geographic origin & exact scale lock
# ---------------------------------------------------------------------------

LAT0 = 49.1913  # degrees N
LON0 = -122.8490  # degrees W (King George & 104 Ave)

METERS_PER_UNIT = 37.9  # 26.4 units = 1.0 km
UNITS_PER_KM = 1000.0 / METERS_PER_UNIT  # 26.385... ≈ 26.4

M_LAT = 111_132.0  # m / deg latitude
# 111_320 * cos(49.1913°) ≈ 72_745 m/deg longitude at Whalley
M_LON = 72_745.0

# Direct Google Maps GPS → Panda3D multipliers (north-up, no rotation):
#   X = (lon - LON0) * X_PER_DEG
#   Y = (lat - LAT0) * Y_PER_DEG
X_PER_DEG = M_LON / METERS_PER_UNIT  # ≈ 1919.4
Y_PER_DEG = M_LAT / METERS_PER_UNIT  # ≈ 2932.2

# Regional extent used for camera / culling guidance.
WORLD_X_MIN, WORLD_X_MAX = -680.0, 820.0
WORLD_Y_MIN, WORLD_Y_MAX = -300.0, 520.0
CAMERA_FAR_CLIP = 6000.0

# Minor Z offsets by road hierarchy (z-fighting only; still "flat").
Z_LAYER = {
    "local": 0.0,
    "collector": 0.001,
    "arterial": 0.01,
    "highway": 0.02,
    "freeway": 0.04,
}


def project(lat: float, lon: float) -> tuple[float, float]:
    """Equirectangular local projection → world (X east, Y north)."""
    x = (lon - LON0) * X_PER_DEG
    y = (lat - LAT0) * Y_PER_DEG
    return (x, y)


def unproject(x: float, y: float) -> tuple[float, float]:
    """Inverse of :func:`project` → (lat, lon) WGS84."""
    lon = LON0 + x / X_PER_DEG
    lat = LAT0 + y / Y_PER_DEG
    return (lat, lon)


def round_xy(x: float, y: float, nd: int = 1) -> tuple[float, float]:
    def _r(v: float) -> float:
        v = round(v, nd)
        if abs(v - round(v)) < 1e-9:
            return float(int(round(v)))
        return v

    return (_r(x), _r(y))


# ---------------------------------------------------------------------------
# 2. Exact Google Maps city centres → Panda3D (X, Y)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CityCentre:
    """Downtown / centre reference for pure north-up plate translation."""

    key: str
    title: str
    reference: str
    lat: float
    lon: float
    target: tuple[float, float]  # mandated world XY from GPS formula
    procedural: tuple[float, float]  # pre-georef downtown on calibrate plate
    locked: bool = False  # True → identity (Surrey / Langley master plate)


# Procedural downtown anchors match calibrate_surrey_2x.py named corridors.
CITY_CENTRES: tuple[CityCentre, ...] = (
    CityCentre(
        "surrey",
        "Surrey (Origin)",
        "King George Blvd & 104 Ave",
        49.1913,
        -122.8490,
        (0.0, 0.0),
        (0.0, 0.0),
        locked=True,
    ),
    CityCentre(
        "new_westminster",
        "New Westminster",
        "Columbia St & 8th St",
        49.2014,
        -122.9126,
        (-122.1, 29.6),
        (-25.0, 57.5),
    ),
    CityCentre(
        "delta",
        "Delta (North)",
        "Scott Rd & 84 Ave",
        49.1554,
        -122.8906,
        (-79.9, -105.3),
        (-84.4, -52.8),
    ),
    CityCentre(
        "richmond",
        "Richmond",
        "No. 3 Rd & Westminster Hwy",
        49.1700,
        -123.1368,
        (-552.4, -62.5),
        (-431.5, -1.1),
    ),
    CityCentre(
        "burnaby",
        "Burnaby",
        "Kingsway & Willingdon (Metrotown)",
        49.2276,
        -123.0076,
        (-304.4, 106.4),
        (-135.8, 118.0),
    ),
    CityCentre(
        "vancouver",
        "Vancouver",
        "W Georgia St & Granville St",
        49.2827,
        -123.1207,
        (-521.5, 268.0),
        (-442.0, 256.0),
    ),
    CityCentre(
        "north_vancouver",
        "North Vancouver",
        "Lonsdale Ave & Esplanade",
        49.3118,
        -123.0795,
        (-442.4, 353.3),
        (-431.5, 345.0),
    ),
    CityCentre(
        "coquitlam",
        "Coquitlam",
        "Lougheed Hwy & Pinetree Way",
        49.2781,
        -122.7925,
        (108.4, 254.5),
        (120.0, 195.0),
    ),
    CityCentre(
        "port_moody",
        "Port Moody",
        "St. Johns St & Moody St",
        49.2776,
        -122.8493,
        (-0.6, 253.0),
        (82.0, 250.0),
    ),
    CityCentre(
        "port_coquitlam",
        "Port Coquitlam",
        "Shaughnessy St & Lougheed Hwy",
        49.2626,
        -122.7811,
        (130.3, 209.1),
        (142.0, 145.0),
    ),
    CityCentre(
        "pitt_meadows",
        "Pitt Meadows",
        "Harris Rd & Lougheed Hwy",
        49.2215,
        -122.6895,
        (306.1, 88.6),
        (306.0, 72.0),
    ),
    CityCentre(
        "langley",
        "Langley",
        "200 St & Fraser Hwy",
        49.1044,
        -122.6604,
        (362.0, -254.8),
        (316.5, -170.3),
        locked=True,  # continuous Surrey–Langley plate
    ),
    CityCentre(
        "maple_ridge",
        "Maple Ridge",
        "224 St & Lougheed Hwy",
        49.2193,
        -122.5984,
        (481.0, 82.1),
        (443.1, 58.0),
    ),
)

# Secondary reference only (same Delta plate as North Delta).
DELTA_LADNER_CENTRE = CityCentre(
    "delta_ladner",
    "Delta (Ladner)",
    "Hwy 17A & Ladner Trunk Rd",
    49.0910,
    -123.0816,
    (-446.5, -294.1),
    (-345.4, -211.0),
    locked=True,
)


def city_centre_by_key(key: str) -> CityCentre:
    for c in CITY_CENTRES:
        if c.key == key:
            return c
    raise KeyError(key)


def verify_city_centres(
    *,
    tol: float = 0.15,
) -> list[tuple[str, tuple[float, float], tuple[float, float], float]]:
    """Return (key, projected, mandated_target, err) for each city centre."""
    out: list[tuple[str, tuple[float, float], tuple[float, float], float]] = []
    for c in CITY_CENTRES:
        xy = round_xy(*project(c.lat, c.lon))
        err = math.hypot(xy[0] - c.target[0], xy[1] - c.target[1])
        out.append((c.key, xy, c.target, err))
    return out


# ---------------------------------------------------------------------------
# 3. Mandatory inter-city bridge stitch checkpoints (target world XY)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StitchCheckpoint:
    name: str
    lat: float | None
    lon: float | None
    target: tuple[float, float]  # mandated world XY after city translation
    cities: tuple[str, ...]


def _cp(
    name: str,
    target: tuple[float, float],
    *cities: str,
    lat: float | None = None,
    lon: float | None = None,
) -> StitchCheckpoint:
    return StitchCheckpoint(name, lat, lon, target, cities)


# Bridge abutments after pure city-centre translation (stretch/snap only).
STITCH_CHECKPOINTS: tuple[StitchCheckpoint, ...] = (
    # Pattullo Bridge (Hwy 1A) — McBride → King George / Whalley
    _cp("pattullo_surrey", (0.0, 0.0), "surrey", "new_westminster"),
    _cp("pattullo_surrey_approach", (-75.0, -5.0), "surrey", "new_westminster"),
    _cp("pattullo_newwest", (-108.0, 28.0), "surrey", "new_westminster"),
    # Port Mann Bridge (Hwy 1)
    _cp("port_mann_surrey", (70.0, 89.0), "surrey", "coquitlam"),
    _cp("port_mann_coquitlam", (75.0, 135.0), "surrey", "coquitlam"),
    # Alex Fraser Bridge (Hwy 91)
    _cp("alex_fraser_delta", (-175.0, -95.0), "delta", "richmond"),
    _cp("alex_fraser_richmond", (-235.0, -35.0), "delta", "richmond"),
    # George Massey Tunnel (Hwy 99)
    _cp("massey_ladner", (-435.0, -205.0), "delta", "richmond"),
    _cp("massey_richmond", (-485.0, -145.0), "delta", "richmond"),
    # Oak Street Bridge (Hwy 99)
    _cp("oak_richmond", (-536.0, 20.0), "richmond", "vancouver"),
    _cp("oak_vancouver", (-536.0, 52.0), "richmond", "vancouver"),
    # Knight Street Bridge
    _cp("knight_richmond", (-439.0, 36.0), "richmond", "vancouver"),
    _cp("knight_vancouver", (-439.0, 65.0), "richmond", "vancouver"),
    # Lions Gate Bridge (Hwy 99)
    _cp("lions_gate_stanley", (-555.0, 362.0), "vancouver", "north_vancouver"),
    _cp("lions_gate_nv", (-545.0, 395.0), "vancouver", "north_vancouver"),
    # Ironworkers Memorial Bridge (Hwy 1)
    _cp("ironworkers_vancouver", (-340.0, 305.0), "vancouver", "north_vancouver"),
    _cp("ironworkers_nv", (-335.0, 355.0), "vancouver", "north_vancouver"),
    # Golden Ears Bridge
    _cp("golden_ears_langley", (288.0, 46.0), "langley", "maple_ridge"),
    _cp("golden_ears_maple_ridge", (295.0, 85.0), "langley", "maple_ridge"),
    # Pitt River Bridge (Hwy 7)
    _cp("pitt_river_poco", (223.0, 142.0), "port_coquitlam", "pitt_meadows"),
    _cp("pitt_river_pitt_meadows", (245.0, 135.0), "port_coquitlam", "pitt_meadows"),
)


def verify_projection(
    *,
    tol: float = 1.0,
) -> list[tuple[str, tuple[float, float], tuple[float, float], float]]:
    """Return (name, projected, target, err) for checkpoints with lat+lon."""
    out: list[tuple[str, tuple[float, float], tuple[float, float], float]] = []
    for cp in STITCH_CHECKPOINTS:
        if cp.lat is None or cp.lon is None:
            continue
        xy = project(cp.lat, cp.lon)
        err = math.hypot(xy[0] - cp.target[0], xy[1] - cp.target[1])
        out.append((cp.name, xy, cp.target, err))
    return out


def checkpoint_by_name(name: str) -> StitchCheckpoint:
    for cp in STITCH_CHECKPOINTS:
        if cp.name == name:
            return cp
    raise KeyError(name)


# ---------------------------------------------------------------------------
# Rigid-body transform (2D Kabsch / Procrustes)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rigid2D:
    """x' = R @ x + t  (rotation about origin then translate)."""

    cos: float
    sin: float
    tx: float
    ty: float

    @staticmethod
    def identity() -> "Rigid2D":
        return Rigid2D(1.0, 0.0, 0.0, 0.0)

    @staticmethod
    def translate(tx: float, ty: float) -> "Rigid2D":
        return Rigid2D(1.0, 0.0, tx, ty)

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return (self.cos * x - self.sin * y + self.tx, self.sin * x + self.cos * y + self.ty)

    def apply_pt(self, pt: Sequence[float]) -> tuple[float, float]:
        return self.apply(float(pt[0]), float(pt[1]))

    def then(self, other: "Rigid2D") -> "Rigid2D":
        """Return transform equivalent to self then other."""
        # other.apply(self.apply(p))
        cos = other.cos * self.cos - other.sin * self.sin
        sin = other.sin * self.cos + other.cos * self.sin
        tx, ty = other.apply(self.tx, self.ty)
        return Rigid2D(cos, sin, tx, ty)


def rigid_align(
    src: Sequence[tuple[float, float]],
    dst: Sequence[tuple[float, float]],
) -> Rigid2D:
    """Best-fit rigid transform mapping src → dst (Kabsch, equal weights).

    Kept for diagnostics; production plates use :func:`translate_align` only.
    """
    if len(src) != len(dst) or not src:
        raise ValueError("src/dst must be non-empty and same length")
    if len(src) == 1:
        return Rigid2D.translate(dst[0][0] - src[0][0], dst[0][1] - src[0][1])

    n = float(len(src))
    sx = sum(p[0] for p in src) / n
    sy = sum(p[1] for p in src) / n
    dx = sum(p[0] for p in dst) / n
    dy = sum(p[1] for p in dst) / n

    sxx = syy = sxy = syx = 0.0
    for (x0, y0), (x1, y1) in zip(src, dst):
        sxx += (x0 - sx) * (x1 - dx)
        sxy += (x0 - sx) * (y1 - dy)
        syx += (y0 - sy) * (x1 - dx)
        syy += (y0 - sy) * (y1 - dy)

    ang = math.atan2(sxy - syx, sxx + syy)
    c, s = math.cos(ang), math.sin(ang)
    tx = dx - (c * sx - s * sy)
    ty = dy - (s * sx + c * sy)
    return Rigid2D(c, s, tx, ty)


def translate_align(
    src: Sequence[tuple[float, float]],
    dst: Sequence[tuple[float, float]],
) -> Rigid2D:
    """Pure north-up translation mapping src centroid → dst centroid (no rotation)."""
    if len(src) != len(dst) or not src:
        raise ValueError("src/dst must be non-empty and same length")
    n = float(len(src))
    sx = sum(p[0] for p in src) / n
    sy = sum(p[1] for p in src) / n
    dx = sum(p[0] for p in dst) / n
    dy = sum(p[1] for p in dst) / n
    return Rigid2D.translate(dx - sx, dy - sy)


# ---------------------------------------------------------------------------
# City plate specs — procedural downtown → Google Maps centre (translate only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CityPlate:
    key: str
    """Route-key predicates; first matching plate wins (most specific first)."""
    match: Callable[[str], bool]
    district_keys: frozenset[str]
    """Source/target downtown pairs for pure translation. Empty → identity."""
    anchors_src: tuple[tuple[float, float], ...]
    anchors_dst: tuple[tuple[float, float], ...]


def _pref(*prefixes: str) -> Callable[[str], bool]:
    prefs = tuple(prefixes)

    def _m(key: str) -> bool:
        return any(key == p or key.startswith(p + "_") or key.startswith(p) for p in prefs)

    return _m


def _keys(*exact: str) -> Callable[[str], bool]:
    s = frozenset(exact)

    def _m(key: str) -> bool:
        return key in s

    return _m


def _any_of(*fns: Callable[[str], bool]) -> Callable[[str], bool]:
    def _m(key: str) -> bool:
        return any(f(key) for f in fns)

    return _m


def _centre_pair(key: str) -> tuple[tuple[tuple[float, float], ...], tuple[tuple[float, float], ...]]:
    """Return (procedural,), (target,) for a city centre, or empty if locked."""
    c = city_centre_by_key(key)
    if c.locked:
        return (), ()
    return (c.procedural,), (c.target,)


# Order: most specific city plates first. Surrey/Langley stay locked (identity)
# so the Whalley origin and continuous 196 St plate are preserved; satellite
# cities translate (no rotation) onto Google Maps downtown centres.
CITY_PLATES: tuple[CityPlate, ...] = (
    CityPlate(
        "north_vancouver",
        _any_of(
            _pref("nv"),
            _keys(
                "hwy1_nv",
                "lions_gate",
                "capilano_rd",
                "marine_nv",
                "keith_rd",
                "mt_seymour_pkwy",
            ),
        ),
        frozenset(
            {
                "city_of_north_vancouver",
                "district_of_north_vancouver",
                "lower_lonsdale",
                "upper_lonsdale",
                "lynn_valley",
                "edgemont_village",
                "capilano_highlands",
                "deep_cove",
                "seymour",
            }
        ),
        *_centre_pair("north_vancouver"),
    ),
    CityPlate(
        "maple_ridge",
        _pref("mr"),
        frozenset(
            {
                "district_of_maple_ridge",
                "haney",
                "hammond",
                "albion",
                "whonnock",
                "ruskin",
                "websters_corners",
                "silver_valley",
            }
        ),
        *_centre_pair("maple_ridge"),
    ),
    CityPlate(
        "pitt_meadows",
        _any_of(_pref("pm"), _keys("lougheed_hwy", "airport_way", "airport_loop")),
        frozenset(
            {
                "district_of_pitt_meadows",
                "pitt_meadows_town",
                "pitt_polder",
            }
        ),
        *_centre_pair("pitt_meadows"),
    ),
    CityPlate(
        "port_coquitlam",
        _any_of(
            _pref("poco", "lincoln_park", "mary_hill", "citadel"),
            _keys(
                "lincoln_ave",
                "lincoln_ave_pc",
                "mary_hill_bypass",
                "mary_hill_rd",
                "mary_hill_pc",
                "shaughnessy_st",
                "westwood_st",
            ),
        ),
        frozenset(
            {
                "port_coquitlam",
                "poco_downtown",
                "lincoln_park",
                "riverwood",
                "mary_hill",
                "citadel_heights",
            }
        ),
        *_centre_pair("port_coquitlam"),
    ),
    CityPlate(
        "port_moody",
        lambda k: (
            k.endswith("_pomo")
            or k.endswith("_pomo_e")
            or k.endswith("_pomo_w")
            or k.startswith("pomo")
            or k
            in {
                "ioco_rd",
                "st_johns_st",
                "moody_st",
                "guildford_pomo",
                "clarke_rd_pomo",
                "clarke_st_pomo",
                "elgin_st_pomo",
                "queen_st_pomo",
                "spring_st_pomo",
                "williams_st_pomo",
                "barnet_pomo_e",
                "barnet_pomo_w",
            }
        ),
        frozenset(
            {
                "port_moody",
                "moody_centre",
                "newport_village",
                "glenayre",
                "pleasantside",
                "heritage_mountain",
            }
        ),
        *_centre_pair("port_moody"),
    ),
    CityPlate(
        "coquitlam",
        _any_of(
            _pref("cq", "coq", "burquitlam"),
            _keys(
                "hwy1_cq",
                "lougheed_cq",
                "brunette_cq",
                "como_lake_ave",
                "barnet_cq",
                "westwood_plateau",
                "north_rd",
                "pinetree_way",
            ),
        ),
        frozenset(
            {
                "coquitlam",
                "maillardville",
                "burquitlam",
                "coq_centre",
                "westwood_plateau",
                "burke_mountain",
            }
        ),
        *_centre_pair("coquitlam"),
    ),
    CityPlate(
        "new_westminster",
        _any_of(
            _pref("nw", "qb", "mcbride"),
            _keys(
                "mcbride_blvd",
                "brunette_ave",
                "ewen_ave",
                "boyd_st",
                "salter_st",
                "howes_st",
                "pembroke_st",
                "wood_st",
                "boyne_st",
            ),
        ),
        frozenset(
            {
                "new_westminster",
                "nw_downtown",
                "nw_uptown",
                "sapperton",
                "queensborough",
            }
        ),
        *_centre_pair("new_westminster"),
    ),
    CityPlate(
        "burnaby",
        _any_of(
            _pref(
                "bn",
                "metrotown",
                "edmonds",
                "brentwood",
                "sfu",
                "gilmore",
                "willingdon",
                "royal_oak",
                "nelson_ave",
                "sperling",
                "kensington",
                "cariboo",
                "griffiths",
                "alpha_ave",
                "beta_ave",
                "mckay",
                "sussex",
                "burke_st",
                "central_blvd",
                "beresford",
                "grange_st",
                "dawson_st",
                "alaska_st",
                "halifax_st",
                "parker_st",
                "delta_ave",
                "strachan",
                "ave_14th_bn",
                "ave_16th_bn",
                "ave_18th_bn",
                "austin_rd",
                "cameron_st",
                "beaverbrook",
                "bartlett",
            ),
            _keys(
                "hwy1_bn",
                "marine_stewardson",
                "kingsway_bn",
                "canada_way",
                "lougheed_bn",
                "hastings_barnet",
                "gaglardi_way",
                "imperial_st",
                "rumble_st",
                "north_fraser_way",
                "gilmore_ave",
                "willingdon_ave",
                "royal_oak_ave",
                "nelson_ave",
                "sperling_ave",
                "kensington_ave",
                "cariboo_rd",
                "alpha_ave",
                "beta_ave",
                "boundary_rd_n",
                "bn_broadway_e",
                "bn_mtn_pkwy",
                "sfu_ring",
                "sfu_hastings_spur",
                "edmonds_st",
            ),
        ),
        frozenset(
            {
                "burnaby",
                "metrotown",
                "brentwood",
                "lougheed_tc",
                "edmonds",
                "sfu",
                "burnaby_heights",
                "deer_lake",
            }
        ),
        *_centre_pair("burnaby"),
    ),
    CityPlate(
        "vancouver",
        _any_of(
            _pref("van", "dt", "ubc"),
            _keys(
                "sw_marine",
                "arthur_laing",
                "knight_st",
                "ave_41st",
                "ave_16th",
                "broadway",
                "kingsway",
                "hwy1_van",
                "chancellor_blvd",
                "university_blvd",
                "ubc_marine_loop",
                "hastings_st",
                "granville_st",
                "cambie_st",
                "main_st",
                "oak_st",
                "boundary_rd",
                "georgia_st",
                "burrard_st",
                "denman_st",
                "davie_st",
            ),
        ),
        frozenset(
            {
                "vancouver",
                "downtown_vancouver",
                "ubc",
                "kitsilano",
                "east_vancouver",
                "mount_pleasant",
                "hastings_sunrise",
                "marpole",
                "oakridge",
                "kerrisdale",
            }
        ),
        *_centre_pair("vancouver"),
    ),
    CityPlate(
        "richmond",
        _any_of(
            _pref(
                "no_",
                "richmond",
                "bridgeport",
                "steveston",
                "blundell",
                "francis",
                "williams",
                "garden_city",
                "gilbert",
                "shell",
                "alderbridge",
                "lansdowne",
                "grant_mcconachie",
                "russ_baker",
                "sea_island",
                "brighouse",
            ),
            _keys(
                "westminster_hwy",
                "hwy91a",
                "richmond_river",
                "no_1_rd",
                "no_2_rd",
                "no_3_rd",
                "no_4_rd",
                "no_5_rd",
                "no_6_rd",
                "no_7_rd",
                "no_8_rd",
                "steveston_hwy",
                "williams_rd",
                "francis_rd",
                "blundell_rd",
                "bridgeport_rd",
                "garden_city_rd",
                "gilbert_rd",
                "shell_rd",
            ),
        ),
        frozenset(
            {
                "richmond",
                "steveston",
                "brighouse",
                "bridgeport",
                "cambie",
                "broadmoor",
                "east_richmond",
                "seaforth",
            }
        ),
        *_centre_pair("richmond"),
    ),
    CityPlate(
        "delta",
        _any_of(
            _pref("delta", "nd", "lad", "tsw"),
            _keys(
                "nordel",
                "ladner_trunk",
                "arthur_dr",
                "river_rd",
                "hwy17a",
            ),
        ),
        frozenset(
            {
                "delta",
                "north_delta",
                "ladner",
                "tsawwassen",
            }
        ),
        *_centre_pair("delta"),
    ),
    # Surrey + Langley: identity — master plate locked at Whalley / 196 St.
    CityPlate(
        "langley",
        _any_of(
            _pref("lg", "wg", "wb", "wlb", "lc", "mv", "bw", "ag"),
            _keys("hwy10_langley", "hwy13", "glover_rd", "fraser_hwy_e"),
        ),
        frozenset(
            {
                "district_of_langley",
                "langley_city",
                "willowbrook",
                "walnut_grove",
                "willoughby",
                "murrayville",
                "brookswood",
                "aldergrove",
                "rural_north_langley",
                "rural_south_langley",
            }
        ),
        (),
        (),
    ),
    CityPlate(
        "surrey",
        lambda _k: True,  # fallback catch-all (identity)
        frozenset(
            {
                "surrey",
                "city_centre",
                "whalley",
                "newton",
                "guildford",
                "fleetwood",
                "cloverdale",
                "south_surrey",
            }
        ),
        (),
        (),
    ),
)


# Provincial corridors spanning multiple cities — snap vertices to stitch
# targets instead of a single plate transform.
SHARED_ROUTE_KEYS = frozenset(
    {
        "hwy99",
        "hwy91",
        "hwy91a",
        "hwy17",
        "hwy1",
        "golden_ears",
        "golden_ears_e",
        "lions_gate",
        "mcbride_blvd",
    }
)


def plate_transform(plate: CityPlate) -> Rigid2D:
    """Pure north-up translation of the city downtown onto its Google Maps centre."""
    if not plate.anchors_src:
        return Rigid2D.identity()
    return translate_align(plate.anchors_src, plate.anchors_dst)


def transforms_by_city() -> dict[str, Rigid2D]:
    return {p.key: plate_transform(p) for p in CITY_PLATES}


def classify_route(key: str) -> str:
    """Return city plate key for a highway route name."""
    if key in SHARED_ROUTE_KEYS:
        return "shared"
    for plate in CITY_PLATES:
        if plate.key in ("surrey", "langley"):
            # Evaluate named plates before the surrey catch-all.
            if plate.key == "langley" and plate.match(key):
                return "langley"
            continue
        if plate.match(key):
            return plate.key
    # Langley explicit
    for plate in CITY_PLATES:
        if plate.key == "langley" and plate.match(key):
            return "langley"
    return "surrey"


def _xform_points(
    points: Iterable[Sequence[float]],
    xform: Rigid2D,
    *,
    nd: int = 1,
) -> list[list[float]]:
    out: list[list[float]] = []
    for p in points:
        x, y = xform.apply(float(p[0]), float(p[1]))
        rx, ry = round_xy(x, y, nd)
        out.append([rx, ry])
    return out


def _nearest_vertex(points: list, target: tuple[float, float]) -> int:
    best_i, best_d = 0, float("inf")
    tx, ty = target
    for i, p in enumerate(points):
        d = math.hypot(float(p[0]) - tx, float(p[1]) - ty)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def snap_checkpoints_to_routes(
    highways: dict,
    *,
    search_radius: float = 200.0,
    claim_tol: float = 1.0,
) -> dict[str, float]:
    """Insert / claim abutment vertices on relevant routes at stitch targets.

    Dual abutments on the same corridor (e.g. Massey Ladner ↔ Richmond) each
    get their own vertex — a vertex already claimed by another checkpoint is
    never overwritten.
    """
    residuals: dict[str, float] = {}
    # Map checkpoint → route keys that should carry it (exact key match).
    route_hints: dict[str, tuple[str, ...]] = {
        "pattullo_surrey": ("mcbride_blvd", "king_george"),
        "pattullo_surrey_approach": ("mcbride_blvd", "king_george"),
        "pattullo_newwest": ("mcbride_blvd",),
        "port_mann_surrey": ("hwy1", "hwy1_cq", "hwy17"),
        "port_mann_coquitlam": ("hwy1", "hwy1_cq", "hwy1_bn"),
        "alex_fraser_delta": ("hwy91", "hwy17"),
        "alex_fraser_richmond": ("hwy91", "hwy91a"),
        "massey_ladner": ("hwy99",),
        "massey_richmond": ("hwy99",),
        "oak_richmond": ("hwy99", "no_3_rd", "oak_st", "sw_marine"),
        "oak_vancouver": ("hwy99", "oak_st", "sw_marine"),
        "knight_richmond": ("knight_st", "hwy91", "no_5_rd"),
        "knight_vancouver": ("knight_st", "hwy91"),
        "lions_gate_stanley": ("lions_gate", "georgia_st"),
        "lions_gate_nv": ("lions_gate", "marine_nv", "capilano_rd"),
        "ironworkers_vancouver": ("hwy1_van", "hwy1_nv", "hwy1"),
        "ironworkers_nv": ("hwy1_van", "hwy1_nv", "hwy1"),
        "golden_ears_langley": ("golden_ears", "golden_ears_e"),
        "golden_ears_maple_ridge": ("golden_ears", "golden_ears_e"),
        "pitt_river_poco": ("lougheed_hwy", "lougheed_pc"),
        "pitt_river_pitt_meadows": ("lougheed_hwy",),
    }

    # (route_key, vertex_index) already locked to a stitch target.
    claimed: set[tuple[str, int]] = set()

    def _is_claimed_pt(pts: list, idx: int) -> bool:
        px, py = float(pts[idx][0]), float(pts[idx][1])
        for cp0 in STITCH_CHECKPOINTS:
            if math.hypot(px - cp0.target[0], py - cp0.target[1]) <= claim_tol:
                return True
        return False

    for cp in STITCH_CHECKPOINTS:
        hints = route_hints.get(cp.name, ())
        candidates: list[str] = []
        if hints:
            for h in hints:
                if h in highways:
                    candidates.append(h)
            for key in highways:
                if key in candidates:
                    continue
                if any(key == h or key.startswith(h + "_") for h in hints):
                    candidates.append(key)
        else:
            candidates = list(highways.keys())

        best_key = None
        best_i = -1
        best_d = float("inf")
        for key in candidates:
            entry = highways[key]
            pts = entry.get("points") if isinstance(entry, dict) else entry
            if not pts:
                continue
            i = _nearest_vertex(pts, cp.target)
            d = math.hypot(float(pts[i][0]) - cp.target[0], float(pts[i][1]) - cp.target[1])
            if d < best_d:
                best_d = d
                best_key = key
                best_i = i

        if best_key is None:
            residuals[cp.name] = float("inf")
            continue

        entry = highways[best_key]
        pts = entry["points"] if isinstance(entry, dict) else entry
        rx, ry = round_xy(cp.target[0], cp.target[1])

        # Already on target.
        if best_d <= claim_tol:
            claimed.add((best_key, best_i))
            residuals[cp.name] = 0.0
            continue

        can_overwrite = (
            best_d <= search_radius
            and (best_key, best_i) not in claimed
            and not _is_claimed_pt(pts, best_i)
        )
        if can_overwrite:
            pts[best_i] = [rx, ry]
            claimed.add((best_key, best_i))
        else:
            # Dedicated abutment — keep dual bridge ends from clobbering each other.
            insert_at = best_i + 1 if best_d <= search_radius else len(pts)
            pts.insert(insert_at, [rx, ry])
            # Shift claimed indices on this route after insertion.
            claimed = {
                (k, i + 1 if k == best_key and i >= insert_at else i)
                for k, i in claimed
            }
            claimed.add((best_key, insert_at))
        residuals[cp.name] = 0.0
    return residuals


def georeference_highways(highways: dict) -> dict[str, Rigid2D]:
    """Apply per-city pure translations, then snap bridge stitch checkpoints.

    Mutates ``highways`` in place. Returns the transform used per city key.
    North stays +Y and east stays +X (no rotation / setH = 0).
    """
    xforms = transforms_by_city()
    # Shared corridors: transform each vertex with the plate whose region
    # owns it; exclusive city routes get a single downtown translation.
    exclusive: dict[str, list[str]] = {k: [] for k in xforms}
    shared: list[str] = []
    for key in list(highways.keys()):
        city = classify_route(key)
        if city == "shared":
            shared.append(key)
        else:
            exclusive.setdefault(city, []).append(key)

    for city, keys in exclusive.items():
        xf = xforms.get(city) or Rigid2D.identity()
        if xf.cos == 1.0 and xf.sin == 0.0 and abs(xf.tx) < 1e-12 and abs(xf.ty) < 1e-12:
            continue
        for key in keys:
            entry = highways[key]
            if isinstance(entry, dict):
                entry["points"] = _xform_points(entry["points"], xf)
            else:
                highways[key] = _xform_points(entry, xf)

    # Shared corridors: transform each vertex with the plate whose post-image
    # abutment is nearest (approx: use pre-image city ownership by X bands).
    for key in shared:
        entry = highways[key]
        pts = entry["points"] if isinstance(entry, dict) else entry
        new_pts: list[list[float]] = []
        for p in pts:
            x, y = float(p[0]), float(p[1])
            xf = _shared_vertex_xform(x, y, xforms)
            rx, ry = round_xy(*xf.apply(x, y))
            new_pts.append([rx, ry])
        if isinstance(entry, dict):
            entry["points"] = new_pts
        else:
            highways[key] = new_pts

    snap_checkpoints_to_routes(highways)
    return xforms


def _shared_vertex_xform(x: float, y: float, xforms: dict[str, Rigid2D]) -> Rigid2D:
    """Pick a city transform for a shared-corridor vertex by rough region."""
    # North of Burrard
    if y > 300:
        return xforms.get("north_vancouver", Rigid2D.identity())
    # Vancouver / Burnaby band
    if y > 80 and x < -50:
        if x > -200:
            return xforms.get("burnaby", Rigid2D.identity())
        return xforms.get("vancouver", Rigid2D.identity())
    # Richmond Lulu / Sea Island
    if -130 < y < 80 and x < -150:
        return xforms.get("richmond", Rigid2D.identity())
    # Delta
    if y < -20 and x < -80:
        return xforms.get("delta", Rigid2D.identity())
    # Pitt / PoCo / MR north of Fraser east
    if y > 40 and x > 150:
        if x < 280:
            return xforms.get("pitt_meadows", Rigid2D.identity())
        return xforms.get("maple_ridge", Rigid2D.identity())
    # New West / Coquitlam
    if 40 < y < 120 and -60 < x < 100:
        if x < 30:
            return xforms.get("new_westminster", Rigid2D.identity())
        return xforms.get("coquitlam", Rigid2D.identity())
    return Rigid2D.identity()


def georeference_ring(
    ring: Sequence[tuple[float, float]],
    city_key: str,
    xforms: dict[str, Rigid2D] | None = None,
) -> tuple[tuple[float, float], ...]:
    xforms = xforms or transforms_by_city()
    xf = xforms.get(city_key, Rigid2D.identity())
    return tuple(round_xy(*xf.apply(p[0], p[1])) for p in ring)


def georeference_bbox(
    bbox: tuple[float, float, float, float],
    city_key: str,
    xforms: dict[str, Rigid2D] | None = None,
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    pts = georeference_ring(corners, city_key, xforms)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def district_city_key(district_key: str) -> str:
    for plate in CITY_PLATES:
        if district_key in plate.district_keys:
            return plate.key
    # Heuristic fallbacks
    if district_key.startswith(("lg_", "langley")):
        return "langley"
    return "surrey"


def apply_district_transforms(district_defs: dict, xforms: dict[str, Rigid2D] | None = None) -> dict:
    """Return a shallow-copied district map with georeferenced rings/bboxes."""
    xforms = xforms or transforms_by_city()
    out: dict = {}
    for key, spec in district_defs.items():
        city = district_city_key(key)
        xf = xforms.get(city, Rigid2D.identity())
        if xf.cos == 1.0 and xf.sin == 0.0 and abs(xf.tx) < 1e-12 and abs(xf.ty) < 1e-12:
            out[key] = spec
            continue
        new_spec = dict(spec)
        if "ring" in spec:
            new_spec["ring"] = georeference_ring(spec["ring"], city, xforms)
        if "bbox" in spec and spec["bbox"] is not None:
            new_spec["bbox"] = georeference_bbox(spec["bbox"], city, xforms)
        out[key] = new_spec
    return out


def stitch_report(highways: dict, *, tol: float = 1.0) -> list[str]:
    """Human-readable distances from each checkpoint to nearest highway vertex."""
    lines: list[str] = []
    for cp in STITCH_CHECKPOINTS:
        best_d = float("inf")
        best_key = "?"
        for key, entry in highways.items():
            pts = entry.get("points") if isinstance(entry, dict) else entry
            if not pts:
                continue
            i = _nearest_vertex(pts, cp.target)
            d = math.hypot(float(pts[i][0]) - cp.target[0], float(pts[i][1]) - cp.target[1])
            if d < best_d:
                best_d = d
                best_key = key
        ok = "OK" if best_d <= tol else "MISS"
        lines.append(f"{ok:4} {cp.name:40} d={best_d:6.2f}  via {best_key}")
    return lines


def calibration_banner() -> str:
    """Header comment block for generated city.yaml."""
    return (
        f"# Georeferenced Metro Vancouver 2× — WGS84 local projection.\n"
        f"# Origin (0,0): King George & 104 Ave  lat0={LAT0} lon0={LON0}\n"
        f"# Scale: 1 unit = {METERS_PER_UNIT} m  ({UNITS_PER_KM:.1f} units = 1 km)\n"
        f"# Pure north-up: X=(lon-lon0)*{X_PER_DEG:.1f}  Y=(lat-lat0)*{Y_PER_DEG:.1f}\n"
        f"# City plates: translate-only onto Google Maps centres (no rotation).\n"
        f"# Flat roads only Z=0 (+ hierarchy offsets {min(Z_LAYER.values())}–{max(Z_LAYER.values())}).\n"
        f"# Camera far clip: {CAMERA_FAR_CLIP:g}. World ≈ X∈[{WORLD_X_MIN:g},{WORLD_X_MAX:g}] "
        f"Y∈[{WORLD_Y_MIN:g},{WORLD_Y_MAX:g}].\n"
    )


if __name__ == "__main__":
    print(f"Scale lock: X_PER_DEG={X_PER_DEG:.1f}  Y_PER_DEG={Y_PER_DEG:.1f}")
    print("\nCity centre GPS → mandated (X, Y):")
    for key, xy, target, err in verify_city_centres():
        flag = "OK" if err <= 0.15 else "DIFF"
        print(
            f"  {flag:4} {key:20} proj=({xy[0]:8.1f},{xy[1]:8.1f})  "
            f"tgt=({target[0]:8.1f},{target[1]:8.1f})  err={err:6.2f}"
        )
    print("\nCity plate transforms (pure translation, rot must be 0°):")
    for k, xf in transforms_by_city().items():
        ang = math.degrees(math.atan2(xf.sin, xf.cos))
        print(f"  {k:20}  Δ=({xf.tx:+7.1f},{xf.ty:+7.1f})  rot={ang:+6.2f}°")
    print("\nBridge stitch abutments:")
    for cp in STITCH_CHECKPOINTS:
        print(f"  {cp.name:28}  ({cp.target[0]:+7.1f},{cp.target[1]:+7.1f})")
