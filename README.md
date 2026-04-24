# LazyPrices: SEC Filing Change Detection Pipeline

An end-to-end implementation of the [Lazy Prices](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1658471) paper (Cohen, Malloy, Nguyen) for detecting material changes in SEC 10-K filings and scoring them with a **Lazy Attention Score (LAS)**.

The pipeline pulls 10-K filings from SEC EDGAR, extracts and cleans the text, computes year-over-year similarity metrics, calculates cumulative abnormal returns around filing dates, and combines everything into a single LAS per filing. An advisor-facing query interface aggregates scores across a portfolio and highlights the most impactful disclosure changes.

## Quick Start

### Option A: Local (no Docker)

```bash
# 1. Install the package in editable mode (installs deps via requirements.txt)
pip install -e .

# 2. Run the full pipeline for Apple (CIK 320193)
tiaa-pipeline --ciks 320193

# 3. Start the dashboard
cd dashboard/backend && python app.py        # Terminal 1 (port 5001)
cd dashboard/frontend && npm install && npm run dev  # Terminal 2 (port 5173)
```

> `pip install -e .` makes the `tiaa` package importable everywhere and exposes the
> `tiaa-pipeline` console script — no `sys.path` hacks or `PYTHONPATH` needed.

### Option B: Docker (recommended)

```bash
# 1. Create .env with your OpenAI key (optional, enables LLM features)
echo "OPENAI_API_KEY=sk-..." > .env

# 2. Start all services (PostgreSQL, backend, frontend)
cd deploy/docker
docker compose up -d --build

# 3. Run the pipeline
docker compose --profile pipeline run --rm pipeline --ciks 320193

# 4. Open http://localhost in your browser
```

## Package Layout

All pipeline code lives in the installable `tiaa` package under `src/tiaa/`, organized
by domain:

```
src/tiaa/
├── pipeline/        # document_pull, extract_clean, run (orchestrator)
├── storage/         # embeddings, store (DB persistence)
├── analysis/        # similarity, numeric_change, attention_proxy,
│                    # abnormal_returns, las, signals
├── backtest/        # core, comparison
├── advisor/         # query (portfolio narrative + sentiment)
└── config/          # paths, sec, features, las, signals, pipeline, llm_rag
                     # + reference/*.json lookup tables
```

The RAG layer stays at the repo root under `rag/` and the dashboard under
`dashboard/`; both import from `tiaa.*`.

## Pipeline Architecture

```
SEC EDGAR ─► pipeline/document_pull.py ─► Raw HTML (data/filings/entityName_cik/)
                                       │
                             pipeline/extract_clean.py
                                       │
                              Cleaned text + sections (cleaned/)
                                       │
                            storage/embeddings.py (count vectors)
                                       │
          ┌────────────────────────────┼────────────────────────────┐
 analysis/similarity.py    analysis/numeric_change.py    analysis/abnormal_returns.py
    (cosine/Jaccard)        (numerical divergence)       (Yahoo Finance CAR)
          │                 analysis/attention_proxy.py              │
          │                 (placeholder 0.5)                        │
          └────────────────────────────┼────────────────────────────┘
                                       │
                          analysis/las.py (Lazy Attention Score)
                                       │
                          storage/store.py (PostgreSQL / SQLite)
                                       │
                    ┌──────────────────┼──────────────────┐
         analysis/signals.py    advisor/query.py     backtest/core.py
              (buy/sell)    (LLM narrative + sentiment) (validation)
```

## Module Reference

