"""Configuration for AEMO historical price analysis."""

from datetime import datetime

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

# Analysis start dates (TAS joined the NEM in May 2005)
START_DATE = datetime(2003, 7, 1)
REGION_START_DATES = {
    "NSW1": datetime(2003, 7, 1),
    "QLD1": datetime(2003, 7, 1),
    "VIC1": datetime(2003, 7, 1),
    "SA1": datetime(2003, 7, 1),
    "TAS1": datetime(2005, 5, 1),
}

# Peak hours: 7am-10pm weekdays AEST (standard NEM definition)
# Since SETTLEMENTDATE marks interval END, hour 7 means the 06:30-07:00 interval.
# We want intervals ending 07:00 through 22:00 (i.e. covering 07:00-22:00 period).
PEAK_START_HOUR = 7   # inclusive
PEAK_END_HOUR = 22    # exclusive (last included = 21)

# Carbon tax period (for flagging in outputs)
CARBON_TAX_START = datetime(2012, 7, 1)
CARBON_TAX_END = datetime(2014, 6, 30)

# Rolling average periods (years) for summary
ROLLING_PERIODS = [1, 2, 3, 5, 10]

# AEMO aggregated price CSV URL pattern
# Pre-Oct 2021: 30-min intervals, no header row
# Oct 2021+: 5-min intervals, has header row
AEMO_URL_PATTERN = (
    "https://aemo.com.au/aemo/data/nem/priceanddemand/"
    "PRICE_AND_DEMAND_{ym}_{region}.csv"
)

# Format change boundary
FORMAT_CHANGE_DATE = datetime(2021, 10, 1)

# RBA CPI data
RBA_CPI_URL = "https://www.rba.gov.au/statistics/tables/csv/g1-data.csv"
RBA_CPI_SKIP_ROWS = 11  # metadata rows before data

# Paths (relative to project root)
DATA_DIR = "data"
OUTPUT_DIR = "outputs"
SUMMARY_CSV = "outputs/summary.csv"

# Network retry settings
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # seconds
