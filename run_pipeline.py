"""
End-to-end LazyPrices pipeline orchestrator.

Runs every stage — pull (optional), extract, embed, similarity, attention,
abnormal returns, LAS, and store — for one or more CIKs, then prints a
summary table.  Already-processed filings are skipped automatically unless
``--force`` is passed.

Supports parallel processing with ``--workers N`` (default 1 = sequential).

Usage:
    python run_pipeline.py --ciks 320193
    python run_pipeline.py --ciks 320193,19617 --skip-pull
    python run_pipeline.py --ciks 320193 --skip-pull --max-filings 3
    python run_pipeline.py --ciks 320193 --force
    python run_pipeline.py --workers 4          # parallel across all tickers
"""

import argparse
import contextlib
import io
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

import config
from document_pull import (
    cik10,
    filing_primary_doc_url,
    get_10k_filings_for_cik,
    get_filings_for_cik,
    get_company_facts,
    output_dir_for_entity,
    sec_get,
)
from extract_clean import process_entity_dir
from embeddings import build_vectors, save_vectors
from similarity import compute_similarity
from attention_proxy import get_attention_proxy
from abnormal_returns import compute_car, resolve_ticker
from las import compute_las, compute_section_las, weighted_change_intensity
from store import LASStore, _normalize_accession

log = logging.getLogger("pipeline")


# Step 1: Pull filings from SEC

def pull_filings(cik: int, max_filings: int | None = None) -> tuple[str, list[dict]]:
    """Download filings for *cik* (10-K and 10-Q per config.FILING_TYPES).
    Returns (entity_dir, filing_metadata_list)."""
    facts = get_company_facts(cik)
    entity_name = facts.get("entityName", "Unknown")
    out_dir = output_dir_for_entity(entity_name, cik)
    os.makedirs(out_dir, exist_ok=True)

    form_types = getattr(config, "FILING_TYPES", ["10-K"])
    limit = max_filings or config.MAX_FILINGS_PER_CIK

    all_filings: list[dict] = []
    for ft in form_types:
        filings = get_filings_for_cik(cik, [ft])
        all_filings.extend(filings[:limit])

    for f in all_filings:
        f["accession"] = _normalize_accession(f["accession"])

    for f in all_filings:
        primary_base = os.path.splitext(f["primary_document"])[0]
        doc_filename = f"{f['accession'].replace('-', '')}_{primary_base}.html"
        doc_path = os.path.join(out_dir, doc_filename)

        if os.path.exists(doc_path):
            log.info("  [pull] Already on disk: %s", doc_path)
            continue

        doc_url = filing_primary_doc_url(cik, f["accession"], f["primary_document"])
        html = sec_get(doc_url, host="www.sec.gov").text
        with open(doc_path, "w", encoding="utf-8") as fp:
            fp.write(html)
        ft_label = f.get("form_type", "10-K")
        log.info("  [pull] Downloaded %s %s -> %s", ft_label, f["accession"], doc_path)
        time.sleep(0.2)

    facts_path = os.path.join(out_dir, "company_facts.json")
    if not os.path.exists(facts_path):
        with open(facts_path, "w", encoding="utf-8") as fp:
            json.dump(facts, fp, indent=2)

    return out_dir, all_filings



# Locate entity dir if skipping pull
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



# Resolve filed_date from SEC metadata (best-effort)

def _enrich_filed_dates(cik: int, filings_meta: list[dict]) -> list[dict]:
    """Try to fill in filed_date from SEC submissions API."""
    try:
        api_filings = get_filings_for_cik(cik)
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
# Market-data fetcher (thread-safe, used for parallel yfinance calls)
# ---------------------------------------------------------------------------

