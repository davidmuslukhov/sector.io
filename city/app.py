"""ShowBase app: assemble the city from CityPlan and run the viewer."""

from __future__ import annotations

import math
import random
import sys

from panda3d.core import (
    AmbientLight,
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
from city.car import CarController
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
    box_instance,
    make_highway_ribbon,
    offset_polyline,
    split_polyline_around_gaps,
    z_cylinder_instance,
)
from city.plan import default_city_plan

# Readable names for arterial YAML keys (world-space map labels).
HIGHWAY_LABELS = {
    "hwy17": "Hwy 17",
    "hwy1": "Hwy 1",
    "fraser": "Fraser Hwy",
    "hwy15": "Hwy 15",
    "hwy10": "88 Ave",
    "hwy99": "Hwy 99",
    "hwy8": "Hwy 10",
    "king_george": "King George Blvd",
    "scott_120": "120 St",
    "st_120_s": "120 St",
    "ave_72": "72 Ave",
    "ave_96": "96 Ave",
    "ave_102": "102 Ave",
    "ave_108": "108 Ave",
    "ave_114": "114 Ave",
    "ave_58": "58 Ave",
    "ave_28": "28 Ave",
    "ave_16": "16 Ave",
    "ave_0": "0 Ave",
    "whalley_blvd": "Whalley Blvd",
    "university_dr": "University Dr",
    "marine_dr": "Marine Dr",
    "st_128": "128 St",
    "st_136": "136 St",
    "st_140": "140 St",
    "st_152": "152 St",
    "st_192": "192 St",
}

