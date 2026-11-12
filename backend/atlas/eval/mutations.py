"""Mutation harness: measures whether the faithfulness verifier actually catches fabrications.

Takes faithful (block, evidence) pairs, produces fabricated variants with labelled mutators,
runs the verifier on each and reports detection recall per mutator plus the false-positive rate
on the untouched blocks.

Independence: this module finds its mutation sites with its own regexes and its own small
tables. It imports the verifier only to call ``verify_block`` — never its lexicons or parsers —
so a gap in the verifier's vocabulary is not mirrored here.

A mutation is only counted when it (a) changes the text and (b) is false by construction.
Variants that might accidentally remain true (e.g. a shifted time that lands on another cited
time) are skipped and logged, never counted in the denominator.

Run:  uv run python -m atlas.eval.mutations [--seed 7] [--markdown]
"""

from __future__ import annotations

import argparse
import importlib.util
import random
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from atlas.pipeline.diary.verify import verify_block
from atlas.pipeline.models import DiaryBlock, Evidence, StyleProfile


@dataclass
class Mutant:
    mutator: str
    block_id: str
    text: str
    detail: str


@dataclass
class Skip:
    mutator: str
    block_id: str
    reason: str


@dataclass
class Case:
    """One faithful block with what the mutators need to know about its surroundings."""

    block: DiaryBlock
    cited: list[Evidence]
    style: StyleProfile | None
    all_evidence: list[Evidence]


@dataclass
class MutatorResult:
    n: int = 0
    detected: int = 0
    skipped: int = 0
    missed: list[Mutant] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return self.detected / self.n if self.n else float("nan")


@dataclass
class HarnessResult:
    seed: int
    coverage: bool
    per_mutator: dict[str, MutatorResult]
    skips: list[Skip]
    faithful_blocks: int
    false_positive_blocks: list[tuple[str, str]]          # (block id, reason)
    faithful_claims: int
    false_positive_claims: int

    @property
    def n(self) -> int:
        return sum(r.n for r in self.per_mutator.values())

    @property
    def detected(self) -> int:
        return sum(r.detected for r in self.per_mutator.values())

    @property
    def recall(self) -> float:
        return self.detected / self.n if self.n else float("nan")

    @property
    def fp_block_rate(self) -> float:
        return len(self.false_positive_blocks) / self.faithful_blocks if self.faithful_blocks else 0.0

    @property
    def fp_claim_rate(self) -> float:
        return self.false_positive_claims / self.faithful_claims if self.faithful_claims else 0.0


# ---------------------------------------------------------------------------------------------
# pools (written without reference to the verifier's lexicons, on purpose)
# ---------------------------------------------------------------------------------------------

DECOY_POIS = [
    "Miradouro da Graça", "Castelo de São Jorge", "Mercado da Ribeira Nova", "Café A Brasileira",
    "Refuge de Bellachat", "Col des Montets", "Lac des Chéserys", "Aiguillette des Houches",
    "Wien Westbahnhof", "Budapest-Nyugati", "Gara Basarab", "Bahnhof Meidling", "Stația Brașov",
    "Praça do Comércio", "Torre de Belém", "Halászbástya",
]
DECOY_LOCALITIES = ["Porto", "Sintra", "Zermatt", "Annecy", "Bratislava", "Prague", "Zagreb", "İstanbul",
                    "Kraków", "Salzburg"]
DECOY_COUNTRIES = ["Spain", "Italy", "Switzerland", "Slovakia", "Serbia", "Bulgaria", "Croatia", "Czechia"]

FOODS = [
    "a pastel de nata", "goulash", "a plate of dumplings", "fresh oysters", "a slice of cheesecake",
    "pierogi", "a bowl of ramen", "lángos", "a kebab", "two scoops of pistachio gelato", "a bifana",
    "a francesinha", "chimney cake", "a pretzel", "tartiflette", "rösti", "a cinnamon bun", "ceviche",
    "pad thai", "octopus salad",
]
WEATHER_SENTENCES = [
    "It rained all morning.", "The sun was out.", "A cold wind blew.", "Fog rolled in.", "It was warm.",
    "Clear skies.", "It drizzled.", "Sweltering.", "A storm passed.", "Cloudless.", "Hot and humid.",
    "The heat was something else.", "It poured.", "Blue skies all day.", "Bitterly cold.", "Not a cloud.",
]
COMPANION_TAILS = [" with Ana", " with my brother", " with Tomás and Inês", " with a friendly waiter",
                   " with two Germans", " with the others", " with a guide"]
