# Plan — refreshing published history after the peak-window fix

Status: **planned, not executed.** The fix is on branch `fix/peak-window` (commit `1ea371f`),
deliberately **not merged to `main`**.

## What changes, and what does not

The fix moves the peak window back to the intended Mon–Fri 07:00–22:00 (AEMO stamps interval *ends*;
the old filter kept the interval ending 07:00 and dropped the one ending 22:00). Only these published
columns change: `peak_rrp_nominal`, `peak_rrp_real` (and the same numbers inside the workbooks and the
page). Everything else is identical by construction: `rrp_*`, `total_intervals`, `peak_intervals`
(still 30/180 per weekday), `carbon_flag`, `cpi_estimated`.

Size of the restatement (audit samples, NSW/SA): typically about ±0.5% of the peak price; larger in
volatile months (TAS 2005-05: 392.08 → 361.77; NSW 2016-03: 49.96 → 48.76, recomputed on the raw file).
The full-history number comes from step 3 below.

## Why it cannot just be merged

`main.py`'s settled-history guard protects `peak_rrp_nominal` for every month outside the mutable
window. If the fixed code reaches `main` while `outputs/` still holds old peaks, the next NAS run
(`--months-back 2`) will (a) restate only the last two months on the new window, leaving 277 months on
the old one — a series with a seam in it — and, if it touches a settled month, (b) trip the guard and
wedge the lane. So code and outputs must land in **one commit**.

## Steps

1. **Freeze.** Tag the current state so it is one command to return to:
   `git tag pre-peak-window-fix origin/main && git push origin pre-peak-window-fix`.
   Pick a moment just after the monthly data lands, so no NAS publish is mid-flight (the lane commits as
   `aemo-nas-bot` and pushes only when `summary.csv` changes).
2. **Rebuild from raw.** On `fix/peak-window`, in a clean venv:
   `pip install -r requirements.txt && python -m src.main --full-refresh`.
   `data/` is empty on the laptop (raw cache is gitignored and the NAS prunes it to 120 days), so this
   downloads one AEMO CSV per region-month (~1,370 files) plus the RBA CPI table. `--full-refresh`
   bypasses the settled-history guard on purpose ("deliberate audited rewrites"). Note the audit's L1:
   it reuses any cached file rather than re-downloading, so start from an empty `data/`.
3. **Prove only peak moved.** Before step 2 save the old file
   (`cp outputs/summary.csv /tmp/summary.before.csv`), then
   `python3 scripts/compare-summaries.py /tmp/summary.before.csv outputs/summary.csv`.
   It exits 1 if anything other than `peak_rrp_nominal` / `peak_rrp_real` differs, and prints how many
   rows moved and by how much. Expect: same 1,373 keys, 0 changes elsewhere. **Stop and investigate if
   `rrp_nominal` or any count differs** — that would mean the re-download disagrees with history
   (AEMO revision), which is a separate question from this fix.
4. **Gate.** `python3 tests/validate_outputs.py` and `python3 tests/test_peak_window.py` must pass.
5. **One commit, one push.** Merge `fix/peak-window` into `main` with the regenerated `outputs/`
   (`summary.csv` + six workbooks) in the *same* push. The Pages workflow redeploys on `outputs/**`.
   The NAS lane needs no change: `deploy/run-update.sh` fast-forwards (or resets onto) `main` before
   running, and its next `--months-back 2` pass compares like with like.
6. **After.** Confirm the next NAS run logs "Settled-history guard: … rows unchanged" and publishes
   nothing; open the live page and spot-check a restated month (NSW 2016-03 peak should read $48.76
   nominal). Check anything else that reads the peak columns (this project's entry in the AI Wif brain
   dashboard registry points at the repo; it should only need the new numbers, but look).

## Rollback

`git revert` the merge commit (restores code and outputs together) or reset to tag
`pre-peak-window-fix`. The settled-history guard will accept the old values again because they
are the values the old outputs carried.

## Deliberately not in this change

- **Public holidays.** Still counted as peak; the README now says "public holidays included". The
  audit believes ASX peak excludes national holidays but was not certain; that needs a decision on
  the calendar (national vs NSW/VIC/…) and moves peak a lot more than this fix (e.g. SA 2025-12:
  −0.41 → +11.53). Separate decision.
- The other audit findings (TAS 2005-05 partial month, validator strength, guard behaviour on healed
  gaps, README example, rolling-period lists): see `logic-pass-2026-10-05.md`.

## Execution record — 2026-10-05

Steps 1–4 were run on `fix/peak-window`; step 5 (merge + push) waits for a go-ahead.

- Tag `pre-peak-window-fix` created on `origin/main` (`1194475`) and pushed.
- `--full-refresh` from an empty `data/`: 1,374 raw files, ~7 minutes, 0 errors, 1,373 rows.
- `compare-summaries.py` against the old file: keys identical; `rrp_nominal`, `rrp_real`,
  `total_intervals`, `carbon_flag`, `cpi_estimated` unchanged on every row. **One expected exception:**
  `peak_intervals` for TAS1 2005-05 (the known partial month, 346 → 347).
- Independent check: peak recomputed from all 1,373 raw files by interval *start* time (a different
  method from the pipeline's end-stamp logic): 0 disagreements in price or count.
- Workbooks vs new `summary.csv`: 0 disagreeing peak cells (nominal and real, all five regions).
- `validate_outputs.py` and `test_peak_window.py` pass.
- Restatement: 1,352 of 1,373 rows moved (peak only); median |Δ| 0.46%, mean −0.8%; 314 rows
  moved >1%, 24 >5%, 3 >20% (TAS 2010-11 38.48 → 19.55; QLD 2015-07 58.91 → 41.74 — a price spike
  in an edge interval). The one negative peak is now SA 2025-12 at −$0.04 (was −$0.41).
  Page headline peak averages moved by at most ~$0.75 (NSW 10-year: 115.11 → 114.46).
