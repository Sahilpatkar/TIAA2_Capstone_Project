"""Filesystem paths and database URL."""

import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
FILINGS_DIR = os.path.join(DATA_DIR, "filings")
VECTORS_DIR = os.path.join(DATA_DIR, "vectors")
DB_PATH = os.path.join(DATA_DIR, "las_store.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")
