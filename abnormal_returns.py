"""
Compute cumulative abnormal returns (CAR) around 10-K filing dates.

Uses Yahoo Finance for daily price data and a simple market-adjusted
model (stock return minus S&P 500 return) over a configurable event window.

Usage:
    python abnormal_returns.py --ticker AAPL --filed-date 2024-11-01
"""

import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

import config


def _trading_days_around(filed_date: str, buffer_calendar_days: int = None) -> tuple[str, str]:
    """Return (start, end) date strings with enough buffer to cover the event window."""
    buf = buffer_calendar_days or config.CAR_BUFFER_DAYS
    dt = datetime.strptime(filed_date, "%Y-%m-%d")
    start = dt - timedelta(days=buf)
    end = dt + timedelta(days=buf)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _daily_returns(ticker: str, start: str, end: str) -> pd.Series:
    """Fetch adjusted close prices from Yahoo Finance and compute daily returns."""
    data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if data.empty:
        return pd.Series(dtype=float)
    close = data["Close"].squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.pct_change().dropna()


def compute_car(
    ticker: str,
    filed_date: str,
    window: tuple[int, int] | None = None,
    market_ticker: str | None = None,
) -> dict:
    """
    Compute the cumulative abnormal return around *filed_date*.

    Parameters
    ----------
    ticker : str
        Stock ticker (e.g. "AAPL").
    filed_date : str
        Filing date in YYYY-MM-DD format.
    window : tuple[int, int], optional
        (start_offset, end_offset) in trading days relative to filed_date.
        Defaults to config.CAR_WINDOW.
    market_ticker : str, optional
        Market index ticker.  Defaults to config.MARKET_TICKER.

    Returns
    -------
    dict with keys: ticker, filed_date, car, window, daily_abnormal (list).
    Returns car=None when data is unavailable.
    """
    window = window or config.CAR_WINDOW
    market_ticker = market_ticker or config.MARKET_TICKER

    start_str, end_str = _trading_days_around(filed_date)

    stock_ret = _daily_returns(ticker, start_str, end_str)
    market_ret = _daily_returns(market_ticker, start_str, end_str)

    if stock_ret.empty or market_ret.empty:
        return {
            "ticker": ticker,
            "filed_date": filed_date,
            "car": None,
            "window": list(window),
            "daily_abnormal": [],
        }

    stock_ret.index = stock_ret.index.tz_localize(None) if stock_ret.index.tz else stock_ret.index
    market_ret.index = market_ret.index.tz_localize(None) if market_ret.index.tz else market_ret.index

    common_idx = stock_ret.index.intersection(market_ret.index)
    stock_ret = stock_ret.loc[common_idx]
    market_ret = market_ret.loc[common_idx]

    filed_dt = pd.Timestamp(filed_date)

    # Map calendar filed_date to the nearest trading day in the index
    idx_after = common_idx[common_idx >= filed_dt]
    if idx_after.empty:
        event_idx = len(common_idx) - 1
    else:
        event_idx = common_idx.get_loc(idx_after[0])

    win_start = max(event_idx + window[0], 0)
    win_end = min(event_idx + window[1] + 1, len(common_idx))

    abnormal = (stock_ret.iloc[win_start:win_end] - market_ret.iloc[win_start:win_end])
    car = float(abnormal.sum()) if len(abnormal) > 0 else None

    return {
        "ticker": ticker,
        "filed_date": filed_date,
        "car": round(car, 6) if car is not None else None,
        "window": list(window),
        "daily_abnormal": [round(float(x), 6) for x in abnormal.values],
    }


def resolve_ticker(cik: int) -> str | None:
    """Look up ticker for a CIK using the config mapping."""
    return config.CIK_TO_TICKER.get(cik)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Compute CAR for a filing")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--filed-date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    result = compute_car(args.ticker, args.filed_date)
    print(f"CAR for {result['ticker']} around {result['filed_date']}: {result['car']}")
    print(f"  Window: {result['window']}, Daily abnormal: {result['daily_abnormal']}")


if __name__ == "__main__":
    main()
