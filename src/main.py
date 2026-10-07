"""CLI orchestrator for AEMO historical price analysis."""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

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


def _month_labels(months: list[tuple[int, int]], months_back: int) -> set[str]:
    if months_back <= 0:
        return set()
    return {f"{y}-{m:02d}" for y, m in months[-months_back:]}


def _assert_settled_history_unchanged(
    before: pd.DataFrame | None,
    after: pd.DataFrame,
    mutable_months: set[str],
) -> None:
    """Protect settled nominal history while allowing CPI columns to refresh.

    Rules, per (region, month) key outside the mutable window:
      1. a settled key present before must still be present after (nothing vanishes);
      2. its protected values must be unchanged;
      3. a key that is NEW (an earlier download failure healing, e.g. one region's file that was
         missing last time) is allowed and logged -- it is not a change to settled history.
    """
    if before is None or before.empty or after.empty:
        return

    key_cols = ["region", "year_month"]
    protected_cols = [
        "region",
        "year_month",
        "rrp_nominal",
        "peak_rrp_nominal",
        "total_intervals",
        "peak_intervals",
        "carbon_flag",
    ]
    protected_cols = [c for c in protected_cols if c in before.columns and c in after.columns]
    if not all(c in protected_cols for c in key_cols):
        return

    before_protected = before[~before["year_month"].isin(mutable_months)][protected_cols]
    after_protected = after[protected_cols]

    joined = before_protected.merge(
        after_protected, on=key_cols, how="outer", suffixes=("_before", "_after"), indicator=True
    )

    vanished = joined[joined["_merge"] == "left_only"]
    if not vanished.empty:
        sample = vanished[key_cols].head(5).values.tolist()
        raise RuntimeError(
            f"Historical price run dropped {len(vanished)} settled region-month row(s) outside "
            f"the mutable window, e.g. {sample}. Use --full-refresh only for deliberate audited rewrites."
        )

    both = joined[joined["_merge"] == "both"]
    value_cols = [c for c in protected_cols if c not in key_cols]
    left = both[[f"{c}_before" for c in value_cols]].set_axis(value_cols, axis=1)
    right = both[[f"{c}_after" for c in value_cols]].set_axis(value_cols, axis=1)
    try:
        assert_frame_equal(
            left.reset_index(drop=True), right.reset_index(drop=True), check_dtype=False
        )
    except AssertionError as exc:
        raise RuntimeError(
            "Historical price run attempted to change settled nominal months outside "
            "the mutable window. Use --full-refresh only for deliberate audited rewrites."
        ) from exc

    # A new key outside the mutable window is a gap healing (the latest month is inside the window).
    healed = joined[(joined["_merge"] == "right_only") & ~joined["year_month"].isin(mutable_months)]
    if not healed.empty:
        logger.info("Settled-history guard: %d previously missing region-month row(s) filled in", len(healed))

    logger.info(
        "Settled-history guard: %d protected region-month rows unchanged",
        len(both),
    )


def _assert_newest_month_processed(newest_ym: str, existing: set, new_results: list[dict]) -> None:
    """Raise when the newest published month is missing in EVERY region.

    Per-region failures inside the loop are logged and skipped so one bad file cannot block the rest
    (a month missing in only some regions fails tests/validate_outputs.py's common-end check). But a
    month that no region produced, and that summary.csv does not already hold, would otherwise be a
    green run with no new data.
    """
    if any(ym == newest_ym for _, ym in existing):
        return
    if any(r["year_month"] == newest_ym for r in new_results):
        return
    raise RuntimeError(
        f"AEMO lists {newest_ym} as published, but no region produced a complete month for it "
        f"(download failed, 404 or incomplete in every region; see the log above). Failing the run "
        f"rather than publishing without it."
    )


def build_status(summary: pd.DataFrame, cpi_edition: dict, files_processed: int,
                 not_refreshed: list[str], now_utc: datetime) -> dict:
    """The run record published as outputs/status.json.

    last_checked is when this run finished checking the sources (UTC, and AWST for the page). Sources:
      aemo        "ok" when every AEMO file this run re-checked was processed; "cached" when some could
                  not be refreshed (download failed, 404 or incomplete) and the previously published
                  row was kept -- kept_previous lists them as "REGION YYYY-MM".
      rba_g1_cpi  always "ok": G1 is downloaded on every run and a failed fetch fails the run.
    """
    now_utc = now_utc.astimezone(timezone.utc)
    return {
        "last_checked_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_checked_awst": now_utc.astimezone(config.AWST).isoformat(timespec="seconds"),
        "aemo_latest_month": str(summary["year_month"].max()),
        "cpi_latest_quarter": cpi_edition.get("latest_quarter"),
        "cpi_g1_publication_date": cpi_edition.get("g1_publication_date"),
        "cpi_g1_last_modified_utc": cpi_edition.get("g1_last_modified_utc"),
        "sources": {
            "aemo": {
                "status": "cached" if not_refreshed else "ok",
                "files_processed": files_processed,
                "kept_previous": sorted(not_refreshed),
            },
            "rba_g1_cpi": {"status": "ok"},
        },
    }


