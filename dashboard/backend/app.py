"""
Flask API backend for the LazyPrices Advisor Dashboard.

Serves filing data from the SQLite store and exposes a chat endpoint.
Run:  python app.py          (starts on port 5001)
"""

import json
import logging
import math
import os
import sys
import threading
import time
import uuid

from dotenv import load_dotenv
from flask import Flask, request, Response
from flask_cors import CORS

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import config  
from store import LASStore  
from advisor_query import aggregate_las, retrieve_high_impact_sections, generate_explanation, summarize_section_change  # noqa: E402
from chat import handle_chat  
app = Flask(__name__)
CORS(app)


def _sanitize(obj):
    
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def json_response(data, status=200):
    
    body = json.dumps(_sanitize(data))
    return Response(body, status=status, mimetype="application/json")


def _get_db():
    return LASStore()



# GET /api/tickers  –  distinct tickers in the DB, with sector/industry metadata
@app.route("/api/tickers")
def api_tickers():
    db = _get_db()
    try:
        df = db.get_all_filings()
        if df.empty:
            return json_response([])
        tickers = sorted(df["ticker"].dropna().unique().tolist())
        result = []
        for t in tickers:
            meta = config.TICKER_SECTOR_INDUSTRY.get(t, {})
            result.append({
                "ticker": t,
                "sector": meta.get("sector", "Other"),
                "industry": meta.get("industry", "Other"),
            })
        return json_response(result)
    finally:
        db.close()



# GET /api/tickers/all  –  full S&P 500 universe with processed flag
@app.route("/api/tickers/all")
def api_tickers_all():
    db = _get_db()
    try:
        df = db.get_all_filings()
        processed = set(df["ticker"].dropna().unique()) if not df.empty else set()
        result = []
        for ticker, meta in sorted(config.TICKER_SECTOR_INDUSTRY.items()):
            result.append({
                "ticker": ticker,
                "sector": meta.get("sector", "Other"),
                "industry": meta.get("industry", "Other"),
                "processed": ticker in processed,
            })
        return json_response(result)
    finally:
        db.close()



# GET /api/filings?tickers=AAPL,JPM  –  all filings (optional filter)
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



# GET /api/filings/<ticker>  –  filings for one ticker
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



# GET /api/portfolio?tickers=AAPL,JPM&risk_tolerance=moderate  –  portfolio LAS + signals
@app.route("/api/portfolio")
def api_portfolio():
    tickers_param = request.args.get("tickers", "")
    if not tickers_param:
        return json_response({"error": "tickers parameter required"}, 400)

    tickers = [t.strip().upper() for t in tickers_param.split(",") if t.strip()]
    risk_tolerance = request.args.get("risk_tolerance", "moderate")
    db = _get_db()
    try:
        result = aggregate_las(tickers, db=db, risk_tolerance=risk_tolerance)
        return json_response(result)
    finally:
        db.close()



# GET /api/sections?tickers=AAPL&top=5  –  high-impact sections
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


# POST /api/sections/summarize  –  AI summary of what changed in one section
@app.route("/api/sections/summarize", methods=["POST"])
def api_sections_summarize():
    body = request.get_json(silent=True) or {}
    ticker = body.get("ticker", "")
    section = body.get("section", "")
    snippet_old = body.get("snippet_old", "")
    snippet_new = body.get("snippet_new", "")
    if not ticker or not section:
        return json_response({"error": "ticker and section are required"}, 400)
    result = summarize_section_change(ticker, section, snippet_old, snippet_new)
    return json_response(result)


# POST /api/sections/analyze  –  free-form per-section summary+sentiment
# Body: {ticker, section, accession?}
# Loads the ticker's filings, picks current (accession if provided else latest)
# and its immediate predecessor, pulls the requested section text from each
# filing's cleaned_text_path, and runs the same summarize_section_change
# pipeline. Unlike /api/sections/summarize this works for ANY section key, not
# just those pre-cached into section_changes_json.
_ANALYZE_SNIPPET_CHARS = 2000


