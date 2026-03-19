# AEMO Historical Electricity Prices

Automated analysis of NEM spot electricity prices across all five regions (NSW, QLD, VIC, SA, TAS), with CPI adjustment from nominal to real terms.

## Live Dashboard

**[View Dashboard](https://cutout-z.github.io/aemo-historical-prices/)**

## What It Does

- Downloads monthly aggregated price data from AEMO (Jul 2003 to present)
- Calculates mean RRP and peak-hour RRP (7am–10pm weekdays AEST) for each region
- Applies CPI adjustment using the RBA Consumer Price Index to produce real (constant-dollar) prices
- Generates per-region Excel workbooks with rolling averages, monthly data, and heatmaps
- Updates automatically on the 16th of each month via GitHub Actions

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

## Notes

- **Peak hours**: 7am–10pm weekdays AEST (standard NEM definition)
- **Carbon tax period** (Jul 2012 – Jun 2014) is flagged in outputs
- **Data format change**: Pre-Oct 2021 files use 30-min intervals without headers; Oct 2021+ use 5-min intervals with headers. Both are handled automatically.
- TAS data starts May 2005 (Tasmania joined the NEM later)
