"""
Buy / sell signal classification from LAS components.

Uses change_intensity, attention_proxy, and CAR to produce one of five
signals per holding:  sell, caution, hold, neutral, buy.

Confidence is a blend of absolute (global universe) and relative
(portfolio-only) z-scores.  The blend weight adapts to portfolio size:
small portfolios lean on the stable absolute baseline; full-universe
portfolios get equal weight (where the two are identical anyway).
Low-confidence signals are downgraded to neutral.
"""

import json
import math

import numpy as np
import pandas as pd

import config


def _zscore(series: pd.Series) -> pd.Series:
    mean = series.mean()
    std = series.std()
    if std == 0 or pd.isna(std):
        return series * 0.0
    return (series - mean) / std


def _compute_z_scores_for_group(holdings: list[dict]) -> dict[str, dict]:
    """Compute per-ticker z-scores for change_intensity, attention_proxy, car."""
    scored = [
        h for h in holdings
        if h.get("change_intensity") is not None
        and h.get("attention_proxy") is not None
        and h.get("car") is not None
    ]
    result: dict[str, dict] = {}
    if len(scored) >= 2:
        ci_z = _zscore(pd.Series([h["change_intensity"] for h in scored]))
        attn_z = _zscore(pd.Series([h["attention_proxy"] for h in scored]))
        car_z = _zscore(pd.Series([h["car"] for h in scored]))
        for i, h in enumerate(scored):
            result[h["ticker"]] = {
                "change_z": float(ci_z.iloc[i]) if pd.notna(ci_z.iloc[i]) else 0.0,
                "attention_z": float(attn_z.iloc[i]) if pd.notna(attn_z.iloc[i]) else 0.0,
                "car_z": float(car_z.iloc[i]) if pd.notna(car_z.iloc[i]) else 0.0,
            }
    elif len(scored) == 1:
        result[scored[0]["ticker"]] = {"change_z": 0.0, "attention_z": 0.0, "car_z": 0.0}
    return result


def _z_confidence(z_scores: dict, ticker: str) -> float:
    zs = z_scores.get(ticker, {})
    return abs(zs.get("change_z", 0.0)) + abs(zs.get("attention_z", 0.0)) + abs(zs.get("car_z", 0.0))


