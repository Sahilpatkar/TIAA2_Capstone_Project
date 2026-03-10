# LazyPrices: Technical Report

## 1. Executive Summary

This project implements the [Lazy Prices](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1658471) paper (Cohen, Malloy, Nguyen, 2020) as a production-grade pipeline and advisor dashboard. The system detects material year-over-year changes in SEC 10-K filings, scores them with a Lazy Attention Score (LAS), computes cumulative abnormal returns around filing dates, and surfaces insights through an interactive web dashboard with LLM-powered chat and risk narratives.

The core thesis of the paper is that companies periodically change the language in their annual filings. When these changes are substantial but investors fail to notice them ("lazy prices"), the changes can predict future stock returns. The LAS captures this dynamic by combining three components: filing change intensity, investor attention, and abnormal returns.

---

## 2. System Architecture

The system is organized into four layers:

```
┌──────────────────────────────────────────────────────────────────────┐
│                        React Frontend (Vite)                         │
│  Sidebar · Portfolio · Charts · Risk Insights · Chat · Filings       │
├──────────────────────────────────────────────────────────────────────┤
│                    Flask API Backend (:5001)                          │
│  REST endpoints · Pipeline trigger · Chat handler                    │
├────────────────────────┬─────────────────────────────────────────────┤
│   RAG Layer            │          Data Processing Pipeline           │
│  Chunker · Indexer     │  Pull · Clean · Embed · Similarity ·       │
│  Providers (OpenAI,    │  Attention · CAR · LAS                      │
│  ChromaDB)             │                                             │
├────────────────────────┴─────────────────────────────────────────────┤
│                        Storage Layer                                 │
│  SQLite (las_store.db) · ChromaDB (vectordb/) · Disk (JSON, .npz)    │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 Technology Stack

| Layer | Technologies |
|---|---|
| Pipeline | Python 3.10+, scikit-learn, BeautifulSoup, lxml, yfinance, NLTK |
| Storage | SQLite (structured data), ChromaDB (vector embeddings), disk (JSON, sparse matrices) |
| LLM / RAG | OpenAI GPT-4o-mini (narrative, chat), text-embedding-3-small (embeddings) |
| Backend | Flask, flask-cors, python-dotenv |
| Frontend | React 18, Vite, Recharts, Axios, react-markdown |

---

## 3. Data Processing Pipeline

The pipeline is orchestrated by `run_pipeline.py` and executes the following stages sequentially for each CIK:

### 3.1 Stage 1: Filing Acquisition (`document_pull.py`)

- Queries SEC EDGAR's submissions API (`data.sec.gov/submissions/CIK{cik}.json`) to retrieve 10-K filing metadata
- Downloads the primary HTML document for each filing
- Stores raw HTML under `entityName_CIK/` directories
- Respects SEC rate limits with 0.2-second delays between requests
- Configurable via `MAX_FILINGS_PER_CIK` (default: 5)

### 3.2 Stage 2: Text Extraction and Cleaning (`extract_clean.py`)

- Parses iXBRL HTML using BeautifulSoup with the lxml parser
- Strips non-textual content: scripts, styles, XBRL hidden elements, numeric tables (tables exceeding `NUMERIC_TABLE_THRESHOLD = 0.15` numeric character ratio)
- Splits text by SEC Item sections (Item 1 through Item 15) using regex pattern matching on section headings
- Outputs per-filing JSON with both full text and per-section text to `cleaned/` subdirectories

### 3.3 Stage 3: Vectorization (`embeddings.py`)

- Builds term-frequency count vectors using scikit-learn's `CountVectorizer`
- Produces both document-level and section-level sparse vectors
- Applies optional stopword removal and NLTK WordNet lemmatization
- Stores sparse matrices as `.npz` files in `data/vectors/`
- Architecture supports TF-IDF and dense embedding modes (hooks present for `sentence-transformers`)

### 3.4 Stage 4: Similarity and Change Intensity (`similarity.py`)

Each 10-K is paired with its prior-year filing (200-550 day gap by report date). Two similarity measures are computed:

**Cosine Similarity** — computed on count vectors using scikit-learn's `cosine_similarity`:

```
cosine_sim(v_current, v_prior) ∈ [0, 1]
```

**Jaccard Similarity** — computed on lemmatized token sets:

```
jaccard_sim = |tokens_current ∩ tokens_prior| / |tokens_current ∪ tokens_prior|
```

**Change Intensity** — the primary measure of how much a filing changed:

```
change_intensity = 1 - cosine_similarity
```

Falls back to `1 - jaccard_similarity` if cosine is unavailable. Change intensity is also computed at the individual section level for each shared Item section between the current and prior filings.

### 3.5 Stage 5: Investor Attention Proxy (`attention_proxy.py`)

Currently a placeholder returning a constant value of 0.5 for all filings. The Lazy Prices paper derives this from SEC FOIA download logs — the fraction of EDGAR users who fetched both the current and prior 10-K around the same time. This component is designed for replacement when FOIA data becomes available.

### 3.6 Stage 6: Cumulative Abnormal Returns (`abnormal_returns.py`)

Computes the market-adjusted CAR around the filing date:

1. Fetches daily adjusted close prices from Yahoo Finance for the stock and the S&P 500 (`^GSPC`)
2. Computes daily returns: `r_t = (P_t - P_{t-1}) / P_{t-1}`
3. Computes daily abnormal returns: `AR_t = r_stock_t - r_market_t`
4. Sums over the event window: `CAR = Σ AR_t` for `t ∈ [-1, +5]` trading days relative to `filed_date`

The event window `(-1, +5)` is configurable via `CAR_WINDOW` in `config.py`. A 30-calendar-day buffer (`CAR_BUFFER_DAYS`) ensures sufficient price data is fetched.

### 3.7 Stage 7: LAS Computation (`las.py`)

The Lazy Attention Score combines the three components:

```
LAS = w_change × f(change_intensity) − w_attention × f(attention_proxy) + w_car × f(|CAR|)
```

| Weight | Default | Component | Interpretation |
|---|---|---|---|
| `w_change` | 0.50 | Change intensity | Higher score when filing changed more |
| `w_attention` | 0.25 | Attention proxy (subtracted) | Higher score when investors paid less attention |
| `w_car` | 0.25 | Absolute CAR | Higher score when abnormal return was larger |

**Normalization function `f()`**: Cross-sectional rank percentile, mapping each raw value to its rank within the batch (values in [0, 1]). Z-score normalization is also supported via `LAS_NORMALIZATION`.

A section-level LAS proxy is also computed as the rank-normalized change intensity for each Item section, enabling granular identification of the most materially changed disclosures.

### 3.8 Stage 8: Persistence (`store.py`)

All results are stored in a SQLite database (`data/las_store.db`) via upsert on the `(cik, accession)` composite key.

**Database Schema:**

| Table | Purpose | Key Columns |
|---|---|---|
| `filings` | Filing-level features and scores | cik, accession, ticker, similarity_cosine, similarity_jaccard, change_intensity, attention_proxy, car, las, section_changes_json, cleaned_text_path |
| `pipeline_runs` | Incremental processing tracker | cik, accession, pipeline_version, processed_at |
| `clients` | Advisor client profiles | id, name, risk_tolerance, investment_goal, notes |
| `client_portfolios` | Client-ticker associations | client_id, ticker, weight |

### 3.9 Incremental Processing

The pipeline tracks which `(cik, accession)` pairs have been processed at the current `PIPELINE_VERSION`. On subsequent runs:

1. The pipeline fetches the latest 10-K list from SEC EDGAR
2. Each filing is checked against the `pipeline_runs` table
3. Already-processed filings are skipped; only new filings run through the full pipeline
4. Successfully stored filings are marked with a UTC timestamp

Bumping `PIPELINE_VERSION` in `config.py` forces reprocessing of all filings. The `--force` CLI flag overrides tracking for one-off full runs.

---

## 4. RAG-Enhanced Chat System

### 4.1 Indexing Pipeline (`rag/`)

Filing text is indexed for retrieval-augmented generation:

1. **Chunking** (`rag/chunker.py`): Cleaned filing JSON is split by Item section. Sections exceeding `RAG_CHUNK_MAX_CHARS` (3000) are sub-chunked at paragraph boundaries with `RAG_CHUNK_OVERLAP` (200) character overlap. Each chunk retains metadata: ticker, CIK, accession, report date, section key, and human-readable section label.

2. **Embedding** (`rag/providers.py`): Chunks are embedded using OpenAI's `text-embedding-3-small` model (1536 dimensions). Rate limiting and batching (20 chunks per API call) are handled automatically.

3. **Storage**: Embeddings are stored in a ChromaDB persistent collection at `data/vectordb/`. An `indexed.json` manifest tracks which filings have been indexed to avoid redundant work.

### 4.2 Chat Flow (`dashboard/backend/chat.py`)

When a user sends a chat message:

1. **Structured context** is built from portfolio metrics (LAS, CAR, change intensity) and top changed sections
2. **RAG retrieval** (when `RAG_ENABLED = True`): The user's query is embedded, and the top-K most similar filing chunks are retrieved from ChromaDB, optionally filtered by ticker
3. **LLM call**: The system prompt, structured context, retrieved passages, conversation history (last 10 turns), and user message are sent to GPT-4o-mini
4. **Fallback**: If no API key is set or the LLM call fails, a template-based response is generated from the structured context

Client-aware context is supported: when an active client profile is selected, the system prompt includes the client's name and risk tolerance to tailor responses.

### 4.3 Provider Abstraction

All RAG components use abstract base classes (`EmbeddingProvider`, `LLMProvider`, `VectorStoreProvider`) with concrete implementations for OpenAI + ChromaDB. This design enables future migration to AWS (Bedrock for embeddings/LLM, OpenSearch for vector storage) by implementing the same interfaces.

---

## 5. Advisor Dashboard

### 5.1 Backend API (`dashboard/backend/app.py`)

A Flask application on port 5001 exposes the following REST endpoints:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/tickers` | GET | List distinct tickers in the database |
| `/api/filings` | GET | Retrieve filings, optionally filtered by tickers |
| `/api/filings/<ticker>` | GET | Filings for a single ticker |
| `/api/portfolio` | GET | Portfolio LAS aggregation (equal-weighted average) |
| `/api/sections` | GET | Top-N highest-change filing sections |
| `/api/risk-narrative` | GET | LLM-generated thematic risk summary |
| `/api/filing/<cik>/<accession>/sections` | GET | Full section text for a specific filing |
| `/api/clients` | GET/POST | List or create client profiles |
| `/api/clients/<id>` | GET/PUT/DELETE | Client profile CRUD |
| `/api/chat` | POST | Chat with RAG-enhanced advisor |
| `/api/pipeline/run` | POST | Trigger pipeline in background thread |
| `/api/pipeline/status/<job_id>` | GET | Poll pipeline job status |

