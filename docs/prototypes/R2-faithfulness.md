# R2 — Faithfulness verifier and its mutation harness

Status: prototype, measured. Code: `backend/atlas/pipeline/diary/verify.py` (+ `verify_text.py`,
`lexicon.py`, `lexicon_safe.txt`), `backend/atlas/eval/mutations.py`, tests and fixtures in
`backend/tests/verify/`. Reproduce the numbers below with:

```
cd backend && uv run python -m atlas.eval.mutations --seed 7 --show-skips
cd backend && uv run pytest tests/verify
```

## 1. Bottom line

- On 47 hand-written faithful blocks (3 days, 3 voices, 144 claims) the verifier flags none:
  **false positives 0/47 blocks, 0/144 claims**.
- On 1,374 seeded fabricated variants from 19 mutators it catches all of them: **recall 1.000**
  (seed 7; 1,393/1,393 on seed 42). Without the content-word backstop the same verifier reaches
  only **0.865**, with invented sentences at 0.61 and invented food at 0.71.
- On 76 hand-written adversarial fabrications it catches **70 (0.921)**; without the backstop 40
  (0.526). The six misses are sentences made only of neutral words ("We made it.").
- The cost: of 24 **true** sentences written without regard to the contract, the verifier rejects
  **12 (50%)**. The zero false-positive figure holds only for text written to the contract in §6.
- Two caveats on the headline recall. The mutators and the verifier have the same author, and two
  misses seen during development were fixed (§4), so 1.000 is an upper bound on this corpus, not a
  forecast. Several mutators have very few countable cases (part of day 4, elevation 4, remove
  hedge 5, reverse sequence 9).

## 2. Design

The verifier reads a finished `DiaryBlock` and the evidence rows it cites. It imports nothing from
the generator and uses no templates. It is deterministic and stdlib-only.

1. **Sentences and tokens.** The block is split into sentences (decimals, clock times and common
   abbreviations do not split). Claims are attributed to a sentence index and a character span.
2. **Claim extraction**, in this order: verbatim quotes; known names (longest match against
   evidence and gazetteer names); dates; clock times and quantities; parts of day; hedges;
   capitalised runs (proper nouns, with `de/du/da/of…` connectors); then every remaining word
   through the closed lexicons (activity/transport, food, weather, people, feeling, superlative,
   sequence).
3. **Coverage backstop (closed world).** Any word still unclaimed must be a function word or in the
   versioned safe vocabulary `lexicon_safe.txt` (about 90 words). Otherwise it becomes an
   `unlicensed` claim, which only a cited payload value or the cited note can license. Negation,
   "again/still/already/finally", comparatives, "he/she/you" and emoji are deliberately not safe.
4. **Checking** is against the evidence the block cites, never the whole trip. The rest of the trip
   is used only to word the reason ("known place but not cited (other day 2025-07-09)").
5. **Hedging (D4).** Evidence with confidence `low`, or a place with `approximate: true`, supports
   only a hedged claim; otherwise the reason is "needs hedge". A hedge never rescues a claim with
   no matching evidence.
6. **User testimony.** Blocks with origin `edited` or `user` return supported with a reason and are
   counted separately.

### Policies per claim kind

