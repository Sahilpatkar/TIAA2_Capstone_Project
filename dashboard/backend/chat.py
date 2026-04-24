"""
Chat-with-data service for the LazyPrices dashboard.

When RAG is enabled (config.RAG_ENABLED), the user's query is embedded
and matched against indexed 10-K filing chunks.  Retrieved passages are
injected alongside the structured portfolio metrics before calling the LLM.

Falls back to a template-based answer when no API key is configured or
when the required packages are missing.
"""

import json
import os
import re

from tiaa import config
from tiaa.storage.store import LASStore
from tiaa.advisor.query import aggregate_las, retrieve_high_impact_sections

_SYSTEM_PROMPT = (
    "You are a financial advisor assistant with expertise in SEC filings analysis. "
    "You have access to the Lazy Prices framework, which measures how much a company's "
    "10-K annual filing changed year-over-year (change intensity), whether investors "
    "paid attention (attention proxy), and the stock's abnormal return around the filing "
    "date (CAR). These are combined into a Lazy Attention Score (LAS).\n\n"
    "When answering questions:\n"
    "- Be concise and professional\n"
    "- Reference specific data points from the context provided\n"
    "- When citing filing text, mention the ticker, section, and report date\n"
    "- Explain what the metrics mean in practical terms for an advisor\n"
    "- If the data doesn't cover something, say so clearly\n"
    "- When the user asks for filing excerpts or detailed text, quote the retrieved "
    "passages verbatim and cite them with [ticker | section | report_date]. "
    "If the retrieved excerpts don't cover what was asked, say so explicitly.\n"
)


# ------------------------------------------------------------------
# Structured context (portfolio metrics — same as before)
# ------------------------------------------------------------------

def _build_context(tickers: list[str]) -> str:
    """Load portfolio and section data, return as a formatted context string."""
    if not tickers:
        db = LASStore()
        try:
            df = db.get_all_filings()
            if df.empty:
                return "No filing data is available in the database."
            tickers = sorted(df["ticker"].dropna().unique().tolist())
        finally:
            db.close()

    db = LASStore()
    try:
        portfolio = aggregate_las(tickers, db=db)
        sections = retrieve_high_impact_sections(tickers, top_n=5, db=db)

        df = db.get_filings_by_tickers(tickers)
        filings_data = []
        if not df.empty:
            for _, row in df.iterrows():
                filings_data.append({
                    "ticker": row.get("ticker"),
                    "entity_name": row.get("entity_name"),
                    "report_date": row.get("report_date"),
                    "filed_date": row.get("filed_date"),
                    "similarity_cosine": row.get("similarity_cosine"),
                    "similarity_jaccard": row.get("similarity_jaccard"),
                    "change_intensity": row.get("change_intensity"),
                    "car": row.get("car"),
                    "las": row.get("las"),
                })

        context = {
            "portfolio_summary": portfolio,
            "all_filings": filings_data,
            "top_changed_sections": sections,
        }
        return json.dumps(context, indent=2, default=str)
    finally:
        db.close()


# ------------------------------------------------------------------
# RAG retrieval
# ------------------------------------------------------------------

# Each entry maps a regex to one section_key OR a tuple of keys when the
# topic commonly spans multiple Items (e.g. banks put interest-rate-risk
# content in MD&A with only a redirect stub in 7A).
_SECTION_KEYWORD_MAP = [
    (r"\brisk\s*factors?\b", "item_1a"),
    (r"\b(cyber|cybersecurity|cyber\s+security)\b", "item_1c"),
    (r"\bproperties\b", "item_2"),
    (r"\blegal\s+proceedings?\b", "item_3"),
    (r"\bmine\s+safety\b", "item_4"),
    (r"\b(md&a|management('?s)?\s+discussion)\b", "item_7"),
    (
        r"\b(market\s+risk|interest\s+rate\s+risk|quantitative\s+(and\s+qualitative\s+)?(disclosures?\s+)?(about\s+)?market\s+risk)\b",
        ("item_7a", "item_7"),
    ),
    (r"\bfinancial\s+statements?\b", "item_8"),
    (r"\bcontrols?\s+(and\s+)?procedures?\b", "item_9a"),
    (r"\bexecutive\s+compensation\b", "item_11"),
    (r"\bbusiness\s+overview\b", "item_1"),
]


