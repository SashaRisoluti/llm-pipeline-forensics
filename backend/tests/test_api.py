from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from evals.runner import EvalJudgeVerdict
from forensics.engine import CategoryVerdict, JudgeVerdict
from pipeline.models import (
    Classification,
    DocumentType,
    ExtractedEntities,
    FailureCategory,
    Summary,
)
from tests.conftest import MockLLM

Client = tuple[TestClient, MockLLM]

HAPPY = [
    ExtractedEntities(dates=["2026-01-01"], confidence=5),
    Classification(doc_type=DocumentType.invoice, confidence=4),
    Summary(summary="ok", confidence=5),
]

FORENSICS = [
    JudgeVerdict(score=5, reasoning="ok"),                       # intake
    JudgeVerdict(score=2, reasoning="hallucinated date"),        # extract
    JudgeVerdict(score=2, reasoning="inherited"),                # classify
    JudgeVerdict(score=2, reasoning="propagated"),               # summarize
    CategoryVerdict(category=FailureCategory.extraction_hallucination,
                    explanation="invented dates"),
]


@pytest.fixture
def app_client(tmp_path: Path) -> Client:
    llm = MockLLM()
    app = create_app(tmp_path / "data", llm=llm)
    return TestClient(app), llm


def run_one(client: TestClient, llm: MockLLM) -> str:
    llm.responses.extend(HAPPY)
    resp = client.post("/api/runs", json={"text": "Invoice ...", "doc_id": "d1"})
    assert resp.status_code == 200
    trace_id: str = resp.json()["trace_id"]
    return trace_id


def test_run_and_get_trace(app_client: Client) -> None:
    client, llm = app_client
    trace_id = run_one(client, llm)
    listing = client.get("/api/traces").json()
    assert listing[0]["trace_id"] == trace_id
    trace = client.get(f"/api/traces/{trace_id}").json()
    assert [s["step"] for s in trace["spans"]] == [
        "pipeline", "intake", "extract", "classify", "summarize"]


def test_get_missing_trace_404(app_client: Client) -> None:
    client, _ = app_client
    assert client.get("/api/traces/deadbeef").status_code == 404


def test_flag_runs_forensics_and_stores_diagnosis(app_client: Client) -> None:
    client, llm = app_client
    trace_id = run_one(client, llm)
    llm.responses.extend(FORENSICS)
    diagnosis = client.post(f"/api/traces/{trace_id}/flag").json()
    assert diagnosis["root_cause_step"] == "extract"
    assert diagnosis["category"] == "extraction_hallucination"
    again = client.get(f"/api/traces/{trace_id}/diagnosis").json()
    assert again == diagnosis
    assert client.get("/api/traces").json()[0]["flagged"] == 1


def test_eval_lifecycle_and_stats(app_client: Client) -> None:
    client, llm = app_client
    trace_id = run_one(client, llm)
    llm.responses.extend(FORENSICS)
    client.post(f"/api/traces/{trace_id}/flag")

    created = client.post("/api/evals", json={
        "trace_id": trace_id,
        "corrected_output": {"dates": ["2026-01-01"], "confidence": 5},
    }).json()
    assert created["failing_step"] == "extract"
    assert client.get(f"/api/evals?trace_id={trace_id}").json()[0]["case_id"] == created["case_id"]

    llm.responses.extend([
        ExtractedEntities(dates=["2026-01-01"], confidence=5),
        EvalJudgeVerdict(score=5, reasoning="fixed"),
    ])
    results = client.post("/api/evals/run").json()
    assert results[0]["passed"] is True

    stats = client.get("/api/stats").json()
    assert stats["failure_types"] == [{"category": "extraction_hallucination", "count": 1}]
    assert stats["failures_per_step"] == [{"step": "extract", "count": 1}]
    assert stats["eval_trend"][0]["passed"] == 1
    assert stats["rate_over_time"][0]["total"] == 1


def test_eval_without_diagnosis_409(app_client: Client) -> None:
    client, llm = app_client
    trace_id = run_one(client, llm)
    resp = client.post("/api/evals", json={"trace_id": trace_id, "corrected_output": {}})
    assert resp.status_code == 409


def test_trace_list_filters(app_client: Client) -> None:
    client, llm = app_client
    trace_id = run_one(client, llm)
    llm.responses.extend(FORENSICS)
    client.post(f"/api/traces/{trace_id}/flag")
    assert len(client.get("/api/traces?flagged=true").json()) == 1
    assert client.get("/api/traces?flagged=false").json() == []
    assert len(client.get("/api/traces?status=ok").json()) == 1
    assert len(client.get("/api/traces?root_cause_step=extract").json()) == 1
    assert client.get("/api/traces?root_cause_step=classify").json() == []