| Module | Description |
|---|---|
| `tiaa.config` | Config package: paths, SEC/universe, features, LAS, signals, pipeline, LLM/RAG. Lookup tables (`CIK_TO_TICKER`, `TICKER_SECTOR_INDUSTRY`) live in `config/reference/*.json` and are loaded lazily. Importing `from tiaa import config` continues to expose every public symbol. |
| `tiaa.pipeline.document_pull` | Pull 10-K filings from SEC EDGAR; saves raw HTML and `company_facts.json` under `entityName_cik/` |
| `tiaa.pipeline.extract_clean` | Parse iXBRL HTML, strip noise (scripts, styles, XBRL blocks, numeric tables), split text by Item section |
| `tiaa.pipeline.run` | End-to-end CLI orchestrator (installed as the `tiaa-pipeline` console script) with incremental processing and parallel workers |
| `tiaa.storage.embeddings` | Build count vectors (or TF-IDF) per document and per section using sklearn |
| `tiaa.storage.store` | Database persistence layer (PostgreSQL via Docker, SQLite fallback); upsert by `(cik, accession)` |
| `tiaa.analysis.similarity` | Pair each 10-K with its prior-year filing, compute cosine and Jaccard similarity, derive change intensity |
| `tiaa.analysis.attention_proxy` | MVP placeholder returning 0.5 for all filings (pending SEC FOIA download data) |
| `tiaa.analysis.abnormal_returns` | Fetch daily prices from Yahoo Finance, compute market-adjusted CAR over a configurable event window |
| `tiaa.analysis.las` | Combine change intensity, attention proxy, and CAR into a weighted LAS with rank or z-score normalization |
| `tiaa.analysis.numeric_change` | Extract financial numbers (dollars, percentages) from filing text; compute numerical divergence scores |
| `tiaa.analysis.signals` | Classify holdings into 5 signal categories (sell, caution, hold, neutral, buy) using LAS components with confidence scoring |
| `tiaa.advisor.query` | Aggregate portfolio LAS, retrieve highest-impact disclosure sections, generate LLM or template narrative with sentiment classification |
| `tiaa.backtest.core` | Validation framework measuring whether LAS and signal classifications predict forward stock returns (30d/60d/90d/180d horizons) |
| `tiaa.backtest.comparison` | Comparative analysis across different signal configurations and LAS weight schemes |
| `rag/chunker.py` | Section-aware text chunker for 10-K filings with configurable max size and overlap |
| `rag/providers.py` | Provider abstractions for embeddings (OpenAI), LLM (OpenAI), and vector store (ChromaDB) |
| `rag/index.py` | CLI tool to embed and index filings into the vector store with manifest-based deduplication |
| `dashboard/backend/app.py` | Flask API server exposing all REST endpoints for the advisor dashboard |
| `dashboard/backend/chat.py` | RAG-enhanced chat handler; retrieves filing passages and structured metrics for LLM context |

## LAS Formula

```
LAS = w_change * f(change_intensity) - w_attention * f(attention_proxy) + w_car * f(|CAR|)
```

Where `f()` is a cross-sectional normalization (rank percentile by default). Weights live in `tiaa.config.las`:

| Weight | Default | Component |
|---|---|---|
| `w_change` | 0.50 | Year-over-year filing change intensity (1 - cosine similarity) |
| `w_attention` | 0.25 | Investor attention proxy (placeholder for MVP) |
| `w_car` | 0.25 | Absolute cumulative abnormal return around filing date |

## Signal Classification

`tiaa.analysis.signals` classifies each holding into one of five actionable signals based on LAS components:

| Signal | Meaning |
|---|---|
| **sell** | High change intensity + negative CAR -- material deterioration investors may have missed |
| **caution** | Elevated change with modest negative drift |
| **hold** | Moderate change, ambiguous direction |
| **neutral** | Minimal change or low confidence -- no action |
| **buy** | High change intensity + positive CAR -- material improvement that's underappreciated |

Confidence is a blend of absolute (global universe) and relative (portfolio-only) z-scores. The blend weight adapts to portfolio size: small portfolios lean on the stable absolute baseline. Low-confidence signals are downgraded to neutral.

## Backtesting & Validation

`tiaa.backtest.core` measures whether LAS and signal classifications predict real-world forward stock returns. Forward returns are computed starting **after** the CAR event window ends (day +6) to avoid circularity, since CAR is an input to the LAS formula.

```bash
python -m tiaa.backtest.core --output results/
```

**Metrics computed:**
- Information Coefficient (IC) -- rank correlation between LAS and forward returns
- Signal hit rates and average returns by signal category
- Forward horizons: 30, 60, 90, and 180 trading days

`tiaa.backtest.comparison` extends this with comparative analysis across different signal configurations and LAS weight schemes.

## Database

The application supports two database backends:

| Backend | When used | Connection |
|---|---|---|
| **PostgreSQL** | Docker deployment (production) | Automatic via `DATABASE_URL` env var |
| **SQLite** | Local dev without Docker | `data/las_store.db` (no setup needed) |

When running via `docker compose`, the `DATABASE_URL` is injected automatically. For local runs without Docker, SQLite is used as a zero-config fallback.

### Schema

Four tables: `filings` (LAS scores and metrics), `pipeline_runs` (incremental processing tracker), `clients` (advisor client profiles), and `client_portfolios` (client holdings).

## Incremental Processing

The pipeline tracks which filings have been fully processed and skips them on subsequent runs. This is managed through the `pipeline_runs` table keyed by `(cik, accession)`.

