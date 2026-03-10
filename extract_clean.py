"""
Extract and clean text from 10-K HTML filings.

Handles modern iXBRL (inline XBRL) HTML produced by SEC EDGAR.
Outputs per-filing cleaned JSON with full text and per-Item sections.

Usage:
    python extract_clean.py --entity-dir "Apple Inc._0000320193"
    python extract_clean.py --entity-dir "Apple Inc._0000320193" --file 000032019325000079_aapl-20250927.html
"""

import argparse
import json
import os
import re
import unicodedata
import warnings

from bs4 import BeautifulSoup, Comment, XMLParsedAsHTMLWarning

import config

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


# ---------------------------------------------------------------------------
# HTML cleaning helpers
# ---------------------------------------------------------------------------

def _remove_hidden_xbrl(soup: BeautifulSoup) -> None:
    """Remove the hidden iXBRL header block (display:none div at top)."""
    for div in soup.find_all("div", style=re.compile(r"display\s*:\s*none", re.I)):
        div.decompose()


def _remove_noise_tags(soup: BeautifulSoup) -> None:
    """Strip script, style, and XBRL-namespace wrapper elements."""
    for tag_name in ("script", "style", "noscript"):
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    for tag in soup.find_all(re.compile(r"^ix:", re.I)):
        tag.unwrap()


def _numeric_fraction(text: str) -> float:
    """Fraction of characters in *text* that are digits or common numeric punctuation."""
    if not text:
        return 0.0
    numeric_chars = sum(1 for c in text if c.isdigit() or c in ".,%-$():")
    return numeric_chars / len(text)


def _drop_numeric_tables(soup: BeautifulSoup, threshold: float) -> None:
    """Remove <table> elements whose text is predominantly numeric."""
    for table in soup.find_all("table"):
        txt = table.get_text(separator=" ", strip=True)
        if _numeric_fraction(txt) > threshold:
            table.decompose()


def _normalize_whitespace(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Full-document cleaning
# ---------------------------------------------------------------------------

def clean_html(html: str) -> str:
    """Return cleaned plain text from a 10-K HTML filing."""
    soup = BeautifulSoup(html, "lxml")
    _remove_hidden_xbrl(soup)
    _remove_noise_tags(soup)
    _drop_numeric_tables(soup, config.NUMERIC_TABLE_THRESHOLD)
    text = soup.get_text(separator="\n", strip=True)
    return _normalize_whitespace(text)


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

# Regex that matches "Item 1", "Item 1A", "ITEM 7A", etc. as a section heading.
# Requires the item label to appear near the start of a line (after optional whitespace)
# and be followed by punctuation, whitespace, or end-of-line.
_ITEM_PATTERN = re.compile(
    r"(?:^|\n)\s{0,4}"                      # start of line / after newline
    r"(?:PART\s+[IV]+\s*[\.\-—]?\s*)?"       # optional "PART I" prefix
    r"ITEM\s+"                               # literal "ITEM "
    r"(\d{1,2}[A-C]?)"                       # item number (capture group 1)
    r"\s*[\.\-—:\s]",                        # separator after number
    re.IGNORECASE,
)


def _canonical_section_key(raw: str) -> str:
    """Normalize '1A' -> 'item_1a'."""
    return f"item_{raw.strip().lower()}"


def extract_sections(full_text: str) -> dict[str, str]:
    """
    Split cleaned full text into sections keyed by Item label.
    Returns dict like {"item_1": "...", "item_1a": "...", "item_7": "..."}.
    Sections not found are omitted.
    """
    matches = list(_ITEM_PATTERN.finditer(full_text))
    if not matches:
        return {}

    # Deduplicate: keep the LAST occurrence for each item key (the actual
    # content heading, not the table-of-contents reference that appears earlier).
    seen: dict[str, list] = {}
    for m in matches:
        key = _canonical_section_key(m.group(1))
        if key not in seen:
            seen[key] = []
        seen[key].append(m)

    ordered_keys = list(dict.fromkeys(_canonical_section_key(m.group(1)) for m in matches))

    # For each item, take the *last* match position as the real section start
    final_positions = []
    for key in ordered_keys:
        last_match = seen[key][-1]
        final_positions.append((key, last_match.start()))

    final_positions.sort(key=lambda x: x[1])

    sections: dict[str, str] = {}
    for i, (key, start) in enumerate(final_positions):
        end = final_positions[i + 1][1] if i + 1 < len(final_positions) else len(full_text)
        section_text = full_text[start:end].strip()
        if section_text:
            sections[key] = section_text

    return sections


# ---------------------------------------------------------------------------
# Per-filing processing
# ---------------------------------------------------------------------------

def process_filing(html_path: str, output_dir: str) -> str:
    """
    Clean one HTML filing and write a JSON artifact.

    Returns the path to the written JSON file.
    """
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    full_text = clean_html(html)
    sections = extract_sections(full_text)

    basename = os.path.splitext(os.path.basename(html_path))[0]
    out_path = os.path.join(output_dir, f"{basename}_cleaned.json")

    payload = {
        "source_file": os.path.basename(html_path),
        "full_text": full_text,
        "sections": sections,
    }

    os.makedirs(output_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return out_path


def process_entity_dir(entity_dir: str, specific_file: str | None = None) -> list[str]:
    """
    Process all HTML filings (or a specific one) under an entity directory.
    Returns list of output JSON paths.
    """
    cleaned_dir = os.path.join(entity_dir, "cleaned")
    html_files = []

    if specific_file:
        html_files.append(os.path.join(entity_dir, specific_file))
    else:
        for fname in sorted(os.listdir(entity_dir)):
            if fname.endswith(".html"):
                html_files.append(os.path.join(entity_dir, fname))

    results = []
    for html_path in html_files:
        out = process_filing(html_path, cleaned_dir)
        print(f"  Cleaned: {html_path} -> {out}")
        results.append(out)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Extract and clean 10-K text")
    parser.add_argument("--entity-dir", required=True, help="Path to entityName_cik folder")
    parser.add_argument("--file", default=None, help="Process a single HTML file within the dir")
    args = parser.parse_args()

    paths = process_entity_dir(args.entity_dir, specific_file=args.file)
    print(f"Processed {len(paths)} filing(s).")


if __name__ == "__main__":
    main()
