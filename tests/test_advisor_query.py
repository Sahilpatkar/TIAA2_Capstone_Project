"""Tests for advisor_query.py -- portfolio aggregation and narrative."""

import json

import pytest

from advisor_query import (
    aggregate_las,
    retrieve_high_impact_sections,
    _template_narrative,
)
from store import LASStore


def _seed_store(store: LASStore):
    """Insert sample filings for testing advisor queries."""
    rows = [
        {
            "cik": 320193, "accession": "acc1", "ticker": "AAPL",
            "entity_name": "Apple Inc.", "report_date": "2024-09-28",
            "change_intensity": 0.1, "attention_proxy": 1.2, "car": 0.02,
            "las": 0.4, "norm_change": 0.5, "norm_attention": 0.6, "norm_car": 0.3,
            "section_changes_json": json.dumps([
                {"section": "item_1a", "change_intensity": 0.15,
                 "snippet_old": "Old risk factors text", "snippet_new": "New risk factors text"},
                {"section": "item_7", "change_intensity": 0.08,
                 "snippet_old": "Old MD&A text", "snippet_new": "New MD&A text"},
            ]),
        },
        {
            "cik": 19617, "accession": "acc2", "ticker": "JPM",
            "entity_name": "JPMorgan Chase", "report_date": "2024-12-31",
            "change_intensity": 0.3, "attention_proxy": 0.8, "car": -0.01,
            "las": 0.6, "norm_change": 0.7, "norm_attention": 0.4, "norm_car": 0.2,
            "section_changes_json": json.dumps([
                {"section": "item_7", "change_intensity": 0.25,
                 "snippet_old": "Old JPM MD&A", "snippet_new": "New JPM MD&A"},
                {"section": "item_1", "change_intensity": 0.05,
                 "snippet_old": "Old JPM business", "snippet_new": "New JPM business"},
            ]),
        },
    ]
    store.upsert_many(rows)


class TestAggregateLas:
    def test_equal_weight(self, tmp_store):
        _seed_store(tmp_store)
        result = aggregate_las(["AAPL", "JPM"], db=tmp_store)
        assert result["portfolio_las"] is not None
        assert result["portfolio_las"] == pytest.approx((0.4 + 0.6) / 2, abs=1e-6)
        assert len(result["holdings"]) == 2

    def test_custom_weights(self, tmp_store):
        _seed_store(tmp_store)
        weights = {"AAPL": 0.7, "JPM": 0.3}
        result = aggregate_las(["AAPL", "JPM"], weights=weights, db=tmp_store)
        expected = (0.4 * 0.7 + 0.6 * 0.3) / (0.7 + 0.3)
        assert result["portfolio_las"] == pytest.approx(expected, abs=1e-6)

    def test_no_data(self, tmp_store):
        result = aggregate_las(["ZZZZ"], db=tmp_store)
        assert result["portfolio_las"] is None
        assert len(result["holdings"]) == 1
        assert result["holdings"][0]["las"] is None

    def test_mixed_data(self, tmp_store):
        _seed_store(tmp_store)
        result = aggregate_las(["AAPL", "ZZZZ"], db=tmp_store)
        assert result["portfolio_las"] is not None
        assert result["portfolio_las"] == pytest.approx(0.4, abs=1e-6)


class TestTemplateNarrative:
    def test_format(self):
        portfolio = {
            "portfolio_las": 0.5,
            "holdings": [
                {"ticker": "AAPL", "las": 0.4},
                {"ticker": "JPM", "las": 0.6},
            ],
        }
        high_impact = [
            {"ticker": "JPM", "section": "item_7", "change_intensity": 0.25, "snippet": "text"},
        ]
        result = _template_narrative(portfolio, high_impact)
        assert "Portfolio Lazy Attention Score" in result
        assert "AAPL" in result
        assert "JPM" in result


class TestRetrieveHighImpactSections:
    def test_ordering(self, tmp_store):
        _seed_store(tmp_store)
        sections = retrieve_high_impact_sections(["AAPL", "JPM"], top_n=5, db=tmp_store)
        assert len(sections) > 0
        intensities = [s.get("change_intensity") or 0 for s in sections]
        assert intensities == sorted(intensities, reverse=True)

    def test_top_n_limit(self, tmp_store):
        _seed_store(tmp_store)
        sections = retrieve_high_impact_sections(["AAPL", "JPM"], top_n=2, db=tmp_store)
        assert len(sections) <= 2

    def test_snippet_old_new_propagated(self, tmp_store):
        _seed_store(tmp_store)
        sections = retrieve_high_impact_sections(["AAPL", "JPM"], top_n=5, db=tmp_store)
        for s in sections:
            assert "snippet_new" in s
            assert "snippet_old" in s
            assert isinstance(s["snippet_new"], str) and len(s["snippet_new"]) > 0
            assert isinstance(s["snippet_old"], str) and len(s["snippet_old"]) > 0
            assert s["snippet"] == s["snippet_new"]
