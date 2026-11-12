import pytest

from atlas.sync.hlc import format_hlc, parse_hlc
from atlas.sync.merge import (DEFAULT_SCHEMA, DELETED, PIPELINE, CollectionSchema, Doc, Mutation,
                              apply_mutation, conflict_id)

T = 1_780_000_000_000
DAY = 86_400_000
B = "diary_blocks"
n = iter(range(10**9))


def h(ms, dev="phone", c=0):
    return format_hlc(ms, c, dev)


def up(fields, base=None, hlc=None, id="b1", resolve=(), coll=B):
    return Mutation(f"op{next(n)}", coll, id, "t1", "upsert", hlc or h(T), fields, base or {}, tuple(resolve))


def rm(base=None, hlc=None, id="b1", resolve=()):
    return Mutation(f"op{next(n)}", B, id, "t1", "delete", hlc or h(T), {}, base or {}, tuple(resolve))


def ap(doc, m, server_ms=T + 10 * DAY, schema=DEFAULT_SCHEMA):
    return apply_mutation(doc, m, server_ms=server_ms, schema=schema)


def make(text="We walked to the market.", pos=1, dev="web", ms=T):
    doc, r = ap(None, up({"text": text, "pos": pos}, hlc=h(ms, dev)))
    assert r.status == "applied" and r.changed
    return doc


S0 = "We walked to the market."
A = "We ran to the market."
C = "We strolled to the market."


def test_create_sets_fields_and_meta_and_does_not_touch_rev():
    d = make()
    assert d.fields == {"text": S0, "pos": 1} and d.rev == 0 and not d.deleted and d.conflicts == []
    assert d.meta["text"] == {"hlc": h(T, "web"), "device": "web"}


def test_base_equal_applies_whatever_the_clock_says():
    """A phone whose clock is two days slow edits the value it has seen: applied, and restamped
    just after the value it replaced, so it is not later beaten by an older concurrent edit."""
    d = make(ms=T)
    d2, r = ap(d, up({"text": A, "pos": 5}, {"text": S0, "pos": 1}, hlc=h(T - 2 * DAY)))
    assert r.status == "applied" and d2.fields == {"text": A, "pos": 5}
    assert d2.meta["pos"]["hlc"] == format_hlc(T, 1, "phone") > d.meta["pos"]["hlc"]
    assert d == make()  # input untouched
    # a third device's concurrent scalar write stamped between the two loses to it
    d3, r = ap(d2, up({"pos": 9}, {"pos": 1}, hlc=h(T - DAY, "tablet")))
    assert r.status == "conflict" and r.fields == {"pos": "lost"} and d3 is d2 and not r.changed


def test_scalar_lww_higher_hlc_wins_loser_reported():
    d = make()
    d, _ = ap(d, up({"pos": 2}, {"pos": 1}, hlc=h(T + 50, "web")))
    lose, r = ap(d, up({"pos": 3}, {"pos": 1}, hlc=h(T + 20)))
    assert r.status == "conflict" and r.fields["pos"] == "lost" and lose.fields["pos"] == 2
    win, r = ap(d, up({"pos": 3}, {"pos": 1}, hlc=h(T + 80)))
    assert r.status == "applied" and win.fields["pos"] == 3 and win.conflicts == []


def test_same_device_later_arrival_wins_even_if_its_clamped_hlc_is_lower():
    d = make(dev="phone")
    far = T + 2 * DAY
    d, _ = ap(d, up({"pos": 2}, {"pos": 1}, hlc=h(far, c=5)), server_ms=T + 100)
    assert d.meta["pos"]["hlc"] == format_hlc(T + 100, 5, "phone")  # clamped
    d, r = ap(d, up({"pos": 3}, {"pos": 1}, hlc=h(far + 1000, c=0)), server_ms=T + 100)
    assert r.status == "applied" and d.fields["pos"] == 3