| Kind | Supported by | Tolerance / rule |
|---|---|---|
| place, locality, country | cited `place`, `locality`, `transport`/`movement` from/to, `border`, `first.value`, or a name in the cited note | Case, diacritics and "the" ignored. A short form is accepted only if the dropped words are generic ("Miradouro de") or the place's own locality ("Budapest-"), it keeps a distinctive word, and it is not the full name of another known place ("Lac Blanc" is rejected for "Refuge du Lac Blanc"). |
| direction | `from`/`to` roles | "from X" fails if X is only a destination in cited evidence; "to X" fails if X is only an origin. |
| time | cited `time` start/end, `transport` depart/arrive, or a time in the note | Exact minutes ±5 (hedged ±15); "half past/quarter to" ±7; bare hour ±10 (hedged ±20); "just after" 0…+25; "just before" −25…0; "by" −30…+5. Hours 1–12 without am/pm match either half of the day. |
| part of day | `time` part_of_day or time window; `visual` tags for sunrise/sunset/night | morning 05–12, afternoon 12–18, evening 17–23, night 21–05, noon 11:30–13:00; "all afternoon" needs 150 minutes inside the window. |
| duration | `duration`, `transport.duration_min`, `timezone_change` offset | Minutes: max(2 min, 5%); hours: max(10 min, 8%); hedged: max(5 or 15 min, 20%). "over/nearly" are one-sided. |
| distance | `movement.distance_km` | Half the last stated digit or 3% (6.2 → "6 km" passes, 7.8 → "7 km" fails); hedged 15%. Miles converted. |
| elevation | `elevation` ascent/max, feet converted | 3%; hedged 12%. |
| count | `photo_count`; number of cited transport legs of that mode; note | Exact; hedged 15%. Any other bare number is unsupported. |
| activity, transport | `kind`, mode, place category, visual tag, cited place name containing the word, or note | Meals need a meal-kind moment whose cited start time is in the window (lunch 11:00–15:30, dinner from 17:30, breakfast before 11:00), or the note. "Activity at Place" must be evidenced in one moment. |
| food, people, feeling | cited note only (food also a cited place name) | A feeling word must share another content word of its sentence with the same note ("The tram was delicious" fails). |
| weather | cited note; `snow` visual tag only | Nothing else supports weather. |
| first, superlative | cited `first` evidence whose value or text matches; else note | |
| sequence | cited times of the named moments, `sequence` evidence | Reversed order of two named moments fails; "back" needs the place in two cited moments. A lone "then" is checked against the previous block in `verify_diary`. |
| date | `block.day` | Weekday, month, day, year; "yesterday/tomorrow" always fail. |
| quote | cited note | Text in double quotes must be a verbatim span of the note. |
| citation | — | Unknown evidence id, evidence from another day, or no citations: block unsupported. |

**Why sentiment is strict.** Unsupported evaluation is the commonest embellishment and nothing but
the traveller's words can evidence it, so every feeling word needs the note. There is no whitelist
of "mild" feelings; neutral connective words live in the safe vocabulary instead.

### Public API

```python
extract_claims(text, *, style=None) -> list[Claim]
verify_block(block, evidence_by_id, *, known_places=None, style=None,
             coverage=True, previous=None) -> BlockVerdict      # VBlockVerdict
verify_diary(blocks, evidence, *, known_places=None, style=None, coverage=True) -> DiaryReport
```

`style` matters only for `person`: with `person="i"`, "we/our" is a people claim.
`coverage=False` exists for measurement only.

## 3. Fabrication rate, defined

Computed over generated blocks only (testimony blocks are counted in `testimony_blocks`).

- `fabrication_rate = unsupported_sentences / sentences`. A sentence is unsupported if at least
  one of its claims is unsupported, or its block has a citation failure.
- `claim_fabrication_rate = unsupported_claims / claims`. Citation failures count as claims.
- `unsupported_blocks` counts blocks with any unsupported claim.

The rate measures disagreement between text and cited evidence. It is not the rate of untrue
statements: wrong evidence makes a false sentence pass (§5).

## 4. Results

Fixture corpus: Lisbon city day (plain "I", 24h, metric, 16 blocks), alpine hike day (terse
fragments, 16 blocks), Vienna–Budapest–Bucharest rail day (chatty "we", 12h clock, miles, 15
blocks); 76 evidence rows, two notes with food and a feeling, three low-confidence rows.

Seed 7, two rounds per (block, mutator):

| mutator | n | detected | recall | skipped | recall, no backstop |
|---|---|---|---|---|---|
| place_decoy | 45 | 45 | 1.000 | 0 | 1.000 |
| place_other_day | 44 | 44 | 1.000 | 0 | 1.000 |
| locality_country | 16 | 16 | 1.000 | 0 | 1.000 |
| time_shift | 21 | 21 | 1.000 | 3 | 1.000 |
| part_of_day | 4 | 4 | 1.000 | 0 | 1.000 |
| distance | 16 | 16 | 1.000 | 0 | 1.000 |
| duration | 16 | 16 | 1.000 | 0 | 1.000 |
| elevation | 4 | 4 | 1.000 | 0 | 1.000 |
| count | 11 | 11 | 1.000 | 0 | 1.000 |
| activity_swap | 38 | 38 | 1.000 | 0 | 0.789 |
| insert_food | 185 | 185 | 1.000 | 0 | 0.708 |
| insert_weather | 175 | 175 | 1.000 | 0 | 0.966 |
| insert_companion | 175 | 175 | 1.000 | 0 | 0.926 |
| insert_feeling | 179 | 179 | 1.000 | 1 | 0.821 |
| invented_sentence | 185 | 185 | 1.000 | 0 | 0.611 |
| remove_hedge | 5 | 5 | 1.000 | 0 | 1.000 |
| claim_first | 151 | 151 | 1.000 | 0 | 1.000 |
| reverse_sequence | 9 | 9 | 1.000 | 0 | 1.000 |
| wrong_date | 95 | 95 | 1.000 | 0 | 1.000 |
| **TOTAL** | 1374 | 1374 | **1.000** | 4 | **0.865** |

