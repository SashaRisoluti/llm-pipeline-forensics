# Failure Forensics Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Observability layer for a 4-step AI document pipeline that traces every step, diagnoses root-cause failures via LLM-as-judge, and feeds confirmed failures into an eval dataset.

**Architecture:** Custom Python chain (Pydantic I/O per step) instrumented with real OpenTelemetry spans exported by a custom exporter to JSON trace files + SQLite index. FastAPI serves traces/forensics/evals to a React (Vite + react-flow + recharts) explorer. Docker Compose wraps both.

**Tech Stack:** Python 3.12, pydantic v2, google-genai (Gemini Flash-Lite), opentelemetry-sdk, FastAPI, uvicorn, pytest, React 18 + TypeScript + Vite, @xyflow/react, recharts, nginx, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-07-02-failure-forensics-design.md`

**Conventions used throughout:**
- All backend commands run from `backend/` unless stated otherwise.
- Python env: `python -m venv .venv` once (Task 1), then `.venv\Scripts\activate` (Windows) / `source .venv/bin/activate`.
- `GEMINI_API_KEY` env var required only for live runs (Tasks 11+ demo steps); all tests use a mock LLM and run offline.
- SQLite database lives at `data/forensics.db`; trace JSON files at `data/traces/`; eval cases at `data/evals/`. All created at runtime, git-ignored.

## File Structure

```
backend/
  pyproject.toml
  pipeline/__init__.py
  pipeline/models.py        # all Pydantic domain models
  pipeline/llm.py           # LLMClient protocol + GeminiClient + LLMCall record
  pipeline/steps.py         # intake / extract / classify / summarize + prompts
  pipeline/orchestrator.py  # run_pipeline + _step wrapper (span instrumentation)
  pipeline/docgen.py        # synthetic doc generator + seeded failure injector
  tracing/__init__.py
  tracing/store.py          # SQLite schema + connect()
  tracing/recorder.py       # PayloadRecorder (span_id -> payload dict)
  tracing/exporter.py       # ForensicsExporter (JSON files + SQLite rows)
  tracing/setup.py          # build_tracer()
  forensics/__init__.py
  forensics/engine.py       # judge prompts, backward walk, category classifier
  evals/__init__.py
  evals/store.py            # eval case create/list (JSON files + SQLite)
  evals/runner.py           # re-run failing steps, judge pass/fail
  api/__init__.py
  api/app.py                # FastAPI app + all endpoints
  scripts/run_batch.py      # CLI: generate 50 docs, run pipeline on each
  tests/                    # pytest suites, one file per module
frontend/
  (Vite scaffold) src/api.ts, src/traceFlow.ts, src/App.tsx,
  src/pages/TraceList.tsx, src/pages/TraceView.tsx, src/pages/Dashboard.tsx,
  src/components/SpanDrawer.tsx, src/components/DiffView.tsx,
  src/components/DiagnosisPanel.tsx
docker/nginx.conf
backend/Dockerfile  frontend/Dockerfile  docker-compose.yml
```

---

### Task 1: Backend scaffold

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/pipeline/__init__.py`, `backend/tracing/__init__.py`, `backend/forensics/__init__.py`, `backend/evals/__init__.py`, `backend/api/__init__.py`, `backend/tests/__init__.py` (all empty)
- Create: `backend/tests/test_scaffold.py`
- Create: `.gitignore`

- [ ] **Step 1: Write `backend/pyproject.toml`**

```toml
[project]
name = "forensics-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7",
    "google-genai>=1.0",
    "opentelemetry-sdk>=1.25",
    "fastapi>=0.111",
    "uvicorn>=0.30",
]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["pipeline", "tracing", "forensics", "evals", "api"]
```

- [ ] **Step 2: Write `.gitignore` at repo root**

```gitignore
.venv/
__pycache__/
*.pyc
data/
node_modules/
frontend/dist/
.env
```

- [ ] **Step 3: Create empty `__init__.py` files**

Create empty files: `backend/pipeline/__init__.py`, `backend/tracing/__init__.py`, `backend/forensics/__init__.py`, `backend/evals/__init__.py`, `backend/api/__init__.py`, `backend/tests/__init__.py`.

- [ ] **Step 4: Write failing sanity test `backend/tests/test_scaffold.py`**

```python
def test_packages_import():
    import pipeline
    import tracing
    import forensics
    import evals
    import api
```

- [ ] **Step 5: Create venv, install, run test**

Run (from `backend/`):
```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/python -m pytest tests/test_scaffold.py -v
```
Expected: PASS (packages exist and import).

- [ ] **Step 6: Commit**

```bash
git add backend .gitignore
git commit -m "chore: backend scaffold with package layout and pytest"
```

---

### Task 2: Domain models

**Files:**
- Create: `backend/pipeline/models.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Write failing tests `backend/tests/test_models.py`**

```python
import pytest
from pydantic import ValidationError

from pipeline.models import (
    Classification, Diagnosis, DocumentType, ExtractedEntities,
    FailureCategory, RawDocument, StepJudgement, Summary,
)


def test_raw_document_defaults():
    doc = RawDocument(doc_id="d1", text="hello")
    assert doc.metadata == {}


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        ExtractedEntities(confidence=6)
    with pytest.raises(ValidationError):
        Summary(summary="s", confidence=0)


def test_document_type_values():
    assert set(DocumentType) == {
        DocumentType.invoice, DocumentType.contract, DocumentType.meeting_notes,
        DocumentType.report, DocumentType.receipt,
    }


def test_failure_categories():
    assert len(FailureCategory) == 5


def test_diagnosis_roundtrip():
    d = Diagnosis(
        trace_id="t1", root_cause_step="extract",
        category=FailureCategory.extraction_hallucination, confident=True,
        judgements=[StepJudgement(step="extract", score=1, reasoning="made up a date")],
        evidence_chain=["extract: score 1/5 — made up a date"],
    )
    assert Diagnosis.model_validate_json(d.model_dump_json()) == d


def test_classification_requires_valid_type():
    with pytest.raises(ValidationError):
        Classification(doc_type="memo", confidence=3)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError` (models.py missing).

- [ ] **Step 3: Write `backend/pipeline/models.py`**

```python
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
    prompt_failure = "prompt_failure"
    context_loss = "context_loss"


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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/models.py backend/tests/test_models.py
git commit -m "feat: Pydantic domain models for pipeline and forensics"
```

---

### Task 3: LLM client (protocol, Gemini impl, mock)

**Files:**
- Create: `backend/pipeline/llm.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_llm.py`

The `LLMClient` protocol is the seam every LLM-touching module depends on. Tests never hit Gemini; they use `MockLLM` from conftest. `GeminiClient` retry logic IS tested, with a stubbed transport.

- [ ] **Step 1: Write `backend/tests/conftest.py` (shared mock)**

```python
import pytest

from pipeline.llm import LLMCall