def test_future_clock_is_clamped_and_cannot_win_forever():
    d = make()
    d, _ = ap(d, up({"pos": 2}, {"pos": 1}, hlc=h(T + 2 * DAY)), server_ms=T + 1000)
    d, r = ap(d, up({"pos": 7}, {"pos": 1}, hlc=h(T + 5000, "web")), server_ms=T + 5000)
    assert r.status == "applied" and d.fields["pos"] == 7


def test_value_equal_to_base_is_no_change_and_does_not_revert_others():
    d = make()
    d, _ = ap(d, up({"pos": 2}, {"pos": 1}, hlc=h(T + 5, "web")))
    d2, r = ap(d, up({"pos": 1}, {"pos": 1}, hlc=h(T + 99)))
    assert r.fields["pos"] == "noop" and d2 is d


def test_identical_concurrent_edit_is_noop():
    d = make()
    d, _ = ap(d, up({"text": A}, {"text": S0}, hlc=h(T + 5, "web")))
    d2, r = ap(d, up({"text": A}, {"text": S0}, hlc=h(T + 9)))
    assert r.status == "applied" and r.fields["text"] == "noop" and d2 is d


def test_text_clean_merge():
    base = "We arived in Lisbon just after noon and walked to the big market."
    d = make(base)
    d, _ = ap(d, up({"text": base.replace("arived", "arrived")}, {"text": base}, hlc=h(T + 5, "web")))
    d, r = ap(d, up({"text": base.replace("big market", "fish market")}, {"text": base}, hlc=h(T + 1)))
    assert r.status == "merged" and d.conflicts == []
    assert d.fields["text"] == "We arrived in Lisbon just after noon and walked to the fish market."
    assert d.meta["text"]["device"] == "phone" and d.meta["text"]["hlc"] > h(T + 5, "web")


@pytest.mark.parametrize("phone_ms,text,alt,alt_dev", [(T + 9, C, A, "web"), (T + 1, A, C, "phone")])
def test_text_conflict_higher_hlc_is_text_other_is_alternative(phone_ms, text, alt, alt_dev):
    d = make()
    d, _ = ap(d, up({"text": A}, {"text": S0}, hlc=h(T + 5, "web")))
    d, r = ap(d, up({"text": C}, {"text": S0}, hlc=h(phone_ms)))
    assert r.status == "conflict" and d.fields["text"] == text
    [a] = d.conflicts
    assert (a["value"], a["device"], a["base"], a["field"]) == (alt, alt_dev, S0, "text")
    assert a["id"] == conflict_id("text", alt) and parse_hlc(a["hlc"]).device == alt_dev


def test_alternatives_dedupe_and_drop_when_equal_to_text():
    d = make()
    d, _ = ap(d, up({"text": A}, {"text": S0}, hlc=h(T + 50, "web")))
    for dev in ("phone", "tablet"):  # two devices typed the identical losing text
        d, r = ap(d, up({"text": C}, {"text": S0}, hlc=h(T + 1, dev)))
    assert [a["value"] for a in d.conflicts] == [C]
    d, _ = ap(d, up({"text": C}, {"text": A}, hlc=h(T + 60, "web")))  # someone types it as the text
    assert d.fields["text"] == C and d.conflicts == []


def test_device_editing_its_own_losing_text_replaces_its_alternative():
    d = make()
    d, _ = ap(d, up({"text": A}, {"text": S0}, hlc=h(T + 50, "web")))
    d, _ = ap(d, up({"text": C}, {"text": S0}, hlc=h(T + 1)))
    c2 = "We strolled to the market, slowly."
    d, r = ap(d, up({"text": c2}, {"text": C}, hlc=h(T + 2)))
    assert r.status == "conflict" and d.fields["text"] == A
    assert [(a["value"], a["base"]) for a in d.conflicts] == [(c2, S0)]


