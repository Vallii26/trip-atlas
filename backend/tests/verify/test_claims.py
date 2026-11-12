"""Unit tests per claim kind: true positives (fabrication caught) and tricky negatives."""

from __future__ import annotations

import pytest

from atlas.pipeline.diary.verify import extract_claims
from atlas.pipeline.models import StyleProfile


def kinds(text, **kw):
    return [(c.kind, c.text) for c in extract_claims(text, **kw)]


def bad(v):
    return [(x.claim.kind, x.claim.text) for x in v.verdicts if not x.supported]


# (block whose citations are used, text, expected supported)
CASES = [
    # --- places / localities / countries -------------------------------------------------------
    ("lisbon_02", "I reached Time Out Market at 12:10.", True),
    ("lisbon_02", "I reached the Time Out Market at 12:10.", True),              # "the"
    ("lisbon_02", "I reached time out market at 12:10.", True),                  # lowercased, still the cited words
    ("lisbon_02", "I reached Mercado da Ribeira at 12:10.", False),              # decoy
    ("lisbon_02", "I reached Refuge du Lac Blanc at 12:10.", False),             # other day
    ("lisbon_02", "I reached Pastelaria Aloma at 12:10.", False),                # same day, not cited
    ("lisbon_08", "I got to Santa Luzia just after two.", True),                 # safe partial
    ("lisbon_08", "I got to Miradouro just after two.", False),                  # generic-only partial
    ("lisbon_08", "I got to Luzia Cathedral just after two.", False),            # superset
    ("hike_05", "Hiked 6.2 km from Lac Blanc.", False),                          # partial = a different known place
    ("rail_13", "We pulled into Nord just before midnight.", False),
    ("rail_06", "We had coffee at Keleti.", True),                               # locality prefix dropped
    ("hike_02", "Up at 06:30 at Refuge du Lac Blanc.", True),
    ("hike_02", "Up at 06:30 at refuge du lac blanc.", True),
    ("hike_01", "Wednesday, 9 July. Chamonix, France.", True),
    ("hike_01", "Wednesday, 9 July. Chamonix, Switzerland.", False),
    ("rail_01", "Tuesday, September 23, and we started in İstanbul.", False),
    ("rail_01", "Then Vienna.", True),                                            # sentence-initial ordinary word
    # --- low confidence needs a hedge (D4) -----------------------------------------------------
    ("hike_07", "Reached Col de la Glière at 09:50.", False),
    ("hike_07", "Reached somewhere near Col de la Glière at 09:50.", True),
    ("hike_07", "Probably Col de la Glière at 09:50.", True),
    ("hike_07", "Probably Col des Montets at 09:50.", False),                    # hedging never rescues a wrong fact
    ("hike_14", "Soup and bread at the hut at 19:00. Sunset.", False),
    # --- times ---------------------------------------------------------------------------------
    ("lisbon_02", "I reached Time Out Market at 12:14.", True),                  # ±5
    ("lisbon_02", "I reached Time Out Market at 12:17.", False),
    ("lisbon_02", "I reached Time Out Market around 12:20.", True),              # hedged ±15
    ("lisbon_02", "I reached Time Out Market around 12:40.", False),
    ("lisbon_02", "I reached Time Out Market just after twelve.", True),
    ("lisbon_02", "I reached Time Out Market just before twelve.", False),
    ("lisbon_02", "I reached Time Out Market around noon.", True),
    ("lisbon_02", "I reached Time Out Market at 3 pm.", False),
    ("lisbon_02", "I left Time Out Market at half past one.", True),             # 13:25, ±7
    ("rail_03", "Our train left at 6:40 am and got into Budapest-Keleti at 9:19 am.", True),
    ("rail_03", "Our train left at 6:40 pm and got into Budapest-Keleti at 9:19 am.", False),
    ("rail_13", "We pulled into Gara de Nord just before midnight.", True),
    ("rail_13", "We pulled into Gara de Nord just after midnight.", False),
    # --- parts of day --------------------------------------------------------------------------
    ("lisbon_08", "I got to Santa Luzia in the afternoon.", True),
    ("lisbon_08", "I got to Santa Luzia in the morning.", False),
    ("lisbon_08", "I got to Santa Luzia in the evening.", False),
    ("lisbon_08", "I stayed at Santa Luzia all afternoon.", False),              # 45 minutes is not "all afternoon"
    ("hike_03", "Sunrise over the lake.", True),
    ("hike_03", "Sunset over the lake.", False),
    ("rail_13", "We pulled into Gara de Nord at night.", True),
    ("rail_02", "We were at Wien Hauptbahnhof early.", True),
    ("rail_02", "We were at Wien Hauptbahnhof late.", False),
    # --- durations -----------------------------------------------------------------------------
    ("lisbon_07", "The walk took 40 minutes.", True),
    ("lisbon_07", "A 40-minute walk.", True),
    ("lisbon_07", "The walk took 45 minutes.", False),
    ("lisbon_07", "The walk took about 45 minutes.", True),
    ("lisbon_07", "The walk took two hours.", False),
    ("lisbon_07", "The walk took over 40 minutes.", True),
    ("lisbon_07", "The walk took over an hour.", False),
    ("hike_06", "2 h 40 on the trail.", True),
    ("hike_06", "2 h 10 on the trail.", False),
    ("hike_06", "Nearly three hours on the trail.", True),
    ("rail_12", "The ride took nearly thirteen hours.", True),
    ("rail_12", "The ride took nearly six hours.", False),
    # --- distances -----------------------------------------------------------------------------
    ("lisbon_16", "I walked 8 km in all.", True),                                # 7.8 rounds to 8
    ("lisbon_16", "I walked 7 km in all.", False),
    ("lisbon_16", "I walked about 7 km in all.", True),                          # hedge widens modestly
    ("lisbon_16", "I walked about 10 km in all.", False),
    ("lisbon_16", "I walked about five miles in all.", True),                    # unit conversion
    ("lisbon_16", "I walked twelve kilometres in all.", False),
    ("lisbon_16", "I walked over 8 km in all.", False),                          # 7.8 is not over 8
    ("rail_08", "It was a ride of roughly 510 miles.", True),
    ("rail_08", "It was a ride of 600 miles.", False),
    # --- elevation -----------------------------------------------------------------------------
    ("hike_05", "Hiked 6.2 km, 540 m of climbing.", True),
    ("hike_05", "Hiked 6.2 km, 900 m of climbing.", False),
    ("hike_09", "Highest point of the trip: 2,461 m.", True),
    ("hike_09", "Highest point of the trip: 8,074 ft.", True),
    ("hike_09", "Highest point of the trip: 2,352 m.", False),
    # --- counts --------------------------------------------------------------------------------
    ("lisbon_05", "I took 23 photos.", True),
    ("lisbon_05", "I took 41 photos.", False),
    ("lisbon_05", "I took about 25 photos.", True),
    ("lisbon_05", "I took hundreds of photos.", False),
    ("rail_15", "Two trains in all.", True),
    ("rail_15", "Three trains in all.", False),
    ("lisbon_10", "I took tram 28.", True),
    ("lisbon_10", "I took tram 15.", False),
    # --- activities / transport ----------------------------------------------------------------
    ("lisbon_06", "I walked to Miradouro de Santa Luzia.", True),
    ("lisbon_06", "I took the tram to Miradouro de Santa Luzia.", False),
    ("lisbon_06", "I drove to Miradouro de Santa Luzia.", False),
    ("hike_10", "Swam.", True),
    ("hike_02", "Swam.", False),
    ("lisbon_13", "Dinner was at Taberna da Rua das Flores.", True),
    ("lisbon_13", "Lunch was at Taberna da Rua das Flores.", False),             # meal exists, wrong time of day
    ("lisbon_13", "Breakfast was at Taberna da Rua das Flores.", False),
    ("lisbon_03", "Lunch was grilled sardines.", True),                          # the note says "Lunch"
    ("lisbon_09", "I went to the museum.", False),
    ("rail_05", "We crossed the border from Austria into Hungary.", True),
    ("rail_05", "We took the ferry from Austria into Hungary.", False),
    ("rail_09", "The clocks went forward by an hour.", True),
    ("rail_09", "The clocks went backward by an hour.", False),
    ("rail_09", "The clocks went forward by two hours.", False),
    # --- food / weather / people / feelings: note only ----------------------------------------
    ("lisbon_03", "Lunch was grilled sardines.", True),
    ("lisbon_03", "Lunch was grilled octopus.", False),
    ("lisbon_13", "Dinner was goulash.", False),
    ("lisbon_13", "Dinner was a pastel de nata.", False),
    ("rail_06", "We had coffee and a pogácsa at Keleti.", True),                 # food word unknown to the lexicon, in note
    ("hike_08", "Snow up there.", True),                                          # visual tag
    ("hike_08", "Fog up there.", False),
    ("hike_08", "It was warm up there.", False),
    ("hike_11", "Water was freezing.", True),
    ("lisbon_09", "It rained.", False),
    ("lisbon_09", "It was sunny.", False),
    ("lisbon_04", "The market was crowded.", True),
    ("lisbon_09", "I went with Ana.", False),
    ("lisbon_09", "My brother took 41 photos.", False),
    ("lisbon_09", "A friendly waiter took 41 photos.", False),
    ("lisbon_04", "The sardines were delicious.", True),
    ("lisbon_04", "The tram was delicious.", False),                             # note word, wrong subject
    ("lisbon_09", "The viewpoint was breathtaking.", False),
    ("lisbon_16", "I walked about 8 km in all and was exhausted.", False),
    # --- firsts / superlatives -----------------------------------------------------------------
    ("rail_10", "It was our first time in Romania.", True),
    ("rail_10", "It was our first time in Hungary.", False),
    ("rail_09", "It was our first time in Romania.", False),                     # no `first` evidence cited
    ("hike_09", "Highest point of the trip: 2,461 m.", True),
    ("hike_16", "The longest day of the trip.", False),
    ("lisbon_09", "The best view of the trip.", False),
    # --- sequence ------------------------------------------------------------------------------
    ("lisbon_12", "Time Out Market first, then Miradouro de Santa Luzia.", True),
    ("lisbon_12", "Miradouro de Santa Luzia first, then Time Out Market.", False),
    ("lisbon_14", "Miradouro de Santa Luzia came before Taberna da Rua das Flores.", True),
    ("lisbon_14", "Miradouro de Santa Luzia came after Taberna da Rua das Flores.", False),
    ("lisbon_14", "After Taberna da Rua das Flores, Miradouro de Santa Luzia.", False),
    ("lisbon_14", "Before Taberna da Rua das Flores, Miradouro de Santa Luzia.", True),
    ("rail_07", "Then the train from Budapest to Bucharest left at 10:10 am.", True),
    ("rail_07", "Then the train from Bucharest to Budapest left at 10:10 am.", False),
    ("hike_13", "Back to Refuge du Lac Blanc: 7.4 km.", True),
    ("hike_10", "Back to Lac Cornu by 11:05.", False),                           # never there before
    # --- dates ---------------------------------------------------------------------------------
    ("lisbon_01", "Saturday, June 14, in Lisbon.", True),
    ("lisbon_01", "Sunday, June 14, in Lisbon.", False),
    ("lisbon_01", "Saturday, June 15, in Lisbon.", False),
    ("lisbon_01", "Saturday, 14 July, in Lisbon.", False),
    ("lisbon_01", "The 14th of June 2025, in Lisbon.", True),
    ("lisbon_01", "The 14th of June 2024, in Lisbon.", False),
    ("lisbon_01", "Yesterday in Lisbon.", False),
    # --- quotes / notes ------------------------------------------------------------------------
    ("hike_11", "In for “maybe two minutes”.", True),
    ("hike_11", "In for “maybe ten minutes”.", False),
    ("hike_11", "In for two minutes.", True),                                    # number from the note
    ("hike_11", "In for twenty minutes.", False),
    ("hike_15", "In bed by nine.", True),
    ("hike_15", "In bed by eleven.", False),
    # --- negation, emoji, pronouns: closed world ----------------------------------------------
    ("hike_10", "Lac Cornu by 11:05. Did not swim.", False),
    ("lisbon_02", "I never reached Time Out Market.", False),
    ("lisbon_04", "The market was crowded 🍷.", False),
    ("lisbon_02", "She reached Time Out Market at 12:10.", False),
    # --- binding -------------------------------------------------------------------------------
    ("lisbon_13", "Dinner at Taberna da Rua das Flores.", True),
]


