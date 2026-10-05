"""Monthly price aggregation with peak-hour filtering."""

import logging

import pandas as pd

from . import config

logger = logging.getLogger(__name__)


def is_peak(dt_series: pd.Series) -> pd.Series:
    """Return boolean mask for peak intervals.

    Peak = Mon-Fri, 07:00-22:00 AEST (public holidays are NOT excluded).
    NEM uses AEST year-round. SETTLEMENTDATE marks the interval END, so an interval belongs to
    the 07:00-22:00 window when it ENDS after 07:00 and at or before 22:00:
      - 30-min data (to Sep 2021): the first peak interval ends 07:30 (covers 07:00-07:30) and
        the last ends 22:00 (covers 21:30-22:00).
      - 5-min data (from Oct 2021): the first ends 07:05 and the last ends 22:00.
    The interval ending exactly 07:00 covers 06:30-07:00 (or 06:55-07:00) and is off-peak.
    Every peak interval ends on the same calendar day it starts, so the weekday of the end stamp
    is the weekday of the interval.
    """
    weekday = dt_series.dt.dayofweek < 5  # Mon=0 to Fri=4
    minute_of_day = dt_series.dt.hour * 60 + dt_series.dt.minute
    in_window = (
        (minute_of_day > config.PEAK_START_HOUR * 60)
        & (minute_of_day <= config.PEAK_END_HOUR * 60)
    )
    return weekday & in_window


def calculate_monthly_stats(df: pd.DataFrame, region: str,
                            year: int, month: int) -> dict | None:
    """Calculate monthly mean RRP and peak RRP from interval data.

    Input: DataFrame with [SETTLEMENTDATE, RRP] for a single region/month.
    Output: dict with rrp_nominal, peak_rrp_nominal, interval counts.

    Intervals with no usable RRP are dropped BEFORE counting, so a gap shows up as a short count
    (and the month is then rejected as incomplete) instead of being counted but ignored by the mean.
    """
    if df.empty:
        return None

    df = df[df["RRP"].notna()]
    if df.empty:
        return None

    total_intervals = len(df)
    rrp_nominal = round(df["RRP"].mean(), 2)

    # Peak filtering
    peak_mask = is_peak(df["SETTLEMENTDATE"])
    peak_df = df[peak_mask]
    peak_intervals = len(peak_df)
    if peak_intervals == 0:
        # A real month always has peak intervals. Never substitute the all-hours mean for a
        # missing peak: the figure would carry the wrong label.
        logger.error(f"No peak intervals for {region} {year}-{month:02d}; month rejected")
        return None
    peak_rrp_nominal = round(peak_df["RRP"].mean(), 2)

    # Carbon tax flag
    month_date = pd.Timestamp(year, month, 1)
    carbon_flag = (
        month_date >= config.CARBON_TAX_START
        and month_date <= config.CARBON_TAX_END
    )

    return {
        "region": region,
        "year_month": f"{year}-{month:02d}",
        "rrp_nominal": rrp_nominal,
        "peak_rrp_nominal": peak_rrp_nominal,
        "total_intervals": total_intervals,
        "peak_intervals": peak_intervals,
        "carbon_flag": carbon_flag,
    }


def analyse_month(raw_df: pd.DataFrame, region: str,
                  year: int, month: int) -> dict | None:
    """Full analysis pipeline for a single region/month.

    Input: DataFrame from download_month with [REGION, SETTLEMENTDATE, RRP, ...].
    Output: dict of monthly statistics, or None when the month is empty or INCOMPLETE.

    A month is complete only when it holds exactly the expected number of intervals
    (config.expected_interval_count). A partial month is not published: the next run retries it
    (the recent months are always re-downloaded), so a month appears once AEMO has published all of it.
    """
    if raw_df.empty:
        return None

    # Filter to just the columns we need
    df = raw_df[["SETTLEMENTDATE", "RRP"]].copy()

    stats = calculate_monthly_stats(df, region, year, month)
    if not stats:
        return None

    expected = config.expected_interval_count(year, month)
    if stats["total_intervals"] != expected:
        logger.warning(
            f"Incomplete month {region} {year}-{month:02d}: {stats['total_intervals']} usable "
            f"intervals, expected exactly {expected}; not published"
        )
        return None

    return stats
