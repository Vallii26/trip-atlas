"""Document model and merge rules (ARCHITECTURE §5).  Pure: no I/O, no clock, no ids generated.

``apply_mutation(doc | None, mutation, *, server_ms, schema) -> (doc, ApplyResult)`` is the whole
contract; ``ApplyResult.status`` is one of applied / merged / conflict / duplicate / rejected
(``duplicate`` is produced by the server, which owns the op log).

Rules, in the order they are applied
------------------------------------
Validation (→ ``rejected``, nothing changes): unknown collection, malformed hlc, trip mismatch,
a client writing a field it may not write / creating / deleting where the schema forbids it,
non-string value for a merge field.

Upsert, per field, with ``s`` = server value, ``b`` = mutation base, ``c`` = new value:
  1. ``c == s``                      → noop (both sides made the same edit).
  2. field is pipeline-owned/unset   → a user write applies outright (users always beat the
                                        pipeline, D6).
  3. ``b == s``                      → apply.  The clock is irrelevant: the writer saw the current
                                        value.  The stored hlc is ``max(hlc, successor(old hlc))``.
  4. ``c == b``                      → noop (the client made no net change; do not let it revert
                                        someone else's edit by LWW).
  5. concurrent, scalar field        → the write that ``_beats`` wins; a losing mutation is
                                        dropped and reported (field outcome ``lost``).
  6. concurrent, merge field         → ``merge3(b, s, c)``.  Clean → merged text.  Not clean →
                                        the write that ``_beats`` becomes the text and the other
                                        whole text is appended to ``doc.conflicts``.
``_beats``: same device → the later arrival wins (a device's ops arrive in the order it made
them; hlc order inside one device is not reliable after clamping); otherwise higher hlc wins.

Conflict alternatives ``{id, field, value, hlc, device, base}``:
  * ``id`` is content-addressed (hash of field + value) → identical alternatives dedupe, and
    "resolve this id" means "dismiss exactly the text I saw", which cannot race a third edit.
  * an alternative equal to the current text is dropped (it is no longer an alternative).
  * a device continuing to edit its own losing text replaces its alternative (see step 6).
  * hard cap per doc (``max_conflicts``); the lowest-hlc alternative is evicted and reported.
Resolving: an ordinary upsert with ``resolve=[ids]``.  The listed alternatives are removed
FIRST, then the fields are applied by the rules above.  Dismiss = no fields.  "Use this" =
``fields{text: alternative}``, ``base{text: text the user saw}``, ``resolve=[alt id]``; if a
third edit raced it, rule 6 runs and whichever text loses is (re-)added as an alternative.

Deletes are tombstones (``deleted`` + ``meta["_deleted"]``); fields are kept for resurrection.
  * A user delete carries ``base`` = every client-writable field as the user saw it and
    ``resolve`` = every alternative the user saw.  It is REFUSED (status ``conflict``) when a user
    edit it did not see exists: an unseen alternative, a merge field that differs from base, a
    scalar that differs from base and beats the delete, or a later restore.  Edit wins over a
    concurrent delete because a delete can be redone with one tap and typed text cannot.
  * An upsert arriving at a tombstone resurrects it when the tombstone is the pipeline's, or the
    upsert carries a merge field (typed text is never dropped), or it beats the tombstone's hlc
    (LWW; also how "undo delete" works: an upsert with no fields).  Otherwise it is dropped.
Pipeline (device ``pipeline``): may write any field and create/delete in any collection, but a
field whose ``meta.device`` is a user device is skipped (``kept``), a doc with any user-owned
field or alternative is not deleted, and a user's tombstone is not resurrected.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from .hlc import clamp, parse_hlc, successor
from .textmerge import merge3

PIPELINE = "pipeline"
DELETED = "_deleted"  # meta key of the tombstone / last restore

APPLIED, MERGED, CONFLICT, DUPLICATE, REJECTED = "applied", "merged", "conflict", "duplicate", "rejected"


@dataclass
class Doc:
    id: str
    collection: str
    trip_id: str
    fields: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, dict[str, str]] = field(default_factory=dict)  # field → {hlc, device}
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    rev: int = 0
    deleted: bool = False

    def copy(self) -> "Doc":
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.__dict__)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Doc":
        return cls(**copy.deepcopy(dict(d)))


@dataclass(frozen=True)
class Mutation:
    op_id: str
    collection: str
    id: str
    trip_id: str
    kind: str  # "upsert" | "delete"
    hlc: str
    fields: Mapping[str, Any] = field(default_factory=dict)
    base: Mapping[str, Any] = field(default_factory=dict)
    resolve: tuple[str, ...] = ()

    @property
    def device(self) -> str:
        return parse_hlc(self.hlc).device

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Mutation":
        return cls(
            op_id=str(d["op_id"]), collection=str(d["collection"]), id=str(d["id"]),
            trip_id=str(d["trip_id"]), kind=str(d["kind"]), hlc=str(d["hlc"]),
            fields=dict(d.get("fields") or {}), base=dict(d.get("base") or {}),
            resolve=tuple(d.get("resolve") or ()),
        )


@dataclass(frozen=True)
class CollectionSchema:
    name: str
    client_fields: frozenset[str] = frozenset()  # writable by clients; everything else is read-only
    merge_fields: frozenset[str] = frozenset()   # subset of client_fields merged as prose
    client_create: bool = False
    client_delete: bool = False
    max_conflicts: int = 8


def _cs(name: str, fields: str = "", merge: str = "", create: bool = False, delete: bool = False):
    return CollectionSchema(name, frozenset(fields.split()), frozenset(merge.split()), create, delete)


DEFAULT_SCHEMA: dict[str, CollectionSchema] = {
    c.name: c
    for c in (
        _cs("trips", "title dates_hint cover_asset_id", create=True, delete=True),
        _cs("moments", "title kind hidden note", merge="note", create=True, delete=True),
        _cs("assets", "hidden favorite caption pinned_moment_id", merge="caption"),
        _cs("diary_blocks", "text pos", merge="text", create=True, delete=True),
        _cs("evidence"),
        _cs("derived"),
    )
}


@dataclass
class ApplyResult:
    status: str
    fields: dict[str, str] = field(default_factory=dict)  # applied|merged|conflict|lost|noop|kept
    changed: bool = False
    detail: str = ""
    evicted: list[dict[str, Any]] = field(default_factory=list)  # alternatives dropped by the cap


def conflict_id(field_name: str, value: str) -> str:
    return "c_" + hashlib.sha256(f"{field_name}\0{value}".encode()).hexdigest()[:16]


def _beats(hlc: str, device: str, stored: Mapping[str, str] | None) -> bool:
    return stored is None or stored["device"] == device or hlc > stored["hlc"]


def _stamp(hlc: str, device: str, stored: Mapping[str, str] | None) -> dict[str, str]:
    """Meta for a write that replaces ``stored``: never older than what it replaced."""
    if stored is not None:
        hlc = max(hlc, successor(stored["hlc"], device))
    return {"hlc": hlc, "device": device}


def would_resurrect(doc: Doc, m: Mutation, hlc: str, cs: CollectionSchema) -> bool:
    """Does upsert ``m`` (with effective timestamp ``hlc``) bring tombstoned ``doc`` back?"""
    tomb = doc.meta.get(DELETED)
    device = parse_hlc(hlc).device
    if tomb is None:
        return True
    if device == PIPELINE:
        return tomb["device"] == PIPELINE
    return (
        tomb["device"] == PIPELINE
        or any(f in cs.merge_fields for f in m.fields)
        or _beats(hlc, device, tomb)
    )


def _rejected(doc: Doc | None, why: str) -> tuple[Doc | None, ApplyResult]:
    return doc, ApplyResult(REJECTED, detail=why)


def apply_mutation(
    doc: Doc | None,
    m: Mutation,
    *,
    server_ms: int,
    schema: Mapping[str, CollectionSchema],
    max_ahead_ms: int = 300_000,
) -> tuple[Doc | None, ApplyResult]:
    """Apply one mutation.  Never mutates ``doc``; returns it unchanged if nothing changed.
    ``rev`` is not touched here (the server sets it when it logs the change)."""
    cs = schema.get(m.collection)
    if cs is None:
        return _rejected(doc, "unknown collection")
    try:
        hlc = clamp(m.hlc, server_ms, max_ahead_ms)
    except ValueError:
        return _rejected(doc, "invalid hlc")
    device = parse_hlc(hlc).device
    is_pipeline = device == PIPELINE
    if m.kind not in ("upsert", "delete"):
        return _rejected(doc, "invalid kind")
    if doc is not None and (doc.trip_id != m.trip_id or doc.collection != m.collection or doc.id != m.id):
        return _rejected(doc, "doc belongs to another trip")
    if not is_pipeline:
        if m.kind == "delete" and not cs.client_delete:
            return _rejected(doc, "collection is not client-deletable")
        if m.kind == "upsert":
            if doc is None and not cs.client_create:
                return _rejected(doc, "collection is not client-creatable")
            bad = sorted(set(m.fields) - cs.client_fields)
            if bad:
                return _rejected(doc, f"read-only field(s): {', '.join(bad)}")
    if m.kind == "upsert":
        for f in cs.merge_fields & set(m.fields):
            if not isinstance(m.fields[f], str):
                return _rejected(doc, f"merge field {f} must be a string")

    if m.kind == "delete":
        new, res = _apply_delete(doc, m, hlc, device, cs)
    else:
        new, res = _apply_upsert(doc, m, hlc, device, cs)
    if doc is not None and new == doc:
        res.changed = False
        return doc, res
    res.changed = new is not None
    return new, res


# ---------------------------------------------------------------- upsert

def _set(doc: Doc, cs: CollectionSchema, f: str, value: Any, hlc: str, device: str) -> None:
    doc.meta[f] = _stamp(hlc, device, doc.meta.get(f))
    doc.fields[f] = value
    if f in cs.merge_fields:  # an alternative equal to the text is no longer an alternative
        doc.conflicts = [a for a in doc.conflicts if not (a["field"] == f and a["value"] == value)]


def _add_alt(doc: Doc, cs: CollectionSchema, res: ApplyResult, f: str, value: str,
             hlc: str, device: str, base: Any) -> None:
    if value == doc.fields.get(f):
        return
    cid = conflict_id(f, value)
    if any(a["id"] == cid for a in doc.conflicts):
        return
    doc.conflicts.append({"id": cid, "field": f, "value": value, "hlc": hlc, "device": device, "base": base})
    while len(doc.conflicts) > cs.max_conflicts:
        victim = min(doc.conflicts, key=lambda a: (a["hlc"], a["id"]))
        doc.conflicts.remove(victim)
        res.evicted.append(victim)


def _apply_upsert(doc: Doc | None, m: Mutation, hlc: str, device: str, cs: CollectionSchema):
    is_pipeline = device == PIPELINE
    res = ApplyResult(APPLIED)
    if doc is None:
        new = Doc(id=m.id, collection=m.collection, trip_id=m.trip_id)
    else:
        new = doc.copy()
        if new.deleted:
            if not would_resurrect(new, m, hlc, cs):
                return doc, ApplyResult(CONFLICT, {f: "lost" for f in m.fields}, detail="doc is deleted")
            new.deleted = False
            new.meta[DELETED] = _stamp(hlc, device, new.meta.get(DELETED))

    if m.resolve and not is_pipeline:
        gone = set(m.resolve)
        new.conflicts = [a for a in new.conflicts if a["id"] not in gone]

    for f in sorted(m.fields):
        c, s, b, fm = m.fields[f], new.fields.get(f), m.base.get(f), new.meta.get(f)
        owner = fm["device"] if fm else None
        if is_pipeline:
            if owner not in (None, PIPELINE):
                res.fields[f] = "kept"  # user-owned: the pipeline never overwrites it
            elif c == s and fm is not None:
                res.fields[f] = "noop"
            else:
                _set(new, cs, f, c, hlc, device)
                res.fields[f] = "applied"
            continue
        if c == s and fm is not None:
            res.fields[f] = "noop"
        elif fm is None or owner == PIPELINE or b == s:
            _set(new, cs, f, c, hlc, device)
            res.fields[f] = "applied"
        elif c == b:
            res.fields[f] = "noop"
        elif f not in cs.merge_fields:
            if _beats(hlc, device, fm):
                _set(new, cs, f, c, hlc, device)
                res.fields[f] = "applied"
            else:
                res.fields[f] = "lost"
        else:
            res.fields[f] = _merge_text(new, cs, res, f, c, s or "", b, hlc, device)

    outcomes = set(res.fields.values())
    if outcomes & {"conflict", "lost", "kept"}:
        res.status = CONFLICT
    elif "merged" in outcomes:
        res.status = MERGED
    return new, res


def _merge_text(doc: Doc, cs: CollectionSchema, res: ApplyResult, f: str, c: str, s: str,
                b: Any, hlc: str, device: str) -> str:
    fm = doc.meta[f]
    # Is this device continuing to edit a text of its own that already lost (b is its alternative)?
    # Then the new text supersedes that alternative: the user edited it deliberately.
    own = next((a for a in doc.conflicts
                if a["field"] == f and a["device"] == device and a["value"] == b), None)
    if own is not None:
        doc.conflicts.remove(own)
    r = merge3(b if isinstance(b, str) else "", s, c)
    if r.clean:
        if r.text != s:
            _set(doc, cs, f, r.text, hlc, device)
        if own is not None:
            # The merged text holds this edit but not the rest of the device's losing branch:
            # keep that branch visible in its latest form.
            _add_alt(doc, cs, res, f, c, hlc, device, own["base"])
        return "merged"
    if _beats(hlc, device, fm):
        _set(doc, cs, f, c, hlc, device)
        _add_alt(doc, cs, res, f, s, fm["hlc"], fm["device"], b)
    else:
        _add_alt(doc, cs, res, f, c, hlc, device, own["base"] if own is not None else b)
    return "conflict"


# ---------------------------------------------------------------- delete

def _apply_delete(doc: Doc | None, m: Mutation, hlc: str, device: str, cs: CollectionSchema):
    if doc is None:
        return None, ApplyResult(APPLIED, detail="absent")
    is_pipeline = device == PIPELINE
    tomb = doc.meta.get(DELETED)
    if doc.deleted:
        # Already deleted.  A user's delete takes the tombstone over from the pipeline, and a
        # newer delete moves the tombstone forward (so an older concurrent scalar edit loses).
        take = tomb is None or (
            not is_pipeline and (tomb["device"] == PIPELINE or (tomb["device"] != device and hlc > tomb["hlc"]))
        )
        if not take:
            return doc, ApplyResult(APPLIED, detail="already deleted")
        new = doc.copy()
        new.meta[DELETED] = _stamp(hlc, device, tomb)
        return new, ApplyResult(APPLIED)

    def refuse(why: str):
        return doc, ApplyResult(CONFLICT, detail=why)

    if is_pipeline:
        if doc.conflicts or any(v["device"] != PIPELINE for v in doc.meta.values()):
            return refuse("kept: user-touched")
    else:
        seen = set(m.resolve)
        if any(a["id"] not in seen for a in doc.conflicts):
            return refuse("edit wins: unseen alternative")
        for f in sorted(cs.client_fields):
            fm = doc.meta.get(f)
            if fm is None or fm["device"] == PIPELINE or doc.fields.get(f) == m.base.get(f):
                continue
            if f in cs.merge_fields or not _beats(hlc, device, fm):
                return refuse(f"edit wins: {f}")
        if tomb is not None and not _beats(hlc, device, tomb):
            return refuse("restored later")
    new = doc.copy()
    new.deleted = True
    new.meta[DELETED] = _stamp(hlc, device, tomb)
    return new, ApplyResult(APPLIED)