**How it works:**

1. On each run the pipeline fetches the latest 10-K list from SEC EDGAR.
2. It checks each filing against `pipeline_runs` for the current `PIPELINE_VERSION`.
3. Filings already processed at the current version are skipped; only new filings are run through the full pipeline.
4. After a filing is successfully stored, it is marked as processed with a UTC timestamp.

**Manual override:** Pass `--force` to reprocess everything regardless of tracking state.

```bash
tiaa-pipeline --ciks 320193 --force
```

**Version bumping:** When pipeline logic changes materially (new LAS formula, new similarity metric, etc.), bump `PIPELINE_VERSION` in `tiaa/config/pipeline.py`. All filings will be reprocessed on the next run because the version check will fail against older records.

## Configuration

The old monolithic `config.py` has been split into `src/tiaa/config/` — one module per
domain — with the two largest lookup tables lifted out into JSON so they're easy to edit
without touching Python.

| Submodule | What lives there |
|---|---|
| `config/paths.py` | `PROJECT_ROOT`, `DATA_DIR`, `FILINGS_DIR`, `VECTORS_DIR`, `DB_PATH`, `DATABASE_URL` |
| `config/sec.py` | `FILING_TYPES`, `UNIVERSE_MODE`, `DEMO_TICKERS`, `CIK_TO_TICKER`, `TICKER_SECTOR_INDUSTRY` |
| `config/features.py` | `ITEM_SECTIONS`, `SECTION_WEIGHTS`, `SIMILARITY_MEASURES`, `NUMERIC_TABLE_THRESHOLD`, `NUMERIC_CHANGE_ALPHA` |
| `config/las.py` | `LAS_WEIGHTS`, `LAS_NORMALIZATION`, `CAR_WINDOW`, `MARKET_TICKER`, attention composite weights |
| `config/signals.py` | `SIGNAL_THRESHOLDS`, `SIGNAL_CONFIDENCE`, `SIGNAL_KEY_SECTIONS` |
| `config/pipeline.py` | `PIPELINE_VERSION`, `PIPELINE_WORKERS`, `PAIRING_DAY_RANGE` |
| `config/llm_rag.py` | `LLM_MODEL` + all `RAG_*` settings |
| `config/reference/*.json` | `cik_to_ticker.json` (~500 entries) and `ticker_sector_industry.json` (~500 entries); loaded lazily on first access |

For backward compatibility, `from tiaa import config` still re-exports every public
symbol — existing callers like `config.LAS_WEIGHTS` keep working unchanged. New code
can import directly from the submodule, e.g. `from tiaa.config.paths import DB_PATH`.

Key tunables:

- **UNIVERSE_MODE** -- `"demo"` (50 tickers) or `"full"` (S&P 500); controls which subset of `CIK_TO_TICKER` is active
- **DATABASE_URL** -- database connection string; reads from env, falls back to SQLite
- **PIPELINE_VERSION** -- pipeline version string; bump to force reprocessing after logic changes
- **LAS_WEIGHTS** -- component weights for the LAS formula
- **LAS_NORMALIZATION** -- `"rank"` (percentile) or `"zscore"`
- **CAR_WINDOW** -- event window in trading days, default `(-1, 5)`
- **NUMERIC_TABLE_THRESHOLD** -- tables with more than this fraction of numeric characters are dropped (default `0.15`)
- **NUMERIC_CHANGE_ALPHA** -- blend weight for text vs. numerical change intensity (default `0.7` text / `0.3` numerical)
- **SECTION_WEIGHTS** -- per-section importance weights for weighted LAS (MD&A 0.30, Risk Factors 0.25, Business 0.15, etc.)
- **PIPELINE_WORKERS** -- number of concurrent CIK workers (default `4`); overridden by `--workers` CLI flag
- **LLM_MODEL** -- OpenAI model for advisor narratives (default `gpt-4o-mini`)

## Advisor Narrative

The advisor query generates a structured explanation of the portfolio's LAS analysis. If the `OPENAI_API_KEY` environment variable is set, it uses the OpenAI API to produce a professional narrative. Otherwise, it falls back to a plain-text template summary.

```bash
# With LLM narrative
export OPENAI_API_KEY="sk-..."
python -m tiaa.advisor.query --portfolio AAPL,JPM,KO --top 5

# Template fallback (no API key needed)
python -m tiaa.advisor.query --portfolio AAPL --top 3
```

