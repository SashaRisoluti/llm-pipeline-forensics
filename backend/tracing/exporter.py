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
