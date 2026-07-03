import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    doc_id TEXT,
    created_at TEXT,
    status TEXT,
    flagged INTEGER NOT NULL DEFAULT 0,
    json_path TEXT
);
CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT,
    step TEXT,
    status TEXT,
    latency_ms REAL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    confidence INTEGER,
    error TEXT,
    started_at TEXT
);
CREATE TABLE IF NOT EXISTS diagnoses (
    trace_id TEXT PRIMARY KEY,
    root_cause_step TEXT,
    category TEXT,
    created_at TEXT,
    json TEXT
);
CREATE TABLE IF NOT EXISTS eval_cases (
    case_id TEXT PRIMARY KEY,
    trace_id TEXT,
    failing_step TEXT,
    category TEXT,
    created_at TEXT,
    json_path TEXT
);
CREATE TABLE IF NOT EXISTS eval_results (
    run_at TEXT,
    case_id TEXT,
    passed INTEGER,
    score INTEGER
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
