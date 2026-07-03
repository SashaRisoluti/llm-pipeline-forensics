import json

from evals.runner import EvalJudgeVerdict, run_evals
from evals.store import EvalCase, create_case, list_cases
from pipeline.models import ExtractedEntities, FailureCategory
from tests.conftest import MockLLM
from tracing.store import connect


CASE = EvalCase(
    case_id="c1", trace_id="t1", failing_step="extract",
    category=FailureCategory.extraction_hallucination,
    original_input={"doc_id": "d1", "text": "Invoice dated 2026-01-01", "metadata": {}},
    bad_output={"dates": ["2024-13-45"], "confidence": 5},
    corrected_output={"dates": ["2026-01-01"], "confidence": 5},
)


def test_create_and_list_case(tmp_env):
    conn = connect(tmp_env["db"])
    create_case(conn, tmp_env["evals"], CASE, created_at="2026-07-02T00:00:00Z")
    cases = list_cases(conn, tmp_env["evals"])
    assert len(cases) == 1
    assert cases[0].failing_step == "extract"
    on_disk = json.loads((tmp_env["evals"] / "c1.json").read_text())
    assert on_disk["corrected_output"]["dates"] == ["2026-01-01"]


def test_run_evals_records_pass_and_fail(tmp_env):
    conn = connect(tmp_env["db"])
    create_case(conn, tmp_env["evals"], CASE, created_at="2026-07-02T00:00:00Z")
    llm = MockLLM([
        ExtractedEntities(dates=["2026-01-01"], confidence=5),  # re-run of extract
        EvalJudgeVerdict(score=5, reasoning="matches correction"),
    ])
    results = run_evals(conn, tmp_env["evals"], llm, run_at="2026-07-02T01:00:00Z")
    assert results == [{"case_id": "c1", "passed": True, "score": 5}]
    row = conn.execute("SELECT * FROM eval_results").fetchone()
    assert row["passed"] == 1 and row["score"] == 5


def test_run_evals_failure_path(tmp_env):
    conn = connect(tmp_env["db"])
    create_case(conn, tmp_env["evals"], CASE, created_at="2026-07-02T00:00:00Z")
    llm = MockLLM([
        ExtractedEntities(dates=["2024-13-45"], confidence=5),  # still bad
        EvalJudgeVerdict(score=1, reasoning="same hallucination"),
    ])
    results = run_evals(conn, tmp_env["evals"], llm, run_at="2026-07-02T01:00:00Z")
    assert results[0]["passed"] is False


def test_run_evals_skips_non_rerunnable_step(tmp_env):
    conn = connect(tmp_env["db"])
    intake_case = CASE.model_copy(update={"case_id": "c2", "failing_step": "intake"})
    create_case(conn, tmp_env["evals"], intake_case, created_at="2026-07-02T00:00:00Z")
    results = run_evals(conn, tmp_env["evals"], MockLLM([]), run_at="2026-07-02T01:00:00Z")
    assert results == []
    assert conn.execute("SELECT COUNT(*) c FROM eval_results").fetchone()["c"] == 0
