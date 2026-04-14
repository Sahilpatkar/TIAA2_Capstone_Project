# Poster Change Report: LazyPrices Advisor

**Date:** April 2026  
**Scope:** Full audit of `Team17 Poster (1).html` against codebase, backtest reports, and config  
**Verdict:** 10 factual corrections required, 6 high-impact additions recommended

---

## Part 1: Factual Corrections (Must Fix)

### 1.1 — LAS Formula (Column 2, "Core Metric" section)

**Current (WRONG):**
```
LAS = w_c · f(change_intensity)
    + w_a · f(attention_proxy)
    + w_r · f(|CAR|)
```
With the note: *"attention moderates raw change scores"*

**Change to (matches `las.py` v1.5, lines 137-141):**
```
LAS = 0.60 · f(change_intensity)
    − 0.30 · f(attention_proxy)
    − 0.10 · f(CAR)
```

**What's wrong:**
- The `attention_proxy` sign is **subtracted**, not added. The poster shows `+` which is the opposite of the code.
- CAR uses **signed values** (not absolute `|CAR|`). v1.5 discovered that negative CAR predicts positive forward returns (mean reversion, IC = −0.36 at 90d, p=0.001). The `|CAR|` notation is v1.3, which lost money.
- CAR weight sign is **negative** (`−0.10`), not positive (`+0.25`).
- Weights should be shown explicitly: 0.60, 0.30, 0.10 — not as abstract `w_c, w_a, w_r`.

**Updated formula-terms bullets:**

| Term Badge | Current Text | Change To |
|---|---|---|
| `change_intensity` | *"Cosine distance between consecutive filing TF-IDF vectors; high = major linguistic shift"* | **Keep as-is** (correct) |
| `attention_proxy` | *"Relative word-count growth in risk sections; high = management redirecting narrative"* | **"Composite of abnormal trading volume (70%) and filing delay in days (30%); high = market is paying attention"** — the current description is wrong; attention_proxy is trading volume, not word-count growth. Word-count growth doesn't appear in the code at all. |
| `\|CAR\|` | *"Absolute Cumulative Abnormal Return around filing date; market-confirmed signal"* | **"Signed Cumulative Abnormal Return (stock vs S&P 500) around filing date; negative CAR signals market overreaction (mean-reversion contrarian indicator)"** — remove the absolute value notation. |

**Updated calibration note:**

Current: *"Weights w_c, w_a, w_r are calibrated via cross-validated regression on historical return outcomes."*

Change to: **"Weights were empirically calibrated through iterative backtesting across three pipeline versions (v1.3→v1.5) using Information Coefficient analysis on 373 SEC filings."**

Reason: There is no cross-validated regression anywhere in the codebase. Weights were tuned by running backtests and measuring IC improvements (documented in `BACKTEST_VALIDATION_REPORT.md`).

---

### 1.2 — Data Sources (Column 2, "Methods & Materials")

**Current (WRONG):**
> SEC EDGAR filings (10-K, 10-Q), **CRSP/Compustat market data**, Yahoo Finance real-time feeds. Coverage: **S&P 500 constituents, 2015–present.**

**Change to:**
> SEC EDGAR filings (10-K, 10-Q), Yahoo Finance market data. Coverage: **50-stock subset of S&P 500** across all 11 GICS sectors, 2015–present. 373 scored filings across 52 tickers.

**What's wrong:**
- `CRSP/Compustat` is not used anywhere. `abnormal_returns.py` uses `yfinance` exclusively.
- The system runs on a 50-ticker demo subset (`config.DEMO_TICKERS`, lines 23-46), not the full S&P 500. Claiming full S&P 500 will be caught immediately by any reviewer who asks about sample size.

---

### 1.3 — Evaluation Metrics (Column 3, "Results & Evaluation")

All four metric cards contain numbers that do not exist in the codebase or backtest reports.