| | with backstop | without backstop |
|---|---|---|
| Mutation recall, seed 7 | 1.000 (1374/1374) | 0.865 (1189/1374) |
| Mutation recall, seed 42 | 1.000 (1393/1393) | 0.873 (1216/1393) |
| False-positive blocks | 0/47 | 0/47 |
| False-positive claims | 0/144 | 0/140 |
| Adversarial recall (76 hand-written) | 0.921 (70/76) | 0.526 (40/76) |
| True off-contract sentences rejected (24) | 12 (50%) | 6 (25%) |

Targets from PLAN.md (recall ≥ 0.95, false positives ≤ 2%) are met on this corpus. The totals are
dominated by the five insertion mutators, which apply to every block; the unweighted mean over
mutators is also 1.000.

**Skipped, not counted (4):** three time shifts that landed within 50 minutes of another cited time
and could be true, and "It was delicious." appended to a block whose note says exactly that.

### Misses found during development and what was done

| Miss | Cause | Fix |
|---|---|---|
| "…at the hut at 21:00" (was 19:00) passed | The block also cited the note "In bed by nine", and the note's time supported the shifted one | A number from a note now supports a diary number only if a neighbouring content word also comes from that note |
| "What a day." passed in 5 blocks | "what", "a", "day" were all neutral | "what" removed from the function words; it survives only inside the hedge "what I think was" |
| "somewhere at Pastelaria Aloma" passed | The mutator left "somewhere" in place, so the text was still hedged | Mutator bug, fixed; not a verifier miss |
| "tram 15" passed (unit test) | Label numbers matched the "15" in "15:02" | Labels now match name-like fields only |
| "over 8 km" passed for 7.8 km (unit test) | One-sided tolerance allowed half a unit below | "over" now requires the true value to be at least the stated one |

### Adversarial misses (6 of 76), all still open

"Had it to myself." · "Swam across." · "It took a while." · "We made it." · "I spent a day there." ·
"I stayed until the end."

Each is built only from function words and safe verbs, so no word is available to flag. This is
the residual of the closed-world approach: a fabrication carried by implication rather than
vocabulary. Shrinking the safe list reduces it and raises the over-rejection rate; it cannot reach
zero.

### False positives

