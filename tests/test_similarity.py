"""Tests for similarity.py -- filing pairing and similarity measures.

Uses actual excerpts from Apple Inc. 10-K filings (FY2023 and FY2024) for
realistic similarity computation.
"""

import json
import os
from datetime import datetime

import numpy as np
import pytest
from scipy import sparse

from similarity import (
    _report_date_from_basename,
    _parse_date,
    pair_filings,
    cosine_sim,
    jaccard_sim,
    compute_similarity,
)


# ---------------------------------------------------------------------------
# Real 10-K excerpts from Apple Inc. (trimmed for test portability)
# ---------------------------------------------------------------------------

# Item 1A  Risk Factors -- nearly identical boilerplate across years
AAPL_2024_ITEM_1A = (
    "Item 1A. Risk Factors\n"
    "The Company\u2019s business, reputation, results of operations, financial "
    "condition and stock price can be affected by a number of factors, whether "
    "currently known or unknown, including those described below. When any one "
    "or more of these risks materialize from time to time, the Company\u2019s "
    "business, reputation, results of operations, financial condition and stock "
    "price can be materially and adversely affected.\n"
    "Macroeconomic and Industry Risks\n"
    "The Company\u2019s operations and performance depend significantly on "
    "global and regional economic conditions and adverse economic conditions "
    "can materially adversely affect the Company\u2019s business, results of "
    "operations and financial condition.\n"
    "The Company has international operations with sales outside the U.S. "
    "representing a majority of the Company\u2019s total net sales. In addition, "
    "the Company\u2019s global supply chain is large and complex and a majority "
    "of the Company\u2019s supplier facilities, including manufacturing and "
    "assembly sites, are located outside the U.S."
)

AAPL_2023_ITEM_1A = (
    "Item 1A. Risk Factors\n"
    "The Company\u2019s business, reputation, results of operations, financial "
    "condition and stock price can be affected by a number of factors, whether "
    "currently known or unknown, including those described below. When any one "
    "or more of these risks materialize from time to time, the Company\u2019s "
    "business, reputation, results of operations, financial condition and stock "
    "price can be materially and adversely affected.\n"
    "Macroeconomic and Industry Risks\n"
    "The Company\u2019s operations and performance depend significantly on "
    "global and regional economic conditions and adverse economic conditions "
    "can materially adversely affect the Company\u2019s business, results of "
    "operations and financial condition.\n"
    "The Company has international operations with sales outside the U.S. "
    "representing a majority of the Company\u2019s total net sales. In addition, "
    "the Company\u2019s global supply chain is large and complex and a majority "
    "of the Company\u2019s supplier facilities, including manufacturing and "
    "assembly sites, are located outside the U.S."
)

# Item 7  MD&A -- distinctly different product launches between years
AAPL_2024_ITEM_7 = (
    "Item 7. Management\u2019s Discussion and Analysis of Financial Condition "
    "and Results of Operations\n"
    "Third Quarter 2024:\n"
    "iPad Air;\niPad Pro;\n"
    "iOS 18, macOS Sequoia, iPadOS 18, watchOS 11, visionOS 2 and tvOS 18, "
    "updates to the Company\u2019s operating systems; and\n"
    "Apple Intelligence, a personal intelligence system that uses generative models.\n"
    "Fourth Quarter 2024:\n"
    "iPhone 16, iPhone 16 Plus, iPhone 16 Pro and iPhone 16 Pro Max;\n"
    "Apple Watch Series 10; and\nAirPods 4.\n"
    "The Company\u2019s fiscal year is the 52- or 53-week period that ends on "
    "the last Saturday of September. The Company\u2019s fiscal years 2024 and "
    "2022 spanned 52 weeks each, whereas fiscal year 2023 spanned 53 weeks.\n"
    "Macroeconomic conditions, including inflation, interest rates and currency "
    "fluctuations, have directly and indirectly impacted, and could in the future "
    "materially impact, the Company\u2019s results of operations."
)

AAPL_2023_ITEM_7 = (
    "Item 7. Management\u2019s Discussion and Analysis of Financial Condition "
    "and Results of Operations\n"
    "Fiscal Year Highlights\n"
    "The Company\u2019s total net sales were $383.3 billion and net income was "
    "$97.0 billion during 2023.\n"
    "The Company\u2019s total net sales decreased 3% or $11.0 billion during "
    "2023 compared to 2022. The weakness in foreign currencies relative to the "
    "U.S. dollar accounted for more than the entire year-over-year decrease in "
    "total net sales, which consisted primarily of lower net sales of Mac and "
    "iPhone, partially offset by higher net sales of Services.\n"
    "First Quarter 2023:\niPad and iPad Pro;\n"
    "Next-generation Apple TV 4K; and\n"
    "MLS Season Pass, a Major League Soccer subscription streaming service.\n"
    "Second Quarter 2023:\nMacBook Pro 14\u201d, MacBook Pro 16\u201d and Mac mini; and\n"
    "Second-generation HomePod.\n"
    "Third Quarter 2023:\n"
    "MacBook Air 15\u201d;\n15-in. MacBook Air;\n"
    "Mac Studio and Mac Pro;\nApple Vision Pro."
)