## RAG-Enhanced Chat

The chat panel supports Retrieval-Augmented Generation (RAG) to ground LLM responses in actual 10-K filing text. When enabled, the user's question is embedded and matched against indexed filing chunks stored in ChromaDB, and the top passages are injected into the LLM context alongside the structured portfolio metrics.

### Indexing Filings

```bash
# Index all filings in the database
python -m rag.index

# Index filings for a specific ticker
python -m rag.index --ticker AAPL

# Force re-index everything
python -m rag.index --reindex
```

### RAG Architecture

```
User question
      │
      ▼
  Embed query (OpenAI text-embedding-3-small)
      │
      ▼
  ChromaDB similarity search (top-K chunks, filtered by ticker)
      │
      ▼
  Retrieved passages + structured portfolio metrics
      │
      ▼
  LLM prompt (OpenAI GPT-4o-mini)
      │
      ▼
  Grounded response with filing citations
```

### RAG Modules

| Module | Description |
|---|---|
| `rag/chunker.py` | Section-aware text chunker; splits cleaned filing JSON by Item section, sub-chunks large sections at paragraph boundaries with configurable overlap |
| `rag/providers.py` | Provider abstractions (embedding, LLM, vector store) with concrete implementations for OpenAI + ChromaDB; swappable to AWS Bedrock + OpenSearch |
| `rag/index.py` | CLI tool to embed and index filings into the vector store; tracks indexed filings via a manifest to avoid redundant work |

### RAG Configuration

Settings in `tiaa/config/llm_rag.py`:

| Setting | Default | Description |
|---|---|---|
| `RAG_ENABLED` | `True` | Toggle RAG retrieval in the chat handler |
| `RAG_EMBEDDING_PROVIDER` | `"openai"` | Embedding provider (`"openai"` or `"bedrock"`) |
| `RAG_EMBEDDING_MODEL` | `"text-embedding-3-small"` | OpenAI embedding model |
| `RAG_LLM_PROVIDER` | `"openai"` | LLM provider (`"openai"` or `"bedrock"`) |
| `RAG_VECTOR_STORE` | `"chroma"` | Vector store (`"chroma"` or `"opensearch"`) |
| `RAG_VECTORDB_DIR` | `data/vectordb` | ChromaDB persistence directory |
| `RAG_CHUNK_MAX_CHARS` | `3000` | Max characters per chunk |
| `RAG_CHUNK_OVERLAP` | `200` | Overlap characters between sub-chunks |
| `RAG_TOP_K` | `5` | Number of passages retrieved per query |

## Repo Layout

```
project_root/
├── src/tiaa/                       # Installable Python package (`pip install -e .`)
│   ├── config/                     # Split config package + reference/*.json lookup tables
│   ├── pipeline/                   # document_pull, extract_clean, run (CLI entrypoint)
│   ├── storage/                    # embeddings, store (DB persistence)
│   ├── analysis/                   # similarity, numeric_change, attention_proxy,
│   │                               # abnormal_returns, las, signals
│   ├── backtest/                   # core, comparison
│   └── advisor/                    # query (portfolio narrative + sentiment)
├── rag/                            # Retrieval-augmented generation layer
│   ├── chunker.py                  # Section-aware filing chunker
│   ├── providers.py                # Embedding, LLM, vector store abstractions
│   └── index.py                    # CLI indexing tool
├── dashboard/
│   ├── backend/
│   │   ├── app.py                  # Flask API server
│   │   └── chat.py                 # RAG-enhanced chat handler
│   └── frontend/                   # React + Vite dashboard
├── data/
│   ├── las_store.db                # SQLite database (local dev fallback)
│   ├── filings/                    # Downloaded 10-K filings by entity
│   │   └── EntityName_CIK/
│   │       ├── *.html              # Raw 10-K filings
│   │       ├── company_facts.json  # SEC XBRL company facts
│   │       └── cleaned/
│   │           └── *_cleaned.json  # Cleaned text + sections
│   ├── vectors/                    # Sparse count vectors (.npz)
│   └── vectordb/                   # ChromaDB persistence (RAG embeddings)
├── deploy/
│   ├── docker/
│   │   ├── Dockerfile.backend      # Python 3.10 + `pip install -e .` + Gunicorn
│   │   ├── Dockerfile.frontend     # Node 18 build + Nginx
│   │   ├── docker-compose.yml      # PostgreSQL, backend, frontend, pipeline
│   │   └── nginx.conf              # Static files + /api reverse proxy
│   ├── terraform/                  # AWS EC2 infrastructure
│   └── scripts/
│       └── user_data.sh            # EC2 bootstrap script
├── notebooks/                      # Jupyter notebooks (demo, backtest, textual analysis)
├── docs/
│   ├── dashboard_qr.png
│   └── research/                   # Reference PDFs (Lazy Prices paper, etc.)
├── Reports/                        # Validation reports and presentation materials
│   ├── EXECUTIVE_REPORT.md
│   ├── TECHNICAL_REPORT.md
│   ├── BACKTEST_VALIDATION_REPORT.md
│   └── ...
├── scripts/
│   └── poster_component_ic_chart.py  # IC chart generation for poster
├── tests/                          # pytest test suite (14 modules, 158 tests)
├── pyproject.toml                  # Package metadata + `tiaa-pipeline` console script
├── requirements.txt
├── DEPLOYMENT.md                   # AWS deployment guide
└── README.md
```

