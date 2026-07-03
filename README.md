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