All responses are JSON-serialized with NaN/Infinity sanitization to prevent serialization errors.

### 5.2 Frontend Architecture

The React frontend (Vite dev server on port 5173) is a single-page application with three panels:

**Left Panel — Sidebar** (`Sidebar.jsx`)
- Client profile selector with risk tolerance badges
- Ticker checkboxes for the DJIA 30 universe
- Portfolio LAS score display
- The ticker list uses CSS flexbox with `flex: 1` and `min-height: 0` so it shrinks dynamically, keeping the Analyze button and Portfolio LAS pinned at the bottom

**Center Panel — Main Content** (scrollable)
- `PortfolioOverview.jsx`: Holdings table with per-ticker LAS; "Process" buttons for unprocessed tickers that trigger the pipeline via background threads
- `LASChart.jsx`: Bar chart of LAS scores by filing (Recharts)
- `SimilarityChart.jsx`: Side-by-side cosine vs. Jaccard similarity bars
- `LASvsCAR.jsx`: Scatter plot showing the relationship between LAS and abnormal returns
- `RiskInsights.jsx`: Top 5 changed sections with change intensity bars, plus an asynchronously loaded LLM risk narrative rendered with `react-markdown`
- `FilingsTable.jsx`: Sortable table of all filings with grouping by ticker
- `SectionChanges.jsx`: Expandable section-level detail with change intensity and text snippets

