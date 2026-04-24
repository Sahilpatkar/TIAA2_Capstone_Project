"""Tests for config.py -- configuration consistency checks."""

import os

from tiaa import config


class TestCikTickerMapping:
    def test_bijectivity(self):
        for cik, ticker in config.CIK_TO_TICKER.items():
            assert config.TICKER_TO_CIK[ticker] == cik

    def test_all_tickers_have_sector(self):
        for ticker in config.CIK_TO_TICKER.values():
            assert ticker in config.TICKER_SECTOR_INDUSTRY, (
                f"{ticker} missing from TICKER_SECTOR_INDUSTRY"
            )


class TestLasWeights:
    def test_weights_sum_to_one(self):
        w = config.LAS_WEIGHTS
        total = w["w_change"] + w["w_attention"] + w["w_car"]
        assert abs(total - 1.0) < 1e-9


class TestPaths:
    def test_project_root_exists(self):
        assert os.path.isdir(config.PROJECT_ROOT)

    def test_data_dir_under_root(self):
        assert config.DATA_DIR.startswith(config.PROJECT_ROOT)