class MockLLM:
    """Returns queued Pydantic objects in order; records prompts."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.prompts: list[str] = []

    def generate_structured(self, prompt, schema):
        self.prompts.append(prompt)
        obj = self.responses.pop(0)
        if isinstance(obj, Exception):
            raise obj
        return obj, LLMCall(
            prompt=prompt, raw_response=obj.model_dump_json(),
            tokens_in=10, tokens_out=5,
        )


@pytest.fixture
def mock_llm():
    return MockLLM


@pytest.fixture
def tmp_env(tmp_path):
    """data dirs for tracing tests"""
    traces = tmp_path / "traces"
    traces.mkdir()
    return {"db": tmp_path / "forensics.db", "traces": traces, "evals": tmp_path / "evals"}
```

- [ ] **Step 2: Write failing tests `backend/tests/test_llm.py`**

```python
import pytest
from pydantic import BaseModel

from pipeline.llm import GeminiClient, LLMCall, RateLimitError


class Out(BaseModel):
    answer: str


class FakeResponse:
    def __init__(self, text):
        self.text = text

        class Usage:
            prompt_token_count = 7
            candidates_token_count = 3

        self.usage_metadata = Usage()


def make_client(side_effects):
    """GeminiClient with generate_content stubbed; no real API."""
    client = GeminiClient.__new__(GeminiClient)
    client._model = "test-model"
    client._max_retries = 3
    client._base_delay = 0.0  # no sleep in tests
    calls = {"n": 0}

    def fake_generate(**kwargs):
        effect = side_effects[calls["n"]]
        calls["n"] += 1
        if isinstance(effect, Exception):
            raise effect
        return effect

    client._generate = fake_generate
    return client, calls


def test_success_returns_parsed_and_call():
    client, _ = make_client([FakeResponse('{"answer": "42"}')])
    out, call = client.generate_structured("q?", Out)
    assert out == Out(answer="42")
    assert call == LLMCall(prompt="q?", raw_response='{"answer": "42"}', tokens_in=7, tokens_out=3)


def test_retries_on_429_then_succeeds():
    client, calls = make_client([
        RateLimitError("429 RESOURCE_EXHAUSTED"),
        FakeResponse('{"answer": "ok"}'),
    ])
    out, _ = client.generate_structured("q?", Out)
    assert out.answer == "ok"
    assert calls["n"] == 2


def test_gives_up_after_max_retries():
    client, _ = make_client([RateLimitError("429")] * 3)
    with pytest.raises(RateLimitError):
        client.generate_structured("q?", Out)


def test_non_rate_limit_error_not_retried():
    client, calls = make_client([ValueError("boom")])
    with pytest.raises(ValueError):
        client.generate_structured("q?", Out)
    assert calls["n"] == 1
```

- [ ] **Step 3: Run tests, verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_llm.py -v`
Expected: FAIL with `ImportError` (llm.py missing).

- [ ] **Step 4: Write `backend/pipeline/llm.py`**

```python
import os
import time
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass
class LLMCall:
    prompt: str
    raw_response: str
    tokens_in: int
    tokens_out: int


class RateLimitError(Exception):
    pass


class LLMClient(Protocol):
    def generate_structured(
        self, prompt: str, schema: type[BaseModel]
    ) -> tuple[BaseModel, LLMCall]: ...


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc)
    return isinstance(exc, RateLimitError) or "429" in text or "RESOURCE_EXHAUSTED" in text


class GeminiClient:
    def __init__(self, model: str | None = None, max_retries: int = 5, base_delay: float = 2.0):
        from google import genai

        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self._model = model or os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
        self._max_retries = max_retries
        self._base_delay = base_delay

    def _generate(self, *, prompt: str, schema: type[BaseModel]):
        return self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )

    def generate_structured(self, prompt: str, schema: type[BaseModel]):
        delay = self._base_delay
        for attempt in range(self._max_retries):
            try:
                resp = self._generate(prompt=prompt, schema=schema)
            except Exception as exc:
                if not _is_rate_limit(exc) or attempt == self._max_retries - 1:
                    raise
                time.sleep(delay)
                delay *= 2
                continue
            usage = resp.usage_metadata
            call = LLMCall(
                prompt=prompt,
                raw_response=resp.text,
                tokens_in=usage.prompt_token_count or 0,
                tokens_out=usage.candidates_token_count or 0,
            )
            return schema.model_validate_json(resp.text), call
```

- [ ] **Step 5: Run tests, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_llm.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/pipeline/llm.py backend/tests/conftest.py backend/tests/test_llm.py
git commit -m "feat: LLM client protocol, Gemini impl with 429 backoff, test mock"
```

---

### Task 4: SQLite store + payload recorder

**Files:**
- Create: `backend/tracing/store.py`
- Create: `backend/tracing/recorder.py`
- Test: `backend/tests/test_store.py`

- [ ] **Step 1: Write failing tests `backend/tests/test_store.py`**

```python
from tracing.recorder import PayloadRecorder
from tracing.store import connect


def test_connect_creates_schema(tmp_env):
    conn = connect(tmp_env["db"])
    tables = {
        r["name"] for r in
        conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"traces", "spans", "diagnoses", "eval_cases", "eval_results"} <= tables


def test_connect_is_idempotent(tmp_env):
    connect(tmp_env["db"]).close()
    conn = connect(tmp_env["db"])  # must not raise on existing schema
    conn.execute("INSERT INTO traces (trace_id) VALUES ('t1')")
    assert conn.execute("SELECT flagged FROM traces").fetchone()["flagged"] == 0


def test_recorder_accumulates_and_pops():
    rec = PayloadRecorder()
    rec.record(123, input={"a": 1})
    rec.record(123, output={"b": 2})
    assert rec.pop(123) == {"input": {"a": 1}, "output": {"b": 2}}
    assert rec.pop(123) == {}  # popped = gone
    assert rec.pop(999) == {}  # unknown span = empty
```

- [ ] **Step 2: Run tests, verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_store.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `backend/tracing/store.py`**

```python
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    doc_id TEXT,
    created_at TEXT,
    status TEXT,
    flagged INTEGER NOT NULL DEFAULT 0,
    json_path TEXT
);
CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT,
    step TEXT,
    status TEXT,
    latency_ms REAL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    confidence INTEGER,
    error TEXT,
    started_at TEXT
);
CREATE TABLE IF NOT EXISTS diagnoses (
    trace_id TEXT PRIMARY KEY,
    root_cause_step TEXT,
    category TEXT,
    created_at TEXT,
    json TEXT
);
CREATE TABLE IF NOT EXISTS eval_cases (
    case_id TEXT PRIMARY KEY,
    trace_id TEXT,
    failing_step TEXT,
    category TEXT,
    created_at TEXT,
    json_path TEXT
);
CREATE TABLE IF NOT EXISTS eval_results (
    run_at TEXT,
    case_id TEXT,
    passed INTEGER,
    score INTEGER
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
```

- [ ] **Step 4: Write `backend/tracing/recorder.py`**

```python
class PayloadRecorder:
    """Holds big span payloads (inputs, outputs, prompts) keyed by OTel span_id.

    OTel span attributes only take primitives, so the orchestrator records
    payloads here and the exporter merges them at export time.
    """

    def __init__(self):
        self._payloads: dict[int, dict] = {}

    def record(self, span_id: int, **payload):
        self._payloads.setdefault(span_id, {}).update(payload)

    def pop(self, span_id: int) -> dict:
        return self._payloads.pop(span_id, {})
```

- [ ] **Step 5: Run tests, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_store.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tracing backend/tests/test_store.py
git commit -m "feat: SQLite schema/connect and span payload recorder"
```

---

### Task 5: OTel exporter + tracer setup

**Files:**
- Create: `backend/tracing/exporter.py`
- Create: `backend/tracing/setup.py`
- Test: `backend/tests/test_exporter.py`

`ForensicsExporter` receives spans one-by-one (SimpleSpanProcessor exports on span end; children end before the root). It buffers span records per trace_id, writes a SQLite `spans` row immediately, and when the parentless root span arrives it flushes the whole trace to `data/traces/<trace_id>.json` plus a `traces` row.

- [ ] **Step 1: Write failing tests `backend/tests/test_exporter.py`**

```python
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_exporter.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `backend/tracing/exporter.py`**

```python
import json
from datetime import datetime, timezone
from pathlib import Path

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


class ForensicsExporter(SpanExporter):
    def __init__(self, db_conn, traces_dir: Path, recorder):
        self._db = db_conn
        self._dir = Path(traces_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._recorder = recorder
        self._buffers: dict[str, list[dict]] = {}

    def export(self, spans) -> SpanExportResult:
        for span in spans:
            ctx = span.get_span_context()
            trace_id = format(ctx.trace_id, "032x")
            payload = self._recorder.pop(ctx.span_id)
            record = {
                "span_id": format(ctx.span_id, "016x"),
                "trace_id": trace_id,
                "step": span.name,
                "status": "error" if span.status.status_code.name == "ERROR" else "ok",
                "latency_ms": (span.end_time - span.start_time) / 1e6,
                "started_at": datetime.fromtimestamp(
                    span.start_time / 1e9, tz=timezone.utc
                ).isoformat(),
                "error": payload.get("error"),
                "tokens_in": payload.get("tokens_in"),
                "tokens_out": payload.get("tokens_out"),
                "confidence": payload.get("confidence"),
                "input": payload.get("input"),
                "output": payload.get("output"),
                "prompt": payload.get("prompt"),
                "raw_response": payload.get("raw_response"),
            }
            self._buffers.setdefault(trace_id, []).append(record)
            self._db.execute(
                "INSERT OR REPLACE INTO spans "
                "(span_id, trace_id, step, status, latency_ms, tokens_in, tokens_out,"
                " confidence, error, started_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (record["span_id"], trace_id, record["step"], record["status"],
                 record["latency_ms"], record["tokens_in"], record["tokens_out"],
                 record["confidence"], record["error"], record["started_at"]),
            )
            if span.parent is None:
                self._flush_trace(trace_id, record)
        self._db.commit()
        return SpanExportResult.SUCCESS

    def _flush_trace(self, trace_id: str, root_record: dict):
        spans = self._buffers.pop(trace_id)
        spans.sort(key=lambda s: s["started_at"])
        root_input = root_record.get("input") or {}
        doc_id = root_input.get("doc_id") if isinstance(root_input, dict) else None
        status = "error" if any(s["status"] == "error" for s in spans) else "ok"
        path = self._dir / f"{trace_id}.json"
        path.write_text(json.dumps({
            "trace_id": trace_id,
            "doc_id": doc_id,
            "created_at": spans[0]["started_at"],
            "status": status,
            "spans": spans,
        }, indent=2, default=str), encoding="utf-8")
        self._db.execute(
            "INSERT OR REPLACE INTO traces "
            "(trace_id, doc_id, created_at, status, flagged, json_path) "
            "VALUES (?,?,?,?,0,?)",
            (trace_id, doc_id, spans[0]["started_at"], status, str(path)),
        )

    def shutdown(self):
        pass
```

- [ ] **Step 4: Write `backend/tracing/setup.py`**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


def build_tracer(exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return trace.get_tracer("forensics", tracer_provider=provider)
```

- [ ] **Step 5: Run tests, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_exporter.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tracing backend/tests/test_exporter.py
git commit -m "feat: OTel custom exporter writing JSON traces + SQLite index"
```

---

### Task 6: Pipeline steps (intake, extract, classify, summarize)

**Files:**
- Create: `backend/pipeline/steps.py`
- Test: `backend/tests/test_steps.py`

All LLM steps return `(output_model, LLMCall)`; `intake` returns `(RawDocument, None)` — uniform shape for the orchestrator. Prompts live here as module constants so forensics/UI can reference the exact text.

- [ ] **Step 1: Write failing tests `backend/tests/test_steps.py`**

```python
from pipeline.models import (
    Classification, DocumentType, ExtractedEntities, RawDocument, Summary,
)
from pipeline.steps import classify, extract, intake, summarize
from tests.conftest import MockLLM


def test_intake_wraps_text():
    doc, call = intake("some text", "d1")
    assert doc == RawDocument(doc_id="d1", text="some text")
    assert call is None


def test_extract_sends_doc_text_and_returns_entities():
    entities = ExtractedEntities(dates=["2026-01-01"], confidence=5)
    llm = MockLLM([entities])
    out, call = extract(llm, RawDocument(doc_id="d1", text="Invoice dated 2026-01-01"))
    assert out == entities
    assert "Invoice dated 2026-01-01" in llm.prompts[0]
    assert call.prompt == llm.prompts[0]


def test_classify_gets_text_and_entities():
    llm = MockLLM([Classification(doc_type=DocumentType.invoice, confidence=4)])
    doc = RawDocument(doc_id="d1", text="Total due: 100 EUR")
    entities = ExtractedEntities(currencies=["EUR"], confidence=5)
    out, _ = classify(llm, doc, entities)
    assert out.doc_type == DocumentType.invoice
    assert "Total due: 100 EUR" in llm.prompts[0]
    assert "EUR" in llm.prompts[0]


def test_summarize_prompt_is_type_tailored():
    llm = MockLLM([Summary(summary="s", confidence=3), Summary(summary="s", confidence=3)])
    doc = RawDocument(doc_id="d1", text="t")
    entities = ExtractedEntities(confidence=5)
    summarize(llm, doc, entities, DocumentType.invoice)
    summarize(llm, doc, entities, DocumentType.contract)
    assert llm.prompts[0] != llm.prompts[1]  # different type = different instructions
```

- [ ] **Step 2: Run tests, verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_steps.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `backend/pipeline/steps.py`**

```python
from pipeline.llm import LLMCall, LLMClient
from pipeline.models import (
    Classification, DocumentType, ExtractedEntities, RawDocument, Summary,
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


def intake(text: str, doc_id: str, metadata: dict | None = None):
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_steps.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/steps.py backend/tests/test_steps.py
git commit -m "feat: four pipeline steps with typed I/O and tailored prompts"
```

---

### Task 7: Orchestrator with span instrumentation

**Files:**
- Create: `backend/pipeline/orchestrator.py`
- Test: `backend/tests/test_orchestrator.py`

Each step runs inside its own OTel span; payloads go to the recorder. A step failure marks its span error, skips downstream steps, and still produces a complete flushed trace.

- [ ] **Step 1: Write failing tests `backend/tests/test_orchestrator.py`**

```python
import json

from pipeline.models import (
    Classification, DocumentType, ExtractedEntities, Summary,
)
from pipeline.orchestrator import run_pipeline
from tests.conftest import MockLLM
from tracing.exporter import ForensicsExporter
from tracing.recorder import PayloadRecorder
from tracing.setup import build_tracer
from tracing.store import connect


def build_env(tmp_env, llm):
    conn = connect(tmp_env["db"])
    recorder = PayloadRecorder()
    tracer = build_tracer(ForensicsExporter(conn, tmp_env["traces"], recorder))
    return conn, tracer, recorder


HAPPY = [
    ExtractedEntities(dates=["2026-01-01"], confidence=5),
    Classification(doc_type=DocumentType.invoice, confidence=4),
    Summary(summary="ok", confidence=5),
]


def test_happy_path_writes_five_spans(tmp_env):
    llm = MockLLM(list(HAPPY))
    conn, tracer, recorder = build_env(tmp_env, llm)
    trace_id = run_pipeline("doc text", "d1", llm, tracer, recorder)
    steps = [r["step"] for r in conn.execute(
        "SELECT step FROM spans WHERE trace_id=? ORDER BY started_at", (trace_id,))]
    assert steps == ["pipeline", "intake", "extract", "classify", "summarize"]
    assert conn.execute(
        "SELECT status FROM traces WHERE trace_id=?", (trace_id,)
    ).fetchone()["status"] == "ok"


def test_trace_json_carries_step_payloads(tmp_env):
    llm = MockLLM(list(HAPPY))
    conn, tracer, recorder = build_env(tmp_env, llm)
    trace_id = run_pipeline("doc text", "d1", llm, tracer, recorder)
    path = conn.execute(
        "SELECT json_path FROM traces WHERE trace_id=?", (trace_id,)
    ).fetchone()["json_path"]
    doc = json.loads(open(path, encoding="utf-8").read())
    spans = {s["step"]: s for s in doc["spans"]}
    assert spans["extract"]["output"]["dates"] == ["2026-01-01"]
    assert spans["extract"]["confidence"] == 5
    assert spans["classify"]["input"]["entities"]["dates"] == ["2026-01-01"]
    assert spans["summarize"]["prompt"]  # prompt captured
    assert doc["doc_id"] == "d1"


def test_step_failure_skips_downstream_but_flushes_trace(tmp_env):
    llm = MockLLM([RuntimeError("LLM exploded")])  # extract raises
    conn, tracer, recorder = build_env(tmp_env, llm)
    trace_id = run_pipeline("doc text", "d1", llm, tracer, recorder)
    rows = {r["step"]: r for r in conn.execute(
        "SELECT * FROM spans WHERE trace_id=?", (trace_id,))}
    assert set(rows) == {"pipeline", "intake", "extract"}  # classify/summarize skipped
    assert rows["extract"]["status"] == "error"
    assert "LLM exploded" in rows["extract"]["error"]
    assert conn.execute(
        "SELECT status FROM traces WHERE trace_id=?", (trace_id,)
    ).fetchone()["status"] == "error"
```

- [ ] **Step 2: Run tests, verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `backend/pipeline/orchestrator.py`**

```python
from opentelemetry.trace import StatusCode

from pipeline.steps import classify, extract, intake, summarize


class PipelineHalted(Exception):
    """A step failed; downstream steps are skipped."""


def run_pipeline(text: str, doc_id: str, llm, tracer, recorder) -> str:
    """Run the 4-step chain under one trace. Returns the trace_id (hex)."""
    with tracer.start_as_current_span("pipeline") as root:
        trace_id = format(root.get_span_context().trace_id, "032x")
        recorder.record(root.get_span_context().span_id, input={"doc_id": doc_id})
        try:
            doc = _step(tracer, recorder, "intake",
                        inp={"doc_id": doc_id, "text": text},
                        fn=lambda: intake(text, doc_id))
            entities = _step(tracer, recorder, "extract",
                             inp=doc.model_dump(),
                             fn=lambda: extract(llm, doc))
            cls = _step(tracer, recorder, "classify",
                        inp={"doc": doc.model_dump(), "entities": entities.model_dump()},
                        fn=lambda: classify(llm, doc, entities))
            _step(tracer, recorder, "summarize",
                  inp={"doc": doc.model_dump(), "entities": entities.model_dump(),
                       "doc_type": cls.doc_type.value},
                  fn=lambda: summarize(llm, doc, entities, cls.doc_type))
        except PipelineHalted as halted:
            root.set_status(StatusCode.ERROR, str(halted))
    return trace_id


def _step(tracer, recorder, name: str, inp: dict, fn):
    with tracer.start_as_current_span(name) as span:
        span_id = span.get_span_context().span_id
        recorder.record(span_id, input=inp)
        try:
            output, call = fn()
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            recorder.record(span_id, error=str(exc))
            raise PipelineHalted(f"{name}: {exc}") from exc
        payload = {"output": output.model_dump(mode="json")}
        if call is not None:
            payload.update(prompt=call.prompt, raw_response=call.raw_response,
                           tokens_in=call.tokens_in, tokens_out=call.tokens_out)
        if hasattr(output, "confidence"):
            payload["confidence"] = output.confidence
        recorder.record(span_id, **payload)
        return output
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_orchestrator.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: orchestrator runs chain under OTel spans with halt-on-error"
```

---

### Task 8: Synthetic docs + seeded failure injection + batch CLI

**Files:**
- Create: `backend/pipeline/docgen.py`
- Create: `backend/scripts/run_batch.py`
- Test: `backend/tests/test_docgen.py`

Generator produces clean docs for the 5 types from templates with randomized (seeded) names/dates/amounts. Corruptors implement the three spec failure modes. `generate_batch(n, seed, corruption_rate)` corrupts ~20% deterministically.

- [ ] **Step 1: Write failing tests `backend/tests/test_docgen.py`**

```python
from pipeline.docgen import (
    corrupt_ambiguous_category, corrupt_currency_mismatch, corrupt_strip_dates,
    generate_batch, generate_doc,
)


def test_generate_doc_is_deterministic():
    assert generate_doc("invoice", seed=7) == generate_doc("invoice", seed=7)
    assert generate_doc("invoice", seed=7) != generate_doc("invoice", seed=8)


def test_strip_dates_removes_dates():
    text = "Invoice issued 2026-03-15, due 2026-04-15."
    out = corrupt_strip_dates(text)
    assert "2026-03-15" not in out and "2026-04-15" not in out


def test_currency_mismatch_swaps_code_keeps_symbol():
    text = "Total: € 1,200.00 EUR payable to Acme."
    out = corrupt_currency_mismatch(text)
    assert "EUR" not in out
    assert "USD" in out
    assert "€" in out  # symbol/code disagreement = the failure


def test_ambiguous_category_appends_confuser():
    out = corrupt_ambiguous_category("Meeting notes from Monday.")
    assert len(out) > len("Meeting notes from Monday.")


def test_generate_batch_marks_corrupted():
    batch = generate_batch(n=50, seed=42, corruption_rate=0.2)
    assert len(batch) == 50
    corrupted = [d for d in batch if d["corruption"] is not None]
    assert 4 <= len(corrupted) <= 18  # ~20% of 50, wide bounds for the fixed seed
    assert {d["corruption"] for d in corrupted} == {
        "strip_dates", "currency_mismatch", "ambiguous_category",
    }
    # deterministic
    assert generate_batch(n=50, seed=42, corruption_rate=0.2) == batch
```

- [ ] **Step 2: Run tests, verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_docgen.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `backend/pipeline/docgen.py`**

```python
import random
import re

COMPANIES = ["Acme Corp", "Globex", "Initech", "Umbrella Ltd", "Stark Industries",
             "Wayne Enterprises", "Hooli", "Vandelay Industries"]
PEOPLE = ["Anna Rossi", "Marco Bianchi", "Julia Chen", "Omar Haddad",
          "Sofia Costa", "Liam O'Brien"]
CATEGORIES = ["billing", "legal", "staffing", "logistics", "marketing"]

TEMPLATES = {
    "invoice": (
        "INVOICE #{num}\nFrom: {company_a}\nTo: {company_b}\n"
        "Issued: {date_a}  Due: {date_b}\n"
        "Services rendered ({category}): consulting hours.\n"
        "Total: € {amount} EUR\n"
    ),
    "contract": (
        "SERVICE AGREEMENT\nBetween {company_a} and {company_b}.\n"
        "Effective {date_a}, terminating {date_b}.\n"
        "{company_b} shall pay € {amount} EUR monthly for {category} services.\n"
        "Signed: {person_a}, {person_b}\n"
    ),
    "meeting_notes": (
        "MEETING NOTES — {date_a}\nAttendees: {person_a}, {person_b}\n"
        "Discussed {category} budget of € {amount} EUR.\n"
        "Action: {person_a} to follow up by {date_b}.\n"
    ),
    "report": (
        "QUARTERLY REPORT — {company_a}\nPeriod ending {date_a}.\n"
        "{category} spend reached € {amount} EUR, up from last quarter.\n"
        "Prepared by {person_a} on {date_b}.\n"
    ),
    "receipt": (
        "RECEIPT #{num}\nVendor: {company_a}\nDate: {date_a}\n"
        "Item: {category} supplies\nPaid: € {amount} EUR by card\n"
    ),
}

AMBIGUOUS_SENTENCES = [
    "\nNote: this also serves as a binding agreement summary and payment record.",
    "\nP.S. treat this as both the invoice and the final report for the quarter.",
    "\nThis document doubles as meeting minutes and a purchase receipt.",
]


def _random_date(rng: random.Random) -> str:
    return f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def generate_doc(doc_type: str, seed: int) -> str:
    rng = random.Random(seed)
    return TEMPLATES[doc_type].format(
        num=rng.randint(1000, 9999),
        company_a=rng.choice(COMPANIES),
        company_b=rng.choice(COMPANIES),
        person_a=rng.choice(PEOPLE),
        person_b=rng.choice(PEOPLE),
        date_a=_random_date(rng),
        date_b=_random_date(rng),
        amount=f"{rng.randint(100, 99999) / 100 * 100:,.2f}",
        category=rng.choice(CATEGORIES),
    )


DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def corrupt_strip_dates(text: str) -> str:
    return DATE_RE.sub("[date unavailable]", text)


def corrupt_currency_mismatch(text: str) -> str:
    return text.replace("EUR", "USD")


def corrupt_ambiguous_category(text: str, seed: int = 0) -> str:
    rng = random.Random(seed)
    return text + rng.choice(AMBIGUOUS_SENTENCES)


CORRUPTORS = {
    "strip_dates": lambda text, seed: corrupt_strip_dates(text),
    "currency_mismatch": lambda text, seed: corrupt_currency_mismatch(text),
    "ambiguous_category": corrupt_ambiguous_category,
}


def generate_batch(n: int, seed: int, corruption_rate: float = 0.2) -> list[dict]:
    rng = random.Random(seed)
    doc_types = list(TEMPLATES)
    batch = []
    corruptor_names = sorted(CORRUPTORS)
    for i in range(n):
        doc_type = doc_types[i % len(doc_types)]
        text = generate_doc(doc_type, seed=seed + i)
        corruption = None
        if rng.random() < corruption_rate:
            corruption = corruptor_names[i % len(corruptor_names)]
            text = CORRUPTORS[corruption](text, seed + i)
        batch.append({
            "doc_id": f"doc-{i:03d}",
            "doc_type": doc_type,
            "corruption": corruption,
            "text": text,
        })
    # guarantee all three corruption kinds appear at the default demo size
    present = {d["corruption"] for d in batch if d["corruption"]}
    for name in corruptor_names:
        if name not in present and n >= len(corruptor_names):
            idx = corruptor_names.index(name)
            target = batch[idx]
            target["corruption"] = name
            target["text"] = CORRUPTORS[name](
                generate_doc(target["doc_type"], seed=seed + idx), seed + idx
            )
    return batch
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_docgen.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Write `backend/scripts/run_batch.py`**

```python
"""Generate synthetic docs and run the pipeline on each. Requires GEMINI_API_KEY.

