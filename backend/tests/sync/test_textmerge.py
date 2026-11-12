import pytest
from hypothesis import given, settings, strategies as st

from atlas.sync.textmerge import merge3, tokenize


def clean(base, a, b, want):
    for x, y in ((a, b), (b, a)):
        r = merge3(base, x, y)
        assert r.clean, r.conflicts
        assert r.text == want


def conflict(base, a, b):
    ra, rb = merge3(base, a, b), merge3(base, b, a)
    assert not ra.clean and not rb.clean and ra.conflicts
    assert ra.text == a and rb.text == b  # nothing is merged on conflict


# ---------------------------------------------------------------- tokeniser
@pytest.mark.parametrize("text", [
    "", " ", "We didn't leave until 17:30… Zoë's café was full!!",
    "Sunrise 🌅 at 6.45, then 1,200 steps up — worth it 👍🏽 👨‍👩‍👧 🇵🇹.",
    "café au lait\n\nNew paragraph\t(tabs)  ", "well-known half-day trip; “quoted” text",
])
def test_tokenize_is_lossless_and_never_splits_words_or_emoji(text):
    toks = tokenize(text)
    assert "".join(toks) == text
    for whole in ["didn't", "17:30", "Zoë's", "6.45", "1,200", "👍🏽", "👨‍👩‍👧", "🇵🇹", "café", "well-known"]:
        if whole in text:
            assert whole in toks


@given(st.text(alphabet=st.sampled_from(list("ab é.,!?'-\n🌅👍🏽‍́🇵🇹1:")), max_size=40))
def test_tokenize_lossless_property(text):
    assert "".join(tokenize(text)) == text


# ---------------------------------------------------------------- trivial cases
def test_identical_edits_one_side_unchanged_and_both_deleting_everything():
    b = "We walked to the market."
    clean(b, "We ran to the market.", "We ran to the market.", "We ran to the market.")
    clean(b, b, "We ran to the market.", "We ran to the market.")
    clean(b, "", "", "")
    clean(b, b, "", "")
    clean("", "", "Hello.", "Hello.")
    conflict(b, "", "We ran to the market.")       # delete everything vs edit
    conflict("", "First draft.", "Another draft.")  # both wrote into an empty block


# ---------------------------------------------------------------- the policy
def test_typo_fix_at_start_and_rewrite_of_last_clause_are_both_kept():
    base = "We arived in Lisbon just after noon and walked to the big market."
    a = "We arrived in Lisbon just after noon and walked to the big market."
    b = "We arived in Lisbon just after noon and took the tram up to Alfama."
    clean(base, a, b, "We arrived in Lisbon just after noon and took the tram up to Alfama.")


def test_same_sentence_close_edits_conflict_instead_of_making_a_chimera():
    conflict("We walked to the big market.", "We walked slowly to the big market.", "We ran to the old market.")
    # two single-word swaps two words apart: would give "We ran to the old market", which nobody wrote
    conflict("We walked to the big market.", "We ran to the big market.", "We walked to the old market.")
    # negation next to a rewrite
    conflict("The food was good.", "The food was not good.", "The food was good, not great.")
    # same word changed differently
    conflict("Dinner was fine.", "Dinner was superb.", "Dinner was awful.")


def test_edits_in_different_sentences_merge_even_when_adjacent():
    base = "The market was closed. Luckily the café next door was open."
    a = "The market was shut. Luckily the café next door was open."
    b = "The market was closed. Thankfully the café next door was open."
    clean(base, a, b, "The market was shut. Thankfully the café next door was open.")


def test_append_sentence_while_other_side_edits_the_middle():
    base = "We walked to the market."
    clean(base, base + " It was closed.", "We strolled to the market.", "We strolled to the market. It was closed.")
    base3 = "Up early. The bus left at 7:10. We slept the whole way."
    clean(base3, base3 + " Arrived at noon 🎉", "Up early. The bus finally left at 7:40. We slept the whole way.",
          "Up early. The bus finally left at 7:40. We slept the whole way. Arrived at noon 🎉")


