from pathlib import Path

from tracing.recorder import PayloadRecorder
from tracing.store import connect


def test_connect_creates_schema(tmp_env: dict[str, Path]) -> None:
    conn = connect(tmp_env["db"])
    tables = {
        r["name"] for r in
        conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"traces", "spans", "diagnoses", "eval_cases", "eval_results"} <= tables


def test_connect_is_idempotent(tmp_env: dict[str, Path]) -> None:
    connect(tmp_env["db"]).close()
    conn = connect(tmp_env["db"])  # must not raise on existing schema
    conn.execute("INSERT INTO traces (trace_id) VALUES ('t1')")
    assert conn.execute("SELECT flagged FROM traces").fetchone()["flagged"] == 0


def test_recorder_accumulates_and_pops() -> None:
    rec = PayloadRecorder()
    rec.record(123, input={"a": 1})
    rec.record(123, output={"b": 2})
    assert rec.pop(123) == {"input": {"a": 1}, "output": {"b": 2}}
    assert rec.pop(123) == {}  # popped = gone
    assert rec.pop(999) == {}  # unknown span = empty
