"""Tests for deploy/run-update.sh's commit rules. No network: a throwaway local origin and a fake
Python stand in for GitHub and the pipeline.

Runs under pytest or directly:  python tests/test_run_update.py
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "run-update.sh"

# Stands in for the venv Python: "-m src.main" regenerates the outputs the way the pipeline does
# (workbooks rewritten every run, status.json stamped every run, summary.csv changed only when told);
# "tests/validate_outputs.py" passes. With $FAKE_SUMMARY set it records the summary it was given as
# input (in $FAKE_LOG/input) and writes $FAKE_SUMMARY as the new summary.
FAKE_PYTHON = """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "-m" ]]; then
  echo "regenerated $RANDOM$RANDOM" > outputs/NSW_historical_prices.xlsx
  printf '{"last_checked_utc": "%s"}\\n' "${FAKE_STAMP}" > outputs/status.json
  if [[ "${FAKE_DATA_CHANGE:-0}" == "1" ]]; then echo "NSW1,2026-10" >> outputs/summary.csv; fi
  if [[ -n "${FAKE_SUMMARY:-}" ]]; then
    cp outputs/summary.csv "${FAKE_LOG}/input"
    printf '%s' "${FAKE_SUMMARY}" > outputs/summary.csv
  fi
fi
"""
COMMITTED = "region,year_month\nNSW1,2026-09\n"


def _git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _setup(tmp: Path) -> Path:
    origin, app = tmp / "origin.git", tmp / "app"
    _git(tmp, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp, "clone", "-q", str(origin), str(app))
    _git(app, "checkout", "-q", "-b", "main")
    (app / "outputs").mkdir()
    (app / "outputs" / "summary.csv").write_text(COMMITTED)
    (app / "outputs" / "NSW_historical_prices.xlsx").write_text("original\n")
    _git(app, "add", ".")
    _git(app, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed")
    _git(app, "push", "-q", "origin", "main")
    fake = tmp / "fake-python"
    fake.write_text(FAKE_PYTHON)
    fake.chmod(0o755)
    return app


def _update(tmp: Path, app: Path, stamp: str, data_change=False, summary=None) -> str:
    log = tmp / "log"
    log.mkdir(exist_ok=True)
    env = {**os.environ, "APP_DIR": str(app), "PYTHON": str(tmp / "fake-python"), "RUN_RAW_CACHE_PRUNE": "0",
           "FAKE_STAMP": stamp, "FAKE_DATA_CHANGE": "1" if data_change else "0",
           "FAKE_SUMMARY": summary or "", "FAKE_LOG": str(log)}
    return subprocess.run(["bash", str(SCRIPT)], env=env, check=True, capture_output=True, text=True).stdout


def _last_commit(app: Path) -> tuple[str, list[str]]:
    subject = _git(app, "log", "-1", "--format=%s").strip()
    files = _git(app, "show", "--name-only", "--format=", "HEAD").split()
    return subject, files


def test_unchanged_data_publishes_only_status_json():
    if not shutil.which("git"):
        return
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        app = _setup(tmp)

        # Day 1: no data change. status.json is new: committed alone, workbooks left as they were.
        _update(tmp, app, "2026-10-07T00:38:12Z")
        subject, files = _last_commit(app)
        assert subject.startswith("Status check ") and subject.endswith("(no data change)"), subject
        assert files == ["outputs/status.json"], files
        assert (app / "outputs" / "NSW_historical_prices.xlsx").read_text() == "original\n"
        assert _git(app, "status", "--porcelain", "outputs") == ""
        assert _git(app, "rev-parse", "HEAD") == _git(app, "rev-parse", "origin/main"), "not pushed"

        # Day 2: no data change, new stamp: another status-only commit.
        _update(tmp, app, "2026-10-08T00:38:12Z")
        subject, files = _last_commit(app)
        assert subject.startswith("Status check ") and files == ["outputs/status.json"], (subject, files)
        assert "2026-10-08" in (app / "outputs" / "status.json").read_text()
        n = int(_git(app, "rev-list", "--count", "HEAD"))

        # Same stamp again (status.json identical): nothing to commit.
        out = _update(tmp, app, "2026-10-08T00:38:12Z")
        assert "nothing to publish" in out, out
        assert int(_git(app, "rev-list", "--count", "HEAD")) == n

        # A data change is a normal data commit carrying everything, status.json included.
        _update(tmp, app, "2026-10-09T00:38:12Z", data_change=True)
        subject, files = _last_commit(app)
        assert subject.startswith("Update historical price analysis "), subject
        assert set(files) == {"outputs/summary.csv", "outputs/NSW_historical_prices.xlsx",
                              "outputs/status.json"}, files



def test_leftover_summary_is_not_the_baseline():
    # A run that failed after the pipeline (e.g. in the validator) left the new data uncommitted in
    # outputs/summary.csv. The next run produces the same data: it must still be published, not
    # dropped as "no change" against the leftover file.
    if not shutil.which("git"):
        return
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        app = _setup(tmp)
        new = COMMITTED + "NSW1,2026-10\n"
        (app / "outputs" / "summary.csv").write_text(new)
        _update(tmp, app, "2026-10-09T00:38:12Z", summary=new)
        subject, files = _last_commit(app)
        assert subject.startswith("Update historical price analysis "), subject
        assert "outputs/summary.csv" in files, files
        assert _git(app, "show", "HEAD:outputs/summary.csv") == new


def test_run_starts_from_committed_outputs_not_leftovers():
    # A failed or manual run left the summary edited and a stray file in outputs/.
    if not shutil.which("git"):
        return
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        app = _setup(tmp)
        (app / "outputs" / "summary.csv").write_text(COMMITTED + "NSW1,2026-10\n")
        (app / "outputs" / "stray.xlsx").write_text("left over\n")
        new = COMMITTED + "QLD1,2026-09\n"
        _update(tmp, app, "2026-10-09T00:38:12Z", summary=new)
        # The pipeline reads the committed summary, not the edited one ...
        assert (tmp / "log" / "input").read_text() == COMMITTED
        # ... and only the pipeline's own outputs are published.
        _, files = _last_commit(app)
        assert "outputs/stray.xlsx" not in files, files
        assert not (app / "outputs" / "stray.xlsx").exists()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
    print(f"\n{len(tests)} run-update tests passed")
