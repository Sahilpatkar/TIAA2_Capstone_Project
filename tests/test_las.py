"""Tests for las.py -- LAS computation and normalization."""

import numpy as np
import pandas as pd
import pytest

import tiaa.analysis.las as las


class TestRankNormalize:
    def test_basic(self):
        s = pd.Series([10.0, 20.0, 30.0])
        result = las._rank_normalize(s)
        assert list(result) == pytest.approx([1 / 3, 2 / 3, 1.0], abs=1e-6)

    def test_ties(self):
        s = pd.Series([5.0, 5.0, 10.0])
        result = las._rank_normalize(s)
        assert result.iloc[0] == result.iloc[1]
        assert result.iloc[2] > result.iloc[0]

    def test_nan_preserved(self):
        s = pd.Series([1.0, np.nan, 3.0])
        result = las._rank_normalize(s)
        assert pd.isna(result.iloc[1])


class TestZscoreNormalize:
    def test_basic(self):
        s = pd.Series([10.0, 20.0, 30.0])
        result = las._zscore_normalize(s)
        assert result.mean() == pytest.approx(0.0, abs=1e-10)
        assert result.std() == pytest.approx(1.0, abs=0.1)

    def test_zero_std(self):
        s = pd.Series([5.0, 5.0, 5.0])
        result = las._zscore_normalize(s)
        assert (result == 0.0).all()

    def test_single_value(self):
        s = pd.Series([42.0])
        result = las._zscore_normalize(s)
        assert (result == 0.0).all()


class TestNormalize:
    def test_dispatches_rank(self):
        s = pd.Series([1.0, 2.0, 3.0])
        result = las.normalize(s, method="rank")
        expected = las._rank_normalize(s)
        pd.testing.assert_series_equal(result, expected)

    def test_dispatches_zscore(self):
        s = pd.Series([1.0, 2.0, 3.0])
        result = las.normalize(s, method="zscore")
        expected = las._zscore_normalize(s)
        pd.testing.assert_series_equal(result, expected)

    def test_unknown_method_raises(self):
        s = pd.Series([1.0])
        with pytest.raises(ValueError, match="Unknown normalization"):
            las.normalize(s, method="invalid")


class TestComputeLas:
    def test_shape_and_columns(self, sample_filings_df):
        result = las.compute_las(sample_filings_df)
        for col in ("norm_change", "norm_attention", "norm_car", "las"):
            assert col in result.columns
        assert len(result) == len(sample_filings_df)

    def test_known_values(self):
        df = pd.DataFrame({
            "change_intensity": [0.0, 0.5, 1.0],
            "attention_proxy": [0.0, 0.5, 1.0],
            "car": [0.0, 0.05, 0.10],
        })
        result = las.compute_las(df)
        assert result["las"].notna().all()
        assert len(result) == 3

    def test_with_nan(self):
        df = pd.DataFrame({
            "change_intensity": [0.3, np.nan, 0.7],
            "attention_proxy": [0.5, 0.5, np.nan],
            "car": [0.02, 0.01, 0.03],
        })
        result = las.compute_las(df)
        assert "las" in result.columns


class TestWeightedChangeIntensity:
    """Tests for las.weighted_change_intensity()."""

    def test_empty_returns_none(self):
        assert las.weighted_change_intensity([]) is None

    def test_none_returns_none(self):
        assert las.weighted_change_intensity(None) is None

    def test_basic_weighted_average(self):
        weights = {"item_7": 0.6, "item_1a": 0.4}
        sections = [
            {"section": "item_7", "change_intensity": 0.8},
            {"section": "item_1a", "change_intensity": 0.2},
        ]
        result = las.weighted_change_intensity(sections, weights=weights)
        expected = (0.6 * 0.8 + 0.4 * 0.2) / (0.6 + 0.4)
        assert result == pytest.approx(expected)

    def test_sections_not_in_weights_ignored(self):
        weights = {"item_7": 1.0}
        sections = [
            {"section": "item_7", "change_intensity": 0.5},
            {"section": "item_99", "change_intensity": 0.9},
        ]
        result = las.weighted_change_intensity(sections, weights=weights)
        assert result == pytest.approx(0.5)

    def test_none_change_intensity_skipped(self):
        weights = {"item_1": 0.5, "item_7": 0.5}
        sections = [
            {"section": "item_1", "change_intensity": None},
            {"section": "item_7", "change_intensity": 0.6},
        ]
        result = las.weighted_change_intensity(sections, weights=weights)
        assert result == pytest.approx(0.6)

    def test_all_none_change_intensity_returns_none(self):
        weights = {"item_1": 0.5, "item_7": 0.5}
        sections = [
            {"section": "item_1", "change_intensity": None},
            {"section": "item_7", "change_intensity": None},
        ]
        assert las.weighted_change_intensity(sections, weights=weights) is None

    def test_single_section(self):
        weights = {"item_7": 0.30}
        sections = [{"section": "item_7", "change_intensity": 0.42}]
        result = las.weighted_change_intensity(sections, weights=weights)
        assert result == pytest.approx(0.42)

    def test_uses_config_defaults(self):
        sections = [
            {"section": "item_7", "change_intensity": 1.0},
            {"section": "item_1a", "change_intensity": 0.0},
        ]
        result = las.weighted_change_intensity(sections)
        w7 = 0.30
        w1a = 0.25
        expected = (w7 * 1.0 + w1a * 0.0) / (w7 + w1a)
        assert result == pytest.approx(expected)

    def test_zero_weight_sections_excluded(self):
        weights = {"item_7": 0.5, "item_15": 0.0}
        sections = [
            {"section": "item_7", "change_intensity": 0.3},
            {"section": "item_15", "change_intensity": 0.9},
        ]
        result = las.weighted_change_intensity(sections, weights=weights)
        assert result == pytest.approx(0.3)


class TestComputeSectionLas:
    def test_empty(self):
        assert las.compute_section_las([]) == []

    def test_ranking(self):
        sections = [
            {"section": "item_1", "change_intensity": 0.1},
            {"section": "item_7", "change_intensity": 0.9},
            {"section": "item_1a", "change_intensity": 0.5},
        ]
        result = las.compute_section_las(sections)
        assert len(result) == 3
        las_values = [r["section_las"] for r in result]
        item7_las = next(r["section_las"] for r in result if r["section"] == "item_7")
        item1_las = next(r["section_las"] for r in result if r["section"] == "item_1")
        assert item7_las > item1_las
