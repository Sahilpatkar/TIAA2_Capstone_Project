"""
End-to-end LazyPrices pipeline orchestrator.

Runs every stage — pull (optional), extract, embed, similarity, attention,
abnormal returns, LAS, and store — for one or more CIKs, then prints a
summary table.  Already-processed filings are skipped automatically unless
``--force`` is passed.

Usage:
    python run_pipeline.py --ciks 320193
    python run_pipeline.py --ciks 320193,19617 --skip-pull
    python run_pipeline.py --ciks 320193 --skip-pull --max-filings 3
    python run_pipeline.py --ciks 320193 --force
"""

import argparse
import json
import os
import re
import time

import pandas as pd

import config
from document_pull import (
    cik10,
    filing_primary_doc_url,
    get_10k_filings_for_cik,
    get_company_facts,
    output_dir_for_entity,
    sec_get,
)
from extract_clean import process_entity_dir
from embeddings import build_vectors, save_vectors
from similarity import compute_similarity
from attention_proxy import get_attention_proxy
from abnormal_returns import compute_car, resolve_ticker
from las import compute_las, compute_section_las
from store import LASStore, _normalize_accession


# ---------------------------------------------------------------------------
# Step 1: Pull filings from SEC
# ---------------------------------------------------------------------------

def pull_filings(cik: int, max_filings: int | None = None) -> tuple[str, list[dict]]:
    """Download 10-K filings for *cik* (reuses document_pull functions).
    Returns (entity_dir, filing_metadata_list)."""
    facts = get_company_facts(cik)
    entity_name = facts.get("entityName", "Unknown")
    out_dir = output_dir_for_entity(entity_name, cik)
    os.makedirs(out_dir, exist_ok=True)

    tenks = get_10k_filings_for_cik(cik)
    limit = max_filings or config.MAX_FILINGS_PER_CIK
    tenks = tenks[:limit]

    for f in tenks:
        f["accession"] = _normalize_accession(f["accession"])

    for f in tenks:
        primary_base = os.path.splitext(f["primary_document"])[0]
        doc_filename = f"{f['accession'].replace('-', '')}_{primary_base}.html"
        doc_path = os.path.join(out_dir, doc_filename)

        if os.path.exists(doc_path):
            print(f"  [pull] Already on disk: {doc_path}")
            continue

        doc_url = filing_primary_doc_url(cik, f["accession"], f["primary_document"])
        html = sec_get(doc_url, host="www.sec.gov").text
        with open(doc_path, "w", encoding="utf-8") as fp:
            fp.write(html)
        print(f"  [pull] Downloaded {f['accession']} -> {doc_path}")
        time.sleep(0.2)

    facts_path = os.path.join(out_dir, "company_facts.json")
    if not os.path.exists(facts_path):
        with open(facts_path, "w", encoding="utf-8") as fp:
            json.dump(facts, fp, indent=2)

    return out_dir, tenks


# ---------------------------------------------------------------------------
# Locate entity dir if skipping pull
# ---------------------------------------------------------------------------

def find_entity_dir(cik: int) -> str | None:
    """Find the entityName_cik folder on disk for a given CIK."""
    cik_suffix = f"_{cik10(cik)}"
    search_dirs = [config.FILINGS_DIR, config.PROJECT_ROOT]
    for base in search_dirs:
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            if entry.endswith(cik_suffix) and os.path.isdir(
                os.path.join(base, entry)
            ):
                return os.path.join(base, entry)
    return None


def _filing_metadata_from_dir(entity_dir: str, cik: int) -> list[dict]:
    """Reconstruct minimal filing metadata from HTML filenames."""
    filings = []
    for fname in sorted(os.listdir(entity_dir)):
        if not fname.endswith(".html"):
            continue
        m = re.match(r"(\d+)_(.+)\.html", fname)
        if not m:
            continue
        accession_nodash = m.group(1)
        report_m = re.search(r"-(\d{8})", fname)
        report_date = None
        if report_m:
            d = report_m.group(1)
            report_date = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        filings.append({
            "cik": cik,
            "accession": accession_nodash,
            "report_date": report_date,
            "filed_date": None,
            "primary_document": fname,
        })
    return filings


