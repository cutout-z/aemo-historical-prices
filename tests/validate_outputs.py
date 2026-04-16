"""Post-pipeline validation for AEMO Historical Prices.

Checks summary.csv and regional Excel workbooks for data integrity
before committing to the repository. Exits non-zero on any failure.
"""

import sys
from pathlib import Path

import pandas as pd

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"
REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]
REGION_NAMES = {"NSW1": "NSW", "QLD1": "QLD", "VIC1": "VIC", "SA1": "SA", "TAS1": "TAS"}
# Oct 2021: NEM switched from 30-min to 5-min settlement intervals
FORMAT_CHANGE = "2021-10"
# First month each region entered the NEM — always partial, exempt from interval checks
REGION_FIRST_MONTHS = {
    "TAS1": "2005-05",  # TAS joined NEM mid-May 2005
}

errors = []


def check(condition, msg):
    if not condition:
        errors.append(msg)
        print(f"  FAIL: {msg}")
    return condition


def validate():
    summary_path = OUTPUTS_DIR / "summary.csv"
    check(summary_path.exists(), "summary.csv does not exist")
    if not summary_path.exists():
        return

    df = pd.read_csv(summary_path)
    print(f"summary.csv: {len(df)} rows")

    # --- Structure ---
    check(len(df) > 0, "summary.csv is empty")
    required_cols = ["region", "year_month", "rrp_nominal", "peak_rrp_nominal",
                     "total_intervals", "peak_intervals"]
    for col in required_cols:
        check(col in df.columns, f"Missing column: {col}")

    # --- All 5 regions present ---
    regions_present = set(df["region"].unique())
    for r in REGIONS:
        check(r in regions_present, f"Region {r} missing from summary.csv")

    # --- Interval counts in expected range ---
    if "total_intervals" in df.columns and "year_month" in df.columns:
        # Exclude the latest month (always in-progress when the monthly job runs on the 16th)
        # and each region's first month (partial due to NEM entry date mid-month)
        latest_ym = df["year_month"].max()
        first_month_mask = df.apply(
            lambda r: REGION_FIRST_MONTHS.get(r["region"]) == r["year_month"], axis=1
        )
        checkable = df[(df["year_month"] != latest_ym) & ~first_month_mask]

        pre_change = checkable[checkable["year_month"] < FORMAT_CHANGE]
        post_change = checkable[checkable["year_month"] >= FORMAT_CHANGE]

        if len(pre_change) > 0:
            bad_pre = pre_change[
                (pre_change["total_intervals"] < 1100) | (pre_change["total_intervals"] > 1700)
            ]
            check(
                len(bad_pre) == 0,
                f"{len(bad_pre)} pre-Oct 2021 rows have interval counts outside [1100, 1700]",
            )

        if len(post_change) > 0:
            bad_post = post_change[
                (post_change["total_intervals"] < 7000) | (post_change["total_intervals"] > 10000)
            ]
            check(
                len(bad_post) == 0,
                f"{len(bad_post)} post-Oct 2021 rows have interval counts outside [7000, 10000]",
            )

    # --- Peak intervals <= total intervals ---
    if "peak_intervals" in df.columns and "total_intervals" in df.columns:
        violations = df[df["peak_intervals"] > df["total_intervals"]]
        check(
            len(violations) == 0,
            f"{len(violations)} rows have peak_intervals > total_intervals",
        )

    # --- Prices non-negative ---
    for col in ["rrp_nominal", "peak_rrp_nominal"]:
        if col in df.columns:
            # Negative average prices can legitimately occur in the NEM
            # but sustained negative averages over a full month would be anomalous
            vals = df[col].dropna()
            check(
                vals.min() > -500,
                f"{col} has extreme negative value (min={vals.min():.2f})",
            )

    # --- No duplicate region/month ---
    if "region" in df.columns and "year_month" in df.columns:
        dupes = df.duplicated(subset=["region", "year_month"], keep=False)
        check(dupes.sum() == 0, f"{dupes.sum()} duplicate region/month rows")

    # --- Regional Excel workbooks exist ---
    for region_id, name in REGION_NAMES.items():
        xlsx_path = OUTPUTS_DIR / f"{name}_historical_prices.xlsx"
        check(xlsx_path.exists(), f"{xlsx_path.name} does not exist")


if __name__ == "__main__":
    print("Validating AEMO Historical Prices outputs...")
    validate()
    if errors:
        print(f"\n{len(errors)} validation error(s) found — aborting.")
        sys.exit(1)
    else:
        print("\nAll validations passed.")
