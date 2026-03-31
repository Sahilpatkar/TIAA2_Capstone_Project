"""Shared fixtures for the LazyPrices test suite."""

import json
import os
import tempfile

import pandas as pd
import pytest

import config
from store import LASStore


@pytest.fixture()
def tmp_dir(tmp_path):
    """Return a temporary directory path (pytest built-in wrapper)."""
    return str(tmp_path)


@pytest.fixture()
def tmp_sqlite_url(tmp_path):
    """Return a sqlite:/// URL pointing at a temp file."""
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture()
def tmp_store(tmp_sqlite_url):
    """Yield a LASStore backed by a throwaway SQLite database."""
    store = LASStore(db_url=tmp_sqlite_url)
    yield store
    store.close()


@pytest.fixture()
def sample_filings_df():
    """Small DataFrame suitable for LAS computation tests."""
    return pd.DataFrame({
        "accession": ["filing_a", "filing_b", "filing_c"],
        "ticker": ["AAPL", "JPM", "KO"],
        "change_intensity": [0.3, 0.7, 0.5],
        "attention_proxy": [0.5, 0.2, 0.8],
        "car": [0.02, -0.05, 0.01],
    })


@pytest.fixture()
def sample_cleaned_json(tmp_path):
    """Write a minimal cleaned-filing JSON and return its path."""
    data = {
        "source_file": "test_filing.html",
        "full_text": "Item 1 Business description here.\n\nItem 7 MD&A discussion.",
        "sections": {
            "item_1": "Business description here.",
            "item_7": "MD&A discussion about financial results.",
        },
    }
    path = tmp_path / "test_filing_cleaned.json"
    with open(path, "w") as f:
        json.dump(data, f)
    return str(path)


@pytest.fixture()
def sample_filing_row():
    """A single filing dict suitable for store.upsert()."""
    return {
        "cik": 320193,
        "entity_name": "Apple Inc.",
        "accession": "000032019325000079",
        "filed_date": "2024-11-01",
        "report_date": "2024-09-28",
        "ticker": "AAPL",
        "similarity_cosine": 0.95,
        "similarity_jaccard": 0.88,
        "change_intensity": 0.05,
        "attention_proxy": 1.2,
        "car": 0.015,
        "las": 0.42,
        "norm_change": 0.5,
        "norm_attention": 0.6,
        "norm_car": 0.3,
        "section_changes_json": json.dumps([
            {"section": "item_1a", "change_intensity": 0.12},
            {"section": "item_7", "change_intensity": 0.08},
        ]),
        "cleaned_text_path": "/tmp/fake_cleaned.json",
    }
