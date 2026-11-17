from pipeline.llm import LLMCall, LLMClient
from pipeline.models import (
    Classification,
    DocumentType,
    ExtractedEntities,
    RawDocument,
    Summary,
)

EXTRACT_PROMPT = """You are an entity extraction engine for business documents.
Extract from the document below:
- dates (ISO format when possible),
- amounts (numbers only),
- currencies (ISO codes like EUR, USD),
- parties (people or companies),
- categories (topical labels such as billing, legal, staffing).
Also rate your confidence in this extraction from 1 (guessing) to 5 (certain).

DOCUMENT:
{text}
"""

CLASSIFY_PROMPT = """You are a document classifier. Classify the document as one of:
invoice, contract, meeting_notes, report, receipt.
Use both the raw text and the extracted entities.
Rate your confidence from 1 (guessing) to 5 (certain).

DOCUMENT:
{text}

EXTRACTED ENTITIES:
{entities}
"""

SUMMARIZE_INSTRUCTIONS = {
    DocumentType.invoice: "State who owes whom, the total amount with currency, and the due date.",
    DocumentType.contract: "State the parties, key obligations, and important deadlines.",
    DocumentType.meeting_notes: "State attendees, decisions made, and action items.",
    DocumentType.report: "State the main findings and any figures that support them.",
    DocumentType.receipt: "State the vendor, what was purchased, the total paid, and the date.",
}

SUMMARIZE_PROMPT = """You are a summarizer for {doc_type} documents.
{instructions}
Keep it under 80 words. Rate your confidence from 1 (guessing) to 5 (certain).

DOCUMENT:
{text}

EXTRACTED ENTITIES:
{entities}
"""


def intake(
    text: str, doc_id: str, metadata: dict[str, str] | None = None
) -> tuple[RawDocument, None]:
    return RawDocument(doc_id=doc_id, text=text, metadata=metadata or {}), None


def extract(llm: LLMClient, doc: RawDocument) -> tuple[ExtractedEntities, LLMCall]:
    prompt = EXTRACT_PROMPT.format(text=doc.text)
    return llm.generate_structured(prompt, ExtractedEntities)


def classify(
    llm: LLMClient, doc: RawDocument, entities: ExtractedEntities
) -> tuple[Classification, LLMCall]:
    prompt = CLASSIFY_PROMPT.format(text=doc.text, entities=entities.model_dump_json())
    return llm.generate_structured(prompt, Classification)


def summarize(
    llm: LLMClient, doc: RawDocument, entities: ExtractedEntities, doc_type: DocumentType
) -> tuple[Summary, LLMCall]:
    prompt = SUMMARIZE_PROMPT.format(
        doc_type=doc_type.value,
        instructions=SUMMARIZE_INSTRUCTIONS[doc_type],
        text=doc.text,
        entities=entities.model_dump_json(),
    )
    return llm.generate_structured(prompt, Summary)
