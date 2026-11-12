"""The client model's subtle rules (R1-R8 in atlas/sync/sim.py), one test each."""

from .harness import DAY, TRIP, World, alts, block, text

B = "diary_blocks"
S0 = "We walked to the market."


def world(*skews, **kw):
    w = World()
    cs = [w.add_client(name, skew, **kw) for name, skew in zip(["phone", "web", "tablet"], skews or (0, 0))]
    cs[0].mutate("trips", TRIP, TRIP, {"title": "Portugal"})
    cs[0].mutate(B, "b1", TRIP, {"text": S0, "pos": 1})
    w.quiesce()
    return (w, *cs)


def test_optimistic_edit_is_visible_and_offline_just_grows_the_outbox():
    w, phone, web = world()
    phone.online = False
    phone.mutate(B, "b1", TRIP, {"text": "We ran to the market."})
    phone.mutate(B, "b2", TRIP, {"text": "New block.", "pos": 2})
    assert text(phone, "b1") == "We ran to the market." and block(phone, "b2").fields["pos"] == 2
    assert not phone.sync() and len(phone.outbox) == 2 and block(web, "b2") is None
    w.quiesce()
    w.assert_converged()
    assert text(web, "b1") == "We ran to the market."


def test_R2_coalescing_keeps_the_original_base_so_unseen_remote_edits_are_not_overwritten():
    w, phone, web = world()
    phone.online = False
    phone.mutate(B, "b1", TRIP, {"text": "We ran to the market."})
    web.mutate(B, "b1", TRIP, {"text": "We walked to the market. It was closed."})
    web.sync()
    phone.online = True
    phone.transport.drop_after = 0   # nothing reaches the server, but the pull below does
    phone.sync()
    phone.outbox[0].sent = False     # (pretend the push was never attempted)
    phone.transport.fail_pull = False
    w.server  # phone now pulls web's edit while its own edit is still pending
    page = phone.transport.pull(phone.cursor, 100)
    for d in page.docs:
        phone._adopt(d)
    assert text(phone, "b1") == "We ran to the market."            # pull did not clobber the pending edit
    phone.mutate(B, "b1", TRIP, {"text": "We ran to the fish market."})  # user keeps typing
    assert len(phone.outbox) == 1 and phone.outbox[0].base == {"text": S0}   # ORIGINAL base
    w.quiesce()
    w.assert_converged()
    assert text(web, "b1") == "We ran to the fish market. It was closed."   # both edits survive


def test_R3_edit_after_a_lost_ack_is_a_new_op_and_is_not_swallowed_as_duplicate():
    w, phone, web = world()
    phone.mutate(B, "b1", TRIP, {"text": "We ran to the market."})
    phone.transport.drop_after = 1          # server applied it; phone never saw the answer
    assert not phone.sync() and phone.outbox[0].sent
    phone.mutate(B, "b1", TRIP, {"text": "We ran to the market at dawn."})
    assert len(phone.outbox) == 2
    assert phone.outbox[1].base == {"text": "We ran to the market."}   # R1: what the user saw
    w.quiesce()
    w.assert_converged()
    assert text(web, "b1") == "We ran to the market at dawn." and alts(web, "b1") == []


def test_R4_partial_push_then_drop_replays_safely():
    w, phone, web = world()
    phone.online = False
    for i in range(4):
        phone.mutate(B, f"n{i}", TRIP, {"text": f"Block {i}.", "pos": i})
    phone.online = True
    phone.transport.drop_after = 2
    assert not phone.sync() and len(phone.outbox) == 4
    assert w.store.get_doc(B, "n1") is not None and w.store.get_doc(B, "n2") is None
    log = len(w.store.log)
    phone.transport.duplicate = True        # and the retry itself is delivered twice
    assert phone.sync() and not phone.outbox
    assert len(w.store.log) == log + 2      # only the two missing ops changed anything
    w.quiesce()
    w.assert_converged()


def test_edit_typed_while_the_push_is_in_flight_survives():
    w, phone, web = world()
    phone.mutate(B, "b1", TRIP, {"text": "We ran to the market."})
    phone.transport.during_push = lambda: phone.mutate(B, "b1", TRIP, {"text": "We ran to the market. Twice."})
    phone.sync()
    assert text(phone, "b1") == "We ran to the market. Twice." and len(phone.outbox) == 1
    w.quiesce()
    w.assert_converged()
    assert text(web, "b1") == "We ran to the market. Twice."