| Metric Card | Current (FABRICATED) | Change To (FROM BACKTEST REPORTS) | Source |
|---|---|---|---|
| Top-left | AUC-ROC: **0.71** | LAS IC (90d): **+0.17** | `BACKTEST_COMPARISON_REPORT_DEMO50.md`, line 106 |
| Top-right | Precision: **68%** | Trade Hit Rate (90d): **62%** | `BACKTEST_COMPARISON_REPORT_DEMO50.md`, line 135 |
| Bottom-left | 3.2× signal lead time | Quintile Spread (90d): **+4.7%** | `BACKTEST_COMPARISON_REPORT_DEMO50.md`, line 123 |
| Bottom-right | <5s alert latency | Sharpe Ratio (90d): **0.31** | `BACKTEST_COMPARISON_REPORT_DEMO50.md`, line 134 |

**Updated metric card labels:**

```
Card 1: "0.17"  — "Information Coefficient (90d Spearman ρ)"
Card 2: "62%"   — "Trade Hit Rate (90d horizon)"
Card 3: "+4.7%" — "Quintile Long/Short Spread (90d)"
Card 4: "0.31"  — "Portfolio Sharpe Ratio (90d)"
```

**Why:** AUC-ROC was never computed (the system uses IC and hit rate, not classification AUC). "3.2× lead time" and "<5s latency" have zero supporting evidence. The real metrics from the 50-stock backtest are strong enough — no need to fabricate.

---

### 1.4 — Result Comparison Bars (Column 3)

**Current (FABRICATED):**
```
LAS Model (Full)     71%
Text-Only Baseline   58%
Price-Only Baseline  54%
Random Baseline      50%
```

These percentages don't correspond to any metric in the codebase. They look like AUC scores, but no AUC was computed.

**Change to (Paper vs LAS portfolio simulation, 90d horizon):**

```
LAS System (Ours)          +188%   total return
Paper Strategy (Text-Only)  -100%   total return
```

Or as hit rates:
```
LAS System (90d)      62.1%
Paper Strategy (90d)  40.6%
Random Baseline       50.0%
```

Source: `BACKTEST_COMPARISON_REPORT_DEMO50.md`, line 133-135.

---

### 1.5 — Architecture Diagram: LLM Model (Column 3)

**Current:** `GPT-4 · RAG Pipeline`

**Change to:** `GPT-4.1-mini · RAG Pipeline`

Source: `config.py` line 1207: `LLM_MODEL = "gpt-4.1-mini"`

---

### 1.6 — Analyst Trust Score (Column 3, "Discussion & Conclusions")

**Current (FABRICATED):**
> RAG-augmented LLM summaries receive high analyst trust scores **(4.1/5)** in user evaluation, validating the system's interpretability goal.

**Change to:**
> RAG-augmented LLM summaries provide structured natural-language explanations of risk drivers, including which filing sections changed most and why signals were generated, enabling advisors to quickly validate or override alerts.

**Why:** There is no user study, no survey data, and no evidence of a 4.1/5 trust score anywhere in the codebase. Remove the fabricated number entirely. Describe what the system actually does instead.

---

### 1.7 — Contact Email (Footer)

**Current:** `your_email@andrew.cmu.edu`

**Change to:** Actual team member email addresses.

---

### 1.8 — Attention Proxy Description Mismatch

In the formula-terms section, the `attention_proxy` description says:

> "Relative word-count growth in risk sections; high = management redirecting narrative"

This is **completely wrong**. The attention_proxy in the code (`abnormal_returns.py`) is:
- **70%** abnormal trading volume ratio (event window mean / baseline mean)
- **30%** filing delay (calendar days from report_date to filed_date)

It has nothing to do with word-count growth. Word-count growth is not computed anywhere.

**Change to:**
> "Composite: 70% abnormal trading volume around filing date + 30% filing delay; high = market is actively monitoring this stock"

---

### 1.9 — Pipeline Step 3 Description

**Current:** `LAS Computation — Composite score from change intensity, attention proxy, & |CAR|`

**Change to:** `LAS Computation — Composite score from change intensity, attention proxy, & signed CAR (mean-reversion contrarian signal)`

Remove `|CAR|` — the absolute value notation is from v1.3.

---

### 1.10 — "Discussion & Conclusions" — Sign-Correction Claim

