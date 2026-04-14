# Next Steps & Recommendations

Derived from the Full S&P 500 backtest results (2,207 scored filings, 369 tickers).

---

## Phase 2: Immediate Priorities

### 1. Implement Proper Portfolio Construction
The current naive long/short-every-signal simulation chains trades multiplicatively, which destroys capital at scale regardless of signal quality. Replace it with a rank-based portfolio:

- **Rank-based selection**: Long the top 10% LAS stocks, short the bottom 10%
- **Monthly rebalancing**: Reconstitute the portfolio on the first trading day of each month
- **Volatility-scaled position sizing**: Size positions inversely to each stock's trailing 60-day volatility
- **Overlap handling**: Cap maximum concurrent positions; blend new signals into existing holdings
- **Transaction cost modeling**: Apply ~10bps round-trip to simulate real execution

Expected outcome: IC of +0.135 should translate into a realistic Sharpe of 0.5-1.0 after costs.

### 2. Run the Rank-Based Backtest
Once portfolio construction is implemented, re-run the backtest using the 2,207 filings with monthly rebalancing. This should produce positive, defensible performance metrics that match what a real quant fund would trade.

---

## Phase 3: Short-Term Improvements

### 3. Separate 10-K and 10-Q Analysis
The current dataset mixes annual (10-K) and quarterly (10-Q) filings. The LazyPrices paper focused exclusively on 10-K. Isolating annual filings would:
- Give a cleaner comparison to the paper
- Remove quarterly seasonality noise
- Align signal horizons with fundamental reporting cycles

Requires a schema migration (add `form_type` column to filings table).

### 4. Fix Remaining Data Gaps
73 tickers still have 0 scored filings due to Yahoo Finance API failures. Sequential retries (1 worker) recovered most of our original problem tickers.

**Action:** Run a pass of `--skip-pull --force --workers 1` for the 73 zero-coverage tickers. This should push coverage from 369 to ~420+ tickers.

### 5. Sector-Neutral Portfolio Construction
Current results are sector-agnostic. A portfolio that goes long/short *within* each sector would isolate stock-specific alpha from sector drift. Should improve risk-adjusted returns.

---

## Phase 4: Long-Term Research

### 6. Walk-Forward Validation
The current backtest uses all 2015-2026 data simultaneously — potential for look-ahead bias in parameter tuning. A rolling window (train on 3 years, test on 1 year, slide forward) would give a realistic view of live-trading performance.

### 7. Sector-Specific Thresholds
Signal classification rules may need per-sector tuning:
- Financial companies have structurally different filing patterns than tech
- Regulated industries (utilities, healthcare) have mandated disclosures that behave differently than discretionary disclosures

Action: Backtest per-sector thresholds using the sector metadata already in `config.TICKER_SECTOR_INDUSTRY`.

### 8. Machine Learning Overlay
Replace the rule-based signal classifier with a trained model that learns non-linear interactions between change, attention, and CAR. Use the 2,207 scored filings as training data. Candidates:
- Gradient boosting (XGBoost/LightGBM) for tabular data
- Could incorporate text embeddings directly rather than collapsing to `change_intensity`

### 9. Sell Signal Tuning
Current sell signal at 90d has only ~48% hit rate with near-zero mean return — it adds no value. Options:
- Tighten thresholds (require stronger evidence)
- Merge sell into caution entirely

### 10. Text Embeddings Instead of TF-IDF
Current `change_intensity` uses cosine similarity on bag-of-words. Modern embedding models (e.g., SentenceTransformers, OpenAI embeddings) would capture semantic change better than word overlap. Could significantly improve the core predictive factor.

---

## Priority Ordering

**Must-do before client presentation:**
1. Portfolio construction (#1) — without this, the headline numbers look catastrophic

**Should-do for credibility:**
2. Separate 10-K analysis (#3) — the paper was 10-K only, so should ours
3. Fix data gaps (#4) — 420+ tickers is more defensible than 369

**Nice-to-have for next round:**
4. Walk-forward validation (#6)
5. Sector-specific thresholds (#7)
6. ML overlay (#8)
