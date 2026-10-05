# AEMO Historical Electricity Prices

Automated analysis of NEM spot electricity prices across all five regions (NSW, QLD, VIC, SA, TAS), with CPI adjustment from nominal to real terms.

## Live Dashboard

**[View Dashboard](https://cutout-z.github.io/aemo-historical-prices/)**

## What It Does

- Downloads monthly aggregated price data from AEMO (Jul 2003 to present; Tasmania from Jun 2005, its first complete month)
- Calculates mean RRP and peak-hour RRP (Mon–Fri 07:00–22:00 AEST) for each region
- Applies CPI adjustment using the RBA Consumer Price Index to produce real (constant-dollar) prices
- Generates per-region Excel workbooks (summary with rolling averages, monthly data, heatmap) and an All States workbook (one monthly sheet per region)
- Checks daily for newly published or corrected monthly AEMO data via the scheduled NAS lane. Only complete months are published: a month must hold exactly every interval (days × 48 half-hours before Oct 2021, days × 288 five-minute intervals from Oct 2021), so the in-progress month and any partial AEMO publication are held back until complete.

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

Quarterly CPI values are linearly interpolated to monthly. Each quarterly value is anchored at the **last month of its quarter** (Mar, Jun, Sep, Dec), so Oct is one third of the way from the Sep value to the Dec value. This is a method choice: anchoring mid-quarter (Feb, May, Aug, Nov) is the other common approach, and the ABS builds each quarterly index as the average of its three monthly indices, which points to the middle month. Compared with the ABS's actual monthly CPI (available from Apr 2024), quarter-end anchoring runs about 0.3% low on the index; mid-quarter anchoring would lower real prices by about 0.2% on average (range −0.7% to +0.7%). For months beyond the latest published CPI quarter, no adjustment is applied (ratio = 1).

All real prices are expressed in **dollars as at the most recent CPI quarter** available from the RBA (e.g. if the latest published quarter is Jun 2026, all prices are in "Jun 2026 dollars"). This base shifts forward automatically each time the script re-runs after a new CPI release. The dashboard and the workbooks both state the base month, and mark the months that have no CPI yet.

### Known limitations of the CPI method, and their size

The method uses one source (the RBA G1 table, which is exactly the ABS quarterly index) and a simple
interpolation. Two things follow from that. Both were measured against the ABS's own monthly CPI
(2026-10 analysis); neither is a bug, and the method was deliberately left as is.

| Limitation | Size | Direction |
|---|---|---|
| **Quarter-end anchoring.** The ABS builds each quarterly index as the average of its three monthly indices, so the value belongs at the middle month, not the last. | Against the ABS monthly CPI (Apr 2024 – May 2026) the interpolated index is **0.27% low on average** (mean absolute error 0.33%, worst month −0.87%). Mid-quarter anchoring would cut the bias to about 0.01%. | Real prices are about **0.2% too high** on average (−0.7% to +0.7% by month) |
| **Months with no CPI yet** (`cpi_estimated`) are left at real = nominal. The ABS monthly CPI is published sooner than the quarterly one (Aug 2026 is out while the latest quarter is Jun 2026). | At the time of writing the monthly index was 1.2% above the base by Aug 2026 (103.50 vs 102.31), so the flagged months are overstated by about 0.7% (Jul) to 1.2% (Aug); the latest month is not yet known. | Real prices of the flagged months are **0.7–1.2% too high** |

**Combined effect.** Using the ABS monthly series from Apr 2024 and mid-quarter anchoring before it would
move any month's real price by no more than 1.2% (mean −0.2%), and the headline averages by about
0.4% (NSW 5-year real RRP $127.92 → $127.44; 1-year $75.16 → $74.84). Nominal prices are unaffected.
For scale, the median month-on-month move in the underlying price is 17%.

**Why it was left as is.** The effect is far smaller than the price movements the dashboard shows, and the
alternative adds a second data source (the ABS Data API, dataflow `CPI` 2.0.0, key `1.10001.10.50.M`) with
only 27 months of monthly history (from Apr 2024), a splice to the older quarterly series, and an
unconfirmed revision policy. Revisit it if the flagged-month window or the 0.2% bias starts to matter.
The monthly series does exist, and the quarterly index is, by the ABS's own description, the average of
its three monthly values.

### Detailed calculation example

#### Step 1 — Monthly nominal price

For each region/month, every interval RRP (5-minute dispatch prices from Oct 2021, 30-minute trading prices before) is averaged into a single nominal $/MWh figure:

```
rrp_nominal = mean of all interval RRPs in that month
```

For example, NSW Jan 2021 is before the switch, so it has 1,488 half-hour intervals (31 days × 48). The nominal price is the simple arithmetic mean of all 1,488 RRP values: **$38.84/MWh**.

#### Step 2 — CPI interpolation

The RBA G1 CPI index (All groups) is published quarterly (Mar, Jun, Sep, Dec). To get a monthly index, quarterly values are linearly interpolated between quarter-end months — e.g. Oct gets a value 1/3 of the way between Sep and Dec, Nov gets 2/3 of the way. Jan 2021 is 1/3 of the way from Dec 2020 (81.40) to Mar 2021 (81.87): 81.40 + (81.87 − 81.40) / 3 = **81.557**.

#### Step 3 — Convert each month to real dollars

Each month's nominal price is scaled to latest-quarter dollars:

| Item | Value |
|------|-------|
| NSW nominal RRP, Jan 2021 | $38.84/MWh |
| CPI index, Jan 2021 (interpolated) | 81.557 |
| CPI index, latest quarter (Jun 2026) | 102.31 |
| **Real price** | 38.84 × (102.31 / 81.557) = **$48.72/MWh** |

(These are the actual values in `outputs/summary.csv` as at the Oct 2026 data.) This means: "$38.84 in Jan 2021 is equivalent to $48.72 in Jun 2026 purchasing power."

For recent months where CPI hasn't been published yet (at the time of writing, Jul–Sep 2026, until the Q3 2026 CPI release), the ratio is `latest / latest = 1`, so real = nominal. These months are flagged `cpi_estimated = True` in the data, marked with a † in the dashboard's Real view, and flagged in the workbooks' Monthly Data sheet.

#### Step 4 — Rolling averages

The workbook Summary sheet shows rolling averages over 1, 2, 3, 5, 10, 15 and 20 years (the dashboard shows 1, 3, 5 and 10). A period longer than a region's history is shown as `n/a` with the months available, never dropped silently. For example, the **5-year real RRP** is:

```
mean of the 60 most recent monthly real prices
```

It is an average of monthly means, each month weighted equally (not weighted by interval count). Each of those 60 values has already been individually CPI-adjusted per Step 3, so the average is in constant latest-quarter dollars. Every time the script re-runs and a new CPI quarter is published, all historical real prices shift slightly as the base period moves forward.

## Usage

```bash
pip install -r requirements.txt

# Incremental update (downloads only new months)
python -m src.main

# Full refresh: re-downloads ALL raw data from Jul 2003 (ignores the local cache) and rebuilds every
# row. It bypasses the settled-history guard on purpose, for deliberate audited rewrites.
python -m src.main --full-refresh

# Tests (no network): peak-window boundaries and pipeline logic
python tests/test_peak_window.py && python tests/test_pipeline_logic.py
```

## Automation

Production updates run on the **NAS runner** — the QNAP `ai-wif-runner` container — via the `nas-job aemo-historical-prices` lane documented in [`deploy/README.md`](deploy/README.md):

- A QNAP scheduled task fires the lane daily; `deploy/run-update.sh` reprocesses the recent complete-month overlap window.
- Older nominal price history is treated as settled; the pipeline aborts if a protected month changes or disappears. A region-month that was missing last time (a failed download) can be filled in without tripping the guard.
- The lane commits as `aemo-nas-bot` and publishes only when canonical `outputs/summary.csv` changes, so daily workbook regeneration does not create noisy commits.
- GitHub Pages deploys on those pushes.
- GitHub Actions is kept as a manual verification/fallback runner.

*Historical:* this lane ran on a Hetzner VPS under the `aemo-historical-prices.timer` systemd timer before the 2026-09 NAS migration. That setup is retired and its unit files were deleted in the same cleanup.

## Project Structure

```
src/
├── config.py        # Constants, URLs, paths
├── download.py      # AEMO CSV downloader with caching
├── cpi.py           # RBA CPI fetch, interpolation, adjustment
├── analyse.py       # Peak filtering, monthly aggregation, completeness rule
├── excel_output.py  # Per-region workbooks and the All States workbook
└── main.py          # CLI orchestrator and settled-history guard
tests/
├── validate_outputs.py       # Output gate run by the lane before every commit
├── test_peak_window.py       # Peak-window boundary tests
└── test_pipeline_logic.py    # Guard, completeness, probe, CPI parsing, workbook tests
outputs/
├── summary.csv      # Master dataset (all regions, all months)
├── {NSW,QLD,VIC,SA,TAS}_historical_prices.xlsx   # Per-region workbooks
└── All_States_historical_prices.xlsx             # One monthly sheet per region
deploy/              # NAS lane runner script (run-update.sh) and env
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

After the pipeline runs and before committing, an automated validation step (`tests/validate_outputs.py`) checks, with exact expectations wherever the right answer is deterministic:

- `summary.csv` has every required column, no duplicate region/month rows, and finite prices (none below the −$1,000/MWh market floor)
- All 5 NEM regions are present, each contiguous from its start month (Tasmania: Jun 2005) to one common end month
- **Every** month, including the latest, holds exactly days × 48 (before Oct 2021) or days × 288 intervals, and exactly weekdays × 30 or × 180 peak intervals
- `carbon_flag` covers exactly Jul 2012 – Jun 2014
- CPI columns are consistent: `cpi_estimated` is only ever the most recent months, those months have real = nominal, and the CPI ratio is the same across regions and across the RRP and peak columns
- All 6 workbooks exist, have the expected sheets, and agree with `summary.csv`

If any check fails, the NAS lane or manual fallback workflow exits before committing — preventing bad data from reaching the dashboard.

## Notes

- **Peak hours**: Mon–Fri 07:00–22:00 AEST, public holidays included. AEMO stamps each interval with its end time, so an interval counts as peak when it ends after 07:00 and at or before 22:00 (the 30-min interval covering 21:30–22:00 is in; the one covering 06:30–07:00 is out)
- **Carbon tax period** (Jul 2012 – Jun 2014) is flagged in outputs
- **Data format change**: AEMO files before Oct 2021 hold 30-minute trading prices; from Oct 2021 they hold 5-minute prices. Every file has a header row. Both are handled automatically.
- **Tasmania** joined the NEM on 16 May 2005 and AEMO's first file starts mid-month, so its series starts with the first complete month, Jun 2005.