def _classify(
    norm_change: float,
    attention_proxy: float,
    car: float,
    thresholds: dict,
    key_section_boost: bool = False,
) -> tuple[str, list[str]]:
    """Return (signal_label, reasons) based on threshold rules.

    v1.5 rule mapping (backtest-driven):
    ┌──────────────────────────────────────────┬────────────┐
    │ Condition                                │ Signal     │
    ├──────────────────────────────────────────┼────────────┤
    │ high change + low attn + neg CAR         │ sell       │
    │ key-section boost + low attn + neg CAR   │ sell       │
    │ high change + low attn + pos/neutral CAR │ caution    │
    │ high change + high attn + deep neg CAR   │ buy        │
    │ high change + high attn + mild neg CAR   │ hold       │
    │ high attn + pos/neutral CAR              │ hold       │
    │ low change + any                         │ neutral    │
    │ moderate change (fallback)               │ neutral    │
    └──────────────────────────────────────────┴────────────┘

    When *key_section_boost* is True, the effective change_high threshold
    is lowered to allow moderate-change filings to trigger sell/caution
    when the change is concentrated in Risk Factors and MD&A.
    """
    t = thresholds
    sell_change_threshold = t["change_high"]
    if key_section_boost:
        sell_change_threshold = t.get("change_high_boosted", t["change_high"] - 0.10)

    change_high = norm_change >= t["change_high"]
    change_high_for_sell = norm_change >= sell_change_threshold
    change_low = norm_change <= t["change_low"]
    attn_low = attention_proxy < t["attention_low"]
    attn_high = not attn_low
    car_neg = car < t["car_negative"]
    car_deep_neg = car < t.get("car_deep_negative", t["car_negative"] * 3)
    car_pos_neutral = not car_neg

    reasons: list[str] = []

    # SELL: high change (or key-section boosted) + low attention + negative CAR
    if change_high_for_sell and attn_low and car_neg:
        if key_section_boost and not change_high:
            reasons.append("Risk Factors and MD&A both changed substantially (section boost)")
        reasons.append("Large disclosure changes went unnoticed by investors")
        reasons.append("Negative market reaction around filing date")
        reasons.append("Consistent with post-filing negative drift (LazyPrices)")
        return "sell", reasons

    # CAUTION: high change + low attention + positive/neutral CAR
    # (speculative — market hasn't repriced yet but no confirming neg CAR)
    if change_high and attn_low and car_pos_neutral:
        reasons.append("Large disclosure changes went unnoticed by investors")
        reasons.append("Market has not reacted negatively yet — speculative risk")
        reasons.append("Monitor for delayed repricing before acting")
        return "caution", reasons

    # BUY (contrarian): high change + high attention + deep negative CAR
    # Backtest showed old "caution" stocks with deep selloffs rebounded +9.8% at 90d
    if change_high and attn_high and car_deep_neg:
        reasons.append("Material disclosure changes with elevated investor attention")
        reasons.append("Deep negative CAR suggests market overreaction")
        reasons.append("Backtest evidence: deep-selloff + high-awareness stocks tend to rebound")
        return "buy", reasons

    # HOLD: high change + high attention + mild negative CAR
    # Market is aware and reacting, wait for stabilisation
    if change_high and attn_high and car_neg:
        reasons.append("Material disclosure changes detected")
        reasons.append("Investors are aware (elevated volume)")
        reasons.append("Mild negative CAR — market digesting information, wait for stabilisation")
        return "hold", reasons

    # HOLD (Priced In): high attention + positive/neutral CAR
    if attn_high and car_pos_neutral:
        reasons.append("Investors are paying attention (high volume)")
        reasons.append("Market reaction is positive or neutral")
        reasons.append("Disclosure impact likely already priced in")
        return "hold", reasons

    # NEUTRAL: low change — no catalyst regardless of other factors
    # (old "buy" signal retired: low-change carries no predictive upside for DJIA large-caps)
    if change_low:
        reasons.append("Minimal disclosure changes — no catalyst for action")
        reasons.append("Filing consistency signals steady-state operations")
        return "neutral", reasons

    # NEUTRAL: moderate change, no strong signal (fallback)
    reasons.append("Moderate disclosure changes with no decisive signal")
    reasons.append("No catalyst for action — maintain current position")
    return "neutral", reasons


def _section_drivers(holding: dict) -> list[str]:
    """Identify which key sections (Risk Factors, MD&A) drove the change."""
    raw = holding.get("section_changes_json")
    if not raw:
        return []

    changes = json.loads(raw) if isinstance(raw, str) else raw
    if not changes:
        return []

    drivers = []
    for sc in sorted(changes, key=lambda s: s.get("change_intensity") or 0, reverse=True):
        sec = sc.get("section", "")
        ci = sc.get("change_intensity")
        if sec in config.SIGNAL_KEY_SECTIONS and ci and ci > 0.05:
            pretty = sec.replace("_", " ").title()
            drivers.append(f"{pretty} (change: {ci:.3f})")
    return drivers


def _has_key_section_boost(holding: dict) -> bool:
    """Check if Risk Factors AND MD&A both have elevated change_intensity.

    When both of these high-importance sections changed substantially,
    the sell threshold is lowered even if global change_intensity is moderate.
    """
    raw = holding.get("section_changes_json")
    if not raw:
        return False

    changes = json.loads(raw) if isinstance(raw, str) else raw
    if not changes:
        return False

    boost_threshold = getattr(config, "SECTION_SELL_BOOST_THRESHOLD", 0.05)
    required = {"item_1a", "item_7"}
    found = set()

    for sc in changes:
        sec = sc.get("section", "")
        ci = sc.get("change_intensity")
        if sec in required and ci and ci > boost_threshold:
            found.add(sec)

    return found == required


def _adjust_thresholds(risk_tolerance: str) -> dict:
    """Shift thresholds based on client risk profile."""
    t = dict(config.SIGNAL_THRESHOLDS)
    if risk_tolerance == "conservative":
        t["change_high"] = 0.60
        t["car_negative"] = -0.002
        t["car_deep_negative"] = -0.010
    elif risk_tolerance == "aggressive":
        t["change_high"] = 0.85
        t["car_negative"] = -0.01
        t["car_deep_negative"] = -0.025
    return t


