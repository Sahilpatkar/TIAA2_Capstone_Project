"""Back-compat facade for the config package.

Existing callers do ``from tiaa import config`` and access ``config.FOO`` for
any setting in the repo. Preserve that surface by re-exporting every public
name from the domain submodules here. New code can import directly from
the submodule, e.g. ``from tiaa.config.paths import DB_PATH``.
"""

from tiaa.config.paths import (
    PROJECT_ROOT,
    DATA_DIR,
    FILINGS_DIR,
    VECTORS_DIR,
    DB_PATH,
    DATABASE_URL,
)
from tiaa.config.sec import (
    FILING_TYPES,
    MAX_FILINGS_PER_CIK,
    UNIVERSE_MODE,
    DEMO_TICKERS,
    CIK_TO_TICKER,
    TICKER_TO_CIK,
    FULL_TICKER_TO_CIK,
    TICKER_SECTOR_INDUSTRY,
    _CIK_TO_TICKER_FULL,
)
from tiaa.config.features import (
    ITEM_SECTIONS,
    SECTION_WEIGHTS,
    ITEM_SECTIONS_10Q,
    SECTION_WEIGHTS_10Q,
    SIMILARITY_MEASURES,
    NUMERIC_TABLE_THRESHOLD,
    NUMERIC_CHANGE_ALPHA,
)
from tiaa.config.las import (
    CAR_WINDOW,
    MARKET_TICKER,
    CAR_BUFFER_DAYS,
    VOLUME_BASELINE_DAYS,
    VOLUME_BASELINE_GAP,
    ATTENTION_COMPOSITE_WEIGHTS,
    LAS_WEIGHTS,
    LAS_NORMALIZATION,
)
from tiaa.config.signals import (
    SIGNAL_THRESHOLDS,
    SIGNAL_CONFIDENCE,
    SIGNAL_KEY_SECTIONS,
    SECTION_SELL_BOOST_THRESHOLD,
)
from tiaa.config.pipeline import (
    PIPELINE_VERSION,
    PIPELINE_WORKERS,
    PAIRING_DAY_RANGE,
)
from tiaa.config.llm_rag import (
    LLM_MODEL,
    RAG_ENABLED,
    RAG_EMBEDDING_PROVIDER,
    RAG_EMBEDDING_MODEL,
    RAG_LLM_PROVIDER,
    RAG_VECTOR_STORE,
    RAG_VECTORDB_DIR,
    RAG_CHUNK_MAX_CHARS,
    RAG_CHUNK_OVERLAP,
    RAG_TOP_K,
)