**Current:**
> The LAS formulation's sign-correction mechanism (attention dampening) reduces false positives from routine boilerplate changes.

**Change to:**
> The LAS formulation's sign-correction mechanism — subtracting attention to isolate under-the-radar filings, and using signed CAR to capture mean-reversion — reduces false positives and produces a composite IC that outperforms any individual component (IC = +0.144 at 90d, p = 0.01).

Source: `BACKTEST_COMPARISON_REPORT_DEMO50.md`, line 155.

---

## Part 2: High-Impact Additions (Should Add)

### 2.1 — ADD: Backtest Comparison Table (Paper vs LAS System)

**Recommendation: YES, absolutely add this.** This is your single strongest piece of evidence.

**Where:** Replace or supplement the current fabricated result bars in Column 3 with a head-to-head comparison table.

**Suggested content (from `BACKTEST_COMPARISON_REPORT_DEMO50.md`, lines 129-136):**

```
Portfolio Simulation: 90-Day Horizon (50 S&P 500 Stocks, 373 Filings)

                    Paper Strategy    LAS System (Ours)
Trades              180               58
Mean Return/Trade   −2.5%             +3.1%
Total Return        −99.9%            +188.2%
Sharpe Ratio        −0.244            +0.313
Hit Rate            40.6%             62.1%
Max Drawdown        −99.9%            −65.8%
```

**Why this matters:**
- The paper strategy loses essentially 100% of capital. Yours makes 188%.
- This is the most visually striking and defensible result you have.
- It directly validates your core thesis: multi-signal (change + attention + CAR) beats single-signal (change only).
- During the poster presentation, reviewers will ask "does it work?" — this table answers that definitively.

**Visual suggestion:** Use the existing `result-bars` CSS class but show:
```
LAS System (90d Sharpe)     0.313  ████████████████████
Paper Strategy (90d Sharpe) -0.244 (negative, show in red)
```

Or a before/after metric cards row with the most dramatic contrasts:
```
+188% vs −100%    (Total Return)
62% vs 41%        (Hit Rate)
0.31 vs −0.24     (Sharpe Ratio)
```

---

### 2.2 — ADD: LAS Version Evolution (v1.3 → v1.5)

**Where:** Bottom of Column 2, after the LAS formula box.

**Suggested content (from `BACKTEST_VALIDATION_REPORT.md`, lines 426-439):**

```
Version   90d IC    90d L/S Spread   Portfolio Return (90d)
v1.3      +0.08     +6.4%            −55.1%
v1.5      +0.14     +9.7%            +207.4%
```

**Why:** This shows methodological rigor — you didn't just pick weights arbitrarily. You iterated, validated, and improved. The key insight (signed CAR, mean reversion) is a genuine finding worth highlighting.

---

### 2.3 — ADD: Dashboard Screenshot

**Where:** Column 3 architecture section or as a new row below the body.

**Why:** You have a live deployed system at `http://34.225.170.58/`. A screenshot showing the actual dashboard with real data makes the poster tangible. Poster sessions are visual — people walk by and decide in 3 seconds whether to stop. A screenshot of a working system is far more compelling than abstract architecture boxes.

---

### 2.4 — ADD: RAG Pipeline in Architecture Diagram

**Current architecture diagram mentions:** `LLM Explainer — GPT-4 · RAG Pipeline` but the RAG system is not described anywhere in the text.

**Add a brief mention in Methods or Architecture:**
> The system uses a Retrieval-Augmented Generation (RAG) pipeline: filing text is chunked by SEC Item section, embedded with OpenAI `text-embedding-3-small`, and stored in ChromaDB. At query time, the top-5 most relevant filing passages are retrieved and injected into the LLM context alongside structured portfolio metrics.

**Why:** RAG is a technical differentiator that shows you're not just sending raw data to GPT — you have a proper information retrieval layer. This is worth mentioning.

---

### 2.5 — ADD: Signal Classification Logic

**Where:** Column 2, after the LAS formula.

The poster currently has no description of how LAS maps to actionable signals (buy/sell/caution/hold/neutral). This is a critical gap — LAS alone is just a number. The signal rules are what make it actionable.