**Right Panel — Chat** (`ChatPanel.jsx`)
- Conversational interface with message history
- Client-aware context (name, risk tolerance) passed to the backend
- Template mode indicator when no API key is configured

**Client Management** (`ClientModal.jsx`)
- Create, edit, and delete client profiles with name, risk tolerance, investment goal, notes, and portfolio tickers

### 5.3 Pipeline Triggering from Dashboard

Unprocessed tickers (those returning `las: null` from the portfolio endpoint) display a "Process" button in the Portfolio Overview. Clicking it:

1. Sends `POST /api/pipeline/run` with the ticker list
2. The backend spawns a `threading.Thread` running `run_pipeline.run(ciks)` in the background
3. The frontend polls `GET /api/pipeline/status/<job_id>` every 3 seconds
4. On completion, the frontend re-fetches all analysis data

A "Process All Missing" button handles batch processing of multiple unprocessed tickers.

---

## 6. Configuration Reference

All tunable parameters are centralized in `config.py`:

### 6.1 Pipeline Settings

| Parameter | Default | Description |
|---|---|---|
| `FILING_TYPE` | `"10-K"` | SEC filing type to process |
| `MAX_FILINGS_PER_CIK` | `5` | Maximum filings downloaded per company |
| `PIPELINE_VERSION` | `"1.0"` | Version string; bump to force reprocessing |
| `NUMERIC_TABLE_THRESHOLD` | `0.15` | Tables above this numeric character ratio are dropped |

