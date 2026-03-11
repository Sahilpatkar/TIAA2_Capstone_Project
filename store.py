"""
Database persistence layer for LAS and filing features.

Supports PostgreSQL (via psycopg2) when DATABASE_URL is set to a postgresql:// URL,
and falls back to SQLite for local development without Docker.

Usage:
    from store import LASStore
    db = LASStore()
    db.upsert(row_dict)
    rows = db.get_filings_by_tickers(["AAPL", "JPM"])
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

import pandas as pd

import config

_USE_PG = config.DATABASE_URL.startswith("postgresql://")

if _USE_PG:
    import psycopg2
    import psycopg2.extras


# ---------------------------------------------------------------------------
# Schema DDL (PostgreSQL flavour)
# ---------------------------------------------------------------------------

_PG_CREATE_FILINGS = """
CREATE TABLE IF NOT EXISTS filings (
    cik              INTEGER  NOT NULL,
    entity_name      TEXT,
    accession        TEXT     NOT NULL,
    filed_date       TEXT,
    report_date      TEXT,
    ticker           TEXT,
    similarity_cosine  DOUBLE PRECISION,
    similarity_jaccard DOUBLE PRECISION,
    change_intensity   DOUBLE PRECISION,
    attention_proxy    DOUBLE PRECISION,
    car                DOUBLE PRECISION,
    las                DOUBLE PRECISION,
    section_changes_json TEXT,
    cleaned_text_path    TEXT,
    PRIMARY KEY (cik, accession)
);
"""

_PG_CREATE_PIPELINE_RUNS = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    cik              INTEGER NOT NULL,
    accession        TEXT    NOT NULL,
    ticker           TEXT,
    filed_date       TEXT,
    report_date      TEXT,
    pipeline_version TEXT    NOT NULL,
    processed_at     TEXT    NOT NULL,
    PRIMARY KEY (cik, accession)
);
"""

_PG_CREATE_CLIENTS = """
CREATE TABLE IF NOT EXISTS clients (
    id               SERIAL PRIMARY KEY,
    name             TEXT    NOT NULL,
    risk_tolerance   TEXT    NOT NULL DEFAULT 'moderate',
    investment_goal  TEXT,
    notes            TEXT,
    is_preset        INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);
"""

_PG_CREATE_CLIENT_PORTFOLIOS = """
CREATE TABLE IF NOT EXISTS client_portfolios (
    client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    ticker     TEXT    NOT NULL,
    weight     DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    PRIMARY KEY (client_id, ticker)
);
"""

# ---------------------------------------------------------------------------
# Schema DDL (SQLite flavour)
# ---------------------------------------------------------------------------

_SQLITE_CREATE_FILINGS = """
CREATE TABLE IF NOT EXISTS filings (
    cik              INTEGER  NOT NULL,
    entity_name      TEXT,
    accession        TEXT     NOT NULL,
    filed_date       TEXT,
    report_date      TEXT,
    ticker           TEXT,
    similarity_cosine  REAL,
    similarity_jaccard REAL,
    change_intensity   REAL,
    attention_proxy    REAL,
    car                REAL,
    las                REAL,
    section_changes_json TEXT,
    cleaned_text_path    TEXT,
    PRIMARY KEY (cik, accession)
);
"""

_SQLITE_CREATE_PIPELINE_RUNS = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    cik              INTEGER NOT NULL,
    accession        TEXT    NOT NULL,
    ticker           TEXT,
    filed_date       TEXT,
    report_date      TEXT,
    pipeline_version TEXT    NOT NULL,
    processed_at     TEXT    NOT NULL,
    PRIMARY KEY (cik, accession)
);
"""

_SQLITE_CREATE_CLIENTS = """
CREATE TABLE IF NOT EXISTS clients (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT    NOT NULL,
    risk_tolerance   TEXT    NOT NULL DEFAULT 'moderate',
    investment_goal  TEXT,
    notes            TEXT,
    is_preset        INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);