Usage (from backend/): python -m scripts.run_batch --n 50 --seed 42
"""
import argparse
import sys
import time
from pathlib import Path

from pipeline.docgen import generate_batch
from pipeline.llm import GeminiClient
from pipeline.orchestrator import run_pipeline
from tracing.exporter import ForensicsExporter
from tracing.recorder import PayloadRecorder
from tracing.setup import build_tracer
from tracing.store import connect

DATA = Path(__file__).resolve().parents[2] / "data"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pause", type=float, default=2.0,
                        help="seconds between docs (free-tier rate limits)")
    args = parser.parse_args()

    conn = connect(DATA / "forensics.db")
    recorder = PayloadRecorder()
    tracer = build_tracer(ForensicsExporter(conn, DATA / "traces", recorder))
    llm = GeminiClient()

    for doc in generate_batch(args.n, args.seed):
        trace_id = run_pipeline(doc["text"], doc["doc_id"], llm, tracer, recorder)
        marker = f" [{doc['corruption']}]" if doc["corruption"] else ""
        print(f"{doc['doc_id']} ({doc['doc_type']}){marker} -> {trace_id}")
        time.sleep(args.pause)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/pipeline/docgen.py backend/scripts backend/tests/test_docgen.py
git commit -m "feat: seeded synthetic doc generator, failure injectors, batch CLI"
```

---

### Task 9: Forensics engine (judge, backward walk, classifier)

**Files:**
- Create: `backend/forensics/engine.py`
- Test: `backend/tests/test_forensics.py`

`diagnose(trace_doc, llm)` takes the trace JSON dict. Judge scores each step's output given its input (1–5). Root cause = earliest step scoring ≥2 below the previous step's score (previous score starts at 5; an errored span scores 1 automatically). No such drop → lowest scorer reported with `confident=False`. A second LLM call assigns the failure category.

- [ ] **Step 1: Write failing tests `backend/tests/test_forensics.py`**

```python
from forensics.engine import CategoryVerdict, JudgeVerdict, diagnose
from pipeline.models import FailureCategory
from tests.conftest import MockLLM


def make_trace(spans):
    return {"trace_id": "t1", "doc_id": "d1", "status": "ok", "spans": spans}


def span(step, status="ok", error=None):
    return {"step": step, "status": status, "error": error,
            "input": {"x": 1}, "output": {"y": 2}, "confidence": 4}


def test_root_cause_is_first_big_drop():
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


def test_no_big_drop_reports_worst_step_unconfident():
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


def test_errored_span_scores_one_without_judge_call():
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


def test_judge_failure_marks_step_unjudgeable():
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_forensics.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `backend/forensics/engine.py`**

```python
import json

from pydantic import BaseModel, Field

from pipeline.models import Diagnosis, FailureCategory, StepJudgement

JUDGE_PROMPT = """You are a strict QA judge for the "{step}" step of a document pipeline.
Given the step's INPUT and its OUTPUT, score OUTPUT quality from 1 to 5:
5 = fully correct and faithful to the input;
3 = usable but with noticeable issues;
1 = wrong, fabricated, or contradicts the input.
Penalize invented facts (dates, amounts, parties not present in the input),
wrong classifications, and information lost from the input.
Explain your score in one or two sentences.