def test_cap_evicts_oldest_and_reports_it():
    schema = {B: CollectionSchema(B, frozenset({"text"}), frozenset({"text"}), True, True, max_conflicts=2)}
    d, _ = ap(None, up({"text": S0}, hlc=h(T, "web")), schema=schema)
    d, _ = ap(d, up({"text": A}, {"text": S0}, hlc=h(T + 500, "web")), schema=schema)
    ev = []
    for i, dev in enumerate(["p1", "p2", "p3"]):
        d, r = ap(d, up({"text": f"Version {i} of it."}, {"text": S0}, hlc=h(T + 10 + i, dev)), schema=schema)
        ev += r.evicted
    assert [a["value"] for a in d.conflicts] == ["Version 1 of it.", "Version 2 of it."]
    assert [a["value"] for a in ev] == ["Version 0 of it."]


# ---------------------------------------------------------------- resolve
def conflicted():
    d = make()
    d, _ = ap(d, up({"text": A}, {"text": S0}, hlc=h(T + 50, "web")))
    d, _ = ap(d, up({"text": C}, {"text": S0}, hlc=h(T + 1)))
    return d, d.conflicts[0]["id"]  # text A, alternative C


def test_dismiss_is_idempotent_and_touches_nothing_else():
    d, cid = conflicted()
    d2, r = ap(d, up({}, resolve=[cid], hlc=h(T + 60, "web")))
    assert r.status == "applied" and d2.conflicts == [] and d2.fields == d.fields
    d3, r = ap(d2, up({}, resolve=[cid], hlc=h(T + 61, "tablet")))  # second device dismisses too
    assert d3 is d2 and r.status == "applied"


def test_use_this_makes_alternative_the_text():
    d, cid = conflicted()
    d, r = ap(d, up({"text": C}, {"text": A}, resolve=[cid], hlc=h(T + 60, "web")))
    assert r.status == "applied" and d.fields["text"] == C and d.conflicts == []


def test_dismiss_does_not_race_a_third_edit():
    d, cid = conflicted()
    third = "We cycled to the market."
    d, _ = ap(d, up({"text": third}, {"text": S0}, hlc=h(T + 2, "tablet")))  # new alternative arrives
    d, _ = ap(d, up({}, resolve=[cid], hlc=h(T + 60, "web")))                # dismiss only what was seen
    assert [a["value"] for a in d.conflicts] == [third]


@pytest.mark.parametrize("use_ms,text,alts", [(T + 55, "We cycled to the market.", [C]),
                                              (T + 99, C, ["We cycled to the market."])])
def test_use_this_racing_a_third_edit_keeps_both(use_ms, text, alts):
    d, cid = conflicted()
    d, _ = ap(d, up({"text": "We cycled to the market."}, {"text": A}, hlc=h(T + 70, "tablet")))
    d, r = ap(d, up({"text": C}, {"text": A}, resolve=[cid], hlc=h(use_ms, "web")))
    assert r.status == "conflict" and d.fields["text"] == text
    assert [a["value"] for a in d.conflicts] == alts


def test_F1_use_this_on_own_alternative_with_value_equal_base_is_not_a_dismiss():
    d, cid = conflicted()  # phone's C lost; phone's next op has base C (its own in-flight text)
    d, r = ap(d, up({"text": C}, {"text": C}, resolve=[cid], hlc=h(T + 3)))
    assert d.fields["text"] == A and [a["value"] for a in d.conflicts] == [C] and r.status == "conflict"


def test_F2_use_this_then_more_typing_coalesced_keeps_the_branch():
    d, cid = conflicted()
    more = C + " It was closed."
    d, r = ap(d, up({"text": more}, {"text": C}, resolve=[cid], hlc=h(T + 3)))
    assert r.status == "merged" and d.fields["text"] == A + " It was closed."
    assert [a["value"] for a in d.conflicts] == [more]


# ---------------------------------------------------------------- deletes
SEEN = {"text": S0, "pos": 1}


