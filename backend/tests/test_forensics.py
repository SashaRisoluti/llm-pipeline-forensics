from typing import Any

from forensics.engine import CategoryVerdict, JudgeVerdict, diagnose
from pipeline.models import FailureCategory
from tests.conftest import MockLLM


def make_trace(spans: list[dict[str, Any]]) -> dict[str, Any]:
    return {"trace_id": "t1", "doc_id": "d1", "status": "ok", "spans": spans}


def span(step: str, status: str = "ok", error: str | None = None) -> dict[str, Any]:
    return {"step": step, "status": status, "error": error,
            "input": {"x": 1}, "output": {"y": 2}, "confidence": 4}


def test_root_cause_is_first_big_drop() -> None:
    trace = make_trace([span("pipeline"), span("intake"), span("extract"),
                        span("classify"), span("summarize")])
    llm = MockLLM([
        JudgeVerdict(score=5, reasoning="clean intake"),
        JudgeVerdict(score=2, reasoning="hallucinated a date"),   # drop 5 -> 2
        JudgeVerdict(score=2, reasoning="inherited bad date"),
        JudgeVerdict(score=1, reasoning="summary asserts fake deadline"),
        CategoryVerdict(category=FailureCategory.extraction_hallucination,
                        explanation="dates invented"),
    ])
    d = diagnose(trace, llm)
    assert d.root_cause_step == "extract"
    assert d.confident is True
    assert d.category == FailureCategory.extraction_hallucination
    assert len(d.judgements) == 4  # pipeline root span not judged
    assert any("hallucinated" in e for e in d.evidence_chain)


def test_no_big_drop_reports_worst_step_unconfident() -> None:
    trace = make_trace([span("pipeline"), span("intake"), span("extract"),
                        span("classify"), span("summarize")])
    llm = MockLLM([
        JudgeVerdict(score=5, reasoning="ok"),
        JudgeVerdict(score=4, reasoning="minor"),
        JudgeVerdict(score=3, reasoning="meh"),
        JudgeVerdict(score=4, reasoning="fine"),
        CategoryVerdict(category=FailureCategory.context_loss, explanation="drift"),
    ])
    d = diagnose(trace, llm)
    assert d.root_cause_step == "classify"
    assert d.confident is False


def test_errored_span_scores_one_without_judge_call() -> None:
    trace = make_trace([span("pipeline"), span("intake"),
                        span("extract", status="error", error="LLM exploded")])
    llm = MockLLM([
        JudgeVerdict(score=5, reasoning="ok"),  # intake only
        CategoryVerdict(category=FailureCategory.prompt_failure, explanation="call died"),
    ])
    d = diagnose(trace, llm)
    assert d.root_cause_step == "extract"
    assert d.confident is True
    extract_j = [j for j in d.judgements if j.step == "extract"][0]
    assert extract_j.score == 1
    assert "LLM exploded" in extract_j.reasoning


def test_judge_failure_marks_step_unjudgeable() -> None:
    trace = make_trace([span("pipeline"), span("intake"), span("extract")])
    llm = MockLLM([
        JudgeVerdict(score=5, reasoning="ok"),
        RuntimeError("judge down"),
        CategoryVerdict(category=FailureCategory.prompt_failure, explanation="?"),
    ])
    d = diagnose(trace, llm)
    extract_j = [j for j in d.judgements if j.step == "extract"][0]
    assert "unjudgeable" in extract_j.reasoning
    assert extract_j.score == 3  # neutral placeholder


def test_unjudgeable_step_is_skipped_by_root_cause_scan() -> None:
    trace = make_trace([span("pipeline"), span("intake"), span("extract"),
                        span("classify"), span("summarize")])
    llm = MockLLM([
        RuntimeError("judge down"),               # intake unjudgeable -> neutral 3
        JudgeVerdict(score=2, reasoning="invented a date"),
        JudgeVerdict(score=2, reasoning="inherited"),
        JudgeVerdict(score=2, reasoning="inherited"),
        CategoryVerdict(category=FailureCategory.extraction_hallucination, explanation="x"),
    ])
    d = diagnose(trace, llm)
    assert d.root_cause_step == "extract"
    assert d.confident is True


def test_all_steps_unjudgeable_is_unconfident() -> None:
    trace = make_trace([span("pipeline"), span("intake"), span("extract")])
    llm = MockLLM([RuntimeError("down"), RuntimeError("down"), RuntimeError("down")])
    d = diagnose(trace, llm)
    assert d.confident is False
