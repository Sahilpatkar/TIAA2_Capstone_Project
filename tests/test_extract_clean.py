"""Tests for extract_clean.py -- HTML cleaning and section extraction."""

import json
import os

import pytest

from extract_clean import (
    _numeric_fraction,
    _normalize_whitespace,
    _canonical_section_key,
    extract_sections,
    clean_html,
    process_filing,
)


class TestNumericFraction:
    def test_all_digits(self):
        assert _numeric_fraction("12345") == 1.0

    def test_all_alpha(self):
        assert _numeric_fraction("abcdef") == 0.0

    def test_mixed(self):
        result = _numeric_fraction("abc123")
        assert 0.4 < result < 0.6

    def test_empty(self):
        assert _numeric_fraction("") == 0.0


class TestNormalizeWhitespace:
    def test_collapses_spaces(self):
        assert _normalize_whitespace("hello    world") == "hello world"

    def test_collapses_newlines(self):
        result = _normalize_whitespace("a\n\n\n\n\nb")
        assert result == "a\n\nb"

    def test_strips(self):
        assert _normalize_whitespace("  hello  ") == "hello"


class TestCanonicalSectionKey:
    def test_lowercase(self):
        assert _canonical_section_key("1A") == "item_1a"

    def test_plain_number(self):
        assert _canonical_section_key("7") == "item_7"

    def test_with_whitespace(self):
        assert _canonical_section_key(" 9B ") == "item_9b"


class TestExtractSections:
    def test_simple(self):
        text = (
            "ITEM 1. Business\n"
            "This is the business section content.\n\n"
            "ITEM 7. MD&A\n"
            "Management discussion and analysis here."
        )
        sections = extract_sections(text)
        assert "item_1" in sections
        assert "item_7" in sections
        assert "business" in sections["item_1"].lower()

    def test_no_items(self):
        text = "Just some random text with no item markers."
        assert extract_sections(text) == {}

    def test_case_insensitive(self):
        text = "item 1a. Risk Factors\nRisk content here.\n\nitem 7. Discussion\nMD&A."
        sections = extract_sections(text)
        assert "item_1a" in sections


class TestCleanHtml:
    def test_removes_script(self):
        html = "<html><body><script>alert('x')</script><p>Hello</p></body></html>"
        result = clean_html(html)
        assert "alert" not in result
        assert "Hello" in result

    def test_removes_hidden_xbrl(self):
        html = '<html><body><div style="display:none">Hidden XBRL</div><p>Visible</p></body></html>'
        result = clean_html(html)
        assert "Hidden XBRL" not in result
        assert "Visible" in result

    def test_preserves_text(self):
        html = "<html><body><p>Important filing text</p></body></html>"
        result = clean_html(html)
        assert "Important filing text" in result


class TestProcessFiling:
    def test_writes_json(self, tmp_path):
        html_path = tmp_path / "test_filing.html"
        html_path.write_text(
            "<html><body>"
            "<p>ITEM 1. Business</p>"
            "<p>Company does things.</p>"
            "<p>ITEM 7. MD&A</p>"
            "<p>Financial discussion.</p>"
            "</body></html>"
        )
        output_dir = str(tmp_path / "cleaned")
        result_path = process_filing(str(html_path), output_dir)

        assert os.path.exists(result_path)
        assert result_path.endswith("_cleaned.json")

        with open(result_path) as f:
            data = json.load(f)
        assert "full_text" in data
        assert "sections" in data
        assert data["source_file"] == "test_filing.html"
