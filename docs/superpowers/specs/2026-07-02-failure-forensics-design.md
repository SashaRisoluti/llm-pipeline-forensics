# Failure Forensics Tool for AI Pipelines — Design Spec

**Date:** 2026-07-02
**Status:** Approved

## Purpose

An observability layer for a multi-step AI document pipeline that traces every intermediate step, identifies exactly where failures originate (root cause analysis via LLM-as-judge), and feeds confirmed failures into a growing evaluation dataset. Portfolio project; the demo headline is: *"Reduces mean time to root cause for AI pipeline failures from hours of manual debugging to seconds of automated diagnosis."*

## Locked Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| LLM provider | Gemini Flash-Lite via Google AI Studio (`google-genai` SDK) | Free tier; retry/backoff required for rate limits |
| Document domain | Synthetic business docs mix (invoice, contract, meeting notes, report, receipt) | Natural fit for date/category/currency failure modes; classification step meaningful |
| Pipeline framework | Custom chain (plain Python functions + Pydantic I/O) | Full control over span instrumentation; no framework magic hiding failures |
| Tracing | Real OpenTelemetry SDK + custom SpanExporter | Industry-standard trace/span IDs and context propagation; full data control |
| Storage | JSON trace files + SQLite index | Big payloads in files; queryable metadata in SQLite |
| UI | React + Vite + TypeScript (react-flow, recharts) + FastAPI backend | Interview polish; real interactive node graph |
| Containerization | Docker Compose (backend + frontend) | One-command demo |
| Time budget | None (14-day phasing from input.md dropped by user) | Quality over speed |

## Repo Layout

```
backend/          Python 3.12
  pipeline/       4 steps + orchestrator + failure injection
  tracing/        OTel setup + custom exporter
  forensics/      backward walk + LLM-as-judge + failure classifier
  evals/          eval case store + runner
  api/            FastAPI app
  tests/
frontend/         React + Vite + TypeScript; react-flow, recharts
data/             docs/, traces/ (JSON), forensics.db (SQLite), evals/
docker-compose.yml
```

## Component 1: Pipeline (custom chain)

Four steps, each an isolated function with Pydantic-typed input and output:

1. `intake`: raw document → `RawDocument` (id, text, metadata). No LLM call.
2. `extract`: `RawDocument` → `ExtractedEntities` (dates, amounts, currencies, parties, categories). LLM call.
3. `classify`: `ExtractedEntities` + text → `DocumentType` (invoice | contract | meeting_notes | report | receipt). LLM call.
4. `summarize`: type-tailored prompt → `Summary`. LLM call.

An orchestrator runs the sequence; each step executes inside an OTel span. If a step hard-fails, the span records status=error, downstream steps are skipped, and the trace remains complete and explorable (failed traces are a core feature, not an edge case).

**LLM client:** thin wrapper around `google-genai` that:
- retries with exponential backoff on 429/quota errors (free-tier rate limits),
- captures prompt, raw response, and token counts for the span,
- requests structured output including a self-assessed confidence score (1–5) from the model.

**Failure injection:** a seeded corruptor mutates synthetic source documents before intake — strips dates, injects ambiguous category vocabulary, mislabels currencies (e.g. € amounts tagged USD). Seed-deterministic so demo runs are reproducible. Target: 50 documents processed with 8–10 failures across different categories.

## Component 2: Tracing Layer

- Real OTel SDK provides trace IDs, span IDs, parent/child context propagation.
- Custom `SpanExporter` writes:
  - one JSON file per trace in `data/traces/` containing full payloads (step input, output, LLM prompt, raw response, errors, confidence),
  - one SQLite row per span: trace_id, span_id, step name, status, latency_ms, tokens_in, tokens_out, confidence, error summary.
- OTel span attributes hold only primitives (metadata + pointer to the JSON file); nested payloads live in the trace files because OTel attributes cannot hold structured data.

## Component 3: Forensics Engine (root cause analysis)

Triggered when a trace is flagged:

1. Walk spans backward from the final step.
2. LLM-as-judge (same Gemini model, dedicated judge prompt) scores each step's output quality 1–5 **given that step's input**.
3. The first (earliest) step whose quality score drops significantly (≥2 points below its upstream input quality) is the root cause.
4. Classify the failure into one of five categories: Extraction Hallucination, Misclassification, Propagation Error, Prompt Failure, Context Loss.
5. Emit a Pydantic `Diagnosis`: root-cause step, category, per-step judge scores, and a quote-level evidence chain (e.g. "extraction emitted date 2024-13-45; classification inherited it; summary asserted a deadline that does not exist").

## Component 4: API (FastAPI)

| Endpoint | Purpose |
| --- | --- |
| `POST /runs` | Run pipeline on one document or a batch |
| `GET /traces` | List traces (SQLite index; filterable by status/step/flag) |
| `GET /traces/{id}` | Full trace JSON |
| `POST /traces/{id}/flag` | Flag trace → run forensics |
| `GET /traces/{id}/diagnosis` | Diagnosis result |
| `POST /evals` | Confirm a flag → create eval case |
| `POST /evals/run` | Re-run full eval dataset |
| `GET /stats` | Dashboard aggregates |

## Component 5: React Trace Explorer

- **Trace view:** react-flow horizontal node graph, one node per step, color-coded: green (healthy), yellow (confidence below threshold), red (diagnosed root cause). Clicking a node opens a span drawer with input, output, prompt, raw response, token counts, latency, confidence.
- **Diff view:** side-by-side comparison of what the step received vs produced vs should have produced (expected value sourced from judge output or eval correction).
- **One-click flag:** runs backward analysis, then displays the diagnosis panel with the evidence chain.
- **Dashboard:** most common failure types (bar), failures per step, failure rate over time (recharts).

## Component 6: Feedback Loop (evals)

Every confirmed flag auto-generates an eval case: original input, failing step, bad output, corrected output (user-editable in UI), failure category. An eval runner re-executes the full eval dataset on demand and records pass/fail history in SQLite, feeding the dashboard's "known failures resolved over time" trend.

## Error Handling

- LLM hard failure after retries: span status=error, downstream skipped, trace explorable.
- Rate limiting (429): exponential backoff with jitter inside the LLM client.
- Judge failure during forensics: diagnosis returns partial scores with the failed step marked unjudgeable rather than aborting.

## Testing Strategy

- pytest unit tests per pipeline step with a mocked LLM client.
- Forensics engine tests against hand-crafted trace fixtures (known root causes → assert correct step + category).
- Integration test running the full chain against recorded real traces.
- Frontend: light vitest coverage for data transforms; manual verification for visuals.

## Success Criteria (demo)

1. Process 50 documents; produce 8–10 failures across different categories.
2. Open a bad output in the trace explorer, click flag, and watch root cause diagnosed in seconds with an evidence chain.
3. Dashboard shows failure distribution and resolution trend.
