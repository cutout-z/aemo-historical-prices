"""CLI orchestrator for AEMO historical price analysis."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config
from .download import download_month, get_latest_available_month
from .cpi import get_cpi_lookup, adjust_prices
from .analyse import analyse_month
from .excel_output import generate_all_workbooks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_summary() -> pd.DataFrame | None:
    """Load existing summary.csv if it exists and is valid."""
    summary_path = PROJECT_ROOT / config.SUMMARY_CSV
    if not summary_path.exists():
        return None
    try:
        df = pd.read_csv(summary_path)
        if df.empty or "year_month" not in df.columns:
            logger.warning("summary.csv is empty or malformed, will do full refresh")
            return None
        return df
    except Exception as e:
        logger.warning(f"Corrupt summary.csv ({e}), falling back to full refresh")
        return None


def save_summary(df: pd.DataFrame):
    """Save summary DataFrame to CSV."""
    summary_path = PROJECT_ROOT / config.SUMMARY_CSV
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(summary_path, index=False)
    logger.info(f"Saved summary.csv ({len(df)} rows)")


def get_existing_months(summary: pd.DataFrame | None) -> set[str]:
    """Get set of already-processed (region, year_month) pairs."""
    if summary is None:
        return set()
    return set(zip(summary["region"], summary["year_month"]))


def months_in_range(start_year: int, start_month: int,
                    end_year: int, end_month: int) -> list[tuple[int, int]]:
    """Generate list of (year, month) tuples in range inclusive."""
    result = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        result.append((y, m))
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return result


def run(full_refresh: bool = False):
    """Main execution flow."""
    cache_dir = str(PROJECT_ROOT / config.DATA_DIR)
    output_dir = str(PROJECT_ROOT / config.OUTPUT_DIR)

    # Step 1: Load existing summary (nominal prices only for incremental)
    summary = None if full_refresh else load_summary()
    existing = get_existing_months(summary)

    if full_refresh:
        logger.info("Full refresh mode — will re-download all data from Jul 2003")
    elif summary is not None:
        unique_months = summary["year_month"].nunique()
        logger.info(f"Loaded summary.csv with {unique_months} months × {len(config.REGIONS)} regions")
    else:
        logger.info("No existing summary found — will do initial full download")

    # Step 2: Probe AEMO for latest available month
    latest = get_latest_available_month()
    if latest is None:
        logger.error("Cannot determine latest available month. Exiting.")
        sys.exit(1)

    latest_year, latest_month = latest

    # Step 3: Determine which months to process
    all_months = months_in_range(
        config.START_DATE.year, config.START_DATE.month,
        latest_year, latest_month,
    )

    # Step 4: Download and analyse each new month/region
    new_results = []
    for year, month in all_months:
        for region in config.REGIONS:
            ym = f"{year}-{month:02d}"

            # Skip months before region's start date (e.g. TAS before May 2005)
            region_start = config.REGION_START_DATES[region]
            if (year, month) < (region_start.year, region_start.month):
                continue

            if not full_refresh and (region, ym) in existing:
                continue

            try:
                raw_df = download_month(year, month, region, cache_dir)
                if raw_df.empty:
                    logger.warning(f"No data for {region} {ym}, skipping")
                    continue
                stats = analyse_month(raw_df, region, year, month)
                if stats:
                    new_results.append(stats)
            except Exception as e:
                logger.error(f"Failed to process {region} {ym}: {e}")
                continue

    if not new_results and summary is None:
        logger.error("No data was successfully processed.")
        sys.exit(1)

    # Step 5: Merge with existing summary
    if new_results:
        new_df = pd.DataFrame(new_results)

        if summary is not None and not full_refresh:
            # Keep only nominal columns from existing (CPI will be re-applied)
            nominal_cols = ["region", "year_month", "rrp_nominal", "peak_rrp_nominal",
                            "total_intervals", "peak_intervals", "carbon_flag"]
            existing_nominal = summary[[c for c in nominal_cols if c in summary.columns]].copy()
            summary = pd.concat([existing_nominal, new_df], ignore_index=True)
            summary = summary.drop_duplicates(subset=["region", "year_month"], keep="last")
        else:
            summary = new_df

    # Step 6: Download CPI and re-apply to ALL rows
    logger.info("Applying CPI adjustment to all rows...")
    cpi_df, latest_cpi = get_cpi_lookup(cache_dir)
    summary = adjust_prices(summary, cpi_df, latest_cpi)

    summary = summary.sort_values(["region", "year_month"]).reset_index(drop=True)

    # Step 7: Save summary and generate Excel
    save_summary(summary)
    generate_all_workbooks(summary, output_dir)

    total_months = summary["year_month"].nunique()
    logger.info(f"Done. {total_months} months × {len(config.REGIONS)} regions = {len(summary)} rows")


def main():
    parser = argparse.ArgumentParser(description="AEMO Historical Electricity Price Analysis")
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Re-download all data from Jul 2003 (default: incremental update)",
    )
    args = parser.parse_args()
    run(full_refresh=args.full_refresh)


if __name__ == "__main__":
    main()
