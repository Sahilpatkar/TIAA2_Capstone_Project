"""
Prior-year pairing and similarity / change-intensity computation.

For each 10-K we find the prior-year 10-K (by report date) and compute
cosine similarity, Jaccard similarity, and change intensity at both the
document and section levels.

Usage:
    python similarity.py --entity-dir "Apple Inc._0000320193"
"""

import argparse
import json
import os
import re
from datetime import datetime

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity as sk_cosine

from embeddings import build_vectors, load_cleaned_filings, tokenize_and_lemmatize
import config


# ---------------------------------------------------------------------------
# Filing metadata extraction
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"(\d{4})(\d{2})(\d{2})")


def _report_date_from_basename(basename: str) -> str | None:
    """
    Extract report date from a cleaned-filing basename like
    '000032019325000079_aapl-20250927'.  Returns 'YYYY-MM-DD' or None.
    """
    m = re.search(r"-(\d{8})", basename)
    if m:
        d = m.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return None


def _parse_date(date_str: str) -> datetime | None:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------

def pair_filings(filings: list[dict]) -> list[tuple[dict, dict]]:
    """
    Pair each filing with its prior-year counterpart.
    Returns list of (current, prior) tuples sorted by report date descending.
    """
    dated = []
    for f in filings:
        rd = _report_date_from_basename(f["_basename"])
        if rd:
            f["_report_date"] = rd
            dated.append(f)

    dated.sort(key=lambda x: x["_report_date"])

    pairs = []
    for i in range(1, len(dated)):
        current = dated[i]
        prior = dated[i - 1]
        cur_dt = _parse_date(current["_report_date"])
        pri_dt = _parse_date(prior["_report_date"])
        if cur_dt and pri_dt and 200 < (cur_dt - pri_dt).days < 550:
            pairs.append((current, prior))

    return pairs


# ---------------------------------------------------------------------------
# Similarity measures
# ---------------------------------------------------------------------------

def cosine_sim(v1, v2) -> float:
    """Cosine similarity between two sparse or dense vectors."""
    sim = sk_cosine(v1, v2)
    return float(sim[0, 0])


def jaccard_sim(text1: str, text2: str) -> float:
    """Jaccard similarity on lemmatized token sets."""
    set1 = set(tokenize_and_lemmatize(text1).split())
    set2 = set(tokenize_and_lemmatize(text2).split())
    if not set1 and not set2:
        return 1.0
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union) if union else 1.0


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def compute_similarity(entity_dir: str) -> list[dict]:
    """
    Compute document-level and section-level similarity for all
    consecutive filing pairs in *entity_dir*.
    """
    filings = load_cleaned_filings(entity_dir)
    if len(filings) < 2:
        print(f"  Need at least 2 filings for comparison; found {len(filings)}")
        return []

    vec_result = build_vectors(entity_dir, use_tfidf=False, remove_stopwords=True)
    doc_vectors = vec_result["doc_vectors"]
    section_vectors = vec_result["section_vectors"]

    pairs = pair_filings(filings)
    results = []

    for current, prior in pairs:
        cur_bn = current["_basename"]
        pri_bn = prior["_basename"]

        cur_vec = doc_vectors.get(cur_bn)
        pri_vec = doc_vectors.get(pri_bn)

        cos = cosine_sim(cur_vec, pri_vec) if cur_vec is not None and pri_vec is not None else None
        jac = jaccard_sim(current["full_text"], prior["full_text"])

        primary_sim = cos if cos is not None else jac
        change_intensity = 1.0 - primary_sim if primary_sim is not None else None

        # Section-level changes
        section_changes = []
        cur_sections = current.get("sections", {})
        pri_sections = prior.get("sections", {})
        common_sections = set(cur_sections.keys()) & set(pri_sections.keys())

        cur_sec_vecs = section_vectors.get(cur_bn, {})
        pri_sec_vecs = section_vectors.get(pri_bn, {})

        for sec_key in sorted(common_sections):
            sec_cos = None
            cv = cur_sec_vecs.get(sec_key)
            pv = pri_sec_vecs.get(sec_key)
            if cv is not None and pv is not None:
                sec_cos = cosine_sim(cv, pv)

            sec_jac = jaccard_sim(cur_sections[sec_key], pri_sections[sec_key])
            sec_sim = sec_cos if sec_cos is not None else sec_jac
            section_changes.append({
                "section": sec_key,
                "similarity_cosine": round(sec_cos, 6) if sec_cos is not None else None,
                "similarity_jaccard": round(sec_jac, 6),
                "change_intensity": round(1.0 - sec_sim, 6) if sec_sim is not None else None,
            })

        section_changes.sort(key=lambda s: s["change_intensity"] or 0, reverse=True)

        results.append({
            "current_basename": cur_bn,
            "prior_basename": pri_bn,
            "current_report_date": current.get("_report_date"),
            "prior_report_date": prior.get("_report_date"),
            "similarity_cosine": round(cos, 6) if cos is not None else None,
            "similarity_jaccard": round(jac, 6),
            "change_intensity": round(change_intensity, 6) if change_intensity is not None else None,
            "section_changes": section_changes,
        })

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Compute filing similarity and change intensity")
    parser.add_argument("--entity-dir", required=True, help="Path to entityName_cik folder")
    args = parser.parse_args()

    results = compute_similarity(args.entity_dir)
    for r in results:
        print(
            f"  {r['current_report_date']} vs {r['prior_report_date']}: "
            f"cosine={r['similarity_cosine']}  jaccard={r['similarity_jaccard']}  "
            f"change={r['change_intensity']}"
        )
        for sc in r["section_changes"][:3]:
            print(f"    {sc['section']}: change={sc['change_intensity']}")

    out_path = os.path.join(args.entity_dir, "cleaned", "similarity_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Results saved to {out_path}")


if __name__ == "__main__":
    main()
