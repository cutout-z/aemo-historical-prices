"""Monthly price aggregation with peak-hour filtering."""

import logging

import pandas as pd

from . import config

logger = logging.getLogger(__name__)


def is_peak(dt_series: pd.Series) -> pd.Series:
    """Return boolean mask for peak intervals.

    Peak = weekdays (Mon-Fri), hours 7-21 (7am-10pm AEST).
    NEM uses AEST year-round. SETTLEMENTDATE marks interval END.
    Hour 7 = interval ending at 07:00 (covers 06:30-07:00 for 30-min or 06:55-07:00 for 5-min).
    We include hours 7 through 21 inclusive.
    """
    weekday = dt_series.dt.dayofweek < 5  # Mon=0 to Fri=4
    hour = dt_series.dt.hour
    peak_hour = (hour >= config.PEAK_START_HOUR) & (hour < config.PEAK_END_HOUR)
    return weekday & peak_hour


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