@pytest.mark.parametrize("block_id,text,expected", CASES, ids=[f"{b}:{t[:48]}" for b, t, _ in CASES])
def test_claim_cases(fx, block_id, text, expected):
    v = fx.check(block_id, text)
    assert v.supported is expected, v.reason or [(x.claim.kind, x.claim.text, x.reason) for x in v.verdicts]


def test_binding_activity_to_place_across_moments(fx):
    ids = ["lis_din_kind", "lis_din_time", "lis_din_place", "lis_mkt_place"]
    v = fx.check("lisbon_13", "Dinner at Time Out Market.", ids)
    assert not v.supported and "different moments" in v.reason


def test_wrong_day_reason_distinguishes(fx):
    v = fx.check("lisbon_02", "I reached Lac Cornu at 12:10.")
    assert "other day 2025-07-09" in v.reason
    v = fx.check("lisbon_02", "I reached Pastelaria Aloma at 12:10.")
    assert "same day, other moment" in v.reason
    v = fx.check("lisbon_02", "I reached Castelo de São Jorge at 12:10.")
    assert "gazetteer" in v.reason
    v = fx.check("lisbon_02", "I reached Zanzibar at 12:10.")
    assert "proper noun not in cited evidence" in v.reason


def test_needs_hedge_reason(fx):
    v = fx.check("hike_07", "Reached Col de la Glière at 09:50.")
    assert "needs hedge" in v.reason