def test_whole_sentences_inserted_at_different_places_merge():
    base = "We woke late. We drove home."
    a = "It rained all night. We woke late. We drove home."
    b = "We woke late. We drove home. The cat was waiting."
    clean(base, a, b, "It rained all night. We woke late. We drove home. The cat was waiting.")


def test_both_append_different_sentences_is_a_conflict_order_is_unknowable():
    base = "We walked to the market."
    conflict(base, base + " It was closed.", base + " We bought figs.")
    clean(base, base + " It was closed.", base + " It was closed.", base + " It was closed.")


def test_continuing_an_unterminated_sentence_is_not_a_new_sentence():
    conflict("We walked to the market", "We walked to the market and bought figs", "We strolled to the market")


def test_trailing_whitespace_never_conflicts():
    clean("We walked to the market. ", "We walked to the market.", "We strolled to the market. It was closed.",
          "We strolled to the market. It was closed.")
    clean("We walked to the market", "We walked to the market\n", "We strolled to the market", "We strolled to the market\n")
    clean("A day.  Two  spaces.", "A day. Two spaces.", "A fine day.  Two  spaces.", "A fine day. Two spaces.")


def test_punctuation_only_edits():
    base = "After lunch we took the long coastal road north and stopped at every beach"
    a = "After lunch, we took the long coastal road north and stopped at every beach"
    b = "After lunch we took the long coastal road north and stopped at every beach."
    clean(base, a, b, "After lunch, we took the long coastal road north and stopped at every beach.")
    conflict("Great day", "Great day!", "Great day.")
    clean("Great day", "Great day!", "Great day!", "Great day!")
    conflict("We ate, then slept.", "We ate; then slept.", "We ate, then napped.")  # too close


def test_unicode_and_emoji():
    base = "Zoë et moi avons mangé à la crêperie près du port, puis marché jusqu'au phare 🌊."
    a = "Zoë et moi avons déjeuné à la crêperie près du port, puis marché jusqu'au phare 🌊."
    b = "Zoë et moi avons mangé à la crêperie près du port, puis marché jusqu'au phare 🌊🌅."
    clean(base, a, b, "Zoë et moi avons déjeuné à la crêperie près du port, puis marché jusqu'au phare 🌊🌅.")
    conflict("Family photo 👨‍👩‍👧 done.", "Family photo 👨‍👩‍👦 done.", "Family photo 👩‍👩‍👧 done.")
    clean("東京に着いた。", "東京に着いた。 Ramen first!", "東京に着いた。", "東京に着いた。 Ramen first!")


def test_abbreviations_and_times_do_not_create_sentence_boundaries():
    # "St. Paul" is one sentence: close edits around the dot must conflict
    conflict("We saw St. Paul's from the bridge.", "We visited St. Paul's from the bridge.",
             "We saw St. Peter's from the bridge.")
    conflict("Left at 5.30 sharp.", "Left at 6.30 sharp.", "Left at 5.30 exactly.")


def test_one_side_deletes_a_sentence_other_edits_another():
    base = "We woke late. Breakfast was cold. The drive home took four hours."
    a = "We woke late. The drive home took four hours."
    b = "We woke late. Breakfast was cold. The drive home took five long hours."
    clean(base, a, b, "We woke late. The drive home took five long hours.")
    conflict(base, a, "We woke late. Breakfast was cold but good. The drive home took four hours.")


WORDS = ["We", "walked", "to", "the", "old", "market", "and", "bought", "figs", ".", "!", ",", "It", "rained",
         "Zoë", "🌊", "didn't", "\n"]
prose = st.lists(st.sampled_from(WORDS), max_size=14).map(" ".join)


@settings(max_examples=300)
@given(prose, prose, prose)
def test_merge_is_symmetric_deterministic_and_never_breaks_tokens(base, a, b):
    r1, r2 = merge3(base, a, b), merge3(base, b, a)
    assert r1.clean == r2.clean
    assert merge3(base, a, b) == r1
    if r1.clean:
        assert r1.text == r2.text
        allowed = set(tokenize(base)) | set(tokenize(a)) | set(tokenize(b))
        assert set(tokenize(r1.text)) <= allowed  # no token that nobody typed
    assert merge3(base, a, a).text == a and merge3(base, base, b).text == b and merge3(base, a, base).text == a