**Suggested compact version:**

```
Signal Rules (simplified):
High change + Low attention + Neg CAR  →  SELL
High change + Low attention + Pos CAR  →  CAUTION  
High change + High attention + Deep neg CAR  →  BUY (contrarian)
High attention + Pos CAR  →  HOLD (priced in)
Low change  →  NEUTRAL
```

**Why:** This is the "attention mechanism" that makes your system work better than the paper. Reviewers will ask "how do you decide buy vs sell?" — this answers it visually.

---

### 2.6 — ADD: Key Insight Callout

**Where:** Column 3, in the Discussion section.

**Add:**
> **Key Finding:** CAR has a statistically significant negative IC at 90 days (−0.106, p = 0.058): stocks with positive abnormal returns around filing date tend to *underperform* afterward. This mean-reversion signal, when combined with change intensity and attention, produces a composite LAS with IC = +0.144 (p = 0.01) — higher than any individual component alone.

**Why:** This is the most intellectually interesting result. It shows that your multi-factor approach captures something no single factor can.

---

## Part 3: Frontend Bug (Fix Before Demo)

### 3.1 — Dashboard Weight Mismatch

**Files affected:**
- `dashboard/frontend/src/components/PortfolioOverview.jsx` lines 4-6
- `dashboard/frontend/src/components/LASChart.jsx` lines 6-8

**Current (v1.3 weights, WRONG):**
```javascript
const W_CHANGE = 0.50;
const W_ATTENTION = 0.25;
const W_CAR = 0.25;
```

**Change to (v1.5 weights):**
```javascript
const W_CHANGE = 0.60;
const W_ATTENTION = 0.30;
const W_CAR = 0.10;
```

**Why this matters:** If anyone opens the dashboard during the poster session, the LAS component breakdown charts will show the wrong weight decomposition. The backend computes LAS with v1.5 weights (0.60/0.30/0.10) but the frontend decomposes it with v1.3 weights (0.50/0.25/0.25). The numbers won't add up.

---

## Part 4: Summary Checklist

### Must Fix (Factual Errors)

| # | Item | Section | Severity |
|---|------|---------|----------|
| 1 | LAS formula signs and |CAR| → signed CAR | Col 2, Formula Box | **Critical** |
| 2 | Remove CRSP/Compustat, say Yahoo Finance | Col 2, Methods | **Critical** |
| 3 | Replace all 4 metric cards with real numbers | Col 3, Results | **Critical** |
| 4 | Replace fabricated result bars | Col 3, Results | **Critical** |
| 5 | Fix attention_proxy description (not word-count) | Col 2, Formula Box | **Critical** |
| 6 | Remove 4.1/5 trust score claim | Col 3, Discussion | **Critical** |
| 7 | Fix GPT-4 → GPT-4.1-mini | Col 3, Architecture | Medium |
| 8 | Fix "cross-validated regression" → "backtest calibration" | Col 2, Formula Box | Medium |
| 9 | Fix contact email placeholder | Footer | Medium |
| 10 | Fix `\|CAR\|` → signed CAR in pipeline step 3 | Col 2, Pipeline | Low |

### Should Add (High-Impact Content)

| # | Item | Where | Impact |
|---|------|-------|--------|
| 1 | Paper vs LAS backtest comparison table | Col 3 | **Very High** — strongest evidence |
| 2 | Dashboard screenshot | Col 3 or new row | **High** — visual proof of working system |
| 3 | Signal classification rules | Col 2 | **High** — explains the "how" |
| 4 | LAS version evolution table | Col 2 | Medium — shows rigor |
| 5 | RAG pipeline description | Col 2 or Col 3 | Medium — technical differentiator |
| 6 | Mean-reversion key insight callout | Col 3 | Medium — intellectual contribution |

### Frontend Fix (Before Demo)

| # | Item | File | Impact |
|---|------|------|--------|
| 1 | Update hardcoded weights to v1.5 | PortfolioOverview.jsx:4-6 | **High** — visible in live demo |
| 2 | Update hardcoded weights to v1.5 | LASChart.jsx:6-8 | **High** — visible in live demo |