# ---------------------------------------------------------------------------
# Resolve filed_date from SEC metadata (best-effort)
# ---------------------------------------------------------------------------

def _enrich_filed_dates(cik: int, filings_meta: list[dict]) -> list[dict]:
    """Try to fill in filed_date from SEC submissions API."""
    try:
        api_filings = get_10k_filings_for_cik(cik)
    except Exception:
        return filings_meta

    acc_to_filed = {}
    for af in api_filings:
        key = af["accession"].replace("-", "")
        acc_to_filed[key] = af.get("filed_date")
        acc_to_filed[af["accession"]] = af.get("filed_date")

    for fm in filings_meta:
        if not fm.get("filed_date"):
            fm["filed_date"] = acc_to_filed.get(fm["accession"])
            if not fm["filed_date"]:
                fm["filed_date"] = acc_to_filed.get(fm["accession"].replace("-", ""))
    return filings_meta


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(
    ciks: list[int],
    skip_pull: bool = False,
    max_filings: int | None = None,
    force: bool = False,
):
    db = LASStore()
    pipeline_ver = config.PIPELINE_VERSION

    total_processed = 0
    total_skipped = 0

    for cik in ciks:
        ticker = resolve_ticker(cik) or "?"
        print(f"\n{'='*60}")
        print(f"Processing CIK {cik} ({ticker})")
        print(f"{'='*60}")

        # --- Step 1: Pull ---
        if skip_pull:
            entity_dir = find_entity_dir(cik)
            if entity_dir is None:
                print(f"  ERROR: No entity dir found for CIK {cik}. Run without --skip-pull.")
                continue
            filings_meta = _filing_metadata_from_dir(entity_dir, cik)
        else:
            entity_dir, filings_meta = pull_filings(cik, max_filings)

        filings_meta = _enrich_filed_dates(cik, filings_meta)

        # --- Check for unprocessed filings ---
        if force:
            to_process = filings_meta
            n_skipped = 0
            print(f"  --force enabled: reprocessing all {len(filings_meta)} filing(s)")
        else:
            to_process = db.get_unprocessed_filings(cik, filings_meta, pipeline_ver)
            n_skipped = len(filings_meta) - len(to_process)

            if not to_process:
                print(f"  {ticker}: all {len(filings_meta)} filing(s) already up to date "
                      f"(pipeline v{pipeline_ver})")
                total_skipped += n_skipped
                continue

            skipped_accs = [
                fm["accession"] for fm in filings_meta if fm not in to_process
            ]
            for acc in skipped_accs:
                print(f"  [skip] {acc} (already processed)")
            for fm in to_process:
                print(f"  [new]  {fm['accession']} (will process)")

        total_skipped += n_skipped

        entity_name = None
        facts_path = os.path.join(entity_dir, "company_facts.json")
        if os.path.exists(facts_path):
            with open(facts_path, "r") as f:
                entity_name = json.load(f).get("entityName")

        print(f"  Entity dir: {entity_dir}  ({len(to_process)} new, {n_skipped} skipped)")

        # --- Step 2: Extract & clean ---
        print("\n  [extract] Cleaning HTML filings...")
        cleaned_paths = process_entity_dir(entity_dir)
        if not cleaned_paths:
            print("  WARNING: No HTML files found to clean.")
            continue

        # --- Step 3: Embeddings ---
        print("\n  [embed] Building count vectors...")
        vec_result = build_vectors(entity_dir, use_tfidf=False)
        save_vectors(entity_dir, vec_result)

        # --- Step 4-5: Similarity ---
        print("\n  [similarity] Computing year-over-year similarity...")
        sim_results = compute_similarity(entity_dir)
        if not sim_results:
            print("  WARNING: Need >= 2 filings for similarity.")

        sim_lookup: dict[str, dict] = {}
        for sr in sim_results:
            sim_lookup[sr["current_basename"]] = sr

        # --- Step 6-9: For each filing, compute attention, CAR, LAS, store ---
        rows_for_las = []

        for fm in to_process:
            accession = _normalize_accession(fm["accession"])
            filed_date = fm.get("filed_date")
            report_date = fm.get("report_date")

            basename = None
            for cp in cleaned_paths:
                bn = os.path.basename(cp).replace("_cleaned.json", "")
                if accession.replace("-", "") in bn:
                    basename = bn
                    break

            sr = sim_lookup.get(basename, {})

            attn = get_attention_proxy(cik, accession)

            car_val = None
            if filed_date and ticker != "?":
                print(f"  [returns] CAR for {ticker} filed {filed_date}...")
                try:
                    car_result = compute_car(ticker, filed_date)
                    car_val = car_result.get("car")
                except Exception as e:
                    print(f"    CAR error: {e}")

            cleaned_text_path = None
            if basename:
                candidate = os.path.join(entity_dir, "cleaned", f"{basename}_cleaned.json")
                if os.path.exists(candidate):
                    cleaned_text_path = candidate

            rows_for_las.append({
                "cik": cik,
                "entity_name": entity_name,
                "accession": accession,
                "filed_date": filed_date,
                "report_date": report_date,
                "ticker": ticker,
                "similarity_cosine": sr.get("similarity_cosine"),
                "similarity_jaccard": sr.get("similarity_jaccard"),
                "change_intensity": sr.get("change_intensity"),
                "attention_proxy": attn,
                "car": car_val,
                "section_changes": sr.get("section_changes", []),
                "cleaned_text_path": cleaned_text_path,
            })

        # --- Step 8: LAS ---
        print("\n  [las] Computing Lazy Attention Scores...")
        df = pd.DataFrame(rows_for_las)
        if "change_intensity" in df.columns and df["change_intensity"].notna().any():
            df = compute_las(df)
        else:
            df["las"] = None

        # --- Step 9: Store & mark processed ---
        print("  [store] Persisting to database...")
        for _, row in df.iterrows():
            r = row.to_dict()
            section_changes = r.pop("section_changes", [])
            section_las = compute_section_las(section_changes)
            r["section_changes_json"] = json.dumps(section_las)
            db.upsert(r)

            db.mark_processed(
                cik=r["cik"],
                accession=r["accession"],
                ticker=r.get("ticker"),
                filed_date=r.get("filed_date"),
                report_date=r.get("report_date"),
                pipeline_version=pipeline_ver,
            )

        total_processed += len(df)
        print(f"\n  Stored {len(df)} filing(s) for {ticker}")

    # --- Summary ---
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    if force:
        print("  Mode: --force (manual override, all filings reprocessed)")
    print(f"  Pipeline version: {pipeline_ver}")
    print(f"  Filings processed: {total_processed}")
    print(f"  Filings skipped:   {total_skipped}")
    print()

    all_filings = db.get_all_filings()
    if not all_filings.empty:
        cols = ["ticker", "report_date", "change_intensity", "car", "las"]
        display_cols = [c for c in cols if c in all_filings.columns]
        print(all_filings[display_cols].to_string(index=False))
    else:
        print("  No filings in database.")

    db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run the LazyPrices pipeline end-to-end")
    parser.add_argument(
        "--ciks", default=None,
        help="Comma-separated CIK numbers (default: all tickers in config)",
    )
    parser.add_argument("--skip-pull", action="store_true", help="Skip SEC filing download")
    parser.add_argument("--max-filings", type=int, default=None, help="Max filings per CIK")
    parser.add_argument(
        "--force", action="store_true",
        help="Reprocess all filings even if already up to date",
    )
    args = parser.parse_args()

    if args.ciks:
        ciks = [int(c.strip()) for c in args.ciks.split(",")]
    else:
        ciks = list(config.CIK_TO_TICKER.keys())

    run(ciks, skip_pull=args.skip_pull, max_filings=args.max_filings, force=args.force)


if __name__ == "__main__":
    main()