"""

_SQLITE_CREATE_CLIENT_PORTFOLIOS = """
CREATE TABLE IF NOT EXISTS client_portfolios (
    client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    ticker     TEXT    NOT NULL,
    weight     REAL    NOT NULL DEFAULT 1.0,
    PRIMARY KEY (client_id, ticker)
);
"""

# ---------------------------------------------------------------------------
# Preset client profiles
# ---------------------------------------------------------------------------

_PRESET_PROFILES = [
    {
        "name": "Sahil Patkar",
        "risk_tolerance": "conservative",
        "investment_goal": "preservation",
        "notes": "Prefers stable, dividend-paying blue chips with low volatility.",
        "tickers": ["JNJ", "KO", "PG", "MCD", "WMT", "VZ", "MRK"],
    },
    {
        "name": "Sahil Patkar",
        "risk_tolerance": "moderate",
        "investment_goal": "retirement",
        "notes": "Balanced growth and value mix for long-term retirement planning.",
        "tickers": ["AAPL", "JNJ", "JPM", "HD", "MSFT", "UNH", "V"],
    },
    {
        "name": "Sahil Patkar",
        "risk_tolerance": "aggressive",
        "investment_goal": "growth",
        "notes": "Growth-oriented, comfortable with higher volatility for greater returns.",
        "tickers": ["AAPL", "MSFT", "AMGN", "CRM", "NKE", "GS", "DIS"],
    },
    {
        "name": "Patricia Williams",
        "risk_tolerance": "conservative",
        "investment_goal": "income",
        "notes": "Focus on high-dividend-yield names for steady income generation.",
        "tickers": ["VZ", "KO", "IBM", "CVX", "DOW", "MMM", "WBA"],
    },
]


def _normalize_accession(acc: str | None) -> str | None:
    """Canonical form: digits only, no hyphens."""
    return acc.replace("-", "") if acc else acc


class LASStore:
    def __init__(self, db_url: str | None = None):
        url = db_url or config.DATABASE_URL
        self._pg = url.startswith("postgresql://")

        if self._pg:
            self._conn = psycopg2.connect(url)
            self._conn.autocommit = False
            self._init_pg_schema()
        else:
            db_path = url.replace("sqlite:///", "") if url.startswith("sqlite:///") else config.DB_PATH
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            self._conn = sqlite3.connect(db_path)
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.row_factory = sqlite3.Row
            self._init_sqlite_schema()

        self._deduplicate_filings()
        self._seed_presets()

    # -- helpers for DB-agnostic execution --

    def _cursor(self):
        if self._pg:
            return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return self._conn.cursor()

    def _ph(self, count: int) -> str:
        """Return comma-separated parameter placeholders."""
        marker = "%s" if self._pg else "?"
        return ",".join([marker] * count)

    def _p(self) -> str:
        """Single parameter placeholder."""
        return "%s" if self._pg else "?"

    def _commit(self):
        self._conn.commit()

    def _execute(self, sql: str, params=None):
        cur = self._cursor()
        cur.execute(sql, params or ())
        return cur

    def _fetchall(self, sql: str, params=None) -> list[dict]:
        cur = self._cursor()
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        if self._pg:
            return [dict(r) for r in rows]
        return [dict(r) for r in rows]

    def _fetchone(self, sql: str, params=None) -> dict | None:
        cur = self._cursor()
        cur.execute(sql, params or ())
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)

    # -- schema init --

    def _init_pg_schema(self):
        cur = self._conn.cursor()
        cur.execute(_PG_CREATE_FILINGS)
        cur.execute(_PG_CREATE_PIPELINE_RUNS)
        cur.execute(_PG_CREATE_CLIENTS)
        cur.execute(_PG_CREATE_CLIENT_PORTFOLIOS)
        self._conn.commit()

    def _init_sqlite_schema(self):
        self._conn.execute(_SQLITE_CREATE_FILINGS)
        self._conn.execute(_SQLITE_CREATE_PIPELINE_RUNS)
        self._conn.execute(_SQLITE_CREATE_CLIENTS)
        self._conn.execute(_SQLITE_CREATE_CLIENT_PORTFOLIOS)
        self._conn.commit()

    # -- dedup migration (idempotent) --

    def _deduplicate_filings(self) -> None:
        p = self._p()
        like_pattern = "%-%"
        rows = self._fetchall(
            f"SELECT cik, accession FROM filings WHERE accession LIKE {p}",
            (like_pattern,),
        )
        if not rows:
            return

        removed = 0
        updated = 0
        for row in rows:
            cik, acc = row["cik"], row["accession"]
            canonical = acc.replace("-", "")
            exists = self._fetchone(
                f"SELECT 1 FROM filings WHERE cik = {p} AND accession = {p}",
                (cik, canonical),
            )
            if exists:
                self._execute(
                    f"DELETE FROM filings WHERE cik = {p} AND accession = {p}",
                    (cik, acc),
                )
                removed += 1
            else:
                self._execute(
                    f"UPDATE filings SET accession = {p} WHERE cik = {p} AND accession = {p}",
                    (canonical, cik, acc),
                )
                updated += 1

        pr_rows = self._fetchall(
            f"SELECT cik, accession FROM pipeline_runs WHERE accession LIKE {p}",
            (like_pattern,),
        )
        for row in pr_rows:
            cik, acc = row["cik"], row["accession"]
            canonical = acc.replace("-", "")
            exists = self._fetchone(
                f"SELECT 1 FROM pipeline_runs WHERE cik = {p} AND accession = {p}",
                (cik, canonical),
            )
            if exists:
                self._execute(
                    f"DELETE FROM pipeline_runs WHERE cik = {p} AND accession = {p}",
                    (cik, acc),
                )
            else:
                self._execute(
                    f"UPDATE pipeline_runs SET accession = {p} WHERE cik = {p} AND accession = {p}",
                    (canonical, cik, acc),
                )

        self._commit()
        if removed or updated:
            print(f"[store] Dedup migration: {removed} duplicates removed, {updated} accessions normalised")

    # -- write --

    def upsert(self, row: dict) -> None:
        """Insert or update a filing record."""
        section_json = row.get("section_changes_json")
        if isinstance(section_json, (list, dict)):
            section_json = json.dumps(section_json)

        params = (
            row.get("cik"),
            row.get("entity_name"),
            _normalize_accession(row.get("accession")),
            row.get("filed_date"),
            row.get("report_date"),
            row.get("ticker"),
            row.get("similarity_cosine"),
            row.get("similarity_jaccard"),
            row.get("change_intensity"),
            row.get("attention_proxy"),
            row.get("car"),
            row.get("las"),
            section_json,
            row.get("cleaned_text_path"),
        )

        if self._pg:
            self._execute(
                """
                INSERT INTO filings
                    (cik, entity_name, accession, filed_date, report_date, ticker,
                     similarity_cosine, similarity_jaccard, change_intensity,
                     attention_proxy, car, las, section_changes_json, cleaned_text_path)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (cik, accession) DO UPDATE SET
                    entity_name = EXCLUDED.entity_name,
                    filed_date = EXCLUDED.filed_date,
                    report_date = EXCLUDED.report_date,
                    ticker = EXCLUDED.ticker,
                    similarity_cosine = EXCLUDED.similarity_cosine,
                    similarity_jaccard = EXCLUDED.similarity_jaccard,
                    change_intensity = EXCLUDED.change_intensity,
                    attention_proxy = EXCLUDED.attention_proxy,
                    car = EXCLUDED.car,
                    las = EXCLUDED.las,
                    section_changes_json = EXCLUDED.section_changes_json,
                    cleaned_text_path = EXCLUDED.cleaned_text_path
                """,
                params,
            )
        else:
            self._execute(
                """
                INSERT OR REPLACE INTO filings
                    (cik, entity_name, accession, filed_date, report_date, ticker,
                     similarity_cosine, similarity_jaccard, change_intensity,
                     attention_proxy, car, las, section_changes_json, cleaned_text_path)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                params,
            )
        self._commit()

    def upsert_many(self, rows: list[dict]) -> None:
        for r in rows:
            self.upsert(r)

    # -- read helpers --

    def _rows_to_df(self, rows) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def get_all_filings(self) -> pd.DataFrame:
        rows = self._fetchall("SELECT * FROM filings ORDER BY ticker, report_date")
        return self._rows_to_df(rows)

    def get_filings_by_cik(self, cik: int) -> pd.DataFrame:
        p = self._p()
        rows = self._fetchall(
            f"SELECT * FROM filings WHERE cik = {p} ORDER BY report_date", (cik,)
        )
        return self._rows_to_df(rows)

    def get_filings_by_tickers(self, tickers: list[str]) -> pd.DataFrame:
        placeholders = ",".join([self._p()] * len(tickers))
        rows = self._fetchall(
            f"SELECT * FROM filings WHERE ticker IN ({placeholders}) ORDER BY ticker, report_date",
            [t.upper() for t in tickers],
        )
        return self._rows_to_df(rows)

    def get_latest_by_ticker(self, ticker: str) -> dict | None:
        p = self._p()
        return self._fetchone(
            f"SELECT * FROM filings WHERE ticker = {p} ORDER BY report_date DESC LIMIT 1",
            (ticker.upper(),),
        )

    # -- pipeline run tracking --

    def is_processed(self, cik: int, accession: str, pipeline_version: str) -> bool:
        p = self._p()
        row = self._fetchone(
            f"SELECT 1 FROM pipeline_runs WHERE cik = {p} AND accession = {p} AND pipeline_version = {p}",
            (cik, _normalize_accession(accession), pipeline_version),
        )
        return row is not None

    def get_unprocessed_filings(
        self, cik: int, filings_meta: list[dict], pipeline_version: str
    ) -> list[dict]:
        return [
            fm for fm in filings_meta
            if not self.is_processed(cik, fm["accession"], pipeline_version)
        ]

    def mark_processed(
        self,
        cik: int,
        accession: str,
        ticker: str | None,
        filed_date: str | None,
        report_date: str | None,
        pipeline_version: str,
    ) -> None:
        params = (
            cik,
            _normalize_accession(accession),
            ticker,
            filed_date,
            report_date,
            pipeline_version,
            datetime.now(timezone.utc).isoformat(),
        )

        if self._pg:
            self._execute(
                """
                INSERT INTO pipeline_runs
                    (cik, accession, ticker, filed_date, report_date,
                     pipeline_version, processed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cik, accession) DO UPDATE SET
                    ticker = EXCLUDED.ticker,
                    filed_date = EXCLUDED.filed_date,
                    report_date = EXCLUDED.report_date,
                    pipeline_version = EXCLUDED.pipeline_version,
                    processed_at = EXCLUDED.processed_at
                """,
                params,
            )
        else:
            self._execute(
                """
                INSERT OR REPLACE INTO pipeline_runs
                    (cik, accession, ticker, filed_date, report_date,
                     pipeline_version, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                params,
            )
        self._commit()

    # -- client profiles --

    def _seed_presets(self) -> None:
        p = self._p()
        row = self._fetchone(f"SELECT COUNT(*) as cnt FROM clients WHERE is_preset = 1")
        if row["cnt"] > 0:
            return
        now = datetime.now(timezone.utc).isoformat()
        for profile in _PRESET_PROFILES:
            if self._pg:
                cur = self._execute(
                    f"""
                    INSERT INTO clients (name, risk_tolerance, investment_goal, notes,
                                         is_preset, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 1, %s, %s)
                    RETURNING id
                    """,
                    (
                        profile["name"],
                        profile["risk_tolerance"],
                        profile["investment_goal"],
                        profile["notes"],
                        now,
                        now,
                    ),
                )
                client_id = cur.fetchone()["id"]
            else:
                cur = self._execute(
                    """
                    INSERT INTO clients (name, risk_tolerance, investment_goal, notes,
                                         is_preset, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        profile["name"],
                        profile["risk_tolerance"],
                        profile["investment_goal"],
                        profile["notes"],
                        now,
                        now,
                    ),
                )
                client_id = cur.lastrowid
            for ticker in profile["tickers"]:
                self._execute(
                    f"INSERT INTO client_portfolios (client_id, ticker, weight) VALUES ({self._ph(3)})",
                    (client_id, ticker, 1.0),
                )
        self._commit()

    def get_all_clients(self) -> list[dict]:
        p = self._p()
        clients_rows = self._fetchall(
            "SELECT * FROM clients ORDER BY is_preset DESC, name"
        )
        clients = []
        for client in clients_rows:
            portfolio_rows = self._fetchall(
                f"SELECT ticker, weight FROM client_portfolios WHERE client_id = {p} ORDER BY ticker",
                (client["id"],),
            )
            client["tickers"] = [r["ticker"] for r in portfolio_rows]
            client["weights"] = [r["weight"] for r in portfolio_rows]
            clients.append(client)
        return clients

    def get_client(self, client_id: int) -> dict | None:
        p = self._p()
        client = self._fetchone(
            f"SELECT * FROM clients WHERE id = {p}", (client_id,)
        )
        if not client:
            return None
        portfolio_rows = self._fetchall(
            f"SELECT ticker, weight FROM client_portfolios WHERE client_id = {p} ORDER BY ticker",
            (client_id,),
        )
        client["tickers"] = [r["ticker"] for r in portfolio_rows]
        client["weights"] = [r["weight"] for r in portfolio_rows]
        return client

    def create_client(self, data: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        if self._pg:
            cur = self._execute(
                """
                INSERT INTO clients (name, risk_tolerance, investment_goal, notes,
                                     is_preset, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 0, %s, %s)
                RETURNING id
                """,
                (
                    data["name"],
                    data.get("risk_tolerance", "moderate"),
                    data.get("investment_goal"),
                    data.get("notes"),
                    now,
                    now,
                ),
            )
            client_id = cur.fetchone()["id"]
        else:
            cur = self._execute(
                """
                INSERT INTO clients (name, risk_tolerance, investment_goal, notes,
                                     is_preset, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    data["name"],
                    data.get("risk_tolerance", "moderate"),
                    data.get("investment_goal"),
                    data.get("notes"),
                    now,
                    now,
                ),
            )
            client_id = cur.lastrowid
        tickers = data.get("tickers", [])
        weights = data.get("weights", [1.0] * len(tickers))
        for i, ticker in enumerate(tickers):
            w = weights[i] if i < len(weights) else 1.0
            self._execute(
                f"INSERT INTO client_portfolios (client_id, ticker, weight) VALUES ({self._ph(3)})",
                (client_id, ticker.upper(), w),
            )
        self._commit()
        return self.get_client(client_id)

    def update_client(self, client_id: int, data: dict) -> dict | None:
        p = self._p()
        existing = self.get_client(client_id)
        if not existing:
            return None
        now = datetime.now(timezone.utc).isoformat()
        self._execute(
            f"""
            UPDATE clients
            SET name = {p}, risk_tolerance = {p}, investment_goal = {p}, notes = {p}, updated_at = {p}
            WHERE id = {p}
            """,
            (
                data.get("name", existing["name"]),
                data.get("risk_tolerance", existing["risk_tolerance"]),
                data.get("investment_goal", existing["investment_goal"]),
                data.get("notes", existing["notes"]),
                now,
                client_id,
            ),
        )
        if "tickers" in data:
            self._execute(
                f"DELETE FROM client_portfolios WHERE client_id = {p}", (client_id,)
            )
            tickers = data["tickers"]
            weights = data.get("weights", [1.0] * len(tickers))
            for i, ticker in enumerate(tickers):
                w = weights[i] if i < len(weights) else 1.0
                self._execute(
                    f"INSERT INTO client_portfolios (client_id, ticker, weight) VALUES ({self._ph(3)})",
                    (client_id, ticker.upper(), w),
                )
        self._commit()
        return self.get_client(client_id)

    def delete_client(self, client_id: int) -> bool:
        p = self._p()
        row = self._fetchone(
            f"SELECT id FROM clients WHERE id = {p}", (client_id,)
        )
        if not row:
            return False
        self._execute(
            f"DELETE FROM client_portfolios WHERE client_id = {p}", (client_id,)
        )
        self._execute(
            f"DELETE FROM clients WHERE id = {p}", (client_id,)
        )
        self._commit()
        return True

    # -- lifecycle --

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
