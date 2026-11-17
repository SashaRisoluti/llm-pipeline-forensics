"""Score forensics diagnoses against the corruptions docgen injected.

Runs a seeded synthetic batch through the pipeline, diagnoses every corrupted
document as if a user had flagged it, and prints a markdown table: how often the
diagnosed root-cause step and failure category match the expected ones, and the
median time from flag to diagnosis. Requires GEMINI_API_KEY.

Usage (from backend/): python -m scripts.evaluate_diagnosis --n 50 --seed 42
"""
import argparse
import json
import sqlite3
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from opentelemetry.trace import Tracer

from forensics.engine import diagnose
from pipeline.docgen import BatchDoc, generate_batch
from pipeline.llm import GeminiClient, LLMClient
from pipeline.models import FailureCategory
from pipeline.orchestrator import run_pipeline
from tracing.exporter import ForensicsExporter
from tracing.recorder import PayloadRecorder
from tracing.setup import build_tracer
from tracing.store import connect

DATA = Path(__file__).resolve().parents[2] / "data" / "evaluation"

# Where each corruption is expected to bite, and how. Decided by the author.
EXPECTED: dict[str, tuple[str, FailureCategory]] = {
    "strip_dates": ("extract", FailureCategory.extraction_hallucination),
    "currency_mismatch": ("extract", FailureCategory.extraction_hallucination),
    "ambiguous_category": ("classify", FailureCategory.misclassification),
}


@dataclass(frozen=True)
class Outcome:
    doc_id: str
    corruption: str
    root_cause_step: str
    category: FailureCategory
    seconds: float


@dataclass(frozen=True)
class EvalRun:
    outcomes: list[Outcome]
    n_traces: int
    n_errored: int


def evaluate(
    batch: list[BatchDoc],
    llm: LLMClient,
    conn: sqlite3.Connection,
    tracer: Tracer,
    recorder: PayloadRecorder,
    clock: Callable[[], float] = time.perf_counter,
    pause: float = 0.0,
) -> EvalRun:
    outcomes = []
    n_errored = 0
    for doc in batch:
        trace_id = run_pipeline(doc["text"], doc["doc_id"], llm, tracer, recorder)
        row = conn.execute(
            "SELECT status, json_path FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
        n_errored += row["status"] == "error"
        corruption = doc["corruption"]
        if corruption is not None:
            trace_doc = json.loads(Path(row["json_path"]).read_text(encoding="utf-8"))
            start = clock()
            diagnosis = diagnose(trace_doc, llm)
            seconds = clock() - start
            outcomes.append(Outcome(doc["doc_id"], corruption, diagnosis.root_cause_step,
                                    diagnosis.category, seconds))
        if pause:
            time.sleep(pause)
    return EvalRun(outcomes, n_traces=len(batch), n_errored=n_errored)


def _row(label: str, outcomes: list[Outcome]) -> str:
    n = len(outcomes)
    if n == 0:
        return f"| {label} | 0 | – | – | – |"
    steps = sum(o.root_cause_step == EXPECTED[o.corruption][0] for o in outcomes)
    cats = sum(o.category == EXPECTED[o.corruption][1] for o in outcomes)
    median = statistics.median(o.seconds for o in outcomes)
    return (f"| {label} | {n} | {steps}/{n} ({round(100 * steps / n)}%) "
            f"| {cats}/{n} ({round(100 * cats / n)}%) | {median:.1f} |")


def render_table(outcomes: list[Outcome]) -> str:
    lines = [
        "| Corruption | n | Root-cause step correct | Category correct "
        "| Median flag→diagnosis (s) |",
        "|---|---|---|---|---|",
    ]
    for name in sorted(EXPECTED):
        lines.append(_row(name, [o for o in outcomes if o.corruption == name]))
    lines.append(_row("**all**", outcomes))
    return "\n".join(lines)


def render_report(run: EvalRun) -> str:
    errors = f"Pipeline errors: {run.n_errored}/{run.n_traces} traces"
    return f"{errors}\n\n{render_table(run.outcomes)}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pause", type=float, default=2.0,
                        help="seconds between docs (free-tier rate limits)")
    parser.add_argument("--data-dir", type=Path, default=DATA)
    args = parser.parse_args()

    conn = connect(args.data_dir / "forensics.db")
    recorder = PayloadRecorder()
    tracer = build_tracer(ForensicsExporter(conn, args.data_dir / "traces", recorder))
    run = evaluate(generate_batch(args.n, args.seed), GeminiClient(), conn, tracer,
                   recorder, pause=args.pause)
    print(f"Diagnosis accuracy on injected corruptions (n={args.n}, seed={args.seed})\n")
    print(render_report(run))
    if run.n_traces and run.n_errored == run.n_traces:
        sys.exit("every pipeline run errored: the numbers above measure nothing; check the LLM")


if __name__ == "__main__":
    main()
