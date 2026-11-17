# llm-pipeline-forensics

**Find the step where a multi-step LLM pipeline went wrong — in seconds, not hours — and make sure it stays fixed.**

On a seeded benchmark of injected faults it names the right failing step for 7 of 12 corrupted documents, with a median of 30 s from flag to diagnosis.

[![tests](https://github.com/SashaRisoluti/llm-pipeline-forensics/actions/workflows/tests.yml/badge.svg)](https://github.com/SashaRisoluti/llm-pipeline-forensics/actions/workflows/tests.yml)
![licence](https://img.shields.io/badge/licence-MIT-blue)

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
  meeting notes, reports,     └────────────┴── OpenTelemetry spans ───────────┘
  receipts;                                         │
  ~20% deliberately corrupted)                      │
                                                    ▼
                                SQLite + JSON traces ─► FastAPI ─► React UI
                                                    │
                        flag a bad run ─► LLM judge scores each step 1–5
                                                    │
               root cause = earliest step scoring ≥ 2 below the previous judged step
          (the first step is compared with 5; a step that errored scores 1;
                 a step the judge could not score is skipped)
                                                    │
                       second LLM call assigns one failure category
                                                    │
                  confirm ─► eval case ─► re-run eval set to check regressions
```

**What each span records:** prompt, raw response, token counts, latency, confidence.

**Failure categories:** extraction hallucination · misclassification · propagation error · context loss · prompt failure.

**Synthetic data with known faults.** The generator produces five document types and injects three kinds of corruption (stripped dates, currency mismatch, ambiguous category), so every diagnosis can be checked against the fault that was actually injected.

## Results

Of 50 seeded synthetic documents, 12 carry an injected fault. Each one is flagged, diagnosed, and scored against where that fault is expected to show up: stripped dates and currency mismatch at extraction (extraction hallucination), ambiguous category at classification (misclassification).

| Metric | Value |
|---|---|
| Root-cause step correctly identified on corrupted documents | 7 / 12 (58 %) |
| Failure category matching the injected corruption | 7 / 12 (58 %) |
| Median time from flag to diagnosis | 29.6 s |

| Corruption | n | Root-cause step correct | Category correct | Median flag→diagnosis (s) |
|---|---|---|---|---|
| ambiguous category | 3 | 0 / 3 | 0 / 3 | 32.2 |
| currency mismatch | 5 | 5 / 5 | 5 / 5 | 39.7 |
| stripped dates | 4 | 2 / 4 | 2 / 4 | 17.4 |

Reproduce with `cd backend && python -m scripts.evaluate_diagnosis --n 50 --seed 42` (needs `GEMINI_API_KEY`; measured with `gemini-3.5-flash-lite` on 2026-11-17, 0 / 50 pipeline runs errored). Runs whose pipeline errors are reported and left out of the scores.

Currency mismatches are traced reliably; ambiguous-category faults are not yet traced to classification. Twelve documents is a small sample, so read the percentages as indicative. The timing is wall-clock and includes retry back-off on the Gemini free tier.

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

Python 3.12 · Pydantic v2 · OpenTelemetry SDK with a custom exporter · SQLite · FastAPI · React + react-flow + recharts · Docker Compose · LLM: Gemini Flash-Lite by default, behind a provider interface (`LLM_PROVIDER`) (AWS Bedrock and Azure OpenAI adapters are on the roadmap)

## Development

```bash
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
pytest                      # runs fully offline with a mock LLM
ruff check . && mypy .      # lint and strict type check, as in CI
uvicorn api.app:create_default_app --factory --reload
cd ../frontend && npm install && npm run dev
```

## Limitations

- The judge is itself an LLM: scores are noisy. Diagnoses are suggestions that a human confirms before they become eval cases.
- Documents are synthetic. Real documents (KYC files, credit applications) would need new corruption types and a domain-specific judge prompt.
- The root-cause rule (a drop of ≥ 2 points) is a heuristic; a calibrated threshold is on the roadmap.
- The benchmark has 12 corrupted documents; ambiguous-category faults are currently missed.

## Roadmap

- [ ] Provider adapters for AWS Bedrock and Azure OpenAI
- [ ] Financial document flow (credit application intake) with domain-specific failure categories
- [ ] Judge agreement study: LLM judge vs human labels on 100 traces
- [ ] Measure how many eval cases stay fixed after a prompt change

## Licence

MIT
