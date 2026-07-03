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
