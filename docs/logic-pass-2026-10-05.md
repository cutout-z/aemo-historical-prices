# Logic and computation audit: AEMO Historical Prices (branch design/2026-10)

Read-only. Nothing in the project was modified. Scratch scripts and cached raw samples were kept outside the repo.
Independent sources used: RBA G1 CSV (fetched live, 30-Jul-2026 publication) and AEMO PRICE_AND_DEMAND files for 24 NSW1/SA1 sample months plus TAS1 2005-05.
Project root: the repository root

## Findings (ranked)

### H1. Peak window is shifted by one interval (src/analyse.py:20-23, src/config.py:27-31)
Severity: High (published numbers silently wrong; small magnitude, so "High" mainly because it is a definite bug that contradicts the code's own comment).
- AEMO SETTLEMENTDATE is the interval END. I confirmed this in the raw files: the 30-min file starts 00:30 on the 1st and ends 00:00 on the 1st of the next month, and the 5-min file starts 00:05.
- The code keeps `hour >= 7 and hour < 22` on the end timestamp. That INCLUDES the interval ending 07:00, which covers 06:30-07:00 (30-min) or 06:55-07:00 (5-min) and is off-peak. It EXCLUDES the interval ending 22:00, which covers 21:30-22:00 or 21:55-22:00 and is peak.
- The config comment says "We want intervals ending 07:00 through 22:00". The code does not do that, and "ending 07:00 through 22:00" would itself be wrong. The correct end-stamp window is 07:00 < end <= 22:00, equivalently start in [07:00, 22:00).
- Effect: the real peak window is 06:30-21:30 pre Oct 2021 and 06:55-21:55 after. `peak_intervals` is unchanged (still 30 or 180 per weekday), so the validator and the interval counts cannot reveal it.
- Recomputed against the pipeline's own function (which reproduces summary.csv exactly) and a start-time-based mask. NSW1 and SA1 sample months, peak $/MWh:

  | Month | Pipeline | Boundary-correct | Diff |
  |---|---|---|---|
  | NSW 2016-03 | 49.96 | 48.76 | -2.4% |
  | SA 2016-03 | 73.59 | 72.32 | -1.7% |
  | NSW 2019-01 | 157.41 | 156.44 | -0.6% |
  | NSW 2024-01 | 80.48 | 80.61 | +0.2% |
  | TAS 2005-05 | 392.08 | 361.77 | -7.7% (partial month) |

- Median absolute error across typical sampled months is about 0.5%, with the sign varying.
- Fix: in `is_peak`, compute minutes-of-day `t = hour*60+minute` and use `(t > 420) & (t <= 1320)` for the end-stamp. Alternatively subtract the interval length (30 min before `FORMAT_CHANGE_DATE`, else 5) and use `(start >= 07:00) & (start < 22:00)`. Weekday must be judged on the same start-based timestamp. This is equivalent here because the only cross-day stamp is 00:00, which is never peak. Update the docstring and comment. Add a unit test with the boundary stamps 07:00, 07:05, 22:00 and 22:05.

### M1. Public holidays are counted as peak weekdays, but the copy calls it the "standard NEM definition" (analyse.py:20; config.py:27; README:144; index.html:33, 76)
Severity: Medium. The numbers are right for the stated algorithm. The label is inconsistent with the common market usage, as I understand it: ASX energy futures peak (07:00-22:00 Mon-Fri) excludes national public holidays. I am fairly, not fully, certain of this.
- Effect is material in months with holidays, because holidays are low-demand and often low-price. With the boundary also fixed and approximate national holidays excluded (Jan 1, Jan 26 observed, Easter Fri/Mon, Apr 25, Dec 25/26), peak $/MWh moved as follows:

  | Month | Pipeline | Holidays excluded |
  |---|---|---|
  | NSW 2025-12 | 77.75 | 83.25 (+7.1%) |
  | NSW 2022-04 | 204.07 | 215.98 (+5.8%) |
  | NSW 2025-01 | 93.90 | 97.99 (+4.4%) |
  | SA 2024-04 | 81.99 | 85.98 (+4.9%) |
  | SA 2025-01 | 8.76 | 13.92 (+59%) |
  | SA 2025-12 | -0.41 | +11.53 |

- The only negative peak average in the dataset (SA1 2025-12, -$0.41) is a Christmas/Boxing Day artefact. It would be positive under the ex-holiday definition.
- Fix: either exclude national public holidays (the `holidays` package or a fixed list; the state-vs-national choice must be documented), or reword every instance to "Mon-Fri 07:00-22:00 AEST, public holidays included" and drop "standard NEM definition". The `peak_intervals` check would then need a holiday-aware expectation.

### M2. README worked example does not match the data or the code (README:46, 57-65)
Severity: Medium (docs). The example is presented as real.
- README:46 says NSW Jan 2021 "has ~8,928 five-minute intervals". Jan 2021 is pre-Oct 2021, so it has 1,488 30-min intervals (summary.csv: total_intervals=1488). 8,928 is the Oct 2021 / Jan 2024 5-min count.
- Actual NSW Jan 2021 values:

  | Item | README | Actual |
  |---|---|---|
  | Nominal RRP | $85.00 | $38.84 |
  | Interpolated CPI | 78.5 | 81.557 |
  | Latest-quarter CPI | 102.3 labelled "Dec 2025" | 102.31 is the Jun 2026 quarter (Dec 2025 is 100.32) |
  | Real price | $110.80 | $48.72 |

- README:34 and 65 use Dec 2025 as the base and "Jan-Mar 2026" as the estimated months. Today's base is Jun 2026 and the estimated months are Jul-Sep 2026. The text says "e.g.", but the numbers are internally inconsistent with the stated data.
- Fix: regenerate the example from outputs/summary.csv (NSW 2021-01: 38.84, CPI 81.557, 102.31, real 48.72), or label it "illustrative, not actual".

### M3. Rolling-average periods: README says 1/3/5/10/15/20, code gives 1/2/3/5/10 (config.py:38, excel_output.py:112, README:14, 69)
Severity: Medium (doc and code inconsistent). I opened all 5 regional workbooks: each Summary has 1, 2, 3, 5 and 10-year rows. There is no 15 or 20 and no hidden skipped row. The dashboard shows 1/3/5/10 (index.html:131), so the three surfaces disagree. TAS has 257 months, so a 15-year row would exist for TAS, but one is never generated.
- Fix: set `ROLLING_PERIODS = [1,2,3,5,10,15,20]`, or fix the README. Decide whether the dashboard should also show 2.
- Related silent skip: excel_output.py:114-115 drops any period when `len(data) < N*12` with no "N/A" row. The workbook would just have fewer rows for a short-history region.

### M4. TAS May 2005 is a partial month published as a complete one (summary.csv row 837; validator exemption validate_outputs.py:18-20, 58-61)
Severity: Medium (contradicts "only complete months shown" in README:15 and index.html:404).
- TAS1 2005-05 has 741 intervals, not the 1,488 a full month would have. The AEMO file starts 2005/05/16 14:00, so about 15.4 of 31 days are covered. It carries rrp_nominal=306.87 and rrp_real=548.53.
- It is the first row of the TAS table and the oldest row in the TAS workbook, and it is counted in "257 months". Every other region-month matches `days_in_month*48` or `*288` exactly. I checked all 1,373 rows; 741 is the sole exception.
- The peak value is also computed over a different set of days. It is outside every rolling window now, so no KPI is affected.
- Fix: show it with a "partial" marker, or start TAS in Jun 2005 (`REGION_START_DATES["TAS1"] = 2005-06-01`).

### M5. Settled-history guard blocks healing of any earlier gap (main.py:103-114 with 178-197)
Severity: Medium (robustness; fails loud, so the daily lane would wedge, not publish bad data).
- Per-region download exceptions and 404s are swallowed (main.py:195-197) and the row is simply missing. On the next run that missing (region, month) is retried because it is not in `existing`.
- The guard then sees a row that did not exist in `before` for a non-mutable month. `after_protected` is filtered by `isin(before months)`, so it picks up the new row. `assert_frame_equal` raises on the shape mismatch, giving "attempted to change settled nominal months".
- I reproduced this by calling the guard with a summary missing QLD1 2020-05 and the full summary as "after": it raises RuntimeError. Mutable-window deletions and new latest months pass, as intended.
- Consequence: any gap older than `--months-back` (deploy uses 2) can only be fixed with `--full-refresh`.
- Fix: in the guard, compare only keys present in both frames (inner-merge on region/year_month) and separately assert that no `before` key vanished.

### M6. Validator is too weak to catch the failures that matter (tests/validate_outputs.py)
Severity: Medium. Things it can pass while the data is wrong:
- 55-61: the latest month is excluded from the interval-count check. That is the month most at risk of being partial.
- 68, 77: the ranges [1100,1700] and [7000,10000] are far wider than the deterministic expected value. Expected count is exactly days*48 (30-min) or days*288 (5-min), and I verified every row matches except the TAS first month. A month missing about 8 days (30-min) or about 3.5 days (5-min) passes.
- No contiguity check per region (a missing month passes), and no check that all regions end on the same month. A transient failure for one region at the latest month passes silently (main.py:195-197).
- No check on CPI columns: real>0, real==nominal exactly when `cpi_estimated`, ratio non-increasing except at genuine deflation quarters, or `cpi_estimated` only as a suffix.
- No check of carbon_flag window or TAS start.
- 98-101: `> -500` average floor is nearly vacuous (actual min is -0.41).
- `peak_intervals <= total_intervals` is trivially true, and cannot detect the H1 boundary shift or a holiday policy change.
- Fix: exact interval-count expectation per month (allow TAS 2005-05 explicitly), contiguity and equal-end-month checks, and the CPI invariants above.

### L1. `--full-refresh` does not re-download cached files (main.py:187, download.py:38)
`force=(not full_refresh and ym in force_months)` is False for a full refresh, so cached CSVs are reused. README:86 says it "re-downloads everything from Jul 2003". On the NAS the cache is pruned only after 120 days (prune-raw-cache.sh), so a refresh can silently reuse files cached when a month was incomplete. Fix: pass `force=True` on full refresh, or say "uses cache".

### L2. `get_latest_available_month` date arithmetic skips months (download.py:96-99)
`now - timedelta(days=30*months_back)` is not calendar months. On 1 Mar 2026, the first fallback probe is 30 Jan, so Feb is never probed. This only bites if the current-month file is momentarily 404/non-200 (then the code returns January). Non-200 statuses other than 404 also `break` to an earlier month and silently return an older month (110-114). Fix: step back by calendar month, and treat non-200/404 as an error.

### L3. "Complete month" is a calendar test, not a data test (main.py:148-153; analyse.py:88-104)
Completeness is `latest month != date.today() month` in the runner's local timezone. The runner is UTC or AEST/AEDT, whereas NEM time is fixed AEST. In AEDT months a Sydney-local run on the 1st between 00:00-01:00 AEDT would take a month with the final hour missing. It self-heals on the next run via the mutable window, but the validator exempts the latest month. `_check_interval_count` only logs warnings, and with loose bounds (1200-1600 / 7500-9500).

### L4. Fallbacks and blanks mask missing data
- analyse.py:44-47: if a month had zero peak intervals, peak is silently set to the all-hours mean. Impossible for complete months, but it would be mislabelled.
- analyse.py:36: `total_intervals = len(df)` counts NaN RRP rows, which the mean skips.
- index.html:238-239: `parseFloat(r[col] || 0)` turns a blank into 0 and drags the KPI down, while the table cell (index.html:299-300) shows "N/A" for the same blank. Inconsistent. There are no blanks in the data today. Fix: skip NaN rows in the KPI and show N/A if any month in the window is missing.
- index.html:305-306, 172: booleans are compared to the literal strings 'True'/'False'. If pandas ever writes lowercase, carbon markers, daggers and `cpiBase()` fail silently. If the `cpi_estimated` column is missing, `cpiBase()` returns the last data month, which is wrong.

### L5. Real-price KPI and workbook include un-deflated months with no flag (index.html:233-242; excel_output.py:120-124, 144-146)
The 1-year real average (Oct 2025-Sep 2026) includes 3 months (Jul-Sep 2026) with ratio 1. The table shows a dagger in real mode and a footnote, but the KPI tiles and the Excel workbooks do not. The Excel Monthly Data sheet has no `cpi_estimated` column and the Summary has no "real = Jun 2026 dollars" label. Fix: add the base label to the Summary sheet, and a note on KPI tiles when the window contains estimated months.

### L6. CPI method notes (cpi.py:72-73)
- Quarterly value is anchored to the quarter-end month (Mar/Jun/Sep/Dec). That matches the README's Oct = 1/3 Sep-to-Dec statement exactly, so code and docs agree. An ABS quarterly index is a quarter average, so the more standard anchor is mid-quarter (Feb/May/Aug/Nov). Re-running with mid-quarter anchoring changes real prices by +0.22% on average (range -0.65% to +0.72%) across all months. The effect is immaterial but systematic.
- The G1 units line now reads "Index, September 2025 month = 100", which suggests ABS monthly CPI exists. A monthly series would remove the interpolation and the Jul-Sep 2026 "real = nominal" window. I have not verified an ABS monthly series is available through this RBA table.
- The first G1 data row (30/06/1922) is consumed as the header (`header=0`, cpi.py:40-46). Harmless today, but fragile to a layout change. RBA's metadata block currently has exactly 11 rows. A change would silently misparse.

### L7. Doc and comment nits
- config.py:41-42, README:146 and download.py (docstring at :72 says "All AEMO files have a header row") contradict each other about headers. The raw 2003, 2019 and 2021 samples all have headers, so the "no headers" statements in config and README are wrong.
- index.html:76 says "RRP averages every dispatch interval". Pre-Oct 2021 are 30-min trading intervals, and Jul 2003 to present at index.html:33 does not hold for TAS (May 2005).
- Rolling averages are means of monthly means (unweighted by days). This matches README:69-71 and the "average monthly price" wording, so it is fine, but it is not an interval-weighted mean.
- README project structure omits the All_States workbook; the validator checks for it.

## Verified correct (checked, found sound)

CPI and real prices
- RBA G1 column B is series GCPIAG, "Consumer price index; All groups", original, quarterly. This is the right headline index. The base-year rebase (Sep 2025 month = 100) is irrelevant to the ratio method.
- Every rrp_real and peak_rrp_real in summary.csv (1,373 rows) reproduces exactly (max diff 0.00) from my own interpolation of the live G1 data. Real = nominal x (102.31 / CPI_month), rounded to 2dp, applied identically to the peak column.
- The interpolation weights are exactly as README states: Oct 2025 = 99.9267 = Sep + 1/3(Dec - Sep), and Nov = 2/3.
- CPI_latest is 102.31, the Jun 2026 quarter, and the base month is Jun 2026. Ratio is exactly 1.000000 from 2026-06 on.
- `cpi_estimated` is True for exactly Jul, Aug and Sep 2026, for all 5 regions, and False for every earlier month.
- The ratio is identical across regions in a month (within 4e-4, which is 2dp rounding of the inputs).
- Ratio increases only at genuine CPI deflation quarters, which is consistent with a monotonic index outside those quarters.
- Future blank-dated G1 rows (30/09/2026 etc.) are dropped by dropna, so the latest quarter is correctly the last published one.

Aggregation and data completeness
- Re-running `analyse_month` on 7 downloaded AEMO files reproduces summary.csv rrp_nominal, peak_rrp_nominal, total_intervals and peak_intervals exactly. Month membership by file is correct: the 00:00 stamp on the 1st of the next month belongs to the last day of the month, and the file includes it.
- Total intervals equal `days*48` (pre Oct 2021) or `days*288` (from Oct 2021) for every row except TAS 2005-05. Peak interval counts equal weekdays*30 or *180 for every row except TAS 2005-05.
- The 30-min to 5-min switch (Oct 2021) lines up with the file format and with the validator's FORMAT_CHANGE.
- No timezone or DST issue: AEMO SETTLEMENTDATE is fixed AEST and no conversion is applied. The weekday test is fine.
- Carbon flag: exactly Jul 2012 to Jun 2014 (24 rows) for every region, no spill. The `<= 2014-06-30` comparison works because month_date is the 1st.
- Region list and TAS start: 5 regions, and TAS starts 2005-05 (with the partial caveat M4).
- summary.csv per region: contiguous (no gaps), sorted, no duplicates, no nulls. NSW/QLD/VIC/SA have 279 months; TAS has 257.

Incremental logic
- Merge and dedupe on (region, year_month) with keep="last" lets fresh rows override existing ones. Sort is by region then year_month. Existing CPI columns are dropped and recomputed for all rows.
- The guard protects nominal columns, intervals and carbon flag outside the mutable window. A +0.01 change to a settled value is caught; a deletion in the mutable window is allowed.
- A new latest month is allowed (only M5's gap-heal case is wrongly blocked).

Excel
- All five regional workbooks and All_States match summary.csv to the cent on every data-sheet value and the carbon column. Summary-sheet rolling averages (1, 2, 3, 5, 10 yr) for all five regions reproduce exactly as `tail(N*12).mean()` for nominal, peak, real and peak real.
- "Data through: Sep 2026" is correct. Heatmap ranges B2:E(n+1) cover every row.
- TAS correctly gets all five periods (257 months).

Dashboard (index.html script)
- Ported the script logic to Node and compared with Python means: KPI tiles for 1/3/5/10 years, RRP and Peak, nominal and real, for NSW/TAS/SA. All equal the workbook values (e.g. NSW 5-yr nominal $116.80/$135.14, window Oct 2021-Sep 2026).
- `slice(-years*12)` is correct today because there are no gaps in any region. A future gap would silently widen the window by calendar span. This is the same hazard as the Excel `tail()`.
- `cpiBase()` returns 2026-06, which is the pipeline's base month (the last non-estimated month). "Jun 2026 dollars" is correct.
- Dagger logic: shows only in real mode and only for estimated rows. The footnote count is 3.
- `HEAT_STOPS`/`heatStep` boundaries match the legend labels (lower-bound inclusive, 29.99 to step 0, 30 to step 1, 250 to step 7, negatives to step 0). The "half of prices between $30 and $80" comment is accurate (56%).
- `usd()` renders negatives as "−$0.41" correctly, using a minus sign and the absolute value.
- Carbon marker uses `carbon_flag==='True'`, and the data carries it for exactly the right 24 rows per region.
- Compared with `main:index.html`, KPI arithmetic is unchanged. Behavioural differences:
  - 8 cards became 4 tiles with Peak in the note.
  - N/A tiles replace silently skipped periods.
  - Heat colouring changed from per-region continuous min-max to fixed dollar stops (legend labelled, one scale for all regions and bases).
  - Negative display changed from "$-0.41" to "−$0.41".
  - Blank handling in the table changed from 0 to "N/A", while KPIs still coerce blank to 0.
  - Footer changed from the stale "Updates monthly on the 3rd" to "Checked daily".
  - New cpiBase labelling.
  - `filter(r => r.region && r.year_month)` is new.
  - No other logic change.

## Summary count
High 1, Medium 6, Low 7. The most important fixes are H1 (boundary mask), M1 (holiday policy or relabel), and M2/M3 (README example and rolling-period list).