def test_R5_R6_own_push_does_not_make_the_client_skip_others_changes():
    w, phone, web = world()
    web.mutate(B, "w1", TRIP, {"text": "Web block.", "pos": 5})
    web.sync()                                   # logged before phone's push
    phone.mutate(B, "p1", TRIP, {"text": "Phone block.", "pos": 6})
    phone.sync()
    assert block(phone, "w1") is not None        # would be skipped if the cursor came from the push
    w.assert_converged() if not web.sync() else w.assert_converged()


def test_F1_use_this_on_own_losing_text_after_typing_more_in_flight():
    w, phone, web = world()
    phone.online = False
    phone.mutate(B, "b1", TRIP, {"text": "We ran to the market."})
    w.tick()
    web.mutate(B, "b1", TRIP, {"text": "We strolled to the market."})   # later → wins
    web.sync()
    phone.online = True
    phone.transport.during_push = lambda: phone.mutate(B, "b1", TRIP, {"text": "We ran to the market. Fast."})
    phone.sync()
    [alt] = block(phone, "b1").conflicts
    assert alt["value"] == "We ran to the market."
    phone.resolve(B, "b1", alt["id"], use=True)      # coalesces: value == base of the pending op
    assert text(phone, "b1") == "We ran to the market."
    w.quiesce()
    w.assert_converged()
    assert "We ran to the market." in [text(web, "b1"), *alts(web, "b1")]   # not silently dismissed


def test_delete_offline_vs_edit_elsewhere_edit_wins_and_delete_of_seen_state_sticks():
    w, phone, web = world()
    phone.online = False
    phone.delete(B, "b1")
    assert block(phone, "b1").deleted
    web.mutate(B, "b1", TRIP, {"text": "We ran to the market."})
    w.quiesce()
    w.assert_converged()
    assert not block(phone, "b1").deleted and text(phone, "b1") == "We ran to the market."
    phone.delete(B, "b1")
    w.quiesce()
    assert block(web, "b1").deleted
    web.restore(B, "b1")
    w.quiesce()
    w.assert_converged()
    assert not block(phone, "b1").deleted


def test_R8_slow_clock_device_edits_on_top_of_what_it_saw_and_wins():
    w, phone, web = world(-2 * DAY, 0, use_server_time=False)
    web.mutate(B, "b1", TRIP, {"pos": 2})
    w.quiesce()
    phone.mutate(B, "b1", TRIP, {"pos": 3, "text": "We ran to the market."})
    assert phone.outbox[0].hlc > web.synced[(B, "b1")].meta["pos"]["hlc"]   # observed → ahead
    w.quiesce()
    w.assert_converged()
    assert block(web, "b1").fields == {"pos": 3, "text": "We ran to the market."}


def test_slow_clock_device_loses_concurrent_scalar_race_but_never_text():
    w, phone, web = world(-2 * DAY, 0, use_server_time=False)
    phone.online = False
    web.mutate(B, "b1", TRIP, {"pos": 2, "text": "We strolled to the market."})
    web.sync()
    w.tick(3_600_000)     # an hour later, in real time, the phone edits offline
    phone.mutate(B, "b1", TRIP, {"pos": 9, "text": "We ran to the market."})
    w.quiesce()
    w.assert_converged()
    assert block(web, "b1").fields == {"pos": 2, "text": "We strolled to the market."}   # accepted weakness
    assert alts(web, "b1") == ["We ran to the market."]                                  # but text is kept


def test_fast_clock_device_does_not_win_forever():
    w, phone, web = world(2 * DAY, 0, use_server_time=False)
    phone.mutate(B, "b1", TRIP, {"pos": 5})
    w.quiesce()
    w.tick(600_000)
    phone.online = False
    phone.mutate(B, "b1", TRIP, {"pos": 6})   # stamped two days ahead, pushed last
    w.tick(1000)
    web.mutate(B, "b1", TRIP, {"pos": 7})
    w.quiesce()
    w.tick(600_000)
    web.mutate(B, "b1", TRIP, {"pos": 8})     # a genuinely later edit by web
    w.quiesce()
    w.assert_converged()
    assert block(phone, "b1").fields["pos"] == 8


def test_server_time_offset_corrects_a_wrong_wall_clock():
    w, phone, web = world(-2 * DAY, 0)   # use_server_time defaults to True
    phone.online = False
    web.mutate(B, "b1", TRIP, {"pos": 2})
    web.sync()
    w.tick(3_600_000)
    phone.mutate(B, "b1", TRIP, {"pos": 9})   # really later, and now stamped so
    w.quiesce()
    assert block(web, "b1").fields["pos"] == 9