def test_delete_tombstones_and_keeps_fields():
    d, r = ap(make(), rm(SEEN, hlc=h(T + 5)))
    assert r.status == "applied" and d.deleted and d.fields["text"] == S0
    assert d.meta[DELETED]["device"] == "phone"
    d2, r = ap(d, rm(SEEN, hlc=h(T + 6)))
    assert d2 is d and r.status == "applied"
    assert ap(None, rm())[0] is None


def test_delete_vs_concurrent_text_edit_edit_wins_in_both_arrival_orders_whatever_the_clocks():
    for edit_ms in (T + 1, T + 99):
        edit = up({"text": A}, {"text": S0}, hlc=h(edit_ms, "web"))
        dele = rm(SEEN, hlc=h(T + 50))
        d1, r1 = ap(ap(make(), edit)[0], dele)
        assert r1.status == "conflict" and r1.detail.startswith("edit wins")
        d2, r2 = ap(ap(make(), dele)[0], edit)
        assert r2.status == "applied"
        for d in (d1, d2):
            assert not d.deleted and d.fields["text"] == A


def test_delete_vs_concurrent_scalar_edit_is_lww_in_both_orders():
    for edit_ms, survives in ((T + 1, False), (T + 99, True)):
        edit = up({"pos": 4}, {"pos": 1}, hlc=h(edit_ms, "web"))
        dele = rm(SEEN, hlc=h(T + 50))
        d1, _ = ap(ap(make(), edit)[0], dele)
        d2, r2 = ap(ap(make(), dele)[0], edit)
        assert d1.deleted == d2.deleted == (not survives)
        assert r2.status == ("applied" if survives else "conflict")


def test_delete_refused_when_an_alternative_was_not_seen():
    d, cid = conflicted()
    seen = {"text": A, "pos": 1}
    d1, r = ap(d, rm(seen, hlc=h(T + 99, "web")))
    assert r.status == "conflict" and not d1.deleted
    d2, r = ap(d, rm(seen, hlc=h(T + 99, "web"), resolve=[cid]))
    assert r.status == "applied" and d2.deleted


def test_restore_is_an_empty_upsert_and_beats_stale_deletes():
    d, _ = ap(make(), rm(SEEN, hlc=h(T + 5)))
    d, r = ap(d, up({}, hlc=h(T + 9, "web")))
    assert r.status == "applied" and not d.deleted and d.fields == SEEN
    d2, r = ap(d, rm(SEEN, hlc=h(T + 6, "tablet")))  # issued before the restore, arrives after
    assert r.status == "conflict" and r.detail == "restored later" and not d2.deleted
    d3, r = ap(d, rm(SEEN, hlc=h(T + 20, "tablet")))
    assert d3.deleted


def test_same_id_created_twice_merges_fields():
    d = make("Sunset from the pier.", pos=3, dev="web", ms=T + 5)
    d, r = ap(d, up({"text": "Sunset from the pier.", "pos": 4}, hlc=h(T + 9)))
    assert d.fields == {"text": "Sunset from the pier.", "pos": 4} and d.conflicts == []
    d, r = ap(d, up({"text": "Dinner on the pier."}, hlc=h(T + 1, "tablet")))
    assert r.status == "conflict" and d.fields["text"] == "Sunset from the pier."
    assert [a["value"] for a in d.conflicts] == ["Dinner on the pier."]


# ---------------------------------------------------------------- validation
@pytest.mark.parametrize("m", [
    up({"text": "x"}, coll="nope"),
    up({"evidence_ids": [1]}),                 # read-only field
    up({"text": 5}),                           # merge field must be a string
    up({"payload": {}}, coll="evidence"),      # read-only collection
    up({"hidden": True}, coll="assets"),       # assets cannot be created by clients
    Mutation("o", B, "b1", "t1", "upsert", "garbage", {"text": "x"}),
    Mutation("o", B, "b1", "t1", "frobnicate", h(T), {}),
])
def test_rejected(m):
    d, r = ap(None, m)
    assert d is None and r.status == "rejected" and not r.changed


