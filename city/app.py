"""ShowBase app: assemble the city from CityPlan and run the viewer."""

from __future__ import annotations

import math
import random
import sys
from collections import defaultdict

from panda3d.core import (
    AmbientLight,
    CompassEffect,
    DirectionalLight,
    Filename,
    KeyboardButton,
    LineSegs,
    Point3,
    TextNode,
)
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase

from city.builders import SceneBuilders
from city.car import CarController, PlayerCar
from city.daycycle import SUNRISE_SECONDS, DayNightCycle
from city.materials import (
    BLOCK_SHADES,
    block_material,
    concrete_material,
    lawn_material,
    mark_material,
    road_material,
)
from city.mesh import (
    _dist2_point_segment,
    arterial_crossing_gaps,
    arterial_junctions,
    box_instance,
    make_highway_ribbon,
    make_sky_dome,
    offset_polyline,
    split_polyline_around_gaps,
    z_cylinder_instance,
)
from city.plan import default_city_plan
from city.signals import TrafficLightController

# Readable names for arterial YAML keys (world-space map labels).
HIGHWAY_LABELS = {
    "hwy17": "Hwy 17",
    "hwy17a": "Hwy 17A",
    "hwy1": "Hwy 1",
    "fraser": "Fraser Hwy",
    "hwy15": "Hwy 15",
    "hwy10": "88 Ave",
    "hwy99": "Hwy 99",
    "hwy91": "Hwy 91",
    "hwy8": "Hwy 10",
    "ladner_trunk": "Ladner Trunk Road",
    "no_2_rd": "No. 2 Rd",
    "no_3_rd": "No. 3 Rd",
    "no_4_rd": "No. 4 Rd",
    "steveston_hwy": "Steveston Hwy",
    "williams_rd": "Williams Rd",
    "francis_rd": "Francis Rd",
    "blundell_rd": "Blundell Rd",
    "bridgeport_rd": "Bridgeport Rd",
    "no_1_rd": "No. 1 Rd",
    "westminster_hwy": "Westminster Hwy",
    "oak_st": "Oak St",
    "granville_st": "Granville St",
    "cambie_st": "Cambie St",
    "main_st": "Main St",
    "fraser_st": "Fraser St",
    "knight_st": "Knight St",
    "boundary_rd": "Boundary Rd",
    "sw_marine": "SW Marine Drive",
    "ave_49": "49th Ave",
    "ave_41": "41st Ave",
    "king_edward": "King Edward Blvd",
    "broadway": "Broadway",
    "burrard_st": "Burrard St",
    "georgia_st": "Georgia St",
    "davie_st": "Davie St",
    "hastings_st": "Hastings St",
    "kingsway": "Kingsway",
    "king_george": "King George Blvd",
    "scott_120": "120 St",
    "st_120_s": "120 St",
    "st_56": "56 St",
    "ave_72": "72 Ave",
    "ave_96": "96 Ave",
    "ave_102": "102 Ave",
    "ave_102_e": "102 Ave",
    "ave_108": "108 Ave",
    "ave_114": "114 Ave",
    "ave_58": "58 Ave",
    "ave_28": "28 Ave",
    "ave_16": "16 Ave",
    "ave_0": "0 Ave",
    "ave_0_delta": "0 Ave",
    "whalley_blvd": "Whalley Blvd",
    "university_dr": "University Dr",
    "marine_dr": "Marine Dr",
    "st_128": "128 St",
    "st_136": "136 St",
    "st_140": "140 St",
    "st_152": "152 St",
    "st_196": "196 St",
    "st_200": "200 St",
    "st_208": "208 St",
    "st_224": "224 St",
    "st_248": "248 St",
    "st_260": "260 St",
    "st_276": "276 St",
}

# Thin side fences: provincial highways plus Fraser, 88 Ave, and King George.
SIDE_BORDER_ROUTES = frozenset(
    {
        "hwy17",
        "hwy17a",
        "hwy1",
        "fraser",
        "hwy15",
        "hwy99",
        "hwy91",
        "hwy8",
        "hwy10",
        "king_george",
    }
)

# Spatial hash cell size for barrier / road lookups (car-mode hot path).
_SEG_CELL = 10.0
# Barrier prism length target — dense Chaikin samples are ~1.25; coarsen for FPS.
_BARRIER_SPAN = 4.5
# Drop leftover stubs between nearby crossings (e.g. Fraser × 58 Ave near 224 St).
_BARRIER_MIN_RUN = 16.0

# Car-mode HUD: neighborhood → (area label, municipality). Checked in order.
_LOCATION_AREAS: tuple[tuple[str, str, str], ...] = (
    ("city_centre", "Surrey City Centre", "Surrey"),
    ("white_rock_centre", "White Rock Centre", "White Rock"),
    ("langley_city", "Langley City", "Langley"),
    ("whalley", "Whalley", "Surrey"),
    ("newton", "Newton", "Surrey"),
    ("guildford", "Guildford", "Surrey"),
    ("fleetwood", "Fleetwood", "Surrey"),
    ("cloverdale", "Cloverdale", "Surrey"),
    ("south_surrey", "South Surrey", "Surrey"),
    ("north_delta", "North Delta", "Delta"),
    ("ladner", "Ladner", "Delta"),
    ("tsawwassen", "Tsawwassen", "Delta"),
    ("bridgeport", "Bridgeport", "Richmond"),
    ("seaforth", "Seaforth", "Richmond"),
    ("steveston", "Steveston", "Richmond"),
    ("brighouse", "Brighouse", "Richmond"),
    ("cambie", "Cambie", "Richmond"),
    ("broadmoor", "Broadmoor", "Richmond"),
    ("east_richmond", "East Richmond", "Richmond"),
    ("downtown_vancouver", "Downtown Vancouver", "Vancouver"),
    ("vancouver", "Vancouver", "Vancouver"),
    ("port_kells", "Port Kells", "Langley"),
    ("walnut_grove", "Walnut Grove", "Langley"),
    ("fort_langley", "Fort Langley", "Langley"),
    ("east_clayton", "East Clayton", "Langley"),
    ("willoughby", "Willoughby", "Langley"),
    ("hopington", "Hopington", "Langley"),
    ("fern_ridge", "Fern Ridge", "Langley"),
    ("brookswood", "Brookswood", "Langley"),
    ("campbell_valley", "Campbell Valley", "Langley"),
)


