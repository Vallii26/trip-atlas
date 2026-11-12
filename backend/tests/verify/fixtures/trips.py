"""Hand-written evidence store + faithful diary for three small days (verifier fixtures).

Every block here is TRUE with respect to the evidence it cites and must verify as supported;
it is the false-positive measurement set and the seed corpus for mutation testing.
Three voices: Lisbon = plain "I", 24h, metric; hike = terse fragments; rail = chatty "we",
12h clock, miles.
"""

from __future__ import annotations

from datetime import date

from atlas.pipeline.models import DiaryBlock, Evidence, SourceRef, StyleProfile

LIS, HIK, RAIL = date(2025, 6, 14), date(2025, 7, 9), date(2025, 9, 23)   # Sat, Wed, Tue


def _ev(eid, day, moment, type_, payload, conf="high", src="derived"):
    return Evidence(id=eid, day=day, moment_id=moment, type=type_, payload=payload,
                    sources=[SourceRef(kind=src, ref=moment or "day")], confidence=conf)


def evidence() -> list[Evidence]:
    L, H, R = LIS, HIK, RAIL
    return [
        # ------------------------------------------------------------------ Lisbon city day
        _ev("lis_loc", L, None, "locality", {"locality": "Lisbon", "region": "Lisboa", "country": "Portugal",
                                             "country_code": "PT"}, src="geocoder"),
        _ev("lis_mkt_place", L, "m_mkt", "place", {"name": "Time Out Market", "category": "market",
                                                   "locality": "Lisbon", "country": "Portugal",
                                                   "approximate": False}, src="geocoder"),
        _ev("lis_mkt_time", L, "m_mkt", "time", {"start_local": "12:10", "end_local": "13:25",
                                                 "part_of_day": "afternoon"}, src="asset"),
        _ev("lis_mkt_kind", L, "m_mkt", "kind", {"kind": "market"}),
        _ev("lis_mkt_dur", L, "m_mkt", "duration", {"minutes": 75}),
        _ev("lis_mkt_photos", L, "m_mkt", "photo_count", {"count": 23}, src="asset"),
        _ev("lis_mkt_note", L, "m_mkt", "note",
            {"text": "Lunch was grilled sardines at Time Out Market. Honestly delicious, but so crowded."},
            src="voice"),
        _ev("lis_walk_move", L, "m_walk", "movement", {"mode": "walk", "distance_km": 2.4,
                                                       "from": "Time Out Market",
                                                       "to": "Miradouro de Santa Luzia"}, src="track"),
        _ev("lis_walk_time", L, "m_walk", "time", {"start_local": "13:25", "end_local": "14:05",
                                                   "part_of_day": "afternoon"}, src="track"),
        _ev("lis_walk_dur", L, "m_walk", "duration", {"minutes": 40}),
        _ev("lis_walk_kind", L, "m_walk", "kind", {"kind": "walk"}),
        _ev("lis_view_place", L, "m_view", "place", {"name": "Miradouro de Santa Luzia", "category": "viewpoint",
                                                     "locality": "Lisbon", "country": "Portugal",
                                                     "approximate": False}, src="geocoder"),
        _ev("lis_view_time", L, "m_view", "time", {"start_local": "14:05", "end_local": "14:50",
                                                   "part_of_day": "afternoon"}, src="asset"),
        _ev("lis_view_kind", L, "m_view", "kind", {"kind": "viewpoint"}),
        _ev("lis_view_photos", L, "m_view", "photo_count", {"count": 41}, src="asset"),
        _ev("lis_view_visual", L, "m_view", "visual", {"tags": ["water", "rooftops", "sky"]}, "medium", "asset"),
        _ev("lis_tram", L, "m_tram", "transport", {"mode": "tram", "line": "28",
                                                   "from": "Miradouro de Santa Luzia", "to": "Campo de Ourique",
                                                   "depart_local": "15:02", "arrive_local": "15:38",
                                                   "duration_min": 36}, src="track"),
        _ev("lis_cafe_place", L, "m_cafe", "place", {"name": "Pastelaria Aloma", "category": "cafe",
                                                     "locality": "Lisbon", "country": "Portugal",
                                                     "approximate": True}, "low", "geocoder"),
        _ev("lis_cafe_time", L, "m_cafe", "time", {"start_local": "15:45", "end_local": "16:20",
                                                   "part_of_day": "afternoon"}, src="asset"),
        _ev("lis_cafe_kind", L, "m_cafe", "kind", {"kind": "cafe"}, "medium"),
        _ev("lis_din_place", L, "m_din", "place", {"name": "Taberna da Rua das Flores", "category": "restaurant",
                                                   "locality": "Lisbon", "country": "Portugal",
                                                   "approximate": False}, "medium", "geocoder"),
        _ev("lis_din_time", L, "m_din", "time", {"start_local": "20:10", "end_local": "21:40",
                                                 "part_of_day": "evening"}, src="asset"),
        _ev("lis_din_kind", L, "m_din", "kind", {"kind": "meal"}),
        _ev("lis_din_dur", L, "m_din", "duration", {"minutes": 90}),
        _ev("lis_total_walk", L, None, "movement", {"mode": "walk", "distance_km": 7.8}, src="track"),
        # ------------------------------------------------------------------ hike day
        _ev("hik_loc", H, None, "locality", {"locality": "Chamonix", "region": "Haute-Savoie",
                                             "country": "France", "country_code": "FR"}, src="geocoder"),
        _ev("hik_hut_place", H, "h_hut1", "place", {"name": "Refuge du Lac Blanc", "category": "alpine_hut",
                                                    "locality": "Chamonix", "country": "France",
                                                    "approximate": False}, src="geocoder"),
        _ev("hik_hut_time", H, "h_hut1", "time", {"start_local": "06:30", "end_local": "07:10",
                                                  "part_of_day": "morning"}, src="asset"),
        _ev("hik_hut_visual", H, "h_hut1", "visual", {"tags": ["sunrise", "mountain", "lake"]}, "medium", "asset"),
        _ev("hik_hut_photos", H, "h_hut1", "photo_count", {"count": 12}, src="asset"),
        _ev("hik_up_move", H, "h_up", "movement", {"mode": "hike", "distance_km": 6.2,
                                                   "from": "Refuge du Lac Blanc", "to": "Col de la Glière"},
            src="track"),
        _ev("hik_up_time", H, "h_up", "time", {"start_local": "07:10", "end_local": "09:50",
                                               "part_of_day": "morning"}, src="track"),
        _ev("hik_up_dur", H, "h_up", "duration", {"minutes": 160}),
        _ev("hik_up_ele", H, "h_up", "elevation", {"ascent_m": 540, "max_ele_m": 2461}, src="track"),
        _ev("hik_up_kind", H, "h_up", "kind", {"kind": "hike"}),
        _ev("hik_pass_place", H, "h_pass", "place", {"name": "Col de la Glière", "category": "pass",
                                                     "locality": "Chamonix", "country": "France",
                                                     "approximate": True}, "low", "geocoder"),
        _ev("hik_pass_time", H, "h_pass", "time", {"start_local": "09:50", "end_local": "10:20",
                                                   "part_of_day": "morning"}, src="asset"),
        _ev("hik_pass_visual", H, "h_pass", "visual", {"tags": ["snow", "mountain"]}, "medium", "asset"),
        _ev("hik_first_high", H, "h_pass", "first", {"what": "altitude", "value": "2461 m",
                                                     "text": "Highest point of the trip"}),
        _ev("hik_lake_place", H, "h_lake", "place", {"name": "Lac Cornu", "category": "lake",
                                                     "locality": "Chamonix", "country": "France",
                                                     "approximate": False}, src="geocoder"),
        _ev("hik_lake_time", H, "h_lake", "time", {"start_local": "11:05", "end_local": "12:15",
                                                   "part_of_day": "morning"}, src="asset"),
        _ev("hik_lake_kind", H, "h_lake", "kind", {"kind": "swim"}, "medium"),
        _ev("hik_lake_dur", H, "h_lake", "duration", {"minutes": 70}),
        _ev("hik_lake_photos", H, "h_lake", "photo_count", {"count": 18}, src="asset"),
        _ev("hik_lake_note", H, "h_lake", "note", {"text": "Water was freezing. Stayed in maybe two minutes."},
            src="voice"),
        _ev("hik_down_move", H, "h_down", "movement", {"mode": "hike", "distance_km": 7.4, "from": "Lac Cornu",
                                                       "to": "Refuge du Lac Blanc"}, src="track"),
        _ev("hik_down_time", H, "h_down", "time", {"start_local": "12:40", "end_local": "15:55",
                                                   "part_of_day": "afternoon"}, src="track"),
        _ev("hik_down_dur", H, "h_down", "duration", {"minutes": 195}),
        _ev("hik_down_kind", H, "h_down", "kind", {"kind": "hike"}),
        _ev("hik_eve_place", H, "h_eve", "place", {"name": "Refuge du Lac Blanc", "category": "alpine_hut",
                                                   "locality": "Chamonix", "country": "France",
                                                   "approximate": False}, src="geocoder"),
        _ev("hik_eve_time", H, "h_eve", "time", {"start_local": "19:00", "end_local": "19:45",
                                                 "part_of_day": "evening"}, src="asset"),
        _ev("hik_eve_kind", H, "h_eve", "kind", {"kind": "meal"}),
        _ev("hik_eve_note", H, "h_eve", "note", {"text": "Soup and bread. In bed by nine."}, src="voice"),
        _ev("hik_eve_visual", H, "h_eve", "visual", {"tags": ["sunset", "mountain"]}, "low", "asset"),
        _ev("hik_total_move", H, None, "movement", {"mode": "hike", "distance_km": 13.6}, src="track"),
        _ev("hik_total_ele", H, None, "elevation", {"ascent_m": 920}, src="track"),
        # ------------------------------------------------------------------ rail day
        _ev("rail_vie_loc", R, "r_vie", "locality", {"locality": "Vienna", "country": "Austria",
                                                     "country_code": "AT"}, src="geocoder"),
        _ev("rail_vie_place", R, "r_vie", "place", {"name": "Wien Hauptbahnhof", "category": "station",
                                                    "locality": "Vienna", "country": "Austria",
                                                    "approximate": False}, src="geocoder"),
        _ev("rail_vie_time", R, "r_vie", "time", {"start_local": "06:15", "end_local": "06:40",
                                                  "part_of_day": "morning"}, src="asset"),
        _ev("rail_t1", R, "r_t1", "transport", {"mode": "train", "from": "Wien Hauptbahnhof",
                                                "to": "Budapest-Keleti", "depart_local": "06:40",
                                                "arrive_local": "09:19", "duration_min": 159}, src="track"),
        _ev("rail_t1_move", R, "r_t1", "movement", {"mode": "train", "distance_km": 243, "from": "Vienna",
                                                    "to": "Budapest"}, src="track"),
        _ev("rail_t1_border", R, "r_t1", "border", {"from_country": "Austria", "to_country": "Hungary"},
            src="track"),
        _ev("rail_bud_place", R, "r_bud", "place", {"name": "Budapest-Keleti", "category": "station",
                                                    "locality": "Budapest", "country": "Hungary",
                                                    "approximate": False}, src="geocoder"),
        _ev("rail_bud_time", R, "r_bud", "time", {"start_local": "09:19", "end_local": "10:10",
                                                  "part_of_day": "morning"}, src="asset"),
        _ev("rail_bud_kind", R, "r_bud", "kind", {"kind": "cafe"}, "medium"),
        _ev("rail_bud_note", R, "r_bud", "note", {"text": "Coffee and a pogácsa at Keleti."}, src="voice"),
        _ev("rail_t2", R, "r_t2", "transport", {"mode": "train", "from": "Budapest-Keleti", "to": "Gara de Nord",
                                                "depart_local": "10:10", "arrive_local": "23:55",
                                                "duration_min": 765}, src="track"),
        _ev("rail_t2_move", R, "r_t2", "movement", {"mode": "train", "distance_km": 825, "from": "Budapest",
                                                    "to": "Bucharest"}, src="track"),
        _ev("rail_t2_border", R, "r_t2", "border", {"from_country": "Hungary", "to_country": "Romania"},
            src="track"),
        _ev("rail_t2_tz", R, "r_t2", "timezone_change", {"from_offset_min": 120, "to_offset_min": 180},
            src="track"),
        _ev("rail_t2_first", R, "r_t2", "first", {"what": "country", "value": "Romania",
                                                  "text": "First time in Romania"}),
        _ev("rail_t2_photos", R, "r_t2", "photo_count", {"count": 34}, src="asset"),
        _ev("rail_t2_visual", R, "r_t2", "visual", {"tags": ["fields", "window"]}, "medium", "asset"),
        _ev("rail_buc_place", R, "r_buc", "place", {"name": "Gara de Nord", "category": "station",
                                                    "locality": "Bucharest", "country": "Romania",
                                                    "approximate": False}, src="geocoder"),
        _ev("rail_buc_time", R, "r_buc", "time", {"start_local": "23:55", "end_local": "00:10",
                                                  "part_of_day": "night"}, src="asset"),
        _ev("rail_total_move", R, None, "movement", {"mode": "train", "distance_km": 1068}, src="track"),
    ]