def _load_section_text(cleaned_path: str, section_key: str) -> str | None:
    if not cleaned_path or not os.path.exists(cleaned_path):
        return None
    try:
        with open(cleaned_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    sections = data.get("sections", {}) or {}
    text = sections.get(section_key)
    if not isinstance(text, str) or not text.strip():
        return None
    return text.strip()


@app.route("/api/sections/analyze", methods=["POST"])
def api_sections_analyze():
    body = request.get_json(silent=True) or {}
    ticker = (body.get("ticker") or "").strip().upper()
    section = (body.get("section") or "").strip()
    accession = (body.get("accession") or "").strip() or None
    if not ticker or not section:
        return json_response({"error": "ticker and section are required"}, 400)

    db = _get_db()
    try:
        df = db.get_filings_by_tickers([ticker])
        if df.empty:
            return json_response({"error": f"no filings found for {ticker}"}, 404)

        df = df.sort_values("report_date", ascending=False).reset_index(drop=True)

        if accession:
            norm = accession.replace("-", "")
            match_idx = df.index[
                (df["accession"] == accession)
                | (df["accession"].str.replace("-", "") == norm)
            ]
            if len(match_idx) == 0:
                return json_response({"error": "accession not found for ticker"}, 404)
            current_idx = int(match_idx[0])
        else:
            current_idx = 0

        if current_idx + 1 >= len(df):
            return json_response(
                {"error": "no prior filing to compare against"}, 400
            )

        current_row = df.iloc[current_idx]
        prior_row = df.iloc[current_idx + 1]

        text_new = _load_section_text(current_row.get("cleaned_text_path"), section)
        text_old = _load_section_text(prior_row.get("cleaned_text_path"), section)

        if text_new is None and text_old is None:
            return json_response(
                {"error": f"section '{section}' not found in either filing"}, 400
            )
        if text_new is None:
            return json_response(
                {"error": f"section '{section}' missing from current filing"}, 400
            )
        if text_old is None:
            return json_response(
                {"error": f"section '{section}' missing from prior filing"}, 400
            )

        snippet_old = text_old[:_ANALYZE_SNIPPET_CHARS]
        snippet_new = text_new[:_ANALYZE_SNIPPET_CHARS]

        result = summarize_section_change(ticker, section, snippet_old, snippet_new)

        return json_response({
            "ticker": ticker,
            "section": section,
            "current": {
                "accession": current_row.get("accession"),
                "report_date": str(current_row.get("report_date") or ""),
                "form": current_row.get("form"),
            },
            "prior": {
                "accession": prior_row.get("accession"),
                "report_date": str(prior_row.get("report_date") or ""),
                "form": prior_row.get("form"),
            },
            "snippet_old": snippet_old,
            "snippet_new": snippet_new,
            **result,
        })
    finally:
        db.close()


# GET /api/risk-narrative?tickers=AAPL,JPM  –  LLM risk summary
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



# GET /api/filing/<cik>/<accession>/sections  –  full section text
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



# Client profile CRUD
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



# POST /api/chat  –  chat with data
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



# ---------------------------------------------------------------------------
# Pipeline job store — file-based JSON so all gunicorn workers can access it
# ---------------------------------------------------------------------------

import subprocess
import tempfile

_JOBS_DIR = os.path.join(tempfile.gettempdir(), "lazyprices_pipeline_jobs")
os.makedirs(_JOBS_DIR, exist_ok=True)


def _job_path(job_id: str) -> str:
    return os.path.join(_JOBS_DIR, f"{job_id}.json")


def _save_job(job_id: str, job: dict):
    """Atomically write job state to disk."""
    path = _job_path(job_id)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(job, f)
    os.replace(tmp, path)


def _load_job(job_id: str) -> dict | None:
    path = _job_path(job_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _run_pipeline_subprocess(job_id: str, ciks: list[int]):
    """Launch the pipeline as a subprocess that writes logs to the job file.

    A thin wrapper script is executed so the heavy CPU work (NLP, vectorisation)
    happens in a separate process and does not block the gunicorn web server.
    """
    # Build a small inline Python script that:
    # 1. Runs the pipeline with a custom logging handler
    # 2. Streams stage/log JSON lines to stdout
    # 3. Prints a final status line
    cik_csv = ",".join(str(c) for c in ciks)
    script = f"""
import json, logging, sys, os, time
# cwd is set to PROJECT_ROOT by the parent process
sys.path.insert(0, os.getcwd())

import config
from run_pipeline import run as run_pipeline

import re as _re

# Summary keywords — stage-start messages the user cares about
_SUMMARY_RE = _re.compile(
    r'(Downloading|Cleaning|Building|Computing|Fetching|Saving|Completed|Processing CIK)',
    _re.IGNORECASE,
)
# Detail noise — file paths, accession IDs, skip/new markers, separators
_DETAIL_RE = _re.compile(
    r'(Already on disk|will process|already processed|already up to date|Entity dir|=====|skipped|new\])',
    _re.IGNORECASE,
)

class StreamHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record).strip()
        if not msg or msg.startswith('==='):
            return
        stage = ""
        if msg.startswith("["):
            i = msg.find("]")
            if i > 0:
                stage = msg[1:i].strip()
        # Classify as summary or detail
        if _SUMMARY_RE.search(msg):
            level = "summary"
        elif _DETAIL_RE.search(msg) or not stage:
            level = "detail"
        else:
            level = "detail"
        line = json.dumps({{"ts": record.created, "msg": msg, "stage": stage, "level": level}})
        sys.stdout.write(line + "\\n")
        sys.stdout.flush()

logger = logging.getLogger("pipeline")
logger.setLevel(logging.INFO)
logger.addHandler(StreamHandler())

ciks = [{cik_csv}]
try:
    run_pipeline(ciks)
    print(json.dumps({{"_status": "completed"}}))
except Exception as e:
    print(json.dumps({{"_status": "failed", "_error": str(e)}}))
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=PROJECT_ROOT,
        text=True,
        bufsize=1,  # line-buffered
    )

    # Reader thread: reads subprocess stdout line-by-line and updates job file
    def _reader():
        job = _load_job(job_id) or {
            "status": "running", "tickers": [], "error": None,
            "logs": [], "current_stage": "",
        }
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if "_status" in data:
                job["status"] = data["_status"]
                job["error"] = data.get("_error")
            else:
                job["logs"].append(data)
                if data.get("stage"):
                    job["current_stage"] = data["stage"]
            _save_job(job_id, job)

        proc.wait()
        if job["status"] == "running":
            stderr = (proc.stderr.read() or "").strip()
            job["status"] = "failed"
            job["error"] = stderr or f"Process exited with code {proc.returncode}"
            _save_job(job_id, job)

    t = threading.Thread(target=_reader, daemon=True)
    t.start()


@app.route("/api/pipeline/run", methods=["POST"])
def api_pipeline_run():
    body = request.get_json(force=True)
    tickers = body.get("tickers", [])
    if not tickers:
        return json_response({"error": "tickers list is required"}, 400)

    tickers = [t.strip().upper() for t in tickers if t.strip()]

    # Use full (unfiltered) mapping so users can process tickers outside the demo subset
    full_map = getattr(config, "FULL_TICKER_TO_CIK", config.TICKER_TO_CIK)
    unknown = [t for t in tickers if t not in full_map]
    valid = [t for t in tickers if t in full_map]

    # If ALL tickers are unknown, return error
    if not valid:
        return json_response(
            {"error": f"Unknown tickers: {', '.join(unknown)}. No CIK mapping found — these may be delisted."}, 400
        )

    ciks = [full_map[t] for t in valid]
    job_id = uuid.uuid4().hex[:12]

    # Seed logs with skip warnings for unknown tickers
    initial_logs = []
    for t in unknown:
        initial_logs.append({
            "ts": time.time(),
            "msg": f"Skipped {t}: no CIK mapping found (may be delisted or not in S&P 500)",
            "stage": "skip",
            "level": "summary",
        })

    job = {
        "status": "running",
        "tickers": valid,
        "skipped": unknown,
        "error": None,
        "logs": initial_logs,
        "current_stage": "",
    }
    _save_job(job_id, job)

    _run_pipeline_subprocess(job_id, ciks)

    resp = {"job_id": job_id, "status": "running", "tickers": valid}
    if unknown:
        resp["skipped"] = unknown
        resp["warning"] = f"Skipped {', '.join(unknown)}: no CIK mapping found"
    return json_response(resp)


@app.route("/api/pipeline/status/<job_id>")
def api_pipeline_status(job_id):
    job = _load_job(job_id)
    if not job:
        return json_response({"error": "job not found"}, 404)

    return json_response({
        "job_id": job_id,
        "status": job["status"],
        "tickers": job["tickers"],
        "error": job["error"],
        "current_stage": job.get("current_stage", ""),
        "log_count": len(job.get("logs", [])),
    })


# GET /api/pipeline/logs/<job_id>  –  SSE stream of pipeline log messages
@app.route("/api/pipeline/logs/<job_id>")
def api_pipeline_logs(job_id):
    def generate():
        last_index = 0
        while True:
            job = _load_job(job_id)
            if not job:
                yield f"data: {json.dumps({'type': 'error', 'msg': 'job not found'})}\n\n"
                return

            logs = job.get("logs", [])
            new_logs = logs[last_index:]
            status = job["status"]

            for entry in new_logs:
                yield f"data: {json.dumps({'type': 'log', **entry})}\n\n"
                last_index += 1

            if status in ("completed", "failed"):
                yield f"data: {json.dumps({'type': 'done', 'status': status, 'error': job.get('error')})}\n\n"
                return

            time.sleep(0.5)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
