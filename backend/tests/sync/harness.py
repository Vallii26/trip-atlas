"""Test harness: a world with one server, a fake real-time clock and fault-injecting transports."""

from __future__ import annotations

import collections
from typing import Callable

from atlas.sync.merge import DEFAULT_SCHEMA
from atlas.sync.server import InMemoryStore, SyncServer
from atlas.sync.sim import Client, ConnectionLost, DirectTransport

STATS: collections.Counter = collections.Counter()
T0 = 1_780_000_000_000  # some real "now" in ms
DAY = 86_400_000
TRIP = "trip-1"
USER = "alice"


class FlakyTransport(DirectTransport):
    """Faults are armed for the next push only."""

    def __init__(self, server, user_id, now):
        super().__init__(server, user_id, now)
        self.drop_after: int | None = None       # server applies the first k ops, response is lost
        self.duplicate = False                    # request delivered twice (retry at HTTP level)
        self.during_push: Callable[[], None] | None = None  # user keeps typing while in flight
        self.fail_pull = False
        self.history: list[tuple[str, list]] = []  # (device, mutations the server really received)
        self.cursors: list[int] = []

    def push(self, device_id, mutations):
        drop, dup, hook = self.drop_after, self.duplicate, self.during_push
        self.drop_after, self.duplicate, self.during_push = None, False, None
        if drop is not None:
            delivered = list(mutations[:drop])
            if delivered:
                self.history.append((device_id, delivered))
                super().push(device_id, delivered)
            raise ConnectionLost()
        self.history.append((device_id, list(mutations)))
        resp = super().push(device_id, mutations)
        if dup:
            resp = super().push(device_id, mutations)
        if hook:
            hook()
        return resp

    def pull(self, cursor, limit):
        if self.fail_pull:
            self.fail_pull = False
            raise ConnectionLost()
        resp = super().pull(cursor, limit)
        assert resp.cursor >= cursor, "cursor went backwards"
        assert len(resp.docs) <= limit
        self.cursors.append(resp.cursor)
        return resp


class RecordingServer(SyncServer):
    """Remembers alternatives evicted by the cap (the one sanctioned way text can vanish)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.evicted_log: list[dict] = []

    def _apply(self, *a, **kw):
        r = super()._apply(*a, **kw)
        self.evicted_log.extend(r.evicted)
        STATS[r.status] += 1
        if r.detail:
            STATS["detail: " + r.detail.split(":")[0]] += 1
        for o in r.fields.values():
            STATS["field " + o] += 1
        return r


class World:
    def __init__(self, schema=DEFAULT_SCHEMA):
        self.now = T0
        self.store = InMemoryStore()
        self.server = RecordingServer(self.store, schema)
        self.schema = schema
        self.clients: dict[str, Client] = {}

    def clock(self) -> int:
        return self.now

    def tick(self, ms: int = 1000) -> None:
        self.now += ms

    def add_client(self, device: str, skew_ms: int = 0, user: str = USER, **kw) -> Client:
        t = FlakyTransport(self.server, user, self.clock)
        c = Client(device, t, lambda: self.now + skew_ms, schema=self.schema, **kw)
        self.clients[device] = c
        return c

    def server_docs(self, user: str = USER) -> dict:
        return {k: d.to_dict() for k, d in self.store.docs.items() if self.store.owners[k] == user}

    def quiesce(self) -> None:
        for c in self.clients.values():
            c.online = True
        for _ in range(2):
            for c in self.clients.values():
                self.tick(10)
                assert c.sync()

    def assert_converged(self, user: str = USER) -> None:
        want = self.server_docs(user)
        for c in self.clients.values():
            assert not c.outbox, f"{c.device_id} outbox not empty"
            got = {k: d.to_dict() for k, d in c.synced.items()}
            assert got == want, f"{c.device_id} diverged from server"
            for coll, i in c.keys():
                assert c.view(coll, i).to_dict() == want[(coll, i)]


def block(c: Client, id: str):
    return c.view("diary_blocks", id)


def text(c: Client, id: str) -> str:
    return block(c, id).fields["text"]


def alts(c: Client, id: str) -> list[str]:
    return [a["value"] for a in block(c, id).conflicts]