STYLES = {
    "lisbon": StyleProfile(person="i", clock="24h", units="metric"),
    "hike": StyleProfile(person="i", clock="24h", units="metric", fragments=0.8, avg_sentence_words=6),
    "rail": StyleProfile(person="we", clock="12h", units="imperial", avg_sentence_words=16),
}

_B = {
    "lisbon": (LIS, [
        ("Saturday, June 14, in Lisbon.", ["lis_loc"]),
        ("I reached Time Out Market at 12:10.", ["lis_mkt_place", "lis_mkt_time"]),
        ("Lunch was grilled sardines, and in my own words they were “honestly delicious”.",
         ["lis_mkt_note", "lis_mkt_kind", "lis_mkt_time"]),
        ("The market was crowded.", ["lis_mkt_note", "lis_mkt_place"]),
        ("I stayed for 75 minutes and took 23 photos.", ["lis_mkt_dur", "lis_mkt_photos"]),
        ("After lunch I walked 2.4 km to Miradouro de Santa Luzia.", ["lis_walk_move", "lis_mkt_note"]),
        ("The walk took 40 minutes.", ["lis_walk_dur", "lis_walk_kind"]),
        ("I got to Santa Luzia just after two in the afternoon.", ["lis_view_place", "lis_view_time"]),
        ("From the viewpoint I looked out over rooftops and water, and took 41 photos.",
         ["lis_view_kind", "lis_view_visual", "lis_view_photos"]),
        ("At 15:02 I took tram 28 from Miradouro de Santa Luzia to Campo de Ourique, a ride of 36 minutes.",
         ["lis_tram"]),
        ("Coffee somewhere near Pastelaria Aloma around a quarter to four.", ["lis_cafe_place", "lis_cafe_kind", "lis_cafe_time"]),
        ("Time Out Market first, then Miradouro de Santa Luzia, and later probably Pastelaria Aloma.",
         ["lis_mkt_place", "lis_mkt_time", "lis_view_place", "lis_view_time", "lis_cafe_place", "lis_cafe_time"]),
        ("Dinner was at Taberna da Rua das Flores, from 20:10 until 21:40.",
         ["lis_din_place", "lis_din_kind", "lis_din_time"]),
        ("Miradouro de Santa Luzia came before Taberna da Rua das Flores.",
         ["lis_view_place", "lis_view_time", "lis_din_place", "lis_din_time"]),
        ("Dinner lasted about an hour and a half.", ["lis_din_dur", "lis_din_kind", "lis_din_time"]),
        ("I walked about 8 km in all.", ["lis_total_walk"]),
    ]),
    "hike": (HIK, [
        ("Wednesday, 9 July. Chamonix, France.", ["hik_loc"]),
        ("Up at 06:30 at Refuge du Lac Blanc.", ["hik_hut_place", "hik_hut_time"]),
        ("Sunrise over the lake. 12 photos.", ["hik_hut_visual", "hik_hut_photos"]),
        ("Left the hut at 07:10.", ["hik_hut_place", "hik_hut_time"]),
        ("Hiked 6.2 km from Refuge du Lac Blanc, 540 m of climbing.", ["hik_up_move", "hik_up_ele", "hik_up_kind"]),
        ("2 h 40 on the trail.", ["hik_up_dur", "hik_up_kind"]),
        ("Reached what I think was Col de la Glière at 09:50.", ["hik_pass_place", "hik_pass_time"]),
        ("Snow up there.", ["hik_pass_visual"]),
        ("Highest point of the trip: 2,461 m.", ["hik_first_high", "hik_up_ele"]),
        ("Lac Cornu by 11:05. Swam.", ["hik_lake_place", "hik_lake_time", "hik_lake_kind"]),
        ("Water was freezing — in for “maybe two minutes”.", ["hik_lake_note"]),
        ("70 minutes at the lake, 18 photos.", ["hik_lake_dur", "hik_lake_photos", "hik_lake_place"]),
        ("Back to Refuge du Lac Blanc: 7.4 km, 3 h 15.", ["hik_down_move", "hik_down_dur", "hik_hut_place"]),
        ("Soup and bread at the hut at 19:00. Sunset, I think.",
         ["hik_eve_note", "hik_eve_place", "hik_eve_time", "hik_eve_visual"]),
        ("In bed by nine.", ["hik_eve_note"]),
        ("13.6 km and 920 m of ascent in all.", ["hik_total_move", "hik_total_ele"]),
    ]),
    "rail": (RAIL, [
        ("Tuesday, September 23, and we started in Vienna.", ["rail_vie_loc"]),
        ("We were at Wien Hauptbahnhof by quarter past six in the morning.", ["rail_vie_place", "rail_vie_time"]),
        ("Our train left at 6:40 am and got into Budapest-Keleti at 9:19 am.", ["rail_t1"]),
        ("That's about 150 miles in a little over two and a half hours.", ["rail_t1_move", "rail_t1"]),
        ("Somewhere along the way we crossed the border from Austria into Hungary.", ["rail_t1_border"]),
        ("We had coffee and a pogácsa at Keleti.", ["rail_bud_note", "rail_bud_place", "rail_bud_kind"]),
        ("Then the train from Budapest to Bucharest left at 10:10 am.", ["rail_t2", "rail_t2_move"]),
        ("It was a ride of roughly 510 miles.", ["rail_t2_move"]),
        ("We crossed the border into Romania and the clocks went forward by an hour.",
         ["rail_t2_border", "rail_t2_tz"]),
        ("It was our first time in Romania.", ["rail_t2_first", "rail_t2_border"]),
        ("We took 34 photos out of the window.", ["rail_t2_photos", "rail_t2_visual"]),
        ("The ride took nearly thirteen hours.", ["rail_t2"]),
        ("We pulled into Gara de Nord just before midnight.", ["rail_buc_place", "rail_buc_time"]),
        ("Wien Hauptbahnhof first, then Budapest-Keleti, then Gara de Nord.",
         ["rail_vie_place", "rail_vie_time", "rail_bud_place", "rail_bud_time", "rail_buc_place", "rail_buc_time"]),
        ("Two trains and about 660 miles in all.", ["rail_t1", "rail_t2", "rail_total_move"]),
    ]),
}


