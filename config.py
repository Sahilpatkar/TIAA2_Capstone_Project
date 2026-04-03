
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
FILINGS_DIR = os.path.join(DATA_DIR, "filings")
VECTORS_DIR = os.path.join(DATA_DIR, "vectors")
DB_PATH = os.path.join(DATA_DIR, "las_store.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")

# SEC / Filing settings
FILING_TYPES = ["10-K", "10-Q"]
MAX_FILINGS_PER_CIK = 5   # per filing type

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
    1744489: "DIS",
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

# Sector and industry classification for each ticker (GICS-style).
TICKER_SECTOR_INDUSTRY = {
    "MMM":  {"sector": "Industrials",             "industry": "Conglomerates"},
    "AXP":  {"sector": "Financial Services",      "industry": "Credit Services"},
    "AMGN": {"sector": "Healthcare",              "industry": "Drug Manufacturers"},
    "AAPL": {"sector": "Technology",              "industry": "Consumer Electronics"},
    "BA":   {"sector": "Industrials",             "industry": "Aerospace & Defense"},
    "CAT":  {"sector": "Industrials",             "industry": "Farm & Heavy Construction Machinery"},
    "CVX":  {"sector": "Energy",                  "industry": "Oil & Gas Integrated"},
    "CSCO": {"sector": "Technology",              "industry": "Communication Equipment"},
    "KO":   {"sector": "Consumer Defensive",      "industry": "Beverages — Non-Alcoholic"},
    "DIS":  {"sector": "Communication Services",  "industry": "Entertainment"},
    "DOW":  {"sector": "Basic Materials",         "industry": "Chemicals"},
    "GS":   {"sector": "Financial Services",      "industry": "Capital Markets"},
    "HD":   {"sector": "Consumer Cyclical",       "industry": "Home Improvement Retail"},
    "HON":  {"sector": "Industrials",             "industry": "Conglomerates"},
    "IBM":  {"sector": "Technology",              "industry": "Information Technology Services"},
    "INTC": {"sector": "Technology",              "industry": "Semiconductors"},
    "JNJ":  {"sector": "Healthcare",              "industry": "Drug Manufacturers"},
    "JPM":  {"sector": "Financial Services",      "industry": "Banks — Diversified"},
    "MCD":  {"sector": "Consumer Cyclical",       "industry": "Restaurants"},
    "MRK":  {"sector": "Healthcare",              "industry": "Drug Manufacturers"},
    "MSFT": {"sector": "Technology",              "industry": "Software — Infrastructure"},
    "NKE":  {"sector": "Consumer Cyclical",       "industry": "Footwear & Accessories"},
    "PG":   {"sector": "Consumer Defensive",      "industry": "Household & Personal Products"},
    "CRM":  {"sector": "Technology",              "industry": "Software — Application"},
    "TRV":  {"sector": "Financial Services",      "industry": "Insurance — Property & Casualty"},
    "UNH":  {"sector": "Healthcare",              "industry": "Healthcare Plans"},
    "VZ":   {"sector": "Communication Services",  "industry": "Telecom Services"},
    "V":    {"sector": "Financial Services",      "industry": "Credit Services"},
    "WBA":  {"sector": "Healthcare",              "industry": "Pharmaceutical Retailers"},
    "WMT":  {"sector": "Consumer Defensive",      "industry": "Discount Stores"},
}

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

# Per-section importance weights for the weighted change_intensity calculation.
# Inspired by the LazyPrices paper: MD&A, Risk Factors, and Business are the
# strongest predictors of post-filing drift.  Sections absent from this dict
# are ignored (weight 0).  The weighted average divides by the sum of weights
# for sections actually present, so missing sections don't penalise the score.
SECTION_WEIGHTS = {
    "item_1":  0.15,   # Business
    "item_1a": 0.25,   # Risk Factors
    "item_1b": 0.02,   # Unresolved Staff Comments
    "item_1c": 0.02,   # Cybersecurity
    "item_2":  0.02,   # Properties
    "item_3":  0.01,   # Legal Proceedings
    "item_4":  0.01,   # Mine Safety Disclosures
    "item_5":  0.02,   # Market for Common Equity
    "item_6":  0.01,   # Reserved
    "item_7":  0.30,   # MD&A (strongest predictor)
    "item_7a": 0.10,   # Quantitative & Qualitative Market Risk
    "item_8":  0.05,   # Financial Statements
    "item_9":  0.01,   # Accountant Changes / Disagreements
    "item_9a": 0.02,   # Controls and Procedures
    "item_9b": 0.01,   # Other Information
    "item_10": 0.01,   # Directors / Corporate Governance
    "item_11": 0.01,   # Executive Compensation
    "item_12": 0.01,   # Security Ownership
    "item_13": 0.01,   # Related Transactions
    "item_14": 0.01,   # Principal Accountant Fees
    "item_15": 0.01,   # Exhibits / Financial Statement Schedules
}

