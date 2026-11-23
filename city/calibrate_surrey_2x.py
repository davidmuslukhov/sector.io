"""DEPRECATED — Metro Vancouver plate. Active city is Chicago.

Use ``city/calibrate_chicago_2x.py`` to regenerate ``city/data/city.yaml``.
This module is retained only as a historical reference; running it will
overwrite the Chicago roads-only plate with Metro Vancouver.

---
Generate Surrey + Langley + Delta + Richmond + Vancouver/UBC + Burnaby +
New Westminster + Coquitlam + Maple Ridge + Pitt Meadows + North Vancouver
2× city.yaml, then pure north-up translate satellite cities onto Google Maps
downtown centres (see city/geo.py).

Scale: 26.4 units = 1.0 km; 1 unit = 37.9 m; 42.2 units = 1.0 mile.
Origin (0,0): King George Blvd & 104 Ave (Whalley) — lat 49.1913°, lon -122.8490°.
Formula: X=(lon+122.8490)*1919.4  Y=(lat-49.1913)*2932.2  (no rotation).
Surrey / Langley plate stays locked (196 St X=+295.4); other municipalities
translate so downtown centres match Google Maps; bridge abutments are snapped.
Flat roads only (Z = 0 + hierarchy offsets). Camera far clip: 6000.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

import yaml

from city.geo import (
    CAMERA_FAR_CLIP,
    LAT0,
    LON0,
    M_LAT,
    M_LON,
    METERS_PER_UNIT,
    calibration_banner,
    georeference_highways,
    snap_checkpoints_to_routes,
    stitch_report,
)

OUT = Path(__file__).resolve().parent / "data" / "city.yaml"

UNITS_PER_KM = 26.4
UNITS_PER_MILE = 42.2
HALF_MILE = UNITS_PER_MILE / 2.0  # 21.1
QUARTER_MILE = HALF_MILE / 2.0  # 10.55

# Street X anchors — Surrey milestones + uniform Langley 8-street steps.
STREET_X: dict[int, float] = {
    120: -84.4,  # Scott Rd / 120 St (GIS snap → -79.8 via geo.py)
    124: -84.4 + HALF_MILE,
    128: -42.2,
    132: -21.1,
    136: 0.0,  # King George corridor
    140: 15.8,  # compressed KG→152 band
    144: 31.6,
    148: 47.4,
    152: 63.2,
    156: 63.2 + HALF_MILE,
    160: 63.2 + UNITS_PER_MILE,
    164: 63.2 + UNITS_PER_MILE + HALF_MILE,
    168: 63.2 + 2 * UNITS_PER_MILE,
    172: 190.0 - HALF_MILE,
    176: 190.0,
    180: 190.0 + HALF_MILE,
    184: 190.0 + UNITS_PER_MILE,
    188: 190.0 + UNITS_PER_MILE + HALF_MILE,
    192: 295.4 - HALF_MILE,
    196: 295.4,
    # Langley Township — continue east from 196 St.
    200: 316.5,
    203: 332.0,  # Hammond / West Maple Ridge
    204: 316.5 + HALF_MILE,
    207: 353.0,  # Laity St / Pitt Meadows–Maple Ridge
    208: 358.7,
    210: 377.0,  # West Haney collector
    212: 358.7 + HALF_MILE,
    216: 400.9,
    220: 400.9 + HALF_MILE,
    222: 432.0,  # Downtown Haney / Haney Bypass branch
    224: 443.1,
    228: 443.1 + HALF_MILE,
    232: 485.3,
    236: 485.3 + HALF_MILE,
    240: 527.5,
    244: 527.5 + HALF_MILE,
    248: 569.7,
    252: 569.7 + HALF_MILE,
    256: 611.9,
    260: 611.9 + HALF_MILE,
    264: 654.1,  # Hwy 13
    268: 654.1 + HALF_MILE,
    272: 696.3,
    276: 717.4,  # Abbotsford border
    280: 738.5,  # Ruskin
    287: 775.0,  # Mission border
}

# Maple Ridge east plate limit (287 St / Mission).
X_MR_EAST = 775.0
# Pitt Meadows west plate — Pitt River Bridge approach.
X_PM_WEST = 175.0
X_PM_DYKE = 185.0  # western Pitt River dyke (no roads west of this except bridge)
X_LAITY = 353.0  # 207 St / Maple Ridge border
X_HARRIS = 306.0
X_BONSON = 295.4
X_RANNIE = 242.0
X_KENNEDY = 211.0
X_FORD = 274.3
# Dewdney Trunk / Park Road (primary E–W spine shared PM ↔ MR).
Y_DEWDNEY = 84.4
Y_AIRPORT = 52.0
Y_FORD_HAMMOND = 63.3
Y_OLD_DEWDNEY = 95.0
Y_NEAVES = 135.0
Y_PITT_LAKE = 195.0
# Maple Ridge avenue Y anchors (compact plate north of the Fraser).
MR_AVE_Y: dict[int, float] = {
    116: 65.0,  # near Lougheed at west Haney (approx)
    122: 94.95,  # midway Dewdney → 124 Ave
    124: 105.5,
    128: 126.6,
    132: 147.7,
    136: 165.0,
}

# River Road / Wharf St southern shoreline control points (X → Y).
MR_RIVER_CTRL: list[tuple[float, float]] = [
    (332.0, 55.0),  # 203 St
    (443.1, 48.0),  # 224 St
    (527.5, 25.0),  # 240 St
    (696.3, 5.0),  # 272 St
    (775.0, -5.0),  # 287 St
]

# Lougheed Hwy (Hwy 7) — Pitt River Bridge → Pitt Meadows → Maple Ridge.
LOUGHEED_CTRL: list[tuple[float, float]] = [
    (175.0, 68.0),  # Pitt River Bridge west approach
    (242.0, 72.0),  # Kennedy / Rannie junction
    (295.4, 72.0),  # Bonson Rd
    (306.0, 72.0),  # Harris Rd
    (332.0, 68.0),  # Blakely / 203 St
    (353.0, 64.0),  # 207 St / Laity (Maple Ridge border)
    (400.9, 60.0),  # 216 St
    (443.1, 58.0),  # Downtown Haney
    (527.5, 32.0),  # Albion
    (696.3, 10.0),  # Whonnock
    (775.0, 0.0),  # Ruskin / Mission
]
# Back-compat alias for MR shoreline helpers.
MR_LOUGHEED_CTRL = LOUGHEED_CTRL

# Compact proportionate Y-scale (Surrey plate).
AVE_Y_ANCHORS: list[tuple[float, float]] = [
    (104.0, 0.0),
    (88.0, -42.2),
    (72.0, -84.4),
    (56.0, -168.8),
    (32.0, -211.0),
    (16.0, -232.0),
    (0.0, -274.2),
]

X_BORDER = 295.4  # 196 St / Surrey–Langley
X_EAST = 717.4  # 276 St / Abbotsford
X_SCOTT = -84.4  # Scott Rd / 120 St / Surrey–Delta (GIS target X≈-79.8)
X_WEST = -465.0  # Tsawwassen Ferry Terminal tip
Y_BORDER = -274.2  # 0 Ave / US border (Surrey)
Y_POINT_ROBERTS = -365.0  # 56 St & 0 Ave / Point Roberts

# Delta street X anchors (56 St corridor + North Delta collectors).
DELTA_ST_X: dict[int, float] = {
    56: -316.5,
    64: -316.5 + UNITS_PER_MILE,  # -274.3
    72: -316.5 + 2 * UNITS_PER_MILE,  # -232.1
    80: -316.5 + 3 * UNITS_PER_MILE,  # -189.9
    88: -316.5 + 4 * UNITS_PER_MILE,  # -147.7
    96: -316.5 + 5 * UNITS_PER_MILE,  # -105.5
    104: -168.8,  # Hwy 91 / Burns Bog south interchange
    112: -126.6,
    116: -105.5,
}

# Burns Bog open zone — no grid roads (west of Hwy 91 corridor).
BOG_X0, BOG_X1 = -250.0, -145.0
BOG_Y0, BOG_Y1 = -180.0, -110.0

# Hwy 91 corridor polyline (Alex Fraser → Nordel → Hwy 99).
HWY91_POLY: list[tuple[float, float]] = [
    (-116.0, -35.0),
    (-116.0, -64.0),
    (-126.6, -105.5),
    (-142.0, -145.0),
    (-168.8, -190.0),
]

# Tsawwassen N–S bounding arterials.
TSW_WEST = -335.0  # English Bluff Rd / 52 St
TSW_EAST = -302.0  # 53A St / Boundary Bay Rd
TSW_Y0 = -275.0
TSW_Y1 = -362.0  # include 1 Ave

# Richmond / Lulu Island — 1-mile arterial grid (42.2 spacing).
# Global offset vs Whalley: ΔX=-115, ΔY=+20 (keeps a Fraser river buffer vs Delta/Surrey).
RICH_NS_X: dict[str, float] = {
    "westwater": -510.0,
    "no_1": -495.0,  # Railway Ave / No. 1 Rd
    "no_2": -473.7,
    "gilbert": -452.6,  # Minoru / Gilbert (City Centre collector)
    "no_3": -431.5,  # Downtown spine
    "garden_city": -410.4,
    "no_4": -389.3,
    "shell": -368.2,
    "no_5": -347.1,  # Knight St corridor
    "no_6": -304.9,
    "no_7": -262.7,
    "no_8": -220.5,
}
RICH_EW_Y: dict[str, float] = {
    "bridgeport": 41.1,
    "cambie": 20.0,
    "westminster": -1.1,
    "granville": -22.2,
    "blundell": -43.3,
    "francis": -64.4,
    "williams": -85.5,
    "steveston": -106.6,
    "moncton": -112.0,
    "alderbridge": 9.5,
    "lansdowne": 4.2,
}
Y_STEVESTON = RICH_EW_Y["steveston"]
Y_RIVER_W = 62.2  # River Rd at No. 1 / Oak St Bridge latitude
Y_RIVER_NO2 = 35.0  # River Rd at No. 2 Rd
# Eastern tip must stay west of this X (open river gap vs Scott Rd X=-84.4).
RICH_X_EAST_LIMIT = -128.0
QUEENSBOROUGH = (-128.0, 30.0)  # Hwy 91A / Richmond east tip

# Vancouver / UBC — 2× Whalley plate, north of the North Arm Fraser.
# Major N–S arterials ≈ 21.1 units (0.5 mi) apart; Boundary Rd = east edge.
VAN_NS_X: dict[str, float] = {
    "ubc_tip": -615.0,
    "wesbrook": -595.0,
    "blanca": -585.0,  # UBC / Point Grey border
    "dunbar": -542.8,
    "macdonald": -511.2,
    "arbutus": -490.0,
    "granville": -458.5,  # Hwy 99 North
    "oak": -431.5,  # Hwy 99 South / Oak St Bridge
    "cambie": -410.4,
    "main": -389.3,
    "fraser": -368.2,
    "knight": -347.1,  # Knight St Bridge / Clark Dr
    "victoria": -326.0,  # Victoria / Commercial
    "nanaimo": -304.9,
    "renfrew": -262.7,
    "rupert": -220.5,
    "joyce": -199.0,
    "boundary": -178.0,  # Vancouver east edge
}
VAN_EW_Y: dict[str, float] = {
    "marine": 90.0,  # SW / SE Marine Drive (south waterfront spine)
    "70th": 100.0,  # Hwy 99 Oak → Granville transfer
    "49th": 121.6,
    "41st": 142.7,
    "king_edward": 174.3,  # 25th Ave
    "16th": 195.4,
    "grandview": 206.0,  # Grandview Hwy / 12th Ave
    "university": 206.0,  # University Blvd (UBC)
    "broadway": 216.5,  # 9th Ave central corridor
    "chancellor": 222.0,  # UBC West 4th / Chancellor Blvd
    "ave_4th": 227.0,  # West 4th / West 2nd / Great Northern Way
    "false_creek_s": 225.0,
    "terminal": 236.0,  # Terminal Ave / 1st Ave (False Creek Flats)
    "false_creek_n": 240.0,
    "downtown_s": 245.0,
    "prior": 248.0,  # Prior / Venables / Terminal north
    "hastings": 269.0,  # Hwy 7A north waterfront arterial
    "waterfront": 275.0,  # Port / Burrard Inlet south shore
    "burrard_n": 290.0,
}
# False Creek open water — bridge / viaduct spines only (no local stubs).
# Flats east of Quebec / Main keep Terminal Ave + grid.
FC_X0, FC_X1 = -475.0, -400.0
FC_Y0, FC_Y1 = 230.0, 246.0
X_QUEBEC = -398.0
Y_4TH = 227.0
Y_TERMINAL = 236.0
Y_VENABLES = 248.0  # Clark / Terminal–Venables band
Y_MARINE = VAN_EW_Y["marine"]
X_BOUNDARY = VAN_NS_X["boundary"]
# Downtown Vancouver peninsula — dual grid (~42° CCW core + orthogonal DTES).
# Avenues (Georgia-parallel) NW–SE @ -42°; cross-streets (Burrard-parallel) SW–NE @ +48°.
DT_AVE_ANGLE = -42.0
DT_CROSS_ANGLE = 48.0  # == AVE + 90°
DT_ORIGIN = (-445.0, 265.0)
# Bridge abutments (False Creek north shore) — downtown streets snap here.
BURRARD_ABUT = (-468.0, 252.0)
GRANVILLE_ABUT = (-452.0, 248.0)
CAMBIE_ABUT = (-420.0, 246.0)
X_GORE = -378.0
X_PRINCESS = -368.0
X_HEATLEY = -357.0
Y_PENDER_E = 263.0
Y_PRIOR = 252.0  # Prior St / Georgia Viaduct east
Y_CORDOVA_E = 272.0


def _shift_pt(
    pt: tuple[float, float],
    angle_deg: float,
    dist: float,
) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return (pt[0] + dist * math.cos(a), pt[1] + dist * math.sin(a))


# False Creek bridges — abutments match downtown cross-street south ends.
BURRARD_BRIDGE_CTRL: list[tuple[float, float]] = [
    BURRARD_ABUT,
    (-478.0, 227.0),
    (-486.0, 216.5),
    (-490.0, 195.4),  # Arbutus / Kitsilano landing
]
GRANVILLE_BRIDGE_CTRL: list[tuple[float, float]] = [
    GRANVILLE_ABUT,
    (-458.5, 227.0),
    (-458.5, 216.5),  # vertical Granville @ Broadway
]
CAMBIE_BRIDGE_CTRL: list[tuple[float, float]] = [
    CAMBIE_ABUT,
    (-410.4, 227.0),
    (-410.4, 216.5),  # vertical Cambie @ Broadway
]
# Marine Drive NW curve control (Boundary → UBC / NW Marine).
MARINE_CTRL: list[tuple[float, float]] = [
    (-178.0, 90.0),
    (-347.1, 90.0),
    (-431.5, 90.0),
    (-458.5, 90.0),
    (-490.0, 100.0),
    (-542.8, 135.0),
    (-585.0, 185.0),
    (-610.0, 225.0),
]
# Kingsway diagonal (Main & Broadway → Boundary / Joyce).
KINGSWAY_CTRL: list[tuple[float, float]] = [
    (-389.3, 216.5),
    (-368.2, 202.0),
    (-347.1, 188.0),
    (-326.0, 174.0),
    (-304.9, 160.0),
    (-262.7, 145.0),
    (-220.5, 135.0),
    (-199.0, 130.0),
    (-178.0, 125.0),
]
# Hwy 1 East Van → Ironworkers Memorial Bridge north approach.
HWY1_VAN_CTRL: list[tuple[float, float]] = [
    (-178.0, 248.0),
    (-220.5, 255.0),
    (-245.0, 269.0),
    (-255.0, 292.0),
]

# North Vancouver — north of Burrard Inlet (roads only, Z = 0).
# Lonsdale X=-431.5 aligns with Vancouver Oak / Richmond No. 3.
# Southern waterfront (Marine / Esplanade) stays north of the open channel
# (Vancouver Hastings / Cordova Y≈+269–285 → NV Marine Y≈+345–375).
NV_NS_X: dict[str, float] = {
    "west_van_border": -640.0,
    "capilano_n": -615.0,  # Capilano Suspension Bridge / Cleveland Dam
    "edgemont": -610.0,
    "capilano": -585.0,  # Capilano Rd / Hwy 1 interchange
    "marine_w": -542.8,  # SW Marine / Keith west hook
    "westview": -495.0,
    "jones": -465.0,
    "lonsdale": -431.5,  # Downtown CNV spine
    "grand": -395.0,  # Grand Boulevard
    "brooksbank": -316.5,  # Brooksbank / Queens / Lynn Valley Rd
    "mountain": -274.3,  # Mountain Highway
    "main": -255.0,  # Main St / Ironworkers north landing
    "seymour_rd": -105.5,  # Mount Seymour Road / Parkgate
    "indian_river": 0.0,
    "deep_cove": 26.4,
    "gallant": 42.2,  # Deep Cove tip / Panorama
}
NV_EW_Y: dict[str, float] = {
    "lions_gate_s": 325.0,  # Stanley Park / Lions Gate south abutment
    "marine": 345.0,  # SW / SE Marine Drive / Esplanade
    "main_st": 355.0,  # Main St / Mt Seymour Pkwy / Hwy 1 exit 23
    "third": 358.7,  # West / East 3rd Street
    "keith": 370.0,  # West / East Keith Road
    "thirteenth": 379.7,  # West / East 13th Street
    "lynn_hwy1": 380.0,  # Hwy 1 @ Lynn Valley Rd
    "queens": 386.0,  # West / East Queens Road
    "hwy1_lonsdale": 395.0,  # Upper Levels @ Lonsdale / Capilano
    "twenty_ninth": 410.0,  # West / East 29th Street / Westview @ Hwy 1
    "edgemont": 425.0,
    "lynn_centre": 435.0,  # Lynn Valley Town Centre
    "capilano_dam": 465.0,  # Capilano Dam / Grouse / Mountain Hwy north
    "seymour_resort": 475.0,  # Mount Seymour ski resort loop
}
# Hwy 1 Upper Levels — Ironworkers north approach → West Vancouver border.
HWY1_NV_CTRL: list[tuple[float, float]] = [
    (-255.0, 292.0),  # Vancouver / Ironworkers south handoff
    (-225.0, 335.0),  # Inlet mid-span curve NE
    (-255.0, 355.0),  # Main St / exit 23–24
    (-316.5, 380.0),  # Lynn Valley Rd
    (-431.5, 395.0),  # Lonsdale Ave
    (-495.0, 410.0),  # Westview Dr
    (-585.0, 395.0),  # Capilano Rd interchange
    (-640.0, 420.0),  # West Vancouver border → Horseshoe Bay
]
# Lions Gate Bridge approach (Hwy 99) — Stanley Park tip → Marine Drive.
LIONS_GATE_CTRL: list[tuple[float, float]] = [
    (-495.0, 325.0),  # Vancouver / Stanley Park northern causeway
    (-500.0, 335.0),
    (-505.0, 345.0),  # Marine Drive landing
]
# Capilano Road — Marine Drive → Capilano Dam / Suspension Bridge loop.
CAPILANO_RD_CTRL: list[tuple[float, float]] = [
    (-505.0, 345.0),  # Marine Drive
    (-540.0, 370.0),
    (-585.0, 395.0),  # Hwy 1 interchange
    (-610.0, 425.0),  # Edgemont Blvd
    (-615.0, 450.0),
    (-615.0, 465.0),  # Capilano Suspension Bridge / Cleveland Dam
    (-605.0, 470.0),
    (-595.0, 465.0),
    (-605.0, 455.0),
    (-615.0, 465.0),
]
# Marine Drive / Esplanade — West Van border → Lions Gate → Main / Hwy 1.
MARINE_NV_CTRL: list[tuple[float, float]] = [
    (-610.0, 345.0),  # West Vancouver border (Hwy 99 / Marine handoff)
    (-542.8, 345.0),  # Keith west hook
    (-505.0, 345.0),  # Lions Gate / Capilano landing
    (-495.0, 345.0),  # Westview
    (-465.0, 345.0),  # Jones
    (-431.5, 345.0),  # Lonsdale / Esplanade
    (-395.0, 345.0),  # Grand Boulevard
    (-316.5, 350.0),  # Brooksbank approach
    (-274.3, 353.0),  # Mountain Hwy
    (-255.0, 355.0),  # Main St / Hwy 1
]
# Keith Road — Marine west → Lonsdale → Hwy 1 / Main.
KEITH_RD_CTRL: list[tuple[float, float]] = [
    (-542.8, 345.0),  # Marine Drive
    (-520.0, 358.0),
    (-495.0, 370.0),  # Westview
    (-465.0, 370.0),  # Jones
    (-431.5, 370.0),  # Lonsdale
    (-395.0, 370.0),  # Grand
    (-316.5, 370.0),  # Brooksbank
    (-274.3, 370.0),  # Mountain Hwy
    (-255.0, 355.0),  # Hwy 1 / Main
]
# Mount Seymour Parkway — Ironworkers north → Deep Cove tip.
MT_SEYMOUR_PKWY_CTRL: list[tuple[float, float]] = [
    (-255.0, 355.0),  # Main St / Hwy 1
    (-105.5, 355.0),  # Parkgate / Mount Seymour Rd
    (0.0, 355.0),  # Indian River Dr
    (26.4, 355.0),  # Deep Cove Road
    (42.2, 355.0),  # Gallant / Panorama
    (48.0, 365.0),
    (42.2, 375.0),
    (26.4, 370.0),
    (26.4, 355.0),
]

# Burnaby — 2× Whalley plate (Boundary → North Rd). Roads only, Z = 0.
# N–S arterials ≈ 21.1 units (0.5 mi) apart west of Gaglardi.
BN_NS_X: dict[str, float] = {
    "boundary": -178.0,  # Vancouver / Burnaby border
    "gilmore": -156.9,
    "alpha": -142.0,  # Brentwood collector
    "willingdon": -135.8,  # Metrotown → Brentwood spine
    "beta": -129.0,  # Brentwood collector
    "royal_oak": -114.7,
    "nelson": -93.6,
    "sperling": -72.5,
    "kensington": -51.4,
    "gaglardi": -20.0,  # Hwy 1 → SFU spine
    "cariboo": 10.0,
    "brunette_x": 35.0,  # Brunette / Cape Horn band
    "north_rd": 52.0,  # Burnaby / Coquitlam border
}
BN_EW_Y: dict[str, float] = {
    "north_fraser": 82.0,  # Big Bend industrial parallel
    "marine": 88.0,  # Marine Way / SE Marine flats
    "rumble": 108.0,
    "imperial": 120.0,
    "oakland": 145.0,  # Deer Lake south edge
    "canada_way_mid": 160.0,  # Deer Lake / City Hall
    "lougheed_w": 216.5,  # Broadway seam through Brentwood
    "broadway_e": 215.0,  # Production / Austin band
    "hastings": 269.0,  # Hwy 7A North Burnaby
    "burrard": 282.0,  # Burrard Inlet north clip
}
# 10th Avenue — Burnaby / New Westminster tilted SE border.
BN_10TH_CTRL: list[tuple[float, float]] = [
    (-58.0, 100.0),  # Kingsway / Edmonds
    (-48.0, 103.5),  # 12th St
    (-38.0, 107.0),  # 8th St
    (-31.0, 109.5),  # 6th St
    (-20.0, 113.5),  # McBride / Canada Way
    (-8.0, 117.5),  # Cumberland
    (10.0, 115.0),  # toward Cariboo
]
# Marine Way → Stewardson handoff (New West takes over east of this).
MARINE_STEWARDSON_CTRL: list[tuple[float, float]] = [
    (-178.0, 90.0),  # Boundary / SE Marine (Vancouver seam)
    (-156.9, 88.0),  # Gilmore
    (-135.8, 88.0),  # Willingdon
    (-114.7, 88.0),  # Royal Oak
    (-93.6, 86.0),  # Nelson
    (-85.0, 86.0),  # Byrne Rd curve
    (-55.0, 72.0),  # Stewardson / 20th St handoff
]
# Kingsway Burnaby (wider ~0.65) — Boundary → 12th St / 10th Ave handoff.
KINGSWAY_BN_CTRL: list[tuple[float, float]] = [
    (-178.0, 125.0),  # Boundary (Vancouver seam)
    (-135.8, 118.0),  # Willingdon / Metrotown
    (-114.7, 114.0),  # Royal Oak
    (-93.6, 110.0),  # Nelson
    (-72.5, 104.0),  # Sperling / Edmonds
    (-65.0, 100.0),  # 12th St / New West entry
]
# Canada Way (wider ~0.6) — Grandview / Boundary → New West.
CANADA_WAY_CTRL: list[tuple[float, float]] = [
    (-178.0, 206.0),  # Boundary & Grandview
    (-156.9, 195.0),  # Gilmore
    (-135.8, 185.0),  # Willingdon
    (-114.7, 175.0),  # Royal Oak
    (-85.0, 160.0),  # Deer Lake / City Hall
    (-72.5, 150.0),  # Sperling (south of Burnaby Lake)
    (-51.4, 140.0),  # Kensington
    (-25.0, 115.0),  # New Westminster entry
]
# Hwy 1 Burnaby → Brunette / Cape Horn handoff (Coquitlam owns Port Mann leg).
HWY1_BN_CTRL: list[tuple[float, float]] = [
    (-178.0, 248.0),  # Boundary (Vancouver seam)
    (-156.9, 238.0),  # Gilmore
    (-135.8, 228.0),  # Willingdon
    (-51.4, 195.0),  # Sprott / Kensington
    (-20.0, 180.0),  # Gaglardi Way
    (10.0, 165.0),  # Cariboo Rd
    (35.0, 125.0),  # Brunette / Cape Horn (Coquitlam seam)
]
# Lougheed Hwy (Hwy 7, wider ~0.65) → North Rd (Brunette owned by New West).
LOUGHEED_BN_CTRL: list[tuple[float, float]] = [
    (-178.0, 216.5),  # Boundary / Broadway
    (-135.8, 216.5),  # Brentwood
    (-72.5, 216.5),  # Sperling
    (-20.0, 200.0),  # Production Way / Gaglardi
    (52.0, 185.0),  # Lougheed Town Centre / North Rd
]
# Hastings St → Barnet Hwy (north waterfront spine).
HASTINGS_BARNET_CTRL: list[tuple[float, float]] = [
    (-178.0, 269.0),  # Boundary (Vancouver seam)
    (-135.8, 269.0),  # Willingdon / Burnaby Heights
    (-72.5, 269.0),  # Sperling
    (-51.4, 269.0),  # Kensington
    (-15.0, 262.0),  # Burnaby Mountain base / Inlet Dr
    (15.0, 268.0),  # Barnet Hwy north flank
    (52.0, 268.0),  # North Rd / Clarke Rd
]
# Gaglardi Way (wider ~0.6) — Hwy 1 → SFU University Drive.
GAGLARDI_CTRL: list[tuple[float, float]] = [
    (-20.0, 180.0),  # Cariboo / Hwy 1
    (-20.0, 200.0),  # Lougheed
    (-20.0, 218.0),  # Broadway
    (-10.0, 238.0),  # Burnaby Mountain curve
    (10.0, 255.0),  # SFU University Drive
]
# Burnaby Mountain Parkway — Broadway east → SFU.
BN_MTN_PKWY_CTRL: list[tuple[float, float]] = [
    (20.0, 220.0),
    (15.0, 235.0),
    (10.0, 255.0),
]
# Park / lake voids — no cross-street fill (Sperling / Cariboo may skirt Burnaby Lake).
BN_VOID_BURNABY_LAKE = (-68.0, 165.0, 15.0, 205.0)
BN_VOID_DEER_LAKE = (-105.0, 145.0, -75.0, 168.0)
BN_VOID_CENTRAL_PARK = (-178.0, 125.0, -152.0, 152.0)
BN_PARK_VOIDS: tuple[tuple[float, float, float, float], ...] = (
    BN_VOID_BURNABY_LAKE,
    BN_VOID_DEER_LAKE,
    BN_VOID_CENTRAL_PARK,
)
# N–S shafts allowed through the Burnaby Lake void (Sperling west / Cariboo east).
BN_LAKE_CROSS_XS = frozenset(
    {
        BN_NS_X["sperling"],
        BN_NS_X["cariboo"],
    }
)
X_NORTH_RD = BN_NS_X["north_rd"]
Y_BN_BURRARD = BN_EW_Y["burrard"]
Y_BN_MARINE = BN_EW_Y["marine"]
SFU_CORE = (10.0, 255.0)

# =====================================================================
# Mainland New Westminster — strict tilted grid (~32° river-parallel /
# ~122° hill-climb). Zero axis-aligned segments inside the wipe box.
# =====================================================================
NW_AVE_ANGLE = 32.0  # NE–SW avenues (river-parallel)
NW_CROSS_ANGLE = 122.0  # NW–SE cross-streets (hill-climb)
NW_WIPE_X0, NW_WIPE_X1 = -55.0, 28.0
NW_WIPE_Y0, NW_WIPE_Y1 = 48.0, 115.0
# 10th Avenue — full Burnaby / New West tilted border (alias of BN_10TH_CTRL).
NW_10TH_CTRL = BN_10TH_CTRL
# Front St / Quayside — immediate waterfront edge.
NW_FRONT_CTRL: list[tuple[float, float]] = [
    (-42.0, 49.0),
    (-24.0, 52.5),  # 8th St
    (-8.0, 58.0),  # Pattullo / Begbie
]
# Columbia St → East Columbia (Downtown → Sapperton).
NW_COLUMBIA_CTRL: list[tuple[float, float]] = [
    (-46.0, 52.5),  # Stewardson / 14th St
    (-38.0, 54.5),  # 12th St
    (-25.0, 57.5),  # 8th St
    (-18.0, 60.0),  # 6th St
    (-5.0, 63.5),  # McBride / Pattullo
    (8.0, 76.0),  # Royal Columbian / Sapperton
    (22.0, 94.0),  # Brunette / North Road
]
# Royal Avenue (wider ~0.6) — Stewardson → Sapperton.
NW_ROYAL_CTRL: list[tuple[float, float]] = [
    (-49.0, 58.0),  # Stewardson
    (-41.0, 60.5),  # 12th St
    (-28.0, 64.0),  # 8th St
    (-21.0, 66.5),  # 6th St
    (-8.0, 70.5),  # McBride
    (12.0, 86.0),  # Sapperton → East Columbia
]
# 6th Avenue (wider ~0.55) — Uptown → Cumberland.
NW_6TH_AVE_CTRL: list[tuple[float, float]] = [
    (-56.0, 74.0),  # 20th St / Marine Way
    (-44.0, 79.0),  # 12th St
    (-32.0, 83.5),  # 8th St
    (-25.0, 86.5),  # 6th St
    (-13.0, 91.0),  # McBride
    (-2.0, 98.0),  # Cumberland / Richmond
    (15.0, 108.0),  # toward Cariboo
]
# 8th Avenue — upper Uptown / Moody Park.
NW_8TH_AVE_CTRL: list[tuple[float, float]] = [
    (-58.0, 82.0),  # 20th St
    (-46.0, 87.0),  # 12th St
    (-35.0, 92.0),  # 8th St
    (-28.0, 95.0),  # 6th St
    (-16.0, 100.0),  # McBride
    (-4.0, 106.0),  # Cumberland
]
# Stewardson Way — Queensborough Bridge → Columbia (western entry).
NW_STEWARDSON_CTRL: list[tuple[float, float]] = [
    (-62.0, 52.0),  # Queensborough Bridge north approach
    (-55.0, 62.0),  # Hwy 91A / 20th snap
    (-52.0, 64.0),  # Stewardson
    (-46.0, 52.5),  # Columbia / 14th St
]
# 20th Street — 10th Ave → Stewardson (NW–SE).
NW_20TH_CTRL: list[tuple[float, float]] = [
    (-58.0, 100.0),  # 10th Ave / Kingsway
    (-57.0, 88.0),  # 8th Ave
    (-56.0, 74.0),  # 6th Ave
    (-52.0, 64.0),  # Stewardson
]
# 14th Street — 8th Ave → Columbia.
NW_14TH_CTRL: list[tuple[float, float]] = [
    (-50.0, 90.0),  # 8th Ave
    (-48.0, 74.0),  # 6th Ave
    (-46.0, 52.5),  # Stewardson / Columbia
]
# 12th Street — Kingsway / 10th Ave → Columbia.
NW_12TH_CTRL: list[tuple[float, float]] = [
    (-65.0, 100.0),  # Burnaby Kingsway handoff
    (-48.0, 103.5),  # 10th Ave
    (-46.0, 92.0),  # 8th Ave
    (-44.0, 79.0),  # 6th Ave
    (-41.0, 60.5),  # Royal Ave
    (-38.0, 54.5),  # Columbia
]
# 10th Street — Brow of the Hill.
NW_10TH_ST_CTRL: list[tuple[float, float]] = [
    (-43.0, 105.0),  # 10th Ave
    (-40.0, 92.0),  # 8th Ave
    (-38.0, 81.0),  # 6th Ave
    (-34.0, 62.0),  # Royal Ave
    (-31.5, 56.0),  # Columbia
]
# 8th Street (wider ~0.5) — 10th Ave → Front.
NW_8TH_ST_CTRL: list[tuple[float, float]] = [
    (-38.0, 107.0),  # 10th Ave
    (-35.0, 95.0),  # 8th Ave
    (-32.0, 83.5),  # 6th Ave
    (-28.0, 64.0),  # Royal Ave
    (-25.0, 57.5),  # Columbia
    (-24.0, 52.5),  # Front
]
# 6th Street (wider ~0.55) — 10th Ave → Front.
NW_6TH_ST_CTRL: list[tuple[float, float]] = [
    (-31.0, 109.5),  # 10th Ave
    (-28.0, 97.0),  # 8th Ave
    (-25.0, 86.5),  # 6th Ave
    (-21.0, 66.5),  # Royal Ave
    (-18.0, 60.0),  # Columbia
    (-17.0, 55.0),  # Front
]
# McBride Blvd (wider ~0.7) — Canada Way → Pattullo / Surrey.
NW_MCBRIDE_CTRL: list[tuple[float, float]] = [
    (-25.0, 115.0),  # Burnaby Canada Way handoff
    (-20.0, 113.5),  # 10th Ave
    (-16.0, 100.0),  # 8th Ave
    (-13.0, 91.0),  # 6th Ave
    (-8.0, 70.5),  # Royal Ave
    (-5.0, 63.5),  # Columbia
    (0.0, 32.0),  # Surrey Pattullo approach
]
# Brunette Ave (wider ~0.65) — Sapperton → Hwy 1 / Lougheed.
NW_BRUNETTE_CTRL: list[tuple[float, float]] = [
    (14.0, 88.0),  # East Columbia
    (18.0, 102.0),  # Sapperton valley
    (35.0, 125.0),  # Hwy 1 / Lougheed
]
# Hwy 91A Queensborough Bridge continuation (Richmond tip → Stewardson).
HWY91A_QB_CTRL: list[tuple[float, float]] = [
    (-128.0, 30.0),  # Richmond / Queensborough tip
    (-95.0, 41.0),
    (-72.0, 44.0),
    (-65.0, 48.0),  # Bridge mid
    (-55.0, 62.0),  # Stewardson / 20th St snap
]
# Queensborough peninsula (~18° island tilt).
QB_EWEN_CTRL: list[tuple[float, float]] = [
    (-125.0, 31.0),
    (-95.0, 35.5),
    (-72.0, 39.0),
    (-52.0, 43.0),
]
QB_BOYD_CTRL: list[tuple[float, float]] = [
    (-95.0, 46.0),
    (-68.0, 50.0),
]
QB_SALTER_CTRL: list[tuple[float, float]] = [
    (-95.0, 31.0),
    (-52.0, 39.0),
]
# Queensborough cross-street X anchors (tilted NW–SE connectors).
QB_CROSS_XS: tuple[float, ...] = (-115.0, -95.0, -82.0, -72.0, -60.0)

# Routes allowed to occupy the Mainland New Westminster wipe box.
_NW_BOX_KEEP = frozenset(
    {
        "nw_front_st",
        "nw_columbia_st",
        "nw_carnarvon_st",
        "nw_clarkson_st",
        "nw_royal_ave",
        "nw_queens_ave",
        "nw_3rd_ave",
        "nw_4th_ave",
        "nw_5th_ave",
        "nw_6th_ave",
        "nw_7th_ave",
        "nw_8th_ave",
        "nw_10th_ave",
        "nw_stewardson",
        "nw_20th_st",
        "nw_14th_st",
        "nw_12th_st",
        "nw_10th_st",
        "nw_8th_st",
        "nw_6th_st",
        "nw_4th_st",
        "nw_2nd_st",
        "nw_1st_st",
        "mcbride_blvd",
        "brunette_ave",
        "hwy91a",
        "marine_stewardson",
        "kingsway_bn",
        "canada_way",
    }
)
# Burnaby SE spines that terminate on 10th Ave (endpoints sit in the wipe AABB).
_BN_SE_KEEP_PREFIXES = (
    "sperling_ave",
    "kensington_ave",
    "cariboo_rd",
    "nelson_ave",
)

# =====================================================================
# Coquitlam — North Rd (Burnaby) → Pitt River Bridge / Port Mann (roads only).
# =====================================================================
CQ_NS_X: dict[str, float] = {
    "north_rd": 52.0,  # Burnaby border
    "blue_mountain": 68.0,
    "king_edward": 76.0,
    "schoolhouse": 84.0,
    "mariner": 105.0,
    "johnson": 112.0,
    "pinetree": 120.0,
    "coast_meridian": 155.0,
    "pitt_bridge": 175.0,  # Pitt Meadows seam
}
CQ_EW_Y: dict[str, float] = {
    "united": 92.0,
    "austin": 165.0,
    "lougheed_w": 185.0,  # North Rd seam
    "glen": 205.0,
    "como_lake": 215.0,
    "guildford": 215.0,
    "barnet_dew": 232.0,
    "clarke": 245.0,
    "david": 245.0,
}
# Hwy 1 Coquitlam — Brunette / Cape Horn → Port Mann → Surrey snap.
HWY1_CQ_CTRL: list[tuple[float, float]] = [
    (35.0, 125.0),  # Brunette interchange (Burnaby seam)
    (55.0, 115.0),  # Maillardville / Cape Horn
    (64.0, 42.2),  # Surrey Hwy 1 / Port Mann snap
]
# Lougheed Hwy (Hwy 7) — North Rd → Coquitlam Centre (PoCo continues east).
LOUGHEED_CQ_CTRL: list[tuple[float, float]] = [
    (52.0, 185.0),  # North Rd (Burnaby seam)
    (85.0, 185.0),  # Burquitlam / Austin Heights North
    (120.0, 195.0),  # Coquitlam Centre / Pinetree (PoCo seam)
]
# Barnet Hwy (Hwy 7A) — Port Moody → Coquitlam Centre.
BARNET_CQ_CTRL: list[tuple[float, float]] = [
    (95.0, 240.0),  # Port Moody / Dewdney Trunk entry
    (110.0, 225.0),  # Westwood Plateau foot
    (120.0, 195.0),  # Lougheed / Pinetree
]
# Mary Hill Bypass (Hwy 7B) — Cape Horn → PoCo west seam.
MARY_HILL_CTRL: list[tuple[float, float]] = [
    (62.0, 110.0),  # Hwy 1 / Lougheed Cape Horn
    (95.0, 95.0),
    (135.0, 82.0),  # Port Coquitlam seam
]
# Brunette Ave Coquitlam leg — Hwy 1 → Blue Mountain / Maillardville.
BRUNETTE_CQ_CTRL: list[tuple[float, float]] = [
    (35.0, 125.0),  # Hwy 1 / New West seam
    (58.0, 165.0),  # into Blue Mountain St
]
# United Boulevard — industrial riverfront spine.
UNITED_BLVD_CTRL: list[tuple[float, float]] = [
    (52.0, 105.0),  # Brunette / North Rd band
    (76.0, 95.0),  # King Edward St
    (105.0, 90.0),  # Mariner Way / Mary Hill
]
# Como Lake Ave — North Rd → Lougheed / Pinetree (curves SE past Mundy Park).
COMO_LAKE_CTRL: list[tuple[float, float]] = [
    (52.0, 215.0),  # North Rd
    (68.0, 215.0),  # Blue Mountain
    (84.0, 215.0),  # Schoolhouse
    (105.0, 205.0),  # Mundy Park south-east edge
    (120.0, 195.0),  # Lougheed / Pinetree
]
# Pinetree Way — Town Centre → Westwood Plateau loop.
PINETREE_CTRL: list[tuple[float, float]] = [
    (120.0, 195.0),  # Lougheed / Coquitlam Centre
    (120.0, 215.0),  # Guildford Way
    (120.0, 245.0),  # David Ave
    (110.0, 260.0),  # Westwood Plateau climb
    (100.0, 270.0),
    (95.0, 265.0),
    (105.0, 255.0),
    (120.0, 250.0),  # Plateau Blvd return
]
# Mundy Park open void — no internal grid (Mariner Way X=+105 is the east edge).
CQ_VOID_MUNDY = (92.0, 168.0, 104.5, 202.0)
CQ_PARK_VOIDS: tuple[tuple[float, float, float, float], ...] = (CQ_VOID_MUNDY,)
X_CQ_WEST = CQ_NS_X["north_rd"]
X_CQ_EAST = CQ_NS_X["pitt_bridge"]
Y_CQ_CLARKE = CQ_EW_Y["clarke"]

# =====================================================================
# Port Moody — U-shaped loop around Burrard Inlet tip (roads only, Z = 0).
# Snaps Burnaby North Rd / Barnet (X=+52) → Coquitlam Barnet (+95,+240) /
# Guildford (Johnson X=+112, Y=+215). Eastern Burrard Inlet tip stays open.
# =====================================================================
POMO_NS_X: dict[str, float] = {
    "north_rd": 52.0,  # Burnaby west border
    "cecile": 68.0,
    "clarke_merge": 76.0,  # Barnet / St Johns / Clarke Rd merge
    "moody": 82.0,  # Rocky Point / Murray start (eastern tip X)
    "moray": 88.0,
    "barnet_branch": 90.0,  # St Johns → Barnet Hwy east leg
    "suter": 94.0,
    "ioco_jct": 95.0,  # St Johns / Ioco / Ungless split
    "ungless": 96.0,
    "guildford_cq": 112.0,  # Coquitlam Guildford / Johnson seam
    "heritage": 112.0,
}
POMO_EW_Y: dict[str, float] = {
    "como_approach": 225.0,  # Moray → Coquitlam Como Lake band
    "glenayre_s": 228.0,
    "guildford_cq": 215.0,  # Coquitlam Guildford Way
    "guildford_approach": 220.0,
    "barnet_cq": 240.0,  # Coquitlam Barnet / Dewdney entry
    "clarke": 245.0,  # North Rd / Clarke Rd (Burnaby seam)
    "david": 245.0,
    "st_johns_w": 250.0,  # Clarke merge / Moody Centre
    "rocky_point": 252.0,  # south shore of Burrard Inlet tip
    "murray": 255.5,  # waterfront industrial / Brewery Row
    "reed_point": 258.0,  # College Park / Newport Dr band
    "newport": 258.0,
    "barnet_bn": 268.0,  # Burnaby Barnet / North Rd tip
    "ioco_jct": 268.0,
    "inlet_n": 275.0,  # north shore of Burrard Inlet tip
    "pleasantside": 280.0,
    "ravine": 280.0,
    "ioco_town": 286.0,
    "belcarra": 292.0,
    "anmore": 315.0,
}
# Open Burrard Inlet tip — no roads inside (U-shaped water gap ~15–22 units).
# South shore (Barnet / St Johns / Rocky Point Y≈+250–258) and north-shore Ioco
# (Y≥+274) stay outside; void is open water east of the North Rd land approaches.
# Rocky Point Y≈+252, Ioco / Pleasantside Y≈+275, eastern tip X≈+82.
POMO_VOID_INLET = (58.0, 259.0, 81.5, 274.0)
POMO_PARK_VOIDS: tuple[tuple[float, float, float, float], ...] = (POMO_VOID_INLET,)
# Barnet Hwy (Hwy 7A) — Burnaby North Rd tip → St Johns / Clarke merge.
# Stays on/south of the shoreline so the Inlet tip void remains open water.
BARNET_POMO_W_CTRL: list[tuple[float, float]] = [
    (52.0, 268.0),  # Burnaby Hastings/Barnet seam
    (54.0, 265.0),
    (56.0, 261.0),  # west of Inlet void
    (57.5, 258.2),  # drop south before void X band
    (62.0, 257.5),  # Reed Point approach
    (68.0, 256.0),  # College Park shoreline
    (72.0, 253.0),
    (76.0, 250.0),  # Clarke Rd / St Johns St
]
# St. Johns Street — main commercial spine wrapping the Inlet tip.
ST_JOHNS_CTRL: list[tuple[float, float]] = [
    (76.0, 250.0),  # Barnet / Clarke merge
    (85.0, 252.0),  # Rocky Point / Moody Centre
    (90.0, 252.0),  # Barnet Hwy east branch
    (94.0, 258.0),  # Suter Brook / Newport Village
    (95.0, 268.0),  # Ioco Rd / Ungless Way split
]
# Barnet Hwy eastern leg — St Johns → Coquitlam Barnet entry.
BARNET_POMO_E_CTRL: list[tuple[float, float]] = [
    (90.0, 252.0),  # branch off St Johns (east of Moody Centre)
    (92.5, 246.0),
    (95.0, 240.0),  # Coquitlam Barnet / Dewdney Trunk seam
]
# Ioco Road — north-shore peninsula spine (wider ~0.55).
IOCO_RD_CTRL: list[tuple[float, float]] = [
    (95.0, 268.0),  # St Johns / Murray / Ungless junction
    (85.0, 274.0),
    (75.0, 280.0),  # Pleasantside / Old Orchard
    (60.0, 284.0),
    (48.0, 286.0),  # Ioco Townsite
    (35.0, 290.0),
    (30.0, 292.0),  # Belcarra / Bedwell Bay approach
]
# Clarke Road — North Rd & Clarke → Barnet / St Johns merge (ridge).
CLARKE_RD_POMO_CTRL: list[tuple[float, float]] = [
    (52.0, 245.0),  # Burnaby / Coquitlam North Rd seam
    (64.0, 247.5),  # Seaview / Seaview Park
    (76.0, 250.0),  # Barnet / St Johns merge
]
# Murray Street — Rocky Point waterfront / Brewery Row (north of St Johns).
MURRAY_ST_CTRL: list[tuple[float, float]] = [
    (82.0, 255.0),  # Moody St / Rocky Point
    (88.0, 260.0),
    (94.0, 266.0),  # Suter Brook / Ioco Rd
]
# Guildford Way — Ioco / Ungless → Coquitlam Guildford / Johnson.
GUILDFORD_POMO_CTRL: list[tuple[float, float]] = [
    (96.0, 266.0),  # Ioco Rd / Ungless Way
    (100.0, 258.0),  # Newport Dr
    (108.0, 245.0),  # David Ave band
    (115.0, 220.0),  # southeast approach
    (112.0, 215.0),  # Coquitlam Guildford Way / Johnson St
]
# Ungless Way / Heritage Mountain Blvd — hillside climb north of Ioco.
UNGLESS_HERITAGE_CTRL: list[tuple[float, float]] = [
    (96.0, 268.0),  # Ioco Rd
    (102.0, 282.0),
    (112.0, 295.0),  # Heritage Mountain crest
]
# Moray Street — St Johns hill climb → Coquitlam Como Lake corridor.
MORAY_ST_CTRL: list[tuple[float, float]] = [
    (88.0, 251.0),  # St Johns St
    (87.0, 240.0),  # crosses Barnet east approach
    (86.0, 225.0),  # Como Lake Ave approach
]
# Clarke Street — Moody Centre historic spine (3.0 units south of St Johns).
CLARKE_ST_POMO_CTRL: list[tuple[float, float]] = [
    (76.0, 247.0),
    (90.0, 249.0),
]
# Spring Street — parallel historic collector south of Clarke Street.
SPRING_ST_POMO_CTRL: list[tuple[float, float]] = [
    (76.0, 244.0),
    (90.0, 246.0),
]
# Sunnyside Road — Anmore north spine off Ioco.
SUNNYSIDE_RD_CTRL: list[tuple[float, float]] = [
    (78.0, 280.0),  # Ioco Rd
    (77.0, 295.0),
    (76.0, 315.0),  # Buntzen Lake / Anmore
]
# East Road / 1st Avenue — Anmore northeast branch.
EAST_RD_ANMORE_CTRL: list[tuple[float, float]] = [
    (78.0, 300.0),  # Sunnyside
    (88.0, 305.0),
    (95.0, 310.0),
]
X_POMO_WEST = POMO_NS_X["north_rd"]
X_POMO_TIP = POMO_NS_X["moody"]
Y_POMO_CLARKE = POMO_EW_Y["clarke"]
Y_POMO_BARNET_BN = POMO_EW_Y["barnet_bn"]

# =====================================================================
# Port Coquitlam — Coquitlam River → Pitt River (roads only, Z = 0).
# =====================================================================
PC_NS_X: dict[str, float] = {
    "westwood": 132.0,  # Coquitlam River / west border
    "shaughnessy": 142.0,
    "coast_meridian": 155.0,
    "ottawa": 168.0,
    "fremont": 188.0,  # Burns Rd / Fremont Connector
    "pitt_bridge": 175.0,  # Pitt Meadows seam
}
PC_EW_Y: dict[str, float] = {
    "citadel": 85.0,
    "mary_hill": 82.0,
    "kingsway": 115.0,
    "wilson": 123.0,
    "mcallister": 128.0,
    "dominion": 135.0,
    "lougheed_dt": 145.0,  # Shaughnessy / Downtown crossing
    "prairie": 165.0,
    "nicola": 185.0,
    "lincoln": 205.0,
    "guildford": 215.0,
}
# Lougheed Hwy (Hwy 7) — Coquitlam Centre → Pitt River Bridge.
LOUGHEED_PC_CTRL: list[tuple[float, float]] = [
    (120.0, 195.0),  # Coquitlam Centre / Pinetree seam
    (130.0, 165.0),  # Westwood St
    (142.0, 145.0),  # Downtown PoCo / Shaughnessy
    (165.0, 105.0),  # Ottawa St / Dominion Triangle
    (172.0, 70.0),  # Mary Hill merge west of bridge
    (175.0, 68.0),  # Pitt River Bridge (Pitt Meadows seam)
]
# Mary Hill Bypass (Hwy 7B) — Coquitlam seam → Lougheed merge.
MARY_HILL_PC_CTRL: list[tuple[float, float]] = [
    (135.0, 82.0),  # Coquitlam seam
    (152.0, 74.0),  # southern Mary Hill edge
    (172.0, 70.0),  # merge to Lougheed
]
# Fremont Connector / Burns Rd — Lougheed → Victoria / Cedar (riverfront X≈188).
FREMONT_CTRL: list[tuple[float, float]] = [
    (168.0, 95.0),  # branch off Lougheed
    (178.0, 112.0),
    (188.0, 135.0),  # Dominion Ave
    (188.0, 165.0),  # Prairie Ave
    (190.0, 185.0),
    (192.0, 205.0),  # Victoria Dr / Cedar Dr
]
# Pitt River Rd — Shaughnessy / Kingsway → Lougheed / Mary Hill.
PITT_RIVER_RD_CTRL: list[tuple[float, float]] = [
    (142.0, 115.0),  # Shaughnessy / Kingsway
    (152.0, 95.0),
    (165.0, 82.0),
    (170.0, 72.0),  # near Pitt River Bridge approach
]
# Citadel Drive — Mary Hill Bypass → Pitt River Rd (southern ridge).
CITADEL_CTRL: list[tuple[float, float]] = [
    (145.0, 78.0),  # Mary Hill Bypass
    (155.0, 88.0),
    (165.0, 85.0),  # Pitt River Rd
]
# Lincoln Ave / Victoria Dr — Guildford Way seam → Cedar / Fremont.
LINCOLN_PC_CTRL: list[tuple[float, float]] = [
    (132.0, 215.0),  # Westwood / Guildford seam
    (145.0, 215.0),  # Guildford Way east tip
    (155.0, 205.0),  # Coast Meridian
    (192.0, 205.0),  # Cedar Dr / Fremont
]


def pc_pitt_x(y: float) -> float:
    """Western bank of the Pitt River (PoCo east clip) at Y."""
    # North bank ~X=+195 (Fremont / Burns); SW to Pitt Bridge (+175, +68).
    y_n, x_n = 205.0, 195.0
    y_s, x_s = 68.0, 175.0
    if y >= y_n:
        return x_n
    if y <= y_s:
        return x_s
    t = (y_n - y) / (y_n - y_s)
    return x_n + t * (x_s - x_n)


def ave_y(ave: float) -> float:
    """Interpolate compact Surrey Y anchors (104 Ave = 0)."""
    if ave >= AVE_Y_ANCHORS[0][0]:
        return AVE_Y_ANCHORS[0][1]
    if ave <= AVE_Y_ANCHORS[-1][0]:
        return AVE_Y_ANCHORS[-1][1]
    for i in range(len(AVE_Y_ANCHORS) - 1):
        a0, y0 = AVE_Y_ANCHORS[i]
        a1, y1 = AVE_Y_ANCHORS[i + 1]
        if a1 <= ave <= a0:
            t = (a0 - ave) / (a0 - a1)
            return y0 + t * (y1 - y0)
    return 0.0


def st_x(street: int) -> float:
    return STREET_X[street]


def _interp_poly_y(controls: list[tuple[float, float]], x: float) -> float:
    """Linear Y along an eastbound control polyline at X."""
    if x <= controls[0][0]:
        return controls[0][1]
    if x >= controls[-1][0]:
        return controls[-1][1]
    for i in range(len(controls) - 1):
        x0, y0 = controls[i]
        x1, y1 = controls[i + 1]
        if x0 <= x <= x1:
            if abs(x1 - x0) < 1e-9:
                return y0
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return controls[-1][1]


def mr_river_y(x: float) -> float:
    """River Road / southern shoreline Y at X (Maple Ridge)."""
    return _interp_poly_y(MR_RIVER_CTRL, x)


def mr_lougheed_y(x: float) -> float:
    """Lougheed Hwy (Hwy 7) Y at X."""
    return _interp_poly_y(MR_LOUGHEED_CTRL, x)


def _mr_rural_north_y(x: float) -> float:
    """Northern envelope Y for east Maple Ridge rural concessions."""
    return _interp_poly_y(
        [
            (550.0, 95.0),
            (611.9, 95.0),
            (654.1, 75.0),
            (696.3, 55.0),
            (738.5, 45.0),
            (775.0, 35.0),
        ],
        x,
    )


# ALR greenbelt — no dense sub-grid (Surrey central valley).
ALR_Y0 = -130.0
ALR_Y1 = -180.0
ALR_X0 = 10.0
ALR_X1 = 295.4
ALR_CROSS = {0.0, 63.2, st_x(168), 190.0, st_x(184), st_x(192), 295.4}


def yaml_pts(points: list[tuple[float, float]]) -> list[list[float]]:
    return [[round(x, 1), round(y, 1)] for x, y in points]


def _catmull_rom(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    t2 = t * t
    t3 = t2 * t
    return (
        0.5
        * (
            (2.0 * p1[0])
            + (-p0[0] + p2[0]) * t
            + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2
            + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3
        ),
        0.5
        * (
            (2.0 * p1[1])
            + (-p0[1] + p2[1]) * t
            + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2
            + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
        ),
    )


def _dense_spline(
    controls: list[tuple[float, float]],
    *,
    segments: int = 18,
) -> list[tuple[float, float]]:
    """Catmull-Rom densify a control polyline into ``segments`` samples/chord."""
    if len(controls) < 2:
        return list(controls)
    if len(controls) == 2:
        (x0, y0), (x1, y1) = controls
        return [
            (x0 + (x1 - x0) * i / segments, y0 + (y1 - y0) * i / segments)
            for i in range(segments + 1)
        ]
    out: list[tuple[float, float]] = []
    n = len(controls)
    for i in range(n - 1):
        p0 = controls[i - 1] if i > 0 else (
            controls[0][0] - (controls[1][0] - controls[0][0]),
            controls[0][1] - (controls[1][1] - controls[0][1]),
        )
        p1 = controls[i]
        p2 = controls[i + 1]
        p3 = controls[i + 2] if i + 2 < n else (
            controls[-1][0] + (controls[-1][0] - controls[-2][0]),
            controls[-1][1] + (controls[-1][1] - controls[-2][1]),
        )
        steps = segments if i < n - 2 else segments + 1
        for s in range(steps):
            t = s / segments
            out.append(_catmull_rom(p0, p1, p2, p3, t))
    return out


def _add_ns(
    highways: dict,
    key: str,
    x: float,
    y0: float,
    y1: float,
    *,
    lanes: int = 4,
) -> None:
    if y0 > y1:
        y0, y1 = y1, y0
    highways[key] = {"lanes": lanes, "points": yaml_pts([(x, y0), (x, y1)])}


def _add_ew(
    highways: dict,
    key: str,
    y: float,
    x0: float,
    x1: float,
    *,
    lanes: int = 4,
) -> None:
    if x0 > x1:
        x0, x1 = x1, x0
    highways[key] = {"lanes": lanes, "points": yaml_pts([(x0, y), (x1, y)])}


# Major shafts urban fill must not redraw.
_MAJOR_XS = {
    X_SCOTT,
    -116.0,
    -126.6,
    -105.5,
    -168.8,
    -274.3,
    -232.1,
    -189.9,
    -147.7,
    -316.5,
    -345.4,
    -335.0,
    -355.0,
    TSW_WEST,
    TSW_EAST,
    -325.0,
    -372.0,
    -375.0,
    # Richmond N–S arterials / Sea Island (ΔX=-115 plate)
    -510.0,
    -495.0,
    -473.7,
    -452.6,
    -431.5,
    -410.4,
    -389.3,
    -368.2,
    -347.1,
    -304.9,
    -262.7,
    -220.5,
    -185.0,
    -150.0,
    -145.0,
    -135.0,
    -550.0,
    -470.0,
    # Vancouver / UBC N–S arterials
    -615.0,
    -610.0,
    -595.0,
    -585.0,
    -542.8,
    -511.2,
    -490.0,
    -458.5,
    -326.0,
    -199.0,
    -178.0,
    -255.0,
    -245.0,
    -475.0,
    -495.0,
    -468.0,
    -480.0,
    -486.0,
    -452.0,
    -420.0,
    -405.0,
    -398.0,
    # North Vancouver N–S arterials
    -640.0,
    -615.0,
    -505.0,
    -465.0,
    -395.0,
    26.4,
    42.2,
    # Burnaby N–S arterials / collectors
    -156.9,
    -142.0,
    -135.8,
    -129.0,
    -114.7,
    -93.6,
    -85.0,
    -72.5,
    -51.4,
    -20.0,
    -10.0,
    10.0,
    15.0,
    20.0,
    35.0,
    52.0,
    # Coquitlam N–S arterials
    68.0,
    76.0,
    84.0,
    95.0,
    105.0,
    112.0,
    120.0,
    135.0,
    145.0,
    155.0,
    # Port Moody N–S arterials / collectors
    30.0,
    48.0,
    64.0,
    78.0,
    79.5,
    82.0,
    83.0,
    86.5,
    88.0,
    90.0,
    93.5,
    94.0,
    96.0,
    100.0,
    102.0,
    # Port Coquitlam N–S arterials
    132.0,
    142.0,
    168.0,
    188.0,
    192.0,
    # Surrey Hwy 1 / Port Mann tip
    64.0,
    175.0,
    185.0,
    211.0,
    242.0,
    274.3,
    295.4,
    306.0,
    316.5,
    332.0,
    353.0,
    358.7,
    377.0,
    400.9,
    432.0,
    443.1,
    485.3,
    527.5,
    569.7,
    611.9,
    654.1,
    696.3,
    717.4,
    738.5,
    775.0,
}
_MAJOR_YS = {round(y, 1) for _, y in AVE_Y_ANCHORS} | {
    round(ave_y(a), 1) for a in (100, 96, 92, 84, 80, 76, 68, 64, 60, 48, 40, 24, 8)
} | {
    -55.0,
    -64.0,
    -105.5,
    -126.6,
    -147.7,
    -189.9,
    -190.0,
    -211.0,
    -253.2,
    -265.0,
    -275.0,
    -310.0,
    -320.0,
    -335.0,
    -348.0,
    -360.0,
    -362.0,
    -365.0,
    # Richmond E–W arterials / Sea Island (ΔY=+20 plate)
    62.2,
    50.0,
    48.0,
    41.1,
    38.0,
    35.0,
    25.0,
    20.0,
    15.0,
    10.0,
    9.5,
    4.2,
    -1.1,
    -15.0,
    -22.2,
    -43.3,
    -64.4,
    -85.5,
    -106.6,
    -112.0,
    -120.0,
    # Maple Ridge / Pitt Meadows E–W spines
    Y_DEWDNEY,
    Y_AIRPORT,
    Y_FORD_HAMMOND,
    Y_OLD_DEWDNEY,
    Y_NEAVES,
    Y_PITT_LAKE,
    105.5,
    126.6,
    147.7,
    165.0,
    145.0,
    125.0,
    92.0,
    78.0,
    71.0,
    72.0,
    68.0,
    65.0,
    58.0,
    55.0,
    50.0,
    32.0,
    0.0,
    -5.0,
    # Vancouver / UBC E–W spines
    90.0,
    100.0,
    121.6,
    142.7,
    174.3,
    195.4,
    206.0,
    216.5,
    222.0,
    225.0,
    227.0,
    236.0,
    240.0,
    245.0,
    248.0,
    252.0,
    255.0,
    269.0,
    275.0,
    285.0,
    290.0,
    292.0,
    305.0,
    325.0,
    # North Vancouver E–W spines
    345.0,
    350.0,
    353.0,
    355.0,
    358.7,
    370.0,
    379.7,
    380.0,
    386.0,
    395.0,
    410.0,
    420.0,
    425.0,
    435.0,
    450.0,
    465.0,
    470.0,
    475.0,
    # Burnaby E–W spines / town-centre collectors
    72.0,
    82.0,
    86.0,
    88.0,
    96.0,
    98.0,
    102.0,
    104.0,
    108.0,
    110.0,
    112.0,
    114.0,
    115.0,
    118.0,
    120.0,
    125.0,
    135.0,
    140.0,
    145.0,
    150.0,
    155.0,
    160.0,
    165.0,
    168.0,
    170.0,
    175.0,
    180.0,
    185.0,
    195.0,
    200.0,
    205.0,
    215.0,
    218.0,
    228.0,
    235.0,
    238.0,
    248.0,
    262.0,
    268.0,
    282.0,
    # Coquitlam E–W spines
    82.0,
    92.0,
    95.0,
    110.0,
    165.0,
    185.0,
    190.0,
    195.0,
    202.0,
    205.0,
    215.0,
    225.0,
    232.0,
    240.0,
    245.0,
    250.0,
    260.0,
    270.0,
    275.0,
    # Port Moody E–W spines / village collectors
    220.0,
    228.0,
    247.0,
    249.0,
    252.0,
    255.0,
    258.0,
    266.0,
    268.0,
    280.0,
    282.0,
    286.0,
    292.0,
    295.0,
    305.0,
    315.0,
    # Port Coquitlam E–W spines
    74.0,
    78.0,
    85.0,
    100.0,
    105.0,
    115.0,
    123.0,
    128.0,
    135.0,
    # Surrey Hwy 1 / Port Mann tip
    42.2,
}


def _near(value: float, pool: set[float], tol: float = 1.0) -> bool:
    return any(abs(value - p) <= tol for p in pool)


def _urban_grid(
    highways: dict,
    prefix: str,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    *,
    step: float = HALF_MILE,
) -> None:
    """Dense 2-lane residential/commercial fill inside a bounding box."""
    if y0 > y1:
        y0, y1 = y1, y0
    if x0 > x1:
        x0, x1 = x1, x0
    x = x0 + step
    n = 0
    while x < x1 - 0.5:
        if not _near(x, _MAJOR_XS):
            _add_ns(highways, f"{prefix}_ns_{n}", x, y0, y1, lanes=2)
            n += 1
        x += step
    y = y0 + step
    n = 0
    while y < y1 - 0.5:
        if not _near(y, _MAJOR_YS):
            _add_ew(highways, f"{prefix}_ew_{n}", y, x0, x1, lanes=2)
            n += 1
        y += step


def _snap_highways(highways: dict, tol: float = 0.15) -> None:
    """Snap near-duplicate vertices onto shared intersection coords."""
    anchors: list[tuple[float, float]] = []
    for x in STREET_X.values():
        for _, y in AVE_Y_ANCHORS:
            anchors.append((round(x, 1), round(y, 1)))
    # Named corridor junctions from the plate.
    anchors.extend(
        [
            (0.0, 0.0),
            (0.0, -84.4),
            (63.2, 42.2),
            (190.0, -20.0),
            (190.0, 24.0),
            (295.4, -48.0),
            (295.4, -168.0),
            (295.4, -168.8),
            (316.5, 20.0),
            (316.5, 58.0),
            (316.5, 63.3),
            (316.5, 71.0),
            (316.5, -84.4),
            (316.5, -168.8),
            (316.5, -232.1),
            (332.0, 55.0),
            (332.0, 68.0),
            (332.0, 78.0),
            (332.0, 84.4),
            (353.0, 64.0),
            (353.0, 63.3),
            (353.0, 84.4),
            (400.9, 10.0),
            (400.9, 60.0),
            (432.0, 58.0),
            (443.1, 48.0),
            (443.1, 58.0),
            (443.1, 84.4),
            (485.3, 45.0),
            (527.5, 25.0),
            (527.5, 32.0),
            (569.7, 84.4),
            (696.3, 10.0),
            (696.3, 15.0),
            (775.0, 0.0),
            (775.0, -5.0),
            # Pitt Meadows
            (175.0, 68.0),
            (211.0, 70.0),
            (211.0, 92.0),
            (242.0, 72.0),
            (242.0, 135.0),
            (242.0, 195.0),
            (245.0, 50.0),
            (274.3, 52.0),
            (274.3, 72.0),
            (295.4, 52.0),
            (295.4, 72.0),
            (295.4, 84.4),
            (295.4, 95.0),
            (306.0, 52.0),
            (306.0, 63.3),
            (306.0, 72.0),
            (306.0, 95.0),
            (306.0, 125.0),
            (306.0, 145.0),
            (52.0, -200.0),
            (654.1, -135.0),
            (654.1, -274.2),
            # Delta junctions
            (X_SCOTT, -64.0),
            (X_SCOTT, -84.4),
            (-116.0, -35.0),
            (-116.0, -64.0),
            (-126.6, -105.5),
            (-142.0, -145.0),
            (-168.8, -190.0),
            (-20.0, -170.0),
            (-225.0, -185.0),
            (-265.0, -180.0),
            (-335.0, -188.0),
            (-345.4, -211.0),
            (-372.0, -255.0),
            (-375.0, -288.0),
            (-325.0, -265.0),
            (-316.5, -335.0),
            (-316.5, -365.0),
            (TSW_WEST, TSW_Y0),
            (TSW_WEST, TSW_Y1),
            (TSW_EAST, TSW_Y0),
            (TSW_EAST, TSW_Y1),
            (TSW_WEST, -310.0),
            (TSW_EAST, -310.0),
            (TSW_WEST, -362.0),
            (TSW_EAST, -362.0),
            (-465.0, -330.0),
            (-84.0, -20.0),
            (-185.0, -115.0),
            (-245.0, -160.0),
            # Richmond / Lulu Island / Sea Island (shifted plate)
            (-495.0, 62.2),
            (-473.7, 35.0),
            (-431.5, 62.2),
            (-431.5, 50.0),
            (-431.5, 41.1),
            (-410.4, -1.1),
            (-410.4, 50.0),
            (-410.4, 41.1),
            (-389.3, -43.3),
            (-368.2, -106.6),
            (-347.1, 50.0),
            (-347.1, -1.1),
            (-304.9, 10.0),
            (-304.9, -1.1),
            (-220.5, 35.0),
            (-225.0, -1.1),
            (-225.0, 11.0),
            # Westminster S-curve + Hwy 91 / 91A Y-fork (no old X stubs)
            (-200.0, 4.0),
            (-198.0, 10.0),
            (-182.0, 10.0),
            (-178.0, 7.0),
            (-172.0, 5.0),
            (-168.0, 20.0),
            (-162.0, -3.0),
            (-158.0, 14.0),
            (-150.0, 28.0),
            (-145.0, 22.0),
            (-145.0, -15.0),
            (-130.0, 36.0),
            QUEENSBOROUGH,
            (-265.0, -180.0),
            (-116.0, -64.0),
            (-470.0, 48.0),
            (-473.7, 20.0),
            (-550.0, 38.0),
            (-452.6, 9.5),
            (-452.6, 4.2),
            (-510.0, -106.6),
            (-510.0, -112.0),
            (-495.0, -112.0),
            # Surrey north approaches (Pattullo / Port Mann tips)
            (0.0, 32.0),
            (64.0, 42.2),
            # Burnaby / Boundary seams + town-centre anchors
            (-178.0, 90.0),
            (-178.0, 108.0),
            (-178.0, 120.0),
            (-178.0, 125.0),
            (-178.0, 206.0),
            (-178.0, 216.5),
            (-178.0, 248.0),
            (-178.0, 269.0),
            (-178.0, 282.0),
            (-156.9, 88.0),
            (-135.8, 88.0),
            (-135.8, 118.0),
            (-135.8, 185.0),
            (-135.8, 216.5),
            (-135.8, 228.0),
            (-135.8, 269.0),
            (-114.7, 88.0),
            (-114.7, 114.0),
            (-114.7, 175.0),
            (-93.6, 86.0),
            (-93.6, 110.0),
            (-72.5, 104.0),
            (-72.5, 108.0),
            (-72.5, 150.0),
            (-72.5, 216.5),
            (-72.5, 269.0),
            (-51.4, 98.0),
            (-51.4, 140.0),
            (-51.4, 195.0),
            (-51.4, 269.0),
            (-45.0, 72.0),
            (-45.0, 96.0),
            (-25.0, 115.0),
            (-20.0, 180.0),
            (-20.0, 200.0),
            (-20.0, 218.0),
            (10.0, 165.0),
            (10.0, 255.0),
            (15.0, 85.0),
            (35.0, 125.0),
            (35.0, 155.0),
            (52.0, 135.0),
            (52.0, 165.0),
            (52.0, 185.0),
            (52.0, 215.0),
            (52.0, 245.0),
            (52.0, 268.0),
            # Coquitlam seams / town-centre anchors
            (35.0, 125.0),
            (55.0, 115.0),
            (62.0, 110.0),
            (64.0, 42.2),
            (68.0, 125.0),
            (68.0, 165.0),
            (68.0, 185.0),
            (68.0, 215.0),
            (84.0, 92.0),
            (84.0, 165.0),
            (84.0, 215.0),
            (95.0, 95.0),
            (95.0, 240.0),
            (105.0, 90.0),
            (105.0, 165.0),
            (105.0, 205.0),
            (112.0, 205.0),
            (112.0, 215.0),
            (112.0, 245.0),
            (120.0, 195.0),
            (120.0, 215.0),
            (120.0, 245.0),
            (135.0, 82.0),
            (135.0, 145.0),
            (155.0, 115.0),
            (155.0, 155.0),
            (155.0, 205.0),
            (155.0, 245.0),
            (165.0, 72.0),
            (175.0, 68.0),
            (175.0, 245.0),
            # Port Moody seams / U-loop / village anchors
            (30.0, 292.0),
            (48.0, 286.0),
            (52.0, 245.0),
            (52.0, 268.0),
            (64.0, 247.5),
            (68.0, 228.0),
            (68.0, 248.0),
            (68.0, 258.0),
            (75.0, 280.0),
            (76.0, 247.0),
            (76.0, 250.0),
            (76.0, 315.0),
            (78.0, 280.0),
            (82.0, 255.0),
            (85.0, 252.0),
            (86.0, 225.0),
            (88.0, 251.0),
            (88.0, 305.0),
            (90.0, 249.0),
            (90.0, 252.0),
            (94.0, 258.0),
            (94.0, 266.0),
            (95.0, 240.0),
            (95.0, 268.0),
            (96.0, 266.0),
            (96.0, 268.0),
            (100.0, 258.0),
            (102.0, 282.0),
            (112.0, 215.0),
            (112.0, 295.0),
            (115.0, 220.0),
            # Port Coquitlam seams / Downtown / Lincoln Park
            (130.0, 165.0),
            (132.0, 115.0),
            (132.0, 215.0),
            (135.0, 82.0),
            (142.0, 115.0),
            (142.0, 135.0),
            (142.0, 145.0),
            (142.0, 165.0),
            (142.0, 185.0),
            (145.0, 78.0),
            (145.0, 215.0),
            (152.0, 74.0),
            (152.0, 95.0),
            (155.0, 125.0),
            (155.0, 165.0),
            (155.0, 185.0),
            (165.0, 82.0),
            (165.0, 85.0),
            (165.0, 105.0),
            (168.0, 95.0),
            (168.0, 100.0),
            (168.0, 135.0),
            (168.0, 165.0),
            (168.0, 185.0),
            (170.0, 72.0),
            (172.0, 70.0),
            (172.0, 185.0),
            (188.0, 135.0),
            (188.0, 165.0),
            (190.0, 165.0),
            (192.0, 205.0),
        ]
    )
    # Dedup anchors.
    uniq: dict[tuple[float, float], None] = {}
    for ax, ay in anchors:
        uniq[(round(ax, 1), round(ay, 1))] = None
    pool = list(uniq.keys())

    # Densified interchange / shoreline splines keep Catmull-Rom samples intact.
    skip_snap = {
        "westminster_hwy",
        "hwy91",
        "hwy91a",
        "golden_ears",
        "lougheed_hwy",
        "haney_bypass",
        "mr_river_rd",
        "dewdney_trunk",
        "mr_rural_north",
        "airport_way",
        "ford_hammond_rd",
        "old_dewdney_trunk",
        "neaves_mcneil",
        "pm_rannie",
        "hwy1_van",
        "hwy1_bn",
        "kingsway",
        "kingsway_bn",
        "canada_way",
        "lougheed_bn",
        "hastings_barnet",
        "gaglardi_way",
        "marine_stewardson",
        "brunette_ave",
        "bn_mtn_pkwy",
        "sfu_ring",
        "nw_front_st",
        "nw_columbia_st",
        "nw_carnarvon_st",
        "nw_clarkson_st",
        "nw_royal_ave",
        "nw_queens_ave",
        "nw_3rd_ave",
        "nw_4th_ave",
        "nw_5th_ave",
        "nw_6th_ave",
        "nw_7th_ave",
        "nw_8th_ave",
        "nw_10th_ave",
        "nw_stewardson",
        "nw_20th_st",
        "nw_14th_st",
        "nw_12th_st",
        "nw_10th_st",
        "nw_8th_st",
        "nw_6th_st",
        "nw_4th_st",
        "nw_2nd_st",
        "nw_1st_st",
        "mcbride_blvd",
        "ewen_ave",
        "boyd_st",
        "salter_st",
        "hwy1_cq",
        "lougheed_cq",
        "barnet_cq",
        "mary_hill_bypass",
        "brunette_cq",
        "united_blvd",
        "como_lake_ave",
        "pinetree_way",
        "barnet_pomo_w",
        "st_johns_st",
        "barnet_pomo_e",
        "ioco_rd",
        "clarke_rd_pomo",
        "murray_st",
        "guildford_pomo",
        "ungless_heritage",
        "moray_st",
        "clarke_st_pomo",
        "spring_st_pomo",
        "sunnyside_rd",
        "east_rd_anmore",
        "glenayre_dr",
        "harvard_dr",
        "princeton_ave",
        "lougheed_pc",
        "mary_hill_pc",
        "fremont_connector",
        "pitt_river_rd",
        "citadel_dr",
        "lincoln_ave_pc",
    }
    for name, route in highways.items():
        if name in skip_snap:
            continue
        pts = route.get("points") or []
        snapped: list[list[float]] = []
        for p in pts:
            x, y = float(p[0]), float(p[1])
            best = None
            best_d = tol
            for ax, ay in pool:
                d = abs(x - ax) + abs(y - ay)
                if d < best_d:
                    best_d = d
                    best = (ax, ay)
            if best is not None:
                x, y = best
            snapped.append([round(x, 1), round(y, 1)])
        # Drop zero-length consecutive duplicates after snap.
        cleaned: list[list[float]] = []
        for p in snapped:
            if not cleaned or p != cleaned[-1]:
                cleaned.append(p)
        route["points"] = cleaned


def _hwy91_x_at(y: float) -> float:
    """West X of the Hwy 91 corridor at a given Y (north → south)."""
    if y >= HWY91_POLY[0][1]:
        return HWY91_POLY[0][0]
    if y <= HWY91_POLY[-1][1]:
        return HWY91_POLY[-1][0]
    for i in range(len(HWY91_POLY) - 1):
        x0, y0 = HWY91_POLY[i]
        x1, y1 = HWY91_POLY[i + 1]
        if y1 <= y <= y0:
            if abs(y0 - y1) < 1e-9:
                return x0
            t = (y0 - y) / (y0 - y1)
            return x0 + t * (x1 - x0)
    return HWY91_POLY[0][0]


def _in_burns_bog(x: float, y: float) -> bool:
    """True if a point sits inside the Burns Bog open zone (west of Hwy 91)."""
    if not (BOG_X0 <= x <= BOG_X1 and BOG_Y0 <= y <= BOG_Y1):
        return False
    # Anything on or east of the Hwy 91 corridor is urban / highway, not bog.
    return x < _hwy91_x_at(y) - 1.0


def _nordel_y_at(x: float) -> float:
    """Y on Nordel Way between Scott Rd and the Hwy 91 interchange."""
    x0, y0 = X_SCOTT, -64.0
    x1, y1 = -126.6, -105.5
    if x >= x0:
        return y0
    if x <= x1:
        return y1
    t = (x0 - x) / (x0 - x1)
    return y0 + t * (y1 - y0)


def _build_north_delta(highways: dict) -> None:
    """North Delta grid: Scott Rd → Hwy 91, clipped clean of bog stubs."""
    # Nordel Way: Scott Rd → Hwy 91 interchange (do not cross west of 91).
    highways["nordel"] = {
        "lanes": 4,
        "points": yaml_pts([(X_SCOTT, -64.0), (-126.6, -105.5)]),
    }

    # East–west avenues terminate on the Hwy 91 corridor.
    nd_aves: list[tuple[int, float]] = [
        (88, round(ave_y(88), 1)),
        (84, round(ave_y(84), 1)),
        (80, round(ave_y(80), 1)),
        (76, round(ave_y(76), 1)),
        (72, round(ave_y(72), 1)),
        (68, round(ave_y(68), 1)),
        (64, -126.6),
    ]
    for ave, y in nd_aves:
        x_west = round(_hwy91_x_at(y), 1)
        # Keep avenues east of Hwy 91; never enter Burns Bog.
        if x_west >= X_SCOTT - 0.5:
            continue
        _add_ew(highways, f"nd_ave_{ave}", y, x_west, X_SCOTT, lanes=4)

    # 116 St & 112 St: Nordel → 64 Ave only (no vertical overhang stubs).
    y_64 = -126.6
    highways["nd_st_116"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (DELTA_ST_X[116], round(_nordel_y_at(DELTA_ST_X[116]), 1)),
                (DELTA_ST_X[116], y_64),
            ]
        ),
    }
    highways["nd_st_112"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (DELTA_ST_X[112], round(_nordel_y_at(DELTA_ST_X[112]), 1)),
                (DELTA_ST_X[112], y_64),
            ]
        ),
    }

    # Compact residential fill, clipped per-row to Hwy 91 and Nordel.
    fill_step = QUARTER_MILE
    y = -64.0 - fill_step
    ew_n = 0
    while y > y_64 + 0.5:
        if not _near(y, _MAJOR_YS):
            x_west = round(_hwy91_x_at(y), 1)
            if x_west < X_SCOTT - 1.0:
                _add_ew(
                    highways, f"nd_fill_ew_{ew_n}", y, x_west, X_SCOTT, lanes=2
                )
                ew_n += 1
        y -= fill_step

    x = X_SCOTT - fill_step
    ns_n = 0
    while x > -126.6 + 0.5:
        if not _near(x, _MAJOR_XS):
            y_top = round(_nordel_y_at(x), 1)
            y_bot = y_64
            # Stay east of Hwy 91 at the south end of this shaft.
            if x >= _hwy91_x_at(y_bot) - 0.5 and y_top > y_bot + 1.0:
                _add_ns(highways, f"nd_fill_ns_{ns_n}", x, y_bot, y_top, lanes=2)
                ns_n += 1
        x -= fill_step


def _build_ladner(highways: dict) -> None:
    """Ladner Trunk spine + River Rd / Arthur Dr triangle + town fill.

    Town centre sits 50 units west of the prior plate (-345.4, -211).
    """
    # Ladner Trunk Rd: Hwy 91 / Hwy 99 interchange → Ladner Town Centre.
    highways["ladner_trunk"] = {
        "lanes": 4,
        "points": yaml_pts([(-168.8, -190.0), (-345.4, -211.0)]),
    }

    # River Road: Massey approach → northern Ladner edge → Town Centre.
    highways["river_rd"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (-265.0, -180.0),
                (-335.0, -188.0),
                (-345.4, -211.0),
            ]
        ),
    }

    # Arthur Drive / 53 St: Town Centre → Hwy 17 on the ferry causeway approach.
    highways["arthur_dr"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (-345.4, -211.0),
                (-372.0, -255.0),
                (-375.0, -288.0),
            ]
        ),
    }

    # Compact Ladner town centre grid (7.5 spacing inside the triangle).
    lad_x0, lad_x1 = -355.0, -325.0
    lad_y0, lad_y1 = -225.0, -195.0
    step = 7.5
    x = lad_x0 + step
    n = 0
    while x < lad_x1 - 0.5:
        if not _near(x, _MAJOR_XS, tol=2.0):
            _add_ns(highways, f"lad_ns_{n}", x, lad_y0, lad_y1, lanes=2)
            n += 1
        x += step
    y = lad_y0 + step
    n = 0
    while y < lad_y1 - 0.5:
        if not _near(y, _MAJOR_YS, tol=2.0):
            _add_ew(highways, f"lad_ew_{n}", y, lad_x0, lad_x1, lanes=2)
            n += 1
        y += step


def _build_tsawwassen(highways: dict) -> None:
    """Frame Tsawwassen: parallel N–S spines + snapped E–W avenues."""
    # Hwy 17A / 56 St: single clean spine from Hwy 17 interchange → Point Roberts.
    highways["hwy17a"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (-325.0, -265.0),
                (-316.5, -335.0),
                (-316.5, Y_POINT_ROBERTS),
            ]
        ),
    }

    # Parallel north–south bounding arterials.
    _add_ns(highways, "tsw_west", TSW_WEST, TSW_Y0, TSW_Y1, lanes=4)
    _add_ns(highways, "tsw_east", TSW_EAST, TSW_Y0, TSW_Y1, lanes=4)

    # Named avenues snapped cleanly between the bounding spines.
    tsw_aves = (
        (18, -310.0),
        (16, -320.0),
        (12, -335.0),
        (8, -348.0),
        (1, -362.0),
    )
    y_lo, y_hi = min(TSW_Y0, TSW_Y1), max(TSW_Y0, TSW_Y1)
    for ave, y in tsw_aves:
        if y_lo - 3.0 <= y <= y_hi + 3.0:
            _add_ew(highways, f"tsw_ave_{ave}", y, TSW_WEST, TSW_EAST, lanes=2)

    # Light internal collectors between the named avenues.
    _urban_grid(
        highways,
        "tsw",
        TSW_WEST,
        TSW_EAST,
        TSW_Y1,
        TSW_Y0,
        step=HALF_MILE,
    )


def _richmond_river_y(x: float) -> float:
    """River Road shoreline Y at a given X (North Arm Fraser)."""
    x_rail, y_rail = RICH_NS_X["no_1"], Y_RIVER_W
    x_no2, y_no2 = RICH_NS_X["no_2"], Y_RIVER_NO2
    x_no8, y_no8 = RICH_NS_X["no_8"], Y_RIVER_NO2
    if x <= x_rail:
        return y_rail
    if x <= x_no2:
        t = (x - x_rail) / (x_no2 - x_rail)
        return y_rail + t * (y_no2 - y_rail)
    if x >= x_no8:
        return y_no8
    t = (x - x_no2) / (x_no8 - x_no2)
    return y_no2 + t * (y_no8 - y_no2)


def _build_richmond(highways: dict) -> None:
    """Lulu Island 1-mile arterial grid + City Centre / Steveston / Sea Island.

    All local roads stay west of RICH_X_EAST_LIMIT (-135) so the Fraser river
    buffer between Richmond and Surrey/Delta stays clear. Only Hwy 99 / 91
    (defined in build()) span that gap.
    """
    x1 = RICH_NS_X["no_1"]
    x2 = RICH_NS_X["no_2"]
    x3 = RICH_NS_X["no_3"]
    x_gc = RICH_NS_X["garden_city"]
    x4 = RICH_NS_X["no_4"]
    x_shell = RICH_NS_X["shell"]
    x5 = RICH_NS_X["no_5"]
    x6 = RICH_NS_X["no_6"]
    x7 = RICH_NS_X["no_7"]
    x8 = RICH_NS_X["no_8"]
    x_gil = RICH_NS_X["gilbert"]
    x_ww = RICH_NS_X["westwater"]

    y_bp = RICH_EW_Y["bridgeport"]
    y_cam = RICH_EW_Y["cambie"]
    y_west = RICH_EW_Y["westminster"]
    y_gran = RICH_EW_Y["granville"]
    y_blun = RICH_EW_Y["blundell"]
    y_fran = RICH_EW_Y["francis"]
    y_will = RICH_EW_Y["williams"]
    y_stev = Y_STEVESTON
    y_monc = RICH_EW_Y["moncton"]
    y_ald = RICH_EW_Y["alderbridge"]
    y_lans = RICH_EW_Y["lansdowne"]

    # --- River Road (North Arm shoreline) ---
    highways["richmond_river"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (x1, Y_RIVER_W),
                (x2, Y_RIVER_NO2),
                (x3, round(_richmond_river_y(x3), 1)),
                (x_gc, round(_richmond_river_y(x_gc), 1)),
                (x4, round(_richmond_river_y(x4), 1)),
                (x5, round(_richmond_river_y(x5), 1)),
                (x6, round(_richmond_river_y(x6), 1)),
                (x7, round(_richmond_river_y(x7), 1)),
                (x8, Y_RIVER_NO2),
            ]
        ),
    }

    # --- N–S numbered roads: River Road → Steveston Hwy (no empty stubs) ---
    ns_roads = (
        ("no_1_rd", x1, 4),
        ("no_2_rd", x2, 4),
        ("no_3_rd", x3, 4),
        ("garden_city_rd", x_gc, 4),
        ("no_4_rd", x4, 4),
        ("shell_rd", x_shell, 4),
        ("no_5_rd", x5, 4),
        ("no_6_rd", x6, 4),
        ("no_7_rd", x7, 4),
        ("no_8_rd", x8, 4),
    )
    for key, x, lanes in ns_roads:
        # No. 3 Rd continues to the Oak Street Bridge approach.
        y_top = Y_RIVER_W if key == "no_3_rd" else round(_richmond_river_y(x), 1)
        _add_ns(highways, key, x, y_stev, y_top, lanes=lanes)

    # Knight Street Connector — Bridgeport → bridge approach (Hwy 91 covers No. 5 N).
    _add_ns(highways, "knight_st", x5, y_bp, 70.0, lanes=4)

    # --- E–W major arterials (extent per corridor) ---
    _add_ew(highways, "bridgeport_rd", y_bp, x3, x6, lanes=4)
    _add_ew(highways, "cambie_rd", y_cam, x1, x8, lanes=4)
    # Westminster Hwy: straight through East Richmond, then continuous NE
    # S-curve across Hwy 91 to the east tip (no X-junction stubs).
    westminster_curve = _dense_spline(
        [
            (-225.0, -1.1),  # No. 8 Rd entry into the curve
            (-200.0, 4.0),
            (-182.0, 10.0),  # Hwy 91 crossover
            (-168.0, 20.0),
            (-150.0, 28.0),
            (-130.0, 36.0),  # Richmond east tip (open Fraser gap)
        ],
        segments=18,
    )
    highways["westminster_hwy"] = {
        "lanes": 4,
        "z_offset": 0.002,  # sit above Hwy 91 at the crossover
        "points": yaml_pts([(x1, y_west), *westminster_curve]),
    }
    _add_ew(highways, "granville_ave", y_gran, x1, x5, lanes=4)
    _add_ew(highways, "blundell_rd", y_blun, x1, x6, lanes=4)
    _add_ew(highways, "francis_rd", y_fran, x1, x5, lanes=4)
    _add_ew(highways, "williams_rd", y_will, x1, x5, lanes=4)
    _add_ew(highways, "steveston_hwy", y_stev, x1, x_shell, lanes=4)

    # --- City Centre / Brighouse dense collectors (10.5 spacing) ---
    _add_ns(highways, "gilbert_rd", x_gil, y_gran, y_bp, lanes=2)
    _add_ew(highways, "alderbridge_way", y_ald, x2, x_gc, lanes=2)
    _add_ew(highways, "lansdowne_rd", y_lans, x2, x_gc, lanes=2)
    _urban_grid(
        highways,
        "brighouse",
        x2,
        x_gc,
        y_gran,
        y_bp,
        step=QUARTER_MILE,
    )

    # --- Steveston Village grid ---
    _add_ns(highways, "westwater_dr", x_ww, -120.0, y_will, lanes=2)
    _add_ew(highways, "steveston_hwy_w", y_stev, x_ww, x1, lanes=4)
    _add_ew(highways, "williams_rd_w", y_will, x_ww, x1, lanes=4)
    _add_ew(highways, "moncton_st", y_monc, x_ww, x2, lanes=2)
    _urban_grid(
        highways,
        "steveston",
        x_ww,
        x2,
        -120.0,
        -95.0,
        step=QUARTER_MILE,
    )

    # --- Sea Island / YVR spur ---
    highways["grant_mcconachie"] = {
        "lanes": 6,
        "points": yaml_pts(
            [
                (x3, 50.0),  # Hwy 99 / Oak St Bridge branch
                (-470.0, 48.0),
                (-550.0, 38.0),  # YVR Terminal Loop
            ]
        ),
    }
    highways["russ_baker"] = {
        "lanes": 6,
        "points": yaml_pts(
            [
                (-470.0, 48.0),
                (x2, 20.0),  # No. 2 Rd Bridge corridor
            ]
        ),
    }
    highways["sea_island_way"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (x3, y_bp),
                (-470.0, 42.0),
            ]
        ),
    }

    # Hwy 91A — smooth Y-fork NE of Hwy 91, parallel to / south of Westminster.
    hwy91a_ctrl = [
        (-172.0, 5.0),  # Y-split node (just east of Westminster crossover)
        (-158.0, 14.0),
        (-145.0, 22.0),
        QUEENSBOROUGH,  # (-128, +30)
    ]
    highways["hwy91a"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(hwy91a_ctrl, segments=16)),
    }

    # Drop any local Richmond stub that drifted east of the river-gap limit.
    _clip_richmond_east(highways)


_RICHMOND_ROUTE_PREFIXES = (
    "no_1_",
    "no_2_",
    "no_3_",
    "no_4_",
    "no_5_",
    "no_6_",
    "no_7_",
    "no_8_",
    "garden_city",
    "shell_rd",
    "bridgeport",
    "cambie_rd",
    "westminster",
    "granville_ave",
    "blundell",
    "francis",
    "williams",
    "steveston",
    "gilbert",
    "alderbridge",
    "lansdowne",
    "westwater",
    "moncton",
    "richmond_river",
    "knight",
    "grant_",
    "russ_",
    "sea_island",
    "brighouse_",
    "hwy91a",
)


def _clip_richmond_east(highways: dict) -> None:
    """Remove Richmond local routes (or vertices) east of the river buffer."""
    keep_crossing = {"hwy99", "hwy91", "hwy91a"}
    doomed: list[str] = []
    for key, route in highways.items():
        if key in keep_crossing:
            continue
        if not key.startswith(_RICHMOND_ROUTE_PREFIXES):
            continue
        pts = route.get("points") or []
        clipped = [p for p in pts if float(p[0]) <= RICH_X_EAST_LIMIT + 0.05]
        if len(clipped) < 2:
            doomed.append(key)
        else:
            route["points"] = clipped
    for key in doomed:
        del highways[key]


def _marine_y(x: float) -> float:
    """SW / SE / NW Marine Drive Y at X (Boundary → UBC tip).

    MARINE_CTRL is authored east→west (decreasing X); reverse for the
    eastbound interpolator.
    """
    return _interp_poly_y(list(reversed(MARINE_CTRL)), x)


def _rotated_corridor(
    origin: tuple[float, float],
    angle_deg: float,
    half_len: float,
    *,
    offset: float = 0.0,
) -> list[tuple[float, float]]:
    """Axis-aligned segment in a rotated downtown frame (angle from +X)."""
    ang = math.radians(angle_deg)
    ux, uy = math.cos(ang), math.sin(ang)
    vx, vy = -math.sin(ang), math.cos(ang)
    ox = origin[0] + vx * offset
    oy = origin[1] + vy * offset
    return [
        (ox - ux * half_len, oy - uy * half_len),
        (ox + ux * half_len, oy + uy * half_len),
    ]


# Routes allowed to span the False Creek gap (bridges / viaducts / spines only).
_FC_BRIDGE_KEYS = frozenset(
    {
        "burrard_bridge",
        "granville_bridge",
        "cambie_bridge",
        "gore_viaduct",
        "georgia_viaduct",
        "dunsmuir_viaduct",
        "ave_4th",
        "terminal_ave",
        "quebec_st",
        "main_st",
        "fraser_st",
        "knight_st",
        "hwy99",
        "beach_ave",
        "pacific_blvd",
    }
)


def _clip_false_creek_stubs(highways: dict) -> None:
    """Remove dead-end vertices / routes dangling inside the False Creek gap."""
    doomed: list[str] = []
    for key, route in highways.items():
        if key in _FC_BRIDGE_KEYS:
            continue
        pts = route.get("points") or []
        if len(pts) < 2:
            doomed.append(key)
            continue
        kept: list[list[float]] = []
        for p in pts:
            x, y = float(p[0]), float(p[1])
            if FC_X0 <= x <= FC_X1 and FC_Y0 < y < FC_Y1:
                continue  # drop mid-gap dangling vertices
            kept.append(p)
        if len(kept) < 2:
            doomed.append(key)
        else:
            route["points"] = kept
    for key in doomed:
        del highways[key]


def _add_route(
    highways: dict,
    key: str,
    pts: list[tuple[float, float]],
    *,
    lanes: int = 4,
    z_offset: float | None = None,
) -> None:
    if len(pts) < 2:
        return
    route: dict = {"lanes": lanes, "points": yaml_pts(pts)}
    if z_offset is not None:
        route["z_offset"] = z_offset
    highways[key] = route


def _build_downtown_peninsula(highways: dict) -> None:
    """Downtown Vancouver peninsula dual-grid (roads only, Z=0).

    Clean layout:
    - Avenues NW–SE @ -42° (Georgia-parallel), clipped north of Pacific (Y≥247)
    - Cross-streets SW–NE @ +48° (Burrard-parallel), snapped to bridge abutments
    - Orthogonal Gastown / DTES / Strathcona east of Cambie
    """
    x_main = VAN_NS_X["main"]
    x_knight = VAN_NS_X["knight"]
    x_bound = VAN_NS_X["boundary"]
    x_fraser = VAN_NS_X["fraser"]
    y_hast = VAN_EW_Y["hastings"]
    y_term = Y_TERMINAL
    y_port = VAN_EW_Y["waterfront"]
    y_pac = 247.0  # Pacific rail — south clip for local avenues

    def _cross(sw: tuple[float, float], length: float = 32.0) -> list[tuple[float, float]]:
        return [sw, _shift_pt(sw, DT_CROSS_ANGLE, length)]

    # =====================================================================
    # Perimeter waterfront (owns False Creek / English Bay edge)
    # =====================================================================
    _add_route(
        highways,
        "beach_ave",
        _dense_spline(
            [
                (-492.0, 272.0),
                (-480.0, 260.0),
                BURRARD_ABUT,
                GRANVILLE_ABUT,
                (-440.0, y_pac),
            ],
            segments=10,
        ),
        lanes=2,
    )
    _add_route(
        highways,
        "pacific_blvd",
        _dense_spline(
            [
                (-440.0, y_pac),
                CAMBIE_ABUT,
                (-405.0, 245.0),
                (x_main, 245.0),
            ],
            segments=8,
        ),
        lanes=4,
    )

    # =====================================================================
    # NW–SE avenues @ -42° (parallel to Georgia), then orthogonal east of Cambie
    # =====================================================================
    # Georgia — Lions Gate causeway → Beatty junction (not on Cambie Bridge deck).
    georgia_beatty = (-418.0, 248.0)
    _add_route(
        highways,
        "georgia_st",
        _dense_spline(
            [
                (-495.0, 325.0),  # Lions Gate / Stanley Park northern causeway
                (-485.0, 292.0),
                (-470.0, 275.0),
                (-455.0, 263.0),  # Burrard
                (-442.0, 256.0),  # Granville
                georgia_beatty,
            ],
            segments=14,
        ),
        lanes=6,
    )
    _add_route(
        highways,
        "georgia_viaduct",
        [georgia_beatty, (-405.0, Y_PRIOR), (x_main, Y_PRIOR)],
        lanes=4,
        z_offset=0.001,
    )

    # Robson — 4u SW of Georgia band; ends on Pacific.
    _add_route(
        highways,
        "robson_st",
        [
            (-488.0, 282.0),
            (-470.0, 268.0),
            (-446.0, 252.0),
            (-430.0, y_pac),
        ],
        lanes=4,
    )

    # Smithe / Nelson couplet — end on Pacific, no creek stubs.
    _add_route(
        highways,
        "smithe_st",
        [(-472.0, 264.0), (-452.0, 254.0), (-436.0, y_pac)],
        lanes=2,
    )
    _add_route(
        highways,
        "nelson_st",
        [(-485.0, 272.0), (-460.0, 256.0), (-440.0, y_pac)],
        lanes=2,
    )

    # Davie — English Bay → Pacific (via Burrard abutment).
    _add_route(
        highways,
        "davie_st",
        [(-486.0, 262.0), BURRARD_ABUT, (-452.0, y_pac)],
        lanes=4,
    )

    # Dunsmuir + viaduct → Main @ Keefer band.
    _add_route(
        highways,
        "dunsmuir_st",
        [(-452.0, 266.0), (-438.0, 258.0), (-422.0, 250.0)],
        lanes=4,
    )
    _add_route(
        highways,
        "dunsmuir_viaduct",
        [(-422.0, 250.0), (-405.0, 255.0), (x_main, 256.0)],
        lanes=4,
        z_offset=0.001,
    )

    # Hastings — angled west of Cambie, orthogonal east to Boundary.
    _add_route(
        highways,
        "hastings_st",
        [
            (-472.0, 284.0),
            (-438.0, 268.0),
            (-415.0, 259.0),
            (x_main, y_hast),
            (x_knight, y_hast),
            (x_bound, y_hast),
        ],
        lanes=4,
    )

    # Pender — parallel SW of Hastings; orthogonal through Chinatown.
    _add_route(
        highways,
        "pender_st",
        [
            (-478.0, 280.0),
            (-448.0, 266.0),
            (-418.0, 254.0),
            (x_main, Y_PENDER_E),
            (X_HEATLEY, Y_PENDER_E),
        ],
        lanes=4,
    )

    # Water (harbour edge) + Cordova (inland parallel) — then orthogonal to Main.
    _add_route(
        highways,
        "water_st",
        _dense_spline(
            [
                (-465.0, 288.0),
                (-435.0, 276.0),
                (-412.0, 270.0),
                (x_main, Y_CORDOVA_E + 2.0),
            ],
            segments=10,
        ),
        lanes=2,
    )
    _add_route(
        highways,
        "cordova_st",
        [
            (-450.0, 280.0),
            (-430.0, 272.0),
            (-412.0, 266.0),
            (x_main, Y_CORDOVA_E),
        ],
        lanes=2,
    )

    # =====================================================================
    # SW–NE cross-streets @ +48° (parallel to Burrard)
    # =====================================================================
    # West End fan — Denman @ 48°, others offset 4.5u along avenue axis.
    denman_sw = (-486.0, 262.0)
    denman_ne = _shift_pt(denman_sw, DT_CROSS_ANGLE, 28.0)
    # Clamp NE below Coal Harbour waterline.
    if denman_ne[1] > y_port + 8.0:
        denman_ne = (denman_ne[0], y_port + 8.0)
    west_end = (
        ("chilco_st", -9.0, 2),
        ("denman_st", 0.0, 4),
        ("cardero_st", 4.5, 2),
        ("nicola_st", 9.0, 2),
        ("broughton_st", 13.5, 2),
        ("jervis_st", 18.0, 2),
        ("bute_st", 22.5, 2),
        ("thurlow_st", 27.0, 2),
    )
    for key, off, lanes in west_end:
        sw = _shift_pt(denman_sw, DT_AVE_ANGLE, off)
        # Keep south ends on/above Pacific rail (avoids FC stub clip).
        if sw[1] < y_pac:
            # Slide NE along the cross-street until Y hits Pacific.
            t = (y_pac - sw[1]) / math.sin(math.radians(DT_CROSS_ANGLE))
            sw = _shift_pt(sw, DT_CROSS_ANGLE, t)
        ne = _shift_pt(sw, DT_CROSS_ANGLE, 28.0)
        y_cap = y_port + 10.0
        if ne[1] > y_cap:
            t = (y_cap - sw[1]) / math.sin(math.radians(DT_CROSS_ANGLE))
            ne = _shift_pt(sw, DT_CROSS_ANGLE, t)
        _add_route(highways, key, [sw, ne], lanes=lanes)

    # Burrard / Hornby — abutment → Coal Harbour @ 48°.
    _add_route(
        highways,
        "burrard_st",
        _cross(BURRARD_ABUT, 34.0),
        lanes=4,
    )
    hornby_sw = _shift_pt(BURRARD_ABUT, DT_AVE_ANGLE, 4.0)
    # Keep Hornby south end on Pacific (Y≥247).
    if hornby_sw[1] < y_pac:
        hornby_sw = (hornby_sw[0], y_pac)
    _add_route(highways, "hornby_st", _cross(hornby_sw, 32.0), lanes=2)

    # Howe (Granville Bridge) + Granville mall + Seymour…Mainland @ 4u spacing.
    _add_route(highways, "howe_st", _cross(GRANVILLE_ABUT, 34.0), lanes=4)
    granville_sw = (-448.0, y_pac)
    _add_route(highways, "granville_dt", _cross(granville_sw, 32.0), lanes=2)
    for i, (key, lanes) in enumerate(
        (
            ("seymour_st", 4),
            ("richards_st", 2),
            ("homer_st", 2),
            ("hamilton_st", 2),
            ("mainland_st", 2),
        )
    ):
        # Start east of Granville mall; stop short of Beatty.
        sw = (-444.0 + 4.0 * i, y_pac)
        _add_route(highways, key, _cross(sw, 28.0), lanes=lanes)

    # Beatty — Cambie Bridge → Gastown (single spine; no duplicate cambie_dt).
    _add_route(highways, "beatty_st", _cross(CAMBIE_ABUT, 28.0), lanes=4)

    # =====================================================================
    # Eastern orthogonal grid (Chinatown / Strathcona / Port)
    # =====================================================================
    _add_route(
        highways,
        "quebec_st",
        [(X_QUEBEC, y_term), (X_QUEBEC, 245.0), (X_QUEBEC, y_hast), (X_QUEBEC, y_port)],
        lanes=4,
    )
    _add_route(
        highways,
        "main_st",
        [
            (x_main, VAN_EW_Y["marine"]),
            (x_main, 216.5),
            (x_main, y_term),
            (x_main, 245.0),
            (x_main, Y_PRIOR),
            (x_main, 256.0),
            (x_main, Y_PENDER_E),
            (x_main, y_hast),
            (x_main, Y_CORDOVA_E),
            (x_main, y_port),
        ],
        lanes=4,
    )
    # Gore / Princess / Heatley — Prior → Hastings (avoid viaduct conflict south of Prior).
    for key, x in (
        ("gore_ave", X_GORE),
        ("princess_ave", X_PRINCESS),
        ("heatley_ave", X_HEATLEY),
    ):
        _add_ns(highways, key, x, Y_PRIOR, y_hast, lanes=2)

    _add_ew(highways, "keefer_st", 256.0, x_main, X_HEATLEY, lanes=2)
    _add_ew(highways, "prior_st", Y_PRIOR, x_main, x_knight, lanes=4)

    # Viaduct east approach lands on Fraser (not Gore), then vertical to Broadway.
    _add_route(
        highways,
        "gore_viaduct",
        [
            (-405.0, 255.0),
            (x_main, 256.0),
            (x_fraser, 256.0),
            (x_fraser, y_term),
            (x_fraser, Y_4TH),
            (x_fraser, 216.5),
        ],
        lanes=4,
        z_offset=0.001,
    )


def _build_vancouver(highways: dict) -> None:
    """City of Vancouver + UBC road network north of the North Arm Fraser.

    Flat Z=0 arterials only. Stitches onto Richmond via Oak St Bridge
    (X=-431.5), Knight St Bridge (X=-347.1), and Arthur Laing / Granville
    (X=-458.5). Downtown peninsula uses a ~42° dual grid (see
    ``_build_downtown_peninsula``) snapped to Burrard / Granville / Cambie
    abutments. Local N–S streets clip at SW/SE Marine (Y=+90); Broadway,
    Kingsway, Grandview, Hastings, and Hwy 1 terminate at Boundary Rd (X=-178).
    """
    x_blanca = VAN_NS_X["blanca"]
    x_dunbar = VAN_NS_X["dunbar"]
    x_mac = VAN_NS_X["macdonald"]
    x_arb = VAN_NS_X["arbutus"]
    x_gran = VAN_NS_X["granville"]
    x_oak = VAN_NS_X["oak"]
    x_cam = VAN_NS_X["cambie"]
    x_main = VAN_NS_X["main"]
    x_fraser = VAN_NS_X["fraser"]
    x_knight = VAN_NS_X["knight"]
    x_vic = VAN_NS_X["victoria"]
    x_nan = VAN_NS_X["nanaimo"]
    x_ren = VAN_NS_X["renfrew"]
    x_rup = VAN_NS_X["rupert"]
    x_joyce = VAN_NS_X["joyce"]
    x_bound = VAN_NS_X["boundary"]
    x_wesbrook = VAN_NS_X["wesbrook"]
    x_tip = VAN_NS_X["ubc_tip"]

    y_mar = VAN_EW_Y["marine"]
    y_70 = VAN_EW_Y["70th"]
    y_49 = VAN_EW_Y["49th"]
    y_41 = VAN_EW_Y["41st"]
    y_ke = VAN_EW_Y["king_edward"]
    y_16 = VAN_EW_Y["16th"]
    y_gv = VAN_EW_Y["grandview"]
    y_bw = VAN_EW_Y["broadway"]
    y_ch = VAN_EW_Y["chancellor"]
    y_4th = Y_4TH
    y_term = Y_TERMINAL
    y_prior = Y_PRIOR
    y_fc_s = VAN_EW_Y["false_creek_s"]
    y_hast = VAN_EW_Y["hastings"]
    y_port = VAN_EW_Y["waterfront"]

    # --- SW / SE / NW Marine Drive (south + west waterfront spine) ---
    highways["sw_marine"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(MARINE_CTRL, segments=20)),
    }

    # --- Arthur Laing Bridge corridor (Sea Island ↔ SW Marine / Granville) ---
    highways["arthur_laing"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (x_gran, y_mar),
                (-470.0, 70.0),
                (-470.0, 48.0),  # russ_baker / Sea Island junction
            ]
        ),
    }

    # --- Knight / Clark: North Arm → Broadway → Prior → Hastings / Port ---
    highways["knight_st"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (x_knight, RICH_EW_Y["bridgeport"]),
                (x_knight, 70.0),
                (x_knight, y_mar),
                (x_knight, y_49),
                (x_knight, y_41),
                (x_knight, 188.0),  # Kingsway crossing
                (x_knight, y_bw),
                (x_knight, y_4th),
                (x_knight, y_prior),  # Terminal / Venables
                (x_knight, y_hast),
                (x_knight, y_port),
            ]
        ),
    }

    # --- Oak St arterial north of Hwy 99 / 70th transfer (to Broadway) ---
    _add_ns(highways, "oak_st", x_oak, y_70, y_bw, lanes=4)

    # --- Major N–S arterials (clipped at Marine; FC crossed only by bridges) ---
    west_ns = (
        ("dunbar_st", x_dunbar, y_4th, 4),
        ("macdonald_st", x_mac, y_4th, 4),
        ("arbutus_st", x_arb, y_16, 4),  # meets Burrard Bridge landing @ 16th
    )
    for key, x, y_top, lanes in west_ns:
        y0 = round(_marine_y(x), 1)
        _add_ns(highways, key, x, y0, y_top, lanes=lanes)

    # Blanca / UBC border — Marine curve up toward Chancellor.
    _add_ns(highways, "blanca_st", x_blanca, round(_marine_y(x_blanca), 1), y_ch, lanes=4)

    # Cambie — Marine → Broadway (Cambie Bridge continues north into Downtown).
    _add_ns(highways, "cambie_st", x_cam, y_mar, y_bw, lanes=4)

    # Main St full peninsula extent is owned by _build_downtown_peninsula.
    # Fraser — Gore viaduct lands at Y=216.5; arterial continues Marine ↔ Port.
    _add_ns(highways, "fraser_st", x_fraser, y_mar, y_port, lanes=4)

    east_ns = (
        ("victoria_dr", x_vic, y_port, 4),
        ("nanaimo_st", x_nan, y_port, 4),
        ("renfrew_st", x_ren, y_hast, 4),
        ("rupert_st", x_rup, y_hast, 4),
        ("joyce_st", x_joyce, y_bw, 4),
    )
    for key, x, y_top, lanes in east_ns:
        _add_ns(highways, key, x, y_mar, y_top, lanes=lanes)

    # Boundary Road — Vancouver east edge (Marine → Hastings / Hwy 1).
    _add_ns(highways, "boundary_rd", x_bound, y_mar, y_hast, lanes=4)

    # --- East–West major avenues ---
    # 49th Ave: Boundary → Dunbar (clips at Marine curve on the west).
    _add_ew(highways, "ave_49th", y_49, x_dunbar, x_bound, lanes=4)
    # 41st Ave: UBC / SW Marine → Joyce / Boundary.
    highways["ave_41st"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (-610.0, round(_marine_y(-610.0), 1)),
                (x_blanca, y_41),
                (x_dunbar, y_41),
                (x_gran, y_41),
                (x_oak, y_41),
                (x_main, y_41),
                (x_knight, y_41),
                (x_bound, y_41),
            ]
        ),
    }
    _add_ew(highways, "king_edward_ave", y_ke, x_dunbar, x_bound, lanes=4)
    # 16th Ave: UBC → Boundary.
    highways["ave_16th"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (x_wesbrook, y_16),
                (x_blanca, y_16),
                (x_dunbar, y_16),
                (x_gran, y_16),
                (x_cam, y_16),
                (x_main, y_16),
                (x_knight, y_16),
                (x_bound, y_16),
            ]
        ),
    }
    # Broadway — UBC → Boundary.
    highways["broadway"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (x_tip + 5.0, y_bw),
                (x_wesbrook, y_bw),
                (x_blanca, y_bw),
                (x_dunbar, y_bw),
                (x_gran, y_bw),
                (x_cam, y_bw),
                (x_main, y_bw),
                (x_vic, y_bw),
                (x_bound, y_bw),
            ]
        ),
    }
    # Grandview Highway / 12th Ave — Cambie / Clark → Boundary.
    _add_ew(highways, "grandview_hwy", y_gv, x_cam, x_bound, lanes=4)
    # Hastings St built in _build_downtown_peninsula (West Hastings → Boundary).

    # --- Kingsway diagonal ---
    highways["kingsway"] = {
        "lanes": 4,
        "points": yaml_pts(KINGSWAY_CTRL),
    }

    # --- Hwy 1 East Vancouver / Ironworkers approach ---
    highways["hwy1_van"] = {
        "lanes": 6,
        "points": yaml_pts(_dense_spline(HWY1_VAN_CTRL, segments=12)),
    }

    # --- West 4th / West 2nd / Great Northern Way (Y=+227) ---
    _add_ew(highways, "ave_4th", y_4th, -610.0, x_knight, lanes=4)
    # Terminal Ave / 1st Ave — False Creek Flats (Main → Clark).
    _add_ew(highways, "terminal_ave", y_term, x_main, x_knight, lanes=4)

    # --- False Creek bridges (abutments = downtown cross-street south ends) ---
    _add_route(highways, "burrard_bridge", BURRARD_BRIDGE_CTRL, lanes=4)
    _add_route(highways, "granville_bridge", GRANVILLE_BRIDGE_CTRL, lanes=6)
    _add_route(highways, "cambie_bridge", CAMBIE_BRIDGE_CTRL, lanes=4)

    # --- Downtown peninsula dual-grid (core ~42° + orthogonal DTES) ---
    _build_downtown_peninsula(highways)

    # Drop any local stub dangling inside the False Creek gap.
    _clip_false_creek_stubs(highways)

    # --- UBC / Point Grey loop ---
    highways["chancellor_blvd"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (x_blanca, y_ch),
                (x_wesbrook, y_ch),
                (x_tip + 5.0, y_ch),
            ]
        ),
    }
    highways["university_blvd"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (x_blanca, VAN_EW_Y["university"]),
                (x_wesbrook, VAN_EW_Y["university"]),
                (x_tip + 10.0, VAN_EW_Y["university"]),
            ]
        ),
    }
    _add_ns(highways, "wesbrook_mall", x_wesbrook, y_16, y_ch, lanes=4)
    # NW / SW Marine perimeter already in sw_marine; add short tip loop.
    highways["ubc_marine_loop"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (x_tip + 5.0, y_ch),
                (x_tip, 210.0),
                (x_tip, 195.0),
                (x_wesbrook, y_16),
            ]
        ),
    }

    # --- Secondary E–W collectors (half-mile) between Marine and Broadway ---
    for i, y in enumerate((105.5, 132.0, 153.5, 163.5, 185.0)):
        if _near(y, _MAJOR_YS, tol=2.0):
            continue
        _add_ew(highways, f"van_ew_{i}", y, x_dunbar, x_bound, lanes=2)

    # --- Dense urban fill (2-lane) — avoid river, False Creek, Stanley Park ---
    # Westside Kerrisdale / Kitsilano — N–S clipped to Marine curve (not flat Y=90).
    step = HALF_MILE
    x = x_dunbar + step
    n = 0
    while x < x_gran - 0.5:
        if not _near(x, _MAJOR_XS):
            y0 = round(_marine_y(x), 1) + 1.0
            if y0 < y_bw - 2.0:
                _add_ns(highways, f"van_west_ns_{n}", x, y0, y_bw, lanes=2)
                n += 1
        x += step
    # E–W collectors on the flat Marine shelf (Arbutus → Granville) only.
    _urban_grid(
        highways, "van_west_ew", x_arb, x_gran, y_mar + 2.0, y_bw, step=HALF_MILE
    )
    # South Cambie / Oakridge / Marpole (south of False Creek).
    _urban_grid(
        highways, "van_south", x_gran, x_main, y_mar + 2.0, y_fc_s, step=HALF_MILE
    )
    # East Vancouver — Main → Boundary, Marine → Broadway.
    _urban_grid(
        highways, "van_east", x_main, x_bound, y_mar + 2.0, y_bw, step=HALF_MILE
    )
    # Grandview–Woodland / Hastings–Sunrise (Broadway → Hastings).
    _urban_grid(
        highways, "van_ne", x_main, x_bound, y_bw, y_hast, step=HALF_MILE
    )
    # Fairview / Mount Pleasant south of Broadway (bridges own FC north of it).
    _urban_grid(
        highways, "van_fairview", x_cam, x_main, y_ke, y_bw, step=QUARTER_MILE
    )


def _bn_10th_y(x: float) -> float:
    """Y of 10th Avenue (Burnaby / New West border) at X."""
    return _interp_poly_y(BN_10TH_CTRL, x)


def _bn_ns_south_y(x: float) -> float:
    """Southern clip for Burnaby N–S arterials (Marine / Stewardson / 10th Ave)."""
    # SE Burnaby: clip at tilted 10th Ave so streets do not poke into New West.
    if -58.0 <= x <= 15.0:
        return _bn_10th_y(x)
    return _interp_poly_y(MARINE_STEWARDSON_CTRL, x)


def _bn_void_y_gaps(x: float) -> list[tuple[float, float]]:
    """Y intervals of park voids that contain this X (excluding lake cross shafts)."""
    gaps: list[tuple[float, float]] = []
    for x0, y0, x1, y1 in BN_PARK_VOIDS:
        if not (x0 <= x <= x1):
            continue
        if (x0, y0, x1, y1) == BN_VOID_BURNABY_LAKE and any(
            abs(x - ax) <= 0.6 for ax in BN_LAKE_CROSS_XS
        ):
            continue
        gaps.append((y0, y1))
    gaps.sort()
    return gaps


def _bn_void_x_gaps(y: float) -> list[tuple[float, float]]:
    """X intervals of park voids that contain this Y."""
    gaps: list[tuple[float, float]] = []
    for x0, y0, x1, y1 in BN_PARK_VOIDS:
        if y0 <= y <= y1:
            gaps.append((x0, x1))
    gaps.sort()
    return gaps


def _add_ns_split_voids(
    highways: dict,
    key: str,
    x: float,
    y0: float,
    y1: float,
    *,
    lanes: int = 2,
) -> None:
    """Add a N–S road, splitting around park voids that contain X."""
    if y0 > y1:
        y0, y1 = y1, y0
    gaps = _bn_void_y_gaps(x)
    if not gaps:
        _add_ns(highways, key, x, y0, y1, lanes=lanes)
        return
    cursor = y0
    part = 0
    for gy0, gy1 in gaps:
        if gy1 <= cursor or gy0 >= y1:
            continue
        seg_end = min(y1, gy0)
        if seg_end > cursor + 1.0:
            _add_ns(highways, f"{key}_{part}", x, cursor, seg_end, lanes=lanes)
            part += 1
        cursor = max(cursor, gy1)
    if y1 > cursor + 1.0:
        _add_ns(highways, f"{key}_{part}" if part else key, x, cursor, y1, lanes=lanes)


def _add_ew_split_voids(
    highways: dict,
    key: str,
    y: float,
    x0: float,
    x1: float,
    *,
    lanes: int = 2,
) -> None:
    """Add an E–W road, splitting around park voids that contain Y."""
    if x0 > x1:
        x0, x1 = x1, x0
    gaps = _bn_void_x_gaps(y)
    if not gaps:
        _add_ew(highways, key, y, x0, x1, lanes=lanes)
        return
    cursor = x0
    part = 0
    for gx0, gx1 in gaps:
        if gx1 <= cursor or gx0 >= x1:
            continue
        seg_end = min(x1, gx0)
        if seg_end > cursor + 1.0:
            _add_ew(highways, f"{key}_{part}", y, cursor, seg_end, lanes=lanes)
            part += 1
        cursor = max(cursor, gx1)
    if x1 > cursor + 1.0:
        _add_ew(
            highways, f"{key}_{part}" if part else key, y, cursor, x1, lanes=lanes
        )


def _bn_urban_grid(
    highways: dict,
    prefix: str,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    *,
    step: float = 10.0,
) -> None:
    """Dense 2-lane fill that skips Burnaby park / lake voids."""
    if y0 > y1:
        y0, y1 = y1, y0
    if x0 > x1:
        x0, x1 = x1, x0
    x = x0 + step
    n = 0
    while x < x1 - 0.5:
        if not _near(x, _MAJOR_XS):
            _add_ns_split_voids(highways, f"{prefix}_ns_{n}", x, y0, y1, lanes=2)
            n += 1
        x += step
    y = y0 + step
    n = 0
    while y < y1 - 0.5:
        if not _near(y, _MAJOR_YS):
            _add_ew_split_voids(highways, f"{prefix}_ew_{n}", y, x0, x1, lanes=2)
            n += 1
        y += step


def _build_burnaby(highways: dict) -> None:
    """City of Burnaby road network (flat Z=0 arterials only).

    Stitches onto Vancouver at Boundary Rd (X=-178): Marine, Kingsway, Canada
    Way / Grandview, Lougheed / Broadway, Hastings, and Hwy 1. Handoffs to New
    Westminster at 10th Ave / Kingsway / Canada Way / Stewardson; east border
    is North Rd (X=+52) toward Coquitlam. Deer Lake, Burnaby Lake, and Central
    Park stay open (no cross-street fill).
    """
    x_bound = BN_NS_X["boundary"]
    x_gil = BN_NS_X["gilmore"]
    x_alpha = BN_NS_X["alpha"]
    x_will = BN_NS_X["willingdon"]
    x_beta = BN_NS_X["beta"]
    x_oak = BN_NS_X["royal_oak"]
    x_nel = BN_NS_X["nelson"]
    x_sper = BN_NS_X["sperling"]
    x_ken = BN_NS_X["kensington"]
    x_gag = BN_NS_X["gaglardi"]
    x_car = BN_NS_X["cariboo"]
    x_north = BN_NS_X["north_rd"]

    y_rumble = BN_EW_Y["rumble"]
    y_imp = BN_EW_Y["imperial"]
    y_oak_st = BN_EW_Y["oakland"]
    y_hast = BN_EW_Y["hastings"]
    y_burrard = Y_BN_BURRARD
    y_lougheed = BN_EW_Y["lougheed_w"]

    # --- Hwy 1 Burnaby → Port Mann → Surrey snap (wider ~0.8) ---
    highways["hwy1_bn"] = {
        "lanes": 6,
        "points": yaml_pts(_dense_spline(HWY1_BN_CTRL, segments=16)),
    }

    # --- Marine Way → Stewardson handoff ---
    highways["marine_stewardson"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(MARINE_STEWARDSON_CTRL, segments=12)),
    }
    # North Fraser Way — Big Bend industrial parallel (Boundary → Byrne).
    _add_ew(highways, "north_fraser_way", BN_EW_Y["north_fraser"], x_bound, -85.0, lanes=2)

    # --- Kingsway (wider ~0.65) → New West entry ---
    highways["kingsway_bn"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(KINGSWAY_BN_CTRL, segments=12)),
    }

    # --- Canada Way (wider ~0.6) → New West entry ---
    highways["canada_way"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(CANADA_WAY_CTRL, segments=14)),
    }

    # --- Lougheed Hwy (Hwy 7, wider ~0.65) → Brunette Ave ---
    highways["lougheed_bn"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(LOUGHEED_BN_CTRL, segments=14)),
    }

    # --- Hastings St / Barnet Hwy ---
    highways["hastings_barnet"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(HASTINGS_BARNET_CTRL, segments=12)),
    }

    # --- Gaglardi Way (wider ~0.6) + Burnaby Mountain Pkwy ---
    highways["gaglardi_way"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(GAGLARDI_CTRL, segments=12)),
    }
    highways["bn_mtn_pkwy"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(BN_MTN_PKWY_CTRL, segments=8)),
    }

    # Brunette Ave owned by New Westminster (Sapperton → Hwy 1).

    # --- Major N–S arterials (clip at Marine / 10th Ave / Burrard) ---
    # Boundary Rd already owned by Vancouver (Marine → Hastings); extend north.
    _add_ns(highways, "boundary_rd_n", x_bound, y_hast, y_burrard, lanes=4)

    # SE spines clip cleanly on tilted 10th Ave / Cumberland (no New West poke).
    ns_major = (
        ("gilmore_ave", x_gil, None, y_burrard - 2.0, 4),
        ("willingdon_ave", x_will, None, y_burrard, 4),
        ("royal_oak_ave", x_oak, None, 175.0, 4),  # Marine → Canada Way
        ("nelson_ave", x_nel, None, y_oak_st, 4),  # Marine → Oakland / Deer Lake
        ("sperling_ave", x_sper, 100.0, y_hast, 4),  # Edmonds / 10th Ave band
        ("kensington_ave", x_ken, None, y_hast, 4),
        ("cariboo_rd", x_car, None, 195.0, 4),  # 10th Ave → Lougheed
    )
    for key, x, y_south, y_top, lanes in ns_major:
        y0 = round(y_south if y_south is not None else _bn_ns_south_y(x), 1)
        if y_top > y0 + 1.0:
            _add_ns_split_voids(highways, key, x, y0, y_top, lanes=lanes)

    # Alpha / Beta — Brentwood collectors (Canada Way → Hastings).
    _add_ns(highways, "alpha_ave", x_alpha, 185.0, y_hast, lanes=2)
    _add_ns(highways, "beta_ave", x_beta, 185.0, y_hast, lanes=2)

    # North Road — Brunette → Clarke (Coquitlam border; Barnet gap stays open north).
    _add_ns(highways, "north_rd", x_north, 135.0, Y_CQ_CLARKE, lanes=4)

    # --- Imperial / Rumble (South Burnaby) ---
    _add_ew(highways, "rumble_st", y_rumble, x_bound, x_sper, lanes=4)
    # Imperial: Boundary → Edmonds (angles toward Kingsway near Sperling).
    highways["imperial_st"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (x_bound, y_imp),
                (x_will, y_imp),
                (x_oak, y_imp),
                (x_nel, 116.0),
                (x_sper, 112.0),
            ]
        ),
    }

    # --- Broadway east of Gaglardi / Production Way band ---
    highways["bn_broadway_e"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (x_gag, 218.0),
                (x_car, BN_EW_Y["broadway_e"]),
                (x_north, BN_EW_Y["broadway_e"]),
            ]
        ),
    }

    # --- SFU / Burnaby Mountain oval ring ---
    sx, sy = SFU_CORE
    highways["sfu_ring"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (sx - 15.0, sy),
                (sx - 8.0, sy + 7.0),
                (sx + 10.0, sy + 7.0),
                (sx + 15.0, sy),
                (sx + 10.0, sy - 7.0),
                (sx - 5.0, sy - 10.0),
                (sx - 15.0, sy),
            ]
        ),
    }
    # Curtis / Hastings west spur into the ring.
    highways["sfu_hastings_spur"] = {
        "lanes": 2,
        "points": yaml_pts([(-15.0, 262.0), (sx - 15.0, sy)]),
    }

    # =====================================================================
    # Town-centre tight sub-grids (8–12 unit spacing) + named collectors
    # =====================================================================
    dense = 10.0

    # Metrotown — Central / Beresford / McKay / Sussex / Grange / Burke.
    _add_ew(highways, "central_blvd", 128.0, -152.0, x_nel, lanes=2)
    _add_ew(highways, "beresford_st", 134.0, -152.0, x_nel, lanes=2)
    _add_ew(highways, "grange_st", 140.0, -152.0, x_nel, lanes=2)
    _add_ns(highways, "mckay_ave", -148.0, y_rumble, 145.0, lanes=2)
    _add_ns(highways, "sussex_ave", -125.0, y_rumble, 145.0, lanes=2)
    _add_ew(highways, "burke_st", 124.0, x_will, x_nel, lanes=2)
    # Skip Central Park void on the west edge of the Metrotown box.
    _bn_urban_grid(
        highways, "metrotown", -152.0, x_nel, y_rumble, 145.0, step=dense
    )

    # Brentwood — Dawson / Alaska / Halifax / Parker + Alpha/Beta/Delta.
    _add_ew(highways, "dawson_st", 205.0, -165.0, -115.0, lanes=2)
    _add_ew(highways, "alaska_st", 210.0, -165.0, -115.0, lanes=2)
    _add_ew(highways, "halifax_st", 222.0, -165.0, -115.0, lanes=2)
    _add_ew(highways, "parker_st", 230.0, -165.0, -115.0, lanes=2)
    _add_ns(highways, "delta_ave", -148.0, 195.0, 235.0, lanes=2)
    _bn_urban_grid(
        highways, "brentwood", -165.0, -115.0, 195.0, 235.0, step=dense
    )

    # Edmonds / HighGate — stay west/north of New West wipe (10th Ave tilted border).
    _add_ew(highways, "edmonds_st", 105.0, -85.0, -58.0, lanes=4)
    _add_ns(highways, "griffiths_dr", -65.0, 105.0, 135.0, lanes=2)
    _add_ew(highways, "strachan_st", 118.0, -85.0, -55.0, lanes=2)
    _add_ew(highways, "ave_14th_bn", 100.0, -85.0, -58.0, lanes=2)
    _add_ew(highways, "ave_16th_bn", 112.0, -85.0, -55.0, lanes=2)
    _add_ew(highways, "ave_18th_bn", 125.0, -85.0, -55.0, lanes=2)
    _bn_urban_grid(
        highways, "edmonds", -85.0, -58.0, 105.0, 135.0, step=dense
    )

    # Lougheed Town Centre — Austin / Cameron / Bartlett / Beaverbrook.
    _add_ew(highways, "austin_rd", 205.0, 20.0, x_north, lanes=4)
    _add_ew(highways, "cameron_st", 195.0, 20.0, x_north, lanes=2)
    _add_ew(highways, "beaverbrook_dr", 180.0, 20.0, x_north, lanes=2)
    _add_ns(highways, "bartlett_ct", 30.0, 170.0, 215.0, lanes=2)
    _bn_urban_grid(
        highways, "lougheed_tc", 20.0, x_north, 170.0, 215.0, step=dense
    )

    # Secondary E–W collectors across Burnaby (split at park voids / SE border).
    for i, y in enumerate((100.0, 130.0, 155.0, 175.0, 190.0, 235.0, 250.0)):
        if _near(y, _MAJOR_YS, tol=2.0):
            continue
        if y <= Y_BN_MARINE + 2.0 or y >= y_burrard - 2.0:
            continue
        # Stop west of New West band for southern collectors.
        x_east = -55.0 if y < 120.0 else x_north
        _add_ew_split_voids(highways, f"bn_ew_{i}", y, x_bound, x_east, lanes=2)

    # Central / North Burnaby fill outside town centres and park voids.
    _bn_urban_grid(
        highways, "bn_central", x_will, -55.0, y_rumble, 200.0, step=HALF_MILE
    )
    _bn_urban_grid(
        highways, "bn_north", x_will, x_gag, 220.0, y_hast, step=HALF_MILE
    )
    # East Burnaby (Cariboo → North Rd) north of Hwy 1 / Brunette band.
    _bn_urban_grid(
        highways, "bn_east", x_car, x_north, 145.0, y_lougheed, step=HALF_MILE
    )


def _in_nw_wipe(x: float, y: float) -> bool:
    """True if (x,y) is interior Mainland New Westminster wipe box."""
    return NW_WIPE_X0 < x < NW_WIPE_X1 and NW_WIPE_Y0 < y < NW_WIPE_Y1


def _offset_polyline(
    controls: list[tuple[float, float]],
    dist: float,
) -> list[tuple[float, float]]:
    """Offset a polyline to the left of its overall forward direction by ``dist``."""
    if len(controls) < 2:
        return list(controls)
    dx = controls[-1][0] - controls[0][0]
    dy = controls[-1][1] - controls[0][1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    return [(x + nx * dist, y + ny * dist) for x, y in controls]


def _clip_poly_between_x(
    controls: list[tuple[float, float]],
    x0: float,
    x1: float,
) -> list[tuple[float, float]]:
    """Keep polyline vertices whose X lies between ``x0`` and ``x1``."""
    if x0 > x1:
        x0, x1 = x1, x0
    return [(x, y) for x, y in controls if x0 - 0.05 <= x <= x1 + 0.05]


def _seg_is_axis_aligned(
    p0: tuple[float, float] | list[float],
    p1: tuple[float, float] | list[float],
    *,
    tol: float = 0.05,
) -> bool:
    return abs(float(p0[0]) - float(p1[0])) <= tol or abs(
        float(p0[1]) - float(p1[1])
    ) <= tol


def _wipe_nw_axis_aligned(highways: dict) -> None:
    """Purge axis-aligned geometry inside the Mainland New West wipe box."""
    doomed: list[str] = []
    for key, route in list(highways.items()):
        if key in _NW_BOX_KEEP or key.startswith("nw_"):
            continue
        if any(key.startswith(p) for p in _BN_SE_KEEP_PREFIXES):
            continue
        pts = route.get("points") or []
        if len(pts) < 2:
            doomed.append(key)
            continue
        # Drop vertices inside the wipe box (orthogonal Burnaby stubs, etc.).
        kept: list[list[float]] = []
        for p in pts:
            x, y = float(p[0]), float(p[1])
            if _in_nw_wipe(x, y):
                continue
            kept.append([round(x, 1), round(y, 1)])
        cleaned: list[list[float]] = []
        for p in kept:
            if not cleaned or p != cleaned[-1]:
                cleaned.append(p)
        # Also drop any remaining axis-aligned chord whose midpoint is in-box.
        final: list[list[float]] = [cleaned[0]] if cleaned else []
        for i in range(1, len(cleaned)):
            a, b = final[-1], cleaned[i]
            mx = 0.5 * (a[0] + b[0])
            my = 0.5 * (a[1] + b[1])
            if _in_nw_wipe(mx, my) and _seg_is_axis_aligned(a, b):
                continue
            final.append(b)
        if len(final) < 2:
            doomed.append(key)
        else:
            route["points"] = final
    for key in doomed:
        del highways[key]


def _qb_cross_pts(x_anchor: float) -> list[tuple[float, float]]:
    """Tilted NW–SE Queensborough cross-street through ``x_anchor`` on Hwy 91A."""
    # Island ~18° NE–SW; cross-streets ~108° (perpendicular).
    a = math.radians(108.0)
    # Anchor Y on Hwy 91A corridor approx.
    y_mid = _interp_poly_y(
        [(-130.0, 36.0), (-95.0, 41.0), (-72.0, 44.0), (-55.0, 50.0)],
        x_anchor,
    )
    half = 10.0
    return [
        (x_anchor - half * math.cos(a), y_mid - half * math.sin(a)),
        (x_anchor + half * math.cos(a), y_mid + half * math.sin(a)),
    ]


def _build_new_westminster(highways: dict) -> None:
    """Mainland New Westminster tilted grid + Queensborough (roads only, Z=0).

    Strict rule: no axis-aligned (ΔX=0 / ΔY=0) segments inside
    X∈[-55,+28], Y∈[+48,+115]. River-parallel avenues ~32°; hill-climb
    cross-streets ~122°. Stitches onto Burnaby at 10th Ave / Kingsway /
    Canada Way / Stewardson, onto Richmond via Hwy 91A / Queensborough
    Bridge, and onto Surrey via Pattullo (0, +32).
    """
    # Purge any leftover orthogonal geometry in the mainland box first.
    _wipe_nw_axis_aligned(highways)

    # --- Extend Hwy 91A across Queensborough Bridge into Stewardson ---
    qb_ext = yaml_pts(_dense_spline(HWY91A_QB_CTRL, segments=14))
    if "hwy91a" in highways:
        base = highways["hwy91a"]["points"]
        # Drop Richmond tip duplicate, then append bridge corridor.
        highways["hwy91a"]["points"] = base[:-1] + qb_ext
        highways["hwy91a"]["lanes"] = 4
    else:
        highways["hwy91a"] = {"lanes": 4, "points": qb_ext}

    # =====================================================================
    # Mainland — river-parallel avenues (south → north)
    # =====================================================================
    highways["nw_front_st"] = {
        "lanes": 2,
        "points": yaml_pts(NW_FRONT_CTRL),
    }
    highways["nw_columbia_st"] = {
        "lanes": 4,
        "points": yaml_pts(NW_COLUMBIA_CTRL),
    }
    # Carnarvon / Clarkson — tight downtown parallels NW of Columbia.
    carn = _clip_poly_between_x(_offset_polyline(NW_COLUMBIA_CTRL, 2.2), -39.0, -7.0)
    clark = _clip_poly_between_x(_offset_polyline(NW_COLUMBIA_CTRL, 4.4), -39.0, -7.0)
    if len(carn) >= 2:
        highways["nw_carnarvon_st"] = {"lanes": 2, "points": yaml_pts(carn)}
    if len(clark) >= 2:
        highways["nw_clarkson_st"] = {"lanes": 2, "points": yaml_pts(clark)}

    highways["nw_royal_ave"] = {
        "lanes": 5,
        "points": yaml_pts(NW_ROYAL_CTRL),
    }
    # Queens / 3rd / 4th / 5th — spaced 4.2 units NW of Royal (20th St → McBride).
    for i, (key, dist) in enumerate(
        (
            ("nw_queens_ave", 4.2),
            ("nw_3rd_ave", 8.4),
            ("nw_4th_ave", 12.6),
            ("nw_5th_ave", 16.8),
        )
    ):
        pts = _clip_poly_between_x(
            _offset_polyline(NW_ROYAL_CTRL, dist), -54.0, -8.0
        )
        if len(pts) >= 2:
            highways[key] = {"lanes": 2, "points": yaml_pts(pts)}

    highways["nw_6th_ave"] = {
        "lanes": 4,
        "points": yaml_pts(NW_6TH_AVE_CTRL),
    }
    # 7th Ave — 4.2 units NW of 6th Ave.
    seventh = _clip_poly_between_x(
        _offset_polyline(NW_6TH_AVE_CTRL, 4.2), -58.0, -4.0
    )
    if len(seventh) >= 2:
        highways["nw_7th_ave"] = {"lanes": 2, "points": yaml_pts(seventh)}
    highways["nw_8th_ave"] = {
        "lanes": 2,
        "points": yaml_pts(NW_8TH_AVE_CTRL),
    }
    highways["nw_10th_ave"] = {
        "lanes": 4,
        "points": yaml_pts(NW_10TH_CTRL),
    }

    # =====================================================================
    # Mainland — hill-climb cross-streets (west → east)
    # =====================================================================
    highways["nw_stewardson"] = {
        "lanes": 4,
        "points": yaml_pts(NW_STEWARDSON_CTRL),
    }
    highways["nw_20th_st"] = {
        "lanes": 2,
        "points": yaml_pts(NW_20TH_CTRL),
    }
    highways["nw_14th_st"] = {
        "lanes": 2,
        "points": yaml_pts(NW_14TH_CTRL),
    }
    highways["nw_12th_st"] = {
        "lanes": 4,
        "points": yaml_pts(NW_12TH_CTRL),
    }
    highways["nw_10th_st"] = {
        "lanes": 2,
        "points": yaml_pts(NW_10TH_ST_CTRL),
    }
    highways["nw_8th_st"] = {
        "lanes": 4,
        "points": yaml_pts(NW_8TH_ST_CTRL),
    }
    highways["nw_6th_st"] = {
        "lanes": 4,
        "points": yaml_pts(NW_6TH_ST_CTRL),
    }
    # 4th / 2nd / 1st — Queen's Park cross-streets (4.5-unit spacing).
    # Interpolate between 6th St and McBride along the hill-climb axis.
    for key, t in (
        ("nw_4th_st", 0.28),
        ("nw_2nd_st", 0.55),
        ("nw_1st_st", 0.78),
    ):
        pts: list[tuple[float, float]] = []
        # Sample corresponding stations on 6th St and McBride, lerp.
        a_ctrl = NW_6TH_ST_CTRL
        b_ctrl = NW_MCBRIDE_CTRL[:6]  # stop at Columbia (before Pattullo tip)
        n = min(len(a_ctrl), len(b_ctrl))
        for i in range(n):
            ax, ay = a_ctrl[i]
            bx, by = b_ctrl[min(i, len(b_ctrl) - 1)]
            pts.append((ax + t * (bx - ax), ay + t * (by - ay)))
        # Clip to 8th/10th Ave band down to Royal (drop Front stubs).
        clipped = [(x, y) for x, y in pts if y >= 62.0]
        if len(clipped) >= 2:
            highways[key] = {"lanes": 2, "points": yaml_pts(clipped)}

    highways["mcbride_blvd"] = {
        "lanes": 5,
        "points": yaml_pts(NW_MCBRIDE_CTRL),
    }
    highways["brunette_ave"] = {
        "lanes": 5,
        "points": yaml_pts(NW_BRUNETTE_CTRL),
    }

    # =====================================================================
    # Queensborough peninsula (~18° tilted island grid)
    # =====================================================================
    highways["ewen_ave"] = {
        "lanes": 2,
        "points": yaml_pts(QB_EWEN_CTRL),
    }
    highways["boyd_st"] = {
        "lanes": 2,
        "points": yaml_pts(QB_BOYD_CTRL),
    }
    highways["salter_st"] = {
        "lanes": 2,
        "points": yaml_pts(QB_SALTER_CTRL),
    }
    for i, x in enumerate(QB_CROSS_XS):
        pts = _qb_cross_pts(x)
        # Clip cross-streets to the island Y band.
        pts = [(px, py) for px, py in pts if 28.0 <= py <= 55.0 and -135.0 <= px <= -48.0]
        if len(pts) < 2:
            # Fall back to short tilted segment around the anchor.
            a = math.radians(108.0)
            y_mid = _interp_poly_y(
                [(-130.0, 36.0), (-95.0, 41.0), (-72.0, 44.0)], x
            )
            pts = [
                (x - 6.0 * math.cos(a), y_mid - 6.0 * math.sin(a)),
                (x + 6.0 * math.cos(a), y_mid + 6.0 * math.sin(a)),
            ]
        highways[f"qb_cross_{i}"] = {"lanes": 2, "points": yaml_pts(pts)}

    # Final safety wipe: drop any leftover non-NW stubs inside the box.
    _wipe_nw_axis_aligned(highways)

    # Assert: no kept NW mainland route may contain an axis-aligned segment
    # whose midpoint sits inside the wipe box.
    for key in list(highways):
        if key not in _NW_BOX_KEEP and not key.startswith("nw_"):
            continue
        pts = highways[key].get("points") or []
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            mx = 0.5 * (float(a[0]) + float(b[0]))
            my = 0.5 * (float(a[1]) + float(b[1]))
            if _in_nw_wipe(mx, my) and _seg_is_axis_aligned(a, b):
                raise RuntimeError(
                    f"axis-aligned NW segment in wipe box: {key} {a}→{b}"
                )


def _cq_void_y_gaps(x: float) -> list[tuple[float, float]]:
    """Y intervals of Coquitlam park voids that contain this X."""
    gaps: list[tuple[float, float]] = []
    for x0, y0, x1, y1 in CQ_PARK_VOIDS:
        if x0 <= x <= x1:
            gaps.append((y0, y1))
    gaps.sort()
    return gaps


def _cq_void_x_gaps(y: float) -> list[tuple[float, float]]:
    """X intervals of Coquitlam park voids that contain this Y."""
    gaps: list[tuple[float, float]] = []
    for x0, y0, x1, y1 in CQ_PARK_VOIDS:
        if y0 <= y <= y1:
            gaps.append((x0, x1))
    gaps.sort()
    return gaps


def _add_ns_cq_voids(
    highways: dict,
    key: str,
    x: float,
    y0: float,
    y1: float,
    *,
    lanes: int = 2,
) -> None:
    if y0 > y1:
        y0, y1 = y1, y0
    gaps = _cq_void_y_gaps(x)
    if not gaps:
        _add_ns(highways, key, x, y0, y1, lanes=lanes)
        return
    cursor = y0
    part = 0
    for gy0, gy1 in gaps:
        if gy1 <= cursor or gy0 >= y1:
            continue
        seg_end = min(y1, gy0)
        if seg_end > cursor + 1.0:
            _add_ns(highways, f"{key}_{part}", x, cursor, seg_end, lanes=lanes)
            part += 1
        cursor = max(cursor, gy1)
    if y1 > cursor + 1.0:
        _add_ns(highways, f"{key}_{part}" if part else key, x, cursor, y1, lanes=lanes)


def _add_ew_cq_voids(
    highways: dict,
    key: str,
    y: float,
    x0: float,
    x1: float,
    *,
    lanes: int = 2,
) -> None:
    if x0 > x1:
        x0, x1 = x1, x0
    gaps = _cq_void_x_gaps(y)
    if not gaps:
        _add_ew(highways, key, y, x0, x1, lanes=lanes)
        return
    cursor = x0
    part = 0
    for gx0, gx1 in gaps:
        if gx1 <= cursor or gx0 >= x1:
            continue
        seg_end = min(x1, gx0)
        if seg_end > cursor + 1.0:
            _add_ew(highways, f"{key}_{part}", y, cursor, seg_end, lanes=lanes)
            part += 1
        cursor = max(cursor, gx1)
    if x1 > cursor + 1.0:
        _add_ew(
            highways, f"{key}_{part}" if part else key, y, cursor, x1, lanes=lanes
        )


def _cq_urban_grid(
    highways: dict,
    prefix: str,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    *,
    step: float = 10.0,
) -> None:
    """Dense 2-lane fill that skips Coquitlam park voids (Mundy Park)."""
    if y0 > y1:
        y0, y1 = y1, y0
    if x0 > x1:
        x0, x1 = x1, x0
    x = x0 + step
    n = 0
    while x < x1 - 0.5:
        if not _near(x, _MAJOR_XS):
            _add_ns_cq_voids(highways, f"{prefix}_ns_{n}", x, y0, y1, lanes=2)
            n += 1
        x += step
    y = y0 + step
    n = 0
    while y < y1 - 0.5:
        if not _near(y, _MAJOR_YS):
            _add_ew_cq_voids(highways, f"{prefix}_ew_{n}", y, x0, x1, lanes=2)
            n += 1
        y += step


def _build_north_vancouver(highways: dict) -> None:
    """North Vancouver road network north of Burrard Inlet (roads only, Z=0).

    Stitches onto Vancouver via Lions Gate (Hwy 99 at −495,+325) and
    Ironworkers Memorial (Hwy 1 at −255,+292). Open Burrard Inlet channel
    stays empty between Hastings/Cordova (Y≈+269–285) and Marine/Esplanade
    (Y≈+345–375). Terminates cleanly at the West Vancouver border
    (−640,+420 Hwy 1; −610,+345 Marine/Hwy 99) for further west stitching.
    """
    x_cap = NV_NS_X["capilano"]
    x_west = NV_NS_X["westview"]
    x_jones = NV_NS_X["jones"]
    x_lon = NV_NS_X["lonsdale"]
    x_grand = NV_NS_X["grand"]
    x_brook = NV_NS_X["brooksbank"]
    x_mtn = NV_NS_X["mountain"]
    x_main = NV_NS_X["main"]
    x_sey = NV_NS_X["seymour_rd"]
    x_ir = NV_NS_X["indian_river"]
    x_dc = NV_NS_X["deep_cove"]
    x_gallant = NV_NS_X["gallant"]

    y_mar = NV_EW_Y["marine"]
    y_main = NV_EW_Y["main_st"]
    y_3rd = NV_EW_Y["third"]
    y_keith = NV_EW_Y["keith"]
    y_13 = NV_EW_Y["thirteenth"]
    y_queens = NV_EW_Y["queens"]
    y_hwy1 = NV_EW_Y["hwy1_lonsdale"]
    y_29 = NV_EW_Y["twenty_ninth"]
    y_edge = NV_EW_Y["edgemont"]
    y_lynn = NV_EW_Y["lynn_centre"]
    y_dam = NV_EW_Y["capilano_dam"]
    y_resort = NV_EW_Y["seymour_resort"]

    # --- Hwy 1 Upper Levels (wider ~0.8) — Ironworkers → West Van ---
    highways["hwy1_nv"] = {
        "lanes": 6,
        "points": yaml_pts(_dense_spline(HWY1_NV_CTRL, segments=16)),
    }

    # --- Lions Gate Bridge approach (Hwy 99, wider ~0.8) ---
    highways["lions_gate"] = {
        "lanes": 6,
        "points": yaml_pts(LIONS_GATE_CTRL),
    }

    # --- Capilano Road (northwest spine, wider ~0.65) ---
    highways["capilano_rd"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(CAPILANO_RD_CTRL, segments=14)),
    }

    # --- Marine Drive / Esplanade (south waterfront clip, wider ~0.65) ---
    highways["marine_nv"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(MARINE_NV_CTRL, segments=12)),
    }

    # --- Keith Road (Marine west → Main / Hwy 1) ---
    highways["keith_rd"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(KEITH_RD_CTRL, segments=12)),
    }

    # --- Mount Seymour Parkway + Deep Cove loop ---
    highways["mt_seymour_pkwy"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(MT_SEYMOUR_PKWY_CTRL, segments=14)),
    }

    # --- City of North Vancouver N–S major arterials ---
    # Clip south at Marine / Esplanade so nothing stubs into Burrard Inlet.
    _add_ns(highways, "westview_dr", x_west, y_mar, y_29 + 15.0, lanes=4)
    _add_ns(highways, "jones_ave", x_jones, y_mar, y_29, lanes=4)
    _add_ns(highways, "lonsdale_ave", x_lon, y_mar, y_dam, lanes=5)
    _add_ns(highways, "grand_blvd", x_grand, y_mar, y_29, lanes=4)  # ~0.5 width
    _add_ns(highways, "brooksbank_ave", x_brook, y_mar + 5.0, y_lynn, lanes=4)

    # --- Main St (Ironworkers north landing) ---
    _add_ns(highways, "main_st_nv", x_main, y_main, y_keith + 5.0, lanes=5)

    # --- Mountain Highway ---
    _add_ns(highways, "mountain_hwy", x_mtn, y_main, y_dam, lanes=4)

    # --- Lynn Valley Road (Hwy 1 → Lynn Valley Town Centre) ---
    _add_ns(highways, "lynn_valley_rd", x_brook, NV_EW_Y["lynn_hwy1"], y_lynn, lanes=4)

    # --- Mount Seymour Road (Parkgate → ski resort) ---
    _add_ns(highways, "mt_seymour_rd", x_sey, y_main, y_resort, lanes=4)
    # Resort loop at the north tip.
    highways["mt_seymour_loop"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (x_sey, y_resort),
                (x_sey - 8.0, y_resort + 8.0),
                (x_sey + 8.0, y_resort + 10.0),
                (x_sey + 6.0, y_resort - 2.0),
                (x_sey, y_resort),
            ]
        ),
    }

    # --- Deep Cove / Indian River collectors ---
    _add_ns(highways, "indian_river_dr", x_ir, y_main, y_main + 25.0, lanes=3)
    _add_ns(highways, "deep_cove_rd", x_dc, y_main, y_main + 20.0, lanes=3)
    highways["gallant_ave"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (x_gallant, y_main),
                (x_gallant + 6.0, y_main + 10.0),
                (x_gallant, y_main + 20.0),
                (x_dc + 5.0, y_main + 15.0),
                (x_dc, y_main + 8.0),
            ]
        ),
    }

    # --- City of North Vancouver E–W major avenues ---
    _add_ew(highways, "third_st", y_3rd, x_west, x_brook, lanes=4)
    _add_ew(highways, "thirteenth_st", y_13, x_west, x_brook, lanes=3)
    _add_ew(highways, "queens_rd", y_queens, x_west, x_brook, lanes=4)
    _add_ew(highways, "twenty_ninth_st", y_29, x_west, x_brook, lanes=4)

    # Edgemont Blvd — Capilano Highlands cross-street.
    _add_ew(highways, "edgemont_blvd", y_edge, x_cap - 25.0, x_lon, lanes=3)

    # Montroyal / Highlands collectors (Upper Lonsdale / Capilano Highlands).
    _add_ew(highways, "montroyal_blvd", 445.0, x_cap - 15.0, x_lon + 20.0, lanes=2)
    _add_ew(highways, "highlands_blvd", 455.0, x_cap - 20.0, x_lon, lanes=2)
    # Grouse Mountain Skyride approach (Lonsdale north tip).
    highways["grouse_approach"] = {
        "lanes": 3,
        "points": yaml_pts(
            [
                (x_lon, y_dam - 15.0),
                (x_lon - 5.0, y_dam),
                (x_lon - 15.0, y_dam + 5.0),
                (x_lon - 25.0, y_dam + 8.0),
            ]
        ),
    }

    # =====================================================================
    # Neighbourhood sub-grids (8–12 unit CNV core; 15–25 unit highlands)
    # =====================================================================
    dense = 10.5  # ~0.4 km minor arterial spacing
    sparse = 21.1  # ~0.8 km / half-mile highland collectors

    # Lower Lonsdale / Central CNV — Marine → Hwy 1, Westview → Grand.
    _urban_grid(
        highways, "nv_lower", x_west, x_grand, y_mar + 1.0, y_hwy1, step=dense
    )
    # Midtown / Upper Lonsdale — Hwy 1 → 29th+, Jones → Grand.
    _urban_grid(
        highways, "nv_upper", x_jones, x_grand, y_hwy1, y_29 + 10.0, step=dense
    )
    # Grand Boulevard east → Brooksbank (Lynn Creek fringe).
    _urban_grid(
        highways, "nv_east", x_grand, x_brook, y_mar + 5.0, y_29, step=dense
    )
    # Capilano Highlands — winding collectors spaced 15–25 units.
    _urban_grid(
        highways,
        "nv_highlands",
        x_cap - 30.0,
        x_west,
        y_hwy1,
        y_dam,
        step=sparse,
    )
    # Upper Capilano / Edgemont — Capilano Rd → Lonsdale north of Edgemont.
    _urban_grid(
        highways, "nv_edgemont", x_cap - 20.0, x_lon, y_edge, y_dam, step=15.0
    )
    # Lynn Valley Town Centre — Brooksbank → Mountain Hwy, Hwy 1 → Lynn Centre.
    _urban_grid(
        highways,
        "nv_lynn",
        x_brook - 15.0,
        x_mtn + 15.0,
        NV_EW_Y["lynn_hwy1"],
        y_lynn + 10.0,
        step=dense,
    )
    # Seymour / Northlands — Main → Parkgate, light fill south of parkway north.
    _urban_grid(
        highways, "nv_seymour", x_main + 10.0, x_sey, y_main + 2.0, y_main + 40.0, step=sparse
    )
    # Parkgate / Deep Cove approach — sparse peninsula fill.
    _urban_grid(
        highways, "nv_parkgate", x_sey, x_ir, y_main + 2.0, y_main + 30.0, step=sparse
    )


def _build_coquitlam(highways: dict) -> None:
    """City of Coquitlam road network (flat Z=0 arterials only).

    Stitches onto Burnaby at North Rd (X=+52): Austin, Lougheed, Como Lake.
    Hwy 1 continues from Brunette (+35,+125) to Port Mann / Surrey (+64,+42.2).
    Lougheed / Mary Hill hand off to Port Coquitlam at Pinetree (+120,+195)
    and (+135,+82). Mundy Park stays open. Port Moody / Burrard Inlet band
    (Y≈+235–268 west of Westwood) left sparse.
    """
    x_north = CQ_NS_X["north_rd"]
    x_blue = CQ_NS_X["blue_mountain"]
    x_school = CQ_NS_X["schoolhouse"]
    x_mariner = CQ_NS_X["mariner"]
    x_johnson = CQ_NS_X["johnson"]
    x_pine = CQ_NS_X["pinetree"]
    x_cm = CQ_NS_X["coast_meridian"]
    x_pitt = CQ_NS_X["pitt_bridge"]
    x_westwood = PC_NS_X["westwood"]

    y_austin = CQ_EW_Y["austin"]
    y_lough = CQ_EW_Y["lougheed_w"]
    y_glen = CQ_EW_Y["glen"]
    y_como = CQ_EW_Y["como_lake"]
    y_guild = CQ_EW_Y["guildford"]
    y_david = CQ_EW_Y["david"]
    y_clarke = CQ_EW_Y["clarke"]
    # --- Hwy 1 Cape Horn → Port Mann (wider ~0.8) ---
    highways["hwy1_cq"] = {
        "lanes": 6,
        "points": yaml_pts(_dense_spline(HWY1_CQ_CTRL, segments=14)),
    }

    # --- Lougheed Hwy → Coquitlam Centre (PoCo continues) (wider ~0.65) ---
    highways["lougheed_cq"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(LOUGHEED_CQ_CTRL, segments=10)),
    }

    # --- Barnet Hwy / Town Centre connector (wider ~0.65) ---
    highways["barnet_cq"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(BARNET_CQ_CTRL, segments=10)),
    }

    # --- Mary Hill Bypass → PoCo seam (wider ~0.65) ---
    highways["mary_hill_bypass"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(MARY_HILL_CTRL, segments=10)),
    }

    # --- Brunette Ave Coquitlam leg (Hwy 1 → Blue Mountain) ---
    highways["brunette_cq"] = {
        "lanes": 4,
        "points": yaml_pts(BRUNETTE_CQ_CTRL),
    }

    # --- United Boulevard ---
    highways["united_blvd"] = {
        "lanes": 4,
        "points": yaml_pts(UNITED_BLVD_CTRL),
    }

    # --- Como Lake Ave (curves SE past Mundy Park to Lougheed) ---
    highways["como_lake_ave"] = {
        "lanes": 4,
        "points": yaml_pts(COMO_LAKE_CTRL),
    }

    # --- Pinetree Way + Westwood Plateau loop ---
    highways["pinetree_way"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(PINETREE_CTRL, segments=12)),
    }

    # North Road already owned by Burnaby (Brunette → Clarke).

    # --- N–S arterials ---
    _add_ns(highways, "blue_mountain_st", x_blue, 125.0, y_como, lanes=4)
    _add_ns(highways, "schoolhouse_st", x_school, 92.0, y_como, lanes=4)
    _add_ns(highways, "mariner_way", x_mariner, 90.0, CQ_EW_Y["barnet_dew"], lanes=4)
    _add_ns(highways, "johnson_st", x_johnson, y_lough, y_david, lanes=4)
    # Coast Meridian north of PoCo Burke handoff (Y=+245) — PoCo owns south.
    _add_ns(highways, "coast_meridian_rd", x_cm, 245.0, 275.0, lanes=4)

    # --- E–W arterials ---
    _add_ew(highways, "austin_ave", y_austin, x_north, x_mariner, lanes=4)
    _add_ew(highways, "glen_dr", y_glen, x_johnson, x_pine, lanes=4)
    _add_ew(highways, "guildford_way", y_guild, x_johnson, 145.0, lanes=4)
    _add_ew(highways, "david_ave", y_david, x_johnson, x_pitt, lanes=4)

    # Secondary E–W collectors (skip Mundy void + Port Moody open gap).
    # Stop at Westwood / Coquitlam River — PoCo owns east of X=+132.
    for i, y in enumerate((145.0, 155.0, 175.0, 195.0, 225.0)):
        if _near(y, _MAJOR_YS, tol=2.0):
            continue
        _add_ew_cq_voids(highways, f"cq_ew_{i}", y, x_north, x_westwood, lanes=2)

    # =====================================================================
    # Neighbourhood sub-grids + named collectors
    # =====================================================================
    dense = 10.0

    # Burquitlam / Austin Heights — Foster / Smith / Marmont / Linton.
    _add_ew(highways, "foster_ave", 175.0, x_north, x_school, lanes=2)
    _add_ew(highways, "smith_ave", 195.0, x_north, x_school, lanes=2)
    _add_ns(highways, "marmont_st", 60.0, y_austin, y_como, lanes=2)
    _add_ns(highways, "linton_st", 76.0, y_austin, y_como, lanes=2)
    _cq_urban_grid(
        highways, "burquitlam", x_north, 95.0, y_austin, 225.0, step=dense
    )

    # Maillardville — Laval / Rochester / Cartier / Alderson.
    _add_ew(highways, "rochester_ave", 140.0, 45.0, 80.0, lanes=2)
    _add_ew(highways, "cartier_ave", 130.0, 45.0, 80.0, lanes=2)
    _add_ew(highways, "alderson_ave", 150.0, 45.0, 80.0, lanes=2)
    _add_ns(highways, "laval_st", 58.0, 115.0, y_austin, lanes=2)
    _cq_urban_grid(
        highways, "maillardville", 45.0, 80.0, 115.0, y_austin, step=dense
    )

    # Coquitlam Town Centre — Lincoln / Glen / Anson / High.
    _add_ew(highways, "lincoln_ave", 200.0, 108.0, 135.0, lanes=2)
    _add_ew(highways, "anson_ave", 210.0, 108.0, 135.0, lanes=2)
    _add_ns(highways, "high_st", 128.0, 190.0, 225.0, lanes=2)
    _cq_urban_grid(
        highways, "coq_centre", 108.0, 135.0, 190.0, 225.0, step=8.0
    )

    # East Coquitlam fringe west of Coquitlam River / Westwood — light fill.
    _cq_urban_grid(
        highways, "cq_east", x_pine, x_westwood, 145.0, y_david, step=HALF_MILE
    )


def _pomo_inlet_blocks(x0: float, x1: float, y0: float, y1: float) -> bool:
    """True if the axis-aligned box overlaps the open Burrard Inlet tip void."""
    vx0, vy0, vx1, vy1 = POMO_VOID_INLET
    return not (x1 < vx0 or x0 > vx1 or y1 < vy0 or y0 > vy1)


def _build_port_moody(highways: dict) -> None:
    """City of Port Moody road network (flat Z=0 arterials only).

    U-shaped primary loop wraps the eastern tip of Burrard Inlet: Barnet Hwy
    west from Burnaby (+52,+268) → St Johns → Ioco Rd along the north shore,
    with Barnet east branching to Coquitlam (+95,+240). Guildford Way stitches
    to Coquitlam at Johnson (+112,+215). Clarke Rd snaps to North Rd (+52,+245).
    Inlet tip void X∈[+45,+82] Y∈[+255,+275] stays open (no crossing lines).
    """
    x_north = POMO_NS_X["north_rd"]
    x_cecile = POMO_NS_X["cecile"]
    x_merge = POMO_NS_X["clarke_merge"]
    x_moody = POMO_NS_X["moody"]

    y_clarke = POMO_EW_Y["clarke"]
    y_ravine = POMO_EW_Y["ravine"]

    # --- Primary U-loop: Barnet west → St Johns → Ioco (wider corridors) ---
    # Linear shoreline polyline (no Catmull bulge into Inlet tip void).
    highways["barnet_pomo_w"] = {
        "lanes": 5,
        "points": yaml_pts(BARNET_POMO_W_CTRL),
    }
    highways["st_johns_st"] = {
        "lanes": 5,  # ~0.65 unit commercial spine
        "points": yaml_pts(_dense_spline(ST_JOHNS_CTRL, segments=12)),
    }
    highways["barnet_pomo_e"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(BARNET_POMO_E_CTRL, segments=8)),
    }
    highways["ioco_rd"] = {
        "lanes": 4,  # ~0.55 unit north-shore spine
        "points": yaml_pts(_dense_spline(IOCO_RD_CTRL, segments=12)),
    }

    # --- South-shore / ridge arterials ---
    highways["clarke_rd_pomo"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(CLARKE_RD_POMO_CTRL, segments=8)),
    }
    highways["murray_st"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(MURRAY_ST_CTRL, segments=8)),
    }
    highways["moray_st"] = {
        "lanes": 4,
        "points": yaml_pts(MORAY_ST_CTRL),
    }
    # Cecile Drive — parallel 12 units west of Moray (Glenayre / College Park).
    _add_ns(highways, "cecile_dr", x_cecile, 228.0, 248.0, lanes=3)

    # --- Moody Centre historic grid (Clarke / Spring + tight N–S streets) ---
    highways["clarke_st_pomo"] = {
        "lanes": 2,
        "points": yaml_pts(CLARKE_ST_POMO_CTRL),
    }
    highways["spring_st_pomo"] = {
        "lanes": 2,
        "points": yaml_pts(SPRING_ST_POMO_CTRL),
    }
    # Queen / Kyle / Williams / Elgin / Moody / Buller — 3.5 unit spacing.
    moody_ns = (
        ("queen_st_pomo", 76.0),
        ("kyle_st", 79.5),
        ("williams_st_pomo", 83.0),
        ("elgin_st_pomo", 86.5),
        ("moody_st", 90.0),
        ("buller_st", 93.5),
    )
    for key, x in moody_ns:
        # South of St Johns / Clarke band; stop short of Murray / Inlet void.
        y1 = 255.0 if x >= x_moody - 0.1 else 252.0
        _add_ns(highways, key, x, 244.0, y1, lanes=2)

    # --- Newport Village / Suter Brook / Heritage Mountain ---
    highways["guildford_pomo"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(GUILDFORD_POMO_CTRL, segments=12)),
    }
    highways["ungless_heritage"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(UNGLESS_HERITAGE_CTRL, segments=10)),
    }
    # Village cross-streets spaced ~4.0 inside Newport / Suter Brook triangle.
    _add_ew(highways, "newport_dr", 258.0, 96.0, 108.0, lanes=2)
    _add_ew(highways, "brew_st", 262.0, 94.0, 106.0, lanes=2)
    _add_ew(highways, "suter_brook_way", 266.0, 94.0, 104.0, lanes=2)
    _add_ew(highways, "morrissey_rd", 254.0, 96.0, 110.0, lanes=2)
    _add_ns(highways, "newport_ns", 100.0, 250.0, 268.0, lanes=2)
    _add_ns(highways, "suter_ns", 104.0, 248.0, 270.0, lanes=2)
    # Ravine Drive + Turner Creek Dr on the Heritage Mountain hillside.
    _add_ew(highways, "ravine_dr", y_ravine, 98.0, 112.0, lanes=2)
    _add_ew(highways, "turner_creek_dr", 288.0, 100.0, 112.0, lanes=2)

    # --- Glenayre / College Park hillside loops ---
    # Glenayre south of Clarke Rd (residential hillside toward Coquitlam).
    highways["glenayre_dr"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (54.0, 244.0),
                (58.0, 238.0),
                (64.0, 234.0),
                (70.0, 232.0),
                (76.0, 236.0),
            ]
        ),
    }
    highways["harvard_dr"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (56.0, 242.0),
                (62.0, 236.0),
                (68.0, 233.0),
                (74.0, 235.0),
            ]
        ),
    }
    highways["princeton_ave"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (55.0, 240.0),
                (62.0, 232.0),
                (70.0, 228.0),
                (76.0, 230.0),
            ]
        ),
    }
    # College Park pocket between Clarke Rd and Barnet Hwy (south of Inlet).
    _add_ew(highways, "college_park_ew", 254.0, 56.0, 72.0, lanes=2)
    _add_ns(highways, "reed_point_dr", 62.0, 248.0, 258.0, lanes=2)

    # --- Anmore / Sunnyside north spine ---
    highways["sunnyside_rd"] = {
        "lanes": 3,
        "points": yaml_pts(SUNNYSIDE_RD_CTRL),
    }
    highways["east_rd_anmore"] = {
        "lanes": 2,
        "points": yaml_pts(EAST_RD_ANMORE_CTRL),
    }

    # =====================================================================
    # Neighbourhood sub-grids (skip Burrard Inlet tip void)
    # =====================================================================
    # Glenayre / College Park south of Clarke — collectors only.
    if not _pomo_inlet_blocks(x_north, x_merge, 232.0, y_clarke):
        _urban_grid(
            highways, "glenayre", x_north, x_merge, 232.0, y_clarke, step=10.0
        )
    # Moody Centre compact fill south of St Johns (outside Inlet void).
    _urban_grid(
        highways, "moody_centre", x_merge, 94.0, 244.0, 252.0, step=6.0
    )
    # Newport / Suter Brook triangle — east of Inlet tip X=+82.
    _urban_grid(
        highways, "newport", 92.0, 112.0, 248.0, 272.0, step=8.0
    )
    # Pleasantside / Ioco north-shore collectors (north of Inlet void).
    _urban_grid(
        highways, "pleasantside", 48.0, 90.0, 276.0, 292.0, step=10.0
    )


def _build_port_coquitlam(highways: dict) -> None:
    """City of Port Coquitlam road network (flat Z=0 arterials only).

    Stitches onto Coquitlam at Lougheed (+120,+195), Guildford Way (+145,+215),
    Coast Meridian (X=+155 at Lincoln Y=+205), and Mary Hill Bypass (+135,+82).
    Eastern roads clip on the Pitt River bank; south clips on Fraser / Mary Hill.
    Hands Lougheed to Pitt Meadows at the Pitt River Bridge (+175,+68).
    """
    x_ww = PC_NS_X["westwood"]
    x_sh = PC_NS_X["shaughnessy"]
    x_cm = PC_NS_X["coast_meridian"]
    x_ot = PC_NS_X["ottawa"]
    x_fr = PC_NS_X["fremont"]

    y_kw = PC_EW_Y["kingsway"]
    y_wilson = PC_EW_Y["wilson"]
    y_mcall = PC_EW_Y["mcallister"]
    y_dom = PC_EW_Y["dominion"]
    y_pr = PC_EW_Y["prairie"]
    y_nic = PC_EW_Y["nicola"]
    y_lin = PC_EW_Y["lincoln"]
    y_guild = PC_EW_Y["guildford"]

    # --- Lougheed Hwy → Pitt River Bridge (wider ~0.65) ---
    highways["lougheed_pc"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(LOUGHEED_PC_CTRL, segments=14)),
    }

    # --- Mary Hill Bypass PoCo leg (wider ~0.65) ---
    highways["mary_hill_pc"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(MARY_HILL_PC_CTRL, segments=10)),
    }

    # --- Fremont Connector / Burns Rd (wider ~0.65; keep on bank, no Catmull bulge) ---
    highways["fremont_connector"] = {
        "lanes": 5,
        "points": yaml_pts(FREMONT_CTRL),
    }

    # --- Pitt River Rd (winding SE arterial) ---
    highways["pitt_river_rd"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(PITT_RIVER_RD_CTRL, segments=10)),
    }

    # --- Citadel Drive (southern ridge loop) ---
    highways["citadel_dr"] = {
        "lanes": 3,
        "points": yaml_pts(CITADEL_CTRL),
    }

    # --- Lincoln Ave / Victoria Dr (Guildford → Cedar / Fremont) ---
    highways["lincoln_ave_pc"] = {
        "lanes": 4,
        "points": yaml_pts(LINCOLN_PC_CTRL),
    }

    # --- N–S major arterials ---
    _add_ns(highways, "westwood_st", x_ww, y_kw, y_guild, lanes=4)
    _add_ns(highways, "shaughnessy_st", x_sh, y_kw, y_lin, lanes=4)
    # Coast Meridian — Kingsway → Burke Mountain handoff (CQ continues north).
    _add_ns(highways, "coast_meridian_pc", x_cm, y_kw, 245.0, lanes=4)
    # Ottawa St — Lougheed → Nicola / Fremont.
    _add_ns(highways, "ottawa_st", x_ot, 100.0, y_nic, lanes=5)

    # --- E–W major arterials (clip east on Pitt River bank) ---
    _add_ew(highways, "kingsway_ave_pc", y_kw, x_ww, 160.0, lanes=4)
    _add_ew(highways, "wilson_ave", y_wilson, x_ww, x_cm, lanes=3)
    _add_ew(highways, "mcallister_ave", y_mcall, x_ww, x_cm, lanes=3)
    _add_ew(highways, "dominion_ave", y_dom, x_sh, x_fr, lanes=4)
    _add_ew(highways, "prairie_ave", y_pr, 130.0, 190.0, lanes=4)
    _add_ew(highways, "nicola_ave", y_nic, x_sh, 172.0, lanes=4)

    # =====================================================================
    # Neighbourhood sub-grids + named collectors
    # =====================================================================
    # Downtown Port Coquitlam — compact 6–10 unit grid (Kingsway → Lougheed).
    _add_ew(highways, "elgin_ave", 120.0, x_ww, x_cm, lanes=2)
    _add_ew(highways, "kelly_ave", 132.0, x_ww, x_cm, lanes=2)
    _add_ew(highways, "bury_ave", 138.0, x_ww, x_sh, lanes=2)
    _add_ns(highways, "mary_hill_rd", 136.0, y_kw, 145.0, lanes=2)
    _add_ns(highways, "donald_st", 148.0, y_kw, 145.0, lanes=2)
    _add_ns(highways, "leigh_st", 150.0, y_kw, y_dom, lanes=2)
    _urban_grid(highways, "poco_dt", x_ww, x_cm, y_kw, 145.0, step=8.0)

    # Lincoln Park & Riverwood — suburban collectors ~10 unit spacing.
    _add_ns(highways, "oxford_st", 138.0, 155.0, y_lin, lanes=2)
    _add_ns(highways, "wellington_st", 148.0, 155.0, y_lin, lanes=2)
    _add_ns(highways, "hawkins_st", 160.0, y_pr, y_lin, lanes=2)
    _add_ns(highways, "blakeburn_st", 178.0, y_pr, y_nic, lanes=2)
    _add_ew(highways, "fremont_st", 175.0, x_sh, min(x_fr, pc_pitt_x(175.0)), lanes=2)
    _urban_grid(
        highways,
        "lincoln_park",
        x_ww,
        min(185.0, pc_pitt_x(180.0)),
        155.0,
        y_lin,
        step=10.0,
    )

    # Mary Hill & Citadel Heights — residential cross-streets south of Kingsway.
    _add_ew(highways, "hawthorne_ave", 105.0, 135.0, 160.0, lanes=2)
    _add_ew(highways, "rosedale_ave", 95.0, 138.0, 162.0, lanes=2)
    _add_ns(highways, "chatham_st", 148.0, 78.0, y_kw, lanes=2)
    _add_ns(highways, "confederation_dr", 158.0, 80.0, y_kw, lanes=2)
    _urban_grid(highways, "mary_hill", 135.0, 168.0, 75.0, y_kw, step=10.0)


def _build_pitt_meadows(highways: dict) -> None:
    """Pitt Meadows plate west of Laity / 207 St (roads only, Z = 0).

    Stitches onto Maple Ridge at X=+353 (Lougheed, Ford/Hammond, Dewdney) and
    onto Golden Ears at X=+316.5. Westbound roads terminate at the Pitt River
    Bridge (X=+175); nothing stubs into the Fraser gap south of Airport Way.
    """
    # --- Lougheed Highway (Hwy 7) — full PM → MR corridor (single route) ---
    highways["lougheed_hwy"] = {
        "lanes": 6,
        "points": yaml_pts(_dense_spline(LOUGHEED_CTRL, segments=14)),
    }

    # --- Airport Way — southern industrial / airport spine ---
    highways["airport_way"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (316.5, 58.0),  # Golden Ears landing
                (X_HARRIS, Y_AIRPORT),
                (X_BONSON, Y_AIRPORT),
                (245.0, 50.0),  # Pitt Meadows Regional Airport loop
            ]
        ),
    }
    # Small airport loop stub (Baynes Rd / apron).
    highways["airport_loop"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (245.0, 50.0),
                (238.0, 48.0),
                (232.0, 52.0),
                (238.0, 56.0),
                (245.0, 50.0),
            ]
        ),
    }

    # --- Ford Road / Hammond Road — E–W into Maple Ridge Hammond ---
    highways["ford_hammond_rd"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (X_FORD, Y_FORD_HAMMOND),
                (X_HARRIS, Y_FORD_HAMMOND),
                (316.5, Y_FORD_HAMMOND),
                (X_LAITY, Y_FORD_HAMMOND),
                (377.0, Y_FORD_HAMMOND),  # into West Maple Ridge / Hammond
            ]
        ),
    }

    # --- Harris Road → McNeil / Neaves (downtown N–S spine) ---
    highways["harris_rd"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (X_HARRIS, Y_AIRPORT),
                (X_HARRIS, Y_FORD_HAMMOND),
                (X_HARRIS, 72.0),
                (X_HARRIS, Y_DEWDNEY),
                (X_HARRIS, Y_OLD_DEWDNEY),
                (X_HARRIS, 125.0),
                (X_HARRIS, 145.0),
            ]
        ),
    }

    # --- Park Road / 122 Ave — snaps onto Dewdney Trunk at Laity ---
    # Built as the western Dewdney Trunk approach (single continuous key below
    # is owned by Maple Ridge from Laity east; this segment ends at the border).
    highways["pm_park_rd"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (X_BONSON, Y_DEWDNEY),
                (X_HARRIS, Y_DEWDNEY),
                (316.5, Y_DEWDNEY),
                (332.0, Y_DEWDNEY),
                (X_LAITY, Y_DEWDNEY),
            ]
        ),
    }

    # --- Old Dewdney Trunk Road (Polder cross-road) ---
    highways["old_dewdney_trunk"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (X_HARRIS, Y_OLD_DEWDNEY),
                (X_BONSON, Y_OLD_DEWDNEY),
                (X_FORD, 94.0),
                (X_RANNIE, 93.0),
                (X_KENNEDY, 92.0),
            ]
        ),
    }

    # --- Neaves / McNeil Road (north Polder cross-road) ---
    highways["neaves_mcneil"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (X_RANNIE, Y_NEAVES),
                (X_FORD, 130.0),
                (X_HARRIS, 125.0),
            ]
        ),
    }

    # --- Pitt Polder N–S rural spines ---
    highways["pm_rannie"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (X_RANNIE, 72.0),  # Lougheed
                (X_RANNIE, Y_OLD_DEWDNEY),
                (X_RANNIE, Y_NEAVES),
                (X_RANNIE, Y_PITT_LAKE),  # Grant Narrows / Pitt Lake
            ]
        ),
    }
    highways["pm_kennedy"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (X_KENNEDY, 70.0),  # Lougheed
                (X_KENNEDY, 92.0),  # Old Dewdney Trunk
            ]
        ),
    }
    # Bonson Rd — urban west edge (Airport → Old Dewdney).
    _add_ns(highways, "pm_bonson", X_BONSON, Y_AIRPORT, Y_OLD_DEWDNEY, lanes=4)
    # Ford / McMyn Rd — Airport → Lougheed / Old Dewdney band.
    _add_ns(highways, "pm_ford_rd", X_FORD, Y_AIRPORT, Y_OLD_DEWDNEY, lanes=2)
    # Blakely / 203 St is owned by Maple Ridge (mr_st_203) — no duplicate shaft.

    # Urban townsite collectors (116B / 119 / 124 Ave equivalents).
    _add_ew(highways, "pm_ave_116b", 58.0, X_BONSON, X_LAITY, lanes=2)
    _add_ew(highways, "pm_ave_119", 68.0, X_BONSON, X_LAITY, lanes=2)
    _add_ew(highways, "pm_ave_124", 105.5, X_HARRIS, X_LAITY, lanes=2)

    # Compact suburban fill — Bonson → Laity, Airport → Old Dewdney.
    _urban_grid(
        highways,
        "pm_town",
        285.0,
        X_LAITY,
        Y_AIRPORT,
        Y_OLD_DEWDNEY,
        step=QUARTER_MILE,
    )


def _build_maple_ridge(highways: dict) -> None:
    """Maple Ridge road plate north of the Fraser (roads only, Z = 0).

    Connects solely via the Golden Ears Bridge corridor at 200 St. All N–S
    streets clip at River Road / Lougheed so nothing stubs into the open
    Fraser gap above Langley. Lougheed Hwy is owned by Pitt Meadows builder
    (full PM→MR polyline); Dewdney Trunk starts at Laity / 207 St.
    """
    # --- River Road / Wharf Street — southern shoreline (no river stubs) ---
    # Piecewise-linear (matches mr_river_y clip) — no Catmull-Rom south bow.
    river_pts: list[tuple[float, float]] = []
    for i in range(len(MR_RIVER_CTRL) - 1):
        chunk = _dense_spline(MR_RIVER_CTRL[i : i + 2], segments=10)
        river_pts.extend(chunk if i == 0 else chunk[1:])
    highways["mr_river_rd"] = {
        "lanes": 2,
        "points": yaml_pts(river_pts),
    }

    # --- Haney Bypass (Hwy 7 riverside relief) ---
    highways["haney_bypass"] = {
        "lanes": 4,
        "points": yaml_pts(
            _dense_spline(
                [
                    (432.0, 58.0),  # branch off Lougheed at 222 St
                    (443.1, 48.0),  # riverside at 224 St
                    (464.2, 46.0),  # 228 St waterfront
                    (485.3, 45.0),  # merge near Kanaka Way / 232 St
                ],
                segments=12,
            )
        ),
    }

    # --- Dewdney Trunk Road — continues east from Laity / Park Road snap ---
    highways["dewdney_trunk"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (X_LAITY, Y_DEWDNEY),  # snaps onto pm_park_rd
                (443.1, Y_DEWDNEY),
                (569.7, Y_DEWDNEY),
                (611.9, Y_DEWDNEY),
                (654.1, 55.0),
                (696.3, 15.0),  # meet Lougheed near Whonnock
            ]
        ),
    }

    # --- Major N–S streets (clipped at River Road / Lougheed on the south) ---
    # (street, x, y_north, lanes)
    mr_ns: list[tuple[int, float, float, int]] = [
        (203, 332.0, 115.0, 4),
        (207, 353.0, 115.0, 4),
        (210, 377.0, 115.0, 2),
        (216, 400.9, 165.0, 4),
        (222, 432.0, 115.0, 4),
        (224, 443.1, 165.0, 4),
        (228, 464.2, 115.0, 2),
        (232, 485.3, 165.0, 4),
        (240, 527.5, 105.5, 4),
        (248, 569.7, 126.6, 2),
        (256, 611.9, 95.0, 2),
        (264, 654.1, 75.0, 2),
        (272, 696.3, 55.0, 2),
        (280, 738.5, 45.0, 2),
        (287, 775.0, 35.0, 2),
    ]
    for st, x, y_north, lanes in mr_ns:
        # West/central: clip at River Road. East of Albion: Lougheed is the
        # practical southern bound (river and Hwy 7 converge).
        if x >= 505.0:
            y_south = mr_lougheed_y(x)
        else:
            y_south = mr_river_y(x)
        if y_north <= y_south + 1.0:
            continue
        _add_ns(highways, f"mr_st_{st}", x, y_south, y_north, lanes=lanes)

    # --- East–west avenues (bounded west/east per community extent) ---
    # 116 Ave — local collector through West Maple Ridge / Haney
    _add_ew(highways, "mr_ave_116", 72.0, 332.0, 485.3, lanes=2)
    # 122 Ave — between Dewdney and 124 Ave
    _add_ew(highways, "mr_ave_122", 94.95, 332.0, 485.3, lanes=2)
    # 124 Avenue
    _add_ew(highways, "mr_ave_124", MR_AVE_Y[124], 332.0, 569.7, lanes=4)
    # 128 Avenue
    _add_ew(highways, "mr_ave_128", MR_AVE_Y[128], 400.9, 569.7, lanes=2)
    # 132 Avenue (Silver Valley / Alouette foothills)
    _add_ew(highways, "mr_ave_132", MR_AVE_Y[132], 400.9, 527.5, lanes=2)
    # 136 Avenue (Silver Valley north tip)
    _add_ew(highways, "mr_ave_136", MR_AVE_Y[136], 443.1, 505.0, lanes=2)

    # Albion collectors between Lougheed and Dewdney (104 / 112 Ave loops).
    alb_x0, alb_x1 = 505.0, 550.0
    alb_y_lougheed = mr_lougheed_y(527.5)
    _add_ew(highways, "mr_alb_104", alb_y_lougheed + 18.0, alb_x0, alb_x1, lanes=2)
    _add_ew(highways, "mr_alb_112", alb_y_lougheed + 36.0, alb_x0, alb_x1, lanes=2)

    # East rural northern bound (112 Ave / 128 Ave stepping down eastward).
    highways["mr_rural_north"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (550.0, 95.0),
                (611.9, 95.0),
                (654.1, 75.0),
                (696.3, 55.0),
                (738.5, 45.0),
                (775.0, 35.0),
            ]
        ),
    }

    # --- Dense urban sub-grids ---
    # West Maple Ridge & Haney (203–232 St, River → ~124 Ave).
    _urban_grid(
        highways, "mr_haney", 332.0, 485.3, 55.0, 115.0, step=QUARTER_MILE
    )
    # Silver Valley — north of 124 Ave to 132 / 136 Ave.
    _urban_grid(
        highways, "mr_sv", 443.1, 505.0, 105.5, 165.0, step=HALF_MILE
    )
    # Albion — Lougheed → Dewdney around 240 St.
    _urban_grid(
        highways, "mr_alb", 505.0, 550.0, 30.0, Y_DEWDNEY, step=HALF_MILE
    )

    # --- East Maple Ridge rural 1-mile concession grid ---
    # N–S shafts already placed above; add half-mile E–W farm roads clipped to
    # stay between Lougheed (south) and the stepping-down northern envelope.
    rural_ew_ys = [75.0, 55.0, 35.0]
    for i, y in enumerate(rural_ew_ys):
        x0 = 550.0
        # Find eastern extent where y is still south of rural_north and north of Lougheed.
        x1 = X_MR_EAST
        for x_probe in (611.9, 654.1, 696.3, 738.5, 775.0):
            if y >= _mr_rural_north_y(x_probe) - 1.0:
                x1 = x_probe
                break
        if y <= mr_lougheed_y(x0) + 2.0:
            continue
        if x1 <= x0 + 2.0:
            continue
        _add_ew(highways, f"mr_rural_ew_{i}", y, x0, x1, lanes=2)

    # Half-mile N–S collectors in the east rural belt (not on major miles).
    for st in (244, 252, 260, 268, 276):
        x = st_x(st)
        y_south = mr_lougheed_y(x)
        y_north = _mr_rural_north_y(x)
        if y_north <= y_south + 2.0:
            continue
        _add_ns(highways, f"mr_col_st_{st}", x, y_south, y_north, lanes=2)


def _build_delta(highways: dict) -> None:
    """Stitch Delta west of Scott Rd onto the Surrey / Langley plate."""
    _build_north_delta(highways)
    _build_ladner(highways)
    _build_tsawwassen(highways)

    # Rural East Delta concession grid (42.2 spacing west of Hwy 91).
    # Stay east of Ladner town centre and south of Burns Bog / Hwy 99.
    rural_x0, rural_x1 = -274.0, -168.8
    rural_y0, rural_y1 = -265.0, -190.0
    rural_ns = (
        (104, -168.8),
        (96, -211.0),
        (88, -253.2),
        (72, -232.1),
        (64, -274.3),
    )
    placed_x: set[float] = set()
    for st, x in rural_ns:
        if not (rural_x0 - 0.5 <= x <= rural_x1 + 0.5):
            continue
        if any(abs(x - px) < 1.0 for px in placed_x):
            continue
        if _in_burns_bog(x, (rural_y0 + rural_y1) * 0.5):
            continue
        _add_ns(highways, f"delta_st_{st}", x, rural_y0, rural_y1, lanes=2)
        placed_x.add(x)

    # 34B Ave & 28 Ave farm roads across the rural band (south of the bog).
    for y, key in ((-211.0, "delta_ave_34b"), (-253.2, "delta_ave_28")):
        _add_ew(highways, key, y, rural_x0, rural_x1, lanes=2)


# =====================================================================
# Post-georef Burnaby / New Westminster / Queensborough stitch (world XY)
# =====================================================================

# Hwy 91A spine through Queensborough → Stewardson (Google Maps world coords).
HWY91A_WORLD_CTRL: list[tuple[float, float]] = [
    (-235.0, -35.0),  # Hwy 91 / 91A fork (East Richmond)
    (-205.0, -22.0),
    (-175.0, -5.0),  # Queensborough centre
    (-145.0, 10.0),
    (-148.0, 26.0),  # Stewardson Way / 20th St
]

# Ewen Ave — 4.5u south of Hwy 91A, parallel island arterial.
EWEN_WORLD_CTRL: list[tuple[float, float]] = [
    (-215.0, -30.0),
    (-190.0, -18.0),
    (-160.0, -2.0),
    (-130.0, 12.0),
]

# Named Queensborough cross-streets (Howes → Boyne), west → east.
QB_CROSS_WORLD: tuple[tuple[str, float], ...] = (
    ("howes_st", 0.18),
    ("pembroke_st", 0.40),
    ("wood_st", 0.62),
    ("boyne_st", 0.82),
)

# Burnaby → New West corridor stitches (world XY).
MARINE_STEWARDSON_WORLD: list[tuple[float, float]] = [
    (-304.0, 42.0),
    (-250.0, 42.0),
    (-185.0, 42.0),
    (-165.0, 36.0),
    (-148.0, 26.0),  # Stewardson / Columbia handoff
]
KINGSWAY_BN_WORLD: list[tuple[float, float]] = [
    (-304.4, 106.4),  # Metrotown
    (-250.0, 88.0),
    (-195.0, 68.0),  # Edmonds
    (-165.0, 55.0),
    (-142.0, 48.0),  # NW 12th St north end
]
CANADA_WAY_WORLD: list[tuple[float, float]] = [
    (-235.0, 125.0),  # Deer Lake
    (-200.0, 105.0),
    (-165.0, 88.0),
    (-140.0, 72.0),
    (-118.0, 58.0),  # McBride Blvd north end
]
# 10th Avenue — Burnaby / New West tilted border (west→east, covers BN N–S clips).
NW_10TH_WORLD: list[tuple[float, float]] = [
    (-283.3, 72.0),  # Royal Oak
    (-262.2, 68.0),  # Nelson
    (-241.1, 58.0),  # Sperling / Edmonds
    (-220.0, 48.0),  # Kensington band
    (-185.0, 42.0),
    (-150.0, 45.0),  # user landmark
    (-125.0, 55.0),
    (-105.0, 65.0),  # user landmark
]
BRUNETTE_WORLD: list[tuple[float, float]] = [
    (-95.0, 52.0),  # East Columbia / Brunette
    (-80.0, 68.0),
    (-65.0, 85.0),
    (-20.0, 120.0),
    (23.4, 184.5),  # Hwy 1 Cape Horn (Coquitlam)
    (40.4, 244.5),  # Lougheed / North Rd (Coquitlam)
]
MCBRIDE_PATTULLO_WORLD: list[tuple[float, float]] = [
    (-118.0, 58.0),  # Canada Way / McBride north
    (-112.0, 42.0),
    (-108.0, 28.0),  # south McBride / Pattullo abutment
    (-95.0, 10.0),
    (-75.0, -5.0),  # Surrey King George / 108 Ave approach
    (-40.0, -2.0),
    (0.0, 0.0),  # Whalley / King George & 104 Ave
]

# Floating-stub purge boxes (world XY).
_QB_FLOAT_BOX = (-200.0, -135.0, -20.0, 15.0)
_NW_STRAY_BOX = (-95.0, -65.0, 20.0, 65.0)


def _pt_in_box(
    x: float,
    y: float,
    box: tuple[float, float, float, float],
) -> bool:
    x0, x1, y0, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


def _lerp_poly(
    poly: Sequence[tuple[float, float]],
    t: float,
) -> tuple[float, float]:
    """Point at normalized arc-length fraction t ∈ [0, 1] along polyline."""
    if not poly:
        return (0.0, 0.0)
    if len(poly) == 1 or t <= 0.0:
        return poly[0]
    if t >= 1.0:
        return poly[-1]
    seg_lens = [
        math.hypot(poly[i + 1][0] - poly[i][0], poly[i + 1][1] - poly[i][1])
        for i in range(len(poly) - 1)
    ]
    total = sum(seg_lens) or 1.0
    target = t * total
    acc = 0.0
    for i, sl in enumerate(seg_lens):
        if acc + sl >= target:
            u = 0.0 if sl < 1e-9 else (target - acc) / sl
            x0, y0 = poly[i]
            x1, y1 = poly[i + 1]
            return (x0 + u * (x1 - x0), y0 + u * (y1 - y0))
        acc += sl
    return poly[-1]


def _perp_unit(poly: Sequence[tuple[float, float]], t: float) -> tuple[float, float]:
    """Unit perpendicular (left of travel) at fraction t along polyline."""
    t0 = max(0.0, min(1.0, t - 0.02))
    t1 = max(0.0, min(1.0, t + 0.02))
    ax, ay = _lerp_poly(poly, t0)
    bx, by = _lerp_poly(poly, t1)
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1.0
    return (-dy / L, dx / L)


def _purge_box_orphans(
    highways: dict,
    box: tuple[float, float, float, float],
    *,
    drop_keys: frozenset[str] | None = None,
    protect: frozenset[str] | None = None,
) -> None:
    """Delete short orphans / strip vertices inside a floating-stub box."""
    drop_keys = drop_keys or frozenset()
    protect = protect or frozenset()
    doomed: list[str] = []
    for key, route in list(highways.items()):
        if key in drop_keys:
            doomed.append(key)
            continue
        if key in protect:
            continue
        pts = route.get("points") or []
        if len(pts) < 2:
            doomed.append(key)
            continue
        inside = [
            p
            for p in pts
            if _pt_in_box(float(p[0]), float(p[1]), box)
        ]
        if not inside:
            continue
        # Whole route (or almost) lives in the float box → delete.
        if len(inside) >= max(1, len(pts) - 1) and len(pts) <= 6:
            doomed.append(key)
            continue
        # Otherwise strip in-box vertices.
        kept = [
            [round(float(p[0]), 1), round(float(p[1]), 1)]
            for p in pts
            if not _pt_in_box(float(p[0]), float(p[1]), box)
        ]
        cleaned: list[list[float]] = []
        for p in kept:
            if not cleaned or p != cleaned[-1]:
                cleaned.append(p)
        if len(cleaned) < 2:
            doomed.append(key)
        else:
            route["points"] = cleaned
    for key in doomed:
        highways.pop(key, None)


def _replace_route_tail(
    highways: dict,
    key: str,
    fork: tuple[float, float],
    new_tail: list[tuple[float, float]],
    *,
    lanes: int,
    join_radius: float = 40.0,
) -> None:
    """Keep route west/south of ``fork``, then append densified ``new_tail``."""
    densified = _dense_spline(new_tail, segments=14)
    if key not in highways:
        highways[key] = {"lanes": lanes, "points": yaml_pts(densified)}
        return
    pts = highways[key].get("points") or []
    fx, fy = fork
    keep: list[list[float]] = []
    for p in pts:
        x, y = float(p[0]), float(p[1])
        # Drop vertices near or past the fork along the new corridor (east/north).
        if math.hypot(x - fx, y - fy) <= join_radius and x >= fx - 5.0:
            break
        if x > fx + 15.0 and y > fy - 10.0:
            break
        keep.append([round(x, 1), round(y, 1)])
    # Ensure fork is present as join vertex.
    if not keep or math.hypot(keep[-1][0] - fx, keep[-1][1] - fy) > 0.5:
        keep.append([round(fx, 1), round(fy, 1)])
    else:
        keep[-1] = [round(fx, 1), round(fy, 1)]
    # Skip duplicate first densified point if it equals fork.
    tail = densified[1:] if densified and math.hypot(
        densified[0][0] - fx, densified[0][1] - fy
    ) < 0.5 else densified
    highways[key]["points"] = keep + yaml_pts(tail)
    highways[key]["lanes"] = lanes


def _clip_ns_to_poly(
    highways: dict,
    key: str,
    poly: Sequence[tuple[float, float]],
) -> None:
    """Extend / clip a vertical N–S arterial so its south end sits on ``poly``."""
    if key not in highways:
        return
    pts = highways[key].get("points") or []
    if len(pts) < 2:
        return
    xs = [float(p[0]) for p in pts]
    x = sum(xs) / len(xs)
    x0, x1 = poly[0][0], poly[-1][0]
    lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
    if not (lo - 2.0 <= x <= hi + 2.0):
        return
    y_join = _interp_poly_y(list(poly), x)
    ys = [float(p[1]) for p in pts]
    y_top = max(ys)
    if y_top <= y_join + 1.0:
        return
    highways[key]["points"] = yaml_pts([(x, y_join), (x, y_top)])


def _clip_ns_prefix_to_poly(
    highways: dict,
    prefix: str,
    poly: Sequence[tuple[float, float]],
) -> None:
    """Clip ``prefix`` and any void-split ``prefix_N`` children onto ``poly``."""
    keys = [
        k
        for k in highways
        if k == prefix or k.startswith(prefix + "_")
    ]
    if not keys:
        return
    # Merge split segments into one N–S shaft, then re-clip.
    xs: list[float] = []
    ys: list[float] = []
    lanes = 4
    for k in keys:
        route = highways[k]
        lanes = int(route.get("lanes") or lanes)
        for p in route.get("points") or []:
            xs.append(float(p[0]))
            ys.append(float(p[1]))
    if not xs:
        return
    x = sum(xs) / len(xs)
    y_top = max(ys)
    x0, x1 = poly[0][0], poly[-1][0]
    lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
    if not (lo - 2.0 <= x <= hi + 2.0):
        return
    y_join = _interp_poly_y(list(poly), x)
    if y_top <= y_join + 1.0:
        return
    for k in keys:
        highways.pop(k, None)
    highways[prefix] = {
        "lanes": lanes,
        "points": yaml_pts([(x, y_join), (x, y_top)]),
    }


def _stitch_burnaby_newwest_queensborough(highways: dict) -> None:
    """World-XY cleanup + stitch after Google Maps city-centre translation.

    Purges floating Queensborough ticks and stray east-NW stubs, rebuilds the
    Hwy 91A / Ewen peninsula, and snaps Burnaby arterials onto New Westminster's
    tilted grid, Brunette into Coquitlam, and McBride/Pattullo into Surrey.
    """
    # --- 1. Purge floating stubs & orphaned ticks ---
    drop_qb = frozenset(
        {
            "qb_cross_0",
            "qb_cross_1",
            "qb_cross_2",
            "qb_cross_3",
            "qb_cross_4",
            "ewen_ave",
            "boyd_st",
            "salter_st",
            "howes_st",
            "pembroke_st",
            "wood_st",
            "boyne_st",
        }
    )
    _purge_box_orphans(
        highways,
        _QB_FLOAT_BOX,
        drop_keys=drop_qb,
        protect=frozenset({"hwy91a", "hwy91", "hwy99"}),
    )
    _purge_box_orphans(
        highways,
        _NW_STRAY_BOX,
        drop_keys=drop_qb,
        protect=frozenset(
            {
                "hwy91a",
                "nw_columbia_st",
                "nw_royal_ave",
                "brunette_ave",
                "mcbride_blvd",
                "nw_10th_ave",
                "nw_front_st",
            }
        ),
    )
    # Hard-delete any remaining legacy QB names.
    for key in list(drop_qb):
        highways.pop(key, None)

    # --- 2. Rebuild Queensborough peninsula + bridge connectors ---
    _replace_route_tail(
        highways,
        "hwy91a",
        (-235.0, -35.0),
        HWY91A_WORLD_CTRL,
        lanes=4,
        join_radius=55.0,
    )
    highways["ewen_ave"] = {
        "lanes": 2,
        "points": yaml_pts(_dense_spline(EWEN_WORLD_CTRL, segments=10)),
    }
    # Perpendicular cross-streets snapped to Hwy 91A and Ewen (no floating ticks).
    ewen_dense = _dense_spline(EWEN_WORLD_CTRL, segments=20)
    for name, t in QB_CROSS_WORLD:
        ax, ay = _lerp_poly(HWY91A_WORLD_CTRL, t)
        # Nearest Ewen vertex at this station (keeps both ends on real spines).
        ex, ey = min(
            ewen_dense,
            key=lambda p: math.hypot(p[0] - ax, p[1] - ay),
        )
        if math.hypot(ex - ax, ey - ay) < 0.5:
            # Degenerate — offset south along corridor perpendicular.
            px, py = _perp_unit(HWY91A_WORLD_CTRL, t)
            # Choose the side toward Ewen's western tip (south of Hwy 91A).
            sign = -1.0 if (EWEN_WORLD_CTRL[0][1] < HWY91A_WORLD_CTRL[0][1]) else 1.0
            ex, ey = ax + sign * 4.5 * px, ay + sign * 4.5 * py
        highways[name] = {
            "lanes": 2,
            "points": yaml_pts([(ex, ey), (ax, ay)]),
        }

    # Stewardson / Columbia landings at the Queensborough Bridge north abutment.
    highways["nw_stewardson"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (-148.0, 26.0),
                (-152.0, 34.0),
                (-155.0, 48.0),
                (-158.0, 62.0),
            ]
        ),
    }

    # --- 3. Stitch Burnaby arterials into New West tilted grid ---
    highways["marine_stewardson"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(MARINE_STEWARDSON_WORLD, segments=14)),
    }
    highways["kingsway_bn"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(KINGSWAY_BN_WORLD, segments=14)),
    }
    highways["canada_way"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(CANADA_WAY_WORLD, segments=14)),
    }
    highways["nw_10th_ave"] = {
        "lanes": 4,
        "points": yaml_pts(NW_10TH_WORLD),
    }
    # Snap 12th Street north end onto Kingsway handoff.
    highways["nw_12th_st"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (-142.0, 48.0),
                (-140.0, 40.0),
                (-138.0, 32.0),
                (-136.0, 26.0),
                (-135.0, 22.0),
            ]
        ),
    }

    for key in (
        "royal_oak_ave",
        "nelson_ave",
        "sperling_ave",
        "kensington_ave",
        "cariboo_rd",
        "griffiths_dr",
    ):
        _clip_ns_prefix_to_poly(highways, key, NW_10TH_WORLD)

    # --- 4. Stitch New West east to Coquitlam + south Pattullo to Surrey ---
    highways["brunette_ave"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(BRUNETTE_WORLD, segments=16)),
    }
    highways["mcbride_blvd"] = {
        "lanes": 5,
        "points": yaml_pts(_dense_spline(MCBRIDE_PATTULLO_WORLD, segments=16)),
    }
    # Surrey King George keeps the Whalley spine; Pattullo joins via mcbride_blvd.
    highways["king_george"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (0.0, 32.0),
                (0.0, 0.0),
                (0.0, -84.4),
                (30.0, -148.0),
                (52.0, -200.0),
            ]
        ),
    }


def build() -> dict:
    highways: dict = {}

    # --- Provincial / major corridors (exact key geometry) ---
    # Hwy 17 (South Fraser Perimeter) ends at 176 St; Golden Ears continues east.
    # Hwy 17: Tsawwassen Ferry causeway → Delta → Alex Fraser → Surrey SFPR.
    highways["hwy17"] = {
        "lanes": 6,
        "points": yaml_pts(
            [
                (-465.0, -330.0),
                (-375.0, -288.0),  # Arthur Dr / shifted Ladner link
                (-325.0, -265.0),  # Hwy 17A / 56 St interchange
                (-265.0, -180.0),
                (-245.0, -160.0),
                (-185.0, -115.0),
                (-116.0, -64.0),
                (-84.0, -20.0),
                (0.0, 32.0),
                (64.0, 42.0),
                (190.0, 24.0),
            ]
        ),
    }
    # Golden Ears Way — Langley → Fraser gap (only span) → Pitt Meadows / Maple Ridge.
    # Open river buffer ≈ 38 units (Y=+20 Langley → Y=+58 north shore).
    # Bridge stays straight N–S; north approach crosses Airport/Hammond & Lougheed
    # then curves NE to Dewdney Trunk at Laity (no duplicate Lougheed stub).
    ge_north = _dense_spline(
        [
            (316.5, 58.0),  # north shore / Airport Way junction
            (316.5, 63.3),  # Ford / Hammond Rd
            (316.5, 71.0),  # Lougheed Hwy
            (332.0, 78.0),  # curve northeast (Blakely)
            (353.0, 84.4),  # Dewdney Trunk / Laity
        ],
        segments=10,
    )
    highways["golden_ears"] = {
        "lanes": 6,
        "points": yaml_pts(
            [
                (190.0, 24.0),
                (316.5, 20.0),  # Langley north shore / 200 St
                (316.5, 58.0),  # Pitt Meadows / Maple Ridge south shore
                *ge_north[1:],
            ]
        ),
    }
    # Langley Golden Ears / riverside spur east of 200 St (Walnut Grove north edge).
    highways["golden_ears_e"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (316.5, 20.0),
                (400.9, 10.0),
            ]
        ),
    }
    highways["hwy1"] = {
        "lanes": 6,
        "points": yaml_pts(
            [
                (64.0, 42.2),
                (106.0, 10.0),
                (190.0, -20.0),
                (295.4, -48.0),
                (316.5, -75.0),
                (400.9, -95.0),
                (485.3, -110.0),
                (654.1, -135.0),
                (717.4, -145.0),
            ]
        ),
    }
    highways["hwy15"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (190.0, -20.0),
                (190.0, Y_BORDER),
            ]
        ),
    }
    highways["fraser"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (0.0, 0.0),
                (84.0, -52.0),
                (190.0, -116.0),
                (295.4, -168.0),
                (332.0, -172.0),
                (400.9, -195.0),
                (696.3, -232.1),
                (717.4, -235.0),
            ]
        ),
    }
    # King George Blvd — north tip → Whalley → South Surrey.
    highways["king_george"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (0.0, 32.0),  # North tip (open Fraser gap)
                (0.0, 0.0),  # Whalley / 104 Ave
                (0.0, -84.4),
                (30.0, -148.0),
                (52.0, -200.0),
            ]
        ),
    }
    # Hwy 99: Granville @ Broadway → 70th → Oak → Bridge → Lulu → Massey → Mud Bay.
    # False Creek angled approach is granville_bridge (Downtown → Broadway).
    highways["hwy99"] = {
        "lanes": 6,
        "points": yaml_pts(
            [
                (-458.5, 216.5),  # Broadway / Granville Bridge landing
                (-458.5, 142.7),  # 41st Ave
                (-458.5, 100.0),  # West 70th Ave
                (-431.5, 100.0),  # Oak & 70th (Hwy 99 transfer)
                (-431.5, 90.0),  # SW Marine Drive
                (-431.5, 62.2),  # Oak Street Bridge / Richmond
                (-410.4, -1.1),  # Westminster / Garden City
                (-368.2, -106.6),  # Shell Rd / Steveston Hwy entry
                (-265.0, -180.0),  # Delta Massey Tunnel approach (gap span)
                (-225.0, -185.0),
                (-168.8, -190.0),
                (-20.0, -170.0),
                (52.0, -200.0),
                (63.2, -210.0),
                (126.0, -250.0),
                (148.0, Y_BORDER),
            ]
        ),
    }
    # Hwy 91: Bridgeport → Richmond Freeway → smooth Y-junction → Annacis →
    # Alex Fraser → Nordel. 91A branches NE off the curve (see _build_richmond).
    hwy91_fork = _dense_spline(
        [
            (-225.0, 11.0),  # East Richmond freeway entry
            (-198.0, 10.0),
            (-178.0, 7.0),  # central junction (91A splits just east)
            (-162.0, -3.0),
            (-145.0, -15.0),  # Annacis Island
        ],
        segments=16,
    )
    highways["hwy91"] = {
        "lanes": 6,
        "points": yaml_pts(
            [
                (-410.4, 50.0),  # Bridgeport Rd
                (-347.1, 50.0),  # No. 5 Rd
                (-304.9, 10.0),  # No. 6 corridor
                *hwy91_fork,
                (-116.0, -64.0),  # Alex Fraser / Hwy 17 (gap span)
                (-126.6, -105.5),
                (-142.0, -145.0),
                (-168.8, -190.0),
            ]
        ),
    }

    # Scott Rd / 120 St (Delta border)
    highways["scott_120"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (st_x(120), 40.0),
                (st_x(120), ave_y(88)),
                (st_x(120), ave_y(56)),
                (st_x(120), ave_y(16)),
            ]
        ),
    }

    # --- Surrey major N–S arterials ---
    major_ns = [128, 144, 152, 160, 168, 184, 192, 196]
    for st in major_ns:
        x = st_x(st)
        y_top = 42.0 if st <= 176 else 20.0
        y_bot = Y_BORDER
        key = f"st_{st}"
        if x in ALR_CROSS or x < ALR_X0:
            highways[key] = {
                "lanes": 4,
                "points": yaml_pts([(x, y_bot), (x, y_top)]),
            }
        else:
            highways[key] = {
                "lanes": 4,
                "points": yaml_pts([(x, ALR_Y1), (x, y_bot)]),
            }
            highways[f"{key}_n"] = {
                "lanes": 4,
                "points": yaml_pts([(x, ALR_Y0), (x, y_top)]),
            }

    highways["st_152"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (63.2, 42.2),
                (63.2, 0.0),
                (63.2, ave_y(72)),
                (63.2, ave_y(16)),
                (63.2, Y_BORDER),
            ]
        ),
    }

    # --- Surrey major E–W avenues (compact anchors), extended into Langley ---
    major_aves = [104, 88, 72, 56, 32, 16, 0]
    for ave in major_aves:
        y = ave_y(ave)
        x0 = st_x(120)
        key = f"ave_{ave}" if ave != 0 else "ave_0"
        if ALR_Y0 <= y <= ALR_Y1:
            # Skip the ALR band; draw only west of the valley and into Langley.
            highways[f"{key}_w"] = {
                "lanes": 4,
                "points": yaml_pts([(x0, y), (ALR_X0, y)]),
            }
            highways[f"{key}_e"] = {
                "lanes": 4,
                "points": yaml_pts([(X_BORDER, y), (X_EAST, y)]),
            }
            continue
        pts = [(x0, y), (0.0, y), (63.2, y), (190.0, y), (X_BORDER, y), (X_EAST, y)]
        if ave == 88:
            highways["hwy10"] = {"lanes": 4, "points": yaml_pts(pts)}
        else:
            highways[key] = {"lanes": 4, "points": yaml_pts(pts)}

    # --- SW Panorama / West Newton fill (Scott→KG, down to Y≈-148) ---
    sw_x0, sw_x1 = st_x(120), 0.0
    sw_y0, sw_y1 = -42.0, -148.0
    for st in (124, 128, 132):
        x = st_x(st)
        highways[f"sw_st_{st}"] = {
            "lanes": 2,
            "points": yaml_pts([(x, sw_y1), (x, sw_y0)]),
        }
    for ave in (80, 72, 64, 56):
        y = ave_y(ave)
        if not (sw_y1 - 1.0 <= y <= sw_y0 + 1.0):
            continue
        highways[f"sw_ave_{ave}"] = {
            "lanes": 2,
            "points": yaml_pts([(sw_x0, y), (sw_x1, y)]),
        }
    highways["sw_fill_n"] = {
        "lanes": 2,
        "points": yaml_pts([(sw_x0, sw_y0), (sw_x1, sw_y0)]),
    }
    highways["sw_fill_s"] = {
        "lanes": 2,
        "points": yaml_pts([(sw_x0, sw_y1), (sw_x1, sw_y1)]),
    }

    # --- Surrey half-mile collectors (21.1 spacing) outside ALR ---
    half_ns = [124, 132, 140, 148, 156, 164, 172, 180, 188]
    half_ew = [100, 96, 92, 84, 80, 76, 68, 64, 60, 48, 40, 24, 8]

    for st in half_ns:
        x = st_x(st)
        highways[f"col_st_{st}_n"] = {
            "lanes": 2,
            "points": yaml_pts([(x, ALR_Y0), (x, 20.0)]),
        }
        y_s1 = ave_y(16) if x >= 50.0 else ave_y(32)
        highways[f"col_st_{st}_s"] = {
            "lanes": 2,
            "points": yaml_pts([(x, ALR_Y1), (x, y_s1)]),
        }

    for ave in half_ew:
        y = ave_y(ave)
        if ALR_Y0 <= y <= ALR_Y1:
            highways[f"col_ave_{ave}_w"] = {
                "lanes": 2,
                "points": yaml_pts([(st_x(120), y), (ALR_X0, y)]),
            }
            highways[f"col_ave_{ave}_e"] = {
                "lanes": 2,
                "points": yaml_pts([(X_BORDER, y), (X_EAST, y)]),
            }
            continue
        highways[f"col_ave_{ave}"] = {
            "lanes": 2,
            "points": yaml_pts(
                [
                    (st_x(120), y),
                    (0.0, y),
                    (63.2, y),
                    (190.0, y),
                    (X_BORDER, y),
                    (X_EAST, y),
                ]
            ),
        }

    # =====================================================================
    # Langley Township — major corridors, concession grid, urban sub-grids
    # =====================================================================

    # 200 Street — main N–S spine (6-lane); clips at Fraser south shore (bridge = golden_ears).
    highways["st_200"] = {
        "lanes": 6,
        "points": yaml_pts(
            [
                (316.5, 20.0),
                (316.5, -84.4),
                (316.5, -168.8),
                (316.5, -232.1),
            ]
        ),
    }

    # Highway 10 — Langley Bypass & Glover Road.
    highways["hwy10_langley"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (295.4, -168.8),
                (316.5, -162.0),
                (365.0, -148.0),
                (422.0, -110.0),
                (485.3, -35.0),
            ]
        ),
    }

    # Highway 13 / 264 Street.
    highways["hwy13"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (654.1, -135.0),
                (654.1, -228.0),
                (654.1, Y_BORDER),
            ]
        ),
    }

    # Langley City one-way couplet (Fraser Hwy parallels) between X=+322..+342.
    highways["langley_couplet_n"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (322.0, -170.0),
                (332.0, -170.5),
                (342.0, -171.0),
            ]
        ),
    }
    highways["langley_couplet_s"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (322.0, -174.0),
                (332.0, -174.5),
                (342.0, -175.0),
            ]
        ),
    }

    # --- Rural township 1-mile concession grid (central / south-central) ---
    # N–S every 8 streets from 216→256; 208/272/276 as arterials.
    rural_ns = [208, 216, 224, 232, 240, 248, 256, 272, 276]
    rural_y_north = -20.0
    for st in rural_ns:
        x = st_x(st)
        y_top = 16.0 if st <= 216 else rural_y_north
        if st == 264:
            continue
        lanes = 4 if st in (208, 216, 232, 272, 276) else 2
        # Central belt (380→654): full north–south concession shafts.
        if 380.0 <= x <= 654.0:
            _add_ns(highways, f"st_{st}", x, Y_BORDER, y_top, lanes=lanes)
        else:
            _add_ns(highways, f"st_{st}", x, Y_BORDER, y_top, lanes=lanes)

    # Clean 42.2-spaced E–W concession lines across central Langley.
    # From 72 Ave (-84.4) south by mile steps, plus compact 16/0 Ave anchors.
    concession_ys = [
        (-84.4, "lg_ave_72"),
        (-126.6, "lg_ave_64"),
        (-168.8, "lg_ave_56"),
        (-211.0, "lg_ave_32"),
        (-253.2, "lg_ave_8"),
        (-232.0, "lg_ave_16"),
        (-274.2, "lg_ave_0"),
    ]
    surrey_ys = {round(ave_y(a), 1) for a, _ in AVE_Y_ANCHORS}
    surrey_ys |= {round(ave_y(a), 1) for a in half_ew}
    for y, key in concession_ys:
        if round(y, 1) in surrey_ys:
            continue
        _add_ew(highways, key, y, 380.0, 654.0, lanes=2)

    # Half-mile N–S collectors in western Langley urban belt (200–216).
    for st in (204, 212):
        x = st_x(st)
        _add_ns(highways, f"col_st_{st}", x, -232.1, -40.0, lanes=2)

    # --- Dense urban sub-grids (aligned to Langley community boxes) ---
    # Walnut Grove — south of Golden Ears / north of Hwy 1.
    _urban_grid(highways, "wg", 295.4, 400.9, -95.0, -40.0, step=HALF_MILE)
    # Willoughby — Hwy 1 → 72/64 Ave (Willowbrook notch handled by majormap).
    _urban_grid(highways, "wb", 295.4, 400.9, -147.7, -65.0, step=HALF_MILE)
    # Willowbrook commercial strip — 72 Ave → 64 Ave.
    _urban_grid(
        highways, "wlb", 295.4, 358.7, -147.7, -126.6, step=QUARTER_MILE
    )
    # Langley City — 196–208 St, 64 Ave → Nicomekl.
    _urban_grid(highways, "lc", 295.4, 358.7, -200.0, -147.7, step=HALF_MILE)
    _urban_grid(
        highways, "lc_core", 310.0, 350.0, -190.0, -160.0, step=QUARTER_MILE
    )
    # Murrayville — east of Langley City to 232 St.
    _urban_grid(
        highways, "mv", 358.7, 485.3, -211.0, -147.7, step=HALF_MILE
    )
    # Brookswood / Fernridge — south of Langley City to 16 Ave.
    _urban_grid(
        highways, "bw", 295.4, 400.9, -253.2, -200.0, step=HALF_MILE
    )
    # Aldergrove — 256–276 St townsite.
    _urban_grid(
        highways, "ag", 611.9, 717.4, -253.2, -135.0, step=HALF_MILE
    )
    _urban_grid(
        highways, "ag_core", 654.0, 717.4, -245.0, -215.0, step=QUARTER_MILE
    )

    # =====================================================================
    # Pitt Meadows — west of Laity / 207 St (owns full Lougheed Hwy polyline)
    # =====================================================================
    _build_pitt_meadows(highways)

    # =====================================================================
    # Maple Ridge — north of Fraser via Golden Ears Bridge corridor
    # =====================================================================
    _build_maple_ridge(highways)

    # =====================================================================
    # Delta — North Delta, Burns Bog ring, Ladner, Tsawwassen, ferry causeway
    # =====================================================================
    _build_delta(highways)

    # =====================================================================
    # Richmond — Lulu Island arterial grid + Sea Island / YVR spur
    # =====================================================================
    _build_richmond(highways)

    # =====================================================================
    # Vancouver / UBC — north of North Arm Fraser (Oak / Knight / Arthur Laing)
    # =====================================================================
    _build_vancouver(highways)

    # =====================================================================
    # North Vancouver — north of Burrard Inlet (Lions Gate / Ironworkers)
    # =====================================================================
    _build_north_vancouver(highways)

    # =====================================================================
    # Burnaby — Boundary Rd → North Rd (roads only; park/lake voids open)
    # =====================================================================
    _build_burnaby(highways)

    # =====================================================================
    # New Westminster — Mainland tilted grid + Queensborough peninsula
    # =====================================================================
    _build_new_westminster(highways)

    # =====================================================================
    # Coquitlam — North Rd → PoCo seams / Port Mann (Mundy Park open)
    # =====================================================================
    _build_coquitlam(highways)

    # =====================================================================
    # Port Moody — U-loop around Burrard Inlet tip (Barnet / St Johns / Ioco)
    # =====================================================================
    _build_port_moody(highways)

    # =====================================================================
    # Port Coquitlam — Coquitlam River → Pitt River Bridge (roads only)
    # =====================================================================
    _build_port_coquitlam(highways)

    _snap_highways(highways)

    # Pure north-up translate: satellite cities → Google Maps centres, then
    # snap inter-city bridge abutments (no rotation / setH = 0).
    georeference_highways(highways)

    # Burnaby / New Westminster / Queensborough world-XY stitch & stub purge.
    _stitch_burnaby_newwest_queensborough(highways)
    # Re-snap bridge abutments after the BN/NW/QB rebuild.
    snap_checkpoints_to_routes(highways)

    # Drop any route left with fewer than 2 points after snap/cleanup.
    highways = {
        k: v
        for k, v in highways.items()
        if isinstance(v, dict) and len(v.get("points") or []) >= 2
    }

    return {
        "lot": {
            "block_size": [0.5, 0.5, 0.4],
            "tower_count": 5,
            "tower_gap": 0.15,
            # lane_width = road_width/2 → 2-lane 0.267, 4-lane 0.53, 6-lane 0.80
            "road_width": 0.267,
            "floor_min": 10,
            "floor_max": 25,
            "towers_per_ring": 10,
        },
        "highway": {
            "lanes": 4,
            "fence_w": 0.03,
            "fence_h": 0.12,
            "barrier_w": 0.04,
            "barrier_h": 0.12,
            "keepout": 0.12,
        },
        "highways": highways,
        "neighborhoods": [],
        "streets": {},
    }


def main() -> None:
    data = build()
    header = (
        calibration_banner()
        + "# Surrey + Langley + Delta + Richmond + Vancouver/UBC + Burnaby +"
        " New Westminster + Coquitlam + Port Moody + Port Coquitlam +"
        " Maple Ridge + Pitt Meadows + North Vancouver — 2× arterials.\n"
        f"# Scale: {UNITS_PER_KM:g} units = 1.0 km; {UNITS_PER_MILE:g} units = 1.0 mile "
        f"(1 unit = {METERS_PER_UNIT} m).\n"
        f"# Anchor (0,0): King George Blvd & 104 Ave "
        f"(lat0={LAT0}, lon0={LON0}).\n"
        f"# Projection: X=(lon-lon0)*{M_LON:g}/{METERS_PER_UNIT}  "
        f"Y=(lat-lat0)*{M_LAT:g}/{METERS_PER_UNIT}  (≈1919.4 / 2932.2).\n"
        "# Surrey plate locked (196 St X=+295.4); satellite cities translate "
        "onto Google Maps centres (no rotation); bridges snapped.\n"
        f"# Camera far clip: {CAMERA_FAR_CLIP:g}. Flat roads Z=0 "
        "(hierarchy offsets 0.001–0.04).\n"
        "# Generated by city/calibrate_surrey_2x.py — re-run to regenerate.\n"
    )
    body = yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=None,
        width=88,
    )
    OUT.write_text(header + body, encoding="utf-8")
    print(f"Wrote {OUT} ({len(data['highways'])} highway routes)")
    print("Stitch checkpoint residuals:")
    for line in stitch_report(data["highways"]):
        print(" ", line)


if __name__ == "__main__":
    main()
