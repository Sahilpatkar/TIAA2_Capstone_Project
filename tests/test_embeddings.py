"""Tests for embeddings.py -- tokenization and vector building."""

import json
import os

import pytest

from embeddings import (
    tokenize_and_lemmatize,
    load_cleaned_filings,
    build_vectors,
)


class TestTokenizeAndLemmatize:
    def test_basic(self):
        result = tokenize_and_lemmatize("The COMPANY reported earnings")
        assert result == result.lower()
        assert "a" not in result.split()  # single-char tokens removed

    def test_stopwords_filtered(self):
        result = tokenize_and_lemmatize("the and or but not", remove_stopwords=True)
        assert result.strip() == ""

    def test_no_stopwords_flag(self):
        result = tokenize_and_lemmatize("the company is big", remove_stopwords=False)
        tokens = result.split()
        assert len(tokens) > 2

    def test_lemmatization(self):
        result = tokenize_and_lemmatize("running companies", remove_stopwords=False)
        assert "run" in result or "running" in result

    def test_empty_string(self):
        assert tokenize_and_lemmatize("") == ""


class TestLoadCleanedFilings:
    def test_empty_dir(self, tmp_path):
        cleaned_dir = tmp_path / "cleaned"
        cleaned_dir.mkdir()
        result = load_cleaned_filings(str(tmp_path))
        assert result == []

    def test_no_dir(self, tmp_path):
        result = load_cleaned_filings(str(tmp_path / "nonexistent"))
        assert result == []

    def test_loads_json(self, tmp_path):
        cleaned_dir = tmp_path / "cleaned"
        cleaned_dir.mkdir()
        data = {
            "full_text": "Some filing text here",
            "sections": {"item_1": "Business section"},
        }
        (cleaned_dir / "test_filing_cleaned.json").write_text(json.dumps(data))
        result = load_cleaned_filings(str(tmp_path))
        assert len(result) == 1
        assert result[0]["full_text"] == "Some filing text here"
        assert "_basename" in result[0]


class TestBuildVectors:
    def test_shape(self, tmp_path):
        cleaned_dir = tmp_path / "cleaned"
        cleaned_dir.mkdir()
        for i, text in enumerate(["company earnings report", "stock market analysis report"]):
            data = {"full_text": text, "sections": {"item_1": text}}
            (cleaned_dir / f"filing_{i}_cleaned.json").write_text(json.dumps(data))

        result = build_vectors(str(tmp_path), use_tfidf=False, remove_stopwords=True)
        assert "doc_vectors" in result
        assert "section_vectors" in result
        assert "vocab" in result
        assert len(result["doc_vectors"]) == 2

    def test_raises_on_empty(self, tmp_path):
        cleaned_dir = tmp_path / "cleaned"
        cleaned_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            build_vectors(str(tmp_path))
