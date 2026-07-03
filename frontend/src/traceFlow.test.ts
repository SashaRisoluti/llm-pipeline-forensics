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
