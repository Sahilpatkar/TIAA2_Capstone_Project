
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
FILINGS_DIR = os.path.join(DATA_DIR, "filings")
VECTORS_DIR = os.path.join(DATA_DIR, "vectors")
DB_PATH = os.path.join(DATA_DIR, "las_store.db")

# SEC / Filing settings
FILING_TYPE = "10-K"  # MVP scope; extend to "10-Q" later
MAX_FILINGS_PER_CIK = 5


# CIK-to-Ticker mapping  (DJIA 30 + common extras)
# Keys are CIK integers, values are ticker strings.

CIK_TO_TICKER = {
    66740: "MMM",
    4962: "AXP",
    318154: "AMGN",
    320193: "AAPL",
    12927: "BA",
    18230: "CAT",
    93410: "CVX",
    858877: "CSCO",
    21344: "KO",
    1001039: "DIS",
    29915: "DOW",
    886982: "GS",
    354950: "HD",
    773840: "HON",
    51143: "IBM",
    50863: "INTC",
    200406: "JNJ",
    19617: "JPM",
    63908: "MCD",
    310158: "MRK",
    789019: "MSFT",
    320187: "NKE",
    80424: "PG",
    1108524: "CRM",
    86312: "TRV",
    1096938: "UNH",
    732712: "VZ",
    1403161: "V",
    1618921: "WBA",
    104169: "WMT",
}

TICKER_TO_CIK = {v: k for k, v in CIK_TO_TICKER.items()}


# 10-K Item sections to extract (ordered as they appear in the filing)

ITEM_SECTIONS = [
    "item_1",
    "item_1a",
    "item_1b",
    "item_1c",
    "item_2",
    "item_3",
    "item_4",
    "item_5",
    "item_6",
    "item_7",
    "item_7a",
    "item_8",
    "item_9",
    "item_9a",
    "item_9b",
    "item_10",
    "item_11",
    "item_12",
    "item_13",
    "item_14",
    "item_15",
]


# Similarity settings

SIMILARITY_MEASURES = ["cosine", "jaccard"]  # supported: cosine, jaccard

# Tables with more than this fraction of numeric chars are dropped during cleaning
NUMERIC_TABLE_THRESHOLD = 0.15


# CAR (Cumulative Abnormal Return) event window

CAR_WINDOW = (-1, 5)  # trading days relative to filed_date
MARKET_TICKER = "^GSPC"  # S&P 500 as market proxy
CAR_BUFFER_DAYS = 30  # calendar-day buffer when fetching price data

# 
# LAS formula  –  LAS = w_change * f(change) - w_attention * f(attn) + w_car * f(|car|)

LAS_WEIGHTS = {
    "w_change": 0.50,
    "w_attention": 0.25,
    "w_car": 0.25,
}

# "rank" (cross-sectional rank percentile) or "zscore"
LAS_NORMALIZATION = "rank"


# Pipeline versioning — bump to force reprocessing of all filings

PIPELINE_VERSION = "1.0"


# LLM settings (advisor narrative)

LLM_MODEL = "gpt-4o-mini"


# RAG settings
# Toggle RAG_ENABLED to False to revert to plain context-injection chat.
# To switch to AWS, change the provider/store values:
#   RAG_EMBEDDING_PROVIDER = "bedrock"
#   RAG_LLM_PROVIDER = "bedrock"
#   RAG_VECTOR_STORE = "opensearch"

RAG_ENABLED = True
RAG_EMBEDDING_PROVIDER = "openai"           # "openai" | "bedrock"
RAG_EMBEDDING_MODEL = "text-embedding-3-small"
RAG_LLM_PROVIDER = "openai"                # "openai" | "bedrock"
RAG_VECTOR_STORE = "chroma"                 # "chroma" | "opensearch"
RAG_VECTORDB_DIR = os.path.join(DATA_DIR, "vectordb")
RAG_CHUNK_MAX_CHARS = 3000
RAG_CHUNK_OVERLAP = 200
RAG_TOP_K = 5
