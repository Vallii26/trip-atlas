from __future__ import annotations

import pytest

from atlas.eval.mutations import load_fixture_cases
from atlas.pipeline.diary.verify import verify_block


class Fx:
    def __init__(self):
        self.by_day, self.trips, self.adv = load_fixture_cases()
        self.cases = {c.block.id: c for cs in self.by_day.values() for c in cs}
        self.evidence = {e.id: e for e in self.trips.evidence()}
        self.known = self.trips.KNOWN_PLACES

    def check(self, block_id: str, text: str, ids=None, style="same", **kw):
        """Verify `text` with the citations (or `ids`) of a fixture block."""
        c = self.cases[block_id]
        upd = {"text": text}
        if ids is not None:
            upd["evidence_ids"] = ids
        return verify_block(c.block.model_copy(update=upd), self.evidence, known_places=self.known,
                            style=c.style if style == "same" else style, **kw)


@pytest.fixture(scope="session")
def fx() -> Fx:
    return Fx()
