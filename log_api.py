"""
Read-only Dashboard API for TBCare chatbot.

Run:
    uvicorn dashboard_api:app --host 0.0.0.0 --port 8001 --reload

Edit the DB_PATH and LOG_PATH variables if needed.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sqlite3
from pathlib import Path
from collections import Counter
import re

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "leads.db"
LOG_PATH = BASE_DIR / "chatbot.log"

app = FastAPI(title="TBCare Log API", version="1.0")

app.add_middleware(
    CORSMiddleware,  
    allow_origins=["*"],      # For development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_conn():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


@app.get("/")
def home():
    return {"status": "running", "database": str(DB_PATH), "log": str(LOG_PATH)}


@app.get("/dashboard")
def dashboard():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    total = cur.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    completed = cur.execute(
        "SELECT COUNT(*) FROM leads WHERE conversation_done=1"
    ).fetchone()[0]
    booked = cur.execute(
        "SELECT COUNT(*) FROM leads WHERE booking_confirmed=1"
    ).fetchone()[0]
    active = total - completed

    conn.close()

    return {
        "total_leads": total,
        "completed_conversations": completed,
        "active_conversations": active,
        "bookings_confirmed": booked,
    }


@app.get("/leads")
def leads(
    page: int = 1,
    limit: int = 50,
    all: bool = False,
):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    total = cur.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    if all:
        rows = cur.execute(
            "SELECT * FROM leads ORDER BY updated_at DESC"
        ).fetchall()
    else:
        offset = (page - 1) * limit
        rows = cur.execute(
            "SELECT * FROM leads ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()

    conn.close()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "count": len(rows),
        "data": [dict(r) for r in rows],
    }


@app.get("/leads/{session_id}")
def lead(session_id: str):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM leads WHERE session_id=?",
        (session_id,),
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, "Lead not found")

    return dict(row)


@app.get("/conversations/{session_id}")
def conversations(session_id: str):
    conn = get_conn()
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT *
        FROM conversation_logs
        WHERE session_id=?
        ORDER BY timestamp
        """,
        (session_id,),
    ).fetchall()

    conn.close()

    return [dict(r) for r in rows]


LOG_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} [\d:,]+)\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<module>\w+)\s+"
    r"(?P<message>.*)$"
)


@app.get("/logs")
def logs(
    level: str | None = None,
    module: str | None = None,
    q: str | None = None,
    limit: int = 200,
):
    if not LOG_PATH.exists():
        raise HTTPException(404, "chatbot.log not found")

    out = []

    with LOG_PATH.open("r", encoding="utf-8", errors="ignore") as f:
        for line in reversed(f.readlines()):
            m = LOG_RE.match(line.strip())
            if not m:
                continue

            item = m.groupdict()

            if level and item["level"] != level:
                continue

            if module and item["module"] != module:
                continue

            if q and q.lower() not in line.lower():
                continue

            out.append(item)

            if len(out) >= limit:
                break

    return out


@app.get("/logs/errors")
def error_logs(limit: int = 100):
    return logs(level="ERROR", limit=limit)


@app.get("/search")
def search(q: str):
    conn = get_conn()
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT *
        FROM leads
        WHERE
            session_id LIKE ?
            OR patient_name LIKE ?
            OR phone_number LIKE ?
            OR mobile LIKE ?
            OR api_lead_id LIKE ?
            OR appointment_id LIKE ?
        """,
        tuple([f"%{q}%"] * 6),
    ).fetchall()

    conv = []
    if rows:
        sid = rows[0]["session_id"]
        conv = conn.execute(
            "SELECT * FROM conversation_logs WHERE session_id=? ORDER BY timestamp",
            (sid,),
        ).fetchall()

    conn.close()

    matching_logs = []
    if LOG_PATH.exists():
        with LOG_PATH.open("r", encoding="utf-8", errors="ignore") as f:
            matching_logs = [
                line.rstrip() for line in f if q.lower() in line.lower()
            ][:100]

    return {
        "leads": [dict(r) for r in rows],
        "conversation": [dict(r) for r in conv],
        "logs": matching_logs,
    }


@app.get("/statistics")
def statistics():
    conn = get_conn()
    conn.row_factory = sqlite3.Row

    diseases = Counter(
        r["disease_name"] or "Unknown"
        for r in conn.execute("SELECT disease_name FROM leads")
    )

    patient_types = Counter(
        r["patient_type"] or "Unknown"
        for r in conn.execute("SELECT patient_type FROM leads")
    )

    conn.close()

    return {
        "diseases": diseases,
        "patient_types": patient_types,
    }
