"""
SQLite persistence layer for LAS and filing features.

Schema: one row per filing, upserted by (cik, accession).
DB file lives at config.DB_PATH  (data/las_store.db).

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

_CREATE_TABLE = """
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

_CREATE_PIPELINE_RUNS = """
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

_CREATE_CLIENTS = """
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

_CREATE_CLIENT_PORTFOLIOS = """
CREATE TABLE IF NOT EXISTS client_portfolios (
    client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    ticker     TEXT    NOT NULL,
    weight     REAL    NOT NULL DEFAULT 1.0,
    PRIMARY KEY (client_id, ticker)
);
"""

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
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_PIPELINE_RUNS)
        self._conn.execute(_CREATE_CLIENTS)
        self._conn.execute(_CREATE_CLIENT_PORTFOLIOS)
        self._conn.commit()
        self._deduplicate_filings()
        self._seed_presets()

    
    # One-time migration: normalise accession numbers (idempotent)


    def _deduplicate_filings(self) -> None:
        """Remove duplicate filings caused by hyphenated vs non-hyphenated accession numbers."""
        cur = self._conn.execute(
            "SELECT cik, accession FROM filings WHERE accession LIKE '%-%'"
        )
        hyphenated = cur.fetchall()
        if not hyphenated:
            return

        removed = 0
        updated = 0
        for row in hyphenated:
            cik, acc = row["cik"], row["accession"]
            canonical = acc.replace("-", "")
            exists = self._conn.execute(
                "SELECT 1 FROM filings WHERE cik = ? AND accession = ?",
                (cik, canonical),
            ).fetchone()
            if exists:
                self._conn.execute(
                    "DELETE FROM filings WHERE cik = ? AND accession = ?",
                    (cik, acc),
                )
                removed += 1
            else:
                self._conn.execute(
                    "UPDATE filings SET accession = ? WHERE cik = ? AND accession = ?",
                    (canonical, cik, acc),
                )
                updated += 1

        pr_cur = self._conn.execute(
            "SELECT cik, accession FROM pipeline_runs WHERE accession LIKE '%-%'"
        )
        for row in pr_cur.fetchall():
            cik, acc = row["cik"], row["accession"]
            canonical = acc.replace("-", "")
            exists = self._conn.execute(
                "SELECT 1 FROM pipeline_runs WHERE cik = ? AND accession = ?",
                (cik, canonical),
            ).fetchone()
            if exists:
                self._conn.execute(
                    "DELETE FROM pipeline_runs WHERE cik = ? AND accession = ?",
                    (cik, acc),
                )
            else:
                self._conn.execute(
                    "UPDATE pipeline_runs SET accession = ? WHERE cik = ? AND accession = ?",
                    (canonical, cik, acc),
                )

        self._conn.commit()
        if removed or updated:
            print(f"[store] Dedup migration: {removed} duplicates removed, {updated} accessions normalised")


    # Write


    def upsert(self, row: dict) -> None:
        """Insert or replace a filing record."""
        section_json = row.get("section_changes_json")
        if isinstance(section_json, (list, dict)):
            section_json = json.dumps(section_json)

        self._conn.execute(
            """
            INSERT OR REPLACE INTO filings
                (cik, entity_name, accession, filed_date, report_date, ticker,
                 similarity_cosine, similarity_jaccard, change_intensity,
                 attention_proxy, car, las, section_changes_json, cleaned_text_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
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
            ),
        )
        self._conn.commit()

    def upsert_many(self, rows: list[dict]) -> None:
        for r in rows:
            self.upsert(r)


    # Read helpers


    def _rows_to_df(self, rows) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([dict(r) for r in rows])

    def get_all_filings(self) -> pd.DataFrame:
        cur = self._conn.execute("SELECT * FROM filings ORDER BY ticker, report_date")
        return self._rows_to_df(cur.fetchall())

    def get_filings_by_cik(self, cik: int) -> pd.DataFrame:
        cur = self._conn.execute(
            "SELECT * FROM filings WHERE cik = ? ORDER BY report_date", (cik,)
        )
        return self._rows_to_df(cur.fetchall())

    def get_filings_by_tickers(self, tickers: list[str]) -> pd.DataFrame:
        placeholders = ",".join("?" for _ in tickers)
        cur = self._conn.execute(
            f"SELECT * FROM filings WHERE ticker IN ({placeholders}) ORDER BY ticker, report_date",
            [t.upper() for t in tickers],
        )
        return self._rows_to_df(cur.fetchall())

    def get_latest_by_ticker(self, ticker: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT * FROM filings WHERE ticker = ? ORDER BY report_date DESC LIMIT 1",
            (ticker.upper(),),
        )
        row = cur.fetchone()
        return dict(row) if row else None


    # Pipeline run tracking


    def is_processed(self, cik: int, accession: str, pipeline_version: str) -> bool:
        """Return True if this filing was already processed at the given version."""
        cur = self._conn.execute(
            "SELECT 1 FROM pipeline_runs WHERE cik = ? AND accession = ? AND pipeline_version = ?",
            (cik, _normalize_accession(accession), pipeline_version),
        )
        return cur.fetchone() is not None

    def get_unprocessed_filings(
        self, cik: int, filings_meta: list[dict], pipeline_version: str
    ) -> list[dict]:
        """Filter *filings_meta* to only those not yet processed at *pipeline_version*."""
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
        """Record that a filing has been fully processed."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO pipeline_runs
                (cik, accession, ticker, filed_date, report_date,
                 pipeline_version, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cik,
                _normalize_accession(accession),
                ticker,
                filed_date,
                report_date,
                pipeline_version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()


    # Client profiles


    def _seed_presets(self) -> None:
        """Insert preset client profiles on first run (idempotent)."""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM clients WHERE is_preset = 1"
        )
        if cur.fetchone()[0] > 0:
            return
        now = datetime.now(timezone.utc).isoformat()
        for profile in _PRESET_PROFILES:
            cur = self._conn.execute(
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
                self._conn.execute(
                    "INSERT INTO client_portfolios (client_id, ticker, weight) VALUES (?, ?, 1.0)",
                    (client_id, ticker),
                )
        self._conn.commit()

    def get_all_clients(self) -> list[dict]:
        """Return all clients with their portfolio tickers."""
        cur = self._conn.execute(
            "SELECT * FROM clients ORDER BY is_preset DESC, name"
        )
        clients = []
        for row in cur.fetchall():
            client = dict(row)
            pcur = self._conn.execute(
                "SELECT ticker, weight FROM client_portfolios WHERE client_id = ? ORDER BY ticker",
                (client["id"],),
            )
            portfolio_rows = pcur.fetchall()
            client["tickers"] = [r["ticker"] for r in portfolio_rows]
            client["weights"] = [r["weight"] for r in portfolio_rows]
            clients.append(client)
        return clients

    def get_client(self, client_id: int) -> dict | None:
        cur = self._conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
        row = cur.fetchone()
        if not row:
            return None
        client = dict(row)
        pcur = self._conn.execute(
            "SELECT ticker, weight FROM client_portfolios WHERE client_id = ? ORDER BY ticker",
            (client_id,),
        )
        portfolio_rows = pcur.fetchall()
        client["tickers"] = [r["ticker"] for r in portfolio_rows]
        client["weights"] = [r["weight"] for r in portfolio_rows]
        return client

    def create_client(self, data: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
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
            self._conn.execute(
                "INSERT INTO client_portfolios (client_id, ticker, weight) VALUES (?, ?, ?)",
                (client_id, ticker.upper(), w),
            )
        self._conn.commit()
        return self.get_client(client_id)

    def update_client(self, client_id: int, data: dict) -> dict | None:
        existing = self.get_client(client_id)
        if not existing:
            return None
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE clients
            SET name = ?, risk_tolerance = ?, investment_goal = ?, notes = ?, updated_at = ?
            WHERE id = ?
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
            self._conn.execute(
                "DELETE FROM client_portfolios WHERE client_id = ?", (client_id,)
            )
            tickers = data["tickers"]
            weights = data.get("weights", [1.0] * len(tickers))
            for i, ticker in enumerate(tickers):
                w = weights[i] if i < len(weights) else 1.0
                self._conn.execute(
                    "INSERT INTO client_portfolios (client_id, ticker, weight) VALUES (?, ?, ?)",
                    (client_id, ticker.upper(), w),
                )
        self._conn.commit()
        return self.get_client(client_id)

    def delete_client(self, client_id: int) -> bool:
        cur = self._conn.execute("SELECT id FROM clients WHERE id = ?", (client_id,))
        if not cur.fetchone():
            return False
        self._conn.execute("DELETE FROM client_portfolios WHERE client_id = ?", (client_id,))
        self._conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        self._conn.commit()
        return True


    # Lifecycle


    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
