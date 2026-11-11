"""Text utilities for the faithfulness verifier: folding, tokens, sentences, numbers.

Pure stdlib, deterministic, never raises on arbitrary unicode.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .lexicon import NUMBER_MULT, NUMBER_WORDS

_TRANS = str.maketrans({
    "ı": "i", "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss", "æ": "ae", "Æ": "AE",
    "œ": "oe", "Œ": "OE", "þ": "th", "ð": "d", "’": "'", "‘": "'", "ʼ": "'", "`": "'",
})


def fold(s: str) -> str:
    """Case- and diacritic-insensitive form: 'İstanbul' → 'istanbul', 'Glière' → 'gliere'."""
    s = unicodedata.normalize("NFKD", s.translate(_TRANS))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def name_tokens(s: str) -> tuple[str, ...]:
    """Folded word/number tokens of a name; hyphens and apostrophes split ('Budapest-Keleti')."""
    return tuple(t for t in re.split(r"[^0-9a-z]+", fold(s)) if t)


def variants(w: str) -> list[str]:
    """Crude inflection variants of a folded word (for closed-list lookup, not linguistics)."""
    out = [w]
    if w.endswith("'s"):
        w = w[:-2]
        out.append(w)
    if w.endswith("ies") and len(w) > 4:
        out.append(w[:-3] + "y")
    if w.endswith("es") and len(w) > 3:
        out.append(w[:-2])
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        out.append(w[:-1])
    for suf in ("ed", "ing"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            base = w[: -len(suf)]
            out += [base, base + "e"]
            if len(base) > 2 and base[-1] == base[-2]:
                out.append(base[:-1])
            if suf == "ed" and base.endswith("i"):
                out.append(base[:-1] + "y")
    if w.endswith("ly") and len(w) > 4:
        out.append(w[:-2])
    return out


def same_word(a: str, b: str) -> bool:
    return bool(set(variants(a)) & set(variants(b)))


@dataclass
class Tok:
    text: str
    start: int
    end: int
    kind: str            # "w" word, "n" number, "p" punctuation/symbol
    low: str = ""
    cap: bool = False
    used: str | None = None     # what consumed this token ("fn", "safe", a claim kind, …)
    quoted: bool = False


_TOKEN_RE = re.compile(r"(?P<n>\d+(?:[.,:]\d+)*)|(?P<w>[^\W\d_]+(?:['’\-][^\W\d_]+)*)|(?P<p>[^\s\w]|_)", re.UNICODE)


def tokenize(text: str, offset: int = 0) -> list[Tok]:
    toks: list[Tok] = []
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup or "p"
        t = m.group()
        low = fold(t)
        toks.append(Tok(t, offset + m.start(), offset + m.end(), kind, low, t[:1].isupper()))
    return toks


_AMPM_RE = re.compile(r"\b([ap])\.m\.?", re.IGNORECASE)
_ABBREV = {"st", "mt", "mr", "mrs", "ms", "dr", "approx", "ca", "no", "vs", "e.g", "i.e", "etc", "hr", "min"}
_END_RE = re.compile(r"([.!?…]+)([\"'”’)\]]*)(\s+|$)|\n+")


def prepare(text: str) -> str:
    """Length-preserving normalisation applied before tokenising (so spans map to the original)."""
    text = unicodedata.normalize("NFC", text)
    return _AMPM_RE.sub(lambda m: (m.group(1) + "m").ljust(len(m.group())), text)


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Sentence spans (start, end) over `text`. Decimals and common abbreviations do not split."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in _END_RE.finditer(text):
        if m.group(1) == ".":
            before = re.search(r"([^\W\d_]+(?:\.[^\W\d_]+)?)$", text[start:m.start()])
            if before and before.group(1).lower() in _ABBREV and m.group(3):
                continue
        end = m.end()
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    if text[start:].strip():
        spans.append((start, len(text)))
    out = []
    for s, e in spans:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        out.append((s, e))
    return out


def parse_digits(s: str) -> tuple[float, int] | None:
    """'2,352' → (2352, 0 decimals); '6.2' → (6.2, 1); '6,2' → (6.2, 1). None if not a plain number."""
    if ":" in s:
        return None
    try:
        if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
            s = s.replace(",", "")
        elif re.fullmatch(r"\d+,\d{1,2}", s):
            s = s.replace(",", ".")
        if not re.fullmatch(r"\d+(\.\d+)?", s):
            return None
        dec = len(s.split(".")[1]) if "." in s else 0
        return float(s), dec
    except (ValueError, OverflowError):
        return None


def parse_number_word(low: str) -> float | None:
    """'twelve' → 12, 'twenty-five' → 25. Single token only."""
    if low in NUMBER_WORDS:
        return float(NUMBER_WORDS[low])
    parts = low.split("-")
    if len(parts) == 2 and parts[0] in NUMBER_WORDS and parts[1] in NUMBER_WORDS:
        a, b = NUMBER_WORDS[parts[0]], NUMBER_WORDS[parts[1]]
        if a >= 20 and a % 10 == 0 and 0 < b < 10:
            return float(a + b)
    return None


def read_number(toks: list[Tok], i: int) -> tuple[float, int, int] | None:
    """Read a quantity starting at token i. Returns (value, decimals, next index).

    Handles digits, number words, 'three hundred', 'two and a half', 'a dozen'.
    """
    if i >= len(toks):
        return None
    t = toks[i]
    val: float | None = None
    dec = 0
    j = i + 1
    if t.kind == "n":
        p = parse_digits(t.text)
        if p is None:
            return None
        val, dec = p
    elif t.kind == "w":
        val = parse_number_word(t.low)
        if val is None:
            return None
        if j < len(toks) and toks[j].kind == "w" and toks[j].low in NUMBER_WORDS and val >= 20 and val % 10 == 0 \
                and NUMBER_WORDS[toks[j].low] < 10:
            val += NUMBER_WORDS[toks[j].low]
            j += 1
    if val is None:
        return None
    while j < len(toks) and toks[j].kind == "w" and toks[j].low in NUMBER_MULT:
        val *= NUMBER_MULT[toks[j].low]
        j += 1
    # "two and a half"
    if j + 2 < len(toks) and [x.low for x in toks[j:j + 3]] == ["and", "a", "half"]:
        val += 0.5
        dec = max(dec, 1)
        j += 3
    return val, dec, j
