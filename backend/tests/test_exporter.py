import json

from tracing.exporter import ForensicsExporter
from tracing.recorder import PayloadRecorder
from tracing.setup import build_tracer
from tracing.store import connect


def run_fake_trace(tmp_env):
    """Emit a root span with one child through a real OTel tracer."""
    conn = connect(tmp_env["db"])
    recorder = PayloadRecorder()
    exporter = ForensicsExporter(conn, tmp_env["traces"], recorder)
    tracer = build_tracer(exporter)

    with tracer.start_as_current_span("pipeline") as root:
        recorder.record(root.get_span_context().span_id, input={"doc_id": "d1"})
        with tracer.start_as_current_span("extract") as child:
            recorder.record(
                child.get_span_context().span_id,
                input={"text": "hi"}, output={"dates": []},
                prompt="P", raw_response="R",
                tokens_in=7, tokens_out=3, confidence=4,
            )
    trace_id = format(root.get_span_context().trace_id, "032x")
    return conn, tmp_env["traces"], trace_id


def test_sqlite_rows_written(tmp_env):
    conn, _, trace_id = run_fake_trace(tmp_env)
    spans = conn.execute(
        "SELECT * FROM spans WHERE trace_id=? ORDER BY started_at", (trace_id,)
    ).fetchall()
    assert [s["step"] for s in spans] == ["pipeline", "extract"]
    extract = spans[1]
    assert extract["tokens_in"] == 7
    assert extract["confidence"] == 4
    assert extract["status"] == "ok"
    trace_row = conn.execute("SELECT * FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
    assert trace_row["doc_id"] == "d1"
    assert trace_row["status"] == "ok"


def test_json_file_has_full_payloads(tmp_env):
    _, traces_dir, trace_id = run_fake_trace(tmp_env)
    doc = json.loads((traces_dir / f"{trace_id}.json").read_text())
    assert doc["trace_id"] == trace_id
    steps = {s["step"]: s for s in doc["spans"]}
    assert steps["extract"]["prompt"] == "P"
    assert steps["extract"]["raw_response"] == "R"
    assert steps["extract"]["output"] == {"dates": []}
    assert steps["extract"]["latency_ms"] >= 0


def test_error_span_marks_trace(tmp_env):
    from opentelemetry.trace import StatusCode

    conn = connect(tmp_env["db"])
    recorder = PayloadRecorder()
    exporter = ForensicsExporter(conn, tmp_env["traces"], recorder)
    tracer = build_tracer(exporter)

    with tracer.start_as_current_span("pipeline") as root:
        with tracer.start_as_current_span("extract") as child:
            child.set_status(StatusCode.ERROR, "boom")
            recorder.record(child.get_span_context().span_id, error="boom")
    trace_id = format(root.get_span_context().trace_id, "032x")
    row = conn.execute("SELECT status FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
    assert row["status"] == "error"
    span = conn.execute(
        "SELECT * FROM spans WHERE trace_id=? AND step='extract'", (trace_id,)
    ).fetchone()
    assert span["status"] == "error"
    assert span["error"] == "boom"
