"""Reference CLIENT model — the executable spec the TypeScript ``SyncEngine`` is ported from.

State (all of it must be persisted atomically on mobile):
  synced   last server state of every doc this device has seen (tombstones included)
  outbox   ordered pending ops; each has a ``sent`` flag
  cursor   pull cursor
  hlc      this device's hybrid logical clock

What the UI shows is never stored: ``view()`` = synced doc + the outbox replayed on top.
Because of that, a pull can only ever touch ``synced`` and so cannot clobber a pending edit.

The subtle rules (each has a test in tests/sync/test_sim.py):

R1  base = the value the user was LOOKING AT when they edited (the view), which is the
    last-synced value overlaid with this device's earlier pending ops.
R2  Coalescing: a new edit folds into the last op for that doc only if that op is an upsert that
    has NEVER been sent.  The folded op keeps its ORIGINAL base.  If it took the freshly pulled
    value as base instead, the server would see "base == current" and overwrite another
    device's edit that this user never saw (the view was showing their own pending text).
R3  An op is frozen the moment a push containing it leaves (``sent = True``, set BEFORE the
    request).  If the response is lost we cannot know whether the server applied it, so it is
    resent byte-for-byte under the same ``op_id`` and the server answers ``duplicate``.  Folding a
    new edit into a sent op would make the server drop the new edit as a duplicate.
    Edits made after that go into a new op whose base is the sent op's value (R1).
R4  A push may succeed partially and then the connection drops: nothing is removed from the
    outbox without an explicit per-op result.  Replay is safe because of R3 + server op log.
R5  A server doc replaces the synced copy only if its ``rev`` is not older.
R6  Never take a cursor from a push response; pull from your own cursor.
R7  ``sync()`` must be single-flight in the TS engine (serialise concurrent calls).
R8  Observe the hlc of every doc received (keeps this clock ahead of everything seen), and use
    ``server_ms`` from responses to correct a wrong wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

from .hlc import HLC
from .merge import DEFAULT_SCHEMA, DELETED, REJECTED, CollectionSchema, Doc, Mutation, would_resurrect
from .server import OpResult, PullResponse, PushResponse, SyncServer

Key = tuple[str, str]


class ConnectionLost(Exception):
    """The request may or may not have reached the server; no response was received."""


class Transport(Protocol):
    def push(self, device_id: str, mutations: Sequence[Mutation]) -> PushResponse: ...
    def pull(self, cursor: int, limit: int) -> PullResponse: ...


class DirectTransport:
    """In-process transport for one user.  ``now`` is the SERVER's clock."""

    def __init__(self, server: SyncServer, user_id: str, now: Callable[[], int]) -> None:
        self.server, self.user_id, self.now = server, user_id, now

    def push(self, device_id, mutations):
        return self.server.push(self.user_id, device_id, mutations, self.now())

    def pull(self, cursor, limit):
        return self.server.pull(self.user_id, cursor, limit, self.now())


@dataclass
class PendingOp:
    op_id: str
    collection: str
    id: str
    trip_id: str
    kind: str
    hlc: str
    fields: dict[str, Any] = field(default_factory=dict)
    base: dict[str, Any] = field(default_factory=dict)
    resolve: list[str] = field(default_factory=list)
    sent: bool = False
    keep: bool = False  # create / restore: meaningful even with no fields

    def to_mutation(self) -> Mutation:
        return Mutation(self.op_id, self.collection, self.id, self.trip_id, self.kind, self.hlc,
                        dict(self.fields), dict(self.base), tuple(self.resolve))