INPUT:
{input}

OUTPUT:
{output}
"""

CATEGORY_PROMPT = """A document pipeline failed. The diagnosed root-cause step is "{step}".
Per-step judge findings (in execution order):
{findings}

Pick the single best failure category:
- extraction_hallucination: extraction invented entities not present in the source
- misclassification: document type was classified wrongly
- propagation_error: an upstream mistake was inherited and amplified downstream
- context_loss: information present upstream was dropped, degrading the output
- prompt_failure: the step's prompt/LLM call itself failed or produced unusable output
Explain your choice in one sentence.
"""


class JudgeVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    reasoning: str


class CategoryVerdict(BaseModel):
    category: FailureCategory
    explanation: str


def diagnose(trace_doc: dict, llm) -> Diagnosis:
    spans = [s for s in trace_doc["spans"] if s["step"] != "pipeline"]
    judgements: list[StepJudgement] = []
    for s in spans:
        if s["status"] == "error":
            judgements.append(StepJudgement(
                step=s["step"], score=1,
                reasoning=f"step errored: {s.get('error')}"))
            continue
        prompt = JUDGE_PROMPT.format(
            step=s["step"],
            input=json.dumps(s.get("input"), default=str),
            output=json.dumps(s.get("output"), default=str),
        )
        try:
            verdict, _ = llm.generate_structured(prompt, JudgeVerdict)
            judgements.append(StepJudgement(
                step=s["step"], score=verdict.score, reasoning=verdict.reasoning))
        except Exception as exc:
            judgements.append(StepJudgement(
                step=s["step"], score=3, reasoning=f"unjudgeable: {exc}"))

    root_step, confident = _find_root_cause(judgements)
    category = _classify(llm, root_step, judgements)
    evidence = [f"{j.step}: score {j.score}/5 — {j.reasoning}" for j in judgements]
    return Diagnosis(
        trace_id=trace_doc["trace_id"], root_cause_step=root_step,
        category=category, confident=confident,
        judgements=judgements, evidence_chain=evidence,
    )


def _find_root_cause(judgements: list[StepJudgement]) -> tuple[str, bool]:
    prev_score = 5
    for j in judgements:
        if j.score <= prev_score - 2:
            return j.step, True
        prev_score = j.score
    worst = min(judgements, key=lambda j: j.score)
    return worst.step, False


def _classify(llm, root_step: str, judgements: list[StepJudgement]) -> FailureCategory:
    findings = "\n".join(f"- {j.step}: {j.score}/5 — {j.reasoning}" for j in judgements)
    prompt = CATEGORY_PROMPT.format(step=root_step, findings=findings)
    try:
        verdict, _ = llm.generate_structured(prompt, CategoryVerdict)
        return verdict.category
    except Exception:
        return FailureCategory.prompt_failure
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_forensics.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/forensics backend/tests/test_forensics.py
git commit -m "feat: forensics engine with LLM judge, backward walk, categorizer"
```

---

### Task 10: Eval store + runner

**Files:**
- Create: `backend/evals/store.py`
- Create: `backend/evals/runner.py`
- Test: `backend/tests/test_evals.py`

An eval case pins: original step input, failing step, bad output, corrected output, category. The runner re-executes the failing step live and asks the judge whether the new output matches the correction (pass = score ≥ 4). Results append to `eval_results` for the dashboard trend.

- [ ] **Step 1: Write failing tests `backend/tests/test_evals.py`**

```python
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
```

- [ ] **Step 2: Run tests, verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_evals.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `backend/evals/store.py`**

```python
import json
from pathlib import Path

from pydantic import BaseModel

from pipeline.models import FailureCategory


class EvalCase(BaseModel):
    case_id: str
    trace_id: str
    failing_step: str
    category: FailureCategory
    original_input: dict
    bad_output: dict
    corrected_output: dict


def create_case(conn, evals_dir: Path, case: EvalCase, created_at: str):
    evals_dir.mkdir(parents=True, exist_ok=True)
    path = evals_dir / f"{case.case_id}.json"
    path.write_text(case.model_dump_json(indent=2), encoding="utf-8")
    conn.execute(
        "INSERT OR REPLACE INTO eval_cases "
        "(case_id, trace_id, failing_step, category, created_at, json_path) "
        "VALUES (?,?,?,?,?,?)",
        (case.case_id, case.trace_id, case.failing_step,
         case.category.value, created_at, str(path)),
    )
    conn.commit()


def list_cases(conn, evals_dir: Path) -> list[EvalCase]:
    rows = conn.execute("SELECT json_path FROM eval_cases ORDER BY created_at").fetchall()
    return [EvalCase.model_validate_json(Path(r["json_path"]).read_text(encoding="utf-8"))
            for r in rows]
```

- [ ] **Step 4: Write `backend/evals/runner.py`**

```python
import json

from pydantic import BaseModel, Field

from evals.store import list_cases
from pipeline.models import Classification, DocumentType, ExtractedEntities, RawDocument
from pipeline.steps import classify, extract, summarize

EVAL_JUDGE_PROMPT = """An earlier pipeline failure produced a corrected reference output.
Compare the NEW OUTPUT of the re-run step "{step}" against the CORRECTED OUTPUT.
Score 1-5: 5 = new output is as good as the correction (failure resolved);
1 = new output repeats the original failure. One-sentence reasoning.

