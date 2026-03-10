"""
Attention proxy for the LazyPrices pipeline.

MVP PLACEHOLDER: returns a constant 0.5 for every filing.

The LazyPrices paper (Section IV) derives attention from SEC FOIA download
logs — the fraction of EDGAR users who fetched both the current and prior
10-K around the same time.  When FOIA data becomes available, replace the
placeholder logic below with the real computation.
"""


def get_attention_proxy(cik: int, accession: str) -> float:
    """
    Return an investor-attention proxy in [0, 1] for the given filing.

    Placeholder: constant 0.5 (neutral attention).
    """
    return 0.5