None on the fixtures. That is by construction: the fixtures were written to the contract, and one
fixture phrase ("what I think was") had to be added as a hedge after the "what" change. The
over-rejection figure is the honest one for free prose. The 12 rejected true sentences fail on
verbs outside the safe list ("rolled up", "hung around", "showed up", "departed", "gave", "ran",
"put"), on time forms the parser does not read ("ten past twelve", "five to midnight", "three and
a quarter hours"), on an unknown sentence-initial word ("Awake"), and once correctly-by-policy
("The train carried us over the border" cited only the border row, not the train).

## 5. Blind spots

1. **Wrong evidence.** If the geocoder picked the wrong restaurant with high confidence, the
   sentence naming it passes. The verifier measures agreement with evidence, not truth.
2. **Implication without vocabulary.** The six adversarial misses above.
3. **Binding inside one block.** A sentence that cites two moments can attach a true fact to the
   wrong one: a time to the wrong place, a feeling from the note to another thing the same note
   mentions ("The market was delicious"), a walk to the tram leg. Only "activity at Place" and
   reversed order are checked.
4. **Start versus end.** "Left at 10:19" passes when 10:19 is the arrival time; any cited time
   point supports any time claim. "Just after midnight" passes on a moment that ended at 00:10.
5. **Negation and counterfactuals** are rejected wholesale, not understood. "Did not swim" fails
   even when true, and would be the only way to state an absence.
6. **Numbers inside quotes** are checked only as a verbatim span of the note, not as quantities.
7. **Twelve-hour ambiguity.** "At eight" matches 08:00 and 20:00.
8. **Hedge scope is loose.** A hedge word within three tokens hedges the next claim, and "I think"
   hedges the whole sentence, so one hedge can cover a claim the writer stated flatly.
9. **Lowercased names** are treated as ordinary words licensed by the payload, so name checks such
   as the unsafe-short-form rule do not apply to them.
10. **Implied causality and comparison** pass if every word is licensed ("so", "because" is not
    safe, but "and" between two true facts can still suggest a link).
11. **English only**, and plain prose only. Idiom, irony and long subordinate clauses are either
    rejected or read word by word.
12. **Gazetteer dependence.** The unsafe-short-form rule only knows collisions that are in the
    evidence or in `known_places`.

## 6. The writer's contract

What the generator (deterministic or LLM) must obey for its text to pass.

1. **Cite everything, same day only.** Every block lists the evidence ids it uses. An unknown id,
   an id from another day, or no ids fails the block.
2. **One moment per sentence** where possible. Sentences spanning moments are only safe for
   explicit order ("X first, then Y") and transport ("from X to Y"), and must cite the `time` rows
   of every moment named.
3. **Vocabulary.** Outside names, numbers and words that appear in the cited payloads or note, use
   only function words and `lexicon_safe.txt` (version 1). The file is the contract; changing it
   changes the verifier version. No negation, no "again/still/already/finally/usual", no
   comparatives, no "he/she/you", no emoji.
4. **Names** exactly as in the evidence, capitalised. A short form may drop only a generic head
   ("Miradouro de") or the locality prefix.
5. **Numbers.** State times within 5 minutes of a cited start, end, departure or arrival; round
   distances to the last digit you print; otherwise hedge ("about", "around", "roughly", "nearly",
   "just over"). Write times as `HH:MM`, `H:MM am/pm`, "half past six", "quarter to four", or a bare
   hour after "at/by/around/just after".
6. **Hedge low confidence.** For evidence with confidence `low` or `approximate: true`, put
   "near", "somewhere near", "probably", "I think" or "what I think was" directly before the claim.
7. **Food, people, weather, feelings** only from the cited note, either as the note's own words
   next to what the note applies them to, or in double quotes as a verbatim span.
8. **Meals** need the moment's `time` row cited as well as its `kind`.
9. **"We"** only when `StyleProfile.person == "we"`.
10. **"First" and superlatives** only with a cited `first` row whose value or text they repeat.
11. **Dates** only for the block's own day; no "yesterday" or "tomorrow".

## 7. Changes requested in `models.py`

Not applied; the verifier currently subclasses the models to carry these.

1. `ClaimKind`: add `"unlicensed"`, `"quote"`, `"citation"`.
2. `Claim`: add `sentence: int = 0`, `start: int = 0`, `end: int = 0` (span in the block text).
3. `BlockVerdict`: add `reason: str = ""`, `testimony: bool = False`,
   `sentences: list[SentenceVerdict]` with
   `SentenceVerdict { index: int, text: str, supported: bool, verdicts: list[ClaimVerdict] }`.
4. Move `DiaryReport` and `Failure` from `verify.py` into `models.py` if other stages consume them.
5. Payload documentation for `EvidenceType`:
   - `transport`: add optional `line` (string, e.g. "28"); the fixtures use it for "tram 28".
   - `time`: state that `part_of_day` is one of morning, afternoon, evening, night, noon, sunrise,
     sunset.
   - `place`: state that `approximate: true` is treated like low confidence by the verifier.
   - `first`: state that `value` must be the literal word(s) the diary may repeat.
6. Consider `start_utc`/`end_utc` on `time` evidence. Order checks currently compare local clock
   times and are unreliable across a timezone change or midnight.

## 8. Not done

- Lint: `ruff check` reports 24 style findings in the new files; none were fixed.
- No evaluation on generator or LLM output, since neither exists yet. The over-rejection figure
  suggests an unconstrained LLM realizer would lose roughly half its true sentences to the gate
  until its prompt enforces the contract.
- No role binding of times (blind spot 4) and no general moment binding (blind spot 3).