# Thin side fences: provincial highways plus Fraser, 88 Ave, and King George.
SIDE_BORDER_ROUTES = frozenset(
    {
        "hwy17",
        "hwy1",
        "fraser",
        "hwy15",
        "hwy99",
        "hwy8",
        "hwy10",
        "king_george",
    }
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

        # Demo towers on the NE plate, plus skyscrapers in the circled Whalley blocks.
        ne = SceneBuilders(self.city, plan, self.render)
        ne._add_house(560.0, 400.0, brick=0.68, chimney=True)
        ne._add_stack(
            590.0,
            400.0,
            18,
            block_size,
            block_material(BLOCK_SHADES[1]),
            footprint="rect",
            doors=("-y",),
        )
        ne._add_stack(
            605.0,
            400.0,
            18,
            block_size,
            block_material(BLOCK_SHADES[4]),
            footprint="round",
            doors=("-y",),
        )
        ne._add_stack(
            590.0,
            415.0,
            16,
            block_size,
            block_material(BLOCK_SHADES[7]),
            footprint="tri",
            heading=18.0,
            doors=("-y",),
        )
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
                # 120 St → 88 Ave → 152 St → Hwy 1 → Hwy 17 → 96 Ave (incl. Hwy 17/120/96 triangle); City Centre notched.
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
                    (140.0, 383.0),
                    (80.0, 372.0),
                    (25.0, 355.0),
                    (8.0, 350.0),
                    (-20.0, 325.0),
                    (-50.0, 280.0),
                    (-68.0, 230.0),
                    (-78.0, 175.0),
                    (14.0, 175.0),
                    (16.0, 120.0),
                ),
                "bright": None,
            },
            "north_delta": {
                "title": "North Delta",
                # West of 120 St, Hwy 99 north to 96 Ave along Hwy 17 (excludes SW Hwy 17/99 wedge).
                "ring": (
                    (14.0, 175.0),
                    (-78.0, 175.0),
                    (-90.0, 120.0),
                    (-105.0, 40.0),
                    (-120.0, -50.0),
                    (-128.5, -160.0),
                    (26.0, -160.0),
                    (24.0, -70.0),
                    (22.0, -20.0),
                    (20.0, 30.0),
                    (18.0, 78.0),
                    (16.0, 120.0),
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
                    (26.0, -160.0),
                    (24.0, -70.0),
                    (22.0, -20.0),
                    (20.0, 30.0),
                ),
                "bright": None,
            },
            "guildford": {
                "title": "Guildford",
                # 152 St / 96 Ave → Hwy 15 → Hwy 17 → Hwy 1 (west edge shared with Whalley).
                "ring": (
                    (285.0, 175.0),
                    (480.0, 175.0),
                    (480.0, 180.0),
                    (480.0, 300.0),
                    (480.0, 366.0),
                    (460.0, 370.0),
                    (400.0, 382.0),
                    (340.0, 390.0),
                    (270.0, 393.0),
                    (200.0, 390.0),
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
                # Hwy 15 → Hwy 1 (angled NE tip) → 192 St → 28 Ave → Hwy 99 → 152 St → Hwy 10.
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
                # 16 Ave → King George → 0 Ave → 136 St (carved from South Surrey).
                "ring": (
                    (174.0, -400.0),
                    (401.0, -400.0),
                    (482.0, -477.0),
                    (174.0, -477.0),
                ),
                "bright": None,
            },
            "south_surrey": {
                "title": "South Surrey",
                # Hwy 99 north → 28 Ave to 192 St → 0 Ave with White Rock Centre notched out → Marine Dr → 120 St.
                "ring": (
                    (26.0, -160.0),
                    (100.0, -160.0),
                    (160.0, -165.0),
                    (220.0, -205.0),
                    (280.0, -255.0),
                    (350.0, -320.0),
                    (480.0, -320.0),
                    (610.0, -320.0),
                    (610.0, -400.0),
                    (610.0, -477.0),
                    (517.0, -477.0),
                    (482.0, -477.0),
                    (401.0, -400.0),
                    (174.0, -400.0),
                    (174.0, -477.0),
                    (174.0, -485.0),
                    (120.0, -478.0),
                    (80.0, -465.0),
                    (45.0, -445.0),
                    (26.0, -420.0),
                    (26.0, -400.0),
                    (26.0, -320.0),
                ),
                "bright": None,
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
                    (480.0, 366.0),
                    (480.0, 190.0),
                    (520.0, 180.0),
                    (580.0, 168.0),
                    (610.0, 160.0),
                    (610.0, -320.0),
                    (610.0, -400.0),
                    (610.0, -477.0),
                    (517.0, -477.0),
                    (482.0, -477.0),
                    (401.0, -400.0),
                    (174.0, -400.0),
                    (174.0, -477.0),
                    (174.0, -485.0),
                    (120.0, -478.0),
                    (80.0, -465.0),
                    (45.0, -445.0),
                    (26.0, -420.0),
                    (26.0, -400.0),
                    (26.0, -320.0),
                    (26.0, -160.0),
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
            if plan.barrier_w > 0.0 and plan.barrier_h > 0.0:
                for piece in split_polyline_around_gaps(pts, median_gaps):
                    barrier = self.highway.attachNewNode(
                        make_highway_ribbon(piece, plan.barrier_w, plan.barrier_h)
                    )
                    barrier.setPos(0.0, 0.0, road_top + plan.barrier_h / 2)
                    barrier.setMaterial(barrier_mat, 1)
            if name in SIDE_BORDER_ROUTES and plan.fence_w > 0.0 and plan.fence_h > 0.0:
                # Thin concrete lips along both pavement edges; gapped at crossings.
                edge = route_width / 2 + plan.fence_w / 2
                fence_gaps = [(x, y, radius + edge) for x, y, radius in median_gaps]
                for side in (-1.0, 1.0):
                    edge_pts = offset_polyline(pts, side * edge)
                    for piece in split_polyline_around_gaps(edge_pts, fence_gaps):
                        fence = self.highway.attachNewNode(
                            make_highway_ribbon(piece, plan.fence_w, plan.fence_h)
                        )
                        fence.setPos(0.0, 0.0, road_top + plan.fence_h / 2)
                        fence.setMaterial(barrier_mat, 1)
            paint_route_marks(
                pts,
                road_top,
                lanes=route_lanes,
                width=route_width,
                mark_gaps=median_gaps,
            )

            title = HIGHWAY_LABELS.get(name, name.replace("_", " ").title())
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

        # Fixed-function lights (same stack the city builders used).
        ambient = AmbientLight("ambient")
        ambient.setColor((0.34, 0.37, 0.42, 1))
        self.render.setLight(self.render.attachNewNode(ambient))
        sun = DirectionalLight("sun")
        sun.setColor((1.15, 1.05, 0.9, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(38, -48, 0)
        self.render.setLight(sun_np)
        fill = DirectionalLight("fill")
        fill.setColor((0.18, 0.22, 0.3, 1))
        fill_np = self.render.attachNewNode(fill)
        fill_np.setHpr(220, -25, 0)
        self.render.setLight(fill_np)

        # One cruiser on Fraser Hwy (right lane); Space focuses it.
        self._cars: list[CarController] = []
        self._car = None
        self._signals = None
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
        self._focus_index = -1  # -1 = overview; 0..len(_cars)-1 = follow car
        self._car_focus_distance = 14.0
        self._update_camera()

        self.accept("escape", sys.exit)
        self.accept("space", self._cycle_car_focus)
        self.accept("backspace", self._clear_district_selection)
        self.accept("s", self._select_surrey)
        self.accept("wheel_up", self._zoom, [0.94])
        self.accept("wheel_down", self._zoom, [1.0 / 0.94])
        self.accept("mouse1", self._start_drag)
        self.accept("mouse1-up", self._end_drag)
        self.taskMgr.add(self._drag_task, "orbit-drag")
        self.taskMgr.add(self._pan_task, "camera-pan")
        self.taskMgr.add(self._follow_focus_task, "follow-car-focus")
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

    def _car_look_at(self, car: CarController) -> list[float]:
        return [car._car_pos[0], car._car_pos[1], car._car_z + 0.5]

    def _cycle_car_focus(self) -> None:
        """Space: zoom to next car; after the last car, restore the city overview."""
        if not self._cars:
            return
        self._focus_index += 1
        if self._focus_index >= len(self._cars):
            self._focus_index = -1
            self.look_at = list(self._default_look_at)
            self.distance = self._default_distance
            self.heading = self._default_heading
            self.pitch = self._default_pitch
            self._update_camera()
            return

        car = self._cars[self._focus_index]
        self.look_at = self._car_look_at(car)
        self.distance = min(
            self.max_distance,
            max(self.min_distance, self._car_focus_distance),
        )
        # Top-down follow; keep heading so the city stays oriented.
        self.pitch = 85.0
        self._update_camera()

    def _follow_focus_task(self, task):
        if 0 <= self._focus_index < len(self._cars):
            self.look_at = self._car_look_at(self._cars[self._focus_index])
            self._update_camera()
        return task.cont

    def _update_camera(self) -> None:
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
        """Hotkey: outline Greater Surrey (excludes North Delta and White Rock Centre)."""
        self._select_district("surrey")

    def _try_select_district(self) -> None:
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
        if was_click:
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
                self.heading -= (x - self.last_x) * 120.0
                self.pitch = max(
                    -85.0, min(85.0, self.pitch + (y - self.last_y) * 90.0)
                )
                self._update_camera()
            self.last_x = x
            self.last_y = y
        return task.cont

    def _pan_task(self, task):
        """WASD / arrows: pan look_at on the ground plane relative to heading."""
        mw = self.mouseWatcherNode
        forward = 0.0
        right = 0.0
        if mw.is_button_down(KeyboardButton.ascii_key("w")) or mw.is_button_down(
            KeyboardButton.up()
        ):
            forward += 1.0
        if mw.is_button_down(KeyboardButton.ascii_key("s")) or mw.is_button_down(
            KeyboardButton.down()
        ):
            forward -= 1.0
        if mw.is_button_down(KeyboardButton.ascii_key("d")) or mw.is_button_down(
            KeyboardButton.right()
        ):
            right += 1.0
        if mw.is_button_down(KeyboardButton.ascii_key("a")) or mw.is_button_down(
            KeyboardButton.left()
        ):
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
