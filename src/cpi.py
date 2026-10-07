"""CPI data acquisition and price adjustment using RBA G1 data."""

import csv
import logging
from pathlib import Path

import pandas as pd
import requests

from . import config

logger = logging.getLogger(__name__)


def download_cpi(cache_path: str) -> pd.DataFrame:
    """Fetch RBA G1 CSV and return quarterly CPI index series.

    Returns DataFrame with columns [date, cpi_index] where date is quarter-end.
    """
    cache = Path(cache_path)

    # Always re-download CPI (small file, ensures latest quarter is captured)
    logger.info("Downloading RBA CPI data...")
    resp = requests.get(config.RBA_CPI_URL, timeout=30)
    resp.raise_for_status()

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(resp.text)

    return _parse_cpi(cache)


def _parse_cpi(path: Path) -> pd.DataFrame:
    """Parse the RBA G1 CSV file.

    Structure: a block of metadata rows ending with the "Series ID" row, then data.
    Col A = dates as DD/MM/YYYY (quarter-end)
    Col B = CPI All Groups index (series GCPIAG; the rebase year does not matter to the ratio method)
    Later rows have more columns than early rows, so we only read cols 0-1.

    The data start is found by locating the "Series ID" row, not by a fixed row count: a change in
    RBA's metadata block must fail loudly rather than silently shift (or swallow) the first data row.
    Column B must be series GCPIAG with Quarterly frequency (config.RBA_CPI_SERIES_ID / _FREQUENCY):
    if RBA reorders the columns or moves the series to monthly, every region would be deflated by the
    same wrong series and no ratio check downstream would notice.
    """
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()

    def _row(label: str) -> tuple[int, list[str]] | tuple[None, None]:
        for i, line in enumerate(lines):
            fields = next(csv.reader([line]), [])
            if fields and fields[0].strip() == label:
                return i, [f.strip() for f in fields]
        return None, None

    header_idx, series_row = _row("Series ID")
    if header_idx is None:
        raise ValueError(f"RBA G1 file {Path(path).name}: no 'Series ID' row found; layout changed?")
    series_id = series_row[1] if len(series_row) > 1 else ""
    if series_id != config.RBA_CPI_SERIES_ID:
        raise ValueError(
            f"RBA G1 file {Path(path).name}: column B is series {series_id!r}, expected "
            f"{config.RBA_CPI_SERIES_ID!r}; table layout changed?"
        )
    freq_idx, freq_row = _row("Frequency")
    frequency = freq_row[1] if freq_row and len(freq_row) > 1 else None
    if freq_idx is None or freq_idx > header_idx or frequency != config.RBA_CPI_FREQUENCY:
        raise ValueError(
            f"RBA G1 file {Path(path).name}: column B frequency is {frequency!r}, expected "
            f"{config.RBA_CPI_FREQUENCY!r}; the quarterly interpolation would be wrong"
        )

    df = pd.read_csv(
        path,
        skiprows=header_idx + 1,
        usecols=[0, 1],
        names=["date_str", "cpi_index"],
        header=None,
    )

    result = pd.DataFrame({
        "date": pd.to_datetime(df["date_str"], dayfirst=True, errors="coerce"),
        "cpi_index": pd.to_numeric(df["cpi_index"], errors="coerce"),
    })

    result = result.dropna(subset=["date", "cpi_index"])
    if result.empty:
        raise ValueError(f"RBA G1 file {Path(path).name}: no CPI rows after the 'Series ID' row")
    result = result.sort_values("date").reset_index(drop=True)

    logger.info(
        f"CPI data: {len(result)} quarters, "
        f"{result['date'].iloc[0]:%b %Y} to {result['date'].iloc[-1]:%b %Y}"
    )
    return result