def test_narrative_person(fx):
    text = "We reached Time Out Market at 12:10."
    assert not fx.check("lisbon_02", text).supported                              # profile says "I"
    assert fx.check("lisbon_02", text, style=StyleProfile(person="we")).supported
    assert fx.check("lisbon_02", text, style=None).supported
    assert ("people", "We") in kinds(text, style=StyleProfile(person="i"))
    assert ("people", "We") not in kinds(text, style=StyleProfile(person="we"))


def test_no_false_proper_nouns():
    ks = kinds("Then coffee. After that I walked on. Saturday was the day. In June I left.")
    assert not [k for k in ks if k[0] in ("place", "locality", "country")]
    assert ("date", "Saturday") in ks and ("date", "June") in ks


def test_proper_noun_shapes():
    ks = dict((t, k) for k, t in kinds("From Miradouro de Santa Luzia to Refuge du Lac Blanc via İstanbul and "
                                       "Gara de Nord."))
    for name in ("Miradouro de Santa Luzia", "Refuge du Lac Blanc", "İstanbul", "Gara de Nord"):
        assert ks.get(name) == "place", ks


def test_extract_hedges_and_values():
    cs = {c.text: c for c in extract_claims("Just after eight we walked about four miles for roughly two hours; "
                                            "I think it rained.")}
    assert cs["eight"].kind == "time" and cs["eight"].value == "08:00"
    assert cs["four miles"].kind == "distance" and cs["four miles"].hedged
    assert abs(cs["four miles"].value - 6.437) < 0.01
    assert cs["two hours"].value == 120 and cs["two hours"].hedged
    assert cs["rained"].kind == "weather" and cs["rained"].hedged          # sentence-level "I think"
    cs = {c.text: c for c in extract_claims("At 2,352 m we took 41 photos in 2 h 35.")}
    assert cs["2,352 m"].kind == "elevation" and cs["2,352 m"].value == 2352
    assert cs["41 photos"].kind == "count" and cs["2 h 35"].value == 155


def test_sentence_attribution(fx):
    v = fx.check("hike_10", "Lac Cornu by 11:05. Swam. A marmot whistled.")
    assert [s.supported for s in v.sentences] == [True, True, False]
    assert all(x.claim.sentence == 2 for x in v.verdicts if not x.supported)
    assert "unlicensed word: 'marmot'" in v.reason


def test_coverage_backstop_switch(fx):
    text = "From the viewpoint I looked out over rooftops and water. Dolphins followed the boat."
    assert not fx.check("lisbon_09", text).supported
    v = fx.check("lisbon_09", "From the viewpoint I looked out over rooftops and water. Dolphins played.",
                 coverage=False)
    assert not v.supported            # "Dolphins" still fails as an unknown capitalised word
    v = fx.check("lisbon_09", "From the viewpoint I looked out over rooftops, water and dolphins.", coverage=False)
    assert v.supported                # the lexicon-only verifier is blind to an unknown lowercase noun
    assert not fx.check("lisbon_09", "From the viewpoint I looked out over rooftops, water and dolphins.").supported
