"""SEC filing universe and sector classification.

CIK/ticker and sector/industry tables live in reference/*.json and are
loaded on first access.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

FILING_TYPES = ["10-K", "10-Q"]
MAX_FILINGS_PER_CIK = 5  # per filing type

# "demo" keeps only DEMO_TICKERS; "full" keeps the whole S&P 500.
UNIVERSE_MODE = "demo"

# Balanced across the 11 GICS sectors; includes the Dow 30 plus key S&P 500 names.
DEMO_TICKERS = {
    # Technology (6)
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "CRM", "CSCO", "INTC",
    # Financial Services (7)
    "JPM", "GS", "V", "MA", "BLK", "AXP", "SCHW",
    # Healthcare (6)
    "UNH", "JNJ", "LLY", "PFE", "AMGN", "MRK",
    # Consumer Cyclical (5)
    "AMZN", "TSLA", "HD", "NKE", "MCD",
    # Consumer Defensive (4)
    "PG", "KO", "WMT", "COST",
    # Industrials (5)
    "BA", "CAT", "HON", "UPS", "DE",
    # Communication Services (3)
    "DIS", "NFLX", "TMUS",
    # Energy (3)
    "CVX", "XOM", "COP",
    # Basic Materials (3)
    "DOW", "LIN", "FCX",
    # Utilities (3)
    "NEE", "DUK", "SO",
    # Real Estate (3)
    "AMT", "PLD", "EQIX",
}

_REFERENCE_DIR = Path(__file__).parent / "reference"


@lru_cache(maxsize=None)
def _load_full_cik_to_ticker() -> dict[int, str]:
    with open(_REFERENCE_DIR / "cik_to_ticker.json") as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.items()}


@lru_cache(maxsize=None)
def _load_ticker_sector_industry() -> dict[str, dict[str, str]]:
    with open(_REFERENCE_DIR / "ticker_sector_industry.json") as f:
        return json.load(f)


_CIK_TO_TICKER_FULL = _load_full_cik_to_ticker()

if UNIVERSE_MODE == "demo":
    CIK_TO_TICKER = {k: v for k, v in _CIK_TO_TICKER_FULL.items() if v in DEMO_TICKERS}
else:
    CIK_TO_TICKER = dict(_CIK_TO_TICKER_FULL)

TICKER_TO_CIK = {v: k for k, v in CIK_TO_TICKER.items()}

# Full (unfiltered) ticker-to-CIK mapping — used by the dashboard to let users
# process tickers outside the current UNIVERSE_MODE subset.
FULL_TICKER_TO_CIK = {v: k for k, v in _CIK_TO_TICKER_FULL.items()}

TICKER_SECTOR_INDUSTRY = _load_ticker_sector_industry()
