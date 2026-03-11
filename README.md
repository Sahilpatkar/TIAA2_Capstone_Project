# LazyPrices: SEC Filing Change Detection Pipeline

An end-to-end implementation of the [Lazy Prices](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1658471) paper (Cohen, Malloy, Nguyen) for detecting material changes in SEC 10-K filings and scoring them with a **Lazy Attention Score (LAS)**.

The pipeline pulls 10-K filings from SEC EDGAR, extracts and cleans the text, computes year-over-year similarity metrics, calculates cumulative abnormal returns around filing dates, and combines everything into a single LAS per filing. An advisor-facing query interface aggregates scores across a portfolio and highlights the most impactful disclosure changes.

## Quick Start

### Option A: Local (no Docker)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the full pipeline for Apple (CIK 320193)
python run_pipeline.py --ciks 320193

# 3. Start the dashboard
cd dashboard/backend && python app.py        # Terminal 1 (port 5001)
cd dashboard/frontend && npm install && npm run dev  # Terminal 2 (port 5173)
```

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

## Pipeline Architecture

```
SEC EDGAR ─► document_pull.py ─► Raw HTML (data/filings/entityName_cik/)
                                       │
                                extract_clean.py
                                       │
                              Cleaned text + sections (cleaned/)
                                       │
                               embeddings.py (count vectors)
                                       │
                 ┌─────────────────────┼─────────────────────┐
           similarity.py        attention_proxy.py    abnormal_returns.py
           (cosine/Jaccard)     (placeholder 0.5)     (Yahoo Finance CAR)
                 └─────────────────────┼─────────────────────┘
                                       │
                                    las.py (Lazy Attention Score)
                                       │
                                    store.py (PostgreSQL / SQLite)
                                       │
                               advisor_query.py
                          (portfolio aggregation + LLM narrative)
```

## Module Reference

| Module | Description |
|---|---|
| `config.py` | Central configuration: paths, LAS weights, CIK-ticker mapping (DJIA 30), CAR window, database URL |
| `document_pull.py` | Pull 10-K filings from SEC EDGAR; saves raw HTML and `company_facts.json` under `entityName_cik/` |
| `extract_clean.py` | Parse iXBRL HTML, strip noise (scripts, styles, XBRL blocks, numeric tables), split text by Item section |
| `embeddings.py` | Build count vectors (or TF-IDF) per document and per section using sklearn |
| `similarity.py` | Pair each 10-K with its prior-year filing, compute cosine and Jaccard similarity, derive change intensity |
| `attention_proxy.py` | MVP placeholder returning 0.5 for all filings (pending SEC FOIA download data) |
| `abnormal_returns.py` | Fetch daily prices from Yahoo Finance, compute market-adjusted CAR over a configurable event window |
| `las.py` | Combine change intensity, attention proxy, and CAR into a weighted LAS with rank or z-score normalization |
| `store.py` | Database persistence layer (PostgreSQL via Docker, SQLite fallback); upsert by `(cik, accession)` |
| `advisor_query.py` | Aggregate portfolio LAS, retrieve highest-impact disclosure sections, generate LLM or template narrative |
| `run_pipeline.py` | End-to-end CLI orchestrator that runs all stages for a given set of CIKs, with incremental processing |
| `rag/chunker.py` | Section-aware text chunker for 10-K filings with configurable max size and overlap |
| `rag/providers.py` | Provider abstractions for embeddings (OpenAI), LLM (OpenAI), and vector store (ChromaDB) |
| `rag/index.py` | CLI tool to embed and index filings into the vector store with manifest-based deduplication |
| `dashboard/backend/app.py` | Flask API server exposing all REST endpoints for the advisor dashboard |
| `dashboard/backend/chat.py` | RAG-enhanced chat handler; retrieves filing passages and structured metrics for LLM context |

## LAS Formula

```
LAS = w_change * f(change_intensity) - w_attention * f(attention_proxy) + w_car * f(|CAR|)
```

Where `f()` is a cross-sectional normalization (rank percentile by default). Weights are configurable in `config.py`:

| Weight | Default | Component |
|---|---|---|
| `w_change` | 0.50 | Year-over-year filing change intensity (1 - cosine similarity) |
| `w_attention` | 0.25 | Investor attention proxy (placeholder for MVP) |
| `w_car` | 0.25 | Absolute cumulative abnormal return around filing date |

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
python run_pipeline.py --ciks 320193 --force
```

**Version bumping:** When pipeline logic changes materially (new LAS formula, new similarity metric, etc.), bump `PIPELINE_VERSION` in `config.py`. All filings will be reprocessed on the next run because the version check will fail against older records.

## Configuration

All tunable parameters live in `config.py`:

