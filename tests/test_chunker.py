"""Tests for rag/chunker.py -- text chunking for RAG."""

import json

import pytest

from rag.chunker import _hard_split, _sub_chunk, chunk_filing


class TestHardSplit:
    def test_basic(self):
        text = "a" * 100
        chunks = _hard_split(text, max_chars=30, overlap=10)
        assert len(chunks) >= 3
        assert all(len(c) <= 30 for c in chunks)

    def test_short_text(self):
        text = "short"
        chunks = _hard_split(text, max_chars=100, overlap=10)
        assert chunks == ["short"]

    def test_overlap(self):
        text = "a" * 50
        chunks = _hard_split(text, max_chars=20, overlap=5)
        if len(chunks) >= 2:
            assert chunks[0][-5:] == chunks[1][:5]


class TestSubChunk:
    def test_short_text(self):
        text = "This is a short paragraph."
        chunks = _sub_chunk(text, max_chars=1000, overlap=100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_splits(self):
        paragraphs = [f"Paragraph {i}. " + "x" * 50 for i in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = _sub_chunk(text, max_chars=200, overlap=50)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 250  # allow slight overshoot from paragraph joining

    def test_empty(self):
        chunks = _sub_chunk("", max_chars=100, overlap=10)
        assert chunks == [] or chunks == [""]


class TestChunkFiling:
    def test_with_sections(self, sample_cleaned_json):
        chunks = chunk_filing(
            sample_cleaned_json,
            ticker="AAPL",
            cik="320193",
            accession="acc1",
            report_date="2024-09-28",
        )
        assert len(chunks) >= 1
        for chunk in chunks:
            assert "id" in chunk
            assert "text" in chunk
            assert "metadata" in chunk
            assert chunk["metadata"]["ticker"] == "AAPL"
            assert chunk["metadata"]["cik"] == "320193"

    def test_no_sections_uses_full_text(self, tmp_path):
        data = {
            "source_file": "test.html",
            "full_text": "Full document text without item sections.",
            "sections": {},
        }
        path = tmp_path / "nosec_cleaned.json"
        path.write_text(json.dumps(data))

        chunks = chunk_filing(str(path), ticker="TEST")
        assert len(chunks) >= 1
        assert "full_document" in chunks[0]["metadata"].get("section_key", "")

    def test_metadata_keys(self, sample_cleaned_json):
        chunks = chunk_filing(
            sample_cleaned_json,
            ticker="AAPL",
            cik="320193",
            accession="000032019325000079",
            report_date="2024-09-28",
        )
        expected_keys = {
            "ticker", "cik", "accession", "report_date",
            "section_key", "section_label", "chunk_index", "source_file",
        }
        for chunk in chunks:
            assert expected_keys.issubset(chunk["metadata"].keys())