def _fetch_market_data(ticker: str, filed_date: str) -> tuple[float | None, float | None]:
    """Return (attention_proxy, car) for a single filing."""
    attn = None
    car_val = None

    try:
        attn = get_attention_proxy(ticker, filed_date)
        if attn is not None:
            log.info("  [attention] %s %s  volume ratio=%.4f", ticker, filed_date, attn)
        else:
            log.info("  [attention] %s %s  no volume data available from Yahoo Finance", ticker, filed_date)
    except Exception as e:
        log.warning("  [attention] %s %s  error: %s", ticker, filed_date, e)

    try:
        car_result = compute_car(ticker, filed_date)
        car_val = car_result.get("car")
        if car_val is not None:
            log.info("  [returns]   %s %s  CAR=%.4f", ticker, filed_date, car_val)
        else:
            log.info("  [returns]   %s %s  stock price data not available from Yahoo Finance", ticker, filed_date)
    except Exception as e:
        log.warning("  [returns]   %s %s  error: %s", ticker, filed_date, e)

    return attn, car_val


# ---------------------------------------------------------------------------
# Per-CIK pipeline (can be run in its own thread)
# ---------------------------------------------------------------------------

def _process_one_cik(
    cik: int,
    skip_pull: bool,
    max_filings: int | None,
    force: bool,
    pipeline_ver: str,
    yf_workers: int = 1,
) -> tuple[int, int]:
    """Run the full pipeline for a single CIK. Returns (n_processed, n_skipped).

    Each invocation creates its own DB connection so it is safe to call from
    multiple threads concurrently.
    """
    db = LASStore()
    ticker = resolve_ticker(cik) or "?"

    log.info("\n%s", "=" * 60)
    log.info("Processing CIK %d (%s)", cik, ticker)
    log.info("%s", "=" * 60)

    # --- Step 1: Pull ---
    if skip_pull:
        entity_dir = find_entity_dir(cik)
        if entity_dir is None:
            log.error("  [pull] No entity dir found for CIK %d. Run without --skip-pull.", cik)
            db.close()
            return 0, 0
        filings_meta = _filing_metadata_from_dir(entity_dir, cik)
    else:
        log.info("  [pull] Downloading SEC filings for %s (CIK %d)...", ticker, cik)
        entity_dir, filings_meta = pull_filings(cik, max_filings)

    filings_meta = _enrich_filed_dates(cik, filings_meta)

    # --- Check for unprocessed filings ---
    if force:
        to_process = filings_meta
        n_skipped = 0
        log.info("  --force enabled: reprocessing all %d filing(s)", len(filings_meta))
    else:
        to_process = db.get_unprocessed_filings(cik, filings_meta, pipeline_ver)
        n_skipped = len(filings_meta) - len(to_process)

        if not to_process:
            log.info("  %s: all %d filing(s) already up to date (pipeline v%s)",
                     ticker, len(filings_meta), pipeline_ver)
            db.close()
            return 0, n_skipped

        skipped_accs = [fm["accession"] for fm in filings_meta if fm not in to_process]
        for acc in skipped_accs:
            log.info("  [skip] %s (already processed)", acc)
        for fm in to_process:
            log.info("  [new]  %s (will process)", fm["accession"])

    entity_name = None
    facts_path = os.path.join(entity_dir, "company_facts.json")
    if os.path.exists(facts_path):
        with open(facts_path, "r") as f:
            entity_name = json.load(f).get("entityName")

    log.info("  Entity dir: %s  (%d new, %d skipped)", entity_dir, len(to_process), n_skipped)

    # --- Step 2: Extract & clean ---
    log.info("  [extract] Cleaning and extracting text from %d HTML filings for %s...",
             len(to_process), ticker)
    cleaned_paths = process_entity_dir(entity_dir)
    if not cleaned_paths:
        log.warning("  [extract] No HTML files found to clean for %s.", ticker)
        db.close()
        return 0, n_skipped

    # --- Step 3: Embeddings ---
    log.info("  [embed] Building document vectors for %s...", ticker)
    vec_result = build_vectors(entity_dir, use_tfidf=False)
    save_vectors(entity_dir, vec_result)

    # --- Step 4-5: Similarity ---
    log.info("  [similarity] Computing year-over-year similarity for %s...", ticker)
    sim_results = compute_similarity(entity_dir)
    if not sim_results:
        log.warning("  WARNING: Need >= 2 filings for similarity.")
        if len(cleaned_paths) >= 2:
            log.warning("  (You have 2+ cleaned filings but no pairs passed the "
                        "200-550 day gap filter.)")

    sim_lookup: dict[str, dict] = {}
    for sr in sim_results:
        sim_lookup[sr["current_basename"]] = sr

    # --- Pre-compute basename mapping for each filing ---
    filing_basenames: dict[str, str | None] = {}
    for fm in to_process:
        accession = _normalize_accession(fm["accession"])
        acc_no_dash = accession.replace("-", "")
        basename = None
        for cp in cleaned_paths:
            bn = os.path.basename(cp).replace("_cleaned.json", "")
            if acc_no_dash in bn:
                basename = bn
                break
        if basename is None and fm.get("report_date") and ticker != "?":
            date_compact = fm["report_date"].replace("-", "") if isinstance(fm["report_date"], str) else ""
            ticker_lower = ticker.lower()
            for cp in cleaned_paths:
                bn = os.path.basename(cp).replace("_cleaned.json", "")
                if date_compact in bn and ticker_lower in bn.lower():
                    basename = bn
                    break
        filing_basenames[accession] = basename

    # --- Step 6-7: Fetch market data (attention + CAR) in parallel ---
    log.info("  [market] Fetching market data from Yahoo Finance for %s (%d filing(s))...",
             ticker, len(to_process))

    market_data: dict[str, tuple[float | None, float | None]] = {}
    filings_needing_market = [
        (fm, _normalize_accession(fm["accession"]))
        for fm in to_process
        if fm.get("filed_date") and ticker != "?"
    ]

    if filings_needing_market:
        with ThreadPoolExecutor(max_workers=yf_workers) as yf_pool:
            future_to_acc = {
                yf_pool.submit(_fetch_market_data, ticker, fm["filed_date"]): acc
                for fm, acc in filings_needing_market
            }
            for fut in as_completed(future_to_acc):
                acc = future_to_acc[fut]
                try:
                    market_data[acc] = fut.result()
                except Exception as e:
                    log.warning("  [market] %s failed: %s", acc, e)
                    market_data[acc] = (None, None)

    # Market data summary
    attn_ok = sum(1 for a, c in market_data.values() if a is not None)
    car_ok = sum(1 for a, c in market_data.values() if c is not None)
    total_mkt = len(market_data)
    if total_mkt:
        log.info("  [market] Completed: %d/%d filings have volume data, %d/%d have return data",
                 attn_ok, total_mkt, car_ok, total_mkt)

    # --- Assemble rows ---
    rows_for_las = []
    for fm in to_process:
        accession = _normalize_accession(fm["accession"])
        filed_date = fm.get("filed_date")
        report_date = fm.get("report_date")
        basename = filing_basenames.get(accession)

        sr = sim_lookup.get(basename, {})
        attn, car_val = market_data.get(accession, (None, None))

        cleaned_text_path = None
        if basename:
            candidate = os.path.join(entity_dir, "cleaned", f"{basename}_cleaned.json")
            if os.path.exists(candidate):
                cleaned_text_path = candidate

        sec_changes = sr.get("section_changes", [])
        w_ci = weighted_change_intensity(sec_changes)
        ci = w_ci if w_ci is not None else sr.get("change_intensity")

        rows_for_las.append({
            "cik": cik,
            "entity_name": entity_name,
            "accession": accession,
            "filed_date": filed_date,
            "report_date": report_date,
            "ticker": ticker,
            "similarity_cosine": sr.get("similarity_cosine"),
            "similarity_jaccard": sr.get("similarity_jaccard"),
            "numerical_divergence": sr.get("numerical_divergence"),
            "change_intensity": ci,
            "attention_proxy": attn,
            "car": car_val,
            "section_changes": sec_changes,
            "cleaned_text_path": cleaned_text_path,
        })

    # --- Step 8: LAS ---
    log.info("  [las] Computing Lazy Attention Scores for %s...", ticker)
    df = pd.DataFrame(rows_for_las)
    if "change_intensity" in df.columns and df["change_intensity"].notna().any():
        df = compute_las(df)
    else:
        df["las"] = None

    # --- Step 9: Store & mark processed ---
    log.info("  [store] Saving results to database for %s...", ticker)
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

    n_processed = len(df)
    log.info("  [done] Completed processing for %s: %d filing(s) stored", ticker, n_processed)
    db.close()
    return n_processed, n_skipped


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(
    ciks: list[int],
    skip_pull: bool = False,
    max_filings: int | None = None,
    force: bool = False,
    workers: int = 1,
):
    pipeline_ver = config.PIPELINE_VERSION

    if workers <= 1:
        results = []
        for cik in ciks:
            results.append(
                _process_one_cik(cik, skip_pull, max_filings, force, pipeline_ver)
            )
    else:
        log.info("Launching %d parallel workers for %d CIKs", workers, len(ciks))
        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_cik = {
                pool.submit(
                    _process_one_cik, cik, skip_pull, max_filings, force,
                    pipeline_ver,
                ): cik
                for cik in ciks
            }
            for fut in as_completed(future_to_cik):
                cik = future_to_cik[fut]
                try:
                    results.append(fut.result())
                except Exception as e:
                    log.error("CIK %d failed: %s", cik, e)
                    results.append((0, 0))

    total_processed = sum(r[0] for r in results)
    total_skipped = sum(r[1] for r in results)

    # --- Summary ---
    log.info("\n%s", "=" * 60)
    log.info("SUMMARY")
    log.info("%s", "=" * 60)
    if force:
        log.info("  Mode: --force (manual override, all filings reprocessed)")
    log.info("  Pipeline version: %s", pipeline_ver)
    log.info("  Workers:           %d", workers)
    log.info("  Filings processed: %d", total_processed)
    log.info("  Filings skipped:   %d", total_skipped)

    db = LASStore()
    all_filings = db.get_all_filings()
    if not all_filings.empty:
        cols = ["ticker", "report_date", "change_intensity", "car", "las"]
        display_cols = [c for c in cols if c in all_filings.columns]
        log.info("\n%s", all_filings[display_cols].to_string(index=False))
    else:
        log.info("  No filings in database.")
    db.close()



