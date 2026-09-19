# Frequency-Driven Updates — NAS runner (production)

The production model:

- The **NAS runner** (QNAP `ai-wif-runner` container) runs the scheduled
  historical-price data monitor and keeps only a bounded recent raw cache.
- GitHub stores code and publishable `outputs/`.
- GitHub Pages deploys after the NAS lane pushes updated outputs.
- GitHub Actions remains available for manual verification, but is not the
  primary scheduled data runner.

## Lane

QNAP scheduled tasks invoke `nas-job aemo-historical-prices`, which runs this
repo's `deploy/run-update.sh` (renamed from the retired VPS-era
`run-vps-update.sh` in the 2026-09 cleanup) with the lane's `PIPELINE_ARGS`:

| Lane | `PIPELINE_ARGS` | Purpose |
| --- | --- | --- |
| Historical price data monitor | `--months-back 2` | Check for newly published or corrected monthly AEMO price/demand CSVs, reprocess the recent complete-month overlap window, preserve settled nominal history, regenerate CPI-adjusted outputs and workbooks only when canonical summary data changes. |

The lane registry, cadence windows and report paths live in
`tools/nas-runner/configs/brain-ops.nas.toml` (the NAS runner tooling).
`deploy/run-update.sh` runs the full test suite and commits/pushes only when
`outputs/` changed, and the script self-heals a rewritten `main`: if
`git pull --ff-only` is impossible it resets onto the fetched remote instead
of exiting 128.

## Raw Cache Retention

`RUN_RAW_CACHE_PRUNE=1` with `RAW_CACHE_RETENTION_DAYS=120` bounds the raw
cache via `deploy/prune-raw-cache.sh`.

## Env

`deploy/env.example` documents the settings the lane injects (`APP_DIR`,
`PIPELINE_ARGS`, test/push toggles, cache retention).