> **Note on recent structural changes:** The repo was recently tidied — root-level
> `.py` files (`config.py`, `run_pipeline.py`, `store.py`, `signals.py`, `backtest.py`,
> etc.) are gone. Their contents moved into `src/tiaa/` submodules and the package is
> installed via `pyproject.toml`. Notebooks moved to `notebooks/`, reference PDFs to
> `docs/research/`, and `config.py` was split into the `tiaa.config` package with its
> large lookup tables lifted into `config/reference/*.json`.

## Requirements

Python 3.10+ with the packages listed in `requirements.txt`. Key dependencies:

- `beautifulsoup4` / `lxml` -- HTML parsing
- `scikit-learn` -- vectorization and cosine similarity
- `yfinance` -- stock price data for CAR
- `nltk` -- tokenization and lemmatization
- `openai` -- LLM narrative generation and embeddings (optional)
- `chromadb` -- vector store for RAG retrieval (optional)
- `psycopg2-binary` -- PostgreSQL adapter (used in Docker deployment)
- `flask` / `flask-cors` -- dashboard API backend
- `python-dotenv` -- environment variable loading

The React frontend (`dashboard/frontend/`) uses Vite and requires Node.js 18+. Key frontend dependencies: `axios`, `recharts`, `react-markdown`.

## CLI Reference

After `pip install -e .`, the orchestrator is exposed as the `tiaa-pipeline` console
script (equivalent to `python -m tiaa.pipeline.run`):

```
tiaa-pipeline [OPTIONS]

Options:
  --ciks TEXT          Comma-separated CIK numbers (default: all tickers in config)
  --skip-pull          Skip SEC filing download (use filings already on disk)
  --max-filings INT    Max filings to process per CIK
  --force              Reprocess all filings even if already up to date
  --rescore-only       Only re-compute LAS from existing DB values (no data fetching)
  --workers INT        Number of parallel CIK workers (default: PIPELINE_WORKERS=4)
```

## Advisor Dashboard

An interactive React + Flask dashboard provides a visual interface for exploring LAS results across a portfolio.

### Starting the Dashboard

**With Docker (recommended):**

```bash
cd deploy/docker
docker compose up -d --build
# Open http://localhost
```

**Without Docker (local dev):**

```bash
# Terminal 1 -- Flask API backend (port 5001)
cd dashboard/backend
python app.py

# Terminal 2 -- React frontend (port 5173, proxied to backend)
cd dashboard/frontend
npm install
npm run dev
# Open http://localhost:5173
```

### Dashboard Features

