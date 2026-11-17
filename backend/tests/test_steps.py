from pipeline.models import (
    Classification,
    DocumentType,
    ExtractedEntities,
    RawDocument,
    Summary,
)
from pipeline.steps import classify, extract, intake, summarize
from tests.conftest import MockLLM


def test_intake_wraps_text() -> None:
    doc, call = intake("some text", "d1")
    assert doc == RawDocument(doc_id="d1", text="some text")
    assert call is None


def test_extract_sends_doc_text_and_returns_entities() -> None:
    entities = ExtractedEntities(dates=["2026-01-01"], confidence=5)
    llm = MockLLM([entities])
    out, call = extract(llm, RawDocument(doc_id="d1", text="Invoice dated 2026-01-01"))
    assert out == entities
    assert "Invoice dated 2026-01-01" in llm.prompts[0]
    assert call.prompt == llm.prompts[0]


def test_classify_gets_text_and_entities() -> None:
    llm = MockLLM([Classification(doc_type=DocumentType.invoice, confidence=4)])
    doc = RawDocument(doc_id="d1", text="Total due: 100 EUR")
    entities = ExtractedEntities(currencies=["EUR"], confidence=5)
    out, _ = classify(llm, doc, entities)
    assert out.doc_type == DocumentType.invoice
    assert "Total due: 100 EUR" in llm.prompts[0]
    assert "EUR" in llm.prompts[0]


def test_summarize_prompt_is_type_tailored() -> None:
    llm = MockLLM([Summary(summary="s", confidence=3), Summary(summary="s", confidence=3)])
    doc = RawDocument(doc_id="d1", text="t")
    entities = ExtractedEntities(confidence=5)
    summarize(llm, doc, entities, DocumentType.invoice)
    summarize(llm, doc, entities, DocumentType.contract)
    assert llm.prompts[0] != llm.prompts[1]  # different type = different instructions
