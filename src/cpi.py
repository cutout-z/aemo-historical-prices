"""CPI data acquisition and price adjustment using RBA G1 data."""

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

    Structure: 11 metadata rows (including Series ID header), then data.
    Col A = dates as DD/MM/YYYY (quarter-end)
    Col B = CPI All Groups index (base: Sep 2025 = 100)
    Later rows have more columns than early rows, so we only read cols 0-1.
    """
    df = pd.read_csv(
        path,
        skiprows=config.RBA_CPI_SKIP_ROWS,
        usecols=[0, 1],
        names=["date_str", "cpi_index"],
        header=0,
    )

    result = pd.DataFrame({
        "date": pd.to_datetime(df["date_str"], dayfirst=True),
        "cpi_index": pd.to_numeric(df["cpi_index"], errors="coerce"),
    })

    result = result.dropna(subset=["cpi_index"])
    result = result.sort_values("date").reset_index(drop=True)

    logger.info(
        f"CPI data: {len(result)} quarters, "
        f"{result['date'].iloc[0]:%b %Y} to {result['date'].iloc[-1]:%b %Y}"
    )
    return result


def interpolate_monthly(quarterly_df: pd.DataFrame) -> pd.DataFrame:
    """Linearly interpolate quarterly CPI to monthly.

    Quarterly dates are quarter-ends (Mar 31, Jun 30, Sep 30, Dec 31).
    We map each to the 1st of that month, then interpolate between them.
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


def get_cpi_lookup(cache_dir: str) -> tuple[pd.DataFrame, float]:
    """Download CPI and prepare monthly lookup.

    Returns (monthly_cpi_df, latest_cpi_value).
    monthly_cpi_df has columns [year_month, cpi_index] where year_month is 'YYYY-MM'.
    """
    cache_path = str(Path(cache_dir) / "rba_g1_cpi.csv")
    quarterly = download_cpi(cache_path)
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
