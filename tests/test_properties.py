"""Property tests: peak window, expected interval count, settled-history guard.

Dev-only (Hypothesis); skipped visibly where it is not installed.
"""

import calendar
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("hypothesis", reason="hypothesis is a dev-only dependency (requirements-dev.txt)")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hypothesis_gate  # noqa: E402,F401  (loads the fixed profile)
from hypothesis import assume, given, strategies as st  # noqa: E402

from src import config, main  # noqa: E402
from src.analyse import is_peak  # noqa: E402

days = st.dates(min_value=datetime(2003, 7, 1).date(), max_value=datetime(2030, 12, 31).date())


def _day_stamps(day, freq: str) -> pd.Series:
    """Every interval END stamp of one calendar day: 00:step ... next-day 00:00."""
    start = pd.Timestamp(day)
    return pd.Series(pd.date_range(start + pd.Timedelta(freq), start + pd.Timedelta("1D"), freq=freq))


# ----------------------------------------------------------------------------- is_peak
@given(day=days, freq=st.sampled_from(["5min", "30min"]))
def test_is_peak_one_day(day, freq):
    stamps = _day_stamps(day, freq)
    mask = is_peak(stamps)
    peak = stamps[mask]
    if day.weekday() >= 5:
        # A weekend day has no peak interval. The final stamp (next-day 00:00) is off-peak anyway.
        assert len(peak) == 0
        return
    assert len(peak) == (180 if freq == "5min" else 30)
    step = pd.Timedelta(freq)
    # contiguous, 07:00 < first <= 22:00 (end stamps)
    assert (peak.diff().dropna() == step).all()
    assert peak.iloc[0] == pd.Timestamp(day) + pd.Timedelta(hours=7) + step
    assert peak.iloc[-1] == pd.Timestamp(day) + pd.Timedelta(hours=22)


# ----------------------------------------------------------------------------- expected_interval_count
def test_expected_interval_count_every_month():
    for year in range(2003, 2031):
        for month in range(1, 13):
            if (year, month) < (2003, 7):
                continue
            n_days = calendar.monthrange(year, month)[1]
            per_day = 288 if (year, month) >= (2021, 10) else 48
            assert config.expected_interval_count(year, month) == n_days * per_day, (year, month)
            # equals the number of end stamps in the month's file (00:step on the 1st ... 00:00 on the next)
            step = timedelta(minutes=5 if per_day == 288 else 30)
            first = datetime(year, month, 1)
            nxt = datetime(year + (month == 12), month % 12 + 1, 1)
            assert (nxt - first) // step == config.expected_interval_count(year, month)


# ----------------------------------------------------------------------------- settled-history guard
COLS = ["region", "year_month", "rrp_nominal", "peak_rrp_nominal", "total_intervals", "peak_intervals", "carbon_flag"]
MONTHS = [f"2020-{m:02d}" for m in range(1, 13)]
REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]
values = st.floats(min_value=-1000, max_value=20000, allow_nan=False, allow_infinity=False)

rows_st = st.dictionaries(
    keys=st.tuples(st.sampled_from(REGIONS), st.sampled_from(MONTHS)),
    values=st.tuples(values, values, st.integers(0, 10000), st.integers(0, 10000), st.booleans()),
    min_size=1,
    max_size=20,
)


def _frame(d):
    return pd.DataFrame([(r, m, *v) for (r, m), v in sorted(d.items())], columns=COLS)


mutable_st = st.sets(st.sampled_from(MONTHS), max_size=3)


def _raises(before, after, mutable):
    try:
        main._assert_settled_history_unchanged(before, after, mutable)
    except RuntimeError:
        return True
    return False


@given(d=rows_st, mutable=mutable_st, extra=rows_st)
def test_guard_identity_and_added_rows_never_raise(d, mutable, extra):
    before = _frame(d)
    assert not _raises(before, _frame(d), mutable)
    # adding rows (new keys) anywhere never raises; existing keys keep their values
    grown = {**extra, **d}
    assert not _raises(before, _frame(grown), mutable)


def _change_one(d, key, col, delta):
    v = list(d[key])
    v[col] = (not v[col]) if col == 4 else v[col] + delta
    changed = dict(d)
    changed[key] = tuple(v)
    return changed


@given(d=rows_st, mutable=mutable_st, data=st.data())
def test_guard_any_changed_settled_cell_raises(d, mutable, data):
    settled = [k for k in d if k[1] not in mutable]
    assume(settled)
    key = data.draw(st.sampled_from(sorted(settled)))
    col = data.draw(st.integers(0, 4))
    delta = data.draw(st.floats(min_value=0.01, max_value=100, allow_nan=False, allow_infinity=False))
    if col in (2, 3):
        delta = int(delta) + 1
    if col in (0, 1):
        # DIVERGENCE (pinned below): assert_frame_equal keeps pandas' default tolerance, so a price change
        # within atol=1e-8 + rtol=1e-5 * max(|old|, |new|) passes the guard. Exactly that band is excluded;
        # every change above it must raise.
        old = d[key][col]
        assume(delta > 1e-8 + 1e-5 * max(abs(old), abs(old + delta)))
    assert _raises(_frame(d), _frame(_change_one(d, key, col, delta)), mutable)


@pytest.mark.xfail(
    strict=True,
    reason="counterexample: settled rrp_nominal 1000.00 -> 1000.01 is not detected; assert_frame_equal "
    "(check_dtype=False) keeps pandas' default rtol=1e-5. Reachable because rrp_nominal is round(mean, 2) "
    "(src/analyse.py), so the smallest real change is 0.01, undetected only when the monthly mean is "
    ">= $1000/MWh. Proposed fix: assert_frame_equal(..., rtol=0, atol=0) in _assert_settled_history_unchanged.",
)
def test_guard_rejects_tiny_relative_change_in_settled_price():
    d = {("NSW1", "2020-01"): (1000.0, 0.0, 0, 0, False)}
    assert _raises(_frame(d), _frame(_change_one(d, ("NSW1", "2020-01"), 0, 0.01)), set())


@given(d=rows_st, mutable=mutable_st, data=st.data())
def test_guard_changing_a_mutable_month_never_raises(d, mutable, data):
    muts = [k for k in d if k[1] in mutable]
    if not muts:
        return
    key = data.draw(st.sampled_from(sorted(muts)))
    changed = dict(d)
    changed[key] = (d[key][0] + 1.5, d[key][1] + 1.5, d[key][2] + 1, d[key][3] + 1, not d[key][4])
    assert not _raises(_frame(d), _frame(changed), mutable)
