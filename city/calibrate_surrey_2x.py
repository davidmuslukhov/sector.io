"""Generate Surrey + Langley + Delta + Richmond + Vancouver/UBC + Burnaby +
New Westminster (Queensborough) + Maple Ridge + Pitt Meadows 2× city.yaml.

Scale: 26.4 units = 1.0 km; 42.2 units = 1.0 mile.
Compact Y-scale anchors (Surrey): 104=0, 88=-42.2, 72=-84.4, 56=-168.8,
32=-211.0, 16=-232.0, 0=-274.2.
Langley continues east from 196 St (X=+295.4) to 276 St / Abbotsford (X=+717.4).
Delta stitches west at Scott Rd (X=-84.4) and Hwy 91 / Hwy 17 (X=-116, Y=-64).
Richmond / Lulu Island sits northwest of Delta (No. 2–8 Rd grid + Sea Island spur).
Vancouver / UBC sits north of the North Arm Fraser (open 25–35 unit river gap);
Oak / Knight / Arthur Laing corridors are the only spans into SW Marine Drive.
Burnaby fills Boundary Rd (X=-178) → North Rd (X=+52); New Westminster /
Queensborough stitch via Pattullo, Queensborough Bridge, and Port Mann only.
Maple Ridge sits north of the Fraser (open 35–45 unit gap); Golden Ears Bridge
corridor at 200 St (X=+316.5) is the only road span into Lougheed / Dewdney Trunk.
Pitt Meadows sits west of Laity / 207 St (X=+353), from the Pitt River Bridge
(X=+175) east to Maple Ridge and north into the Pitt Polder / Pitt Lake valley.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent / "data" / "city.yaml"

UNITS_PER_KM = 26.4
UNITS_PER_MILE = 42.2
HALF_MILE = UNITS_PER_MILE / 2.0  # 21.1
QUARTER_MILE = HALF_MILE / 2.0  # 10.55

# Street X anchors — Surrey milestones + uniform Langley 8-street steps.
STREET_X: dict[int, float] = {
    120: -84.4,
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
X_SCOTT = -84.4  # Scott Rd / 120 St / Surrey–Delta
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
QUEENSBOROUGH = (-128.0, 30.0)  # Hwy 91A tip (parallel to Westminster NE exit)

# Vancouver / UBC — 2× Whalley plate, north of the North Arm Fraser.
# Major N–S arterials ≈ 21.1 units (0.5 mi) apart; Boundary Rd = Burnaby seam.
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
    "boundary": -178.0,  # Vancouver / Burnaby border
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

# Burnaby / New Westminster — 2× Whalley plate (Boundary → North Rd).
# N–S arterials ≈ 21.1 units (0.5 mi) apart west of Gaglardi.
BN_NS_X: dict[str, float] = {
    "boundary": -178.0,  # Vancouver / Burnaby border
    "gilmore": -156.9,
    "willingdon": -135.8,  # Brentwood → Metrotown spine
    "royal_oak": -114.7,
    "nelson": -93.6,  # Nelson / Deer Lake Pkwy
    "sperling": -72.5,
    "kensington": -51.4,
    "gaglardi": -20.0,  # Hwy 1 → SFU spine
    "cariboo": 10.0,
    "brunette_x": 35.0,  # Brunette Ave / Cape Horn band
    "north_rd": 52.0,  # Burnaby / Coquitlam border
}
BN_EW_Y: dict[str, float] = {
    "marine": 88.0,  # Marine Way / SE Marine (South Burnaby flats)
    "rumble": 115.0,  # Rumble / Imperial
    "canada_way_mid": 160.0,  # Deer Lake / City Hall band
    "lougheed_w": 216.5,  # Broadway seam through Brentwood
    "hastings": 269.0,  # Hwy 7A North Burnaby
    "burrard": 275.0,  # Burrard Inlet shoreline clip
}
# Hwy 1 Burnaby → Port Mann → Surrey snap at (64.0, 42.2).
HWY1_BN_CTRL: list[tuple[float, float]] = [
    (-178.0, 248.0),  # Boundary Rd (Vancouver seam)
    (-135.8, 228.0),  # Willingdon
    (-51.4, 195.0),  # Sprott / Kensington
    (-20.0, 180.0),  # Gaglardi Way
    (35.0, 115.0),  # Brunette / Cape Horn
    (50.0, 75.0),  # Port Mann west approach
    (64.0, 42.2),  # Surrey Hwy 1 snap
]
# Kingsway Burnaby → Edmonds (12th St continues into New Westminster).
KINGSWAY_BN_CTRL: list[tuple[float, float]] = [
    (-178.0, 125.0),  # Boundary (Vancouver seam)
    (-125.0, 115.0),  # Metrotown
    (-65.0, 100.0),  # Edmonds / 12th St handoff
]
# Canada Way — Grandview / Boundary → McBride / 10th Ave New West border.
CANADA_WAY_CTRL: list[tuple[float, float]] = [
    (-178.0, 206.0),  # Boundary & Grandview
    (-135.8, 185.0),  # Burnaby Hospital / Willingdon
    (-85.0, 160.0),  # Deer Lake / City Hall
    (-25.0, 115.0),  # McBride Blvd / 10th Ave handoff
]
# Lougheed Hwy (Hwy 7) through Burnaby (Broadway seam → Brunette).
LOUGHEED_BN_CTRL: list[tuple[float, float]] = [
    (-178.0, 216.5),  # Boundary / Broadway
    (-135.8, 216.5),  # Brentwood
    (-72.5, 216.5),  # Sperling
    (-20.0, 200.0),  # Production Way
    (52.0, 185.0),  # Lougheed Town Centre / North Rd
]
# Marine Way → Stewardson entry (New West tilted grid takes over east of this).
MARINE_STEWARDSON_CTRL: list[tuple[float, float]] = [
    (-178.0, 90.0),  # Boundary / SE Marine (Vancouver seam)
    (-135.8, 88.0),  # Willingdon
    (-114.7, 88.0),  # Royal Oak
    (-55.0, 72.0),  # Stewardson / 14th St handoff
]
# Hwy 91A Queensborough Bridge continuation (Richmond tip → Stewardson).
HWY91A_QB_CTRL: list[tuple[float, float]] = [
    (-128.0, 30.0),  # Richmond / Queensborough tip
    (-110.0, 36.0),
    (-95.0, 42.0),  # Howes / Hwy 91A
    (-68.0, 45.0),  # Queensborough Bridge mid
    (-55.0, 72.0),  # Stewardson / Marine Way snap
]
# Mainland New Westminster wipe box (tangled orthogonal overlap removed here).
NW_WIPE_X0, NW_WIPE_X1 = -52.0, 22.0
NW_WIPE_Y0, NW_WIPE_Y1 = 48.0, 112.0
# 10th Avenue — Burnaby / New Westminster tilted border.
NW_10TH_CTRL: list[tuple[float, float]] = [
    (-55.0, 102.0),  # Kingsway / Edmonds
    (-35.0, 106.0),  # 8th St
    (-28.0, 110.0),  # 6th St
    (-15.0, 115.0),  # Canada Way / Cumberland
]
# Columbia / Front — Fraser waterfront spine.
NW_COLUMBIA_CTRL: list[tuple[float, float]] = [
    (-45.0, 52.0),  # Stewardson junction
    (-25.0, 55.0),  # 8th St
    (-18.0, 58.0),  # 6th St
    (-5.0, 62.0),  # McBride / Pattullo
    (15.0, 85.0),  # Sapperton / Brunette
]
# Royal Avenue — parallel main corridor (~5 units NW of Columbia).
NW_ROYAL_CTRL: list[tuple[float, float]] = [
    (-48.0, 58.0),
    (-28.0, 62.0),
    (-10.0, 68.0),
    (10.0, 88.0),
]
# 6th Avenue — Uptown commercial spine.
NW_6TH_AVE_CTRL: list[tuple[float, float]] = [
    (-42.0, 78.0),  # 12th St
    (-30.0, 82.0),  # 8th St
    (-22.0, 86.0),  # 6th St
    (-12.0, 90.0),  # McBride
    (5.0, 98.0),  # 1st St / Cumberland
]
# 8th Avenue — parallel ~6 units NW of 6th Ave.
NW_8TH_AVE_CTRL: list[tuple[float, float]] = [
    (-45.0, 86.0),
    (-33.0, 90.0),
    (-25.0, 94.0),
    (-15.0, 98.0),
]
# Cross-streets (NW–SE, perpendicular to Columbia / Royal).
NW_12TH_CTRL: list[tuple[float, float]] = [
    (-65.0, 100.0),  # Kingsway / Edmonds handoff
    (-50.0, 98.0),  # 10th Ave
    (-45.0, 86.0),  # 8th Ave
    (-42.0, 78.0),  # 6th Ave
    (-40.0, 60.0),  # Royal Ave
    (-5.0, 62.0),  # McBride / Columbia — Pattullo → King George
]
NW_8TH_ST_CTRL: list[tuple[float, float]] = [
    (-35.0, 106.0),  # 10th Ave
    (-33.0, 90.0),  # 8th Ave
    (-30.0, 82.0),  # 6th Ave
    (-28.0, 62.0),  # Royal Ave
    (-25.0, 55.0),  # Columbia
]
NW_6TH_ST_CTRL: list[tuple[float, float]] = [
    (-28.0, 110.0),  # 10th Ave
    (-25.0, 94.0),  # 8th Ave
    (-22.0, 86.0),  # 6th Ave
    (-20.0, 65.0),  # Royal Ave
    (-18.0, 58.0),  # Columbia
]
# McBride Blvd + Pattullo Bridge spine (Canada Way → Surrey).
NW_MCBRIDE_CTRL: list[tuple[float, float]] = [
    (-25.0, 115.0),  # Canada Way handoff
    (-15.0, 98.0),  # 8th Ave
    (-12.0, 90.0),  # 6th Ave
    (-10.0, 68.0),  # Royal Ave
    (-5.0, 62.0),  # Columbia / Pattullo north
    (0.0, 32.0),  # Surrey Pattullo approach
]
# Stewardson / 14th St — Marine + Queensborough Bridge into Columbia / Royal.
NW_STEWARDSON_CTRL: list[tuple[float, float]] = [
    (-55.0, 72.0),  # Marine / Hwy 91A junction
    (-48.0, 58.0),  # Royal Ave
    (-45.0, 52.0),  # Columbia / Front
]
# Hastings → Barnet Highway (North Burnaby → Port Moody approach).
HASTINGS_BARNET_CTRL: list[tuple[float, float]] = [
    (-178.0, 269.0),  # Boundary (Vancouver seam)
    (-51.4, 269.0),  # Kensington / Burnaby Heights
    (-10.0, 260.0),  # SFU / Burnaby Mountain base
    (25.0, 265.0),  # Barnet Hwy
    (65.0, 268.0),  # Port Moody approach
]
# Gaglardi Way — Hwy 1 → SFU ring.
GAGLARDI_CTRL: list[tuple[float, float]] = [
    (-20.0, 180.0),  # Hwy 1 interchange
    (-20.0, 220.0),
    (-10.0, 245.0),
    (10.0, 255.0),  # SFU core
]
# Brunette Ave — Lougheed Town Centre south to Hwy 1 / New West.
BRUNETTE_CTRL: list[tuple[float, float]] = [
    (52.0, 185.0),  # North Rd / Lougheed
    (35.0, 145.0),
    (15.0, 85.0),  # Sapperton / New West
]
X_NORTH_RD = BN_NS_X["north_rd"]
Y_BN_BURRARD = BN_EW_Y["burrard"]
Y_BN_MARINE = BN_EW_Y["marine"]
SFU_CORE = (10.0, 255.0)


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
    # Burnaby / New Westminster N–S arterials
    -156.9,
    -135.8,
    -114.7,
    -93.6,
    -72.5,
    -51.4,
    -35.0,
    -28.0,
    -25.0,
    -20.0,
    -18.0,
    -15.0,
    -10.0,
    -5.0,
    10.0,
    15.0,
    25.0,
    35.0,
    52.0,
    64.0,
    65.0,
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
    # Burnaby / New Westminster E–W spines
    28.0,
    35.0,
    36.0,
    42.0,
    42.2,
    44.0,
    45.0,
    48.0,
    52.0,
    75.0,
    85.0,
    88.0,
    95.0,
    105.0,
    110.0,
    115.0,
    125.0,
    145.0,
    160.0,
    180.0,
    185.0,
    195.0,
    200.0,
    228.0,
    235.0,
    245.0,
    260.0,
    265.0,
    268.0,
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
            # Burnaby / New Westminster / Queensborough
            (-178.0, 90.0),
            (-178.0, 125.0),
            (-178.0, 206.0),
            (-178.0, 216.5),
            (-178.0, 248.0),
            (-178.0, 269.0),
            (-156.9, 88.0),
            (-135.8, 88.0),
            (-135.8, 115.0),
            (-135.8, 185.0),
            (-135.8, 216.5),
            (-135.8, 228.0),
            (-135.8, 269.0),
            (-125.0, 115.0),
            (-114.7, 88.0),
            (-114.7, 115.0),
            (-95.0, 42.0),
            (-93.6, 115.0),
            (-85.0, 160.0),
            (-72.5, 216.5),
            (-68.0, 45.0),
            (-65.0, 100.0),
            (-55.0, 72.0),
            (-51.4, 195.0),
            (-51.4, 269.0),
            (-45.0, 72.0),
            (-35.0, 48.0),
            (-35.0, 105.0),
            (-28.0, 110.0),
            (-25.0, 75.0),
            (-25.0, 115.0),
            (-20.0, 180.0),
            (-20.0, 200.0),
            (-18.0, 55.0),
            (-15.0, 52.0),
            (-10.0, 260.0),
            (-5.0, 50.0),
            (-5.0, 52.0),
            (0.0, 32.0),
            (10.0, 255.0),
            (15.0, 85.0),
            (25.0, 265.0),
            (35.0, 115.0),
            (35.0, 145.0),
            (52.0, 185.0),
            (52.0, 245.0),
            (64.0, 42.2),
            (65.0, 268.0),
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
        "hwy1_bn",
        "hwy1_van",
        "kingsway",
        "kingsway_bn",
        "canada_way",
        "lougheed_bn",
        "marine_stewardson",
        "hastings_barnet",
        "gaglardi_way",
        "brunette_ave",
        "sfu_ring",
        "nw_columbia_st",
        "nw_royal_ave",
        "nw_queens_ave",
        "nw_4th_ave",
        "nw_6th_ave",
        "nw_8th_ave",
        "nw_10th_ave",
        "nw_stewardson",
        "nw_12th_st",
        "nw_8th_st",
        "nw_6th_st",
        "mcbride_blvd",
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
    # S-curve across Hwy 91 into Queensborough (no X-junction stubs).
    westminster_curve = _dense_spline(
        [
            (-225.0, -1.1),  # No. 8 Rd entry into the curve
            (-200.0, 4.0),
            (-182.0, 10.0),  # Hwy 91 crossover
            (-168.0, 20.0),
            (-150.0, 28.0),
            (-130.0, 36.0),  # Queensborough / New West connection
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
                (-498.0, 325.0),
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

    # Boundary Road — Vancouver / Burnaby seam (Marine → Hastings / Hwy 1).
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
    # Broadway — UBC → Boundary (Burnaby / Lougheed seam).
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
    # Hastings St built in _build_downtown_peninsula (West Hastings → Burnaby).

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


def _nw_10th_y(x: float) -> float:
    """Y of 10th Avenue (Burnaby / New West border) at X."""
    return _interp_poly_y(NW_10TH_CTRL, x)


def _bn_ns_south_y(x: float) -> float:
    """Southern clip for Burnaby N–S arterials.

    West of New Westminster: Marine Way / Stewardson. Inside the New West
    X-band: clip at tilted 10th Avenue so orthogonal streets do not poke
    south through the Fraser-aligned grid.
    """
    if -55.0 <= x <= 25.0:
        return _nw_10th_y(x)
    return _interp_poly_y(MARINE_STEWARDSON_CTRL, x)


def _in_nw_wipe(x: float, y: float) -> bool:
    """True if (x,y) is interior Mainland New West (south of 10th Ave border)."""
    if not (NW_WIPE_X0 < x < NW_WIPE_X1 and NW_WIPE_Y0 < y < NW_WIPE_Y1):
        return False
    # Burnaby owns the 10th Avenue seam and everything north of it.
    if y >= _nw_10th_y(x) - 0.5:
        return False
    return True


def _offset_polyline(
    controls: list[tuple[float, float]],
    dist: float,
) -> list[tuple[float, float]]:
    """Offset a polyline to the left of its forward direction by ``dist``."""
    if len(controls) < 2:
        return list(controls)
    dx = controls[-1][0] - controls[0][0]
    dy = controls[-1][1] - controls[0][1]
    length = math.hypot(dx, dy) or 1.0
    # Left normal (NW when travelling NE along the Fraser).
    nx, ny = -dy / length, dx / length
    return [(x + nx * dist, y + ny * dist) for x, y in controls]


# Routes allowed to occupy the Mainland New Westminster wipe box.
_NW_BOX_KEEP = frozenset(
    {
        "nw_columbia_st",
        "nw_royal_ave",
        "nw_queens_ave",
        "nw_4th_ave",
        "nw_6th_ave",
        "nw_8th_ave",
        "nw_10th_ave",
        "nw_stewardson",
        "nw_12th_st",
        "nw_8th_st",
        "nw_6th_st",
        "mcbride_blvd",
        "brunette_ave",
        "hwy91a",
        "marine_stewardson",
        "kingsway_bn",
        "canada_way",
    }
)


def _wipe_new_west_box(highways: dict) -> None:
    """Delete residual non-NW geometry inside the Mainland New West wipe box."""
    doomed: list[str] = []
    for key, route in highways.items():
        if key in _NW_BOX_KEEP or key.startswith("nw_"):
            continue
        pts = route.get("points") or []
        if len(pts) < 2:
            doomed.append(key)
            continue
        kept: list[list[float]] = []
        for p in pts:
            x, y = float(p[0]), float(p[1])
            if _in_nw_wipe(x, y):
                continue
            kept.append([round(x, 1), round(y, 1)])
        # Drop zero-length consecutive duplicates.
        cleaned: list[list[float]] = []
        for p in kept:
            if not cleaned or p != cleaned[-1]:
                cleaned.append(p)
        if len(cleaned) < 2:
            doomed.append(key)
        else:
            route["points"] = cleaned
    for key in doomed:
        del highways[key]


def _build_burnaby_new_west(highways: dict) -> None:
    """Burnaby + Mainland New Westminster + Queensborough (roads only, Z=0).

    Stitches onto Vancouver at Boundary Rd (X=-178): Marine, Kingsway, Canada
    Way / Grandview, Lougheed / Broadway, Hastings, and Hwy 1. Stitches onto
    Richmond via Hwy 91A / Queensborough Bridge, onto Surrey via Pattullo
    (0, +32) and Port Mann / Hwy 1 (64, 42.2). Mainland New Westminster uses
    a single ~30° Fraser-aligned tilted grid; Burnaby orthogonal streets clip
    at 10th Avenue. Open Fraser buffer kept south of Front; Burrard Inlet
    clips the north shore near Y=+275.
    """
    x_bound = BN_NS_X["boundary"]
    x_gil = BN_NS_X["gilmore"]
    x_will = BN_NS_X["willingdon"]
    x_oak = BN_NS_X["royal_oak"]
    x_nel = BN_NS_X["nelson"]
    x_sper = BN_NS_X["sperling"]
    x_ken = BN_NS_X["kensington"]
    x_gag = BN_NS_X["gaglardi"]
    x_car = BN_NS_X["cariboo"]
    x_north = BN_NS_X["north_rd"]

    y_rumble = BN_EW_Y["rumble"]
    y_hast = BN_EW_Y["hastings"]
    y_burrard = Y_BN_BURRARD

    # --- Hwy 1 Burnaby → Port Mann → Surrey snap ---
    highways["hwy1_bn"] = {
        "lanes": 6,
        "points": yaml_pts(_dense_spline(HWY1_BN_CTRL, segments=16)),
    }

    # --- Extend Hwy 91A across Queensborough Bridge into Stewardson ---
    qb_ext = yaml_pts(_dense_spline(HWY91A_QB_CTRL, segments=14))
    if "hwy91a" in highways:
        base = highways["hwy91a"]["points"]
        highways["hwy91a"]["points"] = base[:-1] + qb_ext
    else:
        highways["hwy91a"] = {"lanes": 4, "points": qb_ext}

    # --- Marine Way → Stewardson handoff (New West owns the tilt east of this) ---
    highways["marine_stewardson"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(MARINE_STEWARDSON_CTRL, segments=12)),
    }

    # --- Kingsway → Edmonds (12th St continues into New West) ---
    highways["kingsway_bn"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(KINGSWAY_BN_CTRL, segments=10)),
    }

    # --- Canada Way → McBride / 10th Ave handoff ---
    highways["canada_way"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(CANADA_WAY_CTRL, segments=12)),
    }

    # --- Lougheed Hwy (Hwy 7) through Burnaby ---
    highways["lougheed_bn"] = {
        "lanes": 6,
        "points": yaml_pts(_dense_spline(LOUGHEED_BN_CTRL, segments=12)),
    }

    # --- Hastings St / Barnet Hwy ---
    highways["hastings_barnet"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(HASTINGS_BARNET_CTRL, segments=12)),
    }

    # --- Gaglardi Way + Brunette Ave (NE Sapperton exit) ---
    highways["gaglardi_way"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(GAGLARDI_CTRL, segments=12)),
    }
    highways["brunette_ave"] = {
        "lanes": 4,
        "points": yaml_pts(_dense_spline(BRUNETTE_CTRL, segments=10)),
    }

    # --- Major N–S arterials (10th Ave clip inside New West X-band) ---
    ns_major = (
        ("gilmore_ave", x_gil, y_burrard, 4),
        ("willingdon_ave", x_will, y_burrard, 4),
        ("royal_oak_ave", x_oak, y_hast, 4),
        ("nelson_ave", x_nel, y_hast, 4),
        ("sperling_ave", x_sper, y_hast, 4),
        ("kensington_ave", x_ken, y_hast, 4),
        ("cariboo_rd", x_car, 245.0, 4),
    )
    for key, x, y_top, lanes in ns_major:
        y0 = round(_bn_ns_south_y(x), 1)
        if y_top > y0 + 1.0:
            _add_ns(highways, key, x, y0, y_top, lanes=lanes)

    # North Road — Lougheed Town Centre → Clarke / Como Lake.
    _add_ns(highways, "north_rd", x_north, 185.0, 245.0, lanes=4)

    # Boundary Rd already owned by Vancouver (Marine → Hastings); short north
    # stub to Hwy 1 / Burrard so the seam covers the freeway latitude.
    _add_ns(highways, "boundary_rd_n", x_bound, y_hast, y_burrard, lanes=4)

    # --- Rumble / Imperial (South Burnaby E–W; stops west of New West) ---
    _add_ew(highways, "rumble_st", y_rumble, x_bound, x_oak, lanes=4)

    # --- Secondary E–W collectors (split around the New West wipe box) ---
    for i, y in enumerate((100.0, 130.0, 145.0, 170.0, 190.0, 235.0, 250.0)):
        if _near(y, _MAJOR_YS, tol=2.0):
            continue
        if y <= Y_BN_MARINE + 2.0 or y >= y_burrard - 2.0:
            continue
        if NW_WIPE_Y0 <= y <= NW_WIPE_Y1:
            # West lobe: Boundary → New West west edge.
            _add_ew(highways, f"bn_ew_{i}_w", y, x_bound, -55.0, lanes=2)
            # East lobe: east of wipe → North Rd (Sapperton / LOUGHEED band).
            if x_north > NW_WIPE_X1 + 1.0:
                _add_ew(highways, f"bn_ew_{i}_e", y, NW_WIPE_X1, x_north, lanes=2)
        else:
            _add_ew(highways, f"bn_ew_{i}", y, x_bound, x_north, lanes=2)

    # --- SFU / Burnaby Mountain ring ---
    sx, sy = SFU_CORE
    highways["sfu_ring"] = {
        "lanes": 2,
        "points": yaml_pts(
            [
                (sx - 12.0, sy),
                (sx - 6.0, sy + 8.0),
                (sx + 8.0, sy + 10.0),
                (sx + 14.0, sy),
                (sx + 8.0, sy - 8.0),
                (sx - 4.0, sy - 10.0),
                (sx - 12.0, sy),
            ]
        ),
    }
    highways["sfu_hastings_spur"] = {
        "lanes": 2,
        "points": yaml_pts([(-10.0, 260.0), (sx - 12.0, sy)]),
    }

    # =====================================================================
    # Mainland New Westminster — single ~30° Fraser-aligned tilted grid
    # (no axis-aligned H/V fill inside the wipe box)
    # =====================================================================
    # Waterfront avenues (parallel to the Fraser).
    highways["nw_columbia_st"] = {
        "lanes": 4,
        "points": yaml_pts(NW_COLUMBIA_CTRL),
    }
    highways["nw_royal_ave"] = {
        "lanes": 4,
        "points": yaml_pts(NW_ROYAL_CTRL),
    }
    # Queens Ave / 4th Ave — parallel NW of Royal, between 12th St and McBride.
    royal_span = [(-40.0, 60.0), (-28.0, 62.0), (-10.0, 68.0)]
    highways["nw_queens_ave"] = {
        "lanes": 2,
        "points": yaml_pts(_offset_polyline(royal_span, 5.0)),
    }
    highways["nw_4th_ave"] = {
        "lanes": 2,
        "points": yaml_pts(_offset_polyline(royal_span, 10.0)),
    }

    highways["nw_6th_ave"] = {
        "lanes": 4,
        "points": yaml_pts(NW_6TH_AVE_CTRL),
    }
    highways["nw_8th_ave"] = {
        "lanes": 2,
        "points": yaml_pts(NW_8TH_AVE_CTRL),
    }
    highways["nw_10th_ave"] = {
        "lanes": 4,
        "points": yaml_pts(NW_10TH_CTRL),
    }

    # Cross-streets (perpendicular to Columbia / Royal).
    highways["nw_stewardson"] = {
        "lanes": 4,
        "points": yaml_pts(NW_STEWARDSON_CTRL),
    }
    highways["nw_12th_st"] = {
        "lanes": 4,
        "points": yaml_pts(NW_12TH_CTRL),
    }
    highways["nw_8th_st"] = {
        "lanes": 4,
        "points": yaml_pts(NW_8TH_ST_CTRL),
    }
    highways["nw_6th_st"] = {
        "lanes": 4,
        "points": yaml_pts(NW_6TH_ST_CTRL),
    }
    # McBride + Pattullo — wider spine (~0.65 units ≈ 5 lanes).
    highways["mcbride_blvd"] = {
        "lanes": 5,
        "points": yaml_pts(NW_MCBRIDE_CTRL),
    }

    # =====================================================================
    # Queensborough Peninsula (unchanged — outside the mainland wipe box)
    # =====================================================================
    _add_ew(highways, "ewen_ave", 35.0, -125.0, -55.0, lanes=2)
    _add_ew(highways, "boyd_st", 44.0, -125.0, -55.0, lanes=2)
    for i, x in enumerate((-115.0, -100.0, -80.0, -60.0)):
        if _near(x, _MAJOR_XS, tol=2.0):
            continue
        _add_ns(highways, f"qb_ns_{i}", x, 30.0, 48.0, lanes=2)

    # =====================================================================
    # Burnaby neighbourhood sub-grids (kept outside the New West wipe box)
    # =====================================================================
    dense = QUARTER_MILE  # 10.55
    _urban_grid(
        highways, "brentwood", -160.0, -120.0, 200.0, 235.0, step=dense
    )
    _urban_grid(
        highways, "metrotown", -150.0, -100.0, 100.0, 140.0, step=dense
    )
    # Edmonds — north of 10th Ave / west of New West only.
    _urban_grid(
        highways, "edmonds", -80.0, -55.0, 105.0, 125.0, step=dense
    )

    # Central Burnaby fill — stop west of the New West X-band.
    _urban_grid(
        highways, "bn_central", x_will, -55.0, y_rumble, 200.0, step=HALF_MILE
    )
    _urban_grid(
        highways, "bn_north", x_will, x_gag, 220.0, y_hast, step=HALF_MILE
    )

    # Final safety wipe: drop any leftover non-NW stubs inside the box.
    _wipe_new_west_box(highways)


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
    # King George Blvd — Pattullo (McBride / Kingsway via 12th St) → Whalley → South Surrey.
    highways["king_george"] = {
        "lanes": 4,
        "points": yaml_pts(
            [
                (0.0, 32.0),  # Pattullo Bridge / McBride snap
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
    # Burnaby + New Westminster / Queensborough (Boundary → North Rd)
    # =====================================================================
    _build_burnaby_new_west(highways)

    _snap_highways(highways)

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
        "# Surrey + Langley + Delta + Richmond + Vancouver/UBC + Burnaby +"
        " New Westminster + Maple Ridge + Pitt Meadows — 2× arterials.\n"
        f"# Scale: {UNITS_PER_KM:g} units = 1.0 km; {UNITS_PER_MILE:g} units = 1.0 mile.\n"
        "# Anchor (0,0): King George Blvd & 104 Ave (Surrey City Centre / Whalley).\n"
        "# Scott Rd X=-84.4; Alex Fraser X=-116; Ferry tip X=-465; 276 St X=+717.4.\n"
        "# Compact Y: 88=-42.2, 72=-84.4, 56=-168.8, 32=-211.0, 16=-232.0, 0=-274.2.\n"
        "# Richmond: No.2 X=-473.7 … No.8 X=-220.5; Cambie Y=+20; Steveston Y=-106.6.\n"
        "# River gap: Richmond local roads stay west of X=-135; only Hwy 99/91/91A cross.\n"
        "# Vancouver: Marine Y=+90; Broadway Y=+216.5; Boundary X=-178; UBC tip X=-615.\n"
        "# North Arm gap: Richmond Y≈+55–70 ↔ Vancouver Marine Y=+90; Oak/Knight/Arthur Laing only.\n"
        "# Burnaby: Boundary X=-178 → North Rd X=+52; Willingdon X=-135.8; Hwy1 Port Mann→(64,42.2).\n"
        "# New West: Pattullo (−5,50→0,32); Queensborough Bridge (−68,45); Front/Columbia tilted grid.\n"
        "# Maple Ridge: Golden Ears bridge only (316.5,20→58); Lougheed / Dewdney / 287 St=+775.\n"
        "# Pitt Meadows: Pitt River Bridge X=+175 → Laity X=+353; Airport Way Y=+52; Polder north.\n"
        "# Road widths: ~0.5–0.8 (4–6 lane) / 0.3 (2-lane collectors). Z = 0 coplanar.\n"
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


if __name__ == "__main__":
    main()
