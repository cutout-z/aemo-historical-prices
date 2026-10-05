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
                            year: int, month: int) -> dict:
    """Calculate monthly mean RRP and peak RRP from interval data.

    Input: DataFrame with [SETTLEMENTDATE, RRP] for a single region/month.
    Output: dict with rrp_nominal, peak_rrp_nominal, interval counts.
    """
    if df.empty:
        return None

    total_intervals = len(df)
    rrp_nominal = round(df["RRP"].mean(), 2)

    # Peak filtering
    peak_mask = is_peak(df["SETTLEMENTDATE"])
    peak_df = df[peak_mask]
    peak_intervals = len(peak_df)

    if peak_intervals > 0:
        peak_rrp_nominal = round(peak_df["RRP"].mean(), 2)
    else:
        peak_rrp_nominal = rrp_nominal  # Fallback if no peak intervals

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
    Output: dict of monthly statistics.
    """
    if raw_df.empty:
        return None

    # Filter to just the columns we need
    df = raw_df[["SETTLEMENTDATE", "RRP"]].copy()

    stats = calculate_monthly_stats(df, region, year, month)

    if stats:
        _check_interval_count(region, year, month, stats["total_intervals"])

    return stats


def _check_interval_count(region: str, year: int, month: int, total: int):
    """Log warning if interval count is outside expected range."""
    # Pre-Oct 2021: 30-min intervals = 48/day × 28-31 days = 1344-1488
    # Post-Oct 2021: 5-min intervals = 288/day × 28-31 days = 8064-8928
    from datetime import datetime
    if datetime(year, month, 1) >= config.FORMAT_CHANGE_DATE:
        if total < 7500 or total > 9500:
            logger.warning(
                f"Unexpected interval count for {region} {year}-{month:02d}: "
                f"{total} (expected ~8064-8928 for 5-min data)"
            )
    else:
        if total < 1200 or total > 1600:
            logger.warning(
                f"Unexpected interval count for {region} {year}-{month:02d}: "
                f"{total} (expected ~1344-1488 for 30-min data)"
            )
