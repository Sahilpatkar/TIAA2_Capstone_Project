"""
Calculate the Lazy Attention Score (LAS) for each filing.

LAS = w_change * f(change_intensity)
    - w_attention * f(attention_proxy)
    + w_car * f(|car|)

where f() is a cross-sectional normalization (rank percentile or z-score)
controlled by config.LAS_NORMALIZATION.

Usage:
    # Typically called from run_pipeline.py, not standalone.
    python las.py   (prints demo with dummy data)
"""

import numpy as np
import pandas as pd

import config

def _rank_normalize(series: pd.Series) -> pd.Series:
    """Cross-sectional rank percentile in [0, 1]."""
    return series.rank(pct=True, na_option="keep")


def _zscore_normalize(series: pd.Series) -> pd.Series:
    """Cross-sectional z-score (mean 0, std 1)."""
    mean = series.mean()
    std = series.std()
    if std == 0 or pd.isna(std):
        return series * 0.0
    return (series - mean) / std


def normalize(series: pd.Series, method: str | None = None) -> pd.Series:
    method = method or config.LAS_NORMALIZATION
    if method == "rank":
        return _rank_normalize(series)
    if method == "zscore":
        return _zscore_normalize(series)
    raise ValueError(f"Unknown normalization method: {method}")

def compute_las(filings_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute LAS for a DataFrame of filing-level features.

    Required columns: change_intensity, attention_proxy, car.
    All may contain NaN (treated as missing; LAS will also be NaN).

    Returns the input DataFrame augmented with:
        norm_change, norm_attention, norm_car, las
    """
    df = filings_df.copy()
    w = config.LAS_WEIGHTS

    df["change_intensity"] = pd.to_numeric(df["change_intensity"], errors="coerce")
    df["attention_proxy"] = pd.to_numeric(df["attention_proxy"], errors="coerce")
    df["car"] = pd.to_numeric(df["car"], errors="coerce")

    df["norm_change"] = normalize(df["change_intensity"])
    df["norm_attention"] = normalize(df["attention_proxy"])
    df["norm_car"] = normalize(df["car"].abs())

    df["las"] = (
        w["w_change"] * df["norm_change"]
        - w["w_attention"] * df["norm_attention"]
        + w["w_car"] * df["norm_car"]
    )

    return df


def weighted_change_intensity(
    section_changes: list[dict],
    weights: dict[str, float] | None = None,
) -> float | None:
    """Compute a weighted average of per-section change intensities.

    *section_changes* is the list produced by ``similarity.compute_similarity``
    — each element must have ``"section"`` and ``"change_intensity"`` keys.

    *weights* defaults to ``config.SECTION_WEIGHTS``.  Sections not present in
    the weights dict are ignored.  Returns ``None`` when no usable data exists
    (caller should fall back to the document-level change_intensity).
    """
    if not section_changes:
        return None

    w = weights if weights is not None else config.SECTION_WEIGHTS
    total_w = 0.0
    total_ci = 0.0

    for sc in section_changes:
        sec_key = sc.get("section")
        ci = sc.get("change_intensity")
        if sec_key is None or ci is None:
            continue
        sec_w = w.get(sec_key, 0.0)
        if sec_w <= 0:
            continue
        total_w += sec_w
        total_ci += sec_w * ci

    if total_w == 0:
        return None

    return total_ci / total_w


def compute_section_las(section_changes: list[dict]) -> list[dict]:
    """
    Rank sections by change_intensity and assign a section-level LAS proxy.
    This is a simplified score: just the rank-normalized change intensity.
    """
    if not section_changes:
        return []

    intensities = [s.get("change_intensity") or 0.0 for s in section_changes]
    series = pd.Series(intensities)
    ranked = _rank_normalize(series)

    result = []
    for i, sec in enumerate(section_changes):
        result.append({
            **sec,
            "section_las": round(float(ranked.iloc[i]), 6) if pd.notna(ranked.iloc[i]) else None,
        })
    return result

def main():
    demo = pd.DataFrame({
        "accession": ["filing_a", "filing_b", "filing_c"],
        "change_intensity": [0.3, 0.7, 0.5],
        "attention_proxy": [0.5, 0.5, 0.5],
        "car": [0.02, -0.05, 0.01],
    })
    result = compute_las(demo)
    print(result[["accession", "change_intensity", "car", "las"]].to_string(index=False))


if __name__ == "__main__":
    main()
