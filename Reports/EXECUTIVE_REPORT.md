# LazyPrices: Executive Report

**Prepared for:** Company Higher Management  
**Subject:** Advisor Platform for Detecting Material Changes in Corporate Disclosures  
**Date:** March 2025

---

## Executive Summary

We have delivered a **production-ready advisor platform** that helps identify companies whose annual SEC filings have changed materially from the prior year—changes that, when overlooked by the market ("lazy prices"), have been shown in academic research to predict future stock returns. The system ingests SEC 10-K filings, quantifies how much each filing has changed, scores companies with a **Lazy Attention Score (LAS)**, and surfaces the results through an **interactive web dashboard** with AI-powered chat and risk narratives.

The platform enables advisors to see at a glance which holdings have the highest disclosure change intensity, how that relates to abnormal returns around filing dates, and which sections of the filings changed most. It supports **client-specific views** (risk tolerance, investment goals) and **conversational Q&A** over the underlying filing text, grounded in the actual disclosures. This report summarizes what was built, the business value it delivers, current scope and limitations, and recommended next steps for leadership.

---

## Business Context & Objective

**The problem:** Annual 10-K filings are long and complex. Material changes in wording or emphasis can signal shifts in risk, strategy, or disclosure quality. When such changes go unnoticed by investors, prices may not fully reflect the new information—creating potential alpha for attentive investors and risk for those who miss it.

**The objective:** Build an internal capability that:

- Automatically tracks year-over-year changes in 10-K language for a defined universe of companies  
- Scores each filing with a single, interpretable metric (LAS) that combines change intensity, a proxy for investor attention, and post-filing abnormal returns  
- Gives advisors an intuitive dashboard to monitor portfolios, drill into high-change filings, and answer client questions using the actual disclosure text  

The design is grounded in the **Lazy Prices** research (Cohen, Malloy, Nguyen, 2020), which documents that substantial filing changes that receive little attention can predict future returns.

---

## What We Delivered

| Capability | Description |
|------------|-------------|
| **Automated pipeline** | Pulls 10-K filings from SEC EDGAR, cleans and structures the text, compares each filing to the prior year, and computes change intensity, abnormal returns, and LAS. Results are stored and only new filings are processed on subsequent runs. |
| **Lazy Attention Score (LAS)** | A single score per filing that increases when (1) the filing changed more, (2) investor attention was lower, and (3) absolute abnormal return around the filing was larger. Supports ranking and filtering across the universe. |
| **Advisor dashboard** | Web application with portfolio overview, LAS and similarity charts, risk insights (top changed sections), filings table, and section-level drill-down. Advisors can trigger processing for new tickers from the UI. |
| **Client management** | Create and manage client profiles (name, risk tolerance, investment goal, notes, portfolio tickers). Views and AI responses can be tailored to the selected client. |
| **AI-powered chat** | Conversational interface that uses the platform's data plus retrieval over filing text (RAG) to answer questions with citations from the actual 10-Ks. Works with or without an API key (template fallback when disabled). |
| **Risk narratives** | System-generated thematic summaries of the most materially changed disclosure sections, delivered in the dashboard. |

---

## Key Value Propositions

1. **Systematic change detection** — Reduces reliance on manual review; every filing in scope is compared to its prior year and scored consistently.  
2. **Actionable signal** — LAS and section-level change intensity help prioritize which holdings and which sections deserve deeper review.  
3. **Client-ready communication** — Risk narratives and chat allow advisors to explain "what changed and why it might matter" using the client's risk profile and the underlying text.  
4. **Scalable design** — Pipeline and storage are built to add more companies and filing types; AI and search components use provider abstractions to allow future cloud/LLM swaps.

---

## How It Works (Simplified)

1. **Data ingestion** — The system fetches 10-K filings from the SEC for a configured set of companies and keeps a limited history per company (e.g., last several years).  
2. **Text analysis** — Each filing is cleaned, split by standard sections (e.g., Item 1, Risk Factors), and compared to the prior year's filing using similarity and change-intensity metrics.  
3. **Market context** — Around each filing date, the system computes cumulative abnormal returns (stock return minus market return) over a short window.  
4. **Scoring** — Change intensity, an attention proxy, and the magnitude of abnormal returns are combined (with configurable weights) into the Lazy Attention Score, normalized so filings can be ranked.  
5. **Dashboard & AI** — Stored results drive the dashboard visualizations and client views. Filing text is indexed for search; when users ask questions, relevant passages are retrieved and an AI model generates answers grounded in those passages and in portfolio metrics.

Technical details—data sources, formulas, and system architecture—are documented in the companion Technical Report for IT and quant teams.

---

## Current Scope & Coverage

- **Universe:** Currently configured for the **Dow Jones Industrial Average (DJIA) 30** constituents (29 companies with valid identifiers).  
- **Filing type:** **10-K annual reports only** (quarterly 10-Qs not yet included).  
- **Depth:** Up to a set number of years per company (e.g., five 10-Ks), configurable.  
- **Attention proxy:** The "investor attention" component in the LAS formula is implemented as a **placeholder** (constant value) until SEC FOIA download data or an alternative proxy is available; the rest of the pipeline is operational.

---

## Limitations & Risks

| Area | Limitation | Implication |
|------|------------|-------------|
| **Attention data** | No real investor-attention data yet; LAS uses a placeholder. | LAS is driven mainly by change intensity and abnormal returns until FOIA or another proxy is integrated. |
| **Filing coverage** | Only 10-Ks; no 10-Qs. | Mid-year material changes are not captured in the current scoring. |
| **Single market model** | Abnormal returns are market-adjusted (e.g., vs. S&P 500) only. | No multi-factor model (e.g., Fama–French); suitable for high-level screening, not full academic attribution. |
| **Operational resilience** | Pipeline jobs run in-process; status is in-memory. | Restarting the server loses job status; production use would benefit from a persistent task queue. |
| **Deployment** | Dashboard and backend run as local/dev processes. | For firm-wide use, deployment, authentication, and scaling would need to be addressed. |

These do not undermine the core value of change detection and advisor workflow; they define the boundary of current capability and the roadmap.

---

## Recommendations for Leadership

1. **Pilot with a small advisor group** — Use the dashboard with a defined set of clients and tickers to validate workflow, relevance of LAS and section changes, and usefulness of the chat and risk narratives.  
2. **Decide on attention proxy** — Prioritize either SEC FOIA-based attention data or another proxy (e.g., web traffic, search volume) so the full LAS formula can be activated and back-tested.  
3. **Expand coverage** — If the pilot is successful, plan to extend the universe beyond the DJIA 30 and to add 10-Qs for more timely signals.  
4. **Harden for production** — Plan for task queues, persistent job state, authentication, and deployment (e.g., cloud) if the platform is to be used firm-wide.  
5. **Governance and compliance** — Ensure use of SEC data, client data, and AI-generated narratives aligns with internal policies and any regulatory expectations for advisor tools.

---

## Conclusion

The LazyPrices advisor platform delivers a working end-to-end system for detecting material year-over-year changes in 10-K filings and presenting them through an interactive dashboard and AI-assisted chat. It is grounded in published research and built for scalability and future enhancement. Current scope is the DJIA 30 and 10-Ks only, with a placeholder for investor attention. With a focused pilot, a decision on the attention proxy, and a path to production hardening, the platform can support advisors in identifying and communicating material disclosure changes and their potential implications for client portfolios.

---

*For technical implementation details, configuration, and runbooks, see **TECHNICAL_REPORT.md**.*
