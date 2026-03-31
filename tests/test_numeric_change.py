"""Tests for numeric_change.py -- financial number extraction and divergence."""

import json
import math
import os

import pytest

from numeric_change import (
    extract_financial_numbers,
    match_numbers,
    compute_numerical_divergence,
    _squash,
)


# ---------------------------------------------------------------------------
# extract_financial_numbers
# ---------------------------------------------------------------------------


class TestExtractFinancialNumbers:
    def test_dollar_billions(self):
        text = "Total net sales were $383.3 billion during 2023."
        nums = extract_financial_numbers(text)
        assert len(nums) >= 1
        dollar = [n for n in nums if n["value"] == pytest.approx(383.3e9, rel=1e-3)]
        assert len(dollar) == 1

    def test_dollar_millions(self):
        text = "R&D expense increased $1.2 million during the period."
        nums = extract_financial_numbers(text)
        dollar = [n for n in nums if n["value"] == pytest.approx(1.2e6, rel=1e-3)]
        assert len(dollar) == 1

    def test_dollar_bare(self):
        text = "The company paid $10,000 in fees."
        nums = extract_financial_numbers(text)
        dollar = [n for n in nums if n["value"] == pytest.approx(10_000, rel=1e-3)]
        assert len(dollar) == 1

    def test_percentage(self):
        text = "Gross margin was 45.2% for the fiscal year."
        nums = extract_financial_numbers(text)
        pct = [n for n in nums if n["value"] == pytest.approx(45.2, rel=1e-3)]
        assert len(pct) == 1

    def test_bare_large_number(self):
        text = "The company employed 164,000 full-time employees."
        nums = extract_financial_numbers(text)
        bare = [n for n in nums if n["value"] == pytest.approx(164_000, rel=1e-3)]
        assert len(bare) == 1

    def test_filters_years(self):
        text = "Results for fiscal year 2024 compared to 2023."
        nums = extract_financial_numbers(text)
        year_vals = [n for n in nums if n["value"] in (2024, 2023)]
        assert len(year_vals) == 0

    def test_filters_item_references(self):
        text = "See Part II, Item 8 of this Form 10-K."
        nums = extract_financial_numbers(text)
        item_refs = [n for n in nums if n["value"] == 8]
        assert len(item_refs) == 0

    def test_empty_text(self):
        assert extract_financial_numbers("") == []
        assert extract_financial_numbers("   ") == []

    def test_no_numbers(self):
        text = "The company operates in multiple international markets."
        assert extract_financial_numbers(text) == []

    def test_context_window_populated(self):
        text = "Total revenue was $5.3 billion for the full year."
        nums = extract_financial_numbers(text)
        assert len(nums) >= 1
        assert isinstance(nums[0]["context"], set)
        assert len(nums[0]["context"]) > 0
        assert "revenue" in nums[0]["context"] or "total" in nums[0]["context"]

    def test_multiple_numbers(self):
        text = (
            "Revenue was $383.3 billion and net income was $97.0 billion. "
            "Gross margin improved to 46.2% from 44.1%."
        )
        nums = extract_financial_numbers(text)
        assert len(nums) >= 4


# ---------------------------------------------------------------------------
# match_numbers
# ---------------------------------------------------------------------------


class TestMatchNumbers:
    def test_matching_by_context(self):
        text_cur = "Total revenue was $50 billion for the year."
        text_pri = "Total revenue was $5 billion for the year."
        nums_cur = extract_financial_numbers(text_cur)
        nums_pri = extract_financial_numbers(text_pri)
        pairs = match_numbers(nums_cur, nums_pri)
        assert len(pairs) == 1
        assert pairs[0][0]["value"] == pytest.approx(50e9, rel=1e-3)
        assert pairs[0][1]["value"] == pytest.approx(5e9, rel=1e-3)

    def test_no_match_empty_prior(self):
        text_cur = "Revenue was $50 billion."
        nums_cur = extract_financial_numbers(text_cur)
        pairs = match_numbers(nums_cur, [])
        assert pairs == []

    def test_no_match_empty_current(self):
        text_pri = "Revenue was $5 billion."
        nums_pri = extract_financial_numbers(text_pri)
        pairs = match_numbers([], nums_pri)
        assert pairs == []

    def test_multiple_pairs(self):
        cur = "Revenue $50 billion. Profit $10 billion."
        pri = "Revenue $40 billion. Profit $8 billion."
        nums_cur = extract_financial_numbers(cur)
        nums_pri = extract_financial_numbers(pri)
        pairs = match_numbers(nums_cur, nums_pri)
        assert len(pairs) == 2


# ---------------------------------------------------------------------------
# compute_numerical_divergence
# ---------------------------------------------------------------------------