### 6.2 LAS Formula

| Parameter | Default | Description |
|---|---|---|
| `LAS_WEIGHTS["w_change"]` | `0.50` | Weight for change intensity |
| `LAS_WEIGHTS["w_attention"]` | `0.25` | Weight for attention proxy (subtracted) |
| `LAS_WEIGHTS["w_car"]` | `0.25` | Weight for absolute CAR |
| `LAS_NORMALIZATION` | `"rank"` | `"rank"` (percentile) or `"zscore"` |

### 6.3 Abnormal Returns

| Parameter | Default | Description |
|---|---|---|
| `CAR_WINDOW` | `(-1, 5)` | Trading days relative to filing date |
| `MARKET_TICKER` | `"^GSPC"` | Market proxy (S&P 500) |
| `CAR_BUFFER_DAYS` | `30` | Calendar-day buffer for price data |

### 6.4 RAG Settings

| Parameter | Default | Description |
|---|---|---|
| `RAG_ENABLED` | `True` | Enable RAG in chat handler |
| `RAG_EMBEDDING_PROVIDER` | `"openai"` | `"openai"` or `"bedrock"` |
| `RAG_EMBEDDING_MODEL` | `"text-embedding-3-small"` | Embedding model |
| `RAG_LLM_PROVIDER` | `"openai"` | `"openai"` or `"bedrock"` |
| `RAG_VECTOR_STORE` | `"chroma"` | `"chroma"` or `"opensearch"` |
| `RAG_CHUNK_MAX_CHARS` | `3000` | Maximum characters per chunk |
| `RAG_CHUNK_OVERLAP` | `200` | Overlap between sub-chunks |
| `RAG_TOP_K` | `5` | Passages retrieved per query |
| `LLM_MODEL` | `"gpt-4o-mini"` | LLM model for narratives and chat |

