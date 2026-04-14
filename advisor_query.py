"""
Advisor-facing query interface.

Given a portfolio (list of tickers), this module:
  1. Aggregates LAS across holdings (equal- or custom-weighted).
  2. Retrieves the highest-impact disclosure sections.
  3. Generates a structured explanation (LLM narrative or template fallback).

Usage:
    python advisor_query.py --portfolio AAPL,JPM,KO --top 3
"""

import argparse
import json
import math
import os

from dotenv import load_dotenv

load_dotenv()

import pandas as pd

import config
from signals import compute_portfolio_signals
from store import LASStore



def _fetch_universe(db: LASStore) -> list[dict]:
    """Fetch the latest filing for every ticker in the DB (absolute baseline)."""
    all_tickers = sorted(config.CIK_TO_TICKER.values())
    universe = []
    for ticker in all_tickers:
        latest = db.get_latest_by_ticker(ticker)
        if latest and latest.get("change_intensity") is not None:
            universe.append({
                "ticker": ticker,
                "change_intensity": latest.get("change_intensity"),
                "attention_proxy": latest.get("attention_proxy"),
                "car": latest.get("car"),
            })
    return universe


# 1. Portfolio LAS aggregation
def aggregate_las(
    tickers: list[str],
    weights: dict[str, float] | None = None,
    db: LASStore | None = None,
    risk_tolerance: str = "moderate",
) -> dict:
    """
    Compute a portfolio-level LAS summary with buy/sell signal annotations.

    Parameters
    ----------
    tickers : list[str]
        Ticker symbols in the portfolio.
    weights : dict, optional
        {ticker: weight}.  Defaults to equal weight.
    db : LASStore, optional
        Open database handle.  Opened/closed automatically if None.
    risk_tolerance : str
        Client risk profile used to adjust signal thresholds.

    Returns
    -------
    dict with keys: portfolio_las, holdings (list of per-ticker dicts),
    signal_summary.
    """
    own_db = db is None
    if own_db:
        db = LASStore()

    try:
        holdings = []
        for ticker in tickers:
            latest = db.get_latest_by_ticker(ticker)
            if latest is None:
                holdings.append({"ticker": ticker, "las": None, "note": "no data"})
                continue
            holdings.append({
                "ticker": ticker,
                "entity_name": latest.get("entity_name"),
                "report_date": latest.get("report_date"),
                "las": latest.get("las"),
                "change_intensity": latest.get("change_intensity"),
                "attention_proxy": latest.get("attention_proxy"),
                "car": latest.get("car"),
                "norm_change": latest.get("norm_change"),
                "norm_attention": latest.get("norm_attention"),
                "norm_car": latest.get("norm_car"),
                "section_changes_json": latest.get("section_changes_json"),
            })

        def _valid_las(val):
            return val is not None and not (isinstance(val, float) and math.isnan(val))

        scored = [h for h in holdings if _valid_las(h.get("las"))]
        if not scored:
            portfolio = {"portfolio_las": None, "holdings": holdings}
            universe = _fetch_universe(db)
            compute_portfolio_signals(portfolio, risk_tolerance, universe=universe)
            return portfolio

        if weights:
            total_w = sum(weights.get(h["ticker"], 1.0) for h in scored)
            port_las = sum(
                h["las"] * weights.get(h["ticker"], 1.0) for h in scored
            ) / total_w
        else:
            port_las = sum(h["las"] for h in scored) / len(scored)

        holdings.sort(key=lambda h: h.get("las") or float("-inf"), reverse=True)

        portfolio = {
            "portfolio_las": round(port_las, 6),
            "holdings": holdings,
            "las_weights": config.LAS_WEIGHTS,
        }

        universe = _fetch_universe(db)
        compute_portfolio_signals(portfolio, risk_tolerance, universe=universe)

        for h in holdings:
            h.pop("section_changes_json", None)

        return portfolio
    finally:
        if own_db:
            db.close()


