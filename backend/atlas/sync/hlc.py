"""Hybrid logical clock (ARCHITECTURE §5).

String form ``"<ms:013d>-<counter:04d>-<device>"``.  Because ``ms`` and ``counter`` are
fixed-width and come first, plain string comparison is the total order
``(ms, counter, device)``.  Pure: wall time is always passed in.

Clock skew, and what each side does about it
--------------------------------------------
* Clock in the FUTURE.  The server ``clamp``s any timestamp more than ``max_ahead_ms`` ahead of
  its own clock down to server time, so such a device's edits are effectively stamped "when the
  server received them" and cannot win every last-writer-wins race forever.  Clamping is not
  order-preserving for one device ((T1,5) and (T2,0) clamp to (S,5) and (S,0)), so the merge
  rules never use HLC order between two writes of the SAME device: arrival order decides there
  (see ``merge._beats``).
* Clock in the PAST.  Three things keep such a device usable:
  1. merge rules compare the mutation's ``base`` with the server value first; an edit made on
     top of the current value applies whatever its timestamp says (and is re-stamped just after
     the value it replaced, see ``merge._stamp``);
  2. the client ``observe``s the hlc of every doc it receives, so its own clock never runs
     behind anything it has seen (the normal HLC receive rule);
  3. responses carry ``server_ms`` so a client can correct its wall clock by the offset.
  What remains: an edit made OFFLINE by a slow-clock device, concurrent with another device's
  edit, loses the LWW race even if it was later in real time.  For merge (text) fields the loser
  is kept as a conflict alternative, so nothing is lost; for scalars the loser is dropped and
  reported.  That is accepted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_COUNTER = 9999
MAX_MS = 10**13 - 1
_HLC_RE = re.compile(r"^(\d{13})-(\d{4})-(.+)$", re.DOTALL)
_DEVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")


def valid_device(device: str) -> bool:
    return isinstance(device, str) and bool(_DEVICE_RE.match(device))


@dataclass(frozen=True, order=True)
class Timestamp:
    ms: int
    counter: int
    device: str

    def __str__(self) -> str:
        return format_hlc(self.ms, self.counter, self.device)


def format_hlc(ms: int, counter: int, device: str) -> str:
    if not 0 <= ms <= MAX_MS:
        raise ValueError(f"hlc ms out of range: {ms}")
    if not 0 <= counter <= MAX_COUNTER:
        raise ValueError(f"hlc counter out of range: {counter}")
    if not valid_device(device):
        raise ValueError(f"invalid device id: {device!r}")
    return f"{ms:013d}-{counter:04d}-{device}"


def parse_hlc(s: str) -> Timestamp:
    m = _HLC_RE.match(s) if isinstance(s, str) else None
    if not m or not valid_device(m.group(3)):
        raise ValueError(f"invalid hlc: {s!r}")
    return Timestamp(int(m.group(1)), int(m.group(2)), m.group(3))


def _next(ms: int, counter: int) -> tuple[int, int]:
    """Smallest (ms, counter) strictly greater; a full counter rolls into the next millisecond."""
    return (ms, counter + 1) if counter < MAX_COUNTER else (ms + 1, 0)


def successor(hlc: str, device: str) -> str:
    """A timestamp for ``device`` that sorts strictly after ``hlc``."""
    t = parse_hlc(hlc)
    return format_hlc(*_next(t.ms, t.counter), device)


def clamp(hlc: str, server_ms: int, max_ahead_ms: int = 300_000) -> str:
    """Server side: rewrite a timestamp too far in the future to server time.

    Counter and device are kept.  Timestamps in the past are left alone (see module docstring).
    """
    t = parse_hlc(hlc)
    if t.ms > server_ms + max_ahead_ms:
        return format_hlc(server_ms, t.counter, t.device)
    return hlc


class HLC:
    """One device's clock.  ``now`` for a local event, ``observe``/``update`` for remote ones."""

    def __init__(self, device: str, ms: int = 0, counter: int = 0) -> None:
        if not valid_device(device):
            raise ValueError(f"invalid device id: {device!r}")
        self.device = device
        self.ms = ms
        self.counter = counter

    def now(self, wall_ms: int) -> str:
        """Timestamp for a local event; strictly greater than every timestamp issued or observed."""
        if wall_ms > self.ms:
            self.ms, self.counter = wall_ms, 0
        else:  # wall clock stalled or went backwards: stay monotonic on the counter
            self.ms, self.counter = _next(self.ms, self.counter)
        return format_hlc(self.ms, self.counter, self.device)

    def observe(self, remote: str) -> None:
        """Fold a remote timestamp in without issuing one (cheap; used for every pulled doc)."""
        t = parse_hlc(remote)
        if (t.ms, t.counter) > (self.ms, self.counter):
            self.ms, self.counter = t.ms, t.counter

    def update(self, remote: str, wall_ms: int) -> str:
        """HLC receive rule: observe ``remote`` then issue a timestamp greater than both."""
        self.observe(remote)
        return self.now(wall_ms)

    def __str__(self) -> str:
        return format_hlc(self.ms, self.counter, self.device)
