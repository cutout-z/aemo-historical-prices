#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/workspace/repos/aemo-historical-prices}"
PYTHON="${PYTHON:-${APP_DIR}/.venv/bin/python}"
PIPELINE_ARGS="${PIPELINE_ARGS:---months-back 2}"
RUN_TESTS="${RUN_TESTS:-1}"
PUSH_CHANGES="${PUSH_CHANGES:-1}"
RUN_RAW_CACHE_PRUNE="${RUN_RAW_CACHE_PRUNE:-1}"
COMMIT_MESSAGE_PREFIX="${COMMIT_MESSAGE_PREFIX:-Update historical price analysis}"
STATUS_COMMIT_PREFIX="${STATUS_COMMIT_PREFIX:-Status check}"
STATUS_FILE="outputs/status.json"

cd "${APP_DIR}"

git fetch origin main
git checkout main
if ! git pull --ff-only origin main; then
  echo "origin/main is not fast-forwardable (rewritten?) — resetting onto it."
  git reset --hard origin/main
fi
before_summary="$(mktemp)"
cp outputs/summary.csv "${before_summary}" 2>/dev/null || true

"${PYTHON}" -m src.main ${PIPELINE_ARGS}

if [[ "${RUN_TESTS}" == "1" ]]; then
  "${PYTHON}" tests/validate_outputs.py
fi

if [[ "${RUN_RAW_CACHE_PRUNE}" == "1" ]]; then
  "${APP_DIR}/deploy/prune-raw-cache.sh"
fi

git config user.name "${GIT_AUTHOR_NAME:-aemo-nas-bot}"
git config user.email "${GIT_AUTHOR_EMAIL:-aemo-nas-bot@users.noreply.github.com}"

git add outputs/

if [[ -s "${before_summary}" ]] && cmp -s "${before_summary}" outputs/summary.csv; then
  # The data did not change: drop the regenerated workbooks (publish noise), but still publish
  # status.json so the page's "last checked" date moves. The pipeline writes it on every successful
  # run and the validator has just checked it. It is saved around the reset, which would otherwise
  # revert it (or delete it, the first time it is added).
  rm -f "${before_summary}"
  status_copy="$(mktemp)"
  cp "${STATUS_FILE}" "${status_copy}"
  git restore --staged --worktree -- outputs/
  cp "${status_copy}" "${STATUS_FILE}"
  rm -f "${status_copy}"
  git add -- "${STATUS_FILE}"
  if git diff --cached --quiet; then
    echo "No canonical summary.csv changes and status.json is unchanged; nothing to publish."
    exit 0
  fi
  git commit -m "${STATUS_COMMIT_PREFIX} $(date -u +%Y-%m-%d) (no data change)"
  echo "No canonical summary.csv changes; published status.json only."
else
  rm -f "${before_summary}"

  if git diff --cached --quiet; then
    echo "No publishable output changes."
    exit 0
  fi

  git commit -m "${COMMIT_MESSAGE_PREFIX} $(date -u +%Y-%m)"
fi

if [[ "${PUSH_CHANGES}" == "1" ]]; then
  git push origin main
else
  echo "PUSH_CHANGES=0; commit created but not pushed."
fi
