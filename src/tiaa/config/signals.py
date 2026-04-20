"""Signal thresholds and confidence bands for buy/sell/hold classification."""

# Signal thresholds for buy/sell/hold classification based on LAS components.
# Uses norm_change (rank percentile 0-1), raw attention_proxy, and raw CAR.
SIGNAL_THRESHOLDS = {
    "change_high": 0.70,           # rank percentile cutoff for "high" change
    "change_low": 0.30,            # rank percentile cutoff for "low" change
    "attention_low": 1.0,          # volume ratio below this = inattention
    "car_negative": -0.005,        # CAR below this = negative reaction
    "car_deep_negative": -0.015,   # deep selloff threshold for contrarian buy
}

# Confidence = |change_z| + |attention_z| + |CAR_z|; controls signal strength.
SIGNAL_CONFIDENCE = {
    "strong": 3.0,            # sum of |z| above this = strong recommendation
    "moderate": 1.5,          # between moderate and strong = standard recommendation
}

# High-importance sections that strengthen SELL/CAUTION when they drive the change.
SIGNAL_KEY_SECTIONS = {"item_1a", "item_7", "item_7a"}

# When both item_1a (Risk Factors) and item_7 (MD&A) exceed this threshold,
# the sell signal's change_high requirement is lowered by 0.10 (section boost).
SECTION_SELL_BOOST_THRESHOLD = 0.05
