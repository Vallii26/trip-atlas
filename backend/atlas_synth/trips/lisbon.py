"""Lisbon: a dense city weekend (3 days). Many short moments close together."""

from __future__ import annotations

from ..spec import CameraSpec, TripBuilder
from .hostile import IPHONE

SAMPLE = """
Copenhagen, Saturday. Woke up late and didn't feel bad about it. Coffee first, always coffee first: a
flat white from the place on the corner that takes itself very seriously. It was good, annoyingly.

Walked to Nyhavn because you have to. It's exactly like the postcards, which is the problem. Took the
same photo as everyone else and kept walking. The canal tour was better than I expected. Our guide
told the same joke in three languages and it wasn't funny in any of them, but the low bridges were.
You really do have to duck.

Lunch was smørrebrød at a counter. Herring, egg, something pink I didn't ask about. Eleven euros for
a slice of bread. I'd pay it again.

Afternoon in the botanical garden doing nothing. The palm house was warm and smelled like rain.
Jonas fell asleep on a bench for twenty minutes and I didn't wake him.

Dinner was hot dogs from a cart, eaten standing up. Then Tivoli at dusk, all the lights coming on
at once. I don't like rides. I went on two. Home by eleven, feet done, very happy.
"""


def define(seed: int = 1105):
    cams = [
        CameraSpec(id="phone", folder="iphone-14", start_no=4021, notes="iPhone; local time + OffsetTimeOriginal + GPS", **IPHONE),
        CameraSpec(id="camera", make="FUJIFILM", model="X-T30", lens="XF18-55mmF2.8-4 R LM OIS", folder="fuji-x-t30",
                   prefix="DSCF", start_no=1873, software="Digital Camera X-T30 Ver1.40", tz_mode="manual",
                   clock_error_s=443, quality=90,
                   notes="clock set by hand to local time but 7 min 23 s fast; no GPS, no offset tag"),
    ]
    b = TripBuilder(
        "lisbon", "A weekend in Lisbon", seed,
        {"lat": 52.3597, "lon": 4.8852, "tz": "Europe/Amsterdam", "tz_offset_min": 120, "locality": "Amsterdam", "country_code": "NL"},
        {"name": "Maren", "voice": "first person, past tense, short dry sentences, wry asides, food always noted, no exclamation marks"},
        cams, SAMPLE, sun=(6.3, 20.75), heic=6, exact_dups=3, near_dups=4, noexif=3, corrupt=("truncated", "text"),
        p_nogps_out=0.03, p_nogps_in=0.45)
    H = "lis/my-story-hotel-rossio"

    # ------------------------------------------------------------------ Friday
    b.day("2024-05-17", tz=60)
    b.m("10:20", 20, "lis/aeroporto-humberto-delgado", "station", "terminal", n=3, imp=2, kind_alt=["transit", "unknown"],
        kw=["airport", "Aeroporto", "arrival", "Lisbon"], hard="airport arrivals hall: there is no 'airport' moment kind")
    b.fact("transport", "Flew in and landed at Lisbon airport in the morning.", ["airport", "landed", "flew"])
    b.shot("10:31", "map", ["My Story Hotel Rossio", "24 min"])
    b.gap("10:48", "11:14", "metro (underground)")
    b.m("11:25", 15, H, "lodging", "hotel_room", n=2, imp=1, go="train", kw=["hotel", "Rossio"])
    b.m("12:00", 40, "lis/praca-do-comercio", "sight", "landmark", n=12, c=6, imp=4, look={"shape": "arch", "stone": (240, 214, 120)},
        kw=["Comércio", "Comercio", "Terreiro do Paço"])
    b.m("12:55", 95, "lis/time-out-market", "meal", "market_hall", n=14, c=3, imp=4, gap=35, mix={"food": 0.35},
        looks={"food": {"dish": "seafood"}}, kw=["Time Out", "Ribeira", "lunch"],
        hard="long lunch with a 35-minute gap without photos in the middle: still one moment")
    b.fact("food", "Lunch at Time Out Market: shared plates at the long communal tables.", ["Time Out", "lunch"], True)
    b.m("14:40", 12, "lis/rua-nova-do-carvalho", "sight", "street", n=5, imp=2, look={"pink": True}, kw=["Pink Street", "Carvalho"])
    b.m("15:02", 18, "lis/ascensor-da-bica", "sight", "tram", n=7, c=3, imp=3, kw=["Bica", "funicular", "Ascensor"])
    b.m("15:30", 35, "lis/miradouro-de-santa-catarina", "viewpoint", "waterfront", n=9, c=5, imp=3,
        look={"feature": "bridge"}, kw=["Santa Catarina", "Adamastor"])
    b.m("16:20", 18, "lis/manteigaria-chiado", "cafe", "cafe", n=6, imp=4, mix={"food": 0.5},
        looks={"food": {"dish": "pastry", "second": False}}, hard="first of two cafés back to back, ~55 m apart")
    b.voice("16:33", "The pastel de nata at Manteigaria was still warm from the oven, cinnamon on top. Ate two standing at the counter.",
            ["Manteigaria", "pastel de nata", "warm"], "Ate two warm pastéis de nata at Manteigaria, standing at the counter.", True)
    b.m("16:42", 23, "lis/quiosque-camoes", "cafe", "street", n=5, imp=2, mix={"food": 0.4},
        looks={"food": {"dish": "dessert", "drink_col": (240, 220, 120)}}, kw=["Quiosque", "Camões", "kiosk"],
        hard="second café ~55 m from the previous one, 4 minutes later (outdoor kiosk on the square)")
    b.fact("drink", "Had a lemonade at the kiosk on Praça Luís de Camões.", ["kiosk", "Quiosque", "lemonade"])
    b.m("17:30", 45, "lis/convento-do-carmo", "sight", "landmark", n=10, c=6, imp=3,
        look={"shape": "cathedral", "spire": 0.12, "stone": (206, 196, 180)}, kw=["Carmo"])
    b.stay(H)
    b.m("18:38", 17, H, "lodging", "hotel_room", n=2, imp=1, look={"evening": False}, kw=["hotel", "Rossio"])
    b.m("20:00", 95, "lis/cervejaria-ramiro", "meal", "restaurant", n=12, imp=5, mix={"food": 0.4},
        look={"dish": "seafood", "wall": (226, 226, 220), "drink_col": (236, 190, 60), "tiles": True},
        looks={"food": {"dish": "seafood", "drink_col": (236, 190, 60)}}, kw=["Ramiro", "dinner", "seafood"])
    b.voice("21:20", "Ramiro. Garlic prawns first, then the tiger prawns, and a steak sandwich for dessert, apparently that's the tradition here.",
            ["Ramiro", "prawns", "steak sandwich"], "Dinner at Cervejaria Ramiro: garlic prawns, tiger prawns and a steak sandwich to finish.", True)
    b.m("22:10", 25, "lis/miradouro-de-sao-pedro-de-alcantara", "viewpoint", "city_night", n=6, imp=3,
        look={"landmark": "castle"}, kw=["São Pedro de Alcântara", "Alcântara", "Alcantara"])
    b.m("22:50", 110, "lis/tasca-do-chico", "bar", "bar", n=9, imp=4, look={"stage": True, "glow": (255, 170, 60)},
        kw=["Tasca do Chico", "fado"], kind_alt=["event"])
    b.voice("23:40", "Squeezed into Tasca do Chico for fado. Everyone goes silent when she sings. No photos during the songs, so only a couple.",
            ["Tasca do Chico", "fado"], "Listened to live fado at Tasca do Chico in Bairro Alto.", True)
    b.stay(H)
    b.forbid("Had coffee at A Brasileira.", ["Brasileira"])
    b.forbid("Rode the Santa Justa lift.", ["Santa Justa"])
    b.forbid("Dinner at Marisqueira do Lis.", ["Marisqueira"])
    b.forbid("Went out to Belém.", ["Belém", "Belem"])
    b.forbid("Rode tram 28 through Alfama.", ["tram 28", "28E", "Alfama"])

    # ------------------------------------------------------------------ Saturday
    b.day("2024-05-18")
    b.m("08:45", 30, "lis/confeitaria-nacional", "cafe", "cafe", n=5, imp=2, mix={"food": 0.4},
        look={"wall": (236, 226, 200), "counter": (120, 80, 50)}, looks={"food": {"dish": "pastry"}}, kw=["Confeitaria Nacional", "breakfast"])
    b.m("09:28", 17, "lis/martim-moniz-28e", "transit", "tram", n=5, imp=4, to="lis/graca-28e", transport="tram",
        via=[(38.7181, -9.1346, 60)], kw=["28", "tram", "Graça"])
    b.fact("transport", "Rode the yellow tram 28 from Martim Moniz up to Graça.", ["tram 28", "28", "Graça"], True)
    b.m("09:52", 33, "lis/miradouro-da-graca", "viewpoint", "city_view", n=10, c=6, imp=3, look={"landmark": "castle"})
    b.m("10:45", 60, "lis/feira-da-ladra", "market", "market", n=20, c=8, imp=5, burst=6, kw=["Feira da Ladra", "flea market", "Ladra"])
    b.voice("11:20", "Bought two old azulejo tiles at Feira da Ladra for eight euros. The seller wrapped them in newspaper.",
            ["Feira da Ladra", "tiles", "eight euros"], "Bought two old azulejo tiles at the Feira da Ladra flea market for eight euros.", True)
    b.m("11:57", 25, "lis/miradouro-de-santa-luzia", "viewpoint", "city_view", n=9, c=4, imp=3, look={"landmark": "dome"},
        hard="first of two visits to the same viewpoint on the same day; also ~80 m from Miradouro das Portas do Sol")
    b.shot("12:31", "chat", ["Jonas", "found the sardine place", "table at 12:40?", "on my way"])
    b.m("12:38", 82, "lis/pateo-13", "meal", "restaurant", n=10, imp=4, mix={"food": 0.4},
        look={"dish": "seafood", "wall": (240, 236, 226), "evening": False, "drink_col": (240, 240, 210)},
        looks={"food": {"dish": "seafood"}}, kw=["Pateo 13", "sardines", "lunch"])
    b.fact("food", "Lunch at Pateo 13 in Alfama: grilled sardines at a table outside.", ["Pateo 13", "sardines"], True)
    b.m("14:15", 85, "lis/castelo-de-sao-jorge", "sight", "landmark", n=24, c=10, imp=5, burst=5, mix={"city_view": 0.3},
        look={"shape": "castle"}, looks={"city_view": {"landmark": "dome"}}, kw=["Castelo", "castle", "São Jorge"])
    b.voice("15:05", "Peacocks everywhere at the castle. One of them screamed right behind me and I nearly dropped the camera.",
            ["castle", "peacock"], "There were peacocks roaming at Castelo de São Jorge.", False)
    b.m("15:55", 30, "lis/se-de-lisboa", "worship", "church", n=8, c=3, imp=3, kw=["Sé", "cathedral", "Catedral"])
    b.m("16:45", 80, "lis/museu-nacional-do-azulejo", "museum", "museum", n=20, c=8, imp=4, go="car", look={"art": "tiles"},
        kw=["Azulejo", "tile museum", "Tile Museum"])
    b.gap("16:52", "17:38", "phone in battery saver inside the museum")
    b.stay(H)
    b.m("20:12", 40, "lis/miradouro-de-santa-luzia", "viewpoint", "city_sunset", n=10, c=8, imp=5, look={"landmark": "dome"},
        kw=["Santa Luzia", "sunset"], hard="second visit to Miradouro de Santa Luzia on the same day (sunset)")
    b.voice("20:40", "Back at Santa Luzia for sunset. Same spot as this morning, completely different light. The river's gone pink.",
            ["Santa Luzia", "sunset"], "Came back to Miradouro de Santa Luzia for sunset, the second visit of the day.", True)
    b.m("21:10", 85, "lis/chapito-a-mesa", "meal", "restaurant", n=8, imp=3, mix={"food": 0.35},
        look={"window": True, "evening": True, "wall": (60, 70, 90)}, kw=["Chapitô", "Chapito", "dinner"])
    b.m("22:52", 14, "lis/a-ginjinha", "bar", "night_street", n=4, imp=3, look={"neon": True}, kw=["Ginjinha", "ginja"])
    b.fact("drink", "Finished the night with a ginjinha (sour cherry liqueur) at A Ginjinha by Rossio.", ["ginjinha", "Ginjinha"])
    b.stay(H)
    b.forbid("Visited the Panteão Nacional.", ["Panteão", "Pantheon"])
    b.forbid("Ate at Alfama Cellar.", ["Alfama Cellar"])
    b.forbid("Went to the Museu do Fado.", ["Museu do Fado", "Fado Museum"])
    b.forbid("Watched the sunrise from Senhora do Monte.", ["Senhora do Monte", "sunrise"])
    b.forbid("Took the train out to Belém.", ["Belém", "Belem", "train"])

    # ------------------------------------------------------------------ Sunday
    b.day("2024-05-19")
    b.m("08:30", 20, H, "lodging", "hotel_room", n=2, imp=1, kw=["hotel", "Rossio", "check"])
    b.m("09:18", 27, "lis/praca-da-figueira-15e", "transit", "tram", n=4, imp=2, to="lis/mosteiro-dos-jeronimos-15e", transport="tram",
        via=[(38.7062, -9.1447, 5), (38.7040, -9.1640, 5), (38.7005, -9.1790, 5), (38.6966, -9.1990, 5)],
        look={"tram_col": (236, 236, 230)}, kw=["Belém", "15", "tram"])
    b.m("09:55", 62, "lis/mosteiro-dos-jeronimos", "sight", "landmark", n=18, c=8, imp=5, mix={"church": 0.35},
        look={"shape": "palace", "stone": (236, 228, 208), "lawn": True}, looks={"church": {"stone": (200, 190, 170)}},
        kw=["Jerónimos", "Jeronimos", "monastery"])
    b.m("11:08", 30, "lis/pasteis-de-belem", "cafe", "cafe", n=8, imp=4, mix={"food": 0.5}, look={"tiles": True},
        looks={"food": {"dish": "pastry"}}, kw=["Pastéis de Belém", "Pasteis de Belem"])
    b.voice("11:30", "Pastéis de Belém, the original. Honestly the one at Manteigaria on Friday was better, but the blue tiled rooms here are lovely.",
            ["Pastéis de Belém", "Manteigaria", "tiled"], "Had pastéis de nata at Pastéis de Belém and thought Friday's at Manteigaria were better.", True)
    b.m("11:50", 25, "lis/padrao-dos-descobrimentos", "sight", "landmark", n=9, c=4, imp=3, look={"shape": "monument", "stone": (236, 232, 222)},
        kw=["Padrão", "Descobrimentos", "Discoveries"])
    b.m("12:20", 22, "lis/padrao-dos-descobrimentos", "walk", "waterfront", n=6, imp=2, to="lis/torre-de-belem",
        via=[(38.6931, -9.2105, 3)], look={"feature": "bridge"}, kw=["riverside", "Tejo", "Tagus", "walk"])
    b.m("12:46", 44, "lis/torre-de-belem", "sight", "landmark", n=14, c=7, imp=5, burst=8, look={"shape": "tower"},
        kw=["Torre de Belém", "Belém Tower", "tower"])
    b.voice("13:15", "The queue for the tower was an hour, so we just sat on the wall with our feet over the water instead.",
            ["tower", "queue"], "Did not go inside the Torre de Belém because the queue was an hour long; sat on the river wall instead.", False)
    b.m("13:55", 65, "lis/a-praca-lx-factory", "meal", "restaurant", n=8, imp=3, go="car", mix={"food": 0.4},
        look={"wall": (90, 96, 100), "evening": False, "lamp": (240, 240, 230)}, kw=["LX Factory", "A Praça", "lunch"])
    b.m("15:30", 35, "lis/maat", "sight", "waterfront", n=8, c=4, imp=3, look={"feature": "bridge", "rail": False},
        kind_alt=["museum", "viewpoint"], kw=["MAAT"], hard="museum seen from outside only (walk over its roof by the river)")
    b.fact("activity", "Walked over the roof of the MAAT by the river without going into the museum.", ["MAAT", "roof"])
    b.m("17:35", 25, "lis/aeroporto-humberto-delgado", "station", "terminal", n=3, imp=1, go="car", kind_alt=["transit", "unknown"],
        kw=["airport", "Aeroporto", "departure", "home"], hard="airport departures hall: there is no 'airport' moment kind")
    b.shot("17:42", "boarding_pass", ["Boarding pass", "LIS", "AMS", "19:05", "B14", "23A", "Group 3"])
    b.forbid("Climbed to the top of the Torre de Belém.", ["climbed the tower", "top of the tower", "inside the tower"])
    b.forbid("Visited the Museu Nacional dos Coches.", ["Coches", "Coach Museum"])
    b.forbid("Had lunch at Time Out Market.", ["Time Out"])
    b.forbid("Browsed the Ler Devagar bookshop.", ["Ler Devagar", "bookshop"])
    b.forbid("Took tram 28.", ["tram 28", "28E"])
    return b
