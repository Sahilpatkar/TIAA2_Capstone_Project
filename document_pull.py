import os
import re
import time
import json
import requests
from urllib.parse import urljoin

import config

SEC_DATA = "https://data.sec.gov/"
SEC_ARCHIVES = "https://www.sec.gov/Archives/"

HEADERS = {
    "User-Agent": "YourAppName your.email@domain.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

def sec_get(url, host="data.sec.gov", max_retries=5):
    headers = dict(HEADERS)
    headers["Host"] = host
    for i in range(max_retries):
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            return r
        # simple backoff for 429/5xx
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(1.5 * (i + 1))
            continue
        r.raise_for_status()
    raise RuntimeError(f"Failed after retries: {url} ({r.status_code})")

def cik10(cik: int) -> str:
    return str(cik).zfill(10)

def get_10k_filings_for_cik(cik: int):
    url = f"{SEC_DATA}submissions/CIK{cik10(cik)}.json"
    data = sec_get(url, host="data.sec.gov").json()
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    out = []
    for idx, form in enumerate(forms):
        if form == "10-K":
            accession = recent["accessionNumber"][idx]
            filed = recent["filingDate"][idx]
            primary_doc = recent["primaryDocument"][idx]
            report_date = recent.get("reportDate", [None]*len(forms))[idx]
            out.append({
                "cik": cik,
                "accession": accession,
                "filed_date": filed,
                "report_date": report_date,
                "primary_document": primary_doc,
            })
    return out

def filing_primary_doc_url(cik: int, accession: str, primary_doc: str) -> str:
    # accession like 0000320193-25-000010 -> remove dashes for folder
    acc_nodash = accession.replace("-", "")
    return urljoin(SEC_ARCHIVES, f"edgar/data/{int(cik)}/{acc_nodash}/{primary_doc}")

def get_company_facts(cik: int):
    url = f"{SEC_DATA}api/xbrl/companyfacts/CIK{cik10(cik)}.json"
    return sec_get(url, host="data.sec.gov").json()

def safe_folder_name(name: str) -> str:
    """Sanitize a string for use as a filesystem folder name."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "unknown"

def output_dir_for_entity(entity_name: str, cik: int) -> str:
    """Return folder path under data/filings/ (e.g. data/filings/Apple Inc_0000320193)."""
    safe_name = safe_folder_name(entity_name)
    return os.path.join(config.FILINGS_DIR, f"{safe_name}_{cik10(cik)}")

def pull_all(ciks: list[int] | None = None, max_filings: int | None = None):
    """Download 10-K filings for every CIK (defaults to all in config)."""
    if ciks is None:
        ciks = list(config.CIK_TO_TICKER.keys())

    limit = max_filings or config.MAX_FILINGS_PER_CIK
    os.makedirs(config.FILINGS_DIR, exist_ok=True)

    for cik in ciks:
        ticker = config.CIK_TO_TICKER.get(cik, "?")
        print(f"\n{'='*60}")
        print(f"Pulling filings for CIK {cik} ({ticker})")
        print(f"{'='*60}")

        try:
            facts = get_company_facts(cik)
        except Exception as e:
            print(f"  ERROR fetching company facts: {e}")
            continue

        entity_name = facts.get("entityName", "Unknown")
        out_dir = output_dir_for_entity(entity_name, cik)
        os.makedirs(out_dir, exist_ok=True)
        print(f"  Output folder: {out_dir}")

        try:
            tenks = get_10k_filings_for_cik(cik)
        except Exception as e:
            print(f"  ERROR fetching 10-K list: {e}")
            continue

        for f in tenks[:limit]:
            primary_base = os.path.splitext(f["primary_document"])[0]
            doc_filename = f"{f['accession'].replace('-', '')}_{primary_base}.html"
            doc_path = os.path.join(out_dir, doc_filename)

            if os.path.exists(doc_path):
                print(f"  Already on disk: {doc_path}")
                continue

            try:
                doc_url = filing_primary_doc_url(cik, f["accession"], f["primary_document"])
                html = sec_get(doc_url, host="www.sec.gov").text
                with open(doc_path, "w", encoding="utf-8") as fp:
                    fp.write(html)
                print(f"  Downloaded {f['accession']} ({f['filed_date']}) -> {doc_path}")
            except Exception as e:
                print(f"  ERROR downloading {f['accession']}: {e}")

            time.sleep(0.2)

        facts_path = os.path.join(out_dir, "company_facts.json")
        if not os.path.exists(facts_path):
            with open(facts_path, "w", encoding="utf-8") as fp:
                json.dump(facts, fp, indent=2)
            print(f"  Saved company_facts.json")

    print(f"\nDone. Filings stored in {config.FILINGS_DIR}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pull 10-K filings from SEC EDGAR")
    parser.add_argument(
        "--ciks", default=None,
        help="Comma-separated CIK numbers (default: all tickers in config)",
    )
    parser.add_argument("--max-filings", type=int, default=None, help="Max filings per CIK")
    args = parser.parse_args()

    ciks = None
    if args.ciks:
        ciks = [int(c.strip()) for c in args.ciks.split(",")]

    pull_all(ciks=ciks, max_filings=args.max_filings)