# 10-Q sections (Part I and Part II items).  The regex in extract_clean.py
# already matches these patterns; this list is used for section-level LAS.
ITEM_SECTIONS_10Q = [
    "item_1",   # Financial Statements
    "item_2",   # MD&A
    "item_3",   # Quantitative & Qualitative Market Risk
    "item_4",   # Controls and Procedures
    "item_1a",  # Risk Factors (Part II)
    "item_2",   # Unregistered Sales of Equity
    "item_5",   # Other Information
    "item_6",   # Exhibits
]

# Section weights for 10-Q filings (same key sections, fewer sections total).
SECTION_WEIGHTS_10Q = {
    "item_1":  0.10,   # Financial Statements
    "item_2":  0.35,   # MD&A (strongest predictor, same as 10-K item_7)
    "item_3":  0.15,   # Quantitative & Qualitative Market Risk
    "item_4":  0.05,   # Controls and Procedures
    "item_1a": 0.30,   # Risk Factors
    "item_5":  0.03,   # Other Information
    "item_6":  0.02,   # Exhibits
}

# Pairing gap (calendar days) for filing type.
# 10-K: annual, gap between 200 and 550 days.
# 10-Q: quarterly, gap between 60 and 150 days.
PAIRING_DAY_RANGE = {
    "10-K": (200, 550),
    "10-Q": (60, 150),
}

PIPELINE_WORKERS = 4  # concurrent CIK workers for run_pipeline.py (--workers flag)

SIMILARITY_MEASURES = ["cosine", "jaccard"]  # supported: cosine, jaccard

NUMERIC_TABLE_THRESHOLD = 0.15

# Weight of text-based similarity in the hybrid change_intensity formula.
# change_intensity = alpha * text_change + (1 - alpha) * numerical_divergence
NUMERIC_CHANGE_ALPHA = 0.7


# CAR (Cumulative Abnormal Return) event window

CAR_WINDOW = (-1, 5)  # trading days relative to filed_date
MARKET_TICKER = "^GSPC"  # S&P 500 as market proxy
CAR_BUFFER_DAYS = 30  # calendar-day buffer when fetching price data

VOLUME_BASELINE_DAYS = 60  # trailing trading days for baseline average volume
VOLUME_BASELINE_GAP = 5    # trading-day gap before event window to avoid leakage

# Composite attention proxy weights (volume ratio + filing delay).
# Filing delay = calendar days from report_date to filed_date.
# Late filers signal lower attention / quality.
ATTENTION_COMPOSITE_WEIGHTS = {
    "volume_ratio": 0.7,
    "filing_delay": 0.3,
}

# 
# LAS formula  –  LAS = w_change * f(change) - w_attention * f(attn) - w_car * f(car)

LAS_WEIGHTS = {
    "w_change": 0.60,
    "w_attention": 0.30,
    "w_car": 0.10,
}

# "rank" (cross-sectional rank percentile) or "zscore"
LAS_NORMALIZATION = "rank"


# Pipeline versioning — bump to force reprocessing of all filings

PIPELINE_VERSION = "1.5"


# LLM settings (advisor narrative)

LLM_MODEL = "gpt-4o-mini"


# RAG settings
# Toggle RAG_ENABLED to False to revert to plain context-injection chat.
# To switch to AWS, change the provider/store values:
#   RAG_EMBEDDING_PROVIDER = "bedrock"
#   RAG_LLM_PROVIDER = "bedrock"
#   RAG_VECTOR_STORE = "opensearch"

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


RAG_ENABLED = True
RAG_EMBEDDING_PROVIDER = "openai"           # "openai" | "bedrock"
RAG_EMBEDDING_MODEL = "text-embedding-3-small"
RAG_LLM_PROVIDER = "openai"                # "openai" | "bedrock"
RAG_VECTOR_STORE = "chroma"                 # "chroma" | "opensearch"
RAG_VECTORDB_DIR = os.path.join(DATA_DIR, "vectordb")
RAG_CHUNK_MAX_CHARS = 3000
RAG_CHUNK_OVERLAP = 200
RAG_TOP_K = 5