def _infer_section_keys(query: str) -> list[str]:
    """Detect explicit 'Item X' references or topic keywords in a user query.

    Returns a list of normalized section_key values (e.g. 'item_1a'). Handles
    'Item 1A', 'Item 1 A', 'item1a', plus keyword aliases like 'risk factors'.
    """
    keys: list[str] = []
    for m in re.finditer(r"\bitem\s*(\d{1,2})\s*([a-z])?\b", query, re.IGNORECASE):
        num = m.group(1)
        letter = (m.group(2) or "").lower()
        keys.append(f"item_{num}{letter}")
    for pattern, value in _SECTION_KEYWORD_MAP:
        if not re.search(pattern, query, re.IGNORECASE):
            continue
        candidates = (value,) if isinstance(value, str) else tuple(value)
        for key in candidates:
            if key not in keys:
                keys.append(key)
    return keys


def _build_retrieval_query(message: str, history: list[dict]) -> str:
    """Concatenate recent user turns so follow-ups retrieve the right chunks."""
    recent_user_turns = [
        h.get("content", "") for h in history[-6:]
        if h.get("role") == "user" and h.get("content")
    ]
    parts = recent_user_turns[-2:] + [message]
    return "\n".join(p for p in parts if p)


def _retrieve_rag_context(query: str, tickers: list[str]) -> str:
    """Embed the query and retrieve relevant filing chunks from the vector store."""
    try:
        from tiaa.rag.providers import get_embedding_provider, get_vector_store
    except ImportError:
        return ""

    try:
        embedder = get_embedding_provider()
        store = get_vector_store()

        if store.count() == 0:
            return ""

        query_embedding = embedder.embed([query])[0]

        section_keys = _infer_section_keys(query)

        def _section_clause() -> dict | None:
            if not section_keys:
                return None
            if len(section_keys) == 1:
                return {"section_key": section_keys[0]}
            return {"section_key": {"$in": section_keys}}

        top_k = getattr(config, "RAG_TOP_K", 5)
        # Exclude boilerplate redirect stubs:
        #   - 10-Q Item 1A: "Refer to Part I, Item 1A..."
        #   - Item 7A market-risk pointers: "Refer to the Market Risk Management section..."
        where_document = {
            "$and": [
                {"$not_contains": "Refer to Part I, Item 1A"},
                {"$not_contains": "Refer to the Market Risk Management"},
            ]
        }

        def _search(where_filter: dict | None, k: int) -> list:
            try:
                return store.search(
                    query_embedding=query_embedding,
                    top_k=k,
                    where=where_filter,
                    where_document=where_document,
                )
            except TypeError:
                return store.search(
                    query_embedding=query_embedding,
                    top_k=k,
                    where=where_filter,
                )

        def _build_where(ticker_clause: dict | None) -> dict | None:
            clauses = [c for c in (ticker_clause, _section_clause()) if c is not None]
            if not clauses:
                return None
            if len(clauses) == 1:
                return clauses[0]
            return {"$and": clauses}

        def _pick_preferring_latest(pool: list, k: int) -> list:
            """Prefer chunks from the most recent report_date; top up from older
            filings only if the latest doesn't have enough substantive matches.
            Keeps semantic-similarity order within each date bucket.
            """
            if not pool:
                return []
            dated = [r for r in pool if r.get("metadata", {}).get("report_date")]
            if not dated:
                return pool[:k]
            latest_date = max(r["metadata"]["report_date"] for r in dated)
            latest = [r for r in pool if r.get("metadata", {}).get("report_date") == latest_date]
            if len(latest) >= k:
                return latest[:k]
            older = [r for r in pool if r not in latest]
            return (latest + older)[:k]

        # Per-ticker retrieval when multiple tickers are selected, so each gets
        # fair representation even if one has semantically "louder" content.
        if tickers and len(tickers) > 1:
            per_ticker_k = max(2, -(-top_k // len(tickers)))  # ceil division
            per_ticker_lists: list[list] = []
            for t in tickers:
                # Wider pool so the latest filing has a real chance to supply k chunks.
                t_results = _search(_build_where({"ticker": t}), per_ticker_k * 8)
                t_substantive = [r for r in t_results if len(r.get("document", "")) >= 600]
                pool = t_substantive or t_results
                per_ticker_lists.append(_pick_preferring_latest(pool, per_ticker_k))

            # Round-robin interleave so passages alternate across tickers.
            results = []
            for i in range(max((len(lst) for lst in per_ticker_lists), default=0)):
                for lst in per_ticker_lists:
                    if i < len(lst):
                        results.append(lst[i])
            results = results[: top_k * len(tickers)]
        else:
            ticker_clause = {"ticker": tickers[0]} if tickers else None
            results = _search(_build_where(ticker_clause), top_k * 8)
            substantive = [r for r in results if len(r.get("document", "")) >= 600]
            pool = substantive or results
            results = _pick_preferring_latest(pool, top_k)

        if not results:
            return ""

        passages: list[str] = []
        for r in results:
            meta = r.get("metadata", {})
            header = (
                f"[{meta.get('ticker', '?')} | "
                f"{meta.get('section_label', meta.get('section_key', '?'))} | "
                f"{meta.get('report_date', '?')}]"
            )
            text = r.get("document", "")
            passages.append(f"{header}\n{text}")

        return "\n\n---\n\n".join(passages)

    except Exception as e:
        print(f"[RAG retrieval error] {e}")
        return ""


# ------------------------------------------------------------------
# Template fallback
# ------------------------------------------------------------------

def _template_response(message: str, tickers: list[str]) -> str:
    """Generate a template-based response without an LLM."""
    context_str = _build_context(tickers)
    try:
        context = json.loads(context_str)
    except (json.JSONDecodeError, TypeError):
        return "I don't have enough data to answer that question."

    portfolio = context.get("portfolio_summary", {})
    filings = context.get("all_filings", [])
    sections = context.get("top_changed_sections", [])

    lines = []
    lines.append("[Template mode - set OPENAI_API_KEY for AI-powered responses]\n")

    plas = portfolio.get("portfolio_las")
    if plas is not None:
        lines.append(f"Portfolio LAS: {plas:.4f}")
    else:
        lines.append("Portfolio LAS: No scored holdings")

    if portfolio.get("holdings"):
        lines.append("\nHoldings (by LAS):")
        for h in portfolio["holdings"]:
            las_str = f"{h['las']:.4f}" if h.get("las") is not None else "N/A"
            ci_str = f"{h['change_intensity']:.4f}" if h.get("change_intensity") is not None else "N/A"
            car_str = f"{h['car']:.4f}" if h.get("car") is not None else "N/A"
            lines.append(f"  {h['ticker']}: LAS={las_str}, Change={ci_str}, CAR={car_str}")

    if sections:
        lines.append("\nTop changed sections:")
        for s in sections[:5]:
            ci = s.get("change_intensity")
            ci_str = f"{ci:.4f}" if ci is not None else "N/A"
            lines.append(f"  [{s.get('ticker')}] {s.get('section')} - change intensity: {ci_str}")

    if filings:
        lines.append(f"\nTotal filings in view: {len(filings)}")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Main chat handler
# ------------------------------------------------------------------

def handle_chat(
    message: str,
    tickers: list[str],
    history: list[dict],
    client_name: str | None = None,
    risk_tolerance: str | None = None,
) -> tuple[str, bool]:
    """
    Process a chat message and return (response_text, is_template).

    When RAG is enabled and the vector store is populated, relevant filing
    text chunks are retrieved and injected as additional context.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _template_response(message, tickers), True

    try:
        from tiaa.rag.providers import get_llm_provider
    except ImportError:
        return _template_response(message, tickers), True

    structured_context = _build_context(tickers)

    rag_context = ""
    rag_enabled = getattr(config, "RAG_ENABLED", False)
    if rag_enabled:
        retrieval_query = _build_retrieval_query(message, history)
        rag_context = _retrieve_rag_context(retrieval_query, tickers)

    client_preamble = ""
    if client_name:
        client_preamble = f"You are currently advising client: {client_name}."
        if risk_tolerance:
            client_preamble += f" Their risk tolerance is {risk_tolerance}."
        client_preamble += " Tailor your responses accordingly.\n\n"

    messages = [
        {"role": "system", "content": client_preamble + _SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                "Here is the structured portfolio data (metrics, scores, filings):\n\n"
                + structured_context
            ),
        },
    ]

    if rag_context:
        messages.append({
            "role": "system",
            "content": (
                "Here are relevant excerpts from the actual 10-K filing text, "
                "retrieved based on the user's question. Use these to provide "
                "specific, grounded answers:\n\n" + rag_context
            ),
        })

    for h in history[-10:]:
        role = h.get("role", "user")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": h.get("content", "")})

    messages.append({"role": "user", "content": message})

    try:
        llm = get_llm_provider()
        response_text = llm.chat(messages, temperature=0.3, max_tokens=1000)
        return response_text, False
    except Exception as e:
        fallback = _template_response(message, tickers)
        return f"{fallback}\n\n[LLM error: {e}]", True