def compute_signal(
    holding: dict,
    confidence: float,
    risk_tolerance: str = "moderate",
) -> dict:
    """
    Classify a single holding and return signal metadata.

    Parameters
    ----------
    holding : dict
        Per-ticker dict from aggregate_las (must include norm_change,
        attention_proxy, car).
    confidence : float
        Pre-computed blended confidence score for this holding.
    risk_tolerance : str
        Client risk profile: conservative, moderate, or aggressive.

    Returns
    -------
    dict with keys: signal, confidence, confidence_level, reasons,
    section_drivers.
    """
    norm_change = holding.get("norm_change")
    attention = holding.get("attention_proxy")
    car = holding.get("car")

    if norm_change is None or attention is None or car is None:
        return {
            "signal": "neutral",
            "confidence": 0.0,
            "confidence_level": "weak",
            "reasons": ["Insufficient data to generate a signal"],
            "section_drivers": [],
        }

    thresholds = _adjust_thresholds(risk_tolerance)
    key_boost = _has_key_section_boost(holding)
    signal, reasons = _classify(norm_change, attention, car, thresholds, key_boost)

    conf_thresholds = config.SIGNAL_CONFIDENCE
    if confidence >= conf_thresholds["strong"]:
        confidence_level = "strong"
    elif confidence >= conf_thresholds["moderate"]:
        confidence_level = "moderate"
    else:
        confidence_level = "weak"

    if confidence_level == "weak" and signal not in ("neutral", "hold"):
        reasons.insert(0, f"Downgraded to neutral (confidence {confidence:.2f} below threshold)")
        signal = "neutral"

    drivers = _section_drivers(holding)
    if drivers and signal in ("sell", "caution"):
        reasons.append("Key section changes: " + "; ".join(drivers[:3]))

    return {
        "signal": signal,
        "confidence": round(confidence, 3),
        "confidence_level": confidence_level,
        "reasons": reasons,
        "section_drivers": drivers,
    }


def compute_portfolio_signals(
    portfolio: dict,
    risk_tolerance: str = "moderate",
    universe: list[dict] | None = None,
) -> dict:
    """
    Annotate every holding in *portfolio* with a signal, confidence, and reasons.

    Uses a hybrid confidence score:
      confidence = abs_weight * absolute_confidence + rel_weight * relative_confidence

    *universe* is the full set of latest holdings across all tickers in the DB
    (used for the absolute z-score baseline).  When ``None``, falls back to
    portfolio-only z-scores.

    The blend weight adapts to portfolio size relative to the universe:
      rel_weight = n_portfolio / n_universe
      abs_weight = 1 - rel_weight

    Mutates portfolio["holdings"] in-place and adds a portfolio-level
    "signal_summary" key.

    Returns the enriched portfolio dict.
    """
    holdings = portfolio.get("holdings", [])

    rel_z = _compute_z_scores_for_group(holdings)

    abs_z: dict[str, dict] = {}
    if universe and len(universe) >= 2:
        abs_z = _compute_z_scores_for_group(universe)

    n_portfolio = len([h for h in holdings if h.get("change_intensity") is not None])
    n_universe = len(universe) if universe else n_portfolio
    if n_universe > 0 and abs_z:
        rel_weight = n_portfolio / n_universe
        abs_weight = 1.0 - rel_weight
    else:
        rel_weight = 1.0
        abs_weight = 0.0

    counts = {"sell": 0, "caution": 0, "hold": 0, "neutral": 0, "buy": 0}
    for h in holdings:
        ticker = h.get("ticker", "")
        abs_conf = _z_confidence(abs_z, ticker)
        rel_conf = _z_confidence(rel_z, ticker)
        blended = abs_weight * abs_conf + rel_weight * rel_conf

        sig = compute_signal(h, blended, risk_tolerance)
        h["signal"] = sig["signal"]
        h["signal_confidence"] = sig["confidence"]
        h["signal_confidence_level"] = sig["confidence_level"]
        h["signal_reasons"] = sig["reasons"]
        h["signal_section_drivers"] = sig["section_drivers"]
        counts[sig["signal"]] = counts.get(sig["signal"], 0) + 1

    portfolio["signal_summary"] = counts
    return portfolio
