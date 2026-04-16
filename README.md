# AEMO Historical Electricity Prices

Automated analysis of NEM spot electricity prices across all five regions (NSW, QLD, VIC, SA, TAS), with CPI adjustment from nominal to real terms.

## Live Dashboard

**[View Dashboard](https://cutout-z.github.io/aemo-historical-prices/)**

## What It Does

- Downloads monthly aggregated price data from AEMO (Jul 2003 to present)
- Calculates mean RRP and peak-hour RRP (7am–10pm weekdays AEST) for each region
- Applies CPI adjustment using the RBA Consumer Price Index to produce real (constant-dollar) prices
- Generates per-region Excel workbooks with rolling averages, monthly data, and heatmaps
- Updates automatically on the 3rd of each month via GitHub Actions (only complete months are shown — the current in-progress month is excluded)

## Data Sources

| Source | URL | Description |
|--------|-----|-------------|
| AEMO | `aemo.com.au/aemo/data/nem/priceanddemand/` | Aggregated 5-min/30-min spot prices |
| RBA | `rba.gov.au/statistics/tables/csv/g1-data.csv` | Quarterly CPI index (G1 table) |

## CPI Methodology

Real prices are calculated using the CPI index ratio method:

```
real_price = nominal_price × (CPI_latest / CPI_month)
```

Quarterly CPI values are linearly interpolated to monthly. For months beyond the latest published CPI quarter, no adjustment is applied (ratio = 1).

All real prices are expressed in **dollars as at the most recent CPI quarter** available from the RBA (e.g. if the latest published quarter is Dec 2025, all prices are in "Dec 2025 dollars"). This base shifts forward automatically each time the script re-runs after a new CPI release.

### Detailed calculation example

#### Step 1 — Monthly nominal price

For each region/month, every dispatch interval RRP (5-min post-Oct 2021, 30-min prior) is averaged into a single nominal $/MWh figure:

```
rrp_nominal = mean of all interval RRPs in that month
```

For example, NSW Jan 2021 has ~8,928 five-minute intervals. The nominal price is the simple arithmetic mean of all 8,928 RRP values.

#### Step 2 — CPI interpolation

The RBA G1 CPI index is published quarterly (Mar, Jun, Sep, Dec). To get a monthly index, quarterly values are linearly interpolated — e.g. Oct gets a value 1/3 of the way between Sep and Dec, Nov gets 2/3 of the way, etc.

#### Step 3 — Convert each month to real dollars

Each month's nominal price is scaled to latest-quarter dollars:

| Item | Value |
|------|-------|
| NSW nominal RRP, Jan 2021 | $85.00/MWh |
| CPI index, Jan 2021 (interpolated) | 78.5 |
| CPI index, latest quarter (Dec 2025) | 102.3 |
| **Real price** | 85.00 × (102.3 / 78.5) = **$110.80/MWh** |

This means: "$85 in Jan 2021 is equivalent to $110.80 in Dec 2025 purchasing power."

For recent months where CPI hasn't been published yet (e.g. Jan–Mar 2026 before the Q1 2026 CPI release), the ratio is `latest / latest = 1`, so real = nominal. These months are flagged `cpi_estimated = True` in the data.

#### Step 4 — Rolling averages

The summary sheet shows rolling averages (1, 3, 5, 10, 15, 20 years). For example, the **5-year real RRP** is:

```
mean of the 60 most recent monthly real prices
```

Each of those 60 values has already been individually CPI-adjusted per Step 3, so the average is in constant latest-quarter dollars. Every time the script re-runs and a new CPI quarter is published, all historical real prices shift slightly as the base period moves forward.

## Usage

```bash
pip install -r requirements.txt

# Incremental update (downloads only new months)
python -m src.main

# Full refresh (re-downloads everything from Jul 2003)
python -m src.main --full-refresh
```

## Project Structure

```
src/
├── config.py        # Constants, URLs, paths
├── download.py      # AEMO CSV downloader with caching
├── cpi.py           # RBA CPI fetch, interpolation, adjustment
├── analyse.py       # Peak filtering, monthly aggregation
├── excel_output.py  # Per-region Excel workbooks
└── main.py          # CLI orchestrator
outputs/
├── summary.csv      # Master dataset (all regions, all months)
└── *.xlsx           # Per-region Excel workbooks
index.html           # GitHub Pages dashboard
```

## Regions

| AEMO ID | State |
|---------|-------|
| NSW1 | New South Wales |
| QLD1 | Queensland |
| VIC1 | Victoria |
| SA1 | South Australia |
| TAS1 | Tasmania |

## Output Validation

After the pipeline runs and before committing, an automated validation step (`tests/validate_outputs.py`) checks:

- `summary.csv` exists and is non-empty
- All 5 NEM regions are present
- Interval counts are within expected range: 1,100–1,700 (pre-Oct 2021, 30-min) or 7,000–10,000 (post-Oct 2021, 5-min)
- Peak intervals never exceed total intervals
- No extreme negative average prices (floor at -$500/MWh)
- No duplicate region/month rows
- All 5 regional Excel workbooks exist

If any check fails, the workflow exits before committing — preventing bad data from reaching the dashboard.

## Notes

- **Peak hours**: 7am–10pm weekdays AEST (standard NEM definition)
- **Carbon tax period** (Jul 2012 – Jun 2014) is flagged in outputs
- **Data format change**: Pre-Oct 2021 files use 30-min intervals without headers; Oct 2021+ use 5-min intervals with headers. Both are handled automatically.
- TAS data starts May 2005 (Tasmania joined the NEM later)
