"""Storage-agnostic sync server: push / pull over a small ``Store`` protocol.

A DB-backed service implements ``Store`` (SQLite: ``docs``, ``changes``, ``applied_ops``,
``trips``) and must run **each mutation's** get_doc → put_doc → append_change → record_op in one
transaction, with ``seq`` allocated in commit order (trivially true with SQLite's single writer).

Scoping: every doc belongs to a trip, every trip to one user.  The op log and the change feed
are keyed by the owning user, so one user can never observe another user's docs — not through
pull, not through a ``rejected`` result, and not by replaying someone else's ``op_id``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from .hlc import valid_device
from .merge import (
    DEFAULT_SCHEMA, DUPLICATE, PIPELINE, REJECTED, ApplyResult, CollectionSchema, Doc, Mutation,
    apply_mutation,
)


@dataclass(frozen=True)
class OpRecord:
    status: str
    collection: str
    id: str


class Store(Protocol):
    def get_doc(self, collection: str, id: str) -> Doc | None: ...
    def put_doc(self, owner: str, doc: Doc) -> None: ...
    def append_change(self, owner: str, collection: str, id: str) -> int:
        """Allocate and return the next global, strictly increasing sequence number."""
    def changes_since(self, owner: str, cursor: int, limit: int) -> list[tuple[int, str, str]]:
        """Up to ``limit`` (seq, collection, id) for the owner's docs whose LATEST change has
        seq > cursor, ascending by seq.  One entry per doc.
        (SQL: ``SELECT rev, collection, id FROM docs WHERE owner=? AND rev>? ORDER BY rev LIMIT ?``.)"""
    def get_op(self, owner: str, op_id: str) -> OpRecord | None: ...
    def record_op(self, owner: str, op_id: str, record: OpRecord) -> None: ...
    def trip_owner(self, trip_id: str) -> str | None: ...
    def set_trip_owner(self, trip_id: str, owner: str) -> None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self.docs: dict[tuple[str, str], Doc] = {}
        self.owners: dict[tuple[str, str], str] = {}
        self.log: list[tuple[int, str, str, str]] = []  # (seq, owner, collection, id)
        self.ops: dict[tuple[str, str], OpRecord] = {}
        self.trips: dict[str, str] = {}

    def get_doc(self, collection, id):
        d = self.docs.get((collection, id))
        return d.copy() if d is not None else None

    def put_doc(self, owner, doc):
        self.docs[(doc.collection, doc.id)] = doc.copy()
        self.owners[(doc.collection, doc.id)] = owner

    def append_change(self, owner, collection, id):
        seq = len(self.log) + 1
        self.log.append((seq, owner, collection, id))
        return seq

    def changes_since(self, owner, cursor, limit):
        out = []
        for seq, o, c, i in self.log[cursor:]:
            if o == owner and self.docs[(c, i)].rev == seq:  # only the doc's latest change
                out.append((seq, c, i))
                if len(out) >= limit:
                    break
        return out

    def get_op(self, owner, op_id):
        return self.ops.get((owner, op_id))

    def record_op(self, owner, op_id, record):
        self.ops[(owner, op_id)] = record

    def trip_owner(self, trip_id):
        return self.trips.get(trip_id)

    def set_trip_owner(self, trip_id, owner):
        self.trips[trip_id] = owner

    def snapshot(self) -> dict[str, Any]:
        """Everything observable, for 'replay changed nothing' assertions."""
        return {"docs": {k: v.to_dict() for k, v in self.docs.items()}, "log": len(self.log),
                "trips": dict(self.trips)}


@dataclass
class OpResult:
    op_id: str
    status: str
    doc: Doc | None = None
    fields: dict[str, str] = field(default_factory=dict)
    detail: str = ""
    original_status: str | None = None  # set on duplicates
    evicted: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PushResponse:
    results: list[OpResult]
    server_ms: int


@dataclass
class PullResponse:
    docs: list[Doc]
    cursor: int
    has_more: bool
    server_ms: int


class SyncServer:
    def __init__(self, store: Store, schema: Mapping[str, CollectionSchema] = DEFAULT_SCHEMA,
                 max_ahead_ms: int = 300_000) -> None:
        self.store = store
        self.schema = schema
        self.max_ahead_ms = max_ahead_ms

    # ---- clients

    def push(self, user_id: str, device_id: str, mutations: Sequence[Mutation], server_ms: int) -> PushResponse:
        """Apply mutations in order.  Each is independent and atomic; a batch cut short by a
        dropped connection is safe to resend whole (``op_id`` dedupes)."""
        ok_device = valid_device(device_id) and device_id != PIPELINE
        results = []
        for m in mutations:
            if not ok_device or not self._same_device(m, device_id):
                results.append(OpResult(m.op_id, REJECTED, detail="device mismatch"))
                continue
            results.append(self._apply(user_id, m, server_ms, pipeline=False))
        return PushResponse(results, server_ms)

    def pull(self, user_id: str, cursor: int, limit: int = 200, server_ms: int = 0) -> PullResponse:
        """Docs of ``user_id`` changed after ``cursor``: each once, in its latest state, oldest
        change first.  ``cursor`` never decreases.  A doc that changes again between two pages
        moves to a later page (and may then be delivered twice) but is never skipped."""
        if cursor < 0 or limit < 1:
            raise ValueError("cursor must be >= 0 and limit >= 1")
        entries = self.store.changes_since(user_id, cursor, limit + 1)
        has_more = len(entries) > limit
        entries = entries[:limit]
        docs = [d for _, c, i in entries if (d := self.store.get_doc(c, i)) is not None]
        return PullResponse(docs, entries[-1][0] if entries else cursor, has_more, server_ms)

    # ---- pipeline (internal; never reachable from the HTTP push)

    def apply_pipeline(self, trip_id: str, mutations: Sequence[Mutation], server_ms: int) -> PushResponse:
        owner = self.store.trip_owner(trip_id)
        results = []
        for m in mutations:
            if owner is None or m.trip_id != trip_id or not self._same_device(m, PIPELINE):
                results.append(OpResult(m.op_id, REJECTED, detail="not a pipeline mutation for this trip"))
                continue
            results.append(self._apply(owner, m, server_ms, pipeline=True))
        return PushResponse(results, server_ms)

    # ---- internals

    @staticmethod
    def _same_device(m: Mutation, device_id: str) -> bool:
        try:
            return m.device == device_id
        except ValueError:
            return False

    def _apply(self, user_id: str, m: Mutation, server_ms: int, *, pipeline: bool) -> OpResult:
        st = self.store
        prior = st.get_op(user_id, m.op_id)
        if prior is not None:
            doc = None if prior.status == REJECTED else st.get_doc(prior.collection, prior.id)
            return OpResult(m.op_id, DUPLICATE, doc, original_status=prior.status)

        owner = st.trip_owner(m.trip_id)
        claims_trip = False
        if owner is None:
            # The only thing that can be done in an unknown trip is to create it.
            claims_trip = (not pipeline and m.collection == "trips" and m.id == m.trip_id
                           and m.kind == "upsert" and st.get_doc("trips", m.id) is None)
            allowed = claims_trip
        else:
            allowed = owner == user_id and (m.collection != "trips" or m.id == m.trip_id)
        if not allowed:
            res: ApplyResult = ApplyResult(REJECTED, detail="forbidden")
            doc = new = None
        else:
            doc = st.get_doc(m.collection, m.id)
            new, res = apply_mutation(doc, m, server_ms=server_ms, schema=self.schema,
                                      max_ahead_ms=self.max_ahead_ms)
        if res.status == REJECTED:
            st.record_op(user_id, m.op_id, OpRecord(REJECTED, m.collection, m.id))
            return OpResult(m.op_id, REJECTED, detail=res.detail)  # never leak a doc
        if res.changed and new is not None:
            if claims_trip:
                st.set_trip_owner(m.trip_id, user_id)
            new.rev = st.append_change(user_id, m.collection, m.id)
            st.put_doc(user_id, new)
        st.record_op(user_id, m.op_id, OpRecord(res.status, m.collection, m.id))
        return OpResult(m.op_id, res.status, new, res.fields, res.detail, evicted=res.evicted)
