import os
import re
import threading
import time
import json
import requests
from urllib.parse import urljoin

from tiaa import config

SEC_DATA = "https://data.sec.gov/"
SEC_ARCHIVES = "https://www.sec.gov/Archives/"

HEADERS = {
    "User-Agent": "YourAppName your.email@domain.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

_SEC_SEMAPHORE = threading.Semaphore(8)


def sec_get(url, host="data.sec.gov", max_retries=5):
    with _SEC_SEMAPHORE:
        headers = dict(HEADERS)
        headers["Host"] = host
        for i in range(max_retries):
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (i + 1))
                continue
            r.raise_for_status()
        raise RuntimeError(f"Failed after retries: {url} ({r.status_code})")

def cik10(cik: int) -> str:
    return str(cik).zfill(10)

def _extract_filings(block: dict, cik: int, form_types: list[str] | None = None) -> list[dict]:
    """Extract entries matching *form_types* from a submissions block."""
    form_types = form_types or getattr(config, "FILING_TYPES", ["10-K"])
    form_set = set(form_types)
    forms = block.get("form", [])
    out = []
    for idx, form in enumerate(forms):
        if form in form_set:
            out.append({
                "cik": cik,
                "form_type": form,
                "accession": block["accessionNumber"][idx],
                "filed_date": block["filingDate"][idx],
                "report_date": block.get("reportDate", [None] * len(forms))[idx],
                "primary_document": block["primaryDocument"][idx],
            })
    return out


def _extract_10ks(block: dict, cik: int) -> list[dict]:
    """Extract 10-K entries (backward-compatible wrapper)."""
    return _extract_filings(block, cik, ["10-K"])


def get_filings_for_cik(cik: int, form_types: list[str] | None = None) -> list[dict]:
    """Fetch filings of given types for a CIK from SEC EDGAR."""
    form_types = form_types or getattr(config, "FILING_TYPES", ["10-K"])
    url = f"{SEC_DATA}submissions/CIK{cik10(cik)}.json"
    data = sec_get(url, host="data.sec.gov").json()

    recent = data.get("filings", {}).get("recent", {})
    out = _extract_filings(recent, cik, form_types)

    for file_ref in data.get("filings", {}).get("files", []):
        try:
            overflow_url = f"{SEC_DATA}submissions/{file_ref['name']}"
            overflow = sec_get(overflow_url, host="data.sec.gov").json()
            out.extend(_extract_filings(overflow, cik, form_types))
        except Exception:
            pass

    out.sort(key=lambda f: f["filed_date"], reverse=True)
    return out


def get_10k_filings_for_cik(cik: int):
    """Backward-compatible: fetch only 10-K filings."""
    return get_filings_for_cik(cik, ["10-K"])

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