def save_status(status: dict):
    """Write outputs/status.json (stable key order, so a daily commit only changes what changed)."""
    status_path = PROJECT_ROOT / config.STATUS_JSON
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, indent=2) + "\n")
    logger.info(f"Saved status.json (last checked {status['last_checked_utc']})")


def run(full_refresh: bool = False, months_back: int = 1):
    """Main execution flow."""
    cache_dir = str(PROJECT_ROOT / config.DATA_DIR)
    output_dir = str(PROJECT_ROOT / config.OUTPUT_DIR)

    # Step 1: Load existing summary (nominal prices only for incremental)
    summary = None if full_refresh else load_summary()
    settled_before = summary.copy() if summary is not None and not full_refresh else None
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

    # Never include the in-progress current month — only show complete months. "Current" is NEM
    # time (fixed AEST), not the runner's local clock. A month that slips through anyway is still
    # rejected by analyse_month unless it holds exactly every interval.
    today = config.nem_now().date()
    if (latest_year, latest_month) == (today.year, today.month):
        prev = today.replace(day=1) - timedelta(days=1)
        latest_year, latest_month = prev.year, prev.month
        logger.info(f"Current month in progress — capping at {latest_year}-{latest_month:02d}")

    # Step 3: Determine which months to process
    all_months = months_in_range(
        config.START_DATE.year, config.START_DATE.month,
        latest_year, latest_month,
    )

    # Always re-download the recent mutable window in case the prior run captured
    # an incomplete AEMO publication. Older months are treated as settled history.
    force_months = _month_labels(all_months, months_back)
    if force_months:
        logger.info("Mutable window: %s", ", ".join(sorted(force_months)))

    # Step 4: Download and analyse each new month/region
    new_results = []
    files_processed = 0
    not_refreshed = []   # "REGION YYYY-MM" that this run tried and could not (re)produce
    for year, month in all_months:
        for region in config.REGIONS:
            ym = f"{year}-{month:02d}"

            # Skip months before region's start date (e.g. TAS before Jun 2005)
            region_start = config.REGION_START_DATES[region]
            if (year, month) < (region_start.year, region_start.month):
                continue

            if not full_refresh and (region, ym) in existing and ym not in force_months:
                continue

            files_processed += 1
            try:
                raw_df = download_month(
                    year,
                    month,
                    region,
                    cache_dir,
                    force=(full_refresh or ym in force_months),
                )
                if raw_df.empty:
                    logger.warning(f"No data for {region} {ym}, skipping")
                    not_refreshed.append(f"{region} {ym}")
                    continue
                stats = analyse_month(raw_df, region, year, month)
                if stats:
                    new_results.append(stats)
                else:
                    not_refreshed.append(f"{region} {ym}")
            except Exception as e:
                logger.error(f"Failed to process {region} {ym}: {e}")
                not_refreshed.append(f"{region} {ym}")
                continue

    if not new_results and summary is None:
        logger.error("No data was successfully processed.")
        sys.exit(1)

    # The probe says AEMO has published the newest complete month. If no region produced it (every
    # download failed, 404'd or was incomplete) and it is not already in summary.csv, fail the run:
    # skipping it would exit 0 and leave the page a month behind until the next scheduled run.
    _assert_newest_month_processed(f"{latest_year}-{latest_month:02d}", existing, new_results)

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
    cpi_df, latest_cpi, cpi_edition = get_cpi_lookup(cache_dir)
    summary = adjust_prices(summary, cpi_df, latest_cpi)

    summary = summary.sort_values(["region", "year_month"]).reset_index(drop=True)
    if not full_refresh:
        _assert_settled_history_unchanged(settled_before, summary, force_months)

    # Step 7: Save summary and generate Excel
    save_summary(summary)
    generate_all_workbooks(summary, output_dir)

    # Step 8: Record the check itself, last, so only a run that got this far updates it. Rows that
    # could not be refreshed but were never published are not "kept"; the validator's contiguity check
    # fails on those.
    kept = [k for k in not_refreshed if tuple(k.split(" ")) in get_existing_months(summary)]
    save_status(build_status(summary, cpi_edition, files_processed, kept, datetime.now(timezone.utc)))

    total_months = summary["year_month"].nunique()
    logger.info(f"Done. {total_months} months × {len(config.REGIONS)} regions = {len(summary)} rows")


def main():
    parser = argparse.ArgumentParser(description="AEMO Historical Electricity Price Analysis")
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Re-download ALL raw data from Jul 2003, ignoring the local cache, and rebuild every row (default: incremental update)",
    )
    parser.add_argument(
        "--months-back",
        type=int,
        default=1,
        help="Number of recent complete months to reprocess in incremental mode",
    )
    args = parser.parse_args()
    run(full_refresh=args.full_refresh, months_back=args.months_back)


if __name__ == "__main__":
    main()