STEP INPUT:
{input}

CORRECTED OUTPUT:
{corrected}

NEW OUTPUT:
{new}
"""


class EvalJudgeVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    reasoning: str


def _rerun_step(llm, step: str, original_input: dict):
    if step == "extract":
        out, _ = extract(llm, RawDocument(**original_input))
    elif step == "classify":
        out, _ = classify(llm, RawDocument(**original_input["doc"]),
                          ExtractedEntities(**original_input["entities"]))
    elif step == "summarize":
        out, _ = summarize(llm, RawDocument(**original_input["doc"]),
                           ExtractedEntities(**original_input["entities"]),
                           DocumentType(original_input["doc_type"]))
    else:
        raise ValueError(f"step {step} cannot be re-run")
    return out


def run_evals(conn, evals_dir, llm, run_at: str) -> list[dict]:
    results = []
    for case in list_cases(conn, evals_dir):
        try:
            new_output = _rerun_step(llm, case.failing_step, case.original_input)
            prompt = EVAL_JUDGE_PROMPT.format(
                step=case.failing_step,
                input=json.dumps(case.original_input, default=str),
                corrected=json.dumps(case.corrected_output, default=str),
                new=new_output.model_dump_json(),
            )
            verdict, _ = llm.generate_structured(prompt, EvalJudgeVerdict)
            passed, score = verdict.score >= 4, verdict.score
        except Exception:
            passed, score = False, 1
        conn.execute(
            "INSERT INTO eval_results (run_at, case_id, passed, score) VALUES (?,?,?,?)",
            (run_at, case.case_id, int(passed), score),
        )
        results.append({"case_id": case.case_id, "passed": passed, "score": score})
    conn.commit()
    return results
```

- [ ] **Step 5: Run tests, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_evals.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/evals backend/tests/test_evals.py
git commit -m "feat: eval case store and judge-based eval runner"
```

---

### Task 11: FastAPI app

**Files:**
- Create: `backend/api/app.py`
- Test: `backend/tests/test_api.py`

App factory takes `data_dir` and an injectable `llm` (tests pass `MockLLM`; production lazily builds `GeminiClient`). All routes under `/api`. CORS open for the Vite dev server.

- [ ] **Step 1: Write failing tests `backend/tests/test_api.py`**

```python
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from evals.runner import EvalJudgeVerdict
from forensics.engine import CategoryVerdict, JudgeVerdict
from pipeline.models import (
    Classification, DocumentType, ExtractedEntities, FailureCategory, Summary,
)
from tests.conftest import MockLLM

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
def client(tmp_path):
    llm = MockLLM()
    app = create_app(tmp_path / "data", llm=llm)
    return TestClient(app), llm


def run_one(client, llm):
    llm.responses.extend(HAPPY)
    resp = client.post("/api/runs", json={"text": "Invoice ...", "doc_id": "d1"})
    assert resp.status_code == 200
    return resp.json()["trace_id"]


def test_run_and_get_trace(client):
    client, llm = client
    trace_id = run_one(client, llm)
    listing = client.get("/api/traces").json()
    assert listing[0]["trace_id"] == trace_id
    trace = client.get(f"/api/traces/{trace_id}").json()
    assert [s["step"] for s in trace["spans"]] == [
        "pipeline", "intake", "extract", "classify", "summarize"]


def test_get_missing_trace_404(client):
    client, _ = client
    assert client.get("/api/traces/deadbeef").status_code == 404


def test_flag_runs_forensics_and_stores_diagnosis(client):
    client, llm = client
    trace_id = run_one(client, llm)
    llm.responses.extend(FORENSICS)
    diagnosis = client.post(f"/api/traces/{trace_id}/flag").json()
    assert diagnosis["root_cause_step"] == "extract"
    assert diagnosis["category"] == "extraction_hallucination"
    again = client.get(f"/api/traces/{trace_id}/diagnosis").json()
    assert again == diagnosis
    assert client.get("/api/traces").json()[0]["flagged"] == 1


def test_eval_lifecycle_and_stats(client):
    client, llm = client
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


def test_eval_without_diagnosis_409(client):
    client, llm = client
    trace_id = run_one(client, llm)
    resp = client.post("/api/evals", json={"trace_id": trace_id, "corrected_output": {}})
    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests, verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write `backend/api/app.py`**

```python
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
```

- [ ] **Step 4: Run tests, verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Run full backend suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all PASS.

- [ ] **Step 6: Smoke-check the server boots (no API key needed — don't call LLM routes)**

Run (from `backend/`):
```bash
GEMINI_API_KEY=dummy .venv/Scripts/python -m uvicorn api.app:create_default_app --factory --port 8000 &
curl -s http://localhost:8000/api/traces
```
Expected: `[]`. Kill the server afterwards.

- [ ] **Step 7: Commit**

```bash
git add backend/api backend/tests/test_api.py
git commit -m "feat: FastAPI endpoints for runs, traces, forensics, evals, stats"
```

---

### Task 12: Frontend scaffold + API client + flow transform

**Files:**
- Create: `frontend/` (Vite react-ts scaffold)
- Create: `frontend/src/api.ts`
- Create: `frontend/src/traceFlow.ts`
- Test: `frontend/src/traceFlow.test.ts`
- Modify: `frontend/vite.config.ts` (proxy + vitest)

- [ ] **Step 1: Scaffold (from repo root)**

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install @xyflow/react recharts react-router-dom
npm install -D vitest
```

- [ ] **Step 2: Replace `frontend/vite.config.ts`**

```typescript
/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
  test: { environment: "node" },
});
```

Add to `frontend/package.json` scripts: `"test": "vitest run"`.

- [ ] **Step 3: Write `frontend/src/api.ts`**

```typescript
export interface SpanRecord {
  span_id: string;
  trace_id: string;
  step: string;
  status: "ok" | "error";
  latency_ms: number;
  started_at: string;
  error: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  confidence: number | null;
  input: unknown;
  output: unknown;
  prompt: string | null;
  raw_response: string | null;
}

export interface TraceDoc {
  trace_id: string;
  doc_id: string | null;
  created_at: string;
  status: string;
  spans: SpanRecord[];
}

export interface TraceSummary {
  trace_id: string;
  doc_id: string | null;
  created_at: string;
  status: string;
  flagged: number;
  root_cause_step: string | null;
  category: string | null;
}

export interface Judgement {
  step: string;
  score: number;
  reasoning: string;
}

export interface Diagnosis {
  trace_id: string;
  root_cause_step: string;
  category: string;
  confident: boolean;
  judgements: Judgement[];
  evidence_chain: string[];
}

export interface EvalCaseSummary {
  case_id: string;
  trace_id: string;
  failing_step: string;
  category: string;
  created_at: string;
}

export interface Stats {
  failure_types: { category: string; count: number }[];
  failures_per_step: { step: string; count: number }[];
  rate_over_time: { day: string; total: number; flagged: number }[];
  eval_trend: { run_at: string; total: number; passed: number }[];
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

async function post<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export const api = {
  listTraces: () => get<TraceSummary[]>("/api/traces"),
  getTrace: (id: string) => get<TraceDoc>(`/api/traces/${id}`),
  flagTrace: (id: string) => post<Diagnosis>(`/api/traces/${id}/flag`),
  getDiagnosis: (id: string) => get<Diagnosis>(`/api/traces/${id}/diagnosis`),
  createEval: (traceId: string, corrected: unknown) =>
    post<EvalCaseSummary>("/api/evals", { trace_id: traceId, corrected_output: corrected }),
  listEvals: (traceId?: string) =>
    get<EvalCaseSummary[]>(traceId ? `/api/evals?trace_id=${traceId}` : "/api/evals"),
  runEvals: () => post<{ case_id: string; passed: boolean; score: number }[]>("/api/evals/run"),
  stats: () => get<Stats>("/api/stats"),
};
```

- [ ] **Step 4: Write failing test `frontend/src/traceFlow.test.ts`**

```typescript
import { expect, test } from "vitest";
import type { Diagnosis, SpanRecord } from "./api";
import { nodeColor, traceToFlow } from "./traceFlow";

function span(step: string, over: Partial<SpanRecord> = {}): SpanRecord {
  return {
    span_id: step, trace_id: "t1", step, status: "ok", latency_ms: 10,
    started_at: "2026-07-02T00:00:00Z", error: null, tokens_in: 1, tokens_out: 1,
    confidence: 5, input: {}, output: {}, prompt: null, raw_response: null,
    ...over,
  };
}

const DIAGNOSIS: Diagnosis = {
  trace_id: "t1", root_cause_step: "extract", category: "extraction_hallucination",
  confident: true, judgements: [], evidence_chain: [],
};

test("healthy=green, low-confidence=yellow, root-cause and error=red", () => {
  expect(nodeColor(span("intake"), null)).toBe("#30a46c");
  expect(nodeColor(span("classify", { confidence: 3 }), null)).toBe("#f5d90a");
  expect(nodeColor(span("extract"), DIAGNOSIS)).toBe("#e5484d");
  expect(nodeColor(span("summarize", { status: "error" }), null)).toBe("#e5484d");
});

test("traceToFlow drops the pipeline root span and chains edges", () => {
  const spans = ["pipeline", "intake", "extract", "classify", "summarize"].map((s) => span(s));
  const { nodes, edges } = traceToFlow(spans, null);
  expect(nodes.map((n) => n.id)).toEqual(["intake", "extract", "classify", "summarize"]);
  expect(edges.map((e) => `${e.source}->${e.target}`)).toEqual([
    "intake->extract", "extract->classify", "classify->summarize",
  ]);
});
```

- [ ] **Step 5: Run test, verify failure**

Run (from `frontend/`): `npm test`
Expected: FAIL (`traceFlow.ts` missing).

- [ ] **Step 6: Write `frontend/src/traceFlow.ts`**

```typescript
import type { Edge, Node } from "@xyflow/react";
import type { Diagnosis, SpanRecord } from "./api";

export const GREEN = "#30a46c";
export const YELLOW = "#f5d90a";
export const RED = "#e5484d";

export function nodeColor(span: SpanRecord, diagnosis: Diagnosis | null): string {
  if (span.status === "error") return RED;
  if (diagnosis && diagnosis.root_cause_step === span.step) return RED;
  if (span.confidence !== null && span.confidence <= 3) return YELLOW;
  return GREEN;
}

export function traceToFlow(
  spans: SpanRecord[],
  diagnosis: Diagnosis | null,
): { nodes: Node[]; edges: Edge[] } {
  const steps = spans.filter((s) => s.step !== "pipeline");
  const nodes: Node[] = steps.map((s, i) => ({
    id: s.step,
    position: { x: i * 220, y: 100 },
    data: { label: s.step },
    style: {
      background: nodeColor(s, diagnosis),
      color: s.confidence !== null && s.confidence <= 3 && s.status === "ok" ? "#222" : "#fff",
      borderRadius: 8,
      padding: 12,
      width: 160,
      textAlign: "center" as const,
    },
  }));
  const edges: Edge[] = steps.slice(1).map((s, i) => ({
    id: `${steps[i].step}->${s.step}`,
    source: steps[i].step,
    target: s.step,
    animated: true,
  }));
  return { nodes, edges };
}
```

- [ ] **Step 7: Run test, verify pass**

Run: `npm test`
Expected: 2 PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat: frontend scaffold, typed API client, trace-to-flow transform"
```

---

### Task 13: Routing + trace list page

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/index.css`
- Create: `frontend/src/pages/TraceList.tsx`
- Delete: `frontend/src/App.css` (scaffold leftover made unused by this rewrite)

- [ ] **Step 1: Replace `frontend/src/index.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; background: #0f1115; color: #e6e6e6; }
a { color: #7cb7ff; text-decoration: none; }
nav { display: flex; gap: 16px; padding: 12px 24px; background: #171a21; border-bottom: 1px solid #2a2e39; }
nav .brand { font-weight: 700; color: #fff; }
main { padding: 24px; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #2a2e39; font-size: 14px; }
.badge { padding: 2px 8px; border-radius: 10px; font-size: 12px; color: #fff; }
.badge.ok { background: #30a46c; }
.badge.error { background: #e5484d; }
.badge.flagged { background: #ad5700; }
button { background: #2563eb; color: #fff; border: 0; border-radius: 6px; padding: 8px 14px; cursor: pointer; }
button:disabled { opacity: 0.5; cursor: default; }
textarea { width: 100%; background: #171a21; color: #e6e6e6; border: 1px solid #2a2e39; border-radius: 6px; padding: 8px; font-family: monospace; }
pre { background: #171a21; border: 1px solid #2a2e39; border-radius: 6px; padding: 12px; overflow-x: auto; font-size: 12px; }
```

- [ ] **Step 2: Replace `frontend/src/App.tsx`**

```tsx
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import TraceList from "./pages/TraceList";
import TraceView from "./pages/TraceView";

export default function App() {
  return (
    <BrowserRouter>
      <nav>
        <span className="brand">Failure Forensics</span>
        <Link to="/">Traces</Link>
        <Link to="/dashboard">Dashboard</Link>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<TraceList />} />
          <Route path="/traces/:traceId" element={<TraceView />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
```

Note: `Dashboard` and `TraceView` don't exist yet — create placeholder files now so the app compiles; Tasks 14–15 replace them:

`frontend/src/pages/TraceView.tsx` (placeholder): `export default function TraceView() { return <p>trace view</p>; }`
`frontend/src/pages/Dashboard.tsx` (placeholder): `export default function Dashboard() { return <p>dashboard</p>; }`

Also simplify `frontend/src/main.tsx` to:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 3: Write `frontend/src/pages/TraceList.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type TraceSummary } from "../api";

export default function TraceList() {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listTraces().then(setTraces).catch((e) => setError(String(e)));
  }, []);

  if (error) return <p>Failed to load traces: {error}</p>;
  return (
    <>
      <h2>Traces</h2>
      <table>
        <thead>
          <tr><th>Trace</th><th>Document</th><th>Created</th><th>Status</th><th>Root cause</th><th>Category</th></tr>
        </thead>
        <tbody>
          {traces.map((t) => (
            <tr key={t.trace_id}>
              <td><Link to={`/traces/${t.trace_id}`}>{t.trace_id.slice(0, 12)}…</Link></td>
              <td>{t.doc_id ?? "—"}</td>
              <td>{t.created_at.slice(0, 19)}</td>
              <td>
                <span className={`badge ${t.status}`}>{t.status}</span>{" "}
                {t.flagged === 1 && <span className="badge flagged">flagged</span>}
              </td>
              <td>{t.root_cause_step ?? "—"}</td>
              <td>{t.category ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
```

- [ ] **Step 4: Verify it compiles and renders**

Run: `npm run build` (from `frontend/`)
Expected: build succeeds. Then `npm run dev`, open `http://localhost:5173` — nav renders, trace table loads (empty list OK if backend down shows the error line).

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git rm frontend/src/App.css
git commit -m "feat: app shell with routing and trace list page"
```

---

### Task 14: Trace view — flow graph, span drawer, diff view, flag + diagnosis

**Files:**
- Replace: `frontend/src/pages/TraceView.tsx`
- Create: `frontend/src/components/SpanDrawer.tsx`
- Create: `frontend/src/components/DiffView.tsx`
- Create: `frontend/src/components/DiagnosisPanel.tsx`

- [ ] **Step 1: Write `frontend/src/components/SpanDrawer.tsx`**

```tsx
import type { SpanRecord } from "../api";

function Json({ value }: { value: unknown }) {
  return <pre>{value == null ? "—" : JSON.stringify(value, null, 2)}</pre>;
}

export default function SpanDrawer({ span }: { span: SpanRecord }) {
  return (
    <div style={{ borderTop: "1px solid #2a2e39", paddingTop: 12 }}>
      <h3>
        {span.step}{" "}
        <small>
          {span.latency_ms.toFixed(0)} ms · tokens {span.tokens_in ?? 0}/{span.tokens_out ?? 0} ·
          confidence {span.confidence ?? "—"}/5 · {span.status}
        </small>
      </h3>
      {span.error && <p style={{ color: "#e5484d" }}>Error: {span.error}</p>}
      <details open><summary>Input</summary><Json value={span.input} /></details>
      <details open><summary>Output</summary><Json value={span.output} /></details>
      <details><summary>LLM prompt</summary><pre>{span.prompt ?? "—"}</pre></details>
      <details><summary>Raw response</summary><pre>{span.raw_response ?? "—"}</pre></details>
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/src/components/DiffView.tsx`**

Expected column: the eval correction when one exists for this trace's failing step; otherwise the judge's reasoning as prose.

```tsx
import type { Diagnosis, SpanRecord } from "../api";

export default function DiffView({
  span, diagnosis, correctedOutput,
}: {
  span: SpanRecord;
  diagnosis: Diagnosis | null;
  correctedOutput: unknown | null;
}) {
  const judgement = diagnosis?.judgements.find((j) => j.step === span.step);
  return (
    <div>
      <h3>Received vs produced vs expected — {span.step}</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        <div><h4>Received (input)</h4><pre>{JSON.stringify(span.input, null, 2)}</pre></div>
        <div><h4>Produced (output)</h4><pre>{JSON.stringify(span.output, null, 2)}</pre></div>
        <div>
          <h4>Should have produced</h4>
          {correctedOutput != null
            ? <pre>{JSON.stringify(correctedOutput, null, 2)}</pre>
            : <p style={{ fontSize: 13 }}>{judgement ? `Judge: ${judgement.reasoning}` : "Flag the trace to get a judgement."}</p>}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write `frontend/src/components/DiagnosisPanel.tsx`**

```tsx
import { useState } from "react";
import { api, type Diagnosis, type SpanRecord } from "../api";

export default function DiagnosisPanel({
  diagnosis, rootSpan, onEvalCreated,
}: {
  diagnosis: Diagnosis;
  rootSpan: SpanRecord | undefined;
  onEvalCreated: (corrected: unknown) => void;
}) {
  const [corrected, setCorrected] = useState(
    JSON.stringify(rootSpan?.output ?? {}, null, 2),
  );
  const [status, setStatus] = useState<string | null>(null);

  async function confirmFlag() {
    try {
      const parsed = JSON.parse(corrected);
      await api.createEval(diagnosis.trace_id, parsed);
      setStatus("Eval case created.");
      onEvalCreated(parsed);
    } catch (e) {
      setStatus(String(e));
    }
  }

  return (
    <div style={{ border: "1px solid #e5484d", borderRadius: 8, padding: 16, marginTop: 16 }}>
      <h3>
        Diagnosis: root cause = <strong>{diagnosis.root_cause_step}</strong>{" "}
        ({diagnosis.category}){!diagnosis.confident && " — low confidence"}
      </h3>
      <ol>
        {diagnosis.evidence_chain.map((line, i) => <li key={i}>{line}</li>)}
      </ol>
      <h4>Corrected output (edit, then confirm to create an eval case)</h4>
      <textarea rows={8} value={corrected} onChange={(e) => setCorrected(e.target.value)} />
      <p>
        <button onClick={confirmFlag}>Confirm flag → create eval case</button>{" "}
        {status && <small>{status}</small>}
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Replace `frontend/src/pages/TraceView.tsx`**

```tsx
import { ReactFlow, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Diagnosis, type TraceDoc } from "../api";
import DiagnosisPanel from "../components/DiagnosisPanel";
import DiffView from "../components/DiffView";
import SpanDrawer from "../components/SpanDrawer";
import { traceToFlow } from "../traceFlow";

export default function TraceView() {
  const { traceId } = useParams<{ traceId: string }>();
  const [trace, setTrace] = useState<TraceDoc | null>(null);
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [correctedOutput, setCorrectedOutput] = useState<unknown | null>(null);
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [flagging, setFlagging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!traceId) return;
    api.getTrace(traceId).then(setTrace).catch((e) => setError(String(e)));
    api.getDiagnosis(traceId).then(setDiagnosis).catch(() => setDiagnosis(null));
  }, [traceId]);

  const flow = useMemo(
    () => (trace ? traceToFlow(trace.spans, diagnosis) : { nodes: [], edges: [] }),
    [trace, diagnosis],
  );

  async function flag() {
    if (!traceId) return;
    setFlagging(true);
    try {
      setDiagnosis(await api.flagTrace(traceId));
    } catch (e) {
      setError(String(e));
    } finally {
      setFlagging(false);
    }
  }

  if (error) return <p>{error}</p>;
  if (!trace) return <p>Loading…</p>;

  const selectedSpan = trace.spans.find((s) => s.step === selectedStep);
  const rootSpan = diagnosis
    ? trace.spans.find((s) => s.step === diagnosis.root_cause_step)
    : undefined;

  return (
    <>
      <h2>
        Trace {trace.trace_id.slice(0, 12)}… — {trace.doc_id ?? "?"}{" "}
        <button onClick={flag} disabled={flagging}>
          {flagging ? "Diagnosing…" : diagnosis ? "Re-run diagnosis" : "Flag: find root cause"}
        </button>
      </h2>
      <div style={{ height: 260, border: "1px solid #2a2e39", borderRadius: 8 }}>
        <ReactFlow
          nodes={flow.nodes}
          edges={flow.edges}
          onNodeClick={(_evt, node: Node) => setSelectedStep(node.id)}
          fitView
          colorMode="dark"
        />
      </div>
      {diagnosis && (
        <DiagnosisPanel
          diagnosis={diagnosis}
          rootSpan={rootSpan}
          onEvalCreated={setCorrectedOutput}
        />
      )}
      {selectedSpan && (
        <>
          <SpanDrawer span={selectedSpan} />
          <DiffView
            span={selectedSpan}
            diagnosis={diagnosis}
            correctedOutput={
              diagnosis && selectedSpan.step === diagnosis.root_cause_step
                ? correctedOutput
                : null
            }
          />
        </>
      )}
    </>
  );
}
```

- [ ] **Step 5: Verify build + manual check**

Run: `npm run build`
Expected: success. Then with backend running and at least one trace in `data/` (any tmp run), open a trace: 4 colored nodes render, clicking opens drawer, Flag button triggers diagnosis panel.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat: trace explorer with flow graph, span drawer, diff, diagnosis"
```

---

### Task 15: Dashboard page

**Files:**
- Replace: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Write `frontend/src/pages/Dashboard.tsx`**

```tsx
import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api, type Stats } from "../api";

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid #2a2e39", borderRadius: 8, padding: 16 }}>
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      <div style={{ height: 240 }}>{children}</div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.stats().then(setStats).catch((e) => setError(String(e)));
  useEffect(() => { load(); }, []);

  async function runEvals() {
    setRunning(true);
    try {
      await api.runEvals();
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }

  if (error) return <p>{error}</p>;
  if (!stats) return <p>Loading…</p>;

  const evalTrend = stats.eval_trend.map((e) => ({
    ...e, resolved_pct: e.total ? Math.round((100 * e.passed) / e.total) : 0,
  }));

  return (
    <>
      <h2>
        Dashboard{" "}
        <button onClick={runEvals} disabled={running}>
          {running ? "Running evals…" : "Re-run eval dataset"}
        </button>
      </h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Panel title="Most common failure types">
          <ResponsiveContainer>
            <BarChart data={stats.failure_types}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2e39" />
              <XAxis dataKey="category" tick={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#e5484d" />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Failures per step">
          <ResponsiveContainer>
            <BarChart data={stats.failures_per_step}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2e39" />
              <XAxis dataKey="step" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#f5d90a" />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Flagged traces over time">
          <ResponsiveContainer>
            <LineChart data={stats.rate_over_time}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2e39" />
              <XAxis dataKey="day" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line dataKey="total" stroke="#7cb7ff" />
              <Line dataKey="flagged" stroke="#e5484d" />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Known failures resolved (% of eval cases passing)">
          <ResponsiveContainer>
            <LineChart data={evalTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2e39" />
              <XAxis dataKey="run_at" tick={{ fontSize: 10 }} />
              <YAxis domain={[0, 100]} unit="%" />
              <Tooltip />
              <Line dataKey="resolved_pct" stroke="#30a46c" />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Verify build + manual check**

Run: `npm run build`
Expected: success. With backend up, `/dashboard` renders four panels (empty charts OK before demo data exists).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: dashboard with failure types, per-step, trend, eval charts"
```

---

### Task 16: Docker Compose

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `docker/nginx.conf`
- Create: `docker-compose.yml`

- [ ] **Step 1: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY pipeline ./pipeline
COPY tracing ./tracing
COPY forensics ./forensics
COPY evals ./evals
COPY api ./api
COPY scripts ./scripts
RUN pip install --no-cache-dir .
ENV DATA_DIR=/data
EXPOSE 8000
CMD ["uvicorn", "api.app:create_default_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `docker/nginx.conf`**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://backend:8000;
    }

    location / {
        try_files $uri /index.html;  # SPA routing
    }
}
```

- [ ] **Step 3: Write `frontend/Dockerfile`**

The compose file below builds this with the repo root as context (`dockerfile: frontend/Dockerfile`) so the image can copy `docker/nginx.conf`; all COPY paths are therefore root-relative:

```dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
```

- [ ] **Step 4: Write `docker-compose.yml`**

```yaml
services:
  backend:
    build: ./backend
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - GEMINI_MODEL=${GEMINI_MODEL:-gemini-flash-lite-latest}
      - DATA_DIR=/data
    volumes:
      - ./data:/data
    ports:
      - "8000:8000"

  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
    depends_on:
      - backend
    ports:
      - "5173:80"
```

- [ ] **Step 5: Build and smoke test**

Run (from repo root, with `GEMINI_API_KEY` set in the environment or a `.env` file):
```bash
docker compose build
docker compose up -d
curl -s http://localhost:8000/api/traces
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/
docker compose down
```
Expected: `[]` from the API; `200` from the frontend.

- [ ] **Step 6: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile docker docker-compose.yml
git commit -m "feat: dockerize backend and frontend with compose"
```

---

### Task 17: Demo run + README

**Files:**
- Create: `README.md`

This task exercises the whole system live (needs `GEMINI_API_KEY`) and satisfies the spec's success criteria: 50 docs, 8–10 injected failures across all three corruption kinds, root cause diagnosed in seconds.

- [ ] **Step 1: Run the batch**

Run (from `backend/`, venv active, `GEMINI_API_KEY` set):
```bash
python -m scripts.run_batch --n 50 --seed 42
```
Expected: 50 lines printed, ~10 marked with a corruption tag. Free-tier pacing: ~2s pause per doc → about 5–10 minutes total. If a run dies on quota, re-run with a higher `--pause`.

- [ ] **Step 2: Verify failure count in SQLite**

Run (from repo root):
```bash
python -c "import sqlite3; c = sqlite3.connect('data/forensics.db'); print(c.execute('SELECT COUNT(*) FROM traces').fetchone(), c.execute(\"SELECT COUNT(*) FROM spans WHERE confidence <= 3 OR status='error'\").fetchone())"
```
Expected: 50 traces; a nonzero count of low-confidence/error spans. If fewer than ~8 candidate failures surface, raise `corruption_rate` (e.g. `0.25`) in a re-run with a fresh `data/` directory.

- [ ] **Step 3: Demo walkthrough (manual, this is the interview script)**

1. `docker compose up -d` (or backend `uvicorn` + frontend `npm run dev`).
2. Open `http://localhost:5173` — trace list shows 50 traces, several yellow/error.
3. Open a corrupted trace (e.g. a `currency_mismatch` doc) → nodes render.
4. Click **Flag: find root cause** → diagnosis appears in seconds, red node marks the root-cause step, evidence chain reads step by step.
5. Edit corrected output → **Confirm flag** → eval case created.
6. Dashboard → failure types populated; **Re-run eval dataset** → resolved-% chart gets a data point.

Expected: every step above works end-to-end. Record 2–3 diagnosed trace_ids for the interview demo.

- [ ] **Step 4: Write `README.md`**

```markdown
# Failure Forensics for AI Pipelines

> Reduces mean time to root cause for AI pipeline failures from hours of
> manual debugging to seconds of automated diagnosis.

An observability layer for a multi-step LLM document pipeline
(intake → extraction → classification → summarization). Every run is traced
with OpenTelemetry spans (prompt, raw response, tokens, latency, confidence),
stored as JSON + SQLite. Flagging a bad trace walks the spans backward with an
LLM-as-judge, pinpoints the first step where quality collapsed, categorizes
the failure, and turns confirmed failures into a growing eval dataset.

## Quick start

    export GEMINI_API_KEY=...        # Google AI Studio, free tier works
    docker compose up -d --build
    cd backend && python -m scripts.run_batch --n 50 --seed 42
    open http://localhost:5173

## Stack

Python 3.12 · Pydantic v2 · google-genai (Gemini Flash-Lite) ·
OpenTelemetry SDK + custom exporter · SQLite + JSON traces · FastAPI ·
React + react-flow + recharts · Docker Compose

## Development

    cd backend && python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
    .venv/Scripts/python -m pytest            # all tests offline (mock LLM)
    .venv/Scripts/python -m uvicorn api.app:create_default_app --factory
    cd frontend && npm install && npm run dev # http://localhost:5173

## How root cause analysis works

1. Judge scores each step's output 1–5 given its input.
2. Earliest step scoring ≥2 below its predecessor = root cause
   (errored steps score 1 automatically).
3. A second LLM call assigns one of five failure categories:
   extraction hallucination, misclassification, propagation error,
   context loss, prompt failure.
4. Confirming a diagnosis creates an eval case; re-running the eval set
   tracks whether known failures stay fixed.
```

- [ ] **Step 5: Final full test run and commit**

Run: `cd backend && .venv/Scripts/python -m pytest -v && cd ../frontend && npm test`
Expected: all PASS.

```bash
git add README.md
git commit -m "docs: README with demo script and architecture summary"
```