class TestComputeNumericalDivergence:
    def test_identical_text_zero_divergence(self):
        text = "Revenue was $383.3 billion and margin was 46.2%."
        assert compute_numerical_divergence(text, text) == pytest.approx(0.0, abs=1e-6)

    def test_same_words_different_numbers_high_divergence(self):
        cur = "Revenue was $50 billion for the fiscal year."
        pri = "Revenue was $5 billion for the fiscal year."
        div = compute_numerical_divergence(cur, pri)
        assert div > 0.3, f"Expected high divergence for 10x change, got {div}"

    def test_no_numbers_zero_divergence(self):
        cur = "The company operates in technology markets."
        pri = "The company operates in consumer markets."
        assert compute_numerical_divergence(cur, pri) == 0.0

    def test_both_empty_zero_divergence(self):
        assert compute_numerical_divergence("", "") == 0.0

    def test_numbers_in_only_one_text(self):
        cur = "Revenue was $50 billion."
        pri = "The company had strong performance."
        div = compute_numerical_divergence(cur, pri)
        # Should produce moderate divergence (numbers exist but can't match)
        assert div > 0.0

    def test_small_change_low_divergence(self):
        cur = "Revenue was $385 billion for the year."
        pri = "Revenue was $383 billion for the year."
        div = compute_numerical_divergence(cur, pri)
        assert div < 0.1, f"Expected low divergence for ~0.5% change, got {div}"

    def test_symmetry(self):
        cur = "Revenue was $50 billion for the fiscal year."
        pri = "Revenue was $25 billion for the fiscal year."
        div_forward = compute_numerical_divergence(cur, pri)
        div_reverse = compute_numerical_divergence(pri, cur)
        assert div_forward == pytest.approx(div_reverse, abs=1e-6)

    def test_divergence_bounded_zero_one(self):
        cur = "Revenue was $1000 billion and costs were $999 billion."
        pri = "Revenue was $1 billion and costs were $1 billion."
        div = compute_numerical_divergence(cur, pri)
        assert 0.0 <= div <= 1.0


# ---------------------------------------------------------------------------
# squash function
# ---------------------------------------------------------------------------


class TestSquash:
    def test_zero_input(self):
        assert _squash(0.0) == pytest.approx(0.0, abs=1e-6)

    def test_positive_bounded(self):
        assert 0.0 < _squash(1.0) < 1.0

    def test_large_input_near_one(self):
        assert _squash(100.0) > 0.99

    def test_monotonic(self):
        assert _squash(0.5) < _squash(1.0) < _squash(2.0) < _squash(5.0)


# ---------------------------------------------------------------------------
# Integration: hybrid change_intensity with real-ish 10-K text
# ---------------------------------------------------------------------------


class TestHybridIntegration:
    """Verify that compute_similarity produces higher change_intensity when
    numbers differ, even if the narrative text is nearly identical."""

    @pytest.fixture()
    def entity_dir_numbers_only_change(self, tmp_path):
        """Two filings with identical narrative but different financial figures."""
        cleaned = tmp_path / "cleaned"
        cleaned.mkdir()

        base_text = (
            "Item 7. Management's Discussion and Analysis\n"
            "The Company's total net sales were {revenue} and net income was "
            "{income} during the fiscal year. The Company's gross margin was "
            "{margin}. Operating expenses totaled {opex} for the period."
        )

        filing_2023 = {
            "source_file": "0001_test-20230930.html",
            "full_text": base_text.format(
                revenue="$383.3 billion",
                income="$97.0 billion",
                margin="44.1%",
                opex="$54.8 billion",
            ),
            "sections": {
                "item_7": base_text.format(
                    revenue="$383.3 billion",
                    income="$97.0 billion",
                    margin="44.1%",
                    opex="$54.8 billion",
                ),
            },
        }
        filing_2024 = {
            "source_file": "0001_test-20240928.html",
            "full_text": base_text.format(
                revenue="$391.0 billion",
                income="$101.0 billion",
                margin="46.2%",
                opex="$56.1 billion",
            ),
            "sections": {
                "item_7": base_text.format(
                    revenue="$391.0 billion",
                    income="$101.0 billion",
                    margin="46.2%",
                    opex="$56.1 billion",
                ),
            },
        }

        (cleaned / "0001_test-20230930_cleaned.json").write_text(
            json.dumps(filing_2023)
        )
        (cleaned / "0001_test-20240928_cleaned.json").write_text(
            json.dumps(filing_2024)
        )
        return str(tmp_path)

    def test_numbers_only_change_detected(self, entity_dir_numbers_only_change):
        from similarity import compute_similarity

        results = compute_similarity(entity_dir_numbers_only_change)
        assert len(results) == 1

        r = results[0]
        assert r["numerical_divergence"] > 0.0
        assert r["change_intensity"] > 0.0

        # The text-only change would be near zero; hybrid should be higher
        text_only_ci = 1.0 - r["similarity_cosine"]
        assert r["change_intensity"] > text_only_ci, (
            f"Hybrid CI ({r['change_intensity']}) should exceed "
            f"text-only CI ({text_only_ci}) when numbers differ"
        )

    def test_section_level_numerical_divergence(self, entity_dir_numbers_only_change):
        from similarity import compute_similarity

        results = compute_similarity(entity_dir_numbers_only_change)
        sc = results[0]["section_changes"]
        item7 = [s for s in sc if s["section"] == "item_7"]
        assert len(item7) == 1
        assert item7[0]["numerical_divergence"] > 0.0
