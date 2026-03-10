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
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import config  # noqa: E402
from store import LASStore  # noqa: E402
from advisor_query import aggregate_las, retrieve_high_impact_sections  # noqa: E402

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

def _retrieve_rag_context(query: str, tickers: list[str]) -> str:
    """Embed the query and retrieve relevant filing chunks from the vector store."""
    try:
        from rag.providers import get_embedding_provider, get_vector_store
    except ImportError:
        return ""

    try:
        embedder = get_embedding_provider()
        store = get_vector_store()

        if store.count() == 0:
            return ""

        query_embedding = embedder.embed([query])[0]

        where_filter = None
        if tickers and len(tickers) == 1:
            where_filter = {"ticker": tickers[0]}
        elif tickers and len(tickers) > 1:
            where_filter = {"ticker": {"$in": tickers}}

        top_k = getattr(config, "RAG_TOP_K", 5)
        results = store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            where=where_filter,
        )

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
            if len(text) > 1500:
                text = text[:1500] + "..."
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
        from rag.providers import get_llm_provider
    except ImportError:
        return _template_response(message, tickers), True

    structured_context = _build_context(tickers)

    rag_context = ""
    rag_enabled = getattr(config, "RAG_ENABLED", False)
    if rag_enabled:
        rag_context = _retrieve_rag_context(message, tickers)

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
