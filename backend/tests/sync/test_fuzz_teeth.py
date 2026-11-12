"""Does the fuzz have teeth?  Each case re-introduces one plausible design bug (several are what
ARCHITECTURE §5 literally said, or the obvious naive implementation) and asserts that the state
machine in test_fuzz.py catches it.  If one of these stops failing, the fuzz has gone blind."""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import HealthCheck, Phase, settings
from hypothesis.stateful import run_state_machine_as_test

import atlas.sync.merge as merge
from atlas.sync.server import InMemoryStore
from atlas.sync.sim import Client

from .test_fuzz import SyncMachine


def coalesce_into_sent_ops(mp):
    """Client folds a new edit into an op that was already pushed (ack lost) → server says
    `duplicate` and the new edit evaporates."""
    orig = Client.mutate

    def mutate(self, *a, **kw):
        for op in self.outbox:
            op.sent = False
        return orig(self, *a, **kw)
    mp.setattr(Client, "mutate", mutate)


def refresh_base_at_push(mp):
    """Client sends base = latest synced value instead of the value the user edited from →
    overwrites another device's edit the user never saw."""
    orig = Client.sync

    def sync(self):
        for op in self.outbox:
            if not op.sent and (op.collection, op.id) in self.synced:
                for f in op.base:
                    op.base[f] = self.synced[(op.collection, op.id)].fields.get(f)
        return orig(self)
    mp.setattr(Client, "sync", sync)


def cursor_from_push(mp):
    """Client advances its pull cursor from push answers (§5 returned a cursor from push) →
    skips other devices' changes that were logged before its own."""
    orig = Client._adopt

    def adopt(self, doc):
        orig(self, doc)
        if doc is not None:
            self.cursor = max(self.cursor, doc.rev)
    mp.setattr(Client, "_adopt", adopt)


def delete_ignores_concurrent_edits(mp):
    """Server applies a delete without checking what the deleter saw (delete as plain LWW)."""
    orig = merge._apply_delete

    def bad(doc, m, hlc, device, cs):
        if doc is not None and device != merge.PIPELINE:
            m = dataclasses.replace(m, base=dict(doc.fields), resolve=tuple(a["id"] for a in doc.conflicts))
        return orig(doc, m, hlc, device, cs)
    mp.setattr(merge, "_apply_delete", bad)


def delete_ignores_unseen_alternatives(mp):
    """Delete checks field bases but not alternatives added since the deleter last synced."""
    orig = merge._apply_delete

    def bad(doc, m, hlc, device, cs):
        if doc is not None:
            m = dataclasses.replace(m, resolve=tuple(a["id"] for a in doc.conflicts))
        return orig(doc, m, hlc, device, cs)
    mp.setattr(merge, "_apply_delete", bad)


def conflict_loser_dropped(mp):
    """Plain LWW on text: the losing text is not kept as an alternative."""
    mp.setattr(merge, "_add_alt", lambda *a, **kw: None)


def resolve_after_fields(mp):
    """'Use this' racing a newer edit: the chosen text loses, is re-added as an alternative, and
    is then removed by its own resolve id because resolve ran AFTER the fields."""
    orig = merge._apply_upsert

    def bad(doc, m, hlc, device, cs):
        new, res = orig(doc, dataclasses.replace(m, resolve=()), hlc, device, cs)
        if m.resolve and new is not None and not new.deleted:
            new = new.copy()
            new.conflicts = [a for a in new.conflicts if a["id"] not in m.resolve]
        return new, res
    mp.setattr(merge, "_apply_upsert", bad)


def scalar_edit_never_resurrects_text(mp):
    """An edit arriving at a tombstone is dropped unless its hlc is newer (pure LWW delete):
    text typed offline before the delete is lost."""
    orig = merge.would_resurrect

    def bad(doc, m, hlc, cs):
        return orig(doc, dataclasses.replace(m, fields={}), hlc, cs)
    mp.setattr(merge, "would_resurrect", bad)
    import atlas.sync.sim as sim
    mp.setattr(sim, "would_resurrect", bad)


def no_op_log(mp):
    """Server forgets applied op ids: a retried push is applied twice."""
    mp.setattr(InMemoryStore, "get_op", lambda self, owner, op_id: None)


def no_rev_guard(mp):
    """Client lets any server doc replace its synced copy, even an older one (R5)."""
    def adopt(self, doc):
        if doc is not None:
            self.synced[(doc.collection, doc.id)] = doc.copy()
            for m in doc.meta.values():
                self.hlc.observe(m["hlc"])
    mp.setattr(Client, "_adopt", adopt)


BUGS = [coalesce_into_sent_ops, refresh_base_at_push, cursor_from_push, delete_ignores_concurrent_edits,
        delete_ignores_unseen_alternatives, conflict_loser_dropped, resolve_after_fields,
        scalar_edit_never_resurrects_text, no_op_log]


@pytest.mark.parametrize("bug", BUGS, ids=lambda b: b.__name__)
def test_fuzz_catches(bug, monkeypatch):
    bug(monkeypatch)
    with pytest.raises(AssertionError):
        run_state_machine_as_test(SyncMachine, settings=settings(
            max_examples=1500, stateful_step_count=50, deadline=None, database=None,
            suppress_health_check=list(HealthCheck), phases=[Phase.generate], derandomize=True))
