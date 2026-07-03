from enum import Enum

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    invoice = "invoice"
    contract = "contract"
    meeting_notes = "meeting_notes"
    report = "report"
    receipt = "receipt"


class FailureCategory(str, Enum):
    extraction_hallucination = "extraction_hallucination"
    misclassification = "misclassification"
    propagation_error = "propagation_error"
    context_loss = "context_loss"
    prompt_failure = "prompt_failure"


class RawDocument(BaseModel):
    doc_id: str
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class ExtractedEntities(BaseModel):
    dates: list[str] = Field(default_factory=list)
    amounts: list[float] = Field(default_factory=list)
    currencies: list[str] = Field(default_factory=list)
    parties: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=1, le=5)


class Classification(BaseModel):
    doc_type: DocumentType
    confidence: int = Field(ge=1, le=5)


class Summary(BaseModel):
    summary: str
    confidence: int = Field(ge=1, le=5)


class StepJudgement(BaseModel):
    step: str
    score: int = Field(ge=1, le=5)
    reasoning: str


class Diagnosis(BaseModel):
    trace_id: str
    root_cause_step: str
    category: FailureCategory
    confident: bool
    judgements: list[StepJudgement]
    evidence_chain: list[str]