# ---------------------------------------------------------------------------
# Date extraction helpers
# ---------------------------------------------------------------------------


class TestReportDateFromBasename:
    def test_aapl_2024(self):
        bn = "000032019324000123_aapl-20240928"
        assert _report_date_from_basename(bn) == "2024-09-28"

    def test_aapl_2023(self):
        bn = "000032019323000106_aapl-20230930"
        assert _report_date_from_basename(bn) == "2023-09-30"

    def test_aapl_2025(self):
        bn = "000032019325000079_aapl-20250927"
        assert _report_date_from_basename(bn) == "2025-09-27"

    def test_ko_2022(self):
        bn = "000078901223000001_ko-20221231"
        assert _report_date_from_basename(bn) == "2022-12-31"

    def test_fy_style_end_of_string(self):
        bn = "000100103914000228_fy2014"
        assert _report_date_from_basename(bn) == "2014-09-30"

    def test_fy_style_no_boundary(self):
        bn = "000100103914000228_fy2014_q4x10k"
        assert _report_date_from_basename(bn) is None

    def test_unknown_format(self):
        assert _report_date_from_basename("random_filing_name") is None


class TestParseDate:
    def test_valid(self):
        assert _parse_date("2024-09-28") == datetime(2024, 9, 28)

    def test_invalid(self):
        assert _parse_date("not-a-date") is None

    def test_none(self):
        assert _parse_date(None) is None


# ---------------------------------------------------------------------------
# Pairing with real Apple basenames
# ---------------------------------------------------------------------------


class TestPairFilings:
    def _aapl_filing(self, basename, full_text, sections):
        return {"_basename": basename, "full_text": full_text, "sections": sections}

    def test_pair_two_apple_filings(self):
        filings = [
            self._aapl_filing(
                "000032019323000106_aapl-20230930",
                AAPL_2023_ITEM_7, {"item_7": AAPL_2023_ITEM_7},
            ),
            self._aapl_filing(
                "000032019324000123_aapl-20240928",
                AAPL_2024_ITEM_7, {"item_7": AAPL_2024_ITEM_7},
            ),
        ]
        pairs = pair_filings(filings)
        assert len(pairs) == 1
        current, prior = pairs[0]
        assert current["_report_date"] == "2024-09-28"
        assert prior["_report_date"] == "2023-09-30"

    def test_gap_too_small(self):
        filings = [
            self._aapl_filing("0001_test-20240101", "a", {}),
            self._aapl_filing("0001_test-20240301", "b", {}),
        ]
        assert pair_filings(filings) == []

    def test_gap_too_large(self):
        filings = [
            self._aapl_filing("0001_test-20220101", "a", {}),
            self._aapl_filing("0001_test-20240101", "b", {}),
        ]
        assert pair_filings(filings) == []

    def test_single_filing(self):
        filings = [self._aapl_filing("0001_test-20230930", "a", {})]
        assert pair_filings(filings) == []

    def test_three_consecutive_filings(self):
        filings = [
            self._aapl_filing("0001_test-20220930", "a", {}),
            self._aapl_filing("0001_test-20230930", "b", {}),
            self._aapl_filing("0001_test-20240928", "c", {}),
        ]
        pairs = pair_filings(filings)
        assert len(pairs) == 2

    def test_fallback_no_dates(self):
        filings = [
            {"_basename": "alpha_filing", "full_text": "a", "sections": {}},
            {"_basename": "beta_filing", "full_text": "b", "sections": {}},
        ]
        assert len(pair_filings(filings)) == 1


# ---------------------------------------------------------------------------
# Cosine similarity with real TF vectors
# ---------------------------------------------------------------------------


class TestCosineSim:
    def test_identical_vectors(self):
        v = sparse.csr_matrix([[1.0, 2.0, 3.0]])
        assert cosine_sim(v, v) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        v1 = sparse.csr_matrix([[1.0, 0.0]])
        v2 = sparse.csr_matrix([[0.0, 1.0]])
        assert cosine_sim(v1, v2) == pytest.approx(0.0, abs=1e-6)

    def test_similar_vectors(self):
        v1 = sparse.csr_matrix([[1.0, 2.0, 3.0, 0.5]])
        v2 = sparse.csr_matrix([[1.1, 2.0, 2.9, 0.6]])
        sim = cosine_sim(v1, v2)
        assert 0.99 < sim <= 1.0


# ---------------------------------------------------------------------------
# Jaccard similarity on real 10-K excerpts
# ---------------------------------------------------------------------------