class CityApp(ShowBase):
    def __init__(self, screenshot: str | None = None) -> None:
        super().__init__()
        self.screenshot_path = screenshot
        self.disableMouse()
        self.setBackgroundColor(0.7, 0.78, 0.88, 1)

        plan = default_city_plan()
        self.plan = plan
        self.city = self.render.attachNewNode("city")
        block_size = plan.block_size

        for hood in plan.neighborhoods:
            node = self.city.attachNewNode(f"hood-{hood.name}")
            node.setPos(hood.origin_x, hood.origin_y, 0.0)
            node.setH(hood.heading_deg)
            builders = SceneBuilders(node, plan, self.render)
            for kind, lot in plan.iter_neighborhood_lots(hood):
                if kind == "tower":
                    heights = random.sample(
                        range(plan.floor_min, plan.floor_max + 1),
                        plan.towers_per_ring,
                    )
                    block_floors = (tuple(heights[:5]), (), (), tuple(heights[5:]))
                    builders._add_city_block(
                        lot.west_face,
                        block_size,
                        block_floors,
                        y_offset=lot.y_offset,
                        eastern_road=lot.eastern_road,
                        southern_road=lot.southern_road,
                        factory=False,
                    )
                elif kind == "factory":
                    builders._add_city_block(
                        lot.west_face,
                        block_size,
                        ((), (), (), ()),
                        y_offset=lot.y_offset,
                        eastern_road=lot.eastern_road,
                        southern_road=lot.southern_road,
                        factory=True,
                    )
                else:
                    builders._add_housing_lot(
                        lot.west_face,
                        block_size,
                        lot.lot_width,
                        lot.lot_depth,
                        y_offset=lot.y_offset,
                        eastern_road=lot.eastern_road,
                        southern_road=lot.southern_road,
                        northern_road=lot.northern_road,
                        houses_across=lot.houses_across,
                        houses_deep=lot.houses_deep,
                    )

        # Demo house on the NE plate; skyscrapers stay in the circled Whalley blocks.
        ne = SceneBuilders(self.city, plan, self.render)
        ne._add_house(560.0, 400.0, brick=0.68, chimney=True)
        hwy = plan.highway_geometry()
        lane_width = hwy["lane_width"]
        highway_width = hwy["highway_width"]
        road_z = hwy["road_z"]
        road_thickness = hwy["road_thickness"]
        arterials = list(hwy["arterials"])

        # Road corridors for tower sight checks: (ax, ay, bx, by, half_width).
        road_segs: list[tuple[float, float, float, float, float]] = []
        for route in arterials:
            pts = list(route.get("control_points") or route.get("points") or ())
            half_w = float(route.get("width") or 0.0) * 0.5
            for i in range(len(pts) - 1):
                road_segs.append(
                    (pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], half_w)
                )

        def _tower_sees_road(
            tx: float,
            ty: float,
            half: float,
            others: list[tuple[float, float]],
            *,
            max_dist: float = 48.0,
            step: float = 0.7,
        ) -> bool:
            """True if a cardinal ray hits pavement before another tower."""
            for dx, dy in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)):
                dist = half + 0.05
                while dist < max_dist:
                    px = tx + dx * dist
                    py = ty + dy * dist
                    blocked = False
                    for ox, oy in others:
                        if abs(px - ox) <= half and abs(py - oy) <= half:
                            blocked = True
                            break
                    if blocked:
                        break
                    for ax, ay, bx, by, hw in road_segs:
                        d2, _qx, _qy = _dist2_point_segment(px, py, ax, ay, bx, by)
                        if d2 <= hw * hw:
                            return True
                    dist += step
            return False

        # City Centre: circled blocks packed with towers, split around 102 Ave.
        # Each tuple is (west, east, south, north) inset from the arterials.
        self.city_centre_blocks = (
            (92.0, 113.0, 184.0, 204.0),   # 128–Uni, 96–102
            (127.0, 148.0, 184.0, 204.0),  # Uni–KG, 96–102
            (162.0, 180.0, 184.0, 204.0),  # KG–Whalley, 96–102
            (194.0, 211.0, 184.0, 204.0),  # Whalley–140, 96–102
            (92.0, 113.0, 216.0, 236.0),   # 128–Uni, 102–108
            (127.0, 148.0, 216.0, 236.0),  # Uni–KG, 102–108
            (162.0, 180.0, 216.0, 236.0),  # KG–Whalley, 102–108
            (194.0, 211.0, 216.0, 236.0),  # Whalley–140, 102–108
            (162.0, 180.0, 253.0, 282.0),  # KG–Whalley, above 108
            (194.0, 211.0, 253.0, 282.0),  # Whalley–140, above 108
        )
        self.city_centre = self.city.attachNewNode("city-centre")
        cc = SceneBuilders(self.city_centre, plan, self.render)
        # Dark grey lot pads under the tower blocks (above the lawn).
        pad_mat = concrete_material(0.32)
        pad_thickness = 0.14
        for west, east, south, north in self.city_centre_blocks:
            pad = box_instance(
                self.city_centre,
                east - west,
                north - south,
                pad_thickness,
            )
            pad.setPos(
                (west + east) * 0.5,
                (south + north) * 0.5,
                road_z - 0.02,
            )
            pad.setMaterial(pad_mat, 1)

        footprints = ("rect", "round", "tri")
        tower_pitch = block_size[0] + plan.tower_gap + 0.6
        tower_half = block_size[0] * 0.5
        floor_hi = plan.floor_max + 6
        candidates: list[tuple[float, float, int, str, float, int]] = []
        for west, east, south, north in self.city_centre_blocks:
            cols = max(2, min(3, int((east - west) / tower_pitch)))
            rows = max(2, min(4, int((north - south) / tower_pitch)))
            for row in range(rows):
                for col in range(cols):
                    x = west + (col + 0.5) * (east - west) / cols
                    y = south + (row + 0.5) * (north - south) / rows
                    seed = abs(int(x * 17 + y * 31))
                    x += ((seed % 7) - 3) * 0.12
                    y += ((seed % 5) - 2) * 0.12
                    # Medium or tall only — no short stacks.
                    mid_lo = max(plan.floor_min, 14)
                    mid_hi = max(mid_lo + 4, plan.floor_max - 2)
                    tall_lo = mid_hi + 1
                    tall_hi = floor_hi
                    roll = (seed * 13 + seed // 5) % 100
                    if roll < 40:
                        span = max(1, tall_hi - tall_lo + 1)
                        floors = tall_lo + ((seed * 7) % span)
                    else:
                        span = max(1, mid_hi - mid_lo + 1)
                        floors = mid_lo + ((seed * 11) % span)
                    footprint = footprints[seed % 3]
                    heading = (seed % 9 - 4) * 5.0 if footprint == "tri" else 0.0
                    candidates.append((x, y, floors, footprint, heading, seed))

        # Drop towers with no clear cardinal sightline to a road.
        kept: list[tuple[float, float, int, str, float, int]] = []
        for x, y, floors, footprint, heading, seed in candidates:
            others = [(ox, oy) for ox, oy, *_rest in candidates if ox != x or oy != y]
            if _tower_sees_road(x, y, tower_half, others):
                kept.append((x, y, floors, footprint, heading, seed))
        for x, y, floors, footprint, heading, seed in kept:
            cc._add_stack(
                x,
                y,
                floors,
                block_size,
                block_material(BLOCK_SHADES[seed % len(BLOCK_SHADES)]),
                footprint=footprint,
                heading=heading,
                doors=("-y",),
            )

        self._ground_z = road_z
        outline_z = road_z + road_thickness / 2 + 0.03
        # District rings follow arterial centrelines (click → outline + title).
        # Outer boundary arterials use the outer curb so the full ribbon is inside:
        # 0 Ave south -482, 102 Ave north 212.5, 276 St east 1255, Marine Dr SW +5,
        # 120 St (28–Marine) west 21, Hwy 99 (Hwy 17–120) south -167.5,
        # Hwy 15 (Hwy 17–102) east 487.5.
        self._districts: dict[str, dict] = {
            "city_centre": {
                "title": "Surrey City Centre",
                # 128 St → 96 Ave → 140 St → 114 Ave → King George → 108 Ave.
                "ring": (
                    (85.0, 175.0),
                    (218.0, 175.0),
                    (218.0, 290.0),
                    (155.0, 290.0),
                    (155.0, 245.0),
                    (85.0, 245.0),
                ),
                "bright": self.city_centre,
            },
            "whalley": {
                "title": "Whalley",
                # 120 St → 88 Ave → 152 St → Hwy 1 → Hwy 17 (both sides) → 96 Ave;
                # City Centre notched.
                "ring": (
                    (18.0, 78.0),
                    (285.0, 78.0),
                    (285.0, 175.0),
                    (218.0, 175.0),
                    (218.0, 290.0),
                    (155.0, 290.0),
                    (155.0, 245.0),
                    (85.0, 245.0),
                    (85.0, 175.0),
                    (218.0, 175.0),
                    (285.0, 175.0),
                    (285.0, 234.0),
                    (280.0, 236.0),
                    (266.0, 263.0),
                    (247.0, 319.0),
                    (215.0, 357.0),
                    (176.0, 387.2),
                    (176.0, 397.0),
                    (138.2, 394.9),
                    (77.2, 383.7),
                    (19.9, 365.9),
                    (-28.5, 333.5),
                    (-60.7, 285.4),
                    (-79.6, 233.1),
                    (-89.8, 177.4),
                    (-90.0, 175.0),
                    (14.0, 175.0),
                    (16.0, 120.0),
                ),
                "bright": None,
            },
            "north_delta": {
                "title": "North Delta",
                # West of 120 St to Hwy 17 (Hwy 10 / Hwy 99 junction), Hwy 99 south curb.
                "ring": (
                    (14.0, 175.0),
                    (-90.0, 175.0),
                    (-101.8, 122.4),
                    (-116.8, 42.1),
                    (-131.9, -48.6),
                    (-190.0, -50.0),
                    (-190.0, -167.5),
                    (26.0, -167.5),
                    (24.0, -70.0),
                    (22.0, -20.0),
                    (20.0, 30.0),
                    (18.0, 78.0),
                    (16.0, 120.0),
                ),
                "bright": None,
            },
            "ladner": {
                "title": "Ladner",
                # Hwy 99 → Ladner Trunk → Hwy 17 west arm → back.
                "ring": (
                    (-520.0, -160.0),
                    (-350.0, -160.0),
                    (-270.0, -160.0),
                    (-190.0, -160.0),
                    (-190.0, -190.0),
                    (-220.0, -260.0),
                    (-270.0, -310.0),
                    (-350.0, -320.0),
                    (-520.0, -320.0),
                ),
                "bright": None,
            },
            "tsawwassen": {
                "title": "Tsawwassen",
                # South of Hwy 17 → 56 St / 17A → 0 Ave (south curb, both lanes).
                "ring": (
                    (-520.0, -320.0),
                    (-350.0, -320.0),
                    (-270.0, -310.0),
                    (-260.0, -482.0),
                    (-420.0, -482.0),
                ),
                "bright": None,
            },
            "bridgeport": {
                "title": "Bridgeport",
                # Purple: north of Bridgeport Rd (YVR not included); Hwy 99 leaves
                # at Bridgeport toward Granville and is not part of this ring.
                "ring": (
                    (-1050.0, 550.0),
                    (-620.0, 550.0),
                    (-620.0, 700.0),
                    (-1050.0, 700.0),
                ),
                "bright": None,
            },
            "seaforth": {
                "title": "Seaforth",
                # Green: No. 1 → No. 2, Bridgeport → Francis.
                "ring": (
                    (-915.0, 550.0),
                    (-817.0, 550.0),
                    (-817.0, 215.0),
                    (-915.0, 215.0),
                ),
                "bright": None,
            },
            "steveston": {
                "title": "Steveston",
                # Blue: No. 1 → No. 2, Francis → Steveston Hwy.
                "ring": (
                    (-915.0, 215.0),
                    (-817.0, 215.0),
                    (-817.0, 75.0),
                    (-915.0, 75.0),
                ),
                "bright": None,
            },
            "brighouse": {
                "title": "Brighouse",
                # Red: No. 2 → No. 3, Bridgeport → Francis.
                "ring": (
                    (-817.0, 550.0),
                    (-718.0, 550.0),
                    (-718.0, 215.0),
                    (-817.0, 215.0),
                ),
                "bright": None,
            },
            "cambie": {
                "title": "Cambie",
                # Orange: No. 3 → Hwy 99, Bridgeport → Francis (covers Blundell strip).
                "ring": (
                    (-718.0, 550.0),
                    (-620.0, 550.0),
                    (-620.0, 215.0),
                    (-718.0, 215.0),
                ),
                "bright": None,
            },
            "broadmoor": {
                "title": "Broadmoor",
                # Brown: No. 2 → Hwy 99, Francis → Steveston Hwy.
                "ring": (
                    (-817.0, 215.0),
                    (-620.0, 215.0),
                    (-620.0, 75.0),
                    (-817.0, 75.0),
                ),
                "bright": None,
            },
            "east_richmond": {
                "title": "East Richmond",
                # Yellow: Hwy 99 → No. 4, Bridgeport → Steveston Hwy.
                "ring": (
                    (-620.0, 550.0),
                    (-522.0, 550.0),
                    (-480.0, 550.0),
                    (-480.0, 75.0),
                    (-522.0, 75.0),
                    (-620.0, 75.0),
                ),
                "bright": None,
            },
            "newton": {
                "title": "Newton",
                # 88 Ave → 152 St → Hwy 99 (follow to 152 St) → 120 St.
                "ring": (
                    (18.0, 78.0),
                    (285.0, 78.0),
                    (285.0, -260.0),
                    (280.0, -255.0),
                    (220.0, -205.0),
                    (160.0, -165.0),
                    (100.0, -160.0),
                    (40.0, -160.0),
                    (26.0, -167.5),
                    (24.0, -70.0),
                    (22.0, -20.0),
                    (20.0, 30.0),
                ),
                "bright": None,
            },
            "guildford": {
                "title": "Guildford",
                # 152 St / 96 Ave → Hwy 15 (east curb Hwy 17–102) → Hwy 17 (both sides) → Hwy 1.
                "ring": (
                    (285.0, 175.0),
                    (480.0, 175.0),
                    (480.0, 180.0),
                    (480.0, 210.0),
                    (487.5, 210.0),
                    (487.5, 300.0),
                    (487.5, 366.0),
                    (482.4, 377.8),
                    (462.4, 381.8),
                    (402.0, 393.8),
                    (341.0, 402.0),
                    (270.0, 405.0),
                    (199.1, 402.0),
                    (176.0, 397.0),
                    (176.0, 387.2),
                    (215.0, 357.0),
                    (247.0, 319.0),
                    (266.0, 263.0),
                    (280.0, 236.0),
                    (285.0, 234.0),
                ),
                "bright": None,
            },
            "fleetwood": {
                "title": "Fleetwood",
                # 152 St → 96 Ave → Hwy 15 → Hwy 10.
                "ring": (
                    (285.0, 175.0),
                    (480.0, 175.0),
                    (480.0, -35.0),
                    (285.0, -35.0),
                ),
                "bright": None,
            },
            "cloverdale": {
                "title": "Cloverdale",
                # Hwy 15 → Hwy 1 (angled NE tip) → 196 St → 28 Ave → Hwy 99 → 152 St → Hwy 10.
                "ring": (
                    (480.0, 175.0),
                    (480.0, 190.0),
                    (520.0, 180.0),
                    (580.0, 168.0),
                    (610.0, 160.0),
                    (610.0, -320.0),
                    (350.0, -320.0),
                    (280.0, -255.0),
                    (285.0, -260.0),
                    (285.0, -35.0),
                    (480.0, -35.0),
                ),
                "bright": None,
            },
            "white_rock_centre": {
                "title": "White Rock Centre",
                # 16 Ave → King George → 0 Ave (south curb) → 136 St (carved from South Surrey).
                "ring": (
                    (174.0, -400.0),
                    (401.0, -400.0),
                    (482.0, -482.0),
                    (174.0, -482.0),
                ),
                "bright": None,
            },
            "south_surrey": {
                "title": "South Surrey",
                # Hwy 99 north → 28 Ave to 196 St → 0 Ave (south curb) with White Rock Centre
                # notched out → Marine Dr (SW curb) → 120 St (west curb 28–Marine).
                "ring": (
                    (26.0, -167.5),
                    (100.0, -160.0),
                    (160.0, -165.0),
                    (220.0, -205.0),
                    (280.0, -255.0),
                    (350.0, -320.0),
                    (480.0, -320.0),
                    (610.0, -320.0),
                    (610.0, -400.0),
                    (610.0, -482.0),
                    (517.0, -482.0),
                    (482.0, -482.0),
                    (401.0, -400.0),
                    (174.0, -400.0),
                    (174.0, -482.0),
                    (173.4, -490.0),
                    (118.9, -482.9),
                    (78.0, -469.6),
                    (41.7, -448.8),
                    (21.0, -422.0),
                    (21.0, -400.0),
                    (21.0, -320.0),
                    (26.0, -320.0),
                ),
                "bright": None,
            },
            "port_kells": {
                "title": "Port Kells",
                # 196 St → 102 Ave (north curb) → 208 St → 88 Ave.
                "ring": (
                    (610.0, 212.5),
                    (642.0, 212.5),
                    (706.0, 212.5),
                    (706.0, 78.0),
                    (642.0, 78.0),
                    (610.0, 78.0),
                ),
                "bright": None,
            },
            "walnut_grove": {
                "title": "Walnut Grove",
                # 208 St → 102 Ave (north curb) → 248 St → 88 Ave.
                "ring": (
                    (706.0, 212.5),
                    (834.0, 212.5),
                    (1026.0, 212.5),
                    (1026.0, 78.0),
                    (834.0, 78.0),
                    (706.0, 78.0),
                ),
                "bright": None,
            },
            "fort_langley": {
                "title": "Fort Langley",
                # 248 St → 102 Ave (north curb) → 276 St (east curb) → 88 Ave.
                "ring": (
                    (1026.0, 212.5),
                    (1122.0, 212.5),
                    (1255.0, 212.5),
                    (1255.0, 78.0),
                    (1122.0, 78.0),
                    (1026.0, 78.0),
                ),
                "bright": None,
            },
            "east_clayton": {
                "title": "East Clayton",
                # 196 St → 88 Ave → 208 St → Fraser Hwy.
                "ring": (
                    (610.0, 78.0),
                    (642.0, 78.0),
                    (706.0, 78.0),
                    (706.0, -51.0),
                    (642.0, -29.0),
                    (610.0, -18.0),
                ),
                "bright": None,
            },
            "willoughby": {
                "title": "Willoughby/Willowbrook",
                # 208 St → 88 Ave → 248 St → Fraser Hwy.
                "ring": (
                    (706.0, 78.0),
                    (834.0, 78.0),
                    (1026.0, 78.0),
                    (1026.0, -158.0),
                    (834.0, -93.0),
                    (720.0, -55.0),
                    (706.0, -51.0),
                ),
                "bright": None,
            },
            "langley_city": {
                "title": "Langley City",
                # 196 St → Fraser Hwy → 208 St → 58 Ave.
                "ring": (
                    (610.0, -18.0),
                    (642.0, -29.0),
                    (706.0, -51.0),
                    (706.0, -110.0),
                    (610.0, -110.0),
                ),
                "bright": None,
            },
            "hopington": {
                "title": "Hopington",
                # 248 St → 88 Ave → 276 St (east curb) → Fraser Hwy.
                "ring": (
                    (1026.0, 78.0),
                    (1122.0, 78.0),
                    (1255.0, 78.0),
                    (1255.0, -233.0),
                    (1122.0, -190.0),
                    (1026.0, -158.0),
                ),
                "bright": None,
            },
            "fern_ridge": {
                "title": "Fern Ridge",
                # 196 St → 58 Ave → 208 St → 0 Ave (south curb).
                "ring": (
                    (610.0, -110.0),
                    (706.0, -110.0),
                    (706.0, -482.0),
                    (610.0, -482.0),
                ),
                "bright": None,
            },
            "brookswood": {
                "title": "Brookswood",
                # 208 St → Fraser Hwy → 224 St → 0 Ave (south curb).
                "ring": (
                    (706.0, -51.0),
                    (720.0, -55.0),
                    (834.0, -93.0),
                    (834.0, -482.0),
                    (706.0, -482.0),
                ),
                "bright": None,
            },
            "campbell_valley": {
                "title": "Campbell Valley",
                # 224 St → Fraser Hwy → 276 St (east curb) → 0 Ave (south curb).
                "ring": (
                    (834.0, -93.0),
                    (1026.0, -158.0),
                    (1122.0, -190.0),
                    (1255.0, -233.0),
                    (1255.0, -482.0),
                    (834.0, -482.0),
                ),
                "bright": None,
            },
            "district_of_langley": {
                "title": "District of Langley",
                # All Langley districts except Langley City (notched via 58 Ave / 208 St / Fraser).
                "ring": (
                    (610.0, 212.5),
                    (642.0, 212.5),
                    (706.0, 212.5),
                    (834.0, 212.5),
                    (1026.0, 212.5),
                    (1122.0, 212.5),
                    (1255.0, 212.5),
                    (1255.0, 78.0),
                    (1255.0, -233.0),
                    (1255.0, -482.0),
                    (1122.0, -482.0),
                    (1026.0, -482.0),
                    (834.0, -482.0),
                    (706.0, -482.0),
                    (610.0, -482.0),
                    (610.0, -110.0),
                    (706.0, -110.0),
                    (706.0, -51.0),
                    (642.0, -29.0),
                    (610.0, -18.0),
                    (610.0, 78.0),
                    (610.0, 212.5),
                ),
                "bright": None,
                "hotkey_only": True,
            },
            "delta": {
                "title": "Delta",
                # Outer outline of North Delta + Ladner + Tsawwassen.
                "ring": (
                    (14.0, 175.0),
                    (-90.0, 175.0),
                    (-101.8, 122.4),
                    (-116.8, 42.1),
                    (-131.9, -48.6),
                    (-190.0, -50.0),
                    (-620.0, 75.0),
                    (-560.0, -40.0),
                    (-480.0, -100.0),
                    (-400.0, -140.0),
                    (-350.0, -160.0),
                    (-520.0, -160.0),
                    (-520.0, -320.0),
                    (-420.0, -482.0),
                    (-260.0, -482.0),
                    (-270.0, -310.0),
                    (-220.0, -260.0),
                    (-190.0, -190.0),
                    (-190.0, -167.5),
                    (26.0, -167.5),
                    (24.0, -70.0),
                    (22.0, -20.0),
                    (20.0, 30.0),
                    (18.0, 78.0),
                    (16.0, 120.0),
                ),
                "bright": None,
                "hotkey_only": True,
            },
            "richmond": {
                "title": "Richmond",
                # Outer outline of Bridgeport + Seaforth + Steveston + Brighouse +
                # Cambie + Broadmoor + East Richmond. Sea Island / YVR excluded.
                # Hwy 99 bridge to Granville leaves at Bridgeport (not in ring).
                "ring": (
                    (-915.0, 75.0),
                    (-480.0, 75.0),
                    (-480.0, 550.0),
                    (-620.0, 550.0),
                    (-620.0, 700.0),
                    (-1050.0, 700.0),
                    (-1050.0, 550.0),
                    (-915.0, 550.0),
                ),
                "bright": None,
                "hotkey_only": True,
            },
            "downtown_vancouver": {
                "title": "Downtown Vancouver",
                # Peninsula north of Broadway: Burrard/Granville/Main/Cambie
                # bends + Georgia/Davie diagonals + Hastings across the top.
                "ring": (
                    (-880.0, 1120.0),
                    (-420.0, 1120.0),
                    (-420.0, 1280.0),
                    (-880.0, 1280.0),
                ),
                "bright": None,
            },
            "vancouver": {
                "title": "Vancouver",
                # City proper: SW Marine → Boundary → Burrard waterfront → west tip.
                # UBC / Endowment Lands excluded (west of x=-920).
                # Sub-area: Downtown Vancouver (clickable).
                "ring": (
                    (-920.0, 820.0),
                    (-120.0, 820.0),
                    (-120.0, 1280.0),
                    (-920.0, 1280.0),
                ),
                "bright": None,
                "hotkey_only": True,
            },
            "surrey": {
                "title": "Surrey",
                # Outer outline of all districts except North Delta and White Rock Centre.
                "ring": (
                    (-78.0, 175.0),
                    (-68.0, 230.0),
                    (-50.0, 280.0),
                    (-20.0, 325.0),
                    (8.0, 350.0),
                    (25.0, 355.0),
                    (80.0, 372.0),
                    (140.0, 383.0),
                    (200.0, 390.0),
                    (270.0, 393.0),
                    (340.0, 390.0),
                    (400.0, 382.0),
                    (460.0, 370.0),
                    (487.5, 366.0),
                    (487.5, 210.0),
                    (480.0, 210.0),
                    (480.0, 190.0),
                    (520.0, 180.0),
                    (580.0, 168.0),
                    (610.0, 160.0),
                    (610.0, -320.0),
                    (610.0, -400.0),
                    (610.0, -482.0),
                    (517.0, -482.0),
                    (482.0, -482.0),
                    (401.0, -400.0),
                    (174.0, -400.0),
                    (174.0, -482.0),
                    (173.4, -490.0),
                    (118.9, -482.9),
                    (78.0, -469.6),
                    (41.7, -448.8),
                    (21.0, -422.0),
                    (21.0, -400.0),
                    (21.0, -320.0),
                    (26.0, -320.0),
                    (26.0, -167.5),
                    (24.0, -70.0),
                    (22.0, -20.0),
                    (20.0, 30.0),
                    (18.0, 78.0),
                    (16.0, 120.0),
                    (14.0, 175.0),
                ),
                "bright": None,
                "hotkey_only": True,
            },
        }
        for key, district in self._districts.items():
            outline = self._build_district_outline(key, district["ring"], outline_z)
            outline.hide()
            district["outline"] = outline
            district["label"] = None
            district["label_scale"] = 1.0
        self._selected_district: str | None = None
        # Keep legacy alias used by City Centre tower assembly comments/tests.
        self.city_centre_ring = self._districts["city_centre"]["ring"]

        self.highway = self.render.attachNewNode("highway")
        road_mat = road_material()
        mark_paint = mark_material()
        barrier_mat = concrete_material(0.75)

        def paint_route_marks(
            pts: list[tuple[float, float]],
            z_top: float,
            *,
            lanes: int,
            width: float,
            mark_gaps: list[tuple[float, float, float]],
        ) -> None:
            """Lane dashes that follow the smoothed centreline."""
            if len(pts) < 2 or lanes < 2:
                return
            # Longer dashes / gaps so the continuous ribbon still reads at overview.
            mark_len = 3.5
            mark_w = 0.35
            mark_h = 0.04
            mark_gap = 4.0
            period = mark_len + mark_gap
            centre_divider = lanes // 2
            dist = [0.0]
            for i in range(len(pts) - 1):
                dist.append(
                    dist[-1]
                    + math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                )
            total = dist[-1]
            if total < period:
                return

            def sample(s: float) -> tuple[float, float, float, float]:
                s = max(0.0, min(total, s))
                j = 0
                while j < len(dist) - 2 and dist[j + 1] < s:
                    j += 1
                span = dist[j + 1] - dist[j]
                t = 0.0 if span < 1e-9 else (s - dist[j]) / span
                x0, y0 = pts[j]
                x1, y1 = pts[j + 1]
                dx = x1 - x0
                dy = y1 - y0
                length = math.hypot(dx, dy) or 1.0
                return (x0 + dx * t, y0 + dy * t, dx / length, dy / length)

            def in_gap(x: float, y: float) -> bool:
                for gx, gy, radius in mark_gaps:
                    if radius <= 0.0:
                        continue
                    dx = x - gx
                    dy = y - gy
                    if dx * dx + dy * dy <= radius * radius:
                        return True
                return False

            s = mark_len * 0.5
            while s < total:
                x, y, ux, uy = sample(s)
                if not in_gap(x, y):
                    px, py = -uy, ux
                    heading = math.degrees(math.atan2(uy, ux))
                    for divider in range(1, lanes):
                        if divider == centre_divider:
                            continue
                        offset = -width / 2 + divider * lane_width
                        mark = box_instance(self.highway, mark_len, mark_w, mark_h)
                        mark.setPos(x + px * offset, y + py * offset, z_top + 0.02)
                        mark.setH(heading)
                        mark.setMaterial(mark_paint, 1)
                s += period

        road_top = road_z + road_thickness / 2
        self._highway_labels = self.render.attachNewNode("highway_labels")
        labels_root = self._highway_labels
        self._highway_label_nodes: list = []
        self._label_base_scale = max(36.0, highway_width * 2.8)
        self._label_ref_distance = 1.0
        # Barriers, side fences, and lane marks open at arterial crossings.
        crossing_gaps = arterial_crossing_gaps(arterials)
        # Named centreline segments for car-mode street HUD.
        self._named_roads: list[tuple[str, float, float, float, float, float]] = []
        # Solid median / edge walls for player-car collision: (ax,ay,bx,by,half_w).
        self._solid_barriers: list[tuple[float, float, float, float, float]] = []

        def _coarsen_polyline(points: list, max_span: float) -> list:
            """Keep endpoints; skip verts until arc length reaches max_span."""
            if len(points) < 2:
                return list(points)
            out = [points[0]]
            acc = 0.0
            for i in range(1, len(points)):
                dx = points[i][0] - points[i - 1][0]
                dy = points[i][1] - points[i - 1][1]
                acc += math.hypot(dx, dy)
                if acc >= max_span or i == len(points) - 1:
                    out.append(points[i])
                    acc = 0.0
            return out

        def _place_barrier_prisms(
            piece: list,
            width: float,
            height: float,
            z_center: float,
        ) -> None:
            """Rectangular prisms along a coarsened polyline (keeps collision cheap)."""
            if width <= 0.0 or height <= 0.0 or len(piece) < 2:
                return
            run = 0.0
            for i in range(1, len(piece)):
                run += math.hypot(
                    float(piece[i][0]) - float(piece[i - 1][0]),
                    float(piece[i][1]) - float(piece[i - 1][1]),
                )
            if run < _BARRIER_MIN_RUN:
                return
            half_w = width * 0.5
            pts = _coarsen_polyline(piece, _BARRIER_SPAN)
            for i in range(len(pts) - 1):
                x0 = float(pts[i][0])
                y0 = float(pts[i][1])
                x1 = float(pts[i + 1][0])
                y1 = float(pts[i + 1][1])
                dx = x1 - x0
                dy = y1 - y0
                length = math.hypot(dx, dy)
                if length < 0.05:
                    continue
                box = box_instance(self.highway, length, width, height)
                box.setPos((x0 + x1) * 0.5, (y0 + y1) * 0.5, z_center)
                box.setH(math.degrees(math.atan2(dy, dx)))
                box.setMaterial(barrier_mat, 1)
                self._solid_barriers.append((x0, y0, x1, y1, half_w))

        for arterial in arterials:
            pts = list(arterial["points"])
            if len(pts) < 2:
                continue
            route_lanes = int(arterial.get("lanes", plan.highway_lanes))
            route_width = float(arterial.get("width", highway_width))
            name = str(arterial.get("name", ""))
            # (x, y, clear_radius) — radius is angle-aware (shallow junctions open wider).
            median_gaps = list(crossing_gaps.get(name, []))
            # One continuous ribbon per route — smooth edges through bends.
            deck = self.highway.attachNewNode(
                make_highway_ribbon(pts, route_width, road_thickness)
            )
            deck.setPos(0.0, 0.0, road_z)
            deck.setMaterial(road_mat, 1)
            # Two-lane roads stay open — no median wall or edge fence.
            if route_lanes > 2:
                if plan.barrier_w > 0.0 and plan.barrier_h > 0.0:
                    for piece in split_polyline_around_gaps(pts, median_gaps):
                        _place_barrier_prisms(
                            piece,
                            plan.barrier_w,
                            plan.barrier_h,
                            road_top + plan.barrier_h / 2,
                        )
                if name in SIDE_BORDER_ROUTES and plan.fence_w > 0.0 and plan.fence_h > 0.0:
                    # Thin concrete lips along both pavement edges; gapped at crossings.
                    edge = route_width / 2 + plan.fence_w / 2
                    fence_gaps = [(x, y, radius + edge) for x, y, radius in median_gaps]
                    for side in (-1.0, 1.0):
                        edge_pts = offset_polyline(pts, side * edge)
                        for piece in split_polyline_around_gaps(edge_pts, fence_gaps):
                            _place_barrier_prisms(
                                piece,
                                plan.fence_w,
                                plan.fence_h,
                                road_top + plan.fence_h / 2,
                            )
            paint_route_marks(
                pts,
                road_top,
                lanes=route_lanes,
                width=route_width,
                mark_gaps=median_gaps,
            )

            title = HIGHWAY_LABELS.get(name, name.replace("_", " ").title())
            if title:
                half_w = route_width * 0.5
                # Coarser samples for HUD / on-road tests (full ribbon stays dense).
                road_pts = _coarsen_polyline(pts, 5.0)
                for i in range(len(road_pts) - 1):
                    self._named_roads.append(
                        (
                            title,
                            road_pts[i][0],
                            road_pts[i][1],
                            road_pts[i + 1][0],
                            road_pts[i + 1][1],
                            half_w,
                        )
                    )
            if not title:
                continue
            mid = pts[len(pts) // 2]
            text = TextNode(f"hwy-label-{name}")
            text.setText(title)
            text.setAlign(TextNode.ACenter)
            text.setTextColor(1.0, 1.0, 1.0, 1)
            text.setShadow(0.06, 0.06)
            text.setShadowColor(0.05, 0.06, 0.08, 0.9)
            # Pivot stays fixed in world space; only the text child is re-scaled.
            pivot = labels_root.attachNewNode(f"hwy-label-pivot-{name}")
            pivot.setPos(mid[0], mid[1], road_top + 4.0)
            label = pivot.attachNewNode(text)
            label.setScale(self._label_base_scale)
            label.setBillboardPointEye()
            label.setDepthTest(False)
            label.setDepthWrite(False)
            self._highway_label_nodes.append(label)

        # Spatial hashes — car mode used to scan tens of thousands of segs / frame.
        self._barrier_cell = _SEG_CELL
        self._road_cell = _SEG_CELL
        self._barrier_grid = self._build_segment_grid(
            self._solid_barriers, xy_offset=0, cell=self._barrier_cell
        )
        self._road_grid = self._build_segment_grid(
            self._named_roads, xy_offset=1, cell=self._road_cell
        )

        # Gantry signals on 3-/4-way arterial junctions (never on Hwy 1).
        # Two curb posts per approach, joined by a full crossbar. Shared lens
        # materials still animate after flattenStrong.
        self._signals = None
        self._signals_root = self.city.attachNewNode("traffic-signals")
        signal_builders = SceneBuilders(self._signals_root, plan, self.render)
        signal_count = 0
        for junction in arterial_junctions(arterials):
            if "hwy1" in junction["roads"]:
                continue
            jx = float(junction["x"])
            jy = float(junction["y"])
            half = float(junction["half"])
            # Corner posts are shared by adjacent approach spans — place once.
            posts: dict[tuple[float, float], tuple[float, float]] = {}
            spans: list[tuple[float, float, float, float]] = []
            arms = list(junction["arms"])
            for ox, oy in arms:
                # Through arms: gantry on that edge. T stem: gantry on the
                # missing opposite side (e.g. roads N/S/W → lights on N/S/E).
                has_opposite = any(
                    dx * ox + dy * oy <= -0.85 for dx, dy in arms
                )
                if has_opposite:
                    place_ox, place_oy = ox, oy
                else:
                    place_ox, place_oy = -ox, -oy
                edge_x = jx + place_ox * half
                edge_y = jy + place_oy * half
                px, py = -place_oy, place_ox
                ax = edge_x + px * half
                ay = edge_y + py * half
                bx = edge_x - px * half
                by = edge_y - py * half
                posts[(round(ax, 3), round(ay, 3))] = (ax, ay)
                posts[(round(bx, 3), round(by, 3))] = (bx, by)
                spans.append((ax, ay, bx, by))
            for post_x, post_y in posts.values():
                signal_builders._add_signal_post(
                    post_x, post_y, road_top, block_size
                )
            for ax, ay, bx, by in spans:
                signal_builders._add_traffic_light(
                    ax,
                    ay,
                    bx,
                    by,
                    road_top,
                    block_size,
                    face_x=jx,
                    face_y=jy,
                )
                signal_count += 1
        if signal_count > 0:
            self._signals_root.flattenStrong()
            self._signals = TrafficLightController(self)
            self.taskMgr.add(self._signals.update, "traffic-lights")
        else:
            self._signals_root.removeNode()

        # Red district titles — shown only while that district is selected.
        for key, district in self._districts.items():
            ring = district["ring"]
            text = TextNode(f"district-label-{key}")
            text.setText(district["title"])
            text.setAlign(TextNode.ACenter)
            text.setTextColor(0.86, 0.12, 0.1, 1)
            text.setShadow(0.05, 0.05)
            text.setShadowColor(0.08, 0.02, 0.02, 0.75)
            pivot = self.render.attachNewNode(f"district-label-pivot-{key}")
            pivot.setPos(
                sum(p[0] for p in ring) / len(ring),
                sum(p[1] for p in ring) / len(ring),
                road_top + 6.0,
            )
            label = pivot.attachNewNode(text)
            label_scale = self._label_base_scale * 1.15
            label.setScale(label_scale)
            label.setBillboardPointEye()
            label.setDepthTest(False)
            label.setDepthWrite(False)
            label.hide()
            district["label"] = label
            district["label_scale"] = label_scale

        self.highway.flattenStrong()

        # Local residential streets (Surrey interior fabric) — no median barrier.
        streets = plan.street_geometry()
        self.streets = self.render.attachNewNode("streets")
        street_width = float(streets["street_width"])
        for route in streets["routes"]:
            pts = list(route["points"])
            if len(pts) < 2:
                continue
            deck = self.streets.attachNewNode(
                make_highway_ribbon(pts, street_width, road_thickness)
            )
            deck.setPos(0.0, 0.0, road_z)
            deck.setMaterial(road_mat, 1)
            # Single centreline dash — skip tips so junctions / bulbs stay clean.
            mark_len = 2.0
            mark_w = 0.2
            mark_h = 0.04
            mark_gap = 3.0
            period = mark_len + mark_gap
            tip_clear = street_width * 1.1
            dist = [0.0]
            for i in range(len(pts) - 1):
                dist.append(
                    dist[-1]
                    + math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                )
            total = dist[-1]
            if total >= period + 2.0 * tip_clear:
                s = tip_clear + mark_len * 0.5
                while s < total - tip_clear:
                    ss = max(0.0, min(total, s))
                    j = 0
                    while j < len(dist) - 2 and dist[j + 1] < ss:
                        j += 1
                    span = dist[j + 1] - dist[j]
                    t = 0.0 if span < 1e-9 else (ss - dist[j]) / span
                    x0, y0 = pts[j]
                    x1, y1 = pts[j + 1]
                    dx = x1 - x0
                    dy = y1 - y0
                    length = math.hypot(dx, dy) or 1.0
                    ux, uy = dx / length, dy / length
                    x = x0 + dx * t
                    y = y0 + dy * t
                    heading = math.degrees(math.atan2(uy, ux))
                    mark = box_instance(self.streets, mark_len, mark_w, mark_h)
                    mark.setPos(x, y, road_top + 0.02)
                    mark.setH(heading)
                    mark.setMaterial(mark_paint, 1)
                    s += period
        # Round cul-de-sac pads at dead ends.
        for cx, cy, radius in streets["bulbs"]:
            pad = z_cylinder_instance(
                self.streets, radius, road_thickness, segments=28
            )
            pad.setPos(cx, cy, road_z)
            pad.setMaterial(road_mat, 1)
        self.streets.flattenStrong()

        lawn_mat = lawn_material()
        ground_pad = 80.0
        self._ground = box_instance(
            self.render,
            (hwy["bounds_east"] - hwy["bounds_west"]) + ground_pad,
            (hwy["bounds_north"] - hwy["bounds_south"]) + ground_pad,
            0.16,
        )
        self._ground.setPos(
            (hwy["bounds_west"] + hwy["bounds_east"]) / 2,
            (hwy["bounds_south"] + hwy["bounds_north"]) / 2,
            road_z - 0.12,
        )
        self._ground.setMaterial(lawn_mat, 1)

        # Fixed-function lights — colours / HPR driven by the day-night cycle.
        self._ambient_light = AmbientLight("ambient")
        self._ambient_np = self.render.attachNewNode(self._ambient_light)
        self.render.setLight(self._ambient_np)
        self._sun_light = DirectionalLight("sun")
        self._sun_np = self.render.attachNewNode(self._sun_light)
        self.render.setLight(self._sun_np)
        self._fill_light = DirectionalLight("fill")
        self._fill_np = self.render.attachNewNode(self._fill_light)
        self.render.setLight(self._fill_np)

        # Sky dome tracks the camera, world-oriented; rebuilt as the cycle shifts.
        self._sky_root = self.camera.attachNewNode("sky-root")
        self._sky_root.setEffect(CompassEffect.make(self.render))
        self._sky_root.setBin("background", 0)
        self._sky_root.setDepthWrite(False)
        self._sky_root.setDepthTest(False)
        self._sky_root.setLightOff()
        self._sky_geom: object | None = None
        self._sky_key: tuple | None = None
        # Begin mid-sunrise so load isn't pitch-black; full loop is still 10 min.
        self._day_cycle = DayNightCycle(SUNRISE_SECONDS * 0.5)
        self._vehicle_lights_on = False
        self._apply_day_cycle(self._day_cycle.sample(), force_sky=True)

        # One cruiser on Fraser Hwy (right lane); Space focuses it.
        self._cars: list[CarController] = []
        self._car = None
        self._player_car: PlayerCar | None = None
        self._fleet_root = self.render.attachNewNode("fleet")
        fraser = next((a for a in arterials if a.get("name") == "fraser"), None)
        if fraser is not None and len(fraser.get("points") or ()) >= 2:
            lane_pts = offset_polyline(
                list(fraser["points"]),
                -float(fraser["width"]) / 4,
            )
            loop = [(x, y, road_top) for x, y in lane_pts]
            car = CarController(self, self._cars)
            car.setup(
                road_top,
                plan.west_road_full0,
                plan.south_road_full0,
                plan.stride_x,
                plan.stride_y,
                plan.cols,
                plan.rows,
                start_h=0,
                start_v=0,
                start_dir=(1, 0),
                body_colour=(0.22, 0.48, 0.72),
            )
            car._car_diamonds = []
            car._car_loop_path = loop
            car._car_pos = [loop[0][0], loop[0][1]]
            car._car_set_surface_z(loop[0][2])
            car._car_begin_path(list(loop), kind="arterial_loop")
            car._place_car()
            self._car = car
            self.taskMgr.add(self._fleet_task, "fleet")

        # Green player car on King George Blvd through Surrey City Centre.
        king = next((a for a in arterials if a.get("name") == "king_george"), None)
        if king is not None:
            kg_w = float(king.get("width", plan.road_width))
            # Right lane, northbound, mid-block between 102 Ave and 108 Ave.
            self._player_car = PlayerCar(
                self,
                road_top,
                155.0 + kg_w / 4.0,
                227.0,
                heading=90.0,
                body_colour=(0.16, 0.62, 0.28),
            )
            self.taskMgr.add(self._player_drive_task, "player-drive")

        bounds = plan.framing_bounds()
        left = bounds["left"]
        right = bounds["right"]
        frame_south = bounds["city_south"]
        frame_north = bounds["city_north"]
        # Highways sit near z=0; don't aim at tower mid-height when fabric is empty.
        self.look_at = (
            (left + right) / 2,
            (frame_south + frame_north) / 2,
            road_z,
        )
        # North-up overview so diagonal Fraser Hwy / Hwy 99 read clearly.
        self.heading = 0.0
        self.pitch = 68.0
        half_fov = math.tan(math.radians(20.0))
        fit_x = ((right - left) / 2) / half_fov
        fit_y = ((frame_north - frame_south) / 2) / half_fov / max(0.25, math.cos(math.radians(self.pitch)))
        self.distance = max(fit_x, fit_y) * 1.2
        self.min_distance = 2.0
        self.max_distance = max(200.0, self.distance * 2.5)
        # Overview distance → label world scale of 1× (see _update_camera).
        self._label_ref_distance = self.distance
        self.dragging = False
        self._drag_moved = False
        self._press_x = 0.0
        self._press_y = 0.0
        self.last_x = 0.0
        self.last_y = 0.0
        self._click_drag_threshold = 0.02
        # Nodes dimmed when a district is selected (optional bright node excluded).
        self._dim_targets = list(self.city.getChildren())
        self._dim_targets.extend(
            (
                self.highway,
                self.streets,
                self._ground,
                self._fleet_root,
                self._highway_labels,
            )
        )
        # Space cycles: car 0..n-1, then restore this overview framing.
        self._default_look_at = list(self.look_at)
        self._default_distance = self.distance
        self._default_heading = self.heading
        self._default_pitch = self.pitch
        self._focus_index = -1  # -1 = overview; 0..len(focusables)-1 = follow car
        self._car_focus_distance = 14.0
        # C toggles Fortnite-style third-person drive mode on the green car.
        self._car_mode = False
        self._chase_back = 8.5
        self._chase_height = 3.4
        self._chase_look_ahead = 2.0
        self._chase_look_z = 1.0
        self._chase_yaw_offset = 0.0
        self._map_look_at = list(self.look_at)
        self._map_distance = self.distance
        self._map_heading = self.heading
        self._map_pitch = self.pitch
        self._hud_place_text = ""
        self._hud_street_text = ""
        self._hud_speed_text = ""
        self._hud_compass_text = ""
        # World units ≈ metres; 3.6 → km/h for the car-mode speedometer.
        self._speed_to_kmh = 3.6
        self._hud_place = OnscreenText(
            text="",
            parent=self.a2dTopLeft,
            pos=(0.05, -0.08),
            scale=0.055,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self._hud_street = OnscreenText(
            text="",
            parent=self.a2dTopCenter,
            pos=(0.0, -0.1),
            scale=0.07,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ACenter,
            mayChange=True,
        )
        # C mode: cardinal above the speedometer (world Y = north).
        self._hud_compass = OnscreenText(
            text="",
            parent=self.a2dBottomRight,
            pos=(-0.06, 0.28),
            scale=0.07,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.75),
            align=TextNode.ARight,
            mayChange=True,
        )
        self._hud_speed = OnscreenText(
            text="",
            parent=self.a2dBottomRight,
            pos=(-0.06, 0.14),
            scale=0.1,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.75),
            align=TextNode.ARight,
            mayChange=True,
        )
        self._hud_speed_unit = OnscreenText(
            text="km/h",
            parent=self.a2dBottomRight,
            pos=(-0.06, 0.06),
            scale=0.045,
            fg=(0.85, 0.88, 0.92, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ARight,
            mayChange=False,
        )
        self._hud_place.hide()
        self._hud_street.hide()
        self._hud_compass.hide()
        self._hud_speed.hide()
        self._hud_speed_unit.hide()
        # Clock: top-centre on the map, bottom-left in C (drive) mode.
        self._hud_clock = OnscreenText(
            text=self._day_cycle.clock_text(),
            parent=self.a2dTopCenter,
            pos=(0.0, -0.08),
            scale=0.065,
            fg=(0.96, 0.97, 0.99, 1),
            shadow=(0.0, 0.0, 0.0, 0.7),
            align=TextNode.ACenter,
            mayChange=True,
        )
        self._hud_clock_text = ""
        self._layout_clock_hud()
        self._update_camera()

        self.accept("escape", sys.exit)
        self.accept("c", self._toggle_car_mode)
        self.accept("space", self._cycle_car_focus)
        self.accept("backspace", self._clear_district_selection)
        self.accept("s", self._select_surrey)
        self.accept("l", self._select_district_of_langley)
        self.accept("e", self._select_delta)
        self.accept("r", self._select_richmond)
        self.accept("v", self._select_vancouver)
        self.accept("wheel_up", self._zoom, [0.94])
        self.accept("wheel_down", self._zoom, [1.0 / 0.94])
        self.accept("mouse1", self._start_drag)
        self.accept("mouse1-up", self._end_drag)
        self.taskMgr.add(self._drag_task, "orbit-drag")
        self.taskMgr.add(self._pan_task, "camera-pan")
        self.taskMgr.add(self._follow_focus_task, "follow-car-focus")
        self.taskMgr.add(self._car_hud_task, "car-hud")
        self.taskMgr.add(self._day_cycle_task, "day-night-cycle")
        if not self.screenshot_path:
            self.fps_text = OnscreenText(
                text="",
                parent=self.a2dTopRight,
                pos=(-0.04, -0.08),
                scale=0.09,
                fg=(0.12, 0.14, 0.18, 1),
                align=TextNode.ARight,
                mayChange=True,
            )
            self.taskMgr.add(self._fps_task, "fps-counter")

    def _fps_task(self, task):
        # Text updates are relatively expensive; twice a second is enough.
        slot = int(task.time * 2.0)
        if slot == getattr(self, "_fps_slot", -1):
            return task.cont
        self._fps_slot = slot
        self.fps_text.setText(f"FPS: {self.clock.getAverageFrameRate():.0f}")
        return task.cont

    def _layout_clock_hud(self) -> None:
        """Map mode: top centre. C mode: bottom left (street name keeps the top)."""
        if not hasattr(self, "_hud_clock"):
            return
        if self._car_mode:
            self._hud_clock.reparentTo(self.a2dBottomLeft)
            self._hud_clock.setPos(0.05, 0.1)
            self._hud_clock.setAlign(TextNode.ALeft)
        else:
            self._hud_clock.reparentTo(self.a2dTopCenter)
            self._hud_clock.setPos(0.0, -0.08)
            self._hud_clock.setAlign(TextNode.ACenter)

    def _day_cycle_task(self, task):
        self._day_cycle.update(self.clock.getDt())
        self._apply_day_cycle(self._day_cycle.sample())
        return task.cont

    def _apply_day_cycle(self, sample, *, force_sky: bool = False) -> None:
        """Push cycle sample into lights, clear colour, sky dome, and clock."""
        self._vehicle_lights_on = sample.vehicle_lights_on
        ar, ag, ab = sample.ambient
        self._ambient_light.setColor((ar, ag, ab, 1))
        sr, sg, sb = sample.sun_color
        self._sun_light.setColor((sr, sg, sb, 1))
        self._sun_np.setHpr(*sample.sun_hpr)
        fr, fg, fb = sample.fill_color
        self._fill_light.setColor((fr, fg, fb, 1))
        self._fill_np.setHpr(*sample.fill_hpr)
        br, bg, bb = sample.background
        self.setBackgroundColor(br, bg, bb, 1)

        # Rebuild the dome when the palette moves enough — cheap 8×24 mesh.
        sky_key = (
            round(sample.zenith[0], 3),
            round(sample.zenith[1], 3),
            round(sample.zenith[2], 3),
            round(sample.horizon_cool[0], 3),
            round(sample.horizon_cool[1], 3),
            round(sample.horizon_cool[2], 3),
            round(sample.horizon_warm[0], 3),
            round(sample.horizon_warm[1], 3),
            round(sample.horizon_warm[2], 3),
            round(sample.sun_phi_deg, 1),
        )
        if force_sky or sky_key != self._sky_key:
            self._sky_key = sky_key
            if self._sky_geom is not None:
                self._sky_geom.removeNode()
            # Stronger horizon glow during warm sunrise/sunset keys.
            warm = sample.horizon_warm
            glow = 0.18 + 0.35 * max(0.0, warm[0] - warm[2])
            self._sky_geom = self._sky_root.attachNewNode(
                make_sky_dome(
                    zenith=sample.zenith,
                    horizon_cool=sample.horizon_cool,
                    horizon_warm=sample.horizon_warm,
                    sun_phi_deg=sample.sun_phi_deg,
                    glow_strength=glow,
                )
            )
            self._sky_geom.setBin("background", 0)
            self._sky_geom.setDepthWrite(False)
            self._sky_geom.setDepthTest(False)
            self._sky_geom.setLightOff()

        if hasattr(self, "_hud_clock") and sample.clock_text != self._hud_clock_text:
            self._hud_clock_text = sample.clock_text
            self._hud_clock.setText(sample.clock_text)

        # Player car only runs its update loop in C mode — sync night lamps here.
        player = getattr(self, "_player_car", None)
        if player is not None and not getattr(self, "_car_mode", False):
            player._refresh_lamps(braking=False, reversing=False)

    def _fleet_task(self, task):
        # One spatial/corridor index for the whole fleet, then each car updates.
        CarController.build_fleet_index(self._cars)
        for car in self._cars:
            car._car_task(task)
        # Overview: hide most cars (they're dots). Close-up: hide far cars.
        lx, ly, _lz = self.look_at
        if self.distance >= 70.0:
            hide_r2 = 55.0 * 55.0
        else:
            hide_r2 = 95.0 * 95.0
        for car in self._cars:
            dx = car._car_pos[0] - lx
            dy = car._car_pos[1] - ly
            far = dx * dx + dy * dy > hide_r2
            if far and not car.car.isHidden():
                car.car.hide()
            elif not far and car.car.isHidden():
                car.car.show()
        return task.cont

    def _focusable_cars(self) -> list:
        """Player car first, then AI fleet — Space cycles through these."""
        cars: list = []
        if self._player_car is not None:
            cars.append(self._player_car)
        cars.extend(self._cars)
        return cars

    def _car_look_at(self, car) -> list[float]:
        return [car._car_pos[0], car._car_pos[1], car._car_z + 0.5]

    def _toggle_car_mode(self) -> None:
        """C: enter/exit third-person drive mode on the green player car."""
        if self._player_car is None:
            return
        if self._car_mode:
            self._exit_car_mode()
        else:
            self._enter_car_mode()

    def _enter_car_mode(self) -> None:
        self._car_mode = True
        self._clear_district_selection()
        self._focus_index = -1
        self.dragging = False
        self._map_look_at = list(self.look_at)
        self._map_distance = self.distance
        self._map_heading = self.heading
        self._map_pitch = self.pitch
        self._chase_yaw_offset = 0.0
        self._hud_place_text = ""
        self._hud_street_text = ""
        self._hud_speed_text = ""
        self._hud_compass_text = ""
        # World-space arterial titles clutter the chase cam; HUD keeps the name.
        self._highway_labels.hide()
        self._hud_place.show()
        self._hud_street.show()
        self._hud_compass.show()
        self._hud_speed.show()
        self._hud_speed_unit.show()
        self._layout_clock_hud()
        self._refresh_car_hud(force=True)
        self._update_chase_camera()

    def _exit_car_mode(self) -> None:
        self._car_mode = False
        self.dragging = False
        self._highway_labels.show()
        self._hud_place.hide()
        self._hud_street.hide()
        self._hud_compass.hide()
        self._hud_speed.hide()
        self._hud_speed_unit.hide()
        self._hud_place.setText("")
        self._hud_street.setText("")
        self._hud_compass.setText("")
        self._hud_speed.setText("")
        self._layout_clock_hud()
        self.look_at = list(self._map_look_at)
        self.distance = self._map_distance
        self.heading = self._map_heading
        self.pitch = self._map_pitch
        self._update_camera()

    @staticmethod
    def _build_segment_grid(
        segments: list, *, xy_offset: int, cell: float
    ) -> dict[tuple[int, int], list[int]]:
        """Hash segment indices by AABB cells for nearby queries."""
        grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        if cell <= 0.0:
            return grid
        for idx, seg in enumerate(segments):
            ax = float(seg[xy_offset])
            ay = float(seg[xy_offset + 1])
            bx = float(seg[xy_offset + 2])
            by = float(seg[xy_offset + 3])
            half_w = float(seg[-1])
            pad = half_w + 1.0
            i0 = int(math.floor((min(ax, bx) - pad) / cell))
            i1 = int(math.floor((max(ax, bx) + pad) / cell))
            j0 = int(math.floor((min(ay, by) - pad) / cell))
            j1 = int(math.floor((max(ay, by) + pad) / cell))
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    grid[(i, j)].append(idx)
        return grid

    def _nearby_segment_indices(
        self,
        grid: dict[tuple[int, int], list[int]],
        x: float,
        y: float,
        radius: float,
        cell: float,
    ) -> list[int]:
        if not grid or cell <= 0.0:
            return []
        i0 = int(math.floor((x - radius) / cell))
        i1 = int(math.floor((x + radius) / cell))
        j0 = int(math.floor((y - radius) / cell))
        j1 = int(math.floor((y + radius) / cell))
        seen: set[int] = set()
        out: list[int] = []
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                for idx in grid.get((i, j), ()):
                    if idx not in seen:
                        seen.add(idx)
                        out.append(idx)
        return out

    def nearby_barriers(
        self, x: float, y: float, radius: float
    ) -> list[tuple[float, float, float, float, float]]:
        idxs = self._nearby_segment_indices(
            getattr(self, "_barrier_grid", {}),
            x,
            y,
            radius,
            getattr(self, "_barrier_cell", _SEG_CELL),
        )
        barriers = getattr(self, "_solid_barriers", None) or []
        return [barriers[i] for i in idxs]

    def nearby_roads(
        self, x: float, y: float, radius: float
    ) -> list[tuple[str, float, float, float, float, float]]:
        idxs = self._nearby_segment_indices(
            getattr(self, "_road_grid", {}),
            x,
            y,
            radius,
            getattr(self, "_road_cell", _SEG_CELL),
        )
        roads = getattr(self, "_named_roads", None) or []
        return [roads[i] for i in idxs]

    def _location_at(self, x: float, y: float) -> str:
        """Neighborhood + municipality for car HUD, e.g. 'Newton, Surrey'."""
        for key, area, city in _LOCATION_AREAS:
            district = self._districts.get(key)
            if district is None:
                continue
            if self._point_in_ring(district["ring"], x, y):
                return f"{area}, {city}"
        return "Unknown area"

    def _street_at(self, x: float, y: float) -> str:
        """Nearest arterial name if the car is on/near its pavement."""
        best_name = ""
        best_d2 = float("inf")
        for name, ax, ay, bx, by, half_w in self.nearby_roads(x, y, 40.0):
            d2, _qx, _qy = _dist2_point_segment(x, y, ax, ay, bx, by)
            # Stay within the ribbon plus a small shoulder so lane offset still counts.
            limit = half_w + 2.5
            if d2 <= limit * limit and d2 < best_d2:
                best_d2 = d2
                best_name = name
        return best_name or "Off road"

    @staticmethod
    def _compass_from_heading(heading_deg: float) -> str:
        """Cardinal label from car yaw (0° = +X east, 90° = +Y north)."""
        bearing = (90.0 - heading_deg) % 360.0
        dirs = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        return dirs[int((bearing + 22.5) // 45.0) % 8]

    def _refresh_speedometer(self, *, force: bool = False) -> None:
        if self._player_car is None:
            return
        kmh = int(round(abs(self._player_car._car_speed) * self._speed_to_kmh))
        text = str(kmh)
        if force or text != self._hud_speed_text:
            self._hud_speed_text = text
            self._hud_speed.setText(text)

    def _refresh_compass(self, *, force: bool = False) -> None:
        if self._player_car is None:
            return
        text = self._compass_from_heading(self._player_car._car_heading)
        if force or text != self._hud_compass_text:
            self._hud_compass_text = text
            self._hud_compass.setText(text)

    def _refresh_car_hud(self, *, force: bool = False) -> None:
        if self._player_car is None:
            return
        x, y = self._player_car._car_pos[0], self._player_car._car_pos[1]
        place = self._location_at(x, y)
        street = self._street_at(x, y)
        if force or place != self._hud_place_text:
            self._hud_place_text = place
            self._hud_place.setText(place)
        if force or street != self._hud_street_text:
            self._hud_street_text = street
            self._hud_street.setText(street)
        self._refresh_compass(force=force)
        self._refresh_speedometer(force=force)

    def _car_hud_task(self, task):
        if not self._car_mode:
            return task.cont
        # Speed / compass update snappier; place/street can lag a bit.
        speed_slot = int(task.time * 12.0)
        if speed_slot != getattr(self, "_hud_speed_slot", -1):
            self._hud_speed_slot = speed_slot
            self._refresh_speedometer()
            self._refresh_compass()
        slot = int(task.time * 4.0)
        if slot == getattr(self, "_hud_slot", -1):
            return task.cont
        self._hud_slot = slot
        self._refresh_car_hud()
        return task.cont

    def _update_chase_camera(self) -> None:
        """Fortnite-style chase: behind + above the car, optional mouse yaw offset."""
        car = self._player_car
        if car is None:
            return
        rad = math.radians(car._car_heading + self._chase_yaw_offset)
        fx = math.cos(rad)
        fy = math.sin(rad)
        px, py = car._car_pos[0], car._car_pos[1]
        pz = car._car_z
        self.camera.setPos(
            px - fx * self._chase_back,
            py - fy * self._chase_back,
            pz + self._chase_height,
        )
        look_x = px + fx * self._chase_look_ahead
        look_y = py + fy * self._chase_look_ahead
        look_z = pz + self._chase_look_z
        self.camera.lookAt(look_x, look_y, look_z)
        self.look_at = [look_x, look_y, look_z]

    def _cycle_car_focus(self) -> None:
        """Space: zoom to next car; after the last car, restore the city overview."""
        if self._car_mode:
            return
        cars = self._focusable_cars()
        if not cars:
            return
        self._focus_index += 1
        if self._focus_index >= len(cars):
            self._focus_index = -1
            self.look_at = list(self._default_look_at)
            self.distance = self._default_distance
            self.heading = self._default_heading
            self.pitch = self._default_pitch
            self._update_camera()
            return

        car = cars[self._focus_index]
        self.look_at = self._car_look_at(car)
        self.distance = min(
            self.max_distance,
            max(self.min_distance, self._car_focus_distance),
        )
        # Top-down follow; keep heading so the city stays oriented.
        self.pitch = 85.0
        self._update_camera()

    def _follow_focus_task(self, task):
        if self._car_mode:
            self._update_chase_camera()
            return task.cont
        cars = self._focusable_cars()
        if 0 <= self._focus_index < len(cars):
            self.look_at = self._car_look_at(cars[self._focus_index])
            self._update_camera()
        return task.cont

    def _player_drive_task(self, task):
        """C mode: WASD drive; left/right arrows for slight heading trim."""
        if not self._car_mode or self._player_car is None:
            return task.cont
        mw = self.mouseWatcherNode
        self._player_car.update(
            self.clock.getDt(),
            gas=mw.is_button_down(KeyboardButton.ascii_key("w")),
            brake=mw.is_button_down(KeyboardButton.ascii_key("s")),
            steer_left=mw.is_button_down(KeyboardButton.ascii_key("a")),
            steer_right=mw.is_button_down(KeyboardButton.ascii_key("d")),
            nudge_left=mw.is_button_down(KeyboardButton.left()),
            nudge_right=mw.is_button_down(KeyboardButton.right()),
        )
        return task.cont

    def _update_camera(self) -> None:
        if self._car_mode:
            self._update_chase_camera()
            return
        pitch = math.radians(self.pitch)
        heading = math.radians(self.heading)
        cos_pitch = math.cos(pitch)
        look_x, look_y, look_z = self.look_at
        self.camera.setPos(
            look_x + self.distance * math.sin(heading) * cos_pitch,
            look_y - self.distance * math.cos(heading) * cos_pitch,
            look_z + self.distance * math.sin(pitch),
        )
        self.camera.lookAt(look_x, look_y, look_z)
        # Keep label screen size roughly constant while zooming.
        ref = max(self._label_ref_distance, 1e-6)
        zoom = self.distance / ref
        scale = self._label_base_scale * zoom
        for label in self._highway_label_nodes:
            label.setScale(scale)
        for district in self._districts.values():
            label = district.get("label")
            if label is not None:
                label.setScale(district["label_scale"] * zoom)

    def _zoom(self, factor: float) -> None:
        if self._car_mode:
            self._chase_back = min(22.0, max(4.0, self._chase_back * factor))
            self._chase_height = min(10.0, max(1.5, self._chase_height * factor))
            self._update_chase_camera()
            return
        self.distance = min(
            self.max_distance,
            max(self.min_distance, self.distance * factor),
        )
        # While following a car, keep wheel zoom as the new follow distance.
        if self._focus_index >= 0:
            self._car_focus_distance = self.distance
        self._update_camera()

    def _build_district_outline(self, key: str, ring: tuple, z: float):
        """Dashed red outline along a district's arterial ring."""
        segs = LineSegs(f"district-outline-{key}")
        segs.setThickness(3.0)
        segs.setColor(0.86, 0.12, 0.1, 1.0)
        dash = 2.4
        gap = 1.3
        for i in range(len(ring)):
            x0, y0 = ring[i]
            x1, y1 = ring[(i + 1) % len(ring)]
            dx = x1 - x0
            dy = y1 - y0
            length = math.hypot(dx, dy)
            if length < 1e-6:
                continue
            ux = dx / length
            uy = dy / length
            t = 0.0
            drawing = True
            while t < length:
                seg_len = dash if drawing else gap
                t_end = min(length, t + seg_len)
                if drawing:
                    segs.moveTo(x0 + ux * t, y0 + uy * t, z)
                    segs.drawTo(x0 + ux * t_end, y0 + uy * t_end, z)
                t = t_end
                drawing = not drawing
        return self.render.attachNewNode(segs.create())

    @staticmethod
    def _point_in_ring(ring: tuple, x: float, y: float) -> bool:
        """True if (x, y) is inside the ring (even-odd fill)."""
        n = len(ring)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi
            ):
                inside = not inside
            j = i
        return inside

    def _ground_hit_xy(self) -> tuple[float, float] | None:
        """Ray from camera through the mouse onto the ground plane."""
        if not self.mouseWatcherNode.hasMouse():
            return None
        mpos = self.mouseWatcherNode.getMouse()
        near = Point3()
        far = Point3()
        self.camLens.extrude(mpos, near, far)
        near_w = self.render.getRelativePoint(self.cam, near)
        far_w = self.render.getRelativePoint(self.cam, far)
        dz = far_w.z - near_w.z
        if abs(dz) < 1e-9:
            return None
        t = (self._ground_z - near_w.z) / dz
        if t < 0.0:
            return None
        return (
            near_w.x + (far_w.x - near_w.x) * t,
            near_w.y + (far_w.y - near_w.y) * t,
        )

    def _select_district(self, key: str) -> None:
        if self._selected_district == key:
            return
        self._clear_district_selection()
        district = self._districts[key]
        self._selected_district = key
        dim = (0.55, 0.55, 0.55, 1.0)
        bright = district.get("bright")
        for node in self._dim_targets:
            if bright is not None and node == bright:
                continue
            node.setColorScale(*dim)
        district["outline"].show()
        label = district.get("label")
        if label is not None:
            label.show()

    def _clear_district_selection(self) -> None:
        if self._selected_district is None:
            return
        district = self._districts[self._selected_district]
        self._selected_district = None
        for node in self._dim_targets:
            node.clearColorScale()
        district["outline"].hide()
        label = district.get("label")
        if label is not None:
            label.hide()

    def _select_surrey(self) -> None:
        """S: outline Greater Surrey (disabled in C / car mode)."""
        if self._car_mode:
            return
        self._select_district("surrey")

    def _select_district_of_langley(self) -> None:
        """L: outline District of Langley (disabled in C / car mode)."""
        if self._car_mode:
            return
        self._select_district("district_of_langley")

    def _select_delta(self) -> None:
        """E: outline Delta (disabled in C / car mode)."""
        if self._car_mode:
            return
        self._select_district("delta")

    def _select_richmond(self) -> None:
        """R: outline Richmond / Lulu Island, no YVR (disabled in C / car mode)."""
        if self._car_mode:
            return
        self._select_district("richmond")

    def _select_vancouver(self) -> None:
        """V: outline Vancouver city proper, no UEL (disabled in C / car mode)."""
        if self._car_mode:
            return
        self._select_district("vancouver")

    def _try_select_district(self) -> None:
        if self._car_mode:
            return
        hit = self._ground_hit_xy()
        if hit is None:
            return
        x, y = hit
        for key, district in self._districts.items():
            if district.get("hotkey_only"):
                continue
            if self._point_in_ring(district["ring"], x, y):
                self._select_district(key)
                return

    def _start_drag(self) -> None:
        if not self.mouseWatcherNode.hasMouse():
            return
        self.dragging = True
        self._drag_moved = False
        self.last_x = self.mouseWatcherNode.getMouseX()
        self.last_y = self.mouseWatcherNode.getMouseY()
        self._press_x = self.last_x
        self._press_y = self.last_y

    def _end_drag(self) -> None:
        was_click = self.dragging and not self._drag_moved
        self.dragging = False
        # District pick is map-only; car mode keeps mouse for chase orbit.
        if was_click and not self._car_mode:
            self._try_select_district()

    def _drag_task(self, task):
        if self.dragging and self.mouseWatcherNode.hasMouse():
            x = self.mouseWatcherNode.getMouseX()
            y = self.mouseWatcherNode.getMouseY()
            if (
                abs(x - self._press_x) > self._click_drag_threshold
                or abs(y - self._press_y) > self._click_drag_threshold
            ):
                self._drag_moved = True
            if self._drag_moved:
                dx = x - self.last_x
                dy = y - self.last_y
                if self._car_mode:
                    # Orbit chase yaw; nudge height like a light pitch look.
                    self._chase_yaw_offset -= dx * 120.0
                    self._chase_height = max(
                        1.2, min(12.0, self._chase_height + dy * 6.0)
                    )
                    self._update_chase_camera()
                else:
                    self.heading -= dx * 120.0
                    self.pitch = max(-85.0, min(85.0, self.pitch + dy * 90.0))
                    self._update_camera()
            self.last_x = x
            self.last_y = y
        return task.cont

    def _pan_task(self, task):
        """Arrow keys: pan look_at on the ground plane (disabled in C mode)."""
        if self._car_mode:
            return task.cont
        mw = self.mouseWatcherNode
        forward = 0.0
        right = 0.0
        if mw.is_button_down(KeyboardButton.up()):
            forward += 1.0
        if mw.is_button_down(KeyboardButton.down()):
            forward -= 1.0
        if mw.is_button_down(KeyboardButton.right()):
            right += 1.0
        if mw.is_button_down(KeyboardButton.left()):
            right -= 1.0
        if forward == 0.0 and right == 0.0:
            return task.cont

        # Leave car follow so pan isn't overwritten every frame.
        if self._focus_index >= 0:
            self._focus_index = -1

        heading = math.radians(self.heading)
        # Match _update_camera: heading 0 looks along +Y.
        fx = -math.sin(heading)
        fy = math.cos(heading)
        rx = math.cos(heading)
        ry = math.sin(heading)
        speed = self.distance * 0.85 * self.clock.getDt()
        look_x, look_y, look_z = self.look_at
        self.look_at = (
            look_x + (fx * forward + rx * right) * speed,
            look_y + (fy * forward + ry * right) * speed,
            look_z,
        )
        self._update_camera()
        return task.cont

    def capture(self) -> None:
        for _ in range(3):
            self.graphicsEngine.renderFrame()
        path = Filename.fromOsSpecific(self.screenshot_path)
        if not self.win.saveScreenshot(path):
            raise SystemExit(f"Could not write {self.screenshot_path}")
        print(f"Wrote {self.screenshot_path}")
