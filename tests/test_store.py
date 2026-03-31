"""Tests for store.py -- LASStore database persistence layer."""

import json

import pandas as pd
import pytest

from store import _normalize_accession, LASStore


class TestNormalizeAccession:
    def test_removes_hyphens(self):
        assert _normalize_accession("0001-23-456") == "000123456"

    def test_no_hyphens(self):
        assert _normalize_accession("000123456") == "000123456"

    def test_none(self):
        assert _normalize_accession(None) is None


class TestLASStoreUpsert:
    def test_upsert_and_get_all(self, tmp_store, sample_filing_row):
        tmp_store.upsert(sample_filing_row)
        df = tmp_store.get_all_filings()
        assert len(df) == 1
        assert df.iloc[0]["ticker"] == "AAPL"

    def test_upsert_many(self, tmp_store):
        rows = [
            {
                "cik": 320193, "accession": "acc_a", "ticker": "AAPL",
                "entity_name": "Apple", "report_date": "2023-09-30",
                "change_intensity": 0.1, "las": 0.3,
            },
            {
                "cik": 19617, "accession": "acc_b", "ticker": "JPM",
                "entity_name": "JPMorgan", "report_date": "2023-12-31",
                "change_intensity": 0.2, "las": 0.5,
            },
        ]
        tmp_store.upsert_many(rows)
        df = tmp_store.get_all_filings()
        assert len(df) == 2

    def test_upsert_updates_existing(self, tmp_store, sample_filing_row):
        tmp_store.upsert(sample_filing_row)
        sample_filing_row["las"] = 0.99
        tmp_store.upsert(sample_filing_row)
        df = tmp_store.get_all_filings()
        assert len(df) == 1
        assert df.iloc[0]["las"] == pytest.approx(0.99)


class TestLASStoreQuery:
    def _seed(self, store):
        rows = [
            {
                "cik": 320193, "accession": "acc1", "ticker": "AAPL",
                "entity_name": "Apple", "report_date": "2023-09-30",
                "change_intensity": 0.1, "las": 0.3,
            },
            {
                "cik": 320193, "accession": "acc2", "ticker": "AAPL",
                "entity_name": "Apple", "report_date": "2024-09-28",
                "change_intensity": 0.2, "las": 0.5,
            },
            {
                "cik": 19617, "accession": "acc3", "ticker": "JPM",
                "entity_name": "JPMorgan", "report_date": "2023-12-31",
                "change_intensity": 0.15, "las": 0.4,
            },
        ]
        store.upsert_many(rows)

    def test_get_filings_by_cik(self, tmp_store):
        self._seed(tmp_store)
        df = tmp_store.get_filings_by_cik(320193)
        assert len(df) == 2
        assert (df["ticker"] == "AAPL").all()

    def test_get_filings_by_tickers(self, tmp_store):
        self._seed(tmp_store)
        df = tmp_store.get_filings_by_tickers(["AAPL"])
        assert len(df) == 2
        df_both = tmp_store.get_filings_by_tickers(["AAPL", "JPM"])
        assert len(df_both) == 3

    def test_get_latest_by_ticker(self, tmp_store):
        self._seed(tmp_store)
        latest = tmp_store.get_latest_by_ticker("AAPL")
        assert latest is not None
        assert latest["report_date"] == "2024-09-28"
        assert latest["las"] == pytest.approx(0.5)

    def test_get_latest_nonexistent(self, tmp_store):
        assert tmp_store.get_latest_by_ticker("ZZZZ") is None


class TestPipelineTracking:
    def test_is_processed(self, tmp_store):
        assert not tmp_store.is_processed(320193, "acc1", "1.0")
        tmp_store.mark_processed(320193, "acc1", "AAPL", "2024-11-01", "2024-09-28", "1.0")
        assert tmp_store.is_processed(320193, "acc1", "1.0")

    def test_get_unprocessed_filings(self, tmp_store):
        tmp_store.mark_processed(320193, "acc1", "AAPL", "2024-11-01", "2024-09-28", "1.0")
        filings_meta = [
            {"accession": "acc1"},
            {"accession": "acc2"},
        ]
        unprocessed = tmp_store.get_unprocessed_filings(320193, filings_meta, "1.0")
        assert len(unprocessed) == 1
        assert unprocessed[0]["accession"] == "acc2"


class TestClientCRUD:
    def test_create_and_get(self, tmp_store):
        client = tmp_store.create_client({
            "name": "Test Client",
            "risk_tolerance": "aggressive",
            "investment_goal": "growth",
            "tickers": ["AAPL", "JPM"],
        })
        assert client["name"] == "Test Client"
        assert "AAPL" in client["tickers"]

        fetched = tmp_store.get_client(client["id"])
        assert fetched is not None
        assert fetched["name"] == "Test Client"

    def test_update(self, tmp_store):
        client = tmp_store.create_client({"name": "Old Name"})
        updated = tmp_store.update_client(client["id"], {"name": "New Name"})
        assert updated["name"] == "New Name"

    def test_delete(self, tmp_store):
        client = tmp_store.create_client({"name": "To Delete"})
        assert tmp_store.delete_client(client["id"]) is True
        assert tmp_store.get_client(client["id"]) is None

    def test_delete_nonexistent(self, tmp_store):
        assert tmp_store.delete_client(99999) is False


class TestContextManager:
    def test_with_statement(self, tmp_sqlite_url):
        with LASStore(db_url=tmp_sqlite_url) as db:
            db.upsert({
                "cik": 320193, "accession": "acc1", "ticker": "AAPL",
                "entity_name": "Apple", "report_date": "2024-09-28",
            })
            df = db.get_all_filings()
            assert len(df) == 1