# 2. High-impact section retrieval
def retrieve_high_impact_sections(
    tickers: list[str],
    top_n: int = 5,
    db: LASStore | None = None,
) -> list[dict]:
    """
    Return the *top_n* most-changed sections across the portfolio's
    latest filings, with text snippets.
    """
    own_db = db is None
    if own_db:
        db = LASStore()

    try:
        sections = []
        for ticker in tickers:
            latest = db.get_latest_by_ticker(ticker)
            if not latest:
                continue

            raw = latest.get("section_changes_json")
            if not raw:
                continue
            changes = json.loads(raw) if isinstance(raw, str) else raw

            cleaned_path = latest.get("cleaned_text_path")
            section_texts = {}
            if cleaned_path and os.path.exists(cleaned_path):
                with open(cleaned_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                section_texts = data.get("sections", {})

            for sc in changes:
                snippet_new = sc.get("snippet_new") or ""
                snippet_old = sc.get("snippet_old") or ""
                if not snippet_new:
                    text = section_texts.get(sc["section"], "")
                    snippet_new = text[:500] + "..." if len(text) > 500 else text
                sections.append({
                    "ticker": ticker,
                    "entity_name": latest.get("entity_name"),
                    "report_date": latest.get("report_date"),
                    "section": sc["section"],
                    "change_intensity": sc.get("change_intensity"),
                    "snippet": snippet_new,
                    "snippet_new": snippet_new,
                    "snippet_old": snippet_old,
                })

        sections.sort(key=lambda s: s.get("change_intensity") or 0, reverse=True)
        return sections[:top_n]
    finally:
        if own_db:
            db.close()



# 3. Structured explanation (LLM or template fallback)


def _template_narrative(portfolio: dict, high_impact: list[dict]) -> str:
    """Plain-text summary when no LLM API key is available."""
    lines = []
    plas = portfolio.get("portfolio_las")
    lines.append(f"Portfolio Lazy Attention Score (LAS): {plas}")
    lines.append("")

    lines.append("Holdings ranked by LAS (highest first):")
    for h in portfolio.get("holdings", []):
        las_str = f"{h['las']:.4f}" if h.get("las") is not None else "N/A"
        lines.append(f"  {h['ticker']}: LAS={las_str}")

    if high_impact:
        lines.append("")
        lines.append("Highest-impact disclosure changes:")
        for s in high_impact:
            ci = s.get("change_intensity")
            ci_str = f"{ci:.4f}" if ci is not None else "N/A"
            lines.append(f"  [{s['ticker']}] {s['section']} (change={ci_str})")
            if s.get("snippet"):
                lines.append(f"    {s['snippet'][:200]}...")

    return "\n".join(lines)


def _llm_narrative(portfolio: dict, high_impact: list[dict]) -> str:
    """Generate an explanation via OpenAI."""
    try:
        from openai import OpenAI
    except ImportError:
        return _template_narrative(portfolio, high_impact)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _template_narrative(portfolio, high_impact)

    client = OpenAI(api_key=api_key)

    prompt_data = json.dumps(
        {"portfolio_summary": portfolio, "high_impact_sections": high_impact},
        indent=2,
        default=str,
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a financial advisor assistant. Given a portfolio's "
                "Lazy Attention Score (LAS) analysis — which measures how much "
                "SEC 10-K filings changed year-over-year and whether investors "
                "paid attention — produce a concise, professional narrative for "
                "an advisor. Each holding has a signal (sell, caution, hold, "
                "neutral, buy) with confidence and reasons. Explain which "
                "holdings need attention, why they received their signal, "
                "and summarize key themes. Always note that signals are "
                "based on filing analysis and are not investment advice. "
                "Keep the response under 500 words and always finish every "
                "sentence — never leave text incomplete."
            ),
        },
        {
            "role": "user",
            "content": f"Analyze this portfolio LAS data and produce a narrative:\n\n{prompt_data}",
        },
    ]

    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=1500,
    )

    return response.choices[0].message.content.strip()


def generate_explanation(portfolio: dict, high_impact: list[dict]) -> str:
    """Return a structured narrative — LLM if available, template otherwise."""
    return _llm_narrative(portfolio, high_impact)


# 4. Per-section change summary (LLM or template)

def summarize_section_change(
    ticker: str,
    section: str,
    snippet_old: str,
    snippet_new: str,
) -> dict:
    """Return ``{"summary": str, "is_template": bool}`` describing what changed."""
    if not snippet_old and not snippet_new:
        return {"summary": "No text available for comparison.", "is_template": True}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "summary": _template_section_summary(ticker, section, snippet_old, snippet_new),
            "is_template": True,
        }

    try:
        from openai import OpenAI
    except ImportError:
        return {
            "summary": _template_section_summary(ticker, section, snippet_old, snippet_new),
            "is_template": True,
        }

    client = OpenAI(api_key=api_key)
    pretty = section.replace("_", " ").title()
    messages = [
        {
            "role": "system",
            "content": (
                "You are a financial analyst assistant. Given old and new text "
                "from a specific section of an SEC 10-K filing, write a brief "
                "(2-4 sentence) plain-English summary of what materially changed. "
                "Focus on substance — new risks, removed disclosures, changed "
                "figures, product launches — not formatting differences."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Ticker: {ticker}\nSection: {pretty}\n\n"
                f"--- PRIOR YEAR ---\n{snippet_old}\n\n"
                f"--- CURRENT YEAR ---\n{snippet_new}"
            ),
        },
    ]

    try:
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=300,
        )
        return {
            "summary": response.choices[0].message.content.strip(),
            "is_template": False,
        }
    except Exception:
        return {
            "summary": _template_section_summary(ticker, section, snippet_old, snippet_new),
            "is_template": True,
        }


def _template_section_summary(
    ticker: str, section: str, snippet_old: str, snippet_new: str,
) -> str:
    pretty = section.replace("_", " ").title()
    if not snippet_old:
        return f"Prior-year text for {ticker} {pretty} is not available (re-run pipeline to capture it)."
    if not snippet_new:
        return f"Current-year text for {ticker} {pretty} is not available."
    return (
        f"The {pretty} section of {ticker}'s 10-K changed between filing periods. "
        f"Set OPENAI_API_KEY for an AI-generated summary of the differences."
    )


# CLI


def main():
    parser = argparse.ArgumentParser(description="Advisor portfolio LAS query")
    parser.add_argument(
        "--portfolio", required=True,
        help="Comma-separated tickers (e.g. AAPL,JPM,KO)",
    )
    parser.add_argument("--top", type=int, default=5, help="Top N high-impact sections")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of narrative")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.portfolio.split(",")]

    with LASStore() as db:
        portfolio = aggregate_las(tickers, db=db)
        high_impact = retrieve_high_impact_sections(tickers, top_n=args.top, db=db)

    narrative = generate_explanation(portfolio, high_impact)

    if args.json:
        output = {
            **portfolio,
            "high_impact_sections": high_impact,
            "narrative": narrative,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(narrative)


if __name__ == "__main__":
    main()
