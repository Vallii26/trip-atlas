"""The verifier is measured, not assumed: seeded mutation metrics asserted against PLAN.md targets."""

from __future__ import annotations

import pytest

from atlas.eval.mutations import MUTATORS, _append, format_table, generate, run_harness, run_texts

SEEDS = [7, 42]


@pytest.fixture(scope="module")
def all_cases(fx):
    return [c for cs in fx.by_day.values() for c in cs]


@pytest.mark.parametrize("seed", SEEDS)
def test_mutation_recall_and_false_positives(fx, all_cases, seed):
    r = run_harness(all_cases, seed=seed, coverage=True, known_places=fx.known)
    print("\n" + format_table(r))
    assert r.faithful_blocks >= 40 and r.n >= 1000
    assert r.fp_block_rate <= 0.02, r.false_positive_blocks
    assert r.fp_claim_rate <= 0.02
    assert r.recall >= 0.95
    for name, m in r.per_mutator.items():
        assert m.n > 0, f"mutator {name} produced no countable mutation"
        assert m.recall >= 0.90, (name, [(x.block_id, x.text) for x in m.missed])


def test_backstop_is_what_closes_the_gap(fx, all_cases):
    off = run_harness(all_cases, seed=7, coverage=False, known_places=fx.known)
    on = run_harness(all_cases, seed=7, coverage=True, known_places=fx.known)
    assert off.fp_block_rate == 0.0
    assert off.recall < 0.95 <= on.recall            # the lexicon alone does not reach the target
    assert off.per_mutator["invented_sentence"].recall < 0.8


def test_mutations_are_deterministic_and_never_degenerate(all_cases):
    a, skips_a = generate(all_cases, 7)
    b, skips_b = generate(all_cases, 7)
    assert [(m.mutator, m.block_id, m.text) for _, m in a] == [(m.mutator, m.block_id, m.text) for _, m in b]
    assert [(s.mutator, s.block_id, s.reason) for s in skips_a] == [(s.mutator, s.block_id, s.reason) for s in skips_b]
    assert all(m.text != c.block.text and m.text.strip() for c, m in a)
    assert {m.mutator for _, m in a} == set(MUTATORS)
    c, _ = generate(all_cases, 8)
    assert [m.text for _, m in a] != [m.text for _, m in c]


def _items(fx, rows):
    return [(fx.cases[bid], text if mode == "replace" else _append(fx.cases[bid].block.text, text))
            for bid, text, mode in rows]


def test_adversarial_fabrications(fx):
    rows = fx.adv.ADVERSARIAL
    assert len(rows) >= 60
    n, passed = run_texts(_items(fx, rows), coverage=True, known_places=fx.known)
    recall = (n - len(passed)) / n
    assert recall >= 0.90, passed
    # the known residual: fabrications made only of neutral words (documented blind spot) —
    # if this set changes, update docs/prototypes/R2-faithfulness.md
    assert {t.split(". ")[-1] for _, t in passed} <= {
        "Had it to myself.", "Swam across.", "It took a while.", "We made it.", "I spent a day there.",
        "I stayed until the end."}
    n2, passed2 = run_texts(_items(fx, rows), coverage=False, known_places=fx.known)
    assert (n2 - len(passed2)) / n2 < 0.7             # without the backstop most subtle ones slip through


def test_off_contract_true_prose_is_over_rejected(fx):
    """Honest cost of the closed world: true sentences outside the contract are rejected."""
    n, passed = run_texts(_items(fx, fx.adv.OFF_CONTRACT_TRUE), coverage=True, known_places=fx.known)
    assert 0.3 <= len(passed) / n <= 0.8