COMPANION_SENTENCES = [
    "We met two Germans.", "A friendly waiter helped.", "My brother came along.", "Ana joined.",
    "The guide was waiting.", "Chatted with a local.", "A stranger took the photo.", "Marta was there too.",
    "An old man waved.", "The conductor checked the tickets.",
]
FEELING_SENTENCES = [
    "Loved it.", "The best view of the trip.", "Breathtaking.", "I was exhausted.", "Totally worth it.",
    "What a day.", "Magical.", "Pure bliss.", "A real highlight.", "Unforgettable.", "So peaceful.",
    "It felt like home.", "Could have stayed forever.", "Heaven.", "Not bad at all.",
    "Underwhelming, frankly.", "A bit of a slog.", "My legs were jelly.", "Sublime.", "It was delicious.",
]
INVENTED_SENTENCES = [
    "A street musician played fado on the corner.", "The queue stretched around the block.",
    "A marmot whistled from the rocks.", "The ticket inspector stamped our passes.",
    "Church bells rang across the valley.", "A cat slept on the windowsill.",
    "The waiter recommended the house wine.", "We missed the earlier connection.",
    "The path was washed out in places.", "Laundry hung between the balconies.",
    "A dog followed us for a while.", "The lift was out of order.", "Fishermen were mending nets.",
    "The museum was closed for renovation.", "Somebody was selling roasted chestnuts.",
    "The dining car had run out of everything.", "Paragliders drifted overhead.",
    "The hostel had no hot water.", "A wedding party spilled out of the church.",
    "The bridge was lit up in blue.", "I bought a postcard for my mother.", "The bakery had sold out.",
    "Two ibex stood on the ridge.", "The square was full of pigeons.", "A busker sang in three languages.",
    "The carriage smelled of oranges.", "We got lost twice.", "The tiles were chipped and faded.",
    "Kids were jumping off the pier.", "The cable car was not running.", "A thunderstorm cut the day short.",
    "I dropped my phone in the fountain.", "The border guard barely looked up.", "The elevator was packed.",
    "A man in a blue coat gave us directions.", "The cheese came from the farm next door.",
    "Dolphins followed the boat.", "The room overlooked a courtyard.", "My boots were soaked through.",
    "The fountain had been drained.",
]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
          "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