def test_rejected_wrong_trip_and_undeletable_collection():
    d = make()
    m = Mutation("o", B, "b1", "other-trip", "upsert", h(T + 1), {"pos": 2})
    assert ap(d, m) [1].status == "rejected"
    asset, _ = ap(None, Mutation("p", "assets", "a1", "t1", "upsert", h(T, PIPELINE), {"hidden": False}))
    assert ap(asset, Mutation("o", "assets", "a1", "t1", "delete", h(T + 1)))[1].status == "rejected"
    asset, r = ap(asset, Mutation("o", "assets", "a1", "t1", "upsert", h(T + 1), {"caption": "Pier"}))
    assert r.status == "applied" and asset.meta["caption"]["device"] == "phone"


# ---------------------------------------------------------------- pipeline (D6)
def pipe(fields=None, kind="upsert", ms=T, id="g1"):
    return Mutation(f"op{next(n)}", B, id, "t1", kind, h(ms, PIPELINE), fields or {})


def gen(text="Generated one."):
    return ap(None, pipe({"text": text, "pos": 1, "evidence_ids": ["e1"]}))[0]


def test_pipeline_replaces_untouched_block_and_may_write_readonly_fields():
    d, r = ap(gen(), pipe({"text": "Generated two.", "evidence_ids": ["e2"]}, ms=T + 5))
    assert r.status == "applied" and d.fields["text"] == "Generated two." and d.fields["evidence_ids"] == ["e2"]
    d, r = ap(d, pipe(kind="delete", ms=T + 6))
    assert d.deleted
    d, r = ap(d, pipe({"text": "Generated three."}, ms=T + 7))  # regenerating its own block
    assert not d.deleted and d.fields["text"] == "Generated three."


def test_pipeline_never_overwrites_or_deletes_what_a_user_touched():
    d, _ = ap(gen(), up({"text": "My own words."}, {"text": "Generated one."}, id="g1", hlc=h(T + 1)))
    d2, r = ap(d, pipe({"text": "Generated two.", "evidence_ids": ["e2"]}, ms=T + DAY))
    assert r.status == "conflict" and r.fields == {"text": "kept", "evidence_ids": "applied"}
    assert d2.fields["text"] == "My own words." and d2.fields["evidence_ids"] == ["e2"]
    d3, r = ap(d2, pipe(kind="delete", ms=T + DAY))
    assert r.status == "conflict" and not d3.deleted


def test_user_edit_always_beats_concurrent_regeneration_and_generated_text_is_not_an_alternative():
    d, _ = ap(gen(), pipe({"text": "Generated two, quite different."}, ms=T + DAY))
    d, r = ap(d, up({"text": "Generated one, fixed."}, {"text": "Generated one."}, id="g1", hlc=h(T + 1)))
    assert r.status == "applied" and d.fields["text"] == "Generated one, fixed." and d.conflicts == []


def test_user_delete_sticks_and_user_edit_resurrects_pipeline_delete():
    d, _ = ap(gen(), rm({"text": "Generated one.", "pos": 1}, id="g1", hlc=h(T + 1)))
    d2, r = ap(d, pipe({"text": "Generated two."}, ms=T + DAY))
    assert d2.deleted and r.status == "conflict"
    d, _ = ap(gen(), pipe(kind="delete", ms=T + DAY))
    d, r = ap(d, up({"pos": 7}, {"pos": 1}, id="g1", hlc=h(T + 1)))  # older scalar edit still wins
    assert not d.deleted and d.fields["pos"] == 7
    d, _ = ap(gen(), pipe({"text": "Generated two."}, ms=T + 5))    # user deletes a block that was
    d, r = ap(d, rm({"text": "Generated one.", "pos": 1}, id="g1", hlc=h(T + 9)))  # regenerated meanwhile
    assert d.deleted
