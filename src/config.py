"""Configuration for AEMO historical price analysis."""

from datetime import datetime, timedelta, timezone

# NEM regions (AEMO region IDs)
REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]

# Friendly names for output files and display
REGION_NAMES = {
    "NSW1": "NSW",
    "QLD1": "QLD",
    "VIC1": "VIC",
    "SA1": "SA",
    "TAS1": "TAS",
}

# Analysis start dates. TAS joined the NEM on 16 May 2005 and AEMO's first TAS file starts mid-month
# (741 of 1,488 half-hour intervals), so its series starts with the first COMPLETE month, Jun 2005:
# a partial month must not be published as a month (README: "only complete months").
START_DATE = datetime(2003, 7, 1)
REGION_START_DATES = {
    "NSW1": datetime(2003, 7, 1),
    "QLD1": datetime(2003, 7, 1),
    "VIC1": datetime(2003, 7, 1),
    "SA1": datetime(2003, 7, 1),
    "TAS1": datetime(2005, 6, 1),
}

# Peak hours: Mon-Fri 07:00-22:00 AEST (public holidays are not excluded).
# SETTLEMENTDATE marks the interval END, so an interval is peak when its end stamp is after
# PEAK_START_HOUR:00 and at or before PEAK_END_HOUR:00 (see analyse.is_peak).
PEAK_START_HOUR = 7   # window opens here: an interval ending exactly 07:00 is off-peak
PEAK_END_HOUR = 22    # window closes here: an interval ending exactly 22:00 is peak

# Carbon tax period (for flagging in outputs)
CARBON_TAX_START = datetime(2012, 7, 1)
CARBON_TAX_END = datetime(2014, 6, 30)

# Rolling average periods (years) for the workbook Summary sheet. A period longer than a region's
# history is written as an explicit "n/a" row, never silently dropped.
ROLLING_PERIODS = [1, 2, 3, 5, 10, 15, 20]

# AEMO aggregated price CSV URL pattern. Every file has a header row.
# Before Oct 2021 the intervals are 30-minute trading periods; from Oct 2021 they are 5-minute.
AEMO_URL_PATTERN = (
    "https://aemo.com.au/aemo/data/nem/priceanddemand/"
    "PRICE_AND_DEMAND_{ym}_{region}.csv"
)

# Format change boundary
FORMAT_CHANGE_DATE = datetime(2021, 10, 1)

# RBA CPI data
RBA_CPI_URL = "https://www.rba.gov.au/statistics/tables/csv/g1-data.csv"
# The deflator is G1 column B, which must be the quarterly All groups CPI index. Anything else in
# that column (a re-ordered table, a percent-change series, a switch to monthly) fails the run.
RBA_CPI_SERIES_ID = "GCPIAG"
RBA_CPI_FREQUENCY = "Quarterly"
# The newest CPI quarter may be at most this many days old (quarter-end to NEM "now"), about 5
# months. ABS publishes a quarter about 4 weeks after it ends and RBA G1 follows within a day or
# two, so the oldest the newest quarter normally gets is about 4 months (e.g. 30 Jun until the Sep
# quarter lands in late Oct). 153 days fails the first run after a release is about a month late,
# instead of letting the "awaiting CPI" months pile up for a year.
CPI_MAX_AGE_DAYS = 153

# Paths (relative to project root)
DATA_DIR = "data"
OUTPUT_DIR = "outputs"
SUMMARY_CSV = "outputs/summary.csv"

# Network retry settings
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # seconds


# NEM time is fixed AEST (UTC+10, no daylight saving). Anything that asks "which month is it?"
# must use it rather than the runner's local clock.
NEM_UTC_OFFSET = timedelta(hours=10)


def nem_now() -> datetime:
    """Current wall-clock time in NEM time (naive datetime)."""
    return (datetime.now(timezone.utc) + NEM_UTC_OFFSET).replace(tzinfo=None)


# Lower bound on the newest published month (tests/validate_outputs.py). A month that ENDED at least
# this many days ago must be in summary.csv. AEMO's previous-month file has been complete by the 1st
# (and lags of up to 28 days have been seen), so 35 days never trips on normal publication lag; it
# catches a pipeline that keeps going green while no new month arrives.
AEMO_MAX_MONTH_LAG_DAYS = 35


def latest_required_month(now: datetime) -> str:
    """'YYYY-MM' of the newest month that must be published at `now` (NEM time): the newest month
    whose end (00:00 on the 1st of the next month) is at least AEMO_MAX_MONTH_LAG_DAYS ago."""
    cutoff = now - timedelta(days=AEMO_MAX_MONTH_LAG_DAYS)
    # Months ending on or before the cutoff are those before the cutoff's own month.
    last_month_end = datetime(cutoff.year, cutoff.month, 1) - timedelta(days=1)
    return last_month_end.strftime("%Y-%m")


def expected_interval_count(year: int, month: int) -> int:
    """Exact number of price intervals in a complete month: days x 48 (30-min, before Oct 2021)
    or days x 288 (5-min, from Oct 2021). AEMO's file for a month runs from 00:30 (00:05) on the
    1st to 00:00 on the 1st of the next month, so it holds exactly this many rows."""
    import calendar
    days = calendar.monthrange(year, month)[1]
    per_day = 288 if datetime(year, month, 1) >= FORMAT_CHANGE_DATE else 48
    return days * per_day