# Lightweight re-scoring (skips pull, extract, embed, similarity, attention, CAR)

def rescore_las():
    """Re-compute LAS from existing component values in the DB.

    Useful after changing LAS_WEIGHTS or the LAS formula without needing
    to re-fetch market data from Yahoo Finance.
    """
    db = LASStore()
    df = db.get_all_filings()
    if df.empty:
        log.info("No filings in database.")
        db.close()
        return

    required = ["change_intensity", "attention_proxy", "car"]
    scoreable = df.dropna(subset=required)
    log.info("Re-scoring %d filings (of %d total) with v%s LAS formula",
             len(scoreable), len(df), config.PIPELINE_VERSION)

    scored = compute_las(scoreable)

    cur = db._cursor()
    p = db._p()
    for _, row in scored.iterrows():
        db._execute(
            f"UPDATE filings SET las={p}, norm_change={p}, norm_attention={p}, norm_car={p} "
            f"WHERE cik={p} AND accession={p}",
            (row["las"], row["norm_change"], row["norm_attention"], row["norm_car"],
             row["cik"], row["accession"]),
        )
    db._conn.commit()
    db.close()

    log.info("Updated %d filings.", len(scored))
    log.info("\n%s", scored[["ticker", "report_date", "change_intensity", "car", "las"]].to_string(index=False))


# CLI


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
    parser.add_argument(
        "--rescore-only", action="store_true",
        help="Only re-compute LAS from existing DB values (no data fetching)",
    )
    parser.add_argument(
        "--workers", type=int, default=None,
        help=f"Number of parallel CIK workers (default: config.PIPELINE_WORKERS={getattr(config, 'PIPELINE_WORKERS', 1)})",
    )
    args = parser.parse_args()

    workers = args.workers or getattr(config, "PIPELINE_WORKERS", 1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s" if workers <= 1 else "[%(threadName)s] %(message)s",
    )

    if args.rescore_only:
        rescore_las()
        return

    if args.ciks:
        ciks = [int(c.strip()) for c in args.ciks.split(",")]
    else:
        ciks = list(config.CIK_TO_TICKER.keys())

    run(ciks, skip_pull=args.skip_pull, max_filings=args.max_filings,
        force=args.force, workers=workers)


if __name__ == "__main__":
    main()
