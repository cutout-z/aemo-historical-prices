#!/usr/bin/env python3
"""Compare two summary.csv files after the peak-window refresh.

    python3 scripts/compare-summaries.py OLD_summary.csv NEW_summary.csv

Passes (exit 0) only if the refresh changed NOTHING except the peak price columns: same
region/month keys, and rrp_nominal, rrp_real, total_intervals, peak_intervals, carbon_flag and
cpi_estimated identical. Prints how far peak_rrp_nominal / peak_rrp_real moved so the size of the
restatement is on the record. Reads only.
"""
import sys

import pandas as pd

KEYS = ["region", "year_month"]
MUST_MATCH = ["rrp_nominal", "rrp_real", "total_intervals", "peak_intervals", "carbon_flag", "cpi_estimated"]
MAY_MOVE = ["peak_rrp_nominal", "peak_rrp_real"]


def main(old_path: str, new_path: str) -> int:
    old = pd.read_csv(old_path).sort_values(KEYS).reset_index(drop=True)
    new = pd.read_csv(new_path).sort_values(KEYS).reset_index(drop=True)
    fails = []
    if not old[KEYS].equals(new[KEYS]):
        fails.append(f"row keys differ: {len(old)} old rows vs {len(new)} new rows")
    else:
        for col in MUST_MATCH:
            bad = (old[col] != new[col]) & ~(old[col].isna() & new[col].isna())
            if bad.any():
                ex = old.loc[bad, KEYS].head(3).values.tolist()
                fails.append(f"{col} changed on {int(bad.sum())} rows, e.g. {ex}")
        for col in MAY_MOVE:
            d = new[col] - old[col]
            pct = (d / old[col].abs().where(old[col].abs() > 1)) * 100
            print(f"{col}: {int((d != 0).sum())}/{len(d)} rows moved · median |Δ| ${d.abs().median():.2f}"
                  f" · max |Δ| ${d.abs().max():.2f} · median |Δ%| {pct.abs().median():.2f}%")
            worst = d.abs()[d != 0].sort_values(ascending=False).head(3).index
            for i in worst:
                print(f"    {old.loc[i, 'region']} {old.loc[i, 'year_month']}: {old.loc[i, col]:.2f} -> {new.loc[i, col]:.2f}")
    for f in fails:
        print("FAIL:", f)
    print("OK: only the peak price columns changed" if not fails else f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
