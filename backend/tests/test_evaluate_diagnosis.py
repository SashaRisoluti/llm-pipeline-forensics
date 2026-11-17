from pathlib import Path

from forensics.engine import CategoryVerdict, JudgeVerdict
from pipeline.docgen import CORRUPTORS, BatchDoc
from pipeline.llm import RateLimitError
from pipeline.models import (
    Classification,
    DocumentType,
    ExtractedEntities,
    FailureCategory,
    Summary,
)
from scripts.evaluate_diagnosis import EXPECTED, Outcome, evaluate, render_table
from tests.conftest import MockLLM
from tracing.exporter import ForensicsExporter
from tracing.recorder import PayloadRecorder
from tracing.setup import build_tracer
from tracing.store import connect

PIPELINE_OK = [
    ExtractedEntities(dates=["2026-01-01"], confidence=5),
    Classification(doc_type=DocumentType.invoice, confidence=4),
    Summary(summary="ok", confidence=5),
]


def doc(doc_id: str, corruption: str | None) -> BatchDoc:
    return {"doc_id": doc_id, "doc_type": "invoice", "corruption": corruption,
            "text": "INVOICE #1 Total: € 10.00 EUR"}


def test_mapping_covers_every_corruptor() -> None:
    assert set(EXPECTED) == set(CORRUPTORS)


def test_render_table_scores_and_median() -> None:
    outs = [
        Outcome("d0", "strip_dates", "extract", FailureCategory.extraction_hallucination, 1.0),
        Outcome("d1", "strip_dates", "summarize", FailureCategory.context_loss, 3.0),
        Outcome("d2", "ambiguous_category", "classify", FailureCategory.propagation_error, 2.0),
    ]
    table = render_table(outs)
    assert "| strip_dates | 2 | 1/2 (50%) | 1/2 (50%) | 2.0 |" in table
    assert "| ambiguous_category | 1 | 1/1 (100%) | 0/1 (0%) | 2.0 |" in table
    assert "| currency_mismatch | 0 | – | – | – |" in table
    assert "| **all** | 3 | 2/3 (67%) | 1/3 (33%) | 2.0 |" in table


def test_render_table_empty_batch() -> None:
    assert "| **all** | 0 | – | – | – |" in render_table([])


def test_evaluate_diagnoses_only_corrupted_docs_and_times_them(
    tmp_env: dict[str, Path],
) -> None:
    conn = connect(tmp_env["db"])
    recorder = PayloadRecorder()
    tracer = build_tracer(ForensicsExporter(conn, tmp_env["traces"], recorder))
    llm = MockLLM([
        *PIPELINE_OK,  # clean doc
        *PIPELINE_OK,  # corrupted doc
        JudgeVerdict(score=5, reasoning="ok"),
        JudgeVerdict(score=2, reasoning="invented a date"),
        JudgeVerdict(score=2, reasoning="inherited"),
        JudgeVerdict(score=2, reasoning="inherited"),
        CategoryVerdict(category=FailureCategory.extraction_hallucination, explanation="x"),
    ])
    clock = iter([10.0, 12.5]).__next__

    outcomes = evaluate([doc("d0", None), doc("d1", "strip_dates")],
                        llm, conn, tracer, recorder, clock=clock)

    assert outcomes == [Outcome("d1", "strip_dates", "extract",
                                FailureCategory.extraction_hallucination, 2.5)]
    assert llm.responses == []


def test_evaluate_still_diagnoses_when_a_step_errors(tmp_env: dict[str, Path]) -> None:
    conn = connect(tmp_env["db"])
    recorder = PayloadRecorder()
    tracer = build_tracer(ForensicsExporter(conn, tmp_env["traces"], recorder))
    llm = MockLLM([
        RateLimitError("429"),  # extract call fails, pipeline halts
        JudgeVerdict(score=5, reasoning="ok"),  # intake
        CategoryVerdict(category=FailureCategory.prompt_failure, explanation="call died"),
    ])

    [outcome] = evaluate([doc("d0", "currency_mismatch")], llm, conn, tracer, recorder)

    assert outcome.root_cause_step == "extract"
    assert outcome.category == FailureCategory.prompt_failure
