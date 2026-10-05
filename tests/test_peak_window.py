"""Boundary tests for the peak window (Mon-Fri 07:00-22:00 AEST, interval-END timestamps).

Runs under pytest or directly:  python tests/test_peak_window.py
AEMO's SETTLEMENTDATE marks the END of an interval, so the interval ending exactly 07:00 covers
06:30-07:00 (30-min data) or 06:55-07:00 (5-min data) and is off-peak, while the interval ending
exactly 22:00 is the last peak interval. A filter on the raw end-stamp hour gets both edges wrong.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyse import calculate_monthly_stats, is_peak  # noqa: E402

MON = "2026-03-02"   # a Monday
SAT = "2026-03-07"
SUN = "2026-03-08"


def _day(date: str, freq: str) -> pd.Series:
    """Every interval END stamp of one day: 00:{step} ... next-day 00:00."""
    start = pd.Timestamp(date)
    return pd.Series(pd.date_range(start + pd.Timedelta(freq), start + pd.Timedelta("1D"), freq=freq))


def _peak_stamps(date: str, freq: str) -> list[str]:
    s = _day(date, freq)
    return [t.strftime("%H:%M") for t in s[is_peak(s)]]


def test_30min_edges():
    stamps = _peak_stamps(MON, "30min")
    assert stamps[0] == "07:30", stamps[0]      # covers 07:00-07:30
    assert stamps[-1] == "22:00", stamps[-1]    # covers 21:30-22:00
    assert "07:00" not in stamps                # covers 06:30-07:00
    assert "22:30" not in stamps                # covers 22:00-22:30
    assert len(stamps) == 30                    # 15 hours x 2


def test_5min_edges():
    stamps = _peak_stamps(MON, "5min")
    assert stamps[0] == "07:05", stamps[0]      # covers 07:00-07:05
    assert stamps[-1] == "22:00", stamps[-1]    # covers 21:55-22:00
    assert "07:00" not in stamps                # covers 06:55-07:00
    assert "22:05" not in stamps
    assert len(stamps) == 180                   # 15 hours x 12


def test_weekend_is_never_peak():
    for date in (SAT, SUN):
        for freq in ("30min", "5min"):
            s = _day(date, freq)
            assert not is_peak(s).any(), (date, freq)


def test_friday_last_interval_is_peak_but_saturday_midnight_is_not():
    # The interval ending 00:00 Saturday is Friday's last interval of the day: off-peak by hour.
    s = pd.Series(pd.to_datetime(["2026-03-06 22:00", "2026-03-07 00:00"]))
    assert list(is_peak(s)) == [True, False]


def test_monthly_peak_mean_uses_the_right_intervals():
    # One Monday of 30-min intervals priced by their start hour: off-peak $0, the 07:00-22:00
    # window $100. The corrected filter averages exactly $100; the old hour>=7 & hour<22 filter
    # picked up the 06:30-07:00 interval ($0) and dropped 21:30-22:00 ($100), so it was not $100.
    ends = _day(MON, "30min")
    starts = ends - pd.Timedelta("30min")
    price = ((starts >= pd.Timestamp(MON) + pd.Timedelta("7h")) &
             (starts < pd.Timestamp(MON) + pd.Timedelta("22h"))).astype(float) * 100.0
    df = pd.DataFrame({"SETTLEMENTDATE": ends, "RRP": price})
    stats = calculate_monthly_stats(df, "NSW1", 2026, 3)
    assert stats["peak_rrp_nominal"] == 100.0, stats
    assert stats["peak_intervals"] == 30, stats


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
    print(f"\n{len(tests)} peak-window tests passed")
