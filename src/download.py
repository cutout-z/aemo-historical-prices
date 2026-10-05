"""Data acquisition from AEMO aggregated price & demand CSVs."""

import logging
import time
from pathlib import Path

import pandas as pd
import requests

from . import config

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = ["REGION", "SETTLEMENTDATE", "TOTALDEMAND", "RRP", "PERIODTYPE"]


def _build_url(year: int, month: int, region: str) -> str:
    """Build AEMO CSV URL for a given year, month, and region."""
    ym = f"{year:04d}{month:02d}"
    return config.AEMO_URL_PATTERN.format(ym=ym, region=region)


def download_month(
    year: int,
    month: int,
    region: str,
    cache_dir: str,
    *,
    force: bool = False,
) -> pd.DataFrame:
    """Download a single AEMO CSV for one month/region, with local caching.

    Returns DataFrame with columns [REGION, SETTLEMENTDATE, TOTALDEMAND, RRP, PERIODTYPE].
    """
    cache_path = Path(cache_dir) / f"PRICE_AND_DEMAND_{year:04d}{month:02d}_{region}.csv"

    if cache_path.exists() and not force:
        return _read_csv(cache_path)

    url = _build_url(year, month, region)
    action = "Re-downloading" if force and cache_path.exists() else "Downloading"
    logger.info(f"{action} {region} {year}-{month:02d}...")

    for attempt in range(config.MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 404:
                logger.warning(f"No data at {url} (404)")
                return pd.DataFrame(columns=EXPECTED_COLUMNS)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt < config.MAX_RETRIES - 1:
                wait = config.RETRY_BACKOFF * (attempt + 1)
                logger.warning(f"Download failed (attempt {attempt + 1}): {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Failed to download {region} {year}-{month:02d} after "
                    f"{config.MAX_RETRIES} attempts: {e}"
                )

    # Save raw CSV to cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(resp.text)

    return _read_csv(cache_path)


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a cached CSV file. All AEMO files have a header row."""
    df = pd.read_csv(path)

    # Standardise column names
    df.columns = [c.strip().upper() for c in df.columns]

    # Ensure we have the expected columns
    for col in ["REGION", "SETTLEMENTDATE", "RRP"]:
        if col not in df.columns:
            logger.warning(f"Missing column {col} in {path.name}")
            return pd.DataFrame(columns=EXPECTED_COLUMNS)

    df["SETTLEMENTDATE"] = pd.to_datetime(df["SETTLEMENTDATE"])
    df["RRP"] = pd.to_numeric(df["RRP"], errors="coerce")

    return df


def _months_back(year: int, month: int, n: int) -> tuple[int, int]:
    """The calendar month n months before (year, month)."""
    idx = year * 12 + (month - 1) - n
    return idx // 12, idx % 12 + 1


def get_latest_available_month() -> tuple[int, int] | None:
    """Probe AEMO to find the newest available month.

    Checks NSW1 as the reference region, working backwards by CALENDAR month from the current
    NEM-time month. A 404 means "not published yet": try the month before. Any other failure
    (network error, 5xx, redirect to an error page) is NOT a statement about the month, so it is
    retried and then reported as an error -- never silently answered with an older month.
    Returns (year, month) or None if probing fails.
    """
    now = config.nem_now()

    for back in range(0, 4):
        year, month = _months_back(now.year, now.month, back)
        url = _build_url(year, month, "NSW1")

        status = None
        for attempt in range(config.MAX_RETRIES):
            try:
                resp = requests.head(url, timeout=15, allow_redirects=True)
                status = resp.status_code
                if status in (200, 404):
                    break
                logger.warning(f"Unexpected status {status} for {url} (attempt {attempt + 1})")
            except requests.RequestException as e:
                status = None
                logger.warning(f"Probe failed for {url} (attempt {attempt + 1}): {e}")
            if attempt < config.MAX_RETRIES - 1:
                time.sleep(config.RETRY_BACKOFF * (attempt + 1))

        if status == 200:
            logger.info(f"Latest available month: {year}-{month:02d}")
            return (year, month)
        if status != 404:
            logger.error(f"Could not probe {url} (last status: {status}); not guessing an older month")
            return None
        # 404: this month is not published yet, try the one before

    logger.error("Could not determine latest available month from AEMO")
    return None
