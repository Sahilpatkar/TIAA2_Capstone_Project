"""Pipeline orchestration knobs: version, worker count, pairing gaps."""

# Bump to force reprocessing of all filings.
PIPELINE_VERSION = "1.5"

PIPELINE_WORKERS = 4  # concurrent CIK workers for the pipeline runner

# Pairing gap (calendar days) per filing type.
# 10-K: annual, gap between 200 and 550 days.
# 10-Q: quarterly, gap between 60 and 150 days.
PAIRING_DAY_RANGE = {
    "10-K": (200, 550),
    "10-Q": (60, 150),
}
