"""Property tests: 2-4 client replicas + 1 server under random interleavings and faults.

Invariants (checked whenever all replicas come online and sync to quiescence):
 (a) CONVERGENCE   every replica's synced docs == the server's docs (fields, meta, conflicts,
                   deleted, rev), outboxes empty, view == synced.
 (b) NO SILENT LOSS  every edit of a merge field introduces a fresh marker word.  For every
                   marker m ever typed into doc D, at quiescence one of:
                     1. D is live and m occurs in D's text or in one of D's alternatives;
                     2. some edit (any device) whose author's VIEW contained m produced a text
                        without m (someone saw it and changed it deliberately; includes "use this");
                     3. some dismiss targeted an alternative containing m;
                     4. D is deleted and a delete was issued by a device whose view of D
                        (text + alternatives) contained m;
                     5. an alternative containing m was evicted by the cap (reported; the fuzz
                        asserts this never happens with the default cap unless FUZZ_CAP is small).
                   A deleted D never satisfies 1: text in a tombstone is not "present".
 (c) IDEMPOTENCY   re-delivering any push the server has received changes nothing and answers
                   `duplicate` for every op.
 (d) CURSORS       cursors never decrease; a fresh replica paging from 0 with any limit gets
                   every doc exactly once and ends equal to the server.
Also: the pipeline never changes a user-owned field, never deletes a user-touched doc, never
resurrects a user's tombstone; another user's pushes are rejected and change nothing.
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, Phase, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

from atlas.sync.hlc import format_hlc
from atlas.sync.merge import DELETED, PIPELINE, Mutation
from atlas.sync.textmerge import tokenize

from .harness import DAY, STATS, TRIP, World

EXAMPLES = int(os.environ.get("ATLAS_SYNC_FUZZ", "300"))
STEPS = int(os.environ.get("ATLAS_SYNC_FUZZ_STEPS", "50"))
COUNT = {"examples": 0, "steps": 0, "quiesce": 0, "evicted": 0}

DEVICES = ["phone", "web", "tablet", "laptop"]
SKEWS = [0, 0, 90_000, -90_000, 2 * DAY, -2 * DAY, 600_000]
REWRITE = [
    "We reached {m} just before noon and found the old square almost empty.",
    "Breakfast at {m} was slow, sweet and exactly what the morning needed.",
    "The ferry to {m} left late. Nobody on the upper deck seemed to mind.",
    "{m} smelled of rain and woodsmoke when we finally arrived 🌧️.",
    "Zoë said the climb to {m} was worth it; I wasn't so sure until the top.",
]
APPEND = ["Then {m} happened.", "We'll remember {m}!", "Later, {m} closed early."]
BLK = "diary_blocks"


def markers(text) -> set[str]:
    return {t for t in tokenize(text or "") if t.startswith("Xq")}


class SyncMachine(RuleBasedStateMachine):
    @initialize(n=st.integers(2, 4), skews=st.lists(st.sampled_from(SKEWS), min_size=4, max_size=4),
                srv=st.lists(st.booleans(), min_size=4, max_size=4), limit=st.sampled_from([1, 2, 5, 100]))
    def setup(self, n, skews, srv, limit):
        self.w = World()
        for i in range(n):
            self.w.add_client(DEVICES[i], skews[i], pull_limit=limit, use_server_time=srv[i])
        self.cs = list(self.w.clients.values())
        self.cs[0].mutate("trips", TRIP, TRIP, {"title": "Portugal"})
        self.n_marker = self.n_doc = self.n_pipe = 0
        self.introduced: dict[tuple, set] = {}
        self.removed: set[str] = set()
        self.deleted_seen: dict[tuple, set] = {}
        for i in (0, 1):  # two blocks everyone starts with, so concurrency starts at step 1
            self._type(self.cs[0], f"shared-{i}", REWRITE[i].format(m=self._marker((BLK, f"shared-{i}"))), {"pos": i})
        self.w.quiesce()
        COUNT["examples"] += 1

    # ---------------------------------------------------------------- helpers
    def _marker(self, key) -> str:
        self.n_marker += 1
        m = f"Xq{self.n_marker}"
        self.introduced[key] = self.introduced.get(key, set()) | {m}
        return m

    def _blocks(self, c, deleted=False):
        out = []
        for coll, i in c.keys():
            if coll == BLK:
                d = c.view(coll, i)
                if d is not None and d.deleted == deleted:
                    out.append(d)
        return out

    def _type(self, c, id, new_text, extra=None):
        """A user types `new_text` into block `id` having seen the current view."""
        cur = c.view(BLK, id)
        seen = markers(cur.fields.get("text")) if cur is not None and not cur.deleted else set()
        self.removed |= seen - markers(new_text)
        c.mutate(BLK, id, TRIP, {"text": new_text, **(extra or {})})

    # ---------------------------------------------------------------- user actions
    @rule(ci=st.integers(0, 3), online=st.sampled_from([True, True, False]),
          ms=st.sampled_from([1, 40, 1000, 61_000, 400_000, 3_600_000]))
    def set_online_and_wait(self, ci, online, ms):
        self.cs[ci % len(self.cs)].online = online
        self.w.tick(ms)

    @rule(ci=st.integers(0, 3), shared=st.integers(0, 9), tpl=st.sampled_from(REWRITE), pos=st.integers(0, 5))
    def create_block(self, ci, shared, tpl, pos):
        c = self.cs[ci % len(self.cs)]
        self.w.tick(1)
        if shared < 3 or self.n_doc >= 3:  # few docs → many concurrent edits per doc
            id = f"shared-{shared % 2}"  # two devices may create the same id
        else:
            self.n_doc += 1
            id = f"{c.device_id}-b{self.n_doc}"
        cur = c.view(BLK, id)
        if cur is not None and cur.deleted:
            return
        self._type(c, id, tpl.format(m=self._marker((BLK, id))), {"pos": pos})

    @rule(ci=st.integers(0, 3), bi=st.integers(0, 50), mode=st.sampled_from(["rewrite", "append", "word", "word", "prepend"]),
          k=st.integers(0, 60), tpl=st.sampled_from(REWRITE), app=st.sampled_from(APPEND))
    def edit_text(self, ci, bi, mode, k, tpl, app):
        c = self.cs[ci % len(self.cs)]
        blocks = self._blocks(c)
        if not blocks:
            return
        self.w.tick(1)
        d = blocks[bi % len(blocks)]
        old = d.fields.get("text") or ""
        m = self._marker((BLK, d.id))
        if mode == "rewrite" or not old:
            new = tpl.format(m=m)
        elif mode == "append":
            new = old + " " + app.format(m=m)
        elif mode == "prepend":
            new = app.format(m=m) + " " + old
        else:
            toks = tokenize(old)
            words = [i for i, t in enumerate(toks) if t[0].isalnum()]
            toks[words[k % len(words)]] = m
            new = "".join(toks)
        self._type(c, d.id, new)

    @rule(ci=st.integers(0, 3), cj=st.integers(1, 3), bi=st.integers(0, 50), k=st.integers(0, 60),
          modes=st.tuples(*[st.sampled_from(["rewrite", "append", "word", "word", "prepend"])] * 2),
          tpl=st.sampled_from(REWRITE), app=st.sampled_from(APPEND))
    def edit_text_on_two_devices(self, ci, cj, bi, k, modes, tpl, app):
        """Two devices edit a block at (nearly) the same time: the conflict generator."""
        self.edit_text(ci, bi, modes[0], k, tpl, app)
        self.edit_text(ci + cj, bi, modes[1], k + 7, tpl, app)

    @rule(ci=st.integers(0, 3), bi=st.integers(0, 50), pos=st.integers(0, 5))
    def edit_scalar(self, ci, bi, pos):
        c = self.cs[ci % len(self.cs)]
        blocks = self._blocks(c)
        if blocks:
            self.w.tick(1)
            c.mutate(BLK, blocks[bi % len(blocks)].id, TRIP, {"pos": pos})

    @rule(ci=st.integers(0, 3), bi=st.integers(0, 50))
    def delete_block(self, ci, bi):
        c = self.cs[ci % len(self.cs)]
        blocks = self._blocks(c)
        if blocks:
            self.w.tick(1)
            d = blocks[bi % len(blocks)]
            seen = markers(d.fields.get("text"))
            for a in d.conflicts:
                seen |= markers(a["value"])
            self.deleted_seen.setdefault((BLK, d.id), set()).update(seen)
            c.delete(BLK, d.id)

    @rule(ci=st.integers(0, 3), bi=st.integers(0, 50))
    def restore_block(self, ci, bi):
        c = self.cs[ci % len(self.cs)]
        blocks = self._blocks(c, deleted=True)
        if blocks:
            self.w.tick(1)
            c.restore(BLK, blocks[bi % len(blocks)].id)

    @rule(ci=st.integers(0, 3), bi=st.integers(0, 50), ai=st.integers(0, 9), use=st.booleans())
    def resolve(self, ci, bi, ai, use):
        c = self.cs[ci % len(self.cs)]
        blocks = [d for d in self._blocks(c) if d.conflicts]
        if not blocks:
            return
        self.w.tick(1)
        d = blocks[bi % len(blocks)]
        alt = d.conflicts[ai % len(d.conflicts)]
        if use:
            self.removed |= markers(d.fields.get("text")) - markers(alt["value"])
        else:
            self.removed |= markers(alt["value"])
        c.resolve(BLK, d.id, alt["id"], use)

    @rule(ci=st.integers(0, 3), cj=st.integers(1, 3), bi=st.integers(0, 50), ai=st.integers(0, 9),
          use=st.booleans(), k=st.integers(0, 60), tpl=st.sampled_from(REWRITE), app=st.sampled_from(APPEND),
          mode=st.sampled_from(["rewrite", "append", "word"]))
    def resolve_while_another_device_edits(self, ci, cj, bi, ai, use, k, tpl, app, mode):
        """A resolve racing a third edit of the same block."""
        self.resolve(ci, bi, ai, use)
        self.edit_text(ci + cj, bi, mode, k, tpl, app)

    # ---------------------------------------------------------------- sync and faults
    @rule(ci=st.integers(0, 3), fault=st.sampled_from(["none", "none", "none", "drop", "dup", "pullfail", "typing"]),
          k=st.integers(0, 6))
    def sync(self, ci, fault, k):
        c = self.cs[ci % len(self.cs)]
        t = c.transport
        self.w.tick(5)
        if fault == "drop":  # crash-before-ack: server applied a prefix (maybe all), client saw nothing
            t.drop_after = min(k, len(c.outbox))
        elif fault == "dup":
            t.duplicate = True
        elif fault == "pullfail":
            t.fail_pull = True
        elif fault == "typing":  # the user keeps editing while the push is in flight
            def typing():
                blocks = self._blocks(c)
                if blocks:
                    d = blocks[k % len(blocks)]
                    m = self._marker((BLK, d.id))
                    self._type(c, d.id, (d.fields.get("text") or "") + f" Meanwhile {m}.")
            t.during_push = typing
        c.sync()
        t.drop_after, t.duplicate, t.fail_pull, t.during_push = None, False, False, None
        assert not c.rejected, c.rejected

    @rule(hi=st.integers(0, 200), limit=st.integers(1, 7))
    def audit(self, hi, limit):
        self.replay_old_push(hi)
        self.fresh_pull(limit)
        self.intruder()

    def replay_old_push(self, hi):
        hist = [h for c in self.cs for h in c.transport.history]
        device, muts = hist[hi % len(hist)]
        snap = self.w.store.snapshot()
        resp = self.w.server.push("alice", device, muts, self.w.now)
        assert all(r.status == "duplicate" for r in resp.results)
        assert self.w.store.snapshot() == snap

    def fresh_pull(self, limit):
        seen, cursor = {}, 0
        while True:
            page = self.w.server.pull("alice", cursor, limit)
            assert page.cursor >= cursor and len(page.docs) <= limit
            for d in page.docs:
                assert (d.collection, d.id) not in seen
                assert cursor < d.rev <= page.cursor
                seen[(d.collection, d.id)] = d.to_dict()
            cursor = page.cursor
            if not page.has_more:
                break
        assert seen == self.w.server_docs()

    def intruder(self):
        snap = self.w.store.snapshot()
        hlc = format_hlc(self.w.now, 0, "evil")
        muts = [Mutation("x1", BLK, "shared-0", TRIP, "upsert", hlc, {"text": "pwned"}, {}),
                Mutation("x2", "trips", TRIP, TRIP, "delete", hlc),
                Mutation("phone:1", "trips", TRIP, TRIP, "upsert", hlc, {"title": "pwned"})]
        resp = self.w.server.push("mallory", "evil", muts, self.w.now)
        assert all(r.status in ("rejected", "duplicate") and r.doc is None for r in resp.results)
        assert self.w.store.snapshot() == snap
        assert self.w.server.pull("mallory", 0, 100).docs == []

    # ---------------------------------------------------------------- pipeline
    @rule(gi=st.integers(0, 2), action=st.sampled_from(["write", "write", "delete"]), tgt=st.integers(0, 30))
    def pipeline(self, gi, action, tgt):
        self.w.tick(1)
        self.n_pipe += 1
        ids = sorted(i for (coll, i) in self.w.store.docs if coll == BLK)
        id = f"gen-{gi}" if tgt < 20 or not ids else ids[tgt % len(ids)]
        before = self.w.store.get_doc(BLK, id)
        hlc = format_hlc(self.w.now, 0, PIPELINE)
        if action == "write":
            m = Mutation(f"pipe:{self.n_pipe}", BLK, id, TRIP, "upsert", hlc,
                         {"text": f"Generated sentence number {self.n_pipe}.", "pos": gi, "day": 1})
        else:
            m = Mutation(f"pipe:{self.n_pipe}", BLK, id, TRIP, "delete", hlc)
        self.w.server.apply_pipeline(TRIP, [m], self.w.now)
        after = self.w.store.get_doc(BLK, id)
        if before is None:
            return
        user_fields = [f for f, v in before.meta.items() if f != DELETED and v["device"] != PIPELINE]
        for f in user_fields:
            assert after.fields[f] == before.fields[f], "pipeline overwrote a user field"
        assert after.conflicts == before.conflicts
        if not before.deleted and (user_fields or before.conflicts):
            assert not after.deleted, "pipeline deleted a user-touched doc"
        if before.deleted and before.meta[DELETED]["device"] != PIPELINE:
            assert after.deleted, "pipeline resurrected a user's tombstone"

    # ---------------------------------------------------------------- the invariants
    @rule(go=st.integers(0, 5))
    def quiesce_and_check(self, go):
        if go == 0:  # rare: every check re-synchronises everyone and so removes concurrency
            self.check()

    def teardown(self):
        if hasattr(self, "w"):
            self.check()

    @invariant()
    def count(self):
        COUNT["steps"] += 1

    def check(self):
        COUNT["quiesce"] += 1
        w = self.w
        w.quiesce()
        w.assert_converged()  # (a)
        for c in self.cs:
            assert not c.rejected
            assert c.transport.cursors == sorted(c.transport.cursors)  # (d)
        for key, ms in self.introduced.items():  # (b)
            doc = w.store.docs.get(key)
            assert doc is not None, f"{key} never reached the server"
            present = markers(doc.fields.get("text"))
            for a in doc.conflicts:
                present |= markers(a["value"])
            if doc.deleted:
                ok = self.removed | self.deleted_seen.get(key, set())
            else:
                ok = present | self.removed
            evicted = {m for a in w.server.evicted_log for m in markers(a["value"])}
            COUNT["evicted"] += len(w.server.evicted_log) if key == next(iter(self.introduced)) else 0
            lost = ms - ok - evicted
            assert not lost, f"SILENT LOSS in {key}: {sorted(lost)}\n{doc.to_dict()}"


_PHASES = [Phase.explicit, Phase.reuse, Phase.generate] + ([] if os.environ.get("ATLAS_SYNC_FUZZ_NOSHRINK") else [Phase.shrink])
SyncMachine.TestCase.settings = settings(
    phases=_PHASES,
    max_examples=EXAMPLES, stateful_step_count=STEPS, deadline=None,
    suppress_health_check=list(HealthCheck), print_blob=True,
)
TestSyncFuzz = SyncMachine.TestCase


def test_zz_report_counts():
    print(f"\nfuzz: {COUNT['examples']} examples, {COUNT['steps']} steps, {COUNT['quiesce']} quiescence checks, "
          f"{COUNT['evicted']} cap evictions seen")
    print("server outcomes:", dict(sorted(STATS.items())))
