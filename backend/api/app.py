import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from evals.runner import run_evals
from evals.store import EvalCase, create_case
from forensics.engine import diagnose
from pipeline.models import Diagnosis
from pipeline.orchestrator import run_pipeline
from tracing.exporter import ForensicsExporter
from tracing.recorder import PayloadRecorder
from tracing.setup import build_tracer
from tracing.store import connect


class RunRequest(BaseModel):
    text: str
    doc_id: str


class EvalCreateRequest(BaseModel):
    trace_id: str
    corrected_output: dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_app(data_dir: Path, llm=None) -> FastAPI:
    data_dir = Path(data_dir)
    conn = connect(data_dir / "forensics.db")
    recorder = PayloadRecorder()
    tracer = build_tracer(ForensicsExporter(conn, data_dir / "traces", recorder))
    evals_dir = data_dir / "evals"
    if llm is None:
        from pipeline.llm import GeminiClient
        llm = GeminiClient()

    app = FastAPI(title="Failure Forensics")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    def load_trace(trace_id: str) -> dict:
        row = conn.execute(
            "SELECT json_path FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
        if row is None:
            raise HTTPException(404, f"trace {trace_id} not found")
        return json.loads(Path(row["json_path"]).read_text(encoding="utf-8"))

    @app.post("/api/runs")
    def run(req: RunRequest):
        trace_id = run_pipeline(req.text, req.doc_id, llm, tracer, recorder)
        return {"trace_id": trace_id}

    @app.get("/api/traces")
    def list_traces():
        rows = conn.execute(
            "SELECT t.*, d.root_cause_step, d.category FROM traces t "
            "LEFT JOIN diagnoses d ON d.trace_id = t.trace_id "
            "ORDER BY t.created_at DESC").fetchall()
        return [dict(r) for r in rows]

    @app.get("/api/traces/{trace_id}")
    def get_trace(trace_id: str):
        return load_trace(trace_id)

    @app.post("/api/traces/{trace_id}/flag")
    def flag(trace_id: str):
        trace_doc = load_trace(trace_id)
        diagnosis = diagnose(trace_doc, llm)
        conn.execute(
            "INSERT OR REPLACE INTO diagnoses "
            "(trace_id, root_cause_step, category, created_at, json) VALUES (?,?,?,?,?)",
            (trace_id, diagnosis.root_cause_step, diagnosis.category.value,
             _now(), diagnosis.model_dump_json()),
        )
        conn.execute("UPDATE traces SET flagged=1 WHERE trace_id=?", (trace_id,))
        conn.commit()
        return diagnosis.model_dump()

    @app.get("/api/traces/{trace_id}/diagnosis")
    def get_diagnosis(trace_id: str):
        row = conn.execute(
            "SELECT json FROM diagnoses WHERE trace_id=?", (trace_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "no diagnosis; flag the trace first")
        return json.loads(row["json"])

    @app.post("/api/evals")
    def create_eval(req: EvalCreateRequest):
        row = conn.execute(
            "SELECT json FROM diagnoses WHERE trace_id=?", (req.trace_id,)).fetchone()
        if row is None:
            raise HTTPException(409, "flag and diagnose the trace before creating an eval")
        diagnosis = Diagnosis.model_validate_json(row["json"])
        trace_doc = load_trace(req.trace_id)
        span = next(s for s in trace_doc["spans"]
                    if s["step"] == diagnosis.root_cause_step)
        case = EvalCase(
            case_id=f"case-{req.trace_id[:12]}",
            trace_id=req.trace_id,
            failing_step=diagnosis.root_cause_step,
            category=diagnosis.category,
            original_input=span["input"],
            bad_output=span["output"] or {},
            corrected_output=req.corrected_output,
        )
        create_case(conn, evals_dir, case, created_at=_now())
        return case.model_dump()

    @app.get("/api/evals")
    def list_evals(trace_id: str | None = None):
        sql = ("SELECT case_id, trace_id, failing_step, category, created_at "
               "FROM eval_cases")
        params: tuple = ()
        if trace_id:
            sql += " WHERE trace_id=?"
            params = (trace_id,)
        return [dict(r) for r in conn.execute(sql + " ORDER BY created_at", params)]

    @app.post("/api/evals/run")
    def run_eval_dataset():
        return run_evals(conn, evals_dir, llm, run_at=_now())

    @app.get("/api/stats")
    def stats():
        failure_types = [
            {"category": r["category"], "count": r["c"]}
            for r in conn.execute(
                "SELECT category, COUNT(*) c FROM diagnoses GROUP BY category "
                "ORDER BY c DESC")]
        failures_per_step = [
            {"step": r["root_cause_step"], "count": r["c"]}
            for r in conn.execute(
                "SELECT root_cause_step, COUNT(*) c FROM diagnoses "
                "GROUP BY root_cause_step ORDER BY c DESC")]
        rate_over_time = [
            {"day": r["day"], "total": r["total"], "flagged": r["flagged"]}
            for r in conn.execute(
                "SELECT substr(created_at, 1, 10) day, COUNT(*) total, "
                "SUM(flagged) flagged FROM traces GROUP BY day ORDER BY day")]
        eval_trend = [
            {"run_at": r["run_at"], "total": r["total"], "passed": r["passed"]}
            for r in conn.execute(
                "SELECT run_at, COUNT(*) total, SUM(passed) passed "
                "FROM eval_results GROUP BY run_at ORDER BY run_at")]
        return {"failure_types": failure_types,
                "failures_per_step": failures_per_step,
                "rate_over_time": rate_over_time,
                "eval_trend": eval_trend}

    return app


def create_default_app() -> FastAPI:
    """uvicorn api.app:create_default_app --factory"""
    return create_app(Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parents[2] / "data"))))