def interpolate_monthly(quarterly_df: pd.DataFrame) -> pd.DataFrame:
    """Linearly interpolate quarterly CPI to monthly.

    Quarterly dates are quarter-ends (Mar 31, Jun 30, Sep 30, Dec 31).
    We map each to the 1st of that month, then interpolate between them. So the quarter's index is
    anchored AT its last month (Oct is 1/3 of the way from the Sep to the Dec value). This is a
    documented method choice. The ABS quarterly index is the average of its three monthly indices, so
    the other standard convention is to anchor mid-quarter (Feb/May/Aug/Nov); that raises the
    interpolated index by about 0.2% on average and so LOWERS real prices by about 0.2%
    (README, "CPI Methodology").
    Returns DataFrame with columns [date, cpi_index] at monthly frequency.
    """
    df = quarterly_df.copy()

    # Map quarter-end dates to 1st of month (e.g. 2003-06-30 -> 2003-06-01)
    df["date"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df = df.set_index("date")

    # Create monthly date range and reindex
    start = df.index.min()
    end = df.index.max()
    monthly_idx = pd.date_range(start=start, end=end, freq="MS")

    monthly = df.reindex(monthly_idx).interpolate(method="linear")
    monthly.index.name = "date"

    result = monthly.reset_index()
    result = result.dropna(subset=["cpi_index"])

    return result


def check_cpi_fresh(latest_quarter_end: pd.Timestamp, now) -> None:
    """Raise when the newest CPI quarter is more than config.CPI_MAX_AGE_DAYS old.

    Months after the newest quarter are published with real = nominal and flagged cpi_estimated.
    That is honest for a month or three, but if G1 stops updating (served but frozen) the run would
    otherwise stay green while the flagged window grows. This fails the run instead.
    """
    age_days = (pd.Timestamp(now) - pd.Timestamp(latest_quarter_end)).days
    if age_days > config.CPI_MAX_AGE_DAYS:
        raise RuntimeError(
            f"RBA G1 newest CPI quarter is {pd.Timestamp(latest_quarter_end):%d %b %Y}, {age_days} days "
            f"ago (limit {config.CPI_MAX_AGE_DAYS}). ABS publishes about 4 weeks after quarter end: "
            f"the G1 table has stopped updating, moved, or changed layout."
        )


def get_cpi_lookup(cache_dir: str) -> tuple[pd.DataFrame, float]:
    """Download CPI and prepare monthly lookup.

    Returns (monthly_cpi_df, latest_cpi_value).
    monthly_cpi_df has columns [year_month, cpi_index] where year_month is 'YYYY-MM'.
    """
    cache_path = str(Path(cache_dir) / "rba_g1_cpi.csv")
    quarterly = download_cpi(cache_path)
    check_cpi_fresh(quarterly["date"].iloc[-1], config.nem_now())
    monthly = interpolate_monthly(quarterly)

    # Create year_month key for joining
    monthly["year_month"] = monthly["date"].dt.strftime("%Y-%m")

    latest_cpi = monthly["cpi_index"].iloc[-1]
    logger.info(f"Latest CPI index: {latest_cpi:.2f}")

    return monthly[["year_month", "cpi_index"]], latest_cpi


def adjust_prices(prices_df: pd.DataFrame, cpi_df: pd.DataFrame,
                  latest_cpi: float) -> pd.DataFrame:
    """Apply CPI adjustment to convert nominal prices to real (constant dollars).

    Formula: real_price = nominal_price * (CPI_latest / CPI_month)

    For months beyond the latest CPI data, no adjustment is applied (ratio = 1).
    These months are flagged with cpi_estimated=True.
    """
    df = prices_df.copy()

    # Merge CPI data
    df = df.merge(cpi_df, on="year_month", how="left")

    # Flag months without CPI data
    df["cpi_estimated"] = df["cpi_index"].isna()

    # For months without CPI, use latest CPI (ratio = 1, no adjustment)
    df["cpi_index"] = df["cpi_index"].fillna(latest_cpi)

    # Calculate real prices
    cpi_ratio = latest_cpi / df["cpi_index"]
    df["rrp_real"] = df["rrp_nominal"] * cpi_ratio
    df["peak_rrp_real"] = df["peak_rrp_nominal"] * cpi_ratio

    # Round to 2 decimal places
    df["rrp_real"] = df["rrp_real"].round(2)
    df["peak_rrp_real"] = df["peak_rrp_real"].round(2)

    # Clean up
    df = df.drop(columns=["cpi_index"])

    return df