---

## 7. Data Flow Diagrams

### 7.1 End-to-End Pipeline Flow

```
SEC EDGAR API
    │
    ▼
document_pull.py ──► Raw HTML (entityName_CIK/*.html)
    │
    ▼
extract_clean.py ──► Cleaned JSON + Sections (cleaned/*_cleaned.json)
    │
    ├──► embeddings.py ──► Sparse Vectors (data/vectors/*.npz)
    │         │
    │         ▼
    └──► similarity.py ──► Cosine, Jaccard, Change Intensity
              │
              ├──► attention_proxy.py ──► 0.5 (placeholder)
              │
              ├──► abnormal_returns.py ──► CAR (Yahoo Finance)
              │
              ▼
         las.py ──► LAS = 0.50·f(change) − 0.25·f(attn) + 0.25·f(|CAR|)
              │
              ▼
         store.py ──► SQLite (las_store.db)
              │
              ▼
         advisor_query.py ──► Portfolio Aggregation + LLM Narrative
```

### 7.2 Dashboard Request Flow

```
React Frontend (:5173)
    │
    │  Axios HTTP
    ▼
Flask API (:5001)
    │
    ├──► SQLite (filings, clients)
    │
    ├──► advisor_query.py (portfolio aggregation, risk narrative)
    │
    ├──► chat.py
    │      ├──► Structured context (portfolio + sections)
    │      ├──► RAG retrieval (ChromaDB → top-K passages)
    │      └──► OpenAI GPT-4o-mini
    │
    └──► run_pipeline.py (background thread, triggered from UI)
```

### 7.3 RAG Retrieval Flow

```
User question
    │
    ▼
Embed query (text-embedding-3-small)
    │
    ▼
ChromaDB cosine search (top-5, filtered by ticker)
    │
    ▼
Retrieved passages + structured portfolio metrics
    │
    ▼
System prompt + context + history + question
    │
    ▼
GPT-4o-mini → Grounded response with filing citations
```

---

## 8. File Structure

```
TIAA2_Capstone_Project/
│
├── config.py                       # Central configuration
├── run_pipeline.py                 # Pipeline orchestrator (CLI)
├── document_pull.py                # SEC EDGAR filing acquisition
├── extract_clean.py                # HTML → cleaned JSON extraction
├── embeddings.py                   # Count vector / TF-IDF construction
├── similarity.py                   # Year-over-year similarity computation
├── attention_proxy.py              # Investor attention (placeholder)
├── abnormal_returns.py             # Cumulative abnormal returns (Yahoo Finance)
├── las.py                          # LAS formula computation
├── store.py                        # SQLite persistence layer
├── advisor_query.py                # Portfolio aggregation + LLM narrative
│
├── rag/
│   ├── __init__.py
│   ├── chunker.py                  # Section-aware text chunking
│   ├── providers.py                # Embedding, LLM, vector store abstractions
│   └── index.py                    # Filing indexing CLI
│
├── dashboard/
│   ├── backend/
│   │   ├── app.py                  # Flask API (all REST endpoints)
│   │   └── chat.py                 # RAG-enhanced chat handler
│   └── frontend/
│       ├── index.html
│       ├── package.json
│       ├── vite.config.js          # Dev server with API proxy
│       └── src/
│           ├── api.js              # Axios API client
│           ├── App.jsx             # Root component and layout
│           ├── App.css             # Dashboard styles
│           └── components/
│               ├── Sidebar.jsx
│               ├── PortfolioOverview.jsx
│               ├── LASChart.jsx
│               ├── SimilarityChart.jsx
│               ├── LASvsCAR.jsx
│               ├── RiskInsights.jsx
│               ├── FilingsTable.jsx
│               ├── SectionChanges.jsx
│               ├── ChatPanel.jsx
│               └── ClientModal.jsx
│
├── data/
│   ├── las_store.db                # SQLite database
│   ├── vectors/                    # Sparse count vectors (.npz)
│   └── vectordb/                   # ChromaDB persistence
│       └── indexed.json            # Indexing manifest
│
├── entityName_CIK/                 # One folder per company
│   ├── *.html                      # Raw 10-K filings
│   ├── company_facts.json          # SEC XBRL company facts
│   └── cleaned/
│       ├── *_cleaned.json          # Cleaned text + sections
│       └── similarity_results.json # Year-over-year similarity
│
├── requirements.txt
├── .env                            # OPENAI_API_KEY (optional)
├── README.md
├── TECHNICAL_REPORT.md             # This document
└── PythonPractice10.ipynb          # Reference notebook (similarity only)
```

