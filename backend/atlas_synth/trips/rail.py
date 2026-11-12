"""Rail: London → Paris → Zürich → Vienna → Budapest → Bucharest → Istanbul in ten days.

Three UTC offsets (+60, +120, +180), two changes that happen mid-day on a train, two night
trains that cross a day boundary, a camera left on London time, and a phone that lags two hours
behind the Romanian border.
"""

from __future__ import annotations

from ..spec import CameraSpec, TripBuilder
from .hostile import IPHONE

SAMPLE = """
We took the sleeper up to Fort William in February, which everyone said was the wrong month, and
everyone was right, though not in the way they meant. The train left Euston at a quarter past nine
and by the time I'd worked out how the little sink folded away we were somewhere north of Watford
and the attendant was asking, very gently, whether I wanted porridge or a bacon roll at seven.

I slept badly and happily. Around five I gave up, pulled the blind and watched Rannoch Moor come out
of the dark, all of it white, not a road or a light anywhere, a single stag standing beside the line
as though it had been asked to. The bacon roll cost four pounds fifty and was, I think, the best
thing I ate all year.

Fort William itself was shut. We walked along the loch in sideways sleet, bought a map we didn't
need from the one open shop, and sat in a café with steamed-up windows until it was time for the
train back. I'd do it again tomorrow. I'd probably bring better gloves.
"""


