"""
Index cleaned 10-K filings into the vector store for RAG retrieval.

Usage:
    python -m rag.index                     # index all filings in the DB
    python -m rag.index --ticker AAPL       # index filings for one ticker
    python -m rag.index --reindex           # force re-index everything
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import config  # noqa: E402
from store import LASStore  # noqa: E402
from rag.chunker import chunk_filing  # noqa: E402
from rag.providers import get_embedding_provider, get_vector_store  # noqa: E402

MANIFEST_PATH = os.path.join(
    getattr(config, "RAG_VECTORDB_DIR", os.path.join(config.DATA_DIR, "vectordb")),
    "indexed.json",
)


def _load_manifest() -> set[str]:
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r") as f:
            return set(json.load(f))
    return set()


def _save_manifest(indexed: set[str]) -> None:
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(sorted(indexed), f, indent=2)


def index_filings(
    tickers: list[str] | None = None,
    reindex: bool = False,
) -> dict:
    """
    Embed and index filings into the vector store.

    Returns a summary dict with counts.
    """
    db = LASStore()
    try:
        if tickers:
            df = db.get_filings_by_tickers(tickers)
        else:
            df = db.get_all_filings()
    finally:
        db.close()

    if df.empty:
        print("No filings found in the database.")
        return {"indexed": 0, "skipped": 0, "chunks": 0}

    manifest = set() if reindex else _load_manifest()
    embedder = get_embedding_provider()
    store = get_vector_store()

    total_indexed = 0
    total_skipped = 0
    total_chunks = 0

    for _, row in df.iterrows():
        accession = row.get("accession", "")
        ticker = row.get("ticker", "")
        cik = row.get("cik", "")
        report_date = row.get("report_date", "")
        cleaned_path = row.get("cleaned_text_path", "")

        accession_normalized = str(accession).replace("-", "")
        filing_key = f"{cik}_{accession_normalized}"

        if filing_key in manifest:
            total_skipped += 1
            continue

        if not cleaned_path or not os.path.exists(str(cleaned_path)):
            print(f"  SKIP {ticker} {accession}: no cleaned text at {cleaned_path}")
            total_skipped += 1
            continue

        print(f"  Indexing {ticker} {accession} ({report_date})...")

        chunks = chunk_filing(
            cleaned_json_path=str(cleaned_path),
            ticker=str(ticker),
            cik=str(cik),
            accession=str(accession),
            report_date=str(report_date),
        )

        if not chunks:
            print(f"    No chunks produced, skipping.")
            total_skipped += 1
            continue

        texts = [c["text"] for c in chunks]
        ids = [c["id"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        print(f"    {len(chunks)} chunks, embedding...")
        embeddings = embedder.embed(texts)

        store.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        manifest.add(filing_key)
        _save_manifest(manifest)
        total_indexed += 1
        total_chunks += len(chunks)
        print(f"    Done ({len(chunks)} chunks indexed).")

        time.sleep(1.0)

    _save_manifest(manifest)

    summary = {
        "indexed": total_indexed,
        "skipped": total_skipped,
        "chunks": total_chunks,
        "total_in_store": store.count(),
    }
    print(f"\nIndexing complete: {summary}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Index filings for RAG")
    parser.add_argument("--ticker", default=None, help="Index filings for a specific ticker")
    parser.add_argument("--reindex", action="store_true", help="Force re-index all filings")
    args = parser.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else None
    index_filings(tickers=tickers, reindex=args.reindex)


if __name__ == "__main__":
    main()
