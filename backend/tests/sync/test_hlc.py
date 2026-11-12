import pytest
from hypothesis import given, strategies as st

from atlas.sync.hlc import HLC, clamp, format_hlc, parse_hlc, successor

T = 1_780_000_000_000
devices = st.sampled_from(["phone", "web", "a-b-c", "x.1", "pipeline"])
stamps = st.tuples(st.integers(0, 10**13 - 1), st.integers(0, 9999), devices)


def test_format_and_parse_roundtrip():
    s = format_hlc(T, 7, "phone-2")
    assert s == "1780000000000-0007-phone-2"
    t = parse_hlc(s)
    assert (t.ms, t.counter, t.device) == (T, 7, "phone-2") and str(t) == s


@pytest.mark.parametrize("bad", ["", "1-2-x", "1780000000000-0007-", "1780000000000-00a7-x", "x" * 30,
                                 "1780000000000-0007-has space", None, 5])
def test_parse_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_hlc(bad)


@given(stamps, stamps)
def test_string_order_is_tuple_order(a, b):
    assert (format_hlc(*a) < format_hlc(*b)) == (a < b)


def test_now_is_strictly_monotonic_even_if_wall_clock_stalls_or_goes_back():
    c = HLC("phone")
    seq = [c.now(T), c.now(T), c.now(T - 5000), c.now(T + 1), c.now(T + 1)]
    assert seq == sorted(set(seq))
    assert seq[1] == format_hlc(T, 1, "phone") and seq[3] == format_hlc(T + 1, 0, "phone")


def test_counter_overflow_rolls_into_next_ms():
    c = HLC("phone", T, 9999)
    assert c.now(T) == format_hlc(T + 1, 0, "phone")
    assert successor(format_hlc(T, 9999, "web"), "phone") == format_hlc(T + 1, 0, "phone")


def test_update_is_after_both_remote_and_local():
    c = HLC("phone")
    c.now(T)
    remote = format_hlc(T + 2 * 86_400_000, 3, "web")  # we are two days behind
    got = c.update(remote, T + 10)
    assert got > remote and parse_hlc(got).device == "phone"
    assert c.now(T + 20) > got  # stays ahead although our wall clock is far behind


@given(st.lists(st.one_of(st.tuples(st.just("now"), st.integers(T - 10**6, T + 10**6)),
                          st.tuples(st.just("obs"), stamps)), max_size=40))
def test_issued_timestamps_always_increase_and_exceed_everything_observed(ops):
    c, last, seen = HLC("phone"), "", ""
    for kind, arg in ops:
        if kind == "now":
            if c.ms >= 10**13 - 2:
                return
            s = c.now(arg)
            assert s > last and s[:18] > seen[:18]
            last = s
        else:
            if arg[0] >= 10**13 - 2:
                continue
            c.observe(format_hlc(*arg))
            seen = max(seen, format_hlc(*arg))


def test_clamp_future_to_server_time_keeps_counter_and_device():
    far = format_hlc(T + 2 * 86_400_000, 12, "phone")
    assert clamp(far, T) == format_hlc(T, 12, "phone")
    ok = format_hlc(T + 299_999, 1, "phone")
    assert clamp(ok, T) == ok  # within tolerance
    assert clamp(format_hlc(T + 300_001, 0, "p"), T) == format_hlc(T, 0, "p")
    past = format_hlc(T - 2 * 86_400_000, 0, "phone")
    assert clamp(past, T) == past  # the past is not rewritten (see hlc.py docstring)
