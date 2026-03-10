"""
Section-aware text chunker for 10-K filings.

Uses the existing cleaned JSON sections as primary chunks.
Sections exceeding RAG_CHUNK_MAX_CHARS are sub-chunked with overlap.
"""

from __future__ import annotations

import json
import os
import re
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import config  # noqa: E402

SECTION_LABELS = {
    "item_1": "Business",
    "item_1a": "Risk Factors",
    "item_1b": "Unresolved Staff Comments",
    "item_1c": "Cybersecurity",
    "item_2": "Properties",
    "item_3": "Legal Proceedings",
    "item_4": "Mine Safety Disclosures",
    "item_5": "Market for Registrant's Common Equity",
    "item_6": "Reserved",
    "item_7": "MD&A",
    "item_7a": "Market Risk Disclosures",
    "item_8": "Financial Statements",
    "item_9": "Disagreements with Accountants",
    "item_9a": "Controls and Procedures",
    "item_9b": "Other Information",
    "item_9c": "Foreign Jurisdictions Disclosure",
    "item_10": "Directors and Corporate Governance",
    "item_11": "Executive Compensation",
    "item_12": "Security Ownership",
    "item_13": "Related Transactions",
    "item_14": "Accountant Fees",
    "item_15": "Exhibits and Financial Schedules",
    "item_16": "Form 10-K Summary",
}


def _hard_split(text: str, max_chars: int, overlap: int) -> list[str]:
    """Character-level split as a last resort for text with no paragraph breaks."""
    step = max(max_chars - overlap, 1)
    return [text[i : i + max_chars] for i in range(0, len(text), step)]


def _sub_chunk(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(para) > max_chars:
            if current.strip():
                chunks.append(current.strip())
                current = ""
            chunks.extend(_hard_split(para, max_chars, overlap))
            continue

        candidate = (current + "\n\n" + para).strip() if current else para.strip()
        if len(candidate) > max_chars and current:
            chunks.append(current.strip())
            overlap_text = current[-overlap:] if overlap and len(current) > overlap else ""
            current = (overlap_text + "\n\n" + para).strip()
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    if not chunks:
        chunks = _hard_split(text, max_chars, overlap)

    return chunks


def chunk_filing(
    cleaned_json_path: str,
    ticker: str = "",
    cik: int | str = "",
    accession: str = "",
    report_date: str = "",
) -> list[dict]:
    """
    Chunk a cleaned filing JSON into embedding-ready pieces.

    Returns list of dicts with keys: id, text, metadata.
    """
    with open(cleaned_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sections: dict[str, str] = data.get("sections", {})
    if not sections:
        full_text = data.get("full_text", "")
        if full_text:
            sections = {"full_document": full_text}

    max_chars = getattr(config, "RAG_CHUNK_MAX_CHARS", 3000)
    overlap = getattr(config, "RAG_CHUNK_OVERLAP", 200)

    basename = os.path.splitext(os.path.basename(cleaned_json_path))[0]
    chunks: list[dict] = []

    for section_key, section_text in sections.items():
        if not section_text or not section_text.strip():
            continue

        sub_chunks = _sub_chunk(section_text, max_chars, overlap)

        for idx, chunk_text in enumerate(sub_chunks):
            if not chunk_text.strip():
                continue

            label = SECTION_LABELS.get(section_key, section_key)
            chunk_id = f"{basename}__{section_key}__{idx}"

            chunks.append({
                "id": chunk_id,
                "text": chunk_text.strip(),
                "metadata": {
                    "ticker": str(ticker),
                    "cik": str(cik),
                    "accession": str(accession),
                    "report_date": str(report_date),
                    "section_key": section_key,
                    "section_label": label,
                    "chunk_index": idx,
                    "source_file": os.path.basename(cleaned_json_path),
                },
            })

    return chunks