class TestJaccardSim:
    def test_identical_10k_text(self):
        """Same text => similarity 1.0."""
        assert jaccard_sim(AAPL_2024_ITEM_1A, AAPL_2024_ITEM_1A) == pytest.approx(1.0, abs=1e-6)

    def test_near_identical_risk_factors(self):
        """Item 1A boilerplate is nearly the same year over year => high Jaccard."""
        sim = jaccard_sim(AAPL_2024_ITEM_1A, AAPL_2023_ITEM_1A)
        assert sim > 0.90, f"Expected high similarity for boilerplate risk factors, got {sim}"

    def test_different_mdna_sections(self):
        """Item 7 MD&A differs significantly between 2023 and 2024 product launches."""
        sim = jaccard_sim(AAPL_2024_ITEM_7, AAPL_2023_ITEM_7)
        assert 0.10 < sim < 0.85, f"Expected moderate similarity for MD&A, got {sim}"

    def test_cross_section_low_similarity(self):
        """Risk Factors vs MD&A should have lower overlap than same-section comparisons."""
        cross_sim = jaccard_sim(AAPL_2024_ITEM_1A, AAPL_2024_ITEM_7)
        same_sim = jaccard_sim(AAPL_2024_ITEM_1A, AAPL_2023_ITEM_1A)
        assert cross_sim < same_sim

    def test_disjoint_text(self):
        t1 = "xylophone zebra quilt"
        t2 = "algorithm binary cipher"
        assert jaccard_sim(t1, t2) == pytest.approx(0.0, abs=1e-6)

    def test_both_empty(self):
        assert jaccard_sim("", "") == 1.0


# ---------------------------------------------------------------------------
# End-to-end compute_similarity with real 10-K structure on disk
# ---------------------------------------------------------------------------


class TestComputeSimilarityIntegration:
    """Write two Apple-style cleaned JSONs into a temp dir and run
    the full compute_similarity pipeline (vectorise -> pair -> score)."""

    @pytest.fixture()
    def apple_entity_dir(self, tmp_path):
        cleaned = tmp_path / "cleaned"
        cleaned.mkdir()

        filing_2023 = {
            "source_file": "000032019323000106_aapl-20230930.html",
            "full_text": AAPL_2023_ITEM_1A + "\n\n" + AAPL_2023_ITEM_7,
            "sections": {
                "item_1a": AAPL_2023_ITEM_1A,
                "item_7": AAPL_2023_ITEM_7,
            },
        }
        filing_2024 = {
            "source_file": "000032019324000123_aapl-20240928.html",
            "full_text": AAPL_2024_ITEM_1A + "\n\n" + AAPL_2024_ITEM_7,
            "sections": {
                "item_1a": AAPL_2024_ITEM_1A,
                "item_7": AAPL_2024_ITEM_7,
            },
        }

        (cleaned / "000032019323000106_aapl-20230930_cleaned.json").write_text(
            json.dumps(filing_2023, ensure_ascii=False)
        )
        (cleaned / "000032019324000123_aapl-20240928_cleaned.json").write_text(
            json.dumps(filing_2024, ensure_ascii=False)
        )
        return str(tmp_path)

    def test_produces_one_pair(self, apple_entity_dir):
        results = compute_similarity(apple_entity_dir)
        assert len(results) == 1

    def test_result_structure(self, apple_entity_dir):
        results = compute_similarity(apple_entity_dir)
        r = results[0]
        assert r["current_report_date"] == "2024-09-28"
        assert r["prior_report_date"] == "2023-09-30"
        assert r["similarity_cosine"] is not None
        assert r["similarity_jaccard"] is not None
        assert r["change_intensity"] is not None
        assert 0.0 <= r["similarity_cosine"] <= 1.0
        assert 0.0 <= r["similarity_jaccard"] <= 1.0
        assert 0.0 <= r["change_intensity"] <= 1.0

    def test_section_level_changes(self, apple_entity_dir):
        results = compute_similarity(apple_entity_dir)
        section_changes = results[0]["section_changes"]
        section_keys = [sc["section"] for sc in section_changes]
        assert "item_1a" in section_keys
        assert "item_7" in section_keys

        for sc in section_changes:
            assert sc["change_intensity"] is not None
            assert 0.0 <= sc["change_intensity"] <= 1.0
            assert isinstance(sc["snippet_old"], str) and len(sc["snippet_old"]) > 0
            assert isinstance(sc["snippet_new"], str) and len(sc["snippet_new"]) > 0
            assert len(sc["snippet_old"]) <= 503  # 500 + "..."
            assert len(sc["snippet_new"]) <= 503

    def test_item7_changes_more_than_item1a(self, apple_entity_dir):
        """MD&A (product launches) should change more than boilerplate risk factors."""
        results = compute_similarity(apple_entity_dir)
        sc_map = {sc["section"]: sc for sc in results[0]["section_changes"]}
        assert sc_map["item_7"]["change_intensity"] > sc_map["item_1a"]["change_intensity"]

    def test_single_filing_returns_empty(self, tmp_path):
        cleaned = tmp_path / "cleaned"
        cleaned.mkdir()
        data = {
            "source_file": "single.html",
            "full_text": "Only one filing here.",
            "sections": {"item_1": "Business."},
        }
        (cleaned / "0001_test-20240928_cleaned.json").write_text(json.dumps(data))
        assert compute_similarity(str(tmp_path)) == []
