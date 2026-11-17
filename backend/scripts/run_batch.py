"""Generate synthetic docs and run the pipeline on each. Requires GEMINI_API_KEY.

Usage (from backend/): python -m scripts.run_batch --n 50 --seed 42
"""
import argparse
import time
from pathlib import Path

from pipeline.docgen import generate_batch
from pipeline.llm import make_provider
from pipeline.orchestrator import run_pipeline
from tracing.exporter import ForensicsExporter
from tracing.recorder import PayloadRecorder
from tracing.setup import build_tracer
from tracing.store import connect

DATA = Path(__file__).resolve().parents[2] / "data"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pause", type=float, default=2.0,
                        help="seconds between docs (free-tier rate limits)")
    args = parser.parse_args()

    conn = connect(DATA / "forensics.db")
    recorder = PayloadRecorder()
    tracer = build_tracer(ForensicsExporter(conn, DATA / "traces", recorder))
    llm = make_provider()

    for doc in generate_batch(args.n, args.seed):
        trace_id = run_pipeline(doc["text"], doc["doc_id"], llm, tracer, recorder)
        marker = f" [{doc['corruption']}]" if doc["corruption"] else ""
        print(f"{doc['doc_id']} ({doc['doc_type']}){marker} -> {trace_id}")
        time.sleep(args.pause)


if __name__ == "__main__":
    main()
