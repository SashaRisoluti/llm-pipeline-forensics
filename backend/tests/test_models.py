import pytest
from pydantic import ValidationError

from pipeline.models import (
    Classification,
    Diagnosis,
    DocumentType,
    ExtractedEntities,
    FailureCategory,
    RawDocument,
    StepJudgement,
    Summary,
)


def test_raw_document_defaults() -> None:
    doc = RawDocument(doc_id="d1", text="hello")
    assert doc.metadata == {}


def test_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        ExtractedEntities(confidence=6)
    with pytest.raises(ValidationError):
        Summary(summary="s", confidence=0)


def test_document_type_values() -> None:
    assert set(DocumentType) == {
        DocumentType.invoice, DocumentType.contract, DocumentType.meeting_notes,
        DocumentType.report, DocumentType.receipt,
    }


def test_failure_categories() -> None:
    assert len(FailureCategory) == 5


def test_diagnosis_roundtrip() -> None:
    d = Diagnosis(
        trace_id="t1", root_cause_step="extract",
        category=FailureCategory.extraction_hallucination, confident=True,
        judgements=[StepJudgement(step="extract", score=1, reasoning="made up a date")],
        evidence_chain=["extract: score 1/5 — made up a date"],
    )
    assert Diagnosis.model_validate_json(d.model_dump_json()) == d


def test_classification_requires_valid_type() -> None:
    with pytest.raises(ValidationError):
        Classification(doc_type="memo", confidence=3)
