"""Tests for abnormal_returns.py -- CAR, volume ratio, and helpers."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from tiaa.analysis.abnormal_returns import (
    _trading_days_around,
    resolve_ticker,
    compute_car,
    compute_volume_ratio,
)
from tiaa import config


class TestTradingDaysAround:
    def test_buffer_default(self):
        start, end = _trading_days_around("2024-06-15")
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        filed_dt = datetime(2024, 6, 15)
        assert start_dt < filed_dt
        assert end_dt > filed_dt
        assert (filed_dt - start_dt).days == config.CAR_BUFFER_DAYS
        assert (end_dt - filed_dt).days == config.CAR_BUFFER_DAYS

    def test_custom_buffer(self):
        start, end = _trading_days_around("2024-06-15", buffer_calendar_days=10)
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        filed_dt = datetime(2024, 6, 15)
        assert (filed_dt - start_dt).days == 10
        assert (end_dt - filed_dt).days == 10


class TestResolveTicker:
    def test_known_cik(self):
        assert resolve_ticker(320193) == "AAPL"

    def test_known_cik_jpm(self):
        assert resolve_ticker(19617) == "JPM"

    def test_unknown_cik(self):
        assert resolve_ticker(999999999) is None


class TestComputeCarMocked:
    @patch("tiaa.analysis.abnormal_returns._daily_returns")
    def test_empty_data_returns_none(self, mock_returns):
        mock_returns.return_value = pd.Series(dtype=float)
        result = compute_car("AAPL", "2024-11-01")
        assert result["car"] is None
        assert result["ticker"] == "AAPL"
        assert result["daily_abnormal"] == []

    @patch("tiaa.analysis.abnormal_returns._daily_returns")
    def test_with_data(self, mock_returns):
        dates = pd.date_range("2024-10-01", periods=60, freq="B")
        stock = pd.Series([0.01] * 60, index=dates)
        market = pd.Series([0.005] * 60, index=dates)

        mock_returns.side_effect = [stock, market]
        result = compute_car("AAPL", "2024-11-01")
        assert result["car"] is not None


class TestComputeVolumeRatioMocked:
    @patch("tiaa.analysis.abnormal_returns.yf.download")
    def test_empty_data_returns_none(self, mock_download):
        mock_download.return_value = pd.DataFrame()
        result = compute_volume_ratio("AAPL", "2024-11-01")
        assert result is None
