from __future__ import annotations

from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

from atlas.pipeline.diary.verify import DiaryReport, extract_claims, verify_block, verify_diary
from atlas.pipeline.models import BlockVerdict, DiaryBlock


def test_fixture_diaries_verify_clean(fx):
    for key in fx.trips.DAY_KEYS:
        blocks = fx.trips.blocks(key)
        assert 8 <= len(blocks) <= 16
        rep = verify_diary(blocks, fx.trips.evidence(), known_places=fx.known, style=fx.trips.STYLES[key])
        assert isinstance(rep, DiaryReport)
        assert rep.failures == [], [(f.block_id, f.claim_text, f.reason) for f in rep.failures]
        assert rep.blocks == len(blocks) and rep.claims > rep.blocks
        assert rep.fabrication_rate == 0.0 and rep.claim_fabrication_rate == 0.0
        # every sentence carries at least one checked claim: nothing passes vacuously
        assert all(s.verdicts for v in rep.verdicts for s in v.sentences)


def test_report_counts_and_rates(fx):
    blocks = fx.trips.blocks("hike")
    blocks[2] = blocks[2].model_copy(update={"text": "Sunrise over the lake. 12 photos. A marmot whistled."})
    blocks[4] = blocks[4].model_copy(update={"origin": "edited", "text": "Hiked forever with Ana, glorious."})
    rep = verify_diary(blocks, fx.trips.evidence(), known_places=fx.known, style=fx.trips.STYLES["hike"])
    assert rep.testimony_blocks == 1 and rep.blocks == len(blocks) - 1
    assert rep.unsupported_blocks == 1 and rep.unsupported_sentences == 1
    assert rep.fabrication_rate == 1 / rep.sentences
    assert rep.claim_fabrication_rate == rep.unsupported_claims / rep.claims
    assert {f.block_id for f in rep.failures} == {blocks[2].id}
    assert all(f.reason for f in rep.failures)


def test_user_testimony_supported_by_definition(fx):
    for origin in ("edited", "user"):
        b = DiaryBlock(id="u1", day=date(2025, 6, 14), pos=1, text="Ana and I ate goulash on the moon.",
                       origin=origin)
        v = verify_block(b, fx.evidence)
        assert v.supported and v.testimony and "testimony" in v.reason and isinstance(v, BlockVerdict)


def test_citation_failures(fx):
    v = fx.check("lisbon_02", "I reached Time Out Market at 12:10.", ["does_not_exist"])
    assert not v.supported and any(x.claim.kind == "citation" for x in v.verdicts)
    v = fx.check("lisbon_02", "I reached Time Out Market at 12:10.", ["lis_mkt_place", "lis_mkt_time", "hik_loc"])
    assert not v.supported and "another day" in v.reason
    v = fx.check("lisbon_02", "I went there.", [])
    assert not v.supported and "cites no evidence" in v.reason
    assert all(not s.supported for s in v.sentences)


def test_empty_block(fx):
    for text in ("", "   ", "\n"):
        v = fx.check("lisbon_02", text)
        assert v.supported and v.verdicts == []


def test_cross_block_order(fx):
    blocks = fx.trips.blocks("lisbon")
    late, early = blocks[12], blocks[1]            # dinner 20:10, market 12:10
    swapped = [late.model_copy(update={"pos": 1.0}),
               early.model_copy(update={"pos": 2.0, "text": "Then I reached Time Out Market at 12:10."})]
    rep = verify_diary(swapped, fx.trips.evidence(), known_places=fx.known, style=fx.trips.STYLES["lisbon"])
    assert rep.unsupported_blocks == 1 and "time order" in rep.failures[0].reason


def test_deterministic(fx):
    blocks = fx.trips.blocks("rail")
    a = verify_diary(blocks, fx.trips.evidence(), known_places=fx.known, style=fx.trips.STYLES["rail"])
    b = verify_diary(blocks, fx.trips.evidence(), known_places=fx.known, style=fx.trips.STYLES["rail"])
    assert a.model_dump() == b.model_dump()


def test_serialisation_roundtrip(fx):
    v = fx.check("lisbon_09", "From the viewpoint I saw dolphins and “a quote”.")
    data = v.model_dump_json()
    assert "unlicensed" in data and "quote" in data


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=200))
def test_never_crashes_on_arbitrary_unicode(text):
    extract_claims(text)


_ALPHABET = st.sampled_from(list("abcdefghij ABCDEFG.,;:!?—-–'’“”\"()0123456789\n\t") + [
    "é", "İ", "ß", "ø", "🍷", "́", "‍", "at ", "by ", "half past ", " km", " m ", " h ", "June ", " am",
    "o'clock ", "a quarter to ", "and a half ", "Then ", "about ", "first ", "hours ", "1,000", "12:60", "25:00"])


@settings(max_examples=300, deadline=None)
@given(st.lists(_ALPHABET, max_size=60).map("".join))
def test_never_crashes_on_claim_shaped_noise(fx_text):
    from atlas.eval.mutations import load_fixture_cases
    global _FX
    try:
        _FX
    except NameError:
        by_day, trips, _ = load_fixture_cases()
        _FX = ({c.block.id: c for cs in by_day.values() for c in cs}, {e.id: e for e in trips.evidence()})
    cases, ev = _FX
    for bid in ("lisbon_10", "hike_14", "rail_09"):
        v = verify_block(cases[bid].block.model_copy(update={"text": fx_text}), ev, style=cases[bid].style)
        assert isinstance(v.supported, bool)
        assert v.supported == all(x.supported for x in v.verdicts)