---

## 9. Coverage and Limitations

### 9.1 Current Coverage

- **Universe**: DJIA 30 constituents (29 CIK-to-ticker mappings in `config.py`)
- **Filing type**: 10-K annual reports only
- **Time depth**: Up to 5 filings per company (configurable)
- **Similarity measures**: Cosine similarity (count vectors) and Jaccard similarity (lemmatized token sets)
- **LLM integration**: OpenAI GPT-4o-mini for narratives and chat; template fallback when no API key

### 9.2 Known Limitations

| Limitation | Details | Mitigation Path |
|---|---|---|
| Attention proxy is a placeholder | Constant 0.5 for all filings; no discriminating power | Replace with SEC FOIA download log analysis |
| 10-Q filings not supported | Only 10-K annual reports are processed | Extend `FILING_TYPE` and adjust pairing logic |
| Count vectors only | TF-IDF and dense embeddings are stubbed but not active | Enable `--dense` flag in `embeddings.py` for sentence-transformers |
| Limited similarity measures | Only cosine and Jaccard; paper also uses MinEdit and Sim Simple | The reference notebook implements these; can be ported |
| Single-market CAR model | Market-adjusted model using S&P 500 only | Could add Fama-French factor model |
| In-memory pipeline jobs | Background job tracking uses a Python dict; lost on server restart | Migrate to a task queue (Celery, Redis) for production |
| Local vector store | ChromaDB is file-based; single-node only | Provider abstraction supports OpenSearch migration |

### 9.3 Reference Notebook Comparison

The `PythonPractice10.ipynb` notebook is an earlier prototype that implements filing download, text cleaning, and similarity computation for 5 stocks (AXP, AAPL, KO, JPM, V). It computes four similarity measures (cosine, Jaccard, MinEdit, Sim Simple) but does not compute change intensity, attention proxy, CAR, or LAS. The pipeline modules build on the same concepts but extend them into a full scoring system with normalization, persistence, and a web interface.

---

## 10. Running the System

### 10.1 Pipeline

```bash
pip install -r requirements.txt

# Full pipeline for Apple
python run_pipeline.py --ciks 320193

# Multiple companies
python run_pipeline.py --ciks 320193,19617,21344

# Skip download (use existing filings)
python run_pipeline.py --ciks 320193 --skip-pull

# Force reprocessing
python run_pipeline.py --ciks 320193 --force
```

### 10.2 RAG Indexing

```bash
# Index all filings in the database
python -m rag.index

# Index one ticker
python -m rag.index --ticker AAPL

# Force re-index
python -m rag.index --reindex
```

### 10.3 Dashboard

```bash
# Terminal 1: Flask backend
cd dashboard/backend
python app.py

# Terminal 2: React frontend
cd dashboard/frontend
npm install
npm run dev
```

Open http://localhost:5173.

### 10.4 CLI Query

```bash
# Narrative output
python advisor_query.py --portfolio AAPL,JPM,KO --top 5

# JSON output
python advisor_query.py --portfolio AAPL --top 3 --json
```