def blocks(day_key: str) -> list[DiaryBlock]:
    day, rows = _B[day_key]
    ev = {e.id: e for e in evidence()}
    out = []
    for k, (text, ids) in enumerate(rows):
        moments = sorted({ev[i].moment_id for i in ids if ev[i].moment_id})
        out.append(DiaryBlock(id=f"{day_key}_{k + 1:02d}", day=day, pos=float(k + 1), text=text,
                              evidence_ids=ids, moment_ids=moments))
    return out


DAY_KEYS = list(_B)

# gazetteer names known to the system (includes decoys near the visited places, DECISIONS D9)
KNOWN_PLACES = [
    "Time Out Market", "Miradouro de Santa Luzia", "Miradouro da Graça", "Miradouro das Portas do Sol",
    "Pastelaria Aloma", "Taberna da Rua das Flores", "Campo de Ourique", "Castelo de São Jorge",
    "Mercado de Campo de Ourique", "Lisbon", "Porto", "Sintra", "Portugal", "Spain",
    "Refuge du Lac Blanc", "Lac Blanc", "Lac Cornu", "Col de la Glière", "Col des Montets",
    "Refuge de Bellachat", "Chamonix", "Argentière", "France", "Switzerland", "Italy",
    "Wien Hauptbahnhof", "Wien Westbahnhof", "Budapest-Keleti", "Budapest-Nyugati", "Gara de Nord",
    "Vienna", "Budapest", "Bucharest", "Bratislava", "Brașov", "Austria", "Hungary", "Romania", "Slovakia",
]
