"""
Flask API backend for the LazyPrices Advisor Dashboard.

Serves filing data from the SQLite store and exposes a chat endpoint.
Run:  python app.py          (starts on port 5001)
"""

import json
import math
import os
import sys
import threading
import uuid

from dotenv import load_dotenv
from flask import Flask, request, Response
from flask_cors import CORS

# Add project root so we can import pipeline modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import config  # noqa: E402
from store import LASStore  # noqa: E402
from advisor_query import aggregate_las, retrieve_high_impact_sections, generate_explanation  # noqa: E402
from chat import handle_chat  # noqa: E402
from run_pipeline import run as run_pipeline  # noqa: E402

app = Flask(__name__)
CORS(app)


def _sanitize(obj):
    """Replace NaN/Infinity with None so JSON serialization is valid."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def json_response(data, status=200):
    """Return a JSON response with NaN values replaced by null."""
    body = json.dumps(_sanitize(data))
    return Response(body, status=status, mimetype="application/json")


def _get_db():
    return LASStore()


# ------------------------------------------------------------------
# GET /api/tickers  –  distinct tickers in the DB
# ------------------------------------------------------------------
@app.route("/api/tickers")
def api_tickers():
    db = _get_db()
    try:
        df = db.get_all_filings()
        if df.empty:
            return json_response([])
        tickers = sorted(df["ticker"].dropna().unique().tolist())
        return json_response(tickers)
    finally:
        db.close()


# ------------------------------------------------------------------
# GET /api/filings?tickers=AAPL,JPM  –  all filings (optional filter)
# ------------------------------------------------------------------
@app.route("/api/filings")
def api_filings():
    db = _get_db()
    try:
        tickers_param = request.args.get("tickers", "")
        if tickers_param:
            tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
            df = db.get_filings_by_tickers(tickers)
        else:
            df = db.get_all_filings()

        if df.empty:
            return json_response([])

        records = df.to_dict(orient="records")
        for r in records:
            if isinstance(r.get("section_changes_json"), str):
                try:
                    r["section_changes"] = json.loads(r["section_changes_json"])
                except (json.JSONDecodeError, TypeError):
                    r["section_changes"] = []
            else:
                r["section_changes"] = r.get("section_changes_json") or []
            r.pop("section_changes_json", None)
            r.pop("cleaned_text_path", None)

        return json_response(records)
    finally:
        db.close()


# ------------------------------------------------------------------
# GET /api/filings/<ticker>  –  filings for one ticker
# ------------------------------------------------------------------
@app.route("/api/filings/<ticker>")
def api_filings_by_ticker(ticker):
    db = _get_db()
    try:
        df = db.get_filings_by_tickers([ticker.upper()])
        if df.empty:
            return json_response([])

        records = df.to_dict(orient="records")
        for r in records:
            if isinstance(r.get("section_changes_json"), str):
                try:
                    r["section_changes"] = json.loads(r["section_changes_json"])
                except (json.JSONDecodeError, TypeError):
                    r["section_changes"] = []
            else:
                r["section_changes"] = r.get("section_changes_json") or []
            r.pop("section_changes_json", None)
            r.pop("cleaned_text_path", None)

        return json_response(records)
    finally:
        db.close()


# ------------------------------------------------------------------
# GET /api/portfolio?tickers=AAPL,JPM  –  portfolio LAS aggregation
# ------------------------------------------------------------------
@app.route("/api/portfolio")
def api_portfolio():
    tickers_param = request.args.get("tickers", "")
    if not tickers_param:
        return json_response({"error": "tickers parameter required"}, 400)

    tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
    db = _get_db()
    try:
        result = aggregate_las(tickers, db=db)
        return json_response(result)
    finally:
        db.close()


# ------------------------------------------------------------------
# GET /api/sections?tickers=AAPL&top=5  –  high-impact sections
# ------------------------------------------------------------------
@app.route("/api/sections")
def api_sections():
    tickers_param = request.args.get("tickers", "")
    if not tickers_param:
        return json_response({"error": "tickers parameter required"}, 400)

    tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
    top_n = request.args.get("top", 10, type=int)

    db = _get_db()
    try:
        sections = retrieve_high_impact_sections(tickers, top_n=top_n, db=db)
        return json_response(sections)
    finally:
        db.close()


# ------------------------------------------------------------------
# GET /api/risk-narrative?tickers=AAPL,JPM  –  LLM risk summary
# ------------------------------------------------------------------
@app.route("/api/risk-narrative")
def api_risk_narrative():
    tickers_param = request.args.get("tickers", "")
    if not tickers_param:
        return json_response({"error": "tickers parameter required"}, 400)

    tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]

    db = _get_db()
    try:
        portfolio = aggregate_las(tickers, db=db)
        high_impact = retrieve_high_impact_sections(tickers, top_n=5, db=db)
        narrative = generate_explanation(portfolio, high_impact)
        is_template = not bool(os.environ.get("OPENAI_API_KEY"))
        return json_response({
            "narrative": narrative,
            "is_template": is_template,
        })
    finally:
        db.close()


# ------------------------------------------------------------------
# GET /api/filing/<cik>/<accession>/sections  –  full section text
# ------------------------------------------------------------------
@app.route("/api/filing/<int:cik>/<accession>/sections")
def api_filing_sections(cik, accession):
    db = _get_db()
    try:
        df = db.get_filings_by_cik(cik)
        if df.empty:
            return json_response({"error": "filing not found"}, 404)

        match = df[df["accession"] == accession]
        if match.empty:
            match = df[df["accession"].str.replace("-", "") == accession.replace("-", "")]
        if match.empty:
            return json_response({"error": "filing not found"}, 404)

        row = match.iloc[0]
        cleaned_path = row.get("cleaned_text_path")
        if not cleaned_path or not os.path.exists(cleaned_path):
            return json_response({"error": "cleaned text not found"}, 404)

        with open(cleaned_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return json_response({
            "cik": int(cik),
            "accession": accession,
            "sections": data.get("sections", {}),
        })
    finally:
        db.close()


# ------------------------------------------------------------------
# Client profile CRUD
# ------------------------------------------------------------------
@app.route("/api/clients")
def api_clients():
    db = _get_db()
    try:
        clients = db.get_all_clients()
        return json_response(clients)
    finally:
        db.close()


@app.route("/api/clients", methods=["POST"])
def api_create_client():
    body = request.get_json(force=True)
    if not body.get("name"):
        return json_response({"error": "name is required"}, 400)
    db = _get_db()
    try:
        client = db.create_client(body)
        return json_response(client, 201)
    finally:
        db.close()


@app.route("/api/clients/<int:client_id>")
def api_get_client(client_id):
    db = _get_db()
    try:
        client = db.get_client(client_id)
        if not client:
            return json_response({"error": "client not found"}, 404)
        return json_response(client)
    finally:
        db.close()


@app.route("/api/clients/<int:client_id>", methods=["PUT"])
def api_update_client(client_id):
    body = request.get_json(force=True)
    db = _get_db()
    try:
        client = db.update_client(client_id, body)
        if not client:
            return json_response({"error": "client not found"}, 404)
        return json_response(client)
    finally:
        db.close()


@app.route("/api/clients/<int:client_id>", methods=["DELETE"])
def api_delete_client(client_id):
    db = _get_db()
    try:
        deleted = db.delete_client(client_id)
        if not deleted:
            return json_response({"error": "client not found"}, 404)
        return json_response({"ok": True})
    finally:
        db.close()


# ------------------------------------------------------------------
# POST /api/chat  –  chat with data
# ------------------------------------------------------------------
@app.route("/api/chat", methods=["POST"])
def api_chat():
    body = request.get_json(force=True)
    message = body.get("message", "")
    tickers = body.get("tickers", [])
    history = body.get("history", [])
    client_name = body.get("client_name")
    risk_tolerance = body.get("risk_tolerance")

    if not message:
        return json_response({"error": "message is required"}, 400)

    tickers = [t.strip().upper() for t in tickers if t.strip()]
    response_text, is_template = handle_chat(
        message, tickers, history,
        client_name=client_name,
        risk_tolerance=risk_tolerance,
    )

    return json_response({
        "response": response_text,
        "is_template": is_template,
    })


# ------------------------------------------------------------------
# Pipeline job runner (background thread)
# ------------------------------------------------------------------
_pipeline_jobs: dict[str, dict] = {}
_pipeline_lock = threading.Lock()


def _run_pipeline_thread(job_id: str, ciks: list[int]):
    """Execute the pipeline in a background thread and update job status."""
    try:
        run_pipeline(ciks)
        with _pipeline_lock:
            _pipeline_jobs[job_id]["status"] = "completed"
    except Exception as e:
        with _pipeline_lock:
            _pipeline_jobs[job_id]["status"] = "failed"
            _pipeline_jobs[job_id]["error"] = str(e)


@app.route("/api/pipeline/run", methods=["POST"])
def api_pipeline_run():
    body = request.get_json(force=True)
    tickers = body.get("tickers", [])
    if not tickers:
        return json_response({"error": "tickers list is required"}, 400)

    tickers = [t.strip().upper() for t in tickers if t.strip()]

    unknown = [t for t in tickers if t not in config.TICKER_TO_CIK]
    if unknown:
        return json_response(
            {"error": f"Unknown tickers: {', '.join(unknown)}"}, 400
        )

    ciks = [config.TICKER_TO_CIK[t] for t in tickers]
    job_id = uuid.uuid4().hex[:12]

    with _pipeline_lock:
        _pipeline_jobs[job_id] = {
            "status": "running",
            "tickers": tickers,
            "error": None,
        }

    thread = threading.Thread(
        target=_run_pipeline_thread, args=(job_id, ciks), daemon=True
    )
    thread.start()

    return json_response({"job_id": job_id, "status": "running", "tickers": tickers})


@app.route("/api/pipeline/status/<job_id>")
def api_pipeline_status(job_id):
    with _pipeline_lock:
        job = _pipeline_jobs.get(job_id)

    if not job:
        return json_response({"error": "job not found"}, 404)

    return json_response({"job_id": job_id, **job})


# ------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