_TENS = {30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"}
_FACTORS = [1.5, 2.0, 3.0, 0.5, 0.34]


def _to_words(n: int) -> str:
    if 0 <= n <= 20:
        return _WORDS[n]
    if n < 100:
        t, u = n // 10 * 10, n % 10
        tens = "twenty" if t == 20 else _TENS[t]
        return tens if u == 0 else f"{tens}-{_WORDS[u]}"
    return str(n)


def _from_words(w: str) -> int | None:
    w = w.lower()
    if w in _WORDS:
        return _WORDS.index(w)
    for k, v in _TENS.items():
        if v == w:
            return k
    return None


def _keep_case(old: str, new: str) -> str:
    return new[:1].upper() + new[1:] if old[:1].isupper() else new


def _sub_at(text: str, start: int, end: int, new: str) -> str:
    return text[:start] + new + text[end:]


def _payload_strings(evs: Iterable[Evidence]) -> list[str]:
    out: list[str] = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    for e in evs:
        walk(e.payload)
    return out


def _names(evs: Iterable[Evidence]) -> dict[str, str]:
    """name → class ("poi" | "locality" | "country") for every name in these evidence rows."""
    out: dict[str, str] = {}
    evs = list(evs)
    for e in evs:
        p = e.payload
        for key, cls in (("country", "country"), ("from_country", "country"), ("to_country", "country"),
                         ("locality", "locality")):
            if isinstance(p.get(key), str):
                out[p[key]] = cls
    for e in evs:
        p = e.payload
        keys = ("name",) if e.type == "place" else (("from", "to") if e.type in ("transport", "movement") else ())
        for key in keys:
            if isinstance(p.get(key), str) and p[key] not in out:
                out[p[key]] = "poi"
    return out


def _sites(text: str, names: dict[str, str], cls: Sequence[str]) -> list[tuple[int, int, str]]:
    """Literal, non-overlapping occurrences of names of the wanted classes (longest first)."""
    taken: list[tuple[int, int, str]] = []
    for name in sorted(names, key=len, reverse=True):
        for m in re.finditer(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text):
            if not any(a < m.end() and m.start() < b for a, b, _ in taken):
                taken.append((m.start(), m.end(), name))
    return sorted(t for t in taken if names[t[2]] in cls)


def _minutes_in(evs: Iterable[Evidence]) -> list[int]:
    out = []
    for s in _payload_strings(evs):
        for m in re.finditer(r"\b(\d{1,2}):(\d{2})\b", s):
            out.append(int(m.group(1)) * 60 + int(m.group(2)))
    return out


def _voice_sentence(case: Case, i_form: str, we_form: str, terse: str) -> str:
    st = case.style
    if st is not None and st.fragments >= 0.5:
        return terse
    return we_form if st is not None and st.person == "we" else i_form


def _append(text: str, sentence: str) -> str:
    return text.rstrip() + " " + sentence


# ---------------------------------------------------------------------------------------------
# mutators
# ---------------------------------------------------------------------------------------------

Out = list[Mutant | Skip]


def _m(name: str, case: Case, text: str, detail: str) -> Mutant | Skip:
    if text == case.block.text:
        return Skip(name, case.block.id, "degenerate: text unchanged")
    return Mutant(name, case.block.id, text, detail)


def mut_place_decoy(case: Case, rng: random.Random) -> Out:
    out: Out = []
    known = set(_names(case.all_evidence))
    pool = [d for d in DECOY_POIS if d not in known]
    for a, b, name in _sites(case.block.text, _names(case.cited), ["poi"]):
        new = rng.choice(pool)
        out.append(_m("place_decoy", case, _sub_at(case.block.text, a, b, new), f"{name} → {new}"))
    return out


def mut_place_other_day(case: Case, rng: random.Random) -> Out:
    out: Out = []
    cited_strings = " | ".join(_payload_strings(case.cited))
    other = sorted(n for n, c in _names(e for e in case.all_evidence if e.day != case.block.day).items()
                   if c == "poi" and n not in cited_strings)
    for a, b, name in _sites(case.block.text, _names(case.cited), ["poi"]):
        new = rng.choice(other)
        out.append(_m("place_other_day", case, _sub_at(case.block.text, a, b, new), f"{name} → {new}"))
    return out


def mut_locality_country(case: Case, rng: random.Random) -> Out:
    out: Out = []
    names = _names(case.cited)
    cited_strings = " | ".join(_payload_strings(case.cited))
    other = _names(e for e in case.all_evidence if e.day != case.block.day)
    for a, b, name in _sites(case.block.text, names, ["locality", "country"]):
        cls = names[name]
        pool = (DECOY_LOCALITIES if cls == "locality" else DECOY_COUNTRIES) + sorted(
            n for n, c in other.items() if c == cls)
        pool = [p for p in pool if p not in cited_strings]
        new = rng.choice(pool)
        out.append(_m("locality_country", case, _sub_at(case.block.text, a, b, new), f"{name} → {new}"))
    return out


_CLOCK_RE = re.compile(r"\b(\d{1,2}):(\d{2})(\s?[ap]m)?")
_WORD_HOUR_RE = re.compile(
    r"\b(?:(?:just |shortly )?(?:after|before)|by|around|about|at|past|to) "
    r"(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b(?! (?:hours|minutes|km|miles|and|photos))",
    re.IGNORECASE)


def mut_time_shift(case: Case, rng: random.Random) -> Out:
    out: Out = []
    text = case.block.text
    cited = _minutes_in(case.cited)

    def still_true(cands: list[int]) -> bool:
        return any(min(abs(c - t), 1440 - abs(c - t)) <= 50 for c in cands for t in cited)

    for m in _CLOCK_RE.finditer(text):
        h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
        shift = rng.choice([-3, -2, -1, 1, 2, 3])
        if ap:
            h24 = h % 12 + (12 if "p" in ap else 0)
            n24 = (h24 + shift) % 24
            new = f"{(n24 % 12) or 12}:{mi:02d}{ap[:-2]}{'pm' if n24 >= 12 else 'am'}"
            cands = [n24 * 60 + mi]
        else:
            n24 = (h + shift) % 24
            new = f"{n24:02d}:{mi:02d}" if len(m.group(1)) == 2 else f"{n24}:{mi:02d}"
            cands = [n24 * 60 + mi]
        if still_true(cands):
            out.append(Skip("time_shift", case.block.id, f"{m.group()} → {new} may still be true"))
            continue
        out.append(_m("time_shift", case, _sub_at(text, m.start(), m.end(), new), f"{m.group()} → {new}"))
    for m in _WORD_HOUR_RE.finditer(text):
        h = _from_words(m.group(1)) or 0
        shift = rng.choice([-3, -2, 2, 3])
        nh = (h - 1 + shift) % 12 + 1
        cands = [nh % 12 * 60 + d for d in (0, 15, 30, -15)] + [nh % 12 * 60 + 720 + d for d in (0, 15, 30, -15)]
        if cited and still_true(cands):
            out.append(Skip("time_shift", case.block.id, f"{m.group(1)} → {_WORDS[nh]} may still be true"))
            continue
        new = _keep_case(m.group(1), _WORDS[nh])
        out.append(_m("time_shift", case, _sub_at(text, m.start(1), m.end(1), new), f"{m.group(1)} → {new}"))
    return out


_PART_WINDOWS = {"morning": (300, 720), "afternoon": (720, 1080), "evening": (1020, 1380)}


def mut_part_of_day(case: Case, rng: random.Random) -> Out:
    out: Out = []
    text = case.block.text
    cited = _minutes_in(case.cited)
    tags = " ".join(_payload_strings(case.cited)).lower()
    for m in re.finditer(r"\b(morning|afternoon|evening|sunrise|sunset)\b", text, re.IGNORECASE):
        old = m.group(1).lower()
        if old in ("sunrise", "sunset"):
            new = "sunset" if old == "sunrise" else "sunrise"
            if new in tags or "dusk" in tags or "dawn" in tags:
                out.append(Skip("part_of_day", case.block.id, f"{old} → {new} may still be true"))
                continue
        else:
            options = [p for p in _PART_WINDOWS if p != old and not any(
                _PART_WINDOWS[p][0] - 45 <= t <= _PART_WINDOWS[p][1] + 45 for t in cited)]
            if not options:
                out.append(Skip("part_of_day", case.block.id, f"no part of day is certainly false instead of {old}"))
                continue
            new = rng.choice(options)
        out.append(_m("part_of_day", case, _sub_at(text, m.start(), m.end(), _keep_case(m.group(1), new)),
                      f"{old} → {new}"))
    return out


_NUM = r"(\d[\d,]*(?:\.\d+)?|" + "|".join(_WORDS[1:] + list(_TENS.values())) + r")"


def _scale(raw: str, rng: random.Random) -> tuple[str, float] | None:
    """Scale a number literal by ×1.5–3 or ÷2–3, keeping its surface style. Returns (new, ratio)."""
    f = rng.choice(_FACTORS)
    w = _from_words(raw)
    if w is not None:
        n = max(1, round(w * f))
        if n == w:
            n = w * 2
        return _keep_case(raw, _to_words(n)), n / w
    plain = raw.replace(",", "")
    try:
        v = float(plain)
    except ValueError:
        return None
    if v == 0:
        return None
    if "." in plain:
        dec = len(plain.split(".")[1])
        nv = round(v * f, dec)
        new = f"{nv:.{dec}f}"
    else:
        nv = max(1, round(v * f))
        if nv == v:
            nv = v * 2
        new = f"{int(nv):,}" if "," in raw else str(int(nv))
    return new, nv / v


def _quantity_mutator(name: str, pattern: str) -> Callable[[Case, random.Random], Out]:
    rx = re.compile(pattern, re.IGNORECASE)

    def run(case: Case, rng: random.Random) -> Out:
        out: Out = []
        text = case.block.text
        for m in rx.finditer(text):
            if "“" in text[:m.start()] and "”" in text[m.end():]:
                continue                       # do not edit inside a verbatim quote
            r = _scale(m.group(1), rng)
            if r is None:
                continue
            new, ratio = r
            if 0.72 < ratio < 1.4:
                out.append(Skip(name, case.block.id, f"{m.group(1)} → {new}: change too small to be certainly false"))
                continue
            out.append(_m(name, case, _sub_at(text, m.start(1), m.end(1), new), f"{m.group()} → {new}"))
        return out

    return run


mut_distance = _quantity_mutator("distance", _NUM + r"\s?(?:km|kilometres|kilometers|miles|mi)\b")
mut_elevation = _quantity_mutator("elevation", _NUM + r"\s?m\b(?! in\b)")
mut_count = _quantity_mutator("count", r"\b" + _NUM + r" (?:photos|trains|pictures)\b")
_mut_duration_simple = _quantity_mutator(
    "duration", r"\b" + _NUM + r"(?: and a half)?[\s-]?(?:minutes|minute|mins|min|hours|hour|h)\b")


def mut_duration(case: Case, rng: random.Random) -> Out:
    out = _mut_duration_simple(case, rng)
    text = case.block.text
    for m in re.finditer(r"\b(an hour)\b", text):
        n = rng.choice([3, 4, 5])
        out.append(_m("duration", case, _sub_at(text, m.start(), m.end(), f"{_to_words(n)} hours"),
                      f"an hour → {n} hours"))
    return out


# (pattern, replacement, evidence words that would make the replacement true)
_ACTIVITY_RULES: list[tuple[str, list[str], list[str]]] = [
    (r"\bwalked\b", ["took the tram", "cycled", "took a taxi"], ["tram", "bike", "car"]),
    (r"\b[Tt]he walk\b", ["the bus ride", "the boat trip"], ["bus", "boat"]),
    (r"\b[Ll]unch\b", ["dinner", "breakfast"], []),
    (r"\b[Dd]inner\b", ["breakfast", "lunch"], []),
    (r"\b[Hh]iked\b", ["drove", "cycled", "rode a horse"], ["car", "bike"]),
    (r"\b[Ss]wam\b", ["sailed", "fished", "kayaked"], ["boat"]),
    (r"\btrains?\b", ["bus", "ferry", "flight"], ["bus", "boat", "flight"]),
    (r"\btram\b", ["ferry", "bus", "funicular"], ["boat", "bus"]),
    (r"\b[Cc]offee\b", ["beer", "wine", "cocktails"], ["bar"]),
    (r"\bclimbing\b", ["cycling", "skiing"], ["bike"]),
    (r"\bthe trail\b", ["the motorway", "horseback"], []),
    (r"\bhut\b", ["hotel", "campsite", "villa"], ["hotel", "campsite"]),
    (r"\bviewpoint\b", ["museum", "beach", "cathedral"], ["museum", "beach", "church"]),
    (r"\b[Tt]he market\b", ["the museum", "the cathedral"], ["museum", "church"]),
    (r"\b[Tt]he lake\b", ["the beach", "the glacier"], ["beach"]),
    (r"\bthe border\b", ["the river", "the equator"], []),
]


def mut_activity_swap(case: Case, rng: random.Random) -> Out:
    out: Out = []
    text = case.block.text
    truth = " ".join(_payload_strings(case.cited)).lower()
    for pattern, repls, makes_true in _ACTIVITY_RULES:
        for m in re.finditer(pattern, text):
            if "“" in text[:m.start()] and "”" in text[m.end():]:
                continue
            new = rng.choice(repls)
            if m.group().endswith("s") and m.group().lower().startswith("train"):
                new = {"bus": "buses", "ferry": "ferries", "flight": "flights"}[new]
            if any(re.search(r"\b" + w + r"\b", truth) for w in makes_true) or re.search(
                    r"\b" + re.escape(new.split()[-1]) + r"\b", truth):
                out.append(Skip("activity_swap", case.block.id, f"{m.group()} → {new} may still be true"))
                continue
            out.append(_m("activity_swap", case, _sub_at(text, m.start(), m.end(), _keep_case(m.group(), new)),
                          f"{m.group()} → {new}"))
    return out


def _insert_pool(name: str, pool_fn: Callable[[Case, random.Random], list[str]], k: int = 2):
    def run(case: Case, rng: random.Random) -> Out:
        out: Out = []
        note_text = " ".join(str(e.payload.get("text", "")) for e in case.cited if e.type == "note").lower()
        for sentence in pool_fn(case, rng)[:k]:
            words = [w for w in re.findall(r"[^\W\d_]+", sentence.lower()) if len(w) > 3]
            if note_text and words and all(w in note_text for w in words):
                out.append(Skip(name, case.block.id, f"{sentence!r} is in the traveller's note"))
                continue
            text = sentence if sentence.startswith("@") else _append(case.block.text, sentence)
            out.append(_m(name, case, text.lstrip("@"), f"+ {sentence.lstrip('@')!r}"))
        return out

    return run


def _food_pool(case: Case, rng: random.Random) -> list[str]:
    foods = rng.sample(FOODS, 2)
    return [_voice_sentence(case, f"I had {f}.", f"We had {f}.", f"Ate {f}.") for f in foods]


def _companion_pool(case: Case, rng: random.Random) -> list[str]:
    text = case.block.text.rstrip()
    tail = rng.choice(COMPANION_TAILS)
    first = "@" + (text[:-1] + tail + "." if text.endswith(".") else text + tail)
    return [first, rng.choice(COMPANION_SENTENCES)]


def _first_pool(case: Case, rng: random.Random) -> list[str]:
    if any(e.type == "first" for e in case.cited):
        return []
    names = [n for n, c in _names(e for e in case.all_evidence if e.day == case.block.day).items() if c != "poi"]
    place = rng.choice(sorted(names)) if names else "town"
    me = "Our" if case.style is not None and case.style.person == "we" else "My"
    return rng.sample([f"{me} first time in {place}.", "A first for me.", "The first of the trip.",
                       f"{me} first ever visit.", "First time for everything."], 2)


def _invented_pool(case: Case, rng: random.Random) -> list[str]:
    picks = rng.sample(INVENTED_SENTENCES, 2)
    return [picks[0], "@" + picks[1] + " " + case.block.text]      # one appended, one prepended


mut_insert_food = _insert_pool("insert_food", _food_pool)
mut_insert_weather = _insert_pool("insert_weather", lambda c, r: r.sample(WEATHER_SENTENCES, 2))
mut_insert_companion = _insert_pool("insert_companion", _companion_pool)
mut_insert_feeling = _insert_pool("insert_feeling", lambda c, r: r.sample(FEELING_SENTENCES, 2))
mut_invented_sentence = _insert_pool("invented_sentence", _invented_pool)
mut_claim_first = _insert_pool("claim_first", _first_pool)

_HEDGE_RULES = [
    (r"\bwhat I think was ", ""), (r"\bwhat we think was ", ""), (r",? I think\b", ""), (r"\bprobably ", ""),
    (r"\bsomewhere near ", "at "), (r"(?<!somewhere )\bnear ", "at "), (r"\bwhat looked like ", ""), (r"\bmaybe ", ""),
]


def mut_remove_hedge(case: Case, rng: random.Random) -> Out:
    """Only for claims resting on low-confidence / approximate evidence (DECISIONS D4)."""
    out: Out = []
    if not any(e.confidence == "low" or e.payload.get("approximate") for e in case.cited):
        return out
    text = case.block.text
    for pattern, repl in _HEDGE_RULES:
        for m in re.finditer(pattern, text):
            if "“" in text[:m.start()] and "”" in text[m.end():]:
                continue
            out.append(_m("remove_hedge", case, _sub_at(text, m.start(), m.end(), repl), f"- {m.group().strip()!r}"))
    return out


def mut_reverse_sequence(case: Case, rng: random.Random) -> Out:
    out: Out = []
    text = case.block.text
    sites = _sites(text, _names(case.cited), ["poi", "locality", "country"])
    for (a1, b1, n1), (a2, b2, n2) in zip(sites, sites[1:]):
        if n1 == n2:
            continue
        between = text[b1:a2]
        lead = text[max(0, a1 - 6):a1]
        directional = re.fullmatch(r" (in)?to ", between) and lead.endswith("from ")
        ordered = re.search(r"\b(then|later|before|after)\b", between)
        if directional or ordered:
            new = text[:a1] + n2 + between + n1 + text[b2:]
            out.append(_m("reverse_sequence", case, new, f"swap {n1} ⇄ {n2}"))
    for m in re.finditer(r" (before|after) (?=[A-Z])", text):
        if len(sites) >= 2:
            new_word = "after" if m.group(1) == "before" else "before"
            out.append(_m("reverse_sequence", case, _sub_at(text, m.start(1), m.end(1), new_word),
                          f"{m.group(1)} → {new_word}"))
    return out


def mut_wrong_date(case: Case, rng: random.Random) -> Out:
    out: Out = []
    text = case.block.text
    day = case.block.day
    hit = False
    for m in re.finditer("|".join(WEEKDAYS), text):
        new = rng.choice([w for w in WEEKDAYS if w != m.group()])
        out.append(_m("wrong_date", case, _sub_at(text, m.start(), m.end(), new), f"{m.group()} → {new}"))
        hit = True
    for m in re.finditer(r"\b(" + "|".join(MONTHS) + r")\b", text):
        if re.search(r"\d", text[max(0, m.start() - 4):m.end() + 4]):
            new = rng.choice([x for x in MONTHS if x != m.group()])
            out.append(_m("wrong_date", case, _sub_at(text, m.start(), m.end(), new), f"{m.group()} → {new}"))
            hit = True
    for m in re.finditer(r"(?:(?<=" + MONTHS[day.month - 1] + r" )\d{1,2}\b)|(?:\b\d{1,2}(?= " + MONTHS[day.month - 1] + "))",
                         text):
        d = int(m.group())
        new = str((d + rng.choice([1, 2, 5, 9]) - 1) % 28 + 1)
        if int(new) != d:
            out.append(_m("wrong_date", case, _sub_at(text, m.start(), m.end(), new), f"day {d} → {new}"))
    if not hit:
        wrong = rng.choice([w for i, w in enumerate(WEEKDAYS) if i != day.weekday()])
        out.append(_m("wrong_date", case, _append(text, f"That was a {wrong}."), f"+ wrong weekday {wrong}"))
    return out


MUTATORS: dict[str, Callable[[Case, random.Random], Out]] = {
    "place_decoy": mut_place_decoy,
    "place_other_day": mut_place_other_day,
    "locality_country": mut_locality_country,
    "time_shift": mut_time_shift,
    "part_of_day": mut_part_of_day,
    "distance": mut_distance,
    "duration": mut_duration,
    "elevation": mut_elevation,
    "count": mut_count,
    "activity_swap": mut_activity_swap,
    "insert_food": mut_insert_food,
    "insert_weather": mut_insert_weather,
    "insert_companion": mut_insert_companion,
    "insert_feeling": mut_insert_feeling,
    "invented_sentence": mut_invented_sentence,
    "remove_hedge": mut_remove_hedge,
    "claim_first": mut_claim_first,
    "reverse_sequence": mut_reverse_sequence,
    "wrong_date": mut_wrong_date,
}


# ---------------------------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------------------------


def make_cases(blocks: Sequence[DiaryBlock], evidence: Sequence[Evidence],
               style: StyleProfile | None) -> list[Case]:
    by_id = {e.id: e for e in evidence}
    return [Case(b, [by_id[i] for i in b.evidence_ids if i in by_id], style, list(evidence)) for b in blocks]


def generate(cases: Sequence[Case], seed: int, rounds: int = 2) -> tuple[list[tuple[Case, Mutant]], list[Skip]]:
    """Deterministic: the RNG for (block, mutator, round) depends only on the seed and those names."""
    mutants: list[tuple[Case, Mutant]] = []
    skips: list[Skip] = []
    seen: set[tuple[str, str, str]] = set()
    for case in cases:
        for name, fn in MUTATORS.items():
            for rnd in range(rounds):
                rng = random.Random(f"{seed}/{case.block.id}/{name}/{rnd}")
                for item in fn(case, rng):
                    if isinstance(item, Skip):
                        if rnd == 0:
                            skips.append(item)
                        continue
                    key = (case.block.id, name, item.text)
                    if key not in seen:
                        seen.add(key)
                        mutants.append((case, item))
    return mutants, skips


def run_harness(cases: Sequence[Case], *, seed: int = 7, coverage: bool = True,
                known_places: Sequence[str] | None = None, rounds: int = 2) -> HarnessResult:
    all_ev = {e.id: e for c in cases for e in c.all_evidence}
    per: dict[str, MutatorResult] = {name: MutatorResult() for name in MUTATORS}
    fp_blocks: list[tuple[str, str]] = []
    claims = fp_claims = 0
    for c in cases:
        v = verify_block(c.block, all_ev, known_places=known_places, style=c.style, coverage=coverage)
        claims += len(v.verdicts)
        fp_claims += sum(not x.supported for x in v.verdicts)
        if not v.supported:
            fp_blocks.append((c.block.id, v.reason))
    faithful_ok = {c.block.id for c in cases} - {b for b, _ in fp_blocks}
    mutants, skips = generate(cases, seed, rounds)
    for case, m in mutants:
        if case.block.id not in faithful_ok:
            continue                   # a block that already fails cannot measure detection
        r = per[m.mutator]
        r.n += 1
        v = verify_block(case.block.model_copy(update={"text": m.text}), all_ev, known_places=known_places,
                         style=case.style, coverage=coverage)
        if v.supported:
            r.missed.append(m)
        else:
            r.detected += 1
    for s in skips:
        per[s.mutator].skipped += 1
    return HarnessResult(seed, coverage, per, skips, len(cases), fp_blocks, claims, fp_claims)


def run_texts(items: Sequence[tuple[Case, str]], *, coverage: bool = True,
              known_places: Sequence[str] | None = None) -> tuple[int, list[tuple[str, str]]]:
    """Verify hand-written texts against a block's citations. Returns (n, [(block id, text) that PASSED])."""
    passed = []
    for case, text in items:
        all_ev = {e.id: e for e in case.all_evidence}
        v = verify_block(case.block.model_copy(update={"text": text}), all_ev, known_places=known_places,
                         style=case.style, coverage=coverage)
        if v.supported:
            passed.append((case.block.id, text))
    return len(items), passed


def format_table(with_cov: HarnessResult, without_cov: HarnessResult | None = None, markdown: bool = False) -> str:
    rows = []
    head = ["mutator", "n", "detected", "recall", "skipped"] + (["recall (no backstop)"] if without_cov else [])
    for name, r in with_cov.per_mutator.items():
        row = [name, str(r.n), str(r.detected), f"{r.recall:.3f}" if r.n else "–", str(r.skipped)]
        if without_cov:
            w = without_cov.per_mutator[name]
            row.append(f"{w.recall:.3f}" if w.n else "–")
        rows.append(row)
    total = ["TOTAL", str(with_cov.n), str(with_cov.detected), f"{with_cov.recall:.3f}", str(len(with_cov.skips))]
    if without_cov:
        total.append(f"{without_cov.recall:.3f}")
    rows.append(total)
    if markdown:
        lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
        lines += ["| " + " | ".join(r) + " |" for r in rows]
        return "\n".join(lines)
    widths = [max(len(x[i]) for x in [head] + rows) for i in range(len(head))]
    fmt = lambda r: "  ".join(c.ljust(w) for c, w in zip(r, widths))  # noqa: E731
    return "\n".join([fmt(head), fmt(["-" * w for w in widths])] + [fmt(r) for r in rows])


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def load_fixture_cases(fixtures_dir: Path | None = None):
    """Load the hand-written fixture days (tests/verify/fixtures). Returns (cases by day, module, adversarial)."""
    fixtures_dir = fixtures_dir or Path(__file__).resolve().parents[2] / "tests" / "verify" / "fixtures"
    trips = _load_module(fixtures_dir / "trips.py", "_atlas_fixture_trips")
    adv_path = fixtures_dir / "adversarial.py"
    adv = _load_module(adv_path, "_atlas_fixture_adversarial") if adv_path.exists() else None
    ev = trips.evidence()
    cases = {k: make_cases(trips.blocks(k), ev, trips.STYLES[k]) for k in trips.DAY_KEYS}
    return cases, trips, adv


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--fixtures", type=Path, default=None)
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--show-skips", action="store_true")
    args = ap.parse_args(argv)
    by_day, trips, adv = load_fixture_cases(args.fixtures)
    cases = [c for cs in by_day.values() for c in cs]
    on = run_harness(cases, seed=args.seed, coverage=True, known_places=trips.KNOWN_PLACES, rounds=args.rounds)
    off = run_harness(cases, seed=args.seed, coverage=False, known_places=trips.KNOWN_PLACES, rounds=args.rounds)
    print(f"seed={args.seed}  faithful blocks={on.faithful_blocks}  claims={on.faithful_claims}")
    print(format_table(on, off, args.markdown))
    for label, r in (("with backstop", on), ("without backstop", off)):
        print(f"\n{label}: recall {r.recall:.3f} ({r.detected}/{r.n});  FP blocks {len(r.false_positive_blocks)}/"
              f"{r.faithful_blocks} = {r.fp_block_rate:.3f};  FP claims {r.false_positive_claims}/{r.faithful_claims}"
              f" = {r.fp_claim_rate:.3f}")
        for bid, reason in r.false_positive_blocks:
            print(f"   FALSE POSITIVE {bid}: {reason}")
    print("\nmissed mutations (with backstop):")
    for name, r in on.per_mutator.items():
        for m in r.missed:
            print(f"   [{name}] {m.block_id} ({m.detail}): {m.text}")
    if args.show_skips:
        print("\nskipped (not counted):")
        for s in on.skips:
            print(f"   [{s.mutator}] {s.block_id}: {s.reason}")
    if adv is not None:
        case_by_id = {c.block.id: c for c in cases}
        for title, rows, want_pass in (("adversarial fabrications", adv.ADVERSARIAL, False),
                                       ("faithful but off-contract paraphrases", adv.OFF_CONTRACT_TRUE, True)):
            items = []
            for bid, text, mode in rows:
                c = case_by_id[bid]
                items.append((c, text if mode == "replace" else _append(c.block.text, text)))
            for cov in (True, False):
                n, passed = run_texts(items, coverage=cov, known_places=trips.KNOWN_PLACES)
                tag = "with backstop" if cov else "without backstop"
                if want_pass:
                    print(f"\n{title} ({tag}): accepted {len(passed)}/{n} (over-rejection {(n - len(passed)) / n:.3f})")
                else:
                    print(f"\n{title} ({tag}): caught {n - len(passed)}/{n} = recall {(n - len(passed)) / n:.3f}")
                    if cov:
                        for bid, text in passed:
                            print(f"   MISSED {bid}: {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
