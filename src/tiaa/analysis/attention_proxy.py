"""
Attention proxy for the LazyPrices pipeline.

Uses abnormal trading volume around the 10-K filing date as a proxy for
investor attention.  A ratio > 1 means above-normal volume (high attention);
< 1 means below-normal (low attention / distraction).

The raw volume ratio is returned here; cross-sectional normalisation
(rank percentile or z-score) is applied later inside las.py.
"""

from tiaa.analysis.abnormal_returns import compute_volume_ratio


def get_attention_proxy(ticker: str, filed_date: str) -> float | None:
    """
    Return an investor-attention proxy for the given filing.

    Computes the ratio of mean daily trading volume during the event window
    to the trailing baseline mean volume.  Returns None when market data is
    unavailable.
    """
    return compute_volume_ratio(ticker, filed_date)
