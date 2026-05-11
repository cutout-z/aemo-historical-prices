#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/aemo-historical-prices}"
RAW_CACHE_RETENTION_DAYS="${RAW_CACHE_RETENTION_DAYS:-120}"

find "${APP_DIR}/data" -type f -name 'PRICE_AND_DEMAND_*.csv' -mtime +"${RAW_CACHE_RETENTION_DAYS}" -delete 2>/dev/null || true
