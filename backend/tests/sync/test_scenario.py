"""The product requirement, end to end:

"I start a trip on my phone, edit it on the web, go offline on the phone, keep editing, and when
I reconnect nothing is lost and both show the same thing."
"""

from .harness import TRIP, World, alts, block, text

B = "diary_blocks"


def test_phone_starts_trip_web_edits_phone_edits_offline_reconnect_loses_nothing_and_converges():
    w = World()
    phone, web = w.add_client("phone"), w.add_client("web")

    # Phone starts a trip; the pipeline writes three days of diary.
    phone.mutate("trips", TRIP, TRIP, {"title": "Lisbon in May"})
    phone.sync()
    days = {
        "day1": "We landed in Lisbon before noon and dropped our bags at the flat in Alfama.",
        "day2": "The tram took us up to the castle. We stayed until the light went gold.",
        "day3": "A slow morning, then the train out to Sintra.",
    }
    from atlas.sync.hlc import format_hlc
    from atlas.sync.merge import Mutation
    w.server.apply_pipeline(TRIP, [
        Mutation(f"gen-{k}", B, k, TRIP, "upsert", format_hlc(w.now, 0, "pipeline"), {"text": v, "pos": i, "day": i + 1})
        for i, (k, v) in enumerate(days.items())], w.now)
    w.quiesce()

    # Phone edits day 1 (online).
    w.tick()
    day1 = days["day1"].replace("before noon", "just before noon, tired and happy,")
    phone.mutate(B, "day1", TRIP, {"text": day1})
    phone.sync()

    # Phone goes offline.  Web edits day 2 online: fixes the first sentence.
    phone.online = False
    w.tick()
    web.sync()
    web_day2 = "The 28 tram took us up to the castle. We stayed until the light went gold."
    web.mutate(B, "day2", TRIP, {"text": web_day2})
    web.sync()

    # Phone, offline: edits day 3, adds a block of its own ...
    w.tick()
    day3 = days["day3"] + " The palace was wrapped in fog."
    phone.mutate(B, "day3", TRIP, {"text": day3})
    phone.mutate(B, "phone-note", TRIP, {"text": "Best pastel de nata so far 🥮.", "pos": 9})

    # ... and both edit THE SAME SENTENCE of day 2 (the second one).  Phone first, web later.
    w.tick()
    phone_day2 = "The tram took us up to the castle. We stayed until sunset."
    phone.mutate(B, "day2", TRIP, {"text": phone_day2})
    w.tick()
    web_day2b = "The 28 tram took us up to the castle. We stayed until the light went gold and the swifts came out."
    web.mutate(B, "day2", TRIP, {"text": web_day2b})
    web.sync()
    assert text(phone, "day2") == phone_day2 and len(phone.outbox) == 3  # offline: outbox grows

    # Phone reconnects.
    w.tick()
    phone.online = True
    assert phone.sync() and web.sync()
    w.assert_converged()

    for c in (phone, web):
        assert text(c, "day1") == day1                       # day 1 edit present
        assert text(c, "day3") == day3                       # day 3 edit present
        assert text(c, "phone-note").startswith("Best pastel")
        assert text(c, "day2") == web_day2b                  # same sentence: the later edit is the text
        assert alts(c, "day2") == [phone_day2]               # the other is preserved, attributed
        assert block(c, "day2").conflicts[0]["device"] == "phone"
        assert alts(c, "day1") == alts(c, "day3") == []

    # On the web the user picks the alternative ("Use this").
    w.tick()
    web.resolve(B, "day2", block(web, "day2").conflicts[0]["id"], use=True)
    assert text(web, "day2") == phone_day2 and alts(web, "day2") == []   # optimistic
    assert web.sync() and phone.sync()
    w.assert_converged()
    for c in (phone, web):
        assert text(c, "day2") == phone_day2 and block(c, "day2").conflicts == []

    # And the pipeline regenerating the trip afterwards touches none of the edited blocks.
    w.server.apply_pipeline(TRIP, [
        Mutation(f"regen-{k}", B, k, TRIP, "upsert", format_hlc(w.now + 5, 0, "pipeline"), {"text": "Regenerated."})
        for k in days], w.now + 5)
    w.quiesce()
    assert [text(web, k) for k in days] == [day1, phone_day2, day3]


def test_different_sentences_of_day_two_merge_without_a_conflict():
    w = World()
    phone, web = w.add_client("phone"), w.add_client("web")
    phone.mutate("trips", TRIP, TRIP, {"title": "Lisbon"})
    phone.mutate(B, "day2", TRIP, {"text": "The tram took us up to the castle. We stayed until the light went gold."})
    w.quiesce()
    phone.online = False
    phone.mutate(B, "day2", TRIP, {"text": "The tram took us up to the castle. We stayed until sunset."})
    web.mutate(B, "day2", TRIP, {"text": "The 28 tram took us up to the castle. We stayed until the light went gold."})
    w.quiesce()
    w.assert_converged()
    assert text(phone, "day2") == "The 28 tram took us up to the castle. We stayed until sunset."
    assert alts(phone, "day2") == []
