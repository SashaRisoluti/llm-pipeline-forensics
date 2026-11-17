import json
import sqlite3
from pathlib import Path

from opentelemetry.trace import Tracer

from pipeline.models import (
    Classification,
    DocumentType,
    ExtractedEntities,
    Summary,
)
from pipeline.orchestrator import run_pipeline
from tests.conftest import MockLLM
from tracing.exporter import ForensicsExporter
from tracing.recorder import PayloadRecorder
from tracing.setup import build_tracer
from tracing.store import connect


def build_env(
    tmp_env: dict[str, Path], llm: MockLLM
) -> tuple[sqlite3.Connection, Tracer, PayloadRecorder]:
    conn = connect(tmp_env["db"])
    recorder = PayloadRecorder()
    tracer = build_tracer(ForensicsExporter(conn, tmp_env["traces"], recorder))
    return conn, tracer, recorder


HAPPY = [
    ExtractedEntities(dates=["2026-01-01"], confidence=5),
    Classification(doc_type=DocumentType.invoice, confidence=4),
    Summary(summary="ok", confidence=5),
]


def test_happy_path_writes_five_spans(tmp_env: dict[str, Path]) -> None:
    llm = MockLLM(list(HAPPY))
    conn, tracer, recorder = build_env(tmp_env, llm)
    trace_id = run_pipeline("doc text", "d1", llm, tracer, recorder)
    steps = [r["step"] for r in conn.execute(
        "SELECT step FROM spans WHERE trace_id=? ORDER BY started_at", (trace_id,))]
    assert steps == ["pipeline", "intake", "extract", "classify", "summarize"]
    assert conn.execute(
        "SELECT status FROM traces WHERE trace_id=?", (trace_id,)
    ).fetchone()["status"] == "ok"


def test_trace_json_carries_step_payloads(tmp_env: dict[str, Path]) -> None:
    llm = MockLLM(list(HAPPY))
    conn, tracer, recorder = build_env(tmp_env, llm)
    trace_id = run_pipeline("doc text", "d1", llm, tracer, recorder)
    path = conn.execute(
        "SELECT json_path FROM traces WHERE trace_id=?", (trace_id,)
    ).fetchone()["json_path"]
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    spans = {s["step"]: s for s in doc["spans"]}
    assert spans["extract"]["output"]["dates"] == ["2026-01-01"]
    assert spans["extract"]["confidence"] == 5
    assert spans["classify"]["input"]["entities"]["dates"] == ["2026-01-01"]
    assert spans["summarize"]["prompt"]  # prompt captured
    assert doc["doc_id"] == "d1"


def test_step_failure_skips_downstream_but_flushes_trace(tmp_env: dict[str, Path]) -> None:
    llm = MockLLM([RuntimeError("LLM exploded")])  # extract raises
    conn, tracer, recorder = build_env(tmp_env, llm)
    trace_id = run_pipeline("doc text", "d1", llm, tracer, recorder)
    rows = {r["step"]: r for r in conn.execute(
        "SELECT * FROM spans WHERE trace_id=?", (trace_id,))}
    assert set(rows) == {"pipeline", "intake", "extract"}  # classify/summarize skipped
    assert rows["extract"]["status"] == "error"
    assert "LLM exploded" in rows["extract"]["error"]
    assert conn.execute(
        "SELECT status FROM traces WHERE trace_id=?", (trace_id,)
    ).fetchone()["status"] == "error"
