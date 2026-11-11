"""Stage 5 verify gate: an independent faithfulness checker for diary text.

It reads finished English prose and structured evidence — nothing else. It shares no code,
templates or word lists with the generator. Deterministic, stdlib only.

Model (closed world, conservative):
  1. split the block into sentences, tokenise;
  2. extract every checkable claim (names, times, measures, counts, activities, food, weather,
     people, feelings, firsts, sequence, dates, verbatim quotes);
  3. every remaining content word must be a function word or in the versioned safe narrative
     vocabulary (lexicon_safe.txt); otherwise it becomes an ``unlicensed`` claim (the coverage
     backstop) that only the cited evidence payloads or the traveller's note can license;
  4. each claim is checked against the evidence the block CITES (never the whole trip);
  5. low-confidence / approximate evidence supports only hedged claims (DECISIONS D4).

A block is supported iff all its claims are. Blocks with origin ``edited``/``user`` are the
user's testimony and are supported by definition.

See docs/prototypes/R2-faithfulness.md for policy details, measurements and blind spots.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any, Iterable, Literal, Sequence

from pydantic import BaseModel, Field

from ..models import BlockVerdict, Claim, ClaimKind, ClaimVerdict, DiaryBlock, Evidence, StyleProfile
from . import lexicon as lx
from .verify_text import (Tok, fold, name_tokens, prepare, read_number, same_word, split_sentences,
                          tokenize, variants)

__all__ = ["extract_claims", "verify_block", "verify_diary", "DiaryReport", "VBlockVerdict", "VClaim",
           "VClaimVerdict", "SentenceVerdict", "Failure", "VERIFIER_VERSION"]

VERIFIER_VERSION = f"r2.1+lex{lx.LEXICON_VERSION}+safe{lx.SAFE_VERSION}"

# ---------------------------------------------------------------------------------------------
# result models (extend the contracts in models.py; see the write-up for requested changes)
# ---------------------------------------------------------------------------------------------

VClaimKind = ClaimKind | Literal["unlicensed", "quote", "citation"]


class VClaim(Claim):
    kind: VClaimKind  # type: ignore[assignment]
    sentence: int = 0                       # sentence index within the block
    start: int = 0                          # char span in the block text
    end: int = 0
    meta: dict[str, Any] = Field(default_factory=dict, exclude=True, repr=False)


class VClaimVerdict(ClaimVerdict):
    claim: VClaim  # type: ignore[assignment]


class SentenceVerdict(BaseModel):
    index: int
    text: str
    supported: bool
    verdicts: list[VClaimVerdict] = Field(default_factory=list)


class VBlockVerdict(BlockVerdict):
    verdicts: list[VClaimVerdict] = Field(default_factory=list)  # type: ignore[assignment]
    sentences: list[SentenceVerdict] = Field(default_factory=list)
    testimony: bool = False
    reason: str = ""


class Failure(BaseModel):
    block_id: str
    day: date
    sentence: int
    sentence_text: str
    kind: str
    claim_text: str
    reason: str


class DiaryReport(BaseModel):
    """Counts cover GENERATED blocks only; user testimony is counted in ``testimony_blocks``.

    fabrication_rate        = unsupported_sentences / sentences
    claim_fabrication_rate  = unsupported_claims / claims
    A sentence is unsupported if at least one of its claims is unsupported, or if its block has a
    citation failure (unknown / other-day / missing evidence), which taints every sentence.
    """

    blocks: int = 0
    testimony_blocks: int = 0
    sentences: int = 0
    claims: int = 0
    unsupported_claims: int = 0
    unsupported_sentences: int = 0
    unsupported_blocks: int = 0
    fabrication_rate: float = 0.0
    claim_fabrication_rate: float = 0.0
    failures: list[Failure] = Field(default_factory=list)
    verdicts: list[VBlockVerdict] = Field(default_factory=list)
    verifier_version: str = VERIFIER_VERSION


# ---------------------------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------------------------

_QUOTE_OPEN = {'"', "“", "«"}
_QUOTE_CLOSE = {'"', "”", "»"}
_NUMERIC_KINDS = {"time", "duration", "distance", "elevation", "count"}
_HEDGE_TOKS = {w for p in lx.HEDGE_LOCAL + lx.HEDGE_SENTENCE + lx.HEDGE_POST for w in p.split()}
_TIME_PREPS = {"at", "by", "around", "about", "after", "before", "until", "till", "past", "towards", "toward",
               "from", "to", "roughly", "nearly", "almost", "approximately"}
_TIME_MOD = {  # phrase → (lo, hi) window around the stated time, minutes
    ("just", "after"): (0, 25), ("shortly", "after"): (0, 25), ("soon", "after"): (0, 25),
    ("little", "after"): (0, 25), ("just", "past"): (0, 25), ("just", "before"): (-25, 0),
    ("shortly", "before"): (-25, 0), ("little", "before"): (-25, 0),
    ("after",): (0, 45), ("past",): (0, 45), ("before",): (-45, 0), ("by",): (-30, 5),
}


def _is_ordinary(low: str) -> bool:
    """A word that can legitimately be capitalised only because it starts a sentence."""
    if low in lx.FUNCTION or low in lx.FIRST_PERSON_PLURAL or low in _HEDGE_TOKS or low in lx.SEQUENCE_WORDS:
        return True
    if low in lx.NUMBER_WORDS or low in lx.PARTS_OF_DAY or low in lx.UNITS or low in lx.SUPERLATIVE:
        return True
    if low in ("first", "back", "today", "yesterday", "tomorrow", "half", "quarter", "midnight", "just",
               "forward", "no", "not", "never"):
        return True
    for v in variants(low):
        if v in lx.SAFE or v in lx.ACTIVITY or v in lx.FOOD or v in lx.WEATHER or v in lx.PEOPLE \
                or v in lx.FEELING or v in lx.WEATHER_BY_TAG:
            return True
    return False


def _tok_pieces(t: Tok) -> tuple[str, ...]:
    txt = re.sub(r"['’]s$", "", t.text)
    return name_tokens(txt)


class _Sent:
    def __init__(self, text: str, start: int, end: int, index: int):
        self.index = index
        self.text = text[start:end]
        self.full = text
        self.toks = tokenize(text[start:end], start)
        self.claims: list[VClaim] = []
        self.sentence_hedge = False
        self.words = [i for i, t in enumerate(self.toks) if t.kind == "w"]

    def add(self, kind: str, i: int, j: int, value: Any = None, **meta: Any) -> VClaim:
        toks = self.toks
        for t in toks[i:j]:
            if t.used is None or t.used in ("fn", "safe"):
                t.used = kind
        c = VClaim(kind=kind, text=self.full[toks[i].start:toks[j - 1].end], value=value,  # type: ignore[arg-type]
                   sentence=self.index, start=toks[i].start, end=toks[j - 1].end, meta={"i": i, "j": j, **meta})
        self.claims.append(c)
        return c

    def low(self, i: int) -> str:
        return self.toks[i].low if 0 <= i < len(self.toks) else ""

    def free_word(self, i: int) -> bool:
        return 0 <= i < len(self.toks) and self.toks[i].kind == "w" and self.toks[i].used is None

    def adjacent(self, i: int) -> bool:
        """True if token i+1 follows token i with only whitespace (or nothing) between."""
        return i + 1 < len(self.toks) and self.full[self.toks[i].end:self.toks[i + 1].start].strip() == ""


def _extract_sentence(text: str, start: int, end: int, index: int, style: StyleProfile | None,
                      hints: Sequence[tuple[str, ...]] = ()) -> _Sent:
    s = _Sent(text, start, end, index)
    _x_quotes(s)
    _x_hints(s, hints)
    _x_dates(s)
    _x_numbers(s)
    _x_parts_of_day(s)
    _x_hedges(s)
    _x_proper_nouns(s)
    _x_words(s, style)
    _assign_hedges(s)
    s.claims.sort(key=lambda c: (c.start, c.end))
    return s


def _x_quotes(s: _Sent) -> None:
    open_i: int | None = None
    for i, t in enumerate(s.toks):
        if t.kind != "p":
            continue
        if open_i is None and t.text in _QUOTE_OPEN:
            open_i = i
        elif open_i is not None and t.text in _QUOTE_CLOSE:
            if i - open_i > 1:
                inner = s.toks[open_i + 1:i]
                for q in inner:
                    q.quoted = True
                    q.used = "quote"
                pieces = name_tokens(s.full[inner[0].start:inner[-1].end])
                s.add("quote", open_i + 1, i, list(pieces))
            open_i = None


def _x_hints(s: _Sent, hints: Sequence[tuple[str, ...]]) -> None:
    """Greedy longest match of known names (from evidence / gazetteer) so that names containing
    ordinary words ('Time Out Market') or starting a sentence are found reliably."""
    if not hints:
        return
    toks = s.toks
    first_word = s.words[0] if s.words else -1
    for i in range(len(toks)):
        if toks[i].used is not None or toks[i].kind not in "wn":
            continue
        best = None
        for h in hints:  # sorted longest first
            acc: list[str] = []
            j = i
            ok = False
            while j < len(toks) and toks[j].used is None and (toks[j].kind in "wn" or toks[j].text in "-.'’"):
                if toks[j].kind in "wn":
                    acc.extend(_tok_pieces(toks[j]))
                    if len(acc) >= len(h):
                        ok = tuple(acc) == h
                        j += 1
                        break
                elif j > i and not s.adjacent(j - 1) and toks[j].text != ".":
                    break
                j += 1
            if not ok:
                continue
            span = toks[i:j]
            capped = any(t.cap for t in span if t.kind == "w")
            if not capped:
                continue
            if len(h) == 1 and i == first_word and _is_ordinary(toks[i].low):
                continue
            if len(h) == 1 and h[0].isdigit():
                continue
            best = j
            break
        if best is not None:
            pieces = [p for t in toks[i:best] if t.kind in "wn" for p in _tok_pieces(t)]
            s.add("place", i, best, pieces, hint=True)


def _ordinal_at(s: _Sent, i: int) -> int | None:
    """Day-of-month number at token i ('14', '14th')."""
    t = s.toks[i] if 0 <= i < len(s.toks) else None
    if t is None or t.kind != "n" or not t.text.isdigit() or t.used is not None:
        return None
    n = int(t.text)
    return n if 1 <= n <= 31 else None


def _x_dates(s: _Sent) -> None:
    toks = s.toks
    for i, t in enumerate(toks):
        if t.kind != "w" or t.used is not None:
            continue
        low = t.low
        if low in lx.WEEKDAYS or (t.cap and low in lx.WEEKDAY_ABBR and low != "sun"):
            wd = lx.WEEKDAYS.index(low) if low in lx.WEEKDAYS else lx.WEEKDAY_ABBR[low]
            s.add("date", i, i + 1, {"weekday": wd})
            continue
        month = None
        if low in lx.MONTHS and (t.cap or low not in ("may", "march")):
            month = lx.MONTHS.index(low) + 1
        elif t.cap and low in lx.MONTH_ABBR:
            month = lx.MONTH_ABBR[low]
        if month is None:
            if low in ("yesterday", "tomorrow"):
                s.add("date", i, i + 1, {"relative": low})
            continue
        a, b = i, i + 1
        day = None
        # "June 14", "June 14th"
        if _ordinal_at(s, i + 1) is not None:
            day = _ordinal_at(s, i + 1)
            b = i + 2
            if b < len(toks) and toks[b].low in ("st", "nd", "rd", "th") and s.full[toks[b - 1].end:toks[b].start] == "":
                b += 1
        else:  # "14 June", "14th of June", "the 14th of June"
            k = i - 1
            if k >= 0 and toks[k].low == "of":
                k -= 1
            if k >= 0 and toks[k].low in ("st", "nd", "rd", "th"):
                k -= 1
            if _ordinal_at(s, k) is not None:
                day = _ordinal_at(s, k)
                a = k
        val: dict[str, Any] = {"month": month}
        if day is not None:
            val["day"] = day
        # optional year
        k = b
        if k < len(toks) and toks[k].text == ",":
            k += 1
        if k < len(toks) and toks[k].kind == "n" and re.fullmatch(r"(19|20)\d\d", toks[k].text):
            val["year"] = int(toks[k].text)
            b = k + 1
        for x in toks[a:b]:
            x.used = None if x.used in (None, "date") else x.used
        s.add("date", a, b, val)
    # "the 14th" and bare years
    for i, t in enumerate(toks):
        if t.kind != "n" or t.used is not None:
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if nxt is not None and nxt.low in ("st", "nd", "rd", "th") and s.full[t.end:nxt.start] == "" \
                and t.text.isdigit() and 1 <= int(t.text) <= 31 and s.low(i - 1) == "the":
            s.add("date", i, i + 2, {"day": int(t.text)})
        elif re.fullmatch(r"(19|20)\d\d", t.text) and (nxt is None or nxt.low not in lx.UNITS) \
                and s.low(i - 1) in ("in", "of", "since", "summer", "spring", "autumn", "winter", ","):
            s.add("date", i, i + 1, {"year": int(t.text)})


def _time_claim(s: _Sent, i: int, j: int, minutes: int, ambiguous: bool, precision: str) -> None:
    """Create a time claim over tokens [i, j) and fold preceding modifiers into its window."""
    lo, hi = {"minute": (-5, 5), "fraction": (-7, 7), "hour": (-10, 10)}[precision]
    hlo, hhi = {"minute": (-15, 15), "fraction": (-15, 15), "hour": (-20, 20)}[precision]
    mod = None
    a = i
    p1, p2 = s.low(i - 1), s.low(i - 2)
    if s.free_word(i - 1) or (i >= 1 and s.toks[i - 1].used == "hedge"):
        if (p2, p1) in _TIME_MOD and i >= 2:
            mod = _TIME_MOD[(p2, p1)]
            a = i - 2
            if p2 == "little" and s.low(i - 3) == "a":
                a = i - 3
        elif (p1,) in _TIME_MOD:
            mod = _TIME_MOD[(p1,)]
            a = i - 1
    for t in s.toks[a:i]:
        t.used = "fn"
    meta = dict(minutes=minutes % 1440, ambiguous=ambiguous, lo=lo, hi=hi, hlo=hlo, hhi=hhi, mod=mod)
    s.add("time", i, j, f"{(minutes % 1440) // 60:02d}:{minutes % 60:02d}", **meta)


def _ampm(s: _Sent, k: int) -> str | None:
    low = s.low(k)
    if low in ("am", "pm") and s.toks[k].used is None:
        return low
    return None


def _x_numbers(s: _Sent) -> None:
    toks = s.toks
    n = len(toks)
    i = 0
    while i < n:
        t = toks[i]
        if t.used is not None or t.kind == "p":
            i += 1
            continue
        low = t.low
        # --- clock times ------------------------------------------------------------------
        if t.kind == "n":
            m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", t.text)
            ap = _ampm(s, i + 1)
            if m and (":" in t.text or ap) and int(m.group(1)) < 24 and int(m.group(2)) < 60:
                h, mi = int(m.group(1)), int(m.group(2))
                j = i + 1
                amb = False
                if ap:
                    h = h % 12 + (12 if ap == "pm" else 0)
                    j = i + 2
                else:
                    amb = 1 <= h <= 12 and not t.text.startswith("0")
                _time_claim(s, i, j, h * 60 + mi, amb, "minute")
                i = j
                continue
            if t.text.isdigit() and ap and 1 <= int(t.text) <= 12:
                h = int(t.text) % 12 + (12 if ap == "pm" else 0)
                _time_claim(s, i, i + 2, h * 60, False, "hour")
                i += 2
                continue
        if t.kind == "w" and low == "midnight":
            _time_claim(s, i, i + 1, 0, False, "hour")
            i += 1
            continue
        if t.kind == "w" and low in ("half", "quarter") and s.low(i + 1) in ("past", "to"):
            r = read_number(toks, i + 2)
            if r and 1 <= r[0] <= 12 and r[0] == int(r[0]):
                off = 30 if low == "half" else 15
                base = int(r[0]) * 60 + (off if s.low(i + 1) == "past" else -off)
                j = r[2]
                ap = _ampm(s, j)
                amb = ap is None
                if ap:
                    base = (base + (720 if ap == "pm" else 0)) if int(r[0]) != 12 else base
                    j += 1
                a = i - 1 if s.low(i - 1) == "a" and low == "quarter" else i
                for x in toks[a:i]:
                    x.used = "fn"
                _time_claim(s, i, j, base, amb, "fraction")
                i = j
                continue
        # --- quantities --------------------------------------------------------------------
        r = read_number(toks, i)
        indef = False
        if r is None and t.kind == "w":
            # "an hour", "a mile", "half an hour", "half a mile"
            if low in ("a", "an") and s.low(i + 1) in lx.UNITS and len(s.low(i + 1)) > 2:
                r, indef = (1.0, 0, i + 1), True
            elif low == "half" and s.low(i + 1) in ("a", "an") and s.low(i + 2) in lx.UNITS:
                r, indef = (0.5, 1, i + 2), True
        if r is None:
            i += 1
            continue
        val, dec, j = r
        if t.kind == "w" and low == "one" and not indef:
            nxt = s.low(j)
            if not (nxt in lx.UNITS or nxt in lx.PHOTO_NOUNS or nxt in lx.ACTIVITY or nxt in ("o'clock", "am", "pm")):
                i += 1          # "one" as a determiner
                continue
        k = j
        if k < n and toks[k].text == "-":
            k += 1
        unit = s.low(k) if k < n and toks[k].kind == "w" else ""
        if unit == "o'clock" and 1 <= val <= 12 and val == int(val):
            ap = _ampm(s, k + 1)
            h = int(val) % 12 + (12 if ap == "pm" else 0) if ap else int(val)
            _time_claim(s, i, k + 1 + (1 if ap else 0), h * 60, ap is None, "hour")
            i = k + 2 if ap else k + 1
            continue
        if _ampm(s, k) and 1 <= val <= 12 and val == int(val):
            h = int(val) % 12 + (12 if s.low(k) == "pm" else 0)
            _time_claim(s, i, k + 1, h * 60, False, "hour")
            i = k + 1
            continue
        if unit in lx.UNITS and not (unit in ("m", "h") and t.kind == "w"):
            dim, factor = lx.UNITS[unit]
            j2 = k + 1
            if dim == "duration":
                minutes = val * factor
                scale = "h" if factor == 60 else "min"
                if factor == 60:
                    # "2 h 40", "2 hours and 35 minutes", "an hour and a half"
                    k2 = j2
                    if [s.low(k2), s.low(k2 + 1), s.low(k2 + 2)] == ["and", "a", "half"]:
                        minutes += 30
                        j2 = k2 + 3
                    else:
                        if s.low(k2) == "and":
                            k2 += 1
                        r2 = read_number(toks, k2) if k2 < n else None
                        if r2 and r2[0] < 60:
                            u2 = s.low(r2[2])
                            if u2 in ("min", "mins", "minute", "minutes", "m"):
                                minutes += r2[0]
                                j2 = r2[2] + 1
                                scale = "min"
                            elif toks[k2].kind == "n" and k2 == j2 and u2 not in lx.UNITS:
                                minutes += r2[0]
                                j2 = r2[2]
                                scale = "min"
                s.add("duration", i, j2, round(minutes, 2), stated=minutes, scale=scale, gran=1.0)
            elif dim == "distance":
                s.add("distance", i, j2, round(val * factor, 3), stated=val, factor=factor, gran=10 ** -dec)
            else:
                ctx = {s.low(j2), s.low(j2 + 1), s.low(i - 1)}
                kind = "distance" if ctx & {"from", "away", "walk", "further", "along"} else "elevation"
                s.add(kind, i, j2, round(val * factor, 2), stated=val, factor=factor, gran=10 ** -dec, metres=True)
            i = j2
            continue
        # --- bare hour after a time preposition: "around nine", "by seven" ----------------
        prev = s.low(i - 1)
        nxt_tok = toks[j] if j < n else None
        nxt_free = nxt_tok is None or nxt_tok.kind == "p" or nxt_tok.low in lx.FUNCTION \
            or nxt_tok.low in lx.FIRST_PERSON_PLURAL or nxt_tok.low in lx.PARTS_OF_DAY
        if prev in _TIME_PREPS and val == int(val) and nxt_free and not indef and (
                (t.kind == "w" and 1 <= val <= 12) or (t.kind == "n" and dec == 0 and val <= 24 and j == i + 1)):
            if not (prev in ("from", "to") and t.kind == "w" and nxt_tok is not None and nxt_tok.kind == "w"
                    and nxt_tok.low not in lx.PARTS_OF_DAY and nxt_tok.low not in ("in", "at", "we", "i")):
                h = int(val) % 24
                _time_claim(s, i, j, h * 60, h <= 12, "hour")
                i = j
                continue
        # --- counts / labels ---------------------------------------------------------------
        noun_i = j if j < n and toks[j].kind == "w" else None
        noun = toks[noun_i].low if noun_i is not None else ""
        if noun in lx.PHOTO_NOUNS:
            s.add("count", i, j + 1, val, stated=val, noun="photo", gran=1.0)
            i = j + 1
            continue
        if noun in lx.ACTIVITY and lx.ACTIVITY[noun].claim_kind == "transport":
            s.add("count", i, j, val, stated=val, noun="mode:" + next(iter(lx.ACTIVITY[noun].modes), ""), gran=1.0)
            i = j
            continue
        if noun in ("countries", "country", "borders", "border"):
            s.add("count", i, j, val, stated=val, noun=noun[:6], gran=1.0)
            i = j
            continue
        pt = toks[i - 1] if i >= 1 else None
        if t.kind == "n" and pt is not None and pt.kind == "w" and s.adjacent(i - 1) and (
                pt.low in lx.ACTIVITY or pt.cap or pt.low in ("line", "route", "no", "number", "platform", "gate")):
            lab_kind = "transport" if pt.low in lx.ACTIVITY and lx.ACTIVITY[pt.low].claim_kind == "transport" \
                else "place"
            s.add(lab_kind, i, j, t.text, label=True)
            if pt.used is None and pt.low not in lx.ACTIVITY:
                pt.used = "fn"
            i = j
            continue
        s.add("count", i, j, val, stated=val, noun=noun, gran=1.0)
        i = j


def _x_parts_of_day(s: _Sent) -> None:
    for i, t in enumerate(s.toks):
        if t.kind != "w" or t.used is not None:
            continue
        low = t.low
        whole = s.low(i - 1) in ("all", "whole") and s.free_word(i - 1)
        if low in lx.PARTS_OF_DAY:
            part, window = lx.PARTS_OF_DAY[low]
            a = i - 1 if whole else i
            s.add("part_of_day", a, i + 1, part, window=window, whole=whole)
        elif low in ("day", "night") and whole:
            s.add("part_of_day", i - 1, i + 1, "day", window=(360, 1320), whole=True)


def _match_phrase(s: _Sent, i: int, phrase: str, allow_used: bool = False) -> int | None:
    words = phrase.split()
    j = i
    for w in words:
        if j >= len(s.toks) or s.toks[j].kind != "w" or s.toks[j].low != w:
            return None
        if s.toks[j].used is not None and not allow_used:
            return None
        j += 1
    return j


def _x_hedges(s: _Sent) -> None:
    s.hedge_local: list[int] = []      # token index where a local hedge ends
    s.hedge_post: list[int] = []       # token index where a post hedge starts
    toks = s.toks
    for group, kind in ((lx.HEDGE_SENTENCE, "s"), (sorted(lx.HEDGE_LOCAL, key=len, reverse=True), "l"),
                        (lx.HEDGE_POST, "p")):
        for i in range(len(toks)):
            for phrase in group:
                j = _match_phrase(s, i, phrase)
                if j is None:
                    continue
                for t in toks[i:j]:
                    t.used = "hedge"
                if kind == "s":
                    s.sentence_hedge = True
                elif kind == "l":
                    s.hedge_local.append(j)
                else:
                    s.hedge_post.append(i)
                break


def _x_proper_nouns(s: _Sent) -> None:
    toks = s.toks
    n = len(toks)
    starts = set()
    if s.words:
        starts.add(s.words[0])
    for i, t in enumerate(toks):
        if t.kind == "p" and t.text in ":—–;(" and i + 1 < n:
            starts.add(i + 1)
    i = 0
    while i < n:
        t = toks[i]
        if not (t.kind == "w" and t.cap and t.used is None):
            i += 1
            continue
        low = re.sub(r"'s$", "", t.low)
        if low == "i" or low.startswith("i'"):
            t.used = "fn"
            i += 1
            continue
        nxt_is_label = i + 1 < n and toks[i + 1].kind == "n" and _is_ordinary(low)
        if (i in starts and _is_ordinary(low)) or nxt_is_label:
            i += 1
            continue
        j = i + 1
        while j < n:
            if not s.adjacent(j - 1) and not (toks[j].text == "-"):
                break
            if toks[j].kind == "w" and toks[j].cap and toks[j].used is None:
                j += 1
                continue
            # connectors: "de", "du", "de la" … must be followed by another capitalised word
            k = j
            while k < n and k - j < 2 and toks[k].kind == "w" and not toks[k].cap \
                    and toks[k].low in lx.NAME_CONNECTORS and toks[k].used is None and s.adjacent(k - 1):
                k += 1
            if k > j and k < n and toks[k].kind == "w" and toks[k].cap and toks[k].used is None and s.adjacent(k - 1):
                j = k + 1
                continue
            break
        pieces = [p for x in toks[i:j] if x.kind == "w" for p in _tok_pieces(x)]
        kind = "people" if s.low(i - 1) == "with" else "place"
        s.add(kind, i, j, pieces, proper=True)
        i = j


def _x_words(s: _Sent, style: StyleProfile | None) -> None:
    toks = s.toks
    for i, t in enumerate(toks):
        if t.used is not None:
            continue
        if t.kind == "p":
            if unicodedata.category(t.text[0]) == "So":       # emoji and pictographs assert things too
                s.add("unlicensed", i, i + 1, t.text)
            continue
        if t.kind == "n":
            s.add("count", i, i + 1, t.text, stated=None, noun="", gran=1.0)
            continue
        low = re.sub(r"'s$", "", t.low)
        if low in lx.FUNCTION or low == "today":
            t.used = "fn"
        elif low in lx.FIRST_PERSON_PLURAL:
            if style is not None and style.person == "i":
                s.add("people", i, i + 1, "we")
            else:
                t.used = "fn"
        elif low == "first":
            is_claim = s.low(i - 1) in ("my", "our", "the", "a", "very") or s.low(i + 1) in ("time", "ever", "visit")
            s.add("first" if is_claim else "sequence", i, i + 1, "first")
        elif low in lx.SEQUENCE_WORDS:
            s.add("sequence", i, i + 1, low)
        elif low in ("back", "returned", "return", "returning"):
            s.add("sequence", i, i + 1, "back")
        elif low in ("forward", "forwards", "ahead", "backward", "backwards"):
            s.add("activity", i, i + 1, "tz:" + ("+" if low in ("forward", "forwards", "ahead") else "-"))
        elif low in lx.SUPERLATIVE or (low.endswith("est") and len(low) >= 5 and low not in lx.NOT_SUPERLATIVE
                                       and low not in lx.SAFE):
            s.add("first", i, i + 1, low, superlative=True)
        elif low in lx.SAFE:
            t.used = "safe"
        else:
            hit = None
            for v in variants(low):
                if v in lx.ACTIVITY:
                    hit = (lx.ACTIVITY[v].claim_kind, lx.ACTIVITY[v].key)
                elif v in lx.FOOD:
                    hit = ("food", v)
                elif v in lx.WEATHER or v in lx.WEATHER_BY_TAG:
                    hit = ("weather", v)
                elif v in lx.PEOPLE:
                    hit = ("people", v)
                elif v in lx.FEELING:
                    hit = ("feeling", v)
                if hit:
                    break
            if hit:
                s.add(hit[0], i, i + 1, hit[1], word=low)
            elif any(v in lx.SAFE for v in variants(low)):
                t.used = "safe"
            else:
                s.add("unlicensed", i, i + 1, low)


def _assign_hedges(s: _Sent) -> None:
    toks = s.toks
    for c in s.claims:
        i, j = c.meta["i"], c.meta["j"]
        hedged = s.sentence_hedge
        if not hedged:
            hedged = any(0 <= i - e <= 3 and not any(toks[k].kind == "p" for k in range(e, i)) for e in s.hedge_local)
        if not hedged:
            hedged = any(0 <= p - j <= 1 for p in s.hedge_post)
        if c.kind == "time" and c.meta.get("mod"):
            pass
        c.hedged = bool(hedged)
        if c.kind in _NUMERIC_KINDS and c.kind != "time":
            # direction words immediately before the quantity: "over two hours", "nearly 13 hours"
            for phrases, d in ((lx.DIRECTION_UP, 1), (lx.DIRECTION_DOWN, -1)):
                for ph in sorted(phrases, key=len, reverse=True):
                    w = ph.split()
                    a = i - len(w)
                    if a >= 0 and [toks[k].low for k in range(a, i)] == w and all(
                            toks[k].used in (None, "hedge", "fn", "first", "unlicensed") for k in range(a, i)):
                        c.meta["dir"] = d
                        c.hedged = True
                        for k in range(a, i):
                            toks[k].used = "hedge"
                        s.claims[:] = [x for x in s.claims if not (a <= x.meta["i"] < i and x is not c)]
                        break
                if "dir" in c.meta:
                    break


def _extract(text: str, style: StyleProfile | None, hints: Sequence[tuple[str, ...]] = ()) -> list[_Sent]:
    text = prepare(text)
    return [_extract_sentence(text, a, b, k, style, hints) for k, (a, b) in enumerate(split_sentences(text))]


def extract_claims(text: str, *, style: StyleProfile | None = None) -> list[Claim]:
    """All checkable claims in ``text`` (evidence-free). Includes ``unlicensed`` content words."""
    return [c for s in _extract(text, style) for c in s.claims]


# ---------------------------------------------------------------------------------------------
# evidence context
# ---------------------------------------------------------------------------------------------


def _hhmm(v: Any) -> int | None:
    if not isinstance(v, str):
        return None
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*", v)
    if not m or int(m.group(1)) > 24 or int(m.group(2)) > 59:
        return None
    return (int(m.group(1)) * 60 + int(m.group(2))) % 1440


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _weak(e: Evidence) -> bool:
    return e.confidence == "low" or (e.type == "place" and bool(e.payload.get("approximate")))


def _strings(v: Any) -> Iterable[str]:
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _strings(x)


_NAME_FIELDS = {
    "place": [("name", "place", "place"), ("locality", "place", "locality"), ("country", "place", "country")],
    "locality": [("locality", "place", "locality"), ("region", "place", "locality"),
                 ("country", "place", "country")],
    "transport": [("from", "from", "place"), ("to", "to", "place")],
    "movement": [("from", "from", "place"), ("to", "to", "place")],
    "border": [("from_country", "from", "country"), ("to_country", "to", "country")],
    "first": [("value", "place", "place")],
}


class _Name:
    __slots__ = ("tokens", "role", "kind", "ev", "context")

    def __init__(self, tokens: tuple[str, ...], role: str, kind: str, ev: Evidence, context: frozenset[str]):
        self.tokens, self.role, self.kind, self.ev, self.context = tokens, role, kind, ev, context


def _names_of(e: Evidence) -> list[_Name]:
    out = []
    ctx: set[str] = set()
    for key in ("locality", "country", "region"):
        v = e.payload.get(key)
        if isinstance(v, str):
            ctx.update(name_tokens(v))
    for key, role, kind in _NAME_FIELDS.get(e.type, []):
        v = e.payload.get(key)
        if isinstance(v, str) and v.strip():
            toks = name_tokens(v)
            if toks and toks[0] == "the":
                toks = toks[1:]
            if toks:
                out.append(_Name(toks, role, kind, e, frozenset(ctx)))
    return out


class _Ctx:
    def __init__(self, block: DiaryBlock, evidence_by_id: dict[str, Evidence], known_places: Iterable[str] | None,
                 style: StyleProfile | None):
        self.block = block
        self.style = style
        self.cited: list[Evidence] = []
        self.missing: list[str] = []
        self.wrong_day: list[Evidence] = []
        seen = set()
        for eid in block.evidence_ids:
            if eid in seen:
                continue
            seen.add(eid)
            e = evidence_by_id.get(eid)
            if e is None:
                self.missing.append(eid)
            elif e.day != block.day:
                self.wrong_day.append(e)
            else:
                self.cited.append(e)
        self.names = [n for e in self.cited for n in _names_of(e)]
        self.other_names = [n for e in evidence_by_id.values() if e.id not in seen or e.day != block.day
                            for n in _names_of(e)]
        self.known = [t for t in (name_tokens(p) for p in (known_places or [])) if t]
        self.known = [t[1:] if t[0] == "the" and len(t) > 1 else t for t in self.known]
        self.notes: list[tuple[Evidence, list[str]]] = [
            (e, list(name_tokens(str(e.payload.get("text", ""))))) for e in self.cited if e.type == "note"]
        self.note_claims: list[tuple[Evidence, VClaim]] = []
        for e in self.cited:
            if e.type == "note":
                for s in _extract(str(e.payload.get("text", "")), None):
                    self.note_claims += [(e, c) for c in s.claims if c.kind in _NUMERIC_KINDS | {"part_of_day"}]
        self.payload_words: dict[str, list[Evidence]] = {}
        for e in self.cited:
            if e.type == "note":
                continue
            for st in _strings(e.payload):
                for w in re.split(r"[^0-9a-z]+", fold(st)):
                    if w:
                        self.payload_words.setdefault(w, []).append(e)
        self.by_type: dict[str, list[Evidence]] = {}
        for e in self.cited:
            self.by_type.setdefault(e.type, []).append(e)

    def of(self, *types: str) -> list[Evidence]:
        return [e for t in types for e in self.by_type.get(t, [])]

    def all_hints(self) -> list[tuple[str, ...]]:
        hs = {n.tokens for n in self.names} | {n.tokens for n in self.other_names} | set(self.known)
        return sorted(hs, key=lambda h: (-len(h), h))

    def note_word(self, word: str) -> list[Evidence]:
        return [e for e, toks in self.notes if any(len(t) > 1 and same_word(t, word) for t in toks)]

    def payload_word(self, word: str) -> list[Evidence]:
        out = []
        for v in variants(word):
            out += self.payload_words.get(v, [])
        if not out:
            for w, evs in self.payload_words.items():
                if len(w) > 2 and same_word(w, word):
                    out += evs
        return out

    def moment_times(self, moment_id: str | None) -> list[int]:
        out = []
        if moment_id is None:
            return out
        for e in self.of("time"):
            if e.moment_id == moment_id:
                m = _hhmm(e.payload.get("start_local"))
                if m is not None:
                    out.append(m)
        for e in self.of("transport"):
            if e.moment_id == moment_id:
                m = _hhmm(e.payload.get("depart_local"))
                if m is not None:
                    out.append(m)
        return out


# ---------------------------------------------------------------------------------------------
# checking
# ---------------------------------------------------------------------------------------------

Result = tuple[bool, str | None, str, list[Evidence]]


def _decide(c: VClaim, evs: list[Evidence], none_reason: str, ok_reason: str = "") -> Result:
    """D4: low-confidence / approximate evidence supports only hedged claims."""
    uniq: list[Evidence] = []
    for e in evs:
        if e not in uniq:
            uniq.append(e)
    if not uniq:
        return False, None, none_reason, []
    strong = [e for e in uniq if not _weak(e)]
    if strong:
        return True, strong[0].id, ok_reason or f"matches {strong[0].type} evidence", uniq
    if c.hedged:
        return True, uniq[0].id, f"hedged claim on low-confidence {uniq[0].type} evidence", uniq
    return False, uniq[0].id, f"needs hedge: only low-confidence/approximate evidence ({uniq[0].type})", uniq


def _name_match(ct: tuple[str, ...], n: _Name, ctx: _Ctx) -> bool:
    nt = n.tokens
    if ct == nt:
        return True
    if len(ct) >= len(nt) or not ct:
        return False
    generic = lx.NAME_GENERIC | lx.NAME_CONNECTORS
    for k in range(len(nt) - len(ct) + 1):
        if nt[k:k + len(ct)] == ct:
            dropped = nt[:k] + nt[k + len(ct):]
            if not all(d in generic or d in n.context for d in dropped):
                return False
            if not any(t not in generic and not t.isdigit() for t in ct):
                return False
            # the short form must not be the full name of a different known place
            if any(o.tokens == ct for o in ctx.other_names) or any(k2 == ct for k2 in ctx.known):
                return False
            return True
    return False


def _contig(needle: Sequence[str], hay: Sequence[str]) -> bool:
    n = len(needle)
    return n > 0 and any(tuple(hay[k:k + n]) == tuple(needle) for k in range(len(hay) - n + 1))


def _check_name(c: VClaim, s: _Sent, ctx: _Ctx) -> Result:
    ct = tuple(c.value or ())
    if ct and ct[0] == "the" and len(ct) > 1:
        ct = ct[1:]
    matches = [n for n in ctx.names if _name_match(ct, n, ctx)]
    if matches:
        roles = {n.role for n in matches}
        kinds = {n.kind for n in matches}
        if c.kind == "place":
            c.kind = "place" if "place" in kinds else ("locality" if "locality" in kinds else "country")
        i = c.meta["i"]
        prev = s.low(i - 1) if s.low(i - 1) != "the" else s.low(i - 2)
        if prev == "from" and roles == {"to"}:
            return False, matches[0].ev.id, "direction reversed: cited evidence has this as the destination, not the origin", []
        if prev in ("to", "into", "towards", "toward", "reached") and roles == {"from"}:
            return False, matches[0].ev.id, "direction reversed: cited evidence has this as the origin, not the destination", []
        c.meta["roles"] = {n.ev.id: n.role for n in matches}
        return _decide(c, [n.ev for n in matches], "")
    note = [e for e, toks in ctx.notes if _contig(ct, toks)]
    if note:
        return _decide(c, note, "", "named in the traveller's note")
    others = [n for n in ctx.other_names if n.tokens == ct] or [n for n in ctx.other_names if _contig(ct, n.tokens)]
    if others:
        o = others[0].ev
        where = f"other day {o.day.isoformat()}" if o.day != ctx.block.day else "same day, other moment"
        return False, None, f"known place but not cited ({where})", []
    if any(k == ct for k in ctx.known):
        return False, None, "known gazetteer place but not in cited evidence", []
    return False, None, "proper noun not in cited evidence", []


def _time_points(ctx: _Ctx) -> list[tuple[int, Evidence]]:
    pts = []
    for e in ctx.of("time"):
        for k in ("start_local", "end_local"):
            m = _hhmm(e.payload.get(k))
            if m is not None:
                pts.append((m, e))
    for e in ctx.of("transport"):
        for k in ("depart_local", "arrive_local"):
            m = _hhmm(e.payload.get(k))
            if m is not None:
                pts.append((m, e))
    return pts


def _note_numeric(c: VClaim, ctx: _Ctx) -> list[Evidence]:
    out = []
    for e, nc in ctx.note_claims:
        if nc.kind != c.kind:
            continue
        if c.kind == "time":
            a, b = c.meta["minutes"], nc.meta["minutes"]
            if a == b or ((c.meta["ambiguous"] or nc.meta["ambiguous"]) and a % 720 == b % 720):
                out.append(e)
        elif c.kind == "count":
            if nc.value == c.value and (nc.meta.get("noun") == c.meta.get("noun")
                                        or same_word(str(nc.meta.get("noun")), str(c.meta.get("noun")))):
                out.append(e)
        elif nc.value == c.value:
            out.append(e)
    return out


def _check_time(c: VClaim, ctx: _Ctx) -> Result:
    m = c.meta
    lo, hi = (m["hlo"], m["hhi"]) if c.hedged else (m["lo"], m["hi"])
    if m.get("mod"):
        mlo, mhi = m["mod"]
        lo, hi = (mlo - (5 if c.hedged else 0), mhi + (5 if c.hedged else 0))
    cands = [m["minutes"]] + ([(m["minutes"] + 720) % 1440] if m["ambiguous"] else [])
    evs = []
    for p, e in _time_points(ctx):
        for cm in cands:
            d = ((p - cm + 720) % 1440) - 720
            if lo <= d <= hi:
                evs.append(e)
    evs += _note_numeric(c, ctx)
    return _decide(c, evs, f"no cited time within [{lo:+d},{hi:+d}] min of {c.value}")


def _intervals(ctx: _Ctx) -> list[tuple[int, int, Evidence]]:
    out = []
    for e in ctx.of("time"):
        a, b = _hhmm(e.payload.get("start_local")), _hhmm(e.payload.get("end_local"))
        if a is not None:
            out.append((a, b if b is not None else a, e))
    for e in ctx.of("transport"):
        a, b = _hhmm(e.payload.get("depart_local")), _hhmm(e.payload.get("arrive_local"))
        if a is not None:
            out.append((a, a, e))
        if b is not None:
            out.append((b, b, e))
    return out


def _overlap(a: int, b: int, w: tuple[int, int]) -> int:
    """Minutes of overlap between local interval [a, b] (b may wrap) and window w; -1 if none."""
    if b < a:
        b += 1440
    best = -1
    for shift in (0, 1440):
        lo, hi = max(a + shift, w[0]), min(b + shift, w[1])
        if hi >= lo:
            best = max(best, hi - lo)
    return best


def _check_part(c: VClaim, ctx: _Ctx) -> Result:
    part = str(c.value)
    window = c.meta.get("window")
    aliases = lx.PART_ALIASES.get(part, {part})
    evs: list[Evidence] = []
    if not c.meta.get("whole"):
        evs += [e for e in ctx.of("time") if fold(str(e.payload.get("part_of_day", ""))) in aliases]
        evs += [e for e in ctx.of("visual") if aliases & {fold(str(t)) for t in e.payload.get("tags", []) or []}]
    if window is not None:
        need = 150 if c.meta.get("whole") else 0
        if part == "day":
            need = 360
        for a, b, e in _intervals(ctx):
            if part in ("early", "late"):
                ok = _overlap(a, a, window) >= 0
            else:
                ov = _overlap(a, b, window)
                # a moment that merely touches the window edge does not count unless it starts/ends in it
                ok = ov >= need and (ov >= 15 or a == b or _overlap(a, a, window) >= 0 or _overlap(b, b, window) >= 0)
                if ok and not c.meta.get("whole") and a != b and ov < 15:
                    ok = ov >= 1
            if ok:
                evs.append(e)
    evs += [e for e, nc in ctx.note_claims if nc.kind == "part_of_day" and nc.value == part]
    evs += ctx.note_word(c.text.split()[-1].lower()) if not c.meta.get("whole") else []
    return _decide(c, evs, f"no cited time/visual evidence for '{part}'")


def _range_ok(c: VClaim, actual: float, floor_u: float, rel_u: float, floor_h: float, rel_h: float) -> bool:
    v = float(c.meta["stated"])
    gran = float(c.meta.get("gran", 1.0))
    t = max(floor_h, rel_h * v) if c.hedged else max(floor_u, rel_u * v)
    d = c.meta.get("dir")
    eps = 0.5 * gran
    if d == 1:
        return v - eps <= actual <= v + max(t, 0.25 * v)
    if d == -1:
        return v - max(t, 0.2 * v) <= actual <= v + eps
    return abs(actual - v) <= t + 1e-9


def _check_measure(c: VClaim, ctx: _Ctx) -> Result:
    evs: list[Evidence] = []
    if c.kind == "duration":
        cands: list[tuple[float, Evidence]] = []
        for e in ctx.of("duration"):
            v = _num(e.payload.get("minutes"))
            if v is not None:
                cands.append((v, e))
        for e in ctx.of("transport"):
            v = _num(e.payload.get("duration_min"))
            if v is not None:
                cands.append((v, e))
        for e in ctx.of("timezone_change"):
            a, b = _num(e.payload.get("from_offset_min")), _num(e.payload.get("to_offset_min"))
            if a is not None and b is not None:
                cands.append((abs(b - a), e))
        hours = c.meta.get("scale") == "h"
        for v, e in cands:
            if _range_ok(c, v, 10 if hours else 2, 0.08 if hours else 0.05, 15 if hours else 5, 0.2):
                evs.append(e)
        what = "duration"
    else:
        factor = float(c.meta["factor"])
        gran = float(c.meta["gran"])
        cands = []
        if c.meta.get("metres"):
            for e in ctx.of("elevation"):
                for k in ("ascent_m", "max_ele_m", "descent_m", "min_ele_m"):
                    v = _num(e.payload.get(k))
                    if v is not None:
                        cands.append((v / factor, e))
            for e in ctx.of("movement"):
                v = _num(e.payload.get("distance_km"))
                if v is not None:
                    cands.append((v * 1000 / factor, e))
            rel_u, rel_h = 0.03, 0.12
        else:
            for e in ctx.of("movement"):
                v = _num(e.payload.get("distance_km"))
                if v is not None:
                    cands.append((v / factor, e))
            rel_u, rel_h = 0.03, 0.15
        for v, e in cands:
            if _range_ok(c, v, 0.5 * gran, rel_u, gran, rel_h):
                evs.append(e)
        what = "distance/elevation"
    evs += _note_numeric(c, ctx)
    tol = "hedged" if c.hedged else "unhedged"
    return _decide(c, evs, f"no cited {what} evidence matches {c.text!r} ({tol} tolerance)")


def _check_count(c: VClaim, ctx: _Ctx) -> Result:
    noun = str(c.meta.get("noun", ""))
    evs: list[Evidence] = []
    if c.meta.get("stated") is None:
        return _decide(c, [], f"number {c.text!r} could not be interpreted")
    if noun == "photo":
        for e in ctx.of("photo_count"):
            v = _num(e.payload.get("count"))
            if v is not None and _range_ok(c, v, 0, 0, 1, 0.15):
                evs.append(e)
    elif noun.startswith("mode:"):
        mode = noun[5:]
        legs = [e for e in ctx.of("transport") if e.payload.get("mode") == mode] or \
               [e for e in ctx.of("movement") if e.payload.get("mode") == mode]
        n = len({e.moment_id or e.id for e in legs})
        if n and _range_ok(c, n, 0, 0, 0, 0):
            evs += legs
    elif noun == "countr":
        countries = {fold(str(e.payload.get(k))) for e in ctx.of("locality", "place", "border")
                     for k in ("country", "from_country", "to_country") if e.payload.get(k)}
        if countries and float(c.meta["stated"]) == len(countries):
            evs += ctx.of("locality", "border", "place")
    elif noun == "border":
        if float(c.meta["stated"]) == len(ctx.of("border")) and ctx.of("border"):
            evs += ctx.of("border")
    evs += _note_numeric(c, ctx)
    return _decide(c, evs, f"count {c.text!r} not matched by cited evidence")


def _check_label(c: VClaim, ctx: _Ctx) -> Result:
    lab = fold(str(c.value))
    evs = list(ctx.payload_words.get(lab, []))
    evs += [e for e in ctx.cited if e.type != "note" and any(
        _num(v) is not None and not isinstance(v, str) and str(v).rstrip("0").rstrip(".") == lab
        for k, v in e.payload.items() if k in ("line", "number", "platform"))]
    evs += [e for e, toks in ctx.notes if lab in toks]
    return _decide(c, evs, f"label/number {c.text!r} not in cited evidence")


def _check_activity(c: VClaim, s: _Sent, ctx: _Ctx) -> Result:
    key = str(c.value)
    word = str(c.meta.get("word", c.text)).lower()
    if key.startswith("tz:"):
        evs = []
        for e in ctx.of("timezone_change"):
            a, b = _num(e.payload.get("from_offset_min")), _num(e.payload.get("to_offset_min"))
            if a is not None and b is not None and ((b > a) == (key == "tz:+")) and a != b:
                evs.append(e)
        return _decide(c, evs, "no cited timezone change in that direction")
    act = next(a for a in lx.ACTIVITY.values() if a.key == key)
    evs: list[Evidence] = []
    for e in ctx.cited:
        p = e.payload
        if e.type == "kind" and p.get("kind") in act.kinds:
            evs.append(e)
        elif e.type in ("transport", "movement") and p.get("mode") in act.modes:
            evs.append(e)
        elif e.type == "place" and fold(str(p.get("category", ""))).replace(" ", "_") in act.categories:
            evs.append(e)
        elif e.type == "visual" and act.tags & {fold(str(t)) for t in p.get("tags", []) or []}:
            evs.append(e)
        if e.type in act.types and e not in evs:
            evs.append(e)
    if act.window is not None:
        timed = []
        for e in evs:
            for te in ctx.of("time"):
                st = _hhmm(te.payload.get("start_local"))
                if st is not None and (e.moment_id is None or te.moment_id == e.moment_id) \
                        and act.window[0] <= st <= act.window[1]:
                    timed.append(e)
        none_reason = (f"'{word}' needs a meal moment starting {act.window[0] // 60:02d}:{act.window[0] % 60:02d}–"
                       f"{act.window[1] // 60:02d}:{act.window[1] % 60:02d} with its time cited, or the traveller's note")
        evs = timed
    else:
        none_reason = f"no cited evidence for '{word}' ({act.key})"
        evs += [n.ev for n in ctx.names if any(same_word(t, word) for t in n.tokens)]
        evs += ctx.payload_word(word)
    evs += ctx.note_word(word)
    return _decide(c, evs, none_reason)


def _content_words(s: _Sent, skip: VClaim) -> list[str]:
    out = []
    for k, t in enumerate(s.toks):
        if t.kind != "w" or t.used in ("fn", "safe", "hedge", "feeling", "quote", "sequence", None):
            continue
        if skip.meta["i"] <= k < skip.meta["j"]:
            continue
        out.append(t.low)
    return out


def _check_note_only(c: VClaim, s: _Sent, ctx: _Ctx, label: str) -> Result:
    word = str(c.meta.get("word", c.value))
    evs = ctx.note_word(word)
    if c.kind == "feeling" or c.meta.get("superlative"):
        # an evaluation must be about something the same note talks about
        others = _content_words(s, c)
        if others:
            evs = [e for e in evs if any(any(same_word(t, o) for t in toks) for (ne, toks) in ctx.notes if ne is e
                                         for o in others)]
            if not evs and ctx.note_word(word):
                return False, None, f"{label} word '{word}' is in the note but applied to something the note does not mention", []
    if c.kind == "food":
        evs += [n.ev for n in ctx.names if n.role == "place" and any(same_word(t, word) for t in n.tokens)]
    if c.kind == "weather" and word in lx.WEATHER_BY_TAG:
        tag = lx.WEATHER_BY_TAG[word]
        evs += [e for e in ctx.of("visual") if tag in {fold(str(t)) for t in e.payload.get("tags", []) or []}]
    if c.kind == "people" and word == "crowd":
        evs += [e for e in ctx.of("visual") if {"crowd", "crowds"} & {fold(str(t)) for t in e.payload.get("tags", []) or []}]
    return _decide(c, evs, f"{label} '{c.text}' is only supportable by the traveller's own note, and no cited note says it",
                   "in the traveller's note" if evs and evs[0].type == "note" else "")


def _check_first(c: VClaim, s: _Sent, ctx: _Ctx) -> Result:
    sent_words = {p for t in s.toks if t.kind in "wn" for p in _tok_pieces(t)}
    evs = []
    for e in ctx.of("first"):
        value = set(name_tokens(str(e.payload.get("value", ""))))
        text_words = set(name_tokens(str(e.payload.get("text", "")))) | set(name_tokens(str(e.payload.get("what", ""))))
        if c.meta.get("superlative"):
            if any(same_word(str(c.value), w) for w in text_words):
                evs.append(e)
        elif (value and value <= sent_words) or any(same_word(str(e.payload.get("what", "")), w) for w in sent_words):
            evs.append(e)
    if evs:
        return _decide(c, evs, "")
    if c.meta.get("superlative"):
        return _check_note_only(c, s, ctx, "superlative")
    note = ctx.note_word("first")
    return _decide(c, note, "'first' claim without matching cited `first` evidence", "in the traveller's note")


def _check_date(c: VClaim, ctx: _Ctx) -> Result:
    v = c.value or {}
    d = ctx.block.day
    if "relative" in v:
        return False, None, f"relative date '{v['relative']}' is not checkable against the block's day", []
    bad = []
    if "weekday" in v and v["weekday"] != d.weekday():
        bad.append(f"{d.isoformat()} is a {lx.WEEKDAYS[d.weekday()].title()}")
    if "month" in v and v["month"] != d.month:
        bad.append(f"block day is in {lx.MONTHS[d.month - 1].title()}")
    if "day" in v and v["day"] != d.day:
        bad.append(f"block day is the {d.day}")
    if "year" in v and v["year"] != d.year:
        bad.append(f"block year is {d.year}")
    if bad:
        return False, None, "date mismatch: " + "; ".join(bad), []
    return True, None, f"matches block day {d.isoformat()}", []


def _check_unlicensed(c: VClaim, ctx: _Ctx) -> Result:
    word = str(c.value)
    evs = ctx.payload_word(word) + ctx.note_word(word)
    evs += [n.ev for n in ctx.names if any(same_word(t, word) for t in n.tokens)]
    return _decide(c, evs, f"unlicensed word: '{word}' (not in safe vocabulary, cited evidence or note)",
                   "licensed by cited evidence")


def _check_quote(c: VClaim, ctx: _Ctx) -> Result:
    evs = [e for e, toks in ctx.notes if _contig(list(c.value or []), toks)]
    return _decide(c, evs, "quoted words are not a verbatim span of a cited note", "verbatim from the traveller's note")


def _moments(evs: list[Evidence]) -> set[str]:
    return {e.moment_id for e in evs if e.moment_id}


def _anchor_times(c: VClaim, evs: list[Evidence], ctx: _Ctx) -> list[int]:
    out: list[int] = []
    roles = c.meta.get("roles", {})
    for e in evs:
        if e.type == "transport":
            key = "arrive_local" if roles.get(e.id) == "to" else "depart_local"
            m = _hhmm(e.payload.get(key))
            if m is not None:
                out.append(m)
                continue
        if e.type == "movement" and roles.get(e.id) == "to":
            continue
        out += ctx.moment_times(e.moment_id)
    return out


def _check_sequences(s: _Sent, results: dict[int, Result], ctx: _Ctx) -> None:
    anchors = []
    for c in s.claims:
        r = results.get(id(c))
        if r and r[0] and c.kind in ("place", "locality", "activity", "transport", "food"):
            times = _anchor_times(c, r[3], ctx)
            if times:
                anchors.append((c, times, _moments(r[3])))
    seq_ev = {(e.payload.get("after_moment_id"), e.moment_id) for e in ctx.of("sequence")}  # (earlier, later)

    def before(a, b) -> bool | None:
        """Is anchor a no later than anchor b? None = cannot tell."""
        if a[2] & b[2]:
            return None
        if any((x, y) in seq_ev for x in a[2] for y in b[2]):
            return True
        if any((y, x) in seq_ev for x in a[2] for y in b[2]):
            return False
        if min(a[1]) > max(b[1]):
            return False
        return True

    for c in s.claims:
        if c.kind != "sequence":
            continue
        w = str(c.value)
        k = c.meta["i"]
        if w == "back":
            names = [x for x in s.claims if x.kind in ("place", "locality") and results.get(id(x), (False,))[0]]
            ok = any(len(_moments(results[id(x)][3])) >= 2 for x in names)
            loops = [e for e in ctx.of("movement", "transport") if e.payload.get("from") and
                     fold(str(e.payload.get("from"))) == fold(str(e.payload.get("to")))]
            note = ctx.note_word("back")
            if ok or loops or note:
                results[id(c)] = (True, (loops or note or [None])[0].id if (loops or note) else None,
                                  "return is evidenced (place appears in two cited moments / loop / note)", [])
            else:
                results[id(c)] = (False, None, "'back' needs the place in two cited moments (or a loop movement, or the note)", [])
            continue
        prev = [a for a in anchors if a[0].meta["j"] <= k]
        nxt = [a for a in anchors if a[0].meta["i"] > k]
        pair = None
        if w in ("then", "later", "afterwards", "afterward", "next", "first"):
            if w == "first" and len(nxt) >= 2 and not prev:
                pair = (nxt[0], nxt[1])
            elif w == "first" and prev and nxt:
                pair = (prev[-1], nxt[0])
            elif prev and nxt:
                pair = (prev[-1], nxt[0])
        elif w == "before":
            pair = (prev[-1], nxt[0]) if prev and nxt else ((nxt[1], nxt[0]) if len(nxt) >= 2 else None)
        elif w in ("after", "earlier"):
            pair = (nxt[0], prev[-1]) if prev and nxt else ((nxt[0], nxt[1]) if len(nxt) >= 2 and w == "after" else None)
        if pair is None:
            results[id(c)] = (True, None, "connective; order not checkable within this block", [])
            continue
        verdict = before(pair[0], pair[1])
        if verdict is False:
            results[id(c)] = (False, None,
                              f"order contradicts cited evidence: '{pair[0][0].text}' is not before '{pair[1][0].text}'", [])
        else:
            results[id(c)] = (True, None, "order consistent with cited times" if verdict else
                              "same moment; order not at issue", [])


def _check_binding(s: _Sent, results: dict[int, Result]) -> None:
    """'<activity> at/in <Place>': both must be supported by evidence of one moment."""
    cl = s.claims
    for a, b in zip(cl, cl[1:]):
        if a.kind not in ("activity", "transport", "food") or b.kind not in ("place",):
            continue
        between = s.toks[a.meta["j"]:b.meta["i"]]
        if not (1 <= len(between) <= 3) or any(t.kind == "p" for t in between) \
                or not any(t.low in ("at", "in") for t in between):
            continue
        ra, rb = results.get(id(a)), results.get(id(b))
        if not (ra and rb and ra[0] and rb[0]):
            continue
        ma, mb = _moments(ra[3]), _moments(rb[3])
        free = any(e.moment_id is None for e in ra[3]) or any(e.moment_id is None for e in rb[3])
        if ma and mb and not (ma & mb) and not free:
            results[id(a)] = (False, ra[1], f"'{a.text}' and '{b.text}' are evidenced in different moments", ra[3])


def _check_claim(c: VClaim, s: _Sent, ctx: _Ctx) -> Result:
    k = c.kind
    if c.meta.get("label"):
        return _check_label(c, ctx)
    if k in ("place", "locality", "country") or (k == "people" and c.meta.get("proper")):
        return _check_name(c, s, ctx)
    if k == "time":
        return _check_time(c, ctx)
    if k == "part_of_day":
        return _check_part(c, ctx)
    if k in ("duration", "distance", "elevation"):
        return _check_measure(c, ctx)
    if k == "count":
        return _check_count(c, ctx)
    if k in ("activity", "transport"):
        return _check_activity(c, s, ctx)
    if k in ("food", "weather", "people", "feeling"):
        return _check_note_only(c, s, ctx, k)
    if k == "first":
        return _check_first(c, s, ctx)
    if k == "date":
        return _check_date(c, ctx)
    if k == "quote":
        return _check_quote(c, ctx)
    if k == "unlicensed":
        return _check_unlicensed(c, ctx)
    if k == "sequence":
        return True, None, "connective; order not checkable within this block", []
    return False, None, f"unhandled claim kind {k}", []


def _block_start(block: DiaryBlock, evidence_by_id: dict[str, Evidence]) -> int | None:
    ts = []
    for eid in block.evidence_ids:
        e = evidence_by_id.get(eid)
        if e is None or e.day != block.day:
            continue
        m = _hhmm(e.payload.get("start_local")) if e.type == "time" else (
            _hhmm(e.payload.get("depart_local")) if e.type == "transport" else None)
        if m is not None:
            ts.append(m)
    return min(ts) if ts else None


def verify_block(block: DiaryBlock, evidence_by_id: dict[str, Evidence], *,
                 known_places: Iterable[str] | None = None, style: StyleProfile | None = None,
                 coverage: bool = True, previous: DiaryBlock | None = None) -> VBlockVerdict:
    """Verify one block against the evidence it cites.

    ``coverage=False`` disables the content-word backstop (for measurement only).
    ``previous`` (the preceding block of the same day) enables the cross-block order check for a
    block that opens with "Then/Later/Afterwards/Next".
    """
    if block.origin in ("edited", "user"):
        return VBlockVerdict(block_id=block.id, supported=True, testimony=True,
                             reason=f"origin={block.origin}: the user's own testimony, supported by definition")
    ctx = _Ctx(block, evidence_by_id, known_places, style)
    sents = _extract(block.text or "", style, ctx.all_hints())
    out_sents: list[SentenceVerdict] = []
    all_v: list[VClaimVerdict] = []
    citation: list[VClaimVerdict] = []
    for eid in ctx.missing:
        citation.append(VClaimVerdict(claim=VClaim(kind="citation", text=eid, value=eid), supported=False,
                                      reason="cited evidence id does not exist"))
    for e in ctx.wrong_day:
        citation.append(VClaimVerdict(claim=VClaim(kind="citation", text=e.id, value=e.id), supported=False,
                                      evidence_id=e.id,
                                      reason=f"cited evidence belongs to another day ({e.day.isoformat()})"))
    if sents and not block.evidence_ids:
        citation.append(VClaimVerdict(claim=VClaim(kind="citation", text="", value=None), supported=False,
                                      reason="generated block cites no evidence"))
    for s in sents:
        claims = [c for c in s.claims if coverage or c.kind != "unlicensed"]
        s.claims = claims
        results: dict[int, Result] = {id(c): _check_claim(c, s, ctx) for c in claims}
        _check_sequences(s, results, ctx)
        _check_binding(s, results)
        if previous is not None and s.index == 0 and previous.day == block.day:
            first = next((c for c in claims if c.kind == "sequence" and s.words and c.meta["i"] == s.words[0]), None)
            if first is not None and first.value in ("then", "later", "afterwards", "afterward", "next") \
                    and results[id(first)][0]:
                a, b = _block_start(previous, evidence_by_id), _block_start(block, evidence_by_id)
                if a is not None and b is not None and b < a:
                    results[id(first)] = (False, None, "block order contradicts time order of the previous block", [])
        vs = [VClaimVerdict(claim=c, supported=results[id(c)][0], evidence_id=results[id(c)][1],
                            reason=results[id(c)][2]) for c in claims]
        out_sents.append(SentenceVerdict(index=s.index, text=s.text, verdicts=vs,
                                         supported=all(v.supported for v in vs) and not citation))
        all_v += vs
    all_v = citation + all_v
    ok = all(v.supported for v in all_v)
    reason = "" if ok else "; ".join(f"[{v.claim.kind}] {v.claim.text!r}: {v.reason}" for v in all_v if not v.supported)
    return VBlockVerdict(block_id=block.id, supported=ok, verdicts=all_v, sentences=out_sents, reason=reason)


def verify_diary(blocks: Sequence[DiaryBlock], evidence: Iterable[Evidence] | dict[str, Evidence], *,
                 known_places: Iterable[str] | None = None, style: StyleProfile | None = None,
                 coverage: bool = True) -> DiaryReport:
    ev = evidence if isinstance(evidence, dict) else {e.id: e for e in evidence}
    known = list(known_places or [])
    rep = DiaryReport()
    prev: DiaryBlock | None = None
    for b in sorted(blocks, key=lambda b: (b.day, b.pos)):
        v = verify_block(b, ev, known_places=known, style=style, coverage=coverage, previous=prev)
        prev = b
        rep.verdicts.append(v)
        if v.testimony:
            rep.testimony_blocks += 1
            continue
        rep.blocks += 1
        rep.sentences += len(v.sentences)
        rep.claims += len(v.verdicts)
        rep.unsupported_claims += sum(not x.supported for x in v.verdicts)
        rep.unsupported_sentences += sum(not s.supported for s in v.sentences)
        rep.unsupported_blocks += not v.supported
        cit = [x for x in v.verdicts if x.claim.kind == "citation" and not x.supported]
        for x in cit:
            rep.failures.append(Failure(block_id=b.id, day=b.day, sentence=-1, sentence_text=b.text,
                                        kind="citation", claim_text=x.claim.text, reason=x.reason))
        for s in v.sentences:
            for x in s.verdicts:
                if not x.supported:
                    rep.failures.append(Failure(block_id=b.id, day=b.day, sentence=s.index, sentence_text=s.text,
                                                kind=x.claim.kind, claim_text=x.claim.text, reason=x.reason))
    rep.fabrication_rate = rep.unsupported_sentences / rep.sentences if rep.sentences else 0.0
    rep.claim_fabrication_rate = rep.unsupported_claims / rep.claims if rep.claims else 0.0
    return rep
