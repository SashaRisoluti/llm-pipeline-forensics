# llm-pipeline-forensics

**Find the step where a multi-step LLM pipeline went wrong — in seconds, not hours — and make sure it stays fixed.**

[![tests](https://github.com/SashaRisoluti/llm-pipeline-forensics/actions/workflows/tests.yml/badge.svg)](https://github.com/SashaRisoluti/llm-pipeline-forensics/actions/workflows/tests.yml)
![licence](https://img.shields.io/badge/licence-MIT-blue)

[GIF: run a batch → open a flagged trace → see the root-cause step highlighted → confirm → eval case created]

## Why it matters

When a document pipeline (intake → extraction → classification → summarisation) returns a wrong summary, the visible error is rarely where the fault started. A hallucinated amount in extraction becomes a wrong category, then a confident but wrong summary. Teams debug this by reading logs step by step.

This tool records every step as an OpenTelemetry span and, when a run is flagged, walks the trace backwards with an LLM judge to find **the first step where quality collapsed**. Confirmed diagnoses become **regression eval cases**, so a known failure that comes back is caught automatically. This is the observability and evaluation layer that regulated organisations need before they put LLM pipelines in front of staff or customers.

## Quickstart

```bash
export GEMINI_API_KEY=...            # Google AI Studio, free tier works
docker compose up -d --build && docker compose exec backend python -m scripts.run_batch --n 50 --seed 42
# open http://localhost:5173
```

## How it works

```
synthetic documents ──► intake ──► extraction ──► classification ──► summarisation
 (invoices, contracts,        │            │                │                 │
  meeting notes, reports;     └────────────┴── OpenTelemetry spans ───────────┘
  ~20% deliberately corrupted)                      │
                                                    ▼
                                SQLite + JSON traces ─► FastAPI ─► React UI
                                                    │
                        flag a bad run ─► LLM judge scores each step 1–5
                                                    │
                    root cause = earliest step scoring ≥ 2 below its predecessor
                       (a step that errored scores 1 automatically)
                                                    │
                       second LLM call assigns one failure category
                                                    │
                  confirm ─► eval case ─► re-run eval set to check regressions
```

**What each span records:** prompt, raw response, token counts, latency, confidence.

**Failure categories:** extraction hallucination · misclassification · propagation error · context loss · prompt failure.

**Synthetic data with known faults.** The generator produces four document types and injects three kinds of corruption (stripped dates, currency mismatch, ambiguous category), so every diagnosis can be checked against the fault that was actually injected.

## Results

| Metric | Value |
|---|---|
| Root-cause step correctly identified on corrupted documents | [x / y on seed 42] |
| Failure category matching the injected corruption | [x %] |
| Median time from flag to diagnosis | [seconds] |
| Eval cases that stay fixed after a prompt change | [x / y] |

<!-- Compute these with a script in scripts/ and paste the output. Do not estimate. -->

## Interface

[Screenshot 1: dashboard with failure types over time]
[Screenshot 2: trace view, react-flow graph with the root-cause step highlighted]
[Screenshot 3: diagnosis panel with judge scores and the input/output diff]

## API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/runs` | Run the pipeline on a document |
| GET | `/api/traces`, `/api/traces/{id}` | List and inspect traces |
| POST | `/api/traces/{id}/flag` | Flag a bad run and trigger diagnosis |
| GET | `/api/traces/{id}/diagnosis` | Root cause, per-step scores, category |
| POST/GET | `/api/evals` | Create or list eval cases |
| POST | `/api/evals/run` | Re-run the eval set |
| GET | `/api/stats` | Aggregates for the dashboard |

## Stack

Python 3.12 · Pydantic v2 · OpenTelemetry SDK with a custom exporter · SQLite · FastAPI · React + react-flow + recharts · Docker Compose · LLM: Gemini Flash-Lite by default, behind a provider interface ([AWS Bedrock / Azure OpenAI adapters: roadmap])

## Development

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
pytest                      # runs fully offline with a mock LLM
uvicorn api.app:create_default_app --factory --reload
cd ../frontend && npm install && npm run dev
```

## Limitations

- The judge is itself an LLM: scores are noisy. Diagnoses are suggestions that a human confirms before they become eval cases.
- Documents are synthetic. Real documents (KYC files, credit applications) would need new corruption types and a domain-specific judge prompt.
- The root-cause rule (a drop of ≥ 2 points) is a heuristic; a calibrated threshold is on the roadmap.

## Roadmap

- [ ] Provider adapters for AWS Bedrock and Azure OpenAI
- [ ] Financial document flow (credit application intake) with domain-specific failure categories
- [ ] Judge agreement study: LLM judge vs human labels on 100 traces

## Licence

MIT
