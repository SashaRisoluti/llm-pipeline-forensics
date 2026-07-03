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
