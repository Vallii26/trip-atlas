"""Three-way merge of short prose (a diary block: one to a few sentences).

Policy — "a human should never be surprised by an auto-merged sentence"
-----------------------------------------------------------------------
Text is tokenised into words / whitespace / punctuation (never inside a word, never inside an
emoji cluster), both sides are diffed against the base, and each side's changes become *hunks*
(base range → replacement).  Two hunks from different sides are **independent** when

* they are the identical edit (same range, same replacement), or
* they fall in **different sentences** of the base, or
* one of them inserts a whole new sentence at a sentence boundary (and the other is not an
  insertion at that same spot), or
* they are in the same sentence but at least ``MIN_GAP_WORDS`` unchanged words lie between them
  ("fixed a typo at the start" + "rewrote the last clause").

Anything else — overlapping, adjacent, or merely close edits in one sentence — is a conflict:
a word-level merge there produces grammatical chimeras ("We ran slowly to the big old market").
On conflict NOTHING is merged: ``clean`` is False and the caller keeps one whole version and
surfaces the other whole version.  Both are texts a person actually typed.

Whitespace-only changes never cause a conflict; if one touches another edit it is dropped.
The merge is deterministic and symmetric: ``merge3(o, a, b)`` and ``merge3(o, b, a)`` agree on
``clean`` and, when clean, on ``text``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

MIN_GAP_WORDS = 4

_TERMINATORS = frozenset(".!?…")
_CLOSERS = frozenset("\"'”’»)]")
_ABBREVIATIONS = frozenset({"mr", "mrs", "ms", "dr", "st", "mt", "vs", "prof", "sr", "jr", "approx", "ca"})


@dataclass(frozen=True)
class TextConflict:
    base: str
    a: str
    b: str


@dataclass(frozen=True)
class MergeResult:
    text: str  # merged text when clean; when not clean it is `a` unchanged (callers pick a winner)
    clean: bool
    conflicts: list[TextConflict] = field(default_factory=list)


# ---------------------------------------------------------------- tokenising

def _is_word_char(c: str) -> bool:
    return c.isalnum() or c == "_"


def _is_extender(c: str) -> bool:
    """Characters that belong to the previous one: combining marks, ZWJ, variation selectors,
    emoji skin tones, emoji tag characters."""
    o = ord(c)
    return (
        unicodedata.category(c).startswith("M")
        or o == 0x200D
        or 0xFE00 <= o <= 0xFE0F
        or 0x1F3FB <= o <= 0x1F3FF
        or 0xE0020 <= o <= 0xE007F
    )


def _is_regional(c: str) -> bool:
    return 0x1F1E6 <= ord(c) <= 0x1F1FF


def tokenize(text: str) -> list[str]:
    """Lossless: ``"".join(tokenize(t)) == t``.  Tokens are whitespace runs, words (including
    inner apostrophes/hyphens and digit groups like 17:30 or 1,200) and punctuation/emoji."""
    toks: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        j = i + 1
        if c.isspace():
            while j < n and text[j].isspace():
                j += 1
        elif _is_word_char(c):
            while j < n:
                d = text[j]
                if _is_word_char(d) or _is_extender(d):
                    j += 1
                elif d in "'’-" and j + 1 < n and _is_word_char(text[j + 1]):
                    j += 2
                elif d in ".,:" and text[j - 1].isdigit() and j + 1 < n and text[j + 1].isdigit():
                    j += 2
                else:
                    break
        else:
            if _is_regional(c):
                if j < n and _is_regional(text[j]):  # flag = pair of regional indicators
                    j += 1
            elif not _is_extender(c):
                while j < n and text[j] == c:  # "...", "!!", "--"
                    j += 1
            while j < n and _is_extender(text[j]):
                zwj = text[j] == "‍"
                j += 1
                if zwj and j < n and not text[j].isspace():  # emoji ZWJ sequence
                    j += 1
        toks.append(text[i:j])
        i = j
    return toks


def _ws(tok: str) -> bool:
    return tok.isspace()


def _is_word(tok: str) -> bool:
    return _is_word_char(tok[0])


def _is_terminator(tok: str) -> bool:
    return all(ch in _TERMINATORS for ch in tok)


def _is_closer(tok: str) -> bool:
    return len(tok) == 1 and tok in _CLOSERS


# ---------------------------------------------------------------- sentences

def _ends_at(toks: list[str], i: int) -> bool:
    """Does the terminator token at ``i`` end a sentence?  Deliberately conservative: when in
    doubt say no (fewer boundaries → fewer auto-merges)."""
    n = len(toks)
    j = i + 1
    while j < n and _is_closer(toks[j]):
        j += 1
    if j >= n:
        return True
    if not _ws(toks[j]):
        return False
    if "\n" in toks[j] or j + 1 >= n:
        return True
    if toks[j + 1][0].islower():
        return False
    if toks[i] == "." and i > 0:
        prev = toks[i - 1]
        if prev.lower() in _ABBREVIATIONS or (len(prev) == 1 and prev.isalpha()):
            return False
    return True


def _sentences(toks: list[str]) -> tuple[list[int], set[int]]:
    """Sentence index of every token, and the set of sentences that are properly closed
    (by terminal punctuation or a line break).  Trailing whitespace belongs to its sentence."""
    n = len(toks)
    sent = [0] * n
    closed: set[int] = set()
    k, i, has_content = 0, 0, False
    while i < n:
        t = toks[i]
        sent[i] = k
        if _ws(t):
            if "\n" in t and has_content:
                closed.add(k)
                k, has_content = k + 1, False
            i += 1
            continue
        has_content = True
        if _is_terminator(t) and _ends_at(toks, i):
            j = i + 1
            while j < n and _is_closer(toks[j]):
                sent[j] = k
                j += 1
            if j < n and _ws(toks[j]):
                sent[j] = k
                j += 1
            closed.add(k)
            k, has_content, i = k + 1, False, j
            continue
        i += 1
    return sent, closed


def _completes_sentence(repl: tuple[str, ...]) -> bool:
    k = len(repl) - 1
    if k >= 0 and _ws(repl[k]):
        if "\n" in repl[k]:
            return True
        k -= 1
    while k >= 0 and _is_closer(repl[k]):
        k -= 1
    return k >= 0 and _is_terminator(repl[k])


# ---------------------------------------------------------------- hunks

@dataclass(frozen=True)
class _Hunk:
    i: int  # base[i:j] is replaced by repl; i == j is a pure insertion before base[i]
    j: int
    repl: tuple[str, ...]


def _hunks(base: list[str], side: list[str]) -> list[_Hunk]:
    ops = SequenceMatcher(None, base, side, autojunk=False).get_opcodes()
    raw = [(i1, i2, j1, j2) for tag, i1, i2, j1, j2 in ops if tag != "equal"]
    merged: list[tuple[int, int, int, int]] = []
    for h in raw:
        # Two changes separated only by whitespace are one change ("big market" → "old bazaar").
        if merged and all(_ws(t) for t in base[merged[-1][1]:h[0]]):
            p = merged[-1]
            merged[-1] = (p[0], h[1], p[2], h[3])
        else:
            merged.append(h)
    return [_Hunk(i1, i2, tuple(side[j1:j2])) for i1, i2, j1, j2 in merged]


def _classify(h: _Hunk, base: list[str], sent: list[int], closed: set[int]) -> tuple[str, frozenset[int]]:
    """→ (kind, sentences touched).  kind ∈ cosmetic | sentence | edit."""
    removed = base[h.i:h.j]
    if all(_ws(t) for t in removed) and all(_ws(t) for t in h.repl):
        return "cosmetic", frozenset()
    touched = frozenset(sent[x] for x in range(h.i, h.j) if not _ws(base[x]))
    if touched:
        return "edit", touched
    # Pure insertion (possibly swallowing whitespace) between base tokens p and q.
    p = next((x for x in range(h.i - 1, -1, -1) if not _ws(base[x])), None)
    q = next((x for x in range(h.j, len(base)) if not _ws(base[x])), None)
    if p is None:
        boundary = True
    elif q is None:
        boundary = sent[p] in closed
    else:
        boundary = sent[p] != sent[q]
    if boundary:
        if q is None or _completes_sentence(h.repl):
            return "sentence", frozenset()  # a whole new sentence between/after existing ones
        return "edit", frozenset({sent[q]})  # text put in front of the following sentence
    return "edit", frozenset(sent[x] for x in (p, q) if x is not None)


def _overlap(x: _Hunk, y: _Hunk) -> bool:
    if x.i == x.j and y.i == y.j:
        return x.i == y.i
    if x.i == x.j:
        return y.i < x.i < y.j
    if y.i == y.j:
        return x.i < y.i < x.j
    return x.i < y.j and y.i < x.j


def _touch(x: _Hunk, y: _Hunk) -> bool:
    return x.i <= y.j and y.i <= x.j


def _gap_words(x: _Hunk, y: _Hunk, base: list[str]) -> int:
    lo, hi = (x, y) if (x.i, x.j) <= (y.i, y.j) else (y, x)
    return sum(1 for t in base[lo.j:hi.i] if _is_word(t))


# ---------------------------------------------------------------- merge

def merge3(base: str, a: str, b: str) -> MergeResult:
    if a == b:
        return MergeResult(a, True)
    if a == base:
        return MergeResult(b, True)
    if b == base:
        return MergeResult(a, True)

    tb = tokenize(base)
    sent, closed = _sentences(tb)
    ha, hb = _hunks(tb, tokenize(a)), _hunks(tb, tokenize(b))
    kind = {h: _classify(h, tb, sent, closed) for h in (*ha, *hb)}

    # Whitespace-only changes are never worth a conflict: drop any that touch a different
    # change from the other side (e.g. one side trimmed a trailing space, the other appended).
    def cosmetic_clash(h: _Hunk, others: list[_Hunk]) -> bool:
        return kind[h][0] == "cosmetic" and any(o != h and _touch(h, o) for o in others)

    ka = [h for h in ha if not cosmetic_clash(h, hb)]
    kb = [h for h in hb if not cosmetic_clash(h, ha)]

    conflicts: list[TextConflict] = []
    for x in ka:
        for y in kb:
            if x == y:
                continue
            (kx, fx), (ky, fy) = kind[x], kind[y]
            if _overlap(x, y):
                bad = True
            elif kx != "edit" or ky != "edit" or not (fx & fy):
                bad = False
            else:
                bad = _gap_words(x, y, tb) < MIN_GAP_WORDS
            if bad:
                lo, hi = min(x.i, y.i), max(x.j, y.j)
                conflicts.append(TextConflict("".join(tb[lo:hi]), "".join(x.repl), "".join(y.repl)))
    if conflicts:
        return MergeResult(a, False, conflicts)

    out: list[str] = []
    cur = 0
    for h in sorted(set(ka) | set(kb), key=lambda h: (h.i, h.j)):
        if h.i < cur:  # cannot happen for independent hunks; refuse rather than guess
            return MergeResult(a, False, [TextConflict(base, a, b)])
        out.extend(tb[cur:h.i])
        out.extend(h.repl)
        cur = h.j
    out.extend(tb[cur:])
    return MergeResult("".join(out), True)