- **DATABASE_URL** -- database connection string; reads from env, falls back to SQLite
- **PIPELINE_VERSION** -- pipeline version string (default `"1.0"`); bump to force reprocessing after logic changes
- **LAS_WEIGHTS** -- component weights for the LAS formula
- **LAS_NORMALIZATION** -- `"rank"` (percentile) or `"zscore"`
- **CAR_WINDOW** -- event window in trading days, default `(-1, 5)`
- **NUMERIC_TABLE_THRESHOLD** -- tables with more than this fraction of numeric characters are dropped (default `0.15`)
- **CIK_TO_TICKER** -- mapping of CIK integers to ticker symbols (DJIA 30 pre-loaded)
- **LLM_MODEL** -- OpenAI model for advisor narratives (default `gpt-4o-mini`)

## Advisor Narrative

The advisor query generates a structured explanation of the portfolio's LAS analysis. If the `OPENAI_API_KEY` environment variable is set, it uses the OpenAI API to produce a professional narrative. Otherwise, it falls back to a plain-text template summary.

```bash
# With LLM narrative
export OPENAI_API_KEY="sk-..."
python advisor_query.py --portfolio AAPL,JPM,KO --top 5

# Template fallback (no API key needed)
python advisor_query.py --portfolio AAPL --top 3
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

Settings in `config.py`:

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

## Data Layout

```
project_root/
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
│   │   ├── Dockerfile.backend      # Python 3.10 + Gunicorn
│   │   ├── Dockerfile.frontend     # Node 18 build + Nginx
│   │   ├── docker-compose.yml      # PostgreSQL, backend, frontend, pipeline
│   │   └── nginx.conf              # Static files + /api reverse proxy
│   ├── terraform/                  # AWS EC2 infrastructure
│   └── scripts/
│       └── user_data.sh            # EC2 bootstrap script
├── rag/
│   ├── chunker.py                  # Section-aware filing chunker
│   ├── providers.py                # Embedding, LLM, vector store abstractions
│   └── index.py                    # CLI indexing tool
├── dashboard/
│   ├── backend/
│   │   ├── app.py                  # Flask API server
│   │   └── chat.py                 # RAG-enhanced chat handler
│   └── frontend/                   # React + Vite dashboard
├── config.py
├── store.py
├── run_pipeline.py
├── DEPLOYMENT.md                   # AWS deployment guide
└── requirements.txt
```

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

```
python run_pipeline.py [OPTIONS]

Options:
  --ciks TEXT          Comma-separated CIK numbers (default: all DJIA 30)
  --skip-pull          Skip SEC filing download (use filings already on disk)
  --max-filings INT    Max filings to process per CIK
  --force              Reprocess all filings even if already up to date
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

- **Sidebar** -- select tickers (DJIA 30), manage client profiles with risk tolerance, and view the aggregate Portfolio LAS. The ticker list adjusts its height dynamically so the LAS score is always visible.
- **Portfolio Overview** -- holdings table with per-ticker LAS. Unprocessed tickers show a "Process" button that triggers the pipeline directly from the UI.
- **Charts** -- LAS trend chart, similarity chart, and LAS vs. CAR scatter plot (Recharts).
- **Key Risk Insights** -- top 5 highest-change filing sections rendered as bullet points with change intensity bars, plus an LLM-generated (or template fallback) thematic risk summary loaded asynchronously.
- **Filings Table** -- sortable table of all filings with accession number, dates, similarity, CAR, and LAS.
- **Section Changes** -- expandable view of individual section-level changes per filing with full extracted text.
- **Chat Panel** -- conversational interface powered by OpenAI (or template fallback) for asking questions about the portfolio analysis. Supports client-aware context.
- **Client Profiles** -- create, edit, and delete client profiles with name, risk tolerance, and investment goals. The selected profile tailors chat responses.

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/tickers` | GET | Distinct tickers in the database |
| `/api/filings?tickers=AAPL,JPM` | GET | All filings, optionally filtered by tickers |
| `/api/filings/<ticker>` | GET | Filings for a single ticker |
| `/api/portfolio?tickers=AAPL,JPM` | GET | Portfolio LAS aggregation |
| `/api/sections?tickers=AAPL&top=5` | GET | High-impact filing sections |
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
            ├── LASChart.jsx
            ├── SimilarityChart.jsx
            ├── LASvsCAR.jsx
            ├── RiskInsights.jsx
            ├── FilingsTable.jsx
            ├── SectionChanges.jsx
            ├── ChatPanel.jsx
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

- **MVP scope**: 10-K filings only; 10-Q support is planned
- **Attention proxy**: Currently a placeholder (constant 0.5); will be replaced when SEC FOIA download data is integrated
- **Dense embeddings**: A `--dense` flag hook exists in `embeddings.py` for future `sentence-transformers` integration
- **Additional similarity measures**: MinEdit and Sim Simple from the paper can be added alongside the existing cosine and Jaccard measures
- **RAG-enhanced chat**: Modular RAG integration for grounding chat responses in actual filing text
