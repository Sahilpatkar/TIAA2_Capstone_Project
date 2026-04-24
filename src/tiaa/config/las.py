"""CAR event window, volume baselines, attention weights, and LAS formula."""

# CAR (Cumulative Abnormal Return) event window, trading days relative to filed_date.
CAR_WINDOW = (-1, 5)
MARKET_TICKER = "^GSPC"  # S&P 500 as market proxy
CAR_BUFFER_DAYS = 30     # calendar-day buffer when fetching price data

VOLUME_BASELINE_DAYS = 60  # trailing trading days for baseline average volume
VOLUME_BASELINE_GAP = 5    # trading-day gap before event window to avoid leakage

# Composite attention proxy weights (volume ratio + filing delay).
# Filing delay = calendar days from report_date to filed_date.
# Late filers signal lower attention / quality.
ATTENTION_COMPOSITE_WEIGHTS = {
    "volume_ratio": 0.7,
    "filing_delay": 0.3,
}

# LAS = w_change * f(change) - w_attention * f(attn) - w_car * f(car)
LAS_WEIGHTS = {
    "w_change": 0.60,
    "w_attention": 0.30,
    "w_car": 0.10,
}

# "rank" (cross-sectional rank percentile) or "zscore"
LAS_NORMALIZATION = "rank"
