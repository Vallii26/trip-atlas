from atlas.sync.hlc import format_hlc
from atlas.sync.merge import PIPELINE, Mutation
from atlas.sync.server import InMemoryStore, SyncServer

T = 1_780_000_000_000
B = "diary_blocks"


def h(ms, dev="phone"):
    return format_hlc(ms, 0, dev)


def trip(op="t-op", id="t1", dev="phone"):
    return Mutation(op, "trips", id, id, "upsert", h(T, dev), {"title": "Portugal"})


def blk(op, id, text, base=None, ms=T, dev="phone", trip_id="t1"):
    return Mutation(op, B, id, trip_id, "upsert", h(ms, dev), {"text": text}, {"text": base} if base else {})


def server():
    s = SyncServer(InMemoryStore())
    r = s.push("alice", "phone", [trip(), blk("o1", "b1", "Day one.")], T)
    assert [x.status for x in r.results] == ["applied", "applied"]
    return s


def test_push_applies_in_order_sets_rev_and_returns_docs():
    s = server()
    assert s.store.get_doc("trips", "t1").rev == 1 and s.store.get_doc(B, "b1").rev == 2
    r = s.push("alice", "phone", [blk("o2", "b1", "Day one, edited.", "Day one.", T + 1)], T + 1)
    assert r.results[0].doc.rev == 3 and r.results[0].doc.fields["text"] == "Day one, edited."
    assert r.server_ms == T + 1


def test_replay_is_duplicate_with_current_doc_and_changes_nothing():
    s = server()
    s.push("alice", "web", [blk("w1", "b1", "Web text.", "Day one.", T + 5, "web")], T + 5)
    snap = s.store.snapshot()
    r = s.push("alice", "phone", [trip(), blk("o1", "b1", "Day one.")], T + 9)
    assert [(x.status, x.original_status) for x in r.results] == [("duplicate", "applied")] * 2
    assert r.results[1].doc.fields["text"] == "Web text."  # the CURRENT doc
    assert s.store.snapshot() == snap


def test_noop_mutation_does_not_bump_rev_or_log():
    s = server()
    n = len(s.store.log)
    r = s.push("alice", "web", [blk("w1", "b1", "Day one.", "Day one.", T + 5, "web")], T + 5)
    assert r.results[0].status == "applied" and len(s.store.log) == n and r.results[0].doc.rev == 2


def test_authorization():
    s = server()
    snap = s.store.snapshot()
    evil = [
        blk("e1", "b1", "pwned", dev="evil"),                          # someone else's doc
        blk("e2", "new", "pwned", dev="evil"),                         # new doc in someone else's trip
        Mutation("e3", "trips", "t1", "t1", "delete", h(T + 9, "evil")),
        trip("e4", "t1", "evil"),                                       # re-claim an existing trip
        blk("e5", "x", "orphan", dev="evil", trip_id="ghost"),         # trip that does not exist
        Mutation("e6", "trips", "t9", "t1", "upsert", h(T, "evil"), {"title": "x"}),  # id != trip_id
        blk("o1", "b1", "pwned", dev="evil"),                          # alice's op_id must not leak her doc
    ]
    r = s.push("mallory", "evil", evil, T + 9)
    assert all(x.status == "rejected" and x.doc is None for x in r.results)
    assert s.store.snapshot() == snap
    r = s.push("mallory", "evil", evil, T + 10)  # replays of rejected ops stay opaque
    assert all(x.status == "duplicate" and x.doc is None for x in r.results)
    assert s.pull("mallory", 0, 100).docs == []
    # mallory can have her own trip; same doc id as alice's is refused, not merged
    r = s.push("mallory", "evil", [trip("m1", "t2", "evil"), blk("m2", "b1", "mine", dev="evil", trip_id="t2"),
                                   blk("m3", "mb", "mine", dev="evil", trip_id="t2")], T + 11)
    assert [x.status for x in r.results] == ["applied", "rejected", "applied"]
    assert [d.id for d in s.pull("mallory", 0, 100).docs] == ["t2", "mb"]
    assert {d.id for d in s.pull("alice", 0, 100).docs} == {"t1", "b1"}


def test_device_must_match_and_pipeline_device_is_reserved():
    s = server()
    r = s.push("alice", "web", [blk("x1", "b1", "spoof", dev="phone")], T)
    assert r.results[0].status == "rejected"
    r = s.push("alice", PIPELINE, [blk("x2", "b1", "spoof", dev=PIPELINE)], T)
    assert r.results[0].status == "rejected"
    r = s.apply_pipeline("t1", [blk("x3", "b1", "spoof", dev="phone")], T)
    assert r.results[0].status == "rejected"
    r = s.apply_pipeline("t1", [Mutation("p1", "evidence", "e1", "t1", "upsert", h(T, PIPELINE), {"type": "place"})], T)
    assert r.results[0].status == "applied"
    assert "e1" in {d.id for d in s.pull("alice", 0, 100).docs}


def test_pull_each_doc_once_latest_state_monotonic_cursor_and_pagination():
    s = server()
    for i in range(25):
        s.push("alice", "phone", [blk(f"c{i}", f"d{i % 7}", f"Text {i}.", ms=T + i)], T + i)
    for limit in (1, 2, 3, 7, 100):
        seen, cursor, pages = {}, 0, 0
        while True:
            p = s.pull("alice", cursor, limit)
            assert p.cursor >= cursor and len(p.docs) <= limit
            assert [d.rev for d in p.docs] == sorted(d.rev for d in p.docs)
            for d in p.docs:
                assert d.id not in seen
                seen[d.id] = d
            cursor, pages = p.cursor, pages + 1
            if not p.has_more:
                break
        assert len(seen) == 9 and seen["d3"].fields["text"] == "Text 24."
        assert s.pull("alice", cursor, limit).docs == [] and s.pull("alice", cursor, limit).cursor == cursor


def test_doc_changed_between_pages_is_redelivered_not_skipped():
    s = server()
    for i in range(4):
        s.push("alice", "phone", [blk(f"c{i}", f"d{i}", f"Text {i}.")], T)
    p1 = s.pull("alice", 0, 3)
    assert [d.id for d in p1.docs] == ["t1", "b1", "d0"] and p1.has_more
    s.push("alice", "web", [blk("w", "b1", "Changed.", "Day one.", T + 5, "web")], T + 5)
    rest = s.pull("alice", p1.cursor, 100)
    assert [d.id for d in rest.docs] == ["d1", "d2", "d3", "b1"] and rest.docs[-1].fields["text"] == "Changed."