- **Sidebar** -- select tickers (S&P 500 universe), manage client profiles with risk tolerance, and view the aggregate Portfolio LAS. The ticker list adjusts its height dynamically so the LAS score is always visible. Mobile-responsive with a collapsible drawer.
- **Portfolio Overview** -- holdings table with per-ticker LAS. Unprocessed tickers show a "Process" button that triggers the pipeline directly from the UI.
- **Signal Summary** -- visual breakdown of holdings by signal category (sell/caution/hold/neutral/buy) with counts and color coding.
- **Charts** -- LAS trend chart, similarity chart, and LAS vs. CAR scatter plot (Recharts).
- **Key Risk Insights** -- top 5 highest-change filing sections rendered as bullet points with change intensity bars, plus an LLM-generated (or template fallback) thematic risk summary loaded asynchronously.
- **Filings Table** -- sortable, horizontally scrollable table of all filings with accession number, dates, similarity, CAR, and LAS.
- **Section Changes** -- expandable view of individual section-level changes per filing with AI-generated summaries, **sentiment classification** (positive / negative / neutral pill badges), sentiment rationale, and side-by-side prior vs. current text diffs.
- **Section Explorer** -- free-form section analysis tool. Pick any ticker, filing, and section to get an on-demand AI summary with sentiment classification -- not limited to the pre-computed top-changed list.
- **Chat Panel** -- conversational interface powered by OpenAI (or template fallback) for asking questions about the portfolio analysis. Supports client-aware context.
- **Pipeline Log Panel** -- real-time log output when triggering pipeline runs from the UI, with status polling.
- **Client Profiles** -- create, edit, and delete client profiles with name, risk tolerance, and investment goals. The selected profile tailors chat responses.
- **Mobile Responsive** -- fully responsive layout with collapsible sidebar, touch-friendly controls, and horizontally scrollable tables.

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/tickers` | GET | Distinct tickers in the database |
| `/api/filings?tickers=AAPL,JPM` | GET | All filings, optionally filtered by tickers |
| `/api/filings/<ticker>` | GET | Filings for a single ticker |
| `/api/portfolio?tickers=AAPL,JPM` | GET | Portfolio LAS aggregation |
| `/api/sections?tickers=AAPL&top=5` | GET | High-impact filing sections |
| `/api/sections/summarize` | POST | AI summary + sentiment for a pre-cached section change |
| `/api/sections/analyze` | POST | Free-form per-section summary + sentiment for any ticker/filing/section combination |
| `/api/risk-narrative?tickers=AAPL,JPM` | GET | LLM-generated risk narrative summary |
| `/api/filing/<cik>/<accession>/sections` | GET | Full section text for a specific filing |
| `/api/clients` | GET/POST | List or create client profiles |
| `/api/clients/<id>` | GET/PUT/DELETE | Read, update, or delete a client profile |
| `/api/chat` | POST | Chat with the advisor (message, tickers, history, client context) |
| `/api/pipeline/run` | POST | Trigger pipeline processing for given tickers (background thread) |
| `/api/pipeline/status/<job_id>` | GET | Poll pipeline job status (running/completed/failed) |

### Dashboard File Structure

```
dashboard/
├── backend/
│   ├── app.py              # Flask API server (all endpoints)
│   └── chat.py             # Chat handler (LLM + template fallback)
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js       # Dev server with API proxy to :5001
    └── src/
        ├── api.js           # Axios API client
        ├── App.jsx          # Root component and layout
        ├── App.css          # All dashboard styles
        └── components/
            ├── Sidebar.jsx
            ├── PortfolioOverview.jsx
            ├── SignalSummary.jsx
            ├── LASChart.jsx
            ├── SimilarityChart.jsx
            ├── LASvsCAR.jsx
            ├── RiskInsights.jsx
            ├── FilingsTable.jsx
            ├── SectionChanges.jsx
            ├── SectionExplorer.jsx
            ├── ChatPanel.jsx
            ├── PipelineLogPanel.jsx
            └── ClientModal.jsx
```

## AWS Deployment

The application can be deployed to a single EC2 instance using Docker Compose and Terraform. See [DEPLOYMENT.md](DEPLOYMENT.md) for the full guide covering:

- Terraform setup (EC2, security groups, SSM for secrets)
- Docker Compose with PostgreSQL, Flask/Gunicorn, and Nginx
- Pipeline execution on the instance
- Redeployment workflow
- Troubleshooting

## Scope and Future Work

- **Universe**: S&P 500 tickers pre-loaded; switchable between `"demo"` (50 tickers) and `"full"` (500) via `UNIVERSE_MODE` in `tiaa.config.sec`
- **Filing types**: 10-K annual reports with section weights; 10-Q quarterly support is configured but not fully end-to-end yet
- **Attention proxy**: Currently a placeholder (constant 0.5); will be replaced when SEC FOIA download data is integrated
- **Dense embeddings**: A `--dense` flag hook exists in `tiaa.storage.embeddings` for future `sentence-transformers` integration
- **Additional similarity measures**: MinEdit and Sim Simple from the paper can be added alongside the existing cosine and Jaccard measures
- **Sentiment classification**: Section-level sentiment (positive/negative/neutral) with rationale is supported via OpenAI; template fallback returns `"unknown"`
- **Signal refinement**: Walk-forward backtests, sector-neutral portfolio construction, and ML overlay for non-linear interactions are planned (see `Reports/NEXT_STEPS_RECOMMENDATIONS.md`)
