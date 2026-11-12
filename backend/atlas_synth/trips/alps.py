"""Alps: five days hut to hut on the Alta Via 1 in the Dolomites. Poor signal, long moments."""

from __future__ import annotations

from ..spec import CameraSpec, TripBuilder

SAMPLE = """
Karwendel, day two! We leave the Falkenhütte at 6:40 and the whole north face of the Laliderer is
orange. Nobody talks for the first half hour, we just walk and look. 900 metres up to the
Birkkarspitze, the last 200 on scree that slides back half a step for every step. Anna counts
chamois: eleven before breakfast!

At 10:15 we are on top, 2749 m, the highest point of the range. Wind from the west, clouds building
over the Wetterstein. We eat the last of the cheese and a squashed banana and it tastes fantastic.
Then down, and down, and down. 1400 metres of descent to the Karwendelhaus and my knees file a formal
complaint at around metre 600.

We reach the hut at 14:30. Radler on the terrace, boots off, socks steaming in the sun. The hut
warden says thunderstorms from 17:00 and he is right to the minute! We watch the lightning from the
window with Kaiserschmarrn in front of us. Total for the day: 14 km, 950 up, 1420 down, 7 hours 50
with breaks. Tomorrow is shorter. We always say that.
"""


def define(seed: int = 2207):
    cams = [
        CameraSpec(id="phone", make="Google", model="Pixel 7", lens="Pixel 7 back camera 6.81mm f/1.85", folder="pixel-7",
                   prefix="PXL_", ext="jpg", naming="pixel", software="HDR+ 1.0.540104767zd", has_gps=True, writes_offset=True,
                   tz_mode="auto", quality=88,
                   notes="Pixel: file names carry the UTC capture time; ~40% of photos have no GPS fix (airplane mode / no signal)"),
        CameraSpec(id="camera", make="Canon", model="Canon PowerShot G7 X Mark II", lens="8.8-36.8mm", folder="canon-g7x",
                   prefix="IMG_", start_no=412, tz_mode="manual", clock_error_s=-3720, quality=90, subsec=True,
                   notes="clock 1 h 2 min behind local time (still on winter time, plus drift); no GPS, no offset tag"),
    ]
    b = TripBuilder(
        "alps", "Alta Via 1: hut to hut in the Dolomites", seed,
        {"lat": 48.1310, "lon": 11.5560, "tz": "Europe/Berlin", "tz_offset_min": 120, "locality": "München", "country_code": "DE"},
        {"name": "Tobias", "voice": "first person plural, present tense, enthusiastic, exact numbers (times, metres), exclamation marks"},
        cams, SAMPLE, sun=(5.75, 20.85), heic=4, exact_dups=2, near_dups=3, noexif=3, corrupt=("zero", "truncated"),
        wrong_date=True, screenshot_style="android", p_nogps_out=0.33, p_nogps_in=0.7, no_offset_share=0.1,
        notes=["Path geometry is a smoothed polyline through real waypoints; elevations are interpolated between the "
               "waypoints' real altitudes, so the profile is realistic but not surveyed.",
               "2024-07-24 has no track at all and most phone photos of that day have no GPS."])
    D = "dol/"

    # ------------------------------------------------------------------ day 1
    b.day("2024-07-22", tz=120)
    b.shot("08:05", "map", ["Lago di Braies", "3 h 05 to Rifugio Biella"])
    b.m("08:40", 32, D + "lago-di-braies", "sight", "lake", n=10, c=6, imp=4, look={"boats": True}, kw=["Braies", "Pragser Wildsee", "lake"])
    b.m("09:20", 185, D + "lago-di-braies", "hike", "trail", n=26, c=12, imp=5, to=D + "rifugio-biella",
        via=[(46.6880, 12.0870, 1500), (46.6760, 12.0900, 1800), (46.6680, 12.0950, 2100), D + "forcella-sora-forno"],
        phases=[(0.25, "forest"), (1.0, "trail")], kw=["Biella", "climb", "Braies", "Sora Forno"])
    b.fact("activity", "Climbed about 900 metres from Lago di Braies to Rifugio Biella in roughly three hours.", ["Biella", "Braies", "climb"], True)
    b.gap("10:30", "12:05", "no signal at the head of the valley")
    b.m("12:35", 55, D + "rifugio-biella", "meal", "hut_interior", n=6, imp=3, mix={"food": 0.35}, looks={"food": {"dish": "soup"}},
        kw=["Biella", "lunch"])
    b.m("13:45", 80, D + "rifugio-biella", "hike", "trail", n=10, c=6, imp=3, to=D + "croda-del-becco",
        via=[D + "forcella-sora-forno", (46.6640, 12.0920, 2600)], look={"scree": True}, kw=["Croda del Becco", "Seekofel", "ascent"])
    b.m("15:10", 35, D + "croda-del-becco", "summit", "summit", n=10, c=8, imp=5, kw=["Croda del Becco", "Seekofel", "summit"])
    b.voice("15:25", "On top of Croda del Becco, 2810 metres! You can see the whole lake we started from this morning, it's tiny from up here.",
            ["Croda del Becco", "2810"], "Stood on the summit of Croda del Becco (2810 m) and looked down on Lago di Braies.", True)
    b.m("15:50", 65, D + "croda-del-becco", "hike", "trail", n=5, c=2, imp=2, to=D + "rifugio-biella",
        via=[(46.6640, 12.0920, 2600), D + "forcella-sora-forno"], look={"scree": True}, kw=["descent", "Biella"])
    b.m("18:30", 60, D + "rifugio-biella", "meal", "hut_interior", n=4, imp=2, kw=["Biella", "dinner"])
    b.voice("19:10", "Dinner at Rifugio Biella is canederli in broth and a huge plate of polenta. Twelve of us in the bunk room tonight.",
            ["canederli", "polenta", "Biella"], "Dinner at Rifugio Biella: canederli in broth and polenta; slept in a twelve-bed bunk room.", False)
    b.m("20:28", 32, D + "rifugio-biella", "viewpoint", "mountain_sunset", n=8, c=6, imp=4, kw=["sunset", "Biella"])
    b.forbid("Rowed a boat on Lago di Braies.", ["rowed", "rowing", "boat"])
    b.forbid("Reached Rifugio Fanes.", ["Fanes"])
    b.forbid("Saw ibex on the way up.", ["ibex"])
    b.forbid("Slept at Rifugio Sennes.", ["Sennes"])

    # ------------------------------------------------------------------ day 2
    b.day("2024-07-23")
    b.m("05:32", 33, D + "rifugio-biella", "viewpoint", "mountain_sunrise", n=7, c=6, imp=5, kw=["sunrise", "Biella"])
    b.fact("activity", "Got up before six to watch the sunrise from Rifugio Biella.", ["sunrise", "Biella"], True)
    b.m("06:50", 35, D + "rifugio-biella", "lodging", "hut", n=3, imp=1, kw=["Biella", "hut"])
    b.m("07:50", 62, D + "rifugio-biella", "hike", "trail", n=8, c=4, imp=3, to=D + "lago-di-sennes",
        via=[(46.6520, 12.0930, 2250)], kw=["Sennes", "plateau"])
    b.m("08:56", 16, D + "lago-di-sennes", "wildlife", "wildlife", n=6, c=4, imp=4, burst=5, cburst=7,
        look={"animal": "marmot"}, kw=["marmot", "marmots"])
    b.voice("09:05", "Two marmots just below the lake at Sennes, one standing up like a little guard! They whistle when you get close.",
            ["marmot", "Sennes"], "Watched two marmots near Lago di Sennes.", True)
    b.m("09:16", 112, D + "lago-di-sennes", "hike", "trail", n=12, c=5, imp=3, to=D + "rifugio-pederu",
        via=[(46.6447, 12.0780, 2126), (46.6380, 12.0640, 1966), (46.6385, 12.0480, 1750)],
        phases=[(0.6, "trail"), (1.0, "forest")], kw=["Pederü", "Pederu", "descent"])
    b.m("11:15", 65, D + "rifugio-pederu", "meal", "hut_interior", n=6, imp=3, mix={"food": 0.4}, looks={"food": {"dish": "pasta"}},
        kw=["Pederü", "Pederu", "lunch"])
    b.m("12:40", 160, D + "rifugio-pederu", "hike", "trail", n=16, c=8, imp=4, to=D + "rifugio-fanes",
        via=[(46.6330, 12.0280, 1700), (46.6260, 12.0190, 1819), (46.6190, 12.0130, 1980)], kw=["Fanes", "climb"])
    b.gap("12:55", "14:50", "no signal in the Rudo valley")
    b.m("15:30", 25, D + "rifugio-fanes", "lodging", "hut", n=4, c=2, imp=2, look={"flag": (200, 30, 40)}, kw=["Fanes", "hut"])
    b.voice("15:50", "Fanes hut. Knees are fine, shoulders not. Beer on the terrace is four fifty and worth every cent!",
            ["Fanes", "beer"], "Arrived at Rifugio Fanes mid-afternoon and had a beer on the terrace.", False)
    b.m("18:45", 60, D + "rifugio-fanes", "meal", "hut_interior", n=4, imp=2, kw=["Fanes", "dinner"])
    b.forbid("Slept at Rifugio Lavarella.", ["Lavarella"])
    b.forbid("Swam in Lago di Sennes.", ["swam", "swim"])
    b.forbid("Climbed a summit.", ["summit", "peak"])
    b.forbid("Saw ibex.", ["ibex"])

    # ------------------------------------------------------------------ day 3 (no track)
    b.day("2024-07-24", nogps=(0.6, 0.9))
    b.notrack("tracking never started (phone in flight mode all day)")
    b.m("07:40", 55, D + "rifugio-fanes", "hike", "trail", n=6, c=3, imp=2, to=D + "lago-di-limo", via=[D + "passo-di-limo"],
        kw=["Limo"])
    b.m("08:40", 45, D + "lago-di-limo", "swim", "lake", n=7, c=3, imp=4, look={"swimmer": True, "water": (50, 130, 160)},
        kw=["Limo", "swim", "lake"])
    b.voice("08:55", "Swam in Lago di Limo before nine. Maybe ten strokes. It is unbelievably cold and I'm very awake now!",
            ["Limo", "swam", "cold"], "Swam in the very cold Lago di Limo before nine in the morning.", True)
    b.m("09:35", 210, D + "lago-di-limo", "hike", "trail", n=22, c=10, imp=5, to=D + "forcella-del-lago",
        via=[(46.5950, 12.0240, 2102), (46.5750, 12.0150, 2150), (46.5620, 12.0080, 2350)], kw=["Forcella del Lago", "Fanes"])
    b.m("13:10", 20, D + "forcella-del-lago", "wildlife", "wildlife", n=6, c=5, imp=5, cburst=6, look={"animal": "ibex"}, kw=["ibex"])
    b.voice("13:20", "Two ibex right above us at Forcella del Lago, a big male with huge horns just watching us. We stayed twenty minutes.",
            ["ibex", "Forcella del Lago"], "Saw two ibex at Forcella del Lago, one a big male.", True)
    b.m("13:35", 50, D + "forcella-del-lago", "hike", "trail", n=5, c=2, imp=2, to=D + "lago-di-lagazuoi",
        via=[(46.5530, 12.0020, 2330)], look={"scree": True}, kw=["Lagazuoi", "descent"])
    b.m("14:30", 45, D + "lago-di-lagazuoi", "meal", "lake", n=6, imp=3, mix={"food": 0.4}, look={"water": (30, 120, 110)},
        looks={"food": {"dish": "street", "table": (150, 146, 138)}}, kind_alt=["sight"], kw=["Lagazuoi", "lake", "picnic"],
        hard="picnic lunch on the shore of a lake: a meal with no restaurant, mostly scenery photos")
    b.fact("food", "Ate a picnic lunch on the shore of Lago di Lagazuoi.", ["picnic", "Lago di Lagazuoi"])
    b.m("15:25", 135, D + "lago-di-lagazuoi", "hike", "trail", n=12, c=6, imp=4, to=D + "rifugio-lagazuoi",
        via=[(46.5400, 12.0030, 2350), D + "forcella-lagazuoi"], look={"scree": True}, kw=["Lagazuoi", "climb"])
    b.m("17:50", 20, D + "rifugio-lagazuoi", "lodging", "hut", n=3, imp=2, kw=["Lagazuoi", "hut"])
    b.shot("17:58", "chat", ["Anna", "made it to Lagazuoi", "2752 m!", "no signal all day"])
    b.voice("18:05", "Knees are wrecked after that last climb to Lagazuoi, almost six hundred metres straight up at the end of the day.",
            ["knees", "Lagazuoi"], "The final climb to Rifugio Lagazuoi was close to 600 metres and hard on the knees.", False)
    b.m("19:00", 55, D + "rifugio-lagazuoi", "meal", "hut_interior", n=4, imp=2, kw=["Lagazuoi", "dinner"])
    b.m("20:28", 34, D + "rifugio-lagazuoi", "viewpoint", "mountain_sunset", c=9, imp=4, kw=["sunset", "Lagazuoi"])
    b.forbid("Took the cable car up to Lagazuoi.", ["cable car", "gondola"])
    b.forbid("Stopped at Rifugio Scotoni.", ["Scotoni"])
    b.forbid("Saw marmots.", ["marmot"])
    b.forbid("Crossed Passo di Valparola.", ["Valparola"])

    # ------------------------------------------------------------------ day 4
    b.day("2024-07-25")
    b.m("05:28", 40, D + "rifugio-lagazuoi", "viewpoint", "mountain_sunrise", n=8, c=5, imp=4, kw=["sunrise", "Lagazuoi"])
    b.m("07:45", 35, D + "piccolo-lagazuoi", "summit", "summit", n=8, c=5, imp=4, go="hike", kw=["Piccolo Lagazuoi", "summit", "Kleiner Lagazuoi"])
    b.m("08:40", 90, D + "piccolo-lagazuoi", "hike", "trail", n=8, c=3, imp=2, to=D + "passo-falzarego",
        via=[D + "rifugio-lagazuoi", D + "forcella-lagazuoi", (46.5250, 12.0120, 2350)], look={"scree": True}, kw=["Falzarego", "descent"])
    b.m("10:20", 150, D + "passo-falzarego", "hike", "trail", n=14, c=6, imp=3, to=D + "rifugio-averau",
        via=[(46.5180, 12.0200, 2054), (46.5130, 12.0230, 2171), (46.5060, 12.0300, 2300)], kw=["Averau", "Limides"])
    b.gap("10:40", "12:20", "no signal below the Averau walls")
    b.m("13:00", 65, D + "rifugio-averau", "meal", "hut_interior", n=8, imp=5, mix={"food": 0.45},
        looks={"food": {"dish": "pasta", "drink_col": (236, 190, 60)}}, kw=["Averau", "lunch"])
    b.voice("13:40", "Lunch at Rifugio Averau: casunziei, the beetroot ravioli with poppy seeds. Best meal of the whole trek!",
            ["Averau", "casunziei", "ravioli"], "Lunch at Rifugio Averau was casunziei (beetroot ravioli with poppy seeds).", True)
    b.m("14:20", 50, D + "rifugio-averau", "hike", "trail", n=5, c=3, imp=2, to=D + "rifugio-nuvolau", look={"scree": True},
        via=[(46.4985, 12.0410, 2480)], kw=["Nuvolau"])
    b.m("15:15", 45, D + "rifugio-nuvolau", "summit", "summit", n=10, c=8, imp=5, kind_alt=["viewpoint", "lodging"],
        kw=["Nuvolau"], hard="a hut that stands on a summit: summit, viewpoint and lodging all fit")
    b.voice("15:40", "Nuvolau! The hut sits right on the summit, drop on three sides. We are sleeping up here tonight.",
            ["Nuvolau", "summit"], "Reached Rifugio Nuvolau, a hut on the summit at 2575 m, and slept there.", True)
    b.m("18:50", 55, D + "rifugio-nuvolau", "meal", "hut_interior", n=3, imp=2, kw=["Nuvolau", "dinner"])
    b.m("20:26", 34, D + "rifugio-nuvolau", "viewpoint", "mountain_sunset", n=7, c=5, imp=4, kw=["sunset", "Nuvolau"])
    b.forbid("Rode the Lagazuoi cable car down.", ["cable car", "gondola"])
    b.forbid("Had lunch at Rifugio Scoiattoli.", ["Scoiattoli"])
    b.forbid("Climbed the via ferrata on Monte Averau.", ["via ferrata", "ferrata", "Monte Averau"])
    b.forbid("Walked around the Cinque Torri.", ["Cinque Torri"])

    # ------------------------------------------------------------------ day 5
    b.day("2024-07-26")
    b.m("07:05", 20, D + "rifugio-nuvolau", "lodging", "hut", n=3, imp=1, kw=["Nuvolau", "hut"])
    b.m("07:40", 90, D + "rifugio-nuvolau", "hike", "trail", n=8, c=4, imp=3, to=D + "passo-giau",
        via=[(46.4900, 12.0480, 2400)], look={"scree": True}, kw=["Giau", "descent"])
    b.m("09:15", 25, D + "passo-giau", "sight", "trail", n=5, c=3, imp=2, look={"sign": True, "scree": False}, kind_alt=["viewpoint"],
        kw=["Giau"])
    b.m("09:45", 165, D + "passo-giau", "hike", "trail", n=16, c=8, imp=4, to=D + "lago-federa",
        via=[D + "forcella-giau", D + "forcella-ambrizzola"], kw=["Federa", "Ambrizzola", "Croda da Lago"])
    b.gap("10:15", "11:50", "no signal in the Mondeval basin")
    b.m("12:35", 33, D + "lago-federa", "swim", "lake", n=6, c=3, imp=4, look={"swimmer": True, "water": (40, 110, 90)},
        kw=["Federa", "swim", "lake"], hard="swim in the lake, then lunch at the hut ~60 m from the shore 7 minutes later")
    b.voice("12:50", "Second swim of the trip, Lago Federa, with the Croda da Lago wall straight above. Warmer than Limo. Slightly!",
            ["Federa", "swim"], "Swam in Lago Federa below the Croda da Lago.", True)
    b.m("13:15", 65, D + "rifugio-croda-da-lago", "meal", "hut_interior", n=6, imp=3, mix={"food": 0.4}, kw=["Croda da Lago", "Palmieri", "lunch"],
        hard="lunch at the hut ~60 m from the lake where the previous moment (swim) took place")
    b.m("14:40", 100, D + "rifugio-croda-da-lago", "hike", "trail", n=8, c=3, imp=2, to=D + "ponte-de-ru-curto",
        via=[(46.4950, 12.1100, 1900)], phases=[(0.3, "trail"), (1.0, "forest")], kw=["Ru Curto", "descent"])
    b.m("16:32", 22, D + "ponte-de-ru-curto", "transit", "street", imp=1, to=D + "cortina-autostazione", transport="bus",
        via=[(46.5180, 12.1050, 1500), (46.5300, 12.1250, 1300)], kw=["Cortina", "bus"])
    b.shot("16:36", "chat", ["Bus 30/31", "Ponte de Ru Curto 16:32", "Cortina 16:54"])
    b.m("17:10", 40, D + "pasticceria-alvera", "cafe", "cafe", n=5, imp=3, mix={"food": 0.4}, looks={"food": {"dish": "dessert"}},
        kw=["Cortina", "Alverà", "Alvera"])
    b.voice("17:25", "Cortina. Five days, four huts, and now a coffee and an enormous slice of strudel. Legs are done!",
            ["Cortina", "strudel"], "Finished the trek in Cortina d'Ampezzo with coffee and strudel.", True)
    b.forbid("Climbed Monte Pelmo.", ["Pelmo"])
    b.forbid("Took a taxi to Cortina.", ["taxi"])
    b.forbid("Stopped at Malga Federa.", ["Malga"])
    b.forbid("Saw ibex again.", ["ibex"])
    for mo in b.moments:  # trim to the 300-400 photo target while keeping the relative rhythm
        mo.n = max(1, round(mo.n * 0.72)) if mo.n else 0
        mo.c = max(1, round(mo.c * 0.72)) if mo.c else 0
    return b
