"""
Compute cumulative abnormal returns (CAR) around 10-K filing dates.

Uses Yahoo Finance for daily price data and a simple market-adjusted
model (stock return minus S&P 500 return) over a configurable event window.

Usage:
    python abnormal_returns.py --ticker AAPL --filed-date 2024-11-01
"""

import argparse
import contextlib
import io
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

import config


def _yf_download_with_retry(ticker: str, start: str, end: str, max_retries: int = 3) -> pd.DataFrame:
    """yf.download wrapper with retries + backoff to survive transient rate limits."""
    for attempt in range(max_retries):
        with contextlib.redirect_stderr(io.StringIO()):
            data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if not data.empty:
            return data
        if attempt < max_retries - 1:
            time.sleep(1.5 * (attempt + 1))
    return data


def _trading_days_around(filed_date: str, buffer_calendar_days: int = None) -> tuple[str, str]:
    """Return (start, end) date strings with enough buffer to cover the event window."""
    buf = buffer_calendar_days or config.CAR_BUFFER_DAYS
    dt = datetime.strptime(filed_date, "%Y-%m-%d")
    start = dt - timedelta(days=buf)
    end = dt + timedelta(days=buf)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _daily_returns(ticker: str, start: str, end: str) -> pd.Series:
    """Fetch adjusted close prices from Yahoo Finance and compute daily returns."""
    data = _yf_download_with_retry(ticker, start, end)
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


def compute_volume_ratio(
    ticker: str,
    filed_date: str,
    window: tuple[int, int] | None = None,
    baseline_days: int | None = None,
    baseline_gap: int | None = None,
) -> float | None:
    """
    Abnormal trading-volume ratio around *filed_date*.

    Returns event-window mean volume divided by trailing baseline mean volume.
    A value > 1 signals above-normal investor attention; < 1 signals inattention.
    Returns None when data is insufficient.
    """
    window = window or config.CAR_WINDOW
    baseline_days = baseline_days or config.VOLUME_BASELINE_DAYS
    baseline_gap = baseline_gap or config.VOLUME_BASELINE_GAP

    buf = max(config.CAR_BUFFER_DAYS, baseline_days + baseline_gap + 30)
    dt = datetime.strptime(filed_date, "%Y-%m-%d")
    start_str = (dt - timedelta(days=buf)).strftime("%Y-%m-%d")
    end_str = (dt + timedelta(days=config.CAR_BUFFER_DAYS)).strftime("%Y-%m-%d")

    data = _yf_download_with_retry(ticker, start_str, end_str)
    if data.empty or "Volume" not in data.columns:
        return None

    volume = data["Volume"].squeeze()
    if isinstance(volume, pd.DataFrame):
        volume = volume.iloc[:, 0]

    idx = volume.index
    idx = idx.tz_localize(None) if idx.tz else idx
    volume.index = idx

    filed_dt = pd.Timestamp(filed_date)

    idx_after = idx[idx >= filed_dt]
    if idx_after.empty:
        return None
    event_idx = idx.get_loc(idx_after[0])

    win_start = max(event_idx + window[0], 0)
    win_end = min(event_idx + window[1] + 1, len(idx))
    event_vol = volume.iloc[win_start:win_end]
    if event_vol.empty:
        return None

    baseline_end = max(event_idx + window[0] - baseline_gap, 0)
    baseline_start = max(baseline_end - baseline_days, 0)
    baseline_vol = volume.iloc[baseline_start:baseline_end]
    if baseline_vol.empty:
        return None

    baseline_mean = float(baseline_vol.mean())
    if baseline_mean == 0 or np.isnan(baseline_mean):
        return None

    ratio = float(event_vol.mean()) / baseline_mean
    return round(ratio, 6)


def resolve_ticker(cik: int) -> str | None:
    """Look up ticker for a CIK using the full (unfiltered) config mapping."""
    full = getattr(config, "_CIK_TO_TICKER_FULL", config.CIK_TO_TICKER)
    return full.get(cik)



# CLI


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