def define(seed: int = 3309):
    ip = dict(IPHONE, model="iPhone 13", lens="iPhone 13 back dual wide camera 5.1mm f/1.6", software="17.6.1")
    cams = [
        CameraSpec(id="phone", folder="iphone-13", start_no=7310,
                   notes="iPhone; for ~2 h after the HU→RO border its clock and offset stayed on UTC+2 (GPS stamps stay correct)", **ip),
        CameraSpec(id="camera", make="SONY", model="ILCE-6400", lens="E 18-135mm F3.5-5.6 OSS", folder="sony-a6400",
                   prefix="DSC0", start_no=2231, software="ILCE-6400 v2.00", tz_mode="stuck_home", clock_error_s=194,
                   base_offset_min=60, quality=90,
                   notes="left on London time (UTC+1) for the whole trip and 3 min 14 s fast; no GPS, no offset tag"),
    ]
    b = TripBuilder(
        "rail", "London to Istanbul by train", seed,
        {"lat": 51.5850, "lon": -0.0200, "tz": "Europe/London", "tz_offset_min": 60, "locality": "London", "country_code": "GB"},
        {"name": "Priya", "voice": "first person, past tense, long understated sentences with dry asides, British spelling, notes prices and small details"},
        cams, SAMPLE, sun=(6.5, 20.0), heic=6, exact_dups=3, near_dups=4, noexif=4, corrupt=("truncated", "zero"),
        p_nogps_out=0.04, p_nogps_in=0.5,
        ele_default={"London": 20, "Paris": 35, "Zürich": 410, "Wien": 170, "Budapest": 105, "București": 80, "İstanbul": 30},
        notes=["The Bucharest → Istanbul sleeper crosses Bulgaria without a stop that produced a moment; BG therefore is "
               "not in stats.countries, but a fact of 2024-09-09 states the crossing.",
               "Train paths are polylines through real intermediate stations, not the surveyed track.",
               "Train times are plausible but not copied from a timetable."])
    TW = "train_window"

    # ---------------------------------------------------------------- 1 London → Paris
    b.day("2024-09-01", tz=60, sun=(6.2, 20.5))
    b.m("08:40", 35, "lon/caravan-kings-cross", "cafe", "cafe", n=5, imp=2, mix={"food": 0.4}, kw=["Caravan", "King's Cross", "breakfast"])
    b.m("09:25", 50, "lon/st-pancras-international", "station", "station", n=8, c=4, imp=3, look={"hall": True, "train_col": (250, 200, 40)},
        kw=["St Pancras", "Eurostar"])
    b.shot("09:40", "boarding_pass", ["Eurostar 9014", "LON", "PAR", "10:24", "Coach 7", "Seat 52"])
    b.m("10:24", 143, "lon/st-pancras-international", "transit", TW, n=12, c=5, imp=4, to="par/gare-du-nord", transport="train",
        via=[(51.4430, 0.3210, 10), (51.1437, 0.8750, 40), (51.0970, 1.1560, 20), (50.9240, 1.8100, 5), (50.6393, 3.0757, 25), (49.8590, 2.8320, 80)],
        tz_change=(0.28, 120), look={"land": "fields"}, kw=["Eurostar", "Paris", "train"])
    b.gap("11:53", "12:14", "Channel Tunnel")
    b.voice("12:20", "Out of the tunnel and it's suddenly an hour later. Flat fields, pylons, the first French cows. My phone says welcome to France.",
            ["tunnel", "France", "hour later"], "Took the Eurostar through the Channel Tunnel; the clocks went forward an hour in France.", True)
    b.m("14:00", 10, "par/gare-du-nord", "station", "station", n=4, imp=2, look={"hall": True, "train_col": (250, 200, 40)}, kw=["Gare du Nord"])
    b.m("15:00", 20, "par/hotel-jeanne-d-arc", "lodging", "hotel_room", n=2, imp=1, go="train", kw=["hotel", "Marais"])
    b.m("15:40", 35, "par/place-des-vosges", "park", "park", n=8, c=4, imp=3, kw=["Vosges"])
    b.m("16:30", 45, "par/l-as-du-fallafel", "meal", "street", n=7, imp=4, mix={"food": 0.5}, looks={"food": {"dish": "street"}},
        kw=["Fallafel", "falafel"], hard="street-food meal; two other falafel places stand within 40 m")
    b.fact("food", "Late lunch was a falafel from L'As du Fallafel, eaten standing in the street.", ["falafel", "Fallafel"], True)
    b.m("17:40", 40, "par/notre-dame", "sight", "landmark", n=10, c=6, imp=4, look={"shape": "cathedral", "spire": 0.14}, kw=["Notre-Dame", "Notre Dame"])
    b.m("18:30", 25, "par/shakespeare-and-company", "shop", "street", n=5, imp=2, look={"tiles": True}, kw=["Shakespeare", "bookshop"])
    b.m("20:30", 90, "par/chez-janou", "meal", "restaurant", n=8, imp=3, mix={"food": 0.4}, look={"wall": (190, 150, 60)}, kw=["Chez Janou", "dinner"])
    b.fact("food", "Dinner at Chez Janou in the Marais, finishing with the chocolate mousse served from a huge bowl.", ["Chez Janou", "mousse"])
    b.m("22:35", 25, "par/pont-neuf", "sight", "waterfront_night", n=6, imp=3, go="walk", look={"feature": "bridge"}, kw=["Pont Neuf", "Seine"])
    b.stay("par/hotel-jeanne-d-arc")
    b.forbid("Ate at Miznon.", ["Miznon"])
    b.forbid("Visited the Sainte-Chapelle.", ["Sainte-Chapelle"])
    b.forbid("Crossed the Channel by ferry.", ["ferry"])
    b.forbid("Had ice cream at Berthillon.", ["Berthillon"])

    # ---------------------------------------------------------------- 2 Paris
    b.day("2024-09-02", sun=(7.1, 20.5))
    b.m("08:35", 25, "par/du-pain-et-des-idees", "cafe", "cafe", n=6, imp=3, go="walk", mix={"food": 0.5}, looks={"food": {"dish": "pastry"}},
        kind_alt=["shop"], kw=["Du Pain et des Idées", "bakery", "escargot"])
    b.fact("food", "Breakfast was a pistachio escargot pastry from the bakery Du Pain et des Idées.", ["Du Pain et des Idées", "pastry", "pistachio"])
    b.m("09:05", 30, "par/canal-saint-martin", "sight", "waterfront", n=6, c=4, imp=2, r=45, look={"feature": "bridge", "rail": False},
        kind_alt=["walk", "park"], kw=["Canal Saint-Martin", "canal"])
    b.m("10:00", 150, "par/musee-du-louvre", "museum", "museum", n=24, c=8, imp=5, go="train", mix={"landmark": 0.12},
        looks={"landmark": {"shape": "palace"}}, kw=["Louvre"])
    b.gap("10:20", "11:40", "no signal in the lower galleries")
    b.voice("11:50", "Two and a half hours in the Louvre and I saw perhaps four rooms. The Mona Lisa is a small painting behind a hundred phones. "
            "The Winged Victory at the top of the staircase is the thing.",
            ["Louvre", "Mona Lisa", "Winged Victory"], "Spent two and a half hours in the Louvre; saw the Mona Lisa and the Winged Victory.", True)
    b.m("12:55", 50, "par/jardin-des-tuileries", "park", "park", n=8, c=3, imp=3, mix={"food": 0.3}, looks={"food": {"dish": "salad"}},
        look={"pond": True}, kind_alt=["meal"], kw=["Tuileries", "picnic"], hard="picnic lunch in a park: park or meal")
    b.m("14:30", 30, "par/trocadero", "viewpoint", "landmark", n=9, c=6, imp=4, go="train", look={"shape": "eiffel"}, kw=["Trocadéro", "Trocadero"])
    b.m("15:10", 80, "par/tour-eiffel", "sight", "landmark", n=14, c=6, imp=5, mix={"park": 0.25}, look={"shape": "eiffel", "lawn": True},
        kw=["Eiffel"])
    b.fact("activity", "Stayed on the ground at the Eiffel Tower and lay on the grass of the Champ de Mars instead of queueing.", ["Eiffel", "Champ de Mars"], True)
    b.stay("par/hotel-jeanne-d-arc")
    b.m("19:40", 50, "par/sacre-coeur", "viewpoint", "city_sunset", n=10, c=7, imp=5, go="train", look={"roofs": "grey", "landmark": "tower", "river": False},
        kw=["Sacré-Cœur", "Sacre-Coeur", "Montmartre", "sunset"])
    b.voice("20:10", "Sunset from the steps of Sacré-Cœur with half of Paris. Someone's playing the guitar badly. The whole city has gone gold.",
            ["Sacré-Cœur", "sunset"], "Watched the sunset over Paris from the steps of Sacré-Cœur.", True)
    b.m("20:50", 80, "par/bouillon-pigalle", "meal", "restaurant", n=7, imp=3, mix={"food": 0.4}, look={"wall": (226, 220, 206), "cloth": (250, 250, 250)},
        kw=["Bouillon Pigalle", "dinner"])
    b.stay("par/hotel-jeanne-d-arc")
    b.forbid("Went up to the top of the Eiffel Tower.", ["top of the Eiffel", "went up the Eiffel", "summit of the Eiffel"])
    b.forbid("Visited the Musée d'Orsay.", ["Orsay"])
    b.forbid("Had hot chocolate at Angelina.", ["Angelina"])
    b.forbid("Saw a show at the Moulin Rouge.", ["Moulin Rouge"])

    # ---------------------------------------------------------------- 3 Paris → Zürich → night train
    b.day("2024-09-03", sun=(6.9, 20.1))
    b.m("08:30", 40, "par/marche-d-aligre", "market", "market", n=12, c=5, imp=4, kw=["Aligre", "market"])
    b.m("09:50", 27, "par/gare-de-lyon", "station", "station", n=5, c=2, imp=2, look={"hall": True, "train_col": (200, 40, 40)}, kw=["Gare de Lyon"])
    b.m("10:22", 244, "par/gare-de-lyon", "transit", TW, n=12, c=6, imp=3, to="zrh/zurich-hb", transport="train",
        via=[(47.3230, 5.0270, 245), (47.3070, 5.9540, 280), (47.5860, 6.8990, 360), (47.7420, 7.3430, 240), (47.5476, 7.5896, 270)],
        look={"land": "hills"}, kw=["Zürich", "Zurich", "TGV", "train"])
    b.voice("12:30", "TGV to Zürich, upstairs, forwards. Burgundy is all pale cows and church spires. Sandwich from the market, six euros of comté.",
            ["TGV", "Zürich", "comté"], "Took the TGV from Paris to Zürich and ate a comté sandwich bought at the Marché d'Aligre.", False)
    b.m("15:10", 30, "zrh/lindenhof", "viewpoint", "city_view", n=7, c=4, imp=3, look={"roofs": "grey", "landmark": "dome"}, kw=["Lindenhof"])
    b.m("15:52", 33, "zrh/confiserie-sprungli", "cafe", "cafe", n=5, imp=3, mix={"food": 0.4}, looks={"food": {"dish": "dessert"}},
        kw=["Sprüngli", "Sprungli"])
    b.m("16:40", 35, "zrh/grossmunster", "sight", "landmark", n=8, c=4, imp=3, look={"shape": "cathedral", "spire": 0.1}, kind_alt=["worship"],
        kw=["Grossmünster", "Grossmunster"])
    b.m("17:30", 45, "zrh/burkliplatz", "sight", "waterfront", n=9, c=5, imp=4, look={"feature": None}, kind_alt=["viewpoint"],
        kw=["Bürkliplatz", "lake", "Zürichsee"])
    b.m("18:40", 80, "zrh/zeughauskeller", "meal", "restaurant", n=7, imp=3, mix={"food": 0.4}, look={"wood": True, "wall": (150, 110, 70)},
        looks={"food": {"dish": "meat"}}, kw=["Zeughauskeller", "dinner"])
    b.fact("food", "Dinner at the Zeughauskeller: veal sausage with rösti.", ["Zeughauskeller", "rösti", "sausage"])
    b.m("20:50", 45, "zrh/zurich-hb", "station", "station", n=5, imp=2, look={"hall": True, "train_col": (30, 60, 130)}, kw=["Zürich HB", "Hauptbahnhof"])
    b.m("21:40", 615, "zrh/zurich-hb", "transit", TW, n=12, c=3, imp=4, to="vie/wien-hbf", transport="train",
        via=[(47.0450, 9.4460, 480), (47.1680, 9.4790, 450), (47.2410, 9.6040, 460), (47.1290, 10.2680, 1300), (47.2632, 11.4010, 580),
             (47.4890, 12.0640, 510), (47.8130, 13.0450, 425), (48.2900, 14.2910, 260), (48.2080, 15.6240, 270)],
        when=[(0.0, 0.12), (0.84, 1.0)], phases=[(0.5, "train_interior"), (0.92, "train_window_sunrise"), (1.0, TW)],
        look={"land": "hills"}, kw=["night train", "Nightjet", "Vienna", "Wien", "sleeper"],
        hard="night train: one transit moment that crosses midnight with a 7-hour photo gap")
    b.voice("22:30", "Night train to Vienna. Three-berth sleeper, and the attendant took our breakfast order on a paper form. Lights along the Walensee going past.",
            ["night train", "Vienna", "sleeper"], "Took the night train from Zürich to Vienna in a three-berth sleeper compartment.", True)
    b.gap("23:35", "30:20", "phone off overnight on the night train")
    b.forbid("Flew from Paris to Zürich.", ["flew", "flight"])
    b.forbid("Had lunch at Le Train Bleu.", ["Train Bleu"])
    b.forbid("Swam in Lake Zürich.", ["swam", "swim"])
    b.forbid("Ate a cheese fondue.", ["fondue"])

    # ---------------------------------------------------------------- 4 Vienna
    b.day("2024-09-04", sun=(6.2, 19.5))
    b.m("08:05", 12, "vie/wien-hbf", "station", "station", n=3, imp=1, look={"hall": False, "train_col": (30, 60, 130)}, kw=["Wien Hbf", "Hauptbahnhof"])
    b.m("08:50", 45, "vie/cafe-sperl", "cafe", "cafe", n=6, imp=3, go="train", mix={"food": 0.35}, look={"wall": (220, 200, 160)}, kw=["Sperl", "breakfast"])
    b.m("09:50", 50, "vie/naschmarkt", "market", "market", n=12, c=5, imp=4, kw=["Naschmarkt"])
    b.m("10:55", 30, "vie/karlskirche", "sight", "landmark", n=7, c=4, imp=3, look={"shape": "dome"}, kind_alt=["worship"], kw=["Karlskirche"])
    b.m("11:50", 125, "vie/belvedere", "museum", "museum", n=16, c=6, imp=5, look={"gold": True}, kw=["Belvedere", "Klimt"])
    b.voice("13:10", "Stood in front of Klimt's Kiss for ten minutes. It's bigger than I'd thought and a great deal more gold.",
            ["Klimt", "Kiss", "Belvedere"], "Saw Klimt's The Kiss at the Belvedere.", True)
    b.m("14:25", 25, "vie/bitzinger", "meal", "street", n=5, imp=3, go="tram", mix={"food": 0.5}, looks={"food": {"dish": "street"}},
        kw=["Bitzinger", "Würstelstand", "sausage"], hard="lunch standing at a sausage stand on the street")
    b.fact("food", "Lunch was a Käsekrainer from the Bitzinger sausage stand behind the opera.", ["Bitzinger", "Käsekrainer", "sausage"])
    b.m("15:15", 45, "vie/stephansdom", "worship", "church", n=9, c=4, imp=4, kind_alt=["sight"], kw=["Stephansdom", "St. Stephen"])
    b.m("16:20", 55, "vie/cafe-central", "cafe", "cafe", n=7, imp=4, mix={"food": 0.4}, look={"wall": (236, 226, 200)},
        looks={"food": {"dish": "dessert"}}, kw=["Café Central", "Cafe Central"])
    b.voice("16:50", "Apfelstrudel and a melange at Café Central. There's a pianist. I am the worst-dressed person in the room.",
            ["Café Central", "Apfelstrudel", "melange"], "Had apfelstrudel and a melange at Café Central, where a pianist was playing.", True)
    b.stay("vie/hotel-beethoven")
    b.m("19:30", 85, "vie/figlmuller", "meal", "restaurant", n=7, imp=4, mix={"food": 0.4}, looks={"food": {"dish": "meat"}}, kw=["Figlmüller", "schnitzel"])
    b.voice("20:20", "The schnitzel at Figlmüller hangs over the edge of the plate on both sides. Potato salad on the side and nothing else.",
            ["Figlmüller", "schnitzel"], "Dinner at Figlmüller: a schnitzel larger than the plate, with potato salad.", True)
    b.m("21:35", 40, "vie/riesenrad", "sight", "landmark_night", n=7, c=4, imp=4, go="train", look={"shape": "wheel"}, kw=["Riesenrad", "Prater"])
    b.stay("vie/hotel-beethoven")
    b.forbid("Ate Sachertorte at Café Sacher.", ["Sacher"])
    b.forbid("Visited Schönbrunn.", ["Schönbrunn", "Schonbrunn"])
    b.forbid("Toured the Hofburg.", ["Hofburg"])
    b.forbid("Went to the opera.", ["Staatsoper", "went to the opera"])

    # ---------------------------------------------------------------- 5 Vienna → Budapest
    b.day("2024-09-05", sun=(6.2, 19.3))
    b.m("08:35", 100, "vie/schloss-schonbrunn", "sight", "park", n=12, c=6, imp=4, go="train", look={"palace": True}, kind_alt=["park"],
        kw=["Schönbrunn", "Schonbrunn"])
    b.m("11:05", 30, "vie/wien-hbf", "station", "station", n=4, imp=2, go="train", look={"hall": False, "train_col": (200, 40, 40)}, kw=["Wien Hbf", "Hauptbahnhof"])
    b.m("11:40", 159, "vie/wien-hbf", "transit", TW, n=8, c=4, imp=3, to="bud/keleti", transport="train",
        via=[(47.9130, 17.1560, 125), (47.6830, 17.6350, 115), (47.5860, 18.3950, 160), (47.4640, 19.0200, 110)],
        look={"land": "plain"}, kw=["Budapest", "Railjet", "train"])
    b.voice("13:05", "Railjet to Budapest. Wind turbines all the way to the border and then sunflowers, every one of them brown and finished.",
            ["Railjet", "Budapest", "sunflowers"], "Took the Railjet from Vienna to Budapest past wind turbines and dead sunflower fields.", False)
    b.m("14:25", 12, "bud/keleti", "station", "station", n=4, imp=2, look={"hall": True}, kw=["Keleti"])
    b.m("15:20", 20, "bud/hotel-rum", "lodging", "hotel_room", n=2, imp=1, go="train", kw=["hotel"])
    b.m("16:00", 55, "bud/great-market-hall", "market", "market_hall", n=12, c=5, imp=4, kw=["Market Hall", "Vásárcsarnok", "market"])
    b.fact("food", "Bought paprika and ate a lángos upstairs in the Great Market Hall.", ["Market Hall", "lángos", "paprika"])
    b.m("17:10", 25, "bud/szabadsag-hid", "sight", "waterfront", n=7, c=4, imp=3, look={"feature": "bridge"}, kw=["Szabadság", "Liberty Bridge", "Danube"])
    b.m("18:15", 65, "bud/citadella", "viewpoint", "city_sunset", n=10, c=8, imp=5, look={"roofs": "grey", "landmark": "dome"},
        kw=["Citadella", "Gellért Hill", "Gellert", "sunset"])
    b.voice("19:00", "Top of Gellért Hill. The sun's gone behind Buda and the bridges are being lit one after another, like someone working down a list.",
            ["Gellért Hill", "bridges", "sunset"], "Watched the sunset and the bridges lighting up from the Citadella on Gellért Hill.", True)
    b.m("20:15", 80, "bud/mazel-tov", "meal", "restaurant", n=7, imp=3, mix={"food": 0.4}, look={"wall": (60, 90, 70)}, kw=["Mazel Tov", "dinner"])
    b.m("22:00", 75, "bud/szimpla-kert", "bar", "bar", n=8, imp=4, look={"glow": (150, 255, 160)}, kw=["Szimpla", "ruin bar"])
    b.voice("22:40", "Szimpla Kert. A ruin bar with a bathtub for a sofa and half a Trabant in the courtyard. Beer is under two pounds.",
            ["Szimpla", "ruin bar", "Trabant"], "Had a drink at the ruin bar Szimpla Kert.", False)
    b.stay("bud/hotel-rum")
    b.forbid("Bathed at the Gellért Baths.", ["Gellért Baths", "Gellért fürdő", "bathed"])
    b.forbid("Dinner at Kőleves.", ["Kőleves", "Koleves"])
    b.forbid("Took the bus from Vienna.", ["bus"])
    b.forbid("Drank at the For Sale Pub.", ["For Sale"])

    # ---------------------------------------------------------------- 6 Budapest
    b.day("2024-09-06", sun=(6.2, 19.25))
    b.m("09:00", 55, "bud/new-york-cafe", "cafe", "cafe", n=8, imp=4, mix={"food": 0.3}, look={"wall": (226, 190, 110), "counter": (150, 110, 50)},
        kw=["New York", "breakfast"])
    b.m("10:35", 40, "bud/orszaghaz", "sight", "landmark", n=10, c=6, imp=4, go="tram", look={"shape": "palace", "dome_top": True, "stone": (226, 216, 196)},
        kw=["Parliament", "Országház"])
    b.m("11:35", 20, "bud/szechenyi-lanchid", "sight", "waterfront", n=7, c=3, imp=3, r=60, look={"feature": "bridge", "rail": True},
        kind_alt=["walk"], kw=["Chain Bridge", "Lánchíd"])
    b.m("12:25", 40, "bud/halaszbastya", "viewpoint", "city_view", n=10, c=6, imp=4, look={"roofs": "red", "landmark": "dome"},
        kw=["Fisherman's Bastion", "Halászbástya"])
    b.m("13:15", 40, "bud/ruszwurm", "cafe", "cafe", n=5, imp=3, mix={"food": 0.5}, looks={"food": {"dish": "dessert"}}, kw=["Ruszwurm"])
    b.fact("food", "Had the cream cake (krémes) at Ruszwurm on Castle Hill.", ["Ruszwurm", "krémes", "cream cake"])
    b.m("15:00", 110, "bud/szechenyi-furdo", "swim", "baths", n=6, imp=5, go="train", nogps=0.6, kw=["Széchenyi", "baths", "Szechenyi"])
    b.voice("16:10", "Széchenyi baths. Old men playing chess up to their chests in thirty-eight degree water. I stayed in until my fingers wrinkled.",
            ["Széchenyi", "baths", "chess"], "Spent the afternoon in the outdoor pools of the Széchenyi thermal baths.", True)
    b.stay("bud/hotel-rum")
    b.m("18:40", 70, "bud/frici-papa", "meal", "restaurant", n=5, imp=2, mix={"food": 0.4}, look={"wall": (230, 220, 190)}, looks={"food": {"dish": "soup"}},
        kw=["Frici Papa", "dinner", "goulash"])
    b.fact("food", "Dinner at Frici Papa: goulash soup.", ["Frici Papa", "goulash"])
    b.m("20:30", 60, "bud/vigado-ter-hajoallomas", "sight", "waterfront_night", n=9, c=5, imp=4, to="bud/vigado-ter-hajoallomas", transport="boat",
        via=[(47.5075, 19.0440, 100), (47.5150, 19.0420, 100), (47.4850, 19.0530, 100)], look={"feature": "bridge", "rail": True},
        kind_alt=["transit"], kw=["Danube", "cruise", "boat"],
        hard="evening river cruise: a sightseeing moment on a moving boat that returns to its dock")
    b.voice("21:00", "On the river. The Parliament lit up gold from the water is frankly ridiculous.",
            ["river", "Parliament"], "Took an evening boat cruise on the Danube past the illuminated Parliament.", True)
    b.stay("bud/hotel-rum")
    b.forbid("Took the guided tour inside the Parliament.", ["inside the Parliament", "guided tour"])
    b.forbid("Visited the Royal Palace of Buda.", ["Royal Palace", "Budavári"])
    b.forbid("Ate at Gundel.", ["Gundel"])
    b.forbid("Bathed at the Gellért Baths.", ["Gellért"])

    # ---------------------------------------------------------------- 7 Budapest → Bucharest
    b.day("2024-09-07", sun=(6.2, 19.75))
    b.m("06:35", 28, "bud/keleti", "station", "station", n=4, c=2, imp=2, go="car", look={"hall": True, "train_col": (60, 70, 80)}, kw=["Keleti"])
    b.m("07:10", 870, "bud/keleti", "transit", TW, n=22, c=10, imp=5, to="buc/gara-de-nord", transport="train",
        via=[(47.1790, 20.1790, 90), (46.6780, 21.0830, 90), (46.4300, 21.2330, 95), (46.3470, 21.3040, 100), (46.1900, 21.3230, 110),
             (45.8830, 22.9130, 190), (46.0700, 23.5900, 230), (46.1640, 24.3520, 300), (46.2200, 24.7930, 350), (45.6610, 25.6140, 540),
             (45.5060, 25.5770, 1040), (45.3530, 25.5540, 800), (44.9500, 26.0100, 160)],
        tz_change=(0.29, 180), lag_min=120, when=[(0.02, 0.76)], look={"land": "hills"},
        kw=["Bucharest", "București", "Transylvania", "train"],
        hard="14.5-hour day train across a time-zone change; the phone kept the old zone for two hours after the border")
    b.voice("12:40", "Crossed into Romania at Curtici. The border police took the passports away for twenty minutes. My phone still thinks it's an hour earlier.",
            ["Romania", "Curtici", "border"], "Crossed the Hungarian–Romanian border at Curtici, where the clocks go forward an hour.", True)
    b.shot("13:05", "chat", ["Mum", "in Romania now!", "train is 14 hours", "send pictures"])
    b.gap("15:10", "16:40", "no signal in the Mureș valley")
    b.voice("17:30", "Hour ten. Somewhere after Sighișoara: haystacks, horse carts waiting at the level crossings, the Carpathians on the right. "
            "The dining car does a decent ciorbă.",
            ["Sighișoara", "Carpathians", "ciorbă"], "Rode through Transylvania past Sighișoara and ate ciorbă in the dining car.", False)
    b.m("22:50", 12, "buc/gara-de-nord", "station", "station", n=3, imp=2, look={"hall": True, "sky": "night"}, kw=["Gara de Nord", "București Nord"])
    b.stay("buc/rembrandt-hotel")
    b.forbid("Changed trains in Brașov.", ["changed trains"])
    b.forbid("Flew to Bucharest.", ["flew", "flight"])
    b.forbid("Took a night train to Bucharest.", ["night train", "sleeper"])
    b.forbid("Stopped in Timișoara.", ["Timișoara", "Timisoara"])

    # ---------------------------------------------------------------- 8 Bucharest
    b.day("2024-09-08", sun=(6.75, 19.7))
    b.m("09:30", 40, "buc/origo", "cafe", "cafe", n=5, imp=3, mix={"food": 0.2}, look={"wall": (60, 60, 64), "counter": (30, 30, 34)}, kw=["Origo", "coffee"])
    b.m("10:30", 50, "buc/cismigiu", "park", "park", n=9, c=5, imp=3, look={"pond": True}, kw=["Cișmigiu", "Cismigiu"])
    b.m("11:45", 60, "buc/palatul-parlamentului", "sight", "landmark", n=10, c=6, imp=4, look={"shape": "palace", "stone": (222, 216, 204)},
        kw=["Parliament", "Parlamentului", "Casa Poporului"])
    b.voice("12:10", "The Palace of the Parliament isn't a building, it's a weather system. It took ten minutes just to walk along the front of it.",
            ["Palace of the Parliament"], "Walked along the front of the enormous Palace of the Parliament (outside only).", False)
    b.m("13:20", 80, "buc/caru-cu-bere", "meal", "restaurant", n=9, imp=5, mix={"food": 0.4}, look={"wood": True, "wall": (110, 70, 40), "drink_col": (236, 190, 60)},
        looks={"food": {"dish": "meat"}}, kw=["Caru' cu Bere", "Caru cu Bere", "lunch"])
    b.voice("14:00", "Caru' cu Bere. Stained glass, carved wood, a waiter carrying twelve beers on one tray. Sarmale with mămăligă, and papanași that would feed four.",
            ["Caru' cu Bere", "sarmale", "papanași"], "Lunch at Caru' cu Bere: sarmale with mămăligă, then papanași.", True)
    b.m("14:50", 25, "buc/stavropoleos", "worship", "church", n=7, c=4, imp=3, look={"gold": True}, kw=["Stavropoleos"],
        hard="church ~65 m from the restaurant of the previous moment, 10 minutes later")
    b.m("15:30", 30, "buc/carturesti-carusel", "shop", "street", n=5, imp=3, kw=["Cărturești", "Carturesti", "bookshop"])
    b.m("16:20", 25, "buc/piata-revolutiei", "sight", "landmark", c=6, imp=2, look={"shape": "monument"}, kw=["Revoluției", "Revolution Square"])
    b.m("17:00", 30, "buc/ateneul-roman", "sight", "landmark", n=7, c=3, imp=3, look={"shape": "dome"}, kw=["Ateneul", "Athenaeum"])
    b.stay("buc/rembrandt-hotel")
    b.m("20:00", 90, "buc/lacrimi-si-sfinti", "meal", "restaurant", n=6, imp=3, mix={"food": 0.4}, look={"wall": (70, 80, 70)}, kw=["Lacrimi și Sfinți", "dinner"])
    b.stay("buc/rembrandt-hotel")
    b.forbid("Toured the Village Museum.", ["Village Museum", "Muzeul Satului", "Satului"])
    b.forbid("Dinner at Hanu' lui Manuc.", ["Manuc"])
    b.forbid("Took the tour inside the Palace of the Parliament.", ["inside the Palace", "guided tour"])
    b.forbid("Walked to the Arcul de Triumf.", ["Arcul de Triumf", "Triumphal Arch"])

    # ---------------------------------------------------------------- 9 Bucharest → (night) → Istanbul
    b.day("2024-09-09", sun=(6.75, 19.6))
    b.m("09:20", 50, "buc/gara-de-nord", "station", "station", n=6, c=2, imp=2, go="car", look={"hall": True, "train_col": (30, 60, 130)},
        kw=["Gara de Nord", "București Nord"])
    b.shot("09:35", "boarding_pass", ["CFR Călători", "BUC", "IST", "10:50", "Vagon 483", "Loc 36"])
    b.m("10:50", 1220, "buc/gara-de-nord", "transit", TW, n=18, c=8, imp=5, to="ist/halkali-gar", transport="train",
        via=[(43.9010, 25.9700, 25), (43.8350, 25.9560, 45), (43.1260, 25.6890, 140), (42.4320, 25.6220, 200), (42.0590, 25.5930, 100),
             (41.7660, 26.1960, 60), (41.7170, 26.3570, 45), (41.6600, 26.5400, 40), (41.2850, 28.0000, 160)],
        when=[(0.02, 0.43), (0.76, 0.79), (0.955, 1.0)], phases=[(0.44, TW), (0.9, "train_interior"), (1.0, "train_window_sunrise")],
        look={"land": "plain"}, kw=["Istanbul", "İstanbul", "sleeper", "night train", "Bosphorus Express"],
        hard="20-hour sleeper through three countries with a border stop at 02:30; one transit moment across midnight")
    b.fact("transport", "The sleeper crossed the Danube at Giurgiu–Ruse and ran through Bulgaria overnight without a stop to get off.",
           ["Bulgaria", "Danube"])
    b.voice("15:10", "Crossed the Danube at Giurgiu on the Friendship Bridge and now it's Bulgaria: sunflower fields and storks' nests on the poles.",
            ["Danube", "Bulgaria", "Giurgiu"], "Crossed the Danube into Bulgaria on the Friendship Bridge at Giurgiu.", True)
    b.gap("22:30", "29:50", "phone off overnight on the sleeper")
    b.voice("26:40", "Kapıkule, half past two in the morning. Everyone off the train with their bags for the X-ray, then back to bed.",
            ["Kapıkule", "border"], "Had to leave the train at about 02:30 for the Turkish border control at Kapıkule.", False)
    b.forbid("Flew to Istanbul.", ["flew", "flight"])
    b.forbid("Spent a day in Sofia.", ["Sofia"])
    b.forbid("Took a bus across the border.", ["bus"])
    b.forbid("Visited the Village Museum before leaving.", ["Village Museum", "Satului"])

    # ---------------------------------------------------------------- 10 Istanbul
    b.day("2024-09-10", sun=(6.55, 19.4))
    b.m("07:20", 12, "ist/halkali-gar", "station", "station", n=4, imp=2, look={"hall": False}, kw=["Halkalı", "Halkali"])
    b.m("07:45", 45, "ist/halkali-gar", "transit", "train_interior", n=3, imp=2, to="ist/sirkeci-gar", transport="train",
        via=[(40.9800, 28.8200, 10), (40.9900, 28.9200, 10), (41.0040, 28.9520, 10)], look={"window": (190, 210, 230), "bunks": False},
        kw=["Marmaray", "Sirkeci"])
    b.m("08:50", 40, "ist/hafiz-mustafa-sirkeci", "cafe", "cafe", n=6, imp=3, mix={"food": 0.5}, looks={"food": {"dish": "dessert", "drink_col": (150, 50, 30)}},
        kw=["Hafız Mustafa", "Hafiz Mustafa", "baklava"])
    b.fact("food", "Breakfast was baklava and tea at Hafız Mustafa by Sirkeci station.", ["Hafız Mustafa", "baklava"])
    b.m("10:00", 75, "ist/ayasofya", "sight", "landmark", n=14, c=8, imp=5, mix={"church": 0.4}, look={"shape": "mosque", "stone": (214, 150, 130)},
        looks={"church": {"dome": True, "gold": True, "carpet": (40, 130, 130)}}, kind_alt=["worship"], kw=["Ayasofya", "Hagia Sophia"])
    b.voice("10:40", "Hagia Sophia. Shoes off, neck back. Fifteen hundred years old and the dome still looks as if it's floating.",
            ["Hagia Sophia", "dome"], "Visited Hagia Sophia and stood under its dome.", True)
    b.m("11:30", 50, "ist/sultanahmet-camii", "worship", "landmark", n=10, c=5, imp=4, mix={"church": 0.4},
        look={"shape": "mosque", "stone": (200, 206, 222)}, looks={"church": {"dome": True, "carpet": (170, 40, 40), "stone": (150, 170, 200)}},
        kind_alt=["sight"], kw=["Blue Mosque", "Sultanahmet"],
        hard="second great mosque ~400 m from the previous one, 15 minutes later, visually similar")
    b.m("12:40", 50, "ist/sultanahmet-koftecisi", "meal", "restaurant", n=6, imp=3, mix={"food": 0.4}, look={"wall": (236, 236, 230), "evening": False},
        looks={"food": {"dish": "meat"}}, kw=["Köftecisi", "köfte", "lunch"])
    b.m("14:00", 80, "ist/kapalicarsi", "market", "market_hall", n=14, c=6, imp=5, kw=["Grand Bazaar", "Kapalıçarşı", "bazaar"])
    b.m("16:05", 30, "ist/galata-koprusu", "sight", "waterfront", n=8, c=5, imp=3, look={"feature": "mosque", "rail": True}, kw=["Galata Bridge", "Galata Köprüsü"])
    b.m("16:55", 25, "ist/eminonu-iskelesi", "transit", "waterfront", n=8, c=5, imp=4, to="ist/kadikoy-iskelesi", transport="boat",
        via=[(41.0120, 28.9950, 0), (41.0030, 29.0100, 0)], look={"feature": "tower", "rail": True}, kw=["ferry", "Kadıköy", "Bosphorus"])
    b.voice("17:05", "Ferry to Kadıköy for the price of a bus ticket. Tea in a tulip glass, gulls following the boat, Europe behind and Asia in front.",
            ["ferry", "Kadıköy", "tea"], "Took the ferry from Eminönü across the Bosphorus to Kadıköy on the Asian side.", True)
    b.m("17:35", 55, "ist/ciya-sofrasi", "meal", "restaurant", n=8, imp=4, mix={"food": 0.5}, look={"wall": (226, 210, 180), "evening": False}, kw=["Çiya", "Ciya", "dinner"])
    b.m("18:52", 45, "ist/moda-sahili", "viewpoint", "waterfront_sunset", n=10, c=8, imp=5, look={"feature": "mosque", "rail": False},
        kw=["Moda", "sunset"])
    b.voice("19:15", "Last evening. London to Istanbul without leaving the ground: ten days, seven trains and one ferry. "
            "The sun is going down behind the old city, seen from the Asian side.",
            ["Moda", "sunset", "seven trains"], "Ended the journey watching the sunset from the Moda seafront in Kadıköy.", True)
    b.forbid("Visited Topkapı Palace.", ["Topkapı", "Topkapi"])
    b.forbid("Went down into the Basilica Cistern.", ["Cistern", "Yerebatan"])
    b.forbid("Climbed the Galata Tower.", ["Galata Tower", "Galata Kulesi"])
    b.forbid("Shopped in the Spice Bazaar.", ["Spice Bazaar", "Mısır"])
    for mo in b.moments:  # trim to the 450-550 photo target while keeping the relative rhythm
        mo.n = max(1, round(mo.n * 0.58)) if mo.n else 0
        mo.c = max(1, round(mo.c * 0.58)) if mo.c else 0
    return b