class Client:
    def __init__(self, device_id: str, transport: Transport, wall_clock: Callable[[], int], *,
                 schema: Mapping[str, CollectionSchema] = DEFAULT_SCHEMA, pull_limit: int = 100,
                 use_server_time: bool = True) -> None:
        self.device_id = device_id
        self.transport = transport
        self.wall_clock = wall_clock
        self.schema = schema
        self.pull_limit = pull_limit
        self.use_server_time = use_server_time
        self.clock_offset = 0  # server_ms - wall_ms at the last response (R8)
        self.hlc = HLC(device_id)
        self.synced: dict[Key, Doc] = {}
        self.outbox: list[PendingOp] = []
        self.cursor = 0
        self.online = True
        self.rejected: list[OpResult] = []  # surfaced to the user; the op is dropped
        self._n = 0

    # ------------------------------------------------------------ reading

    def view(self, collection: str, id: str) -> Doc | None:
        """What the user sees: synced state with this device's pending ops replayed on top."""
        doc = self.synced.get((collection, id))
        doc = doc.copy() if doc is not None else None
        for op in self.outbox:
            if (op.collection, op.id) == (collection, id):
                doc = self._apply_local(doc, op)
        return doc

    def keys(self) -> list[Key]:
        return sorted(set(self.synced) | {(op.collection, op.id) for op in self.outbox})

    def _apply_local(self, doc: Doc | None, op: PendingOp) -> Doc | None:
        cs = self.schema[op.collection]
        if op.kind == "delete":
            if doc is not None:
                doc.deleted = True  # optimistic; the server may refuse (edit wins)
            return doc
        if doc is None:
            doc = Doc(op.id, op.collection, op.trip_id)
        elif doc.deleted:
            if DELETED in doc.meta and not would_resurrect(doc, op.to_mutation(), op.hlc, cs):
                return doc  # the server will drop this op too
            doc.deleted = False
        doc.conflicts = [a for a in doc.conflicts if a["id"] not in op.resolve]
        for f, v in op.fields.items():
            doc.fields[f] = v
            doc.conflicts = [a for a in doc.conflicts if not (a["field"] == f and a["value"] == v)]
        return doc

    # ------------------------------------------------------------ writing

    def _stamp(self) -> str:
        return self.hlc.now(self.wall_clock() + self.clock_offset)

    def _new_op(self, collection, id, trip_id, kind, **kw) -> PendingOp:
        self._n += 1
        op = PendingOp(f"{self.device_id}:{self._n}", collection, id, trip_id, kind, self._stamp(), **kw)
        self.outbox.append(op)
        return op

    def mutate(self, collection: str, id: str, trip_id: str, fields: Mapping[str, Any],
               resolve: Sequence[str] = (), restore: bool = False) -> str | None:
        """Create or edit.  Optimistic: visible immediately through ``view()``."""
        cur = self.view(collection, id)
        seen = cur.fields if cur is not None else {}
        changes = {f: v for f, v in fields.items() if seen.get(f) != v}
        creating = cur is None
        if not (changes or resolve or creating or restore):
            return None
        last = next((op for op in reversed(self.outbox) if (op.collection, op.id) == (collection, id)), None)
        if last is not None and not last.sent and last.kind == "upsert":  # R2
            for f, v in changes.items():
                if f not in last.fields:
                    last.base[f] = seen.get(f)  # first edit of this field: base is what was seen
                last.fields[f] = v              # later edits: ORIGINAL base stays
                # Do NOT drop a field that was typed back to its base: the base may be this
                # device's own in-flight text that lost on the server, and "Use this" on that
                # alternative would silently turn into "Dismiss" (found by the fuzz, bug F1).
                # The server treats value == base as "no net change" itself.
            last.resolve.extend(r for r in resolve if r not in last.resolve)
            last.hlc = self._stamp()
            return last.op_id
        op = self._new_op(collection, id, trip_id, "upsert", fields=dict(changes),
                          base={f: seen.get(f) for f in changes},  # R1
                          resolve=list(resolve), keep=creating or restore)
        return op.op_id

    def delete(self, collection: str, id: str) -> str | None:
        """Delete carries everything the user saw, so the server can tell a concurrent edit."""
        cur = self.view(collection, id)
        if cur is None or cur.deleted:
            return None
        cs = self.schema[collection]
        op = self._new_op(collection, id, cur.trip_id, "delete",
                          base={f: cur.fields.get(f) for f in sorted(cs.client_fields)},
                          resolve=[a["id"] for a in cur.conflicts])
        return op.op_id

    def restore(self, collection: str, id: str) -> str | None:
        """Undo delete: an upsert with no fields, stamped after the tombstone (R8 guarantees it)."""
        cur = self.view(collection, id)
        if cur is None or not cur.deleted:
            return None
        return self.mutate(collection, id, cur.trip_id, {}, restore=True)

    def resolve(self, collection: str, id: str, conflict_id: str, use: bool) -> str | None:
        """Dismiss an alternative, or make it the text ("Use this")."""
        cur = self.view(collection, id)
        alt = next((a for a in cur.conflicts if a["id"] == conflict_id), None) if cur else None
        if alt is None:
            return None
        fields = {alt["field"]: alt["value"]} if use else {}
        return self.mutate(collection, id, cur.trip_id, fields, resolve=[conflict_id])

    # ------------------------------------------------------------ syncing

    def sync(self) -> bool:
        """Push the outbox in order, adopt the answers, pull to the end.  False if offline or the
        connection dropped (state stays consistent; just call again)."""
        if not self.online:
            return False
        try:
            if self.outbox:
                batch = self.outbox[:]
                for op in batch:
                    op.sent = True  # R3: frozen before the request leaves
                resp = self.transport.push(self.device_id, [op.to_mutation() for op in batch])
                self._server_time(resp.server_ms)
                done = set()
                for r in resp.results:  # R4: only ops with an explicit result leave the outbox
                    done.add(r.op_id)
                    if r.status == REJECTED:
                        self.rejected.append(r)
                    self._adopt(r.doc)
                self.outbox = [op for op in self.outbox if op.op_id not in done]
            while True:
                page = self.transport.pull(self.cursor, self.pull_limit)
                self._server_time(page.server_ms)
                for d in page.docs:
                    self._adopt(d)
                self.cursor = max(self.cursor, page.cursor)
                if not page.has_more:
                    return True
        except ConnectionLost:
            return False

    def _adopt(self, doc: Doc | None) -> None:
        if doc is None:
            return
        key = (doc.collection, doc.id)
        have = self.synced.get(key)
        if have is None or doc.rev >= have.rev:  # R5
            self.synced[key] = doc.copy()
        for m in doc.meta.values():  # R8
            self.hlc.observe(m["hlc"])

    def _server_time(self, server_ms: int) -> None:
        if self.use_server_time and server_ms:
            self.clock_offset = server_ms - self.wall_clock()
